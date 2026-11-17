"""Radiosonde decoders of rs1729 (https://github.com/rs1729/RS, GPL-3.0) as external programs (lib\\sonde\\*.exe).

One channel of complex baseband (the VFO channel, or a MULTI channel) goes as raw float32 I/Q into the stdin of every
decoder (`--IQ 0.0 --lpIQ --dc - <rate> 32`); each writes one JSON line per decoded frame (`--json`). While no
decoder has decoded anything, all of them listen (the type is not known); after a frame only the decoder of that type
is kept, and when it is silent for SEARCH_AFTER_S all of them listen again. Without samples for IDLE_S the programs
are ended (a channel that is gone needs no closing); the next samples start them again.

Each program has its own writer thread with a short queue (a slow program loses blocks, the receiver never waits) and
a reader thread for its JSON lines. Built by installer/build_sonde.sh (MSYS2 UCRT64 gcc, static).
"""
import collections
import datetime
import json
import os
import queue
import subprocess
import sys
import threading
import time

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(BASE, "lib", "sonde")
SOURCE = "https://github.com/rs1729/RS"

# program, options; the type names of their JSON ("type") in the comment
DECODERS = (
    ("rs41mod", ["--ptu2", "--ecc2"]),                 # RS41 (Vaisala RS41-SG / SGP / SGM)
    ("dfm09mod", ["--ecc2", "--ptu", "--auto"]),       # DFM (Graw DFM-06 / 09 / 17, PS-15; --auto = both polarities)
    ("m10m20mod", ["--ptu"]),                          # M10, M20 (Meteomodem)
    ("lms6Xmod", []),                                  # LMS (Lockheed Martin LMS6-403)
    ("imet54mod", []),                                 # IMET5 (InterMet iMet-54)
    ("mp3h1mod", ["--ptu"]),                           # MRZ (Meteo-Radiy MRZ-N1 / MP3-H1)
    ("meisei100mod", ["--ecc", "--ptu"]),              # MEISEI (Meisei iMS-100, RS-11G)
    ("mts01mod", []),                                  # MTS01 (Meteosis MTS01)
    ("cf06ht03mod", []),                               # CF-06-AH, HT03G-1U (Chinese)
)
# SONDE > TYPES: the decoders that listen while the type is not known yet (only the sondes launched in the area);
# None = all. Each one is a program per channel (with MULTI per channel), so fewer types = much less CPU.
ENABLED = None


def set_enabled(names):
    """Decoders allowed to listen (program names of DECODERS); None or an empty list = all."""
    global ENABLED
    known = [n for n, _ in DECODERS]
    sel = [n for n in (names or []) if n in known]
    ENABLED = None if not sel or len(sel) == len(known) else set(sel)


def enabled():
    return [n for n, _ in DECODERS if ENABLED is None or n in ENABLED]


SEARCH_AFTER_S = 60.0        # the locked decoder silent this long: all decoders listen again
IDLE_S = 10.0                # no samples this long: the programs are ended
QUEUE_S = 2.0                # seconds of samples waiting for a program (more: the block is dropped for it)
WAIT = False                 # tests: wait for the program instead of dropping (they feed faster than real time)
UP_BELOW = 44000.0           # a channel slower than this goes to the programs at twice the rate (rs41mod fails at
                             # 32 kHz and loses frames of a weak signal at 37.5 kHz; 2x: as good as 48 kHz)
OFFSET_AVG = 0.2             # smoothing of the signal offset (per block)
GPS_LEAP = 18

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def exe(name):
    return os.path.join(LIB, name + (".exe" if sys.platform == "win32" else ""))


def available():
    """Names of the decoders whose program is there."""
    return [n for n, _ in DECODERS if os.path.isfile(exe(n))]


class _Proc:
    """One running decoder program: a writer thread (samples -> stdin) and a reader thread (JSON lines -> out)."""

    def __init__(self, name, opts, rate, out):
        self.name = name
        self.q = queue.Queue()
        self.dropped = 0
        self.queued = 0                  # bytes in the queue
        self.limit = int(QUEUE_S * rate * 8)
        self.p = subprocess.Popen([exe(name), *opts, "--json", "--IQ", "0.0", "--lpIQ", "--dc", "-", str(int(rate)), "32"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  creationflags=_NO_WINDOW, cwd=LIB)
        self.out = out
        threading.Thread(target=self._write, name=f"sonde-{name}-w", daemon=True).start()
        threading.Thread(target=self._read, name=f"sonde-{name}-r", daemon=True).start()

    def put(self, data):
        while WAIT and self.queued > self.limit and self.alive:
            time.sleep(0.005)
        if self.queued > self.limit:
            self.dropped += 1
            return
        self.queued += len(data)
        self.q.put_nowait(data)

    def _write(self):
        try:
            while True:
                data = self.q.get()
                if data is None:
                    break
                self.queued -= len(data)
                self.p.stdin.write(data)
                self.p.stdin.flush()
        except (OSError, ValueError):
            pass
        try:
            self.p.stdin.close()
        except OSError:
            pass

    def _read(self):
        for line in self.p.stdout:
            if line.startswith(b"{"):
                try:
                    j = json.loads(line)
                except ValueError:
                    continue
                if isinstance(j, dict):
                    self.out.append((self.name, j))

    def close(self):
        self.q.put_nowait(None)
        try:
            self.p.kill()
        except OSError:
            pass

    @property
    def alive(self):
        return self.p.poll() is None


class ExtChannel:
    """The decoders of one channel of complex baseband at `rate` (Hz)."""

    def __init__(self, rate):
        self.rate = int(round(rate))
        self.up = 2 if rate < UP_BELOW else 1
        if self.up > 1:                  # interpolation filter: zeros between the samples, low-pass at 0.45 x rate
            from scipy.signal import firwin
            self._h = (firwin(63, 0.45 * rate, fs=self.up * rate) * self.up).astype(np.float32)
            self._zi = np.zeros(len(self._h) - 1, np.complex64)
        self.procs = {}              # name -> _Proc
        self.locked = None           # decoder that decoded last
        self.last_frame = None       # time.monotonic() of its last frame
        self.out = collections.deque(maxlen=200)
        self.frames = 0
        self.offset = None           # Hz: mean frequency of the signal in the channel (from the FM discriminator)
        self._prev = np.complex64(0)
        self._lock = threading.Lock()
        self._fed = 0.0
        self._watch = None

    @property
    def headers(self):               # what the old demodulator called headers: here the frames of the programs
        return self.frames

    @property
    def dropped(self):
        return sum(p.dropped for p in self.procs.values())

    def _start(self, names):
        for name, opts in DECODERS:
            if name in names and name not in self.procs and os.path.isfile(exe(name)):
                try:
                    self.procs[name] = _Proc(name, opts, self.rate * self.up, self.out)
                except OSError as e:
                    print(f"sonde: {name}: {e!r}", flush=True)

    def _stop(self, keep=()):
        for name in [n for n in self.procs if n not in keep]:
            self.procs.pop(name).close()

    def close(self):
        with self._lock:
            self._stop()

    def _idle_watch(self):
        """Ends the programs when no samples came for IDLE_S (the channel was dropped or the decoder turned off)."""
        while True:
            time.sleep(2.0)
            with self._lock:
                if time.monotonic() - self._fed > IDLE_S:
                    self._stop()
                    self.locked = None
                    self._watch = None
                    return

    def process(self, base):
        """Samples of the channel in; the JSON frames decoded since the last call out: [(decoder, dict)]."""
        x = np.asarray(base, np.complex64)
        if len(x) == 0:
            return []
        self._offset(x)
        now = time.monotonic()
        with self._lock:
            self._fed = now
            if self._watch is None:
                self._watch = threading.Thread(target=self._idle_watch, name="sonde-idle", daemon=True)
                self._watch.start()
            if self.locked and (self.last_frame is None or now - self.last_frame > SEARCH_AFTER_S
                                or (ENABLED is not None and self.locked not in ENABLED)):
                self.locked = None                    # silent (or its type switched off): listen for the types again
            want = [self.locked] if self.locked else enabled()
            for name in [n for n in self.procs if not self.procs[n].alive]:
                self.procs.pop(name).close()          # a program that ended is started again
            self._stop(keep=want)
            self._start(want)
            data = self._upsample(x).view(np.float32).tobytes()    # interleaved float32 I, Q
            for p in self.procs.values():
                p.put(data)
            got = []
            while self.out:
                name, j = self.out.popleft()
                if self.locked and name != self.locked:
                    continue                          # a stray frame of a program being ended
                got.append((name, j))
                self.locked, self.last_frame = name, now
                self.frames += 1
            if got and len(self.procs) > 1:
                self._stop(keep=(self.locked,))
        return got

    def _upsample(self, x):
        if self.up == 1:
            return x
        from scipy.signal import lfilter
        y = np.zeros(self.up * len(x), np.complex64)
        y[::self.up] = x
        y, self._zi = lfilter(self._h, 1, y, zi=self._zi)
        return y.astype(np.complex64)

    def _offset(self, x):
        """Mean instantaneous frequency of the block (smoothed): the offset of an FSK signal from the channel centre."""
        y = np.concatenate(([self._prev], x))
        self._prev = x[-1]
        d = y[1:] * np.conj(y[:-1])
        if not np.any(d):
            return
        f = float(np.angle(d.sum())) * self.rate / (2 * np.pi)
        self.offset = f if self.offset is None else self.offset + OFFSET_AVG * (f - self.offset)


# ---------- JSON of rs1729 -> a frame of RADIMCOM ----------

TYPES = {"LMS": "LMS6", "IMET5": "iMet-54", "MEISEI": "iMS-100", "CF06": "CF-06", "HT03": "HT03G"}


def _gps_time(j):
    """UTC epoch of the frame time; rs1729 gives GPS time (ref_datetime "GPS") or UTC."""
    s = j.get("datetime")
    if not s:
        return None
    try:
        t = datetime.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc).timestamp()
        frac = s[19:].rstrip("Z")
        if frac.startswith("."):
            t += float(frac)
    except ValueError:
        return None
    if j.get("ref_datetime") == "GPS":
        t -= GPS_LEAP
    return round(t, 3)


def to_frame(j):
    """A frame dict of sonde.py (type, serial, lat, lon, alt, vh, dir, vv, ...) from one JSON line, or None."""
    typ = str(j.get("type") or "")
    sid = str(j.get("id") or "")
    if not typ:
        return None
    t = TYPES.get(typ, typ)
    if typ == "MEISEI" and "RS11G" in str(j.get("subtype", "")).upper().replace("-", ""):
        t = "RS-11G"
    d = {"type": t, "serial": sid or None, "decoder": "rs1729"}
    if typ == "DFM" and (not sid or "xxxx" in sid):
        d["serial"] = None                            # the serial comes after a few frames (sonde.py names it by MHz)
    for k_in, k_out in (("frame", "frame"), ("lat", "lat"), ("lon", "lon"), ("alt", "alt"), ("vel_h", "vh"),
                        ("heading", "dir"), ("vel_v", "vv"), ("sats", "sats"), ("batt", "batt"), ("temp", "temp"),
                        ("humidity", "rh"), ("pressure", "pres"), ("subtype", "subtype"), ("bt", "burst_timer"),
                        ("tx_frequency", "tx_khz")):
        v = j.get(k_in)
        if v is None or (isinstance(v, (int, float)) and k_in in ("temp", "humidity", "pressure") and v <= -273):
            continue
        d[k_out] = v
    for k, n in (("lat", 6), ("lon", 6), ("alt", 1), ("vh", 2), ("dir", 1), ("vv", 2), ("temp", 1), ("rh", 1), ("pres", 1)):
        if isinstance(d.get(k), (int, float)):
            d[k] = round(float(d[k]), n)
    if d.get("lat") == 0 and d.get("lon") == 0:
        for k in ("lat", "lon", "alt"):
            d.pop(k, None)                            # no GPS fix yet
    if j.get("encrypted"):
        d["encrypted"] = True
    if j.get("aux"):
        d["xdata"] = str(j["aux"])
    if d.get("burst_timer") == 65535:
        d.pop("burst_timer")
    gt = _gps_time(j)
    if gt is not None:
        d["gps_time"] = gt
    return d

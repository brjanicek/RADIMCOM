"""ISM decoder: 433 / 868 MHz devices (weather sensors, remote controls, tyre sensors...) with rtl_433 (lib\\ism\\rtl_433.exe).

rtl_433 (Benjamin Larsson and contributors, GPLv2+, https://github.com/merbanan/rtl_433) runs as a separate process,
one per VFO. The dongle stays in RADIMCOM: rtl_433 connects to a small rtl_tcp server here (127.0.0.1, free port) and
gets the raw I/Q bytes of this VFO, exactly like from a network dongle. Reading the samples from standard input is not
an option on Windows: rtl_433 leaves its stdin in text mode there, so the byte 0x1A would end the stream.

    receiver thread --raw u8 I/Q--> queue --> rtl_tcp socket --> rtl_433 --stdout JSON--> card, daily log

Its commands (frequency, gain...) are ignored: the VFO decides where the dongle is, gain included. rtl_433 is told the
frequency only because it chooses the FSK detector by it and reports it; a smaller retune needs no restart.

Channels: rtl_433 does not filter, it finds pulses in the envelope of everything it gets. Given the whole 2 MHz, the noise
of the whole band and all transmitters in it merge into long "packages", and of those at most one device is decoded. So the
2.048 MS/s of the dongle are cut here into narrow channels of 256 kS/s (mixed down, low-pass filtered, decimated by 8),
each with its own rtl_433: 433.92 MHz (most devices), 433.42 MHz (Somfy and others) and 434.42 MHz (car keys, e.g.
VW / Škoda / Audi; 434.40 MHz is a common key frequency), 868.30 MHz. Measured on a 5 min
recording at 433.92 MHz: 107 messages in the whole band, 236 in the 256 kS/s channel, and rtl_433 needs 6x less CPU.
The filtering runs in the thread that sends the samples of each channel, not in the receiver thread.

RAW: with the RAW option rtl_433 also runs its pulse analyzer (-A); a package of at least RAW_MIN_PULSES pulses that no
decoder read is shown as a RAW row (modulation guess, pulses, length, level, a pulse view link at triq.org).
"""
import collections
import json
import os
import queue
import re
import socket
import struct
import subprocess
import threading
import time

import numpy as np

from paths import BASE, data

EXE = os.path.join(BASE, "lib", "ism", "rtl_433.exe")
# A rate rtl_433 lists as valid. It covers all of 433.05-434.79 MHz, and the spectrum is twice as fast as at 1.024 MS/s
# (one waterfall line per block of samples, so the speed of the picture follows the sample rate).
ISM_RATE = 2048000
# middle of the 433.05-434.79 MHz band; middle of the 868.0-868.6 MHz sub-band
ISM_FREQS = (433920000, 868300000)
ISM_DEFAULT = ISM_FREQS[0]
CH_RATE = 256000              # sample rate of a channel for rtl_433 (default)
CH_TAPS_PER_DOWN = 16         # low-pass of a channel: 16 taps per decimation step + 1 (129 taps for 8), at least 65
CH_CUTOFF = 0.45              # its -6 dB point, as a part of the channel's sample rate (115 kHz at 256 kS/s)
CH_GAIN = 1.0                 # the channel back to u8 bytes, same scale as the dongle (measured: clipping stays ~0.002 %)
# channels around each preset: (offset from the centre of the dongle, sample rate, rtl_433 -Y autolevel)
# 433: OOK; autolevel lost messages there. 868: FSK; autolevel found the weaker devices.
CHANNELS = {433920000: ((0, CH_RATE, False), (-500000, CH_RATE, False), (500000, CH_RATE, False)),   # 433.92, 433.42, 434.42
            868300000: ((0, CH_RATE, True), (650000, CH_RATE, True))}   # 868.30 sensors, 868.95 wM-Bus meters
RAW_MIN_PULSES = 20           # smaller undecoded packages are noise
RAW_MERGE_S = 10.0            # RAW packages of one kind near one frequency within this time = one row with a count
RAW_MERGE_HZ = 15000
RAW_SAME_HZ = 10000           # a RAW package this close to a decoded one at the same time is that one
RAW_WAIT_S = 1.5              # a RAW row waits this long for a decoded message of the same package (they come on stdout)
RESTART_HZ = 5000000          # a bigger retune restarts rtl_433 (its FSK detector depends on the frequency)
RESTART_WAIT_S = 2.0          # at least this long between two starts, if rtl_433 keeps ending
REPEAT_S = 60.0               # the same message of a device within this time of its last one = one row with a count
METER_MERGE_S = 3600.0        # Wireless M-Bus meters (hundreds around a block of flats): one row per meter for an hour
SAME_PACKET_S = 0.5           # two decoders reporting one packet (same level and frequency) come this close together
TCP_QUEUE = 64                # raw blocks waiting for rtl_433; more = it is stuck, drop
MAX_HISTORY = 500
# devices (DEVICES and TIMELINE views): one entry per model + ID + channel, with its latest values
MAX_DEVICES = 300             # the least recently heard one goes (passing cars with TPMS, meters of a block of flats)
DEV_TIMES_S = 3600.0          # message times kept for the timeline
DEV_TIMES_MAX = 400
SERIES_STEP_S = 300           # temperature / humidity history: one point per 5 minutes (the latest value in it)
SERIES_KEEP_S = 86400.0
SERIES_FIELDS = ("temperature_C", "humidity")
ACT_STEP_S = 300              # activity for DEVICES / TIMELINE at 6 h and 24 h: messages per 5 minutes for 24 h
HIST_STEP_S = 60              # detail of one device (its tab with charts): one point per minute for 24 h, all numbers
HIST_KEEP_S = 86400.0
HIST_SKIP = {"battery_ok"}    # shown as a state, not a curve
RATE_MINUTES = 60             # messages per minute, for the sparkline in the header
NEW_KEEP_S = 600              # a device never heard before on this PC is marked NEW this long
# names, pins and hidden devices given in the page; devices heard on this PC (for NEW); station-wide, all VFOs
NAMES_FILE = data("ism_devices.json")
KNOWN_FILE = data("ism_known.json")
KNOWN_KEEP_DAYS = 60          # a device not heard this long is forgotten (comes NEW again)
KNOWN_SAVE_S = 60.0
# a RAW signal marked with a name (e.g. a car key: rolling code, no rtl_433 decoder): its later packages with the same
# modulation guess, near the frequency and with about the same number of pulses are that device
RAW_SIG_HZ = 30000
RAW_SIG_PULSES = 0.3

# fields with their own column, or not worth showing
_COLUMNS = {"time", "model", "id", "channel", "mod", "freq", "freq1", "freq2", "rssi", "snr", "noise", "protocol", "mic"}
# field name -> unit; other fields are shown as name=value
# (rtl_433 runs with -C si, so °F, mph, inch... arrive converted)
_UNITS = {"temperature_C": " °C", "temperature_F": " °F", "humidity": " %", "moisture": " %", "pressure_hPa": " hPa",
          "pressure_kPa": " kPa", "pressure_PSI": " PSI", "wind_avg_km_h": " km/h", "wind_max_km_h": " km/h",
          "wind_avg_m_s": " m/s", "wind_max_m_s": " m/s", "wind_dir_deg": "°", "rain_mm": " mm", "uv": " UV",
          "rain_rate_mm_h": " mm/h", "light_lux": " lux", "battery_mV": " mV", "power_W": " W", "energy_kWh": " kWh"}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# pulse analyzer (stderr): one block per package
_AN_START = re.compile(r"^Detected (OOK|FSK) package")
_AN_COUNT = re.compile(r"^Total count:\s*(\d+),\s*width:\s*([\d.]+) ms")
_AN_LEVEL = re.compile(r"^RSSI:\s*(-?[\d.]+) dB SNR:\s*(-?[\d.]+) dB")
_AN_FREQ = re.compile(r"^Frequency offsets.*\(([+-][\d.]+) kHz")
_AN_GUESS = re.compile(r"^Guessing modulation:\s*(.*)")
_AN_VIEW = re.compile(r"^view at (https://triq\.org/\S+)")
_AN_FLEX = re.compile(r"^Use a flex decoder with (.*)")
# with -F log the analyzer's demodulation attempt prints one line on stdout, in the order of the stderr blocks
_AN_CODES = re.compile(r"Analyzer Device codes \[(.*)\]")
RAW_CODES_MAX = 160           # characters of the codes shown in a RAW row


def _clean(value):
    """Text from a radio message: control characters could break a line of the log."""
    return _CONTROL.sub(" ", str(value))


def _field(name, value):
    if name == "battery_ok":
        return f"Batt {'OK' if value else 'LOW'}"
    unit = _UNITS.get(name)
    return f"{_clean(value)}{unit}" if unit else f"{_clean(name)}={_clean(value)}"


# Wireless M-Bus meters (868.95 MHz): mostly encrypted, the raw fields would only make long rows
_MBUS_KEEP = ("mode", "M", "type_string", "type", "version")


def message_text(j):
    """All fields of a device message that have no column of their own, readable."""
    if str(j.get("model", "")).startswith("Wireless-MBus"):
        parts = [_field(k, j[k]) if k != "type_string" else _clean(j[k]) for k in _MBUS_KEEP if j.get(k) not in (None, "")]
        if j.get("payload_encrypted"):
            parts.append("encrypted")
        return " · ".join(parts)
    return " · ".join(_field(k, v) for k, v in j.items() if k not in _COLUMNS)


def message_fields(j):
    """The same fields as message_text, as values (numbers stay numbers) for the device cards."""
    keys = _MBUS_KEEP if str(j.get("model", "")).startswith("Wireless-MBus") else [k for k in j if k not in _COLUMNS]
    out = {}
    for k in keys:
        v = j.get(k)
        if v is None or v == "":
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            v = v if isinstance(v, bool) else _clean(v)[:80]
        out[_clean(k)[:40]] = v
    if str(j.get("model", "")).startswith("Wireless-MBus") and j.get("payload_encrypted"):
        out["encrypted"] = True
    return out


def load_names():
    """{device key: {"name", "pin", "hide"}} from data/ism_devices.json."""
    try:
        with open(NAMES_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def set_name(key, name=None, pin=None, hide=None, sig=None):
    """Changes the name, pin or hidden flag of one device; returns all names. Read again first: other VFOs write too.
    sig: the signature of a marked RAW signal (raw_match); a mark without a name is removed."""
    key = _clean(key)[:200]
    names = load_names()
    e = dict(names.get(key) or {})
    if name is not None:
        e["name"] = _clean(name).strip()[:40]
    if pin is not None:
        e["pin"] = bool(pin)
    if hide is not None:
        e["hide"] = bool(hide)
    if sig is not None:
        e["sig"] = sig
    if not e.get("name"):
        e.pop("sig", None)
    e = {k: v for k, v in e.items() if v}
    if e:
        names[key] = e
    else:
        names.pop(key, None)
    tmp = NAMES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False, indent=1)
    os.replace(tmp, NAMES_FILE)
    return names


_sigs = [None, []]                # mtime of data/ism_devices.json, [(device key, signature)]


def raw_sigs():
    """The marked RAW signals, read again when the file changed (also by another VFO)."""
    try:
        mt = os.stat(NAMES_FILE).st_mtime
    except OSError:
        return []
    if _sigs[0] != mt:
        _sigs[:] = [mt, [(k, e["sig"]) for k, e in load_names().items()
                         if isinstance(e, dict) and isinstance(e.get("sig"), dict)]]
    return _sigs[1]


def raw_match(freq_hz, mod, guess, pulses):
    """Device key of the marked RAW signal this package belongs to, or None."""
    for key, s in raw_sigs():
        try:
            if abs(freq_hz - s["f"]) <= RAW_SIG_HZ and s.get("mod", "") == mod and s.get("guess") == guess \
                    and abs(pulses - s["p"]) <= max(3, s["p"] * RAW_SIG_PULSES):
                return key
        except (KeyError, TypeError):
            continue
    return None


def _load_known():
    try:
        with open(KNOWN_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return {str(k): float(v) for k, v in d.items()} if isinstance(d, dict) else {}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


class Channel:
    """One rtl_433 with its rtl_tcp server, fed by a narrow channel cut from the dongle samples (or by all of them)."""

    def __init__(self, dec, fs, center_hz, offset_hz, raw, rate=CH_RATE, autolevel=False):
        self.dec = dec
        self.offset = offset_hz
        self.fs_in = fs
        self.autolevel = autolevel
        self.down = fs // rate if fs % rate == 0 and fs > rate else 1
        self.fs = fs // self.down
        self.start_hz = center_hz + offset_hz          # what rtl_433 is told
        self.raw = raw
        self.proc = self.srv = self.conn = None
        self.q = queue.Queue(maxsize=TCP_QUEUE)
        self.log = collections.deque(maxlen=10)       # last lines rtl_433 printed (for errors)
        self.decoded = collections.deque(maxlen=50)   # (time, rssi, snr, MHz) of decoded packages, to tell RAW ones apart
        self.pending = []                             # RAW candidates waiting RAW_WAIT_S
        self.plock = threading.Lock()
        self.attempts = 0                             # analyzer blocks with a demodulation attempt (stderr)
        self.n_codes = 0                              # their codes lines (stdout), in the same order
        self.codes = {}
        if self.down > 1:
            from scipy.signal import firwin
            n = max(CH_TAPS_PER_DOWN * self.down + 1, 65)
            n += (-(n - 1)) % self.down                  # (taps - 1) a multiple of the decimation
            self.h = firwin(n, CH_CUTOFF * self.fs, fs=fs, window=("kaiser", 7.0)).astype(np.float32)
            self.tail = np.zeros(n - 1, np.complex64)
            self.phase = 0.0
            self.lut = None
            self.w = -2 * np.pi * offset_hz / fs       # rad per input sample

    # ---------- the narrow channel ----------

    def channel(self, raw):
        """u8 I/Q of the dongle -> u8 I/Q of this channel (mixed to 0 Hz, filtered, decimated)."""
        if self.down == 1:
            return raw
        from scipy.signal import upfirdn
        x = raw.astype(np.float32)
        x -= 127.5
        x = x.view(np.complex64)
        if self.offset:
            if self.lut is None or self.lut.size != x.size:
                self.lut = np.exp(1j * self.w * np.arange(x.size)).astype(np.complex64)
            x = x * (self.lut * np.complex64(np.exp(1j * self.phase)))
            self.phase = (self.phase + self.w * x.size) % (2 * np.pi)
        xe = np.concatenate((self.tail, x))
        y = upfirdn(self.h, xe, down=self.down)
        # outputs whose filter window lies inside xe: index k*down with k*down >= len(h) - 1
        k0 = (self.h.size - 1) // self.down
        k1 = (xe.size - 1) // self.down
        y = y[k0:k1 + 1]
        self.tail = xe[(k1 + 1) * self.down - (self.h.size - 1):]
        out = np.empty(y.size * 2, np.float32)
        out[0::2] = y.real
        out[1::2] = y.imag
        out *= CH_GAIN
        out += 128.0                                 # + 127.5, and truncating below rounds
        np.clip(out, 0, 255, out=out)
        return out.astype(np.uint8).tobytes()

    # ---------- process and server ----------

    def command(self, port):
        cmd = [EXE, "-c", "0", "-d", f"rtl_tcp:127.0.0.1:{port}", "-f", str(int(self.start_hz)), "-s", str(self.fs),
               "-F", "json", "-F", "log", "-C", "si", "-M", "time:off", "-M", "level", "-M", "protocol"]
        if self.autolevel:
            cmd += ["-Y", "autolevel"]
        return cmd + ["-A"] if self.raw else cmd

    def start(self):
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        port = self.srv.getsockname()[1]
        threading.Thread(target=self._accept, args=(self.srv, self.q), name="ism-tcp", daemon=True).start()
        self.proc = subprocess.Popen(self.command(port), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, cwd=os.path.dirname(EXE),
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._reader, args=(self.proc,), name="ism-out", daemon=True).start()
        threading.Thread(target=self._stderr, args=(self.proc,), name="ism-log", daemon=True).start()

    def stop(self):
        p, self.proc = self.proc, None
        self.close_server()
        if p:
            try:
                p.terminate()
                p.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                p.kill()

    def close_server(self):
        srv, conn, self.srv, self.conn = self.srv, self.conn, None, None
        for s in (conn, srv):
            if s:
                try:
                    s.close()
                except OSError:
                    pass
        try:
            self.q.put_nowait(None)
        except queue.Full:
            pass

    def feed(self, raw):
        self._raw_flush()
        if self.conn is None:
            return
        try:
            self.q.put_nowait(raw)
        except queue.Full:
            self.dec.dropped += 1

    def _accept(self, srv, q):
        try:
            conn, _ = srv.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            conn.sendall(b"RTL0" + struct.pack(">II", 0, 0))     # rtl_tcp header: tuner 0 (unknown), 0 gain steps
        except OSError:
            return                           # server closed
        with self.dec.lock:
            if self.srv is not srv:          # stopped in the meantime
                conn.close()
                return
            self.conn = conn
        self.dec._emit_state()
        while True:
            data = q.get()
            if data is None or self.conn is not conn:
                return
            try:
                conn.sendall(self.channel(data))
            except OSError:
                return
            except Exception as e:           # a bug in the filter must not stop quietly
                self.log.append(f"channel: {e!r}")
                self.close_server()
                return

    def _reader(self, p):
        for line in p.stdout:
            if not line.startswith(b"{"):
                text = line.decode("utf-8", "replace").strip()
                m = _AN_CODES.search(text)
                if m:
                    self.codes[self.n_codes] = m.group(1)
                    self.n_codes += 1
                    while len(self.codes) > 200:
                        self.codes.pop(next(iter(self.codes)))
                elif text:
                    self.log.append(text)    # -F log: messages, warnings and errors of rtl_433
                continue
            try:
                j = json.loads(line)
                if isinstance(j, dict) and j.get("model"):
                    mhz = j.get("freq") if j.get("freq") is not None else j.get("freq1")
                    self.decoded.append((time.time(), j.get("rssi"), j.get("snr"), mhz))
                    self.dec._handle(j, self)
            except (ValueError, TypeError):
                continue                     # one odd line must not stop the decoder
        p.wait()
        self.dec._ended(self, p)

    def _stderr(self, p):
        block = None                         # the analyzer block being read
        for line in p.stderr:
            text = line.decode("utf-8", "replace").rstrip()
            if _AN_START.match(text):
                self._raw_block(block)
                block = {"mod": text.split()[1]}
                continue
            if block is None:
                if text.strip():
                    self.log.append(text.strip())
                continue
            if text.startswith("Attempting demodulation"):
                block["attempt"] = self.attempts    # its codes line on stdout has this number
                self.attempts += 1
            for key, rx in (("count", _AN_COUNT), ("level", _AN_LEVEL), ("foff", _AN_FREQ), ("guess", _AN_GUESS),
                            ("view", _AN_VIEW), ("flex", _AN_FLEX)):
                m = rx.match(text.strip())
                if m and key not in block:
                    block[key] = m.groups()
                    break
            if "flex" in block:              # the last line of a block
                self._raw_block(block)
                block = None
            self._raw_flush()
        self._raw_block(block)

    # ---------- RAW: packages no decoder read ----------

    def _raw_block(self, b):
        if not b or "count" not in b or int(b["count"][0]) < RAW_MIN_PULSES:
            return
        with self.plock:
            self.pending.append((time.time(), b))
        self._raw_flush()

    def _raw_flush(self):
        """Also called with every block of samples, so the last RAW rows do not wait for the next package."""
        if not self.pending:
            return
        now = time.time()
        ready = []
        with self.plock:
            while self.pending and now - self.pending[0][0] >= RAW_WAIT_S:
                ready.append(self.pending.pop(0))
        for t, b in ready:
            if not self._was_decoded(t, b):
                self.dec._handle_raw(b, self)

    def _was_decoded(self, t, b):
        """Same level (OOK), or the same frequency at the same time (FSK: the analyzer measures the level otherwise)."""
        rssi, snr = (float(b["level"][0]), float(b["level"][1])) if "level" in b else (None, None)
        hz = self.start_hz + float(b["foff"][0]) * 1e3 if "foff" in b else None
        for td, r, s, mhz in list(self.decoded):
            if abs(td - t) >= RAW_WAIT_S + 1:
                continue
            if rssi is not None and r is not None and s is not None \
                    and abs(float(r) - rssi) < 0.06 and abs(float(s) - snr) < 0.06:
                return True
            if hz is not None and isinstance(mhz, (int, float)) and abs(mhz * 1e6 - hz) <= RAW_SAME_HZ:
                return True
        return False


class IsmDecoder:
    def __init__(self, on_event, on_state):
        self.on_event = on_event      # on_event("ism", message)
        self.on_state = on_state
        self.enabled = False
        self.raw = False              # RAW rows for packages no decoder read (rtl_433 -A)
        self.error = None
        self.count = 0                # all messages, also repeated ones
        self.raw_count = 0
        self.dropped = 0
        self.fs = 0
        self.center_hz = 0.0          # where the dongle is now
        self.start_hz = 0.0           # where it was when the channels started
        self.next_id = 1
        self.history = collections.deque(maxlen=MAX_HISTORY)
        self.aliases = {}             # model -> all models rtl_433 reported for the same packets
        self.lock = threading.Lock()
        self.chans = []
        self.not_before = 0.0
        self.devices = collections.OrderedDict()   # device key -> device, the least recently heard first
        self.rate = collections.deque(maxlen=RATE_MINUTES)   # [minute, messages]
        self.known = None             # device key -> last heard (epoch s); loaded with the first message
        self.known_saved = 0.0

    # ---------- control ----------

    def set_enabled(self, on):
        with self.lock:
            self.enabled = bool(on)
            self.error = None
            self.not_before = 0.0
            if not self.enabled:
                self._stop()
        self._emit_state()

    def set_raw(self, on):
        """RAW on / off: rtl_433 starts again with or without its pulse analyzer."""
        on = bool(on)
        if on == self.raw:
            return
        with self.lock:
            self.raw = on
            self._stop()                     # the next samples start the channels again
            self.not_before = 0.0
        self._emit_state()

    def info(self):
        return {"enabled": self.enabled, "error": self.error, "count": self.count, "dropped": self.dropped,
                "raw": self.raw, "raw_count": self.raw_count,
                "running": bool(self.chans) and all(c.conn is not None for c in self.chans),
                "channels": [round(c.start_hz + self.center_hz - self.start_hz) for c in self.chans],
                "channel_rates": [c.fs for c in self.chans], "rate": self._rate_list(),
                "center_hz": self.center_hz, "fs": self.fs}

    def _rate_list(self):
        """Messages per minute, the last RATE_MINUTES minutes, the oldest first (0 for a quiet minute)."""
        now_min = int(time.time() // 60)
        by_min = dict(self.rate)
        return [by_min.get(m, 0) for m in range(now_min - RATE_MINUTES + 1, now_min + 1)]

    def messages(self):
        with self.lock:
            return list(self.history)

    def device_list(self):
        with self.lock:
            return [self._dev_public(d) for d in self.devices.values()]

    def clear(self):
        with self.lock:
            self.history.clear()
            self.devices.clear()
            self.rate.clear()
            self.count = self.raw_count = 0
        self._emit_state()

    # ---------- devices ----------

    @staticmethod
    def _dev_public(d):
        """A device for the page; its detail history only on request (device_history)."""
        out = {k: v for k, v in d.items() if k != "hist"}
        return dict(out, times=list(d["times"]), series=[list(p) for p in d["series"]], fields=dict(d["fields"]),
                    act=[list(p) for p in d["act"]])

    def device_history(self, key):
        """The device and its history for its tab: [[minute, messages, rssi, snr, {field: number}], ...] for 24 h."""
        with self.lock:
            d = self.devices.get(key)
            if d is None:
                return None
            return dict(self._dev_public(d), hist=[[t, n, r, s, dict(f)] for t, n, r, s, f in d["hist"]])

    def _dev_key(self, model, dev_id, channel):
        """One key for a device also when more decoders of rtl_433 read it (the alphabetically first of their names)."""
        return f"{min(self.aliases.get(model, {model}))}|{dev_id}|{channel}"

    def _device(self, model, row, fields, now):
        """Updates the device of a message (under self.lock); returns its public copy."""
        key = self._dev_key(model, row["dev_id"], row["channel"])
        d = self.devices.pop(key, None)
        if d is None:
            if self.known is None:
                self.known = _load_known()
            d = {"key": key, "model": row["model"], "dev_id": row["dev_id"], "channel": row["channel"], "first": now,
                 "n": 0, "fields": {}, "times": collections.deque(maxlen=DEV_TIMES_MAX), "series": [], "hist": [], "act": [],
                 "new": key not in self.known}
            while len(self.devices) >= MAX_DEVICES:
                self.devices.popitem(last=False)
        self.devices[key] = d                           # the most recently heard last
        d.update(last=now, model=row["model"], freq_hz=row["freq_hz"], rssi=row["rssi"], snr=row["snr"],
                 mod=row["mod"], protocol=row["protocol"], mic=row["mic"])
        d["n"] += 1
        d["fields"] = fields
        d["times"].append(round(now, 1))
        while d["times"] and now - d["times"][0] > DEV_TIMES_S:
            d["times"].popleft()
        vals = [fields.get(k) if isinstance(fields.get(k), (int, float)) and not isinstance(fields.get(k), bool) else None
                for k in SERIES_FIELDS]
        if any(v is not None for v in vals):
            t = int(now // SERIES_STEP_S) * SERIES_STEP_S
            s = d["series"]
            if s and s[-1][0] == t:
                s[-1] = [t] + vals
            else:
                s.append([t] + vals)
            while s and now - s[0][0] > SERIES_KEEP_S:
                s.pop(0)
        ta = int(now // ACT_STEP_S) * ACT_STEP_S
        a = d["act"]
        if a and a[-1][0] == ta:
            a[-1][1] += 1
        else:
            a.append([ta, 1])
        while a and now - a[0][0] > HIST_KEEP_S:
            a.pop(0)
        nums = {k: v for k, v in fields.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in HIST_SKIP}
        t = int(now // HIST_STEP_S) * HIST_STEP_S
        h = d["hist"]
        if h and h[-1][0] == t:                          # the latest values of the minute, its message count
            h[-1] = [t, h[-1][1] + 1, row["rssi"], row["snr"], nums]
        else:
            h.append([t, 1, row["rssi"], row["snr"], nums])
        while h and now - h[0][0] > HIST_KEEP_S:
            h.pop(0)
        self.known[key] = now
        return self._dev_public(d)

    def _save_known(self, now):
        """Devices heard on this PC to data/ism_known.json, at most once a minute (merged: other VFOs write too)."""
        if self.known is None or now - self.known_saved < KNOWN_SAVE_S:
            return
        self.known_saved = now
        with self.lock:
            mine = list(self.known.items())
        try:
            merged = _load_known()
            for k, t in mine:
                merged[k] = max(t, merged.get(k, 0))
            old = now - KNOWN_KEEP_DAYS * 86400
            merged = {k: round(t) for k, t in merged.items() if t >= old}
            tmp = KNOWN_FILE + f".{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(merged, f)
            os.replace(tmp, KNOWN_FILE)
        except OSError:
            pass

    # ---------- samples from the receiver thread ----------

    def feed_raw(self, raw, fs, center_hz):
        """raw: uint8 I/Q from an RTL dongle (the ISM key is not offered on LimeSDR); fs and centre of the dongle."""
        if not self.enabled or raw.dtype != np.uint8:
            return
        self.center_hz = center_hz
        if not self.chans or fs != self.fs or abs(center_hz - self.start_hz) > RESTART_HZ:
            if time.monotonic() < self.not_before:
                return
            with self.lock:
                if self.enabled:
                    self._start(int(fs), center_hz)
            self._emit_state()
        for c in self.chans:
            c.feed(raw)                      # the same array for all: it is only read

    # ---------- rtl_433 processes ----------

    def _offsets(self, fs, center_hz):
        """Channels (offset, rate, autolevel) for this dongle centre and rate."""
        whole = ((0, fs, False),)             # cannot be cut into channels: rtl_433 gets the whole band, as before
        near = min(CHANNELS, key=lambda f: abs(f - center_hz))
        specs = CHANNELS[near] if abs(near - center_hz) < 1e6 else ((0, CH_RATE, False),)
        specs = tuple(c for c in specs if fs % c[1] == 0 and fs > c[1] and abs(c[0]) + c[1] / 2 <= fs / 2)
        return specs or whole

    def _start(self, fs, center_hz):
        self._stop()
        self.fs, self.start_hz = fs, center_hz
        self.not_before = time.monotonic() + RESTART_WAIT_S
        if not os.path.exists(EXE):
            self.error = f"{EXE} is missing"
            return
        chans = []
        try:
            for off, rate, autolevel in self._offsets(fs, center_hz):
                c = Channel(self, fs, center_hz, off, self.raw, rate, autolevel)
                chans.append(c)
                c.start()
        except (OSError, ImportError, ValueError) as e:
            for c in chans:
                c.stop()
            self.error = f"cannot start rtl_433: {e}"
            return
        self.chans = chans
        self.error = None

    def _stop(self):
        chans, self.chans = self.chans, []
        for c in chans:
            c.stop()

    def _ended(self, c, p):
        """rtl_433 of a channel ended by itself: all channels start again with the next samples."""
        with self.lock:
            if c not in self.chans or c.proc is not p or not self.enabled:
                return
            last = next((x for x in reversed(c.log) if x), "")
            self.error = f"rtl_433 ended (code {p.returncode}){': ' + last if last else ''}"
            self._stop()                     # the next samples start it again, after RESTART_WAIT_S
        self._emit_state()

    # ---------- messages ----------

    def _handle(self, j, ch):
        now = time.time()
        # rtl_433 knows the frequency its channel was started with; the dongle may have moved a little since
        shift = self.center_hz - self.start_hz
        mhz = j.get("freq") if j.get("freq") is not None else j.get("freq1")
        freq_hz = round(float(mhz) * 1e6 + shift) if isinstance(mhz, (int, float)) else round(ch.start_hz + shift)
        model = _clean(j["model"])
        dev_id = "" if j.get("id") is None else _clean(j["id"])
        channel = "" if j.get("channel") is None else _clean(j["channel"])
        text = message_text(j)
        fields = message_fields(j)
        pkt = [mhz, j.get("rssi"), j.get("snr")]     # equal for every decoder that read the same packet
        meter = model.startswith("Wireless-MBus")
        window = METER_MERGE_S if meter else REPEAT_S
        names = self.aliases.get(model, {model})
        with self.lock:
            m = None
            for row in reversed(self.history):        # the latest activity last
                if now - row["last"] > max(window, SAME_PACKET_S):
                    continue
                if now - row["last"] < SAME_PACKET_S and pkt == row["pkt"] and None not in pkt and not meter \
                        and row.get("chan") == ch.start_hz and row["dev_id"] == dev_id \
                        and not any(x.startswith("Wireless-MBus") for x in row["models"]):
                    if model in row["models"]:
                        m = dict(row, again=True)         # the same packet again: nothing new
                    else:
                        row["models"].append(model)       # another decoder of rtl_433 read the same packet: one row
                        row["model"] = " / ".join(row["models"])
                        group = set(row["models"]).union(*(self.aliases.get(x, ()) for x in row["models"]))
                        for x in group:
                            self.aliases[x] = group           # later packets of either name join the same row
                        m = dict(row, again=True)
                    break
                if names.intersection(row["models"]) and (row["dev_id"], row["channel"]) == (dev_id, channel) \
                        and (meter or row["text"] == text):
                    row["n"] += 1                         # the device repeats its message (maybe with another in between)
                    row["last"] = now
                    row["pkt"] = pkt
                    row["rssi"], row["snr"] = j.get("rssi"), j.get("snr")
                    if meter:                             # a meter: one row per meter, its latest message
                        row["text"], row["freq_hz"], row["fields"] = text, freq_hz, fields
                    self.history.remove(row)              # the newest activity last (the page moves it to the top)
                    self.history.append(row)
                    m = dict(row)
                    break
            if m is None:
                m = {"id": self.next_id, "time": round(now, 1), "last": now, "n": 1, "freq_hz": freq_hz, "model": model,
                     "models": [model], "pkt": pkt, "chan": ch.start_hz,
                     "dev_id": dev_id, "channel": channel, "text": text, "fields": fields, "mod": _clean(j.get("mod", "")),
                     "rssi": j.get("rssi"), "snr": j.get("snr"), "protocol": j.get("protocol"), "mic": _clean(j.get("mic", ""))}
                self.next_id += 1
                self.history.append(m)
                m = dict(m)
            dev = None
            if not m.get("again"):
                self.count += 1
                self._count_rate(now)
                dev = self._device(model, m, fields, now)
                m["dev"] = dev["key"]
                for row in self.history:              # the row keeps the key (a later "again" copy has it too)
                    if row["id"] == m["id"]:
                        row["dev"] = dev["key"]
                        break
        self.on_event("ism", m)
        if dev:
            self.on_event("ismdev", dev)
            self._save_known(now)
        self._emit_state()

    def _count_rate(self, now):
        minute = int(now // 60)
        if self.rate and self.rate[-1][0] == minute:
            self.rate[-1][1] += 1
        else:
            self.rate.append([minute, 1])

    def _handle_raw(self, b, ch):
        """A package of pulses no decoder read (pulse analyzer of rtl_433)."""
        now = time.time()
        pulses, width = int(b["count"][0]), float(b["count"][1])
        rssi, snr = (float(b["level"][0]), float(b["level"][1])) if "level" in b else (None, None)
        foff = float(b["foff"][0]) * 1e3 if "foff" in b else 0.0
        guess = _clean(b["guess"][0]) if "guess" in b else "?"
        parts = [guess, f"{pulses} pulses", f"{width:g} ms"]
        codes = ch.codes.get(b.get("attempt", -1), "")
        if codes:
            parts.append(_clean(codes if len(codes) <= RAW_CODES_MAX else codes[:RAW_CODES_MAX] + "…"))
        freq_hz = round(ch.start_hz + self.center_hz - self.start_hz + foff)
        view = b["view"][0] if "view" in b else ""
        flex = _clean(b["flex"][0]) if "flex" in b else ""
        mod = b.get("mod", "")
        key = raw_match(freq_hz, mod, guess, pulses)       # a marked signal (e.g. a car key): a device with its name
        dev = None
        with self.lock:
            self.raw_count += 1
            m = None
            for row in reversed(self.history):
                if row.get("raw") and now - row["last"] < RAW_MERGE_S and row["guess"] == guess \
                        and abs(row["freq_hz"] - freq_hz) <= RAW_MERGE_HZ and row.get("dev") == key:
                    row["n"] += 1            # an unknown transmitter (or interference) that keeps sending: one row
                    row["last"] = now
                    self.history.remove(row)
                    self.history.append(row)
                    if codes or not row["has_codes"]:     # show the latest package, but keep one with bits
                        row.update(text=" · ".join(parts), has_codes=bool(codes), rssi=rssi, snr=snr, pulses=pulses,
                                   view=view or row["view"], flex=flex or row["flex"])
                    m = dict(row)
                    break
            if m is None:
                m = {"id": self.next_id, "time": round(now, 1), "last": now, "n": 1, "freq_hz": freq_hz,
                     "model": "RAW", "models": ["RAW"], "guess": guess, "has_codes": bool(codes), "pkt": None,
                     "dev_id": key.split("|")[1] if key else "", "channel": "", "text": " · ".join(parts), "mod": mod,
                     "rssi": rssi, "snr": snr, "protocol": None, "mic": "", "raw": True, "view": view, "flex": flex,
                     "pulses": pulses}
                if key:
                    m["dev"] = key
                self.next_id += 1
                self.history.append(m)
                m = dict(m)
            if key:
                dev = self._device("RAW", dict(m, freq_hz=freq_hz, rssi=rssi, snr=snr), {}, now)
        self.on_event("ism", m)
        if dev:
            self.on_event("ismdev", dev)
            self._save_known(now)
        self._emit_state()

    def mark_raw(self, row_id, name):
        """Marks the signal of a RAW row with a name: this row and its later packages are a device (DEVICES, TIMELINE).
        Returns all names, or None when the row is gone."""
        with self.lock:
            row = next((r for r in self.history if r["id"] == row_id and r.get("raw")), None)
            if row is None:
                return None
            row = dict(row)
        key = row.get("dev")
        if not key:
            m = re.search(r"m=(\w+)", row.get("flex") or "")
            kind = m.group(1) if m else (row["mod"] or "RAW")
            key = self._dev_key("RAW", f"{row['freq_hz'] / 1e6:.3f} {kind}", "")
        p = re.search(r"(\d+) pulses", row.get("text") or "")
        sig = {"f": row["freq_hz"], "mod": row["mod"], "guess": row["guess"],
               "p": row.get("pulses") or (int(p.group(1)) if p else 0)}
        names = set_name(key, name, sig=sig if name.strip() else None)
        if not name.strip():
            return names
        now = time.time()
        with self.lock:
            for r in self.history:
                if r["id"] == row_id:
                    r["dev"], r["dev_id"] = key, key.split("|")[1]
                    row = dict(r)
                    break
            dev = self.devices.get(key)
            dev = self._dev_public(dev) if dev else self._device("RAW", row, {}, now)
        self.on_event("ism", row)
        self.on_event("ismdev", dev)
        self._save_known(now)
        return names

    def _emit_state(self):
        self.on_state(self.info())

"""WSPR decoder: the USB passband above the tuned (dial) frequency, 2-minute cycles timed by the PC clock, decoded
by wsprd.exe (lib\\wspr\\, from WSJT-X 2.7.0, GPL v3, built by installer/build_wspr.sh).

A WSPR transmission takes 110.6 s and starts one second after an even UTC minute; its symbols are interleaved and
coded over the whole message, so it can only be decoded at the end. We record 114 s of 12 kHz audio from each even
minute (like WSJT-X), write it as a WAV file into data\\wspr and let wsprd decode it there; the decodes (call,
locator, power, SNR, drift) go to the table, the station list (for the PROPAGATION tab) and the daily log.
A cycle during which the VFO was retuned is skipped (it would mix two bands).
"""
import collections
import os
import re
import subprocess
import threading
import time
import wave

import numpy as np

from location import locator_to_latlon
from paths import BASE, data
from sdr import lowpass

EXE = os.path.join(BASE, "lib", "wspr", "wsprd.exe")
WORK = data("wspr")                # WAV of the cycle being decoded, wsprd's hash table of the <hashed> calls
RATE = 12000
CYCLE_S = 120
REC_S = 114                        # what wsprd reads of a WAV file
MAX_FREQ = 3100.0
DECODE_TIMEOUT_S = 110          # the next cycle is ready 120 s later
# the "normal" decoding depth of WSJT-X: 3 passes with subtraction, block detection, OSD, at most 500 Fano cycles per bit
# (without -C, wsprd allows 10 000 and a busy band can take minutes)
DEPTH = ["-C", "500", "-o", "4"]
STATION_KEEP_S = 24 * 3600
STATION_MAX = 5000
# dial frequencies (USB) of the WSPR sub-bands: the signals are 1400–1600 Hz above them
WSPR_FREQS = (1836600, 3568600, 5287200, 7038600, 10138700, 14095600, 18104600, 21094600, 24924600, 28124600, 50293000)

_LINE = re.compile(r"^(\d{4})\s+(-?\d+)\s+(-?\d+\.\d+)\s+(\d+\.\d+)\s+(-?\d+)\s+(.+?)\s*$")
_GRID = re.compile(r"^[A-R]{2}\d{2}([A-X]{2})?$")
_CALL = re.compile(r"^(?=.*\d)(?=.*[A-Z])[A-Z0-9/]{3,12}$")


def parse_line(line, ts=None):
    """One line of wsprd's output -> a decode, or None.
    "0001 -24 -0.0  10.140200  0  DL1ABC JO62 37": UTC hhmm, SNR dB (2.5 kHz), DT s, MHz, drift Hz/min, message;
    the message is "CALL GRID dBm", "PFX/CALL dBm" (no locator) or "<CALL> GRID6 dBm" (6-character locator)."""
    m = _LINE.match(line.strip())
    if not m:
        return None
    hhmm, snr, dt, mhz, drift, msg = m.groups()
    d = {"time": f"{hhmm[:2]}:{hhmm[2:]}", "snr": int(snr), "dt": float(dt), "freq_hz": round(float(mhz) * 1e6),
         "drift": int(drift), "msg": " ".join(msg.split()), "ts": ts or time.time()}
    w = d["msg"].split()
    if w and w[-1].lstrip("-").isdigit():
        d["dbm"] = int(w[-1])
        w = w[:-1]
    call = (w[0] if w else "").strip("<>")
    if _CALL.match(call):
        d["call"] = call
        if len(w) >= 2 and _GRID.match(w[1].upper()):
            d["grid"] = w[1][:4].upper() + w[1][4:].lower()
            try:
                d["lat"], d["lon"] = locator_to_latlon(w[1])
            except ValueError:
                d.pop("grid")
    return d


class WsprDecoder:
    """Turns decoding on/off, records the 2-minute cycles from the receiver's baseband and runs wsprd on them."""

    def __init__(self, on_decode, on_cycle=None):
        self.on_decode = on_decode
        self.on_cycle = on_cycle or (lambda info: None)
        self.decodes = collections.deque(maxlen=400)
        self.stations = {}      # call -> newest spot of the station (for the PROPAGATION tab), kept 24 h
        self.enabled = False
        self.error = None
        self.info = ""          # what the decoder does now (recording / decoding / the last cycle)
        self.dial_hz = 0.0
        self.lock = threading.Lock()
        self._fs = None
        self._rec = None        # {"t0": start of the cycle (epoch), "dial": Hz, "parts": [...], "n": samples}
        self._busy = False

    # ---------- on / off ----------

    def set_enabled(self, on):
        if on and not os.path.isfile(EXE):
            self.error = "wsprd.exe is not in lib\\wspr (built by installer/build_wspr.sh)"
            on = False
        elif on:
            self.error = None
        with self.lock:
            self.enabled = bool(on)
            self._rec = None
            self.info = "waiting for an even minute…" if on else ""

    # ---------- audio: USB 0–3.1 kHz at 12 kHz (as for FT8) ----------

    def _setup(self, fs):
        self._fs = fs
        taps = 255
        n = np.arange(taps) - (taps - 1) / 2
        mid = MAX_FREQ / 2 + 50
        self._h = (lowpass(mid, fs, taps) * np.exp(2j * np.pi * mid / fs * n)).astype(np.complex64)
        self._hist = np.zeros(taps - 1, np.complex64)
        self._t = 0.0
        self._last = 0.0

    def feed(self, base, fs, dial_hz):
        """base: complex baseband (tuned frequency = 0 Hz) at sample rate fs."""
        if not self.enabled:
            return
        if fs != self._fs:
            self._setup(fs)
            self._rec = None
        self.dial_hz = dial_hz
        buf = np.concatenate((self._hist, base))
        self._hist = buf[-(len(self._h) - 1):]
        usb = np.convolve(buf, self._h, mode="valid").real
        y = np.concatenate(([self._last], usb))
        step = fs / RATE
        pos = np.arange(self._t, len(y) - 1, step)
        self._last = y[-1]
        if not pos.size:
            self._t -= len(y) - 1
            return
        self._t = pos[-1] + step - (len(y) - 1)
        self._samples(np.interp(pos, np.arange(len(y)), y).astype(np.float32), dial_hz)

    def _samples(self, x, dial_hz):
        now = time.time()
        rec = self._rec
        if rec is not None and rec["dial"] != dial_hz:           # retuned: this cycle would mix two frequencies
            self._rec = rec = None
            self._set_info("retuned – the cycle is skipped, waiting for the next even minute")
        if rec is None:
            t_first = now - len(x) / RATE
            start = float(np.ceil(t_first / CYCLE_S) * CYCLE_S)  # the next even minute
            if start > now:
                return
            i = int(round((start - t_first) * RATE))
            rec = self._rec = {"t0": start, "dial": dial_hz, "parts": [], "n": 0}
            x = x[i:]
            self._set_info(f"recording the cycle {time.strftime('%H:%M', time.gmtime(start))}")
        rec["parts"].append(x)
        rec["n"] += len(x)
        if rec["n"] >= REC_S * RATE:
            self._rec = None
            audio = np.concatenate(rec["parts"])[:REC_S * RATE]
            if self._busy:            # the previous cycle still decodes (slow PC): skip this one
                self._set_info("the previous cycle is still decoding – a cycle skipped")
                return
            self._busy = True
            threading.Thread(target=self._decode, args=(audio, rec["t0"], rec["dial"]), name="wspr", daemon=True).start()

    def _set_info(self, text, busy=None):
        self.info = text
        self.on_cycle(dict(self.progress(busy), info=text))

    def progress(self, busy=None):
        """For the progress bar of the page: the start of the cycle being recorded (epoch) or None, its length, and
        whether wsprd decodes the previous cycle now."""
        rec = self._rec
        return {"rec_t0": rec["t0"] if rec else None, "rec_s": REC_S, "busy": self._busy if busy is None else busy}

    # ---------- decoding ----------

    def _decode(self, audio, t0, dial):
        cyc = time.strftime("%H:%M", time.gmtime(t0))
        try:
            self._set_info(f"decoding the cycle {cyc}…")
            os.makedirs(WORK, exist_ok=True)
            name = os.path.join(WORK, time.strftime("%y%m%d_%H%M", time.gmtime(t0)) + ".wav")
            peak = float(np.percentile(np.abs(audio), 99.9)) or 1.0
            pcm = np.clip(audio * (8000.0 / peak), -32767, 32767).astype("<i2")
            with wave.open(name, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(pcm.tobytes())
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
            try:
                r = subprocess.run([EXE] + DEPTH + ["-a", WORK, "-f", f"{dial / 1e6:.6f}", os.path.basename(name)], cwd=WORK,
                                   capture_output=True, text=True, timeout=DECODE_TIMEOUT_S, creationflags=flags,
                                   # not our stdin: in a VFO process it is the pipe from the launcher that another thread
                                   # reads; the inherited handle shares that blocked synchronous read and wsprd hung at start
                                   stdin=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                # keep the audio of the cycle that took too long (only the last one), to look at it later
                try:
                    os.replace(name, os.path.join(WORK, "timeout_last.wav"))
                except OSError:
                    pass
                raise RuntimeError(f"wsprd did not finish in {DECODE_TIMEOUT_S} s (audio kept in data/wspr/timeout_last.wav)")
            for f in os.listdir(WORK):        # this one, and any left behind by a stopped or crashed run
                if f.endswith(".wav") and f != "timeout_last.wav" and f[:6].isdigit():
                    try:
                        os.remove(os.path.join(WORK, f))
                    except OSError:
                        pass
            ts = t0 + CYCLE_S
            n = 0
            for line in r.stdout.splitlines():
                d = parse_line(line, ts)
                if d is None:
                    continue
                d["df"] = round(d["freq_hz"] - dial)
                n += 1
                if "call" in d:
                    self._station(d)
                self.decodes.append(d)
                self.on_decode(d)
            self.error = None
            self._set_info(f"cycle {cyc} · {n} spot{'s' if n != 1 else ''}", busy=False)
        except Exception as e:  # noqa: BLE001 - a failed cycle must not stop the decoder
            self.error = str(e)[:200]
            self._set_info(f"cycle {cyc} failed: {self.error}", busy=False)
        finally:
            self._busy = False

    # ---------- stations ----------

    def _station(self, d):
        with self.lock:
            s = self.stations.get(d["call"])
            if s is None:
                s = self.stations[d["call"]] = {"call": d["call"], "first": d["ts"], "n": 0}
            s.update(ts=d["ts"], snr=d["snr"], freq_hz=d["freq_hz"], msg=d["msg"], n=s["n"] + 1, drift=d["drift"],
                     dbm=d.get("dbm"), mode="WSPR")
            if "grid" in d:
                s.update(grid=d["grid"], lat=d["lat"], lon=d["lon"])
            if len(self.stations) > STATION_MAX:
                self._prune(time.time())

    def _prune(self, now):
        for k in [k for k, s in self.stations.items() if now - s["ts"] > STATION_KEEP_S]:
            del self.stations[k]
        while len(self.stations) > STATION_MAX:
            del self.stations[min(self.stations, key=lambda k: self.stations[k]["ts"])]

    def station_list(self):
        with self.lock:
            self._prune(time.time())
            return [dict(s) for s in self.stations.values()]

    def clear_stations(self):
        with self.lock:
            self.stations.clear()

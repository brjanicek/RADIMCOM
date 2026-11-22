"""Q65 / JT65 decoder: the USB passband above the tuned (dial) frequency in T/R periods timed by the PC clock, decoded
by jt9.exe (lib\\jt9\\, the slow-mode decoder of WSJT-X 2.7.0, GPL v3, built by installer/build_jt9.sh).

JT65 (60 s periods, submodes A/B/C) is the older weak-signal mode of HF and EME; Q65 (15, 30, 60, 120 or 300 s periods,
submodes A–E = tone spacing ×1 … ×16) is its successor for ionospheric / tropo scatter, rain scatter and EME on 6 m and
above. Both carry the messages of FT8 (calls, locator, report) and can only be decoded at the end of the period.
We record the whole period of 12 kHz audio from its UTC start, write it as a WAV file into data\\q65 and let jt9 decode it
there; the decodes go to the table and the daily log. A period during which the VFO was retuned is skipped.
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

EXE = os.path.join(BASE, "lib", "jt9", "jt9.exe")
WORK = data("q65")                 # WAV of the period being decoded and jt9's own files (decoded.txt, wisdom ...)
RATE = 12000
MAX_FREQ = 3100.0
LOW_HZ, HIGH_HZ = 200, 3000        # the audio range jt9 searches
DEPTH = 3                          # jt9 -d: 3 = deep (as "Deep" in WSJT-X)
START_TOL_S = 1.0                  # a period that started up to this long before the first samples is still recorded
MODES = {"JT65": {"flag": "-6", "periods": (60,), "subs": "ABC"},
         "Q65": {"flag": "-3", "periods": (15, 30, 60, 120, 300), "subs": "ABCDE"}}
# dial frequencies (USB) from the default frequency list of WSJT-X 2.7.0 (models/FrequencyList.cpp, IARU region 1 and
# ALL, up to 1.3 GHz); the signals are about 1000–2000 Hz above them. period / sub = what the band key sets, after the
# WSJT-X user guide (vhf-features.adoc): Q65-30A for 6 m ionoscatter; EME Q65-60A on 50 / 144 MHz, 60B on 432 MHz,
# 60C on 1296 MHz; JT65A on HF and 50 MHz, JT65B on 144 / 432 MHz, JT65C on 1296 MHz.
Q65_FREQS = (
    [{"f": f, "mode": "JT65", "period": 60, "sub": "A"} for f in
     (1838000, 3570000, 7076000, 10138000, 14076000, 18102000, 21076000, 24917000, 28076000, 50310000, 70102000)]
    + [{"f": 144120000, "mode": "JT65", "period": 60, "sub": "B"},
       {"f": 432065000, "mode": "JT65", "period": 60, "sub": "B"},
       {"f": 1296065000, "mode": "JT65", "period": 60, "sub": "C"}]
    + [{"f": 50211000, "mode": "Q65", "period": 60, "sub": "A"},
       {"f": 50275000, "mode": "Q65", "period": 30, "sub": "A"},
       {"f": 144116000, "mode": "Q65", "period": 60, "sub": "A"},
       {"f": 432065000, "mode": "Q65", "period": 60, "sub": "B"},
       {"f": 1296065000, "mode": "Q65", "period": 60, "sub": "C"}])

# "1230 -24  0.1  800 :  CQ K1ABC FN42       q0" (Q65), "0001 -20  0.0  600 #  K1ABC W9XYZ EN37" (JT65);
# UTC hhmm or hhmmss, SNR dB (2.5 kHz), DT s, audio Hz, sync mark, message, flags (q<AP type><periods averaged>, a, d, f)
_LINE = re.compile(r"^(\d{4}|\d{6}|\*+)\s+(-?\d+)\s+(-?\d+\.\d)\s+(-?\d+)\s+(:|#\*?|##)\s+(.+?)\s*$")
_FLAGS = re.compile(r"^(q\d{1,2}|a\d{1,2}|d[\d*][\d*]?|f\d?)$")
_GRID = re.compile(r"^[A-R]{2}\d{2}([A-X]{2})?$")
_CALL = re.compile(r"^(?=.*\d)(?=.*[A-Z])[A-Z0-9/]{3,12}$")


def mode_label(mode, period, sub):
    return f"JT65{sub}" if mode == "JT65" else f"Q65-{period}{sub}"


def sender(msg):
    """The calling station and its locator from a standard message: "CQ [DX|NA|123] CALL GRID", "CALL1 CALL2 GRID",
    "CALL1 CALL2 -15", "CALL1 CALL2 RR73" -> (call or None, grid or None)."""
    w = [x.strip("<>") for x in msg.upper().split()]
    if w and w[0] in ("CQ", "QRZ", "DE"):
        w = w[1:]
        if len(w) >= 2 and not _CALL.match(w[0]):       # CQ DX / CQ NA / CQ 123 ...
            w = w[1:]
        call, rest = (w[0] if w else None), w[1:]
    else:
        call, rest = (w[1] if len(w) >= 2 else None), w[2:]
    if not call or not _CALL.match(call):
        return None, None
    grid = rest[0] if rest and _GRID.match(rest[0]) and rest[0] != "RR73" else None
    return call, grid


def parse_line(line):
    """One line of jt9's output -> {"snr", "dt", "df", "msg", "flags"} or None (a sync line without a message, the end
    line <DecodeFinished>)."""
    m = _LINE.match(line.rstrip())
    if not m:
        return None
    _, snr, dt, df, _sync, rest = m.groups()
    w = rest.split()
    flags = ""
    if len(w) > 1 and _FLAGS.match(w[-1]):
        flags = w.pop()
    msg = " ".join(w).rstrip("?").strip()
    if not msg:
        return None
    return {"snr": int(snr), "dt": float(dt), "df": int(df), "msg": msg, "flags": flags}


class Q65Decoder:
    """Turns decoding on/off, records the T/R periods from the receiver's baseband and runs jt9 on them."""

    def __init__(self, on_decode, on_cycle=None):
        self.on_decode = on_decode
        self.on_cycle = on_cycle or (lambda info: None)
        self.decodes = collections.deque(maxlen=400)
        self.enabled = False
        self.error = None
        self.info = ""
        self.mode, self.period, self.sub = "Q65", 30, "A"
        self.dial_hz = 0.0
        self.lock = threading.Lock()
        self._fs = None
        self._rec = None        # {"t0": start of the period (epoch), "dial": Hz, "key": settings, "parts": [...], "n": samples}
        self._busy = False

    # ---------- settings ----------

    def configure(self, cfg):
        """At start: the settings and the switch saved in config.json."""
        self.set_mode(cfg.get("q65_mode", self.mode), cfg.get("q65_period", self.period), cfg.get("q65_sub", self.sub))
        self.set_enabled(cfg.get("q65", False))

    def set_mode(self, mode=None, period=None, sub=None):
        """Mode JT65 / Q65, period s, submode letter; values that do not fit the mode fall back to its first one."""
        mode = mode if mode in MODES else self.mode
        m = MODES[mode]
        period = int(period) if period is not None and str(period).isdigit() else self.period
        if period not in m["periods"]:
            period = 60 if mode == "JT65" else 30
        sub = str(sub or self.sub).upper()
        if sub not in m["subs"]:
            sub = "A"
        with self.lock:
            if (mode, period, sub) != (self.mode, self.period, self.sub):
                self.mode, self.period, self.sub = mode, period, sub
                if self._rec is not None:
                    self._rec = None
                    self.info = "mode changed – waiting for the next period…"

    def set_enabled(self, on):
        if on and not os.path.isfile(EXE):
            self.error = "jt9.exe is not in lib\\jt9 (built by installer/build_jt9.sh)"
            on = False
        elif on:
            self.error = None
        with self.lock:
            self.enabled = bool(on)
            self._rec = None
            self.info = "waiting for the next period…" if on else ""

    def apply(self, body, cfg):
        """The keys of POST /api/set for this decoder; True if something was changed (the caller saves config)."""
        changed = False
        if any(k in body for k in ("q65_mode", "q65_period", "q65_sub")):
            self.set_mode(body.get("q65_mode"), body.get("q65_period"), body.get("q65_sub"))
            cfg.update(q65_mode=self.mode, q65_period=self.period, q65_sub=self.sub)
            changed = True
        if "q65" in body:
            self.set_enabled(bool(body["q65"]))
            cfg["q65"] = self.enabled
            changed = True
        return changed

    def status(self):
        """The fields of this decoder in the VFO state."""
        return {"q65": self.enabled, "q65_error": self.error, "q65_info": self.info, "q65_mode": self.mode,
                "q65_period": self.period, "q65_sub": self.sub, "q65_label": mode_label(self.mode, self.period, self.sub),
                "q65_prog": self.progress()}

    # ---------- audio: USB 0–3.1 kHz at 12 kHz (as for WSPR) ----------

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
        self._samples(np.interp(pos, np.arange(len(y)), y).astype(np.float32), dial_hz, time.time())

    def _samples(self, x, dial_hz, now):
        key = (self.mode, self.period, self.sub)
        rec = self._rec
        if rec is not None and (rec["dial"] != dial_hz or rec["key"] != key):
            self._rec = rec = None
            self._set_info("retuned – the period is skipped, waiting for the next one")
        if rec is None:
            # the period this audio belongs to: its start may lie up to START_TOL_S before the first sample (the gap is
            # filled with zeros, jt9 finds the signal by its DT); a later start waits for the next period
            period = self.period
            t_first = now - len(x) / RATE
            start = float(np.ceil((t_first - START_TOL_S) / period) * period)
            if start > now:
                return
            i = int(round((start - t_first) * RATE))
            x = np.concatenate((np.zeros(-i, np.float32), x)) if i < 0 else x[i:]
            rec = self._rec = {"t0": start, "dial": dial_hz, "key": key, "parts": [], "n": 0}
            self._set_info(f"receiving the period {self._hms(start)}")
        rec["parts"].append(x)
        rec["n"] += len(x)
        need = rec["key"][1] * RATE
        if rec["n"] >= need:
            self._rec = None
            audio = np.concatenate(rec["parts"])
            rest, audio = audio[need:], audio[:need]
            if self._busy:            # the previous period still decodes (slow PC): skip this one
                self._set_info("the previous period is still decoding – a period skipped")
            else:
                self._busy = True
                threading.Thread(target=self._decode, args=(audio, rec["t0"], rec["dial"], rec["key"]), name="q65",
                                 daemon=True).start()
            if len(rest):             # the start of the next period (aligned again to the PC clock)
                self._samples(rest, dial_hz, now)

    def _hms(self, t):
        return time.strftime("%H:%M:%S" if self.period < 60 else "%H:%M", time.gmtime(t))

    def _set_info(self, text, busy=None):
        self.info = text
        self.on_cycle(dict(self.progress(busy), info=text))

    def progress(self, busy=None):
        """For the progress bar of the page: the start of the period being recorded (epoch) or None, its length, and
        whether jt9 decodes the previous period now."""
        rec = self._rec
        return {"rec_t0": rec["t0"] if rec else None, "rec_s": rec["key"][1] if rec else self.period,
                "busy": self._busy if busy is None else busy}

    # ---------- decoding ----------

    def _decode(self, audio, t0, dial, key):
        mode, period, sub = key
        label = mode_label(mode, period, sub)
        cyc = time.strftime("%H:%M:%S" if period < 60 else "%H:%M", time.gmtime(t0))
        name = None
        try:
            self._set_info(f"decoding the period {cyc}…")
            os.makedirs(WORK, exist_ok=True)
            # jt9 takes the UTC of the period from the file name: _hhmm (60 s and longer) or _hhmmss
            name = os.path.join(WORK, time.strftime("%y%m%d_%H%M%S" if period < 60 else "%y%m%d_%H%M", time.gmtime(t0))
                                + ".wav")
            peak = float(np.percentile(np.abs(audio), 99.9)) or 1.0
            pcm = np.clip(audio * (8000.0 / peak), -32767, 32767).astype("<i2")
            with wave.open(name, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(pcm.tobytes())
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
            args = [EXE, MODES[mode]["flag"], "-b", sub, "-p", str(period), "-d", str(DEPTH), "-L", str(LOW_HZ),
                    "-H", str(HIGH_HZ), "-a", WORK, "-t", WORK, os.path.basename(name)]
            timeout = max(30, 2 * period)
            try:
                r = subprocess.run(args, cwd=WORK, capture_output=True, text=True, timeout=timeout, creationflags=flags,
                                   stdin=subprocess.DEVNULL)     # not our stdin (see wspr.py)
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"jt9 did not finish in {timeout} s")
            ts = t0 + period
            n = 0
            for line in r.stdout.splitlines():
                d = parse_line(line)
                if d is None:
                    continue
                d.update(time=cyc, ts=ts, mode=label, freq_hz=round(dial + d["df"]))
                call, grid = sender(d["msg"])
                if call:
                    d["call"] = call
                if grid:
                    d["grid"] = grid
                    try:
                        d["lat"], d["lon"] = locator_to_latlon(grid)
                    except ValueError:
                        pass
                n += 1
                self.decodes.append(d)
                self.on_decode(d)
            if r.returncode != 0 and not n:
                err = (r.stderr or r.stdout).strip().splitlines()
                raise RuntimeError(f"jt9 exit code {r.returncode}" + (f": {err[0][:120]}" if err else ""))
            self.error = None
            self._set_info(f"{label} · period {cyc} · {n} decode{'s' if n != 1 else ''}", busy=False)
        except Exception as e:  # noqa: BLE001 - a failed period must not stop the decoder
            self.error = str(e)[:200]
            self._set_info(f"period {cyc} failed: {self.error}", busy=False)
        finally:
            self._busy = False
            if name:
                try:
                    os.remove(name)
                except OSError:
                    pass

    def clear(self):
        self.decodes.clear()


def register(app, decoder):
    """GET /api/q65: the decodes and the band keys; DELETE clears the decodes."""
    from flask import jsonify, request

    @app.route("/api/q65", methods=["GET", "DELETE"])
    def api_q65():
        if request.method == "DELETE":
            decoder.clear()
            return jsonify(ok=True)
        return jsonify(decodes=list(decoder.decodes), freqs=Q65_FREQS, modes={k: {"periods": v["periods"], "subs": v["subs"]}
                                                                              for k, v in MODES.items()})

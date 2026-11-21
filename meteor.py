"""Meteor counter on the GRAVES space radar (143.050 MHz, continuous carrier, south of Dijon, France).

From Central Europe GRAVES is below the horizon; what is heard is its carrier reflected by the ionised trails of meteors:
short pings (underdense, < 1 s) and longer echoes (overdense, seconds), a few tens of Hz off the carrier (Doppler).

Detection on the complex baseband of the VFO (dial = 0 Hz), only around the carrier (GRAVES_HZ - dial):
  - spectrum of N samples (N = power of two near fs/8, about 4-8 Hz per bin) every N/4 samples (about 30 ms);
  - each frame is divided by its median over the band, so a gain step of the receiver / AGC+ or broadband impulse noise
    lifts all bins together and changes nothing;
  - the power of each bin is smoothed over 4 frames and compared with the floor of that bin (a slow average: a steady
    carrier, the direct GRAVES signal on a tropo opening or a birdie are learned into the floor and do not trigger);
  - an echo starts when the strongest bin is THRESHOLD_DB above its floor, lasts while it stays 3 dB lower than that,
    and ends after GAP_S below; frames where more than WIDE_FRAC of the band is up at once (broadband) are left out;
  - echoes of aircraft are long and their Doppler drifts: longer than PLANE_S, or longer than 2 s with a drift over
    PLANE_DRIFT Hz/s, or at the Doppler of an aircraft echo seen a little earlier, are aircraft and are not counted.

Counts per UTC hour (underdense, overdense, seconds monitored) are kept in data/meteors_<VFO>.json for LONG_DAYS.
"""
import collections
import json
import math
import os
import threading
import time

import numpy as np

from paths import data

GRAVES_HZ = 143050000.0
GRAVES_LAT, GRAVES_LON = 47.348, 5.515    # the transmitter near Broyes-lès-Pesmes (Haute-Saône)
METEOR_KM = 100.0                       # height of the meteor trails
EARTH_KM = 6371.0
DIAL_USB_HZ = GRAVES_HZ - 1000.0        # USB dial: the carrier is heard as a 1 kHz tone
BAND_HZ = 500.0                         # watched around the carrier (meteor Doppler is mostly within ±150 Hz)
THRESHOLD_DB = 10.0                     # noise alone: the strongest of ~130 bins is ~5.5 dB, 99.9 % under 8.5 dB
HYST_DB = 3.0                           # an echo lasts while its own bins (±TRACK_BINS) stay this much under
TRACK_BINS = 2
GAP_S = 0.3                             # shorter gaps join one echo
WIDE_FRAC = 0.3
SMOOTH = 4                              # frames averaged per bin
LEARN_S = 4.0                           # the first seconds only learn the floor (a plain average)
TAU_S = 10.0                            # floor time constant (quiet bin)
TAU_HOT_S = 120.0                       # floor time constant while the bin is up (a carrier is learned in ~minutes)
UNDER_S = 1.0                           # shorter = underdense
PLANE_S = 20.0
PLANE_DRIFT = 5.0                       # Hz/s
PLANE_MEMORY_S = 30.0
PLANE_DOPPLER_HZ = 15.0
LONG_DAYS = 400
SCOPE_S = 120
SCOPE_RATE = 4                          # points per second
SAVE_S = 60.0


def graves_path(lat, lon):
    """Where to point the antenna from (lat, lon): the azimuth of GRAVES, the distance and the elevation of the meteor
    zone (~100 km high) over the middle of the path, where most forward-scatter echoes come from."""
    p1, p2, dl = math.radians(lat), math.radians(GRAVES_LAT), math.radians(GRAVES_LON - lon)
    az = math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                 math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) % 360
    c = math.acos(max(-1.0, min(1.0, math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl))))
    km = EARTH_KM * c
    half = c / 2                        # elevation of a point METEOR_KM high over the middle of the path
    el = math.degrees(math.atan2(math.cos(half) - EARTH_KM / (EARTH_KM + METEOR_KM), math.sin(half)))
    return {"az": round(az, 1), "km": round(km), "el": round(max(0.0, el), 1)}


def hour_key(t):
    return time.strftime("%Y-%m-%dT%H", time.gmtime(t))


class MeteorCounter:
    def __init__(self, tag="", on_echo=None, path=None):
        self.on_echo = on_echo
        self.path = path or data(f"meteors_{tag or 'main'}.json")
        self.enabled = False
        self.error = ""
        self.threshold_db = THRESHOLD_DB
        self.lock = threading.Lock()
        self.events = collections.deque(maxlen=500)
        self.hours = {}                 # "YYYY-MM-DDTHH" (UTC) -> [underdense, overdense, seconds monitored]
        self.scope = collections.deque(maxlen=SCOPE_S * SCOPE_RATE)    # (t, max SNR dB)
        self.status = ""
        self.planes = 0
        self._dirty = False
        self._saved = 0.0
        self._fs = None
        self._dial = None
        self._load()

    # ----- settings -----
    def set_enabled(self, on):
        on = bool(on)
        if on and not self.enabled:
            self._fs = None             # a new start: learn the floor again
        if not on and self.enabled:
            self._close_event()
            self.save()
        self.enabled = on

    def set_threshold(self, db):
        self.threshold_db = min(30.0, max(3.0, float(db)))

    # ----- signal -----
    def _setup(self, fs, dial_hz):
        self._fs = fs
        self._dial = dial_hz
        self.n = 1 << int(round(math.log2(max(256.0, fs / 8.0))))
        self.hop = self.n // 4
        self.win = np.hanning(self.n).astype(np.float32)
        self._buf = np.zeros(0, np.complex64)
        self.f_off = GRAVES_HZ - dial_hz
        freqs = np.fft.fftfreq(self.n, 1.0 / fs)
        self.idx = np.nonzero(np.abs(freqs - self.f_off) <= BAND_HZ)[0]
        self.idx = self.idx[np.argsort(freqs[self.idx])]
        self.bin_hz = freqs[self.idx] - self.f_off      # Doppler of each watched bin
        self.dt = self.hop / fs
        self._hist = collections.deque(maxlen=SMOOTH)
        self.floor = None
        self.t_learn = 0.0
        self._ev = None
        self._last_hot = None
        self._scope_t = 0.0
        self._scope_max = -99.0
        if abs(self.f_off) + BAND_HZ > fs / 2 * 0.9:
            self.status = f"GRAVES {GRAVES_HZ / 1e6:.3f} MHz is outside the band of this VFO: tune to {DIAL_USB_HZ / 1e6:.3f} USB"
            self.idx = self.idx[:0]
        else:
            self.status = "learning the noise floor…"

    def feed(self, base, fs, dial_hz, now=None):
        """base: complex baseband (dial = 0 Hz) at fs; now: the time of the end of the block (tests)."""
        if not self.enabled:
            return
        try:
            self._feed(base, fs, dial_hz, time.time() if now is None else now)
        except Exception as e:          # never take the receiver down
            self.error = f"meteor: {e}"

    def _feed(self, base, fs, dial_hz, now):
        if fs != self._fs or dial_hz != self._dial:
            self._close_event()
            self._setup(fs, dial_hz)
        if not len(self.idx):
            return
        buf = np.concatenate((self._buf, np.asarray(base, np.complex64)))
        nfr = (len(buf) - self.n) // self.hop + 1 if len(buf) >= self.n else 0
        for i in range(nfr):
            seg = buf[i * self.hop:i * self.hop + self.n]
            t = now - (len(buf) - i * self.hop - self.n) / fs        # the end of this frame
            self._frame(np.abs(np.fft.fft(seg * self.win)[self.idx]) ** 2, t)
        self._buf = buf[nfr * self.hop:]
        self._count_time(len(base) / fs, now)

    def _frame(self, p, t):
        med = float(np.median(p))
        if med <= 0:
            return
        self._hist.append(p / med)
        s = np.mean(self._hist, axis=0)
        if self.floor is None:
            self.floor = s.copy()
        self.t_learn += self.dt
        learning = self.t_learn < LEARN_S
        ratio = s / np.maximum(self.floor, 1e-12)
        thr = 10 ** (self.threshold_db / 10)
        hot = ratio >= thr
        tau = self.t_learn if learning else np.where(hot, TAU_HOT_S, TAU_S)
        self.floor += (s - self.floor) * (self.dt / tau)
        if learning:
            return
        if self.status.startswith("learning"):
            self.status = "listening"
        k = int(np.argmax(ratio))
        snr = 10 * math.log10(max(ratio[k], 1e-6))
        wide = np.count_nonzero(ratio >= thr / 2) > WIDE_FRAC * len(ratio)
        self._scope(t, -99.0 if wide else snr)
        if wide:
            return
        ev = self._ev
        if ev is None:
            if snr >= self.threshold_db:
                self._ev = {"t0": t, "t1": t, "peak": snr, "dop": float(self.bin_hz[k]), "k": k, "track": [(t, float(self.bin_hz[k]))]}
            return
        a = max(0, ev["k"] - TRACK_BINS)
        j = a + int(np.argmax(ratio[a:ev["k"] + TRACK_BINS + 1]))        # the echo's own bins (its Doppler moves)
        snr_j = 10 * math.log10(max(ratio[j], 1e-6))
        if snr_j >= self.threshold_db - HYST_DB:
            ev["t1"] = t
            ev["k"] = j
            if snr_j >= self.threshold_db:
                ev["track"].append((t, float(self.bin_hz[j])))
            if snr_j > ev["peak"]:
                ev["peak"], ev["dop"] = snr_j, float(self.bin_hz[j])
        elif t - ev["t1"] > GAP_S:
            self._close_event()

    def _scope(self, t, snr):
        self._scope_max = max(self._scope_max, snr)
        if t - self._scope_t >= 1.0 / SCOPE_RATE:
            with self.lock:
                self.scope.append((round(t, 2), round(max(self._scope_max, -20.0), 1)))
            self._scope_t = t
            self._scope_max = -99.0

    def _close_event(self):
        ev, self._ev = getattr(self, "_ev", None), None
        if ev is None:
            return
        dur = ev["t1"] - ev["t0"] + self.dt
        tr = ev["track"]
        drift = 0.0
        if len(tr) >= 4 and tr[-1][0] - tr[0][0] > 0.5:
            tt = np.array([x[0] for x in tr]) - tr[0][0]
            ff = np.array([x[1] for x in tr])
            drift = float(np.polyfit(tt, ff, 1)[0])
        if dur > PLANE_S or (dur > 2.0 and abs(drift) > PLANE_DRIFT):
            kind = "plane"
        elif (self._last_hot and ev["t0"] - self._last_hot[0] < PLANE_MEMORY_S
              and abs(ev["dop"] - self._last_hot[1]) < PLANE_DOPPLER_HZ + PLANE_DRIFT * (ev["t0"] - self._last_hot[0])):
            kind = "plane"
        else:
            kind = "under" if dur < UNDER_S else "over"
        if kind == "plane":
            self._last_hot = (ev["t1"], ev["dop"])
            self.planes += 1
        e = {"ts": round(ev["t0"], 2), "time": time.strftime("%H:%M:%S", time.gmtime(ev["t0"])), "dur": round(dur, 2),
             "snr": round(ev["peak"], 1), "doppler": round(ev["dop"]), "drift": round(drift, 1), "kind": kind,
             "freq_hz": round(GRAVES_HZ + ev["dop"])}
        with self.lock:
            self.events.append(e)
            if kind != "plane":
                h = self.hours.setdefault(hour_key(ev["t0"]), [0, 0, 0.0])
                h[0 if kind == "under" else 1] += 1
                self._dirty = True
        if self.on_echo:
            self.on_echo(e)

    def _count_time(self, secs, now):
        with self.lock:
            h = self.hours.setdefault(hour_key(now), [0, 0, 0.0])
            h[2] += secs
            self._dirty = True
        if now - self._saved > SAVE_S:
            self.save(now)

    # ----- stats -----
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.hours = {k: [int(v[0]), int(v[1]), float(v[2])] for k, v in (d.get("hours") or {}).items()}
            self.threshold_db = float(d.get("threshold_db", THRESHOLD_DB))
        except (OSError, ValueError, TypeError, IndexError, AttributeError):
            self.hours = {}

    def save(self, now=None):
        now = time.time() if now is None else now
        self._saved = now
        if not self._dirty:
            return
        cut = hour_key(now - LONG_DAYS * 86400)
        with self.lock:
            self.hours = {k: v for k, v in self.hours.items() if k >= cut}
            d = {"graves_hz": GRAVES_HZ, "threshold_db": self.threshold_db,
                 "hours": {k: [v[0], v[1], round(v[2], 1)] for k, v in self.hours.items()}}
            self._dirty = False
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, separators=(",", ":"))
            os.replace(tmp, self.path)
        except OSError as e:
            self.error = f"meteor: {e}"

    def clear(self):
        """Clears the recent echoes (the hourly statistics stay)."""
        with self.lock:
            self.events.clear()

    def reset_stats(self):
        with self.lock:
            self.hours = {}
            self._dirty = True
        self.save()

    @property
    def info(self):
        if not self.enabled:
            return ""
        h = self.hours.get(hour_key(time.time()))
        n = h[0] + h[1] if h else 0
        return f"{n} this hour · {self.status}"

    def summary(self, now=None):
        """Everything the METEORS page shows."""
        now = time.time() if now is None else now
        hh = [hour_key(now - i * 3600) for i in range(47, -1, -1)]
        with self.lock:
            hours = [[k] + list(self.hours.get(k, [0, 0, 0.0])) for k in hh]
            for h in hours:
                h[3] = round(h[3])
            days = {}
            for k, v in self.hours.items():
                d = days.setdefault(k[:10], [0, 0, 0.0])
                d[0] += v[0]
                d[1] += v[1]
                d[2] += v[2]
            events = list(self.events)[-200:]
            scope = list(self.scope)
        last60 = sum(1 for e in events if e["kind"] != "plane" and now - e["ts"] < 3600)
        today = days.get(hh[-1][:10], [0, 0, 0.0])
        return {"enabled": self.enabled, "status": self.status, "error": self.error, "threshold_db": self.threshold_db,
                "graves_hz": GRAVES_HZ, "dial_usb_hz": DIAL_USB_HZ, "now": now, "planes": self.planes,
                "this_hour": hours[-1][1] + hours[-1][2], "last_hour": hours[-2][1] + hours[-2][2],
                "last_60min": last60, "today": today[0] + today[1],
                "hours": hours, "days": sorted([k, v[0], v[1], round(v[2])] for k, v in days.items()),
                "events": events, "scope": scope}


def register(app, counter, station=None):
    """station: () -> (lat, lon) or None. GET /api/meteors: the page (with the path to GRAVES); DELETE clears the recent echoes (?stats=1 also the statistics);
    POST {threshold_db}: the detection threshold."""
    from flask import jsonify, request

    @app.route("/api/meteors", methods=["GET", "POST", "DELETE"])
    def api_meteors():
        if request.method == "DELETE":
            counter.clear()
            if request.args.get("stats") == "1":
                counter.reset_stats()
            return jsonify(ok=True)
        if request.method == "POST":
            body = request.get_json(force=True, silent=True) or {}
            if "threshold_db" in body:
                try:
                    counter.set_threshold(body["threshold_db"])
                except (TypeError, ValueError):
                    return jsonify({"error": "threshold_db must be a number"}), 400
                counter._dirty = True
                counter.save()
        out = counter.summary()
        qth = station() if station else None
        out["path"] = graves_path(*qth) if qth else None
        return jsonify(out)

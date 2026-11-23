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

The detail of each echo (the ECHOES table, a click on a row): the frames of the detector at full resolution (one per
hop, ~30 ms, not smoothed) from DETAIL_PRE_S before the echo to DETAIL_POST_S after it, kept for the last DETAIL_N
echoes. An echo is reported DETAIL_POST_S after its end, when that detail is complete.

HEAD (optional, set_head): the head echo, the reflection from the meteoroid itself, sweeps fast (kHz in a fraction of a
second) just before the trail echo. A second spectrum with short frames (~15 ms, ~70 Hz bins) over ±HEAD_HZ is kept for
the HEAD_PRE_S before the echo; a chain of strong points with a steep slope in it marks the echo as with a head echo.

SAT (meteor_sat.py): a wide spectrum (±8 kHz) always runs for the echoes of satellites. A meteor echo that is part of
a satellite track is not counted (it waits for the end of the track, SAT_WAIT_S at most); the track is reported as one
echo of kind "sat" after a thread found which satellite it was (orbital elements, the bistatic Doppler).
"""
import collections
import base64
import json
import math
import os
import threading
import time

import numpy as np

import meteor_air
from meteor_sat import SAT_HZ, SAT_DIV, SAT_SMOOTH, SAT_THR_DB, SAT_RING_S, Spec, SatTracker, identify, tle_state
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
SCOPE_S = 3600                          # the chart and the waterfall keep an hour; the page asks for 30 s … 1 h
SCOPE_RATE = 4                          # points per second
VIEW_COLS = 480                         # what the page gets: at most this many points / columns (max of each bucket)
WF_HZ = BAND_HZ                         # the small waterfall: the whole watched band, one column per scope point
WF_DB = 30.0                            # its scale: 0..WF_DB dB over the floor -> 0..255
SAVE_S = 60.0
RING_S = 30.0                           # the full-resolution frames kept for the detail of the next echo
DETAIL_PRE_S = 1.0
DETAIL_POST_S = 1.0
DETAIL_MAX_S = 20.0                     # a longer echo (aircraft): only its last DETAIL_MAX_S
DETAIL_N = 200
HEAD_HZ = 5000.0                        # the head echo spectrum: ±HEAD_HZ around the carrier (less if the VFO band is narrow)
HEAD_PRE_S = 1.5                        # its window: from HEAD_PRE_S before the echo …
HEAD_POST_S = 0.5                       # … to HEAD_POST_S after its start
HEAD_SKIP_HZ = 150.0                    # the trail echo itself (near the carrier) is not a head echo
HEAD_MIN_PTS = 5
HEAD_MIN_SLOPE = 2000.0                 # Hz/s: slower is wind drift or an aircraft
HEAD_MIN_SPAN_HZ = 300.0
SAT_WAIT_S = 200.0                      # an echo waits at most this long for the end of the track it is part of
SAT_PRE_S = 2.0                         # the detail of a satellite: from this before its track to this after it
SAT_COLS = 600                          # … in at most this many columns
OFFSET_RMS_HZ = 20.0                    # a satellite fit this good measures the receiver offset …
OFFSET_N = 10                           # … the median of the last this many is used for the aircraft
SAT_DETAIL_N = 30                      # (~0.6 MB each) the details of the last this many satellites are kept


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
        self.wf = collections.deque(maxlen=SCOPE_S * SCOPE_RATE)       # (t, bytes): dB over the floor per bin ±WF_HZ
        self.wf_hz = []                 # Doppler of the waterfall bins (Hz, low -> high)
        self.status = ""
        self.planes = 0
        self._dirty = False
        self._saved = 0.0
        self._fs = None
        self._dial = None
        self.head = False               # the head echo spectrum (set_head)
        self.head_hz = 0.0              # its band as set up (± Hz), 0 = off or does not fit
        self._hs = None                 # its state (_head_setup)
        self.details = collections.OrderedDict()    # ts of an echo -> its detail (_cut)
        self._pending = []              # closed echoes waiting for DETAIL_POST_S of frames
        self._ring = collections.deque()            # (t, uint8 bytes): full-resolution frames, RING_S
        self._ws = None                 # the wide spectrum (meteor_sat.Spec) and its tracks (SatTracker)
        self._trk = SatTracker()
        self.sat_hz = 0.0               # its band as set up (± Hz), 0 = does not fit
        self.sats = 0                   # satellite echoes since the start (not counted as meteors)
        self.station = None             # () -> (lat, lon) or None: for which satellite / aircraft it was (register)
        self.air = True                 # aircraft echoes looked up on adsb.fi (set_air)
        self.rx_offsets = []            # [[t, Hz]]: the receiver offset measured on satellites (rx_offset)
        self._load()

    # ----- settings -----
    def set_enabled(self, on):
        on = bool(on)
        if on and not self.enabled:
            self._fs = None             # a new start: learn the floor again
        if not on and self.enabled:
            self._close_event()
            self._flush()
            self.save()
        self.enabled = on

    def set_threshold(self, db):
        self.threshold_db = min(30.0, max(3.0, float(db)))

    def set_head(self, on):
        self.head = bool(on)
        self._hs = None                 # set up again (on) or dropped (off) with the next block
        self.head_hz = 0.0

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
        self.wf_sel = np.nonzero(np.abs(self.bin_hz) <= WF_HZ)[0]
        self._wf_max = None
        self._ring = collections.deque(maxlen=int(RING_S / self.dt) + 1)
        self._hs = None
        self._ws = None
        self._trk = SatTracker()
        with self.lock:
            self.wf.clear()
            self.wf_hz = [round(float(h), 1) for h in self.bin_hz[self.wf_sel]]
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
            self._flush()
            self._setup(fs, dial_hz)
        if not len(self.idx):
            return
        base = np.asarray(base, np.complex64)
        # first the wide spectrum and the head echo spectrum: their frames up to now are there when an echo is cut
        self._wide_feed(base, now)
        if self.head:
            self._head_feed(base, now)
        else:
            self._hs = None
        buf = np.concatenate((self._buf, base))
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
        inst = (p / med)[self.wf_sel] / np.maximum(self.floor[self.wf_sel], 1e-12)     # this frame alone: the detail
        self._ring.append((t, self._db8(inst)))
        while self._pending and t >= self._pending[0][0]["t1"] + DETAIL_POST_S:
            ev = self._pending[0][0]
            if "link" not in ev:        # once: the track has all its points up to now
                ev["link"] = self._trk.link(ev["track"]) if self._ws else None
            tr = ev["link"]
            if tr is not None and self._trk.is_open(tr) and t < ev["t1"] + SAT_WAIT_S:
                break                   # part of a track still going on: a satellite or not is told when it ends
            self._finish(*self._pending.pop(0), tr)
        self.floor += (s - self.floor) * (self.dt / tau)
        if learning:
            return
        if self.status.startswith("learning"):
            self.status = "listening"
        k = int(np.argmax(ratio))
        snr = 10 * math.log10(max(ratio[k], 1e-6))
        wide = np.count_nonzero(ratio >= thr / 2) > WIDE_FRAC * len(ratio)
        w = ratio[self.wf_sel]
        self._wf_max = w if self._wf_max is None else np.maximum(self._wf_max, w)
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
            col = b""
            if self._wf_max is not None and len(self._wf_max):
                db = 10 * np.log10(np.maximum(self._wf_max, 1.0))
                col = np.clip(db * (255.0 / WF_DB), 0, 255).astype(np.uint8).tobytes()
            with self.lock:
                self.scope.append((round(t, 2), round(max(self._scope_max, -20.0), 1)))
                if col:
                    self.wf.append((round(t, 2), col))
            self._wf_max = None
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
        e = {"ts": round(ev["t0"], 2), "time": time.strftime("%H:%M:%S", time.gmtime(ev["t0"])), "dur": round(dur, 2),
             "snr": round(ev["peak"], 1), "doppler": round(ev["dop"]), "drift": round(drift, 1), "kind": kind,
             "freq_hz": round(GRAVES_HZ + ev["dop"]), "det": False, "head": None}
        self._pending.append((ev, e))   # reported when its detail is complete (DETAIL_POST_S later)

    def _flush(self):
        """Reports the waiting echoes with the frames there are (stop, retune); the open tracks end."""
        if self._ws:
            for tr in self._trk.close_all(self._ws.bin):
                if tr["sat"]:
                    self._sat_found(tr)
        while self._pending:
            ev = self._pending[0][0]
            tr = ev["link"] if "link" in ev else (self._trk.link(ev["track"]) if self._ws else None)
            self._finish(*self._pending.pop(0), tr)

    def _finish(self, ev, e, tr=None):
        """An echo is complete: counted, or left out as a piece of a satellite track (that track is reported)."""
        if tr is not None and tr.get("sat"):
            tr["pieces"] = tr.get("pieces", 0) + 1
            return
        try:
            self._cut(ev, e)
        except Exception as x:          # the echo is counted even if its detail fails
            self.error = f"meteor detail: {x}"
        if e["kind"] == "plane" and self.station and self.air:
            with self.lock:
                self.planes += 1
            e["air"] = None             # which aircraft: asked from adsb.fi in a thread, reported then
            threading.Thread(target=self._air_publish, args=(e, [(p[0], p[1]) for p in ev["track"]]), daemon=True,
                             name="meteor-air").start()
            return
        with self.lock:
            self.events.append(e)
            if e["kind"] == "plane":
                self.planes += 1
            else:
                h = self.hours.setdefault(hour_key(ev["t0"]), [0, 0, 0.0])
                h[0 if e["kind"] == "under" else 1] += 1
                self._dirty = True
        if self.on_echo:
            self.on_echo(e)

    @staticmethod
    def _db8(ratio):
        """Power ratios -> uint8 bytes, 0..WF_DB dB over the floor."""
        db = 10 * np.log10(np.maximum(ratio, 1.0))
        return np.clip(db * (255.0 / WF_DB), 0, 255).astype(np.uint8).tobytes()

    # ----- the detail of an echo -----
    def _cut(self, ev, e):
        """Keeps the full-resolution frames around the echo (and the head echo spectrum before it)."""
        t_end = ev["t1"] + DETAIL_POST_S
        t_start = max(ev["t0"] - DETAIL_PRE_S, t_end - DETAIL_MAX_S)
        rows = [(t, c) for t, c in self._ring if t_start <= t <= t_end]
        if not rows:
            return
        n = len(rows[-1][1])
        rows = [(t, c) for t, c in rows if len(c) == n]
        det = {"ts": e["ts"], "t0": rows[0][0], "dt": self.dt, "hz": [round(float(h), 1) for h in self.bin_hz[self.wf_sel]],
               "rows": b"".join(c for _, c in rows), "n": len(rows), "echo": e, "head": None}
        hs = self._hs
        if hs and hs.ring and ev["t1"] - ev["t0"] < DETAIL_MAX_S:
            a, b = ev["t0"] - HEAD_PRE_S, ev["t0"] + HEAD_POST_S
            hrows = [(t, c) for t, c in hs.ring if a <= t <= b and len(c) == len(hs.hz)]
            if hrows:
                det["head"] = {"t0": hrows[0][0], "dt": hs.dt, "hz": hs.hz_list, "rows": b"".join(c for _, c in hrows),
                               "n": len(hrows)}
                e["head"] = self._head_find(hrows, hs, ev["t0"])
        e["det"] = True
        with self.lock:
            self.details[e["ts"]] = det
            while len(self.details) > DETAIL_N:
                self.details.popitem(last=False)

    def detail(self, ts):
        """The detail of the echo ts (its "ts"), for the page: rows as base64 of uint8 (0..WF_DB dB), None if gone."""
        with self.lock:
            d = self.details.get(ts)
            if d is None:               # a float from the page: the nearest within 10 ms
                near = [k for k in self.details if abs(k - ts) < 0.01]
                d = self.details[near[0]] if near else None
        if d is None:
            return None
        out = {k: v for k, v in d.items() if k not in ("rows", "head")}
        out["rows"] = base64.b64encode(d["rows"]).decode()
        out["db"] = WF_DB
        h = d["head"]
        out["head"] = dict(h, rows=base64.b64encode(h["rows"]).decode()) if h else None
        return out

    # ----- the wide spectrum: satellites (meteor_sat.py) -----
    def _band(self, want):
        """± Hz around the carrier that fit in the VFO band, at most want; 0 if under 1 kHz."""
        band = min(want, self._fs / 2 * 0.9 - abs(self.f_off))
        return float(band) if band >= 1000 else 0.0

    def _wide_feed(self, base, now):
        ws = self._ws
        if ws is None:
            band = self._band(SAT_HZ)
            if not band:
                self.sat_hz = 0.0
                return
            n = 1 << int(round(math.log2(max(128.0, self._fs / SAT_DIV))))
            ws = self._ws = Spec(self._fs, self.f_off, n, n // 2, band, SAT_SMOOTH, SAT_RING_S, True, WF_DB)
            self._trk = SatTracker()
            self.sat_hz = band
        thr = 10 ** (SAT_THR_DB / 10)
        for t, ratio in ws.feed(base, now, thr):
            for tr in self._trk.frame(t, ratio, ws.hz, thr, ws.bin):
                if tr["sat"]:
                    self._sat_found(tr)

    def _sat_found(self, tr):
        """A satellite track ended: its echo, its detail (the wide spectrum) and, in a thread, which satellite it was."""
        pts = tr["pts"]
        k = max(range(len(pts)), key=lambda i: pts[i][2])
        t0, t1 = tr["t0"], tr["t1"]
        e = {"ts": round(t0, 2), "time": time.strftime("%H:%M:%S", time.gmtime(t0)), "dur": round(t1 - t0, 2),
             "snr": round(pts[k][2], 1), "doppler": round(pts[k][1]), "drift": round(tr["slope"], 1), "kind": "sat",
             "freq_hz": round(GRAVES_HZ + pts[k][1]), "det": False, "head": None,
             "f0": round(pts[0][1]), "f1": round(pts[-1][1]), "sat": None}
        cut = self._ws.rows(t0 - SAT_PRE_S, t1 + SAT_PRE_S, SAT_COLS)
        step = max(1, len(pts) // 400)
        det = None
        if cut:
            det = {"ts": e["ts"], "t0": cut[0], "dt": cut[1], "n": cut[2], "rows": cut[3], "hz": self._ws.hz_list,
                   "echo": e, "head": None, "pts": [[round(p[0], 3), round(p[1], 1)] for p in pts[::step]], "curve": None}
            e["det"] = True
        self.sats += 1
        threading.Thread(target=self._sat_publish, args=(e, det, [(p[0], p[1]) for p in pts]), daemon=True,
                         name="meteor-sat").start()

    def _sat_publish(self, e, det, pts):
        try:
            qth = self.station() if self.station else None
            res = identify(pts, qth, (GRAVES_LAT, GRAVES_LON), GRAVES_HZ)
        except Exception as x:          # the echo is reported anyway
            res = {"norad": None, "why": f"identification failed: {x}"}
        if det is not None:
            det["curve"] = res.pop("curve", None)
        else:
            res.pop("curve", None)
        e["sat"] = res
        if res.get("norad") and not res.get("others") and res.get("rms", 99) <= OFFSET_RMS_HZ:
            with self.lock:             # a sure fit measures the receiver offset (for the aircraft)
                self.rx_offsets = (self.rx_offsets + [[round(e["ts"]), res["offset"]]])[-OFFSET_N:]
                self._dirty = True
        with self.lock:
            if det is not None:
                self.details[e["ts"]] = det
                sat = [k for k, v in self.details.items() if v["echo"]["kind"] == "sat"]
                for k in sat[:-SAT_DETAIL_N]:           # the big ones: only the last few
                    del self.details[k]
                while len(self.details) > DETAIL_N:
                    self.details.popitem(last=False)
            self.events.append(e)
        if self.on_echo:
            self.on_echo(e)

    # ----- which aircraft (meteor_air.py, adsb.fi) -----
    def rx_offset(self):
        """The receiver offset at 143 MHz (Hz) measured on the satellites identified surely, 0 before any."""
        with self.lock:
            offs = [o for _, o in self.rx_offsets]
        return float(np.median(offs)) if offs else 0.0

    def _air_publish(self, e, pts):
        try:
            qth = self.station() if self.station else None
            if not qth:
                res = {"hex": None, "why": "the station location is not set (SETUP › LOCATION)"}
            else:
                mid = meteor_air.midpoint(qth[0], qth[1], GRAVES_LAT, GRAVES_LON)
                t_now, ac = meteor_air.fetch(*mid)
                res = meteor_air.identify(pts, qth, (GRAVES_LAT, GRAVES_LON), GRAVES_HZ, ac, t_now, self.rx_offset())
        except Exception as x:          # no internet, adsb.fi down: the echo is reported anyway
            res = {"hex": None, "why": f"adsb.fi: {x}"}
        curve = res.pop("curve", None)
        e["air"] = res
        with self.lock:
            det = self.details.get(e["ts"])
            if det is not None:
                det["curve"] = curve
            self.events.append(e)
        if self.on_echo:
            self.on_echo(e)

    # ----- the head echo spectrum -----
    def _head_feed(self, base, now):
        hs = self._hs
        if hs is None:
            band = self._band(HEAD_HZ)
            if not band:
                self.head_hz = 0.0
                return
            n = 1 << int(round(math.log2(max(64.0, self._fs / 64.0))))
            hs = self._hs = Spec(self._fs, self.f_off, n, n // 2, band, 1, RING_S, False, WF_DB)
            self.head_hz = band
        hs.feed(base, now, 10 ** (self.threshold_db / 10))

    def _head_find(self, hrows, hs, t_echo):
        """A head echo: a chain of strong points (THR dB, away from the carrier) before the echo, steep and straight.
        Returns {"slope": Hz/s, "f0", "f1": Hz, "t": s before the echo} or None."""
        lim = int(min(255, self.threshold_db * 255.0 / WF_DB))
        hz = hs.hz
        away = np.abs(hz) >= HEAD_SKIP_HZ
        pts = []
        for t, c in hrows:
            if t > t_echo + 0.2:
                break
            v = np.frombuffer(c, np.uint8)
            if len(v) != len(hz):
                continue
            k = int(np.argmax(np.where(away, v, 0)))
            if v[k] >= lim:
                pts.append((t, float(hz[k])))
        chains = []                     # each point continues the chain that ended last within 3 frames and 1 kHz
        for t, f in pts:
            best = None
            for ch in chains:
                lt, lf = ch[-1]
                if 0 < t - lt <= 3.5 * hs.dt and abs(f - lf) <= 1000.0 and (best is None or ch[-1][0] > best[-1][0]):
                    best = ch
            if best is None:
                chains.append([(t, f)])
            else:
                best.append((t, f))
        chains = [c for c in chains if len(c) >= HEAD_MIN_PTS]
        if not chains:
            return None
        ch = max(chains, key=len)
        tt = np.array([p[0] for p in ch]) - ch[0][0]
        ff = np.array([p[1] for p in ch])
        slope, icpt = np.polyfit(tt, ff, 1)
        rms = float(np.sqrt(np.mean((ff - (slope * tt + icpt)) ** 2)))
        if abs(slope) < HEAD_MIN_SLOPE or ff.max() - ff.min() < HEAD_MIN_SPAN_HZ or rms > 2.5 * hs.bin:
            return None
        return {"slope": round(float(slope)), "f0": round(float(ff[0])), "f1": round(float(ff[-1])),
                "t": round(float(t_echo - ch[0][0]), 2)}

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
            self.head = bool(d.get("head", False))
            self.air = bool(d.get("air", True))
            self.rx_offsets = [[float(a), float(b)] for a, b in d.get("rx_offsets", [])][-OFFSET_N:]
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
            d = {"graves_hz": GRAVES_HZ, "threshold_db": self.threshold_db, "head": self.head, "air": self.air, "rx_offsets": self.rx_offsets,
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

    @staticmethod
    def bucket_s(span):
        """Seconds per point / column for a view of span seconds (VIEW_COLS of them, not finer than the scope)."""
        span = min(float(SCOPE_S), max(10.0, float(span)))
        return max(1.0 / SCOPE_RATE, span / VIEW_COLS)

    def waterfall(self, since_k=-1, span=120):
        """The small waterfall for a view of span seconds: columns k (start k × b s) from since_k on, each the max of its
        raw columns, base64 of uint8 (0..WF_DB dB over the floor). The newest column may still grow: the page replaces it."""
        b = self.bucket_s(span)
        t_from = max(since_k * b, time.time() - min(float(span), SCOPE_S) - b)
        with self.lock:
            rows = [(t, c) for t, c in self.wf if t >= t_from]
            hz = list(self.wf_hz)
        cols = []
        if rows:
            ks = np.floor(np.array([t for t, _ in rows]) / b).astype(np.int64)
            n = len(rows[-1][1])
            keep = [i for i, (_, c) in enumerate(rows) if len(c) == n]
            if keep:
                ks = ks[keep]
                arr = np.frombuffer(b"".join(rows[i][1] for i in keep), np.uint8).reshape(len(keep), n)
                starts = np.r_[0, np.nonzero(np.diff(ks))[0] + 1]
                mx = np.maximum.reduceat(arr, starts, axis=0)
                cols = [[int(ks[i]), base64.b64encode(m.tobytes()).decode()] for i, m in zip(starts, mx) if ks[i] >= since_k]
        return {"hz": hz, "db": WF_DB, "bucket_s": b, "now": time.time(), "cols": cols}

    @property
    def info(self):
        if not self.enabled:
            return ""
        h = self.hours.get(hour_key(time.time()))
        n = h[0] + h[1] if h else 0
        return f"{n} this hour · {self.status}"

    def summary(self, now=None, span=120):
        """Everything the METEORS page shows; the chart (scope) for the last span seconds, the max of each bucket."""
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
            events = list(self.events)[-400:]
            b = self.bucket_s(span)
            t_from = now - min(float(span), SCOPE_S) - b
            scope, last_k = [], None
            for t, v in self.scope:
                if t < t_from:
                    continue
                k = int(t // b)
                if k == last_k:
                    scope[-1][1] = max(scope[-1][1], v)
                else:
                    scope.append([round(k * b, 2), v])
                    last_k = k
        last60 = sum(1 for e in events if e["kind"] in ("under", "over") and now - e["ts"] < 3600)
        today = days.get(hh[-1][:10], [0, 0, 0.0])
        return {"enabled": self.enabled, "status": self.status, "error": self.error, "threshold_db": self.threshold_db,
                "head": self.head, "head_hz": self.head_hz, "air": self.air, "rx_offset": round(self.rx_offset(), 1),
                "rx_offset_n": len(self.rx_offsets), "sat_hz": self.sat_hz, "sats": self.sats, "tle": tle_state(),
                "graves_hz": GRAVES_HZ, "dial_usb_hz": DIAL_USB_HZ, "now": now, "planes": self.planes,
                "this_hour": hours[-1][1] + hours[-1][2], "last_hour": hours[-2][1] + hours[-2][2],
                "last_60min": last60, "today": today[0] + today[1],
                "hours": hours, "days": sorted([k, v[0], v[1], round(v[2])] for k, v in days.items()),
                "events": events, "scope": scope, "span_s": span}


def register(app, counter, station=None):
    """station: () -> (lat, lon) or None. GET /api/meteors: the page (with the path to GRAVES); DELETE clears the recent echoes (?stats=1 also the statistics);
    POST {threshold_db, head}: the detection threshold, the head echo spectrum on/off. GET /api/meteors/echo?ts=: the
    detail of one echo."""
    from flask import jsonify, request
    counter.station = station           # which satellite a satellite echo was (meteor_sat.identify)

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
            if "head" in body:
                counter.set_head(body["head"])
                counter._dirty = True
                counter.save()
            if "air" in body:
                counter.air = bool(body["air"])
                counter._dirty = True
                counter.save()
        try:
            span = float(request.args.get("span", 120) or 120)
        except ValueError:
            span = 120.0
        out = counter.summary(span=span)
        qth = station() if station else None
        out["path"] = graves_path(*qth) if qth else None
        return jsonify(out)

    @app.route("/api/meteors/wf")
    def api_meteors_wf():
        """The small waterfall of the METEORS page: ?span=<s>&since=<k> only the columns from k on (k of the span's buckets)."""
        try:
            since = int(request.args.get("since", -1) or -1)
            span = float(request.args.get("span", 120) or 120)
        except ValueError:
            since, span = -1, 120.0
        return jsonify(counter.waterfall(since, span))

    @app.route("/api/meteors/echo")
    def api_meteors_echo():
        try:
            ts = float(request.args.get("ts", ""))
        except ValueError:
            return jsonify({"error": "ts must be a number"}), 400
        d = counter.detail(ts)
        if d is None:
            return jsonify({"error": "no detail of this echo (only the last ones are kept, not over a restart)"}), 404
        return jsonify(d)

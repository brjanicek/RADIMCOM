"""METEORS on GRAVES: the wide spectrum (±8 kHz), satellite echoes in it and which satellite it was.

GRAVES (143.050 MHz) is a space surveillance radar: besides the meteor trails, satellites in its beam reflect it too.
A satellite in a low orbit moves ~7.5 km/s, so its echo is a long streak (seconds to tens of seconds) that sweeps over
hundreds of Hz to kHz, often cut into pieces as the beam of GRAVES moves on. An aircraft (at most ~250 Hz off the
carrier at 143 MHz) drifts slower and stays close to the carrier; a meteor trail hardly drifts at all.

Spec: a spectrum around the carrier with a floor per bin (the frames divided by their median, like the meteor
detector), used for the wide spectrum of the satellites and the short frames of the head echo (meteor.py).

SatTracker: in the wide spectrum (~64 ms frames, ~16 Hz bins, smoothed over SAT_SMOOTH frames) the strongest peaks
of each frame are joined to tracks (each continues where its own slope points); a track ends after SAT_GAP_S without
a point. A track is a satellite when it is long enough, dense enough, smooth (a cubic fits it) and either drifts over
SAT_DRIFT Hz/s or runs further than SAT_FAR_HZ off the carrier, where no aircraft can be.

identify: the bistatic Doppler of every satellite with orbital elements (CelesTrak groups "active", "visual" and
"stations", data/graves_tle.txt, downloaded again after a day, and the elements of the SATELLITES tab) seen from both
GRAVES and the station: f = -(F / c) d/dt (|sat - GRAVES| + |sat - station|). The one whose curve fits the measured
track best (a constant offset of the receiver allowed) is it. Debris and objects without public elements stay unknown.
"""
import bisect
import collections
import math
import os
import threading
import time
import urllib.request

import numpy as np

from paths import data

SAT_HZ = 8000.0                 # the wide spectrum: ±SAT_HZ around the carrier (less if the VFO band is narrow)
SAT_DIV = 16                    # its frames: fs / SAT_DIV samples (~64 ms), every half frame
SAT_SMOOTH = 3
SAT_THR_DB = 8.0                # a peak of the smoothed spectrum over its floor (noise: < 1 such peak a second)
SAT_PEAKS = 4                   # the strongest peaks of a frame that may join a track
SAT_NMS_HZ = 150.0              # weaker peaks this close to a stronger one are its side peaks
SAT_OPEN_MAX = 40
SAT_GAP_S = 4.0                 # a track ends after this without a point (the beam of GRAVES moves on)
SAT_MAX_S = 180.0               # a longer track is closed (and a new one goes on)
SAT_MIN_S = 1.0
SAT_MIN_PTS = 8
SAT_MIN_DENSITY = 2.0           # points a second over the whole track
SAT_DRIFT = 40.0                # Hz/s: faster than an aircraft
SAT_SPAN_HZ = 250.0             # … and sweeps over at least this (two meteors joined by chance do not)
SAT_FAR_HZ = 450.0              # an aircraft is never this far off the carrier at 143 MHz
SAT_FIT_HZ = 60.0               # a point further than this from the smooth curve of the track is not its own
SAT_INLIERS = 0.8
SAT_RING_S = 200.0              # the wide spectrum kept for the detail of a satellite
LINK_DT = 0.12                  # a meteor echo point and a track point closer than this in time …
LINK_DF = 50.0                  # … and in Hz are the same signal
LINK_SMEAR_S = 0.3              # the meteor detector (125 ms frames smoothed over 4) smears a fast sweep over this
LEARN_S = 4.0
TAU_S = 10.0
TAU_HOT_S = 120.0

TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP={}&FORMAT=tle"
TLE_GROUPS = ("active", "visual", "stations")
TLE_PATH = data("graves_tle.txt")
TLE_MAX_AGE_S = 24 * 3600
TLE_RETRY_S = 3600
TLE_TIMEOUT_S = 30
TLE_MAX_BYTES = 12_000_000
ID_POINTS = 40                  # the track is compared at this many of its points
ID_RMS_HZ = 80.0                # a fit worse than this is no identification
ID_OFFSET_HZ = 300.0            # the receiver may be off by this much (PPM)
ID_OUTSIDE = 1.5                # the fit counts this much worse outside the sector GRAVES illuminates
GRAVES_AZ = (90.0, 270.0)       # GRAVES lights the southern sky, low: azimuth and elevation seen from it (about)
GRAVES_EL = (10.0, 45.0)
EARTH_A_KM, EARTH_F = 6378.137, 1 / 298.257223563
EARTH_W = 7.292115e-5
C_KM_S = 299792.458


def db8(ratio, full_db):
    """Power ratios -> uint8 bytes, 0..full_db dB over the floor."""
    db = 10 * np.log10(np.maximum(ratio, 1.0))
    return np.clip(db * (255.0 / full_db), 0, 255).astype(np.uint8).tobytes()


class Spec:
    """A spectrum of the complex baseband around the carrier (f_off Hz from the dial), ±band Hz, frames of n samples
    every hop; each frame divided by its median and by the floor of each bin. The frames of the last ring_s seconds
    are kept as uint8 (0..full_db dB): smoothed (ring_smooth) or each frame alone."""

    def __init__(self, fs, f_off, n, hop, band, smooth, ring_s, ring_smooth, full_db):
        freqs = np.fft.fftfreq(n, 1.0 / fs)
        idx = np.nonzero(np.abs(freqs - f_off) <= band)[0]
        self.idx = idx[np.argsort(freqs[idx])]
        self.hz = freqs[self.idx] - f_off
        self.hz_list = [round(float(h), 1) for h in self.hz]
        self.fs, self.n, self.hop, self.dt, self.bin, self.band = fs, n, hop, hop / fs, fs / n, band
        self.win = np.hanning(n).astype(np.float32)
        self.buf = np.zeros(0, np.complex64)
        self.floor = None
        self.learn = 0.0
        self.hist = collections.deque(maxlen=max(1, smooth))
        self.ring = collections.deque(maxlen=int(ring_s / self.dt) + 1)
        self.ring_smooth = ring_smooth
        self.full_db = full_db

    def feed(self, base, now, thr_lin):
        """-> [(t, smoothed ratio over the floor)] of the new frames after the floor is learned; t = end of the frame."""
        buf = np.concatenate((self.buf, base))
        n, hop = self.n, self.hop
        nfr = (len(buf) - n) // hop + 1 if len(buf) >= n else 0
        out = []
        if nfr > 0:
            seg = buf[np.arange(nfr)[:, None] * hop + np.arange(n)] * self.win
            pw = np.abs(np.fft.fft(seg, axis=1)[:, self.idx]) ** 2
            for i in range(nfr):
                med = float(np.median(pw[i]))
                if med <= 0:
                    continue
                r = pw[i] / med
                self.hist.append(r)
                s = np.mean(self.hist, axis=0) if len(self.hist) > 1 else r
                if self.floor is None:
                    self.floor = s.copy()
                self.learn += self.dt
                fl = np.maximum(self.floor, 1e-12)
                ratio = s / fl
                t = now - (len(buf) - i * hop - n) / self.fs
                self.ring.append((t, db8(ratio if self.ring_smooth else r / fl, self.full_db)))
                learning = self.learn < LEARN_S
                tau = self.learn if learning else np.where(ratio >= thr_lin, TAU_HOT_S, TAU_S)
                self.floor += (s - self.floor) * (self.dt / tau)
                if not learning:
                    out.append((t, ratio))
        self.buf = buf[nfr * hop:]
        return out

    def rows(self, a, b, max_cols=0):
        """The kept frames from a to b -> (t of the first, dt of a column, n, bytes); max_cols: the max of groups of
        frames so there are no more columns than that."""
        rows = [c for t, c in self.ring if a <= t <= b]
        t0 = next((t for t, _ in self.ring if a <= t <= b), None)
        if not rows:
            return None
        nb = len(self.hz)
        arr = np.frombuffer(b"".join(r for r in rows if len(r) == nb), np.uint8).reshape(-1, nb)
        dt = self.dt
        if max_cols and len(arr) > max_cols:
            g = int(math.ceil(len(arr) / max_cols))
            pad = (-len(arr)) % g
            if pad:
                arr = np.vstack((arr, np.zeros((pad, nb), np.uint8)))
            arr = arr.reshape(-1, g, nb).max(axis=1)
            t0 += (g - 1) * dt          # each column ends where its last frame ends
            dt *= g
        return t0, dt, len(arr), arr.tobytes()


class SatTracker:
    """Joins the peaks of the wide spectrum to tracks and tells the satellites among them."""

    def __init__(self):
        self.open = []
        self.closed = collections.deque(maxlen=60)       # recent closed tracks (meteor echoes are linked to them)
        self._n = 0

    @staticmethod
    def _add(tr, p):
        """A point joins the track; its line (where the next point is expected) is fitted to the last 12 points."""
        tr["pts"].append(p)
        pts = tr["pts"][-12:]
        a, b = 0.0, p[1]
        if len(pts) >= 4 and pts[-1][0] - pts[0][0] > 0.2:
            tt = np.array([q[0] for q in pts]) - p[0]
            ff = np.array([q[1] for q in pts])
            a, b = np.polyfit(tt, ff, 1)
        tr["line"] = (p[0], float(b), float(a))

    @staticmethod
    def _pred(tr, t):
        t_ref, f_ref, a = tr["line"]
        return f_ref + a * (t - t_ref)

    def frame(self, t, ratio, hz, thr_lin, bin_hz):
        """One frame of the wide spectrum -> the tracks closed now (each classified, "sat" True / False)."""
        done = []
        for tr in list(self.open):
            if t - tr["pts"][-1][0] > SAT_GAP_S or t - tr["pts"][0][0] > SAT_MAX_S:
                self.open.remove(tr)
                done.append(self._close(tr, bin_hz))
        if len(ratio) >= 3:
            mid = ratio[1:-1]
            ks = np.nonzero((mid > thr_lin) & (mid >= ratio[:-2]) & (mid > ratio[2:]))[0] + 1
            if len(ks):
                ks = ks[np.argsort(ratio[ks])[::-1]]
                keep = []                       # the strongest first; its smeared side peaks (±SAT_NMS_HZ) are not others
                for k in ks:
                    if all(abs(hz[k] - hz[j]) > SAT_NMS_HZ for j in keep):
                        keep.append(k)
                        if len(keep) >= SAT_PEAKS:
                            break
                used = set()
                for k in keep:
                    f, db = float(hz[k]), float(10 * math.log10(ratio[k]))
                    best, best_d = None, None
                    for tr in self.open:
                        if id(tr) in used:
                            continue
                        gap = t - tr["pts"][-1][0]
                        d = abs(f - self._pred(tr, t))
                        if d <= 3 * bin_hz + 60.0 + min(400.0, 80.0 * gap) and (best_d is None or d < best_d):
                            best, best_d = tr, d
                    if best is None:
                        if len(self.open) >= SAT_OPEN_MAX:
                            continue
                        self._n += 1
                        best = {"id": self._n, "pts": []}
                        self.open.append(best)
                    self._add(best, (t, f, db))
                    used.add(id(best))
        return done

    def close_all(self, bin_hz):
        done = [self._close(tr, bin_hz) for tr in self.open]
        self.open = []
        return done

    def _close(self, tr, bin_hz):
        tr["sat"] = False
        pts = tr["pts"]
        tr["t0"], tr["t1"] = pts[0][0], pts[-1][0]
        if len(pts) >= SAT_MIN_PTS and tr["t1"] - tr["t0"] >= SAT_MIN_S:
            tt = np.array([p[0] for p in pts]) - tr["t0"]
            ff = np.array([p[1] for p in pts])
            deg = 3 if len(pts) >= 12 else 1
            c = np.polyfit(tt, ff, deg)
            keep = np.abs(ff - np.polyval(c, tt)) <= max(SAT_FIT_HZ, 3 * bin_hz)
            if keep.sum() >= max(SAT_MIN_PTS, SAT_INLIERS * len(pts)):
                tt, ff = tt[keep], ff[keep]
                pts = [p for p, k in zip(pts, keep) if k]
                c = np.polyfit(tt, ff, deg)
                rms = float(np.sqrt(np.mean((ff - np.polyval(c, tt)) ** 2)))
                slope = float(np.polyfit(tt, ff, 1)[0])
                dur = tt[-1] - tt[0]
                far = float(np.percentile(np.abs(ff), 90))
                fit = np.polyval(c, tt)
                span = float(fit.max() - fit.min())
                tr.update(pts=pts, slope=slope, rms=rms, far=far, span=span)
                tr["sat"] = bool(dur >= SAT_MIN_S and len(pts) / max(dur, 1e-3) >= SAT_MIN_DENSITY
                                 and rms <= max(SAT_FIT_HZ / 2, 2 * bin_hz)
                                 and ((abs(slope) >= SAT_DRIFT and span >= SAT_SPAN_HZ) or far >= SAT_FAR_HZ))
                tr["t0"], tr["t1"] = pts[0][0], pts[-1][0]
                if tr["sat"]:                   # a second track along the same streak (side peaks) is not another one
                    for o in self.closed:
                        if o.get("sat") and o["t1"] >= tr["t0"] and o["t0"] <= tr["t1"] and self._hits(o, pts, 0.0, 0.0) >= len(pts) / 2:
                            tr["sat"], tr["dup"] = False, o["id"]
                            break
        self.closed.append(tr)
        return tr

    @staticmethod
    def _hits(tr, ev_pts, dt_more, smear_s):
        """How many of the points (t, Hz, …) lie on the track: within LINK_DT (+ dt_more) of one of its points and
        LINK_DF + the track's drift over smear_s from it (a fast sweep is smeared by the long frames of the meteor
        detector)."""
        e0, e1 = ev_pts[0][0] - LINK_DT - dt_more - 0.5, ev_pts[-1][0] + LINK_DT + dt_more + 0.5
        tp = tr["pts"]
        i0 = bisect.bisect_left(tp, (e0,))
        i1 = bisect.bisect_right(tp, (e1, math.inf))
        near = tp[i0:i1]
        if not near:
            return 0
        slope = abs(near[-1][1] - near[0][1]) / (near[-1][0] - near[0][0]) if len(near) >= 2 and near[-1][0] > near[0][0] else 0.0
        tol_f = LINK_DF + slope * smear_s
        tol_t = LINK_DT + dt_more
        et = np.array([p[0] for p in ev_pts])[:, None]
        ef = np.array([p[1] for p in ev_pts])[:, None]
        nt = np.array([q[0] for q in near])[None, :]
        nf = np.array([q[1] for q in near])[None, :]
        return int(np.count_nonzero(np.any((np.abs(et - nt) <= tol_t) & (np.abs(ef - nf) <= tol_f), axis=1)))

    def link(self, ev_pts):
        """The track (open or recently closed) a meteor echo (its points (t, Hz)) is part of, or None."""
        best, best_n = None, 0
        if not ev_pts:
            return None
        need = min(2, len(ev_pts))
        for tr in list(self.open) + list(self.closed):
            if not tr["pts"] or tr["pts"][-1][0] < ev_pts[0][0] - 1.0 or tr["pts"][0][0] > ev_pts[-1][0] + 1.0:
                continue
            n = self._hits(tr, ev_pts, LINK_SMEAR_S, LINK_SMEAR_S)
            if n >= need and n > best_n:
                best, best_n = tr, n
        return best

    def is_open(self, tr):
        return any(tr is o for o in self.open)


# ---------- which satellite ----------

_tle_lock = threading.Lock()
_tle = {"key": None, "arr": None, "names": [], "norads": [], "last_try": 0.0, "error": ""}


def _parse(text):
    import sattrack
    return sattrack.parse_tle(text)


def _download():
    merged = {}
    errors = []
    for g in TLE_GROUPS:
        try:
            req = urllib.request.Request(TLE_URL.format(g), headers={"User-Agent": "RADIMCOM"})
            with urllib.request.urlopen(req, timeout=TLE_TIMEOUT_S) as r:
                text = r.read(TLE_MAX_BYTES + 1).decode("ascii", "replace")
            if len(text) > TLE_MAX_BYTES:
                raise ValueError("answer too long")
            for k, v in _parse(text).items():
                merged.setdefault(k, v)
        except (OSError, ValueError) as e:
            errors.append(f"{g}: {getattr(e, 'reason', e)}")
    if not merged:
        raise OSError("; ".join(errors) or "no elements")
    tmp = f"{TLE_PATH}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="ascii") as f:
        f.write("".join(f"{n}\n{l1}\n{l2}\n" for n, l1, l2 in merged.values()))
    os.replace(tmp, TLE_PATH)
    return "; ".join(errors)


def tle_state():
    """-> {"sats": number of satellites with elements, "fetched": unix time of graves_tle.txt or None, "error"}."""
    try:
        m = os.path.getmtime(TLE_PATH)
    except OSError:
        m = None
    return {"sats": len(_tle["norads"]), "fetched": m, "error": _tle["error"]}


def _elements():
    """(SatrecArray, names, norads) of graves_tle.txt and the SATELLITES elements; downloads when old (in this thread)."""
    from sgp4.api import Satrec, SatrecArray
    import sattrack
    with _tle_lock:
        try:
            m = os.path.getmtime(TLE_PATH)
        except OSError:
            m = None
        if (m is None or time.time() - m > TLE_MAX_AGE_S) and time.time() - _tle["last_try"] > TLE_RETRY_S:
            _tle["last_try"] = time.time()
            try:
                _tle["error"] = _download()
                m = os.path.getmtime(TLE_PATH)
            except OSError as e:
                _tle["error"] = f"orbital elements: {getattr(e, 'reason', e)}"
        try:
            m2 = os.path.getmtime(sattrack.TLE_PATH)
        except OSError:
            m2 = None
        key = (m, m2)
        if _tle["key"] != key:
            parsed = {}
            for path in (TLE_PATH, sattrack.TLE_PATH):
                try:
                    with open(path, encoding="ascii", errors="replace") as f:
                        for k, v in _parse(f.read()).items():
                            parsed.setdefault(k, v)
                except OSError:
                    pass
            sats, names, norads = [], [], []
            for norad, (name, l1, l2) in parsed.items():
                try:
                    sats.append(Satrec.twoline2rv(l1, l2))
                except (ValueError, IndexError):
                    continue
                names.append(name)
                norads.append(norad)
            _tle.update(key=key, arr=SatrecArray(sats) if sats else None, names=names, norads=norads)
        return _tle["arr"], _tle["names"], _tle["norads"]


def _site(lat, lon, alt_m=0.0):
    """ECEF (km) of a place and its unit vectors up, east, north."""
    la, lo = math.radians(lat), math.radians(lon)
    e2 = EARTH_F * (2 - EARTH_F)
    n = EARTH_A_KM / math.sqrt(1 - e2 * math.sin(la) ** 2)
    h = alt_m / 1000
    p = np.array([(n + h) * math.cos(la) * math.cos(lo), (n + h) * math.cos(la) * math.sin(lo), (n * (1 - e2) + h) * math.sin(la)])
    up = np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)])
    east = np.array([-math.sin(lo), math.cos(lo), 0.0])
    north = np.cross(up, east)
    return p, up, east, north


def _gmst(jd):
    t = (jd - 2451545.0) / 36525.0
    s = 67310.54841 + (876600.0 * 3600 + 8640184.812866) * t + 0.093104 * t * t - 6.2e-6 * t ** 3
    return np.radians((s % 86400) / 240.0)


def _ecef(arr, times):
    """SatrecArray at the unix times -> err (N, T), r and v (N, T, 3) Earth fixed (km, km/s)."""
    jd = np.asarray(times, float) / 86400.0 + 2440587.5
    ji = np.floor(jd)
    err, r, v = arr.sgp4(ji, jd - ji)
    g = _gmst(jd)
    cg, sg = np.cos(g)[None, :], np.sin(g)[None, :]
    x = cg * r[..., 0] + sg * r[..., 1]
    y = -sg * r[..., 0] + cg * r[..., 1]
    vx = cg * v[..., 0] + sg * v[..., 1] + EARTH_W * y
    vy = -sg * v[..., 0] + cg * v[..., 1] - EARTH_W * x
    return err, np.stack((x, y, r[..., 2]), -1), np.stack((vx, vy, v[..., 2]), -1)


def _look(r, site):
    """Elevation and azimuth (degrees) and range (km) of the positions r (..., 3) from a site."""
    p, up, east, north = site
    d = r - p
    rng = np.linalg.norm(d, axis=-1)
    el = np.degrees(np.arcsin(np.clip((d @ up) / rng, -1, 1)))
    az = np.degrees(np.arctan2(d @ east, d @ north)) % 360
    return el, az, rng


def bistatic_doppler(r, v, tx, rx, f_hz):
    """Doppler (Hz) of the echo from positions r, velocities v (..., 3) between the sites tx and rx (ECEF km)."""
    dt_, dr = r - tx, r - rx
    rate = np.sum(dt_ * v, -1) / np.linalg.norm(dt_, axis=-1) + np.sum(dr * v, -1) / np.linalg.norm(dr, axis=-1)
    return -rate * f_hz / C_KM_S


def identify(pts, qth, tx=(47.348, 5.515), f_hz=143050000.0, elements=None):
    """pts [(t, Hz)] of a satellite track; qth (lat, lon[, alt_m]) of the station ->
    {"norad", "name", "rms", "offset", "az", "el", "km", "others", "curve": [[t, Hz]]} of the best fitting satellite,
    or {"norad": None, "why": text}. elements: (SatrecArray, names, norads) for tests."""
    if not qth:
        return {"norad": None, "why": "the station location is not set (SETUP › LOCATION)"}
    arr, names, norads = elements or _elements()
    if arr is None:
        return {"norad": None, "why": _tle["error"] or "no orbital elements"}
    pts = sorted(pts)
    if len(pts) > ID_POINTS:
        pts = [pts[int(i)] for i in np.linspace(0, len(pts) - 1, ID_POINTS)]
    t = np.array([p[0] for p in pts])
    f = np.array([p[1] for p in pts])
    err, r, v = _ecef(arr, t)
    site_t, site_r = _site(tx[0], tx[1]), _site(*qth)
    el_t, az_t, _ = _look(r, site_t)
    el_r, az_r, km_r = _look(r, site_r)
    fd = bistatic_doppler(r, v, site_t[0], site_r[0], f_hz)
    ok = np.all(err == 0, axis=1) & np.all(el_t > 0, axis=1) & np.all(el_r > 0, axis=1)
    if not ok.any():
        return {"norad": None, "why": "no satellite with orbital elements was over both GRAVES and the station"}
    off = np.median(f[None, :] - fd, axis=1)
    rms = np.sqrt(np.mean((f[None, :] - fd - off[:, None]) ** 2, axis=1))
    mid = len(t) // 2
    inside = ((az_t[:, mid] >= GRAVES_AZ[0]) & (az_t[:, mid] <= GRAVES_AZ[1]) &
              (el_t[:, mid] >= GRAVES_EL[0]) & (el_t[:, mid] <= GRAVES_EL[1]))
    score = np.where(ok & (np.abs(off) <= ID_OFFSET_HZ), rms * np.where(inside, 1.0, ID_OUTSIDE), np.inf)
    i = int(np.argmin(score))
    if not np.isfinite(score[i]) or rms[i] > ID_RMS_HZ:
        j = int(np.argmin(np.where(ok, rms, np.inf)))
        return {"norad": None, "why": f"no orbital elements fit (closest {names[j]}, {rms[j]:.0f} Hz off); debris or an object without public elements",
                "candidates": int(ok.sum())}
    others = int(np.sum(score <= score[i] * 1.3 + 10)) - 1
    return {"norad": int(norads[i]), "name": names[i], "rms": round(float(rms[i]), 1), "offset": round(float(off[i])),
            "az": round(float(az_r[i, mid]), 1), "el": round(float(el_r[i, mid]), 1), "km": round(float(km_r[i, mid])),
            "lit": bool(inside[i]), "others": others, "candidates": int(ok.sum()),
            "curve": [[round(float(a), 2), round(float(b + off[i]), 1)] for a, b in zip(t, fd[i])]}

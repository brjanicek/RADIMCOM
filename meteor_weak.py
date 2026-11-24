"""GRAVES (meteor.py): three detectors for what the spectral detector and the satellite tracker miss. Each can be
switched on in DECODERS › GRAVES › SETTINGS › DETECTOR.

FAST: short underdense pings in the time signal (as in BRAMS: Roelandts et al., "Meteor detection in the BRAMS
  network", Proc. IMC 2014). The meteor detector integrates ~0.25 s (125 ms frames smoothed over 4): a ping of a few
  tens of ms is diluted by that. Here the baseband is mixed to the carrier, filtered to ±FAST_HZ, decimated to
  FAST_RATE and cut into short spectra (FAST_WIN samples every FAST_HOP: a ping that short sums up coherently in one
  ~31 Hz bin, which the plain power of the whole band would not); a ping is a bin FAST_DB over its floor for at least
  FAST_MIN_N frames, and FAST_REF_DB over the same spectra of a reference band FAST_REF_HZ away (broadband impulse
  noise lifts both). Its Doppler: the strongest bin, interpolated.

SAT·TLE: weak satellites along the Doppler their orbital elements predict. Every TLE_STEP_S the satellites lit by
  GRAVES (and over the horizon of the station) during the last seconds are propagated; along the bistatic Doppler
  curve of each (a few receiver offsets around the known one) the unsmoothed ±8 kHz spectrum (each frame value capped
  at CAP, the mean of 3 bins) is summed over its noise level in TLE_BOX_S windows, as a z score. A satellite echo
  raises the sum far over what noise gives; a meteor crossing the curve is too short and capped to. Found: kind
  "sat", the satellite already known.

SAT·LINES: weak streaks in the ±8 kHz spectrum without orbital elements: a Hough (Radon) transform over windows of
  LINE_WIN_S, the same sum along every straight line of LINE_MIN_SLOPE…LINE_MAX_SLOPE Hz/s (a shear: each frame moved
  back by its bins and added), each half of the line also over the noise on its own. Lines of consecutive windows that
  continue each other are joined to a track; a closed track is identified like a track of the tracker
  (meteor_sat.identify).

The searches run in a thread on the unsmoothed frames the wide spectrum keeps (meteor_sat.Spec.raw); what they find
is handed to meteor.py, which reports it in its own thread (with its detail and sound) unless the tracker has it.
"""

import math
import threading
import time

import numpy as np

from meteor_sat import (GRAVES_AZ, GRAVES_EL, SAT_GAP_S, _ecef, _elements, _look, _site, bistatic_doppler)

# ---- FAST ----
FAST_RATE = 1000.0              # the carrier mixed down and decimated to this
FAST_HZ = 150.0                 # the ping band: ±this around the carrier (meteor Doppler)
FAST_TAPS = 63
FAST_WIN = 32                   # short spectra of this many samples (32 ms, ~31 Hz bins: a ping of a few tens of ms
FAST_HOP = 8                    # … sums up coherently in one of them), every this many (8 ms)
FAST_REF_HZ = 500.0             # the reference bands: this far from the carrier on both sides (the stronger counts)
FAST_DB = 11.0                  # a ping: a bin this over its floor … (noise: ~11 bins × 125 frames a second)
FAST_REF_DB = 6.0               # … and this over the reference band (its mean bin) at the same moment
FAST_HYST_DB = 4.0              # it lasts while this much lower
FAST_MIN_N = 3                  # … at least this many frames (a noise spike is one or two)
FAST_GAP_S = 0.016
FAST_SWEEP_BINS = 2              # its strongest bin moving this many bins (~62 Hz) while strong: not a meteor
FAST_MAX_S = 0.8                # longer: left to the meteor detector (and no broadband carrier)
FAST_TAU_S = 5.0                # the floor of each bin: its mean power over this (the quiet frames)
FAST_LEARN_S = 3.0

# ---- SAT·TLE ----
TLE_STEP_S = 15.0               # a search every this …
TLE_WIN_S = 40.0                # … over the frames of the last this
TLE_LAG_S = 6.0                 # … ending this long ago (the tracker closes its tracks first)
TLE_BOX_S = 2.0                 # the sum over the noise along the curve over this
TLE_Z = 10.0                    # z score (thousands of lit satellites × 11 offsets × 1250 frames per search; live
                                # at 7: ~5 a minute, nearly all ~1 dB over the noise = chance fits)
TLE_MIN_DB = 1.5                # and the median level along it (its own bin, _levels; noise alone ~ -0.5 dB)
TLE_HALF_Z = 3.0                # and each half of the run on its own
TLE_OFF_HZ = 24.0               # receiver offsets tried: the known one ± this (the AFC keeps the carrier; more
                                # freedom lets the curve of another satellite fit a streak)
TLE_COARSE_S = 1.0              # the orbit computed every this, interpolated between
TLE_MIN_S = 1.0                 # a run at least this long
TLE_AZ_MARGIN = 15.0            # the sector GRAVES lights, a little wider
TLE_EL_MARGIN = 8.0

# ---- SAT·LINES ----
LINE_STEP_S = 3.0
LINE_WIN_S = 6.0
LINE_LAG_S = 1.0
LINE_MIN_SLOPE = 80.0           # Hz/s: slower is a meteor, an aircraft or the wind (an overdense echo crossed …)
LINE_MAX_SLOPE = 600.0
LINE_PLANE_HZ = 350.0           # slower lines (aircraft: tens of Hz/s) only within this (2 v / λ ≤ ~270 Hz)
LINE_SLOPE_STEP = 6.0
LINE_Z = 8.5                    # over ~250 000 lines per window (noise alone: up to ~7.5)
LINE_HALF_Z = 3.0               # and each half of the line on its own (not one bright spot)
LINE_MAX = 3                    # lines per window
LINE_JOIN_HZ = 120.0            # a line continues a track when it starts this close to where the track points
LINE_MIN_DUR_S = 2.0            # a track at least this long is reported

CAP = 4.0                       # a frame value over the floor counts at most this much (one strong spot is not a line)


def _noise(x):
    """The level and the spread of the noise of x (capped ratios): the median and the standard deviation of the values
    under its 99th percentile (a weak echo hardly moves them; the MAD would understate the spread of this skewed
    distribution and make the z scores too high)."""
    mu = float(np.median(x))
    lo = x[x <= np.percentile(x, 99)]
    return mu, float(np.std(lo)) or 1e-3


def _bins3(x):
    """The mean of each bin and its two neighbours (a curve or line a bin off still counts)."""
    out = x.copy()
    out[:, 1:-1] = (x[:, :-2] + x[:, 1:-1] + x[:, 2:]) / 3
    return out


# ================= FAST =================
class Fast:
    """The time-domain ping detector of one carrier (f_off Hz from the dial) at the baseband rate fs."""

    def __init__(self, fs, f_off):
        from scipy.signal import firwin
        self.fs = float(fs)
        self.dec = max(1, int(round(fs / FAST_RATE)))
        self.rate = self.fs / self.dec
        self.f_off = float(f_off)
        self.bands = (self.f_off, self.f_off + FAST_REF_HZ, self.f_off - FAST_REF_HZ)
        self.ok = all(abs(f) + FAST_HZ < fs / 2 * 0.95 for f in self.bands)
        self.taps = firwin(FAST_TAPS, FAST_HZ + 2 * self.rate / FAST_WIN, fs=self.rate).astype(np.float32)
        self.win = np.hanning(FAST_WIN).astype(np.float32)
        fr = np.fft.fftfreq(FAST_WIN, 1.0 / self.rate)
        sel = np.nonzero(np.abs(fr) <= FAST_HZ + self.rate / FAST_WIN / 2)[0]           # the bins of the ping band …
        self.sel = sel[np.argsort(fr[sel])]                                             # … low -> high
        self.sel_hz = fr[self.sel]
        # how late a sample of the filtered band is after the baseband it comes from (the FIR, the decimation)
        self.delay = (FAST_TAPS - 1) / 2 / self.rate + self.dec / 2 / self.fs
        self.ph = np.zeros(3)                       # mixer phases of the three bands (the ping, the references)
        self.zi = [np.zeros(FAST_TAPS - 1, np.complex64) for _ in range(3)]
        self.buf = np.zeros(0, np.complex64)
        self.ys = [np.zeros(0, np.complex64) for _ in range(3)]       # filtered samples not yet in a whole frame
        self.floor = [None, None, None]             # the mean power of each bin of each band
        self.t_run = 0.0
        self.ev = None

    def _band(self, x, i, f):
        from scipy.signal import lfilter
        n = len(x)
        w = -2 * np.pi * f / self.fs
        rot = np.exp(1j * (self.ph[i] + w * np.arange(n))).astype(np.complex64)
        self.ph[i] = (self.ph[i] + w * n) % (2 * np.pi)
        y = (x * rot).reshape(-1, self.dec).mean(axis=1)
        y, self.zi[i] = lfilter(self.taps, [1.0], y, zi=self.zi[i])
        return y.astype(np.complex64)

    def _frames(self, i, y):
        """The new filtered samples of band i -> the power of its bins in each whole frame (frames × bins)."""
        b = np.concatenate((self.ys[i], y))
        nf = (len(b) - FAST_WIN) // FAST_HOP + 1 if len(b) >= FAST_WIN else 0
        if nf <= 0:
            self.ys[i] = b
            return np.zeros((0, len(self.sel)), np.float32), len(b)
        idx = np.arange(nf)[:, None] * FAST_HOP + np.arange(FAST_WIN)[None, :]
        s = np.fft.fft(b[idx] * self.win, axis=1)[:, self.sel]
        self.ys[i] = b[nf * FAST_HOP:]
        return (s.real ** 2 + s.imag ** 2).astype(np.float32), len(b)

    def feed(self, base, now):
        """base: complex baseband ending at now -> [ping]: {"t0", "t1", "dur", "snr", "dop"} of the pings that ended."""
        if not self.ok:
            return []
        buf = np.concatenate((self.buf, np.asarray(base, np.complex64)))
        g = len(buf) // self.dec
        if not g:
            self.buf = buf
            return []
        x, self.buf = buf[:g * self.dec], buf[g * self.dec:]
        t_last = now - len(self.buf) / self.fs - self.delay          # the time of the last filtered sample
        ps, nb = [], 0
        for i in range(3):
            p, nb = self._frames(i, self._band(x, i, self.bands[i]))
            ps.append(p)
        nf = len(ps[0])
        if not nf:
            return []
        # the middle of each frame: the samples of the last one end nb - nf*HOP - (WIN - HOP) before t_last
        last_end = t_last - (nb - (nf - 1) * FAST_HOP - FAST_WIN) / self.rate
        times = last_end - (nf - 1 - np.arange(nf)) * FAST_HOP / self.rate - FAST_WIN / 2 / self.rate
        dt_blk = nf * FAST_HOP / self.rate
        learning = self.t_run < FAST_LEARN_S
        r = ps[0] / self.floor[0] if self.floor[0] is not None else None
        for i in range(3):              # the floors: the mean of the quiet frames (a ping hardly moves it)
            p = ps[i]
            if self.floor[i] is None:
                self.floor[i] = p.mean(axis=0) + 1e-20
                continue
            if r is not None and not learning:
                q = p[(r.max(axis=1) < 10 ** ((FAST_DB - FAST_HYST_DB) / 10))]
                if not len(q):
                    continue
                m = q.mean(axis=0)
            else:
                m = p.mean(axis=0)
            a = min(1.0, dt_blk / (FAST_TAU_S if not learning else max(self.t_run, dt_blk)))
            self.floor[i] += (m - self.floor[i]) * a
        self.t_run += dt_blk
        if learning or r is None:
            return []
        rb = r.max(axis=1)
        kb = r.argmax(axis=1)
        rr = np.maximum((ps[1] / self.floor[1]).mean(axis=1), (ps[2] / self.floor[2]).mean(axis=1))
        thr, thr_lo, ref = 10 ** (FAST_DB / 10), 10 ** ((FAST_DB - FAST_HYST_DB) / 10), 10 ** (FAST_REF_DB / 10)
        hot = (rb >= thr) & (rb >= ref * np.maximum(rr, 1.0))
        keep = (rb >= thr_lo) & (rb >= np.maximum(rr, 1.0))
        out = []
        if self.ev is None and not hot.any():
            return out
        for i in range(nf):
            ev = self.ev
            if ev is None:
                if hot[i]:
                    self.ev = {"t0": times[i], "t1": times[i], "pk": rb[i], "row": r[i].copy(), "n": 1, "hot": 1,
                               "kmin": int(kb[i]), "kmax": int(kb[i])}
                continue
            if keep[i]:
                ev["t1"] = times[i]
                ev["n"] += 1
                ev["hot"] += int(hot[i])
                if hot[i]:              # where its strongest bin is while it is strong
                    ev["kmin"], ev["kmax"] = min(ev["kmin"], int(kb[i])), max(ev["kmax"], int(kb[i]))
                if rb[i] > ev["pk"]:
                    ev["pk"], ev["row"] = rb[i], r[i].copy()
            elif times[i] - ev["t1"] > FAST_GAP_S:
                self.ev = None
                p = self._close(ev)
                if p:
                    out.append(p)
        return out

    def _close(self, ev):
        dur = float(ev["t1"] - ev["t0"]) + FAST_HOP / self.rate       # the frames over the floor (~the ping)
        # a meteor keeps its Doppler during a ping; a satellite sweeping through the band does not
        if ev["n"] < FAST_MIN_N or dur > FAST_MAX_S or ev["kmax"] - ev["kmin"] >= FAST_SWEEP_BINS:
            return None
        # the Doppler: the strongest bin of the strongest frame, between its neighbours (a parabola of the dB)
        row, k = ev["row"], int(np.argmax(ev["row"]))
        f = float(self.sel_hz[k])
        if 0 < k < len(row) - 1:
            a, b, c = (10 * np.log10(max(float(v), 1e-9)) for v in row[k - 1:k + 2])
            den = a - 2 * b + c
            if den < 0:
                f += 0.5 * (a - c) / den * (self.rate / FAST_WIN)
        return {"t0": float(ev["t0"]), "t1": float(ev["t1"]), "dur": round(dur, 3),
                "snr": round(10 * math.log10(max(ev["pk"], 1e-6)), 1), "dop": round(f, 1)}


# ================= the frames of the wide spectrum =================
def _snapshot(raw, a, b):
    """The unsmoothed frames (t, float16 ratio) of a deque from a to b -> (times, float32 array) or None."""
    for _ in range(5):
        try:
            items = list(raw)
            break
        except RuntimeError:                         # appended while copied: again
            continue
    else:
        return None
    items = [it for it in items if a <= it[0] <= b]
    if len(items) < 10:
        return None
    nb = len(items[-1][1])
    items = [it for it in items if len(it[1]) == nb]
    t = np.array([it[0] for it in items])
    raw = np.stack([it[1] for it in items]).astype(np.float32)
    return t, np.minimum(raw, CAP), raw


def level_db(pts):
    """The level of a weak track: the median of its points' dB (a meteor it crosses does not lift it)."""
    return float(np.median([p[2] for p in pts])) if pts else -99.0


def _levels(pts, t, raw, hz):
    """The points (t, Hz, dB) of a found track with their real level: the capped frames (CAP) only find it, so their dB
    were never over 10·log10(CAP) = 6 dB. Its own bin over three frames (noise alone: ~0 dB on average; not the
    strongest of the bins around, which noise alone lifts to a few dB)."""
    if not pts:
        return pts
    hz = np.asarray(hz, dtype=float)
    out = []
    for p in pts:
        i = int(np.clip(np.searchsorted(t, p[0]), 0, len(t) - 1))
        k = int(np.argmin(np.abs(hz - p[1])))
        blk = raw[max(0, i - 1):i + 2, k]
        v = float(np.mean(blk)) if blk.size else 0.0
        out.append((p[0], p[1], round(10 * math.log10(max(v, 1e-3)), 1)))
    return out


# ================= SAT·TLE =================
class TleSearch:
    def __init__(self):
        self.last = {}                              # norad -> end of the last run found (no second report of it)

    def run(self, t, x, hz, bin_hz, qth, tx, f_hz, offset, elements=None):
        """t (frames), x (frames × bins, ratios over the floor, capped), hz of the bins -> [found]:
        {"norad", "name", "pts": [(t, Hz, dB)], "z", "offset", "az", "el", "km"}."""
        if not qth:
            return []
        arr, names, norads = elements or _elements()
        if arr is None:
            return []
        xs = _bins3(x)
        mu, sd = _noise(xs)
        xc = xs - mu                                    # over the noise: a curve sums to ~0 in noise alone
        site_t, site_r = _site(tx[0], tx[1]), _site(*qth)
        # every satellite every TLE_COARSE_S: lit by GRAVES and over the station's horizon, its Doppler
        tc = np.arange(t[0], t[-1] + TLE_COARSE_S, TLE_COARSE_S)
        err, r, v = _ecef(arr, tc)
        el_t, az_t, _ = _look(r, site_t)
        el_r, az_r, km_r = _look(r, site_r)
        lit = ((az_t >= GRAVES_AZ[0] - TLE_AZ_MARGIN) & (az_t <= GRAVES_AZ[1] + TLE_AZ_MARGIN) &
               (el_t >= GRAVES_EL[0] - TLE_EL_MARGIN) & (el_t <= GRAVES_EL[1] + TLE_EL_MARGIN) & (el_r > 0) & (err == 0))
        keep = np.nonzero(lit.any(axis=1))[0]
        if not len(keep):
            return []
        fd = bistatic_doppler(r[keep], v[keep], site_t[0], site_r[0], f_hz)             # (K, Tc)
        fd_t = np.stack([np.interp(t, tc, f) for f in fd])                              # (K, T)
        lit_t = np.stack([np.interp(t, tc, l.astype(float)) > 0.5 for l in lit[keep]])
        nb, nt = x.shape[1], len(t)
        dt = float(np.median(np.diff(t)))
        box = max(3, int(round(TLE_BOX_S / dt)))
        found, runs = [], []
        offs = offset + np.arange(-TLE_OFF_HZ, TLE_OFF_HZ + 1e-6, bin_hz / 2)
        rows = np.arange(nt)[None, :]

        def boxsum(a):                                  # the sums over box frames centred on each frame
            c = np.concatenate((np.zeros((a.shape[0], 1), a.dtype), np.cumsum(a, axis=1)), axis=1)
            lo = np.clip(np.arange(nt) - box // 2, 0, nt)
            hi = np.clip(np.arange(nt) - box // 2 + box, 0, nt)
            return c[:, hi] - c[:, lo]

        for j, k in enumerate(keep):
            if lit_t[j].sum() < box:
                continue
            # every offset at once: the bins of the curve (offsets × frames), the sum over the noise along it
            idx = np.rint((fd_t[j][None, :] + offs[:, None] - hz[0]) / bin_hz).astype(int)
            okm = lit_t[j][None, :] & (idx >= 1) & (idx < nb - 1)
            v = np.where(okm, xc[rows, np.clip(idx, 0, nb - 1)], 0.0).astype(np.float32)
            s, n = boxsum(v), boxsum(okm.astype(np.float32))
            zz = np.where(n >= box * 0.8, s / (sd * np.sqrt(np.maximum(n, 1))), -99.0)
            oi, m = np.unravel_index(int(np.argmax(zz)), zz.shape)
            if zz[oi, m] < TLE_Z:
                continue
            zmax, off, idx, ok, z = float(zz[oi, m]), float(offs[oi]), idx[oi], okm[oi], zz[oi]
            a = m
            while a > 0 and z[a - 1] >= TLE_Z / 2 and ok[a - 1]:
                a -= 1
            b = m
            while b < nt - 1 and z[b + 1] >= TLE_Z / 2 and ok[b + 1]:
                b += 1
            a, b = max(0, a - box // 2), min(nt - 1, b + box // 2)
            if t[b] - t[a] < TLE_MIN_S:
                continue
            sel = np.array([i for i in range(a, b + 1) if ok[i]])
            h1, h2 = sel[:len(sel) // 2], sel[len(sel) // 2:]
            # each half of the run over the noise on its own: a curve that only crosses a streak or a meteor is not it
            if min(v[oi, h].sum() / (sd * math.sqrt(len(h))) for h in (h1, h2)) < TLE_HALF_Z:
                continue
            runs.append((zmax, int(k), j, off, idx, sel))
        # one streak, one satellite: the curves of others crossing it at the same time give way to the best one
        runs.sort(key=lambda q: -q[0])
        taken = []
        for zmax, gi, j, off, idx, sel in runs:
            f = fd_t[j][sel] + off
            if any(len(np.intersect1d(sel, s2)) > len(sel) / 2 and
                   np.median(np.abs(f[np.isin(sel, s2)] - (fd_t[j2][sel[np.isin(sel, s2)]] + o2))) < 3 * bin_hz
                   for _, _, j2, o2, _, s2 in taken):
                continue
            taken.append((zmax, gi, j, off, idx, sel))
            # another lit satellite whose curve (with an offset of its own) lies on this one over the whole run:
            # which of them it was cannot be told, so it is not reported (better none than a wrong name)
            dif = fd_t[:, sel] - (fd_t[j][sel] + off)[None, :]
            same = ((np.abs(np.median(dif, axis=1)) <= TLE_OFF_HZ + 1.5 * bin_hz) & (np.ptp(dif, axis=1) <= 3 * bin_hz) &
                    lit_t[:, sel].all(axis=1))
            same[j] = False
            if same.any():
                continue
            norad = int(norads[gi])
            a, b = int(sel[0]), int(sel[-1])
            if self.last.get(norad, -1e18) >= t[a] - SAT_GAP_S:
                self.last[norad] = max(self.last[norad], float(t[b]))
                continue
            self.last[norad] = float(t[b])
            pts = [(float(t[i]), float(fd_t[j][i] + off), round(10 * math.log10(max(float(x[i, idx[i]]), 1e-3)), 1))
                   for i in sel]
            mid = int(np.argmin(np.abs(tc - t[(a + b) // 2])))
            found.append({"norad": norad, "name": names[gi], "pts": pts, "z": round(zmax, 1),
                          "offset": round(float(off)), "az": round(float(az_r[gi, mid]), 1),
                          "el": round(float(el_r[gi, mid]), 1), "km": round(float(km_r[gi, mid]))})
        for norad in [n for n, e in self.last.items() if e < t[0] - 3600]:
            del self.last[norad]
        return found


# ================= SAT·LINES =================
class LineSearch:
    def __init__(self):
        self.open = []                              # tracks: {"pts": [(t, Hz, dB)], "slope", "t1"}
        self.done_t = -1e18                         # the end of the last window searched

    def window(self, t, x, hz, bin_hz):
        """One window -> [line]: {"t0", "t1", "f0", "slope", "z", "pts"}."""
        # pairs of frames averaged (half the work, the same lines)
        n2 = len(t) // 2
        if n2 < 8:
            return []
        t2 = (t[:2 * n2:2] + t[1:2 * n2:2]) / 2
        x2 = (x[:2 * n2:2] + x[1:2 * n2:2]) / 2
        xs = _bins3(x2)
        nt, nb = xs.shape
        mu, sd = _noise(xs)
        xc = xs - mu                                   # over the noise: a line sums to ~0 in noise alone
        tt = t2 - t2[0]
        slopes = np.r_[-np.arange(LINE_MAX_SLOPE, LINE_MIN_SLOPE - 1e-6, -LINE_SLOPE_STEP),
                       np.arange(LINE_MIN_SLOPE, LINE_MAX_SLOPE + 1e-6, LINE_SLOPE_STEP),
                       np.arange(-LINE_MIN_SLOPE + LINE_SLOPE_STEP, LINE_MIN_SLOPE - 1e-6, LINE_SLOPE_STEP)]   # slow: aircraft
        plane_k = np.abs(np.asarray(hz)) <= LINE_PLANE_HZ          # … only where an aircraft can be
        half = nt // 2
        zs, ss = [], []
        for s in slopes:
            # the shear: each frame moved back by its bins along the line and added, the halves apart
            sh = np.rint(s * tt / bin_hz).astype(int)
            acc = np.zeros((2, nb), np.float32)
            cnt = np.zeros((2, nb), np.float32)
            for i in range(nt):
                d, h = sh[i], 0 if i < half else 1
                if d >= nb or d <= -nb:
                    continue
                if d >= 0:
                    acc[h, :nb - d] += xc[i, d:]
                    cnt[h, :nb - d] += 1
                else:
                    acc[h, -d:] += xc[i, :nb + d]
                    cnt[h, -d:] += 1
            n = cnt.sum(axis=0)
            z = np.where(n >= nt * 0.6, acc.sum(axis=0) / (sd * np.sqrt(np.maximum(n, 1))), -99.0)
            zh = np.where(cnt >= 4, acc / (sd * np.sqrt(np.maximum(cnt, 1))), -99.0)
            z = np.where((zh[0] >= LINE_HALF_Z) & (zh[1] >= LINE_HALF_Z), z, -99.0)    # not one bright spot
            if abs(s) < LINE_MIN_SLOPE:
                z = np.where(plane_k, z, -99.0)
            zs.append(z)
            ss.append(s)
        zs = np.array(zs)                               # (slopes, start bins)
        lines = []
        for flat in np.argsort(zs, axis=None)[::-1]:
            si, k = divmod(int(flat), nb)
            z = float(zs[si, k])
            if z < LINE_Z or len(lines) >= LINE_MAX:
                break
            if any(abs(si - o[1]) <= 3 and abs(k - o[2]) <= 4 for o in lines):
                continue
            lines.append((z, si, k))
        out = []
        for z, si, k in lines:
            s = float(ss[si])
            idx = k + np.rint(s * tt / bin_hz).astype(int)
            ok = (idx >= 0) & (idx < nb)
            pts = [(float(t2[i]), float(hz[idx[i]]), round(10 * math.log10(max(float(x2[i, idx[i]]), 1e-3)), 1))
                   for i in range(nt) if ok[i] and xs[i, idx[i]] > mu + sd]
            if len(pts) < 4:
                continue
            out.append({"t0": float(t2[0]), "t1": float(t2[-1]), "f0": float(hz[k]), "slope": s, "z": round(z, 1), "pts": pts})
        return out

    def feed(self, lines, t_now):
        """The lines of a window join the open tracks -> the tracks closed now (long enough)."""
        for ln in lines:
            best = None
            for tr in self.open:
                lt, lf = tr["pts"][-1][0], tr["pts"][-1][1]
                if ln["pts"][0][0] - lt > SAT_GAP_S:
                    continue
                # where the track points at the start of the line (or the line at the end of the track)
                f_pred = lf + tr["slope"] * (ln["pts"][0][0] - lt)
                d = min(abs(f_pred - ln["pts"][0][1]),
                        min(abs(p[1] - (ln["f0"] + ln["slope"] * (p[0] - ln["t0"]))) for p in tr["pts"][-5:]))
                if d <= LINE_JOIN_HZ and (best is None or d < best[0]):
                    best = (d, tr)
            if best is None:
                self.open.append({"pts": list(ln["pts"]), "slope": ln["slope"], "z": ln["z"]})
            else:
                tr = best[1]
                last = tr["pts"][-1][0]
                tr["pts"] += [p for p in ln["pts"] if p[0] > last]
                tr["slope"], tr["z"] = ln["slope"], max(tr["z"], ln["z"])
        done = []
        for tr in list(self.open):
            if t_now - tr["pts"][-1][0] > SAT_GAP_S + LINE_WIN_S:
                self.open.remove(tr)
                if tr["pts"][-1][0] - tr["pts"][0][0] >= LINE_MIN_DUR_S:
                    done.append(tr)
        return done


# ================= the thread =================
class WeakWorker:
    """Runs SAT·TLE and SAT·LINES on the frames of the wide spectrum; what it finds goes to out (a list the meteor
    counter takes from its own thread). get() -> (ws, qth, offset, tle on, lines on) or None while there is nothing."""

    def __init__(self, get, out, tx, f_hz, error):
        self.get, self.out, self.tx, self.f_hz, self.error = get, out, tx, f_hz, error
        self.tle, self.lines = TleSearch(), LineSearch()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.t_tle = self.t_line = 0.0
        self.thread = threading.Thread(target=self._loop, daemon=True, name="meteor-weak")
        self.thread.start()

    def _loop(self):
        while not self.stop.wait(0.5):
            try:
                self._step()
            except Exception as e:                     # never stops: the next window again
                self.error(f"meteor weak: {e}")

    def _step(self):
        st = self.get()
        if st is None:
            return
        ws, qth, offset, tle_on, lines_on = st
        if ws is None or ws.raw is None:
            return
        now = time.time()
        if lines_on and now - self.t_line >= LINE_STEP_S:
            self.t_line = now
            b = now - LINE_LAG_S
            snap = _snapshot(ws.raw, b - LINE_WIN_S, b)
            if snap is not None:
                lines = self.lines.window(snap[0], snap[1], ws.hz, ws.bin)
                for ln in lines:
                    ln["pts"] = _levels(ln["pts"], snap[0], snap[2], ws.hz)
                for tr in self.lines.feed(lines, b):
                    with self.lock:
                        self.out.append({"how": "lines", "pts": tr["pts"], "z": tr["z"]})
        elif not lines_on:
            self.lines.open = []
        if tle_on and now - self.t_tle >= TLE_STEP_S:
            self.t_tle = now
            b = now - TLE_LAG_S
            snap = _snapshot(ws.raw, b - TLE_WIN_S, b)
            if snap is not None:
                for f in self.tle.run(snap[0], snap[1], ws.hz, ws.bin, qth, self.tx, self.f_hz, offset):
                    f["pts"] = _levels(f["pts"], snap[0], snap[2], ws.hz)
                    if level_db(f["pts"]) < TLE_MIN_DB:
                        continue        # a chance fit of its curve to the noise
                    with self.lock:
                        self.out.append(dict(f, how="tle"))

    def take(self):
        with self.lock:
            items, self.out[:] = list(self.out), []
        return items

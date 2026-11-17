"""Autotune (ATU key): after a click on a signal in the spectrum or waterfall, the receiver listens to the channel
samples (baseband, 0 Hz = tuned frequency) for a moment and moves the tuning onto the exact carrier.

AM: the carrier is the strongest narrow line near the click; its frequency is measured from a fine FFT (~2 Hz)
with interpolation, so the result is within a few Hz.

SSB (USB / LSB): the ATU key puts the suppressed carrier on the tuned frequency (estimate_ssb_carrier):
a held spectrum of the channel (0.5 s windows, a max-hold falling
0.6 dB a window, so the pauses of speech do not break the shape of the station) smoothed over 250 Hz; the edge of the
voice band on the carrier side where it falls to 40 % of the band's peak height in dB (walking out from its peak, so
splatter and noise under the voice do not pull it), found between bins; the carrier lies CARRIER_TO_EDGE beyond that
edge (fitted on real stations tuned by ear). The carrier then snaps onto a whole kHz within SNAP_KHZ_HZ (SSB stations
sit on whole kHz, e.g. 14.265 MHz), otherwise it is rounded to 100 Hz; the estimate alone is good to about +-70 Hz.
estimate_ssb below finds the carrier from the harmonics of the voice instead (not used by the key now):
  1. Coarse: the averaged spectrum shows the occupied voice band near the click; its lower edge (USB) lies
     ~250 Hz above the carrier (the usual 300–2700 Hz transmitter filter).
  2. Fine: voiced speech has harmonics at exactly c + k·F0 (c = carrier, F0 = pitch). Every short frame gives
     a comb score for each candidate carrier c; F0 changes from frame to frame, so only the true carrier is
     scored well by all of them (a comb shifted by one F0 fits only frames with that particular pitch).
  With no speech (only the edge found) the coarse estimate is used, with nothing found the tuning stays.
LSB is handled as USB on the mirrored spectrum (complex conjugate).
"""
import json
import os
import threading
import time

import numpy as np

MODES = ("AM", "USB", "LSB")
SETTLE_S = 0.25            # skip after retuning: the decimator still holds samples from the old frequency
AM_LISTEN_S = 0.6
SSB_TRIES_S = (2.0, 3.5, 5.0, 6.5)   # SSB: analysed after this much speech-or-not; the last try decides
AM_SEARCH_HZ = 3000.0      # carrier within ± this of the click
SSB_SEARCH_HZ = (-3800.0, 1500.0)    # carrier relative to the click (USB orientation): a click lands on the voice above it,
                                     # wheel tuning leaves it near the tuned frequency
SSB_SPAN_HZ = 4500.0       # analysed band around the click
VOICE_LO, VOICE_HI = 250.0, 2400.0   # harmonics used for the comb, Hz above the carrier
EDGE_TO_CARRIER = 200.0    # voice band lower edge → carrier (coarse estimate)
CAND_BELOW, CAND_ABOVE = 450.0, 20.0   # comb candidates: this far below the voice band edge
F0_MIN, F0_MAX = 75.0, 350.0
FRAME_S = 0.08
# estimate_ssb_carrier
# The numbers are fitted on real SSB stations tuned by ear (data/logs/atu dumps, 40 m LSB, 20 m and 17 m, 2026-11-17): the
# edge at 40 % of the band's peak height in dB, not a few dB over the noise (splatter, skirts and noise under the voice lie
# 4-10 dB over the floor and pulled the edge, and so the carrier, 100-600 Hz too low)
CARRIER_TO_EDGE = 120.0    # the carrier lies this far beyond the edge found in the 250 Hz smoothed held spectrum
EDGE_SMOOTH_HZ = 250.0
EDGE_RUN_DB = 4.0          # a band: over the noise floor by this (gaps up to 400 Hz bridged)
EDGE_FLOOR_DB = 6.0        # the edge at least this far over the floor ...
EDGE_FRAC = 0.4            # ... and at this share of the band's peak height over the floor in dB
EDGE_BRIDGE_HZ = 200.0     # dips under that level bridged while walking down from the band's peak
HOLD_WIN_S = 0.5           # held spectrum: windows of this length, max-hold falling HOLD_DECAY_DB per window
HOLD_DECAY_DB = 0.6
SSB_BW = (800.0, 6000.0)   # width of a band with a voice (and its skirts; narrower: a carrier, a data tone)
ROUND_HZ = 100.0           # the carrier is rounded to this (0 = not)
SNAP_KHZ_HZ = 300.0        # ... or onto a whole kHz when that is this near (SSB stations sit on whole kHz, e.g. 14.265)
# the last DUMP_KEEP analysed blocks with their results are kept here (data/logs/atu, a few MB), to check the ATU on
# real signals (RADIMCOM_ATU_DUMP sets another folder)
try:
    from paths import data as _data
    DUMP_DIR = os.environ.get("RADIMCOM_ATU_DUMP") or _data("logs", "atu")
except Exception:
    DUMP_DIR = os.environ.get("RADIMCOM_ATU_DUMP")
DUMP_KEEP = 8


def _psd(x, fs, nfft):
    """Averaged power spectrum (Hann, 50 % overlap), fftshifted, with its frequency axis."""
    n = len(x)
    seg = min(nfft, n)
    w = np.hanning(seg).astype(np.float32)
    hop = seg // 2
    acc, k = np.zeros(nfft), 0
    for i in range(0, n - seg + 1, hop):
        acc += np.abs(np.fft.fft(x[i:i + seg] * w, nfft)) ** 2
        k += 1
    f = np.fft.fftshift(np.fft.fftfreq(nfft, 1 / fs))
    return f, np.fft.fftshift(acc / max(k, 1))


def _smooth(p, bins):
    bins = max(1, int(bins))
    return np.convolve(p, np.ones(bins) / bins, mode="same")


def estimate_am(x, fs, dc_hz=None):
    """Carrier offset (Hz from the click) of an AM station, or None."""
    nfft = 1 << int(np.ceil(np.log2(fs / 2.0)))            # ~2 Hz bins
    f, p = _psd(x, fs, nfft)
    sel = np.abs(f) <= AM_SEARCH_HZ
    if dc_hz is not None:
        sel &= np.abs(f - dc_hz) > 100                      # the dongle's DC remainder is not a carrier
    if not sel.any():
        return None
    idx = np.flatnonzero(sel)
    i = idx[np.argmax(p[idx])]
    floor = np.median(p[np.abs(f) <= AM_SEARCH_HZ + 2000])
    if p[i] < 30 * floor:                                   # ~15 dB above the surroundings
        return None
    if 0 < i < len(p) - 1:                                  # parabola through the log of the peak and its neighbours
        a, b, c = np.log(p[i - 1] + 1e-30), np.log(p[i] + 1e-30), np.log(p[i + 1] + 1e-30)
        d = a - 2 * b + c
        off = 0.5 * (a - c) / d if d < 0 else 0.0
    else:
        off = 0.0
    return float(f[i] + off * (f[1] - f[0]))


def _voice_band(f, p, df):
    """Occupied band near the click in the averaged spectrum: (lo, hi) Hz, or None."""
    sm = _smooth(p, 60 / df)
    band = np.abs(f) <= SSB_SPAN_HZ
    floor = np.percentile(sm[band], 20)
    on = band & (sm > 2 * floor)                            # 3 dB above the noise
    # close gaps shorter than 400 Hz (the voice spectrum falls off at the top, a notch)
    gap = int(400 / df)
    idx = np.flatnonzero(on)
    if not len(idx):
        return None
    runs, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - prev > gap:
            runs.append((start, prev))
            start = i
        prev = i
    runs.append((start, prev))
    best, score = None, 0.0
    lo_c, hi_c = SSB_SEARCH_HZ
    for a, b in runs:
        lo, hi = f[a], f[b]
        if hi - lo < 400:                                   # a carrier or CW, not a voice
            continue
        if not lo_c + EDGE_TO_CARRIER <= lo <= hi_c + EDGE_TO_CARRIER:
            continue
        e = float(np.sum(sm[a:b + 1] - floor))
        dist = 0.0 if lo <= 0 <= hi else min(abs(lo), abs(hi))
        s = e / (1 + dist / 500)
        if s > score:
            best, score = (float(lo), float(hi)), s
    return best


def _pitch(seg, zdf):
    """Pitch (Hz) and voicing 0..1 of one frame from the autocorrelation of its spectrum (spacing of the harmonics).

    A pitch is scored by the autocorrelation at its multiples minus that at the half-way points, so neither
    half the pitch (every other point between harmonics) nor double the pitch (misses the odd harmonics) wins."""
    seg = seg - seg.mean()
    n = len(seg)
    X = np.fft.rfft(seg, 2 * n)
    ac = np.fft.irfft(np.abs(X) ** 2)[:n]
    if ac[0] <= 0:
        return None, 0.0
    ac = ac / ac[0]
    lags = np.arange(F0_MIN / zdf, F0_MAX / zdf, 0.25)
    if 3 * lags[-1] >= n - 1:
        return None, 0.0

    def r(x):
        i = np.floor(x).astype(int)
        t = x - i
        return ac[i] * (1 - t) + ac[i + 1] * t

    score = (r(lags) + r(2 * lags) + r(3 * lags)) / 3 - (r(0.5 * lags) + r(1.5 * lags) + r(2.5 * lags)) / 3
    j = int(np.argmax(score))
    return float(lags[j] * zdf), float(r(lags[j:j + 1])[0])


def _peaks(s):
    """Indices of the local maxima of s, highest first."""
    i = np.flatnonzero((s[1:-1] >= s[:-2]) & (s[1:-1] > s[2:])) + 1
    return i[np.argsort(s[i])[::-1]]


def estimate_ssb(x, fs, lsb=False):
    """(carrier offset Hz from the click, "comb" | "edge", sure) of an SSB voice signal, or None.

    The offset is in the real spectrum (also for LSB). sure = the comb's best carrier stands clearly above
    the next one (the same voice one pitch step lower or higher); otherwise listening longer helps."""
    if lsb:
        x = np.conj(x)
    sign = -1.0 if lsb else 1.0
    nfft = 1 << int(np.ceil(np.log2(fs / 8.0)))             # ~8 Hz bins
    f, p = _psd(x, fs, nfft)
    df = f[1] - f[0]
    vb = _voice_band(f, p, df)
    if vb is None:
        return None
    lo = vb[0]                                              # where the voice starts: the carrier is just below
    c_edge = lo - EDGE_TO_CARRIER
    top = VOICE_HI

    # Frames: fine spectrum (zero padded to ~3 Hz) of the voice band
    n = int(FRAME_S * fs)
    hop = n // 2
    zf = 1 << int(np.ceil(np.log2(fs / 3.0)))
    w = np.hanning(n).astype(np.float32)
    fr = np.fft.fftfreq(zf, 1 / fs)
    zdf = fs / zf
    lo_f, hi_f = lo - CAND_BELOW - 100, lo + VOICE_HI + 400   # covers every candidate's comb
    kidx = np.flatnonzero((fr >= lo_f) & (fr <= hi_f))
    kidx = kidx[np.argsort(fr[kidx])]
    f0_axis = fr[kidx[0]]
    frames = [np.abs(np.fft.fft(x[i:i + n] * w, zf)[kidx]) ** 2 for i in range(0, len(x) - n + 1, hop)]
    if len(frames) < 4:
        return None
    F = np.array(frames)                                    # (frames, bins), bins from f0_axis in steps of zdf
    energy = F.mean(axis=1)
    noise = np.percentile(energy, 20)
    S = F ** 0.3
    S /= S.mean(axis=1, keepdims=True)
    nb = S.shape[1]

    def at(row, hz):                                        # S at frequencies hz (linear interpolation)
        pos = (hz - f0_axis) / zdf
        i0 = np.clip(np.floor(pos).astype(int), 0, nb - 2)
        t = np.clip(pos - i0, 0, 1)
        return row[i0] * (1 - t) + row[i0 + 1] * t

    # USB has nothing below its carrier, and transmitters pass the voice from ~50–300 Hz above it.
    cands = np.arange(lo - CAND_BELOW, lo - CAND_ABOVE + 1e-9, 2.5)
    lo_c, hi_c = SSB_SEARCH_HZ
    cands = cands[(cands >= lo_c) & (cands <= hi_c)]
    if len(cands) < 3:
        return None
    b0 = max(int((lo + 50 - f0_axis) / zdf), 0)             # pitch from the voice band
    b1 = min(int((lo + top - f0_axis) / zdf), nb)
    total, wsum, voiced = np.zeros(len(cands)), 0.0, 0
    for k in range(len(F)):
        if energy[k] < 2 * noise:
            continue
        f0, v = _pitch(S[k, b0:b1], zdf)
        if f0 is None or v < 0.25:                          # not voiced (noise, hiss, a consonant)
            continue
        # The pitch is refined by the best comb over all candidates, then that one pitch scores every candidate.
        # (A pitch chosen per candidate would bend the comb onto almost any carrier.)
        grid = []
        for g in f0 * (1 + np.linspace(-0.03, 0.03, 31)):
            ks = np.arange(np.ceil(VOICE_LO / g), np.floor(top / g) + 1)
            if len(ks) < 3:
                grid.append(np.full(len(cands), -np.inf))
                continue
            h = cands[:, None] + ks[None, :] * g
            grid.append(at(S[k], h).mean(axis=1) - at(S[k], h - g / 2).mean(axis=1))
        grid = np.array(grid)
        if not np.isfinite(grid).any():
            continue
        row = grid[np.unravel_index(np.argmax(grid), grid.shape)[0]]
        if not np.isfinite(row).all() or row.max() <= 0:
            continue
        total += v * row / row.max()
        wsum += v
        voiced += 1
    if voiced >= 8 and wsum > 0:
        t = total / wsum
        s = np.clip(t, 0, None) * np.exp(-0.5 * ((cands - (lo - 200)) / 250.0) ** 2)
        pk = _peaks(s)
        if len(pk) and t[pk[0]] > 0:
            i = pk[0]
            sure = bool(len(pk) < 2 or s[pk[1]] < 0.75 * s[i])
            off = 0.0
            if 0 < i < len(s) - 1:
                a, b, c = s[i - 1], s[i], s[i + 1]
                d = a - 2 * b + c
                off = 0.5 * (a - c) / d if d < 0 else 0.0
            return sign * float(cands[i] + off * 2.5), "comb", sure
    return sign * float(c_edge), "edge", False


def estimate_ssb_edge(x, fs, lsb=False):
    """(offset Hz from the click, "edge", True) of the voice band edge on the carrier side, or None.

    What the ATU key does in SSB: the visible edge of the signal goes onto the tuned frequency (the red line),
    the lower edge for USB, the upper one for LSB. The offset is in the real spectrum (also for LSB)."""
    if lsb:
        x = np.conj(x)
    nfft = 1 << int(np.ceil(np.log2(fs / 8.0)))             # ~8 Hz bins
    f, p = _psd(x, fs, nfft)
    vb = _voice_band(f, p, f[1] - f[0])
    if vb is None:
        return None
    lo = vb[0] + 30.0                                       # the 60 Hz smoothing in _voice_band widens the band by half of it
    return (-1.0 if lsb else 1.0) * lo, "edge", True


def _held_psd(x, fs, nfft):
    """Max-hold (falling HOLD_DECAY_DB per window) of the HOLD_WIN_S window spectra, smoothed over EDGE_SMOOTH_HZ."""
    win = max(nfft, int(HOLD_WIN_S * fs))
    decay = 10 ** (-HOLD_DECAY_DB / 10)
    held, f = None, None
    for i in range(0, max(len(x) - win, 0) + 1, win):
        f, p = _psd(x[i:i + win], fs, nfft)
        s = _smooth(p, EDGE_SMOOTH_HZ / (f[1] - f[0]))
        held = s if held is None else np.maximum(s, held * decay)
    return f, held


def estimate_ssb_carrier(x, fs, lsb=False):
    """(carrier offset Hz from the click, "carrier", True) of an SSB voice signal near the click, or None.

    The offset is in the real spectrum (also for LSB: there the band is mirrored and its upper edge is used)."""
    if lsb:
        x = np.conj(x)
    nfft = 1 << int(np.ceil(np.log2(fs / 8.0)))             # ~8 Hz bins
    if len(x) < nfft:
        return None
    f, s = _held_psd(x, fs, nfft)
    df = f[1] - f[0]
    db = 10 * np.log10(s + 1e-30)
    floor = float(np.median(db[np.abs(f) > 150]))           # the DC of the channel is not the noise
    gap = int(400 / df)
    br = max(1, int(EDGE_BRIDGE_HZ / df))
    # the bands: stretches a little over the floor, gaps up to 400 Hz bridged (a voice with a strong low formant and
    # weaker highs stays one band; its skirts may join it, the edge below does not follow them)
    idx = np.flatnonzero((np.abs(f) <= SSB_SPAN_HZ) & (db > floor + EDGE_RUN_DB))
    if not len(idx):
        return None
    runs, a, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - prev > gap:
            runs.append((a, prev))
            a = i
        prev = i
    runs.append((a, prev))
    lo_c, hi_c = SSB_SEARCH_HZ
    best, score = None, 0.0
    for a, b in runs:
        if not SSB_BW[0] <= f[b] - f[a] <= SSB_BW[1]:
            continue
        # the edge: walking down from the band's peak while the level stays over EDGE_FRAC of the band's height
        pk = a + int(np.argmax(db[a:b + 1]))
        thr = floor + max(EDGE_FLOOR_DB, EDGE_FRAC * (db[pk] - floor))
        lo, k, ms = pk, pk, 0
        while k > a and ms <= br:
            if db[k - 1] >= thr:
                lo, ms = k - 1, 0
            else:
                ms += 1
            k -= 1
        edge = f[lo]                                          # between bins: where the level passes thr
        if lo > 0 and db[lo] > db[lo - 1]:
            edge = f[lo - 1] + df * (thr - db[lo - 1]) / (db[lo] - db[lo - 1])
        car = edge - CARRIER_TO_EDGE
        if not lo_c <= car <= hi_c:
            continue
        en = float(np.sum(10 ** ((db[a:b + 1] - floor) / 10)))
        dist = 0.0 if f[a] <= 0 <= f[b] else min(abs(f[a]), abs(f[b]))
        sc = en / (1 + dist / 500)
        if sc > score:
            best, score = car, sc
    if best is None:
        return None
    return (-1.0 if lsb else 1.0) * float(best), "carrier", True


class AutoTune:
    """One autotune job at a time: started by a click, fed with baseband by the receiver thread,
    analysed in its own thread; done(new_tune_hz) is called with the result."""

    def __init__(self, done):
        self.done = done
        self.lock = threading.Lock()
        self.job = None
        self.busy = False                       # analysis thread running
        self.n = 0
        self.result = {"id": 0, "state": "", "shift_hz": None, "how": None}

    @property
    def active(self):
        return self.job is not None

    def info(self):
        return dict(self.result)

    def arm(self):
        """A click came in: report "listen" until start() (or an unsupported mode) replaces it."""
        with self.lock:
            self.result = {**self.result, "state": "listen", "id": self.n + 1}

    def start(self, mode, tune_hz, center_hz):
        with self.lock:
            if mode not in MODES:
                self.job = None
                self.result = {**self.result, "state": ""}
                return
            self.n += 1
            self.job = {"id": self.n, "mode": mode, "tune": tune_hz, "center": center_hz, "chunks": [],
                        "len": 0, "skip": None, "try": 0, "t0": time.time()}
            self.result = {"id": self.n, "state": "listen", "shift_hz": None, "how": None, "mode": mode}

    def cancel(self):
        with self.lock:
            if self.job:
                self.result = {**self.result, "state": ""}
            self.job = None

    def feed(self, base, fs, tune_hz, mode):
        job = self.job
        if job is None:
            return
        if tune_hz != job["tune"] or mode != job["mode"]:
            self.cancel()                       # retuned or another mode: the click is no longer valid
            return
        if job["skip"] is None:
            job["skip"] = int(SETTLE_S * fs)
        if job["skip"] > 0:
            drop = min(job["skip"], len(base))
            job["skip"] -= drop
            base = base[drop:]
            if not len(base):
                return
        job["chunks"].append(np.array(base, np.complex64))
        job["len"] += len(base)
        job["fs"] = fs
        if self.busy:
            return
        need = AM_LISTEN_S if mode == "AM" else SSB_TRIES_S[min(job["try"], len(SSB_TRIES_S) - 1)]
        if job["len"] < need * fs:
            return
        last = mode == "AM" or job["try"] >= len(SSB_TRIES_S) - 1
        job["try"] += 1
        x = np.concatenate(job["chunks"])
        job["chunks"], job["len"] = [x], len(x)
        self.busy = True
        threading.Thread(target=self._analyse, args=(job, x, fs, last), name="autotune", daemon=True).start()

    def _analyse(self, job, x, fs, last):
        try:
            try:
                if job["mode"] == "AM":
                    c = estimate_am(x, fs, dc_hz=job["center"] - job["tune"])
                    res = None if c is None else (c, "carrier", True)
                else:
                    res = estimate_ssb_carrier(x, fs, lsb=job["mode"] == "LSB")
            except Exception:                   # never take the receiver down
                res = None
            if DUMP_DIR:
                self._dump(job, x, fs, res, last)
            if (res is None or not res[2]) and not last:
                return                          # a pause, no clear speech yet, or two pitch steps alike: listen longer
        finally:
            self.busy = False
        with self.lock:
            if self.job is not job:
                return
            self.job = None
            if res is None:
                self.result = {**self.result, "state": "none"}
                return
            if job["mode"] == "AM":
                shift = round(res[0])
            elif ROUND_HZ:                      # SSB: the carrier on a round frequency (to ROUND_HZ)
                car = job["tune"] + res[0]
                k = round(car / 1000.0) * 1000.0
                car = k if abs(car - k) <= SNAP_KHZ_HZ else round(car / ROUND_HZ) * ROUND_HZ
                shift = int(car - job["tune"])
            else:
                shift = round(res[0] / 5) * 5
            self.result = {**self.result, "state": "done", "shift_hz": shift, "how": res[1]}
        if shift:
            self.done(job["tune"], job["tune"] + shift)

    @staticmethod
    def _dump(job, x, fs, res, last):
        try:
            os.makedirs(DUMP_DIR, exist_ok=True)
            name = os.path.join(DUMP_DIR, f"atu_{job['id']}_{job['try']}")
            np.save(name + ".npy", x)
            old = sorted((f for f in os.listdir(DUMP_DIR) if f.startswith("atu_") and f.endswith(".npy")),
                         key=lambda f: os.path.getmtime(os.path.join(DUMP_DIR, f)))
            for f in old[:-DUMP_KEEP]:
                for ext in (".npy", ".json"):
                    try:
                        os.remove(os.path.join(DUMP_DIR, f[:-4] + ext))
                    except OSError:
                        pass
            with open(name + ".json", "w") as fh:
                json.dump({"fs": fs, "tune": job["tune"], "mode": job["mode"], "center": job["center"],
                           "res": list(res) if res else None, "last": last}, fh, default=str)
        except Exception:                       # debugging aid only
            pass

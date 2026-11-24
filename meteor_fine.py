"""DECODERS › GRAVES: the fine waterfall, sharp in time and in frequency at once.

A plain spectrum cannot be both: a frame of T seconds resolves ~1/T Hz. Two things together get close:
- the reassignment (Auger & Flandrin, IEEE Trans. SP 1995) moves the power of each bin of each frame to the time and
  frequency where it really is, from two more spectra of the same frame (the window times time, and its derivative):
      f^ = f - Im(X_dh / X_h) * fs / 2pi        t^ = t + Re(X_th / X_h) / fs
  A lone tone then sits on its own frequency to well under a bin, the start of a ping on its own time to a few ms;
- two window lengths (SCALES: a short one sharp in time, a long one that separates tones a few Hz apart), and in each
  cell the smaller of the two (each over its own floor): a cell is lit only where both see power.
The power lands in cells of CELL_S x CELL_HZ; each finished cell is divided by the floor of its row (learned like
the other spectra) and given as uint8 0..full_db dB.
"""
import math

import numpy as np

from meteor_sat import LEARN_S, TAU_HOT_S, TAU_S, db8

CELL_S = 0.016                  # the grid of the waterfall: time …
CELL_HZ = 1.0                   # … and frequency (what the 1 s frames still resolve)
SCALES = ((16, 4, 2, 6.0), (1, 8, 1, 0.0))
# (div, hops, pad, blur_hz): frames of fs / div samples (64 ms and 1 s at 32 kS/s), every 1/hops of a frame (16 and
# 128 ms; ~11 % of a core), the FFT pad times as long (finer bins to move), blur_hz: a triangle of ± this over the
# frequency cells. The
# short frames tell the time only: blurred over about their own resolution their noise is smooth; the long ones tell
# the frequency and stay one cell wide.
LONG_S = 0.1                    # the time of a long frame is known to about ± this: the mean of its cells around
HOT_DB = 9.0                   # a cell this far over its floor learns slowly (a carrier does not become the floor)


class Cols:
    """The columns of a waterfall (uint8 per bin) of the last keep_s seconds, about one every dt, in numpy rings."""

    def __init__(self, keep_s, dt):
        self.size = int(keep_s / dt) + 1
        self.t = np.full(self.size, -np.inf)
        self.a = None
        self.i = 0

    def __len__(self):
        return int(np.count_nonzero(np.isfinite(self.t)))

    def clear(self):
        self.t[:] = -np.inf
        self.a = None
        self.i = 0

    def add(self, t, col):
        col = np.frombuffer(col, np.uint8) if isinstance(col, (bytes, bytearray)) else col
        if self.a is None or self.a.shape[1] != len(col):
            self.clear()
            self.a = np.zeros((self.size, len(col)), np.uint8)
        self.a[self.i] = col
        self.t[self.i] = t
        self.i = (self.i + 1) % self.size

    def since(self, t_from, t_to=np.inf):
        """-> (times, rows) from t_from to t_to, oldest first."""
        idx = np.nonzero((self.t >= t_from) & (self.t <= t_to))[0]
        if self.a is None or not len(idx):
            return np.zeros(0), np.zeros((0, 0), np.uint8)
        idx = idx[np.argsort(self.t[idx], kind="stable")]
        return self.t[idx], self.a[idx]


class Tiered:
    """A waterfall kept twice: every column for the last fine_s seconds (the short views) and the max over coarse_dt
    for the last coarse_s (the long ones, which have fewer screen pixels than columns anyway)."""

    def __init__(self, fine_dt, fine_s, coarse_dt, coarse_s):
        self.fine, self.coarse = Cols(fine_s, fine_dt), Cols(coarse_s, coarse_dt)
        self.fine_dt, self.coarse_dt = fine_dt, coarse_dt
        self.hz = []
        self._max = None
        self._t = -np.inf

    def clear(self):
        self.fine.clear()
        self.coarse.clear()
        self._max = None
        self._t = -np.inf

    def add(self, t, col, coarse_col=None):
        """col: the fine column; coarse_col: what goes into the max of the coarse one (default the same)."""
        col = np.frombuffer(col, np.uint8) if isinstance(col, (bytes, bytearray)) else col
        cc = col if coarse_col is None else (
            np.frombuffer(coarse_col, np.uint8) if isinstance(coarse_col, (bytes, bytearray)) else coarse_col)
        self.fine.add(t, col)
        self._max = cc.copy() if self._max is None or len(self._max) != len(cc) else np.maximum(self._max, cc)
        if t - self._t >= self.coarse_dt:
            self.coarse.add(t, self._max)
            self._max = None
            self._t = t

    def pick(self, b):
        """The tier for columns of b seconds -> (Cols, its column time)."""
        return (self.fine, self.fine_dt) if b < self.coarse_dt else (self.coarse, self.coarse_dt)


class _Scale:
    """One window length: reassigned power -> finished cells over their floor."""

    def __init__(self, fs, f_off, band, nf, div, hops, pad, blur_hz):
        n = 1 << int(round(math.log2(max(256.0, fs / div))))
        k = int(round(blur_hz / CELL_HZ))
        tri = np.r_[np.arange(1, k + 2), np.arange(k, 0, -1)].astype(float) if k else None
        self.kernel = tri / tri.sum() if k else None
        self.fs, self.band, self.nf, self.n, self.hop, self.nfft = fs, band, nf, n, max(1, n // hops), pad * n
        k = np.arange(n)
        h = np.hanning(n)
        self.h = h.astype(np.float32)
        self.th = ((k - (n - 1) / 2) * h).astype(np.float32)
        self.dh = np.gradient(h).astype(np.float32)
        self.freqs = np.fft.fftfreq(self.nfft, 1.0 / fs)
        self.f_off = f_off
        self._select()
        self.buf = np.zeros(0, np.complex64)
        self.acc = {}                   # time cell -> power per frequency cell
        self.done = None                # the cells up to this one were given out
        self.floor = None
        self.learn = 0.0

    def _select(self):
        f = self.freqs
        self.sel = np.nonzero(np.abs(f - self.f_off) <= self.band + 2 * self.fs / self.n)[0]   # a little over: power moves in
        self.f_sel = (f[self.sel] - self.f_off).astype(np.float64)

    def retune(self, f_off):
        """The carrier moved (AFC): the floor and the cells being filled move with it by whole cells."""
        sh = int(round((f_off - self.f_off) / CELL_HZ))
        self.f_off = f_off
        self._select()
        if not sh:
            return

        def roll(a):
            r = np.roll(a, -sh)
            if sh > 0:
                r[-sh:] = a[-1]
            else:
                r[:-sh] = a[0]
            return r
        if self.floor is not None:
            self.floor = roll(self.floor)
        for c in self.acc:
            self.acc[c] = roll(self.acc[c])

    def feed(self, base, now):
        """-> [(cell, ratio over the floor)] of the finished cells (none while the floor is learned)."""
        buf = np.concatenate((self.buf, base))
        n, hop, fs = self.n, self.hop, self.fs
        nfr = (len(buf) - n) // hop + 1 if len(buf) >= n else 0
        if nfr <= 0:
            self.buf = buf
            return []
        seg = buf[np.arange(nfr)[:, None] * hop + np.arange(n)]
        xh = np.fft.fft(seg * self.h, self.nfft, axis=1)[:, self.sel]
        xd = np.fft.fft(seg * self.dh, self.nfft, axis=1)[:, self.sel]
        xt = np.fft.fft(seg * self.th, self.nfft, axis=1)[:, self.sel]
        self.buf = buf[nfr * hop:]
        p = np.abs(xh) ** 2
        med = np.median(p, axis=1, keepdims=True)
        ok = (p > 1e-20) & (med > 0)
        q = np.where(ok, xh, 1.0)
        fh = self.f_sel[None, :] - np.imag(xd / q) * fs / (2 * np.pi)
        tc = now - (len(buf) - np.arange(nfr) * hop - n / 2) / fs           # the middle of each frame
        th = tc[:, None] + np.real(xt / q) / fs
        pn = p / np.maximum(med, 1e-30)
        # power moves in time only within its own frame (further out it is noise), so a cell is finished half a frame
        # after its time
        keep = ok & (np.abs(fh) <= self.band + CELL_HZ / 2) & (np.abs(th - tc[:, None]) <= n / (2 * fs))
        ti = np.floor(th[keep] / CELL_S).astype(np.int64)
        fi = np.clip(np.rint((fh[keep] + self.band) / CELL_HZ).astype(np.int64), 0, self.nf - 1)
        w = pn[keep]
        for t_cell in np.unique(ti):
            m = ti == t_cell
            row = self.acc.get(int(t_cell))
            if row is None:
                row = self.acc[int(t_cell)] = np.zeros(self.nf)
            np.add.at(row, fi[m], w[m])
        # a cell is finished when no frame still to come can move power into it
        last = int(math.floor((tc[-1] - n / (2 * fs)) / CELL_S)) - 1
        if self.done is None:
            self.done = min(self.acc) - 1 if self.acc else last
        out = []
        thr = 10 ** (HOT_DB / 10)
        for c in range(self.done + 1, last + 1):
            row = self.acc.pop(c, None)
            if row is None:
                row = np.zeros(self.nf)
            if self.kernel is not None:
                row = np.convolve(row, self.kernel, "same")
            if self.floor is None:
                self.floor = np.maximum(row, 1e-9)
            self.learn += CELL_S
            learning = self.learn < LEARN_S
            ratio = row / np.maximum(self.floor, 1e-9)
            tau = self.learn if learning else np.where(ratio >= thr, TAU_HOT_S, TAU_S)
            self.floor += (np.maximum(row, 1e-9) - self.floor) * (CELL_S / tau)
            if not learning:
                out.append((c, ratio))
        self.done = max(self.done, last)
        for c in [c for c in self.acc if c <= self.done]:                 # late power of cells already given out
            del self.acc[c]
        return out


class Fine:
    def __init__(self, fs, f_off, band, full_db):
        self.full_db = full_db
        self.nf = int(round(2 * band / CELL_HZ)) + 1
        self.hz = [round(-band + i * CELL_HZ, 1) for i in range(self.nf)]
        self.scales = [_Scale(fs, f_off, band, self.nf, *s) for s in SCALES]
        self.rows = [{} for _ in self.scales]
        self.done = None

    def retune(self, f_off):
        """The carrier moved (AFC): goes on around the new one without learning the floor again."""
        for sc in self.scales:
            sc.retune(f_off)

    def feed(self, base, now):
        """-> [(t, bytes)] of the cells all scales have finished (t = the middle of the cell: rounded it stays in
        its cell). The longer scales tell the frequency, not the time: each counts with the mean of its cells within
        ±LONG_S."""
        L = max(1, int(round(LONG_S / CELL_S)))
        for sc, rows in zip(self.scales, self.rows):
            rows.update(sc.feed(base, now))
        if not all(self.rows):
            return []
        short, longs = self.rows[0], self.rows[1:]
        top = min([max(short)] + [max(r) - L for r in longs])
        out = []
        for c in sorted(k for k in short if k <= top and (self.done is None or k > self.done)):
            if not all(c - L >= min(r) or c in r for r in longs):
                continue                # a longer scale started later (learned its floor later)
            parts = [short[c]]
            for r in longs:
                near = [r[k] for k in range(c - L, c + L + 1) if k in r]
                parts.append(np.mean(near, axis=0))
            out.append(((c + 0.5) * CELL_S, db8(np.minimum.reduce(parts), self.full_db)))
            self.done = c
        if self.done is not None:       # keep only what the next cells still need
            for r in self.rows:
                for k in [k for k in r if k < self.done - L]:
                    del r[k]
        return out

"""AGC+ linearity check: intermodulation of the tuner seen from the spectrum of the whole band across a gain step.

Smart clipping (gainctl.SmartAgc._smart) judges the gain by the clipping of the A/D only. The analogue front end of
an R820T (LNA, mixer) makes intermodulation before the A/D, without one sample clipping: phantom stations where
there are none (2026-11-22, VFO A, 4049.4 kHz AM at 25.4 dB: a phantom AM station with FT8 in it; stepping the gain
down it fell 8.5 dB for 3.2 dB of gain and 9.7 dB for 3.1 dB with the clipping at 0, gone at 12.5 dB; between 25.4
and 22.9 dB it did not move at all, the front end was in compression).

A real signal moves with the gain one to one. A third-order product moves about three times as much, and one from a
front end in compression hardly moves. So the spectra at two neighbouring gains are compared line by line:

* each gain gets a mean spectrum of AVG_S seconds (blocks still carrying the old gain are left out); the spectrum is
  pooled (the strongest of POOL bins), the band edges (the dongle's filter) are left out;
* only steady lines count: each gain keeps its last two mean spectra and a line must stay within STEADY_DB between
  them at both gains (on the air 2026-11-22 FT8 signals, on in one 15 s cycle and off in the next, and speech came out
  as "intermodulation"; carriers, real or phantom, are steady);
* the lines: local maxima PROM_DB over the floor around them (a low percentile of 64 pooled bins) at the higher gain;
* the real step: the median of how much the lines moved (the tuner table is off by 1-2 dB, more at low steps); with
  too few lines the nominal step;
* a line that moved more than FAST x the step (+ TOL_DB) or less than SLOW x the step is non-linear;
  MIN_BAD of them make the step "intermodulation" (one line may just have faded in that second).
"""
import math

import numpy as np

POOL = 8              # pooled bins (WF_FFT 32768 at 2.048 MS/s: ~500 Hz)
EDGE = 0.1            # share of the band left out at each edge
AVG_S = 0.6           # s of blocks per mean spectrum
PROM_DB = 10.0        # a line: this much over the floor around it
MAX_LINES = 60
MIN_LINES = 4         # lines needed to measure the real step
FAST, SLOW = 1.8, 0.4 # slope limits of a linear line (x the real step)
TOL_DB = 1.5
MIN_BAD = 3
MIN_STEP_DB = 1.5     # a smaller step tells nothing
CHECK_DB = 3.0        # a check step down is at least this big (more tuner steps when they are small; on the air
                      # 2026-11-22 22.9 -> 20.7 dB came out "linear" while the phantom played, 22.9 -> 19.7 did not)
STEADY_DB = 1.0       # a line that changed more than this between two means of one gain is not used
STRONG_N = 10         # the strongest pooled bins: the level of the stations that drive the intermodulation
QUIET_DB, QUIET_S = 6.0, 10.0   # they fell this much (products of the third order ~3x as much) for so long: the
                                # ceiling under the intermodulation goes at once


def pooled(power):
    """The spectrum without its edges, the strongest of each POOL bins."""
    n = len(power)
    a = int(n * EDGE)
    p = power[a:n - a]
    m = len(p) // POOL * POOL
    return p[:m].reshape(-1, POOL).max(axis=1)


def floor_db(db, chunk=64, q=30):
    """The floor around each pooled bin: a low percentile of its chunk."""
    m = len(db) // chunk * chunk
    f = np.percentile(db[:m].reshape(-1, chunk), q, axis=1)
    f = np.repeat(f, chunk)
    return np.concatenate((f, np.full(len(db) - m, f[-1] if len(f) else 0.0)))


def compare(hi, lo, nominal_db, steady=None):
    """hi, lo: mean pooled spectra (dB) at the higher and the lower gain; steady: a mask of the bins whose level held
    still at both gains (None = all). -> {step_db, lines, bad: [(i, moved, kind)], imd}: the real step, how many lines
    were looked at, the non-linear ones and whether it is intermodulation."""
    fl = floor_db(hi)
    prom = hi - fl
    peak = np.ones(len(hi), bool)
    for k in (1, 2):                            # a local maximum over ±2 pooled bins
        peak[k:] &= hi[k:] >= hi[:-k]
        peak[:-k] &= hi[:-k] >= hi[k:]
    if steady is not None:
        peak &= steady
    idx = np.flatnonzero(peak & (prom >= PROM_DB))
    idx = idx[np.argsort(prom[idx])[::-1][:MAX_LINES]]
    moved = hi[idx] - lo[idx]
    step = float(np.median(moved)) if len(idx) >= MIN_LINES else float(nominal_db)
    out = {"step_db": round(step, 1), "lines": int(len(idx)), "bad": [], "imd": False}
    if len(idx) >= MIN_LINES and nominal_db >= MIN_STEP_DB and step < SLOW * nominal_db:
        # the whole band hardly moved for a real step: the front end is in compression (2026-11-22, VFO A: 0.5 dB
        # for 25.4 -> 22.9 dB with a phantom AM station and CW playing; the table is never off by that much)
        out["bad"] = [(int(i), round(float(d), 1), "slow") for i, d in zip(idx, moved) if d < SLOW * nominal_db]
        out["imd"] = out["compressed"] = True
        return out
    if step < MIN_STEP_DB:
        return out
    fast = moved > FAST * step + TOL_DB
    slow = moved < SLOW * step                  # (no tolerance: the phantom of 2026-11-22 moved 0 dB on a 2.5 dB step)
    out["bad"] = [(int(i), round(float(d), 1), "fast" if f else "slow")
                  for i, d, f, s in zip(idx, moved, fast, slow) if f or s]
    out["imd"] = len(out["bad"]) >= MIN_BAD
    return out


class Linearity:
    """Mean spectra per gain, fed every block by the receiver (sdr.Receiver._agc_block)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.key = None                         # (centre, rate): a retune makes the spectra of no use
        self.gain = None
        self.sum, self.n, self.dur = None, 0, 0.0
        self.done = {}                          # gain -> [(mean pooled spectrum dB, time it was complete)], the last 2
        self.fs = self.lo_edge = 0.0
        self.size = 0

    def feed(self, power, gain, t, block_s, settling, center, fs):
        key = (round(center), round(fs))
        if key != self.key:
            self.reset()
            self.key = key
        if gain != self.gain:
            self.gain, self.sum, self.n, self.dur = gain, None, 0, 0.0
        if settling or power is None:
            return
        x = pooled(power)
        self.size, self.fs, self.lo_edge = len(power), fs, center - fs / 2
        self.sum = x.astype(np.float64) if self.sum is None else self.sum + x
        self.n += 1
        self.dur += block_s
        if self.dur >= AVG_S:
            w = self.done.setdefault(gain, [])
            w.append((10 * np.log10(self.sum / self.n + 1e-30), t))
            del w[:-2]
            self.sum, self.n, self.dur = None, 0, 0.0

    def ready(self, gain, since):
        """Two mean spectra of this gain, both completed at or after since."""
        w = self.done.get(gain, [])
        return len(w) == 2 and w[0][1] >= since

    def compare(self, g_hi, g_lo, nominal_db):
        (h1, _), (h2, _) = self.done[g_hi]
        (l1, _), (l2, _) = self.done[g_lo]
        lo = (l1 + l2) / 2
        # at the lower gain a phantom may have sunk into the noise, which is not steady: only a line still standing
        # out there has to hold still there too
        sunk = lo - floor_db(lo) < PROM_DB / 2
        steady = (np.abs(h1 - h2) < STEADY_DB) & ((np.abs(l1 - l2) < STEADY_DB) | sunk)
        return compare((h1 + h2) / 2, lo, nominal_db, steady)

    def strong(self, gain):
        """The level of the strongest lines (dB, the mean of the top STRONG_N pooled bins) in the newest mean spectrum
        of this gain, None without one."""
        w = self.done.get(gain)
        if not w:
            return None
        x = w[-1][0]
        return float(np.mean(np.sort(x)[-STRONG_N:]))

    def hz(self, i):
        """The frequency of a pooled bin."""
        if not self.size:
            return 0.0
        bin_hz = self.fs / self.size
        return self.lo_edge + (int(self.size * EDGE) + (i + 0.5) * POOL) * bin_hz

    def describe(self, res):
        """A short text of a result for the AGC+ line."""
        bad = res["bad"]
        if res.get("compressed"):
            return (f"intermodulation: the front end is in compression, {res['lines']} lines moved "
                    f"{res['step_db']:.1f} dB for the whole step")
        fast = [b for b in bad if b[2] == "fast"]
        where = ", ".join(f"{self.hz(i) / 1e6:.4f}" for i, _d, _k in sorted(bad, key=lambda b: -abs(b[1]))[:3])
        kind = "grew too fast" if len(fast) >= len(bad) / 2 else "did not move (compression)"
        return (f"intermodulation: {len(bad)} of {res['lines']} lines {kind} for a {res['step_db']:.1f} dB step"
                + (f" ({where} MHz)" if where else ""))


def _selftest():
    rng = np.random.default_rng(0)
    n = 32768
    base = 1e-9 * rng.exponential(size=n)
    for i in rng.integers(4000, 28000, 30):
        base[i] += 1e-6
    lo = base.copy()
    hi = base * 10 ** (3 / 10)
    for i in (9000, 15000, 21000):            # three products: +9 dB for a 3 dB step
        lo[i] += 3e-8
        hi[i] += 3e-8 * 10 ** (9 / 10)
    r = compare(10 * np.log10(pooled(hi)), 10 * np.log10(pooled(lo)), 3.0)
    return r, math.isclose(r["step_db"], 3.0, abs_tol=0.5)


if __name__ == "__main__":
    print(_selftest())

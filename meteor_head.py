"""A weak head echo before a meteor trail echo: a faint fast sweep, too weak for its points to stand out one by one.

The head echo is the reflection from the meteoroid itself; its Doppler sweeps at v^2 / (lambda R) (~0.4 to tens of
kHz/s, meteor_phys.HEAD_RATE_MIN) and passes the Doppler of the trail at the specular point, where the trail echo
starts. So it is a straight line (over its short time) in the time-frequency plane that ends at a known point: the
trail's Doppler at about the start of the echo. Only the lines through that point are searched.

The detection integrates the power along each such line (incoherent integration, track-before-detect: the Hough /
Radon transform of the spectrogram restricted to lines through one point; Carlson, Evans & Wilson, IEEE Trans. AES 30,
1994, 102-125; Tonissen & Evans, IEEE Trans. AES 32, 1996, 1440-1451) and compares it with the noise measured just
before, where there is no head echo (the mean and spread of the cells there: CFAR). The power is the plain ratio over
the floor of each cell (not clipped, not in dB: the energy detector). The slopes are dense enough that a line is never
more than half a bin off a straight head echo over HEAD_SPAN_HZ. A line is a head echo when its mean is HEAD_Z
standard errors over the noise; HEAD_Z is set on the noise alone with all the lines tried (the maximum over them: the
false alarms per echo, tests/test_meteor_head.py).

The bins near the trail's own Doppler (skip_hz) are left out: the trail echo spreads over the short frames there.
"""
import math

import numpy as np

import meteor_phys as mp

HEAD_RATE_TOP = 80000.0                 # Hz/s, the fastest slope tried
HEAD_SPAN_HZ = 2500.0                   # a line runs at most this far from the trail's Doppler …
HEAD_MAX_S = 0.5                        # … and at most this long before its end
HEAD_END_S = (-0.3, 0.12)               # the line ends at the trail's Doppler this long before … after the echo start
HEAD_MIN_PTS = 4                        # frames on the line (away from the trail) at least
HEAD_NULL_GAP_S = 0.45                  # the noise: the cells at least this long before the echo start …
HEAD_NULL_MIN = 12                      # … in at least this many frames
HEAD_Z = 9.5                            # standard errors over the noise, the maximum over all the lines on noise alone
                                        # (16 and 32 kS/s, 1240 echoes each): 99 % under 8.4, 99.9 % under 9.3
HEAD_Z_DB8 = 12.0                       # the same for a kept detail (clipped at 0 dB, from_db8): 99 % under 9.8,
                                        # 99.9 % under 11.5, at most 11.9 of 2480


def slopes(bin_hz, dt):
    """The slopes tried (Hz/s, both ways): geometric, each next one moves the far end of the line by at most half a
    bin (over HEAD_SPAN_HZ or HEAD_MAX_S, whichever is reached first)."""
    out, s = [], mp.HEAD_RATE_MIN
    while s <= HEAD_RATE_TOP:
        out.append(s)
        reach = min(HEAD_SPAN_HZ, s * HEAD_MAX_S)          # Hz the line spans
        s *= 1.0 + 0.5 * bin_hz / reach
    a = np.array(out)
    return np.concatenate((a, -a))


def from_db8(t0, dt, n, nb, rows, full_db):
    """The kept head echo spectrum of a detail (n frames of nb uint8 bytes, 0..full_db dB over the floor, the first
    ending at t0) -> rows [(t, power over the floor)] for weak(..., z_min=HEAD_Z_DB8): clipped at 0 dB."""
    a = np.frombuffer(rows, np.uint8)[:n * nb].reshape(-1, nb).astype(np.float32) * (full_db / 255.0)
    return [(t0 + i * dt, 10.0 ** (r / 10.0)) for i, r in enumerate(a)]


def weak(rows, hz, dt, bin_hz, t_echo, dop, skip_hz, z_min=None):
    """rows [(t, power over the floor per bin)] of the head echo spectrum (hz: its bins, frames every dt) around an
    echo starting at t_echo at the Doppler dop -> {"slope" Hz/s, "f0", "f1" Hz, "t" s before the echo, "z", "weak": True}
    of the best line through (end, dop), or None. z_min: the threshold (HEAD_Z for the plain power; HEAD_Z_DB8 for
    the clipped power of a kept detail, from_db8)."""
    z_min = HEAD_Z if z_min is None else z_min
    nb = len(hz)
    rows = [(t, r) for t, r in rows if len(r) == nb]
    if len(rows) < 2 * HEAD_MIN_PTS:
        return None
    times = np.array([t for t, _ in rows])
    a = np.stack([np.asarray(r, np.float32) for _, r in rows])
    T = len(rows)
    end = np.nonzero((times >= t_echo + HEAD_END_S[0]) & (times <= t_echo + HEAD_END_S[1]))[0]
    null = times <= t_echo - HEAD_NULL_GAP_S
    if not len(end) or null.sum() < HEAD_NULL_MIN:
        return None
    # the noise of one cell: from all the cells before the head echo could be (away from the trail's Doppler)
    ref = a[null][:, np.abs(hz - dop) >= skip_hz]
    mu, sd = float(np.mean(ref)), float(np.std(ref))
    if sd <= 0:
        return None
    K = int(HEAD_MAX_S / dt) + 1
    ks = np.arange(K)
    S = slopes(bin_hz, dt)
    f = dop + S[:, None] * ks[None, :] * dt                         # (S, K): earlier frames further from the trail
    ok = (np.abs(f - dop) >= skip_hz) & (np.abs(f - dop) <= HEAD_SPAN_HZ) & (f >= hz[0]) & (f <= hz[-1])
    b = np.clip(np.round((f - hz[0]) / bin_hz).astype(int), 0, nb - 1)
    n = ok.sum(axis=1)
    use = n >= HEAD_MIN_PTS
    S, ok, b, n = S[use], ok[use], b[use], n[use]
    if not len(S):
        return None
    tj = end[:, None] - ks[None, :]                                  # (E, K) the frame of each step back
    inside = tj >= 0
    tjc = np.clip(tj, 0, T - 1)
    # a[frame, bin] for every end, slope and step: (E, S, K)
    v = a[tjc[:, None, :], b[None, :, :]]
    m = ok[None, :, :] & inside[:, None, :]
    full = (m.sum(axis=2) == n[None, :])                             # the whole line inside the kept frames
    mean = np.where(m, v, 0.0).sum(axis=2) / n[None, :]
    z = np.where(full, (mean - mu) / (sd / np.sqrt(n[None, :])), -np.inf)
    e, s = np.unravel_index(int(np.argmax(z)), z.shape)
    best = float(z[e, s])
    if not math.isfinite(best) or best < z_min:
        return None
    kv = ks[ok[s]]
    j = int(end[e])
    sl = float(S[s])
    return {"slope": round(-sl), "f0": round(dop + sl * kv[-1] * dt), "f1": round(dop + sl * kv[0] * dt),
            "t": round(float(t_echo - times[j - kv[-1]]), 2), "z": round(best, 1), "weak": True}

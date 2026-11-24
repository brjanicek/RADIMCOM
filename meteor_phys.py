"""The physics behind telling meteors, satellites and aircraft apart on the GRAVES carrier (meteor.py, meteor_sat.py).

All three are seen the same way: the 143.050 MHz carrier scattered towards us, a line in the spectrum. What tells them
apart is how its Doppler can move, bounded by the physics of each target, and measured with a known uncertainty.

Bistatic Doppler (transmitter T, receiver R, target at ranges R_T, R_R; Willis, "Bistatic Radar", 2005, ch. 3;
Skolnik, "Radar Handbook", 3rd ed., ch. 23):

    f_D = -(1/lambda) * d(R_T + R_R)/dt,        |f_D| <= (2 v / lambda) * cos(beta / 2) <= 2 v / lambda

and its rate (the "drift" of the line), for a target moving straight at speed v:

    df_D/dt = -(1/lambda) * (d2R_T/dt2 + d2R_R/dt2),     d2R/dt2 = v_perp^2 / R   (v_perp: across the line of sight)

lambda = c / 143.05 MHz = 2.096 m.

Meteor trail (McKinley, "Meteor Science and Engineering", 1961, ch. 8-9; Ceplecha et al., Space Sci. Rev. 84, 1998,
327-471): the trail is formed within ~0.1 s (the meteoroid crosses the first Fresnel zone) and then drifts with the
neutral wind at 80-110 km. So:
  - the echo rises at once (the Fresnel zone time, tens of ms; here limited by the detector's own smoothing);
  - an underdense echo decays exponentially, amplitude ~ exp(-t / tau), tau = lambda^2 sec^2(phi) / (32 pi^2 D)
    (D the ambipolar diffusion coefficient, 1-10 m^2/s at 90 km; phi half the forward-scatter angle): its power falls
    on a straight line in dB;
  - its Doppler is the wind's: |f_D| <= 2 u cos(beta/2) / lambda, u <= ~100 m/s -> <= ~95 Hz, and it changes slowly:
    the wind does not change within seconds, only an overdense trail twisted by wind shear moves (observed here up to
    ~17 Hz/s). A head echo (the meteoroid itself, 11-72 km/s) sweeps kHz in a fraction of a second BEFORE the trail.

Aircraft (v <= ~300 m/s with a tail wind at cruise): |f_D| <= 2 * 300 / 2.096 = ~290 Hz, and the rate is small:
v^2 / R with R >= ~10 km (the nearest an aircraft is to the receiver or GRAVES) gives <= 9 m/s^2, a turn adds ~3 m/s^2
(25 degrees of bank): (9 + 3) / 2.096 -> <= ~6 Hz/s, usually well under 1 Hz/s. It is there for tens of seconds to
minutes and comes up gradually (it is there, weak, before its strong part).

LEO satellite (v ~7.5 km/s, slant ranges 500-3000 km from GRAVES and from here): near the carrier (|f_D| small: at its
closest approach to the bistatic ellipse) the rate is v^2 / lambda * (1/R_T + 1/R_R) >= 7500^2 / 2.096 * 2 / 3e6
= ~18 Hz/s, and usually tens to hundreds of Hz/s; far from it |f_D| is up to v / lambda * 2 = ~7 kHz. A satellite
crossing the meteor band therefore always drifts at >= SAT_RATE_MIN; a meteor trail or an aircraft never does.

The drift is measured on a line quantised to the detector's bins and smoothed over a few frames, so its uncertainty is
known: the standard error of the slope (Theil-Sen, robust to odd points) with the residual floored at the quantisation noise
(bin / sqrt(12)) and the points counted as independent only once per correlation time of the detector. A class is
given by the drift only when the drift is beyond the bound by two standard errors (~97.5 % one-sided).

When an echo is too short to measure its drift (a short ping), the only way it can be a piece of a satellite is that
it lies where the satellite's line is expected. A meteor may lie there by chance; how likely that is, is known from the
station's own meteors (their rate and their Doppler distribution, learnt live): the Bayes factor of the two hypotheses
(Jeffreys, "Theory of Probability", 1961; Kass & Raftery, JASA 90, 1995, 773-795) decides, not a fixed window.
"""
import bisect
import collections
import math

import numpy as np

C_M_S = 299792458.0
F_HZ = 143050000.0
LAMBDA_M = C_M_S / F_HZ                 # 2.096 m

# aircraft
AIR_V_MAX = 300.0                       # m/s, cruise with a tail wind
AIR_DOP_MAX = 2.0 * AIR_V_MAX / LAMBDA_M          # ~286 Hz: an aircraft is never further off the carrier
AIR_ACC_MAX = 12.0                      # m/s^2: v^2/R at 10 km + a turn
AIR_RATE_MAX = AIR_ACC_MAX / LAMBDA_M             # ~5.7 Hz/s

# satellite (LEO)
SAT_V = 7500.0                          # m/s
SAT_R_MAX = 3.0e6                       # m, the furthest slant range GRAVES sees a satellite at (with both paths)
SAT_RATE_MIN = SAT_V ** 2 / LAMBDA_M * (2.0 / SAT_R_MAX)   # ~17.9 Hz/s at the closest approach, more elsewhere
SAT_R_T_MIN, SAT_R_R_MIN = 5.0e5, 4.0e5                    # m, the nearest a satellite lit by GRAVES is to it / to us
SAT_RATE_MAX = SAT_V ** 2 / LAMBDA_M * (1 / SAT_R_T_MIN + 1 / SAT_R_R_MIN)   # ~121 Hz/s: no satellite sweeps faster

# meteor head echo: the meteoroid itself (11-72 km/s), v^2 / (lambda R) -> ~0.4 kHz/s (30 km/s, 1000 km) to tens of
# kHz/s; its Doppler passes the trail's at the specular point (the start of the trail echo)
HEAD_RATE_MIN = 4.0 * SAT_RATE_MAX                         # ~480 Hz/s: a head echo searched for from here (meteor_head)

# meteor trail
WIND_MAX = 100.0                        # m/s, the neutral wind at 80-110 km
TRAIL_DOP_MAX = 2.0 * WIND_MAX / LAMBDA_M         # ~95 Hz
TRAIL_RATE_SIGMA = 6.0                  # Hz/s: the spread of the drift of trails (twisted overdense trails; live up to ~17)

SIGNIF = 2.0                            # standard errors beyond a bound for a class by the drift

# the station's own meteors (DopplerPrior): the prior until there are enough of them
PRIOR_RATE_H = 100.0                    # meteor echoes per hour (sporadic background, GRAVES from Central Europe)
PRIOR_DOP_SIGMA = 60.0                  # Hz: their Doppler spread around the carrier
PRIOR_WEIGHT = 20                       # the prior counts as this many meteors in the Doppler distribution
PRIOR_N = 2000                          # the last this many meteors are the learnt Doppler distribution
PRIOR_RATE_S = 3600.0                   # … and the rate is counted over this long
KDE_HZ = 15.0                           # the kernel of the learnt distribution (at least one bin)
SAT_PIECE_RATE = 0.5                    # a satellite fading in and out (the GRAVES beam): pieces a second, expected


TS_MAX_PTS = 160                        # Theil-Sen: at most this many points (evenly taken), ~12700 pairs
TS_EFF = 0.91                           # its efficiency against least squares for Gaussian noise (Sen 1968)


def slope(pts, corr_s, bin_hz):
    """The Theil-Sen line through the points (t, Hz, …): the median of the slopes of the pairs at least half the span
    apart (Theil 1950, Sen 1968; the near pairs of a Doppler quantised to bins mostly lie on one stair: slope 0),
    robust to the odd points a least-squares fit follows (the end of a head echo, noise at the end of a fading trail,
    another signal for a frame or two; breakdown point 29 %) -> (Hz/s, standard error Hz/s, robust spread Hz,
    rms Hz around the line), or None for fewer than 3 points or no time span.
    The standard error: the robust spread of the residuals (MAD x 1.4826), at least the bin quantisation
    (bin / sqrt(12)), over the spread of the times and the points independent only once per corr_s (the detector's
    frames overlap and are smoothed), divided by the root of the efficiency of the estimator."""
    if len(pts) < 3:
        return None
    if len(pts) > TS_MAX_PTS:
        pts = [pts[int(i)] for i in np.linspace(0, len(pts) - 1, TS_MAX_PTS)]
    t = np.array([p[0] for p in pts], float)
    f = np.array([p[1] for p in pts], float)
    t -= t[0]
    span = float(t[-1])
    st = float(np.std(t))
    if span <= 0 or st <= 0:
        return None
    i, j = np.triu_indices(len(t), 1)
    dt = t[j] - t[i]
    ok = dt >= span / 2                 # far pairs only: a Doppler quantised to bins is a staircase, and the near pairs
    if np.count_nonzero(ok) < 3:        # (mostly on one stair) would pull the median to 0 Hz/s
        ok = dt > 0
    if not ok.any():
        return None
    s = float(np.median((f[j] - f[i])[ok] / dt[ok]))
    res = f - s * t
    res -= np.median(res)
    robust = 1.4826 * float(np.median(np.abs(res)))
    rms = float(np.sqrt(np.mean(res ** 2)))
    sig = max(robust, bin_hz / math.sqrt(12.0))
    n_eff = min(len(pts), max(2.0, span / max(corr_s, 1e-6) + 1.0))
    return s, sig / (st * math.sqrt(n_eff * TS_EFF)), robust, rms


DECAY_MIN_PTS = 4                       # the decay is fitted on at least this many points after the peak …
DECAY_MIN_S = 0.15                      # … over at least this long
DECAY_MIN_SN = 0.5                      # … each with the signal at least this much of the noise (-3 dB)


def decay(trace):
    """The decay of an echo after its peak: an underdense trail's amplitude falls as exp(-t / tau), tau =
    lambda^2 sec^2(phi) / (32 pi^2 D) (McKinley 1961; D the ambipolar diffusion), so its power in dB falls on a
    straight line: 10 log10 P = a - (20 / ln 10) t / tau. trace [(t, Hz, dB over the floor)] -> (tau s, r^2 of the line
    in dB: ~1 exponential, low for an overdense plateau or a fading signal), or None (too few points, or not falling).
    The detector's frames and smoothing are linear filters: they keep the rate of an exponential, so tau is measured
    right even when it is shorter than a frame, given points enough over the floor."""
    if len(trace) < DECAY_MIN_PTS:
        return None
    t = np.array([p[0] for p in trace], float)
    d = np.array([p[2] for p in trace], float)
    k = int(np.argmax(d))
    t, d = t[k:] - t[k], d[k:]
    # the dB are of (signal + noise) / noise: the signal alone is that ratio - 1 (near the floor the dB fall slower)
    sn = 10.0 ** (d / 10.0) - 1.0
    keep = sn > DECAY_MIN_SN
    t, d = t[keep], 10.0 * np.log10(sn[keep])
    if len(t) < DECAY_MIN_PTS or t[-1] < DECAY_MIN_S:
        return None
    b, a = np.polyfit(t, d, 1)
    if b >= 0:
        return None
    var = float(np.var(d))
    r2 = 1.0 - float(np.mean((d - (a + b * t)) ** 2)) / var if var > 0 else 0.0
    return -20.0 / (float(b) * math.log(10.0)), r2


def faster_than(s, se, bound):
    """The drift s ± se is faster than bound (Hz/s) by SIGNIF standard errors."""
    return abs(s) - SIGNIF * se >= bound


def slower_than(s, se, bound):
    """The drift s ± se is slower than bound (Hz/s) by SIGNIF standard errors."""
    return abs(s) + SIGNIF * se < bound


def same_line(s_echo, se_echo, s_line):
    """An echo with the drift s_echo ± se_echo can lie on a line drifting s_line (Hz/s): log Bayes factor of "on the
    line" over "a meteor trail" (drift ~ N(0, TRAIL_RATE_SIGMA)), both with the measurement error."""
    v_line = se_echo ** 2 + (0.15 * s_line) ** 2 + 1.0        # the line's own slope is known within ~15 %
    v_met = se_echo ** 2 + TRAIL_RATE_SIGMA ** 2
    l_line = -0.5 * (s_echo - s_line) ** 2 / v_line - 0.5 * math.log(v_line)
    l_met = -0.5 * s_echo ** 2 / v_met - 0.5 * math.log(v_met)
    return l_line - l_met


class DopplerPrior:
    """The station's own meteors: their rate (per second) and the distribution of their Doppler (per Hz), learnt live,
    starting from the prior (PRIOR_*). The chance that a meteor falls somewhere by accident comes from these."""

    def __init__(self):
        self.pts = collections.deque(maxlen=PRIOR_N)          # (t, Hz)
        self.t_start = None

    def start(self, t):
        if self.t_start is None:
            self.t_start = t

    def add(self, t, hz):
        self.start(t)
        self.pts.append((t, float(hz)))

    def rate(self, now):
        """Meteor echoes a second: counted over the last PRIOR_RATE_S (at least 10 minutes of listening), never under
        the prior's half (an hour without meteors is a deaf receiver, not a sky without them)."""
        prior = PRIOR_RATE_H / 3600.0
        if self.t_start is None or now - self.t_start < 600.0:
            return prior
        span = min(PRIOR_RATE_S, now - self.t_start)
        times = [p[0] for p in self.pts]
        if len(times) == self.pts.maxlen and times[0] > now - span:
            span = now - times[0]       # more meteors than kept: over the time of those kept
        n = len(times) - bisect.bisect_left(times, now - span)
        return max(n / span, prior / 2)

    def pdf(self, hz, bin_hz=8.0):
        """The density of meteor Doppler at hz (per Hz): the learnt kernel estimate mixed with the prior Gaussian."""
        g = PRIOR_WEIGHT * math.exp(-0.5 * (hz / PRIOR_DOP_SIGMA) ** 2) / (PRIOR_DOP_SIGMA * math.sqrt(2 * math.pi))
        h = max(KDE_HZ, bin_hz)
        if self.pts:
            d = (np.array([p[1] for p in self.pts]) - hz) / h
            g += float(np.sum(np.exp(-0.5 * d * d))) / (h * math.sqrt(2 * math.pi))
        return g / (PRIOR_WEIGHT + len(self.pts))

    def chance_log_bf(self, hz, now, window_hz, bin_hz=8.0):
        """log Bayes factor of "a meteor here by chance" over "the next piece of the satellite", for an echo at hz that
        lies on the satellite's expected line (anywhere within window_hz of it): a meteor comes at rate * pdf(hz) per
        Hz and second, a satellite piece at SAT_PIECE_RATE spread over the window."""
        lam_m = self.rate(now) * self.pdf(hz, bin_hz)
        lam_s = SAT_PIECE_RATE / max(window_hz, 1.0)
        return math.log(max(lam_m, 1e-12) / lam_s)

"""GRAVES (meteor.py): an estimated size of the meteoroid behind a meteor echo. Only an estimate, within a factor of a
few: the speed of the meteoroid, the geometry of the path and the gain of the station are not known per echo.

The line density of the trail q (electrons per metre) first:
  - overdense (UNDER_S and longer): its duration T = r_e q lambda^2 sec^2(phi) / (4 pi^2 D) (McKinley, "Meteor Science
    and Engineering", 1961), and an underdense trail decays with tau = lambda^2 sec^2(phi) / (32 pi^2 D) in the same
    place. With D and phi from the station's own underdense echoes (the median of their measured tau) both cancel:
    q = T / (8 r_e tau_med). Not below the overdense limit Q_TRANS.
  - underdense: its received power goes with q^2: q = Q_LIM 10^((SNR - THR) / 20), Q_LIM at the threshold being the
    station's limiting line density (assumed, ~+6.8 mag: what a small Yagi on GRAVES gets), at most Q_TRANS.
Then the magnitude M = 40 - 2.5 log10 q (a 0 mag meteor ~1e16 e/m; Verniani 1973, Ceplecha et al. 1998), the mass
m = 10^(-0.4 M) g (0 mag ~1 g at the typical V_KM_S, the ionisation ~v^3.5), the size of a sphere of density RHO
(porous cometary dust). The spread: the speed 20…70 km/s alone moves the mass by ~MASS_SPREAD either way.
"""

import math
from collections import deque

R_E_M = 2.818e-15               # classical electron radius
Q_TRANS = 2.4e14                # e/m: underdense below, overdense above
Q_LIM = 3e13                    # e/m at the threshold THR (assumed station limit)
TAU_DEFAULT_S = 0.15            # the median tau before the station has its own
TAU_MIN_N = 10                  # … at least this many underdense taus first
TAU_N = 300
TAU_R2 = 0.9                    # only straight (exponential) decays
V_KM_S = 40.0
RHO_G_CM3 = 1.0
MASS_SPREAD = 5.0


class SizeEstimator:
    def __init__(self):
        self._tau = deque(maxlen=TAU_N)

    def add_tau(self, tau, r2):
        """The decay of an underdense echo (meteor_phys.decay): the station's D and geometry for the overdense ones."""
        if tau and r2 is not None and r2 >= TAU_R2 and 0.01 < tau < 5.0:
            self._tau.append(float(tau))

    def tau_med(self):
        if len(self._tau) < TAU_MIN_N:
            return TAU_DEFAULT_S
        s = sorted(self._tau)
        return s[len(s) // 2]

    def estimate(self, kind, snr, dur, thr_db):
        """-> {"q", "mag", "mg", "mm", "mm_lo", "mm_hi", "how"} for a meteor (kind under / over), else None."""
        if kind == "over":
            q = max(Q_TRANS, dur / (8 * R_E_M * self.tau_med()))
            how = f"overdense: duration {dur:.1f} s, tau of this station {self.tau_med() * 1000:.0f} ms"
        elif kind == "under":
            q = min(Q_TRANS, Q_LIM * 10 ** ((snr - thr_db) / 20))
            how = f"underdense: SNR {snr:.1f} dB, threshold {thr_db:.1f} dB"
        else:
            return None
        mag = 40.0 - 2.5 * math.log10(q)
        g = 10 ** (-0.4 * mag)

        def mm(m):
            return 10 * (6 * m / (math.pi * RHO_G_CM3)) ** (1 / 3)
        return {"q": float(f"{q:.2g}"), "mag": round(mag, 1), "mg": float(f"{g * 1000:.2g}"), "mm": round(mm(g), 1),
                "mm_lo": round(mm(g / MASS_SPREAD), 1), "mm_hi": round(mm(g * MASS_SPREAD), 1), "how": how}

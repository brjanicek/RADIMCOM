"""The Moon for EME (earth-moon-earth) tracking in SATELLITES: an object that sattrack.py treats as one more satellite.

The position is the lunar theory of J. Meeus, Astronomical Algorithms (2nd ed.), chapter 47, with the main terms of
its tables 47.A and 47.B (about 0.003 degrees in longitude, 0.001 in latitude, 20 km in distance against JPL DE440;
see tests/test_moon.py). It gives geocentric ecliptic coordinates of the mean equinox of date; turned by the mean
obliquity they are the equatorial coordinates that sattrack's _ecef() takes from SGP4 (TEME): nutation (under 20
arcseconds) is left out. The station's parallax (up to about a degree) and the Earth's rotation in the range rate come
from sattrack.look() as for any satellite, so the passes, TRACK, the rotor planner, the map and the Doppler work as
they are.

    MOON_ID          the pseudo NORAD number of the Moon in sattrack.satellites()
    MoonSat()        sgp4_array(jd_i, jd_f) -> (err, r, v) like sgp4.api.Satrec, positions in km, velocities in km/s
    geocentric(jd)   (x, y, z) km, equator and equinox of date
    echo_doppler(rate_km_s, f_hz)   the shift of the own echo (there and back: twice the one-way shift)
    path_loss_db(range_km, f_hz)    the EME path loss (radar equation, lunar reflection coefficient 0.065)
"""
import math

import numpy as np

MOON_ID = 999999            # never a real catalogue number (Alpha-5 ends at 339999)
MOON_NAME = "MOON (EME)"
DELTA_T_S = 69.0            # TT - UT; a minute of error moves the Moon by 0.5 arcminute
C_KM_S = 299792.458
MOON_RADIUS_KM = 1737.4
MOON_REFLECTIVITY = 0.065

# Meeus table 47.A: multiples of D, M, M', F; longitude (1e-6 degree), distance (1e-3 km)
_LR = np.array([
    (0, 0, 1, 0, 6288774, -20905355), (2, 0, -1, 0, 1274027, -3699111), (2, 0, 0, 0, 658314, -2955968),
    (0, 0, 2, 0, 213618, -569925), (0, 1, 0, 0, -185116, 48888), (0, 0, 0, 2, -114332, -3149),
    (2, 0, -2, 0, 58793, 246158), (2, -1, -1, 0, 57066, -152138), (2, 0, 1, 0, 53322, -170733),
    (2, -1, 0, 0, 45758, -204586), (0, 1, -1, 0, -40923, -129620), (1, 0, 0, 0, -34720, 108743),
    (0, 1, 1, 0, -30383, 104755), (2, 0, 0, -2, 15327, 10321), (0, 0, 1, 2, -12528, 0),
    (0, 0, 1, -2, 10980, 79661), (4, 0, -1, 0, 10675, -34782), (0, 0, 3, 0, 10034, -23210),
    (4, 0, -2, 0, 8548, -21636), (2, 1, -1, 0, -7888, 24208), (2, 1, 0, 0, -6766, 30824),
    (1, 0, -1, 0, -5163, -8379), (1, 1, 0, 0, 4987, -16675), (2, -1, 1, 0, 4036, -12831),
    (2, 0, 2, 0, 3994, -10445), (4, 0, 0, 0, 3861, -11650), (2, 0, -3, 0, 3665, 14403),
    (0, 1, -2, 0, -2689, -7003), (2, 0, -1, 2, -2602, 0), (2, -1, -2, 0, 2390, 10056),
    (1, 0, 1, 0, -2348, 6322), (2, -2, 0, 0, 2236, -9884), (0, 1, 2, 0, -2120, 5751),
    (0, 2, 0, 0, -2069, 0), (2, -2, -1, 0, 2048, -4950), (2, 0, 1, -2, -1773, 4130),
    (2, 0, 0, 2, -1595, 0), (4, -1, -1, 0, 1215, -3958), (0, 0, 2, 2, -1110, 0),
    (3, 0, -1, 0, -892, 3258), (2, 1, 1, 0, -810, 2616), (4, -1, -2, 0, 759, -1897),
    (0, 2, -1, 0, -713, -2117), (2, 2, -1, 0, -700, 2354), (2, 1, -2, 0, 691, 0),
    (2, -1, 0, -2, 596, 0), (4, 0, 1, 0, 549, -1423), (0, 0, 4, 0, 537, -1117),
    (4, -1, 0, 0, 520, -1571), (1, 0, -2, 0, -487, -1739), (2, 1, 0, -2, -399, 0),
    (0, 0, 2, -2, -381, -4421), (1, 1, 1, 0, 351, 0), (3, 0, -2, 0, -340, 0),
    (4, 0, -3, 0, 330, 0), (2, -1, 2, 0, 327, 0), (0, 2, 1, 0, -323, 1165),
    (1, 1, -1, 0, 299, 0), (2, 0, 3, 0, 294, 0), (2, 0, -1, -2, 0, 8752),
], float)
# Meeus table 47.B: multiples of D, M, M', F; latitude (1e-6 degree)
_B = np.array([
    (0, 0, 0, 1, 5128122), (0, 0, 1, 1, 280602), (0, 0, 1, -1, 277693), (2, 0, 0, -1, 173237),
    (2, 0, -1, 1, 55413), (2, 0, -1, -1, 46271), (2, 0, 0, 1, 32573), (0, 0, 2, 1, 17198),
    (2, 0, 1, -1, 9266), (0, 0, 2, -1, 8822), (2, -1, 0, -1, 8216), (2, 0, -2, -1, 4324),
    (2, 0, 1, 1, 4200), (2, 1, 0, -1, -3359), (2, -1, -1, 1, 2463), (2, -1, 0, 1, 2211),
    (2, -1, -1, -1, 2065), (0, 1, -1, -1, -1870), (4, 0, -1, -1, 1828), (0, 1, 0, 1, -1794),
    (0, 0, 0, 3, -1749), (0, 1, -1, 1, -1565), (1, 0, 0, 1, -1491), (0, 1, 1, 1, -1475),
    (0, 1, 1, -1, -1410), (0, 1, 0, -1, -1344), (1, 0, 0, -1, -1335), (0, 0, 3, 1, 1107),
    (4, 0, 0, -1, 1021), (4, 0, -1, 1, 833),
], float)


def geocentric(jd):
    """Geocentric position of the Moon (km) at the Julian dates jd (UT, numpy array): x, y, z in the equator and
    equinox of date."""
    jd = np.asarray(jd, float) + DELTA_T_S / 86400.0
    t = (jd - 2451545.0) / 36525.0
    r = math.pi / 180
    lp = (218.3164477 + 481267.88123421 * t) * r
    d = (297.8501921 + 445267.1114034 * t) * r
    m = (357.5291092 + 35999.0502909 * t) * r
    mp = (134.9633964 + 477198.8675055 * t) * r
    f = (93.2720950 + 483202.0175233 * t) * r
    e = 1 - 0.002516 * t - 0.0000074 * t * t
    a1 = (119.75 + 131.849 * t) * r
    a2 = (53.09 + 479264.290 * t) * r
    a3 = (313.45 + 481266.484 * t) * r

    def series(tab, col, fn):
        arg = np.outer(d, tab[:, 0]) + np.outer(m, tab[:, 1]) + np.outer(mp, tab[:, 2]) + np.outer(f, tab[:, 3])
        ecc = np.power(e[:, None], np.abs(tab[:, 1])[None, :])       # the terms with M shrink with the Earth's orbit
        return (tab[:, col] * ecc * fn(arg)).sum(axis=1)

    d = np.atleast_1d(d)
    m, mp, f, e = np.atleast_1d(m), np.atleast_1d(mp), np.atleast_1d(f), np.atleast_1d(e)
    lp, a1, a2, a3, t = np.atleast_1d(lp), np.atleast_1d(a1), np.atleast_1d(a2), np.atleast_1d(a3), np.atleast_1d(t)
    sl = series(_LR, 4, np.sin) + 3958 * np.sin(a1) + 1962 * np.sin(lp - f) + 318 * np.sin(a2)
    sr = series(_LR, 5, np.cos)
    sb = (series(_B, 4, np.sin) - 2235 * np.sin(lp) + 382 * np.sin(a3) + 175 * np.sin(a1 - f) + 175 * np.sin(a1 + f)
          + 127 * np.sin(lp - mp) - 115 * np.sin(lp + mp))
    lam = lp + sl * 1e-6 * r
    beta = sb * 1e-6 * r
    dist = 385000.56 + sr / 1000.0
    eps = (23.4392911 - 0.0130042 * t) * r                           # mean obliquity of the ecliptic
    cb = np.cos(beta)
    x = dist * cb * np.cos(lam)
    y = dist * (cb * np.sin(lam) * np.cos(eps) - np.sin(beta) * np.sin(eps))
    z = dist * (cb * np.sin(lam) * np.sin(eps) + np.sin(beta) * np.cos(eps))
    return x, y, z


class MoonSat:
    """Stands in for an sgp4 Satrec: sattrack.look() / subpoint() / find_passes() take it as a satellite."""

    DT_DAYS = 30.0 / 86400.0      # the velocity from positions 30 s before and after
    # sattrack.world_map() draws "one and a half orbits" of the point below; for the Moon that point goes round the
    # Earth once in a lunar day (24 h 50 min), so the map shows about a day and a half of it
    no_kozai = 2 * math.pi / (24.84 * 60)

    def sgp4_array(self, jd_i, jd_f):
        jd = np.asarray(jd_i, float) + np.asarray(jd_f, float)
        r = np.stack(geocentric(jd), axis=1)
        r1 = np.stack(geocentric(jd + self.DT_DAYS), axis=1)
        r0 = np.stack(geocentric(jd - self.DT_DAYS), axis=1)
        v = (r1 - r0) / (2 * self.DT_DAYS * 86400.0)
        return np.zeros(len(jd), int), r, v


def echo_doppler(rate_km_s, f_hz):
    """Shift of the own echo (Hz): the path there and back, twice the one-way shift; + = higher."""
    return -2.0 * rate_km_s / C_KM_S * f_hz


def path_loss_db(range_km, f_hz):
    """EME path loss (dB), the radar equation with the Moon as a sphere of reflection coefficient 0.065:
    L = 10 log10( (4 pi)^3 d^4 / (eta pi r^2 lambda^2) ); about 252 dB at 144 MHz, 271 dB at 1296 MHz."""
    lam = C_KM_S * 1000.0 / f_hz
    d = range_km * 1000.0
    sigma = MOON_REFLECTIVITY * math.pi * (MOON_RADIUS_KM * 1000.0) ** 2
    return 10 * math.log10((4 * math.pi) ** 3 * d ** 4 / (sigma * lam ** 2))

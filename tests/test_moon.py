"""moon.py: the Moon's position against JPL Horizons and the Moon as a satellite in sattrack (EME)."""
import calendar
import math
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import moon

AU_KM = 149597870.7


def _t(text):
    return calendar.timegm(time.strptime(text, "%Y-%b-%d %H:%M"))


# JPL Horizons, geocentric, RA / Dec of date (degrees), distance (au)
GEO = [("2026-Nov-01 00:00", 120.06997, 23.10743, 0.00247266123383),
       ("2026-Nov-11 00:00", 245.14809, -26.43088, 0.00268895992174),
       ("2026-Nov-21 00:00", 7.90624, 7.29041, 0.00252519871970),
       ("2026-Dec-01 00:00", 157.00199, 8.50758, 0.00251635544404)]
# JPL Horizons, topocentric at 50 N 10 E, 0 m: azimuth, elevation (degrees), range (au), range rate (km/s)
TOPO = ("2026-Nov-20 00:00", 257.584752, 10.770638, 0.00255836889497, 0.2009375)


class MoonPosition(unittest.TestCase):
    def test_geocentric_against_horizons(self):
        jd = np.array([_t(r[0]) for r in GEO], float) / 86400 + 2440587.5
        x, y, z = moon.geocentric(jd)
        for i, (_, ra0, de0, au) in enumerate(GEO):
            ra = math.degrees(math.atan2(y[i], x[i])) % 360
            de = math.degrees(math.atan2(z[i], math.hypot(x[i], y[i])))
            a1, d1, a2, d2 = map(math.radians, (ra, de, ra0, de0))
            sep = math.degrees(math.acos(min(1.0, math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(a1 - a2))))
            self.assertLess(sep, 0.02)
            self.assertLess(abs(math.sqrt(x[i] ** 2 + y[i] ** 2 + z[i] ** 2) - au * AU_KM), 100)

    def test_topocentric_through_sattrack(self):
        import sattrack
        lk = sattrack.look(moon.MoonSat(), np.array([_t(TOPO[0])], float), {"lat": 50.0, "lon": 10.0, "alt_m": 0.0})
        self.assertLess(abs((lk["az"][0] - TOPO[1] + 180) % 360 - 180), 0.05)
        self.assertLess(abs(lk["el"][0] - TOPO[2]), 0.05)
        self.assertLess(abs(lk["range"][0] - TOPO[3] * AU_KM), 100)
        self.assertLess(abs(lk["rate"][0] - TOPO[4]), 0.005)     # 5 m/s = 43 Hz of echo at 1296 MHz


class MoonEme(unittest.TestCase):
    def test_path_loss(self):
        self.assertAlmostEqual(moon.path_loss_db(384400, 144e6), 252.1, delta=0.2)
        self.assertAlmostEqual(moon.path_loss_db(384400, 1296e6) - moon.path_loss_db(384400, 144e6),
                               20 * math.log10(9), delta=0.01)

    def test_echo_doppler(self):
        self.assertAlmostEqual(moon.echo_doppler(-0.3, 1296e6), 2 * 0.3 / moon.C_KM_S * 1296e6)
        self.assertLess(moon.echo_doppler(0.3, 144e6), 0)      # going away: lower

    def test_moon_is_a_satellite(self):
        import sattrack
        sat = sattrack.satellites()[moon.MOON_ID]
        self.assertTrue(sat.get("moon"))
        ps = sattrack.find_passes(sat["sat"], _t("2026-Nov-21 00:00"), 48, {"lat": 50.0, "lon": 10.0, "alt_m": 0.0, "min_el": 0})
        self.assertIn(len(ps), (2, 3))                 # one rise a lunar day (24 h 50 min)
        for p in ps:
            if not (p["aos_open"] or p["los_open"]):
                self.assertGreater(p["los"] - p["aos"], 8 * 3600)


if __name__ == "__main__":
    unittest.main()

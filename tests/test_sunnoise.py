"""sunnoise.py: the Sun position, the flux estimate and the G/T arithmetic of SUN NOISE.

Run: python -m unittest tests.test_sunnoise
"""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sunnoise  # noqa: E402


class SunNoise(unittest.TestCase):
    def test_sun_declination(self):
        # equinox 2024-03-20 03:06 UTC: declination 0; solstice 2024-06-20 20:51 UTC: +23.44
        for jd, dec in ((2460389.629, 0.0), (2460482.369, 23.44)):
            x, y, z = sunnoise.sun_geocentric(np.array([jd]))
            d = math.degrees(math.atan2(z[0], math.hypot(x[0], y[0])))
            self.assertAlmostEqual(d, dec, delta=0.05)
            self.assertAlmostEqual(math.sqrt(x[0] ** 2 + y[0] ** 2 + z[0] ** 2) / sunnoise.AU_KM, 1.0, delta=0.02)

    def test_noon_elevation(self):
        import sattrack
        setup = {"lat": 48.0, "lon": 17.0, "alt_m": 0}
        t = np.arange(1718877600, 1718877600 + 86400, 60.0)       # 2024-06-20 UTC
        lk = sattrack.look(sunnoise.SunSat(), t, setup)
        i = int(np.argmax(lk["el"]))
        self.assertAlmostEqual(float(lk["el"][i]), 90 - 48 + 23.44, delta=0.2)
        self.assertAlmostEqual(float(lk["az"][i]), 180.0, delta=2.0)

    def test_flux(self):
        self.assertAlmostEqual(sunnoise.sun_flux_sfu(2800, 70), 70.0, places=3)
        self.assertAlmostEqual(sunnoise.sun_flux_sfu(2800, 140), 140.0, places=3)
        a, b = sunnoise.sun_flux_sfu(144, 100), sunnoise.sun_flux_sfu(1296, 100)
        self.assertLess(a, b)

    def test_gt_round_trip(self):
        for gt in (-15.0, 0.0, 12.0):
            y = sunnoise.expected_y_sun(gt, 80.0, 1296e6)
            self.assertAlmostEqual(sunnoise.gt_sun(y, 80.0, 1296e6), gt, places=6)
        self.assertIsNone(sunnoise.gt_sun(0.0, 80, 144e6))
        # Moon: Y = 1 + G/T * T_moon * Omega / (4 pi)
        g = 10 ** 1.0
        y = 10 * math.log10(1 + g * sunnoise.MOON_TEMP_K * sunnoise.moon_solid_angle(384400) / (4 * math.pi))
        self.assertAlmostEqual(sunnoise.gt_moon(y, 384400), 10.0, places=6)

    def test_scan_fit(self):
        rng = np.random.default_rng(3)
        x = np.arange(-20, 20.1, 2.5)
        for x0, w, y in ((4.2, 27.0, 0.9), (-2.0, 18.0, 2.5)):
            yl = 10 ** (y / 10) - 1
            p = 1 + yl * np.exp(-4 * math.log(2) * (x - x0) ** 2 / w ** 2)
            db = 10 * np.log10(p) - 60 + rng.normal(0, 0.03, len(x))
            r = sunnoise.fit_scan(x, db)
            self.assertTrue(r["ok"], r)
            self.assertAlmostEqual(r["x0"], x0, delta=1.0)
            self.assertLess(r["sigma"], 1.5)
            self.assertAlmostEqual(r["width"], w, delta=w * 0.25)
            self.assertAlmostEqual(r["peak_db"], y, delta=0.2)

    def test_scan_fit_refuses(self):
        x = np.arange(-20, 20.1, 2.5)
        flat = -60 + np.random.default_rng(1).normal(0, 0.03, len(x))
        self.assertFalse(sunnoise.fit_scan(x, flat)["ok"])
        p = 1 + 0.3 * np.exp(-4 * math.log(2) * (x - 19) ** 2 / 20 ** 2)     # the peak at the edge
        self.assertFalse(sunnoise.fit_scan(x, 10 * np.log10(p))["ok"])


if __name__ == "__main__":
    unittest.main()

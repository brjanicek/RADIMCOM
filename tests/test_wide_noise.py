"""sdr.wide_noise_db: the noise floor of the whole band for SUN NOISE › Meter WIDE."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sdr  # noqa: E402


class WideNoiseTest(unittest.TestCase):
    def test_follows_the_noise_not_the_carriers(self):
        rng = np.random.default_rng(1)
        p = rng.exponential(1.0, 32768)
        base = sdr.wide_noise_db(p)
        q = p.copy()
        q[2000:2200] = 1e6              # strong carriers in 0.6 % of the band
        self.assertAlmostEqual(sdr.wide_noise_db(q), base, delta=0.05)
        self.assertAlmostEqual(sdr.wide_noise_db(p * 1.1) - base, 10 * np.log10(1.1), places=3)   # the Sun: +0.41 dB

    def test_edges_and_dc_left_out(self):
        p = np.ones(32768)
        p[:3000] = p[-3000:] = 1e-6      # the roll-off of the SDR's filter
        p[16384 - 100:16384 + 100] = 1e6   # the DC spike
        self.assertAlmostEqual(sdr.wide_noise_db(p), 0.0, places=6)


if __name__ == "__main__":
    unittest.main()

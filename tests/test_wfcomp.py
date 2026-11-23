"""wfcomp.py: the waterfall rows corrected for the tuner gain, with the real step measured on the noise floor.

Run: python -m unittest tests.test_wfcomp
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wfcomp  # noqa: E402


def band(level_db, rng):
    """Linear power of a band: noise at level_db plus a few strong carriers (they must not move the median)."""
    p = 10 ** (level_db / 10) * rng.exponential(size=4096)
    p[[100, 900, 2500]] *= 1e4
    return p


class GainComp(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(1)
        self.gc = wfcomp.GainComp()

    def row_db(self, gain, real_gain, glitch=0):
        cfg = {"gain": gain, "wf_comp": True}
        p = band(-100 + real_gain, self.rng)
        off = self.gc.update(cfg, p, glitch)
        return float(10 * np.log10(np.median(p))) - off

    def test_steady_floor_over_steps(self):
        first = self.row_db(40.2, 40.2)
        # nominal 40.2 -> 29.7 (10.5 dB), the tuner really does 12.0: the measured step is taken
        self.row_db(29.7, 40.2, glitch=2)               # a block with the old gain still
        after = self.row_db(29.7, 28.2)
        self.assertLess(abs(after - first), 0.3)
        back = self.row_db(40.2, 40.2)                  # back to the first gain: the same floor again
        self.assertLess(abs(back - first), 0.3)

    def test_untrusted_measurement_uses_nominal(self):
        self.row_db(20.0, 20.0)
        self.row_db(30.0, 20.0 + 30.0)                  # the floor jumped 30 dB on a 10 dB step: not believed
        self.assertAlmostEqual(self.gc.offset, 30.0 - wfcomp.REF_DB, places=3)

    def test_auto_and_off(self):
        self.assertEqual(self.gc.update({"gain": "auto"}, band(-90, self.rng), 0), 0.0)
        self.assertEqual(self.gc.update({"gain": 30.0, "wf_comp": False}, band(-90, self.rng), 0), 0.0)
        self.assertAlmostEqual(self.gc.update({"gain": 40.0}, band(-90, self.rng), 0), 40.0 - wfcomp.REF_DB)
        # the top of the tuner's range known: no correction there, more brightness under it
        self.assertAlmostEqual(self.gc.update({"gain": 49.6}, band(-90, self.rng), 0, 1.0, 49.6), 0.0)
        self.gc.reset()
        self.assertAlmostEqual(self.gc.update({"gain": 16.6}, band(-90, self.rng), 0, 1.0, 49.6), -33.0)


if __name__ == "__main__":
    unittest.main()

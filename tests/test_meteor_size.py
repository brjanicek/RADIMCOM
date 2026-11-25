"""meteor_size.py: the estimated size of a meteoroid from its echo."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meteor_size as ms  # noqa: E402


class SizeTest(unittest.TestCase):
    def test_classes(self):
        z = ms.SizeEstimator()
        faint = z.estimate("under", 10.0, 0.2, 10.0)
        strong = z.estimate("under", 30.0, 0.6, 10.0)
        over = z.estimate("over", 30.0, 10.0, 10.0)
        self.assertAlmostEqual(faint["q"], ms.Q_LIM, delta=1e12)
        self.assertTrue(1.0 < faint["mm"] < 3.0, faint)               # a grain of sand
        self.assertLess(faint["mm"], strong["mm"])
        self.assertLessEqual(strong["q"], ms.Q_TRANS)                  # underdense stays under the limit
        self.assertGreater(over["mm"], strong["mm"])
        self.assertTrue(over["mm_lo"] < over["mm"] < over["mm_hi"])
        self.assertIsNone(z.estimate("plane", 30.0, 10.0, 10.0))
        self.assertIsNone(z.estimate("sat", 30.0, 10.0, 10.0))

    def test_overdense_from_the_station_tau(self):
        """q = T / (8 r_e tau): a slower diffusion (longer tau) means the same duration needs less electrons."""
        z = ms.SizeEstimator()
        self.assertEqual(z.tau_med(), ms.TAU_DEFAULT_S)
        q0 = z.estimate("over", 25.0, 5.0, 10.0)["q"]
        for _ in range(20):
            z.add_tau(0.3, 0.95)
        z.add_tau(5.0, 0.99)                                          # out of range: left out
        z.add_tau(0.01, 0.5)                                          # not exponential: left out
        self.assertAlmostEqual(z.tau_med(), 0.3)
        q1 = z.estimate("over", 25.0, 5.0, 10.0)["q"]
        self.assertAlmostEqual(q0 / q1, 2.0, delta=0.05)
        self.assertAlmostEqual(q1, 5.0 / (8 * ms.R_E_M * 0.3), delta=0.05 * q1)


if __name__ == "__main__":
    unittest.main()

"""imd.py and the LINEARITY check of AGC+ (gainctl.SmartAgc._linearity): intermodulation of the tuner, which does not
clip the A/D, seen from the spectrum across a gain step.

Run: python -m unittest tests.test_imd
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import imd  # noqa: E402
from gainctl import SmartAgc, Target  # noqa: E402

N = 32768
REAL = [4200, 6100, 8000, 9900, 12500, 14300, 17700, 20100, 23900, 26600]
PHANTOM = [5300, 11100, 16400, 21000, 25200]


def band(gain, rng, phantoms=True, fade=None):
    """Linear spectrum: antenna noise and real lines that follow the gain 1:1, phantoms 3:1 (a third-order product)
    rising out of the noise from 14 dB of gain on (as on VFO A, 4049.4 kHz, 2026-11-22)."""
    db = np.full(N, -110.0 + gain)
    for i in REAL:
        db[i] = -80.0 + gain + (fade.get(i, 0.0) if fade else 0.0)
    if phantoms:
        for i in PHANTOM:
            db[i] = max(db[i], -110.0 + gain + 3 * (gain - 14.0))
    return 10 ** (db / 10) * rng.exponential(size=N) ** 0.1


def pdb(p):
    return 10 * np.log10(imd.pooled(p))


class Compare(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(5)

    def test_linear_band(self):
        r = imd.compare(pdb(band(25.4, self.rng, False)), pdb(band(22.9, self.rng, False)), 2.5)
        self.assertFalse(r["imd"])
        self.assertAlmostEqual(r["step_db"], 2.5, delta=0.5)

    def test_third_order_products(self):
        r = imd.compare(pdb(band(22.9, self.rng)), pdb(band(19.7, self.rng)), 3.2)
        self.assertTrue(r["imd"])
        self.assertTrue(all(k == "fast" for _i, _d, k in r["bad"]))

    def test_the_table_lies_the_median_measures(self):
        # the tuner says 3 dB, it really moved 5: the real lines must not look non-linear
        r = imd.compare(pdb(band(25.0, self.rng, False)), pdb(band(20.0, self.rng, False)), 3.0)
        self.assertFalse(r["imd"])
        self.assertAlmostEqual(r["step_db"], 5.0, delta=0.5)

    def test_one_line_fading_is_not_intermodulation(self):
        r = imd.compare(pdb(band(25.4, self.rng, False, {6100: 6.0})), pdb(band(22.9, self.rng, False)), 2.5)
        self.assertFalse(r["imd"])

    def test_compression_products_that_do_not_move(self):
        hi = band(25.4, self.rng, False)
        lo = band(22.9, self.rng, False)
        for i in PHANTOM:                       # stuck at one level: a front end in compression
            hi[i] = lo[i] = 10 ** (-60 / 10)
        r = imd.compare(pdb(hi), pdb(lo), 2.5)
        self.assertTrue(r["imd"])
        self.assertTrue(all(k == "slow" for _i, _d, k in r["bad"]))

    def test_whole_band_in_compression(self):
        # 2026-11-22, VFO A: 25.4 -> 22.9 dB (2.5 nominal), every line moved 0.5 dB
        r = imd.compare(pdb(band(23.4, self.rng, False)), pdb(band(22.9, self.rng, False)), 2.5)
        self.assertTrue(r["imd"])
        self.assertTrue(r.get("compressed"))


class Flow(unittest.TestCase):
    """SmartAgc at the top of its range (held by the clipping) with phantoms: the checks one step down take it to the
    gain where the phantoms are gone, and it stays there."""

    def test_steps_down_out_of_the_intermodulation(self):
        rng = np.random.default_rng(7)
        gains = [8.7, 12.5, 16.6, 19.7, 22.9, 25.4]
        sa = SmartAgc()
        sa.t = 100.0
        sa.lin_next = 0.0
        tgt = Target("narrow", 4.05e6)
        gain, blk, settle = 25.4, 0.064, 0
        for _ in range(int(240 / blk)):
            sa.t += blk
            sa.lin.feed(band(gain, rng), gain, sa.t, blk, settle > 0, 4.09e6, 2.048e6)
            settle = max(0, settle - 1)
            if settle:
                continue
            if sa.lin_probe is None:
                sa.limit = "smart"              # held at the top by the clipping (as _smart leaves it)
            new = sa._linearity(gains, gain, 1.0, tgt, 30.0, sa.t)
            if new not in (None, False) and new != gain:
                gain, settle = new, 3
        self.assertEqual(gain, 16.6)
        self.assertIn(19.7, sa.fails)
        self.assertIsNotNone(sa.imd_ref)

    def test_ceiling_goes_when_the_strong_stations_fall(self):
        rng = np.random.default_rng(3)
        gains = [8.7, 12.5, 16.6, 19.7, 22.9, 25.4]
        tgt = Target("narrow", 4.05e6)
        for drop, lifted in ((2.0, False), (10.0, True)):
            sa = SmartAgc()
            sa.t, sa.lin_next = 100.0, 1e9      # no checks down here
            sa.imd_ref = -80.0 + 16.6 - 16.6    # the strong lines at 16.6 dB then, gain out
            sa.ceil, sa.ceil_until, sa.limit = 16.6, 1e9, "imd"
            gain, blk = 16.6, 0.064
            for _ in range(int(20 / blk)):
                sa.t += blk
                sa.lin.feed(band(gain - drop, rng, False), gain, sa.t, blk, False, 4.09e6, 2.048e6)
                sa._linearity(gains, gain, 1.0, tgt, 30.0, sa.t)
            self.assertEqual(sa.ceil is None, lifted, drop)


if __name__ == "__main__":
    unittest.main()

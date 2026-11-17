"""Tests of the LPF key (sdr.SharpLowpass): steep like the channel filter, stereo, no click on a change.

Run: python -m unittest tests.test_lpf   (from the RADIMCOM folder)
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sdr  # noqa: E402

FS = 32000.0


def tone_db(f, hz=2400.0, fs=FS):
    """Level of a tone f after the LPF (steady state), dB."""
    lp = sdr.SharpLowpass()
    t = np.arange(int(fs)) / fs
    x = np.sin(2 * np.pi * f * t)
    x = np.stack((x, x), axis=1)
    y = np.concatenate([lp.process(x[i:i + 1024], fs, hz) for i in range(0, len(x), 1024)])
    tail = y[len(y) // 2:, 0]
    return 20 * np.log10(np.sqrt(2) * np.sqrt(np.mean(tail ** 2)) + 1e-12)


class SharpLowpass(unittest.TestCase):
    def test_steep(self):
        self.assertGreater(tone_db(2000), -0.1)              # passband flat
        self.assertAlmostEqual(tone_db(2400), -6, delta=0.5)  # −6 dB at the cutoff, as the channel filter
        self.assertLess(tone_db(2550), -60)                  # steep: 150 Hz above the cutoff already −60 dB
        self.assertLess(tone_db(3000), -70)

    def test_off_passes_through_and_rates(self):
        lp = sdr.SharpLowpass()
        x = np.random.default_rng(1).normal(size=(512, 2)) * 0.1
        self.assertTrue(np.array_equal(lp.process(x, FS, None), x))
        self.assertGreater(tone_db(2000, fs=37500.0), -0.1)
        self.assertLess(tone_db(2600, fs=37500.0), -60)
        self.assertLess(tone_db(15000, hz=16000.0, fs=FS), -60)   # cutoff above Nyquist kept under 0.45 fs

    def test_change_is_smooth(self):
        lp = sdr.SharpLowpass()
        t = np.arange(1024 * 8) / FS
        x = np.sin(2 * np.pi * 500 * t)
        x = np.stack((x, x), axis=1)
        out = []
        for i, hz in enumerate((None, 2400.0, 2400.0, 3000.0, 3000.0, None, None, 2400.0)):
            out.append(lp.process(x[i * 1024:(i + 1) * 1024], FS, hz))
        y = np.concatenate(out)[:, 0]
        self.assertLess(np.max(np.abs(np.diff(y))), 0.2)      # no jump (a 500 Hz sine moves ≤ 0.1 a sample)


if __name__ == "__main__":
    unittest.main()

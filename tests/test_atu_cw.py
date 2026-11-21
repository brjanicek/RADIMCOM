"""ATU in CW (zero beat): estimate_cw finds a keyed carrier near the click in noise; nothing in noise alone."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import autotune  # noqa: E402

FS = 32000.0


def keyed(seconds, off_hz, snr_db, seed=1, wpm=22):
    """Complex baseband: random CW keying at off_hz, white noise; snr_db = key-down power over the noise in 500 Hz."""
    rng = np.random.default_rng(seed)
    n = int(seconds * FS)
    dot = int(1.2 / wpm * FS)
    key = np.repeat(rng.random(n // dot + 1) > 0.45, dot)[:n].astype(float)
    t = np.arange(n) / FS
    x = key * np.exp(2j * np.pi * off_hz * t)
    sigma = np.sqrt(FS / 500 / 10 ** (snr_db / 10) / 2)
    return (x + sigma * (rng.standard_normal(n) + 1j * rng.standard_normal(n))).astype(np.complex64)


class CwZeroBeat(unittest.TestCase):
    def test_finds_the_carrier(self):
        for off, snr in ((-230.0, 10), (85.0, 3), (310.0, 15)):
            f = autotune.estimate_cw(keyed(2.0, off, snr, seed=int(abs(off))), FS)
            self.assertIsNotNone(f, (off, snr))
            self.assertLess(abs(f - off), 3.0, (off, snr, f))

    def test_noise_only(self):
        rng = np.random.default_rng(5)
        x = (rng.standard_normal(64000) + 1j * rng.standard_normal(64000)).astype(np.complex64)
        self.assertIsNone(autotune.estimate_cw(x, FS))


if __name__ == "__main__":
    unittest.main()

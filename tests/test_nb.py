"""Tests of the NB key (sdr.NoiseBlanker): pulses blanked in wideband samples, stations and noise left alone.

Run: python -m unittest tests.test_nb   (from the RADIMCOM folder)
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sdr  # noqa: E402

FS = 2.4e6
N = int(FS * 0.5)
T = np.arange(N) / FS


def noise(seed=1):
    rnd = np.random.default_rng(seed)
    return ((rnd.normal(size=N) + 1j * rnd.normal(size=N)) * 0.01 / np.sqrt(2)).astype(np.complex64)


def pulses(amp, count=50, seed=2):
    rnd = np.random.default_rng(seed)
    x = np.zeros(N, np.complex64)
    at = rnd.choice(N - 100, count, replace=False)
    for k in at:
        x[k:k + 8] = amp * np.exp(1j * rnd.uniform(0, 6.3)) * np.exp(-np.arange(8) / 3)
    return x, at


def blank(x, level=5):
    nb = sdr.NoiseBlanker()
    nb.level = level
    return np.concatenate([nb.process(x[i:i + 262144], FS) for i in range(0, N, 262144)]), nb


class NoiseBlanker(unittest.TestCase):
    def test_pulses_blanked(self):
        p, at = pulses(0.1)
        x = noise() + p
        y, nb = blank(x)
        self.assertTrue(all(y[k] == 0 for k in at))                     # every pulse peak zeroed
        self.assertLess(nb.blanked / N, 0.002)                          # and not much more
        self.assertTrue(np.array_equal(x, noise() + p))                 # the input (shared raw samples) unchanged

    def test_pulse_under_a_strong_station(self):
        station = (1.0 * np.exp(2j * np.pi * 300e3 * T) * (1 + 0.5 * np.sin(2 * np.pi * 1000 * T))).astype(np.complex64)
        p, at = pulses(1.5)
        y, _ = blank(noise() + station + p)
        self.assertGreater(np.mean([y[k] == 0 for k in at]), 0.9)

    def test_noise_and_stations_untouched(self):
        two = (1.0 * np.exp(2j * np.pi * 300e3 * T) + 0.7 * np.exp(-2j * np.pi * 600e3 * T)).astype(np.complex64)
        for x in (noise(), noise() + two):
            for level in (1, 5, 8):
                y, nb = blank(x, level)
                self.assertEqual(nb.blanked, 0, f"level {level}")

    def test_level_order(self):
        self.assertGreater(sdr.NoiseBlanker().k(), 0)
        ks = []
        for lv in (1, 5, 10):
            nb = sdr.NoiseBlanker()
            nb.level = lv
            ks.append(nb.k())
        self.assertTrue(ks[0] > ks[1] > ks[2])


if __name__ == "__main__":
    unittest.main()

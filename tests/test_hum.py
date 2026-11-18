"""Tests of the HUM key (sdr.HumFilter): mains hum and its harmonics out, the mains of the transmitter followed,
speech kept.

Run: python -m unittest tests.test_hum   (from the RADIMCOM folder)
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sdr  # noqa: E402

FS = 37500.0


def hum(base, secs=10, fs=FS):
    t = np.arange(int(fs * secs)) / fs
    return sum(0.3 / k * np.sin(2 * np.pi * base * k * t + k) for k in range(1, 12))


def run(x, base=50, width=sdr.HUM_WIDTH_DEFAULT_HZ, fs=FS):
    h = sdr.HumFilter()
    return np.concatenate([h.process(x[i:i + 2000], fs, base, width) for i in range(0, len(x), 2000)]), h


def left_db(y, x, fs=FS):
    s = int(6 * fs)
    return 10 * np.log10(np.mean(y[s:] ** 2) / np.mean(x[s:] ** 2))


class HumFilter(unittest.TestCase):
    def test_follows_the_mains_of_the_transmitter(self):
        for base, real in ((50, 50.0), (50, 49.96), (50, 50.3), (60, 59.8)):
            for fs in (32000.0, 37500.0):
                x = hum(real, fs=fs)
                y, h = run(x, base, fs=fs)
                self.assertAlmostEqual(h.f, real, delta=0.01, msg=f"{real} Hz at {fs}")
                self.assertLess(left_db(y, x, fs), -35, f"{real} Hz at {fs}")

    def test_speech_kept(self):
        rnd = np.random.default_rng(1)
        n = int(FS * 4)
        X = np.fft.rfft(rnd.normal(size=n))
        f = np.fft.rfftfreq(n, 1 / FS)
        X[(f < 300) | (f > 3000)] = 0
        x = np.fft.irfft(X, n)
        y, h = run(x)
        loss = 10 * np.log10(np.mean(y[n // 2:] ** 2) / np.mean(x[n // 2:] ** 2))
        self.assertGreater(loss, -0.8)                       # no hum: no notch in use
        self.assertAlmostEqual(h.f, 50.0, delta=0.5)         # no hum: stays near the base

    def test_hum_under_speech(self):
        rnd = np.random.default_rng(2)
        n = int(FS * 10)
        X = np.fft.rfft(rnd.normal(size=n))
        f = np.fft.rfftfreq(n, 1 / FS)
        X[(f < 300) | (f > 3000)] = 0
        speech = np.fft.irfft(X, n) * 0.3
        x = speech + hum(49.97)
        y, h = run(x)
        s = int(6 * FS)
        before = 10 * np.log10(np.mean((x - speech)[s:] ** 2))
        after = 10 * np.log10(np.mean((y - speech)[s:] ** 2))   # what is left besides the speech (hum + the notches)
        print(f"\nhum under speech: -{before - after:.1f} dB, mains found {h.f:.3f} Hz")
        self.assertLess(after, before - 10)
        self.assertAlmostEqual(h.f, 49.97, delta=0.02)


if __name__ == "__main__":
    unittest.main()

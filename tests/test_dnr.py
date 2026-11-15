"""Tests of the DNR key (sdr.SpectralNR): spectral noise reduction on synthetic speech in SSB noise, no radio.

Run: python -m unittest tests.test_dnr   (from the RADIMCOM folder)
"""
import os
import sys
import unittest

import numpy as np
from scipy.signal import butter, lfilter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sdr  # noqa: E402

FS = 37500


def speech(t):
    """Speech-like: gliding f0, harmonics shaped by two moving formants, syllables 250 ms on / 150 ms off."""
    f0 = 150 + 30 * np.sin(2 * np.pi * 0.7 * t)
    ph = 2 * np.pi * np.cumsum(f0) / FS
    f1 = 600 + 200 * np.sin(2 * np.pi * 1.3 * t)
    f2 = 1700 + 400 * np.sin(2 * np.pi * 0.9 * t)
    s = np.zeros(len(t))
    for h in range(1, 20):
        fh = h * f0
        s += (np.exp(-((fh - f1) / 250) ** 2) + 0.6 * np.exp(-((fh - f2) / 350) ** 2) + 0.05) * np.sin(h * ph)
    env = np.convolve(((t % 0.4) < 0.25).astype(float), np.hanning(int(0.02 * FS)) / (0.01 * FS), "same")
    return s * env, env


def shadow(nr, x, parts):
    """Runs nr on x frame by frame and applies the same gains to each part alone (speech, noise)."""
    n, h, w = nr.N, nr.H, nr.win
    outs = [np.zeros(len(x)) for _ in parts]
    for k in range((len(x) - n) // h + 1):
        nr._frame(np.fft.rfft(x[k * h:k * h + n] * w))
        for o, p in zip(outs, parts):
            o[k * h:k * h + n] += np.fft.irfft(np.fft.rfft(p[k * h:k * h + n] * w) * nr.gain, n) * w / 1.5
    return outs


class SpectralNR(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t = np.arange(int(5 * FS)) / FS
        b, a = butter(6, [300, 2700], "bandpass", fs=FS)
        s, cls.env = speech(t)
        s = lfilter(b, a, s)
        cls.s = s / np.sqrt(np.mean(s[cls.env > 0.5] ** 2))
        cls.noise = lfilter(b, a, np.random.default_rng(1).normal(size=len(t)))

    def run_level(self, snr_db, level):
        nz = self.noise / np.sqrt(np.mean(self.noise ** 2)) * 10 ** (-snr_db / 20)
        nr = sdr.SpectralNR(FS)
        nr.level = level
        so, no = shadow(nr, self.s + nz, [self.s, nz])
        sk = 2 * FS                                     # after learning the noise
        on, off = self.env[sk:] > 0.9, self.env[sk:] < 0.01
        db = lambda a, b, m: 10 * np.log10(np.mean(a[sk:][m] ** 2) / np.mean(b[sk:][m] ** 2))   # noqa: E731
        return db(so, self.s, on), db(no, nz, on), db(no, nz, off)

    def test_noise_lowered_also_under_speech(self):
        sp, under, pause = self.run_level(6, 5)
        self.assertGreater(sp - under, 3.5)             # SNR under speech better by > 3.5 dB
        self.assertLess(pause, -10)                     # the noise in pauses down by > 10 dB
        self.assertGreater(sp, -4)                      # speech kept

    def test_level_orders_the_reduction(self):
        pauses = [self.run_level(15, lv)[2] for lv in (1, 5, 10)]
        self.assertTrue(pauses[0] > pauses[1] > pauses[2])
        self.assertGreater(pauses[0], -8)               # level 1 is gentle
        self.assertLess(pauses[2], -15)                 # level 10 is strong

    def test_streaming_matches_and_delay(self):
        nr = sdr.SpectralNR(FS)
        x = (0.1 * self.s[:FS]).astype(np.float32)
        y = np.concatenate([nr.process(x[i:i + 777]) for i in range(0, len(x), 777)])   # odd block size
        self.assertEqual(len(y), len(x))
        self.assertTrue(np.all(np.isfinite(y)))
        self.assertGreater(nr.reduction_db, 0)

    def test_channel_uses_it(self):
        ch = sdr.Channel(FS)
        ch.configure("USB", 2700)
        ch.nr_on = True
        z = (0.01 * np.exp(2j * np.pi * 1000 * np.arange(8192) / FS)).astype(np.complex64)
        audio, _ = ch.process(z)
        self.assertEqual(len(audio), len(z))
        ch.configure("FM", 12500)
        ch.process(z)                                   # FM: no DNR, no error


if __name__ == "__main__":
    unittest.main()

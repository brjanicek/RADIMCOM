"""nrx.py: NR4 (SpecBleach) on synthetic SSB speech, its faster tracking of a rising noise than the Wiener DNR,
the streaming interpolation of RNN and RNN itself when lib\\rnnoise\\rnnoise.dll is there.

Run: python -m unittest tests.test_nrx
"""
import os
import sys
import unittest

import numpy as np
from scipy.signal import butter, lfilter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nrx  # noqa: E402
import sdr  # noqa: E402
from tests.test_dnr import FS, shadow, speech  # noqa: E402


class Nr4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t = np.arange(int(6 * FS)) / FS
        b, a = butter(6, [300, 2700], "bandpass", fs=FS)
        s, cls.env = speech(t)
        s = lfilter(b, a, s)
        cls.s = s / np.sqrt(np.mean(s[cls.env > 0.5] ** 2))
        n = lfilter(b, a, np.random.default_rng(2).normal(size=len(t)))
        cls.noise = n / np.sqrt(np.mean(n ** 2))

    def run_nr(self, nr, nz, sk):
        so, no = shadow(nr, self.s + nz, [self.s, nz])
        on, off = self.env[sk:] > 0.9, self.env[sk:] < 0.01
        db = lambda a, b, m: 10 * np.log10(np.mean(a[sk:][m] ** 2) / np.mean(b[sk:][m] ** 2))   # noqa: E731
        return db(so, self.s, on), db(no, nz, on), db(no, nz, off)

    def test_noise_lowered_speech_kept(self):
        nr = nrx.SpecBleach(FS)
        nr.level = 5
        sp, under, pause = self.run_nr(nr, self.noise * 10 ** (-6 / 20), 2 * FS)
        self.assertGreater(sp - under, 3.0)            # SNR under speech (DNR: 3.5; NR4 trades a little for tracking)
        self.assertLess(pause, -10)
        self.assertGreater(sp, -4)

    def test_follows_a_rising_noise_faster(self):
        nz = self.noise * 10 ** (-10 / 20)
        nz[3 * FS:] *= 10 ** (12 / 20)                  # the band noise rises by 12 dB at 3 s
        sk = int(3.4 * FS)                              # 0.4 s after the step
        res = {}
        for name, nr in (("nr4", nrx.SpecBleach(FS)), ("wiener", sdr.SpectralNR(FS))):
            nr.level = 5
            so, no = shadow(nr, self.s + nz, [self.s, nz])
            m = (self.env < 0.01)[sk:sk + FS]
            res[name] = 10 * np.log10(np.mean(no[sk:sk + FS][m] ** 2) / np.mean(nz[sk:sk + FS][m] ** 2))
        self.assertLess(res["nr4"], -8, res)            # tuned: NR4 -9.4 dB, the Wiener DNR -1.2 dB
        self.assertLess(res["nr4"], res["wiener"] - 5, res)

    def test_streaming(self):
        nr = nrx.SpecBleach(FS)
        x = (0.1 * (self.s[:FS] + self.noise[:FS])).astype(np.float32)
        y = np.concatenate([nr.process(x[i:i + 777]) for i in range(0, len(x), 777)])
        self.assertEqual(len(y), len(x))
        self.assertTrue(np.all(np.isfinite(y)))

    def test_channel_algorithms(self):
        ch = sdr.Channel(FS)
        ch.configure("USB", 2700)
        ch.nr_on = True
        z = (0.01 * np.exp(2j * np.pi * 1000 * np.arange(8192) / FS)).astype(np.complex64)
        for algo in nrx.ALGOS:
            ch.nr_algo = algo
            audio, _ = ch.process(z)
            self.assertEqual(len(audio), len(z))


class Interp(unittest.TestCase):
    def test_rate_and_shape(self):
        fs = 37500
        x = np.sin(2 * np.pi * 700 * np.arange(fs) / fs)
        up, down = nrx._Interp(fs, 48000), nrx._Interp(48000, fs)
        y48 = np.concatenate([up.process(x[i:i + 1000]) for i in range(0, fs, 1000)])
        self.assertLess(abs(len(y48) - 48000), 2)
        back = np.concatenate([down.process(y48[i:i + 1234]) for i in range(0, len(y48), 1234)])
        self.assertLess(abs(len(back) - fs), 2)
        self.assertLess(float(np.max(np.abs(back[100:fs - 100] - x[100:fs - 100]))), 0.02)


@unittest.skipIf(nrx.rnn_library() is None, "lib\\rnnoise\\rnnoise.dll not installed")
class Rnn(unittest.TestCase):
    def test_runs_and_lowers_noise(self):
        rng = np.random.default_rng(3)
        x = (0.05 * rng.normal(size=3 * FS)).astype(np.float32)
        nr = nrx.RnNoise(FS)
        y = np.concatenate([nr.process(x[i:i + 2048]) for i in range(0, len(x), 2048)])
        self.assertEqual(len(y), len(x))
        self.assertLess(np.mean(y[FS:] ** 2), 0.3 * np.mean(x[FS:] ** 2))


if __name__ == "__main__":
    unittest.main()

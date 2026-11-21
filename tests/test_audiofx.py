"""audiofx.py: TNF notch depth and width, APF on the CW pitch, BIN pseudo-stereo, Shift+click toggling."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import audiofx  # noqa: E402

FS = 32000.0


def tone(f, n=32000, cplx=True):
    t = np.arange(n) / FS
    return (np.exp(2j * np.pi * f * t) if cplx else np.sin(2 * np.pi * f * t)).astype(np.complex64 if cplx else np.float32)


def db(x):
    return 10 * np.log10(np.mean(np.abs(x[len(x) // 2:]) ** 2) + 1e-30)


class Tnf(unittest.TestCase):
    def test_notch_on_its_frequency_only(self):
        f = audiofx.Tnf()
        out = np.concatenate([f.process(b, FS, [600.0], 50) for b in np.split(tone(600.0), 8)])
        self.assertLess(db(out), -30)
        g = audiofx.Tnf()
        out = np.concatenate([g.process(b, FS, [600.0], 50) for b in np.split(tone(-600.0), 8)])
        self.assertGreater(db(out), -0.5)              # complex: the mirror frequency stays
        h = audiofx.Tnf()
        self.assertGreater(db(h.process(tone(900.0), FS, [600.0], 50)), -0.5)

    def test_toggle(self):
        n = audiofx.tnf_toggle([], 7030000)
        n = audiofx.tnf_toggle(n, 7031000)
        self.assertEqual(n, [7030000.0, 7031000.0])
        self.assertEqual(audiofx.tnf_toggle(n, 7030100), [7031000.0])


class Apf(unittest.TestCase):
    def test_peak_on_pitch(self):
        a = audiofx.Apf()
        on = db(a.process(tone(700.0, cplx=False), FS, 700.0, 100))
        a = audiofx.Apf()
        off = db(a.process(tone(1000.0, cplx=False), FS, 700.0, 100))
        self.assertGreater(on, -4)
        self.assertLess(off, -20)


class Binaural(unittest.TestCase):
    def test_quadrature(self):
        b = audiofx.Binaural()
        x = tone(800.0, cplx=False)
        y = np.concatenate([b.process(p) for p in np.split(x, 8)])
        left, right = y[4000:, 0], y[4000:, 1]
        self.assertAlmostEqual(float(np.std(left)), float(np.std(right)), delta=0.05)
        self.assertLess(abs(float(np.corrcoef(left, right)[0, 1])), 0.05)     # 90 degrees apart


if __name__ == "__main__":
    unittest.main()

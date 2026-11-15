"""AGC+ presets (SAGC_PRESETS in static/app.js) on a simulated band with rare strong bursts:
CONSERVATIVE must clip less than CAREFUL and keep more headroom.

Run: python -m unittest tests.test_sagc   (from the RADIMCOM folder)
"""
import os
import re
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import sdr  # noqa: E402

GAINS = [0.0, 0.9, 1.4, 2.7, 3.7, 7.7, 8.7, 12.5, 14.4, 15.7, 16.6, 19.7, 20.7, 22.9, 25.4, 28.0, 29.7, 32.8,
         33.8, 36.4, 37.2, 38.6, 40.2, 42.1, 43.4, 43.9, 44.5, 48.0, 49.6]     # R820T


def presets():
    """SAGC_PRESETS parsed from app.js, so the test follows the page."""
    js = open(os.path.join(ROOT, "static", "app.js"), encoding="utf-8").read()
    body = js[js.index("const SAGC_PRESETS = {"):]
    body = body[:body.index("\n};")]
    out = {}
    for name, fields in re.findall(r"(\w+): \{([^}]*)\}", body):
        out[name] = {k: float(v) for k, v in re.findall(r"(\w+): (-?[\d.]+)", fields)}
    return out


def simulate(p, seconds=600, block_s=0.1, seed=3):
    """Band = noise and a steady station (−45 dBFS at 0 dB gain) plus bursts up to 12 dB stronger, a few a minute.
    Returns (share of blocks clipped, median A/D peak dBFS)."""
    rnd = np.random.default_rng(seed)
    agc, gain, n = sdr.SmartAgc(), 20.7, 16384
    clipped, peaks = 0, []
    for i in range(int(seconds / block_s)):
        amp = 10 ** ((-45 + gain) / 20)
        if rnd.random() < 0.006:                          # ~4 bursts a minute
            amp *= 10 ** (rnd.uniform(3, 12) / 20)
        x = amp * (rnd.normal(size=n) * 0.5 + np.cos(np.arange(n) * 0.3))
        raw = np.clip(np.round(x * 127.5 + 127.5), 0, 255).astype(np.uint8)
        new = agc.step(raw, GAINS, gain, block_s, 0, p)
        clipped += agc.clip > 0
        if i > 600:
            peaks.append(20 * np.log10(max(agc.peak, 1e-4)))
        if new is not None:
            gain = new
    return clipped / (seconds / block_s), float(np.median(peaks))


class Presets(unittest.TestCase):
    def test_conservative_clips_less(self):
        pre = presets()
        self.assertIn("conservative", pre)
        for k, (d, lo, hi) in sdr.SAGC_PARAMS.items():
            self.assertTrue(lo <= pre["conservative"][k] <= hi, k)     # the server accepts every value
        cons, careful = simulate(pre["conservative"]), simulate(pre["careful"])
        print(f"\nclipped blocks / median peak: conservative {cons[0]:.4f} / {cons[1]:.1f} dBFS, "
              f"careful {careful[0]:.4f} / {careful[1]:.1f} dBFS")
        self.assertLess(cons[0], careful[0] / 2)
        self.assertLess(cons[1], careful[1] - 3)


if __name__ == "__main__":
    unittest.main()

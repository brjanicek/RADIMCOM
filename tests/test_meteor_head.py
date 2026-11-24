"""meteor_head.py: a weak head echo (the power along the lines ending at the trail) and its false alarms on noise."""
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meteor  # noqa: E402
import meteor_head as mh  # noqa: E402
import meteor_sat as ms  # noqa: E402
from tests.test_meteor import baseband, chirp, run, T0  # noqa: E402


def noise_spec(fs, secs, seed):
    n = 1 << int(round(np.log2(max(64.0, fs / 64.0))))
    sp = ms.Spec(fs, 1000.0, n, n // 2, 5000.0, 1, secs, False, meteor.WF_DB, secs)
    rng = np.random.default_rng(seed)
    x = (rng.standard_normal(int(fs * secs)) + 1j * rng.standard_normal(int(fs * secs))).astype(np.complex64)
    for i in range(0, len(x), 2048):
        sp.feed(x[i:i + 2048], 1e9 + (i + 2048) / fs, 10.0)
    return sp


class HeadTest(unittest.TestCase):
    def test_slopes_dense(self):
        """Each next slope moves the far end of the line by at most half a bin."""
        s = mh.slopes(62.5, 0.008)
        pos = s[s > 0]
        self.assertAlmostEqual(pos[0], meteor.mp.HEAD_RATE_MIN, delta=1)
        for a, b in zip(pos, pos[1:]):
            reach = min(mh.HEAD_SPAN_HZ, a * mh.HEAD_MAX_S)
            self.assertLessEqual((b - a) / a * reach, 62.5 / 2 + 1e-6)

    def test_quiet_on_noise(self):
        """Noise alone: no head echo at 60 echo positions, plain power and the clipped power of a detail."""
        sp = noise_spec(16000.0, 34.0, 4)
        raw, ring = list(sp.raw), list(sp.ring)
        alarms = 0
        for t_e in np.arange(1e9 + 5, 1e9 + 33, 0.5):
            r = mh.weak([x for x in raw if t_e - 1.5 <= x[0] <= t_e + 0.5], sp.hz, sp.dt, sp.bin, t_e, 8.0, 150.0)
            h = [x for x in ring if t_e - 1.5 <= x[0] <= t_e + 0.5]
            r8 = mh.weak(mh.from_db8(h[0][0], sp.dt, len(h), len(sp.hz), b"".join(c for _, c in h), meteor.WF_DB),
                         sp.hz, sp.dt, sp.bin, t_e, 8.0, 150.0, z_min=mh.HEAD_Z_DB8)
            alarms += (r is not None) + (r8 is not None)
        self.assertEqual(alarms, 0)

    def test_weak_head_found(self):
        """A faint head echo (+1500 -> +150 Hz in 0.3 s) onto a ping: too weak for _head_find (its points one by one),
        found along its line, with its slope; the ping stays a meteor."""
        x = chirp(baseband(10, [(5.0, 5.4, 60.0, 0.3, 0.0)], seed=11), 4.7, 5.0, 1500.0, 150.0, 0.15)
        with tempfile.TemporaryDirectory() as dd:
            c = meteor.MeteorCounter(path=os.path.join(dd, "m.json"))
            c.set_head(True)
            ev, c = run(x, c)
        self.assertEqual([e["kind"] for e in ev], ["under"], ev)
        h = ev[0]["head"]
        self.assertIsNotNone(h, ev)
        self.assertTrue(h.get("weak"), h)
        self.assertAlmostEqual(h["slope"], -4500, delta=1500)
        self.assertGreaterEqual(h["z"], mh.HEAD_Z)
        self.assertAlmostEqual(ev[0]["ts"] - T0, 5.0, delta=0.3)


if __name__ == "__main__":
    unittest.main()

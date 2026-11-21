"""meteor.py: echoes of the GRAVES carrier in a synthetic baseband (VFO on 143.049 MHz USB: the carrier at +1000 Hz)."""
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meteor  # noqa: E402

FS = 32000.0
DIAL = meteor.DIAL_USB_HZ
BLOCK = 2048
T0 = 1_800_000_000.0


def baseband(secs, tones=(), noise=1.0, step=None, seed=1):
    """tones: (t_from, t_to, offset Hz from the carrier, amplitude, drift Hz/s); step: (t, factor) broadband level jump."""
    rng = np.random.default_rng(seed)
    n = int(secs * FS)
    t = np.arange(n) / FS
    x = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * noise
    if step:
        x[t >= step[0]] *= step[1]
    for a, b, off, amp, drift in tones:
        m = (t >= a) & (t < b)
        tt = t[m] - a
        f0 = meteor.GRAVES_HZ - DIAL + off
        x[m] += amp * np.exp(2j * np.pi * (f0 * tt + drift * tt * tt / 2))
    return x.astype(np.complex64)


def run(x, counter=None):
    events = []
    with tempfile.TemporaryDirectory() as d:
        c = counter or meteor.MeteorCounter(on_echo=events.append, path=os.path.join(d, "m.json"))
        c.on_echo = events.append
        c.set_enabled(True)
        for i in range(0, len(x), BLOCK):
            blk = x[i:i + BLOCK]
            c.feed(blk, FS, DIAL, now=T0 + (i + len(blk)) / FS)
        c.set_enabled(False)
        return events, c


class MeteorTest(unittest.TestCase):
    def test_underdense_ping(self):
        ev, c = run(baseband(10, [(5.0, 5.3, 40.0, 0.3, 0.0)]))
        self.assertEqual(len(ev), 1, ev)
        self.assertEqual(ev[0]["kind"], "under")
        self.assertAlmostEqual(ev[0]["doppler"], 40, delta=8)
        self.assertAlmostEqual(ev[0]["ts"] - T0, 5.0, delta=0.3)
        self.assertGreater(ev[0]["snr"], 10)
        self.assertEqual(c.summary(T0 + 10)["this_hour"], 1)

    def test_overdense_echo(self):
        ev, _ = run(baseband(12, [(5.0, 8.0, -60.0, 0.3, 0.0)]))
        self.assertEqual([e["kind"] for e in ev], ["over"])
        self.assertAlmostEqual(ev[0]["dur"], 3.0, delta=0.4)

    def test_steady_carrier_ignored(self):
        ev, _ = run(baseband(15, [(0.0, 15.0, 20.0, 0.5, 0.0)]))
        self.assertEqual(ev, [])

    def test_broadband_step_ignored(self):
        ev, _ = run(baseband(12, step=(5.0, 10.0)))
        self.assertEqual(ev, [])

    def test_aircraft_drift(self):
        ev, c = run(baseband(14, [(4.0, 10.0, -100.0, 0.3, 30.0)]))
        self.assertTrue(ev)
        self.assertTrue(all(e["kind"] == "plane" for e in ev), ev)
        self.assertEqual(c.summary(T0 + 14)["this_hour"], 0)

    def test_noise_only_quiet(self):
        ev, _ = run(baseband(30, seed=7))
        self.assertEqual(ev, [])

    def test_not_tuned(self):
        with tempfile.TemporaryDirectory() as d:
            c = meteor.MeteorCounter(path=os.path.join(d, "m.json"))
            c.set_enabled(True)
            c.feed(baseband(1), FS, 145_500_000.0, now=T0)
            self.assertIn("outside", c.status)

    def test_stats_saved(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.json")
            c = meteor.MeteorCounter(path=p)
            run(baseband(10, [(5.0, 5.3, 40.0, 0.3, 0.0)]), c)
            c2 = meteor.MeteorCounter(path=p)
            s = c2.summary(T0 + 10)
            self.assertEqual(s["this_hour"], 1)
            self.assertAlmostEqual(s["hours"][-1][3], 10.0, delta=0.5)
            self.assertEqual(sum(d[1] for d in s["days"]), 1)

    def test_graves_path(self):
        p = meteor.graves_path(48.7, 17.9)          # western Slovakia
        self.assertAlmostEqual(p["az"], 265, delta=3)
        self.assertAlmostEqual(p["km"], 930, delta=30)
        self.assertTrue(5 < p["el"] < 15, p)
        self.assertGreater(meteor.graves_path(47.5, 9.0)["el"], p["el"])   # closer: the meteor zone is higher


if __name__ == "__main__":
    unittest.main()

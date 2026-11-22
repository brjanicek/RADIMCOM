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


def chirp(x, t_from, t_to, f_from, f_to, amp):
    """Adds a linear sweep (a head echo) from f_from to f_to Hz off the carrier."""
    t = np.arange(len(x)) / FS
    m = (t >= t_from) & (t < t_to)
    tt = t[m] - t_from
    k = (f_to - f_from) / (t_to - t_from)
    f0 = meteor.GRAVES_HZ - DIAL + f_from
    x[m] += (amp * np.exp(2j * np.pi * (f0 * tt + k * tt * tt / 2))).astype(np.complex64)
    return x


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

    def test_waterfall_shows_ping(self):
        """The small waterfall: a column per scope point, the ping bright in its Doppler bin, quiet elsewhere."""
        import base64
        _, c = run(baseband(10, [(5.0, 5.3, 40.0, 0.3, 0.0)]))
        meteor.time.time, real = (lambda: T0 + 10), meteor.time.time       # the view ends at the end of the test signal
        try:
            w = c.waterfall(span=30)
            wide = c.waterfall(span=3600)
            later = c.waterfall(since_k=10 ** 12, span=30)
        finally:
            meteor.time.time = real
        hz = np.array(w["hz"])
        self.assertLessEqual(abs(hz[0]), meteor.WF_HZ + 1)
        self.assertGreater(len(w["cols"]), 20)
        self.assertEqual(later["cols"], [])
        self.assertLessEqual(len(wide["cols"]), 2)       # 7.5 s buckets: the 10 s are one or two columns
        cols = [(k * w["bucket_s"] - T0, np.frombuffer(base64.b64decode(b), np.uint8)) for k, b in w["cols"]]
        k = int(np.argmin(abs(hz - 40)))
        ping = max(col[k] for t, col in cols if 5.0 <= t <= 5.5)
        quiet = max(int(col.max()) for t, col in cols if t > 7)
        self.assertGreater(ping, 10 * 255 / meteor.WF_DB)       # over 10 dB
        self.assertLess(quiet, ping)

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

    def test_detail_of_echo(self):
        """The detail: full-resolution frames from 1 s before to 1 s after, the ping bright in its bin."""
        import base64
        ev, c = run(baseband(10, [(5.0, 5.3, 40.0, 0.3, 0.0)]))
        self.assertTrue(ev[0]["det"])
        self.assertIsNone(ev[0]["head"])
        d = c.detail(ev[0]["ts"])
        self.assertIsNotNone(d)
        self.assertIsNone(d["head"])            # HEAD off
        rows = np.frombuffer(base64.b64decode(d["rows"]), np.uint8).reshape(d["n"], len(d["hz"]))
        self.assertAlmostEqual(d["n"] * d["dt"], 0.3 + 2 * meteor.DETAIL_PRE_S, delta=0.4)
        k = int(np.argmin(abs(np.array(d["hz"]) - 40)))
        i = int(np.argmax(rows[:, k]))
        self.assertAlmostEqual(d["t0"] + i * d["dt"] - T0, 5.15, delta=0.3)
        self.assertGreater(rows[i, k], 10 * 255 / meteor.WF_DB)
        self.assertIsNone(c.detail(ev[0]["ts"] + 5))

    def test_head_echo(self):
        """HEAD on: a fast sweep (+3 kHz -> +100 Hz in 0.15 s) just before the trail ping is found with its slope."""
        x = chirp(baseband(10, [(5.0, 5.4, 60.0, 0.3, 0.0)]), 4.85, 5.0, 3000.0, 100.0, 0.6)
        with tempfile.TemporaryDirectory() as dd:
            c = meteor.MeteorCounter(path=os.path.join(dd, "m.json"))
            c.set_head(True)
            ev, c = run(x, c)
        self.assertEqual(len(ev), 1, ev)
        h = ev[0]["head"]
        self.assertIsNotNone(h, ev)
        self.assertAlmostEqual(h["slope"], -19333, delta=4000)
        self.assertGreater(c.head_hz, 3000)
        self.assertIsNotNone(c.detail(ev[0]["ts"])["head"])

    def test_head_quiet_on_ping(self):
        """HEAD on, a ping without a head echo (and noise): no head echo found."""
        with tempfile.TemporaryDirectory() as dd:
            c = meteor.MeteorCounter(path=os.path.join(dd, "m.json"))
            c.set_head(True)
            ev, c = run(baseband(30, [(5.0, 5.3, 40.0, 0.3, 0.0), (15.0, 17.0, -50.0, 0.3, 0.0)], seed=3), c)
        self.assertEqual(len(ev), 2, ev)
        self.assertTrue(all(e["head"] is None for e in ev), ev)

    def test_graves_path(self):
        p = meteor.graves_path(48.7, 17.9)          # western Slovakia
        self.assertAlmostEqual(p["az"], 265, delta=3)
        self.assertAlmostEqual(p["km"], 930, delta=30)
        self.assertTrue(5 < p["el"] < 15, p)
        self.assertGreater(meteor.graves_path(47.5, 9.0)["el"], p["el"])   # closer: the meteor zone is higher


if __name__ == "__main__":
    unittest.main()

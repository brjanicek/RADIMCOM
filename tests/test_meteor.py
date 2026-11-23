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

    def _sat_run(self, x, station=None):
        import threading
        with tempfile.TemporaryDirectory() as dd:
            c = meteor.MeteorCounter(path=os.path.join(dd, "m.json"))
            c.station = station
            ev, c = run(x, c)
            for th in threading.enumerate():        # the satellite echoes are reported from a thread
                if th.name == "meteor-sat":
                    th.join(10)
        return list(c.events), c

    def test_satellite_track(self):
        """A satellite: +1500 -> -1500 Hz in 20 s, cut into pieces by the beam; one SAT echo, no meteor counted."""
        x = baseband(30)
        for a in np.arange(4.0, 24.0, 3.0):           # 2 s on, 1 s off
            b = a + 2.0
            f_a, f_b = 1500 - 150 * (a - 4.0), 1500 - 150 * (b - 4.0)
            x = chirp(x, a, b, f_a, f_b, 0.15)
        ev, c = self._sat_run(x)
        sats = [e for e in ev if e["kind"] == "sat"]
        self.assertEqual(len(sats), 1, ev)
        s = sats[0]
        self.assertAlmostEqual(s["drift"], -150, delta=15)
        self.assertAlmostEqual(s["ts"] - T0, 4.0, delta=0.5)
        self.assertGreater(s["dur"], 17)
        self.assertEqual(s["sat"]["norad"], None)                   # no station: not identified
        self.assertEqual([e for e in ev if e["kind"] in ("under", "over")], [], ev)
        self.assertEqual(c.summary(T0 + 30)["this_hour"], 0)
        d = c.detail(s["ts"])
        self.assertEqual(d["echo"]["kind"], "sat")
        self.assertGreater(abs(d["hz"][0]), 7000)
        self.assertGreater(len(d["pts"]), 50)

    def test_fast_satellite_not_a_meteor(self):
        """A fast one crosses the ±500 Hz of the meteor detector in under a second: still SAT, not UNDER."""
        x = chirp(baseband(16), 5.0, 9.0, 2000.0, -2000.0, 0.3)
        ev, c = self._sat_run(x)
        self.assertEqual([e["kind"] for e in ev], ["sat"], ev)
        self.assertEqual(c.summary(T0 + 16)["this_hour"], 0)

    def test_meteor_still_counted(self):
        """The wide spectrum sees a meteor too, but its track does not drift: it stays a meteor."""
        ev, c = self._sat_run(baseband(12, [(5.0, 7.0, -60.0, 0.3, 0.0), (9.0, 9.3, 80.0, 0.3, 0.0)]))
        self.assertEqual([e["kind"] for e in ev], ["over", "under"], ev)

    def test_identify_iss(self):
        """The bistatic Doppler of the ISS over GRAVES and western Slovakia: found among four, with the receiver offset."""
        from sgp4.api import Satrec, SatrecArray
        import meteor_sat as ms
        tle = [("ISS (ZARYA)", "1 25544U 98067A   26326.17166235  .00010101  00000+0  18757-3 0  9993",
                "2 25544  51.6321 238.2738 0007393  52.3454 307.8204 15.49546258596247"),
               ("FUNCUBE-1 (AO-73)", "1 39444U 13066AE  26326.18876087  .00005672  00000+0  33441-3 0  9991",
                "2 39444  97.8472 301.3416 0035767  28.4133 331.9037 15.11455703703514"),
               ("NOAA 20 (JPSS-1)", "1 43013U 17073A   26326.24178322  .00000055  00000+0  46828-4 0  9998",
                "2 43013  98.7355 264.3976 0001382 122.6984 237.4325 14.19550807466892"),
               ("NOAA 21 (JPSS-2)", "1 54234U 22150A   26326.27213746  .00000039  00000+0  39071-4 0  9994",
                "2 54234  98.7218 262.4891 0002801  95.9965 264.1530 14.19560493208970")]
        sats = [Satrec.twoline2rv(a, b) for _, a, b in tle]
        el = (SatrecArray(sats), [n for n, _, _ in tle], [25544, 39444, 43013, 54234])
        qth = (48.7, 17.9)
        iss = SatrecArray(sats[:1])
        ep = (sats[0].jdsatepoch + sats[0].jdsatepochF - 2440587.5) * 86400
        tt = np.arange(ep, ep + 2 * 86400, 5.0)
        _, r, _ = ms._ecef(iss, tt)
        e_t = ms._look(r, ms._site(meteor.GRAVES_LAT, meteor.GRAVES_LON))[0][0]
        e_r = ms._look(r, ms._site(*qth))[0][0]
        both = np.nonzero((e_t > 10) & (e_r > 10))[0]
        self.assertTrue(len(both), "no common pass in 2 days")
        t = tt[both[0]] + np.arange(0, 30, 0.25)
        _, r, v = ms._ecef(iss, t)
        fd = ms.bistatic_doppler(r[0], v[0], ms._site(meteor.GRAVES_LAT, meteor.GRAVES_LON)[0], ms._site(*qth)[0], meteor.GRAVES_HZ)
        rng = np.random.default_rng(2)
        pts = list(zip(t, fd + 37 + rng.normal(0, 8, len(t))))
        res = ms.identify(pts, qth, (meteor.GRAVES_LAT, meteor.GRAVES_LON), meteor.GRAVES_HZ, elements=el)
        self.assertEqual(res["norad"], 25544, res)
        self.assertAlmostEqual(res["offset"], 37, delta=10)
        self.assertLess(res["rms"], 15)
        self.assertTrue(res["curve"])
        bad = ms.identify([(a, 3000.0 - 400 * (a - t[0])) for a in t], qth, (meteor.GRAVES_LAT, meteor.GRAVES_LON),
                          meteor.GRAVES_HZ, elements=el)
        self.assertIsNone(bad["norad"], bad)
        self.assertIsNone(ms.identify(pts, None)["norad"])

    def test_identify_aircraft(self):
        """An aircraft over southern Germany: its bistatic Doppler found among others; the receiver offset is known."""
        import meteor_air as ma
        import meteor_sat as ms
        qth, tx = (48.7, 17.9), (meteor.GRAVES_LAT, meteor.GRAVES_LON)
        mid = ma.midpoint(qth[0], qth[1], *tx)
        self.assertAlmostEqual(mid[0], 48.3, delta=0.5)
        self.assertAlmostEqual(mid[1], 11.8, delta=0.7)

        def rec(hexid, lat, lon, trk, gs=450, alt=37000, seen=2.0):
            return {"hex": hexid, "flight": hexid.upper() + "  ", "r": "D-" + hexid[:4].upper(), "t": "A320", "lat": lat,
                    "lon": lon, "alt_baro": alt, "gs": gs, "track": trk, "baro_rate": 0, "seen_pos": seen}
        ac = [rec("aaa111", mid[0] + 0.3, mid[1] - 0.5, 75), rec("bbb222", mid[0] - 0.4, mid[1] + 0.2, 300),
              rec("ccc333", mid[0], mid[1] + 0.8, 160, gs=380), rec("ddd444", 52.0, 13.0, 90),     # Berlin: too far
              {"hex": "eee555", "lat": mid[0], "lon": mid[1], "alt_baro": "ground", "gs": 10, "track": 0}]
        t_now = T0 + 30
        t = T0 + np.arange(0, 20, 0.25)
        st = ma._state(ac[1], t_now)
        r, v = ma._track(st, t)
        fd = ms.bistatic_doppler(r, v, ms._site(*tx)[0], ms._site(*qth)[0], meteor.GRAVES_HZ)
        rng = np.random.default_rng(4)
        pts = list(zip(t, fd + 12 + rng.normal(0, 4, len(t))))
        res = ma.identify(pts, qth, tx, meteor.GRAVES_HZ, ac, t_now, offset=10.0)
        self.assertEqual(res["hex"], "bbb222", res)
        self.assertEqual(res["flight"], "BBB222")
        self.assertEqual(res["candidates"], 3)
        self.assertLess(res["rms"], 10)
        self.assertEqual(len(res["curve"]), ma.AIR_POINTS)
        far = ma.identify(pts, qth, tx, meteor.GRAVES_HZ, ac, t_now, offset=150.0)     # offset known wrong: no fit
        self.assertIsNone(far["hex"], far)
        self.assertIsNone(ma.identify(pts, qth, tx, meteor.GRAVES_HZ, ac[3:], t_now)["hex"])

    def test_aircraft_echo_looked_up(self):
        """A PLANE echo with a station: adsb.fi asked (here faked) in a thread, the answer in the echo and its detail."""
        import threading
        import meteor_air as ma
        calls = []
        real_fetch, real_id = ma.fetch, ma.identify
        ma.fetch = lambda lat, lon, dist=250: (calls.append((lat, lon)) or (T0, []))
        ma.identify = lambda pts, qth, tx, f, ac, t_now, off: {"hex": "abc123", "flight": "TEST1", "rms": 5.0, "others": 0,
                                                              "curve": [[pts[0][0], 0.0], [pts[-1][0], 1.0]]}
        try:
            with tempfile.TemporaryDirectory() as dd:
                c = meteor.MeteorCounter(path=os.path.join(dd, "m.json"))
                c.station = lambda: (48.7, 17.9)
                ev, c = run(baseband(14, [(4.0, 10.0, -100.0, 0.3, 30.0)]), c)
                for th in threading.enumerate():
                    if th.name in ("meteor-air", "meteor-sat"):
                        th.join(10)
        finally:
            ma.fetch, ma.identify = real_fetch, real_id
        planes = [e for e in c.events if e["kind"] == "plane"]
        self.assertTrue(planes, list(c.events))
        self.assertEqual(planes[0]["air"]["flight"], "TEST1")
        self.assertTrue(calls)
        self.assertAlmostEqual(calls[0][1], 11.8, delta=0.7)          # the middle of the path, not the station
        self.assertEqual(c.detail(planes[0]["ts"])["curve"][1][1], 1.0)
        self.assertEqual(c.summary(T0 + 14)["planes"], len(planes))

    def test_rx_offset_from_satellites(self):
        with tempfile.TemporaryDirectory() as dd:
            p = os.path.join(dd, "m.json")
            c = meteor.MeteorCounter(path=p)
            self.assertEqual(c.rx_offset(), 0.0)
            c.rx_offsets = [[T0, 20], [T0 + 1, 30], [T0 + 2, 26]]
            c._dirty = True
            c.save()
            self.assertEqual(meteor.MeteorCounter(path=p).rx_offset(), 26.0)

    def test_graves_path(self):
        p = meteor.graves_path(48.7, 17.9)          # western Slovakia
        self.assertAlmostEqual(p["az"], 265, delta=3)
        self.assertAlmostEqual(p["km"], 930, delta=30)
        self.assertTrue(5 < p["el"] < 15, p)
        self.assertGreater(meteor.graves_path(47.5, 9.0)["el"], p["el"])   # closer: the meteor zone is higher


if __name__ == "__main__":
    unittest.main()

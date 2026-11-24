"""meteor.py: echoes of the GRAVES carrier in a synthetic baseband (VFO on 143.049 MHz USB: the carrier at +1000 Hz)."""
import os
import sys
import tempfile
import time
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
        ev, c = run(baseband(14, [(4.0, 10.0, -100.0, 0.3, 12.0)]))
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

    def _sat_run(self, x, station=None, counter=None):
        import threading
        with tempfile.TemporaryDirectory() as dd:
            c = counter or meteor.MeteorCounter(path=os.path.join(dd, "m.json"))
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
        # the detail only around the track (± SAT_DETAIL_MARGIN_HZ), not the whole ±8 kHz
        import base64
        self.assertAlmostEqual(d["hz"][0], -1500 - meteor.SAT_DETAIL_MARGIN_HZ, delta=150)
        self.assertAlmostEqual(d["hz"][-1], 1500 + meteor.SAT_DETAIL_MARGIN_HZ, delta=150)
        self.assertEqual(len(base64.b64decode(d["rows"])), d["n"] * len(d["hz"]))
        self.assertGreater(len(d["pts"]), 50)
        # its sound follows the Doppler: +1500 -> -1500 Hz would be 2500 -> -500 Hz on 143.049 USB, so the tone is moved
        # by one step (the middle to 1.5 kHz) and the 3 kHz sweep squeezed into TRACK_SPAN_HZ
        import io
        import wave
        import meteor_audio
        self.assertTrue(d["audio"])
        wav = c.audio(s["ts"])
        self.assertGreater(meteor_audio.duration_of(wav), 17)
        sh, k = c.details[s["ts"]]["wav_shift"], c.details[s["ts"]]["wav_k"]
        self.assertAlmostEqual(sh, -500, delta=30)
        self.assertAlmostEqual(k, meteor_audio.TRACK_SPAN_HZ / 3000, delta=0.05)
        with wave.open(io.BytesIO(wav)) as w:
            fs, a = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float)
        t_wav = c.details[s["ts"]]["wav_t0"]

        def tone(t_from):                   # the strongest tone 1 s from t_from (s after T0)
            i = int((T0 + t_from - t_wav) * fs)
            seg = a[i:i + fs] * np.hanning(fs)
            sp = np.abs(np.fft.rfft(seg))
            return np.fft.rfftfreq(fs, 1 / fs)[int(np.argmax(sp))]
        self.assertAlmostEqual(tone(10.0), 1500 + (1500 - 150 * 6.5) * k, delta=60)   # follows its Doppler then
        self.assertAlmostEqual(tone(16.0), 1500 + (1500 - 150 * 12.5) * k, delta=60)

    def test_sound_of_a_weak_satellite(self):
        """A satellite 15 dB under the noise of the 2.8 kHz audio band, sweeping 4 kHz: its sound is a tone following
        its Doppler (squeezed into 200–3000 Hz) clearly over the noise left around it."""
        import io
        import wave
        import meteor_audio
        fs = meteor_audio.RING_FS
        n = int(20 * fs)
        t = np.arange(n) / fs
        f = 2000.0 - 200.0 * t                                        # +2000 -> -2000 Hz
        rng = np.random.default_rng(3)
        noise = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) / np.sqrt(2)
        amp = np.sqrt(10 ** (-15 / 10) * 2800.0 / (fs / 2) * 2)      # -15 dB in 2.8 kHz of noise
        iq = (noise + amp * np.exp(2j * np.pi * np.cumsum(f) / fs)).astype(np.complex64)
        pts = [(tt, 2000.0 - 200.0 * tt + rng.normal(0, 5)) for tt in np.arange(0.0, 20.0, 0.25)]
        wav, sh, k = meteor_audio.track_wav(100.0, iq, fs, [(100.0 + a, b) for a, b in pts])
        self.assertAlmostEqual(k, meteor_audio.TRACK_SPAN_HZ / 4000, delta=0.05)
        with wave.open(io.BytesIO(wav)) as w:
            ofs, a = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float)
        for t_at in (3.0, 10.0, 17.0):
            i = int(t_at * ofs)
            seg = a[i:i + ofs] * np.hanning(ofs)
            sp = np.abs(np.fft.rfft(seg)) ** 2
            fq = np.fft.rfftfreq(ofs, 1 / ofs)
            want = 1500 + (2000.0 - 200.0 * (t_at + 0.5)) * k
            self.assertAlmostEqual(fq[int(np.argmax(sp))], want, delta=40)
            on = sp[np.abs(fq - want) <= 40].sum()
            self.assertGreater(on / max(sp[(fq > 200) & (fq < 3000)].sum() - on, 1e-9), 1.0)   # the tone over the rest

    def test_sound_of_a_ping(self):
        """▶ of a meteor: as on 143.049 USB, the ping at +40 Hz is a tone at 1040 Hz, about as long as the echo."""
        import meteor_audio
        ev, c = run(baseband(10, [(5.0, 5.5, 40.0, 0.3, 0.0)]))
        self.assertTrue(c.detail(ev[0]["ts"])["audio"])
        wav = c.audio(ev[0]["ts"])
        self.assertAlmostEqual(meteor_audio.tone_of(wav), 1040, delta=15)
        self.assertTrue(0.5 < meteor_audio.duration_of(wav) < 3.0)

    def test_fast_satellite_not_a_meteor(self):
        """A fast one crosses the ±500 Hz of the meteor detector in under a second: still SAT, not UNDER."""
        x = chirp(baseband(16), 5.0, 9.0, 2000.0, -2000.0, 0.3)
        ev, c = self._sat_run(x)
        self.assertEqual([e["kind"] for e in ev], ["sat"], ev)
        self.assertEqual(c.summary(T0 + 16)["this_hour"], 0)

    def test_slow_weak_satellite_in_pieces(self):
        """A weak satellite drifting -56 Hz/s (too weak for the wide spectrum) fading in and out: the first piece is a
        SAT, the next pieces on its line are not meteors (it was OVER, OVER, UNDER)."""
        def piece(a, b):
            return (a, b, 250.0 - 56.0 * (a - 4.0), 0.12, -56.0)
        x = baseband(18, [piece(4.0, 5.6), piece(8.0, 10.4), piece(10.9, 11.2)])
        ev, c = self._blind_run(x)
        self.assertEqual([e for e in ev if e["kind"] in ("under", "over")], [], ev)
        sats = [e for e in ev if e["kind"] == "sat"]
        self.assertEqual(len(sats), 1, ev)
        self.assertAlmostEqual(sats[0]["drift"], -56, delta=12)
        self.assertEqual(c.summary(T0 + 18)["this_hour"], 0)

    def test_meteor_after_a_slow_satellite(self):
        """A meteor 3 s after a slow satellite piece, but off its line: still a meteor."""
        x = baseband(14, [(4.0, 5.6, 250.0, 0.12, -56.0), (8.5, 8.8, 150.0, 0.3, 0.0)])
        ev, _ = self._blind_run(x)
        self.assertEqual([e["kind"] for e in ev], ["sat", "under"], ev)

    def test_short_meteor_on_a_satellite_line(self):
        """A short ping 2.8 s after a slow satellite piece, right where its line is expected (~0 Hz), but not drifting
        with it: a meteor (the Bayes factor of meteor_phys.py), not the satellite's next piece (it was SAT)."""
        x = baseband(14, [(4.0, 5.6, 250.0, 0.12, -56.0), (8.4, 8.7, 0.0, 0.3, 0.0)])
        ev, _ = self._blind_run(x)
        self.assertEqual([e["kind"] for e in ev], ["sat", "under"], ev)

    def test_head_echo_on_a_satellite_line_is_a_meteor(self):
        """A short ping where a slow satellite's line goes on, even drifting with it (the third piece of
        test_slow_weak_satellite_in_pieces: a SAT piece without the head echo), but with a head echo coming onto it
        (+3 kHz -> -120 Hz in 0.15 s): only a meteoroid does that, a meteor."""
        x = baseband(14, [(4.0, 5.6, 250.0, 0.12, -56.0), (8.0, 10.4, 250.0 - 56.0 * 4.0, 0.12, -56.0),
                          (10.9, 11.2, -136.0, 0.3, -56.0)])
        x = chirp(x, 10.75, 10.9, 3000.0, -120.0, 0.6)
        thr = meteor.SAT_THR_DB
        meteor.SAT_THR_DB = 60.0
        try:
            with tempfile.TemporaryDirectory() as dd:
                c = meteor.MeteorCounter(path=os.path.join(dd, "m.json"))
                c.set_head(True)
                ev, _ = self._sat_run(x, counter=c)
        finally:
            meteor.SAT_THR_DB = thr
        met = [e for e in ev if e["kind"] in ("under", "over")]
        self.assertEqual(len(met), 1, ev)
        self.assertAlmostEqual(met[0]["ts"] - T0, 10.9, delta=0.4)
        self.assertIsNotNone(met[0]["head"], met)

    def _blind_run(self, x):
        """_sat_run with the tracker of the wide spectrum blind (the satellite too weak for its short frames)."""
        thr = meteor.SAT_THR_DB
        meteor.SAT_THR_DB = 60.0
        try:
            return self._sat_run(x)
        finally:
            meteor.SAT_THR_DB = thr

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
                ev, c = run(baseband(14, [(4.0, 10.0, -100.0, 0.3, 12.0)]), c)
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

    def test_afc_first_meteor_then_median(self):
        """The receiver 200 Hz off: the first strong meteor moves the carrier there, the next ones are at ~0 Hz."""
        # 5.5 s apart: closer ones at one Doppler would join one track of the wide spectrum (gap SAT_GAP_S)
        tones = [(5.0 + 5.5 * i, 5.25 + 5.5 * i, 200.0 + (-15, 10, 0, 20, -5, 12, -8)[i], 0.3, 0.0) for i in range(7)]
        ev, c = run(baseband(45, tones))
        self.assertGreaterEqual(len(ev), 6, ev)
        self.assertAlmostEqual(ev[0]["doppler"], 185, delta=10)
        self.assertTrue(c.afc_locked)
        self.assertAlmostEqual(c.afc_hz, 200, delta=20)
        for e in ev[1:]:
            self.assertLess(abs(e["doppler"]), 40, ev)

    def test_afc_off_keeps_the_dial(self):
        with tempfile.TemporaryDirectory() as d:
            c = meteor.MeteorCounter(path=os.path.join(d, "m.json"))
            c.set_afc(False)
            ev, c = run(baseband(10, [(5.0, 5.25, 200.0, 0.3, 0.0), (7.0, 7.25, 200.0, 0.3, 0.0)]), c)
        self.assertEqual(c.afc_hz, 0.0)
        self.assertEqual([round(e["doppler"] / 10) for e in ev], [20, 20])

    def test_afc_finds_a_far_carrier_in_the_wide_spectrum(self):
        """3 kHz off (the meteor band ±500 Hz is empty): flashes without drift at one frequency of the wide spectrum."""
        real = meteor.AFC_DEAF_S
        meteor.AFC_DEAF_S = 3.0
        try:
            tones = [(5.0 + 5 * i, 5.3 + 5 * i, 3000.0 + 10 * i, 0.4, 0.0) for i in range(3)]
            tones.append((26.0, 26.3, 3005.0, 0.4, 0.0))
            ev, c = run(baseband(29, tones))
        finally:
            meteor.AFC_DEAF_S = real
        self.assertAlmostEqual(c.afc_hz, 3005, delta=30)
        self.assertTrue(ev and abs(ev[-1]["doppler"]) < 40, ev)

    def test_wide_waterfall(self):
        """±8 kHz: a satellite-like tone 4 kHz off is in it, not in the meteor band."""
        import base64
        _, c = run(baseband(10, [(4.0, 9.0, 4000.0, 0.3, 0.0)]))
        meteor.time.time, real = (lambda: T0 + 10), meteor.time.time
        try:
            w = c.waterfall(span=30, wide=True)
        finally:
            meteor.time.time = real
        hz = np.array(w["hz"])
        self.assertLess(hz[0], -7000)
        self.assertGreater(hz[-1], 7000)
        self.assertLessEqual(len(hz), meteor.WFW_BINS)
        cols = [np.frombuffer(base64.b64decode(b), np.uint8) for _, b in w["cols"]]
        k = int(np.argmin(abs(hz - 4000)))
        self.assertGreater(max(int(col[k]) for col in cols), 10 * 255 / meteor.WF_DB)

    def test_fine_waterfall(self):
        """The meteor band in 1 Hz x 16 ms: two tones 6 Hz apart are two lines with a gap between them, a ping starts
        and ends in the right cells; ±250 Hz is a part of it; the long views get the coarser columns; the detail of
        the ping gets the fine cells too."""
        import base64
        _, c = run(baseband(11, [(5.0, 10.0, 100.0, 0.1, 0.0), (5.0, 10.0, 106.0, 0.1, 0.0),
                                 (7.0, 7.2, -60.0, 0.3, 0.0)]))
        meteor.time.time, real = (lambda: T0 + 10.5), meteor.time.time
        try:
            w = c.waterfall(span=10, cols=1000)
            nw = c.waterfall(span=10, wide="narrow", cols=1000)
            lw = c.waterfall(span=600, cols=1000)
        finally:
            meteor.time.time = real
        cell = meteor.meteor_fine.CELL_S
        self.assertAlmostEqual(w["bucket_s"], cell)
        hz = np.array(w["hz"])
        self.assertEqual(len(hz), 2 * int(meteor.FINE_HZ) + 1)        # 1001 rows of 1 Hz
        self.assertEqual(nw["hz"][0], -meteor.NARROW_HZ)
        self.assertEqual(len(nw["hz"]), 2 * int(meteor.NARROW_HZ) + 1)
        self.assertEqual(len(base64.b64decode(nw["cols"][0][1])), len(nw["hz"]))
        self.assertAlmostEqual(lw["bucket_s"], 0.6)                    # 600 s in 1000 columns, from the coarse ones
        ks = np.array([k for k, _ in w["cols"]])
        self.assertEqual(len(ks), ks[-1] - ks[0] + 1)               # every 16 ms cell, none merged with the next
        cols = np.array([np.frombuffer(base64.b64decode(b), np.uint8) for _, b in w["cols"]], int)
        a, b, mid, p = (int(np.argmin(abs(hz - f))) for f in (100, 106, 103, -60))
        steady = cols[(ks * cell > T0 + 5.5) & (ks * cell < T0 + 6.5)].mean(axis=0)
        self.assertGreater(steady[a], 6 * 255 / meteor.WF_DB)
        self.assertGreater(steady[b], 6 * 255 / meteor.WF_DB)
        self.assertLess(steady[mid], min(steady[a], steady[b]) - 6 * 255 / meteor.WF_DB)
        hot = ks[cols[:, p] > 10 * 255 / meteor.WF_DB] * cell - T0
        self.assertAlmostEqual(hot.min(), 7.0, delta=0.03)
        self.assertAlmostEqual(hot.max(), 7.2, delta=0.03)
        ev, c = run(baseband(15, [(6.0, 6.2, -60.0, 0.3, 0.0)]))     # alone (the tones above are an echo too)
        self.assertEqual(len(ev), 1, ev)
        d = c.detail(ev[0]["ts"])
        self.assertTrue(d["fine"])
        self.assertEqual(len(d["hz"]), 2 * int(meteor.DETAIL_FINE_HZ) + 1)     # ±150 Hz around the echo, 1 Hz
        self.assertAlmostEqual(d["hz"][0], ev[0]["doppler"] - meteor.DETAIL_FINE_HZ, delta=1)
        self.assertAlmostEqual(d["dt"], cell)
        self.assertEqual(len(base64.b64decode(d["rows"])), d["n"] * len(d["hz"]))

    def test_slow_head_echo_in_the_fine_cells(self):
        """As seen on the air: the Doppler comes down +150 -> +16 Hz in 0.25 s just before the trail echo at +16 Hz:
        too slow for the head echo spectrum, found in the fine cells; the detail is ±DETAIL_FINE_HZ around the echo.
        A ping alone has none."""
        x = baseband(15, [(6.0, 6.6, 16.0, 0.3, 0.0)])
        chirp(x, 5.75, 6.0, 150.0, 16.0, 0.15)
        ev, c = run(x)
        self.assertEqual(len(ev), 1, ev)
        h = ev[0]["head"]
        self.assertTrue(h and h.get("fine"), ev[0])
        self.assertAlmostEqual(h["slope"], -536, delta=150)
        self.assertGreater(h["f0"], 100)
        self.assertAlmostEqual(h["t"], 0.25, delta=0.1)
        d = c.detail(ev[0]["ts"])
        self.assertTrue(d["fine"])
        self.assertLessEqual(d["hz"][0], h["f1"] - 30)
        self.assertGreaterEqual(d["hz"][-1], h["f0"] + 29)
        self.assertLess(len(d["hz"]), 2 * meteor.FINE_HZ)
        ev2, _ = run(baseband(15, [(6.0, 6.6, 16.0, 0.3, 0.0)], seed=4))
        self.assertEqual(len(ev2), 1, ev2)
        self.assertIsNone(ev2[0]["head"])

    def test_curved_head_echo(self):
        """As seen on the air: the head echo brakes onto the trail (+424 -> +24 Hz, exponentially, in 0.6 s), and the
        detector starts on its end, before the trail: still found (a curve, not a line)."""
        x = baseband(12, [(6.0, 7.2, 24.0, 0.3, 0.0)])
        t = np.arange(len(x)) / FS
        m = (t >= 5.4) & (t < 6.0)
        tt = t[m] - 5.4
        f0 = meteor.GRAVES_HZ - DIAL
        x[m] += (0.2 * np.exp(2j * np.pi * (f0 * tt + 24.0 * tt + 400 * 0.15 * (1 - np.exp(-tt / 0.15))))).astype(np.complex64)
        ev, _ = run(x)
        hs = [e["head"] for e in ev if e["head"]]
        self.assertEqual(len(hs), 1, ev)
        self.assertGreater(hs[0]["f0"], 200)
        self.assertLess(hs[0]["f1"], 60)
        self.assertGreater(len(hs[0]["pts"]), 5)

    def test_slow_curved_head_echo(self):
        """A slow head echo (1 s, braking +400 -> +24 Hz) the detector starts on long before the trail: the path is
        looked for back from where the trail itself starts, so it is found."""
        x = baseband(12, [(6.0, 7.2, 24.0, 0.3, 0.0)])
        t = np.arange(len(x)) / FS
        m = (t >= 5.0) & (t < 6.0)
        tt = t[m] - 5.0
        f0 = meteor.GRAVES_HZ - DIAL
        x[m] += (0.2 * np.exp(2j * np.pi * (f0 * tt + 24.0 * tt + 376 * 0.3 * (1 - np.exp(-tt / 0.3))))).astype(np.complex64)
        ev, _ = run(x)
        hs = [e["head"] for e in ev if e["head"]]
        self.assertEqual(len(hs), 1, ev)
        self.assertGreater(hs[0]["f0"], 150)
        self.assertLess(hs[0]["f1"], 60)

    def test_head_find_not_the_echo_itself(self):
        """The ±5 kHz spectrum: the echo at +148 Hz spreads over its short frames (points next to it, one far point
        of noise before): no head echo. A steep line coming onto the trail is one."""
        c = meteor.MeteorCounter(path=os.path.join(tempfile.gettempdir(), "m_hf.json"))
        c.threshold_db = 6.0

        class Hs:
            hz = np.arange(-75, 76) * 66.67
            dt = 0.0075
            bin = 66.67
        lim = int(6.0 * 255 / meteor.WF_DB) + 5

        def rows(pts):
            out = []
            for t, f in pts:
                v = np.zeros(len(Hs.hz), np.uint8)
                v[int(np.argmin(np.abs(Hs.hz - f)))] = lim
                out.append((t, v.tobytes()))
            return out
        leak = [(9.94, -344.0)] + [(9.94 + (i + 1) * Hs.dt, 200.0 + 67 * (i % 2)) for i in range(12)]
        self.assertIsNone(c._head_find(rows(leak), Hs, 10.0, 148.0))
        line = [(9.8 + i * Hs.dt, 1800.0 - 8000.0 * i * Hs.dt) for i in range(20)]     # 1800 -> 660 Hz, 8 kHz/s
        h = c._head_find(rows(line), Hs, 10.0, 148.0)
        self.assertTrue(h, h)
        self.assertLess(h["slope"], -5000)

    def test_detail_aligned_when_blocks_come_in_bursts(self):
        """The blocks come late and then all at once (the receiver busy): the frames get their times from the samples,
        so the fine cells of the detail start with the echo (not by the lag later or earlier)."""
        x = baseband(12, [(6.0, 7.5, 40.0, 0.3, 0.0)])
        events = []
        with tempfile.TemporaryDirectory() as d:
            c = meteor.MeteorCounter(on_echo=events.append, path=os.path.join(d, "m.json"))
            c.set_enabled(True)
            for i in range(0, len(x), BLOCK):
                blk = x[i:i + BLOCK]
                ts = (i + len(blk)) / FS
                lag = 0.02 + (5.9 - ts if 5.3 <= ts < 5.9 else 0.0) + (7.0 - ts if 6.4 <= ts < 7.0 else 0.0)
                c.feed(blk, FS, DIAL, now=T0 + ts + lag)
            c.set_enabled(False)
            ev = [e for e in events if e["kind"] != "plane"]
            self.assertEqual(len(ev), 1, events)
            dd = c.detail(ev[0]["ts"])
        self.assertTrue(dd.get("fine"), dd.keys())
        import base64
        hz = np.array(dd["hz"])
        a = np.frombuffer(base64.b64decode(dd["rows"]), np.uint8).reshape(dd["n"], len(hz))
        lit = np.nonzero(a[:, np.abs(hz - 40) <= 3].max(axis=1) >= 10 * 255 / meteor.WF_DB)[0]
        t_on = dd["t0"] + lit[0] * dd["dt"]
        self.assertAlmostEqual(t_on - ev[0]["ts"], 0.0, delta=0.15)
        self.assertAlmostEqual(ev[0]["ts"] - T0, 6.0 + 0.02, delta=0.2)

    def test_weak_line_aircraft(self):
        """A SAT·LINES track within ±350 Hz is an aircraft: PLANE (not SAT), not when the meteor detector had it."""
        def line(a, b, f0, f1):
            return [(T0 + t, f0 + (f1 - f0) * (t - a) / (b - a), 3.0) for t in np.arange(a, b, 0.1)]
        items = {60: [{"how": "lines", "pts": line(2.0, 6.0, -40.0, 0.0), "z": 9.0}]}

        class Stub:
            n = 0

            def take(self):
                self.n += 1
                return items.get(self.n, [])
        with tempfile.TemporaryDirectory() as dd:
            c = meteor.MeteorCounter(path=os.path.join(dd, "m.json"))
            c.set_weak(sat_lines=True)
            c._weak = Stub()
            ev, c = run(baseband(12), c)
        self.assertEqual([(e["kind"], e.get("how")) for e in ev], [("plane", "lines")], ev)

    def test_meteors_in_a_burst_stay_meteors(self):
        """Two meteors at almost the same Doppler 0.7 s apart: the second one is not an aircraft (something there
        before it, but the meteor detector had it)."""
        ev, _ = run(baseband(12, [(5.0, 5.3, 10.0, 0.3, 0.0), (6.0, 7.5, 12.0, 0.3, 0.0)]))
        self.assertEqual([e["kind"] for e in ev], ["under", "over"], ev)

    def test_meteor_after_an_aircraft(self):
        """A meteor 5 s after an aircraft near its Doppler is a meteor (it starts at once)."""
        ev, _ = run(baseband(16, [(2.0, 8.0, -20.0, 0.3, 8.0), (12.0, 12.3, 10.0, 0.3, 0.0)]))
        self.assertEqual([e["kind"] for e in ev], ["plane", "under"], ev)

    def test_long_overdense_with_a_jump_is_a_meteor(self):
        """A 3 s overdense echo whose Doppler jumps one bin (the wind): not an aircraft."""
        ev, _ = run(baseband(14, [(5.0, 6.5, 20.0, 0.3, 0.0), (6.5, 8.0, 28.0, 0.3, 0.0)]))
        self.assertEqual([e["kind"] for e in ev], ["over"], ev)

    def test_head_from_the_track(self):
        """A short steep head echo the detector started on: +70 -> 0 Hz point by point, then the trail: a head echo;
        another meteor at one Doppler before the trail is not."""
        c = meteor.MeteorCounter(path=os.path.join(tempfile.gettempdir(), "m_ht.json"))
        c.bin_hz = np.arange(-64, 65) * 7.8125
        trail = [(6.1 + i * 0.032, 0.0) for i in range(10)]
        ev = {"t0": 6.0, "dop": 0.0, "track": [(6.0, 70.0), (6.032, 47.0), (6.064, 23.0)] + trail}
        h = c._head_track(ev)
        self.assertTrue(h and h["fine"], h)
        self.assertEqual(h["f0"], 70)
        ev2 = {"t0": 6.0, "dop": 0.0, "track": [(6.0, 70.0), (6.032, 70.0), (6.064, 70.0)] + trail}
        self.assertIsNone(c._head_track(ev2))

    def test_sweep(self):
        sat = [(i * 0.032, -200.0 + 300.0 * i * 0.032) for i in range(30)]
        self.assertAlmostEqual(meteor.MeteorCounter._sweep(sat), 300, delta=10)
        head = [(i * 0.032, 24.0 + 300.0 * np.exp(-i * 0.032 / 0.08)) for i in range(30)]   # braking onto the trail
        self.assertEqual(meteor.MeteorCounter._sweep(head), 0.0)
        self.assertEqual(meteor.MeteorCounter._sweep([(i * 0.032, 20.0) for i in range(30)]), 0.0)

    def test_fast_skips_a_sweep(self):
        """A satellite crossing the carrier fast (2 kHz/s) is not a FAST ping; the same burst at one Doppler is."""
        import meteor_weak
        out = {}
        for name, k in (("sweep", 2000.0), ("ping", 0.0)):
            x = baseband(10)
            chirp(x, 6.0, 6.1, -100.0, -100.0 + k * 0.1, 0.5)
            f = meteor_weak.Fast(FS, meteor.GRAVES_HZ - DIAL)
            out[name] = []
            for i in range(0, len(x), BLOCK):
                out[name] += f.feed(x[i:i + BLOCK], T0 + (i + BLOCK) / FS)
        self.assertEqual(out["sweep"], [])
        self.assertEqual(len(out["ping"]), 1, out)

    def test_aircraft_without_drift(self):
        """An aircraft near the middle of the path: ~0 Hz, no drift, a strong part of 1.5 s; weak for seconds before it
        (a meteor starts at once): PLANE, not OVER."""
        ev, _ = run(baseband(14, [(3.0, 9.0, -8.0, 0.06, 0.0), (6.0, 7.5, -8.0, 0.3, 0.0)]))
        self.assertEqual([e["kind"] for e in ev], ["plane"], ev)
        ev, _ = run(baseband(14, [(6.0, 7.5, -8.0, 0.3, 0.0)]))             # the same without it: a meteor
        self.assertEqual([e["kind"] for e in ev], ["over"], ev)

    def test_fast_ping_found(self):
        """FAST: a 15 ms ping too short for the meteor detector is an UNDER echo of its own (F), a strong one is not
        counted twice."""
        x = baseband(10, [(6.0, 6.015, 30.0, 0.45, 0.0)])
        ev, _ = run(x)
        self.assertEqual(ev, [])                                   # the meteor detector alone misses it
        with tempfile.TemporaryDirectory() as dd:
            c = meteor.MeteorCounter(path=os.path.join(dd, "m.json"))
            c.set_weak(fast=True)
            ev, c = run(x, c)
        self.assertEqual(len(ev), 1, ev)
        self.assertEqual(ev[0]["kind"], "under")
        self.assertTrue(ev[0]["fast"])
        self.assertAlmostEqual(ev[0]["doppler"], 30, delta=12)
        self.assertAlmostEqual(ev[0]["ts"] - T0, 6.0, delta=0.05)
        self.assertEqual(c.summary(T0 + 10)["fasts"], 1)
        self.assertEqual(meteor.log_name(ev[0]), " | F")
        with tempfile.TemporaryDirectory() as dd:
            c = meteor.MeteorCounter(path=os.path.join(dd, "m.json"))
            c.set_weak(fast=True)
            ev, c = run(baseband(10, [(6.0, 6.3, 30.0, 0.5, 0.0)]), c)
        self.assertEqual([(e["kind"], e.get("fast")) for e in ev], [("under", None)], ev)

    def test_fast_quiet_on_noise(self):
        import meteor_weak
        f = meteor_weak.Fast(FS, meteor.GRAVES_HZ - DIAL)
        x = baseband(60, seed=7)
        x[int(20 * FS)] += 300                                     # an impulse: in the reference bands too
        out = []
        for i in range(0, len(x), BLOCK):
            out += f.feed(x[i:i + BLOCK], T0 + (i + BLOCK) / FS)
        self.assertEqual(out, [])

    def test_weak_satellites_reported_once(self):
        """What SAT·TLE / SAT·LINES find: reported as SAT (SAT·TLE with its satellite, not identified again), unless a
        satellite reported already lies on it."""
        x = baseband(40)
        x = chirp(x, 4.0, 12.0, 1500.0, -1500.0, 0.15)            # the tracker sees this one

        def line(a, b, f0, f1):
            return [(T0 + t, f0 + (f1 - f0) * (t - a) / (b - a), 3.0) for t in np.arange(a, b, 0.1)]

        tle = {"how": "tle", "norad": 99999, "name": "TEST SAT", "pts": line(15.0, 25.0, 2000.0, 500.0), "z": 9.0,
               "offset": 5, "az": 250.0, "el": 30.0, "km": 900}
        items = {150: [tle, dict(tle),                             # the same twice: once
                       {"how": "lines", "pts": line(15.0, 25.0, -2000.0, -3000.0), "z": 8.0}],
                 300: [{"how": "lines", "pts": line(4.5, 11.0, 1500.0 - 375 * 0.5, 1500 - 375 * 7), "z": 8.0}]}  # the tracker's

        class Stub:
            n = 0

            def take(self):
                self.n += 1
                return items.get(self.n, [])
        with tempfile.TemporaryDirectory() as dd:
            c = meteor.MeteorCounter(path=os.path.join(dd, "m.json"))
            c.set_weak(sat_tle=True, sat_lines=True)
            c._weak = Stub()
            ev, c = self._sat_run(x, counter=c)
        sats = sorted((e for e in ev if e["kind"] == "sat"), key=lambda e: e["ts"])
        self.assertEqual([e.get("how") for e in sats], [None, "tle", "lines"], sats)
        self.assertEqual(sats[1]["sat"]["norad"], 99999)
        self.assertEqual(sats[1]["sat"]["name"], "TEST SAT")
        self.assertAlmostEqual(sats[2]["doppler"], -2000, delta=1000)
        self.assertNotIn("sat_tle", meteor.log_name(sats[1]))
        self.assertEqual(c.summary(T0 + 40)["this_hour"], 0)

    def test_graves_path(self):
        p = meteor.graves_path(48.7, 17.9)          # western Slovakia
        self.assertAlmostEqual(p["az"], 265, delta=3)
        self.assertAlmostEqual(p["km"], 930, delta=30)
        self.assertTrue(5 < p["el"] < 15, p)
        self.assertGreater(meteor.graves_path(47.5, 9.0)["el"], p["el"])   # closer: the meteor zone is higher


if __name__ == "__main__":
    unittest.main()

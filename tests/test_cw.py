"""Tests of the CW decoder / skimmer (cw.py) on synthetic CW; the full CER bench is tests/cw_bench.py.

Run: python -m unittest tests.test_cw   (from the RADIMCOM folder)
"""
import os
import random
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cw  # noqa: E402
import cw_bench as bench  # noqa: E402


def decode(x, **opts):
    return bench.run(cw, x, opts=opts or None)


class TestSingle(unittest.TestCase):
    def test_clean_20wpm(self):
        text = "CQ CQ DE OM2AMR OM2AMR K"
        x = bench.add_noise(bench.signal(text, 20, f0=40.0), 15, random.Random(1))
        d = decode(x)
        self.assertEqual(bench.norm("".join(d.text)), text)
        i = d.info()
        self.assertEqual(i["wpm"], 20)
        self.assertEqual(i["station"]["call"], "OM2AMR")
        self.assertIn(i["station"]["key"], (None, "paddle"))   # needs 12 dots + 8 dashes to tell
        self.assertAlmostEqual(i["tone_hz"], 40, delta=3)
        self.assertEqual(len(i["conf"]), len(i["text"]))

    def test_weak_signal(self):
        text = "TNX FER CALL UR RST 579 579"
        x = bench.add_noise(bench.signal(text, 18), 0, random.Random(2))
        self.assertLess(bench.cer(text, "".join(decode(x).text)), 0.1)

    def test_farnsworth(self):
        text = "QRL? DE DL5XY GM OM TNX FB REPORT 73 ES GL SK"
        x = bench.add_noise(bench.signal(text, 20, farnsworth=10), 12, random.Random(3))
        d = decode(x)
        self.assertLess(bench.cer(text, "".join(d.text)), 0.1)
        self.assertTrue(d.info()["station"]["farnsworth"])

    def test_noise_only_is_silent(self):
        x = bench.add_noise(np.zeros(int(10 * bench.FS), complex), 0, random.Random(4))
        self.assertEqual(bench.norm("".join(decode(x).text)), "")

    def test_compat_attributes(self):
        """app.py (log, TUNE) reads these of the followed station."""
        d = cw.CwDecoder(lambda k, v: None)
        self.assertIsNone(d.tone)
        self.assertGreater(d.dot_ms, 0)
        self.assertFalse(d.present)


class TestSkimmer(unittest.TestCase):
    def test_three_stations(self):
        rnd = random.Random(5)
        spec = [("CQ TEST DE OK1ABC OK1ABC TEST", 22, -1200.0, 1.0), ("UR 5NN 599 TU DE DL5XY", 28, -400.0, 0.7),
                ("QRZ? DE G4XYZ G4XYZ K", 30, 1500.0, 0.8)]
        sig = [bench.signal(t, w, f0=f, amp=a, rnd=rnd) for t, w, f, a in spec]
        n = max(len(s) for s in sig)
        x = bench.add_noise(sum(np.pad(s, (0, n - len(s))) for s in sig), 9, rnd)
        events = []
        d = cw.CwDecoder(lambda k, v: events.append((k, v)), mode="skimmer")
        d.set_options(span="wide")
        d.set_enabled(True)
        for i in range(0, len(x), bench.CHUNK):
            d.feed(x[i: i + bench.CHUNK], bench.FS, 7_030_000.0, (-250.0, 250.0))
        chans = d.info()["channels"]
        for text, wpm, f0, _ in spec:
            ch = min(chans, key=lambda c: abs(c["tone_hz"] - f0))
            self.assertAlmostEqual(ch["tone_hz"], f0, delta=5)
            self.assertAlmostEqual(ch["wpm"], wpm, delta=2)
            self.assertLess(bench.cer(text, ch["text"]), 0.1, ch["text"])
        # every station's characters go out as cwchan; together they make its text
        for c in chans:
            sent = "".join(v["t"] for k, v in events if k == "cwchan" and v["id"] == c["id"])
            whole = d.channel_text(c["id"])
            self.assertEqual(sent, whole["text"])
            self.assertEqual(len(whole["conf"]), len(whole["text"]))
        self.assertIsNone(d.channel_text(9999))
        # following another station
        other = next(c for c in chans if c["id"] != d.info()["cur"])
        d.follow(other["id"])
        self.assertEqual(d.info()["cur"], other["id"])
        d.follow(None)
        self.assertIsNone(d.info()["follow"])
        d.clear()
        self.assertEqual(d.info()["channels"], [])
        self.assertIsNone(d.channel_text(chans[0]["id"]))


class TestClear(unittest.TestCase):
    def test_clear_empties_and_stations_come_back_empty(self):
        text = "CQ CQ DE OM2AMR OM2AMR K " * 4
        x = bench.add_noise(bench.signal(text, 20, f0=40.0), 15, random.Random(10))
        d = cw.CwDecoder(lambda k, v: None, mode="skimmer")
        d.set_enabled(True)
        half = len(x) // 2 // bench.CHUNK * bench.CHUNK
        for i in range(0, half, bench.CHUNK):
            d.feed(x[i: i + bench.CHUNK], bench.FS, 7_030_000.0, (-250.0, 250.0))
        self.assertTrue(d.info()["channels"])
        d.clear()
        self.assertEqual(d.info()["channels"], [])
        d.feed(x[half: half + bench.CHUNK], bench.FS, 7_030_000.0, (-250.0, 250.0))
        # found again soon, and its text is only what was sent after CLR (shorter than the half before)
        for i in range(half + bench.CHUNK, len(x), bench.CHUNK):
            d.feed(x[i: i + bench.CHUNK], bench.FS, 7_030_000.0, (-250.0, 250.0))
        chans = d.info()["channels"]
        self.assertEqual(len(chans), 1)
        after = bench.norm(d.channel_text(chans[0]["id"])["text"])
        self.assertTrue(after and bench.norm(text).endswith(after[-20:]))
        self.assertLess(len(after), len(bench.norm(text)) * 0.6)


class TestStrong(unittest.TestCase):
    """A strong station (35 dB): the noise blanker must not cut its marks, its keying sidebands are not stations."""
    TEXT = "CQ CQ CQ DE LA8IG LA8IG LA8IG K " * 2

    def test_single_exact(self):
        x = bench.add_noise(bench.signal(self.TEXT, 26), 35, random.Random(8))
        self.assertEqual(bench.norm("".join(decode(x).text)), bench.norm(self.TEXT))

    def test_skimmer_no_duplicates(self):
        rnd = random.Random(9)
        x = bench.signal(self.TEXT, 26, f0=-1223.0, rnd=rnd)
        y = bench.signal("CQ DE OM2AMR OM2AMR K " * 2, 20, f0=-1100.0, amp=0.3, rnd=rnd)   # a real neighbour, −10 dB
        n = max(len(x), len(y))
        x = bench.add_noise(np.pad(x, (0, n - len(x))) + np.pad(y, (0, n - len(y))), 35, rnd)
        d = bench.run(cw, x, band=(150.0, 3350.0), opts=dict(mode="skimmer", span="wide"))
        tones = sorted(c["tone_hz"] for c in d.info()["channels"])
        self.assertEqual(len(tones), 2, tones)
        strong = min(d.info()["channels"], key=lambda c: abs(c["tone_hz"] + 1223))
        self.assertEqual(bench.norm(strong["text"]), bench.norm(self.TEXT)[-len(bench.norm(strong["text"])):])


class TestJson(unittest.TestCase):
    def test_numpy_inputs_stay_json(self):
        """The receiver passes numpy numbers (dial, band): info() and the events must still be plain JSON."""
        import json
        events = []
        d = cw.CwDecoder(lambda k, v: events.append(json.dumps(v)))
        d.set_options(mode="skimmer")
        d.set_enabled(True)
        x = bench.add_noise(bench.signal("CQ DE OM2AMR K", 20, f0=300.0), 12, random.Random(7))
        for i in range(0, len(x), bench.CHUNK):
            dial = np.float64(14_016_500.0 + (i // bench.CHUNK) % 2)      # also a small retune
            d.feed(x[i: i + bench.CHUNK], np.float64(bench.FS), dial, (np.float64(150.0), np.float64(3350.0)))
        json.dumps(d.info())
        self.assertTrue(events)


class TestPieces(unittest.TestCase):
    def test_find_call(self):
        self.assertEqual(cw.find_call("CQ CQ DE OM2AMR OM2AMR K"), "OM2AMR")
        self.assertEqual(cw.find_call("UR 5NN TU"), None)
        self.assertEqual(cw.find_call("OK1ABC DE DL5XY/P K"), "DL5XY")

    def test_gap_fit_farnsworth(self):
        p = cw.Profile(60.0)
        rnd = random.Random(6)
        gaps = [60 * np.exp(rnd.gauss(0, 0.1)) * k for k in [1] * 30 + [6] * 10 + [14] * 4]
        p.fit_spaces(gaps)
        info = p.info()
        self.assertAlmostEqual(info["ic"], 6, delta=0.8)
        self.assertAlmostEqual(info["iw"], 14, delta=2)


if __name__ == "__main__":
    unittest.main()

"""meteor_store.py: the echoes of a day from the daily log, the marked echoes with their details."""
import calendar
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import daylog  # noqa: E402
import meteor_store as ms  # noqa: E402

T = calendar.timegm(time.strptime("2026-11-24 05:28:12", "%Y-%m-%d %H:%M:%S"))


class StoreTest(unittest.TestCase):
    def test_log_line_and_history(self):
        with tempfile.TemporaryDirectory() as d:
            log_c, log_d = daylog.DayLog("meteor", "C", d), daylog.DayLog("meteor", "D", d)
            plane = {"kind": "plane", "air": {"hex": "4ca123", "flight": "BAW126"}, "head": None}
            sat = {"kind": "sat", "sat": {"norad": 25544, "name": "ISS (ZARYA)"}}
            log_c.write("143.050016 MHz +16 Hz 33.9 dB 3.20 s plane" + ms.log_name(plane), T)
            log_c.write("143.050000 MHz +0 Hz 12.0 dB 0.25 s under" + ms.log_name({"kind": "under", "head": {"f0": 1}}), T + 5)
            log_c.write("143.048406 MHz -1594 Hz 8.9 dB 2.04 s sat" + ms.log_name(sat), T + 9)
            log_c.write("143.050010 MHz +10 Hz 11.0 dB 0.30 s under", T + 20)            # an old line: no "|"
            log_d.write("143.050000 MHz +3 Hz 15.0 dB 0.40 s under", T + 30)
            self.assertEqual(ms.history_days(d), ["2026-11-24"])
            ev = ms.history("2026-11-24", "C", d)
            self.assertEqual([e["kind"] for e in ev], ["plane", "under", "sat", "under"])
            self.assertEqual(ev[0]["name"], "BAW126")
            self.assertEqual(ev[0]["ts"], T)
            self.assertEqual(ev[0]["time"], "05:28:12")
            self.assertEqual(ev[0]["doppler"], 16)
            self.assertTrue(ev[1]["head"])
            self.assertEqual(ev[1]["name"], "")
            self.assertEqual(ev[2]["name"], "ISS (ZARYA)")
            self.assertIsNone(ev[3]["head"])
            self.assertEqual(len(ms.history("2026-11-24", "D", d)), 1)
            self.assertEqual(ms.history("2026-11-23", "C", d), [])
            with self.assertRaises(ValueError):
                ms.history("../x", "C", d)

    def test_marks_keep_the_detail(self):
        with tempfile.TemporaryDirectory() as d:
            m = ms.Marks("C", d)
            echo = {"ts": 1795.12, "kind": "under", "snr": 20.0, "det": True}
            self.assertTrue(m.add(echo, {"ts": 1795.12, "rows": "AAAA", "echo": echo}, b"RIFFwav"))
            self.assertEqual(m.audio(1795.12), b"RIFFwav")
            self.assertTrue(m.list()[0]["audio"])
            self.assertFalse(m.add({"ts": 1800.0, "kind": "sat", "det": False}))
            m2 = ms.Marks("C", d)                          # read again from the files
            self.assertEqual([e["ts"] for e in m2.list()], [1795.12, 1800.0])
            self.assertEqual(m2.detail(1795.12)["rows"], "AAAA")
            self.assertTrue(m2.detail(1795.12)["echo"]["marked"])
            self.assertIsNone(m2.detail(1800.0))
            self.assertTrue(m2.remove(1795.121))
            self.assertFalse(m2.remove(1795.12))
            self.assertIsNone(m2.detail(1795.12))
            self.assertIsNone(m2.audio(1795.12))                 # the sound goes with the mark
            self.assertEqual(len(ms.Marks("C", d).list()), 1)


if __name__ == "__main__":
    unittest.main()

"""spotting.py: the IPFIX datagram for PSK Reporter (descriptors as in pskreporter.info/pskdev.html, records, padding),
the once-per-hour-and-band rule, the WSPRnet query and the settings check.

Run: python -m unittest tests.test_spotting
"""
import os
import struct
import sys
import tempfile
import time
import unittest
import urllib.parse
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import spotting  # noqa: E402

E = bytes.fromhex("0000768F")


class Templates(unittest.TestCase):
    def test_receiver_template_matches_the_spec(self):
        want = (bytes.fromhex("0003002C99920004 0001".replace(" ", "")) + bytes.fromhex("8002FFFF") + E
                + bytes.fromhex("8004FFFF") + E + bytes.fromhex("8008FFFF") + E + bytes.fromhex("8009FFFF") + E + b"\0\0")
        self.assertEqual(spotting.rx_template(), want)

    def test_sender_template(self):
        t = spotting.tx_template()
        self.assertEqual(t[:8], bytes.fromhex("0002003C99930007"))
        self.assertEqual(len(t), 0x3C)
        self.assertEqual(t[-4:], bytes.fromhex("00960004"))     # flowStartSeconds, no enterprise number


class Datagram(unittest.TestCase):
    def setUp(self):
        self.rx = ("OM0ABC", "JN88wq", "RADIMCOM 1.1rc2", "")
        self.spots = [{"call": "DL1ABC", "freq_hz": 14075123, "snr": -12, "grid": "JO62", "ts": 1800000000},
                      {"call": "K1ABC", "freq_hz": 14074900, "snr": -200, "grid": "", "ts": 1800000015}]

    def test_header_and_sets(self):
        p = spotting.packet(7, 0x12345678, self.rx, self.spots, True, now=1800000100)
        ver, length, t, seq, obs = struct.unpack(">HHIII", p[:16])
        self.assertEqual((ver, length, t, seq, obs), (10, len(p), 1800000100, 7, 0x12345678))
        # walk the sets: each has its id and length, all lengths multiples of 4 and adding up
        pos, ids = 16, []
        while pos < len(p):
            sid, slen = struct.unpack(">HH", p[pos:pos + 4])
            self.assertEqual(slen % 4, 0)
            ids.append(sid)
            pos += slen
        self.assertEqual(pos, len(p))
        self.assertEqual(ids, [3, 2, 0x9992, 0x9993])

    def test_sender_record(self):
        r = spotting.tx_record(self.spots[0])
        self.assertEqual(r[:7], b"\x06DL1ABC")
        self.assertEqual(struct.unpack(">I", r[7:11])[0], 14075123)
        self.assertEqual(struct.unpack(">b", r[11:12])[0], -12)
        self.assertEqual(r[12:16], b"\x03FT8")
        self.assertEqual(r[16:21], b"\x04JO62")
        self.assertEqual(r[21], 1)                       # informationSource: automatically extracted
        self.assertEqual(struct.unpack(">I", r[22:26])[0], 1800000000)
        r2 = spotting.tx_record(self.spots[1])
        self.assertEqual(struct.unpack(">b", r2[10:11])[0], -128)   # clamped to one byte
        self.assertEqual(r2[15:17], b"\x00\x01")                     # no locator: empty string

    def test_without_templates(self):
        p = spotting.packet(0, 1, self.rx, self.spots, False)
        self.assertEqual(struct.unpack(">H", p[16:18])[0], 0x9992)


class Dedupe(unittest.TestCase):
    def test_once_per_hour_and_band(self):
        with mock.patch("threading.Thread"):
            r = spotting.PskReporter()
        d = {"call": "DL1ABC", "freq_hz": 14075000, "snr": -10, "ts": 1000.0}
        r.add(d)
        r.add(dict(d, ts=1100.0))                         # same band within the hour: no
        r.add(dict(d, ts=1200.0, grid="JO62"))            # the locator became known: yes
        r.add(dict(d, ts=1300.0))                         # known again, nothing new: no
        r.add(dict(d, ts=1300.0, freq_hz=7075000))        # another band: yes
        r.add(dict(d, ts=1200.0 + 3700))                  # an hour after the last report: yes
        self.assertEqual([(s["freq_hz"], s["grid"], s["ts"]) for s in r.queue],
                         [(14075000, "", 1000.0), (14075000, "JO62", 1200.0), (7075000, "JO62", 1300.0),
                          (14075000, "JO62", 4900.0)])


class Failures(unittest.TestCase):
    CFG = dict(spotting.DEFAULTS, callsign="OM0ABC", pskreporter=True, wsprnet=True)

    def test_psk_send_error_is_counted_and_logged(self):
        lines = []
        with mock.patch("threading.Thread"):
            r = spotting.PskReporter()
        r.add({"call": "DL1ABC", "freq_hz": 14075000, "snr": -10, "ts": 1000.0})
        with mock.patch.object(spotting, "_cfg", return_value=self.CFG), \
                mock.patch.object(spotting, "_receiver", return_value=(("OM0ABC", "JN88wq"), "")), \
                mock.patch("socket.gethostbyname", side_effect=OSError("no internet")), \
                mock.patch.object(spotting, "log", lines.append):
            r.flush()
        self.assertEqual((r.sent, r.failed, r.error), (0, 1, "no internet"))
        self.assertEqual(len(lines), 1)
        self.assertIn("DL1ABC 14.075000", lines[0])
        self.assertIn("no internet", lines[0])

    def test_wsprnet_keeps_failed_spots_for_the_next_cycle(self):
        lines = []
        with mock.patch("threading.Thread"):
            w = spotting.WsprNet()
        now = time.time()
        for call in ("DL1ABC", "G4XYZ"):
            w.add({"call": call, "grid": "JO62", "dbm": 37, "snr": -24, "dt": 0.3, "drift": 0,
                   "freq_hz": 14097100, "df": 1500, "ts": now})
        with mock.patch.object(spotting, "_cfg", return_value=self.CFG), \
                mock.patch.object(spotting, "_receiver", return_value=(("OM0ABC", "JN88wq"), "")), \
                mock.patch("urllib.request.urlopen", side_effect=OSError("timed out")), \
                mock.patch.object(spotting, "log", lines.append):
            w._send_all()
        self.assertEqual(len(w.queue), 2)
        self.assertEqual(len(lines), 1)
        self.assertIn("G4XYZ", lines[0])
        w.queue[0]["ts"] = now - 4000                     # older than an hour: dropped, counted, logged
        with mock.patch.object(spotting, "_cfg", return_value=self.CFG), \
                mock.patch.object(spotting, "_receiver", return_value=(("OM0ABC", "JN88wq"), "")), \
                mock.patch("urllib.request.urlopen", return_value=mock.MagicMock()), \
                mock.patch.object(spotting, "log", lines.append):
            w._send_all()
        self.assertEqual((w.sent, w.failed, len(w.queue)), (1, 1, 0))
        self.assertIn("dropped", lines[1])


class Wsprnet(unittest.TestCase):
    def test_query(self):
        spot = {"call": "DL1ABC", "grid": "JO62", "dbm": 37, "snr": -24, "dt": 0.34, "drift": -1,
                "freq_hz": 14097123, "df": 1523, "ts": 1800000120.0}    # cycle 2027-01-15 08:00 UTC
        with mock.patch.object(spotting, "software", return_value="RADIMCOM 1.1rc2"):
            q = dict(urllib.parse.parse_qsl(spotting.wsprnet_query(spot, ("OM0ABC", "JN88wq"))))
        self.assertEqual(q["function"], "wspr")
        self.assertEqual((q["rcall"], q["rgrid"], q["tcall"], q["tgrid"]), ("OM0ABC", "JN88wq", "DL1ABC", "JO62"))
        self.assertEqual((q["rqrg"], q["tqrg"]), ("14.095600", "14.097123"))
        self.assertEqual((q["date"], q["time"]), ("270115", "0800"))
        self.assertEqual((q["sig"], q["dt"], q["drift"], q["dbm"], q["mode"]), ("-24", "0.3", "-1", "37", "2"))


class Settings(unittest.TestCase):
    def test_save_checks_the_callsign(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(spotting, "CONFIG_PATH", os.path.join(d, "s.json")):
            self.assertEqual(spotting.load(), spotting.DEFAULTS)
            s = spotting.save({"callsign": " om0abc ", "pskreporter": True, "antenna": "  dipole   40 m "})
            self.assertEqual((s["callsign"], s["pskreporter"], s["wsprnet"], s["antenna"]), ("OM0ABC", True, False, "dipole 40 m"))
            with self.assertRaises(ValueError):
                spotting.save({"callsign": "ABC"})
            self.assertEqual(spotting.save({"callsign": ""})["callsign"], "")


if __name__ == "__main__":
    unittest.main()

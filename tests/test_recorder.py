"""Tests of the recordings list (recorder.py): file names, the list for the RECORDINGS tab and deleting.

Run: python -m unittest tests.test_recorder
"""
import calendar
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import recorder  # noqa: E402


class ParseNameTest(unittest.TestCase):
    def test_memory_name(self):
        f = recorder.parse_name("Piestany_TWR_118.575000MHz_AM_20261105_155300.mp3")
        self.assertEqual(f, {"memory": "Piestany TWR", "hz": 118575000, "mode": "AM", "start": "2026-11-05 15:53:00",
                             "src": "rec"})

    def test_plain_and_numbered(self):
        f = recorder.parse_name("134.475670MHz_AM_20261110_221021_2.mp3")
        self.assertEqual((f["memory"], f["hz"], f["mode"], f["start"]), ("", 134475670, "AM", "2026-11-10 22:10:21"))

    def test_tags(self):
        self.assertEqual(recorder.parse_name("145.500000MHz_FM_20261110_221021_SQ_2.mp3")["src"], "sq")
        self.assertEqual(recorder.parse_name("A_118.100000MHz_AM_20261110_221021_SCAN.mp3")["src"], "scan")
        self.assertEqual(recorder.parse_name("Radio_FM_187.072000MHz_DAB_20261110_221021_SQ.mp3")["src"], "dab")
        f = recorder.parse_name("RADIMCOM_A_20261110_201021Z_145000000Hz_IQ.wav")
        self.assertEqual((f["src"], f["hz"], f["mode"]), ("iq", 145000000, "IQ"))
        self.assertEqual(recorder.start_time("RADIMCOM_A_20261110_201021Z_145000000Hz_IQ.wav"),
                         calendar.timegm((2026, 11, 10, 20, 10, 21, 0, 0, 0)))    # UTC in the name

    def test_foreign_file(self):
        self.assertEqual(recorder.parse_name("song.mp3"), {"memory": "", "hz": 0, "mode": "", "start": "", "src": ""})


class TreeTest(unittest.TestCase):
    """The folder tree YYYY/MM/DD of the RECORDINGS tab: listing, deleting files and folders, finding by name."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.rec = recorder.Recorder(self.root)
        self.day = os.path.join(self.root, "2026", "11", "05")
        os.makedirs(os.path.join(self.day, "iq"))
        self.old = os.path.join(self.day, "145.500000MHz_FM_20261105_155300.mp3")
        self.new = os.path.join(self.day, "Piestany_TWR_118.575000MHz_AM_20261105_160000_SQ.mp3")
        self.scan = os.path.join(self.day, "A_118.100000MHz_AM_20261105_170000_SCAN.mp3")
        for path, n in ((self.old, 16000), (self.new, 32000), (self.scan, 8000)):
            with open(path, "wb") as f:
                f.write(bytes(n))      # 1 s at 128 kbps; the scan 64 kbps
        open(os.path.join(self.day, "iq", "RADIMCOM_A_20261105_150000Z_145000000Hz_IQ.wav"), "wb").close()
        with open(os.path.join(self.day, "notes.txt"), "w") as f:
            f.write("x")

    def tearDown(self):
        self.rec.stop_all(0)
        self.tmp.cleanup()

    def test_list(self):
        top = self.rec.list_dir("")
        self.assertEqual((top["dir"], [d["name"] for d in top["dirs"]], top["files"]), ("", ["2026"], []))
        self.assertEqual((top["dirs"][0]["files"], top["dirs"][0]["size"]), (4, 56000))   # all levels below
        day = self.rec.list_dir("2026/11/05")
        self.assertEqual(day["dir"], "2026/11/05")
        self.assertEqual([d["name"] for d in day["dirs"]], ["iq"])
        files = day["files"]                                   # oldest first; notes.txt is not a recording
        self.assertEqual([f["src"] for f in files], ["rec", "sq", "scan"])
        self.assertEqual((files[1]["memory"], files[1]["secs"], files[1]["path"]),
                         ("Piestany TWR", 2, "2026/11/05/" + os.path.basename(self.new)))
        self.assertEqual(files[2]["secs"], 1)                  # 64 kbps
        self.assertEqual(self.rec.list_dir("2026/11/05/iq")["files"][0]["src"], "iq")
        self.assertEqual(recorder.Recorder(os.path.join(self.root, "none")).list_dir("")["dirs"], [])
        for bad in ("../x", "2026/../../x", "C:/Windows"):
            with self.assertRaises(ValueError):
                self.rec.list_dir(bad)

    def test_delete_files_and_folders(self):
        r = self.rec.delete_paths(["2026/11/05/" + os.path.basename(self.old)])
        self.assertEqual(r, {"deleted": 1, "kept": []})
        self.assertFalse(os.path.exists(self.old))
        with self.assertRaises(ValueError):
            self.rec.delete_paths(["../notes.txt"])
        with self.assertRaises(ValueError):
            self.rec.delete_paths([""])                       # not the whole root
        t = self.rec.tracks["cont"]
        t.enc, t.path = object(), self.new                     # being written: stays, the rest of the folder goes
        self.assertTrue(self.rec.list_dir("2026/11/05")["files"][0]["writing"])
        r = self.rec.delete_paths(["2026/11/05"], {self.scan})
        self.assertEqual(r["deleted"], 2)                      # the IQ and notes.txt
        self.assertEqual(len(r["kept"]), 2)                    # REC SQ written by REC, the scan by the scan
        self.assertTrue(os.path.exists(self.new) and os.path.exists(self.scan))
        t.enc = None
        self.assertEqual(self.rec.delete_paths(["2026"])["deleted"], 2)
        self.assertEqual(os.listdir(self.root), [])            # the emptied folders went too

    def test_find(self):
        self.assertEqual(self.rec.find(os.path.basename(self.scan)), self.scan)
        # an old log row: the name before the _SCAN tag and as WAV -> the moved MP3
        self.assertEqual(self.rec.find("A_118.100000MHz_AM_20261105_170000.wav"), self.scan)
        self.assertIsNone(self.rec.find("../x.mp3"))
        self.assertIsNone(self.rec.find("nothing.mp3"))


class MigrateTest(unittest.TestCase):
    """The flat folders before 1.1 -> YYYY/MM/DD: REC in the root, scan/ (tag _SCAN, WAV -> MP3), iq/."""

    def test_migrate(self):
        import wave
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "scan"))
            os.makedirs(os.path.join(root, "iq"))
            open(os.path.join(root, "145.500000MHz_FM_20261105_155300.mp3"), "wb").close()
            open(os.path.join(root, "song.mp3"), "wb").close()                       # no date: the file time
            t = time.mktime((2025, 3, 4, 12, 0, 0, 0, 0, -1))
            os.utime(os.path.join(root, "song.mp3"), (t, t))
            open(os.path.join(root, "scan", "A_118.100000MHz_AM_20261106_100000.mp3"), "wb").close()
            wav = os.path.join(root, "scan", "B_118.200000MHz_AM_20261106_110000.wav")
            with wave.open(wav, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(bytes(16000 * 2))
            iq = "RADIMCOM_A_20261107_120000Z_145000000Hz_IQ.wav"
            open(os.path.join(root, "iq", iq), "wb").close()
            self.assertEqual(recorder.migrate(root), 5)
            day = lambda *p: os.path.join(root, *p)                                   # noqa: E731
            self.assertTrue(os.path.isfile(day("2026", "11", "05", "145.500000MHz_FM_20261105_155300.mp3")))
            self.assertTrue(os.path.isfile(day("2025", "03", "04", "song.mp3")))
            self.assertTrue(os.path.isfile(day("2026", "11", "06", "A_118.100000MHz_AM_20261106_100000_SCAN.mp3")))
            self.assertTrue(os.path.isfile(day("2026", "11", "06", "B_118.200000MHz_AM_20261106_110000_SCAN.mp3")))
            self.assertFalse(os.path.exists(wav))
            iq_day = recorder.day_folder(root, recorder.start_time(iq))
            self.assertTrue(os.path.isfile(os.path.join(iq_day, "iq", iq)))
            self.assertFalse(os.path.exists(day("scan")) or os.path.exists(day("iq")))  # emptied old folders gone
            self.assertEqual(recorder.migrate(root), 0)                                # nothing left to do


class ActiveStateTest(unittest.TestCase):
    """`active` of a recording (the REC blinks): REC while the file is open, REC SQ only while the squelch is open."""

    def test_active(self):
        import numpy as np
        if recorder.lameenc is None:
            self.skipTest("lameenc not installed")
        with tempfile.TemporaryDirectory() as d:
            loud = (np.sin(np.arange(3200) * 0.3) * 8000).astype("<i2").repeat(2).tobytes()
            quiet = bytes(len(loud))
            sq = recorder.Track(True, lambda: d)
            self.assertFalse(sq.state()["active"])                    # waiting for the squelch
            sq.write(loud, 32000, 145500000, "FM")
            self.assertTrue(sq.state()["active"])                     # squelch open: writing
            sq.write(quiet, 32000, 145500000, "FM")
            st = sq.state()
            self.assertTrue(st["open"])                               # the session is still open (pause held) ...
            self.assertFalse(st["active"])                            # ... but nothing goes in: steady, not blinking
            sq.close()
            cont = recorder.Track(False, lambda: d)
            self.assertFalse(cont.state()["active"])                  # REC off
            cont.on = True
            self.assertTrue(cont.state()["active"])                   # REC: blinks from the press on, before the first block
            cont.write(quiet, 32000, 145500000, "FM")
            self.assertTrue(cont.state()["active"])                   # everything, silence too
            cont.close()


class DabTest(unittest.TestCase):
    """DAB: the MP3 bytes of welle-cli written as they come, named by the station, a new file on a new station."""

    def test_mp3_passthrough(self):
        with tempfile.TemporaryDirectory() as d:
            rec = recorder.Recorder(d)
            chunk = bytes.fromhex("fffba464") + bytes(500)
            for kind in ("cont", "squelch"):
                rec.set(kind, True) if recorder.lameenc else setattr(rec.tracks[kind], "on", True)
            for _ in range(20):
                rec.feed_mp3(chunk, 187072000, "Radio_FM")
            rec.feed_mp3(chunk, 187072000, "Rádio Devín")                # another station: a new file
            for _ in range(100):
                if rec.q.empty():
                    break
                import time
                time.sleep(0.02)
            st = rec.state()
            self.assertTrue(st["cont"]["active"] and st["squelch"]["active"])   # DAB blinks also with REC SQ
            rec.stop_all()
            files = rec.list_dir(os.path.relpath(recorder.day_folder(d), d))["files"]
            names = sorted(f["name"] for f in files)
            self.assertEqual(len(files), 4)                               # 2 buttons x 2 stations
            self.assertTrue(any(n.startswith("Radio_FM_187.072000MHz_DAB_") for n in names), names)
            self.assertTrue(any(n.startswith("Rádio_Devín_187.072000MHz_DAB_") for n in names), names)
            big = [f for f in files if f["memory"] == "Radio FM"][0]
            self.assertEqual(big["size"], 20 * len(chunk))               # the bytes unchanged
            self.assertEqual(big["mode"], "DAB")


class FolderSettingTest(unittest.TestCase):
    """SETTINGS › GENERAL › RECORDINGS: the folder in data\\recordings.json, used by a Recorder without its own folder."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = recorder.SETTINGS_PATH, recorder.FOLDER
        recorder.SETTINGS_PATH = os.path.join(self.tmp.name, "recordings.json")
        recorder.FOLDER = os.path.join(self.tmp.name, "default")
        recorder._settings_cache[:] = [None, ""]

    def tearDown(self):
        recorder.SETTINGS_PATH, recorder.FOLDER = self.old
        recorder._settings_cache[:] = [None, ""]
        self.tmp.cleanup()

    def test_default(self):
        self.assertEqual(recorder.settings(), {"folder": recorder.FOLDER, "custom": "", "default": recorder.FOLDER})

    def test_own_folder_created_and_used(self):
        own = os.path.join(self.tmp.name, "own", "recs")
        s = recorder.save_folder(f'  "{own}" ')
        self.assertEqual((s["folder"], s["custom"]), (own, own))
        self.assertTrue(os.path.isdir(own))
        self.assertEqual(os.listdir(own), [])          # the write test leaves nothing behind
        rec = recorder.Recorder()
        try:
            self.assertEqual(rec.folder, own)
            self.assertEqual(rec.tracks["cont"].folder(), own)
        finally:
            rec.stop_all(0)

    def test_back_to_default(self):
        recorder.save_folder(os.path.join(self.tmp.name, "own"))
        self.assertEqual(recorder.save_folder("")["custom"], "")
        recorder.save_folder(os.path.join(self.tmp.name, "own"))
        self.assertEqual(recorder.save_folder(recorder.FOLDER)["custom"], "")

    def test_relative_path_refused(self):
        with self.assertRaises(ValueError):
            recorder.save_folder("recs")
        self.assertEqual(recorder.custom_folder(), "")


if __name__ == "__main__":
    unittest.main()

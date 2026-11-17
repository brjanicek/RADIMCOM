"""Tests of the recordings list (recorder.py): file names, the list for the RECORDINGS tab and deleting.

Run: python -m unittest tests.test_recorder
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import recorder  # noqa: E402


class ParseNameTest(unittest.TestCase):
    def test_memory_name(self):
        f = recorder.parse_name("Piestany_TWR_118.575000MHz_AM_20261105_155300.mp3")
        self.assertEqual(f, {"memory": "Piestany TWR", "hz": 118575000, "mode": "AM", "start": "2026-11-05 15:53:00"})

    def test_plain_and_numbered(self):
        f = recorder.parse_name("134.475670MHz_AM_20261110_221021_2.mp3")
        self.assertEqual((f["memory"], f["hz"], f["mode"], f["start"]), ("", 134475670, "AM", "2026-11-10 22:10:21"))

    def test_foreign_file(self):
        self.assertEqual(recorder.parse_name("song.mp3"), {"memory": "", "hz": 0, "mode": "", "start": ""})


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rec = recorder.Recorder(self.tmp.name)
        self.old = os.path.join(self.tmp.name, "145.500000MHz_FM_20261105_155300.mp3")
        self.new = os.path.join(self.tmp.name, "Piestany_TWR_118.575000MHz_AM_20261105_160000.mp3")
        with open(self.old, "wb") as f:
            f.write(b"\0" * 16000)      # 1 s at 128 kbps
        with open(self.new, "wb") as f:
            f.write(b"\0" * 32000)
        os.utime(self.old, (1_700_000_000, 1_700_000_000))
        os.utime(self.new, (1_700_000_100, 1_700_000_100))
        with open(os.path.join(self.tmp.name, "notes.txt"), "w") as f:
            f.write("x")

    def tearDown(self):
        self.rec.stop_all(0)
        self.tmp.cleanup()

    def test_list_newest_first(self):
        files = self.rec.files()
        self.assertEqual([f["name"] for f in files], [os.path.basename(self.new), os.path.basename(self.old)])
        self.assertEqual((files[0]["memory"], files[0]["secs"], files[0]["size"], files[0]["writing"]), ("Piestany TWR", 2, 32000, False))
        self.assertEqual((files[1]["hz"], files[1]["mode"], files[1]["secs"]), (145500000, "FM", 1))

    def test_missing_folder(self):
        self.assertEqual(recorder.Recorder(os.path.join(self.tmp.name, "none")).files(), [])

    def test_delete(self):
        self.rec.delete(os.path.basename(self.old))
        self.assertFalse(os.path.exists(self.old))
        with self.assertRaises(ValueError):
            self.rec.delete("nothing.mp3")
        with self.assertRaises(ValueError):
            self.rec.delete("../notes.txt")

    def test_delete_while_writing(self):
        t = self.rec.tracks["cont"]
        t.enc, t.file = object(), os.path.basename(self.new)
        self.assertTrue(self.rec.files()[0]["writing"])
        with self.assertRaises(ValueError):
            self.rec.delete(os.path.basename(self.new))
        t.enc = None


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
            files = rec.files()
            names = sorted(f["name"] for f in files)
            self.assertEqual(len(files), 4)                               # 2 buttons x 2 stations
            self.assertTrue(any(n.startswith("Radio_FM_187.072000MHz_DAB_") for n in names), names)
            self.assertTrue(any(n.startswith("Rádio_Devín_187.072000MHz_DAB_") for n in names), names)
            big = [f for f in files if f["memory"] == "Radio FM"][0]
            self.assertEqual(big["size"], 20 * len(chunk))               # the bytes unchanged
            self.assertEqual(big["mode"], "DAB")


class ScanKindTest(unittest.TestCase):
    """RECORDINGS › SCAN RECS: the WAV files of the scan in the subfolder scan, length from the header."""

    def test_scan_wavs(self):
        import wave
        with tempfile.TemporaryDirectory() as d:
            rec = recorder.Recorder(d)
            os.makedirs(os.path.join(d, "scan"))
            name = "Piestany_TWR_118.575000MHz_AM_20261115_191200.wav"
            with wave.open(os.path.join(d, "scan", name), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(32000)
                w.writeframes(bytes(32000 * 2 * 3))                   # 3 s
            open(os.path.join(d, "x.mp3"), "wb").close()
            files = rec.files("scan")
            self.assertEqual([f["name"] for f in files], [name])     # only the WAVs of the scan, not the MP3 of REC
            self.assertEqual(files[0]["secs"], 3)
            self.assertEqual(files[0]["memory"], "Piestany TWR")
            self.assertEqual(files[0]["mode"], "AM")
            self.assertEqual([f["name"] for f in rec.files()], ["x.mp3"])
            self.assertTrue(rec.files("scan", {name})[0]["writing"])
            with self.assertRaises(ValueError):
                rec.delete(name, "scan", {name})                       # being written by the scan
            rec.delete(name, "scan")
            self.assertEqual(rec.files("scan"), [])
            with self.assertRaises(ValueError):
                rec.files("other")


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

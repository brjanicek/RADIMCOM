"""Tests of the logs and data files (datafiles.py): day folders, the move of the flat logs, the file tree of
SETTINGS › LOGS (list, read, delete, upload) and pruning old days.

Run: python -m unittest tests.test_datafiles
"""
import calendar
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import datafiles  # noqa: E402


def touch(path, text="x\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


class DayFolderTest(unittest.TestCase):
    def test_paths(self):
        t = calendar.timegm((2026, 11, 19, 23, 59, 0, 0, 0, 0))       # UTC: still the 19th
        self.assertEqual(datafiles.day_file("hfdl", t, root="R"),
                         os.path.join("R", "hfdl", "2026", "11", "19", "hfdl_2026-11-19.txt"))
        self.assertEqual(datafiles.date_dir("scan", "2026-01-02", "R"), os.path.join("R", "scan", "2026", "01", "02"))

    def test_prune_days(self):
        with tempfile.TemporaryDirectory() as root:
            now = calendar.timegm((2026, 11, 19, 12, 0, 0, 0, 0, 0))
            touch(datafiles.day_file("scan", now, "csv", root))
            touch(datafiles.day_file("scan", now - 40 * 86400, "csv", root))
            self.assertEqual(datafiles.prune_days("scan", 31, now, root), 1)
            self.assertEqual(os.listdir(os.path.join(root, "scan", "2026")), ["11"])   # the empty month went


class MigrateTest(unittest.TestCase):
    def test_flat_logs_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, acars = os.path.join(tmp, "logs"), os.path.join(tmp, "acars")
            touch(os.path.join(root, "hfdl_2026-11-10.txt"))
            touch(os.path.join(root, "scan_2026-11-11.csv"))
            touch(os.path.join(acars, "vdl2_2026-11-04.txt"))
            touch(os.path.join(root, "radiosonde", "2026-11-05_W1234567.jsonl"))
            touch(os.path.join(root, "atu", "atu_1_1.json"))                  # not a day log: stays
            self.assertEqual(datafiles.migrate(root, acars), 4)
            for p in (("hfdl", "2026", "11", "10", "hfdl_2026-11-10.txt"), ("scan", "2026", "11", "11", "scan_2026-11-11.csv"),
                      ("vdl2", "2026", "11", "04", "vdl2_2026-11-04.txt"),
                      ("radiosonde", "2026", "11", "05", "2026-11-05_W1234567.jsonl"), ("atu", "atu_1_1.json")):
                self.assertTrue(os.path.isfile(os.path.join(root, *p)), p)
            self.assertFalse(os.path.exists(acars))                            # emptied: removed
            self.assertEqual(datafiles.migrate(root, acars), 0)


class TreeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = dict(datafiles.ROOTS)
        datafiles.ROOTS.clear()
        datafiles.ROOTS["logs"] = (self.tmp.name, "logs")
        touch(os.path.join(self.tmp.name, "hfdl", "2026", "11", "19", "hfdl_2026-11-19.txt"), "a\nb\nc\n")
        touch(os.path.join(self.tmp.name, "hfdl", "2026", "11", "18", "hfdl_2026-11-18.txt"))
        touch(os.path.join(self.tmp.name, ".migrate.lock"), "")

    def tearDown(self):
        datafiles.ROOTS.clear()
        datafiles.ROOTS.update(self.old)
        self.tmp.cleanup()

    def test_list_read_delete_upload(self):
        r = datafiles.roots()[0]
        self.assertEqual((r["key"], r["files"]), ("logs", 2))                 # hidden files not counted
        top = datafiles.list_dir("logs", "")
        self.assertEqual(([d["name"] for d in top["dirs"]], top["files"]), (["hfdl"], []))
        day = datafiles.list_dir("logs", "hfdl/2026/11/19")
        self.assertEqual([f["name"] for f in day["files"]], ["hfdl_2026-11-19.txt"])
        self.assertTrue(day["files"][0]["view"])
        t = datafiles.read_text("logs", "hfdl/2026/11/19/hfdl_2026-11-19.txt", tail=4)
        self.assertEqual((t["text"], t["cut"]), ("c\n", True))               # the end, from a whole line
        for bad in ("../x", "C:/Windows", "hfdl/../../x"):
            with self.assertRaises(ValueError):
                datafiles.list_dir("logs", bad)
        with self.assertRaises(ValueError):
            datafiles.list_dir("nothing", "")
        with self.assertRaises(ValueError):
            datafiles.delete_paths("logs", [""])                              # not the whole root
        self.assertEqual(datafiles.save_upload("logs", "hfdl/2026/11/19", "x.jsonl", io.BytesIO(b"{}")), {"saved": "x.jsonl"})
        with self.assertRaises(ValueError):
            datafiles.save_upload("logs", "hfdl/2026/11/19", "x.jsonl", io.BytesIO(b""))   # not over a file
        with self.assertRaises(ValueError):
            datafiles.save_upload("logs", "", ".hidden", io.BytesIO(b""))
        self.assertEqual(datafiles.save_upload("logs", "", "../up.txt", io.BytesIO(b""))["saved"], "up.txt")   # name only
        r = datafiles.delete_paths("logs", ["hfdl/2026/11/19", "hfdl/2026/11/18/hfdl_2026-11-18.txt"])
        self.assertEqual(r, {"deleted": 3, "kept": []})
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "hfdl")))   # the emptied folders went


if __name__ == "__main__":
    unittest.main()

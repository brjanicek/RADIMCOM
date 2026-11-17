"""Tests of the antennas of the station (antennas.py: save, load, ids, checks, covers).

Run: python -m unittest tests.test_antennas
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import antennas  # noqa: E402


class AntennasTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.old = antennas.ANTENNAS_PATH
        antennas.ANTENNAS_PATH = os.path.join(self.dir.name, "antennas.json")   # not data\antennas.json of this PC
        antennas._cache[:] = [None, []]

    def tearDown(self):
        antennas.ANTENNAS_PATH = self.old
        antennas._cache[:] = [None, []]
        self.dir.cleanup()

    def test_empty_without_file(self):
        self.assertEqual(antennas.load(), [])
        self.assertIsNone(antennas.get("x"))

    def test_save_load_and_ids(self):
        out = antennas.save([
            {"name": "Discone roof", "type": "discone", "ranges": [[25e6, 1300e6]], "pol": "V"},
            {"name": "Discone roof", "type": "discone"},
            {"id": "yagi", "name": "Arrow", "type": "yagi", "rotor": True},
        ])
        self.assertEqual([a["id"] for a in out], ["discone-roof", "discone-roof-2", "yagi"])
        self.assertTrue(out[0]["outdoor"])
        self.assertTrue(antennas.get("yagi")["rotor"])
        with open(antennas.ANTENNAS_PATH, encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["antennas"]), 3)

    def test_new_antenna_does_not_take_existing_id(self):
        out = antennas.save([{"name": "Yagi"}, {"id": "yagi", "name": "Old yagi"}])
        self.assertEqual([a["id"] for a in out], ["yagi-2", "yagi"])

    def test_checks(self):
        for bad in ([{"name": ""}], [{"name": "A", "type": "spaceship"}], [{"name": "A", "ranges": [[2e6, 1e6]]}], [{"name": "A", "ranges": [[1e6]]}], [{"name": "A", "ranges": "144-146"}],
                    [{"name": "A", "pol": "Q"}], [{"id": "a", "name": "A"}, {"id": "a", "name": "B"}],
                    [{"name": "A", "gain_dbi": "x"}], "nope"):
            with self.assertRaises(ValueError, msg=bad):
                antennas.save(bad)

    def test_broken_entry_in_file_is_skipped(self):
        with open(antennas.ANTENNAS_PATH, "w", encoding="utf-8") as f:
            json.dump({"antennas": [{"name": ""}, {"id": "ok", "name": "OK"}]}, f)
        self.assertEqual([a["id"] for a in antennas.load()], ["ok"])

    def test_covers_several_bands(self):
        a = antennas.save([{"name": "X-50", "ranges": [[430e6, 440e6], [144e6, 146e6]]}])[0]
        self.assertEqual(a["ranges"], [[144e6, 146e6], [430e6, 440e6]])      # sorted
        self.assertTrue(antennas.covers(a, 145.8e6))
        self.assertTrue(antennas.covers(a, 435e6))
        self.assertFalse(antennas.covers(a, 300e6))
        self.assertFalse(antennas.covers(a, 7.1e6))
        self.assertIsNone(antennas.covers({"ranges": []}, 7e6))

    def test_old_single_range_is_taken_over(self):
        with open(antennas.ANTENNAS_PATH, "w", encoding="utf-8") as f:
            json.dump({"antennas": [{"id": "d", "name": "Disc", "f_min_hz": 25e6, "f_max_hz": 1300e6},
                                    {"id": "w", "name": "Whip", "f_min_hz": 1e6, "f_max_hz": None}]}, f)
        d, w = antennas.load()
        self.assertEqual(d["ranges"], [[25e6, 1300e6]])
        self.assertNotIn("f_min_hz", d)
        self.assertTrue(antennas.covers(w, 5e9))


if __name__ == "__main__":
    unittest.main()

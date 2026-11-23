"""wefax.py: dragging the image sideways (action "shift") and the slant correction move the lines received so far,
the following lines keep the new alignment, and an image already saved is written again.

Run: python -m unittest tests.test_wefax_shift
"""
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wefax  # noqa: E402


class Shift(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.events = []
        self.d = wefax.WefaxDecoder(lambda k, v: self.events.append(k), save_dir=self.tmp.name)
        W = 100
        row = np.zeros(W, np.uint8)
        row[10] = 255                                   # a white line at x = 10
        self.d.rows = [row.tobytes() for _ in range(40)]

    def tearDown(self):
        self.tmp.cleanup()

    def white_x(self):
        return {int(np.argmax(np.frombuffer(r, np.uint8))) for r in self.d.rows}

    def test_drag_rolls_all_lines(self):
        self.d.command({"action": "shift", "dx": 0.25})
        self.assertEqual(self.white_x(), {35})
        self.d.command({"action": "shift", "dx": -0.4})  # wraps round the left edge
        self.assertEqual(self.white_x(), {95})
        self.assertIn("wefaxreload", self.events)

    def test_click_makes_left_edge(self):
        self.d.command({"action": "shift", "dx": -0.10})
        self.assertEqual(self.white_x(), {0})

    def test_saved_image_written_again(self):
        self.d._finish()
        path = os.path.join(self.tmp.name, self.d.saved)
        before = open(path, "rb").read()
        self.d.command({"action": "shift", "dx": 0.3})
        self.assertNotEqual(open(path, "rb").read(), before)
        before = open(path, "rb").read()
        self.d.command({"slant_ppm": 2000})
        self.assertNotEqual(open(path, "rb").read(), before)


if __name__ == "__main__":
    unittest.main()

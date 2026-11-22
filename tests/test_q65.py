"""q65.py: jt9's output lines, the calling station of a message, the settings and the recording of the T/R periods.
Run: python -m unittest tests.test_q65
(jt9.exe itself is checked by hand with WAV files of q65sim / jt65sim of WSJT-X, see installer/build_jt9.sh)"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import q65  # noqa: E402

T0 = 1_800_000_000.0          # a multiple of 300 s: the start of a period of every length


class ParseTest(unittest.TestCase):
    def test_q65_line(self):
        d = q65.parse_line("1230 -24  0.1  800 :  CQ OM2AMR JN88                        q0 ")
        self.assertEqual(d, {"snr": -24, "dt": 0.1, "df": 800, "msg": "CQ OM2AMR JN88", "flags": "q0"})

    def test_q65_short_period_line(self):
        d = q65.parse_line("123030 -22  0.0 2100 :  OK1ABC OM2AMR JN88                    q32")
        self.assertEqual((d["snr"], d["df"], d["msg"], d["flags"]), (-22, 2100, "OK1ABC OM2AMR JN88", "q32"))

    def test_jt65_line(self):
        d = q65.parse_line("0001 -20 -0.3  600 #  K1ABC W9XYZ EN37          ")
        self.assertEqual((d["snr"], d["dt"], d["df"], d["msg"], d["flags"]), (-20, -0.3, 600, "K1ABC W9XYZ EN37", ""))

    def test_other_lines(self):
        self.assertIsNone(q65.parse_line("<DecodeFinished>   0   1        0"))
        self.assertIsNone(q65.parse_line(""))


class SenderTest(unittest.TestCase):
    def test_messages(self):
        self.assertEqual(q65.sender("CQ OM2AMR JN88"), ("OM2AMR", "JN88"))
        self.assertEqual(q65.sender("CQ DX OM2AMR JN88"), ("OM2AMR", "JN88"))
        self.assertEqual(q65.sender("OK1ABC OM2AMR JN88"), ("OM2AMR", "JN88"))
        self.assertEqual(q65.sender("OK1ABC OM2AMR -15"), ("OM2AMR", None))
        self.assertEqual(q65.sender("OK1ABC OM2AMR RR73"), ("OM2AMR", None))
        self.assertEqual(q65.sender("OK1ABC <OM2AMR/P> R-12"), ("OM2AMR/P", None))
        self.assertEqual(q65.sender("TNX 73 GL"), (None, None))


class SettingsTest(unittest.TestCase):
    def test_mode_fallbacks(self):
        d = q65.Q65Decoder(on_decode=lambda d: None)
        d.set_mode("JT65", 30, "E")
        self.assertEqual((d.mode, d.period, d.sub), ("JT65", 60, "A"))
        d.set_mode("Q65", 120, "d")
        self.assertEqual((d.mode, d.period, d.sub), ("Q65", 120, "D"))
        d.set_mode("FT8", 7, None)
        self.assertEqual((d.mode, d.period, d.sub), ("Q65", 30, "D"))

    def test_apply(self):
        d = q65.Q65Decoder(on_decode=lambda d: None)
        cfg = {}
        self.assertTrue(d.apply({"q65_mode": "JT65", "q65_sub": "B"}, cfg))
        self.assertEqual(cfg, {"q65_mode": "JT65", "q65_period": 60, "q65_sub": "B"})
        self.assertFalse(d.apply({"ft8": True}, cfg))


class RecordTest(unittest.TestCase):
    """_samples cuts whole periods aligned to the PC clock; _decode is replaced to catch them."""

    def setUp(self):
        self.dec = q65.Q65Decoder(on_decode=lambda d: None)
        self.dec.set_mode("Q65", 15, "A")
        self.dec.enabled = True
        self.got = []
        self.dec._decode = lambda audio, t0, dial, key: (self.got.append((len(audio), t0, dial, key)),
                                                         setattr(self.dec, "_busy", False))

    def run_blocks(self, t_start, secs, dial=50275000, block=0.1):
        n = int(round(block * q65.RATE))
        t = t_start
        for _ in range(int(round(secs / block))):
            t += block
            self.dec._samples(np.ones(n, np.float32), dial, t)

    def test_periods(self):
        self.run_blocks(T0 - 3.0, 3.0 + 15 * 3 + 0.05)
        self.assertEqual([g[1] for g in self.got], [T0, T0 + 15, T0 + 30])
        self.assertTrue(all(g[0] == 15 * q65.RATE for g in self.got))

    def test_late_start_padded(self):
        # the first samples come 0.5 s after the start of the period: still recorded (zeros in front)
        self.run_blocks(T0 + 0.4, 15.0)
        self.assertEqual([g[1] for g in self.got], [T0])

    def test_retune_skips(self):
        self.run_blocks(T0 - 0.1, 5.0, dial=50275000)
        self.run_blocks(T0 + 4.9, 25.2, dial=144116000)
        self.assertEqual([(g[1], g[2]) for g in self.got], [(T0 + 15, 144116000)])


if __name__ == "__main__":
    unittest.main()

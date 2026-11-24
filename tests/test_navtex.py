"""navtex.py: SITOR-B / NAVTEX from a synthetic complex baseband (encoder of the module)."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import navtex  # noqa: E402

FS = 32000.0
DIAL = 4207800.0
MSG = ("ZCZC MA84\n311813 UTC NOV 25\nISTANBUL TURK RADYO\nNAVTEX NAV WARNING 123/25\n"
       "AEGEAN SEA. FIRING EXERCISE 38-12N 024-30E RADIUS 5 NM.\nNNNN\n")


def signal(text=MSG, tone=1700.0, snr_db=15.0, seed=1, fade=None, lead=1.0):
    """Baseband: lead seconds of noise, the transmission at tone Hz, 1 s of noise; fade = (from, to) s set to noise."""
    rng = np.random.default_rng(seed)
    sig = navtex.modulate(navtex.encode_text(text), FS, tone)
    n_lead = int(lead * FS)
    x = np.zeros(n_lead + len(sig) + int(FS), np.complex64)
    x[n_lead:n_lead + len(sig)] = sig
    if fade:
        x[int(fade[0] * FS):int(fade[1] * FS)] = 0
    # the noise in a 3 kHz band: snr_db is the signal over the noise of that band
    noise = (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x))) / np.sqrt(2)
    noise *= np.sqrt(FS / 3000.0) * 10 ** (-snr_db / 20)
    return (x + noise).astype(np.complex64)


def run(x, block=1600):
    ev = []
    d = navtex.NavtexDecoder(lambda k, v: ev.append((k, v)))
    d.set_enabled(True)
    for i in range(0, len(x), block):
        d.feed(x[i:i + block], FS, DIAL)
    text = "".join(v["t"] for k, v in ev if k == "navtextext")
    msgs = [v for k, v in ev if k == "navtex"]
    return d, text, msgs


class NavtexTest(unittest.TestCase):
    def test_code_table(self):
        """CCIR 476: all 35 words with four 1s, each once."""
        self.assertEqual(len(navtex.LETTERS), 35)
        self.assertTrue(all(navtex._weight(c) == 4 for c in navtex.LETTERS))

    def test_message(self):
        d, text, msgs = run(signal())
        self.assertIn("ISTANBUL TURK RADYO", text)
        self.assertIn("38-12N 024-30E RADIUS 5 NM.", text)
        self.assertEqual(len(msgs), 1, msgs)
        m = msgs[0]
        self.assertEqual((m["station"], m["subject"], m["number"]), ("M", "A", "84"))
        self.assertEqual(m["subject_name"], "Navigational warning")
        self.assertIn("FIRING EXERCISE", m["text"])
        self.assertFalse(m["text"].endswith("NNNN"))
        self.assertEqual(m["end"], "")
        self.assertEqual(m["lost"], 0)
        self.assertAlmostEqual(d.info()["offset_hz"], 1700, delta=25)

    def test_tones_anywhere(self):
        """The tones below the tuned frequency (LSB side) are found too."""
        _, text, msgs = run(signal(tone=-900.0))
        self.assertIn("FIRING EXERCISE", text)
        self.assertEqual(len(msgs), 1)

    def test_fade_taken_from_the_other_copy(self):
        """A fade of 40 ms (4 bits) in the text (the phasing takes 1 + 5.6 s) hits one copy of a character: it is taken
        from the other one; without the RX copy that character would be lost."""
        x = signal(fade=(9.0, 9.04), snr_db=20)
        _, text, msgs = run(x)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["lost"], 0, msgs[0]["text"])
        self.assertIn("38-12N 024-30E RADIUS 5 NM.", text)
        # the fade did hit a word: one of the two copies there is not a valid word
        d = navtex.NavtexDecoder(lambda k, v: None)
        seen = []
        orig = d._code
        d._code = lambda c, done: (seen.append(c), orig(c, done))[1]
        d.set_enabled(True)
        for i in range(0, len(x), 1600):
            d.feed(x[i:i + 1600], FS, DIAL)
        self.assertTrue(any(not navtex.VALID[c] for c in seen))

    def test_weak(self):
        """5 dB over the noise of 3 kHz: still read, at most a few characters lost."""
        _, text, msgs = run(signal(snr_db=5, seed=3))
        self.assertEqual(len(msgs), 1)
        self.assertLessEqual(msgs[0]["lost"], 3, msgs[0]["text"])
        self.assertIn("RADYO", text)

    def test_noise_only(self):
        rng = np.random.default_rng(7)
        x = ((rng.standard_normal(int(20 * FS)) + 1j * rng.standard_normal(int(20 * FS))) / np.sqrt(2)).astype(np.complex64)
        d, text, msgs = run(x)
        self.assertEqual(msgs, [])
        self.assertEqual(text.strip(), "")
        self.assertFalse(d.info()["sync"])

    def test_retune_ends_the_message(self):
        """Retuned in the middle of a message: it is reported as cut off."""
        x = signal()
        ev = []
        d = navtex.NavtexDecoder(lambda k, v: ev.append((k, v)))
        d.set_enabled(True)
        half = len(x) * 3 // 5
        for i in range(0, half, 1600):
            d.feed(x[i:min(i + 1600, half)], FS, DIAL)
        d.feed(x[half:half + 1600], FS, DIAL + 5000)
        msgs = [v for k, v in ev if k == "navtex"]
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["end"], "retuned")


if __name__ == "__main__":
    unittest.main()

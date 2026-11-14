"""Tests of the POCSAG decoder (pocsag.py): codewords, framer and the whole chain on synthetic FSK, no radio.

Run: python -m unittest tests.test_pocsag   (from the RADIMCOM folder)
"""
import os
import random
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pocsag  # noqa: E402

MSGS = [(1234560, 3, "HELLO BRATISLAVA 73", "alpha"), (300001, 0, "0421 555-123", "numeric"), (77777, 1, "", "tone")]


def fsk(bits, baud, fs=32000.0, dev=4500.0, snr_db=20.0, inverted=False, offset=700.0, seed=1):
    """Complex baseband of 2-FSK (NRZ, 1 = +dev unless inverted), with a tuning offset and noise."""
    rnd = np.random.default_rng(seed)
    sps = fs / baud
    lead = int(0.3 * fs)
    n = int(len(bits) * sps)
    sym = np.array(bits, np.float64) * 2 - 1
    if inverted:
        sym = -sym
    f = np.concatenate((np.zeros(lead), sym[(np.arange(n) / sps).astype(int)] * dev, np.zeros(lead))) + offset
    z = np.exp(2j * np.pi * np.cumsum(f) / fs)
    z[:lead] = 0
    z[-lead:] = 0
    sigma = 10 ** (-snr_db / 20) / np.sqrt(2)
    z = z + sigma * (rnd.standard_normal(len(z)) + 1j * rnd.standard_normal(len(z)))
    return z.astype(np.complex64)


def run(z, fs=32000.0, block=1024, rate="all"):
    got = []
    d = pocsag.PocsagDecoder(lambda k, m: got.append(m) if k == "pocsag" else None)
    d.set_options({"rate": rate})
    d.set_enabled(True)
    for k in range(0, len(z), block):
        d.feed(z[k:k + block], fs, 162.47e6)
    return d, got


class Codewords(unittest.TestCase):
    def test_encode_is_valid(self):
        for v in (0, 1, 0x1FFFFF, 0x12345):
            cw = pocsag.bch_encode(v)
            self.assertEqual(pocsag.correct(cw), (cw, 0))
            self.assertEqual(bin(cw).count("1") % 2, 0)

    def test_idle_and_sync_are_codewords(self):
        self.assertEqual(pocsag.correct(pocsag.IDLE)[1], 0)

    def test_corrects_one_and_two_bits(self):
        rnd = random.Random(5)
        for _ in range(300):
            cw = pocsag.bch_encode(rnd.getrandbits(21))
            i, j = rnd.sample(range(1, 32), 2)
            self.assertEqual(pocsag.correct(cw ^ (1 << i)), (cw, 1))
            self.assertEqual(pocsag.correct(cw ^ (1 << i) ^ (1 << j)), (cw, 2))

    def test_three_bits_mostly_rejected(self):
        rnd = random.Random(6)
        wrong = 0
        for _ in range(300):
            cw = pocsag.bch_encode(rnd.getrandbits(21))
            e = 0
            for i in rnd.sample(range(1, 32), 3):
                e |= 1 << i
            fixed, _ = pocsag.correct(cw ^ e)
            wrong += fixed is not None and fixed != cw
        self.assertEqual(wrong, 0)        # odd number of errors: the parity bit catches the false 2-bit fix


class Payload(unittest.TestCase):
    def test_kinds(self):
        bits = pocsag.encode(MSGS)
        f = pocsag.Framer()
        out = f.feed(bits)
        self.assertEqual([m["ric"] for m in out], [m[0] for m in MSGS])
        for m, (ric, func, text, kind) in zip(out, MSGS):
            self.assertEqual(m["func"], func)
            self.assertEqual(pocsag.guess_kind(func, m["words"]), kind)
            if kind == "alpha":
                self.assertEqual(pocsag.alpha_text(m["words"]), text)
            if kind == "numeric":
                self.assertEqual(pocsag.numeric_text(m["words"]), text)

    def test_long_message_over_batches(self):
        text = "The quick brown fox jumps over the lazy dog 0123456789 " * 3
        out = pocsag.Framer().feed(pocsag.encode([(1000007, 3, text, "alpha")]))
        self.assertEqual(pocsag.alpha_text(out[0]["words"]), text)

    def test_bit_errors_corrected(self):
        bits = pocsag.encode(MSGS)
        rnd = random.Random(2)
        start = 576 + 32                   # after the preamble and the first sync: two errors in some codewords
        for k in range(start, len(bits) - 32, 32):
            if (k - 576) % (17 * 32) == 0:
                continue                   # not in the sync codewords
            for i in rnd.sample(range(32), rnd.randint(0, 2)):
                bits[k + i] ^= 1
        out = pocsag.Framer().feed(bits)
        self.assertEqual(pocsag.alpha_text(out[0]["words"]), MSGS[0][2])
        self.assertEqual(out[0]["bad"], 0)

    def test_lost_codeword_is_question_mark(self):
        bits = pocsag.encode([(1234560, 3, "ABCDEFGHIJKLMNOP", "alpha")])
        k = 576 + 32 * 2                   # second codeword after the sync: the first message codeword
        for i in (3, 9, 17):               # three wrong bits: more than BCH corrects, the parity catches them
            bits[k + i] ^= 1
        out = pocsag.Framer().feed(bits)
        self.assertEqual(out[0]["bad"], 1)
        self.assertTrue(out[0]["words"][0] is None)
        self.assertIn("?", pocsag.alpha_text(out[0]["words"]))


class Chain(unittest.TestCase):
    def test_all_speeds_both_polarities(self):
        for baud in pocsag.BAUDS:
            for inv in (False, True):
                with self.subTest(baud=baud, inverted=inv):
                    d, got = run(fsk(pocsag.encode(MSGS), baud, inverted=inv, seed=baud + inv))
                    self.assertEqual([(m["ric"], m["kind"], m["text"]) for m in got],
                                     [(r, k, t) for r, f, t, k in MSGS])
                    self.assertTrue(all(m["baud"] == baud and m["inverted"] == inv for m in got))

    def test_37500_rate_and_weak_signal(self):
        d, got = run(fsk(pocsag.encode(MSGS), 1200, fs=37500.0, snr_db=8.0, seed=9), fs=37500.0)
        self.assertEqual(got[0]["text"], MSGS[0][2])

    def test_rate_option(self):
        d, got = run(fsk(pocsag.encode(MSGS), 512), rate="1200")
        self.assertEqual(got, [])
        self.assertEqual(d.info()["rates"], [1200])

    def test_noise_gives_nothing(self):
        rnd = np.random.default_rng(3)
        z = (rnd.standard_normal(32000 * 20) + 1j * rnd.standard_normal(32000 * 20)).astype(np.complex64)
        d, got = run(z)
        self.assertEqual(got, [])

    def test_duplicates_and_info(self):
        bits = pocsag.encode(MSGS)
        d, got = run(fsk(bits + bits, 1200))
        self.assertEqual(len(got), 3)         # the repeat within DUP_SEC is shown once
        i = d.info()
        self.assertEqual(i["ok"], 3)
        self.assertEqual({r["ric"] for r in i["rics"]}, {m[0] for m in MSGS})
        d.clear()
        self.assertEqual(d.info()["messages"], [])


if __name__ == "__main__":
    unittest.main()

"""msk144.py: the LDPC code, CRC, encoder/decoder round trip, simulated meteor pings in noise (frequency offset, both
polarities, short weak pings with averaging) and the whole path from the receiver baseband.

Run: python -m unittest tests.test_msk144
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import msk144  # noqa: E402

if msk144.IMPORT_ERROR is None:
    from PyFT8 import transmitter as _tx  # noqa: E402  (pyaudio stubbed by ft8.py)

FS = msk144.FS


def bits_of(c1, c2, gr):
    v = _tx.pack_message(c1, c2, gr)[1]
    return np.array([(v >> (76 - i)) & 1 for i in range(77)], np.uint8)


def ping(frame, seconds, df, snr_db, ping_s=0.2, at_s=2.0, seed=1, conj=False):
    """Complex 12 kHz baseband (1500 Hz = 0): the frame repeated during a ping with an exponential tail, white noise;
    snr_db = signal power at the ping peak over the noise power in 2500 Hz."""
    rng = np.random.default_rng(seed)
    n = int(seconds * FS)
    reps = np.tile(frame, n // len(frame) + 1)[:n]
    t = np.arange(n) / FS
    env = np.where(t < at_s, 0.0, np.exp(-(t - at_s) / ping_s))
    x = reps * env * np.exp(2j * np.pi * df * t)
    if conj:
        x = np.conj(x)
    sigma = np.sqrt(FS / 2500 / 10 ** (snr_db / 10) / 2)
    y = x + sigma * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    return np.convolve(y, msk144.lowpass(1350.0, FS, 255), mode="same").astype(np.complex64)   # as Msk144Decoder.feed


def decode_stream(x):
    an = msk144.Analyser()
    found = set()
    for i in range(0, len(x) - msk144.WIN + 1, msk144.HOP):
        for hit in an.window(x[i:i + msk144.WIN]):
            found.add((hit[0], round(hit[1])))
    return found


@unittest.skipIf(msk144.IMPORT_ERROR, "PyFT8 not installed")
class Msk144(unittest.TestCase):
    def test_codewords_satisfy_the_checks(self):
        rng = np.random.default_rng(1)
        for _ in range(20):
            ch = msk144.encode(rng.integers(0, 2, 77))
            cw = np.concatenate((ch[8:56], ch[64:144])).astype(int)
            self.assertFalse((np.bincount(msk144.EDGE_CHK, weights=cw[msk144.EDGE_BIT], minlength=38) % 2).any())

    def test_bp_corrects_errors(self):
        b = bits_of("CQ", "K1ABC", "FN42")
        ch = msk144.encode(b)
        cw = np.concatenate((ch[8:56], ch[64:144])).astype(float)
        llr = (2 * cw - 1) * 4.0
        llr[[3, 40, 101]] *= -1                               # three confidently wrong bits
        res = msk144.bp_decode(llr)
        self.assertIsNotNone(res)
        self.assertTrue(np.array_equal(res[0], b))
        self.assertEqual(msk144.unpack(res[0]), "CQ K1ABC FN42")

    def test_frame_round_trip(self):
        frame = msk144.modulate(msk144.encode(bits_of("W9XYZ", "K1ABC", "R-07")))
        res = msk144.decode_frame(frame * np.exp(0.7j))
        self.assertEqual(res[0], "W9XYZ K1ABC R-07")

    def test_pings_in_noise(self):
        frame = msk144.modulate(msk144.encode(bits_of("CQ", "K1ABC", "FN42")))
        # tuned 2026-11-21: 0.3 s pings decode down to ~5 dB (3 dB: half), 1 s pings to ~3 dB (1 dB: two thirds)
        for df, snr, ps, conj in ((0.0, 7, 0.3, False), (37.0, 5, 0.3, False), (-62.0, 6, 0.5, True), (85.0, 3, 1.0, False)):
            found = decode_stream(ping(frame, 4.0, df, snr, ping_s=ps, seed=int(abs(df)) + 1, conj=conj))
            msgs = {m for m, _ in found}
            self.assertEqual(msgs, {"CQ K1ABC FN42"}, (df, snr, conj, found))
            at = -df if conj else df                         # the conjugate (inverted sideband) sits on the mirror frequency
            self.assertTrue(any(abs(f - at) <= 3 for _, f in found), (df, found))

    def test_noise_alone(self):
        rng = np.random.default_rng(9)
        x = (rng.standard_normal(int(10 * FS)) + 1j * rng.standard_normal(int(10 * FS))).astype(np.complex64)
        self.assertEqual(decode_stream(x), set())

    def test_from_the_receiver_baseband(self):
        fs = 37500.0
        frame = msk144.modulate(msk144.encode(bits_of("CQ", "K1ABC", "FN42")))
        x12 = ping(frame, 3.0, 20.0, 15, seed=4)
        t12 = np.arange(len(x12)) / FS
        t = np.arange(int(3.0 * fs)) / fs
        base = (np.interp(t, t12, x12.real) + 1j * np.interp(t, t12, x12.imag)) * np.exp(2j * np.pi * 1500 * t)
        got = []
        dec = msk144.Msk144Decoder(on_decode=got.append)
        dec.set_enabled(True)
        for i in range(0, len(base), 4096):
            dec.feed(base[i:i + 4096].astype(np.complex64), fs, 144360000)
        dec._q.put((0, np.zeros(0), 0))           # let the worker finish the queue
        import time
        for _ in range(100):
            if got:
                break
            time.sleep(0.05)
        self.assertTrue(got, "no decode")
        self.assertEqual(got[0]["msg"], "CQ K1ABC FN42")
        self.assertLess(abs(got[0]["freq_hz"] - 144361520), 4)


if __name__ == "__main__":
    unittest.main()

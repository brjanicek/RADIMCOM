"""bpsk.py + funcube.py: AO-40 FEC (Reed-Solomon, Viterbi, frame), FUNcube telemetry, the BPSK demodulator on
synthetic signals (AO-40 DBPSK 1200 Bd with Doppler, AX.25 BPSK 1200 Bd NRZI and 9600 Bd G3RUH) and the decoder.
Run: python -m unittest tests.test_bpsk
(checked by hand on a recording of FUNcube-1 / AO-73: every frame decoded with 0 sync errors and ~5 channel errors)"""
import os
import sys
import time
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpsk  # noqa: E402
import funcube as fc  # noqa: E402
import packet  # noqa: E402

RNG = np.random.default_rng(7)


def modulate(levels, baud, fs, f0, drift=0.0, esn0_db=None, lead=0.3):
    """Line levels 0/1 -> complex baseband: BPSK with raised-cosine pulses on a carrier at f0 Hz (+ drift Hz/s),
    complex white noise for the given Es/N0; lead s of noise before and after."""
    sps = int(fs // baud)
    assert sps * baud == fs, "fs must be a multiple of the baud rate"
    a = 2.0 * np.asarray(levels, np.float64) - 1.0
    up = np.zeros(len(a) * sps)
    up[::sps] = a
    t = np.arange(-4 * sps, 4 * sps + 1) / sps
    with np.errstate(divide="ignore", invalid="ignore"):
        h = np.sinc(t) * np.cos(np.pi * 0.5 * t) / (1 - (2 * 0.5 * t) ** 2)
    h[~np.isfinite(h)] = np.pi / 4 * np.sinc(1 / (2 * 0.5))
    x = np.convolve(up, h, mode="same")
    pad = np.zeros(int(lead * fs))
    x = np.concatenate((pad, x, pad))
    n = np.arange(len(x))
    phase = 2 * np.pi * np.cumsum(f0 + drift * n / fs) / fs + 1.0
    z = x * np.exp(1j * phase)
    if esn0_db is not None:
        es = np.mean(np.abs(z[len(pad):-len(pad)]) ** 2) * sps
        n0 = es / 10 ** (esn0_db / 10)
        z = z + np.sqrt(n0 / 2) * (RNG.normal(size=len(z)) + 1j * RNG.normal(size=len(z)))
    return z.astype(np.complex64)


def differential(bits, start=0):
    """DBPSK: a 1 keeps the phase, a 0 turns it (as the decoder reads them)."""
    out, lv = [], start
    for b in bits:
        if not b:
            lv ^= 1
        out.append(lv)
    return out


def ao40_frame_bytes(seq=123456, sat_id=2, ftype=4):
    d = bytearray(RNG.integers(0, 256, fc.DATA_BYTES, dtype=np.uint8).tobytes())
    d[0] = (sat_id << 6) | ftype
    return bytes(d)


class ReedSolomonTest(unittest.TestCase):
    def codeword(self):
        msg = [0] * 95 + list(RNG.integers(0, 256, 128))
        return msg + fc.rs_parity(msg)

    def test_clean(self):
        cw = self.codeword()
        self.assertEqual(fc.rs_decode(cw[:], 95), 0)

    def test_corrects_16(self):
        cw = self.codeword()
        bad = cw[:]
        for p in RNG.choice(np.arange(95, 255), 16, replace=False):
            bad[p] ^= int(RNG.integers(1, 256))
        self.assertEqual(fc.rs_decode(bad, 95), 16)
        self.assertEqual(bad, cw)

    def test_fails_17(self):
        bad = self.codeword()
        for p in RNG.choice(np.arange(95, 255), 17, replace=False):
            bad[p] ^= int(RNG.integers(1, 256))
        self.assertEqual(fc.rs_decode(bad, 95), -1)


class Ao40Test(unittest.TestCase):
    def test_scrambler(self):
        self.assertEqual(list(fc.PN[:5]), [0xFF, 0x48, 0x0E, 0xC0, 0x9A])

    def test_roundtrip(self):
        data = ao40_frame_bytes()
        bits = fc.encode_frame(data)
        self.assertEqual(len(bits), fc.FRAME_SYMS)
        self.assertTrue(np.array_equal(bits[::fc.ROWS], fc.SYNC))
        out, info = fc.decode_frame(2.0 * bits - 1)
        self.assertEqual(out, data)
        self.assertEqual(info["ch_err"], 0)

    def test_noise(self):
        data = ao40_frame_bytes()
        soft = 2.0 * fc.encode_frame(data) - 1 + RNG.normal(0, 0.8, fc.FRAME_SYMS)    # Es/N0 ~ 2 dB
        self.assertEqual(fc.decode_frame(soft)[0], data)

    def test_sync_search(self):
        bits = fc.encode_frame(ao40_frame_bytes())
        soft = np.concatenate((RNG.normal(0, 1, 777), 2.0 * bits - 1, RNG.normal(0, 1, 300)))
        self.assertEqual(fc.find_sync(soft), [(777, 0)])


class TelemetryTest(unittest.TestCase):
    def test_header(self):
        t = fc.parse(bytes([(2 << 6) | 13]) + bytes(255))
        self.assertEqual((t["sat"], t["type"]), ("FUNcube-1 (AO-73)", "FM1"))
        self.assertEqual(fc.parse(bytes([(2 << 6) | 4]) + bytes(255))["type"], "WO5")
        self.assertEqual(fc.parse(bytes([(2 << 6) | 16]) + bytes(255))["type"], "HR2")

    def test_realtime_fields(self):
        rt = bytearray(55)
        rt[8:10] = (7840).to_bytes(2, "big")         # battery mV
        rt[10:12] = (210).to_bytes(2, "big")         # system current mA
        rt[19] = 21                                  # battery temperature
        bits = np.zeros(55 * 8, np.uint8)
        bits[:] = np.unpackbits(np.frombuffer(bytes(rt), np.uint8))
        # sequence number: 24 bits after EPS (24 B), BOB (100 bits), RF (6 B), PA (4 B), antennas (2 B + 4 bits)
        pos = 24 * 8 + 100 + 6 * 8 + 4 * 8 + 2 * 8 + 4
        bits[pos:pos + 24] = [int(c) for c in f"{1021989:024b}"]
        data = bytes([(2 << 6) | 0]) + np.packbits(bits).tobytes() + bytes(200)
        t = fc.parse(data)
        self.assertEqual((t["eps"]["batt_mV"], t["eps"]["sys_mA"], t["eps"]["batt_C"]), (7840, 210, 21))
        self.assertEqual(t["sw"]["seq"], 1021989)
        self.assertIn("batt 7.84 V", fc.summary(t))

    def test_fitter_message(self):
        data = bytes([(2 << 6) | 13]) + bytes(55) + b"Hello from FUNcube".ljust(200, b"\0")
        self.assertEqual(fc.parse(data)["message"], "Hello from FUNcube")


class DemodTest(unittest.TestCase):
    def test_ao40_dbpsk_doppler(self):
        data = ao40_frame_bytes()
        lv = differential([1] * 400 + list(fc.encode_frame(data)) + [1] * 200)
        z = modulate(lv, 1200, 48000, 1530.0, drift=-40.0, esn0_db=6)
        r = bpsk.demod(z, 48000, 1200, -3000, 3000)
        self.assertAlmostEqual(r["freq"], 1530 - 40 * 2.7, delta=60)
        found = fc.find_sync(r["soft"])
        self.assertEqual(len(found), 1)
        self.assertEqual(fc.decode_frame(r["soft"][found[0][0]:])[0], data)

    def ax25(self, baud, fs, scrambled, f0):
        payload = packet.build("OM2AMR-1", "CQ", info=b">BPSK test frame 1234567890")
        raw, _ = packet.hdlc_encode(payload, preamble=40, postamble=4, nrzi=False)
        lv = differential(raw)                     # NRZI = differential: a 0 turns the phase
        if scrambled:
            lv = packet.Scrambler().feed(lv)
        z = modulate(lv, baud, fs, f0, esn0_db=10)
        r = bpsk.demod(z, fs, baud, -0.4 * fs + baud, 0.4 * fs - baud)
        return payload, bpsk.ax25_frames(r["soft"])

    def test_ax25_1200(self):
        payload, frames = self.ax25(1200, 48000, False, -2200.0)
        self.assertIn(("AX.25", payload), frames)
        self.assertEqual(bpsk.ax25_text(payload)[1], "OM2AMR-1")

    def test_ax25_9600_g3ruh(self):
        payload, frames = self.ax25(9600, 96000, True, 4100.0)
        self.assertIn(("AX.25 G3RUH", payload), frames)

    def test_no_signal(self):
        z = (RNG.normal(size=48000 * 3) + 1j * RNG.normal(size=48000 * 3)).astype(np.complex64)
        self.assertIsNone(bpsk.demod(z, 48000, 1200, -3000, 3000))


class DecoderTest(unittest.TestCase):
    def test_stream(self):
        """Two AO-40 frames fed in 0.1 s blocks: each is reported once, with the satellite name."""
        frames = [ao40_frame_bytes(), ao40_frame_bytes(ftype=5)]
        bits = []
        for d in frames:
            bits += [1] * 800 + list(fc.encode_frame(d))
        fs = 48000.0
        z = modulate(differential(bits + [1] * 1200), 1200, fs, 1600.0, esn0_db=8, lead=1.0)
        out = []
        dec = bpsk.BpskDecoder(on_decode=out.append)
        dec.set_enabled(True)
        clock = [1_800_000_000.0]
        real_time, real_mono = bpsk.time.time, bpsk.time.monotonic
        bpsk.time.time = bpsk.time.monotonic = lambda: clock[0]
        try:
            step = 4800
            for i in range(0, len(z), step):
                clock[0] += step / fs
                dec.feed(z[i:i + step], fs, 145933400.0)
                while dec._busy:
                    time.sleep(0.002)
        finally:
            bpsk.time.time, bpsk.time.monotonic = real_time, real_mono
        self.assertIsNone(dec.error)
        self.assertEqual([d["hex"] for d in out], [d.hex(" ") for d in frames])
        self.assertEqual(out[0]["sat"], "FUNcube-1 (AO-73)")
        self.assertEqual(out[0]["framing"], "AO-40")
        self.assertAlmostEqual(out[0]["freq_hz"], 145935000, delta=20)

    def test_options(self):
        dec = bpsk.BpskDecoder(on_decode=lambda d: None)
        cfg = {}
        self.assertTrue(dec.apply({"bpsk_baud": 9600, "bpsk_span": 12000, "bpsk": True}, cfg))
        self.assertEqual(cfg, {"bpsk_baud": 9600, "bpsk_span": 12000, "bpsk": True})
        dec.set_options(1234, 5)                     # not offered: unchanged
        self.assertEqual((dec.baud, dec.span), (9600, 12000))


if __name__ == "__main__":
    unittest.main()

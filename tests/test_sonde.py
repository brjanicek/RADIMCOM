"""Tests of the radiosonde decoder (sonde.py): Reed–Solomon, geodesy, the RS41 frame and the whole chain on synthetic
GFSK, no radio.

Run: python -m unittest tests.test_sonde   (from the RADIMCOM folder)
"""
import os
import random
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sonde  # noqa: E402

FIELDS = dict(lat=48.2486, lon=16.3564, alt=12345.6, vel=(5.0, -3.0, 5.2), serial="W1234567", frame=4242,
              week=2444, tow=123456000, sats=11, batt=2.8)


def gfsk(bits, baud=4800, fs=32000.0, dev=2400.0, snr_db=20.0, offset=3000.0, inverted=False, seed=1):
    """Complex baseband of Gaussian-filtered 2-FSK with a tuning offset and noise (SNR in a 12 kHz band)."""
    rnd = np.random.default_rng(seed)
    sps = fs / baud
    n = int(len(bits) * sps)
    sym = np.array(bits, np.float64) * 2 - 1
    if inverted:
        sym = -sym
    f = sym[(np.arange(n) / sps).astype(int)] * dev
    h = np.exp(-0.5 * (np.arange(-8, 9) / 2.5) ** 2)
    f = np.convolve(f, h / h.sum(), "same") + offset
    z = np.exp(2j * np.pi * np.cumsum(f) / fs)
    noise = (rnd.normal(size=n) + 1j * rnd.normal(size=n)) * np.sqrt(0.5 * fs / 12000) * 10 ** (-snr_db / 20)
    return (z + noise).astype(np.complex64)


def transmission(nframes=4, **kw):
    bits = []
    for k in range(nframes):
        f = dict(FIELDS, frame=FIELDS["frame"] + k, lat=FIELDS["lat"] + 0.001 * k, **kw)
        bits += [k & 1 for k in range(320)] + sonde.rs41_build(f) + [1, 0] * 600
    return bits


def run(z, fs=32000.0, station=None):
    out = []
    d = sonde.SondeDecoder(lambda k, m: out.append(m) if k == "sonde" else None, station=station)
    d.set_enabled(True)
    for i in range(0, len(z), 2048):
        d.feed(z[i:i + 2048], fs, 402.5e6)
    return d, out


class ReedSolomon(unittest.TestCase):
    def test_corrects_up_to_12(self):
        rnd = random.Random(5)
        data = [rnd.randrange(256) for _ in range(132)]
        cw = sonde.rs_encode(data) + data + [0] * (255 - 156)
        self.assertEqual(sonde.rs_correct(list(cw), 24, 156), 0)
        for ne in (1, 6, 12):
            c = list(cw)
            for i in rnd.sample(range(156), ne):
                c[i] ^= rnd.randrange(1, 256)
            self.assertEqual(sonde.rs_correct(c, 24, 156), ne)
            self.assertEqual(c, cw)

    def test_too_many(self):
        rnd = random.Random(6)
        data = [rnd.randrange(256) for _ in range(132)]
        cw = sonde.rs_encode(data) + data + [0] * (255 - 156)
        for i in rnd.sample(range(156), 14):
            cw[i] ^= rnd.randrange(1, 256)
        self.assertEqual(sonde.rs_correct(cw, 24, 156), -1)


class Geodesy(unittest.TestCase):
    def test_round_trip(self):
        for lat, lon, h in ((48.1, 17.1, 150.0), (-33.9, 151.2, 31000.0), (0.0, -170.0, 5.0)):
            got = sonde.ecef_to_geo(*sonde.geo_to_ecef(lat, lon, h))
            self.assertAlmostEqual(got[0], lat, places=7)
            self.assertAlmostEqual(got[1], lon, places=7)
            self.assertAlmostEqual(got[2], h, places=2)

    def test_look(self):
        dist, az, el = sonde.look((48.1, 17.1), 48.2486, 16.3564, 20000.0)
        self.assertAlmostEqual(dist, 62.5, delta=2.0)    # Wien Hohe Warte from Bratislava, 20 km up
        self.assertAlmostEqual(az, 287, delta=3)
        self.assertGreater(el, 15)


class Frame(unittest.TestCase):
    def test_header_and_parse(self):
        self.assertEqual(sonde.RS41_HDR_BYTES.hex(), "10b6ca11229612f8")
        frames = sonde.Rs41Framer().feed([0, 1] * 40 + sonde.rs41_build(FIELDS) + [0] * 50)
        self.assertEqual(len(frames), 1)
        f = frames[0]
        self.assertEqual(bytes(f[:8]).hex(), "8635f44093df1a60")      # descrambled header
        self.assertEqual(sonde.rs41_ecc(f), 0)
        d = sonde.rs41_parse(f)
        self.assertEqual((d["serial"], d["frame"], d["sats"], d["batt"]), ("W1234567", 4242, 11, 2.8))
        self.assertAlmostEqual(d["lat"], FIELDS["lat"], places=5)
        self.assertAlmostEqual(d["lon"], FIELDS["lon"], places=5)
        self.assertAlmostEqual(d["alt"], FIELDS["alt"], delta=0.1)
        self.assertAlmostEqual(d["vv"], 5.2, delta=0.05)
        self.assertAlmostEqual(d["vh"], 5.83, delta=0.05)
        self.assertAlmostEqual(d["dir"], 121.0, delta=1.0)
        self.assertEqual(d["blocks_bad"], 0)

    def test_byte_errors_corrected(self):
        bits = sonde.rs41_build(FIELDS)
        rnd = random.Random(3)
        for i in rnd.sample(range(64, len(bits)), 15):
            bits[i] ^= 1
        f = sonde.Rs41Framer().feed(bits)[0]
        self.assertGreater(sonde.rs41_ecc(f), 0)
        self.assertEqual(sonde.rs41_parse(f)["blocks_bad"], 0)

    def test_extended_frame(self):
        f = sonde.Rs41Framer().feed(sonde.rs41_build(FIELDS, extended=True))[0]
        self.assertEqual(len(f), sonde.RS41_EXT)
        self.assertEqual(sonde.rs41_ecc(f), 0)
        self.assertEqual(sonde.rs41_parse(f)["serial"], "W1234567")


class Chain(unittest.TestCase):
    def test_clean(self):
        d, out = run(gfsk(transmission()), station=lambda: (48.1, 17.1))
        self.assertEqual([m["frame"] for m in out], [4242, 4243, 4244, 4245])
        s = d.info()["sondes"][0]
        self.assertEqual(s["serial"], "W1234567")
        self.assertEqual(len(s["pts"]), 1)          # all frames within TRACK_SEC of each other
        self.assertIn("dist", s)
        self.assertAlmostEqual(d.info()["offset_hz"], 3000, delta=300)

    def test_inverted_noisy_37k5(self):
        fs = 2.4e6 / 64
        _, out = run(gfsk(transmission(), fs=fs, snr_db=11, inverted=True, offset=-2000), fs=fs)
        self.assertGreaterEqual(len(out), 3)
        self.assertTrue(all(m["inverted"] for m in out))

    def test_dfm(self):
        def second(lat, fr):
            m = lambda a, b: ((a & 0xFFFFFFFF) << 16) | (b & 0xFFFF)      # noqa: E731
            vals = {0: fr << 16, 2: m(int(lat * 1e7), 750), 3: m(int(17.35 * 1e7), 12340), 4: m(234560, -420)}
            sym = []
            for k in range(0, 16, 2):
                sym += sonde.dfm_build([(k, vals.get(k, 0)), (k + 1, vals.get(k + 1, 0))])
            return sym
        sym = [0, 1] * 200
        for i in range(3):
            sym += second(48.62 + 0.001 * i, i)
        _, out = run(gfsk(sym + [0, 1] * 200, baud=2500, dev=3500, snr_db=15, offset=-1500))
        self.assertEqual([m["frame"] for m in out], [0, 1, 2])
        m = out[-1]
        self.assertEqual((m["type"], m["serial"], m["lon"], m["alt"], m["vv"], m["dir"], m["vh"]),
                         ("DFM", "DFM-402.500", 17.35, 2345.6, -4.2, 123.4, 7.5))
        self.assertAlmostEqual(m["lat"], 48.622, places=6)

    def test_noise_only(self):
        rnd = np.random.default_rng(9)
        z = (rnd.normal(size=320000) + 1j * rnd.normal(size=320000)).astype(np.complex64)
        _, out = run(z)
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()

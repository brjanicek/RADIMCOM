"""Tests of the radiosonde decoder (sonde.py): Reed–Solomon, geodesy, the RS41 frame and the whole chain on synthetic
GFSK, no radio.

Run: python -m unittest tests.test_sonde   (from the RADIMCOM folder)
"""
import json
import os
import random
import sys
import time
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

    def test_m20(self):
        # real frame of M20 507-2-02967 (raw serial bytes C2 5C 2E; 2026-11-15, 403.5 MHz): the checksum and the fields
        real = bytes.fromhex("452062232126ab0e10f47a0357031b00aa5bc25c2e484100019d098d02e3093000fc6b64b10dc0f6"
                             "001d000002fe05b245d208654972243bada542f500320020000a0a07841b")
        m = sonde.m20_parse(real)
        self.assertEqual((m["type"], m["serial"], m["alt"], m["lat"], m["lon"]),
                         ("M20", "M20-507-2-02967", 11111.6, 48.433456, 16.542564))
        self.assertEqual((m["vv"], m["batt"]), (4.13, 2.48))
        self.assertIsNone(sonde.m20_parse(real[:10] + b"\x00" + real[11:]))       # a wrong byte: checksum
        # synthetic frames through the whole chain (64 kHz: the Gaussian filter of gfsk() is a fixed number of samples,
        # at 32 kHz it would smear the 3.3 samples of a symbol; the real M20 above decodes at 32 kHz)
        f = dict(alt=12345.67, ve=10.0, vn=-5.0, tow=43611, week=2445, lat=48.62, lon=17.35)
        sym = [0, 1] * 300
        for i in range(3):
            sym += sonde.m20_build(dict(f, frame=i, alt=f["alt"] + 5 * i, tow=f["tow"] + i, vu=5.0)) + [0, 1] * 4000
        d, out = run(gfsk(sym, baud=9600, fs=64000.0, dev=4800, snr_db=20, offset=1000), fs=64000.0)
        self.assertEqual([m["frame"] for m in out], [0, 1, 2])
        m = out[-1]
        self.assertEqual((m["serial"], m["alt"], m["lat"], m["lon"], m["vh"], m["dir"]),
                         ("M20-507-2-02967", 12355.7, 48.62, 17.35, 11.18, 116.6))
        self.assertEqual(m["vv"], 5.0)

    def test_m10(self):
        f = dict(ve=3.0, vn=4.0, vu=-6.5, tow_ms=43611000, week=2445, lat=48.62, lon=17.35, alt=8765.432, sats=8)
        self.assertEqual(sonde.m10_serial(bytes((0x01, 0x00, 0x85, 0x2A, 0x41))), "805-1-20298")
        sym = [0, 1] * 300
        for i in range(3):
            sym += sonde.m10_build(dict(f, frame=i, tow_ms=f["tow_ms"] + 1000 * i)) + [0, 1] * 4000
        _, out = run(gfsk(sym, baud=9615, fs=64000.0, dev=4800, snr_db=20, offset=-800), fs=64000.0)
        self.assertEqual([m["frame"] for m in out], [0, 1, 2])
        m = out[-1]
        self.assertEqual((m["type"], m["serial"], m["alt"], m["vv"], m["vh"], m["dir"], m["sats"]),
                         ("M10", "M10-805-1-20298", 8765.4, -6.5, 5.0, 36.9, 8))
        self.assertAlmostEqual(m["lat"], 48.62, places=5)
        self.assertAlmostEqual(m["lon"], 17.35, places=5)
        self.assertEqual(time.strftime("%H:%M:%S", time.gmtime(m["gps_time"])), "12:06:35")

    def test_dfm_serial_type_temp(self):
        def halves(cs, ch, sn, mark=0xC):
            for hl, half in ((0, sn >> 16), (1, sn & 0xFFFF)):
                sonde.dfm_conf(cs, [ch, mark] + [(half >> s) & 15 for s in (12, 8, 4, 0)] + [hl])

        def put(cs, ch, val, p=4):
            v = int(val * 2 ** p)
            sonde.dfm_conf(cs, [ch] + [((p << 20 | v) >> s) & 15 for s in (20, 16, 12, 8, 4, 0)])

        cs, sn = {}, 23038743
        halves(cs, 0xB, sn)
        self.assertEqual(sonde.dfm_info(cs)["serial"], "")          # once: not yet
        halves(cs, 0xB, sn)                                          # twice the same: believed
        self.assertEqual((sonde.dfm_info(cs)["serial"], sonde.dfm_info(cs)["subtype"]), ("23038743", "DFM17"))
        # measurements 0-8: R = (f - f1) / (f2 / Rf) = 10000 / (33200 / 332 kΩ) = 100 kΩ -> -39.2 °C
        for ch, val in ((0, 40000.0), (1, 1000.0), (2, 1000.0), (3, 30000.0), (4, 33200.0), (5, 1000.0),
                        (6, 300000.0), (7, 1000.0), (8, 1000.0)):
            put(cs, ch, val)
        self.assertAlmostEqual(sonde.dfm_info(cs)["temp"], -39.2, delta=0.1)
        # DFM-06: null channel 0x5A, the serial (hex) in the channel after it, twice
        d6 = {}
        for _ in range(2):
            sonde.dfm_conf(d6, [5, 0xA, 0, 0, 0, 0, 0])
            sonde.dfm_conf(d6, [6, 6, 1, 2, 3, 4, 5])
        self.assertEqual((sonde.dfm_info(d6)["serial"], sonde.dfm_info(d6)["subtype"]), ("612345", "DFM06"))
        # PS-15: null channel 0x60, the halves in channel 7 with the nibble 0
        ps = {}
        for _ in range(2):
            sonde.dfm_conf(ps, [6, 0, 0, 0, 0, 0, 0])
            halves(ps, 7, 12345678, mark=0)
        self.assertEqual((sonde.dfm_info(ps)["serial"], sonde.dfm_info(ps)["subtype"]), ("12345678", "PS15"))

    def test_mm_ptu(self):
        # the real M20 frame at 11.1 km: -58.3 °C, 219 hPa (standard atmosphere at 11.1 km: 220 hPa)
        real = bytes.fromhex("452062232126ab0e10f47a0357031b00aa5bc25c2e484100019d098d02e3093000fc6b64b10dc0f6"
                             "001d000002fe05b245d208654972243bada542f500320020000a0a07841b")
        m = sonde.m20_parse(real)
        self.assertEqual((m["temp"], m["temp_h"], m["rh"], m["pres"]), (-58.3, -57.8, 27.9, 219.1))
        # M10: range 1, ADC 2000 -> R = 36.5k / (2095/2000 - 36.5/330) = 38.96 kΩ -> -20.2 °C (table of rs1729: -20 °C = 38.48 kΩ)
        f = bytearray(sonde.M10_LEN)
        f[0x3E] = 1
        f[0x3F:0x41] = (0xA000 + 2000).to_bytes(2, "little")
        f[0x32:0x35] = (1000000).to_bytes(3, "little")
        f[0x35:0x38] = (995500).to_bytes(3, "little")
        p = sonde.m10_ptu(f)
        self.assertAlmostEqual(p["temp"], -20.2, delta=0.1)
        self.assertAlmostEqual(p["rh"], (0.9955 - 0.8955) / 0.002 + 20.2 / 5.5, delta=0.2)

    def test_noise_only(self):
        rnd = np.random.default_rng(9)
        z = (rnd.normal(size=320000) + 1j * rnd.normal(size=320000)).astype(np.complex64)
        _, out = run(z)
        self.assertEqual(out, [])


def calibration():
    """816 calibration bytes: reference resistors 750 / 1100 Ω, Pt1000-like polynomial, type RS41-SG."""
    import struct
    cal = bytearray(sonde.CAL_FRAGS * sonde.CAL_LEN)
    put = lambda pos, *v: cal.__setitem__(slice(pos, pos + 4 * len(v)), struct.pack(f"<{len(v)}f", *v))
    put(0x3D, 750.0, 1100.0)
    put(0x4D, -243.911, 0.187654, 8.2e-06)
    put(0x59, 1.0, 0.0, 0.0)
    put(0x75, 47.5, 50.0)
    put(0x125, -243.911, 0.187654, 8.2e-06)
    put(0x131, 1.0, 0.0, 0.0)
    cal[0x218:0x220] = b"RS41-SG\0"
    return cal


class Multi(unittest.TestCase):
    """MULTI: two sondes in one dongle band (2.048 MS/s), each found and decoded in its own channel."""

    def test_two_sondes(self):
        import time
        fs, center = 2.048e6, 403.0e6
        rs = gfsk(transmission(3), fs=fs, snr_db=40, offset=300e3, seed=2)
        f = dict(alt=12345.67, ve=10.0, vn=-5.0, tow=43611, week=2445, lat=48.62, lon=17.35)
        sym = [0, 1] * 3000
        for i in range(3):
            sym += sonde.m20_build(dict(f, frame=i, tow=f["tow"] + i)) + [0, 1] * 4000
        m20 = gfsk(sym, baud=9600, fs=fs, dev=4800, snr_db=40, offset=-500e3, seed=3)
        n = min(len(rs), len(m20))
        z = rs[:n] + m20[:n]
        out = []
        d = sonde.SondeDecoder(lambda k, m: out.append(m) if k == "sonde" else None)
        d.set_enabled(True)
        d.tune_hz = 401.0e6                  # the VFO is elsewhere
        t0 = time.time()
        for i in range(0, n, 131072):
            d._wide_block(z[i:i + 131072], fs, center, (center - 1e6, center + 1e6), now=t0 + i / fs)
        json.dumps(d.info())                 # what /api/sonde sends (numpy numbers would fail)
        ch = {round(c["hz"] / 1e3): c for c in d.info()["channels"]}
        self.assertEqual(sorted(ch), [402500, 403300])
        types = {(m["type"], round(m["freq_hz"] / 1e3)) for m in out}
        self.assertEqual(types, {("RS41", 403300), ("M20", 402500)})
        self.assertEqual(ch[403300]["serial"], "W1234567")
        # the VFO tuned onto one of them: that channel is left to the VFO (no double frames)
        d.tune_hz = 403.3e6
        before = len(out)
        for i in range(0, n, 131072):
            d._wide_block(z[i:i + 131072], fs, center, (center - 1e6, center + 1e6), now=t0 + 10 + i / fs)
        self.assertTrue(all(m["type"] == "M20" for m in out[before:]))


def frame_bytes(bits):
    """Bits of rs41_build -> the descrambled frame, as the framer gives it."""
    raw = bytes(sum(bits[i * 8 + k] << k for k in range(8)) for i in range(len(bits) // 8))
    return bytearray(b ^ sonde.RS41_MASK[i % 64] for i, b in enumerate(raw))


class Position(unittest.TestCase):
    """Bad GPS fixes after the burst (seen on X1453430) are dropped, the rest of the frame stays."""

    def test_filter(self):
        sondes, t = {}, 1000.0
        def add(**k):
            nonlocal t
            t += 1
            d = dict(type="RS41", serial="X1", temp=-60.0, **k)
            sonde._sonde_add(sondes, "X1", d, t)
            return d
        add(lat=49.8, lon=19.5, alt=12000.0, vv=-40.0, vh=20.0, dir=90.0, sats=8)
        self.assertIn("no GPS", add(lat=49.8, lon=19.5, alt=11960.0, vv=-40.0, vh=20.0, dir=90.0, sats=0)["pos_bad"])
        self.assertIn("falling", add(lat=49.8, lon=19.5, alt=3000.0, vv=-200.0, vh=60.0, dir=90.0, sats=4)["pos_bad"])
        self.assertIn("altitude", add(lat=49.8, lon=19.5, alt=-590.0, vv=-10.0, vh=0.0, dir=0.0, sats=5)["pos_bad"])
        self.assertIn("jump", add(lat=49.05, lon=21.36, alt=12000.0, vv=-5.0, vh=0.0, dir=0.0, sats=6)["pos_bad"])
        ok = add(lat=49.801, lon=19.501, alt=11800.0, vv=-40.0, vh=20.0, dir=90.0, sats=6)
        self.assertNotIn("pos_bad", ok)
        s = sondes["X1"]
        self.assertEqual((s["alt"], s["temp"], s["n"]), (11800.0, -60.0, 6))
        self.assertEqual(len(s["pts"]), 2)


class Telemetry(unittest.TestCase):
    R_T, R_TH = 1100.0, 1000.0           # sensor resistances, Ω

    def meas(self):
        g, rb = 100.0, 20.0               # gain and offset of the measuring circuit
        f = lambda r: g * (r + rb)
        # humidity: (f - f1) / (f2 - f1) = 1.05
        return [f(self.R_T), f(750), f(1100), 110500, 100000, 110000, f(self.R_TH), f(750), f(1100), 0, 0, 0]

    def expect(self, r):
        return -243.911 + 0.187654 * r + 8.2e-06 * r * r

    def test_ptu(self):
        cal = calibration()
        have = set(range(sonde.CAL_FRAGS))
        p = sonde.rs41_ptu(cal, have, self.meas())
        self.assertAlmostEqual(p["temp"], self.expect(self.R_T), delta=0.06)
        self.assertAlmostEqual(p["temp_h"], self.expect(self.R_TH), delta=0.06)
        rh = 100 * (350 / 47.5 * 1.05 - 7.5) - p["temp"] / 5.5
        rh *= 1 + (-25 - p["temp"]) / 90 if p["temp"] < -25 else 1
        self.assertAlmostEqual(p["rh"], rh, delta=0.2)
        self.assertEqual(sonde.rs41_subtype(cal, have), "RS41-SG")
        self.assertEqual(sonde.rs41_ptu(cal, have - {5}, self.meas()).get("temp"), None)

    def test_decoder_collects_calibration(self):
        cal = calibration()
        out = []
        d = sonde.SondeDecoder(lambda k, m: None)
        for i in range(sonde.CAL_FRAGS):
            piece = (i, bytes(cal[i * 16:(i + 1) * 16]))
            out.append(d._frame(frame_bytes(sonde.rs41_build(dict(FIELDS, frame=i, cal=piece, meas=self.meas()))), False, 1.0 + i))
        self.assertNotIn("temp", out[2])
        self.assertIn("temp", out[6])
        last = out[-1]
        self.assertEqual(last["cal_n"], 51)
        self.assertEqual(last["subtype"], "RS41-SG")
        self.assertAlmostEqual(last["temp"], self.expect(self.R_T), delta=0.06)
        self.assertIn("rh", last)
        s = d.info()["sondes"][0]
        self.assertEqual(s["temp"], last["temp"])
        self.assertNotIn("_cal", last)


class Log(unittest.TestCase):
    def test_log_restore_and_read(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = sonde.SondeDecoder(lambda k, m: None, log_dir=tmp, tag="D")
            for i in range(5):
                f = dict(FIELDS, frame=i, alt=1000.0 + 50 * i)
                d._frame(frame_bytes(sonde.rs41_build(f)), False, 1000.0 + 3 * i)
            with open(os.path.join(tmp, os.listdir(tmp)[0]), "a") as fh:
                fh.write("broken line\n")
            # other VFO: nothing of D; same VFO: the sonde with its path
            self.assertEqual(sonde.SondeDecoder(lambda k, m: None, log_dir=tmp, tag="A").sondes, {})
            os.utime(os.path.join(tmp, os.listdir(tmp)[0]))
            r = sonde.SondeDecoder(lambda k, m: None, log_dir=tmp, tag="D")
            s = r.sondes["W1234567"]
            self.assertEqual(s["n"], 5)
            self.assertEqual(len(s["pts"]), 5)
            self.assertEqual(s["max_alt"], d.sondes["W1234567"]["max_alt"])
            self.assertTrue(s["from_log"])
            logs = r.logs()
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["serial"], "W1234567")
            self.assertEqual(r.log_sonde(logs[0]["file"])["n"], 5)
            self.assertIsNone(r.log_sonde("../x.jsonl"))
            # a new frame of a restored sonde goes on in the same file
            r._frame(frame_bytes(sonde.rs41_build(dict(FIELDS, frame=9))), False, 2000.0)
            self.assertEqual(len(os.listdir(tmp)), 1)
            self.assertNotIn("from_log", r.sondes["W1234567"])


if __name__ == "__main__":
    unittest.main()

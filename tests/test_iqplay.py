"""iqplay.py: what an IQ file is (WAV of REC IQ, PortaPack .C16 + .TXT, SigMF, names), the rate plan and the player."""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import iqplay  # noqa: E402
from iqrec import IqRecorder  # noqa: E402


def tone(fs, n, f_off, amp=0.5):
    t = np.arange(n) / fs
    return (amp * np.exp(2j * np.pi * f_off * t)).astype(np.complex64)


def peak_hz(x, fs):
    spec = np.abs(np.fft.fftshift(np.fft.fft(x[:65536])))
    return (np.argmax(spec) - len(spec) / 2) * fs / len(spec)


def run_player(p, blocks=3, timeout=10.0):
    """Collects blocks of the player (as the receiver does) until it has enough."""
    got = []
    p.reset_buffer()

    def on_block(b):
        got.append(b)
        if len(got) >= blocks:
            p.cancel_async()

    th = threading.Thread(target=p.read_async, args=(on_block,), daemon=True)
    th.start()
    th.join(timeout)
    p.cancel_async()
    return got


class Names(unittest.TestCase):
    def test_sdrsharp(self):
        c, r, _ = iqplay.from_name("RADIMCOM_A_20261124_101500Z_145800000Hz_IQ.wav")
        self.assertEqual(c, 145800000)
        self.assertIsNone(r)

    def test_rtl433(self):
        c, r, _ = iqplay.from_name("g001_433.92M_250k.cu8")
        self.assertEqual((c, r), (433.92e6, 250e3))

    def test_units(self):
        c, r, _ = iqplay.from_name("capture_7.1MHz_2.4Msps.cs8")
        self.assertEqual((c, r), (7.1e6, 2.4e6))

    def test_gqrx(self):
        self.assertEqual(iqplay.from_name("gqrx_20261124_120000_145800000_2400000_fc.raw"), (145800000.0, 2400000.0, "f32"))


class RatePlan(unittest.TestCase):
    def test_plan(self):
        self.assertEqual(iqplay.rate_plan(2.4e6), (1, 1))
        self.assertEqual(iqplay.rate_plan(20e6), (8, 1))
        self.assertEqual(iqplay.rate_plan(10e6), (4, 1))
        self.assertEqual(iqplay.rate_plan(500e3), (1, 2))
        self.assertEqual(iqplay.rate_plan(250e3), (1, 4))


class Files(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_our_wav_u8(self):
        """REC IQ of an RTL dongle (8 bit) is found and played with its tone where it was."""
        fs, centre = 2048000.0, 145800000.0
        rec = IqRecorder(lambda: self.dir, "A")
        rec.set(True)
        x = tone(fs, 131072 * 4, 200e3)
        raw = np.empty(len(x) * 2, np.uint8)
        raw[0::2] = np.clip(np.rint(x.real * 127.5 + 127.5), 0, 255)
        raw[1::2] = np.clip(np.rint(x.imag * 127.5 + 127.5), 0, 255)
        for k in range(4):
            rec.feed(raw[k * 262144:(k + 1) * 262144], fs, centre)
        time.sleep(0.5)
        rec.stop()
        path = os.path.join(self.dir, rec.file)
        info = iqplay.probe(path)
        self.assertTrue(info["ready"])
        self.assertEqual((info["fmt"], info["fs"], info["centre"]), ("u8", fs, centre))
        self.assertAlmostEqual(info["secs"], 4 * 131072 / fs, places=1)
        p = iqplay.IqFilePlayer(info)
        got = run_player(p, 2)
        meta, y = got[0]
        self.assertEqual(meta["center_hz"], centre)
        self.assertEqual(y.dtype, np.complex64)
        self.assertAlmostEqual(peak_hz(y, p.fs), 200e3, delta=200)

    def test_portapack_c16(self):
        """PortaPack CAPTURE: .C16 with 8 bit values in 16 bits + .TXT; 500 kS/s is upsampled to 1 MS/s."""
        fs, centre = 500000.0, 433920000.0
        x = tone(fs, 200000, 50e3, amp=100 / 128)
        iq = np.empty(len(x) * 2, "<i2")
        iq[0::2], iq[1::2] = np.rint(x.real * 128), np.rint(x.imag * 128)
        path = os.path.join(self.dir, "CAPT_0001.C16")
        iq.tofile(path)
        with open(os.path.join(self.dir, "CAPT_0001.TXT"), "w") as f:
            f.write(f"sample_rate={int(fs)}\ncenter_frequency={int(centre)}\n")
        info = iqplay.probe(path)
        self.assertEqual((info["fmt"], info["fs"], info["centre"]), ("s16", fs, centre))
        p = iqplay.IqFilePlayer(info)
        self.assertEqual((p.up, p.fs), (2, 1e6))
        self.assertAlmostEqual(p.scale, 1 / 128)
        got = run_player(p, 2)
        y = np.concatenate([b[1] for b in got])
        self.assertAlmostEqual(peak_hz(y[1000:], p.fs), 50e3, delta=100)
        self.assertGreater(np.abs(y[2000:]).mean(), 0.5)        # level kept through the upsampling

    def test_sigmf_and_down(self):
        """SigMF cs8 at 10 MS/s: divided by 4, a tone 300 kHz off the centre stays there."""
        fs, centre = 10e6, 100e6
        x = tone(fs, 131072 * 8, 300e3)
        iq = np.empty(len(x) * 2, np.int8)
        iq[0::2], iq[1::2] = np.rint(x.real * 127), np.rint(x.imag * 127)
        iq.tofile(os.path.join(self.dir, "rec.sigmf-data"))
        with open(os.path.join(self.dir, "rec.sigmf-meta"), "w") as f:
            json.dump({"global": {"core:datatype": "ci8", "core:sample_rate": fs},
                       "captures": [{"core:sample_start": 0, "core:frequency": centre}]}, f)
        info = iqplay.probe(os.path.join(self.dir, "rec.sigmf-meta"))
        self.assertEqual((info["fmt"], info["fs"], info["centre"]), ("s8", fs, centre))
        p = iqplay.IqFilePlayer(info)
        self.assertEqual((p.down, p.fs), (4, 2.5e6))
        got = run_player(p, 2)
        y = np.concatenate([b[1] for b in got])
        self.assertEqual(len(got[0][1]), iqplay.BLOCK)
        self.assertAlmostEqual(peak_hz(y[1000:], p.fs), 300e3, delta=200)

    def test_unknown_needs_input(self):
        path = os.path.join(self.dir, "noname.cu8")
        np.zeros(1000, np.uint8).tofile(path)
        info = iqplay.probe(path)
        self.assertFalse(info["ready"])
        with self.assertRaises(ValueError):
            iqplay.IqFilePlayer(info)

    def test_pause_seek_end(self):
        fs = 1e6
        path = os.path.join(self.dir, "x_100MHz_1Msps.cf32")
        tone(fs, 300000, 10e3).tofile(path)
        p = iqplay.IqFilePlayer(iqplay.probe(path))
        self.assertAlmostEqual(p.total / fs, 0.3)
        got = run_player(p, 10, timeout=3)            # 0.3 s = 3 blocks, then it holds at the end
        self.assertEqual(len(got), 3)
        self.assertTrue(p.ended)
        p.control(seek=0.2)
        self.assertFalse(p.ended)
        got = run_player(p, 5, timeout=1)
        self.assertEqual(len(got), 1)                 # the last 0.1 s played again, then the end
        self.assertTrue(p.ended)
        p.control(pause=False)                        # PLAY at the end: from the start
        self.assertEqual(p.seek_to, 0)


class BackToVfo(unittest.TestCase):
    """START keeps the whole setting, STOP puts the dongle state back in the receiver and the rest through /api/set."""

    def test_restore(self):
        from flask import Flask, jsonify, request

        class FakeRx:
            def __init__(self):
                self.cfg = {"tune_hz": 7.1e6, "center_hz": 7.3e6, "sample_rate": 2048000, "mode": "USB", "gain": 20,
                            "ft8": True, "cw": False, "nb": True, "bandwidth": {"USB": 2700}, "device": 0}
                self.player = self.iq_saved = self.iq_snapshot = None
                self.pending = []

                class W:
                    def set(self):
                        pass
                self._wake = W()

            def update(self, ch):
                if ch.get("iq_stop"):            # what the receiver thread does
                    self.player = None
                    self.cfg.update(self.iq_saved)
                else:
                    self.cfg.update({k: v for k, v in ch.items() if k != "reset"})

        rx, calls = FakeRx(), []
        app = Flask(__name__)

        @app.route("/api/set", methods=["POST"])
        def api_set():
            body = request.get_json(force=True)
            calls.append(body)
            rx.cfg.update(body)
            if body.get("cw") is True:
                rx.cfg["ft8"] = False
            return jsonify({})

        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, "x_145.8MHz_1Msps.cf32")
            tone(1e6, 1000, 1e3).tofile(path)
            iqplay.register(app, rx, None, lambda: None)
            c = app.test_client()
            self.assertEqual(c.post("/api/iqplay/start", json={"path": path}).status_code, 200)
            self.assertEqual(rx.cfg["tune_hz"], 145.8e6)
            # meanwhile: the file's block state and a few settings changed from the page
            rx.cfg.update(center_hz=145.8e6, sample_rate=1000000, gain=0, mode="FM", ft8=False, cw=True, nb=False)
            rx.cfg["bandwidth"]["USB"] = 500
            self.assertEqual(iqplay.saved_cfg(rx.cfg, rx)["mode"], "USB")      # saved meanwhile: as before
            j = c.post("/api/iqplay/stop").get_json()
            self.assertIsNone(rx.player)
            self.assertEqual({k: rx.cfg[k] for k in ("tune_hz", "center_hz", "sample_rate", "gain", "mode", "ft8", "cw", "nb")},
                             {"tune_hz": 7.1e6, "center_hz": 7.3e6, "sample_rate": 2048000, "gain": 20, "mode": "USB",
                              "ft8": True, "cw": False, "nb": True})
            self.assertEqual(rx.cfg["bandwidth"], {"USB": 2700})
            self.assertEqual(sorted(j["restored"]), ["cw", "ft8", "mode", "nb"])
            # the decoder switched off before the one switched on (switching one on switches the others off)
            self.assertLess(calls.index({"cw": False}), calls.index({"ft8": True}))
            self.assertIsNone(rx.iq_snapshot)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

"""meteor_rec.py: GRAVES echoes into the recordings folder (MP3, IQ of the echo, IQ of the whole band)."""
import io
import os
import shutil
import sys
import tempfile
import time
import unittest
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meteor_audio  # noqa: E402
import meteor_rec  # noqa: E402
import recorder  # noqa: E402
from retro import RetroBuffer  # noqa: E402


def wav8k(secs=1.0):
    t = np.arange(int(8000 * secs)) / 8000
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes((0.5 * np.sin(2 * np.pi * 1000 * t) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


class FakeCounter:
    def __init__(self, now):
        fs = 1024000.0
        self._dial = 143049000.0
        self._aud = meteor_audio.Ring(fs, 1000.0)
        n = int(fs * 4)
        k = np.arange(n)
        self._aud.feed((0.1 * np.exp(2j * np.pi * (1000.0 + 30.0) * k / fs)).astype(np.complex64), now)
        self.wav = wav8k()

    def audio(self, ts):
        return self.wav


class MeteorRecTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.cfgdir = tempfile.mkdtemp()
        self.now = time.time()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.cfgdir, ignore_errors=True)

    def make(self, retro=None):
        r = meteor_rec.MeteorRec(FakeCounter(self.now), lambda: self.root, retro, "C", "C")
        r.path = os.path.join(self.cfgdir, "rec.json")
        return r

    def test_all_three(self):
        retro = RetroBuffer("C")
        retro.set(on=True, seconds=30)
        raw = np.full(262144, 128, np.uint8)
        for k in range(16):
            retro.blocks.append((self.now - 3.5 + k * 0.25, raw, 1024000.0, 143e6, "u8"))
            retro.samples += 131072
        rec = self.make(retro)
        e = {"ts": self.now - 2.5, "dur": 0.4, "kind": "under", "freq_hz": 143050030}
        files = rec.save_now(e)
        self.assertEqual(len(files), 3)
        mp3, iq, band = files
        self.assertTrue(mp3.endswith("_GRAVES.mp3"))
        info = recorder.parse_name(os.path.basename(mp3))
        self.assertEqual((info["src"], info["memory"], info["mode"], info["hz"]), ("graves", "METEOR", "USB", 143050030))
        self.assertTrue(iq.endswith("Hz_IQ_GRAVES.wav") and "/iq/" in iq)
        i = recorder.parse_name(os.path.basename(iq))
        self.assertEqual((i["src"], i["memory"], i["hz"]), ("iq", "GRAVES echo", 143050000))
        with wave.open(os.path.join(self.root, iq)) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth()), (2, 2))
            self.assertAlmostEqual(w.getnframes() / w.getframerate(), 2.4, delta=0.1)
        b = recorder.parse_name(os.path.basename(band))
        self.assertEqual((b["memory"], b["hz"]), ("GRAVES band", 143000000))
        with wave.open(os.path.join(self.root, band)) as w:
            self.assertEqual(w.getsampwidth(), 1)                       # the RTL bytes as they were
        # RECORDINGS lists them with their length
        rec_ = recorder.Recorder(self.root)
        day = os.path.dirname(mp3)
        lst = rec_.list_dir(day)
        f = lst["files"][0]
        self.assertEqual(f["src"], "graves")

    def test_kinds_and_off(self):
        rec = self.make()
        e = {"ts": self.now - 2.5, "dur": 0.4, "kind": "plane", "freq_hz": 143050000}
        rec.echo(e)
        self.assertTrue(rec.q.empty())                                  # REC off
        rec.set({"on": True, "kinds": ["met"]})
        rec.echo(e)
        self.assertTrue(rec.q.empty())                                  # aircraft not chosen
        rec.echo(dict(e, kind="over"))
        deadline = time.time() + 5
        while rec.saved == 0 and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(rec.saved, 1)
        self.assertTrue(rec.last.startswith("METEOR_LONG_"))

    def test_prerec_name(self):
        """PRE-REC SAVE files are recognised too (they were shown as foreign files)."""
        i = recorder.parse_name("RADIMCOM_A_20261124_101500Z_145800000Hz_IQ_PREREC.wav")
        self.assertEqual((i["src"], i["memory"]), ("iq", "PRE-REC"))


if __name__ == "__main__":
    unittest.main()

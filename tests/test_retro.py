"""retro.py: the RAM ring of raw IQ, a replay of a past moment demodulated like live (USB tone), the trim to the set
length, both sample formats and SAVE as an IQ WAV.

Run: python -m unittest tests.test_retro
"""
import io
import os
import sys
import tempfile
import time
import unittest
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import retro  # noqa: E402
import sdr  # noqa: E402

FS = 1024000.0
CENTER = 14100000.0


def rtl_block(n, tone_hz, k0):
    """RTL-style uint8 interleaved I/Q with a carrier tone_hz above the centre."""
    t = (np.arange(n) + k0) / FS
    z = 0.5 * np.exp(2j * np.pi * tone_hz * t)
    iq = np.empty(2 * n, np.float32)
    iq[0::2], iq[1::2] = z.real, z.imag
    return np.clip(np.round(iq * 127.5 + 127.5), 0, 255).astype(np.uint8)


class Retro(unittest.TestCase):
    def fill(self, buf, seconds, tone_hz, t_start):
        n = sdr.READ_SAMPLES
        k = 0
        blocks = int(seconds * FS / n)
        for b in range(blocks):
            buf.feed(rtl_block(n, tone_hz, k), FS, CENTER)
            buf.blocks[-1] = (t_start + (k + n) / FS,) + buf.blocks[-1][1:]     # the arrival time as if in real time
            k += n

    def test_replay_finds_the_tone(self):
        buf = retro.RetroBuffer("A")
        buf.set(on=True, seconds=30)
        t0 = time.time() - 10
        self.fill(buf, 8, 101000.0, t0)                  # a carrier at 14.201 MHz
        wav, info = buf.clip_wav(t0 + 2.0, CENTER + 100000.0, {"mode": "USB", "bandwidth": {"USB": 2700}}, seconds=3)
        self.assertIsNotNone(wav, info)
        self.assertAlmostEqual(info["start"], t0 + 2.0, delta=0.01)
        with wave.open(io.BytesIO(wav)) as w:
            fs = w.getframerate()
            a = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float)
        self.assertGreater(len(a), 2 * fs)
        spec = np.abs(np.fft.rfft(a[fs:] * np.hanning(len(a) - fs)))
        f = np.argmax(spec) * fs / (len(a) - fs)
        self.assertAlmostEqual(f, 1000.0, delta=5)       # the carrier 1 kHz above the dial in USB

    def test_trim_and_state(self):
        buf = retro.RetroBuffer("A")
        buf.set(on=True, seconds=10)
        self.fill(buf, 14, 5000.0, time.time() - 14)
        st = buf.state()
        self.assertLessEqual(st["held_s"], 10.0)
        self.assertGreater(st["held_s"], 9.5)
        buf.set(on=False)
        self.assertEqual(buf.state()["held_s"], 0)

    def test_audio_chain_of_the_vfo(self):
        """The AUDIO keys of the VFO act on the replay: LPF cuts the tone, BIN makes it stereo."""
        buf = retro.RetroBuffer("A")
        buf.set(on=True, seconds=30)
        t0 = time.time() - 10
        self.fill(buf, 6, 102500.0, t0)                  # 2.5 kHz above the dial
        base = {"mode": "USB", "bandwidth": {"USB": 2700}}

        def level(cfg):
            wav, info = buf.clip_wav(t0 + 1.0, CENTER + 100000.0, cfg, seconds=3)
            self.assertIsNotNone(wav, info)
            with wave.open(io.BytesIO(wav)) as w:
                ch = w.getnchannels()
                a = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float)
            return ch, float(np.sqrt(np.mean(a[len(a) // 2:] ** 2)))

        ch0, plain = level(dict(base, audio_agc=False))
        _, cut = level(dict(base, audio_agc=False, lpf=True, lpf_hz=1000))
        self.assertEqual(ch0, 1)
        self.assertLess(cut, plain * 0.1)
        ch2, _ = level(dict(base, bin=True))
        self.assertEqual(ch2, 2)

    def test_complex_blocks_and_errors(self):
        buf = retro.RetroBuffer("A")
        buf.set(on=True, seconds=10)
        z = (0.3 * np.exp(2j * np.pi * 2000 * np.arange(sdr.READ_SAMPLES) / FS)).astype(np.complex64)
        for _ in range(20):
            buf.feed(z, FS, CENTER)
        self.assertEqual(buf.blocks[-1][4], "i16")
        x, fs, c, _ = buf.segment(time.time() - 100, 0.1)
        self.assertLess(float(np.max(np.abs(x[:1000] - z[:1000]))), 1e-3)
        self.assertIsNone(buf.clip_wav(time.time() - 100, CENTER + 900000, {"mode": "USB"})[0])    # outside the band
        self.assertIsNone(buf.clip_wav(time.time() - 100, CENTER, {"mode": "WFM"})[0])

    def test_save(self):
        buf = retro.RetroBuffer("B")
        buf.set(on=True, seconds=10)
        self.fill(buf, 2, 1000.0, time.time() - 2)
        with tempfile.TemporaryDirectory() as d:
            p = buf.save_iq(d)
            self.assertIn("_14100000Hz_IQ_PREREC.wav", p)
            with wave.open(p) as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (2, 1, int(FS)))
                self.assertEqual(w.getnframes(), buf.samples)


if __name__ == "__main__":
    unittest.main()

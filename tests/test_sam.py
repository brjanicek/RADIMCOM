"""Tests of the SAM key (sdr.SyncAM): synchronous AM through a selective fade, carrier offset, one sideband.

Run: python -m unittest tests.test_sam   (from the RADIMCOM folder)
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sdr  # noqa: E402

FS = 32000.0
SECS = 6.0
T = np.arange(int(FS * SECS)) / FS
RND = np.random.default_rng(5)
# speech-like modulation: three tones with slowly changing levels, 30 % … 80 %
MOD = (0.35 * np.sin(2 * np.pi * 440 * T) * (1 + 0.5 * np.sin(2 * np.pi * 0.7 * T))
       + 0.25 * np.sin(2 * np.pi * 1230 * T) + 0.15 * np.sin(2 * np.pi * 2600 * T + 1))


def am(carrier_gain, offset_hz=0.0, noise=0.003):
    """AM with the carrier scaled by carrier_gain (array: a selective fade hits the carrier, not the sidebands)."""
    x = (carrier_gain + MOD).astype(np.complex128) * np.exp(2j * np.pi * offset_hz * T + 0.7j)
    return x + noise * (RND.normal(size=T.size) + 1j * RND.normal(size=T.size))


def run(x, sam=True, sb="dsb", bw=9000.0):
    ch = sdr.Channel(FS)
    ch.configure("AM", bw)
    ch.sam_on, ch.sam_sb = sam, sb
    filt = sdr.lowpass(bw / 2, FS, 255).astype(np.complex64)
    xf = np.convolve(x, filt, mode="same").astype(np.complex64)
    n = 2048
    out = []
    for i in range(0, len(xf) - n + 1, n):
        if sam:
            out.append(ch.sam.process(xf[i:i + n], bw, sb))
        else:
            env = np.abs(xf[i:i + n])
            out.append(env - env.mean())
    return np.concatenate(out), ch


def fidelity(y, ref=MOD, skip=1.0):
    """dB of the modulation against everything else (distortion, noise), at the best delay (the SB band-pass delays)."""
    from scipy.signal import butter, sosfiltfilt
    hp = butter(4, 150, "highpass", fs=FS, output="sos")   # what is heard: the slow carrier swing (< 2 Hz) left out
    y, ref = sosfiltfilt(hp, y), sosfiltfilt(hp, ref)
    s, n = int(skip * FS), int(3 * FS)
    r = ref[s:s + n]
    best = 0.0
    for d in range(0, 400):
        c = np.corrcoef(y[s + d:s + d + n], r)[0, 1]
        best = max(best, c)
    best = min(best, 1 - 1e-12)
    return 10 * np.log10(best ** 2 / (1 - best ** 2))


class SyncAM(unittest.TestCase):
    def test_selective_fade(self):
        # the carrier fades to 15 % (under the sidebands) twice a second; the envelope detector distorts, SAM does not
        fade = 0.15 + 0.85 * (0.5 + 0.5 * np.cos(2 * np.pi * 0.5 * T)) ** 2
        x = am(fade, offset_hz=35.0)
        env = fidelity(run(x, sam=False)[0])
        y, ch = run(x)
        s = fidelity(y)
        print(f"\nselective fade: envelope {env:.1f} dB, SAM {s:.1f} dB, offset found {ch.sam.f:.1f} Hz")
        self.assertGreater(s, env + 10)
        self.assertGreater(s, 20)
        self.assertAlmostEqual(ch.sam.f, 35.0, delta=2)

    def test_one_sideband_rejects_interferer(self):
        # an interferer 2.5 kHz under the carrier (an adjacent station): SB-U leaves it out
        x = am(1.0) + 0.4 * np.exp(-2j * np.pi * 2500 * T)
        tone = lambda y, f: np.abs(np.dot(y[int(FS):], np.exp(-2j * np.pi * f * T[int(FS):len(y)])))
        dsb, _ = run(x, sb="dsb")
        usb, _ = run(x, sb="usb")
        lsb, _ = run(x, sb="lsb")
        ratio = lambda y: 20 * np.log10(tone(y, 2500) / tone(y, 1230))
        print(f"interferer / speech: DSB {ratio(dsb):.1f} dB, SB-U {ratio(usb):.1f} dB, SB-L {ratio(lsb):.1f} dB")
        self.assertLess(ratio(usb), ratio(dsb) - 30)
        self.assertGreater(fidelity(usb), 15)

    def test_no_carrier_stays_quiet(self):
        y, ch = run(0.003 * (RND.normal(size=T.size) + 1j * RND.normal(size=T.size)))
        self.assertTrue(np.all(np.isfinite(y)))
        self.assertLessEqual(abs(ch.sam.f), sdr.SAM_MAX_OFFSET_HZ)


if __name__ == "__main__":
    unittest.main()

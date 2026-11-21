"""Audio effects of the channel that live in their own module (sdr.py only calls them):

    Tnf        TNF key: tracking notch filters, fixed on radio frequencies (a click with Shift in the spectrum), applied
               to the complex channel baseband, so a notch stays on its carrier while the VFO is tuned around it.
    Apf        APF key (CW): audio peak filter, a narrow resonance on the CW pitch (two band-pass biquads).
    Binaural   BIN key (CW, SSB, AM): pseudo-stereo, the right channel 90 degrees behind the left one (Hilbert FIR):
               the signal seems to stand in the middle of the head and the noise spreads around, which helps the ear.
"""
import math

import numpy as np
from scipy.signal import lfilter

TNF_MAX = 16                    # notches per VFO
TNF_WIDTH_DEFAULT_HZ = 50.0
TNF_WIDTH_MIN_HZ, TNF_WIDTH_MAX_HZ = 10.0, 500.0
TNF_SNAP_HZ = 150.0             # Shift+click this near a notch removes it
APF_WIDTHS = (50, 100, 200)     # Hz
APF_WIDTH_DEFAULT = 100
APF_MODES = ("CW",)
BIN_MODES = ("CW", "USB", "LSB", "AM")
BIN_TAPS = 129                  # Hilbert FIR: 90 degrees from about fs / BIN_TAPS * 2 (~500 Hz at 32 kHz) up


class Tnf:
    """Complex one-pole notches on the channel baseband (0 Hz = tuned frequency):
    H(z) = (1 - e^jw z^-1) / (1 - r e^jw z^-1), zero on the unit circle at w, -3 dB width about (1 - r) fs / pi."""

    def __init__(self):
        self.state = {}

    def reset(self):
        self.state = {}

    def process(self, ch, fs, offsets, width_hz):
        """ch: complex64 baseband; offsets: notch frequencies relative to the tuned frequency (Hz)."""
        new = {}
        r = max(0.0, 1.0 - math.pi * float(width_hz) / fs)
        for off in offsets:
            if abs(off) >= fs / 2:
                continue
            e = np.exp(2j * math.pi * off / fs)
            key = (round(off, 1), round(r, 6), fs)
            zi = self.state.get(key)
            if zi is None:
                zi = np.zeros(1, np.complex128)
            ch, zf = lfilter([1.0, -e], [1.0, -r * e], ch, zi=zi)
            new[key] = zf
        self.state = new
        return np.asarray(ch, np.complex64)


def _bandpass(f0, q, fs):
    """RBJ band-pass biquad, 0 dB at f0."""
    w = 2 * math.pi * f0 / fs
    al = math.sin(w) / (2 * q)
    b = np.array([al, 0.0, -al])
    a = np.array([1 + al, -2 * math.cos(w), 1 - al])
    return b / a[0], a / a[0]


class Apf:
    """Audio peak filter on the CW pitch: two band-pass biquads in a row (steeper skirts, no ringing tail of a
    single very narrow one), each Q = pitch / (width * 1.55), so the pair is about `width` wide at -3 dB."""

    def __init__(self):
        self.key = None
        self.zi = None

    def reset(self):
        self.key = None

    def process(self, x, fs, pitch, width):
        key = (fs, pitch, width)
        if key != self.key:
            b, a = _bandpass(pitch, pitch / (width * 1.55), fs)
            self.ba = (b, a)
            self.zi = [np.zeros(2), np.zeros(2)]
            self.key = key
        b, a = self.ba
        y, self.zi[0] = lfilter(b, a, x, zi=self.zi[0])
        y, self.zi[1] = lfilter(b, a, y, zi=self.zi[1])
        return y.astype(np.float32)


def _hilbert_fir(taps):
    n = np.arange(taps) - (taps - 1) // 2
    h = np.zeros(taps)
    odd = n % 2 != 0
    h[odd] = 2 / (math.pi * n[odd])
    return (h * np.hamming(taps)).astype(np.float32)


class Binaural:
    """Mono audio -> (n, 2): left = the audio delayed by the FIR's half length, right = its Hilbert transform."""

    def __init__(self):
        self.h = _hilbert_fir(BIN_TAPS)
        self.hist = np.zeros(BIN_TAPS - 1, np.float32)

    def reset(self):
        self.hist[:] = 0

    def process(self, x):
        buf = np.concatenate((self.hist, np.asarray(x, np.float32)))
        self.hist = buf[-(BIN_TAPS - 1):]
        right = np.convolve(buf, self.h, mode="valid")
        left = buf[(BIN_TAPS - 1) // 2:(BIN_TAPS - 1) // 2 + len(x)]
        return np.clip(np.stack((left, right), axis=1), -1, 1).astype(np.float32)


def tnf_toggle(notches, hz):
    """Shift+click at hz: removes the nearest notch within TNF_SNAP_HZ, otherwise adds one (at most TNF_MAX)."""
    notches = [float(n) for n in notches]
    near = [n for n in notches if abs(n - hz) <= TNF_SNAP_HZ]
    if near:
        drop = min(near, key=lambda n: abs(n - hz))
        return [n for n in notches if n != drop]
    return sorted(notches + [round(float(hz), 1)])[:TNF_MAX] if len(notches) < TNF_MAX else notches

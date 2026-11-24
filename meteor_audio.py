"""GRAVES (meteor.py): the sound of each echo, to listen to it later (▶ in the detail, kept with a ★ mark).

Ring: the baseband around the carrier (the carrier moved to 0 Hz, low-passed and decimated to about RING_FS, ±8 kHz
for the satellites), the last RING_S seconds, as float16 (about 13 MB).

wav_bytes: a piece of the ring as it sounds on 143.049 MHz USB: the carrier is a 1 kHz tone, 200–3000 Hz, 8 kHz mono
16-bit WAV, scaled to its loudest sample.

track_wav: a satellite. Over the noise of the whole 2.8 kHz a weak one is not heard, and it sweeps by kHz: its signal
is followed along its Doppler track (moved onto 0 Hz, only ±TRACK_BW_HZ kept: its fading and glints stay) and sounds
as a tone that follows the Doppler; when the track would fall out of 200–3000 Hz the tone is moved by one fixed step
(shift_for), a sweep wider than TRACK_SPAN_HZ is squeezed into it.
"""
import io
import wave

import numpy as np

RING_FS = 16000.0
RING_S = 200.0
OUT_FS = 8000
TONE_HZ = 1000.0                        # the carrier in the audio (143.049 MHz USB)
PASS_HZ = (200.0, 3000.0)
PEAK = 0.7
FADE_S = 0.02


class Ring:
    """The baseband around the carrier (at 0 Hz) of the last RING_S seconds, with the time of its last sample."""

    def __init__(self, fs, f_off):
        from scipy.signal import firwin
        self.dec = max(1, int(round(fs / RING_FS)))
        self.fs = fs / self.dec
        self.fs_in = fs
        self.f_off = f_off
        self.taps = firwin(63, min(0.45 * self.fs, 7600.0), fs=fs).astype(np.float32) if self.dec > 1 else None
        self.zi = np.zeros(len(self.taps) - 1, np.complex64) if self.taps is not None else None
        self.n_in = 0                   # input samples mixed so far (the phase of the mixer)
        self.phase_in = 0               # the input sample the decimation goes on from
        self.size = int(RING_S * self.fs)
        self.buf = np.zeros(self.size * 2, np.float16)
        self.n = 0                      # output samples written so far
        self.t_end = None

    def feed(self, base, now):
        from scipy.signal import lfilter
        x = np.asarray(base, np.complex64)
        if not len(x):
            return
        k = np.arange(self.n_in, self.n_in + len(x), dtype=np.float64)
        self.n_in += len(x)
        x = x * np.exp(-2j * np.pi * self.f_off * (k / self.fs_in)).astype(np.complex64)
        if self.taps is not None:
            x, self.zi = lfilter(self.taps, 1.0, x, zi=self.zi)
            first = (-self.phase_in) % self.dec
            x = x[first::self.dec]
            self.phase_in = (self.phase_in + len(k)) % self.dec
        y = np.empty(len(x) * 2, np.float16)
        y[0::2], y[1::2] = x.real, x.imag
        m = len(x)
        if m >= self.size:
            y, m = y[-self.size * 2:], self.size
        a = (self.n % self.size) * 2
        b = a + m * 2
        if b <= len(self.buf):
            self.buf[a:b] = y
        else:
            c = len(self.buf) - a
            self.buf[a:] = y[:c]
            self.buf[:b - len(self.buf)] = y[c:]
        self.n += m
        self.t_end = now

    def clip(self, t0, t1):
        """(start time, complex samples) of t0..t1 that are still in the ring, or None."""
        if self.t_end is None or t1 <= t0:
            return None
        have = min(self.n, self.size)
        t_first = self.t_end - have / self.fs
        t0, t1 = max(t0, t_first), min(t1, self.t_end)
        if t1 - t0 < 0.05:
            return None
        i0 = self.n - int(round((self.t_end - t0) * self.fs))
        i1 = self.n - int(round((self.t_end - t1) * self.fs))
        idx = (np.arange(i0, i1) % self.size) * 2
        z = self.buf[idx].astype(np.float32) + 1j * self.buf[idx + 1].astype(np.float32)
        return t0, z.astype(np.complex64)


def shift_for(freqs):
    """The fixed step (Hz) the sound of a track of these Doppler values is moved by: 0 when it is heard on 143.049 USB
    as it is (TONE_HZ + Doppler within PASS_HZ, a little margin), else so its middle is at 1.5 kHz."""
    if not len(freqs):
        return 0.0
    lo, hi = TONE_HZ + min(freqs), TONE_HZ + max(freqs)
    if lo >= PASS_HZ[0] + 100 and hi <= PASS_HZ[1] - 100:
        return 0.0
    return float(round((min(freqs) + max(freqs)) / 2 + TONE_HZ - 1500.0))


def wav_bytes(t0, iq, fs, shift_hz=0.0):
    """The clip (start time, complex baseband with the carrier at 0 Hz) as USB audio (WAV bytes): the carrier at
    TONE_HZ - shift_hz, every echo with its own Doppler."""
    from scipy.signal import firwin, lfilter
    n = len(iq)
    ph = 2 * np.pi * (TONE_HZ - shift_hz) * np.arange(n) / fs
    y = iq.astype(np.complex128) * np.exp(1j * ph)
    mid, half = (PASS_HZ[0] + PASS_HZ[1]) / 2, (PASS_HZ[1] - PASS_HZ[0]) / 2
    k = np.arange(n) / fs
    lp = firwin(129, half, fs=fs)
    y = lfilter(lp, 1.0, y * np.exp(-2j * np.pi * mid * k)) * np.exp(2j * np.pi * mid * k)   # only 200..3000 Hz: USB
    a = y.real
    step = max(1, int(round(fs / OUT_FS)))
    a = a[::step]
    out_fs = int(round(fs / step))
    pk = float(np.max(np.abs(a))) if len(a) else 0.0
    if pk > 0:
        a = a * (PEAK / pk)
    nf = min(len(a) // 2, int(FADE_S * out_fs))
    if nf:
        w = np.linspace(0.0, 1.0, nf)
        a[:nf] *= w
        a[-nf:] *= w[::-1]
    pcm = np.clip(a * 32767, -32768, 32767).astype("<i2").tobytes()
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(out_fs)
        w.writeframes(pcm)
    return bio.getvalue()


TRACK_BW_HZ = 60.0                      # a satellite: ± this around its Doppler track is kept (its fading, not the noise)
TRACK_SPAN_HZ = 2000.0                  # a track sweeping wider is squeezed into this much of the audio (around 1.5 kHz)
TRACK_EDGE_S = 0.3                      # the sound fades in / out this long at the ends of the track


def _track_of(pts):
    """(times, Hz) of a Doppler track, sorted and smoothed (a running median of 7: single points off it are left out)."""
    p = sorted((float(t), float(f)) for t, f in pts)
    t = np.array([a for a, _ in p])
    f = np.array([b for _, b in p])
    if len(f) >= 7:
        pad = np.r_[np.full(3, f[0]), f, np.full(3, f[-1])]
        f = np.median(np.lib.stride_tricks.sliding_window_view(pad, 7), axis=1)
    return t, f


def track_wav(t0, iq, fs, pts):
    """The sound of a satellite (WAV bytes): its signal followed along its Doppler track pts [(t, Hz)], only ±TRACK_BW_HZ
    around it (a weak track over the noise of the whole band is heard at all), as a tone that follows its Doppler. Up to
    TRACK_SPAN_HZ wide it is as on 143.049 USB (moved by one fixed step when out of 200–3000 Hz: shift_for); a wider
    sweep is squeezed into TRACK_SPAN_HZ around 1.5 kHz. -> (WAV bytes, the step Hz, the squeeze factor)."""
    from scipy.signal import butter, sosfiltfilt
    n = len(iq)
    tt, ff = _track_of(pts)
    if not n or not len(tt):
        return None
    ts = t0 + np.arange(n) / fs
    f = np.interp(ts, tt, ff)                                         # the Doppler at each sample (its ends held)
    z = iq.astype(np.complex128) * np.exp(-2j * np.pi * np.cumsum(f) / fs)          # the track onto 0 Hz
    sos = butter(4, TRACK_BW_HZ, fs=fs, output="sos")
    z = sosfiltfilt(sos, z.real) + 1j * sosfiltfilt(sos, z.imag)
    lo, hi = float(ff.min()), float(ff.max())
    mid = (lo + hi) / 2
    k = min(1.0, TRACK_SPAN_HZ / max(hi - lo, 1.0))
    sh = shift_for([lo, hi]) if k >= 1.0 else float(round(mid + TONE_HZ - 1500.0))
    g = TONE_HZ - sh + mid + (f - mid) * k                            # the tone in the audio
    a = (z * np.exp(2j * np.pi * np.cumsum(g) / fs)).real
    gate = np.clip(np.minimum(ts - tt[0], tt[-1] - ts) / TRACK_EDGE_S + 1.0, 0.0, 1.0)   # only along the track
    a = a * gate
    step = max(1, int(round(fs / OUT_FS)))
    a = a[::step]
    out_fs = int(round(fs / step))
    pk = float(np.percentile(np.abs(a), 99.9)) if len(a) else 0.0    # a single spike does not make it quiet
    if pk > 0:
        a = np.clip(a * (PEAK / pk), -1.0, 1.0)
    nf = min(len(a) // 2, int(FADE_S * out_fs))
    if nf:
        w = np.linspace(0.0, 1.0, nf)
        a[:nf] *= w
        a[-nf:] *= w[::-1]
    pcm = np.clip(a * 32767, -32768, 32767).astype("<i2").tobytes()
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(out_fs)
        w.writeframes(pcm)
    return bio.getvalue(), sh, k


def tone_of(wav):
    """The strongest audio frequency of a WAV (tests)."""
    with wave.open(io.BytesIO(wav)) as w:
        fs = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float)
    if len(a) < 16:
        return 0.0
    s = np.abs(np.fft.rfft(a * np.hanning(len(a))))
    return float(np.argmax(s) * fs / len(a))


def duration_of(wav):
    with wave.open(io.BytesIO(wav)) as w:
        return w.getnframes() / w.getframerate()


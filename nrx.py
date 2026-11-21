"""More noise reduction algorithms for the DNR key, chosen in SETTINGS › VFO › AUDIO (sdr.SpectralNR stays the default):

    SpecBleach  "NR4": spectral noise reduction after the ideas of libspecbleach / noise-repellent (Luciano Dato), as in
                Thetis NR4: a noise estimate from the speech presence probability (SPP-MMSE, Gerkmann & Hendriks 2012),
                which follows a changing noise within a fraction of a second and needs no speech pauses; the gain from
                the decision-directed a-priori SNR, smoothed in time (fast attack, slow release) and over neighbouring
                bins, so the rest of the noise stays smooth. Level 1-10 sets the reduction (6-30 dB), as for DNR.
    RnNoise     "RNN": the recurrent neural network RNNoise (Xiph.Org, BSD licence) for speech, through lib\\rnnoise\\
                rnnoise.dll (installer/get_rnnoise.py puts it there). It works at 48 kHz on 10 ms frames: the audio is
                interpolated to 48 kHz and back. No level (the network decides); for speech (SSB, AM), not for CW.

Both have the interface of sdr.SpectralNR: process(x) -> the same number of samples, reset(), level, reduction_db.
"""
import ctypes
import os

import numpy as np

ALGOS = ("wiener", "nr4", "rnn")
ALGO_DEFAULT = "wiener"
RNN_DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib", "rnnoise", "rnnoise.dll")


def reduction_floor(level):
    """Level 1-10 -> the gain floor (linear): 6 ... 30 dB below the input."""
    lv = min(max(float(level), 1.0), 10.0)
    return 10 ** (-(3.3 + 2.67 * lv) / 20)


class SpecBleach:
    N, H = 1024, 256
    XI_H1 = 10 ** (15 / 10)      # SPP: the a-priori SNR assumed while speech is present (15 dB)
    P_SMOOTH = 0.9               # smoothing of the speech presence probability
    N_SMOOTH = 0.9               # noise power smoothing per hop
    DD = 0.9                     # decision-directed weight (lower than DNR: follows the speech faster)
    GAIN_EXP = 0.7               # Wiener gain to this power (0.5: power subtraction): keeps more of weak speech
    RELEASE = 0.6                # gain release per hop (a falling gain is followed slowly: no warbling)

    def __init__(self, fs):
        self.fs = fs
        self.win = np.hanning(self.N + 1)[:-1].astype(np.float32)
        self.level = 3
        self.reset()

    def reset(self):
        nb = self.N // 2 + 1
        self.inp = np.zeros(self.N - self.H, np.float32)
        self.ola = np.zeros(self.N, np.float32)
        self.pending = np.zeros(self.H, np.float32)
        self.noise = None
        self.pbar = np.zeros(nb)
        self.g2p = np.ones(nb)
        self.gp = np.ones(nb)
        self.gain = np.ones(nb)
        self.frames = 0
        self.reduction_db = 0.0

    def _frame(self, X):
        p = X.real ** 2 + X.imag ** 2 + 1e-20
        self.frames += 1
        if self.noise is None or self.frames <= 6:          # the first frames: the noise from their mean
            self.noise = p.copy() if self.noise is None else 0.7 * self.noise + 0.3 * p
        else:
            snr = p / self.noise
            q = self.XI_H1 / (1 + self.XI_H1)
            post = 1.0 / (1.0 + (1.0 + self.XI_H1) * np.exp(-np.minimum(snr * q, 60.0)))
            self.pbar = self.P_SMOOTH * self.pbar + (1 - self.P_SMOOTH) * post
            post = np.where(self.pbar > 0.99, np.minimum(post, 0.99), post)   # no stall when speech seems always there
            est = (1 - post) * p + post * self.noise
            self.noise = self.N_SMOOTH * self.noise + (1 - self.N_SMOOTH) * est
        gamma = p / self.noise
        xi = self.DD * self.g2p * self.gp + (1 - self.DD) * np.maximum(gamma - 1.0, 0.0)
        g = (xi / (1.0 + xi)) ** self.GAIN_EXP
        g = np.convolve(np.pad(g, 2, mode="edge"), (0.1, 0.2, 0.4, 0.2, 0.1), "valid")
        g = np.maximum(g, self.gain * self.RELEASE)          # fast attack, slow release
        g = np.clip(g, reduction_floor(self.level), 1.0)
        self.g2p, self.gp, self.gain = g * g, gamma, g
        return X * g.astype(np.float32)

    def process(self, x):
        N, H, w = self.N, self.H, self.win
        buf = np.concatenate((self.inp, np.asarray(x, np.float32)))
        nf = max((len(buf) - N) // H + 1, 0)
        out = np.empty(nf * H, np.float32)
        for k in range(nf):
            Y = self._frame(np.fft.rfft(buf[k * H:k * H + N] * w))
            self.ola += np.fft.irfft(Y, N).astype(np.float32) * w / 1.5
            out[k * H:(k + 1) * H] = self.ola[:H]
            self.ola = np.concatenate((self.ola[H:], np.zeros(H, np.float32)))
        self.inp = buf[nf * H:]
        if self.noise is not None:
            quiet = self.gp < 2.0
            if np.any(quiet):
                self.reduction_db = round(float(-20 * np.log10(np.mean(self.gain[quiet]) + 1e-6)), 1)
        allout = np.concatenate((self.pending, out))
        self.pending = allout[len(x):]
        return allout[:len(x)]


class _Interp:
    """Streaming linear interpolation from fs_in to fs_out (the audio has nothing above ~4 kHz, so this is enough)."""

    def __init__(self, fs_in, fs_out):
        self.step = fs_in / fs_out
        self.prev = 0.0
        self.t = 1.0          # position of the next output, in input samples after self.prev (1 = the first new sample)

    def process(self, x):
        buf = np.concatenate(([self.prev], np.asarray(x, np.float64)))
        n = int(np.floor((len(buf) - 1 - self.t) / self.step)) + 1 if len(buf) > 1 else 0
        pos = self.t + self.step * np.arange(max(n, 0))
        pos = pos[pos <= len(buf) - 1]
        y = np.interp(pos, np.arange(len(buf)), buf)
        self.t = (pos[-1] + self.step if len(pos) else self.t) - (len(buf) - 1)
        self.prev = buf[-1]
        return y.astype(np.float32)


_lib = None
_lib_error = ""


def rnn_library():
    """The loaded rnnoise.dll, or None (rnn_error() says why)."""
    global _lib, _lib_error
    if _lib is not None or _lib_error:
        return _lib
    if not os.path.isfile(RNN_DLL):
        _lib_error = "lib\\rnnoise\\rnnoise.dll is missing (run installer\\get_rnnoise.py)"
        return None
    try:
        lib = ctypes.CDLL(RNN_DLL)
        lib.rnnoise_create.argtypes = [ctypes.c_void_p]
        lib.rnnoise_create.restype = ctypes.c_void_p
        lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
        lib.rnnoise_process_frame.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float)]
        lib.rnnoise_process_frame.restype = ctypes.c_float
        lib.rnnoise_get_frame_size.restype = ctypes.c_int
        if lib.rnnoise_get_frame_size() != 480:
            raise OSError("unexpected frame size")
        _lib = lib
    except OSError as e:
        _lib_error = f"rnnoise.dll cannot be loaded: {e}"
    return _lib


def rnn_error():
    rnn_library()
    return _lib_error


class RnNoise:
    RATE = 48000
    FRAME = 480

    def __init__(self, fs):
        self.fs = fs
        self.level = 3                  # not used: the network has no strength
        self.lib = rnn_library()
        self.state = self.lib.rnnoise_create(None) if self.lib else None
        self.reset()

    def __del__(self):
        try:
            if self.state and self.lib:
                self.lib.rnnoise_destroy(self.state)
        except Exception:
            pass

    def reset(self):
        self.up = _Interp(self.fs, self.RATE)
        self.down = _Interp(self.RATE, self.fs)
        self.in48 = np.zeros(0, np.float32)
        self.out = np.zeros(int(self.fs * 0.02), np.float32)     # 20 ms head start: the frames and interpolation lag
        self.vad = 0.0
        self.reduction_db = 0.0
        self._quiet = [0.0, 0.0]

    def process(self, x):
        x = np.asarray(x, np.float32)
        if not self.state:
            return x
        self.in48 = np.concatenate((self.in48, self.up.process(x)))
        nfr = len(self.in48) // self.FRAME
        res = np.empty(nfr * self.FRAME, np.float32)
        for k in range(nfr):
            fr = np.ascontiguousarray(self.in48[k * self.FRAME:(k + 1) * self.FRAME] * 32767.0, np.float32)
            pin = float(np.mean(fr * fr))
            ptr = fr.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            self.vad = float(self.lib.rnnoise_process_frame(self.state, ptr, ptr))
            res[k * self.FRAME:(k + 1) * self.FRAME] = fr / 32767.0
            if self.vad < 0.2:                                     # no speech: how much of the noise is taken out
                self._quiet = [0.95 * self._quiet[0] + pin, 0.95 * self._quiet[1] + float(np.mean(fr * fr))]
        self.in48 = self.in48[nfr * self.FRAME:]
        if self._quiet[0] > 0:
            self.reduction_db = round(float(10 * np.log10((self._quiet[0] + 1e-9) / (self._quiet[1] + 1e-9))), 1)
        self.out = np.concatenate((self.out, self.down.process(res)))
        if len(self.out) < len(x):                                 # never short: pad (only right after a reset)
            self.out = np.concatenate((np.zeros(len(x) - len(self.out), np.float32), self.out))
        y, self.out = self.out[:len(x)], self.out[len(x):]
        if len(self.out) > self.fs * 0.1:                          # never a growing delay
            self.out = self.out[-int(self.fs * 0.03):]
        return y

"""More noise reduction algorithms for the DNR key, chosen in SETTINGS › VFO › AUDIO (sdr.SpectralNR stays the default):

    SpecBleach  "NR4": spectral noise reduction after the ideas of libspecbleach / noise-repellent (Luciano Dato), as in
                Thetis NR4: a noise estimate from the speech presence probability (SPP-MMSE, Gerkmann & Hendriks 2012),
                which follows a changing noise within a fraction of a second and needs no speech pauses; the gain from
                the decision-directed a-priori SNR, smoothed in time (fast attack, slow release) and over neighbouring
                bins, so the rest of the noise stays smooth. Level 1-10 sets the reduction (6-30 dB), as for DNR.

(1.1rc2: the RNNoise algorithm "RNN" was removed, it did not give good results on the air.)

It has the interface of sdr.SpectralNR: process(x) -> the same number of samples, reset(), level, reduction_db.
"""
import numpy as np

ALGOS = ("wiener", "nr4")
ALGO_DEFAULT = "wiener"


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


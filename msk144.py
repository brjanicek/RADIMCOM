"""MSK144 decoder (meteor scatter on 6 m / 2 m, WSJT-X mode): own demodulator, LDPC belief propagation and CRC.

MSK144: 2000 bit/s MSK (offset QPSK with half-sine pulses) centred on 1500 Hz of USB audio; a frame is 144 bits = 72 ms
(8 sync bits, 48 code bits, 8 sync bits, 80 code bits) and is repeated during the whole transmission (15 s periods), so
a meteor ping of 0.1 s carries a frame or two. The code is the (128,90) LDPC code of WSJT-X over the 77-bit message of
FT8 with a 13-bit CRC (msk144_ldpc.py, GPL from WSJT-X); the messages are unpacked by PyFT8 (as FT8).

The receiver's baseband (0 Hz = dial) is shifted by -1500 Hz, low-passed and resampled to 12 kHz complex. Every
144 ms a window of 4 frames (288 ms) is checked:
  1. ping detector: the squared MSK signal has two lines at +-1000 Hz + 2 df (df = frequency offset); their height over
     the median of the spectrum of the window gives df within +-TOL_HZ and says whether a signal is there at all;
  2. frame timing: correlation with the waveform of the sync word, summed at its two places in a frame (+336 samples);
     the best few starts are tried, both polarities (the conjugate, as from an inverted sideband);
  3. per frame: the carrier phase and a fine frequency from the two sync words, matched-filter soft bits, the sync
     must have at most 4 wrong bits; LLR to belief propagation (10 iterations), CRC13; first one frame, then the frames
     of the window averaged coherently (weak long pings).
The same message within DUP_S seconds is one decode (pings carry it many times); its count goes up.

Not decoded: the short MSK40 messages ("<CALL1 CALL2> R+12") and free text / contest messages PyFT8 cannot unpack.
"""
import collections
import queue
import threading
import time

import numpy as np

import msk144_ldpc
from location import locator_to_latlon
from sdr import lowpass

try:
    import ft8 as _ft8                  # the pyaudio stub and the PyFT8 import live there
    _unpack = _ft8.pft8.unpack if _ft8.IMPORT_ERROR is None else None
    sender_of = _ft8.sender_of
    IMPORT_ERROR = _ft8.IMPORT_ERROR
except Exception as e:                  # pragma: no cover
    _unpack, sender_of, IMPORT_ERROR = None, (lambda m: (None, None)), f"MSK144 decoder not available ({e})"

FS = 12000.0
NSPM = 864                  # samples per frame (72 ms)
CENTER_HZ = 1500.0
TOL_HZ = 100.0              # frequency search around 1500 Hz (as WSJT-X F Tol)
WIN = 4 * NSPM              # analysed window
HOP = 2 * NSPM
DETECT = 3.3                # ping detector: line height over the median of the squared spectrum (noise: below 3.0)
DETECT_SURE = 6.0           # ... this high: its frequency is used, no search
POWER_TRIGGER = 1.4         # ... or a frame time (72 ms) of the window louder than the noise by this (1.5 dB)
GRID_HZ = 4.0               # frequency search step with the sync word (the frame then refines it)
TRIES = 8                   # frame starts / frequencies tried per window
PEAKS = 3                   # frame starts tried per window
DUP_S = 10.0
MAX_ITER = 10
SIGMA = 0.6                 # soft bit noise for the LLR (WSJT-X)
MSK144_FREQS = (50260000, 50280000, 144150000, 144360000, 222100000, 432360000)   # usual calling frequencies (USB dial)

S8 = np.array([0, 1, 1, 1, 0, 0, 1, 0])
PP = np.sin(np.arange(12) * np.pi / 12)             # half-sine pulse, 12 samples (2 bits on one rail)


def _sync_waveform():
    s = 2 * S8 - 1
    q = np.concatenate((PP[6:] * s[0], PP * s[2], PP * s[4], PP * s[6]))
    i = np.concatenate((PP * s[1], PP * s[3], PP * s[5], PP[:6] * s[7]))
    return (i + 1j * q).astype(np.complex64)


CB = _sync_waveform()       # 42 samples: the sync word as it starts a frame


def modulate(codeword_bits):
    """144 channel bits (0/1, sync included) -> one frame of complex baseband (864 samples), as WSJT-X genmsk_128_90."""
    b = 2 * np.asarray(codeword_bits, float) - 1
    xi, xq = np.zeros(NSPM), np.zeros(NSPM)
    xq[:6] = b[0] * PP[6:]
    for i in range(1, 72):
        xq[(i - 1) * 12 + 6:(i - 1) * 12 + 18] = b[2 * i] * PP
    xq[NSPM - 6:] = b[0] * PP[:6]
    for i in range(72):
        xi[i * 12:i * 12 + 12] = b[2 * i + 1] * PP
    return (xi + 1j * xq).astype(np.complex64)


# ---------- the code ----------

def _code():
    n, m = 128, 38
    rows = [np.array(r) - 1 for r in msk144_ldpc.NM]
    edge_chk = np.concatenate([np.full(len(r), i) for i, r in enumerate(rows)])
    edge_bit = np.concatenate(rows)
    gen = np.zeros((m, 90), np.uint8)
    for i, h in enumerate(msk144_ldpc.GEN):
        gen[i] = [int(c) for c in bin(int(h, 16))[2:].zfill(92)[:90]]
    starts = np.concatenate(([0], np.cumsum([len(r) for r in rows])[:-1]))
    return n, m, edge_chk, edge_bit, starts, gen


N_BITS, M_CHK, EDGE_CHK, EDGE_BIT, ROW_START, GEN = _code()


def crc13(bits77):
    """13-bit CRC of WSJT-X (boost augmented_crc<13, 0x15D7> over 12 bytes: the 77 bits, then zeros)."""
    reg = 0
    for i in range(96):
        inbit = int(bits77[i]) if i < 77 else 0
        top = (reg >> 12) & 1
        reg = ((reg << 1) & 0x1FFF) | inbit
        if top:
            reg ^= 0x15D7
    return reg


def encode(bits77):
    """77 message bits -> 144 channel bits (sync + codeword), as WSJT-X."""
    c = crc13(bits77)
    msg = np.concatenate((np.asarray(bits77, np.uint8), np.array([(c >> (12 - k)) & 1 for k in range(13)], np.uint8)))
    cw = np.concatenate((msg, GEN.dot(msg) % 2))
    return np.concatenate((S8, cw[:48], S8, cw[48:])).astype(np.uint8)


def bp_decode(llr):
    """Belief propagation (log domain, tanh rule) as WSJT-X bpdecode128_90; llr > 0 = bit 1.
    -> (77 message bits, hard errors) or None."""
    tov = np.zeros(len(EDGE_BIT))
    for _ in range(MAX_ITER + 1):
        zn = llr + np.bincount(EDGE_BIT, weights=tov, minlength=N_BITS)
        cw = (zn > 0).astype(np.int64)
        if not (np.bincount(EDGE_CHK, weights=cw[EDGE_BIT], minlength=M_CHK) % 2).any():
            dec = cw[:90]
            c = crc13(dec[:77])
            if all(((c >> (12 - k)) & 1) == dec[77 + k] for k in range(13)):
                return dec[:77], int(np.count_nonzero((2 * cw - 1) * llr < 0))
        toc = zn[EDGE_BIT] - tov
        t = np.tanh(-toc / 2)
        t = np.where(np.abs(t) < 1e-12, 1e-12, t)
        prod = np.multiply.reduceat(t, ROW_START)[EDGE_CHK]
        tov = 2 * np.arctanh(np.clip(-prod / t, -0.999999, 0.999999))
    return None


def unpack(bits77):
    if _unpack is None:
        return None
    i3 = int(bits77[74]) * 4 + int(bits77[75]) * 2 + int(bits77[76])
    n3 = int(bits77[71]) * 4 + int(bits77[72]) * 2 + int(bits77[73])
    if (i3 == 0 and (n3 in (1, 3, 4) or n3 > 5)) or i3 == 3 or i3 > 5:     # as WSJT-X msk144decodeframe
        return None
    v = 0
    for b in bits77:
        v = (v << 1) | int(b)
    try:
        t = _unpack(v)
    except Exception:
        return None
    return " ".join(x for x in t if x) if t else None


# ---------- the signal ----------

def soft_bits(c):
    """One frame (864 complex samples, carrier phase removed) -> 144 soft bits (matched filter)."""
    sb = np.empty(144)
    sb[0] = np.dot(c[:6].imag, PP[6:]) + np.dot(c[NSPM - 6:].imag, PP[:6])
    sb[1] = np.dot(c[:12].real, PP)
    for i in range(1, 72):
        sb[2 * i] = np.dot(c[i * 12 - 6:i * 12 + 6].imag, PP)
        sb[2 * i + 1] = np.dot(c[i * 12:i * 12 + 12].real, PP)
    return sb


def decode_frame(c):
    """Complex frame (864 samples, frequency nearly removed) -> (message, hard errors, residual Hz) or None."""
    t = np.arange(NSPM) / FS
    df = 0.0
    for _ in range(2):          # the frequency error from the phase step between the two sync words, then again
        cca = np.vdot(CB, c[:42])
        ccb = np.vdot(CB, c[336:378])
        step = np.angle(ccb * np.conj(cca)) / (2 * np.pi * 336 / FS)
        if abs(step) > 1.0:
            df += step
            c = c * np.exp(-2j * np.pi * step * t).astype(np.complex64)
        else:
            break
    cca = np.vdot(CB, c[:42])
    ccb = np.vdot(CB, c[336:378])
    c = c * np.exp(-1j * np.angle(cca + ccb))
    sb = soft_bits(c)
    hard = sb >= 0
    bad = int(np.count_nonzero(hard[:8] != S8.astype(bool)) + np.count_nonzero(hard[56:64] != S8.astype(bool)))
    if bad > 4:
        return None
    sb = (sb - sb.mean()) / (sb.std() + 1e-12)
    llr = 2.0 * np.concatenate((sb[8:56], sb[64:144])) / (SIGMA * SIGMA)
    res = bp_decode(llr)
    if res is None or res[1] >= 18:
        return None
    msg = unpack(res[0])
    return (msg, res[1], df) if msg else None


class Analyser:
    """Finds and decodes MSK144 frames in windows of 12 kHz complex baseband centred on 1500 Hz."""

    def __init__(self, tol_hz=TOL_HZ):
        self.tol = tol_hz
        self.t = np.arange(WIN) / FS
        self.nfft = 8192
        f = np.fft.fftfreq(self.nfft, 1 / FS)
        self.inband = np.abs(f) <= 1000 + 2 * tol_hz + 200
        self.noise = None           # mean power of the windows without a signal (for the SNR)
        self.triggered = 0          # windows that looked like a ping

    def window(self, w):
        """-> list of (message, df Hz, snr dB, frames averaged, hard errors, start sample)."""
        p = float(np.mean(np.abs(w) ** 2)) + 1e-20
        z = np.fft.fft(w * w * np.hanning(len(w)), self.nfft)
        mag = np.abs(z)
        floor = float(np.median(mag[self.inband])) + 1e-20      # the squared band (filtered noise: +-2.7 kHz)
        mag = np.maximum(mag, np.maximum(np.roll(mag, 1), np.roll(mag, -1)))     # a line between two bins
        bins = FS / self.nfft
        dfs = np.arange(-self.tol, self.tol + 0.5, 0.5)
        score = (mag[np.round((1000 + 2 * dfs) / bins).astype(int) % self.nfft]
                 + mag[np.round((-1000 + 2 * dfs) / bins).astype(int) % self.nfft]) / (2 * floor)
        best = int(np.argmax(score))
        sub = float(np.max(np.mean(np.abs(w[:4 * NSPM].reshape(4, NSPM)) ** 2, axis=1)))   # the loudest frame time
        louder = self.noise is not None and sub > POWER_TRIGGER * self.noise
        if score[best] < DETECT and not louder:
            self.noise = p if self.noise is None else 0.95 * self.noise + 0.05 * min(p, 3 * self.noise)
            return []
        self.triggered += 1
        # frequency: from the squared spectrum when its lines are clear, otherwise searched with the sync word
        grid = [float(dfs[best])] if score[best] >= DETECT_SURE else list(np.arange(-self.tol, self.tol + 0.1, GRID_HZ))
        cands = []
        for conj in (False, True):
            x = np.conj(w) if conj else w
            for d0 in grid:
                d = -d0 if conj else d0
                cm = x * np.exp(-2j * np.pi * d * self.t).astype(np.complex64)
                xc = np.abs(np.convolve(cm, np.conj(CB[::-1]), mode="valid"))      # xc[k]: the sync word at k
                sc = xc[:len(xc) - 336] + xc[336:]
                for _ in range(PEAKS):
                    k = int(np.argmax(sc))
                    cands.append((float(sc[k]), conj, d, k % NSPM))
                    sc[max(0, k - 7):k + 8] = 0
        cands.sort(key=lambda c: -c[0])
        out, tried = [], set()
        for _, conj, d, k0 in cands:
            key = (conj, round(d / 8), k0 // 4)
            if key in tried:
                continue
            tried.add(key)
            if len(tried) > TRIES:
                break
            x = np.conj(w) if conj else w
            cm = x * np.exp(-2j * np.pi * d * self.t).astype(np.complex64)
            # the frames repeat, so any 72 ms hold all 144 bits: the loudest 72 ms (the peak of the ping) turned so that
            # the sync word comes first, then the whole frames of the window, then all of them averaged
            e = np.convolve(np.abs(cm) ** 2, np.ones(NSPM), mode="valid")
            j = int(np.argmax(e))
            segs = [np.roll(cm[j:j + NSPM], -((k0 - j) % NSPM))]
            starts = list(range(k0, WIN - NSPM + 1, NSPM))
            segs += [cm[s0:s0 + NSPM] for s0 in starts if s0 != j]
            hit, nav, st = None, 1, j
            for seg in segs:                                        # each frame alone
                hit = decode_frame(seg)
                if hit:
                    break
            if not hit and len(starts) > 1:                         # the frames averaged
                hit = decode_frame(np.sum([cm[s0:s0 + NSPM] for s0 in starts], axis=0))
                nav = len(starts)
            if hit:
                msg, nerr, fine = hit
                df = -(d + fine) if conj else d + fine
                noise = self.noise if self.noise else p / 10
                snr = 10 * np.log10(max(p - noise, 1e-20) / noise)
                out.append((msg, round(df, 1), int(round(snr)), nav, nerr, st))
                break
        return out


class Msk144Decoder:
    """Turns decoding on/off, prepares 12 kHz complex baseband around 1500 Hz and analyses it in its own thread."""

    def __init__(self, on_decode, tol_hz=TOL_HZ):
        self.on_decode = on_decode
        self.decodes = collections.deque(maxlen=400)
        self.stations = {}
        self.enabled = False
        self.error = IMPORT_ERROR
        self.dial_hz = 0.0
        self.tol_hz = tol_hz
        self.pings = 0                       # windows with a signal (detector), since switched on
        self.lock = threading.Lock()
        self._q = queue.Queue(maxsize=64)
        self._fs = None
        self._thread = None
        self._recent = {}

    def set_enabled(self, on):
        if on and IMPORT_ERROR:
            on = False
        if on and not self.enabled:
            self._fs = None
            self.pings = 0
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="msk144", daemon=True)
                self._thread.start()
        self.enabled = bool(on)

    @property
    def info(self):
        return f"{len(self.decodes)} decodes · {self.pings} pings" if self.enabled else ""

    def _setup(self, fs):
        self._fs = fs
        taps = 255
        self._h = lowpass(1350.0, fs, taps).astype(np.complex64)
        self._hist = np.zeros(taps - 1, np.complex64)
        self._ph = 0.0
        self._t = 1.0
        self._last = 0j
        self._buf = np.zeros(0, np.complex64)
        self._t0 = None

    def feed(self, base, fs, dial_hz):
        """base: complex baseband (dial = 0 Hz) at fs."""
        if not self.enabled:
            return
        if fs != self._fs:
            self._setup(fs)
        if dial_hz != self.dial_hz:
            self._buf = np.zeros(0, np.complex64)     # retuned: a new start
            self.dial_hz = dial_hz
        n = len(base)
        mix = np.exp(1j * (self._ph - 2 * np.pi * CENTER_HZ / fs * np.arange(n))).astype(np.complex64)
        self._ph = (self._ph - 2 * np.pi * CENTER_HZ / fs * n) % (2 * np.pi)
        buf = np.concatenate((self._hist, base * mix))
        self._hist = buf[-(len(self._h) - 1):]
        y = np.convolve(buf, self._h, mode="valid")
        y = np.concatenate(([self._last], y))
        step = fs / FS
        pos = np.arange(self._t, len(y) - 1 + 1e-9, step)
        self._last = y[-1]
        if not len(pos):
            self._t -= len(y) - 1
            return
        self._t = pos[-1] + step - (len(y) - 1)
        out = (np.interp(pos, np.arange(len(y)), y.real) + 1j * np.interp(pos, np.arange(len(y)), y.imag)).astype(np.complex64)
        self._buf = np.concatenate((self._buf, out))
        while len(self._buf) >= WIN:
            try:
                self._q.put_nowait((time.time() - (len(self._buf) - 0) / FS, self._buf[:WIN].copy(), self.dial_hz))
            except queue.Full:
                pass                                   # the PC cannot keep up: a window is skipped
            self._buf = self._buf[HOP:]

    def _run(self):
        an = Analyser(self.tol_hz)
        while True:
            t0, w, dial = self._q.get()
            if not self.enabled:
                continue
            try:
                hits = an.window(w)
            except Exception as e:                     # never take the receiver down
                self.error = f"MSK144: {e}"
                continue
            if an.noise is not None and np.mean(np.abs(w) ** 2) > 2 * an.noise:
                self.pings += 1
            for msg, df, snr, nav, nerr, start in hits:
                self._decoded(t0 + start / FS, dial, msg, df, snr, nav, nerr)

    def _decoded(self, ts, dial, msg, df, snr, nav, nerr):
        now = time.time()
        self._recent = {m: t for m, t in self._recent.items() if now - t < DUP_S}
        if msg in self._recent:
            self._recent[msg] = now
            with self.lock:
                for d in reversed(self.decodes):
                    if d["msg"] == msg:
                        d["n"] += 1
                        d["snr"] = max(d["snr"], snr)
                        break
            return
        self._recent[msg] = now
        d = {"time": time.strftime("%H:%M:%S", time.gmtime(ts)), "ts": ts, "snr": snr, "df": round(CENTER_HZ + df),
             "freq_hz": round(dial + CENTER_HZ + df), "msg": msg, "nav": nav, "nerr": nerr, "n": 1,
             "dt": round(ts % 15, 1)}
        call, grid = sender_of(msg)
        if call:
            d["call"] = call
            if grid:
                d["grid"] = grid
                d["lat"], d["lon"] = locator_to_latlon(grid)
        with self.lock:
            self.decodes.append(d)
        self.on_decode(d)

    def clear(self):
        with self.lock:
            self.decodes.clear()
        self._recent = {}

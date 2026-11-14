"""RTTY decoder (Baudot/ITA2) from the baseband with automatic detection of shift, speed and polarity.

Method: decimation to 8 kHz -> AFC in the spectrum of the last 4 s finds the mark/space tone pair
(shift 90–1000 Hz, or as set) -> each tone mixed to 0 Hz and a moving average one bit long
-> envelope difference (m - s)/(m + s) -> speed from the edge positions (edges lie on a 1/baud grid)
-> asynchronous receiver (start, 5 bits, stop) for both polarities at once; the text comes from the one
with fewer framing errors. Mark is the higher tone on RF (the usual "normal" polarity), independent of the mode.
"""
import base64
import collections
import threading
import time

import numpy as np

from sdr import lowpass

RATE = 8000.0          # Hz, sample rate after decimation
NFFT = 2048            # AFC resolution ≈ 4 Hz
AFC_SEC = 4            # AFC window
MIN_SNR = 5.0          # power of the weaker tone relative to noise (≈ 7 dB)
STD_TOL = 12.0         # Hz: a pair this close to a standard shift counts as standard
STD_PREFER = 0.25      # a standard pair wins over an odd one down to this part of its power
REPLAY_SEC = 3.5       # s of buffered signal decoded again after a new lock (the AFC buffer is AFC_SEC)
CONFIRM_MIN = 1.5      # s after a new lock: the text waits at least this long ...
CONFIRM_MAX = 4.0      # ... until the speed estimate agrees, but at most this long
NOISE = -2             # receiver result: a frame too unclear to be a character (noise between overs)
RUN_MIN = 3            # characters after the squelch opens before its text is written (shorter runs = transients)
NEWLINE = "\x00"       # marker in the decoded text: a new line here unless the text is already at one
ODD_HOLD = 20          # s: a lock on a standard pair is not given up for an odd pair for this long
SHIFTS = (170, 200, 425, 450, 850)
BAUDS = (45.45, 50.0, 75.0, 100.0)
EDGE_SEC = 8           # window of the speed estimate
FAST_BOX = 24          # 3 ms, fast filter for the edge positions
OVERSAMPLE = 16        # samples per bit for the character receiver
MAX_BOX = int(RATE / 40) + 1   # longest bit filter (below 45.45 Bd)
VIZ_HOLD = 4.0         # s: the tuning indicators get data only while the page keeps asking (every ~2 s)
VIZ_EVERY = 0.1        # s between two indicator events
SPEC_N = 1024          # FFT of the mini waterfall (about 7.8 Hz per bin, 128 ms)
# Squelch per character: the mean |decision| over its 7 bits after the ATC. Measured on synthetic contest bursts
# (3-12 dB): characters of a signal 0.77-0.92 (10th percentile 0.6), of the noise in the pauses 0.33-0.37.
# With hysteresis: the squelch opens at CLEAR_OPEN, while open it lets through down to CLEAR_LOW (weak or faded
# characters of a running over) and closes after SQ_CLOSE weaker characters in a row.
CLEAR_OPEN = 0.55
CLEAR_LOW = 0.42
SQ_CLOSE = 2
CLEAR_SURE = 0.7
GOOD_RUN = 8           # a character is "sure" when the last this many frames of its receiver were all correct
# Not Baudot (synchronous / encrypted FSK data): a strong signal whose frames keep failing. Random bits pass the stop
# bit check about half the time (measured 0.43-0.6), real Baudot ~1.0 (short dips while the speed changes).
SYNC_RATIO = 0.7       # correct frames of the last 40 below this ...
SYNC_CLEAR = 0.85      # ... and above this again
SYNC_SEC = 8           # ... for this many seconds in a row
SYNC_SNR_DB = 15       # only above this SNR (a weak Baudot signal also has framing errors)

# Known RTTY transmissions: (from kHz, to kHz, label, group, mode). Matched with the centre between the tones
# (the dial before lock). The page lists them; a click tunes USB so the signal sits in the passband:
# "centre" = one station (the range centre is its frequency), "segment" = an amateur band segment (its start).
STATIONS = [
    (147.0, 147.6, "DWD Pinneberg DDH47 147.3 kHz", "DWD weather, 50 Bd / 85 Hz", "centre"),
    (4582.0, 4584.0, "DWD Pinneberg DDK2 4583 kHz", "DWD weather, 50 Bd / 450 Hz", "centre"),
    (7645.0, 7647.0, "DWD Pinneberg DDH7 7646 kHz", "DWD weather, 50 Bd / 450 Hz", "centre"),
    (10099.8, 10101.8, "DWD Pinneberg DDK9 10100.8 kHz", "DWD weather, 50 Bd / 450 Hz", "centre"),
    (11038.0, 11040.0, "DWD Pinneberg DDH9 11039 kHz", "DWD weather, 50 Bd / 450 Hz", "centre"),
    (14466.3, 14468.3, "DWD Pinneberg DDH8 14467.3 kHz", "DWD weather, 50 Bd / 450 Hz", "centre"),
    (3580.0, 3600.0, "amateur RTTY 80 m", "Amateur RTTY, 45.45 Bd / 170 Hz", "segment"),
    (7040.0, 7050.0, "amateur RTTY 40 m", "Amateur RTTY, 45.45 Bd / 170 Hz", "segment"),
    (10140.0, 10150.0, "amateur RTTY 30 m", "Amateur RTTY, 45.45 Bd / 170 Hz", "segment"),
    (14080.0, 14099.0, "amateur RTTY 20 m", "Amateur RTTY, 45.45 Bd / 170 Hz", "segment"),
    (18095.0, 18109.0, "amateur RTTY 17 m", "Amateur RTTY, 45.45 Bd / 170 Hz", "segment"),
    (21080.0, 21120.0, "amateur RTTY 15 m", "Amateur RTTY, 45.45 Bd / 170 Hz", "segment"),
    (24910.0, 24929.0, "amateur RTTY 12 m", "Amateur RTTY, 45.45 Bd / 170 Hz", "segment"),
    (28050.0, 28150.0, "amateur RTTY 10 m", "Amateur RTTY, 45.45 Bd / 170 Hz", "segment"),
]


def station_at(hz):
    k = hz / 1000.0
    return next((s[2] for s in STATIONS if s[0] <= k <= s[1]), None)


def station_list():
    """For the page: where to tune for each known transmission."""
    return [{"name": name, "group": group, "kind": kind,
             "hz": round((lo + hi) / 2 * 1000) if kind == "centre" else round(lo * 1000)}
            for lo, hi, name, group, kind in STATIONS]


def _b64(a):
    return base64.b64encode(np.asarray(a, np.uint8).tobytes()).decode()

# ITA2 in the US variant (usual in amateur RTTY); code = bits in transmit order, LSB first.
LTRS = ["", "E", "\n", "A", " ", "S", "I", "U", "\r", "D", "R", "J", "N", "F", "C", "K",
        "T", "Z", "L", "W", "H", "Y", "P", "Q", "O", "B", "G", None, "M", "X", "V", None]
_FIG = {"E": "3", "A": "-", "S": "", "I": "8", "U": "7", "D": "$", "R": "4", "J": "'", "N": ",",
        "F": "!", "C": ":", "K": "(", "T": "5", "Z": '"', "L": ")", "W": "2", "H": "#", "Y": "6",
        "P": "0", "Q": "1", "O": "9", "B": "?", "G": "&", "M": ".", "X": "/", "V": ";"}
FIGS = [_FIG.get(c, c) for c in LTRS]
FIGS_CODE, LTRS_CODE = 27, 31


class _Uart:
    """Asynchronous character receiver for one polarity. Input: positive = mark, negative = space."""

    def __init__(self, sign):
        self.sign = sign
        self.events = collections.deque(maxlen=40)   # True = good character, False = framing error
        self.reset()

    def reset(self):
        self.pos = None          # None = waiting for the start bit
        self.prev = 1.0
        self.sampled = False     # a bit was sampled in the last step (eye diagram)
        self.acc = 0.0
        self.clear_ = 1.0
        self.figs = False
        self.events.clear()

    def step(self, v, T):
        """One sample; T = bit length in samples. Returns the character code, -1 on a framing error, otherwise None.
        The moving average delays the transition by half a bit, so the middle of bit k is at (k + 0.5)·T from the transition."""
        self.sampled = False
        if self.pos is None:
            if self.prev > 0 >= v:          # mark -> space: start of the start bit
                self.pos, self.k, self.bits = 0, 0, 0
            self.prev = v
            return None
        self.pos += 1
        if self.pos < (self.k + 0.5) * T:
            return None
        bit = v > 0
        self.sampled = True
        self.acc = (0.0 if self.k == 0 else self.acc) + min(abs(v), 1.0)
        if self.k == 0:
            if bit:                         # noise burst, not a start bit
                self.pos, self.prev = None, v
                return None
        elif self.k <= 5:
            self.bits |= int(bit) << (self.k - 1)
        else:                               # the stop bit must be mark
            self.pos, self.prev = None, v
            self.clear_ = self.acc / 7      # how clearly the tones decided the 7 bits (0..1; noise is lower)
            if self.clear_ < CLEAR_LOW:     # noise between the overs: not a character, not counted
                return NOISE
            self.events.append(bool(bit))
            return self.bits if bit else -1
        self.k += 1
        return None

    def decode(self, code):
        if code == FIGS_CODE:
            self.figs = True
            return ""
        if code == LTRS_CODE:
            self.figs = False
            return ""
        ch = (FIGS if self.figs else LTRS)[code]
        if ch == " ":
            self.figs = False               # unshift on space
        return "" if ch == "\r" else ch

    def score(self):
        return 2 * sum(self.events) - len(self.events)

    def sure(self):
        ev = list(self.events)[-GOOD_RUN:]
        return self.clear_ >= CLEAR_SURE and len(ev) >= GOOD_RUN // 2 and all(ev)


class RttyDecoder:
    def __init__(self, on_event):
        self.on_event = on_event
        self.enabled = False
        self.lock = threading.Lock()
        self.text = collections.deque(maxlen=8000)
        self.qual = collections.deque(maxlen=8000)   # "1" = sure character, "0" = recent framing errors
        self.dial = 0.0
        self.opts = {"shift": "auto", "baud": "auto", "polarity": "auto"}
        self.center = None       # Hz relative to the tuned frequency, centre between the tones
        self.shift = None
        self.baud = BAUDS[0]
        self.snr = 0.0
        self.present = False
        self.sel = 0
        self.band = (0.0, 0.0)
        self.focus_rf = None     # RF frequency (Hz) clicked in the mini waterfall: the AFC looks only around it
        self.viz_until = 0.0
        self._fs = None

    # ---------- control ----------

    def set_enabled(self, on):
        with self.lock:
            self.enabled = bool(on)
            self._fs = None
        self._emit_state()

    def clear(self):
        with self.lock:
            self.text.clear()
            self.qual.clear()

    def set_focus(self, hz):
        """hz: offset from the tuned frequency where to look for the tone pair, None = the whole passband."""
        with self.lock:
            self.focus_rf = None if hz is None else self.dial + float(hz)
            if self._fs:
                self._unlock()
        self._emit_state()

    def want_viz(self):
        self.viz_until = time.monotonic() + VIZ_HOLD

    def set_options(self, opts):
        """shift: "auto" or Hz; baud: "auto" or Bd; polarity: auto/normal/reverse."""
        with self.lock:
            o = dict(self.opts)
            if "shift" in opts:
                s = opts["shift"]
                o["shift"] = "auto" if s == "auto" else float(np.clip(float(s), 50, 1200))
            if "baud" in opts:
                b = opts["baud"]
                o["baud"] = "auto" if b == "auto" else float(np.clip(float(b), 30, 300))
            if opts.get("polarity") in ("auto", "normal", "reverse"):
                o["polarity"] = opts["polarity"]
            self.opts = o
            if o["baud"] != "auto":
                self.baud = o["baud"]
            if o["polarity"] != "auto":
                self.sel = 0 if o["polarity"] == "normal" else 1
            if self._fs:
                self._unlock()
        self._emit_state()

    def info(self):
        locked = self.center is not None
        std = None
        if locked:
            near = min(SHIFTS, key=lambda s: abs(s - self.shift))
            std = near if abs(near - self.shift) <= 15 else None
        return {
            "enabled": self.enabled, "present": self.present, "opts": self.opts,
            "snr_db": round(10 * np.log10(max(self.snr, 1e-3)), 1),
            "shift_hz": round(self.shift) if locked else None, "std_shift": std,
            "baud": self.baud, "polarity": "normal" if self.sel == 0 else "reverse",
            "mark_hz": round(self.dial + self.center + self.shift / 2) if locked else None,
            "space_hz": round(self.dial + self.center - self.shift / 2) if locked else None,
            "text": "".join(self.text), "q": "".join(self.qual),
            "figs": bool(self._fs and self.uarts[self.sel].figs),
            "sync": bool(self._fs and self.sync),
            "probing": bool(self._fs and not self.sync and self.sync_tried),
            "frames_ok": (round(sum(self.uarts[self.sel].events) / len(self.uarts[self.sel].events), 2)
                          if self._fs and self.uarts[self.sel].events else None),
            "focus_hz": None if self.focus_rf is None else round(self.focus_rf - self.dial),
            "station": station_at(self.dial + (self.center if locked else sum(self.band) / 2)),
        }

    # ---------- signal processing ----------

    def _setup(self, fs):
        self._fs = fs
        self.D = max(1, int(round(fs / RATE)))
        self.r = fs / self.D
        self.h = lowpass(0.45 * self.r, fs, 63)
        self.hist = np.zeros(len(self.h) - 1, np.complex64)
        self.dec_off = 0
        self.buf = np.zeros(0, np.complex64)
        self.since_afc = 0
        self.since_state = 0
        self.n = 0
        self.uarts = [_Uart(1), _Uart(-1)]
        self.baud_cand = None
        self.since_viz = 0
        self.std_seen = -10 ** 12    # sample index when a standard-shift pair was last found
        self.replay = False      # decode the buffered signal again from replay_from (new lock, signal back, new speed)
        self.replay_from = 0
        self.last_out = 0        # sample index up to which text was already written (not decoded twice)
        # after a new lock the text waits until the speed is confirmed: a corrected lock or speed then decodes the
        # start again instead of leaving garbage on the screen
        self.confirmed = True
        self.lock_n = 0          # sample index of the new lock, lock_from = where its replay starts
        self.lock_from = 0
        self.baud_ok = False     # the speed estimate agreed with the current speed since the lock
        self.pend_t, self.pend_q = "", ""
        self.viz_m, self.viz_s = [], []
        self.eye_d = collections.deque(maxlen=400)   # receiver input d (about 16 per bit) for the eye traces
        self.eye_i = 0                               # absolute index of the next d sample
        self.eye_at = []                             # indices of the bit decisions waiting for their trace
        self.eye_T = 16.0
        self.viz_peak = 1e-9
        self._unlock()

    def _unlock(self):
        """New tuning or settings: forget the tones, edges and unfinished characters."""
        self.center = self.shift = None
        self.present = False
        self.snr = 0.0
        # squelch state survives a corrected lock (the AFC moving to the over in progress: no new line there)
        self.sq_open, self.sq_weak = False, 0
        self.sq_run, self.sq_n = None, 0     # text held after the squelch opened (with its NEWLINE marker)
        self.sync = False        # the signal is not Baudot (synchronous data): its text is not written
        self.sync_bad = 0        # seconds in a row with too few correct frames
        self.sync_tried = {}     # Auto speed: frame ratio of each speed tried before saying "not Baudot"
        self._reset_demod()

    def _reset_demod(self):
        self.box_hist = {k: np.zeros(MAX_BOX - 1, np.complex128) for k in ("m", "s")}
        self.fast_hist = [np.zeros(FAST_BOX - 1, np.complex128) for _ in range(2)]
        self.u_off = 0
        self.fstate = 0
        self.atc = None          # ATC state: mark / space envelope and noise floor (at the receiver's samples)
        self.edges = collections.deque(maxlen=1000)
        for u in self.uarts:
            u.reset()

    def feed(self, base, fs, dial_hz, band):
        """base: complex baseband (tuned frequency = 0 Hz); band: (from, to) Hz to search for the tones."""
        if not self.enabled:
            return
        with self.lock:
            if fs != self._fs:
                self._setup(fs)
            if dial_hz != self.dial:
                self.dial = dial_hz
                self._unlock()
            self.band = band
            buf = np.concatenate((self.hist, base))
            self.hist = buf[-(len(self.h) - 1):]
            y = np.convolve(buf, self.h, mode="valid")[self.dec_off::self.D]
            self.dec_off = (self.dec_off - len(base)) % self.D
            self.buf = np.concatenate((self.buf, y))[-int(AFC_SEC * self.r):]
            self.since_afc += len(y)
            if self.since_afc >= self.r / 2:
                self.since_afc = 0
                self._afc(band)
                self._estimate_baud()
            pre, pq = self._replay(len(y))
            out, q = self._demod(y)
            out, q = pre + out, pq + q
            if not self.confirmed:
                self.pend_t += out
                self.pend_q += q
                out = q = ""
                age = (self.n - self.lock_n) / self.r
                if age >= CONFIRM_MAX or (age >= CONFIRM_MIN and (self.baud_ok or self.opts["baud"] != "auto")):
                    self.confirmed = True
                    out, q, self.pend_t, self.pend_q = self.pend_t, self.pend_q, "", ""
            if out:
                out, q = self._lines(out, q)
            if out:
                self.last_out = self.n + len(y)
            self.n += len(y)
            self.since_state += len(y)
            self.since_viz += len(y)
            if out:
                self.text.extend(out)
                self.qual.extend(q)
            viz = None
            if self.since_viz >= VIZ_EVERY * self.r:
                self.since_viz = 0
                if time.monotonic() < self.viz_until:
                    viz = self._viz()
                self.viz_m, self.viz_s = [], []
        if out:
            self.on_event("rttytext", {"t": out, "q": q})
        if viz:
            self.on_event("rttyviz", viz)
        if self.since_state >= self.r:
            self.since_state = 0
            with self.lock:
                self._check_sync()
            self._emit_state()

    def _afc(self, band):
        """Tone pair with a shift in the allowed range; keeps the current one while it is at least half as strong."""
        if len(self.buf) < NFFT:
            return
        segs = self.buf[-(len(self.buf) // NFFT) * NFFT:].reshape(-1, NFFT) * np.hanning(NFFT)
        p = np.fft.fftshift(np.mean(np.abs(np.fft.fft(segs, axis=1)) ** 2, axis=0))
        f = np.fft.fftshift(np.fft.fftfreq(NFFT, 1 / self.r))
        lo, hi = max(band[0], -0.45 * self.r), min(band[1], 0.45 * self.r)
        if self.focus_rf is not None:
            fc = self.focus_rf - self.dial
            w = (1000.0 if self.opts["shift"] == "auto" else self.opts["shift"] + 25) / 2 + 60
            if lo < fc < hi:                  # outside the passband (retuned): the whole passband
                lo, hi = max(lo, fc - w), min(hi, fc + w)
        sel = (f >= lo) & (f <= hi)
        if sel.sum() < 16:
            return
        ps = np.convolve(p, np.ones(5) / 5, mode="same")
        noise = float(np.median(p[sel])) + 1e-20
        peak = np.zeros_like(sel)
        peak[1:-1] = sel[1:-1] & (ps[1:-1] >= ps[:-2]) & (ps[1:-1] > ps[2:]) & (ps[1:-1] > MIN_SNR * noise)
        cand = np.flatnonzero(peak)
        cand = cand[np.argsort(ps[cand])[::-1][:10]]
        if self.opts["shift"] == "auto":
            smin, smax = 90.0, 1000.0
        else:
            smin, smax = self.opts["shift"] - 25, self.opts["shift"] + 25
        # With several stations in the passband (a contest) the tones of two stations also make a pair with an odd
        # shift: a pair with a standard shift wins unless it is much weaker than the best one.
        pairs = []
        for a in cand:
            for b in cand:
                if f[b] <= f[a] or not smin <= f[b] - f[a] <= smax:
                    continue
                pa, pb = ps[a], ps[b]
                if max(pa, pb) > 10 * min(pa, pb):
                    continue
                std = min(abs(f[b] - f[a] - x) for x in SHIFTS) <= STD_TOL
                pairs.append((min(pa, pb), a, b, std))
        top = max((p[0] for p in pairs), default=0.0)
        if any(p[3] and p[0] >= STD_PREFER * top for p in pairs):
            pairs = [p for p in pairs if p[3]]
        elif (self.center is not None and min(abs(self.shift - x) for x in SHIFTS) <= STD_TOL
              and self.n - self.std_seen < ODD_HOLD * self.r):
            # locked to a standard pair that went quiet (a contest station listening): keep it, but no text,
            # instead of jumping to a pair made of the tones of two other stations
            self.present = False
            self.snr = 0.0
            return
        best = keep = None
        for sc, a, b, _ in pairs:
            if best is None or sc > best[0]:
                best = (sc, a, b)
            if (self.center is not None and abs(f[a] - (self.center - self.shift / 2)) < 20
                    and abs(f[b] - (self.center + self.shift / 2)) < 20
                    and (keep is None or sc > keep[0])):
                keep = (sc, a, b)
        if best is None:
            self.present = False
            self.snr = 0.0
            return
        if keep is not None and keep[0] * 2 > best[0]:
            best = keep
        sc, a, b = best
        fa, fb = self._refine(ps, f, a), self._refine(ps, f, b)
        center, shift = (fa + fb) / 2, fb - fa
        if min(abs(shift - x) for x in SHIFTS) <= STD_TOL:
            self.std_seen = self.n
        self.snr = sc / noise
        if not self.present:
            self._want_replay()              # the start of the over came before the AFC saw it
        self.present = True
        if self.center is None or abs(center - self.center) > 15 or abs(shift - self.shift) > 15:
            self.center, self.shift = center, shift
            self._reset_demod()
            self._new_lock()
        else:
            self.center = 0.8 * self.center + 0.2 * center
            self.shift = 0.8 * self.shift + 0.2 * shift

    @staticmethod
    def _refine(ps, f, i):
        """Parabolic interpolation of the peak."""
        if 0 < i < len(ps) - 1:
            a, b, c = ps[i - 1], ps[i], ps[i + 1]
            d = a - 2 * b + c
            if d < 0:
                return float(f[i]) + 0.5 * (a - c) / d * (f[1] - f[0])
        return float(f[i])

    def _estimate_baud(self):
        """Speed from the lengths of the segments between edges: none is shorter than a bit and each is a multiple
        of half a bit (1.5 stop bits). Every signal fits double the speed (100 at 50 Bd),
        so we take the lowest that fits; a speed slower than the real one has too many short segments
        (single bits). The match is soft: the mean cosine of the segment lengths in half bits (1 = all exact);
        45.45 and 50 Bd differ by 10 %, so a hard tolerance cannot tell them apart over short segments (a 50 Bd
        signal also passes the frame check at 45.45). A change needs a clear margin over the current speed."""
        if self.opts["baud"] != "auto" or not self.present or self.sync_tried:
            return
        e = np.array(self.edges, float)
        e = e[e > self.n - EDGE_SEC * self.r]
        if len(e) < 16:
            return
        iv = np.diff(e) / self.r
        iv = iv[iv < 0.2]                     # long idle periods (mark) do not determine the speed
        if len(iv) < 12:
            return
        fits, short, ok = {}, {}, []
        for b in BAUDS:
            ub = iv * b                       # in bits
            fits[b] = float(np.mean(np.cos(4 * np.pi * ub)))
            short[b] = float(np.mean(ub < 0.72))   # 75 Bd relative to 50 is 0.67 bit
        base = min(short.values())            # short segments of noise, counted at every speed
        for b in BAUDS:
            if short[b] <= base + 0.15 and fits[b] >= 0.3:
                ok.append(b)
        if not ok:
            return
        b = ok[0]
        if len(ok) > 1 and ok[1] / b < 1.2 and fits[ok[1]] > fits[b]:
            b = ok[1]
        if b != self.baud and self.baud in fits and fits[b] < fits[self.baud] + 0.1:
            b = self.baud                     # not clearly better than the current speed
        if b == self.baud:
            self.baud_cand = None
            self.baud_ok = True
            return
        # a change is accepted after three matching estimates in a row
        self.baud_cand = (b, self.baud_cand[1] + 1) if self.baud_cand and self.baud_cand[0] == b else (b, 1)
        if self.baud_cand[1] >= 3:
            self.baud = b
            self.baud_cand = None
            for u in self.uarts:
                u.reset()
            self._want_replay()

    def _box(self, key, z, L):
        """|moving average| of length L for each new sample z."""
        h = self.box_hist[key]
        buf = np.concatenate((h, z))
        self.box_hist[key] = buf[-(MAX_BOX - 1):]
        c = np.concatenate(([0], np.cumsum(buf)))
        end = np.arange(len(h) + 1, len(buf) + 1)
        return np.abs(c[end] - c[end - L]) / L

    def _demod(self, y):
        if self.center is None:
            return "", ""
        t = (self.n + np.arange(len(y))) / self.r
        fm, fsp = self.center + self.shift / 2, self.center - self.shift / 2
        zm = y * np.exp(-2j * np.pi * ((fm * t) % 1.0))
        zs = y * np.exp(-2j * np.pi * ((fsp * t) % 1.0))
        L = int(np.clip(round(self.r / self.baud), FAST_BOX, MAX_BOX))
        m, s = self._box("m", zm, L), self._box("s", zs, L)
        d = (m - s) / (m + s + 1e-12)
        # fast filter: edge positions for the speed estimate (crossing ±0.3 with hysteresis)
        mf, sf = self._fast(zm, zs)
        df = (mf - sf) / (mf + sf + 1e-12)
        if self.present:
            q = np.where(df > 0.3, 1, np.where(df < -0.3, -1, 0))
            nz = np.flatnonzero(q)
            if nz.size:
                v = q[nz]
                prev = np.concatenate(([self.fstate], v[:-1]))
                ch = nz[(v != prev) & (prev != 0)]
                self.edges.extend((self.n + ch).tolist())
                self.fstate = int(v[-1])
        # character receiver: ~16 samples per bit
        k = max(1, int(self.r / (self.baud * OVERSAMPLE)))
        off = self.u_off
        du = d[off::k]
        self.u_off = (off - len(d)) % k
        T = self.r / k / self.baud
        out, qual = [], []
        auto = self.opts["polarity"] == "auto"
        viz = time.monotonic() < self.viz_until
        if viz:                               # tuning indicators: the tone envelopes at the receiver's samples
            self.viz_m.extend(m[off::k].tolist())
            self.viz_s.extend(s[off::k].tolist())
            self.eye_T = T
        sel = self.uarts[self.sel]
        du = self._atc(m[off::k], s[off::k], T)
        for v in du:
            for i, u in enumerate(self.uarts):
                code = u.step(v * u.sign, T)
                if viz and u is sel and u.sampled:
                    self.eye_at.append(self.eye_i)
                if code is None:
                    continue
                ch = u.decode(code) if code >= 0 else ""
                if i != self.sel:
                    continue
                gate = bool(ch) and self.present and not self.sync and not self.sync_tried and self._good(u)
                qq = "1" if u.sure() else "0"
                # squelch with hysteresis over the clarity of the characters (noise frames and framing errors count
                # as weak). Each opening = a new over (or another signal after a new lock): its text starts a new
                # line, but only once it has RUN_MIN characters; a shorter run (a key-up transient) is dropped.
                if code >= 0 and u.clear_ >= CLEAR_OPEN:
                    if not self.sq_open:
                        self.sq_run, self.sq_n = [(NEWLINE, "1")], 0
                    self.sq_open, self.sq_weak = True, 0
                elif self.sq_open:
                    self.sq_weak += 1
                    if self.sq_weak > SQ_CLOSE:
                        self.sq_open, self.sq_run = False, None
                if not self.sq_open:
                    continue
                if gate:
                    if self.sq_run is None:
                        out.append(ch)
                        qual.append(qq)
                    else:
                        self.sq_run.append((ch, qq))
                if self.sq_run is not None and gate:
                    self.sq_n += 1
                    if self.sq_n >= RUN_MIN:
                        for c0, q0 in self.sq_run:
                            out.append(c0)
                            qual.append(q0)
                        self.sq_run = None
            if viz:
                self.eye_d.append(v * sel.sign)
                self.eye_i += 1
        if auto:
            a, b = self.uarts[0].score(), self.uarts[1].score()
            if self.sel == 0 and b > a + 6:
                self.sel = 1
            elif self.sel == 1 and a > b + 6:
                self.sel = 0
        return "".join(out), "".join(qual)

    def _lines(self, out, q):
        """NEWLINE markers -> a new line, unless the text is already at the start of one."""
        if NEWLINE not in out:
            return out, q
        prev = self.text[-1] if self.text else "\n"
        t, tq = [], []
        for c, cq in zip(out, q):
            if c == NEWLINE:
                if prev == "\n":
                    continue
                c = "\n"
            t.append(c)
            tq.append(cq)
            prev = c
        return "".join(t), "".join(tq)

    def _new_lock(self):
        """A new (or corrected) tone pair. Still unconfirmed: the held text goes and the replay starts where the
        first lock's did; otherwise a new over, decoded from the last written text."""
        if self.confirmed:
            self.lock_from = max(self.last_out, self.n - int(REPLAY_SEC * self.r))
        self.pend_t = self.pend_q = ""
        self.confirmed = False
        self.lock_n = self.n
        self.baud_ok = False
        self.replay, self.replay_from = True, self.lock_from

    def _want_replay(self):
        """Signal back or a new speed: decode again from the lock (unconfirmed) or from the last written text."""
        if not self.confirmed:
            self.pend_t = self.pend_q = ""
            self.replay_from = self.lock_from
        else:
            self.replay_from = max(self.last_out, self.n - int(REPLAY_SEC * self.r))
        self.replay = True

    def _replay(self, ny):
        """After a new lock, a returning signal or a new speed: the receiver starts over on the buffered
        signal since the last written text (at most REPLAY_SEC), so the first characters of an over are not lost.
        ny = the newest samples at the end of the buffer, decoded right after."""
        if not self.replay or self.center is None:
            return "", ""
        self.replay = False
        k = int(min(len(self.buf) - ny, self.n - self.replay_from))
        if k <= int(self.r / self.baud) * 8:
            return "", ""
        self._reset_demod()
        n0 = self.n
        self.n -= k                           # the buffered samples just before y, in their own time
        try:
            return self._demod(self.buf[len(self.buf) - ny - k:len(self.buf) - ny])
        finally:
            self.n = n0

    def _atc(self, mu, su, T):
        """Decision value with automatic threshold correction (Kok Chen's optimal ATC, as in fldigi): each tone
        has its own envelope (fast attack, slow decay) and noise floor (fast fall, slow rise); the threshold moves to
        the middle between the two tone levels, so a selectively faded tone still decides right. Output about -1..1."""
        a = self.atc
        if a is None:
            m0, s0 = float(mu[0]) if len(mu) else 0.0, float(su[0]) if len(su) else 0.0
            a = self.atc = [m0, s0, min(m0, s0), min(m0, s0)]
        me, se, mn, sn = a
        fa, fd = 4.0 / T, 1.0 / (16 * T)        # envelope: attack a quarter bit, decay 16 bits
        na, nd = 4.0 / T, 1.0 / (48 * T)        # noise: fall a quarter bit, rise 48 bits
        out = []
        for m, s in zip(mu.tolist(), su.tolist()):
            me += (m - me) * (fa if m > me else fd)
            se += (s - se) * (fa if s > se else fd)
            mn += (m - mn) * (na if m < mn else nd)
            sn += (s - sn) * (na if s < sn else nd)
            nf = min(mn, sn)
            mc = min(max(m, nf), me) - nf
            sc = min(max(s, nf), se) - nf
            ma, sa = me - nf, se - nf
            v = mc * ma - sc * sa - 0.5 * (ma * ma - sa * sa)
            out.append(v / (0.5 * (ma * ma + sa * sa) + 1e-20))
        a[:] = me, se, mn, sn
        return out

    def _viz(self):
        """Data of the tuning indicators (cross, mini waterfall, bars, eye) since the last event."""
        ev = {"figs": bool(self.uarts[self.sel].figs), "lock": self.center is not None, "present": self.present,
              "focus": None if self.focus_rf is None else round(self.focus_rf - self.dial)}
        # cross: mark and space envelope, against a slowly falling peak (0..255)
        if self.viz_m:
            mm, ss = np.array(self.viz_m), np.array(self.viz_s)
            self.viz_peak = max(float(max(mm.max(), ss.max())), self.viz_peak * 0.9)
            sc = 255 / max(self.viz_peak, 1e-9)
            ev["m"], ev["s"] = _b64(np.clip(mm * sc, 0, 255)), _b64(np.clip(ss * sc, 0, 255))
        # eye: d from one bit before to one bit after each decision of the selected receiver
        h = int(round(self.eye_T))
        n = 2 * h + 1
        first = self.eye_i - len(self.eye_d)
        traces, wait = [], []
        for i in self.eye_at:
            if i + h >= self.eye_i:
                wait.append(i)
            elif i - h >= first:
                traces.append([self.eye_d[j - first] for j in range(i - h, i + h + 1)])
        self.eye_at = wait[-50:]
        if traces:
            a = np.clip(np.round(np.array(traces[-60:]) * 127), -127, 127).astype(np.int8)
            ev["eye"] = {"n": n, "data": base64.b64encode(a.tobytes()).decode()}
        # mini waterfall over the passband, mark / space level and the tuning error from it
        lo, hi = max(self.band[0], -0.45 * self.r), min(self.band[1], 0.45 * self.r)
        if len(self.buf) >= SPEC_N and hi > lo:
            x = self.buf[-SPEC_N:] * np.hanning(SPEC_N)
            p = np.fft.fftshift(np.abs(np.fft.fft(x)) ** 2)
            f = np.fft.fftshift(np.fft.fftfreq(SPEC_N, 1 / self.r))
            sel = (f >= lo) & (f <= hi)
            db = 10 * np.log10(p[sel] + 1e-20)
            fb = f[sel]
            noise = float(np.median(db))
            ev["spec"] = {"lo": round(float(fb[0])), "hi": round(float(fb[-1])),
                          "data": _b64(np.clip((db - noise + 6) * 255 / 50, 0, 255))}
            if self.center is not None:
                fm, fs = self.center + self.shift / 2, self.center - self.shift / 2
                ev["fm"], ev["fs"] = round(float(fm), 1), round(float(fs), 1)
                win = min(40.0, self.shift / 3)
                err, lv = [], []
                for ft in (fm, fs):
                    w = np.flatnonzero(np.abs(fb - ft) <= win)
                    if w.size:
                        j = w[np.argmax(db[w])]
                        lv.append(round(float(db[j] - noise), 1))
                        err.append(self._refine(db, fb, j) - ft)
                    else:
                        lv.append(0.0)
                ev["lm"], ev["ls"] = lv
                ev["err"] = round(float(np.mean(err)), 1) if err else 0.0
        return ev

    def _fast(self, zm, zs):
        """Tone envelopes with a short (3 ms) filter; own history, independent of the bit length."""
        res = []
        for i, z in enumerate((zm, zs)):
            buf = np.concatenate((self.fast_hist[i], z))
            self.fast_hist[i] = buf[-(FAST_BOX - 1):]
            c = np.concatenate(([0], np.cumsum(buf)))
            res.append(np.abs(c[FAST_BOX:] - c[:-FAST_BOX]) / FAST_BOX)
        return res

    @staticmethod
    def _good(u):
        """Text is let through only while most of the recent characters have a correct frame (noise does not)."""
        ev = list(u.events)[-20:]
        return len(ev) < 4 or sum(ev) >= 0.6 * len(ev)

    def _check_sync(self):
        """Once a second: a strong signal with too few correct frames for SYNC_SEC seconds = not Baudot."""
        ev = list(self.uarts[self.sel].events) if self._fs else []
        if not self.present or len(ev) < 30:
            self.sync_bad = 0
            return
        ratio = sum(ev) / len(ev)
        if self.sync:
            if ratio > SYNC_CLEAR:
                self.sync, self.sync_bad = False, 0
                self.sync_tried = {}
            return
        if ratio > SYNC_CLEAR:
            self.sync_tried = {}             # a tried speed decodes: back to the automatic estimate
        strong = 10 * np.log10(max(self.snr, 1e-3)) >= SYNC_SNR_DB
        self.sync_bad = self.sync_bad + 1 if strong and ratio < SYNC_RATIO else 0
        if self.opts["baud"] == "auto" and self.sync_bad >= SYNC_SEC // 2:
            # maybe only a wrong speed: try the other ones (nearest first) before giving up
            if not self.sync_tried:
                self.sync_from = self.baud       # the measured speed: shown again if no speed decodes
            self.sync_tried[self.baud] = ratio
            left = sorted((b for b in BAUDS if b not in self.sync_tried), key=lambda b: abs(b - self.baud))
            if left:
                self._set_baud(left[0])
                return
            self._set_baud(self.sync_from)
            self.sync = True
            return
        if self.sync_bad >= SYNC_SEC:
            self.sync = True

    def _set_baud(self, b):
        self.baud = b
        self.baud_cand = None
        self.sync_bad = 0
        for u in self.uarts:
            u.reset()

    def _emit_state(self):
        i = self.info()
        del i["text"]
        self.on_event("rttystate", i)

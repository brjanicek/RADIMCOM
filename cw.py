"""CW (Morse) decoder and skimmer: several stations in the passband at once, soft decisions.

Chain (for each station = channel):
  decimation to 8 kHz -> noise blanker -> station search in the spectrum (Welch, last 6 s; one channel in SINGLE,
  up to MAX_CH in SKIMMER) -> mixing of each tone to 0 Hz -> CIC decimator to 500 Hz (2 ms steps; its nulls lie
  exactly where the other stations would alias) -> matched filter (Gaussian, width by the speed) -> fine tracking
  of the tone drift from the phase during the marks -> envelope.
Soft decisions:
  noise sigma from the envelope (20th percentile, Rayleigh) and the mark level A from the decoded marks with a Kalman
  filter on log A (QSB: its uncertainty grows during the pauses) -> log likelihood ratio mark/space per step
  (Rice vs Rayleigh, averaged over the uncertainty of A) -> 2-state Viterbi with a delayed decision (an optimal
  "debounce") -> mark and space lengths.
Timing and characters:
  an adaptive operator profile (log-normal lengths of dot, dash and the three gaps, each learned separately:
  hand keying, bug, Farnsworth) gives the probability of each element -> beam search over all ways to read the
  elements; a character is written when all likely readings agree on it, with a confidence 0..1.
"""
import collections
import math
import os
import re
import threading

import numpy as np
from scipy.ndimage import maximum_filter1d
from scipy.signal import lfilter
from scipy.special import i0e

from sdr import lowpass

RATE = 8000.0          # Hz, sample rate after decimation
R_CIC = 16             # CIC decimation -> 500 Hz, one step = 2 ms
H_CIC = np.convolve(np.convolve(np.ones(R_CIC), np.ones(R_CIC)), np.ones(R_CIC)) / R_CIC ** 3
NFFT = 4096            # station search resolution ≈ 2 Hz
AFC_SEC = 6            # spectrum window; even for slow CW it must contain several marks
MIN_SNR = 4.0          # peak-to-noise power ratio in the spectrum (≈ 6 dB) for a new station
KEEP_SNR = 2.5         # ... an existing station stays while it is above this
MAX_CH = 16            # stations decoded at once in SKIMMER
CH_SEP = 40.0          # Hz, two stations closer than this are one
MATCH_HZ = 20.0        # Hz, a spectrum peak this close belongs to an existing channel
PRIME_SEC = 3.0        # s of the buffered signal a new channel decodes first (the start is not lost)
MASK = ((80.0, 10.0), (250.0, 20.0))   # (Hz, dB): a peak this close and this much weaker than a stronger one is
                                        # its keying sideband or key click, not a station
DROP_SEC = 20.0        # s, a silent channel is removed (SKIMMER)
FOLLOW_LOST_SEC = 3.0  # s, auto-follow switches to another station after this long silence
WIDE_SPAN = 3400.0     # Hz, SKIMMER WIDE: searches ± this around the tuned frequency, whatever the filter
NB_SIGMA = 4.5         # noise blanker: sample amplitude × noise RMS
NB_MARK = 3.0          # ... and × the strongest mark level (whichever is higher)
NB_MAX_MS = 20         # longer bursts are a signal, not a crash, and are kept
MF_MAX = 400           # steps of matched filter history (enough for 5 WPM)
A_GRID = np.array([-1.0, 0.0, 1.0])   # mark levels tried around A, in sigmas of the Kalman estimate
KALMAN_Q = 0.15        # (log A)² per second: how fast the fading can change the level
KALMAN_R = 0.04        # (log A)² measurement noise of one mark
LLR_CLIP = 12.0
LLR_GAIN = 1.0         # weight of one 2 ms step of evidence (the steps are correlated by the matched filter)
PEN_C = 0.5            # Viterbi: cost of a key change = PEN_C + PEN_LOG·log(steps per element)
PEN_LOG = 0.0
BEAM = 12              # readings kept by the beam search
PLAUSIBLE = 8.0        # nats; readings less likely than best × e^-8 are dropped
TEXT_MAX = 4000        # characters kept per station (shown when its row is opened)
TEXT_TAIL = 300        # ... of them in the state sent once a second (the row shows the end of it)
LP_MIN = -9.0          # an element class less likely than this is not tried
Q_LO, Q_HI = 3.0, 8.0   # mark level / noise sigma: quality 0 at Q_LO, 1 at Q_HI (enters the confidence)
Q_DROP = 0.05          # characters made only of marks below this quality are noise blips (QSB troughs) and dropped

MORSE = {
    ".-": "A", "-...": "B", "-.-.": "C", "-..": "D", ".": "E", "..-.": "F", "--.": "G",
    "....": "H", "..": "I", ".---": "J", "-.-": "K", ".-..": "L", "--": "M", "-.": "N",
    "---": "O", ".--.": "P", "--.-": "Q", ".-.": "R", "...": "S", "-": "T", "..-": "U",
    "...-": "V", ".--": "W", "-..-": "X", "-.--": "Y", "--..": "Z",
    "-----": "0", ".----": "1", "..---": "2", "...--": "3", "....-": "4", ".....": "5",
    "-....": "6", "--...": "7", "---..": "8", "----.": "9",
    ".-.-.-": ".", "--..--": ",", "..--..": "?", "-..-.": "/", "-...-": "=", ".-.-.": "+",
    "-....-": "-", "---...": ":", ".----.": "'", "-.--.-": ")", ".-..-.": '"',
    ".--.-.": "@", "...-.-": "<SK>", "-.-.-": "<KA>", "-.--.": "<KN>", "...-.": "<SN>",
    "........": "<HH>", "-.-.--": "!",
}
# Log prior of a character (not a language model: only how common the class is in CW traffic).
def _char_lp(c):
    if c == "*":
        return -5.0
    if c.startswith("<"):
        return -1.5
    if c.isalnum():
        return 0.0
    return -1.0


CALL_RE = re.compile(r"\b((?:[A-Z]{1,2}|[0-9][A-Z]|[A-Z][0-9])[0-9][A-Z]{1,4})(?:/[A-Z0-9]{1,3})?\b")
NOT_CALLS = {"5NN", "73", "CQ"}


def find_call(text):
    """Basic callsign spotting (no database): the call after DE, otherwise the last callsign-like word."""
    t = text[-80:]
    after_de = re.findall(r"\bDE\s+" + CALL_RE.pattern, t)
    if after_de:
        return after_de[-1]
    m = [c for c in CALL_RE.findall(t) if c not in NOT_CALLS]
    return m[-1] if m else None


def dot_from_marks(marks):
    """Dot length from mark lengths: the best split into short and long (on a log scale),
    dash = 3 dots. Returns (dot ms, share of marks that fit a dot or dash ±40 %),
    or None if there are too few marks or no two clear groups."""
    m = np.sort(np.log(np.asarray(marks, float)))
    if len(m) < 6:
        return None
    best, split = 0.0, None
    for k in range(1, len(m)):
        gap = m[k:].mean() - m[:k].mean()
        score = gap * k * (len(m) - k)
        if np.log(2) < gap < np.log(6) and score > best:
            best, split = score, k
    if split is None:
        return None
    dit = np.exp(m[:split].mean())
    dah = np.exp(m[split:].mean())
    dot = float((dit * split + dah / 3 * (len(m) - split)) / len(m))
    err = np.minimum(np.abs(m - np.log(dot)), np.abs(m - np.log(3 * dot)))
    return dot, float(np.mean(err < np.log(1.4)))


def _conf_digits(conf):
    return "".join(str(min(9, int(v * 10))) for v in conf)


def _logsumexp(v):
    m = max(v)
    return m + math.log(sum(math.exp(x - m) for x in v))


# ---------- operator profile (timing) ----------

class Profile:
    """Log-normal model of the five lengths; each learned from the elements decoded with high confidence."""
    MARKS = (("dit", 0.55), ("dah", 0.45))
    SPACES = (("ie", 0.6), ("ic", 0.3), ("iw", 0.1))

    def __init__(self, dot_ms):
        self.reset(dot_ms)

    def reset(self, dot_ms):
        lg = math.log(dot_ms)
        self.mu = {"dit": lg, "dah": lg + math.log(3), "ie": lg, "ic": lg + math.log(3), "iw": lg + math.log(7)}
        self.sd = {"dit": 0.22, "dah": 0.22, "ie": 0.3, "ic": 0.3, "iw": 0.35}

    @property
    def dot(self):
        """Dot = half of the dot + element space period: does not depend on where the threshold cuts the edges."""
        return 0.5 * (math.exp(self.mu["dit"]) + math.exp(self.mu["ie"]))

    def post(self, dur, classes):
        """Log posteriors of the classes for a length (ms)."""
        lx = math.log(max(dur, 1.0))
        ll = [-0.5 * ((lx - self.mu[k]) / self.sd[k]) ** 2 - math.log(self.sd[k]) + math.log(p) for k, p in classes]
        z = _logsumexp(ll)
        return [x - z for x in ll]

    def update(self, key, dur, lp):
        if lp < math.log(0.85):
            return
        a = 0.1
        d = math.log(max(dur, 1.0)) - self.mu[key]
        self.mu[key] += a * d
        self.sd[key] = float(np.clip(math.sqrt((1 - a) * self.sd[key] ** 2 + a * d * d), 0.12, 0.45))
        mu = self.mu
        mu["dah"] = float(np.clip(mu["dah"], mu["dit"] + math.log(2.2), mu["dit"] + math.log(4.5)))
        mu["ie"] = float(np.clip(mu["ie"], mu["dit"] - math.log(2), mu["dit"] + math.log(2)))
        mu["ic"] = max(mu["ic"], mu["ie"] + math.log(1.8))
        mu["iw"] = max(mu["iw"], mu["ic"] + math.log(1.5))

    def fit_spaces(self, spaces):
        """The gap lengths from the recent gaps: the best split of the sorted log lengths into 2 or 3 groups
        (Farnsworth or a slow fist moves the character and word gaps far from 3 and 7 dots)."""
        x = np.sort(np.log(np.asarray(spaces, float)))
        n = len(x)
        if n < 12:
            return
        S = np.concatenate(([0.0], np.cumsum(x)))
        S2 = np.concatenate(([0.0], np.cumsum(x * x)))
        sse = lambda i, j: S2[j] - S2[i] - (S[j] - S[i]) ** 2 / (j - i)
        sd = lambda i, j: float(np.clip(math.sqrt(max(sse(i, j), 0) / (j - i)), 0.15, 0.45))
        mean = lambda i, j: (S[j] - S[i]) / (j - i)
        sep = lambda a, b, c: mean(b, c) - mean(a, b)
        # element gaps are the most common (≥ 3), then character gaps (≥ 2), word gaps (≥ 1)
        e2, k2 = min((sse(0, k) + sse(k, n), k) for k in range(3, n - 1))
        best3 = min(((sse(0, i) + sse(i, j) + sse(j, n), i, j) for i in range(3, n - 2) for j in range(i + 2, n)
                     if sep(0, i, j) > math.log(2.2) and sep(i, j, n) > math.log(1.5)), default=None)
        if best3 and best3[0] < 0.5 * e2:
            _, i, j = best3
            c = (mean(0, i), mean(i, j), mean(j, n))
            d = (sd(0, i), sd(i, j), sd(j, n))
        else:
            c = (mean(0, k2), mean(k2, n), None)
            d = (sd(0, k2), sd(k2, n), None)
        if c[1] - c[0] < math.log(2.2):
            return
        self.mu["ie"], self.mu["ic"] = float(c[0]), float(c[1])
        self.sd["ie"], self.sd["ic"] = d[0], d[1]
        if c[2] is not None:
            self.mu["iw"], self.sd["iw"] = float(c[2]), max(d[2], 0.25)
        self.mu["iw"] = max(self.mu["iw"], self.mu["ic"] + math.log(2.0))

    def word_thr(self):
        """Space length above which it is a word space (ms): between the character and the word gap."""
        return math.exp(0.5 * (self.mu["ic"] + self.mu["iw"]))

    def info(self):
        d = self.dot
        r = lambda k: round(math.exp(self.mu[k]) / d, 2)
        return {"dot_ms": round(d), "dit": r("dit"), "dah": r("dah"), "ie": r("ie"), "ic": r("ic"), "iw": r("iw")}


# ---------- one station ----------

class Channel:
    def __init__(self, cid, tone, tick_hz, now, snr):
        self.id = cid
        self.tone = float(tone)
        self.tick_hz = tick_hz
        self.tick_ms = 1000.0 / tick_hz
        self.phase = 0.0
        self.primed = False
        self.zi = np.zeros(len(H_CIC) - 1, complex)
        self.snr = snr
        self.present = True
        self.seen = now
        self.born = now
        self.mf_hist = np.zeros(MF_MAX, complex)
        self.env = collections.deque(maxlen=int(4 * tick_hz))
        self.sigma = None
        self.logA = None
        self.P = 1.0
        self.t = now
        self.t_mark = now
        self.acquired = False
        self.prof = Profile(60.0)
        self.marks = collections.deque(maxlen=24)
        self.spaces = collections.deque(maxlen=80)
        self.n_spaces = 0
        self.pending = []           # elements before the speed is known; decoded once it is
        self.n_marks = 0
        self.g = None
        self.g_dot = None
        # Viterbi
        self.m0, self.m1 = 0.0, -20.0
        self.bp = []
        self.ve = []
        self.vl = []
        self.state = 0
        self.run = 0
        self.run_e = []
        self.space_done = True
        # beam: (log p, text, symbol, quality of the symbol's weakest mark, qualities of the characters in text)
        self.beam = [(0.0, "", "", 1.0, ())]
        self.text = collections.deque(maxlen=TEXT_MAX)
        self.conf = collections.deque(maxlen=TEXT_MAX)
        self.out = []               # (char, confidence) emitted since the decoder last took them
        self.call = None
        self.last_char = now
        self.dits = collections.deque(maxlen=40)
        self.dahs = collections.deque(maxlen=40)

    @property
    def dot_ms(self):
        return self.prof.dot

    # ---------- signal ----------

    def _filter(self):
        dot = self.dot_ms if self.acquired else 40.0
        if self.g is None or abs(math.log(dot / self.g_dot)) > 0.15:
            sig = max(1.0, dot / 4 / self.tick_ms)
            half = min(int(math.ceil(3 * sig)), MF_MAX // 2 - 1)
            k = np.arange(-half, half + 1)
            g = np.exp(-0.5 * (k / sig) ** 2)
            self.g = g / g.sum()
            self.g_dot = dot
            # correlated steps: one step counts as 1/(noise-equivalent length) of an independent sample
            self.llr_scale = 1.0 / max(1.0, 2 * math.sqrt(math.pi) * sig)
            # noise power gain of CIC + matched filter (from the 8 kHz samples to the envelope)
            up = np.zeros(R_CIC * (len(self.g) - 1) + 1)
            up[::R_CIC] = self.g
            self.var_gain = float(np.sum(np.convolve(H_CIC, up) ** 2))
        return self.g

    def process(self, x, n0var):
        """x: 500 Hz samples of this station; n0var: noise variance of one 8 kHz sample (from the spectrum)."""
        n = len(x)
        if n == 0:
            return
        self.t += n / self.tick_hz
        g = self._filter()
        buf = np.concatenate((self.mf_hist[len(self.mf_hist) - (len(g) - 1):], x)) if len(g) > 1 else x
        out = np.convolve(buf, g, mode="valid")
        self.mf_hist = np.concatenate((self.mf_hist, x))[-MF_MAX:]
        e = np.abs(out)
        self.env.extend(e)
        if n0var:
            self.sigma = math.sqrt(n0var * self.var_gain / 2)      # Rayleigh sigma of the noise envelope
        if self.sigma is None or self.sigma <= 0:
            return
        if self.logA is None and self.present and len(self.env) >= self.tick_hz:
            q = float(np.percentile(np.fromiter(self.env, float), 95))
            if q > 4 * self.sigma:
                self.logA, self.P, self.t_mark = math.log(q), 0.3, self.t
        if self.logA is not None:
            self._track_tone(out, e)
        self._viterbi(self._llr(e), e)

    def _track_tone(self, out, e):
        """Fine tone tracking: the phase turn between steps during the marks = residual frequency offset."""
        m = e > 0.6 * math.exp(self.logA)
        pair = m[1:] & m[:-1]
        if pair.sum() < 8:
            return
        d = np.sum(out[1:][pair] * np.conj(out[:-1][pair]))
        df = float(np.angle(d)) * self.tick_hz / (2 * np.pi)
        self.tone += 0.25 * float(np.clip(df, -10, 10))

    def _llr(self, e):
        if self.logA is None or not self.present:
            return np.full(len(e), -3.0)
        s2 = self.sigma ** 2
        P = self.P + KALMAN_Q * (self.t - self.t_mark)        # uncertainty grows during the pause (fading)
        A = np.maximum(math.exp(self.logA) * np.exp(A_GRID * math.sqrt(min(P, 2.0))), 2.0 * self.sigma)
        z = e[:, None] * A[None, :] / s2
        lg = np.log(i0e(z)) + z - (A * A / (2 * s2))[None, :]
        mx = lg.max(axis=1)
        llr = mx + np.log(np.mean(np.exp(lg - mx[:, None]), axis=1))
        return np.clip(llr * (self.llr_scale * LLR_GAIN), -LLR_CLIP, LLR_CLIP)

    def _viterbi(self, llr, e):
        """2-state Viterbi; the decision is made a few dots later, when all paths agree."""
        dt = max(2.0, 1.5 * self.dot_ms / self.tick_ms)
        pen = PEN_C + PEN_LOG * math.log(dt)
        m0, m1, bp = self.m0, self.m1, self.bp
        for v in llr.tolist():
            a = m1 - pen
            b0 = a > m0
            n0 = a if b0 else m0
            c = m0 - pen
            b1 = c > m1
            n1 = (c if b1 else m1) + v
            mx = n0 if n0 > n1 else n1
            m0, m1 = n0 - mx, n1 - mx
            bp.append((b0, b1))
        self.m0, self.m1 = m0, m1
        self.ve.extend(e.tolist())
        lag = int(np.clip(2.5 * self.dot_ms / self.tick_ms, 25, 400))
        if len(bp) <= lag:
            return
        s = 1 if m1 > m0 else 0
        states = [0] * len(bp)
        for t in range(len(bp) - 1, -1, -1):
            states[t] = s
            if bp[t][s]:
                s = 1 - s
        k = len(bp) - lag
        self._commit(states[:k], self.ve[:k])
        del bp[:k]
        del self.ve[:k]

    def _commit(self, states, es):
        for s, ev in zip(states, es):
            if s == self.state:
                self.run += 1
                if s:
                    self.run_e.append(ev)
            else:
                self._end_run()
                self.state, self.run = s, 1
                self.run_e = [ev] if s else []
            if not s and not self.space_done and self.run * self.tick_ms > self.prof.word_thr():
                self._space(self.run * self.tick_ms, word=True)   # the last word is not kept waiting
                self.space_done = True

    def _end_run(self):
        dur = self.run * self.tick_ms
        if self.state:
            self._mark(dur, self.run_e)
            self.space_done = False
        else:
            if not self.space_done:
                self._space(dur)
            # full gap lengths (also those already written as a word space) for the gap model
            if self.n_marks and dur < 4 * math.exp(self.prof.mu["iw"]):
                self.spaces.append(dur)
                self.n_spaces += 1
                if self.acquired and self.n_spaces % 12 == 0:
                    self.prof.fit_spaces(self.spaces)
        self.run_e = []

    # ---------- elements ----------

    def _mark(self, dur, es):
        dot = self.dot_ms
        if dur > max(10 * dot, 600):       # a carrier or tuning, not a mark
            self._flush()
            return
        if dur < 0.25 * math.exp(self.prof.mu["dit"]):
            return                          # glitch
        v = np.sort(es) if len(es) else np.zeros(1)
        lvl = float(np.median(v[len(v) // 4: len(v) - len(v) // 4 or None]))
        q = float(np.clip((lvl / self.sigma - Q_LO) / (Q_HI - Q_LO), 0, 1)) if self.sigma else 1.0
        if self.logA is not None:     # far below the mark level (which follows the fading) = a noise blip
            q = min(q, float(np.clip((lvl / math.exp(self.logA) - 0.2) / 0.3, 0, 1)))
        if dur >= 0.5 * dot and len(es) >= 3:
            if lvl > 0:
                P = self.P + KALMAN_Q * (self.t - self.t_mark)
                if self.logA is None:
                    self.logA, P = math.log(lvl), 0.3
                k = P / (P + KALMAN_R)
                self.logA += k * (math.log(lvl) - self.logA)
                self.P = (1 - k) * P
                self.t_mark = self.t
        self.marks.append(dur)
        self.n_marks += 1
        if self.n_marks % 8 == 0 or (not self.acquired and self.n_marks >= 8 and len(self.spaces) >= 12):
            res = dot_from_marks(list(self.marks))
            if res and res[1] >= 0.8 and (not self.acquired or abs(math.log(res[0] / dot)) > math.log(1.4)):
                self.prof.reset(res[0])     # first estimate or a new speed (another station, QRQ)
                if not self.acquired:
                    self.acquired = True
                    self.prof.fit_spaces(self.spaces)
                    self.pending.append((1, dur, q))
                    for el in self.pending:
                        if el[0]:
                            self._classify_mark(el[1], el[2])
                        else:
                            self._classify_space(el[1])
                    self.pending = []
                    return
        if not self.acquired:
            self.pending = self.pending[-200:] + [(1, dur, q)]
            return
        self._classify_mark(dur, q)

    def _classify_mark(self, dur, q):
        lp = self.prof.post(dur, Profile.MARKS)
        if self.acquired:
            key = "dit" if lp[0] > lp[1] else "dah"
            self.prof.update(key, dur, max(lp))
            if max(lp) > math.log(0.9):
                (self.dits if key == "dit" else self.dahs).append(dur)
        self._beam_mark(lp, q)

    def _space(self, dur, word=False):
        if not self.acquired:
            if self.pending:
                self.pending.append((0, dur, 1.0))
            return
        self._classify_space(dur, word)

    def _classify_space(self, dur, word=False):
        lp = self.prof.post(dur, Profile.SPACES)
        if word or dur > self.prof.word_thr():
            lp = [-30.0, -30.0, 0.0]
        elif self.acquired:
            key = ("ie", "ic", "iw")[int(np.argmax(lp))]
            self.prof.update(key, dur, max(lp))
        self._beam_space(lp)
        if lp[2] > math.log(0.5):
            self._flush()

    # ---------- beam search over the readings ----------

    def _prune(self, hyps):
        merged = {}
        for h in hyps:
            k = (h[1], h[2])
            if k not in merged:
                merged[k] = h
            else:
                o = merged[k]
                best = h if h[0] > o[0] else o
                merged[k] = (float(np.logaddexp(o[0], h[0])),) + best[1:]
        best = sorted(merged.values(), key=lambda h: -h[0])[:BEAM]
        top = best[0][0]
        self.beam = [(h[0] - top,) + h[1:] for h in best]

    def _beam_mark(self, lp, q):
        new = []
        for p, txt, sym, sq, qs in self.beam:
            for el, lq in zip(".-", lp):
                if lq > LP_MIN:
                    new.append((p + lq, txt, (sym + el)[-8:], max(sq, q) if sym else q, qs))
        self._prune(new)

    def _beam_space(self, lp):
        new = []
        for p, txt, sym, sq, qs in self.beam:
            if not sym:
                new.append((p, txt + (" " if lp[2] > LP_MIN and txt and lp[2] >= max(lp) else ""), "", 1.0, qs))
                continue
            c = MORSE.get(sym, "*")
            if lp[0] > LP_MIN:
                new.append((p + lp[0], txt, sym, sq, qs))
            if lp[1] > LP_MIN:
                new.append((p + lp[1] + _char_lp(c), txt + c + "\x00", "", 1.0, qs + (sq,)))
            if lp[2] > LP_MIN:
                new.append((p + lp[2] + _char_lp(c), txt + c + "\x00 ", "", 1.0, qs + (sq,)))
        self._prune(new)
        self._commit_text()

    def _commit_text(self, final=False):
        """Writes the characters on which all likely readings agree (all of the best one if final).
        Confidence = share of the readings that agree × quality of the strongest mark of the character."""
        w = np.exp(np.array([h[0] for h in self.beam]))
        w /= w.sum()
        if final:
            cp = self.beam[0][1]
        else:
            cp = os.path.commonprefix([h[1] for h in self.beam if h[0] > -PLAUSIBLE])
            cp = cp[:cp.rfind("\x00") + 1]      # whole characters only (a prosign has several letters)
        if not cp:
            return
        qs = self.beam[0][4]
        n_chars = cp.count("\x00")
        pos = 0
        for i, tok in enumerate(cp.split("\x00")):
            end = pos + len(tok)
            if tok:
                q = qs[i] if i < n_chars and i < len(qs) else 1.0
                conf = float(sum(wi for wi, h in zip(w, self.beam) if h[1][pos:end] == tok))
                if q >= Q_DROP or not tok.strip():
                    self._emit(tok, conf * (0.3 + 0.7 * q))
                elif tok.startswith(" "):
                    self._emit(" ", 1.0)
            pos = end + 1
        self.beam = [(h[0], h[1][len(cp):], h[2], h[3], h[4][n_chars:]) for h in self.beam
                     if h[1].startswith(cp)] or [(0.0, "", "", 1.0, ())]

    def _flush(self):
        """End of a transmission or a word: the best reading of everything still open is written."""
        new = []
        for p, txt, sym, sq, qs in self.beam:
            if sym:
                c = MORSE.get(sym, "*")
                new.append((p + _char_lp(c), txt + c + "\x00 ", "", 1.0, qs + (sq,)))
            else:
                new.append((p, txt + " ", "", 1.0, qs))
        self._prune(new)
        self._commit_text(final=True)
        self.beam = [(0.0, "", "", 1.0, ())]

    def _emit(self, tok, conf):
        for c in tok:
            if c == " " and (not self.text or self.text[-1] == " "):
                continue                    # no leading or double spaces
            self.text.append(c)
            self.conf.append(conf)
            self.out.append((c, conf))
        self.last_char = self.t
        if tok.strip():
            self.call = find_call("".join(self.text)) or self.call

    # ---------- state ----------

    def key_type(self):
        """Paddle (keyer), bug or straight key from the jitter of the dots and dashes."""
        if len(self.dits) < 12 or len(self.dahs) < 8:
            return None
        cv = lambda v: float(np.std(np.log(np.asarray(v, float))))
        a, b = cv(self.dits), cv(self.dahs)
        if a < 0.12 and b < 0.12:
            return "paddle"
        if a < 0.12:
            return "bug"
        if a > 0.17:
            return "straight"
        return None

    def info(self, dial):
        p = self.prof.info()
        wpm = round(1200 / self.dot_ms)
        # Farnsworth: letters at full speed, longer gaps between them; effective speed from PARIS (31 dots + 19 gap units)
        farn = self.acquired and p["ic"] > 4.5
        eff = round(1200 / self.dot_ms * 50 / (31 + 4 * p["ic"] + p["iw"] + 0.0)) if farn else wpm
        return {"id": self.id, "tone_hz": round(self.tone), "freq_hz": round(dial + self.tone), "wpm": wpm,
                "eff_wpm": eff, "farnsworth": bool(farn), "snr_db": round(10 * math.log10(max(self.snr, 1e-3)), 1),
                "present": bool(self.present), "call": self.call, "key": self.key_type(), "acquired": self.acquired,
                "text": "".join(self.text)[-TEXT_TAIL:], "conf": _conf_digits(list(self.conf)[-TEXT_TAIL:]),
                "profile": p}


# ---------- decoder ----------

class CwDecoder:
    def __init__(self, on_event, mode="single"):
        self.on_event = on_event
        self.enabled = False
        self.lock = threading.RLock()     # info() is read from the web server thread while feed() runs
        self.text = collections.deque(maxlen=6000)
        self.conf = collections.deque(maxlen=6000)
        self.dial = 0.0
        self.mode = mode         # single = the strongest station, skimmer = all stations
        self.span = "filter"     # skimmer: search in the filter passband or WIDE (± WIDE_SPAN)
        self.follow_id = None    # station chosen by the user (None = automatic)
        self.channels = []
        self.cur = None
        self._next_id = 1
        self._fs = None
        self.noise_db = None

    # ---------- compatibility (log, TUNE): the followed station ----------

    @property
    def tone(self):
        return None if self.cur is None else self.cur.tone

    @property
    def dot_ms(self):
        return 60.0 if self.cur is None else self.cur.dot_ms

    @property
    def present(self):
        return self.cur is not None and self.cur.present

    # ---------- control ----------

    def set_enabled(self, on):
        with self.lock:
            self.enabled = bool(on)
            self._fs = None
        self._emit_state()

    def set_options(self, mode=None, span=None):
        with self.lock:
            if mode in ("single", "skimmer") and mode != self.mode:
                self.mode = mode
                self.follow_id = None
                if mode == "single" and self.cur is not None:
                    self.channels = [self.cur]
            if span in ("filter", "wide"):
                self.span = span
        self._emit_state()

    def follow(self, cid):
        """The user picks a station (id) or returns to automatic (None)."""
        with self.lock:
            self.follow_id = cid if any(c.id == cid for c in self.channels) else None
            if self.follow_id is not None:
                self._set_cur(next(c for c in self.channels if c.id == cid))
        self._emit_state()

    def clear(self):
        """CLR: the text and the whole station list. Stations still on the air are found again within 0.5 s,
        with empty text (a new channel does not decode the buffer from before the clear)."""
        with self.lock:
            self.text.clear()
            self.conf.clear()
            self.channels = []
            self.follow_id = None
            self.cur = None
            self.t_clear = getattr(self, "t", 0.0)
        self._emit_state()

    def channel_text(self, cid):
        """Whole text of one station (its row opened in the table), or None if it is gone."""
        with self.lock:
            ch = next((c for c in self.channels if c.id == cid), None)
            if ch is None:
                return None
            return {"id": cid, "text": "".join(ch.text), "conf": _conf_digits(ch.conf)}

    def info(self):
        with self.lock:
            return self._info()

    def _info(self):
        c = self.cur
        i = {
            "enabled": self.enabled, "mode": self.mode, "span": self.span,
            "follow": self.follow_id, "cur": None if c is None else c.id,
            "wpm": round(1200 / self.dot_ms), "present": bool(self.present),
            "snr_db": 0.0 if c is None else round(10 * math.log10(max(c.snr, 1e-3)), 1),
            "tone_hz": None if c is None else round(c.tone),
            "freq_hz": None if c is None else round(self.dial + c.tone),
            "channels": [ch.info(self.dial) for ch in sorted(self.channels, key=lambda ch: ch.tone)],
            "station": None if c is None else c.info(self.dial),
            "text": "".join(self.text),
            "conf": _conf_digits(self.conf),
        }
        return i

    # ---------- signal processing ----------

    def _setup(self, fs):
        self._fs = fs
        self.D = max(1, int(round(fs / RATE)))
        self.r = fs / self.D
        self.tick_hz = self.r / R_CIC
        self.h = lowpass(0.45 * self.r, fs, 63)
        self.hist = np.zeros(len(self.h) - 1, np.complex64)
        self.dec_off = 0
        self.cic_off = 0
        self.buf = np.zeros(0, np.complex64)
        self.since_afc = 0
        self.since_state = 0
        self.t = 0.0
        self.channels = []
        self._set_cur(None)
        self.follow_id = None
        self.hi = 0.0
        self.n0var = None
        self.t_clear = 0.0

    def feed(self, base, fs, dial_hz, band):
        """base: complex baseband (tuned frequency = 0 Hz); band: (from, to) Hz to search for stations."""
        if not self.enabled:
            return
        dial_hz = float(dial_hz)     # the receiver gives numpy numbers: they would leak into the JSON (numpy bool)
        band = (float(band[0]), float(band[1]))
        with self.lock:
            if fs != self._fs:
                self._setup(fs)
                self.dial = dial_hz
            if dial_hz != self.dial:
                # the stations stay where they are on the band: their offset from the new dial changes
                d = dial_hz - self.dial
                self.dial = dial_hz
                for ch in self.channels:
                    ch.tone -= d
                if abs(d) > 50:
                    self.buf = self.buf[:0]
            buf = np.concatenate((self.hist, base))
            self.hist = buf[-(len(self.h) - 1):]
            y = np.convolve(buf, self.h, mode="valid")[self.dec_off::self.D]
            self.dec_off = (self.dec_off - len(base)) % self.D
            y = self._blank(y)
            self.t += len(y) / self.r
            self.buf = np.concatenate((self.buf, y))[-int(AFC_SEC * self.r):]
            self.since_afc += len(y)
            if self.since_afc >= self.r / 2:
                self.since_afc = 0
                self._detect(self._band(band))
            self._channelize(y)
            self._forward()
            self.since_state += len(y)
        if self.since_state >= self.r:
            self.since_state = 0
            self._emit_state()

    def _band(self, band):
        lim = 0.45 * self.r
        if self.mode == "skimmer" and self.span == "wide":
            return (-min(WIDE_SPAN, lim), min(WIDE_SPAN, lim))
        return (max(band[0], -lim), min(band[1], lim))

    def _blank(self, y):
        """Noise blanker: short bursts far above the noise and the mark level (static crashes) are set to zero.
        Bursts longer than NB_MAX_MS are kept: that is a strong station, not a crash."""
        if len(y) < 32:
            return y
        a = np.abs(y)
        rms = np.sqrt(np.median(a * a) / np.log(2))       # complex noise: median |y|² = P·ln 2
        lim = max(NB_SIGMA * rms, NB_MARK * self.hi)
        over = a > lim
        if not over.any():
            return y
        pad = len(self.h) // self.D + 1
        over = np.convolve(over, np.ones(2 * pad + 1), mode="same") > 0
        edges = np.flatnonzero(np.diff(np.concatenate(([0], over.astype(np.int8), [0]))))
        y = y.copy()
        for s0, s1 in zip(edges[::2], edges[1::2]):
            if (s1 - s0) * 1000 / self.r <= NB_MAX_MS:
                y[s0:s1] = 0
        return y

    def _detect(self, band):
        """Stations = peaks of the Welch spectrum; existing channels are matched, new ones started, silent ones dropped."""
        if len(self.buf) < NFFT:
            return
        win = np.hanning(NFFT)
        segs = self.buf[-(len(self.buf) // NFFT) * NFFT:].reshape(-1, NFFT) * win
        p = np.fft.fftshift(np.mean(np.abs(np.fft.fft(segs, axis=1)) ** 2, axis=0))
        f = np.fft.fftshift(np.fft.fftfreq(NFFT, 1 / self.r))
        lo, hi = band
        sel = (f >= lo) & (f <= hi)
        if sel.sum() < 8:
            return
        ps = np.convolve(p, np.ones(5) / 5, mode="same")   # ±5 Hz, the tone is not exactly in one bin
        noise = float(np.median(p[sel])) + 1e-20
        self.noise_db = 10 * math.log10(noise)
        # noise variance of one sample: a bin of the Hann-windowed FFT has E|X|² = var·Σw²;
        # the median of a mean of K exponential values is ≈ (1 - 2/9K)³ of its mean
        k = len(segs)
        self.n0var = noise / (1 - 2 / (9 * k)) ** 3 / float(np.sum(win ** 2))
        # the strongest mark level for the noise blanker (amplitude after decimation, see _blank): a tone of amplitude a
        # gives a peak a²(Σw)² in the raw spectrum, × the key-down share (~0.4–0.5); also the mark levels of the channels
        lvl = math.sqrt(float(p[sel].max()) / 0.4) / float(np.sum(win))
        self.hi = max([lvl] + [math.exp(c.logA) for c in self.channels if c.logA is not None])
        df = f[1] - f[0]
        ratio = np.where(sel, ps / noise, 0.0)
        loc = maximum_filter1d(ratio, 2 * max(1, int(CH_SEP / 2 / df)) + 1)
        idx = np.flatnonzero(sel & (ratio == loc) & (ratio >= KEEP_SNR))
        cands = []
        for i in idx[np.argsort(-ratio[idx])]:
            fi = float(f[i])
            if 0 < i < len(ps) - 1:
                a, b, c = ps[i - 1], ps[i], ps[i + 1]
                d = a - 2 * b + c
                if d < 0:
                    fi += 0.5 * (a - c) / d * df
            cands.append([fi, float(ratio[i]), False])

        def masked(fx, rx):
            return any(abs(fx - c[0]) < hz and rx * 10 ** (db / 10) < c[1] for c in cands for hz, db in MASK)
        # existing channels
        for ch in self.channels:
            near = [c for c in cands if not c[2] and abs(c[0] - ch.tone) <= MATCH_HZ]
            if near:
                c = max(near, key=lambda c: c[1])
                c[2] = True
                ch.snr = c[1]
                if abs(c[0] - ch.tone) > 8:                # coarse correction (the fine one is in the channel)
                    ch.tone += 0.5 * (c[0] - ch.tone)
            else:
                j = int(np.argmin(np.abs(f - ch.tone)))
                ch.snr = float(ratio[max(j - 3, 0): j + 4].max()) if sel[j] else 0.0
            ch.present = bool(ch.snr >= KEEP_SNR and lo <= ch.tone <= hi and not masked(ch.tone, ch.snr))
            if ch.present:
                ch.seen = self.t
        # a mean of few segments has noise peaks far above the median: stricter until the spectrum is averaged
        min_snr = MIN_SNR * (1 + 1 / math.sqrt(k))
        new = [c for c in cands if not c[2] and c[1] >= min_snr and not masked(c[0], c[1])
               and all(abs(c[0] - ch.tone) > CH_SEP for ch in self.channels)]
        if self.mode == "skimmer":
            self.channels = [ch for ch in self.channels if (self.t - ch.seen < DROP_SEC or ch is self.cur)
                             and lo - 50 <= ch.tone <= hi + 50]
            # two channels that the tone tracking pulled onto one station: the followed or older one stays
            keep = []
            for ch in sorted(self.channels, key=lambda c: (c is not self.cur, c.born)):
                if all(abs(ch.tone - o.tone) > CH_SEP / 2 for o in keep):
                    keep.append(ch)
            self.channels = sorted(keep, key=lambda c: c.born)
            for c in new:
                if len(self.channels) >= MAX_CH:
                    break
                self._add(c[0], c[1])
        else:
            cur = self.channels[0] if self.channels else None
            best = max(cands, key=lambda c: c[1]) if cands else None
            if cur is not None and not (lo <= cur.tone <= hi):
                cur = None
            if best is not None and best[1] >= min_snr and (
                    cur is None or (not best[2] and (best[1] > 2 * cur.snr or not cur.present))):
                self.channels = []
                cur = self._add(best[0], best[1])
            self.channels = [cur] if cur is not None else []
        self._auto_follow()

    def _add(self, tone, snr):
        ch = Channel(self._next_id, tone, self.tick_hz, self.t, snr)
        self._next_id += 1
        self.channels.append(ch)
        return ch

    def _auto_follow(self):
        if self.follow_id is not None:
            c = next((c for c in self.channels if c.id == self.follow_id), None)
            if c is not None:
                self._set_cur(c)
                return
            self.follow_id = None
        cur = self.cur if self.cur in self.channels else None
        if cur is not None and (cur.present or self.t - cur.seen < FOLLOW_LOST_SEC):
            return
        live = [c for c in self.channels if c.present]
        self._set_cur(max(live, key=lambda c: c.snr) if live else cur)

    def _set_cur(self, ch):
        if ch is self.cur:
            return
        if self.text and self.text[-1] != "\n":
            self.text.append("\n")
            self.conf.append(1.0)
            self.on_event("cwtext", {"t": "\n", "c": [9]})
        self.cur = ch

    def _channelize(self, y):
        n = len(y)
        for c in self.channels:
            if not c.primed:          # a new station: first the last seconds from the buffer
                c.primed = True
                prime = min(PRIME_SEC, self.t - n / self.r - self.t_clear)     # nothing from before CLR
                h = self.buf[:len(self.buf) - n][-int(prime * self.r):] if prime > 0 else self.buf[:0]
                if len(h):
                    self._run([c], h, (self.cic_off + len(h)) % R_CIC)
        if self.channels and n:
            self._run(self.channels, y, self.cic_off)
        self.cic_off = (self.cic_off - n) % R_CIC

    def _run(self, chs, y, off):
        n = len(y)
        steps = np.array([-2 * np.pi * c.tone / self.r for c in chs])
        ph = np.array([c.phase for c in chs])
        z = y[None, :] * np.exp(1j * (ph[:, None] + steps[:, None] * np.arange(n)[None, :]))
        zf, zi = lfilter(H_CIC, 1.0, z, axis=1, zi=np.vstack([c.zi for c in chs]))
        zd = zf[:, off::R_CIC]
        for k, c in enumerate(chs):
            c.phase = float((ph[k] + steps[k] * n) % (2 * np.pi))
            c.zi = zi[k]
            c.process(zd[k], self.n0var)

    def _forward(self):
        """New characters of every station to the browser (cwchan, the table); those of the followed station also
        to the main text (cwtext: log, audio spectrum bubble)."""
        for ch in self.channels:
            if not ch.out:
                continue
            t = "".join(c for c, _ in ch.out)
            cf = [min(9, int(v * 10)) for _, v in ch.out]
            self.on_event("cwchan", {"id": ch.id, "t": t, "c": cf})
            if ch is self.cur:
                self.text.extend(t)
                self.conf.extend(v for _, v in ch.out)
                self.on_event("cwtext", {"t": t, "c": cf})
            ch.out = []

    def _emit_state(self):
        i = self.info()
        del i["text"], i["conf"]
        self.on_event("cwstate", i)

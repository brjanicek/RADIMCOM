"""NAVTEX decoder (SITOR-B, CCIR 476 / ITU-R M.476 FEC mode B) of one VFO.

NAVTEX sends maritime safety information: navigational and weather warnings, ice, search and rescue, forecasts. 518 kHz
(English), 490 kHz (national language) and 4209.5 kHz (HF NAVTEX); the same signal carries HF maritime safety
information on 6314, 8416.5, 12579, 16806.5, 19680.5, 22376 and 26100.5 kHz.

The signal: FSK 100 Bd, 170 Hz shift (the higher tone = 1, B). Each character is a 7-bit word with exactly four 1s (all
35 such words are used: a wrong bit is seen), its first bit the lowest. Mode B sends every character twice: the stream
alternates DX and RX positions and the RX copy of a character comes 5 positions after its DX one, so a character lost in
a fade is often taken from its other copy.

The decoder works on the baseband of the VFO (any mode, the tones anywhere within ±SEARCH_HZ of the tuned frequency):
  - AFC: the pair of tones 170 Hz apart with the most power over the noise, every half second over the last AFC_S;
  - two correlators over one bit (mark, space), d = (mark − space) / (mark + space); the bit clock follows the zero
    crossings of d;
  - the word boundary (and the polarity) where most of the last words have four 1s; lost when too few still have;
  - DX / RX: the parity of the positions whose word comes again 5 later; each character from its DX copy, else from the
    RX one (~ when both are wrong);
  - messages: "ZCZC B1B2B3B4" (B1 the station, B2 the subject, B3B4 the number) up to "NNNN".
"""
import collections
import re
import threading
import time

import numpy as np

from sdr import lowpass

BAUD = 100.0
SHIFT_HZ = 170.0
RATE = 8000.0               # Hz after the first decimation: the AFC searches here
SEARCH_HZ = 3000.0          # the tone pair is looked for within ± this of the tuned frequency
SUB = 4                     # the demodulator runs at RATE / SUB (20 samples per bit)
AFC_S = 3.0                 # s of signal for the AFC
AFC_EVERY_S = 0.5
AFC_NFFT = 2048             # ~3.9 Hz bins at 8 kHz
AFC_SNR_DB = 8.0            # the weaker tone this much over the noise median to lock
AFC_DIP_DB = 2.0            # both tones this much over the middle between them (live: a wide data signal at
                            # 4206.3 kHz had −2 dB and was locked on, the real NAVTEX +5.6 dB)
AFC_JUMP_HZ = 60.0         # a pair found this far from the lock is another signal: taken only when not in sync
AFC_PULL = 0.25             # nearer: the lock moves this part of the way (the estimate of 100 Bd FSK wanders ±20 Hz;
                            # the correlators do not mind, a new start of the demodulator would lose characters)
LOST_S = 8.0                # no pair for this long: unlocked
CLOCK_GAIN = 0.08           # how much of a zero crossing's timing error moves the bit clock
SYNC_WORDS = 20             # words checked for the word boundary
SYNC_OK = 0.9               # of them with four 1s to sync (live: 0.8 also took a wrong boundary after a fade) …
SYNC_LOST = 0.55            # … and fewer than this (over the last SYNC_WORDS) to lose it
DXRX_DELAY = 5              # positions between the DX and the RX copy of a character
PARITY_WINDOW = 60          # codes over which the DX parity is decided
MAX_TEXT = 20000            # characters of the live text kept
MAX_MSGS = 300
MSG_TIMEOUT_S = 60.0        # a message without NNNN ends this long after the signal was lost

# CCIR 476: code (first bit = lowest) -> letter; the control codes by name
LETTERS = {0x47: "A", 0x72: "B", 0x1D: "C", 0x53: "D", 0x56: "E", 0x1B: "F", 0x35: "G", 0x69: "H", 0x4D: "I",
           0x17: "J", 0x1E: "K", 0x65: "L", 0x39: "M", 0x59: "N", 0x71: "O", 0x2D: "P", 0x2E: "Q", 0x55: "R",
           0x4B: "S", 0x74: "T", 0x4E: "U", 0x3C: "V", 0x27: "W", 0x3A: "X", 0x2B: "Y", 0x63: "Z",
           0x78: "CR", 0x6C: "LF", 0x5A: "LTRS", 0x36: "FIGS", 0x5C: " ", 0x0F: "ALPHA", 0x33: "BETA", 0x66: "RQ",
           0x6A: "CH32"}
FIGURES = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "-?:$3!&#8\x07().,9014'57=2/6+"))
CODE_OF = {v: k for k, v in LETTERS.items()}
LOST = "~"                  # a character lost in both copies

SUBJECTS = {"A": "Navigational warning", "B": "Meteorological warning", "C": "Ice report",
            "D": "Search and rescue / piracy", "E": "Weather forecast", "F": "Pilot service", "G": "AIS",
            "H": "LORAN", "I": "Spare", "J": "GNSS", "K": "Other navaid", "L": "Navigational warning (more)",
            "T": "Test", "V": "Special service", "W": "Special service", "X": "Special service",
            "Y": "Special service", "Z": "No messages"}
FREQS = [(518000, "518", "international NAVTEX (English)"), (490000, "490", "national NAVTEX"),
         (4209500, "4209.5", "HF NAVTEX"), (6314000, "6314", "HF MSI"), (8416500, "8416.5", "HF MSI"),
         (12579000, "12579", "HF MSI"), (16806500, "16806.5", "HF MSI"), (19680500, "19680.5", "HF MSI"),
         (22376000, "22376", "HF MSI"), (26100500, "26100.5", "HF MSI")]
AUDIO_HZ = 1700.0           # a frequency key tunes USB this far below it (the tones at 1615 / 1785 Hz)
HEADER = re.compile(r"ZCZC ?([A-Z])([A-Z])(\d\d)")


def _weight(c):
    return bin(c).count("1")


VALID = np.array([_weight(c) == 4 for c in range(128)])


class _Fir:
    """A streaming FIR filter with decimation."""

    def __init__(self, h, dec):
        self.h = h.astype(np.complex64)
        self.dec = dec
        self.hist = np.zeros(len(h) - 1, np.complex64)
        self.off = 0

    def process(self, x):
        buf = np.concatenate((self.hist, x.astype(np.complex64)))
        self.hist = buf[-(len(self.h) - 1):]
        y = np.convolve(buf, self.h, mode="valid")[self.off::self.dec]
        self.off = (self.off - len(x)) % self.dec
        return y


class NavtexDecoder:
    """Text goes to on_event("navtextext", {"t"}), finished messages to on_event("navtex", msg), the state to
    on_event("navtexstate", info)."""

    def __init__(self, on_event):
        self.on_event = on_event
        self.enabled = False
        self.lock = threading.Lock()
        self.text = collections.deque(maxlen=MAX_TEXT)
        self.msgs = collections.deque(maxlen=MAX_MSGS)
        self.next_id = 1
        self.dial = 0.0
        self._fs = None
        self.chars = 0
        self.lost = 0

    # ---------- control ----------

    def configure(self, cfg):
        self.set_enabled(cfg.get("navtex", False))

    def apply(self, body, cfg):
        """The keys of POST /api/set; True when something changed (the caller saves config)."""
        if "navtex" not in body:
            return False
        self.set_enabled(bool(body["navtex"]))
        cfg["navtex"] = self.enabled
        return True

    def set_enabled(self, on):
        with self.lock:
            self.enabled = bool(on)
            self._fs = None
        self._emit_state()

    def clear(self):
        with self.lock:
            self.text.clear()
            self.msgs.clear()
            self.chars = self.lost = 0

    def status(self):
        """The fields of this decoder in the VFO state."""
        return {"navtex": self.enabled}

    def info(self):
        locked = self._fs is not None and self.center is not None
        return {"enabled": self.enabled, "locked": locked, "sync": bool(self._fs and self.sync),
                "tone_hz": round(self.dial + self.center) if locked else None,
                "offset_hz": round(self.center) if locked else None,
                "snr_db": round(self.snr_db, 1) if locked else None,
                "chars": self.chars, "lost": self.lost, "msgs": len(self.msgs),
                "in_msg": bool(self._fs and self.cur is not None)}

    # ---------- signal ----------

    def _setup(self, fs):
        self._fs = fs
        self.D = max(1, int(round(fs / RATE)))
        self.r = fs / self.D
        self.f1 = _Fir(lowpass(min(SEARCH_HZ + 300, 0.45 * self.r), fs, 8 * self.D + 1), self.D)
        self.r2 = self.r / SUB
        self.f2 = _Fir(lowpass(250.0, self.r, 8 * SUB + 1), SUB)
        self.T = self.r2 / BAUD                     # samples per bit at the demodulator
        self.L = int(round(self.T))
        self.buf = np.zeros(0, np.complex64)
        self.since_afc = 0
        self.since_state = 0
        self.n8 = 0                                 # samples at RATE so far
        self.nco = 0.0                              # the phase of the oscillator moving the tones to 0 Hz
        self._unlock()

    def _unlock(self):
        self.center = None
        self.snr_db = 0.0
        self.last_seen = time.monotonic()
        self._reset_demod()

    def _reset_demod(self):
        self.cm = np.zeros(self.L - 1, np.complex64)    # the correlators' history (one bit)
        self.cs = np.zeros(self.L - 1, np.complex64)
        self.n2 = 0                                 # demodulator samples so far
        self.d_prev = 0.0
        self.next_t = self.T / 2                    # where the next bit is sampled
        self.bits = []
        self.sync = False
        self.word_at = 0                            # bits since the last word boundary
        self.pol = 0
        self.valid = collections.deque(maxlen=SYNC_WORDS)
        self.codes = []                             # codes since the sync (absolute index = code_base + i)
        self.code_base = 0
        self.parity = None
        self.out_k = 0                              # the next DX index to write
        self.figs = False

    def feed(self, base, fs, dial_hz):
        """base: complex baseband (tuned frequency = 0 Hz) at sample rate fs."""
        if not self.enabled:
            return
        out, done = "", []
        with self.lock:
            if fs != self._fs:
                self._setup(fs)
            if dial_hz != self.dial:
                self.dial = dial_hz
                self._unlock()
                out += self._end_msg(done, "retuned")
            y = self.f1.process(np.asarray(base))
            self.buf = np.concatenate((self.buf, y))[-int(AFC_S * self.r):]
            self.since_afc += len(y)
            if self.since_afc >= AFC_EVERY_S * self.r:
                self.since_afc = 0
                self._afc()
            if self.center is not None:
                out += self._demod(y, done)
            self.n8 += len(y)
            if self.cur is not None and time.monotonic() - self.last_seen > MSG_TIMEOUT_S:
                out += self._end_msg(done, "signal lost")
            self.since_state += len(y)
            state = self.since_state >= self.r
            if state:
                self.since_state = 0
        if out:
            self.on_event("navtextext", {"t": out})
        for m in done:
            self.on_event("navtex", m)
        if state or done:
            self._emit_state()

    def _afc(self):
        """The tone pair 170 Hz apart with the most power over the noise (±SEARCH_HZ)."""
        x = self.buf
        if len(x) < AFC_NFFT:
            return
        n = len(x) // AFC_NFFT
        seg = x[-n * AFC_NFFT:].reshape(n, AFC_NFFT) * np.hanning(AFC_NFFT)
        p = np.fft.fftshift(np.mean(np.abs(np.fft.fft(seg, axis=1)) ** 2, axis=0))
        f = np.fft.fftshift(np.fft.fftfreq(AFC_NFFT, 1 / self.r))
        bw = self.r / AFC_NFFT
        k = max(1, int(round(40.0 / bw)))           # each tone's lobe at 100 Bd: ±~50 Hz
        ps = np.convolve(p, np.ones(2 * k + 1) / (2 * k + 1), mode="same")
        h = int(round(SHIFT_HZ / 2 / bw))
        inner = np.abs(f) <= SEARCH_HZ
        noise = float(np.median(ps[inner])) or 1e-12
        lo, hi = np.roll(ps, h), np.roll(ps, -h)    # the tone below / above each candidate centre
        score = np.minimum(lo, hi)
        score[score < ps * 10 ** (AFC_DIP_DB / 10)] = 0   # two tones with a dip between them, not one wide hump
        score[~inner] = 0
        score[: h + 1] = score[-h - 1:] = 0
        i = int(np.argmax(score))
        if self.center is not None:                 # the pair near the lock first (a fade, another signal elsewhere)
            near = np.abs(f - self.center) <= AFC_JUMP_HZ
            j = int(np.argmax(np.where(near, score, 0)))
            if score[j] >= noise * 10 ** (AFC_SNR_DB / 10):
                i = j
        snr = 10 * np.log10(max(score[i] / noise, 1e-9))
        if snr < AFC_SNR_DB:
            if self.center is not None and time.monotonic() - self.last_seen > LOST_S:
                self._unlock()
            return
        c = float(f[i])
        self.snr_db = float(snr)
        if self.center is None or (abs(c - self.center) > AFC_JUMP_HZ and not self.sync):
            self.last_seen = time.monotonic()
            self.center = c
            self._reset_demod()
        elif abs(c - self.center) <= AFC_JUMP_HZ:
            self.last_seen = time.monotonic()
            self.center += AFC_PULL * (c - self.center)

    def _demod(self, y, done):
        ph = self.nco + 2 * np.pi * self.center / self.r * np.arange(len(y))      # continuous when the AFC moves
        self.nco = float((ph[-1] + 2 * np.pi * self.center / self.r) % (2 * np.pi))
        z = self.f2.process(y * np.exp(-1j * ph).astype(np.complex64))
        if not len(z):
            return ""
        m = np.arange(self.n2, self.n2 + len(z))
        rot = np.exp(-1j * np.pi * SHIFT_HZ * m / self.r2).astype(np.complex64)
        self.n2 += len(z)
        zm = np.concatenate((self.cm, z * rot))            # the mark tone moved to 0 Hz
        zs = np.concatenate((self.cs, z * np.conj(rot)))   # the space tone moved to 0 Hz
        self.cm, self.cs = zm[-(self.L - 1):], zs[-(self.L - 1):]
        k = np.ones(self.L, np.float32)
        a = np.abs(np.convolve(zm, k, mode="valid"))
        b = np.abs(np.convolve(zs, k, mode="valid"))
        d = (a - b) / (a + b + 1e-12)
        out = ""
        T, half = self.T, self.T / 2
        prev = self.d_prev
        t = self.next_t
        for i, v in enumerate(d):
            if (v > 0) != (prev > 0):                       # a zero crossing: a bit boundary
                x = i - v / (v - prev) if v != prev else float(i)
                err = (x - (t - half)) % T
                if err > half:
                    err -= T
                t += CLOCK_GAIN * err
            prev = v
            if i >= t:
                t += T
                out += self._bit(1 if v > 0 else 0, done)
        self.d_prev = prev
        self.next_t = t - len(d)
        return out

    # ---------- words, DX / RX, characters ----------

    def _bit(self, b, done):
        self.bits.append(b)
        if len(self.bits) > 7 * (SYNC_WORDS + 2):
            del self.bits[:7]
        if not self.sync:
            if len(self.bits) >= 7 * SYNC_WORDS:
                return "".join(self._code(c, done) for c in self._find_sync())
            return ""
        self.word_at += 1
        if self.word_at < 7:
            return ""
        self.word_at = 0
        w = self.bits[-7:]
        c = sum((bit ^ self.pol) << j for j, bit in enumerate(w))
        self.valid.append(bool(VALID[c]))
        if len(self.valid) == SYNC_WORDS and sum(self.valid) < SYNC_LOST * SYNC_WORDS:
            out = self._flush(done)
            self.sync = False
            self.bits = []
            return out
        return self._code(c, done)

    def _find_sync(self):
        """The word boundary and polarity where most of the last words have four 1s -> the codes of those words
        (decoded too: nothing is lost before the sync), [] when there is none yet."""
        bits = np.array(self.bits[-7 * SYNC_WORDS:], np.uint8)
        best = None
        for pol in (0, 1):
            for off in range(7):
                nw = (len(bits) - off) // 7                 # every whole word: none is skipped (DX / RX pairs)
                ws = bits[off:off + 7 * nw].reshape(-1, 7) ^ pol
                codes = (ws * (1 << np.arange(7))).sum(axis=1)
                ok = float(np.mean(VALID[codes]))
                if best is None or ok > best[0]:
                    best = (ok, pol, off, codes)
        ok, pol, off, codes = best
        if ok < SYNC_OK:
            return []
        self.sync, self.pol = True, pol
        # the bits after the last whole word of that boundary start the next word
        self.word_at = (7 * SYNC_WORDS - off) % 7
        self.valid.clear()
        self.valid.extend(bool(VALID[c]) for c in codes)
        self.codes, self.code_base, self.parity, self.out_k = [], 0, None, 0
        self.figs = False                           # the shift before the gap is not known
        return [int(c) for c in codes]

    def _code(self, c, done):
        self.codes.append(c)
        idx = self.code_base + len(self.codes) - 1
        if self.parity is None or idx % PARITY_WINDOW == 0:
            self._decide_parity()
        out = ""
        if self.parity is None:
            return out
        if self.out_k < self.code_base:
            self.out_k = self.code_base
        if self.out_k % 2 != self.parity:
            self.out_k += 1
        while self.out_k + DXRX_DELAY <= idx:
            dx = self.codes[self.out_k - self.code_base]
            rx = self.codes[self.out_k + DXRX_DELAY - self.code_base]
            out += self._char(dx if VALID[dx] else rx if VALID[rx] else None, done)
            self.out_k += 2
        keep = PARITY_WINDOW + DXRX_DELAY + 2
        if len(self.codes) > 2 * keep:
            cut = len(self.codes) - keep
            self.codes = self.codes[cut:]
            self.code_base += cut
        return out

    def _decide_parity(self):
        cs = self.codes[-PARITY_WINDOW:]
        base = self.code_base + len(self.codes) - len(cs)
        if len(cs) < 2 * DXRX_DELAY + 6:
            return
        score = [0, 0]
        for i in range(len(cs) - DXRX_DELAY):
            if VALID[cs[i]] and cs[i] == cs[i + DXRX_DELAY]:
                score[(base + i) % 2] += 1
        if max(score) >= 3 and max(score) >= 2 * min(score):
            self.parity = 0 if score[0] > score[1] else 1

    def _char(self, c, done):
        self.chars += 1
        if c is None:
            self.lost += 1
            return self._put(LOST, done)
        s = LETTERS[c]
        if s == "LTRS":
            self.figs = False
            return ""
        if s == "FIGS":
            self.figs = True
            return ""
        if s in ("ALPHA", "BETA", "RQ", "CH32", "CR"):
            return ""
        if s == "LF":
            return self._put("\n", done)
        if s == " ":
            return self._put(" ", done)
        ch = FIGURES[s] if self.figs else s
        return self._put("" if ch == "\x07" else ch, done)

    # ---------- messages ----------

    cur = None

    def _put(self, ch, done):
        if not ch:
            return ""
        self.text.append(ch)
        self.last_seen = time.monotonic()
        if self.cur is not None:
            self.cur["text"] += ch
            self.cur["lost"] += ch == LOST
            if self.cur["text"].endswith("NNNN"):
                self.cur["text"] = self.cur["text"][:-4]
                self._end_msg(done, "")
            elif len(self.cur["text"]) > 20000:
                self._end_msg(done, "too long")
        else:
            tail = "".join(list(self.text)[-12:])
            m = HEADER.search(tail)
            if m and tail.endswith(m.group(0)):
                self._start_msg(m)
        return ch

    def _start_msg(self, m):
        st, subj, nr = m.group(1), m.group(2), m.group(3)
        self.cur = {"id": self.next_id, "time": time.time(), "freq_hz": self.dial + (self.center or 0.0),
                    "station": st, "subject": subj, "subject_name": SUBJECTS.get(subj, ""), "number": nr,
                    "header": f"{st}{subj}{nr}", "text": "", "lost": 0, "end": ""}
        self.next_id += 1

    def _end_msg(self, done, why):
        m, self.cur = self.cur, None
        if m is None:
            return ""
        m["text"] = m["text"].strip("\r\n ")
        m["end"] = why
        m["chars"] = len(m["text"])
        self.msgs.append(m)
        done.append(dict(m))
        return ""

    def _flush(self, done):
        """Sync lost: the characters waiting for their RX copy are written from their DX one."""
        out = ""
        if self.parity is not None:
            last = self.code_base + len(self.codes) - 1
            while self.out_k <= last:
                dx = self.codes[self.out_k - self.code_base]
                out += self._char(dx if VALID[dx] else None, done)
                self.out_k += 2
        return out

    def _emit_state(self):
        self.on_event("navtexstate", self.info())


def log_line(m):
    """One line of the daily log for a message (its lines joined by " / ")."""
    text = " / ".join(x.strip() for x in m["text"].splitlines() if x.strip())
    q = f" ({m['lost']} lost)" if m["lost"] else ""
    end = f" [{m['end']}]" if m["end"] else ""
    return (f"{m['freq_hz'] / 1e3:.1f} kHz ZCZC {m['header']} {m['subject_name'] or m['subject']}{q}{end} | {text}")


def register(app, decoder):
    """GET /api/navtex: the state, the live text, the messages and the frequencies; DELETE clears them."""
    from flask import jsonify, request

    @app.route("/api/navtex", methods=["GET", "DELETE"])
    def api_navtex():
        if request.method == "DELETE":
            decoder.clear()
            return jsonify(ok=True)
        with decoder.lock:
            return jsonify(dict(decoder.info(), text="".join(decoder.text), messages=list(decoder.msgs),
                                freqs=[{"hz": h, "label": lb, "note": nt} for h, lb, nt in FREQS],
                                subjects=SUBJECTS, audio_hz=AUDIO_HZ))


# ---------- encoder (tests) ----------

def encode_text(text, phasing=40):
    """The codes of a mode B transmission: phasing, then the text (letters / figures switched as needed), DX and RX
    interleaved (the RX copy DXRX_DELAY positions after the DX one)."""
    chars = []
    figs = False
    for ch in text:
        if ch == "\n":
            chars += [CODE_OF["CR"], CODE_OF["LF"]]
            continue
        if ch == " ":
            chars.append(CODE_OF[" "])
            continue
        if ch.isalpha():
            if figs:
                chars.append(CODE_OF["LTRS"])
                figs = False
            chars.append(CODE_OF[ch.upper()])
            continue
        letter = next((k for k, v in FIGURES.items() if v == ch), None)
        if letter is None:
            continue
        if not figs:
            chars.append(CODE_OF["FIGS"])
            figs = True
        chars.append(CODE_OF[letter])
    # stream: DX k at position 2k, RX at 2k + 1; the RX copy of DX k is at 2k + DXRX_DELAY = RX slot k + 2
    lag = (DXRX_DELAY - 1) // 2
    dx = [CODE_OF["RQ"]] * phasing + chars + [CODE_OF["ALPHA"]] * (lag + 4)
    rx = [CODE_OF["ALPHA"]] * (lag + phasing) + chars + [CODE_OF["ALPHA"]] * 4
    out = []
    for a, b in zip(dx, rx):
        out += [a, b]
    return out


def modulate(codes, fs, tone_hz, amp=1.0):
    """Complex baseband FSK of the codes (first bit lowest, 1 = the higher tone), centred on tone_hz."""
    bits = [(c >> j) & 1 for c in codes for j in range(7)]
    spb = fs / BAUD
    n = int(len(bits) * spb)
    idx = np.minimum((np.arange(n) / spb).astype(int), len(bits) - 1)
    f = tone_hz + (np.array(bits)[idx] * 2 - 1) * SHIFT_HZ / 2
    ph = 2 * np.pi * np.cumsum(f) / fs
    return (amp * np.exp(1j * ph)).astype(np.complex64)

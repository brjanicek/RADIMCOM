"""POCSAG pager decoder (512 / 1200 / 2400 Bd) of one VFO.

From the complex baseband of the VFO, independent of the listening mode and filter:
channel filter (±7 kHz) -> FM discriminator -> for each speed: low-pass -> slicer with an adaptive threshold
(midpoint of the signal envelope) -> bit clock (PLL of packet.py) -> both polarities -> framer.

Framer: hunts the sync codeword 0x7CD215D8 (≤ 2 wrong bits), then reads batches of 16 codewords (8 frames of two),
each a BCH(31,21) codeword + even parity. One and two wrong bits are corrected; a codeword that cannot be corrected
is counted and shown as `?` in its message. Address codeword: RIC = 18 address bits · 8 + frame number, function
bits 0–3. Message codewords carry 20 bits each: numeric (4-bit BCD, LSB first) or alphanumeric (7-bit ASCII,
LSB first). Which of the two is meant is not sent; it is guessed from the function bits and the characters.
"""
import collections
import threading
import time

import numpy as np

from packet import _Clock, _Disc, _Fir
from sdr import lowpass

SYNC = 0x7CD215D8
IDLE = 0x7A89C197
BAUDS = (512, 1200, 2400)
RATES = ("all", "512", "1200", "2400")
SYNC_ERR = 2                 # wrong bits allowed in the first sync codeword
SYNC_ERR_NEXT = 4            # ... in the sync codeword of a following batch
BATCH_BAD = 6                # codewords of a batch that cannot be corrected: the signal is lost (noise passes
                             # the BCH check with up to two corrected bits about every second codeword)
CHAN_HZ = 7000.0             # channel filter: 12.5 kHz channels, deviation ±4.5 kHz
ENV_TAU = 0.08               # s: smoothing of the envelope (slicer threshold)
DUP_SEC = 10.0               # the same message (RIC, function, text) again within this time is shown once
MAX_MSGS = 500
MAX_RICS = 500
NUMERIC = "0123456789*U -)("
GEN = 0x769                  # BCH(31,21) generator x^10+x^9+x^8+x^6+x^5+x^3+1


# ---------- codewords ----------

def _rem(v31):
    """Remainder of a 31-bit word divided by the generator (the syndrome)."""
    for i in range(30, 9, -1):
        if v31 & (1 << i):
            v31 ^= GEN << (i - 10)
    return v31


def bch_encode(data21):
    """32-bit codeword of 21 data bits (flag + 20 bits): 10 check bits and the even parity bit."""
    v = (data21 << 10) | _rem(data21 << 10)
    cw = v << 1
    return cw | (bin(cw).count("1") & 1)


def _syndrome_table():
    t1, t2 = {}, {}
    for i in range(31):
        t1[_rem(1 << i)] = 1 << i
    for i in range(31):
        for j in range(i + 1, 31):
            m = (1 << i) | (1 << j)
            t2.setdefault(_rem(m), m)
    return t1, t2


_T1, _T2 = _syndrome_table()


def correct(cw):
    """(codeword, number of corrected bits) or (None, 0) when it cannot be corrected."""
    v = cw >> 1
    s = _rem(v)
    if s == 0:
        return (v << 1) | (bin(v).count("1") & 1), 0
    if s in _T1:
        v ^= _T1[s]
        return (v << 1) | (bin(v).count("1") & 1), 1
    if s in _T2:
        v2 = v ^ _T2[s]
        if (bin(v2).count("1") + (cw & 1)) % 2 == 0:     # parity agrees: two errors, both in the BCH part
            return (v2 << 1) | (cw & 1), 2
    return None, 0


def _pop(x):
    return bin(x).count("1")


# ---------- message payload ----------

def _bits(words):
    """Message bits in the order sent; None for the bits of a codeword that could not be corrected."""
    out = []
    for w in words:
        out += [None] * 20 if w is None else [(w >> (19 - k)) & 1 for k in range(20)]
    return out


def _chars(bits, size):
    """Groups of `size` bits, LSB first; None for a group with a lost bit."""
    out = []
    for k in range(0, len(bits) - size + 1, size):
        g = bits[k:k + size]
        out.append(None if None in g else sum(b << i for i, b in enumerate(g)))
    return out


def numeric_text(words):
    return "".join("?" if c is None else NUMERIC[c] for c in _chars(_bits(words), 4)).rstrip()


def _alpha_chars(words):
    cs = _chars(_bits(words), 7)
    while cs and cs[-1] in (0, 3, 4, 23):            # NUL, ETX, EOT, ETB: end and fill of the message
        cs.pop()
    return cs


def alpha_text(words):
    out = []
    for c in _alpha_chars(words):
        if c is None:
            out.append("?")
        elif c == 10 or c == 13:
            out.append("\n" if c == 10 else "")
        elif 32 <= c < 127:
            out.append(chr(c))
        else:
            out.append(f"<{c:02X}>")
    return "".join(out)


def guess_kind(func, words):
    """'tone' (address only), 'alpha' or 'numeric'."""
    if not words:
        return "tone"
    cs = [c for c in _alpha_chars(words) if c is not None]
    if not cs:
        return "numeric" if func != 3 else "alpha"
    ok = sum(1 for c in cs if 32 <= c < 127 or c in (10, 13)) / len(cs)
    if func == 3:
        return "alpha" if ok >= 0.6 else "numeric"
    if func == 0:
        return "alpha" if ok == 1.0 and len(cs) >= 4 else "numeric"
    return "alpha" if ok >= 0.9 and len(cs) >= 3 else "numeric"


# ---------- framer ----------

class Framer:
    """Bits of one speed and polarity -> messages: list of dicts (ric, func, words, corrected, bad)."""

    def __init__(self):
        self.reg = 0
        self.batch = False
        self.n = 0              # bits of the codeword being read
        self.idx = 0            # 0..15 codewords of the batch, 16 = the sync codeword of the next batch
        self.cw = 0
        self.cur = None
        self.bbad = 0           # codewords of this batch that could not be corrected
        self.batches = 0
        self.bad = 0
        self.corrected = 0

    def feed(self, bits):
        out = []
        for b in bits:
            self.reg = ((self.reg << 1) | b) & 0xFFFFFFFF
            if not self.batch:
                if _pop(self.reg ^ SYNC) <= SYNC_ERR:
                    self.batch, self.n, self.idx, self.cw, self.bbad = True, 0, 0, 0, 0
                    self.batches += 1
                continue
            self.cw = ((self.cw << 1) | b) & 0xFFFFFFFF
            self.n += 1
            if self.n < 32:
                continue
            self.n = 0
            if self.idx == 16:
                if _pop(self.cw ^ SYNC) <= SYNC_ERR_NEXT:
                    self.idx, self.bbad = 0, 0
                    self.batches += 1
                else:                                   # end of the transmission
                    self._finish(out)
                    self.batch = False
                continue
            self._codeword(self.cw, self.idx, out)
            self.idx += 1
            if self.bbad >= BATCH_BAD:                  # noise: end of the transmission
                self._finish(out)
                self.batch = False
        return out

    def _codeword(self, raw, idx, out):
        if _pop(raw ^ IDLE) <= 2:
            self._finish(out)
            return
        cw, nfix = correct(raw)
        if cw is None:
            self.bad += 1
            self.bbad += 1
            if self.cur is not None:
                self.cur["words"].append(None)
                self.cur["bad"] += 1
            return
        self.corrected += nfix
        if cw == IDLE:
            self._finish(out)
        elif cw >> 31 == 0:                             # address codeword
            self._finish(out)
            self.cur = {"ric": (((cw >> 13) & 0x3FFFF) << 3) | (idx >> 1), "func": (cw >> 11) & 3,
                        "words": [], "corrected": nfix, "bad": 0, "addr_fix": nfix}
        elif self.cur is not None:                      # message codeword
            self.cur["words"].append((cw >> 11) & 0xFFFFF)
            self.cur["corrected"] += nfix

    def _finish(self, out):
        if self.cur is not None:
            m = self.cur
            while m["words"] and m["words"][-1] is None:   # lost codewords at the end: not text
                m["words"].pop()
            # an address with two corrected bits is as likely noise: shown only with a clean message after it
            if m["addr_fix"] < 2 or (m["words"] and not m["bad"]):
                out.append(m)
            self.cur = None


class _Path:
    """One speed: low-pass -> threshold at the envelope midpoint -> PLL -> framers of both polarities."""

    def __init__(self, fs, baud):
        self.baud = baud
        self.fs = fs
        self.lp = _Fir(lowpass(0.6 * baud, fs, 63))
        self.clock = _Clock(fs / baud)
        self.framers = (Framer(), Framer())            # normal, inverted
        self.hi = None
        self.lo = None

    def process(self, f):
        y = self.lp.process(f)
        if not len(y):
            return []
        a = min(1.0, len(y) / self.fs / ENV_TAU)
        hi, lo = float(np.percentile(y, 97)), float(np.percentile(y, 3))
        self.hi = hi if self.hi is None else self.hi + a * (hi - self.hi)
        self.lo = lo if self.lo is None else self.lo + a * (lo - self.lo)
        bits = self.clock.process(y - 0.5 * (self.hi + self.lo))
        out = []
        for inv, fr in enumerate(self.framers):
            for m in fr.feed(bits if not inv else [b ^ 1 for b in bits]):
                m["baud"], m["inverted"] = self.baud, bool(inv)
                out.append(m)
        return out

    @property
    def bad(self):
        return sum(f.bad for f in self.framers)

    @property
    def corrected(self):
        return sum(f.corrected for f in self.framers)

    @property
    def batches(self):
        return sum(f.batches for f in self.framers)


class PocsagDecoder:
    """POCSAG decoder of one VFO. Messages go to on_event("pocsag", ...), the state to on_event("pocsagstate", ...)."""

    def __init__(self, on_event, max_msgs=MAX_MSGS):
        self.on_event = on_event
        self.enabled = False
        self.lock = threading.Lock()
        self.opts = {"rate": "all"}
        self.msgs = collections.deque(maxlen=max_msgs)
        self.rics = {}
        self.next_id = 1
        self.ok = 0
        self.base = {"bad": 0, "corrected": 0, "batches": 0}
        self.last_rx = None
        self.dial = 0.0
        self._fs = None
        self.chan = None
        self.disc = None
        self.paths = []
        self.recent = collections.OrderedDict()
        self.since_state = 0.0

    # ---------- control ----------

    def set_enabled(self, on):
        with self.lock:
            self.enabled = bool(on)
            self._fs = None
        self._emit_state()

    def set_options(self, opts):
        with self.lock:
            if opts.get("rate") in RATES:
                self.opts = dict(self.opts, rate=opts["rate"])
                self._fs = None
        self._emit_state()

    def clear(self):
        with self.lock:
            self.msgs.clear()
            self.rics.clear()
            self.ok = 0
            self.base = self._counts()

    def command(self, body):
        if body.get("action") == "clear":
            self.clear()
        if isinstance(body.get("opts"), dict):
            self.set_options(body["opts"])

    def _counts(self):
        return {"bad": sum(p.bad for p in self.paths), "corrected": sum(p.corrected for p in self.paths),
                "batches": sum(p.batches for p in self.paths)}

    def info(self, msgs=True):
        with self.lock:
            c = self._counts()
            i = {"enabled": self.enabled, "opts": dict(self.opts), "ok": self.ok,
                 "bad": c["bad"] - self.base["bad"], "corrected": c["corrected"] - self.base["corrected"],
                 "batches": c["batches"] - self.base["batches"], "last_rx": self.last_rx,
                 "rates": [p.baud for p in self.paths]}
            if msgs:
                i["messages"] = list(self.msgs)
                i["rics"] = sorted(self.rics.values(), key=lambda r: -r["last"])
            return i

    # ---------- signal ----------

    def _setup(self, fs):
        old = self._counts()
        self._fs = fs
        self.chan = _Fir(lowpass(min(CHAN_HZ, 0.45 * fs), fs, 63), 1, np.complex64)
        self.disc = _Disc(fs)
        r = self.opts["rate"]
        self.paths = [_Path(fs, b) for b in BAUDS if r == "all" or r == str(b)]
        for k, v in old.items():                        # the counters go on across a rebuild
            self.base[k] -= v

    def feed(self, base, fs, dial_hz):
        if not self.enabled:
            return
        new = []
        with self.lock:
            if fs != self._fs:
                self._setup(fs)
            self.dial = dial_hz
            f = self.disc.process(self.chan.process(np.asarray(base, np.complex64)))
            now = time.time()
            for p in self.paths:
                for m in p.process(f):
                    rec = self._record(m, now)
                    if rec is not None:
                        new.append(rec)
            while self.recent and now - next(iter(self.recent.values())) > DUP_SEC:
                self.recent.popitem(last=False)
            self.since_state += len(base) / fs
        for m in new:
            self.on_event("pocsag", m)
        if new or self.since_state >= 1.0:
            self.since_state = 0.0
            self._emit_state()

    def _record(self, m, now):
        words = m["words"]
        kind = guess_kind(m["func"], words)
        alpha, numeric = alpha_text(words), numeric_text(words)
        text = alpha if kind == "alpha" else numeric if kind == "numeric" else ""
        key = (m["ric"], m["func"], text)
        if now - self.recent.get(key, -1e9) < DUP_SEC:
            return None
        self.recent[key] = now
        self.recent.move_to_end(key)
        rec = {"id": self.next_id, "time": now, "freq_hz": self.dial, "baud": m["baud"], "inverted": m["inverted"],
               "ric": m["ric"], "func": m["func"], "kind": kind, "text": text, "alpha": alpha, "numeric": numeric,
               "words": len(words), "corrected": m["corrected"], "bad": m["bad"]}
        self.next_id += 1
        self.ok += 1
        self.last_rx = now
        self.msgs.append(rec)
        r = self.rics.get(m["ric"]) or {"ric": m["ric"], "count": 0, "first": now}
        r.update(last=now, count=r["count"] + 1, func=m["func"], baud=m["baud"], kind=kind, text=text,
                 freq_hz=self.dial)
        if len(self.rics) >= MAX_RICS and m["ric"] not in self.rics:
            del self.rics[min(self.rics, key=lambda k: self.rics[k]["last"])]
        self.rics[m["ric"]] = r
        return rec

    def _emit_state(self):
        self.on_event("pocsagstate", self.info(msgs=False))


# ---------- encoder (tests) ----------

def encode(messages, preamble=576):
    """Bits of a POCSAG transmission: messages = [(ric, func, text, 'alpha' | 'numeric' | 'tone')]."""
    def payload(text, kind):
        if kind == "tone":
            return []
        if kind == "numeric":
            text += " " * (-len(text) % 5)              # numeric messages are filled with spaces
            bits = [((NUMERIC.index(ch) >> i) & 1) for ch in text for i in range(4)]
        else:
            bits = [((ord(ch) >> i) & 1) for ch in text + "\x04" for i in range(7)]
        bits += [0] * (-len(bits) % 20)
        return [sum(b << (19 - k) for k, b in enumerate(bits[j:j + 20])) for j in range(0, len(bits), 20)]

    cws = []
    for ric, func, text, kind in messages:
        frame = ric & 7
        while len(cws) % 16 != 2 * frame:
            cws.append(IDLE)
        cws.append(bch_encode(((ric >> 3) << 2) | func))
        cws += [bch_encode((1 << 20) | w) for w in payload(text, kind)]
        cws.append(IDLE)
    while len(cws) % 16:
        cws.append(IDLE)
    bits = [(k + 1) & 1 for k in range(preamble)]
    for b in range(0, len(cws), 16):
        for w in [SYNC] + cws[b:b + 16]:
            bits += [(w >> (31 - k)) & 1 for k in range(32)]
    return bits

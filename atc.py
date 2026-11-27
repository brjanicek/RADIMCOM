"""ATC speech to text: the voice of the airband (AM, 118–137 MHz) as text, with the callsigns of the aircraft in it.

Each transmission (audio between the squelch opening and closing) is transcribed by a local Whisper model fine-tuned on
ATC speech (faster-whisper, on the CPU, no cloud); the text goes to the page (the AD window shows it as a subtitle with
the callsigns coloured). Test 2026-11-26 on BRATISLAVA RADAR 134.475 MHz: a callsign said was matched to an aircraft
seen by ADS-B / FR24 in about 6 of 10 transmissions (data\\poznamky.md).

    on_audio (pcm, squelch) --> segments by the squelch --> queue --> worker: Whisper --> text --> callsigns --> event "atc"

Callsigns: the radio telephony of the airline ("Ryanair", "Speedbird", "German Cargo") + the flight number spelled
("two one zero five", "six whiskey alfa") -> the ICAO callsign as ADS-B sends it (RYR2105, BEL6WA). The telephony of
the airlines comes from OpenFlights (openflights_airlines.dat, https://openflights.org/data, Open Database License),
plus ALIAS for what controllers really say.

The Python packages (faster-whisper, in lib\\whisper by install_atc.py / the setup) and the model (~1.5 GB, downloaded
once into the Hugging Face cache) are optional: without them the ATC key reports what is missing.
"""
import collections
import csv
import os
import queue
import re
import sys
import threading
import time

import numpy as np
from flask import jsonify, request

MODEL = "jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper"
AIR_LO, AIR_HI = 117_975_000, 137_000_000      # the airband voice channels
GAP_S = 0.4               # squelch closed this long: the transmission is over (shorter = the text sooner)
MIN_S = 0.6               # shorter ones (a click of the squelch) are not transcribed
MAX_S = 30.0              # a longer one is cut (an open squelch would never end)
RATE = 16000              # Whisper wants 16 kHz mono
TARGET_DBFS = -20.0     # the voice for Whisper at this RMS, whatever the volume / AGC of the VFO
SILENCE_PEAK = 1         # as recorder.has_audio: a closed squelch gives exactly 0
HISTORY = 100
THREADS = 8               # CPU threads of the model (of 16; the receivers keep the rest); 8 vs 4: ~20 % faster
AIRLINES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openflights_airlines.dat")

# what controllers and pilots say besides (or instead of) the official telephony
ALIAS = {"BOX": ["german cargo"], "LOT": ["lot"], "CIM": ["cimber"], "RYR": ["ryanair", "ryan air"], "BEL": ["beeline"],
         "WZZ": ["wizz air", "wizzair", "wizz"], "SWR": ["swiss"], "TVS": ["smartwings", "skytravel"], "EZY": ["easy"],
         "GEC": ["lufthansa cargo"], "CSA": ["csa", "czech airlines"], "QTR": ["qatari"], "UAE": ["emirates"],
         "THY": ["turkish"], "AUA": ["austrian"], "DLH": ["lufthansa"], "BAW": ["speedbird"], "EIN": ["shamrock"],
         "KLM": ["klm"], "AFR": ["air france", "airfrans"], "EJU": ["alpine"], "EZS": ["topswiss"], "PGT": ["sunturk"],
         "AEE": ["aegean"], "ROT": ["tarom"], "SXS": ["sunexpress"], "WMT": ["wizz air malta", "wizz go"],
         "WUK": ["wizz go"], "RUK": ["bluejet"], "RYS": ["bluemax"], "LDM": ["lauda europe", "lauda"], "MAY": ["malta air"]}
# words of the phraseology: never taken for the telephony of an airline (some are, nearly: CONTRACT ~ contact)
ATC_WORDS = set("""climb climbing descend descending maintain maintaining flight level contact radar bratislava wien vienna
budapest praha prague heading turn left right direct proceed squawk speed knots runway cleared report roger wilco affirm
negative traffic information and to for the on at is it with via until approach tower ground center centre control
frequency decimal point thousand hundred feet miles nautical good morning day evening bye hello thank thanks you ready
request requesting expect after passing reaching vacating identified standby say again confirm correction cancel resume own
navigation inbound outbound hold holding final ils visual qnh transition altitude above below behind opposite same direction
separation rate minimum maximum or greater less number reduce increase mach due low high when we are on your copy that
this my your of in out off not no yes level flight distance from via route present position time over station
""".split())
WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "tree": "3", "four": "4", "fower": "4", "five": "5", "fife": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "niner": "9",
    "alpha": "A", "alfa": "A", "bravo": "B", "charlie": "C", "delta": "D", "echo": "E", "foxtrot": "F", "golf": "G",
    "hotel": "H", "india": "I", "juliet": "J", "juliett": "J", "kilo": "K", "lima": "L", "mike": "M", "november": "N",
    "oscar": "O", "papa": "P", "quebec": "Q", "romeo": "R", "sierra": "S", "tango": "T", "uniform": "U", "victor": "V",
    "whiskey": "W", "whisky": "W", "x-ray": "X", "xray": "X", "yankee": "Y", "zulu": "Z",
}


def lev(a, b):
    p = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        c = [i]
        for j, y in enumerate(b, 1):
            c.append(min(p[j] + 1, c[j - 1] + 1, p[j - 1] + (x != y)))
        p = c
    return p[-1]


def load_telephony():
    """{telephony (lower case): ICAO designator} from OpenFlights (active airlines win) + ALIAS (wins over both)."""
    tel = {}
    try:
        with open(AIRLINES, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
    except OSError:
        rows = []
    for active in ("N", "Y"):           # the active ones last: they overwrite a dead airline of the same telephony
        for r in rows:
            if len(r) < 8 or r[7] != active:
                continue
            icao, call = r[4].strip().upper(), r[5].strip().lower()
            if re.fullmatch(r"[A-Z]{3}", icao):
                ICAOS.add(icao)
            if re.fullmatch(r"[A-Z]{3}", icao) and call and call != "\\n" and len(call) >= 3 and call not in ATC_WORDS:
                tel[re.sub(r"\s+", " ", call)] = icao
    for icao, names in ALIAS.items():
        for n in names:
            tel[n] = icao
    return tel


ICAOS = set()                      # all ICAO airline designators (a callsign spelled: "foxtrot tango lima five four one")
TEL = load_telephony()
_BY_FIRST = collections.defaultdict(list)          # first letter -> telephonies (for the approximate match)
for _t in TEL:
    _BY_FIRST[_t[0]].append(_t)


def tokens(text):
    """[(norm, start, end, is_char)]: digits and the spelling alphabet -> characters (is_char), other words lower case."""
    out = []
    for m in re.finditer(r"[A-Za-z]+(?:-[A-Za-z]+)?|\d+", text):
        w = m.group(0)
        lw = w.lower()
        if w.isdigit():
            out.append((w, m.start(), m.end(), True))
        elif lw in WORDS:
            out.append((WORDS[lw], m.start(), m.end(), True))
        elif len(w) == 1:
            out.append((w.upper(), m.start(), m.end(), True))
        else:
            out.append((lw, m.start(), m.end(), False))
    return out


def _telephony(words):
    """The telephony these words are (exact, or one / two letters off), or None."""
    for cand in (" ".join(words), "".join(words)):
        if cand in TEL:
            return cand, True
    if any(w in ATC_WORDS for w in words):
        return None, False
    s = " ".join(words)
    lim = 1 if len(s) <= 6 else 2
    best = None
    for t in _BY_FIRST.get(s[0], ()):
        if abs(len(t) - len(s)) > lim:
            continue
        d = min(lev(s, t), lev(s.replace(" ", ""), t.replace(" ", "")))
        if d <= lim and (best is None or d < best[1]):
            best = (t, d)
    return (best[0], False) if best else (None, False)


def find_calls(text):
    """The callsigns in a transcript: [{"cs": "RYR2105", "tel": "ryanair", "start", "end" (in text), "exact"}]."""
    tk = tokens(text)
    calls, i = [], 0
    while i < len(tk):
        if tk[i][3]:
            i += 1
            continue
        hit = None
        for k in (3, 2, 1):
            w = tk[i:i + k]
            if len(w) < k or any(t[3] for t in w):
                continue
            j = i + k
            suf, end = "", None
            while j < len(tk) and tk[j][3] and len(suf) < 7:
                suf += tk[j][0]
                end = tk[j][2]
                j += 1
            if not suf or not suf[0].isdigit() or len(suf) > 6:
                continue
            tel, exact = _telephony([t[0] for t in w])
            if tel and (len(suf) >= 2 or exact):
                hit = ({"cs": TEL[tel] + suf, "suf": suf, "tel": tel, "start": tk[i][1], "end": end, "exact": exact}, j)
                if len(suf) < 2:        # "ups three": UPS3 is real, but a lone digit is often not a flight number
                    hit[0]["short"] = True
                break
        if hit:
            calls.append(hit[0])
            i = hit[1]
        else:
            i += 1
    return calls + _numbers(tk, calls)


# a number after these words is a level, heading, frequency…, not a flight number
NUM_BEFORE = set("level heading squawk runway decimal point speed knots qnh contact frequency mach altitude feet miles "
                 "flight wind degrees radial track minutes seconds".split())
NUM_AFTER = set("decimal point feet knots miles degrees thousand hundred nautical minutes".split())


def _numbers(tk, calls):
    """Flight numbers said without a telephony recognised ("four one seven eight"): {"cs": "", "suf", "num": True}.
    Only a page that knows the aircraft around can tell whose they are (atc.js); alone they are not callsigns.
    A designator spelled before the number ("foxtrot tango lima five four one") is the callsign FTL541 (exact when FTL
    is a known airline); two letters only ("foxtrot lima five four one", a letter swallowed) go as "pre" with the
    number, and the page looks for an aircraft with that number whose designator has those letters."""
    taken = [(c["start"], c["end"]) for c in calls]
    out, i = [], 0
    while i < len(tk):
        if not tk[i][3] or (i and tk[i - 1][3]):
            i += 1
            continue
        j, suf = i, ""
        while j < len(tk) and tk[j][3]:
            suf += tk[j][0]
            j += 1
        start, end = tk[i][1], tk[j - 1][2]
        before = tk[i - 1][0] if i else ""
        after = tk[j][0] if j < len(tk) else ""
        sp = re.fullmatch(r"([A-Z]{2,3})(\d[0-9A-Z]{0,4})", suf)
        if sp and before not in NUM_BEFORE and not any(s <= start < e for s, e in taken):
            pre, num = sp.groups()
            if len(pre) == 3:
                out.append({"cs": suf, "suf": num, "tel": "", "start": start, "end": end, "exact": pre in ICAOS,
                            "spelled": True})
            elif len(num) >= 2:
                out.append({"cs": "", "suf": num, "pre": pre, "tel": "", "start": start, "end": end, "exact": False,
                            "num": True})
            i = j
            continue
        if (3 <= len(suf) <= 6 and suf[0].isdigit() and before not in NUM_BEFORE and after not in NUM_AFTER
                and not any(s <= start < e for s, e in taken)):
            out.append({"cs": "", "suf": suf, "tel": "", "start": start, "end": end, "exact": False, "num": True})
        i = j
    return out


def airband(hz):
    return AIR_LO <= (hz or 0) <= AIR_HI


class AtcStt:
    def __init__(self, on_event, on_state):
        self.on_event = on_event          # on_event("atc", {transmission})
        self.on_state = on_state          # on_state() after a change of the state (the status of the VFO)
        self.enabled = False
        self.state = "off"                # off / loading / ready / busy / error
        self.error = ""
        self.model = None
        self.history = collections.deque(maxlen=HISTORY)
        self.q = queue.Queue(maxsize=8)
        self._buf, self._rate, self._hz, self._t0, self._quiet = [], 0, 0, 0.0, 0.0
        self.next_id = 1
        threading.Thread(target=self._worker, name="atc-stt", daemon=True).start()

    def status(self):
        return {"atc": self.enabled, "atc_state": self.state, "atc_error": self.error}

    def _notify(self):
        """The new state to the browsers; at the start of app.py (enable from the config) state() may not work yet."""
        try:
            self.on_state()
        except Exception:
            pass

    def set_enabled(self, on):
        self.enabled = bool(on)
        self._buf = []
        if on and self.model is None and self.state != "loading":
            self.state, self.error = "loading", ""
            threading.Thread(target=self._load, name="atc-model", daemon=True).start()
        elif not on:
            self.state = "off" if self.model is None else "ready"
        self._notify()

    def _load(self):
        # install_atc.py (the setup's optional task) puts faster-whisper into lib\whisper; appended, so that numpy & co.
        # of RADIMCOM's own Python stay first. A development copy may have it in its .venv instead.
        lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib", "whisper")
        if os.path.isdir(lib) and lib not in sys.path:
            sys.path.append(lib)
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            self.state, self.error = "error", "faster-whisper is not installed: run install_atc.bat in the RADIMCOM folder"
            self._notify()
            return
        try:
            try:      # from the cache, without asking the internet
                m = WhisperModel(MODEL, device="cpu", compute_type="int8", cpu_threads=THREADS, local_files_only=True)
            except Exception:
                m = WhisperModel(MODEL, device="cpu", compute_type="int8", cpu_threads=THREADS)   # first time: ~1.5 GB
            self.model = m
            self.state, self.error = "ready", ""
        except Exception as e:
            self.state, self.error = "error", f"model: {e}"
        self._notify()

    # ---------- audio of the VFO ----------

    def feed(self, audio, env, rate, hz, mode):
        """Every block of the demodulated voice of the VFO (sdr.Receiver.on_voice: float, before LPF / HPF and the
        volume), env = the squelch gain over the block (None = open): collected while the squelch is open."""
        if not self.enabled:
            return
        if mode != "AM" or not airband(hz):
            self._buf = []
            return
        x = audio.mean(axis=1) if audio.ndim == 2 else audio
        if env is not None:
            x = x * env[:len(x)] if len(env) >= len(x) else x * np.pad(env, (0, len(x) - len(env)), mode="edge")
        x = x.astype(np.float32)
        loud = x.size > 0 and float(np.abs(x).max()) > SILENCE_PEAK / 32768.0
        now = time.time()
        if loud:
            if not self._buf:
                self._t0, self._rate, self._hz = now, rate, hz
            self._buf.append(x)
            self._quiet = 0.0
            if sum(len(b) for b in self._buf) / rate >= MAX_S:
                self._flush()
        elif self._buf:
            self._quiet += x.size / rate
            self._buf.append(x)            # the short pauses inside stay
            if self._quiet >= GAP_S:
                self._flush()

    def _flush(self):
        buf, self._buf = self._buf, []
        secs = sum(len(b) for b in buf) / self._rate - self._quiet
        if secs < MIN_S:
            return
        seg = (np.concatenate(buf), self._rate, self._hz, self._t0, secs)
        try:
            self.q.put_nowait(seg)
        except queue.Full:                 # the CPU does not keep up: the oldest one goes
            try:
                self.q.get_nowait()
                self.q.put_nowait(seg)
            except queue.Empty:
                pass

    @staticmethod
    def _level(x):
        """(peak, rms) dBFS of the voice (the open squelch only)."""
        v = x[x != 0]
        if not v.size:
            return -120.0, -120.0
        return (round(20 * float(np.log10(max(float(np.abs(v).max()), 1e-6))), 1),
                round(10 * float(np.log10(max(float(np.mean(v * v)), 1e-12))), 1))

    @staticmethod
    def _to16k(x, rate):
        """16 kHz mono, its RMS at TARGET_DBFS (the level of the VFO does not matter; peaks limited)."""
        x = np.asarray(x, np.float32)
        n = max(1, int(round(rate / RATE)))
        if n > 1:                          # a short average against aliasing (the AM audio is only a few kHz wide)
            x = np.convolve(x, np.ones(n, np.float32) / n, mode="same")
        t_out = np.arange(int(len(x) * RATE / rate)) * (rate / RATE)
        y = np.interp(t_out, np.arange(len(x)), x).astype(np.float32)
        on = y != 0
        if on.any():
            y[on] -= float(np.mean(y[on]))           # DC of the AM demodulator
            rms = float(np.sqrt(np.mean(y[on] ** 2)))
            if rms > 1e-6:
                y *= 10 ** (TARGET_DBFS / 20) / rms
            y = np.tanh(y * 1.2) / np.tanh(1.2)       # soft limit of the peaks, no hard clipping
        return y.astype(np.float32)

    def _worker(self):
        while True:
            pcm, rate, hz, t0, secs = self.q.get()
            lvl = self._level(pcm)             # the level from the VFO (before the normalisation), in the history
            if self.model is None or not self.enabled:
                continue
            self.state = "busy"
            self._notify()                     # the ATC key blinks while transcribing
            t1 = time.time()
            try:
                segs, _ = self.model.transcribe(self._to16k(pcm, rate), language="en", beam_size=5, vad_filter=False,
                                                condition_on_previous_text=False)
                text = " ".join(s.text.strip() for s in segs).strip()
            except Exception as e:
                self.state, self.error = "error", f"transcription: {e}"
                self._notify()
                continue
            self.state = "ready"
            self._notify()
            if not text:
                continue
            d = {"id": self.next_id, "t": round(t0, 1), "hz": hz, "dur": round(secs, 1), "cpu": round(time.time() - t1, 1),
                 "peak": lvl[0], "rms": lvl[1], "text": text, "calls": find_calls(text)}
            self.next_id += 1
            self.history.append(d)
            self.on_event("atc", d)


def register(app, stt, on_change):
    @app.route("/api/atc", methods=["GET"])
    def api_atc():
        return jsonify(dict(stt.status(), history=list(stt.history)))

    @app.route("/api/atc", methods=["POST"])
    def api_atc_set():
        """{"on": bool}: ATC speech to text of this VFO on / off (kept in its config)."""
        body = request.get_json(force=True) or {}
        on = bool(body.get("on"))
        stt.set_enabled(on)
        on_change(on)
        return jsonify(stt.status())

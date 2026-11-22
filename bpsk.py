"""BPSK satellite telemetry decoder: 1200 / 2400 / 4800 / 9600 Bd from the complex baseband of the VFO.

  baseband -> carrier search (squaring: BPSK x^2 has a line at 2 fc) and Doppler track -> mix to 0 Hz -> low-pass
  -> resample to 8 samples / symbol -> symbol timing (Oerder & Meyr, |z|^2 at the symbol rate) -> differential
  detection d_k = Re(z_k z*_(k-1)) -> soft bits (positive = no phase change)
  -> framings, all tried on the same bits:
     AO-40 FEC  (FUNcube-1 AO-73, Nayif-1 EO-88, JY1Sat JO-97 ...: DBPSK 1200 Bd, 5200-symbol frames, funcube.py)
     AX.25      (HDLC with NRZI, plain or with the G3RUH scrambler: BPSK CubeSats at 1200 ... 9600 Bd, packet.py)

Differential detection needs no carrier phase: it is the DBPSK decoder and at the same time the NRZI decoder of AX.25,
and the 180° ambiguity of BPSK does not matter. The G3RUH descrambler is linear, so it can follow the NRZI step.

The decoder keeps the last WINDOW_S seconds of baseband and demodulates the whole window again every STEP_S seconds
(simple and robust against Doppler and fading); a frame found again in the next window is recognised by its time.
"""
import collections
import threading
import time

import numpy as np

import funcube
import packet
from sdr import lowpass

BAUDS = (1200, 2400, 4800, 9600)
SPS = 8                       # samples per symbol after resampling
WINDOW_S = 6.0                # a whole AO-40 frame (4.33 s at 1200 Bd) plus margin
STEP_S = 1.0
SEG_SYMS = 600                # carrier estimate per segment of this many symbols (0.5 s at 1200 Bd)
TIMING_SYMS = 128             # symbol timing averaged over this many symbols
CARRIER_TOL_HZ = 40.0         # carrier estimates of two segments 1 segment apart may differ this much (+2 % of baud)
# satellites known to send BPSK telemetry (downlink MHz, Bd, framing); the user tunes USB ~1.5 kHz below
SATS = [
    {"name": "FUNcube-1 (AO-73)", "f": 145935000, "baud": 1200, "framing": "AO-40"},
    {"name": "Nayif-1 (EO-88)", "f": 145940000, "baud": 1200, "framing": "AO-40"},
    {"name": "JY1Sat (JO-97)", "f": 145840000, "baud": 1200, "framing": "AO-40"},
]


def carrier_track(z, fs, baud, lo, hi):
    """Carrier frequency per segment from the line of z^2 at 2 fc within [lo, hi] Hz.
    Returns (centres of the segments in samples, frequencies Hz, line-to-noise ratios dB)."""
    seg = int(SEG_SYMS * fs / baud)
    seg = max(1024, min(seg, len(z)))
    nfft = 1 << int(np.ceil(np.log2(seg * 2)))
    f = np.fft.fftfreq(nfft, 1 / fs)
    band = (f >= 2 * lo) & (f <= 2 * hi)
    idx = np.flatnonzero(band)
    win = np.hanning(seg)
    cs, fr, q = [], [], []
    for s0 in range(0, len(z) - seg + 1, seg // 2):
        x = z[s0:s0 + seg]
        x = x / (np.mean(np.abs(x)) or 1)
        p = np.abs(np.fft.fft(x * x * win, nfft)) ** 2
        pb = p[idx]
        k = int(np.argmax(pb))
        i = idx[k]
        # parabolic interpolation of the peak
        a, b, c = p[i - 1], p[i], p[(i + 1) % nfft]
        den = a - 2 * b + c
        off = 0.5 * (a - c) / den if den else 0.0
        cs.append(s0 + seg / 2)
        fr.append((f[i] + off * fs / nfft) / 2)
        q.append(10 * np.log10(b / (np.median(pb) or 1e-30)))
    return np.array(cs), np.array(fr), np.array(q)


def demod(z, fs, baud, lo, hi, min_line_db=12.0):
    """Complex baseband z at fs, signal carrier between lo and hi Hz -> dict(soft, t_sym (s from the start of z),
    freq (Hz, mean), snr_db) or None when no carrier is seen."""
    z = np.asarray(z, np.complex64)
    if len(z) < fs * 0.5:
        return None
    cs, fr, q = carrier_track(z, fs, baud, lo, hi)
    # a segment counts when its line is strong and a segment that does not overlap it (2 or 4 steps away) sees the
    # carrier near the same frequency: noise peaks are random, a carrier (even with Doppler) is continuous
    tol = CARRIER_TOL_HZ + 0.02 * baud
    ok = np.zeros(len(fr), bool)
    for i in np.flatnonzero(q >= min_line_db):
        for j in (i - 2, i + 2, i - 4, i + 4):
            if 0 <= j < len(fr) and q[j] >= min_line_db and abs(fr[j] - fr[i]) < tol * abs(j - i) / 2:
                ok[i] = True
                break
    if not ok.any():
        return None
    cs, fr = cs[ok], fr[ok]
    n = np.arange(len(z))
    finst = np.interp(n, cs, fr) if len(cs) > 1 else np.full(len(z), fr[0])
    phase = 2 * np.pi * np.cumsum(finst) / fs
    x = z * np.exp(-1j * phase).astype(np.complex64)
    # low-pass and resample to SPS per symbol
    fs2 = SPS * baud
    taps = int(8 * fs / baud) | 1
    h = lowpass(0.75 * baud, fs, taps)
    from scipy.signal import oaconvolve
    y = oaconvolve(x, h, mode="same")
    t2 = np.arange(0, len(y) - 1, fs / fs2)
    y2 = (np.interp(t2, n, y.real) + 1j * np.interp(t2, n, y.imag)).astype(np.complex64)
    # symbol timing: phase of the symbol-rate component of |y|^2, per block, smoothed
    e = np.abs(y2) ** 2
    nb = len(e) // (SPS * TIMING_SYMS)
    if nb < 1:
        return None
    ph = []
    rot = np.exp(-2j * np.pi * np.arange(SPS * TIMING_SYMS) / SPS)
    for b in range(nb):
        blk = e[b * SPS * TIMING_SYMS:(b + 1) * SPS * TIMING_SYMS]
        ph.append(np.sum(blk * rot))
    ph = np.array(ph)
    # smooth over 3 blocks and unwrap
    sm = np.convolve(ph, np.ones(3), mode="same")
    tau = np.unwrap(-np.angle(sm)) / (2 * np.pi) * SPS    # offset of the maximum of |y|^2 in samples
    centres = (np.arange(nb) + 0.5) * SPS * TIMING_SYMS
    nsym = int((len(y2) - 2 * SPS) // SPS)
    k = np.arange(nsym)
    pos = k * SPS + np.interp(k * SPS, centres, tau)
    pos = pos[(pos >= 0) & (pos < len(y2) - 1)]
    m = np.arange(len(y2))
    zs = np.interp(pos, m, y2.real) + 1j * np.interp(pos, m, y2.imag)
    d = (zs[1:] * np.conj(zs[:-1])).real
    p = np.mean(np.abs(zs) ** 2) or 1.0
    soft = (d / p).astype(np.float32)
    # SNR from the spread of |d| around its mean (rough, for the display)
    a = np.abs(soft)
    snr = 10 * np.log10(max(np.mean(a) ** 2 / (np.var(a) or 1e-9), 1e-3))
    return {"soft": soft, "t_sym": pos[1:] / fs2, "freq": float(np.mean(fr)), "snr_db": float(snr)}


# ---------------------------------------------------------------- framings

def ax25_frames(soft):
    """AX.25 frames in the differential bits: plain NRZI and with the G3RUH scrambler. -> [(framing, bytes)]"""
    bits = (np.asarray(soft) > 0).astype(np.uint8).tolist()      # no phase change = NRZI 1
    out = [("AX.25", f) for f in packet.HdlcDeframer(nrzi=False).feed(bits)]
    out += [("AX.25 G3RUH", f) for f in packet.HdlcDeframer(nrzi=False).feed(packet.Descrambler().feed(bits))]
    return out


def ax25_text(frame):
    f = packet.parse(frame)
    return (f.tnc2(), str(f.src)) if f else ("hex " + frame.hex(" "), "")


SPANS = (3000, 6000, 12000)       # carrier search ± Hz around the tuned frequency


class BpskDecoder:
    """Keeps WINDOW_S seconds of the VFO baseband, demodulates it every STEP_S seconds in a worker thread and reports
    every new frame once."""

    def __init__(self, on_decode, on_stat=None):
        self.on_decode = on_decode
        self.on_stat = on_stat or (lambda d: None)
        self.decodes = collections.deque(maxlen=300)
        self.enabled = False
        self.error = None
        self.info = ""
        self.baud = 1200
        self.span = 6000
        self.dial_hz = 0.0
        self.fs = None
        self.lock = threading.Lock()
        self._fs_in = None
        self._busy = False
        self._reset()

    def _reset(self):
        self._chunks = collections.deque()
        self._n = 0                 # samples in _chunks
        self._total = 0             # samples received since the setup (absolute index of the next one)
        self._t_last = 0.0          # time.time() of the last sample
        self._next = 0.0
        self._seen_ao40 = collections.deque(maxlen=50)      # epoch times of the decoded AO-40 frames
        self._seen_ax25 = {}                                 # frame bytes -> epoch when decoded
        self._stat = {}

    # ---------- settings ----------

    def configure(self, cfg):
        """At start: the settings and the switch saved in config.json."""
        self.set_options(cfg.get("bpsk_baud", self.baud), cfg.get("bpsk_span", self.span))
        self.set_enabled(cfg.get("bpsk", False))

    def set_options(self, baud=None, span=None):
        baud = int(baud) if str(baud).isdigit() and int(baud) in BAUDS else self.baud
        span = int(span) if str(span).isdigit() and int(span) in SPANS else self.span
        with self.lock:
            if (baud, span) != (self.baud, self.span):
                self.baud, self.span = baud, span
                self._fs_in = None

    def set_enabled(self, on):
        with self.lock:
            self.enabled = bool(on)
            self._fs_in = None
            self.error = None
            self.info = "searching for a BPSK carrier…" if on else ""
            self._stat = {}

    def apply(self, body, cfg):
        """The keys of POST /api/set for this decoder; True if something was changed (the caller saves config)."""
        changed = False
        if "bpsk_baud" in body or "bpsk_span" in body:
            self.set_options(body.get("bpsk_baud"), body.get("bpsk_span"))
            cfg.update(bpsk_baud=self.baud, bpsk_span=self.span)
            changed = True
        if "bpsk" in body:
            self.set_enabled(bool(body["bpsk"]))
            cfg["bpsk"] = self.enabled
            changed = True
        return changed

    def status(self):
        """The fields of this decoder in the VFO state."""
        return {"bpsk": self.enabled, "bpsk_error": self.error, "bpsk_info": self.info, "bpsk_baud": self.baud,
                "bpsk_span": self.span, "bpsk_stat": self._stat}

    # ---------- samples ----------

    def _setup(self, fs):
        self._fs_in = fs
        need = 2.4 * (self.span + self.baud)                  # working rate: the search span plus the signal
        self._dec = max(1, int(fs // need))
        self.fs = fs / self._dec
        self.error = None
        if self.fs < 2 * (self.span + 0.6 * self.baud) * 0.9:
            self.error = (f"{self.baud} Bd ±{self.span / 1000:g} kHz needs a baseband of "
                          f"{2.2 * (self.span + self.baud) / 1000:.0f} kHz (SDR sample rate ≥ "
                          f"{2.2 * (self.span + self.baud) * 64 / 1e6:.1f} MS/s); searching a narrower span")
        taps = 16 * self._dec + 1
        self._h = lowpass(0.45 * self.fs, fs, taps).astype(np.complex64) if self._dec > 1 else None
        self._hist = np.zeros(taps - 1, np.complex64)
        self._phase = 0
        self._reset()

    def feed(self, base, fs, dial_hz):
        """base: complex baseband (tuned frequency = 0 Hz) at sample rate fs."""
        if not self.enabled:
            return
        with self.lock:
            if fs != self._fs_in:
                self._setup(fs)
            self.dial_hz = dial_hz
            if self._h is not None:
                from scipy.signal import oaconvolve
                buf = np.concatenate((self._hist, base))
                self._hist = buf[-(len(self._h) - 1):]
                y = oaconvolve(buf, self._h, mode="valid")
                y = y[self._phase::self._dec]
                self._phase = (self._phase - (len(buf) - len(self._h) + 1)) % self._dec
            else:
                y = base
            y = np.asarray(y, np.complex64)
            self._chunks.append(y)
            self._n += len(y)
            self._total += len(y)
            self._t_last = time.time()
            keep = int(WINDOW_S * self.fs)
            while self._chunks and self._n - len(self._chunks[0]) >= keep:
                self._n -= len(self._chunks.popleft())
            now = time.monotonic()
            if now < self._next or self._busy or self._n < self.fs:
                return
            self._next = now + STEP_S
            z = np.concatenate(list(self._chunks))[-keep:]
            job = (z, self.fs, self.baud, self.span, self._total - len(z), self._total, self._t_last, dial_hz)
            self._busy = True
        threading.Thread(target=self._work, args=job, name="bpsk", daemon=True).start()

    # ---------- decoding (worker thread) ----------

    def _work(self, z, fs, baud, span, i0, total, t_last, dial):
        try:
            hi = min(span, 0.45 * fs - 0.6 * baud)
            r = demod(z, fs, baud, -hi, hi)
            if r is None:
                self._stat = {"lock": False}
                self.info = "searching for a BPSK carrier…"
                self.on_stat({"lock": False, "info": self.info})
                return
            soft = r["soft"]

            def t_abs(k):              # symbol index -> epoch
                return t_last - (total - i0 - r["t_sym"][min(k, len(soft) - 1)] * fs) / fs

            freq = dial + r["freq"]
            self._stat = {"lock": True, "freq_hz": round(freq), "off_hz": round(r["freq"]), "snr": round(r["snr_db"], 1)}
            self.info = f"carrier {freq / 1e6:.6f} MHz ({r['freq']:+.0f} Hz) · {r['snr_db']:.1f} dB"
            self.on_stat(dict(self._stat, info=self.info))
            # AO-40 FEC (both polarities of the differential bit: the sync tells which one)
            for pol in (1.0, -1.0):
                for k, _err in funcube.find_sync(pol * soft):
                    t = t_abs(k)
                    if any(abs(t - s) < 1.5 for s in self._seen_ao40):
                        continue
                    data, info = funcube.decode_frame(pol * soft[k:])
                    if data is None:
                        continue
                    self._seen_ao40.append(t)
                    tel = funcube.parse(data)
                    text = funcube.summary(tel) + (f" · {tel['message']}" if tel.get("message") else "")
                    self._emit(t, freq, r, baud, "AO-40", tel.get("sat", ""), text, data, {"telemetry": tel, "fec": info})
            # AX.25 (HDLC; plain NRZI or G3RUH)
            now = time.time()
            self._seen_ax25 = {b: t for b, t in self._seen_ax25.items() if now - t < WINDOW_S + 3 * STEP_S}
            for framing, fr in ax25_frames(soft):
                if fr in self._seen_ax25:
                    continue
                self._seen_ax25[fr] = now
                text, src = ax25_text(fr)
                self._emit(now, freq, r, baud, framing, src, text, fr, {})
            self.error = None
        except Exception as e:  # noqa: BLE001 - a bad window must not stop the decoder
            self.error = str(e)[:200]
        finally:
            self._busy = False

    def _emit(self, t, freq, r, baud, framing, sat, text, data, extra):
        d = {"ts": t, "time": time.strftime("%H:%M:%S", time.gmtime(t)), "freq_hz": round(freq),
             "snr": round(r["snr_db"], 1), "baud": baud, "framing": framing, "sat": sat, "text": text,
             "hex": bytes(data).hex(" "), **extra}
        self.decodes.append(d)
        self.on_decode(d)

    def clear(self):
        self.decodes.clear()


def register(app, decoder):
    """GET /api/bpsk: the decodes, speeds, search spans and known satellites; DELETE clears the decodes."""
    from flask import jsonify, request

    @app.route("/api/bpsk", methods=["GET", "DELETE"])
    def api_bpsk():
        if request.method == "DELETE":
            decoder.clear()
            return jsonify(ok=True)
        return jsonify(decodes=list(decoder.decodes), bauds=BAUDS, spans=SPANS, sats=SATS)

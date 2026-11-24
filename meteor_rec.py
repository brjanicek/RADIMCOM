"""GRAVES (meteor.py): the echoes recorded into the recordings folder (recorder.py), shown in the RECORDINGS tab.

With REC on (DECODERS › GRAVES › SETTINGS › RECORDINGS, or the REC key of ECHOES), every reported echo of the kinds
chosen (meteors; satellites and aircraft optionally) is written into the day folder of its start:
  * MP3: its sound as on 143.049 MHz USB (meteor_audio.py: the carrier a 1 kHz tone, a satellite followed along its
    Doppler), 8 kHz mono; name <KIND[_NAME]>_<MHz>MHz_USB_<YYYYMMDD_HHMMSS local>_GRAVES.mp3 (source GRAVES);
  * IQ ECHO (optional): the baseband around the carrier as the detector keeps it (meteor_audio.Ring, ±8 kHz, ~16 kS/s)
    from PRE_S before to POST_S after the echo, a 16-bit IQ WAV in …/iq named like REC IQ with the tag GRAVES
    (RADIMCOM_<VFO>_<UTC>Z_<carrier Hz>Hz_IQ_GRAVES.wav): the IQ PLAYER or SDR# plays it;
  * IQ BAND (optional): the same time from the raw IQ of the whole dongle (PRE-REC, retro.py, switched on for it),
    8 bit (RTL) or 16 bit, tag GRAVESBAND; at most BAND_MAX_S (~5 MB/s at 2.4 MS/s 8 bit).
SAVE in the detail of one echo writes the same for that echo alone (whatever is still kept of it).
Writing runs in its own thread; the settings are in data/meteor_rec_<VFO>.json.
"""
import datetime
import io
import json
import os
import queue
import threading
import time
import wave

import numpy as np

import recorder as recorder_mod
from paths import data

PRE_S = 1.0                 # the IQ from this before the echo …
POST_S = 1.0                # … to this after its end
ECHO_MAX_S = 120.0          # a satellite: at most this much of IQ around it
BAND_MAX_S = 8.0            # the whole band of the dongle: at most this long
BAND_RETRO_S = 30           # IQ BAND switches PRE-REC on with at least this many seconds
MP3_KBPS = 32               # 8 kHz mono (MPEG-2.5)
KINDS = ("met", "sat", "plane")
KIND_LABEL = {"under": "METEOR", "over": "METEOR_LONG", "sat": "SAT", "plane": "PLANE"}
DEFAULTS = {"on": False, "kinds": ["met"], "iq": False, "band": False}


def _kind_group(kind):
    return "met" if kind in ("under", "over") else kind


def _label(e):
    """METEOR / METEOR_LONG / SAT_<name> / PLANE_<callsign> for the file name (shown as the memory in RECORDINGS)."""
    lab = KIND_LABEL.get(e.get("kind"), "ECHO")
    name = ""
    if e.get("kind") == "sat":
        name = (e.get("sat") or {}).get("name") or ""
    elif e.get("kind") == "plane":
        a = e.get("air") or {}
        name = a.get("flight") or a.get("call") or a.get("hex") or ""
    name = recorder_mod.safe_name(name)
    return f"{lab}_{name}" if name and name != "_" else lab


def _free(path):
    """path, or path with _2, _3 … before the extension when it exists."""
    stem, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        n += 1
        path = f"{stem}_{n}{ext}"
    return path


def _mp3(wav_bytes):
    import lameenc
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        ch, rate, width, n = w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes()
        pcm = w.readframes(n)
    if width != 2:
        raise ValueError("the sound is not 16 bit")
    enc = lameenc.Encoder()
    enc.set_bit_rate(MP3_KBPS)
    enc.set_in_sample_rate(int(rate))
    enc.set_channels(ch)
    enc.set_quality(2)
    return enc.encode(pcm) + enc.flush()


def _iq_wav(path, iq, fs, kind="i16"):
    """complex samples -> 2-channel IQ WAV (I left, Q right): 8 bit unsigned (the RTL bytes) or 16 bit."""
    x = np.asarray(iq, np.complex64).view(np.float32)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setframerate(int(round(fs)))
        if kind == "u8":
            w.setsampwidth(1)
            w.writeframes(np.clip(np.rint(x * 127.5 + 127.5), 0, 255).astype(np.uint8).tobytes())
        else:
            w.setsampwidth(2)
            w.writeframes(np.clip(np.rint(x * 32767.0), -32768, 32767).astype("<i2").tobytes())


class MeteorRec:
    def __init__(self, counter, folder, retro=None, vfo="", tag=""):
        self.counter = counter
        self.folder = folder                # () -> the recordings root (recorder.folder)
        self.retro = retro
        self.vfo = vfo
        self.path = data(f"meteor_rec_{tag}.json" if tag else "meteor_rec.json")
        self.cfg = dict(DEFAULTS)
        self.saved = 0
        self.last = ""
        self.error = ""
        self.q = queue.Queue(maxsize=200)
        self._load()
        if self.cfg["on"] and self.cfg["band"]:
            self._retro_on()
        threading.Thread(target=self._run, daemon=True, name="meteor-rec").start()

    # ---------- settings ----------
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                j = json.load(f)
            self.cfg.update({k: j[k] for k in DEFAULTS if k in j})
        except (OSError, ValueError):
            pass
        self.cfg["kinds"] = [k for k in self.cfg.get("kinds") or [] if k in KINDS]

    def _save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=1)
            os.replace(tmp, self.path)
        except OSError as e:
            self.error = f"settings not saved: {e}"

    def set(self, body):
        for k in ("on", "iq", "band"):
            if k in body:
                self.cfg[k] = bool(body[k])
        if "kinds" in body and isinstance(body["kinds"], list):
            self.cfg["kinds"] = [k for k in body["kinds"] if k in KINDS]
        if self.cfg["on"] and self.cfg["band"]:
            self._retro_on()
        self.error = ""
        self._save()

    def _retro_on(self):
        r = self.retro
        if r is not None and (not r.on or r.seconds < BAND_RETRO_S):
            r.set(on=True, seconds=max(r.seconds, BAND_RETRO_S))

    def state(self):
        return dict(self.cfg, saved=self.saved, last=self.last, error=self.error,
                    retro=bool(self.retro is not None and self.retro.on))

    # ---------- the echoes ----------
    def echo(self, e):
        """on_echo of the counter: queued when REC is on and its kind is chosen."""
        if not self.cfg["on"] or _kind_group(e.get("kind")) not in self.cfg["kinds"]:
            return
        try:
            self.q.put_nowait((dict(e), self.cfg["iq"], self.cfg["band"]))
        except queue.Full:
            self.error = "too many echoes waiting: some were not recorded"

    def save_now(self, e, iq=True, band=True):
        """SAVE of the detail: this echo alone, now -> the files written (relative to the recordings root)."""
        return self._write(e, iq, band)

    def _run(self):
        while True:
            e, iq, band = self.q.get()
            try:
                self._write(e, iq, band)
            except Exception as x:          # one echo must never stop the recording of the next
                self.error = f"GRAVES recording: {x}"
                print(self.error, flush=True)

    def _write(self, e, iq, band):
        root = self.folder()
        ts, dur = float(e["ts"]), float(e.get("dur") or 0.0)
        day = recorder_mod.day_folder(root, ts)
        out = []
        wav = self.counter.audio(ts)
        if wav is None and getattr(self.counter, "marks", None):
            wav = self.counter.marks.audio(ts)
        if wav:
            os.makedirs(day, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(ts))
            mhz = float(e.get("freq_hz") or 143050000.0) / 1e6
            path = _free(os.path.join(day, f"{_label(e)}_{mhz:.6f}MHz_USB_{stamp}_GRAVES.mp3"))
            data_ = _mp3(wav)
            with open(path + ".part", "wb") as f:
                f.write(data_)
            os.replace(path + ".part", path)
            out.append(path)
        t0, t1 = ts - PRE_S, ts + dur + POST_S
        utc = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        vfo = f"_{self.vfo}" if self.vfo else ""
        iqdir = os.path.join(day, "iq")
        if iq:
            aud = getattr(self.counter, "_aud", None)
            clip = aud.clip(max(t0, t1 - ECHO_MAX_S), t1) if aud is not None else None
            if clip:
                start, z = clip
                peak = float(np.max(np.abs(z))) if len(z) else 0.0
                z = z * np.float32(0.5 / peak) if peak > 0 else z       # the ring is not in dBFS: scaled to -6 dB
                centre = int(round(self.counter._dial + aud.f_off))      # the carrier (at 0 Hz in the ring)
                os.makedirs(iqdir, exist_ok=True)
                path = _free(os.path.join(iqdir, f"RADIMCOM{vfo}_{utc}Z_{centre}Hz_IQ_GRAVES.wav"))
                _iq_wav(path, z, aud.fs)
                out.append(path)
        if band and self.retro is not None and self.retro.on:
            seg = self.retro.segment(t0, min(t1 - t0, BAND_MAX_S))
            if seg is not None:
                x, fs, centre, start = seg
                with self.retro.lock:
                    kind = self.retro.blocks[-1][4] if self.retro.blocks else "i16"
                os.makedirs(iqdir, exist_ok=True)
                path = _free(os.path.join(iqdir, f"RADIMCOM{vfo}_{utc}Z_{int(round(centre))}Hz_IQ_GRAVESBAND.wav"))
                _iq_wav(path, x, fs, kind)
                out.append(path)
        if out:
            self.saved += 1
            self.last = os.path.basename(out[0])
        return [os.path.relpath(p, root).replace(os.sep, "/") for p in out]


def register(app, rec):
    """GET / POST /api/meteors/rec: the REC settings {on, kinds, iq, band} and its state; POST /api/meteors/rec/save
    {ts}: SAVE of the detail, this echo into the recordings now."""
    from flask import jsonify, request

    @app.route("/api/meteors/rec", methods=["GET", "POST"])
    def api_meteors_rec():
        if request.method == "POST":
            rec.set(request.get_json(force=True, silent=True) or {})
        return jsonify(rec.state())

    @app.route("/api/meteors/rec/save", methods=["POST"])
    def api_meteors_rec_save():
        body = request.get_json(force=True, silent=True) or {}
        try:
            ts = float(body.get("ts"))
        except (TypeError, ValueError):
            return jsonify({"error": "ts must be a number"}), 400
        det = rec.counter.detail(ts)
        e = det["echo"] if det else None
        if e is None and getattr(rec.counter, "marks", None):
            m = rec.counter.marks.detail(ts)
            e = m["echo"] if m else next((x for x in rec.counter.marks.list() if abs(x["ts"] - ts) < 0.01), None)
        if e is None:
            return jsonify({"error": "this echo is no longer kept (only the last ones; ★ keeps one)"}), 404
        try:
            files = rec.save_now(e, iq=True, band=True)
        except Exception as x:
            return jsonify({"error": str(x)}), 500
        if not files:
            return jsonify({"error": "nothing of this echo is kept any more (its sound and IQ are gone)"}), 404
        return jsonify({"files": files})

"""GRAVES (meteor.py): the echoes of earlier days from the daily log, and the marked echoes kept for good.

History: the daily log (DECODERS › GRAVES › LOG, logs/meteor/YYYY/MM/DD/meteor_YYYY-MM-DD.txt, shared by all VFOs) is
read back for one day and one VFO. A line (app.py) is
  2026-11-24 05:28:12Z VFO-C 143.050016 MHz +16 Hz 33.9 dB 3.20 s plane | BAW126 H
with the time of the echo, its kind and after "|" the satellite / aircraft found and H for a head echo (older lines
have neither). Only what the log holds: no detail (spectrogram) of an old echo, unless it was marked.

Marks: a star at an echo keeps it with its detail (the spectrogram the page shows) in data/meteor_marks/<VFO>/:
index.json (the echoes), <ts>.json (the detail of each, if it was still in memory) and <ts>.wav (its sound,
meteor_audio.py). They stay until unmarked. GET /api/meteors/audio?ts= gives the sound of a recent or marked echo.
"""
import calendar
import json
import os
import re
import threading
import time

import datafiles
from paths import data

HISTORY_MAX = 5000                      # echoes of one day sent to the page at most
MARKS_MAX = 2000
LINE = re.compile(r"^(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)Z (\S+) (\d+\.\d+) MHz ([+-]\d+) Hz (-?[\d.]+) dB ([\d.]+) s (\w+)"
                  r"(?: \| (.*))?$")
DAY = re.compile(r"^\d{4}-\d\d-\d\d$")
LOG_DIR = data("logs")


def log_tag(tag):
    return f"VFO-{tag}" if tag else "VFO"


def log_name(e):
    """The text after "|" in the log line of an echo: the satellite / aircraft found and H for a head echo."""
    parts = []
    s, a = e.get("sat") or {}, e.get("air") or {}
    if e.get("kind") == "sat" and s.get("name"):
        parts.append(str(s["name"]))
    elif e.get("kind") == "plane" and a.get("hex"):
        parts.append(str(a.get("flight") or a.get("reg") or a["hex"].upper()))
    if e.get("fast"):
        parts.append("F")
    if e.get("head"):
        parts.append("H")
    return " | " + " ".join(parts) if parts else ""


def history_days(log_dir=LOG_DIR):
    """The days (YYYY-MM-DD) with a meteor log, newest first."""
    pat = re.compile(r"^meteor_(\d{4}-\d\d-\d\d)\.txt$")
    days = set()
    for p in datafiles.walk_files(os.path.join(log_dir, "meteor"), pat):
        days.add(pat.match(os.path.basename(p)).group(1))
    return sorted(days, reverse=True)


def history(day, tag, log_dir=LOG_DIR):
    """The echoes of one VFO on one UTC day from the log, oldest first (at most the last HISTORY_MAX)."""
    if not DAY.match(day or ""):
        raise ValueError("day must be YYYY-MM-DD")
    t = calendar.timegm(time.strptime(day + " 12", "%Y-%m-%d %H"))
    path = datafiles.day_file("meteor", t, "txt", log_dir)
    want = log_tag(tag)
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = LINE.match(line.rstrip("\r\n"))
                if not m or m.group(3) != want:
                    continue
                d, hms, _, mhz, dop, snr, dur, kind, rest = m.groups()
                ts = calendar.timegm(time.strptime(f"{d} {hms}", "%Y-%m-%d %H:%M:%S"))
                words = (rest or "").split()
                head = bool(words) and words[-1] == "H"
                if head:
                    words = words[:-1]
                fast = kind == "under" and bool(words) and words[-1] == "F"     # a FAST ping (meteor_weak.py)
                if fast:
                    words = words[:-1]
                e = {"ts": round(ts, 2), "time": hms, "dur": float(dur), "snr": float(snr), "doppler": int(dop), "drift": 0.0,
                     "kind": kind, "freq_hz": round(float(mhz) * 1e6), "det": False, "head": {"log": True} if head else None,
                     "name": " ".join(words), "log": True}
                if fast:
                    e["fast"] = True
                out.append(e)
    except OSError:
        pass
    return out[-HISTORY_MAX:]


class Marks:
    """The marked echoes of one VFO with their details."""

    def __init__(self, tag="", root=None):
        self.dir = root or data("meteor_marks", tag or "main")
        self.lock = threading.Lock()
        self._index = None

    def _load(self):
        if self._index is None:
            try:
                with open(os.path.join(self.dir, "index.json"), encoding="utf-8") as f:
                    self._index = {float(e["ts"]): e for e in json.load(f)}
            except (OSError, ValueError, KeyError, TypeError):
                self._index = {}
        return self._index

    def _save(self):
        os.makedirs(self.dir, exist_ok=True)
        tmp = os.path.join(self.dir, "index.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sorted(self._index.values(), key=lambda e: e["ts"]), f, ensure_ascii=False)
        os.replace(tmp, os.path.join(self.dir, "index.json"))

    def _file(self, ts):
        return os.path.join(self.dir, f"{float(ts):.2f}.json")

    def keys(self):
        with self.lock:
            return set(self._load())

    def list(self):
        with self.lock:
            return sorted(self._load().values(), key=lambda e: e["ts"])

    def add(self, echo, detail=None, wav=None):
        """Keeps an echo (and its detail, the answer of /api/meteors/echo, and its sound) -> True when the detail is
        kept too."""
        ts = round(float(echo["ts"]), 2)
        e = dict(echo, ts=ts, marked=True, det=bool(detail) or bool(echo.get("det") and self.detail(ts)))
        if wav:
            os.makedirs(self.dir, exist_ok=True)
            with open(self._file(ts)[:-5] + ".wav", "wb") as f:
                f.write(wav)
        e["audio"] = bool(wav) or os.path.exists(self._file(ts)[:-5] + ".wav")
        if detail:
            detail = dict(detail, audio=e["audio"])
        with self.lock:
            idx = self._load()
            if ts not in idx and len(idx) >= MARKS_MAX:
                raise ValueError(f"at most {MARKS_MAX} marked echoes: unmark some first")
            os.makedirs(self.dir, exist_ok=True)
            if detail:
                tmp = self._file(ts) + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(dict(detail, echo=e), f, separators=(",", ":"))
                os.replace(tmp, self._file(ts))
            idx[ts] = e
            self._save()
        return e["det"]

    def remove(self, ts):
        ts = round(float(ts), 2)
        with self.lock:
            idx = self._load()
            key = next((k for k in idx if abs(k - ts) < 0.01), None)
            if key is None:
                return False
            del idx[key]
            self._save()
            for p in (self._file(key), self._file(key)[:-5] + ".wav"):
                try:
                    os.remove(p)
                except OSError:
                    pass
        return True

    def audio(self, ts):
        """The kept sound (WAV bytes) of a marked echo, or None."""
        try:
            with open(self._file(round(float(ts), 2))[:-5] + ".wav", "rb") as f:
                return f.read()
        except OSError:
            return None

    def detail(self, ts):
        """The kept detail of a marked echo, or None."""
        try:
            with open(self._file(round(float(ts), 2)), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None


def register(app, counter, tag):
    """GET /api/meteors/history (the days) and ?day=YYYY-MM-DD (its echoes); GET /api/meteors/marks;
    POST /api/meteors/mark {ts, on, echo}: marks / unmarks an echo (echo: the row of the page, for one from the log)."""
    from flask import jsonify, request
    marks = counter.marks = Marks(tag)

    @app.route("/api/meteors/history")
    def api_meteors_history():
        day = request.args.get("day")
        if not day:
            return jsonify({"days": history_days()})
        try:
            ev = history(day, tag)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        keys = marks.keys()
        with counter.lock:
            have = set(counter.details)
        for e in ev:
            near = [k for k in have if abs(k - e["ts"]) < 2.5]
            e["det"] = bool(near)
            if near:
                e["ts"] = near[0]          # the log has whole seconds: the echo in memory with its detail
            e["marked"] = any(abs(k - e["ts"]) < 0.01 for k in keys)
        return jsonify({"day": day, "events": ev})

    @app.route("/api/meteors/marks")
    def api_meteors_marks():
        return jsonify({"events": marks.list()})

    @app.route("/api/meteors/mark", methods=["POST"])
    def api_meteors_mark():
        body = request.get_json(force=True, silent=True) or {}
        try:
            ts = float(body.get("ts"))
        except (TypeError, ValueError):
            return jsonify({"error": "ts must be a number"}), 400
        if not body.get("on", True):
            return jsonify({"ok": marks.remove(ts)})
        det = counter.detail(ts)
        echo = det["echo"] if det else body.get("echo")
        if not isinstance(echo, dict) or "ts" not in echo:
            return jsonify({"error": "unknown echo"}), 404
        try:
            kept = marks.add(echo, det, counter.audio(ts))
        except (ValueError, OSError) as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "det": kept})

    @app.route("/api/meteors/audio")
    def api_meteors_audio():
        """?ts=: the sound of an echo as WAV (143.049 USB: the carrier at 1 kHz; a satellite followed to 1 kHz)."""
        from flask import Response
        try:
            ts = float(request.args.get("ts", ""))
        except ValueError:
            return jsonify({"error": "ts must be a number"}), 400
        wav = counter.audio(ts) or marks.audio(ts)
        if not wav:
            return jsonify({"error": "no sound of this echo (only the last ones are kept; ★ keeps one)"}), 404
        return Response(wav, mimetype="audio/wav", headers={"Cache-Control": "max-age=3600"})

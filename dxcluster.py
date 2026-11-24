"""DX cluster spots for the DX tab (DX key, group PROP).

The spots come from the public DX cluster feed of HamQTH (https://www.hamqth.com/dxc_csv.php): plain HTTP, no login
and no callsign of the station, nothing about the station is sent. One line per spot:

    spotter^freq_khz^dx_call^comment^HHMM YYYY-MM-DD^LoTW^eQSL^continent^band^country^dxcc

The feed holds the last 200 spots (about 20 minutes on a busy day). It is read at most once a minute, whoever asks,
and the spots are merged into a list kept for 30 minutes: a spot older than that is dropped. The same DX on the same
frequency (within 1 kHz) is one row: the newest spot with the number of spots and the spotters.

    register(app)      adds GET /api/dxcluster to a Flask app (the launcher, and app.py for a receiver without it)
"""
import calendar
import threading
import time
import urllib.request

URL = "https://www.hamqth.com/dxc_csv.php?limit=200"
SOURCE = "HamQTH DX cluster"
FETCH_EVERY_S = 60          # the feed is read at most this often
KEEP_S = 30 * 60            # a spot older than this is dropped
TIMEOUT_S = 10
SAME_KHZ = 1.0              # the same DX within this is one row

_lock = threading.Lock()
_spots = {}                 # key (dx, freq bucket) -> spot dict
_state = {"fetched": 0.0, "ok": 0.0, "error": ""}


def _spot_time(txt):
    """'1024 2026-11-21' (UTC) -> epoch s, or None."""
    try:
        hm, ymd = txt.split()
        return float(calendar.timegm(time.strptime(f"{ymd} {hm}", "%Y-%m-%d %H%M")))
    except (ValueError, AttributeError):
        return None


def parse(text):
    """Lines of the feed -> spot dicts (bad lines skipped)."""
    out = []
    for line in text.splitlines():
        f = line.strip().split("^")
        if len(f) < 9:
            continue
        try:
            khz = float(f[1])
        except ValueError:
            continue
        t = _spot_time(f[4])
        dx = f[2].strip().upper()
        if not dx or t is None or khz <= 0:
            continue
        out.append({"dx": dx, "khz": round(khz, 1), "spotter": f[0].strip().upper(), "comment": f[3].strip(),
                    "t": t, "lotw": f[5].strip() == "L", "eqsl": f[6].strip() == "E",
                    "cont": f[7].strip() if len(f) > 7 else "", "band": f[8].strip().lower() if len(f) > 8 else "",
                    "country": f[9].strip() if len(f) > 9 else ""})
    return out


def merge(new, now=None):
    """New spots into the kept list: one row per DX and frequency (1 kHz), the newest spot wins and the spotters
    are counted; rows older than KEEP_S go."""
    now = time.time() if now is None else now
    for s in new:
        key = (s["dx"], round(s["khz"] / SAME_KHZ))
        old = _spots.get(key)
        if old is None:
            _spots[key] = {**s, "spotters": [s["spotter"]]}
            continue
        spotters = old["spotters"] if s["spotter"] in old["spotters"] else old["spotters"] + [s["spotter"]]
        if s["t"] >= old["t"]:
            _spots[key] = {**s, "spotters": spotters, "comment": s["comment"] or old["comment"]}
        else:
            old["spotters"] = spotters
    for k in [k for k, s in _spots.items() if now - s["t"] > KEEP_S]:
        del _spots[k]


def _fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "RADIMCOM"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return r.read().decode("utf-8", "replace")


def spots():
    """The kept spots, newest first, reading the feed when the last read is older than FETCH_EVERY_S."""
    now = time.time()
    with _lock:
        if now - _state["fetched"] >= FETCH_EVERY_S:
            _state["fetched"] = now
            try:
                merge(parse(_fetch()), now)
                _state["ok"], _state["error"] = now, ""
            except Exception as e:                  # offline, the feed down: keep what we have
                _state["error"] = f"{SOURCE}: {e}"
                merge([], now)
        else:
            merge([], now)
        lst = sorted(_spots.values(), key=lambda s: s["t"], reverse=True)
        return {"spots": [{**s, "n": len(s["spotters"])} for s in lst], "fetched": _state["ok"],
                "error": _state["error"], "keep_s": KEEP_S, "source": SOURCE, "now": now}


def register(app):
    from flask import jsonify

    @app.route("/api/dxcluster")
    def api_dxcluster():
        """DX cluster spots of the last 30 minutes (dxcluster.py), the same for the whole station."""
        return jsonify(spots())

"""Model wind for the radiosonde prediction: GFS on pressure levels from Open-Meteo (https://open-meteo.com, data
CC-BY 4.0, free for non-commercial use), only for the 0.25° cells the predicted flight of a sonde goes through.

The browser asks for the cells along the path it predicted from the sonde's own winds (GET /api/wind?cells=…); the
missing ones are downloaded in one request and kept in data/wind/<run>/<lat>_<lon>.json, shared by all VFOs. <run> is
the newest GFS run that should be out (00 / 06 / 12 / 18 UTC + RUN_DELAY_H): until the next one, the same cells are not
downloaded again. Runs older than KEEP_S are deleted. Only the positions of the cells (the sonde's path, which the sonde
broadcasts anyway) go out, nothing of the station.

A cell: hourly from PAST_H before to FUTURE_H after now, on all LEVELS: the height of the level (geopotential, m) and
the wind as u (to the east) and v (to the north) in m/s.
"""
import json
import os
import shutil
import threading
import time
import urllib.parse
import urllib.request

from paths import data

URL = "https://api.open-meteo.com/v1/gfs"
DIR = data("wind")
CELL = 0.25                     # deg: the GFS pressure-level grid
LEVELS = (1000, 975, 950, 925, 900, 875, 850, 825, 800, 775, 750, 725, 700, 675, 650, 625, 600, 575, 550, 525, 500,
          475, 450, 425, 400, 375, 350, 325, 300, 275, 250, 225, 200, 175, 150, 125, 100, 70, 50, 40, 30, 20, 15, 10)
PAST_H, FUTURE_H = 6, 12        # hours of the profile around now (a flight with its fall lasts up to ~4 h)
RUN_DELAY_H = 5                 # a GFS run is on Open-Meteo about 4-5 h after its start time
KEEP_S = 2 * 86400
MAX_CELLS = 40                  # per request of the browser
PER_FETCH = 10                  # locations per Open-Meteo request
TIMEOUT_S = 20
RETRY_S = 600                   # a cell that failed is not asked for again before this

_lock = threading.Lock()
_failed = {}                    # (run, key) -> time of the failure
_state = {"error": None, "fetched": 0, "cleaned": 0.0}


def run_id(now=None):
    """The newest GFS run that should be available now, as YYYYMMDD_HH."""
    t = (now or time.time()) - RUN_DELAY_H * 3600
    t -= t % (6 * 3600)
    return time.strftime("%Y%m%d_%H", time.gmtime(t))


def cell_key(lat, lon):
    """The cell of a position: its centre on the 0.25° grid, as "48.75_17.25"."""
    la, lo = round(lat / CELL) * CELL, round(lon / CELL) * CELL
    lo = (lo + 180) % 360 - 180
    return f"{la:.2f}_{lo:.2f}"


def _path(run, key):
    return os.path.join(DIR, run, f"{key}.json")


def _cleanup():
    now = time.time()
    if now - _state["cleaned"] < 3600 or not os.path.isdir(DIR):
        return
    _state["cleaned"] = now
    for name in os.listdir(DIR):
        p = os.path.join(DIR, name)
        try:
            if os.path.isdir(p) and now - os.path.getmtime(p) > KEEP_S:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass


def _profile(h):
    """One location of the Open-Meteo answer -> {t, lv, z, u, v} (rows = hours, columns = LEVELS)."""
    import math
    t = h["time"]
    z, u, v = [], [], []
    for i in range(len(t)):
        zr, ur, vr = [], [], []
        for lv in LEVELS:
            zz = h.get(f"geopotential_height_{lv}hPa", [None] * len(t))[i]
            sp = h.get(f"wind_speed_{lv}hPa", [None] * len(t))[i]
            dr = h.get(f"wind_direction_{lv}hPa", [None] * len(t))[i]
            if zz is None or sp is None or dr is None:
                zr.append(None), ur.append(None), vr.append(None)
                continue
            a = math.radians(dr)                 # the direction the wind comes FROM
            zr.append(round(zz))
            ur.append(round(-sp * math.sin(a), 2))
            vr.append(round(-sp * math.cos(a), 2))
        z.append(zr), u.append(ur), v.append(vr)
    return {"t": t, "lv": list(LEVELS), "z": z, "u": u, "v": v}


def _fetch(run, keys):
    """Downloads the cells (keys) into the run folder; returns {key: profile} of those that came."""
    var = ",".join(f"{n}_{lv}hPa" for lv in LEVELS for n in ("wind_speed", "wind_direction", "geopotential_height"))
    lat = ",".join(k.split("_")[0] for k in keys)
    lon = ",".join(k.split("_")[1] for k in keys)
    q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "hourly": var, "wind_speed_unit": "ms",
                                "timeformat": "unixtime", "past_hours": PAST_H, "forecast_hours": FUTURE_H,
                                "cell_selection": "nearest"}, safe=",")
    req = urllib.request.Request(f"{URL}?{q}", headers={"User-Agent": "RADIMCOM"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        ans = json.loads(r.read().decode("utf-8"))
    if isinstance(ans, dict):
        ans = [ans]
    os.makedirs(os.path.join(DIR, run), exist_ok=True)
    out = {}
    for key, a in zip(keys, ans):
        h = a.get("hourly") if isinstance(a, dict) else None
        if not h or not h.get("time"):
            continue
        prof = _profile(h)
        prof["run"] = run
        tmp = _path(run, key) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(prof, f, separators=(",", ":"))
        os.replace(tmp, _path(run, key))
        out[key] = prof
    return out


def cells(keys):
    """Profiles of the cells (keys as from cell_key), downloading the missing ones of the current run.
    Returns {"run", "cells": {key: profile}, "error", "source"}."""
    run = run_id()
    keys = [k for k in dict.fromkeys(keys) if k][:MAX_CELLS]
    out, missing = {}, []
    with _lock:
        _cleanup()
        now = time.time()
        for k in keys:
            p = _path(run, k)
            if os.path.exists(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        out[k] = json.load(f)
                    continue
                except (OSError, ValueError):
                    pass
            if now - _failed.get((run, k), 0) > RETRY_S:
                missing.append(k)
        for i in range(0, len(missing), PER_FETCH):
            part = missing[i:i + PER_FETCH]
            try:
                got = _fetch(run, part)
                out.update(got)
                _state["fetched"] += len(got)
                _state["error"] = None
                for k in part:
                    if k not in got:
                        _failed[(run, k)] = now
            except Exception as e:      # no internet, limit, … : the prediction stays on the sonde's own winds
                _state["error"] = f"{type(e).__name__}: {e}"[:200]
                for k in part:
                    _failed[(run, k)] = now
                break
    return {"run": run, "cells": out, "error": _state["error"], "source": "Open-Meteo.com (GFS, NOAA), CC-BY 4.0"}

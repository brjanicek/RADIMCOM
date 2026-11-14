"""Radiosonde launch sites in Europe for the SONDE map, from the launch site list of SondeHub (https://sondehub.org).

The list is not part of the package: it is downloaded from the SondeHub API when the map first asks for it and kept in
data/sonde_sites.json for a week (all VFOs share the file). Without internet the last saved list is used; without one,
the map simply shows no sites.

The WMO radiosonde type codes are translated as the SondeHub tracker does (js/sondehub.js, sondeCodes and
unsupportedSondeCodes; https://github.com/projecthorus/sondehub-tracker, MIT licence).
"""
import gzip
import json
import os
import threading
import time
import urllib.request

from paths import data

URL = "https://api.v2.sondehub.org/sites"
CACHE = data("sonde_sites.json")
# own sites (e.g. a military one SondeHub does not list): a JSON list of {"id", "name", "lat", "lon", optional "alt",
# "types" [{"name", "mhz"}] or ["DFM-17", …], "times" ["0:12:00", …], "note"}; an "id" of a SondeHub site changes that site
EXTRA = data("sonde_sites_extra.json")
MAX_AGE_S = 7 * 86400          # download again after a week
RETRY_S = 3600                 # after a failed download
TIMEOUT_S = 20
# Europe (and its edges: Iceland, the Canary Islands are left out, Cyprus and western Turkey are in)
LAT_MIN, LAT_MAX, LON_MIN, LON_MAX = 34.0, 72.0, -25.0, 45.0

TYPES = {"07": "iMet-1", "11": "LMS6-403", "13": "RS92", "14": "RS92", "17": "DFM-09", "18": "DFM-06", "19": "MRZ-N1",
         "22": "RS-11G", "23": "RS41", "24": "RS41", "34": "iMet-4", "35": "iMS-100", "38": "WxR-301D", "41": "RS41",
         "42": "RS41", "45": "CF-06", "50": "SRS-C50", "52": "RS92-NGP", "54": "DFM-17", "62": "MRZ-3MK", "63": "M20",
         "64": "PS20", "65": "MTS01", "77": "M10", "82": "LMS6-1680", "84": "iMet-54"}
OTHER_TYPES = {"15": "PAZA-12M", "16": "PAZA-22", "20": "MK3", "21": "1524LA LORAN-C/GL5000", "26": "SRS-C34",
               "27": "AVK-MRZ", "28": "AVK-AK2-02", "29": "MARZ2-2", "30": "RS2-80", "33": "GTS1-2/GFE(L)",
               "58": "AVK-BAR", "59": "M2K2-R", "68": "AVK-RZM-2", "69": "MARL-A/Vektor-M-RZM-2", "73": "MARL-A",
               "78": "RS90", "80": "RS92", "88": "MARL-A/Vektor-M-MRZ", "89": "MARL-A/Vektor-M-BAR", "97": "iMet-2",
               "99": "iMet-2"}
DECODED = {"RS41", "DFM-09", "DFM-06", "DFM-17"}   # types the SONDE decoder of RADIMCOM reads (DFM experimental)

_lock = threading.Lock()
_state = {"sites": None, "fetched": 0.0, "error": None, "busy": False, "tried": 0.0}


def _type(t):
    """rs_types entry ("41" or ["41", "400.6"]) -> {"name", "mhz", "decoded"}."""
    code, mhz = (t[0], t[1] if len(t) > 1 else None) if isinstance(t, list) else (t, None)
    code = str(code)
    name = TYPES.get(code) or (f"{OTHER_TYPES[code]} (not decodable)" if code in OTHER_TYPES else f"WMO code {code}")
    try:
        mhz = float(mhz) if mhz is not None else None
    except (TypeError, ValueError):
        mhz = None
    return {"name": name, "mhz": mhz, "decoded": name in DECODED}


def _site(key, s):
    """One SondeHub site -> a compact one, or None outside Europe / without a position."""
    try:
        lon, lat = float(s["position"][0]), float(s["position"][1])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return None
    out = {"id": str(s.get("station") or key), "name": str(s.get("station_name") or key)[:120],
           "lat": round(lat, 5), "lon": round(lon, 5), "alt": s.get("alt"),
           "types": [_type(t) for t in s.get("rs_types") or []],
           "times": [str(t) for t in s.get("times") or []]}       # "day:hh:mm" UTC, day 0 = daily, 1-7 = Mon-Sun
    for k in ("ascent_rate", "descent_rate", "burst_altitude"):
        if isinstance(s.get(k), (int, float)):
            out[k] = s[k]
    return out


def _download():
    req = urllib.request.Request(URL, headers={"User-Agent": "RADIMCOM", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    d = json.loads(raw)
    sites = [x for x in (_site(k, v) for k, v in d.items()) if x]
    sites.sort(key=lambda x: x["name"])
    if not sites:
        raise ValueError("no sites in Europe in the answer")
    return sites


def _load_cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            d = json.load(f)
        return d["sites"], float(d["fetched"])
    except (OSError, ValueError, KeyError, TypeError):
        return None, 0.0


def _refresh():
    try:
        sites = _download()
        now = time.time()
        tmp = f"{CACHE}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"fetched": now, "source": URL, "sites": sites}, f, ensure_ascii=False)
        os.replace(tmp, CACHE)
        with _lock:
            _state.update(sites=sites, fetched=now, error=None)
    except Exception as e:                       # no internet, API changed…: keep what there is
        with _lock:
            _state["error"] = f"SondeHub launch sites: {e}"
    finally:
        with _lock:
            _state["busy"] = False


def _extra():
    """data/sonde_sites_extra.json, checked loosely: a bad entry is left out, a bad file gives an error text."""
    try:
        with open(EXTRA, encoding="utf-8") as f:
            items = json.load(f)
    except FileNotFoundError:
        return [], None
    except (OSError, ValueError) as e:
        return [], f"{EXTRA}: {e}"
    out = []
    for i, e in enumerate(items if isinstance(items, list) else []):
        try:
            x = {"id": str(e.get("id") or f"own-{i + 1}"), "name": str(e["name"])[:120], "own": True}
            if "lat" in e or "lon" in e:
                x.update(lat=float(e["lat"]), lon=float(e["lon"]))
            if e.get("alt") is not None:
                x["alt"] = float(e["alt"])
            if "types" in e:
                x["types"] = [{"name": str(t), "mhz": None, "decoded": str(t) in DECODED} if isinstance(t, str) else
                              {"name": str(t.get("name")), "mhz": float(t["mhz"]) if t.get("mhz") else None,
                               "decoded": str(t.get("name")) in DECODED} for t in e["types"]]
            if "times" in e:
                x["times"] = [str(t) for t in e["times"]]
            if e.get("note"):
                x["note"] = str(e["note"])[:200]
            out.append(x)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return out, None


def sites():
    """The sites now (maybe from the cache, maybe none yet); starts a download in the background when needed."""
    with _lock:
        if _state["sites"] is None:
            _state["sites"], _state["fetched"] = _load_cache()
        old = time.time() - _state["fetched"] > MAX_AGE_S
        if (old or _state["sites"] is None) and not _state["busy"] and time.time() - _state["tried"] > RETRY_S:
            _state["busy"], _state["tried"] = True, time.time()
            threading.Thread(target=_refresh, name="sonde-sites", daemon=True).start()
        base = list(_state["sites"] or [])
        info = {"fetched": _state["fetched"] or None, "loading": _state["busy"], "error": _state["error"]}
    extra, err = _extra()
    by_id = {x["id"]: dict(x) for x in base}
    for e in extra:
        if e["id"] in by_id:
            by_id[e["id"]].update(e)                 # own changes of a SondeHub site (a note, a frequency…)
        elif "lat" in e:
            by_id[e["id"]] = dict({"types": [], "times": []}, **e)
    return dict(info, sites=list(by_id.values()), extra_error=err, source="SondeHub (sondehub.org)")

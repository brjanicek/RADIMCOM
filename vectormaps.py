"""Vector maps of the COMPOSITE map: airspaces, airports, navaids, reporting points and obstacles, kept offline.

The data is downloaded once per country (button Update in the map settings) and stored in data/vectormaps/, one file
per source and country, as GeoJSON with properties of the same names for every source:

    kind    airspace | airport | navaid | point | obstacle | tx (transmitter sites) | chan (MEMORIES channels)
            | own (own files) | aero (aerodrome layout: aerodrome, runway, apron, taxiway, helipad)
            (the group of the map settings tree)
    cat     the part of the group: CTR, TMA, R, D, ... / intl, civil, ul, ... / VOR-DME, NDB, ... (the tree's leaves)
    name, ident, cls (ICAO class A-G or SUA), elev (m MSL), height (m above ground, obstacles)
    freq    [{"f": MHz, "name": str, "type": str}]
    lower, upper    {"v": number, "u": "ft" | "m" | "FL", "ref": "GND" | "MSL" | "STD"}   (airspaces)
    src, srcId      where it comes from and its id there

The file's root object also holds "radimcom": {version, name, source, country, fetched (UNIX s), license,
attribution, view}. What is shown is kept in the files too, so it is the same in every browser and computer and travels
with the file: "view" = {on (this map), cats {"kind" | "kind.cat": bool}, lbl {kind: bool}, maxFL, style
{"kind.cat": {c, w, d, o, fc, fo, r, sym, lc, ls, lz}} (only what differs from the defaults)}, and a hidden
object has "hidden": true in its properties. Update keeps both (objects matched by their id in the source). Airspaces keep their polygons and vertical limits, so a later "track inside an airspace" test can use
the same files.

Sources: openAIP (https://www.openaip.net, CC BY-NC 4.0, free API key in data/mapkeys.json). The API has no area
filter, so it is asked per country. OurAirports (https://ourairports.com, public domain): airports with their
frequencies and runways, and navaids, from its CSV files of the whole world (kept a day in data/vectormaps/_ourairports
so more countries need one download), cut per country. OpenStreetMap (ODbL) through the Overpass API: transmitter
sites (masts, towers and antennas for broadcasting, mobile phones, radar, amateur radio and other radio) and the layout of
the aerodromes (boundary, runways, taxiways, aprons, helipads), per country. OurAirports adds the runways that have the
coordinates of both ends.
MEMORIES: the channels with a location (lat / lon) as the map "memories", one part per group, made again whenever
memories.json changes. Own files: GeoJSON (KML / GPX turned into GeoJSON in the browser) stored as file_<name>; objects
that already carry a known kind keep it (files in this format), the others become kind "own" (area / line / point).
"""
import hashlib
import csv
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import Blueprint, jsonify, request

from paths import data

VMAP_DIR = data("vectormaps")
NOTES_PATH = data("vectormaps_notes.json")   # own names and notes of objects, kept apart so an update never loses them
MAPKEYS_PATH = data("mapkeys.json")
VERSION = 1
STALE_S = 28 * 86400            # an AIRAC cycle: older data is marked for an update

OPENAIP_API = "https://api.core.openaip.net/api/"
OPENAIP_LICENSE = "CC BY-NC 4.0"
OPENAIP_ATTR = '&copy; <a href="https://www.openaip.net" target="_blank" rel="noopener noreferrer">openAIP</a> (CC BY-NC)'
OPENAIP_PAGE = 1000
OPENAIP_TIMEOUT = 30

# openAIP codes (https://api.core.openaip.net/api/system/specs/v1/schema.json)
LIMIT_UNIT = {0: "m", 1: "ft", 6: "FL"}
LIMIT_REF = {0: "GND", 1: "MSL", 2: "STD"}
AIRSPACE_CAT = {0: "OTHER", 1: "R", 2: "D", 3: "P", 4: "CTR", 5: "TMZ", 6: "RMZ", 7: "TMA", 8: "TRA", 9: "TSA",
                10: "FIR", 11: "UIR", 12: "ADIZ", 13: "ATZ", 14: "MATZ", 15: "AWY", 16: "MTR", 17: "ALERT",
                18: "WARNING", 19: "PROTECTED", 20: "HTZ", 21: "GLIDING", 22: "TRP", 23: "TIZ", 24: "TIA", 25: "MTA",
                26: "CTA", 27: "ACC", 28: "SPORT", 29: "LOWFLY", 30: "MRT", 31: "TFR", 32: "VFR", 33: "FIS",
                34: "LTA", 35: "UTA", 36: "MCTR"}
ICAO_CLASS = {0: "A", 1: "B", 2: "C", 3: "D", 4: "E", 5: "F", 6: "G", 8: "SUA"}
AIRPORT_CAT = {0: "airport", 1: "glider", 2: "civil", 3: "intl", 4: "heli_mil", 5: "military", 6: "ul",
               7: "heli", 8: "closed", 9: "ifr", 10: "water", 11: "strip", 12: "agri", 13: "altiport"}
NAVAID_CAT = {0: "DME", 1: "TACAN", 2: "NDB", 3: "VOR", 4: "VOR-DME", 5: "VORTAC", 6: "DVOR", 7: "DVOR-DME",
              8: "DVORTAC"}
OBSTACLE_CAT = {0: "obstacle", 1: "chimney", 2: "building", 3: "wind", 4: "tower"}
FREQ_TYPE = {0: "APP", 1: "APRON", 2: "ARR", 3: "CTR", 4: "CTAF", 5: "DEL", 6: "DEP", 7: "FIS", 8: "GLIDING",
             9: "GND", 10: "INFO", 11: "MULTICOM", 12: "UNICOM", 13: "RADAR", 14: "TWR", 15: "ATIS", 16: "RADIO",
             17: "OTHER", 18: "AIRMET", 19: "AWOS", 20: "LIGHTS", 21: "VOLMET", 22: "AFIS", 23: "ASOS", 24: "AWIS",
             25: "EMERG", 26: "CLD", 27: "RCO", 28: "GCO", 29: "FSS"}
# endpoint -> converter name (kind)
OPENAIP_ENDPOINTS = ("airspaces", "airports", "navaids", "reporting-points", "obstacles")

bp = Blueprint("vectormaps", __name__)


# ---------- openAIP -> the common properties ----------
def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _limit(d):
    """{value, unit, referenceDatum} -> {"v", "u", "ref"} (None when missing)."""
    if not isinstance(d, dict) or _num(d.get("value")) is None:
        return None
    v = _num(d["value"])
    return {"v": int(v) if v == int(v) else v, "u": LIMIT_UNIT.get(d.get("unit"), "ft"), "ref": LIMIT_REF.get(d.get("referenceDatum"), "MSL")}


def _mhz(value, unit):
    """A frequency string of openAIP in MHz (unit 1 = kHz, 2 = MHz)."""
    f = _num(value)
    if f is None:
        return None
    return round(f / 1000, 6) if unit == 1 else f


def _freqs(items):
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        f = _mhz(it.get("value"), it.get("unit", 2))
        if f is None:
            continue
        fr = {"f": f}
        if it.get("name"):
            fr["name"] = str(it["name"])
        if it.get("type") is not None:
            fr["type"] = FREQ_TYPE.get(it.get("type"), "OTHER")
        out.append(fr)
    return out


def _elev_m(d):
    if not isinstance(d, dict) or _num(d.get("value")) is None:
        return None
    v = _num(d["value"])
    return round(v * 0.3048) if d.get("unit") == 1 else round(v)


def _feature(item, kind, cat, extra=None):
    geom = item.get("geometry")
    if not isinstance(geom, dict) or geom.get("type") not in ("Point", "Polygon", "MultiPolygon", "LineString"):
        return None
    p = {"kind": kind, "cat": cat, "name": str(item.get("name") or "").strip(), "src": "openaip", "srcId": str(item.get("_id") or "")}
    for k, v in (extra or {}).items():
        if v not in (None, "", []):
            p[k] = v
    return {"type": "Feature", "geometry": geom, "properties": p}


def airspace_cat(item):
    """The part of the tree of an airspace. openAIP codes many TMA / CTA sectors as "Other": the name tells them."""
    cat = AIRSPACE_CAT.get(item.get("type"), "OTHER")
    if cat == "OTHER":
        name = str(item.get("name") or "").upper()
        for c in ("TMA", "CTA", "CTR"):
            if re.search(rf"\b{c}\b", name):
                return c
    return cat


def openaip_airspace(item):
    return _feature(item, "airspace", airspace_cat(item), {
        "cls": ICAO_CLASS.get(item.get("icaoClass")), "lower": _limit(item.get("lowerLimit")),
        "upper": _limit(item.get("upperLimit")), "freq": _freqs(item.get("frequencies")),
        "ident": item.get("identifier")})


def openaip_airport(item):
    rwy = [r.get("designator") for r in item.get("runways") or [] if isinstance(r, dict) and r.get("designator")]
    return _feature(item, "airport", AIRPORT_CAT.get(item.get("type"), "airport"), {
        "ident": item.get("icaoCode") or item.get("iataCode") or item.get("altIdentifier"),
        "elev": _elev_m(item.get("elevation")), "freq": _freqs(item.get("frequencies")), "rwy": rwy})


def openaip_navaid(item):
    f = item.get("frequency")
    fr = _freqs([f]) if isinstance(f, dict) else []
    return _feature(item, "navaid", NAVAID_CAT.get(item.get("type"), "VOR"), {
        "ident": item.get("identifier"), "freq": fr, "channel": item.get("channel"),
        "elev": _elev_m(item.get("elevation")), "range": (item.get("range") or {}).get("value")})


def openaip_point(item):
    return _feature(item, "point", "RP" if item.get("compulsory", True) else "RP_OPT", {
        "remarks": item.get("remarks"), "elev": _elev_m(item.get("elevation"))})


def openaip_obstacle(item):
    return _feature(item, "obstacle", OBSTACLE_CAT.get(item.get("type"), "obstacle"), {
        "elev": _elev_m(item.get("elevation")), "height": _elev_m(item.get("height"))})


OPENAIP_CONVERT = {"airspaces": openaip_airspace, "airports": openaip_airport, "navaids": openaip_navaid,
                   "reporting-points": openaip_point, "obstacles": openaip_obstacle}


def openaip_collection(country, items_by_endpoint, fetched=None):
    """The map file of one country from the raw openAIP items {endpoint: [item, ...]}."""
    feats = []
    for ep in OPENAIP_ENDPOINTS:
        conv = OPENAIP_CONVERT[ep]
        for it in items_by_endpoint.get(ep) or []:
            if isinstance(it, dict):
                f = conv(it)
                if f:
                    feats.append(f)
    return {"type": "FeatureCollection", "radimcom": {
        "version": VERSION, "name": f"openAIP {country}", "source": "openaip", "country": country,
        "fetched": round(fetched or time.time()), "license": OPENAIP_LICENSE, "attribution": OPENAIP_ATTR},
        "features": feats}


def _openaip_get(endpoint, country, key, page):
    q = urllib.parse.urlencode({"country": country, "limit": OPENAIP_PAGE, "page": page})
    req = urllib.request.Request(f"{OPENAIP_API}{endpoint}?{q}", headers={"x-openaip-api-key": key, "Accept": "application/json",
                                                                          "User-Agent": "RADIMCOM"})
    with urllib.request.urlopen(req, timeout=OPENAIP_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def openaip_download(country, key, get=_openaip_get):
    """All items of a country, per endpoint (pages followed)."""
    out = {}
    for ep in OPENAIP_ENDPOINTS:
        items, page = [], 1
        while True:
            j = get(ep, country, key, page)
            items += j.get("items") or []
            if page >= int(j.get("totalPages") or 1) or page >= 50:
                break
            page += 1
        out[ep] = items
    return out


# ---------- the stored maps ----------
def _path(mid):
    return os.path.join(VMAP_DIR, mid + ".json") if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", mid or "") else None


_lock = threading.Lock()
_cache = {}   # path -> (mtime_ns, size, parsed file): the list and the view are asked often, the files change rarely


def save(mid, coll):
    os.makedirs(VMAP_DIR, exist_ok=True)
    path = _path(mid)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(coll, f, separators=(",", ":"), ensure_ascii=False)
    for i in range(30):   # Windows: the file may be open for a moment (another VFO reading it)
        try:
            os.replace(tmp, path)
            break
        except PermissionError:
            if i == 29:
                raise
            time.sleep(0.1)
    _cache.pop(path, None)


GEO_KIND = {"Point": "point", "LineString": "line", "MultiLineString": "line", "Polygon": "area", "MultiPolygon": "area"}


def geo_counts(coll):
    """How many points, lines and areas a map has: {"point", "line", "area"}."""
    out = {"point": 0, "line": 0, "area": 0}
    for f in coll.get("features") or []:
        k = GEO_KIND.get((f.get("geometry") or {}).get("type"))
        if k:
            out[k] += 1
    return out


def summary(coll):
    """Counts per kind and part: {kind: {cat: n}}."""
    cats = {}
    for f in coll.get("features") or []:
        p = f.get("properties") or {}
        k = cats.setdefault(str(p.get("kind") or "other"), {})
        c = str(p.get("cat") or "other")
        k[c] = k.get(c, 0) + 1
    return cats


def _key(p):
    return f"{p.get('src') or 'x'}:{p.get('srcId') or p.get('name')}"


def _load(path):
    """A map file, freshly read (to be changed)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_ro(path):
    """A map file for reading only: parsed once until it changes (do not modify the answer)."""
    st = os.stat(path)
    c = _cache.get(path)
    if c and c[0] == st.st_mtime_ns and c[1] == st.st_size:
        return c[2]
    coll = _load(path)
    _cache[path] = (st.st_mtime_ns, st.st_size, coll)
    return coll


def keep_view(old, new):
    """Carries what was shown (view, hidden objects) from an older file of the map to a new download."""
    if not old:
        return new
    view = (old.get("radimcom") or {}).get("view")
    if view:
        new.setdefault("radimcom", {})["view"] = view
    hidden = {_key(f.get("properties") or {}) for f in old.get("features") or [] if (f.get("properties") or {}).get("hidden")}
    for f in new.get("features") or []:
        p = f.get("properties") or {}
        if _key(p) in hidden:
            p["hidden"] = True
    return new


def get_view(maps=None):
    """What is shown, from all stored maps: {cats, lbl, maxFL, maps {id: bool}, hidden [keys], stored}."""
    view = {"cats": {}, "lbl": {}, "maxFL": 0, "style": {}, "srcs": {}, "maps": {}, "hidden": [], "stored": False}
    if not os.path.isdir(VMAP_DIR):
        return view
    for fn in sorted(os.listdir(VMAP_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            coll = _load_ro(os.path.join(VMAP_DIR, fn))
        except (OSError, ValueError):
            continue
        v = (coll.get("radimcom") or {}).get("view")
        if isinstance(v, dict):
            if not view["stored"]:
                view.update(cats=v.get("cats") or {}, lbl=v.get("lbl") or {}, maxFL=v.get("maxFL") or 0,
                            style=v.get("style") or {}, srcs=v.get("srcs") or {}, stored=True)
            view["maps"][fn[:-5]] = v.get("on", True) is not False
        view["hidden"] += [_key(f.get("properties") or {}) for f in coll.get("features") or [] if (f.get("properties") or {}).get("hidden")]
    return view


STYLE_KEYS = {"c": "color", "fc": "color", "lc": "color", "d": ("solid", "dash", "long", "dot", "dashdot"),
              "sym": ("circle", "square", "diamond", "triangle", "cross", "ad", "ad_civil", "ad_mil", "heli", "glider", "ul", "closed",
                      "vor", "vordme", "vortac", "tacan", "dme", "ndb", "ndbdme", "rp", "rp_opt", "obst", "wind", "mast"), "w": (0.5, 10), "o": (0, 1), "fo": (0, 1),
              "r": (1, 20), "ls": (6, 24), "lz": (1, 18), "sz": (1, 18), "cz": (1, 18), "fz": (1, 18), "sx": (1, 18), "lx": (1, 18), "cx": (1, 18), "fx": (1, 18)}


def clean_style(style):
    """{"kind.cat": {key: value}} with only known keys and sane values."""
    out = {}
    for part, st in (style or {}).items() if isinstance(style, dict) else ():
        if not isinstance(st, dict) or not re.fullmatch(r"[\w-]{1,20}\.[\w-]{1,30}", str(part)):
            continue
        ok = {}
        for k, v in st.items():
            rule = STYLE_KEYS.get(k)
            if rule == "color" and isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v):
                ok[k] = v
            elif isinstance(rule, tuple) and isinstance(rule[0], str) and v in rule:
                ok[k] = v
            elif isinstance(rule, tuple) and isinstance(v, (int, float)) and not isinstance(v, bool) and rule[0] <= v <= rule[1]:
                ok[k] = v
        if ok:
            out[str(part)] = ok
    return out


def set_view(view):
    """Stores what is shown into every map file (the same cats / lbl / maxFL in all, on and hidden per map)."""
    def bools(x):
        return {str(k)[:80]: bool(b) for k, b in (x or {}).items()} if isinstance(x, dict) else {}
    cats, lbl, maps, srcs = bools(view.get("cats")), bools(view.get("lbl")), bools(view.get("maps")), bools(view.get("srcs"))
    try:
        max_fl = int(view.get("maxFL") or 0)
    except (TypeError, ValueError):
        max_fl = 0
    hidden = {str(k) for k in view.get("hidden") or [] if isinstance(k, str)}
    style = clean_style(view.get("style"))
    if not os.path.isdir(VMAP_DIR):
        return
    with _lock:
        for fn in sorted(os.listdir(VMAP_DIR)):
            if not fn.endswith(".json") or not _path(fn[:-5]):
                continue
            try:
                coll = _load(os.path.join(VMAP_DIR, fn))
            except (OSError, ValueError):
                continue
            meta = coll.setdefault("radimcom", {})
            view = {"on": maps.get(fn[:-5], True), "cats": cats, "lbl": lbl, "maxFL": max_fl, "style": style, "srcs": srcs}
            changed = meta.get("view") != view
            meta["view"] = view
            for f in coll.get("features") or []:
                p = f.setdefault("properties", {})
                if _key(p) in hidden:
                    changed = changed or not p.get("hidden")
                    p["hidden"] = True
                elif "hidden" in p:
                    changed = True
                    del p["hidden"]
            if changed:   # only the files that differ are written again
                save(fn[:-5], coll)


def list_maps():
    out = []
    if not os.path.isdir(VMAP_DIR):
        return out
    for fn in sorted(os.listdir(VMAP_DIR)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(VMAP_DIR, fn)
        try:
            coll = _load_ro(path)
            meta = coll.get("radimcom") or {}
            fetched = meta.get("fetched") or round(os.path.getmtime(path))
            out.append({"id": fn[:-5], "name": meta.get("name") or fn[:-5], "source": meta.get("source") or "",
                        "country": meta.get("country") or "", "fetched": fetched,
                        "stale": time.time() - fetched > STALE_S, "license": meta.get("license") or "",
                        "attribution": meta.get("attribution") or "", "n": len(coll.get("features") or []),
                        "size": os.path.getsize(path), "cats": summary(coll), "catNames": meta.get("catNames") or {},
                        "geo": geo_counts(coll)})
        except (OSError, ValueError, AttributeError, TypeError):
            continue
    return out


def _openaip_key():
    try:
        with open(MAPKEYS_PATH, encoding="utf-8") as f:
            return str((json.load(f) or {}).get("openaip") or "").strip()
    except (OSError, ValueError, AttributeError):
        return ""


def openaip_update(country, key=None):
    """Downloads a country from openAIP and stores it as openaip_<CC>. Answers the list entry."""
    country = _country(country)
    key = key or _openaip_key()
    if not key:
        raise ValueError("the openAIP API key is missing (free account at openaip.net)")
    return _store(f"openaip_{country}", openaip_collection(country, openaip_download(country, key)))


def _store(mid, coll):
    """Stores a downloaded map, keeping what was shown and hidden (a new map: shown as the other maps say)."""
    try:
        old = _load(_path(mid))
    except (OSError, ValueError):
        old = None
    if old is None:
        v = get_view()
        if v["stored"]:
            coll["radimcom"]["view"] = {"on": True, "cats": v["cats"], "lbl": v["lbl"], "maxFL": v["maxFL"], "style": v["style"], "srcs": v["srcs"]}
    save(mid, keep_view(old, coll))
    return next((m for m in list_maps() if m["id"] == mid), {"id": mid})


def _country(country):
    country = str(country or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("a country is two letters (ISO 3166, e.g. SK)")
    return country


# ---------- OurAirports ----------
OURAIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/"
OURAIRPORTS_FILES = ("airports.csv", "airport-frequencies.csv", "runways.csv", "navaids.csv")
OURAIRPORTS_DIR = os.path.join(VMAP_DIR, "_ourairports")
OURAIRPORTS_KEEP_S = 86400        # the world files are downloaded again after a day
OURAIRPORTS_ATTR = '<a href="https://ourairports.com" target="_blank" rel="noopener noreferrer">OurAirports</a> (public domain)'
OURAIRPORTS_CAT = {"large_airport": "large", "medium_airport": "medium", "small_airport": "small", "heliport": "heli",
                   "seaplane_base": "water", "balloonport": "balloon", "closed": "closed"}
OURAIRPORTS_NAV = {"VOR": "VOR", "VOR-DME": "VOR-DME", "VORTAC": "VORTAC", "DME": "DME", "NDB": "NDB", "NDB-DME": "NDB-DME",
                   "TACAN": "TACAN"}
_oa_lock = threading.Lock()


def _ft_m(v):
    f = _num(v)
    return None if f is None else round(f * 0.3048)


def _oa_point(lat, lon):
    la, lo = _num(lat), _num(lon)
    if la is None or lo is None or not (-90 <= la <= 90 and -180 <= lo <= 180):
        return None
    return {"type": "Point", "coordinates": [round(lo, 6), round(la, 6)]}


def _oa_feature(kind, cat, row, geom, extra):
    p = {"kind": kind, "cat": cat, "name": str(row.get("name") or "").strip(), "src": "ourairports", "srcId": str(row.get("id") or "")}
    for k, v in extra.items():
        if v not in (None, "", []):
            p[k] = v
    return {"type": "Feature", "geometry": geom, "properties": p}


def ourairports_collection(country, tables, fetched=None):
    """The map file of one country from the OurAirports tables {file name: [row dict, ...]}."""
    airports = [r for r in tables.get("airports.csv") or [] if r.get("iso_country") == country]
    ids = {r.get("id") for r in airports}
    freqs, rwys = {}, {}
    for r in tables.get("airport-frequencies.csv") or []:
        if r.get("airport_ref") in ids and _num(r.get("frequency_mhz")) is not None:
            fr = {"f": round(_num(r["frequency_mhz"]), 6)}
            if r.get("description"):
                fr["name"] = r["description"].strip()
            if r.get("type"):
                fr["type"] = r["type"].strip().upper()
            freqs.setdefault(r["airport_ref"], []).append(fr)
    strips = []
    for r in tables.get("runways.csv") or []:
        if r.get("airport_ref") in ids and r.get("closed") != "1":
            d = "/".join(x for x in (r.get("le_ident"), r.get("he_ident")) if x)
            if d:
                rwys.setdefault(r["airport_ref"], []).append(d)
            a, b = _oa_point(r.get("le_latitude_deg"), r.get("le_longitude_deg")), _oa_point(r.get("he_latitude_deg"), r.get("he_longitude_deg"))
            w = _num(r.get("width_ft"))
            geom = strip_poly([a["coordinates"], b["coordinates"]], w * 0.3048 if w and 10 <= w <= 500 else RUNWAY_WIDTH_M) if a and b else None
            if geom:   # the runway on the ground when both its ends are known
                strips.append({"type": "Feature", "geometry": geom, "properties": {
                    "kind": "aero", "cat": "runway", "name": d, "src": "ourairports", "srcId": f"rwy{r.get('id')}",
                    **({"remarks": r["surface"]} if r.get("surface") else {}), **({"ident": r["airport_ident"]} if r.get("airport_ident") else {})}})
    feats = []
    for r in airports:
        geom = _oa_point(r.get("latitude_deg"), r.get("longitude_deg"))
        if not geom:
            continue
        ident = r.get("icao_code") or r.get("gps_code") or r.get("ident")
        feats.append(_oa_feature("airport", OURAIRPORTS_CAT.get(r.get("type"), "small"), r, geom, {
            "ident": ident, "iata": r.get("iata_code"), "elev": _ft_m(r.get("elevation_ft")), "freq": freqs.get(r.get("id"), []),
            "rwy": rwys.get(r.get("id"), []), "remarks": r.get("municipality")}))
    feats += strips
    for r in tables.get("navaids.csv") or []:
        if r.get("iso_country") != country:
            continue
        geom = _oa_point(r.get("latitude_deg"), r.get("longitude_deg"))
        khz = _num(r.get("frequency_khz"))
        if not geom:
            continue
        feats.append(_oa_feature("navaid", OURAIRPORTS_NAV.get(r.get("type"), "VOR"), dict(r, id=f"nav{r.get('id') or ''}"), geom, {   # ids of their own
            "ident": r.get("ident"), "freq": [{"f": round(khz / 1000, 6)}] if khz else [], "channel": r.get("dme_channel"),
            "elev": _ft_m(r.get("elevation_ft"))}))
    return {"type": "FeatureCollection", "radimcom": {
        "version": VERSION, "name": f"OurAirports {country}", "source": "ourairports", "country": country,
        "fetched": round(fetched or time.time()), "license": "Public domain", "attribution": OURAIRPORTS_ATTR},
        "features": feats}


def _oa_fetch(name):
    req = urllib.request.Request(OURAIRPORTS_URL + name, headers={"User-Agent": "RADIMCOM"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def ourairports_tables(fetch=_oa_fetch, now=None):
    """The OurAirports world tables, downloaded again when older than a day. Answers ({name: rows}, fetched)."""
    now = now or time.time()
    with _oa_lock:
        os.makedirs(OURAIRPORTS_DIR, exist_ok=True)
        tables, fetched = {}, now
        for name in OURAIRPORTS_FILES:
            path = os.path.join(OURAIRPORTS_DIR, name)
            if not os.path.exists(path) or now - os.path.getmtime(path) > OURAIRPORTS_KEEP_S:
                raw = fetch(name)
                if not raw.lstrip().startswith(b'"id"') and not raw.lstrip().startswith(b"id,"):
                    raise ValueError(f"OurAirports sent no CSV for {name}")
                with open(path + ".tmp", "wb") as f:
                    f.write(raw)
                os.replace(path + ".tmp", path)
            fetched = min(fetched, os.path.getmtime(path))
            with open(path, encoding="utf-8-sig", newline="") as f:
                tables[name] = list(csv.DictReader(io.StringIO(f.read())))
        return tables, fetched


def ourairports_update(country, fetch=_oa_fetch):
    """Cuts a country out of OurAirports and stores it as ourairports_<CC>. Answers the list entry."""
    country = _country(country)
    tables, fetched = ourairports_tables(fetch)
    coll = ourairports_collection(country, tables, fetched)
    if not coll["features"]:
        raise ValueError(f"OurAirports has nothing for {country}")
    return _store(f"ourairports_{country}", coll)


# ---------- OpenStreetMap (Overpass): transmitter sites ----------
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSM_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors (ODbL)'
OSM_TX_QUERY = """[out:json][timeout:300];
area["ISO3166-1"="{cc}"][admin_level=2]->.a;
(
  nwr["man_made"~"^(mast|tower|antenna|communications_tower)$"]["tower:type"~"communication|broadcast|radar|radio|television"](area.a);
  nwr["man_made"~"^(mast|tower|antenna|communications_tower)$"]["communication:radio"](area.a);
  nwr["man_made"~"^(mast|tower|antenna|communications_tower)$"]["communication:television"](area.a);
  nwr["man_made"~"^(mast|tower|antenna|communications_tower)$"]["communication:mobile_phone"](area.a);
  nwr["man_made"~"^(mast|tower|antenna|communications_tower)$"]["communication:amateur_radio"](area.a);
  nwr["man_made"="communications_tower"](area.a);
  nwr["man_made"="antenna"](area.a);
);
out center tags;
(
  way["aeroway"~"^(aerodrome|runway|taxiway|apron|helipad)$"](area.a);
  relation["aeroway"="aerodrome"](area.a);
);
out geom tags;"""


def _yes(v):
    return str(v or "").strip().lower() not in ("", "no", "0", "false")


def osm_tx_cat(tags):
    """The part of the tree of a transmitter site: bcast, mobile, radar, ham or comm (any other radio)."""
    tt = str(tags.get("tower:type") or "").lower()
    if _yes(tags.get("communication:television")) or _yes(tags.get("communication:radio")) or "broadcast" in tt or "television" in tt:
        return "bcast"
    if "radar" in tt or tags.get("man_made") == "radar":
        return "radar"
    if _yes(tags.get("communication:amateur_radio")):
        return "ham"
    if _yes(tags.get("communication:mobile_phone")):
        return "mobile"
    return "comm"


def _height(v):
    m = re.match(r"\s*([\d.]+)", str(v or ""))
    return round(float(m.group(1))) if m else None


def osm_tx_feature(el):
    tags = el.get("tags") or {}
    if "lat" in el and "lon" in el:
        la, lo = el["lat"], el["lon"]
    else:
        c = el.get("center") or {}
        la, lo = c.get("lat"), c.get("lon")
    geom = _oa_point(la, lo)
    if not geom:
        return None
    cat = osm_tx_cat(tags)
    name = tags.get("name") or tags.get("description") or ""
    what = [k.split(":", 1)[1].replace("_", " ") for k in ("communication:television", "communication:radio", "communication:mobile_phone",
                                                           "communication:amateur_radio", "communication:microwave") if _yes(tags.get(k))]
    p = {"kind": "tx", "cat": cat, "name": str(name).strip(), "src": "osm", "srcId": f"{str(el.get('type') or 'n')[:1]}{el.get('id')}"}
    for k, v in (("ident", tags.get("ref")), ("height", _height(tags.get("height"))), ("elev", _height(tags.get("ele"))),
                 ("operator", tags.get("operator")), ("remarks", ", ".join(what) or tags.get("tower:type"))):
        if v not in (None, ""):
            p[k] = v
    return {"type": "Feature", "geometry": geom, "properties": p}


# ---------- the layout of aerodromes (runways, taxiways, aprons): OpenStreetMap and OurAirports ----------
RUNWAY_WIDTH_M = 45                # a runway without its width
AERO_WIDTH_M = {"runway": 45, "taxiway": 0, "helipad": 20}


def _width_m(v, default):
    m = re.match(r"\s*([\d.]+)\s*(ft|')?", str(v or ""))
    if not m:
        return default
    w = float(m.group(1)) * (0.3048 if m.group(2) else 1)
    return w if 3 <= w <= 150 else default


def strip_poly(coords, width_m):
    """A line [[lon, lat], ...] widened to a strip width_m wide: one rectangle per segment (a runway as it is on the
    ground). Answers a Polygon or a MultiPolygon."""
    import math
    quads = []
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        k = math.cos(math.radians((y1 + y2) / 2)) or 1e-9
        dx, dy = (x2 - x1) * k * 111320, (y2 - y1) * 110540   # metres east / north
        n = math.hypot(dx, dy)
        if n < 1:
            continue
        ox, oy = -dy / n * width_m / 2, dx / n * width_m / 2   # half the width, across the segment
        ex, ey = ox / (k * 111320), oy / 110540
        ring = [[x1 + ex, y1 + ey], [x2 + ex, y2 + ey], [x2 - ex, y2 - ey], [x1 - ex, y1 - ey]]
        ring = [[round(a, 7), round(b, 7)] for a, b in ring]
        quads.append([ring + [ring[0]]])
    if not quads:
        return None
    return {"type": "Polygon", "coordinates": quads[0]} if len(quads) == 1 else {"type": "MultiPolygon", "coordinates": quads}


def _ring(geom):
    pts = [[round(p["lon"], 7), round(p["lat"], 7)] for p in geom or [] if isinstance(p, dict) and "lat" in p and "lon" in p]
    return pts if len(pts) >= 2 else None


def osm_aero_features(el):
    """The aerodrome layout from one OpenStreetMap way or relation (out geom): areas, runway strips, taxiway lines."""
    tags = el.get("tags") or {}
    cat = tags.get("aeroway")
    rings = []
    if el.get("type") == "way":
        r = _ring(el.get("geometry"))
        if r:
            rings.append(r)
    elif el.get("type") == "relation":   # an aerodrome made of more ways: its closed outer ways
        for m in el.get("members") or []:
            r = _ring(m.get("geometry")) if isinstance(m, dict) and m.get("role") in ("outer", "") else None
            if r and r[0] == r[-1]:
                rings.append(r)
    out = []
    for i, r in enumerate(rings):
        closed = len(r) >= 4 and r[0] == r[-1]
        if cat == "taxiway":
            geom = {"type": "LineString", "coordinates": r}
        elif cat in ("runway", "helipad") and not (closed and tags.get("area") == "yes") and not (cat == "helipad" and closed):
            geom = strip_poly(r, _width_m(tags.get("width"), AERO_WIDTH_M.get(cat, 30)))
        elif closed:
            geom = {"type": "Polygon", "coordinates": [r]}
        else:
            geom = None
        if not geom:
            continue
        p = {"kind": "aero", "cat": cat, "name": str(tags.get("ref") or tags.get("name") or "").strip(),
             "src": "osm", "srcId": f"{str(el.get('type') or 'w')[:1]}{el.get('id')}" + (f"_{i}" if i else "")}
        if cat == "aerodrome":
            p["name"] = str(tags.get("name") or tags.get("icao") or "").strip()
            if tags.get("icao"):
                p["ident"] = tags["icao"]
        for k, v in (("remarks", tags.get("surface")), ("width", _width_m(tags.get("width"), None))):
            if v not in (None, ""):
                p[k] = round(v) if isinstance(v, float) else v
        out.append({"type": "Feature", "geometry": geom, "properties": p})
    return out


def osm_tx_collection(country, elements, fetched=None):
    feats, seen = [], set()
    for el in elements or []:
        if isinstance(el, dict) and (el.get("tags") or {}).get("aeroway"):
            for f in osm_aero_features(el):
                if f["properties"]["srcId"] not in seen:
                    seen.add(f["properties"]["srcId"])
                    feats.append(f)
            continue
        if isinstance(el, dict):
            f = osm_tx_feature(el)
            if f and f["properties"]["srcId"] not in seen:
                seen.add(f["properties"]["srcId"])
                feats.append(f)
    return {"type": "FeatureCollection", "radimcom": {
        "version": VERSION, "name": f"OpenStreetMap {country}", "source": "osm", "country": country,
        "fetched": round(fetched or time.time()), "license": "ODbL", "attribution": OSM_ATTR}, "features": feats}


def _overpass(query):
    req = urllib.request.Request(OVERPASS_URL, data=urllib.parse.urlencode({"data": query}).encode(),
                                 headers={"User-Agent": "RADIMCOM", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=330) as r:
        return json.loads(r.read().decode("utf-8"))


def osm_update(country, get=_overpass):
    """Downloads the transmitter sites of a country from OpenStreetMap and stores them as osm_<CC>."""
    country = _country(country)
    coll = osm_tx_collection(country, (get(OSM_TX_QUERY.replace("{cc}", country)) or {}).get("elements"))
    if not coll["features"]:
        raise ValueError(f"OpenStreetMap has no transmitter sites or aerodromes for {country}")
    return _store(f"osm_{country}", coll)


# ---------- MEMORIES: the channels with a location ----------
MEMORIES_ID = "memories"


def _group_cat(name):
    """A part id for a group name (any characters): short and safe for the settings keys."""
    return "g" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8] if name else "nogroup"


def memories_collection(items, fetched=None):
    """The map of the MEMORIES channels that have a location, one part per (first) group."""
    feats, names = [], {}
    for m in items or []:
        if not isinstance(m, dict):
            continue
        geom = _oa_point(m.get("lat"), m.get("lon"))
        if not geom:
            continue
        groups = m.get("groups") or ([m["group"]] if m.get("group") else [])
        g = str(groups[0]) if groups else ""
        cat = _group_cat(g)
        names[cat] = g or "(no group)"
        f_hz = _num(m.get("freq_hz"))
        p = {"kind": "chan", "cat": cat, "name": str(m.get("name") or "").strip(), "src": "memories", "srcId": str(m.get("id") or "")}
        if f_hz:
            p["freq"] = [{"f": round(f_hz / 1e6, 6), "type": str(m.get("mode") or "")}]
        if m.get("note"):
            p["remarks"] = str(m["note"])[:200]
        if len(groups) > 1:
            p["groups"] = [str(x) for x in groups]
        feats.append({"type": "Feature", "geometry": geom, "properties": p})
    return {"type": "FeatureCollection", "radimcom": {
        "version": VERSION, "name": "MEMORIES channels", "source": "memories", "country": "",
        "fetched": round(fetched or time.time()), "license": "", "attribution": "", "catNames": names}, "features": feats}


def _memories_path():
    import memories   # the frequency memories of RADIMCOM
    return memories.PATH, memories.load


def memories_update():
    """Makes the map of the MEMORIES channels again (shown / hidden objects kept)."""
    path, load = _memories_path()
    return _store(MEMORIES_ID, memories_collection(load(), os.path.getmtime(path) if os.path.exists(path) else None))


def memories_sync():
    """Makes the MEMORIES map again when memories.json changed since (only when that map was made)."""
    mp = _path(MEMORIES_ID)
    if not os.path.exists(mp):
        return
    try:
        path, _ = _memories_path()
        if os.path.exists(path) and os.path.getmtime(path) > os.path.getmtime(mp):
            memories_update()
    except (OSError, ValueError, ImportError):
        pass


# ---------- FUA: the activated airspaces of Slovakia (LPS SR, the map gis.lps.sk/vfrm) ----------
# a public ArcGIS layer of the activations from the AUP / UUP (AMC Zvolen) and the national areas, updated every
# 2 minutes; one feature per activation window (start / end in UTC). No key. Refreshed by the server while the map exists.
FUA_ID = "fua_SK"
FUA_URL = ("https://gis.lps.sk/server/rest/services/Hosted/Reservation_(Public)2/FeatureServer/0/query"
           "?where=1%3D1&outFields=*&outSR=4326&f=geojson")
FUA_REFRESH_S = 120
_fua_busy = threading.Lock()


def _fua_fetch():
    req = urllib.request.Request(FUA_URL, headers={"User-Agent": "RADIMCOM", "Accept": "application/geo+json, application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _fua_limit(val, uom, unit):
    """A vertical limit of the layer as {"v", "u", "ref"} (as the airspaces of openAIP)."""
    if str(uom or "").upper() in ("GND", "SFC") and val in (None, "", 0):
        return {"v": 0, "u": "ft", "ref": "GND"}   # the ground (the layer leaves the number out)
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    v = int(v) if v == int(v) else v
    uom, unit = str(uom or "").upper(), str(unit or "").upper()
    if unit == "FL" or not uom:
        return {"v": v, "u": "FL", "ref": "STD"}
    return {"v": v, "u": "ft", "ref": "GND" if uom in ("GND", "SFC", "AGL") else "MSL"}


def _fua_limit_text(t):
    """A limit from the text of the layer ("GND", "5000 FEET", "125 FL", "FL 95", "3000 FT AGL") when no number is given."""
    t = str(t or "").upper().strip()
    if not t:
        return None
    if t in ("GND", "SFC", "0", "0 GND"):
        return {"v": 0, "u": "ft", "ref": "GND"}
    m = re.search(r"FL\s*(\d+)|(\d+)\s*FL", t)
    if m:
        return {"v": int(m.group(1) or m.group(2)), "u": "FL", "ref": "STD"}
    m = re.search(r"(\d+)\s*(FEET|FT|M)\b", t)
    if m:
        return {"v": int(m.group(1)), "u": "m" if m.group(2) == "M" else "ft", "ref": "GND" if re.search(r"AGL|GND|SFC", t) else "MSL"}
    return None


def fua_collection(gj, now=None):
    """The activations as kind "fua": part "active" (now inside its window) or "planned" (later today); past ones left out."""
    now = now or time.time()
    feats = []
    for f in (gj or {}).get("features") or []:
        p, g = f.get("properties") or {}, f.get("geometry")
        if not isinstance(g, dict) or g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        try:
            start, end = float(p.get("startdate")) / 1000, float(p.get("enddate")) / 1000
        except (TypeError, ValueError):
            continue
        if end <= now:
            continue
        name = str(p.get("airspace") or p.get("label") or "").strip()
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(t))
        props = {"kind": "fua", "cat": "active" if start <= now else "planned", "name": name,
                 "src": "fua", "srcId": name,   # the same area on any day: hidden / own note kept
                  "start": iso(start), "end": iso(end),
                 "type": p.get("type_code") or "", "activity": p.get("activity_code") or "", "mil": p.get("mil_code") or "",
                 "place": p.get("label2") or "", "origin": p.get("airspace_type") or "",
                 "lower": _fua_limit(p.get("lower_val"), p.get("lower_uom"), "FL" if "FL" in (str(p.get("lower_fl")).upper(), str(p.get("lower_ft")).upper()) else "") or _fua_limit_text(p.get("base")),
                 "upper": _fua_limit(p.get("upper_val"), p.get("upper_uom"), "FL" if "FL" in (str(p.get("upper_fl")).upper(), str(p.get("upper_ft")).upper()) else "") or _fua_limit_text(p.get("top_"))}
        feats.append({"type": "Feature", "geometry": g, "properties": {k: v for k, v in props.items() if v not in ("", None)}})
    return {"type": "FeatureCollection", "features": feats,
            "radimcom": {"version": 1, "name": "FUA Slovakia (LPS SR)", "source": "fua", "country": "SK", "fetched": round(now),
                         "license": "LPS SR, gis.lps.sk/vfrm (check with the ATS unit before flying)", "attribution": "FUA © LPS SR"}}


def fua_update(get=_fua_fetch, now=None):
    """Downloads the activations and stores them as fua_SK (also when none is active: an empty map)."""
    gj = get()
    if not isinstance(gj, dict) or "features" not in gj:
        raise ValueError("the FUA layer answered nothing usable")
    return _store(FUA_ID, fua_collection(gj, now))


def fua_sync():
    """Downloads the activations again (in the background) when the FUA map exists and is older than FUA_REFRESH_S."""
    mp = _path(FUA_ID)
    try:
        if not os.path.exists(mp) or time.time() - os.path.getmtime(mp) < FUA_REFRESH_S:
            return
    except OSError:
        return
    if not _fua_busy.acquire(blocking=False):
        return

    def run():
        try:
            fua_update()
        except (OSError, ValueError, urllib.error.URLError):
            try:
                os.utime(mp)   # offline: try again after FUA_REFRESH_S, the last activations stay
            except OSError:
                pass
        finally:
            _fua_busy.release()
    threading.Thread(target=run, daemon=True).start()


# ---------- own files ----------
OWN_MAX = 30 * 1024 * 1024        # bytes of one imported file (as JSON)
KINDS = ("airspace", "airport", "navaid", "point", "obstacle", "tx", "chan")


def _geoms(g):
    """A GeoJSON geometry split into the kinds drawn: Point, LineString, Polygon (Multi kept where drawn as one)."""
    if not isinstance(g, dict):
        return []
    t = g.get("type")
    if t in ("Point", "LineString", "MultiLineString", "Polygon", "MultiPolygon") and g.get("coordinates"):
        return [{"type": t, "coordinates": g["coordinates"]}]
    if t == "MultiPoint":
        return [{"type": "Point", "coordinates": c} for c in g.get("coordinates") or [] if isinstance(c, list) and len(c) >= 2]
    if t == "GeometryCollection":
        return [x for sub in g.get("geometries") or [] for x in _geoms(sub)]
    return []


def own_collection(name, gj, fetched=None):
    """The map file of an imported GeoJSON: objects in this format keep kind / cat, the others are own area / line / point."""
    feats_in = gj.get("features") if gj.get("type") == "FeatureCollection" else [gj] if gj.get("type") == "Feature" else []
    feats, n = [], 0
    for f in feats_in or []:
        if not isinstance(f, dict):
            continue
        props = f.get("properties") if isinstance(f.get("properties"), dict) else {}
        for g in _geoms(f.get("geometry")):
            n += 1
            gt = g["type"]
            if props.get("kind") in KINDS and props.get("cat"):
                p = {k: v for k, v in props.items() if k != "hidden"}
            else:
                cat = "point" if gt == "Point" else "line" if "Line" in gt else "area"
                nm = props.get("name") or props.get("Name") or props.get("title") or props.get("NAME") or props.get("desc") or ""
                p = {"kind": "own", "cat": cat, "name": str(nm).strip()[:120]}
                rem = props.get("description") or props.get("desc") or props.get("cmt")
                if rem and str(rem) != p["name"]:
                    p["remarks"] = re.sub(r"<[^>]+>", " ", str(rem))[:200].strip()
            p["src"], p["srcId"] = "file", str(n)
            feats.append({"type": "Feature", "geometry": g, "properties": p})
    return {"type": "FeatureCollection", "radimcom": {
        "version": VERSION, "name": name, "source": "file", "country": "", "fetched": round(fetched or time.time()),
        "license": "", "attribution": ""}, "features": feats}


def own_import(name, gj):
    """Stores an imported GeoJSON as file_<name> (the same name again replaces it, keeping what was hidden)."""
    name = str(name or "").strip()[:80]
    if not name or not isinstance(gj, dict) or gj.get("type") not in ("FeatureCollection", "Feature"):
        raise ValueError("a name and GeoJSON (FeatureCollection) are needed")
    coll = own_collection(name, gj)
    if not coll["features"]:
        raise ValueError("the file has no points, lines or areas")
    mid = "file_" + (re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:50] or "map")
    return _store(mid, coll)


# ---------- own names and notes of objects ----------
def load_notes():
    """{object key: {"name": str, "note": str}} (the key as the browser makes it: src:srcId)."""
    try:
        with open(NOTES_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def set_note(key, name, note):
    """Stores (or with both empty removes) the own name and note of one object; answers all notes."""
    key = str(key or "")[:200]
    if not key:
        raise ValueError("no object")
    name, note = str(name or "").strip()[:120], str(note or "").strip()[:2000]
    with _lock:
        notes = load_notes()
        if name or note:
            notes[key] = {k: v for k, v in (("name", name), ("note", note)) if v}
        else:
            notes.pop(key, None)
        os.makedirs(os.path.dirname(NOTES_PATH), exist_ok=True)
        tmp = NOTES_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=1)
        for i in range(30):   # Windows: the file may be open for a moment
            try:
                os.replace(tmp, NOTES_PATH)
                break
            except PermissionError:
                if i == 29:
                    raise
                time.sleep(0.1)
    return notes


# ---------- HTTP API ----------
@bp.route("/api/vectormaps", methods=["GET"])
def api_vectormaps():
    """The stored maps [{id, name, source, country, fetched, stale, n, size, cats: {kind: {cat: n}}}]."""
    memories_sync()
    fua_sync()
    return jsonify(maps=list_maps(), view=get_view(), notes=load_notes(), staleDays=STALE_S // 86400)


@bp.route("/api/vectormaps/view", methods=["POST"])
def api_vectormaps_view():
    """POST {cats, lbl, maxFL, maps {id: bool}, hidden [keys]}: what is shown, stored in the map files."""
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify(error="JSON object expected"), 400
    set_view(d)
    return jsonify(view=get_view())


@bp.route("/api/vectormaps/fua", methods=["POST"])
def api_vectormaps_fua():
    """POST: downloads the activated airspaces of Slovakia (LPS SR) as fua_SK; kept up to date while it exists."""
    try:
        return jsonify(map=fua_update())
    except (OSError, urllib.error.URLError) as e:
        return jsonify(error=f"gis.lps.sk: {e}"), 502
    except ValueError as e:
        return jsonify(error=str(e)), 502


@bp.route("/api/vectormaps/note", methods=["POST"])
def api_vectormaps_note():
    """POST {key, name, note}: the own name and note of an object (both empty: removed); answers {notes}."""
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify(error="JSON object expected"), 400
    try:
        return jsonify(notes=set_note(d.get("key"), d.get("name"), d.get("note")))
    except ValueError as e:
        return jsonify(error=str(e)), 400


@bp.route("/api/vectormaps/<mid>", methods=["GET", "DELETE"])
def api_vectormap(mid):
    """GET: the GeoJSON of a map. DELETE: removes it."""
    path = _path(mid)
    if not path or not os.path.exists(path):
        return jsonify(error="no such map"), 404
    if request.method == "DELETE":
        os.remove(path)
        return jsonify(ok=True)
    with open(path, encoding="utf-8") as f:
        return jsonify(json.load(f))


@bp.route("/api/vectormaps/openaip", methods=["POST"])
def api_vectormaps_openaip():
    """POST {"country": "SK"}: downloads that country from openAIP (key from data/mapkeys.json)."""
    d = request.get_json(silent=True) or {}
    try:
        return jsonify(map=openaip_update(d.get("country")))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except urllib.error.HTTPError as e:
        return jsonify(error=f"openAIP answered HTTP {e.code}" + (" (wrong API key?)" if e.code in (401, 403) else "")), 502
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return jsonify(error=f"openAIP not reachable: {getattr(e, 'reason', e)}"), 502


@bp.route("/api/vectormaps/ourairports", methods=["POST"])
def api_vectormaps_ourairports():
    """POST {"country": "SK"}: cuts that country out of OurAirports (the world files downloaded at most once a day)."""
    d = request.get_json(silent=True) or {}
    try:
        return jsonify(map=ourairports_update(d.get("country")))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except urllib.error.HTTPError as e:
        return jsonify(error=f"OurAirports answered HTTP {e.code}"), 502
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return jsonify(error=f"OurAirports not reachable: {getattr(e, 'reason', e)}"), 502


@bp.route("/api/vectormaps/osm", methods=["POST"])
def api_vectormaps_osm():
    """POST {"country": "SK"}: downloads the transmitter sites of that country from OpenStreetMap (Overpass API)."""
    d = request.get_json(silent=True) or {}
    try:
        return jsonify(map=osm_update(d.get("country")))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except urllib.error.HTTPError as e:
        return jsonify(error=f"Overpass answered HTTP {e.code}" + (" (busy, try again later)" if e.code in (429, 504) else "")), 502
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return jsonify(error=f"Overpass not reachable: {getattr(e, 'reason', e)}"), 502


@bp.route("/api/vectormaps/memories", methods=["POST"])
def api_vectormaps_memories():
    """POST: makes the map of the MEMORIES channels with a location (then kept up to date with memories.json)."""
    try:
        return jsonify(map=memories_update())
    except (OSError, ValueError) as e:
        return jsonify(error=f"MEMORIES not read: {e}"), 500


@bp.route("/api/vectormaps/file", methods=["POST"])
def api_vectormaps_file():
    """POST {"name", "geojson"}: stores an own file as a vector map (KML / GPX are turned into GeoJSON in the browser)."""
    if (request.content_length or 0) > OWN_MAX:
        return jsonify(error=f"the file is too big (over {OWN_MAX // 1048576} MB)"), 413
    d = request.get_json(silent=True) or {}
    try:
        return jsonify(map=own_import(d.get("name"), d.get("geojson")))
    except ValueError as e:
        return jsonify(error=str(e)), 400

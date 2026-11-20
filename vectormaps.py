"""Vector maps of the COMPOSITE map: airspaces, airports, navaids, reporting points and obstacles, kept offline.

The data is downloaded once per country (button Update in the map settings) and stored in data/vectormaps/, one file
per source and country, as GeoJSON with properties of the same names for every source:

    kind    airspace | airport | navaid | point | obstacle    (the group of the map settings tree)
    cat     the part of the group: CTR, TMA, R, D, ... / intl, civil, ul, ... / VOR-DME, NDB, ... (the tree's leaves)
    name, ident, cls (ICAO class A-G or SUA), elev (m MSL), height (m above ground, obstacles)
    freq    [{"f": MHz, "name": str, "type": str}]
    lower, upper    {"v": number, "u": "ft" | "m" | "FL", "ref": "GND" | "MSL" | "STD"}   (airspaces)
    src, srcId      where it comes from and its id there

The file's root object also holds "radimcom": {version, name, source, country, fetched (UNIX s), license,
attribution, view}. What is shown is kept in the files too, so it is the same in every browser and computer and travels
with the file: "view" = {on (this map), cats {"kind" | "kind.cat": bool}, lbl {kind: bool}, maxFL}, and a hidden
object has "hidden": true in its properties. Update keeps both (objects matched by their id in the source). Airspaces keep their polygons and vertical limits, so a later "track inside an airspace" test can use
the same files.

Sources: openAIP (https://www.openaip.net, CC BY-NC 4.0, free API key in data/mapkeys.json). The API has no area
filter, so it is asked per country.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import Blueprint, jsonify, request

from paths import data

VMAP_DIR = data("vectormaps")
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


def save(mid, coll):
    os.makedirs(VMAP_DIR, exist_ok=True)
    tmp = _path(mid) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(coll, f, separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp, _path(mid))


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
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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
    view = {"cats": {}, "lbl": {}, "maxFL": 0, "maps": {}, "hidden": [], "stored": False}
    if not os.path.isdir(VMAP_DIR):
        return view
    for fn in sorted(os.listdir(VMAP_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            coll = _load(os.path.join(VMAP_DIR, fn))
        except (OSError, ValueError):
            continue
        v = (coll.get("radimcom") or {}).get("view")
        if isinstance(v, dict):
            if not view["stored"]:
                view.update(cats=v.get("cats") or {}, lbl=v.get("lbl") or {}, maxFL=v.get("maxFL") or 0, stored=True)
            view["maps"][fn[:-5]] = v.get("on", True) is not False
        view["hidden"] += [_key(f.get("properties") or {}) for f in coll.get("features") or [] if (f.get("properties") or {}).get("hidden")]
    return view


def set_view(view):
    """Stores what is shown into every map file (the same cats / lbl / maxFL in all, on and hidden per map)."""
    def bools(x):
        return {str(k)[:80]: bool(b) for k, b in (x or {}).items()} if isinstance(x, dict) else {}
    cats, lbl, maps = bools(view.get("cats")), bools(view.get("lbl")), bools(view.get("maps"))
    try:
        max_fl = int(view.get("maxFL") or 0)
    except (TypeError, ValueError):
        max_fl = 0
    hidden = {str(k) for k in view.get("hidden") or [] if isinstance(k, str)}
    if not os.path.isdir(VMAP_DIR):
        return
    for fn in sorted(os.listdir(VMAP_DIR)):
        if not fn.endswith(".json") or not _path(fn[:-5]):
            continue
        try:
            coll = _load(os.path.join(VMAP_DIR, fn))
        except (OSError, ValueError):
            continue
        coll.setdefault("radimcom", {})["view"] = {"on": maps.get(fn[:-5], True), "cats": cats, "lbl": lbl, "maxFL": max_fl}
        for f in coll.get("features") or []:
            p = f.setdefault("properties", {})
            if _key(p) in hidden:
                p["hidden"] = True
            else:
                p.pop("hidden", None)
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
            with open(path, encoding="utf-8") as f:
                coll = json.load(f)
            meta = coll.get("radimcom") or {}
            fetched = meta.get("fetched") or round(os.path.getmtime(path))
            out.append({"id": fn[:-5], "name": meta.get("name") or fn[:-5], "source": meta.get("source") or "",
                        "country": meta.get("country") or "", "fetched": fetched,
                        "stale": time.time() - fetched > STALE_S, "license": meta.get("license") or "",
                        "attribution": meta.get("attribution") or "", "n": len(coll.get("features") or []),
                        "size": os.path.getsize(path), "cats": summary(coll)})
        except (OSError, ValueError, AttributeError):
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
    country = str(country or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("a country is two letters (ISO 3166, e.g. SK)")
    key = key or _openaip_key()
    if not key:
        raise ValueError("the openAIP API key is missing (free account at openaip.net)")
    coll = openaip_collection(country, openaip_download(country, key))
    mid = f"openaip_{country}"
    try:
        old = _load(_path(mid))
    except (OSError, ValueError):
        old = None
    if old is None:   # a new country: shown as the other maps say
        v = get_view()
        if v["stored"]:
            coll["radimcom"]["view"] = {"on": True, "cats": v["cats"], "lbl": v["lbl"], "maxFL": v["maxFL"]}
    save(mid, keep_view(old, coll))
    return next((m for m in list_maps() if m["id"] == mid), {"id": mid})


# ---------- HTTP API ----------
@bp.route("/api/vectormaps", methods=["GET"])
def api_vectormaps():
    """The stored maps [{id, name, source, country, fetched, stale, n, size, cats: {kind: {cat: n}}}]."""
    return jsonify(maps=list_maps(), view=get_view(), staleDays=STALE_S // 86400)


@bp.route("/api/vectormaps/view", methods=["POST"])
def api_vectormaps_view():
    """POST {cats, lbl, maxFL, maps {id: bool}, hidden [keys]}: what is shown, stored in the map files."""
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return jsonify(error="JSON object expected"), 400
    set_view(d)
    return jsonify(view=get_view())


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

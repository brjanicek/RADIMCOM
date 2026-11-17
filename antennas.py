"""Antennas of the station (SETTINGS › GENERAL › ANTENNAS), shared by all VFOs: file data\\antennas.json.

Each VFO says which antenna it uses (cfg["antenna"] = the id of an antenna here, "" = not set; SETTINGS › VFO › SDR DONGLE).
The page lights ANT in the VFO window while the tuned frequency is within the range of that antenna and shows it amber
outside of it. Later the community (MQTT) sends the antenna with the VFO settings, so others know what it was received on.

{"antennas": [{"id": "x50", "name": "Diamond X-50", "type": "collinear", "ranges": [[144e6, 146e6], [430e6, 440e6]],
               "pol": "V", "gain_dbi": 4.5, "outdoor": true, "height_m": 12, "rotor": false, "chain": "LNA 20 dB", "note": ""}]}
"ranges" = the bands the antenna works on, [lowest Hz, highest Hz] each (a multiband dipole or a dual-band vertical has
several; [] = not given). Files of the first version had one range as "f_min_hz" / "f_max_hz": taken over as one band.
"""
import json
import os
import re
import threading

from paths import data

ANTENNAS_PATH = data("antennas.json")

TYPES = ("discone", "vertical", "ground_plane", "dipole", "yagi", "log_periodic", "longwire", "random_wire",
         "loop", "mag_loop", "qfh", "turnstile", "patch", "helix", "active_whip", "collinear", "indoor", "other")
POLARIZATIONS = ("", "V", "H", "V/H", "RHCP", "LHCP")
MAX_ANTENNAS = 50
MAX_RANGES = 16
F_MAX_HZ = 100e9

_lock = threading.Lock()
_cache = [None, []]          # (mtime, size) of the file, the list read from it


def _text(v, n):
    return str(v if v is not None else "").strip()[:n]


def _num(v, lo, hi, what):
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a number") from None
    if not lo <= x <= hi:
        raise ValueError(f"{what} must be {lo:g} to {hi:g}")
    return x


def _ranges(a, name):
    """The bands of an antenna: [[lo, hi], ...] in Hz, sorted. Also takes the single f_min_hz / f_max_hz of the first version."""
    raw = a.get("ranges")
    if raw is None and (a.get("f_min_hz") is not None or a.get("f_max_hz") is not None):
        raw = [[a.get("f_min_hz") or 0, a.get("f_max_hz") or F_MAX_HZ]]
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_RANGES:
        raise ValueError(f"{name}: at most {MAX_RANGES} bands")
    out = []
    for r in raw:
        if not isinstance(r, (list, tuple)) or len(r) != 2:
            raise ValueError(f"{name}: a band is a pair lowest - highest frequency")
        lo = _num(r[0], 0, F_MAX_HZ, f"{name}: lowest frequency of a band")
        hi = _num(r[1], 0, F_MAX_HZ, f"{name}: highest frequency of a band")
        if lo is None or hi is None or lo >= hi:
            raise ValueError(f"{name}: in each band the lowest frequency must be below the highest")
        out.append([lo, hi])
    return sorted(out)


def slug(name):
    """An id from the name: lower case letters, digits and dashes (the id stays when the name changes later)."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24]
    return s or "ant"


def clean(a, used=()):
    """One antenna from the page → checked dict. ValueError with the reason. used = ids already taken."""
    if not isinstance(a, dict):
        raise ValueError("an antenna must be an object")
    name = _text(a.get("name"), 40)
    if not name:
        raise ValueError("every antenna needs a name")
    aid = _text(a.get("id"), 24).lower()
    if aid and not re.fullmatch(r"[a-z0-9][a-z0-9-]*", aid):
        raise ValueError(f"bad antenna id {aid!r}")
    if not aid:
        base = aid = slug(name)
        n = 2
        while aid in used:
            aid = f"{base}-{n}"
            n += 1
    if aid in used:
        raise ValueError(f"antenna id {aid!r} is used twice")
    typ = _text(a.get("type"), 20) or "other"
    if typ not in TYPES:
        raise ValueError(f"unknown antenna type {typ!r}")
    pol = _text(a.get("pol"), 5)
    if pol not in POLARIZATIONS:
        raise ValueError(f"unknown polarization {pol!r}")
    return {
        "id": aid, "name": name, "type": typ, "ranges": _ranges(a, name), "pol": pol,
        "gain_dbi": _num(a.get("gain_dbi"), -40, 40, f"{name}: gain"),
        "outdoor": bool(a.get("outdoor", True)),
        "height_m": _num(a.get("height_m"), 0, 1000, f"{name}: height"),
        "rotor": bool(a.get("rotor", False)),
        "chain": _text(a.get("chain"), 80), "note": _text(a.get("note"), 200),
    }


def load():
    """The antennas of the station (a list, [] without the file or with a damaged one). Read again only when the file changed."""
    with _lock:
        try:
            st = os.stat(ANTENNAS_PATH)
            key = (st.st_mtime_ns, st.st_size)
        except OSError:
            _cache[:] = [None, []]
            return []
        if _cache[0] != key:
            try:
                with open(ANTENNAS_PATH, encoding="utf-8") as f:
                    raw = json.load(f).get("antennas", [])
                out, used = [], set()
                for a in raw[:MAX_ANTENNAS]:
                    try:
                        c = clean(a, used)
                    except ValueError:
                        continue                  # a broken entry (edited by hand) is left out, the rest stays
                    used.add(c["id"])
                    out.append(c)
            except (OSError, ValueError, AttributeError):
                out = []
            _cache[:] = [key, out]
        return [dict(a) for a in _cache[1]]


def save(items):
    """Replaces the whole list (from the ANTENNAS page). ValueError with the reason; returns the saved list."""
    if not isinstance(items, list):
        raise ValueError("antennas must be a list")
    if len(items) > MAX_ANTENNAS:
        raise ValueError(f"at most {MAX_ANTENNAS} antennas")
    out, used = [], set()
    for a in items:                     # given ids first, so a new antenna does not take an existing id
        if isinstance(a, dict) and _text(a.get("id"), 24):
            used.add(_text(a.get("id"), 24).lower())
    seen = set()
    for a in items:
        given = isinstance(a, dict) and _text(a.get("id"), 24).lower()
        c = clean(a, seen if given else used | seen)
        seen.add(c["id"])
        out.append(c)
    with _lock:
        tmp = f"{ANTENNAS_PATH}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"antennas": out}, f, indent=2, ensure_ascii=False)
        os.replace(tmp, ANTENNAS_PATH)
        _cache[0] = None
    return load()


def get(aid):
    """The antenna with this id, or None."""
    return next((a for a in load() if a["id"] == aid), None) if aid else None


def covers(a, hz):
    """True / False whether the frequency is in one of the bands of the antenna; None if it has no bands given."""
    if not a or not a.get("ranges"):
        return None
    return any(lo <= hz <= hi for lo, hi in a["ranges"])

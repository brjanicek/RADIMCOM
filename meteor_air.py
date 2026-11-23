"""METEORS on GRAVES: which aircraft an aircraft echo (kind "plane") was, from the public ADS-B network adsb.fi.

An aircraft reflects the GRAVES carrier (143.050 MHz) like a satellite does, only slower: its bistatic Doppler
f = -(F / c) d/dt (|plane - GRAVES| + |plane - station|) is at most ~±250 Hz. The aircraft that can be seen from both
GRAVES and the station fly around the middle of the path (from western Slovakia: over southern Germany), so adsb.fi is
asked once per aircraft echo for the aircraft within AIR_DIST_NM of that middle point (only that point is sent, not
the station). Each position is moved to the moments of the echo with its ground speed, track and climb rate, its
Doppler there is compared with the measured track of the echo, and the best fit is the aircraft.

The receiver offset matters here (the whole Doppler is only a few hundred Hz): it is taken as known within
AIR_OFFSET_TOL_HZ (meteor.py learns it from the satellites it identified, otherwise 0 = a calibrated receiver).
"""
import json
import math
import threading
import time
import urllib.request

import numpy as np

from meteor_sat import EARTH_A_KM, _site, bistatic_doppler

URLS = ("https://opendata.adsb.fi/api/v2/lat/{lat:.4f}/lon/{lon:.4f}/dist/{dist}",
        "https://api.adsb.lol/v2/point/{lat:.4f}/{lon:.4f}/{dist}")
AIR_DIST_NM = 250               # the largest radius adsb.fi answers
CACHE_S = 8.0                   # one answer serves the echoes of these seconds
GAP_S = 1.1                     # adsb.fi allows 1 request per second
TIMEOUT_S = 10
MAX_BYTES = 8_000_000
MAX_AGE_S = 90.0                # a position older than this (before the echo) is not moved that far
AIR_RMS_HZ = 30.0               # a fit worse than this is no identification
AIR_OFFSET_TOL_HZ = 40.0        # the receiver offset may differ this much from the known one
AIR_POINTS = 40
K_EARTH = 4.0 / 3.0             # radio horizon over the standard atmosphere
HORIZON_EXTRA_KM = 200.0        # and diffraction beyond it (GRAVES is strong)
FT = 0.3048
KT = 0.514444

_lock = threading.Lock()
_cache = {"t": 0.0, "key": None, "data": None, "last": 0.0, "error": ""}


def midpoint(lat1, lon1, lat2, lon2):
    """The middle of the great circle between two points (degrees)."""
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    bx, by = math.cos(p2) * math.cos(l2 - l1), math.cos(p2) * math.sin(l2 - l1)
    lat = math.atan2(math.sin(p1) + math.sin(p2), math.sqrt((math.cos(p1) + bx) ** 2 + by ** 2))
    lon = l1 + math.atan2(by, math.cos(p1) + bx)
    return math.degrees(lat), (math.degrees(lon) + 540) % 360 - 180


def ground_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_A_KM * math.asin(min(1.0, math.sqrt(a)))


def fetch(lat, lon, dist=AIR_DIST_NM):
    """-> (unix time of the answer, [aircraft records]) of adsb.fi (else adsb.lol) around (lat, lon); cached CACHE_S."""
    key = (round(lat, 2), round(lon, 2), dist)
    with _lock:
        if _cache["key"] == key and time.time() - _cache["t"] < CACHE_S:
            return _cache["data"]
        wait = GAP_S - (time.time() - _cache["last"])
        if wait > 0:
            time.sleep(wait)
        errors = []
        for url in URLS:
            _cache["last"] = time.time()
            try:
                req = urllib.request.Request(url.format(lat=lat, lon=lon, dist=dist), headers={"User-Agent": "RADIMCOM"})
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                    raw = r.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("answer too long")
                d = json.loads(raw)
            except (OSError, ValueError) as e:
                errors.append(f"{url.split('/')[2]}: {getattr(e, 'reason', e)}")
                continue
            now = d.get("now")
            now = now / 1000.0 if isinstance(now, (int, float)) and now > 1e11 else (now or time.time())
            out = (float(now), d.get("aircraft") or d.get("ac") or [])
            _cache.update(t=time.time(), key=key, data=out, error="")
            return out
        _cache["error"] = "; ".join(errors)
        raise OSError(_cache["error"])


def _state(a, t_now):
    """An adsb.fi record -> (unix time of its position, lat, lon, alt m, ground speed m/s, track deg, climb m/s) or None."""
    if a.get("lat") is None or a.get("lon") is None or a.get("alt_baro") == "ground":
        return None
    alt = a.get("alt_geom", a.get("alt_baro"))
    if not isinstance(alt, (int, float)):
        return None
    gs, trk = a.get("gs"), a.get("track", a.get("true_heading"))
    if not isinstance(gs, (int, float)) or not isinstance(trk, (int, float)):
        return None
    rate = a.get("geom_rate", a.get("baro_rate", 0)) or 0
    t_pos = t_now - float(a.get("seen_pos", a.get("seen", 0)) or 0)
    return t_pos, float(a["lat"]), float(a["lon"]), alt * FT, gs * KT, float(trk), float(rate) * FT / 60.0


def _track(st, times):
    """Positions and velocities (ECEF km, km/s) of an aircraft at the unix times: moved along its track from its
    position (east / north on the local plane: enough for a minute or two)."""
    t_pos, lat, lon, alt, gs, trk, climb = st
    p, up, east, north = _site(lat, lon, alt)
    d = np.radians(trk)
    vel = (gs * (math.sin(d) * east + math.cos(d) * north) + climb * up) / 1000.0
    dt = np.asarray(times, float) - t_pos
    return p[None, :] + dt[:, None] * vel[None, :], np.repeat(vel[None, :], len(dt), 0)


def identify(pts, qth, tx, f_hz, aircraft, t_now, offset=0.0, tol=AIR_OFFSET_TOL_HZ):
    """pts [(t, Hz)] of an aircraft echo; qth (lat, lon); tx (lat, lon) of GRAVES; aircraft: adsb.fi records of the
    answer at t_now; offset: the known receiver offset (Hz) ->
    {"hex", "flight", "reg", "type", "desc", "alt_ft", "km", "rms", "others", "candidates", "curve": [[t, Hz]]}
    or {"hex": None, "why": text}."""
    if not qth:
        return {"hex": None, "why": "the station location is not set (SETUP › LOCATION)"}
    pts = sorted(pts)
    if len(pts) > AIR_POINTS:
        pts = [pts[int(i)] for i in np.linspace(0, len(pts) - 1, AIR_POINTS)]
    t = np.array([p[0] for p in pts])
    f = np.array([p[1] for p in pts])
    site_t, site_r = _site(tx[0], tx[1]), _site(qth[0], qth[1])
    best, scores = None, []
    n_cand = 0
    for a in aircraft:
        st = _state(a, t_now)
        if st is None or t[0] - st[0] > MAX_AGE_S or st[0] - t[-1] > MAX_AGE_S:
            continue
        h = math.sqrt(2 * K_EARTH * EARTH_A_KM * max(st[3], 0) / 1000.0) + HORIZON_EXTRA_KM
        if ground_km(st[1], st[2], tx[0], tx[1]) > h or ground_km(st[1], st[2], qth[0], qth[1]) > h:
            continue
        n_cand += 1
        r, v = _track(st, t)
        fd = bistatic_doppler(r, v, site_t[0], site_r[0], f_hz)
        off = float(np.clip(np.median(f - fd), offset - tol, offset + tol))
        rms = float(np.sqrt(np.mean((f - fd - off) ** 2)))
        scores.append(rms)
        if best is None or rms < best[0]:
            best = (rms, a, st, fd, off)
    if best is None:
        return {"hex": None, "why": f"no aircraft of adsb.fi could see both GRAVES and the station ({len(aircraft)} around)",
                "candidates": 0}
    rms, a, st, fd, off = best
    if rms > AIR_RMS_HZ:
        return {"hex": None, "why": f"no aircraft of adsb.fi fits (closest {(a.get('flight') or a.get('hex') or '').strip()}, "
                f"{rms:.0f} Hz off); not on ADS-B, or not an aircraft", "candidates": n_cand}
    others = sum(1 for s in scores if s <= rms * 1.3 + 5) - 1
    km = ground_km(st[1], st[2], qth[0], qth[1])
    return {"hex": a.get("hex"), "flight": (a.get("flight") or "").strip(), "reg": a.get("r", ""), "type": a.get("t", ""),
            "desc": a.get("desc", ""), "alt_ft": round(st[3] / FT), "km": round(km), "lat": round(st[1], 3),
            "lon": round(st[2], 3), "rms": round(rms, 1), "offset": round(off), "others": others, "candidates": n_cand,
            "curve": [[round(float(a_), 2), round(float(b + off), 1)] for a_, b in zip(t, fd)]}

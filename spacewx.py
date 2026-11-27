"""Space weather for the PROP tab: the sun, the solar wind, the geomagnetic field and the NOAA alerts from NOAA SWPC
(https://www.swpc.noaa.gov, public domain, no key), and an estimate of the HF band conditions at the station.

Each feed is downloaded only when the browser asks for it and its copy is older than its TTL, in a background
thread; the copies are kept in data/spacewx/<feed>.json, so a restart or another VFO process does not download them
again. Nothing of the station goes out (the requests are plain GETs of public files).

The band conditions are our own simple model, not a measurement: foF2 over the station from the solar flux, the height
of the sun (time of day, season), the winter anomaly and the geomagnetic storms (Kp); MUF(3000) = 3 × foF2 (one F2 hop
of about 3000 km); the D-layer absorption by day (lower bands, more with a higher flux and X-ray flares, NOAA R scale);
a strong geomagnetic storm lowers all bands. Each band: GOOD / FAIR / POOR, now and for each hour of the next day.
"""
import gzip
import json
import math
import os
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from paths import data

BASE = "https://services.swpc.noaa.gov/"
DIR = data("spacewx")
TIMEOUT_S = 20
RETRY_S = 300                   # a feed that failed is not asked for again before this
SOURCE = "NOAA Space Weather Prediction Center (SWPC), public domain"
# ionosondes: the newest scaled values of each station, collected by KC2G (prop.kc2g.com) from GIRO (Lowell DIDBase,
# CC BY-NC-SA 4.0, Reinisch and Galkin 2011, doi:10.5047/eps.2011.03.001) and other networks
IONO_URL = "https://prop.kc2g.com/api/stations.json"
IONO_SOURCE = "Ionosondes: GIRO (Lowell DIDBase, CC BY-NC-SA 4.0) via KC2G prop.kc2g.com"
IONO_NEAR_KM = 1500             # stations shown
IONO_CAL_KM = 1000              # stations that correct the model (and give foEs)
IONO_FRESH_S = 90 * 60          # a value older than this does not correct the model
IONO_SHOW_S = 6 * 3600          # a station silent for longer is not shown
CAL_DECAY_H = 6.0               # the correction of the model fades into the forecast with this time constant
ES_M = 5.3                      # MUF(Es) = foEs x this for one Es hop of about 2000 km (sporadic E at ~105 km)
# magnetogram: the Kiruna observatory of the Swedish Institute of Space Physics (IRF), 1-minute X Y Z of today
# (IAGA-2002 text, the file starts again at 00 UTC); we keep the last 24 hours ourselves
KIR_URL = "https://www2.irf.se/maggraphs/rt_iaga_secondary.txt"
KIR_SOURCE = "Magnetogram: Kiruna geophysical observatory, Swedish Institute of Space Physics (IRF), irf.se"
KIR_KEEP_S = 24 * 3600

# name: (path, TTL in s)
FEEDS = {
    "kp": ("products/noaa-planetary-k-index.json", 900),            # Kp + ap of each 3 h, last 7 days
    "kpf": ("products/noaa-planetary-k-index-forecast.json", 1800),  # observed + predicted Kp, 3 days ahead
    "kp1m": ("json/planetary_k_index_1m.json", 300),                # estimated Kp, each minute
    "f107": ("json/f107_cm_flux.json", 3600),                        # 10.7 cm flux (3 a day) + its 90-day mean
    "dsi": ("text/daily-solar-indices.txt", 3 * 3600),             # daily flux, sunspot number, flares, last 30 days
    "xray": ("json/goes/primary/xrays-6-hour.json", 300),           # GOES X-ray flux, each minute, 6 h
    "flare": ("json/goes/primary/xray-flares-latest.json", 300),     # the latest flare
    "wind": ("products/summary/solar-wind-speed.json", 300),        # solar wind speed
    "mag": ("products/summary/solar-wind-mag-field.json", 300),     # interplanetary field Bt, Bz
    "scales": ("products/noaa-scales.json", 900),                    # NOAA R / S / G now, yesterday, 3 days ahead
    "alerts": ("products/alerts.json", 900),                         # alerts, warnings, watches, summaries
    "iono": (IONO_URL, 900),                                          # the newest values of each ionosonde (KC2G / GIRO)
    "kir": (KIR_URL, 300),                                            # Kiruna magnetometer, 1 min, today
    "aur": ("json/ovation_aurora_latest.json", 600),                 # OVATION aurora nowcast (~30 min ahead), 1° grid
}
# the aurora map of NOAA itself (OVATION, northern hemisphere, ~800 x 800 JPEG), shown as it is on the PROP tab
AUR_IMG_URL = BASE + "images/aurora-forecast-northern-hemisphere.jpg"
AUR_IMG_TTL = 600
_aur_img_lock = threading.Lock()
AUR_MIN_LAT = 30               # the aurora grid is kept only north of this (the map shows the northern hemisphere)
AUR_OVAL_P = 10                 # OVATION probability (%) from which a cell counts as the oval

BANDS = (("160m", 1.85), ("80m", 3.65), ("60m", 5.36), ("40m", 7.1), ("30m", 10.12), ("20m", 14.1), ("17m", 18.1),
         ("15m", 21.1), ("12m", 24.94), ("10m", 28.5), ("6m", 50.1))
RATING = ("POOR", "FAIR", "GOOD")

_lock = threading.Lock()
_cache = {}                     # name -> {"t": time of the download, "data": parsed}
_failed = {}                    # name -> time of the failure
_errors = {}                    # name -> text of the last error
_busy = threading.Event()


# ---------- downloading ----------

def _path(name):
    return os.path.join(DIR, name + ".json")


def _load_disk(name):
    try:
        with open(_path(name), encoding="utf-8") as f:
            c = json.load(f)
        if "t" in c and "data" in c:
            _cache[name] = c
    except (OSError, ValueError):
        pass


def _fetch(name):
    path = FEEDS[name][0]
    url = path if path.startswith("http") else BASE + path
    req = urllib.request.Request(url, headers={"User-Agent": "RADIMCOM", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    text = raw.decode("utf-8", "replace")
    d = text if name == "dsi" else _kir_merge(text) if name == "kir" else json.loads(text)
    if name == "aur":
        d = _aur_reduce(d)
    c = {"t": time.time(), "data": d}
    os.makedirs(DIR, exist_ok=True)
    tmp = _path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f)
    os.replace(tmp, _path(name))
    return c


def _kir_merge(text):
    """[[epoch, X, Y, Z], ...] of the last 24 hours: the new file (today from 00 UTC) added to what we kept before."""
    pts = {}
    old = _cache.get("kir") or {}
    for p in old.get("data") or []:
        pts[p[0]] = p
    for line in text.splitlines():
        f = line.split()
        if len(f) < 6 or not f[0][:2].isdigit() or "-" not in f[0]:
            continue
        try:
            t = int(datetime.strptime(f[0] + " " + f[1][:8], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
            x, y, z = float(f[3]), float(f[4]), float(f[5])
        except ValueError:
            continue
        if max(abs(x), abs(y), abs(z)) >= 99999:      # IAGA-2002: missing value
            continue
        pts[t] = [t, x, y, z]
    if not pts:
        raise ValueError("no magnetometer values")
    end = max(pts)
    return [pts[t] for t in sorted(pts) if t > end - KIR_KEEP_S]


def _aur_reduce(j):
    """OVATION file (~1 MB, [lon 0..359, lat -90..90, %] for the whole globe) -> the northern cells with some aurora:
    {"obs", "fc", "pts": [lon, lat, p, lon, lat, p, ...]}."""
    pts = []
    for c in j.get("coordinates") or []:
        try:
            lon, lat, p = int(c[0]), int(c[1]), int(round(float(c[2])))
        except (TypeError, ValueError, IndexError):
            continue
        if lat >= AUR_MIN_LAT and p > 0:
            pts += (lon if lon <= 180 else lon - 360, lat, p)
    if not pts and not j.get("coordinates"):
        raise ValueError("no aurora grid")
    return {"obs": _iso(j.get("Observation Time")), "fc": _iso(j.get("Forecast Time")), "pts": pts}


def aurora_image():
    """The NOAA aurora map (bytes of the JPEG, or None): downloaded when the copy in data/spacewx is older than
    AUR_IMG_TTL; the old copy is kept when the download fails."""
    path = os.path.join(DIR, "aurora_north.jpg")
    with _aur_img_lock:
        try:
            age = time.time() - os.path.getmtime(path)
        except OSError:
            age = None
        if (age is None or age >= AUR_IMG_TTL) and time.time() - _failed.get("aur_img", 0) >= RETRY_S:
            try:
                req = urllib.request.Request(AUR_IMG_URL, headers={"User-Agent": "RADIMCOM"})
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                    raw = r.read()
                if raw[:2] != b"\xff\xd8":
                    raise ValueError("not a JPEG")
                os.makedirs(DIR, exist_ok=True)
                with open(path + ".tmp", "wb") as f:
                    f.write(raw)
                os.replace(path + ".tmp", path)
                _errors.pop("aur_img", None)
            except Exception as e:  # noqa: BLE001 - keep the old copy, try again later
                _failed["aur_img"] = time.time()
                _errors["aur_img"] = str(e)[:200]
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None


def _stale(name, now):
    c = _cache.get(name)
    if c is None:
        _load_disk(name)
        c = _cache.get(name)
    if c is not None and now - c["t"] < FEEDS[name][1]:
        return False
    return now - _failed.get(name, 0) >= RETRY_S


def _refresh(names):
    try:
        for name in names:
            try:
                c = _fetch(name)
                with _lock:
                    _cache[name] = c
                    _errors.pop(name, None)
            except Exception as e:  # noqa: BLE001 - any failure of one feed: keep the old copy, try again later
                with _lock:
                    _failed[name] = time.time()
                    _errors[name] = str(e)[:200]
    finally:
        _busy.clear()


def _ensure(wait_s=15.0):
    """Starts the download of the stale feeds in the background; waits for it only when nothing is known yet."""
    now = time.time()
    with _lock:
        stale = [n for n in FEEDS if _stale(n, now)]
        empty = not _cache
    if stale and not _busy.is_set():
        _busy.set()
        threading.Thread(target=_refresh, args=(stale,), name="spacewx", daemon=True).start()
    if empty and _busy.is_set():
        end = time.time() + wait_s
        while _busy.is_set() and time.time() < end:
            time.sleep(0.1)


def _get(name):
    c = _cache.get(name)
    return c["data"] if c else None


# ---------- parsing ----------

def _num(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _iso(t):
    """NOAA time ("2026-11-19T21:00:00", "...Z", "2026-11-19 01:18:16.670") -> "2026-11-19T21:00:00Z"."""
    if not t:
        return None
    t = str(t).replace(" ", "T").rstrip("Z")
    return t[:19] + "Z"


def _epoch(t):
    try:
        return datetime.strptime(_iso(t), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def xray_class(flux):
    """GOES 0.1-0.8 nm flux in W/m² -> "B5.2", "M1.0", "X2.3"."""
    if not flux or flux <= 0:
        return None
    for letter, base in (("X", 1e-4), ("M", 1e-5), ("C", 1e-6), ("B", 1e-7), ("A", 1e-8)):
        if flux >= base or letter == "A":
            return f"{letter}{flux / base:.1f}"
    return None


def _kp_hist():
    out = []
    for r in _get("kp") or []:
        if isinstance(r, dict) and _num(r.get("Kp")) is not None:
            out.append({"t": _iso(r.get("time_tag")), "kp": _num(r.get("Kp")), "ap": _num(r.get("a_running"))})
    return out


def _kp_forecast():
    """The 3-hour Kp of the forecast product. Its "estimated" rows of today are NOAA's forecast, not a measurement:
    an interval that has begun gets the highest 1-minute estimated Kp measured in it instead ("nowcast"; the forecast
    stays in "fc"), so a running interval does not show a storm that was only forecast."""
    m1 = []
    for r in _get("kp1m") or []:
        if isinstance(r, dict) and _num(r.get("estimated_kp")) is not None:
            t = _epoch(r.get("time_tag"))
            if t is not None:
                m1.append((t, _num(r["estimated_kp"])))
    out = []
    for r in _get("kpf") or []:
        if isinstance(r, dict) and _num(r.get("kp")) is not None:
            row = {"t": _iso(r.get("time_tag")), "kp": _num(r.get("kp")), "kind": r.get("observed"),
                   "scale": r.get("noaa_scale")}
            t0 = _epoch(row["t"])
            if row["kind"] != "observed" and t0 is not None:
                inside = [k for t, k in m1 if t0 <= t < t0 + 3 * 3600]
                if inside:
                    row.update(fc=row["kp"], kp=max(inside), kind="nowcast", n=len(inside))
            out.append(row)
    return out


def _kp_now():
    rows = [r for r in (_get("kp1m") or []) if isinstance(r, dict) and _num(r.get("estimated_kp")) is not None]
    if not rows:
        return None
    r = rows[-1]
    return {"kp": _num(r["estimated_kp"]), "t": _iso(r.get("time_tag"))}


def _aurora(lat, lon):
    """The OVATION grid and, with the location: the % at the station and the nearest cell of the oval (>= AUR_OVAL_P %)."""
    a = _get("aur")
    if not a or not isinstance(a, dict):
        return None
    out = {"obs": a.get("obs"), "fc": a.get("fc"), "pts": a.get("pts") or []}
    if lat is None or lon is None or (lat == 0 and lon == 0):
        return out
    p, here, near, best = out["pts"], 0, None, None
    la1, r = math.radians(lat), math.pi / 180
    for i in range(0, len(p) - 2, 3):
        x, y, v = p[i], p[i + 1], p[i + 2]
        if abs(y - lat) <= 0.5 and abs(((x - lon + 180) % 360) - 180) <= 0.5:
            here = max(here, v)
        if v < AUR_OVAL_P:
            continue
        c = math.sin(la1) * math.sin(y * r) + math.cos(la1) * math.cos(y * r) * math.cos((x - lon) * r)
        km = 6371 * math.acos(max(-1.0, min(1.0, c)))
        if best is None or km < best:
            best, near = km, {"km": round(km), "lat": y, "lon": x, "p": v}
    out["here"], out["near"] = here, near
    out["max"] = max(p[2::3]) if p else 0
    return out


def _f107():
    rows = [r for r in (_get("f107") or []) if isinstance(r, dict) and _num(r.get("flux")) is not None]
    if not rows:
        return None
    rows.sort(key=lambda r: r.get("time_tag") or "")
    last = rows[-1]
    mean = next((_num(r.get("ninety_day_mean")) for r in reversed(rows) if _num(r.get("ninety_day_mean"))), None)
    return {"sfi": _num(last["flux"]), "t": _iso(last.get("time_tag")), "mean90": mean}


def _daily():
    """daily-solar-indices.txt -> [{date, sfi, ssn, area, c, m, x}] (last 30 days)."""
    out = []
    for line in (_get("dsi") or "").splitlines():
        p = line.split()
        if len(p) < 15 or line.startswith((":", "#")) or not p[0].isdigit():
            continue
        try:
            out.append({"date": f"{p[0]}-{p[1]}-{p[2]}", "sfi": _num(p[3]), "ssn": _num(p[4]), "area": _num(p[5]),
                        "c": int(p[-7]), "m": int(p[-6]), "x": int(p[-5])})
        except ValueError:
            continue
    return out


def _xray():
    """GOES long channel (0.1-0.8 nm): the curve every 5 min and the newest value."""
    pts = []
    for r in _get("xray") or []:
        if isinstance(r, dict) and r.get("energy") == "0.1-0.8nm" and _num(r.get("flux")):
            pts.append((_iso(r.get("time_tag")), _num(r["flux"])))
    if not pts:
        return None
    curve = [{"t": t, "f": f} for i, (t, f) in enumerate(pts) if i % 5 == 0 or i == len(pts) - 1]
    t, f = pts[-1]
    return {"flux": f, "cls": xray_class(f), "t": t, "curve": curve}


def _flare():
    rows = _get("flare") or []
    r = rows[-1] if isinstance(rows, list) and rows else None
    if not isinstance(r, dict):
        return None
    return {"max": r.get("max_class"), "max_t": _iso(r.get("max_time")), "begin_t": _iso(r.get("begin_time")),
            "end_t": _iso(r.get("end_time")), "now": r.get("current_class")}


def _solar_wind():
    w, m = _get("wind") or [], _get("mag") or []
    w = w[-1] if isinstance(w, list) and w else {}
    m = m[-1] if isinstance(m, list) and m else {}
    if not w and not m:
        return None
    return {"speed": _num(w.get("proton_speed")), "bt": _num(m.get("bt")), "bz": _num(m.get("bz_gsm")),
            "t": _iso(m.get("time_tag") or w.get("time_tag"))}


def _scale(s, key):
    v = (s or {}).get(key) or {}
    return {"scale": int(v["Scale"]) if str(v.get("Scale") or "").isdigit() else None, "text": v.get("Text"),
            **({"minor": _num(v.get("MinorProb")), "major": _num(v.get("MajorProb"))} if key == "R" else {}),
            **({"prob": _num(v.get("Prob"))} if key == "S" else {})}


def _scales():
    d = _get("scales")
    if not isinstance(d, dict):
        return None
    out = {}
    for k in ("-1", "0", "1", "2", "3"):
        s = d.get(k)
        if isinstance(s, dict):
            out[k] = {"date": s.get("DateStamp"), "R": _scale(s, "R"), "S": _scale(s, "S"), "G": _scale(s, "G")}
    return out


_HEAD = ("ALERT:", "WARNING:", "EXTENDED WARNING:", "WATCH:", "SUMMARY:", "CANCEL", "CONTINUED ALERT:")


def _alerts(max_age_h=48):
    out, now = [], time.time()
    for r in _get("alerts") or []:
        if not isinstance(r, dict):
            continue
        t = _epoch(r.get("issue_datetime"))
        if t is None or now - t > max_age_h * 3600:
            continue
        msg = (r.get("message") or "").replace("\r", "")
        head = next((ln.strip() for ln in msg.split("\n") if ln.strip().upper().startswith(_HEAD)), "")
        kind = head.split(":")[0].strip().upper() if head else ""
        out.append({"id": r.get("product_id"), "t": _iso(r.get("issue_datetime")), "kind": kind,
                    "head": head or (r.get("product_id") or ""), "text": msg.strip()[:2000]})
    out.sort(key=lambda a: a["t"], reverse=True)
    return out[:20]


def _kir():
    """Kiruna: 2-minute means of X Y Z for the chart, and the range of X in the last 3 hours (how disturbed)."""
    pts = _get("kir") or []
    if not pts:
        return None
    out, acc = [], []
    for p in pts:
        if acc and p[0] // 120 != acc[0][0] // 120:
            n = len(acc)
            out.append([acc[0][0] // 120 * 120] + [round(sum(a[i] for a in acc) / n, 1) for i in (1, 2, 3)])
            acc = []
        acc.append(p)
    if acc:
        n = len(acc)
        out.append([acc[0][0] // 120 * 120] + [round(sum(a[i] for a in acc) / n, 1) for i in (1, 2, 3)])
    end = pts[-1][0]
    x3 = [p[1] for p in pts if p[0] > end - 3 * 3600]
    return {"t": datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "pts": out, "dx3h": round(max(x3) - min(x3)) if x3 else None}


def dist_km(la1, lo1, la2, lo2):
    p1, p2, dl = math.radians(la1), math.radians(la2), math.radians(lo2 - lo1)
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return 6371.0 * math.acos(max(-1.0, min(1.0, c)))


def _iono(lat, lon):
    """Ionosondes up to IONO_NEAR_KM from the station with a value in the last IONO_SHOW_S, the nearest first."""
    out, now = [], time.time()
    for r in _get("iono") or []:
        st = r.get("station") if isinstance(r, dict) else None
        if not isinstance(st, dict):
            continue
        la, lo, t = _num(st.get("latitude")), _num(st.get("longitude")), _epoch(r.get("time"))
        if la is None or lo is None or t is None or now - t > IONO_SHOW_S:
            continue
        lo = lo - 360 if lo > 180 else lo
        d = dist_km(lat, lon, la, lo)
        if d > IONO_NEAR_KM:
            continue
        out.append({"code": st.get("code"), "name": st.get("name"), "lat": la, "lon": lo, "km": round(d),
                    "t": _iso(r.get("time")), "age_s": round(now - t), "cs": _num(r.get("cs")),
                    "fof2": _num(r.get("fof2")), "mufd": _num(r.get("mufd")), "foes": _num(r.get("foes")),
                    "foe": _num(r.get("foe")), "hmf2": _num(r.get("hmf2")), "source": r.get("source")})
    out.sort(key=lambda x: x["km"])
    return out[:6]


def _trusted(s):
    """A value to correct the model with: fresh, near, and scaled well (KC2G cs = confidence 0-100, -1 = unknown)."""
    return s["km"] <= IONO_CAL_KM and s["age_s"] <= IONO_FRESH_S and (s["cs"] is None or s["cs"] < 0 or s["cs"] >= 25)


# ---------- band conditions (own model) ----------

def _sun(t):
    """Declination of the sun (rad) and the equation of time (min) at the epoch t (approximation good to ~1°)."""
    d = datetime.fromtimestamp(t, timezone.utc)
    doy = d.timetuple().tm_yday + (d.hour + d.minute / 60) / 24
    g = 2 * math.pi / 365.25 * (doy - 1)
    dec = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
           + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g)
                    - 0.040849 * math.sin(2 * g))
    return dec, eqt, d


def sun_cosz(lat, lon, t):
    """Cosine of the zenith angle of the sun at (lat, lon) at the epoch t."""
    dec, eqt, d = _sun(t)
    ha = math.radians((d.hour * 60 + d.minute + eqt + 4 * lon) / 4 - 180)
    la = math.radians(lat)
    return math.sin(la) * math.sin(dec) + math.cos(la) * math.cos(dec) * math.cos(ha)


def noon_cosz(lat, t):
    """Cosine of the zenith angle of the sun at the local noon of that day (its highest point)."""
    dec = _sun(t)[0]
    return math.cos(math.radians(lat) - dec)


def fof2(sfi, cosz, kp, lat, t):
    """Rough foF2 over the station in MHz: from the night level to the day level by the height of the sun relative to
    its noon height that day (the season is in the winter anomaly: by day foF2 is higher in winter at mid latitudes),
    lowered by a geomagnetic storm (negative storm phase)."""
    s = max(60.0, min(sfi, 300.0))
    day = 4.5 + 0.06 * (s - 65)
    night = 2.3 + 0.02 * (s - 65)
    doy = datetime.fromtimestamp(t, timezone.utc).timetuple().tm_yday
    winter = math.cos(2 * math.pi * (doy - 355) / 365.25) * (1 if lat >= 0 else -1)   # +1 = midwinter
    day *= 1 + 0.15 * winter
    top = max(noon_cosz(lat, t), 0.05) + 0.1
    lit = max(0.0, min(1.0, (cosz + 0.1) / top)) ** 0.6     # the F layer is still lit a little after sunset
    f = night + (day - night) * lit
    if kp is not None:
        f *= 0.65 if kp >= 7 else 0.75 if kp >= 6 else 0.85 if kp >= 5 else 1.0
    return f


def band_rating(fmhz, muf, cosz, sfi, kp, r_scale):
    """0 POOR, 1 FAIR, 2 GOOD."""
    r = 2 if fmhz <= 0.85 * muf else 1 if fmhz <= 1.05 * muf else 0
    if cosz > 0:     # D-layer absorption by day
        a = cosz ** 0.75 * (1 + 0.006 * (max(sfi, 65) - 65)) * (7.0 / fmhz) ** 2
        a *= {0: 1, 1: 1.5, 2: 2.5}.get(r_scale or 0, 5)
        r -= 2 if a > 3 else 1 if a > 1 else 0
    if kp is not None:
        r -= 2 if kp >= 8 else 1 if kp >= 6 else 0
    return max(0, min(2, r))


def _kp_at(fc, t):
    """Kp of the 3-hour interval of the forecast that contains the epoch t (or the nearest one)."""
    best, bd = None, None
    for r in fc:
        ts = _epoch(r["t"])
        if ts is None:
            continue
        dist = 0 if ts <= t < ts + 3 * 3600 else min(abs(t - ts), abs(t - ts - 3 * 3600))
        if bd is None or dist < bd:
            best, bd = r["kp"], dist
    return best


def bands(lat, lon, sfi, kp_now, fc, r_now, now=None, cal=1.0, es_muf=None):
    """Conditions now and for each of the next 24 hours (from the current UTC hour) at the station.
    cal: measured / modelled MUF of the near ionosondes, applied now and fading over CAL_DECAY_H;
    es_muf: MUF of sporadic E now from their foEs (only for now: Es comes and goes within minutes)."""
    now = now or time.time()
    h0 = now - now % 3600
    hours, muf = [], []
    for i in range(24):
        t = now if i == 0 else h0 + i * 3600
        kp = kp_now if i == 0 and kp_now is not None else _kp_at(fc, t)
        cz = sun_cosz(lat, lon, t)
        m = 3.0 * fof2(sfi, cz, kp, lat, t) * (1 + (cal - 1) * math.exp(-max(0.0, t - now) / 3600 / CAL_DECAY_H))
        hours.append({"t": datetime.fromtimestamp(h0 + i * 3600, timezone.utc).strftime("%Y-%m-%dT%H:00:00Z"),
                      "day": cz > 0, "kp": kp, "cz": cz, "muf": m})
        muf.append(round(m, 1))
    out = []
    for name, f in BANDS:
        rs = [band_rating(f, h["muf"], h["cz"], sfi, h["kp"], r_now if i == 0 else 0) for i, h in enumerate(hours)]
        es = None
        if es_muf and f >= 14:     # Es matters for the upper bands; below, F2 carries them anyway
            es = 2 if es_muf >= f else 1 if es_muf >= 0.8 * f else 0
            rs[0] = max(rs[0], es)
        out.append({"band": name, "mhz": f, "now": rs[0], "hours": rs, "es": es})
    return {"bands": out, "hours": [{"t": h["t"], "day": h["day"], "kp": h["kp"], "muf": round(h["muf"], 1)} for h in hours],
            "muf": muf[0], "fof2": round(hours[0]["muf"] / 3.0, 2), "ratings": RATING, "cal": round(cal, 2),
            "es_muf": round(es_muf, 1) if es_muf else None}


# ---------- the whole answer ----------

def summary(lat=None, lon=None):
    """Everything the PROP tab and the header chip show."""
    _ensure()
    with _lock:
        kp_hist, fc, kp1m = _kp_hist(), _kp_forecast(), _kp_now()
        f107, daily, xray, flare = _f107(), _daily(), _xray(), _flare()
        sw, scales, alerts, kir = _solar_wind(), _scales(), _alerts(), _kir()
        iono = _iono(lat, lon) if lat is not None and lon is not None else []
        aur = _aurora(lat, lon)
        ages = {n: round(time.time() - c["t"]) for n, c in _cache.items()}
        errors = dict(_errors)
    a_index = None
    aps = [r["ap"] for r in kp_hist[-8:] if r["ap"] is not None]
    if aps:
        a_index = round(sum(aps) / len(aps))
    kp_now = kp1m["kp"] if kp1m else (kp_hist[-1]["kp"] if kp_hist else None)
    sfi = f107["sfi"] if f107 else (daily[-1]["sfi"] if daily else None)
    sfi_eff = None
    if sfi is not None:     # foF2 follows the smoothed activity more than one day's flux
        sfi_eff = (sfi + f107["mean90"]) / 2 if f107 and f107.get("mean90") else sfi
    r_now = (scales or {}).get("0", {}).get("R", {}).get("scale")
    prop, cal, es_muf, cal_from = None, 1.0, None, []
    if sfi_eff is not None and lat is not None and lon is not None and not (lat == 0 and lon == 0):
        num = den = 0.0
        foes = []
        for s in iono:
            if not _trusted(s):
                continue
            t = _epoch(s["t"])
            if s["mufd"]:     # the model at the ionosonde, at the time of its value
                m = 3.0 * fof2(sfi_eff, sun_cosz(s["lat"], s["lon"], t), kp_now, s["lat"], t)
                w = 1.0 / max(s["km"], 100)
                num, den = num + w * s["mufd"] / m, den + w
                s["model"] = round(m, 1)
                cal_from.append(s["code"])
            if s["foes"]:
                foes.append(s["foes"])
        if den:
            cal = max(0.5, min(2.0, num / den))
        if foes:
            es_muf = max(foes) * ES_M
        prop = bands(lat, lon, sfi_eff, kp_now, fc, r_now, cal=cal, es_muf=es_muf)
        prop["sfi_used"] = round(sfi_eff)
        prop["cal_from"] = cal_from
    ssn = next((d["ssn"] for d in reversed(daily) if d.get("ssn") is not None), None)
    return {
        "sfi": f107, "ssn": ssn, "daily": daily, "kp": kp_now, "kp_t": kp1m["t"] if kp1m else None,
        "a": a_index, "kp_hist": kp_hist, "kp_fc": fc, "xray": xray, "flare": flare, "wind": sw,
        "scales": scales, "alerts": alerts, "prop": prop, "qth": {"lat": lat, "lon": lon}, "iono": iono,
        "kir": kir, "aur": aur, "ages": ages, "errors": errors, "busy": _busy.is_set(), "source": SOURCE, "iono_source": IONO_SOURCE,
        "kir_source": KIR_SOURCE,
    }

"""Local FR24 receiver (or any dump1090 style box) as a source of aircraft: its BaseStation (SBS-1) stream on TCP 30003.

The Flightradar24 receiver of the station decodes ADS-B on its own antenna; its port 30003 sends one text line per
message ("MSG,3,…,ICAO,…,callsign,altitude,speed,track,lat,lon,vrate,squawk,alert,emergency,spi,ground"). Here the
lines become aircraft (like the ADS-B decoder makes them), with a trail of each one:

    FR24 receiver :30003 --SBS lines--> Fr24Feed (aircraft, trails) --> /api/fr24 (COMPOSITE map, SETTINGS › FR24 RECEIVER)
                                                                    +-> on_update(icao, fields) (the ADS-B decoder, FR24 ticked)

The settings are one for the station (data\\fr24.json: host, port, on). Every VFO server has its own Fr24Feed, but it
holds the connection only while somebody wants the data (a request in the last IDLE_S, or keep() says so), so usually
only the server of the open page is connected.
"""
import collections
import html
import json
import os
import re
import socket
import threading
import time
import urllib.request

from flask import jsonify, request

from adsb import bearing, distance_km
from paths import data

CFG_FILE = data("fr24.json")
DEFAULT_PORT = 30003      # BaseStation (SBS-1) output of the FR24 receiver
IDLE_S = 60               # without a request this long (and without keep()) the connection is closed
RETRY_S = 5               # after a failed connection
STALE_S = 900             # an aircraft not heard for 15 min is dropped
TRAIL = 180               # trail points kept of each aircraft
TRAIL_EVERY_S = 10        # a new trail point at most this often (unless the squawk changes)
MAX_AIRCRAFT = 2000
WEB_EVERY_S = 300         # the status page of the receiver is read this often while connected
WEB_ROWS = (("radar", "FR24 radar code"), ("feeding", "FR24 feeding"), ("status", "Status"), ("uptime", "Uptime"),
            ("temp", "Temperature"), ("gps", "Antenna status"), ("sats", "Satellites used"), ("ac", "1090MHz aicraft"))
EMERG_SQ = {"7500": "hijack", "7600": "radio failure", "7700": "emergency"}


def _num(s, kind=float):
    try:
        return kind(s) if s not in ("", None) else None
    except ValueError:
        return None


def parse_sbs(line):
    """One SBS line -> (icao, {fields}) or None. Only the fields the message carries are in the dict."""
    p = line.strip().split(",")
    if len(p) < 11 or p[0] != "MSG":
        return None
    icao = p[4].strip().upper()
    if len(icao) != 6 or icao.startswith("~"):
        return None
    try:
        int(icao, 16)
    except ValueError:
        return None
    p += [""] * (22 - len(p))
    f = {}
    if p[10].strip():
        f["flight"] = p[10].strip()
    alt = _num(p[11], lambda x: int(float(x)))
    if alt is not None:
        f["alt"] = alt
    gs = _num(p[12])
    if gs is not None:
        f["gs"] = gs
    trk = _num(p[13])
    if trk is not None:
        f["track"] = trk
    lat, lon = _num(p[14]), _num(p[15])
    if lat is not None and lon is not None and (lat or lon) and abs(lat) <= 90 and abs(lon) <= 180:
        f["lat"], f["lon"] = round(lat, 5), round(lon, 5)
    vr = _num(p[16], lambda x: int(float(x)))
    if vr is not None:
        f["vrate"] = vr
    sq = p[17].strip()
    if sq.isdigit() and len(sq) <= 4:
        f["squawk"] = sq.zfill(4)
    if p[19].strip() in ("-1", "1"):
        f["emergency"] = "emergency"
    if p[21].strip() in ("-1", "1", "0"):
        f["ground"] = p[21].strip() != "0"
    return icao, f


def load_cfg():
    try:
        with open(CFG_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        d = {}
    return {"host": str(d.get("host") or "").strip(), "port": int(d.get("port") or DEFAULT_PORT), "on": bool(d.get("on", True)),
            "radar": str(d.get("radar") or "")}   # radar: the last code read from the receiver (only shown)


def _conn(c):
    """What the connection depends on (a new radar code alone does not reconnect)."""
    return c["host"], c["port"], c["on"]


def save_cfg(c):
    tmp = CFG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(c, fh, indent=2)
    os.replace(tmp, CFG_FILE)


class Fr24Feed:
    def __init__(self, station=None, keep=None):
        self.station = station or (lambda: None)   # () -> (lat, lon) of the station or None
        self.keep = keep or (lambda: False)        # () -> True while a user of the data needs the connection without asking
        self.on_update = None                      # on_update(icao, fields, now) for each message (the ADS-B decoder)
        self.cfg = load_cfg()
        self._cfg_mtime = self._mtime()
        self.lock = threading.Lock()
        self.aircraft = {}
        self.status = "off"
        self.error = ""
        self.connected_since = None
        self.count = 0
        self.rate = 0.0
        self._rate_n, self._rate_t = 0, time.monotonic()
        self._wanted = 0.0
        self.web = {}                              # from the status page of the receiver: radar code, feeding…
        self._web_t = -1e9                         # monotonic time of the last read (at once on the first connection)
        self._sock = None
        self._reset = False
        threading.Thread(target=self._loop, name="fr24-sbs", daemon=True).start()

    # ---------- settings and users ----------

    @staticmethod
    def _mtime():
        try:
            return os.path.getmtime(CFG_FILE)
        except OSError:
            return 0.0

    def set_cfg(self, host, port, on):
        # the address as typed or copied from the browser: "http://192.168.1.10/" or "192.168.1.10:30003" will do
        host = re.sub(r"^\w+://", "", str(host or "").strip()).split("/")[0]
        if re.fullmatch(r"[^:]+:\d+", host):
            host, port = host.split(":")
        c = {"host": host, "port": int(port or DEFAULT_PORT), "on": bool(on),
             "radar": self.cfg.get("radar", "") if host == self.cfg["host"] else ""}
        if not 0 < c["port"] < 65536:
            raise ValueError("the port must be 1–65535")
        save_cfg(c)
        self._cfg_mtime = self._mtime()
        self._apply(c)

    def _apply(self, c):
        same = _conn(c) == _conn(self.cfg)
        self.cfg = c
        if not same:
            self.web, self._web_t = {}, -1e9
            self._reset = True        # the loop reconnects to the new address (or stays off)
            self._close()
            with self.lock:
                self.aircraft = {}

    def want(self):
        self._wanted = time.monotonic()

    def _needed(self):
        if not self.cfg["on"] or not self.cfg["host"]:
            return False
        if time.monotonic() - self._wanted < IDLE_S:
            return True
        try:
            return bool(self.keep())
        except Exception:
            return False

    # ---------- the connection ----------

    def _close(self):
        s, self._sock = self._sock, None
        if s:
            try:
                s.close()
            except OSError:
                pass

    def _loop(self):
        while True:
            m = self._mtime()
            if m != self._cfg_mtime:              # changed by the server of another VFO
                self._cfg_mtime = m
                self._apply(load_cfg())
            self._drop_stale()
            if not self._needed():
                self.status = "off" if not (self.cfg["on"] and self.cfg["host"]) else "idle"
                self.connected_since = None
                time.sleep(1)
                continue
            self._reset = False
            self._run(self.cfg["host"], self.cfg["port"])
            if not self._reset:
                time.sleep(RETRY_S)

    def _run(self, host, port):
        self.status = "connecting"
        try:
            s = socket.create_connection((host, port), timeout=5)
        except OSError as e:
            self.status, self.error = "error", f"{host}:{port}: {e}"
            return
        s.settimeout(30)
        self._sock = s
        self.status, self.error, self.connected_since = "connected", "", time.time()
        buf = b""
        last_check = time.monotonic()
        try:
            while self._sock is s:
                chunk = s.recv(65536)
                if not chunk:
                    raise OSError("the receiver closed the connection")
                buf += chunk
                *lines, buf = buf.split(b"\n")
                now = time.time()
                for ln in lines:
                    r = parse_sbs(ln.decode("ascii", "replace"))
                    if r:
                        self._take(r[0], r[1], now)
                mono = time.monotonic()
                if mono - self._rate_t >= 5:
                    self.rate = self._rate_n / (mono - self._rate_t)
                    self._rate_n, self._rate_t = 0, mono
                if mono - last_check >= 1:
                    last_check = mono
                    if not self._needed():
                        break
                    self._drop_stale()
                    if mono - self._web_t >= WEB_EVERY_S:
                        self._web_t = mono
                        threading.Thread(target=self._read_web, args=(host,), name="fr24-web", daemon=True).start()
        except OSError as e:
            if self._sock is s:
                self.status, self.error = "error", f"{host}:{port}: {e}"
        finally:
            if self._sock is s:
                self._close()
            self.connected_since = None
            if self.status == "connected":
                self.status = "idle"

    def _read_web(self, host):
        """The status page of the FR24 receiver (http://host/): its table "<tr><th>name</th><td>value</td></tr>" gives
        the radar code of the station (F-xxxx / T-xxxx) and a few lines of its state. Not the IPs and the MAC."""
        try:
            req = urllib.request.Request(f"http://{host}/", headers={"User-Agent": "RADIMCOM"})
            with urllib.request.urlopen(req, timeout=5) as r:
                page = r.read(200000).decode("utf-8", "replace")
        except Exception:
            return                        # a box without the page (plain dump1090): only the SBS stream
        rows = {html.unescape(k).strip(): html.unescape(re.sub(r"<[^>]*>", "", v)).strip()
                for k, v in re.findall(r"<th>(.*?)</th>\s*<td>(.*?)</td>", page, re.S)}
        if host == self.cfg["host"]:
            self.web = {k: rows[n] for k, n in WEB_ROWS if rows.get(n)}
            if self.web.get("radar") and self.web["radar"] != self.cfg.get("radar"):
                # kept in data\fr24.json: the name of the source is known also before the first connection
                self.cfg = dict(self.cfg, radar=self.web["radar"])
                try:
                    save_cfg(self.cfg)
                    self._cfg_mtime = self._mtime()
                except OSError:
                    pass

    # ---------- aircraft ----------

    def _take(self, icao, f, now):
        self.count += 1
        self._rate_n += 1
        with self.lock:
            a = self.aircraft.get(icao)
            if a is None:
                if len(self.aircraft) >= MAX_AIRCRAFT:
                    del self.aircraft[min(self.aircraft, key=lambda k: self.aircraft[k]["last"])]
                a = {"icao": icao, "flight": "", "alt": None, "gs": None, "track": None, "vrate": None, "squawk": "",
                     "emergency": "", "ground": False, "lat": None, "lon": None, "pos_time": None, "dist_km": None, "az": None,
                     "first": now, "last": now, "n": 0, "_trail": collections.deque(maxlen=TRAIL)}
                self.aircraft[icao] = a
            a["n"] += 1
            a["last"] = now
            for k in ("flight", "alt", "gs", "track", "vrate", "ground"):
                if k in f:
                    a[k] = f[k]
            if "squawk" in f:
                a["squawk"] = f["squawk"]
                a["emergency"] = EMERG_SQ.get(f["squawk"], "")
            if f.get("emergency") and not a["emergency"]:
                a["emergency"] = f["emergency"]
            if "lat" in f:
                a["lat"], a["lon"], a["pos_time"] = f["lat"], f["lon"], now
                qth = self.station()
                if qth:
                    a["dist_km"] = round(distance_km(qth[0], qth[1], f["lat"], f["lon"]), 1)
                    a["az"] = round(bearing(qth[0], qth[1], f["lat"], f["lon"]))
                tr = a["_trail"]
                sq = a["squawk"] if a["squawk"] in EMERG_SQ else ""
                if not tr or now - tr[-1][2] >= TRAIL_EVERY_S or (len(tr[-1]) > 3) != bool(sq):
                    tr.append([f["lat"], f["lon"], round(now, 1)] + ([sq] if sq else []))
        cb = self.on_update
        if cb:
            try:
                cb(icao, dict(f), now)
            except Exception:
                pass

    def _drop_stale(self):
        now = time.time()
        with self.lock:
            for k in [k for k, a in self.aircraft.items() if now - a["last"] > STALE_S]:
                del self.aircraft[k]

    def info(self):
        with self.lock:
            n = len(self.aircraft)
            npos = sum(1 for a in self.aircraft.values() if a["lat"] is not None)
        c = self.cfg
        return {"host": c["host"], "port": c["port"], "on": c["on"], "status": self.status, "error": self.error,
                "since": self.connected_since, "count": self.count, "rate": round(self.rate, 1), "aircraft": n, "with_pos": npos,
                "radar": self.web.get("radar") or c.get("radar", ""), "web": dict(self.web)}

    def aircraft_list(self, since=0.0):
        """The aircraft with their trail points newer than since (all of them for 0): a page asking every few seconds
        gets only the new points and joins them itself."""
        with self.lock:
            out = []
            for a in sorted(self.aircraft.values(), key=lambda x: -x["last"]):
                d = {k: v for k, v in a.items() if not k.startswith("_")}
                d["trail"] = [p for p in a["_trail"] if p[2] > since]
                out.append(d)
            return out


def register(app, feed):
    @app.route("/api/fr24", methods=["GET"])
    def api_fr24():
        """State of the FR24 receiver; with ?ac=1 also its aircraft (trail points newer than ?since=). Every request
        keeps the connection up for IDLE_S, except ?peek=1 (the page asks only for the radar code)."""
        if not request.args.get("peek"):
            feed.want()
        d = feed.info()
        d["t"] = round(time.time(), 1)
        if request.args.get("ac"):
            try:
                since = float(request.args.get("since") or 0)
            except ValueError:
                since = 0.0
            d["aircraft"] = feed.aircraft_list(since)
        return jsonify(d)

    @app.route("/api/fr24", methods=["POST"])
    def api_fr24_set():
        """SETTINGS › FR24 RECEIVER: {"host", "port", "on"} for the whole station (data\\fr24.json)."""
        j = request.get_json(force=True) or {}
        try:
            feed.set_cfg(j.get("host", ""), j.get("port") or DEFAULT_PORT, j.get("on", True))
        except (ValueError, TypeError, OSError) as e:
            return jsonify(error=str(e)), 400
        feed.want()
        return jsonify(feed.info())

"""SETTINGS › SDR SOURCES: the SDR setup inside RADIMCOM (the launcher), instead of the separate window (setup_web.py).

The page assigns a source to VFO A–D: a local device (RTL-SDR, LimeSDR, Airspy on USB), a dongle of an rtl_tcp server,
a SpyServer, or the dongle of another VFO (chained). APPLY writes vfos.json and restarts only the VFOs that changed:
a VFO that keeps its source keeps its settings (config_X.json: frequency, AGC, memories of the page…), also when it
moves to another letter; a VFO with a new source starts from the defaults (its old settings go to data/config_backup/).
PPM and the upconverter LO typed here are written into the settings of the VFO (they are read at its start).

The launcher holds the VFO processes in Procs; the routes are /api/sources/*.
Local dongles opened by a running VFO cannot be listed by USB (they are busy): they are taken from vfos.json.
Writing the EEPROM serial numbers needs the dongles free: STOP USB VFOs first (POST /api/sources/stop_usb).
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

from flask import jsonify, request

import serverlog
import setup_sdr
from paths import BASE, data

LOCAL = ("rtl", "lime", "airspy")            # drivers of devices on this PC's USB
UNPLUG_WAIT_S = 30
BACK_WAIT_S = 20
STOP_WAIT_S = 10

usb_lock = threading.Lock()                  # one USB enumeration / EEPROM access at a time
apply_lock = threading.Lock()


class Procs:
    """The VFO receiver processes of the launcher (app.py --vfo X), by VFO name."""

    def __init__(self, labels):
        self.p = {}
        self.labels = labels                 # pid -> VFO name (CPU / MEM indicator, sysload.py)

    def start(self, v):
        p = serverlog.spawn([sys.executable, os.path.join(BASE, "app.py"), "--vfo", v["name"]], v["name"],
                            stdin=subprocess.PIPE, cwd=BASE)
        self.p[v["name"]] = p
        self.labels[p.pid] = v["name"]
        return p

    def start_all(self, vfos):
        # VFOs with their own dongle first, chained VFOs (sharing a dongle, "chain": "A") after them.
        for v in sorted(vfos, key=lambda v: bool(v.get("chain"))):
            self.start(v)
            # Dongles are opened one after another; opening them at the same time through libusb is unreliable.
            time.sleep(0.5 if v.get("chain") else 1.5)

    def alive(self, name):
        p = self.p.get(name)
        return p is not None and p.poll() is None

    def stop(self, names):
        """Ends these VFO processes as at the end of RADIMCOM (their input closes), terminates the stuck ones."""
        ps = [(n, self.p.pop(n)) for n in names if n in self.p]
        for _, p in ps:
            try:
                p.stdin.close()
            except OSError:
                pass
        for n, p in ps:
            try:
                p.wait(STOP_WAIT_S)
            except subprocess.TimeoutExpired:
                p.terminate()
                try:
                    p.wait(3)
                except subprocess.TimeoutExpired:
                    p.kill()
            self.labels.pop(p.pid, None)
            print(f"SDR SOURCES: VFO {n} stopped")

    def all(self):
        return list(self.p.values())


# ---------- what is assigned now ----------

def ident(v, by_name):
    """What the VFO receives from: ("dev", driver, serial) or ("chain", identity of the owner)."""
    if v.get("chain"):
        o = by_name.get(v["chain"])
        return ("chain",) + (ident(o, by_name) if o else ("?", v["chain"]))
    return ("dev", v.get("driver", "rtl"), str(v.get("serial", "")))


def read_cfg(v):
    try:
        with open(data(v["config"]), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, KeyError):
        return {}


def current(vfos, procs):
    """The VFOs for the page: the vfos.json entry with ppm / LO from its settings and whether it runs."""
    out = []
    for v in vfos:
        c = read_cfg(v)
        x = {k: v.get(k) for k in ("name", "serial", "driver", "chain", "note", "port")}
        x["driver"] = v.get("driver", "rtl") if not v.get("chain") else None
        lo = c.get("lo_offset_hz", (v.get("init") or {}).get("lo_offset_hz", 0)) or 0
        upc = c.get("upconv", (v.get("init") or {}).get("upconv", "off"))
        x.update(ppm=c.get("ppm", (v.get("init") or {}).get("ppm", 0)), lo_mhz=lo / 1e6 if lo and upc != "off" else None,
                 running=procs.alive(v["name"]))
        out.append(x)
    return out


# ---------- the devices ----------

def _vfo_dev_info(vfos):
    """USB name, index and tuner of the devices open in the running VFOs (their /api/state "dev_info"), by VFO name."""
    from concurrent.futures import ThreadPoolExecutor
    from urllib.request import urlopen

    def one(v):
        try:
            with urlopen(f"http://127.0.0.1:{v['port']}/api/state", timeout=1.5) as r:
                return v["name"], json.loads(r.read().decode()).get("dev_info") or {}
        except Exception:
            return v["name"], {}
    if not vfos:
        return {}
    with ThreadPoolExecutor(len(vfos)) as ex:
        return dict(ex.map(one, vfos))


def list_devices(vfos, procs, servers):
    """Local devices (USB) + the busy ones of running VFOs + the network ones. -> (devices, server errors, no_serials)"""
    with usb_lock:
        local = setup_sdr.devices([])
    busy = [v for v in vfos if not v.get("chain") and v.get("driver", "rtl") in LOCAL and procs.alive(v["name"])]
    keys = {(d["driver"], d["serial"]) for d in local}
    info = _vfo_dev_info(busy)
    # a dongle open in a running VFO is listed without a serial number (or not at all): it comes from vfos.json,
    # its USB name, index and tuner from the VFO itself
    for v in busy:
        k = (v.get("driver", "rtl"), str(v.get("serial", "")))
        if k in keys:
            continue
        i = info.get(v["name"]) or {}
        blank = next((d for d in local if d["driver"] == k[0] and not d["serial"]
                      and (i.get("index") is None or d.get("index") == i.get("index"))), None)
        if blank:
            local.remove(blank)
        name = i.get("usb") or (blank or {}).get("name") or setup_sdr.DEVICE_NAMES.get(k[0], k[0])
        local.append({"driver": k[0], "serial": k[1], "name": name, "busy": v["name"], "tuner": i.get("tuner"),
                      "index": i.get("index", (blank or {}).get("index"))})
    net, errors = setup_sdr.net_devices(servers) if servers else ([], [])
    devs = local + net
    rtl = [d for d in devs if d["driver"] == "rtl" and not d.get("busy")]
    bad = {d["index"] for d in setup_sdr.to_rewrite(rtl)}
    taken = {d["serial"] for d in devs if d["driver"] == "rtl"}
    out = []
    for d in devs:
        x = {"driver": d["driver"], "serial": d["serial"], "name": d.get("name", ""), "index": d.get("index"),
             "busy": d.get("busy"), "tuner": d.get("tuner")}
        if d["driver"] == "rtl" and d.get("index") in bad and not d.get("busy"):
            x["rewrite"] = True
            new = setup_sdr.unique_serial(d["serial"] or "00000000", taken)
            if new:
                taken.add(new)
            x["suggest"] = new or ""
        out.append(x)
    no_serials = bool(local) and not any(d["serial"] for d in local)
    return out, errors, no_serials


def servers_arg(raw):
    """Network servers from the page ("192.168.1.50, sdr://host:5555"), or None = the saved ones."""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.replace(";", ",").replace(" ", ",").split(",")
    return [str(s).strip() for s in raw if str(s).strip()]


# ---------- the public SpyServer directory (https://airspy.com/directory/) ----------

DIRECTORY_URL = "https://airspy.com/directory/status.json"
DIRECTORY_KEEP_S = 300
_directory = {"t": 0.0, "servers": None, "error": None}


def directory():
    """The SpyServers of the Airspy directory for the DIRECTORY list: host, port, device, owner (call), antenna,
    location with the distance and bearing from the QTH, frequency range, IQ rate, clients, control. Owner e-mails are
    left out. Fetched at most every 5 minutes."""
    import math
    from urllib.request import Request, urlopen
    now = time.time()
    if _directory["servers"] is None or now - _directory["t"] > DIRECTORY_KEEP_S:
        try:
            req = Request(f"{DIRECTORY_URL}?t={int(now)}", headers={"User-Agent": "RADIMCOM"})
            with urlopen(req, timeout=12) as r:
                raw = json.loads(r.read().decode("utf-8", "replace")).get("servers", [])
            _directory.update(t=now, servers=raw, error=None)
        except Exception as e:  # noqa: BLE001 - shown on the page, the last list stays
            _directory.update(t=now, error=str(e))
    raw = _directory["servers"] or []
    try:
        import location
        q = location.load()
        qlat, qlon = math.radians(float(q["lat"])), math.radians(float(q["lon"]))
    except Exception:  # noqa: BLE001
        qlat = qlon = None
    out = []
    for s in raw:
        host, port = str(s.get("streamingHost") or "").strip(), s.get("streamingPort")
        if not host or not port:
            continue
        loc = s.get("antennaLocation") or {}
        km = az = None
        try:
            lat, lon = float(loc["lat"]), float(loc["long"])
            if qlat is not None:
                p2, l2 = math.radians(lat), math.radians(lon)
                d = 2 * math.asin(math.sqrt(math.sin((p2 - qlat) / 2) ** 2
                                            + math.cos(qlat) * math.cos(p2) * math.sin((l2 - qlon) / 2) ** 2))
                km = round(d * 6371.0)
                y = math.sin(l2 - qlon) * math.cos(p2)
                x = math.cos(qlat) * math.sin(p2) - math.sin(qlat) * math.cos(p2) * math.cos(l2 - qlon)
                az = round((math.degrees(math.atan2(y, x)) + 360) % 360)
        except (KeyError, TypeError, ValueError):
            lat = lon = None
        out.append({"addr": f"sdr://{host}:{port}", "owner": str(s.get("ownerName") or "")[:40],
                    "device": s.get("deviceType") or "", "antenna": str(s.get("antennaType") or "")[:40],
                    "desc": "" if s.get("generalDescription") in (None, "no description") else str(s["generalDescription"])[:120],
                    "lat": lat, "lon": lon, "km": km, "az": az,
                    "min_hz": s.get("minimumFrequency"), "max_hz": s.get("maximumFrequency"),
                    "center_hz": s.get("currentCenterFrequency"), "iq_rate": s.get("maximumIQSampleRate"),
                    "clients": s.get("currentClientCount", 0), "max_clients": s.get("maxClients", 0),
                    "control": bool(s.get("fullControlAllowed")), "online": bool(s.get("online"))})
    return {"servers": out, "error": _directory["error"], "age_s": round(now - _directory["t"]) if _directory["t"] else None,
            "source": "https://airspy.com/directory/"}


# ---------- APPLY ----------

def build(rows, devs):
    """The page's rows -> (new vfos.json entries, errors), as setup_web.api_save (empty rows skipped, letters close up)."""
    vfos, errors = [], []
    for i, r in enumerate(rows[:setup_sdr.MAX_VFOS]):
        name = setup_sdr.NAMES[i]
        port = setup_sdr.FIRST_PORT + i
        note = r.get("note")
        if r.get("chain"):
            owner = next((v for v in vfos if v["name"] == r["chain"] and "chain" not in v), None)
            if owner is None:
                errors.append(f"VFO {name}: VFO {r['chain']} has no source of its own")
                continue
            vfos.append(setup_sdr.make_chained(owner, name, port, note))
            continue
        dev = next((d for d in devs if [d["driver"], d["serial"]] == list(r.get("device") or [])), None)
        if dev is None:
            errors.append(f"VFO {name}: the source is not connected")
            continue
        lo = None
        if r.get("lo") not in (None, ""):
            try:
                lo = setup_sdr.lo_mhz(r["lo"])
            except ValueError as e:
                errors.append(f"VFO {name}: {e}")
                continue
        try:
            ppm = int(float(str(r.get("ppm") or 0).replace(",", ".")))
        except ValueError:
            errors.append(f"VFO {name}: ppm must be a whole number")
            continue
        vfos.append(setup_sdr.make_entry(dev, name, port, ppm, lo, note))
    return vfos, errors


def _patch(c, init):
    """PPM and the upconverter of the page into kept settings; -> True when something changed."""
    want = {"ppm": init.get("ppm", 0), "upconv": init.get("upconv", "off"), "lo_offset_hz": init.get("lo_offset_hz", 0)}
    old_up = c.get("upconv", "off") != "off" and bool(c.get("lo_offset_hz"))
    new_up = want["upconv"] != "off" and bool(want["lo_offset_hz"])
    changed = False
    if int(c.get("ppm", 0) or 0) != int(want["ppm"]):
        c["ppm"] = want["ppm"]
        changed = True
    if old_up != new_up or (new_up and abs(float(c.get("lo_offset_hz", 0)) - want["lo_offset_hz"]) > 0.5):
        # the upconverter switched on / off or another LO: "auto" keeps the choice of the page when it was on already
        c["lo_offset_hz"] = want["lo_offset_hz"]
        if not new_up:
            c["upconv"] = "off"
        elif not old_up:
            c["upconv"] = "auto"
        changed = True
    return changed


def apply(new, old, procs, servers, setup_path, setup):
    """Writes vfos.json and restarts what changed. -> {"restart": [...], "kept": [...], "stopped": [...], "backup"}
    A new VFO takes the settings of the old VFO with the same source (the same letter first)."""
    old_by = {v["name"]: v for v in old}
    new_by = {v["name"]: v for v in new}
    src = {}                                   # new name -> old entry with the same source, or None
    used = set()
    for same_name in (True, False):
        for v in new:
            if v["name"] in src:
                continue
            k = ident(v, new_by)
            o = next((o for o in old if o["name"] not in used and ident(o, old_by) == k
                      and (o["name"] == v["name"]) == same_name), None)
            if o is not None:
                src[v["name"]] = o
                used.add(o["name"])
    # a chained VFO whose owner got another dongle keeps its settings when it is chained under the same letter again
    for v in new:
        if v["name"] not in src and v.get("chain"):
            o = old_by.get(v["name"])
            if o is not None and o.get("chain") and o["name"] not in used:
                src[v["name"]] = o
                used.add(o["name"])
    for v in new:
        src.setdefault(v["name"], None)
    # what restarts: a new source, settings from another letter, other ppm / LO, a stopped VFO, the chain of a restarted one
    restart = set()
    for v in new:
        o = src[v["name"]]
        if o is None or o["name"] != v["name"] or not procs.alive(v["name"]):
            restart.add(v["name"])
        elif not v.get("chain") and _patch(read_cfg(o), v["init"]):
            restart.add(v["name"])
    for v in new:
        if v.get("chain") and v["chain"] in restart:
            restart.add(v["name"])
    # stop: the restarted ones, the removed ones and those whose settings go to another letter
    stop = [v["name"] for v in old if v["name"] not in new_by or v["name"] in restart
            or any(o is not None and o["name"] == v["name"] and n != v["name"] for n, o in src.items())]
    procs.stop(stop)

    # the settings are read only now: a VFO saves its last frequency etc. when it ends
    cfg = {}
    for n in restart:
        o = src[n]
        if o is not None:
            c = read_cfg(o)
            if not new_by[n].get("chain"):
                _patch(c, new_by[n]["init"])
            cfg[n] = c
    stamp = time.strftime("%Y%m%d_%H%M%S")
    bdir = data("config_backup", stamp)
    backed = []

    def backup(fname):
        p = data(fname)
        if os.path.exists(p):
            os.makedirs(bdir, exist_ok=True)
            shutil.copy2(p, os.path.join(bdir, fname))
            backed.append(fname)

    backup(os.path.basename(setup_path))
    touched = set(stop) | restart
    for n in touched:
        backup(f"config_{n}.json")
    for n in touched:
        for f in (f"config_{n}.json", f"config_{n}.json.bak"):
            try:
                os.remove(data(f))
            except OSError:
                pass
    for n, c in cfg.items():                   # a new source (no entry here) starts from "init" (ensure_configs)
        with open(data(f"config_{n}.json"), "w", encoding="utf-8") as f:
            json.dump(c, f, indent=2, ensure_ascii=False)

    out = dict(setup)                          # keeps "port", "host", "update_check" … of vfos.json
    out["vfos"] = new
    if servers:
        out["rtltcp_servers"] = list(servers)
    else:
        out.pop("rtltcp_servers", None)
    tmp = setup_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    os.replace(tmp, setup_path)
    order = [v["name"] for v in new]
    return {"restart": [n for n in order if n in restart], "stopped": [n for n in stop if n not in new_by],
            "kept": [n for n in order if n not in restart],
            "fresh": [n for n in order if src[n] is None],
            "backup": bdir if backed else None, "setup": out}


def register(app, procs, state, ensure_configs):
    """Routes of SETTINGS › SDR SOURCES on the launcher. state = {"setup": vfos.json, "vfos": its list (shared with
    /api/vfos, changed in place), "path": vfos.json path}."""

    def same_origin():
        """Only pages of this server may change anything (no other web site through the browser)."""
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            return jsonify({"error": "not allowed"}), 403
        return None

    def saved_servers():
        return [s for s in state["setup"].get("rtltcp_servers", []) if str(s).strip()]

    @app.route("/api/sources")
    def api_sources():
        servers = servers_arg(request.args.get("servers"))
        if servers is None:
            servers = saved_servers()
        servers = setup_sdr.normalize_servers(servers)     # SpyServers typed as host:port get sdr://
        devs, errors, no_serials = list_devices(state["vfos"], procs, servers)
        return jsonify({"devices": devs, "servers": servers, "saved_servers": saved_servers(), "server_errors": errors,
                        "no_serials": no_serials, "current": current(state["vfos"], procs),
                        "max_vfos": setup_sdr.MAX_VFOS})

    @app.route("/api/sources/directory")
    def api_sources_directory():
        """The public SpyServers (Airspy directory) to pick from."""
        return jsonify(directory())

    @app.route("/api/sources/apply", methods=["POST"])
    def api_sources_apply():
        bad = same_origin()
        if bad:
            return bad
        body = request.get_json(force=True, silent=True) or {}
        servers = servers_arg(body.get("servers"))
        if servers is None:
            servers = saved_servers()
        servers = setup_sdr.normalize_servers(servers)
        with apply_lock:
            devs, _, _ = list_devices(state["vfos"], procs, servers)
            new, errors = build(body.get("vfos", []), devs)
            if errors:
                return jsonify({"error": "; ".join(errors)}), 400
            if not new:
                return jsonify({"error": "no VFO has a source"}), 400
            res = apply(new, state["vfos"], procs, servers, state["path"], state["setup"])
            state["setup"] = res.pop("setup")
            state["vfos"][:] = new
            ensure_configs(new)
            starting = [v for v in new if v["name"] in res["restart"]]
            print("SDR SOURCES applied: " + ", ".join(f"VFO {v['name']} = {v.get('chain') or v['serial']}" for v in new)
                  + f"; restarting {', '.join(res['restart']) or 'none'}")
            threading.Thread(target=procs.start_all, args=(starting,), name="sources_start", daemon=True).start()
        return jsonify(res)

    @app.route("/api/sources/stop_usb", methods=["POST"])
    def api_sources_stop_usb():
        """Frees the local dongles for the EEPROM: stops the VFOs with a USB device (and the ones chained to them);
        APPLY starts them again."""
        bad = same_origin()
        if bad:
            return bad
        vfos = state["vfos"]
        usb = {v["name"] for v in vfos if not v.get("chain") and v.get("driver", "rtl") in LOCAL}
        names = [v["name"] for v in vfos if v["name"] in usb or v.get("chain") in usb]
        procs.stop(names)
        return jsonify({"stopped": names})

    @app.route("/api/sources/serials", methods=["POST"])
    def api_sources_serials():
        """{"items": [{"index": 1, "serial": "SDR00002"}]}: new serial numbers into the EEPROM (backed up first)."""
        bad = same_origin()
        if bad:
            return bad
        res = []
        with usb_lock:
            for it in (request.get_json(force=True, silent=True) or {}).get("items", []):
                try:
                    backup = setup_sdr.write_serial(int(it["index"]), str(it["serial"]))
                    res.append({"index": it["index"], "ok": True, "backup": backup})
                except Exception as e:
                    res.append({"index": it["index"], "ok": False, "error": str(e)})
        return jsonify({"results": res})

    @app.route("/api/sources/unplug", methods=["POST"])
    def api_sources_unplug():
        """{"devices": [[driver, serial], …]} (free ones): waits until one of them is unplugged (IDENTIFY)."""
        bad = same_origin()
        if bad:
            return bad
        want = [tuple(k) for k in (request.get_json(force=True, silent=True) or {}).get("devices", [])]
        before = {k: want.count(k) for k in want}
        until = time.time() + UNPLUG_WAIT_S
        while time.time() < until:
            with usb_lock:
                now = setup_sdr.present()
            gone = {k for k in before if now.get(k, 0) < before[k]}
            if len(gone) == 1:
                return jsonify({"gone": list(gone.pop())})
            if len(gone) > 1:
                return jsonify({"gone": None, "error": "more than one device is missing: unplug only one"})
            time.sleep(0.7)
        return jsonify({"gone": None, "error": "nothing was unplugged"})

    @app.route("/api/sources/back", methods=["POST"])
    def api_sources_back():
        """{"device": [driver, serial]}: waits until it is connected again."""
        bad = same_origin()
        if bad:
            return bad
        k = tuple((request.get_json(force=True, silent=True) or {}).get("device", []))
        until = time.time() + BACK_WAIT_S
        while time.time() < until:
            with usb_lock:
                if k in setup_sdr.present():
                    return jsonify({"back": True})
            time.sleep(0.7)
        return jsonify({"back": False})

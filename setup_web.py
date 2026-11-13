"""SDR setup in a window: the same wizard as setup_sdr.py (finds the SDRs, unique RTL-SDR serial numbers in the
EEPROM, assignment to VFO A–D, chaining, ppm, upconverter LO, description, vfos.json), as a page (static/setup.html).

RADIMCOM.exe --setup (or SDR setup in its tray menu / Start menu) stops the receiver, starts this server and shows
the page in its window; after SAVE (or CANCEL) the page tells the app ("setup-done") and the receiver starts again.

  python setup_web.py [--port 8433]      then open http://localhost:8433 (only from this PC)

The receiver must not run meanwhile (the dongles are busy). Ends when its input closes (RADIMCOM.exe) or by POST /api/quit.
"""
import os
import sys
import threading
import time
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_from_directory

import setup_sdr
from paths import BASE, data

PORT = 8433
UNPLUG_WAIT_S = 30
BACK_WAIT_S = 20

app = Flask(__name__, static_folder=os.path.join(BASE, "static"))
lock = threading.Lock()          # one USB enumeration / EEPROM access at a time


def key(d):
    return [d["driver"], d["serial"]]


def current():
    """The saved assignment (vfos.json) to prefill the page, or []."""
    try:
        import json
        with open(data("vfos.json"), encoding="utf-8") as f:
            return json.load(f).get("vfos", [])
    except (OSError, ValueError):
        return []


@app.before_request
def same_origin():
    """Only pages of this server may change anything (no other web site through the browser)."""
    if request.method == "POST":
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).hostname not in ("localhost", "127.0.0.1"):
            return jsonify({"error": "not allowed"}), 403
    return None


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "setup.html")


@app.route("/api/devices")
def api_devices():
    with lock:
        devs = setup_sdr.devices()
    rtl = [d for d in devs if d["driver"] == "rtl"]
    bad = {d["index"] for d in setup_sdr.to_rewrite(rtl)}
    taken = {d["serial"] for d in rtl}
    out = []
    for d in devs:
        x = {"driver": d["driver"], "serial": d["serial"], "name": d.get("name", ""), "index": d.get("index"),
             "label": setup_sdr.label(d)}
        if d["driver"] == "rtl" and d["index"] in bad:
            x["rewrite"] = True
            new = setup_sdr.unique_serial(d["serial"] or "00000000", taken)
            if new:
                taken.add(new)
            x["suggest"] = new or ""
        out.append(x)
    return jsonify({"devices": out, "no_serials": bool(devs) and not any(d["serial"] for d in devs),
                    "current": current(), "max_vfos": setup_sdr.MAX_VFOS, "first_port": setup_sdr.FIRST_PORT})


@app.route("/api/serials", methods=["POST"])
def api_serials():
    """{"items": [{"index": 1, "serial": "SDR00002"}]}: writes new serial numbers (EEPROM backed up first)."""
    res = []
    with lock:
        for it in (request.get_json(force=True, silent=True) or {}).get("items", []):
            try:
                backup = setup_sdr.write_serial(int(it["index"]), str(it["serial"]))
                res.append({"index": it["index"], "ok": True, "backup": backup})
            except Exception as e:
                res.append({"index": it["index"], "ok": False, "error": str(e)})
    return jsonify({"results": res})


@app.route("/api/unplug", methods=["POST"])
def api_unplug():
    """{"devices": [[driver, serial], …]} (the free ones, as listed): waits until one of them is unplugged.
    -> {"gone": [driver, serial]}, {"gone": null, "error": …}"""
    want = [tuple(k) for k in (request.get_json(force=True, silent=True) or {}).get("devices", [])]
    before = {k: want.count(k) for k in want}
    until = time.time() + UNPLUG_WAIT_S
    while time.time() < until:
        with lock:
            now = setup_sdr.present()
        gone = {k for k in before if now.get(k, 0) < before[k]}
        if len(gone) == 1:
            return jsonify({"gone": list(gone.pop())})
        if len(gone) > 1:
            return jsonify({"gone": None, "error": "more than one device is missing: unplug only one"})
        time.sleep(0.7)
    return jsonify({"gone": None, "error": "nothing was unplugged"})


@app.route("/api/back", methods=["POST"])
def api_back():
    """{"device": [driver, serial]}: waits until it is connected again. -> {"back": true/false}"""
    k = tuple((request.get_json(force=True, silent=True) or {}).get("device", []))
    until = time.time() + BACK_WAIT_S
    while time.time() < until:
        with lock:
            if k in setup_sdr.present():
                return jsonify({"back": True})
        time.sleep(0.7)
    return jsonify({"back": False})


@app.route("/api/save", methods=["POST"])
def api_save():
    """{"vfos": [{"name": "A", "device": [driver, serial]} or {"name": "B", "chain": "A"}, with "ppm", "lo" (MHz or
    null), "note"}]} -> vfos.json (the old settings go to data/config_backup/)."""
    rows = (request.get_json(force=True, silent=True) or {}).get("vfos", [])
    with lock:
        devs = setup_sdr.devices()
    vfos, errors = [], []
    for i, r in enumerate(rows[:setup_sdr.MAX_VFOS]):
        name = setup_sdr.NAMES[i]
        port = setup_sdr.FIRST_PORT + i
        note = r.get("note")
        if r.get("chain"):
            owner = next((v for v in vfos if v["name"] == r["chain"] and "chain" not in v), None)
            if owner is None:
                errors.append(f"VFO {name}: VFO {r['chain']} has no dongle of its own")
                continue
            vfos.append(setup_sdr.make_chained(owner, name, port, note))
            continue
        dev = next((d for d in devs if key(d) == list(r.get("device") or [])), None)
        if dev is None:
            errors.append(f"VFO {name}: the device is not connected")
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
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400
    if not vfos:
        return jsonify({"error": "no VFO has an SDR"}), 400
    backup = setup_sdr.save(vfos)
    print(f"SDR setup saved: " + ", ".join(f"VFO {v['name']} = {v.get('chain') or v['serial']}" for v in vfos))
    return jsonify({"saved": setup_sdr.VFOS_PATH, "backup": backup, "vfos": vfos})


@app.route("/api/quit", methods=["POST"])
def api_quit():
    threading.Timer(0.3, lambda: os._exit(0)).start()
    return jsonify({"ok": True})


def exit_with_shell():
    sys.stdin.read()
    os._exit(0)


def main():
    port = PORT
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    if os.environ.get("RADIMCOM_SHELL"):
        threading.Thread(target=exit_with_shell, daemon=True).start()
    import logging
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(f"RADIMCOM SDR setup: http://localhost:{port}", flush=True)
    app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()

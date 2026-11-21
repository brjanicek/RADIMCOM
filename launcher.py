"""VFO A–D launcher: for every VFO in vfos.json it starts a separate receiver process (app.py --vfo X)
with its own dongle (by serial number), port and settings, and itself serves the page and the VFO list
on the main port. The page then talks to the receivers directly through their ports.
A chained VFO ("chain": "A") has no dongle of its own: it gets the samples of VFO A (iqshare.py).

VFO settings (config_X.json) are created at the first start from config.json and the "init" entry in vfos.json.
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import threading
import time

from flask import Flask, jsonify, request, send_from_directory

import backup
import rotor
import serverlog
import sources
import sysload
import update_check
from paths import BASE, data

VFOS_PATH = data("vfos.json")


def _valid_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            json.load(f)
        return True
    except (OSError, ValueError):
        return False


def ensure_configs(vfos):
    with open(data("config.json"), encoding="utf-8") as f:
        template = json.load(f)
    for k in ("dongles", "device", "vfo", "serial"):
        template.pop(k, None)
    for v in vfos:
        path = data(v["config"])
        if os.path.exists(path):
            if _valid_json(path):
                continue
            # damaged (e.g. zero bytes after a power cut): keep it as .broken, restore .bak or create a new one
            os.replace(path, path + ".broken")
            if _valid_json(path + ".bak"):
                shutil.copyfile(path + ".bak", path)
                print(f"VFO {v['name']}: {v['config']} was damaged, restored from {v['config']}.bak")
                continue
            print(f"VFO {v['name']}: {v['config']} was damaged (kept as .broken), creating a new one")
        c = copy.deepcopy(template)
        c.update(v.get("init", {}))
        c["device"] = 0
        with open(path, "w", encoding="utf-8") as f:
            json.dump(c, f, indent=2, ensure_ascii=False)
        print(f"VFO {v['name']}: created {v['config']}")


def main():
    if os.path.exists(VFOS_PATH):
        with open(VFOS_PATH, encoding="utf-8") as f:
            setup = json.load(f)
    else:
        from paths import no_source_setup
        setup = no_source_setup()           # no dongles assigned yet: VFO A without a source, nothing written
        print("No vfos.json: VFO A without a source (assign the dongles in SETTINGS › SDR SOURCES)")
    vfos = setup["vfos"]
    ensure_configs(vfos)
    # one rotor for the station: its settings move from the VFO configs (up to 0.114beta1) to rotor.json
    src = rotor.migrate(data("rotor.json"), [data(v["config"]) for v in vfos])
    if src:
        print(f"Rotor: settings moved from {src} to rotor.json (the rotor is now run by VFO {vfos[0]['name']})")

    labels = {}                 # pid of a VFO server → its name (the CPU / MEM indicator shows each VFO)
    # the VFO processes (sources.py): SETTINGS › SDR SOURCES restarts single VFOs
    procs = sources.Procs(labels)
    procs.start_all(vfos)

    app = Flask(__name__, static_folder="static")
    src_state = {"setup": setup, "vfos": vfos, "path": VFOS_PATH}   # shared by SDR SOURCES and BACKUP
    sources.register(app, procs, src_state, ensure_configs)

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/api/sysload")
    def api_sysload():
        """CPU and memory of RADIMCOM (server by VFO, the window) and of the whole PC (indicator under the S-meter)."""
        return jsonify(sysload.load(labels))

    @app.route("/api/spacewx")
    def api_spacewx():
        """Space weather and the HF bands at the station for the PROP tab and the chip under the S-meter (spacewx.py);
        here once for the whole station, the page asks the launcher like /api/sysload."""
        import location
        import spacewx
        q = location.load()
        return jsonify(spacewx.summary(q.get("lat"), q.get("lon")))

    @app.route("/api/clock", methods=["GET", "POST"])
    def api_clock():
        """PC clock against NTP for FT8 / WSPR (clocksync.py): GET = the offset (cached 10 min, ?force=1 measures now),
        POST = sync the clock by it (an administrator consent of Windows when not elevated)."""
        import clocksync
        from flask import request as rq
        if rq.method == "POST":
            return jsonify(clocksync.sync())
        return jsonify(clocksync.offset(force=rq.args.get("force") == "1"))

    @app.route("/api/vfos")
    def api_vfos():
        # "rotor": the VFO whose process holds the rotor (the first one, as in app.py ROTOR_HERE)
        return jsonify([dict({k: v.get(k) for k in ("name", "port", "serial", "note", "chain")}, rotor=i == 0)
                        for i, v in enumerate(vfos)])

    def shutdown(code=0):
        """The VFO receivers end as with the launcher closed (their input closes), then the launcher
        (when RADIMCOM.exe closes our input)."""
        for p in procs.all():
            try:
                p.stdin.close()
            except OSError:
                pass
        for p in procs.all():
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.terminate()
        serverlog.close()
        os._exit(code)

    # SETTINGS › GENERAL › BACKUP: export / restore of the settings, factory reset (backup.py)
    backup.register(app, procs, src_state, ensure_configs, shutdown)

    if os.environ.get("RADIMCOM_SHELL"):
        # started by RADIMCOM.exe: it stops the server by closing our input (Exit in its tray menu)
        def exit_with_shell():
            sys.stdin.read()
            print("RADIMCOM.exe closed: stopping the receivers")
            shutdown(0)
        threading.Thread(target=exit_with_shell, name="exit_with_shell", daemon=True).start()

    @app.route("/api/update")
    def api_update():
        """Newer version on GitHub (update_check.py): the page shows it with the link to its setup."""
        return jsonify(update_check.info())

    @app.route("/api/whatsnew", methods=["GET", "POST"])
    def api_whatsnew():
        """What's new in this version (INSTALL.txt); POST = the window was closed (data\\whatsnew.json)."""
        return jsonify(update_check.whats_new_seen() if request.method == "POST" else update_check.whats_new())

    update_check.start(setup.get("update_check", True))

    port = int(setup.get("port", 8434))
    print(f"RADIMCOM (VFO {', '.join(v['name'] for v in vfos)}): http://localhost:{port}")
    try:
        app.run(host=setup.get("host", "0.0.0.0"), port=port, threaded=True, use_reloader=False)
    finally:
        for p in procs.all():
            p.terminate()

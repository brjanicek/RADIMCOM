"""SETTINGS › GENERAL › BACKUP: the settings of the whole station to a ZIP file and back, and the factory reset.

Runs in the launcher (all VFOs at once). A backup is a ZIP with
    manifest.json   {"app": "RADIMCOM", "version", "created", "items": [...]}
    data/<file>     the files of the items chosen (from data\\)
    browser.json    the page settings of the browser that made it (its localStorage), when "browser" was chosen
Items (ITEMS): VFO settings, VFO sources, memories, station, satellites, ISM devices, map API keys (secret: not chosen by
default) and the page settings of the browser. Logs, recordings, decoder pictures and histories are not settings: they
stay in data\\ (SETTINGS › DATA/LOG exports them).

Restore: the VFOs stop, the files are written, the VFOs start again; the page writes browser.json into its
localStorage. "VFO sources" from another PC: a VFO whose USB dongle is not here stays without a source (a warning
says so: set up the dongles first in SETTINGS › SDR SOURCES, then restore the VFO settings), network sources are taken.
Factory reset: first a full backup (every item) to RADIMCOM\\backup\\, then every file of the items is deleted and
RADIMCOM restarts (exit code RESTART_CODE: RADIMCOM.exe starts the server again) like a fresh installation; the page
clears its localStorage.
"""
import io
import json
import os
import re
import tempfile
import threading
import time
import uuid
import zipfile

from flask import jsonify, request, send_file

from paths import BASE, data

BACKUP_DIR = os.path.join(BASE, "backup")   # the automatic backup of the factory reset (and copies kept there)
RESTART_CODE = 75                           # the launcher ends with it: RADIMCOM.exe starts the server again

# key, title, what it holds, files in data\ (a regex for the VFO configs), chosen by default
ITEMS = [
    {"key": "vfo", "title": "VFO settings", "default": True,
     "note": "frequency, mode, filters, AGC+, audio, decoders and the other settings of each VFO (A–D)",
     "files": ["config.json"], "pattern": r"config_[A-Z]\.json"},
    {"key": "sources", "title": "VFO sources", "default": True,
     "note": "which dongle, rtl_tcp or SpyServer each VFO uses (SETTINGS › SDR SOURCES)", "files": ["vfos.json"]},
    {"key": "memories", "title": "Memories", "default": True,
     "note": "the frequency memories and their groups", "files": ["memories.json", "memory_groups.json"]},
    {"key": "station", "title": "Station", "default": True,
     "note": "location, antennas, rotor, the recordings folder",
     "files": ["location.json", "antennas.json", "rotor.json", "recordings.json"]},
    {"key": "satellites", "title": "Satellites", "default": True,
     "note": "the satellites chosen and their groups", "files": ["sat_setup.json", "sat_groups.json"]},
    {"key": "ism", "title": "ISM devices", "default": True,
     "note": "names, pins and hidden ISM devices, the devices heard", "files": ["ism_devices.json", "ism_known.json"]},
    {"key": "mapkeys", "title": "Map API keys", "default": False, "secret": True,
     "note": "the keys of the map services (e.g. aisstream): the backup file then holds them – keep it safe",
     "files": ["mapkeys.json"]},
    {"key": "browser", "title": "Page settings", "default": True,
     "note": "this browser: layout, open tabs and pages, filters, map settings (also those of the decoders)", "files": []},
]
ITEM_KEYS = [i["key"] for i in ITEMS]
_lock = threading.Lock()
_uploads = {}                               # token -> path of an uploaded backup (until restored or 1 h)


def _version():
    try:
        import update_check
        return update_check.own_version()
    except Exception:
        return ""


def item_files(item):
    """The files of an item that exist in data\\ now (names)."""
    names = [f for f in item["files"] if os.path.isfile(data(f))]
    if item.get("pattern"):
        rx = re.compile(item["pattern"] + r"$")
        names += sorted(f for f in os.listdir(data()) if rx.match(f) and os.path.isfile(data(f)))
    return names


def _item(key):
    return next(i for i in ITEMS if i["key"] == key)


def build_zip(items, browser):
    """-> bytes of a backup ZIP with these items (browser = the localStorage dict of the page, or None)."""
    items = [k for k in ITEM_KEYS if k in items]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        files = {}
        for k in items:
            if k == "browser":
                if isinstance(browser, dict):
                    z.writestr("browser.json", json.dumps(browser, ensure_ascii=False, indent=1))
                continue
            files[k] = item_files(_item(k))
            for f in files[k]:
                z.write(data(f), "data/" + f)
        man = {"app": "RADIMCOM", "version": _version(), "created": time.strftime("%Y-%m-%d %H:%M:%S"),
               "items": [k for k in items if k != "browser" or isinstance(browser, dict)], "files": files}
        z.writestr("manifest.json", json.dumps(man, ensure_ascii=False, indent=1))
    return buf.getvalue()


def stamp_name(prefix="RADIMCOM_backup"):
    return f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}.zip"


def stored():
    """The backups in RADIMCOM\\backup\\, newest first."""
    if not os.path.isdir(BACKUP_DIR):
        return []
    out = []
    for f in os.listdir(BACKUP_DIR):
        p = os.path.join(BACKUP_DIR, f)
        if f.lower().endswith(".zip") and os.path.isfile(p):
            out.append({"name": f, "size": os.path.getsize(p), "mtime": os.path.getmtime(p)})
    return sorted(out, key=lambda x: -x["mtime"])


def read_backup(path):
    """-> (manifest, {name in data\\: bytes}, browser dict or None); ValueError for a file that is no backup."""
    try:
        with zipfile.ZipFile(path) as z:
            man = json.loads(z.read("manifest.json").decode("utf-8"))
            if man.get("app") != "RADIMCOM":
                raise ValueError("not a RADIMCOM backup")
            files = {}
            for n in z.namelist():
                if n.startswith("data/") and not n.endswith("/"):
                    name = n[5:]
                    if "/" in name or "\\" in name or name.startswith("."):
                        continue                # only plain files of data\ (no paths out of it)
                    files[name] = z.read(n)
            browser = json.loads(z.read("browser.json").decode("utf-8")) if "browser.json" in z.namelist() else None
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"not a RADIMCOM backup ({e.__class__.__name__})")
    return man, files, browser


def _files_of(key, files):
    """The names of a backup's files that belong to item key."""
    it = _item(key)
    rx = re.compile(it["pattern"] + r"$") if it.get("pattern") else None
    return [f for f in files if f in it["files"] or (rx and rx.match(f))]


def check_sources(vfos_json, procs, current_vfos):
    """The VFO sources of a backup against the dongles of this PC. -> (vfos entries kept, warnings)"""
    import sources
    try:
        setup = json.loads(vfos_json.decode("utf-8"))
        vfos = list(setup.get("vfos") or [])
    except (ValueError, AttributeError):
        return None, ["the VFO sources of the backup are damaged: not restored"]
    try:
        devs, _, _ = sources.list_devices(current_vfos, procs, [])
    except Exception:
        devs = []
    here = {(d["driver"], str(d["serial"])) for d in devs}
    keep, warn, gone = [], [], set()
    for v in vfos:
        drv = v.get("driver", "rtl")
        if v.get("chain") or drv in ("spyserver", "rtltcp"):
            continue
        if (drv, str(v.get("serial", ""))) not in here:
            gone.add(v["name"])
            warn.append(f"VFO {v['name']}: dongle {v.get('serial') or '?'} ({drv}) is not on this PC – the VFO stays "
                        "without a source. Set up the dongles first in SETTINGS › SDR SOURCES, then restore the VFO "
                        "settings again.")
    for v in vfos:
        if v["name"] in gone:
            continue
        if v.get("chain") and v["chain"] in gone:
            warn.append(f"VFO {v['name']}: it shares the dongle of VFO {v['chain']}, which has none here – "
                        "it stays without a source.")
            continue
        keep.append(v)
    return (dict(setup, vfos=keep), warn)


def register(app, procs, state, ensure_configs, shutdown):
    """Routes on the launcher. state as in sources.register; shutdown(code) ends RADIMCOM (launcher.py)."""
    from urllib.parse import urlsplit

    def same_origin():
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            return jsonify({"error": "not allowed"}), 403
        return None

    @app.route("/api/backup/info")
    def api_backup_info():
        items = []
        for it in ITEMS:
            fs = item_files(it)
            items.append({k: it.get(k) for k in ("key", "title", "note", "default", "secret")}
                         | {"files": fs, "size": sum(os.path.getsize(data(f)) for f in fs)})
        return jsonify({"items": items, "stored": stored(), "dir": BACKUP_DIR})

    @app.route("/api/backup/export", methods=["POST"])
    def api_backup_export():
        bad = same_origin()
        if bad:
            return bad
        body = request.get_json(force=True, silent=True) or {}
        items = [k for k in body.get("items") or [] if k in ITEM_KEYS]
        if not items:
            return jsonify({"error": "nothing chosen"}), 400
        blob = build_zip(items, body.get("browser") if "browser" in items else None)
        return send_file(io.BytesIO(blob), mimetype="application/zip", as_attachment=True, download_name=stamp_name())

    @app.route("/api/backup/stored/<name>")
    def api_backup_stored(name):
        """A backup of RADIMCOM\\backup\\ to download."""
        if name not in {s["name"] for s in stored()}:
            return jsonify({"error": "no such backup"}), 404
        return send_file(os.path.join(BACKUP_DIR, name), mimetype="application/zip", as_attachment=True,
                         download_name=name)

    @app.route("/api/backup/inspect", methods=["POST"])
    def api_backup_inspect():
        """An uploaded backup (file) or one of RADIMCOM\\backup\\ (name): what it holds, before the restore."""
        bad = same_origin()
        if bad:
            return bad
        now = time.time()
        for t, (p, at) in list(_uploads.items()):
            if now - at > 3600:
                _uploads.pop(t, None)
                try:
                    os.remove(p)
                except OSError:
                    pass
        if "file" in request.files:
            fd, path = tempfile.mkstemp(suffix=".zip", prefix="radimcom_restore_")
            os.close(fd)
            request.files["file"].save(path)
            token = uuid.uuid4().hex
            _uploads[token] = (path, now)
            src = request.files["file"].filename or "backup.zip"
        else:
            name = (request.form.get("name") or (request.get_json(silent=True) or {}).get("name") or "")
            if name not in {s["name"] for s in stored()}:
                return jsonify({"error": "no such backup"}), 404
            path, token, src = os.path.join(BACKUP_DIR, name), "stored:" + name, name
        try:
            man, files, browser = read_backup(path)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        have = [k for k in ITEM_KEYS if (k == "browser" and browser is not None) or (k != "browser" and _files_of(k, files))]
        warn = []
        if "sources" in have:
            _, warn = check_sources(files["vfos.json"], procs, state["vfos"])
        return jsonify({"token": token, "source": src, "created": man.get("created"), "version": man.get("version"),
                        "items": have, "warnings": warn})

    def _path_of(token):
        if token.startswith("stored:"):
            name = token[7:]
            return os.path.join(BACKUP_DIR, name) if name in {s["name"] for s in stored()} else None
        return (_uploads.get(token) or (None,))[0]

    @app.route("/api/backup/restore", methods=["POST"])
    def api_backup_restore():
        bad = same_origin()
        if bad:
            return bad
        body = request.get_json(force=True, silent=True) or {}
        path = _path_of(str(body.get("token") or ""))
        if not path or not os.path.isfile(path):
            return jsonify({"error": "the backup is gone – choose it again"}), 400
        items = [k for k in body.get("items") or [] if k in ITEM_KEYS]
        try:
            _man, files, browser = read_backup(path)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        with _lock:
            warn = []
            new_setup = None
            if "sources" in items and "vfos.json" in files:
                new_setup, warn = check_sources(files["vfos.json"], procs, state["vfos"])
                if new_setup is not None and not new_setup["vfos"]:
                    warn.append("No VFO of the backup has its source on this PC: the VFO sources stay as they are.")
                    new_setup = None
            # the VFOs save their settings when they end: stopped first, then the files are written
            old = list(state["vfos"])
            procs.stop([v["name"] for v in old])
            written = []
            for k in items:
                if k in ("browser", "sources"):
                    continue
                for f in _files_of(k, files):
                    tmp = data(f) + ".restore"
                    with open(tmp, "wb") as fh:
                        fh.write(files[f])
                    os.replace(tmp, data(f))
                    written.append(f)
            if new_setup is not None:
                setup = dict(state["setup"])
                setup.update({k: v for k, v in new_setup.items() if k != "port"})   # this PC's page port stays
                with open(state["path"] + ".restore", "w", encoding="utf-8") as fh:
                    json.dump(setup, fh, indent=2, ensure_ascii=False)
                os.replace(state["path"] + ".restore", state["path"])
                written.append("vfos.json")
                state["setup"] = setup
                state["vfos"][:] = setup["vfos"]
            ensure_configs(state["vfos"])
            threading.Thread(target=procs.start_all, args=(list(state["vfos"]),), name="restore_start",
                             daemon=True).start()
        if not str(body.get("token")).startswith("stored:"):
            _uploads.pop(str(body.get("token")), None)
            try:
                os.remove(path)
            except OSError:
                pass
        print(f"BACKUP restored: {', '.join(items)} ({len(written)} files)")
        return jsonify({"ok": True, "written": written, "warnings": warn,
                        "browser": browser if "browser" in items else None})

    @app.route("/api/backup/reset", methods=["POST"])
    def api_backup_reset():
        """Factory reset: a full backup to RADIMCOM\\backup\\, every settings file deleted, RADIMCOM restarts."""
        bad = same_origin()
        if bad:
            return bad
        body = request.get_json(force=True, silent=True) or {}
        if body.get("confirm") != "RESET":
            return jsonify({"error": "not confirmed"}), 400
        with _lock:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            name = stamp_name("RADIMCOM_before_reset")
            blob = build_zip(ITEM_KEYS, body.get("browser") if isinstance(body.get("browser"), dict) else {})
            with open(os.path.join(BACKUP_DIR, name), "wb") as fh:
                fh.write(blob)
            procs.stop([v["name"] for v in state["vfos"]])
            gone = []
            for it in ITEMS:
                for f in item_files(it):
                    if f == "config.json":
                        continue                # the template of the VFO settings (from the installation) stays
                    for p in (data(f), data(f) + ".bak"):
                        if os.path.isfile(p):
                            os.remove(p)
                            gone.append(os.path.basename(p))
            print(f"FACTORY RESET: backup {name}, deleted {', '.join(gone)}; restarting")
        threading.Timer(1.5, lambda: shutdown(RESTART_CODE)).start()
        return jsonify({"ok": True, "backup": name, "deleted": gone})


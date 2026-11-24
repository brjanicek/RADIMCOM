"""Shared paths: the program in the root folder, this PC's data (settings, memories, logs, recordings) in data/.

On the first import, data from the old location (root) is moved to data/, so older installations
keep working after an update without any manual steps. config.json from the installer (template) is moved to data/ too.
"""
import os
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")

LEGACY_DIRS = ("logs", "acars", "wefax", "sstv", "eeprom_backup", "config_backup", "tx_audio")
LEGACY_FILES = ("config.json", "vfos.json", "memories.json")


def data(*parts):
    return os.path.join(DATA, *parts)


def no_source_setup():
    """No data\\vfos.json yet (a new installation, a factory reset, the SDR setup cancelled): the launcher runs as with
    one VFO A without a source (driver "none": dark, silent, no waterfall), nothing is written, so RADIMCOM.exe offers
    the SDR setup again at the next start; SETTINGS › SDR SOURCES assigns the dongles (and writes vfos.json)."""
    import json
    port = 8434
    try:
        with open(data("config.json"), encoding="utf-8") as f:
            port = int(json.load(f).get("port") or 8434)
    except (OSError, ValueError):
        pass
    return {"port": port, "vfos": [{"name": "A", "serial": "", "driver": "none", "port": port + 7,
                                    "config": "config_A.json", "note": "", "init": {}}]}


def _migrate():
    os.makedirs(DATA, exist_ok=True)
    names = list(LEGACY_FILES) + list(LEGACY_DIRS)
    names += [f for f in os.listdir(BASE) if f.startswith("config_") and f.endswith(".json")]
    for name in names:
        src, dst = os.path.join(BASE, name), data(name)
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                shutil.move(src, dst)
                print(f"moved {name} -> data/{name}")
            except OSError as e:
                print(f"could not move {name} to data/: {e}")


_migrate()

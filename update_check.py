"""After start: is a newer RADIMCOM on GitHub Releases? One request to the GitHub API in the background;
the page asks /api/update, shows the newer version beside its own and a small window with the link to the setup
of the new version. Nothing is downloaded or installed by RADIMCOM itself: the user downloads the setup and runs it,
it installs over the same folder (data\\ stays). Without internet nothing is shown.

The own version is the one in the logo of the page (static/index.html, <span class="r-ver">Ver. 0.1xx</span>),
the same that make_installer.py puts into the setup name. Off with "update_check": false (vfos.json, or config.json
of a receiver started without vfos.json).
"""
import json
import os
import re
import threading
import time
import urllib.request

from paths import BASE

LATEST_URL = "https://api.github.com/repos/om2amr/RADIMCOM/releases/latest"     # drafts and pre-releases are left out
RELEASES_URL = "https://github.com/om2amr/RADIMCOM/releases"
TIMEOUT_S = 10
START_DELAY_S = 5        # the receivers open their dongles first

_state = {"state": "off"}
_lock = threading.Lock()


def own_version():
    try:
        with open(os.path.join(BASE, "static", "index.html"), encoding="utf-8") as f:
            m = re.search(r'class="r-ver">\s*Ver\.\s*([0-9.]+(?:beta\d+)?)\s*<', f.read())
        return m.group(1) if m else None
    except OSError:
        return None


def _key(v):
    """"v0.111" / "0.111" -> (0, 111, 1, 0), "0.112beta1" -> (0, 112, 0, 1): a beta is older than its release
    and newer than the release before; None for anything else."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)(?:beta(\d+))?", (v or "").strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2))) + ((0, int(m.group(3))) if m.group(3) else (1, 0))


def kind():
    """How this folder is installed: "dev" (git), "setup" (RADIMCOM_Setup) or "zip" (0.114 and older)."""
    if os.path.exists(os.path.join(BASE, ".git")):
        return "dev"
    return "setup" if os.path.exists(os.path.join(BASE, "unins000.exe")) else "zip"


def _check():
    time.sleep(START_DELAY_S)
    cur = own_version()
    try:
        req = urllib.request.Request(LATEST_URL, headers={"User-Agent": "RADIMCOM", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            rel = json.load(r)
        tag = rel.get("tag_name", "")
        latest = tag.lstrip("v")
        newer = _key(tag) is not None and _key(cur) is not None and _key(tag) > _key(cur)
        name = f"RADIMCOM_Setup_v{latest}.exe"
        asset = next((a for a in rel.get("assets") or [] if a.get("name") == name), None)
        res = {"state": "done", "current": cur, "latest": latest, "newer": newer, "checked": time.time(),
               "name": rel.get("name") or tag, "url": rel.get("html_url") or RELEASES_URL, "published": rel.get("published_at"),
               "kind": kind(), "folder": BASE, "setup_name": asset and name,
               "setup_url": asset and asset.get("browser_download_url"), "setup_size": asset and asset.get("size")}
        print(f"Update check: version {latest} is available at {res['url']}" if newer
              else f"Update check: {cur} is the newest version")
    except Exception as e:      # offline, GitHub limit, ...: quietly nothing
        res = {"state": "failed", "current": cur, "newer": False, "error": str(e)}
        print(f"Update check: GitHub not reached ({e})")
    with _lock:
        _state.clear()
        _state.update(res)


def start(enabled=True):
    """Starts the check in the background (once per program start)."""
    with _lock:
        if _state.get("state") != "off" or not enabled:
            return
        _state.update({"state": "checking", "current": own_version(), "newer": False})
    threading.Thread(target=_check, name="update_check", daemon=True).start()


def info():
    with _lock:
        return dict(_state)

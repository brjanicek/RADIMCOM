"""Logs and data files of RADIMCOM: where they are, the day folders of the logs, and the file tree of SETTINGS › LOGS.

Logs (UTC, shared by all VFOs; each line carries its VFO):
    data/logs/<source>/YYYY/MM/DD/<source>_YYYY-MM-DD.<ext>
      sources of daylog.py (ft8, cw, rtty, wefax, sstv, dsd, ism, packet, pocsag, hfdl, ais, adsb), acars and vdl2
      (acars.py), scan (.csv, scanner.py: the activities) and radiosonde (one <YYYY-MM-DD>_<serial>.jsonl per flight,
      sonde.py: every frame, also the history of the sonde map).
Older versions wrote them flat (data/logs/<source>_YYYY-MM-DD.txt, data/acars/…, data/logs/radiosonde/*.jsonl):
migrate() moves them once.

ROOTS are the folders the LOGS page may browse, read, download, delete in and upload to; nothing outside them.
"""
import os
import re
import time

from paths import data

LOG_ROOT = data("logs")
# folders of SETTINGS › LOGS › FILES: key → (folder, what it is)
ROOTS = {
    "logs": (LOG_ROOT, "Logs of the decoders, the scan and the radiosondes (YYYY/MM/DD, UTC)"),
    "wefax": (data("wefax"), "WEFAX images"),
    "sstv": (data("sstv"), "SSTV images"),
    "dab": (data("dab_history"), "DAB: songs played per station"),
    "server": (data("server_logs"), "Logs of the server (each start of RADIMCOM)"),
    "wind": (data("wind"), "GFS wind cache of the sonde predictions (Open-Meteo)"),
    "sonde_iq": (data("sonde_iq"), "IQ recordings of the sonde channel"),
}
TEXT_EXT = (".txt", ".csv", ".jsonl", ".json", ".log")
VIEW_EXT = TEXT_EXT + (".png", ".jpg", ".jpeg")
VIEW_MAX = 1 << 20          # a text file is shown up to its last 1 MB
FLAT_RE = re.compile(r"^(?P<src>[a-z0-9]+)_(?P<d>\d{4}-\d\d-\d\d)\.(?P<ext>txt|csv)$")
SONDE_RE = re.compile(r"^(?P<d>\d{4}-\d\d-\d\d)_[\w.-]+\.jsonl$")


def day_dir(source, t=None, root=None):
    """The folder of one day of a log (UTC): <logs>/<source>/YYYY/MM/DD."""
    return date_dir(source, time.strftime("%Y-%m-%d", time.gmtime(t)), root)


def date_dir(source, date, root=None):
    """The same from a date "YYYY-MM-DD"."""
    y, m, d = date.split("-")
    return os.path.join(root or LOG_ROOT, source, y, m, d)


def day_file(source, t=None, ext="txt", root=None):
    """<logs>/<source>/YYYY/MM/DD/<source>_YYYY-MM-DD.<ext> (the folder is not created)."""
    date = time.strftime("%Y-%m-%d", time.gmtime(t))
    return os.path.join(date_dir(source, date, root), f"{source}_{date}.{ext}")


def walk_files(folder, pattern=None):
    """All files below folder (paths), optionally only names matching a regex."""
    out = []
    for top, _, names in os.walk(folder):
        for n in names:
            if pattern is None or pattern.match(n):
                out.append(os.path.join(top, n))
    return out


def prune_empty(folder, root):
    """Removes folder and its parents up to root (not root itself) while they are empty."""
    root = os.path.normcase(os.path.abspath(root))
    folder = os.path.abspath(folder)
    while os.path.normcase(folder).startswith(root + os.sep):
        try:
            os.rmdir(folder)
        except OSError:
            return
        folder = os.path.dirname(folder)


def prune_days(source, keep_days, now=None, root=None):
    """Deletes the day folders of a log older than keep_days (the date in the path, UTC). Returns files deleted."""
    now = now or time.time()
    keep = time.strftime("%Y-%m-%d", time.gmtime(now - (int(keep_days) - 1) * 86400))
    base = os.path.join(root or LOG_ROOT, source)
    gone = 0
    for top, dirs, names in os.walk(base, topdown=False):
        rel = os.path.relpath(top, base).replace(os.sep, "/").split("/")
        if len(rel) == 3 and "-".join(rel) < keep:
            for n in names:
                try:
                    os.remove(os.path.join(top, n))
                    gone += 1
                except OSError:
                    pass
            prune_empty(top, base)
    return gone


# ---------- the move of the flat logs of older versions (once) ----------

def migrate(root=None, acars_dir=None):
    """Flat logs → day folders: <logs>/<src>_DATE.txt|csv, <acars>/(acars|vdl2)_DATE.txt and
    <logs>/radiosonde/DATE_serial.jsonl. More VFO servers start at once: a lock file lets one do it.
    Returns the number of files moved."""
    root = root or LOG_ROOT
    acars_dir = acars_dir or data("acars")
    lock = os.path.join(root, ".migrate.lock")
    try:
        os.makedirs(root, exist_ok=True)
        if os.path.exists(lock):
            if time.time() - os.path.getmtime(lock) < 600:
                return 0
            os.remove(lock)
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except OSError:
        return 0
    moved = 0

    def move(src, dst_dir):
        nonlocal moved
        try:
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, os.path.basename(src))
            if os.path.exists(dst):           # both written meanwhile (should not happen): keep both
                with open(src, "rb") as a, open(dst, "ab") as b:
                    b.write(a.read())
                os.remove(src)
            else:
                os.replace(src, dst)
            moved += 1
        except OSError as e:
            print(f"logs: {src} not moved: {e}", flush=True)

    try:
        for folder in (root, acars_dir):
            try:
                names = os.listdir(folder)
            except OSError:
                continue
            for n in names:
                m = FLAT_RE.match(n)
                if m and os.path.isfile(os.path.join(folder, n)):
                    move(os.path.join(folder, n), date_dir(m.group("src"), m.group("d"), root))
        rs = os.path.join(root, "radiosonde")
        try:
            names = os.listdir(rs)
        except OSError:
            names = []
        for n in names:
            m = SONDE_RE.match(n)
            if m and os.path.isfile(os.path.join(rs, n)):
                move(os.path.join(rs, n), date_dir("radiosonde", m.group("d"), root))
        try:
            os.rmdir(acars_dir)                  # empty now: the logs of ACARS / VDL2 are in data/logs
        except OSError:
            pass
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass
    if moved:
        print(f"logs: {moved} files moved into the YYYY/MM/DD folders", flush=True)
    return moved


# ---------- the file tree of SETTINGS › LOGS › FILES ----------

def resolve(key, rel=""):
    """(root folder, absolute path) of a path inside one of ROOTS; ValueError otherwise."""
    if key not in ROOTS:
        raise ValueError("unknown folder")
    root = os.path.abspath(ROOTS[key][0])
    parts = [p for p in str(rel or "").replace("\\", "/").split("/") if p not in ("", ".")]
    if any(p == ".." or ":" in p for p in parts):
        raise ValueError("bad path")
    path = os.path.abspath(os.path.join(root, *parts))
    if os.path.normcase(path) != os.path.normcase(root) and \
            not os.path.normcase(path).startswith(os.path.normcase(root) + os.sep):
        raise ValueError("bad path")
    return root, path


def _tree_stats(folder):
    """(files, bytes, newest mtime) of a folder and all below (scandir: the sizes come with the listing on Windows)."""
    n = size = newest = 0
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return 0, 0, 0
    for e in entries:
        try:
            if e.is_dir():
                a, b, c = _tree_stats(e.path)
                n, size, newest = n + a, size + b, max(newest, c)
            elif not e.name.startswith("."):
                st = e.stat()
                n, size, newest = n + 1, size + st.st_size, max(newest, int(st.st_mtime))
        except OSError:
            continue
    return n, size, newest


def roots():
    """The folders of the LOGS page with their size."""
    out = []
    for key, (folder, what) in ROOTS.items():
        n, size, newest = _tree_stats(folder)
        out.append({"key": key, "name": key, "what": what, "folder": os.path.abspath(folder), "files": n,
                    "size": size, "mtime": newest})
    return out


def list_dir(key, rel=""):
    """One folder: its subfolders (files and size of all below) and its files."""
    root, folder = resolve(key, rel)
    relp = lambda p: os.path.relpath(p, root).replace(os.sep, "/")   # noqa: E731
    dirs, files = [], []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        entries = []
    for e in entries:
        if e.name.startswith("."):
            continue
        try:
            if e.is_dir():
                n, size, newest = _tree_stats(e.path)
                dirs.append({"name": e.name, "path": relp(e.path), "files": n, "size": size, "mtime": newest})
            else:
                st = e.stat()
                files.append({"name": e.name, "path": relp(e.path), "size": st.st_size, "mtime": int(st.st_mtime),
                              "view": e.name.lower().endswith(VIEW_EXT)})
        except OSError:
            continue
    dirs.sort(key=lambda d: d["name"], reverse=True)
    files.sort(key=lambda f: f["name"])
    here = relp(folder)
    return {"key": key, "dir": "" if here == "." else here, "folder": folder, "dirs": dirs, "files": files}


def delete_paths(key, rels):
    """Deletes files and whole folders (with all inside) of one root; emptied parents go too.
    {"deleted": n, "kept": [why…]}; ValueError for a bad path or the root itself."""
    root = None
    paths = []
    for r in rels:
        root, p = resolve(key, r)
        if os.path.normcase(p) == os.path.normcase(root):
            raise ValueError("the whole folder cannot be deleted at once: open it and tick what to delete")
        paths.append(p)
    deleted, kept, parents = 0, [], set()

    def rm(path):
        nonlocal deleted
        try:
            os.remove(path)
            deleted += 1
        except OSError as e:
            kept.append(f"{os.path.basename(path)}: {e.strerror or e}")   # e.g. the log the server writes now

    for p in paths:
        if os.path.isdir(p):
            for top, _, names in os.walk(p, topdown=False):
                for n in names:
                    rm(os.path.join(top, n))
                try:
                    os.rmdir(top)
                except OSError:
                    pass
        elif os.path.isfile(p):
            rm(p)
        else:
            kept.append(f"{os.path.basename(p)}: not found")
        parents.add(os.path.dirname(p))
    for d in parents:
        prune_empty(d, root)
    return {"deleted": deleted, "kept": kept}


def read_text(key, rel, tail=VIEW_MAX):
    """The end of a text file for the viewer: {"text", "size", "cut"} (cut = only its last `tail` bytes)."""
    _, path = resolve(key, rel)
    if not path.lower().endswith(TEXT_EXT) or not os.path.isfile(path):
        raise ValueError("not a text file")
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > tail:
            f.seek(size - tail)
        raw = f.read()
    text = raw.decode("utf-8", "replace")
    if size > tail:
        text = text.split("\n", 1)[-1]        # from a whole line
    return {"text": text, "size": size, "cut": size > tail}


def save_upload(key, rel, name, stream):
    """An uploaded file into a folder of a root (import: logs of another PC, a sonde flight …); not over a file."""
    name = os.path.basename(str(name or "").replace("\\", "/"))
    if not name or name.startswith(".") or not re.fullmatch(r"[\w .()+,-]+", name):
        raise ValueError("bad file name")
    _, folder = resolve(key, rel)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    if os.path.exists(path):
        raise ValueError(f"{name} is already there")
    with open(path, "xb") as f:
        while True:
            chunk = stream.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return {"saved": name}

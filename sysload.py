"""CPU load and memory use for the small indicator under the S-meter: RADIMCOM's own processes (the server, the
window with the page) as Task Manager counts them, and the whole PC.

Windows: GetSystemTimes / GlobalMemoryStatusEx (ctypes, no psutil). Linux: /proc/stat and /proc/meminfo.
CPU load is measured between two calls (the page asks every few seconds); the first call samples 0.2 s.
"""

import collections
import os
import sys
import threading
import time

_lock = threading.Lock()
_plock = threading.Lock()
_prev = None        # (idle, total) of the last call
_prev_at = 0.0
_last_cpu = None    # returned again when two calls come too close (several pages open)


def _cpu_times():
    """-> (idle, total) ticks since boot, or None."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        val = lambda ft: (ft.dwHighDateTime << 32) | ft.dwLowDateTime
        return val(idle), val(kernel) + val(user)     # kernel time includes idle
    try:
        with open("/proc/stat") as f:
            v = [int(x) for x in f.readline().split()[1:]]
        return v[3] + v[4], sum(v)                     # idle + iowait
    except (OSError, ValueError, IndexError):
        return None


def _memory():
    """-> (used %, used bytes, total bytes), or None."""
    if sys.platform == "win32":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        m = MEMORYSTATUSEX()
        m.dwLength = ctypes.sizeof(m)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return None
        used = m.ullTotalPhys - m.ullAvailPhys
        return 100.0 * used / m.ullTotalPhys, used, m.ullTotalPhys
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = int(v.split()[0]) * 1024
        total, avail = info["MemTotal"], info.get("MemAvailable", info.get("MemFree", 0))
        return 100.0 * (total - avail) / total, total - avail, total
    except (OSError, ValueError, KeyError, ZeroDivisionError):
        return None


def load(labels=None):
    """-> {"cpu": %, "mem": %, "mem_used": bytes, "mem_total": bytes} of the whole PC and "procs" = RADIMCOM's own
    processes (processes(): the server and the window); None for what cannot be read."""
    global _prev, _prev_at, _last_cpu
    with _lock:
        now = _cpu_times()
        if now and _prev is None:
            _prev, _prev_at = now, time.monotonic() - 0.5
            time.sleep(0.2)
            now = _cpu_times()
        cpu = _last_cpu
        if now and _prev:
            d_idle, d_total = now[0] - _prev[0], now[1] - _prev[1]
            if d_total > 0 and time.monotonic() - _prev_at >= 0.5:
                cpu = _last_cpu = max(0.0, min(100.0, 100.0 * (1 - d_idle / d_total)))
                _prev = now
                _prev_at = time.monotonic()
    mem = _memory()
    try:
        with _plock:
            procs = processes(labels)
    except (OSError, ValueError, KeyError, IndexError) as e:   # never breaks the indicator of the PC
        print(f"sysload: processes: {e}", flush=True)
        procs = None
    return {"procs": procs, "cpu": None if cpu is None else round(cpu, 1),
            "mem": None if mem is None else round(mem[0], 1),
            "mem_used": mem[1] if mem else None,
            "mem_total": mem[2] if mem else None}


# ---------- RADIMCOM's own processes (Windows): the server and the window (WebView2) ----------
# One NtQuerySystemInformation(SystemProcessInformation) call gives every process with its parent, CPU time and
# private working set – the same numbers Task Manager shows (Memory = private working set; CPU = share of the whole
# PC, all cores = 100 %, as in its Details tab). The tree: RADIMCOM.exe (the window) → msedgewebview2.exe (the page:
# CLIENT) and python launcher → one python per VFO → its helper programs (welle-cli, dumphfdl …: SERVER).
SHELL_EXE = "radimcom.exe"
WEBVIEW_EXE = "msedgewebview2.exe"
PY_EXE = ("python.exe", "pythonw.exe", "python3.exe")
_pprev = {}          # pid -> CPU time (100 ns) at the last call
_pprev_at = 0.0
_pplast = None       # the last result (returned to calls that come less than 1 s after it)


def _snapshot():
    """{pid: (name, parent pid, private working set bytes, CPU time 100 ns)}, or None."""
    if sys.platform != "win32":
        return None
    import ctypes
    import struct
    ntdll = ctypes.windll.ntdll
    size = ctypes.c_ulong(1 << 20)
    for _ in range(8):
        buf = ctypes.create_string_buffer(size.value)
        ret = ntdll.NtQuerySystemInformation(5, buf, size, ctypes.byref(size)) & 0xFFFFFFFF
        if ret == 0:
            break
        if ret != 0xC0000004:                       # STATUS_INFO_LENGTH_MISMATCH: a bigger buffer
            return None
        size = ctypes.c_ulong(size.value + 65536)
    else:
        return None
    raw, out, off = buf.raw, {}, 0
    base = ctypes.addressof(buf)
    while True:
        nxt, = struct.unpack_from("<I", raw, off)
        wsp, = struct.unpack_from("<q", raw, off + 8)
        ut, kt = struct.unpack_from("<qq", raw, off + 40)
        ln, = struct.unpack_from("<H", raw, off + 56)
        ptr, = struct.unpack_from("<Q", raw, off + 64)
        pid, ppid = struct.unpack_from("<QQ", raw, off + 80)
        name = ""
        if ptr and base <= ptr < base + len(raw):  # the name lies in the same buffer
            name = raw[ptr - base:ptr - base + ln].decode("utf-16-le", "replace")
        out[pid] = (name, ppid, max(wsp, 0), ut + kt)
        if not nxt:
            return out
        off += nxt


def _is_py(name):
    n = name.lower()
    return n in PY_EXE or (n.startswith("python3") and n.endswith(".exe"))


def processes(labels=None):
    """CPU and memory of RADIMCOM itself: {"server": {...}, "client": {...} | None}; None where it cannot be read.
    labels: {pid of a VFO server process: "A"} (the launcher knows them) for the parts of the server."""
    global _pprev, _pprev_at, _pplast
    snap = _snapshot()
    if not snap:
        return None
    kids = {}
    for pid, (_, ppid, _, _) in snap.items():
        if ppid != pid:
            kids.setdefault(ppid, []).append(pid)
    # the root: RADIMCOM.exe above this process, else the topmost python above it (started without the window)
    root, pid, seen = os.getpid(), os.getpid(), set()
    while pid in snap and pid not in seen:
        seen.add(pid)
        name, ppid = snap[pid][0].lower(), snap[pid][1]
        if name == SHELL_EXE:
            root = pid
            break
        if _is_py(name):
            root = pid
        pid = ppid

    def tree(p):
        out, stack = [], [p]
        while stack:
            q = stack.pop()
            if q in snap:
                out.append(q)
                stack.extend(kids.get(q, []))
        return out

    allp = tree(root)
    client = set()
    for p in allp:
        if snap[p][0].lower() == WEBVIEW_EXE:      # the page in the window (WebView2) with all its processes
            client.update(tree(p))
    if snap[root][0].lower() == SHELL_EXE:
        client.add(root)
    server = [p for p in allp if p not in client]
    now = time.monotonic()
    times = {p: snap[p][3] for p in allp}
    if _pplast is not None and now - _pprev_at < 1.0:
        return _pplast                              # several pages ask at once: the last measurement
    prev, dt = _pprev, now - _pprev_at
    if not prev:                                    # the first call: measure over a short time
        _pprev, _pprev_at = times, now
        time.sleep(0.4)
        return processes(labels) if _snapshot() else None
    ncpu = os.cpu_count() or 1

    def cpu(ps):
        busy = sum(max(times[p] - prev.get(p, times[p]), 0) for p in ps)
        return round(min(100.0, busy / 1e7 / dt / ncpu * 100), 1)

    def mem(ps):
        return sum(snap[p][2] for p in ps)

    def group(ps):
        names = collections.Counter(snap[p][0] for p in ps)
        return {"cpu": cpu(ps), "mem": mem(ps), "n": len(ps),
                "procs": [f"{n} ×{c}" if c > 1 else n for n, c in names.most_common()]}

    parts, rest = [], set(server)
    for pid, label in sorted((labels or {}).items(), key=lambda x: x[1]):
        ps = [p for p in tree(pid) if p in rest]
        if ps:
            rest.difference_update(ps)
            parts.append(dict(group(ps), name=f"VFO {label}"))
    if parts and rest:
        parts.insert(0, dict(group(list(rest)), name="launcher"))
    out = {"server": dict(group(server), parts=parts),
           "client": dict(group(list(client)), parts=[]) if client else None, "cpus": ncpu}
    _pprev, _pprev_at, _pplast = times, now, out
    return out

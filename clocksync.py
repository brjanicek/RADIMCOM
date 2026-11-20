"""PC clock check and sync for the time-slotted decoders (FT8 15 s, WSPR 2 min: the PC clock must be right to ±1 s).

offset() asks an NTP server (SNTP, UDP 123; nothing of the station goes out) how far the PC clock is off.
sync() corrects it by that offset: directly when RADIMCOM runs as administrator, otherwise through an elevated
PowerShell "Set-Date -Adjust" (Windows asks for the administrator consent once - UAC).
"""
import ctypes
import socket
import struct
import sys
import threading
import time

SERVERS = ("pool.ntp.org", "time.windows.com", "time.google.com")
NTP_EPOCH = 2208988800          # 1900-01-01 -> 1970-01-01
CACHE_S = 600

_lock = threading.Lock()
_last = {"t": 0.0, "res": None}


def _query(host, timeout=2.0):
    """One SNTP request: (offset s = NTP time - PC time, round trip s)."""
    pkt = bytearray(48)
    pkt[0] = 0x23                                   # LI 0, version 4, mode 3 (client)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        t1 = time.time()
        s.sendto(bytes(pkt), (host, 123))
        data, _ = s.recvfrom(512)
        t4 = time.time()
    if len(data) < 48:
        raise ValueError("short NTP answer")
    def ts(off):
        sec, frac = struct.unpack("!II", data[off:off + 8])
        return sec - NTP_EPOCH + frac / 2 ** 32
    t2, t3 = ts(32), ts(40)                         # server receive / transmit time
    if t3 <= 0:
        raise ValueError("NTP server not synchronised")
    return ((t2 - t1) + (t3 - t4)) / 2, (t4 - t1) - (t3 - t2)


def offset(force=False):
    """{"offset": s, "rtt": s, "server": host, "t": epoch} or {"error": text}; cached for CACHE_S."""
    with _lock:
        if not force and _last["res"] and time.time() - _last["t"] < CACHE_S:
            return _last["res"]
    errors = []
    res = None
    for host in SERVERS:
        try:
            best = min((_query(host) for _ in range(3)), key=lambda x: x[1])   # the shortest round trip is the most exact
            res = {"offset": round(best[0], 3), "rtt": round(best[1], 3), "server": host, "t": time.time()}
            break
        except (OSError, ValueError) as e:
            errors.append(f"{host}: {e}")
    if res is None:
        res = {"error": "no NTP server answers (" + "; ".join(errors)[:200] + ")", "t": time.time()}
    with _lock:
        _last.update(t=time.time(), res=res)
    return res


class _SYSTEMTIME(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint16) for n in ("wYear", "wMonth", "wDayOfWeek", "wDay", "wHour", "wMinute", "wSecond", "wMilliseconds")]


def _set_direct(off):
    """Sets the clock in this process (works only when it runs as administrator)."""
    t = time.time() + off
    g = time.gmtime(t)
    st = _SYSTEMTIME(g.tm_year, g.tm_mon, (g.tm_wday + 1) % 7, g.tm_mday, g.tm_hour, g.tm_min, g.tm_sec, int((t % 1) * 1000))
    return bool(ctypes.windll.kernel32.SetSystemTime(ctypes.byref(st)))


def sync():
    """Corrects the PC clock by the measured offset. {"ok": bool, "before": s, "how": text, ...}."""
    if sys.platform != "win32":
        return {"ok": False, "error": "only on Windows; use the NTP service of the system"}
    m = offset(force=True)
    if "error" in m:
        return {"ok": False, "error": m["error"]}
    off = m["offset"]
    if abs(off) < 0.05:
        return {"ok": True, "before": off, "how": "the clock was already right (within 50 ms)"}
    if _set_direct(off):
        how = "set directly"
    else:
        # not an administrator: an elevated PowerShell adjusts the clock by the offset (UAC asks for consent)
        ms = int(round(off * 1000))
        args = f"-NoProfile -WindowStyle Hidden -Command Set-Date -Adjust ([TimeSpan]::FromMilliseconds({ms})) | Out-Null"
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", args, None, 0)
        if r <= 32:
            return {"ok": False, "before": off, "error": "Windows refused to change the clock (the administrator consent was not given)"}
        how = "set by an elevated PowerShell (administrator consent)"
        time.sleep(3)
    after = offset(force=True)
    return {"ok": "error" not in after and abs(after.get("offset", 9)) < 0.5, "before": off, "after": after.get("offset"),
            "how": how, "error": after.get("error")}

"""SETTINGS › DEBUG: where this server process (one VFO) spends its CPU.

GET /api/debug/threads -> {"t": seconds (monotonic), "proc": CPU seconds of the whole process,
                           "threads": [{"id", "name", "cpu"}],   (CPU seconds of each Python thread)
                           "samples": {thread id: [[place, count], ...]}, "sampled": number of sampling rounds}
  ?sample=1   keeps the sampler running (it stops by itself 30 s after the last such request)
  ?reset=1    clears the sample counts

The sampler looks at the stack of every thread 50 times a second and counts the innermost line of our own code
(file:line function): where a busy thread works, or where an idle one waits. Read it together with the CPU of the
thread. The page computes the CPU shares from two answers.
"""

import collections
import os
import sys
import threading
import time

SAMPLE_HZ = 50
SAMPLE_KEEP_S = 30          # the sampler runs this long after the last request with ?sample=1
TOP = 6                     # places per thread in the answer

_HERE = os.path.dirname(os.path.abspath(__file__))
_lock = threading.Lock()
_samples = collections.defaultdict(collections.Counter)   # thread id -> Counter(place)
_rounds = 0
_until = 0.0
_sampler = None


def _thread_cpu_win():
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenThread.restype = wintypes.HANDLE
    k.OpenThread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k.GetThreadTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    k.CloseHandle.argtypes = (wintypes.HANDLE,)
    val = lambda ft: (ft.dwHighDateTime << 32) | ft.dwLowDateTime

    def cpu(tid):
        h = k.OpenThread(0x0800, False, tid)          # THREAD_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            ft = [wintypes.FILETIME() for _ in range(4)]
            if not k.GetThreadTimes(h, *(ctypes.byref(x) for x in ft)):
                return None
            return (val(ft[2]) + val(ft[3])) / 1e7    # kernel + user, 100 ns units
        finally:
            k.CloseHandle(h)
    return cpu


def _thread_cpu_linux(tid):
    try:
        with open(f"/proc/self/task/{tid}/stat") as f:
            p = f.read().rsplit(")", 1)[1].split()
        return (int(p[11]) + int(p[12])) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return None


_thread_cpu = _thread_cpu_win() if sys.platform == "win32" else _thread_cpu_linux


def _place(frame):
    """The innermost frame of our own code (not the standard library or numpy): 'file.py:line function'."""
    f = frame
    while f is not None:
        fn = f.f_code.co_filename
        if fn.startswith(_HERE) and "site-packages" not in fn:
            return f"{os.path.basename(fn)}:{f.f_lineno} {f.f_code.co_name}"
        f = f.f_back
    return f"{os.path.basename(frame.f_code.co_filename)}:{frame.f_lineno} {frame.f_code.co_name}"


def _sample_loop():
    global _rounds, _sampler
    me = threading.get_ident()
    while time.monotonic() < _until:
        frames = sys._current_frames()
        with _lock:
            for ident, frame in frames.items():
                if ident != me:
                    _samples[ident][_place(frame)] += 1
            _rounds += 1
        del frames
        time.sleep(1 / SAMPLE_HZ)
    with _lock:
        _sampler = None


def threads(sample=False, reset=False):
    global _until, _sampler, _rounds
    with _lock:
        if reset:
            _samples.clear()
            _rounds = 0
        if sample:
            _until = time.monotonic() + SAMPLE_KEEP_S
            if _sampler is None:
                _sampler = threading.Thread(target=_sample_loop, name="dbgstats sampler", daemon=True)
                _sampler.start()
        by_ident = {t.ident: t for t in threading.enumerate()}
        out = []
        for ident, t in by_ident.items():
            tid = getattr(t, "native_id", None)
            out.append({"id": ident, "name": t.name, "cpu": _thread_cpu(tid) if tid else None})
        samples = {str(i): c.most_common(TOP) for i, c in _samples.items() if i in by_ident}
        rounds = _rounds
    pt = os.times()
    return {"t": time.monotonic(), "proc": pt.user + pt.system, "threads": out, "samples": samples, "sampled": rounds,
            "pid": os.getpid()}


def register(app):
    from flask import jsonify, request

    @app.route("/api/debug/threads")
    def api_debug_threads():
        return jsonify(threads(sample=request.args.get("sample") == "1", reset=request.args.get("reset") == "1"))

"""Server log: what the launcher and the VFO processes print (messages, errors with tracebacks, output of the SDR
libraries and of the helper programs) goes to data/server_logs/logs_DDMMYYYY_HHMMSS.log (date and time of the start)
instead of the console window. One file per start, shared by all VFO processes.

Every line starts with the time (DD.MM.YYYY HH:MM:SS.mmm) and, for a VFO process, its letter: [A]. The launcher reads
the output of each process through its own pipe, so lines are whole even when the processes write at the same time
(the C libraries write in pieces, e.g. librtlsdr "Found Rafael Mic" + "ro R828D tuner").

The web server's lines for successful requests (200, 304 – the page polls several times a second) are left out;
requests that failed (4xx, 5xx) and all errors stay.
"""
import atexit
import datetime
import logging
import os
import subprocess
import sys
import threading
import time

from paths import data

LOG_DIR = data("server_logs")
ENV = "RADIMCOM_SERVER_LOG"     # set for the VFO processes: the path of the shared log

_file = None
_lock = threading.Lock()
_pumps = []                     # threads reading the pipes (this process and each VFO process)


class _FailedRequestsOnly(logging.Filter):
    """Werkzeug request lines have the HTTP status as the 2nd argument: only 4xx / 5xx pass."""

    def filter(self, record):
        a = record.args
        if isinstance(a, tuple) and len(a) >= 2:
            try:
                return int(str(a[1])) >= 400
            except ValueError:
                return True
        return True


def _quiet_requests():
    logging.getLogger("werkzeug").addFilter(_FailedRequestsOnly())


def _write(raw, tag):
    """One line into the log with the time and the source."""
    text = raw.decode("utf-8", errors="replace").rstrip("\r")
    stamp = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S.%f")[:-3]
    with _lock:
        _file.write(f"{stamp} [{tag}] {text}\n" if tag else f"{stamp} {text}\n")
        _file.flush()


def _pump(rfd, tag):
    """Reads a pipe until all its writers close it; a line is written once it is complete."""
    buf = b""
    try:
        while True:
            chunk = os.read(rfd, 65536)
            if not chunk:
                break
            buf += chunk
            *lines, buf = buf.split(b"\n")
            for ln in lines:
                _write(ln, tag)
    except OSError:
        pass
    finally:
        if buf:
            _write(buf, tag)
        os.close(rfd)


def _pipe(tag):
    """A new pipe whose lines go into the log; returns its write end."""
    r, w = os.pipe()
    t = threading.Thread(target=_pump, args=(r, tag), name=f"serverlog-{tag or 'main'}", daemon=True)
    t.start()
    _pumps.append(t)
    return w


def start():
    """The launcher (or a standalone receiver): open a new log and send this process's output there.
    Returns the path of the log."""
    global _file
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, time.strftime("logs_%d%m%Y_%H%M%S.log"))
    print(f"RADIMCOM: the server log is in {path}", flush=True)
    sys.stderr.flush()
    _file = open(path, "a", encoding="utf-8", errors="replace")
    w = _pipe(None)
    # also the output of C libraries (e.g. librtlsdr "Found Rafael Micro R828D tuner") of this process
    for fd in (1, 2):
        try:
            os.dup2(w, fd)
        except OSError:
            pass
    out = open(w, "w", encoding="utf-8", errors="replace", buffering=1)
    sys.stdout = sys.stderr = out
    os.environ[ENV] = path
    atexit.register(close)
    print("RADIMCOM server log started")
    _quiet_requests()
    return path


def spawn(args, tag, **kw):
    """subprocess.Popen of a VFO process: its output (and that of its helper programs) goes into the log
    through its own pipe, each line marked [tag]."""
    if _file is None:
        return subprocess.Popen(args, **kw)
    w = _pipe(tag)
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8:replace")
    try:
        return subprocess.Popen(args, stdout=w, stderr=subprocess.STDOUT, env=env, **kw)
    finally:
        os.close(w)                 # the child has its copy; the pipe ends when the child ends


def close(timeout=2.0):
    """Before the process ends (also before os._exit): the last lines into the log."""
    if _file is None:
        return
    try:
        sys.stdout.flush()
    except (OSError, ValueError):
        pass
    for fd in (1, 2):
        try:
            os.close(fd)
        except OSError:
            pass
    try:
        sys.stdout.close()          # the last write end of this process's pipe
    except (OSError, ValueError):
        pass
    end = time.monotonic() + timeout
    for t in _pumps:
        t.join(max(0.0, end - time.monotonic()))


def attach():
    """A VFO process started by the launcher: its output already goes to the log; only the request lines are thinned."""
    if os.environ.get(ENV):
        _quiet_requests()

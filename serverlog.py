"""Server log: what the launcher and the VFO processes print (messages, errors with tracebacks, output of the SDR
libraries and of the helper programs) goes to data/server_logs/logs_DDMMYYYY_HHMMSS.log (date and time of the start)
instead of the console window. One file per start, shared by all VFO processes.

The web server's lines for successful requests (200, 304 – the page polls several times a second) are left out;
requests that failed (4xx, 5xx) and all errors stay.
"""
import logging
import os
import subprocess
import sys
import time

from paths import data

LOG_DIR = data("server_logs")
ENV = "RADIMCOM_SERVER_LOG"     # set for the VFO processes: the path of the shared log

_file = None


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


def start():
    """The launcher (or a standalone receiver): open a new log and send this process's output there.
    Returns the path of the log."""
    global _file
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, time.strftime("logs_%d%m%Y_%H%M%S.log"))
    print(f"RADIMCOM: the server log is in {path}", flush=True)
    sys.stderr.flush()
    _file = open(path, "a", encoding="utf-8", errors="replace", buffering=1)
    # also the output of C libraries (e.g. librtlsdr "Found Rafael Micro R828D tuner") of this process
    for fd in (1, 2):
        try:
            os.dup2(_file.fileno(), fd)
        except OSError:
            pass
    sys.stdout = sys.stderr = _file
    os.environ[ENV] = path
    print(f"RADIMCOM server log started {time.strftime('%d.%m.%Y %H:%M:%S')}")
    _quiet_requests()
    return path


def child_kwargs():
    """subprocess.Popen arguments for a VFO process: it writes into the same log (unbuffered, UTF-8)."""
    if _file is None:
        return {}
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8:replace")
    return {"stdout": _file, "stderr": subprocess.STDOUT, "env": env}


def attach():
    """A VFO process started by the launcher: its output already goes to the log; only the request lines are thinned."""
    if os.environ.get(ENV):
        _quiet_requests()

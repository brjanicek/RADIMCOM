"""SondeHub uploader: the decoded radiosonde frames go to the SondeHub tracker (https://sondehub.org), like
radiosonde_auto_rx does. One switch (SONDE › SONDEHUB) per VFO, config key "sondehub".

Only frames that SondeHub can use and trust are sent, with a good GPS position (sonde.pos_filter) and the time of the
frame: Vaisala RS41, Graw DFM (only once its serial has come in the configuration blocks), Meteomodem M10 / M20 (serial
as on the label, rs1729's get_SN); not the encrypted RS41-SGM. The per-type rules (serial without the type prefix,
DFM subtype, the frame number of DFM / M10 / M20 = the time of the frame) follow radiosonde_auto_rx's sondehub.py
and the SondeHub telemetry format (https://github.com/projecthorus/sondehub-infra/wiki). The frames are collected and sent every UPLOAD_SEC as one gzipped JSON list
(PUT /sondes/telemetry); the station (callsign, location of SETTINGS › GENERAL › LOCATION) goes to /listeners once
on start and then every LISTENER_SEC, so it is shown on the map as a receiver.
"""
import email.utils
import gzip
import json
import os
import threading
import time
import urllib.error
import urllib.request

TELEMETRY_URL = "https://api.v2.sondehub.org/sondes/telemetry"
LISTENER_URL = "https://api.v2.sondehub.org/listeners"
UPLOAD_SEC = 15.0            # frames collected this long are sent together (auto_rx: 15-30 s)
UPLOAD_SEC_DFM = 30.0        # with DFM frames: SondeHub's check of DFM altitudes needs 30 s
BLOCKED_SEC = 600.0          # SondeHub does not take this software yet: tried again this often
LISTENER_SEC = 6 * 3600.0    # the station position again after this long
QUEUE_MAX = 2000             # frames kept when SondeHub cannot be reached (the oldest dropped)
TIMEOUT_S = 20.0
RETRY_SEC = 60.0             # after a failed upload
SOFTWARE = "RADIMCOM"
MANUFACTURER = {"RS41": "Vaisala", "DFM": "Graw", "M20": "Meteomodem"}
UPLOAD_TYPES = ("RS41", "DFM", "M10", "M20")
DFM_SONDEHUB = {"PS15": ("PS-15", "PS-15")}             # DFM subtypes SondeHub files under another type
DFM_SUBTYPES = ("DFM06", "DFM09", "DFM09P", "DFM17")   # the subtypes SondeHub knows


def iso(t):
    """Unix time -> ISO 8601 UTC with milliseconds, as SondeHub wants it."""
    ms = int(round(t * 1000))
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ms // 1000)) + f".{ms % 1000:03d}Z"


def telemetry(d, callsign, position=None, version=""):
    """A decoded frame -> one SondeHub telemetry object, or None when it is not to be sent."""
    if d.get("type") not in UPLOAD_TYPES or not d.get("serial") or d.get("encrypted"):
        return None
    if d.get("lat") is None or d.get("alt") is None or d.get("gps_time") is None:
        return None
    typ, serial, frame = d["type"], d["serial"], d.get("frame")
    if typ != "RS41":
        serial = serial[4:]                  # DFM-, M10-, M20- off
        frame = int(d["gps_time"])           # SondeHub: for DFM / M10 / M20 the time of the frame
        if (typ == "DFM" and "." in serial) or d.get("serial_raw"):
            return None                      # the serial is not known yet (DFM-<frequency>) or not given (M20 0)
    if frame is None:
        return None
    t = {
        "software_name": SOFTWARE, "software_version": version, "uploader_callsign": callsign,
        "time_received": iso(d.get("time") or time.time()),
        "manufacturer": MANUFACTURER[typ], "type": typ, "serial": serial, "frame": int(frame),
        "datetime": iso(d["gps_time"]), "lat": d["lat"], "lon": d["lon"], "alt": d["alt"],
    }
    if typ == "RS41" and d.get("subtype"):
        t["subtype"] = d["subtype"]
    elif typ == "DFM" and d.get("subtype") in DFM_SONDEHUB:
        t["type"], t["subtype"] = DFM_SONDEHUB[d["subtype"]]
    elif typ == "DFM" and d.get("subtype") in DFM_SUBTYPES:
        t["subtype"] = d["subtype"]
    elif typ in ("M10", "M20"):
        t["subtype"] = typ
    for src, dst in (("vv", "vel_v"), ("vh", "vel_h"), ("dir", "heading"), ("sats", "sats"),
                     ("batt", "batt"), ("temp", "temp"), ("rh", "humidity"), ("pres", "pressure")):
        if d.get(src) is not None:
            t[dst] = d[src]
    if d.get("freq_hz"):
        t["frequency"] = round(d["freq_hz"] / 1e6, 4)
    if position:
        t["uploader_position"] = list(position)
    return t


class SondeHub:
    def __init__(self, callsign, position, version="", on_state=None, log_dir=None):
        """callsign() -> str ("" = not set), position() -> [lat, lon, alt] or None; on_state(info) on changes."""
        self.callsign, self.position, self.version = callsign, position, version
        self.on_state = on_state or (lambda i: None)
        self.log_dir = log_dir       # every object to be sent: <log_dir>/<YYYY-MM-DD>.jsonl (samples for SondeHub)
        self.enabled = False
        self.lock = threading.Lock()
        self.queue = []
        self.sent = 0                # frames accepted by SondeHub
        self.last_ok = None          # time of the last good upload
        self.last_try = None
        self.error = None
        self.warn = None             # a problem SondeHub reported with some frames
        self.rejected = 0            # frames SondeHub refused
        self.blocked = False         # SondeHub does not take data from this software (not validated yet)
        self.listener_t = 0.0
        self.ev = threading.Event()
        self.thread = None

    def info(self):
        with self.lock:
            return {"on": self.enabled, "sent": self.sent, "queued": len(self.queue), "last_ok": self.last_ok,
                    "error": self.error, "warn": self.warn, "rejected": self.rejected, "blocked": self.blocked,
                    "callsign": self.callsign() or ""}

    def set_enabled(self, on):
        with self.lock:
            self.enabled = bool(on)
            if not self.enabled:
                self.queue, self.error = [], None
            else:
                self.listener_t = 0.0        # the station to the map at once
        if self.enabled and (self.thread is None or not self.thread.is_alive()):
            self.thread = threading.Thread(target=self._loop, name="sondehub", daemon=True)
            self.thread.start()
        self.ev.set()
        self.on_state(self.info())

    def add(self, d):
        """A decoded frame (any thread); queued when it is one to send."""
        if not self.enabled:
            return
        call = self.callsign()
        t = telemetry(d, call, self.position(), self.version) if call else None
        if t is None:
            return
        with self.lock:
            self.queue.append(t)
            del self.queue[:-QUEUE_MAX]
        self._log(t)

    def _log(self, t):
        if not self.log_dir:
            return
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            name = os.path.join(self.log_dir, time.strftime("%Y-%m-%d", time.gmtime()) + ".jsonl")
            with open(name, "a", encoding="utf-8") as f:
                f.write(json.dumps(t, separators=(",", ":")) + "\n")
        except OSError:
            pass

    def _loop(self):
        while True:
            with self.lock:
                dfm = any(t["type"] in ("DFM", "PS-15") for t in self.queue)
            self.ev.wait(BLOCKED_SEC if self.blocked else UPLOAD_SEC_DFM if dfm else UPLOAD_SEC)
            self.ev.clear()
            if not self.enabled:
                continue
            call = self.callsign()
            if not call:
                self._state(error="no callsign: SETTINGS › GENERAL › LOCATION")
                continue
            if time.time() - self.listener_t > LISTENER_SEC and self.position():
                self._listener(call)
            with self.lock:
                batch, self.queue = self.queue, []
            if not batch:
                self._state(self.error if self.blocked else None)
                continue
            status, err, bad = self._put(TELEMETRY_URL, batch)
            with self.lock:
                self.last_try = time.time()
                if err is None:
                    self.sent += len(batch) - bad
                    self.rejected += bad
                    self.last_ok, self.error, self.blocked = self.last_try, None, False
                elif status is None or status >= 500:
                    self.queue = (batch + self.queue)[-QUEUE_MAX:]   # not reached: sent again later
                    self.error = err
                else:
                    self.rejected += len(batch)                      # refused: not sent again
                    self.error = err
            self.on_state(self.info())
            if err is not None and not self.blocked:
                self.ev.wait(RETRY_SEC)

    def _state(self, error=None):
        with self.lock:
            changed = self.error != error
            self.error = error
        if changed:
            self.on_state(self.info())

    def _listener(self, call):
        body = {"software_name": SOFTWARE, "software_version": self.version, "uploader_callsign": call,
                "uploader_position": list(self.position()), "uploader_antenna": "", "mobile": False}
        status, err, _ = self._put(LISTENER_URL, body, gz=False)
        self.listener_t = time.time() if err is None else time.time() - LISTENER_SEC + RETRY_SEC * 10

    def _put(self, url, body, gz=True):
        """PUT body as JSON -> (HTTP status or None, error or None, frames refused). SondeHub answers 200 = all taken,
        201 / 202 = taken with problems ("errors": the refused frames), 4xx = refused, 5xx = busy. A refusal of
        software SondeHub has not validated yet ("unknown to us") sets self.blocked."""
        data = json.dumps(body, separators=(",", ":")).encode()
        headers = {"User-Agent": f"{SOFTWARE}-{self.version}", "Content-Type": "application/json",
                   "Date": email.utils.formatdate(usegmt=True)}
        if gz:
            data = gzip.compress(data)
            headers["Content-Encoding"] = "gzip"
        req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                status, text = r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            try:
                text = e.read().decode("utf-8", "replace")
            except OSError:
                text = ""
            return e.code, self._why(e.code, text), len(body) if isinstance(body, list) else 0
        except (OSError, ValueError) as e:
            return None, str(getattr(e, "reason", e)), 0
        if status == 200:
            return status, None, 0
        try:
            errs = json.loads(text).get("errors") or []
        except (ValueError, AttributeError):
            errs = []
        if not errs:
            return status, None, 0
        msg = str(errs[0].get("error_message", "")) if isinstance(errs[0], dict) else str(errs[0])
        if len(errs) >= (len(body) if isinstance(body, list) else 1):
            return 400, self._why(status, msg), len(errs)       # every frame refused: an error
        self.warn = msg[:200]
        return status, None, len(errs)

    def _why(self, code, text):
        if "unknown to us" in text:
            self.blocked = True
            return ("SondeHub does not take data from RADIMCOM yet: new software has to be validated by SondeHub "
                    "(support@sondehub.org, sondehub.org/go/discord); the frames are logged in data\\logs\\sondehub")
        return f"HTTP {code} {text[:200]}".strip()

"""Spots to the networks (SETTINGS › GENERAL › SPOTS): FT8 decodes to PSK Reporter, WSPR decodes to WSPRnet.

Off until the user enters a callsign and switches a network on (data\\spotting.json, shared by all VFOs). The receiver
locator is the station location (location.py); nothing is sent while it is still 0.0 / 0.0.

PSK Reporter (https://pskreporter.info/pskdev.html): IPFIX over UDP to report.pskreporter.info:4739. The spots are
collected and sent at most once per five minutes (the timer is not tied to the clock), the record descriptors in the
first three packets and then once per hour, one UDP socket (the same source port) and one random observation ID per
process. A callsign is reported once per hour per band, again sooner only when its locator becomes known.

WSPRnet: each WSPR spot as an HTTP request to wsprnet.org/post/ (like WSJT-X, "function=wspr"), from a worker thread
right after the cycle; a spot that could not be sent is tried again with the next cycle, at most one hour.

Every VFO process reports what it decodes itself; the counters on the page are those of the VFO that serves it.
Spots that could not be sent (offline, no locator, WSPRnet refusing) are written to the daily log logs\\spots
(always, shared by all VFOs, each line with the VFO name).
"""
import json
import os
import random
import re
import socket
import struct
import threading
import time
import urllib.parse
import urllib.request

import location
from daylog import DayLog
from paths import data

CONFIG_PATH = data("spotting.json")
DEFAULTS = {"callsign": "", "antenna": "", "pskreporter": False, "wsprnet": False}

PSK_HOST, PSK_PORT = "report.pskreporter.info", 4739
PSK_EVERY_S = 300               # "no more than one every five minutes"
PSK_FIRST_S = 60                # the first packet after the start of the reporter
PSK_JITTER_S = 20               # "add some randomization to the five minute timer"
PSK_TEMPLATES_EVERY_S = 3600    # descriptors "at least once per hour"
PSK_TEMPLATES_FIRST = 3         # … and in the first three packets
PSK_REPEAT_S = 3600             # a callsign once per hour (per band) if it has not changed
PSK_MAX_BYTES = 1400            # a full packet is sent at once (and stays under a usual MTU)
PSK_QUEUE_MAX = 2000
ENTERPRISE = 30351

WSPRNET_URL = "http://wsprnet.org/post/"
WSPRNET_TIMEOUT_S = 15
WSPRNET_KEEP_S = 3600
WSPRNET_QUEUE_MAX = 500

_CALL = re.compile(r"^(?=.*\d)(?=.*[A-Z])[A-Z0-9/]{3,12}$")
_lock = threading.Lock()
_cfg_cache = [0.0, None]
_log = DayLog("spots")          # replaced in register() by one with the VFO name


def log(line):
    _log.write(line)


# ---------- settings ----------

def load():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    s = s if isinstance(s, dict) else {}
    return {k: type(v)(s.get(k, v)) for k, v in DEFAULTS.items()}


def save(changes):
    """Checks and saves the changed fields; returns the whole settings. ValueError with the reason if a value is wrong."""
    with _lock:
        s = load()
        if "callsign" in changes:
            call = str(changes["callsign"] or "").strip().upper()
            if call and not _CALL.match(call):
                raise ValueError("a callsign has 3 to 12 letters, digits or /, with at least one letter and one digit")
            s["callsign"] = call
        if "antenna" in changes:
            s["antenna"] = " ".join(str(changes["antenna"] or "").split())[:60]
        for k in ("pskreporter", "wsprnet"):
            if k in changes:
                s[k] = bool(changes[k])
        tmp = f"{CONFIG_PATH}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
        os.replace(tmp, CONFIG_PATH)
        _cfg_cache[0] = 0.0
        return s


def _cfg():
    """The settings, read again at most every 10 s (another VFO may have changed them)."""
    if time.monotonic() - _cfg_cache[0] > 10 or _cfg_cache[1] is None:
        _cfg_cache[0], _cfg_cache[1] = time.monotonic(), load()
    return _cfg_cache[1]


def _receiver():
    """(callsign, 6-character locator) of the station, or the reason why nothing can be sent."""
    c = _cfg()
    if not c["callsign"]:
        return None, "no callsign set"
    q = location.load()
    if q["lat"] == 0 and q["lon"] == 0:
        return None, "the station location is not set (SETTINGS › GENERAL › LOCATION)"
    return (c["callsign"], q["locator"][:6].upper()[:4] + q["locator"][4:6].lower()), ""


_version = [None]


def software():
    if _version[0] is None:
        try:
            import update_check
            _version[0] = f"RADIMCOM {update_check.own_version() or ''}".strip()
        except Exception:
            _version[0] = "RADIMCOM"
    return _version[0]


def band_of(hz):
    """A key for "the same band": whole MHz below 30 MHz is enough to tell the HF bands apart."""
    return int(hz // 1_000_000)


# ---------- PSK Reporter: IPFIX ----------

def _s(text):
    b = str(text).encode("utf-8")[:254]
    return bytes([len(b)]) + b


def _pad4(b):
    return b + b"\0" * (-len(b) % 4)


def _field(fid, length):
    return struct.pack(">HHI", 0x8000 | fid, length, ENTERPRISE)


RX_TEMPLATE_ID, TX_TEMPLATE_ID = 0x9992, 0x9993


def rx_template():
    """Options template (set 3, scope count 1): receiverCallsign, receiverLocator, decodingSoftware, antennaInformation."""
    fields = _field(2, 0xFFFF) + _field(4, 0xFFFF) + _field(8, 0xFFFF) + _field(9, 0xFFFF)
    b = _pad4(struct.pack(">HHHHH", 3, 0, RX_TEMPLATE_ID, 4, 1) + fields)
    return b[:2] + struct.pack(">H", len(b)) + b[4:]


def tx_template():
    """senderCallsign, frequency (4 bytes), sNR (1), mode, senderLocator, informationSource (1), flowStartSeconds (4)."""
    body = (struct.pack(">HH", TX_TEMPLATE_ID, 7) + _field(1, 0xFFFF) + _field(5, 4) + _field(6, 1) + _field(10, 0xFFFF)
            + _field(3, 0xFFFF) + _field(11, 1) + struct.pack(">HH", 150, 4))
    return struct.pack(">HH", 2, 4 + len(body)) + body


def _set(set_id, records):
    b = _pad4(b"".join(records))
    return struct.pack(">HH", set_id, 4 + len(b)) + b


def rx_record(call, grid, soft, antenna):
    return _s(call) + _s(grid) + _s(soft) + _s(antenna)


def tx_record(spot):
    snr = max(-128, min(127, int(spot["snr"])))
    return (_s(spot["call"]) + struct.pack(">I", int(spot["freq_hz"]) & 0xFFFFFFFF) + struct.pack(">b", snr)
            + _s(spot.get("mode", "FT8")) + _s(spot.get("grid") or "") + b"\x01" + struct.pack(">I", int(spot["ts"])))


def packet(seq, obs_id, rx, spots, templates, now=None):
    """One IPFIX datagram: header, the descriptors (if templates), the receiver record and the sender records."""
    body = b""
    if templates:
        body += rx_template() + tx_template()
    body += _set(RX_TEMPLATE_ID, [rx_record(*rx)])
    if spots:
        body += _set(TX_TEMPLATE_ID, [tx_record(s) for s in spots])
    head = struct.pack(">HHIII", 10, 16 + len(body), int(now or time.time()), seq & 0xFFFFFFFF, obs_id)
    return head + body


class PskReporter:
    def __init__(self):
        self.queue = []
        self.reported = {}          # (call, band) -> (time, grid) of the last report
        self.grids = {}             # call -> the newest 4-character locator heard from it
        self.lock = threading.Lock()
        self.obs_id = random.getrandbits(32)
        self.seq = 0
        self.packets = 0
        self.templates_at = 0.0
        self.sent = 0
        self.failed = 0
        self.last_sent = 0.0
        self.error = ""
        self._sock = None
        # the first packet soon after the first spot (no packet before it); then every five minutes
        self._next = time.monotonic() + PSK_FIRST_S + random.uniform(0, PSK_JITTER_S)
        threading.Thread(target=self._loop, name="pskreporter", daemon=True).start()

    def add(self, d):
        """An FT8 decode (with "call"): queued unless the call was reported on this band within the hour."""
        call, now = d["call"], d.get("ts") or time.time()
        with self.lock:
            if d.get("grid"):
                self.grids[call] = d["grid"]
            grid = self.grids.get(call, "")
            key = (call, band_of(d["freq_hz"]))
            last = self.reported.get(key)
            if last and now - last[0] < PSK_REPEAT_S and (last[1] or not grid):
                return
            self.reported[key] = (now, grid)
            if len(self.queue) < PSK_QUEUE_MAX:
                self.queue.append({"call": call, "freq_hz": d["freq_hz"], "snr": d["snr"], "grid": grid,
                                   "mode": d.get("mode", "FT8"), "ts": now})
            if len(self.reported) > 20000:
                for k in [k for k, v in self.reported.items() if now - v[0] > PSK_REPEAT_S]:
                    del self.reported[k]
            full = len(self.queue) * 30 > PSK_MAX_BYTES - 200
        if full:
            self._next = time.monotonic()

    def _loop(self):
        while True:
            time.sleep(1)
            if time.monotonic() < self._next:
                continue
            self._next = time.monotonic() + PSK_EVERY_S + random.uniform(0, PSK_JITTER_S)
            try:
                self.flush()
            except Exception as e:  # noqa: BLE001 - the thread must keep running
                self.error = str(e)[:200]

    def _failed(self, spots, why):
        self.failed += len(spots)
        self.error = why
        calls = " ".join(f"{s['call']} {s['freq_hz'] / 1e6:.6f}" for s in spots[:20])
        more = f" … +{len(spots) - 20}" if len(spots) > 20 else ""
        log(f"PSK Reporter: {len(spots)} FT8 spot{'s' if len(spots) != 1 else ''} not sent ({why}): {calls}{more}")

    def flush(self):
        with self.lock:
            spots, self.queue = self.queue, []
        if not spots:
            return
        if not _cfg()["pskreporter"]:           # switched off meanwhile: the queue is just dropped
            return
        rx, why = _receiver()
        if rx is None:
            self._failed(spots, why)
            return
        try:
            self._send(spots, rx + (software(), _cfg()["antenna"]))
        except Exception as e:  # noqa: BLE001 - offline, DNS: these spots are lost, the next ones in five minutes
            self._failed(spots, str(e)[:200] or type(e).__name__)

    def _send(self, spots, rx):
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        addr = (socket.gethostbyname(PSK_HOST), PSK_PORT)
        while spots:
            now = time.time()
            templates = self.packets < PSK_TEMPLATES_FIRST or now - self.templates_at > PSK_TEMPLATES_EVERY_S
            part = []
            size = 16 + (len(rx_template()) + len(tx_template()) if templates else 0) + 8 + len(rx_record(*rx)) + 8
            while spots and size + len(tx_record(spots[0])) <= PSK_MAX_BYTES:
                size += len(tx_record(spots[0]))
                part.append(spots.pop(0))
            if not part:                        # cannot happen with sane strings; never loop forever
                part.append(spots.pop(0))
            try:
                self._sock.sendto(packet(self.seq, self.obs_id, rx, part, templates, now), addr)
            except Exception:
                spots[:0] = part                # this part and the rest are counted as failed by flush()
                raise
            self.seq += len(part)               # "the count of reports and not the count of packets"
            self.packets += 1
            if templates:
                self.templates_at = now
            self.sent += len(part)
            self.last_sent = now
        self.error = ""

    def status(self):
        with self.lock:
            q = len(self.queue)
        return {"queued": q, "sent": self.sent, "failed": self.failed, "last_sent": self.last_sent, "error": self.error,
                "next_in_s": max(0, round(self._next - time.monotonic()))}


# ---------- WSPRnet ----------

def wsprnet_query(spot, rx):
    """The query of one WSPR spot for wsprnet.org/post/ (the fields WSJT-X sends)."""
    t0 = time.gmtime(spot["ts"] - 120)          # the decode time is the end of the 2-minute cycle
    dial = spot["freq_hz"] - spot.get("df", 0)
    return urllib.parse.urlencode({
        "function": "wspr", "rcall": rx[0], "rgrid": rx[1], "rqrg": f"{dial / 1e6:.6f}",
        "date": time.strftime("%y%m%d", t0), "time": time.strftime("%H%M", t0),
        "sig": spot["snr"], "dt": f"{spot['dt']:.1f}", "drift": spot.get("drift", 0),
        "tqrg": f"{spot['freq_hz'] / 1e6:.6f}", "tcall": spot["call"], "tgrid": spot.get("grid", ""),
        "dbm": spot.get("dbm", 0), "version": software(), "mode": 2})


class WsprNet:
    def __init__(self):
        self.queue = []
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.sent = 0
        self.failed = 0
        self.last_sent = 0.0
        self.error = ""
        threading.Thread(target=self._loop, name="wsprnet", daemon=True).start()

    def add(self, d):
        with self.lock:
            if len(self.queue) < WSPRNET_QUEUE_MAX:
                self.queue.append(dict(d))
        self.wake.set()

    def _loop(self):
        while True:
            self.wake.wait(60)
            self.wake.clear()
            time.sleep(2)                        # the rest of the cycle's spots arrive together
            try:
                self._send_all()
            except Exception as e:  # noqa: BLE001 - the thread must keep running
                self.error = str(e)[:200]

    def _send_all(self):
        with self.lock:
            spots, self.queue = self.queue, []
        if not spots:
            return
        if not _cfg()["wsprnet"]:
            return
        rx, why = _receiver()
        if rx is None:
            self.failed += len(spots)
            self.error = why
            for s in spots:
                log(f"WSPRnet: {self._name(s)} not sent ({why})")
            return
        left = []
        for i, s in enumerate(spots):
            if time.time() - s["ts"] > WSPRNET_KEEP_S:
                self.failed += 1
                log(f"WSPRnet: {self._name(s)} dropped, not sent within {WSPRNET_KEEP_S // 60} min ({self.error})")
                continue
            try:
                req = urllib.request.Request(f"{WSPRNET_URL}?{wsprnet_query(s, rx)}", headers={"User-Agent": software()})
                with urllib.request.urlopen(req, timeout=WSPRNET_TIMEOUT_S) as r:
                    r.read()
                self.sent += 1
                self.last_sent = time.time()
                self.error = ""
            except Exception as e:  # noqa: BLE001 - WSPRnet busy or offline: the rest waits for the next cycle
                self.error = str(e)[:200] or type(e).__name__
                left = spots[i:]
                log(f"WSPRnet: {len(left)} spot{'s' if len(left) != 1 else ''} not sent yet ({self.error}), "
                    f"tried again after the next cycle: {', '.join(self._name(x) for x in left[:20])}")
                break
        if left:
            with self.lock:
                self.queue = left + self.queue

    @staticmethod
    def _name(s):
        return f"{s['call']} {s['freq_hz'] / 1e6:.6f} {time.strftime('%H%M', time.gmtime(s['ts'] - 120))}"

    def status(self):
        with self.lock:
            q = len(self.queue)
        return {"queued": q, "sent": self.sent, "failed": self.failed, "last_sent": self.last_sent, "error": self.error}


# ---------- the decoders' hook and the API ----------

_psk = None
_wspr = None
_start_lock = threading.Lock()


def decode(kind, d):
    """Called for every FT8 / WSPR decode; sends only what the settings allow."""
    global _psk, _wspr
    if "call" not in d:
        return
    c = _cfg()
    if not c["callsign"]:
        return
    if kind == "ft8" and c["pskreporter"]:
        with _start_lock:
            if _psk is None:
                _psk = PskReporter()
        _psk.add(d)
    elif kind == "wspr" and c["wsprnet"]:
        with _start_lock:
            if _wspr is None:
                _wspr = WsprNet()
        _wspr.add(d)


def info():
    rx, why = _receiver()
    return dict(load(), ready=rx is not None, why=why, software=software(),
                psk=_psk.status() if _psk else None, wspr=_wspr.status() if _wspr else None)


def register(app, same_host, tag=""):
    global _log
    from flask import jsonify, request
    _log = DayLog("spots", tag)

    @app.route("/api/spotting", methods=["GET", "POST"])
    def api_spotting():
        """SETTINGS › GENERAL › SPOTS: the callsign and the networks (shared by all VFOs), and what this VFO has sent.
        POST {"callsign", "antenna", "pskreporter", "wsprnet"} (any of them)."""
        if request.method == "POST":
            if not same_host(request):
                return jsonify({"error": "the spot settings can be changed only from this RADIMCOM page"}), 403
            body = request.get_json(force=True, silent=True) or {}
            try:
                save({k: body[k] for k in DEFAULTS if k in body})
            except (TypeError, ValueError) as e:
                return jsonify({"error": str(e)}), 400
        return jsonify(info())

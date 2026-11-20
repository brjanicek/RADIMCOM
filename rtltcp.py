"""Remote RTL-SDR dongle over the network (rtl_tcp) with the same interface as RtlSdr in sdr.py.

A VFO gets driver "rtltcp" and, instead of a USB serial, the address of the dongle in "serial":

    "SDR1_060@192.168.1.50"   dongle SDR1_060 on a server with rtltcp-manager (rpi/install_rtltcp.sh): its rtl_tcp
                                 port is looked up in http://192.168.1.50:1233/dongles.json, so it does not matter
                                 which USB port of the server it is plugged into
    "192.168.1.50:1234"       any plain rtl_tcp server (rtl_tcp -a 0.0.0.0 -p 1234)

The samples are the same raw unsigned 8 bit I/Q as from a USB dongle, so DSP, VDL2, DAB and ISM work unchanged.
rtl_tcp protocol: the server sends a 12 byte header ("RTL0", tuner type, number of gains), then I/Q without end;
the client sends commands of 5 bytes (command, 32 bit big endian value).

Settings for the SDR setup page live in vfos.json "rtltcp_servers": ["192.168.1.50", "10.0.0.7:1234"]
(a host alone = rtltcp-manager list, host:port = one plain rtl_tcp).
"""
import json
import socket
import struct
import threading
import time
import urllib.error
import urllib.request

import numpy as np

LIST_PORT = 1233             # rtltcp-manager: http://<host>:1233/dongles.json
CONNECT_TIMEOUT_S = 4.0
READ_TIMEOUT_S = 5.0         # no data this long: the read fails and the receiver reconnects
RCVBUF = 4 << 20
RATE_WINDOW_S = 3.0          # received samples are compared with the sample rate over this window
SLOW_RATIO = 0.97            # less than this share arrives: the network is too slow (the server drops samples)
WATCH_S = 15                 # how often a VFO asks its server for warnings (under-voltage, temperature)

# rtl_tcp commands
SET_FREQ, SET_RATE, SET_GAIN_MODE, SET_GAIN, SET_PPM, SET_IF_GAIN, SET_TEST, SET_AGC = 1, 2, 3, 4, 5, 6, 7, 8
SET_DIRECT, SET_OFFSET, SET_XTAL, SET_TUNER_XTAL, SET_GAIN_IDX, SET_BIAS_TEE = 9, 10, 11, 12, 13, 14

# The header gives only the tuner type and the number of gains; the values are those of librtlsdr (tenths of dB).
TUNERS = {1: "E4000", 2: "FC0012", 3: "FC0013", 4: "FC2580", 5: "R820T", 6: "R828D"}
TUNER_GAINS = {
    1: [-10, 15, 40, 65, 90, 115, 140, 165, 190, 215, 240, 290, 340, 420],
    2: [-99, -40, 71, 179, 192],
    3: [-99, -73, -65, -63, -60, -58, -54, 58, 61, 63, 65, 67, 68, 70, 71, 179, 181, 182, 184, 186, 188, 191, 197],
    4: [0],
    5: [0, 9, 14, 27, 37, 77, 87, 125, 144, 157, 166, 197, 207, 229, 254, 280, 297, 328, 338, 364, 372, 386, 402,
        421, 434, 439, 445, 480, 496],
}
TUNER_GAINS[6] = TUNER_GAINS[5]


def is_addr(s):
    return "@" in (s or "") or ":" in (s or "")


SPYSERVER = ("sdr://", "spyserver://")


def clean_server(server):
    """Address as typed or pasted -> 'host' or 'host:port': a scheme (rtl_tcp://, tcp://, http://) and a path or a
    trailing slash are dropped. ValueError for a SpyServer address (sdr://, a different protocol than rtl_tcp)."""
    server = (server or "").strip()
    low = server.lower()
    if low.startswith(SPYSERVER):
        raise ValueError("this is a SpyServer address (sdr://, Airspy SpyServer protocol); RADIMCOM connects only to "
                         "rtl_tcp servers (rtl_tcp -a 0.0.0.0 -p 1234) and rtltcp-manager")
    if "://" in server:
        server = server.split("://", 1)[1]
    return server.split("/", 1)[0].strip()


def server_kind(server, timeout=2.0):
    """"spyserver" or "rtltcp" by the address: sdr:// = SpyServer, a host alone = rtltcp-manager; host:port without a
    scheme is asked – an rtl_tcp server sends its "RTL0" header at once, a SpyServer is silent until the client's HELLO
    (any port: SpyServers are not only on 5555)."""
    if (server or "").strip().lower().startswith(SPYSERVER):
        return "spyserver"
    try:
        host, port = split_server(server)
    except ValueError:
        return "rtltcp"
    if port is None or port == LIST_PORT:
        return "rtltcp"
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(1.2)
            hdr = s.recv(4)
    except socket.timeout:
        return "spyserver"           # connected, but nothing comes: waits for the client
    except OSError:
        return "rtltcp"              # not reachable: the error is shown by the rtl_tcp check
    return "rtltcp"                  # "RTL0" header (or closed at once: the rtl_tcp check tells why)


def split_server(server):
    """'host' -> (host, None), 'host:1234' -> (host, 1234); also 'rtl_tcp://host:1234/'."""
    server = clean_server(server)
    if server.count(":") == 1:
        host, port = server.rsplit(":", 1)
        return host.strip(), int(port)
    return server, None


def fetch_list(host, port=LIST_PORT, timeout=2.0):
    """Dongles of an rtltcp-manager server: [{serial, port, product, running, ...}]."""
    with urllib.request.urlopen(f"http://{host}:{port}/dongles.json", timeout=timeout) as r:
        return json.load(r).get("dongles", [])


def probe(host, port, timeout=2.0):
    """Header of a plain rtl_tcp server: (tuner type, number of gains). Connecting takes the dongle only briefly."""
    with socket.create_connection((host, port), timeout=timeout) as s:
        hdr = _recv_exact(s, 12)
    if hdr[:4] != b"RTL0":
        raise RuntimeError(f"{host}:{port} is not an rtl_tcp server")
    return struct.unpack(">II", hdr[4:])


def list_devices(servers, timeout=2.0):
    """Network dongles of the given servers for the SDR setup: [{serial (= address), name, server, error?}]."""
    out = []
    for server in servers or []:
        try:
            host, port = split_server(server)
        except ValueError as e:
            msg = str(e) if "SpyServer" in str(e) else "address must be host or host:port"
            out.append({"serial": "", "name": "", "server": server, "error": msg})
            continue
        if port is None or port == LIST_PORT:
            try:
                for d in fetch_list(host, port or LIST_PORT, timeout):
                    if d.get("port") and d.get("serial"):
                        name = f"{d.get('product') or 'RTL-SDR'} · {host}:{d['port']}"
                        out.append({"serial": f"{d['serial']}@{host}", "name": name, "server": server})
                continue
            except Exception as e:
                if port == LIST_PORT:
                    out.append({"serial": "", "name": "", "server": server, "error": str(e)})
                    continue
                port = 1234                  # no rtltcp-manager: a plain rtl_tcp on its default port?
                err = e
        try:
            tuner, _ = probe(host, port, timeout)
            out.append({"serial": f"{host}:{port}", "name": f"rtl_tcp {TUNERS.get(tuner, 'tuner ?')}", "server": server})
        except Exception as e:
            out.append({"serial": "", "name": "", "server": server, "error": str(e) if split_server(server)[1] else
                        f"no rtltcp-manager list ({err}) and no rtl_tcp on port 1234"})
    return out


def _host_of(server):
    try:
        return split_server(server)[0]
    except ValueError:              # a SpyServer address in the saved list: not one of ours
        return server


def servers_in_use(vfos_cfg):
    """rtl_tcp servers of vfos.json: the saved list ("rtltcp_servers") and the hosts of the VFO dongles."""
    out = [str(s).strip() for s in vfos_cfg.get("rtltcp_servers", []) if str(s).strip()
           and not str(s).strip().lower().startswith(SPYSERVER)]      # SpyServers are not rtl_tcp servers
    for v in vfos_cfg.get("vfos", []):
        if v.get("driver") == "rtltcp" and "@" in (v.get("serial") or ""):
            host = v["serial"].split("@", 1)[1]
            if host not in out and split_server(host)[0] not in [_host_of(s) for s in out]:
                out.append(host)
    return out


def tcp_ping(host, port, count=3, timeout=1.5):
    """Round trip of a TCP connect in ms (the best of a few; no ICMP needed), None if it does not answer."""
    import time
    best = None
    for _ in range(count):
        t0 = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                ms = (time.perf_counter() - t0) * 1000
        except OSError:
            continue
        best = ms if best is None else min(best, ms)
    return None if best is None else round(best, 1)


def server_status(server, vfos_cfg=None):
    """SETTINGS > RTL_TCP: the state of one server (rtltcp-manager /status.json) with the ping from here."""
    try:
        host, port = split_server(server)
    except ValueError as e:
        return {"server": server, "host": server, "ping_ms": None, "error": str(e)}
    lport = port or LIST_PORT
    out = {"server": server, "host": host, "ping_ms": tcp_ping(host, lport)}
    try:
        t0 = time.time()
        with urllib.request.urlopen(f"http://{host}:{lport}/status.json", timeout=3) as r:
            out["status"] = json.load(r)
        t1 = time.time()
        if out["status"].get("time"):          # server clock minus PC clock, at the middle of the request
            out["clock_offset_s"] = round(out["status"]["time"] - (t0 + t1) / 2, 3)
            out["clock_error_s"] = round((t1 - t0) / 2, 3)
    except Exception as e:
        out["error"] = f"no rtltcp-manager status ({getattr(e, 'reason', e)})"
        if port and port != LIST_PORT:          # a plain rtl_tcp: only whether it answers
            try:
                tuner, _ = probe(host, port)
                out["plain"] = {"port": port, "tuner": TUNERS.get(tuner, "?")}
                out.pop("error")
            except Exception as e2:
                out["error"] = str(e2)
    if vfos_cfg:                                # which VFO uses which dongle of this server
        use = {}
        for v in vfos_cfg.get("vfos", []):
            s = v.get("serial") or ""
            if v.get("driver") == "rtltcp" and split_server(s.split("@", 1)[-1])[0] == host:
                use.setdefault(s.split("@", 1)[0] if "@" in s else s, []).append(v["name"])
        for v in vfos_cfg.get("vfos", []):      # chained VFOs follow their owner
            if v.get("chain"):
                for k, names in use.items():
                    if v["chain"] in names:
                        names.append(v["name"])
        out["vfos"] = use
        out["vfo_state"] = _vfo_states(vfos_cfg, [n for names in use.values() for n in names])
    return out


def _vfo_states(vfos_cfg, names):
    """Frequency, sample rate and share of arriving samples of the VFOs on this server (their /api/state)."""
    out = {}
    for v in vfos_cfg.get("vfos", []):
        if v["name"] not in names or not v.get("port"):
            continue
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{v['port']}/api/state", timeout=1.5) as r:
                s = json.load(r)
            out[v["name"]] = {k: s.get(k) for k in ("tune_hz", "center_hz", "sample_rate", "net_ratio", "status", "mode")}
        except Exception:
            out[v["name"]] = {"status": "unreachable"}
    return out


def latest_manager():
    """Version of rpi/rtltcp_manager.py shipped with this RADIMCOM (for the UPDATE key)."""
    import os
    import re
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rpi", "rtltcp_manager.py")
    try:
        with open(path, encoding="utf-8") as f:
            code = f.read()
    except OSError:
        return None, None
    m = re.search(r'^VERSION = "([^"]+)"', code, re.M)
    return (m.group(1) if m else None), code


def version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return ()


def _post(server, path, obj, timeout=6):
    host, port = split_server(server)
    req = urllib.request.Request(f"http://{host}:{port or LIST_PORT}{path}", data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return {"error": json.load(e).get("error", str(e))}
        except ValueError:
            return {"error": str(e)}
    except Exception as e:
        return {"error": str(getattr(e, "reason", e))}


def server_restart_dongle(server, serial):
    return _post(server, "/restart", {"serial": serial})


def server_update(server):
    """Sends the rtltcp_manager.py of this RADIMCOM to the server, which replaces itself and restarts."""
    version, code = latest_manager()
    if not code:
        return {"error": "rpi/rtltcp_manager.py not found in RADIMCOM"}
    return _post(server, "/update", {"code": code}, timeout=15)


def server_power(server, action):
    """Reboot / poweroff of a server through its rtltcp-manager."""
    return _post(server, "/power", {"action": action})


def resolve(addr):
    """Address of a VFO -> (host, rtl_tcp port, product or "")."""
    if "@" in addr:
        serial, server = addr.split("@", 1)
        host, lport = split_server(server)
        try:
            dongles = fetch_list(host, lport or LIST_PORT, timeout=CONNECT_TIMEOUT_S)
        except Exception as e:
            why = getattr(e, "reason", e)
            raise RuntimeError(f"rtl_tcp server {host} not reachable ({why})")
        for d in dongles:
            if d.get("serial") == serial:
                if not d.get("port"):
                    raise RuntimeError(f"dongle {serial} on {host}: {d.get('error', 'not served')}")
                if d.get("running") is False:
                    raise RuntimeError(f"dongle {serial} on {host}: rtl_tcp is not running (see journalctl -u rtltcp-manager)")
                return host, int(d["port"]), d.get("product", "")
        raise RuntimeError(f"dongle {serial} is not connected to {host}")
    host, port = split_server(addr)
    if port is None:
        raise RuntimeError(f"rtl_tcp address '{addr}' needs a port (host:port) or a serial (serial@host)")
    return host, port, ""


def _recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        d = sock.recv(n - len(buf))
        if not d:
            raise RuntimeError("rtl_tcp server closed the connection")
        buf += d
    return bytes(buf)


class RtlTcpSdr:
    """rtl_tcp client; the methods match RtlSdr (sdr.py)."""

    has_bias_tee = True
    has_rtl_agc = True

    def __init__(self, read_samples, addr):
        from sdr import TUNER_MIN_HZ, V4_MIN_HZ
        self.addr = addr
        self.block = read_samples * 2
        host, port, product = resolve(addr)
        self.where = f"{host}:{port}"
        try:
            self.sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT_S)
        except OSError as e:
            raise RuntimeError(f"cannot connect to rtl_tcp {self.where} ({e})")
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RCVBUF)
        except OSError:
            pass
        self.sock.settimeout(READ_TIMEOUT_S)
        hdr = _recv_exact(self.sock, 12)
        if hdr[:4] != b"RTL0":
            self.sock.close()
            raise RuntimeError(f"{self.where} is not an rtl_tcp server")
        self.tuner, ngains = struct.unpack(">II", hdr[4:])
        if self.tuner == 0:
            self.sock.close()
            raise RuntimeError(f"rtl_tcp {self.where}: the server has no dongle (tuner unknown)")
        table = TUNER_GAINS.get(self.tuner) or []
        self.gains = [g / 10 for g in (table if len(table) == ngains or not ngains else table[:ngains])]
        self.tuner_min_hz = V4_MIN_HZ if "Blog V4" in product else TUNER_MIN_HZ
        self.tuner_name = TUNERS.get(self.tuner, "?")
        self.lock = threading.Lock()
        self._stop = False
        self.lost = 0
        self.rate = 0
        self.net_ratio = None        # share of the samples that arrive (None = not measured yet)
        self._win_t, self._win_bytes = None, 0
        self.server_warn = []        # warnings of the server (under-voltage, hot), for the VFO header
        if "@" in addr:              # an rtltcp-manager: its state is checked now and then
            threading.Thread(target=self._watch_server, args=(addr.split("@", 1)[1],), name="rtltcp-watch",
                             daemon=True).start()

    def _watch_server(self, server):
        host, port = split_server(server)
        while self.sock is not None and not self._stop:
            warn = []
            try:
                with urllib.request.urlopen(f"http://{host}:{port or LIST_PORT}/status.json", timeout=3) as r:
                    st = json.load(r)
                flags = (st.get("throttled") or {}).get("flags", [])
                if "under-voltage" in flags:
                    warn.append("under-voltage")
                if (st.get("temp_c") or 0) >= 80:
                    warn.append(f"hot {st['temp_c']:.0f} °C")
            except Exception:
                pass
            self.server_warn = warn
            for _ in range(WATCH_S):
                if self.sock is None or self._stop:
                    return
                time.sleep(1)

    def _cmd(self, cmd, value):
        with self.lock:
            try:
                self.sock.sendall(struct.pack(">BI", cmd, int(value) & 0xFFFFFFFF))
            except OSError as e:
                raise RuntimeError(f"rtl_tcp {self.where}: {e}")

    def set_sample_rate(self, rate):
        self._cmd(SET_RATE, rate)
        self.rate = int(rate)
        self._win_t, self.net_ratio = None, None      # measure again at the new rate

    def _measure(self, n):
        """Share of the expected bytes that arrived in the last window. rtl_tcp drops what the network cannot
        carry, so a slow link is seen only here (the stream itself has no gaps or counters)."""
        now = time.monotonic()
        if self._win_t is None:
            self._win_t, self._win_bytes = now + 1.0, -1     # skip the first second (buffers filling)
            return
        if now < self._win_t:
            return
        if self._win_bytes < 0:
            self._win_t, self._win_bytes = now, 0
            return
        self._win_bytes += n
        dt = now - self._win_t
        if dt >= RATE_WINDOW_S and self.rate:
            self.net_ratio = round(min(self._win_bytes / (2 * self.rate * dt), 1.0), 3)
            self._win_t, self._win_bytes = now, 0

    def set_center_freq(self, hz):
        self._cmd(SET_FREQ, hz)

    def set_gain(self, gain):
        if gain in ("auto", "", None):
            self._cmd(SET_GAIN_MODE, 0)
        else:
            self._cmd(SET_GAIN_MODE, 1)
            self._cmd(SET_GAIN, int(round(float(gain) * 10)))

    def set_rtl_agc(self, on):
        self._cmd(SET_AGC, 1 if on else 0)

    def set_bias_tee(self, on):
        self._cmd(SET_BIAS_TEE, 1 if on else 0)

    def set_ppm(self, ppm):
        self._cmd(SET_PPM, int(ppm))

    def reset_buffer(self):
        pass                     # rtl_tcp resets the buffer itself when a client connects

    def read_async(self, on_block):
        """Blocks until cancel_async (or a network error): blocks of read_samples like the USB dongle."""
        buf = bytearray(self.block)
        view = memoryview(buf)
        while not self._stop:
            got = 0
            while got < self.block:
                try:
                    n = self.sock.recv_into(view[got:], self.block - got)
                except socket.timeout:
                    if self._stop:
                        return
                    raise RuntimeError(f"rtl_tcp {self.where}: no data for {READ_TIMEOUT_S:g} s")
                except OSError as e:
                    if self._stop:
                        return
                    raise RuntimeError(f"rtl_tcp {self.where}: {e}")
                if n == 0:
                    if self._stop:
                        return
                    raise RuntimeError(f"rtl_tcp {self.where} closed the connection")
                got += n
                self._measure(n)
            on_block(np.frombuffer(bytes(buf), np.uint8))

    def cancel_async(self):
        self._stop = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def close(self):
        if self.sock:
            self._stop = True
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

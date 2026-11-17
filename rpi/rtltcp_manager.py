#!/usr/bin/env python3
"""rtltcp-manager: one rtl_tcp per RTL-SDR dongle, found by its USB serial, on a fixed TCP port.

Runs as the systemd service rtltcp-manager. Every few seconds it looks at the USB bus (sysfs, no libusb),
starts rtl_tcp for each new dongle and restarts one that died. A dongle keeps its port across reboots and
replugs: the serial -> port map is saved in /etc/rtltcp/ports.conf (edit it by hand to choose ports).

    dongle SDR1_060 --> rtl_tcp -d SDR1_060 -p 1234
    dongle SDR2_101 --> rtl_tcp -d SDR2_101 -p 1235

A small HTTP server for RADIMCOM (port 1233):
    GET  /dongles.json   the dongles and their rtl_tcp ports
    GET  /status.json    the server: model, CPU, RAM, temperature, power, network link of the caller, clients
    POST /power          {"action": "reboot" | "poweroff"}                   (POWER=1)
    POST /restart        {"serial": "SDR1_060"}: restarts the rtl_tcp of one dongle
    POST /update         {"code": "<new rtltcp_manager.py>"}: replaces this program and restarts it (UPDATE=1)
The POSTs are accepted only as JSON (a web page cannot send that here) and only from private (LAN) addresses.
Like rtl_tcp itself, nothing here has a password: keep the server in your own network.

Serials must be unique. Two dongles with the same serial (often 00000001) cannot be told apart: only the
first one is served, the log says so. Give each one its own serial with: rtl_eeprom -d <index> -s <serial>
A serial made only of digits is read by librtlsdr as an index, so use one with a letter (e.g. SDR1_060).
"""
import collections
import ipaddress
import json
import os
import re
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONF_DIR = "/etc/rtltcp"
PORTS_FILE = os.path.join(CONF_DIR, "ports.conf")
SETTINGS_FILE = os.path.join(CONF_DIR, "rtltcp.conf")
SYSFS_USB = "/sys/bus/usb/devices"
# RTL2832U based dongles (librtlsdr's known list, the common ones)
RTL_IDS = {("0bda", "2832"), ("0bda", "2838"), ("0ccd", "00a9"), ("0ccd", "00b3"), ("0ccd", "00d3"),
           ("0ccd", "00e0"), ("185b", "0620"), ("185b", "0650"), ("1f4d", "b803"), ("1f4d", "c803"),
           ("1b80", "d3a4"), ("1d19", "1101"), ("1d19", "1102"), ("1d19", "1103"), ("0458", "707f"),
           ("1b80", "d393"), ("1b80", "d394"), ("1b80", "d395"), ("1b80", "d39d")}

DEFAULTS = {"BIND": "0.0.0.0", "FIRST_PORT": "1234", "HTTP_PORT": "1233", "BUFFERS": "500",
            "SCAN_S": "3", "STALL_S": "10", "RTL_TCP": "/opt/rtlsdr-blog/bin/rtl_tcp", "EXTRA_ARGS": "", "IGNORE": "", "POWER": "1", "UPDATE": "1"}
VERSION = "1.4"
HISTORY = 200                # samples of data rate and WiFi signal (every SCAN_S, 3 s -> 10 min)


def log(msg):
    print(msg, flush=True)       # journald adds the time


def read_kv(path):
    out = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"')
    except FileNotFoundError:
        pass
    return out


def sysfs(dev, name):
    try:
        with open(os.path.join(SYSFS_USB, dev, name)) as f:
            return f.read().strip()
    except OSError:
        return ""


def scan():
    """Connected RTL dongles: list of dicts (serial, usb path, names), in bus order."""
    found = []
    for dev in sorted(os.listdir(SYSFS_USB)):
        if ":" in dev:                              # interfaces, not devices
            continue
        if (sysfs(dev, "idVendor"), sysfs(dev, "idProduct")) in RTL_IDS:
            found.append({"serial": sysfs(dev, "serial"), "usb": dev,
                          "vendor": sysfs(dev, "manufacturer"), "product": sysfs(dev, "product")})
    return found


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def host_name():
    """Name shown in RADIMCOM: the pretty hostname (may contain _ , e.g. rtl_tcp_1; hostnamectl --pretty),
    otherwise the hostname."""
    for line in read("/etc/machine-info").splitlines():
        if line.startswith("PRETTY_HOSTNAME="):
            name = line.split("=", 1)[1].strip().strip('"')
            if name:
                return name
    return os.uname().nodename


def run(cmd, timeout=3):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


class CpuLoad:
    """CPU load in % from /proc/stat, sampled in the background (a request must not wait for it)."""

    def __init__(self):
        self.pct = None
        threading.Thread(target=self._run, name="cpu", daemon=True).start()

    @staticmethod
    def _sample():
        v = [int(x) for x in read("/proc/stat").splitlines()[0].split()[1:]]
        idle = v[3] + (v[4] if len(v) > 4 else 0)
        return sum(v), idle

    def _run(self):
        last = self._sample()
        while True:
            time.sleep(2)
            now = self._sample()
            dt, di = now[0] - last[0], now[1] - last[1]
            if dt > 0:
                self.pct = round(100 * (dt - di) / dt, 1)
            last = now


def wifi_info(dev):
    """Frequency (MHz), bit rate (Mb/s), signal (dBm) and SSID of a WiFi interface (iwconfig, wireless-tools)."""
    txt = run(["/sbin/iwconfig", dev])
    out = {}
    m = re.search(r'ESSID:"([^"]*)"', txt)
    if m:
        out["ssid"] = m.group(1)
    m = re.search(r"Frequency[:=]([\d.]+) GHz", txt)
    if m:
        out["freq_mhz"] = round(float(m.group(1)) * 1000)
    m = re.search(r"Bit Rate[:=]([\d.]+) Mb/s", txt)
    if m:
        out["bitrate_mbps"] = float(m.group(1))
    m = re.search(r"Signal level[:=](-?\d+) dBm", txt)
    if m:
        out["signal_dbm"] = int(m.group(1))
    return out


def link_kind(dev, wifi):
    if dev.startswith("wl"):
        f = wifi.get("freq_mhz") or 0
        return "WIFI 5G" if f >= 4900 else "WIFI 2G" if f else "WIFI"
    if dev.startswith(("eth", "en")):
        return "LAN"
    return dev


def interfaces():
    """Network interfaces with an IPv4 address (no docker / loopback)."""
    out = []
    for line in run(["ip", "-4", "-o", "addr", "show"]).splitlines():
        p = line.split()
        if len(p) < 4 or p[1] == "lo" or p[1].startswith(("docker", "br-", "veth")):
            continue
        dev, addr = p[1], p[3].split("/")[0]
        wifi = wifi_info(dev) if dev.startswith("wl") else {}
        speed = read(f"/sys/class/net/{dev}/speed") if not dev.startswith("wl") else ""
        it = {"dev": dev, "addr": addr, "kind": link_kind(dev, wifi), **wifi}
        if speed.lstrip("-").isdigit() and int(speed) > 0:
            it["bitrate_mbps"] = int(speed)
        out.append(it)
    return out


def route_dev(ip):
    """Interface the traffic to this address leaves through."""
    m = re.search(r"\bdev (\S+)", run(["ip", "route", "get", ip]))
    return m.group(1) if m else ""


def clients():
    """Established connections: {local port: [(peer ip, bytes acknowledged), ...]}."""
    out, cur = {}, None
    for line in run(["ss", "-tinH", "state", "established"]).splitlines():
        if not line[:1].isspace():
            p = line.split()
            cur = None
            if len(p) >= 4 and ":" in p[2]:
                cur = [p[3].rsplit(":", 1)[0].strip("[]").replace("::ffff:", ""), 0]
                out.setdefault(int(p[2].rsplit(":", 1)[1]), []).append(cur)
        elif cur is not None:
            m = re.search(r"bytes_acked:(\d+)", line)
            if m:
                cur[1] = int(m.group(1))
    return out


def cpu_mhz():
    txt = run(["vcgencmd", "measure_clock", "arm"])
    if "=" in txt:
        return round(int(txt.split("=")[1]) / 1e6)
    khz = read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    return round(int(khz) / 1000) if khz.isdigit() else None


def disk():
    st = os.statvfs("/")
    return st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize


def meminfo():
    m = {}
    for line in read("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        m[k] = int(v.split()[0]) * 1024 if v.split() else 0
    total = m.get("MemTotal", 0)
    return total, total - m.get("MemAvailable", 0)


THROTTLE_BITS = {0: "under-voltage", 1: "ARM frequency capped", 2: "throttled", 3: "soft temperature limit",
                 16: "under-voltage since boot", 17: "frequency capped since boot", 18: "throttled since boot",
                 19: "soft temperature limit since boot"}


def throttled():
    txt = run(["vcgencmd", "get_throttled"])
    if "=" not in txt:
        return None
    v = int(txt.split("=")[1], 16)
    return {"raw": hex(v), "flags": [t for b, t in THROTTLE_BITS.items() if v & (1 << b)]}


def stalled_ports(stall_ms):
    """Local ports whose client stopped acknowledging data (WiFi switched, PC asleep, cable pulled).
    rtl_tcp serves one client at a time and would wait for TCP to give up (up to ~15 min) before it accepts
    the client's reconnect, so such an rtl_tcp is restarted."""
    try:
        out = subprocess.run(["ss", "-tinH", "state", "established"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return set()
    ports, port = set(), None
    for line in out.splitlines():
        if not line[:1].isspace():                      # socket line: Recv-Q Send-Q local peer
            parts = line.split()
            port = int(parts[2].rsplit(":", 1)[1]) if len(parts) >= 4 and ":" in parts[2] else None
            continue
        if port is None or "unacked:" not in line:
            continue
        last = next((int(t.split(":")[1]) for t in line.split() if t.startswith("lastack:")), 0)
        if last > stall_ms:
            ports.add(port)
    return ports


class Manager:
    def __init__(self):
        self.cfg = dict(DEFAULTS, **read_kv(SETTINGS_FILE))
        self.ports = {k: int(v) for k, v in read_kv(PORTS_FILE).items() if v.isdigit()}
        self.procs = {}         # serial -> Popen
        self.started = {}       # serial -> time of the last start
        self.state = []         # for the HTTP list
        self.warned = set()
        self.lock = threading.Lock()
        self.cpu = CpuLoad()
        self.acked = {}             # (port, peer) -> (time, bytes acknowledged), for the data rate
        self.rates = {}             # port -> Mb/s sent, from the last two scans
        self.history = collections.deque(maxlen=HISTORY)

    def sample(self):
        """Data rate of every client (bytes acknowledged between two scans) and the WiFi signal, into the history."""
        conns, now, rates, seen = clients(), time.monotonic(), {}, set()
        for port, lst in conns.items():
            for peer, acked in lst:
                key = (port, peer)
                seen.add(key)
                last = self.acked.get(key)
                if last and now - last[0] > 0.5 and acked >= last[1]:
                    rates[port] = rates.get(port, 0) + (acked - last[1]) * 8 / (now - last[0]) / 1e6
                self.acked[key] = (now, acked)
        for key in list(self.acked):
            if key not in seen:
                del self.acked[key]
        self.rates, self.conns = rates, conns
        wl = next((l.split(":")[0].strip() for l in read("/proc/net/wireless").splitlines()[2:]), "")
        sig = wifi_info(wl).get("signal_dbm") if wl else None
        with self.lock:
            by_serial = {d["serial"]: round(rates.get(d.get("port"), 0), 1) for d in self.state if d.get("port")}
        self.history.append({"t": round(time.time(), 1), "mbps": by_serial, "signal": sig})

    def status(self, caller):
        """GET /status.json: what the RTL_TCP page of RADIMCOM shows about this server."""
        total, used = meminfo()
        ifs = interfaces()
        dev = route_dev(caller) if caller else ""
        link = next((i for i in ifs if i["dev"] == dev), {"dev": dev, "kind": dev or "?"})
        conns, rates = getattr(self, "conns", {}), self.rates
        with self.lock:
            dongles = [dict(d, clients=[c[0] for c in conns.get(d.get("port"), [])],
                            tx_mbps=round(rates.get(d.get("port"), 0), 1) if d.get("running") else None)
                       for d in self.state]
        temp = read("/sys/class/thermal/thermal_zone0/temp")
        disk_total, disk_free = disk()
        return {
            "host": host_name(), "hostname": os.uname().nodename, "model": read("/proc/device-tree/model").rstrip("\x00") or os.uname().machine,
            "os": next((l.split("=", 1)[1].strip('"') for l in read("/etc/os-release").splitlines()
                        if l.startswith("PRETTY_NAME=")), ""),
            "version": VERSION, "uptime_s": int(float(read("/proc/uptime", "0").split()[0])),
            "cpu_pct": self.cpu.pct, "cpus": os.cpu_count(), "load": [round(x, 2) for x in os.getloadavg()],
            "temp_c": round(int(temp) / 1000, 1) if temp.isdigit() else None,
            "mem_total": total, "mem_used": used, "throttled": throttled(), "cpu_mhz": cpu_mhz(),
            "disk_total": disk_total, "disk_free": disk_free,
            "interfaces": ifs, "link": link, "caller": caller, "dongles": dongles,
            "power": self.cfg["POWER"] == "1", "update": self.cfg["UPDATE"] == "1",
            "time": round(time.time(), 3),
            "ntp": run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"]) == "yes",
            "history": list(self.history),
        }

    def restart_dongle(self, serial):
        """POST /restart: the rtl_tcp of one dongle (its client reconnects)."""
        if serial not in self.procs:
            return 404, {"error": f"no rtl_tcp running for {serial}"}
        self.stop(serial, "restart requested")
        self.started.pop(serial, None)          # start again at the next scan, without the 5 s pause
        return 200, {"ok": True}

    def update(self, code):
        """POST /update: replaces this program with a newer version and restarts (systemd starts it again)."""
        if self.cfg["UPDATE"] != "1":
            return 403, {"error": "updates are off (UPDATE=0 in /etc/rtltcp/rtltcp.conf)"}
        m = re.search(r'^VERSION = "([^"]+)"', code, re.M)
        if not m or "class Manager" not in code:
            return 400, {"error": "this is not rtltcp_manager.py"}
        try:
            compile(code, "rtltcp_manager.py", "exec")
        except SyntaxError as e:
            return 400, {"error": f"syntax error: {e}"}
        path = os.path.realpath(__file__)
        if not os.access(path, os.W_OK) or not os.access(os.path.dirname(path), os.W_OK):
            return 500, {"error": f"{path} is not writable by the service: run install_rtltcp.sh again once"}
        tmp = path + ".new"
        with open(tmp, "w") as f:
            f.write(code)
        os.chmod(tmp, 0o755)
        try:
            os.replace(path, path + ".prev")    # the previous version stays next to it
        except OSError:
            pass
        os.replace(tmp, path)
        log(f"updated {VERSION} -> {m.group(1)}, restarting")
        threading.Timer(1.0, lambda: os._exit(0)).start()      # Restart=always in the service
        return 200, {"ok": True, "version": m.group(1)}

    def power(self, action, caller):
        """POST /power: reboot / poweroff of the server (sudoers rule from install_rtltcp.sh)."""
        if self.cfg["POWER"] != "1":
            return 403, {"error": "power control is off (POWER=0 in /etc/rtltcp/rtltcp.conf)"}
        try:
            private = ipaddress.ip_address(caller).is_private
        except ValueError:
            private = False
        if not private:
            return 403, {"error": "only from the local network"}
        if action not in ("reboot", "poweroff"):
            return 400, {"error": "action must be reboot or poweroff"}
        log(f"{action} requested by {caller}")
        threading.Timer(1.0, lambda: subprocess.run(["sudo", "-n", "/usr/bin/systemctl", action])).start()
        return 200, {"ok": True, "action": action}

    def port_for(self, serial):
        if serial not in self.ports:
            used = set(self.ports.values()) | {int(self.cfg["HTTP_PORT"])}
            p = int(self.cfg["FIRST_PORT"])
            while p in used:
                p += 1
            self.ports[serial] = p
            os.makedirs(CONF_DIR, exist_ok=True)
            with open(PORTS_FILE, "w") as f:
                f.write("# serial = TCP port of its rtl_tcp (edit and restart rtltcp-manager to change)\n")
                for s, pp in sorted(self.ports.items(), key=lambda x: x[1]):
                    f.write(f"{s} = {pp}\n")
            log(f"new dongle {serial}: port {p}")
        return self.ports[serial]

    def start(self, serial, port):
        cmd = [self.cfg["RTL_TCP"], "-a", self.cfg["BIND"], "-p", str(port), "-d", serial,
               "-n", self.cfg["BUFFERS"]] + self.cfg["EXTRA_ARGS"].split()
        log("start: " + " ".join(cmd))
        # rtl_tcp prints a lot (every client, every command): keep only errors in the journal
        self.procs[serial] = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.started[serial] = time.time()

    def stop(self, serial, why):
        p = self.procs.pop(serial, None)
        if p and p.poll() is None:
            log(f"stop {serial}: {why}")
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()

    def tick(self):
        dongles = scan()
        seen = {}
        for d in dongles:
            s = d["serial"]
            if not s:
                d["error"] = "no serial"
                continue
            if s in self.cfg["IGNORE"].split():
                d["error"] = "ignored (IGNORE in rtltcp.conf)"
                continue
            if s in seen:
                d["error"] = "duplicate serial, not served"
                if s not in self.warned:
                    log(f"two dongles with serial {s}: only the first is served, set unique serials with rtl_eeprom")
                    self.warned.add(s)
                continue
            if s.isdigit() and s not in self.warned:
                log(f"serial {s} is only digits: librtlsdr may read it as an index, better rename it (rtl_eeprom -s)")
                self.warned.add(s)
            seen[s] = d
        for s in list(self.procs):
            if s not in seen:
                self.stop(s, "unplugged")
        stall_s = float(self.cfg["STALL_S"] or 0)
        stalled = stalled_ports(stall_s * 1000) if stall_s > 0 and self.procs else set()
        for s, d in seen.items():
            port = self.port_for(s)
            if port in stalled and s in self.procs:
                self.stop(s, f"client stopped answering for over {stall_s:g} s, restart so it can reconnect")
                self.started.pop(s, None)
            d["port"] = port
            p = self.procs.get(s)
            if p is not None and p.poll() is not None:
                log(f"rtl_tcp {s} exited with {p.returncode}")
                self.procs.pop(s)
                p = None
            if p is None and time.time() - self.started.get(s, 0) > 5:    # no restart storm
                self.start(s, port)
            d["running"] = s in self.procs and self.procs[s].poll() is None
        with self.lock:
            self.state = dongles

    def run(self):
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(SystemExit))
        threading.Thread(target=self.http, daemon=True).start()
        try:
            while True:
                try:
                    self.tick()
                    self.sample()
                except Exception as e:      # never die on one bad scan
                    log(f"scan error: {e}")
                time.sleep(float(self.cfg["SCAN_S"]))
        finally:
            for s in list(self.procs):
                self.stop(s, "service stop")

    def http(self):
        mgr = self

        class H(BaseHTTPRequestHandler):
            def reply(self, code, obj):
                body = json.dumps(obj, indent=1).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split("?")[0]
                if path in ("/", "/dongles.json"):
                    with mgr.lock:
                        self.reply(200, {"host": host_name(), "dongles": mgr.state})
                elif path == "/status.json":
                    self.reply(200, mgr.status(self.client_address[0]))
                else:
                    self.send_error(404)

            def do_POST(self):
                path = self.path.split("?")[0]
                if path not in ("/power", "/restart", "/update"):
                    self.send_error(404)
                    return
                # a web page cannot send JSON here without CORS (which this server does not allow), only a program
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    self.reply(400, {"error": "Content-Type must be application/json"})
                    return
                caller = self.client_address[0]
                try:
                    private = ipaddress.ip_address(caller).is_private
                except ValueError:
                    private = False
                if not private:
                    self.reply(403, {"error": "only from the local network"})
                    return
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(min(n, 1 << 20)) or b"{}")
                except ValueError:
                    body = {}
                if path == "/power":
                    self.reply(*mgr.power(str(body.get("action", "")), caller))
                elif path == "/restart":
                    self.reply(*mgr.restart_dongle(str(body.get("serial", ""))))
                else:
                    log(f"update requested by {caller}")
                    self.reply(*mgr.update(str(body.get("code", ""))))

            def log_message(self, *a):
                pass

        ThreadingHTTPServer((self.cfg["BIND"], int(self.cfg["HTTP_PORT"])), H).serve_forever()


if __name__ == "__main__":
    Manager().run()

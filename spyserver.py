"""Remote SDR on an Airspy SpyServer (sdr://host:port, default port 5555) with the same interface as RtlSdr in sdr.py.

SpyServer serves an Airspy R2 / Mini, an Airspy HF+ or an RTL-SDR to many clients over TCP. A client gets the I/Q of
a part of the band the device receives: its own centre (inside the band of the device) and its own rate (the full
rate of the device divided by 2^n, n >= the minimum decimation the server allows). Only the first client (or the only
one) may change the device centre and gain ("can control"); the others tune inside what it receives.

The VFO gets driver "spyserver" and its address in "serial": "host:port". read_async sends complex64 blocks (±1),
like the Airspy and LimeSDR drivers.

Protocol (little endian), as published by Airspy and implemented by SDR# / SDR++:
  client -> server  command: u32 type, u32 body size, body (HELLO = protocol version + client name, SET_SETTING =
                    u32 setting + u32 value)
  server -> client  message: u32 protocol id, u32 type (low 16 bits), u32 stream type, u32 sequence, u32 body size,
                    body (DEVICE_INFO, CLIENT_SYNC, then I/Q blocks while streaming is on)
"""
import socket
import struct
import threading
import time

import numpy as np

DEFAULT_PORT = 5555
PROTOCOL_VERSION = (2 << 24) | (0 << 16) | 1700
CLIENT_NAME = b"RADIMCOM"
CONNECT_TIMEOUT_S = 5.0
READ_TIMEOUT_S = 6.0
RCVBUF = 4 << 20
MIN_RATE = 500000            # lower rates are not offered: the audio is rate / 64 (sdr.DECIM)
MAX_RATE = 2600000           # the DSP is made for up to ~2.5 MS/s (an Airspy R2 at 10 MS/s is divided down)

CMD_HELLO, CMD_GET_SETTING, CMD_SET_SETTING, CMD_PING = 0, 1, 2, 3
SET_STREAMING_MODE, SET_STREAMING_ENABLED, SET_GAIN = 0, 1, 2
SET_IQ_FORMAT, SET_IQ_FREQUENCY, SET_IQ_DECIMATION, SET_IQ_DIGITAL_GAIN = 100, 101, 102, 103
STREAM_IQ = 1
FORMAT_UINT8, FORMAT_INT16, FORMAT_INT24, FORMAT_FLOAT = 1, 2, 3, 4
MSG_DEVICE_INFO, MSG_CLIENT_SYNC, MSG_PONG, MSG_READ_SETTING = 0, 1, 2, 3
MSG_UINT8_IQ, MSG_INT16_IQ, MSG_INT24_IQ, MSG_FLOAT_IQ = 100, 101, 102, 103
DEVICE_TYPES = {1: "Airspy One", 2: "Airspy HF+", 3: "RTL-SDR"}
MAX_BODY = 1 << 22


def split_addr(addr):
    """'sdr://host:5555', 'host:5555' or 'host' -> (host, port)."""
    a = (addr or "").strip()
    if "://" in a:
        a = a.split("://", 1)[1]
    a = a.split("/", 1)[0].strip()
    if a.count(":") == 1:
        host, port = a.rsplit(":", 1)
        return host.strip(), int(port)
    if not a:
        raise ValueError("empty SpyServer address")
    return a, DEFAULT_PORT


def _recv_exact(sock, n):
    buf = bytearray(n)
    view = memoryview(buf)
    got = 0
    while got < n:
        k = sock.recv_into(view[got:], n - got)
        if k == 0:
            raise RuntimeError("the SpyServer closed the connection")
        got += k
    return buf


class _Conn:
    """One connection: hello, device info and client sync, commands, messages."""

    def __init__(self, addr, timeout=CONNECT_TIMEOUT_S):
        self.host, self.port = split_addr(addr)
        self.where = f"{self.host}:{self.port}"
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        except OSError as e:
            raise RuntimeError(f"cannot connect to the SpyServer {self.where} ({e})")
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RCVBUF)
        except OSError:
            pass
        self.lock = threading.Lock()
        self.info = None
        self.sync = None
        self.command(CMD_HELLO, struct.pack("<I", PROTOCOL_VERSION) + CLIENT_NAME)
        end = time.time() + timeout
        while (self.info is None or self.sync is None) and time.time() < end:
            self.read_message()
        if self.info is None or self.sync is None:
            self.close()
            raise RuntimeError(f"{self.where} did not answer like a SpyServer")

    def command(self, ctype, body=b""):
        with self.lock:
            self.sock.sendall(struct.pack("<II", ctype, len(body)) + body)

    def setting(self, setting, value):
        self.command(CMD_SET_SETTING, struct.pack("<II", setting, int(value) & 0xFFFFFFFF))

    def read_message(self):
        """-> (type, body). DEVICE_INFO and CLIENT_SYNC are kept in self.info / self.sync."""
        _pid, mtype, _stream, _seq, size = struct.unpack("<5I", _recv_exact(self.sock, 20))
        if size > MAX_BODY:
            raise RuntimeError(f"SpyServer {self.where}: a message of {size} bytes, the stream is broken")
        body = _recv_exact(self.sock, size) if size else bytearray()
        mtype &= 0xFFFF
        if mtype == MSG_DEVICE_INFO and len(body) >= 48:
            f = struct.unpack("<12I", body[:48])
            self.info = dict(zip(("type", "serial", "max_rate", "max_bw", "decim_stages", "gain_stages", "max_gain",
                                  "min_hz", "max_hz", "resolution", "min_decim", "forced_format"), f))
        elif mtype == MSG_CLIENT_SYNC and len(body) >= 36:
            f = struct.unpack("<9I", body[:36])
            self.sync = dict(zip(("can_control", "gain", "device_hz", "iq_hz", "fft_hz", "iq_min_hz", "iq_max_hz",
                                  "fft_min_hz", "fft_max_hz"), f))
        return mtype, body

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def rates(info):
    """[(rate of the VFO, decimation on the server, upsampling here)], from the highest. The rates the server allows
    within MIN_RATE..MAX_RATE; a server that allows only less (an Airspy HF+ shared over the internet, e.g. 228 kS/s)
    gets its highest rate upsampled here by 2^n to at least MIN_RATE: the DSP of RADIMCOM needs that (audio = rate / 64),
    the band shown is then wider than what arrives (the edges stay empty)."""
    out = []
    for d in range(info["min_decim"], info["decim_stages"] + 1):
        r = info["max_rate"] >> d
        if MIN_RATE <= r <= MAX_RATE:
            out.append((r, d, 1))
    if not out:
        r, up = info["max_rate"] >> info["min_decim"], 1
        while r and r * up < MIN_RATE:
            up *= 2
        if r and r * up <= MAX_RATE:
            out.append((r * up, info["min_decim"], up))
    return out


def device_name(info):
    return DEVICE_TYPES.get(info["type"], "SDR")


def probe(addr, timeout=CONNECT_TIMEOUT_S):
    """Device info, client sync and the offered rates of a SpyServer (connects for a moment)."""
    c = _Conn(addr, timeout)
    try:
        plan = rates(c.info)
        return {"info": c.info, "sync": c.sync, "rates": [r for r, _, _ in plan], "net_rate": plan[0][0] // plan[0][2] if plan else None,
                "name": device_name(c.info), "where": c.where}
    finally:
        c.close()


def list_devices(servers, timeout=CONNECT_TIMEOUT_S):
    """For the SDR setup: [{serial (= host:port), name, server, error?}] of the given sdr:// addresses."""
    out = []
    for server in servers or []:
        try:
            p = probe(server, timeout)
            i, s = p["info"], p["sync"]
            if not p["rates"]:
                raise RuntimeError(f"the server allows only {i['max_rate'] >> i['min_decim']} S/s, "
                                   f"RADIMCOM needs at least {MIN_RATE} S/s")
            ctl = "can control" if s["can_control"] else "shared: tunes only inside the band of the device"
            net = p["net_rate"]
            bw = f"{net / 1e3:g} kHz band" if net < MIN_RATE else f"up to {net / 1e6:g} MS/s"
            out.append({"serial": p["where"], "server": server, "name": f"SpyServer {p['name']} · {p['where']} · {bw} · {ctl}"})
        except Exception as e:  # noqa: BLE001 - any failure is shown at that server
            out.append({"serial": "", "name": "", "server": server, "error": str(e)})
    return out


def rates_for(addr, timeout=CONNECT_TIMEOUT_S):
    """The rates a VFO on this server can use (for its SAMPLE RATE list); () when the server does not answer."""
    try:
        return tuple(probe(addr, timeout)["rates"])
    except Exception:  # noqa: BLE001
        return ()


class SpyServerSdr:
    """SpyServer client; the methods match RtlSdr (sdr.py)."""

    has_bias_tee = False
    has_rtl_agc = False

    def __init__(self, block, addr):
        self.block = block
        self.c = _Conn(addr)
        self.where = self.c.where
        i = self.c.info
        self.tuner_name = device_name(i)
        self.tuner_min_hz = float(i["min_hz"])
        self.tuner_max_hz = float(i["max_hz"])
        self.can_control = bool(self.c.sync["can_control"])
        self.gains = list(range(i["max_gain"] + 1)) if self.can_control else []
        self.rates = rates(i)
        self.rate = None
        self.up = 1
        self.freq = None
        self.ppm = 0
        self.lost = 0
        self._stop = False
        self._seq = None
        fmt = i["forced_format"] or FORMAT_INT16
        self.fmt = fmt if fmt in (FORMAT_UINT8, FORMAT_INT16, FORMAT_FLOAT) else FORMAT_INT16
        self.c.setting(SET_STREAMING_MODE, STREAM_IQ)
        self.c.setting(SET_IQ_FORMAT, self.fmt)

    def set_sample_rate(self, rate):
        rate = int(rate)
        plan = next((p for p in self.rates if p[0] == rate), None)
        if plan is None:
            ok = ", ".join(f"{r / 1e6:g}" for r, _, _ in self.rates) or "none"
            raise RuntimeError(f"SpyServer {self.where}: {rate / 1e6:g} MS/s is not offered (it allows {ok} MS/s)")
        self.c.setting(SET_IQ_DECIMATION, plan[1])
        self.rate = rate
        self._set_up(plan[2])

    def _set_up(self, up):
        """Upsampling by up (1 = none): a low-pass FIR, run over the stream with its history (overlap)."""
        self.up = up
        if up > 1:
            from scipy.signal import firwin
            self._h = (firwin(16 * up + 1, 0.9 / up) * up).astype(np.float32)
            self._hist = np.zeros(-(-len(self._h) // up), np.complex64)

    def _upsample(self, x):
        from scipy.signal import upfirdn
        L = len(self._hist)
        buf = np.concatenate((self._hist, x))
        self._hist = buf[-L:]
        y = upfirdn(self._h, buf, self.up)
        return y[L * self.up:(L + len(x)) * self.up].astype(np.complex64)

    def set_center_freq(self, hz):
        if self.freq != float(hz):
            self.freq = float(hz)
            self._tune()

    def _tune(self):
        hz = int(round(self.freq * (1 + self.ppm * 1e-6)))      # no ppm on the server: shift the centre
        s = self.c.sync or {}
        if not self.can_control and s.get("iq_max_hz") and not s["iq_min_hz"] <= hz <= s["iq_max_hz"]:
            raise RuntimeError(f"SpyServer {self.where} is shared: it tunes only {s['iq_min_hz'] / 1e6:.3f}–"
                               f"{s['iq_max_hz'] / 1e6:.3f} MHz now (another client controls the device)")
        self.c.setting(SET_IQ_FREQUENCY, hz)

    def set_gain(self, gain):
        if not self.can_control or gain in ("auto", "", None):
            return                     # no AGC setting in the protocol; a shared server keeps its gain
        self.c.setting(SET_GAIN, max(0, min(len(self.gains) - 1, int(round(float(gain))))))

    def set_bias_tee(self, on):
        pass

    def set_rtl_agc(self, on):
        pass

    def set_ppm(self, ppm):
        self.ppm = int(ppm)
        if self.freq is not None:
            self._tune()

    def reset_buffer(self):
        pass

    def read_async(self, on_block):
        """Blocks until cancel_async (or a network error): blocks of self.block complex64 samples."""
        self.c.sock.settimeout(READ_TIMEOUT_S)
        self.c.setting(SET_STREAMING_ENABLED, 1)
        buf = np.empty(self.block, np.complex64)
        fill = 0
        try:
            while not self._stop:
                try:
                    mtype, body = self.c.read_message()
                except socket.timeout:
                    if self._stop:
                        return
                    raise RuntimeError(f"SpyServer {self.where}: no data for {READ_TIMEOUT_S:g} s")
                except (OSError, RuntimeError) as e:
                    if self._stop:
                        return
                    raise RuntimeError(f"SpyServer {self.where}: {e}")
                if mtype == MSG_INT16_IQ:
                    x = np.frombuffer(body, "<i2").astype(np.float32) * (1 / 32768)
                elif mtype == MSG_UINT8_IQ:
                    x = (np.frombuffer(body, np.uint8).astype(np.float32) - 127.5) * (1 / 128)
                elif mtype == MSG_FLOAT_IQ:
                    x = np.frombuffer(body, "<f4")
                else:
                    continue           # status, sync, pong
                src = np.ascontiguousarray(x[: len(x) // 2 * 2], np.float32).view(np.complex64)
                if self.up > 1:
                    src = self._upsample(src)
                pos = 0
                while pos < len(src):
                    n = min(self.block - fill, len(src) - pos)
                    buf[fill:fill + n] = src[pos:pos + n]
                    fill += n
                    pos += n
                    if fill == self.block:
                        on_block(buf)
                        buf = np.empty(self.block, np.complex64)
                        fill = 0
        finally:
            try:
                self.c.setting(SET_STREAMING_ENABLED, 0)
            except OSError:
                pass

    def cancel_async(self):
        self._stop = True
        try:
            self.c.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def close(self):
        self._stop = True
        self.c.close()

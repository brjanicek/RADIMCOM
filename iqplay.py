"""IQ PLAYER: an IQ recording played through the VFO instead of its dongle, as a "virtual dongle".
Thanks to Dano OM1ATS for the idea.

The player has the interface of a device (RtlSdr, LimeSdr, ChainedSdr …), so the whole receiver works on the file as
on the air: the spectrum and waterfall, tuning inside the recorded band, every mode, NB / DNR / filters, the decoders
of the audio and of the raw IQ, REC. Like a chained VFO (iqshare.py) it hands its blocks to the receiver as (metadata,
samples): the centre and the sample rate are the file's, the VFO can tune only inside them.

Files:
  * WAV, 2 channels (I left, Q right), 8 bit unsigned, 16 bit signed or 32 bit float: REC IQ and PRE-REC of RADIMCOM,
    SDR#, SDR++, HDSDR … The centre from the name (…_<Hz>Hz_…) or from the "auxi" chunk (SpectraVue / HDSDR).
  * raw samples without a header, the format by the extension: .cu8 / .u8 (rtl_sdr), .cs8 / .s8 / .c8 / .iq
    (hackrf_transfer), .c16 / .cs16 / .s16 (HackRF PortaPack CAPTURE, 16 bit signed), .cf32 / .fc32 / .cfile / .raw
    (GNU Radio, gqrx: 32 bit float); the centre and the rate from the name (433.92M_2M, …Hz…, …sps…, gqrx_…_fc),
    from a .txt beside the file (PortaPack: center_frequency= / sample_rate=) or from SigMF (.sigmf-meta).
    What cannot be found out is entered in the OPEN window.

The DSP is made for ~0.9 to 2.6 MS/s (the audio is the rate / sdr.DECIM): a faster file is divided down by a whole
number (HackRF 10 / 20 MS/s -> 2.5 MS/s, only the middle of its band stays), a slower one is multiplied by a power of
two (PortaPack 500 kS/s -> 1 MS/s). The blocks go out in real time; PAUSE, a jump (seek) and LOOP work at any time.

When a file starts, the whole setting of the VFO is kept aside; it is also what is saved in the settings meanwhile.
BACK TO VFO opens the dongle again with its frequency, centre, sample rate and gain, then puts back every other setting
changed meanwhile (mode, filters, NB / DNR …, decoders) through /api/set, so decoders start and stop as from the page.
"""
import copy
import json
import math
import os
import re
import string
import struct
import threading
import time

import numpy as np

MIN_RATE = 900000            # below: upsampled ×2, ×4 … (the audio is fs / 64)
MAX_RATE = 2600000           # above: divided down by a whole number
BLOCK = 131072               # output samples per block (sdr.READ_SAMPLES)
# (format, bytes of one complex sample)
FORMATS = {"u8": 2, "s8": 2, "s16": 4, "f32": 8}
FORMAT_NAMES = {"u8": "8 bit unsigned (rtl_sdr .cu8)", "s8": "8 bit signed (HackRF .cs8)",
                "s16": "16 bit signed (PortaPack .c16)", "f32": "32 bit float (GNU Radio .cf32)"}
EXT_FORMAT = {".cu8": "u8", ".u8": "u8", ".complex16u": "u8",
              ".cs8": "s8", ".s8": "s8", ".c8": "s8", ".iq": "s8", ".complex16s": "s8",
              ".c16": "s16", ".cs16": "s16", ".s16": "s16", ".complex32s": "s16",
              ".cf32": "f32", ".fc32": "f32", ".cfile": "f32", ".raw": "f32", ".complex": "f32"}
SIGMF_FORMAT = {"cu8": "u8", "ci8": "s8", "ci16_le": "s16", "cf32_le": "f32"}
IQ_EXT = (".wav",) + tuple(EXT_FORMAT) + (".sigmf-data", ".sigmf-meta")
# put back by the receiver thread itself (the dongle state the file's blocks overwrite)
SAVED_KEYS = ("tune_hz", "center_hz", "sample_rate", "gain", "rtl_agc", "smart_agc", "zoom")
# never sent back through /api/set: the dongle keys above and what only SETTINGS › SDR SOURCES changes
NO_RESTORE = set(SAVED_KEYS) | {"device", "driver", "serial", "chain", "vfo", "net_pause", "tx_enabled", "lo_offset_hz", "view_hz"}


# ---------- what a file is ----------

def _num(txt, unit):
    return float(txt) * {"": 1, "k": 1e3, "m": 1e6, "g": 1e9}[(unit or "").lower()]


def from_name(name):
    """(centre Hz or None, rate S/s or None, format or None) read from the file name."""
    stem = os.path.splitext(os.path.basename(name))[0]
    centre = rate = fmt = None
    m = re.search(r"gqrx_\d{8}_\d{6}_(\d+)_(\d+)_fc", stem)
    if m:
        return float(m.group(1)), float(m.group(2)), "f32"
    m = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)\s*([kMG]?)Hz", stem, re.I)
    if m:
        centre = _num(m.group(1), m.group(2))
    m = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)\s*([kM]?)(?:S/?s|sps)(?![a-z])", stem, re.I)
    if m:
        rate = _num(m.group(1), m.group(2))
    if centre is None or rate is None:
        # rtl_433 / URH style: …_433.92M_250k… = the centre, then the rate
        bare = [_num(a, b) for a, b in re.findall(r"(?:^|[_\-\s])(\d+(?:\.\d+)?)([kMG])(?=$|[_\-\s.])", stem)]
        if centre is None and bare:
            centre = bare.pop(0)
        if rate is None and bare:
            rate = bare[0]
    return centre, rate, fmt


def _sidecar_txt(path):
    """PortaPack CAPTURE: <name>.TXT beside the .C16 with center_frequency= and sample_rate=."""
    stem = os.path.splitext(path)[0]
    for ext in (".txt", ".TXT", ".Txt"):
        p = stem + ext
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    kv = dict(line.split("=", 1) for line in f.read(4096).splitlines() if "=" in line)
                kv = {k.strip().lower(): v.strip() for k, v in kv.items()}
                return (float(kv["center_frequency"]) if kv.get("center_frequency") else None,
                        float(kv["sample_rate"]) if kv.get("sample_rate") else None)
            except (OSError, ValueError):
                pass
    return None, None


def _sigmf(path):
    """(data path, centre, rate, format) of a SigMF recording (.sigmf-meta / .sigmf-data), or None."""
    stem = re.sub(r"\.sigmf-(meta|data)$", "", path, flags=re.I)
    meta = stem + ".sigmf-meta"
    if not os.path.isfile(meta):
        return None
    try:
        with open(meta, encoding="utf-8") as f:
            j = json.load(f)
        g = j.get("global", {})
        caps = j.get("captures") or [{}]
        dt = str(g.get("core:datatype", "")).lower()
        return (stem + ".sigmf-data", caps[0].get("core:frequency"), g.get("core:sample_rate"),
                SIGMF_FORMAT.get(dt) or SIGMF_FORMAT.get(dt.replace("_be", "_le")))
    except (OSError, ValueError, AttributeError):
        return None


def _wav(path, f):
    """WAV / RF64: {fmt, fs, offset, length, centre (auxi)}; ValueError if it is not a 2-channel IQ WAV."""
    head = f.read(12)
    if len(head) < 12 or head[:4] not in (b"RIFF", b"RF64") or head[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    size = os.fstat(f.fileno()).st_size
    out = {"centre": None}
    while True:
        h = f.read(8)
        if len(h) < 8:
            raise ValueError("WAV without a data chunk")
        cid, n = h[:4], struct.unpack("<I", h[4:])[0]
        if cid == b"fmt ":
            b = f.read(n)
            tag, ch, rate, _, _, bits = struct.unpack("<HHIIHH", b[:16])
            if tag == 0xFFFE and len(b) >= 26:
                tag = struct.unpack("<H", b[24:26])[0]      # WAVE_FORMAT_EXTENSIBLE: the sub-format
            if ch != 2:
                raise ValueError(f"the WAV has {ch} channel(s), an IQ WAV has 2 (I and Q)")
            fmt = {(1, 8): "u8", (1, 16): "s16", (3, 32): "f32"}.get((tag, bits))
            if not fmt:
                raise ValueError(f"WAV with {bits} bit samples (format {tag}) is not supported (8, 16 bit or 32 bit float)")
            out.update(fmt=fmt, fs=float(rate))
        elif cid == b"auxi":
            b = f.read(n)
            if len(b) >= 36:
                cf = struct.unpack("<I", b[32:36])[0]
                out["centre"] = float(cf) if cf else None
        elif cid == b"data":
            off = f.tell()
            # a file still being written, cut off or over 4 GB: the rest of the file
            length = size - off if n in (0, 0xFFFFFFFF) or off + n > size else n
            out.update(offset=off, length=length)
            if "fmt" not in out:
                raise ValueError("WAV without a fmt chunk")
            return out
        else:
            f.seek(n, 1)
        if n % 2:
            f.seek(1, 1)


def probe(path):
    """What the file is: {path, name, size, fmt, fs, centre, offset, length, secs, known: {...}}; ValueError if not."""
    path = os.path.abspath(path)
    sig = _sigmf(path) if path.lower().endswith((".sigmf-meta", ".sigmf-data")) else None
    if sig:
        path = sig[0]
    if not os.path.isfile(path):
        raise ValueError("no such file")
    size = os.path.getsize(path)
    ext = os.path.splitext(path)[1].lower()
    n_c, n_r, n_f = from_name(path)
    info = {"path": path, "name": os.path.basename(path), "size": size, "offset": 0, "length": size,
            "fmt": None, "fs": None, "centre": None, "wav": False}
    if ext == ".wav":
        with open(path, "rb") as f:
            w = _wav(path, f)
        info.update(fmt=w["fmt"], fs=w["fs"], offset=w["offset"], length=w["length"], wav=True,
                    centre=n_c or w["centre"])          # the name first: SDR# keeps the auxi of the first file
    elif sig:
        info.update(centre=sig[1], fs=sig[2], fmt=sig[3])
    else:
        t_c, t_r = _sidecar_txt(path)
        info.update(fmt=EXT_FORMAT.get(ext) or n_f, centre=t_c or n_c, fs=t_r or n_r)
    if info["centre"] is None and n_c:
        info["centre"] = n_c
    if info["fs"] is None and n_r:
        info["fs"] = n_r
    return _finish(info)


def _finish(info):
    fb = FORMATS.get(info["fmt"])
    info["secs"] = round(info["length"] / fb / info["fs"], 1) if fb and info["fs"] else None
    info["ready"] = bool(fb and info["fs"] and info["centre"] is not None)
    return info


def rate_plan(fs):
    """(down, up) so that fs × up / down is in the range of the DSP."""
    if fs > MAX_RATE:
        return math.ceil(fs / MAX_RATE), 1
    up = 1
    while fs * up < MIN_RATE:
        up *= 2
    return 1, up


# ---------- the virtual dongle ----------

class IqFilePlayer:
    """Plays one file in real time; the interface of a device for sdr.Receiver."""

    gains = []
    has_bias_tee = False
    has_rtl_agc = False
    usb_name = "IQ file"

    def __init__(self, info):
        if not info.get("ready"):
            raise ValueError("the centre frequency, the sample rate and the sample format of the file are needed")
        self.info = info
        self.path, self.fmt, self.fs_in = info["path"], info["fmt"], float(info["fs"])
        self.frame = FORMATS[self.fmt]
        self.offset = int(info["offset"])
        self.total = int(info["length"]) // self.frame          # complex samples in the file
        self.centre = float(info["centre"])
        self.down, self.up = rate_plan(self.fs_in)
        self.fs = self.fs_in * self.up / self.down
        self.n_in = BLOCK * self.down // self.up                 # file samples per block
        self.pos = 0
        self.paused = False
        self.loop = False
        self.ended = False
        self.error = ""
        self.lock = threading.Lock()
        self.seek_to = None
        self._cancel = False
        self.scale = self._scale()
        self._filt = self._history = None
        self._make_filter()
        self.meta = {"center_hz": self.centre, "lo": 0.0, "fs": self.fs}

    def _scale(self):
        """s16: PortaPack writes the 8 bit samples of the HackRF into 16 bits; a small range is taken as 8 bit."""
        if self.fmt == "u8":
            return 1 / 127.5
        if self.fmt == "s8":
            return 1 / 128
        if self.fmt == "s16":
            try:
                with open(self.path, "rb") as f:
                    f.seek(self.offset)
                    x = np.frombuffer(f.read(min(self.total, 1 << 20) * 4), "<i2")
                peak = int(np.abs(x.astype(np.int32)).max()) if len(x) else 0
            except OSError:
                peak = 32768
            return 1 / 128 if 0 < peak <= 256 else 1 / 32768
        return 1.0

    def _make_filter(self):
        if self.down == 1 and self.up == 1:
            return
        from scipy.signal import firwin
        k = max(self.down, self.up)
        self._filt = (firwin(16 * k + 1, 0.9 / k) * self.up).astype(np.float32)
        # history: whole multiples of the decimation, at least the filter length
        L = -(-len(self._filt) // self.down) * self.down if self.up == 1 else -(-len(self._filt) // self.up)
        self._hlen = L
        self._history = np.zeros(L, np.complex64)

    def _resample(self, x):
        if self._filt is None:
            return x
        from scipy.signal import upfirdn
        L = self._hlen
        buf = np.concatenate((self._history, x))
        self._history = buf[-L:]
        if self.up > 1:
            y = upfirdn(self._filt, buf, self.up)
            return y[L * self.up:(L + len(x)) * self.up].astype(np.complex64)
        y = upfirdn(self._filt, buf, 1, self.down)
        return y[L // self.down:(L + len(x)) // self.down].astype(np.complex64)

    def _convert(self, b):
        if self.fmt == "u8":
            x = np.frombuffer(b, np.uint8).astype(np.float32) - np.float32(127.5)
        elif self.fmt == "s8":
            x = np.frombuffer(b, np.int8).astype(np.float32)
        elif self.fmt == "s16":
            x = np.frombuffer(b, "<i2").astype(np.float32)
        else:
            x = np.frombuffer(b, "<f4").astype(np.float32)
        if self.scale != 1.0:
            x *= np.float32(self.scale)
        return x[: len(x) // 2 * 2].view(np.complex64)

    # ---------- control (web page) ----------
    def control(self, pause=None, seek=None, loop=None):
        with self.lock:
            if pause is not None:
                self.paused = bool(pause)
                if not self.paused and self.ended:
                    self.seek_to, self.ended = 0, False   # PLAY at the end: from the start
            if seek is not None:
                self.seek_to = max(0, min(self.total - 1, int(float(seek) * self.fs_in)))
                self.ended = False
            if loop is not None:
                self.loop = bool(loop)

    def state(self):
        i = self.info
        return {"name": i["name"], "path": i["path"], "pos": round(self.pos / self.fs_in, 2),
                "secs": round(self.total / self.fs_in, 2), "paused": self.paused, "ended": self.ended,
                "loop": self.loop, "fs_file": self.fs_in, "fs": self.fs, "centre": self.centre, "fmt": self.fmt,
                "down": self.down, "up": self.up, "error": self.error}

    # ---------- the device interface ----------
    def set_sample_rate(self, rate): pass
    def set_center_freq(self, hz): pass
    def set_gain(self, gain): pass
    def set_rtl_agc(self, on): pass
    def set_bias_tee(self, on): pass
    def set_ppm(self, ppm): pass

    def reset_buffer(self):
        self._cancel = False                     # called by the receiver before each read_async

    def cancel_async(self):
        self._cancel = True

    def close(self):
        pass                                     # the file is open only inside read_async

    def read_async(self, on_block):
        """Blocks until cancel_async; each block goes to on_block as (metadata, complex64 samples), in real time."""
        try:
            f = open(self.path, "rb")
        except OSError as e:
            self.error, self.paused = f"cannot open the file: {e}", True
            while not self._cancel:
                time.sleep(0.1)
            return
        with f:
            t_next = time.monotonic()
            jumped = True
            while not self._cancel:
                with self.lock:
                    if self.seek_to is not None:
                        self.pos, self.seek_to, jumped = self.seek_to, None, True
                    hold = self.paused or self.ended
                if hold:
                    time.sleep(0.05)
                    t_next = time.monotonic()
                    continue
                if jumped:
                    f.seek(self.offset + self.pos * self.frame)
                    if self._history is not None:
                        self._history[:] = 0
                    jumped = False
                n = min(self.n_in, self.total - self.pos)
                b = f.read(n * self.frame) if n > 0 else b""
                if len(b) < self.frame:
                    with self.lock:
                        if self.loop and self.total > 0:
                            self.seek_to = 0
                        else:
                            self.ended = True
                    continue
                x = self._convert(b)
                self.pos += len(x)
                if len(x) < self.n_in:                 # the end of the file: the receiver takes only whole blocks
                    x = np.concatenate((x, np.zeros(self.n_in - len(x), np.complex64)))
                on_block((self.meta, self._resample(x)))
                t_next += len(x) / self.fs_in
                wait = t_next - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                elif wait < -1.0:
                    t_next = time.monotonic()          # the PC fell behind: no rush to catch up


# ---------- the VFO side ----------

def start_tune(player, tune_hz):
    """The VFO starts on the centre frequency of the file (from its name, auxi, .TXT or SigMF)."""
    return player.centre


def saved_cfg(cfg, receiver):
    """The settings to save: while a file plays, the VFO's settings as they were before it (BACK TO VFO puts them back)."""
    snap = getattr(receiver, "iq_snapshot", None)
    if receiver.player is None or not snap:
        return cfg
    return snap


def _drives():
    return [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")] if os.name == "nt" else ["/"]


def browse(folder):
    """A folder of the disk for the OPEN window: {dir, parent, dirs: [name], files: [{name, size}]}; "" = the drives."""
    if not folder:
        return {"dir": "", "parent": None, "dirs": _drives(), "files": []}
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise ValueError("no such folder")
    dirs, files = [], []
    with os.scandir(folder) as it:
        for e in it:
            try:
                if e.is_dir():
                    if not e.name.startswith((".", "$")):
                        dirs.append(e.name)
                elif e.name.lower().endswith(IQ_EXT):
                    files.append({"name": e.name, "size": e.stat().st_size})
            except OSError:
                pass
    parent = os.path.dirname(folder)
    return {"dir": folder, "parent": "" if parent == folder else parent,
            "dirs": sorted(dirs, key=str.lower), "files": sorted(files, key=lambda x: x["name"].lower())}


def register(app, receiver, recorder, on_change):
    """/api/iqplay…: probe, start, control and stop the playback of this VFO, browse the disk for a file.
    on_change() saves the settings (and sends the state)."""
    from flask import jsonify, request

    def path_of(body):
        if body.get("rel") is not None:
            return recorder.resolve(str(body["rel"]))        # a recording of the RECORDINGS tab
        p = str(body.get("path") or "").strip().strip('"')
        if not p:
            raise ValueError("no file given")
        return p

    def with_overrides(info, body):
        for k, conv in (("centre", float), ("fs", float)):
            if body.get(k) not in (None, ""):
                info[k] = conv(body[k])
        if body.get("fmt") in FORMATS and not info["wav"]:
            info["fmt"] = body["fmt"]
        return _finish(info)

    @app.route("/api/iqplay/browse", methods=["GET"])
    def api_iqplay_browse():
        try:
            return jsonify(browse(request.args.get("dir", "")))
        except (OSError, ValueError) as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/iqplay/probe", methods=["POST"])
    def api_iqplay_probe():
        body = request.get_json(force=True, silent=True) or {}
        try:
            return jsonify(dict(with_overrides(probe(path_of(body)), body), formats=FORMAT_NAMES))
        except (OSError, ValueError) as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/iqplay/start", methods=["POST"])
    def api_iqplay_start():
        body = request.get_json(force=True, silent=True) or {}
        try:
            info = with_overrides(probe(path_of(body)), body)
            player = IqFilePlayer(info)
        except (OSError, ValueError, ImportError) as e:
            return jsonify({"error": str(e)}), 400
        player.loop = bool(body.get("loop", False))
        c = receiver.cfg
        if receiver.player is None:
            # the whole setting of the VFO before the file (another file meanwhile keeps this one)
            receiver.iq_snapshot = copy.deepcopy(c)
            receiver.iq_saved = {k: copy.deepcopy(c[k]) for k in SAVED_KEYS if k in c}
        tune = start_tune(player, c["tune_hz"])
        receiver.player = player
        receiver.update({"tune_hz": tune, "reset": True})
        receiver._wake.set()
        print(f"IQ PLAYER: {info['name']} ({info['fmt']}, {info['fs'] / 1e6:g} MS/s"
              f"{f' -> {player.fs / 1e6:g} MS/s' if player.fs != info['fs'] else ''}, centre {info['centre'] / 1e6:.6f} MHz)",
              flush=True)
        on_change()
        return jsonify(player.state())

    @app.route("/api/iqplay/control", methods=["POST"])
    def api_iqplay_control():
        body = request.get_json(force=True, silent=True) or {}
        p = receiver.player
        if p is None:
            return jsonify({"error": "no IQ file is playing"}), 400
        try:
            p.control(pause=body.get("pause"), seek=body.get("seek"), loop=body.get("loop"))
        except (TypeError, ValueError) as e:
            return jsonify({"error": str(e)}), 400
        on_change()
        return jsonify(p.state())

    @app.route("/api/iqplay/stop", methods=["POST"])
    def api_iqplay_stop():
        """BACK TO VFO: the dongle opened again and the whole setting of the VFO as before the file (mode, filters,
        decoders … everything changed meanwhile)."""
        if receiver.player is None:
            return jsonify({"ok": True})
        snap = getattr(receiver, "iq_snapshot", None) or {}
        # 1. the receiver thread: the dongle state and the settings kept as tables (bandwidth and squelch by mode …)
        receiver.iq_saved = dict(receiver.iq_saved or {}, **{k: copy.deepcopy(v) for k, v in snap.items()
                                                             if isinstance(v, dict) and k not in NO_RESTORE})
        receiver.update({"iq_stop": True})
        end = time.monotonic() + 3.0
        while receiver.player is not None and time.monotonic() < end:
            time.sleep(0.02)
        # 2. every other setting that differs: through /api/set, so decoders and modes start / stop as from the page;
        #    the decoders switched off first (switching one on switches the others off)
        diff = {k: v for k, v in snap.items() if k not in NO_RESTORE and not isinstance(v, dict) and receiver.cfg.get(k) != v}
        failed = []
        client = app.test_client()
        for k in sorted(diff, key=lambda k: diff[k] is True):
            r = client.post("/api/set", json={k: diff[k]})
            if r.status_code >= 400:
                failed.append(k)
        receiver.iq_snapshot = None
        print(f"IQ PLAYER: back to the dongle{f', {len(diff)} settings put back' if diff else ''}"
              f"{f' (not: {failed})' if failed else ''}", flush=True)
        on_change()
        return jsonify({"ok": True, "restored": sorted(diff), "failed": failed})

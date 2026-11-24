"""Audio recording of one VFO to MP3 files in data/recordings, or in the folder set in SETTINGS › GENERAL › RECORDINGS.

Two independent recordings, each with its own button:
  cont     everything until it is switched off, a new file every MAX_FILE_S
  squelch  only while there is audio (open squelch), each session in its own file

The receiver thread only puts the blocks in a queue; encoding and writing to disk run in their own thread.
DAB: welle-cli already gives MP3 (DAB_KBPS), its bytes are written as they come (feed_mp3), both buttons record
everything (DAB has no squelch).
Folder: <recordings>/YYYY/MM/DD of the start (local time) for all recordings – REC, REC SQ, the scan (scanner.py)
and DAB; REC IQ (iqrec.py) in its subfolder iq. migrate() moves the flat folders of older versions there once.
File name: [<memory name>_]<frequency>MHz_<mode>_<YYYYMMDD_HHMMSS of the start>[_SQ | _SCAN].mp3
The RECORDINGS tab browses the tree (Recorder.list_dir), deletes files and folders (delete_paths) and plays them.
The folder is shared by all VFOs (data\recordings.json, read again when it changes); a file being written stays where it was opened.
"""
import calendar
import json
import os
import queue
import re
import threading
import time

import numpy as np

import memories
from paths import data

try:
    import lameenc
except ImportError:
    lameenc = None                  # installation before this feature: upgrade.bat installs it

FOLDER = data("recordings")               # default folder
SETTINGS_PATH = data("recordings.json")    # {"folder": "<absolute path>"}; missing or empty = FOLDER
BITRATE = 128         # kbps
QUALITY = 2           # LAME: 2 = high quality (about 2 % of one CPU core per recording)
MAX_FILE_S = 15 * 60  # cont: longer recordings continue in the next file
SESSION_HOLD_S = 1.0  # squelch: a closed squelch ends the session after this long, so a short dip does not split it
SESSION_MIN_S = 0.3   # squelch: a shorter session is a noise burst, its file is deleted
SILENCE_PEAK = 1      # 16-bit samples: a block up to this level is silence (a closed squelch gives exactly 0)
QUEUE_BLOCKS = 256    # about 16 s of audio
SCAN_KBPS = 64        # MP3 of the scanner (scanner.REC_KBPS, mono): for the length of a scan file
DAB_IDLE_S = 10.0     # DAB with REC SQ: the file ends when no MP3 came for this long (DAB off, no signal)
DAB_KBPS = 160        # the MP3 of welle-cli (MPEG-1 layer 3, 48 kHz): for the length of a DAB file
NAME_RE = re.compile(r"^(?:(?P<memory>.+?)_)?(?P<mhz>\d+\.\d{6})MHz_(?P<mode>[A-Z0-9]+)_(?P<start>\d{8}_\d{6})"
                     r"(?:_(?P<tag>SQ|SCAN|GRAVES))?(?:_\d+)?\.(?:mp3|wav)$")
# REC IQ (iqrec.py, SDR# style, UTC): RADIMCOM[_<VFO>]_<YYYYMMDD_HHMMSS>Z_<centre>Hz_IQ[_<tag>][_n].wav; the tag:
# PREREC (PRE-REC SAVE), GRAVES / GRAVESBAND (meteor_rec.py: the IQ of an echo, around the carrier / the whole band)
IQ_RE = re.compile(r"^RADIMCOM(?:_.+?)?_(?P<start>\d{8}_\d{6})Z_(?P<hz>\d+)Hz_IQ(?:_(?P<tag>PREREC|GRAVES|GRAVESBAND))?(?:_\d+)?\.wav$")
IQ_TAG_NAME = {"PREREC": "PRE-REC", "GRAVES": "GRAVES echo", "GRAVESBAND": "GRAVES band"}   # shown as its memory
AUDIO_EXT = (".mp3", ".wav")
TAG_SRC = {"": "rec", "SQ": "sq", "SCAN": "scan", "GRAVES": "graves"}   # tag in the file name → source shown in RECORDINGS
GRAVES_KBPS = 32      # the MP3 of a GRAVES echo (meteor_rec.MP3_KBPS, 8 kHz mono): for its length
STARS_FILE = "starred.json"   # in the root of the recordings folder: the recordings starred (★) in RECORDINGS
_stars_lock = threading.Lock()


def day_folder(root, t=None):
    """The folder of the recordings started at t (local time): <root>/YYYY/MM/DD."""
    lt = time.localtime(t)
    return os.path.join(root, f"{lt.tm_year:04d}", f"{lt.tm_mon:02d}", f"{lt.tm_mday:02d}")


_settings_cache = [None, ""]   # (mtime, size) of SETTINGS_PATH, the folder from it


def custom_folder():
    """The folder set by the user, "" = the default one."""
    try:
        st = os.stat(SETTINGS_PATH)
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return ""
    if _settings_cache[0] != key:
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                s = json.load(f)
            folder = s.get("folder") if isinstance(s, dict) else ""
        except (OSError, ValueError):
            folder = ""
        _settings_cache[:] = [key, folder if isinstance(folder, str) else ""]
    return _settings_cache[1]


def current_folder():
    return custom_folder() or FOLDER


def settings():
    """For SETTINGS › GENERAL › RECORDINGS: the folder in use, the set one ("" = default) and the default one."""
    return {"folder": current_folder(), "custom": custom_folder(), "default": FOLDER}


def save_folder(folder):
    """Sets the recordings folder ("" or the default path = the default one); creates it and checks that it can be written.
    ValueError with the reason if it cannot be used."""
    folder = (folder or "").strip().strip('"').strip()
    if folder:
        folder = os.path.expandvars(os.path.expanduser(folder))
        if not os.path.isabs(folder):
            raise ValueError("enter a full path, for example D:\\Recordings")
        folder = os.path.normpath(folder)
        if os.path.normcase(folder) == os.path.normcase(os.path.normpath(FOLDER)):
            folder = ""
    if folder:
        try:
            os.makedirs(folder, exist_ok=True)
            probe = os.path.join(folder, f".radimcom_write_test_{os.getpid()}")
            with open(probe, "wb") as f:
                f.write(b"x")
            os.remove(probe)
        except OSError as e:
            raise ValueError(f"the folder cannot be used: {e.strerror or e}") from None
    tmp = f"{SETTINGS_PATH}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"folder": folder}, f, indent=2)
    os.replace(tmp, SETTINGS_PATH)
    return settings()


def has_audio(pcm):
    x = np.frombuffer(pcm, "<i2")
    return x.size > 0 and (int(x.max()) > SILENCE_PEAK or int(x.min()) < -SILENCE_PEAK)


def memory_prefix(hz, mode):
    """Name of the memory on this frequency for the file name: "Piestany TWR" -> "Piestany_TWR_", no memory -> ""."""
    try:
        name = memories.name_at(hz, mode)
    except (OSError, ValueError, KeyError, TypeError):   # an unreadable memory file must not stop the recording
        return ""
    name = re.sub(r'[\s\\/:*?"<>|\x00-\x1f]+', "_", name).strip("_.")    # also characters Windows forbids in a file name
    return name + "_" if name else ""


def _start_text(s):
    return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[9:11]}:{s[11:13]}:{s[13:15]}"


def parse_name(name):
    """Frequency, mode, start (local time), memory name and source (rec / sq / scan / dab / iq) from a file name of a
    recording (empty for a foreign file)."""
    m = NAME_RE.match(name)
    if m:
        memory, mode = m.group("memory") or "", m.group("mode")
        return {"memory": memory.replace("_", " "), "hz": int(round(float(m.group("mhz")) * 1e6)), "mode": mode,
                "start": _start_text(m.group("start")), "src": "dab" if mode == "DAB" else TAG_SRC[m.group("tag") or ""]}
    m = IQ_RE.match(name)
    if m:                       # the IQ name is in UTC: the start shown in local time like the others
        try:
            t = time.strftime("%Y%m%d_%H%M%S", time.localtime(
                calendar.timegm(time.strptime(m.group("start"), "%Y%m%d_%H%M%S"))))
        except ValueError:
            t = m.group("start")
        return {"memory": IQ_TAG_NAME.get(m.group("tag") or "", ""), "hz": int(m.group("hz")), "mode": "IQ",
                "start": _start_text(t), "src": "iq"}
    return {"memory": "", "hz": 0, "mode": "", "start": "", "src": ""}


def start_time(name):
    """Start of a recording from its name as a Unix time (None when the name has none)."""
    s = parse_name(name)["start"]
    try:
        return time.mktime(time.strptime(s, "%Y-%m-%d %H:%M:%S")) if s else None
    except ValueError:
        return None


def wav_secs(path, size):
    """Length of a WAV file in seconds from its header; a file still being written (header not final) from its size."""
    import wave
    try:
        with wave.open(path, "rb") as w:
            rate, n, width = w.getframerate(), w.getnframes(), w.getsampwidth() * w.getnchannels()
        if rate:
            return int(max(n, (size - 44) // max(width, 1)) / rate)
    except (OSError, EOFError, wave.Error):
        pass
    return 0


RAW = object()        # Track.enc of a DAB file: MP3 bytes written as they come, no encoder


def safe_name(text):
    """A station name for a file name: letters, digits, - and ., the rest _ (empty if nothing is left)."""
    return re.sub(r"_+", "_", re.sub(r"[^\w.-]", "_", str(text or ""))).strip("_.")[:40]


class Track:
    """One recording. Only the recorder's thread touches the open file; `on` is the switch from outside."""

    def __init__(self, gated, folder):
        self.gated = gated
        self.folder = folder          # callable: the root folder of the recordings (the file goes to its YYYY/MM/DD)
        self.on = False
        self.error = ""
        self.file = ""       # file being written, otherwise the last saved one
        self.saved = 0       # files finished since the button was pressed
        self.enc = None
        self.out = None
        self.path = ""
        self.rate = 0
        self.frames = 0
        self.held = []       # squelch: silent blocks after the audio, written only if the audio returns
        self.held_frames = 0
        self.last_block = 0.0

    def _stem_folder(self, prefix, hz, mode):
        """(folder of today, file stem): <root>/YYYY/MM/DD and <prefix><MHz>MHz_<mode>_<start>[_SQ] (one time for both)."""
        t = time.time()
        folder = day_folder(self.folder(), t)
        os.makedirs(folder, exist_ok=True)
        tag = "_SQ" if self.gated else ""
        return folder, f"{prefix}{hz / 1e6:.6f}MHz_{mode}_{time.strftime('%Y%m%d_%H%M%S', time.localtime(t))}{tag}"

    def _open(self, rate, hz, mode):
        folder, stem = self._stem_folder(memory_prefix(hz, mode), hz, mode)
        path, n = os.path.join(folder, stem + ".mp3"), 1
        while os.path.exists(path):          # both recordings, or two VFOs, in the same second
            n += 1
            path = os.path.join(folder, f"{stem}_{n}.mp3")
        enc = lameenc.Encoder()
        enc.set_bit_rate(BITRATE)
        enc.set_in_sample_rate(int(round(rate)))   # LAME resamples rates that MP3 does not have
        enc.set_channels(2)
        enc.set_quality(QUALITY)
        self.out = open(path, "xb")
        self.enc, self.path, self.rate, self.frames, self.file = enc, path, rate, 0, os.path.basename(path)

    def _open_mp3(self, hz, mode, label):
        """A file for MP3 bytes as they come (DAB): no encoder, self.enc = RAW."""
        prefix = safe_name(label) + "_" if safe_name(label) else memory_prefix(hz, mode)   # the station, not the ensemble
        folder, stem = self._stem_folder(prefix, hz, mode)
        path, n = os.path.join(folder, stem + ".mp3"), 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(folder, f"{stem}_{n}.mp3")
        self.out = open(path, "xb")
        self.enc, self.path, self.rate, self.frames, self.file = RAW, path, DAB_KBPS * 125, 0, os.path.basename(path)
        self.label = label

    def write_mp3(self, chunk, hz, mode, label):
        """DAB: MP3 bytes of welle-cli; a new file every MAX_FILE_S and when the station changes."""
        self.last_block = time.monotonic()
        if self.enc is not None and (self.enc is not RAW or self.label != label):
            self.close()
        if self.enc is not None and self.frames + len(chunk) > MAX_FILE_S * self.rate:
            self.close()
        if self.enc is None:
            self._open_mp3(hz, mode, label)
        self.out.write(chunk)
        self.frames += len(chunk)              # bytes; self.rate = bytes a second

    def _encode(self, pcm):
        self.out.write(self.enc.encode(pcm))
        self.frames += len(pcm) // 4

    def close(self):
        if self.enc is None:
            return
        enc, out, self.enc, self.out = self.enc, self.out, None, None
        self.held, self.held_frames = [], 0
        frames, self.frames = self.frames, 0
        try:
            if enc is not RAW:
                out.write(enc.flush())
        finally:
            out.close()
        if self.gated and enc is not RAW and frames < SESSION_MIN_S * self.rate:
            os.remove(self.path)
            self.file = ""
        else:
            self.saved += 1

    def write(self, pcm, rate, hz, mode):
        self.last_block = time.monotonic()
        if self.enc is RAW:
            self.close()                         # DAB is over: back to the audio of the receiver
        if self.enc is not None and rate != self.rate:
            self.close()                         # one file has one sample rate
        if self.gated:
            self._write_gated(pcm, rate, hz, mode)
            return
        if self.enc is not None and self.frames + len(pcm) // 4 > MAX_FILE_S * self.rate:
            self.close()
        if self.enc is None:
            self._open(rate, hz, mode)
        self._encode(pcm)

    def _write_gated(self, pcm, rate, hz, mode):
        if has_audio(pcm):
            if self.enc is None:
                self._open(rate, hz, mode)
            for block in self.held:              # the pause inside the session stays in the file
                self._encode(block)
            self.held, self.held_frames = [], 0
            self._encode(pcm)
        elif self.enc is not None:
            self.held.append(pcm)
            self.held_frames += len(pcm) // 4
            if self.held_frames >= SESSION_HOLD_S * self.rate:
                self.close()

    def idle(self):
        """No blocks are coming (a decoder muted the audio, band of the owner VFO left): the session is over."""
        hold = DAB_IDLE_S if self.enc is RAW else SESSION_HOLD_S
        if self.gated and self.enc is not None and time.monotonic() - self.last_block > hold:
            self.close()

    def fail(self, e):
        self.on, self.error = False, f"Recording stopped: {e}"
        print(self.error, flush=True)
        try:
            self.close()
        except (OSError, RuntimeError):
            pass

    def state(self):
        enc, rate, frames = self.enc, self.rate, self.frames
        # active: audio goes into the file now -> the REC blinks. REC: from the press on (also before the first block
        # opens the file); REC SQ: only while the squelch is open, not in the pause held after it
        active = enc is not None and (enc is RAW or not self.held_frames) if self.gated else self.on
        return {"on": self.on, "open": enc is not None, "active": active, "file": self.file, "saved": self.saved,
                "secs": int(frames / rate) if enc is not None and rate else 0, "error": self.error}


class Recorder:
    def __init__(self, folder=None):
        self.fixed_folder = folder    # None = the folder of the settings (tests give their own)
        self.tracks = {"cont": Track(False, lambda: self.folder), "squelch": Track(True, lambda: self.folder)}
        self.q = queue.Queue(maxsize=QUEUE_BLOCKS)
        self.dropped = 0
        threading.Thread(target=self._run, daemon=True, name="recorder").start()

    def set(self, kind, on):
        """Button of a recording; ValueError if it cannot be started."""
        t = self.tracks[kind]
        if on and not t.on:
            if lameenc is None:
                raise ValueError("MP3 encoder is missing: run upgrade.bat")
            t.error, t.file, t.saved = "", "", 0
        t.on = bool(on)

    def feed_mp3(self, chunk, hz, label):
        """DAB: MP3 bytes of the station from welle-cli (the DAB thread of app.py); never blocks."""
        if not any(t.on for t in self.tracks.values()):
            return
        try:
            self.q.put_nowait(("mp3", chunk, hz, label))
        except queue.Full:
            self.dropped += 1

    def feed(self, pcm, rate, hz, mode):
        """16-bit stereo block from the receiver thread; never blocks it."""
        if not any(t.on for t in self.tracks.values()):
            return
        try:
            self.q.put_nowait((pcm, rate, hz, mode))
        except queue.Full:
            self.dropped += 1                    # the disk does not keep up

    def _run(self):
        while True:
            try:
                block = self.q.get(timeout=0.25)
            except queue.Empty:
                block = None
            for t in self.tracks.values():
                try:
                    if not t.on:
                        t.close()
                    elif block and block[0] == "mp3":
                        t.write_mp3(block[1], block[2], "DAB", block[3])
                    elif block:
                        t.write(*block)
                    else:
                        t.idle()
                except (OSError, RuntimeError) as e:
                    t.fail(e)

    def stop_all(self, wait_s=2.0):
        """Closes the files properly when the program ends."""
        for t in self.tracks.values():
            t.on = False
        end = time.monotonic() + wait_s
        while any(t.enc is not None for t in self.tracks.values()) and time.monotonic() < end:
            time.sleep(0.02)

    @property
    def folder(self):
        return self.fixed_folder or current_folder()

    def state(self):
        return dict({kind: t.state() for kind, t in self.tracks.items()}, dropped=self.dropped)

    def writing(self):
        """Full paths (normcase) of the files being written now by REC / REC SQ of this VFO."""
        return {os.path.normcase(os.path.abspath(t.path)) for t in self.tracks.values() if t.enc is not None and t.path}

    # ---------- RECORDINGS tab: the folder tree <root>/YYYY/MM/DD[/iq] ----------
    def resolve(self, rel):
        """Absolute path of a path relative to the root ("" = the root); ValueError for one outside it."""
        root = os.path.abspath(self.folder)
        parts = [p for p in str(rel or "").replace("\\", "/").split("/") if p not in ("", ".")]
        if any(p == ".." or ":" in p for p in parts):
            raise ValueError("bad path")
        path = os.path.abspath(os.path.join(root, *parts))
        if os.path.normcase(path) != os.path.normcase(root) and not os.path.normcase(path).startswith(os.path.normcase(root) + os.sep):
            raise ValueError("bad path")
        return path

    def rel(self, path):
        return os.path.relpath(path, os.path.abspath(self.folder)).replace(os.sep, "/")

    # ---------- stars (★ in RECORDINGS): <root>/starred.json, a list of paths relative to the root ----------
    def stars(self):
        """Set of the starred recordings (relative paths); empty when the file is missing or broken."""
        try:
            with open(os.path.join(self.folder, STARS_FILE), encoding="utf-8") as f:
                data_ = json.load(f)
            return {p for p in data_ if isinstance(p, str)} if isinstance(data_, list) else set()
        except (OSError, ValueError):
            return set()

    def _save_stars(self, stars):
        path = os.path.join(self.folder, STARS_FILE)
        if not stars:
            try:
                os.remove(path)
            except OSError:
                pass
            return
        os.makedirs(self.folder, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sorted(stars), f, indent=0)
        os.replace(tmp, path)

    def set_star(self, rel, on):
        """Stars or unstars one recording; ValueError for a path that is not a recording."""
        path = self.resolve(rel)
        if not os.path.isfile(path) or not path.lower().endswith(AUDIO_EXT):
            raise ValueError("No such recording")
        rel = self.rel(path)
        with _stars_lock:
            stars = self.stars()
            if bool(on) == (rel in stars):
                return
            (stars.add if on else stars.discard)(rel)
            self._save_stars(stars)

    def _forget_stars(self):
        """Drops the stars of recordings that are gone (after a delete)."""
        with _stars_lock:
            stars = self.stars()
            alive = {p for p in stars if os.path.isfile(os.path.join(self.folder, *p.split("/")))}
            if alive != stars:
                self._save_stars(alive)

    def file_info(self, path, writing, stat=None):
        name = os.path.basename(path)
        stat = stat or os.stat(path)
        info = parse_name(name)
        if name.lower().endswith(".wav"):
            secs = wav_secs(path, stat.st_size)
        else:
            kbps = {"scan": SCAN_KBPS, "dab": DAB_KBPS, "graves": GRAVES_KBPS}.get(info["src"], BITRATE)
            secs = int(stat.st_size * 8 / (kbps * 1000))
        return dict(info, name=name, path=self.rel(path), size=stat.st_size, mtime=int(stat.st_mtime), secs=secs,
                    writing=os.path.normcase(os.path.abspath(path)) in writing)

    def list_dir(self, rel="", writing=None):
        """One folder of the tree: its subfolders (with the number of recordings and their size, counted through all
        levels below) and its recordings (MP3 / WAV). writing = full paths written now by others (scan, IQ)."""
        folder = self.resolve(rel)
        writing = self.writing() | {os.path.normcase(os.path.abspath(p)) for p in (writing or ()) if p}
        dirs, files = [], []
        try:
            entries = list(os.scandir(folder))
        except OSError:
            entries = []
        for e in entries:
            try:
                if e.is_dir():
                    n, size, newest = _tree_stats(e.path)
                    dirs.append({"name": e.name, "path": self.rel(e.path), "files": n, "size": size, "mtime": newest})
                elif e.name.lower().endswith(AUDIO_EXT):
                    files.append(self.file_info(e.path, writing, e.stat()))
            except OSError:
                continue
        stars = self.stars()
        for f in files:
            f["starred"] = f["path"] in stars
        for d in dirs:
            d["starred"] = sum(1 for p in stars if p.startswith(d["path"] + "/"))
        dirs.sort(key=lambda d: d["name"], reverse=True)
        files.sort(key=lambda f: (f["start"] or "", f["name"]))
        return {"dir": self.rel(folder) if os.path.normcase(folder) != os.path.normcase(os.path.abspath(self.folder)) else "",
                "root": os.path.abspath(self.folder), "dirs": dirs, "files": files}

    def delete_paths(self, rels, writing=None):
        """Deletes recordings and whole folders (with all inside); files being written stay, folders left empty go,
        also the empty day / month / year above. Returns {"deleted": n, "kept": [why…]}; ValueError for a bad path."""
        writing = self.writing() | {os.path.normcase(os.path.abspath(p)) for p in (writing or ()) if p}
        root = os.path.normcase(os.path.abspath(self.folder))
        paths = [self.resolve(r) for r in rels]
        if any(os.path.normcase(p) == root for p in paths):
            raise ValueError("the whole recordings folder cannot be deleted at once")
        deleted, kept, parents = 0, [], set()

        def rm(path):
            nonlocal deleted
            if os.path.normcase(os.path.abspath(path)) in writing:
                kept.append(f"{os.path.basename(path)}: being written")
                return
            try:
                os.remove(path)
                deleted += 1
            except OSError as e:
                kept.append(f"{os.path.basename(path)}: {e.strerror or e}")

        for p in paths:
            if os.path.isdir(p):
                for top, subs, names in os.walk(p, topdown=False):
                    for fn in names:
                        rm(os.path.join(top, fn))
                    try:
                        os.rmdir(top)
                    except OSError:
                        pass
            elif os.path.isfile(p):
                rm(p)
            else:
                kept.append(f"{os.path.basename(p)}: not found")
            parents.add(os.path.dirname(p))
        for d in parents:
            prune_empty(d, self.folder)
        self._forget_stars()
        return {"deleted": deleted, "kept": kept}

    def find(self, name):
        """A recording by its name alone (the file column of the scan log): in its day folder (also with the _SCAN tag
        and as MP3 that older names lack), else in the old flat folders. None when it is gone."""
        if not name or "/" in name or "\\" in name or name.startswith("."):
            return None
        stem, ext = os.path.splitext(name)
        names = [name, stem + ".mp3"]
        m = NAME_RE.match(name)
        if m and not m.group("tag"):
            tagged = re.sub(r"(_\d{8}_\d{6})", r"\1_SCAN", stem, count=1)
            names += [tagged + ext, tagged + ".mp3"]
        t = start_time(name)
        folders = [day_folder(self.folder, t), os.path.join(day_folder(self.folder, t), "iq")] if t else []
        folders += [os.path.join(self.folder, "scan"), self.folder]
        for f in folders:
            for n in names:
                path = os.path.join(f, n)
                if os.path.isfile(path):
                    return path
        return None


def _tree_stats(folder):
    """(recordings, bytes, newest mtime) of a folder and all below; scandir: on Windows the sizes come with the
    listing, no stat per file (a network drive with thousands of files)."""
    n = size = newest = 0
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return 0, 0, 0
    for e in entries:
        try:
            if e.is_dir():
                a, b, c = _tree_stats(e.path)
                n, size, newest = n + a, size + b, max(newest, c)
            elif e.name.lower().endswith(AUDIO_EXT):
                st = e.stat()
                n, size, newest = n + 1, size + st.st_size, max(newest, int(st.st_mtime))
        except OSError:
            continue
    return n, size, newest


def prune_empty(folder, root):
    """Removes folder and its parents up to root (not root itself) while they are empty."""
    root = os.path.normcase(os.path.abspath(root))
    folder = os.path.abspath(folder)
    while os.path.normcase(folder).startswith(root + os.sep):
        try:
            os.rmdir(folder)            # only an empty one
        except OSError:
            return
        folder = os.path.dirname(folder)


def _wav_to_mp3(src, dst):
    """An old WAV of the scan (mono 16 bit) to MP3 like the scan writes now; the WAV is deleted after."""
    import wave
    with wave.open(src, "rb") as w:
        ch, rate, width, n = w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes()
        pcm = w.readframes(n)
    if width != 2 or ch not in (1, 2):
        raise ValueError("not 16-bit PCM")
    enc = lameenc.Encoder()
    enc.set_bit_rate(SCAN_KBPS if ch == 1 else BITRATE)
    enc.set_in_sample_rate(int(rate))
    enc.set_channels(ch)
    enc.set_quality(2)
    part = dst + ".part"              # an interrupted conversion leaves no half MP3 (the next start does it again)
    with open(part, "wb") as out:
        out.write(enc.encode(pcm))
        out.write(enc.flush())
    t = os.path.getmtime(src)
    os.utime(part, (t, t))
    os.replace(part, dst)
    os.remove(src)


def migrate(root=None):
    """Once (at the start of a VFO server): the recordings of the flat folders before 1.1 – <root>/*.mp3, <root>/scan/*,
    <root>/iq/*.wav – go to <root>/YYYY/MM/DD (IQ to …/DD/iq) by the start in their name (else the file time); the
    scan files get the _SCAN tag, their old WAV become MP3. More servers start together: a lock file lets one do it.
    Returns the number of files moved."""
    root = root or current_folder()
    lock = os.path.join(root, ".migrate.lock")
    try:
        if os.path.exists(lock):
            if time.time() - os.path.getmtime(lock) < 600:
                return 0                      # another VFO server is at it (a lock older than that: it was killed)
            os.remove(lock)
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        return 0
    except OSError:
        return 0
    moved = 0
    try:
        for sub, scan, iq in (("", False, False), ("scan", True, False), ("iq", False, True)):
            folder = os.path.join(root, sub) if sub else root
            try:
                names = [n for n in os.listdir(folder) if n.lower().endswith(AUDIO_EXT if not iq else (".wav",))
                         and os.path.isfile(os.path.join(folder, n))]
            except OSError:
                continue
            for name in names:
                src = os.path.join(folder, name)
                try:
                    os.utime(lock)                    # still at it: the lock stays fresh for the other servers
                    t = start_time(name) or os.path.getmtime(src)
                    day = day_folder(root, t)
                    dst_dir = os.path.join(day, "iq") if iq else day
                    os.makedirs(dst_dir, exist_ok=True)
                    new = name
                    m = NAME_RE.match(name)
                    if scan and m and not m.group("tag"):
                        new = re.sub(r"(_\d{8}_\d{6})", r"\1_SCAN", name, count=1)
                    if scan and new.lower().endswith(".wav") and lameenc is not None:
                        dst = os.path.join(dst_dir, os.path.splitext(new)[0] + ".mp3")
                        if not os.path.exists(dst):
                            _wav_to_mp3(src, dst)
                            moved += 1
                            time.sleep(0.02)          # at start-up: leave the CPU to the receivers between files
                        continue
                    dst = os.path.join(dst_dir, new)
                    if not os.path.exists(dst):
                        os.replace(src, dst)
                        moved += 1
                except Exception as e:     # noqa: BLE001 – one bad file must not stop the others (wave.Error, lameenc …)
                    print(f"recordings: {name} not moved: {e}", flush=True)
            if sub:
                prune_empty(folder, root)
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass
    if moved:
        print(f"recordings: {moved} files moved into the YYYY/MM/DD folders", flush=True)
    return moved

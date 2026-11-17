"""REC IQ: the whole IQ of the dongle (the raw samples, the full band at its sample rate) into WAV files in the
subfolder "iq" of the recordings folder (default data\\recordings\\iq), the way SDR# records the baseband:

  * WAV, 2 channels: I = left, Q = right, at the sample rate of the dongle;
  * RTL-SDR: 8 bit unsigned, the bytes of the dongle as they come (lossless, no CPU); LimeSDR / Airspy: 16 bit signed;
  * the name as SDR#: RADIMCOM_<VFO>_<YYYYMMDD_HHMMSS>Z_<centre>Hz_IQ.wav (UTC), so SDR#, SDR++ and others take the
    centre frequency from it; an "auxi" chunk (SpectraVue / HDSDR) carries the start / stop time and the centre too.

A new file when the centre, the sample rate or the sample format changes, and before a file passes MAX_BYTES
(2 GiB: readers that take the 32-bit WAV sizes as signed stop there). The sizes in the header are written every
HEADER_EVERY_S, so a file cut off by a crash still opens. The receiver thread only puts the blocks in a queue;
writing runs in its own thread, and blocks the disk cannot take are counted (dropped).
"""
import datetime
import os
import queue
import struct
import threading
import time

import numpy as np

MAX_BYTES = 2 * 1024 ** 3 - 1024 * 1024
HEADER_EVERY_S = 5.0
QUEUE_BLOCKS = 96            # RTL at 2.4 MS/s: 256 kB a block (~55 ms), ~5 s of samples


def _systemtime(t):
    """Windows SYSTEMTIME of a datetime (UTC): 8 WORD."""
    return struct.pack("<8H", t.year, t.month, (t.weekday() + 1) % 7, t.day, t.hour, t.minute, t.second,
                       t.microsecond // 1000)


class IqRecorder:
    def __init__(self, folder, vfo=""):
        self.folder = folder         # callable: the folder for the next file
        self.vfo = vfo
        self.on = False
        self.error = ""
        self.file = ""               # file being written, otherwise the last saved one
        self.saved = 0
        self.dropped = 0
        self.out = None
        self.key = None              # (fs, centre, bits) of the open file
        self.data_bytes = 0
        self.start_t = None
        self.header_t = 0.0
        self.q = queue.Queue(maxsize=QUEUE_BLOCKS)
        threading.Thread(target=self._run, daemon=True, name="iq-rec").start()

    # ---------- from the outside ----------
    def set(self, on):
        if on and not self.on:
            self.error, self.file, self.saved, self.dropped = "", "", 0, 0
        self.on = bool(on)

    def feed(self, raw, fs, center_hz):
        """A raw block of the dongle (uint8 interleaved I/Q of RTL, or complex64); never blocks the receiver."""
        if not self.on:
            return
        try:
            self.q.put_nowait((raw, float(fs), float(center_hz)))
        except queue.Full:
            self.dropped += 1

    def stop(self, wait_s=3.0):
        self.on = False
        end = time.monotonic() + wait_s
        while self.out is not None and time.monotonic() < end:
            time.sleep(0.02)

    def state(self):
        key, n = self.key, self.data_bytes
        secs = 0
        if self.out is not None and key:
            secs = int(n / (key[0] * 2 * key[2] // 8))
        return {"on": self.on, "open": self.out is not None, "file": self.file, "secs": secs, "saved": self.saved,
                "mb": round(n / 1e6, 1) if self.out is not None else 0, "rate": int(key[0]) if key else 0,
                "dropped": self.dropped, "error": self.error}

    # ---------- the writer thread ----------
    def _run(self):
        while True:
            try:
                block = self.q.get(timeout=0.25)
            except queue.Empty:
                block = None
            try:
                if not self.on:
                    self._close()
                    while not self.q.empty():          # blocks queued before the stop are not written
                        self.q.get_nowait()
                elif block:
                    self._write(*block)
            except (OSError, ValueError) as e:
                self.on, self.error = False, f"IQ recording stopped: {e}"
                print(self.error, flush=True)
                try:
                    self._close()
                except OSError:
                    pass

    def _write(self, raw, fs, center):
        if raw.dtype == np.uint8:
            bits, data = 8, raw.tobytes()                 # RTL: unsigned 8 bit, I Q I Q … = WAV 8 bit stereo
        else:
            x = np.asarray(raw, np.complex64).view(np.float32)
            data, bits = np.clip(np.rint(x * 32767.0), -32768, 32767).astype("<i2").tobytes(), 16
        key = (fs, center, bits)
        if self.out is not None and (key != self.key or self.data_bytes + len(data) > MAX_BYTES):
            self._close()
        if self.out is None:
            self._open(fs, center, bits)
        self.out.write(data)
        self.data_bytes += len(data)
        if time.monotonic() - self.header_t > HEADER_EVERY_S:
            self._header()

    def _open(self, fs, center, bits):
        folder = self.folder()
        os.makedirs(folder, exist_ok=True)
        self.start_t = datetime.datetime.now(datetime.timezone.utc)
        vfo = f"_{self.vfo}" if self.vfo else ""
        stem = f"RADIMCOM{vfo}_{self.start_t:%Y%m%d_%H%M%S}Z_{int(round(center))}Hz_IQ"
        path, n = os.path.join(folder, stem + ".wav"), 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(folder, f"{stem}_{n}.wav")
        self.out = open(path, "xb")
        self.key, self.data_bytes, self.file = (fs, center, bits), 0, os.path.basename(path)
        self._header()

    def _header(self):
        """RIFF / fmt / auxi / data with the sizes so far; the file position stays at its end."""
        fs, center, bits = self.key
        rate = int(round(fs))
        align = 2 * bits // 8
        fmt = struct.pack("<HHIIHH", 1, 2, rate, rate * align, align, bits)
        now = datetime.datetime.now(datetime.timezone.utc)
        cf = int(round(center)) & 0xFFFFFFFF                     # DWORD: up to 4.29 GHz
        auxi = _systemtime(self.start_t) + _systemtime(now) + struct.pack("<9I", cf, rate, 0, rate, 0, 0, 0, 0, 0)
        head = (b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"auxi" + struct.pack("<I", len(auxi)) + auxi
                + b"data" + struct.pack("<I", self.data_bytes))
        riff = b"RIFF" + struct.pack("<I", 4 + len(head) + self.data_bytes) + b"WAVE"
        pos = self.out.tell()
        self.out.seek(0)
        self.out.write(riff + head)
        if pos > 0:
            self.out.seek(pos)
        self.out.flush()
        self.header_t = time.monotonic()

    def _close(self):
        if self.out is None:
            return
        try:
            self._header()
        finally:
            out, self.out = self.out, None
            out.close()
            self.saved += 1

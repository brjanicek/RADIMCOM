"""PRE-REC (formerly RETRO): tuning back in time. The raw IQ of the dongle of the last RETRO_S seconds (10-300, default 60) is kept in RAM
(RTL: its 8-bit bytes as they come, others: 16 bit), so a signal that was on the waterfall a while ago can still be
heard: Alt+click on the waterfall at its row and frequency demodulates CLIP_S seconds from that moment with the mode
and filter of the VFO (sdr.Decimator + sdr.Channel, as live) and plays them in the browser. SAVE writes the whole buffer
as an IQ WAV (as REC IQ, SDR# style), so the last minute can still be recorded after the fact.

RAM: RTL 2.4 MS/s = 4.8 MB/s (60 s: 288 MB); LimeSDR / Airspy (16 bit) twice that. Only while PRE-REC is on.
"""
import collections
import datetime
import io
import os
import threading
import time
import wave

import numpy as np

RETRO_S_DEFAULT = 60
RETRO_S_MIN, RETRO_S_MAX = 10, 300
CLIP_S = 20.0               # a replay is this long at most (it stops earlier where the buffer ends or the centre moved)


class RetroBuffer:
    def __init__(self, vfo=""):
        self.vfo = vfo
        self.on = False
        self.seconds = RETRO_S_DEFAULT
        self.lock = threading.Lock()
        self.blocks = collections.deque()       # (t_end unix, data, fs, centre, kind) kind: "u8" | "i16"
        self.samples = 0
        self.bytes = 0
        self.error = ""

    def set(self, on=None, seconds=None):
        with self.lock:
            if seconds is not None:
                self.seconds = int(min(max(int(seconds), RETRO_S_MIN), RETRO_S_MAX))
            if on is not None:
                self.on = bool(on)
            if not self.on:
                self.blocks.clear()
                self.samples = self.bytes = 0
            else:
                self._trim()

    def feed(self, raw, fs, center_hz):
        """A raw block of the dongle (uint8 interleaved I/Q of RTL, or complex64); copied, never blocks long."""
        if not self.on:
            return
        if raw.dtype == np.complex64:
            data, kind = np.clip(raw.view(np.float32) * 32767.0, -32768, 32767).astype(np.int16), "i16"
        else:
            data, kind = np.array(raw, np.uint8, copy=True), "u8"
        with self.lock:
            if self.blocks and (self.blocks[-1][2] != fs):
                self.blocks.clear()                     # another sample rate: the old samples cannot be joined
                self.samples = self.bytes = 0
            self.blocks.append((time.time(), data, float(fs), float(center_hz), kind))
            self.samples += len(data) // 2
            self.bytes += data.nbytes
            self._trim()

    def _trim(self):
        while self.blocks and self.samples > self.seconds * self.blocks[-1][2]:
            _, d, _, _, _ = self.blocks.popleft()
            self.samples -= len(d) // 2
            self.bytes -= d.nbytes

    def state(self):
        with self.lock:
            span = 0.0
            if self.blocks:
                span = self.samples / self.blocks[-1][2]
            return {"on": self.on, "seconds": self.seconds, "held_s": round(span, 1), "mb": round(self.bytes / 1e6),
                    "oldest": round(self.blocks[0][0] - len(self.blocks[0][1]) / 2 / self.blocks[0][2], 2) if self.blocks else None,
                    "error": self.error}

    @staticmethod
    def _iq(data, kind):
        if kind == "u8":
            return ((data.astype(np.float32) - 127.5) / 127.5).view(np.complex64)
        return (data.astype(np.float32) / 32767.0).view(np.complex64)

    def segment(self, t_from, seconds):
        """IQ from unix time t_from, at most `seconds` long, with one centre frequency.
        -> (complex64 samples, fs, centre Hz, actual start time) or None."""
        with self.lock:
            blocks = list(self.blocks)
        if not blocks:
            return None
        out, fs, center, start = [], None, None, None
        for t_end, data, f, c, kind in blocks:
            n = len(data) // 2
            t0 = t_end - n / f
            if t_end <= t_from:
                continue
            if center is None:
                fs, center = f, c
                skip = max(0, int((t_from - t0) * f))
                start = t0 + skip / f
                iq = self._iq(data, kind)[skip:]
            elif c != center:
                break                                   # the centre moved: the replay ends here
            else:
                iq = self._iq(data, kind)
            out.append(iq)
            if sum(len(x) for x in out) >= seconds * fs:
                break
        if not out:
            return None
        x = np.concatenate(out)[:int(seconds * fs)]
        return x, fs, center, start

    def clip_wav(self, t_from, tune_hz, cfg, seconds=CLIP_S):
        """Demodulates `seconds` from t_from at tune_hz through the audio chain of the VFO as it is set now (config
        cfg: mode, filter and all the AUDIO keys: NB, NF, DNR, HUM, TNF, APF, SAM, NTH, ALC, AFI, LPF / HPF, BIN), as
        the live audio, only without the squelch and the tone squelch (a replay is listened to on purpose).
        -> (WAV bytes 16 bit, mono or stereo with BIN, info) or (None, error)."""
        import audiofx
        import sdr                                      # here: sdr imports nothing of this module
        seg = self.segment(t_from, seconds)
        if seg is None:
            return None, "nothing kept at that time (PRE-REC holds the last %d s)" % self.seconds
        x, fs, center, start = seg
        if abs(tune_hz - center) > fs / 2 * 0.95:
            return None, "that frequency was outside the band of the dongle then"
        mode = cfg.get("mode", "USB")
        if mode not in ("AM", "FM", "LSB", "USB", "CW"):
            return None, f"PRE-REC plays AM, FM, LSB, USB and CW, not {mode}"
        bw = float(cfg.get("bandwidth", {}).get(mode, 3000))
        if mode == "FM":
            bw = min(bw, sdr.FM_NARROW_MAX)              # wide FM goes another way live; PRE-REC plays it narrow
        c = dict(cfg, tune_hz=tune_hz)                  # the TNF notches stay on their RF frequencies
        x = x - np.mean(x)                              # the DC spike of the dongle, as live (_remove_dc)
        n = np.arange(len(x))
        x = x * np.exp(-2j * np.pi * (tune_hz - center) / fs * n).astype(np.complex64)
        afs = fs / sdr.DECIM
        dec = sdr.Decimator(fs, cutoff=min(10000.0, afs / 3))
        ch = sdr.Channel(afs)
        nb = sdr.NoiseBlanker() if c.get("nb") and mode not in sdr.NB_OFF_MODES else None
        if nb:
            nb.level = int(c.get("nb_level", sdr.NB_LEVEL_DEFAULT))
            nb.width_us = float(c.get("nb_width_us", sdr.NB_WIDTH_DEFAULT_US))
        afi = sdr.FreqInverter() if c.get("afi") else None
        lpf, hpf = sdr.SharpLowpass(), sdr.PassFilter("highpass")
        lp = float(c.get("lpf_hz", sdr.LPF_DEFAULT_HZ)) if c.get("lpf") else None
        hp = float(c.get("hpf_hz", sdr.HPF_DEFAULT_HZ)) if c.get("hpf") else None
        binaural = audiofx.Binaural() if c.get("bin") and mode in audiofx.BIN_MODES else None
        blk = sdr.READ_SAMPLES
        audio = []
        for i in range(0, len(x) - blk + 1, blk):
            iq = x[i:i + blk]
            if nb:
                iq = nb.process(iq, fs)
            base = dec.process(iq)
            if len(base) % sdr.SQUELCH_SUB:
                base = base[:len(base) - len(base) % sdr.SQUELCH_SUB]
            sdr.channel_setup(ch, c, mode, bw)
            a, _ = ch.process(base)
            if afi is not None and a.ndim == 1:
                a = afi.process(a, afs, float(c.get("afi_hz", sdr.AFI_DEFAULT_HZ)))
            if lp is not None or hp is not None:
                st = np.stack((a, a), axis=1)
                st = hpf.process(lpf.process(st, afs, lp), afs, hp)
                a = np.clip(st[:, 0], -1, 1).astype(np.float32)
            if binaural is not None:
                a = binaural.process(a)
            audio.append(a)
        if not audio:
            return None, "too short"
        a = np.concatenate(audio)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(2 if a.ndim == 2 else 1)
            w.setsampwidth(2)
            w.setframerate(int(round(afs)))
            w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())
        return buf.getvalue(), {"start": start, "seconds": round(len(a) / afs, 1), "center_hz": center}

    def save_iq(self, folder):
        """The whole buffer as a 2-channel WAV (I left, Q right) named like REC IQ -> path."""
        with self.lock:
            blocks = list(self.blocks)
        if not blocks:
            raise ValueError("the PRE-REC buffer is empty")
        last = blocks[-1]
        blocks = [b for b in blocks if b[2] == last[2] and b[3] == last[3] and b[4] == last[4]]
        fs, center, kind = last[2], last[3], last[4]
        t0 = blocks[0][0] - len(blocks[0][1]) / 2 / fs
        os.makedirs(folder, exist_ok=True)
        stamp = datetime.datetime.fromtimestamp(t0, datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = f"RADIMCOM_{self.vfo or 'VFO'}_{stamp}Z_{int(round(center))}Hz_IQ_PREREC.wav"
        path = os.path.join(folder, name)
        with wave.open(path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(1 if kind == "u8" else 2)
            w.setframerate(int(round(fs)))
            for b in blocks:
                w.writeframes(b[1].tobytes() if kind == "u8" else b[1].astype("<i2").tobytes())
        return path


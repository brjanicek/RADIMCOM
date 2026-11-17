"""AGC+ (smart AGC): the tuner gain of the dongle from the A/D samples and the spectrum of the whole band.

The ideas (not the code) follow the auto gain of OnAir (adswill/OnAir, docs/AUTOGAIN.md and docs/auto-gain.md):

* Measurement (FrontMeter): the clipped share and the peak of the A/D, a robust peak (the 99.9 % point of the samples,
  so one spike does not decide), a 2 s peak-hold; from the spectrum of the band the noise floor (the quietest quarter)
  over the A/D's own quantisation noise, the SNR of the channel against its flanks and the strongest signal outside it.
* AUTO (SmartAgc): keeps a headroom (full scale over the robust peak) that depends on the kind of signal and the band,
  instead of driving the gain up to the top of the A/D. An overload cuts at once, by how bad it is, and leaves a soft
  ceiling; the gain then climbs back to where it was. It does not go up when more gain buys nothing (the noise floor
  far over the A/D's own: "gain wasted"), and goes up 3 dB at a time when the floor is too close to the A/D's noise.
  Hysteresis: after a step down, a step up needs a clearly larger room for 8 s.

Not verified against OnAir's own numbers on hardware (OnAir says the same of its thresholds); tuned on the simulation
of tests/test_sagc.py.
"""
import math
import time
from collections import deque

import numpy as np

# Settings of AGC+ (SETTINGS › VFO › ADVANCED), name: (default, min, max). Kept in the config as "sagc".
# The defaults = the preset MODERATE of the page (SAGC_PRESETS in app.js); CONSERVATIVE, CAREFUL and BOLD are there too.
SAGC_PARAMS = {
    "headroom_adj": (0.0, -10, 10),   # dB added to the headroom target of the signal kind and band
    "window_db": (3.0, 1, 10),        # dead band around the headroom target
    "clip_ppm": (100, 0, 2000),       # clipped samples per million in a block above which the gain is cut at once
    "down_db": (3.0, 1, 10),          # the cut on a mild overload (6 / 9 / 14 / 30 dB on heavier ones)
    "up_db": (6.0, 1, 12),            # at most per step up
    "hold_s": (2.5, 0.2, 10),         # at least this between steps up
    "wasted_db": (15.0, 6, 30),       # no step up while the noise floor is this far over the goal ("gain wasted")
    "settle": (2, 0, 20),             # blocks ignored after a gain change (the tuner settles), plus those already queued
}
SAGC_SETTLE = SAGC_PARAMS["settle"][0]


def sagc_params(cfg):
    """The AGC+ settings of a config, missing ones by default (old keys of before 1.0beta2 are ignored)."""
    own = cfg.get("sagc") or {}
    return {k: own.get(k, d) for k, (d, _lo, _hi) in SAGC_PARAMS.items()}


# Per kind of signal: (headroom dB, floor over the A/D's noise: goal dB, headroom from the peak-hold)
KINDS = {
    "narrow": (14.0, 10.0, False),     # voice and data in a narrow channel (SSB, CW, NFM, AM, digital voice, ...)
    "fm": (9.0, 5.0, False),           # FM broadcast
    "wide": (7.5, 8.0, False),         # DAB
    "pulsed": (3.0, 12.0, True),       # ADS-B: the pulses may come close to full scale
}
KIND_TEXT = {"narrow": "narrow channel", "fm": "FM broadcast", "wide": "DAB", "pulsed": "ADS-B pulses"}


class Target:
    """What AGC+ aims at for this VFO now (signal kind, band and the user's adjustment)."""

    def __init__(self, kind="narrow", freq_hz=145e6, wide_capture=True, adj=0.0):
        head, goal, hold = KINDS[kind]
        band = ""
        if freq_hz < 30e6:
            head, goal, band = head + 3, goal - 2, "HF: the band's noise is far above the radio's, strong stations"
        elif 87.5e6 <= freq_hz <= 108e6 and kind != "fm":
            head, band = head + 3, "FM broadcast band: strong stations"
        elif 30e6 <= freq_hz < 87.5e6 or 108e6 < freq_hz < 174e6:
            head, band = head + 1, "VHF"
        elif freq_hz > 1e9 and kind != "pulsed":
            head, goal, band = head - 2, goal + 2, "above 1 GHz: sensitivity first"
        if wide_capture:
            head += 2                           # the band is much wider than the channel: more strong signals reach the A/D
        self.kind, self.band = kind, band
        self.head, self.goal, self.use_hold = head + adj, goal, hold

    def as_dict(self):
        return {"kind": self.kind, "kind_text": KIND_TEXT[self.kind], "band": self.band, "target": round(self.head, 1),
                "goal": round(self.goal, 1)}


def kind_for(mode, adsb=False, dab=False):
    return "pulsed" if adsb else "wide" if dab else "fm" if mode == "WFM" else "narrow"


def passband(mode, tune, bw):
    """(lo, hi) Hz of the channel of a mode."""
    bw = max(float(bw or 0), 500.0)
    if mode == "USB":
        return tune + 100, tune + bw
    if mode == "LSB":
        return tune - bw, tune - 100
    return tune - bw / 2, tune + bw / 2


def adc_noise_bin(bits, nfft):
    """The A/D's quantisation noise per bin of a Hann FFT normalised to the window sum (the waterfall units):
    each of I and Q carries LSB²/12 with LSB = 1 / 2^(bits-1) of full scale; Hann: sum(w²)/sum(w)² = 1.5 / N."""
    lsb = 2.0 ** -(bits - 1)
    return 2 * lsb * lsb / 12 * 1.5 / nfft


def analyse(power, fs, center, tune, mode, bw, bits):
    """Noise floor, its margin over the A/D's noise, the channel SNR and the strongest signal outside the channel,
    from one spectrum of the whole band (power per bin, fftshifted, sine-normalised as the waterfall)."""
    n = len(power)
    bin_hz = fs / n
    lo_edge = center - fs / 2
    a, b = n // 10, n - n // 10                 # the edges: the anti-alias filter of the dongle
    mid = n // 2
    use = np.concatenate((power[a:mid - 4], power[mid + 5:b]))
    q = len(use) // 4
    floor = float(np.partition(use, q)[q])     # the median of the quietest half
    adc = adc_noise_bin(bits, n)
    out = {"floor_db": 10 * math.log10(floor + 1e-30), "margin": 10 * math.log10((floor + 1e-30) / adc)}
    plo, phi = passband(mode, tune, bw)
    i0 = int(max(0, min(n - 1, (plo - lo_edge) / bin_hz)))
    i1 = int(max(i0 + 1, min(n, math.ceil((phi - lo_edge) / bin_hz))))
    ch = power[i0:i1]
    wid = max(i1 - i0, 4)
    gap = max(1, wid // 4)
    fl = np.concatenate((power[max(a, i0 - gap - wid):max(a, i0 - gap)], power[min(b, i1 + gap):min(b, i1 + gap + wid)]))
    if len(ch) and len(fl):
        out["snr"] = 10 * math.log10(float(np.mean(ch)) / (float(np.median(fl)) + 1e-30) + 1e-30)
    # the strongest line outside the channel (± one channel width more)
    mask = np.ones(n, bool)
    mask[:a] = mask[b:] = False
    mask[mid - 4:mid + 5] = False
    mask[max(0, i0 - wid):min(n, i1 + wid)] = False
    if mask.any():
        idx = int(np.flatnonzero(mask)[np.argmax(power[mask])])
        out["nb_db"] = 10 * math.log10(float(power[idx]) + 1e-30)
        out["nb_hz"] = lo_edge + (idx + 0.5) * bin_hz
    if len(ch):
        out["ch_db"] = 10 * math.log10(float(np.max(ch)) + 1e-30)
    return out


class FrontMeter:
    """The A/D and the band, measured on every block."""

    HOLD_S = 2.0

    def __init__(self):
        self.clip, self.peak, self.robust = 0.0, 0.0, 0.0
        self.hold = deque()                     # (time, peak) over HOLD_S
        self.spec = {}                          # the last analyse()
        self.clip_t = -1e9                      # last block with clipping (the lamp holds 2 s)

    def block(self, raw, t):
        """(clipped share, peak 0..1) of a block of A/D samples: uint8 (RTL) or complex64 ±1 (Airspy, Lime);
        also the robust peak (the 99.9 % point of |I|, |Q|) and the peak-hold."""
        if raw.dtype == np.uint8:
            lo, hi = int(raw.min()), int(raw.max())
            peak = max(hi - 127.5, 127.5 - lo) / 127.5
            n = (np.count_nonzero(raw == 0) if lo == 0 else 0) + (np.count_nonzero(raw == 255) if hi == 255 else 0)
            a = np.abs(raw[::8].astype(np.float32) - 127.5) * np.float32(1 / 127.5)
        else:
            v = raw.view(np.float32)
            a = np.abs(v[::8])
            peak = float(np.abs(v).max()) if len(v) else 0.0
            n = np.count_nonzero(np.abs(v) >= 0.99) if peak >= 0.99 else 0
        k = int(0.999 * (len(a) - 1)) if len(a) else 0
        self.robust = float(np.partition(a, k)[k]) if len(a) else 0.0
        self.clip, self.peak = float(n) / max(raw.size, 1), float(peak)
        if self.clip > 0:
            self.clip_t = t
        self.hold.append((t, self.peak))
        while self.hold and self.hold[0][0] < t - self.HOLD_S:
            self.hold.popleft()
        return self.clip, self.peak

    @staticmethod
    def head_of(x):
        return -20 * math.log10(max(x, 1e-4))

    def headroom(self, use_hold=False):
        """Full scale over the robust peak (or over the 2 s peak-hold), dB."""
        if use_hold and self.hold:
            return self.head_of(max(p for _t, p in self.hold))
        return self.head_of(self.robust)


def _down(gains, gain, db, dpu):
    target = gain - db / dpu
    lower = [g for g in gains if g <= target + 1e-9]
    return lower[-1] if lower else gains[0]


def _up(gains, gain, db, dpu, ceil=None):
    """The highest gain at most db over gain (or the next step when it is at most 1 dB more), under the ceiling."""
    target = gain + db / dpu
    ok = [g for g in gains if gain < g <= target + 1e-9 and (ceil is None or g <= ceil + 1e-9)]
    if ok:
        return ok[-1]
    nxt = [g for g in gains if g > gain]
    if nxt and (nxt[0] - gain) * dpu <= db + 1.0 and (ceil is None or nxt[0] <= ceil + 1e-9):
        return nxt[0]
    return None


def _cut_db(ppm, mild):
    """How far an overload cuts: by how many samples clipped."""
    return max(mild, 0.0) if ppm < 1000 else max(mild, 6.0) if ppm < 1e4 else 9.0 if ppm < 5e4 else 14.0 if ppm < 2e5 else 30.0


class SmartAgc:
    """AUTO: decides a new tuner gain from each block (None = keep it), see the module docstring."""

    ACQ_S = 8.0                                 # after a start or a retune: faster steps up
    HYST_S = 8.0

    def __init__(self):
        self.meter = FrontMeter()
        self.clip, self.peak = 0.0, 0.0         # last block, for the state on the web page
        self.t = 0.0
        self.ceil, self.ceil_until = None, 0.0  # soft ceiling after an overload
        self.episodes = deque()                 # times of the overload episodes (3 in 60 s: a longer ceiling)
        self.last_clip_t = -1e9
        self.before = None                      # the gain before an overload: it climbs back to it
        self.last_up = self.last_down = -1e9
        self.acq_until = 0.0
        self.limit, self.last, self.last_t = "", "", None
        self.reset()

    def reset(self, settle=0, acquire=True):
        self.skip = settle
        self.win_head = None                    # the worst headroom since the last step up
        if acquire:
            self.acq_until = self.t + self.ACQ_S
            self.before = None

    def _note(self, text):
        self.last, self.last_t = text, time.time()

    def measure(self, raw, block_s):
        self.t += block_s
        self.clip, self.peak = self.meter.block(raw, self.t)

    def step(self, raw, gains, gain, block_s, backlog, p, db_per_unit=1.0, tgt=None, measured=False):
        """p = sagc_params(): the settings from SETTINGS; tgt = Target (by the VFO's mode and band).
        measured: measure() already ran for this block."""
        if not measured:
            self.measure(raw, block_s)
        tgt = tgt or Target(adj=p.get("headroom_adj", 0.0))
        dpu = db_per_unit
        if self.skip > 0:
            self.skip -= 1
            return None
        t = self.t
        new, ppm, win = None, self.clip * 1e6, p["window_db"]
        head = self.meter.headroom(tgt.use_hold)
        margin = self.meter.spec.get("margin")
        if ppm > p["clip_ppm"]:
            # overload: cut at once by how bad it is; a soft ceiling 3 dB under this gain, longer when it repeats
            cut = _cut_db(ppm, p["down_db"])
            if t - self.last_clip_t > 3.0:
                self.episodes.append(t)
            self.last_clip_t = t
            while self.episodes and self.episodes[0] < t - 60:
                self.episodes.popleft()
            self.ceil = gain - 3.0 / dpu
            self.ceil_until = t + (90.0 if len(self.episodes) >= 3 else 20.0)
            if self.before is None:
                self.before = gain
            new = _down(gains, gain, cut, dpu)
            if new != gain:
                self._note(f"down {(gain - new) * dpu:.1f} dB: the A/D clipped {ppm / 1e4:.3f} % of the samples")
                self.last_down = t
            self.limit = "overload"
        elif head < tgt.head - win:
            # too hot (no clipping yet): down by the error, at most every 0.8 s
            self.limit = "headroom"
            if t - self.last_down >= 0.8:
                new = _down(gains, gain, max(tgt.head - head, 1.0), dpu)
                if new != gain:
                    self._note(f"down {(gain - new) * dpu:.1f} dB: headroom {head:.1f} dB under the target {tgt.head:.0f} dB")
                    self.last_down = t
                    self.before = None
        else:
            self.win_head = head if self.win_head is None else min(self.win_head, head)
            room = self.win_head - tgt.head
            wasted = margin is not None and margin > tgt.goal + p["wasted_db"]
            ceil = self.ceil if t < self.ceil_until else None
            recovering = self.before is not None and gain < self.before
            acq = t < self.acq_until
            hold = 0.5 if acq else 1.2 if recovering else p["hold_s"]
            need = 1.5 * win if t - self.last_down < self.HYST_S and not recovering else win
            if wasted and margin > tgt.goal + p["wasted_db"] + 3:
                # far too much gain for the antenna's noise: one step down, only if it stays over the "wasted" line
                below = [g for g in gains if g < gain]
                if below and margin - (gain - below[-1]) * dpu > tgt.goal + p["wasted_db"] and t - self.last_down >= 2.5:
                    new = below[-1]
                    self._note(f"down {(gain - new) * dpu:.1f} dB: the noise floor is {margin:.0f} dB over the A/D's (gain wasted)")
                    self.last_down = t
                self.limit = "wasted"
            elif wasted:
                self.limit = "wasted"
            elif t - self.last_up >= hold and room > need:
                db = min(12.0 if acq else 4.0 if recovering else p["up_db"], room)
                if margin is not None:
                    db = min(db, tgt.goal + p["wasted_db"] - margin + 1.0)
                up = _up(gains, gain, db, dpu, ceil)
                if recovering and up is not None and up > self.before:
                    cap = [g for g in gains if gain < g <= self.before]
                    up = cap[-1] if cap else None
                if up is not None and up != gain:
                    new = up
                    why = "back toward the gain before the overload" if recovering else f"headroom {head:.1f} dB, target {tgt.head:.0f} dB"
                    self._note(f"up {(new - gain) * dpu:.1f} dB: {why}")
                    self.last_up = t
                    self.limit = ""
                elif ceil is not None and [g for g in gains if g > gain]:
                    self.limit = "ceiling"
                elif not [g for g in gains if g > gain]:
                    self.limit = "top"
                else:
                    self.limit = "headroom"
            elif (margin is not None and margin < tgt.goal and abs(room) <= win and head - 3 >= tgt.head - win
                  and t - self.last_up >= hold):
                up = _up(gains, gain, 3.0, dpu, ceil)
                if up is not None:
                    new = up
                    self._note(f"up {(new - gain) * dpu:.1f} dB: the noise floor only {margin:.1f} dB over the A/D's (goal {tgt.goal:.0f} dB)")
                    self.last_up = t
                self.limit = "sensitivity"
            else:
                self.limit = "top" if not [g for g in gains if g > gain] else "headroom" if room <= need else ""
        if self.before is not None and gain >= self.before:
            self.before = None
        if new is None or new == gain:
            return None
        self.reset(backlog + int(p["settle"]) + 1, acquire=False)
        return new

    def why(self, tgt, gain_text, p):
        """The line "why this gain" for the page."""
        m, s = self.meter, self.meter.spec
        head = m.headroom(tgt.use_hold)
        parts = [f"{gain_text}: headroom {head:.1f} dB (target {tgt.head:.0f})"]
        if "margin" in s:
            parts.append(f"floor {s['margin']:.0f} dB over the A/D's noise (goal {tgt.goal:.0f})")
        lim = {"overload": "limited by an overload",
               "ceiling": f"held under the gain that clipped ({max(0, self.ceil_until - self.t):.0f} s)",
               "wasted": "more gain buys nothing (the antenna's noise is far over the A/D's)",
               "top": "top of the gain range", "sensitivity": "raising the sensitivity"}.get(self.limit)
        if self.limit == "headroom":
            nb = s.get("nb_db")
            lim = "limited by the headroom" + (f" – strong signal at {s['nb_hz'] / 1e6:.3f} MHz ({nb:.0f} dBFS)"
                                               if nb is not None and nb > -40 and nb > s.get("ch_db", -999) else "")
        if lim:
            parts.append(lim)
        return ", ".join(parts)


def warning(meter, tgt, wasted_db):
    """The first warning in plain words (OnAir's meter strip), or ""."""
    s = meter.spec
    if meter.clip > 0:
        return "The A/D clips: a strong signal overloads the dongle – lower the gain or add a filter"
    nb = s.get("nb_db")
    if nb is not None and nb > -12:
        return (f"Strong signal nearby ({s['nb_hz'] / 1e6:.3f} MHz, {nb:.0f} dBFS): reduce the gain or add a filter "
                "(band-pass, or an FM / GSM notch)")
    mg = s.get("margin")
    if mg is not None and mg < 3:
        return "Gain too low: the A/D's own noise limits the sensitivity"
    if mg is not None and mg > tgt.goal + wasted_db:
        return "The antenna's noise is far over the A/D's: more gain buys nothing, less gives more room for strong signals"
    return ""

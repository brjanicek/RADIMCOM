"""AGC+ (gainctl.py) on a simulated front end: an R820T gain table, antenna noise and the radio's own noise (rising
slower than the gain), a strong neighbour, its third-order product (3 dB per dB of gain), an 8-bit A/D that clips and
quantises. Checks AUTO (convergence to the headroom target without hunting, "gain wasted" on a noisy HF band,
recovery after an overload burst, the presets). The page's presets (SAGC_PRESETS in app.js) are parsed, so the test follows them.

Run: python -m unittest tests.test_sagc   (from the RADIMCOM folder)
"""
import os
import re
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import gainctl  # noqa: E402

GAINS = [0.0, 0.9, 1.4, 2.7, 3.7, 7.7, 8.7, 12.5, 14.4, 15.7, 16.6, 19.7, 20.7, 22.9, 25.4, 28.0, 29.7, 32.8,
         33.8, 36.4, 37.2, 38.6, 40.2, 42.1, 43.4, 43.9, 44.5, 48.0, 49.6]     # R820T
FS, NFFT, CENTER = 2.4e6, 32768, 145e6
ADC = gainctl.adc_noise_bin(8, NFFT)
BS = 0.1                                                                       # simulated block length, s


def presets():
    """SAGC_PRESETS parsed from app.js, so the test follows the page."""
    with open(os.path.join(ROOT, "static", "app.js"), encoding="utf-8") as f:
        js = f.read()
    body = js[js.index("const SAGC_PRESETS = {"):]
    body = body[:body.index("\n};")]
    out = {}
    for name, fields in re.findall(r"(\w+): \{([^}]*)\}", body):
        out[name] = {k: float(v) for k, v in re.findall(r"(\w+): (-?[\d.]+)", fields)}
    return out


class Front:
    """Levels in dBFS at the A/D for 0 dB gain; the front end is linear except the radio's own noise
    (rx0 + rx_slope * gain) and the product (3 * strong - 2 * iip3, output referred)."""

    def __init__(self, ant=-118.0, rx0=-112.0, rx_slope=0.55, strong=-55.0, iip3=40.0, center=CENTER, seed=1, real=None):
        self.ant, self.rx0, self.rx_slope, self.strong, self.iip3 = ant, rx0, rx_slope, strong, iip3
        self.real = real or (lambda g: g)       # the real gain of a table value (the R820T's low steps are not what it says)
        self.center, self.rng = center, np.random.default_rng(seed)
        b = lambda hz: int((hz - (center - FS / 2)) / (FS / NFFT))     # noqa: E731
        self.k_strong, self.k_prod = b(center - 500e3), b(center + 600e3)
        self.phase = 0.0

    def levels(self, g, extra=0.0):
        g = self.real(g)
        floor = 10 ** ((self.ant + g) / 10) + 10 ** ((self.rx0 + self.rx_slope * g) / 10)
        s = self.strong + g + extra
        return floor, s, 3 * s - 2 * self.iip3

    def spectrum(self, g, extra=0.0):
        floor, s, prod = self.levels(g, extra)
        p = (floor + ADC) * self.rng.chisquare(8, NFFT) / 8
        p[self.k_strong] += 10 ** (s / 10)
        p[self.k_prod] += 10 ** (prod / 10)
        return p

    def raw(self, g, extra=0.0, n=16384):
        floor, s, _ = self.levels(g, extra)
        sd = np.sqrt(floor * NFFT / 1.5 / 2)                           # the floor spread over the whole band
        t = np.arange(n)
        x = sd * (self.rng.standard_normal(n) + 1j * self.rng.standard_normal(n))
        x += 10 ** (s / 20) * np.exp(1j * (0.37 * t + self.phase))
        self.phase += 0.37 * n
        out = np.empty(2 * n, np.uint8)
        out[0::2] = np.clip(np.round(x.real * 127.5 + 127.5), 0, 255)
        out[1::2] = np.clip(np.round(x.imag * 127.5 + 127.5), 0, 255)
        return out


def ctx(front, mode="FM", bw=12500):
    return (FS, front.center, front.center + 300e3, mode, bw, 8)


def run_auto(front, p, tgt, seconds=400, g0=20.7, burst=None):
    agc, g, log = gainctl.SmartAgc(), g0, []
    agc.reset(0)
    for i in range(int(seconds / BS)):
        t = i * BS
        extra = burst(t) if burst else 0.0
        agc.measure(front.raw(g, extra), BS)
        agc.meter.spec = gainctl.analyse(front.spectrum(g, extra), *ctx(front))
        new = agc.step(None, GAINS, g, BS, 0, p, 1.0, tgt, measured=True)
        log.append((t, g, agc.meter.headroom(), agc.meter.spec["margin"], agc.clip))
        if new is not None:
            g = new
    return log


def changes(log, after):
    gs = [g for t, g, *_ in log if t >= after]
    return sum(1 for a, b in zip(gs, gs[1:]) if a != b)


class Auto(unittest.TestCase):
    def test_converges_to_the_headroom_target(self):
        p = gainctl.sagc_params({})
        tgt = gainctl.Target("narrow", CENTER + 300e3, True, 0)
        for g0 in (0.0, 20.7, 49.6):
            log = run_auto(Front(), p, tgt, g0=g0)
            heads = [h for t, g, h, m, c in log if t > 200]
            print(f"\nAUTO from {g0}: gain {log[-1][1]} dB, headroom median {np.median(heads):.1f} (target {tgt.head}), "
                  f"changes after 200 s: {changes(log, 200)}")
            self.assertLess(abs(np.median(heads) - tgt.head), p["window_db"] + 3)
            self.assertLessEqual(changes(log, 200), 4)              # no hunting

    def test_gain_wasted_on_a_noisy_band(self):
        p = gainctl.sagc_params({})
        front = Front(ant=-100.0, strong=-75.0, center=7.1e6)
        tgt = gainctl.Target("narrow", 7.1e6 + 300e3, True, 0)
        log = run_auto(front, p, tgt, g0=0.0)
        margin, g = log[-1][3], log[-1][1]
        print(f"\nHF noisy band: gain {g} dB, floor {margin:.1f} dB over the A/D (wasted over {tgt.goal + p['wasted_db']})")
        self.assertLess(g, 40)                                      # the headroom alone would take it to the top
        self.assertLessEqual(margin, tgt.goal + p["wasted_db"] + 3)
        self.assertGreater(margin, tgt.goal)

    def test_no_hunting_on_a_step_bigger_than_it_says(self):
        # 40 m, a strong station: the table step 0 -> 3.7 dB moves the A/D by ~15 dB (seen on an R820T), the target
        # lies between the two; AGC+ went up and down every 2.5 s (a line across the waterfall each time)
        p = gainctl.sagc_params({})
        front = Front(ant=-100.0, strong=-31.0, center=7.1e6, real=lambda g: g * 4.0 if g < 4 else g + 11.1)
        tgt = gainctl.Target("narrow", 7.1e6 + 300e3, True, 0)
        log = run_auto(front, p, tgt, seconds=300, g0=0.0)
        n, early = changes(log, 90), changes(log, 0)
        heads = [h for t, g, h, m, c in log if t > 90]
        print(f"\nbig step: gain {log[-1][1]} dB, headroom median {np.median(heads):.1f} (target {tgt.head}), "
              f"changes {early} in all, {n} after 90 s")
        self.assertEqual(n, 0)                                              # it learnt the real steps: no hunting
        self.assertLessEqual(early, 8)                                      # learning costs a few steps, 30 s apart
        self.assertGreater(min(heads), tgt.head - p["window_db"])

    def test_recovers_after_an_overload_burst(self):
        p = gainctl.sagc_params({})
        tgt = gainctl.Target("narrow", CENTER + 300e3, True, 0)
        log = run_auto(Front(), p, tgt, seconds=300, burst=lambda t: 22.0 if 150 <= t < 153 else 0.0)
        before = [g for t, g, *_ in log if 140 <= t < 150][-1]
        low = min(g for t, g, *_ in log if 150 <= t < 160)
        after = [g for t, g, *_ in log if t >= 260][-1]
        print(f"\nburst: {before} -> {low} -> {after} dB")
        self.assertLess(low, before - 5)
        self.assertLessEqual(abs(after - before), 3.5)

    def test_presets(self):
        pre = presets()
        for name in ("conservative", "careful", "moderate", "bold"):
            self.assertIn(name, pre)
            for k, (d, lo, hi) in gainctl.SAGC_PARAMS.items():
                self.assertTrue(lo <= pre[name][k] <= hi, (name, k))   # the server accepts every value
        for k, (d, lo, hi) in gainctl.SAGC_PARAMS.items():
            self.assertEqual(pre["moderate"][k], d, k)                   # MODERATE = the server's defaults
        heads = {}
        for name in ("conservative", "bold"):
            p = {**gainctl.sagc_params({}), **pre[name]}
            tgt = gainctl.Target("narrow", CENTER + 300e3, True, p["headroom_adj"])
            log = run_auto(Front(), p, tgt, seconds=300)
            heads[name] = float(np.median([h for t, g, h, m, c in log if t > 150]))
        print(f"\npresets: headroom conservative {heads['conservative']:.1f}, bold {heads['bold']:.1f} dB")
        self.assertGreater(heads["conservative"], heads["bold"] + 6)


if __name__ == "__main__":
    unittest.main()

"""CW decoder bench: synthetic CW (speed, SNR, QSB, QRN, hand keying, Farnsworth, a neighbour station)
-> character error rate (CER) of the decoder. Can compare the current cw.py with another version.

Run (from the RADIMCOM folder):
  python tests/cw_bench.py                    # current cw.py
  python tests/cw_bench.py --old path/cw.py   # + another version side by side (e.g. git show 0.114:cw.py > old.py)
  python tests/cw_bench.py --quick            # fewer SNR steps

SNR is the tone power to the noise power in 500 Hz (as on a CW filter).
"""
import argparse
import importlib.util
import os
import random
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cw  # noqa: E402

FS = 32000.0
CHUNK = 2048
CODE = {v: k for k, v in cw.MORSE.items() if not v.startswith("<")}

TEXTS = [
    "CQ CQ DE OM2AMR OM2AMR K",
    "OK1ABC DE OM2AMR TNX FER CALL UR RST 579 579 NAME RADO QTH BRATISLAVA HW? BK",
    "QRL? DE DL5XY GM OM TNX FB REPORT 73 ES GL SK",
    "XKQZJ WPMVB 4T9RA HYGFE 07LZN UCDOS",
]


def keying(text, wpm, rnd, jitter=0.0, key="paddle", farnsworth=None, ratio=3.0):
    """List of (key down?, ms). key: paddle (exact), bug (exact dots, loose dashes), straight (all loose)."""
    dot = 1200.0 / wpm
    gap_dot = 1200.0 / farnsworth if farnsworth else dot     # Farnsworth: longer gaps between characters
    j = lambda: float(np.exp(rnd.gauss(0, jitter))) if jitter else 1.0
    out = []
    words = text.split()
    for wi, w in enumerate(words):
        for ci, c in enumerate(w):
            code = CODE.get(c)
            if code is None:
                continue
            for ei, el in enumerate(code):
                if el == ".":
                    d = dot * (j() if key == "straight" else 1.0)
                else:
                    d = ratio * dot * (j() if key in ("straight", "bug") else 1.0)
                out.append((True, d))
                if ei < len(code) - 1:
                    out.append((False, dot * (j() if key == "straight" else 1.0)))
            if ci < len(w) - 1:
                out.append((False, 3 * gap_dot * (j() if key != "paddle" else 1.0)))
        if wi < len(words) - 1:
            out.append((False, 7 * gap_dot * (j() if key != "paddle" else 1.0)))
    return out


def envelope(keys, fs, lead=1.0, tail=2.0, edge_ms=5.0):
    """Key envelope 0..1 with raised-cosine edges (no key clicks)."""
    n = int((lead + tail + sum(d for _, d in keys) / 1000) * fs)
    env = np.zeros(n)
    t = lead
    for on, d in keys:
        if on:
            env[int(t * fs): int((t + d / 1000) * fs)] = 1.0
        t += d / 1000
    k = max(1, int(edge_ms / 1000 * fs))
    w = np.hanning(2 * k + 1)
    return np.convolve(env, w / w.sum(), mode="same")


def signal(text, wpm, f0=0.0, amp=1.0, rnd=None, jitter=0.0, key="paddle", farnsworth=None,
           qsb=0.0, qsb_hz=0.15, drift_hz=0.0, fs=FS):
    rnd = rnd or random.Random(1)
    env = envelope(keying(text, wpm, rnd, jitter, key, farnsworth), fs)
    t = np.arange(len(env)) / fs
    if qsb:
        env = env * (1 - qsb * (0.5 + 0.5 * np.sin(2 * np.pi * qsb_hz * t + rnd.random() * 6)))
    phase = 2 * np.pi * (f0 * t + 0.5 * drift_hz * t * t / max(t[-1], 1e-9))
    return amp * env * np.exp(1j * phase)


def add_noise(x, snr_db, rnd, qrn=0.0, fs=FS):
    """Complex white noise with the given SNR (tone amplitude 1) in 500 Hz; qrn = static crashes per second."""
    n0 = 1.0 / (500 * 10 ** (snr_db / 10))
    rs = np.random.default_rng(rnd.randrange(1 << 30))
    s = np.sqrt(n0 * fs / 2)
    y = x + s * (rs.standard_normal(len(x)) + 1j * rs.standard_normal(len(x)))
    if qrn:
        for _ in range(int(qrn * len(x) / fs)):
            i = rs.integers(0, len(x) - 200)
            y[i: i + rs.integers(20, 160)] += 40 * (rs.standard_normal() + 1j * rs.standard_normal())
    return y.astype(np.complex64)


def run(mod, x, band=(-250.0, 250.0), fs=FS, opts=None):
    d = mod.CwDecoder(lambda k, v: None)
    if opts and hasattr(d, "set_options"):
        d.set_options(**opts)
    d.set_enabled(True)
    for i in range(0, len(x), CHUNK):
        d.feed(x[i: i + CHUNK], fs, 7_030_000.0, band)
    return d


def norm(s):
    return " ".join(s.replace("\n", " ").split())


def cer(ref, hyp):
    """Levenshtein distance / reference length."""
    a, b = norm(ref), norm(hyp)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / max(1, len(a))


SCENARIOS = {
    "paddle 20": dict(wpm=20),
    "paddle 35": dict(wpm=35),
    "paddle 12": dict(wpm=12),
    "straight 16": dict(wpm=16, key="straight", jitter=0.18),
    "bug 25": dict(wpm=25, key="bug", jitter=0.15),
    "farnsworth 20/10": dict(wpm=20, farnsworth=10),
    "QSB 20": dict(wpm=20, qsb=0.85),
    "QRN 20": dict(wpm=20, qrn=3.0),
    "drift 20": dict(wpm=20, drift_hz=40.0),
    "neighbour 20": dict(wpm=20, neighbour=True),
}


def scenario_signal(name, snr, seed):
    p = dict(SCENARIOS[name])
    rnd = random.Random(seed)
    qrn = p.pop("qrn", 0.0)
    nb = p.pop("neighbour", False)
    text = TEXTS[seed % len(TEXTS)]
    x = signal(text, rnd=rnd, f0=30.0, **p)
    if nb:   # another station 90 Hz away, 6 dB weaker, other speed, ends sooner (the decoder must stay on the stronger)
        y = signal("QRL? DE DL5XY", 27, f0=-60.0, amp=0.5, rnd=rnd)
        n = max(len(x), len(y))
        x = np.pad(x, (0, n - len(x))) + np.pad(y, (0, n - len(y)))
    return text, add_noise(x, snr, rnd, qrn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", help="another cw.py to compare")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", help="scenario name substring")
    ap.add_argument("--seeds", type=int, default=2)
    a = ap.parse_args()
    mods = {"new": cw}
    if a.old:
        spec = importlib.util.spec_from_file_location("cw_old", a.old)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        mods = {"old": old, "new": cw}
    snrs = [12, 3, -3] if a.quick else [15, 9, 6, 3, 0, -3, -6]
    names = [n for n in SCENARIOS if not a.only or a.only in n]
    print(f"{'scenario':18} {'SNR':>4} " + " ".join(f"{m:>7}" for m in mods))
    tot = {m: [] for m in mods}
    t0 = time.time()
    for name in names:
        for snr in snrs:
            row = {m: [] for m in mods}
            for seed in range(a.seeds):
                text, x = scenario_signal(name, snr, seed)
                for m, mod in mods.items():
                    row[m].append(cer(text, "".join(run(mod, x).text)))
            for m in mods:
                tot[m].append(np.mean(row[m]))
            print(f"{name:18} {snr:>4} " + " ".join(f"{100 * np.mean(row[m]):6.1f}%" for m in mods), flush=True)
    print(f"{'MEAN':18} {'':>4} " + " ".join(f"{100 * np.mean(tot[m]):6.1f}%" for m in mods))
    print(f"({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()

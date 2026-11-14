"""RTTY decoder bench: synthetic RTTY (SNR, contest bursts with pauses, selective fading, a neighbour station)
-> character error rate (CER) of the decoder. Can compare the current rtty.py with another version.

Run (from the RADIMCOM folder):
  python tests/rtty_bench.py                      # current rtty.py
  python tests/rtty_bench.py --old path/rtty.py   # + another version side by side (git show HEAD:rtty.py > old.py)
  python tests/rtty_bench.py --quick              # fewer SNR steps

SNR is the signal power to the noise power in 500 Hz. CER = edit distance / length of the sent text; text decoded
from the noise in the pauses counts as inserted characters.
"""
import argparse
import importlib.util
import os
import random
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rtty  # noqa: E402

FS = 8000.0
CHUNK = 800
CENTER = 1500.0
LTRS = {c: i for i, c in enumerate(rtty.LTRS) if c and c not in "\r\n"}
FIGS = {c: i for i, c in enumerate(rtty.FIGS) if c and c not in LTRS and c not in "\r\n"}

TEXTS = [
    "CQ WAE DJ3NG DJ3NG CQ",
    "OM2AMR 599 034 034 OM2AMR",
    "DR6W TU 599 193 193 DR6W",
    "RYRYRY DE HA5CQZ HA5CQZ QSL 73 GL",
    "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG 1234567890",
    "QRL? DE F1FCA F1FCA PSE K",
]


def baudot(text, stop=1.5):
    """Bits (1 = mark) of the text with LTRS / FIGS shifts; stop bits in units of a half bit -> list of (bit, halves)."""
    out, figs = [], False
    def char(code):
        out.append((0, 2))
        for k in range(5):
            out.append(((code >> k) & 1, 2))
        out.append((1, int(round(stop * 2))))
    char(rtty.LTRS_CODE)
    for ch in text:
        if ch in LTRS:
            if figs and ch != " ":
                char(rtty.LTRS_CODE); figs = False
            char(LTRS[ch])
            if ch == " ":
                figs = False          # the receiver unshifts on space too
        elif ch in FIGS:
            if not figs:
                char(rtty.FIGS_CODE); figs = True
            char(FIGS[ch])
    return out


def fsk(bits, baud, shift, offset, rnd, idle=0.3):
    """Phase-continuous FSK at CENTER + offset (mark higher); idle mark before and after."""
    half = FS / baud / 2
    seq = [(1, int(idle * baud * 2))] + bits + [(1, int(idle * baud * 2))]
    lev = np.concatenate([np.full(int(round(h * half)), b, np.int8) for b, h in seq])
    f = CENTER + offset + np.where(lev == 1, shift / 2, -shift / 2)
    ph = 2 * np.pi * np.cumsum(f) / FS + rnd.uniform(0, 2 * np.pi)
    return np.exp(1j * ph), lev


def noise(n, snr_db, rng):
    """Complex noise for a unit-power signal at snr_db in 500 Hz."""
    sigma2 = 10 ** (-snr_db / 10) * FS / 500
    return np.sqrt(sigma2 / 2) * (rng.standard_normal(n) + 1j * rng.standard_normal(n))


def fading(n, rate_hz, rng):
    """Rayleigh fading envelope (complex), mean power 1, about rate_hz."""
    k = max(4, int(n / FS * rate_hz * 4))
    g = (rng.standard_normal(k) + 1j * rng.standard_normal(k)) / np.sqrt(2)
    return np.interp(np.arange(n), np.linspace(0, n - 1, k), g.real) + 1j * np.interp(np.arange(n), np.linspace(0, n - 1, k), g.imag)


def case_signal(case, snr, seed):
    rnd, rng = random.Random(seed), np.random.default_rng(seed)
    if case == "contest":
        # stations one after another, each its own small offset and level, pauses of noise between them
        parts, truth = [], []
        for k in range(6):
            t = TEXTS[(seed + k) % len(TEXTS)]
            s, _ = fsk(baudot(t), 45.45, 170, rnd.uniform(-35, 35), rnd)
            s = s * 10 ** (rnd.uniform(-3, 3) / 20)
            parts += [s, np.zeros(int(FS * rnd.uniform(1.5, 3.0)))]
            truth.append(t)
        x = np.concatenate([np.zeros(int(FS * 1.0))] + parts)
        return x + noise(len(x), snr, rng), " ".join(truth)
    text = " ".join(TEXTS[(seed + k) % len(TEXTS)] for k in range(3))
    if case == "clean":
        x, _ = fsk(baudot(text), 45.45, 170, 0, rnd, idle=2.0)
    elif case == "50/450":
        x, _ = fsk(baudot(text), 50.0, 450, 0, rnd, idle=2.0)
    elif case == "fading":
        # selective fading: mark and space fade independently (ionospheric multipath)
        bits = baudot(text)
        x, lev = fsk(bits, 45.45, 170, 0, rnd, idle=2.0)
        fm, fs_ = fading(len(x), 0.6, rng), fading(len(x), 0.6, rng)
        x = x * np.where(lev == 1, fm, fs_)
    elif case == "neighbour":
        x, _ = fsk(baudot(text), 45.45, 170, 0, rnd, idle=2.0)
        y, _ = fsk(baudot(TEXTS[(seed + 4) % len(TEXTS)] * 4), 45.45, 170, 260, rnd, idle=2.0)   # starts with it
        x = x + 0.5 * np.resize(y, len(x))         # 6 dB weaker, 260 Hz above
    else:
        raise ValueError(case)
    return x + noise(len(x), snr, rng), text


def norm(t):
    return " ".join(t.replace("\r", " ").replace("\n", " ").split())


def edit(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def run(mod, x, band=(150.0, 2900.0)):
    out = []
    d = mod.RttyDecoder(lambda k, v: out.append(v["t"]) if k == "rttytext" else None)
    d.set_enabled(True)
    x = x.astype(np.complex64)
    for i in range(0, len(x), CHUNK):
        d.feed(x[i:i + CHUNK], FS, 7e6, band)
    return "".join(out)


def load(path):
    spec = importlib.util.spec_from_file_location("rtty_old", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--case")
    ap.add_argument("--seeds", type=int, default=2)
    a = ap.parse_args()
    mods = [("new", rtty)] + ([("old", load(a.old))] if a.old else [])
    snrs = [0, 6, 12] if a.quick else [-3, 0, 3, 6, 9, 12, 20]
    cases = [a.case] if a.case else ["clean", "50/450", "contest", "fading", "neighbour"]
    tot = {n: [] for n, _ in mods}
    t0 = time.time()
    print("case        SNR  " + "  ".join(f"{n:>6}" for n, _ in mods))
    for case in cases:
        for snr in snrs:
            row = {n: [] for n, _ in mods}
            for seed in range(a.seeds):
                x, truth = case_signal(case, snr, seed)
                for n, m in mods:
                    got = norm(run(m, x))
                    row[n].append(edit(got, norm(truth)) / len(norm(truth)))
            for n in row:
                tot[n] += row[n]
            print(f"{case:10s} {snr:4d}  " + "  ".join(f"{100 * np.mean(row[n]):5.0f}%" for n, _ in mods), flush=True)
    print("mean            " + "  ".join(f"{100 * np.mean(tot[n]):5.1f}%" for n, _ in mods), f"({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()

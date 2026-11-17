"""ATU in SSB: estimate_ssb_carrier on a synthetic voice (harmonics on a moving pitch, syllables, pauses, a 300-2700 Hz
transmitter filter) at several levels, USB and LSB. Run: python tests/test_atu.py (prints the errors, asserts the limits)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import autotune  # noqa: E402

FS = 32000.0


def voice_ssb(seconds, carrier_hz, snr_db, lsb=False, seed=1, f0=130.0):
    """Complex baseband: an SSB voice with its suppressed carrier at carrier_hz, white noise; snr_db = voice power
    over the noise power in 2.4 kHz."""
    rng = np.random.default_rng(seed)
    n = int(seconds * FS)
    t = np.arange(n) / FS
    # pitch: slow wander and vibrato, per syllable a new base
    syl = np.repeat(rng.uniform(0.8, 1.25, int(seconds * 4) + 2), int(FS / 4))[:n]
    pitch = f0 * syl * (1 + 0.04 * np.sin(2 * np.pi * 5.5 * t))
    phase = 2 * np.pi * np.cumsum(pitch) / FS
    # syllables (4 / s) and pauses between words
    env = np.clip(np.sin(2 * np.pi * 4 * t + rng.uniform(0, 6)), 0, None) ** 0.6
    env *= np.repeat(rng.random(int(seconds) * 2 + 2) > 0.25, int(FS / 2))[:n]
    x = np.zeros(n, np.complex128)
    for k in range(1, 40):
        fk = k * pitch
        # formants around 500, 1500 and 2500 Hz on a falling slope
        a = (1 / k ** 0.7) * (1 + 2 * np.exp(-((fk - 500) / 200) ** 2) + 1.2 * np.exp(-((fk - 1500) / 300) ** 2)
                              + 0.6 * np.exp(-((fk - 2400) / 300) ** 2))
        a = a * ((fk >= 300) & (fk <= 2700))                # the transmitter filter
        x += a * np.exp(1j * (k * phase + rng.uniform(0, 6.3)))
    x *= env
    if lsb:
        x = np.conj(x)
    x *= np.exp(2j * np.pi * carrier_hz * t)
    p_sig = np.mean(np.abs(x) ** 2)
    noise_psd = p_sig / 10 ** (snr_db / 10) / 2400.0       # per Hz
    sigma = np.sqrt(noise_psd * FS / 2)
    x += sigma * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    return x.astype(np.complex64)


def old_estimate(x, lsb):
    r = autotune.estimate_ssb_edge(x, FS, lsb=lsb)
    return None if r is None else r[0] - (-1 if lsb else 1) * 200.0   # edge -> carrier as the old coarse step


def main():
    rows, errs = [], []
    for lsb in (False, True):
        for snr in (40, 25, 15, 10):
            for car0 in (-1800.0, -350.0, 0.0, 420.0):
                car = -car0 if lsb else car0            # LSB: the voice below the carrier, the click on it
                for seed in (1, 2, 3):
                    x = voice_ssb(3.5, car, snr, lsb=lsb, seed=seed, f0=110 + 40 * seed)
                    r = autotune.estimate_ssb_carrier(x, FS, lsb=lsb)
                    o = old_estimate(x, lsb)
                    e = None if r is None else r[0] - car
                    eo = None if o is None else o - car
                    rows.append((lsb, snr, car, seed, e, eo))
                    if e is not None:
                        errs.append((snr, abs(e)))
    print(" side  SNR  carrier  seed   new err   old err")
    for lsb, snr, car, seed, e, eo in rows:
        f = lambda v: "   none" if v is None else f"{v:+7.0f}"
        print(f" {'LSB' if lsb else 'USB'}  {snr:3d}  {car:+7.0f}  {seed}   {f(e)}   {f(eo)}")
    for snr in (40, 25, 15, 10):
        es = [e for s, e in errs if s == snr]
        found = sum(1 for r in rows if r[1] == snr and r[4] is not None)
        total = sum(1 for r in rows if r[1] == snr)
        print(f"SNR {snr}: found {found}/{total}, median |err| {np.median(es) if es else float('nan'):.0f} Hz, max {max(es) if es else float('nan'):.0f} Hz")
    strong = [e for s, e in errs if s >= 15]
    assert len(strong) == sum(1 for r in rows if r[1] >= 15), "a station at 15 dB or more was not found"
    assert max(strong) <= 150, f"carrier off by {max(strong):.0f} Hz"
    print("ok")


if __name__ == "__main__":
    main()

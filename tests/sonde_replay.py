"""Replays an IQ recording of the SONDE decoder (data/sonde_iq/*.cf32, POST /api/sonde {"action": "rec_iq"})
through SondeDecoder and the rs1729 decoders, and prints the decoded frames.

Run (from the RADIMCOM folder):
  python tests/sonde_replay.py data/sonde_iq/20261115_101500_403.5000MHz_37500Hz.cf32
  python tests/sonde_replay.py <file.cf32> --rate 37500        (a file without the rate in its name)
"""
import argparse
import os
import re
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sonde  # noqa: E402
import sonde_ext  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--rate", type=float, help="sample rate (Hz); default from the file name")
    ap.add_argument("--mhz", type=float, help="tuned frequency (MHz); default from the file name")
    a = ap.parse_args()
    name = os.path.basename(a.file)
    m = re.search(r"_(\d+)Hz", name)
    rate = a.rate or (float(m.group(1)) if m else None)
    if not rate:
        sys.exit("no sample rate: give --rate")
    m = re.search(r"_([\d.]+)MHz", name)
    dial = (a.mhz or (float(m.group(1)) if m else 403.0)) * 1e6
    z = np.fromfile(a.file, np.complex64)
    print(f"{name}: {len(z) / rate:.1f} s at {rate:.0f} Hz, {dial / 1e6:.4f} MHz; decoders {sonde_ext.available()}")
    sonde_ext.WAIT = True
    out = []
    d = sonde.SondeDecoder(lambda k, f: out.append(f) if k == "sonde" else None)
    d.set_enabled(True)
    blk = int(rate * 0.05)
    for i in range(0, len(z), blk):
        d.feed(z[i:i + blk], rate, dial)
    t0 = last = time.monotonic()
    n = len(out)
    while time.monotonic() - last < 1.5 and time.monotonic() - t0 < 30:
        time.sleep(0.05)
        d.feed(np.zeros(blk, np.complex64), rate, dial)
        if len(out) != n:
            n, last = len(out), time.monotonic()
    for f in out:
        print(f"{f.get('type'):8} {f.get('serial') or '':18} fr {f.get('frame')!s:>10}  {f.get('lat')} {f.get('lon')} "
              f"{f.get('alt')} m  vv {f.get('vv')}  T {f.get('temp')}  sats {f.get('sats')}")
    i = d.info(frames=False)
    print(f"{len(out)} frames, offset {i['offset_hz']} Hz, decoder {d.main.ext.locked if d.main else None}")
    if d.main:
        d.main.close()


if __name__ == "__main__":
    main()

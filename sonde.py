"""Radiosonde decoder (Vaisala RS41; Graw DFM and Meteomodem M20 experimental) of one VFO: position, altitude, speed and climb of weather balloons, 400–406 MHz.

From the complex baseband of the VFO, independent of the listening mode and filter:
channel filter (±10 kHz) -> FM discriminator -> low-pass -> slicer with an adaptive threshold (midpoint of the
signal envelope, so a sonde a few kHz off the dial still works) -> bit clock (PLL of packet.py) -> both polarities
-> framer.

RS41: GFSK 4800 Bd, one frame a second. The frame starts with an 8-byte header, bytes are sent LSB first and are
whitened with a 64-byte mask. Bytes 8–55 are the Reed–Solomon parity of two interleaved RS(255,231) codewords over
the frame from byte 56 (12 wrong bytes of each can be corrected). From byte 57 on, the frame is a chain of blocks
(id, length, data, CRC-16): 0x79 status (frame number, serial number, battery), 0x7C GPS time, 0x7B GPS position
and velocity (ECEF), 0x7A raw measurements, 0x7D raw GPS, 0x7E extra sensors (ozone…), 0x80 encrypted (RS41-SGM).
Temperature and humidity: the raw frequencies of the sensors (block 0x7A) are turned into °C and % with the calibration
the sonde sends in 51 pieces of 16 bytes over the status blocks (one a frame, so the first values come after up to 51 s,
temperature after pieces 3–6). Temperature as in rs41mod (rs1729): reference resistors -> sensor resistance ->
polynomial; humidity: the simple empirical formula of rs41mod (a few % accurate). Pressure (RS41-SGP) is not decoded.
"""
import collections
import datetime
import json
import math
import os
import re
import struct
import threading
import time

import numpy as np

import datafiles
import sonde_ext
from packet import _Clock, _Disc, _Fir
from paths import data as _data
from sdr import lowpass

REC_IQ_DIR = _data("sonde_iq")   # IQ recordings of the VFO channel (POST /api/sonde {"action": "rec_iq"})
REC_IQ_MAX = 900.0               # seconds at most (37.5 kHz complex64: 300 kB/s, 270 MB)

CHAN_HZ = 10000.0            # channel filter: the sonde can be a few kHz off, deviation ±2.4 kHz
ENV_TAU = 0.15               # s: smoothing of the envelope (slicer threshold)
MAX_FRAMES = 300
MAX_SONDES = 50
MAX_TRACK = 6000             # track points kept for each sonde (every 2 s: 3.3 h, a whole flight)
RESTORE_SEC = 24 * 3600      # at the start the sondes of logs written in this time are read back
LOG_SAME_SEC = 6 * 3600      # a sonde heard again within this time goes on in the same log file
LOG_LIST = 200               # logged flights listed
HISTORY_PTS = 300            # map history (1D / 7D): points of a flight path at most
# MULTI: all sondes in the visible part of the spectrum at once, each in its own channel cut from the dongle samples
BAND_HZ = (400.0e6, 406.0e6)
WIDE_MAX = 6                 # channels at most
WIDE_RATE = 30000.0          # channel rate at least (the dongle rate / a power of two), ≥ 3 samples a symbol of M20
WIDE_PASS_HZ = 12000.0       # channel flat up to ± this, tapered to ± rate/2
WIDE_DELAY = 4096            # input samples: delay that makes the channel filter causal (a multiple of the decimation)
WIDE_BLOCK = 131072          # channelizer block (samples) when the dongle blocks are of another size
WIDE_SEG = 2048              # bins of the detection spectrum (1 kHz at 2.048 MS/s)
WIDE_EVAL_S = 1.0            # the spectrum is looked at once a second (max-hold, so the M20 bursts count too)
WIDE_ON_DB = 8.0             # a signal: this much above the noise …
WIDE_WIDTH_HZ = 4000.0       # … and at least this wide (spurs and carriers are narrow)
WIDE_GAP_HZ = 10000.0        # parts of a signal with a gap up to this are one signal (lobes of a strong FSK)
WIDE_MATCH_HZ = 8000.0       # a signal this close to a channel is that channel
WIDE_OWN_HZ = 10000.0        # this close to the tuned frequency it is the VFO's own sonde (decoded from the VFO channel)
WIDE_KEEP_S = 60.0           # a channel without a signal and a frame for this long is dropped
WIDE_QUEUE = 4               # blocks waiting for the worker (more: the oldest are skipped)
LOG_KEYS = ("time", "type", "serial", "frame", "lat", "lon", "alt", "vh", "dir", "vv", "temp", "rh", "temp_h", "pres",
            "sats", "batt", "freq_hz", "dist", "az", "el", "encrypted", "subtype", "cal_n", "gps_time")
LOG_NAME = re.compile(r"^\d{4}-\d\d-\d\d_[\w.-]+\.jsonl$")
TRACK_SEC = 2.0              # a track point at most this often
POS_MIN_SATS = 4             # fewer GPS satellites: no fix, the sonde sends an extrapolated or frozen position
POS_ALT = (-100.0, 45000.0)  # m: a position outside is wrong (a sonde does not go under the ground or to 60 km)
POS_FALL = (60.0, 250.0)     # a fall faster than 60 m/s + alt / 250 (60 at the ground, 140 at 20 km) is a bad GPS fix
POS_JUMP = (2.0, 0.25)       # km + km/s × time from the last good position: farther is a jump of a bad fix
POS_JUMP_RESET = 30          # after this many jumps in a row the new place is believed (the old one was wrong)
POS_KEYS = ("lat", "lon", "alt", "vh", "dir", "vv")
OLD_SEC = 600                # a sonde not heard for this long is shown as lost
GPS_LEAP = 18                # GPS - UTC, seconds

# ---------- RS41 frame ----------

RS41_BAUD = 4800
RS41_HEADER = "0000100001101101010100111000100001000100011010010100100000011111"   # bits as sent
RS41_HDR_BYTES = bytes(int(RS41_HEADER[i * 8:i * 8 + 8][::-1], 2) for i in range(8))   # LSB first
RS41_HDR_ERR = 4             # wrong bits allowed in the 64-bit header
RS41_STD, RS41_EXT = 320, 518   # frame length: standard, extended (frame type 0xF0)
RS41_MASK = bytes((
    0x96, 0x83, 0x3E, 0x51, 0xB1, 0x49, 0x08, 0x98, 0x32, 0x05, 0x59, 0x0E, 0xF9, 0x44, 0xC6, 0x26,
    0x21, 0x60, 0xC2, 0xEA, 0x79, 0x5D, 0x6D, 0xA1, 0x54, 0x69, 0x47, 0x0C, 0xDC, 0xE8, 0x5C, 0xF1,
    0xF7, 0x76, 0x82, 0x7F, 0x07, 0x99, 0xA2, 0x2C, 0x93, 0x7C, 0x30, 0x63, 0xF5, 0x10, 0x2E, 0x61,
    0xD0, 0xBC, 0xB4, 0xB6, 0x06, 0xAA, 0xF4, 0x23, 0x78, 0x6E, 0x3B, 0xAE, 0xBF, 0x7B, 0x4C, 0xC1))
RS41_PARPOS, RS41_MSGPOS, RS41_BLKPOS = 0x08, 0x38, 0x39
RS_R = 24                    # parity bytes of each codeword

CAL_FRAGS, CAL_LEN = 51, 16   # calibration: 51 pieces of 16 bytes, one in each status block
CAL_T = {3, 4, 5, 6}           # pieces with the reference resistors and the coefficients of the temperature sensor
CAL_TH = {3, 4, 18, 19}        # ... of the temperature sensor of the humidity sensor
CAL_RH = CAL_T | {7}           # ... of the humidity sensor
CAL_TYPE = {33, 34}            # sonde type ("RS41-SG", "RS41-SGP")

BLK_STATUS, BLK_MEAS, BLK_GPSPOS, BLK_GPSINFO, BLK_GPSRAW, BLK_XDATA, BLK_EMPTY, BLK_ENCRYPTED = \
    0x79, 0x7A, 0x7B, 0x7C, 0x7D, 0x7E, 0x76, 0x80


# ---------- Reed–Solomon over GF(256), polynomial 0x11D, roots alpha^0 .. alpha^23 ----------

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _div(a, b):
    return 0 if a == 0 else _EXP[(_LOG[a] - _LOG[b]) % 255]


def _peval(p, x):
    """p[i] = coefficient of x^i."""
    y = 0
    for c in reversed(p):
        y = _mul(y, x) ^ c
    return y


def _gen_poly(nroots, b=0):
    g = [1]
    for j in range(nroots):
        r = _EXP[b + j]
        ng = [0] * (len(g) + 1)
        for i, c in enumerate(g):
            ng[i + 1] ^= c                  # x * g
            ng[i] ^= _mul(c, r)             # r * g
        g = ng
    return g                                # g[i] = coefficient of x^i, monic


_GEN = _gen_poly(RS_R)


def rs_encode(data, nroots=RS_R):
    """Parity bytes p of the codeword c = p (x^0 .. x^(n-1)) + data (x^n ...)."""
    rem = [0] * nroots
    for d in reversed(data):                # highest power first
        fb = d ^ rem[-1]
        rem = [0] + rem[:-1]
        if fb:
            for i in range(nroots):
                rem[i] ^= _mul(_GEN[i], fb)
    return rem


def rs_correct(cw, nroots=RS_R, length=None):
    """Corrects the codeword in place (cw[i] = coefficient of x^i, at most 255 bytes, the rest are zeros).
    Returns the number of corrected bytes, or -1 when it cannot be corrected."""
    n = len(cw) if length is None else length
    synd = [_peval(cw, _EXP[j]) for j in range(nroots)]
    if not any(synd):
        return 0
    # Berlekamp–Massey
    lam, prev = [1], [1]
    L, m, bprev = 0, 1, 1
    for k in range(nroots):
        d = synd[k]
        for i in range(1, L + 1):
            if i < len(lam):
                d ^= _mul(lam[i], synd[k - i])
        if d == 0:
            m += 1
            continue
        coef = _div(d, bprev)
        t = lam + [0] * max(0, len(prev) + m - len(lam))
        for i, c in enumerate(prev):
            t[i + m] ^= _mul(coef, c)
        if 2 * L <= k:
            prev, L, bprev, m = lam, k + 1 - L, d, 1
        else:
            m += 1
        lam = t
    while len(lam) > 1 and lam[-1] == 0:
        lam.pop()
    nerr = len(lam) - 1
    if nerr == 0 or nerr > nroots // 2 or L != nerr:
        return -1
    # Chien search: error at position i when lam(alpha^-i) == 0
    pos = [i for i in range(255) if _peval(lam, _EXP[(255 - i) % 255]) == 0]
    if len(pos) != nerr or any(i >= n for i in pos):
        return -1
    # Forney (first root alpha^0): e = X * omega(X^-1) / lam'(X^-1)
    omega = [0] * nroots
    for i, s in enumerate(synd):
        for j, c in enumerate(lam):
            if i + j < nroots:
                omega[i + j] ^= _mul(s, c)
    dlam = [lam[i] if i & 1 else 0 for i in range(1, len(lam))]    # formal derivative
    for i in pos:
        xinv = _EXP[(255 - i) % 255]
        den = _peval(dlam, xinv)
        if den == 0:
            return -1
        cw[i] ^= _mul(_EXP[i], _div(_peval(omega, xinv), den))
    if any(_peval(cw, _EXP[j]) for j in range(nroots)):
        return -1
    return nerr


def crc16(data):
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)."""
    c = 0xFFFF
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


# ---------- geodesy ----------

WGS_A = 6378137.0
WGS_F = 1 / 298.257223563
WGS_E2 = WGS_F * (2 - WGS_F)


def ecef_to_geo(x, y, z):
    """(lat, lon, height above the ellipsoid) of an ECEF point in metres."""
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    if p < 1.0:
        return (90.0 if z >= 0 else -90.0), math.degrees(lon), abs(z) - WGS_A * (1 - WGS_F)
    lat = math.atan2(z, p * (1 - WGS_E2))
    h = 0.0
    for _ in range(6):
        s = math.sin(lat)
        n = WGS_A / math.sqrt(1 - WGS_E2 * s * s)
        h = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1 - WGS_E2 * n / (n + h)))
    return math.degrees(lat), math.degrees(lon), h


def geo_to_ecef(lat, lon, h):
    la, lo = math.radians(lat), math.radians(lon)
    n = WGS_A / math.sqrt(1 - WGS_E2 * math.sin(la) ** 2)
    return ((n + h) * math.cos(la) * math.cos(lo), (n + h) * math.cos(la) * math.sin(lo),
            (n * (1 - WGS_E2) + h) * math.sin(la))


def enu_velocity(lat, lon, vx, vy, vz):
    """(east, north, up) of an ECEF velocity at a place."""
    la, lo = math.radians(lat), math.radians(lon)
    sla, cla, slo, clo = math.sin(la), math.cos(la), math.sin(lo), math.cos(lo)
    e = -slo * vx + clo * vy
    n = -sla * clo * vx - sla * slo * vy + cla * vz
    u = cla * clo * vx + cla * slo * vy + sla * vz
    return e, n, u


def look(qth, lat, lon, alt):
    """Distance (km), azimuth and elevation (degrees) of a point seen from qth = (lat, lon)."""
    q = geo_to_ecef(qth[0], qth[1], 0.0)
    p = geo_to_ecef(lat, lon, alt)
    e, n, u = enu_velocity(qth[0], qth[1], p[0] - q[0], p[1] - q[1], p[2] - q[2])
    rng = math.sqrt(e * e + n * n + u * u)
    return rng / 1000.0, math.degrees(math.atan2(e, n)) % 360.0, math.degrees(math.asin(u / rng)) if rng else 90.0


def gps_utc(week, tow_ms):
    t = datetime.datetime(1980, 1, 6, tzinfo=datetime.timezone.utc) + datetime.timedelta(
        weeks=week, milliseconds=tow_ms) - datetime.timedelta(seconds=GPS_LEAP)
    return t.timestamp()


# ---------- RS41 frame decoding ----------

def _u16(b, i):
    return b[i] | b[i + 1] << 8


def _i16(b, i):
    v = _u16(b, i)
    return v - 0x10000 if v & 0x8000 else v


def _u32(b, i):
    return b[i] | b[i + 1] << 8 | b[i + 2] << 16 | b[i + 3] << 24


def _i32(b, i):
    v = _u32(b, i)
    return v - 0x100000000 if v & 0x80000000 else v


def _u24(b, i):
    return b[i] | b[i + 1] << 8 | b[i + 2] << 16


def _f32(b, i):
    return struct.unpack_from("<f", b, i)[0]


def _rs41_temp(cal, f, f1, f2, co, ct):
    """°C of a platinum sensor: f = its measurement, f1, f2 = the reference resistors rf1, rf2 (cal 0x3D, 0x41);
    co = polynomial at cal[co], ct = calibration at cal[ct] (rs41mod get_T)."""
    rf1, rf2 = _f32(cal, 0x3D), _f32(cal, 0x41)
    if f2 == f1 or rf2 == rf1:
        return None
    p = [_f32(cal, co + 4 * k) for k in range(3)]
    c = [_f32(cal, ct + 4 * k) for k in range(3)]
    g = (f2 - f1) / (rf2 - rf1)
    rb = (f1 * rf2 - f2 * rf1) / (f2 - f1)
    r = (f / g - rb) * c[0]
    t = (p[0] + p[1] * r + p[2] * r * r + c[1]) * (1.0 + c[2])
    return t if math.isfinite(t) and -120.0 < t < 80.0 else None


def _rs41_rh(cal, f, f1, f2, t):
    """Relative humidity, % (rs41mod get_RH: empirical, with a temperature compensation)."""
    h0 = _f32(cal, 0x75)
    if f2 == f1 or not h0 or not math.isfinite(h0):
        return None
    rh = 100.0 * (350.0 / h0 * (f - f1) / (f2 - f1) - 7.5)
    rh -= t / 5.5
    if t < -25.0:
        rh *= 1.0 + (-25.0 - t) / 90.0
    return min(100.0, max(0.0, rh)) if math.isfinite(rh) else None


def rs41_ptu(cal, have, meas):
    """{"temp", "rh", "temp_h"} from the 12 raw values of block 0x7A and the calibration bytes (816) of which the
    pieces in `have` are known; a value is left out while its calibration is missing."""
    out = {}
    t = th = None
    if CAL_T <= have:
        t = _rs41_temp(cal, meas[0], meas[1], meas[2], 0x4D, 0x59)
        if t is not None:
            out["temp"] = round(t, 1)
    if CAL_TH <= have:
        th = _rs41_temp(cal, meas[6], meas[7], meas[8], 0x125, 0x131)
        if th is not None:
            out["temp_h"] = round(th, 1)
    if t is not None and CAL_RH <= have:
        rh = _rs41_rh(cal, meas[3], meas[4], meas[5], t)
        if rh is not None:
            out["rh"] = round(rh, 1)
    return out


def rs41_subtype(cal, have):
    """Sonde type from the calibration ("RS41-SG", "RS41-SGP" = with a pressure sensor) or None."""
    if not CAL_TYPE <= have:
        return None
    t = bytes(cal[0x218:0x220]).split(b"\x00")[0].decode("ascii", "replace").strip()
    return t if t.startswith("RS41") and t.isprintable() else None


def rs41_ecc(frame):
    """Reed–Solomon correction of a descrambled frame (bytearray, changed in place).
    Returns the number of corrected bytes, or -1 when a codeword cannot be corrected."""
    n = len(frame)
    k = (n - RS41_MSGPOS) // 2           # data bytes of each codeword (132 standard, 231 extended)
    total = 0
    for c in range(2):
        cw = [0] * 255
        cw[:RS_R] = frame[RS41_PARPOS + c * RS_R:RS41_PARPOS + (c + 1) * RS_R]
        for i in range(k):
            cw[RS_R + i] = frame[RS41_MSGPOS + 2 * i + c]
        e = rs_correct(cw, RS_R, RS_R + k)
        if e < 0:
            return -1
        if e:
            frame[RS41_PARPOS + c * RS_R:RS41_PARPOS + (c + 1) * RS_R] = bytes(cw[:RS_R])
            for i in range(k):
                frame[RS41_MSGPOS + 2 * i + c] = cw[RS_R + i]
        total += e
    return total


def rs41_blocks(frame):
    """[(id, data, crc ok)] of the frame."""
    out = []
    pos = RS41_BLKPOS
    while pos + 4 <= len(frame):
        bid, ln = frame[pos], frame[pos + 1]
        end = pos + 2 + ln
        if end + 2 > len(frame):
            break
        data = bytes(frame[pos + 2:end])
        out.append((bid, data, crc16(data) == _u16(frame, end)))
        pos = end + 2
        if bid == BLK_EMPTY:
            break
    return out


def rs41_parse(frame):
    """Fields of a descrambled, corrected RS41 frame; None when no block has a good CRC."""
    d = {"type": "RS41", "blocks_ok": 0, "blocks_bad": 0}
    for bid, data, ok in rs41_blocks(frame):
        if not ok:
            d["blocks_bad"] += 1
            continue
        d["blocks_ok"] += 1
        if bid == BLK_STATUS and len(data) >= 11:
            d["frame"] = _u16(data, 0)
            serial = data[2:10].decode("ascii", "replace").strip("\x00 ")
            if serial.isalnum():
                d["serial"] = serial
            d["batt"] = data[10] / 10.0
            if len(data) >= 40 and data[23] < CAL_FRAGS:
                d["cal_frag"] = data[23]
                d["_cal"] = (data[23], bytes(data[24:40]))
        elif bid == BLK_MEAS and len(data) >= 36:
            d["_meas"] = [_u24(data, 3 * k) for k in range(12)]
        elif bid == BLK_GPSINFO and len(data) >= 6:
            week, tow = _u16(data, 0), _u32(data, 2)
            if 1000 < week < 4000:
                d["gps_time"] = gps_utc(week, tow)
        elif bid == BLK_GPSPOS and len(data) >= 21:
            x, y, z = _i32(data, 0) / 100.0, _i32(data, 4) / 100.0, _i32(data, 8) / 100.0
            vx, vy, vz = _i16(data, 12) / 100.0, _i16(data, 14) / 100.0, _i16(data, 16) / 100.0
            d["sats"] = data[18]
            if 6.0e6 < math.sqrt(x * x + y * y + z * z) < 6.5e6 + 60000:
                lat, lon, alt = ecef_to_geo(x, y, z)
                e, n, u = enu_velocity(lat, lon, vx, vy, vz)
                d.update(lat=round(lat, 6), lon=round(lon, 6), alt=round(alt, 1), vh=round(math.hypot(e, n), 2),
                         dir=round(math.degrees(math.atan2(e, n)) % 360.0, 1), vv=round(u, 2))
        elif bid == BLK_XDATA:
            d["xdata"] = data.hex()
        elif bid == BLK_ENCRYPTED:
            d["encrypted"] = True
    return d if d["blocks_ok"] else None


def rs41_build(fields, extended=False):
    """Bits of one RS41 frame as sent (tests): fields = serial, frame, batt, lat, lon, alt, vel (e, n, u), week, tow."""
    n = RS41_EXT if extended else RS41_STD
    f = bytearray(n)
    f[:8] = bytes(a ^ b for a, b in zip(RS41_HDR_BYTES, RS41_MASK))
    f[RS41_MSGPOS] = 0xF0 if extended else 0x0F
    blocks = []
    st = bytearray(40)
    st[0:2] = fields.get("frame", 1).to_bytes(2, "little")
    st[2:10] = fields.get("serial", "S1234567").encode().ljust(8, b"\0")[:8]
    st[10] = int(round(fields.get("batt", 2.9) * 10))
    if "cal" in fields:
        st[23] = fields["cal"][0]
        st[24:40] = fields["cal"][1]
    blocks.append((BLK_STATUS, bytes(st)))
    meas = bytearray(42)
    for k, v in enumerate(fields.get("meas", ())):
        meas[3 * k:3 * k + 3] = int(v).to_bytes(3, "little")
    meas = bytes(meas)
    blocks.append((BLK_MEAS, meas))
    gi = bytearray(30)
    gi[0:2] = fields.get("week", 2400).to_bytes(2, "little")
    gi[2:6] = fields.get("tow", 0).to_bytes(4, "little")
    blocks.append((BLK_GPSINFO, bytes(gi)))
    blocks.append((BLK_GPSRAW, bytes(0x59)))   # GPS position then at 0x112, as in the real frames
    x, y, z = geo_to_ecef(fields["lat"], fields["lon"], fields["alt"])
    la, lo = math.radians(fields["lat"]), math.radians(fields["lon"])
    ve, vn, vu = fields.get("vel", (0.0, 0.0, 0.0))
    vx = -math.sin(lo) * ve - math.sin(la) * math.cos(lo) * vn + math.cos(la) * math.cos(lo) * vu
    vy = math.cos(lo) * ve - math.sin(la) * math.sin(lo) * vn + math.cos(la) * math.sin(lo) * vu
    vz = math.cos(la) * vn + math.sin(la) * vu
    gp = bytearray(21)
    for i, v in enumerate((x, y, z)):
        gp[4 * i:4 * i + 4] = int(round(v * 100)).to_bytes(4, "little", signed=True)
    for i, v in enumerate((vx, vy, vz)):
        gp[12 + 2 * i:14 + 2 * i] = int(round(v * 100)).to_bytes(2, "little", signed=True)
    gp[18] = fields.get("sats", 9)
    blocks.append((BLK_GPSPOS, bytes(gp)))
    pos = RS41_BLKPOS
    for bid, data in blocks:
        f[pos], f[pos + 1] = bid, len(data)
        f[pos + 2:pos + 2 + len(data)] = data
        f[pos + 2 + len(data):pos + 4 + len(data)] = crc16(data).to_bytes(2, "little")
        pos += len(data) + 4
    rest = n - pos - 4
    if rest >= 0:
        f[pos], f[pos + 1] = BLK_EMPTY, rest
        f[pos + 4 + rest - 2:pos + 4 + rest] = crc16(bytes(rest)).to_bytes(2, "little")
    k = (n - RS41_MSGPOS) // 2
    for c in range(2):
        par = rs_encode([f[RS41_MSGPOS + 2 * i + c] for i in range(k)])
        f[RS41_PARPOS + c * RS_R:RS41_PARPOS + (c + 1) * RS_R] = bytes(par)
    raw = bytes(b ^ RS41_MASK[i % 64] for i, b in enumerate(f))
    return [(byte >> i) & 1 for byte in raw for i in range(8)]


class Rs41Framer:
    """Bits of one polarity -> descrambled frames (bytearray)."""

    def __init__(self):
        self.buf = None
        self.need = RS41_STD
        self.cur = 0
        self.nb = 0
        self.headers = 0
        self._hdr = int(RS41_HEADER, 2)
        self._sr = 0

    def feed(self, bits):
        out = []
        for b in bits:
            if self.buf is None:
                self._sr = ((self._sr << 1) | b) & 0xFFFFFFFFFFFFFFFF
                if bin(self._sr ^ self._hdr).count("1") <= RS41_HDR_ERR:
                    self.headers += 1
                    self.buf = bytearray(RS41_HDR_BYTES)
                    self.need, self.cur, self.nb = RS41_STD, 0, 0
                continue
            self.cur |= b << self.nb
            self.nb += 1
            if self.nb < 8:
                continue
            self.buf.append(self.cur)
            self.cur, self.nb = 0, 0
            if len(self.buf) == RS41_MSGPOS + 1:
                if self.buf[RS41_MSGPOS] ^ RS41_MASK[RS41_MSGPOS % 64] == 0xF0:
                    self.need = RS41_EXT
            if len(self.buf) >= self.need:
                out.append(bytearray(x ^ RS41_MASK[i % 64] for i, x in enumerate(self.buf)))
                self.buf = None
                self._sr = 0
        return out


class _Path:
    """One symbol rate: low-pass -> threshold at the envelope midpoint -> PLL -> framers of both polarities."""

    def __init__(self, fs, baud, make_framer, kind):
        self.fs = fs
        self.kind = kind
        self.lp = _Fir(lowpass(0.7 * baud, fs, 47))
        self.clock = _Clock(fs / baud)
        self.framers = (make_framer(), make_framer())
        self.hi = None
        self.lo = None
        self.offset = 0.0       # midpoint of the discriminator output: offset of the sonde from the dial (Hz)

    def process(self, f):
        y = self.lp.process(f)
        if not len(y):
            return []
        a = min(1.0, len(y) / self.fs / ENV_TAU)
        hi, lo = float(np.percentile(y, 95)), float(np.percentile(y, 5))
        self.hi = hi if self.hi is None else self.hi + a * (hi - self.hi)
        self.lo = lo if self.lo is None else self.lo + a * (lo - self.lo)
        self.offset = 0.5 * (self.hi + self.lo)
        bits = self.clock.process(y - self.offset)
        out = []
        for inv, fr in enumerate(self.framers):
            for frame in fr.feed(bits if not inv else [b ^ 1 for b in bits]):
                out.append((self.kind, frame, bool(inv)))
        return out

    @property
    def headers(self):
        return sum(f.headers for f in self.framers)


# ---------- Graw DFM (DFM-06 / 09 / 17), experimental ----------

DFM_BAUD = 2500              # symbols/s, Manchester: 1250 bit/s
DFM_RAWHEADER = "10011010100110010101101001010101"   # the 16 header bits 0100010111001111 as symbols
DFM_HDR_ERR = 2              # wrong symbols allowed in the header
DFM_BITS = 264               # after the header: configuration (7 codewords) + two data blocks (13 codewords each)
_DFM_A = ((0, 1, 1, 1), (1, 0, 1, 1), (1, 1, 0, 1), (1, 1, 1, 0))    # Hamming(8,4): H = [A | I]
_DFM_HE = (0x7, 0xB, 0xD, 0xE, 0x8, 0x4, 0x2, 0x1)                    # columns of H


def _dfm_deinterleave(bits, n):
    """n codewords of 8 bits sent column by column."""
    return [[bits[n * j + i] for j in range(8)] for i in range(n)]


def _dfm_hamming(cw):
    """(data nibble, corrected bit count) of an 8-bit codeword, or (None, 0) when it cannot be corrected."""
    syn = 0
    for r in range(4):
        v = sum(_DFM_A[r][k] * cw[k] for k in range(4)) + cw[4 + r]
        syn = (syn << 1) | (v & 1)
    fixed = 0
    if syn:
        if syn not in _DFM_HE:
            return None, 0
        cw = list(cw)
        cw[_DFM_HE.index(syn)] ^= 1
        fixed = 1
    return cw[0] << 3 | cw[1] << 2 | cw[2] << 1 | cw[3], fixed


def dfm_decode(bits):
    """The 264 bits after the header -> {"conf": [nibbles] or None, "dat": [(id, 48-bit value)], "fixed", "bad"}."""
    out = {"conf": None, "dat": [], "fixed": 0, "bad": 0}
    for off, n in ((0, 7), (56, 13), (160, 13)):
        nibs = []
        for cw in _dfm_deinterleave(bits[off:off + 8 * n], n):
            v, f = _dfm_hamming(cw)
            if v is None:
                nibs = None
                out["bad"] += 1
                break
            out["fixed"] += f
            nibs.append(v)
        if nibs is None:
            continue
        if n == 7:
            out["conf"] = nibs
        else:
            val = 0
            for v in nibs[:12]:
                val = val << 4 | v
            out["dat"].append((nibs[12], val))
    return out


def dfm_build(dats, conf=(0, 1, 2, 3, 4, 5, 6)):
    """Symbols of one DFM frame (tests): dats = two (id, 48-bit value)."""
    def enc(nib):
        d = [(nib >> (3 - k)) & 1 for k in range(4)]
        return d + [sum(_DFM_A[r][k] * d[k] for k in range(4)) & 1 for r in range(4)]

    def block(nibs):
        cws = [enc(v) for v in nibs]
        n = len(cws)
        return [cws[i][j] for j in range(8) for i in range(n)]

    bits = block(conf)
    for fid, val in dats:
        bits += block([(val >> (44 - 4 * k)) & 15 for k in range(12)] + [fid])
    sym = [int(c) for c in DFM_RAWHEADER]
    for b in bits:
        sym += [0, 1] if b else [1, 0]
    return sym


# DFM serial number, type, temperature and battery from the configuration blocks, after rs1729's dfm09mod.c
# (conf_out, get_Temp; https://github.com/rs1729/RS, author zilog80). A configuration block is 7 nibbles: channel,
# then 6 nibbles of data. Channels 0-8 are measurements (24-bit floats). The serial comes in the channel after the
# "null" channel or in the highest channel followed by the nibble C (DFM-09/17) or 0 (PS-15): two blocks with one
# 16-bit half each (nibble 6 = which half); DFM-06 sends its whole serial (hex) in one channel after the null channel
# 0x5x. Here a serial is taken when it has come twice the same (rs1729 takes the first one). The channel of the serial
# is the type: 6 DFM-06, 7/8 DFM-06P (with an SN6) or PS-15, A DFM-09 (DFM-17 from serial 23000000), B DFM-17,
# C DFM-09P or DFM-17 (by measurement 6), D DFM-17P.
DFM_T_COEF = (1.09698417e-03, 2.39564629e-04, 2.48821437e-06, 5.84354921e-08)   # Steinhart-Hart of the sensor


def _dfm_fl24(d):
    """24-bit DFM measurement: 4-bit exponent, 20-bit value."""
    return (d & 0xFFFFF) / 2.0 ** ((d >> 20) & 0xF)


def _nibval(nibs, a, b):
    v = 0
    for x in nibs[a:b]:
        v = v << 4 | x
    return v


def _dfm_reset(cs):
    cs["cfg"] = set()
    cs["ptu_out"] = 0
    cs["sn_out"] = ""


def dfm_conf(cs, nibs):
    """One configuration block (7 nibbles) into the state cs of a DFM channel (port of rs1729's conf_out)."""
    cs.setdefault("cfg", set())
    cs.setdefault("meas", {})
    cid = nibs[0]
    b8, v20, v24 = _nibval(nibs, 0, 2), _nibval(nibs, 2, 7), _nibval(nibs, 1, 7)
    if cid > 4 and v20 == 0:
        cs["nul_ch"] = b8
    nul = cs.get("nul_ch", 0)
    dfm6 = (nul & 0xF0) == 0x50 and (nul & 0x0F)
    if dfm6:
        cs["ptu_out"] = 6
    if dfm6 and (cs.get("typ", 0) & 0xF) > 6:
        cs["typ"], cs["max_ch"] = 0, cid
        _dfm_reset(cs)
    if cid > 5 and cid > cs.get("max_ch", 0) and nibs[1] == 0xC:
        cs["max_ch"] = cid
    if cid > 5 and (cid == (nul >> 4) + 1 or cid == cs.get("max_ch", 0)):
        sn_ch = cid
        if (nul & 0x58) == 0x58:                         # DFM-06 (0x5A, 0x5B) / DFM-06P (0x7A, 0x7B)
            sn6 = v24
            if sn6 == cs.get("sn6") and sn6 != 0:
                cs["typ"], cs["ptu_out"], cs["sn_out"] = 0x100 | sn_ch, 6, f"{sn6:X}"
            else:
                cs["typ"] = 0
                _dfm_reset(cs)
            cs["sn6"] = sn6
        elif nibs[1] in (0xC, 0x0):                      # DFM-09 / 17 (C), PS-15 (0)
            hl = nibs[6]
            if hl < 2:
                if cs.get("sn_ch") != sn_ch:
                    cs["chx"], cs["chxbit"] = [0, 0], 0
                    _dfm_reset(cs)
                cs["sn_ch"] = sn_ch
                cs.setdefault("chx", [0, 0])[hl] = _nibval(nibs, 2, 6)
                cs["chxbit"] = cs.get("chxbit", 0) | 1 << hl
                if cs["chxbit"] == 3:
                    sn = cs["chx"][0] << 16 | cs["chx"][1]
                    if sn == cs.get("sn_x"):
                        cs["typ"], cs["sn"] = 0x100 | sn_ch, sn
                        cs["ptu_out"] = sn_ch if 0xA <= sn_ch <= 0xD else 0
                        if not cs.get("sn6") or sn_ch >= 0xA:
                            cs["sn_out"] = str(sn)
                    elif cs.get("sn_x") is not None:
                        cs["typ"] = 0
                        _dfm_reset(cs)
                    cs["sn_x"], cs["chxbit"] = sn, 0
    if cid <= 8:
        cs["cfg"].add(cid)
        cs["meas"][cid] = _dfm_fl24(v24)
    ptu = cs.get("ptu_out", 0)
    if ptu >= 0xA:                                       # DFM-09 / 17 (STM32): battery in channel 5 (7 with 'P')
        if cid == (7 if _dfm_sensor(cs) == "P" else 5):
            cs["batt"] = _nibval(nibs, 2, 6) / 1000.0


def _dfm_cfgchk(cs):
    ptu, cfg = cs.get("ptu_out", 0), cs.get("cfg", set())
    if ptu < 5:
        return False
    need = set(range(6)) | ({6, 7} if ptu >= 7 else set()) | ({8} if ptu >= 8 else set())
    return need <= cfg


def _dfm_sensor(cs):
    ptu, meas = cs.get("ptu_out", 0), cs.get("meas", {})
    if ptu >= 0xD or (ptu >= 0xC and meas.get(6, 1e9) < 220e3):
        return "P"
    if ptu == 6 and (cs.get("typ", 0) & 0xF) == 8:
        return "P"
    return "T"


def dfm_info(cs):
    """{serial (as on the label, "" while unknown), subtype (DFM06, DFM06P, PS15, DFM09, DFM09P, DFM17, DFM17P),
    temp °C, batt V} of a DFM channel."""
    typ, sn, sens = cs.get("typ", 0) & 0xF, cs.get("sn", 0), _dfm_sensor(cs)
    name = {0x6: "DFM06", 0xB: "DFM17", 0xD: "DFM17P"}.get(typ)
    if typ in (0x7, 0x8):
        name = "DFM06P" if cs.get("sn6") else "PS15"
    elif typ == 0xA:
        name = "DFM17" if sn >= 23000000 else "DFM09"
    elif typ == 0xC:
        name = "DFM09P" if sens == "P" else "DFM17"
    out = {"serial": cs.get("sn_out", ""), "subtype": name if cs.get("sn_out") else None, "temp": None,
           "batt": cs.get("batt")}
    ptu = cs.get("ptu_out", 0)
    if ptu and _dfm_cfgchk(cs):
        rf = 220e3
        if (ptu in (0xB, 0xC) and sens == "T") or ptu >= 0xD or (ptu == 0xA and sn >= 23000000):
            rf = 332e3
        meas = cs["meas"]
        a, b, c = (1, 5, 6) if sens == "P" else (0, 3, 4)
        f, f1, f2 = meas[a], meas[b], meas[c]
        if f * f1 * f2:
            r = (f - f1) / (f2 / rf)
            if r > 0:
                lr = math.log(r)
                p0, p1, p2, p3 = DFM_T_COEF
                t = 1.0 / (p0 + p1 * lr + p2 * lr * lr + p3 * lr ** 3) - 273.15
                if -100 < t < 60:
                    out["temp"] = round(t, 1)
    return out


class DfmFramer:
    """Manchester symbols of one polarity -> decoded frames (dfm_decode)."""

    def __init__(self):
        self._hdr = int(DFM_RAWHEADER, 2)
        self._sr = 0
        self.buf = None
        self.headers = 0

    def feed(self, syms):
        out = []
        for b in syms:
            if self.buf is None:
                self._sr = ((self._sr << 1) | b) & 0xFFFFFFFF
                if bin(self._sr ^ self._hdr).count("1") <= DFM_HDR_ERR:
                    self.headers += 1
                    self.buf = []
                continue
            self.buf.append(b)
            if len(self.buf) == 2 * DFM_BITS:
                out.append(dfm_decode(self.buf[1::2]))     # symbols 10 = bit 0, 01 = bit 1: the second symbol
                self.buf = None
                self._sr = 0
        return out


# ---------- Meteomodem M10 / M20 ----------
# The frame layouts, checksum and serial numbers follow rs1729's m10mod.c / m20mod.c (https://github.com/rs1729/RS,
# also in radiosonde_auto_rx/demod/mod); the M20 was found and checked on a real sonde (403.5 MHz, 2026-11-15).
# Both send ~9600 symbols/s (M10 9615): header (32 symbols), then the bytes as biphase-M symbols (a bit is 1 when the
# first symbols of two neighbouring pairs are equal), MSB first. Byte 0 = length L, byte 1 = type (0x20 M20, 0x9F M10),
# the frame is L + 1 bytes with the checksum in bytes L-1, L over bytes 0..L-2. No error correction.
# Needs a VFO rate of 2.048 MS/s or more (channel samples >= 32 kHz, >= 3.3 per symbol).

M20_BAUD = 9600
M20_HEADER = "10011001100110010100110010011001"   # symbols; the same header for M10 and M20
M20_HDR_ERR = 2
M20_LEN = 70                 # M20: bytes 0x00-0x45, length 0x45, checksum at 0x44-0x45
M20_CHECK = 0x44
M10_LEN = 0x65               # M10: bytes 0x00-0x64, length 0x64
MM_MAX = 0x77                # the longest frame collected (M10 with aux data: length 0x76)
M10_DEG = 360.0 / 2 ** 32    # M10 (Trimble) latitude / longitude unit


def m10_check(data):
    """Checksum of Meteomodem M10 / M20 (m10mod / m20mod by rs1729)."""
    c = 0
    for b in data:
        c1 = c & 0xFF
        b = ((b >> 1) | ((b & 1) << 7)) & 0xFF
        b ^= (b >> 2) & 0xFF
        t6 = (c & 1) ^ ((c >> 2) & 1) ^ ((c >> 4) & 1)
        t7 = ((c >> 1) & 1) ^ ((c >> 3) & 1) ^ ((c >> 5) & 1)
        t = (c & 0x3F) | (t6 << 6) | (t7 << 7)
        s = (c >> 7) & 0xFF
        s ^= (s >> 2) & 0xFF
        c = ((c1 << 8) | (b ^ t ^ s)) & 0xFFFF
    return c


def mm_check_ok(f):
    """Length byte and checksum of a Meteomodem frame (bytes from the length byte on)."""
    n = f[0] if f else 0
    if n < 0x20 or len(f) < n + 1:
        return False
    return m10_check(f[:n - 1]) == (f[n - 1] << 8 | f[n])


def m20_symbols_to_bytes(syms):
    """Header + frame symbols -> bytes (the 2 header bytes first)."""
    first = syms[0::2]
    out, cur, n, prev = bytearray(), 0, 0, None
    for s in first:                      # pair k = bit k (bit 0 has no neighbour: its value does not matter)
        cur = (cur << 1) | (1 if s == prev else 0)
        n += 1
        if n == 8:
            out.append(cur)
            cur, n = 0, 0
        prev = s
    return out


def mm_symbols(f):
    """Symbols of a Meteomodem frame (header + bytes, checksum filled in) for the tests."""
    n = f[0]
    c = m10_check(f[:n - 1])
    f[n - 1], f[n] = c >> 8, c & 0xFF
    hdr = [int(c) for c in M20_HEADER]
    prev = hdr[-2]                       # first symbol of the last header pair
    syms = list(hdr)
    for byte in f:
        for i in range(7, -1, -1):
            s = prev if (byte >> i) & 1 else 1 - prev
            syms += [s, 1 - s]
            prev = s
    return syms


def m20_build(fields):
    """Symbols of one M20 frame for the tests."""
    f = bytearray(M20_LEN)
    f[0], f[1] = 0x45, 0x20
    f[0x08:0x0B] = int(round(fields["alt"] * 100)).to_bytes(3, "big")
    f[0x0B:0x0D] = int(round(fields["ve"] * 100)).to_bytes(2, "big", signed=True)
    f[0x0D:0x0F] = int(round(fields["vn"] * 100)).to_bytes(2, "big", signed=True)
    f[0x0F:0x12] = int(fields["tow"]).to_bytes(3, "big")
    f[0x12:0x15] = bytes(fields.get("sn", bytes((0xC2, 0x5C, 0x2E))))
    f[0x15] = fields.get("frame", 0) & 0xFF
    f[0x18:0x1A] = int(round(fields.get("vu", 0) * 100)).to_bytes(2, "big", signed=True)
    f[0x1A:0x1C] = int(fields["week"]).to_bytes(2, "big")
    f[0x1C:0x20] = int(round(fields["lat"] * 1e6)).to_bytes(4, "big", signed=True)
    f[0x20:0x24] = int(round(fields["lon"] * 1e6)).to_bytes(4, "big", signed=True)
    f[0x26] = fields.get("batt_raw", 190)
    return mm_symbols(f)


def m10_build(fields):
    """Symbols of one M10 frame (Trimble GPS) for the tests."""
    f = bytearray(M10_LEN)
    f[0], f[1], f[2] = 0x64, 0x9F, 0x20
    f[0x04:0x06] = int(round(fields["ve"] * 200)).to_bytes(2, "big", signed=True)
    f[0x06:0x08] = int(round(fields["vn"] * 200)).to_bytes(2, "big", signed=True)
    f[0x08:0x0A] = int(round(fields["vu"] * 200)).to_bytes(2, "big", signed=True)
    f[0x0A:0x0E] = int(fields["tow_ms"]).to_bytes(4, "big")
    f[0x0E:0x12] = int(round(fields["lat"] / M10_DEG)).to_bytes(4, "big", signed=True)
    f[0x12:0x16] = int(round(fields["lon"] / M10_DEG)).to_bytes(4, "big", signed=True)
    f[0x16:0x1A] = int(round(fields["alt"] * 1000)).to_bytes(4, "big", signed=True)
    f[0x1E] = fields.get("sats", 9)
    f[0x1F] = 18
    f[0x20:0x22] = int(fields["week"]).to_bytes(2, "big")
    f[0x45:0x47] = int(fields.get("batt_adc", 466)).to_bytes(2, "little")
    f[0x5D:0x62] = bytes(fields.get("sn", bytes((0x01, 0x00, 0x85, 0x2A, 0x41))))
    f[0x62] = fields.get("frame", 0) & 0xFF
    return mm_symbols(f)


def m20_serial(b):
    """Serial of an M20 as on its label (rs1729's m20mod get_SN): bytes 0x12-0x14 -> e.g. 507-2-02967; None for 0."""
    sn = b[2] << 16 | b[1] << 8 | b[0]
    if sn == 0:
        return None
    ym = sn & 0x7F
    return f"{ym // 12}{ym % 12 + 1:02d}-{((sn >> 7) & 7) + 1}-{(sn >> 23) & 1}{(sn >> 10) & 0x1FFF:04d}"


def m10_serial(b):
    """Serial of an M10 as on its label (rs1729's m10mod get_SN): bytes 0x5D-0x61 -> e.g. 805-1-20554."""
    w = b[3] | b[4] << 8
    return f"{(b[2] >> 4) & 0xF:X}{b[2] & 0xF:02d}-{b[0] & 0xF:X}-{(w >> 13) & 7}{w & 0x1FFF:04d}"


# Temperature, humidity and pressure of M10 / M20 after rs1729's m10mod.c / m20mod.c (get_Temp, get_Tntc2, get_RH,
# get_P; the M20 humidity is DF9DQ's formula from ra-firmware). Main sensor: NTC Shibaura PB5-41E in a divider of
# 3 ranges, Steinhart-Hart; humidity sensor temperature: SMD NTC 2.2 kΩ.
MM_T_COEF = (1.07303516e-03, 2.41296733e-04, 2.26744154e-06, 6.52855181e-08)
MM_RS = (12.1e3, 36.5e3, 475.0e3)          # series resistor of each range
MM_RP = (1e20, 330.0e3, 2000.0e3)          # parallel resistor of each range
M10_TH_COEF = (4.42606809e-03, -6.58184309e-04, 8.95735557e-05, -2.84347503e-06)


def _sh(r, p):
    lr = math.log(r)
    return 1.0 / (p[0] + p[1] * lr + p[2] * lr * lr + p[3] * lr ** 3) - 273.15


def _mm_ntc(adc, sc):
    """Main temperature °C from the ADC value of range sc, or None."""
    if not 0 < adc < 4095 or sc > 2:
        return None
    x = (4095.0 - adc) / adc
    r = MM_RS[sc] / (x - MM_RS[sc] / MM_RP[sc])
    if r <= 0:
        return None
    t = _sh(r, MM_T_COEF)
    return round(t, 1) if -120.0 <= t <= 60.0 else None


def m20_ptu(f):
    """{temp, rh, temp_h, pres} of an M20 frame (the ones that are valid)."""
    out = {}
    adc = f[0x05] << 8 | f[0x04]
    sc = 2 if adc > 8191 else 1 if adc > 4095 else 0
    t = _mm_ntc(adc - 4096 * sc, sc)
    if t is not None:
        out["temp"] = t
    adc = f[0x07] << 8 | f[0x06]
    th = None
    if 0 < adc < 4095:
        r = 22.1e3 / ((4095.0 - adc) / adc)
        th = 1.0 / (1.0 / 298.15 + 1.0 / 3650.0 * math.log(r / 2.2e3)) - 273.15
        if -100 < th < 60:
            out["temp_h"] = round(th, 1)
        else:
            th = None
    hum, cal = f[0x03] << 8 | f[0x02], f[0x30] << 8 | f[0x2F]
    if th is not None and hum < 48000:
        x = (hum + 80000.0) * (6.4e8 / (cal + 80000.0)) * (1.0 - 5.8e-4 * (th - 25.0))
        x = 4.16e9 / x
        x = 10.087 * x ** 3 - 211.62 * x * x + 1388.2 * x - 2797.0
        if -20.0 < x < 120.0:
            out["rh"] = round(min(100.0, max(0.0, x)), 1)
    fw = f[0x43] if f[0x43] <= 0x20 else 0
    val = (f[0x25] << 8 | f[0x24]) << 8 | (f[0x16] if fw >= 7 else 0)
    if 0 < val and val / 4096.0 <= 2560.0:
        out["pres"] = round(val / 4096.0, 1)
    return out


def m10_ptu(f):
    """{temp, rh, temp_h} of an M10 frame (the ones that are valid)."""
    out = {}
    t = _mm_ntc(((f[0x40] << 8 | f[0x3F]) - 0xA000) & 0xFFFF, f[0x3E])
    if t is not None:
        out["temp"] = t
    adc = f[0x5A] << 8 | f[0x59]
    if 0 < adc < 4095:
        th = _sh(22.1e3 / ((4095.0 - adc) / adc), M10_TH_COEF)
        if -100 < th < 60:
            out["temp_h"] = round(th, 1)
    c55 = (f[0x32] | f[0x33] << 8 | f[0x34] << 16) / 1000.0
    crh = (f[0x35] | f[0x36] << 8 | f[0x37] << 16) / 1000.0
    if t is not None and c55 > 0 and crh > 0:
        rh = (crh / c55 - 0.8955) / 0.002                    # U.P.S.I. sensor, linear
        if t < 0.0:
            rh += 0.0 - t / 5.5                              # rs1729's empirical temperature correction
        if t < -30.0:
            rh *= 1.0 + (-30.0 - t) / 75.0
        out["rh"] = round(min(100.0, max(0.0, rh)), 1)
    return out


def _mm_vel(d, ve, vn, vu):
    d.update(vv=round(vu, 2), vh=round(math.hypot(ve, vn), 2), dir=round(math.degrees(math.atan2(ve, vn)) % 360, 1))


def m20_parse(f):
    """Fields of an M20 frame with a good checksum, or None."""
    if len(f) < M20_LEN or f[0] != 0x45 or f[1] != 0x20 or not mm_check_ok(f):
        return None
    alt = int.from_bytes(f[0x08:0x0B], "big") / 100.0
    tow = int.from_bytes(f[0x0F:0x12], "big")
    week = int.from_bytes(f[0x1A:0x1C], "big")
    lat = int.from_bytes(f[0x1C:0x20], "big", signed=True) / 1e6
    lon = int.from_bytes(f[0x20:0x24], "big", signed=True) / 1e6
    if not (abs(lat) <= 90 and abs(lon) <= 180 and -500 < alt < 50000):
        return None
    sn = m20_serial(f[0x12:0x15])
    d = {"type": "M20", "serial": "M20-" + (sn or f[0x12:0x15].hex().upper()), "frame": f[0x15],
         "lat": round(lat, 6), "lon": round(lon, 6), "alt": round(alt, 1), "batt": round(f[0x26] * 3.3 / 255, 2)}
    _mm_vel(d, *(int.from_bytes(f[k:k + 2], "big", signed=True) / 100.0 for k in (0x0B, 0x0D, 0x18)))
    if week < 1304:
        week += 1024
    if 1000 < week < 4000 and tow < 7 * 86400:
        d["gps_time"] = gps_utc(week, tow * 1000)
    d.update(m20_ptu(f))
    if sn is None:
        d["serial_raw"] = True           # 000-0-00000: the serial is not known (not sent to SondeHub)
    return d


def m10_parse(f):
    """Fields of an M10 frame (Trimble GPS, type 0x9F) with a good checksum, or None."""
    if len(f) < M10_LEN or f[1] != 0x9F or f[0] not in (0x64, 0x76) or not mm_check_ok(f):
        return None
    tow_ms = int.from_bytes(f[0x0A:0x0E], "big")
    lat = int.from_bytes(f[0x0E:0x12], "big", signed=True) * M10_DEG
    lon = int.from_bytes(f[0x12:0x16], "big", signed=True) * M10_DEG
    alt = int.from_bytes(f[0x16:0x1A], "big", signed=True) / 1000.0
    week = int.from_bytes(f[0x20:0x22], "big")
    if not (abs(lat) <= 90 and abs(lon) <= 180 and -500 < alt < 50000):
        return None
    d = {"type": "M10", "serial": "M10-" + m10_serial(f[0x5D:0x62]), "frame": f[0x62],
         "lat": round(lat, 6), "lon": round(lon, 6), "alt": round(alt, 1), "sats": f[0x1E],
         "batt": round(2.709 * (f[0x46] << 8 | f[0x45]) * 2.5 / 1023.0, 2)}
    _mm_vel(d, *(int.from_bytes(f[k:k + 2], "big", signed=True) / 200.0 for k in (0x04, 0x06, 0x08)))
    d.update(m10_ptu(f))
    if week < 1304:
        week += 1024
    if 1000 < week < 4000 and tow_ms < 7 * 86400 * 1000:
        d["gps_time"] = gps_utc(week, tow_ms)
    return d


def mm_parse(f):
    """An M10 or M20 frame -> fields, or None (wrong checksum, unknown type)."""
    if len(f) < 2:
        return None
    return m20_parse(f) if f[1] == 0x20 else m10_parse(f) if f[1] == 0x9F else None


class M20Framer:
    """Symbols of one polarity -> Meteomodem frames (M10 / M20, as long as their length byte says; mm_parse
    checks them)."""

    def __init__(self):
        self._hdr = int(M20_HEADER, 2)
        self._sr = 0
        self.buf = None
        self.need = 0
        self.headers = 0

    def feed(self, syms):
        out = []
        h = len(M20_HEADER)
        for b in syms:
            if self.buf is None:
                self._sr = ((self._sr << 1) | b) & 0xFFFFFFFF
                if bin(self._sr ^ self._hdr).count("1") <= M20_HDR_ERR:
                    self.headers += 1
                    self.buf = [int(c) for c in M20_HEADER]
                    self.need = h + 16 * MM_MAX
                continue
            self.buf.append(b)
            if len(self.buf) == h + 16:          # the length byte: collect only as many bytes
                n = m20_symbols_to_bytes(self.buf)[-1]
                self.need = h + 16 * min(MM_MAX, max(M20_LEN, n + 1))
            elif len(self.buf) >= self.need:
                out.append(m20_symbols_to_bytes(self.buf)[2:])
                self.buf = None
                self._sr = 0
        return out


def _s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def _s16(v):
    return v - (1 << 16) if v & 0x8000 else v


class _Demod:
    """One channel of baseband: the external decoders of rs1729 (sonde_ext.ExtChannel), all types."""

    def __init__(self, fs):
        self.fs = fs
        self.ext = sonde_ext.ExtChannel(fs)
        self.paths = []                      # the Python demodulators are no longer used (rs1729 decodes)
        self.dfm = {}
        self.dfm_id = {}
        self.offset = None

    @property
    def headers(self):
        return self.ext.headers

    def process(self, base):
        """[(decoder, JSON dict)] of the frames decoded since the last call."""
        return self.ext.process(base)

    def update_offset(self):
        """Offset of the signal from the channel centre, once a frame was decoded."""
        if self.ext.frames:
            self.offset = self.ext.offset

    def close(self):
        self.ext.close()


class _Channelizer:
    """MULTI: cuts narrow channels out of the dongle samples with one FFT a block (overlap-save): the FFT of the
    previous and the current block (2·S samples); a channel takes the bins of ±rate/2 around it, tapered from
    WIDE_PASS_HZ, delayed by a linear phase (so the filter is causal) and an inverse FFT of 2·S/D points gives
    its samples at fs/D, of which the second half belongs to the current block. Channel centres are on even bins,
    so the frames join without a phase step. The same FFT gives the detection spectrum."""

    def __init__(self, fs, block):
        self.fs, self.S = fs, block
        self.N = 2 * block
        d = 1
        while fs / (d * 2) >= WIDE_RATE:     # D: a power of two, rate fs/D ≥ WIDE_RATE (2.048 MS/s: 64 → 32 kHz)
            d *= 2
        self.D = d
        self.M = self.N // d
        self.rate = fs / d
        f = (np.arange(self.M) - self.M // 2) * fs / self.N          # offsets of the channel bins, Hz
        a = np.clip((np.abs(f) - WIDE_PASS_HZ) / (self.rate / 2 - WIDE_PASS_HZ), 0, 1)
        tau = WIDE_DELAY                                              # input samples (multiple of D)
        self.h = (0.5 * (1 + np.cos(np.pi * a)) * np.exp(-2j * np.pi * (np.arange(self.M) - self.M // 2) * tau / self.N)
                  ).astype(np.complex64)
        self.prev = np.zeros(block, np.complex64)
        self.X = None

    def frame(self, cur):
        """FFT of the previous + this block (len(cur) == S)."""
        self.X = np.fft.fft(np.concatenate((self.prev, cur)))
        self.prev = cur
        return self.X

    def bin_of(self, offset_hz):
        return 2 * int(round(offset_hz / self.fs * self.N / 2))      # an even bin

    def channel(self, k):
        """Samples (rate fs/D) of the current block for the channel centred on bin k."""
        idx = (k + np.arange(-(self.M // 2), self.M - self.M // 2)) % self.N
        y = np.fft.ifft(np.fft.ifftshift(self.X[idx] * self.h)) * (self.M / self.N)
        return y[self.M // 2:].astype(np.complex64)

    def power(self, bins):
        """Detection spectrum: power in `bins` equal bins over the band, DC in the middle."""
        p = np.fft.fftshift(np.abs(self.X) ** 2)
        return p.reshape(bins, -1).sum(axis=1)


class _WideChan:
    """MULTI: one sonde signal found in the band: its bin and its own demodulator."""

    def __init__(self, hz, chz, center_hz, now):
        self.k = chz.bin_of(hz - center_hz)
        self.hz = center_hz + self.k * chz.fs / chz.N
        self.dm = _Demod(chz.rate)
        self.seen = now                      # signal seen in the spectrum
        self.frame_t = None                  # last decoded frame
        self.level = None                    # dB above the noise
        self.type = self.serial = None
        self.frames = 0


def to_iq(raw):
    """Dongle samples as complex64 ±1: uint8 I/Q of an RTL, or already complex (LimeSDR, Airspy)."""
    if raw.dtype == np.complex64:
        return raw
    iq = raw.astype(np.float32).view(np.complex64)
    iq -= np.complex64(127.5 + 127.5j)
    iq *= np.float32(1 / 127.5)
    return iq


def find_signals(maxhold_db, freqs, lo, hi):
    """Sonde-like signals in a max-hold spectrum (dB per bin) within lo…hi Hz: [(centre Hz, dB above the noise)].
    Noise = the median; a signal stands WIDE_ON_DB above it and is at least WIDE_WIDTH_HZ wide at 5 dB."""
    sel = (freqs >= lo) & (freqs <= hi)
    if sel.sum() < 8:
        return []
    bin_hz = abs(freqs[1] - freqs[0])
    sm = np.convolve(maxhold_db, np.ones(3) / 3, "same")
    noise = float(np.median(sm[sel]))
    above = sel & (sm > noise + 5.0)
    runs, i, n = [], 0, len(sm)
    while i < n:                             # runs of bins above the noise
        if not above[i]:
            i += 1
            continue
        j = i
        while j < n and above[j]:
            j += 1
        if runs and (i - runs[-1][1]) * bin_hz <= WIDE_GAP_HZ:
            runs[-1][1] = j                  # a strong FSK has nulls between its lobes: one signal
        else:
            runs.append([i, j])
        i = j
    out = []
    for i, j in runs:
        m = above[i:j]
        peak = float(sm[i:j].max())
        if m.sum() * bin_hz >= WIDE_WIDTH_HZ and peak >= noise + WIDE_ON_DB:
            w = np.where(m, 10 ** ((sm[i:j] - noise) / 10) - 1, 0.0)
            out.append((float((freqs[i:j] * w).sum() / w.sum()), round(peak - noise, 1)))
    return out


# ---------- decoder ----------

class SondeDecoder:
    """Radiosonde decoder of one VFO. Frames go to on_event("sonde", ...), the state to on_event("sondestate", ...)."""

    def __init__(self, on_event, station=None, max_frames=MAX_FRAMES, log_dir=None, tag=""):
        self.on_event = on_event
        self.log_dir = log_dir       # radiosonde log: <log_dir>/<YYYY-MM-DD>_<serial>.jsonl, every frame (JSON lines)
        self.tag = tag               # VFO name: the logs are shared by all VFOs, each reads back only its own lines
        self.log_files = {}          # serial -> file name
        self.station = station or (lambda: None)
        self.enabled = False
        self.lock = threading.Lock()
        self.frames = collections.deque(maxlen=max_frames)
        self.sondes = {}
        self.cal = {}                # serial -> [calibration bytes, pieces known]
        self.next_id = 1
        self.ok = 0
        self.bad = 0
        self.bad_frames = collections.deque(maxlen=20)   # M10 / M20 frames with a wrong checksum (hex), to look at
        self.fixed = 0
        self.base_headers = 0
        self.last_rx = None
        self.dial = 0.0
        self.offset = None
        self._fs = None
        self.main = None             # _Demod of the VFO channel
        self.tune_hz = None
        self.dfm = {}                # DFM state of the channel being processed (self.main or a MULTI channel)
        self.dfm_id = {}
        self.since_state = 0.0
        # MULTI: the other sondes of the visible band, from the dongle samples, in a worker thread
        self.multi = True
        self.wide = []               # _WideChan
        self.wide_q = collections.deque(maxlen=WIDE_QUEUE)
        self.wide_ev = threading.Event()
        self.wide_acc = None         # max-hold of the detection spectrum (dB)
        self.wide_key = None         # (rate, centre) the spectrum belongs to
        self.wide_t = 0.0            # seconds collected
        self.wide_view = None        # [lo, hi] Hz searched (visible part of 400-406 MHz)
        self.wide_thread = None
        self.wide_chz = None         # _Channelizer of the current band
        self.wide_pend = np.zeros(0, np.complex64)   # samples waiting for a whole channelizer block
        self.rec = None              # IQ recording of the VFO channel (rec_iq)
        self.rec_last = None         # file name of the last finished one
        if log_dir:
            self.restore()

    # ---------- control ----------

    def set_enabled(self, on):
        with self.lock:
            self.enabled = bool(on)
            self._fs = None
        self._emit_state()

    def set_types(self, names):
        """SONDE > TYPES: the decoders listening for a new sonde (sonde_ext.ENABLED, for every channel)."""
        sonde_ext.set_enabled(names)
        self._emit_state()

    def clear(self):
        with self.lock:
            self.frames.clear()
            self.sondes.clear()
            self.cal.clear()
            self.ok = self.bad = self.fixed = 0
            self.bad_frames.clear()
            self.base_headers = self._headers()

    def command(self, body):
        if body.get("action") == "clear":
            self.clear()
        elif body.get("action") == "forget" and body.get("serial"):
            with self.lock:
                self.sondes.pop(str(body["serial"]), None)
                self.cal.pop(str(body["serial"]), None)
        elif body.get("action") == "rec_iq":
            self.rec_iq(float(body.get("secs", 60)))
        elif body.get("action") == "rec_iq_stop":
            self.rec_iq(0)

    def rec_iq(self, secs):
        """Records the baseband of the VFO channel (what the decoders get) for `secs` (≤ REC_IQ_MAX) into
        data\\sonde_iq\\<date>_<time>_<MHz>_<rate>.cf32 (complex64), to replay it later (tests/sonde_replay.py);
        0 stops."""
        with self.lock:
            if self.rec is not None:
                self.rec["f"].close()
                self.rec = None
            if secs > 0:
                self.rec = {"secs": min(float(secs), REC_IQ_MAX), "done": 0.0, "f": None, "file": None}

    def _rec_feed(self, base, fs, dial_hz):
        r = self.rec
        if r["f"] is None:
            os.makedirs(REC_IQ_DIR, exist_ok=True)
            r["file"] = time.strftime("%Y%m%d_%H%M%S") + f"_{dial_hz / 1e6:.4f}MHz_{int(round(fs))}Hz.cf32"
            r["f"] = open(os.path.join(REC_IQ_DIR, r["file"]), "wb")
        r["f"].write(np.asarray(base, np.complex64).tobytes())
        r["done"] += len(base) / fs
        if r["done"] >= r["secs"]:
            r["f"].close()
            self.rec_last = r["file"]
            self.rec = None

    def _headers(self):
        return (self.main.headers if self.main else 0) + sum(c.dm.headers for c in self.wide)

    @property
    def paths(self):
        return self.main.paths if self.main else []

    def info(self, frames=True):
        with self.lock:
            now = time.time()
            i = {"enabled": self.enabled, "ok": self.ok, "bad": self.bad, "fixed": self.fixed,
                 "headers": self._headers() - self.base_headers, "last_rx": self.last_rx,
                 "offset_hz": None if self.offset is None else round(self.offset), "multi": self.multi,
                 "view": self.wide_view,
                 "rec_iq": None if self.rec is None else {"file": self.rec["file"], "secs": round(self.rec["done"], 1),
                                                          "of": self.rec["secs"]},
                 "rec_iq_last": self.rec_last,
                 "decoders": sonde_ext.available(),
                 "types": sonde_ext.enabled(),
                 "channels": [{"hz": round(c.hz), "level_db": c.level, "type": c.type, "serial": c.serial,
                               "frames": c.frames, "age_s": None if c.frame_t is None else round(now - c.frame_t, 1),
                               "offset_hz": None if c.dm.offset is None else round(c.dm.offset)}
                              for c in sorted(self.wide, key=lambda c: c.hz)]}
            if frames:
                i["frames"] = list(self.frames)
                i["bad_frames"] = list(self.bad_frames)
                i["sondes"] = sorted((dict(s) for s in self.sondes.values()), key=lambda s: -s["last"])
            return i

    # ---------- signal ----------

    def _setup(self, fs):
        old = self._headers()
        self._fs = fs
        self.main = _Demod(fs)
        self.base_headers -= old

    def feed(self, base, fs, dial_hz):
        if not self.enabled:
            return
        new = []
        with self.lock:
            if fs != self._fs:
                self._setup(fs)
            self.tune_hz = dial_hz
            if self.rec is not None:
                self._rec_feed(base, fs, dial_hz)
            new = self._run(self.main, base, dial_hz, time.time())
            self.offset = self.main.offset
            self.since_state += len(base) / fs
        for m in new:
            self.on_event("sonde", m)
        if new or self.since_state >= 1.0:
            self.since_state = 0.0
            self._emit_state()

    def _run(self, dm, base, dial_hz, now):
        """Baseband of one channel through its demodulator; the decoded frames (under self.lock)."""
        self.dial, self.dfm, self.dfm_id = dial_hz, dm.dfm, dm.dfm_id
        out = []
        for _name, j in dm.process(base):
            rec = self._ext(j, now)
            if rec is not None:
                out.append(rec)
        dm.update_offset()
        return out

    def _ext(self, j, now):
        """One JSON frame of an rs1729 decoder -> published frame (None for a frame without anything usable)."""
        d = sonde_ext.to_frame(j)
        if d is None:
            self.bad += 1
            return None
        if d["type"] == "DFM":
            ph = f"DFM-{self.dial / 1e6:.3f}"
            if d["serial"] is None:
                d["serial"] = ph                  # until the serial comes: named by the frequency
            else:
                s = self.sondes.pop(ph, None)     # the sonde heard before its serial came: renamed
                if s is not None and d["serial"] not in self.sondes:
                    s["serial"] = d["serial"]
                    self.sondes[d["serial"]] = s
        if d["serial"] is None:
            d.pop("serial")
        if d.get("lat") is None:
            return None                           # no position (yet): nothing for the table, the map or the log
        return self._publish(d, False, now)

    # ---------- MULTI: the other sondes of the visible band ----------

    def set_multi(self, on):
        with self.lock:
            self.multi = bool(on)
            if not self.multi:
                self.wide, self.wide_acc, self.wide_view = [], None, None
        self._emit_state()

    def feed_wide(self, raw, fs, center_hz, view):
        """Dongle samples (receiver thread), view = (lo, hi) Hz of the visible spectrum. Queued for the worker when
        it reaches into 400–406 MHz; only copied here, the work is done in the worker thread."""
        if not (self.enabled and self.multi):
            return
        lo = max(view[0], center_hz - 0.48 * fs, BAND_HZ[0])
        hi = min(view[1], center_hz + 0.48 * fs, BAND_HZ[1])
        if hi - lo < WIDE_WIDTH_HZ:
            if self.wide or self.wide_view:
                with self.lock:
                    self.wide, self.wide_acc, self.wide_view = [], None, None
            return
        self.wide_q.append((np.array(raw), fs, center_hz, (lo, hi)))
        if self.wide_thread is None or not self.wide_thread.is_alive():
            self.wide_thread = threading.Thread(target=self._wide_loop, name="sonde-multi", daemon=True)
            self.wide_thread.start()
        self.wide_ev.set()

    def _wide_loop(self):
        while True:
            if not self.wide_ev.wait(30):
                if not (self.enabled and self.multi):
                    return                   # idle: the thread ends, the next block starts it again
                continue
            self.wide_ev.clear()
            while True:
                try:
                    raw, fs, center_hz, view = self.wide_q.popleft()
                except IndexError:
                    break
                try:
                    self._wide_block(to_iq(raw), fs, center_hz, view)
                except Exception as e:      # a bad block must not end the thread
                    print(f"sonde MULTI: {e!r}", flush=True)

    def _wide_block(self, iq, fs, center_hz, view, now=None):
        now = time.time() if now is None else now
        key = (fs, center_hz)
        if self.wide_key != key:             # another band or rate: the channels of the old one are gone
            self.wide_key, self.wide_acc, self.wide_t = key, None, 0.0
            self.wide_chz, self.wide_pend = None, np.zeros(0, np.complex64)
            with self.lock:
                self.wide = []
        if self.wide_chz is None:
            self.wide_chz = _Channelizer(fs, len(iq) if len(iq) % (2 * WIDE_SEG) == 0 else WIDE_BLOCK)
        chz = self.wide_chz
        pend = np.concatenate((self.wide_pend, iq)) if len(self.wide_pend) else iq
        new = []
        while len(pend) >= chz.S:
            cur, pend = pend[:chz.S], pend[chz.S:]
            chz.frame(np.asarray(cur, np.complex64))
            # detection: max-hold of the block spectra, looked at once a second (so the M20 bursts count too)
            db = 10 * np.log10(chz.power(WIDE_SEG) + 1e-20)
            self.wide_acc = db if self.wide_acc is None else np.maximum(self.wide_acc, db)
            self.wide_t += chz.S / fs
            if self.wide_t >= WIDE_EVAL_S:
                self._wide_detect(fs, center_hz, view, now)
            for c in list(self.wide):
                base = chz.channel(c.k)              # also while the VFO is on it, so its demodulator keeps up
                with self.lock:
                    if self.tune_hz is not None and abs(c.hz - self.tune_hz) <= WIDE_OWN_HZ:
                        continue                     # the VFO is on it: its own channel decodes it (no double frames)
                    for m in self._run(c.dm, base, float(c.hz), now):
                        new.append(m)
                        c.frame_t, c.type, c.serial = now, m.get("type"), m.get("serial")
                        c.frames += 1
        self.wide_pend = np.array(pend, np.complex64) if len(pend) else np.zeros(0, np.complex64)
        for m in new:
            self.on_event("sonde", m)

    def _wide_detect(self, fs, center_hz, view, now):
        """Signals of the last second: new channels for new ones, the channels without a signal and a frame dropped."""
        freqs = center_hz + (np.arange(WIDE_SEG) - WIDE_SEG / 2 + 0.5) * fs / WIDE_SEG
        found = find_signals(self.wide_acc, freqs, *view)
        self.wide_acc, self.wide_t = None, 0.0
        with self.lock:
            self.wide_view = [round(view[0]), round(view[1])]
            for hz, lvl in found:
                if abs(hz - center_hz) < 5000:
                    continue                     # what is left of the DC peak
                c = min(self.wide, key=lambda c: abs(c.hz - hz), default=None)
                if c is not None and abs(c.hz - hz) <= WIDE_MATCH_HZ:
                    c.seen, c.level = now, lvl
                elif len(self.wide) < WIDE_MAX:
                    c = _WideChan(hz, self.wide_chz, center_hz, now)
                    c.level = lvl
                    self.wide.append(c)
            self.wide = [c for c in self.wide if now - max(c.seen, c.frame_t or 0) < WIDE_KEEP_S
                         and view[0] <= c.hz <= view[1]]

    def _frame(self, frame, inv, now):
        e = rs41_ecc(frame)
        d = rs41_parse(frame)
        if d is None:
            self.bad += 1
            return None
        if e > 0:
            self.fixed += e
        d["ecc"] = e
        self._ptu(d)
        return self._publish(d, inv, now)

    def _ptu(self, d):
        """Calibration piece of the frame into the store of its sonde, temperature and humidity when known."""
        cal, meas = d.pop("_cal", None), d.pop("_meas", None)
        serial = d.get("serial")
        if not serial:
            return
        c = self.cal.get(serial)
        if c is None:
            if len(self.cal) >= MAX_SONDES:
                del self.cal[next(iter(self.cal))]
            c = self.cal[serial] = [bytearray(CAL_FRAGS * CAL_LEN), set()]
        if cal is not None:
            i, data = cal
            c[0][i * CAL_LEN:(i + 1) * CAL_LEN] = data
            c[1].add(i)
        d["cal_n"] = len(c[1])
        st = rs41_subtype(c[0], c[1])
        if st:
            d["subtype"] = st
        if meas is not None and any(meas):
            d.update(rs41_ptu(c[0], c[1], meas))

    def _dfm(self, fr, inv, now):
        """DFM: the fields come in data blocks 0-15 spread over the frames of a second; a position is published
        when latitude, longitude and altitude of the same second are there (block 4 after 2 and 3). The configuration
        blocks give the serial, type and temperature (dfm_conf); until the serial is known the sonde is called
        DFM-<frequency>, then renamed. Time: date, hour and minute of block 8 (the previous second), the second of
        block 1."""
        cs = self.dfm_id
        if fr["conf"] is not None:
            dfm_conf(cs, fr["conf"])
        if not fr["dat"]:
            if fr["bad"]:
                self.bad += 1
            return None
        self.fixed += fr["fixed"]
        st = self.dfm
        if now - st.get("t", 0) > 3 or st.get("inv") != inv:
            st.clear()
        st["t"], st["inv"] = now, inv
        out = None
        for fid, v in fr["dat"]:
            hi32, lo16 = v >> 16, v & 0xFFFF
            if fid == 0:
                st["frame"] = (v >> 16) & 0xFF
            elif fid == 1:
                st["sec"] = lo16 / 1000.0
            elif fid == 2:
                st["lat"], st["vh"] = _s32(hi32) / 1e7, lo16 / 100.0
            elif fid == 3:
                st["lon"], st["dir"] = _s32(hi32) / 1e7, lo16 / 100.0
            elif fid == 8:
                y, mo, dd = v >> 36 & 0xFFF, v >> 32 & 0xF, v >> 27 & 0x1F
                hh, mi, nsv = v >> 22 & 0x1F, v >> 16 & 0x3F, v >> 8 & 0xFF
                try:
                    if not 2020 <= y <= 2100:
                        raise ValueError(y)          # not a date: neither the time nor the satellites are believed
                    cs["minute_t"] = datetime.datetime(y, mo, dd, hh, mi, tzinfo=datetime.timezone.utc).timestamp()
                    cs["sec_at8"] = st.get("sec")
                    cs["sats"] = nsv
                except ValueError:
                    cs.pop("minute_t", None)
                    cs.pop("sats", None)
            elif fid == 4 and "lat" in st and "lon" in st:
                alt, vv = _s32(hi32) / 100.0, _s16(lo16) / 100.0
                if abs(st["lat"]) <= 90 and abs(st["lon"]) <= 180 and -500 < alt < 50000 and st["dir"] <= 360:
                    out = self._publish(self._dfm_rec(st, cs, alt, vv, fr, now), inv, now)
                st.pop("lat", None)
                st.pop("lon", None)
        return out

    def _dfm_rec(self, st, cs, alt, vv, fr, now):
        ph = f"DFM-{self.dial / 1e6:.3f}"
        d = {"type": "DFM", "serial": ph, "lat": round(st["lat"], 6), "lon": round(st["lon"], 6),
             "alt": round(alt, 1), "vh": st["vh"], "dir": st["dir"], "vv": vv,
             "blocks_ok": len(fr["dat"]), "blocks_bad": fr["bad"], "ecc": fr["fixed"]}
        if "frame" in st:
            d["frame"] = st["frame"]
        info = dfm_info(cs)
        for k in ("temp", "batt"):
            if info[k] is not None:
                d[k] = info[k]
        if info["serial"]:
            d["serial"] = f"DFM-{info['serial']}"
            if info["subtype"]:
                d["subtype"] = info["subtype"]
            s = self.sondes.pop(ph, None)           # the sonde heard before its serial came: renamed
            if s is not None and d["serial"] not in self.sondes:
                s["serial"] = d["serial"]
                self.sondes[d["serial"]] = s
        if cs.get("sats") is not None:
            d["sats"] = cs["sats"]
        if cs.get("minute_t") is not None and st.get("sec") is not None:
            t = cs["minute_t"] + st["sec"]
            if cs.get("sec_at8") is not None and st["sec"] + 1 < cs["sec_at8"]:
                t += 60                              # the minute changed since block 8
            if abs(t - now) < 86400:
                d["gps_time"] = round(t, 3)
        return d

    def _m20(self, frame, inv, now):
        """Meteomodem M10 / M20: a frame with a good checksum."""
        d = mm_parse(frame)
        if d is None:
            self.bad += 1
            self.bad_frames.append([round(now, 1), bytes(frame).hex()])
            return None
        return self._publish(d, inv, now)

    def _publish(self, d, inv, now):
        self.ok += 1
        self.last_rx = now
        d.update(id=self.next_id, time=now, freq_hz=self.dial, inverted=inv)
        self.next_id += 1
        if d.get("serial"):
            pos_filter(self.sondes.get(d["serial"]), d, now)   # a bad fix goes neither to the frames nor to the log
        qth = self.station()
        if qth and d.get("lat") is not None:
            dist, az, el = look(qth, d["lat"], d["lon"], d["alt"])
            d.update(dist=round(dist, 2), az=round(az, 1), el=round(el, 2))
        if len(d.get("xdata", "")) > 200:
            d.pop("xdata")
        self.frames.append(d)
        serial = d.get("serial")
        if serial:
            self._sonde(serial, d, now)
            self._log(serial, d)
        return d

    # ---------- radiosonde log ----------
    # <log_dir>/YYYY/MM/DD/<YYYY-MM-DD>_<serial>.jsonl (the day of the first frame, UTC; datafiles.py)

    def _log_path(self, name):
        return os.path.join(datafiles.date_dir("", name[:10], self.log_dir), name)

    def _log_files(self):
        """All flight logs (paths) below log_dir."""
        return datafiles.walk_files(self.log_dir, LOG_NAME) if self.log_dir else []

    def _log(self, serial, d):
        """Every frame of a sonde into its log, whatever the LOG key (to read the flight back after a restart)."""
        if not self.log_dir:
            return
        try:
            name = self.log_files.get(serial)
            if name is None:
                safe = re.sub(r"[^\w.-]", "_", serial)
                old = [f for f in self._log_files() if f.endswith(f"_{safe}.jsonl")
                       and time.time() - os.path.getmtime(f) < LOG_SAME_SEC]
                name = os.path.basename(max(old, key=os.path.getmtime)) if old else \
                    f"{time.strftime('%Y-%m-%d', time.gmtime(d['time']))}_{safe}.jsonl"
                self.log_files[serial] = name
            rec = {k: d[k] for k in LOG_KEYS if d.get(k) is not None}
            rec["time"] = round(rec["time"], 2)
            rec["vfo"] = self.tag
            path = self._log_path(name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        except OSError:
            pass                     # a full disk / locked file must not stop the decoder

    def restore(self):
        """At the start: the sondes of this VFO from the logs of the last RESTORE_SEC, with their flight paths."""
        try:
            files = [f for f in self._log_files() if time.time() - os.path.getmtime(f) < RESTORE_SEC]
        except OSError:
            return
        for path in sorted(files, key=os.path.getmtime)[-MAX_SONDES:]:
            for rec in read_log(path):
                if rec.get("vfo", "") == self.tag and rec.get("serial") and rec.get("type"):
                    self._sonde(rec["serial"], rec, rec["time"])
                    self.log_files.setdefault(rec["serial"], os.path.basename(path))
        for s in self.sondes.values():
            s["from_log"] = True

    def logs(self):
        """Logged flights, newest first: file, serial, type, first / last time, frames, highest altitude."""
        out = []
        try:
            files = sorted(self._log_files(), key=os.path.getmtime, reverse=True)
        except OSError:
            return out
        for path in files[:LOG_LIST]:
            name = os.path.basename(path)
            if not LOG_NAME.match(name):
                continue
            recs = read_log(path, head_tail=True)
            if not recs:
                continue
            a, b = recs[0], recs[-1]
            out.append({"file": name, "serial": a.get("serial"), "type": a.get("type"), "first": a.get("time"),
                        "last": b.get("time"), "alt": b.get("alt"), "size": os.path.getsize(path)})
        return out

    def history(self, days):
        """Flights of all VFOs logged in the last days (1-7), oldest first, for the map: serial, type, file, first /
        last time, highest altitude, burst, last point and the flight path thinned to at most HISTORY_PTS points."""
        out = []
        if not self.log_dir:
            return out
        since = time.time() - max(1, min(7, int(days))) * 86400
        try:
            files = [f for f in self._log_files() if os.path.getmtime(f) >= since]
        except OSError:
            return out
        for path in sorted(files, key=os.path.getmtime):
            tmp = {}
            for rec in read_log(path):
                if rec.get("serial") and rec.get("type") and rec["time"] >= since:
                    _sonde_add(tmp, rec["serial"], rec, rec["time"])
            for sd in tmp.values():
                if sd.get("lat") is None:
                    continue
                pts = sd["pts"]
                step = max(1, -(-len(pts) // HISTORY_PTS))
                thin = pts[::step]
                if pts and thin[-1] is not pts[-1]:
                    thin.append(pts[-1])
                out.append({"serial": sd["serial"], "type": sd["type"], "file": os.path.basename(path),
                            "first": sd["first"], "last": sd["last"], "max_alt": sd["max_alt"], "burst": sd["burst"],
                            "lat": sd["lat"], "lon": sd["lon"], "alt": sd["alt"],
                            "freq_hz": sd.get("freq_hz"), "pts": [[q[0], q[1], q[2]] for q in thin]})
        return out

    def log_sonde(self, name):
        """One logged flight as a sonde (as in info()["sondes"]), or None."""
        if not self.log_dir or not LOG_NAME.match(name or ""):
            return None
        path = self._log_path(name)
        if not os.path.isfile(path):
            return None
        tmp = {}
        for rec in read_log(path):
            if rec.get("serial") and rec.get("type"):
                _sonde_add(tmp, rec["serial"], rec, rec["time"])
        if not tmp:
            return None
        s = max(tmp.values(), key=lambda x: x["n"])
        s["from_log"] = name
        return s

    def _sonde(self, serial, d, now):
        _sonde_add(self.sondes, serial, d, now)

    def _emit_state(self):
        self.on_event("sondestate", self.info(frames=False))


def read_log(path, head_tail=False):
    """Records of a radiosonde log (broken lines skipped); head_tail: only the first and the last one."""
    out = []
    try:
        with open(path, "rb") as f:
            if head_tail:
                first = f.readline()
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - 4096))
                lines = [first] + f.read().splitlines()[-1:]
            else:
                lines = f.read().splitlines()
    except OSError:
        return out
    for ln in lines:
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("time"), (int, float)):
            out.append(rec)
    return out


def pos_filter(s, d, now):
    """Drops the position of frame d (in place) when it cannot be believed: no GPS fix (a sonde that lost its
    satellites after the burst goes on with an extrapolated, frozen or random position), under the ground or too high,
    falling faster than a sonde can, or a jump from the last good position s (the sonde so far, or None).
    The reason goes to d["pos_bad"]. Returns True when the position was dropped."""
    if d.get("lat") is None:
        return False
    alt, vv, sats = d.get("alt"), d.get("vv"), d.get("sats")
    why = None
    if sats is not None and sats < POS_MIN_SATS:
        why = f"no GPS fix ({sats} satellites)"
    elif alt is None or not POS_ALT[0] <= alt <= POS_ALT[1]:
        why = f"altitude {alt} m"
    elif vv is not None and vv < -(POS_FALL[0] + max(0.0, alt) / POS_FALL[1]):
        why = f"falling {-vv:.0f} m/s"
    elif s and s.get("lat") is not None and s.get("pos_time") is not None and s.get("jumps", 0) < POS_JUMP_RESET:
        dt = max(1.0, now - s["pos_time"])
        km = math.hypot((d["lat"] - s["lat"]) * 111.2,
                        (d["lon"] - s["lon"]) * 111.2 * math.cos(math.radians(d["lat"])))
        if km > POS_JUMP[0] + POS_JUMP[1] * dt:
            s["jumps"] = s.get("jumps", 0) + 1
            why = f"jump of {km:.0f} km"
    if why is None:
        if s:
            s["jumps"] = 0
        return False
    for k in POS_KEYS + ("dist", "az", "el"):
        d.pop(k, None)
    d["pos_bad"] = why
    return True


def _sonde_add(sondes, serial, d, now):
    """Frame d of a sonde into the dict of sondes: the newest values, highest point, burst, flight path."""
    s = sondes.get(serial)
    pos_filter(s, d, now)                        # also the logs written before the filter
    if s is None:
        if len(sondes) >= MAX_SONDES:
            del sondes[min(sondes, key=lambda k: sondes[k]["last"])]
        s = {"serial": serial, "type": d["type"], "first": now, "n": 0, "pts": [], "max_alt": None,
             "burst": False}
        sondes[serial] = s
    s.pop("from_log", None)
    s["n"] += 1
    s["last"] = now
    for k in ("frame", "batt", "sats", "freq_hz", "encrypted", "gps_time", "dist", "az", "el", "temp", "rh",
              "temp_h", "pres", "cal_n", "subtype"):
        if d.get(k) is not None:
            s[k] = d[k]
    if d.get("lat") is not None:
        for k in ("lat", "lon", "alt", "vh", "dir"):
            s[k] = d[k]
        if d.get("vv") is not None:              # M20: no climb in its first frame (it comes from two altitudes)
            s["vv"] = d["vv"]
        s["pos_time"] = now
        if s["max_alt"] is None or d["alt"] > s["max_alt"]:
            s["max_alt"] = d["alt"]
        # burst: falling fast well below the highest point
        if not s["burst"] and (d.get("vv") or 0) < -8 and s["max_alt"] - d["alt"] > 200 and s["max_alt"] > 5000:
            s["burst"] = True
            s["burst_alt"] = s["max_alt"]
        pts = s["pts"]
        if not pts or now - pts[-1][3] >= TRACK_SEC:
            pts.append([d["lat"], d["lon"], d["alt"], now, d.get("temp"), d.get("rh")])   # + profile
            if len(pts) > MAX_TRACK:
                del pts[1:len(pts) - MAX_TRACK + 1]

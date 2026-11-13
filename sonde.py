"""Radiosonde decoder (Vaisala RS41) of one VFO: position, altitude, speed and climb of weather balloons, 400–406 MHz.

From the complex baseband of the VFO, independent of the listening mode and filter:
channel filter (±10 kHz) -> FM discriminator -> low-pass -> slicer with an adaptive threshold (midpoint of the
signal envelope, so a sonde a few kHz off the dial still works) -> bit clock (PLL of packet.py) -> both polarities
-> framer.

RS41: GFSK 4800 Bd, one frame a second. The frame starts with an 8-byte header, bytes are sent LSB first and are
whitened with a 64-byte mask. Bytes 8–55 are the Reed–Solomon parity of two interleaved RS(255,231) codewords over
the frame from byte 56 (12 wrong bytes of each can be corrected). From byte 57 on, the frame is a chain of blocks
(id, length, data, CRC-16): 0x79 status (frame number, serial number, battery), 0x7C GPS time, 0x7B GPS position
and velocity (ECEF), 0x7A raw measurements, 0x7D raw GPS, 0x7E extra sensors (ozone…), 0x80 encrypted (RS41-SGM).
Temperature and humidity need the calibration that is sent in 51 pieces over the status blocks: not decoded.
"""
import collections
import datetime
import math
import threading
import time

import numpy as np

from packet import _Clock, _Disc, _Fir
from sdr import lowpass

CHAN_HZ = 10000.0            # channel filter: the sonde can be a few kHz off, deviation ±2.4 kHz
ENV_TAU = 0.15               # s: smoothing of the envelope (slicer threshold)
MAX_FRAMES = 300
MAX_SONDES = 50
MAX_TRACK = 3000             # track points kept for each sonde
TRACK_SEC = 2.0              # a track point at most this often
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
            if len(data) >= 40:
                d["cal_frag"] = data[23]
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
    blocks.append((BLK_STATUS, bytes(st)))
    meas = bytes(42)
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

DFM_BAUD = 2500              # bits/s, Manchester: 5000 symbols/s
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


def _s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def _s16(v):
    return v - (1 << 16) if v & 0x8000 else v


# ---------- decoder ----------

class SondeDecoder:
    """Radiosonde decoder of one VFO. Frames go to on_event("sonde", ...), the state to on_event("sondestate", ...)."""

    def __init__(self, on_event, station=None, max_frames=MAX_FRAMES):
        self.on_event = on_event
        self.station = station or (lambda: None)
        self.enabled = False
        self.lock = threading.Lock()
        self.frames = collections.deque(maxlen=max_frames)
        self.sondes = {}
        self.next_id = 1
        self.ok = 0
        self.bad = 0
        self.fixed = 0
        self.base_headers = 0
        self.last_rx = None
        self.dial = 0.0
        self.offset = None
        self._fs = None
        self.chan = None
        self.disc = None
        self.paths = []
        self.dfm = {}
        self.since_state = 0.0

    # ---------- control ----------

    def set_enabled(self, on):
        with self.lock:
            self.enabled = bool(on)
            self._fs = None
        self._emit_state()

    def clear(self):
        with self.lock:
            self.frames.clear()
            self.sondes.clear()
            self.ok = self.bad = self.fixed = 0
            self.base_headers = self._headers()

    def command(self, body):
        if body.get("action") == "clear":
            self.clear()
        elif body.get("action") == "forget" and body.get("serial"):
            with self.lock:
                self.sondes.pop(str(body["serial"]), None)

    def _headers(self):
        return sum(p.headers for p in self.paths)

    def info(self, frames=True):
        with self.lock:
            i = {"enabled": self.enabled, "ok": self.ok, "bad": self.bad, "fixed": self.fixed,
                 "headers": self._headers() - self.base_headers, "last_rx": self.last_rx,
                 "offset_hz": None if self.offset is None else round(self.offset)}
            if frames:
                i["frames"] = list(self.frames)
                i["sondes"] = sorted((dict(s) for s in self.sondes.values()), key=lambda s: -s["last"])
            return i

    # ---------- signal ----------

    def _setup(self, fs):
        old = self._headers()
        self._fs = fs
        self.chan = _Fir(lowpass(min(CHAN_HZ, 0.45 * fs), fs, 63), 1, np.complex64)
        self.disc = _Disc(fs)
        self.paths = [_Path(fs, RS41_BAUD, Rs41Framer, "rs41"), _Path(fs, 2 * DFM_BAUD, DfmFramer, "dfm")]
        self.dfm = {}
        self.base_headers -= old

    def feed(self, base, fs, dial_hz):
        if not self.enabled:
            return
        new = []
        with self.lock:
            if fs != self._fs:
                self._setup(fs)
            self.dial = dial_hz
            f = self.disc.process(self.chan.process(np.asarray(base, np.complex64)))
            now = time.time()
            for p in self.paths:
                for kind, frame, inv in p.process(f):
                    rec = self._frame(frame, inv, now) if kind == "rs41" else self._dfm(frame, inv, now)
                    if rec is not None:
                        new.append(rec)
            if self.paths and self.paths[0].hi is not None:
                self.offset = self.paths[0].offset
            self.since_state += len(base) / fs
        for m in new:
            self.on_event("sonde", m)
        if new or self.since_state >= 1.0:
            self.since_state = 0.0
            self._emit_state()

    def _frame(self, frame, inv, now):
        e = rs41_ecc(frame)
        d = rs41_parse(frame)
        if d is None:
            self.bad += 1
            return None
        if e > 0:
            self.fixed += e
        d["ecc"] = e
        return self._publish(d, inv, now)

    def _dfm(self, fr, inv, now):
        """DFM: the fields come in data blocks 0-15 spread over the frames of a second; a position is published
        when latitude, longitude and altitude of the same second are there (block 4 after 2 and 3)."""
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
            elif fid == 2:
                st["lat"], st["vh"] = _s32(hi32) / 1e7, lo16 / 100.0
            elif fid == 3:
                st["lon"], st["dir"] = _s32(hi32) / 1e7, lo16 / 100.0
            elif fid == 4 and "lat" in st and "lon" in st:
                alt, vv = _s32(hi32) / 100.0, _s16(lo16) / 100.0
                if abs(st["lat"]) <= 90 and abs(st["lon"]) <= 180 and -500 < alt < 50000 and st["dir"] <= 360:
                    d = {"type": "DFM", "serial": f"DFM-{self.dial / 1e6:.3f}", "lat": round(st["lat"], 6),
                         "lon": round(st["lon"], 6), "alt": round(alt, 1), "vh": st["vh"], "dir": st["dir"], "vv": vv,
                         "blocks_ok": len(fr["dat"]), "blocks_bad": fr["bad"], "ecc": fr["fixed"]}
                    if "frame" in st:
                        d["frame"] = st["frame"]
                    out = self._publish(d, inv, now)
                st.pop("lat", None)
                st.pop("lon", None)
        return out

    def _publish(self, d, inv, now):
        self.ok += 1
        self.last_rx = now
        d.update(id=self.next_id, time=now, freq_hz=self.dial, inverted=inv)
        self.next_id += 1
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
        return d

    def _sonde(self, serial, d, now):
        s = self.sondes.get(serial)
        if s is None:
            if len(self.sondes) >= MAX_SONDES:
                del self.sondes[min(self.sondes, key=lambda k: self.sondes[k]["last"])]
            s = {"serial": serial, "type": d["type"], "first": now, "n": 0, "pts": [], "max_alt": None,
                 "burst": False}
            self.sondes[serial] = s
        s["n"] += 1
        s["last"] = now
        for k in ("frame", "batt", "sats", "freq_hz", "encrypted", "gps_time", "dist", "az", "el"):
            if d.get(k) is not None:
                s[k] = d[k]
        if d.get("lat") is not None:
            for k in ("lat", "lon", "alt", "vh", "dir", "vv"):
                s[k] = d[k]
            s["pos_time"] = now
            if s["max_alt"] is None or d["alt"] > s["max_alt"]:
                s["max_alt"] = d["alt"]
            # burst: falling fast well below the highest point
            if not s["burst"] and d["vv"] < -8 and s["max_alt"] - d["alt"] > 200 and s["max_alt"] > 5000:
                s["burst"] = True
                s["burst_alt"] = s["max_alt"]
            pts = s["pts"]
            if not pts or now - pts[-1][3] >= TRACK_SEC:
                pts.append([d["lat"], d["lon"], d["alt"], now])
                if len(pts) > MAX_TRACK:
                    del pts[1:len(pts) - MAX_TRACK + 1]

    def _emit_state(self):
        self.on_event("sondestate", self.info(frames=False))

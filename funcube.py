"""FUNcube telemetry: the AO-40 FEC frame (as sent by FUNcube-1 / AO-73, Nayif-1 / EO-88, JY1Sat / JO-97) and the
realtime telemetry of its 256-byte data block.

AO-40 FEC (Phil Karn, KA9Q): 256 data bytes -> two interleaved Reed-Solomon RS(255,223) codewords, each shortened to
(160,128) -> CCSDS scrambling of the 320 bytes -> convolutional code r=1/2 K=7 (polynomials 0x4F, 0x6D, the second
inverted) with 6 tail bits = 5132 channel bits -> a block interleaver of 80 rows x 65 columns, filled row by row with
the 65-bit sync vector first, then the coded bits (3 zeros pad it). The 5200 symbols (4.33 s at 1200 Bd) are sent column
by column, so a sync bit starts every 80 symbols.

decode_frame() takes the 5200 soft symbols of one frame (positive = 1, as the sync search find_sync() gives them) and
returns the 256 data bytes or None. parse() turns a data block into a dict of the realtime telemetry.
The frame layout follows the FUNcube telemetry description of AMSAT-UK (and its use in gr-satellites by Daniel Estévez).
"""
import numpy as np

ROWS, COLS = 80, 65
FRAME_SYMS = ROWS * COLS                      # 5200
CODED_BITS = 5132                             # (320 bytes * 8 + 6 tail bits) * 2
DATA_BYTES = 256
SYNC = np.array([int(c) for c in "11111110000111011110010110010010000001000100110001011101011011000"], np.int8)
SYNC_PM = (2.0 * SYNC - 1.0).astype(np.float32)

# ---------- convolutional code r=1/2 K=7 ----------

_POLY_A, _POLY_B = 0x4F, 0x6D


def _parity(x):
    return bin(x).count("1") & 1


# encoder: reg = (state << 1 | bit) & 0x7F, next state = reg & 0x3F; outputs parity(reg & A), not parity(reg & B).
# For a next state s the two predecessors are p = (s >> 1) | (b << 5), b = 0/1, i.e. reg = (b << 6) | s.
_NS = np.arange(64)
_PRED = np.stack([(_NS >> 1), (_NS >> 1) | 32])                              # [b, s]
_OUT = np.array([[[_parity(((b << 6) | s) & _POLY_A), 1 - _parity(((b << 6) | s) & _POLY_B)] for s in range(64)]
                 for b in (0, 1)], np.float32)                               # [b, s, 2]
_OUT_PM = 2 * _OUT - 1


def viterbi(soft):
    """Soft-decision Viterbi of the terminated code (starts and ends in state 0); soft: 2 per bit, positive = 1.
    Returns the decoded bits (tail included) as uint8 0/1."""
    soft = np.asarray(soft, np.float32).reshape(-1, 2)
    n = len(soft)
    metric = np.full(64, -1e9, np.float32)
    metric[0] = 0.0
    dec = np.zeros((n, 64), np.uint8)
    for i in range(n):
        bm = _OUT_PM[..., 0] * soft[i, 0] + _OUT_PM[..., 1] * soft[i, 1]    # [b, s]
        cand = metric[_PRED] + bm
        pick = cand[1] > cand[0]
        dec[i] = pick
        metric = np.where(pick, cand[1], cand[0])
    bits = np.zeros(n, np.uint8)
    s = 0
    for i in range(n - 1, -1, -1):
        bits[i] = s & 1
        s = (s >> 1) | (int(dec[i, s]) << 5)
    return bits


# ---------- CCSDS scrambler: h(x) = x^8 + x^7 + x^5 + x^3 + 1, all ones at the start ----------

def _ccsds_pn(nbytes):
    a = [1] * 8
    while len(a) < nbytes * 8:
        n = len(a) - 8
        a.append(a[n + 7] ^ a[n + 5] ^ a[n + 3] ^ a[n])
    return np.packbits(np.array(a[:nbytes * 8], np.uint8))


PN = _ccsds_pn(320)

# ---------- Reed-Solomon RS(255,223) of CCSDS in the conventional basis: GF(2^8) mod 0x187, roots b^(112+i), b = a^11

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x187
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]
NROOTS, FCR, PRIM = 32, 112, 11


def _mul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _inv(a):
    return _EXP[255 - _LOG[a]]


def _beta(n):
    """b^n = a^(11 n)."""
    return _EXP[(PRIM * n) % 255]


def _poly_eval(p, x):
    """p[0] + p[1] x + p[2] x^2 ..."""
    y = 0
    for c in reversed(p):
        y = _mul(y, x) ^ c
    return y


def rs_decode(cw, pad=0):
    """Corrects a 255-byte codeword in place (cw[0] first sent = highest power); the first pad bytes are the zeros of a
    shortened code. Returns the number of corrected bytes, or -1 if it cannot be corrected."""
    # syndromes S_i = r(b^(FCR+i)), r(x) = sum cw[j] x^(254-j)
    synd = []
    for i in range(NROOTS):
        x = _beta(FCR + i)
        s = 0
        for c in cw:
            s = _mul(s, x) ^ c
        synd.append(s)
    if not any(synd):
        return 0
    # Berlekamp-Massey: lam(x) = prod (1 - X_k x)
    lam, b = [1], [1]
    L, m = 0, 1
    bb = 1
    for n in range(NROOTS):
        d = synd[n]
        for i in range(1, L + 1):
            if i < len(lam):
                d ^= _mul(lam[i], synd[n - i])
        if d == 0:
            m += 1
            continue
        coef = _mul(d, _inv(bb))
        t = lam[:]
        shifted = [0] * m + [_mul(coef, c) for c in b]
        if len(shifted) > len(lam):
            lam = lam + [0] * (len(shifted) - len(lam))
        for i, c in enumerate(shifted):
            lam[i] ^= c
        if 2 * L <= n:
            L, b, bb, m = n + 1 - L, t, d, 1
        else:
            m += 1
    while len(lam) > 1 and lam[-1] == 0:
        lam.pop()
    deg = len(lam) - 1
    if deg != L or deg == 0 or deg > NROOTS // 2:
        return -1
    # Chien search over the powers of the codeword: X = b^p, root of lam at X^-1
    locs = []
    for p in range(255):
        if _poly_eval(lam, _beta(-p % 255)) == 0:
            locs.append(p)
    if len(locs) != deg:
        return -1
    # Forney: e = X^(1-FCR) omega(X^-1) / lam'(X^-1), omega = S(x) lam(x) mod x^NROOTS
    omega = [0] * NROOTS
    for i, li in enumerate(lam):
        for j in range(NROOTS - i):
            omega[i + j] ^= _mul(li, synd[j])
    dlam = [lam[i] if i % 2 == 1 else 0 for i in range(1, len(lam))]     # formal derivative (char 2)
    for p in locs:
        pos = 254 - p
        if pos < pad:
            return -1
        xinv = _beta(-p % 255)
        den = _poly_eval(dlam, xinv)
        if den == 0:
            return -1
        num = _mul(_poly_eval(omega, xinv), _beta((p * (1 - FCR)) % 255))
        cw[pos] ^= _mul(num, _inv(den))
    return len(locs)


# ---------- the frame ----------

def find_sync(soft, threshold=8):
    """Start indexes of frames in a soft symbol stream (positive = 1): the 65 sync bits every 80 symbols with at most
    threshold errors. Returns [(index, errors), ...]; a frame needs FRAME_SYMS symbols from its index."""
    soft = np.asarray(soft, np.float32)
    n = len(soft) - FRAME_SYMS + 1
    if n <= 0:
        return []
    hard = (soft > 0).astype(np.int8)
    err = np.zeros(n, np.int16)
    for j in range(COLS):
        err += hard[j * ROWS: j * ROWS + n] != SYNC[j]
    out = []
    for i in np.flatnonzero(err <= threshold):
        if out and i - out[-1][0] < FRAME_SYMS // 2:
            if err[i] < out[-1][1]:
                out[-1] = (int(i), int(err[i]))
            continue
        out.append((int(i), int(err[i])))
    return out


def decode_frame(soft):
    """5200 soft symbols of a frame from its sync -> (256 data bytes or None, info dict)."""
    soft = np.asarray(soft, np.float32)[:FRAME_SYMS]
    info = {"sync_err": int(np.sum((soft[::ROWS] > 0) != SYNC))}
    # deinterleave: sent by columns of 80, filled by rows of 65; the first row is the sync vector
    de = soft.reshape(COLS, ROWS).T.ravel()[COLS:COLS + CODED_BITS]
    scale = np.mean(np.abs(de)) or 1.0
    bits = viterbi(de / scale)
    # channel bit errors: re-encode and compare with the hard decisions
    coded = _encode(bits)
    info["ch_err"] = int(np.sum(coded != (de > 0)))
    data = np.packbits(bits[:320 * 8]) ^ PN
    out = bytearray(DATA_BYTES)
    rs = []
    for j in range(2):
        cw = [0] * 95 + [int(v) for v in data[j::2]]
        n = rs_decode(cw, pad=95)
        rs.append(n)
        if n < 0:
            info["rs"] = rs
            return None, info
        out[j::2] = bytes(cw[95:95 + 128])
    info["rs"] = rs
    return bytes(out), info


def _rs_generator():
    g = [1]                                   # highest power first
    for i in range(NROOTS):
        r = _beta(FCR + i)
        g = [a ^ _mul(b, r) for a, b in zip(g + [0], [0] + g)]
    return g


_GEN = _rs_generator()


def rs_parity(msg):
    """The 32 parity bytes of RS(255,223) for the 223 message bytes (msg[0] = highest power)."""
    rem = [0] * NROOTS
    for m in msg:
        fb = m ^ rem[0]
        rem = rem[1:] + [0]
        if fb:
            for j in range(NROOTS):
                rem[j] ^= _mul(fb, _GEN[j + 1])
    return rem


def encode_frame(data):
    """256 data bytes -> the 5200 channel bits (0/1) of an AO-40 FEC frame, the inverse of decode_frame(): for the
    tests and the signal generator."""
    data = bytes(data)
    if len(data) != DATA_BYTES:
        raise ValueError("AO-40 frame needs 256 bytes")
    rs = bytearray(320)
    for j in range(2):
        msg = [0] * 95 + list(data[j::2])
        cw = msg + rs_parity(msg)
        rs[j::2] = bytes(cw[95:])
    bits = np.unpackbits(np.frombuffer(bytes(rs), np.uint8) ^ PN)
    coded = _encode(np.concatenate((bits, np.zeros(6, np.uint8))))
    v = np.zeros(FRAME_SYMS, np.uint8)
    v[:COLS] = SYNC
    v[COLS:COLS + CODED_BITS] = coded
    return v.reshape(ROWS, COLS).T.ravel()


def _encode(bits):
    reg = 0
    out = np.zeros(2 * len(bits), np.uint8)
    for i, b in enumerate(bits):
        reg = ((reg << 1) | int(b)) & 0x7F
        out[2 * i] = _parity(reg & _POLY_A)
        out[2 * i + 1] = 1 - _parity(reg & _POLY_B)
    return out


# ---------- telemetry ----------

SATS = {0: "FUNcube-1 EM", 1: "FUNcube-2", 2: "FUNcube-1 (AO-73)", 3: "extended"}
EXT_SATS = {0x08: "Nayif-1 (EO-88)"}


def _frame_type(n, nayif=False):
    if n < 12:
        return f"WO{n + 1}"
    if nayif:
        if n < 17:
            return f"HR{n - 11}"
        return f"FM{n - 16}" if n < 24 else f"#{n}"
    hr = {12: 1, 16: 2, 20: 3}
    if n in hr:
        return f"HR{hr[n]}"
    fm = {13: 1, 14: 2, 15: 3, 17: 4, 18: 5, 19: 6, 21: 7, 22: 8, 23: 9}
    return f"FM{fm[n]}" if n in fm else f"#{n}"


class _Bits:
    def __init__(self, data):
        self.v = int.from_bytes(data, "big")
        self.n = len(data) * 8
        self.p = 0

    def get(self, k):
        self.p += k
        return (self.v >> (self.n - self.p)) & ((1 << k) - 1)


def parse(data):
    """256 data bytes -> dict: sat, frame type, the realtime telemetry of FUNcube-1 (values converted where the
    conversion is published) and the text of a fitter message."""
    if len(data) != DATA_BYTES:
        return {}
    sat_id, ftype = data[0] >> 6, data[0] & 0x3F
    out = {"sat_id": sat_id, "sat": SATS[sat_id], "type": _frame_type(ftype, sat_id == 3)}
    body = data[1:]
    if sat_id == 3:
        out["sat"] = EXT_SATS.get(data[1], f"extended 0x{data[1]:02X}")
        body = data[2:]
    if sat_id in (0, 2):                       # FUNcube-1: 55 bytes of realtime telemetry
        b = _Bits(body[:55])
        pv = [b.get(16) for _ in range(3)]
        rt = {"photo_mV": pv, "photo_mA": b.get(16), "batt_mV": b.get(16), "sys_mA": b.get(16),
              "reboots": b.get(16), "sw_errors": b.get(16), "boost_C": [b.get(8) for _ in range(3)],
              "batt_C": _s8(b.get(8)), "latchup_5V": b.get(8), "latchup_3V3": b.get(8), "reset_cause": b.get(8),
              "mppt_mode": b.get(8)}
        rt["sun_sensor"] = [b.get(10) for _ in range(3)]
        rt["panel_C"] = {k: round(m * b.get(10) + c, 1) for k, m, c in
                         (("X+", -0.2073, 158.239), ("X-", -0.2083, 159.227), ("Y+", -0.2076, 158.656),
                          ("Y-", -0.2087, 159.045))}
        rt["v3v3_mV"] = 4 * b.get(10)
        rt["i3v3_mA"] = b.get(10)
        rt["v5_mV"] = 6 * b.get(10)
        rf = {"rx_doppler": b.get(8), "rx_rssi": b.get(8), "temp_C": round(-0.857 * b.get(8) + 193.672, 1),
              "rx_mA": round(0.636 * b.get(8), 1), "tx3v3_mA": round(0.636 * b.get(8), 1),
              "tx5v_mA": round(1.272 * b.get(8), 1)}
        rev, fwd = b.get(8), b.get(8)
        pa = {"rev_mW": round(5e-3 * rev ** 2.0629, 1), "fwd_mW": round(5e-3 * fwd ** 2.0629, 1),
              "board_temp_raw": b.get(8), "board_mA": round(0.5496 * b.get(8) + 2.5435, 1)}
        ants = {"temp_raw": [b.get(8), b.get(8)], "deployed": [bool(b.get(1)) for _ in range(4)]}
        sw = {"seq": b.get(24), "dtmf_count": b.get(6), "dtmf_last": b.get(5), "dtmf_ok": bool(b.get(1)),
              "data_valid": [bool(b.get(1)) for _ in range(7)], "eclipse": bool(b.get(1)),
              "safe_mode": bool(b.get(1)), "hw_abf": bool(b.get(1)), "sw_abf": bool(b.get(1)),
              "deploy_wait": bool(b.get(1))}
        out.update(eps=rt, rf=rf, pa=pa, ants=ants, sw=sw)
        payload = body[55:55 + 200]
    else:
        payload = body[-200:]
    if out["type"].startswith("FM"):
        out["message"] = bytes(payload).split(b"\0")[0].decode("ascii", "replace").strip()
    return out


def _s8(v):
    return v - 256 if v > 127 else v


def summary(t):
    """A short line of the main values of parse()."""
    if "eps" not in t:
        return f"{t.get('sat', '?')} {t.get('type', '')}"
    e, sw, rf, pa = t["eps"], t["sw"], t["rf"], t["pa"]
    s = (f"seq {sw['seq']} · batt {e['batt_mV'] / 1000:.2f} V {e['batt_C']} °C · sys {e['sys_mA']} mA · "
         f"solar {e['photo_mA']} mA · RF {rf['temp_C']} °C · PA fwd {pa['fwd_mW']} mW")
    if sw["eclipse"]:
        s += " · eclipse"
    if sw["safe_mode"]:
        s += " · SAFE"
    return s

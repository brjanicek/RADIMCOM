"""Draws the RADIMCOM icon (a spectrum peak over a waterfall on a dark rounded square) without Pillow, numpy only:
installer/radimcom.ico (RADIMCOM.exe, setup, shortcuts) and static/favicon.png (the page, the app window).

  python installer/make_icon.py
"""
import os
import struct
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
SS = 4                                  # supersampling


def hexrgb(h):
    return np.array([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)])


BG_TOP, BG_BOT = hexrgb("#16304f"), hexrgb("#070f1b")
TRACE = hexrgb("#ffd84a")               # --accent of the page
FILL_TOP, FILL_BOT = hexrgb("#ffb547"), hexrgb("#ff7a1a")
WF_LO, WF_MID = hexrgb("#0d2a52"), hexrgb("#2f68b0")


def curve(x):
    """Spectrum: noise floor, a strong carrier in the middle, two weaker ones (0 = bottom, 1 = top)."""
    y = 0.08 + 0.018 * np.sin(x * 61.0) + 0.012 * np.sin(x * 23.0 + 1.0)
    y += 0.84 * np.exp(-((x - 0.5) / 0.06) ** 2)
    y += 0.28 * np.exp(-((x - 0.18) / 0.05) ** 2)
    y += 0.18 * np.exp(-((x - 0.82) / 0.045) ** 2)
    return y


def colormap(s):
    """Waterfall: dark blue -> blue -> yellow accent."""
    s = s.clip(0, 1)[..., None]
    lo = WF_LO * (1 - s / 0.45) + WF_MID * (s / 0.45)
    hi = WF_MID * (1 - (s - 0.45) / 0.55) + TRACE * ((s - 0.45) / 0.55)
    return np.where(s < 0.45, lo, hi)


def rounded(X, Y, x0, x1, y0, y1, r):
    dx = np.maximum(np.maximum(x0 + r - X, X - (x1 - r)), 0)
    dy = np.maximum(np.maximum(y0 + r - Y, Y - (y1 - r)), 0)
    return (dx ** 2 + dy ** 2) <= r ** 2


def render(size):
    """Spectrum peak on top, a waterfall of the same carriers below, on a dark rounded square."""
    n = size * SS
    c = (np.arange(n) + 0.5) / n
    X, Y = np.meshgrid(c, c)                       # Y down
    small = size <= 24
    m = 0.02 if small else 0.03
    inside = rounded(X, Y, m, 1 - m, m, 1 - m, 0.2)
    t = ((Y - m) / (1 - 2 * m)).clip(0, 1)[..., None]
    rgb = BG_TOP * (1 - t) + BG_BOT * t
    # spectrum area (top half)
    px0, px1 = (0.09, 0.91) if small else (0.125, 0.875)
    py0, py1 = (0.1, 0.52) if small else (0.12, 0.5)
    u = (X - px0) / (px1 - px0)
    v = (py1 - Y) / (py1 - py0)                    # 0 bottom, 1 top
    in_x = (u >= 0) & (u <= 1)
    cy = curve(u.clip(0, 1))
    under = in_x & (v <= cy) & (v >= 0)
    ft = (1 - (v / np.maximum(cy, 1e-3))).clip(0, 1)[..., None]
    fill = FILL_TOP * (1 - ft) + FILL_BOT * ft
    alpha_fill = (0.55 + 0.3 * (1 - ft)) if not small else 0.9
    rgb = np.where(under[..., None], rgb * (1 - alpha_fill) + fill * alpha_fill, rgb)
    du = 1e-3
    slope = (curve((u + du).clip(0, 1)) - curve((u - du).clip(0, 1))) / (2 * du) * (py1 - py0) / (px1 - px0)
    dist = np.abs(v - cy) * (py1 - py0) / np.sqrt(1 + slope ** 2)
    w = 0.04 if small else 0.014
    rgb = np.where((in_x & (dist < w) & (v >= 0))[..., None], TRACE, rgb)
    # waterfall (bottom part): same carriers, rows with a little fading
    wy0, wy1 = (0.58, 0.9) if small else (0.53, 0.86)
    wf = rounded(X, Y, px0, px1, wy0, wy1, 0 if small else 0.025)
    rows = 3 if small else 5
    k = ((Y - wy0) / (wy1 - wy0) * rows).clip(0, rows - 1e-6)
    fade = 1 - 0.12 * np.floor(k) + 0.06 * np.sin(np.floor(k) * 2.3)
    s = ((curve(u.clip(0, 1)) - 0.1) / 0.8).clip(0, 1) ** 0.7 * fade
    rgb = np.where(wf[..., None], colormap(s), rgb)
    if not small:                                  # dark gaps between rows
        gap = wf & (np.abs(k - np.round(k)) < 0.08) & (k > 0.5) & (k < rows - 0.5)
        rgb = np.where(gap[..., None], rgb * 0.6, rgb)
    a = inside.astype(float)
    rgb = rgb * a[..., None]
    # downsample (premultiplied)
    rgb = rgb.reshape(size, SS, size, SS, 3).mean(axis=(1, 3))
    a = a.reshape(size, SS, size, SS).mean(axis=(1, 3))
    out = np.where(a[..., None] > 0, rgb / np.maximum(a, 1e-6)[..., None], 0)
    return np.dstack([out, a])


def png(img):
    h, w = img.shape[:2]
    raw = (img.clip(0, 1) * 255 + 0.5).astype(np.uint8)
    rows = b"".join(b"\0" + raw[y].tobytes() for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def dib(img):
    """Icon image as a classic DIB (BITMAPINFOHEADER, 32-bit BGRA bottom-up + AND mask): Explorer and the taskbar
    read PNG reliably only for 256 px; smaller PNG entries may show the default icon there."""
    h, w = img.shape[:2]
    rgba = (img.clip(0, 1) * 255 + 0.5).astype(np.uint8)
    bgra = rgba[::-1, :, [2, 1, 0, 3]].tobytes()                     # bottom-up rows
    mask_row = ((w + 31) // 32) * 4
    mask = bytes(mask_row * h)                                      # all 0: alpha decides
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(bgra) + len(mask), 0, 0, 0, 0)
    return header + bgra + mask


def ico(images):
    """images: [(size, rgba array)] -> .ico; 256 px as PNG, the smaller ones as DIB."""
    head = struct.pack("<HHH", 0, 1, len(images))
    off = 6 + 16 * len(images)
    dirs, body = b"", b""
    for size, img in images:
        data = png(img) if size >= 256 else dib(img)
        dirs += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), off + len(body))
        body += data
    return head + dirs + body


def main():
    imgs = [(s, render(s)) for s in SIZES]
    with open(os.path.join(HERE, "radimcom.ico"), "wb") as f:
        f.write(ico(imgs))
    with open(os.path.join(ROOT, "static", "favicon.png"), "wb") as f:
        f.write(png(dict(imgs)[64]))
    print("installer/radimcom.ico, static/favicon.png")


if __name__ == "__main__":
    main()

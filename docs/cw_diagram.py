"""Draws docs/images/cw_decoder.png: block diagram of the CW decoder (cw.py) and where it takes the signal from the
receiver chain (sdr.py), i.e. which receiver functions (gain, AGC+, DC, spurs, filter, ALC, DNR...) it sees.

  python docs/cw_diagram.py

Same drawing helpers and rendering as docs/block_diagram.py (an SVG in a page, turned into a PNG by Chrome or Edge).
"""
import os
import subprocess
import sys
import tempfile
from html import escape as E

W, H = 2800, 1650
INK = "#1f2933"; MUTE = "#5b6875"; LINE = "#c3ccd5"
C = {"iq": "#0b6fb8", "audio": "#c2570c", "ctl": "#39434e", "ev": "#7a3fb5", "fb": "#12805c", "no": "#9aa3ad"}
FILL = {"hw": "#e7e9ec", "dsp": "#e8f6f3", "audio": "#fdf0e6", "dec": "#fdf3e4", "ch": "#fffaf0", "out": "#f3eefa",
        "yes": "#e8f1fb", "not": "#f2f4f6"}
o = []


def rect(x, y, w, h, fill="#fff", stroke=LINE, sw=1.5, r=8, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def text(x, y, s, size=15, fill=INK, weight=400, anchor="start", mono=False, halo=False):
    fam = "Consolas,monospace" if mono else "'Segoe UI',Arial,sans-serif"
    h = ' paint-order="stroke" stroke="#fff" stroke-width="5" stroke-linejoin="round"' if halo else ''
    o.append(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
             f'text-anchor="{anchor}"{h}>{E(s)}</text>')


def group(x, y, w, h, title, fill, sub=None, stroke="#9aa6b2", dash=None, tx=None):
    rect(x, y, w, h, fill=fill, stroke=stroke, r=12, dash=dash)
    tx = x + 16 if tx is None else tx
    text(tx, y + 27, title, 18, weight=700)
    if sub:
        text(tx, y + 49, sub, 13.5, MUTE)


def box(x, y, w, h, name, lines=(), fill="#fff", size=15, stroke=LINE, name_fill=INK):
    rect(x, y, w, h, fill=fill, stroke=stroke)
    n = 1 + len(lines); lh = 18
    y0 = y + h / 2 - (n * lh) / 2 + 14
    text(x + w / 2, y0, name, size, name_fill, weight=700, anchor="middle")
    for i, l in enumerate(lines):
        text(x + w / 2, y0 + (i + 1) * lh, l, 13, MUTE, anchor="middle")


def path(pts, kind, end=True, dash=None, sw=2.4):
    d = "M" + " L".join(f"{a},{b}" for a, b in pts)
    c = C[kind]
    o.append(f'<path d="{d}" fill="none" stroke="#fff" stroke-width="{sw + 4}"/>')
    a = f' marker-end="url(#a-{kind})"' if end else ''
    ds = f' stroke-dasharray="{dash}"' if dash else ''
    o.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="{sw}"{ds}{a}/>')


def label(x, y, s, kind=None, anchor="middle", size=13):
    text(x, y, s, size, C[kind] if kind else MUTE, 600 if kind else 400, anchor, halo=True)


def chain(x0, y, w, h, gap, items, kind, fill="#fff"):
    """Boxes in a row joined by arrows; returns the x of each box."""
    xs = []
    x = x0
    for name, lines in items:
        box(x, y, w, h, name, lines, fill=fill)
        xs.append(x)
        x += w + gap
    for a in xs[:-1]:
        path([(a + w, y + h / 2), (a + w + gap, y + h / 2)], kind)
    return xs


# ---------- title ----------
text(40, 50, "RADIMCOM: how the CW decoder works", 32, weight=700)
text(40, 78, "cw.py (skimmer, up to 16 stations at once) and where it takes the signal from the receiver chain of a VFO "
             "(sdr.py). Ver. 0.115beta1", 16, MUTE)

# ---------- receiver chain (row A) ----------
BY, BH = 175, 104
group(30, 105, 640, 290, "Dongle (RTL-SDR)", FILL["hw"], "gain stages before the A/D converter")
box(50, BY, 120, BH, "Antenna", ["(HF: upconverter", "or RTL V4 HF)"], size=15)
box(190, BY, 210, BH, "Tuner R828D", ["RF gain: manual steps", "or TUNER AGC", "(MENU › VFO › gain)"])
box(420, BY, 230, BH, "RTL2832U", ["A/D converter, 8 bit", "RTL AGC = digital gain", "after the A/D (optional)"])
path([(170, BY + BH / 2), (190, BY + BH / 2)], "iq")
path([(400, BY + BH / 2), (420, BY + BH / 2)], "iq")

group(690, 105, 1040, 290, "Receiver IQ chain (sdr.py)", FILL["dsp"], "the whole band of the dongle, then the VFO channel", tx=812)
xs = chain(710, BY, 165, BH, 22, [
    ("AGC+", ["tuner gain as high as", "the A/D allows (watches", "clipping of each block)"]),
    ("Remove DC peak", ["the dongle's DC spike", "in the band centre"]),
    ("Shift (NCO)", ["tuned frequency", "→ 0 Hz"]),
    ("Decimator ÷64", ["polyphase FIR", "e.g. 2.048 MS/s", "→ 32 kS/s"]),
    ("SPUR removal", ["learnt spur lines", "notched (SPUR on)"]),
], "iq")
path([(650, BY + BH / 2), (710, BY + BH / 2)], "iq")
label(680, BY + BH / 2 - 10, "USB")
# AGC+ sets the tuner gain (feedback over the top)
path([(792, 105), (792, 96), (295, 96), (295, BY)], "fb", dash="7 5")
label(546, 90, "AGC+ sets the tuner gain (turns TUNER AGC and RTL AGC off)", "fb")
path([(792, 105), (792, BY)], "fb", end=False, dash="7 5")
# waterfall branch
box(897, 312, 165, 58, "Spectrum, waterfall", ["(display only)"], size=14)
path([(979, BY + BH), (979, 312)], "iq")

# tap
TAPX = 1672
path([(xs[-1] + 165, BY + BH / 2), (TAPX, BY + BH / 2)], "iq", end=False)
o.append(f'<circle cx="{TAPX}" cy="{BY + BH / 2}" r="9" fill="{C["iq"]}" stroke="#fff" stroke-width="3"/>')
label(TAPX, BY - 12, "tap", "iq")
label(TAPX + 10, BY + BH + 22, "baseband", "iq", anchor="start")

# ---------- audio chain (row A, right) ----------
group(1750, 105, 1020, 290, "Audio chain: only for listening", FILL["audio"],
      "after the tap – none of this reaches the CW decoder", stroke="#d9a27a")
axs = chain(1766, BY, 147, BH, 21, [
    ("Channel filter", ["mode + bandwidth", "(CW 300–1200 Hz),", "NOTCH"]),
    ("Demodulator", ["CW: BFO,", "tone 700 Hz"]),
    ("ALC", ["audio AGC", "(ALC key)"]),
    ("DNR", ["EXP: noise down", "LIM: soft limiter"]),
    ("AFI, LPF, HPF", ["voice inversion,", "audio filters"]),
    ("SQL, volume", ["squelch, MAIN,", "MUTE → browser"]),
], "audio")
path([(TAPX, BY + BH / 2), (1766, BY + BH / 2)], "audio")

# ---------- CW decoder ----------
DY = 455
group(30, DY, 2740, 795, "CW decoder (cw.py) – runs in the VFO process on every baseband block", FILL["dec"],
      "its own levels, speed and thresholds from the signal: independent of the volume, ALC, DNR and the audio filter",
      tx=300)
path([(TAPX, BY + BH / 2 + 9), (TAPX, 420), (170, 420), (170, DY + 75)], "iq")
label(900, 412, "complex baseband (the tuned frequency at 0 Hz), e.g. 32 kS/s", "iq")

# common part (row 1)
R1 = DY + 75; RH = 104
cxs = chain(60, R1, 220, RH, 30, [
    ("Decimation to 8 kHz", ["FIR 63 taps"]),
    ("Noise blanker", ["bursts ≤ 20 ms, > 4.5× noise", "and > 3× the strongest", "station → zero (crashes)"]),
    ("Buffer 6 s", ["for the spectrum and", "the start of new stations"]),
    ("Station search", ["Welch spectrum, 2 Hz", "peaks ≥ 6 dB over the noise,", "sidebands masked, max. 16"]),
], "iq")
text(cxs[3] + 110, R1 + RH + 24, "every 0.5 s", 13, MUTE, anchor="middle")
# SPAN input from the channel filter bandwidth
path([(1839, BY + BH), (1839, 438), (990, 438), (990, R1)], "ctl", dash="4 4")
label(1450, 432, "mode + bandwidth = SPAN Filter search range (Wide: ±3.4 kHz)", "ctl")
# outputs of the search
box(1080, R1, 260, RH, "Stations + noise", ["tone of each station,", "spectral SNR, noise level σ,", "new: last 3 s from the buffer"],
    fill="#fff")
path([(1030, R1 + RH / 2), (1080, R1 + RH / 2)], "iq")

# per-station channels (row 2)
R2 = DY + 300; CH = 120
for d in (16, 8):
    rect(50 + d, R2 - 30 + d, 2690, 225, fill="#f6ead2", stroke="#c9b07a", r=10)
rect(50, R2 - 30, 2690, 225, fill=FILL["ch"], stroke="#c9b07a", r=10)
text(2724, R2 - 9, "One channel per station: up to 16 in parallel, all fed with the same 8 kHz samples", 15,
     weight=700, anchor="end")
kxs = chain(66, R2, 233, CH, 32, [
    ("Mixer (NCO)", ["station tone → 0 Hz"]),
    ("CIC ÷16", ["→ 500 Hz, 2 ms steps;", "nulls where other", "stations would alias"]),
    ("Matched filter", ["Gaussian, width", "¼ dot (by speed)"]),
    ("Envelope |x|", ["mark level vs noise"]),
    ("Likelihood ratio", ["mark / space per step:", "Rice (level A) vs", "Rayleigh (noise σ)"]),
    ("Viterbi, 2 states", ["key down / up decided", "a few dots later", "(no fixed threshold)"]),
    ("Lengths", ["marks and gaps (ms)", "quality = level / noise"]),
    ("Timing profile", ["dot, dash, 3 gaps (log-normal),", "speed, Farnsworth,", "paddle / bug / straight key"]),
    ("Beam search", ["12 readings of the", "elements → characters", "+ confidence 0–9"]),
], "iq")
# from "Stations + noise" to the channels
path([(1150, R1 + RH), (1150, R2 - 56), (182, R2 - 56), (182, R2)], "ctl", dash="4 4")
label(640, R2 - 62, "tone of each station", "ctl")
path([(1270, R1 + RH), (1270, R2 - 44), (kxs[4] + 116, R2 - 44), (kxs[4] + 116, R2)], "ctl", dash="4 4")
label(1290, R2 - 50, "noise level σ", "ctl", anchor="start")

# feedback loops (under the channel row)
FB = R2 + CH
path([(kxs[2] + 116, FB), (kxs[2] + 116, FB + 34), (kxs[0] + 116, FB + 34), (kxs[0] + 116, FB)], "fb", dash="7 5")
label((kxs[0] + kxs[2]) / 2 + 116, FB + 28, "fine tone tracking (phase turn during marks)", "fb")
path([(kxs[6] + 116, FB), (kxs[6] + 116, FB + 34), (kxs[4] + 150, FB + 34), (kxs[4] + 150, FB)], "fb", dash="7 5")
label((kxs[4] + kxs[6]) / 2 + 133, FB + 28, "mark level A: Kalman on log A (follows QSB)", "fb")
path([(kxs[7] + 116, FB), (kxs[7] + 116, FB + 62), (kxs[2] + 150, FB + 62), (kxs[2] + 150, FB)], "fb", dash="7 5")
label((kxs[2] + kxs[7]) / 2 + 133, FB + 56, "speed: matched filter width, Viterbi delay, glitch limit", "fb")

# outputs (row 3)
R3 = DY + 650; OH = 92
group(50, R3 - 18, 2690, 128, "", FILL["out"])
BUS = R3 - 44
path([(kxs[8] + 116, R2 + CH), (kxs[8] + 116, BUS), (280, BUS)], "ev", end=False)
label(1250, BUS - 8, "characters + confidence (white / amber / grey) of every station", "ev")
oxs = [70, 520, 970, 1420, 1870]
for x in oxs:
    path([(x + 210, BUS), (x + 210, R3)], "ev")
outs = [
    ("Call sign", ["pattern in the text", "(the word after DE first)"]),
    ("cwchan event", ["new characters of each", "station → CW table rows"]),
    ("cwtext event", ["the followed station →", "LOG data\\logs\\cw_*.txt,", "audio spectrum bubble"]),
    ("cwstate event (1/s)", ["stations, WPM, SNR, profile", "→ table, header,", "▲ marks in the spectrum"]),
    ("GET /api/cw", ["?id=N: the whole text", "of a station (opened row)"]),
]
for x, (n, ls) in zip(oxs, outs):
    box(x, R3, 420, OH, n, ls)

# ---------- what affects it ----------
LY = 1280
group(30, LY, 1340, 340, "Reaches the CW decoder (before the tap)", FILL["yes"], stroke="#7aa7d6")
yes = [
    ("RF gain / TUNER AGC", "sets the level and the noise floor; the decoder measures both itself"),
    ("RTL AGC", "digital gain after the A/D: level changes, handled like fading"),
    ("AGC+", "a gain step = a level jump of all stations; the Kalman mark level follows in a few marks"),
    ("Remove DC peak", "removes the dongle spike at the band centre (a station exactly there is attenuated)"),
    ("SPUR removal", "notches learnt spur lines: a station sitting on a spur line is notched too"),
    ("Tuning (VFO)", "stations keep their RF frequency; a big step restarts the spectrum"),
    ("Mode + bandwidth", "only the search range with SPAN Filter (USB: 150 Hz…bw, CW: ±bw/2)"),
    ("SCAN", "while the VFO scans, the decoders pause"),
]
for i, (a, b) in enumerate(yes):
    y = LY + 82 + i * 31
    text(52, y, a, 15, C["iq"], weight=700)
    text(300, y, b, 14, INK)

group(1400, LY, 1370, 340, "Does not reach it (after the tap: audio only)", FILL["not"], stroke="#b8c0c8")
no = [
    ("Channel filter width", "the decoder has its own filters (a 300 Hz CW filter does not narrow the skimmer)"),
    ("NOTCH", "only in the audio"),
    ("Demodulator, CW tone", "the decoder mixes each station itself"),
    ("ALC", "the decoder sets its own levels; ALC on / off makes no difference"),
    ("DNR (EXP, LIM)", "only shapes what you hear"),
    ("AFI, LPF, HPF", "audio filters for listening"),
    ("Squelch, MAIN, MUTE", "decoding goes on with the audio closed or muted"),
    ("Audio bubble (CW mode)", "with the decoder off: a separate 'peek' decoder on the same baseband"),
]
for i, (a, b) in enumerate(no):
    y = LY + 82 + i * 31
    text(1422, y, a, 15, "#56606b", weight=700)
    text(1680, y, b, 14, INK)

# legend
for i, (k, s) in enumerate([("iq", "samples / data"), ("audio", "audio"), ("fb", "feedback loop"),
                            ("ctl", "parameter"), ("ev", "to the page")]):
    x = 1760 + i * 205
    path([(x, 62), (x + 46, 62)], k, dash="7 5" if k in ("fb", "ctl") else None)
    text(x + 56, 67, s, 14, MUTE)

defs = "<defs>"
for k, c in C.items():
    defs += (f'<marker id="a-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" '
             f'markerUnits="strokeWidth" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>')
defs += "</defs>"
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{defs}'
       f'<rect width="{W}" height="{H}" fill="#fff"/>' + "".join(o) + "</svg>")
page = f'<!DOCTYPE html><html><body style="margin:0">{svg}</body></html>'

BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images", "cw_decoder.png")


def render():
    browser = next((b for b in BROWSERS if os.path.exists(b)), None)
    if not browser:
        sys.exit("Chrome or Edge not found")
    with tempfile.TemporaryDirectory() as tmp:
        html = os.path.join(tmp, "diagram.html")
        png = os.path.join(tmp, "diagram.png")
        with open(html, "w", encoding="utf-8") as f:
            f.write(page)
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={tmp}\\profile",
                        "--force-device-scale-factor=2", f"--window-size={W},{H}", "--virtual-time-budget=1000",
                        f"--screenshot={png}", "file:///" + html.replace("\\", "/")], check=True, timeout=120,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.exists(png):
            sys.exit("the browser did not write the image")
        os.replace(png, OUT)
    print(f"{OUT}: {os.path.getsize(OUT) / 1e6:.1f} MB")


if __name__ == "__main__":
    render()

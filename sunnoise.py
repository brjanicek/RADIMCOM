"""SUN NOISE: the receiving system measured on the Sun or the Moon (SATELLITES › SUN NOISE).

The rotor points the antenna at the Sun (or the Moon), the S-meter power is averaged, then the antenna is turned to
cold sky beside it and averaged again; the ratio is the Y factor. With the flux of the Sun at the frequency, Y gives the
figure of merit of the whole station, G/T (antenna gain over system noise temperature), the number that says how well
EME, weak satellites or meteor scatter can be heard. The measuring (the rotor moves, the averaging) runs in the browser;
this module gives the positions, the solar flux estimate and the G/T arithmetic.

    Sun:  G/T = 8 pi k (Y - 1) / (S lambda^2)            S = flux density in W/m^2/Hz (1 SFU = 1e-22)
    Moon: G/T = 4 pi (Y - 1) / (T_moon Omega_moon)       T_moon about 210 K, Omega = pi (R_moon / distance)^2

Both assume a beam much wider than the disc (true for Yagis up to about 23 cm; a big dish at 10 GHz sees less than
the whole Sun and reads too low). The solar flux at other frequencies than 2800 MHz (F10.7, NOAA, spacewx.py) is an
estimate: the quiet-Sun spectrum interpolated log-log and scaled by today's F10.7. The measured flux of Learmonth,
San Vito or Penticton at a nearby frequency can be entered instead and is then used as is.
"""
import math
import time

import numpy as np

AU_KM = 149597870.7
K_BOLTZMANN = 1.380649e-23
C_M_S = 299792458.0
SFU = 1e-22                       # W/m^2/Hz
MOON_TEMP_K = 210.0               # mean brightness temperature of the lunar disc (microwave)
MOON_RADIUS_KM = 1737.4

# Quiet-Sun flux (SFU) against frequency (MHz) at F10.7 = 70 (solar minimum); the active Sun is this times F10.7 / 70.
# Rounded from the published quiet-Sun spectrum (metre waves: the corona at about 1e6 K over a disc larger than the
# optical one; centimetre waves: the chromosphere).
QUIET_SUN = ((50, 2.0), (144, 8.0), (245, 13.0), (410, 22.0), (610, 32.0), (1415, 50.0), (2800, 70.0),
             (4995, 120.0), (8800, 230.0), (10368, 270.0), (15400, 380.0), (24000, 550.0))
SUN_ID = "sun"


def sun_geocentric(jd):
    """Low-precision Sun (Astronomical Almanac, about 0.01 degree) at Julian dates jd ->
    (x, y, z) km, equatorial of date, as moon.geocentric()."""
    n = np.asarray(jd, float) - 2451545.0
    r = math.pi / 180.0
    lon_mean = (280.460 + 0.9856474 * n) * r
    g = (357.528 + 0.9856003 * n) * r
    lam = lon_mean + (1.915 * np.sin(g) + 0.020 * np.sin(2 * g)) * r
    dist = (1.00014 - 0.01671 * np.cos(g) - 0.00014 * np.cos(2 * g)) * AU_KM
    eps = (23.439 - 4e-7 * n) * r
    return dist * np.cos(lam), dist * np.cos(eps) * np.sin(lam), dist * np.sin(eps) * np.sin(lam)


class SunSat:
    """Stands in for an sgp4 Satrec, like moon.MoonSat: sattrack.look() takes it as a satellite."""

    DT_DAYS = 60.0 / 86400.0

    def sgp4_array(self, jd_i, jd_f):
        jd = np.asarray(jd_i, float) + np.asarray(jd_f, float)
        r = np.stack(sun_geocentric(jd), axis=1)
        r1 = np.stack(sun_geocentric(jd + self.DT_DAYS), axis=1)
        r0 = np.stack(sun_geocentric(jd - self.DT_DAYS), axis=1)
        v = (r1 - r0) / (2 * self.DT_DAYS * 86400.0)
        return np.zeros(len(jd), int), r, v


def sun_flux_sfu(f_mhz, f107):
    """Estimated solar flux (SFU) at f_mhz from today's F10.7 (None = solar minimum, 70)."""
    f = min(max(float(f_mhz), QUIET_SUN[0][0]), QUIET_SUN[-1][0])
    xs = [math.log(a) for a, _ in QUIET_SUN]
    ys = [math.log(b) for _, b in QUIET_SUN]
    q = math.exp(float(np.interp(math.log(f), xs, ys)))
    return q * max(float(f107 or 70.0), 60.0) / 70.0


def gt_sun(y_db, sfu, f_hz):
    """G/T in dB/K from the Sun: Y in dB, flux in SFU at the frequency f_hz."""
    y = 10 ** (y_db / 10.0)
    if y <= 1.0 or sfu <= 0:
        return None
    lam = C_M_S / f_hz
    return 10 * math.log10(8 * math.pi * K_BOLTZMANN * (y - 1) / (sfu * SFU * lam * lam))


def moon_solid_angle(range_km):
    return math.pi * (MOON_RADIUS_KM / range_km) ** 2


def gt_moon(y_db, range_km, t_moon=MOON_TEMP_K):
    """G/T in dB/K from the Moon (Y in dB, its distance in km)."""
    y = 10 ** (y_db / 10.0)
    if y <= 1.0:
        return None
    return 10 * math.log10(4 * math.pi * (y - 1) / (t_moon * moon_solid_angle(range_km)))


def expected_y_sun(gt_db, sfu, f_hz):
    """The Y (dB) a station of G/T gt_db should read on the Sun: for checking a result."""
    lam = C_M_S / f_hz
    y1 = 10 ** (gt_db / 10.0) * sfu * SFU * lam * lam / (8 * math.pi * K_BOLTZMANN)
    return 10 * math.log10(1 + y1)


def fit_scan(x, db, slope=False):
    """SUN SCAN: noise (dB, any reference) at pointing offsets x (degrees, reported rotor position minus the Sun)
    -> the beam fitted as a Gaussian on a flat baseline, in linear power: P = B + A exp(-4 ln2 (x - x0)^2 / w^2).
    slope: the baseline B + C x (the elevation: the lower the antenna, the more of the warm ground the beam sees).
    {ok, x0 (the pointing error: the rotor reads this much too high), sigma (1-sigma of x0), width (-3 dB), peak_db
    (Y at the top), why (when not ok)}."""
    x = np.asarray(x, float)
    p = 10 ** (np.asarray(db, float) / 10.0)
    if len(x) < 6 or len(x) != len(p):
        return {"ok": False, "why": "too few points"}
    p = p / np.min(p)
    lo, hi = float(np.min(x)), float(np.max(x))
    span = hi - lo
    x0s = np.arange(lo, hi + 1e-9, 0.1)
    ws = np.arange(max(2.0, span / 20), span * 2.5, 0.25)
    best = (np.inf, None)
    prof = np.full(len(x0s), np.inf)
    ones = np.ones_like(x)
    for j, w in enumerate(ws):
        g = np.exp(-4 * math.log(2) * (x[None, :] - x0s[:, None]) ** 2 / (w * w))     # (x0, points)
        if slope:
            # least squares of p = B + C x + A g for every x0 at once (3 × 3 normal equations each)
            xs = (x - x.mean()) / max(span, 1e-9)
            cols = np.stack((np.broadcast_to(ones, g.shape), np.broadcast_to(xs, g.shape), g), axis=2)   # (x0, points, 3)
            m = np.einsum("kpi,kpj->kij", cols, cols)
            v = np.einsum("kpi,p->ki", cols, p)
            try:
                sol = np.linalg.solve(m, v[:, :, None])[:, :, 0]
            except np.linalg.LinAlgError:
                continue
            bline = sol[:, 0:1] + sol[:, 1:2] * xs[None, :]
            a = sol[:, 2]
            r = p[None, :] - bline - a[:, None] * g
            b = sol[:, 0] + sol[:, 1] * (x0s - x.mean()) / max(span, 1e-9)      # the baseline under the peak
        else:
            # least squares of p = B + A g for every x0 at once
            sg, sgg, sp, sgp, n = g.sum(1), (g * g).sum(1), p.sum(), (g * p).sum(1), len(x)
            det = n * sgg - sg * sg
            with np.errstate(divide="ignore", invalid="ignore"):
                a = (n * sgp - sg * sp) / det
                b = (sp - a * sg) / n
            r = p[None, :] - b[:, None] * ones[None, :] - a[:, None] * g
        sse = (r * r).sum(1)
        sse = np.where((a > 0) & (b > 0) & np.isfinite(sse), sse, np.inf)
        prof = np.minimum(prof, sse)
        k = int(np.argmin(sse))
        if sse[k] < best[0]:
            best = (float(sse[k]), (float(x0s[k]), float(w), float(a[k]), float(b[k])))
    if best[1] is None:
        return {"ok": False, "why": "no peak found"}
    sse_min, (x0, w, a, b) = best
    dof = max(1, len(x) - (5 if slope else 4))
    within = x0s[prof <= sse_min * (1 + 1.0 / dof)]
    sigma = max(0.05, (float(within.max()) - float(within.min())) / 2) if len(within) else span
    peak_db = 10 * math.log10((a + b) / b) if b > 0 else 0.0
    rms = math.sqrt(sse_min / len(x))
    out = {"ok": True, "x0": round(x0, 2), "sigma": round(sigma, 2), "width": round(w, 1), "peak_db": round(peak_db, 2),
           "base": b, "amp": a, "rms_db": round(10 * math.log10(1 + rms / b), 3) if b > 0 else None}
    edge = 0.15 * span
    if peak_db < 0.15:
        out.update(ok=False, why="the Sun is not seen in the scan (peak under 0.15 dB)")
    elif x0 < lo + edge or x0 > hi - edge:
        out.update(ok=False, why="the peak is at the edge of the scan: scan wider or POINT and peak first")
    elif w > span * 1.5:
        out.update(ok=False, why="the beam is wider than the scan: scan wider")
    return out


def info(f_hz, y_db=None, sfu=None, now=None):
    """Positions of the Sun and the Moon now, the flux at f_hz and, with y_db, the G/T from both."""
    import moon
    import sattrack
    import spacewx
    now = time.time() if now is None else now
    setup = sattrack.load_setup()
    t = np.array([now])
    out = {"t": now, "f_hz": f_hz, "located": not (setup.get("lat", 0) == 0 and setup.get("lon", 0) == 0)}
    for key, sat in ((SUN_ID, SunSat()), ("moon", moon.MoonSat())):
        lk = sattrack.look(sat, t, setup)
        out[key] = {"az": round(float(lk["az"][0]), 2), "el": round(float(lk["el"][0]), 2), "range_km": round(float(lk["range"][0]))}
    f107 = None
    try:
        spacewx._ensure(wait_s=5.0)      # the feeds from data/spacewx, downloaded again when stale
        with spacewx._lock:
            f = spacewx._f107()
        f107 = f and f.get("sfi")
    except Exception:  # noqa: BLE001 - no space weather yet: the minimum flux
        f107 = None
    out["f107"] = f107
    out["sfu_est"] = round(sun_flux_sfu(f_hz / 1e6, f107), 1)
    use = float(sfu) if sfu else out["sfu_est"]
    out["sfu"] = use
    out["moon_t_k"] = MOON_TEMP_K
    if y_db is not None:
        g = gt_sun(y_db, use, f_hz)
        out["gt_sun"] = None if g is None else round(g, 1)
        m = gt_moon(y_db, out["moon"]["range_km"])
        out["gt_moon"] = None if m is None else round(m, 1)
    return out


def register(app):
    from flask import jsonify, request

    @app.route("/api/sunnoise/fit", methods=["POST"])
    def api_sunnoise_fit():
        """SUN SCAN: {"x": [offsets °], "db": [noise dB], "slope": baseline with a slope (elevation)} -> the fitted
        beam: pointing error, its sigma, width, peak."""
        body = request.get_json(force=True) or {}
        try:
            x = [float(v) for v in body["x"]]
            db = [float(v) for v in body["db"]]
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "x and db must be lists of numbers"}), 400
        return jsonify(fit_scan(x, db, bool(body.get("slope"))))

    @app.route("/api/sunnoise")
    def api_sunnoise():
        """SUN NOISE: ?f=Hz [&y=dB] [&sfu=measured flux] -> positions of the Sun and Moon, flux, G/T (sunnoise.py)."""
        try:
            f = float(request.args.get("f", 144e6))
            y = request.args.get("y")
            y = float(y) if y not in (None, "") else None
            s = request.args.get("sfu")
            s = float(s) if s not in (None, "") else None
        except ValueError:
            return jsonify({"error": "f, y and sfu must be numbers"}), 400
        if not 1e6 <= f <= 100e9:
            return jsonify({"error": "f out of range"}), 400
        try:
            return jsonify(info(f, y, s))
        except ImportError as e:
            return jsonify({"error": f"satellite tracking is not available: {e}"}), 503

"""countries.json for SETTINGS › SDR SOURCES › DIRECTORY (sources.country_of): the outer borders of the countries of
Natural Earth 1:50m admin 0 (public domain), Douglas-Peucker simplified, in 1/20 degree.

  python installer/make_countries.py ne_50m_admin_0_countries.geojson countries.json
  (https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson)
"""
import json, sys
src, dst = sys.argv[1], sys.argv[2]
EPS = 0.06      # degrees, Douglas-Peucker
Q = 20          # stored in 1/20 degree

def rdp(pts, eps):
    if len(pts) < 3: return pts
    keep = [False] * len(pts); keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]; bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        n = (dx * dx + dy * dy) ** .5
        best, bi = 0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / n if n else ((px - ax) ** 2 + (py - ay) ** 2) ** .5
            if d > best: best, bi = d, i
        if best > eps:
            keep[bi] = True; stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]

d = json.load(open(src, encoding="utf-8"))
out = []
for f in d["features"]:
    p = f["properties"]
    iso = (p.get("ISO_A2_EH") or p.get("ISO_A2") or "").lower()
    if iso == "-99": iso = ""
    name = p.get("NAME") or p.get("ADMIN")
    g = f["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    rings = []
    for poly in polys:
        r = rdp(poly[0], EPS)
        flat, last = [], None
        for lon, lat in r:
            q = (round(lon * Q), round(lat * Q))
            if q != last: flat += q; last = q
        if len(flat) >= 6: rings.append(flat)
        elif poly[0]:     # a tiny island: keep it as a small box around its first point
            lon, lat = poly[0][0]; x, y = round(lon * Q), round(lat * Q)
            rings.append([x - 1, y - 1, x + 1, y - 1, x + 1, y + 1, x - 1, y + 1])
    if rings: out.append([iso, name, rings])
json.dump({"q": Q, "source": "Natural Earth 1:50m admin 0 countries (public domain, https://www.naturalearthdata.com/), outer rings simplified",
           "countries": out}, open(dst, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
print(len(out))

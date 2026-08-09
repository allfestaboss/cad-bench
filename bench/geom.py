"""spec から図面の正解幾何を一意に導く。作図者の癖を一切入れない。

壁 = 芯を ±t/2 で膨らませて union した領域。
描くべき線 = (その領域 − 開口) の境界。
  T字接合のトリムも、開口の小口(ジャンブ)も、この定義から自動的に出てくる。
斜め壁でも同じ定義がそのまま効く。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from shapely.geometry import LinearRing, LineString, Polygon, box
from shapely.ops import linemerge, unary_union

TOL = 1.0  # mm


def load_spec(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def wall_of(spec, wid):
    return next(w for w in spec["walls"] if w["id"] == wid)


def wall_vec(w):
    (x0, y0), (x1, y1) = w["from"], w["to"]
    L = math.hypot(x1 - x0, y1 - y0)
    return (x1 - x0) / L, (y1 - y0) / L, L


def point_at(w, t):
    """壁の始点から距離 t の点。"""
    ux, uy, _ = wall_vec(w)
    return (w["from"][0] + ux * t, w["from"][1] + uy * t)


def faces_of(spec, w):
    """壁の左右の面までの距離 (左, 右)。左＝進行方向に対して +90度側。

    `faces: [dl, dr]` で個別指定できる。無ければ `thickness`（無ければ全体の
    `wall_thickness`）を芯振り分けにする。**面芯の壁は faces:[0,120] のように書く。**
    """
    if "faces" in w:
        return float(w["faces"][0]), float(w["faces"][1])
    t = float(w.get("thickness", spec["wall_thickness"]))
    return t / 2.0, t / 2.0


def thick_of(spec, w):
    a, b = faces_of(spec, w)
    return a + b


def _unit(p, q):
    L = math.hypot(q[0] - p[0], q[1] - p[1])
    return (q[0] - p[0]) / L, (q[1] - p[1]) / L, L


def opening_rect(spec, o, pad=0.5):
    """開口が壁を貫く矩形（壁厚方向に pad だけ余分）。斜めでも面芯でも正しい。"""
    w = wall_of(spec, o["wall"])
    ux, uy, _ = wall_vec(w)
    nx, ny = -uy, ux
    hl, hr = faces_of(spec, w)
    hl, hr = hl + pad, hr + pad
    a, b = point_at(w, o["t0"]), point_at(w, o["t1"])
    return Polygon([(a[0] + nx * hl, a[1] + ny * hl), (b[0] + nx * hl, b[1] + ny * hl),
                    (b[0] - nx * hr, b[1] - ny * hr), (a[0] - nx * hr, a[1] - ny * hr)])


def _rect(w, hl, hr):
    (x0, y0), (x1, y1) = tuple(w["from"]), tuple(w["to"])
    ux, uy, _ = _unit((x0, y0), (x1, y1))
    nx, ny = -uy, ux
    return Polygon([(x0 + nx * hl, y0 + ny * hl), (x1 + nx * hl, y1 + ny * hl),
                    (x1 - nx * hr, y1 - ny * hr), (x0 - nx * hr, y0 - ny * hr)])


def _cross(a, b, c, d):
    """直線 ab と cd の交点。平行なら None。"""
    x1, y1 = a; x2, y2 = b; x3, y3 = c; x4, y4 = d
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-9:
        return None
    p = x1 * y2 - y1 * x2
    q = x3 * y4 - y3 * x4
    return ((p * (x3 - x4) - (x1 - x2) * q) / den, (p * (y3 - y4) - (y1 - y2) * q) / den)


def _ring_seq(walls):
    """外壁を端点で連結して閉ループ順に並べる。反転した壁は左右の面を入れ替える。"""
    if not walls:
        return None
    rem = [dict(w) for w in walls]
    seq = [rem.pop(0)]
    while rem:
        end = tuple(seq[-1]["to"])
        for i, w in enumerate(rem):
            if tuple(w["from"]) == end:
                seq.append(rem.pop(i))
                break
            if tuple(w["to"]) == end:
                v = rem.pop(i)
                v["from"], v["to"] = v["to"], v["from"]
                if "faces" in v:
                    v["faces"] = [v["faces"][1], v["faces"][0]]
                seq.append(v)
                break
        else:
            return None
    return seq if tuple(seq[-1]["to"]) == tuple(seq[0]["from"]) else None


def _offset_ring(spec, seq, outward):
    """各辺を自分の面距離だけずらし、隣接辺の交点で結んだ多角形。

    辺ごとに距離が違ってよいので、shapely の buffer では作れない。
    厚さの違う壁が角で出会うと、外面と内面のマイター点が別々の位置に出る。
    """
    ccw = LinearRing([tuple(w["from"]) for w in seq]).is_ccw
    lines = []
    for w in seq:
        hl, hr = faces_of(spec, w)
        ux, uy, _ = _unit(tuple(w["from"]), tuple(w["to"]))
        nx, ny = -uy, ux
        # CCW なら左法線が内向き。外側の面までの距離は右の hr。
        out_side = (not ccw)
        d = (hl if out_side else -hr) if outward else (-hr if out_side else hl)
        lines.append(((w["from"][0] + nx * d, w["from"][1] + ny * d),
                      (w["to"][0] + nx * d, w["to"][1] + ny * d)))
    pts = []
    for i in range(len(lines)):
        p = _cross(*lines[i - 1], *lines[i])
        pts.append(p if p is not None else lines[i][0])
    return Polygon(pts)


def wall_solid(spec):
    """壁の実体。

    外壁は**閉じたリングとして**扱い、外面リングと内面リングを別々に作って差し引く。
    辺ごとに面までの距離が違ってよいので、隣接する offset 直線の交点でマイターする。
    1本ずつ膨らませて union すると隅に切り欠きが残り、まとめて buffer すると
    厚さを壁ごとに変えられない。

    内壁は平口の矩形として union する。内壁の端部は必ず他の壁の実体の内側にある。
    """
    ext = [w for w in spec["walls"] if w["kind"] == "exterior"]
    inn = [w for w in spec["walls"] if w["kind"] != "exterior"]

    seq = _ring_seq(ext)
    if seq is not None:
        solid = _offset_ring(spec, seq, True).difference(_offset_ring(spec, seq, False))
    else:   # 外周が閉じないタスクへの安全側フォールバック
        solid = unary_union([_rect(w, *faces_of(spec, w)) for w in ext]) if ext else Polygon()
    if inn:
        solid = unary_union([solid] + [_rect(w, *faces_of(spec, w)) for w in inn])
    return solid


def boundary(spec):
    """(境界全体, 壁面, 小口) を返す。"""
    poly = wall_solid(spec).difference(unary_union([opening_rect(spec, o) for o in spec["openings"]]))
    bnd = poly.boundary
    holes = unary_union([opening_rect(spec, o, pad=0.0) for o in spec["openings"]]).buffer(0.01)
    return bnd, bnd.difference(holes), bnd.intersection(holes)


def wall_rings(spec):
    """参照解を描くための閉リング列。"""
    poly = wall_solid(spec).difference(unary_union([opening_rect(spec, o) for o in spec["openings"]]))
    geoms = [poly] if poly.geom_type == "Polygon" else list(poly.geoms)
    out = []
    for g in geoms:
        for ring in [g.exterior] + list(g.interiors):
            out.append([(round(x, 3), round(y, 3)) for x, y in ring.coords[:-1]])
    return out


def room_poly(r):
    return Polygon(r["poly"]) if "poly" in r else box(r["x0"], r["y0"], r["x1"], r["y1"])


def on_wall_face(spec, a, b):
    """線分 a-b が、いずれかの壁芯に平行でその壁の面の距離に乗っているか。

    壁ごとに厚さも振り分けも違ってよいので、左右それぞれの距離と照合する。
    """
    seg = LineString([a, b])
    for w in spec["walls"]:
        ux, uy, _ = wall_vec(w)
        sx, sy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(sx, sy)
        if L < TOL:
            continue
        if abs((sx / L) * uy - (sy / L) * ux) > 1e-3:   # 平行でない
            continue
        cl = LineString([tuple(w["from"]), tuple(w["to"])])
        d0, d1 = cl.distance(seg.interpolate(0.25, True)), cl.distance(seg.interpolate(0.75, True))
        for h in faces_of(spec, w):
            if abs(d0 - h) < TOL and abs(d1 - h) < TOL:
                return True
    return False

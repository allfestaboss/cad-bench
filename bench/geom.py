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

from shapely.geometry import LineString, Polygon, box
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


def opening_rect(spec, o, pad=0.5):
    """開口が壁を貫く矩形（壁厚方向に pad だけ余分）。斜め壁でも正しい。"""
    w = wall_of(spec, o["wall"])
    ux, uy, _ = wall_vec(w)
    nx, ny = -uy, ux
    h = spec["wall_thickness"] / 2.0 + pad
    a, b = point_at(w, o["t0"]), point_at(w, o["t1"])
    return Polygon([(a[0] + nx * h, a[1] + ny * h), (b[0] + nx * h, b[1] + ny * h),
                    (b[0] - nx * h, b[1] - ny * h), (a[0] - nx * h, a[1] - ny * h)])


def wall_solid(spec):
    """壁の実体。

    外壁は**閉じたリングとして一括で**膨らませる。端部が無いので全ての隅がマイター
    結合され、直角も135度も正しく出る。1本ずつ膨らませて union すると斜めの隅に
    角スパイクが出るし、線群をまとめて buffer すると直角がベベルになる。

    内壁は平口(flat)で個別に膨らませて union する。内壁の端部は必ず他の壁の実体の
    内側にあるので、平口で問題ない。
    """
    h = spec["wall_thickness"] / 2.0
    ext = [LineString([tuple(w["from"]), tuple(w["to"])]) for w in spec["walls"] if w["kind"] == "exterior"]
    inn = [LineString([tuple(w["from"]), tuple(w["to"])]) for w in spec["walls"] if w["kind"] != "exterior"]

    merged = linemerge(ext) if ext else None
    if merged is not None and merged.geom_type == "LineString" and merged.is_ring:
        solid = merged.buffer(h, join_style=2, mitre_limit=10)
    else:   # 外周が閉じないタスクへの安全側フォールバック
        solid = unary_union([g.buffer(h, cap_style=3, join_style=2) for g in ext])
    if inn:
        solid = unary_union([solid] + [g.buffer(h, cap_style=2, join_style=2, mitre_limit=10) for g in inn])
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
    """線分 a-b が、いずれかの壁芯に平行で距離 t/2 か。斜め壁でも効く。"""
    h = spec["wall_thickness"] / 2.0
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
        if abs(d0 - h) < TOL and abs(d1 - h) < TOL:
            return True
    return False

#!/usr/bin/env python3
"""汎用 参照解ビルダー。spec.json から機械的に「正解図面」を組む。
ここに知能は無い。採点器の較正と、決定論ジェネレータの天井の提示が目的。

使い方: build_ref.py <spec.json> <out.dxf>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import ezdxf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geom import load_spec, point_at, room_poly, wall_of, wall_rings, wall_vec  # noqa: E402
from resolve import resolve  # noqa: E402
from solve_code import solve_schedule  # noqa: E402

COLORS = {"GRID": 1, "WALL": 7, "OPENING": 4, "DIM": 3, "ROOM": 2, "TEXT": 7, "STAIR": 6}

raw = load_spec(sys.argv[1])
OUT = Path(sys.argv[2])
# 第3引数で建具表を差し替えられる（違反例の生成用）
if len(sys.argv) > 3:
    SCHED = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
else:
    SCHED = solve_schedule(raw) if raw.get("code") else {}
if SCHED:
    Path(str(OUT).rsplit(".", 1)[0] + ".schedule.json").write_text(
        json.dumps(SCHED, ensure_ascii=False, indent=2), encoding="utf-8")
spec = resolve(raw, SCHED)
S = float(str(spec["scale"]).split(":")[1])
H = spec["wall_thickness"] / 2.0

doc = ezdxf.new("R2010", setup=True)
doc.header["$INSUNITS"] = 4
doc.header["$LTSCALE"] = 50
msp = doc.modelspace()

for name in spec["layers"]["required"]:
    doc.layers.add(name, color=COLORS.get(name, 7),
                   linetype="CENTER" if name == "GRID" else "CONTINUOUS")

# 実寸mmを 1:S で刷る前提。文字・矢印はモデル空間で S 倍しないと紙面で読めない。
DS = "JP"
ds = doc.dimstyles.add(DS)
ds.dxf.dimtxt, ds.dxf.dimasz, ds.dxf.dimexe = 0.025 * S * 100, 0.015 * S * 100, 0.01 * S * 100
ds.dxf.dimexo, ds.dxf.dimgap, ds.dxf.dimdec = 0.008 * S * 100, 0.006 * S * 100, 0
ds.dxf.dimblk, ds.dxf.dimtad = "ARCHTICK", 1


def line(a, b, layer):
    msp.add_line(a, b, dxfattribs={"layer": layer})


def text(s, at, h, layer):
    msp.add_text(s, dxfattribs={"layer": layer, "height": h}).set_placement(at)


# ---- 通り芯 + 符号（丸囲み）
GX, GY = spec["grid"]["x"], spec["grid"]["y"]
x0, x1 = min(GX["coords"]), max(GX["coords"])
y0, y1 = min(GY["coords"]), max(GY["coords"])
R = 0.026 * S * 100
for x, lab in zip(GX["coords"], GX["labels"]):
    line((x, y0 - 1000), (x, y1 + 1000), "GRID")
    msp.add_circle((x, y0 - 1000 - R), R, dxfattribs={"layer": "GRID"})
    text(lab, (x - R * 0.55, y0 - 1000 - R * 1.5), R * 0.9, "GRID")
for y, lab in zip(GY["coords"], GY["labels"]):
    line((x0 - 1000, y), (x1 + 1000, y), "GRID")
    msp.add_circle((x0 - 1000 - R, y), R, dxfattribs={"layer": "GRID"})
    text(lab, (x0 - 1000 - R * 1.55, y - R * 0.45), R * 0.9, "GRID")

# ---- 壁（実体の境界）
for ring in wall_rings(spec):
    msp.add_lwpolyline(ring, close=True, dxfattribs={"layer": "WALL"})

# ---- 建具（小口は壁境界に含まれる）
for o in spec["openings"]:
    w = wall_of(spec, o["wall"])
    ux, uy, _ = wall_vec(w)
    nx, ny = -uy, ux
    a, b = point_at(w, o["t0"]), point_at(w, o["t1"])
    width = o["t1"] - o["t0"]
    if o["type"] == "window":
        for k in (-0.5, 0.5):     # ガラス2本線
            line((a[0] + nx * H * k, a[1] + ny * H * k), (b[0] + nx * H * k, b[1] + ny * H * k), "OPENING")
    else:
        line(a, (a[0] + nx * width, a[1] + ny * width), "OPENING")   # 戸
        ang = __import__("math").degrees(__import__("math").atan2(uy, ux))
        msp.add_arc(a, width, ang, ang + 90, dxfattribs={"layer": "OPENING"})

# ---- 室名（＋ annotations があれば面積も）
#  収納のような薄い室（奥行455mm＝紙上4.55mm）には2行入らない。室内に収まる位置へ寄せる。
ann = spec.get("annotations", {})


def inside(poly, cand, fallback):
    from shapely.geometry import Point as _P
    return cand if poly.contains(_P(cand)) else fallback


for rm in spec["rooms"]:
    poly = room_poly(rm)
    c = poly.representative_point()
    base = (c.x, c.y)
    text(rm["name"], inside(poly, (c.x - len(rm["name"]) * 0.011 * S * 100, c.y + 0.008 * S * 100), base),
         0.030 * S * 100, "ROOM")
    if "room_area" in ann:
        d_ = ann["room_area"]["decimals"]
        cand = (c.x - 0.030 * S * 100, c.y - 0.045 * S * 100)          # 名前の下
        alt = (c.x + 0.022 * S * 100, c.y - 0.008 * S * 100)           # 薄い室では名前の右
        text(f"{rm['area_m2']:.{d_}f}", inside(poly, cand, inside(poly, alt, base)),
             0.024 * S * 100, ann["room_area"]["layer"])

if "total_area" in ann:
    d_ = ann["total_area"]["decimals"]
    text(f"床面積 {spec['_total_area_m2']:.{d_}f} m2", (0, max(GY['coords']) + 1400),
         0.030 * S * 100, ann["total_area"]["layer"])

if "opening_marks" in ann:
    from geom import point_at as _pa, wall_of as _wo, wall_vec as _wv
    for o in spec["openings"]:
        mark = ann["opening_marks"]["map"].get(o["id"])
        if not mark:
            continue
        w = _wo(spec, o["wall"])
        ux, uy, _ = _wv(w)
        nx, ny = -uy, ux
        m = _pa(w, (o["t0"] + o["t1"]) / 2.0)
        text(mark, (m[0] + nx * 300, m[1] + ny * 300), 0.022 * S * 100, ann["opening_marks"]["layer"])

# ---- 階段（spec に座標がある課題／建具表から決まる課題の両方に対応）
_st = spec.get("stairs") or SCHED.get("stairs")
if _st and _st.get("treads"):
    lay = spec.get("stair_layer", _st.get("layer", "STAIR"))
    for t in _st["treads"]:
        line(tuple(t[0]), tuple(t[1]), lay)
    if _st.get("up_text_at"):
        text("UP", tuple(_st["up_text_at"]), 0.025 * S * 100, lay)

# ---- 寸法（本物の DIMENSION）
for c in spec["dimensions"]["chains"]:
    st, at, base, obase = c["stations"], c["at"], c["base"], c.get("overall_base")
    for p, q in zip(st[:-1], st[1:]):
        if c["direction"] == "x":
            d = msp.add_linear_dim(base=(0, base), p1=(p, at), p2=(q, at), dimstyle=DS,
                                   dxfattribs={"layer": "DIM"})
        else:
            d = msp.add_linear_dim(base=(base, 0), p1=(at, p), p2=(at, q), angle=90, dimstyle=DS,
                                   dxfattribs={"layer": "DIM"})
        d.render()
    if c.get("overall") is None:
        continue
    if c["direction"] == "x":
        d = msp.add_linear_dim(base=(0, obase), p1=(st[0], at), p2=(st[-1], at), dimstyle=DS,
                               dxfattribs={"layer": "DIM"})
    else:
        d = msp.add_linear_dim(base=(obase, 0), p1=(at, st[0]), p2=(at, st[-1]), angle=90, dimstyle=DS,
                               dxfattribs={"layer": "DIM"})
    d.render()

OUT.parent.mkdir(parents=True, exist_ok=True)
doc.saveas(OUT)
print(f"wrote {OUT}", file=sys.stderr)

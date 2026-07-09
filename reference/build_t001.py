#!/usr/bin/env python3
"""T001 の参照解（決定論ジェネレータ）。採点器の較正用。
spec.json から機械的に図面を組み立てる。ここに「知能」は無い。"""
import json
import sys
from pathlib import Path

import ezdxf

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "tasks" / "T001" / "spec.json").read_text())
OUT = ROOT / "reference" / "reference_t001.dxf"

H = SPEC["wall_thickness"] / 2.0
GX, GY = SPEC["grid"]["x"]["coords"], SPEC["grid"]["y"]["coords"]
LX, LY = SPEC["grid"]["x"]["labels"], SPEC["grid"]["y"]["labels"]
X0, Y0, X1, Y1 = (SPEC["footprint"][k] for k in ("x0", "y0", "x1", "y1"))

doc = ezdxf.new("R2010", setup=True)
doc.header["$INSUNITS"] = 4  # mm
doc.header["$LTSCALE"] = 50
msp = doc.modelspace()

# 実寸mmの図面を 1:100 で刷る前提。寸法の文字・矢印は図面上 1.5〜2.5mm 相当が
# 見えるよう、モデル空間では 100 倍しておく。これを怠ると値は正しいのに読めない。
DIMSTYLE = "JP100"
ds = doc.dimstyles.add(DIMSTYLE)
ds.dxf.dimtxt = 250    # 寸法文字高
ds.dxf.dimasz = 150    # 矢印(建築なので後で斜線に)
ds.dxf.dimexe = 100    # 補助線の突出
ds.dxf.dimexo = 80     # 補助線の逃げ
ds.dxf.dimgap = 60
ds.dxf.dimdec = 0      # 整数mm表記
ds.dxf.dimblk = "ARCHTICK"
ds.dxf.dimtad = 1      # 寸法線の上に文字

for name, color, lt in [("GRID", 1, "CENTER"), ("WALL", 7, "CONTINUOUS"),
                        ("OPENING", 4, "CONTINUOUS"), ("DIM", 3, "CONTINUOUS"),
                        ("ROOM", 2, "CONTINUOUS"), ("TEXT", 7, "CONTINUOUS")]:
    doc.layers.add(name, color=color, linetype=lt)


def line(a, b, layer):
    msp.add_line(a, b, dxfattribs={"layer": layer})


def cut(lo, hi, holes):
    segs = [(lo, hi)]
    for h0, h1 in holes:
        out = []
        for a, b in segs:
            if h1 <= a or h0 >= b:
                out.append((a, b)); continue
            if a < h0: out.append((a, h0))
            if h1 < b: out.append((h1, b))
        segs = out
    return [(a, b) for a, b in segs if b - a > 1.0]


def holes(wall_id):
    return [(o["start"], o["end"]) for o in SPEC["openings"] if o["wall"] == wall_id]


# ---- 通り芯
for x, lab in zip(GX, LX):
    line((x, Y0 - 1000), (x, Y1 + 1000), "GRID")
    msp.add_text(lab, dxfattribs={"layer": "GRID", "height": 150}).set_placement((x - 60, Y0 - 1250))
for y, lab in zip(GY, LY):
    line((X0 - 1000, y), (X1 + 1000, y), "GRID")
    msp.add_text(lab, dxfattribs={"layer": "GRID", "height": 150}).set_placement((X0 - 1250, y - 60))

# ---- 壁: 芯を±60で膨らませて union し、開口を差し引いた領域の「境界」を描く。
#      T字接合のトリムも開口の小口も、この一手で自動的に正しくなる。
from shapely.geometry import LineString as _LS, box as _box
from shapely.ops import unary_union as _uu

solid = _uu([_LS([tuple(w["from"]), tuple(w["to"])]).buffer(H, cap_style=3, join_style=2)
             for w in SPEC["walls"]])
cuts = []
for o in SPEC["openings"]:
    w = next(x for x in SPEC["walls"] if x["id"] == o["wall"])
    if o["axis"] == "x":
        c = w["from"][1]; cuts.append(_box(o["start"], c - H - 0.5, o["end"], c + H + 0.5))
    else:
        c = w["from"][0]; cuts.append(_box(c - H - 0.5, o["start"], c + H + 0.5, o["end"]))
poly = solid.difference(_uu(cuts))

for ring in ([poly.exterior] + list(poly.interiors)) if poly.geom_type == "Polygon" else \
            [r for g in poly.geoms for r in [g.exterior] + list(g.interiors)]:
    pts = [(round(x, 3), round(y, 3)) for x, y in ring.coords[:-1]]
    msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "WALL"})

# ---- 建具（小口は壁境界に含まれるので、ここでは開き勝手・ガラス線のみ）
for o in SPEC["openings"]:
    w = next(x for x in SPEC["walls"] if x["id"] == o["wall"])
    s, e = o["start"], o["end"]
    if o["axis"] == "x":
        c = w["from"][1]
        if o["type"] == "window":
            line((s, c), (e, c), "OPENING")
        else:
            line((s, c), (s, c + (e - s)), "OPENING")
            msp.add_arc((s, c), e - s, 0, 90, dxfattribs={"layer": "OPENING"})
    else:
        c = w["from"][0]
        if o["type"] == "window":
            line((c, s), (c, e), "OPENING")
        else:
            line((c, s), (c + (e - s), s), "OPENING")
            msp.add_arc((c, s), e - s, 0, 90, dxfattribs={"layer": "OPENING"})

# ---- 室名
for r in SPEC["rooms"]:
    cx, cy = (r["x0"] + r["x1"]) / 2, (r["y0"] + r["y1"]) / 2
    msp.add_text(r["name"], dxfattribs={"layer": "ROOM", "height": 200}).set_placement((cx - 300, cy))

# ---- 寸法（本物の DIMENSION）
def chain(stations, overall, along, base1, base2):
    for a, b in zip(stations[:-1], stations[1:]):
        if along == "x":
            d = msp.add_linear_dim(base=(0, base1), p1=(a, Y0), p2=(b, Y0), dimstyle=DIMSTYLE, dxfattribs={"layer": "DIM"})
        else:
            d = msp.add_linear_dim(base=(base1, 0), p1=(X0, a), p2=(X0, b), angle=90, dimstyle=DIMSTYLE, dxfattribs={"layer": "DIM"})
        d.render()
    if along == "x":
        d = msp.add_linear_dim(base=(0, base2), p1=(stations[0], Y0), p2=(stations[-1], Y0), dimstyle=DIMSTYLE, dxfattribs={"layer": "DIM"})
    else:
        d = msp.add_linear_dim(base=(base2, 0), p1=(X0, stations[0]), p2=(X0, stations[-1]), angle=90, dimstyle=DIMSTYLE, dxfattribs={"layer": "DIM"})
    d.render()


for c in SPEC["dimensions"]["chains"]:
    if c["along"] == "x":
        chain(c["stations"], c["overall"], "x", Y0 - 600, Y0 - 1600)
    else:
        chain(c["stations"], c["overall"], "y", X0 - 600, X0 - 1600)

OUT.parent.mkdir(parents=True, exist_ok=True)
doc.saveas(OUT)
print(f"wrote {OUT}", file=sys.stderr)

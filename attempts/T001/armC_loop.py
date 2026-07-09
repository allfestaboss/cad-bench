#!/usr/bin/env python
"""
T001 木造平屋 1階平面図 (armC: 検証ループ許可)
仕様: tasks/T001/spec.json
- 単位 mm, 1:100, 原点=南西通り芯交点, X=東, Y=北
- 壁厚120 芯振り分け(±60), 通り芯/壁両面線/開口4/寸法DIMENSION/室名/通り芯符号
"""
import json
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment
from shapely.geometry import LineString, box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
SPEC = json.loads((HERE.parent.parent / "tasks" / "T001" / "spec.json").read_text())
OUT = HERE / "armC_loop.dxf"

HALF = SPEC["wall_thickness"] / 2.0  # 60

# ---------------------------------------------------------------- doc / layers
doc = ezdxf.new("R2010", setup=True)
doc.header["$INSUNITS"] = 4  # millimeters
doc.header["$LTSCALE"] = 25
msp = doc.modelspace()

# Japanese-capable text style
JP_FONT = "Arial Unicode.ttf"
doc.styles.add("JP", font=JP_FONT)

LAYERS = {
    "GRID":    {"color": 1, "linetype": "CENTER", "lineweight": 13},
    "WALL":    {"color": 7, "linetype": "CONTINUOUS", "lineweight": 50},
    "OPENING": {"color": 3, "linetype": "CONTINUOUS", "lineweight": 25},
    "DIM":     {"color": 4, "linetype": "CONTINUOUS", "lineweight": 18},
    "ROOM":    {"color": 5, "linetype": "CONTINUOUS", "lineweight": 18},
    "TEXT":    {"color": 6, "linetype": "CONTINUOUS", "lineweight": 18},
}
for name, a in LAYERS.items():
    lay = doc.layers.add(name)
    lay.color = a["color"]
    lay.dxf.linetype = a["linetype"]
    lay.dxf.lineweight = a["lineweight"]

# ---------------------------------------------------------------- dim style
dimstyle = doc.dimstyles.duplicate_entry("EZDXF", "ARCH")
dimstyle.dxf.dimtxt = 300      # text height (3mm @1:100)
dimstyle.dxf.dimasz = 200      # arrow / tick size
dimstyle.dxf.dimtsz = 120      # >0 -> architectural ticks instead of arrows
dimstyle.dxf.dimexe = 150      # ext line beyond dim line
dimstyle.dxf.dimexo = 200      # ext line offset from origin
dimstyle.dxf.dimgap = 90       # gap around text
dimstyle.dxf.dimdec = 0        # integer mm
dimstyle.dxf.dimlfac = 1.0     # displayed value == real mm
dimstyle.dxf.dimtad = 1        # text above dim line
dimstyle.dxf.dimscale = 1.0
dimstyle.dxf.dimtxsty = "Standard"
dimstyle.dxf.dimclrd = 4
dimstyle.dxf.dimclre = 4
dimstyle.dxf.dimclrt = 4

# ---------------------------------------------------------------- WALLS (boolean)
wall_solids = []
for w in SPEC["walls"]:
    line = LineString([tuple(w["from"]), tuple(w["to"])])
    wall_solids.append(line.buffer(HALF, cap_style=3, join_style=2))  # square cap, mitre
solid = unary_union(wall_solids)

# opening notches (cut full thickness + margin)
M = 40  # lateral over-cut beyond faces
cuts = []
for o in SPEC["openings"]:
    w = next(x for x in SPEC["walls"] if x["id"] == o["wall"])
    if o["axis"] == "x":            # opening runs along X (horizontal wall)
        wy = w["from"][1]
        cuts.append(box(o["start"], wy - HALF - M, o["end"], wy + HALF + M))
    else:                           # opening runs along Y (vertical wall)
        wx = w["from"][0]
        cuts.append(box(wx - HALF - M, o["start"], wx + HALF + M, o["end"]))
solid = solid.difference(unary_union(cuts))

def draw_polygon(poly):
    rings = [poly.exterior] + list(poly.interiors)
    for ring in rings:
        pts = list(ring.coords)[:-1]  # drop closing dup
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "WALL"})

geoms = getattr(solid, "geoms", [solid])
for g in geoms:
    draw_polygon(g)

# ---------------------------------------------------------------- OPENINGS layer
def line(p1, p2, layer):
    msp.add_line(p1, p2, dxfattribs={"layer": layer})

def arc(center, radius, a0, a1, layer):
    msp.add_arc(center, radius, a0, a1, dxfattribs={"layer": layer})

for o in SPEC["openings"]:
    w = next(x for x in SPEC["walls"] if x["id"] == o["wall"])
    if o["axis"] == "x":
        wy = w["from"][1]; s, e = o["start"], o["end"]
        if o["type"] == "window":
            # frame faces + centre glass line
            line((s, wy - HALF), (e, wy - HALF), "OPENING")
            line((s, wy + HALF), (e, wy + HALF), "OPENING")
            line((s, wy), (e, wy), "OPENING")
        else:  # door on horizontal wall (O1 entrance, swings into +y room)
            inner = wy + HALF
            width = e - s
            hinge = (s, inner)
            line((s, wy - HALF), (e, wy - HALF), "OPENING")  # threshold at outer face
            line(hinge, (s, inner + width), "OPENING")        # leaf
            arc(hinge, width, 0, 90, "OPENING")               # swing
    else:
        wx = w["from"][0]; s, e = o["start"], o["end"]
        if o["type"] == "window":
            line((wx - HALF, s), (wx - HALF, e), "OPENING")
            line((wx + HALF, s), (wx + HALF, e), "OPENING")
            line((wx, s), (wx, e), "OPENING")
        else:  # door on vertical wall (O4, swings into +x room = LDK)
            inner = wx + HALF
            width = e - s
            hinge = (inner, s)
            line(hinge, (inner, s + width), "OPENING")        # leaf along wall
            arc(hinge, width, 0, 90, "OPENING")               # swing into LDK

# ---------------------------------------------------------------- GRID
gx = SPEC["grid"]["x"]; gy = SPEC["grid"]["y"]
TOP = SPEC["footprint"]["y1"] + 100
RIGHT = SPEC["footprint"]["x1"] + 100
BUB = 350
X_BUB_Y = -2100
Y_BUB_X = -2100

for x, lab in zip(gx["coords"], gx["labels"]):
    line((x, TOP), (x, X_BUB_Y + BUB), "GRID")
    msp.add_circle((x, X_BUB_Y), BUB, dxfattribs={"layer": "GRID"})
    msp.add_text(lab, dxfattribs={"layer": "GRID", "height": 250, "style": "Standard"}
                 ).set_placement((x, X_BUB_Y), align=TextEntityAlignment.MIDDLE_CENTER)

for y, lab in zip(gy["coords"], gy["labels"]):
    line((RIGHT, y), (Y_BUB_X + BUB, y), "GRID")
    msp.add_circle((Y_BUB_X, y), BUB, dxfattribs={"layer": "GRID"})
    msp.add_text(lab, dxfattribs={"layer": "GRID", "height": 250, "style": "Standard"}
                 ).set_placement((Y_BUB_X, y), align=TextEntityAlignment.MIDDLE_CENTER)

# ---------------------------------------------------------------- DIMENSIONS
ds = SPEC["dimensions"]["chains"][0]  # south, along x
dw = SPEC["dimensions"]["chains"][1]  # west, along y

DIM_ATTR = {"layer": "DIM"}
# south chain
msp.add_multi_point_linear_dim(
    base=(0, -900),
    points=[(x, 0) for x in ds["stations"]],
    angle=0, dimstyle="ARCH", dxfattribs=DIM_ATTR)
# south overall
msp.add_linear_dim(base=(0, -1500), p1=(0, 0), p2=(ds["overall"], 0),
                   angle=0, dimstyle="ARCH", dxfattribs=DIM_ATTR).render()

# west chain
msp.add_multi_point_linear_dim(
    base=(-900, 0),
    points=[(0, y) for y in dw["stations"]],
    angle=90, dimstyle="ARCH", dxfattribs=DIM_ATTR)
# west overall
msp.add_linear_dim(base=(-1500, 0), p1=(0, 0), p2=(0, dw["overall"]),
                   angle=90, dimstyle="ARCH", dxfattribs=DIM_ATTR).render()

# ---------------------------------------------------------------- ROOM names
for r in SPEC["rooms"]:
    cx = (r["x0"] + r["x1"]) / 2.0
    cy = (r["y0"] + r["y1"]) / 2.0
    msp.add_text(r["name"], dxfattribs={"layer": "ROOM", "height": 350, "style": "JP"}
                 ).set_placement((cx, cy), align=TextEntityAlignment.MIDDLE_CENTER)

# ---------------------------------------------------------------- TEXT (title + opening notes)
msp.add_text("木造平屋 1階平面図　S=1:100",
             dxfattribs={"layer": "TEXT", "height": 400, "style": "JP"}
             ).set_placement((SPEC["footprint"]["x1"] / 2.0, -3100),
                             align=TextEntityAlignment.MIDDLE_CENTER)

# opening description notes on TEXT layer
notes = {
    "O1": ((910, 300), "玄関ドア"),
    "O2": ((3640, 300), "掃出窓"),
    "O3": ((5150, 2730), "窓"),
    "O4": ((1820, 1550), "内部ドア"),
}
for oid, (pos, txt) in notes.items():
    msp.add_text(txt, dxfattribs={"layer": "TEXT", "height": 180, "style": "JP"}
                 ).set_placement(pos, align=TextEntityAlignment.MIDDLE_CENTER)

# ---------------------------------------------------------------- save
doc.saveas(OUT)
print("saved", OUT)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cad-bench T001 : 木造平屋 1階平面図（作図のみ）
DXF generator using ezdxf.

Coordinate system: origin (0,0) = SW grid intersection, X=east, Y=north, unit = mm.
Wall thickness 120mm, centered on grid (each face +/-60 from the grid line).

NOTE: This script is only WRITTEN, never executed by the author (benchmark rule).
When run it writes armB_ezdxf.dxf next to this file.
"""

import os
import ezdxf
from ezdxf.enums import TextEntityAlignment  # noqa: F401  (kept for reference)

OUT = "/Users/boss/dev/01_projects/big-business/cad-bench/attempts/T001/armB_ezdxf.dxf"

# ---------------------------------------------------------------------------
# Spec constants (mirrors spec.json)
# ---------------------------------------------------------------------------
X_LABELS = ["X1", "X2", "X3", "X4", "X5", "X6", "X7"]
X_COORDS = [0, 910, 1820, 2730, 3640, 4550, 5460]
Y_LABELS = ["Y1", "Y2", "Y3", "Y4", "Y5", "Y6"]
Y_COORDS = [0, 910, 1820, 2730, 3640, 4550]

FP_X0, FP_Y0, FP_X1, FP_Y1 = 0, 0, 5460, 4550   # footprint (grid) extents
H = 60                                            # wall half thickness (120/2)

ROOMS = [
    {"name": "玄関",     "x0": 0,    "y0": 0,    "x1": 1820, "y1": 1820, "area": 3.3124},
    {"name": "便所",     "x0": 0,    "y0": 1820, "x1": 1820, "y1": 2730, "area": 1.6562},
    {"name": "洗面浴室", "x0": 0,    "y0": 2730, "x1": 1820, "y1": 4550, "area": 3.3124},
    {"name": "LDK",      "x0": 1820, "y0": 0,    "x1": 5460, "y1": 4550, "area": 16.5620},
]

# ---------------------------------------------------------------------------
# Document / units / linetypes / styles / layers
# ---------------------------------------------------------------------------
doc = ezdxf.new("R2010", setup=True)   # AC1024 (>= AC1015). setup loads std linetypes/dimstyles
doc.units = ezdxf.units.MM             # $INSUNITS = 4
try:
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = 25         # make CENTER linetype dashes visible at mm scale
except Exception:
    pass

msp = doc.modelspace()

# ensure CENTER linetype exists (setup=True normally provides it; guard anyway)
if "CENTER" not in doc.linetypes:
    doc.linetypes.add(
        "CENTER",
        pattern=[2.0, 1.25, -0.25, 0.25, -0.25],
        description="Center ____ _ ____ _ ____",
    )

# text styles: ASCII (labels/dims) and JP (Japanese room names / callouts)
if "ASCII" not in doc.styles:
    doc.styles.add("ASCII", font="arial.ttf")
if "JP" not in doc.styles:
    # Japanese-capable font; rendering depends on the viewer (cannot be verified here)
    doc.styles.add("JP", font="msgothic.ttf")

# layers
LAYER_DEF = [
    ("GRID",    8, "CENTER"),
    ("WALL",    7, "Continuous"),
    ("OPENING", 3, "Continuous"),
    ("DIM",     1, "Continuous"),
    ("ROOM",    5, "Continuous"),
    ("TEXT",    2, "Continuous"),
]
for name, color, ltype in LAYER_DEF:
    if name not in doc.layers:
        doc.layers.add(name, color=color, linetype=ltype)

# ---------------------------------------------------------------------------
# small drawing helpers
# ---------------------------------------------------------------------------
def line(p1, p2, layer):
    msp.add_line(p1, p2, dxfattribs={"layer": layer})


def hline(x1, x2, y, layer):
    msp.add_line((x1, y), (x2, y), dxfattribs={"layer": layer})


def vline(x, y1, y2, layer):
    msp.add_line((x, y1), (x, y2), dxfattribs={"layer": layer})


def circle(center, radius, layer):
    msp.add_circle(center, radius, dxfattribs={"layer": layer})


def arc(center, radius, a0, a1, layer):
    msp.add_arc(center, radius, a0, a1, dxfattribs={"layer": layer})


def text(s, x, y, height, layer, style="ASCII", rotation=0):
    """Middle-center placed text, version-robust (uses low-level align attribs)."""
    msp.add_text(
        s,
        dxfattribs={
            "layer": layer,
            "style": style,
            "height": height,
            "rotation": rotation,
            "insert": (x, y),
            "align_point": (x, y),
            "halign": 1,   # Center
            "valign": 2,   # Middle
        },
    )


def segments(a, b, cuts):
    """Return list of (s,e) subsegments of [a,b] with `cuts` intervals removed."""
    norm = sorted((max(s, a), min(e, b)) for s, e in cuts if e > a and s < b)
    out, cur = [], a
    for s, e in norm:
        if s > cur:
            out.append((cur, s))
        cur = max(cur, e)
    if cur < b:
        out.append((cur, b))
    return out


def draw_h_face(y, x_a, x_b, cuts, layer):
    for s, e in segments(x_a, x_b, cuts):
        hline(s, e, y, layer)


def draw_v_face(x, y_a, y_b, cuts, layer):
    for s, e in segments(y_a, y_b, cuts):
        vline(x, s, e, layer)


# ---------------------------------------------------------------------------
# 1) GRID lines + balloons (GRID layer)
# ---------------------------------------------------------------------------
GRID_EXT_TR = 700          # extension beyond footprint at top/right
BALLOON_R = 260
X_BALLOON_Y = -1900        # X balloons row (south)
Y_BALLOON_X = -1900        # Y balloons column (west)
GRID_BOT = X_BALLOON_Y + BALLOON_R   # grid vertical lines stop at top of X balloon
GRID_LEFT = Y_BALLOON_X + BALLOON_R  # grid horizontal lines stop at right of Y balloon
GRID_TOP = FP_Y1 + GRID_EXT_TR
GRID_RIGHT = FP_X1 + GRID_EXT_TR

for lab, xc in zip(X_LABELS, X_COORDS):
    vline(xc, GRID_BOT, GRID_TOP, "GRID")
    circle((xc, X_BALLOON_Y), BALLOON_R, "GRID")
    text(lab, xc, X_BALLOON_Y, 260, "GRID", style="ASCII")

for lab, yc in zip(Y_LABELS, Y_COORDS):
    hline(GRID_LEFT, GRID_RIGHT, yc, "GRID")
    circle((Y_BALLOON_X, yc), BALLOON_R, "GRID")
    text(lab, Y_BALLOON_X, yc, 260, "GRID", style="ASCII")

# ---------------------------------------------------------------------------
# 2) WALLS (double face lines) on WALL layer, broken at openings
#    Opening cut-ranges per wall (along the wall axis):
# ---------------------------------------------------------------------------
CUT_S = [(455, 1365), (2730, 4550)]   # O1 door, O2 window  (south wall, x)
CUT_E = [(1820, 3640)]                # O3 window           (east wall,  y)
CUT_W1 = [(455, 1365)]               # O4 door             (interior W-1, y)

# --- exterior walls: outer face closes corners, inner face stops at inner corner
# South (yc=0)
draw_h_face(-H, FP_X0 - H, FP_X1 + H, CUT_S, "WALL")     # outer, y=-60
draw_h_face(+H, FP_X0 + H, FP_X1 - H, CUT_S, "WALL")     # inner, y=+60
# North (yc=4550)
draw_h_face(FP_Y1 + H, FP_X0 - H, FP_X1 + H, [], "WALL")  # outer, y=4610
draw_h_face(FP_Y1 - H, FP_X0 + H, FP_X1 - H, [], "WALL")  # inner, y=4490
# West (xc=0)
draw_v_face(-H, FP_Y0 - H, FP_Y1 + H, [], "WALL")         # outer, x=-60
draw_v_face(+H, FP_Y0 + H, FP_Y1 - H, [], "WALL")         # inner, x=+60
# East (xc=5460)
draw_v_face(FP_X1 + H, FP_Y0 - H, FP_Y1 + H, CUT_E, "WALL")  # outer, x=5520
draw_v_face(FP_X1 - H, FP_Y0 + H, FP_Y1 - H, CUT_E, "WALL")  # inner, x=5400

# --- interior walls
# W-1 vertical at x=1820, spanning inner-south(60)..inner-north(4490), door O4
draw_v_face(1820 - H, FP_Y0 + H, FP_Y1 - H, CUT_W1, "WALL")   # x=1760
draw_v_face(1820 + H, FP_Y0 + H, FP_Y1 - H, CUT_W1, "WALL")   # x=1880
# W-2 horizontal at y=1820, spanning inner-west(60)..W-1 west face(1760)
draw_h_face(1820 - H, FP_X0 + H, 1820 - H, [], "WALL")        # y=1760
draw_h_face(1820 + H, FP_X0 + H, 1820 - H, [], "WALL")        # y=1880
# W-3 horizontal at y=2730, spanning inner-west(60)..W-1 west face(1760)
draw_h_face(2730 - H, FP_X0 + H, 1820 - H, [], "WALL")        # y=2670
draw_h_face(2730 + H, FP_X0 + H, 1820 - H, [], "WALL")        # y=2790

# ---------------------------------------------------------------------------
# 3) OPENINGS on OPENING layer (jambs that notch the wall + door/window symbols)
# ---------------------------------------------------------------------------
# O1 : door, south wall, x 455..1365, hinge at x=455 swinging into 玄関 (+y)
vline(455, -H, +H, "OPENING")
vline(1365, -H, +H, "OPENING")
line((455, H), (455, H + 910), "OPENING")          # door leaf (open)
arc((455, H), 910, 0, 90, "OPENING")               # swing arc

# O2 : window, south wall, x 2730..4550
vline(2730, -H, +H, "OPENING")
vline(4550, -H, +H, "OPENING")
hline(2730, 4550, -20, "OPENING")                  # glazing lines
hline(2730, 4550, 20, "OPENING")

# O3 : window, east wall, y 1820..3640
hline(FP_X1 - H, FP_X1 + H, 1820, "OPENING")
hline(FP_X1 - H, FP_X1 + H, 3640, "OPENING")
vline(FP_X1 - 20, 1820, 3640, "OPENING")           # glazing lines
vline(FP_X1 + 20, 1820, 3640, "OPENING")

# O4 : interior door, W-1 (x=1820), y 455..1365, hinge at y=455 swinging into LDK (+x)
hline(1820 - H, 1820 + H, 455, "OPENING")
hline(1820 - H, 1820 + H, 1365, "OPENING")
line((1820 + H, 455), (1820 + H + 910, 455), "OPENING")   # door leaf (open)
arc((1820 + H, 455), 910, 0, 90, "OPENING")              # swing arc

# ---------------------------------------------------------------------------
# 4) DIMENSIONS on DIM layer  (real DIMENSION entities)
# ---------------------------------------------------------------------------
DIM_OVERRIDE = {
    "dimtxt": 180,   # text height
    "dimasz": 120,   # arrow size
    "dimexe": 80,    # extension line extension
    "dimexo": 120,   # extension line offset from origin
    "dimgap": 50,    # gap around text
    "dimtad": 1,     # text above dim line
    "dimdle": 0,
}


def linear_chain(stations, const_coord, axis, dimline_coord):
    """Chain of single-interval linear DIMENSION entities."""
    for i in range(len(stations) - 1):
        a, b = stations[i], stations[i + 1]
        if axis == "x":
            p1, p2, base, ang = (a, const_coord), (b, const_coord), (0, dimline_coord), 0
        else:  # 'y'
            p1, p2, base, ang = (const_coord, a), (const_coord, b), (dimline_coord, 0), 90
        d = msp.add_linear_dim(
            base=base, p1=p1, p2=p2, angle=ang,
            dimstyle="EZDXF", override=DIM_OVERRIDE,
            dxfattribs={"layer": "DIM"},
        )
        d.render()


def linear_overall(a, b, const_coord, axis, dimline_coord):
    if axis == "x":
        p1, p2, base, ang = (a, const_coord), (b, const_coord), (0, dimline_coord), 0
    else:
        p1, p2, base, ang = (const_coord, a), (const_coord, b), (dimline_coord, 0), 90
    d = msp.add_linear_dim(
        base=base, p1=p1, p2=p2, angle=ang,
        dimstyle="EZDXF", override=DIM_OVERRIDE,
        dxfattribs={"layer": "DIM"},
    )
    d.render()


# South chain (measures X), placed below the south wall
linear_chain(X_COORDS, 0, "x", -700)
linear_overall(0, 5460, 0, "x", -1250)
# West chain (measures Y), placed left of the west wall
linear_chain(Y_COORDS, 0, "y", -700)
linear_overall(0, 4550, 0, "y", -1250)

# ---------------------------------------------------------------------------
# 5) ROOM names on ROOM layer
# ---------------------------------------------------------------------------
for r in ROOMS:
    cx = (r["x0"] + r["x1"]) / 2.0
    cy = (r["y0"] + r["y1"]) / 2.0
    text(r["name"], cx, cy + 90, 280, "ROOM", style="JP")
    text(f"{r['area']:.2f} m2", cx, cy - 220, 150, "ROOM", style="JP")

# ---------------------------------------------------------------------------
# 6) TEXT layer : drawing title + opening callouts
# ---------------------------------------------------------------------------
text("木造平屋 1階平面図   S=1:100", (FP_X0 + FP_X1) / 2.0, -2700, 320, "TEXT", style="JP")

OPENING_CALLOUTS = [
    ("玄関ドア",   910,  330),
    ("LDK掃出窓", 3640, 330),
    ("LDK窓",     5090, 2730),
    ("内部ドア",   2160, 910),
]
for s, x, y in OPENING_CALLOUTS:
    text(s, x, y, 150, "TEXT", style="JP")

# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------
os.makedirs(os.path.dirname(OUT), exist_ok=True)
doc.saveas(OUT)

# -*- coding: utf-8 -*-
"""
T004 : 木造2階建て 1階平面図（法規適合を自分で満たす）
armB : ezdxf で DXF を生成し、建具表(schedule.json)を書き出す。

自分で決めた自由パラメータ
---------------------------
階段（令23条, 階高2900mm, 階段室内法 1700x1700）:
    段数(riser) = 13      -> 蹴上 = 2900/13 = 223.08mm (<=230 OK)
    踏面 tread  = 225mm   (>=150 OK)
    幅   width  = 800mm   (>=750 OK, 折り返し1フライトの有効幅)
    段板本数 = 段数-1 = 12（STAIRレイヤに12本の段板線）

居室の窓（法28条, 採光1/7・換気1/20, 採光補正=1の簡略モデル）:
    和室 床面積 16.562 m^2  必要採光 2.3660  必要換気 0.8281
        O2(W1,南) 1690x2000 = 3.380 m^2
        O3(W2,東) 1690x1200 = 2.028 m^2
        採光合計 5.408 (>=2.366 OK)  換気 5.408*0.5=2.704 (>=0.8281 OK)
    LDK  床面積 31.4678 m^2 必要採光 4.4954  必要換気 1.5734
        O4(W3,斜め) 1400x1500 = 2.100 m^2
        O5(W4,北)   2400x1800 = 4.320 m^2
        採光合計 6.420 (>=4.4954 OK)  換気 6.420*0.5=3.210 (>=1.5734 OK)
"""

import math
import json
import ezdxf
from ezdxf.enums import TextEntityAlignment
from shapely.geometry import Polygon, MultiPolygon, LineString, box
from shapely.ops import unary_union

OUT_DXF = "/Users/boss/dev/01_projects/big-business/cad-bench/attempts/T004/armB_ezdxf.dxf"
OUT_SCHED = "/Users/boss/dev/01_projects/big-business/cad-bench/attempts/T004/armB_ezdxf.schedule.json"

# --------------------------------------------------------------------------
# grid
# --------------------------------------------------------------------------
XC = [0, 910, 1820, 2730, 3640, 4550, 5460, 6370, 7280, 8190, 9100]
YC = [0, 910, 1820, 2730, 3640, 4550, 5460, 6370, 7280, 8190]
X = {f"X{i+1}": c for i, c in enumerate(XC)}
Y = {f"Y{i+1}": c for i, c in enumerate(YC)}
T = 120          # wall thickness
HT = T / 2.0     # half thickness


def resolve(tok):
    """'X3' or 'Y3+455' -> coordinate value"""
    tok = tok.strip()
    base, off = tok, 0.0
    if "+" in tok:
        base, o = tok.split("+")
        off = float(o)
    elif "-" in tok[1:]:
        i = tok.index("-", 1)
        base, off = tok[:i], float(tok[i:])
    d = X if base[0] == "X" else Y
    return d[base] + off


def rp(p):
    return (resolve(p[0]), resolve(p[1]))


# --------------------------------------------------------------------------
# free parameters
# --------------------------------------------------------------------------
STAIR_RISERS = 13
STAIR_RISER = round(2900.0 / STAIR_RISERS, 2)     # 223.08
STAIR_TREAD = 225
STAIR_WIDTH = 800

WIN = {   # id : (room, width, height, openable_ratio)
    "O2": ("和室", 1690, 2000, 0.5),
    "O3": ("和室", 1690, 1200, 0.5),
    "O4": ("LDK", 1400, 1500, 0.5),
    "O5": ("LDK", 2400, 1800, 0.5),
}

# --------------------------------------------------------------------------
# document / layers
# --------------------------------------------------------------------------
doc = ezdxf.new("R2010", setup=True)
doc.header["$INSUNITS"] = 4   # millimeters
msp = doc.modelspace()

LAYERS = {
    "GRID":    (8, "CENTER"),
    "WALL":    (7, "Continuous"),
    "OPENING": (1, "Continuous"),
    "DIM":     (4, "Continuous"),
    "ROOM":    (3, "Continuous"),
    "TEXT":    (7, "Continuous"),
    "STAIR":   (5, "Continuous"),
}
for name, (col, lt) in LAYERS.items():
    if name not in doc.layers:
        doc.layers.add(name, color=col, linetype=lt)


def add_text(s, x, y, h, layer):
    t = msp.add_text(s, height=h, dxfattribs={"layer": layer})
    t.set_placement((x, y), align=TextEntityAlignment.MIDDLE_CENTER)
    return t


# --------------------------------------------------------------------------
# WALLS  (shapely: exterior band + interior wall rectangles, unioned, then
#         openings subtracted -> automatic corner/T trim + jambs)
# --------------------------------------------------------------------------
footprint = Polygon([(0, 0), (9100, 0), (9100, 6370), (7280, 8190), (0, 8190)])
outer = footprint.buffer(HT, join_style=2, mitre_limit=10)
inner = footprint.buffer(-HT, join_style=2, mitre_limit=10)
band = outer.difference(inner)

interior_walls = [
    (("X3", "Y1"), ("X3", "Y6")),          # I1
    (("X5", "Y1"), ("X5", "Y6")),          # I2
    (("X7", "Y1"), ("X7", "Y6")),          # I3
    (("X1", "Y3"), ("X7", "Y3")),          # I4
    (("X1", "Y3+455"), ("X3", "Y3+455")),  # I5
    (("X3", "Y4"), ("X5", "Y4")),          # I6
    (("X1", "Y6"), ("X11", "Y6")),         # I7
]
wall_geoms = [band]
for a, b in interior_walls:
    ls = LineString([rp(a), rp(b)])
    wall_geoms.append(ls.buffer(HT, cap_style=2, join_style=2))
walls = unary_union(wall_geoms)

# ---- opening cut geometries -----------------------------------------------
# axis-aligned cuts slightly overshoot the wall faces so the cut is clean
cuts = []
cuts.append(box(455, -70, 1365, 70))        # O1 door  W-S  x centre 910
cuts.append(box(6435, -70, 8125, 70))       # O2 win   W-S  centre 7280 w1690
cuts.append(box(9030, 1430, 9170, 3120))    # O3 win   W-E  centre 2275 w1690
cuts.append(box(2440, 8120, 4840, 8260))    # O5 win   W-N  centre 3640 w2400
cuts.append(box(1755, 455, 1885, 1365))     # O6 door  I1   centre 910
cuts.append(box(455, 4485, 1365, 4615))     # O7 door  I7   centre 910
cuts.append(box(6825, 4485, 7735, 4615))    # O8 door  I7   centre 7280

# O4 diagonal window on W-D  (wall A=(9100,6370) -> B=(7280,8190))
A = (9100.0, 6370.0)
B = (7280.0, 8190.0)
L = math.hypot(B[0] - A[0], B[1] - A[1])
d = ((B[0] - A[0]) / L, (B[1] - A[1]) / L)     # along wall
per = (d[1], -d[0])                            # perpendicular
M = ((A[0] + B[0]) / 2, (A[1] + B[1]) / 2)     # centre (8190,7280)
w4 = WIN["O4"][1]
e1 = (M[0] + d[0] * w4 / 2, M[1] + d[1] * w4 / 2)
e2 = (M[0] - d[0] * w4 / 2, M[1] - d[1] * w4 / 2)
o = 70
c1 = (e1[0] + per[0] * o, e1[1] + per[1] * o)
c2 = (e1[0] - per[0] * o, e1[1] - per[1] * o)
c3 = (e2[0] - per[0] * o, e2[1] - per[1] * o)
c4 = (e2[0] + per[0] * o, e2[1] + per[1] * o)
cuts.append(Polygon([c1, c2, c3, c4]))

wall_final = walls.difference(unary_union(cuts))


def draw_polygon_edges(geom, layer):
    polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    for p in polys:
        msp.add_lwpolyline(list(p.exterior.coords), close=True,
                           dxfattribs={"layer": layer})
        for ring in p.interiors:
            msp.add_lwpolyline(list(ring.coords), close=True,
                               dxfattribs={"layer": layer})


draw_polygon_edges(wall_final, "WALL")


# --------------------------------------------------------------------------
# OPENING symbols
# --------------------------------------------------------------------------
def draw_window(cx, cy, ax, ay, px, py, w):
    hx, hy = ax * w / 2.0, ay * w / 2.0
    for off in (20, -20):
        ox, oy = px * off, py * off
        msp.add_line((cx - hx + ox, cy - hy + oy),
                     (cx + hx + ox, cy + hy + oy),
                     dxfattribs={"layer": "OPENING"})


def draw_door(cx, cy, ax, ay, px, py, w):
    hx, hy = cx - ax * w / 2.0, cy - ay * w / 2.0     # hinge
    fx, fy = cx + ax * w / 2.0, cy + ay * w / 2.0     # far jamb
    lx, ly = hx + px * w, hy + py * w                 # leaf tip
    msp.add_line((hx, hy), (lx, ly), dxfattribs={"layer": "OPENING"})
    a1 = math.degrees(math.atan2(ly - hy, lx - hx))
    a2 = math.degrees(math.atan2(fy - hy, fx - hx))
    if (a2 - a1) % 360 <= 180:
        s, e = a1, a2
    else:
        s, e = a2, a1
    msp.add_arc((hx, hy), w, s, e, dxfattribs={"layer": "OPENING"})


# doors
draw_door(910, 0, 1, 0, 0, 1, 910)        # O1  D1  into 玄関
draw_door(1820, 910, 0, 1, 1, 0, 910)     # O6  D2  into ホール
draw_door(910, 4550, 1, 0, 0, -1, 910)    # O7  D3  into 洗面脱衣
draw_door(7280, 4550, 1, 0, 0, -1, 910)   # O8  D4  into 和室
# windows
draw_window(7280, 0, 1, 0, 0, 1, WIN["O2"][1])          # O2  W1  south
draw_window(9100, 2275, 0, 1, 1, 0, WIN["O3"][1])       # O3  W2  east
draw_window(M[0], M[1], d[0], d[1], per[0], per[1], w4)  # O4 W3 diagonal
draw_window(3640, 8190, 1, 0, 0, 1, WIN["O5"][1])       # O5  W4  north

# opening marks (符号) on OPENING layer, near each opening
MARKS = {
    "D1": (910, -300), "W1": (7280, -300),
    "D2": (2150, 910), "D3": (910, 4300), "D4": (7280, 4300),
    "W2": (8720, 2275),
    "W3": (M[0] - per[0] * 380, M[1] - per[1] * 380),
    "W4": (3640, 7860),
}
for sym, (mx, my) in MARKS.items():
    add_text(sym, mx, my, 230, "OPENING")


# --------------------------------------------------------------------------
# ROOMS : name + area  (壁芯多角形の面積)
# --------------------------------------------------------------------------
ROOMS = [
    ("玄関",     [["X1", "Y1"], ["X3", "Y1"], ["X3", "Y3"], ["X1", "Y3"]]),
    ("収納",     [["X1", "Y3"], ["X3", "Y3"], ["X3", "Y3+455"], ["X1", "Y3+455"]]),
    ("洗面脱衣", [["X1", "Y3+455"], ["X3", "Y3+455"], ["X3", "Y6"], ["X1", "Y6"]]),
    ("ホール",   [["X3", "Y1"], ["X5", "Y1"], ["X5", "Y3"], ["X3", "Y3"]]),
    ("便所",     [["X3", "Y3"], ["X5", "Y3"], ["X5", "Y4"], ["X3", "Y4"]]),
    ("浴室",     [["X3", "Y4"], ["X5", "Y4"], ["X5", "Y6"], ["X3", "Y6"]]),
    ("階段",     [["X5", "Y1"], ["X7", "Y1"], ["X7", "Y3"], ["X5", "Y3"]]),
    ("納戸",     [["X5", "Y3"], ["X7", "Y3"], ["X7", "Y6"], ["X5", "Y6"]]),
    ("和室",     [["X7", "Y1"], ["X11", "Y1"], ["X11", "Y6"], ["X7", "Y6"]]),
    ("LDK",      [["X1", "Y6"], ["X11", "Y6"], ["X11", "Y8"], ["X9", "Y10"], ["X1", "Y10"]]),
]

total_area = 0.0
for name, poly in ROOMS:
    pts = [rp(p) for p in poly]
    sp = Polygon(pts)
    area_m2 = sp.area / 1_000_000.0
    total_area += area_m2
    rpn = sp.representative_point()
    cx, cy = rpn.x, rpn.y
    add_text(name, cx, cy + 170, 260, "ROOM")
    add_text(f"{area_m2:.2f} m2", cx, cy - 170, 230, "ROOM")

# total floor area on TEXT layer
add_text(f"1F 床面積合計 = {total_area:.2f} m2", 4000, -3550, 320, "TEXT")


# --------------------------------------------------------------------------
# STAIR : 折り返し階段（U-turn）, 段板 = 段数-1 = 12 本, 各線長 = 幅 800
#         内法 X[3700,5400] Y[60,1760] ; 中央ささら x=4550
# --------------------------------------------------------------------------
west_x0, west_x1 = 3700, 4500          # 西フライト（幅800）
east_x0, east_x1 = 4600, 5400          # 東フライト（幅800）
tread_y0 = 200
for i in range(6):
    y = tread_y0 + i * STAIR_TREAD     # 200,425,...,1325
    msp.add_line((west_x0, y), (west_x1, y), dxfattribs={"layer": "STAIR"})
    msp.add_line((east_x0, y), (east_x1, y), dxfattribs={"layer": "STAIR"})
# 中央ささら（段板に数えない : 縦線・長さ1700）
msp.add_line((4550, 60), (4550, 1760), dxfattribs={"layer": "STAIR"})
# 昇り方向表示
add_text("UP", 4550, 1600, 180, "STAIR")


# --------------------------------------------------------------------------
# GRID lines + labels
# --------------------------------------------------------------------------
GY0, GY1 = -700, 8850
GX0, GX1 = -2400, 9400
for lab, xc in X.items():
    msp.add_line((xc, GY0), (xc, GY1), dxfattribs={"layer": "GRID"})
    msp.add_circle((xc, GY1), 300, dxfattribs={"layer": "GRID"})
    add_text(lab, xc, GY1, 240, "GRID")
for lab, yc in Y.items():
    msp.add_line((GX0, yc), (GX1, yc), dxfattribs={"layer": "GRID"})
    msp.add_circle((GX0, yc), 300, dxfattribs={"layer": "GRID"})
    add_text(lab, GX0, yc, 240, "GRID")


# --------------------------------------------------------------------------
# DIMENSIONS (real DIMENSION entities)
# --------------------------------------------------------------------------
DIMOVR = {"dimtxt": 250, "dimasz": 180, "dimexe": 120, "dimexo": 200,
          "dimgap": 80, "dimdec": 0, "dimtad": 1}


def chain_dim(stations, fixed, direction, dimline_pos, overall_pos=None):
    st = sorted(set(stations))
    ang = 0 if direction == "x" else 90
    for a, b in zip(st, st[1:]):
        if direction == "x":
            p1, p2, base = (a, fixed), (b, fixed), (0, dimline_pos)
        else:
            p1, p2, base = (fixed, a), (fixed, b), (dimline_pos, 0)
        dim = msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=ang,
                                 dimstyle="EZDXF", override=DIMOVR,
                                 dxfattribs={"layer": "DIM"})
        dim.render()
    if overall_pos is not None:
        a, b = st[0], st[-1]
        if direction == "x":
            p1, p2, base = (a, fixed), (b, fixed), (0, overall_pos)
        else:
            p1, p2, base = (fixed, a), (fixed, b), (overall_pos, 0)
        dim = msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=ang,
                                 dimstyle="EZDXF", override=DIMOVR,
                                 dxfattribs={"layer": "DIM"})
        dim.render()


# D-S2 : 南面 開口位置寸法（自分の窓幅から導出）
#   station 0, W-S 上の開口の両端 (O1:455,1365 / O2:6435,8125), 壁全長 9100
o2c = 7280
o2h = WIN["O2"][1] / 2.0
ds2 = [0, 455, 1365, o2c - o2h, o2c + o2h, 9100]
chain_dim(ds2, 0, "x", -600)

# D-S1 : 南面 通り芯寸法 + 総寸法
chain_dim(XC, 0, "x", -1600, overall_pos=-2600)

# D-W : 西面 通り芯寸法 + 総寸法
chain_dim(YC, 0, "y", -600, overall_pos=-1600)

# D-E : 東面 通り芯寸法(Y1..Y8) + 総寸法
chain_dim([0, 910, 1820, 2730, 3640, 4550, 5460, 6370], 9100, "y", 9700,
          overall_pos=10700)


# --------------------------------------------------------------------------
# save DXF
# --------------------------------------------------------------------------
doc.saveas(OUT_DXF)


# --------------------------------------------------------------------------
# schedule.json (建具表)
# --------------------------------------------------------------------------
schedule = {
    "stairs": {
        "risers": STAIR_RISERS,
        "riser_mm": STAIR_RISER,
        "tread_mm": STAIR_TREAD,
        "width_mm": STAIR_WIDTH,
    },
    "openings": {
        oid: {
            "room": room,
            "width_mm": w,
            "height_mm": h,
            "openable_ratio": r,
        }
        for oid, (room, w, h, r) in WIN.items()
    },
}
with open(OUT_SCHED, "w", encoding="utf-8") as f:
    json.dump(schedule, f, ensure_ascii=False, indent=2)

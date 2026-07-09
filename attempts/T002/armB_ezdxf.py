#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T002 : 木造2階建て 1階平面図（作図のみ）
spec.json の仕様どおりに DXF を生成する ezdxf スクリプト。

方針の要点
----------
- 壁は「壁芯 ±60mm の帯（buffer）」を全部 union して 1つの実体にする。
  これにより T字接合／十字接合／出隅が自動的にトリムされ、
  突き当たる側の壁面線が相手の壁を貫通しない（実体トリム）。
- 開口は壁実体から矩形を differnce して欠き込む（小口＝ジャム面が生成される）。
- 開口記号（戸＋弧／ガラス線）は OPENING レイヤに別途作図する。
- 寸法は実 DIMENSION エンティティ（add_linear_dim）で 4系統。1:100 用に dimscale=100。

このスクリプトを実行すると同ディレクトリに armB_ezdxf.dxf を書き出す。
"""

import math
import ezdxf
from ezdxf.enums import TextEntityAlignment
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

OUT = "/Users/boss/dev/01_projects/big-business/cad-bench/attempts/T002/armB_ezdxf.dxf"

# ---------------------------------------------------------------- 定数 -----
HALF = 60           # 壁厚 120 の半分（芯振り分け ±60）
EXT = 60            # union のため各壁端部をこの分だけ延長（接合部を確実に充填）
CUT = HALF + 15     # 開口の欠き込み帯の半幅（壁面を確実に貫く）

# ---------------------------------------------------------------- 通り芯 ---
XL = ["X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9", "X10", "X11"]
XC = [0, 910, 1820, 2730, 3640, 4550, 5460, 6370, 7280, 8190, 9100]
YL = ["Y1", "Y2", "Y3", "Y4", "Y5", "Y6", "Y7", "Y8", "Y9", "Y10"]
YC = [0, 910, 1820, 2730, 3640, 4550, 5460, 6370, 7280, 8190]

# ---------------------------------------------------------------- 壁 -------
# (id, from, to)
WALLS = [
    ("W-S", (0, 0),       (9100, 0)),
    ("W-E", (9100, 0),    (9100, 6370)),
    ("W-D", (9100, 6370), (7280, 8190)),   # 45度 斜め外壁
    ("W-N", (0, 8190),    (7280, 8190)),
    ("W-W", (0, 0),       (0, 8190)),
    ("I1", (1820, 0),    (1820, 4550)),
    ("I2", (3640, 0),    (3640, 4550)),
    ("I3", (5460, 0),    (5460, 4550)),
    ("I4", (0, 1820),    (5460, 1820)),
    ("I5", (0, 2275),    (1820, 2275)),    # 通り芯に乗らない半モジュール
    ("I6", (1820, 2730), (3640, 2730)),
    ("I7", (0, 4550),    (9100, 4550)),
]
WALLD = {wid: (pf, pt) for wid, pf, pt in WALLS}

# ---------------------------------------------------------------- 室 -------
ROOMS = [
    ("玄関",     [(0, 0), (1820, 0), (1820, 1820), (0, 1820)]),
    ("収納",     [(0, 1820), (1820, 1820), (1820, 2275), (0, 2275)]),
    ("洗面脱衣", [(0, 2275), (1820, 2275), (1820, 4550), (0, 4550)]),
    ("ホール",   [(1820, 0), (3640, 0), (3640, 1820), (1820, 1820)]),
    ("便所",     [(1820, 1820), (3640, 1820), (3640, 2730), (1820, 2730)]),
    ("浴室",     [(1820, 2730), (3640, 2730), (3640, 4550), (1820, 4550)]),
    ("階段",     [(3640, 0), (5460, 0), (5460, 1820), (3640, 1820)]),
    ("納戸",     [(3640, 1820), (5460, 1820), (5460, 4550), (3640, 4550)]),
    ("和室",     [(5460, 0), (9100, 0), (9100, 4550), (5460, 4550)]),
    ("LDK",      [(0, 4550), (9100, 4550), (9100, 6370), (7280, 8190), (0, 8190)]),
]

# ---------------------------------------------------------------- 開口 -----
# type: door / window
# door の swing: 戸を開く方向の法線（壁進行方向 from->to に対する符号 side）と
#               ヒンジ位置（"t0" 側）。s=-1 は左法線の逆、s=+1 は左法線。
OPENINGS = [
    {"id": "O1", "type": "door",   "wall": "W-S", "t0": 455,  "t1": 1365, "side": +1},  # 玄関ドア（北=玄関側へ）
    {"id": "O2", "type": "window", "wall": "W-S", "t0": 6370, "t1": 8190},              # 和室掃出窓
    {"id": "O3", "type": "window", "wall": "W-E", "t0": 1820, "t1": 3640},              # 和室窓
    {"id": "O4", "type": "window", "wall": "W-D", "t0": 700,  "t1": 1900},              # LDK窓（斜め壁）
    {"id": "O5", "type": "window", "wall": "W-N", "t0": 2730, "t1": 4550},              # LDK北窓
    {"id": "O6", "type": "door",   "wall": "I1",  "t0": 455,  "t1": 1365, "side": -1},  # 玄関→ホール（玄関側へ）
    {"id": "O7", "type": "door",   "wall": "I7",  "t0": 455,  "t1": 1365, "side": +1},  # 洗面脱衣→LDK（洗面側へ）
    {"id": "O8", "type": "door",   "wall": "I7",  "t0": 6370, "t1": 7280, "side": +1},  # 和室→LDK（和室側へ）
]

# ---------------------------------------------------------------- 階段 -----
TREADS = [
    [(3700, 260),  (4550, 260)],
    [(3700, 460),  (4550, 460)],
    [(3700, 660),  (4550, 660)],
    [(3700, 860),  (4550, 860)],
    [(3700, 1060), (4550, 1060)],
    [(3700, 1260), (4550, 1260)],
    [(4550, 260),  (5400, 260)],
    [(4550, 460),  (5400, 460)],
    [(4550, 660),  (5400, 660)],
    [(4550, 860),  (5400, 860)],
    [(4550, 1060), (5400, 1060)],
    [(4550, 1260), (5400, 1260)],
    [(3700, 1360), (5400, 1360)],
    [(4550, 60),   (4550, 1360)],
]
UP_AT = (3760, 140)

# ---------------------------------------------------------------- 寸法 -----
DIM_CHAINS = [
    {"id": "D-S", "dir": "x", "at": 0,
     "stations": [0, 910, 1820, 2730, 3640, 4550, 5460, 6370, 7280, 8190, 9100],
     "base": -600,  "overall_base": -1600},
    {"id": "D-W", "dir": "y", "at": 0,
     "stations": [0, 910, 1820, 2730, 3640, 4550, 5460, 6370, 7280, 8190],
     "base": -600,  "overall_base": -1600},
    {"id": "D-E", "dir": "y", "at": 9100,
     "stations": [0, 910, 1820, 2730, 3640, 4550, 5460, 6370],
     "base": 9700,  "overall_base": 10700},
    {"id": "D-N", "dir": "x", "at": 8190,
     "stations": [0, 910, 1820, 2730, 3640, 4550, 5460, 6370, 7280],
     "base": 8790,  "overall_base": 9790},
]

DIM_OVR = {
    "dimscale": 100,   # 1:100 用の全体スケール
    "dimtxt": 2.5,     # 文字高（紙 mm）→ model 250mm
    "dimasz": 2.5,     # 矢印
    "dimexe": 1.25,    # 補助線の突き出し
    "dimexo": 1.0,     # 補助線と対象の隙間
    "dimgap": 0.8,     # 文字と寸法線の隙間
    "dimdec": 0,       # 小数点以下 0 桁
    "dimtad": 1,       # 文字を寸法線の上に
    "dimlfac": 1,      # 計測係数（mm そのまま）
    "dimtih": 0,       # 内側文字は寸法線に平行
    "dimtoh": 0,       # 外側文字も平行
}


# =============================================================== ヘルパ ===
def unit_dir(pf, pt):
    """from->to の単位ベクトル u, 左法線 n, 長さ L を返す。"""
    dx, dy = pt[0] - pf[0], pt[1] - pf[1]
    L = math.hypot(dx, dy)
    u = (dx / L, dy / L)
    n = (-u[1], u[0])  # 左法線
    return u, n, L


def along(pf, pt, t):
    """from から距離 t の点（芯線上）。"""
    u, _, _ = unit_dir(pf, pt)
    return (pf[0] + u[0] * t, pf[1] + u[1] * t)


def extend_seg(pf, pt, ext):
    u, _, _ = unit_dir(pf, pt)
    a = (pf[0] - u[0] * ext, pf[1] - u[1] * ext)
    b = (pt[0] + u[0] * ext, pt[1] + u[1] * ext)
    return a, b


def polygons(geom):
    """Polygon / MultiPolygon / GeometryCollection から Polygon 群を取り出す。"""
    gt = geom.geom_type
    if gt == "Polygon":
        return [geom]
    if gt in ("MultiPolygon", "GeometryCollection"):
        return [g for g in geom.geoms if g.geom_type == "Polygon"]
    return []


# =============================================================== 図面 =====
doc = ezdxf.new("R2010", setup=True)
doc.header["$INSUNITS"] = 4        # mm
doc.header["$MEASUREMENT"] = 1     # metric
doc.header["$LTSCALE"] = 100
msp = doc.modelspace()

# ---- レイヤ -----------------------------------------------------------
# (name, color, linetype)
LAYERS = [
    ("GRID",    8, "CENTER"),
    ("WALL",    7, "CONTINUOUS"),
    ("OPENING", 3, "CONTINUOUS"),
    ("DIM",     4, "CONTINUOUS"),
    ("ROOM",    2, "CONTINUOUS"),
    ("TEXT",    7, "CONTINUOUS"),
    ("STAIR",   6, "CONTINUOUS"),
]
for name, col, lt in LAYERS:
    try:
        doc.layers.add(name, color=col, linetype=lt)
    except Exception:
        doc.layers.add(name, color=col)  # CENTER が無い環境用フォールバック

# ---- 日本語テキストスタイル ------------------------------------------
try:
    doc.styles.add("JP", font="msgothic.ttc")
except Exception:
    pass  # 既にある/環境差でも本文の文字列は保持される


def add_text(s, pos, layer, height, align=TextEntityAlignment.MIDDLE_CENTER,
             style="JP"):
    t = msp.add_text(
        s, dxfattribs={"layer": layer, "style": style, "height": height})
    t.set_placement(pos, align=align)
    return t


# ============================================================ 壁実体 =====
wall_bands = []
for wid, pf, pt in WALLS:
    a, b = extend_seg(pf, pt, EXT)
    wall_bands.append(LineString([a, b]).buffer(HALF, cap_style=2, join_style=2))
wall_solid = unary_union(wall_bands)

# 開口の欠き込み
cut_bands = []
for op in OPENINGS:
    pf, pt = WALLD[op["wall"]]
    p0 = along(pf, pt, op["t0"])
    p1 = along(pf, pt, op["t1"])
    cut_bands.append(LineString([p0, p1]).buffer(CUT, cap_style=2, join_style=2))
walls_cut = wall_solid.difference(unary_union(cut_bands))

# 壁面線を LWPOLYLINE で作図（外形＋各室内周）
for poly in polygons(walls_cut):
    rings = [poly.exterior] + list(poly.interiors)
    for ring in rings:
        pts = [(x, y) for x, y in list(ring.coords)[:-1]]
        if len(pts) >= 2:
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "WALL"})


# ============================================================ 開口記号 ===
def draw_window(op):
    pf, pt = WALLD[op["wall"]]
    _, n, _ = unit_dir(pf, pt)
    w = op["t1"] - op["t0"]
    m = 0.05 * w  # 端部余白 5% → 有効長 90%（8割以上）
    ga = along(pf, pt, op["t0"] + m)
    gb = along(pf, pt, op["t1"] - m)
    for off in (-30, 30):  # 壁と平行なガラス線 2本
        a = (ga[0] + n[0] * off, ga[1] + n[1] * off)
        b = (gb[0] + n[0] * off, gb[1] + n[1] * off)
        msp.add_line(a, b, dxfattribs={"layer": "OPENING"})


def draw_door(op):
    pf, pt = WALLD[op["wall"]]
    u, n, _ = unit_dir(pf, pt)
    w = op["t1"] - op["t0"]
    s = (n[0] * op["side"], n[1] * op["side"])  # 戸を開く方向（壁の法線）
    hinge = along(pf, pt, op["t0"])             # ヒンジ（t0 側）
    other = along(pf, pt, op["t1"])             # 反対側ジャム
    leaf_end = (hinge[0] + s[0] * w, hinge[1] + s[1] * w)

    # 戸（薄い板）：開いた状態を厚み d の矩形で表現
    d = 40
    tdir = (u[0], u[1])  # 板厚方向（other 側へ）
    rect = [
        hinge,
        leaf_end,
        (leaf_end[0] + tdir[0] * d, leaf_end[1] + tdir[1] * d),
        (hinge[0] + tdir[0] * d, hinge[1] + tdir[1] * d),
    ]
    msp.add_lwpolyline(rect, close=True, dxfattribs={"layer": "OPENING"})

    # 開き勝手の弧（半径 w, ヒンジ中心, 90度）
    a_other = math.degrees(math.atan2(other[1] - hinge[1], other[0] - hinge[0]))
    a_leaf = math.degrees(math.atan2(leaf_end[1] - hinge[1], leaf_end[0] - hinge[0]))
    start, end = a_other, a_leaf
    if (end - start) % 360 > 180:
        start, end = a_leaf, a_other
    msp.add_arc(center=hinge, radius=w, start_angle=start, end_angle=end,
                dxfattribs={"layer": "OPENING"})


for op in OPENINGS:
    if op["type"] == "window":
        draw_window(op)
    else:
        draw_door(op)


# ============================================================ 通り芯 =====
GV0, GV1 = -1850, 8450    # 縦グリッド線（定 x）の y 範囲
GH0, GH1 = -1850, 9450    # 横グリッド線（定 y）の x 範囲
BUB = 250                 # 通り芯符号の丸半径

for x in XC:
    msp.add_line((x, GV0), (x, GV1), dxfattribs={"layer": "GRID"})
for y in YC:
    msp.add_line((GH0, y), (GH1, y), dxfattribs={"layer": "GRID"})

# 符号（丸＋文字）: X は下端、Y は左端
for lab, x in zip(XL, XC):
    c = (x, -2100)
    msp.add_circle(c, BUB, dxfattribs={"layer": "GRID"})
    add_text(lab, c, "GRID", 200, style="Standard")
for lab, y in zip(YL, YC):
    c = (-2100, y)
    msp.add_circle(c, BUB, dxfattribs={"layer": "GRID"})
    add_text(lab, c, "GRID", 200, style="Standard")


# ============================================================ 室名 =======
for name, poly in ROOMS:
    p = Polygon(poly).representative_point()  # L型 LDK でも内部点を保証
    add_text(name, (p.x, p.y), "ROOM", 300)


# ============================================================ 階段 =======
for a, b in TREADS:
    msp.add_line(a, b, dxfattribs={"layer": "STAIR"})
add_text("UP", UP_AT, "STAIR", 180, align=TextEntityAlignment.LEFT, style="Standard")


# ============================================================ 図面注記 ===
# 一般注記は TEXT レイヤに（表題・縮尺）
add_text("木造2階建て 1階平面図", (0, -2900), "TEXT", 350,
         align=TextEntityAlignment.LEFT)
add_text("S=1:100  単位:mm", (0, -3450), "TEXT", 250,
         align=TextEntityAlignment.LEFT)


# ============================================================ 寸法 =======
def add_chain(ch):
    d = ch["dir"]
    at = ch["at"]
    st = ch["stations"]

    def pt_at(v):
        return (v, at) if d == "x" else (at, v)

    def base_pt(mid, line):
        return (mid, line) if d == "x" else (line, mid)

    angle = 0 if d == "x" else 90

    # 個別寸法（通り芯間）
    for i in range(len(st) - 1):
        s0, s1 = st[i], st[i + 1]
        mid = (s0 + s1) / 2.0
        dim = msp.add_linear_dim(
            base=base_pt(mid, ch["base"]),
            p1=pt_at(s0), p2=pt_at(s1),
            angle=angle, dimstyle="EZDXF",
            override=DIM_OVR, dxfattribs={"layer": "DIM"})
        dim.render()

    # 総寸法
    s0, s1 = st[0], st[-1]
    mid = (s0 + s1) / 2.0
    dim = msp.add_linear_dim(
        base=base_pt(mid, ch["overall_base"]),
        p1=pt_at(s0), p2=pt_at(s1),
        angle=angle, dimstyle="EZDXF",
        override=DIM_OVR, dxfattribs={"layer": "DIM"})
    dim.render()


for ch in DIM_CHAINS:
    add_chain(ch)


# ============================================================ 保存 =======
doc.saveas(OUT)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cad-bench T003 : 木造2階建て 1階平面図（座標を導出する）
armB / ezdxf 実装

このスクリプトを実行すると、同じディレクトリに armB_ezdxf.dxf を書き出す。
座標はほとんど与えられていないため、通り芯符号・室との関係から
すべて自前で導出している。実験プロトコルにより、本スクリプトの実行・検証は
一切行っていない（一発生成）。

方針の要点:
  - 壁は「芯振り分け 120mm」を shapely でソリッド化して union する。
    T字接合・入隅出隅・45度隅は union の外形境界として自動的にトリムされる。
  - 開口は壁ソリッドから矩形を差し引いて「実体の抜き」を作り、
    その位置にドア（戸＋開き勝手の弧）／窓（ガラス線）を描く。
  - center_of_room 開口は「室境界のうちその壁芯線上に乗っている共有辺」の
    中央に、幅 width で置く（射影ではなく共有辺）。
  - 寸法は実 CAD の DIMENSION エンティティ。
  - 各室面積・床面積合計は自前計算。
"""

import os
import math
import re

import ezdxf
from ezdxf.enums import TextEntityAlignment

from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union

# --------------------------------------------------------------------------
# 出力先（絶対パス・ハードコード可）
# --------------------------------------------------------------------------
OUT_DXF = "/Users/boss/dev/01_projects/big-business/cad-bench/attempts/T003/armB_ezdxf.dxf"

# --------------------------------------------------------------------------
# 通り芯
# --------------------------------------------------------------------------
X_LABELS = ["X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9", "X10", "X11"]
X_COORDS = [0, 910, 1820, 2730, 3640, 4550, 5460, 6370, 7280, 8190, 9100]
Y_LABELS = ["Y1", "Y2", "Y3", "Y4", "Y5", "Y6", "Y7", "Y8", "Y9", "Y10"]
Y_COORDS = [0, 910, 1820, 2730, 3640, 4550, 5460, 6370, 7280, 8190]

GRID = {}
for lb, co in zip(X_LABELS, X_COORDS):
    GRID[lb] = co
for lb, co in zip(Y_LABELS, Y_COORDS):
    GRID[lb] = co

_TOK = re.compile(r'^([XY]\d+)([+-]\d+)?$')


def axis(tok):
    """'X3' -> 1820, 'Y3+455' -> 2275 のように通り芯符号を座標へ解決する。"""
    m = _TOK.match(tok)
    if not m:
        raise ValueError("bad grid token: %r" % tok)
    base = GRID[m.group(1)]
    off = int(m.group(2)) if m.group(2) else 0
    return base + off


def P(pair):
    """['X3','Y3+455'] -> (x, y)"""
    return (axis(pair[0]), axis(pair[1]))


# --------------------------------------------------------------------------
# 壁定義
# --------------------------------------------------------------------------
WALL_T = 120.0
HALF = WALL_T / 2.0

# 外壁芯線（建物外周・南西の交点原点、反時計回り）
EXT_LOOP = [
    P(["X1", "Y1"]),    # (0,0)
    P(["X11", "Y1"]),   # (9100,0)
    P(["X11", "Y8"]),   # (9100,6370)
    P(["X9", "Y10"]),   # (7280,8190)  ← 45度斜め外壁 W-D の端
    P(["X1", "Y10"]),   # (0,8190)
]

# 壁 id -> (from点, to点)  ※開口の t0/t1 は from 点からの距離
WALLS = {
    "W-S": (P(["X1", "Y1"]),  P(["X11", "Y1"])),
    "W-E": (P(["X11", "Y1"]), P(["X11", "Y8"])),
    "W-D": (P(["X11", "Y8"]), P(["X9", "Y10"])),
    "W-N": (P(["X1", "Y10"]), P(["X9", "Y10"])),
    "W-W": (P(["X1", "Y1"]),  P(["X1", "Y10"])),
    "I1": (P(["X3", "Y1"]),      P(["X3", "Y6"])),
    "I2": (P(["X5", "Y1"]),      P(["X5", "Y6"])),
    "I3": (P(["X7", "Y1"]),      P(["X7", "Y6"])),
    "I4": (P(["X1", "Y3"]),      P(["X7", "Y3"])),
    "I5": (P(["X1", "Y3+455"]),  P(["X3", "Y3+455"])),
    "I6": (P(["X3", "Y4"]),      P(["X5", "Y4"])),
    "I7": (P(["X1", "Y6"]),      P(["X11", "Y6"])),
}
INTERIOR_IDS = ["I1", "I2", "I3", "I4", "I5", "I6", "I7"]

# --------------------------------------------------------------------------
# 室定義
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

ROOM_BY_NAME = {name: [P(p) for p in poly] for name, poly in ROOMS}

# --------------------------------------------------------------------------
# 開口定義
# --------------------------------------------------------------------------
OPENINGS = [
    {"id": "O1", "type": "door",   "wall": "W-S", "room": "玄関",   "width": 910},
    {"id": "O2", "type": "window", "wall": "W-S", "room": "和室",   "width": 1820},
    {"id": "O3", "type": "window", "wall": "W-E", "room": "和室",   "width": 1820},
    {"id": "O4", "type": "window", "wall": "W-D", "t0": 700, "t1": 1900},
    {"id": "O5", "type": "window", "wall": "W-N", "room": "LDK",    "width": 1820},
    {"id": "O6", "type": "door",   "wall": "I1",  "room": "玄関",   "width": 910},
    {"id": "O7", "type": "door",   "wall": "I7",  "room": "洗面脱衣", "width": 910},
    {"id": "O8", "type": "door",   "wall": "I7",  "room": "和室",   "width": 910},
]

OPENING_MARKS = {"O1": "D1", "O6": "D2", "O7": "D3", "O8": "D4",
                 "O2": "W1", "O3": "W2", "O4": "W3", "O5": "W4"}

# --------------------------------------------------------------------------
# 階段（座標は明示。導出対象外）
# --------------------------------------------------------------------------
TREADS = [
    [[3700, 260],  [4550, 260]], [[3700, 460],  [4550, 460]],
    [[3700, 660],  [4550, 660]], [[3700, 860],  [4550, 860]],
    [[3700, 1060], [4550, 1060]], [[3700, 1260], [4550, 1260]],
    [[4550, 260],  [5400, 260]], [[4550, 460],  [5400, 460]],
    [[4550, 660],  [5400, 660]], [[4550, 860],  [5400, 860]],
    [[4550, 1060], [5400, 1060]], [[4550, 1260], [5400, 1260]],
    [[3700, 1360], [5400, 1360]], [[4550, 60],   [4550, 1360]],
]
UP_TEXT_AT = [3760, 140]

# --------------------------------------------------------------------------
# 幾何ユーティリティ
# --------------------------------------------------------------------------
def unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    return (dx / L, dy / L), L


def add(a, s, u):
    return (a[0] + s * u[0], a[1] + s * u[1])


def perp(u):
    """u を +90度回転（左法線）。"""
    return (-u[1], u[0])


def dist_pt_line(p, a, u):
    """点 p の、点 a 方向 u の直線からの垂直距離。"""
    return abs((p[0] - a[0]) * u[1] - (p[1] - a[1]) * u[0])


def shared_edge_center_t(wall_from, wall_to, room_poly):
    """
    室境界のうち、その壁の芯線上に乗っている共有辺の、壁 from 点から測った
    距離範囲 [tmin, tmax] とその中央 tc を返す。
    """
    u, L = unit(wall_from, wall_to)
    ts = []
    n = len(room_poly)
    for i in range(n):
        p1 = room_poly[i]
        p2 = room_poly[(i + 1) % n]
        # 両端点が壁芯線上か（垂直距離ほぼ0）
        if dist_pt_line(p1, wall_from, u) < 1.0 and dist_pt_line(p2, wall_from, u) < 1.0:
            t1 = (p1[0] - wall_from[0]) * u[0] + (p1[1] - wall_from[1]) * u[1]
            t2 = (p2[0] - wall_from[0]) * u[0] + (p2[1] - wall_from[1]) * u[1]
            # 壁の範囲 [0,L] と重なる辺のみ採用
            lo, hi = min(t1, t2), max(t1, t2)
            if hi > 1.0 and lo < L - 1.0:
                ts += [t1, t2]
    if not ts:
        raise RuntimeError("shared edge not found")
    tmin, tmax = min(ts), max(ts)
    return tmin, tmax, (tmin + tmax) / 2.0


def resolve_openings():
    """各開口の t0/t1 と幾何情報を確定する。"""
    footprint = Polygon(EXT_LOOP)
    result = []
    for op in OPENINGS:
        wf, wt = WALLS[op["wall"]]
        u, L = unit(wf, wt)
        if "t0" in op:
            t0, t1 = float(op["t0"]), float(op["t1"])
        else:
            w = float(op["width"])
            _, _, tc = shared_edge_center_t(wf, wt, ROOM_BY_NAME[op["room"]])
            t0, t1 = tc - w / 2.0, tc + w / 2.0
        p0 = add(wf, t0, u)          # 開口 t0 側の芯上点
        p1 = add(wf, t1, u)          # 開口 t1 側の芯上点
        mid = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
        nrm = perp(u)
        # 建物内側を向く法線の符号を決定
        test = (mid[0] + 250.0 * nrm[0], mid[1] + 250.0 * nrm[1])
        s_in = 1.0 if footprint.contains(Point(test)) else -1.0
        result.append({
            "id": op["id"], "type": op["type"], "wall": op["wall"],
            "t0": t0, "t1": t1, "u": u, "nrm": nrm, "s_in": s_in,
            "p0": p0, "p1": p1, "mid": mid, "width": t1 - t0,
        })
    return result


# --------------------------------------------------------------------------
# 壁ソリッドの構築
# --------------------------------------------------------------------------
CAP_FLAT = 2
JOIN_MITRE = 2


def build_wall_solid():
    footprint = Polygon(EXT_LOOP)
    outer = footprint.buffer(HALF, join_style=JOIN_MITRE, mitre_limit=10.0)
    inner = footprint.buffer(-HALF, join_style=JOIN_MITRE, mitre_limit=10.0)
    ext_ring = outer.difference(inner)

    bars = [ext_ring]
    for wid in INTERIOR_IDS:
        a, b = WALLS[wid]
        bar = LineString([a, b]).buffer(
            HALF, cap_style=CAP_FLAT, join_style=JOIN_MITRE, mitre_limit=10.0)
        bars.append(bar)
    solid = unary_union(bars)
    return solid


def cut_openings(solid, ops):
    cuts = []
    for o in ops:
        # 芯線に沿った開口区間を、壁厚+余裕で抜く（小口＝ジャム面が残る）
        cut = LineString([o["p0"], o["p1"]]).buffer(
            HALF + 2.0, cap_style=CAP_FLAT, join_style=JOIN_MITRE, mitre_limit=10.0)
        cuts.append(cut)
    if cuts:
        solid = solid.difference(unary_union(cuts))
    return solid


# --------------------------------------------------------------------------
# 面積計算
# --------------------------------------------------------------------------
def room_area_m2(room_poly):
    return Polygon(room_poly).area / 1.0e6


# --------------------------------------------------------------------------
# DXF 構築
# --------------------------------------------------------------------------
LAYERS = {
    "GRID":    {"color": 8, "linetype": "CENTER"},
    "WALL":    {"color": 7},
    "OPENING": {"color": 3},
    "DIM":     {"color": 1},
    "ROOM":    {"color": 5},
    "TEXT":    {"color": 2},
    "STAIR":   {"color": 4},
}

DIM_OVERRIDE = {
    "dimtxt": 250,     # 文字高さ(model, 1:100で2.5mm)
    "dimasz": 150,     # 矢印
    "dimexe": 80,      # 補助線の延長
    "dimexo": 120,     # 補助線の原点オフセット
    "dimgap": 60,
    "dimtad": 1,       # 寸法線の上に文字
    "dimdec": 0,       # 小数0桁(mm)
    "dimlfac": 1.0,
    "dimscale": 1.0,
}

DIM_CHAINS = [
    {"id": "D-S2", "direction": "x", "at": 0, "base": -600,
     "stations": None, "overall": None, "overall_base": None,
     "derive_from": "W-S"},
    {"id": "D-S1", "direction": "x", "at": 0, "base": -1600,
     "stations": [0, 910, 1820, 2730, 3640, 4550, 5460, 6370, 7280, 8190, 9100],
     "overall": 9100, "overall_base": -2600},
    {"id": "D-W", "direction": "y", "at": 0, "base": -600,
     "stations": [0, 910, 1820, 2730, 3640, 4550, 5460, 6370, 7280, 8190],
     "overall": 8190, "overall_base": -1600},
    {"id": "D-E", "direction": "y", "at": 9100, "base": 9700,
     "stations": [0, 910, 1820, 2730, 3640, 4550, 5460, 6370],
     "overall": 6370, "overall_base": 10700},
]


def derive_d_s2_stations(ops):
    """D-S2: 0, W-S 上の各開口の両端, 壁 W-S の全長。"""
    wf, wt = WALLS["W-S"]
    _, L = unit(wf, wt)
    st = {0.0, L}
    for o in ops:
        if o["wall"] == "W-S":
            st.add(round(o["t0"], 6))
            st.add(round(o["t1"], 6))
    return sorted(st)


def txt(msp, s, at, h, layer, align=TextEntityAlignment.MIDDLE_CENTER,
        rot=0.0, style="ARCH"):
    t = msp.add_text(s, dxfattribs={
        "height": h, "rotation": rot, "layer": layer, "style": style})
    t.set_placement(at, align=align)
    return t


def draw_walls(msp, wall_final):
    if wall_final.geom_type == "MultiPolygon":
        geoms = list(wall_final.geoms)
    else:
        geoms = [wall_final]
    for g in geoms:
        msp.add_lwpolyline(list(g.exterior.coords), close=True,
                           dxfattribs={"layer": "WALL"})
        for ring in g.interiors:
            msp.add_lwpolyline(list(ring.coords), close=True,
                               dxfattribs={"layer": "WALL"})


def draw_opening_symbols(msp, ops):
    for o in ops:
        u = o["u"]
        nrm = o["nrm"]
        s = o["s_in"]
        p0, p1 = o["p0"], o["p1"]
        w = o["width"]
        mid = o["mid"]
        if o["type"] == "window":
            # ガラス線（壁と平行）: 両面フレーム線 + 中央ガラス線（開口幅100%）
            for off in (HALF, 0.0, -HALF):
                a = (p0[0] + off * nrm[0], p0[1] + off * nrm[1])
                b = (p1[0] + off * nrm[0], p1[1] + off * nrm[1])
                msp.add_line(a, b, dxfattribs={"layer": "OPENING"})
        else:
            # ドア: 戸(開いた位置の板) + 開き勝手の弧
            H = p0                       # 吊り元
            open_dir = (s * nrm[0], s * nrm[1])
            leaf_tip = (H[0] + w * open_dir[0], H[1] + w * open_dir[1])
            msp.add_line(H, leaf_tip, dxfattribs={"layer": "OPENING"})
            a1 = math.degrees(math.atan2(u[1], u[0]))            # 閉：壁方向
            a2 = math.degrees(math.atan2(open_dir[1], open_dir[0]))  # 開：垂直
            diff = (a2 - a1) % 360.0
            if abs(diff - 90.0) < 1.0:
                start, end = a1, a2
            else:
                start, end = a2, a1
            msp.add_arc(center=H, radius=w, start_angle=start, end_angle=end,
                        dxfattribs={"layer": "OPENING"})
        # 建具符号（開口の近く・OPENING レイヤ）
        mk = OPENING_MARKS[o["id"]]
        mpos = (mid[0] + s * 320.0 * nrm[0], mid[1] + s * 320.0 * nrm[1])
        txt(msp, mk, mpos, 250, "OPENING")


def draw_grid(msp):
    y_bot = -2900.0
    y_top = 8600.0
    x_left = -2700.0
    x_right = 9400.0
    r = 250.0
    for lb, cx in zip(X_LABELS, X_COORDS):
        msp.add_line((cx, y_bot), (cx, y_top), dxfattribs={"layer": "GRID"})
        bub = (cx, y_bot - r)
        msp.add_circle(bub, r, dxfattribs={"layer": "GRID"})
        txt(msp, lb, bub, 220, "GRID")
    for lb, cy in zip(Y_LABELS, Y_COORDS):
        msp.add_line((x_left, cy), (x_right, cy), dxfattribs={"layer": "GRID"})
        bub = (x_left - r, cy)
        msp.add_circle(bub, r, dxfattribs={"layer": "GRID"})
        txt(msp, lb, bub, 220, "GRID")


def draw_rooms(msp, areas):
    for name, poly in ROOMS:
        pts = [P(p) for p in poly]
        pg = Polygon(pts)
        c = pg.centroid
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        rh = max(ys) - min(ys)
        base = min(280.0, 0.30 * rh)
        hn = base
        ha = base * 0.8
        off = base * 0.62
        txt(msp, name, (c.x, c.y + off), hn, "ROOM")
        txt(msp, "%.2f" % areas[name], (c.x, c.y - off), ha, "ROOM")


def draw_stairs(msp):
    for a, b in TREADS:
        msp.add_line((a[0], a[1]), (b[0], b[1]), dxfattribs={"layer": "STAIR"})
    # UP 表記 + 上り方向の矢印
    txt(msp, "UP", (UP_TEXT_AT[0], UP_TEXT_AT[1]), 220, "STAIR",
        align=TextEntityAlignment.BOTTOM_LEFT)
    ax = 4120.0
    msp.add_line((ax, 360.0), (ax, 1180.0), dxfattribs={"layer": "STAIR"})
    msp.add_line((ax, 1180.0), (ax - 90.0, 1010.0), dxfattribs={"layer": "STAIR"})
    msp.add_line((ax, 1180.0), (ax + 90.0, 1010.0), dxfattribs={"layer": "STAIR"})


def draw_dims(msp, ops):
    for ch in DIM_CHAINS:
        stations = ch["stations"]
        if stations is None:
            stations = derive_d_s2_stations(ops)
        d = ch["direction"]
        at = ch["at"]
        base = ch["base"]
        angle = 0.0 if d == "x" else 90.0
        for a, b in zip(stations, stations[1:]):
            if d == "x":
                p1 = (a, at)
                p2 = (b, at)
                bpt = ((a + b) / 2.0, base)
            else:
                p1 = (at, a)
                p2 = (at, b)
                bpt = (base, (a + b) / 2.0)
            dim = msp.add_linear_dim(
                base=bpt, p1=p1, p2=p2, angle=angle,
                dimstyle="EZDXF", override=DIM_OVERRIDE,
                dxfattribs={"layer": "DIM"})
            dim.render()
        ov = ch.get("overall")
        if ov is not None:
            ob = ch["overall_base"]
            s0, s1 = stations[0], stations[-1]
            if d == "x":
                p1 = (s0, at)
                p2 = (s1, at)
                bpt = ((s0 + s1) / 2.0, ob)
            else:
                p1 = (at, s0)
                p2 = (at, s1)
                bpt = (ob, (s0 + s1) / 2.0)
            dim = msp.add_linear_dim(
                base=bpt, p1=p1, p2=p2, angle=angle,
                dimstyle="EZDXF", override=DIM_OVERRIDE,
                dxfattribs={"layer": "DIM"})
            dim.render()


# --------------------------------------------------------------------------
# メイン
# --------------------------------------------------------------------------
def main():
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4      # mm
    doc.header["$MEASUREMENT"] = 1   # metric
    doc.header["$LTSCALE"] = 25.0
    msp = doc.modelspace()

    # レイヤ
    for name, attr in LAYERS.items():
        dxfattribs = {"color": attr["color"]}
        if "linetype" in attr:
            dxfattribs["linetype"] = attr["linetype"]
        doc.layers.new(name, dxfattribs=dxfattribs)

    # 文字スタイル（CJK フォント参照。読めない環境では代替される）
    if "ARCH" not in doc.styles:
        doc.styles.new("ARCH", dxfattribs={"font": "msgothic.ttc"})

    # 開口を確定
    ops = resolve_openings()

    # 壁ソリッド → 開口で抜く → 外形線を描く
    solid = build_wall_solid()
    wall_final = cut_openings(solid, ops)
    draw_walls(msp, wall_final)

    # 開口シンボル + 建具符号
    draw_opening_symbols(msp, ops)

    # 通り芯 + 符号
    draw_grid(msp)

    # 室名 + 面積
    areas = {name: round(room_area_m2([P(p) for p in poly]), 2)
             for name, poly in ROOMS}
    draw_rooms(msp, areas)

    # 床面積合計（TEXT レイヤ）
    total = round(sum(room_area_m2([P(p) for p in poly]) for _, poly in ROOMS), 2)
    txt(msp, "%.2f" % total, (4550.0, -4200.0), 300, "TEXT")

    # 階段
    draw_stairs(msp)

    # 寸法（DIMENSION）
    draw_dims(msp, ops)

    doc.saveas(OUT_DXF)


if __name__ == "__main__":
    main()

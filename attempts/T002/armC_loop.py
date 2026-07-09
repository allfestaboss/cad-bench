#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T002 : 木造2階建て 1階平面図（作図のみ）
armC_loop : 検証ループ版

方針:
- 壁は「壁芯を±60でオフセットした帯」を shapely で構築 -> unary_union -> 開口を difference
  -> できたポリゴンの境界線(外殻+室の穴)を WALL レイヤに作図。
  これにより T字接合は自動でトリムされ、開口部は壁が欠き込まれる。
- 開口記号(ドア=戸+開き弧 / 窓=ガラス2本線)は OPENING レイヤに別途作図。
- 寸法は実 DIMENSION エンティティ(add_linear_dim)で 4系統38本。
"""

import math
import ezdxf
from ezdxf.enums import TextEntityAlignment
from shapely.geometry import Polygon, LineString, MultiPolygon
from shapely.ops import unary_union
from shapely.geometry.polygon import orient

OUT = "/Users/boss/dev/01_projects/big-business/cad-bench/attempts/T002/armC_loop.dxf"
PNG = "/Users/boss/dev/01_projects/big-business/cad-bench/attempts/T002/armC_loop.png"

T = 120.0            # 壁厚
H = T / 2.0          # 60 芯振り分け
OVERCUT = 80.0       # 開口を壁厚方向に貫通させるための余裕(壁面より外へは無害)

# ---------- spec データ ----------
GX = {"X1":0,"X2":910,"X3":1820,"X4":2730,"X5":3640,"X6":4550,
      "X7":5460,"X8":6370,"X9":7280,"X10":8190,"X11":9100}
GY = {"Y1":0,"Y2":910,"Y3":1820,"Y4":2730,"Y5":3640,"Y6":4550,
      "Y7":5460,"Y8":6370,"Y9":7280,"Y10":8190}

EXT_CENTER = [(0,0),(9100,0),(9100,6370),(7280,8190),(0,8190)]  # 外周壁芯 閉ポリゴン

INTERIOR_WALLS = {
    "I1": ((1820,0),(1820,4550)),
    "I2": ((3640,0),(3640,4550)),
    "I3": ((5460,0),(5460,4550)),
    "I4": ((0,1820),(5460,1820)),
    "I5": ((0,2275),(1820,2275)),
    "I6": ((1820,2730),(3640,2730)),
    "I7": ((0,4550),(9100,4550)),
}

# 外周壁: 開口の t 座標計算のための from/to (順序が spec 準拠)
EXT_WALL_SEG = {
    "W-S": ((0,0),(9100,0)),
    "W-E": ((9100,0),(9100,6370)),
    "W-D": ((9100,6370),(7280,8190)),
    "W-N": ((0,8190),(7280,8190)),
    "W-W": ((0,0),(0,8190)),
}

ROOMS = [
    ("玄関",     [(0,0),(1820,0),(1820,1820),(0,1820)]),
    ("収納",     [(0,1820),(1820,1820),(1820,2275),(0,2275)]),
    ("洗面脱衣", [(0,2275),(1820,2275),(1820,4550),(0,4550)]),
    ("ホール",   [(1820,0),(3640,0),(3640,1820),(1820,1820)]),
    ("便所",     [(1820,1820),(3640,1820),(3640,2730),(1820,2730)]),
    ("浴室",     [(1820,2730),(3640,2730),(3640,4550),(1820,4550)]),
    ("階段",     [(3640,0),(5460,0),(5460,1820),(3640,1820)]),
    ("納戸",     [(3640,1820),(5460,1820),(5460,4550),(3640,4550)]),
    ("和室",     [(5460,0),(9100,0),(9100,4550),(5460,4550)]),
    ("LDK",      [(0,4550),(9100,4550),(9100,6370),(7280,8190),(0,8190)]),
]

# openings: (id, type, wall, t0, t1)
OPENINGS = [
    ("O1","door","W-S",455,1365),
    ("O2","window","W-S",6370,8190),
    ("O3","window","W-E",1820,3640),
    ("O4","window","W-D",700,1900),
    ("O5","window","W-N",2730,4550),
    ("O6","door","I1",455,1365),
    ("O7","door","I7",455,1365),
    ("O8","door","I7",6370,7280),
]

# ドアの向き: hinge=t0側 or t1側,  swing_sign = 開く側(法線符号: +1 = rot90ccw方向, -1 = 反対)
DOOR_CFG = {
    "O1": {"hinge":"t0","swing":+1},   # 玄関へ(+y)  wall +x, ccw法線=+y
    "O6": {"hinge":"t0","swing":-1},   # I1縦 上向きu(+y), -1=+x = ホール側へ開く
    "O7": {"hinge":"t0","swing":-1},   # I7横 +x, -1=-y = 洗面脱衣側へ開く
    "O8": {"hinge":"t0","swing":-1},   # I7横 +x, -1=-y = 和室側へ開く
}

STAIR_TREADS = [
    [(3700,260),(4550,260)],[(3700,460),(4550,460)],[(3700,660),(4550,660)],
    [(3700,860),(4550,860)],[(3700,1060),(4550,1060)],[(3700,1260),(4550,1260)],
    [(4550,260),(5400,260)],[(4550,460),(5400,460)],[(4550,660),(5400,660)],
    [(4550,860),(5400,860)],[(4550,1060),(5400,1060)],[(4550,1260),(5400,1260)],
    [(3700,1360),(5400,1360)],[(4550,60),(4550,1360)],
]
UP_AT = (3760,140)

DIM_CHAINS = [
    {"id":"D-S","dir":"x","at":0,   "st":[0,910,1820,2730,3640,4550,5460,6370,7280,8190,9100],"overall":9100,"base":-600, "obase":-1600},
    {"id":"D-W","dir":"y","at":0,   "st":[0,910,1820,2730,3640,4550,5460,6370,7280,8190],       "overall":8190,"base":-600, "obase":-1600},
    {"id":"D-E","dir":"y","at":9100,"st":[0,910,1820,2730,3640,4550,5460,6370],                  "overall":6370,"base":9700, "obase":10700},
    {"id":"D-N","dir":"x","at":8190,"st":[0,910,1820,2730,3640,4550,5460,6370,7280],             "overall":7280,"base":8790, "obase":9790},
]

# ---------- ベクトル小道具 ----------
def unit(a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    L=math.hypot(dx,dy)
    return (dx/L,dy/L),L
def rot90ccw(u): return (-u[1],u[0])
def add(p,v,s=1.0): return (p[0]+v[0]*s,p[1]+v[1]*s)

def wall_rect(a,b):
    """壁芯 a-b を ±H でオフセットした矩形(端は芯端まで)"""
    u,_=unit(a,b); n=rot90ccw(u)
    return Polygon([add(a,n,H),add(b,n,H),add(b,n,-H),add(a,n,-H)])

def opening_cut(a,b,t0,t1):
    """壁芯 a-b の from(a) から距離 t0..t1, 壁厚方向は貫通(OVERCUT)"""
    u,_=unit(a,b); n=rot90ccw(u)
    p0=add(a,u,t0); p1=add(a,u,t1)
    return Polygon([add(p0,n,OVERCUT),add(p1,n,OVERCUT),
                    add(p1,n,-OVERCUT),add(p0,n,-OVERCUT)])

def opening_points(wall_id,t0,t1):
    """開口の中心線 P0,P1 と (u,n) を返す"""
    if wall_id in EXT_WALL_SEG:
        a,b=EXT_WALL_SEG[wall_id]
    else:
        a,b=INTERIOR_WALLS[wall_id]
    u,_=unit(a,b); n=rot90ccw(u)
    return add(a,u,t0),add(a,u,t1),u,n,a,b

# ================= DXF 構築 =================
doc=ezdxf.new("R2010",setup=True)
doc.header["$LTSCALE"]=25       # 1:100 で通り芯の破線が読める
doc.header["$INSUNITS"]=4       # mm
doc.header["$MEASUREMENT"]=1    # metric
msp=doc.modelspace()

# レイヤ
LAYER_DEF={
    "GRID":  {"color":8, "ltype":"CENTER"},
    "WALL":  {"color":7},
    "OPENING":{"color":3},
    "DIM":   {"color":1},
    "ROOM":  {"color":5},
    "TEXT":  {"color":7},
    "STAIR": {"color":4},
}
for name,cfg in LAYER_DEF.items():
    lay=doc.layers.add(name,color=cfg["color"])
    if cfg.get("ltype"): lay.dxf.linetype=cfg["ltype"]

# テキストスタイル(日本語)
if "JP" not in doc.styles:
    try:
        doc.styles.add("JP",font="msgothic.ttf")
    except Exception:
        doc.styles.add("JP")

# 寸法スタイル
if "PLAN" in doc.dimstyles: doc.dimstyles.remove("PLAN")
ds=doc.dimstyles.add("PLAN")
ds.dxf.dimtxt=2.5      # 文字高(×dimscale)
ds.dxf.dimasz=2.0      # 矢印
ds.dxf.dimexe=1.0
ds.dxf.dimexo=0.6
ds.dxf.dimgap=0.8
ds.dxf.dimscale=100.0  # 1:100 -> 図面上で読める大きさに
ds.dxf.dimlfac=1.0     # 表示値=実寸(mm)
ds.dxf.dimdec=0
ds.dxf.dimtad=1        # 寸法線上に文字
ds.dxf.dimtxsty="JP"
ds.dxf.dimclrt=1

# ---------- 壁 ----------
wall_polys=[wall_rect(*EXT_WALL_SEG["W-S"])]  # placeholder, rebuild below properly
wall_polys=[]
# 外周: 芯ポリゴンを ±H オフセットしてリング
cl=Polygon(EXT_CENTER)
outer=cl.buffer(H, join_style=2, mitre_limit=10)
inner=cl.buffer(-H, join_style=2, mitre_limit=10)
ext_ring=outer.difference(inner)
wall_polys.append(ext_ring)
# 内壁
for wid,(a,b) in INTERIOR_WALLS.items():
    wall_polys.append(wall_rect(a,b))

assembly=unary_union(wall_polys)

# 開口を差し引く
cuts=[]
for oid,otype,wid,t0,t1 in OPENINGS:
    if wid in EXT_WALL_SEG:
        a,b=EXT_WALL_SEG[wid]
    else:
        a,b=INTERIOR_WALLS[wid]
    cuts.append(opening_cut(a,b,t0,t1))
assembly=assembly.difference(unary_union(cuts))

def iter_polys(geom):
    if isinstance(geom,MultiPolygon):
        for g in geom.geoms: yield orient(g,1.0)   # 外周CCW / 穴CW に正規化
    elif isinstance(geom,Polygon):
        yield orient(geom,1.0)

# 壁ポシェ(薄いソリッドハッチ) : 各ポリゴンごとに個別ハッチ(穴を確実に抜く)
for poly in iter_polys(assembly):
    hatch=msp.add_hatch(dxfattribs={"layer":"WALL"})
    hatch.rgb=(205,205,205)
    hatch.set_solid_fill()
    hatch.dxf.hatch_style=ezdxf.const.HATCH_STYLE_NESTED
    hatch.paths.add_polyline_path(list(poly.exterior.coords),is_closed=True,
                                  flags=ezdxf.const.BOUNDARY_PATH_EXTERNAL)
    for ring in poly.interiors:
        hatch.paths.add_polyline_path(list(ring.coords),is_closed=True,
                                      flags=ezdxf.const.BOUNDARY_PATH_DEFAULT)

# WALL 境界線(ハッチの上に黒で)
for poly in iter_polys(assembly):
    msp.add_lwpolyline(list(poly.exterior.coords),
                       dxfattribs={"layer":"WALL","lineweight":35},close=True)
    for ring in poly.interiors:
        msp.add_lwpolyline(list(ring.coords),
                           dxfattribs={"layer":"WALL","lineweight":35},close=True)

# ---------- 開口記号 ----------
def draw_door(oid,wid,t0,t1):
    P0,P1,u,n,a,b=opening_points(wid,t0,t1)
    w=t1-t0
    cfg=DOOR_CFG[oid]
    if cfg["hinge"]=="t0":
        hinge=P0; along=u          # along = hinge->反対ジャンブ方向
    else:
        hinge=P1; along=(-u[0],-u[1])
    swing = n if cfg["swing"]>0 else (-n[0],-n[1])
    tip=add(hinge,swing,w)         # 開いた戸先
    # 戸(葉)
    msp.add_line(hinge,tip,dxfattribs={"layer":"OPENING"})
    # 開き弧: along方向(閉)から swing方向(開)まで90度
    a_al=math.degrees(math.atan2(along[1],along[0]))%360
    a_sw=math.degrees(math.atan2(swing[1],swing[0]))%360
    d=(a_sw-a_al)%360
    if abs(d-90)<1: sa,ea=a_al,a_sw
    else:           sa,ea=a_sw,a_al
    msp.add_arc(center=hinge,radius=w,start_angle=sa,end_angle=ea,
                dxfattribs={"layer":"OPENING"})

def draw_window(wid,t0,t1):
    P0,P1,u,n,a,b=opening_points(wid,t0,t1)
    for off in (30,-30):
        s=add(P0,n,off); e=add(P1,n,off)
        msp.add_line(s,e,dxfattribs={"layer":"OPENING"})

for oid,otype,wid,t0,t1 in OPENINGS:
    if otype=="door": draw_door(oid,wid,t0,t1)
    else:             draw_window(wid,t0,t1)

# ---------- 階段 ----------
for s,e in STAIR_TREADS:
    msp.add_line(s,e,dxfattribs={"layer":"STAIR"})
msp.add_text("UP",dxfattribs={"layer":"STAIR","height":180,"style":"JP"}).set_placement(
    UP_AT,align=TextEntityAlignment.LEFT)

# ---------- 通り芯 + 符号 ----------
GBUB=300
X_BUB_Y=-2900
Y_BUB_X=-2900
for lbl,x in GX.items():
    msp.add_line((x,X_BUB_Y+GBUB),(x,8290),dxfattribs={"layer":"GRID"})
    msp.add_circle((x,X_BUB_Y),GBUB,dxfattribs={"layer":"GRID"})
    msp.add_text(lbl,dxfattribs={"layer":"GRID","height":220,"style":"JP"}).set_placement(
        (x,X_BUB_Y),align=TextEntityAlignment.MIDDLE_CENTER)
for lbl,y in GY.items():
    msp.add_line((Y_BUB_X+GBUB,y),(9200,y),dxfattribs={"layer":"GRID"})
    msp.add_circle((Y_BUB_X,y),GBUB,dxfattribs={"layer":"GRID"})
    msp.add_text(lbl,dxfattribs={"layer":"GRID","height":220,"style":"JP"}).set_placement(
        (Y_BUB_X,y),align=TextEntityAlignment.MIDDLE_CENTER)

# ---------- 室名 ----------
ROOM_LABEL_OVERRIDE={"階段":(4550,1600)}  # 段板を避ける
for name,poly in ROOMS:
    if name in ROOM_LABEL_OVERRIDE:
        px,py=ROOM_LABEL_OVERRIDE[name]
    else:
        p=Polygon(poly).representative_point(); px,py=p.x,p.y
    msp.add_text(name,dxfattribs={"layer":"ROOM","height":260,"style":"JP"}).set_placement(
        (px,py),align=TextEntityAlignment.MIDDLE_CENTER)

# ---------- 寸法 ----------
def linear(p1,p2,base,ang):
    dim=msp.add_linear_dim(base=base,p1=p1,p2=p2,angle=ang,
                           dimstyle="PLAN",dxfattribs={"layer":"DIM"})
    dim.render()

for ch in DIM_CHAINS:
    st=ch["st"]; at=ch["at"]
    if ch["dir"]=="x":
        ang=0
        for i in range(len(st)-1):
            linear((st[i],at),(st[i+1],at),(0,ch["base"]),ang)
        linear((st[0],at),(st[-1],at),(0,ch["obase"]),ang)
    else:
        ang=90
        for i in range(len(st)-1):
            linear((at,st[i]),(at,st[i+1]),(ch["base"],0),ang)
        linear((at,st[0]),(at,st[-1]),(ch["obase"],0),ang)

# ---------- タイトル(TEXTレイヤ) ----------
msp.add_text("木造2階建て 1階平面図",dxfattribs={"layer":"TEXT","height":400,"style":"JP"}).set_placement(
    (0,-4200),align=TextEntityAlignment.LEFT)
msp.add_text("S=1:100  単位:mm",dxfattribs={"layer":"TEXT","height":260,"style":"JP"}).set_placement(
    (0,-4900),align=TextEntityAlignment.LEFT)

doc.saveas(OUT)
print("saved",OUT)

# ================= 自己検証 =================
print("\n=== geometry self-check ===")
# 1) 壁厚: 各壁芯中点で ±(H-1) は壁内, ±(H+2) は壁外
def check_thickness(a,b,label):
    u,_=unit(a,b); n=rot90ccw(u)
    mid=((a[0]+b[0])/2,(a[1]+b[1])/2)
    from shapely.geometry import Point
    inside_ok = assembly.contains(Point(add(mid,n,H-2))) and assembly.contains(Point(add(mid,n,-(H-2))))
    outside_ok = (not assembly.contains(Point(add(mid,n,H+3)))) and (not assembly.contains(Point(add(mid,n,-(H+3)))))
    print(f"  {label:5s} thickness inside={inside_ok} outside={outside_ok}")
for wid,(a,b) in EXT_WALL_SEG.items(): check_thickness(a,b,wid)
for wid,(a,b) in INTERIOR_WALLS.items(): check_thickness(a,b,wid)

# 2) 開口: 開口中央で壁芯上に壁が無い(欠き込み確認)
from shapely.geometry import Point
print("  -- openings notched? --")
for oid,otype,wid,t0,t1 in OPENINGS:
    P0,P1,u,n,a,b=opening_points(wid,(t0+t1)/2,(t0+t1)/2)
    center=P0
    notched = not assembly.contains(Point(center))
    print(f"  {oid} {wid} notched={notched}")

# 3) 寸法エンティティ数
dims=[e for e in msp if e.dxftype()=="DIMENSION"]
print(f"  DIMENSION count = {len(dims)} (expect 38)")

# ================= レンダリング =================
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.family"]=["Hiragino Sans","AppleGothic","sans-serif"]
import matplotlib.pyplot as plt
from ezdxf.addons.drawing import RenderContext,Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

def render(path,xlim=None,ylim=None,figsize=(16,16),dpi=150):
    fig=plt.figure(figsize=figsize)
    ax=fig.add_axes([0,0,1,1])
    ctx=RenderContext(doc)
    Frontend(ctx,MatplotlibBackend(ax)).draw_layout(msp,finalize=True)
    ax.set_axis_off()
    if xlim: ax.set_xlim(*xlim)
    if ylim: ax.set_ylim(*ylim)
    fig.savefig(path,dpi=dpi,facecolor="white")
    plt.close(fig)
    print("rendered",path)

render(PNG)
render(PNG.replace(".png","_ne.png"),xlim=(6000,9600),ylim=(5500,8600),figsize=(10,10))  # 斜め壁NE
render(PNG.replace(".png","_sw.png"),xlim=(-500,4000),ylim=(-500,3200),figsize=(10,8))   # 玄関/T字/I5
render(PNG.replace(".png","_stair.png"),xlim=(3400,5700),ylim=(-200,2100),figsize=(9,9)) # 階段
render(PNG.replace(".png","_tee.png"),xlim=(1550,2100),ylim=(1600,3000),figsize=(6,10)) # I5→I1 T字

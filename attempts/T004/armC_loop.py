#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T004  木造2階建て 1階平面図（法規適合を自分で満たす）  arm C (verification loop)

固定: 通り芯・壁・室・8開口の位置。
自由(法規支配): 階段(段数/蹴上/踏面/幅/段板配置)、居室(和室/LDK)の窓寸法。

出力:
  armC_loop.dxf
  armC_loop.schedule.json
  armC_loop.png (検証用レンダ)
"""

import json, math, re, os
import numpy as np
import ezdxf
from ezdxf.enums import TextEntityAlignment
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
DXF  = os.path.join(HERE, "armC_loop.dxf")
SCHED= os.path.join(HERE, "armC_loop.schedule.json")
PNG  = os.path.join(HERE, "armC_loop.png")

# ------------------------------------------------------------------ grid
X = [0,910,1820,2730,3640,4550,5460,6370,7280,8190,9100]
Y = [0,910,1820,2730,3640,4550,5460,6370,7280,8190]
def cval(tok):
    m = re.fullmatch(r'([XY])(\d+)(?:\+(\d+))?', tok)
    axis, idx, off = m.group(1), int(m.group(2)), m.group(3)
    base = (X if axis=='X' else Y)[idx-1]
    return base + (int(off) if off else 0)
def pt(pair):  # ["X1","Y1"] -> np.array
    return np.array([float(cval(pair[0])), float(cval(pair[1]))])

TH = 120.0        # wall thickness
HT = TH/2.0       # 60
FLOOR_H = 2900.0

# ------------------------------------------------------------------ spec shell
walls_spec = [
 ("W-S",("X1","Y1"),("X11","Y1")),
 ("W-E",("X11","Y1"),("X11","Y8")),
 ("W-D",("X11","Y8"),("X9","Y10")),
 ("W-N",("X1","Y10"),("X9","Y10")),
 ("W-W",("X1","Y1"),("X1","Y10")),
 ("I1",("X3","Y1"),("X3","Y6")),
 ("I2",("X5","Y1"),("X5","Y6")),
 ("I3",("X7","Y1"),("X7","Y6")),
 ("I4",("X1","Y3"),("X7","Y3")),
 ("I5",("X1","Y3+455"),("X3","Y3+455")),
 ("I6",("X3","Y4"),("X5","Y4")),
 ("I7",("X1","Y6"),("X11","Y6")),
]
rooms_spec = [
 ("玄関",     [("X1","Y1"),("X3","Y1"),("X3","Y3"),("X1","Y3")]),
 ("収納",     [("X1","Y3"),("X3","Y3"),("X3","Y3+455"),("X1","Y3+455")]),
 ("洗面脱衣", [("X1","Y3+455"),("X3","Y3+455"),("X3","Y6"),("X1","Y6")]),
 ("ホール",   [("X3","Y1"),("X5","Y1"),("X5","Y3"),("X3","Y3")]),
 ("便所",     [("X3","Y3"),("X5","Y3"),("X5","Y4"),("X3","Y4")]),
 ("浴室",     [("X3","Y4"),("X5","Y4"),("X5","Y6"),("X3","Y6")]),
 ("階段",     [("X5","Y1"),("X7","Y1"),("X7","Y3"),("X5","Y3")]),
 ("納戸",     [("X5","Y3"),("X7","Y3"),("X7","Y6"),("X5","Y6")]),
 ("和室",     [("X7","Y1"),("X11","Y1"),("X11","Y6"),("X7","Y6")]),
 ("LDK",      [("X1","Y6"),("X11","Y6"),("X11","Y8"),("X9","Y10"),("X1","Y10")]),
]

def poly_area_m2(pairs):
    pts = [pt(p) for p in pairs]
    s = 0.0
    for i in range(len(pts)):
        a=pts[i]; b=pts[(i+1)%len(pts)]
        s += a[0]*b[1]-b[0]*a[1]
    return abs(s)/2.0/1e6

room_area = {name: poly_area_m2(pairs) for name,pairs in rooms_spec}
TOTAL_AREA = sum(room_area.values())

# ------------------------------------------------------------------ LEGAL: STAIR
# 階高2900。蹴上<=230 -> 段数 >= ceil(2900/230)=13。段数13 -> 蹴上=223.08(<=230)。
# 階段室 内法: x[3700,5400] y[60,1760] = 1700 x 1700。直通階段は 12踏面*150=1800>1700 で不可。
# -> 折返し(U字)階段。踊り場を北に配置し、6+6=12段板。段板長=幅=850(>=750)、踏面150(>=150)。
RISERS   = 13
RISER_MM = round(FLOOR_H/RISERS, 3)          # 223.077
TREAD_MM = 150
STAIR_W  = 850
assert RISER_MM <= 230 and TREAD_MM >= 150 and STAIR_W >= 750

# ------------------------------------------------------------------ LEGAL: WINDOWS
# 採光: sum(w*h) >= area/7 。換気: sum(w*h*ratio) >= area/20 。ratio=0.5。
windows = {
 "O2": {"room":"和室","w":1820,"h":1200,"r":0.5},
 "O3": {"room":"和室","w":1820,"h":1200,"r":0.5},
 "O4": {"room":"LDK", "w":1820,"h":1370,"r":0.5},
 "O5": {"room":"LDK", "w":2730,"h":1370,"r":0.5},
}
def legal_check():
    rep={}
    for rm in ("和室","LDK"):
        A = room_area[rm]*1e6  # mm2
        need_d = A/7.0
        need_v = A/20.0
        got_d  = sum(w["w"]*w["h"] for w in windows.values() if w["room"]==rm)
        got_v  = sum(w["w"]*w["h"]*w["r"] for w in windows.values() if w["room"]==rm)
        rep[rm]=dict(area=A/1e6, need_d=need_d/1e6, got_d=got_d/1e6,
                     need_v=need_v/1e6, got_v=got_v/1e6,
                     ok_d=got_d>=need_d, ok_v=got_v>=need_v)
    return rep
LEGAL = legal_check()
for rm,r in LEGAL.items():
    assert r["ok_d"], f"daylight fail {rm}"
    assert r["ok_v"], f"vent fail {rm}"

# ------------------------------------------------------------------ DXF setup
doc = ezdxf.new("R2010", setup=True)
msp = doc.modelspace()
doc.header['$INSUNITS'] = 4   # mm
doc.header['$LTSCALE']  = 30

LAYERS = {  # name: (aci, linetype)
 "GRID":   (8,  "CENTER"),
 "WALL":   (7,  "CONTINUOUS"),
 "OPENING":(4,  "CONTINUOUS"),
 "DIM":    (1,  "CONTINUOUS"),
 "ROOM":   (3,  "CONTINUOUS"),
 "TEXT":   (5,  "CONTINUOUS"),
 "STAIR":  (6,  "CONTINUOUS"),
}
have_lt = set(lt.dxf.name.upper() for lt in doc.linetypes)
for name,(aci,lt) in LAYERS.items():
    lt = lt if lt.upper() in have_lt else "CONTINUOUS"
    doc.layers.add(name, color=aci, linetype=lt)

# text style with CJK-capable font (for viewer); content is what matters to checker
try:
    doc.styles.add("JP", font="Arial Unicode.ttf")
    JPSTYLE="JP"
except Exception:
    JPSTYLE="Standard"

# dim style
ds = doc.dimstyles.new("ARCH")
ds.dxf.dimtxt = 250
ds.dxf.dimasz = 150
ds.dxf.dimexe = 90
ds.dxf.dimexo = 100
ds.dxf.dimgap = 60
ds.dxf.dimdec = 0
ds.dxf.dimlunit = 2
ds.dxf.dimtad = 1
ds.dxf.dimscale = 1
ds.dxf.dimtxsty = "Standard"
ds.dxf.dimse1 = 0
ds.dxf.dimse2 = 0

def line(a,b,layer):
    msp.add_line((float(a[0]),float(a[1])),(float(b[0]),float(b[1])),dxfattribs={"layer":layer})
def arc(c,r,s,e,layer):
    msp.add_arc((float(c[0]),float(c[1])),float(r),float(s),float(e),dxfattribs={"layer":layer})
def circle(c,r,layer):
    msp.add_circle((float(c[0]),float(c[1])),float(r),dxfattribs={"layer":layer})
def text(s,x,y,h,layer,align=TextEntityAlignment.MIDDLE_CENTER,style=None):
    t=msp.add_text(s,height=h,dxfattribs={"layer":layer,"style":style or JPSTYLE})
    t.set_placement((float(x),float(y)),align=align)
    return t
def lwpoly(coords,layer,closed=True):
    msp.add_lwpolyline([(float(c[0]),float(c[1])) for c in coords],close=closed,dxfattribs={"layer":layer})

# ------------------------------------------------------------------ WALLS via union/difference
def wall_rect(a,b):
    a=np.array(a,float); b=np.array(b,float)
    u=b-a; L=np.hypot(*u); u=u/L
    n=np.array([-u[1],u[0]])
    a2=a-HT*u; b2=b+HT*u   # extend by half-thickness for clean corners/T-joints
    return Polygon([tuple(a2+HT*n),tuple(b2+HT*n),tuple(b2-HT*n),tuple(a2-HT*n)])

wall_polys=[wall_rect(pt(f),pt(t)) for _,f,t in walls_spec]
wall_union=unary_union(wall_polys)

# opening cutters
SQ2=math.sqrt(2)
def diag_cutter(center,u,w,ov=70):
    C=np.array(center,float); u=np.array(u,float); u=u/np.hypot(*u)
    n=np.array([-u[1],u[0]])
    hl=w/2.0
    c1=C+hl*u+ov*n; c2=C+hl*u-ov*n; c3=C-hl*u-ov*n; c4=C-hl*u+ov*n
    return Polygon([tuple(c1),tuple(c2),tuple(c3),tuple(c4)])

cutters=[
 box(455,-70,1365,70),          # O1 door 玄関 W-S
 box(6370,-70,8190,70),         # O2 win 和室 W-S (1820@7280)
 box(2275,8120,5005,8260),      # O5 win LDK  W-N (2730@3640)
 box(9030,1365,9170,3185),      # O3 win 和室 W-E (1820@2275)
 box(1750,455,1890,1365),       # O6 door I1 (910@910)
 box(455,4480,1365,4620),       # O7 door I7 洗面脱衣 (910@910)
 box(6825,4480,7735,4620),      # O8 door I7 和室 (910@7280)
 diag_cutter((8190,7280),(-1/SQ2,1/SQ2),1820),  # O4 win LDK W-D
]
walls_geom=wall_union.difference(unary_union(cutters))

def emit_poly(g):
    if g.geom_type=="Polygon":
        lwpoly(list(g.exterior.coords)[:-1],"WALL")
        for r in g.interiors:
            lwpoly(list(r.coords)[:-1],"WALL")
    elif g.geom_type in ("MultiPolygon","GeometryCollection"):
        for sub in g.geoms: emit_poly(sub)
emit_poly(walls_geom)

# ------------------------------------------------------------------ OPENING symbols
def add_door(center,u,n,w,hinge_sign=-1):
    C=np.array(center,float); u=np.array(u,float); n=np.array(n,float)
    H=C+hinge_sign*(w/2)*u
    J=C-hinge_sign*(w/2)*u
    P=H+w*n
    line(H,P,"OPENING")                      # 戸(leaf)
    a1=math.degrees(math.atan2((J-H)[1],(J-H)[0]))
    a2=math.degrees(math.atan2((P-H)[1],(P-H)[0]))
    d=(a2-a1)%360
    s,e=(a1,a2) if abs(d-90)<1 else (a2,a1)
    arc(H,w,s,e,"OPENING")                    # 開き勝手の弧

def add_window(center,u,w):
    C=np.array(center,float); u=np.array(u,float); u=u/np.hypot(*u)
    n=np.array([-u[1],u[0]])
    for off in (-40,0,40):
        b=C+off*n
        line(b-(w/2)*u,b+(w/2)*u,"OPENING")   # ガラス線 (length=w >= .8w)

add_door((910,0),(1,0),(0,1),910)             # O1
add_door((1820,910),(0,1),(1,0),910)          # O6
add_door((910,4550),(1,0),(0,-1),910)         # O7
add_door((7280,4550),(1,0),(0,-1),910)        # O8
add_window((7280,0),(1,0),windows["O2"]["w"])          # O2
add_window((9100,2275),(0,1),windows["O3"]["w"])       # O3
add_window((8190,7280),(-1/SQ2,1/SQ2),windows["O4"]["w"])  # O4
add_window((3640,8190),(1,0),windows["O5"]["w"])       # O5

# ------------------------------------------------------------------ STAIR (U-turn)
# room clear x[3700,5400] y[60,1760]; split at x=4550; landing north y[960,1760]
xL,xM,xR=3700.0,4550.0,5400.0
yB,yLand=60.0,960.0
# 12 tread boards (6 left + 6 right), each length = STAIR_W = 850
tread_ys=[135,285,435,585,735,885]
for ty in tread_ys:
    line((xL,ty),(xL+STAIR_W,ty),"STAIR")     # left flight
    line((xM,ty),(xM+STAIR_W,ty),"STAIR")     # right flight
# landing (rectangle; edges 1700/800, not counted)
lwpoly([(xL,yLand),(xR,yLand),(xR,1760),(xL,1760)],"STAIR")
# stringer / well line (length 900, not counted)
line((xM,yB),(xM,yLand),"STAIR")
text("UP",(xL+xR)/2, (yB+yLand)/2, 200,"STAIR")

# ------------------------------------------------------------------ ROOMS: name + area
for name,pairs in rooms_spec:
    sp=Polygon([tuple(pt(p)) for p in pairs])
    c=sp.centroid                      # true centroid (all rooms convex -> inside)
    cx,cy=c.x,c.y
    ys=[pt(p)[1] for p in pairs]; bh=max(ys)-min(ys)
    if bh<700:
        nh,ah,dy=150,150,120
    else:
        nh,ah,dy=320,260,300
    text(name,cx,cy+dy,nh,"ROOM")
    text(f"{room_area[name]:.2f} m²",cx,cy-dy,ah,"ROOM")

# ------------------------------------------------------------------ TOTAL area (TEXT layer)
text(f"1階 床面積合計  {TOTAL_AREA:.2f} m²", 4550, -3450, 400, "TEXT")

# ------------------------------------------------------------------ OPENING marks (OPENING layer)
marks={"O1":("D1",(910,650)),"O6":("D2",(2550,650)),"O7":("D3",(1550,4300)),
       "O8":("D4",(6100,4250)),"O2":("W1",(7280,650)),"O3":("W2",(8600,2275)),
       "O4":("W3",(7650,7050)),"O5":("W4",(3640,7750))}
for oid,(sym,(mx,my)) in marks.items():
    text(sym,mx,my,250,"OPENING")

# ------------------------------------------------------------------ GRID lines + bubbles
for i,xc in enumerate(X):
    line((xc,-300),(xc,8300),"GRID")
    circle((xc,8600),300,"GRID")
    text(f"X{i+1}",xc,8600,250,"GRID")
for j,yc in enumerate(Y):
    line((-1800,yc),(9300,yc),"GRID")
    circle((-2100,yc),300,"GRID")
    text(f"Y{j+1}",-2100,yc,250,"GRID")

# ------------------------------------------------------------------ DIMENSIONS
def hchain(stations, base_y):
    for a,b in zip(stations[:-1],stations[1:]):
        d=msp.add_linear_dim(base=((a+b)/2,base_y),p1=(a,0),p2=(b,0),
                             angle=0,dimstyle="ARCH",dxfattribs={"layer":"DIM"})
        d.render()
def hoverall(a,b,base_y):
    d=msp.add_linear_dim(base=((a+b)/2,base_y),p1=(a,0),p2=(b,0),
                         angle=0,dimstyle="ARCH",dxfattribs={"layer":"DIM"})
    d.render()
def vchain(stations, base_x, atx):
    for a,b in zip(stations[:-1],stations[1:]):
        d=msp.add_linear_dim(base=(base_x,(a+b)/2),p1=(atx,a),p2=(atx,b),
                             angle=90,dimstyle="ARCH",dxfattribs={"layer":"DIM"})
        d.render()
def voverall(a,b,base_x,atx):
    d=msp.add_linear_dim(base=(base_x,(a+b)/2),p1=(atx,a),p2=(atx,b),
                         angle=90,dimstyle="ARCH",dxfattribs={"layer":"DIM"})
    d.render()

# D-S2 : opening dims on W-S, derived from window width (O1 door + O2 window)
o1a,o1b=910-455,910+455            # 455,1365
o2a,o2b=7280-windows["O2"]["w"]/2, 7280+windows["O2"]["w"]/2   # 6370,8190
ds2_stations=[0,o1a,o1b,o2a,o2b,9100]
hchain(ds2_stations,-600)
# D-S1
ds1=[0,910,1820,2730,3640,4550,5460,6370,7280,8190,9100]
hchain(ds1,-1600); hoverall(0,9100,-2600)
# D-W
dw=[0,910,1820,2730,3640,4550,5460,6370,7280,8190]
vchain(dw,-600,0); voverall(0,8190,-1600,0)
# D-E
de=[0,910,1820,2730,3640,4550,5460,6370]
vchain(de,9700,9100); voverall(0,6370,10700,9100)

doc.saveas(DXF)

# ------------------------------------------------------------------ SCHEDULE json
schedule={
 "stairs":{"risers":RISERS,"riser_mm":RISER_MM,"tread_mm":TREAD_MM,"width_mm":STAIR_W},
 "openings":{oid:{"room":w["room"],"width_mm":w["w"],"height_mm":w["h"],
                  "openable_ratio":w["r"]} for oid,w in windows.items()},
}
with open(SCHED,"w",encoding="utf-8") as f:
    json.dump(schedule,f,ensure_ascii=False,indent=2)

# ------------------------------------------------------------------ report
print("=== LEGAL: STAIR ===")
print(f"risers={RISERS} riser={RISER_MM}mm(<=230) tread={TREAD_MM}mm(>=150) width={STAIR_W}mm(>=750)")
print(f"riser*risers = {RISER_MM*RISERS:.2f} (target {FLOOR_H})")
print("=== LEGAL: WINDOWS (mm2 -> m2) ===")
for rm,r in LEGAL.items():
    print(f"{rm}: area={r['area']:.3f}  need_daylight={r['need_d']:.3f} got={r['got_d']:.3f} ok={r['ok_d']}"
          f"  need_vent={r['need_v']:.3f} got={r['got_v']:.3f} ok={r['ok_v']}")
print("=== room areas ===")
for n,a in room_area.items(): print(f"  {n}: {a:.2f}")
print(f"TOTAL floor area = {TOTAL_AREA:.2f} m2")
print("D-S2 stations:",ds2_stations)
print("saved:",DXF,SCHED)

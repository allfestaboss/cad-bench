#!/usr/bin/env python3
# T003 1F plan generator. Coordinates derived from grid symbols + room relations.
import math
import ezdxf
from ezdxf.enums import TextEntityAlignment
from ezdxf.math import Vec2
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union

OUT = "/Users/boss/dev/01_projects/big-business/cad-bench/attempts/T003/armC_loop.dxf"
PNG = "/Users/boss/dev/01_projects/big-business/cad-bench/attempts/T003/armC_loop.png"

# ------------------------------------------------------------------ grid
XL = ["X1","X2","X3","X4","X5","X6","X7","X8","X9","X10","X11"]
XC = [0,910,1820,2730,3640,4550,5460,6370,7280,8190,9100]
YL = ["Y1","Y2","Y3","Y4","Y5","Y6","Y7","Y8","Y9","Y10"]
YC = [0,910,1820,2730,3640,4550,5460,6370,7280,8190]
xd = dict(zip(XL, XC)); yd = dict(zip(YL, YC))

def _res(sym, table):
    if "+" in sym:
        b, o = sym.split("+"); return table[b] + float(o)
    if "-" in sym and not sym.startswith("-"):
        b, o = sym.split("-"); return table[b] - float(o)
    return table[sym]

def gp(sx, sy):
    return (_res(sx, xd), _res(sy, yd))

# ------------------------------------------------------------------ walls
WALLS = {
 "W-S": (("X1","Y1"),("X11","Y1")),
 "W-E": (("X11","Y1"),("X11","Y8")),
 "W-D": (("X11","Y8"),("X9","Y10")),
 "W-N": (("X1","Y10"),("X9","Y10")),
 "W-W": (("X1","Y1"),("X1","Y10")),
 "I1":  (("X3","Y1"),("X3","Y6")),
 "I2":  (("X5","Y1"),("X5","Y6")),
 "I3":  (("X7","Y1"),("X7","Y6")),
 "I4":  (("X1","Y3"),("X7","Y3")),
 "I5":  (("X1","Y3+455"),("X3","Y3+455")),
 "I6":  (("X3","Y4"),("X5","Y4")),
 "I7":  (("X1","Y6"),("X11","Y6")),
}
def wpts(wid):
    a, b = WALLS[wid]; return gp(*a), gp(*b)

def wall_frame(wid):
    a, b = wpts(wid); A = Vec2(a); B = Vec2(b)
    L = (B - A).magnitude
    u = (B - A) / L
    n = Vec2(-u.y, u.x)
    return A, B, u, n, L

# ------------------------------------------------------------------ rooms
ROOMS = {
 "玄関":    [("X1","Y1"),("X3","Y1"),("X3","Y3"),("X1","Y3")],
 "収納":    [("X1","Y3"),("X3","Y3"),("X3","Y3+455"),("X1","Y3+455")],
 "洗面脱衣": [("X1","Y3+455"),("X3","Y3+455"),("X3","Y6"),("X1","Y6")],
 "ホール":  [("X3","Y1"),("X5","Y1"),("X5","Y3"),("X3","Y3")],
 "便所":    [("X3","Y3"),("X5","Y3"),("X5","Y4"),("X3","Y4")],
 "浴室":    [("X3","Y4"),("X5","Y4"),("X5","Y6"),("X3","Y6")],
 "階段":    [("X5","Y1"),("X7","Y1"),("X7","Y3"),("X5","Y3")],
 "納戸":    [("X5","Y3"),("X7","Y3"),("X7","Y6"),("X5","Y6")],
 "和室":    [("X7","Y1"),("X11","Y1"),("X11","Y6"),("X7","Y6")],
 "LDK":     [("X1","Y6"),("X11","Y6"),("X11","Y8"),("X9","Y10"),("X1","Y10")],
}
def room_poly(name):
    return Polygon([gp(*p) for p in ROOMS[name]])

# ------------------------------------------------------------------ openings
OPENS = [
 dict(id="O1", type="door",   wall="W-S", room="玄関",    width=910,  mark="D1"),
 dict(id="O2", type="window", wall="W-S", room="和室",    width=1820, mark="W1"),
 dict(id="O3", type="window", wall="W-E", room="和室",    width=1820, mark="W2"),
 dict(id="O4", type="window", wall="W-D", t0=700, t1=1900,            mark="W3"),
 dict(id="O5", type="window", wall="W-N", room="LDK",     width=1820, mark="W4"),
 dict(id="O6", type="door",   wall="I1",  room="玄関",    width=910,  mark="D2"),
 dict(id="O7", type="door",   wall="I7",  room="洗面脱衣", width=910,  mark="D3"),
 dict(id="O8", type="door",   wall="I7",  room="和室",    width=910,  mark="D4"),
]

def resolve_open(o):
    A, B, u, n, L = wall_frame(o["wall"])
    if "t0" in o and "t1" in o:
        t0, t1 = o["t0"], o["t1"]
    else:
        rp = room_poly(o["room"])
        wl = LineString([(A.x, A.y), (B.x, B.y)])
        inter = wl.intersection(rp.boundary)
        geoms = list(inter.geoms) if hasattr(inter, "geoms") else [inter]
        ts = []
        for g in geoms:
            if g.geom_type == "LineString":
                for (px, py) in g.coords:
                    ts.append((Vec2(px, py) - A).dot(u))
        tmin, tmax = min(ts), max(ts)
        c = (tmin + tmax) / 2.0
        t0, t1 = c - o["width"]/2.0, c + o["width"]/2.0
    o.update(A=A, u=u, n=n, L=L, t0=t0, t1=t1,
             P0=A + u*t0, P1=A + u*t1, mid=A + u*((t0+t1)/2.0))
    return o

for o in OPENS:
    resolve_open(o)

# ------------------------------------------------------------------ doc / layers
doc = ezdxf.new("R2010", setup=True)
doc.header["$INSUNITS"] = 4  # mm
msp = doc.modelspace()
LY = {
 "GRID":    dict(color=8,  linetype="CENTER"),
 "WALL":    dict(color=7),
 "OPENING": dict(color=3),
 "DIM":     dict(color=4),
 "ROOM":    dict(color=5),
 "TEXT":    dict(color=7),
 "STAIR":   dict(color=2),
}
for name, kw in LY.items():
    lay = doc.layers.add(name)
    lay.color = kw.get("color", 7)
    if "linetype" in kw:
        lay.dxf.linetype = kw["linetype"]

def txt(s, p, h, layer, align=TextEntityAlignment.MIDDLE_CENTER):
    t = msp.add_text(s, dxfattribs={"layer": layer, "height": h,
                                    "style": "Standard"})
    t.set_placement(p, align=align)
    return t

# ------------------------------------------------------------------ WALL bodies
HALF = 60
def seg_rect(a, b, half=HALF):
    A = Vec2(a); B = Vec2(b)
    u = (B - A).normalize(); n = Vec2(-u.y, u.x)
    pts = [A + n*half, B + n*half, B - n*half, A - n*half]
    return Polygon([(p.x, p.y) for p in pts])

wall_mat = unary_union([seg_rect(*wpts(w)) for w in WALLS])

# cut every opening -> jambs
cuts = []
for o in OPENS:
    A, u, n = o["A"], o["u"], o["n"]; t0, t1 = o["t0"], o["t1"]; h = 90
    c = [A + u*t0 + n*h, A + u*t1 + n*h, A + u*t1 - n*h, A + u*t0 - n*h]
    cuts.append(Polygon([(p.x, p.y) for p in c]))
wall_cut = wall_mat.difference(unary_union(cuts))

def draw_boundary(geom, layer):
    polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    for poly in polys:
        for ring in [poly.exterior, *poly.interiors]:
            msp.add_lwpolyline(list(ring.coords), close=True,
                               dxfattribs={"layer": layer})
draw_boundary(wall_cut, "WALL")

# ------------------------------------------------------------------ opening symbols
def line(p, q, layer, lt=None):
    att = {"layer": layer}
    if lt: att["linetype"] = lt
    msp.add_line((p.x, p.y), (q.x, q.y), dxfattribs=att)

for o in OPENS:
    A, u, n = o["A"], o["u"], o["n"]; t0, t1 = o["t0"], o["t1"]; w = t1 - t0
    if o["type"] == "window":
        for s in (-60, -22, 22, 60):
            p = A + u*t0 + n*s; q = A + u*t1 + n*s
            line(p, q, "OPENING")
    else:  # door: leaf + swing arc, opening into center_of_room
        rp = room_poly(o["room"]); cen = Vec2(rp.centroid.x, rp.centroid.y)
        nsign = 1.0 if (cen - o["mid"]).dot(n) > 0 else -1.0
        H = A + u*t0                     # hinge at t0 jamb
        d_open = n*nsign
        leaf = H + d_open*w
        line(H, leaf, "OPENING")         # door leaf (open position)
        a_close = math.degrees(math.atan2(u.y, u.x))     # closed = toward t1
        a_open = math.degrees(math.atan2(d_open.y, d_open.x))
        diff = (a_open - a_close) % 360
        if diff <= 180:
            sa, ea = a_close, a_open
        else:
            sa, ea = a_open, a_close
        msp.add_arc((H.x, H.y), w, sa, ea, dxfattribs={"layer": "OPENING"})

# opening marks (D1..W4) near each opening, inside building
bcx, bcy = 4200, 3500
for o in OPENS:
    n = o["n"]; mid = o["mid"]
    to_c = Vec2(bcx - mid.x, bcy - mid.y)
    nsign = 1.0 if to_c.dot(n) > 0 else -1.0
    p = mid + n*(nsign*430)
    txt(o["mark"], (p.x, p.y), 230, "OPENING")

# ------------------------------------------------------------------ GRID
gx0, gx1 = -900, 9100 + 500
gy0, gy1 = -900, 8190 + 500
for lab, x in zip(XL, XC):
    msp.add_line((x, gy0), (x, gy1), dxfattribs={"layer": "GRID"})
    c = (x, gy0 - 300)
    msp.add_circle(c, 260, dxfattribs={"layer": "GRID", "linetype": "CONTINUOUS"})
    txt(lab, c, 230, "GRID").dxf.linetype = "CONTINUOUS"
for lab, y in zip(YL, YC):
    msp.add_line((gx0, y), (gx1, y), dxfattribs={"layer": "GRID"})
    c = (gx0 - 300, y)
    msp.add_circle(c, 260, dxfattribs={"layer": "GRID", "linetype": "CONTINUOUS"})
    txt(lab, c, 230, "GRID").dxf.linetype = "CONTINUOUS"

# ------------------------------------------------------------------ ROOM names + areas
areas = {}
for name in ROOMS:
    rp = room_poly(name)
    area_m2 = rp.area / 1e6
    areas[name] = area_m2
    c = rp.centroid
    if not rp.contains(c):
        c = rp.representative_point()
    cx, cy = c.x, c.y
    bx0, by0, bx1, by1 = rp.bounds
    mind = min(bx1 - bx0, by1 - by0)
    nh = min(300.0, mind * 0.30)
    ah = nh * 0.85
    off = nh * 0.75
    txt(name, (cx, cy + off), nh, "ROOM")
    txt(f"{area_m2:.2f}", (cx, cy - off), ah, "ROOM")

total = sum(areas.values())
txt(f"1階床面積 {total:.2f} m2", (4000, -3900), 360, "TEXT")

# ------------------------------------------------------------------ STAIRS
TREADS = [
 [[3700,260],[4550,260]],[[3700,460],[4550,460]],[[3700,660],[4550,660]],
 [[3700,860],[4550,860]],[[3700,1060],[4550,1060]],[[3700,1260],[4550,1260]],
 [[4550,260],[5400,260]],[[4550,460],[5400,460]],[[4550,660],[5400,660]],
 [[4550,860],[5400,860]],[[4550,1060],[5400,1060]],[[4550,1260],[5400,1260]],
 [[3700,1360],[5400,1360]],[[4550,60],[4550,1360]],
]
for a, b in TREADS:
    msp.add_line(tuple(a), tuple(b), dxfattribs={"layer": "STAIR"})
txt("UP", (3760, 140), 230, "STAIR", align=TextEntityAlignment.BOTTOM_LEFT)

# ------------------------------------------------------------------ DIMENSIONS
ds = doc.dimstyles.new("PLAN")
ds.dxf.dimtxt = 230; ds.dxf.dimasz = 180; ds.dxf.dimexe = 130
ds.dxf.dimexo = 180; ds.dxf.dimgap = 70; ds.dxf.dimtad = 1
ds.dxf.dimdec = 0; ds.dxf.dimlunit = 2; ds.dxf.dimtxsty = "Standard"
ds.dxf.dimscale = 1.0

def hdim(stations, y0, base_y, overall=None, overall_base=None):
    for i in range(len(stations) - 1):
        a, b = stations[i], stations[i+1]
        d = msp.add_linear_dim(base=((a+b)/2, base_y), p1=(a, y0), p2=(b, y0),
                               angle=0, dimstyle="PLAN",
                               dxfattribs={"layer": "DIM"})
        d.render()
    if overall is not None:
        d = msp.add_linear_dim(base=(stations[0], overall_base),
                               p1=(stations[0], y0), p2=(stations[-1], y0),
                               angle=0, dimstyle="PLAN",
                               dxfattribs={"layer": "DIM"})
        d.render()

def vdim(stations, x0, base_x, overall=None, overall_base=None):
    for i in range(len(stations) - 1):
        a, b = stations[i], stations[i+1]
        d = msp.add_linear_dim(base=(base_x, (a+b)/2), p1=(x0, a), p2=(x0, b),
                               angle=90, dimstyle="PLAN",
                               dxfattribs={"layer": "DIM"})
        d.render()
    if overall is not None:
        d = msp.add_linear_dim(base=(overall_base, stations[0]),
                               p1=(x0, stations[0]), p2=(x0, stations[-1]),
                               angle=90, dimstyle="PLAN",
                               dxfattribs={"layer": "DIM"})
        d.render()

# D-S2 derived from openings on W-S
ws_stations = {0.0, wall_frame("W-S")[4]}
for o in OPENS:
    if o["wall"] == "W-S":
        ws_stations.add(round(o["t0"], 6)); ws_stations.add(round(o["t1"], 6))
S2 = sorted(ws_stations)
hdim(S2, 0, -600)                                   # D-S2
hdim(XC, 0, -1600, overall=9100, overall_base=-2600)  # D-S1
vdim(YC, 0, -600, overall=8190, overall_base=-1600)   # D-W
vdim(YC[:8], 9100, 9700, overall=6370, overall_base=10700)  # D-E

doc.saveas(OUT)

# ------------------------------------------------------------------ report values
print("=== derived opening t0/t1 (mm along wall from 'from') ===")
for o in OPENS:
    print(f"  {o['id']} {o['type']:6s} wall={o['wall']:4s} "
          f"t0={o['t0']:.1f} t1={o['t1']:.1f} width={o['t1']-o['t0']:.1f} "
          f"P0=({o['P0'].x:.1f},{o['P0'].y:.1f}) P1=({o['P1'].x:.1f},{o['P1'].y:.1f})")
print("=== room areas (m2) ===")
for k, v in areas.items():
    print(f"  {k:8s} {v:.4f} -> {v:.2f}")
print(f"  TOTAL {total:.4f} -> {total:.2f}")
print("=== D-S2 stations ===", S2)
print("saved", OUT)

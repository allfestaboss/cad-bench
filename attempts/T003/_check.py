#!/usr/bin/env python3
import ezdxf, math
from collections import Counter
from shapely.geometry import Polygon, Point

DXF = "/Users/boss/dev/01_projects/big-business/cad-bench/attempts/T003/armC_loop.dxf"
doc = ezdxf.readfile(DXF); msp = doc.modelspace()

# ---- layer usage ----
used = Counter(e.dxf.layer for e in msp)
print("layer usage:", dict(used))
assert "0" not in used, "ENTITY ON LAYER 0!"
req = {"GRID","WALL","OPENING","DIM","ROOM","TEXT","STAIR"}
print("required layers present with entities:", req <= set(used))

# ---- dimensions: displayed measurement ----
print("\n--- DIMENSION entities (actual_measurement / text) ---")
dims = [e for e in msp if e.dxftype() == "DIMENSION"]
print("count:", len(dims))
meas = []
for d in dims:
    m = d.get_measurement()
    txt = d.dxf.get("text", "<>")
    meas.append(round(m, 1))
    if txt not in ("<>", "") :
        print("  OVERRIDE TEXT:", txt, "meas", m)
meas.sort()
print("measurements:", meas)

# expected set of segment/overall measurements
exp = []
XC=[0,910,1820,2730,3640,4550,5460,6370,7280,8190,9100]
YC=[0,910,1820,2730,3640,4550,5460,6370,7280,8190]
def segs(st): return [round(st[i+1]-st[i],1) for i in range(len(st)-1)]
S2=[0,455,1365,6370,8190,9100]
exp += segs(S2)                       # D-S2
exp += segs(XC)                       # D-S1
exp += [9100.0]
exp += segs(YC)                       # D-W
exp += [8190.0]
exp += segs(YC[:8])                   # D-E
exp += [6370.0]
exp_sorted = sorted(round(x,1) for x in exp)
print("expected     :", exp_sorted)
print("MATCH:", meas == exp_sorted)

# ---- room area texts inside room polygons ----
def gp(x,y): return (x,y)
ROOMS = {
 "玄関":[(0,0),(1820,0),(1820,1820),(0,1820)],
 "収納":[(0,1820),(1820,1820),(1820,2275),(0,2275)],
 "洗面脱衣":[(0,2275),(1820,2275),(1820,4550),(0,4550)],
 "ホール":[(1820,0),(3640,0),(3640,1820),(1820,1820)],
 "便所":[(1820,1820),(3640,1820),(3640,2730),(1820,2730)],
 "浴室":[(1820,2730),(3640,2730),(3640,4550),(1820,4550)],
 "階段":[(3640,0),(5460,0),(5460,1820),(3640,1820)],
 "納戸":[(3640,1820),(5460,1820),(5460,4550),(3640,4550)],
 "和室":[(5460,0),(9100,0),(9100,4550),(5460,4550)],
 "LDK":[(0,4550),(9100,4550),(9100,6370),(7280,8190),(0,8190)],
}
polys = {k: Polygon(v) for k, v in ROOMS.items()}
areas = {k: round(p.area/1e6, 2) for k, p in polys.items()}
print("\n--- room area strings expected ---")
for k,v in areas.items(): print(f"  {k}: {v:.2f}")
print("  total:", round(sum(polys[k].area for k in polys)/1e6, 2))

# collect texts
texts = [(e.dxf.text, e.dxf.layer, tuple(e.dxf.insert)[:2]) for e in msp
         if e.dxftype() == "TEXT"]
# check each area value text lies inside its room
print("\n--- area text placement check ---")
for k, p in polys.items():
    want = f"{areas[k]:.2f}"
    found = [t for t in texts if t[0]==want and t[1]=="ROOM"]
    inside = any(p.buffer(1e-6).contains(Point(t[2])) for t in found)
    print(f"  {k}: value '{want}' present={bool(found)} inside_room={inside}")

# opening marks present
marks = {"D1","D2","D3","D4","W1","W2","W3","W4"}
mark_texts = {t[0] for t in texts if t[0] in marks}
print("\nopening marks present:", sorted(mark_texts), "complete:", marks==mark_texts)

# total area text present on TEXT layer
tot = [t for t in texts if "72.87" in t[0]]
print("total-area text:", tot)

# 'UP' present on STAIR
up = [t for t in texts if t[0]=="UP" and t[1]=="STAIR"]
print("UP on STAIR:", bool(up))
print("\nALL CHECKS DONE")

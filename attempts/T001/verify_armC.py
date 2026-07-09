#!/usr/bin/env python
"""Read-back verification + render for armC_loop.dxf (self-written checks only)."""
import json
from pathlib import Path

import ezdxf
from ezdxf.math import Vec3

HERE = Path(__file__).resolve().parent
SPEC = json.loads((HERE.parent.parent / "tasks" / "T001" / "spec.json").read_text())
DXF = HERE / "armC_loop.dxf"

doc = ezdxf.readfile(DXF)
msp = doc.modelspace()

print("=== LAYERS present ===")
have = set(l.dxf.name for l in doc.layers)
for req in SPEC["layers"]["required"]:
    print(f"  {req}: {'OK' if req in have else 'MISSING'}")

print("=== entities per layer / layer-0 check ===")
from collections import Counter
c = Counter(e.dxf.layer for e in msp)
for k, v in sorted(c.items()):
    print(f"  {k}: {v}")
zero = [e for e in msp if e.dxf.layer == "0"]
print(f"  entities on layer 0: {len(zero)}  {'OK' if not zero else 'BAD'}")

print("=== DIMENSION entities ===")
dims = [e for e in msp if e.dxftype() == "DIMENSION"]
print(f"  count: {len(dims)}")
# measured value: read from dimension geometry via defpoints
for d in dims:
    meas = d.get_measurement()
    txt = d.dxf.text  # '<>' means auto = measurement
    layer = d.dxf.layer
    disp = round(meas) if txt in ("<>", "") else txt
    print(f"  layer={layer} measured={meas:.1f} text_field={txt!r} -> shows {disp}")

# Expected chain segment measurements
print("=== expected vs measured (module 910 / overalls) ===")
measured_vals = sorted(round(d.get_measurement()) for d in dims)
print("  measured multiset:", measured_vals)

print("=== WALL faces at +/-60 sample check ===")
# collect all vertical & horizontal segment x/y from LWPOLYLINE on WALL
xs = set(); ys = set()
for e in msp.query('LWPOLYLINE[layer=="WALL"]'):
    pts = [(round(p[0], 2), round(p[1], 2)) for p in e.get_points("xy")]
    n = len(pts)
    for i in range(n):
        a = pts[i]; b = pts[(i + 1) % n]
        if abs(a[0] - b[0]) < 1e-6:  # vertical segment -> x face
            xs.add(a[0])
        if abs(a[1] - b[1]) < 1e-6:  # horizontal segment -> y face
            ys.add(a[1])
print("  wall vertical-face X values:", sorted(xs))
print("  wall horizontal-face Y values:", sorted(ys))
# expected faces: grid coord +/-60 for walls present
expected_x_faces = {-60, 60, 1760, 1880, 5400, 5520}
expected_y_faces = {-60, 60, 1760, 1880, 2670, 2790, 4490, 4610}
print("  expected X faces subset present:",
      expected_x_faces.issubset(xs), sorted(expected_x_faces - xs))
print("  expected Y faces subset present:",
      expected_y_faces.issubset(ys), sorted(expected_y_faces - ys))

print("=== opening jamb presence (gaps in wall faces) ===")
# For O1 on south outer face y=-60: expect gap between x=455 and x=1365
# Check that no wall horizontal segment at y=-60 spans across 455..1365
def face_segments_at_y(yval):
    segs = []
    for e in msp.query('LWPOLYLINE[layer=="WALL"]'):
        pts = [(p[0], p[1]) for p in e.get_points("xy")]
        n = len(pts)
        for i in range(n):
            a = pts[i]; b = pts[(i + 1) % n]
            if abs(a[1] - yval) < 1e-6 and abs(b[1] - yval) < 1e-6:
                segs.append((min(a[0], b[0]), max(a[0], b[0])))
    return segs
for yv, (gs, ge) in [(-60, (455, 1365)), (-60, (2730, 4550))]:
    segs = face_segments_at_y(yv)
    covered = any(s <= gs + 1 and e >= ge - 1 for s, e in segs)
    print(f"  face y={yv} gap {gs}-{ge}: {'GAP OK (not covered)' if not covered else 'NO GAP (bad)'} segs={sorted(segs)}")

# ---- render ----
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing.config import Configuration, ColorPolicy, BackgroundPolicy

CFG = Configuration(
    color_policy=ColorPolicy.MONOCHROME_LIGHT_BG,  # simulate B/W paper plot
    background_policy=BackgroundPolicy.WHITE,
    lineweight_scaling=1.5,
)

fig = plt.figure(figsize=(16, 14))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_axis_off()
ctx = RenderContext(doc)
out = MatplotlibBackend(ax)
Frontend(ctx, out, config=CFG).draw_layout(msp, finalize=True)
png = HERE / "armC_loop.png"
fig.savefig(png, dpi=120, facecolor="white")
print("rendered", png)

# zoom: SW corner + entrance door + internal door junction
for tag, (x0, x1, y0, y1) in {
    "sw_corner_door": (-300, 2100, -300, 1600),
    "east_window": (5000, 5700, 1500, 4000),
}.items():
    figz = plt.figure(figsize=(10, 10))
    axz = figz.add_axes([0, 0, 1, 1]); axz.set_axis_off()
    Frontend(RenderContext(doc), MatplotlibBackend(axz), config=CFG).draw_layout(msp, finalize=True)
    axz.set_xlim(x0, x1); axz.set_ylim(y0, y1)
    pz = HERE / f"zoom_{tag}.png"
    figz.savefig(pz, dpi=140, facecolor="white")
    print("rendered", pz)

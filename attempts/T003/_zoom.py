#!/usr/bin/env python3
import sys, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = ["Hiragino Sans", "AppleGothic", "Arial Unicode MS"]
import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

DXF = "/Users/boss/dev/01_projects/big-business/cad-bench/attempts/T003/armC_loop.dxf"
x0, y0, x1, y1, out = (float(sys.argv[1]), float(sys.argv[2]),
                       float(sys.argv[3]), float(sys.argv[4]), sys.argv[5])
doc = ezdxf.readfile(DXF); msp = doc.modelspace()
fig = plt.figure(figsize=(14, 14)); ax = fig.add_axes([0, 0, 1, 1])
ax.set_aspect("equal"); ax.set_facecolor("white")
Frontend(RenderContext(doc), MatplotlibBackend(ax)).draw_layout(msp, finalize=True)
ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
fig.savefig(out, dpi=130, facecolor="white")
print("wrote", out)

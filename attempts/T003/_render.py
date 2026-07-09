#!/usr/bin/env python3
import sys, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
# try to get a CJK font so Japanese isn't tofu
for f in ["Hiragino Sans", "Hiragino Kaku Gothic Pro", "AppleGothic",
          "Arial Unicode MS", "PingFang SC"]:
    plt.rcParams["font.family"] = [f]
    break
import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing.config import Configuration

DXF = "/Users/boss/dev/01_projects/big-business/cad-bench/attempts/T003/armC_loop.dxf"
PNG = sys.argv[1] if len(sys.argv) > 1 else \
      "/Users/boss/dev/01_projects/big-business/cad-bench/attempts/T003/armC_loop.png"

doc = ezdxf.readfile(DXF)
msp = doc.modelspace()
fig = plt.figure(figsize=(18, 18))
ax = fig.add_axes([0, 0, 1, 1]); ax.set_aspect("equal")
ax.set_facecolor("white")
ctx = RenderContext(doc)
out = MatplotlibBackend(ax)
Frontend(ctx, out).draw_layout(msp, finalize=True)
fig.savefig(PNG, dpi=120, facecolor="white")
print("wrote", PNG)

import sys, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import ezdxf, ezdxf.recover
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
for p in sys.argv[1:]:
    try:
        doc = ezdxf.readfile(p)
    except Exception:
        doc, _ = ezdxf.recover.readfile(p)
    fig = plt.figure(figsize=(11, 9)); ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    Frontend(RenderContext(doc), MatplotlibBackend(ax)).draw_layout(doc.modelspace(), finalize=True)
    out = p.rsplit(".", 1)[0] + ".png"
    fig.savefig(out, dpi=110); plt.close(fig); print(out)

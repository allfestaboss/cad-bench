#!/usr/bin/env python3
"""採点器の偽陰性テスト。

ベンチマークは「良い提出が高得点」だけでは信用できない。
**悪い提出が確実に低得点になる**ことを示す必要がある。

参照解を故意に壊し、各検査が反応するかを確かめる。
  usage: .venv/bin/python checker/adversarial.py
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import ezdxf

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "bin" / "python")
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / "bench"))
from geom import load_spec  # noqa: E402
from resolve import make_coord  # noqa: E402


def score(spec, dxf):
    r = subprocess.run([PY, str(ROOT / "bench" / "check.py"), str(spec), str(dxf)],
                       capture_output=True, text=True, cwd=ROOT)
    j = json.loads(r.stdout)[0]
    return j["score"], j["max"], [c for c in j["checks"] if not c["ok"]]


def build(spec, out, sched=None):
    cmd = [PY, str(ROOT / "bench" / "build_ref.py"), str(spec), str(out)]
    if sched:
        cmd.append(str(sched))
    subprocess.run(cmd, check=True, capture_output=True, cwd=ROOT)


def report(title, spec, dxf, expect_fail=True):
    s, m, fails = score(spec, dxf)
    print(f"\n{title}\n  {s:.1f}/{m:.0f}  ({100*s/m:.1f}%)")
    for c in fails:
        print(f"    NG [{c['level']}] {c['name']}\n        {c['detail'][:78]}")
    if not fails:
        print("    失点なし" + ("  ← 細工を検出できていない（採点器の盲点）" if expect_fail else "（正しい）"))


# ================================================================ T003 の細工
T3 = ROOT / "tasks" / "T003" / "spec.json"
REF3 = ROOT / "reference" / "reference_t003.dxf"
build(T3, REF3)
print("=" * 78)
print("T003: 参照解を故意に壊して、採点器が反応するか")
print("=" * 78)
report("(0) 無傷の参照解", T3, REF3, expect_fail=False)

# 1) 寸法の表示だけ100倍（幾何は完璧のまま）
d = ezdxf.readfile(REF3)
for e in d.modelspace():
    if e.dxftype() == "DIMENSION":
        ov = e.override()          # override() は毎回新しい物を返す。同じ物に commit すること
        ov.update({"dimlfac": 100.0})
        ov.commit()
d.saveas(OUT / "evil_dimlfac.dxf")
report("(1) 寸法の表示だけ100倍（DIMLFAC=100）", T3, OUT / "evil_dimlfac.dxf")

# 2) 寸法を線分＋文字で偽装
d = ezdxf.readfile(REF3)
msp = d.modelspace()
for e in list(msp):
    if e.dxftype() == "DIMENSION":
        msp.delete_entity(e)
for x in range(0, 9101, 910):
    msp.add_line((x, -600), (x, -500), dxfattribs={"layer": "DIM"})
    msp.add_text("910", dxfattribs={"layer": "DIM", "height": 250}).set_placement((x + 300, -550))
d.saveas(OUT / "evil_fakedim.dxf")
report("(2) 寸法を線分と文字で偽装", T3, OUT / "evil_fakedim.dxf")

# 3) 壁をわずか0.05%だけ拡大（紙の上で0.05mm）
d = ezdxf.readfile(REF3)
for e in d.modelspace():
    if e.dxf.layer == "WALL" and e.dxftype() == "LWPOLYLINE":
        e.set_points([(round(p[0] * 1.0005, 3), round(p[1] * 1.0005, 3)) for p in e.get_points("xy")],
                     format="xy")
d.saveas(OUT / "evil_thick.dxf")
report("(3) 壁を0.05%だけ拡大", T3, OUT / "evil_thick.dxf")

# 4) 1室だけ面積を間違える
d = ezdxf.readfile(REF3)
for e in d.modelspace():
    if e.dxftype() == "TEXT" and e.dxf.layer == "ROOM" and e.dxf.text == "31.47":
        e.dxf.text = "31.50"
d.saveas(OUT / "evil_area.dxf")
report("(4) LDKの面積を 31.47 → 31.50", T3, OUT / "evil_area.dxf")

# 5) 建具と符号を全削除
d = ezdxf.readfile(REF3)
msp = d.modelspace()
for e in list(msp):
    if e.dxf.layer == "OPENING":
        msp.delete_entity(e)
d.saveas(OUT / "evil_noopen.dxf")
report("(5) 建具と建具符号を全削除", T3, OUT / "evil_noopen.dxf")

# ================================================================ T004 の細工
T4 = ROOT / "tasks" / "T004" / "spec.json"
REF4 = ROOT / "reference" / "reference_t004.dxf"
build(T4, REF4)
print("\n" + "=" * 78)
print("T004: 法規（L4）と、建具表の申告で嘘をつけないこと")
print("=" * 78)
report("(0) 無傷の参照解", T4, REF4, expect_fail=False)

raw = load_spec(T4)
c = make_coord(raw)
x0, y0, x1, y1 = 3700.0, 60.0, 5400.0, 1760.0
N, T, W = 12, 140.0, 850.0                 # 蹴上241.7(>230) / 踏面140(<150)
mid, per = x0 + W, (N - 1) // 2
tr = []
for k in range(1, per + 1):
    y = y0 + T * k
    tr += [[[x0, y], [mid, y]], [[mid, y], [x1, y]]]
land = y0 + T * (per + 1)
tr += [[[x0, land], [x1, land]], [[mid, y0], [mid, land]]]
evil = {"stairs": {"floor_height_mm": 2900, "risers": N, "riser_mm": round(2900 / N, 2),
                   "tread_mm": T, "width_mm": W, "treads": tr, "up_text_at": [x0 + 60, y0 + 80]},
        "openings": {"O2": {"room": "和室", "width_mm": 1820, "height_mm": 2000, "openable_ratio": 0.5},
                     "O3": {"room": "和室", "width_mm": 1820, "height_mm": 1200, "openable_ratio": 0.5},
                     "O4": {"room": "LDK", "width_mm": 1200, "height_mm": 1200, "openable_ratio": 0.5},
                     "O5": {"room": "LDK", "width_mm": 1820, "height_mm": 1200, "openable_ratio": 0.5}}}
(OUT / "evil_t004.schedule.json").write_text(json.dumps(evil, ensure_ascii=False, indent=1), encoding="utf-8")

# (6) 申告と作図は一致しているが、法規に違反する図面
build(T4, OUT / "evil_t004.dxf", OUT / "evil_t004.schedule.json")
report("(6) 幾何は完璧だが法規に違反（蹴上241.7 / 踏面140 / LDK採光不足）", T4, OUT / "evil_t004.dxf")

# (7) 図面は参照解のまま、建具表だけ「大きい窓を入れた」と偽る
(OUT / "liar_t004.dxf").write_bytes((REF4).read_bytes())
(OUT / "liar_t004.schedule.json").write_text(json.dumps(evil, ensure_ascii=False, indent=1), encoding="utf-8")
report("(7) 建具表だけ偽る（図面は参照解のまま）", T4, OUT / "liar_t004.dxf")

print("""
--------------------------------------------------------------------------------
残る盲点（正直に）:
  ・窓の「高さ」は平面図から読めない。幅と整合させたまま高さだけ盛れば検出できない。
    これは実務で建具表と姿図が別図書として要求される理由そのもの。
  ・L5（製図の作法）は点数に入れていない。図面枠が無くても満点が出る。
--------------------------------------------------------------------------------""")

#!/usr/bin/env python3
"""参照解のための法規ソルバー。制約を満たす値を決定論で選ぶだけ。知能は無い。

被験者はこれを見られない。参照解が L4 を満点で通ることを示し、
「制約は満たせる（課題は解ける）」ことを保証するためだけに存在する。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from shapely.geometry import Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resolve import make_coord  # noqa: E402


def solve_schedule(raw: dict) -> dict:
    code = raw["code"]
    H = raw["floor_height_mm"]

    # ---- 階段: 蹴上が上限以下になる最小の段数。踏面と幅は余裕を見て決める。
    N = math.ceil(H / code["stair"]["max_riser_mm"])
    if (N - 1) % 2:            # 折返しなので段板を左右に等分したい
        N += 1
    tread = max(code["stair"]["min_tread_mm"], 210.0)

    stair_room = next(r for r in raw["rooms"] if r["name"] == "階段")
    c = make_coord(raw)   # 解決規則は resolver と同一の実装を使う
    poly = Polygon([(c(p[0], "x"), c(p[1], "y")) for p in stair_room["poly"]])
    hw = raw["wall_thickness"] / 2.0
    x0, y0, x1, y1 = poly.buffer(-hw).bounds
    width = (x1 - x0) / 2.0                       # 折返しなので有効幅は内法の半分
    per_run = (N - 1) // 2
    if y0 + tread * per_run + tread > y1:         # 収まらないなら踏面を詰める
        tread = max(code["stair"]["min_tread_mm"], (y1 - y0) / (per_run + 1))

    treads, mid = [], x0 + width
    for k in range(1, per_run + 1):
        y = y0 + tread * k
        treads.append([[x0, y], [mid, y]])        # 西側の上り
        treads.append([[mid, y], [x1, y]])        # 東側の下り
    land = y0 + tread * (per_run + 1)
    treads.append([[x0, land], [x1, land]])       # 踊り場の端
    treads.append([[mid, y0], [mid, land]])       # 中央のささら

    sched = {
        "stairs": {"floor_height_mm": H, "risers": N, "riser_mm": round(H / N, 2),
                   "tread_mm": round(tread, 2), "width_mm": round(width, 2),
                   "treads": treads, "up_text_at": [x0 + 60, y0 + 80]},
        "openings": {},
    }

    # ---- 居室の窓: 採光 1/7 と換気 1/20 を満たす最小の見付けを、決められた順で割り付ける
    areas = {r["name"]: Polygon([(c(p[0], "x"), c(p[1], "y")) for p in r["poly"]]).area / 1e6
             for r in raw["rooms"]}
    free = {o["id"]: o for o in raw["openings"] if "width" not in o}
    for room in raw["habitable_rooms"]:
        need = areas[room] * code["daylight_ratio"]
        mine = [o for o in free.values() if o.get("center_of_room") == room or o.get("belongs_to") == room]
        if not mine:
            continue
        h = 1800.0
        # 壁に収まる最大幅（安全側に 0.9 倍）を上限に、必要面積を等分して割り付ける
        caps = []
        for o in mine:
            w = next(x for x in raw["walls"] if x["id"] == o["wall"])
            L = math.dist((c(w["from"][0], "x"), c(w["from"][1], "y")),
                          (c(w["to"][0], "x"), c(w["to"][1], "y")))
            caps.append(min(L * 0.9, 2730.0))
        share = need / len(mine)
        for o, cap in zip(mine, caps):
            w = min(cap, max(910.0, math.ceil(share / (h / 1000.0) * 1000 / 455) * 455))
            sched["openings"][o["id"]] = {"room": room, "width_mm": w, "height_mm": h,
                                          "openable_ratio": 0.5}
        # 足りなければ大きい方から広げる
        got = sum(v["width_mm"] * v["height_mm"] / 1e6 for k, v in sched["openings"].items()
                  if v["room"] == room)
        i = 0
        while got < need and i < 20:
            for o, cap in sorted(zip(mine, caps), key=lambda z: -z[1]):
                v = sched["openings"][o["id"]]
                if v["width_mm"] < cap:
                    v["width_mm"] = min(cap, v["width_mm"] + 455)
            got = sum(v["width_mm"] * v["height_mm"] / 1e6 for k, v in sched["openings"].items()
                      if v["room"] == room)
            i += 1
    return sched

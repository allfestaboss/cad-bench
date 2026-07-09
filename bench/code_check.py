#!/usr/bin/env python3
"""L4: 法規適合の機械採点。

重要な性質: **L4 は正解の図面を必要としない。** 制約を満たすかどうかを見るだけ。
だから L4 を入れると、設計の自由度を開いたまま採点できる。

重要な限界（誠実に）:
  ・採光補正係数（令20条）を 1 と仮定した簡略モデル。実務の判定には使えない。
  ・窓の高さは平面図からは読めない。建具表（schedule）の申告を信じるしかない。
    ——これは実務で建具表が存在する理由そのもの。図面だけでは採光は証明できない。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from shapely.geometry import LineString, Point

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geom import TOL, room_poly  # noqa: E402


def _tread_lines(segs, width_mm):
    """段板 = 長さが階段幅にほぼ等しい線分。踊り場端(幅の2倍)とささら(直交)を除く。"""
    return [s for s in segs if abs(math.dist(*s) - width_mm) <= 30.0]


def check_code(spec, sched, stair_segs, rooms_area):
    """[(name, ok, detail, points, max)] を返す。"""
    out = []
    code = spec["code"]

    def add(name, ok, detail, pts=None, mx=5):
        out.append((name, bool(ok), detail, (mx if ok else 0) if pts is None else pts, mx))

    # ---------------- 階段（令23条・住宅）
    st = sched.get("stairs", {})
    N = st.get("risers")
    T = st.get("tread_mm")
    W = st.get("width_mm")
    H = spec["floor_height_mm"]
    c = code["stair"]

    if not N or not T or not W:
        add("階段の申告が揃っている", False, "risers / tread_mm / width_mm のいずれかが無い")
        return out

    riser = H / N
    add(f"蹴上 ≤ {c['max_riser_mm']}mm（{c['source']}）", riser <= c["max_riser_mm"] + 1e-6,
        f"階高{H} ÷ {N}段 = 蹴上 {riser:.1f}mm")
    add(f"踏面 ≥ {c['min_tread_mm']}mm（{c['source']}）", T >= c["min_tread_mm"] - 1e-6,
        f"申告 踏面 {T:.1f}mm")
    add(f"階段の幅 ≥ {c['min_width_mm']}mm（{c['source']}）", W >= c["min_width_mm"] - 1e-6,
        f"申告 幅 {W:.1f}mm")

    # 申告と作図の突き合わせ（申告だけで嘘をつけないように）
    treads = _tread_lines(stair_segs, W)
    add("段板の本数が段数と整合する（段数−1）", len(treads) == N - 1,
        f"作図された段板 {len(treads)}本 / 期待 {N-1}本（幅{W:.0f}mmの線分として検出）")

    # 各 run 内の段板ピッチが申告した踏面と一致するか
    pitch_ok, pitch_detail = True, []
    runs = {}
    for s in treads:
        key = round(min(p[0] for p in s), 1)
        runs.setdefault(key, []).append(round(min(p[1] for p in s), 2))
    for key, ys in runs.items():
        ys = sorted(set(ys))
        diffs = [round(b - a, 1) for a, b in zip(ys[:-1], ys[1:])]
        bad = [d for d in diffs if abs(d - T) > 1.0]
        if bad:
            pitch_ok = False
            pitch_detail.append(f"x={key}: 実測ピッチ {sorted(set(diffs))}")
    add("作図された段板のピッチが申告の踏面と一致する", pitch_ok,
        "; ".join(pitch_detail) if pitch_detail else f"全 run で {T:.0f}mm")

    # 階段の作図が階段室の内法に収まっているか
    stair_room = next((r for r in spec["rooms"] if r["name"] == "階段"), None)
    if stair_room:
        inner = room_poly(stair_room).buffer(-spec["wall_thickness"] / 2.0)
        outside = [s for s in stair_segs if not inner.buffer(TOL).contains(LineString(s))]
        add("階段の作図が階段室の内法に収まっている", not outside,
            f"はみ出した線分 {len(outside)}本")

    # ---------------- 採光・換気（法28条）
    hab = spec["habitable_rooms"]
    op = sched.get("openings", {})
    walls = {w["id"]: w for w in spec["walls"]}

    for name in hab:
        area = rooms_area[name]
        lit = vent = 0.0
        detail = []
        for oid, d in op.items():
            if d.get("room") != name:
                continue
            a = d["width_mm"] * d["height_mm"] / 1e6
            lit += a
            vent += a * d.get("openable_ratio", 0.0)
            detail.append(f"{oid} {d['width_mm']:.0f}x{d['height_mm']:.0f}")
        need_l = area * code["daylight_ratio"]
        need_v = area * code["ventilation_ratio"]
        add(f"[{name}] 採光 ≥ 床面積の1/7（{code['daylight_source']}）", lit >= need_l - 1e-9,
            f"開口 {lit:.3f}㎡ / 必要 {need_l:.3f}㎡（床 {area:.2f}㎡）  {', '.join(detail)}", mx=8)
        add(f"[{name}] 換気 ≥ 床面積の1/20（{code['ventilation_source']}）", vent >= need_v - 1e-9,
            f"開放可能 {vent:.3f}㎡ / 必要 {need_v:.3f}㎡", mx=4)

    # ---------------- 窓が壁に収まっているか
    bad = []
    for o in spec["openings"]:
        w = walls[o["wall"]]
        L = math.dist(tuple(w["from"]), tuple(w["to"]))
        if o["t0"] < -TOL or o["t1"] > L + TOL:
            bad.append(f"{o['id']} t={o['t0']:.0f}..{o['t1']:.0f} > 壁長 {L:.0f}")
    add("全ての開口が壁の中に収まっている", not bad, "; ".join(bad) if bad else "全て収まっている")
    return out

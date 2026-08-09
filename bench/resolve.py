#!/usr/bin/env python3
"""宣言的な仕様（通り芯符号・室との関係で書かれた仕様）を、具体座標の仕様に解決する。

被験者に渡すのは宣言的な仕様だけ。採点器はここで解決した具体仕様を使う。
解決規則は spec に明記してあるものだけを使い、恣意的な選択を入れない。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geom import load_spec  # noqa: E402


def make_coord(d: dict):
    """'X3' / 'Y3+455' / 数値 を座標に解決する関数を返す。解決規則の唯一の実装。"""
    gx = dict(zip(d["grid"]["x"]["labels"], d["grid"]["x"]["coords"]))
    gy = dict(zip(d["grid"]["y"]["labels"], d["grid"]["y"]["coords"]))

    def coord(ref, axis):
        if isinstance(ref, (int, float)):
            return float(ref)
        s = str(ref)
        for op in ("+", "-"):
            if op in s[1:]:
                base, off = s.split(op, 1)
                return coord(base.strip(), axis) + (1 if op == "+" else -1) * float(off)
        return float((gx if axis == "x" else gy)[s])
    return coord


def resolve(d: dict, sched: dict | None = None) -> dict:
    """sched（提出者の建具表）があれば、自由な開口の幅をそこから取る。"""
    import copy
    d = copy.deepcopy(d)
    sched = sched or {}
    sop = sched.get("openings", {})
    coord = make_coord(d)

    out = {k: v for k, v in d.items() if k not in ("walls", "openings", "rooms")}
    out["walls"] = []
    for w in d["walls"]:
        # 座標以外のキーは落とさずに持ち越す。thickness / faces を落とすと
        # 壁厚が全部 wall_thickness の既定値になり、参照解が黙って別物になる。
        v = {k: val for k, val in w.items() if k not in ("from", "to")}
        v["from"] = [coord(w["from"][0], "x"), coord(w["from"][1], "y")]
        v["to"] = [coord(w["to"][0], "x"), coord(w["to"][1], "y")]
        out["walls"].append(v)

    out["rooms"] = []
    for r in d["rooms"]:
        out["rooms"].append({
            "name": r["name"],
            "poly": [[coord(p[0], "x"), coord(p[1], "y")] for p in r["poly"]],
        })
    for r in out["rooms"]:
        r["area_m2"] = round(Polygon(r["poly"]).area / 1e6, 4)

    rooms = {r["name"]: r for r in out["rooms"]}
    walls = {w["id"]: w for w in out["walls"]}

    def proj(w, pt):
        (x0, y0), (x1, y1) = w["from"], w["to"]
        dx, dy = x1 - x0, y1 - y0
        L = (dx * dx + dy * dy) ** 0.5
        return ((pt[0] - x0) * dx + (pt[1] - y0) * dy) / L

    out["openings"] = []
    for o in d["openings"]:
        w = walls[o["wall"]]
        width = o.get("width")
        if width is None and o["id"] in sop:
            width = float(sop[o["id"]]["width_mm"])
        if "t0" in o:
            t0, t1 = float(o["t0"]), float(o["t1"])
        elif o.get("center_of_wall"):
            L = ((w["to"][0]-w["from"][0])**2 + (w["to"][1]-w["from"][1])**2) ** 0.5
            if width is None:
                raise ValueError(f"開口 {o['id']}: 幅の指定も建具表も無い")
            t0, t1 = L/2.0 - width/2.0, L/2.0 + width/2.0
        elif "center_of_room" in o:
            # 「その室の、その壁に沿った範囲」＝ 室の境界のうち、その壁の芯線上に
            # 乗っている部分（共有辺）。室の多角形を壁の軸へ射影した範囲ではない。
            # 例: LDK は W-N と x0..7280 でしか接していない（北東が45度で欠けるため）。
            poly = Polygon(rooms[o["center_of_room"]]["poly"])
            cl = LineString([tuple(w["from"]), tuple(w["to"])])
            shared = poly.exterior.intersection(cl.buffer(1e-6))
            if shared.is_empty:
                raise ValueError(f"開口 {o['id']}: 室 {o['center_of_room']} は壁 {o['wall']} と接していない")
            ts = [proj(w, p) for g in getattr(shared, "geoms", [shared]) for p in g.coords]
            c = (min(ts) + max(ts)) / 2.0
            if width is None:
                raise ValueError(f"開口 {o['id']}: 幅の指定も建具表も無い")
            t0, t1 = c - width / 2.0, c + width / 2.0
        elif "from_axis" in o:
            base = coord(o["from_axis"], "x" if abs(w["from"][1] - w["to"][1]) < 1e-6 else "y")
            t0 = proj(w, (base, base) if False else (
                (base, w["from"][1]) if abs(w["from"][1] - w["to"][1]) < 1e-6 else (w["from"][0], base)))
            t0 += float(o.get("offset", 0))
            t1 = t0 + float(width)
        else:
            raise ValueError(f"開口 {o['id']} の位置指定が不明")
        out["openings"].append({"id": o["id"], "type": o["type"], "wall": o["wall"],
                                "t0": round(t0, 4), "t1": round(t1, 4), "desc": o.get("desc", "")})

    # 開口位置の寸法系統を導出（宣言側は "derive_from_openings": "W-S" と書くだけ）
    for c in out["dimensions"]["chains"]:
        if c.get("derive_from_openings"):
            w = walls[c["derive_from_openings"]]
            _, _, = None, None
            st = {0.0}
            for o in out["openings"]:
                if o["wall"] == c["derive_from_openings"]:
                    st.add(round(o["t0"], 3))
                    st.add(round(o["t1"], 3))
            L = ((w["to"][0] - w["from"][0]) ** 2 + (w["to"][1] - w["from"][1]) ** 2) ** 0.5
            st.add(round(L, 3))
            c["stations"] = sorted(st)
            if "overall" not in c:          # 宣言側で null と書いてあればそれを尊重する
                c["overall"] = round(L, 3)

    out["_total_area_m2"] = round(sum(r["area_m2"] for r in out["rooms"]), 4)
    return out


if __name__ == "__main__":
    src = load_spec(sys.argv[1])
    res = resolve(src)
    Path(sys.argv[2]).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"resolved → {sys.argv[2]}", file=sys.stderr)
    for r in res["rooms"]:
        print(f"  {r['name']:<8} {r['area_m2']:>9.4f} m2", file=sys.stderr)
    print(f"  {'合計':<8} {res['_total_area_m2']:>9.4f} m2", file=sys.stderr)

#!/usr/bin/env python3
"""汎用採点器。spec.json だけを真として DXF を機械採点する。

  L0 開けるか / L1 幾何が健全か / L2 寸法が本物か / L3 意味が合っているか
  L5 製図の作法（点数外・助言。JIS A 0150 由来）

使い方: check.py <spec.json> <a.dxf> [b.dxf ...]
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import ezdxf
import ezdxf.recover
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geom import (TOL, boundary, load_spec, on_wall_face, opening_rect,  # noqa: E402
                  point_at, room_poly, wall_of, wall_vec)
from resolve import resolve  # noqa: E402
from code_check import check_code  # noqa: E402


def load_schedule(dxf_path):
    """提出者の建具表。<stem>.schedule.json を探す。"""
    p = Path(str(dxf_path).rsplit(".", 1)[0] + ".schedule.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


# ------------------------------------------------------------------ DXF 読み
def segments_of(e):
    t = e.dxftype()
    if t == "LINE":
        s, q = e.dxf.start, e.dxf.end
        return [((s.x, s.y), (q.x, q.y))]
    if t == "LWPOLYLINE":
        pts = [(p[0], p[1]) for p in e.get_points("xy")]
        if e.closed:
            pts = pts + [pts[0]]
        return list(zip(pts[:-1], pts[1:]))
    if t == "POLYLINE":
        pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
        if e.is_closed:
            pts = pts + [pts[0]]
        return list(zip(pts[:-1], pts[1:]))
    return []


def text_of(e):
    if e.dxftype() == "TEXT":
        halign, valign = e.dxf.get("halign", 0), e.dxf.get("valign", 0)
        p = e.dxf.align_point if (halign or valign) and e.dxf.hasattr("align_point") else e.dxf.insert
        return e.dxf.text.strip(), (p.x, p.y)
    if e.dxftype() == "MTEXT":
        return e.text.strip(), (e.dxf.insert.x, e.dxf.insert.y)
    return None


def load(path):
    try:
        return ezdxf.readfile(path), True, "ezdxf.readfile 成功"
    except Exception as exc:  # noqa: BLE001
        try:
            doc, aud = ezdxf.recover.readfile(path)
            return doc, False, f"readfile 失敗({type(exc).__name__}) → recover で復旧 / 監査エラー {len(aud.errors)}件"
        except Exception as exc2:  # noqa: BLE001
            return None, False, f"recover でも開けず: {type(exc2).__name__}: {exc2}"


# ------------------------------------------------------------------ 採点
def grade(spec, path, sched=None):
    r = {"file": str(path), "checks": [], "score": 0.0, "max": 0.0}

    def add(level, name, pts, maxp, ok, detail):
        r["checks"].append({"level": level, "name": name, "points": round(pts, 2),
                            "max": maxp, "ok": bool(ok), "detail": detail})
        r["score"] += pts
        r["max"] += maxp

    doc, clean, note = load(path)
    if doc is None:
        add("L0", "DXFとして開ける", 0, 10, False, note)
        return r
    add("L0", "DXFとして開ける", 10 if clean else 4, 10, clean, note)

    msp = doc.modelspace()
    ents = list(msp)
    by_layer = {}
    for e in ents:
        by_layer.setdefault(e.dxf.layer, []).append(e)
    r["entity_counts"] = {}
    for e in ents:
        r["entity_counts"][e.dxftype()] = r["entity_counts"].get(e.dxftype(), 0) + 1
    r["layer_counts"] = {k: len(v) for k, v in sorted(by_layer.items())}
    r["dxfversion"] = doc.dxfversion

    def lines_on(*layers):
        segs = []
        for L in layers:
            for e in by_layer.get(L, []):
                segs += segments_of(e)
        return [s for s in segs if math.dist(*s) > TOL]

    def texts_on(layer):
        return [t for t in (text_of(e) for e in by_layer.get(layer, [])) if t]

    # ---- L1 レイヤ
    defined = {l.dxf.name for l in doc.layers}
    req = set(spec["layers"]["required"])
    missing = sorted(req - defined)
    add("L1", "必須レイヤが定義されている", 5 * (1 - len(missing) / len(req)), 5, not missing,
        f"欠落: {missing}" if missing else "全て定義済み")
    zero = len(by_layer.get("0", []))
    add("L1", "0レイヤ直置きがない", 5 if zero == 0 else 0, 5, zero == 0, f"0レイヤ上 {zero}件")

    # ---- L1 壁
    bnd, faces, jambs = boundary(spec)
    wsegs = lines_on("WALL")
    wall_g = [LineString(s) for s in wsegs]
    both = wall_g + [LineString(s) for s in lines_on("OPENING")]
    wall_u = unary_union(wall_g) if wall_g else MultiLineString([])
    both_u = unary_union(both) if both else MultiLineString([])
    wall_len = sum(g.length for g in wall_g)

    cov_f = faces.intersection(wall_u.buffer(TOL)).length if wall_g else 0.0
    cov_j = jambs.intersection(both_u.buffer(TOL)).length if both else 0.0
    exp_len = faces.length + jambs.length
    cov = (cov_f + cov_j) / exp_len if exp_len else 0.0
    add("L1", "壁の線を描けている（被覆率）", 10 * cov, 10, cov > 0.98,
        f"被覆率 {cov*100:.1f}%  (壁面 {cov_f:.0f}/{faces.length:.0f}mm, 小口 {cov_j:.0f}/{jambs.length:.0f}mm)")

    spur = sum(g.length - g.intersection(bnd.buffer(TOL)).length for g in wall_g)
    sr = spur / wall_len if wall_len else 1.0
    add("L1", "WALLレイヤに余計な線がない", 5 * max(0.0, 1 - sr * 2), 5, sr < 0.02,
        f"余分な線 {sr*100:.1f}%  (実長 {wall_len:.0f}mm / 境界外 {spur:.0f}mm)")

    th = spec["wall_thickness"]
    faces_seg = [s for s in wsegs if math.dist(*s) > th + TOL]   # 小口は除外
    good = sum(1 for s in faces_seg if on_wall_face(spec, *s))
    ratio = good / len(faces_seg) if faces_seg else 0.0
    add("L1", f"壁面が芯から±{th/2:.0f}mmに乗っている（壁厚{th}の担保）", 5 * ratio, 5, ratio > 0.98,
        f"適合 {good}/{len(faces_seg)} 線分（小口は対象外）")

    # ---- L2 寸法
    dims = [e for e in ents if e.dxftype() == "DIMENSION"]
    n_exp = sum(len(c["stations"]) if c.get("overall") is not None else len(c["stations"]) - 1
                for c in spec["dimensions"]["chains"])

    # 名前が存在するだけでは不可。空のブロック1個を全DIMENSIONで共有すると
    # CADには寸法が1本も描かれないのに満点が取れてしまう（run_cedar-vent で実証）。
    # AutoCAD は寸法1本につき無名ブロック1個を作るので、専有と非空を要求する。
    used = Counter(d.dxf.geometry for d in dims
                   if d.dxf.hasattr("geometry") and d.dxf.geometry in doc.blocks)
    wf, empty, shared = [], 0, 0
    for d in dims:
        g = d.dxf.geometry if d.dxf.hasattr("geometry") else None
        if g is None or g not in doc.blocks:
            continue
        if len(doc.blocks[g]) == 0:
            empty += 1
            continue
        if used[g] > 1:
            shared += 1
            continue
        wf.append(d)
    why = f"DIMENSION {len(dims)}個 / 作図ブロックあり {len(wf)}個 / 期待 {n_exp}個"
    if empty:
        why += f" ／ 中身が空 {empty}個"
    if shared:
        why += f" ／ 他の寸法と共有 {shared}個"
    add("L2", "DIMENSIONで作図されている（専有の作図ブロックに中身がある）",
        10 * min(1.0, len(wf) / n_exp), 10, len(wf) >= n_exp, why)

    def displayed(d):
        try:
            raw = float(d.get_measurement())
        except Exception:  # noqa: BLE001
            return None
        lit = (d.dxf.get("text", "") or "").strip()
        if lit not in ("", "<>"):
            try:
                return float(lit.replace(",", ""))
            except ValueError:
                return None
        try:
            return raw * float(d.override().get("dimlfac", 1.0) or 1.0)
        except Exception:  # noqa: BLE001
            return raw

    want = []
    for c in spec["dimensions"]["chains"]:
        st = c["stations"]
        want += [st[i + 1] - st[i] for i in range(len(st) - 1)]
        if c.get("overall") is not None:
            want.append(c["overall"])
    hit, shown = 0, []
    for d in dims:
        m = displayed(d)
        if m is None:
            continue
        shown.append(round(m, 1))
        for i, w in enumerate(want):
            if abs(m - w) < TOL:
                want.pop(i)
                hit += 1
                break
    add("L2", "図面に表示される寸法値が仕様と一致する", 10 * hit / n_exp, 10, hit >= n_exp,
        f"一致 {hit}/{n_exp}  表示値={sorted(set(shown))[:14]}")

    fake = sum(1 for e in by_layer.get("DIM", []) if e.dxftype() in ("LINE", "LWPOLYLINE", "POLYLINE", "TEXT", "MTEXT"))
    add("L2", "寸法を線分＋文字で偽装していない", 5 if fake == 0 else 0, 5, fake == 0,
        f"DIMレイヤ上の生の線分/文字 {fake}件" if fake else "偽装なし")

    # ---- L3 開口部
    need_sym = spec.get("openings_requirement", {})
    ok_gap = ok_sym = 0
    for o in spec["openings"]:
        w = wall_of(spec, o["wall"])
        ux, uy, _ = wall_vec(w)
        nx, ny = -uy, ux
        h = th / 2.0
        mid = point_at(w, (o["t0"] + o["t1"]) / 2.0)
        probes = [Point(mid[0] + nx * h, mid[1] + ny * h), Point(mid[0] - nx * h, mid[1] - ny * h)]
        if wall_g and all(p.distance(wall_u) > 5 * TOL for p in probes):
            ok_gap += 1

        rect = opening_rect(spec, o, pad=1.0)
        opes = by_layer.get("OPENING", [])
        if o["type"] == "door" and need_sym.get("door_symbol"):
            hit_s = any(e.dxftype() in ("ARC", "CIRCLE", "INSERT") and
                        Point(e.dxf.center.x, e.dxf.center.y).distance(rect) < o["t1"] - o["t0"] + TOL
                        for e in opes if e.dxf.hasattr("center"))
        elif o["type"] == "window" and need_sym.get("window_symbol"):
            width = o["t1"] - o["t0"]
            hit_s = False
            for e in opes:
                for s in segments_of(e):
                    L = LineString(s)
                    if L.length >= 0.8 * width and L.intersection(rect).length >= 0.8 * width:
                        hit_s = True
            # 壁と平行なガラス線のみ可
        else:
            hit_s = any(LineString(s).intersects(rect) for e in opes for s in segments_of(e))
        ok_sym += 1 if hit_s else 0

    n = len(spec["openings"])
    add("L3", "開口部で壁が欠き込まれている", 6 * ok_gap / n, 6, ok_gap == n, f"欠き込み {ok_gap}/{n}")
    add("L3", "開口部に建具が作図されている", 4 * ok_sym / n, 4, ok_sym == n, f"建具 {ok_sym}/{n}")

    # ---- L3 室名
    rt = texts_on("ROOM")
    found = sum(1 for rm in spec["rooms"]
                if any(rm["name"] in t and room_poly(rm).contains(Point(p)) for t, p in rt))
    add("L3", "室名が正しい室の中に記入されている", 10 * found / len(spec["rooms"]), 10,
        found == len(spec["rooms"]), f"{found}/{len(spec['rooms'])}  検出={[t for t,_ in rt][:10]}")

    # ---- L3 通り芯
    gs = lines_on("GRID")
    GX, GY = spec["grid"]["x"]["coords"], spec["grid"]["y"]["coords"]
    gv = {round(a[0], 1) for a, b in gs if abs(a[0] - b[0]) < TOL}
    gh = {round(a[1], 1) for a, b in gs if abs(a[1] - b[1]) < TOL}
    hx = sum(1 for c in GX if any(abs(c - v) < TOL for v in gv))
    hy = sum(1 for c in GY if any(abs(c - v) < TOL for v in gh))
    add("L3", "通り芯が正しい位置に引かれている", 5 * (hx + hy) / (len(GX) + len(GY)), 5,
        hx == len(GX) and hy == len(GY), f"X {hx}/{len(GX)}  Y {hy}/{len(GY)}")

    gl = {t for t, _ in texts_on("GRID")}
    labels = set(spec["grid"]["x"]["labels"]) | set(spec["grid"]["y"]["labels"])
    got = sum(1 for l in labels if any(l == t or l in t for t in gl))
    add("L3", "通り芯符号が記入されている", 5 * got / len(labels), 5, got == len(labels), f"{got}/{len(labels)}")

    # ---- L3 実寸
    bx = bnd.bounds
    xs = [p[0] for s in wsegs for p in s] or [0]
    ys = [p[1] for s in wsegs for p in s] or [0]
    okw = abs((max(xs) - min(xs)) - (bx[2] - bx[0])) < 2 * TOL
    okh = abs((max(ys) - min(ys)) - (bx[3] - bx[1])) < 2 * TOL
    add("L3", "モデル空間が実寸mm（1:1）", 5 if okw and okh else 0, 5, okw and okh,
        f"壁の外形 {max(xs)-min(xs):.0f} x {max(ys)-min(ys):.0f} mm (期待 {bx[2]-bx[0]:.0f} x {bx[3]-bx[1]:.0f})")

    # ---- L3 注記（面積・建具符号）: spec に annotations がある場合のみ
    ann = spec.get("annotations", {})
    if "room_area" in ann:
        cfg = ann["room_area"]
        at = texts_on(cfg["layer"])
        hit = 0
        misses = []
        for rm in spec["rooms"]:
            want_s = f"{rm['area_m2']:.{cfg['decimals']}f}"
            poly = room_poly(rm)
            if any(want_s in t and poly.contains(Point(p)) for t, p in at):
                hit += 1
            else:
                misses.append(f"{rm['name']}={want_s}")
        add("L3", "各室の面積が正しく計算・記入されている", 10 * hit / len(spec["rooms"]), 10,
            hit == len(spec["rooms"]), f"{hit}/{len(spec['rooms'])}" + (f"  不一致: {misses[:4]}" if misses else ""))

    if "total_area" in ann:
        cfg = ann["total_area"]
        want_s = f"{spec['_total_area_m2']:.{cfg['decimals']}f}"
        ok = any(want_s in t for t, _ in texts_on(cfg["layer"]))
        add("L3", "1階の床面積の合計が正しく記入されている", 3 if ok else 0, 3, ok,
            f"期待 {want_s}  検出={[t for t,_ in texts_on(cfg['layer'])][:4]}")

    if "opening_marks" in ann:
        cfg = ann["opening_marks"]
        at = texts_on(cfg["layer"])
        tolm = cfg.get("tolerance_mm", 1200)
        hit, misses = 0, []
        for o in spec["openings"]:
            mark = cfg["map"].get(o["id"])
            if mark is None:
                continue
            rect = opening_rect(spec, o, pad=0.0)
            if any(mark == t.strip() and Point(p).distance(rect) <= tolm for t, p in at):
                hit += 1
            else:
                misses.append(f"{o['id']}={mark}")
        n = len(cfg["map"])
        add("L3", "建具符号が正しい位置に記入されている", 5 * hit / n, 5, hit == n,
            f"{hit}/{n}" + (f"  欠落: {misses[:4]}" if misses else ""))

    # ---- L4 法規（spec に code がある場合のみ）。正解の図面を必要としない検査。
    if spec.get("code"):
        stair_segs = lines_on(spec.get("stair_layer", "STAIR"))
        areas = {rm["name"]: rm["area_m2"] for rm in spec["rooms"]}
        for name, ok, detail, pts, mx in check_code(spec, sched or {}, stair_segs, areas):
            add("L4", name, pts, mx, ok, detail)

    # ---- L3 階段（spec にある場合のみ）
    if spec.get("stairs"):
        st = spec["stairs"]
        exp = unary_union([LineString(t) for t in st["treads"]])
        act = lines_on(st.get("layer", "STAIR"))
        au = unary_union([LineString(s) for s in act]) if act else MultiLineString([])
        c = exp.intersection(au.buffer(TOL)).length / exp.length if act else 0.0
        add("L3", f"階段の段板を{len(st['treads'])}本描けている", 8 * c, 8, c > 0.98, f"被覆率 {c*100:.1f}%")
        ups = [t for t, _ in texts_on(st.get("layer", "STAIR"))]
        add("L3", "階段に昇り方向（UP）が記入されている", 2 if any("UP" in u.upper() for u in ups) else 0, 2,
            any("UP" in u.upper() for u in ups), f"検出={ups[:4]}")

    r["score"] = round(r["score"], 2)
    return r


# ------------------------------------------------------------------ L5 助言
def advise(spec, path):
    doc, _, _ = load(path)
    if doc is None:
        return []
    S = float(str(spec["scale"]).split(":")[1])
    msp, adv = doc.modelspace(), []

    def note(name, ok, detail):
        adv.append({"name": name, "ok": bool(ok), "detail": detail})

    hs = []
    for d in (e for e in msp if e.dxftype() == "DIMENSION"):
        try:
            ov = d.override()
            hs.append(float(ov.get("dimtxt", 2.5)) * float(ov.get("dimscale", 1.0) or 1.0))
        except Exception:  # noqa: BLE001
            pass
    note("寸法文字が紙面で1.5mm以上", bool(hs) and min(hs) / S >= 1.5,
         f"最小 {min(hs)/S:.2f}mm" if hs else "DIMENSIONなし")

    # JIS Z 8313-10:1998 6.2「文字の大きさの呼びの種類」
    #   漢字 3.5, 5, 7, 10, 14, 20mm ／ 仮名 2.5, 3.5, 5, 7, 10, 14, 20mm
    #   ローマ字・数字・記号は JIS Z 8313-1（呼びは 1.8 から）
    # かつて一律「2.0mm以上」としていたが、2.0 はどの呼びにも無い値だった。
    # MTEXT を見ていなかったのも誤り（生DXFの腕は MTEXT を使う）。
    KANJI, KANA = re.compile(r"[一-鿿]"), re.compile(r"[぀-ヿ]")

    def floor_mm(s):
        return 3.5 if KANJI.search(s) else (2.5 if KANJI.search(s) or KANA.search(s) else 1.8)

    bad, worst = [], None
    for e in msp:
        if e.dxf.layer not in ("ROOM", "GRID", "TEXT"):
            continue
        if e.dxftype() == "TEXT":
            h, s = e.dxf.height, str(e.dxf.text or "")
        elif e.dxftype() == "MTEXT":
            h, s = e.dxf.char_height, str(e.text or "")
        else:
            continue
        need = floor_mm(s)
        mm = h / S
        if worst is None or mm - need < worst[0]:
            worst = (mm - need, mm, need, s[:8])
        if mm + 1e-9 < need:
            bad.append((mm, need, s[:8]))
    if worst is None:
        note("文字の大きさが呼びの下限以上（漢字3.5/仮名2.5mm・JIS Z 8313-10 6.2）", False, "文字なし")
    else:
        note("文字の大きさが呼びの下限以上（漢字3.5/仮名2.5mm・JIS Z 8313-10 6.2）", not bad,
             f"不足 {len(bad)}件／最も厳しい例 「{worst[3]}」 {worst[1]:.2f}mm（要 {worst[2]}mm）")

    # JIS A 0150:1999 10.1.1「基準線は，通常，実線で表現する。」
    # 10.1.2 で一点鎖線は「はっきりとさせるために必要な箇所」に限る条件付き。
    # かつて「通り芯が一点鎖線でないと NG」としていたのは規格に反していたので撤去した。
    # 線の太さの比 1:2:4（10.1.3）は DXF のレイヤ線種からは判定できないので触れない。
    try:
        lt = doc.layers.get("GRID").dxf.linetype
    except Exception:  # noqa: BLE001
        lt = "?"
    note("通り芯の線種（実線・一点鎖線いずれも可／JIS A 0150 10.1）", True, f"GRID線種 = {lt}")

    # JIS A 0150:1999 10.2「…はっきり示す必要がある箇所では，線の片方又は両側に，
    # 細線でかいた円を付ける。」「基準記号は円の近くに置いてもよい。」
    # 円は必須ではなく、記号が円の外にあってもよい。符号の有無だけを見る。
    circ = sum(1 for e in msp if e.dxftype() == "CIRCLE" and e.dxf.layer == "GRID")
    marks = sum(1 for e in msp if e.dxftype() in ("TEXT", "MTEXT") and e.dxf.layer == "GRID")
    n = len(spec["grid"]["x"]["coords"]) + len(spec["grid"]["y"]["coords"])
    note("通り芯に基準記号がある（円は任意／JIS A 0150 10.2）", marks >= n,
         f"符号 {marks}個 / 必要 {n}個（うち丸囲み {circ}個）")

    frame = False
    for e in msp:
        if e.dxftype() in ("LWPOLYLINE", "POLYLINE"):
            pts = [p[:2] for p in e.get_points("xy")] if e.dxftype() == "LWPOLYLINE" \
                else [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            if len(pts) < 4:
                continue
            w = max(p[0] for p in pts) - min(p[0] for p in pts)
            h = max(p[1] for p in pts) - min(p[1] for p in pts)
            if h > 0 and 1.30 <= w / h <= 1.50 and w > 1000:
                frame = True
    note("図面枠・表題欄がある", frame, "A列比率の外枠を検出" if frame else "検出できず")
    return adv


if __name__ == "__main__":
    raw = load_spec(sys.argv[1])
    out = []
    for p in sys.argv[2:]:
        sched = load_schedule(p)
        try:
            spec = resolve(raw, sched)
        except Exception as exc:  # noqa: BLE001  建具表が無い/壊れている＝解決不能
            out.append({"file": str(p), "checks": [{"level": "L0", "name": "建具表から仕様を解決できる",
                        "points": 0, "max": 10, "ok": False, "detail": str(exc)}],
                        "score": 0.0, "max": 10.0, "l5_advisory": []})
            continue
        g = grade(spec, p, sched)
        g["l5_advisory"] = advise(spec, p)
        out.append(g)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    for r in out:
        pct = 100 * r["score"] / r["max"] if r["max"] else 0
        print(f"\n{'='*76}\n{Path(r['file']).name}   {r['score']}/{r['max']}  ({pct:.1f}%)", file=sys.stderr)
        if "entity_counts" in r:
            print(f"  entities: {r['entity_counts']}\n  layers  : {r['layer_counts']}", file=sys.stderr)
        for c in r["checks"]:
            print(f"  [{c['level']}] {'OK ' if c['ok'] else 'NG '}{c['points']:5.1f}/{c['max']:<3} "
                  f"{c['name']}  -- {c['detail']}", file=sys.stderr)
        if r.get("l5_advisory"):
            print("  --- L5 製図の作法（点数外・助言） ---", file=sys.stderr)
            for c in r["l5_advisory"]:
                print(f"  [L5] {'OK ' if c['ok'] else 'NG '}      {c['name']}  -- {c['detail']}", file=sys.stderr)

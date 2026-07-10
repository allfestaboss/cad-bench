#!/usr/bin/env python3
"""競合 Dessia の "2D Checker" が DIMLFAC の誤りを検出できるかを確かめる。

Dessia (dessia.io) は 2D図面の自動検査を商品にしている唯一の実在プレイヤー。
公開されている検査項目（2026-07-10 時点、原文）:

    Tag-to-drawing presence        BOMのタグが図面のどこかに存在するか
    Tag-to-grid alignment          タグの座標が正しいグリッドセルに載っているか
    BOM-to-drawing consistency     数量・参照・メタデータが一致するか
    Title block integrity          表題欄の必須項目が埋まっているか
    GD&T compliance                公差の値が規格に沿った書式か
    Dimension chain compliance     "Chained dimensions sum correctly to overall dimensions"

最後の項目は **印字された数字どうし** を足し合わせる検査であって、
描かれた線の長さ（幾何）とは照合していない、というのが我々の読み。

ここではその検査を実装し、DIMLFAC=100 で汚染した図面に当てて、
通り抜けるかどうかを実測する。

  usage: .venv/bin/python checker/dessia_probe.py
  前提:  checker/adversarial.py を先に走らせて out/evil_dimlfac.dxf を作っておく
         （無ければ自動で作る）
"""
from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import ezdxf

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "bin" / "python")
REF = ROOT / "reference" / "reference_t003.dxf"
EVIL = ROOT / "out" / "evil_dimlfac.dxf"


def displayed(d):
    """CAD が図面に実際に描く数値。内部の計測値ではない。"""
    raw = float(d.get_measurement())
    lit = (d.dxf.get("text", "") or "").strip()
    if lit not in ("", "<>"):
        try:
            return float(lit.replace(",", ""))
        except ValueError:
            return None
    return raw * float(d.override().get("dimlfac", 1.0) or 1.0)


def dessia_dimension_chain_check(dims_indiv, dim_overall):
    """Dessia の "Chained dimensions sum correctly to overall dimensions"。
    印字値だけを見る。幾何は参照しない。"""
    total = sum(displayed(d) for d in dims_indiv)
    return abs(total - displayed(dim_overall)) < 1e-6, total


def our_check(d):
    """我々の検査: 印字値が幾何と一致するか。"""
    return abs(float(d.get_measurement()) - displayed(d)) < 1e-6


def probe(label, path):
    doc = ezdxf.readfile(path)
    chains = defaultdict(list)
    for e in doc.modelspace():
        if e.dxftype() == "DIMENSION":
            chains[round(e.dxf.defpoint.y, 0)].append(e)   # 寸法線の位置で系統を分ける

    indiv = chains[-1600.0]      # 南面 通り芯間（T003 の base=-1600）
    overall = chains[-2600.0][0] # 南面 総寸法（overall_base=-2600）

    passed, total = dessia_dimension_chain_check(indiv, overall)
    g_i, s_i = float(indiv[0].get_measurement()), displayed(indiv[0])
    g_o, s_o = float(overall.get_measurement()), displayed(overall)

    print(f"\n■ {label}   [南面 通り芯間の寸法系統]")
    print(f"   個別 {len(indiv)}本 : 幾何 {g_i:.0f}mm → 図面に印字 {s_i:.0f}")
    print(f"   総寸法       : 幾何 {g_o:.0f}mm → 図面に印字 {s_o:.0f}")
    print(f"   Dessia式「連鎖寸法の和 = 総寸法」 : {total:.0f} vs {s_o:.0f}"
          f"  → {'通過' if passed else '検出'}")
    ok = all(our_check(d) for d in indiv + [overall])
    print(f"   我々の「印字値 = 幾何」           : {'一致' if ok else '不一致'}")
    return passed, ok


if __name__ == "__main__":
    if not EVIL.exists():
        subprocess.run([PY, str(ROOT / "checker" / "adversarial.py")],
                       check=True, capture_output=True, cwd=ROOT)
    a = probe("無傷の参照解", REF)
    b = probe("DIMLFAC=100 で汚染した図面", EVIL)

    print(f"""
{'-'*78}
結果:
  無傷の図面           Dessia式={'通過' if a[0] else '検出'}   印字=幾何 {'一致' if a[1] else '不一致'}
  DIMLFAC=100 の図面   Dessia式={'通過' if b[0] else '検出'}   印字=幾何 {'一致' if b[1] else '不一致'}

  → 印字値が全て100倍になっても、和も100倍になるので連鎖は閉じる。
     「幅910メートルの木造住宅」は Dessia の寸法チェーン検査を満点で通過する。
     印字された数字どうしの整合と、印字と幾何の整合は、別の検査である。

留保: これは Dessia が公開している検査項目の記述から我々が再実装したもので、
      実製品を動かして確かめたわけではない。彼らの実装が幾何も見ている可能性は残る。
      公開コード(volmdlr, 68k行)には DXF も DIMENSION も一切現れない。
{'-'*78}""")

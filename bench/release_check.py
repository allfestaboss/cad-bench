#!/usr/bin/env python3
"""公開前の版ズレ検査。

**Zenodo は `.zenodo.json` を権威として読む。**CITATION.cff だけ上げて
`.zenodo.json` を放置すると、Zenodo は古いメタデータで新しい中身を登録する。
ai-reach-paper で実際に起きた: v1.3.0 の zip が **1.2.0 として** DOI を取った。

このリポでは `.zenodo.json` に `version` 欄を置いていない（Zenodo がタグから
版を採る）ので、ズレるのは**要旨の側**である。だからここでは要旨を見る。

**関門にする条件は誤検出の率で決めてある。**
「現行版が要旨に出てこない」だけを条件にすると、版段落を持たない初版
（v1.0.0）で必ず鳴る。**毎回鳴る警報は無視する癖を作る**ので、そうしない。

  落とす: 要旨が版に言及しているのに、**現行版だけが無い**（追随漏れ）
  落とす: 初版でないのに、要旨が版に一度も言及していない（版段落の書き漏れ）
  通す  : 初版で、版への言及が無い（正常）
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VER = re.compile(r"\b\d+\.\d+\.\d+\b")


def main() -> int:
    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    m = re.search(r'^version:\s*"?([^"\s]+)"?', cff, re.M)
    if not m:
        print("[NG] CITATION.cff に version が無い")
        return 1
    cur = m.group(1)

    zj = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))

    # .zenodo.json が版を明示しているなら、そちらが優先されるので厳密に一致させる
    pinned = zj.get("version")
    if pinned is not None and pinned != cur:
        print(f"[NG] 版がズレている。CITATION.cff={cur} / .zenodo.json={pinned}")
        print(f"     **このまま release を切ると Zenodo は {pinned} として登録する。**")
        return 1

    desc = re.sub("<[^>]+>", " ", zj.get("description", ""))
    seen = sorted(set(VER.findall(desc)))

    if not seen:
        if cur == "1.0.0":
            print(f"[OK] 公開メタデータ  v{cur}（初版。版段落なしで正常）")
            return 0
        print(f"[NG] v{cur} なのに .zenodo.json の要旨が版に一度も触れていない")
        print("     **初版でない公開は、何が変わったかを要旨に書く。**")
        return 1

    if cur not in seen:
        print(f"[NG] .zenodo.json の要旨が v{cur} に追随していない（記載: {', '.join(seen)}）")
        print("     **Zenodo はこの要旨で登録する。中身より古い説明が DOI に付く。**")
        return 1

    print(f"[OK] 公開メタデータ  v{cur} が要旨に記載あり")
    return 0


if __name__ == "__main__":
    sys.exit(main())

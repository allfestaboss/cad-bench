#!/usr/bin/env bash
# 使い方: ./run.sh [T001 T002 ...]   引数なしで全課題
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
TASKS=("$@"); [ ${#TASKS[@]} -eq 0 ] && TASKS=($(ls tasks))

mkdir -p out

# 凍結／事後記録の検算。課題文・参照解・腕への文面が答案の後に動いていたら止める。
$PY -m bench.freeze > out/_freeze.txt 2>&1 || {
  echo "凍結が破れている。out/_freeze.txt を見ること。"; cat out/_freeze.txt; exit 1; }
echo "凍結OK: $(grep -c '^\[OK' out/_freeze.txt) 課題"

for T in "${TASKS[@]}"; do
  SPEC="tasks/$T/spec.json"
  $PY bench/resolve.py "$SPEC" "out/${T}_resolved.json" 2>/dev/null || true
  REF="reference/reference_$(echo "$T" | tr 'A-Z' 'a-z').dxf"
  $PY bench/build_ref.py "$SPEC" "$REF"

  FILES=("$REF")
  for f in attempts/$T/*.dxf; do [ -e "$f" ] && FILES+=("$f"); done

  $PY bench/check.py "$SPEC" "${FILES[@]}" > "out/${T}.json" 2> "out/${T}.txt"
  $PY checker/render.py "${FILES[@]}" > /dev/null 2>&1 || true

  T="$T" $PY - <<'PY'
import json, os, pathlib
T = os.environ["T"]
rows = json.loads(pathlib.Path(f"out/{T}.json").read_text())
lv = ["L0", "L1", "L2", "L3", "L4"]
w = 24
print(f"\n== {T} ==")
print(f"{'提出':<{w}}" + "".join(f"{l:>8}" for l in lv) + f"{'合計':>11}{'%':>8}{'L5':>7}")
print("-" * (w + 8*len(lv) + 26))
for r in rows:
    name = pathlib.Path(r["file"]).stem.replace(f"reference_{T.lower()}", "reference")
    got = {l: 0.0 for l in lv}; mx = {l: 0.0 for l in lv}
    for c in r["checks"]:
        got[c["level"]] += c["points"]; mx[c["level"]] += c["max"]
    adv = r.get("l5_advisory", [])
    l5 = f"{sum(1 for a in adv if a['ok'])}/{len(adv)}" if adv else "-"
    cells = "".join((f"{got[l]:.0f}/{mx[l]:.0f}" if mx[l] else "-").rjust(8) for l in lv)
    pct = 100*r["score"]/r["max"] if r["max"] else 0
    print(f"{name:<{w}}{cells}{r['score']:>7.1f}/{r['max']:<3.0f}{pct:>7.1f}%{l5:>7}")
print()
for r in rows:
    fails = [c for c in r["checks"] if not c["ok"]]
    if fails:
        print(f"■ {pathlib.Path(r['file']).stem} の失点:")
        for c in fails:
            print(f"   [{c['level']}] -{c['max']-c['points']:.1f}点  {c['name']}\n           {c['detail']}")
PY
done
echo
echo "詳細: out/<TASK>.txt  /  画像: reference/*.png attempts/*/*.png"

# 公開メタデータの版ズレ（Zenodo は .zenodo.json を権威として読む）
$PY bench/release_check.py || exit 1

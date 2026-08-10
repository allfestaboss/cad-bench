"""課題を凍結し、答案が書かれたあとに動いていないことを機械で確かめる。

    python3 -m bench.freeze T001 --stamp      # 凍結する（**答案がまだ無いときだけ**）
    python3 -m bench.freeze T001 --baseline   # 事後記録（答案が既にあるとき）
    python3 -m bench.freeze                   # 全課題を検算する

**なぜ要るか。**

シリーズの別のベンチ（bim-bench）で、**答案を読んだあとに課題文と採点器の両方を
書き換えていた**ことが分かり、その課題の結論は撤回になった。改訂が動かした点数のほうが、
示したとされる腕間差より大きかった。「走らせる前に凍結する」を人の記憶で守るのは無理で、
鍵を取って照合するしかない。

**2層に分ける。**

  硬  課題文 / 参照解 / 腕に渡した文面
      答案が存在したあとに動いたら、その課題の点数は測定ではない。**落とす。**
  軟  採点器・生成器・敵対テスト・各種検査
      課題を足せば必ず動く共有コード。動いたこと自体は罪ではない。
      罪なのは動いた結果として参照解や点数が変わることで、それは硬の層が捕まえる。
      **報告だけして止めない。**

**凍結と事後記録は違う。**

`--stamp` は答案が1本でもあると拒否する。答案を見たあとに凍結し直すのは、
bim-bench の T004 を撤回に追い込んだ改訂と同じだからである。
既に走り終えた課題には `--baseline` を使う。これは**凍結ではない。**
過去を保証しない。**これから先の改変を検出できるようにするだけ**である。
その区別はファイル名（`FROZEN_` と `BASELINE_`）と中身の `kind` に書いてある。

**腕に渡した文面について。**

本ベンチには `arms/` が無い。**腕が実際に読んだ文面はどこにも記録されていない。**
これはシリーズ8本のうち6本に共通する欠落で、bim-bench で
「凍結はテンプレートを覆っていたが差し込みを覆っていなかった」と気づいて分かった。
次に課題を起こすときは、差し込み済みの完成形を `arms/<課題>_<腕>.md` に置き、
硬の層に入れること。この検査は既にそのパスを見るようになっている。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TASK_FILE = "spec.json"

# **参照解（DXF）は硬の層に入れない。**
#
# 本ベンチは run.sh が毎回 build_ref.py で参照解を生成し直す。DXF は作成時刻
# （ユリウス日）と GUID と辞書の並びを含むので、**中身が同じでもバイトは毎回変わる。**
# それをハッシュで縛ると、走らせるたびに必ず発火する。
#
# 実際そうなった。基準を取り、run.sh が再生成し、ハッシュが変わり、
# **検査を入れた行為そのものが参照解を書き換えて commit された。**
# 幾何も点数も変わっていない（旧版と新版を採点器に並べて全項目一致を確認済み）が、
# 公開済みの参照解のバイトを動かしたことに変わりはない。
#
# **毎回必ず鳴る警報は、無視する癖を作る。**関門としても失敗である。
#
# そこで守る対象を入力に移す。**生成物は入力から再現できるので、縛るべきは入力のほう。**
# 参照解が入力と食い合っているかは `verify_ref()` が意味で見る。
REF_PATTERNS = []
ANSWER_GLOB = "*.dxf"


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def hard_paths(task: str) -> list[Path]:
    low = task.lower()
    out = [ROOT / "tasks" / task / TASK_FILE]
    out += [ROOT / p.format(task=task, low=low) for p in REF_PATTERNS]
    arms = ROOT / "arms"
    if arms.is_dir():
        out += sorted(arms.glob(f"{task}_*.md"))
    return [p for p in out if p.exists()]


def soft_paths() -> list[Path]:
    out = []
    for d in ("bench", "checker"):
        p = ROOT / d
        if p.is_dir():
            out += [f for f in sorted(p.glob("*.py")) if f.name != "freeze.py"]
    return out


def verify_ref(task: str) -> str | None:
    """参照解を生成し直して、**意味**が一致するか見る。バイトでは見ない。

    DXF は毎回バイトが変わる（作成時刻・GUID・辞書の並び）ので、
    採点器に現行版と生成し直した版を並べて通し、全項目の点数が一致するかで判定する。
    **これが「参照解が動いていない」の意味である。**

    **2つの罠を踏んだので、その対策が入っている。**

    1. **検査が成果物を書き換えてはいけない。**最初の実装は本物の参照解の上に
       生成し直していた。参照解のバイトが変わり、それを気づかず commit した
       （幾何も点数も同一だったが、公開済みのバイトを動かしたことに変わりはない）。
       いまは一時ファイルにだけ書き、**本物には触れない。**
    2. **一時ファイルは参照解と同じディレクトリに置く。**採点器は建具表を
       `<stem>.schedule.json` として**隣から**探す。`/tmp` に置くと建具表が
       見つからず「解決できない」と出る。**中身ではなく置き場所が原因の誤検出だった。**
    """
    import subprocess, tempfile
    ref = ROOT / f"reference/reference_{task.lower()}.dxf"
    spec = ROOT / "tasks" / task / TASK_FILE
    if not ref.exists() or not spec.exists():
        return None
    py = ROOT / ".venv/bin/python"
    py = str(py) if py.exists() else sys.executable
    tmp = ref.with_name(f".verify_{task.lower()}.dxf")   # **隣に置く**
    sched = Path(str(ref).rsplit(".", 1)[0] + ".schedule.json")
    tmp_sched = Path(str(tmp).rsplit(".", 1)[0] + ".schedule.json")
    try:
        r = subprocess.run([py, "bench/build_ref.py", str(spec), str(tmp)],
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            return f"参照解を生成し直せない: {r.stderr.strip()[:120]}"
        if sched.exists():
            tmp_sched.write_bytes(sched.read_bytes())
        g = subprocess.run([py, "bench/check.py", str(spec), str(ref), str(tmp)],
                           cwd=ROOT, capture_output=True, text=True)
        try:
            a, b = json.loads(g.stdout)
        except Exception as e:
            return f"採点器で比べられない: {e}"
        diff = [c1["name"] for c1, c2 in zip(a["checks"], b["checks"])
                if c1["points"] != c2["points"]]
        if diff:
            return "生成し直すと点数が変わる項目: " + " / ".join(diff[:4])
    finally:
        for f in (tmp, tmp_sched):
            if f.exists():
                f.unlink()
    return None


def answers(task: str) -> list[Path]:
    d = ROOT / "attempts" / task
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob(ANSWER_GLOB)
                  if p.is_file() and p.name not in ("cost.json",)
                  and not p.name.endswith(("_report.md", ".bak")))


def record(task: str, mode: str) -> int:
    have = answers(task)
    if mode == "stamp" and have:
        print(f"**凍結できない。**{task} には既に答案が {len(have)}本ある。")
        print("答案を見たあとに凍結するのは、bim-bench の T004 を撤回に追い込んだ改訂と同じである。")
        print("既に走り終えた課題には --baseline を使うこと（凍結ではなく事後記録）。")
        return 1
    if mode == "baseline" and not have:
        print(f"{task} にはまだ答案が無い。--stamp で本当の凍結ができる。")
        return 1

    hp, sp = hard_paths(task), soft_paths()
    if not hp:
        print(f"{task}: 課題文も参照解も見つからない。")
        return 1
    doc = {
        "task": task,
        "kind": ("腕を走らせる前に凍結した" if mode == "stamp" else
                 "**事後記録であって凍結ではない。**過去を保証しない。"
                 "これから先の改変を検出できるようにするだけである"),
        "answers_at_record": [p.name for p in have],
        "arms_prompt_recorded": bool([p for p in hp if p.parent.name == "arms"]),
        "hard": {str(p.relative_to(ROOT)): digest(p) for p in hp},
        "soft": {str(p.relative_to(ROOT)): digest(p) for p in sp},
    }
    name = ("FROZEN_" if mode == "stamp" else "BASELINE_") + task + ".json"
    out = ROOT / "tasks" / task / name
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out.relative_to(ROOT)}: 硬{len(doc['hard'])}件 / 軟{len(doc['soft'])}件"
          + ("" if doc["arms_prompt_recorded"] else "   ※腕に渡した文面の記録が無い"))
    return 0


def verify(task: str) -> int:
    d = ROOT / "tasks" / task
    f = next((d / n for n in (f"FROZEN_{task}.json", f"BASELINE_{task}.json")
              if (d / n).exists()), None)
    if f is None:
        print(f"[--] {task}: 記録が無い（--stamp / --baseline で作る）")
        return 0
    doc = json.loads(f.read_text(encoding="utf-8"))
    frozen = f.name.startswith("FROZEN_")
    have = answers(task)

    def drift(tier):
        out = []
        for rel, want in (doc.get(tier) or {}).items():
            p = ROOT / rel
            got = digest(p) if p.exists() else "(無い)"
            if got != want:
                out.append((rel, want, got))
        return out

    hard, soft = drift("hard"), drift("soft")
    label = "凍結" if frozen else "事後記録"
    bad_ref = verify_ref(task)
    if bad_ref:
        print(f"[NG] {task}: **参照解が入力と食い違っている** — {bad_ref}")
        return 1
    if not hard and not soft:
        n = len(doc["hard"]) + len(doc["soft"])
        print(f"[OK] {task}: {label}の {n}件は動いていない"
              f"（答案 {len(have)}本 / 参照解は生成し直しても意味が一致）")
        return 0
    for rel, want, got in soft:
        print(f"[--] {task}: 共有コードが動いた {rel}  {want[:12]} -> {got[:12]}")
    if not hard:
        print(f"     課題文・参照解は動いていないので、点数は測定のままである。")
        return 0
    print(f"[NG] {task}: **課題文か参照解か腕への文面が動いている**")
    for rel, want, got in hard:
        print(f"     {rel:<40} {want[:12]} -> {got[:12]}")
    if not have:
        print("     答案がまだ無いので設計である。記録を取り直すこと。")
        return 0
    print("     **答案が存在したあとに動いている。この課題の点数は測定として使えない。**")
    return 1


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tasks = args or [d.name for d in sorted((ROOT / "tasks").iterdir()) if d.is_dir()]
    if "--stamp" in sys.argv or "--baseline" in sys.argv:
        mode = "stamp" if "--stamp" in sys.argv else "baseline"
        return 1 if sum(record(t, mode) for t in tasks) else 0
    return 1 if sum(verify(t) for t in tasks) else 0


if __name__ == "__main__":
    sys.exit(main())

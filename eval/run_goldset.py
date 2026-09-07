#!/usr/bin/env python3
"""eval-gate(KB-377/KB-419)—— goldset-kb-v4 → gold_key@k,守冻结基线。

goldset v4(2026-06-10,KB-419):中央语料 identity 口径(repo:domain:slug),
368 query / 103 doc,10xOpus 生成 + 对抗审计闭环(host-local
eval/weave-search-eval/data/goldgen-v4/)。gold_key 与检索结果 **exact match**
(identity 中间段是 domain,slug 跨域有实测撞名 → 不做 norm);gold→repo 路由 =
identity 首段,未知仓大声 KeyError 不兜底。启动先做漂移自检:goldset 全部
gold_key 必须 ⊆ lexical 引擎已加载 doc keys,缺失即 FAIL——语料口径再漂移时
第一时间炸,而不是默默跑出全红假数(KB-419 的教训)。

跑: uv run python eval/run_goldset.py            (lexical gate, poe eval)
    uv run python eval/run_goldset.py --lane hybrid --protect   (poe eval-hybrid)
BASELINE/HYBRID_BASELINE 为空占位时进 REBASELINE 模式:只报数不判闸,跑完把
数字回填常量再复跑确认。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

from memex.engine import Engine
from memex.hybrid import HybridEngine
from memex.semantic import SemanticEngine

_DEFAULT_GOLD = Path(
    os.environ.get(
        "KB_EVAL_GOLDSET",
        str(Path.home() / "workspace/data/personal/kb-eval/data/goldset_kb_v5.jsonl"),
    )
)
# eval 跑分输出: 可重建 runtime, 出 hot tree → XDG state(OPS-546); env 可配
_DEFAULT_RESULTS = Path(
    os.environ.get(
        "KB_EVAL_RESULTS",
        str(Path.home() / ".local/state/memex/eval-results"),
    )
)
_MARGIN = 0.01  # 同算法同语料,应近精确复现;留极小容差
_HYBRID_MARGIN = 0.01  # hybrid ≥ 单 lane 较好者,留极小噪声容差

# 大仓单独 track(n≥30);其余聚合 _repo_group=long_tail(小仓单 slice 纯噪声)。
_BIG_REPOS = ("rhizome", "eridanus-ops", "docket-kb", "logistics-kb")

# lexical 闸冻结基线:rebaseline 到 2026-06-23 语料/identity(ERI-608,承接 ADR-035 改名 +
# goldset v5 迁移到当前 registry name 474 题)。lexical 随语料增长(11 天 freight rollout)
# 近邻稀释整体下行(_overall 0.9853→0.9599),hybrid 补偿后基本持平(见 HYBRID_BASELINE)。
BASELINE = {
    "_overall": 0.9599,
    "_repo_true=rhizome": 0.9565,
    "_repo_true=eridanus-ops": 0.9714,
    "_repo_true=docket-kb": 1.0,
    "_repo_true=logistics-kb": 0.9146,
    "_repo_group=long_tail": 1.0,
    "_slice=zh_low_anchor": 0.9286,
}
# hybrid --protect 闸的绝对地板:rebaseline 到 2026-06-23 单轮实测(ERI-608)。hybrid 用
# semantic+RRF+protection 补偿了 lexical 的近邻稀释,_overall 仅 0.9916→0.9873(基本持平);
# 地板被语料自然增长顶破时 = goldset 陈旧信号,按 KB-375 式刷新而非放宽 margin。
HYBRID_BASELINE = {
    "_overall": 0.9873,
    "_repo_true=rhizome": 0.987,
    "_repo_true=eridanus-ops": 0.9857,
    "_repo_true=docket-kb": 1.0,
    # 小切片(n<150)有 query-embedding GPU 噪声;logistics-kb 因 11 天 freight rollout
    # 语料增长 0.988→0.9756(近邻稀释,非回归), rebaseline 接受为新地板。
    "_repo_true=logistics-kb": 0.9756,
    "_repo_group=long_tail": 1.0,
    "qtype=TB": 0.9873,
    "qtype=NL": 0.9873,
    "_slice=zh_low_anchor": 0.9921,
    "_slice=lexical_dependent": 0.9856,
}
# hybrid 相对闸 tracked slices(principal 拍:hybrid ≥ max(lexical, semantic) per slice)。
_HYBRID_TRACKED = (
    "_overall",
    "_repo_true=rhizome",
    "_repo_true=eridanus-ops",
    "_repo_true=docket-kb",
    "_repo_true=logistics-kb",
    "_repo_group=long_tail",
    "qtype=TB",
    "qtype=NL",
    "_slice=zh_low_anchor",
    "_slice=lexical_dependent",
)


def score(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    gk = {1: 0, 3: 0, 5: 0, 8: 0, 10: 0}
    mrr = miss = 0.0
    for r in rows:
        rk = r["rank"]
        if rk == 0:
            miss += 1
            continue
        mrr += 1.0 / rk
        for k in gk:
            if rk <= k:
                gk[k] += 1
    return {
        "n": n,
        "no_hit": int(miss),
        # @3/@8 服务 recall 默认 --limit 定档(KB-337 follow-up),不进闸。
        **{f"gold_key@{k}": round(v / n, 4) for k, v in gk.items()},
        "mrr_gold": round(mrr / n, 4),
    }


def _preembed(
    sem: SemanticEngine, gold: list[dict], batch: int
) -> dict[str, list[float]]:
    """批量预 embed(8B 模型,逐条串行太慢);按 query text 缓存向量。"""
    qtexts = [q["query"] for q in gold]
    vec_by_q: dict[str, list[float]] = {}
    for i in range(0, len(qtexts), batch):
        chunk = qtexts[i : i + batch]
        for t, v in zip(chunk, sem.embed(chunk), strict=True):
            vec_by_q[t] = v
        print(f"  embedded {min(i + batch, len(qtexts))}/{len(qtexts)}", flush=True)
    return vec_by_q


def _drift_check(engine: Engine, gold: list[dict]) -> None:
    """goldset gold_key ⊆ 引擎已加载 doc keys;缺失 = 语料口径漂移,立即炸。"""
    loaded = {d.object_key for idx in engine.repos.values() for d in idx.docs}
    missing = sorted({q["gold_key"] for q in gold} - loaded)
    if missing:
        print(
            f"✗ DRIFT CHECK FAILED: {len(missing)} 个 gold_key 不在已加载语料(口径漂移,eval 无意义):"
        )
        for k in missing:
            print(f"    {k}")
        sys.exit(1)


def _search_keys_for_lane(
    args: argparse.Namespace, gold: list[dict]
) -> Callable[[str, str], list[str]]:
    # lane → search_keys(query_text, repo) -> top-10 identity 列表。
    if args.lane == "lexical":
        engine = Engine()
        print(
            f"[lexical] active repos: {', '.join(f'{n}={ix.n}' for n, ix in engine.repos.items())}",
            flush=True,
        )
        _drift_check(engine, gold)

        def search_keys(qtext: str, repo: str) -> list[str]:
            return [h.object_key for h in engine.search(qtext, k=10, repo=repo)]
    elif args.lane == "semantic":
        _drift_check(Engine(), gold)
        sem = SemanticEngine()

        def search_keys(qtext: str, repo: str) -> list[str]:
            # 当前 SemanticEngine.search 内部 embed + 中央 collection(ADR-035 后),
            # 不再外部预 embed + per-root collections。
            return [h.object_key for h in sem.search(qtext, k=10, repo=repo)]
    else:  # hybrid
        hy = HybridEngine(protect_anchored=args.protect, kind_prior=args.kind_prior)
        print(
            f"[hybrid] protect_anchored={hy.protect_anchored} kind_prior={hy.kind_prior} | repos: {sorted(hy.lexical.repos)} | collections: {hy.semantic.collections}",
            flush=True,
        )
        _drift_check(hy.lexical, gold)

        def search_keys(qtext: str, repo: str) -> list[str]:
            # 当前 HybridEngine.search 内部自走 embed + 中央 collection(ADR-035 后架构),
            # 不再外部预 embed 传 query_vector(旧 per-root 设计)。
            return [h.object_key for h in hy.search(qtext, k=10, repo=repo)]

    return search_keys


def _evaluate(
    gold: list[dict], search_keys: Callable[[str, str], list[str]]
) -> list[dict]:
    rows = []
    for q in gold:
        repo = q["gold_key"].split(":", 1)[
            0
        ]  # identity 首段;未知仓 engine 大声 KeyError
        keys = search_keys(q["query"], repo)
        rank = next((i for i, kk in enumerate(keys, 1) if kk == q["gold_key"]), 0)
        rows.append(
            {
                **q,
                "rank": rank,
                "_repo_true": repo,
                "_repo_group": repo if repo in _BIG_REPOS else "long_tail",
            }
        )

    return rows


def _slices(rs: list[dict]) -> dict:
    out = {"_overall": score(rs)}
    for dim in ("qtype", "_slice", "_repo_true", "_repo_group"):
        for v in sorted({r[dim] for r in rs}):
            out[f"{dim}={v}"] = score([r for r in rs if r[dim] == v])
    return out


def _write_report(
    args: argparse.Namespace, gold: list[dict], s: dict, out_path: Path
) -> None:
    report = {
        "lane": args.lane,
        "gold": args.gold.name,
        "n_queries": len(gold),
        "slices": s,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {out_path}\n")

    for k in _HYBRID_TRACKED:
        if k in s:
            v = s[k]
            print(
                f"  {k:34} n={v.get('n'):3} gold@10={v.get('gold_key@10')} gold@5={v.get('gold_key@5')} mrr={v.get('mrr_gold')} no_hit={v.get('no_hit')}"
            )


def _check_hybrid_relative(s: dict, d: Path, failed: list[str]) -> None:
    lex_s = json.loads((d / "lexical_goldset.json").read_text())["slices"]
    sem_s = json.loads((d / "semantic_goldset.json").read_text())["slices"]
    print(
        "\n=== HYBRID GATE (hybrid ≥ 单 lane 较好者 per slice, margin",
        _HYBRID_MARGIN,
        ") ===",
    )
    for key in _HYBRID_TRACKED:
        h = s.get(key, {}).get("gold_key@10", 0.0)
        lx = lex_s.get(key, {}).get("gold_key@10", 0.0)
        sm = sem_s.get(key, {}).get("gold_key@10", 0.0)
        best = max(lx, sm)
        ok = h >= best - _HYBRID_MARGIN
        print(
            f"  {'PASS' if ok else 'FAIL'}  {key:34} hybrid={h}  lex={lx} sem={sm} max={best}  Δ={round(h - best, 4):+}"
        )
        if not ok:
            failed.append(key)


def _check_hybrid_floor(s: dict, failed: list[str]) -> None:
    print(
        "\n=== HYBRID ABSOLUTE FLOOR (vs HYBRID_BASELINE, margin",
        _HYBRID_MARGIN,
        ") ===",
    )
    for key, base in HYBRID_BASELINE.items():
        got = s.get(key, {}).get("gold_key@10", 0.0)
        ok = got >= base - _HYBRID_MARGIN
        print(
            f"  {'PASS' if ok else 'FAIL'}  {key:34} got={got}  base={base}  Δ={round(got - base, 4):+}"
        )
        if not ok:
            failed.append(f"floor:{key}")


def _report_kind_prior(s: dict, default_file: Path) -> None:
    base_s = json.loads(default_file.read_text())["slices"]
    print("\n=== kind-prior vs current default(hybrid --protect)per slice ===")
    regressed = []
    improved = False
    for key in _HYBRID_TRACKED:
        for metric in ("gold_key@10", "gold_key@5", "mrr_gold"):
            c = s.get(key, {}).get(metric, 0.0)
            b = base_s.get(key, {}).get(metric, 0.0)
            delta = round(c - b, 4)
            flag = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
            print(
                f"  {flag}  {key:34} {metric:12} candidate={c}  default={b}  Δ={delta:+}"
            )
            if delta < -_HYBRID_MARGIN:
                regressed.append(f"{key}:{metric}")
            if delta > 0:
                improved = True
    verdict = "FLIP ON" if not regressed and improved else "KEEP OFF"
    print(
        f"\n  KB-334 promotion: {verdict}"
        + (f"(回归: {regressed})" if regressed else "(无回归)")
    )


def _report_protection(s: dict, base_file: Path) -> None:
    base_s = json.loads(base_file.read_text())["slices"]
    print("\n=== 选项2 vs baseline hybrid(flag off)per slice ===")
    regressed = []
    for key in _HYBRID_TRACKED:
        h = s.get(key, {}).get("gold_key@10", 0.0)
        b = base_s.get(key, {}).get("gold_key@10", 0.0)
        delta = round(h - b, 4)
        flag = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
        print(f"  {flag}  {key:34} protected={h}  baseline={b}  Δ={delta:+}")
        if delta < -_HYBRID_MARGIN:
            regressed.append(key)
    verdict = (
        "FLIP ON"
        if not regressed
        and any(
            s.get(k, {}).get("gold_key@10", 0.0)
            > base_s.get(k, {}).get("gold_key@10", 0.0)
            for k in _HYBRID_TRACKED
        )
        else "KEEP OFF"
    )
    print(
        f"\n  §I9 promotion: {verdict}"
        + (f"(回归: {regressed})" if regressed else "(无回归)")
    )


def _hybrid_gate(args: argparse.Namespace, s: dict, out_path: Path) -> int:
    rebaseline = args.protect and HYBRID_BASELINE.get("_overall", 0.0) == 0.0
    if rebaseline:
        print(
            "\n*** REBASELINE MODE: HYBRID_BASELINE 为占位,绝对地板不判;回填常量后复跑 ***"
        )
    d = out_path.parent
    failed = []
    _check_hybrid_relative(s, d, failed)
    if args.protect and not rebaseline:
        _check_hybrid_floor(s, failed)
    # kind-prior 促升闸(KB-334,ADR-023 条5):candidate(protect+kind_prior)vs
    # current default(protect)。gold@10 近天花板 → 闸含排序敏感指标 @5/mrr。
    default_file = d / "hybrid_protected_goldset.json"
    if args.kind_prior and default_file.exists():
        _report_kind_prior(s, default_file)
    elif args.kind_prior:
        print(f"\n*** kind-prior 闸跳过: 缺 current default 成绩单 {default_file} ***")
    # 选项 2 开关:对比 baseline hybrid(flag off),看是否净改善 + 无回归(§I9 promotion gate)。
    base_file = d / "hybrid_goldset.json"
    if args.protect and not args.kind_prior and base_file.exists():
        _report_protection(s, base_file)

    if failed:
        print(f"\n✗ HYBRID GATE FAILED: {failed}")
        return 1
    print(
        "\n✓ HYBRID GATE PASS — hybrid ≥ 单 lane 较好者(per slice)"
        + (" 且 ≥ 冻结绝对地板" if (args.protect and not rebaseline) else "")
    )
    return 0


def _lexical_gate(s: dict) -> int:
    # lexical gate
    if BASELINE.get("_overall", 0.0) == 0.0:
        print("\n*** REBASELINE MODE: BASELINE 为占位,只报数;回填常量后复跑判闸 ***")
        return 0
    print("\n=== GATE (vs goldset-kb-v5 冻结基线, margin", _MARGIN, ") ===")
    failed = []
    for slice_key, base in BASELINE.items():
        got = s.get(slice_key, {}).get("gold_key@10", 0.0)
        ok = got >= base - _MARGIN
        print(
            f"  {'PASS' if ok else 'FAIL'}  {slice_key:34} got={got}  base={base}  Δ={round(got - base, 4):+}"
        )
        if not ok:
            failed.append(slice_key)
    if failed:
        print(f"\n✗ GATE FAILED: {failed}")
        return 1
    print("\n✓ GATE PASS — lexical lane ≥ goldset-kb-v5 冻结基线")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--lane", choices=["lexical", "semantic", "hybrid"], default="lexical"
    )
    ap.add_argument("--gold", type=Path, default=_DEFAULT_GOLD)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--embed-batch", type=int, default=64, help="semantic lane 批量 embed 大小"
    )
    ap.add_argument(
        "--protect",
        action="store_true",
        help="hybrid: 开选项2 lexical-dependent 保护(强锚定抬 lexical 权重)",
    )
    ap.add_argument(
        "--kind-prior",
        action="store_true",
        help="hybrid: 开 kind 排序 prior(ADR-016 档位伪 lane 票,KB-334 候选)",
    )
    args = ap.parse_args()
    suffix = ""
    if args.lane == "hybrid":
        suffix += "_protected" if args.protect else ""
        suffix += "_kindprior" if args.kind_prior else ""
    out_path = args.out or _DEFAULT_RESULTS / f"{args.lane}{suffix}_goldset.json"

    gold = [
        json.loads(ln)
        for ln in args.gold.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    search_keys = _search_keys_for_lane(args, gold)
    rows = _evaluate(gold, search_keys)
    s = _slices(rows)
    _write_report(args, gold, s, out_path)

    if args.lane == "semantic":
        # 无冻结 semantic-only 基准 → 报数不判闸(诚实)。真正的回归闸是 hybrid。
        print("\n=== semantic lane(无冻结 semantic-only 基准 → 报数不判闸)===")
        return 0
    if args.lane == "hybrid":
        return _hybrid_gate(args, s, out_path)
    return _lexical_gate(s)


if __name__ == "__main__":
    sys.exit(main())

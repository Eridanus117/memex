---
description: "KB-350:per-root qdrant collection → 单一中央 collection(F-B)+ repo/domain/kind payload filter;联邦=一次 search+filter 无 fan-out。记实现验证后的契约,尤其 semantic-sync --scope-repo 必须与中央 collection 原子同落否则删兄弟仓。"
keywords: [中央collection, F-B, per-root退役, payload-filter, scope-repo, 孤儿prune, domain段前缀, 联邦召回, KB-350]
kind: decision
links: [kb-index-design-2026-06-06, adr-003-recall-rot-surface-not-engine, adr-002-indexability-contract, semantic-sync-massprune-mode-switch]
code: [workspace-weave/crates/weave-index/src/lib.rs, workspace-weave/crates/weave-semantic-qwen3-qdrant/src/lib.rs, workspace-weave/crates/weave-cli/src/commands/retrieval.rs]
---

# ADR-004:KB 索引中央化 — 单一中央 collection(F-B)+ payload filter

- **状态**:Accepted · 引擎已实装(workspace-weave main `fb8748e`,KB-350)· 切换(reindex/生产)gated 待 principal
- **日期**:2026-06-07
- **决策**:principal 拍方向(ERI-319 §索引 I3),agent 落实(KB-350)
- **关联**:实装 [[kb-index-design-2026-06-06]] §I3;延续 [[adr-003-recall-rot-surface-not-engine]](健康引擎上改面);mass-prune 机理 [[semantic-sync-massprune-mode-switch]];阻塞 KB-338(联邦 recall)

## TL;DR

把 weave 向量索引从 **per-root collection(F-A,每源仓一个 qdrant collection)** 改成 **单一中央 collection(F-B)**:4 个 KB 源仓的点汇进一锅,`repo`/`domain`/`kind` 当 payload filter。**联邦召回 = 一次 search + filter,不再 N 路 fan-out + merge**;hash/同步从 ×N 收成 ×1。核心理由:去中心多仓已是现实,per-root 让 recall 实质单 root、跨仓要 fan-out。**实装已落引擎层,但有一条数据安全契约必须在切换时守住:`semantic-sync --scope-repo` 必须与「collection 指向中央」原子同落——否则同步 A 仓会把 B/C/D 仓的点全判孤儿(轻则 >50% 守卫 abort,重则删光)。**

## 1. 问题 → Context

现状 per-root(F-A):collection 名由 root 派生(`<root>_hybrid_qwen3_v0`)。后果:
- recall 绑单 root → 跨 4 个 KB 源仓(`eridanus-kb / logistics-private / eridanus-ops / eridanus-pm`)要上层 N 路 fan-out + merge。
- hash 同步、stale 判定、prune 守卫每 collection 各算一遍(×N)。
- 异构源要「知道查哪个 collection」。

ERI-319 §索引 I3 已拍 F-B 方向(F-A/F-B 权衡见 [[kb-index-design-2026-06-06]]);本 ADR 记**拍定 + 实装后**的决策与契约。

## 2. 选项

- **F-A**:per-root collection + 查询时 fan-out + merge(现状)。
- **F-B**:单一中央 collection + `repo/domain/kind` payload filter,一次 search + filter(选)。
- **carve**:敏感源(logistics-private)独立 collection(F-B 的可选 flag)。

## 3. 权衡(逐项)

| 维度 | F-B 中央(选) | F-A per-root + fan-out |
|---|---|---|
| 联邦召回 | 一次 search + filter | N 路 fan-out + merge |
| 同步 / hash | 一处 | ×N |
| 异构源 | filter 收窄 | 要知道查哪个 |
| 复杂度 | filter 字段 + prune 按 repo 收窄 | fan-out / merge 编排 |
| 隐私 carve | 需要才 flag | 天然隔离 |

## 4. 决策

走 **F-B**:4 个 KB 源仓汇进一个中央 collection;`repo`(精确)/ `domain`(段前缀)/ `kind`(精确)当 payload filter。**不 carve**(logistics-private 也进全中央——本地个人用、carve 收益低)。legacy 数据仓(weave-data / eridanus-data,正冻结 TIDY-303)保留各自 collection,出范围。

## 5. Consequences(实装验证后的契约 + 代价)

**收益**:联邦召回去 fan-out;同步 / hash ×N → ×1;按 repo/domain/kind 任意收窄。

**必须守的契约(否则丢数据 / 召回错)**:

1. **`--scope-repo` 原子同落〔数据安全·头号〕**:中央 collection 共享后,`semantic-sync` 同步某仓时孤儿 prune **必须**按 `repo` payload 收窄(`--scope-repo <root>`)。否则其它仓的点都不在该次 `expected_ids` 里 → 全判孤儿 → >50% mass-prune 守卫 abort(好),若加 `--allow-major-prune` → **删光兄弟仓**(灾难)。「collection 指向中央」与「sync 传 --scope-repo」必须**同一次 cutover 落地**;host `weave-embed` 应硬断言「中央 ⟺ 必须 scope-repo」。
2. **段前缀两 lane 一致**:`domain` 存全 path + `domain_segments`(累积前缀数组)。`--domain logistics` = 对数组 match(qdrant)/ 段包含(lexical),`logistics` 不误伤 `logistics-private`。`domain` 在入口**统一去斜杠**(单点 normalize),否则 semantic(数组无斜杠)与 lexical(容忍斜杠)分叉。
3. **legacy hash 不变**:facet 仅 KB-lane 派生 + `skip_serializing_if` → 非 KB 仓 `compiled_hash` 字节不变、不被无谓重索引;KB-lane 加 facet → KB 点 hash 变 → **需重索引 4 仓**。
4. **lexical 是搜索时内存重建**:中央 lexical = `--artifact-dir` 多 dir 并集(union per-root sidecar);semantic 走中央 collection。两者经 repo/domain filter 对齐。

**代价 / 后续约束**:
- 切换动检索核心 + reindex(:3002 单线程挑空窗;`WEAVE_QWEN3_CHUNKED_EMBEDDING` 全链路一致避免 chunk↔whole mass-prune)—— ADR-001 类动作,principal 过目。
- 切前跑一次**无 scope 全量 reconcile**清「切换前已删文档」的存量 `repo=null` 孤儿(否则永不进 scope、持续召回已删)。
- 中央 collection 点数翻几倍,建议对 `repo` / `kind` / `domain_segments` 建 qdrant payload index。
- done 判据走 eval gate(复用 `kb-recall-baseline-v1` + OQ-2,nDCG 不劣化)。

## 6. Non-Goals + Alternatives Considered

| 替代 / 不做 | 否决理由 |
|---|---|
| 保留 F-A per-root + fan-out | 去中心多仓已是现实;fan-out 让 recall 实质单 root、hash ×N |
| carve 敏感源独立 collection | 本地个人用、carve 收益低;留作 flag 不默认 |
| legacy 数据仓并入中央 | weave-data / eridanus-data 正冻结(TIDY-303),出范围 |
| `--scope-repo` 设成隐式 / 自动 | 显式 opt-in 才能让 legacy per-root prune 字节不变(最小爆炸半径) |
| 4 dir 写进一个中央 sidecar 目录 | 会逼 index-build 的 sidecar prune 也按 repo 收窄;改成 search 时 union per-root 目录,存储不动 |

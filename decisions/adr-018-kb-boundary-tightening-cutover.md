---
description: "ADR-018:KB 中央化 cutover 接受边界收紧 — logistics-private 105 篇旧工作文档(handoff/brainstorm/对齐/deck)退出语义召回,不阻塞切换;兜底=旧 per-root collection 冻结快照+git;耐用部分由 principal 主导重整(KB-325)"
keywords: [cutover, KB边界, logistics重整, 去填埋场, 冻结快照, ADR]
kind: decision
links: [kb-write-path-contract-v1, adr-004-kb-central-collection, adr-001-kb-consumption-layer]
---

# ADR-018:cutover 接受 KB 边界收紧(去填埋场)

- **状态**:Accepted(principal 拍 A,2026-06-10,PM KB-380 串)
- **背景**:中央化 eval gate 通过(闸 lane 全 slice 持平、Hole@10 全零、MRR 略升),但 goldset 538 题仅 133 可比:logistics-private 134 个旧文件不在中央——旧 Rust 索引无差别收录整仓(861 点),新设计只收 INDEX 域树。其中 43 个(captures/work-items/logs)按既有设计排除无争议;105 个(docs/logistics + notes:5 月前后的 handoff/brainstorm/对齐纪要/deck,混少量耐用 spec)是取舍点。

## 决定

**选 A:接受边界收紧,直接 cutover。** 105 篇旧工作文档暂退出语义召回,不把切换押在大迁移上。

理由:① 这正是 ADR-001 北极星的"去填埋场"意图——旧 861 点中 work-item/brainstorm 噪音正是"好货被淹"元凶,请出召回是 feature;② curated 主体(domain-map + 全部契约/ADR)已在中央且过闸;③ 兜底三层:旧 per-root collection 留观察期不删(冻结快照)、weave search legacy 可查、git grep 永在。

## 否决的替代

**B:先逐篇判断迁移 105 篇再切**——几天级人工活卡住 cutover,且大部分判断结果大概率是"不迁"(本就是一次性交付物)。

## 后果

- logistics-private 知识库重整由 principal 主导(PM KB-325 承接);迁完做 KB-375 式 goldset 刷新(v3 仅 133 题,对新中央语料覆盖不足)。
- 观察期后清理旧 collection/.weave/disabled plists = PM KB-412。
- 过渡期查旧工作文档走 weave search(冻结快照)或 git。

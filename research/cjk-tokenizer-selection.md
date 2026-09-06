---
description: 选 cang-jie 0.19.0 + Tantivy 0.26；zh-only lexical baseline nDCG@10 从 0.530 升到目标 ≥0.70，work-item-lifecycle topic 从 0 修到 ≥0.40
keywords: [cang-jie, jieba-rs, lindera, cc-cedict, tantivy, 中文分词, 全文检索, nDCG]
links: [INDEX]
supersedes: cjk-tokenizer-selection-design-memo
kind: research
---
> 来源：workspace-weave WEAVE-22 design memo（2026-05-11）；eval 数据来自 6-run lexical baseline 实测

## 三行人话摘要（给 principal，只读这个就够）

1. **选 `cang-jie 0.19.0 + Tantivy 0.26`**：最直接的 Tantivy 原生中文 tokenizer，基于 `jieba-rs cut_for_search`，开箱可用，无需自维护 adapter。
2. **问题根因**：原始配置四个 text field 全走 Tantivy 默认英文 analyzer，中文不分词，`work-item-lifecycle` topic zh-only nDCG/MRR/Recall 全为 0。
3. **accept 门槛**：lexical zh-only nDCG@10 ≥ 0.70、Recall@10 ≥ 0.80；en-only / mixed 任意 cell 退化 > 0.05 = reject；`lindera + cc-cedict` 是 cang-jie 不达标后的第二刀 A/B 候选，不是首选。

## Baseline 数据

| metric | en-only | zh-only | 灾难点 |
|---|---|---|---|
| nDCG@10 | 0.675 | 0.530 | work-item-lifecycle zh: **0** |
| Recall@10 | 0.833 | 0.600 | work-item-lifecycle zh: **0** |

## 三路选型对比

| 维度 | `cang-jie 0.19.0` + Tantivy 0.26 | `lindera-tantivy 2.0.0` + CC-CEDICT + Tantivy 0.25 | 本地适配 Tantivy 0.22 |
|---|---|---|---|
| 词表 | jieba-rs 默认词典；可加用户词典 | CC-CEDICT，繁简/专名覆盖更好 | 取决于选 jieba-rs 或 Lindera core |
| 集成成本 | Tantivy 0.22→0.26 bump；API break 可控 | Tantivy 0.22→0.25 + Lindera 字典特性，依赖更重 | 不升 Tantivy；但要自维护 tokenizer adapter |
| MSRV 成本 | 实际升到 Rust 1.88 | Rust ≥1.85（Tantivy 0.25 / edition 2024） | 保持现有 MSRV |
| runtime overhead | 最低，Arc\<Jieba\> + cut_for_search | 字典加载和 pipeline 更重 | 可控但自维护 |
| 达标概率 | 高：细粒度中文 token 直击 zh-only 痛点 | 中高：词典强但调参复杂 | 中：保守但易变自维护负担 |

**选 cang-jie 理由**：Tantivy 使用面窄（仅 weave-search），升级可控；cang-jie 是 Tantivy 原生 tokenizer，最小集成面；lindera 是 cang-jie 失败后的 A/B 候选。

## 实施要点

**字段配置**：
- title/body → `weave_cjk_jieba_v0` tokenizer（`TokenizerOption::ForSearch { hmm: false }`）+ `WithFreqsAndPositions`
- object_key/path → `raw` tokenizer + `IndexRecordOption::Basic`
- QueryParser boost：title=5.0，body=1.0；object_key/path exact=1.0~2.0（由 baseline 判）

**HMM 初始 false**：减少未登录词猜测噪音；`work-item-lifecycle` 仍不达标再 A/B `hmm: true`。

**fallback 触发条件**：Tantivy 0.22→0.26 API break > 10 处，或 30 分钟修不通 → 退回"Tantivy 0.22 + 本地 jieba-rs adapter"临时路径，Tantivy upgrade 拆 follow-up。

## Accept/Reject 门槛

| cell | 阈值 |
|---|---|
| lexical zh-only | nDCG@10 ≥ 0.70，Recall@10 ≥ 0.80 |
| lexical zh-only work-item-lifecycle | nDCG@10 ≥ 0.40，Recall@10 ≥ 0.50 |
| en-only / mixed 任一退化 | > 0.05 = reject |
| hybrid zh-only | nDCG@10 ≥ 0.85 |

## 版本约束速查

| 组件 | 版本 | 备注 |
|---|---|---|
| cang-jie | 0.19.0 | 要求 tantivy 0.26.1，Rust 1.88 |
| cang-jie 0.18.0 | 不用 | 依赖 tantivy 0.21，trait 不兼容 0.22 |
| lindera-tantivy | 2.0.0 | 依赖 tantivy 0.25，edition 2024 |
| tantivy | 0.26.1 | cang-jie 主路升级目标 |

## 不做的事（非目标）

- analyzer registry schema 改动（协议级，需单独 review）
- sub-document chunking（留 session 3）
- query rewrite / expansion（lexical upgrade 规则明确禁止）

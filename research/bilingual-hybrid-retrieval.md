---
description: 中英混合 hybrid 检索设计；zh-only query 通过 weighted RRF(2×/3×) + semantic depth cap 320 将 nDCG@10 从 0.469 推向目标 ≥0.85，en-only/mixed 维持 nDCG@10 0.903/0.932
keywords: [RRF融合, 双语检索, 语言分类, semantic-budget, Recall@10, nDCG@10, hybrid-search, 候选深度]
links: [INDEX]
supersedes: bilingual-hybrid-retrieval-design-memo
kind: research
---
> 来源：WEAVE-103/WEAVE-22 双语 hybrid 检索设计 memo（eval/search/runs/weave-22-session2）

## 三行人话摘要（给 principal，只读这个就够）

1. **问题根因是两段的**：纯中文 query（无 ASCII identifier）找英文-heavy 文档，第一段是 semantic 候选池太浅（depth 40 时 canonical docs 完全缺席），第二段是 equal RRF 把 semantic-only canonical docs 压到 final rank 65+——两个问题必须分开修。
2. **修法**：用确定性本地 classifier 判 `zh_only_low_anchor`，触发 semantic depth cap 320；同时把 equal RRF 降为 baseline，新 profile 评测 semantic weight 2×/3× 的 weighted RRF matrix；embedding model 和 Qdrant collection 不变（probe 证明 depth 320 下已能找到 missing docs）。
3. **当前 baseline 数字**：zh-only aggregate nDCG@10 0.792、Recall@10 0.767；最难 topic（work-item-lifecycle）nDCG@10 0.469、Recall@10 0.333（3 个 canonical docs 只召回 1 个）；en-only 0.903/1.000，mixed 0.932/1.000——后两组已接近 ceiling，改动必须守住 regression ≤ 0.05。

## Baseline 数字

| backend | topic set | nDCG@10 | Recall@10 |
|---|---|---:|---:|
| `hybrid-qwen3-qdrant-v0` | zh-only-v1 aggregate | 0.792 | 0.767 |
| `hybrid-qwen3-qdrant-v0` | zh-only work-item-lifecycle | 0.469 | 0.333 |
| `hybrid-qwen3-qdrant-v0` | en-only-v1 | 0.903 | 1.000 |
| `hybrid-qwen3-qdrant-v0` | zh-en-mixed-v1 | 0.932 | 1.000 |
| `local-lexical-v0` | zh-only-v1 | 0.612 | 0.667 |

接受门槛：bilingual profile zh-only nDCG@10 ≥ 0.85 且 Recall@10 ≥ 0.90；hard topic strict Recall@10 ≥ 0.67；en-only/mixed regression ≤ 0.05。

## RRF 融合设计

当前 equal RRF 公式：`score = 1/(60 + rank)` per lane，lexical/semantic 等权。

Probe 证据（hard topic `工作项目 生命周期 状态 重设计`）：

| limit | semantic depth | canonical docs 情况 |
|---:|---:|---|
| 10–40 | 40–160 | weave-6 / WEAVE-76 完全不在 candidate pool |
| 80 | 320 | weave-6 final rank 65（semantic rank 9）；WEAVE-76 final rank 73（semantic rank 17）—— docs 进了 pool 但 equal RRF 压排名 |

**结论**：depth-only 修不够；必须同时改 fusion policy。

新 profile 必须评测三个 fusion cell：

| fusion_policy | lexical_weight | semantic_weight | 用途 |
|---|---:|---:|---|
| `rrf-equal-v0` | 1.0 | 1.0 | baseline，保持 v0 可复现 |
| `rrf-semantic-weight-2-v1` | 1.0 | 2.0 | 低风险 boost，仅 zh_only_low_anchor 触发 |
| `rrf-semantic-weight-3-v1` | 1.0 | 3.0 | 验证 weighted RRF 是否足以修复 top-10 缺失 |

选最低通过 gate 的 semantic weight。若 3× 仍不过，下一步是 authority-aware reranking，**不是**继续加 weight。

## 查询语言分类（query_language_hint classifier）

确定性本地 heuristic，只读 query text，不改写 query：

| hint | 判定规则 | semantic base budget |
|---|---|---|
| `zh_only_low_anchor` | `cjk_char_count > 0` 且 `ascii_identifier_count == 0` | cap 320 |
| `mixed` | `cjk_char_count > 0` 且 `ascii_identifier_count >= 1` | `max(limit×4, 20)` |
| `en_only` | `cjk_char_count == 0` 且 `ascii_identifier_count >= 1` | `max(limit×4, 20)` |
| `unknown` | 两者均为 0 | `max(limit×4, 20)` |

`ascii_identifier_count` 来自 token regex `[A-Za-z_][A-Za-z0-9_:-]*`。`path-filter` 是正交 overlay（不是 language enum）：有 path filter 时 depth = `max(base_budget, max(limit×8, 50))`，再套同一 cap 320。

classifier 必须有单元测试 + worked examples，`query_language_hint` 值用下划线进 trace/JSON，topic-set 文件名和 profile id 用 dash。

## Semantic Budget 策略与 Candidate-Depth 权衡

核心原则：**candidate-missing 和 fusion-dropped 是两个独立问题，不能只调一个参数**。

- depth 40–160：zh-only hard topic canonical docs 完全缺席 pool —— 改 fusion 无意义
- depth 320：canonical docs 进入 pool，semantic rank 9/17 —— 但 equal RRF 压到 final rank 65/73

所以 `zh_only_low_anchor` 的 cap 设为 320（opt-in，不改默认 profile）。

Latency guard 要求：bilingual profile eval p95 不超过 baseline 2×；semantic lane p95 不超过 1000ms；implementation 必须记录 `per_lane_stats.<lane>.elapsed_ms`。

## Profile 设计与关键决策

**复用当前 embedding**：Qwen3/Qdrant probe 在 depth 320 已能找到 missing canonical docs，暂不换 embedding model 或新建 per-language collection；新建 profile id（`hybrid-qwen3-qdrant-bilingual-v1`）复用同一 collection，保留 v0 baseline 可复现性。

**显式拒绝的方案**：query rewriting、translation、HyDE、hard-coded bilingual alias injection——probe 证明 eval-specific alias 和 topic vocabulary 高度重合且改变 caller query semantics。

**Trace 必须输出的字段**：`query_language_hint`、`query_language_features`（cjk_char_count/ascii_identifier_count）、`semantic_budget_policy`、`semantic_budget_reason`、`semantic_depth_cap`、`fusion_algorithm`、`fusion_policy`、`fusion_weights`、`per_lane_stats.<lane>.elapsed_ms`。

**Qrels 原则**：handoff/lore 对象（低权威）不加入 binary expected set——会让 eval 用替代物过关而 canonical docs 仍缺。非 primary hits 作 report-only `supporting_object_keys`，不参与 Recall@10 scoring；graded qrels scoring 需另走 schema review。

**Default profile 保护**：eval 通过前不改 `weave search` 默认 profile；新 profile 只通过 `--backend hybrid-qwen3-qdrant-bilingual-v1` opt-in 触发。

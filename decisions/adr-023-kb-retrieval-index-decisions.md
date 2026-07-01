---
description: "ADR-023:KB 检索与索引引擎决策(KB-319 蒸馏留痕)——conditional hybrid(planner+weighted-RRF+depth cap 320)、facet 收敛 domain/kind/tag 去 repo facet、命中返回指针+预览不内联、可索引性闸门=frontmatter+loud-skip、eval promotion gate 是改检索默认值的唯一门;否决 flat RRF/repo facet/stale 软提示/凭感觉调参"
keywords: [conditional-hybrid, weighted-RRF, facet收敛, 去repo-facet, 可索引性闸门, loud-skip, eval-gate, promotion-gate, ADR]
kind: decision
links: [kb-write-path-contract-v1, adr-003-recall-rot-surface-not-engine, adr-004-kb-central-collection, adr-005-kb-python-rewrite-edr, adr-016-kind-v2-taxonomy]
---

# ADR-023:KB 检索与索引引擎决策

- **状态**:Accepted(principal 拍板 2026-06-06~06-09 分批;本篇为 KB-319 收口蒸馏留痕,2026-06-11)
- **背景**:召回/索引/统一向量化三份设计稿的决策已实装于 kb-search 与写路径契约(C1-C8),其中数项无 ADR 留痕。单一 recall verb(ADR-003 走 A)、中央单 collection(ADR-004/018)、Python 化(ADR-005)已各有 ADR,本篇不重复,只收无留痕项。

## 决定

1. **conditional hybrid 是默认相关性**:query planner 入口确定性分类,中文低锚 query(cjk>0 且无 ascii identifier)走 weighted-RRF(semantic 加权,实装 2.0)+ semantic depth cap 320——flat 等权 RRF 对纯中文 nDCG@10 实测塌到 0.469;depth 不够则好货不进 pool,与融合权重是两个独立问题。
2. **facet 收敛为 domain/kind/tag 三维,不设 repo facet**(2026-06-08 拍,改写 06-06 初版 4-facet):domain 才是检索维度,`--repo` 走 identity 前缀客户端兜底(契约 C5;ADR-020 复核"不受影响")。代价条款:`--domain` 跨仓共用一个命名空间,顶层域名须全局可区分(同仓撞域有 C8 守卫,跨仓靠命名约定)。
3. **命中返回 = 指针 + 预览,不内联正文**:召回是"先定位再读",内联全文炸上下文。
4. **可索引性闸门 = 有 frontmatter ⟺ 可索引**,全仓一致,杀 repo_kind/lane;无 frontmatter 一律 loud-skip 不静默(契约 C1;承 ADR-002 的静默失败诊断,该篇至今 Proposed,决策本体以本条为锚)。
5. **eval promotion gate 是改检索默认值的唯一门**:Hole@10<0.80 做 binding 前置(覆盖不够时 nDCG 不可信),质量阈值相对 current default 加 margin(不相对 candidate,防 self-validating);一切调优(融合权重/depth/prior/chunk)= eval-gated flag 过此闸。ADR-018 cutover 即以此 gate 结果为 done 判据。
6. 一行项:kind 当排序 prior 非硬过滤(决策已由 ADR-006/ADR-016 覆盖,档位 T1-T4 见 ADR-016),prior 实装为 eval-gated flag 待切(公式与参数归 kb-search,不入本篇);两级 reuse(point_id O(1) → text_hash 复用向量只 re-key,使移动可逆且便宜,契约 C6);lexical 中文分词 Python PoC 候选 A 决定性 GO(2026-06-09)——ADR-005 的"冻结 rust 分词 bin"例外条款条件未触发、无需启用(条款本身不动)。

## 否决的替代

保留 query/search/recall 多路径(agent 必走到差的那条,ADR-002 实证)/ flat 等权 RRF(中文塌 0.469)/ repo facet(物理来源非检索维度)/ stale 软提示或静默返结果(正是本病;分态大声口径在 ADR-003 §9)/ 无 eval gate 凭感觉调参(self-validating 陷阱)。

## 后果

- 改任何检索默认值,流程固定:flag → eval → gate 过 → flip。
- 已知执行缺口:R6 召回健康行/stale 标注在 Python 读路径未复刻(Rust 时代实装已随 ADR-005 废弃),挂 PM 跟踪,非决策回退。
- 条款真相在 kb-write-path-contract-v1(C1-C8)与 kb-search docs/architecture.md,本篇只记拍板与否决。

## 来源

蒸馏自 `eridanus-kb:design/kb-recall-design-2026-06-06.md`、`eridanus-kb:design/kb-index-design-2026-06-06.md`、`eridanus-kb:design/kb-unified-vectorization-design-2026-06-08.md`(本篇落盘后删,git 留史;其中 unified-vectorization D2a 物流整仓方案已被 ADR-020 明文 supersede,D3/D5 已被 ADR-018/ADR-005 改写作废)。

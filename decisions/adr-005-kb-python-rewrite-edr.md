---
description: "KB/weave 栈去 Rust/Go 化、全部重写为 Python——根除 EDR 杀新编译 binary 首跑的开发期税。翻 ADR-003「引擎 0.93 健康不重写」:因 EDR 即使健康也重写,但风险收敛——语义检索调外部服务(qdrant+:3002)零回归,唯一回归点=lexical 中文分词。禁 rust/go 铁律;唯一例外=中文分词 Python 守不住召回时固化一个冻结的小 rust-bin(编译一次、不再迭代)。绞杀式 + eval gate 守 0.93。"
keywords: [EDR, 去Rust化, Python重写, weave引擎重写, 中文分词fallback, 绞杀式重写, eval-gate, 翻ADR-003]
kind: decision
links: [adr-003-recall-rot-surface-not-engine, kb-unified-vectorization-design-2026-06-08, adr-004-kb-central-collection, weave-wx-rebuild-over-patch]
code: [host-local/tools/weave-semantic-sync, workspace-weave/crates]
---

# ADR-005:KB/weave 栈去 Rust/Go 化 — 重写为 Python(躲 EDR),翻 ADR-003「引擎不重写」

- **状态**:Accepted · principal 拍(2026-06-08)· 实施未启动
- **关联**:翻 [[adr-003-recall-rot-surface-not-engine]] §「引擎健康不重写」+ [[weave-wx-rebuild-over-patch]];实施设计见 [[kb-unified-vectorization-design-2026-06-08]];中央 collection [[adr-004-kb-central-collection]]

## TL;DR

**决策:KB/weave 栈全部重写为 Python,去掉所有 Rust/Go 编译 binary。** 驱动 = EDR(企业安全软件)拦截新编译 binary 首跑(本 session freight-obs、weave binary 重建均实测撞),开发期高频重建 rust/go **无法忍受**。Python 解释执行无 binary、根除此税(与 wx→Python、freight-obs→Python 绞杀一脉,现扩到整个 weave 栈)。

这**推翻** ADR-003「weave 引擎(nDCG 0.93)健康、不重写只改面」——因 EDR,即使健康也重写。**但风险收敛到一处**:真正的检索重活在外部服务(qdrant 向量 + :3002 embedding),Python 直接调它们 → **语义召回零回归**;唯一真回归点 = lexical 的 BM25 + 中文分词(Rust Tantivy+cang-jie → Python)。

**铁律:不允许任何 rust/go 被用到。唯一例外**:中文分词若 Python 方案守不住召回,固化**一个小的 rust-bin**(编译一次、冻结、不再迭代——故 EDR 首扫一次后不再拦,不参与开发期高频重建)。这是 last-resort,不是默认。

## 1. 问题 → Context

- **EDR 税**:企业 EDR 云端首扫,新编译 binary 首次 exec 被拦(SIGKILL / launchd I/O error)。本 session 实证:freight-obs Go binary launchd 起不来(ADR/PM ERI-369)、weave binary 若重建带 `--scope-repo` 也会撞。
- **痛在高频重建**:KB 重建期一直在改 sync/索引/编排/facet → 频繁重建 weave binary → 频繁撞 EDR。principal 判定**无法忍受**。
- **旧决策**:[[adr-003-recall-rot-surface-not-engine]] + [[weave-wx-rebuild-over-patch]] 拍过「引擎(nDCG 0.93)健康,不重写、只改面;壳可绞杀重构」。该决策假设「引擎稳定 = 不常重建 = EDR 不痛」——但实测引擎在 KB 重建期**也常改常重建**,假设不成立。

## 2. 选项

- **A · 维持现状**:Rust 引擎不动,只壳层 Python 绞杀(adr-003 现状)。
- **B · 绞杀保留检索内核**:高频改的(sync/索引/编排)走 Python,检索排序内核(0.93)留 Rust、拆成独立低频 binary。
- **C · 全部 Python + 禁 rust 铁律**:连检索内核重写 Python;中文分词守不住时固化一个冻结小 rust-bin 兜底。(选)

## 3. 权衡(逐项横比)

| 维度 | A 维持现状 | B 保留检索内核 | C 全 Python(选) |
|---|---|---|---|
| **EDR 根除** | 部分(引擎仍 rust,偶重建仍撞) | 大部分(内核 rust 低频仍偶撞) | **根除**(默认无 rust;例外是冻结 bin,首扫一次不再拦) |
| **0.93 检索回归** | 零(引擎不动) | 零(内核不动) | 语义**零**(调同 qdrant/:3002);仅 lexical 中文分词有风险 |
| **中文 lexical** | rust cang-jie 保留,零风险 | rust 保留,零风险 | Python(jieba+rank_bm25 / qdrant 全文)→ **唯一回归点**,PoC+eval+fallback 守 |
| **重写工作量** | 小(已在做) | 中(拆 binary) | 大(检索内核胶水 + lexical 方案);但重活在外部服务、非从零造算法 |
| **可逆性** | n/a | 好 | 好(绞杀式,每块 eval gate,新旧并行) |
| **违「禁 rust」铁律** | 是(保留 rust 引擎) | 是(内核 rust) | **否**(默认全 Python;冻结小 bin 不参与高频重建,不违精神) |

## 4. 决策

走 **C**:KB/weave 栈全部重写为 Python。

- **禁 rust/go 铁律**:开发期任何高频重建的部分,一律 Python,不允许 rust/go。
- **唯一例外(last-resort)**:中文分词若 Python 守不住召回(eval gate 不过),固化一个小 rust-bin——**必须编译一次、冻结、不再迭代**(这样它不参与开发期高频重建,EDR 首扫一次后不再拦,不违铁律精神)。不是默认,是兜底。
- **风险定位**:语义/embedding/RRF/sync/编排 = 调外部服务 + 逻辑搬运,零或低回归;唯一真回归点 = lexical 中文分词。

## 5. Consequences

**收益**
- 根除 EDR 高频重建痛(开发期不再被安全软件拦)。
- 栈语言统一 Python(wx / freight-obs / KB 栈一脉),解释执行、改即生效。

**代价 / 必须守的契约**
1. **语义零回归靠"调同外部服务"**:Python 必须调同一个 qdrant + 同一个 :3002 embedding(同模型/参数),否则语义召回不再等同。
2. **lexical 中文分词 = 唯一回归闸**:先做 PoC(jieba+rank_bm25 或 qdrant 全文,跑 gold-set 中文 query);**eval gate 守 0.93**(复用 `kb-recall-baseline-v1`,Python 版召回 ≥ Rust 才切);守不住 → 固化小 rust-bin(非降级召回)。
3. **绞杀式可逆**:逐块 Python 替换,新旧并行对照,每块过 eval gate;不大爆炸一次性切。
4. **Python 检索性能**:本地个人 kb 量小(百~千篇),Python 调 qdrant + 内存 BM25 预计够用;若量级涨需复测(待验,非阻塞)。

**翻案后果**
- [[adr-003-recall-rot-surface-not-engine]] 的「引擎健康不重写」失效;[[weave-wx-rebuild-over-patch]](「引擎 nDCG 0.93 不在重构范围」)翻案,需更新。
- [[kb-unified-vectorization-design-2026-06-08]] 基调从「flip 现状 Rust 引擎」改为「Python 重写」。

## 6. Non-Goals + Alternatives Considered

**Non-Goals**
- 不大爆炸重写(绞杀式逐块切)。
- 不接受召回降级换纯 Python(eval gate 守 0.93;守不住用固化小 rust-bin 兜底,不是降召回)。
- 不重写外部服务(qdrant / :3002 embedding 不动,它们是检索重活所在、且非本机高频重建)。

**Alternatives Considered**
| 替代 | 否决理由 |
|---|---|
| A 维持 Rust 引擎(adr-003 现状) | 引擎在 KB 重建期也常重建 → 仍频繁撞 EDR;principal 无法忍受任何高频 rust |
| B 保留 Rust 检索内核 | 违「禁 rust」铁律;且 0.93 重写风险已收敛(语义零回归),保留 rust 收益不抵铁律 |
| 接受中文召回降级换纯 Python | 砸北极星(召回是 telos);改用 eval gate + 固化小 rust-bin 兜底守住 0.93 |
| 用 Go 重写(也解释执行?) | Go 仍编译 binary,同样撞 EDR;只有解释执行(Python)躲税 |

> 综上:C 是唯一同时满足「根除 EDR」与「守住 0.93」的路径——代价收敛到 lexical 中文分词这一个可控点(PoC + eval gate + 冻结小 bin 兜底),其余皆调外部服务或逻辑搬运。

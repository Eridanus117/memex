---
description: "钉死 logistics-private 检索≈0(gold_key@10 0.046)的真因:weave query 用硬编码 object_type 白名单 {doc,plan,episode,work_item,kb} 过滤结果,非白名单类型(guide/run_log/report/reference/onboarding-doc/handoff…)整批在排序前被静默丢弃。logistics 主力类型全不在白名单 → 158 篇加载了只 ~5 篇可被检索到;eridanus-kb 因全是 object_type=kb(白名单内,且 kb 还是 ADR-003 a06cc95 临时补的)才幸存。决定:把'类型=硬过滤'降为'类型=排序 prior'(kb-index-design I6 已设计),并入 ADR-005 Python 重写,不单独改 Rust。refine ADR-003:其'引擎健康 nDCG 0.93'实为只在 object_type=kb 语料上成立,换类型词汇的仓即致盲——'腐在面'论点被证实并加重。"
keywords: [object_type白名单, 类型硬过滤致盲, tier_object_types, 类型降prior, refine-ADR-003, 引擎健康是假象, logistics检索失效]
kind: decision
links: [adr-003-recall-rot-surface-not-engine, adr-005-kb-python-rewrite-edr, kb-index-design-2026-06-06, kb-lexical-tokenization-poc-2026-06-09, adr-004-kb-central-collection]
code: [workspace-weave/crates/weave-cli/src/commands/retrieval.rs, workspace-weave/crates/weave-search/src/lib.rs]
---

# ADR-006:object_type 硬过滤白名单致盲非标准类型仓 — 类型降为 prior(并入 Python 重写)

- **状态**:Accepted · principal 拍(2026-06-09)· 修法并入 [[adr-005-kb-python-rewrite-edr]],不单独改 Rust
- **日期**:2026-06-09
- **决策**:principal 拍方向,agent 落实
- **关联**:refine [[adr-003-recall-rot-surface-not-engine]] 的「引擎健康」;实施并入 [[adr-005-kb-python-rewrite-edr]];设计依据 [[kb-index-design-2026-06-06]] §I6;发现于 lexical PoC([[kb-lexical-tokenization-poc-2026-06-09]] / PM KB-375)
- **实证(2026-06-09)**:lexical PoC 候选 A(无类型过滤)在同一 gold-set 上把 logistics gold_key@10 从 0.046 → **0.947**,直接验证「去 object_type 硬过滤 = 修复」;本 ADR 从推断升为实测确认

## TL;DR

**logistics-private 检索几乎全失效(新 gold-set 上 hybrid 与 lexical-only gold_key@10 均 0.046,eridanus-kb 同口径 0.95),真因不是 frontmatter、不是中文分词、不是存储、不是孪生文档,而是 `weave query` 用一张硬编码 `object_type` 白名单 `{doc, plan, episode, work_item, kb}` 过滤结果——非白名单类型在排序前被静默丢弃。** logistics 文档主力类型(`guide`/`run_log`/`report`/`reference`/`onboarding-doc`/`handoff`/`narrative`…)无一在白名单内,故 158 篇 artifact 全部加载、却只有 ~5 篇(恰好是 `doc`/`plan` 类型的)能进入结果。eridanus-kb 之所以正常,仅因其文档**全是 `object_type=kb`**(白名单内,且 `kb` 是 ADR-003 commit `a06cc95` 才临时补进去的)。

**决定:把「类型=硬过滤(scope)」降为「类型=排序 prior」(kb-index-design §I6 已设计),并入 ADR-005 的 Python 重写,不在将被重写扔掉的 Rust 引擎上单独打补丁。** 默认检索不按类型筛;类型只做 post-fusion 排序加权;要按类型收窄时走显式 `--object-type`/`--kind`。

## 1. 问题 → Context

KB-375 在当前 KB(logistics-private + eridanus-kb)上重建了 gold-set(538 query,对抗审计 100% faithful),用以给 lexical PoC 立现状基准。重测现状 Rust(binary `9aaea96`)暴露:

| gold_key@10(deterministic 精确匹配) | hybrid | lexical-only |
|---|---|---|
| eridanus-kb(82 query) | 0.963 | 0.951 |
| logistics-private(456 query) | **0.046** | **0.046** |

0.046 ≈ 失效,不是「难」。逐层排查(全 query-time 实测,见 KB-375):

- **非 frontmatter**:这 158 篇是**有** frontmatter、已进索引的(`doctor` 报 158 artifacts 加载)。另有 124 篇无 frontmatter 未索引,是独立小账,不解释这 158 篇。
- **非加载**:`doctor` 与显式 `--backend hybrid-qwen3-qdrant-v0`(精确匹配 sidecar profile)均确认 158 篇加载。
- **非分词**:eridanus-kb 也是中文,0.95 正常。
- **非孪生挤**:广义词「运费」(出现在 59+ 篇)只返回 5 个候选,且 `--hits 20` 也只 5——是**候选池**只有 5,不是排序把 gold 挤出。
- **定位**:返回的 5 篇 `object_type` 全是 `{doc, plan}`;被丢的全是 `{guide, run_log, report, onboarding-doc, reference, …}`。`--flat`(无 tiering)在装机 `9aaea96` 上也不绕过。

代码证据(`crates/weave-cli/src/commands/retrieval.rs`):`tier_object_types(tier)` 返回 tier1=`["doc","plan","episode"]`、tier2=`["work_item"]`、tier3=`[]`;ADR-003 `a06cc95` 另补了 `kb`。这张白名单是 ADR-003 同一个 footgun 的延续(当时 `kb` 漏登记 → KB 整仓返空;现在 logistics 的类型词汇漏登记 → logistics 整仓致盲)。

> 注:静态读的是当前源码,实测跑的是装机 `9aaea96`,可能有版本差;但「返回的全是白名单类型、被丢的全不是」「`--flat` 不绕过」是装机实测,确凿。

## 2. 选项

- **A · 改 Rust 白名单**:把 logistics 的类型(guide/run_log/report/…)补进 `tier_object_types`,或去掉硬过滤。
- **B · 折进 ADR-005 Python 重写,类型降 prior**(选):重写检索面时,默认不按类型筛,类型只做 post-fusion 排序 prior(§I6 已设计);显式 `--object-type`/`--kind` 才 scope。
- **C · 改数据**:把 logistics 文档 re-type 成白名单内类型(guide→doc 等)。

## 3. 权衡(逐项横比)

| 维度 | A 改 Rust 白名单 | B 类型降 prior(Python 重写) | C re-type 数据 |
|---|---|---|---|
| 根治 footgun | 否(下次又有新类型词汇致盲) | **是**(类型不再是硬闸,新类型默认可检索) | 否(且持续要维护映射) |
| EDR | 重编 Rust binary 撞 EDR | 无(Python 解释执行,ADR-005) | 无 |
| 与 ADR-005 一致 | **冲突**(改马上要被重写扔掉的代码) | **一致**(本就是重写范围) | 不涉及引擎 |
| 信息损耗 | 无 | 无 | **有**(抹掉真实类型语义) |
| 工作量 | 小但 throwaway | 中(并入重写,无额外) | 中(改 158+ 篇 + 持续) |
| 可逆 | 是 | 是(eval-gated flag) | 差(改了原始数据) |

## 4. 决策

走 **B**:类型从「硬过滤(kind-as-scope, pre-fusion)」降为「排序 prior(kind-as-prior, post-fusion boost)」,并入 [[adr-005-kb-python-rewrite-edr]] 的 Python 重写。

- **默认**:检索不按 `object_type`/`kind` 筛;所有类型可被召回。
- **类型的正当用途**:① post-fusion 排序 prior(免调参公式 `PRIOR_WEIGHT/(RRF_K+rank)`,§I6);② **显式** `--object-type`/`--kind` 时才做 scope 收窄。
- **不在 Rust 引擎上补白名单**(违 ADR-005 + EDR + 不根治)。

## 5. Consequences

**收益**
- logistics(KB 主体,861 点)从检索≈0 恢复到可召回;lexical PoC 得以在物流上立有效基准。
- 根除「换一套类型词汇就整仓致盲」这一类 footgun;新仓/新类型默认可检索,不需登记白名单。

**代价 / 后续约束**
- logistics 的有效基准**要等 Python 重写的检索面**(或用无类型过滤的 PoC 候选先行测,见 KB-375)。在此之前,logistics 段 gold-set 在现状 Rust 上的数**不可用作基准**(0.046 是 footgun 造的)。
- 类型 prior 权重是 eval-gated flag(§I9),flip 过 promotion gate。

**refine ADR-003(重要)**
- ADR-003 头条「引擎健康 nDCG@10 0.93」**只在 `object_type=kb` 的 eridanus-kb 语料上成立**——它恰好全是白名单内的唯一类型,绕过了这个 footgun。换任何用别的类型词汇的仓,引擎检索即致盲。
- ADR-003 的「腐在**面**不在引擎」论点**被证实并加重**:这张类型白名单正是「面」的腐,且后果比「对状态撒谎」更重——它**静默吞掉整仓**。ADR-003 不被推翻,而是其「引擎健康」的适用范围被收窄、「面腐」的严重度被上调。

## 6. Non-Goals + Alternatives Considered

**Non-Goals**
- 不在本 ADR 修那 124 篇无 frontmatter 文档(独立账,KB-325/KB-351)。
- 不改 embedding/存储设计(principal 暂缓中;本 ADR 只动检索面的类型过滤,不碰存储)。
- 不动 ranking 融合算法(类型 prior 是 eval-gated flag,独立演进)。

**Alternatives Considered(否决)**

| 替代 | 否决理由 |
|---|---|
| A 改 Rust 白名单 | 改 throwaway 代码 + 撞 EDR + 不根治(下个新类型词汇又致盲) |
| C re-type 数据成白名单类型 | 抹掉真实类型语义、持续维护映射、改原始数据不可逆 |
| 保留硬过滤、靠文档教 agent「记得登记类型」 | 把工具的坑转嫁给人/agent 记忆 = 反「好 CLI 消灭坑」;footgun 仍在 |

---

> 即时下一步(不等重写):logistics 的有效 lexical 基准,用无类型过滤的 PoC 候选(jieba+bm25s)直接在 158 篇 logistics artifact 上跑——既验证 gold-set、又出 logistics 第一个真数,见 [[kb-lexical-tokenization-poc-2026-06-09]] / PM KB-375。

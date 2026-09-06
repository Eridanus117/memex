---
description: "ADR-035: KB object_key 的 repo 段 = kb-sources.toml 的 name 字段(逻辑名), memex 编译只读 name 永不取物理目录 basename; 物理迁移/改名不改 identity; KB 逻辑名命名空间独立于 registrar 资产命名。补 ADR-017 未钉的 repo 段口径。"
keywords: [identity, repo段, registry-name, 物理无关, memex, source命名, ADR]
kind: decision
links: [adr-017-domain-node-chain-identity, adr-026-kb-domain-c2-unified, kb-source-repository-contract]
---

# ADR-035: KB identity 的 repo 段 = registry 逻辑 name(物理位置无关)

- **状态**: Accepted(principal 拍板 2026-06-23, 串 ERI-601)
- **背景**: ADR-017 钉死了 identity 的 domain 段(节点链)和 slug 段, 但 **repo 段未钉**; `kb-source-repository-contract` 写"identity 由路径或 git 派生", memex 据此用物理目录 basename(`scan.py:repo_name()` → `compile.py:compile_repo()` 重算, 丢弃 sync 传入的 registry `name`)当 repo 段。迁移前物理 leaf == registry name, 一直未暴露。ADR-026 把仓 path 改成 `<class>/<world>/<project>` 形态后, leaf ≠ name 的仓 identity 跟物理目录漂移 → recall repo 名与 registry/rhizome 对不上、compiled 双份、agent 无法定位磁盘文件。

## 决定

1. KB object_key 的 repo 段 = `kb-sources.toml` 的 `name` 字段(逻辑名)。memex 编译**只读 name, 永不从物理目录 basename 派生 repo identity**。
2. 物理位置(class/world/目录名)与 identity 完全解耦: 仓迁移/改名不改 identity。这是 ADR-026"物理段不进 identity"对 repo 段的延伸。
3. KB 逻辑名命名空间**独立于** registrar 的 workspace 资产命名: 同一短词(如 `logistics`)可在 KB 作合法逻辑名、在 registrar 资产操作语境按 ADR-026 GOTCHA#7 禁用裸名。两套命名空间各自自洽, 不强行合并。
4. 防回归: 回归测试用 **name ≠ leaf 的合成 fixture** 断言 identity 出 name(生产名可能 name==leaf, 物理数据测不出该 bug)。

## 否决的替代

- **物理 leaf**(现状): 物理改名即漂, 正是本 bug。
- **完整坐标**(`knowledge/work/logistics` 当 repo 段): 把物理布局(class/world)焊进 identity, taxonomy 一调又全漂(漂移点只从 leaf 换成 class/world, 病没治); 与 ADR-017"物理层不泄漏进检索维度"反向; object_key 引入 `/` 且变长。
- **改 registry name 迁就物理 leaf**: 违背 ADR-026 命名模型(坐标即身份) + 裸名歧义。

## 后果

- 三仓 repo identity 统一到 registry 逻辑名(均带语义后缀且 ≠ 物理 leaf, 自带防回归探针):
  - `logistics-kb`(归位, 迁移前原名, 旧 goldset/引用自动对上; leaf=logistics)
  - `docket-kb`(原 eridanus-pm 改名; 旧 `eridanus-pm:` / 漂移期 `docket:` 引用需扫描迁移; leaf=docket)
  - `the-orrery-kb`(原 the-orrery 改名; 旧 `the-orrery:` / 漂移期 `org-meta:` 引用需扫描迁移; leaf=org-meta)
- 需重建索引 + prune leaf 短名孤儿(logistics/docket/org-meta)与旧 name 残留(eridanus-pm/the-orrery)。
- repo 段口径从此单一真相 = registry name; KB-421 prune 扩展到"整个退役 repo 目录"场景。
- 执行追踪见 ERI-601。

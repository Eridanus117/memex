---
description: weave index semantic-sync 报「refusing to prune N/M points (>50%), likely a misconfigured root」时,先别查 root——多半是某次 chunk-mode sync 在 whole collection 里留下的另一模式残留点(点 ID 算法 whole=裸 object_id、chunk=v5(object_id:idx),模式一变全成 orphan);或游离的 WEAVE_QWEN3_CHUNKED_EMBEDDING env 把 sync 翻了模式。守卫拦得对,但合法批量清理会被永久卡死,连带新写 note 嵌不进。
keywords: [semantic-sync, mass-prune, refusing to prune, chunk模式, whole模式, 模式切换, orphan, CHUNKED_EMBEDDING, 召回卡死]
links: [adr-003-recall-rot-surface-not-engine, adr-002-indexability-contract]
code: [workspace-weave/crates/weave-cli/src/commands/retrieval.rs, workspace-weave/crates/weave-semantic-qwen3-qdrant/src/lib.rs]
kind: research
---

# semantic-sync mass-prune 真因 = 模式切换残留

## 一句话
`weave index semantic-sync` 中止报 `refusing to prune N/M points (>50%), likely a misconfigured root` 时,**真因通常不是 root**,而是 collection 里混了 chunk 模式和 whole 模式的点,whole-mode sync 把另一模式的点全判成 orphan。

## 机理(2026-06-07 rhizome 实测)
- point ID 算法:**whole 模式 = 裸 `source_object_id`**;**chunk 模式 = `uuid_v5(NAMESPACE, "{object_id}:{chunk_index}")`**(`point_id_for_unit` / `chunk_point_id`)。
- 某次手动 chunk-mode sync(shell 里带了 `WEAVE_QWEN3_CHUNKED_EMBEDDING=true`)在 whole collection 里给 4 篇大文档留下 37 个 chunk 点 → collection 变成 23 whole + 37 chunk 混合。
- whole-mode daemon sync 算 `expected_point_ids`=27 个裸 object_id → 37 个 chunk 点 ID 全对不上 → 判 37 orphan → 37/60>50% → 守卫中止 → adr-003 等新写 note 再也嵌不进、recall 报一堆 `compiled_hash_mismatch` 过期向量。
- 守卫**拦得对**(防按错模式删半个 collection),错在它把真因甩成「misconfigured root」误导排查。

## 诊断(30 秒坐实)
```
# 看 collection 点 ID 是裸 object_id(whole)还是 v5(chunk)
curl -s -X POST http://127.0.0.1:6333/collections/<col>/points/scroll \
  -H 'Content-Type: application/json' \
  -d '{"limit":200,"with_payload":["source_object_id"],"with_vector":false}' \
 | python3 -c "import sys,json;[print('whole' if str(p['id'])==(p.get('payload') or {}).get('source_object_id') else 'chunk', p['id']) for p in json.load(sys.stdin)['result']['points']]"
# whole 和 chunk 同时出现 = 混合模式 = 本病
env | grep CHUNK   # 游离 WEAVE_QWEN3_CHUNKED_EMBEDDING=true 也会触发
```

## 修
1. 统一模式:确认 `WEAVE_QWEN3_CHUNKED_EMBEDDING` 在所有 env 源一致(`semantic-sync.env` daemon 走、`hybrid-runtime.env` shell 走;chunk A/B 已否 → 两边都关)。
2. 删另一模式的残留点(外科 `points/delete` 按 ID),再正常 sync;或整 collection drop+rebuild。
3. 合法批量清理被守卫永久卡住时,用 `weave index semantic-sync --allow-major-prune` 一次性放行(2026-06-07 加,带 ⚠ 日志)。

## 上下游 / 相关
- 召回侧对偶:过期向量在 recall 健康行大声报(`[[adr-003-recall-rot-surface-not-engine]]` 的 stale 拆态);未索引在 doctor `semantic_index_coverage` 报。
- 守卫消息已改成自报两个真因(模式切换 vs 真 root)+ 指向 `--allow-major-prune`,见 `retrieval.rs`。

## 坑
- `cp`/relink 出来的 binary 若字节相同 md5 不变;chunk env 改了不重启 shell 不生效。
- daemon 走 `semantic-sync.env`(chunk 默认注释),手动在 shell 跑会被 `hybrid-runtime.env` 的残留 env 翻模式——两条路径 env 源不同,易踩。

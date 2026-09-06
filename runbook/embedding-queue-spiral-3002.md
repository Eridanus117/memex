---
description: ":3002 embedding 大面积超时/504 的诊断与修法:服务是 ssh 隧道远端单线程,空闲 0.3s/请求;雪崩真因 = 客户端短超时弃请求、服务端继续磨死请求、新请求排死队;修法 = 等队列排空 + 长客户端超时(600s),别重试轰炸"
keywords: [embedding超时, "3002", 队列雪崩, ssh隧道, "504", memex-sync]
kind: runbook
code: [memex/src/memex/config.py]
---

# :3002 embedding 队列雪崩 — 诊断与修法

## 症状

- `memex-sync` / weave sync 大面积 `embed: timed out` + `HTTP Error 504: Gateway Timeout`,跨仓全挂。
- 单独 curl 一条最小 embedding 也要 1-2 分钟以上。

## 检查

1. `lsof -iTCP:3002 -sTCP:LISTEN` → 是 **ssh 隧道**(远端服务),不是本机进程;CPU/内存看本机无意义。
2. 等几分钟无人请求后再 curl 一条最小 embedding:回到 ~0.3s = 服务本身健康,刚才是**队列堵塞**;仍慢 = 远端/隧道问题,查 qwen-embedding-sync-tunnel launchd 与远端。

## 真因(2026-06-10 KB-380 首建实测)

客户端超时(当时默认 90s)杀掉连接后,**远端单线程服务端继续计算被遗弃的请求**;后续请求排在死队列后面也超时,又制造新遗弃请求 → 螺旋恶化,看起来像"服务坏了"。

## 修法

1. **停止重试轰炸**,等队列自然排空(几分钟)。
2. 客户端超时给足(memex 已默认 600s,`KB_SEARCH_EMBED_TIMEOUT_SECS`):对单线程上游,**长等待远比制造遗弃请求便宜**。
3. 重跑即可:memex-sync 幂等(point_id+text_hash 命中即 skip),断点续跑零成本。

## 失败分支

- 排空后单条仍慢:查隧道(`launchctl print gui/$UID/com.a123.qwen-embedding-sync-tunnel`)与远端服务;
- 批量任务再雪崩:确认没有第二个并发 sync 在抢 :3002(launchd kb-central-sync 单实例,手动跑前先看它是否在跑)。

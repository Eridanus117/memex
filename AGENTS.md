# memex

memex 是 local-first 的 Markdown 知识库检索引擎：把多个源仓的 Markdown note 编译成可重建索引，提供 lexical（BM25）、semantic（向量）与 hybrid（weighted RRF）检索，入口命令是 `memex`（读路径）和 `memex-sync`（写路径）。

- 主要目录：`src/memex/`（读路径与检索 lane）、`src/memex/indexing/`（扫描、编译、同步）、`tests/`、`eval/`（goldset 评测）、`scripts/`（release 构建）；`docs/` 是公开文档入口，`decisions/`、`research/`、`runbook/` 是本仓自带的知识域（历史 ADR 在 `decisions/`）。
- 开发与检查：`uv sync --group dev` 后 `uv run poe check`（ruff lint + pyrefly + pytest），只跑测试用 `uv run pytest`。
- 架构与模块边界见 `docs/architecture.md`。

## Agent skills

### Issue tracker

Issues 在本仓 GitHub Issues（`Eridanus117/memex`）里，`gh` 在仓内自动识别。See `docs/agents/issue-tracker.md`.

### Triage labels

使用默认五个标签：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。See `docs/agents/triage-labels.md`.

### Domain docs

Single-context：根 `CONTEXT.md` + `docs/adr/`（按需生成）。See `docs/agents/domain.md`.

# My-Agent

[한국어 문서](README.md)

My-Agent is an asynchronous Python 3.11+ agent framework with swappable LLM
providers, a ReAct runtime, policy-gated tools, Discord and Telegram adapters,
managed MCP connections, context compression, and persistent SQLite sessions.

The primary executable is `myagen`. The former `agent-framework` executable is
kept as a deprecated alias for one release.

## Phase 0–8 status

The master-plan checklist is the requirements text, not a "done" ledger. The
table below reflects the 2026-08-31 code audit, kept in sync with the
[Korean README](README.md).

| Phase | Status | Actual scope |
|---|---|---|
| 0 | Done | Single-source version, `uv.lock`, Python 3.11/3.12 CI, baseline eval |
| 1 | Done | Run state, trace, timeout/cancellation, tool pairing |
| 2 | Done | Provider error normalization, retry/fallback, health command |
| 3 | Done | Tool contract, validation, policy, output/concurrency limits |
| 4 | Done (with limits) | Fail-closed HITL + `ApprovalService` wired into the executor; Docker backend is a loud-fail stub |
| 5 | Done (with limits) | File/terminal/web built-ins; local backend and explicit config flags required |
| 6 | Done | Managed stdio/HTTP MCP wired into CLI/bot startup/shutdown |
| 7 | Done | Versioned SQLite, metadata, FTS, persisted session commands, incomplete-turn quarantine |
| 8 | Done (approximate) | Trimming/summarizing wired; smallest-window fallback budgeting; token count is a heuristic |

See [`docs/remaining_risks.md`](docs/remaining_risks.md) for the risk register
and follow-up priorities.

## Install and configure

```bash
uv sync --locked --extra dev
uv run myagen config init
uv run myagen provider use openai
uv run myagen model set openai gpt-4o-mini
uv run myagen auth set openai
uv run myagen doctor
```

Secrets are stored in the operating-system credential backend, never in TOML.
User, project, environment, and CLI settings use this precedence:

```text
CLI > process environment > project config > user config > defaults
```

Legacy `.env` files remain readable for one compatibility release and can be
migrated without modifying the source file:

```bash
uv run myagen config migrate-env .env --dry-run
uv run myagen config migrate-env .env
```

## Commands

```bash
uv run myagen                         # interactive chat
uv run myagen ask "Summarize this"    # one-shot output
printf '%s\n' 'Summarize' | uv run myagen ask --stdin --json

uv run myagen provider list
uv run myagen provider check --all
uv run myagen tools permissions

uv run myagen mcp add notes --stdio -- node server.js
uv run myagen mcp add remote --http https://example.test/mcp
uv run myagen mcp test --all

uv run myagen config set memory.backend sqlite
uv run myagen session list
uv run myagen session search "query"
uv run myagen session resume cli:work

uv run myagen bot discord start
uv run myagen bot telegram start
uv run myagen completion bash
```

## Safety and lifecycle

- `HIGH` and `DESTRUCTIVE` tools fail closed without an explicit confirmation
  handler. Approval decisions are argument-bound and recorded by the executor.
- Provider fallback chains use the smallest declared context window.
- Provider SDK clients and MCP transports are owned and closed by a shared
  application lifecycle on success, failure, and cancellation.
- MCP stdio commands are stored as argv arrays and run without a shell. HTTP
  headers and extra environment secrets use credential-store references.
- SQLite uses versioned migrations, session metadata, FTS5 search, transactional
  tool-turn writes, and quarantine for incomplete historical tool turns.
- Tool arguments and CLI output apply field-aware credential redaction.

The Docker execution backend remains an intentional loud-fail scaffold; built-in
file and terminal tools currently use the local safe-root boundary. The web tool
checks DNS and redirects against non-public address ranges but does not pin the
validated address through the subsequent httpx connection.

## Development checks

```bash
uv run ruff check src tests
uv run mypy --strict src/agent_framework
uv run pytest -q
uv lock --check
```

See [the CLI implementation plan](docs/myagen_cli_plan.md),
[remaining risks](docs/remaining_risks.md), and [the changelog](CHANGELOG.md).

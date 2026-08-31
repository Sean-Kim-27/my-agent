# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Phase 8 — Context engine and compression

- Extended `agent_framework.memory.context` with atomic-group trimming and
  an LLM-backed summarizing strategy. `build_groups` partitions history so
  an assistant `tool_calls` message and its matching tool-result messages
  form a single, trim-atomic block; the trimmer never splits a call from
  its result.
- `TokenTrimmingContextManager` now always preserves every system message
  and the most recent non-system group (the current user turn). If system +
  current turn alone exceed the budget, it raises the new
  `ContextOverflowError` instead of silently truncating a mandatory
  message.
- Added `SummarizingContextManager` which compresses middle turns into an
  assistant-authored summary via the active LLM provider and falls back to
  plain trimming on any summarizer error. `Agent._fit_context` prefers the
  new async `afit()` path when available so summarization runs inside the
  existing await loop.
- `bootstrap.build_context_manager` reads the provider's advertised
  `context_window` (with per-model defaults for common OpenAI and
  Anthropic models, and `CONTEXT_MAX_TOKENS` as an explicit fallback),
  reserves `CONTEXT_HEADROOM_RATIO` for the completion, and attaches the
  resulting manager to the Agent. `build_agent` wires this in by default,
  and `CONTEXT_STRATEGY` selects `trimming` (default) or `summarizing`.
- Added 8 Phase 8 capability tests covering atomic-group preservation,
  full-group drop under tight budgets, oversized-message failure, current-
  turn preservation, summarizing compression, summarizer-failure fallback,
  sync-fit degradation, and bootstrap wiring.

### Phase 6 — MCP (Model Context Protocol) integration

- Added the `agent_framework.mcp` package. MCP servers are declarative
  (`MCPServerConfig`) and every discovered tool flows through the same
  `ToolExecutor` + `ToolPolicy` + HITL approval gate as built-in tools.
- `MCPTransport` is an abstract Protocol; concrete transports:
  - `StdioSubprocessTransport` speaks minimal MCP JSON-RPC 2.0 over
    stdin/stdout without depending on the official MCP SDK. Subprocess
    env is built from an explicit `env_allowlist` + `extra_env` — no
    host secret leaks into the child process. Close terminates the
    process group and drops in-flight futures.
  - `HttpMCPTransport` POSTs the same JSON-RPC methods to a Streamable
    HTTP endpoint via `httpx.AsyncClient`.
- `MCPManager` connects each server under separate `connect_timeout`,
  `init_timeout`, and `call_timeout` budgets. Failure of a single
  server is isolated (broken server surfaces `MCPConnectionError` in its
  `MCPServerStatus`, other servers still register their tools).
- Discovered tools are namespaced (default: `mcp.<server>.<tool>`),
  filtered by per-server `allow_tools` / `deny_tools`, and stamped with
  the server's `default_risk_level` and `default_idempotent` so
  `HIGH`/`DESTRUCTIVE` MCP tools automatically require human
  confirmation via `DefaultToolPolicy`.
- `MCPManager.reconnect(name)` deregisters existing tools before
  reconnecting so a reconnect never duplicates registrations.
  `MCPManager.shutdown()` closes every transport in order.
- Added `ENABLE_MCP` and `MCP_CONFIG_PATH` settings. The new async
  `bootstrap.bootstrap_mcp_servers(...)` reads the JSON config, builds
  the correct transport per server, and returns the `MCPManager` so
  the caller can await `shutdown()` alongside agent teardown.
- Added 21 Phase 6 capability tests covering config validation, env
  allowlist enforcement, namespacing, allow/deny filtering, per-phase
  timeout separation, reconnect deduplication, transport-error
  propagation, and per-server failure isolation.

### Phase 5 — Real Built-in Tools (file / terminal / web)

- Added the `agent_framework.tools.builtin` package. Every tool is a thin
  adapter over an `ExecutionBackend`, so safe-root, allow_writes,
  allow_subprocess, env allowlist, output caps, and audit logging from
  Phase 4 are inherited unchanged — the built-ins add no new host access
  paths.
- File tools: `builtin.file.list_directory`, `builtin.file.read_file`,
  `builtin.file.write_file`, and `builtin.file.apply_patch`.
  `apply_patch` is an exact find/replace edit that requires the caller
  to declare `expected_occurrences`; ambiguous or zero matches fail
  before the file is touched, and the write itself is refused when the
  backend was not configured with `allow_writes`.
- Terminal tool: `builtin.terminal.run_command` accepts an explicit
  `argv` list (shell strings are rejected at the schema and tool
  layer), applies a per-tool timeout cap on top of the backend's own
  timeout, and surfaces exit code, duration, timeout flag, and
  truncation flag as structured JSON.
- Web tools: `builtin.web.http_fetch` and `builtin.web.http_fetch_text`
  enforce fail-closed SSRF defenses — non-http(s) schemes, IP literals
  and hostnames that resolve to private / loopback / link-local /
  multicast / reserved / unspecified ranges (including the AWS/GCP
  metadata endpoint 169.254.169.254) are rejected before the request
  leaves the process. Redirects are followed manually with the same
  address check on every hop, and responses are capped at 512 KiB by
  default (4 MiB hard ceiling).
- Added `register_builtin_tools(registry, backend, …)` plus new
  `ENABLE_BUILTIN_TOOLS`, `BUILTIN_TOOLS_INCLUDE_FILES`,
  `BUILTIN_TOOLS_INCLUDE_TERMINAL`, and `BUILTIN_TOOLS_INCLUDE_WEB`
  settings. `bootstrap.build_agent()` registers the built-ins only when
  the toggle is on, so existing deployments are unaffected.
- Added 27 Phase 5 capability tests covering safe-root enforcement,
  write / patch fail-closed defaults, terminal timeout & shell-string
  rejection, SSRF blocking (private / loopback / metadata / private-on-
  redirect), response truncation, HTML text extraction, and registry
  wiring. The complete suite now contains 234 tests.

Public API: `register_builtin_tools`, `register_file_tools`,
`register_terminal_tools`, `register_web_tools`, `WebFetchError`,
`WebFetchResult`, and `extract_text_from_html` are exported from
`agent_framework`. No data migrations. Default behavior is unchanged —
built-ins must be enabled via `ENABLE_BUILTIN_TOOLS=true` and the
Phase 4 backend flags.

### Phase 4 — Security boundary and Execution Backend

- Added `execution/backend.py` defining the `ExecutionBackend` Protocol
  and frozen contracts (`CommandSpec`, `CommandResult`, `FileReadSpec`,
  `FileWriteSpec`, `FileReadResult`). `CommandSpec.argv` rejects shell
  strings at model-validation time to prevent shell-string command
  injection.
- Added `execution/local.py::LocalExecutionBackend`. Writes, destructive
  filesystem operations, and subprocess execution are OFF by default;
  each is enabled explicitly via `LocalExecutionConfig`. Subprocesses
  run in a new session, honor a per-call timeout with `os.killpg`
  cleanup, cap stdout/stderr to `max_output_bytes`, and forward only
  environment variables in the configured `env_allowlist` (host API
  keys never leak into children).
- Added `execution/paths.py::resolve_safe_path` — the single fail-closed
  path resolver. Rejects empty paths, `..` traversal, absolute paths
  that escape the safe root, and symlinks that resolve outside the safe
  root. Nested symlinks that remain inside the safe root are allowed.
- Added `execution/docker.py::DockerExecutionBackend` as a
  container-isolation scaffold that raises `NotImplementedError` for
  every operation so mis-wired production configs fail loudly.
- Added `execution/approval.py::ApprovalService` — durable
  command-approval records with a `PENDING → APPROVED | REJECTED`
  state machine, TTL-driven `EXPIRED` transition, argument-bound
  reuse (mutating any argument invalidates a prior approval), and
  frozen `ApprovalState` / `ApprovalDecision` snapshots.
- Added `logging/audit.py` with a dedicated non-propagating logger
  (`agent_framework.audit`), a JSON-serialized `AuditEvent` model, and
  automatic secret masking on every recorded field.
- Added `bootstrap.build_execution_backend()` and
  `bootstrap.build_approval_service()` plus new `EXECUTION_*` /
  `APPROVAL_*` settings; the fail-closed defaults are documented in
  `.env.example`.
- Added 32 Phase 4 capability tests covering path safety, subprocess
  env allowlist, timeout with process-group kill, output caps, write /
  destructive fail-closed defaults, Docker stub Protocol conformance,
  approval state machine transitions, TTL expiry, argument-bound
  matching, and audit-event masking. The complete suite now contains
  207 tests.

Public API: `ExecutionBackend`, `LocalExecutionBackend`,
`LocalExecutionConfig`, `DockerExecutionBackend`,
`DockerExecutionConfig`, `CommandSpec`, `CommandResult`,
`FileReadSpec`, `FileWriteSpec`, `FileReadResult`,
`ExecutionDeniedError`, `resolve_safe_path`, `PathSafetyError`,
`ApprovalService`, `ApprovalState`, `ApprovalStatus`,
`ApprovalDecision`, `AuditEvent`, `AuditEventKind`, and
`get_audit_logger` are available from their respective submodules.
`build_execution_backend` and `build_approval_service` are added to
`agent_framework.bootstrap`. No data migrations. Existing tools that
never touched a filesystem or subprocess are unaffected — the
execution backend is opt-in wiring that Phase 5 will consume.

### Phase 3 — Tool contract, toolsets, and policy layer

- Added `ToolRiskLevel` (`safe / low / medium / high / destructive`) and
  extended `ToolDefinition` with `toolset`, `idempotent`, `max_output_bytes`,
  `max_concurrency`, and a derived `namespace` property.
- Added `ToolExecutionContext` (`run_id`, `step`, `session_id`, `actor`,
  `platform`) threaded from `Agent` into `ToolExecutor.execute_all` and passed
  through to the policy engine.
- Added strict argument validation in `tools/schema.validate_arguments()`;
  the executor now rejects unknown arguments, missing required fields, and
  wrong types **before** invoking the tool (fail closed).
- Added `ToolPolicy` protocol, `DefaultToolPolicy`, and `AllowAllPolicy`.
  Policy decisions are separated from execution — agents cannot bypass the
  human confirmation gate.
- Added registry safeguards: duplicate registration raises
  `ToolRegistryError` unless `replace=True`; namespaced names such as
  `builtin.file.read` are first-class; and `disable_toolset`,
  `enable_toolset`, `apply_preset(allow_toolsets=…)` control visible tools.
- Added output-size caps: outputs exceeding `max_output_bytes` (per-tool or
  the executor default of 32 KiB) are truncated in `content` and the full
  payload is surfaced on `ToolCallResult.artifact`.
- Added per-tool `asyncio.Semaphore` concurrency limits and a retry policy
  that only retries idempotent, non-destructive tools.
- Added 17 Phase 3 capability tests. The complete suite now contains 175
  tests.

Public API: `ToolRiskLevel`, `ToolExecutionContext`, `ToolArtifact`,
`ToolPolicy`, `ToolPolicyDecision`, `ToolPolicyError`, `DefaultToolPolicy`,
`AllowAllPolicy`, and `ToolRegistryError` are exported from
`agent_framework`. `ToolRegistry.register(...)` accepts new keyword-only
arguments (`risk_level`, `toolset`, `idempotent`, `max_output_bytes`,
`max_concurrency`, `replace`); duplicate registration now raises unless
`replace=True`. `ToolExecutor.__init__` accepts `policy`, `max_retries`, and
`default_max_output_bytes`. `ToolExecutor.execute*` accept an optional
keyword-only `context: ToolExecutionContext`. Legacy
`requires_confirmation=True` still forces human approval; existing tools
continue to work with `risk_level` defaulted to `SAFE`. No data migrations.

### Phase 2 — Provider runtime, retry, and fallback

- Added provider-neutral capability validation and error normalization before
  the Agent core, including masked credential-bearing error text.
- Added transient retry classification for timeouts, 408/429, connection
  failures, and 5xx responses; `Retry-After` takes precedence over exponential
  backoff with jitter. SDK-native retries are disabled so the configured retry
  count remains authoritative.
- Added ordered provider fallback for a single generation boundary. The
  runtime never restarts an Agent run or executes tools, and a repeated tool
  call ID across a provider transition is rejected before duplicate side
  effects.
- Added connect/read/write/pool timeout configuration, per-model capability and
  context-window metadata, and `agent-framework --providers --check` health
  diagnostics.
- Added Phase 2 capability tests and fixed PEP 604 optional schema handling on
  Python 3.12. The complete suite now contains 158 tests.

Public API: `ProviderRuntime`, `ProviderTimeouts`, `ModelMetadata`,
`create_provider_runtime()`, and the normalized provider error subclasses are
exported from `agent_framework`. No data migrations.

### Phase 1 — Agent run-loop state machine

- Added public `RunContext` and `RunState` primitives so every started run has
  a stable `run_id` and ends as `completed`, `failed`, or `cancelled`.
- Added whole-run timeouts and cooperative cancellation across in-flight
  provider and tool awaits, with asyncio task cleanup.
- Unified lifecycle dispatch for persistent and one-off callbacks and ensured
  unhandled errors emit `on_agent_error` exactly once.
- Re-fit context before every provider call and fail closed when tool calls and
  results are missing, duplicated, mismatched, or out of order.
- Extended `AgentStep` with provider, model, token usage, latency, and error
  metadata; max-step exhaustion now raises a structured `AgentError`.
- Added 14 Phase 1 capability/regression tests. The complete suite now contains
  132 unit tests and 10 baseline evals.

Public API: `RunContext` and `RunState` are exported from `agent_framework`;
`Agent.run()` and `Agent.run_with_trace()` accept `run_context` and `timeout`.
No data migrations.

### Phase 0 — Baseline, version, and release alignment

- Unified the package version. `pyproject.toml` is now the single source of
  truth (`0.3.0`); `agent_framework.__version__` is derived from
  `importlib.metadata` and falls back to `0.0.0+local` in source checkouts.
- Added the `agent-framework` console entry point via `[project.scripts]`
  → `agent_framework.main:main`.
- Generated `uv.lock` and switched CI to `uv sync --locked --extra dev` on
  Python 3.11 and 3.12 so every job resolves the same dependency set.
- Corrected the unit-test count in `README.md` and `README_EN.md` (67 → 118)
  to match `pytest --collect-only`.
- Added `docs/architecture.md` capturing the current package layout,
  dependency direction, runtime flow, public API, and the intentional gaps
  the later master-plan phases will close.
- Added `docs/master_plan.md` — the Phase 0-8 master plan checked into the
  repo alongside the code it drives.
- Added `tests/evals/` with 10 hermetic baseline scenarios (plain chat,
  single tool call, parallel tool calls, tool-error self-correction, tool
  timeout, provider 429 retry, max steps, cross-session isolation, SQLite
  restart restore, secret masking). These run as part of `pytest -q`.

No public API changes. No data migrations.

# Architecture Overview

_This document is the source of truth for the current architecture and dependency
direction of `agent-framework`. It is written as part of Phase 0 of the master
plan; later phases (state machine, provider runtime, tool policy, execution
backend, MCP, session store, context engine) will extend this document as they
land._

## Guiding principles

- **Dependency Inversion.** The `Agent` core depends on abstractions only:
  `LLMProvider`, `AuthenticationProvider`, `ConversationMemory`, `ToolRegistry`,
  `ToolExecutor`, callback protocols. Concrete SDKs (OpenAI, Anthropic, NVIDIA
  NIM, `discord.py`, `python-telegram-bot`) live at the edges.
- **Async-first.** All network I/O and tool execution are non-blocking. Every
  integration boundary must be `await`-able.
- **Fail closed.** Security-relevant decisions (auth, tool approval, filesystem
  access) default to deny.
- **Small surface.** New capabilities extend the abstraction layer rather than
  branching inside the core.

## Package layout

```
src/agent_framework/
├── __init__.py            # Public API re-exports + __version__ (importlib.metadata)
├── main.py                # CLI entrypoint (also wired via [project.scripts])
├── bootstrap.py           # Composition root: assembles Agent + providers + memory
├── exceptions.py          # Framework-wide typed exceptions
├── agent/
│   ├── agent.py           # Agent core + run() / run_with_trace() loop
│   ├── events.py          # Callback handler protocols
│   └── runtime.py         # RunContext, RunState (lifecycle state machine)
├── llm/
│   ├── base.py            # LLMProvider ABC (+ streaming protocol)
│   ├── factory.py         # create_llm_provider() dynamic factory
│   ├── retry.py           # Retry-After + exponential jitter retry policy
│   ├── errors.py          # SDK/HTTP error normalization + secret masking
│   ├── runtime.py         # Ordered provider fallback boundary
│   ├── openai_provider.py, anthropic_provider.py,
│   ├── nvidia_nim_provider.py, openai_compatible.py
├── auth/
│   ├── base.py            # AuthenticationProvider ABC + NoAuth
│   ├── api_key.py         # ApiKeyAuth
│   └── codex_oauth.py     # CodexOAuthAuth (official token lifecycle)
├── tools/
│   ├── registry.py        # ToolRegistry + @tool decorator, toolset gating
│   ├── executor.py        # ToolExecutor: validation, policy, timeout, retry
│   ├── policy.py          # ToolPolicy (DefaultToolPolicy, AllowAllPolicy)
│   ├── schema.py          # Python signature → JSON schema + arg validation
│   └── safe_math.py       # Sample deterministic tool
├── memory/
│   ├── base.py            # ConversationMemory ABC
│   ├── in_memory.py       # Default in-process store
│   ├── sqlite.py          # SQLite-backed persistent store
│   ├── session.py         # SessionManager for per-actor isolation
│   └── context.py         # ContextManager (token trimming + summarizing, Phase 8)
├── models/
│   ├── message.py         # Message + MessageRole
│   ├── response.py        # LLMResponse, TokenUsage, ProviderCapabilities
│   ├── tool.py            # ToolCall/Result/Definition + RiskLevel/Policy/Context
│   └── events.py          # AgentStep, AgentRunResult, StreamChunk
├── config/
│   └── settings.py        # pydantic-settings central configuration
├── execution/
│   ├── backend.py         # ExecutionBackend Protocol + Command/File specs (Phase 4)
│   ├── local.py           # LocalExecutionBackend: safe root + env allowlist + subprocess controls
│   ├── docker.py          # DockerExecutionBackend scaffold (raises NotImplementedError)
│   ├── paths.py           # resolve_safe_path — fail-closed path containment
│   └── approval.py        # Command approval state machine (argument-bound + TTL)
├── mcp/
│   ├── config.py          # MCPServerConfig (stdio/http, timeouts, allow/deny, env)
│   ├── transport.py       # MCPTransport Protocol + MCPToolInfo
│   ├── stdio.py           # StdioSubprocessTransport (JSON-RPC over stdin/stdout)
│   ├── http.py            # HttpMCPTransport (JSON-RPC over Streamable HTTP)
│   ├── manager.py         # MCPManager: connect, register, isolate, shutdown
│   ├── env.py             # Child-env allowlist builder
│   └── errors.py          # MCPError hierarchy
├── logging/
│   ├── logger.py          # Structured logger with regex-based secret masking
│   └── audit.py           # Separate audit logger (agent_framework.audit)
└── integrations/
    ├── cli/{bot,router,callbacks}.py
    ├── discord/{bot,router}.py
    └── telegram/{bot,router}.py
```

## Dependency direction

```
                  integrations/*  (CLI / Discord / Telegram)
                           │
                           ▼
                       bootstrap.py
                           │
                           ▼
                       agent/agent.py  ─────────►  agent/events.py
                     /       │       \
                    ▼        ▼        ▼
              LLMProvider  ToolRegistry  ConversationMemory
              (llm/*)      + Executor    + SessionManager
                    │        │
                    ▼        ▼
              AuthenticationProvider   models/*
              (auth/*)
```

Direction rules:

- `agent/*` depends on `models/*`, `tools/*` (via protocols), `memory/*` (via
  protocol), `llm/base`, `logging/*`. It **must not** import concrete providers,
  concrete integrations, or `bootstrap`.
- `llm/*` providers depend on `auth/*`, `models/*`, and `logging/*`. They do not
  reach back into `agent/*`.
- `integrations/*` depend on `agent/*`, `memory/session`, and `bootstrap`; they
  are always the outermost layer.
- `bootstrap.py` is the only module that instantiates concrete providers,
  memory backends, and tools together. Everything else receives abstractions.

## Runtime execution flow

1. **CLI / bot startup** — `agent_framework.main:main` parses arguments,
   `bootstrap.build_agent()` wires an `Agent` with the selected `LLMProvider`,
   `AuthenticationProvider`, `ConversationMemory`, `ToolRegistry`, and callback
   handlers.
2. **Session routing** — the integration layer maps a raw event (CLI stdin,
   Discord/Telegram message) to a canonical `session_id` and hands the user
   utterance to the agent.
3. **Agent loop** — `Agent.run_with_trace()` iteratively:
   a. Loads the session history from `ConversationMemory`.
   b. Fits the context budget and calls the LLM via `LLMProvider.generate()`.
   c. If tool calls are returned, invokes `ToolExecutor.execute()` for each
      and appends `tool` messages to memory.
   d. Emits lifecycle events to registered `AgentCallbackHandler`s.
   e. Terminates on a plain-text response, on `max_steps`, or on an error.
4. **Response delivery** — the integration formats and dispatches the final
   assistant message back to the platform (respecting per-platform limits).

## Public API surface

`agent_framework/__init__.py` re-exports the stable API:

- Core: `Agent`, `AgentCallbackHandler`, `ConsoleCallbackHandler`,
  `AgentRunResult`, `AgentStep`, `StreamChunk`, `RunContext`, `RunState`.
- LLM: `LLMProvider`, `create_llm_provider`, concrete providers
  (`OpenAIProvider`, `AnthropicProvider`, `NvidiaNIMProvider`,
  `OpenAICompatibleProvider`), `ProviderRuntime`, `create_provider_runtime`,
  `LLMResponse`, `TokenUsage`, `ProviderCapabilities`, `ProviderTimeouts`, and
  `ModelMetadata`.
- Auth: `AuthenticationProvider`, `NoAuth`, `ApiKeyAuth`, `CodexOAuthAuth`,
  `CodexOAuthToken`.
- Memory: `ConversationMemory`, `InMemoryConversationMemory`, `SessionManager`.
- Tools: `ToolRegistry`, `ToolRegistryError`, `ToolExecutor`, `ToolDefinition`,
  `ToolCall`, `ToolCallResult`, `ToolArtifact`, `ToolRiskLevel`,
  `ToolExecutionContext`, `ToolPolicy`, `DefaultToolPolicy`, `AllowAllPolicy`,
  `ToolPolicyDecision`, `ToolPolicyError`, `generate_tool_definition`,
  `python_type_to_json_schema`.
- Models: `Message`, `MessageRole`.
- Config & logging: `Settings`, `get_settings`, `get_logger`, `mask_secrets`.
- Exceptions: `AgentFrameworkError`, `AgentError`, `AuthenticationError`,
  `ConfigurationError`, `LLMProviderError`, `MemoryError`,
  `OAuthAuthenticationError`, `ProviderAuthenticationError`,
  `ProviderCapabilityError`, `FallbackExhaustedError`,
  `ProviderTimeoutError`, `ProviderUnavailableError`, `RateLimitError`,
  `SessionError`.

`__version__` is derived from installed package metadata
(`importlib.metadata.version("agent-framework")`) so `pyproject.toml` is the
single source of truth. In an un-installed source checkout it falls back to
`0.0.0+local`.

## Known gaps (tracked by the master plan)

The following gaps are intentional and are the subject of later phases:

- **Phase 1** — _Completed._ `agent/runtime.py` introduces `RunContext` and the
  `RunState` lifecycle (`pending → running → completed | failed | cancelled`).
  `run_with_trace()` now:
  - dispatches lifecycle events to both persistent and one-off callbacks,
  - fires `on_agent_error` exactly once via a single outer handler,
  - re-fits the context (via `ContextManager.afit` when available,
    otherwise `.fit`) before every provider call,
  - validates that every tool_call has exactly one matching tool_result and
    reorders results to match the call sequence,
  - supports wall-clock timeout and cooperative cancellation
    (`RunContext.cancel()` interrupts in-flight provider and async tool awaits
    and drains their asyncio tasks),
  - records per-step `provider`, `model`, `token_usage` and `error` on
    `AgentStep`, and terminates `max_steps` overflow with a structured
    `AgentError` while stamping `RunState.FAILED` on the context.
  Synchronous tool functions already running in worker threads cannot be
  forcibly stopped by asyncio cancellation; callers should keep side-effecting
  sync tools short-lived or implement them as cancellation-aware async tools.
- **Phase 2** — _Completed._ Provider calls are normalized behind the
  `LLMProvider`/`ProviderRuntime` boundary. Requests validate capabilities
  before network I/O; transient failures retry with `Retry-After` or
  exponential jitter while auth/bad-request failures fail immediately. The
  optional ordered fallback chain operates on one generation call only and
  never restarts the Agent or executes tools. Repeated tool-call IDs across a
  provider transition are rejected before a second side effect. OpenAI and
  Anthropic transports receive distinct connect/read/write/pool timeouts,
  model metadata can override capability/context-window values, and
  `--providers --check` reports live endpoint health without printing secrets.
- **Phase 3** — _Completed._ Tools now carry explicit contracts:
  - `ToolRiskLevel` (`safe / low / medium / high / destructive`) drives policy
    decisions; `HIGH` and `DESTRUCTIVE` require human confirmation and
    `DESTRUCTIVE` also blocks auto-retry.
  - `ToolDefinition` metadata adds `toolset`, `namespace` (derived from the
    dotted name), `idempotent`, `max_output_bytes`, and `max_concurrency`.
  - `ToolExecutionContext` is threaded from the Agent to the executor and
    policy engine (`run_id`, `step`, `session_id`, `platform`, `actor`).
  - Argument validation (`tools/schema.validate_arguments`) rejects unknown
    fields, missing required parameters, and mismatched types **before**
    invocation.
  - `ToolRegistry` fails closed on duplicate registration (opt-in `replace=True`),
    supports namespaced names (`builtin.file.read`), and provides
    `disable_toolset`, `enable_toolset`, and `apply_preset(allow_toolsets=…)`.
  - `DefaultToolPolicy` decouples policy from execution; agents cannot bypass
    the confirmation gate because the executor always consults the policy.
  - Output past `max_output_bytes` is truncated in the summary and preserved
    on the `ToolCallResult.artifact` payload.
  - Idempotent tools may be retried up to `ToolExecutor(max_retries=…)`;
    non-idempotent and destructive tools are executed exactly once.
  - Per-tool `asyncio.Semaphore` enforces `max_concurrency` across
    `execute_all`.
- **Phase 4** — _Completed._ Security boundaries and execution isolation are
  in place before Phase 5 lands any real tools:
  - `execution/backend.py` defines the `ExecutionBackend` Protocol along with
    frozen `CommandSpec`, `CommandResult`, `FileReadSpec`, `FileWriteSpec`,
    and `FileReadResult` contracts. `CommandSpec.argv` refuses shell strings
    at construction time to prevent shell-string injection.
  - `execution/local.py::LocalExecutionBackend` is the direct-host backend.
    Writes, destructive filesystem operations, and subprocess execution are
    OFF by default; each capability is an explicit opt-in on
    `LocalExecutionConfig`. Subprocesses run in a new session with
    `os.killpg` cleanup on timeout, an `env_allowlist` that never forwards
    other host variables (so API keys stay out of children), and stdout/
    stderr capped by `max_output_bytes`.
  - `execution/paths.py::resolve_safe_path` is the single entry point for
    filesystem access. It rejects empty paths, `..` traversal, absolute
    paths that escape the safe root, and symlinks that point outside the
    safe root — using `Path.resolve(strict=False)` so nested symlinks that
    stay inside the safe root are still allowed.
  - `execution/docker.py::DockerExecutionBackend` is the container-isolated
    scaffold. Every operation raises `NotImplementedError` so a mis-wired
    production config fails loudly instead of silently degrading to
    host-level execution.
  - `execution/approval.py::ApprovalService` implements the command-approval
    state machine (`PENDING → APPROVED | REJECTED`, plus TTL-driven
    `EXPIRED`). Approvals are bound to (tool_name, actor, canonical
    argument fingerprint), so mutating any argument makes a prior approval
    ineligible for reuse. Snapshots are returned as frozen Pydantic models.
  - `logging/audit.py::get_audit_logger` provides the dedicated
    `agent_framework.audit` logger tree (non-propagating), a JSON-serialized
    `AuditEvent`, and applies the shared secret masking to every recorded
    detail so audit records never leak credentials.
  - `bootstrap.build_execution_backend` and `bootstrap.build_approval_service`
    wire the new primitives from `Settings`; the `EXECUTION_*` and
    `APPROVAL_*` environment variables in `.env.example` document the
    fail-closed defaults.
  Phase 4 does not connect the backend/approval service to any live tool —
  that wiring lands with the Phase 5 built-in file, terminal, and web tools.
- **Phase 5** — _Completed._ Real built-in tools live in
  `tools/builtin/` and route every operation through the Phase 4
  `ExecutionBackend`:
  - `tools/builtin/files.py` — `builtin.file.list_directory`,
    `builtin.file.read_file`, `builtin.file.write_file`, and
    `builtin.file.apply_patch`. `apply_patch` is an exact find/replace
    edit that requires the caller to declare `expected_occurrences`
    and refuses the write if the count does not match, so ambiguous
    edits fail before touching the file.
  - `tools/builtin/terminal.py` — `builtin.terminal.run_command`
    accepts only an argv list (shell strings are rejected at both the
    tool and `CommandSpec` layer) and enforces a built-in timeout cap
    on top of the backend timeout.
  - `tools/builtin/web.py` — `builtin.web.http_fetch` and
    `builtin.web.http_fetch_text` implement fail-closed SSRF defenses:
    non-http(s) schemes, IP literals in private / loopback / link-local
    / multicast / reserved / unspecified ranges (including the cloud
    metadata endpoint 169.254.169.254), and hostnames that resolve to
    those ranges are rejected before the request leaves the process.
    Redirects are followed manually with the same address check on
    every hop and responses are size-capped.
  - `tools/builtin/registry.py::register_builtin_tools` wires all
    three families onto a `ToolRegistry`. `bootstrap.build_agent`
    registers the built-ins only when `ENABLE_BUILTIN_TOOLS=true`, so
    existing deployments keep the demo-tool default.
- **Phase 6** — _Completed._ MCP (Model Context Protocol) integration lives in
  `mcp/` and reuses the existing tool policy pipeline:
  - `mcp/config.py::MCPServerConfig` validates transport-specific fields
    (`stdio` requires `command`, `http` requires `url`), holds separate
    `connect_timeout`, `init_timeout`, and `call_timeout` budgets, and carries
    per-server `allow_tools` / `deny_tools`, `env_allowlist`, `extra_env`,
    `namespace`, `default_risk_level`, and `default_idempotent` defaults.
  - `mcp/transport.py` defines the `MCPTransport` Protocol and the
    `MCPToolInfo` payload used by discovery; concrete transports (stdio, HTTP,
    or fakes in tests) plug in behind it.
  - `mcp/stdio.py::StdioSubprocessTransport` speaks minimal MCP JSON-RPC 2.0
    (`initialize`, `notifications/initialized`, `tools/list`, `tools/call`)
    over stdin/stdout. Subprocess env is built from `env_allowlist` +
    `extra_env` only — no host secret leaks into the child. Close terminates
    the process group and drops any in-flight futures.
  - `mcp/http.py::HttpMCPTransport` POSTs the same JSON-RPC methods to a
    Streamable HTTP endpoint via `httpx.AsyncClient` and surfaces HTTP/JSON
    errors through the `MCPError` hierarchy.
  - `mcp/manager.py::MCPManager` connects each server behind its per-phase
    timeout, isolates individual failures (a broken server does not stop the
    others), namespaces every discovered tool as `<namespace>.<tool>`,
    stamps the configured `default_risk_level` / `default_idempotent`
    onto the `ToolDefinition`, and registers a proxy callable so tool
    invocations flow through the same `ToolExecutor` / `ToolPolicy` / HITL
    approval gate as built-in tools. `reconnect(name)` deregisters stale
    entries before reconnecting so a reconnect never duplicates tool
    registrations. `shutdown()` closes every transport.
  - `bootstrap.bootstrap_mcp_servers` reads legacy `MCP_CONFIG_PATH` or managed
    `mcp.servers`, resolves credential-store references, and constructs the
    correct transport. `ApplicationLifecycle` owns shutdown on success/failure.
- **Phase 7 / 9.5** — _Completed._ `memory/sqlite_store.py` owns schema v2,
  migration metadata, WAL/busy timeout, session metadata, FTS5 search,
  transactional tool-turn writes, and quarantine of incomplete historical
  turns. `myagen session` exposes persisted list/show/search/resume/clear/delete.
- **Phase 8** — _Completed._ `memory/context.py` now ships two strategies
  (`TokenTrimmingContextManager`, `SummarizingContextManager`) that share a
  `build_groups` partitioner. Groups are trim-atomic: an assistant
  `tool_calls` message and each of its matching tool-result messages are
  kept or dropped together, preserving the invariant enforced by
  `Agent._validate_tool_pairing`. The trimmer always keeps every system
  message and the most recent non-system group (the current user turn); when
  system + current turn together exceed the budget it raises
  `ContextOverflowError` instead of truncating a mandatory message. The
  summarizing strategy compresses middle history into an assistant summary
  via the active LLM provider and falls back to plain trimming on any
  summarizer error. `bootstrap.build_context_manager` reads the provider's
  advertised `context_window` (with `context_max_tokens` as an explicit
  fallback and per-model defaults for common OpenAI/Anthropic models),
  reserves `context_headroom_ratio` for the completion, and attaches the
  resulting manager to the Agent. `Agent._fit_context` prefers async
  `afit()` when available so summarization runs off the event loop path
  without stalling other awaits.
- **Phase 9** — _Completed._ `cli/` provides the `myagen` router, atomic
  user/project TOML, OS-keyring secrets, settings precedence/source reporting,
  Provider/model/tool/MCP/bot/session commands, `.env` migration, completion,
  stable exit codes, and versioned JSON output. `lifecycle.py` owns Provider and
  MCP resources; `agent-framework` is a one-release deprecated alias.

## Quality gates

The CI workflow (`.github/workflows/ci.yml`) runs the same commands you should
run locally, against the lockfile on Python 3.11 and 3.12:

```bash
uv sync --locked --extra dev
uv run ruff check src/ tests/
uv run mypy --strict src/agent_framework
uv run pytest -q
```

`tests/evals/` holds behavior-level scenarios (agent + tool + memory) beyond
the unit tests, and is executed as part of `pytest`.

# Remaining Risks Register — master_plan Phases 0–8

Consolidated **"남은 위험"** section from every Phase completion report
recorded across prior work sessions. Each item is the risk exactly as it
was flagged when the phase landed, so future work can decide whether it
still applies, has been superseded by a later phase, or needs a dedicated
follow-up.

Verify each risk against current code before acting — some were mitigated
by subsequent phases (noted inline where applicable).

## 2026-08-31 final audit summary

This audit compared the Phase 0–8 master-plan acceptance criteria with the
actual CLI/bootstrap paths, not only with the presence of individual classes
and unit tests. The repository passes its automated quality gates, but it is
**not yet accurate to call every Phase 0–8 acceptance criterion complete**.

Validation evidence:

- `ruff check src tests`: passed.
- `mypy --strict src/agent_framework`: passed (75 source files).
- `pytest -q`: passed (275 tests: 265 unit + 10 eval).
- `uv lock --check`: passed.
- `pip-audit` against the fully exported locked dependency set: no known
  vulnerabilities; the editable project itself was skipped because its version
  cannot be inferred from the exported editable URL.
- Installed entry-point smoke tests (`agent-framework --help`,
  `agent-framework --providers`): passed.
- Current tracked files and non-test Git history scan: no credential-like value
  was found. This is a pattern scan, not a substitute for a dedicated secret
  scanner in CI.

### 2026-08-31 Phase 9 remediation update

The original audit below is retained as historical evidence. Phase 9.0–9.6
subsequently closed every P0/P1 Go/No-Go item: confirmation now fails closed,
`ApprovalService` records executor decisions, fallback budgeting uses the
smallest declared window, owned Provider clients and MCP transports close under
one lifecycle, SQLite has versioned metadata/FTS/session commands, and incomplete
tool turns are transactionally stored or quarantined on read. The shipped
`myagen` router now owns config, secret, Provider, MCP, session, bot, doctor,
completion, and `.env` migration commands; `agent-framework` is a deprecated
one-release alias.

Remaining release risks are now limited to the explicitly documented P2/design
constraints: Docker isolation is still a loud-fail scaffold, web DNS validation
is not connection-pinned, sync worker-thread tools cannot be forcibly cancelled,
token counting/model metadata remain approximate, and real third-party MCP
interoperability still depends on each server's protocol behavior.

Phase 9 verification: Ruff passed; MyPy strict passed for 94 source files;
pytest passed 304 tests (294 unit + 10 eval); `uv lock --check`, wheel build,
Python 3.11 clean-venv install, `myagen --help/version`, and the deprecated
alias smoke test passed.

> **Reproducing the gates.** The dev toolchain (ruff, mypy, pytest) is
> installed by the `dev` extra. Run `uv sync --locked --extra dev` first;
> without it the `.venv` binaries referenced below will not exist. Follow-up
> verification is captured in [phase9_verification_report.md](phase9_verification_report.md).

### Go/No-Go assessment

| Priority | Area | Assessment | Release implication |
|---|---|---|---|
| P0 | HITL fail-closed policy | **Resolved in Phase 9.0.** Empty/base callbacks reject; executor decisions are recorded by `ApprovalService`. | Keep explicit confirmation-adapter regression tests. |
| P1 | MCP lifecycle | **Resolved in Phase 9.3–9.4.** Managed MCP starts and stops inside `ApplicationLifecycle`. | Third-party server interoperability remains an environment-level check. |
| P1 | Persistent sessions | **Resolved in Phase 9.5.** Versioned schema, metadata, FTS5 and persisted commands are implemented. | Back up databases before future breaking migrations. |
| P1 | Fallback context budget | **Resolved in Phase 9.0.** The smallest known fallback window is used. | Unknown-model metadata can still drift. |
| P1 | Interrupted tool turns | **Resolved in Phase 9.5.** Tool-call/result groups use `add_many`; legacy partial suffixes are quarantined. | A process death after an external side effect but before commit still requires tool-level idempotency. |
| P1 | Provider client lifecycle | **Resolved in Phase 9.0–9.3.** Owned SDK clients are cached/closed; injected clients remain caller-owned. | Keep lifecycle tests on SDK upgrades. |
| P2 | Documentation/roadmap | **Resolved in Phase 9.6.** Korean/English READMEs and the CLI plan describe the shipped router. | Maintain the machine-checked Settings mapping registry. |

### Additional confirmed risks

- ~~**Configuration precedence bug:** `argparse` gives `--session` the concrete
  default `cli:default`, so `DEFAULT_SESSION_ID` from `Settings` is never used
  by the main entry point unless `--session` is explicitly passed. The new
  `myagen` CLI must keep parser defaults as `None` and apply one documented
  precedence chain.~~ **Resolved:** parser defaults are `None` and the resolver
  tests CLI > env > project > user > default.
- ~~**Dynamic provider switch drift:** interactive `/provider` creates one
  concrete provider rather than the configured `ProviderRuntime`, and does not
  rebuild the context manager. Fallback behavior and context limits can
  therefore remain tied to the previous provider.~~ **Resolved:** the REPL switch
  rebuilds ProviderRuntime and ContextManager and closes the old provider.
- ~~**Persistent clear/list semantics:** `SessionManager.list_sessions()` only
  reports in-process handles. `clear_session()` is a no-op for a persisted
  session that has not been instantiated since restart, and `delete_session()`
  removes only the handle, not SQLite rows.~~ **Resolved:** session commands use
  `SQLiteSessionStore` directly across restarts.
- ~~**MCP stdio lifecycle gaps:** `tools/list` has no manager-level timeout, stderr
  is piped but not drained, and the subprocess is not started/terminated as a
  process group. A noisy or child-spawning server can hang startup or leave
  descendants behind.~~ **Resolved:** list timeout, stderr drain, new process
  session and process-group termination are implemented.
- ~~**MCP HTTP/config mismatch:** `.env.example` shows an
  `Authorization: Bearer ${TOKEN}` header, but config loading does not expand
  `${...}`. The literal value would be sent. Streamable HTTP session negotiation
  and `notifications/initialized` are also not implemented, so interoperability
  needs real-server tests.~~ **Resolved:** managed secret references replace
  interpolation, HTTP session IDs and initialized notification are implemented.
- ~~**Web SSRF documentation mismatch:** the web-tool module claims the connection
  is pinned to the validated IP, but the implementation validates DNS and then
  lets `httpx` resolve the hostname again. The existing DNS-rebinding/TOCTOU risk
  remains.~~ **Documentation corrected; the underlying TOCTOU risk remains.**
- ~~**Cancellation leak in summarization:** `SummarizingContextManager` shields
  the summarizer request. Cancelling the Agent await does not guarantee that the
  underlying provider request is cancelled and drained.~~ **Resolved:** the
  summarizer await is no longer shielded.
- ~~**Sensitive tool arguments in diagnostics:** tool arguments are written to
  application logs and approval prompts. Regex masking only occurs at log
  formatter output and does not protect chat-platform prompts; secret-bearing
  tool schemas need field-aware redaction.~~ **Resolved for credential-like
  fields:** callbacks, logs and CLI output use recursive redaction.
- ~~**User-visible internal errors:** CLI and Telegram can print raw exception
  text, and MCP HTTP errors include response bodies. Provider/tool/server error
  strings can contain operational details or credentials not matched by the
  current regex set.~~ **Resolved at shipped CLI/chat and MCP HTTP boundaries:**
  user output now reports stable categories/types without remote bodies.
- **Filesystem race window:** safe-root containment is checked before the later
  file operation. A local attacker able to swap symlinks concurrently may race
  the check; descriptor-relative operations or an isolated backend are needed
  for a stronger boundary.
- **No real Docker isolation:** `DockerExecutionBackend` remains an intentional
  loud-fail scaffold. Selecting it does not provide a usable sandbox.

### Deferred to a future isolation phase (Phase 10 candidate)

The following items are known design constraints, not defects in shipped
Phase 0–9 code. They are tracked here so a dedicated isolation-backend phase
can pick them up:

- Real Docker (or equivalent) execution backend replacing the loud-fail scaffold.
- Connection-pinned web fetch to close the DNS-validated → `httpx`-redialed
  TOCTOU window that today's `WebFetchTool` cannot fully eliminate.
- Descriptor-relative file operations to close the safe-root symlink race that
  the current path-check-then-open flow leaves open.
- Forcible cancellation of synchronous worker-thread tools (requires an out-of-
  process boundary; asyncio cancellation alone is insufficient).
- Full MCP protocol-revision negotiation (parsing the server's advertised
  `protocolVersion` and adjusting per-revision headers/session rules).
  The current transports advertise `2024-11-05` by default; operators can point
  at another revision via the `MCP_PROTOCOL_VERSION` environment variable, but
  automatic negotiation and revision-specific transport behavior still need a
  dedicated interoperability effort.

---

## Phase 0 — Baseline, versions, release alignment

- ~~`README.md`의 Phase 0-5 "구현 완료" 체크리스트는 마스터 시행안의
  Phase 번호 체계와 다른 옛 로드맵을 지칭함.~~ **2026-08-31:** Korean
  README rewritten against the actual Phase 0–8 implementation and acceptance
  gaps. **2026-09-01:** `README_EN.md` now carries the same Phase 0–8 status
  table, closing this item.
- `SecretMaskingFormatter` 등 로거 재설계는 Phase 4에서 다시 다룰 여지가
  있음. 현재는 정규식 기반 라이브 masking만 검증됨.
- `Agent.run_with_trace`의 `on_agent_error` 중복 dispatch, task 취소 부재
  등은 그대로 남아 있음 — Phase 1의 대상이며 baseline eval에는 아직
  회귀 테스트가 없음. _(→ Phase 1에서 해소)_

## Phase 1 — Agent run-loop state machine

Dedicated Phase 1 report was not captured in a standalone session log
(work landed as part of the aggregated revision-instructions commit).
Residual risks documented in `docs/architecture.md`:

- Synchronous tool functions already running in worker threads cannot be
  forcibly stopped by asyncio cancellation. Callers should keep
  side-effecting sync tools short-lived or implement them as
  cancellation-aware async tools.

## Phase 2 — Provider runtime, retry, and fallback

Dedicated Phase 2 report was not captured in a standalone session log.
Residual risks implied by `docs/architecture.md` and the fallback design:

- Provider capability metadata (`ModelMetadata`) is only applied when the
  caller registers the model in Settings — unknown models fall back to
  provider defaults, which may miss newer context windows or tool-calling
  toggles until an explicit override is added.
- The ordered fallback chain runs at most once per generation call and
  never restarts the Agent, so a fallback that succeeds after the primary
  emitted a partial `tool_calls` payload cannot be resumed mid-turn — the
  Agent surfaces the primary failure instead.

## Phase 3 — Tool contract, toolsets, and policy layer

- 인자 타입 매칭이 Pydantic `BaseModel` 이외에는 `jsonschema` 없이 자체
  매칭 — 복잡한 유니온/제네릭 케이스는 여전히 loose. 필요 시 Phase 5에서
  강화.
- ~~`DefaultToolPolicy`는 platform-preset 기반 destructive 차단만 제공.
  Phase 4에서 approval service와 결합해 정교화 필요. **2026-08-31 재검증:**
  `ApprovalService` 구현체와 factory는 추가됐지만 `DefaultToolPolicy` 또는
  `ToolExecutor`에는 연결되지 않았으므로 이 위험은 해소되지 않음.~~
  **Phase 9.0:** `ToolExecutor`가 confirmation 결과를 argument-bound
  `ApprovalService` record로 기록하며 빈 handler는 거부한다.

## Phase 4 — Security boundary and Execution Backend

- Docker 백엔드는 스텁이므로 실제 격리는 아직 없음 (의도적,
  `NotImplementedError`로 loud-fail). _(현재도 동일 — Phase 5의 built-in
  도구는 사실상 local backend 전용)_
- `ApprovalService`는 인메모리 저장소이므로 프로세스 재시작 시 승인
  상태가 유실됨 — 지속화가 필요하면 Phase 7 세션 스토어와 통합 필요.
- `LocalExecutionBackend`는 정의만 되어 있고 아직 어떤 도구도 이를 통해
  실행하지 않음 (Phase 5의 실제 file/terminal/web 도구와 함께 연결
  예정 — Phase 4는 경계 완성이 목표). _(→ Phase 5에서 해소)_

## Phase 5 — Real built-in tools (file / terminal / web)

- `apply_patch`는 unified-diff 다중 hunk가 아닌 단일 find/replace 방식이라
  대규모 리팩터에는 여러 번 호출이 필요하다.
- 웹 도구는 SNI/IP pinning까지는 하지 않아 TOCTOU 이론적 위험이 남아있다
  (요청 시점 DNS 재해석). Phase 6 MCP HTTP transport에서 커스텀 transport
  로 IP 강제 pinning 검토 여지.
- Docker backend는 여전히 stub이라 built-in tool은 사실상 local backend
  전용.

## Phase 6 — MCP (Model Context Protocol) integration

- 실제 상용 MCP 서버(Claude Desktop 등)와의 상호운용은 별도 통합 테스트
  필요 — 프로토콜 버전 `2024-11-05` 하드코딩.
- HTTP 트랜스포트는 최신 Streamable HTTP만 지원 — legacy HTTP+SSE 미지원.
- 공식 MCP SDK를 lockfile에 고정하지 않았음(자체 JSON-RPC 구현). 필요 시
  후속 작업에서 SDK 어댑터 추가 가능.
- Notification 수신 처리 미구현(현재 무시). 향후
  `notifications/tools/list_changed` 등 처리 시 재연결 로직 확장 필요.

## Phase 7 — Persistent session store + HITL

Dedicated Phase 7 report was not captured in a standalone session log.
Residual risks flagged in `docs/architecture.md` "known gaps":

- ~~SQLite schema is unversioned — there is no migration harness for
  breaking schema changes yet.~~ **Phase 9.5:** schema migration/version table,
  busy timeout and transactional writes added.
- ~~No FTS/index for full-text search over historical sessions; the CLI has
  no session browse / resume UI.~~ **Phase 9.5:** FTS5 and persisted
  list/show/search/resume/clear/delete added.
- ~~HITL approval integrations exist for CLI, Discord, and Telegram, but the
  programmatic/default Agent path has no fail-closed handler. When the callback
  list is empty, `_confirm()` returns `True`; silent auto-approval is therefore
  the effective default outside the three wired adapters. There is no
  `AutoApproveHandler` class involved.~~ **Phase 9.0:** explicit override is
  required; empty/base handlers fail closed.

## Phase 8 — Context engine and compression

- `approximate_token_count` 4-char/token 휴리스틱은 실제 tokenizer보다
  과/과소 추정될 수 있음 — `TokenCounter` 주입으로 대체 가능.
- `SummarizingContextManager`는 요약 자체에 LLM 호출을 하므로 비용/지연이
  증가 — 기본 전략은 여전히 trimming.
- `_OPENAI_CONTEXT_WINDOWS` / `_ANTHROPIC_CONTEXT_WINDOWS` 테이블은 신모델을
  별도로 추가해야 함(`MODEL_METADATA` env 오버라이드로 우회 가능).

---

## Cross-cutting themes

Patterns that recur across multiple phases and are worth a dedicated
follow-up rather than another patch:

- **Docker backend is a stub.** Flagged in Phase 4 and Phase 5. Anything
  that assumes container isolation today runs on the host under
  `LocalExecutionBackend`.
- **Ephemeral operational state.** `ApprovalService` records are intentionally
  per-process/per-call; retry backoff and MCP reconnection state also reset on
  restart. Persistent sessions themselves now survive restarts.
- **Model / provider capability metadata drifts.** Phases 2 and 8 both
  depend on accurate per-model tables (context window, tool-calling,
  vision). New provider releases require explicit `MODEL_METADATA`
  overrides until the built-in tables are updated.
- **Web / network boundary hardening is best-effort.** SSRF defense
  (Phase 5) blocks the well-known private/loopback/metadata ranges but
  does not IP-pin between DNS lookup and connect.
- **Sync tool cancellation.** Async cancellation (Phase 1) cannot
  interrupt a blocking sync tool once it is already running on the thread
  pool.

## How to update this document

- When a future change closes a risk, strike it through (`~~...~~`) and
  add a short "resolved by …" note rather than deleting it — the history
  is more useful than a clean slate.
- When a new risk is discovered mid-phase, append it under that phase's
  heading with the date and the commit that introduced it.
- Keep the phase order in sync with `docs/master_plan.md`.

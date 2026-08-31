# Remaining Risks Register — master_plan Phases 0–8

Consolidated **"남은 위험"** section from every Phase completion report
recorded across prior work sessions. Each item is the risk exactly as it
was flagged when the phase landed, so future work can decide whether it
still applies, has been superseded by a later phase, or needs a dedicated
follow-up.

Verify each risk against current code before acting — some were mitigated
by subsequent phases (noted inline where applicable).

---

## Phase 0 — Baseline, versions, release alignment

- `README.md`의 Phase 0-5 "구현 완료" 체크리스트는 마스터 시행안의 Phase
  번호 체계와 다른 옛 로드맵을 지칭함(실제 코드 상태와 모순되지는 않음).
  Phase 1 진입 시 라벨 리네이밍이 필요할 수 있음.
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
- `DefaultToolPolicy`는 platform-preset 기반 destructive 차단만 제공.
  Phase 4에서 approval service와 결합해 정교화 필요. _(→ Phase 4에서
  ApprovalService가 결합됨)_

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

- SQLite schema is unversioned — there is no migration harness for
  breaking schema changes yet.
- No FTS/index for full-text search over historical sessions; the CLI has
  no session browse / resume UI.
- HITL approval integrations exist for Discord and Telegram; other
  transports (CLI web, Slack, etc.) inherit `AutoApproveHandler` unless
  explicitly opted-in — silent auto-approval is the default outside the
  wired integrations.

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
- **State that does not survive a restart.** `ApprovalService` (Phase 4)
  is in-memory; retry backoff state (Phase 2) resets per process; MCP
  reconnection state (Phase 6) is not persisted.
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

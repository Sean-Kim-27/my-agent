# Phase 9 Verification Report

날짜: 2026-09-01
검증 대상: [docs/remaining_risks.md](remaining_risks.md) 의 Phase 9.0–9.6 "Resolved" 주장
검증자: 자동화 게이트 실행 + 코드베이스 직접 확인

## 1. 자동화 품질 게이트

문서에 기록된 게이트를 현재 워킹트리에서 재실행한 결과:

| 게이트 | 명령 | 결과 |
|---|---|---|
| Lint | `.venv/bin/ruff check src tests` | ✅ All checks passed |
| Type check | `.venv/bin/mypy --strict src/agent_framework` | ✅ Success: no issues found in 94 source files |
| Test suite | `.venv/bin/pytest -q` | ✅ 304 passed (문서 주장과 일치) |
| Lockfile | `uv lock --check` | ✅ Resolved 65 packages |

### 재현 시 주의사항

기본 `.venv`에 개발 도구(ruff/mypy/pytest)가 설치돼 있지 않아
`uv sync --extra dev`를 먼저 실행해야 게이트를 돌릴 수 있었다.
`docs/remaining_risks.md` 또는 [README_EN.md](../README_EN.md) 상단에
`uv sync --locked --extra dev` 가 게이트 실행의 전제임을 명시하는 것이 좋다.

## 2. "Resolved" 항목 코드 검증

문서에서 취소선(`~~...~~`)과 "**Resolved**" 라벨로 종결됐다고 표기된
Phase 9.0–9.6 항목 15건을 실제 소스에서 확인했다.

| # | 주장 항목 | 판정 | 증거 |
|---|---|---|---|
| 1 | HITL fail-closed 정책 (Phase 9.0) | ✅ CONFIRMED | [tools/executor.py:190-237](../src/agent_framework/tools/executor.py), [execution/approval.py:61](../src/agent_framework/execution/approval.py) — 빈/베이스 핸들러 거부, `ApprovalService`가 argument fingerprint와 함께 기록 |
| 2 | Fallback context budget (Phase 9.0) | ✅ CONFIRMED | [llm/runtime.py:33](../src/agent_framework/llm/runtime.py) `min()` 으로 가장 작은 known window 선택 |
| 3 | Provider client lifecycle (Phase 9.0–9.3) | ✅ CONFIRMED | [lifecycle.py:63,85,99](../src/agent_framework/lifecycle.py) 소유 SDK 클라이언트를 shutdown 시 `await provider.close()` |
| 4 | MCP lifecycle (Phase 9.3–9.4) | ✅ CONFIRMED | [lifecycle.py:57-84](../src/agent_framework/lifecycle.py), [mcp/stdio.py:71,79](../src/agent_framework/mcp/stdio.py) `ApplicationLifecycle` 내부에서 start/stop |
| 5 | Persistent sessions v2 (Phase 9.5) | ✅ CONFIRMED | [memory/sqlite_store.py:14,52,91,131](../src/agent_framework/memory/sqlite_store.py) `SQLITE_SCHEMA_VERSION=2`, migration table, FTS5, `BEGIN IMMEDIATE`; [cli/commands/session.py:28-87](../src/agent_framework/cli/commands/session.py) 가 `SQLiteSessionStore` 직접 사용 |
| 6 | Interrupted tool turns (Phase 9.5) | ✅ CONFIRMED | [memory/sqlite_store.py:119-221](../src/agent_framework/memory/sqlite_store.py) `append_messages` 원자적 배치 + `repair_incomplete_turn` 이 매칭 안 된 tool-call suffix를 `quarantined=1` 로 격리 |
| 7 | Config precedence 버그 | ✅ CONFIRMED | [cli/app.py:42-44](../src/agent_framework/cli/app.py) argparse 기본값 `None`, [config/sources.py:57-108](../src/agent_framework/config/sources.py) 가 CLI > env > project > user > default 순서로 해석 |
| 8 | `/provider` REPL 스위치 | ✅ CONFIRMED | [integrations/cli/bot.py:72-84](../src/agent_framework/integrations/cli/bot.py) 가 [lifecycle.py:88-99](../src/agent_framework/lifecycle.py) `replace_agent_provider()` 를 호출해 `ProviderRuntime`/`ContextManager` 재빌드, 이전 provider 종료 |
| 9 | MCP stdio process group | ✅ CONFIRMED | [mcp/stdio.py:71,141,151](../src/agent_framework/mcp/stdio.py) `start_new_session=os.name != "nt"`, `os.killpg(...)`; [mcp/stdio.py:79,232-242](../src/agent_framework/mcp/stdio.py) stderr drain task |
| 10 | MCP HTTP secret ref + 세션/notif | ✅ CONFIRMED | [mcp/config.py:52-54](../src/agent_framework/mcp/config.py) `header_secret_refs` (`${...}` 리터럴 아님), [mcp/http.py:43,56,111-155](../src/agent_framework/mcp/http.py) session ID 트래킹 + `notifications/initialized` |
| 11 | Summarizer 취소 (shield 제거) | ✅ CONFIRMED | [memory/context.py:305-308](../src/agent_framework/memory/context.py) `asyncio.shield` 없이 직접 await |
| 12 | 민감 인자 재귀 redaction | ✅ CONFIRMED | [logging/logger.py:43-60](../src/agent_framework/logging/logger.py) `redact_sensitive_data()` (dict/list/tuple 재귀), [tools/executor.py:250](../src/agent_framework/tools/executor.py) 콜백·로그·CLI 출력에 적용 |
| 13 | 사용자 표면 에러 (범주/타입만 노출) | ✅ CONFIRMED | [cli/app.py:404-409](../src/agent_framework/cli/app.py) `AgentFrameworkError` / generic exception 을 `type(exc).__name__` 만 노출, MCP HTTP 는 응답 바디 미노출 |
| 14 | `myagen` CLI 라우터 + alias | ✅ CONFIRMED | [pyproject.toml:39-40](../pyproject.toml) `myagen` 엔트리포인트 + deprecated `agent-framework` alias, [cli/app.py:51-125](../src/agent_framework/cli/app.py) 가 config/secret/provider/mcp/session/bot/doctor/completion/migrate-env 서브커맨드 소유 |
| 15 | README 동기화 | ✅ CONFIRMED | [README.md](../README.md) (KR) 와 [README_EN.md](../README_EN.md) 모두 Phase 0–8 상태 표를 보유 (2026-09-01 EN 반영) |

## 3. 여전히 열려 있는 위험 (문서와 실제 코드에서 재확인)

다음은 문서에도 명시돼 있고 현재 코드에서도 해소되지 않은 항목이며,
의도적으로 남긴 P2/디자인 제약이거나 상위 계층에서만 완화 가능한 것들이다.

- **Docker isolation:** [execution](../src/agent_framework/execution/) 의 Docker 백엔드는
  여전히 loud-fail 스텁 — 실제 컨테이너 격리는 제공되지 않는다.
- **Web SSRF TOCTOU:** [tools](../src/agent_framework/tools/) 의 웹 도구는 DNS 검증 후
  `httpx` 가 재해석하도록 위임되어 rebinding 창이 남아 있다. 문서 표현만 정정됨.
- **Sync 툴 취소 불가:** 워커 스레드에서 실행 중인 동기 도구는 asyncio 취소로
  강제 종료할 수 없다 ([agent](../src/agent_framework/agent/) 런루프의 알려진 제약).
- **토큰 카운팅 근사치:** `approximate_token_count` 4-char/token 휴리스틱은 실제
  tokenizer 와 오차가 있다. `TokenCounter` 주입으로만 정확도 향상 가능.
- **모델 metadata 드리프트:** 신규 provider 릴리즈는 `MODEL_METADATA` 오버라이드
  또는 내장 테이블 갱신을 요구한다.
- **Filesystem symlink race:** safe-root 검사와 실제 파일 오퍼레이션 사이 창은
  descriptor-relative API 나 격리 백엔드가 없으면 완전히 닫히지 않는다.
- **MCP 상용 서버 호환성:** 프로토콜 버전 `2024-11-05` 하드코딩. 실제 서버는
  환경별 통합 테스트가 필요하다.

## 4. 결론

- Phase 9.0–9.6 의 P0/P1 종결 주장 15건은 모두 코드/문서에서 **CONFIRMED**
  (2026-09-01 README_EN Phase 상태 표 반영으로 README 동기화 항목 종결).
- 남은 위험은 문서가 명시적으로 열어둔 P2/디자인 제약과 일치.

## 5. 후속 조치 상태 (2026-09-01)

1. ✅ [README_EN.md](../README_EN.md) 에 KR README 와 동일한 Phase 0–8 상태
   표 추가 — 15번 항목 완전 종결.
2. ✅ [docs/remaining_risks.md](remaining_risks.md) 의 Phase 9 remediation
   블록 아래에 `uv sync --locked --extra dev` 가 게이트 재현 전제임을 명시.
3. ✅ Docker isolation, Web SSRF TOCTOU, symlink race, sync-tool 강제 취소
   4건은 [docs/remaining_risks.md](remaining_risks.md) 의 "Deferred to a
   future isolation phase (Phase 10 candidate)" 섹션으로 backlog 이관.
4. (계속 열림) Section 3 의 나머지 항목 — 토큰 카운팅 근사치, `MODEL_METADATA`
   드리프트, MCP 서버 상호운용성 — 은 상위 계층 또는 외부 릴리스에 의존하는
   내재적 제약으로 유지.

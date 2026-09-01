# My-Agent

교체 가능한 LLM Provider, ReAct 실행 루프, 정책 기반 도구 실행, 메시징
어댑터, SQLite 메모리, MCP 클라이언트 구성요소, 컨텍스트 압축을 제공하는
Python 3.11+ 비동기 에이전트 프레임워크입니다.

기본 실행 명령은 `myagen`입니다. 기존 `agent-framework` 명령은 한 릴리스 동안
deprecated alias로 유지됩니다. 구현 범위와 단계별 검증은
[`docs/myagen_cli_plan.md`](docs/myagen_cli_plan.md)에 정리되어 있습니다.

> 현재 상태: Ruff, MyPy strict, 테스트 304개와 lockfile 검사는 통과합니다.
> `myagen` 설정/secret/Provider/MCP/session 명령과 공통 resource lifecycle이
> 연결되어 있습니다. 운영 도입 전에는
> [`docs/remaining_risks.md`](docs/remaining_risks.md)의 P0/P1 항목을 먼저
> 확인해야 합니다.

## 제공 기능

- OpenAI, Anthropic, NVIDIA NIM, OpenAI-compatible Provider
- API key 인증과 주입 가능한 Codex OAuth 토큰/refresh callback 어댑터
- Provider timeout, retry, `Retry-After`, ordered fallback, health check
- 실행 상태(`pending → running → completed/failed/cancelled`)와 step trace
- 함수 시그니처 기반 tool schema, 인자 검증, risk level, confirmation gate
- safe-root 기반 로컬 파일/터미널 도구와 SSRF 방어 웹 fetch 도구
- CLI REPL, Discord, Telegram 어댑터
- 인메모리 또는 SQLite 대화 메시지 저장
- stdio 및 Streamable HTTP MCP 구성요소
- tool call/result atomic trimming과 선택적 LLM 요약
- 일반 로그와 분리된 감사 로그, 정규식 기반 비밀값 마스킹

## Phase 0–8 실제 상태

마스터플랜의 체크박스는 요구사항 원문이며 현재 완료 대장이 아닙니다. 아래
표는 2026-08-31 코드 점검 결과입니다.

| Phase | 상태 | 실제 범위 |
|---|---|---|
| 0 | 완료 | 버전 단일화, uv lock, Python 3.11/3.12 CI, baseline eval |
| 1 | 완료 | run state, trace, timeout/cancellation, tool pairing |
| 2 | 완료 | provider error 정규화, retry/fallback, health 명령 |
| 3 | 완료 | tool contract, validation, policy, output/concurrency 제한 |
| 4 | 완료(제약 있음) | fail-closed HITL과 `ApprovalService`가 executor에 연결됨; Docker는 loud-fail stub |
| 5 | 완료(제약 있음) | file/terminal/web built-in 도구; 로컬 backend와 설정 플래그 필요 |
| 6 | 완료 | managed stdio/HTTP MCP가 CLI·bot lifecycle과 startup/shutdown에 연결됨 |
| 7 | 완료 | versioned SQLite, metadata, FTS, persisted session 명령, incomplete-turn quarantine |
| 8 | 완료(근사치) | trimming/summarizing 연결, fallback 최소 context window 적용; 토큰 계산은 휴리스틱 |

세부 근거와 우선순위는
[`docs/remaining_risks.md`](docs/remaining_risks.md)를 참고하세요.

## 빠른 시작

### 1. 설치

권장 개발 환경은 [uv](https://docs.astral.sh/uv/)와 lockfile을 사용합니다.

```bash
uv sync --locked --extra dev
```

```bash
uv run myagen config init
uv run myagen provider use openai
uv run myagen model set openai gpt-4o-mini
uv run myagen auth set openai
```

기존 `.env`는 한 번의 호환 기간 동안 읽을 수 있으며 다음 명령으로 안전하게
이관할 수 있습니다. 원본 파일은 수정하거나 삭제하지 않습니다.

```bash
uv run myagen config migrate-env .env --dry-run
uv run myagen config migrate-env .env
```

`.env`는 Git에 커밋하지 마세요. `.gitignore`에는 `.env`와 주요 credential
파일 패턴이 포함되어 있습니다.

### 2. 설정 확인

```bash
uv run myagen doctor
uv run myagen provider list
uv run myagen provider check --all
```

`--check`는 실제 Provider endpoint를 호출합니다. Anthropic health check는
최소 generation 요청을 사용하므로 비용 또는 rate limit이 발생할 수 있습니다.

### 3. 대화형 CLI

```bash
uv run myagen
uv run myagen chat --provider anthropic --model claude-3-5-sonnet-20241022
uv run myagen ask "현재 저장소를 요약해줘"
printf '%s\n' '테스트 결과를 요약해줘' | uv run myagen ask --stdin --json
```

REPL 명령:

```text
/help
/clear
/history
/tools
/session <id>
/provider <id>
/info
/exit
```

`/provider`는 ProviderRuntime과 ContextManager를 함께 재구성하고 기존 SDK client를
정리합니다.

### 4. Discord / Telegram

```bash
uv run myagen bot discord start
uv run myagen bot telegram start
```

각 bot token과 allowlist/mention 설정은 `.env.example`을 참고하세요. CLI,
Discord, Telegram 어댑터는 high-risk tool confirmation UI를 제공합니다.
프로그램에서 `Agent`를 직접 생성하는 경로도 confirmation handler가 없으면
`HIGH`/`DESTRUCTIVE` 도구를 fail-closed로 거부합니다.

## 설정 영역

전체 키와 기본값은 `myagen config list --source`, [`.env.example`](.env.example)과
[`Settings`](src/agent_framework/config/settings.py)에 있습니다.

### 영속 메모리

```bash
uv run myagen config set memory.backend sqlite
uv run myagen config set memory.sqlite_path ./agent_memory.db
uv run myagen session list
uv run myagen session search "검색어"
uv run myagen session resume cli:work
```

SQLite는 schema migration, metadata, FTS5 검색, 재시작 후 list/search/resume,
확인 기반 clear/delete를 지원합니다. 중단된 과거 tool turn은 자동 quarantine됩니다.

### Built-in 도구

기본값은 비활성·읽기 중심·subprocess 금지입니다.

```env
ENABLE_BUILTIN_TOOLS=true
EXECUTION_SAFE_ROOT=/absolute/path/to/workspace
EXECUTION_ALLOW_WRITES=false
EXECUTION_ALLOW_DESTRUCTIVE=false
EXECUTION_ALLOW_SUBPROCESS=false
EXECUTION_ENV_ALLOWLIST=[]
```

파일 write와 terminal을 허용하려면 해당 플래그를 명시적으로 켜야 합니다.
Docker backend는 아직 `NotImplementedError`를 내는 scaffold이므로 실제 격리
수단으로 사용할 수 없습니다.

### Context engine

```env
CONTEXT_MANAGER_ENABLED=true
CONTEXT_STRATEGY=trimming
CONTEXT_HEADROOM_RATIO=0.2
# CONTEXT_MAX_TOKENS=32000
# CONTEXT_SUMMARY_MAX_TOKENS=512
```

- `trimming`: 오래된 atomic message group을 제거합니다.
- `summarizing`: 중간 대화를 LLM으로 요약하고 실패하면 trimming으로
  fallback합니다.

현재 토큰 계산은 기본적으로 4 chars/token 근사치입니다. fallback Provider들의
context window가 다르면 예산 계산 위험이 있으므로 같은 window 계열을 사용하거나
`MODEL_METADATA`와 `CONTEXT_MAX_TOKENS`를 보수적으로 설정하세요.

### MCP

MCP config model, stdio/Streamable HTTP transport, discovery, namespace,
allow/deny filter와 tool proxy가 공통 application lifecycle에 연결됩니다.

```bash
uv run myagen mcp add notes --stdio -- node servers/notes.js
uv run myagen mcp add remote --http https://example.test/mcp \
  --header-secret Authorization=mcp/remote/token
uv run myagen mcp list
uv run myagen mcp test --all
```

stdio argv는 shell string으로 합치지 않으며, HTTP header/extra-env 비밀값은 TOML에
값 대신 secret reference만 저장됩니다.

## Python API 예시

```python
import asyncio

from agent_framework import Agent, ToolRegistry, create_llm_provider


registry = ToolRegistry()


@registry.tool(description="두 정수를 곱합니다.")
def multiply(a: int, b: int) -> int:
    return a * b


async def main() -> None:
    provider = create_llm_provider()
    agent = Agent(provider=provider, tool_registry=registry)
    result = await agent.run_with_trace("15 곱하기 24는?")
    print(result.content)
    print(result.run_id, result.state, result.total_steps)


asyncio.run(main())
```

이 예시는 현재 환경 설정에서 선택된 Provider credential이 준비되어 있어야 합니다.
`SAFE`/`LOW`가 아닌 도구를 직접 등록할 때는 반드시 fail-closed confirmation
handler를 제공하세요.

## 구조

```text
src/agent_framework/
├── agent/          # run state machine, callbacks
├── auth/           # API key / OAuth token adapter
├── config/         # pydantic-settings
├── execution/      # local boundary, approval model, Docker scaffold
├── integrations/   # CLI, Discord, Telegram
├── llm/            # providers, retry, fallback runtime
├── logging/        # app/audit logging and masking
├── mcp/            # config, stdio/HTTP transports, manager
├── memory/         # in-memory, SQLite, context managers
├── models/         # shared Pydantic contracts
└── tools/          # registry, schema, policy, executor, built-ins
```

의존성 방향과 runtime flow는
[`docs/architecture.md`](docs/architecture.md)에 설명되어 있습니다.

## 검증

```bash
.venv/bin/ruff check src tests
.venv/bin/mypy --strict src/agent_framework
.venv/bin/pytest -q
uv lock --check
```

2026-08-31 기준 결과:

```text
Ruff:   passed
MyPy:   passed (94 source files)
Pytest: 304 passed (294 unit + 10 eval)
Lock:   passed
```

CI는 Python 3.11과 3.12에서 같은 `uv.lock`으로 위 검사를 실행합니다.

## 문서

- [마스터플랜](docs/master_plan.md)
- [아키텍처](docs/architecture.md)
- [남은 위험 및 최종 감사](docs/remaining_risks.md)
- [`myagen` CLI·설정 전환 계획](docs/myagen_cli_plan.md)
- [변경 이력](CHANGELOG.md)

`README_EN.md`는 동일한 `myagen` 설치·설정·운영 흐름을 요약합니다.

## 라이선스

현재 저장소에는 라이선스 파일이 없습니다. 배포 또는 외부 공개 전에 사용할
라이선스를 명시해야 합니다.

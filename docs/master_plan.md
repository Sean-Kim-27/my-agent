# My-Agent 고도화 마스터 시행안 (Core & Working Agent)

## 1. 최종 목표

현재의 작고 명확한 비동기 Agent Core를 유지하면서 다음 핵심 능력을 단계적으로 추가한다.

1. 신뢰할 수 있는 Agent 실행 상태 머신
2. Provider 장애 대응과 fallback
3. 안전한 파일·터미널·웹 도구
4. MCP 연동
5. 검색·재개 가능한 영속 세션
6. 실제 토큰 기반 컨텍스트 압축

Hermes Agent를 그대로 복제하지 않는다. 현재 프로젝트의 장점인 작은 코드베이스, 명확한 의존성 역전, Async-First 구조를 유지한다.

---

## 2. 에이전트 공통 작업 규칙

### 2.1 작업 범위

- 한 번에 하나의 Phase만 구현한다.
- Phase를 건너뛰지 않는다.
- 현재 Phase와 관계없는 리팩터링을 하지 않는다.
- 다음 Phase 기능을 미리 구현하지 않는다.
- 공개 API를 변경할 경우 하위 호환 계층과 마이그레이션 문서를 제공한다.
- 사용자가 명시하지 않으면 커밋·푸시·배포하지 않는다.

### 2.2 구현 순서

각 Phase에서 반드시 다음 순서로 진행한다.

1. 관련 코드를 읽고 현재 동작을 요약한다.
2. 해당 Phase의 capability test 또는 실패 재현 테스트를 먼저 추가한다.
3. 최소 구현으로 테스트를 통과시킨다.
4. 예외·동시성·보안 경계를 보강한다.
5. 전체 회귀 테스트를 실행한다.
6. 문서와 설정 예시를 갱신한다.
7. 변경 파일, 검증 결과, 남은 위험을 보고한다.

### 2.3 필수 품질 명령

```bash
.venv/bin/ruff check src tests
.venv/bin/mypy --strict src/agent_framework
.venv/bin/pytest -q
```

가상환경이 없다면 프로젝트 표준 방식으로 설치한 뒤 동일 검사를 실행한다.

### 2.4 보안 원칙

- 모든 권한 판정은 기본 거부(fail closed)로 구현한다.
- 비밀번호, 토큰, API 키를 로그·DB·테스트 fixture에 평문으로 저장하지 않는다.
- `eval`, 무제한 shell 실행, 검증되지 않은 경로 결합을 사용하지 않는다.
- 파일 경로는 symlink 탈출과 `..` traversal을 방어한다.
- 외부 입력으로 구성되는 subprocess는 shell 문자열이 아니라 argument list를 우선 사용한다.
- 승인되지 않은 destructive action은 실행하지 않는다.

### 2.5 완료 보고 형식

```markdown
## Phase N 결과

- 구현 요약:
- 변경 파일:
- 추가 테스트:
- Ruff:
- MyPy:
- Pytest:
- 수동 검증:
- 공개 API 변경:
- 데이터 마이그레이션:
- 남은 위험:
- 다음 Phase 진입 가능 여부:
```

---

## 3. 마일스톤 및 의존성

```text
Milestone A — 신뢰 가능한 코어
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4

Milestone B — 실제로 일하는 에이전트
Phase 4 → Phase 5 → Phase 6
Phase 1 → Phase 7 → Phase 8
```

---

# Phase 0. 기준선, 버전, 릴리스 정합성

## 목표

기능 추가 전에 버전·문서·의존성·CI·평가 기준을 단일화한다.

## 수정 대상

- `pyproject.toml`
- `src/agent_framework/__init__.py`
- `README.md`
- `README_EN.md`
- `.github/workflows/ci.yml`
- `.env.example`
- 신규 `CHANGELOG.md`
- 신규 `docs/architecture.md`
- 신규 `tests/evals/`
- 신규 또는 갱신 `uv.lock`

## 구현 항목

- [ ] `pyproject.toml`의 `0.1.0`과 `__version__`의 `0.3.0` 불일치를 제거한다.
- [ ] 버전의 source of truth를 하나로 만든다.
- [ ] README의 테스트 개수와 실제 테스트 개수 불일치를 수정한다.
- [ ] README의 구현 완료 주장과 실제 bootstrap 연결 상태를 대조한다.
- [ ] `uv.lock`을 생성하고 CI에서 `uv sync --locked --extra dev`를 사용한다.
- [ ] CI가 Python 3.11과 3.12에서 동일 lockfile로 실행되게 한다.
- [ ] `agent-framework` CLI entry point를 `[project.scripts]`에 정의한다.
- [ ] 현재 아키텍처와 의존성 방향을 `docs/architecture.md`에 기록한다.
- [ ] 기본 eval 시나리오를 fixture 형태로 만든다.

## 기본 eval 시나리오

- [ ] 일반 대화 1회
- [ ] 도구 1회 호출
- [ ] 한 응답에서 도구 2개 호출
- [ ] 도구 오류 후 self-correction
- [ ] 도구 timeout
- [ ] Provider 429 후 retry
- [ ] max steps 도달
- [ ] 세션 간 메모리 격리
- [ ] SQLite 재시작 후 대화 복원
- [ ] 민감값 로그 마스킹

## 완료 조건

- 버전 문자열이 모든 위치에서 일치한다.
- README가 현재 구현을 과장하지 않는다.
- lockfile 기반 CI가 통과한다.
- 기존 118개 테스트와 새 baseline eval이 통과한다.

---

# Phase 1. Agent 실행 루프 상태 머신 보강

## 목표

`Agent.run_with_trace()`를 예측 가능하고 취소 가능하며 정확히 한 번만 이벤트를 발생시키는 실행 상태 머신으로 만든다.

## 수정 대상

- `src/agent_framework/agent/agent.py`
- `src/agent_framework/agent/events.py`
- `src/agent_framework/models/events.py`
- `src/agent_framework/models/response.py`
- `src/agent_framework/exceptions.py`
- 신규 `src/agent_framework/agent/runtime.py`
- 관련 unit tests

## 구현 항목

- [ ] `RunContext`를 추가한다.
- [ ] 실행 상태를 명시한다.
- [ ] one-off callback도 lifecycle event를 받도록 수정한다.
- [ ] 현재 중복 발생 가능한 `on_agent_error`가 정확히 한 번만 호출되게 한다.
- [ ] Provider 호출 전에 매 iteration마다 context fitting을 수행한다.
- [ ] tool result가 추가된 뒤 다음 Provider 호출 전에 다시 context budget을 확인한다.
- [ ] tool call과 tool result의 pairing이 깨지지 않도록 검증한다.
- [ ] 다중 tool call 결과의 순서를 입력 tool call 순서와 일치시킨다.
- [ ] 전체 Agent 실행 timeout과 취소를 지원한다.
- [ ] 취소 시 실행 중인 tool task를 정리한다.
- [ ] max steps 도달을 명확한 오류 또는 구조화된 종료 결과로 통일한다.
- [ ] 각 step에 token usage, latency, provider, model, 오류 정보를 기록한다.
- [ ] callback 실패는 Agent를 중단하지 않되 구조화된 경고로 남긴다.

## 완료 조건

- Agent 실행을 `run_id`로 끝까지 추적할 수 있다.
- 모든 실행은 completed, failed, cancelled 중 하나로 종료된다.
- task 또는 coroutine이 백그라운드에 누수되지 않는다.

---

# Phase 2. Provider Runtime, Retry, Fallback 보강

## 목표

Provider별 차이를 Agent Core 밖에서 정규화하고 일시적 장애에 안전하게 대응한다.

## 구현 항목

- [x] Provider capability를 호출 전 검증한다.
- [x] retry 가능한 오류와 retry 불가능한 오류를 구분한다.
- [x] HTTP `Retry-After`를 존중한다.
- [x] exponential backoff에 jitter를 적용한다.
- [x] 인증 오류와 잘못된 요청은 재시도하지 않는다.
- [x] Provider timeout을 connect/read/write/pool 수준으로 구분한다.
- [x] fallback provider 목록을 설정할 수 있게 한다.
- [x] tool side effect가 발생한 이후에는 무조건적인 전체 재실행을 금지한다.
- [x] fallback 전환 시 동일 tool call을 중복 실행하지 않는다.
- [x] Provider health check 결과를 CLI에서 확인할 수 있게 한다.
- [x] `doctor` 또는 `--providers --check` 명령을 추가한다.
- [x] 모델별 context window와 capability metadata를 설정할 수 있게 한다.
- [x] credential 값은 오류 메시지와 로그에 포함하지 않는다.

## 완료 조건

- Provider 장애가 Agent Core의 분기문 증가로 이어지지 않는다.
- fallback이 중복 side effect를 만들지 않는다.
- 모든 Provider 오류가 공통 오류 타입으로 정규화된다.

---

# Phase 3. Tool 계약, Toolset, 정책 계층

## 목표

도구를 단순 Python callable이 아니라 위험도와 실행 정책을 가진 명시적 계약으로 확장한다.

## 구현 항목

- [x] `ToolRiskLevel`을 추가한다.
- [x] `ToolDefinition`에 metadata를 추가한다 (toolset, risk level, idempotent 등).
- [x] `ToolExecutionContext`를 도입한다.
- [x] JSON Schema 또는 Pydantic으로 실제 argument validation을 수행한다.
- [x] 알 수 없는 argument, 타입 오류, 누락 필드를 실행 전에 거부한다.
- [x] registry에서 중복 이름 등록을 기본 거부한다.
- [x] namespace를 지원한다 (예: `builtin.file.read`).
- [x] toolset enable/disable 기능을 추가한다.
- [x] 플랫폼별 toolset preset을 지원한다.
- [x] tool output 크기를 제한하고 초과분은 artifact로 분리한다.
- [x] 도구별 동시 실행 제한을 지원한다.
- [x] non-idempotent tool의 자동 재시도를 금지한다.
- [x] 정책 판정과 실행을 분리한다.

## 완료 조건

- 모든 도구 호출은 실행 전 정책 결정을 거친다.
- Agent가 임의로 확인 요구 여부를 우회할 수 없다.
- 등록·정책·실행·결과 직렬화가 분리된다.

---

# Phase 4. 보안 경계와 Execution Backend

## 목표

실제 파일·터미널 도구를 추가하기 전에 실행 격리와 승인 체계를 완성한다.

## 구현 항목

- [ ] `ExecutionBackend` 인터페이스를 만든다.
- [ ] Local backend와 Docker backend를 분리한다.
- [ ] Local backend는 명시적 설정이 없으면 write/destructive 실행을 거부한다.
- [ ] safe root 밖 파일 접근을 차단한다.
- [ ] `..`, absolute path, symlink 탈출을 테스트한다.
- [ ] subprocess 환경변수는 allowlist 방식으로 전달한다.
- [ ] API 키와 토큰은 기본적으로 child process에 전달하지 않는다.
- [ ] subprocess timeout, process group 종료, stdout/stderr 제한을 구현한다.
- [ ] command approval service를 구현한다.
- [ ] 승인 상태를 pending/approved/rejected/expired로 관리한다.
- [ ] 인자가 바뀌면 기존 승인을 재사용하지 않는다.
- [ ] 보안 감사 로그는 일반 application log와 분리한다.
- [ ] 감사 로그에도 비밀값 마스킹을 적용한다.

## 완료 조건

- Phase 5의 실제 도구를 안전하게 올릴 실행 경계가 존재한다.
- 기본 설정에서 호스트 전체 파일시스템과 비밀 환경변수에 접근할 수 없다.

---

# Phase 5. 실제 Built-in Tools

## 목표

모의 도구를 넘어 실제 작업이 가능한 최소 도구 세트를 제공한다.

## 구현 항목

### 파일 도구
- [ ] `list_directory`, `read_file`, `write_file`, `apply_patch` 등.
- [ ] 모든 write 도구에 safe root와 승인 정책을 적용한다.
- [ ] 파일 크기와 binary 파일 처리를 제한한다.

### 터미널 도구
- [ ] argument list 기반 command 실행
- [ ] working directory 검증 및 stdout/stderr 분리
- [ ] timeout, exit code, process terminate 처리

### 웹 도구
- [ ] HTTP fetch 인터페이스 (connect/read timeout, response size 제한)
- [ ] private IP와 metadata endpoint를 막는 SSRF 방어
- [ ] HTML text extraction

## 완료 조건

- CLI에서 실제 저장소 읽기·검색·수정·테스트 실행이 가능하다.

---

# Phase 6. MCP 통합

## 목표

외부 도구와 서비스를 네이티브 코드를 추가하지 않고 연결한다.

## 구현 항목

- [ ] 공식 MCP SDK를 lockfile에 고정한다.
- [ ] stdio 및 Streamable HTTP transport를 지원한다.
- [ ] MCP server별 namespace를 적용한다.
- [ ] discovery 결과를 `ToolDefinition`으로 변환한다.
- [ ] server별 allowlist/denylist를 지원한다.
- [ ] MCP subprocess 환경변수도 allowlist 방식으로 전달한다.
- [ ] connect, initialize, call timeout을 분리한다.
- [ ] disconnect와 Agent shutdown 시 subprocess를 정리한다.
- [ ] 재연결 시 중복 tool registration을 방지한다.
- [ ] MCP tool에도 기존 risk/approval policy를 적용한다.

## 완료 조건

- MCP 도구가 Built-in Tool과 동일한 정책 경로를 사용한다.
- MCP server 장애가 전체 Agent를 중단시키지 않는다.

---

# Phase 7. 영속 Session Store와 검색

## 목표

단순 메시지 저장을 넘어 세션 조회·재개·검색·실행 이력을 제공한다.

## 구현 항목

- [ ] 현재 `conversation_messages` 스키마를 versioned migration으로 전환한다.
- [ ] session metadata를 저장한다 (title, platform, actor 등).
- [ ] SQLite WAL, busy timeout, transaction 경계를 명시한다.
- [ ] FTS5 기반 메시지 검색을 추가한다.
- [ ] session list/resume/delete를 지원한다.
- [ ] 삭제는 soft delete 또는 명시적 확인을 사용한다.
- [ ] CLI 명령을 추가한다 (`/sessions`, `/resume`, `/search` 등).

## 완료 조건

- 프로세스를 재시작해도 세션 목록과 실행 이력을 조회할 수 있다.
- 과거 대화를 텍스트 검색하고 해당 세션을 재개할 수 있다.

---

# Phase 8. Context Engine과 압축

## 목표

현재의 문자 수 기반 trimming을 실제 provider context budget 기반 관리로 교체한다.

## 구현 항목

- [ ] `ContextManager`를 bootstrap에 실제 연결한다.
- [ ] 매 LLM 호출 직전에 context를 계산한다.
- [ ] provider/model별 context window를 적용한다.
- [ ] 시스템 메시지와 최근 유저 메시지를 보존한다.
- [ ] assistant tool call과 tool result를 하나의 atomic group으로 취급한다.
- [ ] 중간 대화를 요약하는 compression strategy를 추가한다.
- [ ] summary 생성 실패 시 안전한 trimming으로 fallback한다.
- [ ] 단일 user/tool message가 너무 클 경우 명확한 오류로 처리한다.

## 완료 조건

- 긴 세션에서 context overflow 없이 동작한다.
- tool call/result가 trimming으로 분리되지 않는다.
- 압축으로 인해 현재 요청이 제거되지 않는다.

---

## 4. 마일스톤별 Go/No-Go 조건

### Milestone A: 신뢰 가능한 코어 (Phase 0~4)

- **진입 조건:** 기존 테스트 전체 통과
- **완료 조건:** Agent 상태 추적 가능, Provider 오류 정규화, Tool 정책 중앙화, 보안 경계 준비
- **No-Go:** callback 중복, task 누수, 승인 우회, safe root 탈출, secret 유출

### Milestone B: 실제로 일하는 에이전트 (Phase 5~8)

- **완료 조건:** 파일·터미널·웹 도구 사용 가능, MCP 연결 가능, 세션 검색/재개 가능, 장시간 대화에서 context overflow 없음
- **No-Go:** shell 또는 path injection, MCP orphan process, DB migration 불가능, tool call/result 손상

---

## 5. 핵심 위험 등록부

| 위험 | 초기 신호 | 완화책 | 중단 조건 |
|---|---|---|---|
| 기능 범위 폭증 | 한 Phase에서 unrelated 파일 대량 변경 | Phase별 별도 PR | 다음 Phase 기능이 섞임 |
| 보안 경계 우회 | 도구가 Policy 없이 직접 실행 | Executor 단일 진입점 | 승인 우회 발견 |
| DB 마이그레이션 실패 | 기존 DB fixture 실패 | versioned migration과 backup | 데이터 손실 가능성 |
| 컨텍스트 품질 저하 | 압축 후 답변 정확도 하락 | retention eval | baseline 대비 유의미한 회귀 |
| 동시성 장애 | task 누수, DB lock, 순서 뒤섞임 | structured concurrency | 재현 가능한 message loss |
| 문서 불일치 | README 명령 실패 | 문서 smoke test | release 문서 재현 실패 |
| Provider 종속 | Core에 Provider 분기 증가 | runtime adapter와 capability | Provider 추가 시 Core 수정 필요 |

---

## 6. 개별 Phase 실행용 프롬프트 템플릿

아래 템플릿에서 `{PHASE_NUMBER}`와 `{PHASE_TITLE}`만 바꿔 사용한다.

```text
My-Agent 고도화 마스터 시행안의 Phase {PHASE_NUMBER}: {PHASE_TITLE}만 구현해 줘.

규칙:
1. 다른 Phase 기능은 구현하지 마.
2. 먼저 현재 코드와 관련 테스트를 읽고 현재 동작, 결함, 변경 범위를 요약해.
3. capability test 또는 실패 재현 테스트를 먼저 추가해.
4. 공개 API를 변경하면 하위 호환성과 migration을 제공해.
5. 보안 판정은 fail closed로 구현해.
6. 기존 사용자 변경을 보존하고 관련 없는 파일을 수정하지 마.
7. 완료 후 아래 명령을 실행해:
   - .venv/bin/ruff check src tests
   - .venv/bin/mypy --strict src/agent_framework
   - .venv/bin/pytest -q
8. 테스트 실패를 숨기거나 skip으로 우회하지 마.
9. README, 설정 예시, architecture 문서를 실제 구현에 맞게 갱신해.
10. 커밋이나 푸시는 내가 별도로 요청할 때만 해.

최종 보고에 반드시 포함할 것:
- 구현한 기능
- 수정한 파일
- 추가한 테스트
- Ruff/MyPy/Pytest 결과
- 수정한 파일
- 공개 API 및 DB migration 영향
- 남은 위험
- 다음 Phase 진행 가능 여부
```

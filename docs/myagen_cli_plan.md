# `myagen` CLI 및 명령 기반 설정 전환 계획

## 1. 목표

현재의 `agent-framework` 단일 argparse 진입점과 `.env` 복사 workflow를 다음
형태로 전환한다.

```bash
myagen
myagen ask "이 저장소를 분석해줘"
myagen config init
myagen provider configure openai
myagen auth set openai
myagen doctor
```

완료 후 신규 사용자는 `.env.example`을 복사하거나 Python 모듈 경로를 알 필요가
없어야 한다. 설정, credential, Provider, MCP, 세션, bot 실행을 모두 `myagen`
하위 명령으로 관리한다.

이 문서는 구현 계획과 완료 대장을 겸한다. 2026-08-31 기준 위 명령은 제공되며,
기존 `agent-framework`는 한 릴리스 동안 deprecated alias로 유지된다.

### 구현 상태

| Phase | 상태 | 검증 요약 |
|---|---|---|
| 9.0 | 완료 | 빈 handler fail-closed, ApprovalService executor 연결, 최소 fallback window, owned SDK/MCP close, atomic tool turn |
| 9.1 | 완료 | `myagen` entry point, argparse router, legacy alias, version/doctor/help/usage smoke |
| 9.2 | 완료 | user/project TOML, precedence/source, atomic lock/write, OS keyring abstraction, config/auth 명령, 64-field mapping gate |
| 9.3 | 완료 | chat/ask/provider/model/tools, Provider+Context 동시 rebuild, 공통 lifecycle 정상/실패 정리 |
| 9.4 | 완료 | managed MCP와 secret reference, bot 명령, 실제 local stdio/Streamable HTTP connect·list·call·shutdown 테스트 |
| 9.5 | 완료 | SQLite schema v2, metadata/FTS5, persisted session 명령, incomplete-turn quarantine |
| 9.6 | 완료 | `.env` dry-run/migration, import/export, completion, 한·영 README, packaging/alias smoke |

남은 제약은 [`remaining_risks.md`](remaining_risks.md)의 Phase 9 remediation
update에 기록한다. Docker backend, DNS connection pinning, sync worker 강제 취소,
실제 tokenizer/model metadata drift는 이번 CLI 전환 범위 밖의 후속 항목이다.

## 2. 시작 전 필수 선행 수정

새 CLI가 unattended/one-shot 실행을 쉽게 만들기 때문에 다음 항목을 먼저 해결하지
않으면 공격 면만 넓어진다.

1. confirmation handler가 없을 때 `HIGH`/`DESTRUCTIVE` 도구를 거부하도록
   fail-closed 기본값을 적용한다.
2. `ApprovalService`를 실제 policy/executor 경로에 연결하거나, 중복 개념을
   제거하고 callback approval 하나로 일관되게 만든다.
3. heterogeneous fallback chain의 context 예산을 primary보다 크게 잡지 않게 한다.
4. SDK client를 소유권에 따라 cache/close하고 공통 application lifecycle을 만든다.
5. MCP startup 실패와 정상 종료 모두에서 transport/process를 정리할 수 있게 한다.

이 다섯 항목은 Phase 9 진입 Go/No-Go gate로 둔다.

## 3. CLI 계약

### 3.1 최상위 명령

| 명령 | 역할 |
|---|---|
| `myagen` / `myagen chat` | 기본 interactive chat 시작 |
| `myagen ask <prompt>` | 한 번 실행하고 stdout으로 답변 출력 |
| `myagen doctor` | 설정, credential 존재, DB, MCP, safe-root 점검 |
| `myagen version` | CLI/package/config schema 버전 출력 |
| `myagen completion <shell>` | bash/zsh/fish completion 출력/설치 안내 |

`ask`는 automation 친화적으로 stdin도 받아야 한다.

```bash
printf '%s\n' '테스트를 요약해줘' | myagen ask --stdin
myagen ask --session work --json "현재 상태는?"
```

### 3.2 설정과 인증

```text
myagen config init [--scope user|project]
myagen config path [--scope user|project|effective]
myagen config list [--source] [--show-secrets=false]
myagen config get <key>
myagen config set <key> [value]
myagen config unset <key>
myagen config validate
myagen config import <path> [--dry-run]
myagen config export <path> [--include-secrets=false]
myagen config migrate-env [path] [--dry-run]

myagen auth set <provider>          # getpass prompt; argv에 secret 금지
myagen auth set <provider> --stdin  # CI/pipe용
myagen auth status [provider]
myagen auth logout <provider>
myagen auth login codex             # 공식 interactive flow가 구현된 뒤에만 노출
```

`config set`이 secret field를 받으면 일반 TOML에 쓰지 않고 `auth set`과 같은
secret backend로 라우팅한다. 값이 명령행 인자로 전달되면 shell history와 process
list에 남으므로 기본 거부한다. `config list/get/export`는 secret을 항상 마스킹하고,
`--show-secrets` 같은 우회 옵션은 만들지 않는다.

### 3.3 Provider와 모델

```text
myagen provider list
myagen provider use <name>
myagen provider configure <name>
myagen provider show <name>
myagen provider check [name|--all]
myagen provider fallback list
myagen provider fallback add <name>
myagen provider fallback remove <name>
myagen provider fallback reorder <name>...
myagen model set <provider> <model>
myagen model metadata set <provider:model> <key> <value>
```

`provider use/configure` 후에는 ProviderRuntime과 ContextManager를 같은 factory에서
새로 만들어 `/provider`의 현재 drift를 제거한다.

### 3.4 도구, MCP, 세션, integration

```text
myagen tools list [--enabled|--all]
myagen tools enable <toolset>
myagen tools disable <toolset>
myagen tools permissions

myagen mcp list
myagen mcp add <name> --stdio -- <argv...>
myagen mcp add <name> --http <url>
myagen mcp show <name>
myagen mcp enable|disable|remove <name>
myagen mcp test [name|--all]

myagen session list
myagen session show <id>
myagen session resume <id>
myagen session search <query>
myagen session clear <id> --confirm
myagen session delete <id> --confirm

myagen bot discord start
myagen bot telegram start
```

MCP command argv는 `--` 뒤 argument list로만 받는다. HTTP header secret은
`myagen auth` secret reference로 저장하고 `${TOKEN}` 문자열 치환에 의존하지 않는다.
세션 명령은 versioned migration, metadata와 FTS가 구현되기 전에는 노출하지 않는다.

## 4. 설정 저장 설계

### 4.1 저장 위치

`platformdirs`를 사용해 OS별 표준 위치를 선택한다.

| 종류 | macOS 예시 | 내용 |
|---|---|---|
| User config | `~/Library/Application Support/myagen/config.toml` | 비밀값이 아닌 사용자 기본 설정 |
| Project config | `<repo>/.myagen/config.toml` | 저장소별 override; commit 가능 여부는 사용자 선택 |
| Secrets | macOS Keychain/Windows Credential Manager/Linux Secret Service | API key, bot token, OAuth token |
| Data | `~/Library/Application Support/myagen/data/` | SQLite session DB, migration metadata |
| Cache | `~/Library/Caches/myagen/` | provider metadata 등 재생성 가능 데이터 |

Secret backend는 Python `keyring`을 기본으로 한다. headless Linux에서 secure backend가
없으면 명확히 실패하고, 사용자가 명시적으로 선택한 경우에만 권한 `0600`의 encrypted
또는 local credential file fallback을 허용한다. 평문 TOML fallback은 제공하지 않는다.

### 4.2 우선순위

effective 설정은 아래 순서로 계산한다.

```text
CLI flag
  > process environment (CI/legacy compatibility)
  > project config
  > user config
  > Settings default
```

- argparse option의 기본값은 모두 `None`으로 두어 하위 source를 가리지 않게 한다.
- `DEFAULT_SESSION_ID`가 현재 parser default에 가려지는 회귀를 테스트로 고정한다.
- `myagen config list --source`는 각 값이 어느 layer에서 왔는지 표시한다.
- legacy `.env` 자동 로드는 한 번의 deprecation 기간 동안 opt-in으로만 유지한다.

### 4.3 schema와 파일 안정성

```toml
schema_version = 1

[agent]
provider = "openai"
default_session = "cli:default"
max_steps = 10

[providers.openai]
model = "gpt-4o-mini"
base_url = "https://api.openai.com/v1"

[memory]
backend = "sqlite"

[execution]
safe_root = "/absolute/path"
allow_writes = false
allow_subprocess = false
```

- Pydantic model을 TOML schema의 단일 source of truth로 사용한다.
- write는 temp file + fsync + atomic replace로 처리한다.
- user config/credential fallback은 소유자 전용 권한을 검증한다.
- unknown key, 잘못된 enum, 음수 timeout은 저장 전에 거부한다.
- schema migration은 version별 forward migration과 backup을 제공한다.
- 동시에 실행된 `config set` 충돌을 막기 위해 file lock을 사용한다.

### 4.4 모든 기존 환경변수의 이관 보장

`Settings.model_fields`의 모든 항목을 다음 중 하나로 분류하는 mapping registry를 둔다.

1. 일반 config key
2. secret key
3. runtime-only flag
4. deprecated/removed key와 replacement

테스트는 mapping되지 않은 `Settings` field가 하나라도 추가되면 실패해야 한다. 이로써
`.env.example`의 일부만 CLI로 옮겨지고 나머지가 빠지는 문제를 방지한다.

대표 mapping:

| 기존 env | 새 config/secret |
|---|---|
| `LLM_PROVIDER` | `agent.provider` |
| `DEFAULT_SESSION_ID` | `agent.default_session` |
| `OPENAI_MODEL` | `providers.openai.model` |
| `OPENAI_API_KEY` | secret `provider/openai/api-key` |
| `FALLBACK_PROVIDERS` | `agent.fallback_providers` |
| `EXECUTION_*` | `execution.*` |
| `ENABLE_BUILTIN_TOOLS`, `BUILTIN_TOOLS_*` | `tools.builtin.*` |
| `ENABLE_MCP`, `MCP_CONFIG_PATH` | `mcp.*` + managed server records |
| `MEMORY_*`, `SQLITE_MEMORY_PATH` | `memory.*` |
| `CONTEXT_*` | `context.*` |
| `DISCORD_BOT_TOKEN`, `TELEGRAM_BOT_TOKEN` | integration secret records |
| 나머지 Discord/Telegram key | `integrations.discord.*`, `integrations.telegram.*` |

## 5. 내부 구조 변경

예상 파일 구조:

```text
src/agent_framework/
├── cli/
│   ├── app.py              # parser와 최상위 dispatch
│   ├── exit_codes.py
│   ├── output.py           # text/json, stdout/stderr contract
│   └── commands/
│       ├── ask.py
│       ├── auth.py
│       ├── config.py
│       ├── doctor.py
│       ├── mcp.py
│       ├── provider.py
│       ├── session.py
│       └── tools.py
├── config/
│   ├── settings.py         # effective runtime model
│   ├── schema.py           # versioned TOML model
│   ├── sources.py          # precedence merge
│   ├── store.py            # atomic TOML I/O + lock
│   ├── secrets.py          # keyring abstraction
│   └── migration.py
└── lifecycle.py            # provider/MCP/client startup and shutdown ownership
```

기존 `integrations/cli/bot.py`는 REPL UI만 유지하고, parser와 operational command는
새 `cli/` package로 옮긴다. 우선 argparse subparser로 구현해 새 runtime dependency를
늘리지 않는다. 명령 규모가 실제로 argparse 유지보수 한계를 넘을 때만 Typer/Click을
별도 ADR로 검토한다.

## 6. 단계별 시행안

### Phase 9.0 — Safety prerequisite

- fail-closed confirmation과 ApprovalService 결합/정리
- fallback context 예산 수정
- Provider/MCP owned-resource close protocol
- interrupted tool turn recovery 정책 설계 및 capability test

완료 조건: unattended `ask`가 승인 없이 high-risk tool을 실행할 수 없다.

### Phase 9.1 — Command skeleton과 호환 alias

- `[project.scripts]`에 `myagen = "agent_framework.cli.app:main"` 추가
- `argparse` subcommand router, 공통 output/exit-code contract 구현
- bare `myagen`을 `myagen chat`으로 연결
- 기존 `agent-framework`는 같은 router를 가리키는 deprecated alias로 한 release 유지
- `--help`, `version`, `doctor` smoke test 추가

완료 조건: 설치 후 어느 디렉터리에서든 `myagen --help`가 실행되고, 잘못된 명령은
usage를 stderr로 출력하며 non-zero로 종료한다.

### Phase 9.2 — Config/secret store

- user/project TOML, precedence merge, source 표시 구현
- keyring abstraction과 masked output 구현
- `config init/get/set/unset/list/validate/path` 구현
- `auth set/status/logout` 구현
- 모든 `Settings` field mapping coverage test 추가

완료 조건: 신규 설치가 `.env` 없이 Provider를 구성하고 재시작 후 같은 effective
설정을 읽는다. secret이 argv, stdout, config, log에 나타나지 않는다.

### Phase 9.3 — Runtime commands와 lifecycle

- `chat`, `ask`, `provider`, `model`, `tools`, `doctor` 구현
- config 변경 시 ProviderRuntime/ContextManager를 함께 재구성
- MCP bootstrap과 shutdown을 `lifecycle.py`의 `async with` 경계에 연결
- SIGINT/SIGTERM에서 Agent task, Provider client, MCP process를 순서대로 정리

완료 조건: normal path, provider failure, Ctrl+C 모두 orphan task/process 없이
종료한다.

### Phase 9.4 — MCP와 integration 관리

- managed MCP records와 `mcp add/list/show/test/remove` 구현
- header/extra-env secret reference 적용
- Discord/Telegram configure/start 명령 구현
- bot token과 allowlist를 config/secret store에서 읽도록 변경

완료 조건: 실제 stdio 서버 1개와 Streamable HTTP 서버 1개로 connect, tool call,
failure isolation, shutdown 통합 테스트가 통과한다.

### Phase 9.5 — Session completion

- SQLite versioned migration, metadata, busy timeout, transaction boundary
- FTS5, persisted list/show/search/resume/clear/delete API 구현
- incomplete tool turn 감지와 repair/quarantine 구현
- session 명령을 위 storage API에 연결

완료 조건: 프로세스 재시작 후 list → search → resume이 가능하고, clear/delete가
실제 persisted rows에 반영된다.

### Phase 9.6 — Migration과 deprecation 종료

- `config migrate-env` dry-run/import 구현
- README와 `.env.example`을 신규 CLI 중심으로 변경
- CI용 environment override 문서는 별도 유지
- deprecation 기간 후 `.env` 자동 로드와 `agent-framework` alias 제거 여부 결정
- shell completion과 packaging smoke test 추가

완료 조건: 깨끗한 machine에서 문서의 명령만으로 install → configure → doctor →
ask를 완료할 수 있다.

## 7. 출력과 exit code 계약

| Code | 의미 |
|---|---|
| 0 | 성공 |
| 2 | CLI usage/validation 오류 |
| 3 | 설정 또는 credential 누락 |
| 4 | Provider/MCP 연결 실패 |
| 5 | policy/approval 거부 |
| 6 | session/storage 오류 |
| 130 | SIGINT 취소 |

- 정상 결과와 `--json` payload는 stdout에만 출력한다.
- progress, warning, diagnostics는 stderr에 출력한다.
- `--json` schema에는 `schema_version`, `ok`, `data` 또는 `error.code/message`를 둔다.
- secret, raw stack trace, remote response body는 사용자 출력에 포함하지 않는다.
- human-readable error에는 다음 행동(`myagen auth set ...`, `myagen doctor`)을 제시한다.

## 8. 필수 테스트

각 명령마다 valid, invalid, integration edge를 최소 한 개씩 검증한다.

- parser: bare command, nested help, unknown command, quoting, Unicode
- precedence: flag/env/project/user/default 조합과 `None` parser default
- config: atomic write, concurrent writer, invalid TOML, migration rollback
- secrets: getpass/stdin, masking, keyring unavailable, shell-history 방지
- provider: configure/use/check, fallback reorder, context rebuild
- approval: no handler, reject, timeout, changed arguments, non-interactive ask
- MCP: stdio stderr flood, list timeout, child process cleanup, HTTP auth reference
- sessions: restart list/search/resume, clear/delete, incomplete tool turn
- output: stdout/stderr 분리, JSON schema snapshot, exit code
- platforms: macOS/Linux/Windows config path and permission behavior
- packaging: wheel install 후 `myagen --help`와 legacy alias smoke test

품질 gate:

```bash
ruff check src tests
mypy --strict src/agent_framework
pytest -q
uv lock --check
```

## 9. 하위 호환과 rollback

- 첫 release에서는 `agent-framework`와 환경변수를 계속 읽되 warning을 한 번만
  출력한다.
- `config migrate-env --dry-run`은 key mapping, conflict, secret destination을
  보여주고 원본 `.env`를 수정하지 않는다.
- 실제 migration도 `.env`를 자동 삭제하지 않는다. 삭제는 별도 명시 확인을 받는다.
- config schema migration 전 backup을 만들고 실패 시 atomic rollback한다.
- 기존 Python API(`Settings`, `build_agent`, Provider factory)는 CLI와 같은 source
  resolver를 사용하되 공개 signature는 유지한다.
- alias 제거와 env 자동 로드 제거는 changelog, migration guide, 최소 한 release의
  deprecation 후 별도 결정한다.

## 10. 최종 Definition of Done

- `pipx install .` 또는 wheel 설치 후 `myagen`이 PATH에서 실행된다.
- `.env` 생성 없이 interactive command만으로 Provider와 secret 설정이 완료된다.
- 모든 기존 `Settings` field가 새 config 체계에 mapping되거나 명시적으로 deprecated다.
- secret이 TOML, argv, stdout/stderr, log, audit log, approval prompt에 노출되지 않는다.
- config precedence와 source가 사용자에게 설명 가능하고 테스트로 고정되어 있다.
- MCP, Provider SDK, bot, DB resource가 성공/실패/취소 모든 경로에서 정리된다.
- 재시작 후 session list/search/resume/clear/delete가 실제 SQLite 상태와 일치한다.
- old/new entry point 호환 정책과 제거 시점이 changelog에 기록된다.
- Ruff, MyPy, 전체 test, lockfile, packaging smoke test가 모두 통과한다.

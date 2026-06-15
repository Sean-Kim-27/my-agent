# Personal Codex Telegram Agent

Ubuntu LTS + OCI 서버에서 Docker 없이 직접 구동하는 개인용 Telegram 에이전트입니다.
Telegram 봇은 대화 입구 역할을 하고, 실제 추론과 작업은 서버에 로그인된 Codex OAuth 세션을 재사용합니다.

## Architecture

```text
Telegram app
    |
    v
python-telegram-bot webhook/polling process
    |
    +--> optional Cosmic Graph Intelligence harness
    |       (POST /api/compare/report)
    |
    v
openai-codex Python SDK
    |
    v
local Codex runtime + ~/.codex/auth.json
```

기본 실행 방식은 polling입니다. 개인용 단일 서버에서는 방화벽, TLS, reverse proxy 없이도 안정적으로 시작할 수 있기 때문입니다.

## Project Documents

- `AGENTS.md`: 다른 에이전트가 따라야 할 개발 지침
- `ARCHITECTURE.md`: 컴포넌트 책임, 인증 모델, 대화 모델
- `DEVELOPMENT.md`: 개발 절차, 검증, 확장 방법
- `SECURITY.md`: 개인 서버 기준 보안 원칙
- `ROADMAP.md`: 단계별 개발 우선순위

## Previous Test Results

최근 개발 과정에서 실제로 실행해 확인한 테스트/검증 결과입니다. 상세한 작업 로그는 `codex/YYYY-MM-DD.md` 파일에 날짜별로 남겨져 있습니다.

| Date | Scope | Command / Check | Result |
| --- | --- | --- | --- |
| 2026-06-12 | 초기 로드맵 구현 전체 테스트 | `. .venv/bin/activate && pytest tests -q` | `25 passed in 0.92s` |
| 2026-06-12 | 초기 로드맵 구현 컴파일 | `PYTHONPYCACHEPREFIX=/tmp/my-agent-pycache-final python -m compileall src` | 성공 |
| 2026-06-12 | smoke 검증 | SQLite initialize/upsert, persona prompt, `CodexRuntime.status()` import/instantiate | `smoke-ok` |
| 2026-06-13 | CGI harness 연동 전체 테스트 | `. .venv/bin/activate && pytest tests -q` | `29 passed in 0.96s` |
| 2026-06-13 | CGI harness 연동 컴파일 | `. .venv/bin/activate && PYTHONPYCACHEPREFIX=/tmp/my-agent-pycache-cgi-2 python -m compileall src` | 성공 |
| 2026-06-13 | CGI harness 로컬 HTTP smoke | CGI 리포트 prompt 주입 경로 확인 | `cgi-harness-smoke-ok` |
| 2026-06-14 | `/api/chat` 결과 전용 엔드포인트 | `. .venv/bin/activate && python -m pytest -q` | `32 passed, 1 warning` |
| 2026-06-14 | `/api/chat` 결과 전용 엔드포인트 컴파일 | `python3 -m compileall src` | 성공 |
| 2026-06-14 | my-agent API health/smoke | `GET /health`, `POST /api/chat` | `{"status":"ok"}`, `네, 연결은 정상입니다.` |
| 2026-06-14 | CGI Codex auth provider 전환 후 전체 테스트 | `. .venv/bin/activate && python -m pytest -q` | `33 passed, 1 warning` |
| 2026-06-14 | CGI Codex auth provider 전환 후 컴파일 | `python3 -m compileall src` | 성공 |
| 2026-06-14 | my-agent → CGI harness → Codex 실제 호출 | `POST http://127.0.0.1:8010/api/chat` | `네, CGI harness 컨텍스트를 받은 뒤 Codex로 답하고 있습니다.` |
| 2026-06-15 | README 테스트 결과 섹션 추가 후 회귀 테스트 | `. .venv/bin/activate && python -m pytest -q` | `34 passed, 1 warning in 1.18s` |

참고: 현재 개발 checkout은 `.git` 저장소가 아니라 `git status`/`git diff` 검증은 사용할 수 없습니다.

## Server Setup

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv git curl

mkdir -p ~/apps
cd ~/apps
git clone <your-repo-url> my-agent
cd my-agent

python3.12 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
```

Codex CLI가 없다면 설치한 뒤 로그인합니다.

```bash
npm install -g @openai/codex
codex login --device-auth
codex exec --skip-git-repo-check "Say hello from this server"
```

`codex login --device-auth`는 headless 서버에 적합합니다. 브라우저 링크와 일회용 코드를 로컬 브라우저에서 처리하면 서버의 `~/.codex/auth.json`에 세션이 저장됩니다.
앱은 시작 시 `CODEX_WORKDIR`로 이동한 뒤 Codex thread를 만들기 때문에, 에이전트가 읽고 쓸 개인 작업 폴더를 이 값으로 지정하세요.

## Telegram Setup

1. Telegram에서 `@BotFather`에게 `/newbot`을 보내 봇을 만듭니다.
2. 발급된 token을 `.env`에 넣습니다.
3. 본인 Telegram user id를 알아낸 뒤 `TELEGRAM_ALLOWED_USER_IDS`에 넣습니다.
4. 긴 Codex 실행을 제한하려면 `CODEX_TIMEOUT_SECONDS`를 서버 상황에 맞게 조정합니다.
5. 긴 작업 중 Telegram에 주기적으로 진행 중 메시지를 보내려면 `TELEGRAM_HEARTBEAT_SECONDS`를 조정합니다. `0` 이하로 두면 heartbeat 메시지를 끕니다.
6. 대화 metadata를 저장할 SQLite 경로를 `SQLITE_PATH`에 지정합니다.
7. SDK thread 생성 실패 시 `codex exec` fallback을 쓰려면 `CODEX_CLI_FALLBACK=true`를 설정합니다.
8. `~/CGI/CGI_Cosmic_Graph_Intelligence`의 Cosmic Graph Intelligence 리포트를 Codex prompt 강화 컨텍스트로 쓰려면 CGI 서버를 먼저 띄운 뒤 `CGI_HARNESS_ENABLED=true`를 설정합니다.

```bash
cp .env.example .env
nano .env
```

## Run Locally

```bash
. .venv/bin/activate
python -m personal_codex_agent
```

지원 명령:

- `/start`: 상태 확인
- `/status`: Codex runtime 시작 여부, active session 수, model, sandbox, workdir, timeout 확인
- `/reset`: 현재 Telegram chat의 Codex thread 초기화
- `/new`: 새 Codex 대화 시작
- `/cancel`: 진행 중인 Codex 작업 취소
- `/mode`: `default`, `dev`, `research` persona 확인/변경
- `/help`: 간단한 사용법

## Persistence And Runtime Modes

`SQLITE_PATH`에는 chat metadata, mode, 최근 message metadata가 저장됩니다. 현재 Codex Python SDK에서 안정적인 thread resume API/ID가 확인되지 않아 프로세스 재시작 후에는 저장된 metadata를 기준으로 상태를 파악하고 새 thread를 시작하는 방식으로 동작합니다.

`CODEX_CLI_FALLBACK=true`이면 SDK thread 생성이 실패할 때 `codex exec --skip-git-repo-check --model <CODEX_MODEL>` 경로로 기본 질의를 수행합니다. SDK 경로가 기본이며 fallback은 장애 대응용입니다.

## Cosmic Graph Intelligence Harness

`~/CGI/CGI_Cosmic_Graph_Intelligence` 프로젝트는 `POST /api/compare/report` 엔드포인트로 CGI 파이프라인 마크다운 리포트를 반환합니다. 이 앱은 선택적으로 해당 리포트를 가져와 Codex에 전달하는 prompt 앞부분에 bounded context로 추가합니다. Telegram 계층은 여전히 `CodexRuntime.run()`만 호출하고, CGI 호출 실패 시 사용자 요청 자체는 원본 prompt로 계속 처리합니다.

CGI 서버 예시:

```bash
cd ~/CGI/CGI_Cosmic_Graph_Intelligence
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`my-agent` 설정:

```env
CGI_HARNESS_ENABLED=true
CGI_HARNESS_ENDPOINT=http://127.0.0.1:8000/api/compare/report
CGI_HARNESS_MODE=balanced
CGI_HARNESS_TIMEOUT_SECONDS=60
CGI_HARNESS_MAX_REPORT_CHARS=8000
```

운영 로그:

- `cgi_harness_enhancement_completed`: chat_id, prompt_chars, enhanced_prompt_chars
- `cgi_harness_enhancement_failed`: chat_id

파일 업로드는 Telegram document metadata를 Codex prompt로 넘겨 후속 작업 맥락을 만들도록 처리합니다. 파일 본문 다운로드/분석 고도화는 별도 확장 지점입니다.

## Logging

기본 로그 포맷은 `timestamp level logger message`입니다. 운영 중에는 다음 event 이름으로 원인을 추적합니다.

- `codex_runtime_started`: model, sandbox, workdir, timeout_seconds
- `codex_runtime_stopped`: active_sessions
- `codex_chat_reset`: chat_id, existed
- `status_requested`: user_id, started, active_sessions, model, sandbox, workdir, timeout_seconds
- `codex_run_completed`: chat_id, user_id, prompt_chars, response_chars, duration_ms
- `codex_run_timed_out`: chat_id, user_id, prompt_chars, duration_ms
- `codex_run_failed`: chat_id, user_id, prompt_chars, duration_ms

민감한 사용자 프롬프트 본문과 Codex 응답 본문은 로그에 남기지 않고 길이만 남깁니다.

## systemd

`deploy/personal-codex-agent.service`의 `User`, `WorkingDirectory`, `EnvironmentFile`을 서버 경로에 맞게 수정한 뒤 설치합니다.

```bash
sudo cp deploy/personal-codex-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now personal-codex-agent
sudo journalctl -u personal-codex-agent -f
```

## Security Notes

- 이 봇은 개인용으로 설계되었습니다. 반드시 `TELEGRAM_ALLOWED_USER_IDS`를 설정하세요.
- `~/.codex/auth.json`은 비밀번호처럼 취급하세요.
- 서버 방화벽은 SSH 외 포트를 최소화하세요. polling 모드에서는 inbound Telegram webhook 포트가 필요 없습니다.
- 앱 전용 Unix user를 만들고 해당 user로 `codex login --device-auth`를 실행하는 구성을 권장합니다.

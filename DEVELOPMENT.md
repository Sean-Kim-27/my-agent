# Development Guide

이 문서는 다른 에이전트가 어떤 순서로 개발해야 하는지 정해둔 실행 지침입니다.

## Local Mental Model

이 프로젝트는 네 계층입니다.

1. Telegram transport
2. Access control and UX
3. Codex runtime adapter
4. Linux service deployment

기능을 추가할 때는 어느 계층의 변화인지 먼저 정하고, 다른 계층까지 번지지 않게 작업합니다.

## Setup

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
```

`.env`에는 실제 token을 넣되 커밋하지 않습니다.

```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_IDS=...
CODEX_MODEL=gpt-5.4
CODEX_SANDBOX=workspace_write
CODEX_WORKDIR=/home/ubuntu/agent-workspace
```

## Run

```bash
. .venv/bin/activate
python -m personal_codex_agent
```

Codex 로그인 확인:

```bash
codex exec --skip-git-repo-check "Say hello from this server"
```

## Test And Validation

현재 자동 테스트는 없습니다.
코드를 바꾸면 최소한 문법 검증을 합니다.

```bash
PYTHONPYCACHEPREFIX=/private/tmp/my-agent-pycache python3 -m compileall src
```

서버에서는 다음 smoke test를 수행합니다.

1. `systemctl status personal-codex-agent`
2. Telegram에서 `/start`
3. Telegram에서 짧은 질문
4. Telegram에서 `/reset`
5. `journalctl -u personal-codex-agent -n 100`

## Adding Commands

Telegram command는 `bot.py`에 추가합니다.

규칙:

- 모든 handler 첫 줄에서 `_guard()`를 통과시킨다.
- Codex thread 상태를 바꾸는 명령은 `CodexRuntime` 메서드로 캡슐화한다.
- Telegram 메시지 포맷은 간결하게 유지한다.

예상 명령:

- `/status`: 현재 chat의 실행 상태 표시
- `/cancel`: 실행 중인 작업 취소
- `/new`: `/reset` alias
- `/mode`: persona 또는 sandbox preset 선택

## Adding Persistence

권장 persistence는 SQLite입니다.

첫 단계 schema 예시:

```sql
CREATE TABLE chat_sessions (
  chat_id INTEGER PRIMARY KEY,
  codex_thread_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE message_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL
);
```

주의:

- message log에는 민감한 정보가 들어갈 수 있으므로 기본값은 최소 저장으로 둔다.
- `codex_thread_id` 복원은 SDK의 resume 기능을 실제로 검증한 뒤 켠다.

## Adding Codex CLI Fallback

SDK가 깨질 때를 대비한 fallback은 `codex_runtime.py` 안에 둡니다.

권장 방식:

- 기본: Python SDK
- fallback: `codex exec --skip-git-repo-check`
- timeout: 환경 변수로 조정
- stdout final response만 Telegram으로 전달
- stderr는 로그에 남기되 token이나 auth file 내용은 남기지 않음

fallback을 추가해도 Telegram bot 계층은 바꾸지 않습니다.

## Adding File Uploads

Telegram file upload를 추가할 때는 다음 원칙을 지킵니다.

- 파일은 `CODEX_WORKDIR/uploads/<chat_id>/` 아래 저장한다.
- 파일명은 Telegram 원본명을 그대로 신뢰하지 않는다.
- 저장 후 Codex prompt에는 절대경로와 사용자 요청을 함께 전달한다.
- 대용량 파일 제한을 둔다.

## Adding CGI Harness Integrations

`~/CGI/CGI_Cosmic_Graph_Intelligence` 연동은 Telegram 계층이 아니라 `cgi_harness.py`와 `codex_runtime.py` 경계에서 처리합니다.

원칙:

- CGI 서버 인터페이스는 `POST /api/compare/report`로 둔다.
- `CGI_HARNESS_ENABLED=false`를 기본값으로 유지한다.
- HTTP 호출은 timeout과 output length limit을 둔다.
- CGI 실패는 `cgi_harness_enhancement_failed`로 기록하고 원본 prompt로 계속 진행한다.
- 새 동작은 `tests/test_cgi_harness.py`와 `tests/test_codex_runtime.py`에 먼저 실패 테스트를 추가한다.

검증:

```bash
. .venv/bin/activate
pytest tests/test_cgi_harness.py tests/test_codex_runtime.py tests/test_config.py -q
```

CGI 프로젝트 자체 테스트는 별도 환경에서 requirements 설치 후 실행한다.

```bash
cd ~/CGI/CGI_Cosmic_Graph_Intelligence
pip install -r requirements.txt
python -m pytest tests -q
```

## Code Style

- Python 3.10 이상 호환을 유지한다.
- 복잡한 framework를 추가하기 전 표준 라이브러리와 현재 의존성으로 가능한지 먼저 본다.
- Telegram API와 Codex API 사이에 직접 결합을 만들지 않는다.
- 비동기 코드는 `asyncio` 흐름을 유지한다.

## Handoff Checklist

작업 종료 전 확인:

- `README.md`가 실제 실행 방식과 맞는가
- `ARCHITECTURE.md`에 구조 변경이 반영됐는가
- `SECURITY.md`에 새 위험이 반영됐는가
- `ROADMAP.md`의 상태가 갱신됐는가
- `codex/YYYY-MM-DD.md`에 작업 요약을 남겼는가


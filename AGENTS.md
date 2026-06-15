# Agent Development Instructions

이 저장소는 개인용 Telegram 인터페이스를 통해 서버의 Codex OAuth 세션을 사용하는 에이전트입니다.
다른 에이전트가 이 프로젝트를 이어 개발할 때는 아래 기준을 우선합니다.

## Product Goal

- 사용자는 Telegram으로 개인 서버의 Codex 에이전트와 대화한다.
- 서버는 Ubuntu LTS on OCI에서 Docker 없이 직접 실행한다.
- Codex 인증은 앱이 직접 OAuth 토큰을 구현하지 않고, 서버 user의 `codex login --device-auth` 결과를 재사용한다.
- 기본 운영은 polling + systemd이다. webhook, reverse proxy, Docker, Kubernetes는 명시 요청 전까지 기본 경로가 아니다.

## Non-Goals

- 다중 사용자 SaaS로 확장하지 않는다.
- 공개 인터넷 사용자를 받지 않는다.
- Telegram 외 채널을 먼저 추가하지 않는다.
- Codex OAuth 토큰을 앱 코드에서 직접 파싱하거나 갱신하지 않는다.
- Docker 격리를 전제로 구조를 바꾸지 않는다.

## Architecture Rules

- Telegram 관련 코드는 `src/personal_codex_agent/bot.py`에 둔다.
- Codex SDK 또는 Codex CLI 호출 래퍼는 `src/personal_codex_agent/codex_runtime.py`에 둔다.
- 환경 변수 파싱과 검증은 `src/personal_codex_agent/config.py`에 둔다.
- 프로세스 시작, logging, lifecycle wiring은 `src/personal_codex_agent/__main__.py`에 둔다.
- 운영 문서는 `README.md`, 설계 문서는 `ARCHITECTURE.md`, 개발 절차는 `DEVELOPMENT.md`, 보안 원칙은 `SECURITY.md`, 향후 작업은 `ROADMAP.md`에 갱신한다.

## Implementation Rules

- 개인용 서버라는 가정을 유지하되, `TELEGRAM_ALLOWED_USER_IDS` allowlist는 절대 제거하지 않는다.
- 대화 thread는 Telegram chat id 단위로 관리한다.
- 장기 작업, persistence, cancel 기능을 추가할 때도 기존 chat id 경계를 유지한다.
- Codex SDK가 불안정하거나 변경될 경우 `codex exec` fallback을 추가하되, 기존 SDK 경로를 갑자기 삭제하지 않는다.
- 비밀값은 `.env`와 서버의 `~/.codex/auth.json`에만 둔다. 저장소에 실제 token, user id, auth json을 커밋하지 않는다.
- README 명령어는 Ubuntu LTS 기준으로 유지한다.

## Verification

문서만 바꿔도 링크와 경로가 맞는지 확인한다.
Python 코드를 바꾸면 최소한 아래 명령을 실행한다.

```bash
PYTHONPYCACHEPREFIX=/private/tmp/my-agent-pycache python3 -m compileall src
```

Linux 서버에서 검증할 때는 아래 순서를 따른다.

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e .
python -m personal_codex_agent
```

## Handoff Notes

작업을 마치면 `codex/YYYY-MM-DD.md`에 변경 요약, 확인한 명령, 남은 리스크를 기록한다.
Obsidian MCP가 사용 가능하면 사용자의 vault 내 `codex/YYYY-MM-DD.md`에도 같은 요약을 남긴다.


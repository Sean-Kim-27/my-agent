# Architecture

이 문서는 다른 에이전트가 구조를 오해하지 않고 이어 개발하도록 만든 기준 문서입니다.

## One Sentence

Telegram 봇은 개인용 대화 UI이고, Codex 실행은 같은 Linux user로 로그인된 로컬 Codex 런타임이 담당합니다.

## Runtime Components

```text
Telegram client
  -> Telegram Bot API
  -> personal-codex-agent Python process
  -> optional Cosmic Graph Intelligence harness (HTTP /api/chat)
  -> openai-codex Python SDK
  -> local Codex app-server/runtime
  -> ~/.codex/auth.json or OS credential store
```

## Component Responsibilities

`src/personal_codex_agent/config.py`

- `.env`와 환경 변수를 읽는다.
- 필수값 누락을 시작 시점에 실패시킨다.
- runtime module이 Telegram token 같은 비밀값을 알 필요 없게 한다.

`src/personal_codex_agent/bot.py`

- Telegram command와 text message를 처리한다.
- user allowlist를 적용한다.
- `/status`로 Codex runtime 상태를 표시하고 status 요청을 구조화 로그로 남긴다.
- 긴 Codex run 동안 `TELEGRAM_HEARTBEAT_SECONDS` 주기로 "작업 중입니다..." 메시지를 보낸다.
- Codex run 성공/실패/timeout을 chat id, user id, prompt/response 길이, duration과 함께 로그로 남긴다. 프롬프트 본문은 로그에 남기지 않는다.
- Telegram 메시지 길이 제한에 맞게 응답을 나눈다.
- Codex 실행 방식은 알지 않고 `CodexRuntime.run()`만 호출한다.

`src/personal_codex_agent/codex_runtime.py`

- Codex SDK lifecycle을 관리하고 start/stop/reset lifecycle을 구조화 로그로 남긴다.
- Telegram chat id별 Codex thread를 관리한다.
- 같은 chat에서 동시 요청이 섞이지 않도록 lock을 둔다.
- `CODEX_TIMEOUT_SECONDS` 안에 끝나지 않는 run을 timeout 처리한다.
- Codex SDK가 바뀔 경우 이 파일에서 호환 레이어를 만든다.
- 선택적으로 CGI harness가 제공되면 Codex 실행 전에 prompt를 강화한다.

`src/personal_codex_agent/cgi_harness.py`

- `~/CGI/CGI_Cosmic_Graph_Intelligence`의 `POST /api/chat` 엔드포인트를 호출한다.
- 비교/Judge 리포트가 아니라 CGI 파이프라인 최종 답변만 받아 길이 제한 안에서 Codex prompt context로 감싼다.
- CGI 서버 장애, timeout, 빈 응답은 명확한 `CGIHarnessError`로 변환한다.
- Telegram 계층이나 Codex SDK 인증 정보를 알지 않는다.

`src/personal_codex_agent/__main__.py`

- logging을 설정한다.
- `CODEX_WORKDIR`로 이동한다.
- Codex runtime과 Telegram application lifecycle을 연결한다.

`deploy/personal-codex-agent.service`

- Ubuntu systemd 배포 기준 템플릿이다.
- 실제 서버 user, working directory, env file 경로는 서버에 맞게 수정한다.

## Authentication Model

이 앱은 Codex OAuth를 직접 구현하지 않습니다.
운영자는 서버에서 다음을 먼저 실행합니다.

```bash
codex login --device-auth
```

그 결과 Codex CLI/SDK가 재사용할 수 있는 인증 정보가 서버 user 계정에 저장됩니다.
앱은 해당 user로 실행되므로 Codex SDK가 저장된 인증을 사용합니다.

중요한 결론:

- 앱 코드에 OpenAI OAuth client flow를 만들지 않는다.
- 앱 코드가 `~/.codex/auth.json`을 열어 token을 직접 읽지 않는다.
- 인증 갱신은 Codex 런타임에 맡긴다.

## Conversation Model

현재 기준은 in-memory session입니다.

- key: Telegram chat id
- value: Codex thread object + asyncio lock
- `/reset`: 해당 chat id의 thread를 버리고 다음 메시지에서 새 thread 생성

현재 한계:

- 프로세스 재시작 시 thread mapping이 사라진다.
- 과거 thread id를 복원하지 않는다.
- Telegram message id와 Codex event log를 영속 저장하지 않는다.

권장 다음 단계:

- SQLite로 `chat_id -> codex_thread_id` mapping 저장
- 최근 사용자 메시지와 최종 응답 metadata 저장
- 재시작 후 `resumeThread` 또는 Python SDK equivalent가 안정적으로 확인되면 복원

## Execution Model

기본은 polling입니다.

선택 이유:

- 개인용 서버에서 inbound HTTPS endpoint가 필요 없다.
- OCI security list와 reverse proxy 설정이 단순하다.
- Telegram Bot API token만 있으면 바로 시작할 수 있다.

webhook은 다음 조건이 모두 필요할 때만 추가합니다.

- 고정 도메인과 TLS가 있다.
- reverse proxy 운영이 이미 안정화되어 있다.
- polling latency나 connection model이 실제 문제가 된다.

## Data Boundaries

저장소에 들어가도 되는 것:

- 코드
- 문서
- `.env.example`
- systemd 템플릿

저장소에 들어가면 안 되는 것:

- `.env`
- Telegram bot token
- 실제 Telegram user id 목록
- `~/.codex/auth.json`
- Codex logs 중 민감한 사용자 프롬프트가 포함된 파일

## Extension Points

안전한 확장 순서:

1. SQLite persistence
2. `/status`, `/cancel`, `/new` 같은 명령어
3. Codex run timeout과 queue 상태 메시지
4. file upload 처리
5. Codex CLI fallback
6. webhook mode
7. multi-persona routing
8. optional CGI prompt harness

피해야 할 확장:

- allowlist 없는 public bot
- 임의 사용자가 shell command를 직접 실행하게 하는 기능
- Telegram message를 그대로 shell command로 변환하는 기능
- OAuth token 직접 관리


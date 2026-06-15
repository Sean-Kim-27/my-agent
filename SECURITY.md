# Security

이 프로젝트는 개인용 봇이지만, Codex는 서버에서 파일을 읽고 명령을 실행할 수 있으므로 보안 경계를 명확히 유지해야 합니다.

## Primary Threats

- Telegram bot token 유출
- 허용되지 않은 Telegram 사용자의 접근
- `~/.codex/auth.json` 유출
- Codex가 민감한 파일을 읽거나 수정하는 것
- 로그에 사용자 프롬프트, token, 파일 경로가 과하게 남는 것
- webhook을 열었을 때 외부 공격면이 늘어나는 것
- CGI harness endpoint를 외부에 열거나 신뢰할 수 없는 리포트를 무제한 prompt에 주입하는 것

## Required Controls

`TELEGRAM_ALLOWED_USER_IDS`는 필수입니다.
이 값이 없으면 앱은 시작하지 않아야 합니다.

`.env` 권장 권한:

```bash
chmod 600 .env
```

Codex auth cache 권장 권한:

```bash
chmod 700 ~/.codex
chmod 600 ~/.codex/auth.json
```

서비스는 전용 Linux user로 실행하는 것을 권장합니다.

```bash
sudo adduser --disabled-password --gecos "" codexagent
```

그 user로 `codex login --device-auth`를 실행해야 앱과 Codex 인증 소유자가 일치합니다.

## OCI Network Posture

polling 모드에서는 Telegram webhook inbound 포트가 필요 없습니다.

권장:

- inbound SSH만 허용
- SSH source IP 제한
- 필요하지 않은 public port 차단
- OS 보안 업데이트 적용

webhook을 추가할 경우:

- TLS termination 필요
- reverse proxy hardening 필요
- request path에 secret을 포함
- Telegram IP allowlist 여부 검토

## CGI Harness

`CGI_HARNESS_ENABLED=true`로 사용할 때도 CGI 서버는 기본적으로 `127.0.0.1`에만 바인딩합니다. `0.0.0.0` 또는 public port로 노출하지 않습니다.

권장:

- `CGI_HARNESS_ENDPOINT`는 `http://127.0.0.1:8000/api/compare/report` 같은 loopback URL로 둔다.
- `CGI_HARNESS_MAX_REPORT_CHARS`로 Codex prompt에 주입되는 CGI 리포트 길이를 제한한다.
- CGI 서버 장애 시 앱은 원본 prompt로 fail-open하며, 사용자 prompt 전문은 로그에 남기지 않는다.
- CGI 프로젝트의 `.env`와 `GEMINI_API_KEY`는 저장소에 커밋하지 않는다.

## Codex Sandbox

기본값은 `workspace_write`입니다.

권장:

- `CODEX_WORKDIR`를 전용 작업 폴더로 둔다.
- 홈 디렉터리 전체를 작업 폴더로 쓰지 않는다.
- 민감한 SSH key, cloud credential, production secret이 `CODEX_WORKDIR` 안에 들어가지 않게 한다.

`full_access`는 개인 서버라도 기본값으로 쓰지 않습니다.
필요한 작업이 명확할 때만 일시적으로 사용합니다.

## Logging

로그에 남겨도 되는 것:

- handler 진입 여부
- 오류 type과 stack trace
- Telegram chat id 같은 운영 식별자

주의할 것:

- Telegram bot token
- Codex auth json 내용
- 사용자가 보낸 민감한 프롬프트 전문
- 파일 업로드 원문

## Secrets

저장소에 커밋 금지:

- `.env`
- `auth.json`
- Telegram token
- OpenAI API key
- 개인 Telegram user id가 포함된 실제 운영 설정

향후 `.gitignore`를 추가할 때는 최소한 아래 항목을 포함합니다.

```gitignore
.env
.venv/
__pycache__/
*.pyc
auth.json
*.db
```

## Incident Response

Telegram token이 유출된 경우:

1. BotFather에서 token revoke
2. `.env` 교체
3. 서비스 재시작
4. 로그에서 비정상 접근 확인

Codex auth가 유출된 경우:

1. ChatGPT/OpenAI 계정에서 세션 revoke
2. 서버의 `~/.codex/auth.json` 삭제
3. `codex login --device-auth` 재실행
4. 서버 접근 로그 확인


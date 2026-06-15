# Roadmap

이 문서는 다음 에이전트가 우선순위를 헷갈리지 않도록 작성한 개발 순서입니다.

## Current State

완료:

- Telegram text message 수신
- Telegram user id allowlist
- chat id별 in-memory Codex thread
- `/start`, `/help`, `/reset`
- Codex Python SDK 기반 실행
- Ubuntu systemd 템플릿
- 기본 운영 문서
- `.gitignore`
- Codex 실행 timeout (`CODEX_TIMEOUT_SECONDS`)
- `/status` 명령
- 긴 작업 heartbeat 메시지 (`TELEGRAM_HEARTBEAT_SECONDS`)
- health/status structured logging
- SQLite persistence
- `/cancel`, `/new`, `/mode`
- file upload metadata handoff
- Codex CLI fallback (`CODEX_CLI_FALLBACK`)
- persona/mode presets
- optional Cosmic Graph Intelligence prompt harness
- 기본 automated tests

아직 없음:

- webhook mode

## Phase 1: Make It Reliably Operable

목표: 개인 서버에서 재시작과 오류에 강하게 만든다.

작업:

- [x] `.gitignore` 추가
- [x] health/status logging 정리
- [x] Codex 실행 timeout 추가
- [x] `/status` 명령 추가
- [x] 긴 작업 중 "작업 중" heartbeat 메시지 추가
- [x] systemd hardening 옵션 검토

완료 기준:

- 서비스 재시작 후 정상적으로 Telegram 응답
- Codex 실패 시 사용자에게 명확한 오류 메시지
- 로그로 원인 파악 가능

## Phase 2: Persistence

목표: 프로세스 재시작 후에도 대화 상태를 최대한 복원한다.

작업:

- [x] SQLite storage module 추가
- [x] chat session metadata 저장
- [x] message metadata 최소 저장
- [x] `/reset`이 DB 상태도 정리
- [x] SDK resume 가능 여부 검증: 현재 SDK에서 안정적 thread resume API/ID가 확인되지 않아 metadata 저장 + 새 thread 안내 경로로 처리

완료 기준:

- 재시작 후 chat id 상태 확인 가능
- thread 복원이 불가능해도 사용자에게 새 thread 시작을 명확히 안내

## Phase 3: Better Telegram UX

목표: Telegram에서 개인 비서처럼 쓰기 편하게 만든다.

작업:

- [x] `/cancel`
- [x] `/new`
- [x] `/mode`
- [x] 응답 Markdown escaping 검토: 기본 plain text 응답으로 Telegram Markdown parsing을 사용하지 않아 escaping 불필요
- [x] 파일 업로드 metadata handoff
- 음성 메시지 transcription은 별도 검토

완료 기준:

- 긴 응답도 읽기 좋게 분할
- 사용자가 작업을 중단하거나 새 대화로 전환 가능

## Phase 4: Runtime Resilience

목표: Codex SDK 변화나 장애에도 최소 기능이 살아 있게 한다.

작업:

- [x] `codex exec` fallback
- [x] runtime adapter interface 정리: `CodexRuntime.run/reset/cancel/status` 경계 유지
- [x] SDK/CLI 선택 환경 변수 추가 (`CODEX_CLI_FALLBACK`)
- [x] 실패 유형별 user-facing 메시지 분리

완료 기준:

- SDK import 또는 thread_start 실패 시 CLI fallback으로 기본 질의 가능

## Phase 5: Personas And Skills

목표: 사용자가 원하는 에이전트 성격과 작업 모드를 선택할 수 있게 한다.

작업:

- [x] persona prompt registry
- [x] `/mode`로 persona 선택
- [x] mode별 system instruction template
- [x] Obsidian MCP 또는 로컬 vault가 사용 가능하면 persona/skill 참고 자동화: 현재 앱 runtime에는 외부 MCP 직접 의존을 두지 않고 mode preset에 한정

완료 기준:

- 기본 모드, 개발 모드, 리서치 모드 같은 preset 사용 가능
- mode 변경이 다음 Codex thread 생성에 반영

## Phase 6: Cosmic Graph Intelligence Harness

목표: `~/CGI/CGI_Cosmic_Graph_Intelligence`의 그래프 기반 메타 프롬프팅 리포트를 Codex prompt 강화 컨텍스트로 선택 적용한다.

작업:

- [x] CGI `POST /api/compare/report` 엔드포인트 인터페이스 확인
- [x] `CGIHarness` HTTP adapter 추가
- [x] `CGI_HARNESS_*` 환경 변수 추가
- [x] `CodexRuntime`에서 SDK/CLI 실행 전 prompt 강화 적용
- [x] CGI 장애 시 원본 prompt로 fail-open 처리
- [x] 테스트와 문서 갱신

완료 기준:

- `CGI_HARNESS_ENABLED=true`일 때 CGI report가 Codex prompt context에 포함됨
- CGI 서버가 꺼져 있어도 Telegram 요청이 CGI 오류만으로 실패하지 않음

## Explicitly Deferred

다음은 지금 당장 하지 않습니다.

- Dockerization
- multi-tenant auth
- public web dashboard
- payment/billing
- Kubernetes
- browser UI


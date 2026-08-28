# 🤖 자율형 AI 에이전트 프레임워크 (Autonomous AI Agent Framework)

[🌐 English Version (영어 버전)](./README_EN.md)

---

다양한 LLM Provider(OpenAI, Anthropic Claude, NVIDIA NIM, OpenAI 호환 로컬 모델) 및 인증 방식(API Key, Codex OAuth)을 교체 가능하게 지원하며, Tool Calling, Discord Bot, Telegram Bot, ReAct 자율 실행 루프 및 세션 격리 메모리를 갖춘 **확장성 높은 독립형 비동기 Python AI Agent Framework**입니다.

---

## 🌟 핵심 아키텍처 특징

- **의존성 역전 원칙 (Dependency Inversion)**: `Agent` 코어는 특정 LLM 공급자 SDK, 인증 방식, 메시징 플랫폼에 직접 종속되지 않습니다.
- **Provider & Auth 완전 분리**:
  - 지원 Provider: `OpenAI`, `Anthropic Claude`, `NVIDIA NIM`, `OpenAI-Compatible (vLLM, Ollama, Groq, Together, LM Studio 등)`
  - 지원 인증: `ApiKeyAuth`, `CodexOAuthAuth` (공식 OAuth 토큰 수명주기), `NoAuth`
- **ReAct 고급 런타임 및 실행 궤적 추적 (Phase 5)**:
  - 다단계 자율 추론 루프 및 `max_steps` 제어
  - Thought / Action / Observation 실행 궤적 보존 (`AgentStep`, `AgentRunResult`, `run_with_trace()`)
  - 비동기 라이프사이클 이벤트 콜백 (`AgentCallbackHandler`, `ConsoleCallbackHandler`)
  - 도구 실행 오류 시 자율 에러 분석 및 복구 프롬프팅 (Self-Correction)
  - 스트리밍 토큰 제너레이터 프로토콜 (`generate_stream`, `StreamChunk`)
- **Provider 중립적 자동 Tool Calling (Phase 2)**:
  - Python 함수 시그니처 및 Docstring 분석 기반 자동 JSON Schema 생성 (`schema.py`)
  - `@registry.tool` 데코레이터를 지원하는 `ToolRegistry`
  - 동기/비동기 함수 실행, 타임아웃, 예외 격리를 지원하는 `ToolExecutor`
- **Discord Bot 연동 (Phase 3)**:
  - 비동기 `asyncio.Queue` 기반 이벤트 큐 및 백그라운드 워커
  - DM, Guild Channel, Thread 단위의 독립된 세션 ID 격리
  - 멘션 및 채널 화이트리스트 필터링
  - Discord 2000자 제한 안전 분할 (마크다운 코드 블록 무결성 유지)
- **Telegram Bot 연동 (Phase 4)**:
  - `python-telegram-bot` 기반 비동기 Polling / Webhook 확장 구조
  - 1:1 개인 대화, 그룹, 채널별 세션 ID 격리
  - Telegram MarkdownV2 특수문자 안전 이스케이프 및 Fallback 처리
  - Telegram 4096자 제한 안전 분할
  - `/start`, `/help`, `/clear` 빌트인 명령어 지원
- **세션 격리 메모리**: `SessionManager`를 통해 사용자/채널별 대화 기록을 완벽히 격리하여 세션 간 간섭 및 메모리 누수 방지
- **보안 및 비밀정보 마스킹**: 정규식 기반 로거를 통해 API 키, Bearer 토큰, 비밀번호 등 민감 정보를 콘솔 및 로그에서 자동 마스킹
- **Async-First**: 모든 네트워크 I/O, Tool 실행, 봇 이벤트 루프가 논블로킹 `asyncio`로 구동

---

## 🏛️ 시스템 아키텍처

```text
                      메시징 인터페이스 (CLI / Discord / Telegram)
                                            │
                                            ▼
                                       Agent Core
                                 (ReAct Loop & Tracing)
                                            │
                      ┌─────────────────────┼─────────────────────┐
                      ▼                     ▼                     ▼
               SessionManager          ToolRegistry          LLMProvider
                      │                     │                     │
                      ▼                     ▼          ┌──────────┼──────────┐
             ConversationMemory        ToolExecutor    ▼          ▼          ▼
          (InMemory / Redis / DB)   (Sync/Async/Timeout) OpenAI Anthropic NvidiaNIM
                                                           │                  │
                                                           ▼                  ▼
                                                   CodexOAuthAuth /       ApiKeyAuth /
                                                      ApiKeyAuth             NoAuth
```

---

## 💡 사용 예시

### 1. Tool 등록 및 ReAct 실행 궤적 추적

```python
import asyncio
from agent_framework import (
    Agent,
    ConsoleCallbackHandler,
    ToolRegistry,
    create_llm_provider,
)

registry = ToolRegistry()

@registry.tool(description="두 숫자를 곱합니다.")
def multiply(a: int, b: int) -> int:
    """두 정수를 곱하는 도구."""
    return a * b

agent = Agent(
    provider=create_llm_provider(),
    tool_registry=registry,
    callbacks=[ConsoleCallbackHandler()],
)

async def main():
    # Thought, Action, Observation 전체 궤적과 함께 실행
    result = await agent.run_with_trace("15 곱하기 24는 얼마인가요?")
    
    print("최종 응답:", result.content)
    print(f"총 실행 스텝: {result.total_steps}")
    for step in result.steps:
        print(f"스텝 {step.step_number}: 생각={step.thought}, 도구={step.tool_calls}")

asyncio.run(main())
```

---

## 🚀 빠른 시작 (Quick Start)

### 1. 환경 설정

`.env.example` 파일을 복사하여 `.env` 파일을 생성하고 사용할 API 키를 입력합니다.

```bash
cp .env.example .env
```

`.env` 예시:
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini

# Discord 사용 시 (선택)
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_REQUIRE_MENTION=true

# Telegram 사용 시 (선택)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_REQUIRE_MENTION=true
```

### 2. 실행 모드

#### 1) 대화형 터미널 CLI 실행
```bash
python -m agent_framework.main
```

Provider를 즉시 변경하여 실행할 수도 있습니다:
```bash
python -m agent_framework.main --provider anthropic
python -m agent_framework.main --provider nvidia_nim
```

Provider 설정 상태 확인:
```bash
python -m agent_framework.main --providers
```

#### 2) Discord 봇 실행
```bash
python -m agent_framework.main --discord
```

#### 3) Telegram 봇 실행
```bash
python -m agent_framework.main --telegram
```

---

## 📁 디렉토리 구조

```text
My-Agent/
├── pyproject.toml                     # 프로젝트 의존성 및 툴링 설정
├── .env.example                       # 환경변수 템플릿
├── .gitignore                         # 보안 및 캐시 파일 제외 설정
├── README.md                          # 한국어 메인 문서
├── README_EN.md                       # 영어 문서
│
├── src/agent_framework/
│   ├── __init__.py                    # 공개 API export (v0.3.0)
│   ├── exceptions.py                  # 도메인 커스텀 예외 계층
│   ├── main.py                        # CLI / Discord / Telegram 통합 런처
│   │
│   ├── agent/                         # [Agent Core & ReAct]
│   │   ├── __init__.py
│   │   ├── agent.py                   # Agent 오케스트레이터 (ReAct Loop)
│   │   └── events.py                  # 라이프사이클 이벤트 콜백
│   │
│   ├── integrations/                  # [메시징 플랫폼 연동 어댑터]
│   │   ├── discord/                   # Discord 어댑터 (비동기 큐, 2000자 분할)
│   │   │   ├── __init__.py
│   │   │   ├── bot.py                 # DiscordAgentBot 클라이언트
│   │   │   └── router.py              # 세션 라우팅 및 메시지 청킹
│   │   └── telegram/                  # Telegram 어댑터 (MarkdownV2, 4096자 분할)
│   │       ├── __init__.py
│   │       ├── bot.py                 # TelegramAgentBot 애플리케이션
│   │       └── router.py              # 세션 라우팅 및 이스케이프
│   │
│   ├── tools/                         # [Tool Calling 서브시스템]
│   │   ├── __init__.py
│   │   ├── schema.py                  # 함수 기반 자동 JSON Schema 생성기
│   │   ├── registry.py                # ToolRegistry (@registry.tool)
│   │   └── executor.py                # 비동기/동기 타임아웃 ToolExecutor
│   │
│   ├── models/                        # [표준 데이터 모델]
│   │   ├── __init__.py
│   │   ├── events.py                  # AgentStep, AgentRunResult, StreamChunk
│   │   ├── message.py                 # Message (system/user/assistant/tool)
│   │   ├── response.py                # LLMResponse & ProviderCapabilities
│   │   └── tool.py                    # ToolDefinition, ToolCall, ToolCallResult
│   │
│   ├── memory/                        # [세션 격리 메모리]
│   │   ├── __init__.py
│   │   ├── base.py                    # ConversationMemory 인터페이스
│   │   ├── in_memory.py               # InMemoryConversationMemory
│   │   └── session.py                 # Multi-Session Manager
│   │
│   ├── auth/                          # [보안 인증 계층]
│   │   ├── __init__.py
│   │   ├── base.py                    # AuthenticationProvider 인터페이스
│   │   ├── api_key.py                 # ApiKeyAuth
│   │   └── codex_oauth.py             # CodexOAuthAuth (공식 OAuth 프로토콜)
│   │
│   ├── llm/                           # [Swappable Provider 계층]
│   │   ├── __init__.py
│   │   ├── base.py                    # LLMProvider ABC & 스트리밍
│   │   ├── openai_compatible.py       # OpenAI 호환 전송 계층 (Streaming 지원)
│   │   ├── openai_provider.py         # OpenAI Provider (API Key / OAuth)
│   │   ├── anthropic_provider.py      # Anthropic Claude Messages API
│   │   ├── nvidia_nim_provider.py     # NVIDIA NIM Provider
│   │   └── factory.py                 # create_llm_provider 동적 팩토리
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py                # pydantic-settings 중앙 설정
│   │
│   └── logging/
│       ├── __init__.py
│       └── logger.py                  # 비밀정보 자동 마스킹 구조화 로거
│
└── tests/
    ├── __init__.py
    ├── conftest.py                    # MockLLMProvider 및 테스트 픽스처
    └── unit/                          # 67개 단위 테스트 스위트 (100% 통과)
```

---

## 🧪 테스트 및 코드 품질 검사

모든 단위 테스트는 외부 네트워크 요청 없이 Mock 객체로 안전하고 독립적으로 실행됩니다.

### 단위 테스트 실행
```bash
pytest -v
```

### Linter 및 정적 타입 검사
```bash
ruff check src tests
mypy src tests
```

---

## 📋 구현 완료 체크리스트 (Definition of Done)

- [x] **Phase 0 & 1**: Clean Architecture, 교체 가능한 Provider(OpenAI, Anthropic, NIM, Codex OAuth), 세션 분리 메모리, 토큰 마스킹 로깅, CLI
- [x] **Phase 2**: 함수 기반 자동 JSON Schema 생성기, `ToolRegistry`, 비동기/동기 `ToolExecutor`, Multi-Step Tool Calling 루프
- [x] **Phase 3**: `discord.py` 기반 디스코드 봇 어댑터, 비동기 큐 워커, 채널/스레드별 세션 분리, 2000자 분할
- [x] **Phase 4**: `python-telegram-bot` 기반 텔레그램 봇 어댑터, MarkdownV2 이스케이프, 4096자 분할, 세션 분리
- [x] **Phase 5**: ReAct Thought/Action/Observation 실행 궤적(`run_with_trace`), `AgentCallbackHandler` 이벤트 훅, 자율 에러 복구, 스트리밍 프로토콜
- [x] **품질 검증**: 67개 단위 테스트 100% 통과, Ruff 및 MyPy 엄격 정적 검사 통과, 한/영 문서화 완료

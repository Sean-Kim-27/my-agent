# 🤖 Autonomous AI Agent Framework

[🇰🇷 한국어 버전 (Korean Version)](./README.md)

---

A high-performance, asynchronous Python AI Agent Framework built for production-grade agentic applications. Features swappable LLM providers, isolated multi-session memory, pluggable authentication (API Key & Codex OAuth), provider-neutral Tool Calling, Discord and Telegram Bot adapters, ReAct Thought/Action/Observation execution traces, lifecycle callback hooks, and strict dependency inversion.

---

## 🌟 Key Architecture Highlights

- **Dependency Inversion**: The `Agent` core does not depend on any specific LLM provider, authentication mechanism, or messaging protocol.
- **Provider & Auth Decoupling**: Swappable providers (`OpenAI`, `Anthropic`, `NVIDIA NIM`, `OpenAI-Compatible`) powered by clean authentication abstractions (`ApiKeyAuth`, `CodexOAuthAuth`, `NoAuth`).
- **Advanced ReAct Runtime & Execution Trace (Phase 5)**:
  - Multi-step iterative reasoning loop with configurable `max_steps`.
  - Structured Thought / Action / Observation step trajectory (`AgentStep`, `AgentRunResult`).
  - Asynchronous lifecycle event callbacks (`AgentCallbackHandler`, `ConsoleCallbackHandler`).
  - Autonomous error recovery prompt feedback and self-correction.
  - Streaming token generator protocols (`generate_stream`, `StreamChunk`).
- **Provider-Neutral Tool Calling (Phase 2)**:
  - Automated reflection & JSON Schema extraction from Python functions and docstrings (`schema.py`).
  - Thread-safe `ToolRegistry` with `@registry.tool` decorator support.
  - Safe `ToolExecutor` handling sync/async execution, per-tool timeouts, and error containment.
- **Discord Bot Adapter (Phase 3)**:
  - Non-blocking `asyncio.Queue` event processing with background worker.
  - Granular Session ID mapping across Direct Messages, Guild Channels, and Threads.
  - Mention and Channel whitelist filtering.
  - Safe response chunking respecting Discord's 2000-character limit with markdown code-fence preservation.
- **Telegram Bot Adapter (Phase 4)**:
  - Async polling & webhook-extensible architecture using `python-telegram-bot`.
  - Session ID isolation per chat & user (`telegram:private:<id>`, `telegram:group:<id>:user:<id>`).
  - Telegram MarkdownV2 escaping outside of code blocks with plain-text fallback.
  - Safe message chunking respecting Telegram's 4096-character limit.
  - Built-in command handlers (`/start`, `/help`, `/clear`).
- **Session-Isolated Memory**: `SessionManager` manages isolated `ConversationMemory` stores per user, channel, or chat, preventing cross-talk and memory leaks.
- **Safety & Secret Masking**: Structured logging with automated redaction of API keys, bearer tokens, passwords, and authorization headers.
- **Async-First**: All network I/O, tool executions, bots, and state transitions are built with non-blocking `asyncio`.

---

## 🏛️ System Architecture

```text
                      Messaging Interfaces (CLI / Discord / Telegram)
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

## 💡 ReAct Trajectory & Callback Example

```python
import asyncio
from agent_framework import (
    Agent,
    ConsoleCallbackHandler,
    ToolRegistry,
    create_llm_provider,
)

registry = ToolRegistry()

@registry.tool(description="Multiply two numbers")
def multiply(a: int, b: int) -> int:
    return a * b

agent = Agent(
    provider=create_llm_provider(),
    tool_registry=registry,
    callbacks=[ConsoleCallbackHandler()],
)

# Run with full Thought/Action/Observation execution trace
result = await agent.run_with_trace("What is 15 multiplied by 24?")

print("Final Content:", result.content)
print(f"Executed in {result.total_steps} step(s)")
for step in result.steps:
    print(f"Step {step.step_number}: Thought={step.thought}, Tools={[t.name for t in step.tool_calls]}")
```

---

## 🎮 Launching Integrations

### Interactive CLI
```bash
python -m agent_framework.main
```

### Discord Bot
```bash
python -m agent_framework.main --discord
```

### Telegram Bot
```bash
python -m agent_framework.main --telegram
```

---

## 📁 Directory Structure

```text
My-Agent/
├── pyproject.toml                     # Project metadata, dependencies, and tool settings
├── .env.example                       # Environment variable templates
├── .gitignore                         # Secret protection and artifact ignores
├── README.md                          # Korean Framework documentation (Main)
├── README_EN.md                       # English Framework documentation
│
├── src/agent_framework/
│   ├── __init__.py                    # Public API exports
│   ├── exceptions.py                  # Custom domain exception hierarchy
│   ├── main.py                        # Interactive CLI and Bot launcher
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── agent.py                   # Agent orchestrator with ReAct multi-step loop
│   │   └── events.py                  # Lifecycle callbacks (AgentCallbackHandler)
│   │
│   ├── integrations/
│   │   ├── discord/                   # [Phase 3 Discord Integration]
│   │   │   ├── __init__.py
│   │   │   ├── bot.py                 # DiscordAgentBot client with async queue worker
│   │   │   └── router.py              # Discord session mapping, filtering, & chunking
│   │   └── telegram/                  # [Phase 4 Telegram Integration]
│   │       ├── __init__.py
│   │       ├── bot.py                 # TelegramAgentBot application & command handlers
│   │       └── router.py              # Telegram session mapping, MarkdownV2, & chunking
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── schema.py                  # Automated JSON Schema generation from functions
│   │   ├── registry.py                # ToolRegistry with decorator support
│   │   └── executor.py                # Async/Sync ToolExecutor with timeouts
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── events.py                  # ReAct AgentStep, AgentRunResult, StreamChunk
│   │   ├── message.py                 # Standardized Message model (system/user/assistant/tool)
│   │   ├── response.py                # LLMResponse & ProviderCapabilities models
│   │   └── tool.py                    # ToolDefinition, ToolCall, ToolCallResult models
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── base.py                    # Abstract ConversationMemory interface
│   │   ├── in_memory.py               # Async-safe InMemoryConversationMemory
│   │   └── session.py                 # Multi-session SessionManager
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── base.py                    # AuthenticationProvider base & AuthCredentials
│   │   ├── api_key.py                 # ApiKeyAuth implementation with secret masking
│   │   └── codex_oauth.py             # Official Codex/OpenAI OAuth credential lifecycle
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py                    # LLMProvider abstract base class & streaming generator
│   │   ├── openai_compatible.py       # OpenAI-compatible transport layer with streaming
│   │   ├── openai_provider.py         # OpenAI Provider (API Key & Codex OAuth)
│   │   ├── anthropic_provider.py      # Anthropic Provider (Claude Messages API)
│   │   ├── nvidia_nim_provider.py     # NVIDIA NIM Provider (Hosted & Self-hosted)
│   │   └── factory.py                 # Dynamic Provider Factory (create_llm_provider)
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py                # Pydantic-settings centralized configuration
│   │
│   └── logging/
│       ├── __init__.py
│       └── logger.py                  # Structured logger with regex secret redaction
│
└── tests/
    ├── __init__.py
    ├── conftest.py                    # Fixtures & MockLLMProvider
    └── unit/
        ├── test_models.py             # Message, Response, Tool model tests
        ├── test_memory.py             # Memory CRUD & trimming tests
        ├── test_session.py            # Session isolation tests
        ├── test_auth.py               # API key & OAuth auth tests
        ├── test_tool_schema.py        # Automated schema generation tests
        ├── test_tool_registry.py      # Tool registry & decorator tests
        ├── test_tool_executor.py      # Sync/Async tool executor & timeout tests
        ├── test_agent_tools.py        # Multi-step tool loop & max_steps tests
        ├── test_react_events.py       # ReAct callbacks, trace, & self-correction tests
        ├── test_streaming.py          # LLM streaming generator tests
        ├── test_llm_providers.py      # Provider conversion & tool format tests
        ├── test_discord.py            # Discord routing, filtering, chunking & bot tests
        ├── test_telegram.py           # Telegram routing, MarkdownV2, chunking & bot tests
        ├── test_agent.py              # Agent lifecycle & multi-turn memory tests
        └── test_factory.py            # Dynamic factory configuration tests
```

---

## 🧪 Testing and Code Quality

### Running Unit Tests

All unit tests run completely decoupled from external network requests via mocks:

```bash
pytest -v
```

### Linting and Type Checking

```bash
ruff check src tests
mypy src tests
```

---

## 📋 Definition of Done (Full Framework Checklist)

- [x] **Phase 0 & 1**: Clean architecture, swappable providers (OpenAI, Anthropic, NVIDIA NIM, Codex OAuth), multi-session memory, structured secret masking, CLI runner.
- [x] **Phase 2**: Automated JSON Schema reflection, `ToolRegistry`, safe async/sync `ToolExecutor`, multi-step tool execution loop.
- [x] **Phase 3**: Decoupled Discord Bot adapter (`discord.py`), async queue worker, session mapping, 2000-character safe splitting.
- [x] **Phase 4**: Decoupled Telegram Bot adapter (`python-telegram-bot`), async polling, MarkdownV2 escaping, 4096-character safe splitting.
- [x] **Phase 5**: Advanced ReAct execution trajectory (`run_with_trace`), lifecycle event callbacks (`AgentCallbackHandler`), autonomous error recovery prompting, streaming token generator protocols.
- [x] **Verification**: 67 unit tests with 100% pass rate, 0 linter errors (`ruff`), 0 type errors (`mypy` strict mode).

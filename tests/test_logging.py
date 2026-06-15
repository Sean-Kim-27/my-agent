from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from personal_codex_agent.__main__ import configure_logging
from personal_codex_agent.bot import TelegramCodexBot
from personal_codex_agent.config import Settings


class FakeBotApi:
    async def send_chat_action(self, chat_id: int, action: str) -> None:
        pass


class FakeMessage:
    text = "hello"

    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class FakeCodex:
    async def run(self, chat_id: int, prompt: str) -> str:
        return "answer"

    def status(self) -> dict[str, object]:
        return {
            "started": True,
            "active_sessions": 1,
            "model": "gpt-test",
            "sandbox": "workspace_write",
            "workdir": "/tmp/work",
            "timeout_seconds": 30,
        }


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        telegram_bot_token="token",
        allowed_user_ids={123},
        codex_model="gpt-test",
        codex_sandbox="workspace_write",
        codex_workdir=Path("/tmp/work"),
        codex_timeout_seconds=30,
        telegram_max_response_chars=3900,
        telegram_heartbeat_seconds=0,
        sqlite_path=Path("/tmp/agent.sqlite3"),
        codex_cli_fallback=False,
    )


@pytest.mark.asyncio
async def test_message_logs_codex_run_success_without_prompt_content(settings: Settings, caplog: pytest.LogCaptureFixture) -> None:
    bot = TelegramCodexBot(settings, FakeCodex())
    message = FakeMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=999),
        effective_message=message,
    )

    with caplog.at_level(logging.INFO, logger="personal_codex_agent.bot"):
        await bot.message(update, SimpleNamespace(bot=FakeBotApi()))

    assert message.replies == ["answer"]
    matching = [record for record in caplog.records if record.message == "codex_run_completed"]
    assert len(matching) == 1
    record = matching[0]
    assert record.chat_id == 999
    assert record.user_id == 123
    assert record.prompt_chars == 5
    assert record.response_chars == 6
    assert record.duration_ms >= 0
    assert "hello" not in caplog.text


@pytest.mark.asyncio
async def test_status_logs_runtime_status_request(settings: Settings, caplog: pytest.LogCaptureFixture) -> None:
    bot = TelegramCodexBot(settings, FakeCodex())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_message=FakeMessage(),
    )

    with caplog.at_level(logging.INFO, logger="personal_codex_agent.bot"):
        await bot.status(update, SimpleNamespace())

    matching = [record for record in caplog.records if record.message == "status_requested"]
    assert len(matching) == 1
    record = matching[0]
    assert record.user_id == 123
    assert record.started is True
    assert record.active_sessions == 1


def test_configure_logging_suppresses_http_client_token_urls() -> None:
    logging.getLogger("httpx").setLevel(logging.NOTSET)

    configure_logging()

    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpcore").level >= logging.WARNING

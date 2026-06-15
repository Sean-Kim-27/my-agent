from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from personal_codex_agent.bot import TelegramCodexBot
from personal_codex_agent.config import Settings


class FakeBotApi:
    def __init__(self) -> None:
        self.actions: list[tuple[int, str]] = []

    async def send_chat_action(self, chat_id: int, action: str) -> None:
        self.actions.append((chat_id, action))


@dataclass
class FakeMessage:
    text: str | None = None
    replies: list[str] | None = None

    async def reply_text(self, text: str) -> None:
        if self.replies is None:
            self.replies = []
        self.replies.append(text)


class FakeStorage:
    def __init__(self) -> None:
        self.mode = "default"
        self.reset: list[int] = []

    def get_chat(self, chat_id: int):
        return SimpleNamespace(mode=self.mode)

    def set_mode(self, chat_id: int, mode: str) -> None:
        self.mode = mode

    def reset_chat(self, chat_id: int) -> None:
        self.reset.append(chat_id)

    def record_message(self, **kwargs) -> None:
        pass

    def upsert_chat(self, metadata) -> None:
        self.mode = metadata.mode


class FakeCodex:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.cancelled: list[int] = []
        self.reset: list[int] = []

    async def run(self, chat_id: int, prompt: str) -> str:
        self.prompts.append(prompt)
        return f"answer: {prompt}"

    async def reset_chat(self, chat_id: int) -> None:
        self.reset.append(chat_id)

    async def cancel_chat(self, chat_id: int) -> bool:
        self.cancelled.append(chat_id)
        return True

    def status(self) -> dict[str, object]:
        return {
            "started": True,
            "active_sessions": 2,
            "model": "gpt-test",
            "sandbox": "workspace_write",
            "workdir": "/tmp/work",
            "timeout_seconds": 30,
        }


@pytest.fixture()
def bot() -> TelegramCodexBot:
    settings = Settings(
        telegram_bot_token="token",
        allowed_user_ids={123},
        codex_model="gpt-test",
        codex_sandbox="workspace_write",
        codex_workdir=Path("/tmp/work"),
        codex_timeout_seconds=30,
        telegram_max_response_chars=3900,
        telegram_heartbeat_seconds=30,
        sqlite_path=Path("/tmp/agent.sqlite3"),
        codex_cli_fallback=False,
    )
    return TelegramCodexBot(settings, FakeCodex())


@pytest.mark.asyncio
async def test_status_reports_runtime_state_for_allowed_user(bot: TelegramCodexBot) -> None:
    message = FakeMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_message=message,
    )

    await bot.status(update, SimpleNamespace())

    assert message.replies == [
        "Codex runtime 상태\n"
        "- started: yes\n"
        "- active sessions: 2\n"
        "- model: gpt-test\n"
        "- sandbox: workspace_write\n"
        "- workdir: /tmp/work\n"
        "- timeout: 30s"
    ]


@pytest.mark.asyncio
async def test_help_mentions_status_command(bot: TelegramCodexBot) -> None:
    message = FakeMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_message=message,
    )

    await bot.help(update, SimpleNamespace())

    assert message.replies is not None
    assert "/status" in message.replies[0]


class SlowCodex(FakeCodex):
    async def run(self, chat_id: int, prompt: str) -> str:
        await asyncio.sleep(0.015)
        return "done"


@pytest.mark.asyncio
async def test_message_sends_heartbeat_while_codex_is_running() -> None:
    settings = Settings(
        telegram_bot_token="token",
        allowed_user_ids={123},
        codex_model="gpt-test",
        codex_sandbox="workspace_write",
        codex_workdir=Path("/tmp/work"),
        codex_timeout_seconds=30,
        telegram_max_response_chars=3900,
        telegram_heartbeat_seconds=0.01,
        sqlite_path=Path("/tmp/agent.sqlite3"),
        codex_cli_fallback=False,
    )
    bot = TelegramCodexBot(settings, SlowCodex())
    message = FakeMessage(text="hello")
    api = FakeBotApi()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=999),
        effective_message=message,
    )
    context = SimpleNamespace(bot=api)

    await bot.message(update, context)

    assert message.replies == ["작업 중입니다...", "done"]


@pytest.mark.asyncio
async def test_mode_command_sets_storage_mode_and_lists_modes() -> None:
    settings = Settings(
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
    storage = FakeStorage()
    bot = TelegramCodexBot(settings, FakeCodex(), storage=storage)
    message = FakeMessage(text="/mode dev")
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=999),
        effective_message=message,
    )
    context = SimpleNamespace(args=["dev"])

    await bot.mode(update, context)

    assert storage.mode == "dev"
    assert message.replies == ["mode를 dev 로 변경했습니다."]


@pytest.mark.asyncio
async def test_message_prefixes_prompt_with_selected_mode() -> None:
    settings = Settings(
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
    storage = FakeStorage()
    storage.mode = "dev"
    codex = FakeCodex()
    bot = TelegramCodexBot(settings, codex, storage=storage)
    message = FakeMessage(text="fix bug")
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=999),
        effective_message=message,
    )

    await bot.message(update, SimpleNamespace(bot=FakeBotApi()))

    assert "소프트웨어 개발 모드" in codex.prompts[0]
    assert codex.prompts[0].endswith("fix bug")


@pytest.mark.asyncio
async def test_cancel_command_cancels_chat_runtime() -> None:
    settings = Settings(
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
    codex = FakeCodex()
    bot = TelegramCodexBot(settings, codex)
    message = FakeMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=999),
        effective_message=message,
    )

    await bot.cancel(update, SimpleNamespace())

    assert codex.cancelled == [999]
    assert message.replies == ["진행 중인 Codex 작업을 취소했습니다."]


@pytest.mark.asyncio
async def test_new_command_resets_chat_and_reports_new_thread() -> None:
    settings = Settings(
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
    codex = FakeCodex()
    bot = TelegramCodexBot(settings, codex)
    message = FakeMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=999),
        effective_message=message,
    )

    await bot.new(update, SimpleNamespace())

    assert codex.reset == [999]
    assert message.replies == ["새 Codex 대화를 시작합니다."]


@pytest.mark.asyncio
async def test_document_upload_sends_file_context_to_codex() -> None:
    settings = Settings(
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
    codex = FakeCodex()
    bot = TelegramCodexBot(settings, codex)
    document = SimpleNamespace(file_name="notes.txt", file_size=128)
    message = FakeMessage(text=None)
    message.document = document
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=999),
        effective_message=message,
    )

    await bot.document(update, SimpleNamespace(bot=FakeBotApi()))

    assert "파일 업로드" in codex.prompts[0]
    assert "notes.txt" in codex.prompts[0]

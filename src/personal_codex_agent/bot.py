from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .config import Settings
from .persona import build_prompt, list_modes, resolve_mode
from .storage import ChatMetadata

if TYPE_CHECKING:
    from .codex_runtime import CodexRuntime
    from .storage import SQLiteStorage

logger = logging.getLogger(__name__)


class TelegramCodexBot:
    def __init__(self, settings: Settings, codex: "CodexRuntime", storage: "SQLiteStorage | None" = None) -> None:
        self.settings = settings
        self.codex = codex
        self.storage = storage

    def build_application(self) -> Application:
        app = Application.builder().token(self.settings.telegram_bot_token).build()
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help))
        app.add_handler(CommandHandler("reset", self.reset))
        app.add_handler(CommandHandler("new", self.new))
        app.add_handler(CommandHandler("cancel", self.cancel))
        app.add_handler(CommandHandler("mode", self.mode))
        app.add_handler(CommandHandler("status", self.status))
        app.add_handler(MessageHandler(filters.Document.ALL, self.document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message))
        return app

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        await update.effective_message.reply_text(
            "개인 Codex 에이전트가 준비됐습니다. 작업 내용을 그대로 보내주세요."
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        await update.effective_message.reply_text(
            "/status 로 런타임 상태를 확인하고, /reset 또는 /new 로 현재 대화 thread를 새로 시작할 수 있습니다. "
            "/cancel 로 진행 중인 작업을 취소하고, /mode 로 모드를 확인/변경할 수 있습니다."
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        status = self.codex.status()
        logger.info(
            "status_requested",
            extra={
                "user_id": update.effective_user.id if update.effective_user else None,
                "started": status["started"],
                "active_sessions": status["active_sessions"],
                "model": status["model"],
                "sandbox": status["sandbox"],
                "workdir": status["workdir"],
                "timeout_seconds": status["timeout_seconds"],
            },
        )
        await update.effective_message.reply_text(self._format_status(status))

    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        await self.codex.reset_chat(update.effective_chat.id)
        if self.storage is not None:
            self.storage.reset_chat(update.effective_chat.id)
        await update.effective_message.reply_text("현재 Telegram chat의 Codex thread를 초기화했습니다.")

    async def new(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        await self.codex.reset_chat(update.effective_chat.id)
        if self.storage is not None:
            self.storage.reset_chat(update.effective_chat.id)
        await update.effective_message.reply_text("새 Codex 대화를 시작합니다.")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        cancelled = await self.codex.cancel_chat(update.effective_chat.id)
        if cancelled:
            await update.effective_message.reply_text("진행 중인 Codex 작업을 취소했습니다.")
        else:
            await update.effective_message.reply_text("취소할 진행 중인 Codex 작업이 없습니다.")

    async def mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        args = getattr(context, "args", []) or []
        if not args:
            modes = ", ".join(list_modes())
            current = self._mode_for_chat(update.effective_chat.id)
            await update.effective_message.reply_text(f"현재 mode: {current}\n사용 가능: {modes}")
            return
        requested = resolve_mode(args[0])
        if self.storage is not None:
            self.storage.set_mode(update.effective_chat.id, requested.name)
        await update.effective_message.reply_text(f"mode를 {requested.name} 로 변경했습니다.")

    async def message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return

        message = update.effective_message
        prompt = message.text or ""
        if self.storage is not None:
            self.storage.record_message(
                chat_id=update.effective_chat.id,
                telegram_message_id=getattr(message, "message_id", None),
                direction="in",
                text_chars=len(prompt),
            )
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

        heartbeat = asyncio.create_task(self._heartbeat(message))
        started_at = time.monotonic()
        codex_prompt = build_prompt(self._mode_for_chat(update.effective_chat.id), prompt)
        try:
            answer = await self.codex.run(update.effective_chat.id, codex_prompt)
        except TimeoutError:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            logger.exception(
                "codex_run_timed_out",
                extra={
                    "chat_id": update.effective_chat.id,
                    "user_id": update.effective_user.id if update.effective_user else None,
                    "prompt_chars": len(prompt),
                    "duration_ms": duration_ms,
                },
            )
            await message.reply_text(
                "Codex 실행 시간이 제한을 초과했습니다. /status 로 상태를 확인한 뒤 다시 시도해주세요."
            )
            return
        except Exception:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            logger.exception(
                "codex_run_failed",
                extra={
                    "chat_id": update.effective_chat.id,
                    "user_id": update.effective_user.id if update.effective_user else None,
                    "prompt_chars": len(prompt),
                    "duration_ms": duration_ms,
                },
            )
            await message.reply_text(
                "Codex 실행 중 오류가 났습니다. 서버 로그와 `codex login` 상태를 확인해주세요."
            )
            return
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

        duration_ms = int((time.monotonic() - started_at) * 1000)
        logger.info(
            "codex_run_completed",
            extra={
                "chat_id": update.effective_chat.id,
                "user_id": update.effective_user.id if update.effective_user else None,
                "prompt_chars": len(prompt),
                "response_chars": len(answer),
                "duration_ms": duration_ms,
            },
        )
        if self.storage is not None:
            self.storage.record_message(
                chat_id=update.effective_chat.id,
                telegram_message_id=None,
                direction="out",
                text_chars=len(answer),
            )
            self.storage.upsert_chat(
                ChatMetadata(
                    chat_id=update.effective_chat.id,
                    last_user_message_id=getattr(message, "message_id", None),
                    last_response_chars=len(answer),
                )
            )
        for chunk in self._split(answer):
            await message.reply_text(chunk)

    async def document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._guard(update):
            return
        document = update.effective_message.document
        file_name = getattr(document, "file_name", "unknown")
        file_size = getattr(document, "file_size", None)
        prompt = f"파일 업로드가 수신되었습니다. 파일명: {file_name}, 크기: {file_size} bytes. 이 파일을 바탕으로 다음 작업 지시를 기다려주세요."
        answer = await self.codex.run(update.effective_chat.id, build_prompt(self._mode_for_chat(update.effective_chat.id), prompt))
        for chunk in self._split(answer):
            await update.effective_message.reply_text(chunk)

    def _mode_for_chat(self, chat_id: int) -> str:
        if self.storage is None:
            return "default"
        metadata = self.storage.get_chat(chat_id)
        return getattr(metadata, "mode", "default") if metadata is not None else "default"

    async def _heartbeat(self, message) -> None:
        interval = self.settings.telegram_heartbeat_seconds
        if interval <= 0:
            return
        while True:
            await asyncio.sleep(interval)
            await message.reply_text("작업 중입니다...")

    async def _guard(self, update: Update) -> bool:
        user = update.effective_user
        if user is None or user.id not in self.settings.allowed_user_ids:
            if update.effective_message is not None:
                await update.effective_message.reply_text("이 봇은 소유자만 사용할 수 있습니다.")
            return False
        return True

    def _split(self, text: str) -> list[str]:
        max_chars = self.settings.telegram_max_response_chars
        if len(text) <= max_chars:
            return [text]

        chunks: list[str] = []
        remaining = text
        while remaining:
            chunks.append(remaining[:max_chars])
            remaining = remaining[max_chars:]
        return chunks

    def _format_status(self, status: dict[str, Any]) -> str:
        started = "yes" if status["started"] else "no"
        return (
            "Codex runtime 상태\n"
            f"- started: {started}\n"
            f"- active sessions: {status['active_sessions']}\n"
            f"- model: {status['model']}\n"
            f"- sandbox: {status['sandbox']}\n"
            f"- workdir: {status['workdir']}\n"
            f"- timeout: {status['timeout_seconds']:g}s"
        )


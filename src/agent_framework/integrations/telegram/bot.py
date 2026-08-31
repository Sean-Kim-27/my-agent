"""Telegram Bot adapter connecting python-telegram-bot to the Agent runtime."""

import asyncio

from agent_framework.agent.agent import Agent
from agent_framework.config.settings import Settings, get_settings
from agent_framework.exceptions import ConfigurationError
from agent_framework.integrations.telegram.callbacks import (
    TelegramConfirmationBroker,
    TelegramConfirmationHandler,
)
from agent_framework.integrations.telegram.router import (
    escape_markdown_v2,
    extract_clean_telegram_text,
    generate_telegram_session_id,
    should_process_telegram_message,
    split_telegram_message,
)
from agent_framework.logging.logger import get_logger
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logger = get_logger("agent_framework.telegram")


class TelegramAgentBot:
    """Asynchronous Telegram bot application forwarding events to the decoupled Agent core."""

    def __init__(
        self,
        agent: Agent,
        settings: Settings | None = None,
        token: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.agent = agent
        self.token = token or self.settings.telegram_bot_token
        self.bot_username: str | None = None

        if not self.token or not self.token.strip():
            raise ConfigurationError(
                message="Missing Telegram Bot Token. Please configure TELEGRAM_BOT_TOKEN in .env or provide token.",
                details={"setting": "TELEGRAM_BOT_TOKEN"},
            )

        self.app: Application = (  # type: ignore[type-arg]
            ApplicationBuilder().token(self.token).build()
        )
        self.confirmation_broker = TelegramConfirmationBroker()
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register command and message handlers on the application."""
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("clear", self.cmd_clear))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        self.app.add_handler(
            CallbackQueryHandler(self.confirmation_broker.on_callback_query)
        )

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if update.effective_message:
            await update.effective_message.reply_text(
                "👋 Hello! I am an autonomous AI Assistant.\n"
                "Send me a message to start chatting, or use /help to see available commands."
            )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if update.effective_message:
            await update.effective_message.reply_text(
                "🤖 Available Commands:\n"
                "• /start - Start interaction\n"
                "• /help  - Show help instructions\n"
                "• /clear - Clear conversation history for this chat"
            )

    async def cmd_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /clear command to reset session memory."""
        msg = update.effective_message
        if not msg or not update.effective_user or not update.effective_chat:
            return

        session_id = generate_telegram_session_id(
            chat_id=update.effective_chat.id,
            user_id=update.effective_user.id,
            chat_type=update.effective_chat.type,
        )
        await self.agent.clear_session(session_id)
        await msg.reply_text(f"🧹 Cleared conversation memory for session `{session_id}`.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Process incoming user text message and reply with Agent response."""
        msg = update.effective_message
        user = update.effective_user
        chat = update.effective_chat

        if not msg or not msg.text or not user or not chat:
            return

        if self.bot_username is None:
            me = await context.bot.get_me()
            self.bot_username = me.username

        should_process = should_process_telegram_message(
            is_bot=user.is_bot,
            chat_id=chat.id,
            chat_type=chat.type,
            text=msg.text,
            bot_username=self.bot_username,
            allowed_chats=self.settings.telegram_allowed_chat_ids,
            require_mention=self.settings.telegram_require_mention,
        )

        if not should_process:
            return

        clean_text = extract_clean_telegram_text(msg.text, bot_username=self.bot_username)
        if not clean_text:
            return

        session_id = generate_telegram_session_id(
            chat_id=chat.id,
            user_id=user.id,
            chat_type=chat.type,
        )

        logger.info(f"Telegram processing message for session '{session_id}'")

        try:
            # Send typing action
            await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
            confirmation_handler = TelegramConfirmationHandler(
                broker=self.confirmation_broker,
                chat_id=chat.id,
                user_id=user.id,
                bot=context.bot,
                timeout=self.settings.telegram_confirmation_timeout,
            )
            response = await self.agent.run(
                clean_text,
                session_id=session_id,
                callbacks=[confirmation_handler],
            )

            if response.content:
                chunks = split_telegram_message(response.content, max_chunk_size=4096)
                for chunk in chunks:
                    try:
                        escaped = escape_markdown_v2(chunk)
                        await msg.reply_text(escaped, parse_mode=ParseMode.MARKDOWN_V2)
                    except Exception:
                        # Fallback to plain text if MarkdownV2 parsing fails
                        await msg.reply_text(chunk, parse_mode=None)
            else:
                await msg.reply_text("*(No response content)*")

        except Exception as exc:
            logger.error(f"Error handling Telegram message for session '{session_id}': {exc}", exc_info=True)
            await msg.reply_text(f"❌ An error occurred: {type(exc).__name__}: {exc}")

    async def start(self) -> None:
        """Start the Telegram bot using non-blocking application polling."""
        logger.info("Initializing and starting Telegram Agent Bot...")
        await self.app.initialize()
        await self.app.start()
        if self.app.updater:
            await self.app.updater.start_polling()
        logger.info("Telegram Bot is running in polling mode.")

    async def stop(self) -> None:
        """Stop and gracefully shut down the Telegram application."""
        logger.info("Stopping Telegram Agent Bot...")
        if self.app.updater and self.app.updater.running:
            await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
        logger.info("Telegram Bot stopped successfully.")


async def start_telegram_bot(
    agent: Agent,
    token: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Convenience helper to initialize and launch the Telegram bot."""
    bot = TelegramAgentBot(agent=agent, settings=settings, token=token)
    await bot.start()
    try:
        # Keep running until cancelled
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        await bot.stop()

"""Discord Bot adapter connecting discord.py events to the Agent runtime."""

import asyncio
from typing import Any

import discord
from agent_framework.agent.agent import Agent
from agent_framework.config.settings import Settings, get_settings
from agent_framework.exceptions import ConfigurationError
from agent_framework.integrations.discord.callbacks import DiscordConfirmationHandler
from agent_framework.integrations.discord.router import (
    extract_clean_content,
    generate_session_id,
    should_process_message,
    split_message_content,
)
from agent_framework.logging.logger import get_logger

logger = get_logger("agent_framework.discord")


class DiscordAgentBot(discord.Client):
    """Asynchronous Discord bot client forwarding events to the decoupled Agent core."""

    def __init__(
        self,
        agent: Agent,
        settings: Settings | None = None,
        **options: Any,
    ) -> None:
        self.settings = settings or get_settings()
        self.agent = agent

        # Configure intents
        intents = options.pop("intents", None)
        if intents is None:
            intents = discord.Intents.default()
            intents.message_content = True

        super().__init__(intents=intents, **options)

        self._queue: asyncio.Queue[tuple[discord.Message, str, str]] = asyncio.Queue(
            maxsize=self.settings.discord_max_queue_size
        )
        self._worker_task: asyncio.Task[None] | None = None
        self._is_closing = False

    async def setup_hook(self) -> None:
        """Start the background queue worker upon client setup."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(
                self._process_message_queue(),
                name="discord_agent_worker",
            )
            logger.info("Started Discord background message processing worker")

    async def on_ready(self) -> None:
        """Log bot status and connected guilds upon successful websocket connection."""
        if self.user:
            logger.info(f"Discord Bot connected as '{self.user.name}' (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")

    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming Discord message event."""
        if self.user is None or self._is_closing:
            return

        is_dm = message.guild is None
        guild_id = message.guild.id if message.guild else None
        channel_id = message.channel.id
        thread_id = message.channel.id if isinstance(message.channel, discord.Thread) else None
        mentions_bot = self.user in message.mentions

        should_process = should_process_message(
            author_id=message.author.id,
            is_bot=message.author.bot,
            channel_id=channel_id,
            guild_id=guild_id,
            bot_user_id=self.user.id,
            mentions_bot=mentions_bot,
            allowed_channels=self.settings.discord_allowed_channel_ids,
            require_mention=self.settings.discord_require_mention,
            is_dm=is_dm,
        )

        if not should_process:
            return

        clean_text = extract_clean_content(message.content, bot_user_id=self.user.id)
        if not clean_text:
            return

        session_id = generate_session_id(
            author_id=message.author.id,
            channel_id=channel_id,
            guild_id=guild_id,
            thread_id=thread_id,
            is_dm=is_dm,
        )

        try:
            self._queue.put_nowait((message, clean_text, session_id))
            logger.debug(f"Enqueued Discord message from session '{session_id}' (queue size: {self._queue.qsize()})")
        except asyncio.QueueFull:
            logger.warning(f"Discord message queue is full ({self.settings.discord_max_queue_size}). Dropping message.")
            await message.reply("⚠️ Server is currently overloaded. Please try again in a moment.")

    async def _process_message_queue(self) -> None:
        """Background worker pulling messages from the queue and generating responses."""
        while not self._is_closing:
            try:
                message, clean_text, session_id = await self._queue.get()
            except asyncio.CancelledError:
                break

            try:
                logger.info(f"Processing Discord request for session '{session_id}'")
                confirmation_handler = DiscordConfirmationHandler(
                    client=self,
                    message=message,
                    timeout=self.settings.discord_confirmation_timeout,
                )
                async with message.channel.typing():
                    response = await self.agent.run(
                        clean_text,
                        session_id=session_id,
                        callbacks=[confirmation_handler],
                    )

                if response.content:
                    chunks = split_message_content(response.content, max_chunk_size=2000)
                    for chunk in chunks:
                        await message.reply(chunk)
                else:
                    await message.reply("*(No content returned from assistant)*")

            except Exception as exc:
                logger.error(f"Error processing Discord message for session '{session_id}': {exc}", exc_info=True)
                try:
                    await message.reply(f"❌ An error occurred while processing your request: {type(exc).__name__}")
                except Exception:
                    pass
            finally:
                self._queue.task_done()

    async def close(self) -> None:
        """Gracefully shut down background workers and disconnect from Discord."""
        self._is_closing = True
        logger.info("Shutting down Discord bot client and cancelling worker...")

        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        await super().close()
        logger.info("Discord bot closed successfully.")


async def start_discord_bot(
    agent: Agent,
    token: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Convenience helper to initialize and launch the Discord bot."""
    cfg = settings or get_settings()
    bot_token = token or cfg.discord_bot_token

    if not bot_token or not bot_token.strip():
        raise ConfigurationError(
            message="Missing Discord Bot Token. Please configure DISCORD_BOT_TOKEN in .env or provide token.",
            details={"setting": "DISCORD_BOT_TOKEN"},
        )

    client = DiscordAgentBot(agent=agent, settings=cfg)
    try:
        await client.start(bot_token)
    except KeyboardInterrupt:
        await client.close()

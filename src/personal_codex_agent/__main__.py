from __future__ import annotations

import asyncio
import logging
import os

from .bot import TelegramCodexBot
from .cgi_harness import CGIHarness
from .codex_runtime import CodexRuntime
from .config import load_settings
from .storage import SQLiteStorage


async def shutdown_application(app) -> None:
    updater = getattr(app, "updater", None)
    if updater is not None and getattr(updater, "running", False):
        await updater.stop()
    if getattr(app, "running", False):
        await app.stop()
    await app.shutdown()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def async_main() -> None:
    configure_logging()
    settings = load_settings()
    settings.codex_workdir.mkdir(parents=True, exist_ok=True)
    os.chdir(settings.codex_workdir)

    cgi_harness = None
    if settings.cgi_harness_enabled:
        cgi_harness = CGIHarness(
            endpoint=settings.cgi_harness_endpoint,
            mode=settings.cgi_harness_mode,
            timeout_seconds=settings.cgi_harness_timeout_seconds,
            max_report_chars=settings.cgi_harness_max_report_chars,
        )

    codex = CodexRuntime(
        model=settings.codex_model,
        sandbox_name=settings.codex_sandbox,
        workdir=settings.codex_workdir,
        timeout_seconds=settings.codex_timeout_seconds,
        fallback_to_cli=settings.codex_cli_fallback,
        cgi_harness=cgi_harness,
    )
    storage = SQLiteStorage(settings.sqlite_path)
    storage.initialize()
    await codex.start()
    try:
        app = TelegramCodexBot(settings, codex, storage=storage).build_application()
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()
    finally:
        if "app" in locals():
            await shutdown_application(app)
        await codex.stop()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

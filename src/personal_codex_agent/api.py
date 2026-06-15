from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Protocol

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .cgi_harness import CGIHarness
from .codex_runtime import CodexRuntime

logger = logging.getLogger(__name__)


class CodexRunner(Protocol):
    async def run(self, chat_id: int, prompt: str) -> str: ...


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    chat_id: int = 0


def create_app(codex: CodexRunner) -> FastAPI:
    app = FastAPI(title="Personal Codex Agent API", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/chat", response_class=PlainTextResponse)
    async def chat(request: ChatRequest) -> str:
        try:
            return await codex.run(request.chat_id, request.message)
        except TimeoutError as exc:
            logger.exception("api_chat_timeout", extra={"chat_id": request.chat_id})
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("api_chat_failed", extra={"chat_id": request.chat_id})
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_codex_runtime_from_env() -> CodexRuntime:
    cgi_harness = None
    if _env_bool("CGI_HARNESS_ENABLED", False):
        cgi_harness = CGIHarness(
            endpoint=os.getenv("CGI_HARNESS_ENDPOINT", "http://127.0.0.1:8000/api/chat").strip(),
            mode=os.getenv("CGI_HARNESS_MODE", "balanced").strip(),
            timeout_seconds=float(os.getenv("CGI_HARNESS_TIMEOUT_SECONDS", "60")),
            max_report_chars=int(os.getenv("CGI_HARNESS_MAX_REPORT_CHARS", "8000")),
        )

    return CodexRuntime(
        model=os.getenv("CODEX_MODEL", "gpt-5.4").strip(),
        sandbox_name=os.getenv("CODEX_SANDBOX", "workspace_write").strip(),
        workdir=Path(os.getenv("CODEX_WORKDIR", os.getcwd())).expanduser(),
        timeout_seconds=float(os.getenv("CODEX_TIMEOUT_SECONDS", "300")),
        fallback_to_cli=_env_bool("CODEX_CLI_FALLBACK", False),
        cgi_harness=cgi_harness,
    )


async def async_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    host = os.getenv("MY_AGENT_API_HOST", "127.0.0.1").strip()
    port = int(os.getenv("MY_AGENT_API_PORT", "8010"))

    codex = create_codex_runtime_from_env()
    await codex.start()
    config = uvicorn.Config(create_app(codex), host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        await codex.stop()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

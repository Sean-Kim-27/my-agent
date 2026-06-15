from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai_codex import AsyncCodex, Sandbox


SANDBOX_BY_NAME = {
    "read_only": Sandbox.read_only,
    "workspace_write": Sandbox.workspace_write,
    "full_access": Sandbox.full_access,
}

logger = logging.getLogger(__name__)


@dataclass
class ChatSession:
    thread: Any
    lock: asyncio.Lock
    current_task: asyncio.Task[Any] | None = None


class CodexRuntime:
    def __init__(
        self,
        model: str,
        sandbox_name: str,
        workdir: Path,
        timeout_seconds: float = 300,
        fallback_to_cli: bool = False,
        cgi_harness: Any | None = None,
    ) -> None:
        self.model = model
        self.sandbox = SANDBOX_BY_NAME.get(sandbox_name, Sandbox.workspace_write)
        self.workdir = workdir
        self.timeout_seconds = timeout_seconds
        self.fallback_to_cli = fallback_to_cli
        self.cgi_harness = cgi_harness
        self._codex: AsyncCodex | None = None
        self._sessions: dict[int, ChatSession] = {}

    async def start(self) -> None:
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._codex = AsyncCodex()
        await self._codex.__aenter__()
        logger.info(
            "codex_runtime_started",
            extra={
                "model": self.model,
                "sandbox": self._sandbox_name(),
                "workdir": str(self.workdir),
                "timeout_seconds": self.timeout_seconds,
            },
        )

    async def stop(self) -> None:
        if self._codex is not None:
            await self._codex.__aexit__(None, None, None)
            self._codex = None
            logger.info("codex_runtime_stopped", extra={"active_sessions": len(self._sessions)})

    async def reset_chat(self, chat_id: int) -> None:
        existed = chat_id in self._sessions
        self._sessions.pop(chat_id, None)
        logger.info("codex_chat_reset", extra={"chat_id": chat_id, "existed": existed})

    async def cancel_chat(self, chat_id: int) -> bool:
        session = self._sessions.get(chat_id)
        task = session.current_task if session is not None else None
        if task is None or task.done():
            return False
        task.cancel()
        logger.info("codex_run_cancelled", extra={"chat_id": chat_id})
        return True

    def status(self) -> dict[str, object]:
        return {
            "started": self._codex is not None,
            "active_sessions": len(self._sessions),
            "model": self.model,
            "sandbox": self._sandbox_name(),
            "workdir": str(self.workdir),
            "timeout_seconds": self.timeout_seconds,
        }

    async def run(self, chat_id: int, prompt: str) -> str:
        if self._codex is None:
            raise RuntimeError("Codex runtime is not started")

        try:
            session = await self._get_or_create_session(chat_id)
        except Exception:
            if self.fallback_to_cli:
                logger.exception("codex_sdk_thread_start_failed_falling_back_to_cli", extra={"chat_id": chat_id})
                enhanced_prompt = await self._maybe_enhance_prompt(prompt, chat_id)
                return await self._run_cli(enhanced_prompt)
            raise
        enhanced_prompt = await self._maybe_enhance_prompt(prompt, chat_id)
        async with session.lock:
            task = asyncio.create_task(session.thread.run(enhanced_prompt))
            session.current_task = task
            try:
                result = await asyncio.wait_for(
                    task,
                    timeout=self.timeout_seconds,
                )
            except TimeoutError as exc:
                raise TimeoutError(f"Codex run timed out after {self.timeout_seconds:g} seconds") from exc
            finally:
                session.current_task = None
            return getattr(result, "final_response", str(result))

    async def _get_or_create_session(self, chat_id: int) -> ChatSession:
        if chat_id in self._sessions:
            return self._sessions[chat_id]

        assert self._codex is not None
        thread = await self._codex.thread_start(
            model=self.model,
            sandbox=self.sandbox,
        )
        session = ChatSession(thread=thread, lock=asyncio.Lock())
        self._sessions[chat_id] = session
        return session

    def _sandbox_name(self) -> str:
        return next(
            (name for name, sandbox in SANDBOX_BY_NAME.items() if sandbox == self.sandbox),
            "unknown",
        )

    async def _maybe_enhance_prompt(self, prompt: str, chat_id: int) -> str:
        if self.cgi_harness is None:
            return prompt
        try:
            enhanced = await self.cgi_harness.enhance_prompt(prompt)
        except Exception:
            logger.exception("cgi_harness_enhancement_failed", extra={"chat_id": chat_id})
            return prompt
        logger.info(
            "cgi_harness_enhancement_completed",
            extra={
                "chat_id": chat_id,
                "prompt_chars": len(prompt),
                "enhanced_prompt_chars": len(enhanced),
            },
        )
        return enhanced

    async def _run_cli(self, prompt: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--model",
            self.model,
            prompt,
            cwd=str(self.workdir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", "replace") or "codex exec failed")
        return stdout.decode("utf-8", "replace").strip()

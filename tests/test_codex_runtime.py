from __future__ import annotations

import asyncio
import importlib
import logging
import sys
import types

import pytest


class _Sandbox:
    read_only = object()
    workspace_write = object()
    full_access = object()


class FakeAsyncCodex:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.fixture()
def runtime_module(monkeypatch):
    fake_openai_codex = types.SimpleNamespace(AsyncCodex=FakeAsyncCodex, Sandbox=_Sandbox)
    monkeypatch.setitem(sys.modules, "openai_codex", fake_openai_codex)
    sys.modules.pop("personal_codex_agent.codex_runtime", None)
    module = importlib.import_module("personal_codex_agent.codex_runtime")
    yield module
    sys.modules.pop("personal_codex_agent.codex_runtime", None)


class SlowThread:
    async def run(self, prompt: str):
        await asyncio.sleep(1)
        return types.SimpleNamespace(final_response=f"late: {prompt}")


class EchoThread:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def run(self, prompt: str):
        self.prompts.append(prompt)
        return types.SimpleNamespace(final_response=f"echo: {prompt}")


class FakeHarness:
    async def enhance_prompt(self, prompt: str) -> str:
        return f"CGI::{prompt}"


@pytest.mark.asyncio
async def test_runtime_run_times_out_and_releases_chat_lock(runtime_module, tmp_path):
    runtime = runtime_module.CodexRuntime(
        model="gpt-test",
        sandbox_name="workspace_write",
        workdir=tmp_path,
        timeout_seconds=0.01,
    )
    runtime._codex = object()
    runtime._sessions[123] = runtime_module.ChatSession(thread=SlowThread(), lock=asyncio.Lock())

    with pytest.raises(TimeoutError, match="timed out"):
        await runtime.run(123, "hello")

    assert not runtime._sessions[123].lock.locked()


@pytest.mark.asyncio
async def test_runtime_logs_lifecycle_events(runtime_module, tmp_path, caplog: pytest.LogCaptureFixture):
    runtime = runtime_module.CodexRuntime(
        model="gpt-test",
        sandbox_name="workspace_write",
        workdir=tmp_path,
        timeout_seconds=30,
    )

    with caplog.at_level(logging.INFO, logger="personal_codex_agent.codex_runtime"):
        await runtime.start()
        await runtime.reset_chat(123)
        await runtime.stop()

    messages = [record.message for record in caplog.records]
    assert messages == ["codex_runtime_started", "codex_chat_reset", "codex_runtime_stopped"]
    started = caplog.records[0]
    assert started.model == "gpt-test"
    assert started.sandbox == "workspace_write"
    assert started.workdir == str(tmp_path)
    reset = caplog.records[1]
    assert reset.chat_id == 123


@pytest.mark.asyncio
async def test_runtime_can_fallback_to_codex_cli_when_sdk_thread_fails(runtime_module, tmp_path, monkeypatch):
    class BrokenCodex:
        async def thread_start(self, **kwargs):
            raise RuntimeError("sdk unavailable")

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return (b"cli answer", b"")

    calls = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    runtime = runtime_module.CodexRuntime(
        model="gpt-test",
        sandbox_name="workspace_write",
        workdir=tmp_path,
        timeout_seconds=30,
        fallback_to_cli=True,
    )
    runtime._codex = BrokenCodex()

    answer = await runtime.run(123, "hello")

    assert answer == "cli answer"
    assert calls[0][0][:2] == ("codex", "exec")
    assert "hello" in calls[0][0]


@pytest.mark.asyncio
async def test_runtime_enhances_prompt_with_cgi_harness_before_codex_run(runtime_module, tmp_path):
    thread = EchoThread()
    runtime = runtime_module.CodexRuntime(
        model="gpt-test",
        sandbox_name="workspace_write",
        workdir=tmp_path,
        timeout_seconds=30,
        cgi_harness=FakeHarness(),
    )
    runtime._codex = object()
    runtime._sessions[123] = runtime_module.ChatSession(thread=thread, lock=asyncio.Lock())

    answer = await runtime.run(123, "hello")

    assert thread.prompts == ["CGI::hello"]
    assert answer == "echo: CGI::hello"

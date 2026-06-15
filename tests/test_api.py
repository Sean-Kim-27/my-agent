from __future__ import annotations

from fastapi.testclient import TestClient

from personal_codex_agent.api import create_app, create_codex_runtime_from_env


class FakeCodexRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def run(self, chat_id: int, prompt: str) -> str:
        self.calls.append((chat_id, prompt))
        return "Codex 최종 답변"


def test_chat_endpoint_returns_codex_result_only() -> None:
    runtime = FakeCodexRuntime()
    client = TestClient(create_app(runtime))

    response = client.post("/api/chat", json={"message": "안녕", "chat_id": 42})

    assert response.status_code == 200
    assert response.text == "Codex 최종 답변"
    assert response.headers["content-type"].startswith("text/plain")
    assert runtime.calls == [(42, "안녕")]


def test_chat_endpoint_uses_default_chat_id_for_stateless_clients() -> None:
    runtime = FakeCodexRuntime()
    client = TestClient(create_app(runtime))

    response = client.post("/api/chat", json={"message": "상태 없는 호출"})

    assert response.status_code == 200
    assert runtime.calls == [(0, "상태 없는 호출")]


def test_create_codex_runtime_from_env_wires_cgi_harness(monkeypatch, tmp_path) -> None:
    created = {}

    class FakeCGIHarness:
        def __init__(self, **kwargs):
            created["harness"] = kwargs

    class FakeCodexRuntime:
        def __init__(self, **kwargs):
            created["runtime"] = kwargs

    monkeypatch.setattr("personal_codex_agent.api.CGIHarness", FakeCGIHarness)
    monkeypatch.setattr("personal_codex_agent.api.CodexRuntime", FakeCodexRuntime)
    monkeypatch.setenv("CODEX_MODEL", "gpt-5.5")
    monkeypatch.setenv("CODEX_WORKDIR", str(tmp_path))
    monkeypatch.setenv("CGI_HARNESS_ENABLED", "true")
    monkeypatch.setenv("CGI_HARNESS_ENDPOINT", "http://127.0.0.1:8000/api/chat")

    runtime = create_codex_runtime_from_env()

    assert runtime is not None
    assert created["harness"]["endpoint"] == "http://127.0.0.1:8000/api/chat"
    assert created["runtime"]["model"] == "gpt-5.5"
    assert created["runtime"]["cgi_harness"] is not None

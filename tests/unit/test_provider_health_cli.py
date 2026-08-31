"""Provider health-check CLI coverage for Phase 2."""

from __future__ import annotations

from typing import Any

from agent_framework.config.settings import Settings
from agent_framework.main import check_provider_health, print_provider_status


class FakeProvider:
    def __init__(self, healthy: bool) -> None:
        self.healthy = healthy

    async def health_check(self) -> bool:
        return self.healthy


async def test_check_provider_health_returns_each_supported_provider(monkeypatch: Any) -> None:
    def fake_factory(
        settings: Settings,
        provider_name: str,
        **kwargs: Any,
    ) -> FakeProvider:
        return FakeProvider(provider_name != "anthropic")

    monkeypatch.setattr("agent_framework.main.create_llm_provider", fake_factory)

    result = await check_provider_health(Settings())

    assert result == {
        "openai": True,
        "anthropic": False,
        "nvidia_nim": True,
        "openai_compatible": True,
        "codex": True,
    }


def test_print_provider_status_includes_health(capsys: Any) -> None:
    health = {
        "openai": True,
        "anthropic": False,
        "nvidia_nim": True,
        "openai_compatible": True,
        "codex": False,
    }

    print_provider_status(Settings(), health)

    output = capsys.readouterr().out
    assert "Health         : healthy" in output
    assert "Health         : unhealthy" in output


def test_print_provider_status_masks_credentials_embedded_in_url(capsys: Any) -> None:
    settings = Settings(
        openai_base_url="https://user:password@example.test/v1?api_key=supersecret"
    )

    print_provider_status(settings)

    output = capsys.readouterr().out
    assert "user:password" not in output
    assert "supersecret" not in output
    assert "MASKED" in output

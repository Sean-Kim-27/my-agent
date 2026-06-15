from __future__ import annotations

from personal_codex_agent.persona import build_prompt, list_modes, resolve_mode


def test_resolve_mode_defaults_unknown_to_default() -> None:
    assert resolve_mode("missing").name == "default"


def test_list_modes_includes_expected_presets() -> None:
    assert list_modes() == ["default", "dev", "research"]


def test_build_prompt_prefixes_mode_instruction() -> None:
    prompt = build_prompt("dev", "fix the tests")

    assert "소프트웨어 개발 모드" in prompt
    assert prompt.endswith("fix the tests")

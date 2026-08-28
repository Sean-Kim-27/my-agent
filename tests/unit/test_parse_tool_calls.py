"""Tests confirming ToolCall normalization contract across providers."""

from __future__ import annotations

from types import SimpleNamespace

from agent_framework.llm.anthropic_provider import AnthropicProvider
from agent_framework.llm.openai_compatible import OpenAICompatibleProvider


def _fake_openai_message() -> SimpleNamespace:
    return SimpleNamespace(
        tool_calls=[
            SimpleNamespace(
                id="call_1",
                function=SimpleNamespace(name="search", arguments='{"q": "hi"}'),
            ),
            SimpleNamespace(
                id="call_2",
                function=SimpleNamespace(name="lookup", arguments="not-json"),
            ),
        ]
    )


def test_openai_compatible_parse_tool_calls_normalizes_openai_message() -> None:
    provider = OpenAICompatibleProvider(api_key_hint="x") if False else OpenAICompatibleProvider()
    tool_calls = provider._parse_tool_calls(_fake_openai_message())
    assert [tc.name for tc in tool_calls] == ["search", "lookup"]
    assert tool_calls[0].arguments == {"q": "hi"}
    assert tool_calls[1].arguments == "not-json"  # fallback when JSON parse fails


def test_openai_compatible_parse_tool_calls_handles_no_tool_calls() -> None:
    provider = OpenAICompatibleProvider()
    assert provider._parse_tool_calls(SimpleNamespace(tool_calls=None)) == []
    assert provider._parse_tool_calls(SimpleNamespace()) == []


def test_anthropic_parse_tool_calls_normalizes_content_blocks() -> None:
    provider = AnthropicProvider(api_key="fake")
    raw = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="thinking..."),
            SimpleNamespace(
                type="tool_use",
                id="toolu_1",
                name="lookup",
                input={"city": "Seoul"},
            ),
        ]
    )
    tool_calls = provider._parse_tool_calls(raw)
    assert len(tool_calls) == 1
    assert tool_calls[0].id == "toolu_1"
    assert tool_calls[0].name == "lookup"
    assert tool_calls[0].arguments == {"city": "Seoul"}


def test_anthropic_parse_tool_calls_ignores_invalid_input_type() -> None:
    provider = AnthropicProvider(api_key="fake")
    raw = SimpleNamespace(
        content=[
            SimpleNamespace(type="tool_use", id="t1", name="broken", input="not-a-dict"),
        ]
    )
    tool_calls = provider._parse_tool_calls(raw)
    assert tool_calls[0].arguments == {}

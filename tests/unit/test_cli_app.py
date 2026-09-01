"""CLI parser, output contract, and compatibility smoke tests."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agent_framework.cli.app import build_parser, run


def test_version_human_output(capsys: Any) -> None:
    assert run(["version"]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("myagen ")
    assert captured.err == ""


def test_version_json_output_is_versioned(capsys: Any) -> None:
    assert run(["--json", "version"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["ok"] is True
    assert "package_version" in payload["data"]


def test_unknown_command_uses_argparse_usage_exit_code(capsys: Any) -> None:
    with pytest.raises(SystemExit) as caught:
        run(["does-not-exist"])
    assert caught.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_session_parser_default_is_none() -> None:
    args = build_parser().parse_args(["chat"])
    assert args.session is None


def test_unicode_session_and_prompt_parse() -> None:
    args = build_parser().parse_args(["chat", "--session", "작업:한글"])
    assert args.session == "작업:한글"

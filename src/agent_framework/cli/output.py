"""stdout/stderr and JSON response contracts for the CLI."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, TextIO

from agent_framework.logging.logger import mask_secrets, redact_sensitive_data


@dataclass
class OutputWriter:
    """Keep command results on stdout and diagnostics on stderr."""

    json_mode: bool = False
    stdout: TextIO = field(default_factory=lambda: sys.stdout)
    stderr: TextIO = field(default_factory=lambda: sys.stderr)

    def success(self, data: Any = None, *, text: str | None = None) -> None:
        if self.json_mode:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "ok": True,
                        "data": redact_sensitive_data(data),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                file=self.stdout,
            )
            return
        if text is not None:
            print(mask_secrets(text), file=self.stdout)

    def error(self, code: str, message: str, *, hint: str | None = None) -> None:
        safe_message = mask_secrets(message)
        safe_hint = mask_secrets(hint) if hint else None
        if self.json_mode:
            payload: dict[str, Any] = {
                "schema_version": 1,
                "ok": False,
                "error": {"code": code, "message": safe_message},
            }
            if safe_hint:
                payload["error"]["hint"] = safe_hint
            print(json.dumps(payload, ensure_ascii=False), file=self.stderr)
            return
        print(f"Error [{code}]: {safe_message}", file=self.stderr)
        if safe_hint:
            print(f"Hint: {safe_hint}", file=self.stderr)

    def diagnostic(self, message: str) -> None:
        print(mask_secrets(message), file=self.stderr)


__all__ = ["OutputWriter"]

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from dataclasses import dataclass


class CGIHarnessError(RuntimeError):
    """Raised when the external CGI harness endpoint cannot produce a report."""


@dataclass(frozen=True)
class CGIHarness:
    """Client for the Cosmic Graph Intelligence compare/report harness.

    The CGI project under ``~/CGI/CGI_Cosmic_Graph_Intelligence`` exposes
    ``POST /api/compare/report`` and returns a markdown report.  This adapter
    keeps that FastAPI implementation out of the Telegram layer and turns the
    report into bounded Codex prompt context.
    """

    endpoint: str
    mode: str = "balanced"
    timeout_seconds: float = 60.0
    max_report_chars: int = 8000

    async def generate_report(self, prompt: str) -> str:
        return await asyncio.to_thread(self._generate_report_sync, prompt)

    async def enhance_prompt(self, prompt: str) -> str:
        report = await self.generate_report(prompt)
        bounded_report = report[: self.max_report_chars]
        return (
            "Use the following Cosmic Graph Intelligence harness report as "
            "additional reasoning context. Do not quote it verbatim unless useful; "
            "use it to improve structure, creativity, and coverage.\n\n"
            "<Cosmic Graph Intelligence Harness Report>\n"
            f"{bounded_report}\n"
            "</Cosmic Graph Intelligence Harness Report>\n\n"
            "Original user request:\n"
            f"{prompt}"
        )

    def _generate_report_sync(self, prompt: str) -> str:
        payload = json.dumps(
            {"question": prompt, "mode": self.mode},
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8", "replace")
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            raise CGIHarnessError(f"CGI harness request failed: {exc}") from exc

        if not body.strip():
            raise CGIHarnessError("CGI harness returned an empty report")
        return body.strip()

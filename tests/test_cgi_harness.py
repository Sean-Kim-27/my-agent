from __future__ import annotations

import json
import urllib.error

import pytest

from personal_codex_agent.cgi_harness import CGIHarness, CGIHarnessError


@pytest.mark.asyncio
async def test_cgi_harness_posts_question_to_compare_report_endpoint(monkeypatch):
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return "# CGI 리포트\n강화 컨텍스트".encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    harness = CGIHarness(
        endpoint="http://127.0.0.1:8000/api/compare/report",
        mode="creative",
        timeout_seconds=12.5,
        max_report_chars=1000,
    )

    report = await harness.generate_report("질문")

    assert report == "# CGI 리포트\n강화 컨텍스트"
    request, timeout = calls[0]
    assert request.full_url == "http://127.0.0.1:8000/api/compare/report"
    assert timeout == 12.5
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data.decode("utf-8")) == {"question": "질문", "mode": "creative"}


@pytest.mark.asyncio
async def test_cgi_harness_wraps_prompt_with_bounded_report(monkeypatch):
    long_report = "가" * 20

    async def fake_generate_report(self, prompt):
        return long_report

    monkeypatch.setattr(CGIHarness, "generate_report", fake_generate_report)
    harness = CGIHarness(
        endpoint="http://127.0.0.1:8000/api/compare/report",
        mode="balanced",
        timeout_seconds=30,
        max_report_chars=8,
    )

    enhanced = await harness.enhance_prompt("원본 질문")

    assert "원본 질문" in enhanced
    assert "가" * 8 in enhanced
    assert "가" * 9 not in enhanced
    assert "Cosmic Graph Intelligence" in enhanced


@pytest.mark.asyncio
async def test_cgi_harness_raises_clear_error_on_endpoint_failure(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    harness = CGIHarness(
        endpoint="http://127.0.0.1:8000/api/compare/report",
        mode="balanced",
        timeout_seconds=1,
        max_report_chars=1000,
    )

    with pytest.raises(CGIHarnessError, match="CGI harness request failed"):
        await harness.generate_report("질문")

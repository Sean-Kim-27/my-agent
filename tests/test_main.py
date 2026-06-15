from __future__ import annotations

import pytest

from personal_codex_agent.__main__ import shutdown_application


class FakeUpdater:
    def __init__(self, running: bool) -> None:
        self.running = running
        self.stop_calls = 0

    async def stop(self) -> None:
        self.stop_calls += 1
        if not self.running:
            raise RuntimeError("This Updater is not running!")
        self.running = False


class FakeApplication:
    def __init__(self, updater_running: bool, running: bool = True) -> None:
        self.updater = FakeUpdater(updater_running)
        self.running = running
        self.stop_calls = 0
        self.shutdown_calls = 0

    async def stop(self) -> None:
        self.stop_calls += 1
        if not self.running:
            raise RuntimeError("This Application is not running!")
        self.running = False

    async def shutdown(self) -> None:
        self.shutdown_calls += 1


@pytest.mark.asyncio
async def test_shutdown_application_skips_updater_stop_when_not_running() -> None:
    app = FakeApplication(updater_running=False)

    await shutdown_application(app)

    assert app.updater.stop_calls == 0
    assert app.stop_calls == 1
    assert app.shutdown_calls == 1


@pytest.mark.asyncio
async def test_shutdown_application_stops_running_updater() -> None:
    app = FakeApplication(updater_running=True)

    await shutdown_application(app)

    assert app.updater.stop_calls == 1
    assert app.stop_calls == 1
    assert app.shutdown_calls == 1


@pytest.mark.asyncio
async def test_shutdown_application_skips_app_stop_when_not_running() -> None:
    app = FakeApplication(updater_running=False, running=False)

    await shutdown_application(app)

    assert app.updater.stop_calls == 0
    assert app.stop_calls == 0
    assert app.shutdown_calls == 1

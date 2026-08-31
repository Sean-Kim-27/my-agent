"""Agent run state machine primitives.

This module defines the explicit lifecycle states of an :class:`Agent` run and
the :class:`RunContext` object that travels with it. Introduced by Phase 1 of
the master plan, these primitives make the execution loop of
:meth:`Agent.run_with_trace` observable, cancellable, and terminatable in
exactly one of ``completed``, ``failed`` or ``cancelled``.

The public surface is intentionally small:

* :class:`RunState` — the finite lifecycle states.
* :class:`RunContext` — a per-run handle carrying ``run_id``, timeout,
  cancellation event and the current state.

Callers that want to cancel an in-flight run construct a ``RunContext`` up
front, hand it to :meth:`Agent.run_with_trace` and call :meth:`RunContext.cancel`
from any coroutine. The agent honors the cancellation between steps and while
awaiting the LLM provider or tool executor.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class RunState(StrEnum):
    """Finite lifecycle states of an :class:`Agent` run.

    A run always begins in :attr:`PENDING`, transitions to :attr:`RUNNING` when
    the loop starts, and terminates in exactly one of :attr:`COMPLETED`,
    :attr:`FAILED` or :attr:`CANCELLED`. The string values are chosen so the
    enum serializes cleanly in Pydantic models and structured logs.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Return True if this state cannot legally transition further."""
        return self in (RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED)


@dataclass
class RunContext:
    """Handle representing a single agent execution.

    ``RunContext`` is the source of truth for a run's identity, timing budget
    and cancellation signal. The :class:`Agent` mutates :attr:`state` as it
    progresses and honors :meth:`cancel` at every await boundary between steps.

    Attributes:
        run_id: Opaque identifier used to correlate logs, callbacks and traces.
        session_id: Conversation session this run belongs to.
        timeout_seconds: Optional wall-clock budget for the entire run.
        started_at: Monotonic clock at which the run began. ``0.0`` until the
            agent transitions the run into :attr:`RunState.RUNNING`.
        state: Current lifecycle state.
    """

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    session_id: str = ""
    timeout_seconds: float | None = None
    started_at: float = 0.0
    state: RunState = RunState.PENDING
    _cancel_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    @classmethod
    def create(
        cls,
        session_id: str,
        *,
        timeout_seconds: float | None = None,
        run_id: str | None = None,
    ) -> RunContext:
        """Construct a fresh :class:`RunContext` for ``session_id``."""
        return cls(
            run_id=run_id or uuid.uuid4().hex,
            session_id=session_id,
            timeout_seconds=timeout_seconds,
        )

    def mark_running(self) -> None:
        """Transition into :attr:`RunState.RUNNING` and stamp ``started_at``."""
        self.started_at = time.perf_counter()
        self.state = RunState.RUNNING

    def cancel(self) -> None:
        """Request cancellation. Idempotent; safe to call from any task."""
        self._cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        """Return True once :meth:`cancel` has been called."""
        return self._cancel_event.is_set()

    def raise_if_cancelled(self) -> None:
        """Raise :class:`asyncio.CancelledError` if cancellation was requested."""
        if self._cancel_event.is_set():
            raise asyncio.CancelledError("Agent run cancelled via RunContext")

    async def wait_cancelled(self) -> None:
        """Await cancellation. Useful for composing with ``asyncio.wait``."""
        await self._cancel_event.wait()


__all__ = ["RunContext", "RunState"]

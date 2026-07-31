"""
Abstract base agent for the Omniroute multi-agent system.

Provides a standard lifecycle and state management interface that
all specialized agents follow.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from omniroute.logging_setup import get_logger


@dataclass
class AgentContext:
    """Context provided to an agent when it runs."""

    run_id: str = ""
    dry_run: bool = True
    force: bool = False
    timeout_seconds: float | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Result returned by an agent after execution."""

    success: bool
    agent_name: str
    summary: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_seconds: float = 0.0


class BaseAgent(ABC):
    """Abstract base class for all Omniroute agents.

    Each agent follows a standard lifecycle:
        init → validate → execute → finalize

    Subclasses must implement ``agent_name``, ``execute()``, and
    optionally override ``validate()``.
    """

    def __init__(self, context: AgentContext | None = None) -> None:
        self.context = context or AgentContext()
        self.log = get_logger(f"omniroute.agent.{self.agent_name}")
        self._start_time: datetime | None = None
        self._end_time: datetime | None = None

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Human-readable agent name (e.g. 'lead_hunter')."""
        ...

    # ── Lifecycle ───────────────────────────────────────────────────────

    def validate(self) -> bool:
        """Validate that the agent can run.

        Override to check preconditions. Default returns True.

        Returns:
            True if preconditions are met.
        """
        return True

    @abstractmethod
    def execute(self) -> AgentResult:
        """Execute the agent's primary logic.

        Returns:
            AgentResult with execution outcome.
        """
        ...

    def finalize(self, result: AgentResult) -> None:
        """Cleanup after execution. Override if needed.

        Args:
            result: The result from execute().
        """
        pass

    # ── Runner ──────────────────────────────────────────────────────────

    def run(self) -> AgentResult:
        """Run the full agent lifecycle.

        Returns:
            AgentResult with execution outcome.
        """
        self._start_time = datetime.now(timezone.utc)
        self.log.info(
            "Agent %s starting (dry_run=%s)",
            self.agent_name,
            self.context.dry_run,
        )

        try:
            valid = self.validate()
        except Exception as exc:
            self.log.exception("Agent %s validate() raised: %s", self.agent_name, exc)
            valid = False

        if not valid:
            self._end_time = datetime.now(timezone.utc)
            self.log.error("Agent %s validation failed", self.agent_name)
            return AgentResult(
                success=False,
                agent_name=self.agent_name,
                error="Validation failed",
                duration_seconds=(self._end_time - self._start_time).total_seconds(),
            )

        timeout = self.context.timeout_seconds
        if timeout and timeout > 0:
            result = self._execute_with_timeout(timeout)
        else:
            result = self._execute_guarded()

        self._end_time = datetime.now(timezone.utc)
        result.duration_seconds = (
            self._end_time - self._start_time
        ).total_seconds()

        try:
            self.finalize(result)
        except Exception as exc:
            self.log.exception("Agent %s finalize error: %s", self.agent_name, exc)

        status = "succeeded" if result.success else "failed"
        self.log.info(
            "Agent %s %s in %.1fs",
            self.agent_name,
            status,
            result.duration_seconds,
        )
        return result

    # ── Execution helpers ───────────────────────────────────────────────

    def _execute_guarded(self) -> AgentResult:
        """Run execute() with exception guarding."""
        try:
            return self.execute()
        except Exception as exc:
            self.log.exception("Agent %s crashed: %s", self.agent_name, exc)
            return AgentResult(
                success=False,
                agent_name=self.agent_name,
                error=str(exc),
            )

    def _execute_with_timeout(self, timeout: float) -> AgentResult:
        """Run execute() in a watchdog thread, failing the run if it overruns.

        A hung execute() cannot stall the pipeline forever — after ``timeout``
        seconds the run is marked failed and the agent lifecycle completes.
        The daemon thread is left to finish (and be reaped) in the background.
        """
        import threading

        box: dict[str, AgentResult | Exception | None] = {"result": None}

        def _target() -> None:
            try:
                box["result"] = self.execute()
            except Exception as exc:  # pragma: no cover - surfaced via timed-out path
                box["result"] = exc

        thread = threading.Thread(target=_target, daemon=True, name=f"{self.agent_name}-exec")
        thread.start()
        thread.join(timeout=timeout)

        value = box["result"]
        if value is None:
            self.log.error(
                "Agent %s timed out after %.1fs", self.agent_name, timeout
            )
            return AgentResult(
                success=False,
                agent_name=self.agent_name,
                error=f"Timed out after {timeout:.0f}s",
            )
        if isinstance(value, Exception):
            self.log.exception("Agent %s crashed: %s", self.agent_name, value)
            return AgentResult(
                success=False,
                agent_name=self.agent_name,
                error=str(value),
            )
        return value

    # ── Convenience ─────────────────────────────────────────────────────

    @property
    def is_dry_run(self) -> bool:
        """Whether this agent is running in dry-run mode."""
        return self.context.dry_run

    @property
    def run_id(self) -> str:
        """The current run ID."""
        return self.context.run_id

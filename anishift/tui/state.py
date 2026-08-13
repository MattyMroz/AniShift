"""Presentation-only state owned by one Textual session."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic


@dataclass(slots=True)
class SessionState:
    """Small mutable view state without product or planner decisions."""

    workspace_label: str
    route: str = "workspace"
    mode: str = "auto"
    preset: str = "default"
    run_state: str = "idle"
    active_run_id: str | None = None
    generation: int = 0
    _started_at: float | None = None
    _clock: Callable[[], float] = monotonic

    @property
    def elapsed_seconds(self) -> int:
        """Return elapsed whole seconds only while a run is active."""
        if self._started_at is None:
            return 0
        return max(0, int(self._clock() - self._started_at))

    def select(self, *, mode: str, preset: str) -> None:
        """Update the footer selection without changing workflow state."""
        self.mode = mode
        self.preset = preset

    def begin_run(self) -> int:
        """Start a new UI generation and return its identity."""
        self.generation += 1
        self.run_state = "running"
        self.active_run_id = None
        self._started_at = self._clock()
        return self.generation

    def finish_run(self, state: str) -> None:
        """Stop elapsed time and retain the terminal run state."""
        self.run_state = state
        self.active_run_id = None
        self._started_at = None

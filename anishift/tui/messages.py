"""Typed Textual messages crossing presentation component boundaries."""

from __future__ import annotations

from textual.message import Message

from anishift.application.events import RunEvent
from anishift.application.results import RunResult


class CommandSubmitted(Message):
    """Raw command text submitted by the persistent input."""

    def __init__(self, value: str) -> None:
        super().__init__()
        self.value: str = value


class RunEventsReceived(Message):
    """One UI-thread batch drained from the worker event buffer."""

    def __init__(self, generation: int, events: tuple[RunEvent, ...]) -> None:
        super().__init__()
        self.generation: int = generation
        self.events: tuple[RunEvent, ...] = events


class RunCompleted(Message):
    """Terminal result returned by the application worker."""

    def __init__(self, generation: int, result: RunResult) -> None:
        super().__init__()
        self.generation: int = generation
        self.result: RunResult = result

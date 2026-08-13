"""Typed Textual messages crossing presentation component boundaries."""

from __future__ import annotations

from textual.message import Message

from anishift.application.events import RunEvent
from anishift.application.inspection import InspectedSourceGroup, InspectedWorkspace
from anishift.application.intents import ExternalAudioRole
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


class WorkspaceInspected(Message):
    """Completed inspection result tagged with its request generation."""

    def __init__(self, generation: int, workspace: InspectedWorkspace) -> None:
        super().__init__()
        self.generation: int = generation
        self.workspace: InspectedWorkspace = workspace


class WorkspaceInspectionFailed(Message):
    """Sanitized inspection failure tagged with its request generation."""

    def __init__(self, generation: int, error: str) -> None:
        super().__init__()
        self.generation: int = generation
        self.error: str = error


class ExternalArtifactRegistered(Message):
    """Validated external artifact result for one manual draft generation."""

    def __init__(
        self,
        generation: int,
        group: InspectedSourceGroup,
        artifact_id: str,
        *,
        audio_role: ExternalAudioRole | None,
    ) -> None:
        super().__init__()
        self.generation: int = generation
        self.group: InspectedSourceGroup = group
        self.artifact_id: str = artifact_id
        self.audio_role: ExternalAudioRole | None = audio_role


class ExternalArtifactFailed(Message):
    """Sanitized external validation failure for one generation."""

    def __init__(self, generation: int, error: str) -> None:
        super().__init__()
        self.generation: int = generation
        self.error: str = error

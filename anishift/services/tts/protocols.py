"""Protocols exposed by the TTS domain."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from anishift.services._base import EngineInfo

if TYPE_CHECKING:
    from pathlib import Path

    from anishift.services.tts.types import (
        ClipExpectation,
        ClipValidation,
        EngineAvailability,
        EngineCapabilities,
        EngineClipResult,
        SynthesisRequest,
        VoiceInfo,
    )

__all__ = ["CancellationToken", "ClipValidator", "TtsEngine"]


@runtime_checkable
class ClipValidator(Protocol):
    """Decode-check one provider-native clip without owning its lifecycle."""

    def validate_clip(
        self,
        path: Path,
        expectation: ClipExpectation,
    ) -> ClipValidation | None:
        """Return trusted technical metadata or ``None`` for an invalid clip."""
        ...


@runtime_checkable
class CancellationToken(Protocol):
    """Cooperative cancellation and late-result commit permission."""

    @property
    def is_cancelled(self) -> bool:
        """Whether cancellation has been requested."""
        ...

    @property
    def generation(self) -> int:
        """Generation captured when the current run started."""
        ...

    async def wait(self) -> None:
        """Wait until cancellation is requested."""
        ...

    def can_commit(self, generation: int) -> bool:
        """Return whether a result from the generation may still be committed."""
        ...


@runtime_checkable
class TtsEngine(EngineInfo, Protocol):
    """Asynchronous provider contract owned by the synchronous TTS facade."""

    @property
    def is_available(self) -> bool:
        """Return the cached cheap projection of detailed availability."""
        ...

    @property
    def capabilities(self) -> EngineCapabilities:
        """Return static capabilities without performing network I/O."""
        ...

    async def availability(self, *, live: bool = False) -> EngineAvailability:
        """Return a detailed cached or live availability result."""
        ...

    async def list_voices(self) -> tuple[VoiceInfo, ...]:
        """Return voices currently available to this engine."""
        ...

    async def synthesize(
        self,
        request: SynthesisRequest,
        *,
        cancel: CancellationToken,
    ) -> EngineClipResult:
        """Synthesize one validated request without applying shared retry."""
        ...

    async def close(self) -> None:
        """Release provider resources."""
        ...

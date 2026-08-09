"""Public neutral media-probe boundary and default format dispatcher."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from anishift.application.cancellation import CancellationToken
from anishift.errors import ErrorCode, ErrorContext, UnsupportedMediaError
from anishift.services.media._process import ProcessRunner
from anishift.services.media.mkv import identify_mkv
from anishift.services.media.mp4 import identify_mp4
from anishift.services.media.types import MediaCatalog


class MediaProbe(Protocol):
    """Neutral identification boundary used by workspace inspection."""

    def identify(
        self,
        path: Path,
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> MediaCatalog:
        """Identify a supported container without extracting any tracks."""
        ...


class DefaultMediaProbe:
    """Dispatch MKV and MP4 identification to their controlled adapters."""

    def __init__(self, *, runner: ProcessRunner | None = None) -> None:
        self._runner: ProcessRunner | None = runner

    def identify(
        self,
        path: Path,
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> MediaCatalog:
        """Identify one container through the adapter selected by its suffix."""
        match path.suffix.casefold():
            case ".mkv":
                return identify_mkv(path, cancel=cancel, timeout_s=timeout_s, runner=self._runner)
            case ".mp4":
                return identify_mp4(path, cancel=cancel, timeout_s=timeout_s, runner=self._runner)
            case _:
                raise UnsupportedMediaError(
                    context=ErrorContext(
                        code=ErrorCode.MEDIA_UNSUPPORTED,
                        message=f"Unsupported media container: {path.name}",
                        suggestion="Use an MKV or MP4 source file.",
                        details={"suffix": path.suffix.casefold()},
                    )
                )

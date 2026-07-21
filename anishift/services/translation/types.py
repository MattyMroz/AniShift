"""Translation domain value types.

Plain ``slots=True`` dataclasses (no pydantic) so the facade can run in the
pipeline hot loop. Validation belongs at the API/settings boundary.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BatchedLine:
    """One line result from an engine batch, with a success flag.

    Attributes:
        text: Translated text, or the source text when the line failed.
        ok: ``False`` when the line was padded with its source on failure.
    """

    text: str
    ok: bool = True


@dataclass(frozen=True, slots=True)
class TranslatedLine:
    """One translated spoken line: source paired with its Polish rendering.

    Attributes:
        start: Start time in ms, copied from the source SpokenLine.
        end: End time in ms, copied from the source SpokenLine.
        source_text: Original single-line text fed to the provider.
        text: Translated single-line text (for the narrator / TTS).
        lines: Translated text re-split into on-screen verses (for displayed
            subtitles). For spoken lines this is ``(text,)``.
        style: Style name copied from the source SpokenLine.
        ok: ``False`` when translation failed and text fell back to source.
    """

    start: int
    end: int
    source_text: str
    text: str
    lines: tuple[str, ...]
    style: str
    ok: bool = True


@dataclass(slots=True)
class FileTranslation:
    """Result of translating one file's spoken + displayed streams.

    Attributes:
        spoken: Translated narrator lines, in input order.
        displayed: Translated visible-texts of displayed events, in event order.
        engine_id: Id of the engine that actually produced the result (after any
            fallback).
        target_lang: Target language code.
        unique_lines: Distinct lines after deduplication.
        total_lines: All lines before deduplication.
        api_calls: ``translate_batch`` calls the facade issued (max 2), not the
            raw HTTP request count.
        failed_lines: Lines that fell back to source (partial failure).
        error: Set only on a hard failure of the whole file (fallback chain
            exhausted); the file is then reported failed.
    """

    spoken: tuple[TranslatedLine, ...] = ()
    displayed: tuple[str, ...] = ()
    engine_id: str = ""
    target_lang: str = "pl"
    unique_lines: int = 0
    total_lines: int = 0
    api_calls: int = 0
    failed_lines: int = 0
    error: str | None = None

    @property
    def is_success(self) -> bool:
        """True when the file translated without a hard error."""
        return self.error is None


__all__ = ["BatchedLine", "FileTranslation", "TranslatedLine"]

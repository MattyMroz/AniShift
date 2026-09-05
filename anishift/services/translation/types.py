"""Translation domain value types."""

from __future__ import annotations

from dataclasses import dataclass

from anishift.errors import ErrorContext


@dataclass(frozen=True, slots=True)
class BatchedLine:
    """One line result from an engine batch, with a success flag."""

    text: str
    ok: bool = True


@dataclass(frozen=True, slots=True)
class TranslatedLine:
    """One translated spoken line: source paired with its Polish rendering."""

    start: int
    end: int
    source_text: str
    text: str
    lines: tuple[str, ...]
    style: str
    ok: bool = True


@dataclass(slots=True)
class FileTranslation:
    """Result of translating one file's spoken + displayed streams."""

    spoken: tuple[TranslatedLine, ...] = ()
    displayed: tuple[str, ...] = ()
    engine_id: str = ""
    target_lang: str = "pl"
    unique_lines: int = 0
    total_lines: int = 0
    api_calls: int = 0
    failed_lines: int = 0
    error: str | None = None
    error_context: ErrorContext | None = None

    @property
    def is_success(self) -> bool:
        """True when the file translated without a hard error."""
        return self.error is None


__all__ = ["BatchedLine", "FileTranslation", "TranslatedLine"]

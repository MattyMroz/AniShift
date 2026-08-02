"""Pipeline-owned mapping from subtitle state to neutral TTS batches."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Never

from anishift.errors import ErrorCode, ErrorContext, FatalError
from anishift.services.tts import SpeechBatch, SpeechRequest
from anishift.services.tts.validation import validate_speech_batch
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from anishift.services.subtitles.types import SpokenLine, SubtitleSplit
    from anishift.services.translation.types import FileTranslation, TranslatedLine

__all__ = [
    "NarrationBatch",
    "NarrationBuildError",
    "NarrationItem",
    "build_polish_narration",
    "build_translated_narration",
    "scope_id_for_source",
]

_IDENTITY_SCHEMA: Final[str] = "anishift-narration-v1"
"""Version separating narration identity algorithms."""

_IDENTITY_HEX_LENGTH: Final[int] = 24
"""Truncated SHA-256 length used in portable opaque ids."""

logger = get_logger(__name__)


class NarrationBuildError(FatalError):
    """Pipeline failure raised before an invalid batch reaches TTS."""


@dataclass(frozen=True, slots=True)
class NarrationItem:
    """One neutral request paired with pipeline-owned timing."""

    request: SpeechRequest
    start_ms: int
    end_ms: int
    source_order: int


@dataclass(frozen=True, slots=True)
class NarrationBatch:
    """Neutral TTS batch plus the timing retained by pipeline."""

    speech: SpeechBatch
    items: tuple[NarrationItem, ...]


def scope_id_for_source(source: Path, *, workspace_root: Path) -> str:
    """Build a short stable scope id from a workspace-relative source path."""
    try:
        relative: Path = source.resolve().relative_to(workspace_root.resolve())
    except ValueError:
        _raise_narration_error(
            "Narration source must be inside the configured workspace",
            code=ErrorCode.PIPELINE_STEP_FAILED,
            details={"source": source.name},
        )
    relative_identity: str = relative.as_posix()
    if os.name == "nt":
        relative_identity = relative_identity.casefold()
    identity: str = f"{_IDENTITY_SCHEMA}\0{relative_identity}"
    return f"scope-{_short_hash(identity)}"


def build_polish_narration(
    split: SubtitleSplit,
    *,
    scope_id: str,
    batch_rank: int,
) -> NarrationBatch:
    """Map already-Polish spoken state without reparsing a subtitle file."""
    return _build_narration(
        split.spoken,
        None,
        scope_id=scope_id,
        batch_rank=batch_rank,
    )


def build_translated_narration(
    split: SubtitleSplit,
    translation: FileTranslation,
    *,
    scope_id: str,
    batch_rank: int,
) -> NarrationBatch:
    """Map complete Polish translation while retaining source timing."""
    _validate_translation(split.spoken, translation)
    return _build_narration(
        split.spoken,
        translation.spoken,
        scope_id=scope_id,
        batch_rank=batch_rank,
    )


def _build_narration(
    sources: Sequence[SpokenLine],
    translations: Sequence[TranslatedLine] | None,
    *,
    scope_id: str,
    batch_rank: int,
) -> NarrationBatch:
    requests: list[SpeechRequest] = []
    items: list[NarrationItem] = []
    translated_texts: tuple[str, ...] = (
        tuple(line.text for line in translations) if translations is not None else tuple(line.text for line in sources)
    )
    for source, translated_text in zip(sources, translated_texts, strict=True):
        if source.end <= source.start:
            logger.warning(
                "Narration line skipped because its timing is not positive",
                scope_id=scope_id,
                source_order=source.order,
                start_ms=source.start,
                end_ms=source.end,
            )
            continue
        request_rank: int = len(requests)
        request_id: str = _request_id(scope_id, source)
        request = SpeechRequest(
            request_id=request_id,
            text=translated_text,
            request_rank=request_rank,
        )
        requests.append(request)
        items.append(
            NarrationItem(
                request=request,
                start_ms=source.start,
                end_ms=source.end,
                source_order=source.order,
            ),
        )
    speech = validate_speech_batch(
        SpeechBatch(
            scope_id=scope_id,
            batch_rank=batch_rank,
            requests=tuple(requests),
        ),
    )
    return NarrationBatch(speech=speech, items=tuple(items))


def _validate_translation(
    sources: Sequence[SpokenLine],
    translation: FileTranslation,
) -> None:
    if not translation.is_success or translation.target_lang != "pl":
        _raise_incomplete_translation()
    if len(sources) != len(translation.spoken):
        _raise_incomplete_translation()
    for source, translated in zip(sources, translation.spoken, strict=True):
        if (
            not translated.ok
            or translated.start != source.start
            or translated.end != source.end
            or translated.source_text != source.text
        ):
            _raise_incomplete_translation()


def _request_id(scope_id: str, source: SpokenLine) -> str:
    identity: str = f"{_IDENTITY_SCHEMA}\0{scope_id}\0{source.order}\0{source.start}\0{source.end}"
    return f"req-{_short_hash(identity)}"


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:_IDENTITY_HEX_LENGTH]


def _raise_incomplete_translation() -> Never:
    _raise_narration_error(
        "Translation is incomplete; narration was not queued",
        code=ErrorCode.TRANSLATION_FAILED,
        details={},
    )


def _raise_narration_error(
    message: str,
    *,
    code: ErrorCode,
    details: dict[str, object],
) -> Never:
    context: ErrorContext = ErrorContext(
        code=code,
        message=message,
        suggestion="Fix the subtitle or translation result before running TTS.",
        details=details,
    )
    raise NarrationBuildError(context=context)

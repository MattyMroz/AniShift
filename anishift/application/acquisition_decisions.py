"""Allowlisted, nonauthoritative evidence appended by the acquisition owner."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

from anishift.application.control_views import encode_view
from anishift.errors import AniShiftError
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from anishift.application.control import EpisodeAssignment
    from anishift.application.episode_selection import EpisodeOffer, RankedCandidate, StreamCandidate

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_TARGET_FIELDS: Final[tuple[str, ...]] = (
    "aliases",
    "type",
    "local_episode",
    "season",
    "episode",
    "absolute",
    "episode_title",
    "other_series",
    "other_episode_titles",
)
"""Exact runtime H1 target keys, excluding arbitrary catalogue metadata."""

_UNSAFE_TEXT: Final[re.Pattern[str]] = re.compile(r"(?:[a-z][a-z0-9+.-]*://|magnet:)", re.I)
"""URLs cannot enter local decision evidence."""

_ABSOLUTE_PATH: Final[re.Pattern[str]] = re.compile(r"^(?:[a-z]:[\\/]|[\\/])", re.I)
"""Rooted paths are refused only in evidence path fields."""

_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "source",
        "key",
        "target",
        "candidates",
        "suggestion",
        "episodes",
        "with_length",
        "error",
        "http_status",
        "command_id",
        "operation_id",
        "admission_id",
        "info_hash",
        "file_name",
        "verdict",
        "reason",
        "deviation_confirmed",
        "previous_admission_id",
        "conflict",
        "anilist_id",
        "number",
        "stream",
        "streams",
        "donghua",
        "identity",
        "traits",
        "quality",
        "confidence",
        "name",
        "file_index",
        "release",
        "path",
        "seeders",
        "size_text",
        "provider",
        "tags",
        "resolution",
        "polish",
        "polish_audio_beside_original",
        "english_subtitles",
        "subtitles_listed",
        "audio",
        "raw",
        "hardsub",
        "bluray",
        "platform",
        "dub_only",
        "supported",
        "subscription_id",
        "due_at",
        "aired_at",
        "result",
        "excluded",
        "mapping_source",
        "attempt",
        "attempt_result",
        "verification",
        "measured_s",
        "expected_s",
        "duration_source",
        "sources",
        "blocker",
        "numbering",
        "pack",
        "after_metadata",
        *_TARGET_FIELDS,
    }
)
"""Closed evidence fields at every nesting level; unknown transport data is refused."""


def _evidence(value: object, field: str = "") -> None:
    if isinstance(value, Mapping):
        if not value.keys() <= _FIELDS:
            msg = "Unknown decision evidence fields"
            raise ValueError(msg)
        for key, item in value.items():
            _evidence(item, key)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _evidence(item, field)
        return
    if value is None or type(value) in {int, float, bool}:
        return
    if (
        isinstance(value, str)
        and not _UNSAFE_TEXT.search(value)
        and (field not in {"path", "file_name"} or not _ABSOLUTE_PATH.match(value))
    ):
        return
    msg = "Decision evidence contains an unsupported or private value"
    raise ValueError(msg)


def target_view(target: Mapping[str, object]) -> dict[str, object]:
    """Project only the inputs understood by the frozen H1 target contract."""
    return {key: target[key] for key in _TARGET_FIELDS if key in target}


def stream_view(stream: StreamCandidate) -> dict[str, object]:
    """Retain replay inputs without magnets, trackers or transport metadata."""
    return {
        "info_hash": stream.info_hash,
        "name": stream.name,
        "file_index": stream.file_index,
        "file_name": stream.file_name,
        "release": stream.release,
        "path": stream.path,
        "seeders": stream.seeders,
        "size_text": stream.size_text,
        "provider": stream.provider,
        "tags": stream.tags,
    }


def offer_check(
    offer: EpisodeOffer, target: Mapping[str, object], streams: Sequence[StreamCandidate], *, donghua: bool
) -> dict[str, object]:
    """Record every ranking input, the resulting row order and the suggestion of one live source read."""
    return {
        "source": "torrentio",
        "key": encode_view(offer.key),
        "target": target_view(target),
        "donghua": donghua,
        "streams": [stream_view(stream) for stream in streams],
        "candidates": [_candidate_view(item) for item in offer.candidates],
        "suggestion": offer.suggestion,
    }


def source_error(source: str, anilist_id: int, number: int | None, error: BaseException) -> dict[str, object]:
    """Keep only a source error code and HTTP status, never its message or payload."""
    from anishift.application.episode_search import http_status  # noqa: PLC0415

    return {
        "source": source,
        "key": {"anilist_id": anilist_id, "number": number},
        "error": error.context.code.value if isinstance(error, AniShiftError) else type(error).__name__,
        "http_status": http_status(error),
    }


def admission_decision(assignment: EpisodeAssignment, operation_id: str) -> dict[str, object]:
    """Describe a durable admission and its explicit replacement relationship."""
    return {
        "operation_id": operation_id,
        "admission_id": assignment.admission_id,
        "key": {"anilist_id": assignment.choice.anilist_id, "number": assignment.choice.number},
        "info_hash": assignment.choice.reference.info_hash,
        "file_name": assignment.choice.reference.file_name,
        "target": target_view(assignment.choice.target),
        "verdict": assignment.choice.verdict.value,
        "reason": assignment.choice.reason,
        "deviation_confirmed": assignment.choice.deviation_confirmed,
        "previous_admission_id": assignment.previous_admission_id,
        "conflict": assignment.conflict,
    }


def candidate_proposal(candidate: RankedCandidate, target: Mapping[str, object]) -> dict[str, object]:
    """Describe the candidate a subscription would admit, with the H1 target it was assessed against."""
    return {"target": target_view(target), **_candidate_view(candidate)}


def selection_view(candidate: RankedCandidate) -> dict[str, object]:
    """Describe one candidate an automatic choice weighed by its hash, without names, paths or links."""
    return {
        "info_hash": candidate.stream.info_hash,
        "verdict": candidate.identity.verdict.value,
        "quality": candidate.quality,
        "confidence": candidate.confidence,
        "conflict": candidate.conflict,
        "pack": candidate.pack,
        "after_metadata": candidate.release_name_only,
    }


def _candidate_view(candidate: RankedCandidate) -> dict[str, object]:
    return {
        "stream": stream_view(candidate.stream),
        "identity": encode_view(candidate.identity),
        "traits": encode_view(candidate.traits),
        "quality": candidate.quality,
        "confidence": candidate.confidence,
        "conflict": candidate.conflict,
        "supported": candidate.supported,
    }


def append_decision(path: Path, kind: str, payload: Mapping[str, object], *, entry: str = "manual") -> None:
    """Append trusted allowlisted evidence of the *entry* path without making admission depend on the journal."""
    try:
        _evidence(payload)
        record: dict[str, object] = {
            "schema": 1,
            "rules": "e1",
            "kind": kind,
            "at": datetime.now(UTC).isoformat(),
            "entry": entry,
            **payload,
        }
        line: str = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
    except (OSError, ValueError, TypeError) as error:
        logger.warning("Decision journal append failed", error_class=type(error).__name__)

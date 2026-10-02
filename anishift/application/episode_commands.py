"""Bounded episode command views and admission payloads shared by the owner and its clients."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from anishift.application.episode_selection import EpisodeKey, EpisodeOffer

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_EPISODE_KEYS: Final[int] = 100
"""Maximum unique episodes of one entry accepted by one command or state read."""


class EpisodeReason(StrEnum):
    """Owner-local reason of one episode result or status; other reasons reuse existing error enums."""

    ADMITTED = "admitted"
    ACQUISITION_UNAVAILABLE = "acquisition_unavailable"
    EPISODE_NOT_AIRED = "episode_not_aired"
    SOURCE_FAILED = "source_failed"
    LEGACY_UNREADABLE = "legacy_unreadable"
    EPISODE_IN_PROGRESS = "episode_in_progress"
    NO_SUGGESTION = "no_suggestion"
    PACK_IN_PROGRESS = "pack_in_progress"
    ADMISSION_FAILED = "admission_failed"
    TRANSFER_FAILED = "transfer_failed"
    PUBLICATION_FAILED = "publication_failed"
    WAITING_PREVIOUS_TRANSFER = "waiting_previous_transfer"
    EPISODE_FILE_UNRESOLVED = "episode_file_unresolved"
    PUBLICATION_MISSING = "publication_missing"
    FINALIZATION_FAILED = "finalization_failed"
    RESULT_MISSING = "result_missing"
    EPISODE_CHANGED = "episode_changed"
    COMMAND_REUSED = "command_reused"


@dataclass(frozen=True, slots=True)
class EpisodeResult:
    """Describe one episode's admission outcome independently of its transfer progress."""

    key: EpisodeKey
    reason: str
    admission_id: str | None = None
    operation_id: str | None = None


@dataclass(frozen=True, slots=True)
class EpisodeBatch:
    """Project a durable batch receipt without restoring its in-memory work queue."""

    command_id: str
    instance_id: str
    keys: tuple[EpisodeKey, ...]
    state: str
    results: tuple[EpisodeResult, ...] = ()


@dataclass(frozen=True, slots=True)
class EpisodeOfferView:
    """Bind an inspected offer and conflict to one session in one owner instance."""

    offer_id: str
    instance_id: str
    offer: EpisodeOffer
    previous_admission_id: str | None = None
    conflict: tuple[str, ...] = ()
    unknown_previous: bool = False


@dataclass(frozen=True, slots=True)
class EpisodeFile:
    """Identify one safe video in the exact file map shown for manual binding."""

    index: int
    path: str
    size: int


@dataclass(frozen=True, slots=True)
class EpisodeFiles:
    """Present the revision-bound video choices for one unresolved admission."""

    admission_id: str
    revision: str
    files: tuple[EpisodeFile, ...]


@dataclass(frozen=True, slots=True)
class EpisodeStatus:
    """Project the latest real admission or the scoped legacy uncertainty of one episode."""

    key: EpisodeKey
    state: str
    reason: str | None = None
    admission_id: str | None = None
    operation_id: str | None = None
    uncertain: bool = False
    set_id: str | None = None

    @property
    def active(self) -> bool:
        """Whether the owner reports an unfinished order, transfer or processing run."""
        return self.state in {"ordered", "downloading", "processing"}


def validate_episode_keys(keys: tuple[EpisodeKey, ...]) -> None:
    """Require one bounded, unique, positive episode range belonging to one catalogue entry."""
    if not 1 <= len(keys) <= MAX_EPISODE_KEYS or len(set(keys)) != len(keys):
        msg = "An episode command requires 1-100 unique keys"
        raise ValueError(msg)
    if len({key.anilist_id for key in keys}) != 1 or any(
        type(value) is not int or value < 1 for key in keys for value in (key.anilist_id, key.number)
    ):
        msg = "Episode keys require positive integers of one entry"
        raise ValueError(msg)

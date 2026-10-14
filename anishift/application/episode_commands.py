"""Bounded episode command views and admission payloads shared by the owner and its clients."""

from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from anishift.application.episode_selection import EpisodeKey, EpisodeOffer
from anishift.application.release_quality import ResolutionClass

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_EPISODE_KEYS: Final[int] = 100
"""Maximum unique episodes of one entry accepted by one command or state read."""

_NOTICES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "stalled": "wydanie stoi",
        "metadata_timeout": "wydanie stoi",
        "rejected": "wydanie odrzucone",
        "pack": "wydanie okazało się paczką",
        "ambiguous": "wydanie ma niejednoznaczny plik",
        "no_match": "plik to nie ten odcinek",
        "recheck": "plik nie przeszedł ponownej kontroli",
        "taken": "plik należy już do innego odcinka",
        "no_admissible": "brak pewnego wydania",
        "threshold": "czekam na lepszą rozdzielczość",
        "pending": "czekam na sprawdzenie wydań",
        "sources_down": "źródła wydań nie odpowiadają",
        "no_polish_after_wait": "brak PL",
    }
)
"""Polish phrase of each reason a subscription target has no download yet, or took one without Polish."""

_FAILED_ATTEMPT: Final[str] = "pobieranie nie powiodło się"
"""Phrase of an attempt that ended for a reason without its own phrase."""

_REJECTIONS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "no_video_stream": "brak obrazu",
        "fragment_duration": "za krótki plik",
        "compilation_or_extended_duration": "za długi plik",
    }
)
"""Polish cause of each download check rejection."""

_THRESHOLDS: Final[Mapping[ResolutionClass, str]] = MappingProxyType(
    {
        ResolutionClass.FULL_HD: "1080p",
        ResolutionClass.UHD: "1080p lub 2160p",
        ResolutionClass.HD: "1080p, 2160p lub 720p",
        ResolutionClass.OTHER: "znaną rozdzielczość",
        ResolutionClass.UNKNOWN: "dowolną rozdzielczość",
    }
)
"""Resolutions a target threshold still admits, by the resolution class of its dead attempt."""

_HOUR_MINUTES: Final[int] = 60
"""Minutes in one hour."""


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
    SUBSCRIPTION_AWAITING_AIRING = "subscription_awaiting_airing"
    SUBSCRIPTION_AWAITING_RELEASE = "subscription_awaiting_release"
    SUBSCRIPTION_CHECKING = "subscription_checking"
    SUBSCRIPTION_CHECK_SKIPPED = "subscription_check_skipped"
    SUBSCRIPTION_EXHAUSTED = "subscription_exhausted"


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
    revision: int = 1


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
class TargetNotice:
    """One reason a subscription target has no download yet, or took one without Polish subtitles.

    ``cause`` is the rejection reason, ``total/untried matching/tried matching`` releases, ``threshold class/height``,
    the pending height, whole hours without sources or minutes waited for Polish subtitles, by *reason*; a cause
    that cannot be read leaves the plain phrase.
    """

    reason: str
    cause: str | None = None


@dataclass(frozen=True, slots=True)
class EpisodeStatus:
    """Project the latest real admission or the scoped legacy uncertainty of one episode.

    ``attempt`` marks an unfinished subscription attempt, which an explicit order replaces instead of waiting for it.
    A due subscription target carries its Polish history in ``polish``, the end of its Polish wait in
    ``polish_wait_until`` while it waits, and ``polish_skipped`` once the user ended that wait; ``notices`` say
    why a subscription target has no download yet, or took one without Polish subtitles.
    """

    key: EpisodeKey
    state: str
    reason: str | None = None
    admission_id: str | None = None
    operation_id: str | None = None
    uncertain: bool = False
    set_id: str | None = None
    attempt: bool = False
    polish: str | None = None
    polish_wait_until: str | None = None
    polish_skipped: bool = False
    notices: tuple[TargetNotice, ...] = ()

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


def notice_text(notice: TargetNotice, *, searching: bool = False) -> str:
    """Name one target notice in Polish; *searching* adds that automation looks for the next release."""
    phrase: str = _NOTICES.get(notice.reason, _FAILED_ATTEMPT)
    if notice.cause is not None:
        with suppress(ValueError, KeyError):
            phrase = _detailed(notice.reason, notice.cause) or phrase
    return f"{phrase}, szukam następnego" if searching else phrase


def _detailed(reason: str, cause: str) -> str | None:
    detail: str | None = None
    match reason:
        case "rejected":
            detail = f"({_REJECTIONS.get(cause, 'kontrola pliku')})"
        case "no_admissible":
            detail = f"({_counts(cause)})"
        case "threshold":
            return _threshold(cause)
        case "pending":
            detail = _height(cause)
        case "sources_down":
            detail = f"od {_whole(cause)} h"
        case "no_polish_after_wait":
            detail = f"po {_duration(_whole(cause))}"
    return None if detail is None else f"{_NOTICES[reason]} {detail}"


def _counts(cause: str) -> str:
    total, fresh, tried = (_whole(part) for part in cause.split("/"))
    counted: str = f"{total} {_plural(total, 'wydanie', 'wydania', 'wydań')}, {fresh} {_plural(fresh, 'zgodne')}"
    return f"{counted}, {tried} już {_plural(tried, 'próbowane')}" if tried else counted


def _threshold(cause: str) -> str:
    level, _separator, height = cause.partition("/")
    wanted: str = f"czekam na {_THRESHOLDS[ResolutionClass(_whole(level))]}"
    return f"{wanted} (dostępne {_height(height)})" if height else wanted


def _height(cause: str) -> str:
    return f"{_whole(cause)}p"


def _duration(minutes: int) -> str:
    hours, rest = divmod(minutes, _HOUR_MINUTES)
    if not hours:
        return f"{rest} min"
    return f"{hours} h {rest} min" if rest else f"{hours} h"


def _whole(text: str) -> int:
    if not text.isdecimal():
        msg: str = "A notice cause names a whole number"
        raise ValueError(msg)
    return int(text)


def _plural(count: int, one: str, few: str | None = None, many: str | None = None) -> str:
    """Return the Polish form for *count*; an adjective passes only its singular and gets ``-ych`` for many."""
    if count == 1:
        return one
    if count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}:
        return few or one
    return many or f"{one[:-1]}ych"

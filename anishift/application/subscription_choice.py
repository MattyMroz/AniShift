"""Pure subscription release choice: usability, admissibility, choice order, pending reads and replacement."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from anishift.application.episode_identity import IdentityVerdict
from anishift.application.episode_releases import info_hash_hex
from anishift.application.release_quality import (
    PolishClass,
    ReleaseTraits,
    ResolutionClass,
    class_key,
    resolution_class,
)
from anishift.application.subscription_targets import (
    MAX_TRANSIENT_FAILURES,
    Blocker,
    PolishObservation,
    PolishState,
    ReleaseFailure,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Iterator, Mapping, Sequence

    from anishift.application.control import AcquisitionConfirmation
    from anishift.application.episode_selection import RankedCandidate

__all__ = [
    "ABSENT_AFTER_H",
    "DECISION_AFTER_H",
    "NO_POLISH_AFTER_WAIT",
    "SOURCES_DOWN_NOTICE_H",
    "UNKNOWN_WAIT_H",
    "Blocker",
    "ChoiceCandidate",
    "ChoiceDecision",
    "ChoiceState",
    "ReadOutcome",
    "admissible",
    "choice_candidate",
    "choice_key",
    "choose",
    "completion_order",
    "decide",
    "decision_deadline",
    "is_taken",
    "pending_blocks",
    "pending_releases",
    "polish_admitted",
    "polish_history",
    "protected_file",
    "protected_files",
    "record_failures",
    "release_hash",
    "replacement",
    "usable",
    "wait_until",
]


class ReadOutcome(StrEnum):
    """Outcome of a complete inventory visit, never of its intermediate ID lookup."""

    LISTED = "listed"
    EMPTY = "empty"
    NO_HASH = "no_hash"
    PENDING = "pending"
    RATE_LIMITED = "rate_limited"
    FAILED = "failed"
    TIMEOUT = "timeout"


# ── Constants ─────────────────────────────────────────────────────────────────

type ProtectedFile = tuple[str, str | None]
"""Info hash and casefolded slash path of a file another target holds; no path protects the whole hash."""

_DECISIVE: Final[frozenset[ReadOutcome]] = frozenset({ReadOutcome.EMPTY, ReadOutcome.NO_HASH})
"""Inventory outcomes that end the wait for a release without giving it an inventory."""

UNKNOWN_WAIT_H: Final[int] = 2
"""Longest wait for Polish subtitles, in hours after the deadline, while the Polish history is unknown."""

ABSENT_AFTER_H: Final[int] = 24
"""Hours after the previous episode aired before its releases may prove that Polish subtitles are absent."""

NO_POLISH_AFTER_WAIT: Final[str] = "no_polish_after_wait"
"""Reason of a choice taken without Polish subtitles once the wait for them ended."""

DECISION_AFTER_H: Final[int] = 2
"""Hours after the deadline before a target without an admissible release is reported, at least."""

SOURCES_DOWN_NOTICE_H: Final[int] = 1
"""Hours every enabled source of a due target may stay unavailable before the user is told."""


@dataclass(frozen=True, slots=True)
class ChoiceCandidate:
    """One ranked release as automation sees it, deliberately without the list confidence."""

    info_hash: str
    file: str | None
    verdict: IdentityVerdict
    conflict: bool
    after_metadata: bool
    traits: ReleaseTraits
    quality: float
    pack: bool
    ambiguous: bool
    supported: bool
    taken: bool = False


@dataclass(frozen=True, slots=True)
class ChoiceState:
    """What one due target brings to its choice: tried releases, threshold, pending reads and its Polish wait."""

    excluded: frozenset[str]
    threshold: ResolutionClass | None
    failures: tuple[ReleaseFailure, ...]
    tsukihime: bool
    wait_until: datetime
    skip_wait: bool = False


@dataclass(frozen=True, slots=True)
class ChoiceDecision:
    """The release one check admits for a target, or what blocks it, with the end of its Polish wait.

    ``blocked`` is the best release the threshold refuses, or the best pending release that blocks the choice.
    """

    candidate: ChoiceCandidate | None
    blocker: Blocker
    wait_until: datetime | None = None
    reason: str | None = None
    blocked: ChoiceCandidate | None = None


def choice_candidate(candidate: RankedCandidate, protected: Collection[ProtectedFile] = ()) -> ChoiceCandidate:
    """Project one ranked row, marking it taken when its file is protected for another target."""
    path: str | None = candidate.stream.path
    return ChoiceCandidate(
        info_hash=release_hash(candidate.stream.info_hash),
        file=path or candidate.stream.file_name,
        verdict=candidate.identity.verdict,
        conflict=candidate.conflict,
        after_metadata=candidate.release_name_only,
        traits=candidate.traits,
        quality=candidate.quality,
        pack=candidate.pack,
        ambiguous=candidate.ambiguous,
        supported=candidate.supported is not False,
        taken=is_taken(candidate.stream.info_hash, path, protected),
    )


def usable(candidate: ChoiceCandidate) -> bool:
    """Whether the release could serve any target: one file, original audio, no burned subtitles, known container."""
    traits: ReleaseTraits = candidate.traits
    return not (
        candidate.pack
        or candidate.ambiguous
        or traits.dub_only
        or traits.raw
        or traits.hardsub
        or not candidate.supported
        or candidate.taken
    )


def admissible(candidate: ChoiceCandidate, *, excluded: Collection[str], threshold: ResolutionClass | None) -> bool:
    """Whether automation may try *candidate*: a usable untried match no worse than the target threshold."""
    return (
        candidate.verdict is IdentityVerdict.MATCH
        and usable(candidate)
        and candidate.info_hash not in excluded
        and (threshold is None or _resolution(candidate) <= threshold)
    )


def choice_key(candidate: ChoiceCandidate) -> tuple[object, ...]:
    """Order by classes, a known file before one verified after metadata, quality, seeds and hash."""
    seeders: int = -1 if candidate.traits.seeders is None else candidate.traits.seeders
    return (*class_key(candidate.traits), candidate.after_metadata, -candidate.quality, -seeders, candidate.info_hash)


def pending_releases(
    candidates: Sequence[ChoiceCandidate],
    *,
    failures: Sequence[ReleaseFailure],
    excluded: Collection[str],
    tsukihime: bool,
) -> tuple[ChoiceCandidate, ...]:
    """Return the name-only releases whose TsukiHime read has not ended yet; none while TsukiHime is off."""
    if not tsukihime:
        return ()
    ended: frozenset[str] = _ended(failures)
    return tuple(
        item
        for item in candidates
        if item.after_metadata
        and not item.conflict
        and usable(item)
        and item.info_hash not in excluded
        and item.info_hash not in ended
    )


def pending_blocks(pending: Collection[ChoiceCandidate], candidate: ChoiceCandidate) -> bool:
    """Whether a pending release of a better resolution, or better Polish at equal resolution, blocks *candidate*."""
    return any(_worse(candidate, item) for item in pending)


def choose(
    candidates: Sequence[ChoiceCandidate],
    *,
    excluded: Collection[str],
    threshold: ResolutionClass | None,
    failures: Sequence[ReleaseFailure],
    tsukihime: bool,
) -> ChoiceCandidate | None:
    """Return the first admissible, unblocked release, never a known zero-seed one beside a seeded one of its class."""
    pending: tuple[ChoiceCandidate, ...] = pending_releases(
        candidates, failures=failures, excluded=excluded, tsukihime=tsukihime
    )
    allowed: list[ChoiceCandidate] = sorted(
        (
            item
            for item in candidates
            if admissible(item, excluded=excluded, threshold=threshold) and not pending_blocks(pending, item)
        ),
        key=choice_key,
    )
    seeded: frozenset[tuple[ResolutionClass, PolishClass]] = frozenset(
        _class(item) for item in allowed if item.traits.seeders != 0
    )
    return next((item for item in allowed if item.traits.seeders != 0 or _class(item) not in seeded), None)


def decide(candidates: Sequence[ChoiceCandidate], state: ChoiceState, now: datetime) -> ChoiceDecision:
    """Admit the first choice at once when it has Polish subtitles, otherwise only after the Polish wait or a skip."""
    picked: ChoiceCandidate | None = choose(
        candidates,
        excluded=state.excluded,
        threshold=state.threshold,
        failures=state.failures,
        tsukihime=state.tsukihime,
    )
    if picked is None:
        return _blocked(candidates, state)
    if picked.traits.polish is PolishClass.POLISH or state.skip_wait:
        return ChoiceDecision(picked, Blocker.NONE)
    if now < state.wait_until:
        return ChoiceDecision(None, Blocker.WAITING_POLISH, state.wait_until)
    return ChoiceDecision(picked, Blocker.NONE, reason=NO_POLISH_AFTER_WAIT)


def decision_deadline(due: datetime, polish_until: datetime) -> datetime:
    """Return when a due target without an admissible release counts as a failure: its Polish wait, at least 2 h."""
    return max(polish_until, due + timedelta(hours=DECISION_AFTER_H))


def polish_history(observation: PolishObservation | None, *, local: bool) -> PolishState:
    """Return the Polish history of a target: a local admission with Polish first, then the last observation."""
    if local:
        return PolishState.PRESENT
    return PolishState.UNKNOWN if observation is None else observation.state


def wait_until(due: datetime, history: PolishState, wait_h: int) -> datetime:
    """Return when a target stops waiting for Polish: the full wait, none when absent, at most two hours unknown."""
    hours: int = {
        PolishState.PRESENT: wait_h,
        PolishState.ABSENT: 0,
        PolishState.UNKNOWN: min(UNKNOWN_WAIT_H, wait_h),
    }[history]
    return due + timedelta(hours=hours)


def polish_admitted(acquisitions: Sequence[AcquisitionConfirmation], anilist_id: int, number: int) -> bool:
    """Whether any release admitted for one episode, by hand or by a subscription, had Polish subtitles."""
    return any(
        assignment.choice.traits is not None and assignment.choice.traits.polish is PolishClass.POLISH
        for transfer in acquisitions
        for assignment in transfer.assignments
        if (assignment.choice.anilist_id, assignment.choice.number) == (anilist_id, number)
    )


def replacement(candidates: Sequence[ChoiceCandidate], *, excluded: Collection[str]) -> ChoiceCandidate | None:
    """Return the R-07 replacement: the first admissible release by ``choice_key``, or None for a manual choice.

    It ignores the Polish wait and the target threshold, and *excluded* drops every file of each tried hash, so
    an uncertain release never qualifies. E4 calls it from the U-08 trigger on ``search_episode`` candidates and
    admits the result through ``_admit_episode`` with the rejected admission as ``previous``.
    """
    allowed: list[ChoiceCandidate] = sorted(
        (item for item in candidates if admissible(item, excluded=excluded, threshold=None)), key=choice_key
    )
    return allowed[0] if allowed else None


def completion_order(
    releases: Sequence[ChoiceCandidate], *, failures: Sequence[ReleaseFailure], excluded: Collection[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the hashes the subscription completion queue visits: still blocking ones, then ended ones."""
    ended: frozenset[str] = _ended(failures)
    queued: list[ChoiceCandidate] = sorted(
        (item for item in releases if not item.conflict and usable(item) and item.info_hash not in excluded),
        key=choice_key,
    )
    hashes: tuple[str, ...] = tuple(dict.fromkeys(item.info_hash for item in queued))
    return (
        tuple(item for item in hashes if item not in ended),
        tuple(item for item in hashes if item in ended),
    )


def record_failures(
    failures: Sequence[ReleaseFailure],
    outcomes: Mapping[str, ReadOutcome],
    *,
    tsukihime_down: bool,
    pending: Collection[str],
) -> tuple[ReleaseFailure, ...]:
    """Return the target failures after one check: an inventory clears, a decisive read ends, others count once."""
    current: dict[str, ReleaseFailure] = {item.info_hash: item for item in failures}
    read: set[str] = set()
    for raw, outcome in outcomes.items():
        info_hash: str | None = info_hash_hex(raw)
        if info_hash is None:
            continue
        read.add(info_hash)
        known: ReleaseFailure = current.get(info_hash, ReleaseFailure(info_hash))
        if outcome is ReadOutcome.LISTED:
            current.pop(info_hash, None)
        elif outcome in _DECISIVE:
            current[info_hash] = replace(known, decisive=True)
        else:
            current[info_hash] = _counted(known)
    if tsukihime_down:
        for raw in pending:
            missed: str | None = info_hash_hex(raw)
            if missed is not None and missed not in read:
                current[missed] = _counted(current.get(missed, ReleaseFailure(missed)))
    return tuple(current.values())


def protected_files(
    acquisitions: Sequence[AcquisitionConfirmation], except_key: tuple[int | None, int]
) -> frozenset[ProtectedFile]:
    """Return the files every protected assignment of an episode other than *except_key* holds."""
    return frozenset(
        item
        for transfer in acquisitions
        for assignment in transfer.protected_assignments
        if (assignment.choice.anilist_id, assignment.choice.number) != except_key
        for item in _assignment_files(
            assignment.choice.reference.info_hash,
            (*(path for _index, path, _size in assignment.files), assignment.video_path),
        )
    )


def protected_file(info_hash: str, path: str | None) -> ProtectedFile:
    """Return the protection key of one file; without a path it protects the whole hash."""
    return release_hash(info_hash), None if path is None else path.replace("\\", "/").casefold()


def is_taken(info_hash: str, path: str | None, protected: Collection[ProtectedFile]) -> bool:
    """Whether a file is protected for another target; a file without a known path is taken by any of its hash."""
    key: ProtectedFile = protected_file(info_hash, path)
    if (key[0], None) in protected:
        return True
    if key[1] is None:
        return any(item[0] == key[0] for item in protected)
    return key in protected


def _assignment_files(info_hash: str, paths: tuple[str | None, ...]) -> Iterator[ProtectedFile]:
    known: tuple[str, ...] = tuple(path for path in paths if path is not None)
    if not known:
        yield protected_file(info_hash, None)
    for path in known:
        yield protected_file(info_hash, path)


def release_hash(value: str) -> str:
    """Return the lowercase hexadecimal hash automation compares releases by, else the casefolded text."""
    return info_hash_hex(value) or value.casefold()


def _blocked(candidates: Sequence[ChoiceCandidate], state: ChoiceState) -> ChoiceDecision:
    allowed: list[ChoiceCandidate] = [
        item for item in candidates if admissible(item, excluded=state.excluded, threshold=state.threshold)
    ]
    if allowed:
        pending: tuple[ChoiceCandidate, ...] = pending_releases(
            candidates, failures=state.failures, excluded=state.excluded, tsukihime=state.tsukihime
        )
        return ChoiceDecision(None, Blocker.PENDING, blocked=min(pending, key=choice_key, default=None))
    refused: list[ChoiceCandidate] = [
        item for item in candidates if admissible(item, excluded=state.excluded, threshold=None)
    ]
    if refused:
        return ChoiceDecision(None, Blocker.THRESHOLD, blocked=min(refused, key=choice_key))
    return ChoiceDecision(None, Blocker.NO_ADMISSIBLE)


def _ended(failures: Sequence[ReleaseFailure]) -> frozenset[str]:
    return frozenset(item.info_hash for item in failures if item.decisive or item.transient >= MAX_TRANSIENT_FAILURES)


def _counted(failure: ReleaseFailure) -> ReleaseFailure:
    return replace(failure, transient=min(MAX_TRANSIENT_FAILURES, failure.transient + 1))


def _resolution(candidate: ChoiceCandidate) -> ResolutionClass:
    return resolution_class(candidate.traits.resolution)[0]


def _class(candidate: ChoiceCandidate) -> tuple[ResolutionClass, PolishClass]:
    return _resolution(candidate), candidate.traits.polish


def _worse(candidate: ChoiceCandidate, pending: ChoiceCandidate) -> bool:
    mine: ResolutionClass = _resolution(candidate)
    theirs: ResolutionClass = _resolution(pending)
    return mine > theirs or (mine == theirs and candidate.traits.polish > pending.traits.polish)

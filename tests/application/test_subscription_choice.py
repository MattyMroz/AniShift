from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Final

import pytest

from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AdmissionSource,
    ChoiceTraits,
    EpisodeAssignment,
    EpisodeChoice,
    FileReservation,
    TorrentioReference,
)
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.intents import RequestOrigin
from anishift.application.release_quality import AudioClass, PolishClass, ReleaseTraits, ResolutionClass
from anishift.application.subscription_choice import (
    NO_POLISH_AFTER_WAIT,
    Blocker,
    ChoiceCandidate,
    ChoiceDecision,
    ChoiceState,
    ProtectedFile,
    ReadOutcome,
    admissible,
    choose,
    completion_order,
    decide,
    is_taken,
    pending_releases,
    polish_admitted,
    polish_history,
    protected_file,
    protected_files,
    record_failures,
    replacement,
    usable,
    wait_until,
)
from anishift.application.subscription_targets import (
    MAX_TRANSIENT_FAILURES,
    PolishObservation,
    PolishState,
    ReleaseFailure,
)

pytestmark = pytest.mark.unit

_A: Final[str] = "a" * 40
_B: Final[str] = "b" * 40
_C: Final[str] = "c" * 40


def _traits(**changes: object) -> ReleaseTraits:
    traits: ReleaseTraits = ReleaseTraits(
        PolishClass.POLISH, False, False, AudioClass.ORIGINAL, False, False, False, 1080, False, False, 10, False
    )
    return replace(traits, **changes)  # type: ignore[arg-type]


def _item(info_hash: str = _A, **changes: object) -> ChoiceCandidate:
    traits: dict[str, object] = {key: changes.pop(key) for key in tuple(changes) if hasattr(_traits(), key)}
    item: ChoiceCandidate = ChoiceCandidate(
        info_hash=info_hash,
        file="Series - 04.mkv",
        verdict=IdentityVerdict.MATCH,
        conflict=False,
        after_metadata=False,
        traits=_traits(**traits),
        quality=50.0,
        pack=False,
        ambiguous=False,
        supported=True,
    )
    return replace(item, **changes)  # type: ignore[arg-type]


def _choose(
    *items: ChoiceCandidate,
    threshold: ResolutionClass | None = None,
    failures: tuple[ReleaseFailure, ...] = (),
    tsukihime: bool = True,
) -> ChoiceCandidate | None:
    return choose(items, excluded=frozenset(), threshold=threshold, failures=failures, tsukihime=tsukihime)


def test_usable_plain_release() -> None:
    assert usable(_item())


@pytest.mark.parametrize(
    "changes",
    [
        {"pack": True},
        {"ambiguous": True},
        {"dub_only": True},
        {"raw": True},
        {"hardsub": True},
        {"supported": False},
        {"taken": True},
    ],
    ids=["pack", "ambiguous", "dub-only", "raw", "hardsub", "unsupported", "taken"],
)
def test_usable_rejects_each_condition(changes: dict[str, object]) -> None:
    assert not usable(_item(_A, **changes))


@pytest.mark.parametrize(
    "verdict", [IdentityVerdict.INSUFFICIENT, IdentityVerdict.MISMATCH], ids=["uncertain", "mismatch"]
)
def test_admissible_requires_match(verdict: IdentityVerdict) -> None:
    assert not admissible(_item(verdict=verdict), excluded=(), threshold=None)


def test_admissible_rejects_tried_hash() -> None:
    assert not admissible(_item(), excluded={_A}, threshold=None)


@pytest.mark.parametrize(
    ("resolution", "threshold", "expected"),
    [
        (720, ResolutionClass.FULL_HD, False),
        (1080, ResolutionClass.FULL_HD, True),
        (720, ResolutionClass.HD, True),
        (None, None, True),
    ],
    ids=["below", "at", "raised", "none"],
)
def test_admissible_respects_threshold(
    resolution: int | None, threshold: ResolutionClass | None, expected: bool
) -> None:
    assert admissible(_item(resolution=resolution), excluded=(), threshold=threshold) is expected


def test_choose_ignores_list_confidence_and_follows_owner_classes() -> None:
    bare: ChoiceCandidate = _item(_A, polish=PolishClass.BARE, quality=99.0)
    polish: ChoiceCandidate = _item(_B, polish=PolishClass.POLISH, quality=10.0)

    assert _choose(bare, polish) == polish


def test_choose_prefers_known_file_over_one_verified_after_metadata() -> None:
    late: ChoiceCandidate = _item(_A, after_metadata=True, quality=99.0)
    known: ChoiceCandidate = _item(_B, quality=10.0)

    assert _choose(late, known, tsukihime=False) == known


def test_choose_skips_zero_seed_beside_seeded_release_of_its_class() -> None:
    dead: ChoiceCandidate = _item(_A, seeders=0, quality=99.0)
    seeded: ChoiceCandidate = _item(_B, seeders=2, quality=10.0)

    assert _choose(dead, seeded) == seeded
    assert _choose(dead) == dead


def test_choose_pending_better_release_blocks_worse() -> None:
    pending: ChoiceCandidate = _item(_A, after_metadata=True, verdict=IdentityVerdict.INSUFFICIENT)
    worse: ChoiceCandidate = _item(_B, polish=PolishClass.NONE)

    assert _choose(pending, worse) is None
    assert _choose(pending, worse, tsukihime=False) == worse


def test_choose_ended_pending_release_no_longer_blocks() -> None:
    pending: ChoiceCandidate = _item(_A, after_metadata=True, verdict=IdentityVerdict.INSUFFICIENT)
    worse: ChoiceCandidate = _item(_B, polish=PolishClass.NONE)

    assert _choose(pending, worse, failures=(ReleaseFailure(_A, decisive=True),)) == worse
    assert _choose(pending, worse, failures=(ReleaseFailure(_A, transient=MAX_TRANSIENT_FAILURES),)) == worse


def test_choose_conflicting_pending_release_never_blocks() -> None:
    pending: ChoiceCandidate = _item(_A, after_metadata=True, conflict=True, verdict=IdentityVerdict.MISMATCH)

    assert pending_releases((pending,), failures=(), excluded=(), tsukihime=True) == ()


def test_pending_skipped_does_not_increment() -> None:
    failures: tuple[ReleaseFailure, ...] = (ReleaseFailure(_A, transient=1),)

    assert record_failures(failures, {}, tsukihime_down=False, pending={_A}) == failures


def test_record_failures_counts_inventory_outcomes() -> None:
    outcomes: dict[str, ReadOutcome] = {
        _A.upper(): ReadOutcome.LISTED,
        _B: ReadOutcome.EMPTY,
        _C: ReadOutcome.TIMEOUT,
    }

    result: tuple[ReleaseFailure, ...] = record_failures(
        (ReleaseFailure(_A, transient=2),), outcomes, tsukihime_down=False, pending=()
    )

    assert set(result) == {ReleaseFailure(_B, decisive=True), ReleaseFailure(_C, transient=1)}


def test_record_failures_counts_unread_pending_while_tsukihime_down() -> None:
    result: tuple[ReleaseFailure, ...] = record_failures(
        (ReleaseFailure(_A, transient=MAX_TRANSIENT_FAILURES),), {}, tsukihime_down=True, pending={_A, _B}
    )

    assert set(result) == {ReleaseFailure(_A, transient=MAX_TRANSIENT_FAILURES), ReleaseFailure(_B, transient=1)}


def test_completion_order_visits_blocking_before_ended() -> None:
    ended: ChoiceCandidate = _item(_A, quality=99.0)
    open_: ChoiceCandidate = _item(_B, quality=1.0)

    order: tuple[tuple[str, ...], tuple[str, ...]] = completion_order(
        (ended, open_, _item(_C, pack=True)), failures=(ReleaseFailure(_A, decisive=True),), excluded=()
    )

    assert order == ((_B,), (_A,))


def test_replacement_first_admissible_by_choice_key() -> None:
    worse: ChoiceCandidate = _item(_A, resolution=720)
    better: ChoiceCandidate = _item(_B, resolution=1080, quality=1.0)

    assert replacement((worse, better), excluded=frozenset()) == better


def test_replacement_ignores_polish_wait_and_threshold() -> None:
    pending: ChoiceCandidate = _item(_A, after_metadata=True, verdict=IdentityVerdict.INSUFFICIENT)
    low: ChoiceCandidate = _item(_B, resolution=480, polish=PolishClass.NONE)

    assert replacement((pending, low), excluded=frozenset()) == low


def test_replacement_excludes_whole_hash() -> None:
    other_file: ChoiceCandidate = _item(_A, file="Series - 04v2.mkv")

    assert replacement((other_file,), excluded=frozenset({_A})) is None


def test_replacement_never_uncertain() -> None:
    assert replacement((_item(verdict=IdentityVerdict.INSUFFICIENT),), excluded=frozenset()) is None


def test_replacement_none_when_no_admissible() -> None:
    assert replacement((), excluded=frozenset()) is None
    assert replacement((_item(pack=True),), excluded=frozenset()) is None


def _held(
    number: int,
    *,
    files: tuple[FileReservation, ...] = (),
    video_path: str | None = None,
    info_hash: str = _A,
    traits: ChoiceTraits | None = None,
) -> AcquisitionConfirmation:
    choice: EpisodeChoice = EpisodeChoice(
        7,
        number,
        TorrentioReference(info_hash.upper(), 0, f"Series - {number:02}.mkv", "[Group] Series", ()),
        {"local_episode": number},
        IdentityVerdict.MATCH,
        "match",
        traits=traits,
    )
    assignment: EpisodeAssignment = EpisodeAssignment(
        f"held-{number}",
        "2026-10-07T00:00:00+00:00",
        AdmissionSource.MANUAL,
        choice,
        file_map="f" * 64 if files else None,
        files=files,
        video_path=video_path,
    )
    return AcquisitionConfirmation(
        operation_id=f"operation-{number}",
        info_hash=info_hash,
        directory="",
        required_files=(),
        state=AcquisitionState.ACCEPTED,
        origin=RequestOrigin.USER,
        subscription_id=None,
        episode=str(number),
        updated_at="2026-10-07T00:00:00+00:00",
        assignments=(assignment,),
    )


def test_protected_same_path_different_file_index_taken() -> None:
    protected: frozenset[ProtectedFile] = protected_files((_held(4, files=((2, "Pack/Series - 04.mkv", 10),)),), (7, 3))

    assert is_taken(_A, "pack/series - 04.MKV", protected)
    assert is_taken(_A, "Pack\\Series - 04.mkv", protected)


def test_protected_other_path_same_hash_not_taken() -> None:
    protected: frozenset[ProtectedFile] = protected_files((_held(4, files=((2, "Pack/Series - 04.mkv", 10),)),), (7, 3))

    assert not is_taken(_A, "Pack/Series - 03.mkv", protected)
    assert not is_taken(_B, "Pack/Series - 04.mkv", protected)
    assert is_taken(_A, None, protected)


def test_protected_unbound_assignment_protects_hash() -> None:
    protected: frozenset[ProtectedFile] = protected_files((_held(4),), (7, 3))

    assert protected == frozenset({(_A, None)})
    assert is_taken(_A.upper(), "Pack/Series - 03.mkv", protected)
    assert not is_taken(_B, None, protected)


def test_protected_survives_compaction_via_video_path() -> None:
    protected: frozenset[ProtectedFile] = protected_files((_held(4, video_path="Pack/Series - 04.mkv"),), (7, 3))

    assert protected == frozenset({protected_file(_A, "Pack/Series - 04.mkv")})


def test_protected_ignores_assignments_of_the_own_target() -> None:
    assert protected_files((_held(3),), (7, 3)) == frozenset()


def test_tried_hash_excluded_only_for_own_target() -> None:
    other_file: ChoiceCandidate = _item(_A, file="Pack/Series - 04v2.mkv")

    assert not admissible(other_file, excluded={_A}, threshold=None)
    assert admissible(other_file, excluded={_B}, threshold=None)
    assert usable(other_file)


_DUE: Final[datetime] = datetime(2026, 10, 7, 18, tzinfo=UTC)


def _state(*, waits_h: int = 2, skip_wait: bool = False) -> ChoiceState:
    return ChoiceState(
        excluded=frozenset(),
        threshold=None,
        failures=(),
        tsukihime=True,
        wait_until=_DUE + timedelta(hours=waits_h),
        skip_wait=skip_wait,
    )


def test_decide_admits_polish_at_once() -> None:
    polish: ChoiceCandidate = _item()

    assert decide((polish,), _state(), _DUE) == ChoiceDecision(polish, Blocker.NONE)


def test_decide_waits_for_polish_until_the_wait_ends() -> None:
    bare: ChoiceCandidate = _item(polish=PolishClass.NONE)

    assert decide((bare,), _state(), _DUE + timedelta(minutes=119)) == ChoiceDecision(
        None, Blocker.WAITING_POLISH, _DUE + timedelta(hours=2)
    )


def test_decide_admits_without_polish_after_the_wait() -> None:
    bare: ChoiceCandidate = _item(polish=PolishClass.BARE)

    assert decide((bare,), _state(), _DUE + timedelta(hours=2)) == ChoiceDecision(
        bare, Blocker.NONE, reason=NO_POLISH_AFTER_WAIT
    )


def test_skip_wait_admits_without_polish_at_once() -> None:
    bare: ChoiceCandidate = _item(polish=PolishClass.NONE)

    assert decide((bare,), _state(skip_wait=True), _DUE) == ChoiceDecision(bare, Blocker.NONE)


def test_skip_wait_still_needs_an_admissible_release() -> None:
    assert decide((_item(raw=True),), _state(skip_wait=True), _DUE) == ChoiceDecision(None, Blocker.NO_ADMISSIBLE)


def test_decide_waits_when_the_first_choice_lacks_polish_even_beside_a_worse_polish_one() -> None:
    bare: ChoiceCandidate = _item(_A, polish=PolishClass.NONE, resolution=1080)
    polish: ChoiceCandidate = _item(_B, resolution=720)

    assert decide((bare, polish), _state(), _DUE).blocker is Blocker.WAITING_POLISH
    assert decide((bare, polish), _state(), _DUE + timedelta(hours=2)).candidate is bare


def test_polish_history_local_evidence_wins_over_an_observation() -> None:
    absent: PolishObservation = PolishObservation(PolishState.ABSENT, _DUE.isoformat())

    assert polish_history(absent, local=True) is PolishState.PRESENT


@pytest.mark.parametrize("state", list(PolishState))
def test_polish_history_keeps_the_last_observation(state: PolishState) -> None:
    assert polish_history(PolishObservation(state, _DUE.isoformat()), local=False) is state


def test_polish_history_unknown_without_evidence() -> None:
    assert polish_history(None, local=False) is PolishState.UNKNOWN


def test_polish_history_local_evidence_from_any_admission_of_the_previous_episode() -> None:
    held: AcquisitionConfirmation = _held(3, traits=ChoiceTraits(PolishClass.POLISH, ResolutionClass.FULL_HD))

    assert polish_admitted((held,), 7, 3)
    assert not polish_admitted((held,), 7, 4)
    assert not polish_admitted((held,), 8, 3)


@pytest.mark.parametrize(
    "traits", [None, ChoiceTraits(PolishClass.BARE, ResolutionClass.FULL_HD)], ids=["none", "bare"]
)
def test_polish_history_no_local_evidence_without_polish_traits(traits: ChoiceTraits | None) -> None:
    assert not polish_admitted((_held(3, traits=traits),), 7, 3)


@pytest.mark.parametrize(
    ("history", "wait_h", "hours"),
    [
        (PolishState.PRESENT, 6, 6),
        (PolishState.ABSENT, 6, 0),
        (PolishState.UNKNOWN, 6, 2),
        (PolishState.UNKNOWN, 1, 1),
        (PolishState.PRESENT, 0, 0),
        (PolishState.UNKNOWN, 0, 0),
    ],
    ids=["present", "absent", "unknown-capped", "unknown-short", "present-off", "unknown-off"],
)
def test_wait_until_follows_the_history_and_setting(history: PolishState, wait_h: int, hours: int) -> None:
    assert wait_until(_DUE, history, wait_h) == _DUE + timedelta(hours=hours)

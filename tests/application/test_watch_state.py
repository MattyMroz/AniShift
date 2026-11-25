from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from test_episode_selection import _fixture_graph, _fixture_mapping

from anishift.application.control import (
    WATCH_STATE_SCHEMA_VERSION,
    AcquisitionConfirmation,
    AcquisitionState,
    AdmissionSource,
    AudiobookRecipe,
    AutomationPolicy,
    ChoiceTraits,
    CommandReceipt,
    DeletionOutcome,
    DeletionStatus,
    EpisodeAssignment,
    EpisodeChoice,
    LegacyScope,
    ManualHandledMarker,
    NarrationTimeline,
    PendingDeletion,
    ProcessingRequest,
    ProductConfirmation,
    ProviderLock,
    ReadyGroup,
    RecipePreferences,
    RequestState,
    Reservation,
    SourceFingerprint,
    SourceSelection,
    TextResultFormat,
    TorrentioReference,
    TranslateRecipe,
    WatchState,
    choice_traits,
    compact_acquisition,
)
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.episode_selection import AniZipMapping, FranchiseGraph, ListedEpisode, identity_target
from anishift.application.intents import ProductKind, RebuildRequest, RequestOrigin, TranslationAction
from anishift.application.release_quality import AudioClass, PolishClass, ReleaseTraits, ResolutionClass
from anishift.application.subscription_targets import (
    MAX_TRANSIENT_FAILURES,
    Blocker,
    PolishObservation,
    PolishSkip,
    PolishState,
    ReleaseFailure,
    SubscriptionRecord,
    SubscriptionTarget,
    TargetState,
)
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore, watch_state_path
from anishift.application.workflows import WorkflowTarget
from anishift.errors import ConfigError, ErrorCode

_TIMESTAMP: str = "2026-09-08T12:00:00+00:00"

_FINGERPRINT: SourceFingerprint = (("episode-01.mkv", 1024, 111),)

_SECTIONS: tuple[str, ...] = (
    "recipes",
    "ready_groups",
    "pause_owned_transfers",
    "pending_deletions",
    "subscriptions",
    "removed_subscription",
    "legacy_orders",
)

_EPISODE_IDENTITY_FIELDS: tuple[str, ...] = (
    "assignments",
    "legacy_scope",
    "selection_revision",
    "applied_revision",
    "manifest",
    "cleaned",
)


def test_deletion_evidence_round_trips_and_legacy_scope_never_gains_invented_identity(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    deletion: PendingDeletion = PendingDeletion(
        "delete-01",
        "set-01",
        _TIMESTAMP,
        (("ready/01.txt", 10, 20),),
        identities=(("ready/01.txt", 30, 40),),
        outcomes=(DeletionOutcome("ready/01.txt", DeletionStatus.INFLIGHT, "recycle_inflight"),),
        instance_id="original-owner",
    )
    state: WatchState = replace(_state(), pending_deletions=(deletion,))
    store.save(state)
    assert store.load() == state
    path: Path = tmp_path / WATCH_STATE_FILE_NAME
    document: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    records: list[dict[str, object]] = cast("list[dict[str, object]]", document["pending_deletions"])
    for field in ("identities", "outcomes", "instance_id"):
        records[0].pop(field)
    path.write_text(json.dumps(document), encoding="utf-8")
    legacy: PendingDeletion = store.load().pending_deletions[0]
    assert legacy.files == deletion.files
    assert legacy.identities == ()
    assert legacy.outcomes == ()
    assert legacy.instance_id is None


@pytest.mark.parametrize("change", ["foreign_identity", "duplicate_identity", "foreign_outcome", "missing_receipt"])
def test_deletion_loader_rejects_unsafe_native_evidence(tmp_path: Path, change: str) -> None:
    store: WatchStateStore = _store(tmp_path)
    deletion: PendingDeletion = PendingDeletion("delete-01", "set-01", _TIMESTAMP, (("ready/01.txt", 10, 20),))
    store.save(replace(_state(), pending_deletions=(deletion,)))
    path: Path = tmp_path / WATCH_STATE_FILE_NAME
    document: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    entry: dict[str, object] = cast("list[dict[str, object]]", document["pending_deletions"])[0]
    if change == "foreign_identity":
        entry["identities"] = [["ready/010.txt", 1, 2]]
    elif change == "duplicate_identity":
        entry["identities"] = [["ready/01.txt", 1, 2], ["ready/01.txt", 1, 2]]
    else:
        entry["outcomes"] = [
            {
                "path": "ready/010.txt" if change == "foreign_outcome" else "ready/01.txt",
                "status": "inflight" if change == "foreign_outcome" else "recycled",
                "reason": "test",
                "receipt": None,
            }
        ]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ConfigError):
        store.load()


def _store(tmp_path: Path) -> WatchStateStore:
    return WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME)


def _state() -> WatchState:
    return WatchState(
        policy=AutomationPolicy(auto_enabled=True, directory_exceptions={"Solo Leveling": False}),
        reservations=(Reservation("episode-01", _FINGERPRINT, "panel", _TIMESTAMP),),
        markers=(
            ManualHandledMarker(
                group_id="episode-01",
                fingerprint=_FINGERPRINT,
                products=frozenset({ProductKind.FULL_PL}),
                request_id="request-1",
                recorded_at=_TIMESTAMP,
            ),
        ),
        requests=(
            ProcessingRequest(
                request_id="request-1",
                generation=2,
                group_ids=("episode-01",),
                fingerprints={"episode-01": _FINGERPRINT},
                origin=RequestOrigin.BACKGROUND,
                source_selection=SourceSelection.MANUAL,
                rebuild=RebuildRequest(frozenset({ProductKind.NARRATION_AUDIO})),
                state=RequestState.RUNNING,
                attempts=1,
                accepted_at=_TIMESTAMP,
            ),
        ),
        acquisitions=(
            AcquisitionConfirmation(
                operation_id="operation-1",
                info_hash="AABBCC",
                directory="Solo Leveling",
                required_files=("episode-01.mkv",),
                state=AcquisitionState.ACCEPTED,
                origin=RequestOrigin.BACKGROUND,
                subscription_id="63b5bd67f700",
                episode="7.5",
                updated_at=_TIMESTAMP,
            ),
        ),
        products=(
            ProductConfirmation(
                group_id="episode-01",
                artifact_kind="final_mkv",
                path="Solo Leveling/episode-01.mkv",
                generation=2,
                request_id="request-1",
                origin=RequestOrigin.USER,
            ),
        ),
        provider_locks=(ProviderLock("nyaa", _TIMESTAMP, "rate limited"),),
        command_receipts=(CommandReceipt("command-1", _TIMESTAMP, {"accepted": True, "queued": 2, "note": None}),),
        notified=frozenset({("episode-01", "2", "ready")}),
    )


def _write(tmp_path: Path, document: object) -> None:
    (tmp_path / WATCH_STATE_FILE_NAME).write_text(json.dumps(document), encoding="utf-8")


def test_store_round_trips_every_recorded_fact(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    state: WatchState = _state()

    store.save(state)

    assert store.load() == state


def test_legacy_transfer_actions_do_not_invent_a_durable_send_record(tmp_path: Path) -> None:
    state: WatchState = _state()
    store: WatchStateStore = _store(tmp_path)
    store.save(state)
    document: dict[str, object] = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    for acquisition in document["acquisitions"]:  # type: ignore[attr-defined]
        acquisition.pop("action_sent")
    _write(tmp_path, document)

    assert store.load() == state
    assert store.load().acquisitions[0].action_sent is False


def test_legacy_requests_without_group_intents_still_load(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    document = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    document["requests"][0].pop("intents")
    _write(tmp_path, document)

    assert store.load() == _state()


def test_legacy_products_without_the_identity_of_their_bytes_still_load(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    document = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    document["products"][0].pop("size")
    document["products"][0].pop("modified_ns")
    _write(tmp_path, document)

    loaded: WatchState = store.load()

    assert loaded == _state()
    assert loaded.products[0].size == -1


def test_store_lowercases_the_info_hash_of_an_acquisition(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)

    store.save(_state())

    assert store.load().acquisitions[0].info_hash == "aabbcc"


def test_a_never_written_store_answers_with_automation_working_and_nothing_else_recorded(tmp_path: Path) -> None:
    state: WatchState = _store(tmp_path).load()

    assert state == WatchState(policy=AutomationPolicy(auto_enabled=True))
    assert state.policy.auto_enabled is True
    assert state.policy.directory_exceptions == {}


def test_a_stored_pause_stays_a_pause_instead_of_becoming_the_working_default(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=False)))

    assert store.load().policy.auto_enabled is False


def test_store_rejects_a_corrupt_document(tmp_path: Path) -> None:
    (tmp_path / WATCH_STATE_FILE_NAME).write_text('{"schema_version": 1, "policy"', encoding="utf-8")

    with pytest.raises(ConfigError) as failure:
        _store(tmp_path).load()

    assert failure.value.context.code is ErrorCode.CONFIG_INVALID


def test_store_rejects_an_unknown_field(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(WatchState())
    document: dict[str, object] = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    document["surprise"] = []
    _write(tmp_path, document)

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        store.load()


@pytest.mark.parametrize("version", [1, 4, WATCH_STATE_SCHEMA_VERSION - 1, WATCH_STATE_SCHEMA_VERSION + 1, "7"])
def test_store_rejects_another_schema_version_and_leaves_the_file(tmp_path: Path, version: object) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    path: Path = tmp_path / WATCH_STATE_FILE_NAME
    document: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = version
    _write(tmp_path, document)
    original: bytes = path.read_bytes()

    with pytest.raises(ConfigError) as failure:
        store.load()

    assert failure.value.context.code is ErrorCode.CONFIG_INVALID
    assert failure.value.context.suggestion is not None
    assert "state.json" in failure.value.context.suggestion
    assert path.read_bytes() == original


def test_saving_keeps_the_previous_version_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    first: WatchState = _state()
    store.save(first)

    store.save(replace(first, policy=AutomationPolicy(auto_enabled=False)))

    backup: WatchStateStore = WatchStateStore(tmp_path / f"{WATCH_STATE_FILE_NAME}.bak")
    assert backup.load() == first
    assert store.load().policy.auto_enabled is False
    assert not (tmp_path / f"{WATCH_STATE_FILE_NAME}.tmp").exists()


def test_a_temporary_file_left_by_a_crash_changes_nothing(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    state: WatchState = _state()
    store.save(state)
    (tmp_path / f"{WATCH_STATE_FILE_NAME}.tmp").write_text("{ not json", encoding="utf-8")

    assert store.load() == state


@pytest.mark.integration
@pytest.mark.parametrize("loaded", [False, True])
def test_saving_a_known_readable_file_copies_bytes_without_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, loaded: bool
) -> None:
    store: WatchStateStore = _store(tmp_path)
    first: WatchState = _state()
    store.save(first)
    if loaded:
        store = _store(tmp_path)
        assert store.load() == first
    original: bytes = (tmp_path / WATCH_STATE_FILE_NAME).read_bytes()

    def unexpected_parse(text: str) -> WatchState:
        raise AssertionError(text)

    monkeypatch.setattr("anishift.application.watch_state._parse", unexpected_parse)
    store.save(replace(first, policy=AutomationPolicy(auto_enabled=False)))
    assert (tmp_path / f"{WATCH_STATE_FILE_NAME}.bak").read_bytes() == original
    assert (tmp_path / WATCH_STATE_FILE_NAME).is_file()


@pytest.mark.integration
def test_saving_an_unknown_corrupt_file_preserves_the_existing_backup(tmp_path: Path) -> None:
    path: Path = tmp_path / WATCH_STATE_FILE_NAME
    backup: Path = path.with_name(f"{path.name}.bak")
    path.write_bytes(b"{broken")
    backup.write_bytes(b"previous-readable-backup")
    _store(tmp_path).save(_state())
    assert backup.read_bytes() == b"previous-readable-backup"
    assert _store(tmp_path).load() == _state()


def test_backup_keeps_the_previous_state_when_the_saved_file_is_later_rewritten_in_place(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    path: Path = tmp_path / WATCH_STATE_FILE_NAME
    store.save(_state())
    previous: bytes = path.read_bytes()
    store.save(replace(_state(), policy=AutomationPolicy(auto_enabled=False)))
    with path.open("r+b") as handle:
        handle.write(b"{broken")
    assert (tmp_path / f"{WATCH_STATE_FILE_NAME}.bak").read_bytes() == previous
    assert not (tmp_path / f"{WATCH_STATE_FILE_NAME}.bak.tmp").exists()


def test_saving_overwrites_a_temporary_file_left_by_a_crash(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    (tmp_path / f"{WATCH_STATE_FILE_NAME}.tmp").write_text("{ not json", encoding="utf-8")

    store.save(_state())

    assert not (tmp_path / f"{WATCH_STATE_FILE_NAME}.tmp").exists()
    assert store.load() == _state()


def test_store_rejects_a_file_that_is_not_valid_text_and_can_still_save(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    (tmp_path / WATCH_STATE_FILE_NAME).write_bytes(b'{"schema_version": 1, "policy": "\xff\xfe')

    with pytest.raises(ConfigError) as failure:
        store.load()
    store.save(_state())

    assert failure.value.context.code is ErrorCode.CONFIG_INVALID
    assert store.load() == _state()


def test_saving_always_writes_the_current_schema_version(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)

    store.save(replace(_state(), schema_version=99))

    assert json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))["schema_version"] == (
        WATCH_STATE_SCHEMA_VERSION
    )
    assert store.load().schema_version == WATCH_STATE_SCHEMA_VERSION


@pytest.mark.parametrize("section", _SECTIONS)
def test_a_state_missing_a_section_it_must_carry_is_refused(tmp_path: Path, section: str) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    document: dict[str, object] = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    document.pop(section)
    _write(tmp_path, document)

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        store.load()


@pytest.mark.parametrize("section", _SECTIONS)
def test_a_state_with_a_malformed_section_is_refused(tmp_path: Path, section: str) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    document: dict[str, object] = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    document[section] = "nonsense"
    _write(tmp_path, document)

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        store.load()


def test_an_acquisition_without_its_completeness_is_refused(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    document: dict[str, object] = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    for acquisition in document["acquisitions"]:  # type: ignore[attr-defined]
        acquisition.pop("complete_files")
    _write(tmp_path, document)

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        store.load()


def test_a_truncated_state_still_raises_instead_of_answering_with_defaults(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    full: str = (tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8")
    (tmp_path / WATCH_STATE_FILE_NAME).write_text(full[: len(full) // 2], encoding="utf-8")

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        store.load()


def test_the_store_round_trips_recipes_ready_sets_and_pending_deletions(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    state: WatchState = replace(
        _state(),
        recipes=RecipePreferences(
            translate=TranslateRecipe(TextResultFormat.SUBTITLES, TranslationAction.TRANSLATE),
            audiobook=AudiobookRecipe(TranslationAction.DO_NOT_TRANSLATE, NarrationTimeline.SOURCE_TIMES),
        ),
        ready_groups=(
            ReadyGroup(
                set_id="set-1",
                group_id="ready-episode-01",
                stem="episode-01",
                source_directory="audiobook/Solo Leveling",
                source_stem="episode-01",
                target=WorkflowTarget.AUDIOBOOK,
                sources=("ready/episode-01.mkv",),
                products=("ready/episode-01.m4a",),
                main_result="ready/episode-01.m4a",
                pending_sources=("audiobook/Solo Leveling/episode-01.mkv",),
                recipe=RecipePreferences(audiobook=AudiobookRecipe(timeline=NarrationTimeline.SOURCE_TIMES)),
            ),
        ),
        pause_owned_transfers=("aabbcc",),
        pending_deletions=(
            PendingDeletion(
                operation_id="deletion-1",
                set_id="set-1",
                requested_at=_TIMESTAMP,
                files=(("ready/episode-01.mkv", 1024, 111), ("ready/episode-01.m4a", 2048, 222)),
                recycled=("ready/episode-01.mkv",),
            ),
        ),
        acquisitions=(replace(_state().acquisitions[0], complete_files=("episode-01.mkv",)),),
    )

    store.save(state)

    assert store.load() == state


def _selective() -> AcquisitionConfirmation:
    choice: EpisodeChoice = EpisodeChoice(
        anilist_id=500,
        number=3,
        reference=TorrentioReference("FFEE", 2, "Neko S2 - 03.mkv"),
        target={"aliases": ["Neko"], "local_episode": 3, "absolute": 27},
        verdict=IdentityVerdict.INSUFFICIENT,
        reason="Bare number",
        deviation_confirmed=True,
    )
    return AcquisitionConfirmation(
        operation_id="operation-3",
        info_hash="ffee",
        directory="",
        required_files=(),
        state=AcquisitionState.ADMITTED,
        origin=RequestOrigin.USER,
        subscription_id=None,
        episode=None,
        updated_at=_TIMESTAMP,
        assignments=(EpisodeAssignment("admission-1", _TIMESTAMP, AdmissionSource.MANUAL, choice),),
    )


def test_the_store_round_trips_episode_assignments_and_legacy_scopes(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    legacy: AcquisitionConfirmation = replace(_state().acquisitions[0], legacy_scope=LegacyScope(500, None))
    numbered: AcquisitionConfirmation = replace(legacy, operation_id="operation-4", legacy_scope=LegacyScope(500, 4))
    state: WatchState = replace(_state(), acquisitions=(legacy, numbered, _selective()))

    store.save(state)

    assert store.load() == state
    assert [item.selective for item in store.load().acquisitions] == [False, False, True]


@pytest.mark.parametrize("field", _EPISODE_IDENTITY_FIELDS)
def test_an_acquisition_without_its_episode_identity_is_refused(tmp_path: Path, field: str) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    document: dict[str, object] = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    cast("list[dict[str, object]]", document["acquisitions"])[0].pop(field)
    _write(tmp_path, document)

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        store.load()


def test_an_admission_without_an_episode_assignment_is_refused() -> None:
    with pytest.raises(ValueError, match="selective"):
        replace(_selective(), assignments=())


def test_a_mismatched_episode_choice_requires_a_confirmed_deviation() -> None:
    with pytest.raises(ValueError, match="deviation"):
        replace(_selective().assignments[0].choice, verdict=IdentityVerdict.MISMATCH, deviation_confirmed=False)


def test_an_uncertain_suggestion_preserves_the_absence_of_explicit_confirmation() -> None:
    choice: EpisodeChoice = replace(_selective().assignments[0].choice, deviation_confirmed=False)
    assert choice.verdict is IdentityVerdict.INSUFFICIENT
    assert not choice.deviation_confirmed


def test_a_saved_episode_mapping_loads_equal_and_builds_the_same_identity_target_for_every_number(
    tmp_path: Path,
) -> None:
    season: int = 182205
    mapping: AniZipMapping = replace(_fixture_mapping(season), max_age_s=None)
    record: SubscriptionRecord = SubscriptionRecord(
        "s", season, "Slime", _TIMESTAMP, 0, kitsu_id=mapping.kitsu_id, mapping=mapping
    )
    store: WatchStateStore = _store(tmp_path)
    store.save(replace(_state(), subscriptions=(record,)))
    loaded: AniZipMapping | None = store.load().subscriptions[0].mapping
    graph: FranchiseGraph = _fixture_graph(101280)
    assert loaded == mapping
    assert loaded is not None
    assert json.dumps(loaded.raw_episodes) == json.dumps(mapping.raw_episodes)
    assert [identity_target(graph, season, loaded, number) for number in range(1, 30)] == [
        identity_target(graph, season, mapping, number) for number in range(1, 30)
    ]


def test_a_saved_mapped_episode_keeps_both_title_languages_and_rejects_a_single_title_key(tmp_path: Path) -> None:
    episode: ListedEpisode = ListedEpisode(8, title_en="Yatan's High Priest", title_romaji="Yatan no Saishichou")
    mapping: AniZipMapping = AniZipMapping(None, "TV", 12, (episode,), (), None, {})
    record: SubscriptionRecord = SubscriptionRecord("s", 500, "Overgeared", _TIMESTAMP, 0, mapping=mapping)
    store: WatchStateStore = _store(tmp_path)
    store.save(replace(_state(), subscriptions=(record,)))
    assert store.load().subscriptions[0].mapping == mapping
    path: Path = tmp_path / WATCH_STATE_FILE_NAME
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    saved: dict[str, object] = document["subscriptions"][0]["mapping"]["episodes"][0]
    assert (saved["title_en"], saved["title_romaji"]) == ("Yatan's High Priest", "Yatan no Saishichou")
    title: object = saved.pop("title_en")
    del saved["title_romaji"]
    saved["title"] = title
    _write(tmp_path, document)
    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        store.load()


_CHOICE_KEYS: dict[str, tuple[str, ...]] = {
    "subscription": ("tsukihime_id", "mapping_tvdb_season"),
    "target": ("started", "threshold", "failures", "polish", "sources_down_since", "polish_skip"),
    "assignment": ("traits", "stopped"),
}


def _choice_state() -> WatchState:
    target: SubscriptionTarget = SubscriptionTarget(
        1,
        _TIMESTAMP,
        TargetState.DUE,
        attempts=1,
        tried=("a" * 40, "ffee:2"),
        started=2,
        threshold=ResolutionClass.HD,
        failures=(ReleaseFailure("b" * 40, decisive=True), ReleaseFailure("c" * 40, transient=MAX_TRANSIENT_FAILURES)),
        polish=PolishObservation(PolishState.ABSENT, _TIMESTAMP),
        sources_down_since=_TIMESTAMP,
        polish_skip=PolishSkip(_TIMESTAMP, _TIMESTAMP, settled=True),
    )
    record: SubscriptionRecord = SubscriptionRecord(
        "s",
        500,
        "Neko",
        _TIMESTAMP,
        0,
        mapping=AniZipMapping(None, "TV", 12, (), (), None, {"1": {"seasonNumber": 2, "episodeNumber": 1}}),
        targets=(target,),
        tsukihime_id=77,
        mapping_tvdb_season=2,
    )
    selective: AcquisitionConfirmation = _selective()
    assignment: EpisodeAssignment = selective.assignments[0]
    traits: ChoiceTraits = ChoiceTraits(PolishClass.BARE, ResolutionClass.FULL_HD, ("hardsub", "raw"))
    chosen: EpisodeAssignment = replace(assignment, choice=replace(assignment.choice, traits=traits), stopped="pack")
    return replace(
        _state(),
        subscriptions=(record,),
        removed_subscription=replace(record, subscription_id="gone", anilist_id=501),
        acquisitions=(replace(selective, assignments=(chosen,)),),
    )


def _saved_objects(document: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    records: list[dict[str, object]] = [
        *cast("list[dict[str, object]]", document["subscriptions"]),
        cast("dict[str, object]", document["removed_subscription"]),
    ]
    return {
        "subscription": records,
        "target": [item for record in records for item in cast("list[dict[str, object]]", record["targets"])],
        "assignment": [
            item
            for acquisition in cast("list[dict[str, object]]", document["acquisitions"])
            for item in cast("list[dict[str, object]]", acquisition["assignments"])
        ],
    }


def _saved_document(tmp_path: Path, state: WatchState) -> dict[str, object]:
    _store(tmp_path).save(state)
    return cast("dict[str, object]", json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8")))


def test_the_current_schema_roundtrip(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    state: WatchState = _choice_state()

    store.save(state)

    assert store.load() == state
    written: dict[str, object] = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert written["schema_version"] == WATCH_STATE_SCHEMA_VERSION
    assert all("settings" not in request for request in cast("list[dict[str, object]]", written["requests"]))


@pytest.mark.parametrize("tsukihime_id", [None, 77])
def test_tsukihime_id_roundtrip(tmp_path: Path, tsukihime_id: int | None) -> None:
    store: WatchStateStore = _store(tmp_path)
    state: WatchState = _choice_state()
    record: SubscriptionRecord = replace(state.subscriptions[0], tsukihime_id=tsukihime_id)

    store.save(replace(state, subscriptions=(record,)))

    assert store.load().subscriptions[0].tsukihime_id == tsukihime_id


@pytest.mark.parametrize("tried", [False, True])
def test_polish_skip_roundtrip_and_reads_a_skip_saved_without_tried(tmp_path: Path, tried: bool) -> None:
    state: WatchState = _choice_state()
    target: SubscriptionTarget = state.subscriptions[0].targets[0]
    skip: PolishSkip = PolishSkip(_TIMESTAMP, _TIMESTAMP, tried=tried)
    record: SubscriptionRecord = replace(state.subscriptions[0], targets=(replace(target, polish_skip=skip),))
    document: dict[str, object] = _saved_document(tmp_path, replace(state, subscriptions=(record,)))
    saved: dict[str, object] = cast("dict[str, object]", _saved_objects(document)["target"][0]["polish_skip"])

    assert saved == {"due": _TIMESTAMP, "at": _TIMESTAMP, "settled": False, "tried": tried}
    assert _store(tmp_path).load().subscriptions[0].targets[0].polish_skip == skip
    saved.pop("tried")
    (tmp_path / WATCH_STATE_FILE_NAME).write_text(json.dumps(document), encoding="utf-8")
    assert _store(tmp_path).load().subscriptions[0].targets[0].polish_skip == replace(skip, tried=False)


@pytest.mark.parametrize(
    ("field", "value", "saved_value"),
    [
        ("blocker", None, None),
        ("blocker", Blocker.THRESHOLD, "threshold"),
        ("polish_buffer_min", None, None),
        ("polish_buffer_min", 120, 120),
    ],
)
def test_optional_target_fact_roundtrip_and_reads_a_target_saved_without_it(
    tmp_path: Path, field: str, value: object, saved_value: object
) -> None:
    state: WatchState = _choice_state()
    target: SubscriptionTarget = replace(state.subscriptions[0].targets[0], **{field: value})  # type: ignore[arg-type]
    record: SubscriptionRecord = replace(state.subscriptions[0], targets=(target,))
    document: dict[str, object] = _saved_document(tmp_path, replace(state, subscriptions=(record,)))
    saved: dict[str, object] = _saved_objects(document)["target"][0]

    assert saved[field] == saved_value
    assert getattr(_store(tmp_path).load().subscriptions[0].targets[0], field) == value
    saved.pop(field)
    _write(tmp_path, document)
    assert getattr(_store(tmp_path).load().subscriptions[0].targets[0], field) is None


def test_failures_roundtrip(tmp_path: Path) -> None:
    document: dict[str, object] = _saved_document(tmp_path, _choice_state())
    target: dict[str, object] = _saved_objects(document)["target"][0]

    assert target["failures"] == [
        {"hash": "b" * 40, "decisive": True, "transient": 0},
        {"hash": "c" * 40, "decisive": False, "transient": MAX_TRANSIENT_FAILURES},
    ]
    assert (
        _store(tmp_path).load().subscriptions[0].targets[0].failures
        == _choice_state().subscriptions[0].targets[0].failures
    )


def test_choice_traits_are_saved_under_the_assignment(tmp_path: Path) -> None:
    document: dict[str, object] = _saved_document(tmp_path, _choice_state())
    assignment: dict[str, object] = _saved_objects(document)["assignment"][0]

    assert (assignment["traits"], assignment["stopped"]) == (
        {"polish": "bare", "resolution": 0, "unusable": ["hardsub", "raw"]},
        "pack",
    )


@pytest.mark.parametrize(("place", "key"), [(place, key) for place, keys in _CHOICE_KEYS.items() for key in keys])
def test_a_saved_choice_fact_is_required(tmp_path: Path, place: str, key: str) -> None:
    document: dict[str, object] = _saved_document(tmp_path, _choice_state())
    _saved_objects(document)[place][0].pop(key)
    _write(tmp_path, document)

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        _store(tmp_path).load()


@pytest.mark.parametrize(
    ("place", "key", "value"),
    [
        ("target", "started", 0),
        ("target", "threshold", 5),
        ("target", "failures", [{"hash": "B" * 40, "decisive": False, "transient": 0}]),
        ("target", "failures", [{"hash": "b" * 40, "decisive": False, "transient": MAX_TRANSIENT_FAILURES + 1}]),
        ("target", "polish", {"state": "maybe", "observed_at": _TIMESTAMP}),
        ("assignment", "traits", {"polish": "Polish", "resolution": 0, "unusable": []}),
        ("assignment", "traits", {"polish": "polish", "resolution": 0, "unusable": ["raw", "hardsub"]}),
        ("assignment", "stopped", "later"),
    ],
)
def test_an_invalid_choice_fact_is_refused(tmp_path: Path, place: str, key: str, value: object) -> None:
    document: dict[str, object] = _saved_document(tmp_path, _choice_state())
    _saved_objects(document)[place][0][key] = value
    _write(tmp_path, document)

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        _store(tmp_path).load()


def test_compaction_keeps_the_choice_traits_through_a_restart(tmp_path: Path) -> None:
    state: WatchState = _choice_state()
    finished: AcquisitionConfirmation = compact_acquisition(
        replace(state.acquisitions[0], state=AcquisitionState.COMPLETE, cleaned=True)
    )
    store: WatchStateStore = _store(tmp_path)

    store.save(replace(state, acquisitions=(finished,)))

    assert finished.assignments[0].choice.target == {}
    assert store.load().acquisitions[0].assignments[0].choice.traits == ChoiceTraits(
        PolishClass.BARE, ResolutionClass.FULL_HD, ("hardsub", "raw")
    )


def test_choice_traits_snapshot_the_ranked_release_facts() -> None:
    traits: ReleaseTraits = ReleaseTraits(
        PolishClass.POLISH, False, False, AudioClass.ORIGINAL, True, True, False, 720, False, None, False
    )

    assert choice_traits(traits) == ChoiceTraits(PolishClass.POLISH, ResolutionClass.HD, ("dub_only", "raw"))


def test_the_state_lives_beside_the_other_watch_files() -> None:
    path: Path = watch_state_path()

    assert path.name == WATCH_STATE_FILE_NAME
    assert path.parent.name == "watch"
    assert path.parent.parent.name == "config"

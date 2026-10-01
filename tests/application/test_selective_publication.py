from __future__ import annotations

import os
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from fakes import FakeMediaProbe, FakeTranslationService
from test_automation import _request
from test_selective_lifecycle import (
    _HASH,
    _choice,
    _running,
    _SelectiveNetwork,
    _Setup,
    _starts,
    _state,
    _stored,
    _until,
    _view,
)
from test_service import _service

from anishift.application import automation as automation_module
from anishift.application import watch as watch_module
from anishift.application.acquisition import AcquisitionService, TorrentClient, TorrentManagement
from anishift.application.acquisition_staging import (
    SetPublication,
    clean_staging,
    copy_staged,
    publish_set,
    published_copy,
)
from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState, create_group_id
from anishift.application.automation import AutomationOwner
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    EpisodePublication,
    FileStamp,
    PublishedFile,
    ReadyGroup,
    RequestState,
)
from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.intents import AutoPreset, ProductIntent, ProductKind
from anishift.application.ready import ReadyMove, ReadyStore
from anishift.application.service import AppService
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore
from anishift.application.workflows import WorkflowTarget
from anishift.config.presets import AutoPresetFile
from anishift.platform.directory_watch import DirectoryChange
from anishift.platform.local_control import ControlResponse
from anishift.services.torrents import TorrentFile, parse_release_name

_VIDEO: bytes = b"v" * 400

_SUBTITLES: bytes = b"s" * 40

_NAMES: list[str] = ["Neko to Ryuu - 03.mkv", "Neko to Ryuu - 03.ass"]

_REAL_LINK: Callable[[str | os.PathLike[str], str | os.PathLike[str]], None] = os.link

_REAL_SETTLE: Callable[..., None] = AutomationOwner._settle_publication


class _Crash(BaseException):
    pass


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Setup:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    monkeypatch.setattr(automation_module, "PANEL_TRANSFER_CHECK_INTERVAL_S", 0.01)
    return _Setup(_SelectiveNetwork(), WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME), tmp_path)


class _Group:
    def __init__(self, paths: tuple[Path, ...]) -> None:
        self.artifacts: tuple[Artifact, ...] = tuple(
            Artifact(
                artifact_id=f"artifact-{index}",
                group_id="group",
                kind=ArtifactKind.SOURCE_SUBTITLES,
                lifetime=ArtifactLifetime.SOURCE,
                state=ArtifactState.READY,
                path=path,
                planned_destination=path,
            )
            for index, path in enumerate(paths)
        )


def _crash_at(boundary: str, owners: list[AutomationOwner], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    crashed: list[str] = []

    def crash(point: str) -> None:
        if point == boundary and not crashed:
            crashed.append(boundary)
            owners[0].request_shutdown()
            raise _Crash

    def copy(source: Path, target: Path, size: int) -> tuple[str, FileStamp]:
        crash("reserved")
        result: tuple[str, FileStamp] = copy_staged(source, target, size)
        crash("copied")
        return result

    def publish(root: Path, private: Path, files: Sequence[PublishedFile]) -> SetPublication:
        crash("proven")
        result: SetPublication = publish_set(root, private, files)
        crash("published")
        return result

    def link(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
        _REAL_LINK(source, destination)
        crash("linked")

    def settle(self: AutomationOwner, *args: object) -> None:
        _REAL_SETTLE(self, *args)
        if boundary == "handed_off" and not crashed:
            crashed.append(boundary)
            self.request_shutdown()

    monkeypatch.setattr("anishift.application.automation.copy_staged", copy)
    monkeypatch.setattr("anishift.application.automation.publish_set", publish)
    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(AutomationOwner, "_settle_publication", settle)
    return crashed


def _download(setup: _Setup, owner: AutomationOwner, *, sidecar: bool = True) -> Path:
    assert owner.admit_episode("admit-1", _choice(3)).ok
    _until(lambda: bool(setup.network.metadata_added))
    setup.network.deliver(_HASH)
    _until(_starts(setup))
    data: Path = setup.root / "temp" / ".acquisition" / str(_view(owner)["operation_id"]) / "data"
    (data / "Pack").mkdir(parents=True, exist_ok=True)
    (data / "Pack" / _NAMES[0]).write_bytes(_VIDEO)
    if sidecar:
        (data / "Pack" / _NAMES[1]).write_bytes(_SUBTITLES)
    _until(lambda: setup.network.tracked[_HASH].state == "downloading")
    setup.network.finish(_HASH)
    return data


def _publication(setup: _Setup) -> EpisodePublication | None:
    return _stored(setup).assignments[0].publication


def _current(owner: AutomationOwner) -> AcquisitionConfirmation:
    return owner.state.acquisitions[0]


def _problem(owner: AutomationOwner) -> bool:
    publication: EpisodePublication | None = _current(owner).assignments[0].publication
    return publication is not None and publication.problem is not None


def _settled(owner: AutomationOwner) -> bool:
    current: AcquisitionConfirmation = _current(owner)
    return current.state is AcquisitionState.COMPLETE and current.cleaned


def _root_files(setup: _Setup) -> set[str]:
    return {path.name for path in setup.root.iterdir() if path.suffix in {".mkv", ".ass"}}


def test_completed_transfer_retries_an_unconfirmed_release_without_restart(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    release: Callable[[frozenset[str]], frozenset[str]] = setup.network.release_completed
    attempts: list[frozenset[str]] = []

    def delayed(hashes: frozenset[str]) -> frozenset[str]:
        attempts.append(hashes)
        return frozenset() if len(attempts) <= automation_module._FINALIZE_ATTEMPTS + 2 else release(hashes)

    monkeypatch.setattr(setup.network, "release_completed", delayed)
    with _running(setup) as owner:
        _download(setup, owner)
        _until(lambda: _settled(owner))
    assert len(attempts) > automation_module._FINALIZE_ATTEMPTS + 2


@pytest.mark.parametrize("cancel", [False, True])
def test_removal_or_cancel_preserves_a_handed_off_episode(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch, *, cancel: bool
) -> None:
    monkeypatch.setattr(setup.network, "release_completed", lambda hashes: frozenset())
    with _running(setup) as owner:
        _download(setup, owner)
        _until(lambda: _current(owner).assignments[0].publication is not None)
        _until(
            lambda: (publication := _current(owner).assignments[0].publication) is not None and publication.handed_off
        )
        before: set[str] = _root_files(setup)
        if cancel:
            assert owner.handle(_request("transfer", {"info_hash": _HASH, "action": "cancel"})).ok
            _until(lambda: _current(owner).state is AcquisitionState.FAILED)
        else:
            setup.network.tracked.clear()

            def inspect_removed() -> None:
                assert owner._replace_acquisition(
                    replace(_current(owner), state=AcquisitionState.ACCEPTED, content_started=True)
                )
                owner._schedule_transfers()

            owner._on_owner(inspect_removed)
            _until(lambda: _current(owner).state is AcquisitionState.FAILED)
        assert not owner.admit_episode("again", _choice(3)).ok
        assert _status(owner)["state"] != "not_ordered"
        assert _root_files(setup) == before


def test_cleanup_runs_after_release_even_when_finishing_the_client_fails(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse() -> None:
        raise OSError(13, "Client shutdown failed")

    monkeypatch.setattr(setup.network, "finish_transfers", refuse)
    with _running(setup) as owner:
        data: Path = _download(setup, owner)
        _until(lambda: _settled(owner))
        assert not data.parent.exists()


@pytest.mark.parametrize("external", [False, True])
def test_unmanageable_completed_transfer_parks_until_an_explicit_retry(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch, *, external: bool
) -> None:
    attempts: list[frozenset[str]] = []

    def held(hashes: frozenset[str]) -> frozenset[str]:
        attempts.append(hashes)
        return frozenset()

    monkeypatch.setattr(setup.network, "release_completed", held)
    monkeypatch.setattr(setup.network, "finalizable_hashes", lambda hashes: frozenset(), raising=False)
    with _running(setup) as owner:
        _download(setup, owner)
        if external:
            acquisition: AcquisitionService = cast("AcquisitionService", owner._service.acquisition)
            monkeypatch.setattr(acquisition, "_torrent_management", None)
            monkeypatch.setattr(acquisition, "release_completed", held)
        _until(lambda: _current(owner).state is AcquisitionState.COMPLETE and bool(attempts))
        time.sleep(0.1)
        count: int = len(attempts)
        time.sleep(0.1)
        assert len(attempts) == count
        assert owner._on_owner(lambda: owner._transfers_at) is None
        assert not _current(owner).cleaned
        assert owner.handle(_request("ready_retry")).ok
        _until(lambda: len(attempts) > count)


def test_cleanup_problem_preserves_downloaded_state_and_material_reason(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*args: object) -> None:
        raise OSError(13, "Cleanup failed")

    monkeypatch.setattr(automation_module, "clean_staging", refuse)
    with _running(setup) as owner:
        _download(setup, owner)
        _until(lambda: _current(owner).problem == automation_module._CLEANUP_FAILED)
        status: dict[str, object] = _status(owner)
        assert status["state"] == "downloaded"
        assert status["reason"] == "finalization_failed"
        response: ControlResponse = owner.handle(_request("status"))
        materials: list[dict[str, object]] = cast("list[dict[str, object]]", response.result["materials"])
        row: dict[str, object] = next(item for item in materials if item.get("admission_id"))
        assert row["stage"] == "waiting"
        assert row["reason"] == "finalization_failed"


def test_finalization_recognizes_cleanup_done_by_a_successor_without_a_second_release(setup: _Setup) -> None:
    with _running(setup) as owner:
        _download(setup, owner)
        _until(lambda: _settled(owner))
        current: AcquisitionConfirmation = _current(owner)

        def settle() -> None:
            owner._completion_done.discard(current.operation_id)
            owner._completion_attempts[current.operation_id] = automation_module._FINALIZE_ATTEMPTS
            owner._active_io += 1
            owner._released_completed(None, attempted=(current,))

        owner._on_owner(settle)
        assert current.operation_id in owner._completion_done
        assert _current(owner).problem is None


def test_cleanup_retries_a_transient_windows_file_lock(setup: _Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    unlink: Callable[..., None] = Path.unlink
    denied: list[Path] = []

    def transient(path: Path, *, missing_ok: bool = False) -> None:
        if path.name == _NAMES[0] and path.parent.name == "Pack" and not denied:
            denied.append(path)
            raise PermissionError(13, "Sharing violation", str(path), 32)
        unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", transient)
    with _running(setup) as owner:
        _download(setup, owner)
        _until(lambda: _settled(owner))
    assert len(denied) == 1


def _status(owner: AutomationOwner) -> dict[str, object]:
    answer: ControlResponse = owner.handle(
        _request("episode_states", {"anilist_id": 500, "numbers": [3]}, command_id="states-1")
    )
    assert answer.ok
    return cast("list[dict[str, object]]", answer.result["items"])[0]


def test_a_finished_episode_is_published_whole_handed_off_released_and_its_staging_cleaned(setup: _Setup) -> None:
    with _running(setup) as owner:
        data: Path = _download(setup, owner)
        _until(lambda: _settled(owner))
        status: dict[str, object] = _status(owner)
        snapshot: ControlResponse = owner.handle(_request("status"))
        materials: list[dict[str, object]] = cast("list[dict[str, object]]", snapshot.result["materials"])
        group_id: str | None = _current(owner).assignments[0].group_id
        assert any(row.get("group_id") == group_id and row["stage"] == "waiting" for row in materials)

    stored: AcquisitionConfirmation = _stored(setup)
    assert stored.manifest == ()
    assert stored.assignments[0].publication is None
    assert stored.assignments[0].choice.target == {}
    assert stored.assignments[0].group_id is not None
    assert stored.required_files == ()
    assert stored.assignments[0].video_path == f"Pack/{_NAMES[0]}"
    with _running(setup) as restarted:
        duplicate: ControlResponse = restarted.admit_episode("duplicate-after-cleanup", _choice(3))
        assert not duplicate.ok
        assert duplicate.reason == "episode_admitted"
    assert (setup.root / _NAMES[0]).read_bytes() == _VIDEO
    assert (setup.root / _NAMES[1]).read_bytes() == _SUBTITLES
    assert frozenset({_HASH}) in setup.network.released
    assert not data.parent.exists()
    assert status["state"] in {"downloaded", "processing"}


def test_a_name_taken_before_publication_moves_the_whole_set_to_one_free_core(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    owners: list[AutomationOwner] = []
    reserved: list[tuple[str, ...]] = []

    def copy(source: Path, target: Path, size: int) -> tuple[str, FileStamp]:
        saved: EpisodePublication | None = _current(owners[0]).assignments[0].publication
        reserved.append(() if saved is None else tuple(item.name for item in saved.files))
        return copy_staged(source, target, size)

    monkeypatch.setattr("anishift.application.automation.copy_staged", copy)
    (setup.root / _NAMES[0]).write_bytes(b"foreign")
    with _running(setup) as owner:
        owners.append(owner)
        _download(setup, owner)
        _until(lambda: _settled(owner))

    assert set(reserved) == {("Neko to Ryuu - 03 [2].mkv", "Neko to Ryuu - 03 [2].ass")}
    assert _stored(setup).assignments[0].group_id == create_group_id(Path(), "Neko to Ryuu - 03 [2]")
    assert (setup.root / _NAMES[0]).read_bytes() == b"foreign"
    assert (setup.root / "Neko to Ryuu - 03 [2].mkv").read_bytes() == _VIDEO
    assert (setup.root / "Neko to Ryuu - 03 [2].ass").read_bytes() == _SUBTITLES


def test_a_name_taken_after_the_first_link_moves_the_whole_set_without_replacing_the_occupant(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    links: list[Path] = []

    def link(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
        _REAL_LINK(source, destination)
        links.append(Path(destination))
        if len(links) == 1:
            (setup.root / _NAMES[1]).write_bytes(b"foreign")

    monkeypatch.setattr(os, "link", link)
    with _running(setup) as owner:
        _download(setup, owner)
        _until(lambda: _settled(owner))

    assert _stored(setup).problem is None
    assert _stored(setup).assignments[0].group_id is not None
    assert (setup.root / _NAMES[1]).read_bytes() == b"foreign"
    assert not (setup.root / _NAMES[0]).exists()
    assert (setup.root / "Neko to Ryuu - 03 [2].mkv").read_bytes() == _VIDEO
    assert (setup.root / "Neko to Ryuu - 03 [2].ass").read_bytes() == _SUBTITLES


def test_an_episode_whose_sidecar_is_not_finished_is_not_published_until_the_whole_set_is(setup: _Setup) -> None:
    with _running(setup) as owner:
        data: Path = _download(setup, owner, sidecar=False)
        subtitles: Path = data / "Pack" / _NAMES[1]
        polled: int = setup.network.info_calls
        _until(lambda: setup.network.info_calls > polled + 5)
        waiting: EpisodePublication | None = _current(owner).assignments[0].publication
        blocked: set[str] = _root_files(setup)
        subtitles.write_bytes(_SUBTITLES)
        _until(lambda: _settled(owner))

    assert waiting is None
    assert blocked == set()
    assert _root_files(setup) == set(_NAMES)


def test_a_publication_step_taken_on_an_older_saved_step_is_discarded(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    owners: list[AutomationOwner] = []

    def interfere() -> None:
        owner: AutomationOwner = owners[0]
        current: AcquisitionConfirmation = _current(owner)
        publication: EpisodePublication | None = current.assignments[0].publication
        assert publication is not None
        changed: EpisodePublication = replace(publication, problem="changed meanwhile")
        assert owner._replace_acquisition(
            replace(current, assignments=(replace(current.assignments[0], publication=changed),))
        )

    def copy(source: Path, target: Path, size: int) -> tuple[str, FileStamp]:
        if _current(owners[0]).assignments[0].publication.problem is None:  # type: ignore[union-attr]
            owners[0]._on_owner(interfere)
        return copy_staged(source, target, size)

    monkeypatch.setattr("anishift.application.automation.copy_staged", copy)
    with _running(setup) as owner:
        owners.append(owner)
        _download(setup, owner)
        _until(lambda: _problem(owner))
        polled: int = setup.network.info_calls
        _until(lambda: setup.network.info_calls > polled + 5)
        publication: EpisodePublication | None = _current(owner).assignments[0].publication

    assert publication is not None
    assert publication.problem == "changed meanwhile"
    assert not publication.copied
    assert _root_files(setup) == set()


@pytest.mark.parametrize("recovered", [False, True])
def test_failed_cleanup_exhausts_bounded_retries_and_restarts_its_budget_after_restart(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch, *, recovered: bool
) -> None:
    attempts: list[int] = []

    def refuse(*args: object) -> None:
        attempts.append(len(attempts))
        raise OSError(13, "Access is denied")

    monkeypatch.setattr("anishift.application.automation.clean_staging", refuse)
    with _running(setup) as owner:
        data: Path = _download(setup, owner)
        _until(lambda: _current(owner).problem == automation_module._CLEANUP_FAILED)
        _until(lambda: len(attempts) == automation_module._FINALIZE_ATTEMPTS)
        _until(lambda: owner._on_owner(owner._pending_completion) == ())
        assert owner.admit_episode(
            "admit-2", replace(_choice(4), reference=replace(_choice(4).reference, info_hash="next"))
        ).ok
        polled: int = setup.network.info_calls
        _until(lambda: setup.network.info_calls > polled + 5)
        assert len(attempts) == automation_module._FINALIZE_ATTEMPTS
        assert _stored(setup).manifest
        assert not _stored(setup).cleaned
        assert (data / "Pack" / _NAMES[0]).read_bytes() == _VIDEO
    if recovered:
        monkeypatch.setattr("anishift.application.automation.clean_staging", clean_staging)
    with _running(setup) as owner:
        if recovered:
            _until(lambda: _settled(owner))
        else:
            _until(lambda: len(attempts) == automation_module._FINALIZE_ATTEMPTS * 2)
        polled = setup.network.info_calls
        _until(lambda: setup.network.info_calls > polled + 5)
        assert _stored(setup).cleaned is recovered

    assert _stored(setup).problem == (None if recovered else automation_module._CLEANUP_FAILED)
    assert data.parent.exists() is not recovered
    assert _root_files(setup) == set(_NAMES)


def test_a_failed_copy_is_reported_and_an_explicit_resume_publishes_the_set(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    failures: list[int] = []

    def copy(source: Path, target: Path, size: int) -> tuple[str, FileStamp]:
        if not failures:
            failures.append(size)
            raise OSError(28, "No space left on device")
        return copy_staged(source, target, size)

    monkeypatch.setattr("anishift.application.automation.copy_staged", copy)
    with _running(setup) as owner:
        _download(setup, owner)
        _until(lambda: _problem(owner))
        blocked: set[str] = _root_files(setup)
        resumed: ControlResponse = owner.handle(
            _request("transfer", {"info_hash": _HASH, "action": "resume"}, command_id="resume-1")
        )
        _until(lambda: setup.network.tracked[_HASH].state == "downloading")
        setup.network.finish(_HASH)
        _until(lambda: _settled(owner))

    assert blocked == set()
    assert resumed.ok
    assert (setup.root / _NAMES[0]).read_bytes() == _VIDEO


def test_auto_ignores_a_set_that_is_not_handed_off_yet(setup: _Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup.network, "release_completed", lambda hashes: frozenset())
    with _running(setup) as owner:
        _download(setup, owner)
        _until(lambda: _current(owner).state is AcquisitionState.COMPLETE)
        stored: AcquisitionConfirmation = _stored(setup)
        publication: EpisodePublication | None = stored.assignments[0].publication
        assert publication is not None
        group: InspectedSourceGroup = cast("InspectedSourceGroup", _Group(tuple(setup.root / name for name in _NAMES)))
        handed: object = owner._on_owner(lambda: owner._file_origin(group))
        pending: AcquisitionConfirmation = replace(
            stored, assignments=(replace(stored.assignments[0], publication=replace(publication, handed_off=False)),)
        )
        assert owner._on_owner(lambda: owner._replace_acquisition(pending))
        waiting: object = owner._on_owner(lambda: owner._file_origin(group))

    assert handed is stored.origin
    assert waiting is None


class _ProcessingSetup(_Setup):
    def owner(self) -> AutomationOwner:
        acquisition: AcquisitionService = AcquisitionService(
            source=self.network,
            client=cast("TorrentClient", self.network),
            workspace_root=self.root,
            parse_name=parse_release_name,
            torrent_management=cast("TorrentManagement", self.network),
        )
        preset: AutoPreset = AutoPreset("subtitles", "Subtitles", ProductIntent(frozenset({ProductKind.FULL_PL})))
        service: AppService = _service(
            self.root,
            FakeTranslationService(),
            inspector=WorkspaceInspector(FakeMediaProbe()),
            preset_store=[AutoPresetFile(1, (preset,), preset.preset_id)],
            acquisition=acquisition,
        )
        owner: AutomationOwner = AutomationOwner(
            service,
            self.store,
            instance_id="instance-1",
            scan_interval_s=0.01,
            ready_store=ReadyStore(self.root / ".relocations", self.root),
        )
        owner.files_changed(DirectoryChange(reconcile=True, reason="initial"))
        return owner


@pytest.mark.parametrize("boundary", ["reserved", "copied", "proven", "linked", "published", "handed_off", "processed"])
def test_only_the_ordered_episode_enters_one_real_auto_run_across_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    monkeypatch.setattr(watch_module, "QUIET_S", 0.02)
    monkeypatch.setattr(watch_module, "SCAN_INTERVAL_S", 0.01)
    setup: _ProcessingSetup = _ProcessingSetup(_SelectiveNetwork(), WatchStateStore(tmp_path / "state.json"), tmp_path)
    subtitles: bytes = b"1\n00:00:00,000 --> 00:00:01,000\nHello\n"
    names: tuple[str, ...] = (_NAMES[0], _NAMES[1].replace(".ass", ".srt"))
    owners: list[AutomationOwner] = []
    crashed: list[str] = _crash_at(boundary, owners, monkeypatch)
    with _running(setup) as owner:
        owners.append(owner)
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(
            _HASH,
            (
                TorrentFile(0, f"Pack/{names[0]}", len(_VIDEO), 0.0, 1),
                TorrentFile(1, f"Pack/{names[1]}", len(subtitles), 0.0, 1),
                TorrentFile(2, "Pack/Neko to Ryuu - 04.mkv", 410, 0.0, 1),
            ),
        )
        _until(_starts(setup))
        data: Path = setup.network.metadata_added[0][2]
        (data / "Pack").mkdir(parents=True, exist_ok=True)
        (data / "Pack" / names[0]).write_bytes(_VIDEO)
        (data / "Pack" / names[1]).write_bytes(subtitles)
        (data / "Pack" / "Neko to Ryuu - 04.mkv").write_bytes(b"unrequested")
        setup.network.finish(_HASH)
        if boundary == "processed":
            _until(lambda: bool(owner.state.ready_groups))
        else:
            _until(lambda: bool(crashed))
    with _running(setup) as owner:
        _until(lambda: bool(owner.state.ready_groups) and _settled(owner))
        owner.files_changed(DirectoryChange(reconcile=True))
        owner.files_changed(DirectoryChange(paths=(data / "Pack" / "Neko to Ryuu - 04.mkv",)))
        _until(lambda: len(owner.state.requests) == 1 and owner.state.requests[0].state is RequestState.SUCCEEDED)
        groups: tuple[str, ...] = tuple(group.source.stem for group in owner._service.discover().groups)
        status: dict[str, object] = _status(owner)

    assert groups == ("Neko to Ryuu - 03",)
    assert len(_state(setup).requests) == 1
    assert _state(setup).requests[0].attempts == 1
    assert (tmp_path / "ready" / names[0]).read_bytes() == _VIDEO
    assert (tmp_path / "ready" / names[1]).read_bytes() == subtitles
    assert not data.parent.exists()
    assert status["state"] == "ready"
    assert setup.network.selections == [(_HASH, frozenset({0, 1}))]


@pytest.mark.parametrize("pause_before", [False, True])
def test_manual_download_reaches_library_under_pause_and_resume_deduplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pause_before: bool
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    monkeypatch.setattr(watch_module, "QUIET_S", 0.02)
    monkeypatch.setattr(watch_module, "SCAN_INTERVAL_S", 0.01)
    setup: _ProcessingSetup = _ProcessingSetup(_SelectiveNetwork(), WatchStateStore(tmp_path / "state.json"), tmp_path)
    subtitles: bytes = b"1\n00:00:00,000 --> 00:00:01,000\nHello\n"
    name: str = "Neko to Ryuu - 03.srt"
    with _running(setup) as owner:
        if pause_before:
            assert owner.handle(_request("set_auto", {"enabled": False}, command_id="pause")).ok
        assert owner.admit_episode("admit", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(
            _HASH,
            (
                TorrentFile(0, f"Pack/{_NAMES[0]}", len(_VIDEO), 0.0, 1),
                TorrentFile(1, f"Pack/{name}", len(subtitles), 0.0, 1),
            ),
        )
        _until(_starts(setup))
        if not pause_before:
            assert owner.handle(_request("set_auto", {"enabled": False}, command_id="pause")).ok
        assert owner.state.pause_owned_transfers == ()
        data: Path = setup.network.metadata_added[0][2] / "Pack"
        data.mkdir(parents=True, exist_ok=True)
        (data / _NAMES[0]).write_bytes(_VIDEO)
        (data / name).write_bytes(subtitles)
        unrelated: Path = tmp_path / "unrelated.srt"
        unrelated.write_bytes(subtitles)
        unrelated_video: Path = tmp_path / "unrelated.mkv"
        unrelated_video.write_bytes(_VIDEO)
        owner.files_changed(DirectoryChange(paths=(unrelated, unrelated_video)))
        setup.network.finish(_HASH)
        _until(lambda: bool(owner.state.ready_groups) and _settled(owner))
        assert not owner.state.policy.auto_enabled
        assert len(owner.state.requests) == 1
        assert owner.state.requests[0].state is RequestState.SUCCEEDED
        assert not owner.state.requests[0].automatic
        assert setup.network.actions == []
        assert (tmp_path / "ready" / name).read_bytes() == subtitles
        manual_id: str = owner.state.requests[0].request_id
        assert owner.handle(_request("set_auto", {"enabled": True}, command_id="resume")).ok
        _until(lambda: len(owner.state.requests) == 2)
        assert sum(item.request_id == manual_id for item in owner.state.requests) == 1
        assert len(setup.network.metadata_added) == 1
        assert setup.network.started == [_HASH]


@pytest.mark.parametrize("incomplete", ["size", "sidecar", "progress", "checking"])
def test_incomplete_episode_never_publishes_despite_whole_torrent_progress(setup: _Setup, incomplete: str) -> None:
    with _running(setup) as owner:
        data: Path = _download(setup, owner, sidecar=False)
        if incomplete == "size":
            (data / "Pack" / _NAMES[0]).write_bytes(b"short")
        if incomplete == "progress":
            setup.network.per_hash[_HASH] = tuple(
                replace(item, progress=0.9) if item.index == 1 else item for item in setup.network.per_hash[_HASH]
            )
        if incomplete == "checking":
            setup.network.tracked[_HASH] = replace(setup.network.tracked[_HASH], state="checkingUP")
        if incomplete != "sidecar":
            (data / "Pack" / _NAMES[1]).write_bytes(_SUBTITLES)
        polled: int = setup.network.info_calls
        _until(lambda: setup.network.info_calls > polled + 5)
        assert _root_files(setup) == set()
        assert _current(owner).assignments[0].publication is None
        assert owner.state.requests == ()
        assert setup.network.released == []


def test_one_episode_publishes_while_the_other_ordered_episode_is_still_downloading(setup: _Setup) -> None:
    with _running(setup) as owner:
        assert owner.admit_episode("admit-2", _choice(4)).ok
        data: Path = _download(setup, owner, sidecar=False)
        setup.network.per_hash[_HASH] = tuple(
            replace(item, progress=0.0) if item.index in {2, 3} else item for item in setup.network.per_hash[_HASH]
        )
        setup.network.tracked[_HASH] = replace(
            setup.network.tracked[_HASH], progress=0.5, amount_left=451, state="downloading"
        )
        (data / "Pack" / _NAMES[1]).write_bytes(_SUBTITLES)
        _until(lambda: _root_files(setup) == set(_NAMES))
        assert _current(owner).state is AcquisitionState.ACCEPTED
        assert setup.network.released == []
        assert (data / "Pack" / _NAMES[0]).read_bytes() == _VIDEO


def test_stop_during_copy_preserves_staging_and_blocks_publication(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    owners: list[AutomationOwner] = []
    stopped: list[ControlResponse] = []

    def copy(source: Path, target: Path, size: int) -> tuple[str, FileStamp]:
        if not stopped:
            stopped.append(owners[0].handle(_request("transfer", {"info_hash": _HASH, "action": "stop"})))
        return copy_staged(source, target, size)

    monkeypatch.setattr(automation_module, "copy_staged", copy)
    with _running(setup) as owner:
        owners.append(owner)
        data: Path = _download(setup, owner)
        _until(lambda: bool(stopped) and not _current(owner).action_pending)
        assert stopped[0].ok
        assert _root_files(setup) == set()
        assert owner.state.requests == ()
        assert (data / "Pack" / _NAMES[0]).read_bytes() == _VIDEO


@pytest.mark.parametrize("proof", ["held", "missing", "changed", "ready"])
def test_cleanup_requires_release_and_the_preserved_copy_even_after_ready_relocation(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch, proof: str
) -> None:
    release: Callable[[frozenset[str]], frozenset[str]] = setup.network.release_completed
    monkeypatch.setattr(setup.network, "release_completed", lambda hashes: frozenset())
    with _running(setup) as owner:
        data: Path = _download(setup, owner)
        _until(lambda: _current(owner).state is AcquisitionState.COMPLETE)
        item: AcquisitionConfirmation = _current(owner)
        target: Path = setup.root / _NAMES[0]
        if proof == "missing":
            target.unlink()
        elif proof == "changed":
            stamp: os.stat_result = target.stat()
            target.write_bytes(b"x" * len(_VIDEO))
            os.utime(target, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        elif proof == "ready":
            service: AppService = owner._service
            monkeypatch.setattr(service, "_inspector", WorkspaceInspector(FakeMediaProbe()))
            group: InspectedSourceGroup = service.discover().groups[0]
            ready: ReadyStore = ReadyStore(setup.root / ".relocations", setup.root)
            move: ReadyMove | None = ready.prepare(group.source, ())
            assert move is not None
            ready.execute(move)
            assert owner._on_owner(lambda: owner._save(owner._relocated_state(move)))
    if proof != "held":
        monkeypatch.setattr(setup.network, "release_completed", release)
    with _running(setup) as owner:
        if proof != "held":
            _until(lambda: _settled(owner))
        else:
            assert not _current(owner).cleaned

    if proof == "ready":
        assert _stored(setup).manifest == ()
        assert not data.parent.exists()
        assert (setup.root / "ready" / _NAMES[0]).read_bytes() == _VIDEO
    else:
        assert (data / "Pack" / _NAMES[0]).read_bytes() == _VIDEO
        assert _stored(setup).manifest == item.manifest
        assert _stored(setup).cleaned is (proof != "held")


def test_episode_states_follow_an_episode_from_ordering_to_its_ready_set(setup: _Setup) -> None:
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        ordered: dict[str, object] = _status(owner)
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(_starts(setup))
        _until(lambda: _current(owner).content_started)
        downloading: dict[str, object] = _status(owner)
        data: Path = setup.root / "temp" / ".acquisition" / str(_view(owner)["operation_id"]) / "data" / "Pack"
        data.mkdir(parents=True, exist_ok=True)
        (data / _NAMES[0]).write_bytes(_VIDEO)
        (data / _NAMES[1]).write_bytes(_SUBTITLES)
        _until(lambda: setup.network.tracked[_HASH].state == "downloading")
        setup.network.finish(_HASH)
        _until(lambda: _settled(owner))
        group_id: str = create_group_id(Path(), "Neko to Ryuu - 03")
        record: ReadyGroup = ReadyGroup(
            group_id,
            create_group_id(Path("ready"), "Neko to Ryuu - 03"),
            "Neko to Ryuu - 03",
            "",
            "Neko to Ryuu - 03",
            WorkflowTarget.VIDEO,
            (f"ready/{_NAMES[0]}",),
            (),
        )
        assert owner._on_owner(lambda: owner._save(replace(owner._state, ready_groups=(record,))))
        ready: dict[str, object] = _status(owner)

    assert ordered["state"] == "ordered"
    assert downloading["state"] == "downloading"
    assert (ready["state"], ready["set_id"]) == ("ready", group_id)


def test_cleanup_with_a_protected_original_finishes_once_without_rehashing_on_restart(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked: list[str] = []

    def release(hashes: frozenset[str]) -> frozenset[str]:
        (setup.root / _NAMES[0]).unlink(missing_ok=True)
        return hashes

    def verify(path: Path, item: PublishedFile) -> bool:
        checked.append(item.name)
        return published_copy(path, item)

    monkeypatch.setattr(setup.network, "release_completed", release)
    monkeypatch.setattr(automation_module, "published_copy", verify)
    with _running(setup) as owner:
        data: Path = _download(setup, owner)
        _until(lambda: _settled(owner))
        assert owner._on_owner(owner._pending_completion) == ()
    first: list[str] = list(checked)
    with _running(setup) as owner:
        assert owner._on_owner(owner._pending_completion) == ()

    assert first == _NAMES
    assert checked == first
    assert _stored(setup).cleaned
    assert _stored(setup).problem is None
    assert _stored(setup).manifest
    assert _stored(setup).assignments[0].publication is not None
    assert (data / "Pack" / _NAMES[0]).read_bytes() == _VIDEO


@pytest.mark.parametrize("terminal", ["complete", "failed"])
def test_a_new_episode_from_a_terminal_pack_gets_one_new_transfer_after_restart(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch, terminal: str
) -> None:
    def release(hashes: frozenset[str]) -> frozenset[str]:
        setup.network.released.append(hashes)
        for info_hash in hashes:
            setup.network.tracked.pop(info_hash, None)
            setup.network.per_hash.pop(info_hash, None)
        return hashes

    action: Callable[[str, str], None] = setup.network.transfer_action

    def control(info_hash: str, requested: str) -> None:
        action(info_hash, requested)
        if requested == "cancel":
            setup.network.tracked.pop(info_hash, None)
            setup.network.per_hash.pop(info_hash, None)

    monkeypatch.setattr(setup.network, "release_completed", release)
    monkeypatch.setattr(setup.network, "transfer_action", control)
    with _running(setup) as owner:
        assert owner.admit_episode("admit-5", _choice(5)).ok
        data: Path = _download(setup, owner)
        if terminal == "complete":
            (data / "Pack" / "Neko to Ryuu - 05.mkv").write_bytes(b"v" * 420)
            _until(lambda: _settled(owner))
        else:
            assert owner.handle(
                _request("transfer", {"info_hash": _HASH, "action": "cancel"}, command_id="cancel-1")
            ).ok
            _until(lambda: _current(owner).state is AcquisitionState.FAILED)
        previous: AcquisitionConfirmation = _current(owner)
    with _running(setup) as owner:
        admitted: ControlResponse = owner.admit_episode("admit-4", _choice(4))
        assert admitted.ok
        _until(lambda: len(setup.network.metadata_added) == 2)
        duplicate: ControlResponse = owner.admit_episode("duplicate-3", _choice(3))
        protected: bool = terminal == "complete" or any(
            item.choice.number == 3 and item.publication is not None for item in previous.assignments
        )
        assert (duplicate.ok, duplicate.reason) == ((False, "episode_admitted") if protected else (True, ""))
        setup.network.deliver(_HASH)
        _until(lambda: owner.state.acquisitions[-1].content_started)
        assert len(owner.state.acquisitions) == 2
        assert owner.state.acquisitions[0] == previous
        assert owner.state.acquisitions[-1].operation_id != previous.operation_id
        assert setup.network.metadata_added[1][2] != data
    assert len(setup.network.metadata_added) == 2


def test_lost_handed_off_files_report_a_problem_without_holding_the_remaining_pack(
    setup: _Setup,
) -> None:
    with _running(setup) as owner:
        assert owner.admit_episode("admit-4", _choice(4)).ok
        data: Path = _download(setup, owner)
        setup.network.per_hash[_HASH] = tuple(
            replace(item, progress=0.0) if item.index in {2, 3} else item for item in setup.network.per_hash[_HASH]
        )
        setup.network.tracked[_HASH] = replace(
            setup.network.tracked[_HASH], state="downloading", progress=0.5, amount_left=451
        )
        _until((setup.root / _NAMES[0]).exists)
        _until(
            lambda: (publication := _current(owner).assignments[1].publication) is not None and publication.handed_off
        )
        (setup.root / _NAMES[0]).unlink()
        (data / "Pack" / _NAMES[0]).unlink()
        (data / "Pack" / "Neko to Ryuu - 04.mkv").write_bytes(b"v" * 410)
        (data / "Pack" / "Neko to Ryuu - 04.ass").write_bytes(b"s" * 41)
        setup.network.finish(_HASH)
        _until(lambda: _settled(owner))
        assert _status(owner)["reason"] == "publication_missing"
    assert frozenset({_HASH}) in setup.network.released
    assert (setup.root / "Neko to Ryuu - 04.mkv").read_bytes() == b"v" * 410

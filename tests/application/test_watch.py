from __future__ import annotations

import ctypes
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from anishift.application.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    SourceGroup,
)
from anishift.application.inspection import InspectedSourceGroup, InspectedWorkspace
from anishift.application.intents import VIDEO_PRODUCTS, AutoPreset, ProductIntent, ProductKind
from anishift.application.watch import (
    PARTIAL_SUFFIXES,
    QUIET_S,
    SourceSnapshot,
    WatchLedger,
    is_stable,
    needs_work,
    snapshot_sources,
    source_fingerprint,
)
from anishift.application.workflows import ROOT_ROUTE, WorkflowRoute, WorkflowTarget, WorkspacePlace
from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind

_TRANSLATE_ROUTE: WorkflowRoute = WorkflowRoute(WorkspacePlace.TRANSLATE, WorkflowTarget.TRANSLATE)

_SOURCE_KINDS: frozenset[ArtifactKind] = frozenset(
    {
        ArtifactKind.VIDEO_MKV,
        ArtifactKind.VIDEO_MP4,
        ArtifactKind.SOURCE_SUBTITLES,
        ArtifactKind.SOURCE_AUDIO,
        ArtifactKind.STANDALONE_TEXT,
    },
)

_PRODUCT_ARTIFACT_KINDS: dict[ProductKind, ArtifactKind] = {
    ProductKind.SOURCE_SUBTITLES: ArtifactKind.SOURCE_SUBTITLES,
    ProductKind.FULL_PL: ArtifactKind.FULL_PL,
    ProductKind.SPOKEN_PL: ArtifactKind.SPOKEN_PL,
    ProductKind.DISPLAYED_PL: ArtifactKind.DISPLAYED_PL,
    ProductKind.NARRATION_AUDIO: ArtifactKind.NARRATION_AUDIO,
    ProductKind.MKV: ArtifactKind.FINAL_MKV,
    ProductKind.MP4: ArtifactKind.FINAL_MP4,
    ProductKind.TRANSLATED_TEXT: ArtifactKind.TRANSLATED_TEXT,
}


def _artifact(group_id: str, kind: ArtifactKind, path: Path) -> Artifact:
    lifetime: ArtifactLifetime = ArtifactLifetime.SOURCE if kind in _SOURCE_KINDS else ArtifactLifetime.DURABLE
    return Artifact(
        artifact_id=f"artifact-{group_id}-{kind.value}",
        group_id=group_id,
        kind=kind,
        path=path,
        state=ArtifactState.READY,
        lifetime=lifetime,
        planned_destination=path,
    )


def _group(
    group_id: str,
    stem: str,
    *artifacts: Artifact,
    route: WorkflowRoute = _TRANSLATE_ROUTE,
    media_catalogs: dict[str, MediaCatalog] | None = None,
) -> InspectedSourceGroup:
    source: SourceGroup = SourceGroup(
        group_id=group_id,
        stem=stem,
        directory=Path(),
        artifacts=artifacts,
        route=route,
    )
    return InspectedSourceGroup(
        source=source,
        artifacts=artifacts,
        media_catalogs=media_catalogs if media_catalogs is not None else {},
        conflicts=(),
    )


def _text_group(tmp_path: Path, group_id: str, stem: str) -> InspectedSourceGroup:
    path: Path = tmp_path / f"{stem}.txt"
    path.write_text("one", encoding="utf-8")
    return _group(group_id, stem, _artifact(group_id, ArtifactKind.STANDALONE_TEXT, path))


def _video_group(tmp_path: Path, group_id: str, stem: str, *products: Artifact) -> InspectedSourceGroup:
    path: Path = tmp_path / f"{stem}.mkv"
    path.write_bytes(b"data")
    video: Artifact = _artifact(group_id, ArtifactKind.VIDEO_MKV, path)
    catalog: MediaCatalog = MediaCatalog(
        path=path,
        container=ContainerKind.MKV,
        duration_us=10_000_000,
        tracks=(
            MediaTrack(0, MediaTrackKind.VIDEO, "h264", None, None, True, False),
            MediaTrack(1, MediaTrackKind.SUBTITLES, "S_TEXT/UTF8", "eng", None, True, False, subtitle_format="srt"),
        ),
    )
    return _group(
        group_id,
        stem,
        video,
        *products,
        route=ROOT_ROUTE,
        media_catalogs={video.artifact_id: catalog},
    )


def _workspace(*groups: InspectedSourceGroup) -> InspectedWorkspace:
    return InspectedWorkspace(groups=groups, warnings=())


def _preset(*products: ProductKind) -> AutoPreset:
    return AutoPreset("watch", "Watch", ProductIntent(requested_products=frozenset(products)))


def _first_seen(snapshots: tuple[SourceSnapshot, ...]) -> list[float]:
    return [snapshot.first_seen for snapshot in snapshots]


def _by_path(snapshots: tuple[SourceSnapshot, ...]) -> dict[Path, SourceSnapshot]:
    return {snapshot.path: snapshot for snapshot in snapshots}


@pytest.mark.parametrize("suffix", sorted(PARTIAL_SUFFIXES))
def test_a_partial_transfer_suffix_keeps_a_long_quiet_file_unstable(tmp_path: Path, suffix: str) -> None:
    path: Path = tmp_path / f"episode{suffix.upper()}"
    path.write_bytes(b"data")
    snapshot: SourceSnapshot = SourceSnapshot(path, 4, 1, 0.0)
    assert is_stable(snapshot, QUIET_S * 10) is False


def test_a_file_becomes_stable_exactly_when_the_quiet_period_elapses(tmp_path: Path) -> None:
    path: Path = tmp_path / "episode.mkv"
    path.write_bytes(b"data")
    snapshot: SourceSnapshot = SourceSnapshot(path, 4, 1, 100.0)
    assert is_stable(snapshot, 100.0 + QUIET_S - 0.001) is False
    assert is_stable(snapshot, 100.0 + QUIET_S) is True


def test_first_seen_survives_an_unchanged_file_and_resets_after_a_write(tmp_path: Path) -> None:
    path: Path = tmp_path / "episode.txt"
    path.write_text("one", encoding="utf-8")
    group: InspectedSourceGroup = _group(
        "group-a",
        "episode",
        _artifact("group-a", ArtifactKind.STANDALONE_TEXT, path),
    )
    first: tuple[SourceSnapshot, ...] = snapshot_sources(group, {}, 100.0)
    assert _first_seen(first) == [100.0]
    carried: tuple[SourceSnapshot, ...] = snapshot_sources(group, _by_path(first), 200.0)
    assert _first_seen(carried) == [100.0]
    path.write_text("one two three", encoding="utf-8")
    reset: tuple[SourceSnapshot, ...] = snapshot_sources(group, _by_path(carried), 300.0)
    assert _first_seen(reset) == [300.0]


def test_snapshots_cover_source_files_and_ignore_derived_products(tmp_path: Path) -> None:
    text: Path = tmp_path / "episode.txt"
    text.write_text("one", encoding="utf-8")
    product: Path = tmp_path / "episode.pl.mkv"
    product.write_bytes(b"done")
    group: InspectedSourceGroup = _group(
        "group-a",
        "episode",
        _artifact("group-a", ArtifactKind.STANDALONE_TEXT, text),
        _artifact("group-a", ArtifactKind.FINAL_MKV, product),
    )
    assert [snapshot.path for snapshot in snapshot_sources(group, {}, 100.0)] == [text]


def test_a_source_that_disappeared_is_left_out_of_the_snapshot(tmp_path: Path) -> None:
    group: InspectedSourceGroup = _group(
        "group-a",
        "episode",
        _artifact("group-a", ArtifactKind.STANDALONE_TEXT, tmp_path / "gone.txt"),
    )
    assert snapshot_sources(group, {}, 100.0) == ()


def test_the_fingerprint_orders_source_files_by_name(tmp_path: Path) -> None:
    snapshots: tuple[SourceSnapshot, ...] = (
        SourceSnapshot(tmp_path / "b.txt", 2, 20, 0.0),
        SourceSnapshot(tmp_path / "a.mkv", 1, 10, 0.0),
    )
    assert source_fingerprint(snapshots) == (("a.mkv", 1, 10), ("b.txt", 2, 20))


@pytest.mark.parametrize("product", sorted(VIDEO_PRODUCTS))
def test_every_requested_video_product_needs_work_until_its_artifact_is_ready(
    tmp_path: Path,
    product: ProductKind,
) -> None:
    preset: AutoPreset = _preset(product)
    assert needs_work(_video_group(tmp_path, "group-a", "episode"), preset) is True
    produced: Path = tmp_path / f"episode.{product.value}"
    produced.write_bytes(b"done")
    complete: InspectedSourceGroup = _video_group(
        tmp_path,
        "group-a",
        "episode",
        _artifact("group-a", _PRODUCT_ARTIFACT_KINDS[product], produced),
    )
    assert needs_work(complete, preset) is False


def test_a_translate_group_needs_work_for_its_own_product_not_the_video_preset(tmp_path: Path) -> None:
    preset: AutoPreset = _preset(ProductKind.MKV)
    assert needs_work(_text_group(tmp_path, "group-a", "episode"), preset) is True
    produced: Path = tmp_path / "episode.pl.txt"
    produced.write_bytes(b"done")
    group: InspectedSourceGroup = _group(
        "group-a",
        "episode",
        _artifact("group-a", ArtifactKind.STANDALONE_TEXT, tmp_path / "episode.txt"),
        _artifact("group-a", ArtifactKind.TRANSLATED_TEXT, produced),
    )
    assert needs_work(group, preset) is False


def test_a_group_holding_every_requested_product_needs_no_work(tmp_path: Path) -> None:
    products: list[Artifact] = []
    for product in (ProductKind.FULL_PL, ProductKind.NARRATION_AUDIO, ProductKind.MKV):
        produced: Path = tmp_path / f"episode.{product.value}"
        produced.write_bytes(b"done")
        products.append(_artifact("group-a", _PRODUCT_ARTIFACT_KINDS[product], produced))
    group: InspectedSourceGroup = _video_group(tmp_path, "group-a", "episode", *products)
    preset: AutoPreset = _preset(ProductKind.FULL_PL, ProductKind.NARRATION_AUDIO, ProductKind.MKV)
    assert needs_work(group, preset) is False


def test_a_group_without_any_subtitle_source_never_needs_work(tmp_path: Path) -> None:
    video: Path = tmp_path / "episode.mkv"
    video.write_bytes(b"data")
    group: InspectedSourceGroup = _group(
        "group-a",
        "episode",
        _artifact("group-a", ArtifactKind.VIDEO_MKV, video),
        route=ROOT_ROUTE,
    )
    assert needs_work(group, _preset(ProductKind.MKV)) is False


def test_candidates_take_only_the_quiet_group_that_still_misses_a_product(tmp_path: Path) -> None:
    pending: InspectedSourceGroup = _text_group(tmp_path, "group-pending", "pending")
    done_text: Path = tmp_path / "done.txt"
    done_text.write_text("one", encoding="utf-8")
    done_product: Path = tmp_path / "done.pl.txt"
    done_product.write_bytes(b"done")
    done: InspectedSourceGroup = _group(
        "group-done",
        "done",
        _artifact("group-done", ArtifactKind.STANDALONE_TEXT, done_text),
        _artifact("group-done", ArtifactKind.TRANSLATED_TEXT, done_product),
    )
    ledger: WatchLedger = WatchLedger()
    workspace: InspectedWorkspace = _workspace(pending, done)
    preset: AutoPreset = _preset(ProductKind.TRANSLATED_TEXT)
    assert ledger.candidates(workspace, preset, 100.0) == ()
    assert ledger.candidates(workspace, preset, 100.0 + QUIET_S) == ("group-pending",)


def test_a_sidecar_still_being_copied_keeps_its_group_waiting_until_it_settles(tmp_path: Path) -> None:
    sidecar: Path = tmp_path / "episode.srt"
    sidecar.write_bytes(b"1\n00:00:00,000 --> 00:00:01,000\nfirst\n")
    group: InspectedSourceGroup = _video_group(
        tmp_path,
        "group-a",
        "episode",
        _artifact("group-a", ArtifactKind.SOURCE_SUBTITLES, sidecar),
    )
    workspace: InspectedWorkspace = _workspace(group)
    preset: AutoPreset = _preset(ProductKind.FULL_PL)
    ledger: WatchLedger = WatchLedger()

    assert ledger.candidates(workspace, preset, 100.0) == ()
    with sidecar.open("ab") as growing:
        growing.write(b"\n2\n00:00:01,000 --> 00:00:02,000\nsecond\n")
    assert ledger.candidates(workspace, preset, 100.0 + QUIET_S) == ()
    with sidecar.open("ab") as growing:
        growing.write(b"\n3\n00:00:02,000 --> 00:00:03,000\nthird\n")
    assert ledger.candidates(workspace, preset, 100.0 + 2 * QUIET_S) == ()
    assert ledger.candidates(workspace, preset, 100.0 + 3 * QUIET_S) == ("group-a",)


def test_a_started_group_leaves_the_candidate_list_until_its_window_exits(tmp_path: Path) -> None:
    group: InspectedSourceGroup = _text_group(tmp_path, "group-a", "episode")
    workspace: InspectedWorkspace = _workspace(group)
    preset: AutoPreset = _preset(ProductKind.MKV)
    ledger: WatchLedger = WatchLedger()
    ledger.candidates(workspace, preset, 100.0)
    assert ledger.candidates(workspace, preset, 100.0 + QUIET_S) == ("group-a",)
    ledger.mark_started(("group-a",))
    assert ledger.candidates(workspace, preset, 100.0 + QUIET_S) == ()


def test_a_closed_batch_is_not_retried_until_its_source_changes(tmp_path: Path) -> None:
    text: Path = tmp_path / "episode.txt"
    text.write_text("one", encoding="utf-8")
    group: InspectedSourceGroup = _group(
        "group-a",
        "episode",
        _artifact("group-a", ArtifactKind.STANDALONE_TEXT, text),
    )
    workspace: InspectedWorkspace = _workspace(group)
    preset: AutoPreset = _preset(ProductKind.MKV)
    ledger: WatchLedger = WatchLedger()
    ledger.candidates(workspace, preset, 100.0)
    ledger.mark_started(ledger.candidates(workspace, preset, 100.0 + QUIET_S))
    ledger.mark_finished(("group-a",))
    assert ledger.candidates(workspace, preset, 200.0) == ()
    text.write_text("one two three", encoding="utf-8")
    assert ledger.candidates(workspace, preset, 300.0) == ()
    assert ledger.candidates(workspace, preset, 300.0 + QUIET_S) == ("group-a",)


def test_a_finished_batch_is_not_restarted_for_the_same_input(tmp_path: Path) -> None:
    group: InspectedSourceGroup = _text_group(tmp_path, "group-a", "episode")
    workspace: InspectedWorkspace = _workspace(group)
    preset: AutoPreset = _preset(ProductKind.MKV)
    ledger: WatchLedger = WatchLedger()
    ledger.candidates(workspace, preset, 100.0)
    ledger.mark_started(ledger.candidates(workspace, preset, 100.0 + QUIET_S))
    ledger.mark_finished(("group-a",))
    assert ledger.candidates(workspace, preset, 200.0) == ()
    assert ledger.candidates(workspace, preset, 400.0) == ()


if sys.platform == "win32":
    _GENERIC_READ_WRITE: int = 0xC000_0000
    _OPEN_EXISTING: int = 3
    _FILE_ATTRIBUTE_NORMAL: int = 0x80
    _INVALID_HANDLE_VALUE: int = 0xFFFF_FFFF_FFFF_FFFF

    @contextmanager
    def _held_without_sharing(path: Path) -> Iterator[None]:
        kernel32: ctypes.WinDLL = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle: int = kernel32.CreateFileW(
            str(path),
            _GENERIC_READ_WRITE,
            0,
            None,
            _OPEN_EXISTING,
            _FILE_ATTRIBUTE_NORMAL,
            None,
        )
        assert handle not in {0, _INVALID_HANDLE_VALUE}
        try:
            yield
        finally:
            kernel32.CloseHandle(handle)

    def test_a_source_another_process_holds_without_sharing_is_not_stable(tmp_path: Path) -> None:
        path: Path = tmp_path / "episode.mkv"
        path.write_bytes(b"data")
        snapshot: SourceSnapshot = SourceSnapshot(path, 4, 1, 0.0)
        with _held_without_sharing(path):
            assert is_stable(snapshot, QUIET_S * 10) is False
        assert is_stable(snapshot, QUIET_S * 10) is True

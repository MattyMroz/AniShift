from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from anishift.application.artifacts import GroupConflict, GroupConflictKind
from anishift.application.cancellation import CancellationToken, NeverCancelledToken
from anishift.application.discovery import discover_groups
from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.selection import GroupReadiness, ReadinessReason, resolve_readiness
from anishift.services.media._process import ProcessResult
from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind

_AUDIO_DURATION_US: int = 9_000_000


class _FakeProbe:
    def __init__(self, catalogs: dict[Path, MediaCatalog]) -> None:
        self.catalogs: dict[Path, MediaCatalog] = catalogs

    def identify(self, path: Path, *, cancel: CancellationToken, timeout_s: float) -> MediaCatalog:
        del cancel, timeout_s
        return self.catalogs[path]


class _FakeRunner:
    def run(self, command: tuple[str, ...], *, cancel: CancellationToken, timeout_s: float) -> ProcessResult:
        del command, cancel, timeout_s
        return ProcessResult(f"out_time_us={_AUDIO_DURATION_US}\nprogress=end\n", "", 0)


def _english_video(path: Path) -> MediaCatalog:
    return MediaCatalog(
        path=path,
        container=ContainerKind.MKV if path.suffix.casefold() == ".mkv" else ContainerKind.MP4,
        duration_us=_AUDIO_DURATION_US,
        tracks=(
            MediaTrack(0, MediaTrackKind.VIDEO, "h264", None, None, True, False),
            MediaTrack(1, MediaTrackKind.SUBTITLES, "text", "eng", None, False, False, "srt"),
        ),
    )


def _write_srt(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1\n00:00:00,000 --> 00:00:01,000\nDzień dobry\n", encoding="utf-8")


def _write_ass(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Script Info]\n"
        "ScriptType: v4.00+\n\n"
        "[V4+ Styles]\n"
        "Format: Name\n"
        "Style: Default\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Dzień dobry\n",
        encoding="utf-8",
    )


def _write_text(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Zażółć gęślą jaźń.\n", encoding="utf-8")


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _readiness(root: Path) -> dict[str, GroupReadiness]:
    discovery = discover_groups(root)
    videos = {
        artifact.path: _english_video(artifact.path)
        for group in discovery.groups
        for artifact in group.artifacts
        if artifact.path is not None and artifact.path.suffix.casefold() in {".mkv", ".mp4"}
    }
    workspace = WorkspaceInspector(_FakeProbe(videos), runner=_FakeRunner()).inspect(
        discovery,
        cancel=NeverCancelledToken(),
    )
    return {group.source.stem: resolve_readiness(group) for group in workspace.groups}


def _only(root: Path) -> GroupReadiness:
    resolved = _readiness(root)
    assert len(resolved) == 1
    return next(iter(resolved.values()))


def test_a_ready_group_never_carries_a_waiting_reason() -> None:
    with pytest.raises(ValueError, match="waiting reason"):
        GroupReadiness(ready=True, reason=ReadinessReason.VIDEO_MISSING)
    with pytest.raises(ValueError, match="exactly one reason"):
        GroupReadiness(ready=False)


def test_a_lone_sidecar_in_subs_waits_for_its_film(tmp_path: Path) -> None:
    _write_srt(tmp_path / "subs" / "Film.srt")
    assert _only(tmp_path) == GroupReadiness(ready=False, reason=ReadinessReason.VIDEO_MISSING)


def test_a_film_in_subs_with_english_tracks_still_waits_for_the_sidecar(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "subs" / "Film.mkv", b"video")
    assert _only(tmp_path) == GroupReadiness(ready=False, reason=ReadinessReason.SIDECAR_MISSING)


@pytest.mark.parametrize("sidecar", ["Film.srt", "Film.ass", "Film.ssa"])
def test_a_complete_pair_in_subs_runs_whichever_file_arrived_first(tmp_path: Path, sidecar: str) -> None:
    _write_bytes(tmp_path / "subs" / "Film.mkv", b"video")
    if sidecar.endswith(".srt"):
        _write_srt(tmp_path / "subs" / sidecar)
    else:
        _write_ass(tmp_path / "subs" / sidecar)
    assert _only(tmp_path) == GroupReadiness(ready=True)


def test_two_competing_sidecars_in_subs_are_never_picked_at_random(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "subs" / "Film.mkv", b"video")
    _write_srt(tmp_path / "subs" / "Film.srt")
    _write_ass(tmp_path / "subs" / "Film.ass")
    assert _only(tmp_path) == GroupReadiness(ready=False, reason=ReadinessReason.AMBIGUOUS_SIDECAR)


def test_an_unreadable_sidecar_in_subs_leaves_the_pair_incomplete(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "subs" / "Film.mkv", b"video")
    _write_bytes(tmp_path / "subs" / "Film.srt", b"")
    assert _only(tmp_path) == GroupReadiness(ready=False, reason=ReadinessReason.SIDECAR_MISSING)


def test_a_sidecar_still_held_by_its_writer_is_named_as_arriving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_bytes(tmp_path / "subs" / "Film.mkv", b"video")
    _write_srt(tmp_path / "subs" / "Film.srt")
    monkeypatch.setattr(
        "anishift.application.inspection.source_is_available",
        lambda path: path.suffix.casefold() != ".srt",
    )
    assert _only(tmp_path) == GroupReadiness(ready=False, reason=ReadinessReason.SOURCE_INCOMPLETE)


@pytest.mark.parametrize("name", ["Film.srt", "Notatki.txt"])
def test_a_lone_source_in_the_root_never_becomes_unordered_work(tmp_path: Path, name: str) -> None:
    if name.endswith(".srt"):
        _write_srt(tmp_path / name)
        assert _readiness(tmp_path) == {}
        return
    _write_text(tmp_path / name)
    assert _only(tmp_path) == GroupReadiness(ready=False, reason=ReadinessReason.VIDEO_MISSING)


def test_a_film_in_the_root_may_use_its_embedded_track(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "Film.mkv", b"video")
    assert _only(tmp_path) == GroupReadiness(ready=True)


@pytest.mark.parametrize("place", ["translate", "audiobook"])
@pytest.mark.parametrize("name", ["Book.srt", "Book.txt"])
def test_a_standalone_source_runs_without_any_film(tmp_path: Path, place: str, name: str) -> None:
    if name.endswith(".srt"):
        _write_srt(tmp_path / place / name)
    else:
        _write_text(tmp_path / place / name)
    assert _only(tmp_path) == GroupReadiness(ready=True)


def test_an_audiobook_refuses_styled_subtitles_as_its_only_source(tmp_path: Path) -> None:
    _write_ass(tmp_path / "audiobook" / "Book.ass")
    assert _only(tmp_path) == GroupReadiness(ready=False, reason=ReadinessReason.UNSUPPORTED_SOURCE)


def test_translation_accepts_styled_subtitles_as_its_only_source(tmp_path: Path) -> None:
    _write_ass(tmp_path / "translate" / "Book.ssa")
    assert _only(tmp_path) == GroupReadiness(ready=True)


def test_an_empty_task_folder_source_waits_for_real_content(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "translate" / "Book.txt", b"   \n")
    assert _only(tmp_path) == GroupReadiness(ready=False, reason=ReadinessReason.CONTENT_SOURCE_MISSING)


@pytest.mark.parametrize("content", ["Book.txt", "Book.srt", "Book.mp3"])
def test_a_cover_runs_only_once_the_image_joined_its_content(tmp_path: Path, content: str) -> None:
    cover = tmp_path / "cover"
    if content.endswith(".txt"):
        _write_text(cover / content)
    elif content.endswith(".srt"):
        _write_srt(cover / content)
    else:
        _write_bytes(cover / content, b"audio")
    assert _only(tmp_path) == GroupReadiness(ready=False, reason=ReadinessReason.IMAGE_MISSING)
    _write_bytes(cover / "Book.png", b"image")
    assert _only(tmp_path) == GroupReadiness(ready=True)


def test_a_lone_cover_image_waits_for_the_content_it_should_show(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "cover" / "Book.jpg", b"image")
    assert _only(tmp_path) == GroupReadiness(ready=False, reason=ReadinessReason.CONTENT_SOURCE_MISSING)


def test_two_competing_cover_images_are_never_picked_at_random(tmp_path: Path) -> None:
    _write_text(tmp_path / "cover" / "Book.txt")
    _write_bytes(tmp_path / "cover" / "Book.png", b"image")
    _write_bytes(tmp_path / "cover" / "Book.jpeg", b"image")
    assert _only(tmp_path) == GroupReadiness(ready=False, reason=ReadinessReason.AMBIGUOUS_IMAGE)


def test_a_cover_text_beside_independent_audio_is_never_picked_at_random(tmp_path: Path) -> None:
    _write_text(tmp_path / "cover" / "Book.txt")
    _write_bytes(tmp_path / "cover" / "Book.mp3", b"audio")
    _write_bytes(tmp_path / "cover" / "Book.png", b"image")
    assert _only(tmp_path) == GroupReadiness(ready=False, reason=ReadinessReason.AMBIGUOUS_CONTENT_SOURCE)


def test_a_published_group_waiting_in_ready_never_starts_work_again(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "ready" / "Film.mkv", b"video")
    _write_srt(tmp_path / "ready" / "Film.srt")
    assert _only(tmp_path) == GroupReadiness(ready=False, reason=ReadinessReason.PLACE_STARTS_NO_WORK)


def test_a_group_reported_as_conflicting_is_never_run(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "Film.mkv", b"video")
    _write_text(tmp_path / "Film.txt")
    assert _only(tmp_path) == GroupReadiness(ready=False, reason=ReadinessReason.AMBIGUOUS_CONTENT_SOURCE)


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        (GroupConflictKind.TXT_WITH_VIDEO, ReadinessReason.AMBIGUOUS_CONTENT_SOURCE),
        (GroupConflictKind.AMBIGUOUS_PRIMARY, ReadinessReason.AMBIGUOUS_CONTENT_SOURCE),
        (GroupConflictKind.SOURCE_PATH_COLLISION, ReadinessReason.SOURCE_PATH_COLLISION),
    ],
)
def test_every_kind_of_conflict_is_reported_as_the_condition_it_really_is(
    tmp_path: Path,
    kind: GroupConflictKind,
    reason: ReadinessReason,
) -> None:
    _write_text(tmp_path / "translate" / "Book.txt")
    group: InspectedSourceGroup = _conflicting(_group_of(tmp_path, "Book"), kind)

    assert resolve_readiness(group) == GroupReadiness(ready=False, reason=reason)


def _conflicting(group: InspectedSourceGroup, kind: GroupConflictKind) -> InspectedSourceGroup:
    conflict: GroupConflict = GroupConflict(kind=kind, message="Reported by discovery", paths=(Path("Book.txt"),))
    return replace(group, conflicts=(conflict,))


def test_polish_names_are_recognised_exactly_as_written(tmp_path: Path) -> None:
    _write_text(tmp_path / "audiobook" / "Zażółć gęślą jaźń.txt")
    resolved = _readiness(tmp_path)
    assert resolved == {"Zażółć gęślą jaźń": GroupReadiness(ready=True)}


def test_an_inspected_group_is_either_ready_or_names_one_reason(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "subs" / "Film.mkv", b"video")
    _write_text(tmp_path / "audiobook" / "Book.txt")
    _write_bytes(tmp_path / "cover" / "Okładka.png", b"image")
    for readiness in _readiness(tmp_path).values():
        assert readiness.ready is (readiness.reason is None)


def _group_of(root: Path, stem: str) -> InspectedSourceGroup:
    discovery = discover_groups(root)
    workspace = WorkspaceInspector(_FakeProbe({}), runner=_FakeRunner()).inspect(
        discovery,
        cancel=NeverCancelledToken(),
    )
    return next(group for group in workspace.groups if group.source.stem == stem)


def test_readiness_reads_the_route_recorded_on_the_group(tmp_path: Path) -> None:
    _write_text(tmp_path / "translate" / "Book.txt")
    group = _group_of(tmp_path, "Book")
    assert resolve_readiness(group) == GroupReadiness(ready=True)

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from fakes import write_image_source

from anishift.application import inspection as inspection_module
from anishift.application.artifacts import ArtifactKind, ArtifactState
from anishift.application.cancellation import CancellationToken, NeverCancelledToken
from anishift.application.discovery import discover_groups
from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.intents import ExternalAudioRole
from anishift.application.selection import choose_auto_sidecar
from anishift.errors import ErrorCode, ErrorContext, ExecutionError, MediaProbeError
from anishift.services.media._process import (
    ProcessExecutionError,
    ProcessFailureReason,
    ProcessResult,
)
from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind


class _FakeProbe:
    def __init__(
        self,
        catalogs: dict[Path, MediaCatalog],
        failures: dict[Path, MediaProbeError] | None = None,
    ) -> None:
        self.catalogs: dict[Path, MediaCatalog] = catalogs
        self.failures: dict[Path, MediaProbeError] = failures or {}
        self.calls: list[tuple[Path, CancellationToken, float]] = []

    def identify(
        self,
        path: Path,
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> MediaCatalog:
        self.calls.append((path, cancel, timeout_s))
        if path in self.failures:
            raise self.failures[path]
        return self.catalogs[path]


class _FakeRunner:
    def __init__(
        self,
        duration_us: int,
        *,
        failure: ProcessFailureReason | None = None,
    ) -> None:
        self.duration_us: int = duration_us
        self.failure: ProcessFailureReason | None = failure
        self.calls: list[tuple[tuple[str, ...], CancellationToken, float]] = []

    def run(
        self,
        command: tuple[str, ...],
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> ProcessResult:
        self.calls.append((command, cancel, timeout_s))
        if self.failure is not None:
            raise ProcessExecutionError(self.failure)
        stdout = f"out_time_us={self.duration_us}\nprogress=end\n"
        return ProcessResult(stdout, "", 0)


def _catalog(path: Path, *, duration_us: int = 10_000_000) -> MediaCatalog:
    container = ContainerKind.MKV if path.suffix.casefold() == ".mkv" else ContainerKind.MP4
    return MediaCatalog(
        path=path,
        container=container,
        duration_us=duration_us,
        tracks=(
            MediaTrack(0, MediaTrackKind.VIDEO, "h264", None, None, True, False),
            MediaTrack(1, MediaTrackKind.AUDIO, "aac", "jpn", None, True, False),
            MediaTrack(2, MediaTrackKind.SUBTITLES, "text", "eng", None, False, False, "srt"),
        ),
    )


def _write_srt(path: Path) -> None:
    path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
        encoding="utf-8",
    )


def _write_ass(path: Path) -> None:
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


def _write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _inspect_video(root: Path, *, duration_us: int = 10_000_000) -> InspectedSourceGroup:
    video = root / "1.mkv"
    video.write_bytes(b"video")
    probe = _FakeProbe({video: _catalog(video, duration_us=duration_us)})
    workspace = WorkspaceInspector(probe).inspect(
        discover_groups(root),
        cancel=NeverCancelledToken(),
    )
    return workspace.groups[0]


def test_inspection_skips_invalid_ass_and_keeps_valid_srt(tmp_path: Path) -> None:
    video = tmp_path / "1.mkv"
    video.write_bytes(b"video")
    (tmp_path / "1.ass").write_bytes(b"\xff")
    _write_srt(tmp_path / "1.srt")
    discovery = discover_groups(tmp_path)
    workspace = WorkspaceInspector(_FakeProbe({video: _catalog(video)})).inspect(
        discovery,
        cancel=NeverCancelledToken(),
    )
    group = workspace.groups[0]
    ass = next(artifact for artifact in group.artifacts if artifact.path == tmp_path / "1.ass")
    srt = next(artifact for artifact in group.artifacts if artifact.path == tmp_path / "1.srt")
    assert ass.state is ArtifactState.INVALID
    assert srt.state is ArtifactState.READY
    assert choose_auto_sidecar(group.artifacts) is srt
    assert discovery.groups[0].artifacts[0].state is ArtifactState.CANDIDATE


def test_inspection_keeps_embedded_tracks_for_mkv_and_mp4(tmp_path: Path) -> None:
    mkv = tmp_path / "1.mkv"
    mp4 = tmp_path / "1.mp4"
    mkv.write_bytes(b"mkv")
    mp4.write_bytes(b"mp4")
    workspace = WorkspaceInspector(_FakeProbe({mkv: _catalog(mkv), mp4: _catalog(mp4)})).inspect(
        discover_groups(tmp_path),
        cancel=NeverCancelledToken(),
    )
    catalogs = workspace.groups[0].media_catalogs
    assert len(catalogs) == 2
    assert all(catalog.tracks[2].kind is MediaTrackKind.SUBTITLES for catalog in catalogs.values())


def test_unmarked_subtitle_language_remains_unknown(tmp_path: Path) -> None:
    video = tmp_path / "1.mkv"
    video.write_bytes(b"video")
    _write_srt(tmp_path / "1.srt")
    group = (
        WorkspaceInspector(_FakeProbe({video: _catalog(video)}))
        .inspect(
            discover_groups(tmp_path),
            cancel=NeverCancelledToken(),
        )
        .groups[0]
    )
    subtitle = next(artifact for artifact in group.artifacts if artifact.kind is ArtifactKind.SOURCE_SUBTITLES)
    assert subtitle.language is None


def test_polish_product_marker_sets_language_without_content_guessing(tmp_path: Path) -> None:
    video = tmp_path / "1.mkv"
    video.write_bytes(b"video")
    _write_srt(tmp_path / "1.pl.srt")
    group = (
        WorkspaceInspector(_FakeProbe({video: _catalog(video)}))
        .inspect(
            discover_groups(tmp_path),
            cancel=NeverCancelledToken(),
        )
        .groups[0]
    )
    subtitle = next(artifact for artifact in group.artifacts if artifact.kind is ArtifactKind.FULL_PL)
    assert subtitle.language == "pol"


def test_external_subtitle_outside_workspace_uses_declared_language(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    outside_root = tmp_path / "outside"
    workspace_root.mkdir()
    outside_root.mkdir()
    group = _inspect_video(workspace_root)
    external = outside_root / "french subtitles.srt"
    _write_srt(external)
    registered = WorkspaceInspector(_FakeProbe({})).register_external_subtitle(
        group,
        external,
        declared_language="fra",
        cancel=NeverCancelledToken(),
    )
    artifact = registered.artifacts[-1]
    assert artifact.path == external
    assert artifact.language == "fra"
    assert artifact.state is ArtifactState.READY
    assert len(group.artifacts) + 1 == len(registered.artifacts)


def test_external_styled_subtitles_register_under_the_format_they_are_read_as(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    group = _inspect_video(workspace_root)
    external = tmp_path / "napisy.ssa"
    _write_ass(external)
    registered = WorkspaceInspector(_FakeProbe({})).register_external_subtitle(
        group,
        external,
        declared_language=None,
        cancel=NeverCancelledToken(),
    )
    artifact = registered.artifacts[-1]
    assert artifact.subtitle_format == "ass"
    assert artifact.state is ArtifactState.READY


def test_external_subtitles_in_an_unknown_format_are_refused(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    group = _inspect_video(workspace_root)
    external = tmp_path / "napisy.sub"
    external.write_text("nic", encoding="utf-8")
    with pytest.raises(ExecutionError, match="ASS, SSA, or SRT"):
        WorkspaceInspector(_FakeProbe({})).register_external_subtitle(
            group,
            external,
            declared_language=None,
            cancel=NeverCancelledToken(),
        )


def test_standalone_audio_is_validated_without_any_video_to_compare_with(tmp_path: Path) -> None:
    write_image_source(tmp_path / "cover" / "Book.png")
    _write_text_file(tmp_path / "cover" / "Book.mp3", "audio")
    workspace = WorkspaceInspector(_FakeProbe({}), runner=_FakeRunner(7_000_000)).inspect(
        discover_groups(tmp_path),
        cancel=NeverCancelledToken(),
    )
    states = {artifact.kind: artifact.state for artifact in workspace.groups[0].artifacts}
    assert states[ArtifactKind.SOURCE_AUDIO] is ArtifactState.READY
    assert states[ArtifactKind.SOURCE_IMAGE] is ArtifactState.READY
    assert workspace.warnings == ()


def test_an_empty_cover_image_is_reported_as_invalid(tmp_path: Path) -> None:
    (tmp_path / "cover").mkdir()
    (tmp_path / "cover" / "Book.png").write_bytes(b"")
    _write_text_file(tmp_path / "cover" / "Book.txt", "Zażółć gęślą jaźń")
    workspace = WorkspaceInspector(_FakeProbe({}), runner=_FakeRunner(0)).inspect(
        discover_groups(tmp_path),
        cancel=NeverCancelledToken(),
    )
    image = next(artifact for artifact in workspace.groups[0].artifacts if artifact.kind is ArtifactKind.SOURCE_IMAGE)
    assert image.state is ArtifactState.INVALID
    assert tuple(warning.code for warning in workspace.warnings) == ("image_invalid",)


def _cover_image_state(tmp_path: Path) -> tuple[ArtifactState, tuple[str, ...]]:
    _write_text_file(tmp_path / "cover" / "Book.txt", "Zażółć gęślą jaźń")
    workspace = WorkspaceInspector(_FakeProbe({}), runner=_FakeRunner(0)).inspect(
        discover_groups(tmp_path),
        cancel=NeverCancelledToken(),
    )
    image = next(artifact for artifact in workspace.groups[0].artifacts if artifact.kind is ArtifactKind.SOURCE_IMAGE)
    return image.state, tuple(warning.code for warning in workspace.warnings)


def test_a_half_copied_cover_image_is_refused_instead_of_being_read_as_a_picture(tmp_path: Path) -> None:
    write_image_source(tmp_path / "cover" / "whole.jpg", width=64, height=64)
    complete: bytes = (tmp_path / "cover" / "whole.jpg").read_bytes()
    (tmp_path / "cover" / "whole.jpg").unlink()
    (tmp_path / "cover" / "Book.jpg").write_bytes(complete[: len(complete) // 2])

    assert _cover_image_state(tmp_path) == (ArtifactState.INVALID, ("image_undecodable",))


def test_a_cover_image_still_being_copied_waits_and_becomes_ready_once_it_is_whole(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_text_file(tmp_path / "cover" / "Book.txt", "Zażółć gęślą jaźń")
    write_image_source(tmp_path / "cover" / "whole.jpg", width=64, height=64)
    complete: bytes = (tmp_path / "cover" / "whole.jpg").read_bytes()
    (tmp_path / "cover" / "whole.jpg").unlink()
    picture: Path = tmp_path / "cover" / "Book.jpg"
    picture.write_bytes(complete[: len(complete) // 2])
    copying: dict[Path, bool] = {picture: False}
    monkeypatch.setattr(
        inspection_module,
        "source_is_available",
        lambda path: copying.get(Path(path), True),
    )
    inspector: WorkspaceInspector = WorkspaceInspector(_FakeProbe({}), runner=_FakeRunner(0))

    busy = inspector.inspect(discover_groups(tmp_path), cancel=NeverCancelledToken())
    busy_image = next(item for item in busy.groups[0].artifacts if item.kind is ArtifactKind.SOURCE_IMAGE)

    assert busy_image.state is ArtifactState.MISSING
    assert tuple(warning.code for warning in busy.warnings) == ("source_busy",)
    assert busy.pending_paths == (picture,)

    picture.write_bytes(complete)
    copying[picture] = True
    finished = inspector.inspect(discover_groups(tmp_path), cancel=NeverCancelledToken())
    whole = next(item for item in finished.groups[0].artifacts if item.kind is ArtifactKind.SOURCE_IMAGE)

    assert whole.state is ArtifactState.READY
    assert finished.warnings == ()
    assert finished.pending_paths == ()


def test_a_cover_image_that_is_not_a_picture_at_all_is_refused(tmp_path: Path) -> None:
    (tmp_path / "cover").mkdir()
    (tmp_path / "cover" / "Book.png").write_bytes(b"this text is not a picture")

    assert _cover_image_state(tmp_path) == (ArtifactState.INVALID, ("image_undecodable",))


def test_a_cover_image_is_judged_by_what_it_holds_rather_than_by_its_extension(tmp_path: Path) -> None:
    write_image_source(tmp_path / "cover" / "real.jpg", width=32, height=32)
    (tmp_path / "cover" / "Book.png").write_bytes((tmp_path / "cover" / "real.jpg").read_bytes())
    (tmp_path / "cover" / "real.jpg").unlink()

    assert _cover_image_state(tmp_path) == (ArtifactState.READY, ())


@pytest.mark.parametrize(("width", "height"), [(101, 55), (40, 90), (2, 2)])
def test_an_odd_sized_portrait_or_tiny_cover_image_is_still_a_real_picture(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    write_image_source(tmp_path / "cover" / "Book.png", width=width, height=height)

    assert _cover_image_state(tmp_path) == (ArtifactState.READY, ())


def test_external_audio_within_tolerance_is_fully_decoded(tmp_path: Path) -> None:
    group = _inspect_video(tmp_path, duration_us=10_000_000)
    audio = tmp_path / "external voice.anything"
    audio.write_bytes(b"audio")
    runner = _FakeRunner(10_500_000)
    registered = WorkspaceInspector(
        _FakeProbe({}),
        runner=runner,
        ffmpeg=Path("ffmpeg.exe"),
    ).register_external_audio(
        group,
        audio,
        role=ExternalAudioRole.NARRATION_MIX,
        cancel=NeverCancelledToken(),
    )
    artifact = registered.artifacts[-1]
    command = runner.calls[0][0]
    assert artifact.kind is ArtifactKind.NARRATION_AUDIO
    assert artifact.state is ArtifactState.READY
    assert command[command.index("-i") + 1] == str(audio)
    assert command[-2:] == ("null", "-")


def test_external_audio_beyond_tolerance_is_rejected(tmp_path: Path) -> None:
    group = _inspect_video(tmp_path, duration_us=10_000_000)
    audio = tmp_path / "external.wav"
    audio.write_bytes(b"audio")
    inspector = WorkspaceInspector(
        _FakeProbe({}),
        runner=_FakeRunner(20_000_001),
        ffmpeg=Path("ffmpeg.exe"),
    )
    with pytest.raises(ExecutionError, match="beyond tolerance"):
        inspector.register_external_audio(
            group,
            audio,
            role=ExternalAudioRole.SOURCE_AUDIO,
            cancel=NeverCancelledToken(),
        )


def test_external_audio_decode_failure_is_typed(tmp_path: Path) -> None:
    group = _inspect_video(tmp_path)
    audio = tmp_path / "broken.wav"
    audio.write_bytes(b"broken")
    inspector = WorkspaceInspector(
        _FakeProbe({}),
        runner=_FakeRunner(0, failure=ProcessFailureReason.NONZERO_EXIT),
        ffmpeg=Path("ffmpeg.exe"),
    )
    with pytest.raises(ExecutionError) as raised:
        inspector.register_external_audio(
            group,
            audio,
            role=ExternalAudioRole.SOURCE_AUDIO,
            cancel=NeverCancelledToken(),
        )
    assert raised.value.context.code is ErrorCode.AUDIO_FAILED


def test_cancel_during_probe_is_not_downgraded_to_invalid_artifact(tmp_path: Path) -> None:
    video = tmp_path / "1.mkv"
    video.write_bytes(b"video")
    cancelled = MediaProbeError(context=ErrorContext(code=ErrorCode.CANCELLED, message="cancelled"))
    inspector = WorkspaceInspector(_FakeProbe({}, {video: cancelled}))
    with pytest.raises(MediaProbeError) as raised:
        inspector.inspect(discover_groups(tmp_path), cancel=NeverCancelledToken())
    assert raised.value.context.code is ErrorCode.CANCELLED


def test_invalid_media_is_retained_for_manual_diagnostics(tmp_path: Path) -> None:
    video = tmp_path / "1.mkv"
    video.write_bytes(b"broken")
    failure = MediaProbeError(context=ErrorContext(code=ErrorCode.MEDIA_PROBE_FAILED, message="broken"))
    workspace = WorkspaceInspector(_FakeProbe({}, {video: failure})).inspect(
        discover_groups(tmp_path),
        cancel=NeverCancelledToken(),
    )
    assert workspace.groups[0].artifacts[0].state is ArtifactState.INVALID
    assert workspace.warnings[0].code == "media_invalid"


class _BarrierProbe:
    def __init__(self, catalogs: dict[Path, MediaCatalog], parties: int) -> None:
        self.catalogs: dict[Path, MediaCatalog] = catalogs
        self.barrier: threading.Barrier = threading.Barrier(parties, timeout=10)

    def identify(self, path: Path, *, cancel: CancellationToken, timeout_s: float) -> MediaCatalog:
        del cancel, timeout_s
        self.barrier.wait()
        return self.catalogs[path]


def test_groups_are_probed_at_once_and_keep_the_discovery_order(tmp_path: Path) -> None:
    names: tuple[str, ...] = ("1", "2", "3", "4")
    catalogs: dict[Path, MediaCatalog] = {}
    for name in names:
        video = tmp_path / f"{name}.mkv"
        video.write_bytes(b"video")
        catalogs[video] = _catalog(video)
    discovery = discover_groups(tmp_path)

    workspace = WorkspaceInspector(_BarrierProbe(catalogs, len(names))).inspect(
        discovery,
        cancel=NeverCancelledToken(),
    )

    assert tuple(group.group_id for group in workspace.groups) == tuple(group.group_id for group in discovery.groups)
    assert all(group.artifacts[0].state is ArtifactState.READY for group in workspace.groups)

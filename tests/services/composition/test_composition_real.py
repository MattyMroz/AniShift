from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.composition.commands import StreamingRunner
from anishift.services.composition.config import CompositionConfig
from anishift.services.composition.probe import source_duration_us, validate_merged
from anishift.services.composition.service import CompositionService
from anishift.services.composition.types import (
    AttachedSubtitle,
    CompositionPlan,
    CompositionResult,
    CompositionStatus,
    ContainerCompositionRequest,
    ContainerCompositionResult,
    ContainerTarget,
    OutputVariant,
    SubtitleRole,
)
from anishift.services.extraction.service import identify

FFMPEG = resolve_binary(Binary.FFMPEG)
MKVMERGE = resolve_binary(Binary.MKVMERGE)
FFPROBE = resolve_binary(Binary.FFPROBE)

_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, Bold, Alignment, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,0,2,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.20,0:00:01.50,Default,,0,0,0,,Zażółć gęślą jaźń
"""


def _sample_video(path: Path, *, duration_s: int = 2) -> None:
    subprocess.run(  # noqa: S603
        [
            str(FFMPEG),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=320x240:rate=10:duration={duration_s}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration_s}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


@pytest.mark.skipif(FFMPEG is None or MKVMERGE is None, reason="bundled tools are unavailable")
def test_merge_keeps_source_tracks_first_and_adds_ours_last(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    _sample_video(source)
    subtitle = tmp_path / "Episode.pl.ass"
    subtitle.write_text(_ASS, encoding="utf-8")
    plan = CompositionPlan(
        source_path=source,
        variant=OutputVariant.MERGE,
        subtitles=(AttachedSubtitle(subtitle, SubtitleRole.FULL, "pol", "Napisy PL"),),
        destination_dir=tmp_path / "output",
        temporary_root=tmp_path / "tmp",
    )
    service = CompositionService(CompositionConfig(), runner=StreamingRunner())

    result = service.compose(plan)

    assert result.status is CompositionStatus.COMPLETED
    assert result.output_path is not None
    validate_merged(result.output_path, expected_track_names=("Napisy PL",))
    merged = identify(result.output_path)
    assert [track.type for track in merged.tracks[:2]] == ["video", "audio"]
    assert merged.tracks[-1].name == "Napisy PL"
    assert merged.tracks[-1].language == "pol"


@pytest.mark.skipif(FFMPEG is None or MKVMERGE is None, reason="bundled tools are unavailable")
def test_merge_appends_the_lector_after_the_original_audio(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    _sample_video(source)
    lector = tmp_path / "Lector.m4a"
    subprocess.run(  # noqa: S603
        [str(FFMPEG), "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=2", "-c:a", "aac", str(lector)],
        check=True,
        capture_output=True,
    )
    plan = CompositionPlan(
        source_path=source,
        variant=OutputVariant.MERGE,
        narration_audio=lector,
        destination_dir=tmp_path / "output",
        temporary_root=tmp_path / "tmp",
    )
    service = CompositionService(CompositionConfig(), runner=StreamingRunner())

    result = service.compose(plan)

    assert result.output_path is not None
    merged = identify(result.output_path)
    audio = [track for track in merged.tracks if track.type == "audio"]
    assert len(audio) == 2
    assert audio[-1].name == "Lektor PL"
    assert audio[-1].default is False


@pytest.mark.skipif(FFMPEG is None or FFPROBE is None, reason="bundled tools are unavailable")
@pytest.mark.parametrize("container_request", [False, True])
def test_burn_handles_difficult_path_characters(tmp_path: Path, container_request: bool) -> None:
    media_dir = tmp_path / "Heroine's dir with spaces [1080p]"
    media_dir.mkdir()
    source = media_dir / "Zażółć - 04.mkv"
    _sample_video(source)
    subtitle = media_dir / "Heroine's episode.pl.ass"
    subtitle.write_text(_ASS, encoding="utf-8")
    plan = CompositionPlan(
        source_path=source,
        variant=OutputVariant.BURN,
        burn_subtitle=subtitle,
        destination_dir=media_dir / "output",
        temporary_root=media_dir / "tmp",
    )
    service = CompositionService(CompositionConfig(), runner=StreamingRunner())

    result: CompositionResult | ContainerCompositionResult
    if container_request:
        result = service.compose_container(
            ContainerCompositionRequest(
                source_video=source,
                destination=media_dir / "output" / "Episode.pl.mp4",
                target=ContainerTarget.MP4,
                burn_subtitle=subtitle,
                attached_subtitles=(),
                narration_audio=None,
                keep_original_audio=True,
            )
        )
    else:
        result = service.compose(plan)

    assert result.output_path is not None
    assert result.output_path.stat().st_size > 0


@pytest.mark.skipif(FFMPEG is None or FFPROBE is None, reason="bundled tools are unavailable")
@pytest.mark.parametrize("container_request", [False, True])
def test_mp4_preserves_narration_beyond_video_duration(tmp_path: Path, container_request: bool) -> None:
    source: Path = tmp_path / "Episode.mp4"
    _sample_video(source, duration_s=1)
    narration: Path = tmp_path / "Narration.m4a"
    subprocess.run(  # noqa: S603
        [str(FFMPEG), "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=4", "-c:a", "aac", str(narration)],
        check=True,
        capture_output=True,
    )
    service: CompositionService = CompositionService(CompositionConfig())
    result: CompositionResult | ContainerCompositionResult
    if container_request:
        result = service.compose_container(
            ContainerCompositionRequest(
                source_video=source,
                destination=tmp_path / "Episode.pl.mp4",
                target=ContainerTarget.MP4,
                burn_subtitle=None,
                attached_subtitles=(),
                narration_audio=narration,
                keep_original_audio=False,
            )
        )
    else:
        result = service.compose(
            CompositionPlan(
                source_path=source,
                variant=OutputVariant.BURN,
                narration_audio=narration,
                destination_dir=tmp_path,
            )
        )

    assert result.output_path is not None
    assert source_duration_us(result.output_path, ffprobe=service.ffprobe) == pytest.approx(4_000_000, abs=100_000)


@pytest.mark.skipif(FFMPEG is None or FFPROBE is None, reason="bundled tools are unavailable")
def test_mp4_duration_excludes_original_audio_when_dropped(tmp_path: Path) -> None:
    source: Path = tmp_path / "Episode.mp4"
    subprocess.run(  # noqa: S603
        [
            str(FFMPEG),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=10:duration=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=4",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    service: CompositionService = CompositionService(CompositionConfig())

    result: ContainerCompositionResult = service.compose_container(
        ContainerCompositionRequest(
            source_video=source,
            destination=tmp_path / "Episode.pl.mp4",
            target=ContainerTarget.MP4,
            burn_subtitle=None,
            attached_subtitles=(),
            narration_audio=None,
            keep_original_audio=False,
        )
    )

    assert source_duration_us(result.output_path, ffprobe=service.ffprobe) == pytest.approx(1_000_000, abs=100_000)

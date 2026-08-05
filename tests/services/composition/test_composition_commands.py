from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

from anishift.services.composition.commands import (
    StreamingRunner,
    burn_command,
    merge_command,
    mp4_audio_is_copyable,
    parse_ffmpeg_progress,
    parse_mkvmerge_progress,
    subtitle_filter_argument,
)
from anishift.services.composition.config import CompositionConfig
from anishift.services.composition.errors import (
    CompositionCancelledError,
    CompositionProcessError,
)
from anishift.services.composition.types import (
    AttachedSubtitle,
    CompositionPlan,
    OutputVariant,
    SubtitleRole,
)

_SILENT_SLEEP = "import time; time.sleep(30)"


def _plan(tmp_path: Path, **overrides: object) -> CompositionPlan:
    defaults: dict[str, object] = {
        "source_path": tmp_path / "Episode.mkv",
        "variant": OutputVariant.MERGE,
        "temporary_root": tmp_path / "tmp",
        "destination_dir": tmp_path / "output",
    }
    defaults.update(overrides)
    return CompositionPlan(**defaults)  # type: ignore[arg-type]


def test_merge_command_uses_current_mkvmerge_flag_names(tmp_path: Path) -> None:
    plan = _plan(tmp_path, narration_audio=tmp_path / "Episode.eac3")

    command = merge_command(plan, mkvmerge=Path("mkvmerge"), destination=tmp_path / "out.mkv")

    assert "--default-track-flag" in command
    assert "--forced-display-flag" in command
    assert "--default-track" not in command
    assert "--forced-track" not in command


def test_merge_command_names_the_lector_track(tmp_path: Path) -> None:
    plan = _plan(tmp_path, narration_audio=tmp_path / "Episode.eac3")

    command = merge_command(plan, mkvmerge=Path("mkvmerge"), destination=tmp_path / "out.mkv")

    assert "0:Lektor PL" in command
    assert "0:pol" in command


def test_merge_command_puts_added_files_after_the_source(tmp_path: Path) -> None:
    subtitles = (
        AttachedSubtitle(tmp_path / "full.ass", SubtitleRole.FULL, "pol", "Napisy PL"),
        AttachedSubtitle(tmp_path / "signs.ass", SubtitleRole.DISPLAYED, "pol", "Napisy poboczne PL"),
    )
    narration = tmp_path / "Episode.eac3"
    plan = _plan(tmp_path, narration_audio=narration, subtitles=subtitles)

    command = merge_command(plan, mkvmerge=Path("mkvmerge"), destination=tmp_path / "out.mkv")

    appended = [narration, *[subtitle.path for subtitle in subtitles]]
    positions = [command.index(str(path)) for path in [plan.source_path, *appended]]
    assert positions == sorted(positions)


def test_merge_command_never_reorders_source_tracks(tmp_path: Path) -> None:
    plan = _plan(tmp_path, narration_audio=tmp_path / "Episode.eac3")

    command = merge_command(plan, mkvmerge=Path("mkvmerge"), destination=tmp_path / "out.mkv")

    assert "--track-order" not in command


def test_merge_command_without_material_only_copies_source(tmp_path: Path) -> None:
    command = merge_command(_plan(tmp_path), mkvmerge=Path("mkvmerge"), destination=tmp_path / "out.mkv")

    assert "--language" not in command
    assert command[-1] == str(tmp_path / "Episode.mkv")


def test_burn_command_forces_compatibility_flags(tmp_path: Path) -> None:
    plan = _plan(tmp_path, variant=OutputVariant.BURN, burn_subtitle=tmp_path / "signs.ass")

    command = burn_command(
        plan,
        ffmpeg=Path("ffmpeg"),
        config=CompositionConfig(),
        subtitle_argument="ass='signs.ass'",
        audio_codec="eac3",
        destination=tmp_path / "out.mp4",
    )

    assert "-pix_fmt" in command
    assert "yuv420p" in command
    assert "+faststart" in command
    assert "-progress" in command


def test_burn_command_copies_video_without_subtitles(tmp_path: Path) -> None:
    plan = _plan(tmp_path, variant=OutputVariant.BURN, narration_audio=tmp_path / "Episode.eac3")

    command = burn_command(
        plan,
        ffmpeg=Path("ffmpeg"),
        config=CompositionConfig(),
        subtitle_argument=None,
        audio_codec="eac3",
        destination=tmp_path / "out.mp4",
    )

    assert "copy" in command
    assert "-vf" not in command


def test_burn_command_transcodes_unsupported_audio(tmp_path: Path) -> None:
    plan = _plan(tmp_path, variant=OutputVariant.BURN, burn_subtitle=tmp_path / "s.ass")

    command = burn_command(
        plan,
        ffmpeg=Path("ffmpeg"),
        config=CompositionConfig(),
        subtitle_argument="ass='s.ass'",
        audio_codec="dts",
        destination=tmp_path / "out.mp4",
    )

    audio_index = command.index("-c:a")
    assert command[audio_index + 1] == "aac"


@pytest.mark.parametrize(
    ("kind", "expected_prefix"),
    [("ass", "ass="), ("srt", "subtitles=")],
)
def test_subtitle_filter_picks_the_faithful_filter(kind: str, expected_prefix: str) -> None:
    value = subtitle_filter_argument(Path("C:/anime/show.ass"), kind=kind)

    assert value.startswith(expected_prefix)


def test_subtitle_filter_appends_fonts_directory() -> None:
    value = subtitle_filter_argument(Path("C:/a/s.ass"), kind="ass", fonts_dir=Path("C:/a/fonts"))

    assert ":fontsdir=" in value


@pytest.mark.parametrize(
    ("codec", "expected"),
    [("eac3", True), ("aac", True), ("mp3", True), ("dts", False), ("truehd", False), ("", False)],
)
def test_mp4_audio_copy_matrix(codec: str, expected: bool) -> None:
    assert mp4_audio_is_copyable(codec) is expected


def test_parse_mkvmerge_progress_reads_gui_lines() -> None:
    assert parse_mkvmerge_progress("#GUI#progress 42%") == 42
    assert parse_mkvmerge_progress("#GUI#error nope") is None
    assert parse_mkvmerge_progress("Progress: 42%") is None


def test_parse_ffmpeg_progress_scales_against_duration() -> None:
    assert parse_ffmpeg_progress("out_time_us=500000", total_us=1_000_000) == 50
    assert parse_ffmpeg_progress("out_time_us=2000000", total_us=1_000_000) == 100
    assert parse_ffmpeg_progress("speed=1.2x", total_us=1_000_000) is None
    assert parse_ffmpeg_progress("out_time_us=1", total_us=0) is None


def test_streaming_runner_reports_progress_and_succeeds() -> None:
    percents: list[int] = []

    outcome = StreamingRunner().run(
        (sys.executable, "-c", "print('#GUI#progress 50%'); print('#GUI#progress 100%')"),
        operation="merge",
        timeout_s=30.0,
        progress=parse_mkvmerge_progress,
        on_percent=percents.append,
    )

    assert outcome.returncode == 0
    assert percents == [50, 100]


def test_streaming_runner_cancels_a_process_that_never_prints() -> None:
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(CompositionCancelledError):
        StreamingRunner(shutdown_grace_s=1.0).run(
            (sys.executable, "-c", _SILENT_SLEEP),
            operation="merge",
            timeout_s=30.0,
            cancel=cancel,
        )


def test_streaming_runner_times_out_a_process_that_never_prints() -> None:
    with pytest.raises(CompositionProcessError):
        StreamingRunner(shutdown_grace_s=1.0).run(
            (sys.executable, "-c", _SILENT_SLEEP),
            operation="burn",
            timeout_s=0.5,
        )


def test_streaming_runner_reports_a_failing_process() -> None:
    with pytest.raises(CompositionProcessError):
        StreamingRunner().run(
            (sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(2)"),
            operation="merge",
            timeout_s=30.0,
        )


def test_streaming_runner_accepts_a_warning_exit_code() -> None:
    outcome = StreamingRunner().run(
        (sys.executable, "-c", "import sys; sys.exit(1)"),
        operation="merge",
        timeout_s=30.0,
        warning_exit_code=1,
    )

    assert outcome.had_warnings is True

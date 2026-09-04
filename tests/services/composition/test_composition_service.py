from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from anishift.services.composition.commands import CommandOutcome
from anishift.services.composition.config import CompositionConfig
from anishift.services.composition.errors import CompositionValidationError
from anishift.services.composition.service import CompositionService, _notify
from anishift.services.composition.types import (
    AttachedSubtitle,
    CompositionPlan,
    CompositionStatus,
    ContainerCompositionRequest,
    ContainerTarget,
    OutputVariant,
    SubtitleRole,
)


class _FakeRunner:
    def __init__(self, *, produces: Path | None = None, payload: bytes = b"result") -> None:
        self._produces = produces
        self._payload = payload
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: Any, **kwargs: Any) -> CommandOutcome:
        self.commands.append(tuple(command))
        if self._produces is not None:
            self._produces.write_bytes(self._payload)
        return CommandOutcome(command=tuple(command), returncode=0, stderr="", had_warnings=False)


class _FailingRunner:
    def run(self, command: Any, **kwargs: Any) -> CommandOutcome:
        raise CompositionValidationError("merge failed")


class _ContainerRunner:
    def __init__(self, *, progress_line: str | None = None) -> None:
        self.commands: list[tuple[str, ...]] = []
        self._progress_line: str | None = progress_line

    def run(self, command: Any, **kwargs: Any) -> CommandOutcome:
        captured = tuple(command)
        self.commands.append(captured)
        destination = Path(captured[captured.index("--output") + 1]) if "--output" in captured else Path(captured[-1])
        destination.write_bytes(b"container")
        if self._progress_line is not None:
            percent: int | None = kwargs["progress"](self._progress_line)
            assert percent is not None
            kwargs["on_percent"](percent)
        return CommandOutcome(command=captured, returncode=0, stderr="", had_warnings=False)


def _service(runner: Any, tmp_path: Path) -> CompositionService:
    return CompositionService(
        CompositionConfig(),
        runner=runner,
        mkvmerge=tmp_path / "mkvmerge.exe",
        ffmpeg=tmp_path / "ffmpeg.exe",
        ffprobe=tmp_path / "ffprobe.exe",
    )


def test_compose_without_material_is_skipped(tmp_path: Path) -> None:
    plan = CompositionPlan(
        source_path=tmp_path / "Episode.mkv",
        variant=OutputVariant.MERGE,
        destination_dir=tmp_path / "output",
    )

    result = _service(_FakeRunner(), tmp_path).compose(plan)

    assert result.status is CompositionStatus.SKIPPED_NOTHING_TO_ADD
    assert result.output_path is None


def test_failed_merge_keeps_inputs_and_source(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    source.write_bytes(b"source")
    lector = tmp_path / "Episode.eac3"
    lector.write_bytes(b"audio")
    plan = CompositionPlan(
        source_path=source,
        variant=OutputVariant.MERGE,
        narration_audio=lector,
        destination_dir=tmp_path / "output",
    )

    with pytest.raises(CompositionValidationError):
        _service(_FailingRunner(), tmp_path).compose(plan)

    assert source.read_bytes() == b"source"
    assert lector.read_bytes() == b"audio"
    assert list((tmp_path / "output").glob("*.mkv")) == []


def test_players_moves_products_next_to_source(tmp_path: Path) -> None:
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    source = media_dir / "Episode.mkv"
    source.write_bytes(b"source")
    subtitle = tmp_path / "Episode.pl.ass"
    subtitle.write_text("[Script Info]", encoding="utf-8")
    plan = CompositionPlan(
        source_path=source,
        variant=OutputVariant.PLAYERS,
        subtitles=(AttachedSubtitle(subtitle, SubtitleRole.FULL, "pol", "Napisy PL"),),
    )

    result = _service(_FakeRunner(), tmp_path).compose(plan)

    assert result.status is CompositionStatus.COMPLETED
    assert (media_dir / "Episode.pl.ass").is_file()
    assert result.moved_paths == (media_dir / "Episode.pl.ass",)


def test_players_does_not_require_external_tools(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    source.touch()
    plan = CompositionPlan(
        source_path=source,
        variant=OutputVariant.PLAYERS,
        destination_dir=tmp_path,
    )

    monkeypatch.setattr(
        "anishift.services.composition.service.require_binary",
        lambda _binary: pytest.fail("players resolved an external tool"),
    )

    result = CompositionService(CompositionConfig()).compose(plan)

    assert result.status is CompositionStatus.COMPLETED


def test_players_leaves_products_already_next_to_source(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    source.write_bytes(b"source")
    subtitle = tmp_path / "Episode.pl.ass"
    subtitle.write_text("[Script Info]", encoding="utf-8")
    plan = CompositionPlan(
        source_path=source,
        variant=OutputVariant.PLAYERS,
        subtitles=(AttachedSubtitle(subtitle, SubtitleRole.FULL, "pol", "Napisy PL"),),
    )

    result = _service(_FakeRunner(), tmp_path).compose(plan)

    assert result.moved_paths == ()
    assert subtitle.is_file()


def test_progress_observer_failure_is_contained() -> None:
    class _Throwing:
        def __init__(self) -> None:
            self.calls = 0

        def on_composition_phase(self, scope_id: str, phase: str, percent: int) -> None:
            self.calls += 1
            raise RuntimeError("renderer unavailable")

    sink = _Throwing()

    _notify(sink, "scope", "merging", 50)

    assert sink.calls == 1


def test_compose_container_builds_mkv_with_selected_tracks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "Episode.mp4"
    source.write_bytes(b"source")
    narration = tmp_path / "Episode.eac3"
    narration.write_bytes(b"audio")
    subtitle = tmp_path / "Episode.displayed.pl.ass"
    subtitle.write_text("[Script Info]", encoding="utf-8")
    destination = tmp_path / "Episode.pl.mkv"
    runner = _ContainerRunner()
    service = _service(runner, tmp_path)
    monkeypatch.setattr(service, "_container_font_warnings", lambda _request, **_kwargs: ())
    monkeypatch.setattr("anishift.services.composition.service.validate_merged", lambda *_args, **_kwargs: None)
    request = ContainerCompositionRequest(
        source_video=source,
        destination=destination,
        target=ContainerTarget.MKV,
        burn_subtitle=None,
        attached_subtitles=(AttachedSubtitle(subtitle, SubtitleRole.DISPLAYED, "pol", "Signs PL"),),
        narration_audio=narration,
        keep_original_audio=True,
    )

    result = service.compose_container(request)

    assert result.output_path == destination
    assert result.target is ContainerTarget.MKV
    assert destination.read_bytes() == b"container"
    assert narration.read_bytes() == b"audio"
    assert str(narration) in runner.commands[0]
    assert str(subtitle) in runner.commands[0]


def test_compose_container_builds_mp4_without_burn_or_narration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "Episode.mkv"
    source.write_bytes(b"source")
    destination = tmp_path / "Episode.pl.mp4"
    runner = _ContainerRunner()
    service = _service(runner, tmp_path)
    monkeypatch.setattr("anishift.services.composition.service.source_duration_us", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr("anishift.services.composition.service.audio_codec_name", lambda *_args, **_kwargs: "aac")
    monkeypatch.setattr("anishift.services.composition.service.validate_burned", lambda *_args, **_kwargs: None)
    request = ContainerCompositionRequest(
        source_video=source,
        destination=destination,
        target=ContainerTarget.MP4,
        burn_subtitle=None,
        attached_subtitles=(),
        narration_audio=None,
        keep_original_audio=True,
    )

    result = service.compose_container(request)

    assert result.output_path == destination
    assert result.target is ContainerTarget.MP4
    assert destination.read_bytes() == b"container"
    assert "-vf" not in runner.commands[0]
    assert "0:a:0?" in runner.commands[0]


def test_mkv_and_mp4_requests_reuse_the_same_narration_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "Episode.mkv"
    source.write_bytes(b"source")
    narration = tmp_path / "Episode.eac3"
    narration.write_bytes(b"audio")
    runner = _ContainerRunner()
    service = _service(runner, tmp_path)
    monkeypatch.setattr("anishift.services.composition.service.validate_merged", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("anishift.services.composition.service.source_duration_us", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr("anishift.services.composition.service.audio_codec_name", lambda *_args, **_kwargs: "eac3")
    monkeypatch.setattr("anishift.services.composition.service.validate_burned", lambda *_args, **_kwargs: None)
    requests = (
        ContainerCompositionRequest(
            source_video=source,
            destination=tmp_path / "Episode.pl.mkv",
            target=ContainerTarget.MKV,
            burn_subtitle=None,
            attached_subtitles=(),
            narration_audio=narration,
            keep_original_audio=True,
        ),
        ContainerCompositionRequest(
            source_video=source,
            destination=tmp_path / "Episode.pl.mp4",
            target=ContainerTarget.MP4,
            burn_subtitle=None,
            attached_subtitles=(),
            narration_audio=narration,
            keep_original_audio=False,
        ),
    )

    results = tuple(service.compose_container(request) for request in requests)

    assert tuple(result.target for result in results) == (ContainerTarget.MKV, ContainerTarget.MP4)
    assert all(str(narration) in command for command in runner.commands)
    assert narration.read_bytes() == b"audio"


def test_failed_container_composition_preserves_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    source.write_bytes(b"source")
    destination = tmp_path / "Episode.pl.mkv"
    destination.write_bytes(b"previous")
    request = ContainerCompositionRequest(
        source_video=source,
        destination=destination,
        target=ContainerTarget.MKV,
        burn_subtitle=None,
        attached_subtitles=(),
        narration_audio=None,
        keep_original_audio=True,
    )

    with pytest.raises(CompositionValidationError):
        _service(_FailingRunner(), tmp_path).compose_container(request)

    assert destination.read_bytes() == b"previous"


def test_container_request_rejects_source_as_destination(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"

    with pytest.raises(ValueError, match="must differ"):
        ContainerCompositionRequest(
            source_video=source,
            destination=source,
            target=ContainerTarget.MKV,
            burn_subtitle=None,
            attached_subtitles=(),
            narration_audio=None,
            keep_original_audio=True,
        )


@pytest.mark.parametrize(
    ("target", "progress_line", "phase"),
    [(ContainerTarget.MKV, "#GUI#progress 50%", "merging"), (ContainerTarget.MP4, "out_time_us=500000", "burning")],
)
def test_container_composition_reports_measured_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: ContainerTarget,
    progress_line: str,
    phase: str,
) -> None:
    class _Progress:
        def __init__(self) -> None:
            self.events: list[tuple[str, int]] = []

        def on_composition_phase(self, scope_id: str, phase: str, percent: int) -> None:
            del scope_id
            self.events.append((phase, percent))

    source: Path = tmp_path / "Episode.mkv"
    source.write_bytes(b"source")
    runner: _ContainerRunner = _ContainerRunner(progress_line=progress_line)
    service: CompositionService = _service(runner, tmp_path)
    observer: _Progress = _Progress()
    monkeypatch.setattr("anishift.services.composition.service.source_duration_us", lambda *_args, **_kwargs: 1_000_000)
    monkeypatch.setattr("anishift.services.composition.service.validate_burned", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("anishift.services.composition.service.validate_merged", lambda *_args, **_kwargs: None)
    request: ContainerCompositionRequest = ContainerCompositionRequest(
        source_video=source,
        destination=tmp_path / f"Episode.pl.{target.value}",
        target=target,
        burn_subtitle=None,
        attached_subtitles=(),
        narration_audio=None,
        keep_original_audio=False,
    )

    service.compose_container(request, callbacks=observer)

    assert observer.events == [(phase, 50)]

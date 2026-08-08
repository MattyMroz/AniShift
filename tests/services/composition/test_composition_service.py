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

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from anishift.pipeline.composition_runtime import build_plan, compose_outcomes
from anishift.pipeline.narration import scope_id_for_source
from anishift.pipeline.types import FileOutcome
from anishift.services.composition.errors import CompositionValidationError
from anishift.services.composition.types import (
    CompositionPlan,
    CompositionResult,
    CompositionStatus,
    OutputVariant,
    SubtitleRole,
)


def _outcome(tmp_path: Path, **overrides: object) -> FileOutcome:
    defaults: dict[str, object] = {
        "source": tmp_path / "Episode.mkv",
        "status": "done",
    }
    defaults.update(overrides)
    return FileOutcome(**defaults)  # type: ignore[arg-type]


def test_foreign_source_with_lector_adds_full_and_displayed(tmp_path: Path) -> None:
    outcome = _outcome(
        tmp_path,
        translated_path=tmp_path / "Episode.pl.ass",
        displayed_path=tmp_path / "Episode.displayed.pl.ass",
        mixed_audio_path=tmp_path / "Episode.eac3",
    )

    plan = build_plan(outcome, variant=OutputVariant.MERGE, workspace_root=tmp_path, scope_id="scope-1")

    assert plan is not None
    assert [subtitle.role for subtitle in plan.subtitles] == [SubtitleRole.FULL, SubtitleRole.DISPLAYED]
    assert plan.narration_audio is not None


def test_foreign_source_without_lector_still_adds_subtitles(tmp_path: Path) -> None:
    outcome = _outcome(
        tmp_path,
        translated_path=tmp_path / "Episode.pl.ass",
        displayed_path=tmp_path / "Episode.displayed.pl.ass",
    )

    plan = build_plan(outcome, variant=OutputVariant.MERGE, workspace_root=tmp_path, scope_id="scope-1")

    assert plan is not None
    assert len(plan.subtitles) == 2
    assert plan.narration_audio is None


def test_polish_source_never_duplicates_the_full_track(tmp_path: Path) -> None:
    outcome = _outcome(
        tmp_path,
        already_polish=True,
        translated_path=tmp_path / "Episode.pl.ass",
        displayed_path=tmp_path / "Episode.displayed.pl.ass",
        mixed_audio_path=tmp_path / "Episode.eac3",
    )

    plan = build_plan(outcome, variant=OutputVariant.MERGE, workspace_root=tmp_path, scope_id="scope-1")

    assert plan is not None
    assert [subtitle.role for subtitle in plan.subtitles] == [SubtitleRole.DISPLAYED]


def test_polish_source_without_lector_or_signs_has_nothing_to_add(tmp_path: Path) -> None:
    outcome = _outcome(tmp_path, already_polish=True, translated_path=tmp_path / "Episode.pl.ass")

    assert build_plan(outcome, variant=OutputVariant.MERGE, workspace_root=tmp_path, scope_id="s") is None


def test_merge_without_material_returns_no_plan(tmp_path: Path) -> None:
    assert build_plan(_outcome(tmp_path), variant=OutputVariant.MERGE, workspace_root=tmp_path, scope_id="s") is None


def test_burn_prefers_displayed_when_a_lector_exists(tmp_path: Path) -> None:
    outcome = _outcome(
        tmp_path,
        translated_path=tmp_path / "Episode.pl.ass",
        displayed_path=tmp_path / "Episode.displayed.pl.ass",
        mixed_audio_path=tmp_path / "Episode.eac3",
    )

    plan = build_plan(outcome, variant=OutputVariant.BURN, workspace_root=tmp_path, scope_id="s")

    assert plan is not None
    assert plan.burn_subtitle == tmp_path / "Episode.displayed.pl.ass"


def test_burn_uses_full_subtitles_without_a_lector(tmp_path: Path) -> None:
    outcome = _outcome(tmp_path, translated_path=tmp_path / "Episode.pl.ass")

    plan = build_plan(outcome, variant=OutputVariant.BURN, workspace_root=tmp_path, scope_id="s")

    assert plan is not None
    assert plan.burn_subtitle == tmp_path / "Episode.pl.ass"


def test_burn_with_lector_only_remuxes_without_subtitles(tmp_path: Path) -> None:
    outcome = _outcome(tmp_path, mixed_audio_path=tmp_path / "Episode.eac3")

    plan = build_plan(outcome, variant=OutputVariant.BURN, workspace_root=tmp_path, scope_id="s")

    assert plan is not None
    assert plan.burn_subtitle is None
    assert plan.narration_audio is not None


def test_burn_without_material_returns_no_plan(tmp_path: Path) -> None:
    assert build_plan(_outcome(tmp_path), variant=OutputVariant.BURN, workspace_root=tmp_path, scope_id="s") is None


def test_subtitle_kind_follows_the_written_product(tmp_path: Path) -> None:
    outcome = _outcome(tmp_path, translated_path=tmp_path / "Episode.pl.srt")

    composed = compose_outcomes(
        {outcome.source: outcome},
        service=_StubService(),
        variant=OutputVariant.BURN,
        workspace_root=tmp_path,
    )

    assert composed[outcome.source].composition_status == "completed"


@pytest.mark.parametrize("variant", [OutputVariant.MERGE, OutputVariant.BURN])
def test_assembled_variants_target_the_source_directory(tmp_path: Path, variant: OutputVariant) -> None:
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    outcome = _outcome(media_dir, translated_path=media_dir / "Episode.pl.ass")

    plan = build_plan(outcome, variant=variant, workspace_root=tmp_path, scope_id="s")

    assert plan is not None
    assert plan.destination_dir == media_dir


def test_players_variant_targets_the_source_directory(tmp_path: Path) -> None:
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    outcome = _outcome(media_dir, translated_path=media_dir / "Episode.pl.ass")

    plan = build_plan(outcome, variant=OutputVariant.PLAYERS, workspace_root=tmp_path, scope_id="s")

    assert plan is not None
    assert plan.destination_dir == media_dir


class _StubService:
    def __init__(self, *, fail_for: frozenset[Path] = frozenset()) -> None:
        self.ffprobe = Path("ffprobe")
        self._fail_for = fail_for

    def compose(self, plan: CompositionPlan, **kwargs: Any) -> CompositionResult:
        if plan.source_path in self._fail_for:
            raise CompositionValidationError("merge failed")
        return CompositionResult(
            source_path=plan.source_path,
            variant=plan.variant,
            status=CompositionStatus.COMPLETED,
            output_path=plan.destination_dir / f"{plan.source_path.stem}.pl.mkv",
        )


def _done(tmp_path: Path, name: str) -> FileOutcome:
    return FileOutcome(
        source=tmp_path / f"{name}.mkv",
        status="done",
        translated_path=tmp_path / f"{name}.pl.ass",
    )


def test_one_failure_does_not_stop_the_batch(tmp_path: Path) -> None:
    failing = _done(tmp_path, "A")
    healthy = _done(tmp_path, "B")

    composed = compose_outcomes(
        {failing.source: failing, healthy.source: healthy},
        service=_StubService(fail_for=frozenset({failing.source})),
        variant=OutputVariant.MERGE,
        workspace_root=tmp_path,
    )

    assert composed[failing.source].composition_status == "failed"
    assert composed[healthy.source].composition_status == "completed"
    assert composed[healthy.source].composed_path is not None


def test_unfinished_file_is_left_alone(tmp_path: Path) -> None:
    outcome = FileOutcome(source=tmp_path / "A.mkv", status="failed")

    composed = compose_outcomes(
        {outcome.source: outcome},
        service=_StubService(),
        variant=OutputVariant.MERGE,
        workspace_root=tmp_path,
    )

    assert composed[outcome.source].composition_status == "skipped_nothing_to_add"


def test_success_discards_the_scope_directory(tmp_path: Path) -> None:
    outcome = _done(tmp_path, "A")
    scope = tmp_path / "temp" / scope_id_for_source(outcome.source, workspace_root=tmp_path)
    scope.mkdir(parents=True)

    compose_outcomes(
        {outcome.source: outcome},
        service=_StubService(),
        variant=OutputVariant.MERGE,
        workspace_root=tmp_path,
    )

    assert not scope.exists()


def test_failure_keeps_the_scope_directory(tmp_path: Path) -> None:
    outcome = _done(tmp_path, "A")
    scope = tmp_path / "temp" / scope_id_for_source(outcome.source, workspace_root=tmp_path)
    scope.mkdir(parents=True)

    compose_outcomes(
        {outcome.source: outcome},
        service=_StubService(fail_for=frozenset({outcome.source})),
        variant=OutputVariant.MERGE,
        workspace_root=tmp_path,
    )

    assert scope.is_dir()


def test_burn_announces_the_batch_cost_before_rendering(tmp_path: Path) -> None:
    class _Ui:
        def __init__(self) -> None:
            self.announced: list[tuple[int, float]] = []

        def on_composition_phase(self, scope_id: str, phase: str, percent: int) -> None:
            return

        def on_burn_estimate(self, file_count: int, estimated_seconds: float) -> None:
            self.announced.append((file_count, estimated_seconds))

    ui = _Ui()
    outcome = _done(tmp_path, "A")

    compose_outcomes(
        {outcome.source: outcome},
        service=_StubService(),
        variant=OutputVariant.BURN,
        workspace_root=tmp_path,
        ui=ui,
    )

    assert [count for count, _ in ui.announced] == [1]

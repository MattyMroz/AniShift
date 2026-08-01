from __future__ import annotations

import os
from pathlib import Path

import pytest
from pysubs2 import SSAFile

from anishift.errors import ErrorCode
from anishift.pipeline.narration import (
    NarrationBuildError,
    build_polish_narration,
    build_translated_narration,
    scope_id_for_source,
)
from anishift.services.subtitles.types import SplitStats, SpokenLine, SubtitleSplit
from anishift.services.translation.types import FileTranslation, TranslatedLine


def _split(*lines: SpokenLine) -> SubtitleSplit:
    return SubtitleSplit(
        kind="ass",
        subs=SSAFile(),
        decisions=(),
        verdicts=(),
        spoken=lines,
        stats=SplitStats(
            total_events=len(lines),
            spoken_events=len(lines),
            spoken_lines=len(lines),
            displayed_events=0,
            drawing_events=0,
            collapsed_away=0,
        ),
    )


def _translation(
    *lines: TranslatedLine,
    failed_lines: int = 0,
    error: str | None = None,
) -> FileTranslation:
    return FileTranslation(
        spoken=lines,
        failed_lines=failed_lines,
        error=error,
    )


def _source(
    text: str = "Dobry wieczór.",
    *,
    start: int = 1000,
    end: int = 2000,
    order: int = 4,
) -> SpokenLine:
    return SpokenLine(start=start, end=end, text=text, style="Default", order=order)


def _translated(source: SpokenLine, text: str | None = None, *, ok: bool = True) -> TranslatedLine:
    return TranslatedLine(
        start=source.start,
        end=source.end,
        source_text=source.text,
        text=source.text if text is None else text,
        lines=(source.text if text is None else text,),
        style=source.style,
        ok=ok,
    )


def test_polish_and_identical_translation_build_the_same_narration() -> None:
    source = _source()
    split = _split(source)

    polish = build_polish_narration(split, scope_id="scope-test", batch_rank=2)
    translated = build_translated_narration(
        split,
        _translation(_translated(source)),
        scope_id="scope-test",
        batch_rank=2,
    )

    assert polish == translated


def test_translation_changes_only_request_text_not_identity_or_timing() -> None:
    source = _source("Good evening.")
    split = _split(source)
    polish = build_polish_narration(split, scope_id="scope-test", batch_rank=0)
    translated = build_translated_narration(
        split,
        _translation(_translated(source, "Dobry wieczór.")),
        scope_id="scope-test",
        batch_rank=0,
    )

    assert polish.speech.requests[0].request_id == translated.speech.requests[0].request_id
    assert translated.speech.requests[0].text == "Dobry wieczór."
    assert polish.items[0].start_ms == translated.items[0].start_ms
    assert polish.items[0].source_order == translated.items[0].source_order


def test_adapter_preserves_already_clean_spoken_text_verbatim() -> None:
    first = _source("Zbiór {1, 2}")
    second = _source("2 < 3 > 1", start=2100, end=2200, order=5)

    batch = build_polish_narration(
        _split(first, second),
        scope_id="scope-test",
        batch_rank=0,
    )

    assert tuple(request.text for request in batch.speech.requests) == (
        "Zbiór {1, 2}",
        "2 < 3 > 1",
    )
    assert len(batch.items) == 2


def test_incomplete_spoken_translation_is_rejected_before_tts() -> None:
    source = _source("Good evening.")

    with pytest.raises(NarrationBuildError) as exc_info:
        build_translated_narration(
            _split(source),
            _translation(_translated(source, ok=False)),
            scope_id="scope-test",
            batch_rank=0,
        )

    assert exc_info.value.context.code is ErrorCode.TRANSLATION_FAILED


def test_translation_count_source_and_timing_must_match() -> None:
    source = _source("Good evening.")
    mismatch_source = _translated(source)
    mismatch_source = TranslatedLine(
        start=mismatch_source.start,
        end=mismatch_source.end,
        source_text="Different source",
        text=mismatch_source.text,
        lines=mismatch_source.lines,
        style=mismatch_source.style,
    )
    mismatch_timing = TranslatedLine(
        start=source.start + 1,
        end=source.end,
        source_text=source.text,
        text="Dobry wieczór.",
        lines=("Dobry wieczór.",),
        style=source.style,
    )

    for translation in (
        _translation(),
        _translation(mismatch_source),
        _translation(mismatch_timing),
    ):
        with pytest.raises(NarrationBuildError):
            build_translated_narration(
                _split(source),
                translation,
                scope_id="scope-test",
                batch_rank=0,
            )


def test_displayed_failure_count_does_not_block_complete_spoken() -> None:
    source = _source("Good evening.")

    narration = build_translated_narration(
        _split(source),
        _translation(_translated(source, "Dobry wieczór."), failed_lines=3),
        scope_id="scope-test",
        batch_rank=0,
    )

    assert narration.speech.requests[0].text == "Dobry wieczór."


def test_scope_id_is_stable_safe_and_path_specific(tmp_path: Path) -> None:
    source = tmp_path / ("[Grupa] Zażółć " + "bardzo-" * 30 + "01.mkv")
    other = tmp_path / "other" / source.name

    first = scope_id_for_source(source, workspace_root=tmp_path)
    second = scope_id_for_source(source, workspace_root=tmp_path)
    distinct = scope_id_for_source(other, workspace_root=tmp_path)

    assert first == second
    assert first != distinct
    assert len(first) == 30
    assert first.startswith("scope-")
    assert first.replace("-", "").isalnum()


@pytest.mark.skipif(os.name != "nt", reason="Windows paths are case-insensitive")
def test_scope_id_ignores_windows_path_casing(tmp_path: Path) -> None:
    source = tmp_path / "Series" / "Episode.MKV"
    differently_cased_source = Path(str(tmp_path).upper()) / "series" / "episode.mkv"

    first = scope_id_for_source(source, workspace_root=tmp_path)
    second = scope_id_for_source(
        differently_cased_source,
        workspace_root=Path(str(tmp_path).upper()),
    )

    assert first == second


def test_request_ranks_follow_input_order_while_timing_stays_outside_request() -> None:
    later_source_order = _source("Pierwszy.", start=3000, end=4000, order=8)
    earlier_source_order = _source("Drugi.", start=1000, end=2000, order=2)

    narration = build_polish_narration(
        _split(later_source_order, earlier_source_order),
        scope_id="scope-test",
        batch_rank=7,
    )

    assert tuple(request.request_rank for request in narration.speech.requests) == (0, 1)
    assert narration.speech.batch_rank == 7
    assert not hasattr(narration.speech.requests[0], "start_ms")
    assert tuple(item.source_order for item in narration.items) == (8, 2)


def test_invalid_timing_is_skipped_and_empty_spoken_is_empty() -> None:
    valid = _source("Poprawna linia.", start=2_000, end=3_000, order=2)
    narration = build_polish_narration(
        _split(_source(start=1_000, end=1_000), valid),
        scope_id="scope-test",
        batch_rank=0,
    )

    assert tuple(request.text for request in narration.speech.requests) == ("Poprawna linia.",)
    assert tuple(item.source_order for item in narration.items) == (2,)

    empty = build_polish_narration(
        _split(),
        scope_id="scope-test",
        batch_rank=0,
    )
    assert empty.speech.requests == ()
    assert empty.items == ()


def test_source_outside_workspace_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.mkv"

    with pytest.raises(NarrationBuildError):
        scope_id_for_source(outside, workspace_root=tmp_path)

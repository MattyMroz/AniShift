from __future__ import annotations

import importlib.util
import json
from typing import TYPE_CHECKING

import pytest

from anishift.paths import quality_dir
from anishift.services.tts import DocumentPart
from anishift.services.tts.engines.elevenreader.service import part_spans
from anishift.services.tts.engines.elevenreader.types import AlignmentChunk

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

pytestmark = pytest.mark.integration

DATA = quality_dir() / "elevenreader"
TANTEI = DATA / "tantei"


def _prototype_bounds() -> ModuleType:
    spec = importlib.util.spec_from_file_location("elevenreader_prototype_bounds", DATA / "bounds.py")
    assert spec is not None
    assert spec.loader is not None
    module: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row_chunk(row: dict[str, list[object] | float]) -> AlignmentChunk:
    chars = row["chars"]
    starts = row["start_ms"]
    durations = row["dur_ms"]
    assert isinstance(chars, list)
    assert isinstance(starts, list)
    assert isinstance(durations, list)
    return AlignmentChunk(
        offset_ms=float(str(row["offset_ms"])),
        chars=tuple(str(char) for char in chars),
        starts_ms=tuple(float(str(value)) for value in starts),
        durations_ms=tuple(float(str(value)) for value in durations),
    )


def _align_chunks(path: Path) -> tuple[AlignmentChunk, ...]:
    lines: list[str] = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    return tuple(_row_chunk(json.loads(line)) for line in lines)


def _parts(lines: Path) -> tuple[DocumentPart, ...]:
    rows: list[dict[str, object]] = json.loads(lines.read_text(encoding="utf-8"))
    return tuple(DocumentPart(request_id=str(index), text=str(row["text"])) for index, row in enumerate(rows))


@pytest.mark.parametrize("voice", ["fronczewski", "adam"])
def test_part_spans_tantei_recording_matches_prototype_lines(voice: str) -> None:
    alignment: Path = TANTEI / f"anishift-test-{voice}.align.jsonl"
    if not alignment.is_file() or not (DATA / "bounds.py").is_file():
        pytest.skip("ElevenReader prototype data is not available")

    timings = part_spans(_align_chunks(alignment), _parts(TANTEI / "lines.json"))
    lines = _prototype_bounds().load_lines(TANTEI, voice)

    assert len(timings) == len(lines)
    for timing, line in zip(timings, lines, strict=True):
        assert (timing.start_ms, timing.end_ms) == pytest.approx((line.start, line.end))


@pytest.mark.parametrize("voice", ["fronczewski", "adam"])
def test_part_spans_separated_edgerunners_recording_returns_every_line(voice: str) -> None:
    alignment: Path = DATA / "edge02c" / f"anishift-test-{voice}.align.jsonl"
    if not alignment.is_file():
        pytest.skip("ElevenReader prototype data is not available")
    parts = _parts(DATA / "edge02" / "lines.json")

    timings = part_spans(_align_chunks(alignment), parts)

    assert [timing.request_id for timing in timings] == [part.request_id for part in parts]

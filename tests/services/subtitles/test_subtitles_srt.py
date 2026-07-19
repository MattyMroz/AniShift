from __future__ import annotations

from pathlib import Path

from anishift.services.subtitles.srt import spoken_to_srt
from anishift.services.translation.types import TranslatedLine


def _line(text: str, start: int = 0, end: int = 0) -> TranslatedLine:
    return TranslatedLine(start=start, end=end, source_text=text, text=text, lines=(text,), style="")


def test_empty_lines_write_nothing(tmp_path: Path) -> None:
    assert spoken_to_srt((), tmp_path / "out.srt") is None


def test_generates_monotonic_timings_from_length(tmp_path: Path) -> None:
    dest = tmp_path / "out.srt"
    lines = (_line("Pierwsze zdanie lektora."), _line("Drugie zdanie lektora."))
    result = spoken_to_srt(lines, dest)
    assert result == dest
    body = dest.read_text(encoding="utf-8")
    assert body.count("-->") == 2
    assert "Pierwsze zdanie lektora." in body
    assert "00:00:00,000" in body


def test_existing_timings_are_kept(tmp_path: Path) -> None:
    dest = tmp_path / "out.srt"
    spoken_to_srt((_line("Ma czasy", start=5000, end=7000),), dest)
    body = dest.read_text(encoding="utf-8")
    assert "00:00:05,000 --> 00:00:07,000" in body


def test_line_count_preserved(tmp_path: Path) -> None:
    dest = tmp_path / "out.srt"
    lines = tuple(_line(f"Linia numer {i}") for i in range(5))
    spoken_to_srt(lines, dest)
    assert dest.read_text(encoding="utf-8").count("-->") == 5

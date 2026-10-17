from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.quality import report
from scripts.quality.episode import OUTPUT_NAME, SOURCE_NAME, analyse

if TYPE_CHECKING:
    from pathlib import Path

_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, \
Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, \
MarginV, Encoding
Style: Default,Arial,26,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _write(path: Path, lines: list[tuple[int, str]]) -> None:
    events = [
        f"Dialogue: 0,0:00:{second:02d}.00,0:00:{second + 1:02d}.00,Default,,0,0,0,,{text}" for second, text in lines
    ]
    path.write_text(_HEADER + "\n".join(events) + "\n", encoding="utf-8")


def _episode(root: Path, name: str, source: list[tuple[int, str]], output: list[tuple[int, str]]) -> Path:
    directory = root / name
    directory.mkdir()
    _write(directory / SOURCE_NAME, source)
    _write(directory / OUTPUT_NAME, output)
    return directory


def test_summarise_compares_languages_on_paired_lines_of_current_outputs_only(tmp_path: Path) -> None:
    source = [(second, f"Line number {second} is here.") for second in range(1, 11)]
    current = _episode(tmp_path, "current", [*source, (30, "This English line has no Polish pair at all.")], source)
    stale = _episode(tmp_path, "stale", source, [(50, "Inna wersja.")])
    results = [analyse(current, tmp_path / "cache", render=False), analyse(stale, tmp_path / "cache", render=False)]
    summary = report.summarise(results)
    comparison = summary["comparison"]
    assert isinstance(comparison, dict)
    assert comparison["events"] == 10
    assert comparison["empty_output"] == 0
    assert comparison["timing"]["source"]["count"] == comparison["timing"]["output"]["count"] == 10
    assert comparison["breaks"]["source"]["events"] == comparison["breaks"]["output"]["events"] == 10
    source_only = summary["source_only"]
    assert isinstance(source_only, dict)
    assert source_only["timing"]["count"] == 21
    assert source_only["breaks"]["events"] == 21

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from anishift.services.subtitles import load_subtitles, visible_text
from scripts.subtitle_quality import __main__ as quality_main
from scripts.subtitle_quality import replay
from scripts.subtitle_quality.episode import OUTPUT_NAME, SOURCE_NAME

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, \
Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, \
MarginV, Encoding
Style: Default,Arial,26,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,20,1
Style: Sign,Arial,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,8,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

_SOURCE = (
    "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Where are you going?\n"
    "Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,I {\\i1}really{\\i0} need to\\Nfind my brother.\n"
    "Dialogue: 0,0:00:04.00,0:00:06.00,Sign,,0,0,0,,{\\pos(320,40)}Bakery\n"
    "Dialogue: 0,0:00:07.00,0:00:09.00,Default,,0,0,0,,See you.\n"
)

_OUTPUT = (
    "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Dokąd idziesz?\n"
    "Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,Naprawdę muszę\\Nznaleźć brata.\n"
    "Dialogue: 0,0:00:04.00,0:00:06.00,Sign,,0,0,0,,{\\pos(320,40)}Piekarnia\n"
    "Dialogue: 0,0:00:07.50,0:00:09.00,Default,,0,0,0,,Na razie.\n"
)


def _pair(root: Path, name: str, *, output: bool = True) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / SOURCE_NAME).write_text(_HEADER + _SOURCE, encoding="utf-8")
    if output:
        (directory / OUTPUT_NAME).write_text(_HEADER + _OUTPUT, encoding="utf-8")
    return directory


def test_pair_input_takes_paired_polish_with_joined_lines_and_keeps_unpaired_english(tmp_path: Path) -> None:
    directory = _pair(tmp_path, "pair")
    inputs = replay.pair_input(load_subtitles(directory / SOURCE_NAME), load_subtitles(directory / OUTPUT_NAME))
    assert inputs.translations == {
        0: "Dokąd idziesz?",
        1: "Naprawdę muszę znaleźć brata.",
        2: "Piekarnia",
        3: "See you.",
    }
    assert inputs.excluded == (3,)


def test_replay_writes_polish_output_and_mapping_and_skips_pairs_without_output(tmp_path: Path) -> None:
    pairs = [_pair(tmp_path / "pairs", "pair"), _pair(tmp_path / "pairs", "lonely", output=False)]
    mapping = json.loads(replay.replay(pairs, tmp_path / "run").read_text(encoding="utf-8"))
    written = load_subtitles(tmp_path / "run" / f"pair{replay.REPLAY_SUFFIX}")
    texts = [visible_text(event.text) for event in written.events if event.type == "Dialogue"]
    assert texts == ["Dokąd idziesz?", "Naprawdę muszę znaleźć brata.", "Piekarnia", "See you."]
    assert [pair["name"] for pair in mapping["pairs"]] == ["pair"]
    assert mapping["pairs"][0]["excluded"] == [3]
    assert mapping["pairs"][0]["inputs"][1] == {"index": 1, "text": "Naprawdę muszę znaleźć brata."}
    assert mapping["skipped"] == [{"name": "lonely", "reason": f"no {OUTPUT_NAME}"}]


def test_compare_reports_identical_different_and_skipped_pairs(tmp_path: Path) -> None:
    pairs = [_pair(tmp_path / "pairs", "pair"), _pair(tmp_path / "pairs", "lonely", output=False)]
    replay.replay(pairs, tmp_path / "base")
    replay.replay(pairs, tmp_path / "other")
    same = replay.compare(tmp_path / "base", tmp_path / "other")
    assert same == replay.Comparison(("pair",), (), (("lonely", f"no {OUTPUT_NAME}"),))
    output = tmp_path / "other" / f"pair{replay.REPLAY_SUFFIX}"
    output.write_bytes(output.read_bytes() + b"\n")
    changed = replay.compare(tmp_path / "base", tmp_path / "other")
    assert changed.different == (("pair", "output bytes differ"),)


def test_quality_command_line_hands_replay_arguments_to_the_replay(tmp_path: Path) -> None:
    pairs = tmp_path / "pairs"
    _pair(pairs, "pair")
    assert quality_main.main(["replay", str(pairs), "--out", str(tmp_path / "base")]) == 0
    assert quality_main.main(["replay", str(pairs), "--out", str(tmp_path / "other")]) == 0
    assert quality_main.main(["replay", "--compare", str(tmp_path / "base"), str(tmp_path / "other")]) == 0

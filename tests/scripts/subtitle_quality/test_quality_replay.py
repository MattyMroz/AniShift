from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from anishift.services.subtitles import load_subtitles, visible_text
from scripts.subtitle_quality import __main__ as quality_main
from scripts.subtitle_quality import replay
from scripts.subtitle_quality.episode import OUTPUT_NAME, SOURCE_NAME

if TYPE_CHECKING:
    from pathlib import Path

    from pysubs2 import SSAFile

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

_FBF_SOURCE = (
    "Dialogue: 0,0:00:01.00,0:00:01.50,Default,,0,0,0,,Hold on!\n"
    "Dialogue: 0,0:00:01.50,0:00:02.00,Default,,0,0,0,,Hold on!\n"
    "Dialogue: 0,0:00:04.00,0:00:04.50,Default,,0,0,0,,Run!\n"
    "Dialogue: 0,0:00:04.50,0:00:05.00,Default,,0,0,0,,Run!\n"
    "Dialogue: 0,0:00:06.00,0:00:07.00,Sign,,0,0,0,,{\\pos(320,40)}Exit\n"
    "Dialogue: 0,0:00:08.00,0:00:09.00,Sign,,0,0,0,,{\\pos(320,40)}Station\n"
)

_FBF_OUTPUT = (
    "Dialogue: 0,0:00:01.00,0:00:01.50,Default,,0,0,0,,Czekaj!\n"
    "Dialogue: 0,0:00:01.60,0:00:02.00,Default,,0,0,0,,Stój!\n"
    "Dialogue: 0,0:00:04.10,0:00:04.50,Default,,0,0,0,,Uciekaj!\n"
    "Dialogue: 0,0:00:04.50,0:00:05.00,Default,,0,0,0,,Biegnij!\n"
    "Dialogue: 0,0:00:06.00,0:00:07.00,Sign,,0,0,0,,{\\pos(320,40)}Wyjście\n"
    "Dialogue: 0,0:00:08.20,0:00:09.00,Sign,,0,0,0,,{\\pos(320,40)}Stacja\n"
)


def _pair(root: Path, name: str, *, source: str = _SOURCE, output: str | None = _OUTPUT) -> Path:
    directory: Path = root / name
    directory.mkdir(parents=True)
    (directory / SOURCE_NAME).write_text(_HEADER + source, encoding="utf-8")
    if output is not None:
        (directory / OUTPUT_NAME).write_text(_HEADER + output, encoding="utf-8")
    return directory


def _texts(path: Path) -> list[str]:
    subs: SSAFile = load_subtitles(path)
    return [visible_text(event.text) for event in subs.events if event.type == "Dialogue"]


def _mapping(path: Path) -> dict[str, Any]:
    content: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return content


def test_pair_input_takes_paired_polish_with_joined_lines_and_keeps_unpaired_english(tmp_path: Path) -> None:
    directory: Path = _pair(tmp_path, "pair")
    inputs: replay.PairInput = replay.pair_input(
        load_subtitles(directory / SOURCE_NAME), load_subtitles(directory / OUTPUT_NAME)
    )
    assert inputs.translations == {
        0: "Dokąd idziesz?",
        1: "Naprawdę muszę znaleźć brata.",
        2: "Piekarnia",
        3: "See you.",
    }
    assert inputs.paired == frozenset({0, 1, 2})


def test_replay_writes_polish_output_and_mapping_under_pair_ids_and_skips_pairs_without_output(
    tmp_path: Path,
) -> None:
    _pair(tmp_path / "library", "pair")
    _pair(tmp_path / "library", "lonely", output=None)
    mapping: dict[str, Any] = _mapping(replay.replay([tmp_path / "library"], tmp_path / "run"))
    assert _texts(tmp_path / "run" / "library" / f"pair{replay.REPLAY_SUFFIX}") == [
        "Dokąd idziesz?",
        "Naprawdę muszę znaleźć brata.",
        "Piekarnia",
        "See you.",
    ]
    assert mapping["rule"] == replay.EXCLUSION_RULE
    assert [(pair["pair"], pair["output"]) for pair in mapping["pairs"]] == [("library/pair", "library/pair.pl.ass")]
    assert mapping["pairs"][0]["excluded"] == [3]
    assert mapping["pairs"][0]["inputs"][1] == {"index": 1, "text": "Naprawdę muszę znaleźć brata."}
    assert mapping["skipped"] == [{"pair": "library/lonely", "reason": f"no {OUTPUT_NAME}"}]


def test_a_spoken_group_follows_its_first_event_and_is_excluded_whole_when_that_event_is_unpaired(
    tmp_path: Path,
) -> None:
    _pair(tmp_path / "library", "fbf", source=_FBF_SOURCE, output=_FBF_OUTPUT)
    mapping: dict[str, Any] = _mapping(replay.replay([tmp_path / "library"], tmp_path / "run"))
    assert _texts(tmp_path / "run" / "library" / f"fbf{replay.REPLAY_SUFFIX}") == [
        "Czekaj!",
        "Czekaj!",
        "Run!",
        "Run!",
        "Wyjście",
        "Station",
    ]
    assert mapping["pairs"][0]["excluded"] == [2, 3, 5]


def test_replay_writes_a_mapping_when_every_pair_is_skipped_or_the_corpus_is_empty(tmp_path: Path) -> None:
    _pair(tmp_path / "library", "lonely", output=None)
    (tmp_path / "empty").mkdir()
    skipped: dict[str, Any] = _mapping(replay.replay([tmp_path / "library"], tmp_path / "skipped" / "run"))
    empty: dict[str, Any] = _mapping(replay.replay([tmp_path / "empty"], tmp_path / "empty-run"))
    assert (skipped["pairs"], skipped["skipped"]) == ([], [{"pair": "library/lonely", "reason": f"no {OUTPUT_NAME}"}])
    assert (empty["pairs"], empty["skipped"]) == ([], [])


def test_pairs_with_one_folder_name_under_two_roots_keep_separate_ids(tmp_path: Path) -> None:
    _pair(tmp_path / "library", "pair")
    _pair(tmp_path / "corpus-pairs", "pair")
    mapping: dict[str, Any] = _mapping(
        replay.replay([tmp_path / "library", tmp_path / "corpus-pairs"], tmp_path / "run")
    )
    assert [pair["pair"] for pair in mapping["pairs"]] == ["corpus-pairs/pair", "library/pair"]
    assert mapping["skipped"] == []


def test_compare_reports_identical_different_and_skipped_pairs(tmp_path: Path) -> None:
    _pair(tmp_path / "library", "pair")
    _pair(tmp_path / "library", "lonely", output=None)
    replay.replay([tmp_path / "library"], tmp_path / "base")
    replay.replay([tmp_path / "library"], tmp_path / "other")
    same: replay.Comparison = replay.compare(tmp_path / "base", tmp_path / "other")
    assert same == replay.Comparison(("library/pair",), (), (("library/lonely", f"no {OUTPUT_NAME}"),))
    output: Path = tmp_path / "other" / "library" / f"pair{replay.REPLAY_SUFFIX}"
    output.write_bytes(output.read_bytes() + b"\n")
    changed: replay.Comparison = replay.compare(tmp_path / "base", tmp_path / "other")
    assert changed.different == (("library/pair", "output bytes differ"),)


def test_event_comparison_leaves_excluded_events_out_and_counts_changed_ones(tmp_path: Path) -> None:
    _pair(tmp_path / "library", "pair")
    replay.replay([tmp_path / "library"], tmp_path / "base")
    replay.replay([tmp_path / "library"], tmp_path / "other")
    output: Path = tmp_path / "other" / "library" / f"pair{replay.REPLAY_SUFFIX}"
    output.write_text(output.read_text(encoding="utf-8").replace("See you.", "Bye."), encoding="utf-8")
    excluded_only: replay.EventComparison = replay.compare_events(tmp_path / "base", tmp_path / "other")
    assert excluded_only == replay.EventComparison((replay.EventCounts("library/pair", 3, 0, 1),), ())
    assert replay.compare(tmp_path / "base", tmp_path / "other").different == (("library/pair", "output bytes differ"),)
    output.write_text(output.read_text(encoding="utf-8").replace("Piekarnia", "Sklep"), encoding="utf-8")
    changed: replay.EventComparison = replay.compare_events(tmp_path / "base", tmp_path / "other")
    assert changed.pairs == (replay.EventCounts("library/pair", 2, 1, 1),)


def test_quality_command_line_hands_replay_arguments_to_the_replay(tmp_path: Path) -> None:
    pairs: Path = tmp_path / "pairs"
    _pair(pairs, "pair")
    base: str = str(tmp_path / "base")
    other: str = str(tmp_path / "other")
    assert quality_main.main(["replay", str(pairs), "--out", base]) == 0
    assert quality_main.main(["replay", str(pairs), "--out", other]) == 0
    assert quality_main.main(["replay", "--compare", base, other]) == 0
    assert quality_main.main(["replay", "--compare", base, other, "--events"]) == 0

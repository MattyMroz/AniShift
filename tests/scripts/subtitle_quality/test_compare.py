from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from PIL import Image
from pysubs2 import SSAFile

from anishift.platform.binaries import Binary, resolve_binary
from scripts.subtitle_quality import __main__ as quality_main
from scripts.subtitle_quality import compare, metrics
from scripts.subtitle_quality.episode import SOURCE_NAME
from scripts.subtitle_quality.render import GALLERY_WIDTH
from scripts.subtitle_quality.replay import MAPPING_NAME

if TYPE_CHECKING:
    from pathlib import Path

    from pysubs2 import SSAEvent

_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, \
Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, \
MarginV, Encoding
Style: Default,Arial,26,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,20,1
Style: Sign,Arial,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

_TIMES = (
    ("0:00:01.00", "0:00:03.00", "Default"),
    ("0:00:04.00", "0:00:06.00", "Default"),
    ("0:00:04.00", "0:00:06.00", "Sign"),
    ("0:00:04.00", "0:00:06.00", "Sign"),
    ("0:00:07.00", "0:00:09.00", "Default"),
)

_SOURCE = (
    "Where are you going?",
    "I really need to find my brother.",
    r"{\pos(200,100)}Bakery",
    r"{\pos(440,100)}Exit",
    "See you.",
)

_BEFORE = (
    "Where are you going?",
    r"Naprawdę muszę\Nznaleźć brata.",
    r"{\pos(200,100)}Piekarnia",
    r"{\pos(440,100)}Wyjście",
    "Na razie.",
)

_AFTER = (
    "Dokąd idziesz?",
    r"Naprawdę muszę znaleźć\Nbrata.",
    r"{\fscx150\pos(200,100)}Piekarnia",
    r"{\fscx250\pos(440,100)}Wyjście",
    r"Na {\i1}razie{\i0}.",
)

_PAIR = "library/pair"


def _script(texts: tuple[str, ...]) -> str:
    lines: list[str] = [
        f"Dialogue: 0,{start},{end},{style},,0,0,0,,{text}"
        for (start, end, style), text in zip(_TIMES, texts, strict=True)
    ]
    return _HEADER + "\n".join(lines) + "\n"


def _pairs(root: Path) -> Path:
    directory: Path = root / _PAIR
    directory.mkdir(parents=True)
    (directory / SOURCE_NAME).write_text(_script(_SOURCE), encoding="utf-8")
    return root


def _run(
    root: Path,
    name: str,
    texts: tuple[str, ...],
    *,
    decisions: list[str] | None = None,
    inputs: str = "Where are you going?",
) -> Path:
    run: Path = root / name
    output: str = f"{_PAIR}.pl.ass"
    (run / "library").mkdir(parents=True)
    (run / output).write_text(_script(texts), encoding="utf-8")
    entry: dict[str, Any] = {"pair": _PAIR, "output": output, "inputs": [{"index": 0, "text": inputs}], "excluded": [0]}
    if decisions is not None:
        entry[compare.DECISIONS_KEY] = decisions
    mapping: dict[str, Any] = {"rule": "", "pairs": [entry], "skipped": [{"pair": "library/lonely", "reason": "none"}]}
    (run / MAPPING_NAME).write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    return run


def _kinds(selection: compare.Selection) -> list[str]:
    return sorted(case.kind for case in selection.cases)


def _requires_ffmpeg() -> None:
    if resolve_binary(Binary.FFMPEG) is None:
        pytest.skip("ffmpeg is not installed")


@pytest.mark.unit
def test_marker_layout_places_style_tags_by_visible_characters_and_ignores_line_breaks() -> None:
    assert compare.marker_layout(r"Na {\i1}razie{\i0}.") == ((2, ("\\i1",)), (7, ("\\i0",)))
    assert compare.marker_layout(r"Na\N{\i1}razie{\i0}.") == compare.marker_layout(r"Na {\i1}razie{\i0}.")
    assert compare.marker_layout(r"{\pos(1,2)}Na razie.") == ()
    assert compare.marker_layout(r"{\i1}Na{\i0} razie.") != compare.marker_layout(r"Na {\i1}razie{\i0}.")


@pytest.mark.unit
def test_tagged_view_keeps_only_style_tags_and_joins_lines() -> None:
    assert compare.tagged_view(r"{\pos(1,2)\i1}Nie,\Nnie{\i0} mówiliście!") == r"{\i1}Nie, / nie{\i0} mówiliście!"


@pytest.mark.unit
def test_episode_title_drops_release_groups_checksums_and_release_details() -> None:
    assert (
        compare.episode_title("library/[Erai-raws] Seihantai 2nd Season - 10 [1080p CR WEB-DL][5752ED65]")
        == "Seihantai 2nd Season - 10"
    )
    assert compare.episode_title("library/The.Apothecary.Diaries.S03E01.Locusts.1080p.CR.WEB-DL") == (
        "The Apothecary Diaries S03E01 Locusts"
    )
    assert compare.episode_title("corpus-pairs/kaguya-s1-06") == "kaguya-s1-06"


@pytest.mark.unit
def test_changed_events_leave_excluded_events_out_and_count_style_definition_changes() -> None:
    before: SSAFile = SSAFile.from_string(_script(_BEFORE))
    after: SSAFile = SSAFile.from_string(_script(_BEFORE))
    after.events[0].text = "Gdzie idziesz?"
    assert compare.changed_events(before, after, frozenset({0})) == []
    after.styles["Sign"].fontsize = 50
    assert compare.changed_events(before, after, frozenset({0})) == [2, 3]


@pytest.mark.unit
def test_mismatched_events_differ_in_identity_or_wording_but_not_in_layout_tags_or_dialogue_clone() -> None:
    before: SSAFile = SSAFile.from_string(_script(_BEFORE))
    after: SSAFile = SSAFile.from_string(_script(_AFTER))
    assert compare.mismatched_events(before, after, frozenset({0})) == []
    after.events[1].style = "Default (dialog)"
    after.events[3].text = r"{\pos(440,100)}Wejście"
    after.events[4].end += 10
    after.events[2].layer = 1
    assert compare.mismatched_events(before, after, frozenset({0})) == [2, 3, 4]


@pytest.mark.unit
def test_hidden_text_appends_full_transparency_after_every_override() -> None:
    assert compare.hidden_text(r"{\1a&H00&}Hi{\i1}x") == r"{\alpha&HFF&}{\1a&H00&\alpha&HFF&}Hi{\i1\alpha&HFF&}x"


@pytest.mark.unit
def test_chosen_keeps_every_hard_case_and_the_highest_ranked_cases_of_each_kind() -> None:
    cases: list[compare.Case] = [
        compare.Case(_PAIR, compare.KIND_BREAKS, 1, (1,), "", "", "", 1.0),
        compare.Case(_PAIR, compare.KIND_BREAKS, 2, (2,), "", "", "", 3.0),
        compare.Case(_PAIR, compare.KIND_HARD, 3, (), "", "", ""),
        compare.Case(_PAIR, compare.KIND_HARD, 4, (), "", "", ""),
        compare.Case(_PAIR, compare.KIND_WIDTH, 5, (3,), "", "", "", 0.5),
    ]
    shown: list[compare.Case] = compare.chosen(cases, 1)
    assert [(case.kind, case.time_ms) for case in shown] == [
        (compare.KIND_HARD, 3),
        (compare.KIND_HARD, 4),
        (compare.KIND_WIDTH, 5),
        (compare.KIND_BREAKS, 2),
    ]


@pytest.mark.integration
def test_identical_replays_give_no_case_and_keep_the_mapping_skips(tmp_path: Path) -> None:
    pairs: Path = _pairs(tmp_path / "pairs")
    base: Path = _run(tmp_path, "base", _BEFORE)
    selection: compare.Selection = compare.find_cases(base, base, pairs, tmp_path / "work")
    assert selection.cases == ()
    assert selection.skipped == (("library/lonely", "none"),)
    assert selection.undecided == (_PAIR,)


@pytest.mark.integration
def test_pairs_with_different_inputs_or_event_counts_are_skipped(tmp_path: Path) -> None:
    pairs: Path = _pairs(tmp_path / "pairs")
    base: Path = _run(tmp_path, "base", _BEFORE)
    other: Path = _run(tmp_path, "other", _BEFORE, inputs="Gdzie idziesz?")
    hard: tuple[compare.HardCase, ...] = (compare.HardCase(_PAIR, 5000, "Opis"),)
    selection: compare.Selection = compare.find_cases(base, other, pairs, tmp_path / "work", hard)
    assert selection.cases == ()
    assert selection.skipped == (
        ("library/lonely", "none"),
        (_PAIR, "inputs differ"),
        (_PAIR, "hard case pair not compared"),
    )
    shorter: Path = tmp_path / "shorter"
    _run(tmp_path, "shorter", _BEFORE)
    output: Path = shorter / f"{_PAIR}.pl.ass"
    output.write_text(output.read_text(encoding="utf-8").rsplit("Dialogue:", 1)[0], encoding="utf-8")
    assert compare.find_cases(base, shorter, pairs, tmp_path / "work").skipped[-1] == (_PAIR, "event counts differ")


@pytest.mark.integration
def test_line_style_tag_and_reader_decision_changes_become_cases_without_rendering(tmp_path: Path) -> None:
    pairs: Path = _pairs(tmp_path / "pairs")
    decisions: list[str] = ["spoken", "spoken", "displayed", "displayed", "spoken"]
    flipped: list[str] = ["displayed", "spoken", "displayed", "spoken", "spoken"]
    texts: tuple[str, ...] = (_AFTER[0], _AFTER[1], _BEFORE[2], _BEFORE[3], _AFTER[4])
    base: Path = _run(tmp_path, "base", _BEFORE, decisions=decisions)
    other: Path = _run(tmp_path, "other", texts, decisions=flipped)
    selection: compare.Selection = compare.find_cases(base, other, pairs, tmp_path / "work")
    assert _kinds(selection) == sorted((compare.KIND_BREAKS, compare.KIND_MARKERS, compare.KIND_DECISION))
    cases: dict[str, compare.Case] = {case.kind: case for case in selection.cases}
    assert cases[compare.KIND_BREAKS].indexes == (1,)
    assert cases[compare.KIND_BREAKS].description == (
        "Podział wierszy zmienił się z „Naprawdę muszę / znaleźć brata.” na „Naprawdę muszę znaleźć / brata.”."
    )
    assert cases[compare.KIND_MARKERS].indexes == (4,)
    assert cases[compare.KIND_DECISION].indexes == (3,)
    assert cases[compare.KIND_DECISION].tags == (compare.TAG_SCREEN, compare.TAG_SPOKEN)
    assert selection.undecided == ()
    assert selection.mismatches == ()
    assert not (tmp_path / "work").exists()


@pytest.mark.integration
def test_events_with_other_wording_or_timing_are_reported_apart_and_never_as_layout_changes(tmp_path: Path) -> None:
    pairs: Path = _pairs(tmp_path / "pairs")
    texts: tuple[str, ...] = (_BEFORE[0], r"Naprawdę muszę znaleźć\Nsiostrę.", _BEFORE[2], _BEFORE[3], _AFTER[4])
    base: Path = _run(tmp_path, "base", _BEFORE, decisions=["spoken"] * 5)
    other: Path = _run(tmp_path, "other", texts, decisions=["spoken", "displayed", "spoken", "spoken", "displayed"])
    output: Path = other / f"{_PAIR}.pl.ass"
    output.write_text(output.read_text(encoding="utf-8").replace("0:00:07.00", "0:00:07.10"), encoding="utf-8")
    hard: tuple[compare.HardCase, ...] = (compare.HardCase(_PAIR, 5000, "Opis"),)
    selection: compare.Selection = compare.find_cases(base, other, pairs, tmp_path / "work", hard)
    assert [(mismatch.index, mismatch.after) for mismatch in selection.mismatches] == [
        (1, "Naprawdę muszę znaleźć / siostrę."),
        (4, "Na razie."),
    ]
    assert [(case.kind, case.indexes) for case in selection.cases] == [(compare.KIND_HARD, (2, 3))]
    index: str = compare.index_text(selection, [], ("base", "other"))
    assert "## Inny tekst — poza porównaniem" in index
    assert "| pair | 2 | 0:00:04.00 | Naprawdę muszę / znaleźć brata. | Naprawdę muszę znaleźć / siostrę. |" in index


@pytest.mark.integration
def test_sign_width_and_new_collision_are_found_and_reversed_into_a_removed_collision(tmp_path: Path) -> None:
    _requires_ffmpeg()
    pairs: Path = _pairs(tmp_path / "pairs")
    base: Path = _run(tmp_path, "base", _BEFORE)
    other: Path = _run(tmp_path, "other", _AFTER)
    forward: compare.Selection = compare.find_cases(base, other, pairs, tmp_path / "work")
    assert _kinds(forward) == sorted(
        (compare.KIND_WIDTH, compare.KIND_WIDTH, compare.KIND_NEW_COLLISION, compare.KIND_BREAKS, compare.KIND_MARKERS)
    )
    widths: list[compare.Case] = [case for case in forward.cases if case.kind == compare.KIND_WIDTH]
    assert {case.indexes for case in widths} == {(2,), (3,)}
    assert all(case.rank > 0.4 for case in widths)
    collision: compare.Case = next(case for case in forward.cases if case.kind == compare.KIND_NEW_COLLISION)
    assert collision.indexes == (2, 3)
    assert collision.time_ms == 5000
    assert collision.description == (
        "Prostokąty obwiedni szyldów „Piekarnia” i „Wyjście” przecinają się po zmianie, a przed nią się nie przecinały."
    )
    backward: compare.Selection = compare.find_cases(other, base, pairs, tmp_path / "work")
    removed: compare.Case = next(case for case in backward.cases if case.kind == compare.KIND_REMOVED_COLLISION)
    assert removed.description.endswith("przecinały się przed zmianą, a po niej przestały się przecinać.")
    assert compare.KIND_NEW_COLLISION not in _kinds(backward)


@pytest.mark.integration
def test_hard_case_frames_the_compared_events_visible_at_its_moment_and_leaves_excluded_ones_out(
    tmp_path: Path,
) -> None:
    _requires_ffmpeg()
    pairs: Path = _pairs(tmp_path / "pairs")
    base: Path = _run(tmp_path, "base", _BEFORE)
    other: Path = _run(tmp_path, "other", _AFTER)
    hard: tuple[compare.HardCase, ...] = (compare.HardCase(_PAIR, 2000, "Opis"), compare.HardCase(_PAIR, 5000, "Opis"))
    selection: compare.Selection = compare.find_cases(base, other, pairs, tmp_path / "work", hard)
    cases: list[compare.Case] = [case for case in selection.cases if case.kind == compare.KIND_HARD]
    assert [(case.indexes, case.description) for case in cases] == [
        ((), "Opis (zmienione zdarzenia w tej chwili: 0 z 0)."),
        ((1, 2, 3), "Opis (zmienione zdarzenia w tej chwili: 3 z 3)."),
    ]


@pytest.mark.integration
def test_placed_boxes_find_events_where_the_rendered_frame_draws_them_among_concurrent_lines(tmp_path: Path) -> None:
    _requires_ffmpeg()
    script: Path = tmp_path / "stack.ass"
    lines: list[str] = [
        r"Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Pierwsza kwestia",
        r"Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Druga kwestia",
        r"Dialogue: 0,0:00:01.00,0:00:03.00,Sign,,0,0,0,,{\pos(200,100)}Piekarnia",
        r"Dialogue: 0,0:00:05.00,0:00:06.00,Sign,,0,0,0,,{\pos(440,100)}Wyjście",
    ]
    script.write_text(_HEADER + "\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "work").mkdir()
    files: compare.PairFiles = compare.PairFiles(tmp_path / "pair", script, script, tmp_path / "work")
    size: tuple[int, int] = (640, 360)
    shown: tuple[Image.Image, Image.Image] = compare.render_halves(files, (script, script), 2000, size)

    def boxes(*indexes: int) -> tuple[metrics.Box | None, metrics.Box | None]:
        case: compare.Case = compare.Case(_PAIR, compare.KIND_HARD, 2000, indexes, "", "", "")
        return compare.placed_boxes(files, case, shown, size)

    lower, lower_after = boxes(0)
    upper, _ = boxes(1)
    sign, _ = boxes(2)
    assert lower is not None
    assert upper is not None
    assert sign is not None
    assert lower == lower_after
    assert upper[3] <= lower[1] + 4
    assert sign[0] < 400 < sign[2]
    assert sign[1] < 200 < sign[3]
    assert boxes(3) == (None, None)


@pytest.mark.integration
def test_compare_command_renders_a_gallery_with_an_index_and_reports_changes(tmp_path: Path) -> None:
    _requires_ffmpeg()
    pairs: Path = _pairs(tmp_path / "pairs")
    base: str = str(_run(tmp_path, "base", _BEFORE))
    other: str = str(_run(tmp_path, "other", _AFTER))
    hard: Path = tmp_path / "hard.json"
    hard.write_text(json.dumps([{"pair": _PAIR, "time_ms": 5000, "description": "Opis"}]), encoding="utf-8")
    out: Path = tmp_path / "gallery"
    arguments: list[str] = ["--pairs", str(pairs), "--out", str(out), "--size", "1"]
    assert quality_main.main(["compare", base, other, *arguments, "--hard", str(hard)]) == 1
    images: list[Path] = sorted(out.glob("*.png"))
    assert [image.name for image in images] == [f"{number:02d}.png" for number in range(1, 6)]
    with Image.open(images[0]) as image:
        assert image.width == 2 * GALLERY_WIDTH + 16
    index: str = (out / compare.INDEX_NAME).read_text(encoding="utf-8")
    assert "| szerokość szyldu | 2 | 1 |" in index
    assert "[05.png](05.png)" in index
    assert not (out / ".work").exists()
    assert quality_main.main(["compare", base, base, *arguments]) == 0
    assert list(out.glob("*.png")) == []
    assert "Brak przypadków: 0 zmian." in (out / compare.INDEX_NAME).read_text(encoding="utf-8")


@pytest.mark.unit
def test_decision_cases_compare_reader_decisions_event_by_event_outside_excluded_events() -> None:
    events: list[SSAEvent] = metrics.dialogue(SSAFile.from_string(_script(_BEFORE)))
    decisions: tuple[list[str], list[str]] = (["spoken"] * 5, ["displayed"] + ["spoken"] * 3 + ["displayed"])
    cases: list[compare.Case] = compare.decision_cases(_PAIR, events, decisions, frozenset({0}))
    assert [(case.indexes, case.description) for case in cases] == [
        ((4,), "Decyzja lektora zmieniła się z „czyta” na „tylko ekran”.")
    ]

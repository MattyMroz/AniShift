from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pysubs2 import SSAEvent, SSAFile

from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.fonts import system_font_paths
from scripts.subtitle_quality import calibrate
from scripts.subtitle_quality.episode import OUTPUT_NAME, SOURCE_NAME

_SCRIPT = """[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, \
Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, \
MarginV, Encoding
Style: Default,Arial,28,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1.5,0,2,20,20,20,1
Style: Sign,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

_EN_EVENTS = (
    "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Where are you going?",
    "Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,This line of dialogue is long enough to wrap twice on screen",
    "Dialogue: 0,0:00:07.00,0:00:09.00,Sign,,0,0,0,,{\\pos(320,100)}Station",
    "Dialogue: 0,0:00:10.00,0:00:12.00,Sign,,0,0,0,,{\\move(10,10,200,10)}Moving",
)
_PL_EVENTS = (
    "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Dokąd idziesz?",
    "Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,Ta kwestia jest tak długa, że zawinie się na ekranie dwa razy",
    "Dialogue: 0,0:00:07.00,0:00:09.00,Sign,,0,0,0,,{\\pos(320,100)}Stacja",
    "Dialogue: 0,0:00:10.00,0:00:12.00,Sign,,0,0,0,,{\\move(10,10,200,10)}Ruch",
)


def _subs(events: tuple[str, ...]) -> SSAFile:
    return SSAFile.from_string(_SCRIPT + "\n".join(events) + "\n")


_ROW = calibrate.Row(
    pair="pair",
    lang="pl",
    kind="dialogue",
    case="static",
    style="Default",
    text="text",
    status="exact",
    lines=1,
    wrapped=False,
    wrap_slack=10.0,
    estimate=(100.0, 300.0, 300.0, 330.0),
    libass=(100, 300, 300, 330),
    clipped=False,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "start", "end", "expected"),
    [
        ("Plain line", 0, 2000, True),
        (r"{\pos(10,10)\fad(200,200)}Sign", 0, 2000, True),
        (r"{\fad(1500,0)}Slow fade", 0, 2000, False),
        (r"{\move(1,1,5,5)}Moving", 0, 2000, False),
        (r"{\t(\fscx120)}Growing", 0, 2000, False),
        (r"{\k20}Ka{\k20}ra", 0, 2000, False),
        (r"{\p1}m 0 0 l 10 0 10 10", 0, 2000, False),
        (r"Top\N\NBottom", 0, 2000, False),
        ("Too long", 0, 25000, False),
        ("Instant", 1000, 1000, False),
    ],
)
def test_is_static_keeps_visible_text_drawn_the_same_way_for_its_lifetime(
    text: str, start: int, end: int, expected: bool
) -> None:
    subs = _subs(())

    assert calibrate.is_static(SSAEvent(start=start, end=end, style="Default", text=text), subs) is expected


@pytest.mark.unit
def test_is_static_rejects_events_of_an_undefined_style() -> None:
    assert not calibrate.is_static(SSAEvent(start=0, end=1000, style="Missing", text="Text"), _subs(()))


@pytest.mark.unit
def test_spaced_spreads_the_kept_items_evenly() -> None:
    assert calibrate.spaced(list(range(10)), 20) == list(range(10))
    assert calibrate.spaced(list(range(10)), 5) == [0, 2, 4, 6, 8]


@pytest.mark.unit
def test_row_errors_are_relative_to_the_libass_box_and_lines_follow_the_height_difference() -> None:
    row = replace(_ROW, estimate=(100.0, 300.0, 303.0, 330.0), libass=(100, 300, 300, 330), lines=1)
    two_lines = replace(_ROW, estimate=(100.0, 300.0, 300.0, 330.0), libass=(100, 286, 300, 344), lines=1)

    assert row.width_error == pytest.approx(1.5)
    assert row.height_error == 0.0
    assert row.libass_lines == 1
    assert two_lines.libass_lines == 2


@pytest.mark.unit
def test_row_is_comparable_only_with_a_whole_large_enough_libass_box() -> None:
    assert _ROW.comparable
    assert not replace(_ROW, libass=None).comparable
    assert not replace(_ROW, clipped=True).comparable
    assert not replace(_ROW, libass=(100, 300, 105, 330)).comparable


@pytest.mark.unit
def test_gates_check_width_on_wide_exact_static_samples_and_height_on_all_exact_ones() -> None:
    accurate = [replace(_ROW, estimate=(100.0, 300.0, 300.5, 330.5)) for _ in range(20)]
    narrow_miss = [replace(_ROW, estimate=(100.0, 300.0, 160.0, 340.0), libass=(100, 300, 150, 330)) for _ in range(5)]
    approximate_miss = [replace(_ROW, status="approximate", estimate=(100.0, 300.0, 400.0, 360.0)) for _ in range(5)]

    passing = calibrate.gates([*accurate, *narrow_miss, *approximate_miss])
    failing = calibrate.gates([*accurate, *(replace(_ROW, estimate=(100.0, 300.0, 310.0, 340.0)) for _ in range(5))])

    assert [gate.passed for gate in passing] == [True, True, False]
    assert [gate.passed for gate in failing] == [False, False, False]


@pytest.mark.unit
def test_wrap_verdicts_accept_a_different_line_count_only_at_the_wrap_limit() -> None:
    agree = replace(_ROW, wrapped=True, lines=2, estimate=(100.0, 300.0, 300.0, 360.0), libass=(100, 300, 300, 360))
    borderline = replace(_ROW, case="margins", lines=2, wrap_slack=0.3, estimate=(0.0, 300.0, 300.0, 360.0))
    wrong = replace(borderline, wrap_slack=5.0)
    unwrapped = _ROW

    verdicts = calibrate.wrap_verdicts([agree, borderline, wrong, unwrapped])

    assert [verdict for _, verdict in verdicts] == ["agree", "borderline", "disagree"]
    assert calibrate.wraps_pass([agree, borderline])
    assert not calibrate.wraps_pass([agree, wrong])


@pytest.mark.integration
def test_calibrate_renders_static_samples_and_wrap_controls_and_writes_the_report(tmp_path: Path) -> None:
    if resolve_binary(Binary.FFMPEG) is None:
        pytest.skip("ffmpeg is not installed")
    if not any(path.name.casefold() == "arial.ttf" for path in system_font_paths()):
        pytest.skip("system Arial is not available")
    pair = tmp_path / "pairs" / "episode"
    (pair / "fonts").mkdir(parents=True)
    _subs(_EN_EVENTS).save(str(pair / SOURCE_NAME))
    _subs(_PL_EVENTS).save(str(pair / OUTPUT_NAME))

    rows, report = calibrate.calibrate([tmp_path / "pairs"], tmp_path / "out", jobs=2)

    static = [row for row in rows if row.case == "static"]
    assert {(row.lang, row.text) for row in static} >= {("en", "Where are you going?"), ("pl", "Stacja")}
    assert all("Moving" not in row.text for row in rows)
    assert {row.case for row in rows} == {"static", "no-wrap", "margins"}
    assert all(row.comparable for row in rows)
    assert max(row.width_error for row in static) < 3
    assert calibrate.wraps_pass(rows)
    assert "gates:" in report
    assert (tmp_path / "out" / calibrate.SUMMARY_NAME).read_text(encoding="utf-8").startswith("samples ")
    assert len(json.loads((tmp_path / "out" / calibrate.ROWS_NAME).read_text(encoding="utf-8"))) == len(rows)

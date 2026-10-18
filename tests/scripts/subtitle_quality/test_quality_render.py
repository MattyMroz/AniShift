from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from pysubs2 import SSAFile

from anishift.platform.binaries import Binary, resolve_binary
from scripts.subtitle_quality import metrics, render

_SCRIPT = """[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, \
Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, \
MarginV, Encoding
Style: Sign,Arial,30,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,10,20,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Sign,,0,0,0,,{\\fad(300,0)\\pos(320,180)}Exit
Dialogue: 0,0:00:10.00,0:00:20.00,Sign,,0,0,0,,{\\an4\\pos(600,180)\\clip(0,0,620,360)}A very long translated sign
Dialogue: 0,0:00:30.00,0:00:31.00,Sign,,0,0,0,,{\\move(10,20,30,40,0,500)\\org(5,5)}Moving
"""

_SIZE = (640, 360)


def _subs() -> SSAFile:
    return SSAFile.from_string(_SCRIPT)


def test_measurement_file_isolates_events_on_padded_canvas() -> None:
    subs = _subs()
    canvas, slot_s = render.measurement_file(subs, subs.events, _SIZE)
    assert slot_s == 12
    assert (canvas.info["PlayResX"], canvas.info["PlayResY"]) == ("1280", "720")
    assert [(event.start, event.end) for event in canvas.events] == [
        (11000, 13000),
        (19000, 29000),
        (35500, 36500),
    ]
    assert canvas.events[0].text == r"{\fad(300,0)\pos(640,360)}Exit"
    assert canvas.events[1].text == r"{\an4\pos(920,360)}A very long translated sign"
    assert canvas.events[2].text == r"{\move(330,200,350,220,0,500)\org(325,185)}Moving"
    assert (canvas.events[0].marginl, canvas.events[0].marginr, canvas.events[0].marginv) == (330, 340, 210)


def test_parse_font_log_reports_fallbacks_and_missing_glyphs() -> None:
    log = "\n".join(
        (
            "[Parsed_ass_0 @ 0] fontselect: (Arial, 400, 0) -> ArialMT, 0, ArialMT",
            "[Parsed_ass_0 @ 0] fontselect: (Roboto Medium, 500, 0) -> Roboto-Medium, 0, Roboto-Medium",
            "[Parsed_ass_0 @ 0] fontselect: (Missing Sans, 400, 0) -> ArialMT, 0, ArialMT",
            "[Parsed_ass_0 @ 0] Glyph 0x105 not found, selecting one more font for (Comic Hand, 400, 0)",
        )
    )
    report = render.parse_font_log(log)
    assert report.fallbacks == ("Missing Sans -> ArialMT",)
    assert report.missing_glyphs == {"Comic Hand": "ą"}


@pytest.mark.integration
def test_measure_boxes_finds_text_extent_beyond_the_screen(tmp_path: Path) -> None:
    if resolve_binary(Binary.FFMPEG) is None:
        pytest.skip("ffmpeg is not installed")
    subs = _subs()
    boxes, _ = render.measure_boxes(subs, subs.events[:2], _SIZE, tmp_path, "measure")
    centred, overflowing = boxes
    assert centred is not None
    assert overflowing is not None
    assert metrics.offscreen_px(centred, _SIZE) == 0
    assert centred[0] < 320 < centred[2]
    assert centred[2] - centred[0] < 100
    assert overflowing[0] >= 595
    assert overflowing[2] > _SIZE[0] + 100
    assert not (tmp_path / "measure-frames").exists()


@pytest.mark.integration
def test_measure_boxes_measures_events_beyond_the_ass_time_limit(tmp_path: Path) -> None:
    if resolve_binary(Binary.FFMPEG) is None:
        pytest.skip("ffmpeg is not installed")
    subs = _subs()
    long_sign = subs.events[0].copy()
    long_sign.end = long_sign.start + 3_598_000
    events = [long_sign.copy() for _ in range(12)]
    boxes, _ = render.measure_boxes(subs, events, _SIZE, tmp_path, "measure")
    assert len(boxes) == 12
    assert all(box is not None for box in boxes)
    assert render.batch_size(events) == 8


def test_nearest_frame_picks_the_closest_saved_moment(tmp_path: Path) -> None:
    assert render.nearest_frame(tmp_path / "missing", 1000) is None
    for name in ("1000.jpg", "5000.jpg", "cover.jpg", "3000.png"):
        (tmp_path / name).touch()
    assert render.nearest_frame(tmp_path, 2900) == tmp_path / "1000.jpg"
    assert render.nearest_frame(tmp_path, 3100) == tmp_path / "5000.jpg"


@pytest.mark.integration
def test_render_shot_uses_the_nearest_relative_saved_frame(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if resolve_binary(Binary.FFMPEG) is None:
        pytest.skip("ffmpeg is not installed")
    work = tmp_path / "work"
    work.mkdir()
    script = tmp_path / "script.ass"
    script.write_text(_SCRIPT, encoding="utf-8")
    render.copy_scripts(script, None, work)
    (tmp_path / "frames").mkdir()
    Image.new("RGB", (640, 360), (200, 30, 30)).save(tmp_path / "frames" / "2100.jpg")
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "shot" / "01.png"
    render.render_shot(render.Shot(2000, target, "caption"), None, Path("frames"), _SIZE, work)
    with Image.open(target) as shot:
        pixel = shot.convert("RGB").getpixel((render.GALLERY_WIDTH - 10, 300))
    assert isinstance(pixel, tuple)
    assert pixel[0] > 150
    assert max(pixel[1:]) < 80

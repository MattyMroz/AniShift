from __future__ import annotations

import asyncio
import threading
from dataclasses import replace
from importlib.resources import files
from io import StringIO
from types import SimpleNamespace
from typing import cast

import pytest
from PIL import Image
from prompt_toolkit import Application
from prompt_toolkit.application.current import create_app_session, set_app
from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import DummyInput
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.output.vt100 import Vt100_Output
from rich.text import Text

import anishift.cli.interactive.mascot_native as native_module
import anishift.cli.interactive.native_image as image_module
import anishift.cli.interactive.prompts as prompts_module
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive.app import _auto_content, _home_content, _message_content, _QueueView
from anishift.cli.interactive.home import brand_for_geometry
from anishift.cli.interactive.mascot import MascotController, MascotState
from anishift.cli.interactive.native_image import NATIVE_IMAGE_ANCHOR, NativeImage
from anishift.cli.interactive.pointer import FrameSelection
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.interactive.prompts import (
    HomeGeometry,
    TerminalRenderer,
    _native_anchor,
    resolve_auto_geometry,
    resolve_home_geometry,
)
from anishift.cli.interactive.settings import SettingsController


class _Progress:
    row_count = 1
    active_row = 0

    def render(self, columns: int, *, offset: int = 0, limit: int | None = None) -> Text:
        del columns, offset, limit
        return Text("Progress")


def _image(*, cell_columns: int = 18, cell_rows: int = 10, payloads: tuple[str, ...] = ("frame",)) -> NativeImage:
    return NativeImage(
        payloads=payloads,
        frame_seconds=(0.06,) * len(payloads),
        cycle_seconds=0.06 * len(payloads),
        cell_columns=cell_columns,
        cell_rows=cell_rows,
        layout_rows=cell_rows,
    )


def _renderer_with(image: NativeImage | None, writes: list[str]) -> TerminalRenderer:
    output = SimpleNamespace(write_raw=writes.append, flush=lambda: None)
    renderer = object.__new__(TerminalRenderer)
    renderer._application = cast(
        "Application[None]",
        SimpleNamespace(
            output=output,
            exit=lambda: None,
            invalidate=lambda: None,
            is_done=False,
            renderer=SimpleNamespace(reset=lambda **_kwargs: None, _last_screen=object()),
        ),
    )
    renderer._native_mascot = image
    renderer._image_provider = None
    renderer._drawn = None
    renderer._terminal_size = None
    renderer._use_mascot = True
    return renderer


def test_native_mascot_is_ten_text_rows_tall_in_a_small_cell_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native_module, "_is_windows", lambda: True)
    monkeypatch.setattr(native_module, "terminal_cell_size", lambda: (7, 17))

    image: NativeImage | None = native_module.load_native_mascot()

    assert image is not None
    assert len(image.payloads) == 46
    assert all(payload.startswith('\x1bP9;1;0q"1;1;170;178') for payload in image.payloads)
    assert all(payload.endswith("\x1b\\") for payload in image.payloads)
    assert (image.cell_columns, image.cell_rows, image.layout_rows) == (25, 11, 10)
    assert image.cycle_seconds == pytest.approx(2.76)


def test_native_mascot_grows_with_the_font_of_a_large_cell_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native_module, "_is_windows", lambda: True)
    monkeypatch.setattr(native_module, "terminal_cell_size", lambda: (10, 20))

    image: NativeImage | None = native_module.load_native_mascot()

    assert image is not None
    assert all(payload.startswith('\x1bP9;1;0q"1;1;200;210') for payload in image.payloads)
    assert (image.cell_columns, image.cell_rows, image.layout_rows) == (20, 11, 10)


def test_native_mascot_assumes_a_cell_when_the_terminal_reports_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native_module, "_is_windows", lambda: True)
    monkeypatch.setattr(native_module, "terminal_cell_size", lambda: None)

    image: NativeImage | None = native_module.load_native_mascot()

    assert image is not None
    assert all(payload.startswith('\x1bP9;1;0q"1;1;170;178') for payload in image.payloads)
    assert (image.cell_columns, image.cell_rows, image.layout_rows) == (22, 11, 10)


def test_native_mascot_is_disabled_outside_supported_terminals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native_module, "_is_windows", lambda: False)

    assert native_module.load_native_mascot() is None


def test_cell_size_comes_from_the_terminal_cell_report(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(image_module, "_query_terminal", lambda _query: "\x1b[6;20;10t")

    assert image_module.terminal_cell_size() == (10, 20)


def test_cell_size_falls_back_to_the_text_area_report(monkeypatch: pytest.MonkeyPatch) -> None:
    replies: dict[str, str] = {"\x1b[16t": "", "\x1b[14t": "\x1b[4;340;160t"}
    monkeypatch.setattr(image_module, "_query_terminal", lambda query: replies[query])
    monkeypatch.setattr(
        "anishift.cli.interactive.native_image.shutil.get_terminal_size",
        lambda fallback: SimpleNamespace(columns=20, lines=20),
    )

    assert image_module.terminal_cell_size() == (8, 17)


def test_cell_size_is_unknown_without_any_terminal_report(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(image_module, "_query_terminal", lambda _query: "")

    assert image_module.terminal_cell_size() is None


def test_native_brand_reserves_layout_and_exposes_one_anchor() -> None:
    geometry: HomeGeometry = resolve_home_geometry(120, 40)

    brand: Text = brand_for_geometry(geometry, native_mascot=True)
    position: tuple[int, int] | None = _native_anchor(brand.plain)

    assert brand.plain.count(NATIVE_IMAGE_ANCHOR) == 1
    assert position is not None
    assert position[0] == 0
    assert len(brand.split("\n")) == geometry.mascot_rows


def test_the_mascot_is_level_with_the_wordmark_at_the_bottom() -> None:
    geometry: HomeGeometry = resolve_home_geometry(120, 40, (20, 10))

    brand: Text = brand_for_geometry(geometry, native_mascot=True)
    lines: list[str] = [line.plain.replace(NATIVE_IMAGE_ANCHOR, " ") for line in brand.split("\n")]

    assert len(lines) == 10
    assert [index for index, line in enumerate(lines) if line.strip()] == [4, 5, 6, 7, 8, 9]


def test_home_geometry_reserves_the_measured_mascot_footprint() -> None:
    geometry: HomeGeometry = resolve_home_geometry(120, 40, (16, 8))

    assert (geometry.mascot_columns, geometry.mascot_rows) == (16, 8)


def test_a_mascot_wider_than_the_terminal_is_dropped() -> None:
    geometry: HomeGeometry = resolve_home_geometry(15, 40, (16, 8))

    assert not geometry.show_mascot
    assert (geometry.mascot_columns, geometry.mascot_rows) == (0, 0)


def test_the_renderer_reports_the_cells_its_native_mascot_needs() -> None:
    renderer: TerminalRenderer = _renderer_with(_image(cell_columns=23, cell_rows=10), [])

    assert renderer.native_mascot_size == (23, 10)


def test_the_renderer_reports_no_native_mascot_size_without_an_image() -> None:
    renderer: TerminalRenderer = _renderer_with(None, [])

    assert renderer.native_mascot_size is None


def test_the_native_reservation_includes_the_painted_padding_row() -> None:
    renderer = _renderer_with(replace(_image(cell_rows=11), layout_rows=10), [])
    content = _auto_content(
        (120, 30),
        cast("RichRunProgress", _Progress()),
        MascotState.TTS,
        _QueueView(),
        native_size=renderer.native_mascot_size,
    )
    lines: list[str] = content.plain.split("\n")
    anchor: int = next(index for index, line in enumerate(lines) if NATIVE_IMAGE_ANCHOR in line)
    progress: int = next(index for index, line in enumerate(lines) if "Progress" in line)

    assert renderer.native_mascot_size == (18, 11)
    assert progress >= anchor + 11 + 1
    assert not lines[progress - 1].strip()


def test_home_balances_the_three_gaps_around_the_resting_brand_and_menu() -> None:
    content: Text = _home_content(120, 40, 0, MascotState.IDLE, native_size=(18, 10))
    lines: list[str] = [line.plain for line in content.split("\n")]

    anchor: int = next(index for index, line in enumerate(lines) if NATIVE_IMAGE_ANCHOR in line)
    menu_top: int = next(index for index, line in enumerate(lines) if "Panel" in line)
    menu_bottom: int = next(index for index, line in enumerate(lines) if "Wyjście" in line)
    gaps: tuple[int, int, int] = (anchor + 3, menu_top - anchor - 10, 40 - menu_bottom - 3)
    assert max(gaps) - min(gaps) <= 1


def test_resting_padding_matches_the_packaged_gif_silhouette() -> None:
    asset = files("anishift.cli.interactive.assets").joinpath("mascot", "idle", "01.gif")
    with asset.open("rb") as stream, Image.open(stream) as source:
        bounds = source.convert("RGBA").getbbox()
        assert bounds is not None
        resting_top: int = int(bounds[1] / source.height * native_module.MASCOT_FRAME_ROWS + 0.5)

    assert resting_top == native_module.MASCOT_REST_TOP_ROWS


def test_auto_reserves_mascot_space_above_progress() -> None:
    geometry = resolve_auto_geometry(120, 40, 1)

    content: Text = _auto_content(
        (120, 40), cast("RichRunProgress", _Progress()), MascotState.TTS, _QueueView(), native_size=(18, 10)
    )

    assert geometry.show_mascot
    assert (geometry.mascot_columns, geometry.mascot_rows) == (18, 10)
    assert NATIVE_IMAGE_ANCHOR in content.plain
    assert "Progress" in content.plain


@pytest.mark.parametrize(("columns", "rows", "visible"), [(60, 20, True), (120, 12, False), (200, 60, True)])
def test_auto_keeps_the_mascot_when_controls_fit(columns: int, rows: int, visible: bool) -> None:
    geometry = resolve_auto_geometry(columns, rows, 1)

    content: Text = _auto_content(
        (columns, rows),
        cast("RichRunProgress", _Progress()),
        MascotState.TTS,
        _QueueView(),
        native_size=(18, 10),
    )

    assert geometry.show_mascot is visible
    assert (NATIVE_IMAGE_ANCHOR in content.plain) is visible


def test_message_view_does_not_render_the_mascot() -> None:
    content: Text = _message_content(120, 40, Text("Problem"), MascotState.ERROR)

    assert NATIVE_IMAGE_ANCHOR not in content.plain
    assert "Problem" in content.plain


def test_settings_view_does_not_render_the_mascot() -> None:
    application = object.__new__(interactive_app._InteractiveApplication)
    application._lock = threading.Lock()
    application._mode = interactive_app._ViewMode.SETTINGS
    application._selected = 0
    application._message = Text()
    application._message_view = interactive_app._QueueView(following=False)
    application._progress = None
    application._settings = cast(
        "SettingsController",
        SimpleNamespace(render=lambda _columns, _rows: Text("Ustawienia"), view_key=tuple),
    )
    application._manual = None
    application._batch = None
    application._closing_at = None
    application._mascot = cast("MascotController", SimpleNamespace(state=MascotState.IDLE))
    application._renderer = cast("TerminalRenderer", SimpleNamespace(native_mascot_size=(20, 10)))
    application._directory = "~"
    application._frame_selection = FrameSelection()

    content: Text = application._render_frame(120, 40)

    assert NATIVE_IMAGE_ANCHOR not in content.plain
    assert "Ustawienia" in content.plain


def test_terminal_renderer_captures_normal_mouse_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompts_module, "load_native_mascot", lambda: None)
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        renderer = TerminalRenderer(lambda _columns, _rows: Text(), lambda _key: None)

    assert renderer._application.mouse_support()


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        ("", None),
        ("\x1b[?1;2c", None),
        ("\x1b[6;20;10t\x1b[?1;4;22c", (10, 20)),
        ("\x1b[?4c", (8, 17)),
    ],
)
def test_native_mascot_requires_explicit_sixel_support(
    monkeypatch: pytest.MonkeyPatch,
    report: str,
    expected: tuple[int, int] | None,
) -> None:
    monkeypatch.setattr(image_module, "_query_terminal", lambda _query: report)

    assert image_module.native_cell() == expected


def test_terminal_construction_never_encodes_animation(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden() -> None:
        pytest.fail("animation encoding must not block construction")

    monkeypatch.setattr(prompts_module, "load_native_mascot", forbidden)
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        renderer = TerminalRenderer(lambda _columns, _rows: Text(), lambda _key: None)

    assert renderer.native_mascot_size is None


def test_running_the_renderer_leaves_the_terminal_untouched() -> None:
    writes: list[str] = []
    renderer = _renderer_with(None, writes)
    renderer._application = cast(
        "Application[None]",
        SimpleNamespace(run=lambda: None, output=SimpleNamespace(write_raw=writes.append, flush=lambda: None)),
    )

    renderer.run()

    assert writes == []


def test_native_encoder_does_not_require_chafa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native_module, "_is_windows", lambda: True)
    monkeypatch.setattr(native_module, "terminal_cell_size", lambda: None)

    assert native_module.load_native_mascot() is not None


@pytest.mark.parametrize("next_frame", [Text("Settings"), Text(f"\n\n  {NATIVE_IMAGE_ANCHOR}")])
def test_native_repaint_never_exposes_the_primary_screen(next_frame: Text) -> None:
    stream = StringIO()
    output = Vt100_Output(stream, lambda: Size(rows=24, columns=80), term="xterm-256color")
    frames: list[Text] = [Text(NATIVE_IMAGE_ANCHOR), next_frame]
    with create_app_session(input=DummyInput(), output=output):
        renderer = TerminalRenderer(lambda _columns, _rows: frames.pop(0), lambda _key: None)
    renderer._native_mascot = _image()
    application = renderer._application
    with set_app(application):
        for _ in range(2):
            renderer._before_render(application)
            application.renderer.render(application, application.layout)
            renderer._after_render(application)

    assert not frames
    assert stream.getvalue().count("\x1b[?1049h") == 1
    assert "\x1b[?1049l" not in stream.getvalue()
    assert "\x1b[3J" not in stream.getvalue()
    application.renderer.reset()
    assert stream.getvalue().count("\x1b[?1049l") == 1


def test_real_application_exit_never_paints_on_the_restored_console() -> None:
    stream = StringIO()
    output = Vt100_Output(stream, lambda: Size(rows=24, columns=80), term="xterm-256color")
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=output):
        renderer = TerminalRenderer(lambda _columns, _rows: Text(NATIVE_IMAGE_ANCHOR), lambda _key: None)
        renderer._native_mascot = _image(payloads=("SIXEL_SENTINEL",))

        def close_after_first_frame() -> None:
            asyncio.get_running_loop().call_later(0.05, renderer.exit)

        renderer._application.run(pre_run=close_after_first_frame)

    before, separator, after = stream.getvalue().partition("\x1b[?1049l")
    assert separator
    assert "SIXEL_SENTINEL" in before
    assert "SIXEL_SENTINEL" not in after
    assert "\x1b[2J" not in after

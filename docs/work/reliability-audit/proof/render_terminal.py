"""Export offline snapshots of the real Rich views without touching user settings."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from PIL import Image, ImageDraw, ImageFont
from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput
from rich.cells import get_character_cell_size
from rich.console import Console
from rich.style import Style
from rich.text import Text

from anishift.application import RunEventKind, TaskKind, TaskState
from anishift.cli.interactive.app import _auto_content, _fit_frame, _home_content, _QueueView
from anishift.cli.interactive.mascot import MascotState
from anishift.cli.interactive.palette import BRAND_THEME
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.interactive.prompts import TerminalRenderer
from anishift.cli.interactive.settings import SettingsController
from anishift.utils.rich_console.theme import RICH_THEME
from tests.cli.test_interactive_progress import _event, _prepared
from tests.cli.test_interactive_settings_models import _service


def snapshot(name: str, content: Text, columns: int, rows: int) -> None:
    """Draw actual Rich segments with Consolas into a static text-fallback preview."""
    console = Console(file=StringIO(), width=columns, height=rows, theme=RICH_THEME, record=True, legacy_windows=False)
    console.push_theme(BRAND_THEME)
    frame: Text = _fit_frame(content, "0.1.0", "workspace", columns, rows)
    font = ImageFont.truetype("consola.ttf", 18)
    bold = ImageFont.truetype("consolab.ttf", 18)
    symbols = ImageFont.truetype("seguisym.ttf", 18)
    cell: int = round(font.getlength("M"))
    row_height: int = 24
    canvas = Image.new("RGB", (columns * cell + 32, rows * row_height + 32), "#0c0f18")
    drawing = ImageDraw.Draw(canvas)
    for row, segments in enumerate(console.render_lines(frame, console.options, pad=True)):
        column: int = 0
        for segment in segments:
            style: Style = segment.style or Style()
            foreground: str = (
                style.color.get_truecolor().hex if style.color and not style.color.is_default else "#d7dceb"
            )
            background: str | None = (
                style.bgcolor.get_truecolor().hex if style.bgcolor and not style.bgcolor.is_default else None
            )
            for glyph in segment.text:
                x: int = 16 + column * cell
                y: int = 16 + row * row_height
                width: int = get_character_cell_size(glyph)
                if background:
                    drawing.rectangle((x, y, x + width * cell, y + row_height), fill=background)
                chosen_font = symbols if glyph in "\u276f✓↔↑↓" else bold if style.bold else font
                drawing.text((x, y), glyph, font=chosen_font, fill=foreground)
                column += width
    canvas.save(Path(__file__).with_name(f"terminal-{name}.png"))


def queue() -> RichRunProgress:
    """Build a run from the existing offline event fixtures."""
    names: tuple[str, ...] = (
        "Violet Evergarden - 01 - The Letter That Changed Everything [1080p]",
        "Violet Evergarden - 02 - Never Coming Back [1080p]",
        "Violet Evergarden - 03 - May You Be an Exemplary Auto Memory Doll",
        "Violet Evergarden - 04 - A Letter Waiting in the Quiet Garden",
    )
    prepared = _prepared(
        tuple((f"group-{index}", name) for index, name in enumerate(names)),
        tuple((f"task-{index}", f"group-{index}", TaskKind.TRANSLATE_SUBTITLES) for index in range(len(names))),
    )
    progress = RichRunProgress(prepared, lambda: None)
    progress.__enter__()
    progress.emit(_event(1, RunEventKind.GROUP_FINISHED, group_id="group-0", state=TaskState.SUCCEEDED))
    progress.emit(_event(2, RunEventKind.TASK_STARTED, group_id="group-1", task_id="task-1"))
    progress.emit(_event(3, RunEventKind.TASK_PROGRESS, group_id="group-1", task_id="task-1", progress_percent=62))
    progress.emit(_event(4, RunEventKind.TASK_STARTED, group_id="group-2", task_id="task-2"))
    return progress


def measure(progress: RichRunProgress) -> None:
    """Measure cold and warm full frame conversion, excluding terminal transport."""
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        renderer = TerminalRenderer(lambda _columns, _rows: Text(), lambda _key: None)
    for columns, rows in ((120, 40), (80, 24), (50, 20)):
        view = _QueueView()
        elapsed: list[float] = []
        for index in range(120):
            start: float = perf_counter()
            content = _auto_content((columns, rows), progress, MascotState.TRANSLATE, view, animation_phase=index % 24)
            frame = _fit_frame(content, "0.1.0", "workspace", columns, rows)
            console, stream = renderer._render_target(columns)
            stream.seek(0)
            stream.truncate(0)
            console.print(frame, end="", soft_wrap=True)
            elapsed.append((perf_counter() - start) * 1000)
        warm: list[float] = sorted(elapsed[24:])
        Console().print(
            f"{columns}x{rows}: cold max={max(elapsed[:24]):.2f} ms, "
            f"warm median={median(warm):.2f} ms, p95={warm[int(len(warm) * 0.95)]:.2f} ms"
        )


def main() -> None:
    """Save representative Home, Auto and Settings frames from isolated fixtures."""
    progress = queue()
    snapshot("home", _home_content(100, 28, 0, MascotState.IDLE), 100, 28)
    snapshot("auto", _auto_content((120, 24), progress, MascotState.TRANSLATE, _QueueView()), 120, 24)
    snapshot(
        "narrow", _auto_content((50, 20), progress, MascotState.TRANSLATE, _QueueView(), animation_phase=19), 50, 20
    )
    with TemporaryDirectory(prefix="anishift-ui-preview-") as temporary:
        panel = SettingsController(_service(Path(temporary), []), lambda: None)
        snapshot("settings", panel.render(80, 24), 80, 24)
        panel._open_model_editor()
        snapshot("models", panel.render(80, 24), 80, 24)
    measure(progress)


if __name__ == "__main__":
    main()

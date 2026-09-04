from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from rich.text import Text

from anishift.cli.interactive import home
from anishift.cli.interactive.palette import (
    BRAND_THEME,
    MASCOT_AZURE,
    MASCOT_RED,
    MASCOT_VIOLET,
    hex_color,
    mix,
    rim_color,
)
from anishift.utils.rich_console.theme import RICH_THEME

_AZURE_ANSI = "38;2;0;98;250"


def _views() -> tuple[Path, ...]:
    package = Path(home.__file__).parent
    return tuple(sorted(package.glob("*.py")))


def _rendered(style: str) -> str:
    stream = StringIO()
    console = Console(
        file=stream,
        theme=RICH_THEME,
        width=20,
        color_system="truecolor",
        force_terminal=True,
        legacy_windows=False,
        highlight=False,
    )
    console.push_theme(BRAND_THEME)
    console.print(Text("x", style=style), end="", soft_wrap=True)
    return stream.getvalue()


def test_the_palette_carries_the_three_colors_measured_on_the_mascot() -> None:
    assert (hex_color(MASCOT_AZURE), hex_color(MASCOT_VIOLET), hex_color(MASCOT_RED)) == (
        "#0062fa",
        "#4c03d9",
        "#f9011a",
    )


@pytest.mark.parametrize(
    ("position", "expected"),
    [(0.0, MASCOT_AZURE), (0.5, MASCOT_VIOLET), (1.0, MASCOT_RED)],
)
def test_the_gradient_passes_through_every_brand_color(position: float, expected: tuple[int, int, int]) -> None:
    assert rim_color(position) == expected


@pytest.mark.parametrize("position", [-1.0, 2.0])
def test_the_gradient_clamps_a_position_outside_the_wordmark(position: float) -> None:
    assert rim_color(position) in {MASCOT_AZURE, MASCOT_RED}


def test_the_gradient_leaves_the_brand_colors_between_the_anchors() -> None:
    assert rim_color(0.25) not in {MASCOT_AZURE, MASCOT_VIOLET, MASCOT_RED}


def test_mixing_by_the_edge_weights_returns_the_endpoints() -> None:
    assert (mix(MASCOT_AZURE, MASCOT_RED, 0.0), mix(MASCOT_AZURE, MASCOT_RED, 1.0)) == (MASCOT_AZURE, MASCOT_RED)


def test_the_accent_style_preserves_the_original_mascot_azure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert _AZURE_ANSI in _rendered("brand_accent")


def test_the_accent_style_respects_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert _AZURE_ANSI not in _rendered("brand_accent")


def test_the_shared_theme_alone_cannot_paint_the_brand_accent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert _AZURE_ANSI not in _rendered("purple_bold")


def test_no_interactive_view_still_uses_the_generic_accent() -> None:
    offenders = tuple(path.name for path in _views() if "purple" in path.read_text(encoding="utf-8"))
    assert offenders == ()


def test_the_wordmark_keeps_no_second_copy_of_the_brand_colors() -> None:
    source = Path(home.__file__).read_text(encoding="utf-8")
    assert "palette import" in source
    assert hex(MASCOT_AZURE[1]) not in source


def test_the_wordmark_starts_azure_and_ends_red() -> None:
    wordmark = home._full_wordmark()
    styles = tuple(str(span.style) for span in wordmark.spans)
    assert styles[0] == hex_color(MASCOT_AZURE)
    assert styles[-1] == hex_color(rim_color(1.0))

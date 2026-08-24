from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from textual.app import App
from textual.css.stylesheet import Stylesheet
from textual.theme import Theme

import anishift.tui
from anishift.tui.theme import (
    DARK_PALETTE,
    DARK_THEME_ID,
    DEFAULT_THEME_ID,
    LIGHT_PALETTE,
    LIGHT_THEME_ID,
    THEME_IDS,
    Palette,
    anishift_themes,
    register_themes,
)

_COLOR_LITERAL: Final[re.Pattern[str]] = re.compile(
    r"#(?:[0-9A-Fa-f]{8}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3,4})\b|\bColor\s*\(",
)

_STYLED_SUFFIXES: Final[frozenset[str]] = frozenset((".py", ".tcss"))


def test_theme_ids_are_exactly_the_two_stable_ids() -> None:
    assert DARK_THEME_ID == "anishift-dark"
    assert LIGHT_THEME_ID == "anishift-light"
    assert THEME_IDS == ("anishift-dark", "anishift-light")
    assert DEFAULT_THEME_ID == DARK_THEME_ID


def test_exactly_two_themes_are_built_in_id_order() -> None:
    themes: tuple[Theme, Theme] = anishift_themes()
    assert tuple(theme.name for theme in themes) == THEME_IDS
    assert (themes[0].dark, themes[1].dark) == (True, False)


def test_dark_palette_matches_the_visual_grammar() -> None:
    assert (
        Palette(
            background="#0B0D10",
            surface="#11141A",
            elevated="#171B22",
            border="#2A303B",
            focus="#7AA2F7",
            text="#E6E9EF",
            muted="#8B93A5",
            accent_soft="#283457",
            success="#9ECE6A",
            warning="#E0AF68",
            error="#F7768E",
            info="#7DCFFF",
        )
        == DARK_PALETTE
    )


def test_light_palette_matches_the_visual_grammar() -> None:
    assert (
        Palette(
            background="#F5F7FA",
            surface="#FFFFFF",
            elevated="#EEF1F5",
            border="#CDD3DD",
            focus="#3B6EDC",
            text="#1F2430",
            muted="#667085",
            accent_soft="#DCE7FF",
            success="#2F7D32",
            warning="#9A6700",
            error="#C6283D",
            info="#1F6FA8",
        )
        == LIGHT_PALETTE
    )


def test_every_palette_token_is_reachable_from_tcss() -> None:
    for theme, palette in zip(anishift_themes(), (DARK_PALETTE, LIGHT_PALETTE), strict=True):
        assert theme.background == palette.background
        assert theme.surface == palette.surface
        assert theme.panel == palette.elevated
        assert theme.foreground == palette.text
        assert theme.primary == palette.focus
        assert theme.success == palette.success
        assert theme.warning == palette.warning
        assert theme.error == palette.error
        assert theme.variables["border"] == palette.border
        assert theme.variables["border-blurred"] == palette.border
        assert theme.variables["elevated"] == palette.elevated
        assert theme.variables["focus"] == palette.focus
        assert theme.variables["info"] == palette.info
        assert theme.variables["text"] == palette.text
        assert theme.variables["text-muted"] == palette.muted
        assert theme.variables["accent-soft"] == palette.accent_soft


def test_register_themes_registers_both_ids() -> None:
    app: App[None] = App()
    register_themes(app)
    registered: list[Theme] = []
    for theme_id in THEME_IDS:
        theme = app.get_theme(theme_id)
        assert theme is not None
        registered.append(theme)
    assert [theme.name for theme in registered] == list(THEME_IDS)


def test_theme_module_is_the_only_owner_of_colour_literals() -> None:
    root: Path = Path(anishift.tui.__file__).parent
    offenders: list[str] = [
        str(path.relative_to(root))
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.suffix in _STYLED_SUFFIXES
        and path.name != "theme.py"
        and _COLOR_LITERAL.search(path.read_text(encoding="utf-8")) is not None
    ]
    assert offenders == []


def test_style_sheets_resolve_every_variable_from_both_themes() -> None:
    styles: list[Path] = sorted((Path(anishift.tui.__file__).parent / "styles").glob("*.tcss"))
    assert [path.name for path in styles] == ["base.tcss", "screens.tcss"]
    for theme in anishift_themes():
        stylesheet = Stylesheet(
            variables={**theme.to_color_system().generate(), **theme.variables},
        )
        for path in styles:
            stylesheet.read(path)
        stylesheet.parse()
        assert stylesheet.rules


def test_theme_module_actually_contains_colour_literals() -> None:
    theme_source: Path = Path(anishift.tui.__file__).with_name("theme.py")
    assert _COLOR_LITERAL.search(theme_source.read_text(encoding="utf-8")) is not None

from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Final

import pytest
from textual.app import App
from textual.color import Color, ColorParseError
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
    on_primary,
    register_themes,
)

_STYLED_SUFFIXES: Final[frozenset[str]] = frozenset((".py", ".tcss"))

_COLOUR_TOKEN: Final[re.Pattern[str]] = re.compile(
    r"#[0-9A-Fa-f]+|(?:rgba?|hsla?)\([^)]*\)|[A-Za-z][A-Za-z0-9_]*",
)

_TCSS_COMMENT: Final[re.Pattern[str]] = re.compile(r"/\*.*?\*/", re.DOTALL)

_TCSS_DECLARATION_VALUE: Final[re.Pattern[str]] = re.compile(r":\s*([^;{}]*)")

_TCSS_VARIABLE_REFERENCE: Final[re.Pattern[str]] = re.compile(r"\$[\w-]+")

_COLOUR_CONSTRUCTOR_NAME: Final[str] = "Color"

_COLOUR_CONSTRUCTOR_ORIGIN: Final[str] = "textual.color.Color"

_RUNTIME_COMPOSED_COLOURS_ARE_OUTSIDE_STATIC_REACH: Final[str] = (
    "colours composed while the program runs are an accepted blind spot of this static guard: "
    "no static analysis can resolve a value produced at runtime, so the guard owns literals and "
    "constructor calls only and deliberately does not guess about computed strings"
)

_COLOUR_CONSTRUCTOR_IMPORT_FORMS: Final[tuple[str, ...]] = (
    "from textual.color import Color\nACCENT = Color(1, 2, 3)\n",
    "from textual.color import Color as C\nACCENT = C(1, 2, 3)\n",
    "from textual import color\nACCENT = color.Color(1, 2, 3)\n",
    "from textual import color as clr\nACCENT = clr.Color(1, 2, 3)\n",
    "import textual.color\nACCENT = textual.color.Color(1, 2, 3)\n",
    "import textual.color as tc\nACCENT = tc.Color(1, 2, 3)\n",
)

_RUNTIME_COMPOSED_COLOUR_FORMS: Final[tuple[str, ...]] = (
    'ACCENT = f"#{red_hex}{green_hex}{blue_hex}"',
    'ACCENT = "#" + computed_hex',
    "ACCENT = build_colour(11, 13, 16)",
)

_COLOUR_FORMS: Final[tuple[tuple[str, str], ...]] = (
    (".tcss", "Widget { color: #f00; }"),
    (".tcss", "Widget { color: #f00f; }"),
    (".tcss", "Widget { color: #ff0000; }"),
    (".tcss", "Widget { color: #ff0000ff; }"),
    (".tcss", "Widget { color: red; }"),
    (".tcss", "Widget { color: rgb(1, 2, 3); }"),
    (".tcss", "Widget { color: rgba(1, 2, 3, 0.5); }"),
    (".tcss", "Widget { color: hsl(1, 2%, 3%); }"),
    (".tcss", "Widget { color: hsla(1, 2%, 3%, 0.5); }"),
    (".tcss", "Widget { color: ansi_red; }"),
    (".py", 'ACCENT = "#ff0000"'),
    (".py", 'ACCENT = "ansi_red"'),
    (".py", 'ACCENT = Color("red")'),
)

_NON_COLOUR_TOKENS: Final[tuple[str, ...]] = (
    "panel",
    "round",
    "solid",
    "hidden",
    "auto",
    "none",
    "block",
    "focus",
    "border",
    "surface",
    "background",
    "elevated",
    "success",
    "warning",
    "error",
    "info",
    "muted",
    "accent",
    "compact",
    "app-brand",
    "text-muted",
)


def _token_is_a_colour(token: str) -> bool:
    try:
        Color.parse(token)
    except ColorParseError:
        return False
    return True


def _tcss_declaration_values(source: str) -> list[str]:
    body: str = _TCSS_COMMENT.sub(" ", source)
    return [_TCSS_VARIABLE_REFERENCE.sub(" ", match.group(1)) for match in _TCSS_DECLARATION_VALUE.finditer(body)]


def _python_string_literals(source: str) -> list[str]:
    tree: ast.Module = ast.parse(source)
    return [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def _name_bindings(tree: ast.Module) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name.partition(".")[0]] = (
                    alias.name if alias.asname else alias.name.partition(".")[0]
                )
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.ClassDef):
            bindings[node.name] = node.name
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bindings[target.id] = node.value.id
    return bindings


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix: str | None = _dotted_name(node.value)
        return None if prefix is None else f"{prefix}.{node.attr}"
    return None


def _resolved_origin(dotted: str, bindings: Mapping[str, str]) -> str | None:
    root: str
    rest: str
    root, _, rest = dotted.partition(".")
    if root not in bindings:
        return None
    seen: set[str] = {root}
    origin: str = bindings[root]
    while origin in bindings and origin not in seen:
        seen.add(origin)
        origin = bindings[origin]
    return f"{origin}.{rest}" if rest else origin


def _colour_constructor_calls(source: str) -> list[str]:
    tree: ast.Module = ast.parse(source)
    bindings: Mapping[str, str] = _name_bindings(tree)
    calls: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted: str | None = _dotted_name(node.func)
        if dotted is None:
            continue
        origin: str | None = _resolved_origin(dotted, bindings)
        if origin == _COLOUR_CONSTRUCTOR_ORIGIN or (
            origin is None and dotted.rpartition(".")[2] == _COLOUR_CONSTRUCTOR_NAME
        ):
            calls.append(f"{dotted}(")
    return calls


def _colour_literals(source: str, *, suffix: str) -> list[str]:
    scopes: list[str] = _tcss_declaration_values(source) if suffix == ".tcss" else _python_string_literals(source)
    literals: list[str] = [
        token for scope in scopes for token in _COLOUR_TOKEN.findall(scope) if _token_is_a_colour(token)
    ]
    if suffix != ".tcss":
        literals.extend(_colour_constructor_calls(source))
    return literals


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
            primary="#fab283",
            secondary="#5c9cf5",
            accent="#9d7cd8",
            error="#e06c75",
            warning="#f5a742",
            success="#7fd88f",
            info="#56b6c2",
            text="#eeeeee",
            text_muted="#808080",
            background="#0a0a0a",
            background_panel="#141414",
            background_element="#1e1e1e",
            border="#484848",
            border_active="#606060",
            border_subtle="#3c3c3c",
        )
        == DARK_PALETTE
    )


def test_light_palette_matches_the_visual_grammar() -> None:
    assert (
        Palette(
            primary="#3b7dd8",
            secondary="#7b5bb6",
            accent="#d68c27",
            error="#d1383d",
            warning="#d68c27",
            success="#3d9a57",
            info="#318795",
            text="#1a1a1a",
            text_muted="#8a8a8a",
            background="#ffffff",
            background_panel="#fafafa",
            background_element="#f5f5f5",
            border="#b8b8b8",
            border_active="#a0a0a0",
            border_subtle="#d4d4d4",
        )
        == LIGHT_PALETTE
    )


def test_the_neutral_scale_carries_exactly_one_accent_hue() -> None:
    for palette in (DARK_PALETTE, LIGHT_PALETTE):
        neutrals: tuple[str, ...] = (
            palette.text,
            palette.text_muted,
            palette.background,
            palette.background_panel,
            palette.background_element,
            palette.border,
            palette.border_active,
            palette.border_subtle,
        )
        for colour in neutrals:
            digits: str = colour.lstrip("#")
            assert digits[0:2] == digits[2:4] == digits[4:6]


def test_every_palette_token_is_reachable_from_tcss() -> None:
    for theme, palette in zip(anishift_themes(), (DARK_PALETTE, LIGHT_PALETTE), strict=True):
        assert theme.background == palette.background
        assert theme.surface == palette.background_panel
        assert theme.panel == palette.background_element
        assert theme.foreground == palette.text
        assert theme.primary == palette.primary
        assert theme.secondary == palette.secondary
        assert theme.accent == palette.accent
        assert theme.success == palette.success
        assert theme.warning == palette.warning
        assert theme.error == palette.error
        for field in fields(palette):
            assert theme.variables[field.name.replace("_", "-")] == getattr(palette, field.name)
        assert theme.variables["border-blurred"] == palette.border
        assert theme.variables["on-primary"] == on_primary(palette)


def test_selection_text_is_black_on_the_bright_dark_accent() -> None:
    assert on_primary(DARK_PALETTE) == "#000000"


def test_selection_text_is_white_on_the_deep_light_accent() -> None:
    assert on_primary(LIGHT_PALETTE) == "#ffffff"


def test_register_themes_registers_both_ids() -> None:
    app: App[None] = App()
    register_themes(app)
    registered: list[Theme] = []
    for theme_id in THEME_IDS:
        theme: Theme | None = app.get_theme(theme_id)
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
        and _colour_literals(path.read_text(encoding="utf-8"), suffix=path.suffix)
    ]
    assert offenders == []


@pytest.mark.parametrize(("suffix", "source"), _COLOUR_FORMS)
def test_colour_guard_flags_every_colour_form(suffix: str, source: str) -> None:
    assert _colour_literals(source, suffix=suffix)


@pytest.mark.parametrize("source", _COLOUR_CONSTRUCTOR_IMPORT_FORMS)
def test_colour_guard_flags_the_constructor_under_every_import_alias(source: str) -> None:
    assert _colour_literals(source, suffix=".py")


def test_colour_guard_ignores_a_color_class_imported_from_another_module() -> None:
    assert _colour_literals("from anishift.tui.brand import Color\nACCENT = Color(1, 2, 3)\n", suffix=".py") == []


def test_colour_guard_ignores_a_color_class_defined_in_the_same_module() -> None:
    assert _colour_literals("class Color:\n    pass\n\n\nACCENT = Color(1, 2, 3)\n", suffix=".py") == []


def test_colour_guard_flags_the_constructor_behind_an_assignment_alias() -> None:
    assert _colour_literals("from textual.color import Color\nAlias = Color\nACCENT = Alias(1, 2, 3)\n", suffix=".py")


@pytest.mark.parametrize("source", _RUNTIME_COMPOSED_COLOUR_FORMS)
def test_runtime_composed_colours_are_an_accepted_blind_spot(source: str) -> None:
    assert _colour_literals(source, suffix=".py") == [], _RUNTIME_COMPOSED_COLOURS_ARE_OUTSIDE_STATIC_REACH


@pytest.mark.parametrize("token", _NON_COLOUR_TOKENS)
def test_colour_guard_ignores_tokens_that_are_not_colours(token: str) -> None:
    assert not _token_is_a_colour(token)


def test_style_sheets_resolve_every_variable_from_both_themes() -> None:
    styles: list[Path] = sorted((Path(anishift.tui.__file__).parent / "styles").glob("*.tcss"))
    assert [path.name for path in styles] == ["base.tcss", "dialogs.tcss", "screens.tcss"]
    for theme in anishift_themes():
        stylesheet: Stylesheet = Stylesheet(
            variables={**theme.to_color_system().generate(), **theme.variables},
        )
        for path in styles:
            stylesheet.read(path)
        stylesheet.parse()
        assert stylesheet.rules


def test_theme_module_actually_contains_colour_literals() -> None:
    theme_source: Path = Path(anishift.tui.__file__).with_name("theme.py")
    assert _colour_literals(theme_source.read_text(encoding="utf-8"), suffix=".py")

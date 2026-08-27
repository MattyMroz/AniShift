from __future__ import annotations

import ast
import asyncio
import re
from collections.abc import Coroutine, Mapping
from dataclasses import fields
from pathlib import Path
from typing import Any, Final

import pytest
from textual.app import App
from textual.color import Color, ColorParseError
from textual.css.stylesheet import Stylesheet
from textual.theme import Theme
from tui_fakes import shell

import anishift.tui
from anishift.tui import ui_state
from anishift.tui.app import AniShiftApp
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
from anishift.tui.ui_state import UiState, save_ui_state
from anishift.tui.widgets.composer import BOX_ID, HINT_ID

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

_SPEC_TOKEN_NAMES: Final[frozenset[str]] = frozenset(
    (
        "primary",
        "secondary",
        "accent",
        "error",
        "warning",
        "success",
        "info",
        "text",
        "text_muted",
        "background",
        "background_panel",
        "background_element",
        "border",
        "border_active",
        "border_subtle",
    ),
)

_SPEC_TOKEN_COUNT: Final[int] = 15

_HEX_COLOUR: Final[re.Pattern[str]] = re.compile(r"\A#[0-9a-f]{6}\Z")

_SEMANTIC_TOKEN_NAMES: Final[tuple[str, ...]] = ("error", "warning", "success", "info")

_SEMANTIC_VARIABLE: Final[re.Pattern[str]] = re.compile(r"\$(?:error|warning|success|info)\b")

_TCSS_DECLARATION: Final[re.Pattern[str]] = re.compile(r"([\w-]+)\s*:\s*([^;{}]*);")

_STATE_ONLY_PROPERTY: Final[str] = "color"

_SELECTION_AND_FOCUS_VARIABLES: Final[tuple[str, ...]] = (
    "primary",
    "on-primary",
    "block-cursor-background",
    "block-cursor-foreground",
    "block-hover-background",
    "input-cursor-background",
    "input-selection-background",
    "border",
    "border-active",
    "border-blurred",
    "border-subtle",
)

_CHANNEL_MAX: Final[float] = 255.0

_SRGB_KNEE: Final[float] = 0.04045

_SRGB_LOW_SLOPE: Final[float] = 12.92

_SRGB_OFFSET: Final[float] = 0.055

_SRGB_EXPONENT: Final[float] = 2.4

_WCAG_WEIGHTS: Final[tuple[float, float, float]] = (0.2126, 0.7152, 0.0722)

_CONTRAST_OFFSET: Final[float] = 0.05

_AA_BODY_TEXT_RATIO: Final[float] = 4.5

_AA_LARGE_TEXT_RATIO: Final[float] = 3.0

_WCAG_MAX_RATIO: Final[float] = 21.0

_WCAG_MIN_RATIO: Final[float] = 1.0

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_SETTLE_PAUSES: Final[int] = 5


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


def _token_values(palette: Palette) -> dict[str, str]:
    return {field.name: getattr(palette, field.name) for field in fields(palette)}


def _surfaces(palette: Palette) -> tuple[str, str, str]:
    return (palette.background, palette.background_panel, palette.background_element)


def _semantic_values(palette: Palette) -> frozenset[str]:
    return frozenset(getattr(palette, name) for name in _SEMANTIC_TOKEN_NAMES)


def _relative_luminance(colour: str) -> float:
    digits: str = colour.lstrip("#")
    channels: list[float] = [int(digits[start : start + 2], 16) / _CHANNEL_MAX for start in (0, 2, 4)]
    linear: list[float] = [
        channel / _SRGB_LOW_SLOPE
        if channel <= _SRGB_KNEE
        else ((channel + _SRGB_OFFSET) / (1.0 + _SRGB_OFFSET)) ** _SRGB_EXPONENT
        for channel in channels
    ]
    return sum(weight * value for weight, value in zip(_WCAG_WEIGHTS, linear, strict=True))


def _contrast_ratio(one: str, other: str) -> float:
    first: float = _relative_luminance(one)
    second: float = _relative_luminance(other)
    return (max(first, second) + _CONTRAST_OFFSET) / (min(first, second) + _CONTRAST_OFFSET)


def _resolved_variables(theme: Theme) -> dict[str, str]:
    return {**theme.to_color_system().generate(), **theme.variables}


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)


@pytest.fixture
def state_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target: Path = tmp_path / "ui_state.json"
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: target)
    return target


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


def test_both_variants_define_the_same_fifteen_tokens_with_none_missing_and_none_extra() -> None:
    dark: dict[str, str] = _token_values(DARK_PALETTE)
    light: dict[str, str] = _token_values(LIGHT_PALETTE)
    assert frozenset(dark) == frozenset(light) == _SPEC_TOKEN_NAMES
    assert len(dark) == len(light) == _SPEC_TOKEN_COUNT


def test_neither_variant_exposes_a_tcss_variable_the_other_one_lacks() -> None:
    dark: Theme
    light: Theme
    dark, light = anishift_themes()
    assert set(dark.variables) == set(light.variables)
    assert {name.replace("-", "_") for name in dark.variables} >= _SPEC_TOKEN_NAMES


def test_every_token_of_both_variants_is_a_six_digit_lowercase_hex_colour() -> None:
    for palette in (DARK_PALETTE, LIGHT_PALETTE):
        for value in _token_values(palette).values():
            assert _HEX_COLOUR.match(value)


def test_the_contrast_helper_reproduces_the_wcag_reference_extremes() -> None:
    assert _contrast_ratio("#000000", "#ffffff") == pytest.approx(_WCAG_MAX_RATIO)
    assert _contrast_ratio("#ffffff", "#ffffff") == pytest.approx(_WCAG_MIN_RATIO)
    assert _contrast_ratio("#000000", "#ffffff") == _contrast_ratio("#ffffff", "#000000")


def test_primary_text_clears_the_wcag_aa_body_ratio_over_every_surface_of_both_variants() -> None:
    for palette in (DARK_PALETTE, LIGHT_PALETTE):
        for surface in _surfaces(palette):
            assert _contrast_ratio(palette.text, surface) >= _AA_BODY_TEXT_RATIO


def test_muted_text_clears_the_wcag_aa_large_text_ratio_over_every_surface_of_both_variants() -> None:
    for palette in (DARK_PALETTE, LIGHT_PALETTE):
        for surface in _surfaces(palette):
            assert _contrast_ratio(palette.text_muted, surface) >= _AA_LARGE_TEXT_RATIO


def test_muted_text_stays_fainter_than_primary_text_over_every_surface_of_both_variants() -> None:
    for palette in (DARK_PALETTE, LIGHT_PALETTE):
        for surface in _surfaces(palette):
            assert _contrast_ratio(palette.text_muted, surface) < _contrast_ratio(palette.text, surface)


def test_selection_text_clears_the_wcag_aa_large_text_ratio_over_the_single_accent() -> None:
    for palette in (DARK_PALETTE, LIGHT_PALETTE):
        assert _contrast_ratio(on_primary(palette), palette.primary) >= _AA_LARGE_TEXT_RATIO


def test_no_semantic_colour_is_the_single_accent_of_either_variant() -> None:
    for palette in (DARK_PALETTE, LIGHT_PALETTE):
        assert palette.primary not in _semantic_values(palette)


def test_no_selection_or_focus_variable_of_either_variant_resolves_to_a_semantic_colour() -> None:
    for theme, palette in zip(anishift_themes(), (DARK_PALETTE, LIGHT_PALETTE), strict=True):
        resolved: dict[str, str] = _resolved_variables(theme)
        semantic: frozenset[Color] = frozenset(Color.parse(value) for value in _semantic_values(palette))
        for name in _SELECTION_AND_FOCUS_VARIABLES:
            assert Color.parse(resolved[name]) not in semantic


def test_the_style_sheets_reference_semantic_colours_only_as_text_colour() -> None:
    styles: list[Path] = sorted((Path(anishift.tui.__file__).parent / "styles").glob("*.tcss"))
    properties: list[str] = [
        match.group(1)
        for path in styles
        for match in _TCSS_DECLARATION.finditer(_TCSS_COMMENT.sub(" ", path.read_text(encoding="utf-8")))
        if _SEMANTIC_VARIABLE.search(match.group(2))
    ]
    assert properties
    assert set(properties) == {_STATE_ONLY_PROPERTY}


def test_a_stored_light_variant_opens_the_next_shell_on_the_light_variant(state_file: Path) -> None:
    save_ui_state(UiState(theme=LIGHT_THEME_ID))
    app: AniShiftApp = shell()
    assert app.theme == LIGHT_THEME_ID
    assert sorted(path.name for path in state_file.parent.iterdir()) == [state_file.name]


@pytest.mark.usefixtures("state_file")
def test_switching_to_the_light_variant_repaints_the_running_shell_without_a_restart() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.theme == DARK_THEME_ID
            assert app.screen.styles.background == Color.parse(DARK_PALETTE.background)
            app.theme = LIGHT_THEME_ID
            for _ in range(_SETTLE_PAUSES):
                await pilot.pause()
            assert app.is_running
            assert app.screen.styles.background == Color.parse(LIGHT_PALETTE.background)
            assert app.query_one(f"#{BOX_ID}").styles.background == Color.parse(LIGHT_PALETTE.background_element)
            assert app.query_one(f"#{HINT_ID}").styles.color == Color.parse(LIGHT_PALETTE.text_muted)

    _run(scenario())


@pytest.mark.usefixtures("state_file")
def test_a_runtime_switch_alone_does_not_persist_the_light_variant(state_file: Path) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.theme = LIGHT_THEME_ID
            for _ in range(_SETTLE_PAUSES):
                await pilot.pause()
            assert not state_file.exists()

    _run(scenario())

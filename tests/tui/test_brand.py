from __future__ import annotations

import unicodedata
from typing import Final

from rich.cells import cell_len
from textual.content import Content

from anishift.tui.brand import (
    BRAND_ACCENT_STYLE,
    BRAND_MUTED_STYLE,
    COMPACT_LOGO_MIN_HEIGHT,
    COMPACT_LOGO_MIN_WIDTH,
    FULL_LOGO_MIN_HEIGHT,
    FULL_LOGO_MIN_WIDTH,
    LOGO_ROWS,
    LOGO_WIDTH,
    WORDMARK,
    compact_logo,
    full_logo,
    full_logo_lines,
    logo_for_size,
    logo_variant,
)
from anishift.tui.theme import anishift_themes

_ALLOWED_LOGO_CHARACTERS: Final[frozenset[str]] = frozenset(" \u2588\u2550\u2551\u2554\u2557\u255a\u255d")


def test_full_logo_has_exactly_six_rows() -> None:
    assert LOGO_ROWS == 6
    assert len(full_logo_lines()) == LOGO_ROWS


def test_the_full_logo_is_the_width_the_specification_pins() -> None:
    assert LOGO_WIDTH == 57


def test_every_full_logo_row_has_the_same_cell_width() -> None:
    assert {cell_len(line) for line in full_logo_lines()} == {LOGO_WIDTH}
    assert {len(line) for line in full_logo_lines()} == {LOGO_WIDTH}


def test_logo_never_changes_width_between_calls() -> None:
    assert full_logo_lines() == full_logo_lines()
    assert full_logo().plain == full_logo().plain


def test_logo_uses_only_predictable_single_cell_characters() -> None:
    characters: set[str] = set("".join(full_logo_lines()))
    assert characters <= _ALLOWED_LOGO_CHARACTERS
    for character in characters:
        assert cell_len(character) == 1
        assert unicodedata.east_asian_width(character) in {"N", "Na", "A"}


def test_full_logo_splits_the_muted_half_from_the_accented_half() -> None:
    content: Content = full_logo()
    assert content.plain == "\n".join(full_logo_lines())
    assert {span.style for span in content.spans} == {BRAND_MUTED_STYLE, BRAND_ACCENT_STYLE}
    assert len(content.spans) == 2 * LOGO_ROWS


def test_compact_logo_is_a_single_row_wordmark() -> None:
    content: Content = compact_logo()
    assert content.plain == WORDMARK == "ANISHIFT"
    assert "\n" not in content.plain
    assert [span.style for span in content.spans] == [BRAND_MUTED_STYLE, BRAND_ACCENT_STYLE]
    assert content.plain[: content.spans[0].end] == "ANI"
    assert content.plain[content.spans[1].start :] == "SHIFT"


def test_brand_styles_resolve_against_both_themes() -> None:
    for theme in anishift_themes():
        for style in (BRAND_MUTED_STYLE, BRAND_ACCENT_STYLE):
            assert style.startswith("$")
            assert style.removeprefix("$") in theme.variables


def test_full_variant_applies_from_the_full_layout_size() -> None:
    assert (FULL_LOGO_MIN_WIDTH, FULL_LOGO_MIN_HEIGHT) == (100, 30)
    assert logo_variant(width=100, height=30) == "full"
    assert logo_variant(width=200, height=60) == "full"


def test_compact_variant_applies_below_the_full_layout_size() -> None:
    assert logo_variant(width=99, height=30) == "compact"
    assert logo_variant(width=100, height=29) == "compact"
    assert logo_variant(width=80, height=24) == "compact"


def test_controls_win_over_the_logo_below_the_compact_thresholds() -> None:
    assert logo_variant(width=COMPACT_LOGO_MIN_WIDTH - 1, height=24) == "hidden"
    assert logo_variant(width=80, height=COMPACT_LOGO_MIN_HEIGHT - 1) == "hidden"
    assert logo_variant(width=20, height=6) == "hidden"


def test_logo_for_size_matches_the_selected_variant() -> None:
    large: Content | None = logo_for_size(width=120, height=40)
    small: Content | None = logo_for_size(width=80, height=24)
    assert large is not None
    assert small is not None
    assert large.plain == full_logo().plain
    assert small.plain == WORDMARK
    assert logo_for_size(width=20, height=6) is None

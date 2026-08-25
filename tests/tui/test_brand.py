from __future__ import annotations

import unicodedata
from typing import Final

from rich.cells import cell_len
from textual.content import Content

from anishift.tui.brand import (
    BRAND_ACCENT_STYLE,
    BRAND_MUTED_STYLE,
    LOGO_MIN_HEIGHT,
    LOGO_MIN_WIDTH,
    LOGO_ROWS,
    LOGO_WIDTH,
    WORDMARK,
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


def test_brand_styles_resolve_against_both_themes() -> None:
    for theme in anishift_themes():
        for style in (BRAND_MUTED_STYLE, BRAND_ACCENT_STYLE):
            assert style.startswith("$")
            assert style.removeprefix("$") in theme.variables


def test_the_wordmark_names_the_product() -> None:
    assert WORDMARK == "ANISHIFT"


def test_the_wordmark_leaves_whole_rather_than_wrap_in_a_narrow_terminal() -> None:
    assert LOGO_MIN_WIDTH == LOGO_WIDTH
    assert logo_variant(width=LOGO_MIN_WIDTH, height=LOGO_MIN_HEIGHT) == "full"
    for width in (LOGO_MIN_WIDTH - 1, 40, 20):
        assert logo_variant(width=width, height=LOGO_MIN_HEIGHT) == "hidden"


def test_a_short_terminal_gives_the_rows_back_to_the_controls() -> None:
    assert logo_variant(width=100, height=LOGO_MIN_HEIGHT) == "full"
    assert logo_variant(width=100, height=LOGO_MIN_HEIGHT - 1) == "hidden"


def test_the_wordmark_renders_at_one_size_whenever_it_renders_at_all() -> None:
    wide: Content | None = logo_for_size(width=200, height=40)
    tight: Content | None = logo_for_size(width=LOGO_MIN_WIDTH, height=LOGO_MIN_HEIGHT)
    assert wide is not None
    assert tight is not None
    assert wide.plain == tight.plain == full_logo().plain


def test_no_wordmark_is_offered_when_the_frame_cannot_hold_it() -> None:
    assert logo_for_size(width=200, height=LOGO_MIN_HEIGHT - 1) is None
    assert logo_for_size(width=LOGO_MIN_WIDTH - 1, height=40) is None

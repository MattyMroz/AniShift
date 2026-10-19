from __future__ import annotations

import pytest

from anishift.services.subtitles.layout import DEFAULT_MAX_CHARS, MAX_LINES, LayoutLimits
from anishift.services.subtitles.linebreak import split_for_layout

_LONG_LINE = "Zupełnie przypadkowe zdanie o tym jak długo potrafi ciągnąć się jedna kwestia bohatera"


def test_defaults_match_the_shipped_pipeline() -> None:
    assert LayoutLimits() == LayoutLimits(max_chars=DEFAULT_MAX_CHARS, max_lines=MAX_LINES)


@pytest.mark.parametrize("changes", [{"max_chars": 0}, {"max_chars": -1}, {"max_lines": 0}])
def test_a_limit_that_cannot_produce_output_is_rejected(changes: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        LayoutLimits(**changes)


def test_the_layout_splitter_honours_the_verse_budget() -> None:
    verses = split_for_layout(_LONG_LINE, ("jedna kwestia",), max_chars=20, max_lines=1)
    assert verses == (_LONG_LINE,)

from __future__ import annotations

import pytest

from anishift.services.subtitles.layout import DEFAULT_MAX_CHARS, MAX_LINES, LayoutLimits


def test_defaults_match_the_shipped_pipeline() -> None:
    assert LayoutLimits() == LayoutLimits(max_chars=DEFAULT_MAX_CHARS, max_lines=MAX_LINES)


@pytest.mark.parametrize("changes", [{"max_chars": 0}, {"max_chars": -1}, {"max_lines": 0}])
def test_a_limit_that_cannot_produce_output_is_rejected(changes: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        LayoutLimits(**changes)

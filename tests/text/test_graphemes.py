from __future__ import annotations

import pytest

from anishift.text.graphemes import hard_split_graphemes, split_graphemes


@pytest.mark.parametrize(
    "grapheme",
    [
        "a\u0301",
        "👍🏽",
        "👨‍👩‍👧‍👦",
        "🇵🇱",
        "✈️",
        "1️⃣",
        "क्ष",
    ],
)
def test_split_graphemes_keeps_extended_clusters_whole(grapheme: str) -> None:
    assert split_graphemes(f"A{grapheme}B") == ("A", grapheme, "B")


def test_hard_split_preserves_graphemes_and_source_text() -> None:
    grapheme = "👨‍👩‍👧‍👦"
    text = f"A{grapheme}BC"
    chunks = hard_split_graphemes(text, len(grapheme))

    assert chunks == ["A", grapheme, "BC"]
    assert "".join(chunks) == text
    assert all(len(chunk) <= len(grapheme) for chunk in chunks)


def test_hard_split_uses_code_points_when_one_grapheme_exceeds_limit() -> None:
    text = "a\u0301"
    chunks = hard_split_graphemes(text, 1)

    assert chunks == ["a", "\u0301"]
    assert "".join(chunks) == text


@pytest.mark.parametrize("limit", [0, -1, True])
def test_hard_split_rejects_invalid_limits(limit: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        hard_split_graphemes("tekst", limit)

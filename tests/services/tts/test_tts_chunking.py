from __future__ import annotations

import pytest

from anishift.services.tts import TtsUnsupportedError
from anishift.services.tts.chunking import chunk_speech_text


def test_text_within_limits_stays_in_one_chunk() -> None:
    assert chunk_speech_text("Krótki tekst.", max_chars=100, max_bytes=100) == ("Krótki tekst.",)


def test_chunking_prefers_sentence_then_phrase_then_word_boundaries() -> None:
    sentence = chunk_speech_text("Pierwsze zdanie. Drugie zdanie.", max_chars=18, max_bytes=None)
    phrase = chunk_speech_text("Pierwsza część, druga część", max_chars=17, max_bytes=None)
    words = chunk_speech_text("pierwsze drugie trzecie", max_chars=15, max_bytes=None)

    assert sentence == ("Pierwsze zdanie. ", "Drugie zdanie.")
    assert phrase == ("Pierwsza część, ", "druga część")
    assert words == ("pierwsze ", "drugie trzecie")


def test_byte_limit_is_enforced_independently_of_character_limit() -> None:
    text = "ąć ąć ąć"
    chunks = chunk_speech_text(text, max_chars=100, max_bytes=5)

    assert "".join(chunks) == text
    assert all(len(chunk.encode("utf-8")) <= 5 for chunk in chunks)


@pytest.mark.parametrize(
    "cluster",
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
def test_chunking_never_splits_unicode_graphemes(cluster: str) -> None:
    text = f"A{cluster}B"
    chunks = chunk_speech_text(
        text,
        max_chars=len(cluster) + 1,
        max_bytes=None,
    )

    assert "".join(chunks) == text
    assert any(cluster in chunk for chunk in chunks)


def test_character_limit_counts_code_points_without_splitting_graphemes() -> None:
    with pytest.raises(TtsUnsupportedError):
        chunk_speech_text("a\u0301", max_chars=1, max_bytes=None)


def test_one_grapheme_larger_than_byte_limit_is_unsupported() -> None:
    with pytest.raises(TtsUnsupportedError):
        chunk_speech_text("🙂", max_chars=None, max_bytes=3)


def test_punctuation_cannot_be_orphaned_by_a_tight_limit() -> None:
    with pytest.raises(TtsUnsupportedError):
        chunk_speech_text("A!", max_chars=1, max_bytes=None)


@pytest.mark.parametrize(
    ("text", "max_chars", "expected"),
    [
        ("AA!", 2, ("A", "A!")),
        ("! AB", 3, ("! A", "B")),
    ],
)
def test_chunking_moves_boundaries_to_keep_every_part_pronounceable(
    text: str,
    max_chars: int,
    expected: tuple[str, ...],
) -> None:
    assert chunk_speech_text(text, max_chars=max_chars, max_bytes=None) == expected


def test_chunking_backtracks_when_a_greedy_suffix_would_fail() -> None:
    assert chunk_speech_text("AA, A", max_chars=2, max_bytes=None) == (
        "A",
        "A,",
        " A",
    )


def test_chunking_never_reorders_punctuation_to_invent_a_partition() -> None:
    with pytest.raises(TtsUnsupportedError):
        chunk_speech_text("AA!!!", max_chars=3, max_bytes=None)


@pytest.mark.parametrize(
    ("max_chars", "max_bytes"),
    [(0, None), (-1, None), (True, None), (None, 0), (None, -1), (None, True)],
)
def test_invalid_limits_are_rejected(
    max_chars: int | None,
    max_bytes: int | None,
) -> None:
    with pytest.raises(ValueError, match="positive integers"):
        chunk_speech_text("Tekst", max_chars=max_chars, max_bytes=max_bytes)


def test_chunking_preserves_all_source_whitespace() -> None:
    text = "Pierwsze.   Drugie."
    chunks = chunk_speech_text(text, max_chars=12, max_bytes=None)

    assert chunks == ("Pierwsze.   ", "Drugie.")
    assert "".join(chunks) == text


def test_decimal_abbreviation_and_initial_are_not_sentence_boundaries() -> None:
    text = "Dr A. Kowalski żył w 1798. roku i miał ok. 1.5 kg, np. jabłek."
    chunks = chunk_speech_text(text, max_chars=20, max_bytes=None)

    assert "".join(chunks) == text
    assert chunks[0] != "Dr A. "


@pytest.mark.parametrize(
    ("text", "max_chars", "expected"),
    [
        ("Tekst", 5, ("Tekst",)),
        ("Teksty", 5, ("Tekst", "y")),
        ("Tekst", None, ("Tekst",)),
    ],
)
def test_character_limit_boundaries(
    text: str,
    max_chars: int | None,
    expected: tuple[str, ...],
) -> None:
    chunks = chunk_speech_text(text, max_chars=max_chars, max_bytes=None)

    assert chunks == expected
    assert all(any(character.isalnum() for character in chunk) for chunk in chunks)

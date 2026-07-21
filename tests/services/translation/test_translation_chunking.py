import pytest

from anishift.services.translation import chunking
from anishift.services.translation.chunking import (
    _PHRASE_CUT_CHARS,
    chunk_text,
    split_paragraphs,
    split_phrases,
    split_sentences,
    split_words,
)


def test_phrase_cut_set_spans_hundreds_of_chars_across_scripts() -> None:
    assert len(_PHRASE_CUT_CHARS) > 500


@pytest.mark.parametrize("closing", [")", "]", "}", "»", "”", "、", "،", "؛"])
def test_closing_and_phrase_marks_from_many_scripts_are_cut_points(closing: str) -> None:
    assert closing in _PHRASE_CUT_CHARS


@pytest.mark.parametrize("opening", ["(", "[", "{", "«", "“", "〈", "「"])
def test_opening_brackets_and_quotes_never_cut(opening: str) -> None:
    assert opening not in _PHRASE_CUT_CHARS


def test_arabic_comma_splits_phrases() -> None:
    assert len(split_phrases("مرحبا، كيف")) == 2


def test_cjk_closing_quote_splits_phrases() -> None:
    assert len(split_phrases("彼は「こんにちは」と言った")) > 1


@pytest.mark.parametrize("word", ["don't", "don’t"])  # noqa: RUF001 - typographic apostrophe on purpose
def test_apostrophes_never_cut(word: str) -> None:
    assert split_phrases(f"{word} stop") == [f"{word} stop"]


def test_paragraphs_split_on_blank_lines() -> None:
    parts = split_paragraphs("Pierwszy akapit.\n\nDrugi akapit.")
    assert len(parts) == 2
    assert "".join(parts) == "Pierwszy akapit.\n\nDrugi akapit."


def test_words_split_on_whitespace_and_rejoin_exactly() -> None:
    words = split_words("Ala ma  kota")
    assert len(words) == 3
    assert "".join(words) == "Ala ma  kota"


def test_sentences_split_on_endings() -> None:
    assert split_sentences("Pierwsze zdanie. Drugie zdanie!") == ["Pierwsze zdanie. ", "Drugie zdanie!"]


def test_ellipsis_ends_a_sentence() -> None:
    assert len(split_sentences("Czekaj… Myślę.")) == 2


def test_en_title_abbreviation_keeps_sentence_whole() -> None:
    sentences = split_sentences("Dr. Smith met Mr. Brown. Then he left.")
    assert sentences == ["Dr. Smith met Mr. Brown. ", "Then he left."]


def test_pl_abbreviation_before_capital_keeps_sentence_whole() -> None:
    assert split_sentences("Kup mleko, chleb itd. Potem wróć.") == ["Kup mleko, chleb itd. Potem wróć."]


def test_lowercase_after_dot_is_not_a_boundary_in_any_language() -> None:
    sentences = split_sentences("Der Zug kam ca. fünf Minuten später. Alle warteten.")
    assert sentences[0] == "Der Zug kam ca. fünf Minuten später. "


def test_single_letter_initial_is_not_a_boundary() -> None:
    sentences = split_sentences("A. Mickiewicz to poeta. Znają go wszyscy.")
    assert sentences[0] == "A. Mickiewicz to poeta. "


def test_ordinal_number_before_lowercase_is_not_a_boundary() -> None:
    sentences = split_sentences("Urodził się w 1798. roku. Zmarł później.")
    assert sentences[0] == "Urodził się w 1798. roku. "


def test_short_text_is_one_chunk() -> None:
    assert chunk_text("Zdanie pierwsze. Zdanie drugie.") == ["Zdanie pierwsze. Zdanie drugie."]


def test_chunks_respect_char_limit() -> None:
    text = " ".join(f"slowo{i}" for i in range(200))
    chunks = chunk_text(text, char_limit=100, chunk_limit=50)
    assert len(chunks) > 1
    assert all(len(chunk) <= 100 for chunk in chunks)


@pytest.mark.parametrize(
    "text",
    [
        "Ala ma kota. Kot ma Alę. Wszyscy są zadowoleni z tego układu.",
        "Hello world。 これはテストです。 Goodbye.",
        "Dr. Smith i prof. Nowak np. rozmawiali, itd. — bez końca.",
    ],
)
def test_chunks_concatenate_back_to_input(text: str) -> None:
    assert "".join(chunk_text(text, char_limit=20, chunk_limit=10)) == text


def test_empty_text_gives_no_chunks() -> None:
    assert chunk_text("") == []


def test_whitespace_only_text_is_one_chunk() -> None:
    assert chunk_text("   \t  ") == ["   \t  "]


def test_oversized_word_is_hard_cut() -> None:
    chunks = chunk_text("a" * 300, char_limit=100, chunk_limit=100)
    assert all(len(chunk) <= 100 for chunk in chunks)
    assert "".join(chunks) == "a" * 300


def test_cjk_splits_on_ideographic_full_stop() -> None:
    assert chunk_text("こんにちは。世界です。", char_limit=8, chunk_limit=8) == ["こんにちは。", "世界です。"]


def test_smaller_chunk_limit_packs_chunks_tighter() -> None:
    sentence = "A" + "a" * 194 + ", " + "b" * 195 + ". "
    text = sentence * 10
    coarse = chunk_text(text, char_limit=750, chunk_limit=750)
    fine = chunk_text(text, char_limit=750, chunk_limit=250)
    assert len(fine) < len(coarse)
    assert all(len(chunk) <= 750 for chunk in coarse)
    assert all(len(chunk) <= 750 for chunk in fine)
    assert "".join(coarse) == text
    assert "".join(fine) == text


def test_default_limits_are_750_and_250() -> None:
    assert chunking.DEFAULT_CHAR_LIMIT == 750
    assert chunking.DEFAULT_CHUNK_LIMIT == 250
    text = "Pełne zdanie z kilkoma słowami w środku. " * 50
    chunks = chunk_text(text)
    assert len(chunks) > 1
    assert all(len(chunk) <= 750 for chunk in chunks)
    assert "".join(chunks) == text

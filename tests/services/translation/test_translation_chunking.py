import pytest

from anishift.services.translation.chunking import _PHRASE_CUT_CHARS, LatinPunctuator, chunk_text


def test_unicode_cut_set_covers_all_languages() -> None:
    # Built from unicodedata categories, so it spans hundreds of chars across
    # every script - not the handful a hand-written list would hold.
    assert len(_PHRASE_CUT_CHARS) > 500


@pytest.mark.parametrize(
    "closing",
    # Pe/Pf/Pd/Po phrase marks from many scripts must all be cut points.
    # CJK full stop U+3002 is a sentence ending, not a phrase cut - excluded.
    [")", "]", "}", "»", "”", "、", "،", "؛"],
)
def test_closing_and_marks_are_cut_points(closing: str) -> None:
    assert closing in _PHRASE_CUT_CHARS


@pytest.mark.parametrize("opening", ["(", "[", "{", "«", "“", "〈", "「"])
def test_opening_brackets_and_quotes_never_cut(opening: str) -> None:
    assert opening not in _PHRASE_CUT_CHARS


def test_arabic_comma_splits_phrases() -> None:
    phrases = LatinPunctuator().get_phrases("مرحبا، كيف")
    assert len(phrases) > 1


def test_ellipsis_glyph_ends_a_sentence() -> None:
    sentences = LatinPunctuator().get_sentences("Czekaj… myślę tak.")
    assert len(sentences) == 2


def test_apostrophe_kept_inside_word() -> None:
    words = LatinPunctuator().get_words("don't stop")
    assert any(w.strip() == "don't" for w in words)


def test_short_text_single_chunk() -> None:
    assert chunk_text("Zdanie pierwsze. Zdanie drugie.", limit=100) == ["Zdanie pierwsze. Zdanie drugie."]


def test_chunks_respect_limit() -> None:
    text = " ".join(f"slowo{i}" for i in range(200))
    chunks = chunk_text(text, limit=100)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 100


def test_chunks_preserve_all_content() -> None:
    text = "Ala ma kota. Kot ma Alę. Wszyscy są zadowoleni z tego układu."
    chunks = chunk_text(text, limit=20)
    joined = "".join(chunks)
    assert joined.replace(" ", "") == text.replace(" ", "")


def test_empty_text_returns_empty() -> None:
    assert chunk_text("", limit=100) == []


def test_word_method_produces_more_chunks_at_lower_limit() -> None:
    # WordBreaker counts word+separator tokens (faithful to the original);
    # a smaller limit yields more chunks and preserves all content.
    text = "one two three four five six"
    few = chunk_text(text, method="word", limit=6)
    many = chunk_text(text, method="word", limit=2)
    assert len(many) > len(few)
    assert "".join(many).split() == text.split()


def test_very_long_word_is_hard_cut() -> None:
    chunks = chunk_text("a" * 300, limit=100)
    assert all(len(chunk) <= 100 for chunk in chunks)
    assert "".join(chunks) == "a" * 300


def test_single_punctuation_char() -> None:
    assert chunk_text(".", limit=100) == ["."]


def test_abbreviation_is_not_a_sentence_boundary() -> None:
    # "Dr." must not split the sentence; "Dr. Kowalski był" stays whole.
    sentences = LatinPunctuator().get_sentences("Dr. Kowalski był tutaj. Potem wyszedł.")
    assert any("Dr. Kowalski był tutaj." in s for s in sentences)


def test_polish_abbreviation_not_split() -> None:
    # "itd." is an abbreviation, so its dot does not end the sentence: the whole
    # phrase up to and past "itd." stays in one piece.
    sentences = LatinPunctuator().get_sentences("Kup mleko, chleb itd. Potem wróć.")
    assert any("itd. Potem" in s for s in sentences)


def test_cjk_text_splits_on_ideographic_punctuation() -> None:
    chunks = chunk_text("こんにちは。世界です。", limit=8)
    assert len(chunks) == 2


def test_cjk_quotes_split_phrases() -> None:
    phrases = LatinPunctuator().get_phrases("彼は「こんにちは」と言った")
    assert len(phrases) > 1


def test_mixed_jp_en_text_preserved() -> None:
    text = "Hello world。 これはテストです。 Goodbye."
    chunks = chunk_text(text, limit=15)
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_get_words_keeps_symbols_as_tokens() -> None:
    words = LatinPunctuator().get_words("cena @ 100 zł")
    assert any("@" in w for w in words)

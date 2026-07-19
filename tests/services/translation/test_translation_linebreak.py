import pytest

from anishift.services.translation.linebreak import split_line


def test_short_line_stays_single() -> None:
    assert split_line("Krótkie zdanie.") == ("Krótkie zdanie.",)


def test_line_without_space_is_not_split() -> None:
    long_token = "a" * 60
    assert split_line(long_token) == (long_token,)


@pytest.mark.parametrize(
    "text",
    [
        "Nie wiem, czy dam radę bo to trudne zadanie dla mnie",
        "Musimy iść do domu zanim zrobi się całkiem ciemno na zewnątrz",
        "Powiedziała że wróci wieczorem ale nie podała dokładnej godziny",
    ],
)
def test_long_line_splits_into_short_verses(text: str) -> None:
    verses = split_line(text, max_chars=42)
    assert len(verses) >= 2
    for verse in verses:
        assert verse
        # each verse is comfortably short (allow small overshoot on hard cases)
        assert len(verse) <= 50


def test_no_orphan_single_word_verse() -> None:
    verses = split_line("To jest naprawdę bardzo długie zdanie do przetestowania podziału", max_chars=42)
    for verse in verses:
        assert " " in verse.strip() or len(verses) == 1


def test_preposition_stays_with_noun() -> None:
    # "w domu" must not be split between the two verses.
    verses = split_line("Spotkamy się w domu mojego przyjaciela dzisiaj wieczorem po pracy", max_chars=30)
    joined = "\n".join(verses)
    assert "w\ndomu" not in joined
    assert "na\n" not in joined


def test_cut_prefers_comma() -> None:
    verses = split_line("Zjadłem obiad, potem poszedłem na spacer do parku", max_chars=28)
    assert verses[0].rstrip().endswith(",")

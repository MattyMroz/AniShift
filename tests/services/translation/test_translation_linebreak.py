import pytest

from anishift.services.translation.linebreak import (
    _CONJUNCTIONS,
    _CONJUNCTIONS_MULTIWORD,
    _PREPOSITIONS_MULTIWORD,
    MAX_LINES,
    split_line,
)


def test_empty_text_returns_single_empty_verse() -> None:
    assert split_line("") == ("",)


def test_single_word_is_not_split() -> None:
    assert split_line("Słowo") == ("Słowo",)


def test_short_line_stays_single() -> None:
    assert split_line("Krótkie zdanie.") == ("Krótkie zdanie.",)


def test_line_without_space_is_not_split() -> None:
    long_token = "a" * 60
    assert split_line(long_token) == (long_token,)


def test_whitespace_runs_collapse_to_single_space() -> None:
    assert split_line("Ala   ma \t kota") == ("Ala ma kota",)


def test_foreign_line_without_word_lists_still_splits_near_centre() -> None:
    verses = split_line("これは テスト です とても 長い 行 の 分割 用", max_chars=12)
    assert len(verses) == MAX_LINES
    assert all(verse for verse in verses)


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
    assert len(verses) <= MAX_LINES
    for verse in verses:
        assert verse
        assert len(verse) <= 50


def test_never_exceeds_max_lines_even_when_text_cannot_fit() -> None:
    text = " ".join(f"slowo{i}" for i in range(40))
    verses = split_line(text, max_chars=20)
    assert len(verses) <= MAX_LINES
    assert all(verses)


def test_both_verses_fit_when_split_is_possible() -> None:
    verses = split_line("To zdanie ma dokladnie tyle znakow ile trzeba do podzialu", max_chars=32)
    assert len(verses) == 2
    for verse in verses:
        assert len(verse) <= 32


def test_no_orphan_single_word_verse() -> None:
    verses = split_line("To jest naprawdę bardzo długie zdanie do przetestowania podziału", max_chars=42)
    for verse in verses:
        assert " " in verse.strip() or len(verses) == 1


def test_preposition_stays_with_noun() -> None:
    verses = split_line("Spotkamy się w domu mojego przyjaciela dzisiaj wieczorem po pracy", max_chars=30)
    joined = "\n".join(verses)
    assert "w\ndomu" not in joined
    assert not any(v.strip().endswith(" w") or v.strip() in {"w", "na", "z"} for v in verses)


def test_cut_prefers_comma() -> None:
    verses = split_line("Zjadłem obiad, potem poszedłem na spacer do parku", max_chars=28)
    assert verses[0].rstrip().endswith(",")


def test_cut_prefers_conjunction_boundary() -> None:
    verses = split_line("Chciałem przyjść ale zabrakło mi czasu", max_chars=22)
    assert len(verses) == 2
    assert verses[1].lower().startswith("ale")


def test_multiword_conjunction_kept_whole() -> None:
    verses = split_line("Czytałem książkę podczas gdy ona gotowała obiad w kuchni", max_chars=28)
    joined = "\n".join(verses)
    assert "podczas\ngdy" not in joined


def test_multiword_preposition_kept_whole() -> None:
    verses = split_line("Odwołano wycieczkę ze względu na bardzo złą pogodę tego dnia", max_chars=26)
    joined = "\n".join(verses)
    assert "ze\nwzględu" not in joined
    assert "względu\nna" not in joined


def test_complete_conjunction_list_loaded() -> None:
    assert len(_CONJUNCTIONS) == 76
    for word in ("aczkolwiek", "aniżeli", "wszelako", "niżeli", "ilekroć"):
        assert word in _CONJUNCTIONS


def test_multiword_conjunction_at_line_start_is_kept_whole() -> None:
    verses = split_line("Zostań w domu chyba że wolisz iść ze mną dzisiaj wieczorem", max_chars=24)
    joined = "\n".join(verses)
    assert "chyba\nże" not in joined
    assert ("chyba", "że") in _CONJUNCTIONS_MULTIWORD


def test_multiword_preposition_three_words_is_kept_whole() -> None:
    verses = split_line("Zrobił to bez względu na koszty jakie musiał ostatecznie ponieść", max_chars=26)
    joined = "\n".join(verses)
    assert "bez\nwzględu" not in joined
    assert "względu\nna" not in joined
    assert ("bez", "względu", "na") in _PREPOSITIONS_MULTIWORD

import pytest

from anishift.services.subtitles.linebreak import MAX_LINES, split_for_layout, split_line
from anishift.text.gaps import CONJUNCTIONS, CONJUNCTIONS_MULTIWORD, PREPOSITIONS_MULTIWORD


def test_empty_text_returns_single_empty_verse() -> None:
    assert split_line("") == ("",)


@pytest.mark.unit
@pytest.mark.parametrize("dash", ["-", "–", "—"])
@pytest.mark.parametrize("space", ["", " "])
def test_attached_speaker_markers_keep_turns_separate(dash: str, space: str) -> None:
    first: str = f"{dash}{space}Idziesz ze mną?"
    second: str = f"{dash}{space}Tak."
    assert split_line(f"{first} {second}") == (first, second)


@pytest.mark.unit
def test_dash_aside_is_not_a_speaker_turn() -> None:
    text: str = "- Myślę - powiedział cicho."
    assert split_line(text) == (text,)


@pytest.mark.unit
def test_three_speakers_still_use_the_line_budget() -> None:
    text: str = "- Idziesz ze mną? - Tak, już wychodzę. - Na pewno?"
    verses: tuple[str, ...] = split_line(text)
    assert len(verses) == 2
    assert max(map(len, verses)) <= 42
    assert " ".join(verses) == text


@pytest.mark.unit
@pytest.mark.parametrize(
    "preposition", ["według", "wśród", "obok", "zza", "spod", "poza", "wobec", "podczas", "około", "ponad", "pomiędzy"]
)
def test_additional_prepositions_never_end_a_verse(preposition: str) -> None:
    text: str = f"Wczoraj szedłem {preposition} domu ponownie"
    assert f"{preposition} domu" in "\n".join(split_line(text, max_chars=20))


@pytest.mark.unit
@pytest.mark.parametrize("limit", [8, 13, 16])
def test_name_is_protected_even_when_that_requires_overflow(limit: int) -> None:
    assert "Jan Kowalski" in "\n".join(split_line("Wczoraj Jan Kowalski ponownie", max_chars=limit))


@pytest.mark.unit
def test_capitalised_run_without_other_cuts_still_breaks() -> None:
    text: str = "Święty Imperator Wilhelm Ludwig Evernatten."
    verses: tuple[str, ...] = split_line(text)
    assert len(verses) == 2
    assert max(map(len, verses)) <= 42
    assert " ".join(verses) == text


@pytest.mark.unit
def test_all_caps_dialogue_is_not_one_protected_name() -> None:
    text: str = "NIE WIEM CO MAM TERAZ ZROBIĆ Z TYM WSZYSTKIM NAPRAWDĘ"
    verses: tuple[str, ...] = split_line(text)
    assert len(verses) == 2
    assert max(map(len, verses)) <= 42
    assert " ".join(verses) == text


@pytest.mark.unit
def test_unavoidable_overflow_tolerates_two_characters_for_intact_adjective_phrase() -> None:
    text: str = "Wczoraj widziałem ogromnego smoka daleko stąd."
    assert split_line(text, max_chars=24) == ("Wczoraj widziałem", "ogromnego smoka daleko stąd.")


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "Powiedziałem mu wszystko, co wiedziałem o tamtej strasznej nocy w lesie.",
    ],
)
def test_dialogue_chooses_a_fitting_boundary_before_punctuation_bonus(text: str) -> None:
    verses: tuple[str, ...] = split_line(text)
    assert len(verses) == 2
    assert max(map(len, verses)) <= 42
    assert " ".join(verses) == text


@pytest.mark.unit
@pytest.mark.parametrize("dash", ["-", "–", "—"])
@pytest.mark.parametrize("first", ["Tak.", "Tak", "To jest bardzo długa wypowiedź pierwszego rozmówcy."])
def test_two_speakers_get_exactly_one_verse_each(dash: str, first: str) -> None:
    assert split_line(f"{dash} {first} {dash} Nie.") == (f"{dash} {first}", f"{dash} Nie.")


@pytest.mark.unit
@pytest.mark.parametrize("abbreviation", ["np.", "dr", "dr.", "ok.", "p.", "ul.", "tzn.", "itd.", "itp.", "godz."])
def test_abbreviations_stay_with_the_following_word(abbreviation: str) -> None:
    text: str = f"Zobacz koniecznie {abbreviation} Kowalski przekazał wiadomość dla ciebie."
    assert not split_line(text, max_chars=30)[0].endswith(abbreviation)


@pytest.mark.unit
@pytest.mark.parametrize(
    "phrase",
    [
        "nie wróci",
        "on wróci",
        "będzie biegać",
        "musi wyjść",
        "stary dom",
        "czerwonego smoka",
        "Jan Kowalski",
        "pan Kowalski",
        "on się boi",
        "boi się",
    ],
)
def test_protected_polish_phrase_is_not_split(phrase: str) -> None:
    text: str = f"Wczoraj {phrase} ponownie"
    verses: tuple[str, ...] = split_line(text, max_chars=len(text) - len("Wczoraj "))
    assert phrase in "\n".join(verses)
    assert " ".join(verses) == text


@pytest.mark.unit
def test_nonbreaking_space_is_never_a_cut_candidate() -> None:
    text: str = "Widziałem Jan\u00a0Kowalski ponownie"
    assert "Jan\u00a0Kowalski" in "\n".join(split_line(text, max_chars=15))


@pytest.mark.unit
def test_no_legal_boundary_preserves_one_overlong_verse() -> None:
    assert split_line("w nie tak", max_chars=3) == ("w nie tak",)


@pytest.mark.unit
def test_unavoidable_overflow_minimizes_the_longest_verse() -> None:
    text: str = (
        "Dobra, wczoraj wieczorem poszedłem sam do sklepu, a tam spotkałem starego przyjaciela "
        "z liceum, który mnie nie poznał."
    )
    verses: tuple[str, ...] = split_line(text)
    assert max(map(len, verses)) <= 62


@pytest.mark.unit
@pytest.mark.parametrize("budget", [3, 4])
def test_dialogue_reserves_remaining_line_budget_for_the_right_side(budget: int) -> None:
    text: str = " ".join(["abcdefghij"] * (budget * 5))
    verses: tuple[str, ...] = split_line(text, max_lines=budget)
    assert len(verses) == budget
    assert max(map(len, verses)) <= 76
    assert " ".join(verses) == text


@pytest.mark.unit
def test_sentence_boundary_wins_over_comma_when_both_fit() -> None:
    assert split_line("Wróciłem. Zjadłem obiad, potem zasnąłem.", max_chars=30) == (
        "Wróciłem.",
        "Zjadłem obiad, potem zasnąłem.",
    )


@pytest.mark.unit
def test_conjunction_boundary_wins_over_comma_when_both_fit() -> None:
    assert split_line("Zjadłem obiad, odpocząłem ale potem wyszedłem.", max_chars=35) == (
        "Zjadłem obiad, odpocząłem",
        "ale potem wyszedłem.",
    )


@pytest.mark.unit
def test_equally_natural_breaks_prefer_bottom_heavy_shape() -> None:
    verses: tuple[str, ...] = split_line("Wczoraj wróciłem samotnie wieczorem ponownie", max_chars=28)
    assert len(verses) == 2
    assert len(verses[0]) <= len(verses[1])


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


@pytest.mark.parametrize("limit", [12, 18, 24, 30, 42])
@pytest.mark.parametrize(
    "text",
    [
        "Zastanawiam się nad tym.",
        "Naprawdę bardzo boję się wracać do domu.",
        "Postanowiłem się nie poddawać, nawet jeśli będzie trudno.",
        "Wtedy właśnie spotkaliśmy się ponownie po wielu latach.",
    ],
)
def test_polish_reflow_keeps_reflexive_particle_off_generated_line_starts(text: str, limit: int) -> None:
    verses: tuple[str, ...] = split_line(text, max_chars=limit)

    assert " ".join(verses) == text
    assert not any(verse.split()[0].casefold().strip(".,!?") == "się" for verse in verses[1:])


@pytest.mark.parametrize(
    "text", ["Się nie zmienia źródła.", "Sięga wysoko, ale jeszcze nie dosięga sufitu.", "— Boję się! — Nie bój się."]
)
def test_polish_reflow_never_reorders_or_rewrites_words(text: str) -> None:
    assert " ".join(split_line(text, max_chars=14)) == text


def test_cut_prefers_comma() -> None:
    verses = split_line("Zjadłem obiad, potem poszedłem na spacer do parku", max_chars=34)
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
    assert len(CONJUNCTIONS) == 76
    for word in ("aczkolwiek", "aniżeli", "wszelako", "niżeli", "ilekroć"):
        assert word in CONJUNCTIONS


def test_multiword_conjunction_at_line_start_is_kept_whole() -> None:
    verses = split_line("Zostań w domu chyba że wolisz iść ze mną dzisiaj wieczorem", max_chars=24)
    joined = "\n".join(verses)
    assert "chyba\nże" not in joined
    assert ("chyba", "że") in CONJUNCTIONS_MULTIWORD


def test_multiword_preposition_three_words_is_kept_whole() -> None:
    verses = split_line("Zrobił to bez względu na koszty jakie musiał ostatecznie ponieść", max_chars=26)
    joined = "\n".join(verses)
    assert "bez\nwzględu" not in joined
    assert "względu\nna" not in joined
    assert ("bez", "względu", "na") in PREPOSITIONS_MULTIWORD


def test_split_for_layout_preserves_authored_displayed_line_count() -> None:
    verses = split_for_layout(
        "Odcinek 3: Życie z powrotem w domu",
        ("Episode 3", "Life Back at Home"),
    )
    assert verses == ("Odcinek 3:", "Życie z powrotem w domu")


def test_split_for_layout_prefers_semantic_boundary_over_source_ratio() -> None:
    verses = split_for_layout(
        "W następnym odcinku: Wodny mag rangi królewskiej",
        ("Next Time", "A King-Class Water Mage"),
    )
    assert verses == ("W następnym odcinku:", "Wodny mag rangi królewskiej")


def test_split_for_layout_keeps_one_source_verse_on_normal_policy() -> None:
    text = "To jest długie polskie zdanie, które powinno zostać czytelnie podzielone na ekranie"
    assert split_for_layout(text, ("One source line",)) == (
        "To jest długie polskie zdanie,",
        "które powinno zostać czytelnie podzielone na ekranie",
    )


def test_split_for_layout_does_not_break_one_target_word_artificially() -> None:
    assert split_for_layout("Dom", ("Home", "again")) == ("Dom",)


@pytest.mark.parametrize(
    "text",
    [
        "Co innego bestiodłuni i ich odporność na Urok,",
        "Zamknęli bramy miasta i nikt nie może teraz wyjść na zewnątrz",
        "Kupiłem chleb oraz masło na jutrzejsze wspólne śniadanie",
    ],
)
def test_no_conjunction_dangling_at_line_end(text: str) -> None:
    verses = split_line(text, max_chars=42)
    assert len(verses) == 2
    assert verses[0].split()[-1].lower() not in CONJUNCTIONS


def test_split_for_layout_keeps_balanced_paragraph_balanced() -> None:
    source = (
        "This is a work of fiction.",
        "Underage drinking is strongly",
        "prohibited and illegal. We also",
        "do not encourage the forceful or",
        "excessive  consumption of alcohol,",
        "nor do we endorse the litany of",
        "depraved and shameful acts portrayed",
        "in the binge-drinking scenes. We ask",
        "that you view this as a comedy anime",
        "and  nothing more. Furthermore,",
        " all characters drinking in this work",
        "are of legal age. In keeping with",
        "the recent social climate, the black circles",
        "have been increased 5% in size from this season.",
    )
    target = (
        "To jest dzieło fikcyjne. Spożywanie alkoholu przez osoby niepełnoletnie "
        "jest surowo zabronione i nielegalne. Nie zachęcamy również do wymuszonego "
        "ani nadmiernego spożywania alkoholu, ani nie popieramy serii zepsutych i "
        "wstydliwych czynów przedstawionych w scenach opilstwa. Prosimy traktować "
        "to jako anime komediowe i nic więcej. Ponadto wszystkie postacie pijące w "
        "tym dziele są pełnoletnie. Zgodnie z obecnym klimatem społecznym, czarne "
        "kółka zostały powiększone o 5% w porównaniu z poprzednim sezonem."
    )
    verses = split_for_layout(target, source)
    assert len(verses) == len(source)
    assert max(len(verse) for verse in verses) <= 60
    assert all(" " in verse for verse in verses)

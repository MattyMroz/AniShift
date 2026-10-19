from __future__ import annotations

import pytest

from anishift.text.gaps import PROTECTED_KINDS, TIERS, Gap, GapKind, gaps, list_markers, quote_spans


def _gap(text: str, left: str) -> Gap:
    words: list[str] = text.split(" ")
    return gaps(words)[words.index(left)]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left", "kind"),
    [
        ("Idę spać. Idź spać.", "spać.", GapKind.SENTENCE),
        ("Naprawdę?! Nie wierzę!", "Naprawdę?!", GapKind.SENTENCE),
        ("O! Spójrz!", "O!", GapKind.SENTENCE),
        ("Wcale nie. Idę już.", "nie.", GapKind.SENTENCE),
        ("Martwię się o ciebie, bo nie odpowiadasz.", "ciebie,", GapKind.CLAUSE),
        ("Ja… nie wiem, czy potrafię.", "Ja…", GapKind.ELLIPSIS),
        ("Wszyscy – a zwłaszcza on – poszli już.", "–", GapKind.PARENTHETICAL),
        ("Myślę – powiedział cicho.", "–", GapKind.DASH),
        ("Ludzie zamieszkujący te ziemie popełnili grzechy.", "ziemie", GapKind.PHRASE),
        ("Jan Kowalski czeka na dworcu.", "Jan", GapKind.NAME),
        ("Czekał pan Kowalski.", "pan", GapKind.NAME),
        ("Musimy iść do domu.", "do", GapKind.AFTER_PREPOSITION),
        ("Zrobił to bez względu na koszty.", "względu", GapKind.AFTER_PREPOSITION),
        ("Kupiłem chleb i masło.", "i", GapKind.AFTER_OPENER),
        ("Witamina C działa.", "C", GapKind.AFTER_SINGLE_LETTER),
        ("Wiem, że wrócisz.", "że", GapKind.AFTER_OPENER),
        ("To dom, który kupiłem.", "który", GapKind.AFTER_OPENER),
        ("Nigdy nie chciałem tego.", "nie", GapKind.NEGATION),
        ("Z nami będziesz się bawił.", "się", GapKind.REFLEXIVE),
        ("Z nami będziesz się bawił.", "będziesz", GapKind.REFLEXIVE),
        ("Kto pierwszy się zakocha?", "się", GapKind.REFLEXIVE),
        ("Ciągle się boi.", "się", GapKind.REFLEXIVE),
        ("Kosztuje 20–30 zł.", "20–30", GapKind.NUMBER),
        ("To 1,4 miliarda ludzi.", "1,4", GapKind.NUMBER),
        ("Kup np. chleb.", "np.", GapKind.ABBREVIATION),
        ("Zostań chyba że wolisz iść.", "chyba", GapKind.IDIOM),
        ("Zrobię to raz na zawsze.", "raz", GapKind.IDIOM),
        ("Tak czy inaczej idę.", "czy", GapKind.IDIOM),
        ("Mimo wszystko wrócę.", "Mimo", GapKind.IDIOM),
        ("Idziemy w końcu do domu.", "w", GapKind.AFTER_PREPOSITION),
        ("Musi wrócić dziś.", "Musi", GapKind.AUXILIARY),
        ("Widziałem czerwonego smoka.", "czerwonego", GapKind.MODIFIER),
        ("Widziałem tego smoka.", "tego", GapKind.MODIFIER),
        ("Kupiłem chleb i masło.", "chleb", GapKind.BEFORE_COORDINATOR),
        ("Idź z Midorikawą albo resztą.", "Midorikawą", GapKind.BEFORE_COORDINATOR),
        ("Widzę dom który kupiłem.", "dom", GapKind.BEFORE_SUBORDINATOR),
        ("Wiem dobrze że wrócisz.", "dobrze", GapKind.BEFORE_SUBORDINATOR),
        ("Zostanę dłużej chyba że wolisz.", "dłużej", GapKind.BEFORE_SUBORDINATOR),
        ("Zostanę dłużej a co więcej zaczekam.", "dłużej", GapKind.BEFORE_COORDINATOR),
        ("Zakochałem się w niej.", "Zakochałem", GapKind.REFLEXIVE),
        ("Wszyscy wiedzą kto pierwszy się zakocha podczas zabawy.", "się", GapKind.REFLEXIVE),
        ("Wydaje się, że tak.", "Wydaje", GapKind.REFLEXIVE),
        ("Siedzę cicho na ławce.", "cicho", GapKind.BEFORE_PREPOSITION),
        ("Czekam spokojnie w związku z tym.", "spokojnie", GapKind.BEFORE_PREPOSITION),
        ("Musi w końcu wrócić.", "Musi", GapKind.AUXILIARY),
        ("Wolisz kawę czy herbatę?", "kawę", GapKind.BEFORE_COORDINATOR),
        ("Znam chleb jak i masło.", "chleb", GapKind.BEFORE_COORDINATOR),
        ("Wiem dobrze jak gdyby nigdy nic.", "dobrze", GapKind.BEFORE_SUBORDINATOR),
        ("On się na mnie patrzy.", "On", GapKind.REFLEXIVE),
        ("Wszyscy wiedzą kto pierwszy się zakocha.", "pierwszy", GapKind.REFLEXIVE),
    ],
)
def test_gap_class_follows_the_evidence_of_its_words(text: str, left: str, kind: GapKind) -> None:
    gap: Gap = _gap(text, left)

    assert gap.kind == kind
    assert gap.protected == (kind in PROTECTED_KINDS)
    assert not gap.turn


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left"),
    [
        ("Liczę na nie dziś.", "nie"),
        ("Dlaczego się na mnie patrzysz?", "się"),
        ("On się na mnie patrzy.", "się"),
        ("Boję się, że nie zdążę.", "się,"),
        ("Martwię się bo nie odpowiadasz.", "się"),
        ("Cieszę się i czekam.", "się"),
        ("Boję się w związku z tym.", "się"),
        ("Właściwie to ta dziewczyna nazywa się Magiczna Różowa...", "się"),
    ],
)
def test_word_that_only_looks_bound_leaves_the_gap_weighted(text: str, left: str) -> None:
    assert not _gap(text, left).protected


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "Zupełnie nie rozumiem dlaczego moja siostra boi się ciemności i samotności każdego wieczoru.",
        "Tę książkę się czyta jednym tchem.",
        "On się często spóźnia na zajęcia.",
        "Kto pierwszy się zakocha, ten przegrywa.",
    ],
)
def test_no_gap_next_to_the_reflexive_particle_is_free_unless_a_new_phrase_follows(text: str) -> None:
    words: list[str] = text.split(" ")
    at: int = words.index("się")

    assert _gap(text, words[at - 1]).protected
    assert _gap(text, "się").protected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left"),
    [
        (
            "Zupełnie nie rozumiem dlaczego moja siostra boi\u00a0się ciemności i samotności każdego wieczoru.",
            "boi\u00a0się",
        ),
        ("Ciągle boi\u202fsię ciemności.", "boi\u202fsię"),
        ("Ciągle boi się\u00a0ciemności.", "boi"),
    ],
)
def test_reflexive_particle_at_the_edge_of_a_hard_spaced_group_keeps_the_gap_protected(text: str, left: str) -> None:
    gap: Gap = _gap(text, left)

    assert gap.kind == GapKind.REFLEXIVE
    assert gap.protected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left"),
    [
        ("Wszyscy – a zwłaszcza on – poszli.", "Wszyscy"),
        ("Wszyscy – a zwłaszcza on – poszli.", "on"),
        ("Myślę – powiedział cicho.", "Myślę"),
        ("Znam go ( to mój brat ) od lat.", "("),
        ("Znam go ( to mój brat ) od lat.", "brat"),
        ("Powiedział „ Tak ” i wyszedł.", "„"),
        ("Czekaj , proszę.", "Czekaj"),
        ("Czekaj ... proszę.", "Czekaj"),
    ],
)
def test_a_line_never_ends_on_an_opener_or_starts_on_a_closer_or_inner_dash(text: str, left: str) -> None:
    assert _gap(text, left).banned


@pytest.mark.unit
@pytest.mark.parametrize(("text", "left"), [("Ja… …nie wiem.", "Ja…"), ("Powiedział „Tak” i wyszedł.", "Powiedział")])
def test_a_word_with_attached_punctuation_may_start_a_line(text: str, left: str) -> None:
    assert not _gap(text, left).banned


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    ["- Kufer ze złotem? - Widać? Całe szczęście.", "-Kufer ze złotem? -Widać?", "— Kufer? — Widać."],
)
def test_dash_after_a_sentence_end_starts_a_new_speaker(text: str) -> None:
    words: list[str] = text.split(" ")
    turns: list[int] = [index for index, gap in enumerate(gaps(words), 1) if gap.turn]

    assert len(turns) == 1
    assert words[turns[0]][0] in "-—"


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    ["- Chodźmy już.", "- Wszyscy – a zwłaszcza on – poszli.", "Kosztuje 20–30 zł.", "Kato-senpai wróciła."],
)
def test_dash_that_does_not_follow_a_sentence_end_is_no_speaker_turn(text: str) -> None:
    assert not any(gap.turn for gap in gaps(text.split(" ")))


@pytest.mark.unit
@pytest.mark.parametrize("dash", ["-", "–", "—"])
def test_dash_like_the_opening_one_starts_a_new_speaker_without_a_sentence_end(dash: str) -> None:
    words: list[str] = [dash, "Tak", dash, "Nie."]

    assert [gap.turn for gap in gaps(words)] == [False, True, False]


@pytest.mark.unit
def test_every_hyphen_like_the_opening_one_before_a_capital_starts_a_new_speaker() -> None:
    words: list[str] = ["-", "Tak", "-", "Nie", "-", "Może."]

    assert [gap.turn for gap in gaps(words)] == [False, True, False, True, False]


@pytest.mark.unit
@pytest.mark.parametrize(
    "text", ["- Tak - nie wiem - mówię.", "Tak - Nie.", "- Tak – Nie.", "- Myślę - powiedział cicho."]
)
def test_aside_pair_or_other_dash_after_an_opening_dash_is_no_speaker_turn(text: str) -> None:
    assert not any(gap.turn for gap in gaps(text.split(" ")))


@pytest.mark.unit
def test_speaker_dash_stays_attached_to_the_first_word() -> None:
    words: list[str] = ["-", "Idziesz?", "-", "Za", "chwilę."]

    assert [gap.banned for gap in gaps(words)] == [True, False, True, False]


@pytest.mark.unit
def test_tiers_rank_every_class_and_protect_exactly_the_bound_pairs_of_the_spec() -> None:
    assert set(TIERS) == set(GapKind)
    assert {
        GapKind.NAME,
        GapKind.AFTER_PREPOSITION,
        GapKind.NEGATION,
        GapKind.REFLEXIVE,
        GapKind.NUMBER,
        GapKind.IDIOM,
        GapKind.AFTER_SINGLE_LETTER,
    } == PROTECTED_KINDS
    assert TIERS[GapKind.SENTENCE] < TIERS[GapKind.CLAUSE] < TIERS[GapKind.BEFORE_SUBORDINATOR]
    assert TIERS[GapKind.BEFORE_SUBORDINATOR] < TIERS[GapKind.PHRASE] < TIERS[GapKind.MODIFIER]
    assert TIERS[GapKind.MODIFIER] < TIERS[GapKind.NAME] < TIERS[GapKind.AFTER_SINGLE_LETTER]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left"),
    [
        ("Kosztuje 10 000 jenów.", "10"),
        ("Kosztuje 10 000 jenów.", "000"),
        ("Mam czterdzieści procent szans.", "czterdzieści"),
        ("Kąt wynosi sto trzydzieści osiem stopni.", "sto"),
        ("Kąt wynosi sto trzydzieści osiem stopni.", "osiem"),
        ("ponad tysiąc spółek zależnych", "tysiąc"),
    ],
)
def test_number_with_a_thousands_space_or_a_spelled_numeral_stays_with_what_follows(text: str, left: str) -> None:
    gap: Gap = _gap(text, left)

    assert gap.kind == GapKind.NUMBER
    assert gap.protected


@pytest.mark.unit
@pytest.mark.parametrize(("text", "left"), [("Wybrał jeden z graczy.", "jeden"), ("Mam dwa i pół.", "dwa")])
def test_numeral_before_a_preposition_or_conjunction_is_not_bound(text: str, left: str) -> None:
    assert _gap(text, left).kind != GapKind.NUMBER


@pytest.mark.unit
@pytest.mark.parametrize(("text", "left", "kind"), [("N-nie chcę iść.", "N-nie", GapKind.NEGATION)])
def test_stuttered_word_is_classified_like_the_word_it_repeats(text: str, left: str, kind: GapKind) -> None:
    assert _gap(text, left).kind == kind


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left", "kind"),
    [("Wiem, że wrócisz.", "że", GapKind.AFTER_OPENER), ("Kup np. chleb.", "np.", GapKind.ABBREVIATION)],
)
def test_opener_and_abbreviation_at_a_line_end_are_weighted_not_bound(text: str, left: str, kind: GapKind) -> None:
    gap: Gap = _gap(text, left)

    assert gap.kind == kind
    assert not gap.protected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "spans"),
    [
        ("W następnym odcinku „The Iceblade Sorcerer”:", ((3, 5),)),
        ("Co tam jest? „Szum rzecznego nurtu”... „Podwodny szmer”...", ((3, 5), (6, 7))),
        ('Zasada "Kto pierwszy, ten lepszy" to dogmat!', ((1, 4),)),
        ("Powiedział „Tak” i wyszedł.", ()),
        ("Bez cudzysłowu tutaj.", ()),
    ],
)
def test_quote_spans_cover_each_quotation_of_more_than_one_word(text: str, spans: tuple[tuple[int, int], ...]) -> None:
    assert quote_spans(text.split(" ")) == spans


@pytest.mark.unit
def test_list_markers_find_each_numbered_item() -> None:
    words: list[str] = ["(1)", "W", "SPRAWIE", "A", "(2)", "W", "SPRAWIE", "B", "(3)", "KONIEC"]

    assert list_markers(words) == (0, 4, 8)


@pytest.mark.unit
@pytest.mark.parametrize("words", [[], [""], ["Uciekaj!"]])
def test_text_without_neighbouring_words_has_no_gaps(words: list[str]) -> None:
    assert gaps(words) == ()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left"),
    [
        ("Akurat dzisiaj tak bardzo chciałem porozmawiać.", "tak"),
        ("Akurat dzisiaj tak bardzo chciałem porozmawiać.", "bardzo"),
        ("To jest zbyt długie zdanie.", "zbyt"),
        ("Zrobił to tak samo dobrze.", "samo"),
        ("Jest coraz zimniej.", "coraz"),
    ],
)
def test_degree_adverb_stays_with_the_word_it_grades(text: str, left: str) -> None:
    gap: Gap = _gap(text, left)

    assert gap.kind == GapKind.DEGREE
    assert not gap.protected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left"),
    [
        ("Akurat dzisiaj tak bardzo chciałem.", "dzisiaj"),
        ("Było tak w ogóle fajnie.", "tak"),
        ("Jest tak, jak mówisz.", "tak,"),
    ],
)
def test_degree_adverb_before_a_preposition_or_a_comma_or_after_another_word_is_no_degree_gap(
    text: str, left: str
) -> None:
    assert _gap(text, left).kind != GapKind.DEGREE

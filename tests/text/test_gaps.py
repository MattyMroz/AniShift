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
        ("Kupiłem chleb i masło.", "i", GapKind.AFTER_SINGLE_LETTER),
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
        ("Idziemy w końcu do domu.", "w", GapKind.AFTER_SINGLE_LETTER),
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
        GapKind.LABEL,
        GapKind.REPETITION,
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
        ("Jest tak że wyszedł.", "tak"),
    ],
)
def test_degree_adverb_before_an_idiom_a_conjunction_or_a_comma_or_after_another_word_is_no_degree_gap(
    text: str, left: str
) -> None:
    assert _gap(text, left).kind != GapKind.DEGREE


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left"),
    [("Nie możesz zjawiać się tak bez zapowiedzi.", "tak"), ("Mamy dużo pracy.", "dużo"), ("To sporo wody.", "sporo")],
)
def test_degree_or_quantity_adverb_stays_with_the_phrase_or_noun_it_grades(text: str, left: str) -> None:
    assert _gap(text, left).kind == GapKind.DEGREE


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left", "kind"),
    [
        ("Kupiłem chleb i masło.", "i", GapKind.AFTER_SINGLE_LETTER),
        ("Wróciłem, a potem zasnąłem.", "a", GapKind.AFTER_SINGLE_LETTER),
        ("Przyszedł dr. Kowalski.", "dr.", GapKind.NAME),
        ("Prof. Nowak przyszedł.", "Prof.", GapKind.NAME),
    ],
)
def test_gap_with_evidence_of_several_classes_takes_the_most_harmful_one(text: str, left: str, kind: GapKind) -> None:
    assert _gap(text, left).kind == kind


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left"),
    [
        ("Po drodze załatwiliśmy kilka zabłąkanych.", "kilka"),
        ("Przyszło wielu ludzi.", "wielu"),
        ("Mam dwoje dzieci.", "dwoje"),
        ("Zostało tyle jedzenia.", "tyle"),
    ],
)
def test_indefinite_or_collective_numeral_stays_with_the_noun_it_counts(text: str, left: str) -> None:
    gap: Gap = _gap(text, left)

    assert gap.kind == GapKind.NUMBER
    assert gap.protected


@pytest.mark.unit
def test_indefinite_numeral_before_a_preposition_is_not_bound() -> None:
    assert _gap("Kilka z nich zostało.", "Kilka").kind != GapKind.NUMBER


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left"),
    [("Nawet czujniki milczą.", "Nawet"), ("Właśnie ty to zrobiłeś.", "Właśnie"), ("Już idę.", "Już")],
)
def test_focus_particle_at_a_line_end_is_a_weighted_particle_gap(text: str, left: str) -> None:
    gap: Gap = _gap(text, left)

    assert gap.kind == GapKind.PARTICLE
    assert not gap.protected


@pytest.mark.unit
def test_focus_particle_followed_by_a_comma_is_a_clause_gap() -> None:
    assert _gap("Ja też, ale później.", "też,").kind == GapKind.CLAUSE


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left"),
    [
        ("A ja nie wyobrażam sobie siebie w roli.", "wyobrażam"),
        ("A ja nie wyobrażam sobie siebie w roli.", "sobie"),
        ("Zrobiłem to sam dla siebie.", "dla"),
        ("Rozmawiali ze sobą długo.", "ze"),
    ],
)
def test_reflexive_pronoun_is_bound_like_the_reflexive_particle(text: str, left: str) -> None:
    assert _gap(text, left).protected


@pytest.mark.unit
def test_reflexive_pronoun_before_a_new_phrase_leaves_the_gap_weighted() -> None:
    assert not _gap("Nie możemy pozwolić sobie na błędy.", "sobie").protected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left"),
    [
        ("Muszę trenować co najmniej godzinę.", "co"),
        ("To tak zwany geniusz.", "tak"),
        ("Przyszedł wraz z bratem.", "wraz"),
    ],
)
def test_fixed_phrase_from_the_dictionary_is_never_broken_inside(text: str, left: str) -> None:
    gap: Gap = _gap(text, left)

    assert gap.kind == GapKind.IDIOM
    assert gap.protected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "left"),
    [
        ("Podpiąłeś się tylko pod jej uczucia.", "jej"),
        ("Wrócił do naszych drzwi.", "naszych"),
        ("Zrobił to z punktu widzenia zarówno nas, jak i was.", "widzenia"),
        ("Czytam na temat wojny.", "temat"),
    ],
)
def test_prepositional_phrase_is_bound_up_to_its_noun_without_morphology(text: str, left: str) -> None:
    gap: Gap = _gap(text, left)

    assert gap.kind == GapKind.AFTER_PREPOSITION
    assert gap.protected


@pytest.mark.unit
@pytest.mark.parametrize(("text", "left"), [("Dałem jej książkę.", "jej"), ("Nie chcę o tym mówić.", "tym")])
def test_pronoun_outside_or_heading_a_prepositional_phrase_is_not_bound_to_the_next_word(text: str, left: str) -> None:
    assert _gap(text, left).kind != GapKind.AFTER_PREPOSITION


@pytest.mark.unit
def test_prepositional_phrase_through_agreeing_adjectives_is_a_weighted_gap() -> None:
    words: list[str] = ["Uczę", "się", "w", "tej", "prestiżowej", "akademii."]
    pairs: set[tuple[str, str]] = {("tej", "prestiżowej"), ("prestiżowej", "akademii.")}

    with_modifiers: tuple[Gap, ...] = gaps(words, lambda left, right: (left, right) in pairs)
    without: tuple[Gap, ...] = gaps(words)

    assert [gap.kind for gap in with_modifiers[3:]] == [GapKind.PREPOSITIONAL, GapKind.PREPOSITIONAL]
    assert not any(gap.protected for gap in with_modifiers[3:])
    assert without[4].kind != GapKind.PREPOSITIONAL


@pytest.mark.unit
def test_prepositional_phrase_binds_its_possessive_and_weighs_its_adjective() -> None:
    words: list[str] = ["Wrócił", "do", "naszego", "starego", "domu."]

    found: tuple[Gap, ...] = gaps(words, lambda left, right: (left, right) == ("starego", "domu."))

    assert found[2].kind == GapKind.AFTER_PREPOSITION
    assert found[3].kind == GapKind.PREPOSITIONAL


@pytest.mark.unit
def test_label_ending_in_a_colon_stays_with_its_numeric_value() -> None:
    gap: Gap = _gap("MEGAMIASTO NA ETOROFU WYS.: 4,5 KM", "WYS.:")

    assert gap.kind == GapKind.LABEL
    assert gap.protected


@pytest.mark.unit
def test_colon_before_a_word_is_a_clause_gap() -> None:
    assert _gap("Powiem ci jedno: idź.", "jedno:").kind == GapKind.CLAUSE


@pytest.mark.unit
def test_dash_between_repeated_words_joins_them() -> None:
    words: list[str] = ["STRZELNICA", "BAM", "-", "BAM", "-", "BAM"]
    found: tuple[Gap, ...] = gaps(words)

    assert [found[2].kind, found[4].kind] == [GapKind.REPETITION, GapKind.REPETITION]
    assert found[2].protected
    assert found[1].banned

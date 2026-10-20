from __future__ import annotations

from dataclasses import replace
from itertools import combinations

import pytest

from anishift.services.subtitles import layout as core
from anishift.services.subtitles.layout import (
    CHAR_WIDTH,
    DIALOGUE_MAX_WIDTH,
    HARMS,
    WEIGHTS,
    Field,
    Flag,
    Layout,
    Scale,
    candidates,
    chars_measure,
    dialogue_field,
    lay_out,
    ranked,
    sign_field,
)

_FLAT: dict[str, float] = dict.fromkeys(HARMS, 1.0)
_TEXTS: tuple[str, ...] = (
    "Jeśli to prawdziwa miłość, przyjmę ją — nawet za cenę wyrzucenia ze szkoły.",
    "- Idziesz już do domu? - Za chwilę, tylko się spakuję.",
    "Zapłaciłem aż 10\u00a0000 jenów za bilet do Tokio i wcale tego nie żałuję.",
    "W następnym odcinku „The Iceblade Sorcerer Shall Rule the World”:",
)


def _find(found: list[Layout], *lines: str) -> Layout:
    return next(layout for layout in found if layout.lines == lines)


@pytest.mark.unit
@pytest.mark.parametrize("text", _TEXTS)
def test_candidates_keep_every_word_whole_and_in_order(text: str) -> None:
    for layout in candidates(text, dialogue_field(), chars_measure):
        assert " ".join(layout.lines) == text


@pytest.mark.unit
def test_candidates_never_start_a_line_with_an_aside_dash() -> None:
    found: list[Layout] = candidates(_TEXTS[0], dialogue_field(), chars_measure)

    assert all(not line.startswith("—") for layout in found for line in layout.lines)


@pytest.mark.unit
def test_dialogue_gives_every_speaker_a_line_of_their_own() -> None:
    found: list[Layout] = candidates(_TEXTS[1], dialogue_field(), chars_measure)

    assert found
    assert all(any(line.startswith("- Za") for line in layout.lines) for layout in found)


@pytest.mark.unit
def test_speaker_line_of_one_word_is_no_orphan() -> None:
    layout: Layout = _find(
        candidates("–Tak. –Nie wiem, co robić.", dialogue_field(), chars_measure), "–Tak.", "–Nie wiem, co robić."
    )

    assert Flag.ORPHAN not in layout.flags


@pytest.mark.unit
def test_hard_space_is_never_a_cut() -> None:
    found: list[Layout] = candidates(_TEXTS[2], dialogue_field(), chars_measure)

    assert all(not line.endswith("10") and not line.startswith("000") for layout in found for line in layout.lines)


@pytest.mark.unit
def test_numbered_list_items_start_lines_when_each_fits() -> None:
    text: str = "(1) W SPRAWIE RELACJI (2) W SPRAWIE STUDIÓW (3) W SPRAWIE POCAŁUNKU"

    found: list[Layout] = candidates(text, dialogue_field(), chars_measure)

    assert [layout.lines for layout in found] == [
        ("(1) W SPRAWIE RELACJI", "(2) W SPRAWIE STUDIÓW", "(3) W SPRAWIE POCAŁUNKU")
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "upper", "lower", "flag"),
    [
        (
            "Za nic w świecie nie mogę do tego dopuścić.",
            "Za nic w świecie nie",
            "mogę do tego dopuścić.",
            Flag.BOUND_PAIR,
        ),
        (
            "Pewnie nawet nie dałaś z siebie wszystkiego, co?",
            "Pewnie nawet nie dałaś z siebie wszystkiego,",
            "co?",
            Flag.ORPHAN,
        ),
        (_TEXTS[3], "W następnym odcinku „The Iceblade", "Sorcerer Shall Rule the World”:", Flag.QUOTE),
    ],
)
def test_avoided_harms_raise_the_rescue_level(text: str, upper: str, lower: str, flag: Flag) -> None:
    layout: Layout = _find(candidates(text, dialogue_field(), chars_measure), upper, lower)

    assert flag in layout.flags
    assert layout.rescue[2] >= 1


@pytest.mark.unit
def test_cut_inside_a_quotation_wider_than_the_field_is_not_avoided() -> None:
    narrow: Field = Field(max_width=0.4, length_knots=(0.3, 0.35), count_chars=True)

    layout: Layout = _find(
        candidates(_TEXTS[3], narrow, chars_measure),
        "W następnym odcinku „The Iceblade",
        "Sorcerer Shall Rule the World”:",
    )

    assert Flag.QUOTE not in layout.flags


@pytest.mark.unit
def test_lowest_rescue_level_wins_over_any_weight() -> None:
    weights: dict[str, float] = {**_FLAT, "extra_line": 1000.0, "cut_negation": 1000.0}

    layout: Layout = lay_out("Za nic w świecie nie mogę.", dialogue_field(), chars_measure, weights)

    assert layout.rescue == (0, 0, 0)


@pytest.mark.unit
def test_word_wider_than_the_field_stays_whole_and_is_reported_outside() -> None:
    word: str = "x" * (int(DIALOGUE_MAX_WIDTH / CHAR_WIDTH) + 5)

    layout: Layout = lay_out(word, dialogue_field(), chars_measure, _FLAT)

    assert layout.lines == (word,)
    assert Flag.OUTSIDE in layout.flags


@pytest.mark.unit
def test_chars_measure_counts_graphemes_at_the_character_width() -> None:
    assert chars_measure("Zażółć", 0.5) == pytest.approx(6 * CHAR_WIDTH * 0.5)


@pytest.mark.unit
def test_length_harm_takes_the_larger_of_width_and_characters() -> None:
    text: str = "a" * 70

    layout: Layout = candidates(text, dialogue_field(), lambda line, fx: 0.01 * len(line) * fx)[0]

    assert layout.harms["length_wide"] == pytest.approx(70 * CHAR_WIDTH - 0.76)


@pytest.mark.unit
def test_two_line_imbalance_and_longer_top_follow_the_character_difference() -> None:
    layout: Layout = _find(
        candidates("Gdzie się podziała moja stara pianka? Przecież tu leżała.", dialogue_field(), chars_measure),
        "Gdzie się podziała moja stara pianka?",
        "Przecież tu leżała.",
    )

    assert layout.harms["top_longer"] == 18.0
    assert layout.harms["imbalance_6"] == 12.0
    assert layout.harms["imbalance_20"] == 0.0


@pytest.mark.unit
def test_agreement_is_read_only_with_morphology() -> None:
    text: str = "Czy cosplay na przyjęciu powitalnym jest konieczny?"
    upper: str = "Czy cosplay na przyjęciu"
    lower: str = "powitalnym jest konieczny?"

    with_morphology: Layout = _find(candidates(text, dialogue_field(), chars_measure), upper, lower)
    without: Layout = _find(candidates(text, dialogue_field(), chars_measure, morphology=False), upper, lower)

    assert with_morphology.harms["agreement"] == 1.0
    assert "agreement" not in without.harms


@pytest.mark.unit
def test_scalable_field_offers_the_scale_that_fits_the_comfortable_width() -> None:
    sign: Field = Field(max_width=1.0, comfort_width=0.4, scalable=True, letter_height=60.0)
    text: str = "Sekretarz Samorządu Uczniowskiego"

    found: list[Layout] = candidates(text, sign, chars_measure)
    fitting: float = int(0.4 / chars_measure(text, 1.0) * 100) / 100

    uniform: Layout = next(layout for layout in found if layout.scale == Scale(fitting, fitting))
    squeezed: Layout = next(layout for layout in found if layout.scale == Scale(fitting, 1.0))
    assert uniform.harms["shrink"] == pytest.approx(1 - fitting)
    assert uniform.harms["squeeze"] == 0.0
    assert squeezed.harms["squeeze"] == pytest.approx(1 - fitting)
    assert uniform.harms["over_comfort"] == 0.0


@pytest.mark.unit
def test_lines_taller_than_the_field_are_outside() -> None:
    band: Field = Field(max_width=1.0, scalable=True, height_lines=1.3)

    layout: Layout = _find(
        candidates("Miłość to wojna! Miłość to wojna!", band, chars_measure), "Miłość to wojna!", "Miłość to wojna!"
    )

    assert Flag.OUTSIDE in layout.flags


@pytest.mark.unit
def test_many_lines_come_from_dynamic_programming_within_the_field() -> None:
    narrow: Field = Field(max_width=0.2, preferred_lines=5, max_lines=8, rescue_lines=8)
    text: str = "Niniejsze dzieło jest fikcją i nie zachęcamy nikogo do picia alkoholu w żadnej postaci."

    layout: Layout = lay_out(text, narrow, chars_measure, _FLAT)

    assert len(layout.lines) > 3
    assert " ".join(layout.lines) == text
    assert all(chars_measure(line, layout.scale.fx) <= 0.2 for line in layout.lines)


@pytest.mark.unit
def test_dynamic_programming_keeps_forced_breaks() -> None:
    narrow: Field = Field(max_width=0.3, max_lines=6, rescue_lines=6, breaks=frozenset({1}))
    text: str = "Pierwsza pozycja oraz druga pozycja i trzecia pozycja listy tutaj"

    layout: Layout = lay_out(text, narrow, chars_measure, _FLAT)

    assert layout.lines[0] == "Pierwsza pozycja"


def _exhaustive(text: str, field: Field, weights: dict[str, float]) -> Layout:
    case: core._Case = core._case(text, field, chars_measure, morphology=True)
    allowed: list[int] = [index for index in range(len(case.gaps)) if core._allowed_cut(case, index)]
    found: list[Layout] = [
        core._evaluate(case, cuts, scale)
        for lines in range(1, field.rescue_lines + 1)
        for cuts in combinations(allowed, lines - 1)
        if case.forced <= set(cuts)
        for scale in core._scales(case, cuts)
    ]
    return min(found, key=lambda layout: (layout.rescue, layout.score(weights)))


_DISCLAIMER: str = "Niniejsze dzieło jest fikcją i nie zachęcamy nikogo do picia alkoholu w żadnej postaci ani formie."
_FICTION: str = (
    "Wszystkie postacie i wydarzenia przedstawione w tym filmie są fikcyjne, a podobieństwo jest przypadkowe."
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "width", "pyramid"),
    [
        (_FICTION, 0.2, False),
        (_FICTION, 0.25, False),
        (_FICTION, 0.3, False),
        (_DISCLAIMER, 0.35, True),
        (_DISCLAIMER, 0.4, True),
        (_DISCLAIMER, 0.45, True),
    ],
)
def test_dynamic_programming_finds_the_optimum_of_the_exhaustive_search(
    text: str, width: float, *, pyramid: bool
) -> None:
    field: Field = Field(
        max_width=width,
        preferred_lines=4,
        max_lines=6,
        rescue_lines=6,
        pyramid=pyramid,
        scalable=not pyramid,
        comfort_width=None if pyramid else width * 0.8,
        letter_height=0.0 if pyramid else 40.0,
    )
    weights: dict[str, float] = {**WEIGHTS, "top_longer": 1.0}

    programmed: Layout = lay_out(text, field, chars_measure, weights)
    exhaustive: Layout = _exhaustive(text, field, weights)

    assert programmed.rescue == exhaustive.rescue
    assert programmed.score(weights) == pytest.approx(exhaustive.score(weights))


@pytest.mark.unit
@pytest.mark.parametrize("text", ["- Tak. - Nie. - Może. - Jutro.", "(1) RAZ (2) DWA (3) TRZY (4) CZTERY"])
def test_forced_breaks_beyond_the_rescue_lines_are_joined_and_reported(text: str) -> None:
    layout: Layout = lay_out(text, dialogue_field(), chars_measure)

    assert " ".join(layout.lines) == text
    assert len(layout.lines) <= dialogue_field().rescue_lines
    assert Flag.JOINED in layout.flags


@pytest.mark.unit
def test_line_mixing_two_text_styles_is_avoided_while_a_cut_between_them_exists() -> None:
    field: Field = Field(max_width=1.0, max_lines=3, style_breaks=frozenset({1}))

    found: list[Layout] = candidates("Odcinek pierwszy: Chłopiec, który wygrał", field, chars_measure)
    mixed: Layout = _find(found, "Odcinek pierwszy: Chłopiec,", "który wygrał")
    best: Layout = lay_out("Odcinek pierwszy: Chłopiec, który wygrał", field, chars_measure, _FLAT)

    assert Flag.MIXED in mixed.flags
    assert best.lines[0] == "Odcinek pierwszy:"


@pytest.mark.unit
def test_dialogue_weighs_a_line_mixing_two_text_styles_instead_of_rescuing_it() -> None:
    field: Field = replace(dialogue_field(), style_breaks=frozenset({1}))

    layout: Layout = lay_out("Ja naprawdę cię kocham.", field, chars_measure, _FLAT)

    assert layout.lines == ("Ja naprawdę cię kocham.",)
    assert layout.harms["mixed_style"] == 1.0
    assert Flag.MIXED not in layout.flags


@pytest.mark.unit
def test_style_break_that_is_also_forced_is_never_reported_as_mixed() -> None:
    field: Field = Field(max_width=1.0, max_lines=3, breaks=frozenset({1}), style_breaks=frozenset({1}))

    found: list[Layout] = candidates("Odcinek pierwszy: Chłopiec, który wygrał", field, chars_measure)

    assert all(any(line.endswith("pierwszy:") for line in layout.lines) for layout in found)
    assert not any(Flag.MIXED in layout.flags for layout in found)


@pytest.mark.unit
def test_quotation_wider_than_a_comfortable_line_may_be_cut_without_a_rescue() -> None:
    found: list[Layout] = candidates(
        "„Cóż z ciebie za roszczeniowa gwiazda pierwszej wielkości”.", dialogue_field(), chars_measure
    )

    assert all(Flag.QUOTE not in layout.flags for layout in found)


@pytest.mark.unit
def test_ranked_layouts_start_with_the_chosen_one_and_are_ordered_by_rescue_and_harm() -> None:
    field: Field = sign_field(source_lines=2, comfort_width=0.2, letter_height=60.0)
    found: list[Layout] = ranked("Ma licencję na ceremonię herbacianą", field, chars_measure)
    keys: list[tuple[tuple[int, int, int], float]] = [(layout.rescue, layout.score(WEIGHTS)) for layout in found]
    assert found[0] == lay_out("Ma licencję na ceremonię herbacianą", field, chars_measure)
    assert keys == sorted(keys)


@pytest.mark.unit
def test_list_with_a_forced_break_after_every_word_keeps_one_word_per_line() -> None:
    words: list[str] = [f"{number}." for number in range(1, 41)]
    field: Field = replace(
        sign_field(source_lines=40, comfort_width=chars_measure("40.", 1.0), letter_height=60.0),
        breaks=frozenset(range(39)),
    )
    assert lay_out(" ".join(words), field, chars_measure).lines == tuple(words)

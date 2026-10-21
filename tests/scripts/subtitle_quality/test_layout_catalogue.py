from __future__ import annotations

from dataclasses import replace

import pytest

from anishift.services.subtitles.layout import Field, Layout, candidates, chars_measure, dialogue_field
from scripts.subtitle_quality.layout_catalogue import Accepted, CatalogueCase, faults, load, winner

_TEXT: str = "Czy cosplay na przyjęciu powitalnym jest naprawdę konieczny?"
_WIN: tuple[str, ...] = ("Czy cosplay na przyjęciu powitalnym", "jest naprawdę konieczny?")


def _case(**changes: object) -> CatalogueCase:
    base: CatalogueCase = CatalogueCase(
        id="x01",
        group="x01",
        source="test",
        text=_TEXT,
        field=dialogue_field(),
        measure=chars_measure,
        accept=(Accepted(_WIN),),
        rule=None,
        if_fits=False,
        soft=False,
        forbid=frozenset({("przyjęciu", "powitalnym")}),
        forbid_lines=frozenset(),
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def _found(case: CatalogueCase) -> list[Layout]:
    return candidates(case.text, case.field, case.measure)


@pytest.mark.unit
def test_faults_accept_a_listed_layout_and_name_a_forbidden_cut() -> None:
    case: CatalogueCase = _case()
    found: list[Layout] = _found(case)
    listed: Layout = next(layout for layout in found if layout.lines == _WIN)
    forbidden: Layout = next(layout for layout in found if layout.lines[0] == "Czy cosplay na przyjęciu")

    assert faults(case, listed, found) == []
    assert "forbidden cut przyjęciu|powitalnym" in faults(case, forbidden, found)


@pytest.mark.unit
def test_winner_is_the_candidate_of_the_first_acceptable_layout() -> None:
    case: CatalogueCase = _case()

    assert winner(case, _found(case)).lines == _WIN  # type: ignore[union-attr]


@pytest.mark.unit
def test_winner_is_none_when_only_a_rule_defines_the_acceptable_set() -> None:
    case: CatalogueCase = _case(accept=(), rule="any")

    assert winner(case, _found(case)) is None


@pytest.mark.unit
@pytest.mark.parametrize(("rule", "lines", "expected"), [("lines:2", 2, True), ("lines:2", 1, False), ("any", 1, True)])
def test_rules_judge_the_line_count(rule: str, lines: int, expected: bool) -> None:
    case: CatalogueCase = _case(accept=(), rule=rule, forbid=frozenset())
    found: list[Layout] = _found(case)
    layout: Layout = next(layout for layout in found if len(layout.lines) == lines)

    assert (faults(case, layout, found) == []) == expected


@pytest.mark.unit
def test_phrase_rule_takes_the_fewest_lines_cut_at_phrase_boundaries() -> None:
    case: CatalogueCase = _case(accept=(), rule="phrase", forbid=frozenset())
    found: list[Layout] = _found(case)
    clause: Layout = next(
        layout
        for layout in found
        if layout.lines == ("Czy cosplay", "na przyjęciu powitalnym jest naprawdę konieczny?")
    )
    three: Layout = next(layout for layout in found if len(layout.lines) == 3)

    assert faults(case, clause, found) == []
    assert faults(case, three, found) == ["not in the acceptable set"]


@pytest.mark.unit
def test_listed_layout_counts_only_when_it_fits_if_asked() -> None:
    narrow: Field = replace(dialogue_field(), max_width=0.45)
    case: CatalogueCase = _case(field=narrow, if_fits=True, rule="lines:3", forbid=frozenset())
    found: list[Layout] = _found(case)
    listed: Layout = next(layout for layout in found if layout.lines == _WIN)

    assert faults(case, listed, found) == ["not in the acceptable set"]


@pytest.mark.unit
def test_hourglass_rule_rejects_a_narrow_middle_line() -> None:
    case: CatalogueCase = _case(
        text="Odcinek drugi: Chłopiec, który jest magiem świata", accept=(), rule="no_hourglass", forbid=frozenset()
    )
    found: list[Layout] = _found(case)
    hourglass: Layout = next(
        layout for layout in found if layout.lines == ("Odcinek drugi: Chłopiec,", "który", "jest magiem świata")
    )

    assert faults(case, hourglass, found) == ["not in the acceptable set"]


@pytest.mark.integration
def test_catalogue_lists_layouts_the_core_can_produce() -> None:
    for case in load():
        found: list[Layout] = _found(case) if case.field.rescue_lines <= 3 else []
        for item in case.accept if found else ():
            assert any(layout.lines == item.lines for layout in found), (case.id, item.lines)

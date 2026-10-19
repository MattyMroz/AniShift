from __future__ import annotations

import pytest

from anishift.text.morphology import agrees


@pytest.mark.unit
@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("przyjęciu", "powitalnym"),
        ("romantyczne", "miejsce"),
        ("wszystkie", "ciągi"),
        ("kostium", "kąpielowy"),
        ("młodsza", "siostrzyczka."),
    ],
)
def test_agrees_adjective_and_noun_in_number_case_and_gender_either_order(left: str, right: str) -> None:
    assert agrees(left, right)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("stara", "dobra"),
        ("powitalnym", "jest"),
        ("przyjęciu,", "powitalnym"),
        ("ty", "trafiłaś"),
        ("młodego", "kobiety"),
        ("", "dom"),
    ],
)
def test_agrees_rejects_two_adjectives_a_verb_a_punctuated_left_word_or_a_mismatch(left: str, right: str) -> None:
    assert not agrees(left, right)

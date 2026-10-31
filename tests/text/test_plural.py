from __future__ import annotations

import pytest

from anishift.text.plural import plural


@pytest.mark.parametrize(
    ("count", "form"),
    [
        (0, "materiałów"),
        (1, "materiał"),
        (2, "materiały"),
        (4, "materiały"),
        (5, "materiałów"),
        (12, "materiałów"),
        (14, "materiałów"),
        (21, "materiałów"),
        (22, "materiały"),
        (112, "materiałów"),
        (124, "materiały"),
    ],
)
def test_plural_picks_the_polish_form_agreeing_with_the_count(count: int, form: str) -> None:
    assert plural(count, "materiał", "materiały", "materiałów") == form

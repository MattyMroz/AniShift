from __future__ import annotations

import pytest

from anishift.services.subtitles.layout import WEIGHTS, Layout, candidates, lay_out
from scripts.subtitle_quality.layout_catalogue import CatalogueCase, faults, load

_CASES: list[CatalogueCase] = load()


@pytest.mark.integration
@pytest.mark.parametrize("case", _CASES, ids=[case.id for case in _CASES])
def test_catalogue_case_gets_an_acceptable_layout_from_the_full_candidate_space(case: CatalogueCase) -> None:
    best: Layout = lay_out(case.text, case.field, case.measure, WEIGHTS)
    found: list[Layout] = [*candidates(case.text, case.field, case.measure), best]

    assert faults(case, best, found) == [], " / ".join(best.lines)

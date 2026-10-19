from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from anishift.services.subtitles.layout import HARMS
from anishift.text.gaps import TIERS, GapKind
from scripts.subtitle_quality.layout_calibrate import Fit, Pairs, conflict_set, conflict_sets, feasible, solve


def _row(**degrees: float) -> np.ndarray:
    return np.array([degrees.get(name, 0.0) for name in HARMS])


def _rows(cases: dict[str, list[np.ndarray]]) -> dict[str, tuple[Any, ...]]:
    return {case: (rows, []) for case, rows in cases.items()}


@pytest.mark.unit
def test_solve_meets_every_hard_row_with_the_margin() -> None:
    row: np.ndarray = _row(cut_phrase=1.0, cut_sentence=-1.0, extra_line=0.5)

    fit: Fit = solve(Pairs(hard=[("a", row)]))

    assert fit.weights is not None
    weights: np.ndarray = np.array([fit.weights[name] for name in HARMS])
    assert float(weights @ row) >= 1.0 - 1e-6


@pytest.mark.unit
def test_solve_keeps_cut_weights_positive_and_ordered_by_tier() -> None:
    fit: Fit = solve(Pairs(hard=[("a", _row(length_wide=1.0))]))

    assert fit.weights is not None
    for lower in GapKind:
        for upper in GapKind:
            if TIERS[upper] == TIERS[lower] + 1:
                assert fit.weights[f"cut_{upper.value}"] >= fit.weights[f"cut_{lower.value}"] - 1e-9
    assert min(fit.weights[f"cut_{kind.value}"] for kind in GapKind) > 0


@pytest.mark.unit
def test_contradictory_cases_are_infeasible_and_form_the_conflict_set() -> None:
    rows: dict[str, tuple[Any, ...]] = _rows(
        {
            "a": [_row(top_longer=1.0, length_wide=-1.0)],
            "b": [_row(top_longer=-1.0, length_wide=1.0)],
            "c": [_row(extra_line=1.0)],
        }
    )

    assert not feasible(rows, ["a", "b", "c"])
    assert conflict_set(rows, ["a", "b", "c"]) == ["a", "b"]
    assert conflict_sets(rows, ["a", "b", "c"]) == [["a", "b"]]


@pytest.mark.unit
def test_professional_rows_are_soft_and_report_their_violations() -> None:
    hard: np.ndarray = _row(top_longer=1.0)
    against: np.ndarray = _row(top_longer=-1.0)

    fit: Fit = solve(Pairs(hard=[("a", hard)], professional=[against]))

    assert fit.weights is not None
    assert fit.violated_professional == 1

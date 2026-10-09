from __future__ import annotations

from typing import Any, Final

import pytest
from reference_support import (
    BASELINE_PAIRS,
    CASES,
    GATE,
    Automatic,
    Manual,
    automatic,
    baseline,
    case_coverage,
    coverage,
    diagnostic_coverage,
    expectations,
    manual,
    proven_gone,
    research_cases,
)

from anishift.application.release_quality import PolishClass
from anishift.application.subscription_choice import NO_POLISH_AFTER_WAIT, Blocker, ChoiceCandidate, ChoiceDecision
from anishift.application.subscription_targets import PolishState

pytestmark = pytest.mark.integration

type Outcome = tuple[str, str | None, PolishState | None, bool, str | None]

_SEASON_CONFLICT_WITHDRAWN: Final[str] = (
    "a1-recon.md §8: O7 withdrawn, an explicit other season in the name stays insufficient instead of a conflict"
)
_DOCUMENTED: Final[dict[str, str]] = {
    "140960-12": f"{_SEASON_CONFLICT_WITHDRAWN} and the completion queue",
    "154587-1": f"{_SEASON_CONFLICT_WITHDRAWN} and the completion queue",
    "204389-1": _SEASON_CONFLICT_WITHDRAWN,
}
_REASONS: Final[tuple[tuple[str, str], ...]] = (
    ("przed emisją", "not_due"),
    ("brak pewnego wydania", Blocker.NO_ADMISSIBLE.value),
    ("PL: nieznane", "waiting"),
    ("PL: zwykle jest", "waiting"),
    ("PL: brak w poprzednim", "without_polish"),
    ("pierwszy dopuszczalny ma PL", "polish"),
)
_LOSS_CASE: Final[str] = "210031-13"
_KNABEN: Final[frozenset[str]] = frozenset({"api.knaben.org"})
_HASH_A: Final[str] = "a" * 40
_HASH_B: Final[str] = "b" * 40
_HASH_C: Final[str] = "c" * 40
_TOP3_CASES: Final[list[object]] = [
    pytest.param(case, marks=[pytest.mark.xfail(strict=True, reason=_DOCUMENTED[case])] if case in _DOCUMENTED else [])
    for case in CASES
]


def _expected(entry: dict[str, Any]) -> Outcome:
    chosen: dict[str, Any] = entry["automatic"]
    after: dict[str, Any] = entry.get("after_wait", {})
    state: str = next(state for marker, state in _REASONS if marker in chosen["reason"])
    recorded: str | None = entry["proposal"]["automatic"].get("polish_history")
    return (
        state,
        chosen["hash"] or after.get("hash"),
        None if recorded is None else PolishState(recorded.lower()),
        "po metadanych" in chosen["reason"] + after.get("reason", ""),
        NO_POLISH_AFTER_WAIT if "brak PL po" in after.get("reason", "") else None,
    )


def _actual(result: Automatic) -> Outcome:
    decision: ChoiceDecision | None = result.decision
    if decision is None:
        return "not_due", None, None, False, None
    if decision.blocker is Blocker.WAITING_POLISH:
        later: ChoiceDecision | None = result.after_wait
        after: ChoiceCandidate | None = None if later is None else later.candidate
        return (
            "waiting",
            None if after is None else after.info_hash,
            result.history,
            after is not None and after.after_metadata,
            None if later is None else later.reason,
        )
    if decision.candidate is None:
        return decision.blocker.value, None, None, False, None
    state: str = "polish" if decision.candidate.traits.polish is PolishClass.POLISH else "without_polish"
    return state, decision.candidate.info_hash, result.history, decision.candidate.after_metadata, None


@pytest.mark.parametrize("case", _TOP3_CASES)
def test_reference_manual_top3(case: str) -> None:
    assert manual(case).top3() == expectations()[case]["top3"]


@pytest.mark.parametrize("case", CASES)
def test_reference_automatic_choice(case: str) -> None:
    assert _actual(automatic(case)) == _expected(expectations()[case])


@pytest.mark.parametrize("case", CASES)
def test_reference_replay_answers_every_manual_request(case: str) -> None:
    assert manual(case).misses == ()


@pytest.mark.parametrize("case", CASES)
def test_reference_replay_answers_every_subscription_request(case: str) -> None:
    assert automatic(case).misses == ()


def test_reference_expectations_cover_every_case_confirmed_by_owner() -> None:
    entries: dict[str, Any] = expectations()
    assert sorted(entries) == list(CASES)
    assert all(entry["confirmed_by_owner"] is True for entry in entries.values())


@pytest.mark.parametrize("mode", ["manual", "subscription"])
def test_reference_coverage_gate_against_640(mode: str) -> None:
    found: dict[str, frozenset[str]] = {
        case: manual(case).hashes() if mode == "manual" else automatic(case).hashes() for case in research_cases()
    }
    assert sum(len(baseline()[case]["union"]) for case in found) == BASELINE_PAIRS
    assert coverage(baseline(), found) >= GATE
    assert diagnostic_coverage(baseline(), found) >= coverage(baseline(), found)


def test_coverage_diagnostic_excludes_only_proven_gone() -> None:
    pairs: dict[str, Any] = {
        "1-1": {
            "union": [_HASH_A, _HASH_B, _HASH_C],
            "missing": {
                _HASH_A: {"status": "gone", "research_sources": ["knaben"]},
                _HASH_B: {"status": "gone", "research_sources": ["knaben", "nyaa"]},
                _HASH_C: {"status": "unverified", "research_sources": ["knaben"]},
            },
            "requery": {"knaben": {"complete": True}, "nyaa": {"complete": False}},
        }
    }
    found: dict[str, frozenset[str]] = {"1-1": frozenset()}

    assert proven_gone(pairs, "1-1") == {_HASH_A}
    assert diagnostic_coverage(pairs, {"1-1": frozenset({_HASH_B})}) == 1 / (BASELINE_PAIRS - 1)
    assert diagnostic_coverage(pairs, found) == 0.0


def test_coverage_detects_loss_with_same_top3() -> None:
    full: Manual = manual(_LOSS_CASE)
    without_knaben: Manual = manual(_LOSS_CASE, _KNABEN)

    assert without_knaben.top3() == full.top3()
    assert case_coverage(baseline(), _LOSS_CASE, full.hashes()) >= GATE
    assert case_coverage(baseline(), _LOSS_CASE, without_knaben.hashes()) < GATE

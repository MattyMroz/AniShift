from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

import pytest

from anishift.application import episode_confidence as model
from anishift.application.episode_confidence import confidence, features
from anishift.application.episode_identity import (
    IdentityAssessment,
    IdentityEvidence,
    IdentityVerdict,
    classify,
    identity_evidence,
)

_FIXTURES: Final[Path] = Path(__file__).parents[1] / "fixtures" / "acquisition"
_CASES: Final[list[dict[str, Any]]] = json.loads((_FIXTURES / "confidence-cases.json").read_text(encoding="utf-8"))[
    "cases"
]


def _evidence(case: dict[str, Any]) -> IdentityEvidence:
    return identity_evidence(case["target"], case["candidate"])


def _expected_evidence(case: dict[str, Any]) -> IdentityEvidence:
    values: dict[str, Any] = dict(case["evidence"])
    assessment: dict[str, str] = values.pop("assessment")
    values["assessment"] = IdentityAssessment(IdentityVerdict(assessment["verdict"]), assessment["reason"])
    values["number"] = Decimal(values["number"]) if values["number"] is not None else None
    return IdentityEvidence(**values)


@pytest.mark.unit
def test_model_matches_research_json() -> None:
    raw: bytes = (_FIXTURES / "confidence-model.json").read_bytes()
    frozen: dict[str, Any] = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == "03f61e3c27c193c3735c549dd6512bac5e843f0a44608fd9c4a175b10d29633a"
    assert frozen["weights"] == model._WEIGHTS
    assert frozen["platt"]["intercept"] == model._PLATT_INTERCEPT
    assert frozen["platt"]["logit"] == model._PLATT_LOGIT
    assert frozen["selected_threshold"] == 0.99


@pytest.mark.unit
@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["id"])
def test_features_match_research_cases(case: dict[str, Any]) -> None:
    evidence: IdentityEvidence = _evidence(case)
    assert evidence == _expected_evidence(case)
    assert features(evidence) == pytest.approx(case["features"], abs=1e-9, rel=0)
    assert confidence(evidence) == pytest.approx(case["confidence"], abs=1e-9, rel=0)
    assert classify(case["target"], case["candidate"]) == evidence.assessment


@pytest.mark.unit
def test_features_filename_differs_from_path() -> None:
    evidence: IdentityEvidence = _evidence(_CASES[0])
    assert evidence.selected != evidence.path.rsplit("/", 1)[-1]
    assert features(evidence)["mapped_agrees"] == 1.0
    assert features(evidence)["path_present"] == 1.0


@pytest.mark.unit
def test_features_path_without_filename() -> None:
    evidence: IdentityEvidence = _evidence(_CASES[1])
    assert evidence.selected == evidence.path.rsplit("/", 1)[-1]
    assert features(evidence)["selected_present"] == 1.0


@pytest.mark.unit
def test_features_release_only() -> None:
    values: dict[str, float] = features(_evidence(_CASES[2]))
    assert "selected_present" not in values
    assert "selected_video_extension" not in values
    assert "path_present" not in values
    assert values["mapped_agrees"] == 1.0


@pytest.mark.unit
def test_confidence_does_not_apply_research_vetoes() -> None:
    evidence: IdentityEvidence = _evidence(_CASES[5])
    assert evidence.assessment.verdict is IdentityVerdict.MISMATCH
    assert confidence(evidence) == pytest.approx(0.8153862014939198, abs=1e-9, rel=0)


@pytest.mark.unit
@pytest.mark.parametrize(("words", "expected"), [(0, None), (1, 0.05), (20, 1.0), (25, 1.0)])
def test_residual_words_research_scaling(words: int, expected: float | None) -> None:
    evidence: IdentityEvidence = replace(_evidence(_CASES[0]), residual=" ".join(["word"] * words))
    assert features(evidence).get("residual_words") == expected


@pytest.mark.unit
def test_unknown_reason_has_no_weight() -> None:
    evidence: IdentityEvidence = _evidence(_CASES[0])
    first: IdentityEvidence = replace(evidence, assessment=IdentityAssessment(IdentityVerdict.MATCH, "New reason"))
    second: IdentityEvidence = replace(evidence, assessment=IdentityAssessment(IdentityVerdict.MATCH, "Other reason"))
    assert confidence(first) == confidence(second)


@pytest.mark.unit
@pytest.mark.parametrize(("mode", "agrees"), [("mapped", True), ("plain", False)])
def test_season_agreement_uses_parsed_numbering_namespace(mode: str, agrees: bool) -> None:
    evidence: IdentityEvidence = replace(_evidence(_CASES[0]), mode=mode, season=2, target_season=2, named_season=1)
    assert ("season_agrees" in features(evidence)) is agrees


@pytest.mark.unit
def test_research_cases_cover_every_weighted_feature_except_reasons() -> None:
    required: set[str] = {key for key in model._WEIGHTS if not key.startswith("reason=")}
    expected: set[str] = {key for case in _CASES for key, value in case["features"].items() if value}
    observed: set[str] = {key for case in _CASES for key, value in features(_evidence(case)).items() if value}
    assert required <= expected
    assert required <= observed

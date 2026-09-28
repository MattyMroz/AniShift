from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import pytest

from anishift.application.episode_identity import REASONS, IdentityAssessment, IdentityVerdict, classify, classify_many

pytestmark = pytest.mark.unit

_FIXTURES: Final[Path] = Path(__file__).parents[1] / "fixtures/acquisition"


def test_identity_golden_and_historical_fixture_match_frozen_assessments() -> None:
    golden: dict[str, Any] = json.loads((_FIXTURES / "identity-golden.json").read_text(encoding="utf-8"))
    historical: list[dict[str, Any]] = json.loads((_FIXTURES / "identity-231.json").read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = [
        {**record, "target": golden["targets"][record["target_index"]]} for record in golden["records"]
    ]
    assert len(records) == 400
    assert len(historical) == len(golden["identity_231_expected"]) == 231
    groups: dict[str, list[dict[str, Any]]] = {}
    combined: list[dict[str, Any]] = [
        *records,
        *(
            {**row["state"], **expected}
            for row, expected in zip(historical, golden["identity_231_expected"], strict=True)
        ),
    ]
    for record in combined:
        expected: IdentityAssessment = IdentityAssessment(IdentityVerdict(record["verdict"]), record["reason"])
        assert classify(record["target"], record["candidate"]) == expected
        assert expected.reason in REASONS
        key: str = json.dumps(record["target"], sort_keys=True, ensure_ascii=False)
        groups.setdefault(key, []).append(record)
    for group in groups.values():
        assert classify_many(group[0]["target"], [row["candidate"] for row in group]) == tuple(
            IdentityAssessment(IdentityVerdict(row["verdict"]), row["reason"]) for row in group
        )


def test_identity_golden_wrong_matches_have_exact_documented_exceptions() -> None:
    path: Path = _FIXTURES / "identity-golden.json"
    golden: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    assert path.stat().st_size <= 500 * 1024
    assert golden["seed"] == 20260929
    exceptions: dict[int, str] = {entry["index"]: entry["cause"] for entry in golden["known_wrong_matches"]}
    wrong: set[int] = set()
    for index, record in enumerate(golden["records"]):
        assert set(record) == {"target_index", "candidate", "label", "verdict", "reason", "shape"}
        assert set(record["candidate"]) == {"release", "path", "filename"}
        target: dict[str, Any] = golden["targets"][record["target_index"]]
        if record["label"] == "błędny" and classify(target, record["candidate"]).verdict is IdentityVerdict.MATCH:
            wrong.add(index)
    assert wrong == set(exceptions)
    assert all(cause.startswith("H2:") for cause in exceptions.values())


def test_identity_golden_covers_every_working_reason_and_stratum_with_lossless_targets() -> None:
    golden: dict[str, Any] = json.loads((_FIXTURES / "identity-golden.json").read_text(encoding="utf-8"))
    targets: list[dict[str, Any]] = golden["targets"]
    records: list[dict[str, Any]] = golden["records"]
    assert len(golden["working_reasons"]) == 37
    assert {record["reason"] for record in records} == set(golden["working_reasons"])
    assert len(golden["working_strata"]) == 50
    assert {(targets[record["target_index"]]["type"], record["verdict"], record["shape"]) for record in records} == {
        tuple(stratum) for stratum in golden["working_strata"]
    }
    assert all(type(record["target_index"]) is int for record in records)
    assert {record["target_index"] for record in records} == set(range(len(targets)))
    assert len({json.dumps(target, sort_keys=True) for target in targets}) == len(targets)
    assert all(
        set(target)
        == {
            "absolute",
            "aliases",
            "episode",
            "episode_title",
            "local_episode",
            "other_episode_titles",
            "other_series",
            "season",
            "type",
        }
        for target in targets
    )
    assert max(len(target["other_episode_titles"]) for target in targets) == 1836

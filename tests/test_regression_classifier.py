import json
from pathlib import Path
from typing import Final

import pytest

from anishift.services.subtitles.classifier import Category, classify_styles
from anishift.services.subtitles.service import load_subtitles

DATASET: Final[Path] = Path(__file__).resolve().parents[1].parent / "mm_avh_working_space" / "temp"
"""Local mm_avh regression dataset."""

_KNOWN_MISSED_DIALOG: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("140___Fuji__Kimi_to_Koete_Koi_ni_Naru_-_03__1080p_.mkv.ass", "Znaki"),
        ("141___Fuji__Kimi_to_Koete_Koi_ni_Naru_-_04__1080p_.mkv.ass", "Znaki"),
    }
)
"""The two style-granularity misses measured at port time (Fuji 3-4)."""


def test_classifier_regression_matches_mm_avh_baseline() -> None:
    ground_truth = DATASET / "ground_truth"
    dataset_ass = DATASET / "dataset_ass"
    if not ground_truth.is_dir() or not dataset_ass.is_dir():
        pytest.skip("mm_avh regression dataset is not available")
    truth: dict[str, dict[str, dict[str, object]]] = {}
    for path in ground_truth.glob("pack_*.json"):
        truth.update(json.loads(path.read_text(encoding="utf-8")))
    correct = 0
    total = 0
    missed: set[tuple[str, str]] = set()
    for filename, styles in truth.items():
        path = dataset_ass / filename
        if not path.is_file():
            continue
        verdicts = {verdict.style: verdict for verdict in classify_styles(load_subtitles(path))}
        for style, raw_expected in styles.items():
            expected = raw_expected
            if expected["uncertain"] is True or style not in verdicts:
                continue
            want_dialog = expected["cat"] == "DIALOG"
            got_dialog = verdicts[style].category in (Category.DIALOG, Category.UNCERTAIN)
            total += 1
            correct += want_dialog == got_dialog
            if want_dialog and not got_dialog:
                missed.add((filename, style))
    assert total > 0
    assert correct / total >= 0.9586
    assert missed <= _KNOWN_MISSED_DIALOG, f"new missed dialog: {sorted(missed)}"

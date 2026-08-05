from __future__ import annotations

from pathlib import Path

import pytest

from anishift.services.composition.errors import CompositionValidationError
from anishift.services.composition.probe import validate_merged


def test_validate_merged_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CompositionValidationError, match="missing or empty"):
        validate_merged(tmp_path / "absent.mkv", expected_track_names=("Napisy PL",))


def test_validate_merged_rejects_empty_file(tmp_path: Path) -> None:
    target = tmp_path / "empty.mkv"
    target.write_bytes(b"")

    with pytest.raises(CompositionValidationError, match="missing or empty"):
        validate_merged(target, expected_track_names=("Napisy PL",))

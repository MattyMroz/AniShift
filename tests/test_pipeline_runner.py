"""Tests for pipeline discovery and per-file isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from anishift.bootstrap import AppContext
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import ErrorCode, ErrorContext
from anishift.pipeline import discover_inputs, run_pipeline
from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.types import MediaInfo


def _context(root: Path) -> AppContext:
    """Build a minimal test context."""
    return AppContext(Settings(), UserSettings(), root)


def test_discover_inputs_uses_top_level_natural_order(tmp_path: Path) -> None:
    (tmp_path / "episode 10.mkv").touch()
    (tmp_path / "episode 2.mkv").touch()
    (tmp_path / "episode.displayed.ass").touch()
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "episode 1.mkv").touch()

    assert [path.name for path in discover_inputs(tmp_path)] == ["episode 2.mkv", "episode 10.mkv"]


def test_run_pipeline_isolates_identify_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bad = tmp_path / "bad.mkv"
    good = tmp_path / "good.mkv"
    bad.touch()
    good.touch()

    def fake_identify(path: Path) -> MediaInfo:
        if path == bad:
            context = ErrorContext(code=ErrorCode.EXTRACTION_FAILED, message="bad input")
            raise ExtractionError(context=context)
        return MediaInfo(path, ())

    monkeypatch.setattr("anishift.pipeline.runner.identify", fake_identify)
    report = run_pipeline(_context(tmp_path))

    assert [outcome.source for outcome in report.outcomes] == [bad, good]
    assert report.outcomes[0].status == "failed"
    assert report.outcomes[0].failure is not None
    assert report.outcomes[1].status == "done"

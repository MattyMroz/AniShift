from __future__ import annotations

from decimal import Decimal
from typing import Final

import pytest

from anishift.services.torrents.names import parse_release_name
from anishift.services.torrents.types import ReleaseName

_CASES: Final[tuple[tuple[str, ReleaseName], ...]] = (
    (
        "[SubsPlease] Neko to Ryuu - 10 (1080p) [B565394A].mkv",
        ReleaseName(
            group="SubsPlease",
            series="Neko to Ryuu",
            episode=Decimal("10"),
            season=None,
            resolution=1080,
            batch=False,
            version=None,
        ),
    ),
    (
        "[SubsPlease] Tensei Shitara Slime Datta Ken S4 - 21 (1080p) [9057F2E5].mkv",
        ReleaseName(
            group="SubsPlease",
            series="Tensei Shitara Slime Datta Ken S4",
            episode=Decimal("21"),
            season=None,
            resolution=1080,
            batch=False,
            version=None,
        ),
    ),
    (
        "[DKB] Neko to Ryuu - S01E11 [1080p][HEVC x265 10bit][Multi-Subs][weekly]",
        ReleaseName(
            group="DKB",
            series="Neko to Ryuu",
            episode=Decimal("11"),
            season=1,
            resolution=1080,
            batch=False,
            version=None,
        ),
    ),
    (
        "[Judas] Neko to Ryuu (The Cat and the Dragon) - S01E11 [1080p][HEVC x265 10bit][Multi-Subs] (Weekly)",
        ReleaseName(
            group="Judas",
            series="Neko to Ryuu (The Cat and the Dragon)",
            episode=Decimal("11"),
            season=1,
            resolution=1080,
            batch=False,
            version=None,
        ),
    ),
    (
        "[SubsPlease] Oshi no Ko S3 (01-11) (1080p) [Batch]",
        ReleaseName(
            group="SubsPlease",
            series="Oshi no Ko S3",
            episode=None,
            season=None,
            resolution=1080,
            batch=True,
            version=None,
        ),
    ),
    (
        "[Group] Title - 07.5 (1080p)",
        ReleaseName(
            group="Group",
            series="Title",
            episode=Decimal("7.5"),
            season=None,
            resolution=1080,
            batch=False,
            version=None,
        ),
    ),
    (
        "[Group] Title - 05v2 (720p)",
        ReleaseName(
            group="Group",
            series="Title",
            episode=Decimal("5"),
            season=None,
            resolution=720,
            batch=False,
            version=2,
        ),
    ),
    (
        "[Group] Title - 05 (2160p)",
        ReleaseName(
            group="Group",
            series="Title",
            episode=Decimal("5"),
            season=None,
            resolution=2160,
            batch=False,
            version=None,
        ),
    ),
    (
        "[Group] Title - 05",
        ReleaseName(
            group="Group",
            series="Title",
            episode=Decimal("5"),
            season=None,
            resolution=None,
            batch=False,
            version=None,
        ),
    ),
    (
        "Some random upload name.mkv",
        ReleaseName(
            group=None,
            series="Some random upload name",
            episode=None,
            season=None,
            resolution=None,
            batch=False,
            version=None,
        ),
    ),
    (
        "[Erai-raws] Title - 03 [1080p][Multiple Subtitle] [ENG][POR-BR]",
        ReleaseName(
            group="Erai-raws",
            series="Title",
            episode=Decimal("3"),
            season=None,
            resolution=1080,
            batch=False,
            version=None,
        ),
    ),
)


@pytest.mark.parametrize(("title", "expected"), _CASES, ids=[title for title, _ in _CASES])
def test_parse_release_name_recognizes_known_title_patterns(title: str, expected: ReleaseName) -> None:
    assert parse_release_name(title) == expected


def test_parse_release_name_collapses_repeated_whitespace() -> None:
    parsed = parse_release_name("[Group]   Title   -   05   (1080p)")
    assert parsed.series == "Title"
    assert parsed.episode == Decimal("5")

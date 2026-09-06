from __future__ import annotations

from decimal import Decimal
from typing import Final

import pytest

from anishift.services.torrents.names import base_title, parse_release_name, season_hint, strip_season, title_forms
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
            subtitle_language="multi",
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
            subtitle_language="multi",
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
    (
        "[Erai-raws] Mushoku Tensei III: Isekai Ittara Honki Dasu - 10 [1080p CR WEB-DL AVC AAC][MultiSub][183A368D]",
        ReleaseName(
            group="Erai-raws",
            series="Mushoku Tensei III: Isekai Ittara Honki Dasu",
            episode=Decimal("10"),
            season=None,
            resolution=1080,
            batch=False,
            version=None,
            subtitle_language="multi",
        ),
    ),
    (
        "[ToonsHub] Mushoku Tensei Jobless Reincarnation S03E10 1080p BILI WEB-DL AAC2.0 H.265",
        ReleaseName(
            group="ToonsHub",
            series="Mushoku Tensei Jobless Reincarnation",
            episode=Decimal("10"),
            season=3,
            resolution=1080,
            batch=False,
            version=None,
        ),
    ),
    (
        "[Cytox] Mushoku Tensei Jobless Reincarnation 2021 S03E08 1080p CR WEB-DL Dual-Audio DDP 2.0 H.264",
        ReleaseName(
            group="Cytox",
            series="Mushoku Tensei Jobless Reincarnation",
            episode=Decimal("8"),
            season=3,
            resolution=1080,
            batch=False,
            version=None,
        ),
    ),
    (
        "Mushoku Tensei Jobless Reincarnation S03E07 Phase Four 1080p CR WEB-DL DUAL AAC2.0 H.264-VARYG",
        ReleaseName(
            group="VARYG",
            series="Mushoku Tensei Jobless Reincarnation",
            episode=Decimal("7"),
            season=3,
            resolution=1080,
            batch=False,
            version=None,
        ),
    ),
    (
        "Mushoku Tensei Jobless Reincarnation S03E10 SUBFRENCH 1080p CR WEB-DL AAC2.0 "
        "H.264-Tsundere-Raws (READNFO, VOSTFR, Mushoku Tensei)",
        ReleaseName(
            group="Tsundere-Raws",
            series="Mushoku Tensei Jobless Reincarnation",
            episode=Decimal("10"),
            season=3,
            resolution=1080,
            batch=False,
            version=None,
            subtitle_language="fr",
        ),
    ),
    (
        "Solo.Leveling.Arise.from.the.Shadow.S02.MULTi.1080p.WEBRiP.x265-T3KASHi",
        ReleaseName(
            group="T3KASHi",
            series="Solo Leveling Arise from the Shadow",
            episode=None,
            season=2,
            resolution=1080,
            batch=False,
            version=None,
            subtitle_language="multi",
        ),
    ),
    (
        "[Xspitfire911] Ore dake Level Up na Ken - Solo Leveling S01 + S02 BDRIP 1080p X265 10bit VOSTFR",
        ReleaseName(
            group="Xspitfire911",
            series="Ore dake Level Up na Ken",
            episode=None,
            season=2,
            resolution=1080,
            batch=False,
            version=None,
            subtitle_language="fr",
        ),
    ),
    (
        "[Breeze] Mushoku Tensei S03E08",
        ReleaseName(
            group="Breeze",
            series="Mushoku Tensei",
            episode=Decimal("8"),
            season=3,
            resolution=None,
            batch=False,
            version=None,
        ),
    ),
    (
        "[Yameii] Solo Leveling - S02E13 [English Dub] [CR WEB-DL 1080p] [93CA9D52] "
        "(Ore dake Level Up na Ken: Arise from the Shadow | Season 2 | S2)",
        ReleaseName(
            group="Yameii",
            series="Solo Leveling",
            episode=Decimal("13"),
            season=2,
            resolution=1080,
            batch=False,
            version=None,
            dubbed=True,
        ),
    ),
    (
        "[Feibanyama] Mushoku Tensei Jobless Reincarnation S03E09",
        ReleaseName(
            group="Feibanyama",
            series="Mushoku Tensei Jobless Reincarnation",
            episode=Decimal("9"),
            season=3,
            resolution=None,
            batch=False,
            version=None,
        ),
    ),
    (
        "[Judas] Ore dake Level Up na Ken (Solo Leveling) (Season 02) [1080p][HEVC x265 10bit]"
        "[Dual-Audio][Multi-Subs] (Batch)",
        ReleaseName(
            group="Judas",
            series="Ore dake Level Up na Ken",
            episode=None,
            season=None,
            resolution=1080,
            batch=True,
            version=None,
            subtitle_language="multi",
        ),
    ),
    (
        "Solo Leveling S02E13 MULTi 1080p WEB x264 AAC -Tsundere-Raws (CR) "
        "(VF, FRENCH, VOSTFR, Multi-Audio, Ore dake Level Up na Ken)",
        ReleaseName(
            group="Tsundere-Raws",
            series="Solo Leveling",
            episode=Decimal("13"),
            season=2,
            resolution=1080,
            batch=False,
            version=None,
            subtitle_language="fr",
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


def test_parse_release_name_reads_a_season_pack_as_a_pack_without_an_episode() -> None:
    parsed = parse_release_name("Solo.Leveling.Arise.from.the.Shadow.S02.MULTi.1080p.WEBRiP.x265-T3KASHi")
    assert parsed.is_pack is True


def test_parse_release_name_reads_a_single_episode_as_no_pack() -> None:
    assert parse_release_name("[Breeze] Mushoku Tensei S03E08").is_pack is False


def test_parse_release_name_does_not_call_dual_audio_dubbed() -> None:
    title = "[Cytox] Mushoku Tensei Jobless Reincarnation 2021 S03E08 1080p CR WEB-DL Dual-Audio DDP 2.0 H.264"
    assert parse_release_name(title).dubbed is False


_SEASON_CASES: Final[tuple[tuple[str, int | None, str], ...]] = (
    ("Mushoku Tensei S3", 3, "Mushoku Tensei"),
    ("Sousou no Frieren 2nd Season", 2, "Sousou no Frieren"),
    ("Solo Leveling Season 2", 2, "Solo Leveling"),
    ("Re:Zero 3rd Season", 3, "Re:Zero"),
    ("Mushoku Tensei III: Isekai Ittara Honki Dasu", 3, "Mushoku Tensei : Isekai Ittara Honki Dasu"),
    ("Mushoku Tensei II: Isekai Ittara Honki Dasu Part 2", 2, "Mushoku Tensei : Isekai Ittara Honki Dasu Part 2"),
    ("Solo Leveling", None, "Solo Leveling"),
    ("Lv999 no Murabito", None, "Lv999 no Murabito"),
    ("Solo Leveling S01 + S02", None, "Solo Leveling S01 + S02"),
)


@pytest.mark.parametrize(
    ("series", "expected"),
    [(series, season) for series, season, _ in _SEASON_CASES],
    ids=[series for series, _, _ in _SEASON_CASES],
)
def test_season_hint_reads_a_single_season_marker(series: str, expected: int | None) -> None:
    assert season_hint(series) == expected


@pytest.mark.parametrize(
    ("series", "expected"),
    [(series, stripped) for series, _, stripped in _SEASON_CASES],
    ids=[series for series, _, _ in _SEASON_CASES],
)
def test_strip_season_drops_the_marker_season_hint_reads(series: str, expected: str) -> None:
    assert strip_season(series) == expected


_BASE_CASES: Final[tuple[tuple[str, str], ...]] = (
    ("Solo Leveling Season 2 -Arise from the Shadow-", "Solo Leveling"),
    ("Ore dake Level Up na Ken Season 2: Arise from the Shadow", "Ore dake Level Up na Ken"),
    ("Mushoku Tensei III: Isekai Ittara Honki Dasu", "Mushoku Tensei"),
    ("Neko to Ryuu - The Cat and the Dragon", "Neko to Ryuu"),
    ("Sousou no Frieren – Beyond Journey's End", "Sousou no Frieren"),
    ("Solo Leveling", "Solo Leveling"),
    ("Re:Zero 3rd Season", "Re:Zero"),
    ("Solo Leveling (Ore dake Level Up na Ken) S2", "Solo Leveling"),
)


@pytest.mark.parametrize(("title", "expected"), _BASE_CASES, ids=[title for title, _ in _BASE_CASES])
def test_base_title_drops_the_season_marker_and_the_subtitle(title: str, expected: str) -> None:
    assert base_title(title) == expected


def test_title_forms_meet_when_a_release_drops_the_subtitle() -> None:
    english: frozenset[str] = title_forms("Solo Leveling Season 2 -Arise from the Shadow-")
    romaji: frozenset[str] = title_forms("Ore dake Level Up na Ken Season 2: Arise from the Shadow")

    assert title_forms("Solo Leveling") & english
    assert title_forms("Ore dake Level Up na Ken") & romaji


def test_title_forms_of_unrelated_titles_do_not_meet() -> None:
    assert not (title_forms("Solo Leveling") & title_forms("Ore dake Level Up na Ken"))

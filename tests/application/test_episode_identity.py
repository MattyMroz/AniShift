from __future__ import annotations

import ast
import copy
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import pytest

from anishift.application import episode_identity
from anishift.application.episode_identity import (
    CONFLICT_REASONS,
    REASONS,
    IdentityAssessment,
    IdentityVerdict,
    classify,
    classify_many,
    classify_release_name,
    conflict_label,
    is_conflict,
)

pytestmark = pytest.mark.unit

_IDENTITY_FIXTURE: Final[Path] = Path(__file__).parents[1] / "fixtures/acquisition/identity-231.json"


def _target_for(title: str = "Star Garden", **changes: Any) -> dict[str, Any]:
    target: dict[str, Any] = {
        "aliases": [title],
        "type": "TV",
        "season": 1,
        "episode": 5,
        "local_episode": 5,
        "absolute": 5,
        "episode_title": "A Journey Through Clouds",
        "other_episode_titles": ["The Silent Winter Night"],
        "other_series": [],
    }
    target.update(changes)
    return target


def _assess(
    target: Mapping[str, Any], candidate: Mapping[str, Any], evidence: Mapping[str, Any] | None = None
) -> IdentityAssessment:
    result: IdentityAssessment = classify(target, candidate, evidence)
    assert result.reason in REASONS
    without_evidence: IdentityAssessment = classify(target, candidate)
    assert without_evidence.reason in REASONS
    assert classify_many(target, [candidate, candidate]) == (without_evidence, without_evidence)
    return result


def _assert_rejected(target: Mapping[str, Any], candidate: Mapping[str, Any]) -> None:
    assert _assess(target, candidate).verdict is not IdentityVerdict.MATCH


@pytest.mark.parametrize(
    "word",
    [
        "Omake",
        "Audio Commentary",
        "Teaser",
        "SP",
        "Picture Drama",
        "Mini Anime",
        "Yokoku",
        "Bonus",
        "Opening",
        "Ending",
        "NC",
        "CD2",
        "Preview",
        "Recap",
        "NCOP",
        "NCED",
        "PV",
        "CM",
        "Menu",
        "Commentary",
        "Special",
        "OVA",
        "OAD",
        "Extra",
        "Trailer",
        "Part",
        "CD",
        "Disc",
        "Vol",
        "Digest",
        "Summary",
        "Movie",
        "Film",
    ],
)
def test_classify_review_and_separator_extras_rejected(word: str) -> None:
    _assert_rejected(_target_for(), {"filename": f"Star Garden - 05 {word}.mkv"})
    _assert_rejected(
        _target_for(episode_title=None), {"filename": f"Star Garden S01E05 - Clouds - {word} [1080p HEVC].mkv"}
    )


@pytest.mark.parametrize(
    ("title", "filename", "release", "path"),
    [
        ("Star Garden", "[SubsPlease] Star Garden - 05 Preview [1080p].mkv", "", ""),
        ("Star Garden", "[Erai-raws] Star Garden - 05 NCOP [1080p].mkv", "", ""),
        ("Star Garden", "[VCB-Studio] Star Garden [05][Menu][1080p].mkv", "", ""),
        ("Star Garden", "[Beatrice-Raws] Star Garden 05 Interview [BDRip].mkv", "", ""),
        ("Star Garden", "[Judas] Star Garden S01E05-E06.mkv", "", ""),
        ("Star Garden", "Star Garden - 05 & 06.mkv", "", ""),
        ("Star Garden", "Star Garden - 05+06.mkv", "", ""),
        ("Star Garden", "Star Garden - 05~06.mkv", "", ""),
        ("Star Garden", "Star Garden - 05 to 06.mkv", "", ""),
        ("Star Garden", "Star Garden S01E05E06.mkv", "", ""),
        ("Star Garden", "Star Garden - 05.5.mkv", "", ""),
        ("Star Garden", "Star Garden - 05 Part B.mkv", "", ""),
        ("Star Garden", "Star Garden - 05 - Recap.mkv", "", ""),
        ("Star Garden", "Star Garden Movie - 05.mkv", "", ""),
        ("Star Garden", "Star Garden II - 05.mkv", "", ""),
        ("Star Garden", "Star Garden 2 - 05.mkv", "", ""),
        ("Star Garden", "Star Garden 3rd Season - 05.mkv", "", ""),
        ("Star Garden", "Star Garden - S01E05 - The Silent Winter Night.mkv", "", ""),
        ("Star Garden", "Star Garden - S01E05 - Unknown Plex Episode.mkv", "", ""),
        ("Star Garden", "Re Star Garden S01E05.mkv", "", ""),
        ("Star Garden", "Star Garden S01E05 [Picture Drama].mkv", "", ""),
        ("Star Garden", "Star Garden S01E05 [Bonus 1080p HEVC].mkv", "", ""),
        ("Star Garden", "Star Garden - 05.mkv", "Star Garden Part 2", ""),
        ("Star Garden", "Star Garden - 05.mkv", "", "Season 2/Star Garden - 05.mkv"),
        ("Star Garden", "05.mkv", "Star Garden", "OVA/05.mkv"),
        ("Star Garden", "Star Garden S01E05.mkv", "", "Extras/Star Garden S01E05.mkv"),
        ("Star Garden", "Star Garden 05.mkv", "Star Garden Final Season", ""),
        ("星の庭", "[字幕組] 星の庭 - 05 特典映像.mkv", "", ""),
        ("星の庭", "[字幕組] 星の庭 第二期 - 05.mkv", "", ""),
        ("星之庭", "[字幕组] 星之庭 - 05 预告.mkv", "", ""),
        ("星之庭", "[字幕组] 星之庭 剧场版 - 05.mkv", "", ""),
        ("86", "[Group] 86 - 05-06 [1080p].mkv", "", ""),
        ("86", "[Group] 86 Part 2 - 05 [1080p].mkv", "", ""),
        ("Mob Psycho 100", "Mob Psycho 100 II - 05.mkv", "", ""),
        ("Mob Psycho 100", "Mob Psycho 100 - 05 - OVA.mkv", "", ""),
        ("Fairy Tail", "Fairy Tail 100 Years Quest - 05.mkv", "", ""),
        ("Fairy Tail 100 Years Quest", "Fairy Tail S01E05.mkv", "", ""),
        ("Star Garden", "Star Garden S01E05 [1080p].zip", "", ""),
        ("Star Garden", "Star Garden S01E05 [1080p].mkv.exe", "", ""),
        ("Star Garden", "Star Garden - 05.mkv", "Star Garden S02 Batch", ""),
    ],
)
def test_classify_original_forty_adversarial_cases_rejected(title: str, filename: str, release: str, path: str) -> None:
    _assert_rejected(_target_for(title), {"filename": filename, "release": release, "path": path})


def test_classify_ranges_sequels_and_nonvideo_rejected() -> None:
    for suffix in ("S01E05 + S01E06", "05 and 06", "05, 06", "05_06"):
        _assert_rejected(_target_for(), {"filename": f"Star Garden {suffix}.mkv"})
    for title in ("Gintama'", "Gintama°", "Gintama²", "Gintama II", "Gintama 2"):
        _assert_rejected(_target_for("Gintama"), {"filename": f"{title} - 05.mkv"})
    for extension in ("mka", "mks", "ac3", "rar"):
        assert _assess(_target_for(), {"filename": f"Star Garden - 05.{extension}"}).verdict is IdentityVerdict.MISMATCH


def test_classify_group_cleanup_extras_preserved() -> None:
    for filename in (
        "[Bonus] Star Garden - 05 [1080p HEVC].mkv",
        "[Team] Star Garden - 05 [1080p HEVC]-Omake.mkv",
        "[Team] Star Garden - 05 [1080p HEVC]-CD2.mkv",
        "[Team] Star Garden - 05 [1080p HEVC] [OVA].mkv",
    ):
        _assert_rejected(_target_for(), {"filename": filename})
    for release in ("[Team&Other] Star Garden OAD 01-12 Batch", "Star Garden OAD 01-12 Batch EAC3+AC3"):
        _assert_rejected(_target_for(), {"filename": "Star Garden - 05.mkv", "release": release})


def test_classify_numbered_titles_and_technical_metadata_accepted() -> None:
    for title in ("86", "Mob Psycho 100", "Fairy Tail 100 Years Quest", "星の庭", "星之庭", "Gintama°", "Gintama'"):
        assert (
            _assess(_target_for(title), {"filename": f"[Fansub] {title} - 05 [1080p].mkv"}).verdict
            is IdentityVerdict.MATCH
        )
    for filename in (
        "[Team][Star Garden][05][1080p HEVC].mkv",
        "Star.Garden.S01E05.1080p.WEB-DL.AAC2.0.H.264.mkv",
        "Star Garden - 05 - A Journey Through Clouds [BD 1080p HEVC FLAC].mkv",
    ):
        assert _assess(_target_for(), {"filename": filename}).verdict is IdentityVerdict.MATCH


def test_classify_part_and_season_conflicts_rejected() -> None:
    target: dict[str, Any] = _target_for(
        aliases=["Star Garden Season 2 Part 2", "Star Garden"], season=2, episode=17, absolute=29
    )
    for filename in ("Star Garden S2 - 05.mkv", "Star Garden Part 1 S02E17.mkv", "Star Garden S03E17.mkv"):
        _assert_rejected(target, {"filename": filename})
    assert _assess(target, {"filename": "Star Garden S02E17.mkv"}).verdict is IdentityVerdict.MATCH
    assert _assess(target, {"filename": "Star Garden S2 Part 2 - 05.mkv"}).verdict is IdentityVerdict.MATCH
    _assert_rejected(
        _target_for("Star Garden Moon Voyage", season=2, absolute=17),
        {"filename": "Star Garden Moon Voyage 2nd Season - 05.mkv"},
    )


def test_classify_titleless_file_nearest_directory_respected() -> None:
    assert (
        _assess(
            _target_for(),
            {"filename": "05.mkv", "path": "Star Garden/Season 1/05.mkv", "release": "Star Garden S1-S3 + OVA"},
        ).verdict
        is IdentityVerdict.MATCH
    )
    for path in ("Star Garden/Different Work/05.mkv", "Star Garden/Season 2/05.mkv", "Star Garden/OVA/05.mkv"):
        _assert_rejected(_target_for(), {"filename": "05.mkv", "path": path, "release": "Star Garden"})
    _assert_rejected(_target_for(), {"filename": "05.mkv", "release": "Star Garden S1-S3"})


def test_classify_collection_selected_neighbor_preserved() -> None:
    target: dict[str, Any] = _target_for(
        "Star Garden Moon Voyage", aliases=["Star Garden Moon Voyage", "Star Garden"], season=2, absolute=17
    )
    evidence: dict[str, Any] = {
        "target_catalog": {"title": "Star Garden Moon Voyage", "format": "TV"},
        "related_catalog_entries": [
            {"title": "Star Garden", "format": "TV"},
            {"title": "Star Garden Other Voyage", "format": "TV"},
        ],
    }
    release: str = "Star Garden + Star Garden Moon Voyage Complete Series S1-S2"
    for candidate in (
        {"filename": "Star Garden S02E05.mkv", "release": release},
        {"path": "Star Garden Other Voyage/Star Garden Moon Voyage S02E05.mkv", "release": release},
        {"filename": "Star Garden Moon Voyage S02E05.mkv", "path": "Star Garden S02E05.mkv", "release": release},
        {"filename": "[Star Garden] Star Garden Moon Voyage S02E05.mkv", "release": release},
    ):
        assert _assess(target, candidate, evidence).verdict is IdentityVerdict.INSUFFICIENT
    good: dict[str, Any] = {
        "path": f"{release}/Star Garden Moon Voyage/Star Garden Moon Voyage S02E05.mkv",
        "release": release,
    }
    assert _assess(target, good, evidence).verdict is IdentityVerdict.MATCH


def test_classify_numbered_directory_episode_not_inferred() -> None:
    target: dict[str, Any] = _target_for(episode=2, local_episode=2, absolute=2)
    for directory in ("Star Garden 2", "Star Garden 2 [1080p]", "[Team] Star Garden 2 [BD HEVC]"):
        candidate: dict[str, Any] = {"path": f"{directory}/Star Garden - 02.mkv", "release": "Star Garden S1-S3"}
        assert _assess(target, candidate).verdict is IdentityVerdict.INSUFFICIENT
    for path in ("Star Garden 1 [BD]/Star Garden - 02.mkv", "Star Garden - 02.mkv"):
        assert _assess(target, {"path": path, "release": "Star Garden S1-S3"}).verdict is IdentityVerdict.MATCH
    assert _assess(_target_for("Orbit 2"), {"path": "Orbit 2/Orbit 2 - 05.mkv"}).verdict is IdentityVerdict.MATCH


def test_classify_library_roots_local_identity_preferred() -> None:
    target: dict[str, Any] = _target_for(
        "Star Garden Moon Voyage", aliases=["Star Garden Moon Voyage", "Star Garden"], season=2, absolute=17
    )
    evidence: dict[str, Any] = {"related_catalog_entries": [{"title": "Star Garden", "format": "TV"}]}
    for directory in ("Star Garden/Star Garden Moon Voyage", "Star Garden/Season 2", "Star Garden"):
        assert (
            _assess(target, {"path": f"{directory}/Star Garden Moon Voyage S02E05.mkv"}, evidence).verdict
            is IdentityVerdict.MATCH
        )


def test_classify_episode_directories_and_unknown_season_accepted() -> None:
    for directory in ("Star Garden - 05 [1080p]", "[Group] Star Garden 05 [1080p]"):
        assert _assess(_target_for(), {"path": f"{directory}/Star Garden - 05.mkv"}).verdict is IdentityVerdict.MATCH
    for season in (None, 1):
        assert (
            _assess(_target_for(season=season), {"path": "Star Garden 1 [BD]/Star Garden - 05.mkv"}).verdict
            is IdentityVerdict.MATCH
        )
    assert (
        _assess(_target_for(year=2024), {"path": "Star Garden 2 (2024)/Star Garden - 05.mkv"}).verdict
        is IdentityVerdict.INSUFFICIENT
    )


def test_classify_context_exemptions_conflicting_ancestors_preserved() -> None:
    target: dict[str, Any] = _target_for(other_series=["Star Garden Moon Voyage"])
    for directory in (
        "Star Garden Moon Voyage/Season 1",
        "Star Garden/Star Garden Moon Voyage/Season 1",
        "Star Garden Moon Voyage/Star Garden",
    ):
        assert _assess(target, {"path": f"{directory}/Star Garden - 05.mkv"}).verdict is IdentityVerdict.INSUFFICIENT
    sequel: dict[str, Any] = _target_for(
        "Star Garden Moon Voyage", aliases=["Star Garden Moon Voyage", "Star Garden"], season=2, absolute=17
    )
    for directory in ("Star Garden OVA/Star Garden", "Movies/Star Garden", "Specials/Star Garden"):
        assert (
            _assess(sequel, {"path": f"{directory}/Star Garden Moon Voyage S02E05.mkv"}).verdict
            is IdentityVerdict.INSUFFICIENT
        )


def test_classify_episode_directory_exemption_both_conditions_required() -> None:
    for directory, episode in (("2", 2), ("3", 3), ("2 [1080p]", 2), ("02", 5), ("5 [BD]", 5)):
        assert (
            _assess(
                _target_for(episode=episode, local_episode=episode, absolute=episode),
                {"path": f"Star Garden {directory}/Star Garden - {episode:02}.mkv", "release": "Star Garden S1-S3"},
            ).verdict
            is IdentityVerdict.INSUFFICIENT
        )
    assert (
        _assess(_target_for(season=None), {"path": "Star Garden 2/Star Garden - 05.mkv"}).verdict
        is IdentityVerdict.INSUFFICIENT
    )
    assert (
        _assess(
            _target_for("Star Garden Director's Cut", aliases=["Star Garden Director's Cut", "Star Garden"]),
            {"path": "TV/Star Garden - 05.mkv", "release": "Star Garden (TV + Director's Cut)"},
        ).verdict
        is IdentityVerdict.INSUFFICIENT
    )


def test_classify_multiseason_release_episode_directory_exemption_disabled() -> None:
    target: dict[str, Any] = _target_for(episode=2, local_episode=2, absolute=2)
    for release in ("Star Garden S1-S3", "Star Garden Season 1 Season 2"):
        assert (
            _assess(target, {"path": "Star Garden 02/Star Garden - 02.mkv", "release": release}).verdict
            is IdentityVerdict.INSUFFICIENT
        )
    assert (
        _assess(target, {"path": "Star Garden 02/Star Garden - 02.mkv", "release": "Star Garden S1"}).verdict
        is IdentityVerdict.MATCH
    )


def test_classify_local_tv_variant_and_original_audio_note_accepted() -> None:
    for candidate in (
        {
            "path": "Star Garden (TV + Director's Cut)/TV/Star Garden - 05.mkv",
            "release": "Star Garden (TV + Director's Cut)",
        },
        {"filename": "Star Garden - 05 [TV].mkv", "release": "Star Garden (TV + Director's Cut)"},
        {"filename": "Star Garden - 05.mkv", "release": "Star Garden [BD] Original Version"},
    ):
        assert _assess(_target_for(), candidate).verdict is IdentityVerdict.MATCH
    assert (
        _assess(
            _target_for(),
            {"path": "Director's Cut/Star Garden - 05.mkv", "release": "Star Garden (TV + Director's Cut)"},
        ).verdict
        is IdentityVerdict.INSUFFICIENT
    )
    assert (
        _assess(
            _target_for("Star Garden Director's Cut"),
            {
                "path": "Director's Cut/Star Garden Director's Cut - 05.mkv",
                "release": "Star Garden Director's Cut + Extended Edition",
            },
        ).verdict
        is IdentityVerdict.MATCH
    )


def test_classify_editing_variant_target_agreement_required() -> None:
    evidence: dict[str, Any] = {
        "target_mappings": {
            "episodes": [
                {"seasonNumber": 1, "episodeNumber": 5, "title": "A Journey Through Clouds"},
                {"seasonNumber": 0, "episodeNumber": 1, "title": "A Journey Through Clouds (Director's Cut)"},
            ]
        }
    }
    for edition in ("Director's Cut", "Directors Cut", "Extended Edition", "Theatrical Cut"):
        for candidate in (
            {"filename": "Star Garden - 05.mkv", "release": f"Star Garden [1080p] [{edition}]"},
            {"filename": "Star Garden - 05.mkv", "release": f"[{edition}] Star Garden [1080p]"},
            {"path": f"Star Garden {edition}/Star Garden - 05.mkv", "release": "Star Garden S1-S2"},
        ):
            assert _assess(_target_for(), candidate, evidence).verdict is IdentityVerdict.INSUFFICIENT
    for title in ("Star Garden Director's Cut", "Star Garden Extended Edition"):
        assert (
            _assess(_target_for(title), {"filename": f"{title} - 05.mkv", "release": title}).verdict
            is IdentityVerdict.MATCH
        )
    assert (
        _assess(
            _target_for(episode_title="The Director's Cut"),
            {
                "filename": "Star Garden - 05 - The Director's Cut.mkv",
                "release": "Star Garden - 05 - The Director's Cut",
            },
        ).verdict
        is IdentityVerdict.MATCH
    )
    assert (
        _assess(_target_for(), {"filename": "Star Garden - 05.mkv", "release": "Star Garden [1080p]"}, evidence).verdict
        is IdentityVerdict.MATCH
    )
    assert (
        _assess(
            _target_for(episode_title=None),
            {"filename": "Star Garden - 05.mkv", "release": "Star Garden [Director's Cut]"},
            {"target_episode": {"title": "Clouds (Director's Cut)"}},
        ).verdict
        is IdentityVerdict.MATCH
    )


def test_classify_unverified_title_and_fuzzy_competitor_rejected() -> None:
    target: dict[str, Any] = _target_for(episode_title=None)
    _assert_rejected(target, {"filename": "Star Garden S01E05 - Through the Clouds [1080p HEVC].mkv"})
    for filename in (
        "Star Garden S01E06 - Through the Clouds.mkv",
        "Star Garden S02E05 - Through the Clouds.mkv",
        "Star Garden 05 - Through the Clouds.mkv",
        "Star Garden S01E05 Through the Clouds.mkv",
        "Star Garden S01E05 - Through the Clouds 06.mkv",
        "Star Garden S01E05 - Through the Clouds S01E06.mkv",
        "Star Garden S01E05 - Through the Clouds 05-06.mkv",
    ):
        _assert_rejected(target, {"filename": filename})
    target = _target_for(
        episode_title="A Journey Through Clouds Part 1", other_episode_titles=["A Journey Through Clouds Part 2"]
    )
    _assert_rejected(target, {"filename": "Star Garden - 05 - A Journey Through Cloud Part 2.mkv"})


def test_classify_movie_year_collision_and_special_directory_rejected() -> None:
    target: dict[str, Any] = _target_for(type="MOVIE", episode_title="Complete Movie")
    evidence: dict[str, Any] = {
        "related_catalog_entries": [{"id": 2, "type": "ANIME", "seasonYear": 2020, "title": {"en": "Other Garden"}}]
    }
    assert _assess(target, {"filename": "Star Garden (2020).mkv"}, evidence).verdict is not IdentityVerdict.MATCH
    for candidate in (
        {"filename": "Star Garden 2016.mkv"},
        {"filename": "Star Garden.mkv", "path": "OVA/Star Garden.mkv"},
        {"filename": "Star Garden.mkv", "path": "Specials/Star Garden.mkv"},
    ):
        _assert_rejected({**target, "year": 2020}, candidate)


@pytest.mark.parametrize("marker", ["第5话", "第5話", "第5集", "Episode 5", "Ep 5", "E 5", "#5"])
def test_classify_cjk_single_numbers_accepted_and_ranges_rejected(marker: str) -> None:
    assert _assess(_target_for(), {"filename": f"Star Garden - {marker} [1080p].mkv"}).verdict is IdentityVerdict.MATCH
    _assert_rejected(_target_for(), {"filename": f"Star Garden - {marker} + 06 [1080p].mkv"})


def test_classify_labels_ignored_and_inputs_preserved() -> None:
    target: dict[str, Any] = _target_for()
    candidate: dict[str, Any] = {"filename": "Star Garden - 05.mkv"}
    original: dict[str, Any] = copy.deepcopy(target)
    expected: IdentityAssessment = _assess(target, candidate)
    for key in (
        "label",
        "id",
        "info_hash",
        "provenance",
        "review_history",
        "source_adjudication",
        "size",
        "file_index",
    ):
        assert _assess({**target, key: "anything"}, {**candidate, key: "anything"}) == expected
    assert target == original


def test_classify_leading_bracket_identity_conflicts_rejected() -> None:
    for bracket in ("Star Garden II", "Star Garden OVA", "Star Garden S2", "Moon Garden", "Star Garden Movie"):
        _assert_rejected(
            _target_for(),
            {
                "filename": f"[{bracket}][05][1080p].mkv",
                "path": f"Star Garden/[{bracket}][05][1080p].mkv",
                "release": "Star Garden [BD 1080p]",
            },
        )
    assert _assess(_target_for(), {"filename": "[Star Garden][05][1080p].mkv"}).verdict is IdentityVerdict.MATCH


def test_classify_plex_extra_folders_and_suffixes_rejected() -> None:
    for folder in (
        "Featurettes",
        "Behind The Scenes",
        "Deleted Scenes",
        "Interviews",
        "Scenes",
        "Shorts",
        "Other",
        "Trailers",
    ):
        _assert_rejected(
            _target_for(), {"filename": "Star Garden - 05.mkv", "path": f"Star Garden/{folder}/Star Garden - 05.mkv"}
        )
    for suffix in ("featurette", "behindthescenes", "deleted", "interview", "scene", "short", "other", "trailer"):
        _assert_rejected(_target_for(), {"filename": f"Star Garden - 05 [1080p HEVC]-{suffix}.mkv"})


@pytest.mark.parametrize(
    "suffix",
    ["Interview with the Cast", "Making Of", "Deleted Scenes", "Music Video", "Clouds-featurette", "Clouds", "[Audio]"],
)
def test_classify_unknown_episode_text_and_audio_rejected(suffix: str) -> None:
    _assert_rejected(_target_for(episode_title=None), {"filename": f"Star Garden S01E05 - {suffix}.mkv"})


@pytest.mark.parametrize(
    "title",
    [
        "The Other Side of the Wall",
        "A Short Journey Through Clouds",
        "The Interview",
        "A Happy Ending",
        "The Making of a Hero",
    ],
)
def test_classify_plex_words_in_catalogued_titles_accepted(title: str) -> None:
    filename: str = f"Star Garden S01E05 - {title}.mkv"
    assert (
        _assess(_target_for(episode_title=title), {"filename": filename, "release": filename}).verdict
        is IdentityVerdict.MATCH
    )
    _assert_rejected(_target_for(episode_title=title), {"filename": filename[:-4] + " Bonus.mkv"})


@pytest.mark.parametrize(
    "context",
    [
        "Звёздный сад (спешл)",
        "Звёздный сад [ТВ-2] [1080p]",  # noqa: RUF001
        "Сезон 2",
        "Фильм",
        "ова",
        "星の庭 第2期",
        "[字幕组] 星之庭 第二季",
        "剧场版",
        "劇場版",
        "特典",
        "番外",
        "総集編",
        "总集篇",
        "特別編",
        "特别篇",
        "Star Garden II",
        "Star Garden III",
        "Star Garden IV",
        "Star Garden Zoku",
        "Star Garden Second Season",
        "Star Garden Kan",
        "Season Two",
        "Third Season",
        "Season Three",
        "Star Garden Season Ten",
    ],
)
def test_classify_multilingual_context_sequels_and_formats_rejected(context: str) -> None:
    target: dict[str, Any] = _target_for(aliases=["Star Garden", "Звёздный сад", "星の庭", "星之庭"])
    _assert_rejected(target, {"filename": "Star Garden - 05.mkv", "release": context})
    _assert_rejected(target, {"path": f"Star Garden/{context}/Star Garden - 05.mkv"})


def test_classify_context_markers_compatible_metadata_retained() -> None:
    for context in (
        "[Team] Star Garden [BD 1080p HEVC FLAC]",
        "Star Garden 01-12 Batch",
        "Star Garden First Season",
        "Star Garden Season One",
        "Star Garden 第一期",
        "Star Garden ТВ-1",  # noqa: RUF001
        "Star Garden (2024)",
        "Star Garden S01E05",
    ):
        assert (
            _assess(_target_for(year=2024), {"filename": "Star Garden - 05.mkv", "release": context}).verdict
            is IdentityVerdict.MATCH
        )
    for context in ("Star Garden 2023", "Star Garden 第十期"):
        _assert_rejected(_target_for(year=2024), {"filename": "Star Garden - 05.mkv", "release": context})


@pytest.mark.parametrize(
    "context", ["Star Garden: Next Horizon", "Star Garden - Uncatalogued Arc", "Star Garden: Beyond the Stars"]
)
def test_classify_unknown_context_subtitle_rejected(context: str) -> None:
    _assert_rejected(_target_for(), {"filename": "Star Garden - 05.mkv", "release": context})
    _assert_rejected(_target_for(), {"path": f"{context}/Star Garden - 05.mkv"})


@pytest.mark.parametrize(
    "context",
    [
        "Saison 2",
        "Staffel 2",
        "Temporada 2",
        "Stagione 2",
        "시즌2",
        "극장판",
        "2期",
        "第2季",
        "続",
        "Part II",
        "Season II",
        "2nd Cour",
        "Gekijouban",
        "R2",
        "Saison 3",
        "Staffel III",
        "Temporada IV",
        "Stagione 12",
        "시즌 3",
        "三期",
        "第十二季",
        "Part IV",
        "Season XII",
        "3rd Cour",
        "Gekijōban",
        "R3",
    ],
)
@pytest.mark.parametrize("prefix", ["", "Star Garden "])
def test_classify_multilingual_context_regressions_rejected(context: str, prefix: str) -> None:
    _assert_rejected(_target_for(), {"filename": "Star Garden - 05.mkv", "release": prefix + context})
    _assert_rejected(_target_for(), {"path": f"{prefix}{context}/Star Garden - 05.mkv"})


def test_classify_compatible_context_and_catalogued_subtitles_accepted() -> None:
    for context in (
        "Star Garden Saison 1",
        "Staffel I",
        "Temporada 1",
        "Star Garden Stagione 1",
        "시즌1",
        "Star Garden 1期",
        "第1季",
        "Season I",
        "Star Garden 2024",
    ):
        assert (
            _assess(_target_for(), {"filename": "Star Garden - 05.mkv", "release": context}).verdict
            is IdentityVerdict.MATCH
        )
    for title in ("Star Garden: Next Horizon", "Star Garden R2", "Star Garden 続", "Star Garden Season II"):
        assert (
            _assess(_target_for(title), {"filename": f"{title} - 05.mkv", "release": title}).verdict
            is IdentityVerdict.MATCH
        )
    assert (
        _assess(
            _target_for(episode_title="Next Horizon"),
            {"filename": "Star Garden - 05.mkv", "release": "Star Garden - 05 - Next Horizon [1080p]"},
        ).verdict
        is IdentityVerdict.MATCH
    )


def test_classify_collection_and_title_boundaries_preserved() -> None:
    for release in (
        "Star Garden R1 + R2",
        "Star Garden Saison 1 Saison 2",
        "Star Garden Season I Season II",
        "Star Garden + 극장판",
        "Star Garden + Gekijouban",
        "Star Garden (Jardin des etoiles) [1080p HEVC]",
    ):
        assert (
            _assess(
                _target_for(aliases=["Star Garden", "Jardin des etoiles"]),
                {"filename": "Star Garden - 05.mkv", "release": release},
            ).verdict
            is IdentityVerdict.MATCH
        )
    for context in ("Star Garden: Next Horizon", "Star Garden Season II"):
        _assert_rejected(
            _target_for(episode_title=context.removeprefix("Star Garden ")),
            {"filename": "Star Garden - 05.mkv", "release": context},
        )


@pytest.mark.parametrize(
    "context",
    [
        "Star Garden [R2 DVD]",
        "Star Garden [1080p] R2 DVD",
        "Star Garden R1 + R2",
        "Star Garden Uncatalogued Arc",
        "Star Garden Next Horizon",
        "Star Garden [1080p] - Next Horizon",
        "Star Garden - 05 - Next Horizon",
        "Star Garden (2024) [Team]",
        "R2 DVD",
    ],
)
def test_classify_release_metadata_subtitle_not_inferred(context: str) -> None:
    assert (
        _assess(_target_for(), {"filename": "Star Garden - 05.mkv", "release": context}).verdict
        is IdentityVerdict.MATCH
    )


@pytest.mark.parametrize("title", ["Star Garden II", "Star Garden Season II", "Code Geass Lelouch of the Rebellion R2"])
def test_classify_catalogued_work_qualifiers_accepted(title: str) -> None:
    assert (
        _assess(_target_for(title), {"filename": f"{title} - 05.mkv", "release": title}).verdict
        is IdentityVerdict.MATCH
    )


@pytest.mark.parametrize("context", ["R2", "R3", "r12"])
def test_classify_standalone_continuation_context_uncertain(context: str) -> None:
    for candidate in (
        {"filename": "Star Garden - 05.mkv", "release": context},
        {"path": f"{context}/Star Garden - 05.mkv"},
    ):
        assert _assess(_target_for(), candidate).verdict is IdentityVerdict.INSUFFICIENT


@pytest.mark.parametrize("context", ["[R2 DVD]", "R2 DVD", "R1 + R2", "Star Garden R2"])
def test_classify_standalone_continuation_exceptions_accepted(context: str) -> None:
    title: str = "Star Garden R2" if context == "Star Garden R2" else "Star Garden"
    for candidate in ({"filename": f"{title} - 05.mkv", "release": context}, {"path": f"{context}/{title} - 05.mkv"}):
        assert _assess(_target_for(title), candidate).verdict is IdentityVerdict.MATCH


@pytest.mark.parametrize(
    "title", ["The Second Season", "Season II", "Saison 2", "Gekijouban", "The Final Season", "続", "R2"]
)
@pytest.mark.parametrize("number", ["05", "S01E05"])
def test_classify_episode_title_language_markers_removed(title: str, number: str) -> None:
    context: str = f"Star Garden - {number} - {title} [1080p]"
    assert (
        _assess(_target_for(episode_title=title), {"filename": f"{context}.mkv", "release": context}).verdict
        is IdentityVerdict.MATCH
    )
    _assert_rejected(
        _target_for(episode_title=title), {"filename": "Star Garden - 05.mkv", "release": context + " Saison 2"}
    )


def test_classify_explicit_subtitle_before_episode_rejected() -> None:
    for context in (
        "Star Garden: Next Horizon",
        "Star Garden - Next Horizon - 05 [1080p]",
        "Star Garden: Next Horizon S01E05 [1080p]",
        "Star Garden: Next Horizon [1080p]",
    ):
        assert (
            _assess(_target_for(), {"filename": "Star Garden - 05.mkv", "release": context}).verdict
            is IdentityVerdict.INSUFFICIENT
        )
    for context in ("Star Garden Saison 2 Saison 3", "Star Garden Season II Season III"):
        _assert_rejected(_target_for(), {"filename": "Star Garden - 05.mkv", "release": context})
    assert (
        _assess(_target_for(), {"filename": "Star Garden - 05v2.mkv", "release": "Star Garden - 05v2 [1080p]"}).verdict
        is IdentityVerdict.MATCH
    )


def test_classify_archived_identifiers_identity_unaffected() -> None:
    evidence: dict[str, Any] = {
        "target_catalog": {"id": 1, "title": "Star Garden", "format": "TV", "seasonYear": 2024},
        "related_catalog_entries": [
            {"id": 1, "title": "Star Garden", "format": "TV", "seasonYear": 2024},
            {"id": 2, "title": "Moon Garden", "format": "TV", "seasonYear": 2025},
        ],
    }
    candidate: dict[str, Any] = {"filename": "Star Garden - 05.mkv"}
    expected: IdentityAssessment = _assess(_target_for(), candidate, evidence)
    assert expected.verdict is IdentityVerdict.MATCH
    for entry in [evidence["target_catalog"], *evidence["related_catalog_entries"]]:
        entry["id"] = "changed"
        entry["label"] = "błędny"
        entry["provenance"] = "unknown"
        entry["info_hash"] = "changed"
    assert _assess(_target_for(), candidate, evidence) == expected


@pytest.mark.parametrize(
    "release",
    ["Star Garden Complete Series (Star Garden Second Season)", "Star Garden 01-12 + 特典映像", "Star Garden + спешл"],
)
def test_classify_mixed_work_release_specific_file_preserved(release: str) -> None:
    target: dict[str, Any] = _target_for(other_series=["Star Garden Second Season"])
    assert _assess(target, {"filename": "Star Garden - 05.mkv", "release": release}).verdict is IdentityVerdict.MATCH
    _assert_rejected(target, {"filename": "05.mkv", "release": release})


def test_classify_zero_episode_mapping_fallback_disabled() -> None:
    evidence: dict[str, Any] = {
        "target_episode": {"episodeNumber": 5},
        "target_mappings": {
            "episodes": [
                {"seasonNumber": 1, "episodeNumber": 0, "title": "The Interview"},
                {"seasonNumber": 1, "episodeNumber": 5, "title": "The Other Journey"},
            ]
        },
    }
    candidate: dict[str, Any] = {"filename": "Star Garden S01E00 - The Interview.mkv"}
    assert _assess(_target_for(episode=0, episode_title=None), candidate, evidence).verdict is IdentityVerdict.MATCH
    assert (
        _assess(_target_for(episode=None, episode_title=None), candidate, evidence).verdict is not IdentityVerdict.MATCH
    )


@pytest.mark.parametrize(
    "evidence",
    [
        {"related_catalog_entries": [None]},
        {"target_catalog": ["bad"]},
        {"target_mappings": {"episodes": [None]}},
        {"target_episode": "bad"},
    ],
)
def test_classify_malformed_evidence_uncertain_and_nonvideo_rejected(evidence: dict[str, Any]) -> None:
    assert (
        _assess(_target_for(), {"filename": "Star Garden - 05.mkv"}, evidence).verdict is IdentityVerdict.INSUFFICIENT
    )
    archive: dict[str, Any] = {"filename": "Star Garden - 05.rar", "resolution": 1080}
    assert _assess(_target_for(), archive, evidence).verdict is IdentityVerdict.MISMATCH


def test_classify_archived_synonym_matches_selected_work() -> None:
    evidence: dict[str, Any] = {"target_catalog": {"synonyms": ["Jardin des etoiles"]}}
    assert (
        _assess(_target_for(), {"filename": "Jardin des etoiles - 05.mkv"}, evidence).verdict is IdentityVerdict.MATCH
    )


def test_classify_multilingual_metadata_competing_episodes_and_works_excluded() -> None:
    evidence: dict[str, Any] = {
        "target_catalog": {"id": 1, "synonyms": ["Jardin des etoiles", "Moon Garden"]},
        "related_catalog_entries": [{"id": 2, "synonyms": ["Moon Garden"]}],
        "target_mappings": {
            "episodes": [
                {"seasonNumber": 1, "episodeNumber": 5, "title": {"es": "El viaje entre las nubes"}},
                {"seasonNumber": 1, "episodeNumber": 6, "title": {"es": "El viaje entre los mares"}},
            ]
        },
    }
    assert (
        _assess(
            _target_for(episode_title=None),
            {"filename": "Jardin des etoiles S01E05 - El viaje entre la nubes.mkv"},
            evidence,
        ).verdict
        is IdentityVerdict.MATCH
    )
    for filename in ("Moon Garden - 05.mkv", "Star Garden S01E05 - El viaje entre los mares.mkv"):
        assert (
            _assess(_target_for(episode_title=None), {"filename": filename}, evidence).verdict
            is not IdentityVerdict.MATCH
        )


def test_classify_absolute_number_part_and_format_guards_preserved() -> None:
    evidence: dict[str, Any] = {"target_catalog": {"episodes": 12}}
    target: dict[str, Any] = _target_for(absolute=17)
    assert _assess(target, {"filename": "Star Garden - 17.mkv"}, evidence).verdict is IdentityVerdict.MATCH
    assert _assess(target, {"filename": "Star Garden Part 2 - 17.mkv"}, evidence).verdict is not IdentityVerdict.MATCH
    assert (
        _assess({**target, "type": "OVA"}, {"filename": "Star Garden - 17.mkv"}, evidence).verdict
        is not IdentityVerdict.MATCH
    )


@pytest.mark.parametrize("target", [_target_for(), None, [], "bad"])
def test_classify_many_mixed_boundaries_order_and_inputs_preserved(target: Any) -> None:
    candidates: list[Any] = [
        {"filename": "Star Garden - 05.mkv"},
        {"filename": "Star Garden S01E06.mkv"},
        {"filename": "Star Garden - 05.rar"},
        {},
        None,
        {"filename": 5},
        {"path": "Star Garden\\Season 1\\05.mkv"},
        {"release": False},
    ]
    original: tuple[Any, list[Any]] = copy.deepcopy((target, candidates))
    expected: tuple[IdentityAssessment, ...] = tuple(classify(target, candidate) for candidate in candidates)
    assert classify_many(target, candidates) == expected
    assert classify_many(target, []) == ()
    assert (target, candidates) == original
    assert all(result.reason in REASONS for result in expected)


def test_classify_many_identity_fixture_matches_classify_and_known_reasons() -> None:
    records: list[dict[str, Any]] = json.loads(_IDENTITY_FIXTURE.read_text(encoding="utf-8"))
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        state: dict[str, Any] = record["state"]
        key: str = json.dumps(state["target"], sort_keys=True, ensure_ascii=False)
        groups.setdefault(key, []).append(state)
    assert len(records) == 231
    for group in groups.values():
        target: dict[str, Any] = group[0]["target"]
        candidates: list[dict[str, Any]] = [state["candidate"] for state in group]
        expected: tuple[IdentityAssessment, ...] = tuple(classify(target, candidate) for candidate in candidates)
        assert classify_many(target, candidates) == expected
        assert all(result.reason in REASONS for result in expected)


def _returned_strings(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value} if node.value else set()
    if isinstance(node, ast.IfExp):
        return _returned_strings(node.body) | _returned_strings(node.orelse)
    if isinstance(node, ast.BoolOp):
        return set().union(*(_returned_strings(value) for value in node.values))
    return set()


def test_reasons_assessment_and_conflict_return_literals_complete() -> None:
    tree: ast.Module = ast.parse(Path(episode_identity.__file__).read_text(encoding="utf-8"))
    assessments: set[str] = set()
    conflicts: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "IdentityAssessment":
            assessments.update(_returned_strings(node.args[1]))
        if isinstance(node, ast.FunctionDef) and node.name.endswith("_conflict"):
            conflicts.update(
                reason
                for child in ast.walk(node)
                if isinstance(child, ast.Return) and child.value is not None
                for reason in _returned_strings(child.value)
            )
    assert assessments
    assert conflicts
    assert assessments | conflicts == REASONS


_NO_NUMBERING: Final[str] = "Mapped numbering cannot be checked without target numbering."
_UNCONSUMED: Final[str] = "Unconsumed filename text is neither technical metadata nor a catalog episode title."
_SEASON_CONFLICT: Final[str] = "Season marker conflicts with the target numbering system."
_MISMATCH_REASONS: Final[frozenset[str]] = frozenset(
    {
        "Explicit mapped episode differs from target.",
        "Selected file has no allowed video extension.",
        "Selected filename has an explicit Plex extra suffix.",
        "Selected residual explicitly identifies non-episode material.",
        "Catalog episode title belongs to another episode.",
    }
)
_OTHER_EPISODE_TITLE: Final[str] = "Catalog episode title belongs to another episode."


def _unnumbered_target() -> dict[str, Any]:
    return _target_for(
        aliases=[
            "Koori no Jouheki 2nd Season",
            "The Ramparts of Ice Season 2",
            "Koori no Jouheki",
            "The Ramparts of Ice",
        ],
        season=None,
        episode=None,
        local_episode=1,
        absolute=None,
        episode_title=None,
        other_episode_titles=[],
    )


def test_conflict_reasons_subset_of_reasons() -> None:
    assert CONFLICT_REASONS <= REASONS
    assert len(CONFLICT_REASONS) == 19
    assert not CONFLICT_REASONS & {
        "Package localized season conflicts with the target or is unresolved.",
        "Package Roman season/part conflicts with the target or is unresolved.",
        "Package season declaration conflicts with the target or is unresolved.",
        _NO_NUMBERING,
        _UNCONSUMED,
    }


def test_every_mismatch_is_conflict() -> None:
    assert _MISMATCH_REASONS <= REASONS
    for reason in _MISMATCH_REASONS:
        assessment: IdentityAssessment = IdentityAssessment(IdentityVerdict.MISMATCH, reason)
        assert is_conflict(assessment)
        assert conflict_label(assessment)
    for reason in REASONS:
        assert not is_conflict(IdentityAssessment(IdentityVerdict.MATCH, reason))


def test_conflict_label_for_every_reason() -> None:
    labels: set[str] = set()
    for reason in REASONS:
        assessment: IdentityAssessment = IdentityAssessment(IdentityVerdict.INSUFFICIENT, reason)
        assert is_conflict(assessment) is (reason in CONFLICT_REASONS)
        if reason in CONFLICT_REASONS:
            labels.add(conflict_label(assessment))
            continue
        with pytest.raises(ValueError, match=re.escape(reason)):
            conflict_label(assessment)
    assert "inny sezon" in labels
    with pytest.raises(ValueError, match=re.escape(_UNCONSUMED)):
        conflict_label(IdentityAssessment(IdentityVerdict.MATCH, _UNCONSUMED))


def test_insufficient_conflict_cases() -> None:
    other_season: IdentityAssessment = _assess(_target_for(), {"filename": "Star Garden S02E05 1080p.mkv"})
    assert other_season == IdentityAssessment(IdentityVerdict.INSUFFICIENT, _SEASON_CONFLICT)
    assert conflict_label(other_season) == "inny sezon"
    for filename in ("Star Garden 1080p WEB.mkv", "Star Garden - 05 Mystery Words.mkv"):
        assert not is_conflict(_assess(_target_for(), {"filename": filename}))
    unresolved: IdentityAssessment = _assess(
        _target_for("Example", season=11, episode=1, local_episode=1, absolute=None),
        {"path": "Example 第十一季/01.mkv", "release": "Example"},
    )
    assert unresolved.verdict is IdentityVerdict.INSUFFICIENT
    assert not is_conflict(unresolved)


def _name_assessments(target: Mapping[str, Any], name: str) -> tuple[IdentityAssessment, ...]:
    return (
        classify_release_name(target, name),
        _assess(target, {"filename": f"{name}.mkv"}),
        _assess(target, {"filename": f"{name}.mkv", "release": name}),
    )


@pytest.mark.parametrize(
    "depth",
    ["8bit", "8-bit", "8 bit", "8bits", "8BITS", "10bit", "10-bit", "10-bits", "10bits", "12bit"],
)
@pytest.mark.parametrize("source", ["", "WEBRip "])
def test_classify_bit_depth_metadata_matches_across_name_boundaries(depth: str, source: str) -> None:
    target: dict[str, Any] = _target_for(episode_title=None, other_episode_titles=[])
    for assessment in _name_assessments(target, f"Star Garden S01E05 1080p {source}{depth}"):
        assert assessment.verdict is IdentityVerdict.MATCH


@pytest.mark.parametrize("suffix", ["8bits Unknown Words", "8bitsExtra", "18bits"])
def test_classify_bit_depth_does_not_consume_unknown_text(suffix: str) -> None:
    for assessment in _name_assessments(_target_for(), f"Star Garden S01E05 1080p {suffix}"):
        assert assessment == IdentityAssessment(IdentityVerdict.INSUFFICIENT, _UNCONSUMED)


def test_classify_bit_depth_preserves_numbering_and_extra_guards() -> None:
    for name in ("Star Garden S02E05 8bits", "Star Garden S01E06 8bits", "Star Garden S01E05 Bonus 8bits"):
        for assessment in _name_assessments(_target_for(), name):
            assert is_conflict(assessment)
    for assessment in _name_assessments(_target_for(), "Star Garden 1080p 8bits"):
        assert assessment.verdict is IdentityVerdict.INSUFFICIENT


def _marker_cases() -> list[tuple[dict[str, Any], str]]:
    plain: dict[str, Any] = {"episode_title": None, "other_episode_titles": []}
    first: dict[str, Any] = _target_for(season=1, episode=1, local_episode=1, absolute=1, **plain)
    return [
        (_target_for(season=1, episode=12, local_episode=12, absolute=12), "[FrixySubs] Star Garden - S02E01"),
        (_target_for(season=1, episode=12, local_episode=12, absolute=12), "Star Garden S02E12"),
        (first, "Star Garden - S02E02"),
        (_target_for(season=2, episode=1, local_episode=1, absolute=13, **plain), "Star Garden - S03E01"),
        (_target_for(season=1, episode=13, local_episode=1, absolute=13, **plain), "Star Garden - S01E14"),
        (_target_for(season=1, episode=25, local_episode=1, absolute=25, **plain), "Star Garden - S03E01"),
        (first, "Star Garden - S01E02"),
        (
            _target_for(aliases=["Star Garden Part 2", "Star Garden"], episode=1, local_episode=1, absolute=1, **plain),
            "Star Garden Part 3 - 01",
        ),
    ]


def test_unconsumed_text_keeps_explicit_markers_uncertain() -> None:
    for target, name in _marker_cases():
        for assessment in _name_assessments(target, f"{name} Unknown Words 1080p"):
            assert assessment == IdentityAssessment(IdentityVerdict.INSUFFICIENT, _UNCONSUMED)
            assert not is_conflict(assessment)


def test_reference_other_season_names_stay_uncertain() -> None:
    target: dict[str, Any] = _target_for(season=1, episode=12, local_episode=12, absolute=12)
    for name in (
        "[FrixySubs] Star Garden - S02E01 (13) [1080p CR WEB-DL H.264 AAC] [Napisy PL]",
        "Star Garden S02E12 Part of the Family 1080p NF WEB-DL AAC2.0 H 264-VARYG",
    ):
        for assessment in _name_assessments(target, name):
            assert assessment == IdentityAssessment(IdentityVerdict.INSUFFICIENT, _UNCONSUMED)


def test_clean_name_explicit_markers_conflict() -> None:
    for target, name in _marker_cases():
        for assessment in _name_assessments(target, f"{name} 1080p"):
            assert is_conflict(assessment), (name, assessment)


def test_classify_mapped_absolute_number_stays_ambiguous() -> None:
    target: dict[str, Any] = _target_for(
        season=2, episode=1, local_episode=1, absolute=13, episode_title=None, other_episode_titles=[]
    )
    assessment: IdentityAssessment = _assess(target, {"filename": "Star Garden S02E13 1080p WEB-DL.mkv"})
    assert assessment == IdentityAssessment(
        IdentityVerdict.INSUFFICIENT, "Mapped number equals the target absolute number; numbering is ambiguous."
    )
    assert not is_conflict(assessment)


def test_classify_inherited_named_season_is_not_conflict() -> None:
    target: dict[str, Any] = _target_for(
        aliases=["Fruits Basket The Final Season", "Fruits Basket: 1st Season", "Fruits Basket (2019)"],
        season=3,
        episode=13,
        local_episode=13,
        absolute=63,
        episode_title="See You Again Soon",
        other_episode_titles=[],
        other_series=["Fruits Basket"],
    )
    name: str = "[SubsPlease] Fruits Basket (2019) S3 - 13 (720p) [BFFACE5E].mkv"
    assessment: IdentityAssessment = _assess(target, {"filename": name, "release": name})
    assert assessment == IdentityAssessment(IdentityVerdict.INSUFFICIENT, _UNCONSUMED)


def test_classify_dual_before_language_suffix_is_not_release_group() -> None:
    target: dict[str, Any] = _target_for(
        season=2, episode=1, local_episode=1, absolute=14, episode_title=None, other_episode_titles=[]
    )
    assessment: IdentityAssessment = _assess(target, {"filename": "Star.Garden.S02E01.1080p.WEB-DL-Dual-Lat.mkv"})
    assert assessment.verdict is IdentityVerdict.INSUFFICIENT


def test_classify_dual_before_release_group_is_technical_metadata() -> None:
    target: dict[str, Any] = _target_for(episode_title="It Would Be Embarrassing When We Met Again")
    filename: str = (
        "Star.Garden.S01E05.It.Would.Be.Embarrassing.When.We.Met.Again.1080p.CR.WEB-DL.AAC2.0.H.264.DUAL-VARYG.mkv"
    )
    assert _assess(target, {"filename": filename}).verdict is IdentityVerdict.MATCH
    assert _assess(_target_for(), {"filename": "Star.Garden.S01E05.1080p.WEB-DL.H.264.DUAL-VARYG.mkv"}).verdict is (
        IdentityVerdict.MATCH
    )


def test_classify_multi_before_release_group_is_technical_metadata() -> None:
    for assessment in _name_assessments(_target_for(), "Star.Garden.S01E05.1080p.WEB-DL.H.264.MULTi-VARYG"):
        assert assessment.verdict is IdentityVerdict.MATCH


def test_classify_multi_before_language_suffix_is_not_release_group() -> None:
    target: dict[str, Any] = _target_for(
        season=2, episode=1, local_episode=1, absolute=14, episode_title=None, other_episode_titles=[]
    )
    assessment: IdentityAssessment = _assess(target, {"filename": "Star.Garden.S02E01.1080p.WEB-DL-Multi-Lat.mkv"})
    assert assessment == IdentityAssessment(IdentityVerdict.INSUFFICIENT, _UNCONSUMED)


def _season_entry(**changes: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "aliases": ["Star Garden Season 2 - Night Bloom", "Star Garden"],
        "season": 2,
        "episode": 1,
        "local_episode": 1,
        "absolute": 13,
        "episode_title": None,
        "other_episode_titles": [],
    }
    return _target_for(**{**fields, **changes})


@pytest.mark.parametrize(
    "name",
    [
        "[Erai-raws] Star Garden Season 2 - 01 [1080p CR WEB-DL AVC AAC][MultiSub][55FBD905]",
        "[SubsPlease] Star Garden S2 - 01 (1080p) [9A6F02B8]",
        "[Erai-raws] Star Garden 2nd Season - 01 [720p][Multiple Subtitle]",
    ],
)
def test_classify_franchise_alias_with_target_season_identifies_local_episode(name: str) -> None:
    for assessment in _name_assessments(_season_entry(), name):
        assert assessment.verdict is IdentityVerdict.MATCH


@pytest.mark.parametrize(
    ("target", "name"),
    [
        (_season_entry(), "[Erai-raws] Star Garden Season 2 - 13 [1080p][MultiSub]"),
        (_season_entry(), "[Erai-raws] Star Garden Season 3 - 01 [1080p][MultiSub]"),
        (_season_entry(), "[Erai-raws] Star Garden - 01 [1080p][MultiSub]"),
        (_season_entry(episode=13, absolute=25), "[Erai-raws] Star Garden Season 2 - 01 [1080p][MultiSub]"),
        (
            _season_entry(aliases=["Star Garden Zero", "Star Garden"], season=1, absolute=1),
            "[SubsPlease] Star Garden S1 - 01 (1080p) [9A6F02B8]",
        ),
    ],
)
def test_classify_franchise_alias_without_target_season_and_local_numbering_stays_uncertain(
    target: dict[str, Any], name: str
) -> None:
    for assessment in _name_assessments(target, name):
        assert assessment.verdict is IdentityVerdict.INSUFFICIENT


def test_entry_title_local_number_without_numbering() -> None:
    target: dict[str, Any] = _unnumbered_target()
    name: str = "[Erai-raws] Koori no Jouheki 2nd Season - 01 [1080p CR WEB-DL AVC AAC][MultiSub]"
    assert classify_release_name(target, name).verdict is IdentityVerdict.MATCH
    assert _assess(target, {"filename": f"{name}.mkv"}).verdict is IdentityVerdict.MATCH
    assert _assess(target, {"filename": "Koori no Jouheki - 01.mkv"}) == IdentityAssessment(
        IdentityVerdict.INSUFFICIENT, "A franchise alias does not identify this installment."
    )


def test_sxxexx_without_numbering_stays_uncertain() -> None:
    target: dict[str, Any] = _unnumbered_target()
    for name in ("Koori no Jouheki S02E01 1080p", "The Ramparts of Ice S02E01 1080p NF WEB-DL"):
        for assessment in (classify_release_name(target, name), _assess(target, {"filename": f"{name}.mkv"})):
            assert assessment == IdentityAssessment(IdentityVerdict.INSUFFICIENT, _NO_NUMBERING)
            assert not is_conflict(assessment)


def test_release_context_without_numbering_stays_uncertain() -> None:
    target: dict[str, Any] = _unnumbered_target()
    name: str = "Koori no Jouheki S01E01 1080p"
    for assessment in (
        classify_release_name(target, name),
        _assess(target, {"filename": f"{name}.mkv", "release": name}),
        _assess(target, {"filename": "Koori no Jouheki - 01.mkv", "release": name}),
    ):
        assert assessment.verdict is IdentityVerdict.INSUFFICIENT
        assert not is_conflict(assessment)


def test_classify_release_name_match() -> None:
    for name in ("Star Garden S01E05 1080p WEB-DL AAC2.0 H 264", "[Group] Star Garden - 05 (1080p) [ABCD1234].mkv"):
        assert classify_release_name(_target_for(), name).verdict is IdentityVerdict.MATCH


def test_classify_release_name_other_season() -> None:
    assessment: IdentityAssessment = classify_release_name(_target_for(), "Star Garden S02E05 1080p")
    assert assessment == IdentityAssessment(
        IdentityVerdict.INSUFFICIENT, "Package explicitly identifies a different season."
    )
    assert conflict_label(assessment) == "inny sezon"


def test_classify_release_name_other_episode() -> None:
    assessment: IdentityAssessment = classify_release_name(_target_for(), "Star Garden S01E06 1080p")
    assert assessment.verdict is IdentityVerdict.MISMATCH
    assert conflict_label(assessment) == "inny odcinek"


def test_classify_release_name_unresolved() -> None:
    for name in ("Star Garden 1080p WEB", "Star Garden - 05 Mystery Words"):
        assessment: IdentityAssessment = classify_release_name(_target_for(), name)
        assert assessment.verdict is IdentityVerdict.INSUFFICIENT
        assert not is_conflict(assessment)
    assert classify_release_name(_target_for(), " ") == IdentityAssessment(
        IdentityVerdict.INSUFFICIENT, "No selected file."
    )
    assert classify_release_name(_target_for(), 5) == IdentityAssessment(  # type: ignore[arg-type]
        IdentityVerdict.INSUFFICIENT, "Malformed candidate metadata."
    )


@pytest.mark.parametrize(
    ("target", "name"),
    [
        (_target_for(), "Star Garden S01E06 The Silent Winter Night 1080p WEB-DL"),
        (_target_for(), "Star Garden - 06 - The Silent Winter Night"),
        (_target_for(), "Star Garden S01E06 The Silent WinterNight 1080p"),
        (_target_for(), "[Group] Star Garden - 06 The Silent Winter Night (1080p) [ABCD1234]"),
        (
            _target_for(season=2, episode=1, local_episode=1, absolute=13),
            "Star.Garden.S02E13.The.Silent.Winter.Night.1080p.CR.WEB-DL.AAC2.0.H.264-VARYG",
        ),
        (
            {**_unnumbered_target(), "other_episode_titles": ["The Silent Winter Night"]},
            "Koori no Jouheki - 02 - The Silent Winter Night",
        ),
        (_target_for(season=2, episode=1, local_episode=1, absolute=13), "Star Garden - 13 - The Silent Winter Night"),
        (
            _target_for(season=1, episode=13, local_episode=1, absolute=13),
            "Star Garden S01E01 The Silent Winter Night 1080p",
        ),
    ],
)
def test_classify_other_episode_title_after_conflicting_number_is_conflict(target: dict[str, Any], name: str) -> None:
    for assessment in _name_assessments(target, name):
        assert assessment == IdentityAssessment(IdentityVerdict.MISMATCH, _OTHER_EPISODE_TITLE)
        assert conflict_label(assessment) == "tytuł innego odcinka"


@pytest.mark.parametrize(
    ("target", "name"),
    [
        (_target_for(), "Star Garden S01E05 The Silent Winter Night 1080p"),
        (_target_for(), "Star Garden - 05 - The Silent Winter Night"),
        (
            {**_unnumbered_target(), "other_episode_titles": ["The Silent Winter Night"]},
            "Koori no Jouheki S02E01 The Silent Winter Night 1080p",
        ),
        (
            {**_unnumbered_target(), "other_episode_titles": ["The Silent Winter Night"]},
            "Koori no Jouheki S02E05 The Silent Winter Night 1080p",
        ),
        (
            _target_for(season=1, episode=13, local_episode=1, absolute=13),
            "Star Garden S01E13 The Silent Winter Night 1080p",
        ),
        (_target_for(), "Star Garden S01E06 The Silent Winter Night Extended Cut 1080p"),
        (_target_for(), "Star Garden S01E06 Prologue The Silent Winter Night 1080p"),
        (_target_for(other_episode_titles=["Snow!"]), "Star Garden S01E06 Snow 1080p"),
        (_target_for(other_episode_titles=["Snowy"]), "Star Garden - 06 - Snowy"),
        (_target_for(other_episode_titles=["Journey"]), "Star Garden S01E06 Journey 1080p"),
        (
            _target_for(other_episode_titles=["A Journey Through Clouds Again"]),
            "Star Garden S01E06 A Journey Through Clouds Again 1080p",
        ),
        (_target_for(other_episode_titles=["Return to Star Garden"]), "Star Garden S01E06 Return to Star Garden 1080p"),
    ],
)
def test_classify_other_episode_title_without_full_evidence_stays_uncertain(target: dict[str, Any], name: str) -> None:
    for assessment in _name_assessments(target, name):
        assert assessment == IdentityAssessment(IdentityVerdict.INSUFFICIENT, _UNCONSUMED)
        assert not is_conflict(assessment)

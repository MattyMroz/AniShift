from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from harness import Composed, Resolved, composed_fixture  # noqa: F401

from anishift.application.acquisition import MAX_QUERIES, ReleaseChoice, SeasonContext
from anishift.services.catalog import TitleStatus
from anishift.services.torrents.nyaa import CATEGORY_ENGLISH_TRANSLATED, CATEGORY_NON_ENGLISH_TRANSLATED

if TYPE_CHECKING:
    from collections.abc import Iterator

SOLO_SEASON_1 = "Ore dake Level Up na Ken"
SOLO_SEASON_2 = "Arise from the Shadow"
MUSHOKU_SEASON_3 = "III"


def _choices(found: Resolved) -> Iterator[ReleaseChoice]:
    return (choice for group in found.catalog.groups for choice in group.choices)


def test_solo_leveling_episode_one_finds_the_first_season(composed: Composed) -> None:
    found = composed.resolve("solo leveling 1", SOLO_SEASON_1)

    first = found.candidates[0]
    assert (first.romaji, first.english) == ("Ore dake Level Up na Ken", "Solo Leveling")
    assert first.status is TitleStatus.FINISHED
    assert first.episodes == 12
    assert first is found.candidate
    assert found.context == SeasonContext(index=1, offset=0, episodes=12)


def test_solo_leveling_episode_one_lists_the_subsplease_release_of_that_episode(composed: Composed) -> None:
    found = composed.resolve("solo leveling 1", SOLO_SEASON_1)

    (subsplease,) = found.groups_of("SubsPlease")
    (choice,) = subsplease.choices
    assert subsplease.subtitle_language == "en"
    assert choice.episode == Decimal(1)
    assert choice.name.resolution == 1080
    assert choice.release.subtitle_language == "en"


def test_solo_leveling_episode_one_lists_only_that_episode_in_watchable_quality(composed: Composed) -> None:
    found = composed.resolve("solo leveling 1", SOLO_SEASON_1)

    assert {choice.episode for choice in _choices(found)} == {Decimal(1)}
    assert found.catalog.filtered > 0
    assert not [choice for choice in _choices(found) if choice.name.dubbed]
    assert not [choice for choice in _choices(found) if choice.release.subtitle_language is None]


def test_solo_leveling_episode_one_lists_other_season_groups_last(composed: Composed) -> None:
    found = composed.resolve("solo leveling 1", SOLO_SEASON_1)

    foreign = [index for index, group in enumerate(found.catalog.groups) if all(c.other_season for c in group.choices)]
    chosen = [
        index for index, group in enumerate(found.catalog.groups) if not all(c.other_season for c in group.choices)
    ]
    assert foreign
    assert chosen
    assert max(chosen) < min(foreign)


def test_mushoku_tensei_third_season_counts_the_episodes_that_aired_before_it(composed: Composed) -> None:
    found = composed.resolve("mushoku tensei", MUSHOKU_SEASON_3)

    assert (found.context.index, found.context.offset) == (3, 48)


def test_mushoku_tensei_third_season_lists_the_erai_raws_release_of_the_newest_episode(composed: Composed) -> None:
    found = composed.resolve("mushoku tensei", MUSHOKU_SEASON_3)

    erai = found.groups_of("Erai-raws")[0]
    assert "III" in erai.series
    assert erai.choices[0].episode == Decimal(10)
    assert not erai.choices[0].other_season


def test_mushoku_tensei_third_season_reports_the_french_group_as_french(composed: Composed) -> None:
    found = composed.resolve("mushoku tensei", MUSHOKU_SEASON_3)

    tsundere = found.groups_of("Tsundere-Raws")
    assert tsundere
    assert {group.subtitle_language for group in tsundere} == {"fr"}


def test_mushoku_tensei_third_season_merges_series_titles_differing_only_in_punctuation(composed: Composed) -> None:
    found = composed.resolve("mushoku tensei", MUSHOKU_SEASON_3)

    (cytox,) = found.groups_of("Cytox")
    assert {choice.name.series for choice in cytox.choices} == {
        "Mushoku Tensei Jobless Reincarnation",
        "Mushoku Tensei: Jobless Reincarnation",
    }


def test_mushoku_tensei_third_season_reads_second_season_releases_as_another_season(composed: Composed) -> None:
    found = composed.resolve("mushoku tensei", MUSHOKU_SEASON_3)

    second = [choice for group in found.groups_of("VARYG") for choice in group.choices if choice.name.season == 2]
    assert second
    assert all(choice.other_season for choice in second)


def test_solo_leveling_season_two_episode_one_places_the_season_in_the_series(composed: Composed) -> None:
    found = composed.resolve("solo leveling season 2 1", SOLO_SEASON_2)

    assert (found.context.index, found.context.offset, found.context.episodes) == (2, 12, 13)


def test_solo_leveling_season_two_episode_one_reads_the_absolute_number_of_the_release(composed: Composed) -> None:
    found = composed.resolve("solo leveling season 2 1", SOLO_SEASON_2)

    (subsplease,) = found.groups_of("SubsPlease")
    assert (subsplease.choices[0].episode, subsplease.choices[0].absolute) == (Decimal(1), Decimal(13))
    assert [choice for choice in _choices(found) if choice.absolute == Decimal(13)]


def test_solo_leveling_season_two_recognizes_the_french_group_as_the_searched_title(composed: Composed) -> None:
    found = composed.resolve("solo leveling season 2 1", SOLO_SEASON_2)

    tsundere = [group for group in found.groups_of("Tsundere-Raws") if group.series == "Solo Leveling"]
    assert tsundere
    assert tsundere[0].matches_title


def test_one_title_search_stays_inside_the_query_budget_and_asks_both_categories(composed: Composed) -> None:
    composed.resolve("solo leveling season 2 1", SOLO_SEASON_2)

    asked: dict[str, set[str]] = {}
    for query, category in composed.nyaa_queries:
        asked.setdefault(query, set()).add(category)
    assert len(asked) <= MAX_QUERIES
    assert all(
        categories == {CATEGORY_ENGLISH_TRANSLATED, CATEGORY_NON_ENGLISH_TRANSLATED} for categories in asked.values()
    )
    assert len(composed.nyaa_queries) == 2 * len(asked)

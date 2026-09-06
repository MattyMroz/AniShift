from __future__ import annotations

from decimal import Decimal

import pytest

from anishift.services.torrents.query import EpisodeRange, SearchQuery, parse_query


@pytest.mark.parametrize(
    ("text", "title", "first", "last"),
    [
        ("solo leveling 1", "solo leveling", Decimal(1), Decimal(1)),
        ("frieren 4-10", "frieren", Decimal(4), Decimal(10)),
        ("frieren 4 - 10", "frieren", Decimal(4), Decimal(10)),
        ("frieren 5-", "frieren", Decimal(5), None),
        ("kimetsu -3", "kimetsu", None, Decimal(3)),
        ("frieren odc 3", "frieren", Decimal(3), Decimal(3)),
        ("frieren odc. 3", "frieren", Decimal(3), Decimal(3)),
        ("frieren ep 3", "frieren", Decimal(3), Decimal(3)),
        ("frieren e03", "frieren", Decimal(3), Decimal(3)),
        ("Frieren Episode 12", "Frieren", Decimal(12), Decimal(12)),
        ("solo leveling season 2 1", "solo leveling season 2", Decimal(1), Decimal(1)),
        ("  bleach   10.5  ", "bleach", Decimal("10.5"), Decimal("10.5")),
    ],
)
def test_parse_query_reads_the_trailing_episode_marker(
    text: str,
    title: str,
    first: Decimal | None,
    last: Decimal | None,
) -> None:
    query: SearchQuery = parse_query(text)
    assert query.title == title
    assert query.episodes == EpisodeRange(first=first, last=last)


@pytest.mark.parametrize(
    ("text", "title"),
    [
        ("mushoku tensei", "mushoku tensei"),
        ("solo leveling 2024", "solo leveling 2024"),
        ("frieren 1080p", "frieren 1080p"),
        ("1", "1"),
        ("frieren 1 uncut", "frieren 1 uncut"),
    ],
)
def test_parse_query_keeps_the_whole_phrase_as_the_title(text: str, title: str) -> None:
    query: SearchQuery = parse_query(text)
    assert query == SearchQuery(title=title, episodes=None)


@pytest.mark.parametrize(
    ("episodes", "text"),
    [
        (EpisodeRange(first=Decimal(1), last=Decimal(1)), "1"),
        (EpisodeRange(first=Decimal(4), last=Decimal(10)), "4–10"),
        (EpisodeRange(first=Decimal(5), last=None), "5–"),
        (EpisodeRange(first=None, last=Decimal(3)), "–3"),
    ],
)
def test_episode_range_text_carries_no_language(episodes: EpisodeRange, text: str) -> None:
    assert episodes.text == text


@pytest.mark.parametrize(
    ("episodes", "episode", "expected"),
    [
        (EpisodeRange(first=Decimal(4), last=Decimal(10)), Decimal(4), True),
        (EpisodeRange(first=Decimal(4), last=Decimal(10)), Decimal(10), True),
        (EpisodeRange(first=Decimal(4), last=Decimal(10)), Decimal(3), False),
        (EpisodeRange(first=Decimal(4), last=Decimal(10)), Decimal(11), False),
        (EpisodeRange(first=Decimal(5), last=None), Decimal(120), True),
        (EpisodeRange(first=None, last=Decimal(3)), Decimal(1), True),
        (EpisodeRange(first=None, last=Decimal(3)), Decimal("3.5"), False),
    ],
)
def test_episode_range_contains(episodes: EpisodeRange, episode: Decimal, expected: bool) -> None:
    assert episodes.contains(episode) is expected

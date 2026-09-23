"""Anime title catalog: candidates, aliases, and season episode offsets."""

from anishift.services.catalog.anilist import AniListCatalog
from anishift.services.catalog.errors import TitleCatalogError
from anishift.services.catalog.types import (
    EpisodeAiring,
    PrequelEntry,
    SeasonAiring,
    TitleCandidate,
    TitleStatus,
    is_cour_title,
)

__all__ = [
    "AniListCatalog",
    "EpisodeAiring",
    "PrequelEntry",
    "SeasonAiring",
    "TitleCandidate",
    "TitleCatalogError",
    "TitleStatus",
    "is_cour_title",
]

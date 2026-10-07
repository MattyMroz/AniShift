"""Anime title catalog: candidates, aliases, and season episode offsets."""

from anishift.services.catalog.anilist import AniListCatalog
from anishift.services.catalog.anizip import AniZipCatalog
from anishift.services.catalog.arm import ArmCatalog, ArmIds
from anishift.services.catalog.errors import TitleCatalogError
from anishift.services.catalog.kitsu import KitsuCatalog
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
    "AniZipCatalog",
    "ArmCatalog",
    "ArmIds",
    "EpisodeAiring",
    "KitsuCatalog",
    "PrequelEntry",
    "SeasonAiring",
    "TitleCandidate",
    "TitleCatalogError",
    "TitleStatus",
    "is_cour_title",
]

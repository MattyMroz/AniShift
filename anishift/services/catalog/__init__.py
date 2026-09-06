"""Anime title catalog: candidates, aliases, and season episode offsets."""

from anishift.services.catalog.anilist import AniListCatalog
from anishift.services.catalog.errors import TitleCatalogError
from anishift.services.catalog.types import TitleCandidate, TitleStatus

__all__ = [
    "AniListCatalog",
    "TitleCandidate",
    "TitleCatalogError",
    "TitleStatus",
]

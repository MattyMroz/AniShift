"""Catalog domain exception hierarchy."""

from __future__ import annotations

from anishift.errors import TransientError

__all__ = ["TitleCatalogError"]


class TitleCatalogError(TransientError):
    """Raised when the title catalog is unreachable or answers with an unusable body."""

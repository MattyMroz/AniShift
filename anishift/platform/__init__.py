"""Platform layer — OS detection and external-binary resolution.

Trimmed vs. MangaShift: no GPU / torch-wheel concerns (AniShift has no local
ML models). Just OS detection and locating ``external/bin`` binaries per OS.
"""

from __future__ import annotations

from anishift.platform.binaries import (
    Binary,
    BinaryNotFoundError,
    external_bin_root,
    is_windows,
    require_binary,
    resolve_binary,
)

__all__ = [
    "Binary",
    "BinaryNotFoundError",
    "external_bin_root",
    "is_windows",
    "require_binary",
    "resolve_binary",
]

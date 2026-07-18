"""Platform layer — OS detection and external-binary resolution.

Detects the OS and locates ``external/bin`` binaries per platform.
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

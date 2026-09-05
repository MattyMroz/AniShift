"""Palantir token variable names and precedence, free of any provider SDK."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Final

from anishift.utils.logger import get_logger

__all__ = [
    "PALANTIR_TOKEN_COMPAT_ENV_VAR",
    "PALANTIR_TOKEN_ENV_VAR",
    "PALANTIR_TOKEN_ENV_VARS",
    "resolve_palantir_token",
]

logger = get_logger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

PALANTIR_TOKEN_ENV_VAR: Final[str] = "ANISHIFT_PALANTIR_TOKEN"  # noqa: S105
"""Canonical environment variable; the only name any writer may target."""

PALANTIR_TOKEN_COMPAT_ENV_VAR: Final[str] = "FOUNDRY_API_TOKEN"  # noqa: S105
"""Legacy environment variable read only when the canonical one is empty."""

PALANTIR_TOKEN_ENV_VARS: Final[tuple[str, ...]] = (
    PALANTIR_TOKEN_ENV_VAR,
    PALANTIR_TOKEN_COMPAT_ENV_VAR,
)
"""Read order of the token variables, canonical first."""


def resolve_palantir_token(environ: Mapping[str, str] | None = None) -> str:
    """Return the configured token, preferring the canonical variable."""
    source: Mapping[str, str] = os.environ if environ is None else environ
    for variable in PALANTIR_TOKEN_ENV_VARS:
        token: str = source.get(variable, "").strip()
        if not token:
            continue
        if variable != PALANTIR_TOKEN_ENV_VAR:
            logger.debug("Palantir token read from the compatibility variable", variable=variable)
        return token
    return ""

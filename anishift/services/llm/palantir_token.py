"""Palantir token variable names and precedence, free of any provider SDK.

This is a leaf module on purpose: it imports nothing from ``anishift.services``
and pulls no provider package. Both ``anishift.config.settings`` and the
Palantir engine adapter depend on this single owner of the precedence rule
instead of on each other, so a process environment and an ``.env`` file cannot
resolve the token differently and the settings module stays out of the
provider import graph.

Public API:
    PALANTIR_TOKEN_ENV_VAR, PALANTIR_TOKEN_COMPAT_ENV_VAR,
        PALANTIR_TOKEN_ENV_VARS: Canonical and compatibility variable names.
    resolve_palantir_token: Read the token, returning ``""`` when unset.
"""

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
    """Return the configured token, preferring the canonical variable.

    Args:
        environ: Environment mapping to read; the process environment by
            default.

    Returns:
        The stripped token of the first variable that holds a visible value, or
        ``""`` when neither variable is configured.
    """
    source: Mapping[str, str] = os.environ if environ is None else environ
    for variable in PALANTIR_TOKEN_ENV_VARS:
        token: str = source.get(variable, "").strip()
        if not token:
            continue
        if variable != PALANTIR_TOKEN_ENV_VAR:
            logger.debug("Palantir token read from the compatibility variable", variable=variable)
        return token
    return ""

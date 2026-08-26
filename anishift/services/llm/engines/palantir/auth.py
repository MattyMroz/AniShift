"""Palantir token retrieval and the single Authorization header builder.

The canonical secret is ``ANISHIFT_PALANTIR_TOKEN``. ``FOUNDRY_API_TOKEN`` is
read only for compatibility with an older setup and only when the canonical
variable holds nothing; a writer such as ``/connect`` always targets the
canonical name.

``resolve_palantir_token`` is the ONE algorithm that implements this precedence:
strip, skip a blank value, canonical before compatibility.
``Settings.palantir_token`` delegates to it with the values pydantic-settings
gathered from the environment and from ``.env`` instead of re-implementing the
order, because two mechanisms for one rule drift apart — a blank canonical value
being the case that breaks first. This module therefore stays free of any
``anishift.config`` import; the dependency runs the other way.

Every request header is built here, from an allowlist: exactly one
``Authorization: Bearer <token>`` plus the JSON negotiation headers. The token
itself is never logged, never rendered and never returned by
``redacted_headers``.

Public API:
    PALANTIR_TOKEN_ENV_VAR, PALANTIR_TOKEN_COMPAT_ENV_VAR,
        PALANTIR_TOKEN_ENV_VARS: Canonical and compatibility variable names.
    resolve_palantir_token: Read the token, returning ``""`` when unset.
    require_palantir_token: Read the token or raise an authentication error.
    validated_palantir_token: Reject a token that cannot be sent in a header.
    authorization_headers: Build the allowlisted request headers.
    redacted_headers: Copy headers with every secret value masked.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Final

from anishift.services.llm.engines.palantir.errors import raise_palantir_auth_error
from anishift.utils.logger import get_logger

__all__ = [
    "PALANTIR_TOKEN_COMPAT_ENV_VAR",
    "PALANTIR_TOKEN_ENV_VAR",
    "PALANTIR_TOKEN_ENV_VARS",
    "REDACTED_HEADER_VALUE",
    "authorization_headers",
    "redacted_headers",
    "require_palantir_token",
    "resolve_palantir_token",
    "validated_palantir_token",
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
"""Read order of the token variables, canonical first.

``resolve_palantir_token`` walks this order, and ``Settings`` reaches the same
result by delegating to that function, so a process environment and a ``.env``
file cannot resolve the token differently.
"""

REDACTED_HEADER_VALUE: Final[str] = "<redacted>"
"""Placeholder rendered instead of a secret header value."""

_SECRET_HEADER_NAMES: Final[frozenset[str]] = frozenset({"authorization", "proxy-authorization"})
"""Casefolded header names whose value must never be rendered or logged."""

_JSON_MEDIA_TYPE: Final[str] = "application/json"
"""Only media type the proxy protocols exchange."""


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


def require_palantir_token(environ: Mapping[str, str] | None = None) -> str:
    """Return the configured token or fail before any network access.

    Args:
        environ: Environment mapping to read; the process environment by
            default.

    Returns:
        The stripped token.

    Raises:
        LlmAuthError: Neither the canonical nor the compatibility variable holds
            a value.
    """
    token: str = resolve_palantir_token(environ)
    if not token:
        raise_palantir_auth_error(
            "Palantir token is not configured",
            field_name=PALANTIR_TOKEN_ENV_VAR,
            suggestion=f"Set {PALANTIR_TOKEN_ENV_VAR} in the environment or the .env file.",
        )
    return token


def authorization_headers(token: str) -> dict[str, str]:
    """Build the allowlisted headers of one proxy request.

    Args:
        token: Token already resolved from the environment or ``Settings``.

    Returns:
        A fresh mapping with the single bearer authorization header and the
        JSON negotiation headers, and nothing derived from user input.

    Raises:
        LlmAuthError: The token is empty or carries characters that cannot be
            sent in a header; the offending value is never echoed.
    """
    validated: str = validated_palantir_token(token)
    return {
        "Authorization": f"Bearer {validated}",
        "Content-Type": _JSON_MEDIA_TYPE,
        "Accept": _JSON_MEDIA_TYPE,
    }


def redacted_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Copy *headers* with every secret value replaced by a placeholder.

    Args:
        headers: Headers of one proxy request.

    Returns:
        A mapping safe to render or log, where an authorization value is
        replaced instead of truncated, so no prefix of the token survives.
    """
    return {
        name: REDACTED_HEADER_VALUE if name.casefold() in _SECRET_HEADER_NAMES else value
        for name, value in headers.items()
    }


def validated_palantir_token(token: str) -> str:
    """Return a token usable in a header, rejecting an unsendable value.

    Args:
        token: Token resolved from the environment or from ``Settings``.

    Returns:
        The token unchanged.

    Raises:
        LlmAuthError: The token is empty or carries whitespace or control
            characters; the value itself is never part of the failure.
    """
    if not token.strip():
        raise_palantir_auth_error(
            "Palantir token is not configured",
            field_name=PALANTIR_TOKEN_ENV_VAR,
            suggestion=f"Set {PALANTIR_TOKEN_ENV_VAR} in the environment or the .env file.",
        )
    if any(character.isspace() or not character.isprintable() for character in token):
        raise_palantir_auth_error(
            "Palantir token contains whitespace or control characters",
            field_name=PALANTIR_TOKEN_ENV_VAR,
            suggestion=f"Store {PALANTIR_TOKEN_ENV_VAR} as one line without quotes or spaces.",
        )
    return token

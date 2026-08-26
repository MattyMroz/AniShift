"""Palantir token requirements and the single Authorization header builder.

The canonical secret is ``ANISHIFT_PALANTIR_TOKEN``. ``FOUNDRY_API_TOKEN`` is
read only for compatibility with an older setup and only when the canonical
variable holds nothing; a writer such as ``/connect`` always targets the
canonical name.

The precedence rule and its variable names live in
``anishift.services.llm.palantir_token`` — a leaf module that pulls no provider
package — so ``anishift.config.settings`` can delegate to that rule without
importing the Palantir engine. This module re-exports the same names for every
caller that already reaches through the ``palantir`` package, and adds the
header allowlist and secret-safe rendering on top.

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

from collections.abc import Mapping
from typing import Final

from anishift.services.llm.engines.palantir.errors import raise_palantir_auth_error
from anishift.services.llm.palantir_token import (
    PALANTIR_TOKEN_COMPAT_ENV_VAR,
    PALANTIR_TOKEN_ENV_VAR,
    PALANTIR_TOKEN_ENV_VARS,
    resolve_palantir_token,
)

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

# ── Constants ────────────────────────────────────────────────────────────────

REDACTED_HEADER_VALUE: Final[str] = "<redacted>"
"""Placeholder rendered instead of a secret header value."""

_SECRET_HEADER_NAMES: Final[frozenset[str]] = frozenset({"authorization", "proxy-authorization"})
"""Casefolded header names whose value must never be rendered or logged."""

_JSON_MEDIA_TYPE: Final[str] = "application/json"
"""Only media type the proxy protocols exchange."""


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

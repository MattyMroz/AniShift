"""Palantir token requirements and the single Authorization header builder."""

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
    """Return the configured token or fail before any network access."""
    token: str = resolve_palantir_token(environ)
    if not token:
        raise_palantir_auth_error(
            "Palantir token is not configured",
            field_name=PALANTIR_TOKEN_ENV_VAR,
            suggestion=f"Set {PALANTIR_TOKEN_ENV_VAR} in the environment or the .env file.",
        )
    return token


def authorization_headers(token: str) -> dict[str, str]:
    """Build the allowlisted headers of one proxy request."""
    validated: str = validated_palantir_token(token)
    return {
        "Authorization": f"Bearer {validated}",
        "Content-Type": _JSON_MEDIA_TYPE,
        "Accept": _JSON_MEDIA_TYPE,
    }


def redacted_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Copy *headers* with every secret value replaced by a placeholder."""
    return {
        name: REDACTED_HEADER_VALUE if name.casefold() in _SECRET_HEADER_NAMES else value
        for name, value in headers.items()
    }


def validated_palantir_token(token: str) -> str:
    """Return a token usable in a header, rejecting an unsendable value."""
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

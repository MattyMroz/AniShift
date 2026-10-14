"""Palantir token requirements and the single Authorization header builder."""

from __future__ import annotations

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
    "authorization_headers",
    "resolve_palantir_token",
    "validated_palantir_token",
]

# ── Constants ────────────────────────────────────────────────────────────────

_JSON_MEDIA_TYPE: Final[str] = "application/json"
"""Only media type the proxy protocols exchange."""


def authorization_headers(token: str) -> dict[str, str]:
    """Build the allowlisted headers of one proxy request."""
    validated: str = validated_palantir_token(token)
    return {
        "Authorization": f"Bearer {validated}",
        "Content-Type": _JSON_MEDIA_TYPE,
        "Accept": _JSON_MEDIA_TYPE,
    }


def validated_palantir_token(token: str, *, field_name: str = PALANTIR_TOKEN_ENV_VAR) -> str:
    """Return a token usable in a header, rejecting an unsendable value."""
    if not token.strip():
        raise_palantir_auth_error(
            "Palantir token is not configured",
            field_name=field_name,
            suggestion=(
                f"Set {field_name} in the environment or the .env file."
                if field_name == PALANTIR_TOKEN_ENV_VAR
                else f"Set {field_name} to a valid Palantir token."
            ),
        )
    if any(character.isspace() or not character.isprintable() for character in token):
        raise_palantir_auth_error(
            "Palantir token contains whitespace or control characters",
            field_name=field_name,
            suggestion=f"Store {field_name} as one line without quotes or spaces.",
        )
    return token

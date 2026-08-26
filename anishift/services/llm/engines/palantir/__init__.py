"""Palantir Foundry proxy adapter: configuration, authorization and routing.

The modules here stay inert on import: they resolve the token, assemble the
endpoint from the catalog and shape a request per protocol, without creating an
HTTP client or opening a connection. The engine that sends a request is added on
top of these contracts.

Importing this package therefore loads no HTTP client, no provider SDK and no
other engine — reaching into a sibling engine package for a shared value would
break that, because a package ``__init__`` evaluates its own service module and
pulls the SDK in with it.
"""

from __future__ import annotations

from anishift.services.llm.engines.palantir.auth import (
    PALANTIR_TOKEN_COMPAT_ENV_VAR,
    PALANTIR_TOKEN_ENV_VAR,
    PALANTIR_TOKEN_ENV_VARS,
    REDACTED_HEADER_VALUE,
    authorization_headers,
    redacted_headers,
    require_palantir_token,
    resolve_palantir_token,
    validated_palantir_token,
)
from anishift.services.llm.engines.palantir.config import (
    PalantirGenerationOptions,
    PalantirModelConfig,
    palantir_model_config,
)
from anishift.services.llm.engines.palantir.errors import (
    PALANTIR_ENGINE_ID,
    PalantirResponseDefect,
    palantir_blocked_error,
    palantir_response_error,
    palantir_status_error,
    palantir_timeout_error,
    palantir_unavailable_error,
    raise_palantir_auth_error,
    raise_palantir_config_error,
)
from anishift.services.llm.engines.palantir.protocols import (
    PalantirHttpRequest,
    PalantirRequestBuilder,
    build_palantir_request,
    request_builder,
)

__all__ = [
    "PALANTIR_ENGINE_ID",
    "PALANTIR_TOKEN_COMPAT_ENV_VAR",
    "PALANTIR_TOKEN_ENV_VAR",
    "PALANTIR_TOKEN_ENV_VARS",
    "REDACTED_HEADER_VALUE",
    "PalantirGenerationOptions",
    "PalantirHttpRequest",
    "PalantirModelConfig",
    "PalantirRequestBuilder",
    "PalantirResponseDefect",
    "authorization_headers",
    "build_palantir_request",
    "palantir_blocked_error",
    "palantir_model_config",
    "palantir_response_error",
    "palantir_status_error",
    "palantir_timeout_error",
    "palantir_unavailable_error",
    "raise_palantir_auth_error",
    "raise_palantir_config_error",
    "redacted_headers",
    "request_builder",
    "require_palantir_token",
    "resolve_palantir_token",
    "validated_palantir_token",
]

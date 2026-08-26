"""Provider-neutral Palantir model configuration.

One catalog alias becomes one immutable ``PalantirModelConfig``: the wire
protocol, the fully assembled provider base URL, the provider model identifier
and the token. Assembling the endpoint is the job of this module — the
enrollment address and the relative proxy route are joined here, never by a
view and never by a request builder, so no screen can invent an address.

The configuration is inert: it validates values, holds no client, opens no
socket and imports no HTTP library. The first connection can only happen later,
when an engine completes or probes.

Public API:
    PalantirModelConfig: Frozen configuration of one alias, token excluded from
        ``repr``.
    PalantirGenerationOptions: Already validated generation limits a protocol
        builder may apply.
    palantir_model_config: Assemble and validate a configuration from catalog
        values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final
from urllib.parse import SplitResult, urlsplit

from anishift.services.llm.engines.palantir.auth import validated_palantir_token
from anishift.services.llm.engines.palantir.errors import raise_palantir_config_error
from anishift.services.llm.wire_protocol import ModelProtocol
from anishift.utils.logger import get_logger

__all__ = [
    "PalantirGenerationOptions",
    "PalantirModelConfig",
    "palantir_model_config",
]

logger = get_logger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_REQUIRED_SCHEME: Final[str] = "https"
"""Only URL scheme an enrollment address may use."""


@dataclass(frozen=True, slots=True)
class PalantirGenerationOptions:
    """Generation limits a protocol builder may put into a request body.

    The values are the already validated ones of ``LlmConfig``; this record only
    carries them into the protocol mappers, and applies no range checks of its
    own.

    Attributes:
        temperature: Sampling temperature, ``None`` to let the provider decide.
        top_p: Nucleus sampling probability, ``None`` to leave it unset.
        max_output_tokens: Output limit, ``None`` to leave it unset for the
            protocols that treat it as optional.
    """

    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class PalantirModelConfig:
    """Everything one Palantir request needs, resolved from the catalog.

    Attributes:
        alias: Catalog alias the user selected.
        provider_id: Catalog provider whose route carries the request.
        protocol: Wire protocol declared by that provider.
        base_url: Enrollment address joined with the relative proxy route,
            without a trailing slash.
        provider_model_id: Exact provider model identifier or RID.
        token: Palantir token, kept out of ``repr`` so no log, panel or
            traceback can render it.
    """

    alias: str
    provider_id: str
    protocol: ModelProtocol
    base_url: str
    provider_model_id: str
    token: str = field(repr=False)

    def __post_init__(self) -> None:
        """Validate every field before any client or request can be built.

        Raises:
            LlmConfigError: A field is empty, the protocol is outside the
                catalog vocabulary, or the base URL is not an https address.
            LlmAuthError: The token is missing or unsendable.
        """
        _require_text(self.alias, field_name="alias", subject="Palantir model alias")
        _require_text(self.provider_id, field_name="provider_id", subject="Palantir provider ID")
        _require_text(
            self.provider_model_id,
            field_name="provider_model_id",
            subject="Palantir provider model ID",
        )
        _require_protocol(self.protocol)
        _require_base_url(self.base_url)
        validated_palantir_token(self.token)


def palantir_model_config(  # noqa: PLR0913 - one explicit argument per resolved catalog value
    *,
    alias: str,
    provider_id: str,
    protocol: ModelProtocol,
    enrollment_base_url: str,
    provider_path: str,
    provider_model_id: str,
    token: str,
) -> PalantirModelConfig:
    """Assemble one configuration from validated catalog values and a token.

    Args:
        alias: Catalog alias the user selected.
        provider_id: Catalog provider of that alias.
        protocol: Wire protocol the provider entry declares.
        enrollment_base_url: Enrollment address the caller resolved from settings.
        provider_path: Relative proxy route of the provider entry.
        provider_model_id: Provider model identifier or RID of the alias.
        token: Token resolved from the environment or from ``Settings``.

    Returns:
        The configuration whose ``base_url`` already joins the enrollment
        address with the proxy route, keeping any path prefix of the
        enrollment.

    Raises:
        LlmConfigError: The enrollment address is not an https address, the
            route is not relative, or a value is empty.
        LlmAuthError: The token is missing or unsendable.
    """
    config: PalantirModelConfig = PalantirModelConfig(
        alias=alias.strip(),
        provider_id=provider_id.strip(),
        protocol=protocol,
        base_url=_joined_base_url(enrollment_base_url, provider_path),
        provider_model_id=provider_model_id.strip(),
        token=token,
    )
    logger.debug(
        "Palantir model configuration assembled",
        alias=config.alias,
        provider_id=config.provider_id,
        protocol=config.protocol.value,
    )
    return config


def _joined_base_url(enrollment_base_url: str, provider_path: str) -> str:
    """Join the enrollment address with the relative route of the provider."""
    enrollment: str = enrollment_base_url.strip()
    _require_base_url(enrollment)
    route: str = _relative_route(provider_path)
    if not route:
        return enrollment.rstrip("/")
    return f"{enrollment.rstrip('/')}/{route}"


def _relative_route(provider_path: str) -> str:
    """Return the route without its surrounding slashes, rejecting an address."""
    route: str = provider_path.strip()
    parts: SplitResult = urlsplit(route)
    if not route.startswith("/") or parts.scheme or parts.netloc or parts.query or parts.fragment:
        raise_palantir_config_error(
            "Palantir provider route is not a relative proxy path",
            field_name="provider_path",
            suggestion="Use a catalog route starting with / and carrying no host, query or fragment.",
        )
    return route.strip("/")


def _require_base_url(base_url: str) -> None:
    """Reject anything that is not a plain https enrollment address."""
    parts: SplitResult = urlsplit(base_url.strip())
    if parts.scheme != _REQUIRED_SCHEME or not parts.netloc or parts.query or parts.fragment:
        raise_palantir_config_error(
            "Palantir enrollment address must be an https URL without a query or a fragment",
            field_name="base_url",
            suggestion="Set the enrollment address to the https origin of your enrollment in /connect.",
        )


def _require_protocol(protocol: ModelProtocol) -> None:
    """Reject a protocol outside the four values the catalog defines."""
    if isinstance(protocol, ModelProtocol):
        return
    raise_palantir_config_error(
        "Palantir provider declares a protocol outside the supported set",
        field_name="protocol",
        suggestion=f"Use one of: {', '.join(item.value for item in ModelProtocol)}.",
    )


def _require_text(value: str, *, field_name: str, subject: str) -> None:
    """Reject an empty or blank identifier, naming the field but not the value."""
    if value.strip():
        return
    raise_palantir_config_error(
        f"{subject} cannot be empty",
        field_name=field_name,
        suggestion=f"Select a catalog alias whose {field_name} is set.",
    )

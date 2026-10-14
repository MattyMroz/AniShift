"""Provider-neutral Palantir model configuration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final
from urllib.parse import SplitResult, urlsplit

from anishift.services.llm.engines.palantir.auth import validated_palantir_token
from anishift.services.llm.engines.palantir.constants import PALANTIR_MODELS, PalantirModel
from anishift.services.llm.engines.palantir.errors import raise_palantir_config_error
from anishift.services.llm.types import Modality
from anishift.services.llm.wire_protocol import ModelProtocol
from anishift.utils.logger import get_logger

__all__ = [
    "PalantirGenerationOptions",
    "PalantirModelConfig",
    "palantir_model",
    "palantir_model_config",
    "request_options",
    "require_palantir_origin",
]

logger = get_logger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_REQUIRED_SCHEME: Final[str] = "https"
"""Only URL scheme an enrollment address may use."""


@dataclass(frozen=True, slots=True)
class PalantirGenerationOptions:
    """Generation limits and request options passed to a protocol builder."""

    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    request_options: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PalantirModelConfig:
    """Everything one Palantir request needs, resolved from the catalog."""

    alias: str
    provider_id: str
    protocol: ModelProtocol
    base_url: str
    provider_model_id: str
    token: str = field(repr=False)
    file_modalities: frozenset[Modality] = frozenset()

    def __post_init__(self) -> None:
        """Validate every field before any client or request can be built."""
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


def palantir_model(alias: str) -> PalantirModel:
    """Resolve a supported model alias to its capabilities and options."""
    for model in PALANTIR_MODELS:
        if model.alias == alias:
            return model
    return raise_palantir_config_error(
        "Palantir model alias is not in the built-in list",
        field_name="alias",
        suggestion="Select a supported Palantir model alias.",
    )


def request_options(model: PalantirModel, variant: str | None) -> dict[str, object]:
    """Combine model defaults with the selected reasoning variant."""
    options: dict[str, object] = dict(model.options)
    if variant is None:
        return options
    if variant not in model.variants:
        raise_palantir_config_error(
            "Palantir reasoning variant is not supported by the selected model",
            field_name="reasoning_variant",
            suggestion="Select a reasoning variant from the model's built-in list.",
        )
    options.update(model.variants[variant])
    return options


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
    """Assemble one configuration from validated catalog values and a token."""
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
    if not _is_plain_https(parts):
        raise_palantir_config_error(
            "Palantir enrollment address must be an https URL without a query or a fragment",
            field_name="base_url",
            suggestion="Set the enrollment address to the https origin of your enrollment in /connect.",
        )


def require_palantir_origin(origin: str) -> None:
    """Require an https fallback origin without a path, query or fragment."""
    parts: SplitResult = urlsplit(origin.strip())
    if not _is_plain_https(parts) or parts.path not in {"", "/"}:
        raise_palantir_config_error(
            "Palantir fallback_origin must be an https origin without a path, query or fragment",
            field_name="fallback_origin",
            suggestion="Set fallback_origin to the https origin of the second enrollment.",
        )


def _is_plain_https(parts: SplitResult) -> bool:
    return parts.scheme == _REQUIRED_SCHEME and bool(parts.netloc) and not parts.query and not parts.fragment


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

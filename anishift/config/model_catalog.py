"""Local catalog of Palantir providers and model aliases."""

from __future__ import annotations

import shutil
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Literal
from urllib.parse import SplitResult, urlsplit

import json5

from anishift.errors import ConfigError, ErrorCode, ErrorContext
from anishift.paths import config_path
from anishift.services.llm.wire_protocol import ModelProtocol
from anishift.utils.logger import get_logger

__all__ = [
    "CATALOG_EXAMPLE_FILE_NAME",
    "CATALOG_FILE_NAME",
    "CATALOG_SCHEMA_VERSION",
    "CatalogDefaults",
    "CatalogIssue",
    "CatalogSection",
    "ModelCatalog",
    "ModelCatalogError",
    "ModelEntry",
    "ModelLimits",
    "ModelProtocol",
    "ProviderEntry",
    "ensure_model_catalog_file",
    "load_model_catalog",
    "model_catalog_example_path",
    "model_catalog_path",
    "parse_model_catalog",
]

logger = get_logger(__name__)

CatalogSection = Literal["root", "providers", "models", "defaults"]
"""Part of the catalog one configuration issue belongs to."""


# ── Constants ────────────────────────────────────────────────────────────────

CATALOG_SCHEMA_VERSION: Final[int] = 1
"""Only catalog schema this loader accepts."""

CATALOG_FILE_NAME: Final[str] = "anishift.models.jsonc"
"""Filename of the runtime catalog inside the configuration directory."""

CATALOG_EXAMPLE_FILE_NAME: Final[str] = "anishift.models.example.jsonc"
"""Filename of the secret-free example shipped with the repository."""

_CATALOG_LOCATION: Final[str] = f"config/{CATALOG_FILE_NAME}"
"""Repo-relative runtime location named in messages instead of an absolute path."""

_EXAMPLE_LOCATION: Final[str] = f"config/{CATALOG_EXAMPLE_FILE_NAME}"
"""Repo-relative example location named in messages instead of an absolute path."""

_SECRET_NAME_ENDINGS: Final[tuple[str, ...]] = (
    "auth",
    "authorization",
    "bearer",
    "credential",
    "credentials",
    "key",
    "passwd",
    "password",
    "secret",
    "token",
)
"""Separator-free field-name endings that mark a field as secret-looking."""

_IDENTIFIER_KEYED_SECTIONS: Final[frozenset[str]] = frozenset({"providers", "models"})
"""Root sections whose keys are user-chosen identifiers, not schema fields."""

_ROOT_KEYS: Final[frozenset[str]] = frozenset(
    {"schema_version", "providers", "models", "defaults"},
)
"""Keys the catalog schema defines at the top level."""

_PROVIDER_KEYS: Final[frozenset[str]] = frozenset({"protocol", "path"})
"""Keys the catalog schema defines inside one provider entry."""

_MODEL_KEYS: Final[frozenset[str]] = frozenset(
    {"provider", "model", "label", "experimental", "limits"},
)
"""Keys the catalog schema defines inside one model entry."""

_LIMIT_KEYS: Final[frozenset[str]] = frozenset({"context", "input", "output"})
"""Safe metadata limits a model entry may declare."""

_DEFAULT_ROLE_KEYS: Final[frozenset[str]] = frozenset({"primary", "translation"})
"""Model roles the catalog may preselect."""


@dataclass(frozen=True, slots=True)
class CatalogIssue:
    """One configuration error kept visible instead of silently dropped."""

    section: CatalogSection
    key: str
    message: str
    suggestion: str = ""


@dataclass(frozen=True, slots=True)
class ProviderEntry:
    """One Foundry proxy provider: its protocol and its relative route."""

    provider_id: str
    protocol: ModelProtocol
    path: str


@dataclass(frozen=True, slots=True)
class ModelLimits:
    """Optional safe capacity metadata of one model."""

    context: int | None = None
    input: int | None = None
    output: int | None = None


@dataclass(frozen=True, slots=True)
class ModelEntry:
    """One model alias bound to a provider and a provider model identifier."""

    alias: str
    provider_id: str
    model_id: str
    label: str
    experimental: bool = False
    limits: ModelLimits = field(default_factory=ModelLimits)


@dataclass(frozen=True, slots=True)
class CatalogDefaults:
    """Aliases preselected for the model roles, ``None`` when unresolved."""

    primary: str | None = None
    translation: str | None = None


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    """Validated local catalog plus every configuration error it carries."""

    schema_version: int
    providers: Mapping[str, ProviderEntry]
    models: Mapping[str, ModelEntry]
    defaults: CatalogDefaults
    issues: tuple[CatalogIssue, ...]


class ModelCatalogError(ConfigError):
    """Raised when the catalog file as a whole cannot be used."""


def model_catalog_path() -> Path:
    """Return the absolute path of the runtime catalog."""
    return config_path().parent / CATALOG_FILE_NAME


def model_catalog_example_path() -> Path:
    """Return the absolute path of the secret-free example catalog."""
    return config_path().parent / CATALOG_EXAMPLE_FILE_NAME


def parse_model_catalog(source: str) -> ModelCatalog:
    """Validate JSONC *source* into a catalog without touching the network."""
    raw: dict[str, Any] = _decode(source)
    _reject_secret_fields(raw)
    _require_schema_version(raw)
    issues: list[CatalogIssue] = list(_unknown_key_issues("root", "", raw, _ROOT_KEYS))
    providers: dict[str, ProviderEntry] = _parse_providers(raw.get("providers"), issues)
    models: dict[str, ModelEntry] = _parse_models(raw.get("models"), providers, issues)
    defaults: CatalogDefaults = _parse_defaults(raw.get("defaults"), models, issues)
    return ModelCatalog(
        schema_version=CATALOG_SCHEMA_VERSION,
        providers=MappingProxyType(providers),
        models=MappingProxyType(models),
        defaults=defaults,
        issues=tuple(issues),
    )


def load_model_catalog() -> ModelCatalog:
    """Read and validate the runtime catalog, performing no network access."""
    path: Path = model_catalog_path()
    if not path.is_file():
        raise _catalog_error(
            ErrorCode.CONFIG_MISSING,
            f"Model catalog is missing: {_CATALOG_LOCATION}",
            f"Copy {_EXAMPLE_LOCATION} to {_CATALOG_LOCATION} and adjust its providers and model aliases",
        )
    try:
        source: str = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise _catalog_error(
            ErrorCode.CONFIG_INVALID,
            f"Model catalog is unreadable: {_CATALOG_LOCATION}",
            f"Check the file permissions and save {_CATALOG_LOCATION} as UTF-8 text",
        ) from error
    catalog: ModelCatalog = parse_model_catalog(source)
    logger.debug(
        "Model catalog loaded",
        providers=len(catalog.providers),
        models=len(catalog.models),
        issues=len(catalog.issues),
    )
    return catalog


def ensure_model_catalog_file() -> bool:
    """Create the runtime catalog from the example when none exists yet."""
    path: Path = model_catalog_path()
    if path.exists():
        return False
    example: Path = model_catalog_example_path()
    if not example.is_file():
        raise _catalog_error(
            ErrorCode.CONFIG_MISSING,
            f"Example model catalog is missing: {_EXAMPLE_LOCATION}",
            f"Restore {_EXAMPLE_LOCATION} from the repository or write {_CATALOG_LOCATION} by hand",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example, path)
    logger.info("Model catalog created from the bundled example")
    return True


def _catalog_error(code: ErrorCode, message: str, suggestion: str) -> ModelCatalogError:
    """Build a typed catalog error carrying a structured context."""
    return ModelCatalogError(
        context=ErrorContext(code=code, message=message, suggestion=suggestion),
    )


def _decode(source: str) -> dict[str, Any]:
    """Parse JSONC *source* into a mapping, rejecting repeated keys."""
    try:
        raw: object = json5.loads(source, allow_duplicate_keys=False)
    except ValueError as error:
        # The parser message can quote file content, so it never reaches the UI.
        raise _catalog_error(
            ErrorCode.CONFIG_INVALID,
            f"Model catalog is not valid JSONC or repeats a key: {_CATALOG_LOCATION}",
            "Fix the syntax and keep every provider ID and model alias unique",
        ) from error
    if not isinstance(raw, dict):
        raise _catalog_error(
            ErrorCode.CONFIG_INVALID,
            f"Model catalog is not a JSONC object: {_CATALOG_LOCATION}",
            f"Wrap the catalog in braces, as in {_EXAMPLE_LOCATION}",
        )
    return raw


def _is_secret_name(name: str) -> bool:
    """Whether *name* reads like a secret rather than catalog metadata."""
    normalized: str = name.casefold().replace("-", "").replace("_", "").replace(" ", "")
    return normalized.endswith(_SECRET_NAME_ENDINGS)


def _secret_field_name(value: object) -> str | None:
    """Return the first secret-looking field name anywhere under *value*."""
    if isinstance(value, dict):
        return _secret_key_in(value)
    if isinstance(value, list):
        return next(
            (found for item in value if (found := _secret_field_name(item)) is not None),
            None,
        )
    return None


def _secret_key_in(mapping: dict[Any, Any]) -> str | None:
    """Return the first secret-looking key of *mapping* or of its children."""
    for key, item in mapping.items():
        if isinstance(key, str) and _is_secret_name(key):
            return key
        nested: str | None = _secret_field_name(item)
        if nested is not None:
            return nested
    return None


def _secret_field_name_in_entries(value: object) -> str | None:
    """Return the first secret-looking field name inside identifier-keyed entries."""
    if not isinstance(value, dict):
        return _secret_field_name(value)
    return next(
        (found for item in value.values() if (found := _secret_field_name(item)) is not None),
        None,
    )


def _secret_field_name_in_catalog(raw: dict[str, Any]) -> str | None:
    """Return the first secret-looking field name of the catalog tree."""
    for key, item in raw.items():
        name: str = str(key)
        if _is_secret_name(name):
            return name
        found: str | None = (
            _secret_field_name_in_entries(item) if name in _IDENTIFIER_KEYED_SECTIONS else _secret_field_name(item)
        )
        if found is not None:
            return found
    return None


def _reject_secret_fields(raw: dict[str, Any]) -> None:
    """Reject the whole catalog when a field name looks like a secret."""
    found: str | None = _secret_field_name_in_catalog(raw)
    if found is None:
        return
    raise _catalog_error(
        ErrorCode.CONFIG_INVALID,
        f"Model catalog holds a field that looks like a secret: {found}",
        "Delete that field; the Palantir token belongs in ANISHIFT_PALANTIR_TOKEN",
    )


def _require_schema_version(raw: dict[str, Any]) -> None:
    """Accept only the supported schema version, treating absence as version 1."""
    version: object = raw.get("schema_version", CATALOG_SCHEMA_VERSION)
    if type(version) is int and version == CATALOG_SCHEMA_VERSION:
        return
    raise _catalog_error(
        ErrorCode.CONFIG_INVALID,
        f"Model catalog declares an unsupported schema version: {_CATALOG_LOCATION}",
        f"Set schema_version to {CATALOG_SCHEMA_VERSION}",
    )


def _unknown_key_issues(
    section: CatalogSection,
    key_prefix: str,
    mapping: dict[Any, Any],
    allowed: frozenset[str],
) -> list[CatalogIssue]:
    """Report every key of *mapping* the schema does not define."""
    return [
        CatalogIssue(
            section=section,
            key=f"{key_prefix}{key}",
            message=f"Unknown catalog field: {key_prefix}{key}",
            suggestion="Remove the field or fix its spelling",
        )
        for key in mapping
        if str(key) not in allowed
    ]


def _nonempty_string(value: object) -> str | None:
    """Return the stripped string, or ``None`` for anything else or empty."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _relative_route(value: object) -> str | None:
    """Return the relative proxy route, or ``None`` when it is not relative."""
    route: str | None = _nonempty_string(value)
    if route is None or not route.startswith("/"):
        return None
    try:
        parts: SplitResult = urlsplit(route)
    except ValueError:
        return None
    if parts.scheme or parts.netloc or parts.query or parts.fragment:
        return None
    return route


def _parse_provider(
    provider_id: str,
    value: object,
    issues: list[CatalogIssue],
) -> ProviderEntry | None:
    """Validate one provider entry, reporting it by ID when unusable."""
    if not provider_id or not isinstance(value, dict):
        issues.append(
            CatalogIssue(
                section="providers",
                key=provider_id,
                message=f"Provider entry is not a usable object: {provider_id}",
                suggestion="Give the provider an ID and a protocol/path object",
            ),
        )
        return None
    issues.extend(_unknown_key_issues("providers", f"{provider_id}.", value, _PROVIDER_KEYS))
    protocol: str | None = _nonempty_string(value.get("protocol"))
    if protocol not in frozenset(item.value for item in ModelProtocol):
        issues.append(
            CatalogIssue(
                section="providers",
                key=provider_id,
                message=f"Provider {provider_id} declares an unsupported protocol: {protocol}",
                suggestion=f"Use one of: {', '.join(item.value for item in ModelProtocol)}",
            ),
        )
        return None
    route: str | None = _relative_route(value.get("path"))
    if route is None:
        issues.append(
            CatalogIssue(
                section="providers",
                key=provider_id,
                message=f"Provider {provider_id} has no relative proxy path",
                suggestion="Use a route starting with / and no host, query or fragment",
            ),
        )
        return None
    return ProviderEntry(
        provider_id=provider_id,
        protocol=ModelProtocol(protocol),
        path=route,
    )


def _parse_providers(value: object, issues: list[CatalogIssue]) -> dict[str, ProviderEntry]:
    """Validate the provider section, keeping only usable providers."""
    if not isinstance(value, dict):
        issues.append(
            CatalogIssue(
                section="providers",
                key="",
                message="Providers section is missing",
                suggestion=f"Copy the providers section from {_EXAMPLE_LOCATION}",
            ),
        )
        return {}
    entries: dict[str, ProviderEntry] = {}
    for key, item in _unique_entries(value, "providers", issues):
        entry: ProviderEntry | None = _parse_provider(key, item, issues)
        if entry is not None:
            entries[entry.provider_id] = entry
    return entries


def _unique_entries(
    value: dict[Any, Any],
    section: CatalogSection,
    issues: list[CatalogIssue],
) -> Iterator[tuple[str, object]]:
    """Yield entries with unambiguous normalized IDs and report collisions."""
    counts: Counter[str] = Counter(str(key).strip() for key in value)
    for key, item in value.items():
        identifier: str = str(key).strip()
        if counts[identifier] > 1:
            issues.append(
                CatalogIssue(
                    section=section,
                    key=str(key),
                    message=f"Duplicate catalog identifier after trimming whitespace: {identifier}",
                    suggestion="Give each entry a unique identifier without surrounding whitespace",
                ),
            )
            continue
        yield identifier, item


def _parse_limit(alias: str, name: str, value: object, issues: list[CatalogIssue]) -> int | None:
    """Read one optional positive integer limit, reporting a bad value."""
    if value is None:
        return None
    if type(value) is int and value > 0:
        return value
    issues.append(
        CatalogIssue(
            section="models",
            key=alias,
            message=f"Model {alias} declares a non-positive {name} limit",
            suggestion="Use a positive integer or null",
        ),
    )
    return None


def _parse_limits(alias: str, value: object, issues: list[CatalogIssue]) -> ModelLimits:
    """Read the optional safe capacity metadata of one model."""
    if not isinstance(value, dict):
        return ModelLimits()
    issues.extend(_unknown_key_issues("models", f"{alias}.limits.", value, _LIMIT_KEYS))
    return ModelLimits(
        context=_parse_limit(alias, "context", value.get("context"), issues),
        input=_parse_limit(alias, "input", value.get("input"), issues),
        output=_parse_limit(alias, "output", value.get("output"), issues),
    )


def _parse_model(
    alias: str,
    value: object,
    providers: dict[str, ProviderEntry],
    issues: list[CatalogIssue],
) -> ModelEntry | None:
    """Validate one model entry, reporting it by alias when unusable."""
    if not alias or not isinstance(value, dict):
        issues.append(
            CatalogIssue(
                section="models",
                key=alias,
                message=f"Model entry is not a usable object: {alias}",
                suggestion="Give the alias a provider/model object",
            ),
        )
        return None
    issues.extend(_unknown_key_issues("models", f"{alias}.", value, _MODEL_KEYS))
    provider_id: str | None = _nonempty_string(value.get("provider"))
    if provider_id is None or provider_id not in providers:
        issues.append(
            CatalogIssue(
                section="models",
                key=alias,
                message=f"Model {alias} references an unknown or unusable provider: {provider_id}",
                suggestion="Point the model at a provider defined with a supported protocol",
            ),
        )
        return None
    model_id: str | None = _nonempty_string(value.get("model"))
    if model_id is None:
        issues.append(
            CatalogIssue(
                section="models",
                key=alias,
                message=f"Model {alias} has an empty model identifier",
                suggestion="Set the exact provider model ID or RID",
            ),
        )
        return None
    return ModelEntry(
        alias=alias,
        provider_id=provider_id,
        model_id=model_id,
        label=_nonempty_string(value.get("label")) or alias,
        experimental=value.get("experimental") is True,
        limits=_parse_limits(alias, value.get("limits"), issues),
    )


def _parse_models(
    value: object,
    providers: dict[str, ProviderEntry],
    issues: list[CatalogIssue],
) -> dict[str, ModelEntry]:
    """Validate the model section, keeping only usable aliases."""
    if not isinstance(value, dict):
        issues.append(
            CatalogIssue(
                section="models",
                key="",
                message="Models section is missing",
                suggestion=f"Copy the models section from {_EXAMPLE_LOCATION}",
            ),
        )
        return {}
    entries: dict[str, ModelEntry] = {}
    for key, item in _unique_entries(value, "models", issues):
        entry: ModelEntry | None = _parse_model(key, item, providers, issues)
        if entry is not None:
            entries[entry.alias] = entry
    return entries


def _parse_role(
    role: str,
    value: object,
    models: dict[str, ModelEntry],
    issues: list[CatalogIssue],
) -> str | None:
    """Resolve one default role to a usable alias, never to a substitute."""
    alias: str | None = _nonempty_string(value)
    if alias is None:
        return None
    if alias in models:
        return alias
    issues.append(
        CatalogIssue(
            section="defaults",
            key=role,
            message=f"Default {role} model points at an unusable alias: {alias}",
            suggestion="Select one of the aliases the models section defines",
        ),
    )
    return None


def _parse_defaults(
    value: object,
    models: dict[str, ModelEntry],
    issues: list[CatalogIssue],
) -> CatalogDefaults:
    """Read the preselected roles, leaving a role unset when it is unusable."""
    if value is None:
        return CatalogDefaults()
    if not isinstance(value, dict):
        issues.append(
            CatalogIssue(
                section="defaults",
                key="",
                message="Defaults section is not an object",
                suggestion='Use "defaults": { "primary": "...", "translation": "..." }',
            ),
        )
        return CatalogDefaults()
    issues.extend(_unknown_key_issues("defaults", "defaults.", value, _DEFAULT_ROLE_KEYS))
    return CatalogDefaults(
        primary=_parse_role("primary", value.get("primary"), models, issues),
        translation=_parse_role("translation", value.get("translation"), models, issues),
    )

"""Palantir account selection and process-wide enrollment cooldowns."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from threading import Lock
from time import monotonic
from typing import Final
from urllib.parse import SplitResult, urlsplit

from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines.palantir.auth import authorization_headers, validated_palantir_token
from anishift.services.llm.engines.palantir.config import require_palantir_origin
from anishift.services.llm.engines.palantir.protocols import PalantirHttpRequest
from anishift.utils.logger import get_logger

__all__ = [
    "PalantirAccount",
    "account_order",
    "account_request",
    "clear_cooldown",
    "palantir_accounts",
    "reset_cooldowns",
    "start_cooldown",
]

logger = get_logger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_COOLDOWN_S: Final[float] = 60.0
"""Time an enrollment is skipped after an HTTP limit or server failure."""

_COOLDOWNS: Final[dict[str, float]] = {}
"""Monotonic cooldown deadlines keyed by enrollment origin."""

_LOCK: Final[Lock] = Lock()
"""Guard for cooldown snapshots and updates, never held during HTTP."""


@dataclass(frozen=True, slots=True)
class PalantirAccount:
    """One ordered enrollment with private origin and credentials."""

    number: int
    origin: str = field(repr=False)
    token: str = field(repr=False)


def palantir_accounts(config: LlmConfig) -> tuple[PalantirAccount, ...]:
    """Resolve the primary account and an optional complete fallback account."""
    primary: SplitResult = urlsplit(config.base_url or "")
    accounts: tuple[PalantirAccount, ...] = (
        PalantirAccount(1, f"{primary.scheme}://{primary.netloc}", config.api_key),
    )
    if not config.fallback_origin or not config.fallback_api_key:
        return accounts
    require_palantir_origin(config.fallback_origin)
    fallback: SplitResult = urlsplit(config.fallback_origin.strip())
    token: str = validated_palantir_token(config.fallback_api_key, field_name="fallback_api_key")
    return (*accounts, PalantirAccount(2, f"{fallback.scheme}://{fallback.netloc}", token))


def account_order(accounts: tuple[PalantirAccount, ...]) -> tuple[PalantirAccount, ...]:
    """Snapshot ready accounts in order, using all accounts when all are cooling."""
    with _LOCK:
        now: float = monotonic()
        ready: tuple[PalantirAccount, ...] = tuple(
            account for account in accounts if _COOLDOWNS.get(account.origin, 0.0) <= now
        )
    return ready or accounts


def start_cooldown(account: PalantirAccount) -> None:
    """Cool an enrollment after an HTTP rate limit or server failure."""
    with _LOCK:
        _COOLDOWNS[account.origin] = monotonic() + _COOLDOWN_S
    logger.debug("Palantir account cooldown started", account=account.number)


def clear_cooldown(account: PalantirAccount) -> None:
    """Clear an enrollment cooldown after any other HTTP response."""
    with _LOCK:
        previous: float | None = _COOLDOWNS.pop(account.origin, None)
    if previous is not None:
        logger.debug("Palantir account cooldown cleared", account=account.number)


def reset_cooldowns() -> None:
    """Clear process-wide enrollment cooldowns."""
    with _LOCK:
        _COOLDOWNS.clear()


def account_request(built: PalantirHttpRequest, account: PalantirAccount) -> PalantirHttpRequest:
    """Replace only the request origin and bearer token for an account."""
    url: SplitResult = urlsplit(built.url)
    origin: SplitResult = urlsplit(account.origin)
    return replace(
        built,
        url=url._replace(scheme=origin.scheme, netloc=origin.netloc).geturl(),
        headers={**built.headers, "Authorization": authorization_headers(account.token)["Authorization"]},
    )

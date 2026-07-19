"""Shared service base Protocol - EngineInfo.

All domain-specific engine Protocols extend EngineInfo, which provides the
identity and availability every engine must expose.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EngineInfo(Protocol):
    """Base protocol that every engine must satisfy.

    Provides identity and availability shared across all engine domains.
    """

    @property
    def engine_id(self) -> str:
        """Stable engine identifier (registry key)."""
        ...

    @property
    def is_available(self) -> bool:
        """Whether the engine can be used (deps installed, key present)."""
        ...


__all__ = ["EngineInfo"]

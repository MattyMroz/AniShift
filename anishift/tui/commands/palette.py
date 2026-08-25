"""Rows the command palette and the composer project out of one registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from anishift.tui.commands.spec import key_display

if TYPE_CHECKING:
    from collections.abc import Iterable

    from anishift.tui.commands.registry import CommandRegistry
    from anishift.tui.commands.spec import CommandSpec

__all__ = [
    "CommandOption",
    "format_keys",
    "option_of",
    "palette_options",
    "slash_options",
]

# ── Constants ──────────────────────────────────────────────────────────────

_KEY_JOINER: Final[str] = " "
"""Separator between the keys one command answers to."""

_SLASH_PREFIX: Final[str] = "/"
"""Character the composer uses to open a slash command."""


@dataclass(frozen=True, slots=True)
class CommandOption:
    """One selectable row of the palette, projecting one command."""

    name: str
    label: str
    description: str
    keys: str
    suggested: bool


def format_keys(keys: Iterable[str]) -> str:
    """Render *keys* the way a palette row and the status footer show them."""
    return _KEY_JOINER.join(key_display(key) for key in keys)


def option_of(registry: CommandRegistry, spec: CommandSpec) -> CommandOption:
    """Project *spec* into the row a surface shows for it."""
    label: str = spec.title if spec.slash_name is None else f"{_SLASH_PREFIX}{spec.slash_name}"
    return CommandOption(
        name=spec.name,
        label=label,
        description=spec.description,
        keys=format_keys(spec.keys),
        suggested=registry.is_suggested(spec),
    )


def palette_options(registry: CommandRegistry) -> tuple[CommandOption, ...]:
    """Rows of every listed command the session allows, suggested ones first."""
    options: list[CommandOption] = [option_of(registry, spec) for spec in registry.available()]
    return tuple(sorted(options, key=_suggested_first))


def slash_options(registry: CommandRegistry, query: str) -> tuple[CommandOption, ...]:
    """Rows of the ranked slash suggestions for the composer query *query*."""
    return tuple(option_of(registry, spec) for spec in registry.suggestions(query))


def _suggested_first(option: CommandOption) -> tuple[bool, str]:
    """Sort key lifting the suggested rows, then reading alphabetically inside each group."""
    return (not option.suggested, option.label)

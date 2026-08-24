"""Rows the command palette and the composer show for one registry.

The palette owns no command: it projects what the registry already knows, so a
row can never disagree with the command it runs. Selecting a row hands its
``name`` back to ``CommandRegistry.dispatch``.

The shared modal selector arrives with the dialog primitives; until then these
rows are the whole contract between the registry and the palette.

Public API:
    CommandOption: One selectable row projecting one command.
    format_keys: Render the keys of one command for a row.
    option_of: Project one command into the row a surface shows.
    palette_options: Rows of every command the palette may list.
    slash_options: Rows of the ranked suggestions for one composer query.
"""

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
    """One selectable row of the palette, projecting one command.

    Attributes:
        name: Registry name the selected row hands to ``dispatch``.
        label: Slash form of the command, or the title of a contextual action.
        description: Sentence the catalogue wrote for the command.
        keys: Rendered keys of the command, empty when it answers to none.
        suggested: Whether the session makes this command the likely next step.
    """

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


def _suggested_first(option: CommandOption) -> bool:
    """Sort key lifting the suggested rows, keeping the ranked order below."""
    return not option.suggested

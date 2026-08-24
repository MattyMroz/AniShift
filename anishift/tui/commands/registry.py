"""The one registry of commands and the one point that runs them.

The application registers the global catalogue once; the active screen adds its
contextual actions under its own scope on mount and drops that scope on unmount.
Every surface — palette, composer, key hints, buttons — projects this registry
and runs a command only through ``dispatch``.

Availability is evaluated on every read, never at registration: a predicate
answers about the state the shell owns at the moment a surface asks.

Public API:
    GLOBAL_SCOPE: Scope of the commands the application owns for the session.
    SLASH_SUGGESTION_LIMIT: Most slash suggestions the composer may show.
    KEY_HINT_LIMIT: Most key hints the one-row status footer may show.
    PREFIX_BOOST: Factor lifting a prefix match above a scattered match.
    DESCRIPTION_WEIGHT: Factor keeping a description match below a name match.
    CommandRegistry: The only registry and the only dispatch point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from textual.fuzzy import FuzzySearch

from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from anishift.tui.commands.spec import CommandSpec, KeyHint, StateReader
    from anishift.tui.state import SessionState

__all__ = [
    "DESCRIPTION_WEIGHT",
    "GLOBAL_SCOPE",
    "KEY_HINT_LIMIT",
    "PREFIX_BOOST",
    "SLASH_SUGGESTION_LIMIT",
    "CommandRegistry",
]

logger = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

GLOBAL_SCOPE: Final[str] = "global"
"""Scope of the commands the application registers once for the whole session."""

SLASH_SUGGESTION_LIMIT: Final[int] = 10
"""Most slash suggestions the composer may show for one query."""

KEY_HINT_LIMIT: Final[int] = 5
"""Most key hints the one-row status footer may show at once."""

PREFIX_BOOST: Final[float] = 2.0
"""Factor lifting a prefix match above the same match spread over a name."""

DESCRIPTION_WEIGHT: Final[float] = 0.5
"""Factor keeping a description match below any slash name or alias match."""

_SLASH_PREFIX: Final[str] = "/"
"""Character the composer uses to open a slash command."""

_FUZZY: Final[FuzzySearch] = FuzzySearch()
"""Shared cached matcher; it holds queries only, never session state."""


def _form_score(query: str, candidate: str) -> float:
    """Score *candidate* against *query*, lifting a prefix match."""
    score: float
    score, _ = _FUZZY.match(query, candidate)
    if score > 0.0 and candidate.startswith(query):
        return score * PREFIX_BOOST
    return score


def _command_score(spec: CommandSpec, query: str) -> float:
    """Best score of one command over its slash forms and its description."""
    forms: float = max(_form_score(query, form.casefold()) for form in spec.slash_forms)
    described: float = _form_score(query, spec.description.casefold()) * DESCRIPTION_WEIGHT
    return max(forms, described)


def _best_first(scored: tuple[CommandSpec, float]) -> float:
    """Sort key putting the best score first and keeping registration order."""
    return -scored[1]


class CommandRegistry:
    """The only registry of commands and the only point that runs them."""

    def __init__(self, read_state: StateReader) -> None:
        """Answer every availability question against the state *read_state* gives."""
        self._read_state: StateReader = read_state
        self._specs: dict[str, CommandSpec] = {}
        self._scopes: dict[str, tuple[str, ...]] = {}

    def register(self, specs: Iterable[CommandSpec], *, scope: str = GLOBAL_SCOPE) -> None:
        """Add *specs* under *scope*, refusing any name the registry already holds."""
        if scope in self._scopes:
            msg = f"Scope {scope!r} is already registered"
            raise ValueError(msg)
        added: tuple[CommandSpec, ...] = tuple(specs)
        names: tuple[str, ...] = tuple(spec.name for spec in added)
        if len(set(names)) != len(names):
            msg = f"Scope {scope!r} defines one command name twice"
            raise ValueError(msg)
        taken: tuple[str, ...] = tuple(name for name in names if name in self._specs)
        if taken:
            msg = f"Commands already registered: {taken}"
            raise ValueError(msg)
        self._specs.update({spec.name: spec for spec in added})
        self._scopes[scope] = names

    def unregister(self, scope: str) -> None:
        """Drop every command of *scope*; an unknown scope changes nothing."""
        for name in self._scopes.pop(scope, ()):
            self._specs.pop(name, None)

    def command(self, name: str) -> CommandSpec | None:
        """Return the command called *name*, if the registry holds it."""
        return self._specs.get(name)

    def commands(self) -> tuple[CommandSpec, ...]:
        """Every registered command, in registration order."""
        return tuple(self._specs.values())

    def slash_names(self) -> tuple[str, ...]:
        """Slash name of every registered command, in registration order."""
        return tuple(spec.slash_name for spec in self._specs.values() if spec.slash_name is not None)

    def available(self) -> tuple[CommandSpec, ...]:
        """Every listed command the current state allows, in registration order."""
        state: SessionState = self._read_state()
        return tuple(spec for spec in self._specs.values() if not spec.hidden and spec.is_enabled(state))

    def is_suggested(self, spec: CommandSpec) -> bool:
        """Whether the current state makes *spec* the likely next step."""
        return spec.is_suggested(self._read_state())

    def key_hints(self, *, limit: int = KEY_HINT_LIMIT) -> tuple[KeyHint, ...]:
        """Labels of the first *limit* listed commands that answer to a key."""
        hints: list[KeyHint] = [spec.key_hint for spec in self.available() if spec.key_hint is not None]
        return tuple(hints[:limit])

    def suggestions(self, query: str) -> tuple[CommandSpec, ...]:
        """Rank the available slash commands for *query*, best match first."""
        candidates: tuple[CommandSpec, ...] = tuple(spec for spec in self.available() if spec.slash_name is not None)
        normalized: str = query.casefold().removeprefix(_SLASH_PREFIX)
        if not normalized:
            return candidates[:SLASH_SUGGESTION_LIMIT]
        scored: list[tuple[CommandSpec, float]] = [(spec, _command_score(spec, normalized)) for spec in candidates]
        ranked: Sequence[tuple[CommandSpec, float]] = sorted(
            (pair for pair in scored if pair[1] > 0.0),
            key=_best_first,
        )
        return tuple(spec for spec, _ in ranked[:SLASH_SUGGESTION_LIMIT])

    def dispatch(self, name: str) -> bool:
        """Run the command called *name*; the only place a command runs."""
        spec: CommandSpec | None = self._specs.get(name)
        if spec is None or not spec.is_enabled(self._read_state()):
            logger.debug("Command refused", command=name, known=spec is not None)
            return False
        spec.run()
        return True

    def dispatch_key(self, key: str) -> bool:
        """Run the command *key* is bound to, listed or not."""
        state: SessionState = self._read_state()
        for spec in self._specs.values():
            if key in spec.keys and spec.is_enabled(state):
                return self.dispatch(spec.name)
        return False

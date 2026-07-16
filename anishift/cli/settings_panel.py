"""Full-screen ``/settings`` panel — arrow-key editing with auto-save.

Arrow keys only (no WASD): ``↑``/``↓`` pick a field, ``←``/``→`` or ``Enter``
cycle its value, ``Esc``/``q`` returns to the shell. Each change is persisted
immediately. Engine and voice lists are static placeholders until stages 4/6
derive them from the engine registries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from anishift.bootstrap import AppContext
from anishift.config.user_settings import (
    TEMPO_RANGE,
    VOLUME_RANGE,
    UserSettings,
    save_user_settings,
)

__all__ = ["open_settings_panel"]

# ── Constants ──────────────────────────────────────────────────────────────

_TRANSLATION_ENGINES: Final[tuple[str, ...]] = ("google", "deepl", "llm")
"""Placeholder translation-engine ids (real list arrives in stage 4)."""

_TTS_ENGINES: Final[tuple[str, ...]] = ("edge", "elevenlabs", "balcon")
"""Placeholder TTS-engine ids (real list arrives in stage 6)."""

_VOICES: Final[tuple[str, ...]] = ("pl-PL-MarekNeural", "pl-PL-ZofiaNeural")
"""Placeholder TTS voices (real list arrives in stage 6)."""

_OUTPUT_VARIANTS: Final[tuple[str, ...]] = ("players", "merge", "burn")
"""Selectable output-assembly variants."""

_MODES: Final[tuple[str, ...]] = ("auto", "manual")
"""Selectable processing modes."""

_TEMPO_STEP: Final[float] = 0.05
"""Tempo increment per ``←``/``→`` press."""

_VOLUME_STEP: Final[int] = 5
"""Volume increment (percent) per ``←``/``→`` press."""


@dataclass(frozen=True, slots=True)
class _Field:
    """One editable row of the panel.

    Attributes:
        key: The :class:`UserSettings` attribute name.
        label: Human-readable label shown on the left.
    """

    key: str
    label: str


_FIELDS: Final[tuple[_Field, ...]] = (
    _Field("mode", "Mode"),
    _Field("translation_engine", "Translation"),
    _Field("tts_engine", "TTS engine"),
    _Field("voice", "Voice"),
    _Field("tempo", "Tempo"),
    _Field("volume", "Volume"),
    _Field("output_variant", "Output"),
    _Field("move_results_to_output", "-> output/"),
)
"""Editable rows, top to bottom."""


def _cycle(options: tuple[str, ...], current: str, delta: int) -> str:
    """Return the option ``delta`` steps from ``current`` (wrapping)."""
    index = options.index(current) if current in options else 0
    return options[(index + delta) % len(options)]


def _clamp_float(value: float, low: float, high: float) -> float:
    """Clamp ``value`` into the inclusive ``[low, high]`` range."""
    return round(min(max(value, low), high), 2)


def _clamp_int(value: int, low: int, high: int) -> int:
    """Clamp ``value`` into the inclusive ``[low, high]`` range."""
    return min(max(value, low), high)


def _step_field(settings: UserSettings, field: _Field, delta: int) -> None:
    """Advance ``field`` by ``delta`` on ``settings`` in place."""
    if field.key == "mode":
        settings.mode = _cycle(_MODES, settings.mode, delta)  # type: ignore[assignment]
    elif field.key == "translation_engine":
        settings.translation_engine = _cycle(_TRANSLATION_ENGINES, settings.translation_engine, delta)
    elif field.key == "tts_engine":
        settings.tts_engine = _cycle(_TTS_ENGINES, settings.tts_engine, delta)
    elif field.key == "voice":
        settings.voice = _cycle(_VOICES, settings.voice, delta)
    elif field.key == "output_variant":
        settings.output_variant = _cycle(_OUTPUT_VARIANTS, settings.output_variant, delta)  # type: ignore[assignment]
    elif field.key == "tempo":
        settings.tempo = _clamp_float(settings.tempo + delta * _TEMPO_STEP, *TEMPO_RANGE)
    elif field.key == "volume":
        settings.volume = _clamp_int(settings.volume + delta * _VOLUME_STEP, *VOLUME_RANGE)
    elif field.key == "move_results_to_output":
        settings.move_results_to_output = not settings.move_results_to_output


def _value_text(settings: UserSettings, field: _Field) -> str:
    """Render the current value of ``field`` for display."""
    value = getattr(settings, field.key)
    if field.key == "tempo":
        return f"{value:.2f}x"
    if field.key == "volume":
        return f"{value}%"
    if field.key == "move_results_to_output":
        return "yes" if value else "no"
    return str(value)


def open_settings_panel(context: AppContext) -> UserSettings:
    """Open the arrow-key settings panel and return the edited preferences.

    Args:
        context: Wired context whose ``user_settings`` seed the panel.

    Returns:
        The mutated :class:`UserSettings` (already persisted on every change).
    """
    settings = context.user_settings
    state = {"row": 0}

    def render() -> StyleAndTextTuples:
        lines: StyleAndTextTuples = [("class:title", " AniShift · Settings\n\n")]
        for i, field in enumerate(_FIELDS):
            marker = "> " if i == state["row"] else "  "
            style = "class:active" if i == state["row"] else "class:normal"
            lines.append((style, f"{marker}{field.label:<14}{_value_text(settings, field)}\n"))
        lines.append(("class:hint", "\n ↑↓ field · ←→ change · Esc back"))
        return lines

    bindings = KeyBindings()

    @bindings.add("up")
    def _up(event: KeyPressEvent) -> None:
        state["row"] = (state["row"] - 1) % len(_FIELDS)

    @bindings.add("down")
    def _down(event: KeyPressEvent) -> None:
        state["row"] = (state["row"] + 1) % len(_FIELDS)

    @bindings.add("left")
    def _left(event: KeyPressEvent) -> None:
        _step_field(settings, _FIELDS[state["row"]], -1)
        save_user_settings(settings)

    @bindings.add("right")
    def _right(event: KeyPressEvent) -> None:
        _step_field(settings, _FIELDS[state["row"]], 1)
        save_user_settings(settings)

    @bindings.add("enter")
    def _enter(event: KeyPressEvent) -> None:
        _step_field(settings, _FIELDS[state["row"]], 1)
        save_user_settings(settings)

    @bindings.add("escape")
    @bindings.add("q")
    def _quit(event: KeyPressEvent) -> None:
        event.app.exit()

    control = FormattedTextControl(render, focusable=True, show_cursor=False)
    layout = Layout(HSplit([Window(control)]))
    application: Application[None] = Application(
        layout=layout,
        key_bindings=bindings,
        full_screen=True,
    )
    application.run()
    return settings

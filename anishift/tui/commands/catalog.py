"""The commands the product froze, and none of their behaviour.

Section 5 of the specification closes the catalogue at fourteen slash commands.
This module writes those fourteen definitions once and delegates every effect to
the application shell through ``CommandHost``: nothing here opens a dialog, reads
a file or talks to the application layer.

Contextual actions never receive a slash name, so the catalogue cannot grow a
fifteenth command by adding an action. ``palette_command`` is such an action: it
stays out of every listing so the palette never offers to open itself.

Public API:
    PALETTE_COMMAND_NAME: Name of the action that opens the command palette.
    PALETTE_KEY: Key the specification reserves for the command palette.
    CommandHost: Behaviour the catalogue delegates to.
    global_commands: Build the fourteen commands of the frozen catalogue.
    palette_command: Build the hidden action that opens the command palette.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Protocol

from anishift.tui.commands.spec import CommandCategory, CommandSpec

if TYPE_CHECKING:
    from anishift.tui.commands.spec import CommandRun

__all__ = [
    "PALETTE_COMMAND_NAME",
    "PALETTE_KEY",
    "CommandHost",
    "global_commands",
    "palette_command",
]

# ── Constants ──────────────────────────────────────────────────────────────

PALETTE_COMMAND_NAME: Final[str] = "palette"
"""Name of the contextual action that opens the command palette."""

PALETTE_KEY: Final[str] = "ctrl+p"
"""Key the specification reserves for opening the command palette."""


class CommandHost(Protocol):
    """Behaviour the catalogue delegates to, one method per frozen command."""

    def open_init(self) -> None:
        """Prepare the workspace and the configuration, then show the next steps."""

    def open_connect(self) -> None:
        """Edit the Palantir Foundry connection and probe one model on request."""

    def show_status(self) -> None:
        """Show the safe summary of configuration, workspace and current run."""

    def show_debug(self) -> None:
        """Show the wider redacted diagnostics of the current session."""

    def show_help(self) -> None:
        """List the commands and the keys the registry currently holds."""

    def exit_app(self) -> None:
        """Leave the application, confirming first while a run is active."""

    def open_auto(self) -> None:
        """Configure the default automatic mode and its presets."""

    def open_manual(self) -> None:
        """Prepare the manual intents of the selected groups."""

    def open_model(self) -> None:
        """Choose the primary Palantir model from the local catalogue."""

    def open_translation(self) -> None:
        """Edit the translation settings and their own model."""

    def open_prompts(self) -> None:
        """Choose the task prompt, the style and the prompt modules."""

    def open_tts(self) -> None:
        """Edit the speech settings, the voices and the audio profile."""

    def open_theme(self) -> None:
        """Choose the theme with a live preview and a rollback."""

    def run_doctor(self) -> None:
        """Run the technical diagnostics without repairing anything."""


def global_commands(host: CommandHost) -> tuple[CommandSpec, ...]:
    """Build the fourteen commands section 5 of the specification froze."""
    return (
        CommandSpec(
            name="init",
            title="Inicjalizacja",
            description="Przygotowuje workspace i konfigurację oraz pokazuje dalsze kroki.",
            category=CommandCategory.SESSION,
            run=host.open_init,
            slash_name="init",
        ),
        CommandSpec(
            name="connect",
            title="Połączenie Foundry",
            description="Konfiguruje połączenie Palantir Foundry i sprawdza jeden model po potwierdzeniu.",
            category=CommandCategory.SESSION,
            run=host.open_connect,
            slash_name="connect",
        ),
        CommandSpec(
            name="status",
            title="Stan sesji",
            description="Pokazuje bezpieczne podsumowanie konfiguracji, workspace i aktywnego przebiegu.",
            category=CommandCategory.DIAGNOSTICS,
            run=host.show_status,
            slash_name="status",
        ),
        CommandSpec(
            name="debug",
            title="Diagnostyka rozszerzona",
            description="Pokazuje zredagowaną diagnostykę bez sekretów i bez treści użytkownika.",
            category=CommandCategory.DIAGNOSTICS,
            run=host.show_debug,
            slash_name="debug",
        ),
        CommandSpec(
            name="help",
            title="Pomoc",
            description="Wypisuje komendy i aktualne skróty z żywego rejestru.",
            category=CommandCategory.SESSION,
            run=host.show_help,
            slash_name="help",
        ),
        CommandSpec(
            name="exit",
            title="Wyjście",
            description="Zamyka aplikację; aktywny przebieg wymaga potwierdzenia.",
            category=CommandCategory.SESSION,
            run=host.exit_app,
            slash_name="exit",
        ),
        CommandSpec(
            name="auto",
            title="Tryb Auto",
            description="Konfiguruje domyślny tryb Auto i presety; nigdy nie uruchamia przetwarzania.",
            category=CommandCategory.WORKFLOW,
            run=host.open_auto,
            slash_name="auto",
        ),
        CommandSpec(
            name="manual",
            title="Tryb Manual",
            description="Przygotowuje intencje grup i prowadzi przez Preview oraz jawny Start.",
            category=CommandCategory.WORKFLOW,
            run=host.open_manual,
            slash_name="manual",
        ),
        CommandSpec(
            name="model",
            title="Model główny",
            description="Wybiera główny model Palantir z lokalnego katalogu modeli.",
            category=CommandCategory.SETTINGS,
            run=host.open_model,
            slash_name="model",
        ),
        CommandSpec(
            name="translation",
            title="Tłumaczenie",
            description="Ustawia tłumaczenie oraz niezależny model LLM do tłumaczenia.",
            category=CommandCategory.SETTINGS,
            run=host.open_translation,
            slash_name="translation",
        ),
        CommandSpec(
            name="prompts",
            title="Prompty",
            description="Wybiera prompt zadania, styl wypowiedzi i moduły promptu.",
            category=CommandCategory.SETTINGS,
            run=host.open_prompts,
            slash_name="prompts",
        ),
        CommandSpec(
            name="tts",
            title="Synteza mowy",
            description="Ustawia TTS, głosy, profil audio i klucze związane z TTS.",
            category=CommandCategory.SETTINGS,
            run=host.open_tts,
            slash_name="tts",
        ),
        CommandSpec(
            name="theme",
            title="Motyw",
            description="Wybiera motyw z podglądem na żywo i wycofaniem po Esc.",
            category=CommandCategory.SETTINGS,
            run=host.open_theme,
            slash_name="theme",
        ),
        CommandSpec(
            name="doctor",
            title="Diagnostyka techniczna",
            description="Uruchamia diagnostykę techniczną bez automatycznej naprawy.",
            category=CommandCategory.DIAGNOSTICS,
            run=host.run_doctor,
            slash_name="doctor",
        ),
    )


def palette_command(run: CommandRun) -> CommandSpec:
    """Build the hidden action that opens the palette without listing itself."""
    return CommandSpec(
        name=PALETTE_COMMAND_NAME,
        title="Paleta komend",
        description="Otwiera listę dostępnych komend i akcji kontekstowych.",
        category=CommandCategory.ACTION,
        run=run,
        hidden=True,
        keys=(PALETTE_KEY,),
    )

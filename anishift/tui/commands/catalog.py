"""The fourteen frozen command definitions, and none of their behaviour."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Protocol

from anishift.tui import strings
from anishift.tui.commands.spec import CommandCategory, CommandSpec

if TYPE_CHECKING:
    from anishift.tui.commands.spec import CommandRun

__all__ = [
    "EXIT_COMMAND_NAME",
    "EXIT_KEY",
    "PALETTE_COMMAND_NAME",
    "PALETTE_KEY",
    "CommandHost",
    "global_commands",
    "palette_command",
]

# ── Constants ──────────────────────────────────────────────────────────────

EXIT_COMMAND_NAME: Final[str] = "exit"
"""Name of the one command that leaves the application, whatever asks for it."""

PALETTE_COMMAND_NAME: Final[str] = "palette"
"""Name of the contextual action that opens the command palette."""

PALETTE_KEY: Final[str] = "ctrl+p"
"""Key the specification reserves for opening the command palette."""

EXIT_KEY: Final[str] = "ctrl+c"
"""Key that leaves the application, through the one exit command."""


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
            title=strings.COMMAND_INIT_TITLE,
            description=strings.COMMAND_INIT_DESCRIPTION,
            category=CommandCategory.SESSION,
            run=host.open_init,
            slash_name="init",
        ),
        CommandSpec(
            name="connect",
            title=strings.COMMAND_CONNECT_TITLE,
            description=strings.COMMAND_CONNECT_DESCRIPTION,
            category=CommandCategory.SESSION,
            run=host.open_connect,
            slash_name="connect",
        ),
        CommandSpec(
            name="status",
            title=strings.COMMAND_STATUS_TITLE,
            description=strings.COMMAND_STATUS_DESCRIPTION,
            category=CommandCategory.DIAGNOSTICS,
            run=host.show_status,
            slash_name="status",
        ),
        CommandSpec(
            name="debug",
            title=strings.COMMAND_DEBUG_TITLE,
            description=strings.COMMAND_DEBUG_DESCRIPTION,
            category=CommandCategory.DIAGNOSTICS,
            run=host.show_debug,
            slash_name="debug",
        ),
        CommandSpec(
            name="help",
            title=strings.COMMAND_HELP_TITLE,
            description=strings.COMMAND_HELP_DESCRIPTION,
            category=CommandCategory.SESSION,
            run=host.show_help,
            slash_name="help",
        ),
        CommandSpec(
            name=EXIT_COMMAND_NAME,
            title=strings.COMMAND_EXIT_TITLE,
            description=strings.COMMAND_EXIT_DESCRIPTION,
            category=CommandCategory.SESSION,
            run=host.exit_app,
            slash_name=EXIT_COMMAND_NAME,
            keys=(EXIT_KEY,),
        ),
        CommandSpec(
            name="auto",
            title=strings.COMMAND_AUTO_TITLE,
            description=strings.COMMAND_AUTO_DESCRIPTION,
            category=CommandCategory.WORKFLOW,
            run=host.open_auto,
            slash_name="auto",
        ),
        CommandSpec(
            name="manual",
            title=strings.COMMAND_MANUAL_TITLE,
            description=strings.COMMAND_MANUAL_DESCRIPTION,
            category=CommandCategory.WORKFLOW,
            run=host.open_manual,
            slash_name="manual",
        ),
        CommandSpec(
            name="model",
            title=strings.COMMAND_MODEL_TITLE,
            description=strings.COMMAND_MODEL_DESCRIPTION,
            category=CommandCategory.SETTINGS,
            run=host.open_model,
            slash_name="model",
        ),
        CommandSpec(
            name="translation",
            title=strings.COMMAND_TRANSLATION_TITLE,
            description=strings.COMMAND_TRANSLATION_DESCRIPTION,
            category=CommandCategory.SETTINGS,
            run=host.open_translation,
            slash_name="translation",
        ),
        CommandSpec(
            name="prompts",
            title=strings.COMMAND_PROMPTS_TITLE,
            description=strings.COMMAND_PROMPTS_DESCRIPTION,
            category=CommandCategory.SETTINGS,
            run=host.open_prompts,
            slash_name="prompts",
        ),
        CommandSpec(
            name="tts",
            title=strings.COMMAND_TTS_TITLE,
            description=strings.COMMAND_TTS_DESCRIPTION,
            category=CommandCategory.SETTINGS,
            run=host.open_tts,
            slash_name="tts",
        ),
        CommandSpec(
            name="theme",
            title=strings.COMMAND_THEME_TITLE,
            description=strings.COMMAND_THEME_DESCRIPTION,
            category=CommandCategory.SETTINGS,
            run=host.open_theme,
            slash_name="theme",
        ),
        CommandSpec(
            name="doctor",
            title=strings.COMMAND_DOCTOR_TITLE,
            description=strings.COMMAND_DOCTOR_DESCRIPTION,
            category=CommandCategory.DIAGNOSTICS,
            run=host.run_doctor,
            slash_name="doctor",
        ),
    )


def palette_command(run: CommandRun) -> CommandSpec:
    """Build the hidden action that opens the palette without listing itself."""
    return CommandSpec(
        name=PALETTE_COMMAND_NAME,
        title=strings.COMMAND_PALETTE_TITLE,
        description=strings.COMMAND_PALETTE_DESCRIPTION,
        category=CommandCategory.ACTION,
        run=run,
        hidden=True,
        keys=(PALETTE_KEY,),
    )

"""Every string the shell shows a user, written exactly once and in English."""

from __future__ import annotations

from typing import Final

__all__ = [
    "COMMAND_AUTO_DESCRIPTION",
    "COMMAND_AUTO_TITLE",
    "COMMAND_CONNECT_DESCRIPTION",
    "COMMAND_CONNECT_TITLE",
    "COMMAND_DEBUG_DESCRIPTION",
    "COMMAND_DEBUG_TITLE",
    "COMMAND_DOCTOR_DESCRIPTION",
    "COMMAND_DOCTOR_TITLE",
    "COMMAND_EXIT_DESCRIPTION",
    "COMMAND_EXIT_TITLE",
    "COMMAND_HELP_DESCRIPTION",
    "COMMAND_HELP_TITLE",
    "COMMAND_INIT_DESCRIPTION",
    "COMMAND_INIT_TITLE",
    "COMMAND_MANUAL_DESCRIPTION",
    "COMMAND_MANUAL_TITLE",
    "COMMAND_MODEL_DESCRIPTION",
    "COMMAND_MODEL_TITLE",
    "COMMAND_PALETTE_DESCRIPTION",
    "COMMAND_PALETTE_TITLE",
    "COMMAND_PROMPTS_DESCRIPTION",
    "COMMAND_PROMPTS_TITLE",
    "COMMAND_STATUS_DESCRIPTION",
    "COMMAND_STATUS_TITLE",
    "COMMAND_THEME_DESCRIPTION",
    "COMMAND_THEME_TITLE",
    "COMMAND_TRANSLATION_DESCRIPTION",
    "COMMAND_TRANSLATION_TITLE",
    "COMMAND_TTS_DESCRIPTION",
    "COMMAND_TTS_TITLE",
    "COMPOSER_ACCENT_GLYPH",
    "COMPOSER_PLACEHOLDER",
    "COMPOSER_PLAIN_TEXT",
    "COMPOSER_TAIL_EDGE_GLYPH",
    "COMPOSER_TAIL_GLYPH",
    "COMPOSER_UNKNOWN_COMMAND",
    "COMPOSER_UNKNOWN_COMMAND_SUGGESTION",
    "CONTEXT_MODEL_SEPARATOR",
    "CONTEXT_MODEL_UNSET",
    "CONTEXT_MODE_AUTO",
    "CONTEXT_MODE_DEMO",
    "CONTEXT_PROVIDER",
    "CONTEXT_SEPARATOR",
    "DEMO_GROUP_FIVE",
    "DEMO_GROUP_FOUR",
    "DEMO_GROUP_ONE",
    "DEMO_GROUP_THREE",
    "DEMO_GROUP_TWO",
    "DEMO_TITLE",
    "DIALOG_CANCEL_LABEL",
    "DIALOG_CONFIRM_LABEL",
    "DIALOG_DOWN_LABEL",
    "DIALOG_FIRST_LABEL",
    "DIALOG_LAST_LABEL",
    "DIALOG_PAGE_DOWN_LABEL",
    "DIALOG_PAGE_UP_LABEL",
    "DIALOG_UP_LABEL",
    "GLYPH_GAP",
    "GROUP_COLUMN_GAP",
    "GROUP_CONFLICT_GLYPH",
    "GROUP_MISSING_GLYPH",
    "GROUP_READY_GLYPH",
    "GROUP_SELECTED_GLYPH",
    "GROUP_STATE_CONFLICT",
    "GROUP_STATE_NO_SIDECAR",
    "GROUP_STATE_READY",
    "GROUP_UNSELECTED_GLYPH",
    "HINT_ENTER_KEY",
    "HINT_ENTER_LABEL",
    "HINT_KEY_GAP",
    "HINT_PAIR_GAP",
    "HOME_MARK",
    "LOCATION_SEPARATOR",
    "MISSING_SURFACE",
    "PALETTE_COMMAND_CATEGORY",
    "PALETTE_SUGGESTED_CATEGORY",
    "PALETTE_TITLE",
    "PATH_ELLIPSIS",
    "REORDER_ADD_HINT",
    "REORDER_ADD_LABEL",
    "REORDER_DELETE_PROMPT",
    "REORDER_MOVE_DOWN_LABEL",
    "REORDER_MOVE_UP_LABEL",
    "REORDER_NOTHING_TO_ADD",
    "REORDER_ORDER_HINT",
    "REORDER_REMOVE_LABEL",
    "RUN_DONE",
    "RUN_PLANNING",
    "RUN_STEP_SPEECH",
    "RUN_WORKING",
    "SELECTION_SUMMARY",
    "SELECT_DISABLED_OPTION",
    "SELECT_FILTER_PLACEHOLDER",
    "SELECT_NO_RESULTS",
    "SETTINGS_OFF",
    "SETTINGS_ON",
    "SETTING_BOOST_DESCRIPTION",
    "SETTING_BOOST_TITLE",
    "SETTING_CONCURRENCY_DESCRIPTION",
    "SETTING_CONCURRENCY_TITLE",
    "SETTING_ENGINE_DESCRIPTION",
    "SETTING_ENGINE_TITLE",
    "SETTING_GAIN_DESCRIPTION",
    "SETTING_GAIN_TITLE",
    "SETTING_RETRIES_DESCRIPTION",
    "SETTING_RETRIES_TITLE",
    "SETTING_TEMPO_DESCRIPTION",
    "SETTING_TEMPO_TITLE",
    "STATUS_GLYPH",
    "SUGGESTION_COMPLETE_LABEL",
    "SUGGESTION_DISMISS_LABEL",
    "SUGGESTION_NEXT_LABEL",
    "SUGGESTION_PREVIOUS_LABEL",
    "SUGGESTION_ROW_GAP",
    "THEME_DARK_DESCRIPTION",
    "THEME_DARK_TITLE",
    "THEME_LIGHT_DESCRIPTION",
    "THEME_LIGHT_TITLE",
    "TIP_GLYPH",
    "TIP_LABEL",
    "TIP_TEXT",
    "TTS_ENGINE_EDGE",
    "TTS_ENGINE_ELEVENBYTES",
    "TTS_ENGINE_ELEVENLABS",
    "TTS_ENGINE_SAPI",
    "VALUE_ABOVE_MAXIMUM",
    "VALUE_BELOW_MINIMUM",
    "VALUE_CONFIRM_HINT",
    "VALUE_LESS_LABEL",
    "VALUE_MORE_LABEL",
    "VALUE_NOT_A_NUMBER",
    "VALUE_OPTIONAL_HINT",
    "VALUE_OUT_OF_RANGE",
    "VALUE_RANGE_LABEL",
    "VALUE_RANGE_OPEN_END",
    "VALUE_REQUIRED",
    "VALUE_STEP_LABEL",
    "WORKSPACE_EMPTY",
]

# ── Constants ──────────────────────────────────────────────────────────────

COMPOSER_PLACEHOLDER: Final[str] = "Press enter to dub, or type / for commands"
"""Hint the empty composer field shows, written once by the specification."""

COMPOSER_ACCENT_GLYPH: Final[str] = "▌"
"""Glyph drawing the vertical accent on the left edge of the composer box."""

COMPOSER_TAIL_GLYPH: Final[str] = "▀"
"""Glyph closing the composer box with the upper half of one row."""

COMPOSER_TAIL_EDGE_GLYPH: Final[str] = "▘"
"""Glyph carrying the accent edge through the upper half of the closing row."""

COMPOSER_PLAIN_TEXT: Final[str] = "Chat mode is not available yet"
"""Answer to text that names no command; the text stays in the field."""

COMPOSER_UNKNOWN_COMMAND: Final[str] = "Unknown command"
"""Answer to a slash command the registry does not hold and cannot guess."""

COMPOSER_UNKNOWN_COMMAND_SUGGESTION: Final[str] = "Unknown command, did you mean {command}?"
"""Answer naming the one closest known command instead of running anything."""

SUGGESTION_PREVIOUS_LABEL: Final[str] = "Previous suggestion"
"""Action label of the key moving the suggestion popup one row up."""

SUGGESTION_NEXT_LABEL: Final[str] = "Next suggestion"
"""Action label of the key moving the suggestion popup one row down."""

SUGGESTION_COMPLETE_LABEL: Final[str] = "Complete name"
"""Action label of the key writing the highlighted name into the field."""

SUGGESTION_DISMISS_LABEL: Final[str] = "Hide suggestions"
"""Action label of the key taking the suggestion popup off the screen."""

SUGGESTION_ROW_GAP: Final[str] = "  "
"""Separator between the name of a suggested command and its sentence."""

GLYPH_GAP: Final[str] = " "
"""Separator between a glyph and the text that glyph marks."""

CONTEXT_SEPARATOR: Final[str] = " · "
"""Separator between the mode and the provider of the context line."""

CONTEXT_MODEL_SEPARATOR: Final[str] = ": "
"""Separator between the provider and the model of the context line."""

CONTEXT_MODE_AUTO: Final[str] = "Auto"
"""Mode the context line reports while Auto is the default workflow."""

CONTEXT_MODE_DEMO: Final[str] = "Demo"
"""Mode the context line reports while the session simulates every workflow."""

DEMO_TITLE: Final[str] = "AniShift Demo"
"""Terminal title of a session that simulates every workflow."""

CONTEXT_PROVIDER: Final[str] = "Foundry"
"""Provider the context line reports for the primary model."""

CONTEXT_MODEL_UNSET: Final[str] = "no model selected"
"""Model segment of the context line while no catalogue entry is chosen."""

HINT_ENTER_KEY: Final[str] = "enter"
"""Key of the hint describing what an empty composer line starts."""

HINT_ENTER_LABEL: Final[str] = "auto"
"""Label of the hint describing what an empty composer line starts."""

HINT_KEY_GAP: Final[str] = " "
"""Separator between one key and the label of the action it runs."""

HINT_PAIR_GAP: Final[str] = "   "
"""Separator between two whole key hints of the same row."""

TIP_GLYPH: Final[str] = "●"
"""Bullet in front of the tip line, so the tip reads as a tip without colour."""

TIP_LABEL: Final[str] = "Tip"
"""Word marking the tip line, which is the first thing a small terminal drops."""

TIP_TEXT: Final[str] = "Drop an MKV into workspace to begin"
"""The one tip the start screen offers while nothing has been discovered."""

LOCATION_SEPARATOR: Final[str] = ":"
"""Separator between the working path and the git branch of the bottom bar."""

HOME_MARK: Final[str] = "~"
"""Stand-in the bottom bar puts in place of the home directory of the user."""

PATH_ELLIPSIS: Final[str] = "…"
"""Mark of a working path the bottom bar had to shorten from the left."""

WORKSPACE_EMPTY: Final[str] = "No supported files in workspace"
"""Base state shown while the workspace holds no supported source file."""

MISSING_SURFACE: Final[str] = "This surface is not available yet"
"""Missing state a command reports while its own surface is not built."""

PALETTE_TITLE: Final[str] = "Commands"
"""Heading of the palette dialog."""

PALETTE_SUGGESTED_CATEGORY: Final[str] = "Suggested"
"""Heading the palette groups the likely next steps under."""

PALETTE_COMMAND_CATEGORY: Final[str] = "Commands"
"""Heading the palette groups every remaining command under."""

COMMAND_INIT_TITLE: Final[str] = "Init"
"""Title of the ``init`` command."""

COMMAND_INIT_DESCRIPTION: Final[str] = "Guided workspace setup"
"""Description of the ``init`` command."""

COMMAND_CONNECT_TITLE: Final[str] = "Connect"
"""Title of the ``connect`` command."""

COMMAND_CONNECT_DESCRIPTION: Final[str] = "Connect provider"
"""Description of the ``connect`` command."""

COMMAND_STATUS_TITLE: Final[str] = "Status"
"""Title of the ``status`` command."""

COMMAND_STATUS_DESCRIPTION: Final[str] = "Show session status"
"""Description of the ``status`` command."""

COMMAND_DEBUG_TITLE: Final[str] = "Debug"
"""Title of the ``debug`` command."""

COMMAND_DEBUG_DESCRIPTION: Final[str] = "View debug info"
"""Description of the ``debug`` command."""

COMMAND_HELP_TITLE: Final[str] = "Help"
"""Title of the ``help`` command."""

COMMAND_HELP_DESCRIPTION: Final[str] = "Help"
"""Description of the ``help`` command."""

COMMAND_EXIT_TITLE: Final[str] = "Exit"
"""Title of the ``exit`` command."""

COMMAND_EXIT_DESCRIPTION: Final[str] = "Exit the app"
"""Description of the ``exit`` command."""

COMMAND_AUTO_TITLE: Final[str] = "Auto"
"""Title of the ``auto`` command."""

COMMAND_AUTO_DESCRIPTION: Final[str] = "Configure auto mode"
"""Description of the ``auto`` command."""

COMMAND_MANUAL_TITLE: Final[str] = "Manual"
"""Title of the ``manual`` command."""

COMMAND_MANUAL_DESCRIPTION: Final[str] = "Pick groups manually"
"""Description of the ``manual`` command."""

COMMAND_MODEL_TITLE: Final[str] = "Model"
"""Title of the ``model`` command."""

COMMAND_MODEL_DESCRIPTION: Final[str] = "Switch model"
"""Description of the ``model`` command."""

COMMAND_TRANSLATION_TITLE: Final[str] = "Translation"
"""Title of the ``translation`` command."""

COMMAND_TRANSLATION_DESCRIPTION: Final[str] = "Configure translation"
"""Description of the ``translation`` command."""

COMMAND_PROMPTS_TITLE: Final[str] = "Prompts"
"""Title of the ``prompts`` command."""

COMMAND_PROMPTS_DESCRIPTION: Final[str] = "Choose prompts"
"""Description of the ``prompts`` command."""

COMMAND_TTS_TITLE: Final[str] = "Speech"
"""Title of the ``tts`` command."""

COMMAND_TTS_DESCRIPTION: Final[str] = "Configure speech"
"""Description of the ``tts`` command."""

COMMAND_THEME_TITLE: Final[str] = "Theme"
"""Title of the ``theme`` command."""

COMMAND_THEME_DESCRIPTION: Final[str] = "Switch theme"
"""Description of the ``theme`` command."""

COMMAND_DOCTOR_TITLE: Final[str] = "Doctor"
"""Title of the ``doctor`` command."""

COMMAND_DOCTOR_DESCRIPTION: Final[str] = "Run diagnostics"
"""Description of the ``doctor`` command."""

COMMAND_PALETTE_TITLE: Final[str] = "Commands"
"""Title of the contextual action that opens the palette."""

COMMAND_PALETTE_DESCRIPTION: Final[str] = "Open command list"
"""Description of the contextual action that opens the palette."""

DIALOG_CANCEL_LABEL: Final[str] = "Cancel"
"""Action label of the key that leaves a dialog without a decision."""

DIALOG_CONFIRM_LABEL: Final[str] = "Confirm"
"""Action label of the key that hands a decision back to the caller."""

DIALOG_UP_LABEL: Final[str] = "Up"
"""Action label of the key moving a dialog cursor one row up."""

DIALOG_DOWN_LABEL: Final[str] = "Down"
"""Action label of the key moving a dialog cursor one row down."""

DIALOG_PAGE_UP_LABEL: Final[str] = "Page up"
"""Action label of the key moving a dialog cursor one page up."""

DIALOG_PAGE_DOWN_LABEL: Final[str] = "Page down"
"""Action label of the key moving a dialog cursor one page down."""

DIALOG_FIRST_LABEL: Final[str] = "First"
"""Action label of the key moving a dialog cursor to the first row."""

DIALOG_LAST_LABEL: Final[str] = "Last"
"""Action label of the key moving a dialog cursor to the last row."""

SELECT_NO_RESULTS: Final[str] = "No matches"
"""Row the list shows when the filter matches nothing."""

SELECT_DISABLED_OPTION: Final[str] = "This option is unavailable"
"""Message the dialog shows instead of confirming a disabled row."""

SELECT_FILTER_PLACEHOLDER: Final[str] = "Filter…"
"""Hint the empty filter box of the list selector shows."""

VALUE_REQUIRED: Final[str] = "A value is required"
"""Reason shown when a required value was left empty."""

VALUE_NOT_A_NUMBER: Final[str] = "Enter a number"
"""Reason shown when the typed text is not a number at all."""

VALUE_OPTIONAL_HINT: Final[str] = "An empty field clears the value"
"""Hint telling that an empty value is allowed."""

VALUE_CONFIRM_HINT: Final[str] = "Enter confirms · Esc cancels"
"""Hint of the confirmation dialog, naming both keys that answer it."""

VALUE_RANGE_LABEL: Final[str] = "Range"
"""Word introducing the two ends of a number range."""

VALUE_STEP_LABEL: Final[str] = "step"
"""Word introducing the amount one key press moves a number by."""

VALUE_RANGE_OPEN_END: Final[str] = "…"
"""Stand-in for the end of a range the field leaves unbounded."""

VALUE_OUT_OF_RANGE: Final[str] = "Enter a value between {minimum} and {maximum}"
"""Reason shown when a number left the range bounded at both ends."""

VALUE_BELOW_MINIMUM: Final[str] = "Enter a value of at least {minimum}"
"""Reason shown when a number fell below the only bound of its field."""

VALUE_ABOVE_MAXIMUM: Final[str] = "Enter a value of at most {maximum}"
"""Reason shown when a number rose above the only bound of its field."""

VALUE_MORE_LABEL: Final[str] = "More"
"""Action label of the key raising a number by one step."""

VALUE_LESS_LABEL: Final[str] = "Less"
"""Action label of the key lowering a number by one step."""

REORDER_MOVE_UP_LABEL: Final[str] = "Move up"
"""Action label of the key moving the highlighted member one place up."""

REORDER_MOVE_DOWN_LABEL: Final[str] = "Move down"
"""Action label of the key moving the highlighted member one place down."""

REORDER_REMOVE_LABEL: Final[str] = "Remove"
"""Action label of the key taking the highlighted member out of the list."""

REORDER_ADD_LABEL: Final[str] = "Add"
"""Action label of the key offering the candidates that are not members yet."""

REORDER_ORDER_HINT: Final[str] = "shift+↑/↓ move · a add · delete remove · enter save · esc discard"
"""Hint shown while the order itself is being edited."""

REORDER_ADD_HINT: Final[str] = "enter add the highlighted item · esc back to the order"
"""Hint shown while a member is being added."""

REORDER_NOTHING_TO_ADD: Final[str] = "Every item is already on the list"
"""Reason shown when every candidate is already a member."""

REORDER_DELETE_PROMPT: Final[str] = "Press delete again to remove: {item}"
"""Reason shown while the removal of one member waits for its second key."""

GROUP_SELECTED_GLYPH: Final[str] = "✓"
"""Marker of a source group the next workflow acts on."""

GROUP_UNSELECTED_GLYPH: Final[str] = "·"
"""Marker of a source group the next workflow leaves alone."""

GROUP_READY_GLYPH: Final[str] = "●"
"""Glyph of a group whose source needs no decision before a run."""

GROUP_CONFLICT_GLYPH: Final[str] = "▲"
"""Glyph of a group whose sources disagree with one another."""

GROUP_MISSING_GLYPH: Final[str] = "○"
"""Glyph of a group whose expected companion file is absent."""

GROUP_STATE_READY: Final[str] = "Ready"
"""State of a group whose source needs no decision before a run."""

GROUP_STATE_CONFLICT: Final[str] = "Conflict"
"""State of a group whose sources disagree with one another."""

GROUP_STATE_NO_SIDECAR: Final[str] = "No sidecar"
"""State of a group whose expected companion subtitle file is absent."""

GROUP_COLUMN_GAP: Final[str] = "  "
"""Separator between two columns of one group row."""

SELECTION_SUMMARY: Final[str] = "{selected} of {total} selected"
"""Row saying how many of the listed groups the next workflow acts on."""

STATUS_GLYPH: Final[str] = "●"
"""Bullet in front of the run status, so the row reads as a state."""

RUN_PLANNING: Final[str] = "Building plan…"
"""Base state shown while a plan is being built and nothing runs yet."""

RUN_WORKING: Final[str] = "Working"
"""Base state shown while a run is active."""

RUN_STEP_SPEECH: Final[str] = "Rendering speech"
"""Operation the running state names while speech is being produced."""

RUN_DONE: Final[str] = "Done"
"""Terminal state of a run that finished every group it admitted."""

DEMO_GROUP_ONE: Final[str] = "youjo-senki-ii-01"
"""Name of the first simulated source group."""

DEMO_GROUP_TWO: Final[str] = "youjo-senki-ii-02"
"""Name of the second simulated source group."""

DEMO_GROUP_THREE: Final[str] = "mushoku-tensei-s3-03"
"""Name of the third simulated source group."""

DEMO_GROUP_FOUR: Final[str] = "frieren-01"
"""Name of the fourth simulated source group."""

DEMO_GROUP_FIVE: Final[str] = "frieren-02"
"""Name of the fifth simulated source group."""

THEME_DARK_TITLE: Final[str] = "Dark"
"""Title of the dark theme row."""

THEME_DARK_DESCRIPTION: Final[str] = "Dark surfaces for a dim room"
"""Description of the dark theme row."""

THEME_LIGHT_TITLE: Final[str] = "Light"
"""Title of the light theme row."""

THEME_LIGHT_DESCRIPTION: Final[str] = "Light surfaces for a bright room"
"""Description of the light theme row."""

SETTINGS_ON: Final[str] = "On"
"""Value text of a switch that is turned on."""

SETTINGS_OFF: Final[str] = "Off"
"""Value text of a switch that is turned off."""

SETTING_ENGINE_TITLE: Final[str] = "Engine"
"""Title of the speech-engine field."""

SETTING_ENGINE_DESCRIPTION: Final[str] = "Choose the registered speech engine"
"""Description of the speech-engine field."""

SETTING_TEMPO_TITLE: Final[str] = "Tempo"
"""Title of the speech-tempo field."""

SETTING_TEMPO_DESCRIPTION: Final[str] = "Adjust the rendered speech tempo"
"""Description of the speech-tempo field."""

SETTING_GAIN_TITLE: Final[str] = "Voice gain"
"""Title of the voice-gain field."""

SETTING_GAIN_DESCRIPTION: Final[str] = "Offset this voice against the mix"
"""Description of the voice-gain field."""

SETTING_CONCURRENCY_TITLE: Final[str] = "Concurrency"
"""Title of the request-concurrency field."""

SETTING_CONCURRENCY_DESCRIPTION: Final[str] = "Limit simultaneous requests of the engine"
"""Description of the request-concurrency field."""

SETTING_RETRIES_TITLE: Final[str] = "Retries"
"""Title of the retry-count field."""

SETTING_RETRIES_DESCRIPTION: Final[str] = "Retry transient speech failures this often"
"""Description of the retry-count field."""

SETTING_BOOST_TITLE: Final[str] = "Speaker boost"
"""Title of the speaker-boost field."""

SETTING_BOOST_DESCRIPTION: Final[str] = "Ask the provider to boost the speaker"
"""Description of the speaker-boost field."""

TTS_ENGINE_EDGE: Final[str] = "edge"
"""Identifier of the Edge speech engine."""

TTS_ENGINE_ELEVENBYTES: Final[str] = "elevenbytes"
"""Identifier of the ElevenBytes speech engine."""

TTS_ENGINE_ELEVENLABS: Final[str] = "elevenlabs"
"""Identifier of the ElevenLabs speech engine."""

TTS_ENGINE_SAPI: Final[str] = "sapi"
"""Identifier of the Windows SAPI speech engine."""

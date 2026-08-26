"""Every string the shell shows a user, written exactly once and in English."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "AUTO_CANCELLED",
    "AUTO_DEFAULT_MARKER",
    "AUTO_DEFAULT_REFUSED",
    "AUTO_DEFAULT_SAVED",
    "AUTO_EDIT_LABEL",
    "AUTO_FIELDS_TITLE",
    "AUTO_FIELD_REFUSED",
    "AUTO_GROUPS_LABEL",
    "AUTO_LABEL_GAP",
    "AUTO_NO_CHANGES",
    "AUTO_NO_GROUPS",
    "AUTO_NO_PRESET",
    "AUTO_NO_WORKSPACE",
    "AUTO_OVERWRITE_QUESTION",
    "AUTO_OVERWRITE_TITLE",
    "AUTO_PLAN_BLOCKED",
    "AUTO_PRESET_LABEL",
    "AUTO_PRESET_SAVED",
    "AUTO_PROBLEMS_LABEL",
    "AUTO_PROBLEM_SEPARATOR",
    "AUTO_PRODUCTS_LABEL",
    "AUTO_READY_GROUPS",
    "AUTO_RESET_LABEL",
    "AUTO_SAVE_LABEL",
    "AUTO_UNSAVED_MARKER",
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
    "COMMAND_REFRESH_DESCRIPTION",
    "COMMAND_REFRESH_TITLE",
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
    "COMPOSER_UNKNOWN_COMMAND",
    "COMPOSER_UNKNOWN_COMMAND_SUGGESTION",
    "CONNECT_ADDRESS_CONFIGURED",
    "CONNECT_TEST_FAILED",
    "CONNECT_TEST_QUESTION",
    "CONNECT_TEST_TITLE",
    "CONNECT_TEST_VERIFIED",
    "CONNECT_TEST_WARNING",
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
    "DIALOG_ALREADY_OPEN",
    "DIALOG_CANCEL_LABEL",
    "DIALOG_CONFIRM_LABEL",
    "DIALOG_DOWN_LABEL",
    "DIALOG_FIRST_LABEL",
    "DIALOG_LAST_LABEL",
    "DIALOG_PAGE_DOWN_LABEL",
    "DIALOG_PAGE_UP_LABEL",
    "DIALOG_UP_LABEL",
    "EXIT_ACTIVE_RUN_QUESTION",
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
    "MANUAL_AUDIO_DESCRIPTION",
    "MANUAL_AUDIO_TITLE",
    "MANUAL_COPIED",
    "MANUAL_COPY_DESCRIPTION",
    "MANUAL_COPY_TITLE",
    "MANUAL_EDIT_TITLE",
    "MANUAL_EMPTY",
    "MANUAL_NO_SELECTION",
    "MANUAL_PATH_HINT",
    "MANUAL_POLICY_AUTO",
    "MANUAL_POLICY_EMBEDDED",
    "MANUAL_POLICY_EXTERNAL",
    "MANUAL_POLICY_NONE",
    "MANUAL_POLICY_READY_POLISH",
    "MANUAL_POLICY_SIDECAR",
    "MANUAL_POLICY_TITLE",
    "MANUAL_PREVIEW_DESCRIPTION",
    "MANUAL_PREVIEW_INCOMPLETE",
    "MANUAL_PREVIEW_TITLE",
    "MANUAL_PRODUCTS_TITLE",
    "MANUAL_PRODUCT_DISPLAYED_PL",
    "MANUAL_PRODUCT_FULL_PL",
    "MANUAL_PRODUCT_MKV",
    "MANUAL_PRODUCT_MP4",
    "MANUAL_PRODUCT_NARRATION_AUDIO",
    "MANUAL_PRODUCT_SOURCE_SUBTITLES",
    "MANUAL_PRODUCT_SPOKEN_PL",
    "MANUAL_ROLE_NARRATION_MIX",
    "MANUAL_ROLE_SOURCE_AUDIO",
    "MANUAL_ROLE_TITLE",
    "MANUAL_STATE_INVALID",
    "MANUAL_SUBTITLE_DESCRIPTION",
    "MANUAL_SUBTITLE_TITLE",
    "MANUAL_SUMMARY",
    "MANUAL_TRANSLATION_AUTO",
    "MANUAL_TRANSLATION_DO_NOT_TRANSLATE",
    "MANUAL_TRANSLATION_TITLE",
    "MANUAL_TRANSLATION_TRANSLATE",
    "MISSING_SURFACE",
    "MODEL_CATALOG_EMPTY",
    "MODEL_CATALOG_UNUSABLE",
    "MODEL_EXPERIMENTAL",
    "MODEL_ISSUES_CATEGORY",
    "MODEL_PICKER_TITLE",
    "MODEL_REFRESH_LABEL",
    "MODEL_ROW_SEPARATOR",
    "MODEL_SAVED",
    "MODEL_STATE_ERROR",
    "MODEL_STATE_UNVERIFIED",
    "MODEL_STATE_VERIFIED",
    "MODEL_TEST_TITLE",
    "MODEL_TIME_FORMAT",
    "OBJECT_ADD_LABEL",
    "OBJECT_REMOVE_LABEL",
    "OBJECT_REMOVE_QUESTION",
    "OBJECT_REMOVE_TITLE",
    "PALETTE_COMMAND_CATEGORY",
    "PALETTE_SUGGESTED_CATEGORY",
    "PALETTE_TITLE",
    "PATH_ELLIPSIS",
    "PLAN_BLOCKED_WORD",
    "PLAN_EMPTY",
    "PLAN_GROUP_GLYPH",
    "PLAN_INDENT",
    "PLAN_KEPT_WORD",
    "PLAN_NONE",
    "PLAN_OPERATIONS_LABEL",
    "PLAN_OPERATION_LABELS",
    "PLAN_OUTSIDE_WORKSPACE",
    "PLAN_PRODUCTS_LABEL",
    "PLAN_PROFILES_LABEL",
    "PLAN_PROFILE_MODEL_LABEL",
    "PLAN_PROFILE_SPEECH_LABEL",
    "PLAN_PROFILE_TRANSLATION_LABEL",
    "PLAN_REPLACES_WORD",
    "PLAN_SOURCES_LABEL",
    "PLAN_WARNING_WORD",
    "PREVIEW_BACK_DESCRIPTION",
    "PREVIEW_BACK_TITLE",
    "PREVIEW_LEFT",
    "PREVIEW_NO_PLAN",
    "PREVIEW_START_BLOCKED",
    "PREVIEW_START_DESCRIPTION",
    "PREVIEW_START_TITLE",
    "PREVIEW_TITLE",
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
    "SECRET_CONFIGURED",
    "SECRET_HINT",
    "SECRET_MISSING",
    "SECRET_OVERRIDDEN",
    "SECRET_REMOVED",
    "SECRET_REMOVE_LABEL",
    "SECRET_REMOVE_QUESTION",
    "SECRET_REMOVE_TITLE",
    "SECRET_STORED",
    "SELECTION_SUMMARY",
    "SELECT_DISABLED_OPTION",
    "SELECT_FILTER_PLACEHOLDER",
    "SELECT_NO_RESULTS",
    "SETTINGS_OFF",
    "SETTINGS_ON",
    "SETTING_EMPTY_VALUE",
    "SETTING_ENV_READONLY",
    "SETTING_INVALID_VALUE",
    "SETTING_LIST_SEPARATOR",
    "SETTING_UNSET",
    "SETUP_ACTION_DESCRIPTION",
    "SETUP_ACTION_TITLE",
    "SETUP_CONFIRM_QUESTION",
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
    "TOOLS_CATALOG_LABEL",
    "TOOLS_CATALOG_SUMMARY",
    "TOOLS_CHECK_FAIL_GLYPH",
    "TOOLS_CHECK_FAIL_WORD",
    "TOOLS_CHECK_OK_GLYPH",
    "TOOLS_CHECK_OK_WORD",
    "TOOLS_CHECK_SKIP_GLYPH",
    "TOOLS_CHECK_SKIP_WORD",
    "TOOLS_CHECK_WARN_GLYPH",
    "TOOLS_CHECK_WARN_WORD",
    "TOOLS_ENCODING_LABEL",
    "TOOLS_ENGINES_LABEL",
    "TOOLS_ENGINE_COUNT",
    "TOOLS_ERRORS_LABEL",
    "TOOLS_EVENTS_LABEL",
    "TOOLS_FILES_LABEL",
    "TOOLS_HELP_ACTIONS_HEADING",
    "TOOLS_HELP_COMMANDS_HEADING",
    "TOOLS_HELP_KEYS_HEADING",
    "TOOLS_INIT_CONNECT_STEP",
    "TOOLS_INIT_MODEL_STEP",
    "TOOLS_INIT_READY",
    "TOOLS_INIT_SETUP_STEP",
    "TOOLS_LABEL_GAP",
    "TOOLS_MAIN_MODEL_LABEL",
    "TOOLS_NONE",
    "TOOLS_PENDING",
    "TOOLS_PLATFORM_LABEL",
    "TOOLS_PRESET_LABEL",
    "TOOLS_PYTHON_LABEL",
    "TOOLS_RESULT_COUNT",
    "TOOLS_RESULT_LABEL",
    "TOOLS_RUN_CANCELLING",
    "TOOLS_RUN_IDLE",
    "TOOLS_RUN_LABEL",
    "TOOLS_RUN_PLANNING",
    "TOOLS_RUN_RUNNING",
    "TOOLS_RUN_TERMINAL",
    "TOOLS_SELECTION_LABEL",
    "TOOLS_SUGGESTION_GLYPH",
    "TOOLS_TRANSLATION_LABEL",
    "TOOLS_UNKNOWN",
    "TOOLS_VERSION_LABEL",
    "TOOLS_WORKERS_DRAINING",
    "TOOLS_WORKERS_IDLE",
    "TOOLS_WORKERS_LABEL",
    "TOOLS_WORKSPACE_GROUPS",
    "TOOLS_WORKSPACE_LABEL",
    "TOOLS_WORKSPACE_UNREAD",
    "TRANSLATION_MODEL_SAVED",
    "TRANSLATION_MODEL_TITLE",
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
    "WORKER_FAILED",
    "WORKSPACE_EMPTY",
]

# ── Constants ──────────────────────────────────────────────────────────────

COMPOSER_PLACEHOLDER: Final[str] = "Press enter to dub, or type / for commands"
"""Hint the empty composer field shows, written once by the specification."""

COMPOSER_ACCENT_GLYPH: Final[str] = "▌"
"""Glyph drawing the vertical accent on the left edge of the composer box."""

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

WORKER_FAILED: Final[str] = "The operation could not be completed"
"""Redacted reason of an operation that ended outside its own failure contract."""

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

COMMAND_REFRESH_TITLE: Final[str] = "Refresh"
"""Title of the contextual action that inspects the workspace again."""

COMMAND_REFRESH_DESCRIPTION: Final[str] = "Read the workspace again"
"""Description of the contextual action that inspects the workspace again."""

DIALOG_ALREADY_OPEN: Final[str] = "A dialog is already open, close it before opening another"
"""Message of every refused open while one dialog holds the screen."""

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

SETTING_UNSET: Final[str] = "Not set"
"""Value text of an optional field that holds no value."""

SETTING_EMPTY_VALUE: Final[str] = "Empty"
"""Value text of a list or set field that holds no members."""

SETTING_LIST_SEPARATOR: Final[str] = ", "
"""Separator between the members a list or set field shows."""

SETTING_INVALID_VALUE: Final[str] = "This value is not accepted here"
"""Reason shown when a typed value fails the field's own format."""

SETTING_ENV_READONLY: Final[str] = "From the environment"
"""Footer of a setting only the environment can supply, shown read-only."""

SECRET_CONFIGURED: Final[str] = "Configured"  # noqa: S105
"""Status of a secret the environment already holds a value for."""

SECRET_MISSING: Final[str] = "Missing"  # noqa: S105
"""Status of a secret the environment holds no value for."""

SECRET_HINT: Final[str] = "Type a value to store it; the stored value is never shown"  # noqa: S105
"""Hint of the secret editor, promising the value stays hidden."""

SECRET_STORED: Final[str] = "Stored in .env; the next run uses it"  # noqa: S105
"""Feedback shown after one secret was written to the environment file."""

SECRET_OVERRIDDEN: Final[str] = "Stored in .env, but a shell variable overrides it until you restart the shell"  # noqa: S105
"""Feedback shown when an exported variable still shadows the stored secret."""

SECRET_REMOVED: Final[str] = "Removed from .env"  # noqa: S105
"""Feedback shown after one secret was cleared from the environment file."""

SECRET_REMOVE_LABEL: Final[str] = "Clear secret"  # noqa: S105
"""Action label of the key that clears the highlighted secret."""

SECRET_REMOVE_TITLE: Final[str] = "Clear secret"  # noqa: S105
"""Heading of the dialog confirming a secret removal."""

SECRET_REMOVE_QUESTION: Final[str] = "Remove {label} from .env?"  # noqa: S105
"""Question the secret-removal dialog asks before clearing the key."""

OBJECT_ADD_LABEL: Final[str] = "Add"
"""Action label of the key that adds one item to an object list."""

OBJECT_REMOVE_LABEL: Final[str] = "Remove"
"""Action label of the key that removes the highlighted object-list item."""

OBJECT_REMOVE_TITLE: Final[str] = "Remove voice"
"""Heading of the dialog confirming an object-list removal."""

OBJECT_REMOVE_QUESTION: Final[str] = "Remove {alias}?"
"""Question the object-list removal dialog asks before dropping an item."""

MODEL_PICKER_TITLE: Final[str] = "Main model"
"""Heading of the picker that changes the main model role and nothing else."""

MODEL_TEST_TITLE: Final[str] = "Test model"
"""Heading of the picker that chooses the one alias a connection test uses."""

MODEL_ROW_SEPARATOR: Final[str] = " · "
"""Separator between the provider, the protocol and the state of one model row."""

MODEL_EXPERIMENTAL: Final[str] = "experimental"
"""Mark of a catalog entry the user wrote down as experimental."""

MODEL_STATE_UNVERIFIED: Final[str] = "Unverified"
"""State of an alias no connection test has confirmed in this session."""

MODEL_STATE_VERIFIED: Final[str] = "Verified {time}"
"""State of an alias one connection test confirmed, with the time it finished."""

MODEL_STATE_ERROR: Final[str] = "Failed {error_class}"
"""State of an alias whose single connection test failed, by safe error class."""

MODEL_CATALOG_UNUSABLE: Final[str] = "The model catalog cannot be read"
"""Row shown instead of any model when the catalog file cannot be used."""

MODEL_CATALOG_EMPTY: Final[str] = "The model catalog defines no usable model"
"""Row shown when the catalog is readable but holds no usable entry."""

MODEL_ISSUES_CATEGORY: Final[str] = "Catalog warnings"
"""Heading the picker groups every rejected catalog entry under."""

MODEL_REFRESH_LABEL: Final[str] = "Reload catalog"
"""Action label of the key that reads the catalog file again."""

MODEL_SAVED: Final[str] = "Main model set to {alias}"
"""Feedback shown after the main model role was changed."""

MODEL_TIME_FORMAT: Final[str] = "%H:%M"
"""Format of the moment one connection test finished."""

TRANSLATION_MODEL_TITLE: Final[str] = "Translation model"
"""Title of the alias selection the translation panel opens for the catalog provider."""

TRANSLATION_MODEL_SAVED: Final[str] = "Translation model set to {alias}"
"""Feedback shown after the translation model role alone was changed."""

CONNECT_ADDRESS_CONFIGURED: Final[str] = "Configured"
"""Status of an enrollment address that is set; the address itself is never shown."""

CONNECT_TEST_TITLE: Final[str] = "Connection test"
"""Title of the row and of the dialog that run one confirmed connection test."""

CONNECT_TEST_WARNING: Final[str] = "One minimal request is sent only after you confirm, and it may use provider quota"
"""Warning shown before anything is sent, both on the row and in the question."""

CONNECT_TEST_QUESTION: Final[str] = "Test {alias}? {warning}"
"""Question the confirmation asks before the single request is allowed."""

CONNECT_TEST_VERIFIED: Final[str] = "Connection verified for {alias} in this session only"
"""Feedback of a test that succeeded; the answer is never written anywhere."""

CONNECT_TEST_FAILED: Final[str] = "Connection test failed for {alias}: {error_class}"
"""Feedback of a test that failed, carrying only the safe error class."""

TOOLS_LABEL_GAP: Final[str] = "  "
"""Separator between the padded label of one report row and its value."""

TOOLS_PENDING: Final[str] = "Working…"
"""Row shown while the worker of one report is still collecting its answer."""

TOOLS_UNKNOWN: Final[str] = "unknown"
"""Value of a diagnostic the terminal itself does not answer."""

TOOLS_NONE: Final[str] = "None"
"""Value of a diagnostic that holds nothing yet."""

TOOLS_WORKSPACE_LABEL: Final[str] = "Workspace"
"""Label of the row saying what the last inspection found."""

TOOLS_WORKSPACE_GROUPS: Final[str] = "{groups} groups, {warnings} warnings"
"""Value saying how much the last inspection found, never naming a path."""

TOOLS_WORKSPACE_UNREAD: Final[str] = "Not read yet"
"""Value of the workspace row before any inspection has run."""

TOOLS_SELECTION_LABEL: Final[str] = "Selection"
"""Label of the row saying how many groups the next workflow acts on."""

TOOLS_PRESET_LABEL: Final[str] = "Preset"
"""Label of the row naming the preset new groups start from."""

TOOLS_MAIN_MODEL_LABEL: Final[str] = "Main model"
"""Label of the row naming the alias of the main model role."""

TOOLS_TRANSLATION_LABEL: Final[str] = "Translation"
"""Label of the row naming the translation provider and its model."""

TOOLS_ENGINES_LABEL: Final[str] = "Engines"
"""Label of the row counting the engines the configuration already allows."""

TOOLS_ENGINE_COUNT: Final[str] = "{domain} {ready} of {total}"
"""Value counting the ready engines of one domain."""

TOOLS_RUN_LABEL: Final[str] = "Run"
"""Label of the row naming the run state of this session."""

TOOLS_RUN_IDLE: Final[str] = "Idle"
"""Word the run state before any work is named by."""

TOOLS_RUN_PLANNING: Final[str] = "Planning"
"""Word the run state of a plan being built is named by."""

TOOLS_RUN_RUNNING: Final[str] = "Running"
"""Word the run state of an active run is named by."""

TOOLS_RUN_CANCELLING: Final[str] = "Cancelling"
"""Word the run state of a run that was asked to stop is named by."""

TOOLS_RUN_TERMINAL: Final[str] = "Finished"
"""Word the run state of a run that reached its end is named by."""

TOOLS_RESULT_LABEL: Final[str] = "Result"
"""Label of the row counting how the groups of the last run ended."""

TOOLS_RESULT_COUNT: Final[str] = "{count} {status}"
"""Value counting the groups of the last run that share one status."""

TOOLS_VERSION_LABEL: Final[str] = "Version"
"""Label of the row naming the installed version of this application."""

TOOLS_PYTHON_LABEL: Final[str] = "Python"
"""Label of the row naming the running interpreter version."""

TOOLS_PLATFORM_LABEL: Final[str] = "Platform"
"""Label of the row naming the operating system and its release."""

TOOLS_ENCODING_LABEL: Final[str] = "Encoding"
"""Label of the row naming the encoding this session writes with."""

TOOLS_FILES_LABEL: Final[str] = "Files"
"""Label of the row naming the local configuration files, never their paths."""

TOOLS_CATALOG_LABEL: Final[str] = "Catalog"
"""Label of the row saying what the local model catalog holds."""

TOOLS_CATALOG_SUMMARY: Final[str] = "{providers} providers, {models} models, {issues} warnings"
"""Value saying how much the local model catalog holds."""

TOOLS_EVENTS_LABEL: Final[str] = "Events"
"""Label of the row counting the run events this session received."""

TOOLS_WORKERS_LABEL: Final[str] = "Workers"
"""Label of the row saying whether run events are still being drained."""

TOOLS_WORKERS_DRAINING: Final[str] = "Draining run events"
"""Value of the worker row while the event pump is still reading."""

TOOLS_WORKERS_IDLE: Final[str] = "Idle"
"""Value of the worker row while no event pump is reading."""

TOOLS_ERRORS_LABEL: Final[str] = "Errors"
"""Label of the row carrying the safe error classes of this session."""

TOOLS_CHECK_OK_GLYPH: Final[str] = "●"
"""Glyph a finished diagnostic is marked with, ahead of its own word."""

TOOLS_CHECK_OK_WORD: Final[str] = "OK"
"""Word a finished diagnostic is named by, so the glyph is never alone."""

TOOLS_CHECK_WARN_GLYPH: Final[str] = "▲"
"""Glyph a diagnostic that only warns is marked with."""

TOOLS_CHECK_WARN_WORD: Final[str] = "Warning"
"""Word a diagnostic that only warns is named by."""

TOOLS_CHECK_FAIL_GLYPH: Final[str] = "✕"
"""Glyph a failed diagnostic is marked with."""

TOOLS_CHECK_FAIL_WORD: Final[str] = "Failed"
"""Word a failed diagnostic is named by."""

TOOLS_CHECK_SKIP_GLYPH: Final[str] = "○"
"""Glyph a skipped diagnostic is marked with."""

TOOLS_CHECK_SKIP_WORD: Final[str] = "Skipped"
"""Word a skipped diagnostic is named by."""

TOOLS_SUGGESTION_GLYPH: Final[str] = "→"
"""Glyph in front of the suggestion one diagnostic offers."""

TOOLS_INIT_READY: Final[str] = "Everything is ready"
"""Only row shown when no first step is missing any more."""

TOOLS_INIT_CONNECT_STEP: Final[str] = "Connect the provider with /connect"
"""Step shown while no provider token is configured."""

TOOLS_INIT_MODEL_STEP: Final[str] = "Choose the main model with /model"
"""Step shown while the main model role holds no alias."""

TOOLS_INIT_SETUP_STEP: Final[str] = "Install the external tools with {action}, from the palette ({key})"
"""Step naming the action that installs the external tools on request."""

TOOLS_HELP_COMMANDS_HEADING: Final[str] = "Commands"
"""Heading the help groups the slash commands under."""

TOOLS_HELP_ACTIONS_HEADING: Final[str] = "Actions"
"""Heading the help groups the contextual actions under."""

TOOLS_HELP_KEYS_HEADING: Final[str] = "Keys"
"""Heading the help groups the keys of the current context under."""

SETUP_ACTION_TITLE: Final[str] = "Setup"
"""Title of the contextual action that installs the external tools."""

SETUP_ACTION_DESCRIPTION: Final[str] = "Install the external tools"
"""Description of the contextual action that installs the external tools."""

SETUP_CONFIRM_QUESTION: Final[str] = "Download and install the external tools now?"
"""Question the confirmation asks before anything is downloaded."""

EXIT_ACTIVE_RUN_QUESTION: Final[str] = "A run is still active. Leave and stop it?"
"""Question the confirmation asks before an active run is abandoned."""

# ── Manual ──────────────────────────────────────────────────────────────────

MANUAL_EMPTY: Final[str] = "No groups selected for manual setup"
"""Base state shown while no selected group holds a manual draft."""

MANUAL_SUMMARY: Final[str] = "{count} groups in manual setup"
"""Row saying how many drafts the manual view currently prepares."""

MANUAL_STATE_INVALID: Final[str] = "Incomplete"
"""Word a draft that cannot yet be materialised is named by."""

MANUAL_PREVIEW_TITLE: Final[str] = "Preview"
"""Title of the contextual action that builds the manual plan."""

MANUAL_PREVIEW_DESCRIPTION: Final[str] = "Build the manual plan"
"""Description of the contextual action that builds the manual plan."""

MANUAL_PREVIEW_INCOMPLETE: Final[str] = "Every selected group needs a valid intent"
"""Reason a preview refuses while any draft cannot be materialised."""

MANUAL_NO_SELECTION: Final[str] = "Select at least one group first"
"""Reason a preview refuses while no draft is selected."""

MANUAL_COPY_TITLE: Final[str] = "Copy"
"""Title of the contextual action that copies one draft into the others."""

MANUAL_COPY_DESCRIPTION: Final[str] = "Copy this group into the others"
"""Description of the contextual action that copies one draft into the others."""

MANUAL_COPIED: Final[str] = "Copied into the other selected groups"
"""Feedback shown after one draft was copied into every other selection."""

MANUAL_SUBTITLE_TITLE: Final[str] = "External subtitle"
"""Title of the contextual action and the dialog that register a subtitle."""

MANUAL_SUBTITLE_DESCRIPTION: Final[str] = "Register an external subtitle"
"""Description of the contextual action that registers an external subtitle."""

MANUAL_AUDIO_TITLE: Final[str] = "External audio"
"""Title of the contextual action and the dialog that register an audio source."""

MANUAL_AUDIO_DESCRIPTION: Final[str] = "Register an external audio source"
"""Description of the contextual action that registers external audio."""

MANUAL_PATH_HINT: Final[str] = "Type the full path to the file"
"""Hint the external-source path editor shows."""

MANUAL_EDIT_TITLE: Final[str] = "Edit group"
"""Heading of the menu that opens one editable facet of a draft."""

MANUAL_PRODUCTS_TITLE: Final[str] = "Products"
"""Heading of the picker that chooses the requested products of a draft."""

MANUAL_POLICY_TITLE: Final[str] = "Subtitle source"
"""Heading of the picker that chooses the subtitle source policy of a draft."""

MANUAL_TRANSLATION_TITLE: Final[str] = "Translation"
"""Heading of the picker that chooses the translation decision of a draft."""

MANUAL_ROLE_TITLE: Final[str] = "Audio role"
"""Heading of the picker that chooses the role of a registered audio source."""

MANUAL_PRODUCT_SOURCE_SUBTITLES: Final[str] = "Source subtitles"
"""Label of the source-subtitles product."""

MANUAL_PRODUCT_FULL_PL: Final[str] = "Full Polish dub"
"""Label of the full Polish dub product."""

MANUAL_PRODUCT_SPOKEN_PL: Final[str] = "Spoken Polish"
"""Label of the spoken Polish product."""

MANUAL_PRODUCT_DISPLAYED_PL: Final[str] = "Displayed Polish"
"""Label of the displayed Polish product."""

MANUAL_PRODUCT_NARRATION_AUDIO: Final[str] = "Narration audio"
"""Label of the narration audio product."""

MANUAL_PRODUCT_MKV: Final[str] = "MKV"
"""Label of the MKV container product."""

MANUAL_PRODUCT_MP4: Final[str] = "MP4"
"""Label of the MP4 container product."""

MANUAL_POLICY_AUTO: Final[str] = "Auto"
"""Label of the automatic subtitle source policy."""

MANUAL_POLICY_SIDECAR: Final[str] = "Sidecar"
"""Label of the sidecar subtitle source policy."""

MANUAL_POLICY_EMBEDDED: Final[str] = "Embedded"
"""Label of the embedded subtitle source policy."""

MANUAL_POLICY_EXTERNAL: Final[str] = "External"
"""Label of the external subtitle source policy."""

MANUAL_POLICY_READY_POLISH: Final[str] = "Ready Polish"
"""Label of the ready-Polish subtitle source policy."""

MANUAL_POLICY_NONE: Final[str] = "None"
"""Label of the subtitle source policy that requests no subtitles."""

MANUAL_TRANSLATION_AUTO: Final[str] = "Auto"
"""Label of the automatic translation decision."""

MANUAL_TRANSLATION_TRANSLATE: Final[str] = "Translate"
"""Label of the translation decision that always translates."""

MANUAL_TRANSLATION_DO_NOT_TRANSLATE: Final[str] = "Do not translate"
"""Label of the translation decision that never translates."""

MANUAL_ROLE_SOURCE_AUDIO: Final[str] = "Source audio"
"""Label of the external audio role that supplies the source audio."""

MANUAL_ROLE_NARRATION_MIX: Final[str] = "Narration mix"
"""Label of the external audio role that supplies a narration mix."""

AUTO_PRESET_LABEL: Final[str] = "Preset"
"""Label of the row naming the automatic preset a run would use."""

AUTO_PRODUCTS_LABEL: Final[str] = "Products"
"""Label of the row listing the products the preset asks for."""

AUTO_GROUPS_LABEL: Final[str] = "Groups"
"""Label of the row counting the groups a default run would take."""

AUTO_PROBLEMS_LABEL: Final[str] = "Problems"
"""Label of the row listing what the last plan reported."""

AUTO_LABEL_GAP: Final[str] = "  "
"""Gap between a label of the automatic route and its value."""

AUTO_READY_GROUPS: Final[str] = "{ready} of {total} ready"
"""Value of the group row: groups a run may take out of every inspected one."""

AUTO_DEFAULT_MARKER: Final[str] = "default"
"""Word marking the preset an empty Enter would use."""

AUTO_UNSAVED_MARKER: Final[str] = "unsaved"
"""Word marking a preset whose draft holds changes nothing stored yet."""

AUTO_EDIT_LABEL: Final[str] = "Edit fields"
"""Label of the key that opens the fields of the highlighted preset."""

AUTO_SAVE_LABEL: Final[str] = "Save preset"
"""Label of the key that stores the edited draft."""

AUTO_RESET_LABEL: Final[str] = "Reset changes"
"""Label of the key that drops every unsaved change of the draft."""

AUTO_FIELDS_TITLE: Final[str] = "Preset fields"
"""Heading of the list holding every field of one automatic preset."""

AUTO_DEFAULT_SAVED: Final[str] = "Default preset is now {name}"
"""Feedback of one stored change of the default preset."""

AUTO_DEFAULT_REFUSED: Final[str] = "The default preset could not be saved"
"""Feedback of a default preset the preset file refused to keep."""

AUTO_PRESET_SAVED: Final[str] = "Preset {name} saved"
"""Feedback of one stored preset."""

AUTO_NO_CHANGES: Final[str] = "This preset has no unsaved changes"
"""Feedback of a save or a reset asked for while no draft holds a change."""

AUTO_FIELD_REFUSED: Final[str] = "This value does not fit the rest of the preset"
"""Feedback of one field value the preset contract refused."""

AUTO_NO_WORKSPACE: Final[str] = "Read the workspace first, nothing is inspected yet"
"""Reason a default run is refused while no inspection is held."""

AUTO_NO_GROUPS: Final[str] = "No inspected group is ready for a run"
"""Reason a default run is refused while every group needs attention first."""

AUTO_NO_PRESET: Final[str] = "No automatic preset is stored"
"""Reason a default run is refused while no preset can be resolved."""

AUTO_PLAN_BLOCKED: Final[str] = "The plan cannot run yet"
"""Reason a planned run is refused, shown next to the problems that block it."""

AUTO_CANCELLED: Final[str] = "The automatic run was not started"
"""Reason a planned run ended at the confirmation instead of at a start."""

AUTO_OVERWRITE_TITLE: Final[str] = "Replace products"
"""Heading of the confirmation asked before existing products are replaced."""

AUTO_OVERWRITE_QUESTION: Final[str] = "{products}\nStart anyway?"
"""Question carrying every product one accepted start would replace."""

AUTO_PROBLEM_SEPARATOR: Final[str] = "\n"
"""Separator between two problems one plan reported."""

# ── Preview ────────────────────────────────────────────────────────────────

PLAN_GROUP_GLYPH: Final[str] = "▪"
"""Glyph opening the block one group owns in a rendered plan."""

PLAN_INDENT: Final[str] = "  "
"""Indent shifting one detail line under the group heading that owns it."""

PLAN_SOURCES_LABEL: Final[str] = "Sources"
"""Label of the line naming the files one planned group reads."""

PLAN_OPERATIONS_LABEL: Final[str] = "Operations"
"""Label of the line naming the planned operations in execution order."""

PLAN_PRODUCTS_LABEL: Final[str] = "Products"
"""Label of the block naming the durable products one group would leave."""

PLAN_PROFILES_LABEL: Final[str] = "Profiles"
"""Heading of the block naming the engines and models one plan would use."""

PLAN_PROFILE_TRANSLATION_LABEL: Final[str] = "Translation"
"""Label of the translation profile one plan would run."""

PLAN_PROFILE_MODEL_LABEL: Final[str] = "Model"
"""Label of the language-model profile one plan would run."""

PLAN_PROFILE_SPEECH_LABEL: Final[str] = "Speech"
"""Label of the speech profile one plan would run."""

PLAN_BLOCKED_WORD: Final[str] = "Blocked"
"""Word naming a problem that stops a plan, shown beside its glyph."""

PLAN_WARNING_WORD: Final[str] = "Warning"
"""Word naming a problem a plan survives, shown beside its glyph."""

PLAN_REPLACES_WORD: Final[str] = "replaces an existing file"
"""Note marking a planned product that would take the place of another."""

PLAN_KEPT_WORD: Final[str] = "already there"
"""Note marking a product a plan found and would leave untouched."""

PLAN_NONE: Final[str] = "none"
"""Value shown where a plan lists nothing at all."""

PLAN_EMPTY: Final[str] = "There is no plan to preview yet"
"""Body shown where a preview has no plan to render."""

PLAN_OUTSIDE_WORKSPACE: Final[str] = "outside the workspace"
"""Stand-in for a location the preview refuses to spell out."""

PLAN_OPERATION_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "extract_audio": "Extract audio",
        "extract_subtitles": "Extract subtitles",
        "normalize_subtitles": "Normalize subtitles",
        "translate_subtitles": "Translate subtitles",
        "split_subtitles": "Split subtitles",
        "synthesize_speech": "Synthesize speech",
        "transcode_audio": "Transcode audio",
        "mix_narration": "Mix narration",
        "compose_mkv": "Compose MKV",
        "compose_mp4": "Compose MP4",
        "publish_artifact": "Publish product",
    },
)
"""Human label of every planned operation, keyed by the value of its task kind."""

PREVIEW_TITLE: Final[str] = "Preview"
"""Heading of the screen showing what a planned run would do."""

PREVIEW_START_TITLE: Final[str] = "Start"
"""Title of the action running the previewed plan."""

PREVIEW_START_DESCRIPTION: Final[str] = "Run the previewed plan"
"""Description of the start action, shown in the palette."""

PREVIEW_BACK_TITLE: Final[str] = "Back"
"""Title of the action leaving the preview for the screen that opened it."""

PREVIEW_BACK_DESCRIPTION: Final[str] = "Return without starting"
"""Description of the back action, shown in the palette."""

PREVIEW_NO_PLAN: Final[str] = "Plan something before previewing it"
"""Reason a preview refuses to open with nothing planned."""

PREVIEW_START_BLOCKED: Final[str] = "This plan cannot start while a problem blocks it"
"""Reason the start action refuses a plan carrying a blocking problem."""

PREVIEW_LEFT: Final[str] = "The plan was left without starting"
"""Reason a previewed plan ended at the back action instead of at a start."""

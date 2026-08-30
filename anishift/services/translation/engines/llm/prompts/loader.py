"""Load packaged Markdown prompts for LLM translation."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from importlib.resources.abc import Traversable

from natsort import natsorted

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.translation.engines.llm.constants import (
    RETRY_ERROR_PLACEHOLDER,
    RETRY_PROMPT_NAME,
    STYLES_DIRECTORY,
    SYSTEM_PROMPT_NAME,
    TRANSLATION_PROMPT_NAME,
)
from anishift.services.translation.errors import TranslationConfigError


@dataclass(frozen=True, slots=True)
class LoadedPrompts:
    """Complete prompt set for one translation style."""

    system: str
    translation: str
    retry: str
    style: str


class PromptLoader:
    """Discover and load prompts bundled with the translation module."""

    __slots__ = ("_root",)

    def __init__(self, root: Traversable | None = None) -> None:
        """Use the packaged prompt directory or an injected test root."""
        self._root = root or files(__package__)

    def available_styles(self) -> tuple[str, ...]:
        """Return deterministic names of valid immediate style resources."""
        styles_root = self._root.joinpath(STYLES_DIRECTORY)
        if not styles_root.is_dir():
            raise _prompt_error("styles", "The prompt styles directory is missing.")

        styles: dict[str, str] = {}
        for resource in styles_root.iterdir():
            if not resource.is_file() or not resource.name.endswith(".md"):
                continue
            style_name = resource.name.removesuffix(".md")
            if not style_name or style_name != style_name.strip():
                raise _prompt_error(resource.name, "Translation style names must not be blank.")
            normalized_name = style_name.casefold()
            if normalized_name in styles:
                raise _prompt_error(style_name, "Translation style names must be unique.")
            _read_prompt(resource, f"{STYLES_DIRECTORY}/{resource.name}")
            styles[normalized_name] = style_name
        if not styles:
            raise _prompt_error("styles", "At least one translation style is required.")
        return tuple(natsorted(styles.values(), key=str.casefold))

    def load(self, style_name: str) -> LoadedPrompts:
        """Load fixed base prompts and one discovered style prompt."""
        available_styles = self.available_styles()
        if style_name not in available_styles:
            raise _prompt_error(style_name, "The selected translation style does not exist.")

        system = _read_prompt(self._root.joinpath(SYSTEM_PROMPT_NAME), SYSTEM_PROMPT_NAME)
        translation = _read_prompt(
            self._root.joinpath(TRANSLATION_PROMPT_NAME),
            TRANSLATION_PROMPT_NAME,
        )
        retry = _read_prompt(self._root.joinpath(RETRY_PROMPT_NAME), RETRY_PROMPT_NAME)
        if retry.count(RETRY_ERROR_PLACEHOLDER) != 1:
            raise _prompt_error(
                RETRY_PROMPT_NAME,
                "The retry prompt must contain exactly one validation placeholder.",
            )
        style_resource = self._root.joinpath(STYLES_DIRECTORY, f"{style_name}.md")
        style = _read_prompt(style_resource, f"{STYLES_DIRECTORY}/{style_name}.md")
        return LoadedPrompts(
            system=system,
            translation=translation,
            retry=retry,
            style=style,
        )


@cache
def available_style_names() -> tuple[str, ...]:
    """Return translation style names bundled with the installed package."""
    return PromptLoader().available_styles()


def _read_prompt(resource: Traversable, resource_name: str) -> str:
    """Read one required UTF-8 prompt and normalize its boundaries."""
    if not resource.is_file():
        raise _prompt_error(resource_name, "A required translation prompt is missing.")
    try:
        text = resource.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise _prompt_error(resource_name, "Translation prompts must use UTF-8.") from error
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise _prompt_error(resource_name, "Translation prompts must not be empty.")
    return normalized


def _prompt_error(resource_name: str, message: str) -> TranslationConfigError:
    """Build a safe structured error without exposing filesystem paths."""
    context = ErrorContext(
        code=ErrorCode.CONFIG_INVALID,
        message=message,
        suggestion="Restore the packaged translation prompt resources.",
        details={"resource": resource_name},
    )
    return TranslationConfigError(context=context)


__all__ = ["LoadedPrompts", "PromptLoader", "available_style_names"]

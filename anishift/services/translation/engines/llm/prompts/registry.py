"""Discover built-in and user-authored LLM translation prompt assets."""

from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path
from typing import Final, Never

from natsort import os_sorted

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.translation.engines.llm.prompts.types import PromptAsset, PromptAssetKind
from anishift.services.translation.errors import TranslationConfigError

# ── Constants ────────────────────────────────────────────────────────────────

_VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"_v(\d+)$")
"""Extracts a positive version from a built-in prompt identifier."""

_CUSTOM_DIRECTORIES: Final[dict[PromptAssetKind, str]] = {
    "task": "tasks",
    "style": "styles",
    "module": "modules",
}
"""Runtime prompt directories available to non-programmer users."""


class PromptRegistry:
    """Validated catalog of built-in and runtime translation prompt assets."""

    __slots__ = ("_assets", "_custom_root")

    def __init__(self, *, custom_root: Path | None = None) -> None:
        """Load all built-in assets and optional custom ``.txt`` files."""
        self._custom_root = custom_root or Path("config/prompts")
        self._assets: dict[tuple[PromptAssetKind, str], PromptAsset] = {}
        self._load_builtins()
        self._load_custom()

    def resolve(self, kind: PromptAssetKind, asset_id: str) -> PromptAsset:
        """Return one asset or raise a structured configuration error."""
        normalized_id = asset_id.strip()
        asset = self._assets.get((kind, normalized_id))
        if asset is not None:
            return asset
        available = self.list_ids(kind)
        context = ErrorContext(
            code=ErrorCode.CONFIG_INVALID,
            message=f"Unknown {kind} prompt: {normalized_id or '<empty>'}",
            suggestion=f"Choose one of: {', '.join(available) or '<none>'}.",
            details={"kind": kind, "prompt_id": normalized_id, "available": available},
        )
        raise TranslationConfigError(context=context)

    def list_ids(self, kind: PromptAssetKind) -> list[str]:
        """Return naturally sorted identifiers for one asset category."""
        identifiers: list[str] = [asset_id for asset_kind, asset_id in self._assets if asset_kind == kind]
        return os_sorted(identifiers)

    def _load_builtins(self) -> None:
        """Load package-owned tasks, styles, modules, and contracts."""
        assets_root = files("anishift.services.translation.engines.llm.prompts").joinpath("assets")
        directories: dict[PromptAssetKind, str] = {
            "task": "tasks",
            "style": "styles",
            "module": "modules",
            "contract": "contracts",
        }
        for kind, directory in directories.items():
            prompt_directory = assets_root.joinpath(directory)
            if not prompt_directory.is_dir():
                continue
            for entry in sorted(prompt_directory.iterdir(), key=lambda item: item.name):
                if not entry.is_file() or not entry.name.endswith(".txt"):
                    continue
                asset_id = entry.name.removesuffix(".txt")
                match = _VERSION_PATTERN.search(asset_id)
                if match is None:
                    self._raise_invalid_asset(
                        source=f"builtin:{directory}/{entry.name}",
                        message="Built-in prompt ID must end with _vN",
                    )
                version = int(match.group(1))
                text = _canonical_text(entry.read_text(encoding="utf-8"))
                self._register(
                    PromptAsset(
                        asset_id=asset_id,
                        version=version,
                        kind=kind,
                        text=text,
                        source=f"builtin:{directory}/{entry.name}",
                    )
                )

    def _load_custom(self) -> None:
        """Load user-authored task, style, and module text files."""
        custom_root = self._custom_root.resolve()
        for kind, directory in _CUSTOM_DIRECTORIES.items():
            prompt_directory = self._custom_root / directory
            if not prompt_directory.is_dir():
                continue
            resolved_directory = prompt_directory.resolve()
            if not resolved_directory.is_relative_to(custom_root):
                self._raise_invalid_asset(
                    source=str(prompt_directory),
                    message="Custom prompt directory must stay inside the configured prompt root",
                )
            paths: list[Path] = [path for path in prompt_directory.iterdir() if path.suffix.lower() == ".txt"]
            for path_text in os_sorted(str(path) for path in paths):
                path = Path(path_text)
                try:
                    resolved_path = path.resolve(strict=True)
                    if not resolved_path.is_relative_to(resolved_directory):
                        self._raise_invalid_asset(
                            source=str(path),
                            message="Custom prompt path must stay inside its controlled directory",
                        )
                    text = _canonical_text(resolved_path.read_text(encoding="utf-8"))
                except UnicodeDecodeError as error:
                    self._raise_invalid_asset(
                        source=str(path),
                        message="Custom prompt must use UTF-8 encoding",
                        cause=error,
                    )
                except OSError as error:
                    self._raise_invalid_asset(
                        source=str(path),
                        message="Custom prompt could not be read",
                        cause=error,
                    )
                self._register(
                    PromptAsset(
                        asset_id=path.stem,
                        version=1,
                        kind=kind,
                        text=text,
                        source=str(path),
                    )
                )

    def _register(self, asset: PromptAsset) -> None:
        """Validate and register one prompt without silent overrides."""
        if not asset.asset_id.strip():
            self._raise_invalid_asset(source=asset.source, message="Prompt ID must not be empty")
        if not asset.text.strip():
            self._raise_invalid_asset(source=asset.source, message="Prompt file must not be empty")
        key = (asset.kind, asset.asset_id)
        if key in self._assets:
            self._raise_invalid_asset(
                source=asset.source,
                message=f"Duplicate {asset.kind} prompt ID: {asset.asset_id}",
            )
        self._assets[key] = asset

    @staticmethod
    def _raise_invalid_asset(
        *,
        source: str,
        message: str,
        cause: Exception | None = None,
    ) -> Never:
        """Raise a structured fatal error for one invalid prompt asset."""
        context = ErrorContext(
            code=ErrorCode.CONFIG_INVALID,
            message=message,
            suggestion=f"Fix or remove the prompt file: {source}",
            details={"source": source},
        )
        error = TranslationConfigError(context=context)
        if cause is None:
            raise error
        raise error from cause


def _canonical_text(text: str) -> str:
    """Normalize every supported line ending to LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


__all__ = ["PromptRegistry"]

from __future__ import annotations

from pathlib import Path
from zipfile import Path as ZipPath
from zipfile import ZipFile

import pytest

from anishift.services.translation.engines.llm.prompts import PromptLoader, available_style_names
from anishift.services.translation.errors import TranslationConfigError


def _write_required_prompts(root: Path, *, retry: str | None = None) -> None:
    (root / "styles").mkdir(parents=True)
    (root / "system.md").write_text("System", encoding="utf-8")
    (root / "translation.md").write_text("Translation", encoding="utf-8")
    (root / "retry.md").write_text(
        retry or "Error: {{validation_error}}",
        encoding="utf-8",
    )
    (root / "styles" / "neutral.md").write_text("Neutral", encoding="utf-8")


def test_packaged_prompts_load_as_polish_markdown_resources() -> None:
    prompts = PromptLoader().load("neutral")

    assert available_style_names() == ("neutral",)
    assert "polski" in prompts.system
    assert "Przetłumacz" in prompts.translation
    assert "{{validation_error}}" in prompts.retry
    assert "neutralny" in prompts.style


def test_loader_discovers_immediate_markdown_styles_in_stable_order(tmp_path: Path) -> None:
    _write_required_prompts(tmp_path)
    (tmp_path / "styles" / "zebra.md").write_text("Zebra", encoding="utf-8")
    (tmp_path / "styles" / "alpha.md").write_text("Alpha", encoding="utf-8")
    (tmp_path / "styles" / "style10.md").write_text("Ten", encoding="utf-8")
    (tmp_path / "styles" / "style2.md").write_text("Two", encoding="utf-8")
    (tmp_path / "styles" / "ignored.txt").write_text("Ignored", encoding="utf-8")
    nested = tmp_path / "styles" / "nested"
    nested.mkdir()
    (nested / "hidden.md").write_text("Hidden", encoding="utf-8")

    assert PromptLoader(tmp_path).available_styles() == (
        "alpha",
        "neutral",
        "style2",
        "style10",
        "zebra",
    )


def test_loader_rejects_style_names_colliding_after_casefold(tmp_path: Path) -> None:
    archive_path = tmp_path / "prompts.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("styles/Funny.md", "First")
        archive.writestr("styles/funny.md", "Second")

    with ZipFile(archive_path) as archive, pytest.raises(TranslationConfigError, match="must be unique"):
        PromptLoader(ZipPath(archive)).available_styles()


def test_loader_normalizes_line_endings_and_boundaries(tmp_path: Path) -> None:
    _write_required_prompts(tmp_path)
    (tmp_path / "system.md").write_bytes(b"  First\r\nSecond\r  ")

    prompts = PromptLoader(tmp_path).load("neutral")

    assert prompts.system == "First\nSecond"


def test_loader_rejects_unknown_style_without_path_lookup(tmp_path: Path) -> None:
    _write_required_prompts(tmp_path)

    with pytest.raises(TranslationConfigError, match="does not exist") as error:
        PromptLoader(tmp_path).load("../outside")

    assert error.value.context.details == {"resource": "../outside"}


@pytest.mark.parametrize("resource_name", ["system.md", "translation.md", "retry.md"])
def test_loader_rejects_missing_required_prompt(tmp_path: Path, resource_name: str) -> None:
    _write_required_prompts(tmp_path)
    (tmp_path / resource_name).unlink()

    with pytest.raises(TranslationConfigError, match="required translation prompt"):
        PromptLoader(tmp_path).load("neutral")


def test_loader_rejects_empty_style(tmp_path: Path) -> None:
    _write_required_prompts(tmp_path)
    (tmp_path / "styles" / "neutral.md").write_text(" \n", encoding="utf-8")

    with pytest.raises(TranslationConfigError, match="must not be empty"):
        PromptLoader(tmp_path).available_styles()


def test_loader_rejects_blank_style_name(tmp_path: Path) -> None:
    _write_required_prompts(tmp_path)
    (tmp_path / "styles" / " .md").write_text("Blank name", encoding="utf-8")

    with pytest.raises(TranslationConfigError, match="must not be blank"):
        PromptLoader(tmp_path).available_styles()


def test_loader_rejects_non_utf8_prompt(tmp_path: Path) -> None:
    _write_required_prompts(tmp_path)
    (tmp_path / "system.md").write_bytes(b"\xff")

    with pytest.raises(TranslationConfigError, match="UTF-8"):
        PromptLoader(tmp_path).load("neutral")


@pytest.mark.parametrize(
    "retry",
    [
        "No placeholder",
        "{{validation_error}} and {{validation_error}}",
    ],
)
def test_loader_requires_one_retry_placeholder(tmp_path: Path, retry: str) -> None:
    _write_required_prompts(tmp_path, retry=retry)

    with pytest.raises(TranslationConfigError, match="exactly one validation placeholder"):
        PromptLoader(tmp_path).load("neutral")


def test_loader_rejects_missing_or_empty_styles_directory(tmp_path: Path) -> None:
    with pytest.raises(TranslationConfigError, match="styles directory"):
        PromptLoader(tmp_path).available_styles()

    (tmp_path / "styles").mkdir()
    with pytest.raises(TranslationConfigError, match="At least one"):
        PromptLoader(tmp_path).available_styles()

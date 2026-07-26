from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from anishift.services.translation.engines.llm.prompts import (
    GlossaryEntry,
    PromptAsset,
    PromptComposer,
    PromptContext,
    PromptRegistry,
)
from anishift.services.translation.errors import TranslationConfigError


def _write_prompt(root: Path, directory: str, name: str, text: str) -> None:
    path = root / directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_registry_lists_builtin_prompts() -> None:
    registry = PromptRegistry()
    assert registry.list_ids("task") == ["anime_translation_v1"]
    assert registry.list_ids("style") == ["natural_polish_v1"]
    assert registry.list_ids("contract") == [
        "numbered_output_v1",
        "repair_numbered_output_v1",
    ]


def test_registry_discovers_custom_assets_and_ignores_other_extensions(
    tmp_path: Path,
) -> None:
    _write_prompt(tmp_path, "tasks", "custom_task.txt", "Custom task")
    _write_prompt(tmp_path, "modules", "module10.txt", "Tenth")
    _write_prompt(tmp_path, "modules", "module2.txt", "Second")
    _write_prompt(tmp_path, "styles", "ignored.md", "Ignored")
    registry = PromptRegistry(custom_root=tmp_path)
    assert registry.resolve("task", "custom_task").version == 1
    assert registry.list_ids("module") == ["module2", "module10"]
    assert "ignored" not in registry.list_ids("style")


def test_registry_normalizes_custom_line_endings_before_payload_and_hash(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tasks" / "custom_task.txt"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"First\r\nSecond\rThird")
    registry = PromptRegistry(custom_root=tmp_path)

    asset = registry.resolve("task", "custom_task")
    prompt = PromptComposer(registry, task_id="custom_task").compose(
        ["line"],
        source_lang="auto",
        target_lang="pl",
    )

    assert asset.text == "First\nSecond\nThird"
    assert "\r" not in prompt.system


def test_registry_rejects_duplicate_builtin_and_custom_id(tmp_path: Path) -> None:
    _write_prompt(
        tmp_path,
        "tasks",
        "anime_translation_v1.txt",
        "Duplicate",
    )
    with pytest.raises(TranslationConfigError, match="Duplicate task prompt ID"):
        PromptRegistry(custom_root=tmp_path)


def test_registry_rejects_empty_custom_prompt(tmp_path: Path) -> None:
    _write_prompt(tmp_path, "styles", "empty.txt", " \n")
    with pytest.raises(TranslationConfigError, match="must not be empty"):
        PromptRegistry(custom_root=tmp_path)


def test_registry_rejects_non_utf8_custom_prompt(tmp_path: Path) -> None:
    path = tmp_path / "tasks" / "broken.txt"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff")
    with pytest.raises(TranslationConfigError, match="UTF-8"):
        PromptRegistry(custom_root=tmp_path)


def test_registry_rejects_prompt_symlink_outside_custom_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("Outside prompt", encoding="utf-8")
    task_dir = tmp_path / "prompts" / "tasks"
    task_dir.mkdir(parents=True)
    link = task_dir / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this system")

    with pytest.raises(TranslationConfigError, match="controlled directory"):
        PromptRegistry(custom_root=tmp_path / "prompts")


def test_registry_reports_unknown_prompt_with_available_ids() -> None:
    registry = PromptRegistry()
    with pytest.raises(TranslationConfigError) as error:
        registry.resolve("task", "missing")
    assert error.value.context.details["prompt_id"] == "missing"
    assert error.value.context.details["available"] == ["anime_translation_v1"]


def test_composer_escapes_runtime_data_and_preserves_numbering() -> None:
    prompt = PromptComposer(PromptRegistry()).compose(
        ["<dialogue>&", "second"],
        source_lang="<auto>",
        target_lang="pl&",
    )
    assert "<source_language>&lt;auto&gt;</source_language>" in prompt.user
    assert "<target_language>pl&amp;</target_language>" in prompt.user
    assert "[1] &lt;dialogue&gt;&amp;\n[2] second" in prompt.user
    assert "<dialogue>" not in prompt.user


def test_composer_fingerprint_excludes_runtime_text() -> None:
    composer = PromptComposer(PromptRegistry())
    first = composer.compose(
        ["first"],
        source_lang="ja",
        target_lang="pl",
    )
    second = composer.compose(
        ["completely different"],
        source_lang="en",
        target_lang="de",
    )
    assert first.identity.fingerprint == second.identity.fingerprint
    assert first.system == second.system
    assert first.user != second.user


def test_repair_contract_has_distinct_identity_and_fingerprint() -> None:
    composer = PromptComposer(PromptRegistry())
    translation = composer.compose(
        ["line"],
        source_lang="auto",
        target_lang="pl",
    )
    repair = composer.compose(
        ["line"],
        source_lang="auto",
        target_lang="pl",
        repair=True,
    )
    assert translation.identity.purpose == "translation"
    assert repair.identity.purpose == "translation_repair"
    assert translation.identity.fingerprint != repair.identity.fingerprint


def test_composer_orders_modules_naturally_and_deduplicates_ids(
    tmp_path: Path,
) -> None:
    _write_prompt(tmp_path, "modules", "rule10.txt", "Rule ten")
    _write_prompt(tmp_path, "modules", "rule2.txt", "Rule two")
    prompt = PromptComposer(
        PromptRegistry(custom_root=tmp_path),
        module_ids=("rule10", "rule2", "rule2"),
    ).compose(
        ["line"],
        source_lang="auto",
        target_lang="pl",
    )
    assert prompt.system.index("Rule two") < prompt.system.index("Rule ten")


def test_composer_serializes_escaped_context_and_reports_omitted_glossary() -> None:
    glossary = tuple(GlossaryEntry(source=f"source<{index}", target=f"target&{index}") for index in range(202))
    prompt = PromptComposer(
        PromptRegistry(),
        context=PromptContext(
            title="Episode <1>",
            summary="A & B",
            glossary=glossary,
        ),
    ).compose(
        ["line"],
        source_lang="auto",
        target_lang="pl",
    )
    assert "<title>Episode &lt;1&gt;</title>" in prompt.user
    assert "<summary>A &amp; B</summary>" in prompt.user
    assert 'omitted_entries="2"' in prompt.user
    assert prompt.user.count("<entry>") == 200
    assert prompt.omitted_context_items == 2


def test_composer_rejects_oversized_dynamic_value_without_truncation() -> None:
    composer = PromptComposer(
        PromptRegistry(),
        context=PromptContext(title="x" * 2001),
    )
    with pytest.raises(TranslationConfigError, match="2000-character limit"):
        composer.compose(
            ["line"],
            source_lang="auto",
            target_lang="pl",
        )


def test_prompt_fingerprint_excludes_dynamic_context() -> None:
    first = PromptComposer(
        PromptRegistry(),
        context=PromptContext(title="First"),
    ).compose(
        ["line"],
        source_lang="auto",
        target_lang="pl",
    )
    second = PromptComposer(
        PromptRegistry(),
        context=PromptContext(title="Second"),
    ).compose(
        ["line"],
        source_lang="auto",
        target_lang="pl",
    )
    assert first.identity.fingerprint == second.identity.fingerprint
    assert first.user != second.user


def test_fingerprint_hashes_only_canonical_asset_bytes_and_separators() -> None:
    assets = [
        PromptAsset("first_v1", 1, "task", " first\r\nline ", "test"),
        PromptAsset("second_v9", 9, "style", "second\rline", "test"),
    ]
    expected = hashlib.sha256(b" first\nline \0second\nline\0").hexdigest()

    assert PromptComposer._fingerprint(assets) == expected


def test_repair_prompt_keeps_numbered_contract_and_adds_repair_contract() -> None:
    prompt = PromptComposer(PromptRegistry()).compose(
        ["line"],
        source_lang="auto",
        target_lang="pl",
        repair=True,
    )

    assert 'id="numbered_output_v1"' in prompt.system
    assert 'id="repair_numbered_output_v1"' in prompt.system

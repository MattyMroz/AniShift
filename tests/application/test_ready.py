from __future__ import annotations

import errno
from collections.abc import Callable
from pathlib import Path

import pytest
from fakes import write_image_source

from anishift.application.artifacts import SourceGroup
from anishift.application.control import (
    AudiobookRecipe,
    NarrationTimeline,
    RecipePreferences,
    TextResultFormat,
    TranslateRecipe,
)
from anishift.application.discovery import discover_groups
from anishift.application.ready import ReadyMove, ReadyStore
from anishift.application.workflows import WorkflowTarget
from anishift.errors import ExecutionError


def _group(root: Path) -> SourceGroup:
    (root / "Episode.mkv").write_bytes(b"video bytes")
    (root / "Episode.pl.srt").write_text("Polish subtitles", encoding="utf-8")
    return discover_groups(root).groups[0]


def test_ready_preserves_file_identity_and_renames_the_whole_colliding_group(tmp_path: Path) -> None:
    group: SourceGroup = _group(tmp_path)
    identities: dict[str, int] = {path.name: path.stat().st_ino for path in tmp_path.iterdir()}
    ready: Path = tmp_path / "ready"
    ready.mkdir()
    (ready / "Episode.mkv").write_bytes(b"another episode")
    store: ReadyStore = ReadyStore(tmp_path / ".state/relocations", tmp_path)
    move: ReadyMove | None = store.prepare(group, ())
    assert move is not None
    store.execute(move)
    assert (ready / "Episode.mkv").read_bytes() == b"another episode"
    assert (ready / "Episode [2].mkv").stat().st_ino == identities["Episode.mkv"]
    assert (ready / "Episode [2].pl.srt").stat().st_ino == identities["Episode.pl.srt"]
    assert not (tmp_path / "Episode.mkv").exists()
    assert store.pending() == (move,)
    store.acknowledge(move)
    assert store.pending() == ()
    moved: SourceGroup = next(
        item for item in discover_groups(tmp_path).groups if item.group_id == move.destination_group_id
    )
    assert store.prepare(moved, ()) is None


def test_a_relocation_journal_still_knows_the_origin_of_its_set_after_a_restart(tmp_path: Path) -> None:
    audiobook: Path = tmp_path / "audiobook"
    audiobook.mkdir()
    (audiobook / "Book.txt").write_text("Zażółć gęślą jaźń.", encoding="utf-8")
    product: Path = audiobook / "Book.m4a"
    product.write_bytes(b"recording")
    group: SourceGroup = discover_groups(tmp_path).groups[0]
    store: ReadyStore = ReadyStore(tmp_path / ".state/relocations", tmp_path)
    prepared: ReadyMove | None = store.prepare(group, (product,))
    assert prepared is not None

    restarted: ReadyMove = ReadyStore(tmp_path / ".state/relocations", tmp_path).pending()[0]

    assert restarted == prepared
    assert restarted.target is WorkflowTarget.AUDIOBOOK
    assert restarted.source_directory == "audiobook"
    assert restarted.source_stem == "Book"
    assert restarted.product_sources == ("audiobook/Book.m4a",)
    assert restarted.destination_stem == "Book"


def test_a_relocation_journal_keeps_the_recipe_its_order_was_accepted_with(tmp_path: Path) -> None:
    audiobook: Path = tmp_path / "audiobook"
    audiobook.mkdir()
    (audiobook / "Book.txt").write_text("Zażółć gęślą jaźń.", encoding="utf-8")
    product: Path = audiobook / "Book.m4a"
    product.write_bytes(b"recording")
    group: SourceGroup = discover_groups(tmp_path).groups[0]
    accepted: RecipePreferences = RecipePreferences(
        translate=TranslateRecipe(text_result=TextResultFormat.TEXT),
        audiobook=AudiobookRecipe(timeline=NarrationTimeline.SOURCE_TIMES),
    )
    store: ReadyStore = ReadyStore(tmp_path / ".state/relocations", tmp_path)
    prepared: ReadyMove | None = store.prepare(group, (product,), accepted)
    assert prepared is not None

    restarted: ReadyMove = ReadyStore(tmp_path / ".state/relocations", tmp_path).pending()[0]

    assert restarted.recipe == accepted
    assert restarted.recipe.audiobook.timeline is NarrationTimeline.SOURCE_TIMES
    assert restarted.recipe.translate.text_result is TextResultFormat.TEXT


def test_ready_recovers_after_linking_before_removing_the_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    group: SourceGroup = _group(tmp_path)
    store: ReadyStore = ReadyStore(tmp_path / ".state/relocations", tmp_path)
    move: ReadyMove | None = store.prepare(group, ())
    assert move is not None
    unlink: Callable[..., None] = Path.unlink

    def interrupted(path: Path, *, missing_ok: bool = False) -> None:
        if path == tmp_path / "Episode.mkv":
            raise OSError(errno.EIO, "Interrupted after linking")
        unlink(path, missing_ok=missing_ok)

    with monkeypatch.context() as failure:
        failure.setattr(Path, "unlink", interrupted)
        with pytest.raises(OSError, match="Interrupted after linking"):
            store.execute(move)
    assert (tmp_path / "Episode.mkv").samefile(tmp_path / "ready/Episode.mkv")
    restored: ReadyStore = ReadyStore(tmp_path / ".state/relocations", tmp_path)
    restored.execute(restored.pending()[0])
    assert not (tmp_path / "Episode.mkv").exists()
    assert (tmp_path / "ready/Episode.mkv").read_bytes() == b"video bytes"
    assert (tmp_path / "ready/Episode.pl.srt").read_text(encoding="utf-8") == "Polish subtitles"


def test_ready_rejects_a_destination_created_after_preparation_without_overwriting(tmp_path: Path) -> None:
    group: SourceGroup = _group(tmp_path)
    store: ReadyStore = ReadyStore(tmp_path / ".state/relocations", tmp_path)
    move: ReadyMove | None = store.prepare(group, ())
    assert move is not None
    destination: Path = tmp_path / "ready/Episode.mkv"
    destination.write_bytes(b"someone else's file")
    with pytest.raises(ExecutionError, match="changed"):
        store.execute(move)
    assert destination.read_bytes() == b"someone else's file"
    assert (tmp_path / "Episode.mkv").read_bytes() == b"video bytes"


def _cover_group(root: Path) -> SourceGroup:
    cover: Path = root / "cover"
    write_image_source(cover / "Book.png", width=48, height=32)
    (cover / "Book.txt").write_text("Zażółć gęślą jaźń", encoding="utf-8")
    (cover / "Book.cover.mp4").write_bytes(b"still film")
    return discover_groups(root).groups[0]


def test_a_finished_cover_moves_its_picture_and_film_instead_of_being_called_unrecognized(tmp_path: Path) -> None:
    group: SourceGroup = _cover_group(tmp_path)
    store: ReadyStore = ReadyStore(tmp_path / ".state/relocations", tmp_path)

    move: ReadyMove | None = store.prepare(group, (tmp_path / "cover" / "Book.cover.mp4",))

    assert move is not None
    assert move.destination_stem == "Book"
    store.execute(move)
    assert sorted(path.name for path in (tmp_path / "ready").iterdir()) == [
        "Book.cover.mp4",
        "Book.png",
        "Book.txt",
    ]
    assert list((tmp_path / "cover").iterdir()) == []


def test_a_second_cover_of_the_same_name_reserves_one_core_for_its_whole_set(tmp_path: Path) -> None:
    group: SourceGroup = _cover_group(tmp_path)
    ready: Path = tmp_path / "ready"
    ready.mkdir()
    write_image_source(ready / "Book.png", width=10, height=10)
    store: ReadyStore = ReadyStore(tmp_path / ".state/relocations", tmp_path)

    move: ReadyMove | None = store.prepare(group, (tmp_path / "cover" / "Book.cover.mp4",))

    assert move is not None
    assert move.destination_stem == "Book [2]"
    store.execute(move)
    assert sorted(path.name for path in ready.iterdir()) == [
        "Book [2].cover.mp4",
        "Book [2].png",
        "Book [2].txt",
        "Book.png",
    ]


def test_a_file_a_transfer_still_holds_keeps_its_place_until_a_later_stage_moves_it(tmp_path: Path) -> None:
    group: SourceGroup = _group(tmp_path)
    store: ReadyStore = ReadyStore(tmp_path / ".state/relocations", tmp_path)
    move: ReadyMove | None = store.prepare(group, ())
    assert move is not None

    staged: ReadyMove = store.defer(move, ("Episode.mkv", "Nothing.mkv"))
    store.execute(staged)

    assert staged.deferred == ("Episode.mkv",)
    assert tuple(item.source for item in staged.moved) == ("Episode.pl.srt",)
    assert (tmp_path / "Episode.mkv").read_bytes() == b"video bytes"
    assert (tmp_path / "ready" / "Episode.pl.srt").exists()
    assert store.pending() == (staged,)

    released: ReadyMove = store.defer(staged, ())
    store.execute(released)

    assert released.deferred == ()
    assert not (tmp_path / "Episode.mkv").exists()
    assert (tmp_path / "ready" / "Episode.mkv").read_bytes() == b"video bytes"
    store.acknowledge(released)
    assert store.pending() == ()

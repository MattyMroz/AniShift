from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from anishift.application.control_views import DeletionPreview, LibraryFile, LibraryFileIdentity, LibrarySet
from anishift.application.workflows import WorkflowTarget
from anishift.cli.interactive import state as module
from anishift.cli.interactive import state_library
from anishift.cli.interactive.state import StateController
from anishift.cli.interactive.text_input import TextInput
from anishift.cli.resident import ResidentSession
from anishift.platform.local_control import ControlError


@pytest.mark.parametrize("key", ["enter", "text:f"])
@pytest.mark.parametrize("missing", [False, True])
def test_details_open_exact_file_but_not_heading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str, missing: bool
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    identity: LibraryFileIdentity = LibraryFileIdentity("ready/01.txt", 1, 2, 3, 4)
    second: LibraryFileIdentity = replace(identity, path="ready/02.txt", inode=5)
    details: LibrarySet = LibrarySet(
        "set",
        "group",
        "name",
        WorkflowTarget.TRANSLATE,
        identity.path,
        (
            LibraryFile(identity.path, "product", "TXT", None if missing else identity),
            LibraryFile(second.path, "source", "TXT", second),
        ),
        False,
        problem="library_result_missing",
        provisional_timing=True,
    )
    calls: list[tuple[Path, bool]] = []

    def resolve(set_id: str, expected: LibraryFileIdentity) -> Path:
        assert set_id == "set"
        assert expected == identity
        return tmp_path / expected.path

    client: ResidentSession = cast("ResidentSession", SimpleNamespace(library_file=resolve, close=lambda: None))
    parent: ResidentSession = cast("ResidentSession", SimpleNamespace(new_session=lambda: client))
    controller: StateController = StateController(parent, lambda: None)
    monkeypatch.setattr(controller, "_work", lambda action, **kwargs: controller._perform(action, ""))
    monkeypatch.setattr(module, "_open_path", lambda path, *, show_folder: calls.append((path, show_folder)))
    controller._tab = module._Tab.FILES
    controller._details = details
    try:
        controller.handle_key(key)
        assert calls == []
        controller._selected = len(state_library.detail_entries(details)) - len(details.files)
        controller.handle_key(key)
        assert calls == ([] if missing else [(tmp_path / identity.path, key == "text:f")])
    finally:
        controller.close()
        controller._thread.join(5)


def test_library_refusal_survives_snapshot_but_not_target_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    client: ResidentSession = cast(
        "ResidentSession", SimpleNamespace(command=lambda kind: {"subscriptions": []}, close=lambda: None)
    )
    parent: ResidentSession = cast("ResidentSession", SimpleNamespace(new_session=lambda: client))
    controller: StateController = StateController(parent, lambda: None)
    controller._tab = module._Tab.FILES
    controller._snapshot = {"library": [{"set_id": "one"}, {"set_id": "two"}]}

    def refuse(session: ResidentSession) -> None:
        del session
        raise ControlError("held", reason="library_source_held", answered=True)

    try:
        controller._perform(refuse)
        controller._receive(
            client, {"event": "state_changed", "payload": {**controller._snapshot, "auto_enabled": False}}
        )
        assert "Źródło czeka na zwolnienie przez torrent" in controller.render(120, 35).plain
        controller.handle_key("down")
        assert controller._notice == ""
        controller._perform(refuse, generation=controller._view_generation - 1)
        assert controller._notice == ""
    finally:
        controller.close()
        controller._thread.join(5)


@pytest.mark.parametrize("details", [False, True])
def test_library_ctrl_z_uses_owner_latest_not_selected_set(monkeypatch: pytest.MonkeyPatch, details: bool) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    calls: list[str] = []
    client: ResidentSession = cast(
        "ResidentSession", SimpleNamespace(undo_deletion=lambda: calls.append("latest"), close=lambda: None)
    )
    controller: StateController = StateController(
        cast("ResidentSession", SimpleNamespace(new_session=lambda: client)), lambda: None
    )
    monkeypatch.setattr(controller, "_work", lambda action, **kwargs: controller._perform(action, ""))
    controller._tab = module._Tab.FILES
    controller._connected = True
    if details:
        controller._details = LibrarySet("unrelated", "group", "name", None, None, (), False)
    try:
        controller.handle_key("undo")
        assert calls == ["latest"]
        assert controller._notice == ""
        monkeypatch.setattr(controller, "_work", StateController._work.__get__(controller))
        controller._busy = True
        controller.handle_key("undo")
        assert calls == ["latest"]
        assert controller._notice == ""
    finally:
        controller.close()
        controller._thread.join(5)


def test_action_context_capture_holds_lock_and_failure_releases_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    controller: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    controller._busy = True

    def context() -> tuple[str, str] | None:
        assert controller._lock.locked()
        raise RuntimeError("context failure")

    monkeypatch.setattr(controller, "_library_context", context)
    try:
        with pytest.raises(RuntimeError, match="context failure"):
            controller._perform(lambda session: None)
        assert not controller._busy
    finally:
        controller.close()
        controller._thread.join(5)


def test_undo_refusal_is_visible_without_synthetic_operation_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)

    def refuse() -> None:
        raise ControlError("Nothing to undo", reason="restore_nothing", answered=True)

    client: ResidentSession = cast("ResidentSession", SimpleNamespace(undo_deletion=refuse, close=lambda: None))
    controller: StateController = StateController(
        cast("ResidentSession", SimpleNamespace(new_session=lambda: client)), lambda: None
    )
    monkeypatch.setattr(controller, "_work", lambda action, **kwargs: controller._perform(action, ""))
    controller._tab = module._Tab.FILES
    try:
        controller.handle_key("undo")
        frame: str = controller.render(120, 35).plain
        assert "Brak usuniętego zestawu do przywrócenia" in frame
        assert state_library.library_rows(controller._snapshot) == []
    finally:
        controller.close()
        controller._thread.join(5)


class _DeletingOwner:
    def __init__(self, *, refuse: bool = False) -> None:
        self.refuse: bool = refuse
        self.release: threading.Event = threading.Event()
        self.deleted: list[str] = []
        self.undone: list[str] = []

    def new_session(self) -> _DeletingOwner:
        return self

    def close(self) -> None:
        return

    def command(self, kind: str, payload: Mapping[str, object] | None = None) -> Mapping[str, object]:
        return {"subscriptions": []}

    def preview_deletion(self, set_id: str) -> DeletionPreview:
        assert self.release.wait(5)
        return DeletionPreview(f"preview-{set_id}", "instance", set_id, set_id, ())

    def delete_set(self, preview: DeletionPreview) -> str:
        if self.refuse:
            raise ControlError("held", reason="library_source_held", answered=True)
        self.deleted.append(preview.set_id)
        return f"recycle-{preview.set_id}"

    def undo_deletion(self) -> str:
        self.undone.append("latest")
        return "restore"


_SETS: tuple[dict[str, str], ...] = tuple({"set_id": name, "name": name} for name in ("Alpha", "Beta", "Gamma"))


def _deleting_panel(monkeypatch: pytest.MonkeyPatch, owner: _DeletingOwner) -> StateController:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    panel: StateController = StateController(cast("ResidentSession", owner), lambda: None)
    panel._tab = module._Tab.FILES
    panel._connected = True
    panel._snapshot = {"library": list(_SETS)}
    return panel


def _shown(panel: StateController) -> list[str]:
    return [state_library.library_row_id(item) for item in panel._library()]


def _until(condition: Callable[[], bool]) -> None:
    deadline: float = time.monotonic() + 5
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert condition()


def _stop(owner: _DeletingOwner, panel: StateController) -> None:
    owner.release.set()
    panel.close()
    panel._thread.join(5)
    for thread in threading.enumerate():
        if thread.name == "anishift-library-delete":
            thread.join(5)


@pytest.mark.parametrize("key", ["delete", "text:x"])
def test_library_delete_hides_the_row_before_the_owner_answers_without_a_question(
    monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    owner: _DeletingOwner = _DeletingOwner()
    panel: StateController = _deleting_panel(monkeypatch, owner)
    try:
        panel.handle_key(key)
        assert _shown(panel) == ["Beta", "Gamma"]
        assert panel._selected == 0
        assert "Alpha" not in panel.render(80, 24).plain
        assert owner.deleted == []
        owner.release.set()
        _until(lambda: "Usunięto · Ctrl+Z cofnij" in panel.render(80, 24).plain)
        assert owner.deleted == ["Alpha"]
        assert _shown(panel) == ["Beta", "Gamma"]
        panel.handle_key("down")
        assert "Usunięto" not in panel.render(80, 24).plain
    finally:
        _stop(owner, panel)


def test_library_quick_deletes_remove_two_different_sets(monkeypatch: pytest.MonkeyPatch) -> None:
    owner: _DeletingOwner = _DeletingOwner()
    panel: StateController = _deleting_panel(monkeypatch, owner)
    try:
        panel.handle_key("delete")
        panel.handle_key("delete")
        assert _shown(panel) == ["Gamma"]
        owner.release.set()
        _until(lambda: sorted(owner.deleted) == ["Alpha", "Beta"])
    finally:
        _stop(owner, panel)


def test_library_refused_delete_returns_the_row_with_the_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    owner: _DeletingOwner = _DeletingOwner(refuse=True)
    panel: StateController = _deleting_panel(monkeypatch, owner)
    panel._selected = 1
    try:
        panel.handle_key("delete")
        assert _shown(panel) == ["Alpha", "Gamma"]
        owner.release.set()
        _until(lambda: "Źródło czeka na zwolnienie przez torrent" in panel.render(80, 24).plain)
        assert _shown(panel) == ["Alpha", "Beta", "Gamma"]
        assert owner.deleted == []
    finally:
        _stop(owner, panel)


def test_library_accepted_delete_stays_hidden_until_reported_and_undo_restores_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner: _DeletingOwner = _DeletingOwner()
    panel: StateController = _deleting_panel(monkeypatch, owner)
    session: ResidentSession = cast("ResidentSession", owner)
    deletion: dict[str, object] = {"operation_id": "recycle-Alpha", "set_id": "Alpha", "total": 1}
    try:
        panel.handle_key("delete")
        owner.release.set()
        _until(lambda: owner.deleted == ["Alpha"] and panel._hidden == {"Alpha": "recycle-Alpha"})
        panel._receive(session, {"event": "state_changed", "payload": {"library": list(_SETS)}})
        assert _shown(panel) == ["Beta", "Gamma"]
        active: dict[str, object] = {"library": list(_SETS), "deletions": [{**deletion, "active": True}]}
        panel._receive(session, {"event": "state_changed", "payload": active})
        assert panel._hidden == {}
        assert _shown(panel) == ["Beta", "Gamma"]
        done: dict[str, object] = {"library": list(_SETS[1:]), "deletions": [{**deletion, "recycled": 1}]}
        panel._receive(session, {"event": "state_changed", "payload": done})
        assert _shown(panel) == ["Beta", "Gamma"]
        panel.handle_key("undo")
        _until(lambda: owner.undone == ["latest"])
        restored: dict[str, object] = {
            "library": list(_SETS),
            "deletions": [{**deletion, "recycled": 1, "restored": True}],
        }
        panel._receive(session, {"event": "state_changed", "payload": restored})
        assert _shown(panel) == ["Alpha", "Beta", "Gamma"]
    finally:
        _stop(owner, panel)


def test_delete_in_a_panel_text_field_removes_a_character_not_a_set(monkeypatch: pytest.MonkeyPatch) -> None:
    owner: _DeletingOwner = _DeletingOwner()
    panel: StateController = _deleting_panel(monkeypatch, owner)
    panel._history_input = TextInput("ab")
    try:
        panel.handle_key("home")
        panel.handle_key("delete")
        assert panel._history_input.text == "b"
        assert panel._hidden == {}
        assert _shown(panel) == ["Alpha", "Beta", "Gamma"]
    finally:
        _stop(owner, panel)

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from anishift.application.control import DeletionRestore, PendingDeletion, RestoreOutcome
from anishift.application.control_views import LibraryFile, LibraryFileIdentity, LibrarySet
from anishift.application.workflows import WorkflowTarget
from anishift.cli.interactive import state as module
from anishift.cli.interactive.state import StateController
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
        controller._selected = len(module._library_detail_entries(details)) - len(details.files)
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
    if details:
        controller._details = LibrarySet("unrelated", "group", "name", None, None, (), False)
    try:
        controller.handle_key("undo")
        assert calls == ["latest"]
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


def test_operation_details_expose_recorded_relative_staging_for_unsettled_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    controller: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    controller._tab = module._Tab.FILES
    controller._operation_details = PendingDeletion(
        "delete",
        "set",
        "now",
        (("ready/01.txt", 1, 2),),
        identities=(("ready/01.txt", 3, 4),),
        restore=DeletionRestore(
            "restore", (RestoreOutcome("ready/01.txt", "temp/.restore-one/0", "uncertain", "restore_incomplete", True),)
        ),
    )
    try:
        frame: str = controller.render(120, 35).plain
        assert "temp/.restore-one/0" in frame
        assert "staging do sprawdzenia" in frame
    finally:
        controller.close()
        controller._thread.join(5)

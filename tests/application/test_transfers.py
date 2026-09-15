from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from loguru import logger as loguru_logger

from anishift.application.acquisition import AcquisitionService
from anishift.application.control import AcquisitionConfirmation, AcquisitionState
from anishift.application.intents import RequestOrigin
from anishift.application.transfers import TransferInspector
from anishift.errors import ErrorCode, ErrorContext
from anishift.services.torrents import TorrentFile, TorrentInfo
from anishift.services.torrents.errors import TorrentClientError


class _Acquisition(AcquisitionService):
    def __init__(self, root: Path) -> None:
        self.info: TorrentInfo | None = TorrentInfo("Episode", "abc", 1.0, "stoppedUP", str(root), 0, 4)
        self.entries: tuple[TorrentFile, ...] = (TorrentFile(0, "Episode.mkv", 4, 1.0, 1, True),)
        self.info_calls: int = 0
        self.file_calls: int = 0
        self.resumed: list[frozenset[str]] = []
        self.raises: Exception | None = None

    def resume_unconfirmed(self, hashes: frozenset[str]) -> None:
        self.resumed.append(hashes)

    def transfers(self) -> tuple[TorrentInfo, ...]:
        self.info_calls += 1
        return (self.info,) if self.info is not None else ()

    def transfer_files(self, info_hash: str) -> tuple[TorrentFile, ...]:
        assert info_hash == "abc"
        self.file_calls += 1
        if self.raises is not None:
            raise self.raises
        return self.entries


def _confirmation() -> AcquisitionConfirmation:
    return AcquisitionConfirmation(
        "op-1", "abc", "", (), AcquisitionState.ACCEPTED, RequestOrigin.USER, "sub-1", "9", "old"
    )


@pytest.mark.parametrize("interruption", ["pausedDL", "checkingDL", "resume"])
def test_stall_time_excludes_pauses_checks_and_sleep(tmp_path: Path, interruption: str) -> None:
    now: list[float] = [0.0]
    acquisition: _Acquisition = _Acquisition(tmp_path)
    assert acquisition.info is not None
    acquisition.info = replace(acquisition.info, progress=0.5, completed=2, state="downloading", amount_left=2)
    inspector: TransferInspector = TransferInspector(acquisition, tmp_path, clock=lambda: now[0])
    inspector.inspect((_confirmation(),), stall_after_s=60)
    now[0] = 30
    inspector.inspect((_confirmation(),), stall_after_s=60)
    if interruption == "resume":
        inspector.reset_clock()
    else:
        acquisition.info = replace(acquisition.info, state=interruption)
        inspector.inspect((_confirmation(),), stall_after_s=60)
    now[0] += 3600
    acquisition.info = replace(acquisition.info, state="downloading")
    inspector.inspect((_confirmation(),), stall_after_s=60)
    assert not inspector.stalled
    now[0] += 30
    inspector.inspect((_confirmation(),), stall_after_s=60)
    assert inspector.stalled == frozenset({"abc"})
    acquisition.info = replace(acquisition.info, progress=0.75, completed=3)
    inspector.inspect((_confirmation(),), stall_after_s=60)
    assert not inspector.stalled


@pytest.mark.parametrize("state", ["uploading", "stalledUP", "queuedUP", "pausedUP", "stoppedUP", "forcedUP"])
def test_completed_selected_files_are_ready_without_unselected_pack_files(tmp_path: Path, state: str) -> None:
    (tmp_path / "Episode.mkv").write_bytes(b"data")
    acquisition: _Acquisition = _Acquisition(tmp_path)
    assert acquisition.info is not None
    acquisition.info = replace(acquisition.info, state=state)
    acquisition.entries += (TorrentFile(1, "Skipped.mkv", 100, 0.0, 0, False),)

    result: AcquisitionConfirmation = TransferInspector(acquisition, tmp_path).inspect((_confirmation(),))[0]

    assert result.state is AcquisitionState.COMPLETE
    assert result.directory == ""
    assert result.required_files == ("Episode.mkv",)
    assert result.operation_id == "op-1"
    assert result.updated_at != "old"


@pytest.mark.parametrize(
    "state",
    ["downloading", "metaDL", "forcedMetaDL", "checkingDL", "checkingUP", "checkingResumeData", "moving", "error"],
)
def test_client_work_blocks_full_sized_files(tmp_path: Path, state: str) -> None:
    (tmp_path / "Episode.mkv").write_bytes(b"data")
    acquisition: _Acquisition = _Acquisition(tmp_path)
    assert acquisition.info is not None
    acquisition.info = replace(acquisition.info, state=state)

    result: AcquisitionConfirmation = TransferInspector(acquisition, tmp_path).inspect((_confirmation(),))[0]

    assert result.state is AcquisitionState.ACCEPTED
    assert result.required_files == ("Episode.mkv",)


@pytest.mark.parametrize("remaining", [None, 1])
def test_unknown_or_remaining_bytes_prevent_completion(tmp_path: Path, remaining: int | None) -> None:
    (tmp_path / "Episode.mkv").write_bytes(b"data")
    acquisition: _Acquisition = _Acquisition(tmp_path)
    assert acquisition.info is not None
    acquisition.info = replace(acquisition.info, amount_left=remaining)

    result: AcquisitionConfirmation = TransferInspector(acquisition, tmp_path).inspect((_confirmation(),))[0]

    assert result.state is AcquisitionState.ACCEPTED


@pytest.mark.parametrize("problem", ["preallocated", "incomplete_file", "short_file", "missing_file", "unselected"])
def test_client_and_local_file_must_both_prove_completion(tmp_path: Path, problem: str) -> None:
    acquisition: _Acquisition = _Acquisition(tmp_path)
    if problem != "missing_file":
        (tmp_path / "Episode.mkv").write_bytes(b"bad" if problem == "short_file" else b"data")
    if problem == "preallocated":
        acquisition.entries = (replace(acquisition.entries[0], progress=0.4, is_seed=False),)
    elif problem == "incomplete_file":
        acquisition.entries = (replace(acquisition.entries[0], is_seed=False),)
    elif problem == "unselected":
        acquisition.entries = (replace(acquisition.entries[0], priority=0),)

    result: AcquisitionConfirmation = TransferInspector(acquisition, tmp_path).inspect((_confirmation(),))[0]

    assert result.state is AcquisitionState.ACCEPTED


@pytest.mark.parametrize("name", ["../Episode.mkv", "C:\\Episode.mkv", "/Episode.mkv", "folder/../../Episode.mkv"])
def test_external_file_paths_are_never_admitted(tmp_path: Path, name: str) -> None:
    acquisition: _Acquisition = _Acquisition(tmp_path)
    acquisition.entries = (replace(acquisition.entries[0], name=name),)

    result: AcquisitionConfirmation = TransferInspector(acquisition, tmp_path).inspect((_confirmation(),))[0]

    assert result.state is AcquisitionState.UNCERTAIN
    assert not result.required_files


def test_external_save_directory_is_not_treated_as_a_library_transfer(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(tmp_path.parent)

    result: AcquisitionConfirmation = TransferInspector(acquisition, tmp_path).inspect((_confirmation(),))[0]

    assert result.state is AcquisitionState.UNCERTAIN
    assert acquisition.file_calls == 0


def test_file_metadata_is_reused_until_the_transfer_reaches_completion(tmp_path: Path) -> None:
    (tmp_path / "Episode.mkv").write_bytes(b"data")
    acquisition: _Acquisition = _Acquisition(tmp_path)
    inspector: TransferInspector = TransferInspector(acquisition, tmp_path)
    for progress in (0.1, 0.4, 0.9):
        assert acquisition.info is not None
        acquisition.info = replace(acquisition.info, progress=progress, amount_left=1, state="downloading")
        assert inspector.inspect((_confirmation(),))[0].state is AcquisitionState.ACCEPTED
    assert acquisition.info_calls == 3
    assert acquisition.file_calls == 1
    assert acquisition.info is not None
    acquisition.info = replace(acquisition.info, progress=1.0, amount_left=0, state="stoppedUP")

    assert inspector.inspect((_confirmation(),))[0].state is AcquisitionState.COMPLETE
    assert acquisition.info_calls == 4
    assert acquisition.file_calls == 2


def test_a_missing_transfer_keeps_its_identity_as_uncertain(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(tmp_path)
    acquisition.info = None

    result: AcquisitionConfirmation = TransferInspector(acquisition, tmp_path).inspect((_confirmation(),))[0]

    assert result.state is AcquisitionState.UNCERTAIN
    assert result.operation_id == "op-1"
    assert acquisition.file_calls == 0


def test_an_empty_transfer_set_makes_no_client_request(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(tmp_path)

    assert TransferInspector(acquisition, tmp_path).inspect(()) == ()
    assert acquisition.info_calls == 0
    assert acquisition.file_calls == 0
    assert acquisition.resumed == []


def test_unconfirmed_transfers_ask_for_their_client_before_it_is_read(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(tmp_path)

    TransferInspector(acquisition, tmp_path).inspect((_confirmation(),))

    assert acquisition.resumed == [frozenset({"abc"})]
    assert acquisition.info_calls == 1


def test_a_failed_confirmation_alone_still_names_no_client_to_start(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(tmp_path)
    failed: AcquisitionConfirmation = replace(_confirmation(), state=AcquisitionState.FAILED)

    results: tuple[AcquisitionConfirmation, ...] = TransferInspector(acquisition, tmp_path).inspect((failed,))

    assert results == (failed,)
    assert acquisition.resumed == [frozenset({"abc"})]
    assert acquisition.file_calls == 0


def test_repeated_inspection_failures_log_one_line_until_the_cause_changes(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(tmp_path)
    acquisition.raises = _unavailable()
    inspector: TransferInspector = TransferInspector(acquisition, tmp_path)
    captured: list[str] = []
    handler_id: int = loguru_logger.add(captured.append, format="{message} {extra}", level="DEBUG")
    try:
        for _ in range(4):
            inspector.inspect((_confirmation(),))
        acquisition.raises = OSError("the file vanished")
        inspector.inspect((_confirmation(),))
        acquisition.raises = None
        inspector.inspect((_confirmation(),))
        inspector.inspect((_confirmation(),))
    finally:
        loguru_logger.remove(handler_id)

    failures: list[str] = [line for line in captured if "Transfer inspection failed" in line]
    recoveries: list[str] = [line for line in captured if "Transfer inspection recovered" in line]
    assert len(failures) == 2
    assert len(recoveries) == 1
    assert f"TorrentClientError:{ErrorCode.TORRENT_CLIENT_UNAVAILABLE.value}" in failures[0]
    assert "The Web UI is closed" in failures[0]
    assert "OSError" in failures[1]
    assert "the file vanished" in failures[1]
    assert all(str(tmp_path) not in line for line in failures)


def _unavailable() -> TorrentClientError:
    return TorrentClientError(
        context=ErrorContext(code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE, message="The Web UI is closed")
    )

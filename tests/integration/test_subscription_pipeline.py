from __future__ import annotations

import pytest
from harness import Composed, composed_fixture  # noqa: F401

from anishift.application.acquisition import INCOMPLETE_EXTENSION_PREFERENCE, ReleaseChoice
from anishift.errors import ErrorCode
from anishift.services.torrents import TorrentClientError


def _first_season_choice(composed: Composed) -> ReleaseChoice:
    found = composed.resolve("solo leveling 1", "Ore dake Level Up na Ken")
    (subsplease,) = found.groups_of("SubsPlease")
    return subsplease.choices[0]


def test_the_client_reports_its_version_and_takes_the_incomplete_extension_preference(composed: Composed) -> None:
    status = composed.acquisition.setup_client()

    assert status.reachable
    assert status.version == "5.2.3"
    assert status.incomplete_extension
    assert composed.client.settings[INCOMPLETE_EXTENSION_PREFERENCE] is True


def test_a_refused_torrent_reports_the_client_refusal_code(composed: Composed) -> None:
    choice = _first_season_choice(composed)
    composed.client.refuse = True

    with pytest.raises(TorrentClientError) as refusal:
        composed.acquisition.download((choice,))

    assert refusal.value.context.code is ErrorCode.TORRENT_CLIENT_REFUSED

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from itertools import permutations
from typing import Final

import pytest

from anishift.application.episode_releases import (
    NAME_PRIORITY,
    EpisodeRelease,
    ListedFile,
    ReleaseFile,
    TsukiHimeFiles,
    info_hash_hex,
    is_pack,
    merge_releases,
)
from anishift.application.episode_selection import StreamCandidate
from anishift.application.release_quality import LanguageSource, PolishClass, ReleaseTraits, release_traits
from anishift.services.torrents.names import parse_release_name

_HASH: Final[str] = "3753beaf00112233445566778899aabbccddeeff"
_STREAM: Final[StreamCandidate] = StreamCandidate(
    info_hash=_HASH,
    name="Torrentio",
    file_index=None,
    file_name=None,
    release="Example - 01",
    path=None,
    seeders=None,
    size_text=None,
    provider=None,
    tags=(),
    trackers=(),
)


def _pack_name(name: str) -> bool:
    return parse_release_name(name).is_pack


def _merge(
    streams: Sequence[StreamCandidate], listings: Mapping[str, TsukiHimeFiles] | None = None
) -> tuple[EpisodeRelease, ...]:
    return merge_releases(streams, listings or {}, pack_name=_pack_name)


def _traits(release: EpisodeRelease, file: str | None) -> ReleaseTraits:
    return release_traits(
        release.names,
        release.tags,
        release.declarations,
        file=file,
        pack=is_pack(release, pack_name=_pack_name),
        donghua=False,
        seeders=release.seeders,
    )


@pytest.mark.unit
def test_info_hash_hex_keeps_lowercase_hex() -> None:
    assert info_hash_hex("3753beaf00112233445566778899aabbccddeeff") == "3753beaf00112233445566778899aabbccddeeff"


@pytest.mark.unit
def test_info_hash_hex_lowercases_uppercase_hex() -> None:
    assert info_hash_hex("3753BEAF00112233445566778899AABBCCDDEEFF") == "3753beaf00112233445566778899aabbccddeeff"


@pytest.mark.unit
@pytest.mark.parametrize("value", ["G5J35LYACERDGRCVMZ3YRGNKXPGN33X7", "g5j35lyacerdgrcvmz3yrgnkxpgn33x7"])
def test_info_hash_hex_converts_base32(value: str) -> None:
    assert info_hash_hex(value) == "3753beaf00112233445566778899aabbccddeeff"


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [
        "",
        "3753beaf00112233445566778899aabbccddeef",
        "3753beaf00112233445566778899aabbccddeeff0",
        "3753beaf00112233445566778899aabbccddeefg",
        " 3753beaf00112233445566778899aabbccddeeff",
        "G5J35LYACERDGRCVMZ3YRGNKXPGN33X1",
        "G5J35LYACERDGRCVMZ3YRGNKXPGN33X",
        "magnet:?xt=urn:btih:3753beaf00112233445566778899aabbccddeeff",
    ],
)
def test_info_hash_hex_rejects_other_text(value: str) -> None:
    assert info_hash_hex(value) is None


@pytest.mark.unit
def test_merge_releases_same_hash_one_row() -> None:
    streams: tuple[StreamCandidate, ...] = (
        _STREAM,
        replace(_STREAM, source="nyaa", info_hash=_HASH.upper()),
        replace(_STREAM, source="knaben", info_hash="G5J35LYACERDGRCVMZ3YRGNKXPGN33X7"),
        replace(_STREAM, info_hash="invalid"),
    )
    releases: tuple[EpisodeRelease, ...] = _merge(streams)
    assert len(releases) == 1
    assert releases[0].info_hash == _HASH
    assert releases[0].sources == frozenset({"torrentio", "nyaa", "knaben"})


@pytest.mark.unit
def test_merge_releases_preserves_distinct_hashes_in_first_seen_order() -> None:
    assert [item.info_hash for item in _merge((_STREAM, replace(_STREAM, info_hash="a" * 40), _STREAM))] == [
        _HASH,
        "a" * 40,
    ]


@pytest.mark.unit
@pytest.mark.parametrize("start", range(5))
def test_merge_releases_name_priority(start: int) -> None:
    streams: tuple[StreamCandidate, ...] = tuple(
        replace(_STREAM, source=source, release=f"{source} title") for source in NAME_PRIORITY[start:]
    )
    for ordered in permutations(streams):
        release: EpisodeRelease = _merge(ordered)[0]
        assert release.name == f"{NAME_PRIORITY[start]} title"
        assert release.names == tuple(f"{source} title" for source in NAME_PRIORITY[start:])


@pytest.mark.unit
def test_merge_releases_empty_preferred_name_uses_next_available() -> None:
    release: EpisodeRelease = _merge((replace(_STREAM, source="tsukihime", release=""), _STREAM))[0]
    assert release.name == _STREAM.release


@pytest.mark.unit
@pytest.mark.parametrize(("seeders", "expected"), [((None, None), None), ((None, 0), 0), ((5, 30, 10), 30)])
def test_merge_releases_seeders_max_or_unknown(seeders: tuple[int | None, ...], expected: int | None) -> None:
    release: EpisodeRelease = _merge(tuple(replace(_STREAM, seeders=value) for value in seeders))[0]
    assert release.seeders == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "filename"),
    [
        ("Original directory/second line.mkv", "different filename.mkv"),
        (None, "filename only.mkv"),
        ("directory/path only.mkv", None),
    ],
)
def test_torrentio_file_keeps_filename_and_path(path: str | None, filename: str | None) -> None:
    release: EpisodeRelease = _merge((replace(_STREAM, path=path, file_name=filename, file_index=7),))[0]
    file: ReleaseFile = release.files[0]
    assert file.path == path
    assert file.filename == filename
    assert file.file_index == 7
    assert file.identity_candidate(release.name) == {"release": _STREAM.release, "path": path, "filename": filename}


@pytest.mark.unit
def test_merge_releases_torrentio_file_is_not_listing() -> None:
    release: EpisodeRelease = _merge((replace(_STREAM, file_name="Example - 01.mkv", file_count=1),))[0]
    assert not release.listing
    assert not release.files[0].from_listing


@pytest.mark.unit
def test_merge_releases_does_not_invent_file_from_release_or_index() -> None:
    release: EpisodeRelease = _merge((replace(_STREAM, release="Example - 01.mkv", file_index=0),))[0]
    assert release.files == ()
    assert release.file_hint == 0
    assert not release.listing


@pytest.mark.unit
def test_merge_releases_file_from_listing_wins() -> None:
    stream: StreamCandidate = replace(_STREAM, path="Wrong folder/01.mkv", file_name="01.mkv", file_index=9)
    listing: TsukiHimeFiles = TsukiHimeFiles((ListedFile("Real folder/01.mkv", 100),))
    release: EpisodeRelease = _merge((stream,), {_HASH.upper(): listing})[0]
    assert release.listing
    assert release.files == (ReleaseFile("Real folder/01.mkv", "01.mkv", 100, from_listing=True, file_index=9),)
    assert release.files[0].identity_candidate(release.name) == {
        "release": _STREAM.release,
        "path": "Real folder/01.mkv",
        "filename": "01.mkv",
    }


@pytest.mark.unit
def test_merge_releases_torrentio_name_joined_once() -> None:
    stream: StreamCandidate = replace(_STREAM, path="old/01.mkv", file_name="01.mkv", file_index=0)
    listing: TsukiHimeFiles = TsukiHimeFiles((ListedFile("new/01.mkv", 100), ListedFile("new/02.mkv", 200)))
    release: EpisodeRelease = _merge((stream, stream), {_HASH: listing})[0]
    assert len(release.files) == 2
    assert release.files[0].file_index == 0
    assert release.files[1].filename is None


@pytest.mark.unit
def test_merge_releases_torrentio_path_basename_joins_when_filename_absent() -> None:
    listing: TsukiHimeFiles = TsukiHimeFiles((ListedFile("new/01.mkv", 100),))
    release: EpisodeRelease = _merge((replace(_STREAM, path="old\\01.mkv", file_index=3),), {_HASH: listing})[0]
    assert release.files == (ReleaseFile("new/01.mkv", None, 100, from_listing=True, file_index=3),)


@pytest.mark.unit
def test_merge_releases_torrentio_name_ambiguous_kept_alone() -> None:
    stream: StreamCandidate = replace(_STREAM, path="hint/01.mkv", file_name="01.mkv", file_index=1)
    listing: TsukiHimeFiles = TsukiHimeFiles((ListedFile("a/01.mkv", 100), ListedFile("b/01.mkv", 200)))
    release: EpisodeRelease = _merge((stream,), {_HASH: listing})[0]
    assert len(release.files) == 3
    assert release.files[-1] == ReleaseFile("hint/01.mkv", "01.mkv", None, from_listing=False, file_index=1)
    assert all(file.file_index is None for file in release.files[:2])


@pytest.mark.unit
def test_merge_releases_unmatched_filename_does_not_fall_back_to_matching_path() -> None:
    stream: StreamCandidate = replace(_STREAM, path="hint/01.mkv", file_name="02.mkv", file_index=0)
    listing: TsukiHimeFiles = TsukiHimeFiles((ListedFile("real/01.mkv", 100),))
    release: EpisodeRelease = _merge((stream,), {_HASH: listing})[0]
    assert len(release.files) == 2
    assert release.files[0].file_index is None
    assert release.files[1].identity_candidate(release.name) == {
        "release": _STREAM.release,
        "path": "hint/01.mkv",
        "filename": "02.mkv",
    }


@pytest.mark.unit
def test_torrentio_flag_follows_matched_listing_file() -> None:
    stream: StreamCandidate = replace(
        _STREAM, path="hint/01 [MultiSub].mkv", file_name="01 [MultiSub].mkv", tags=("🇵🇱",)
    )
    listing: TsukiHimeFiles = TsukiHimeFiles(
        (ListedFile("real/01 [MultiSub].mkv", 100), ListedFile("real/02.mkv", 200))
    )
    release: EpisodeRelease = _merge((stream,), {_HASH: listing})[0]
    assert _traits(release, "real/01 [MultiSub].mkv").polish is PolishClass.BARE
    assert _traits(release, "real/02.mkv").polish is PolishClass.NONE
    assert any(
        item.source is LanguageSource.TORRENTIO_FLAG and item.file == "real/01 [MultiSub].mkv"
        for item in release.declarations
    )


@pytest.mark.unit
def test_torrentio_flag_without_known_file_is_not_release_declaration() -> None:
    release: EpisodeRelease = _merge((replace(_STREAM, tags=("🇵🇱",)),))[0]
    assert _traits(release, None).polish is PolishClass.NONE


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subtitles", "expected"),
    [(("en", "pl-PL"), PolishClass.POLISH), (("en",), PolishClass.NONE), ((), PolishClass.BARE)],
)
def test_tsukihime_release_subtitles_decide_before_torrentio_file_flag(
    subtitles: tuple[str, ...], expected: PolishClass
) -> None:
    flagged: StreamCandidate = replace(_STREAM, file_name="Example - 01 [1080p].mkv", tags=("🇵🇱",))
    listed: StreamCandidate = replace(_STREAM, source="tsukihime", subtitle_languages=subtitles, torrent_id=1)
    release: EpisodeRelease = _merge((flagged, listed))[0]
    assert _traits(release, release.files[0].filename).polish is expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "english"),
    [
        ("[Group] Example - 01 (1080p) [Multi-Subs]", True),
        ("[Group] Example - 01 (1080p) [MultiSub]", True),
        ("[Group] Example - 01 1080p WEB-DL MULTi AAC2.0", False),
    ],
)
def test_nyaa_multi_marker_leaves_english_to_release_name(name: str, english: bool) -> None:
    language: str | None = parse_release_name(name).subtitle_language
    stream: StreamCandidate = replace(
        _STREAM, source="nyaa", release=name, subtitle_languages=(language,) if language else ()
    )
    release: EpisodeRelease = _merge((stream,))[0]
    assert language == "multi"
    assert _traits(release, None).english_subtitles is english


@pytest.mark.unit
def test_torrentio_flag_and_filename_only_use_filename_scope_without_changing_identity() -> None:
    stream: StreamCandidate = replace(_STREAM, file_name="01 [MultiSub].mkv", tags=("🇵🇱",))
    release: EpisodeRelease = _merge((stream,))[0]
    assert release.files[0].path is None
    assert _traits(release, release.files[0].filename).polish is PolishClass.BARE


@pytest.mark.unit
def test_torrentio_flag_ambiguous_name_stays_on_unmatched_file() -> None:
    stream: StreamCandidate = replace(_STREAM, path="hint/01.mkv", file_name="01.mkv", tags=("🇵🇱",))
    listing: TsukiHimeFiles = TsukiHimeFiles((ListedFile("a/01.mkv", 100), ListedFile("b/01.mkv", 200)))
    release: EpisodeRelease = _merge((stream,), {_HASH: listing})[0]
    assert _traits(release, "hint/01.mkv").polish is PolishClass.BARE
    assert _traits(release, "a/01.mkv").polish is PolishClass.NONE
    assert _traits(release, "b/01.mkv").polish is PolishClass.NONE


@pytest.mark.unit
def test_torrentio_different_filename_and_path_keep_language_of_selected_filename() -> None:
    stream: StreamCandidate = replace(_STREAM, path="hint/01.mkv", file_name="01 [PL sub].mkv")
    release: EpisodeRelease = _merge((stream,))[0]
    assert _traits(release, "hint/01.mkv").polish is PolishClass.POLISH


@pytest.mark.unit
def test_torrentio_multiple_known_files_are_preserved_without_claiming_a_listing() -> None:
    streams: tuple[StreamCandidate, ...] = (
        replace(_STREAM, path="01.mkv", file_name="01.mkv", tags=("🇵🇱",), file_index=0),
        replace(_STREAM, path="02.mkv", file_name="02.mkv", file_index=1),
    )
    release: EpisodeRelease = _merge(streams)[0]
    assert len(release.files) == 2
    assert not release.listing
    assert _traits(release, "01.mkv").polish is PolishClass.BARE
    assert _traits(release, "02.mkv").polish is PolishClass.NONE


@pytest.mark.unit
def test_merge_releases_keeps_file_language_lists_separate_and_normalized() -> None:
    listing: TsukiHimeFiles = TsukiHimeFiles(
        (
            ListedFile("01.mkv", 100, ("pl-PL",), ("ja-JP",)),
            ListedFile("02.mkv", 200, ("en-US",), ("ko-KR",)),
        )
    )
    release: EpisodeRelease = _merge((_STREAM,), {_HASH: listing})[0]
    assert _traits(release, "01.mkv").polish is PolishClass.POLISH
    assert _traits(release, "02.mkv").polish is PolishClass.NONE
    assert _traits(release, "02.mkv").english_subtitles
    assert release.declarations[0].subtitles == frozenset({"pl"})
    assert release.declarations[0].audio == frozenset({"ja"})


@pytest.mark.unit
def test_merge_releases_scopes_tsukihime_and_nekobt_to_release() -> None:
    streams: tuple[StreamCandidate, ...] = (
        replace(_STREAM, source="tsukihime", subtitle_languages=("en-US",), audio_languages=("ja-JP",), torrent_id=42),
        replace(_STREAM, source="nekobt", language_tags=("A=en;F=pl-PL;S=en", "HS")),
    )
    release: EpisodeRelease = _merge(streams)[0]
    assert release.torrent_id == 42
    assert all(item.file is None for item in release.declarations)
    assert _traits(release, None).polish is PolishClass.NONE
    assert _traits(release, None).hardsub
    assert not _traits(release, None).dub_only
    assert _traits(_merge(streams[1:])[0], None).polish is PolishClass.POLISH


@pytest.mark.unit
def test_merge_releases_keeps_all_exclusion_evidence_and_deduplicates_trackers() -> None:
    release: EpisodeRelease = _merge(
        (
            replace(_STREAM, source="tsukihime", trackers=("udp://one",)),
            replace(_STREAM, source="nyaa", release="Example - 01 [RAW]", trackers=("udp://one", "udp://two")),
            replace(_STREAM, source="nekobt", tags=("HS",)),
        )
    )[0]
    assert release.name == _STREAM.release
    assert _traits(release, None).raw
    assert _traits(release, None).hardsub
    assert release.trackers == ("udp://one", "udp://two")


@pytest.mark.unit
@pytest.mark.parametrize("name", ["Example E01-E04", "Example S01E01-E04", "Example [Batch]", "Example - 01-12"])
def test_is_pack_any_source_name(name: str) -> None:
    release: EpisodeRelease = _merge((replace(_STREAM, source="tsukihime"), replace(_STREAM, release=name)))[0]
    assert is_pack(release, pack_name=_pack_name)


@pytest.mark.unit
@pytest.mark.parametrize("name", ["Example [Batch]", "Example - 01"])
def test_is_pack_listing_wins(name: str) -> None:
    listing: TsukiHimeFiles = TsukiHimeFiles((ListedFile("01.mkv", 100),))
    release: EpisodeRelease = _merge((replace(_STREAM, release=name),), {_HASH: listing})[0]
    assert not is_pack(release, pack_name=_pack_name)
    listing = TsukiHimeFiles((*listing.files, ListedFile("02.MP4", 200)))
    assert is_pack(_merge((replace(_STREAM, release=name),), {_HASH: listing})[0], pack_name=_pack_name)


@pytest.mark.unit
def test_is_pack_companion_files_do_not_count() -> None:
    listing: TsukiHimeFiles = TsukiHimeFiles(
        tuple(ListedFile(path, 100) for path in ("01.mkv", "01.mka", "01.ass", "font.ttf"))
    )
    release: EpisodeRelease = _merge((_STREAM,), {_HASH: listing})[0]
    assert not is_pack(release, pack_name=_pack_name)


_EXTRA_CASES: list[tuple[str, str, bool]] = [
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - 02.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - Kanojo.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - 02 - The Opening.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - 02 [ED123456].mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - ED.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - PV.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - PV1.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - PV 01.mkv", True),
    ("Neko to Ryuu [03].mkv", "Neko to Ryuu [04] The Menu.mkv", True),
    ("Neko to Ryuu [03].mkv", "Neko to Ryuu [04] Creditless OP.mkv", True),
    ("Neko to Ryuu Menu.mkv", "Neko to Ryuu Menu - 02 - Story.mkv", True),
    ("Neko to Ryuu Preview.mkv", "Neko to Ryuu Preview - 02 - Story.mkv", True),
    ("Menu2.mkv", "Menu2 - 02 - Story.mkv", True),
    ("NCOP - 01.mkv", "NCOP - 02 - Story.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Featurettes/Neko to Ryuu - 02.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - 02-other.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu \u2161 - NCOP.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Extras/Neko - 02.mkv", True),
    ("Neko to Ryuu - 03.mkv", "Extras/Neko to Ryuu - S01E04/Story.mkv", True),
    ("Neko to Ryuu - 03.mkv", "Extras/02/Neko to Ryuu.mkv", True),
    ("Neko to Ryuu - 03.mkv", "Other/Season 1/02/Story.mkv", True),
    ("Neko to Ryuu - 03.mkv", "Neko to Ryuu/02/Story-other.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - NCOP\u00b2.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - NCOP.mkv", False),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - NCOP 01.mkv", False),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - NCED2 [ABCDEF12].mkv", False),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - Creditless OP.mkv", False),
    ("Neko to Ryuu - 01.mkv", "Extras/Making Of.mkv", False),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - PV-trailer.mp4", False),
]

_EXTRA_IDS: list[str] = [
    "two-episodes",
    "unrecognized-video",
    "marker-word-in-episode-title",
    "marker-like-checksum",
    "bare-ed",
    "pv",
    "attached-pv-number",
    "separated-pv-number",
    "bracketed-episode-number",
    "bracketed-number-beside-marker",
    "menu-series-without-number",
    "preview-series-without-number",
    "attached-number-series",
    "ncop-series",
    "plex-folder-with-number",
    "plex-suffix-with-number",
    "roman-numeral",
    "extras-folder-with-number",
    "numbered-folder-under-extras",
    "numbered-folder-in-extras",
    "numbered-folders-under-other",
    "numbered-folder-above-plex-suffix",
    "superscript-number",
    "ncop",
    "separated-ncop-number",
    "nced-with-checksum",
    "creditless",
    "extras-folder",
    "plex-suffix",
]


@pytest.mark.unit
@pytest.mark.parametrize(("first", "second", "pack"), _EXTRA_CASES, ids=_EXTRA_IDS)
def test_is_pack_counts_only_episode_videos(first: str, second: str, *, pack: bool) -> None:
    listing: TsukiHimeFiles = TsukiHimeFiles((ListedFile(first, 100), ListedFile(second, 50)))
    release: EpisodeRelease = _merge((_STREAM,), {_HASH: listing})[0]
    assert is_pack(release, pack_name=_pack_name) is pack


@pytest.mark.unit
@pytest.mark.parametrize("series", ["Ed", "Menu", "The Menu", "CM", "PV", "Preview", "Teaser", "Yokoku"])
def test_is_pack_series_named_like_a_marker(series: str) -> None:
    listing: TsukiHimeFiles = TsukiHimeFiles(
        (ListedFile(f"{series} - 01.mkv", 100), ListedFile(f"{series} - 02 - Story.mkv", 50))
    )
    release: EpisodeRelease = _merge((_STREAM,), {_HASH: listing})[0]
    assert is_pack(release, pack_name=_pack_name)


@pytest.mark.unit
def test_is_pack_counts_extras_when_no_episode_video_remains() -> None:
    listing: TsukiHimeFiles = TsukiHimeFiles(
        (ListedFile("Example - NCOP.mkv", 100), ListedFile("Example - NCED.mkv", 50))
    )
    release: EpisodeRelease = _merge((_STREAM,), {_HASH: listing})[0]
    assert is_pack(release, pack_name=_pack_name)


@pytest.mark.unit
def test_is_pack_unmatched_torrentio_hint_does_not_add_inventory_video() -> None:
    listing: TsukiHimeFiles = TsukiHimeFiles((ListedFile("01.mkv", 100),))
    release: EpisodeRelease = _merge((replace(_STREAM, file_name="02.mkv"),), {_HASH: listing})[0]
    assert not is_pack(release, pack_name=_pack_name)


@pytest.mark.unit
def test_is_pack_empty_listing_falls_back_to_names() -> None:
    release: EpisodeRelease = _merge((replace(_STREAM, release="Example [Batch]"),), {_HASH: TsukiHimeFiles(())})[0]
    assert not release.listing
    assert is_pack(release, pack_name=_pack_name)

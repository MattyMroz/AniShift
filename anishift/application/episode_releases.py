"""Merge episode release metadata and scoped file declarations without I/O."""

from __future__ import annotations

import base64
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, Literal

from anishift.application.episode_identity import episode_video_count
from anishift.application.release_quality import (
    LanguageDeclaration,
    LanguageSource,
    language_code,
    name_declaration,
    tag_declaration,
)

if TYPE_CHECKING:
    from anishift.application.episode_selection import StreamCandidate

__all__ = [
    "NAME_PRIORITY",
    "EpisodeRelease",
    "ListedFile",
    "ReleaseFile",
    "SourceName",
    "TsukiHimeFiles",
    "info_hash_hex",
    "is_pack",
    "merge_releases",
]

# ── Constants ─────────────────────────────────────────────────────────────────

type SourceName = Literal["tsukihime", "nyaa", "nekobt", "knaben", "torrentio"]
"""Supported sources contributing metadata to one release."""

NAME_PRIORITY: Final[tuple[SourceName, ...]] = ("tsukihime", "nyaa", "nekobt", "knaben", "torrentio")
"""Source order for the first available release name."""

_POLISH_FLAG: Final[str] = "\U0001f1f5\U0001f1f1"
"""Torrentio Polish language flag scoped to its known file."""

_HEX_HASH: Final[re.Pattern[str]] = re.compile(r"[0-9a-fA-F]{40}")
"""BTIH v1 hash written as forty hexadecimal digits."""

_BASE32_HASH: Final[re.Pattern[str]] = re.compile(r"[A-Za-z2-7]{32}")
"""BTIH v1 hash written as thirty-two base32 characters."""


@dataclass(frozen=True, slots=True)
class ListedFile:
    """One original torrent path and its TsukiHime language lists."""

    path: str
    size: int | None
    subtitle_languages: tuple[str, ...] = ()
    audio_languages: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TsukiHimeFiles:
    """Complete torrent inventory validated by the source adapter before merging."""

    files: tuple[ListedFile, ...]


@dataclass(frozen=True, slots=True)
class ReleaseFile:
    """Original file identity with optional Torrentio filename and index hints."""

    path: str | None
    filename: str | None
    size: int | None
    from_listing: bool
    file_index: int | None

    @property
    def scope(self) -> str | None:
        """Return the original path, else the filename, that file-scoped declarations refer to."""
        return self.path or self.filename

    @property
    def names(self) -> tuple[str, ...]:
        """Return the distinct base names of the filename and the path that describe this file."""
        return tuple(
            dict.fromkeys(value.replace("\\", "/").rsplit("/", 1)[-1] for value in (self.filename, self.path) if value)
        )

    def identity_candidate(self, release: str) -> dict[str, object]:
        """Project source identity fields without substituting a filename for a path."""
        return {"release": release, "path": self.path, "filename": self.filename}


@dataclass(frozen=True, slots=True)
class EpisodeRelease:
    """One normalized BTIH with all source evidence and independently scoped file languages."""

    info_hash: str
    name: str
    names: tuple[str, ...]
    tags: tuple[str, ...]
    sources: frozenset[SourceName]
    seeders: int | None
    size_text: str | None
    files: tuple[ReleaseFile, ...]
    listing: bool
    file_hint: int | None
    declarations: tuple[LanguageDeclaration, ...]
    torrent_id: int | None
    trackers: tuple[str, ...]
    pack: bool


def info_hash_hex(value: str) -> str | None:
    """Return the lowercase hexadecimal BTIH of a hex or base32 hash, or ``None`` for any other text."""
    if _HEX_HASH.fullmatch(value) is not None:
        return value.lower()
    if _BASE32_HASH.fullmatch(value) is None:
        return None
    return base64.b32decode(value.upper()).hex()


def is_pack(release: EpisodeRelease, *, pack_name: Callable[[str], bool]) -> bool:
    """Prefer the complete inventory's episode video count to pack markers from any source name."""
    if release.listing:
        paths: list[str] = list(dict.fromkeys(file.path for file in release.files if file.from_listing and file.path))
        return episode_video_count(paths) > 1
    return any(pack_name(name) for name in release.names)


def merge_releases(
    streams: Sequence[StreamCandidate],
    listings: Mapping[str, TsukiHimeFiles],
    *,
    pack_name: Callable[[str], bool],
) -> tuple[EpisodeRelease, ...]:
    """Merge valid BTIH rows and mark packs without inferring files or inventory completeness from release names."""
    grouped: dict[str, list[StreamCandidate]] = {}
    for stream in streams:
        key: str | None = info_hash_hex(stream.info_hash)
        if key is not None:
            grouped.setdefault(key, []).append(stream)
    normalized_listings: dict[str, TsukiHimeFiles] = {
        key: listing for value, listing in listings.items() if (key := info_hash_hex(value)) is not None
    }
    merged: tuple[EpisodeRelease, ...] = tuple(
        _merge_release(key, rows, normalized_listings.get(key)) for key, rows in grouped.items()
    )
    return tuple(replace(release, pack=is_pack(release, pack_name=pack_name)) for release in merged)


def _source_name(source: str) -> SourceName:
    if source not in NAME_PRIORITY:
        msg: str = "Unsupported release metadata source"
        raise ValueError(msg)
    return source


def _merge_release(key: str, streams: Sequence[StreamCandidate], listing: TsukiHimeFiles | None) -> EpisodeRelease:
    ordered: list[StreamCandidate] = sorted(
        streams, key=lambda stream: NAME_PRIORITY.index(_source_name(stream.source))
    )
    names: tuple[str, ...] = tuple(dict.fromkeys(stream.release for stream in ordered if stream.release))
    files: list[ReleaseFile] = []
    declarations: list[LanguageDeclaration] = []
    if listing is not None:
        for item in listing.files:
            files.append(ReleaseFile(item.path, None, item.size, from_listing=True, file_index=None))
            declarations.append(_listed_declaration(item))
    for stream in ordered:
        selected: ReleaseFile | None = _attach_torrentio_file(files, stream) if stream.source == "torrentio" else None
        declarations.extend(_stream_declarations(stream, selected))
    return EpisodeRelease(
        info_hash=key,
        name=names[0] if names else "",
        names=names,
        tags=tuple(dict.fromkeys(tag for stream in ordered for tag in (*stream.tags, *stream.language_tags))),
        sources=frozenset(_source_name(stream.source) for stream in ordered),
        seeders=max((stream.seeders for stream in ordered if stream.seeders is not None), default=None),
        size_text=next((stream.size_text for stream in ordered if stream.size_text), None),
        files=tuple(files),
        listing=bool(listing and listing.files),
        file_hint=next(
            (stream.file_index for stream in ordered if stream.source == "torrentio" and stream.file_index is not None),
            None,
        ),
        declarations=tuple(dict.fromkeys(declarations)),
        torrent_id=next(
            (stream.torrent_id for stream in ordered if stream.source == "tsukihime" and stream.torrent_id is not None),
            None,
        ),
        trackers=tuple(dict.fromkeys(tracker for stream in ordered for tracker in stream.trackers)),
        pack=False,
    )


def _listed_declaration(file: ListedFile) -> LanguageDeclaration:
    return LanguageDeclaration(
        LanguageSource.TSUKIHIME,
        file.path,
        frozenset(language_code(code) for code in file.subtitle_languages),
        frozenset(language_code(code) for code in file.audio_languages),
        complete_audio=True,
    )


def _attach_torrentio_file(files: list[ReleaseFile], stream: StreamCandidate) -> ReleaseFile | None:
    if not stream.file_name and not stream.path:
        return None
    filename: str = stream.file_name or (stream.path or "").replace("\\", "/").rsplit("/", 1)[-1]
    matches: list[int] = [
        index
        for index, file in enumerate(files)
        if file.from_listing and file.path and file.path.replace("\\", "/").rsplit("/", 1)[-1] == filename
    ]
    if len(matches) == 1:
        index: int = matches[0]
        files[index] = replace(
            files[index],
            filename=stream.file_name or files[index].filename,
            file_index=stream.file_index if stream.file_index is not None else files[index].file_index,
        )
        return files[index]
    selected: ReleaseFile = ReleaseFile(
        stream.path, stream.file_name, None, from_listing=False, file_index=stream.file_index
    )
    if selected not in files:
        files.append(selected)
    return selected


def _stream_declarations(stream: StreamCandidate, file: ReleaseFile | None) -> tuple[LanguageDeclaration, ...]:
    if stream.source == "tsukihime":
        return (
            LanguageDeclaration(
                LanguageSource.TSUKIHIME,
                None,
                frozenset(language_code(code) for code in stream.subtitle_languages),
                frozenset(language_code(code) for code in stream.audio_languages),
                complete_audio=True,
            ),
        )
    if stream.source == "nekobt":
        return (tag_declaration((*stream.tags, *stream.language_tags)),)
    if stream.source == "nyaa" and stream.subtitle_languages:
        return (
            LanguageDeclaration(
                LanguageSource.RELEASE_NAME,
                None,
                frozenset(language_code(code) for code in stream.subtitle_languages),
                None,
                complete_audio=False,
                partial_subtitles=True,
            ),
        )
    if file is None:
        return ()
    scope: str | None = file.scope
    filename: str = stream.file_name or (stream.path or "").replace("\\", "/").rsplit("/", 1)[-1]
    declarations: list[LanguageDeclaration] = [name_declaration(filename, LanguageSource.FILE_NAME, scope)]
    if _POLISH_FLAG in stream.tags:
        declarations.append(
            LanguageDeclaration(
                LanguageSource.TORRENTIO_FLAG,
                scope,
                None,
                None,
                complete_audio=False,
                polish_bare=True,
            )
        )
    return tuple(declarations)

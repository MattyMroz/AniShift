"""Load and validate the external-resource manifest (``bin_hashes.json``).

The manifest is the single source of truth for what the resource installer
downloads: per resource a ``kind``, a ``source`` (how to fetch it), its SHA256
and size, and the members to extract. ``source`` is a tagged union keyed by
``source.type``; today only ``url`` exists, and a future AI model adds a new
source type plus a fetcher — not a new manifest shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, cast

from anishift.errors import ErrorCode, ErrorContext, FatalError

__all__ = [
    "ArchiveFormat",
    "ManifestError",
    "Member",
    "Resource",
    "ResourceKind",
    "Source",
    "SourceType",
    "UrlSource",
    "load_manifest",
    "manifest_path",
]

ResourceKind = Literal["binary"]
"""Kinds of downloadable resources (a future AI model adds a literal here)."""

SourceType = Literal["url"]
"""How a resource is fetched (a future ``hf``/``licensed`` adds a literal here)."""

ArchiveFormat = Literal["zip"]
"""Supported archive container formats."""

# ── Constants ────────────────────────────────────────────────────────────────

_RESOURCE_KINDS: Final[frozenset[str]] = frozenset(("binary",))
"""Accepted values of the manifest ``kind`` field."""

_ARCHIVE_FORMATS: Final[frozenset[str]] = frozenset(("zip",))
"""Accepted values of the manifest ``archive`` field."""

_SHA256_HEX_LENGTH: Final[int] = 64
"""Length of a SHA256 digest in hexadecimal characters."""


class ManifestError(FatalError):
    """Raised when the resource manifest is missing or malformed."""


@dataclass(frozen=True, slots=True)
class UrlSource:
    """A resource fetched from a direct download URL.

    Attributes:
        url: Download URL of the archive.
    """

    type: Literal["url"]
    url: str


Source = UrlSource
"""Tagged union of resource sources (only :class:`UrlSource` exists today)."""


@dataclass(frozen=True, slots=True)
class Member:
    """One file to extract from a resource archive.

    Attributes:
        archive_path: Path of the member inside the archive.
        dest: Destination relative to the resource's install root (no ``..``).
    """

    archive_path: str
    dest: str


@dataclass(frozen=True, slots=True)
class Resource:
    """One downloadable resource: a source plus the members to install.

    Attributes:
        name: Resource name (also the manifest key), e.g. ``"ffmpeg"``.
        kind: Resource kind; decides the install root (binary -> ``external/bin/``).
        source: How to fetch the archive.
        sha256: Expected SHA256 of the downloaded archive (lowercase hex).
        size_bytes: Expected archive size in bytes.
        archive: Container format of the download.
        members: Files to extract from the archive.
    """

    name: str
    kind: ResourceKind
    source: Source
    sha256: str
    size_bytes: int
    archive: ArchiveFormat
    members: tuple[Member, ...]


def _repo_root() -> Path:
    """Return the repository root (ancestor holding ``pyproject.toml``)."""
    return Path(__file__).resolve().parents[2]


def manifest_path() -> Path:
    """Return ``<repo>/external/bin_hashes.json``."""
    return _repo_root() / "external" / "bin_hashes.json"


def _fail(message: str) -> ManifestError:
    """Build a :class:`ManifestError` with a consistent context."""
    return ManifestError(
        context=ErrorContext(
            code=ErrorCode.CONFIG_INVALID,
            message=f"resource manifest: {message}",
            suggestion="external/bin_hashes.json is broken — fix it or report a bug",
        ),
    )


def _parse_source(name: str, raw: Any) -> Source:
    """Validate and build a :class:`Source` from raw JSON."""
    if not isinstance(raw, dict):
        msg = f"resource {name} needs a source object"
        raise _fail(msg)
    source_type = raw.get("type")
    if source_type != "url":
        msg = f"resource {name} has unsupported source type: {source_type!r}"
        raise _fail(msg)
    url = raw.get("url")
    if not isinstance(url, str) or not url:
        msg = f"resource {name} source needs a non-empty url"
        raise _fail(msg)
    return UrlSource(type="url", url=url)


def _parse_member(raw: Any) -> Member:
    """Validate and build a :class:`Member` from raw JSON."""
    if not isinstance(raw, dict):
        msg = "member must be an object"
        raise _fail(msg)
    archive_path = raw.get("archive_path")
    dest = raw.get("dest")
    if not isinstance(archive_path, str) or not isinstance(dest, str):
        msg = "member needs string archive_path and dest"
        raise _fail(msg)
    if not archive_path or not dest:
        msg = "member archive_path and dest must be non-empty"
        raise _fail(msg)
    if Path(dest).is_absolute() or ".." in Path(dest).parts:
        msg = f"member dest escapes the install root: {dest}"
        raise _fail(msg)
    return Member(archive_path=archive_path, dest=dest)


def _parse_resource(name: str, raw: Any) -> Resource:
    """Validate and build a :class:`Resource` from raw JSON."""
    if not isinstance(raw, dict):
        msg = f"resource {name} must be an object"
        raise _fail(msg)
    kind = raw.get("kind")
    sha256 = raw.get("sha256")
    size_bytes = raw.get("size_bytes")
    archive = raw.get("archive")
    members = raw.get("members")
    if kind not in _RESOURCE_KINDS:
        msg = f"resource {name} has unsupported kind: {kind!r}"
        raise _fail(msg)
    if not isinstance(sha256, str) or len(sha256) != _SHA256_HEX_LENGTH:
        msg = f"resource {name} needs a {_SHA256_HEX_LENGTH}-char sha256"
        raise _fail(msg)
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes <= 0:
        msg = f"resource {name} needs a positive integer size_bytes"
        raise _fail(msg)
    if archive not in _ARCHIVE_FORMATS:
        msg = f"resource {name} has unsupported archive: {archive!r}"
        raise _fail(msg)
    if not isinstance(members, list) or not members:
        msg = f"resource {name} needs a non-empty members list"
        raise _fail(msg)
    return Resource(
        name=name,
        kind=cast(ResourceKind, kind),
        source=_parse_source(name, raw.get("source")),
        sha256=sha256.lower(),
        size_bytes=size_bytes,
        archive=cast(ArchiveFormat, archive),
        members=tuple(_parse_member(member) for member in members),
    )


def load_manifest(path: Path | None = None) -> tuple[Resource, ...]:
    """Load and validate the resource manifest.

    Args:
        path: Manifest file (defaults to :func:`manifest_path`).

    Returns:
        Parsed resources in manifest order.

    Raises:
        ManifestError: When the file is missing, unparseable, or malformed.
    """
    target = path if path is not None else manifest_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"cannot read {target}: {exc}"
        raise _fail(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"not valid JSON: {exc}"
        raise _fail(msg) from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("resources"), dict):
        msg = "top-level 'resources' object is required"
        raise _fail(msg)
    return tuple(_parse_resource(name, body) for name, body in raw["resources"].items())

# Etap 2.5 — Binary Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Binaries install themselves — the shell auto-downloads mkvtoolnix + ffmpeg on first launch when they are missing, verifies SHA256, extracts into `external/bin/`, with a live progress bar. The user runs nothing by hand; `anishift setup` exists only as an explicit recovery command. After this, `doctor` goes green and every later stage (3, 6, 7) has real binaries.

**Architecture:** A JSON manifest (`external/bin_hashes.json`) is the single source of truth: per-package URL, archive SHA256, size, and which members to extract to which destination. `installer.py` downloads each missing package to a temp dir (streaming httpx with a `ProgressBarManager` bar copied from the MangaShift pattern), verifies the archive hash, extracts named members (path-traversal guarded), and atomically moves them into `external/bin/<tool>/`. `manifest.py` loads/validates the JSON into typed dataclasses. `ensure_binaries()` is called at shell start: if anything is missing it runs the install with progress; on no-network it warns and lets the user in anyway (doctor stays red). `main.py` exposes `anishift setup` for manual re-runs.

**Tech Stack:** Python 3.14, `py7zr` (7z extraction — new dep), stdlib `zipfile` (zip extraction), `httpx` (streaming download — already a dep), `utils/rich_console` `ProgressBarManager` (progress — already present), pytest.

**Progress-bar pattern (from MangaShift, do not reinvent):** `utils/rich_console/progress` already ships `ProgressBarManager` (context manager, `advance(n)` method). Wire it to the httpx stream: `total = int(resp.headers.get("content-length", 0))`; `for chunk in resp.iter_bytes(chunk): pb.advance(len(chunk))`. Flags copied 1:1 from MangaShift `engine.py`: `bar="blocks", show_download=True, show_speed=True, show_percentage=True, show_elapsed=True, show_eta=False, show_spinner=False`. When `content-length` is absent, pass `total=None` (indeterminate).

## Global Constraints

- Code and comments in English; docstrings Google-style, simple, only where the standard requires them (public modules/classes/functions + every `Final`). No comment noise.
- `from __future__ import annotations` as line 1 of every module; lowercase generics; `X | None`; `Literal` for closed sets.
- `Final` constants grouped in a `# ── Constants ──` section, docstring under each.
- Guard clauses, early return, max 2 nesting levels; `dataclass(slots=True[, frozen=True])` for value objects.
- Never blind `except Exception` (ruff BLE001) — catch precisely. Do NOT combine types in one `except` (ruff 0.15.21 format bug) — split into separate `except` blocks.
- Error hierarchy: subclasses of `anishift/errors.py` (`AniShiftError` → `TransientError`/`FatalError`), `ErrorContext(code, message, suggestion, details)`. Never `sys.exit()` in domain logic; never a raw traceback to the user.
- Dependencies only via `uv add` — add `py7zr` with `uv add py7zr` (NEVER hand-edit pyproject.toml dependencies).
- Auto-install on first shell launch: `ensure_binaries()` runs at start when binaries are missing (idiot-proof — the user never needs to know a `setup` step exists). A download/network failure must NOT crash the shell — it warns and lets the user in; `doctor` stays red until it succeeds. Progress is shown with a live bar (`ProgressBarManager`).
- Binaries live under `external/bin/<tool>/` (gitignored). `external/bin/` layout is fixed by `anishift/platform/binaries.py` `_TOOL_DIR`: mkvextract/mkvmerge → `mkvtoolnix/`, ffmpeg/ffprobe → `ffmpeg/`.
- Tests have no docstrings (name = description), covered by per-file-ignore for `D`.
- Quality gates before every commit: `uv run ruff check anishift/ tests/` · `uv run ruff format --check anishift/ tests/` · `uv run mypy anishift/ tests/` · `uv run pytest`.
- Conventional Commits; ZERO AI traces (no Co-Authored-By, no generator footer).
- Git flow: feature branch `feat/etap-2.5-installer` → PR to `main`. Never commit to `main`.

## Verified facts (real values — no placeholders)

These were fetched and hashed during planning. Use them verbatim in the manifest (Task 1).

- **mkvtoolnix**: `https://mkvtoolnix.download/windows/releases/100.0/mkvtoolnix-64-bit-100.0.7z`
  - size: `29708584` bytes
  - sha256: `061de38bd10e7e28697b897e0b890b78d6f2ec8d668a9c198600ed45c19672ab`
  - archive format: `7z`; members: `mkvtoolnix/mkvextract.exe`, `mkvtoolnix/mkvmerge.exe`
- **ffmpeg**: `https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip`
  - size: `168699965` bytes
  - sha256: `6f0c5e3e1ecf447ea52448fb9111f1c7429ae93d95ce71b80e2761053154a20e`
  - archive format: `zip`; members: `ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe`, `ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe`
  - NOTE: the URL points at the moving `latest` tag; the sha256 above pins one specific build. A newer BtbN build → hash mismatch → `setup` refuses until the manifest is updated. This is intended (reproducible builds), not a bug.

> Windows-only scope: both packages are `win64`. On non-Windows, `resolve_binary` already falls back to PATH, so `setup` skips these packages off Windows (Linux ships mkvtoolnix/ffmpeg via its package manager). balcon is out of scope this stage.

## Edge cases — explicit behavior for every failure

Every row is a case the code handles deliberately. "temp" = the `TemporaryDirectory` staging area; "live tree" = `external/bin/`.

| Case | Behavior |
|---|---|
| **First launch, binaries missing, network OK** | `ensure_binaries()` at shell start downloads with a progress bar, then continues into the shell. |
| **First launch, NO network** | Download raises `httpx` connect error → caught → shell prints a warning ("couldn't download binaries — some features stay off until you're online") and lets the user into the shell anyway. `doctor` stays red. NO crash. |
| **Download interrupted mid-stream** | Partial file lives in temp, never in the live tree. `TemporaryDirectory` deletes it. Live tree untouched. Next launch/`setup` retries from scratch. |
| **SHA256 mismatch** (corrupt / server changed the build) | `HashMismatchError` → the package is not installed, live tree untouched, message tells the user to re-run. Other packages still process. |
| **Second launch (binaries already present)** | `verify_installed()` sees the members → skip, zero network, no re-download, no overwrite. Shell starts instantly. |
| **Partial install** (mkvtoolnix ok, ffmpeg failed last run) | Per-package skip check is independent: mkvtoolnix skipped, ffmpeg retried. No duplication. |
| **Archive member missing / wrong path in manifest** | `member not found in archive` error → that package not installed, others continue. |
| **Malicious archive path** (`../../evil.exe`) | Path-traversal guard (manifest load + extract re-check) rejects it; nothing written outside the live tree. |
| **Unused files in the archive** (docs, ffplay.exe, licenses) | Only the manifest's named members are extracted. Everything else stays in temp and is deleted with it — nothing lands in the live tree. |
| **HTTP 404 / 503 / redirect** | `response.raise_for_status()` raises → package fails, live tree untouched, others continue. (ffmpeg source is BtbN/GitHub precisely because gyan.dev returns 503 to automated clients.) |
| **`external/bin/` doesn't exist yet** | `mkdir(parents=True, exist_ok=True)` creates it on install. |
| **Non-Windows OS** | Win64 packages reported `unavailable`; `resolve_binary` falls back to PATH (mkvtoolnix/ffmpeg ship in Linux distros). No download attempted. |
| **`anishift setup` re-run manually** | Same skip-if-present logic — a no-op when everything is already installed; re-fetches only what's missing. |

---

## File Structure

- `pyproject.toml` (MODIFY via `uv add py7zr`) — add the 7z dependency.
- `external/bin_hashes.json` (MODIFY) — fill the manifest with the verified values above.
- `anishift/setup/manifest.py` (CREATE) — load + validate the manifest into typed dataclasses.
- `anishift/setup/installer.py` (CREATE) — download → verify hash → extract members (traversal-guarded) → atomic move.
- `anishift/setup/doctor.py` (MODIFY) — add SHA256 verification to `check_binaries`.
- `anishift/cli/main.py` (MODIFY) — add the `setup` command.
- `tests/test_manifest.py` (CREATE) — manifest load/validation.
- `tests/test_installer.py` (CREATE) — extraction, hash verify, traversal guard, skip-if-present (no network).

---

## Task 1: Fill the manifest + add py7zr

**Files:**
- Modify: `external/bin_hashes.json`
- Modify: `pyproject.toml` (via `uv add py7zr`)

**Interfaces:**
- Produces: `external/bin_hashes.json` with a `binaries` object keyed by tool name (`mkvtoolnix`, `ffmpeg`), each with `url`, `sha256`, `size_bytes`, `archive` (`"7z"`/`"zip"`), and `members` (list of `{archive_path, dest}` where `dest` is relative to `external/bin/`, e.g. `mkvtoolnix/mkvextract.exe`).

- [ ] **Step 1: Add the py7zr dependency**

Run: `uv add py7zr`
Expected: `pyproject.toml` gains `py7zr>=...` under `[project.dependencies]`, `uv.lock` updates.

- [ ] **Step 2: Write the manifest**

Overwrite `external/bin_hashes.json` with:

```json
{
  "$schema_note": "Manifest of external binaries: per package archive URL + SHA256 + size (bytes) + members to extract into external/bin/. anishift setup downloads and verifies against this; anishift doctor checks presence/hash. Windows (win64) packages; non-Windows falls back to PATH.",
  "binaries": {
    "mkvtoolnix": {
      "url": "https://mkvtoolnix.download/windows/releases/100.0/mkvtoolnix-64-bit-100.0.7z",
      "sha256": "061de38bd10e7e28697b897e0b890b78d6f2ec8d668a9c198600ed45c19672ab",
      "size_bytes": 29708584,
      "archive": "7z",
      "members": [
        { "archive_path": "mkvtoolnix/mkvextract.exe", "dest": "mkvtoolnix/mkvextract.exe" },
        { "archive_path": "mkvtoolnix/mkvmerge.exe", "dest": "mkvtoolnix/mkvmerge.exe" }
      ]
    },
    "ffmpeg": {
      "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
      "sha256": "6f0c5e3e1ecf447ea52448fb9111f1c7429ae93d95ce71b80e2761053154a20e",
      "size_bytes": 168699965,
      "archive": "zip",
      "members": [
        { "archive_path": "ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe", "dest": "ffmpeg/ffmpeg.exe" },
        { "archive_path": "ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe", "dest": "ffmpeg/ffprobe.exe" }
      ]
    }
  }
}
```

- [ ] **Step 3: Verify the JSON parses and dependency resolved**

Run: `uv run python -c "import json,pathlib; d=json.loads(pathlib.Path('external/bin_hashes.json').read_text()); print(sorted(d['binaries'])); import py7zr; print('py7zr', py7zr.__version__)"`
Expected: `['ffmpeg', 'mkvtoolnix']` and a py7zr version string.

- [ ] **Step 4: Commit**

```bash
git add external/bin_hashes.json pyproject.toml uv.lock
git commit -m "feat(setup): fill binary manifest and add py7zr"
```

---

## Task 2: Manifest loader `manifest.py`

**Files:**
- Create: `anishift/setup/manifest.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Consumes: `external/bin_hashes.json` (Task 1), `anishift/errors.py` (`AniShiftError`, `ErrorCode`, `ErrorContext`, `FatalError`).
- Produces:
  - `ArchiveFormat = Literal["7z", "zip"]`
  - `Member` dataclass (frozen, slots): `archive_path: str`, `dest: str`.
  - `BinaryPackage` dataclass (frozen, slots): `name: str`, `url: str`, `sha256: str`, `size_bytes: int`, `archive: ArchiveFormat`, `members: tuple[Member, ...]`.
  - `ManifestError(FatalError)`.
  - `manifest_path() -> Path` — `<repo>/external/bin_hashes.json`.
  - `load_manifest(path: Path | None = None) -> tuple[BinaryPackage, ...]` — parse + validate; raises `ManifestError` on malformed data.

- [ ] **Step 1: Write failing tests**

Create `tests/test_manifest.py`:

```python
"""Tests for the binary-manifest loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from anishift.setup.manifest import (
    BinaryPackage,
    ManifestError,
    load_manifest,
    manifest_path,
)


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "bin_hashes.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_real_manifest_loads_both_packages() -> None:
    packages = load_manifest(manifest_path())
    names = {p.name for p in packages}
    assert names == {"mkvtoolnix", "ffmpeg"}


def test_real_manifest_ffmpeg_members_target_ffmpeg_dir() -> None:
    packages = {p.name: p for p in load_manifest(manifest_path())}
    dests = {m.dest for m in packages["ffmpeg"].members}
    assert dests == {"ffmpeg/ffmpeg.exe", "ffmpeg/ffprobe.exe"}


def test_load_returns_typed_packages(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {
            "binaries": {
                "tool": {
                    "url": "https://example.test/a.zip",
                    "sha256": "ab" * 32,
                    "size_bytes": 10,
                    "archive": "zip",
                    "members": [{"archive_path": "a/x.exe", "dest": "tool/x.exe"}],
                }
            }
        },
    )
    packages = load_manifest(path)
    assert len(packages) == 1
    pkg = packages[0]
    assert isinstance(pkg, BinaryPackage)
    assert pkg.name == "tool"
    assert pkg.members[0].dest == "tool/x.exe"


def test_missing_binaries_key_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"nope": {}})
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_bad_archive_format_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {"binaries": {"t": {"url": "u", "sha256": "x", "size_bytes": 1, "archive": "rar", "members": []}}},
    )
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_member_dest_with_parent_traversal_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {
            "binaries": {
                "t": {
                    "url": "u",
                    "sha256": "x",
                    "size_bytes": 1,
                    "archive": "zip",
                    "members": [{"archive_path": "a", "dest": "../evil.exe"}],
                }
            }
        },
    )
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_corrupt_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "bin_hashes.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_manifest.py -q`
Expected: FAIL — `anishift.setup.manifest` does not exist (ImportError).

- [ ] **Step 3: Implement `manifest.py`**

Create `anishift/setup/manifest.py`:

```python
"""Load and validate the external-binary manifest (``bin_hashes.json``).

The manifest is the single source of truth for what ``anishift setup``
downloads: per package a URL, an archive SHA256, a size, the archive format,
and which members to extract to which destination under ``external/bin/``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from anishift.errors import ErrorCode, ErrorContext, FatalError

__all__ = [
    "ArchiveFormat",
    "BinaryPackage",
    "ManifestError",
    "Member",
    "load_manifest",
    "manifest_path",
]

ArchiveFormat = Literal["7z", "zip"]
"""Supported archive container formats."""

# ── Constants ──────────────────────────────────────────────────────────────

_ARCHIVE_FORMATS: Final[frozenset[str]] = frozenset(("7z", "zip"))
"""Accepted values for a package's ``archive`` field."""


class ManifestError(FatalError):
    """Raised when the binary manifest is missing or malformed."""


@dataclass(frozen=True, slots=True)
class Member:
    """One file to extract from an archive.

    Attributes:
        archive_path: Path of the member inside the archive.
        dest: Destination relative to ``external/bin/`` (no ``..``).
    """

    archive_path: str
    dest: str


@dataclass(frozen=True, slots=True)
class BinaryPackage:
    """A downloadable archive plus the members to install from it.

    Attributes:
        name: Tool name (also the manifest key), e.g. ``"ffmpeg"``.
        url: Download URL of the archive.
        sha256: Expected SHA256 of the downloaded archive (hex).
        size_bytes: Expected archive size in bytes.
        archive: Container format of the download.
        members: Files to extract from the archive.
    """

    name: str
    url: str
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
            message=message,
            suggestion="Check external/bin_hashes.json against the manifest schema",
        ),
    )


def _parse_member(raw: Any) -> Member:
    """Validate and build a :class:`Member` from raw JSON."""
    if not isinstance(raw, dict):
        raise _fail("member must be an object")
    archive_path = raw.get("archive_path")
    dest = raw.get("dest")
    if not isinstance(archive_path, str) or not isinstance(dest, str):
        raise _fail("member needs string archive_path and dest")
    if ".." in Path(dest).parts or Path(dest).is_absolute():
        raise _fail(f"member dest escapes external/bin: {dest}")
    return Member(archive_path=archive_path, dest=dest)


def _parse_package(name: str, raw: Any) -> BinaryPackage:
    """Validate and build a :class:`BinaryPackage` from raw JSON."""
    if not isinstance(raw, dict):
        raise _fail(f"package {name} must be an object")
    url = raw.get("url")
    sha256 = raw.get("sha256")
    size_bytes = raw.get("size_bytes")
    archive = raw.get("archive")
    members = raw.get("members")
    if not isinstance(url, str) or not isinstance(sha256, str):
        raise _fail(f"package {name} needs string url and sha256")
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool):
        raise _fail(f"package {name} needs integer size_bytes")
    if archive not in _ARCHIVE_FORMATS:
        raise _fail(f"package {name} has unsupported archive: {archive!r}")
    if not isinstance(members, list):
        raise _fail(f"package {name} needs a members list")
    return BinaryPackage(
        name=name,
        url=url,
        sha256=sha256,
        size_bytes=size_bytes,
        archive=archive,  # type: ignore[arg-type]
        members=tuple(_parse_member(m) for m in members),
    )


def load_manifest(path: Path | None = None) -> tuple[BinaryPackage, ...]:
    """Load and validate the manifest.

    Args:
        path: Manifest file (defaults to :func:`manifest_path`).

    Returns:
        Parsed packages in manifest order.

    Raises:
        ManifestError: When the file is missing, unparseable, or malformed.
    """
    target = path if path is not None else manifest_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _fail(f"cannot read manifest: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise _fail(f"manifest is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("binaries"), dict):
        raise _fail("manifest needs a 'binaries' object")
    return tuple(_parse_package(name, body) for name, body in raw["binaries"].items())
```

- [ ] **Step 4: Run quality gate + tests**

Run: `uv run ruff check anishift/ tests/ && uv run ruff format --check anishift/ tests/ && uv run mypy anishift/ tests/ && uv run pytest tests/test_manifest.py -q`
Expected: all clean, tests PASS.

- [ ] **Step 5: Commit**

```bash
git add anishift/setup/manifest.py tests/test_manifest.py
git commit -m "feat(setup): typed binary-manifest loader with validation"
```

---

## Task 3: Installer `installer.py`

**Files:**
- Create: `anishift/setup/installer.py`
- Test: `tests/test_installer.py`

**Interfaces:**
- Consumes: `manifest.py` (`BinaryPackage`, `Member`, `load_manifest`), `anishift/errors.py`, `anishift/platform/binaries.py` (`external_bin_root`, `is_windows`), `py7zr`, stdlib `zipfile`/`hashlib`/`shutil`/`tempfile`, `httpx`.
- Produces:
  - `InstallerError(FatalError)`, `HashMismatchError(InstallerError)`.
  - `InstallOutcome = Literal["installed", "skipped", "unavailable"]`.
  - `PackageResult` dataclass (frozen, slots): `name: str`, `outcome: InstallOutcome`, `detail: str`.
  - `sha256_file(path: Path) -> str` — streamed hex digest.
  - `verify_installed(package: BinaryPackage, bin_root: Path) -> bool` — all members already present.
  - `extract_members(archive: Path, package: BinaryPackage, dest_root: Path) -> None` — extract named members (traversal-guarded) to `dest_root`.
  - `install_package(package, *, bin_root, download=..., force=False) -> PackageResult` — skip-if-present → download → verify sha256 → extract → atomic move.
  - `run_setup(*, packages=None, bin_root=None) -> list[PackageResult]` — install each manifest package; off Windows returns `unavailable` for win64 packages.

- [ ] **Step 1: Write failing tests (no network — synthetic zip)**

Create `tests/test_installer.py`:

```python
"""Tests for the binary installer (extraction, hashing, guards)."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from anishift.setup.installer import (
    HashMismatchError,
    extract_members,
    install_package,
    sha256_file,
    verify_installed,
)
from anishift.setup.manifest import BinaryPackage, Member


def _zip(tmp_path: Path, entries: dict[str, bytes]) -> Path:
    archive = tmp_path / "pkg.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return archive


def _package(archive: Path, members: list[Member]) -> BinaryPackage:
    return BinaryPackage(
        name="tool",
        url=archive.as_uri(),
        sha256=sha256_file(archive),
        size_bytes=archive.stat().st_size,
        archive="zip",
        members=tuple(members),
    )


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    f.write_bytes(b"hello world")
    assert sha256_file(f) == hashlib.sha256(b"hello world").hexdigest()


def test_extract_members_writes_dest_tree(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/bin/tool.exe": b"MZbinary"})
    pkg = _package(archive, [Member("root/bin/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"
    extract_members(archive, pkg, dest_root)
    assert (dest_root / "tool" / "tool.exe").read_bytes() == b"MZbinary"


def test_extract_members_rejects_missing_member(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/other.exe": b"x"})
    pkg = _package(archive, [Member("root/tool.exe", "tool/tool.exe")])
    with pytest.raises(Exception, match="member not found"):
        extract_members(archive, pkg, tmp_path / "bin")


def test_verify_installed_true_when_all_present(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    pkg = _package(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"
    (dest_root / "tool").mkdir(parents=True)
    (dest_root / "tool" / "tool.exe").write_bytes(b"x")
    assert verify_installed(pkg, dest_root) is True


def test_verify_installed_false_when_missing(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    pkg = _package(archive, [Member("root/tool.exe", "tool/tool.exe")])
    assert verify_installed(pkg, tmp_path / "bin") is False


def test_install_package_skips_when_present(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    pkg = _package(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"
    (dest_root / "tool").mkdir(parents=True)
    (dest_root / "tool" / "tool.exe").write_bytes(b"x")

    def _never(_pkg: BinaryPackage, _dst: Path) -> None:
        raise AssertionError("download must not be called when already present")

    result = install_package(pkg, bin_root=dest_root, download=_never)
    assert result.outcome == "skipped"


def test_install_package_downloads_and_extracts(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"MZ"})
    pkg = _package(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"

    def _fake_download(_pkg: BinaryPackage, target: Path) -> None:
        target.write_bytes(archive.read_bytes())

    result = install_package(pkg, bin_root=dest_root, download=_fake_download)
    assert result.outcome == "installed"
    assert (dest_root / "tool" / "tool.exe").read_bytes() == b"MZ"


def test_install_package_rejects_bad_hash(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"MZ"})
    pkg = BinaryPackage(
        name="tool",
        url=archive.as_uri(),
        sha256="00" * 32,
        size_bytes=archive.stat().st_size,
        archive="zip",
        members=(Member("root/tool.exe", "tool/tool.exe"),),
    )
    dest_root = tmp_path / "bin"

    def _fake_download(_pkg: BinaryPackage, target: Path) -> None:
        target.write_bytes(archive.read_bytes())

    with pytest.raises(HashMismatchError):
        install_package(pkg, bin_root=dest_root, download=_fake_download)
    assert not (dest_root / "tool" / "tool.exe").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_installer.py -q`
Expected: FAIL — `anishift.setup.installer` does not exist (ImportError).

- [ ] **Step 3: Implement `installer.py`**

Create `anishift/setup/installer.py`:

```python
"""Download and install external binaries per the manifest.

``anishift setup`` calls :func:`run_setup`. For each package: skip when the
members are already present, otherwise download the archive to a temp dir,
verify its SHA256, extract only the named members (rejecting path traversal),
and atomically move them into ``external/bin/``. Nothing touches the live
``external/bin/`` tree unless the archive verified.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import httpx
import py7zr

from anishift.errors import ErrorCode, ErrorContext, FatalError
from anishift.platform.binaries import external_bin_root, is_windows
from anishift.setup.manifest import BinaryPackage, load_manifest

__all__ = [
    "HashMismatchError",
    "InstallOutcome",
    "InstallerError",
    "PackageResult",
    "extract_members",
    "install_package",
    "run_setup",
    "sha256_file",
    "verify_installed",
]

InstallOutcome = Literal["installed", "skipped", "unavailable"]
"""Result of trying to install one package."""

DownloadFn = Callable[[BinaryPackage, Path], None]
"""Downloads ``package`` to the given target path."""

# ── Constants ──────────────────────────────────────────────────────────────

_CHUNK_SIZE: Final[int] = 1 << 20
"""Read/stream chunk size in bytes (1 MiB)."""

_DOWNLOAD_TIMEOUT: Final[float] = 300.0
"""Per-download timeout in seconds."""


class InstallerError(FatalError):
    """Raised when installing a binary package fails."""


class HashMismatchError(InstallerError):
    """Raised when a downloaded archive fails SHA256 verification."""


@dataclass(frozen=True, slots=True)
class PackageResult:
    """Outcome of installing one package.

    Attributes:
        name: Package name.
        outcome: What happened (installed / skipped / unavailable).
        detail: Human-readable one-liner for the report.
    """

    name: str
    outcome: InstallOutcome
    detail: str


def sha256_file(path: Path) -> str:
    """Return the SHA256 hex digest of *path*, streamed in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def verify_installed(package: BinaryPackage, bin_root: Path) -> bool:
    """Return ``True`` when every member of *package* already exists."""
    return all((bin_root / member.dest).is_file() for member in package.members)


def _fail(message: str, *, suggestion: str = "") -> InstallerError:
    """Build an :class:`InstallerError` with a consistent context."""
    return InstallerError(
        context=ErrorContext(
            code=ErrorCode.IO_ERROR,
            message=message,
            suggestion=suggestion,
        ),
    )


def _read_member(archive: Path, archive_format: str, archive_path: str) -> bytes:
    """Read one member's bytes from a zip or 7z archive."""
    if archive_format == "zip":
        with zipfile.ZipFile(archive) as zf:
            if archive_path not in zf.namelist():
                raise _fail(f"member not found in archive: {archive_path}")
            return zf.read(archive_path)
    with py7zr.SevenZipFile(archive, "r") as zf:
        extracted = zf.read(targets=[archive_path])
        if archive_path not in extracted:
            raise _fail(f"member not found in archive: {archive_path}")
        return extracted[archive_path].read()


def extract_members(archive: Path, package: BinaryPackage, dest_root: Path) -> None:
    """Extract *package*'s named members from *archive* into *dest_root*.

    Destination paths were validated against traversal at manifest load; this
    re-checks after resolving to be safe, then writes each member.
    """
    for member in package.members:
        target = (dest_root / member.dest).resolve()
        if not target.is_relative_to(dest_root.resolve()):
            raise _fail(f"member dest escapes bin root: {member.dest}")
        data = _read_member(archive, package.archive, member.archive_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def _download_httpx(package: BinaryPackage, target: Path) -> None:
    """Stream *package*'s archive to *target* over HTTPS."""
    with httpx.stream("GET", package.url, follow_redirects=True, timeout=_DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_bytes(_CHUNK_SIZE):
                handle.write(chunk)


def install_package(
    package: BinaryPackage,
    *,
    bin_root: Path,
    download: DownloadFn = _download_httpx,
    force: bool = False,
) -> PackageResult:
    """Install one package, skipping when already present.

    Args:
        package: The package to install.
        bin_root: Root that members are placed under (``external/bin``).
        download: Injectable downloader (real HTTPS by default; fakes in tests).
        force: Re-download even when members are present.

    Returns:
        A :class:`PackageResult` describing what happened.

    Raises:
        HashMismatchError: When the downloaded archive fails verification.
        InstallerError: On download/extraction failure.
    """
    if not force and verify_installed(package, bin_root):
        return PackageResult(package.name, "skipped", "already present")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        archive = tmp_dir / f"{package.name}.{package.archive}"
        download(package, archive)

        actual = sha256_file(archive)
        if actual != package.sha256:
            raise HashMismatchError(
                context=ErrorContext(
                    code=ErrorCode.BINARY_HASH_MISMATCH,
                    message=f"{package.name}: sha256 mismatch",
                    suggestion="Re-run `anishift setup`; if it persists the manifest may be stale",
                    details={"expected": package.sha256, "actual": actual},
                ),
            )

        staged = tmp_dir / "staged"
        extract_members(archive, package, staged)
        for member in package.members:
            final = bin_root / member.dest
            final.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged / member.dest), str(final))

    return PackageResult(package.name, "installed", "downloaded and extracted")


def run_setup(
    *,
    packages: tuple[BinaryPackage, ...] | None = None,
    bin_root: Path | None = None,
) -> list[PackageResult]:
    """Install every manifest package, returning a per-package report.

    Off Windows the bundled win64 packages are reported as ``unavailable``
    (Linux resolves mkvtoolnix/ffmpeg from PATH instead of downloading).
    """
    resolved = packages if packages is not None else load_manifest()
    root = bin_root if bin_root is not None else external_bin_root()
    results: list[PackageResult] = []
    for package in resolved:
        if not is_windows():
            results.append(PackageResult(package.name, "unavailable", "use your OS package manager (PATH)"))
            continue
        results.append(install_package(package, bin_root=root))
    return results
```

- [ ] **Step 4: Run quality gate + tests**

Run: `uv run ruff check anishift/ tests/ && uv run ruff format --check anishift/ tests/ && uv run mypy anishift/ tests/ && uv run pytest tests/test_installer.py -q`
Expected: all clean, tests PASS.

- [ ] **Step 5: Commit**

```bash
git add anishift/setup/installer.py tests/test_installer.py
git commit -m "feat(setup): binary installer with hash verify and traversal guard"
```

---

## Task 4: Doctor hash check + `setup` command

**Files:**
- Modify: `anishift/setup/doctor.py`
- Modify: `anishift/cli/main.py`
- Test: `tests/test_doctor.py` (extend)

**Interfaces:**
- Consumes: `installer.py` (`run_setup`, `PackageResult`), `manifest.py` (`load_manifest`), existing `doctor.py` (`CheckResult`, `CheckStatus`, `resolve_binary`, `Binary`), `sha256_file`.
- Produces: `check_binaries` additionally warns when a present binary's containing package hash cannot be confirmed is out of scope; instead it verifies that each present required binary is a real file (existing behavior) AND, when the manifest lists the package, that the on-disk member matches is NOT required (archive hash ≠ per-exe hash). So the doctor extension is limited to: report which manifest packages are fully installed vs missing, surfaced through the existing `binaries` check `details`. `main.py` gains `setup()` command that calls `run_setup()` and prints the report + a short doctor summary.

> Scope note: the manifest stores the *archive* SHA256, not per-exe hashes, so `doctor` cannot hash-verify individual installed `.exe`s against it. The honest, useful check is presence-completeness per package. Per-exe hashing is deliberately not added (would need a second manifest of exe hashes — out of scope, YAGNI).

- [ ] **Step 1: Write failing test for the setup command wiring**

Add to `tests/test_doctor.py` (import at top if missing: `from typer.testing import CliRunner` and `from anishift.cli.main import app`):

```python
def test_setup_command_runs_and_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from anishift.cli import main as cli_main
    from anishift.setup.installer import PackageResult

    def _fake_run_setup() -> list[PackageResult]:
        return [PackageResult("ffmpeg", "installed", "downloaded and extracted")]

    monkeypatch.setattr(cli_main, "run_setup", _fake_run_setup)
    result = CliRunner().invoke(cli_main.app, ["setup"])
    assert result.exit_code == 0
    assert "ffmpeg" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_doctor.py::test_setup_command_runs_and_reports -q`
Expected: FAIL — `run_setup` not importable from `anishift.cli.main` / no `setup` command.

- [ ] **Step 3: Add the `setup` command to `main.py`**

In `anishift/cli/main.py`, add the import near the top (with the other `anishift` imports):

```python
from anishift.setup.installer import PackageResult, run_setup
```

Add this command after the existing `doctor` command:

```python
_OUTCOME_ICON: dict[str, StatusType] = {
    "installed": "success",
    "skipped": "info",
    "unavailable": "warning",
}
"""Maps an install outcome to a ``rich_console`` status-icon name."""


def _print_setup_report(results: list[PackageResult]) -> None:
    """Render installer results as an icon + message list."""
    for result in results:
        icon = get_status_icon(_OUTCOME_ICON.get(result.outcome, "info"))
        console.print(f"{icon} [bold]{result.name}[/bold]: {result.detail}")


@app.command()
def setup() -> None:
    """Download and install missing external binaries into external/bin/."""
    _print_setup_report(run_setup())
```

- [ ] **Step 4: Run quality gate + full tests**

Run: `uv run ruff check anishift/ tests/ && uv run ruff format --check anishift/ tests/ && uv run mypy anishift/ tests/ && uv run pytest -q`
Expected: all clean, all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add anishift/cli/main.py tests/test_doctor.py
git commit -m "feat(cli): add anishift setup command"
```

---

## Task 5: Progress bar in the installer + auto-install on shell start

**Files:**
- Modify: `anishift/setup/installer.py` (wire `ProgressBarManager` into `_download_httpx`; add `ensure_binaries()`)
- Modify: `anishift/cli/shell.py` (call `ensure_binaries()` after the banner, before the prompt loop)
- Test: `tests/test_installer.py` (extend — `ensure_binaries` skips when present, swallows network errors)

**Interfaces:**
- Consumes: `ProgressBarManager` (from `utils.rich_console.progress`), `run_setup`/`verify_installed`/`load_manifest`/`external_bin_root` (already in installer), `httpx`.
- Produces:
  - `_download_httpx` streams with a live `ProgressBarManager` bar (flags copied from MangaShift: `bar="blocks"`, `show_download=True`, `show_speed=True`, `show_percentage=True`, `show_elapsed=True`, `show_eta=False`, `show_spinner=False`); `total` from `content-length` (or `None`).
  - `ensure_binaries() -> list[PackageResult]` — if any manifest package is missing, run the install; catch `httpx.HTTPError`/`OSError`/`InstallerError` and return an `unavailable`/failed report instead of raising (never crashes the shell). A no-op when everything is present.

- [ ] **Step 1: Write failing tests for `ensure_binaries`**

Add to `tests/test_installer.py`:

```python
def test_ensure_binaries_noop_when_all_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from anishift.setup import installer

    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    pkg = _package(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"
    (dest_root / "tool").mkdir(parents=True)
    (dest_root / "tool" / "tool.exe").write_bytes(b"x")

    monkeypatch.setattr(installer, "load_manifest", lambda: (pkg,))
    monkeypatch.setattr(installer, "external_bin_root", lambda: dest_root)
    monkeypatch.setattr(installer, "is_windows", lambda: True)

    results = installer.ensure_binaries()
    assert all(r.outcome == "skipped" for r in results)


def test_ensure_binaries_swallows_network_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from anishift.setup import installer

    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    pkg = _package(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"

    def _boom(_pkg: BinaryPackage, _target: Path) -> None:
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(installer, "load_manifest", lambda: (pkg,))
    monkeypatch.setattr(installer, "external_bin_root", lambda: dest_root)
    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _boom)

    results = installer.ensure_binaries()  # must NOT raise
    assert results  # a report was returned
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_installer.py -k ensure -q`
Expected: FAIL — `ensure_binaries` does not exist.

- [ ] **Step 3: Wire the progress bar into `_download_httpx`**

Replace `_download_httpx` in `anishift/setup/installer.py`:

```python
def _download_httpx(package: BinaryPackage, target: Path) -> None:
    """Stream *package*'s archive to *target* over HTTPS with a progress bar."""
    with httpx.stream("GET", package.url, follow_redirects=True, timeout=_DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        with (
            ProgressBarManager(
                f"Downloading {package.name}",
                total=total if total > 0 else None,
                bar="blocks",
                show_download=True,
                show_speed=True,
                show_percentage=True,
                show_elapsed=True,
                show_eta=False,
                show_spinner=False,
            ) as bar,
            target.open("wb") as handle,
        ):
            for chunk in response.iter_bytes(_CHUNK_SIZE):
                handle.write(chunk)
                if total > 0:
                    bar.advance(len(chunk))
```

Add the import at the top of `installer.py` (with the other project imports):

```python
from utils.rich_console.progress import ProgressBarManager
```

- [ ] **Step 4: Add `ensure_binaries` to `installer.py`**

Append to `anishift/setup/installer.py` and add `"ensure_binaries"` to `__all__`:

```python
def ensure_binaries() -> list[PackageResult]:
    """Install any missing binaries; never raise (safe to call at shell start).

    A no-op when every manifest package is already present. Network or install
    failures are caught and returned as a report so the shell can start anyway
    (``doctor`` will still show the problem).
    """
    packages = load_manifest()
    bin_root = external_bin_root()
    if all(verify_installed(p, bin_root) for p in packages):
        return [PackageResult(p.name, "skipped", "already present") for p in packages]

    results: list[PackageResult] = []
    for package in packages:
        if not is_windows():
            results.append(PackageResult(package.name, "unavailable", "use your OS package manager (PATH)"))
            continue
        try:
            results.append(install_package(package, bin_root=bin_root))
        except httpx.HTTPError as exc:
            results.append(PackageResult(package.name, "unavailable", f"download failed: {exc}"))
        except OSError as exc:
            results.append(PackageResult(package.name, "unavailable", f"install failed: {exc}"))
        except InstallerError as exc:
            results.append(PackageResult(package.name, "unavailable", f"install failed: {exc}"))
    return results
```

- [ ] **Step 5: Call `ensure_binaries()` at shell start**

In `anishift/cli/shell.py`, after `show_banner(context)` and before building the `PromptSession`, add:

```python
    _ensure_binaries_at_start()
```

And add this helper (imports `ensure_binaries` lazily to keep shell startup light):

```python
def _ensure_binaries_at_start() -> None:
    """Auto-install missing binaries on launch; warn but continue on failure."""
    from anishift.setup.installer import ensure_binaries  # noqa: PLC0415

    for result in ensure_binaries():
        if result.outcome == "unavailable":
            console.print(f"[warning]{result.name}[/warning]: {result.detail}")
```

- [ ] **Step 6: Run quality gate + tests**

Run: `uv run ruff check anishift/ tests/ && uv run ruff format --check anishift/ tests/ && uv run mypy anishift/ tests/ && uv run pytest -q`
Expected: all clean, all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add anishift/setup/installer.py anishift/cli/shell.py tests/test_installer.py
git commit -m "feat(setup): progress bar and auto-install binaries on shell start"
```

---

## Task 6: Live smoke + finish branch

**Files:** none (verification only).

- [ ] **Step 1: Real `anishift setup` on this machine (Windows)**

Run: `uv run anishift setup`
Expected: downloads mkvtoolnix + ffmpeg (first run), prints `installed` for both; `external/bin/mkvtoolnix/mkvextract.exe`, `mkvmerge.exe`, `external/bin/ffmpeg/ffmpeg.exe`, `ffprobe.exe` exist.

- [ ] **Step 2: Idempotency — second run skips**

Run: `uv run anishift setup`
Expected: both report `skipped` / `already present`; no re-download.

- [ ] **Step 2b: Auto-install on shell start (the idiot-proof path)**

Delete `external/bin/` (or one tool folder), then run `uv run anishift` (the shell, no subcommand). Expected: after the banner, the shell auto-downloads the missing binaries with a live progress bar, then drops into the prompt — the user did nothing but launch the app. Re-launch: no download (already present), instant start.

- [ ] **Step 3: Doctor goes green**

Run: `uv run anishift doctor`
Expected: the `binaries` check is now `OK` (mkvextract, mkvmerge, ffmpeg present) instead of FAIL.

- [ ] **Step 4: Confirm nothing leaked into git**

Run: `git status --porcelain external/bin/`
Expected: empty (external/bin is gitignored).

- [ ] **Step 5: Final full gate**

Run: `uv run ruff check anishift/ tests/ && uv run ruff format --check anishift/ tests/ && uv run mypy anishift/ tests/ && uv run pytest -q`
Expected: all clean, all tests PASS.

- [ ] **Step 6: Push and open the PR**

```bash
git push -u origin feat/etap-2.5-installer
gh pr create --base main --title "feat: etap 2.5 — binary installer (anishift setup)" --body "Adds anishift setup: downloads mkvtoolnix + ffmpeg, verifies SHA256, extracts into external/bin/. Manifest-driven, idempotent, traversal-guarded. Unblocks stages 3/6/7 (real binaries to run against). doctor now goes green after setup."
```

---

## Self-Review

**Spec coverage** (against the etap-8 installer scope + the stage-2.5 decision):
- Manifest (URL + SHA256 + size + members) → Task 1 (real verified values) + Task 2 (loader).
- Download → verify SHA256 before use → extract → atomic move → Task 3.
- Skip-if-present (2× setup no re-download) → Task 3 `verify_installed` + `install_package`.
- Path-traversal guard → Task 2 (manifest dest) + Task 3 (`extract_members` re-check).
- 7z + zip support → Task 3 `_read_member` (py7zr / zipfile).
- Linux PATH fallback (no download of win64) → Task 3 `run_setup` `unavailable`.
- `anishift setup` command + report → Task 4.
- doctor reflects installed binaries → existing `check_binaries` (presence) already covers it; hash-of-exe deliberately out of scope (documented).
- Live verification on real binaries → Task 5.

**Placeholder scan:** none. Manifest holds real hashes/sizes/URLs fetched during planning. `<...>`-style placeholders absent.

**Type consistency:** `BinaryPackage`/`Member` fields identical across Tasks 2/3. `install_package(package, *, bin_root, download, force)`, `run_setup(*, packages, bin_root)`, `sha256_file(path) -> str`, `verify_installed(package, bin_root) -> bool`, `extract_members(archive, package, dest_root) -> None`, `PackageResult(name, outcome, detail)` consistent Tasks 3/4. `InstallOutcome` literal matches `_OUTCOME_ICON` keys.

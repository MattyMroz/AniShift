# Etap 7 — plan implementacji składania i pełnego E2E

> Status: plan wykonawczy z gotowym kodem, po audycie zgodności z repo (2026-08-05).
> Data: 2026-08-02.
> Wymagania: [`etap-7-wymagania.md`](etap-7-wymagania.md) — wszystkie decyzje domknięte.
> Branch: `feature/composition`.
> Ten dokument zawiera **kod do napisania**, nie opis. Każdy plik ma pełną treść albo dokładny
> diff. Kod jest zgodny z kontraktami zastanymi w repo (sprawdzone: `services/audio/commands.py`,
> `services/extraction/types.py`, `pipeline/types.py`, `cli/commands.py`).

## 1. Zasady realizacji

- każdy krok kończy się **działającą aplikacją** i zielonymi bramkami;
- bramki przed każdym commitem: `uv run ruff check anishift/ tests/`,
  `uv run ruff format --check anishift/ tests/`, `uv run mypy anishift/ tests/`, `uv run pytest`;
- żaden plik serwisu nie przekracza ~400 linii (wzorzec `services/audio/`);
- zero rejestru silników — tryby to `Enum`, zgodnie z regułą repo;
- composition nie importuje `subtitles`, `translation`, `tts` ani `pysubs2`;
- typowanie zmiennych lokalnych, docstring stałej `Final` **pod** nią, sekcja
  `# ── Constants ──`, guard clauses, maks. 2 poziomy zagnieżdżeń;
- testy bez docstringów i komentarzy (hook `check_test_comments.py`).

## 2. Drzewo katalogów po etapie

```text
anishift/
├── services/
│   └── composition/                  NOWY — domena składania
│       ├── AGENTS.md                 NOWY
│       ├── CLAUDE.md                 NOWY (@AGENTS.md)
│       ├── __init__.py               NOWY — publiczna fasada
│       ├── types.py                  NOWY — wartości domeny
│       ├── errors.py                 NOWY — hierarchia błędów
│       ├── config.py                 NOWY — CompositionConfig
│       ├── paths.py                  NOWY — ścieżki, escapowanie, nazwy
│       ├── commands.py               NOWY — budowa komend + streaming runner
│       ├── probe.py                  NOWY — identify + walidacja wyniku
│       ├── fonts.py                  NOWY — brakujące czcionki
│       └── service.py                NOWY — fasada trzech trybów
├── pipeline/
│   ├── composition_runtime.py        NOWY — adapter FileOutcome → CompositionPlan + pętla składania
│   ├── compose_only.py               NOWY — źródło outcomes dla /compose (bez tłumaczenia i TTS)
│   ├── runner.py                     ZMIANA — krok 5, sprzątanie tmp, filtr .displayed
│   ├── types.py                      ZMIANA — pola wyniku składania, protokół UI składania
│   └── AGENTS.md                     ZMIANA
├── cli/
│   ├── commands.py                   ZMIANA — /compose
│   ├── pipeline_ui.py                ZMIANA — postęp, zapowiedź kosztu, raport
│   └── settings_panel.py             ZMIANA — nowe pola
├── config/user_settings.py           ZMIANA — nowe pola, usunięcie martwego
└── services/extraction/
    ├── types.py                      ZMIANA — MediaInfo.attachments
    ├── service.py                    ZMIANA — parse_media_info czyta załączniki
    └── tracks.py                     ZMIANA — priorytety języków z konfiguracji

tests/
├── services/composition/
│   ├── test_composition_paths.py
│   ├── test_composition_commands.py
│   ├── test_composition_probe.py
│   ├── test_composition_fonts.py
│   ├── test_composition_service.py
│   └── test_composition_real.py
├── pipeline/
│   ├── test_composition_runtime.py
│   └── test_compose_only.py
└── cli/test_compose_command.py
```

Czego **nie** budujemy, choć wymagania tego żądają: ręcznego wyboru ścieżek audio i napisów
(§6.5 wymagań). To już istnieje w kodzie — `PipelineInteraction.choose_tracks`
(`pipeline/types.py:206`), implementacja `_ManualInteraction.choose_tracks`
(`cli/pipeline_ui.py:648`) i wywołanie per plik w `_extract_mkv` (`runner.py:1063`).
Etap 7 dokłada do tego wyłącznie priorytety języków dla trybu auto (krok 10).

---

## 3. Krok 1 — szkielet domeny

### 3.1. `anishift/services/composition/types.py`

```python
"""Value objects describing one composition request and its outcome."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

__all__ = [
    "AttachedSubtitle",
    "CompositionPlan",
    "CompositionResult",
    "CompositionStatus",
    "OutputVariant",
    "QualityPreset",
    "SubtitleRole",
]


class OutputVariant(StrEnum):
    """Final artifact the user asked for."""

    PLAYERS = "players"
    MERGE = "merge"
    BURN = "burn"


class QualityPreset(StrEnum):
    """Named quality target for hardsub rendering."""

    HIGH = "high"
    BALANCED = "balanced"
    COMPACT = "compact"


class SubtitleRole(StrEnum):
    """Role a subtitle file plays in the finished container."""

    FULL = "full"
    DISPLAYED = "displayed"


class CompositionStatus(StrEnum):
    """Terminal state of one composition attempt."""

    COMPLETED = "completed"
    SKIPPED_NOTHING_TO_ADD = "skipped_nothing_to_add"


@dataclass(frozen=True, slots=True)
class AttachedSubtitle:
    """One subtitle file muxed into the result with its track metadata."""

    path: Path
    role: SubtitleRole
    language: str
    track_name: str


@dataclass(frozen=True, slots=True)
class CompositionPlan:
    """Neutral description of what to assemble for one source file.

    Attributes:
        source_path: Original container the result is built from.
        variant: Requested output variant.
        narration_audio: Rendered lector sidecar, when one exists.
        subtitles: Subtitle files to mux, in final track order.
        burn_subtitle: Subtitle file to render into the picture.
        source_subtitle_kind: ``ass`` or ``srt`` for the burned file.
        scope_id: Opaque per-source identifier owned by the pipeline.
        temporary_root: Directory for filter-safe copies and partial files.
        destination_dir: Directory the finished artifact is written to.
    """

    source_path: Path
    variant: OutputVariant
    narration_audio: Path | None = None
    subtitles: tuple[AttachedSubtitle, ...] = ()
    burn_subtitle: Path | None = None
    source_subtitle_kind: str = "ass"
    scope_id: str = ""
    temporary_root: Path = Path()
    destination_dir: Path = Path()

    @property
    def has_material(self) -> bool:
        """Return whether anything would actually be added to the result."""
        return self.narration_audio is not None or bool(self.subtitles) or self.burn_subtitle is not None


@dataclass(frozen=True, slots=True)
class CompositionResult:
    """Outcome of one composition attempt."""

    source_path: Path
    variant: OutputVariant
    status: CompositionStatus
    output_path: Path | None = None
    output_size_bytes: int = 0
    source_size_bytes: int = 0
    duration_ms: float = 0.0
    warnings: tuple[str, ...] = ()
    moved_paths: tuple[Path, ...] = field(default_factory=tuple)
```

### 3.2. `anishift/services/composition/errors.py`

```python
"""Typed failures raised by the composition domain."""

from __future__ import annotations

from anishift.errors import AniShiftError, FatalError

__all__ = [
    "CompositionCancelledError",
    "CompositionConfigError",
    "CompositionError",
    "CompositionProcessError",
    "CompositionValidationError",
]


class CompositionError(AniShiftError):
    """Base error for muxing, rendering, and result placement."""


class CompositionConfigError(CompositionError, FatalError):
    """Composition settings or binaries cannot produce a result."""


class CompositionProcessError(CompositionError, FatalError):
    """An mkvmerge or FFmpeg subprocess failed."""


class CompositionValidationError(CompositionError, FatalError):
    """A produced file failed its post-run validation."""


class CompositionCancelledError(CompositionError, FatalError):
    """Composition stopped because cancellation was requested."""
```

### 3.3. `anishift/services/composition/config.py`

```python
"""Immutable settings for muxing and hardsub rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.composition.errors import CompositionConfigError
from anishift.services.composition.types import QualityPreset

__all__ = ["CompositionConfig"]

# ── Constants ────────────────────────────────────────────────────────────────

_PRESET_CRF: Final[dict[QualityPreset, int]] = {
    QualityPreset.HIGH: 18,
    QualityPreset.BALANCED: 21,
    QualityPreset.COMPACT: 24,
}
"""Constant-quality value per named preset for the x264 encoder."""

_MIN_SIZE_BUDGET_RATIO: Final[float] = 1.0
"""Lowest meaningful ratio between rendered output and source size."""

_MAX_SIZE_BUDGET_RATIO: Final[float] = 4.0
"""Highest ratio still worth warning about instead of rejecting outright."""

_SUPPORTED_ENCODERS: Final[frozenset[str]] = frozenset({"libx264", "libx265"})
"""Video encoders validated for hardsub rendering."""


@dataclass(frozen=True, slots=True)
class CompositionConfig:
    """Composition behaviour shared by every variant.

    Attributes:
        quality_preset: Named quality target for hardsub rendering.
        video_encoder: FFmpeg encoder used when the picture is re-encoded.
        encoder_preset: FFmpeg speed/compression preset.
        size_budget_ratio: Output-to-source size ratio that triggers a warning.
        operation_timeout_s: Timeout for a single muxing or probing process.
        render_timeout_s: Timeout for one hardsub render.
        shutdown_grace_s: Grace period before a hard kill.
    """

    quality_preset: QualityPreset = QualityPreset.BALANCED
    video_encoder: str = "libx264"
    encoder_preset: str = "medium"
    size_budget_ratio: float = 1.1
    operation_timeout_s: float = 120.0
    render_timeout_s: float = 14_400.0
    shutdown_grace_s: float = 5.0

    def __post_init__(self) -> None:
        """Reject settings that cannot produce a valid result."""
        if self.video_encoder not in _SUPPORTED_ENCODERS:
            _raise_config("Composition video encoder is not supported")
        if not _MIN_SIZE_BUDGET_RATIO <= self.size_budget_ratio <= _MAX_SIZE_BUDGET_RATIO:
            _raise_config("Composition size budget ratio must be between 1.0 and 4.0")
        if self.operation_timeout_s <= 0 or self.render_timeout_s <= 0:
            _raise_config("Composition timeouts must be positive")

    @property
    def crf(self) -> int:
        """Return the constant-quality value for the selected preset."""
        return _PRESET_CRF[self.quality_preset]


def _raise_config(message: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.COMPOSITION_FAILED,
        message=message,
        suggestion="Choose supported values in the composition settings.",
    )
    raise CompositionConfigError(context=context)
```

### 3.4. `anishift/services/composition/__init__.py`

```python
"""Composition domain: assemble pipeline products into one finished file."""

from __future__ import annotations

from anishift.services.composition.config import CompositionConfig
from anishift.services.composition.errors import (
    CompositionCancelledError,
    CompositionConfigError,
    CompositionError,
    CompositionProcessError,
    CompositionValidationError,
)
from anishift.services.composition.service import CompositionProgressSink, CompositionService
from anishift.services.composition.types import (
    AttachedSubtitle,
    CompositionPlan,
    CompositionResult,
    CompositionStatus,
    OutputVariant,
    QualityPreset,
    SubtitleRole,
)

__all__ = [
    "AttachedSubtitle",
    "CompositionCancelledError",
    "CompositionConfig",
    "CompositionConfigError",
    "CompositionError",
    "CompositionPlan",
    "CompositionProcessError",
    "CompositionProgressSink",
    "CompositionResult",
    "CompositionService",
    "CompositionStatus",
    "CompositionValidationError",
    "OutputVariant",
    "QualityPreset",
    "SubtitleRole",
]
```

### 3.5. `anishift/services/composition/AGENTS.md`

```markdown
# services/composition

Samodzielna domena składania: bierze źródłowy kontener i gotowe artefakty, oddaje
jeden zweryfikowany plik wynikowy.

## Granica

- Composition przyjmuje `CompositionPlan` ze ścieżkami plików i decyzją, co dołożyć.
- NIE zna ASS/SRT jako formatu, `pysubs2`, `SubtitleSplit`, `FileTranslation`
  ani `SpeechBatch`.
- Decyzję „co dołożyć" podejmuje `pipeline/composition_runtime.py`; composition
  odpowiada wyłącznie za „jak to złożyć".

## Zakazane zależności

- `pysubs2`
- `anishift.pipeline`
- `anishift.services.subtitles`
- `anishift.services.translation`
- `anishift.services.tts`

## Twarde reguły

- Kod wyjścia i stderr sprawdzane ZAWSZE. mkvmerge `1` to sukces z ostrzeżeniem,
  `2` to błąd. `commands.py`
- Nic nie jest kasowane w tej domenie poza własnym plikiem częściowym. Sprzątanie
  `tmp/` należy do pipeline. `service.py`
- Źródłowy plik nie jest nigdy przenoszony ani przemianowywany. Zapis idzie do
  pliku tymczasowego i dopiero po walidacji zastępuje cel. `service.py`
- Brak materiału zwraca `SKIPPED_NOTHING_TO_ADD`, nigdy pustą komendę. `service.py`
- Apostrof w ścieżce łamie filtr napisów FFmpeg niezależnie od escapowania —
  napisy do wypalania ZAWSZE przechodzą przez `filter_safe_copy`. `paths.py`
- mkvmerge nie potrafi pisać do pliku, który czyta. `commands.py`
- Wypalanie zawsze przekodowuje wideo; `-c:v copy` z filtrem napisów nie istnieje.
- Observer postępu nie posiada wykonania: jego wyjątek jest ignorowany. `service.py`

## Konwencje

- mkvmerge v100: `--default-track-flag` i `--forced-display-flag`; stare
  `--default-track`/`--forced-track` NIE istnieją. `commands.py`
- Bez `--track-order`. mkvmerge układa ścieżki w kolejności plików, więc dołożone
  lądują za całym źródłem. Wymienienie tylko dołożonych przesunęłoby oryginalne
  audio i napisy ZA nie. `commands.py`
- Decyzja `-c:a copy` dotyczy pliku faktycznie mapowanego do wyniku (sidecar
  lektora, gdy istnieje), nie pierwszej ścieżki źródła. `service.py`
- Walidacja merge sprawdza NAZWY dołożonych ścieżek. Liczenie polskich ścieżek
  przepuszcza merge, który nic nie dołożył do już polskiego źródła. `probe.py`
- Oba potoki procesu drenowane w wątkach: cichy proces musi dać się anulować i
  ubić po timeoucie, a duży stderr nie może zakleszczyć runnera. `commands.py`
- Postęp merge z `--gui-mode` (`#GUI#progress N%`), postęp renderu z
  `-progress pipe:1 -nostats` (`out_time_us`). `commands.py`
- Filtr `ass=` dla ASS (pełna wierność stylów), `subtitles=` tylko dla SRT.
- MP4 nie przyjmuje ASS ani załączników; stylowane napisy istnieją tam wyłącznie
  jako wypalone w obrazie.
```

**Weryfikacja kroku 1:**

```bash
uv run python -c "from anishift.services.composition import CompositionConfig, OutputVariant; print(CompositionConfig().crf)"
uv run ruff check anishift/services/composition
uv run mypy anishift/services/composition
```

Oczekiwane: wypisze `21`, obie bramki zielone.

---

## 4. Krok 2 — ścieżki i escapowanie

### 4.1. `anishift/services/composition/paths.py`

```python
"""Result placement, output naming, and FFmpeg-safe path handling."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Final

from anishift.services.composition.types import OutputVariant

__all__ = [
    "escape_filter_path",
    "filter_safe_copy",
    "output_path",
    "temporary_sibling",
]

# ── Constants ────────────────────────────────────────────────────────────────

_RESULT_INFIX: Final[str] = ".pl"
"""Infix marking a file as the Polish product of this application."""

_VARIANT_SUFFIX: Final[dict[OutputVariant, str]] = {
    OutputVariant.MERGE: ".mkv",
    OutputVariant.BURN: ".mp4",
}
"""Container extension produced by each assembling variant."""

_FILTER_UNSAFE: Final[re.Pattern[str]] = re.compile(r"['\"]+")
"""Quote characters the FFmpeg subtitle filter drops regardless of escaping."""

_SAFE_STEM_LENGTH: Final[int] = 32
"""Maximum retained characters of a sanitised working-copy stem."""

_DIGEST_LENGTH: Final[int] = 12
"""Hex characters of the stem digest keeping working copies unique."""


def output_path(source: Path, variant: OutputVariant, destination_dir: Path) -> Path:
    """Return the finished artifact path for one source and variant.

    Args:
        source: Original container.
        variant: Assembling variant; ``PLAYERS`` has no single artifact.
        destination_dir: Directory the artifact is written to.

    Returns:
        The destination path carrying the Polish result infix.
    """
    suffix: str = _VARIANT_SUFFIX[variant]
    return destination_dir / f"{source.stem}{_RESULT_INFIX}{suffix}"


def escape_filter_path(path: Path) -> str:
    """Return a path usable inside an FFmpeg subtitle filter value.

    ``as_posix`` removes backslashes, then the drive colon and the remaining
    filter metacharacters are escaped. Apostrophes are NOT handled — the filter
    drops them whatever the escaping, so callers pass a
    :func:`filter_safe_copy` result instead.
    """
    text: str = path.as_posix()
    for character in (":", "[", "]", ","):
        text = text.replace(character, f"\\{character}")
    return f"'{text}'"


def filter_safe_copy(subtitle: Path, work_dir: Path) -> Path:
    """Copy a subtitle to a deterministic name FFmpeg can always open.

    The copy is rewritten on every call: a subtitle is a small text file and a
    stale copy would silently burn the previous run's text.

    Args:
        subtitle: Subtitle file that may carry quote characters in its name.
        work_dir: Directory owned by this run for working copies.

    Returns:
        Path to the working copy.
    """
    digest: str = hashlib.sha256(subtitle.name.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]
    stem: str = _FILTER_UNSAFE.sub("", subtitle.stem)[:_SAFE_STEM_LENGTH].strip() or "subtitle"
    target: Path = work_dir / f"{stem}-{digest}{subtitle.suffix}"
    work_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(subtitle, target)
    return target


def temporary_sibling(path: Path) -> Path:
    """Reserve a unique temporary file beside the destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int
    raw_path: str
    descriptor, raw_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.stem}-",
        suffix=f".tmp{path.suffix}",
    )
    os.close(descriptor)
    return Path(raw_path)
```

### 4.2. `tests/services/composition/test_composition_paths.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from anishift.services.composition.paths import (
    escape_filter_path,
    filter_safe_copy,
    output_path,
    temporary_sibling,
)
from anishift.services.composition.types import OutputVariant


@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        (OutputVariant.MERGE, "Episode.pl.mkv"),
        (OutputVariant.BURN, "Episode.pl.mp4"),
    ],
)
def test_output_path_uses_polish_infix(tmp_path: Path, variant: OutputVariant, expected: str) -> None:
    result = output_path(tmp_path / "Episode.mkv", variant, tmp_path / "output")
    assert result.name == expected
    assert result.parent == tmp_path / "output"


def test_output_path_keeps_polish_characters_and_spaces(tmp_path: Path) -> None:
    source = tmp_path / "Zażółć gęślą jaźń - 04 [1080p].mkv"
    result = output_path(source, OutputVariant.MERGE, tmp_path)
    assert result.name == "Zażółć gęślą jaźń - 04 [1080p].pl.mkv"


def test_escape_filter_path_escapes_drive_colon_and_brackets() -> None:
    escaped = escape_filter_path(Path("C:/anime/[Erai-raws] show - 04.ass"))
    assert escaped.startswith("'")
    assert escaped.endswith("'")
    assert "C\\:" in escaped
    assert "\\[" in escaped
    assert "\\]" in escaped


def test_escape_filter_path_uses_forward_slashes() -> None:
    escaped = escape_filter_path(Path("C:\\anime\\show.ass"))
    assert escaped == "'C\\:/anime/show.ass'"


def test_filter_safe_copy_strips_apostrophes(tmp_path: Path) -> None:
    source = tmp_path / "Heroine Saint No, I'm an All-Works Maid.ass"
    source.write_text("[Script Info]\n", encoding="utf-8")
    work_dir = tmp_path / "work"

    copy = filter_safe_copy(source, work_dir)

    assert "'" not in copy.name
    assert copy.exists()
    assert copy.read_text(encoding="utf-8") == "[Script Info]\n"


def test_filter_safe_copy_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "show's episode.ass"
    source.write_text("x", encoding="utf-8")
    work_dir = tmp_path / "work"

    first = filter_safe_copy(source, work_dir)
    second = filter_safe_copy(source, work_dir)

    assert first == second


def test_filter_safe_copy_separates_similar_names(tmp_path: Path) -> None:
    first_source = tmp_path / "show's episode.ass"
    second_source = tmp_path / 'show"s episode.ass'
    first_source.write_text("a", encoding="utf-8")
    second_source.write_text("bb", encoding="utf-8")
    work_dir = tmp_path / "work"

    assert filter_safe_copy(first_source, work_dir) != filter_safe_copy(second_source, work_dir)


def test_temporary_sibling_lives_next_to_destination(tmp_path: Path) -> None:
    destination = tmp_path / "output" / "Episode.pl.mkv"
    temporary = temporary_sibling(destination)

    assert temporary.parent == destination.parent
    assert temporary.name.endswith(".tmp.mkv")
    assert temporary.exists()
```

**Weryfikacja kroku 2:**

```bash
uv run pytest tests/services/composition/test_composition_paths.py -v
```

Oczekiwane: wszystkie testy zielone, w tym parametryzacja na realnych nazwach z `workspace/`.

---

## 5. Krok 3 — komendy i streaming postępu

`SubprocessRunner` z `services/audio/commands.py` używa `communicate()`, więc **nie umie
strumieniować postępu**. Wypalanie trwa minuty i musi raportować procent, dlatego composition
dostaje własny runner czytający stdout linia po linii.

### 5.1. `anishift/services/composition/commands.py`

```python
"""Command construction and streaming subprocess execution for composition."""

from __future__ import annotations

import queue
import re
import subprocess
import threading
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.composition.config import CompositionConfig
from anishift.services.composition.errors import (
    CompositionCancelledError,
    CompositionProcessError,
)
from anishift.services.composition.paths import escape_filter_path
from anishift.services.composition.types import CompositionPlan
from anishift.utils.logger import get_logger
from anishift.utils.timer import Timer

__all__ = [
    "NARRATION_TRACK_NAME",
    "CommandOutcome",
    "ProgressReader",
    "StreamingRunner",
    "burn_command",
    "merge_command",
    "mp4_audio_is_copyable",
    "parse_ffmpeg_progress",
    "parse_mkvmerge_progress",
    "subtitle_filter_argument",
]

# ── Constants ────────────────────────────────────────────────────────────────

_POLL_SECONDS: Final[float] = 0.2
"""Interval between cancellation checks while a process is streaming."""

_STDERR_TAIL_LINES: Final[int] = 8
"""Trailing stderr lines retained in a safe process error."""

_STDERR_TAIL_CHARS: Final[int] = 2_000
"""Maximum diagnostic stderr characters retained in an error."""

_NEW_PROCESS_GROUP: Final[int] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
"""Windows flag preventing console Ctrl+C from leaking into child processes."""

_MKVMERGE_WARNING_EXIT: Final[int] = 1
"""mkvmerge exit code meaning the result exists but carries warnings."""

_GUI_PROGRESS: Final[re.Pattern[str]] = re.compile(r"^#GUI#progress (\d+)%")
"""mkvmerge --gui-mode progress line."""

_FFMPEG_PROGRESS: Final[re.Pattern[str]] = re.compile(r"^out_time_us=(\d+)")
"""FFmpeg -progress microsecond position line."""

_MP4_COPYABLE_AUDIO: Final[frozenset[str]] = frozenset(
    {"aac", "eac3", "ac3", "mp3", "opus", "flac"},
)
"""FFprobe audio codec names that mux into MP4 without re-encoding."""

_POLISH_LANGUAGE: Final[str] = "pol"
"""BCP 47 language assigned to every track this application adds."""

NARRATION_TRACK_NAME: Final[str] = "Lektor PL"
"""Track name carried by the narration audio in every merged container."""

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """Captured result of one streamed external process."""

    command: tuple[str, ...]
    returncode: int
    stderr: str
    had_warnings: bool


type ProgressReader = Callable[[str], int | None]
"""Translate one output line into a percentage, or ``None`` when irrelevant."""


def merge_command(
    plan: CompositionPlan,
    *,
    mkvmerge: Path,
    destination: Path,
) -> tuple[str, ...]:
    """Build the mkvmerge invocation adding lector and subtitle tracks.

    Original tracks, attachments, chapters, and tags are copied by default, so
    only the appended files carry explicit metadata. No ``--track-order`` is
    passed: mkvmerge lays files out in command order, which already puts every
    appended track after the whole source. Naming only the added tracks would
    instead push the source's own audio and subtitles behind them.
    """
    arguments: list[str] = [
        str(mkvmerge),
        "--gui-mode",
        "--output",
        str(destination),
        str(plan.source_path),
    ]
    if plan.narration_audio is not None:
        arguments.extend(_appended_track_arguments(NARRATION_TRACK_NAME, plan.narration_audio))
    for subtitle in plan.subtitles:
        arguments.extend(_appended_track_arguments(subtitle.track_name, subtitle.path))
    return tuple(arguments)


def _appended_track_arguments(track_name: str, path: Path) -> tuple[str, ...]:
    """Return per-track options plus the file they apply to."""
    return (
        "--language",
        f"0:{_POLISH_LANGUAGE}",
        "--track-name",
        f"0:{track_name}",
        "--default-track-flag",
        "0:no",
        "--forced-display-flag",
        "0:no",
        str(path),
    )


def burn_command(
    plan: CompositionPlan,
    *,
    ffmpeg: Path,
    config: CompositionConfig,
    subtitle_argument: str | None,
    audio_codec: str,
    destination: Path,
) -> tuple[str, ...]:
    """Build the FFmpeg invocation rendering one MP4.

    The picture is always re-encoded when a subtitle filter is present; a copy
    of the video stream is impossible while libass composites frames.
    ``audio_codec`` describes the stream actually mapped into the result — the
    narration sidecar when one exists, otherwise the source's own audio.
    """
    arguments: list[str] = [str(ffmpeg), "-y", "-hide_banner", "-nostats"]
    arguments.extend(("-i", str(plan.source_path)))
    if plan.narration_audio is not None:
        arguments.extend(("-i", str(plan.narration_audio)))
        arguments.extend(("-map", "0:v:0", "-map", "1:a:0"))
    else:
        arguments.extend(("-map", "0:v:0", "-map", "0:a:0?"))
    if subtitle_argument is not None:
        arguments.extend(("-vf", subtitle_argument))
        arguments.extend(("-c:v", config.video_encoder))
        arguments.extend(("-crf", str(config.crf)))
        arguments.extend(("-preset", config.encoder_preset))
        arguments.extend(("-pix_fmt", "yuv420p"))
    else:
        arguments.extend(("-c:v", "copy"))
    audio_arguments: tuple[str, ...] = ("-c:a", "copy") if mp4_audio_is_copyable(audio_codec) else ("-c:a", "aac")
    arguments.extend(audio_arguments)
    arguments.extend(("-movflags", "+faststart"))
    arguments.extend(("-progress", "pipe:1"))
    arguments.append(str(destination))
    return tuple(arguments)


def subtitle_filter_argument(
    subtitle: Path,
    *,
    kind: str,
    fonts_dir: Path | None = None,
) -> str:
    """Return the ``-vf`` value rendering one subtitle file.

    ``ass`` preserves every V4+ style verbatim; ``subtitles`` is used only for
    SRT, which libass renders with its default style.
    """
    filter_name: str = "ass" if kind == "ass" else "subtitles"
    value: str = f"{filter_name}={escape_filter_path(subtitle)}"
    if fonts_dir is not None:
        value = f"{value}:fontsdir={escape_filter_path(fonts_dir)}"
    return value


def mp4_audio_is_copyable(codec: str) -> bool:
    """Return whether an FFprobe audio codec muxes into MP4 as is."""
    return codec.casefold() in _MP4_COPYABLE_AUDIO


def parse_mkvmerge_progress(line: str) -> int | None:
    """Return the percentage reported by one ``--gui-mode`` line."""
    match: re.Match[str] | None = _GUI_PROGRESS.match(line.strip())
    return int(match.group(1)) if match is not None else None


def parse_ffmpeg_progress(line: str, *, total_us: int) -> int | None:
    """Return the percentage derived from one ``-progress`` line."""
    match: re.Match[str] | None = _FFMPEG_PROGRESS.match(line.strip())
    if match is None or total_us <= 0:
        return None
    position_us: int = int(match.group(1))
    return min(100, round(position_us * 100 / total_us))


class StreamingRunner:
    """Run one external process while reporting progress line by line."""

    def __init__(self, *, shutdown_grace_s: float = 5.0) -> None:
        """Store the grace period applied before a hard kill."""
        self._shutdown_grace_s: float = shutdown_grace_s

    def run(
        self,
        command: Sequence[str],
        *,
        operation: str,
        timeout_s: float,
        progress: ProgressReader | None = None,
        on_percent: Callable[[int], None] | None = None,
        cancel: threading.Event | None = None,
        warning_exit_code: int | None = None,
    ) -> CommandOutcome:
        """Execute one command, streaming stdout and enforcing cancellation.

        Both pipes are drained by daemon threads: a process that stops printing
        still meets its cancellation and timeout checks every poll interval,
        and a noisy stderr never fills its buffer and deadlocks the run.
        """
        timer: Timer = Timer(operation, auto_start=True)
        logger.debug("Composition subprocess starting", operation=operation)
        process: subprocess.Popen[str] = _spawn(command, operation)
        lines: queue.Queue[str | None] = queue.Queue()
        stderr_tail: deque[str] = deque(maxlen=_STDERR_TAIL_LINES)
        _drain(process.stdout, lines.put, done=lambda: lines.put(None))
        _drain(process.stderr, stderr_tail.append)
        last_percent: int = -1
        while True:
            self._guard(process, operation=operation, timer=timer, timeout_s=timeout_s, cancel=cancel)
            try:
                line: str | None = lines.get(timeout=_POLL_SECONDS)
            except queue.Empty:
                continue
            if line is None:
                break
            last_percent = _report(line, progress=progress, on_percent=on_percent, last_percent=last_percent)
        returncode: int = process.wait()
        timer.stop()
        stderr: str = _safe_stderr(stderr_tail)
        had_warnings: bool = warning_exit_code is not None and returncode == warning_exit_code
        if returncode != 0 and not had_warnings:
            _raise_process(operation, returncode, stderr, ErrorCode.COMPOSITION_FAILED)
        logger.info(
            "Composition subprocess completed",
            operation=operation,
            duration_ms=round(timer.duration_ms),
            had_warnings=had_warnings,
        )
        return CommandOutcome(
            command=tuple(command),
            returncode=returncode,
            stderr=stderr,
            had_warnings=had_warnings,
        )

    def _guard(
        self,
        process: subprocess.Popen[str],
        *,
        operation: str,
        timer: Timer,
        timeout_s: float,
        cancel: threading.Event | None,
    ) -> None:
        """Stop the process when cancellation or the time budget demands it."""
        if cancel is not None and cancel.is_set():
            self._stop(process)
            _raise_cancelled(operation)
        if timer.duration_s <= timeout_s:
            return
        self._stop(process)
        _raise_process(operation, None, "operation timed out", ErrorCode.TIMEOUT)

    def _stop(self, process: subprocess.Popen[str]) -> None:
        """Terminate a running process, killing it after the grace period."""
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=self._shutdown_grace_s)
        except subprocess.TimeoutExpired:
            process.kill()


def _spawn(command: Sequence[str], operation: str) -> subprocess.Popen[str]:
    """Start one external process with both pipes captured as text."""
    try:
        return subprocess.Popen(  # noqa: S603
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=_NEW_PROCESS_GROUP,
        )
    except OSError as error:
        _raise_process(operation, None, str(error), ErrorCode.IO_ERROR, cause=error)


def _drain(stream: IO[str] | None, sink: Callable[[str], None], *, done: Callable[[], None] | None = None) -> None:
    """Consume one pipe in a daemon thread so its buffer never fills."""

    def _pump() -> None:
        for line in stream or ():
            sink(line)
        if done is not None:
            done()

    threading.Thread(target=_pump, name="composition-pipe", daemon=True).start()


def _report(
    line: str,
    *,
    progress: ProgressReader | None,
    on_percent: Callable[[int], None] | None,
    last_percent: int,
) -> int:
    """Return the percentage after reporting one changed progress line."""
    if progress is None or on_percent is None:
        return last_percent
    percent: int | None = progress(line)
    if percent is None or percent == last_percent:
        return last_percent
    on_percent(percent)
    return percent


def _safe_stderr(lines: Iterable[str]) -> str:
    """Return a short diagnostic tail free of full commands and paths."""
    kept: list[str] = [line.strip() for line in lines if line.strip()]
    return " | ".join(kept)[-_STDERR_TAIL_CHARS:]


def _raise_cancelled(operation: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.CANCELLED,
        message=f"Composition cancelled: {operation}",
        suggestion="Run the file again to assemble it from existing products.",
        details={"operation": operation},
    )
    raise CompositionCancelledError(context=context)


def _raise_process(
    operation: str,
    returncode: int | None,
    stderr: str,
    code: ErrorCode,
    *,
    cause: OSError | None = None,
) -> Never:
    context: ErrorContext = ErrorContext(
        code=code,
        message=f"Composition process failed: {operation}",
        suggestion="Check the source file, free disk space, and the bundled tools.",
        details={"operation": operation, "returncode": returncode, "stderr_tail": stderr},
    )
    error: CompositionProcessError = CompositionProcessError(context=context)
    if cause is not None:
        raise error from cause
    raise error
```

> **Uwaga o `_MKVMERGE_WARNING_EXIT`**: przekazywany do `run(warning_exit_code=...)` przez
> `service.py`, nie używany wewnątrz `commands.py` — stała mieszka tu, bo opisuje kontrakt
> narzędzia.

### 5.2. `tests/services/composition/test_composition_commands.py`

```python
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

from anishift.services.composition.commands import (
    StreamingRunner,
    burn_command,
    merge_command,
    mp4_audio_is_copyable,
    parse_ffmpeg_progress,
    parse_mkvmerge_progress,
    subtitle_filter_argument,
)
from anishift.services.composition.config import CompositionConfig
from anishift.services.composition.errors import (
    CompositionCancelledError,
    CompositionProcessError,
)
from anishift.services.composition.types import (
    AttachedSubtitle,
    CompositionPlan,
    OutputVariant,
    SubtitleRole,
)

_SILENT_SLEEP = "import time; time.sleep(30)"


def _plan(tmp_path: Path, **overrides: object) -> CompositionPlan:
    defaults: dict[str, object] = {
        "source_path": tmp_path / "Episode.mkv",
        "variant": OutputVariant.MERGE,
        "temporary_root": tmp_path / "tmp",
        "destination_dir": tmp_path / "output",
    }
    defaults.update(overrides)
    return CompositionPlan(**defaults)  # type: ignore[arg-type]


def test_merge_command_uses_current_mkvmerge_flag_names(tmp_path: Path) -> None:
    plan = _plan(tmp_path, narration_audio=tmp_path / "Episode.eac3")
    command = merge_command(plan, mkvmerge=Path("mkvmerge"), destination=tmp_path / "out.mkv")

    assert "--default-track-flag" in command
    assert "--forced-display-flag" in command
    assert "--default-track" not in command
    assert "--forced-track" not in command


def test_merge_command_names_the_lector_track(tmp_path: Path) -> None:
    plan = _plan(tmp_path, narration_audio=tmp_path / "Episode.eac3")
    command = merge_command(plan, mkvmerge=Path("mkvmerge"), destination=tmp_path / "out.mkv")

    assert "0:Lektor PL" in command
    assert "0:pol" in command


def test_merge_command_puts_added_files_after_the_source(tmp_path: Path) -> None:
    subtitles = (
        AttachedSubtitle(tmp_path / "full.ass", SubtitleRole.FULL, "pol", "Napisy PL"),
        AttachedSubtitle(tmp_path / "signs.ass", SubtitleRole.DISPLAYED, "pol", "Napisy poboczne PL"),
    )
    plan = _plan(tmp_path, narration_audio=tmp_path / "Episode.eac3", subtitles=subtitles)
    command = merge_command(plan, mkvmerge=Path("mkvmerge"), destination=tmp_path / "out.mkv")

    positions = [command.index(str(path)) for path in (plan.source_path, plan.narration_audio, *[s.path for s in subtitles])]
    assert positions == sorted(positions)


def test_merge_command_never_reorders_source_tracks(tmp_path: Path) -> None:
    plan = _plan(tmp_path, narration_audio=tmp_path / "Episode.eac3")
    command = merge_command(plan, mkvmerge=Path("mkvmerge"), destination=tmp_path / "out.mkv")

    assert "--track-order" not in command


def test_merge_command_without_material_only_copies_source(tmp_path: Path) -> None:
    command = merge_command(_plan(tmp_path), mkvmerge=Path("mkvmerge"), destination=tmp_path / "out.mkv")

    assert "--language" not in command
    assert command[-1] == str(tmp_path / "Episode.mkv")


def test_burn_command_forces_compatibility_flags(tmp_path: Path) -> None:
    plan = _plan(tmp_path, variant=OutputVariant.BURN, burn_subtitle=tmp_path / "signs.ass")
    command = burn_command(
        plan,
        ffmpeg=Path("ffmpeg"),
        config=CompositionConfig(),
        subtitle_argument="ass='signs.ass'",
        audio_codec="eac3",
        destination=tmp_path / "out.mp4",
    )

    assert "-pix_fmt" in command
    assert "yuv420p" in command
    assert "+faststart" in command
    assert "-progress" in command


def test_burn_command_copies_video_without_subtitles(tmp_path: Path) -> None:
    plan = _plan(tmp_path, variant=OutputVariant.BURN, narration_audio=tmp_path / "Episode.eac3")
    command = burn_command(
        plan,
        ffmpeg=Path("ffmpeg"),
        config=CompositionConfig(),
        subtitle_argument=None,
        audio_codec="eac3",
        destination=tmp_path / "out.mp4",
    )

    assert "copy" in command
    assert "-vf" not in command


def test_burn_command_transcodes_unsupported_audio(tmp_path: Path) -> None:
    plan = _plan(tmp_path, variant=OutputVariant.BURN, burn_subtitle=tmp_path / "s.ass")
    command = burn_command(
        plan,
        ffmpeg=Path("ffmpeg"),
        config=CompositionConfig(),
        subtitle_argument="ass='s.ass'",
        audio_codec="dts",
        destination=tmp_path / "out.mp4",
    )

    audio_index = command.index("-c:a")
    assert command[audio_index + 1] == "aac"


@pytest.mark.parametrize(
    ("kind", "expected_prefix"),
    [("ass", "ass="), ("srt", "subtitles=")],
)
def test_subtitle_filter_picks_the_faithful_filter(kind: str, expected_prefix: str) -> None:
    value = subtitle_filter_argument(Path("C:/anime/show.ass"), kind=kind)
    assert value.startswith(expected_prefix)


def test_subtitle_filter_appends_fonts_directory() -> None:
    value = subtitle_filter_argument(Path("C:/a/s.ass"), kind="ass", fonts_dir=Path("C:/a/fonts"))
    assert ":fontsdir=" in value


@pytest.mark.parametrize(
    ("codec", "expected"),
    [("eac3", True), ("aac", True), ("mp3", True), ("dts", False), ("truehd", False), ("", False)],
)
def test_mp4_audio_copy_matrix(codec: str, expected: bool) -> None:
    assert mp4_audio_is_copyable(codec) is expected


def test_parse_mkvmerge_progress_reads_gui_lines() -> None:
    assert parse_mkvmerge_progress("#GUI#progress 42%") == 42
    assert parse_mkvmerge_progress("#GUI#error nope") is None
    assert parse_mkvmerge_progress("Progress: 42%") is None


def test_parse_ffmpeg_progress_scales_against_duration() -> None:
    assert parse_ffmpeg_progress("out_time_us=500000", total_us=1_000_000) == 50
    assert parse_ffmpeg_progress("out_time_us=2000000", total_us=1_000_000) == 100
    assert parse_ffmpeg_progress("speed=1.2x", total_us=1_000_000) is None
    assert parse_ffmpeg_progress("out_time_us=1", total_us=0) is None


def test_streaming_runner_cancels_a_process_that_never_prints() -> None:
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(CompositionCancelledError):
        StreamingRunner(shutdown_grace_s=1.0).run(
            (sys.executable, "-c", _SILENT_SLEEP),
            operation="merge",
            timeout_s=30.0,
            cancel=cancel,
        )


def test_streaming_runner_times_out_a_process_that_never_prints() -> None:
    with pytest.raises(CompositionProcessError):
        StreamingRunner(shutdown_grace_s=1.0).run(
            (sys.executable, "-c", _SILENT_SLEEP),
            operation="burn",
            timeout_s=0.5,
        )
```

> Oba testy uruchamiają `sys.executable` z `_SILENT_SLEEP = "import time; time.sleep(30)"` — proces,
> który nie pisze na stdout. W poprzedniej wersji runnera (pętla `for line in stdout`) obie ścieżki
> wisiałyby 30 s, bo anulowanie i timeout sprawdzało się wyłącznie przy nadejściu linii.

**Weryfikacja kroku 3:**

```bash
uv run pytest tests/services/composition/test_composition_commands.py -v
```

---

## 6. Krok 4 — probe i walidacja

### 6.1. `anishift/services/composition/probe.py`

```python
"""Source identification and validation of produced containers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.composition.errors import (
    CompositionProcessError,
    CompositionValidationError,
)
from anishift.services.extraction.service import identify
from anishift.services.extraction.types import MediaInfo

__all__ = [
    "audio_codec_name",
    "source_duration_us",
    "source_tracks",
    "validate_burned",
    "validate_merged",
]

# ── Constants ────────────────────────────────────────────────────────────────

_DURATION_TOLERANCE_MS: Final[int] = 2_000
"""Accepted difference between source and rendered duration."""

_PROBE_TIMEOUT_S: Final[float] = 120.0
"""Timeout for one ffprobe invocation."""

_NEW_PROCESS_GROUP: Final[int] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
"""Windows flag preventing console Ctrl+C from leaking into child processes."""


def source_tracks(path: Path) -> MediaInfo:
    """Return the current track layout of one container.

    Identification runs immediately before assembling, so the result reflects
    the file on disk rather than a snapshot from an earlier stage.
    """
    return identify(path)


def audio_codec_name(path: Path, *, ffprobe: Path) -> str:
    """Return the codec name of a file's first audio stream.

    The name comes from the file that is actually mapped into the render — the
    narration sidecar when one exists — so the copy-or-transcode decision is
    never taken from a different stream.
    """
    payload: dict[str, Any] = _probe_json(
        path,
        ffprobe=ffprobe,
        arguments=("-select_streams", "a:0", "-show_entries", "stream=codec_name"),
    )
    streams: object = payload.get("streams", [])
    if not isinstance(streams, list) or not streams:
        return ""
    first: object = streams[0]
    name: object = first.get("codec_name") if isinstance(first, dict) else None
    return name if isinstance(name, str) else ""


def source_duration_us(path: Path, *, ffprobe: Path) -> int:
    """Return the container duration in microseconds."""
    payload: dict[str, Any] = _probe_json(
        path,
        ffprobe=ffprobe,
        arguments=("-show_entries", "format=duration"),
    )
    raw: object = payload.get("format", {}).get("duration")
    if not isinstance(raw, str):
        return 0
    try:
        seconds: float = float(raw)
    except ValueError:
        return 0
    return max(0, round(seconds * 1_000_000))


def validate_merged(path: Path, *, expected_track_names: tuple[str, ...]) -> None:
    """Confirm a merged container carries every track this run appended.

    Track names are checked instead of counting Polish tracks: a source that
    was already Polish would satisfy a count on its own, so a merge that added
    nothing would pass unnoticed.
    """
    _require_non_empty(path)
    info: MediaInfo = identify(path)
    present: frozenset[str] = frozenset(track.name for track in info.tracks)
    missing: tuple[str, ...] = tuple(name for name in expected_track_names if name not in present)
    if missing:
        _raise_validation(
            "Merged container is missing appended tracks",
            details={"expected": len(expected_track_names), "missing": len(missing)},
        )


def validate_burned(path: Path, *, expected_duration_us: int, ffprobe: Path) -> None:
    """Confirm a rendered MP4 decodes and matches the source duration."""
    _require_non_empty(path)
    payload: dict[str, Any] = _probe_json(
        path,
        ffprobe=ffprobe,
        arguments=("-show_entries", "format=duration:stream=codec_type"),
    )
    streams: object = payload.get("streams", [])
    if not isinstance(streams, list) or not any(
        isinstance(stream, dict) and stream.get("codec_type") == "video" for stream in streams
    ):
        _raise_validation("Rendered file carries no video stream", details={})
    if expected_duration_us <= 0:
        return
    actual_us: int = source_duration_us(path, ffprobe=ffprobe)
    drift_ms: int = abs(actual_us - expected_duration_us) // 1_000
    if drift_ms > _DURATION_TOLERANCE_MS:
        _raise_validation(
            "Rendered duration does not match the source",
            details={"drift_ms": drift_ms},
        )


def _require_non_empty(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        _raise_validation("Composed file is missing or empty", details={"name": path.name})


def _probe_json(path: Path, *, ffprobe: Path, arguments: tuple[str, ...]) -> dict[str, Any]:
    command: tuple[str, ...] = (
        str(ffprobe),
        "-v",
        "error",
        "-of",
        "json",
        *arguments,
        str(path),
    )
    try:
        completed: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603
            list(command),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PROBE_TIMEOUT_S,
            check=True,
            creationflags=_NEW_PROCESS_GROUP,
        )
    except (subprocess.SubprocessError, OSError) as error:
        _raise_probe("ffprobe failed to read the composed file", cause=error)
    try:
        payload: Any = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        _raise_probe("ffprobe returned malformed JSON", cause=error)
    return payload if isinstance(payload, dict) else {}


def _raise_probe(message: str, *, cause: Exception) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.COMPOSITION_FAILED,
        message=message,
        suggestion="Check the produced file and the bundled FFprobe binary.",
        details={"operation": "composition_probe"},
    )
    raise CompositionProcessError(context=context) from cause


def _raise_validation(message: str, *, details: dict[str, Any]) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.COMPOSITION_FAILED,
        message=message,
        suggestion="Re-run composition; the previous result was not published.",
        details={"operation": "composition_validation", **details},
    )
    raise CompositionValidationError(context=context)
```

### 6.2. `tests/services/composition/test_composition_probe.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from anishift.services.composition.errors import CompositionValidationError
from anishift.services.composition.probe import validate_merged


def test_validate_merged_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CompositionValidationError, match="missing or empty"):
        validate_merged(tmp_path / "absent.mkv", expected_track_names=("Napisy PL",))


def test_validate_merged_rejects_empty_file(tmp_path: Path) -> None:
    target = tmp_path / "empty.mkv"
    target.write_bytes(b"")

    with pytest.raises(CompositionValidationError, match="missing or empty"):
        validate_merged(target, expected_track_names=("Napisy PL",))
```

**Weryfikacja kroku 4** — dodatkowo **dowód wymagany w §4.2 wymagań**:

```bash
uv run pytest tests/services/composition/test_composition_probe.py -v
uv run python -c "
from pathlib import Path; from anishift.utils.timer import Timer
from anishift.services.composition.probe import source_tracks
mkv = sorted(Path('workspace').glob('*.mkv'), key=lambda p: p.stat().st_size)[-1]
t = Timer('identify', auto_start=True); info = source_tracks(mkv); t.stop()
print(f'{mkv.stat().st_size/1e9:.2f} GB -> {t.duration_ms:.0f} ms, {len(info.tracks)} tracks')
"
```

Oczekiwane: czas `identify` rzędu setek milisekund — dowód, że wołanie go per plik jest tanie.

---

## 7. Krok 5 — czcionki

### 7.1. `anishift/services/composition/fonts.py`

```python
"""Detect ASS font references missing from a container's attachments."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

__all__ = ["attachment_font_names", "font_names", "missing_fonts"]

# ── Constants ────────────────────────────────────────────────────────────────

_STYLE_LINE: Final[re.Pattern[str]] = re.compile(r"^Style:\s*([^,]*),([^,]*),", re.MULTILINE)
"""V4+ style line whose second field carries the font name."""

_INLINE_FONT: Final[re.Pattern[str]] = re.compile(r"\\fn([^\\}]+)")
"""Inline font override inside an event's override block."""

_FONT_SUFFIXES: Final[frozenset[str]] = frozenset({".ttf", ".otf", ".ttc", ".woff", ".woff2"})
"""Attachment extensions treated as fonts."""


def font_names(subtitle: Path) -> frozenset[str]:
    """Return every font referenced by styles and inline overrides."""
    try:
        text: str = subtitle.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return frozenset()
    names: set[str] = {match.group(2).strip() for match in _STYLE_LINE.finditer(text)}
    names.update(match.group(1).strip() for match in _INLINE_FONT.finditer(text))
    return frozenset(name.lstrip("@") for name in names if name)


def attachment_font_names(attachment_names: tuple[str, ...]) -> frozenset[str]:
    """Return normalized font names available as container attachments."""
    return frozenset(
        Path(name).stem.casefold() for name in attachment_names if Path(name).suffix.casefold() in _FONT_SUFFIXES
    )


def missing_fonts(subtitle: Path, available: frozenset[str]) -> tuple[str, ...]:
    """Return referenced fonts absent from the available set, sorted."""
    referenced: frozenset[str] = font_names(subtitle)
    missing: set[str] = {name for name in referenced if name.casefold() not in available}
    return tuple(sorted(missing))
```

### 7.2. `anishift/services/extraction/types.py` — diff

`mkvmerge -J` zwraca załączniki w polu `attachments`, którego dzisiejszy `MediaInfo` nie niesie.
Zmiana jest addytywna, z domyślną pustą krotką, więc żaden istniejący konstruktor się nie psuje.

```diff
 @dataclass(frozen=True, slots=True)
 class MediaInfo:
     """Identified MKV container."""

     path: Path
     tracks: tuple[TrackInfo, ...]
+    attachments: tuple[str, ...] = ()
```

### 7.3. `anishift/services/extraction/service.py` — diff

```diff
         tracks = tuple(_parse_track(track) for track in raw["tracks"])
+        attachments = tuple(
+            str(attachment.get("file_name", "")) for attachment in raw.get("attachments", [])
+        )
     except KeyError as exc:
```

```diff
-    return MediaInfo(path=path, tracks=tuple(sorted(tracks, key=lambda track: track.id)))
+    return MediaInfo(
+        path=path,
+        tracks=tuple(sorted(tracks, key=lambda track: track.id)),
+        attachments=tuple(name for name in attachments if name),
+    )
```

Test do dołożenia w `tests/services/extraction/`: payload `mkvmerge -J` z sekcją `attachments`
daje nazwy plików czcionek, a payload bez tej sekcji daje pustą krotkę.

### 7.4. `tests/services/composition/test_composition_fonts.py`

```python
from __future__ import annotations

from pathlib import Path

from anishift.services.composition.fonts import attachment_font_names, font_names, missing_fonts

_ASS = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Open Sans Semibold,45
Style: Signs,Trebuchet MS,40

[Events]
Format: Layer, Start, End, Style, Text
Dialogue: 0,0:00:01.00,0:00:02.00,Default,{\\fnComic Sans MS}Hello
"""


def test_font_names_reads_styles_and_inline_overrides(tmp_path: Path) -> None:
    subtitle = tmp_path / "episode.ass"
    subtitle.write_text(_ASS, encoding="utf-8")

    names = font_names(subtitle)

    assert "Open Sans Semibold" in names
    assert "Trebuchet MS" in names
    assert "Comic Sans MS" in names


def test_font_names_survives_unreadable_file(tmp_path: Path) -> None:
    assert font_names(tmp_path / "absent.ass") == frozenset()


def test_attachment_font_names_keeps_only_fonts() -> None:
    names = attachment_font_names(("OpenSans-Semibold.ttf", "cover.jpg", "Trebuchet.otf"))

    assert names == frozenset({"opensans-semibold", "trebuchet"})


def test_missing_fonts_reports_only_absent_ones(tmp_path: Path) -> None:
    subtitle = tmp_path / "episode.ass"
    subtitle.write_text(_ASS, encoding="utf-8")

    missing = missing_fonts(subtitle, frozenset({"open sans semibold"}))

    assert "Trebuchet MS" in missing
    assert "Open Sans Semibold" not in missing
```

**Weryfikacja kroku 5:**

```bash
uv run pytest tests/services/composition/test_composition_fonts.py -v
uv run python -c "
from pathlib import Path
from anishift.services.composition.fonts import font_names
ass = sorted(Path('workspace').glob('*.pl.ass'))[0]
print(ass.name, '->', sorted(font_names(ass)))
"
```

Oczekiwane: realne nazwy czcionek z produktu pipeline'u.

---

## 8. Krok 6 — fasada domeny

### 8.1. `anishift/services/composition/service.py`

```python
"""Synchronous facade assembling pipeline products into one finished file."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Final, Protocol

from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.binaries import Binary, BinaryNotFoundError, require_binary
from anishift.services.composition.commands import (
    NARRATION_TRACK_NAME,
    StreamingRunner,
    burn_command,
    merge_command,
    parse_ffmpeg_progress,
    parse_mkvmerge_progress,
    subtitle_filter_argument,
)
from anishift.services.composition.config import CompositionConfig
from anishift.services.composition.errors import CompositionConfigError
from anishift.services.composition.fonts import attachment_font_names, missing_fonts
from anishift.services.composition.paths import filter_safe_copy, output_path, temporary_sibling
from anishift.services.composition.probe import (
    audio_codec_name,
    source_duration_us,
    source_tracks,
    validate_burned,
    validate_merged,
)
from anishift.services.composition.types import (
    CompositionPlan,
    CompositionResult,
    CompositionStatus,
    OutputVariant,
)
from anishift.services.extraction.types import MediaInfo
from anishift.utils.logger import get_logger
from anishift.utils.safe_fs import safe_move
from anishift.utils.timer import Timer

__all__ = ["CompositionProgressSink", "CompositionService"]

# ── Constants ────────────────────────────────────────────────────────────────

_MKVMERGE_WARNING_EXIT: Final[int] = 1
"""mkvmerge exit code meaning the result exists but carries warnings."""

logger = get_logger(__name__)


class CompositionProgressSink(Protocol):
    """Optional phase callback owned and rendered by the pipeline."""

    def on_composition_phase(self, scope_id: str, phase: str, percent: int) -> None:
        """Report one composition phase without rendering UI."""
        ...


class CompositionService:
    """Assemble one source container into the requested final artifact."""

    def __init__(
        self,
        config: CompositionConfig,
        *,
        runner: StreamingRunner | None = None,
        mkvmerge: Path | None = None,
        ffmpeg: Path | None = None,
        ffprobe: Path | None = None,
    ) -> None:
        """Resolve external tools eagerly so a missing binary fails early."""
        self._config: CompositionConfig = config
        self._runner: StreamingRunner = runner or StreamingRunner(
            shutdown_grace_s=config.shutdown_grace_s,
        )
        try:
            self._mkvmerge: Path = mkvmerge or require_binary(Binary.MKVMERGE)
            self._ffmpeg: Path = ffmpeg or require_binary(Binary.FFMPEG)
            self._ffprobe: Path = ffprobe or require_binary(Binary.FFPROBE)
        except BinaryNotFoundError as error:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.BINARY_NOT_FOUND,
                message="Composition requires MKVToolNix and FFmpeg",
                suggestion="Run `anishift setup` to install the external tools.",
                details={"operation": "composition_config"},
            )
            raise CompositionConfigError(context=context) from error

    @property
    def ffprobe(self) -> Path:
        """Return the resolved FFprobe binary, reused for pre-run estimates."""
        return self._ffprobe

    def compose(
        self,
        plan: CompositionPlan,
        *,
        callbacks: CompositionProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> CompositionResult:
        """Produce the artifact described by ``plan`` and validate it."""
        timer: Timer = Timer("composition", auto_start=True)
        logger.info(
            "Composition started",
            scope_id=plan.scope_id,
            variant=plan.variant.value,
            has_narration=plan.narration_audio is not None,
            subtitle_count=len(plan.subtitles),
        )
        if plan.variant is OutputVariant.PLAYERS:
            return self._compose_players(plan, timer=timer)
        if not plan.has_material:
            logger.info("Composition skipped", scope_id=plan.scope_id, reason="nothing_to_add")
            return CompositionResult(
                source_path=plan.source_path,
                variant=plan.variant,
                status=CompositionStatus.SKIPPED_NOTHING_TO_ADD,
                duration_ms=timer.duration_ms,
            )
        if plan.variant is OutputVariant.MERGE:
            return self._compose_merge(plan, timer=timer, callbacks=callbacks, cancel=cancel)
        return self._compose_burn(plan, timer=timer, callbacks=callbacks, cancel=cancel)

    def _compose_players(self, plan: CompositionPlan, *, timer: Timer) -> CompositionResult:
        """Gather every product next to the source so players pair them."""
        destination: Path = plan.source_path.parent
        moved: list[Path] = []
        sources: list[Path] = [subtitle.path for subtitle in plan.subtitles]
        if plan.narration_audio is not None:
            sources.append(plan.narration_audio)
        for product in sources:
            if product.parent == destination or not product.is_file():
                continue
            moved.append(safe_move(product, destination / product.name))
        timer.stop()
        logger.info("Composition completed", scope_id=plan.scope_id, variant="players", moved=len(moved))
        return CompositionResult(
            source_path=plan.source_path,
            variant=plan.variant,
            status=CompositionStatus.COMPLETED,
            output_path=destination,
            duration_ms=timer.duration_ms,
            moved_paths=tuple(moved),
        )

    def _compose_merge(
        self,
        plan: CompositionPlan,
        *,
        timer: Timer,
        callbacks: CompositionProgressSink | None,
        cancel: threading.Event | None,
    ) -> CompositionResult:
        """Mux the lector and subtitle tracks into a new container."""
        destination: Path = output_path(plan.source_path, plan.variant, plan.destination_dir)
        temporary: Path = temporary_sibling(destination)
        info: MediaInfo = source_tracks(plan.source_path)
        expected: tuple[str, ...] = _appended_track_names(plan)
        warnings: tuple[str, ...] = self._font_warnings(plan, info)
        try:
            outcome = self._runner.run(
                merge_command(plan, mkvmerge=self._mkvmerge, destination=temporary),
                operation="merge",
                timeout_s=self._config.operation_timeout_s,
                progress=parse_mkvmerge_progress,
                on_percent=lambda percent: _notify(callbacks, plan.scope_id, "merging", percent),
                cancel=cancel,
                warning_exit_code=_MKVMERGE_WARNING_EXIT,
            )
            validate_merged(temporary, expected_track_names=expected)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        timer.stop()
        if outcome.had_warnings:
            warnings = (*warnings, "mkvmerge reported warnings")
        logger.info(
            "Composition completed",
            scope_id=plan.scope_id,
            variant="merge",
            added_tracks=len(expected),
            duration_ms=round(timer.duration_ms),
        )
        return CompositionResult(
            source_path=plan.source_path,
            variant=plan.variant,
            status=CompositionStatus.COMPLETED,
            output_path=destination,
            output_size_bytes=destination.stat().st_size,
            source_size_bytes=plan.source_path.stat().st_size,
            duration_ms=timer.duration_ms,
            warnings=warnings,
        )

    def _compose_burn(
        self,
        plan: CompositionPlan,
        *,
        timer: Timer,
        callbacks: CompositionProgressSink | None,
        cancel: threading.Event | None,
    ) -> CompositionResult:
        """Render an MP4 with the subtitles composited into the picture."""
        destination: Path = output_path(plan.source_path, plan.variant, plan.destination_dir)
        temporary: Path = temporary_sibling(destination)
        info: MediaInfo = source_tracks(plan.source_path)
        total_us: int = source_duration_us(plan.source_path, ffprobe=self._ffprobe)
        subtitle_argument: str | None = self._burn_filter(plan)
        warnings: tuple[str, ...] = self._font_warnings(plan, info)
        audio_source: Path = plan.narration_audio or plan.source_path
        try:
            self._runner.run(
                burn_command(
                    plan,
                    ffmpeg=self._ffmpeg,
                    config=self._config,
                    subtitle_argument=subtitle_argument,
                    audio_codec=audio_codec_name(audio_source, ffprobe=self._ffprobe),
                    destination=temporary,
                ),
                operation="burn",
                timeout_s=self._config.render_timeout_s,
                progress=lambda line: parse_ffmpeg_progress(line, total_us=total_us),
                on_percent=lambda percent: _notify(callbacks, plan.scope_id, "burning", percent),
                cancel=cancel,
            )
            validate_burned(temporary, expected_duration_us=total_us, ffprobe=self._ffprobe)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        timer.stop()
        output_size: int = destination.stat().st_size
        source_size: int = plan.source_path.stat().st_size
        if source_size > 0 and output_size > source_size * self._config.size_budget_ratio:
            warnings = (*warnings, "rendered file is larger than the source; consider a smaller preset")
        logger.info(
            "Composition completed",
            scope_id=plan.scope_id,
            variant="burn",
            duration_ms=round(timer.duration_ms),
            size_ratio=round(output_size / source_size, 2) if source_size else 0,
        )
        return CompositionResult(
            source_path=plan.source_path,
            variant=plan.variant,
            status=CompositionStatus.COMPLETED,
            output_path=destination,
            output_size_bytes=output_size,
            source_size_bytes=source_size,
            duration_ms=timer.duration_ms,
            warnings=warnings,
        )

    def _burn_filter(self, plan: CompositionPlan) -> str | None:
        """Return the subtitle filter value, copying the file when needed."""
        if plan.burn_subtitle is None:
            return None
        work_dir: Path = plan.temporary_root / "composition"
        safe_subtitle: Path = filter_safe_copy(plan.burn_subtitle, work_dir)
        return subtitle_filter_argument(safe_subtitle, kind=plan.source_subtitle_kind)

    def _font_warnings(self, plan: CompositionPlan, info: MediaInfo) -> tuple[str, ...]:
        """Return one warning per font referenced but not attached."""
        subtitle: Path | None = plan.burn_subtitle or (plan.subtitles[0].path if plan.subtitles else None)
        if subtitle is None:
            return ()
        available: frozenset[str] = attachment_font_names(info.attachments)
        missing: tuple[str, ...] = missing_fonts(subtitle, available)
        if not missing:
            return ()
        logger.warning("Composition font missing", scope_id=plan.scope_id, font_count=len(missing))
        return tuple(f"font not embedded: {name}" for name in missing)


def _appended_track_names(plan: CompositionPlan) -> tuple[str, ...]:
    """Return the track names this run adds to the merged container."""
    names: list[str] = [subtitle.track_name for subtitle in plan.subtitles]
    if plan.narration_audio is not None:
        names.append(NARRATION_TRACK_NAME)
    return tuple(names)


def _notify(callbacks: CompositionProgressSink | None, scope_id: str, phase: str, percent: int) -> None:
    """Report progress without letting an observer break composition."""
    if callbacks is None:
        return
    try:
        callbacks.on_composition_phase(scope_id, phase, percent)
    except Exception:  # noqa: BLE001 - observers never own composition execution
        logger.warning("Composition progress observer failed", scope_id=scope_id, phase=phase)
```

> **Uwaga o trybie `players`**: `discover_inputs` czyta wyłącznie korzeń `workspace/`
> (`root.iterdir()`), więc katalog źródła i korzeń workspace to dziś ten sam katalog — pętla
> przenoszenia zwykle nie ma czego przenosić i kończy się zerem ruchów. Kod zostaje, bo domyka
> kontrakt z §6.1 wymagań („wszystkie produkty w jednym katalogu obok filmu") i zadziała, gdy
> wykrywanie wejść kiedyś zejdzie do podkatalogów. `safe_move` nadpisuje istniejący cel, więc
> powtórny przebieg tego samego odcinka nie wywala się na kolizji.

### 8.2. `tests/services/composition/test_composition_service.py`

```python
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from anishift.services.composition.commands import CommandOutcome
from anishift.services.composition.config import CompositionConfig
from anishift.services.composition.errors import CompositionValidationError
from anishift.services.composition.service import CompositionService, _notify
from anishift.services.composition.types import (
    AttachedSubtitle,
    CompositionPlan,
    CompositionStatus,
    OutputVariant,
    SubtitleRole,
)


class _FakeRunner:
    def __init__(self, *, produces: Path | None = None, payload: bytes = b"result") -> None:
        self._produces = produces
        self._payload = payload
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: Any, **kwargs: Any) -> CommandOutcome:
        self.commands.append(tuple(command))
        if self._produces is not None:
            self._produces.write_bytes(self._payload)
        return CommandOutcome(command=tuple(command), returncode=0, stderr="", had_warnings=False)


class _FailingRunner:
    def run(self, command: Any, **kwargs: Any) -> CommandOutcome:
        raise CompositionValidationError("merge failed")


def _service(runner: Any, tmp_path: Path) -> CompositionService:
    return CompositionService(
        CompositionConfig(),
        runner=runner,
        mkvmerge=tmp_path / "mkvmerge.exe",
        ffmpeg=tmp_path / "ffmpeg.exe",
        ffprobe=tmp_path / "ffprobe.exe",
    )


def test_compose_without_material_is_skipped(tmp_path: Path) -> None:
    plan = CompositionPlan(
        source_path=tmp_path / "Episode.mkv",
        variant=OutputVariant.MERGE,
        destination_dir=tmp_path / "output",
    )

    result = _service(_FakeRunner(), tmp_path).compose(plan)

    assert result.status is CompositionStatus.SKIPPED_NOTHING_TO_ADD
    assert result.output_path is None


def test_failed_merge_keeps_inputs_and_source(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    source.write_bytes(b"source")
    lector = tmp_path / "Episode.eac3"
    lector.write_bytes(b"audio")
    plan = CompositionPlan(
        source_path=source,
        variant=OutputVariant.MERGE,
        narration_audio=lector,
        destination_dir=tmp_path / "output",
    )

    with pytest.raises(CompositionValidationError):
        _service(_FailingRunner(), tmp_path).compose(plan)

    assert source.read_bytes() == b"source"
    assert lector.read_bytes() == b"audio"
    assert not list((tmp_path / "output").glob("*.mkv")) if (tmp_path / "output").exists() else True


def test_players_moves_products_next_to_source(tmp_path: Path) -> None:
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    source = media_dir / "Episode.mkv"
    source.write_bytes(b"source")
    subtitle = tmp_path / "Episode.pl.ass"
    subtitle.write_text("[Script Info]", encoding="utf-8")
    plan = CompositionPlan(
        source_path=source,
        variant=OutputVariant.PLAYERS,
        subtitles=(AttachedSubtitle(subtitle, SubtitleRole.FULL, "pol", "Napisy PL"),),
    )

    result = _service(_FakeRunner(), tmp_path).compose(plan)

    assert result.status is CompositionStatus.COMPLETED
    assert (media_dir / "Episode.pl.ass").is_file()


def test_progress_observer_failure_is_contained() -> None:
    class _Throwing:
        def __init__(self) -> None:
            self.calls = 0

        def on_composition_phase(self, scope_id: str, phase: str, percent: int) -> None:
            self.calls += 1
            raise RuntimeError("renderer unavailable")

    sink = _Throwing()

    _notify(sink, "scope", "merging", 50)

    assert sink.calls == 1
```

**Weryfikacja kroku 6:**

```bash
uv run pytest tests/services/composition/test_composition_service.py -v
```

Krytyczne: `test_failed_merge_keeps_inputs_and_source` — to bezpośrednia naprawa defektu
ze starego kodu (§4.8 wymagań).

---

## 9. Krok 7 — testy na realnych binarkach

### 9.1. `tests/services/composition/test_composition_real.py`

```python
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.composition.commands import StreamingRunner
from anishift.services.composition.config import CompositionConfig
from anishift.services.composition.probe import validate_merged
from anishift.services.composition.service import CompositionService
from anishift.services.composition.types import (
    AttachedSubtitle,
    CompositionPlan,
    CompositionStatus,
    OutputVariant,
    SubtitleRole,
)
from anishift.services.extraction.service import identify

FFMPEG = resolve_binary(Binary.FFMPEG)
MKVMERGE = resolve_binary(Binary.MKVMERGE)
FFPROBE = resolve_binary(Binary.FFPROBE)

_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, Bold, Alignment, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,0,2,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.20,0:00:01.50,Default,,0,0,0,,Zażółć gęślą jaźń
"""


def _sample_video(path: Path) -> None:
    subprocess.run(
        [
            str(FFMPEG), "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path),
        ],
        check=True,
        capture_output=True,
    )


@pytest.mark.skipif(FFMPEG is None or MKVMERGE is None, reason="bundled tools are unavailable")
def test_merge_keeps_attachments_and_adds_tracks(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    _sample_video(source)
    subtitle = tmp_path / "Episode.pl.ass"
    subtitle.write_text(_ASS, encoding="utf-8")
    plan = CompositionPlan(
        source_path=source,
        variant=OutputVariant.MERGE,
        subtitles=(AttachedSubtitle(subtitle, SubtitleRole.FULL, "pol", "Napisy PL"),),
        destination_dir=tmp_path / "output",
        temporary_root=tmp_path / "tmp",
    )
    service = CompositionService(CompositionConfig(), runner=StreamingRunner())

    result = service.compose(plan)

    assert result.status is CompositionStatus.COMPLETED
    assert result.output_path is not None
    validate_merged(result.output_path, expected_track_names=("Napisy PL",))
    merged = identify(result.output_path)
    assert merged.tracks[-1].name == "Napisy PL"
    assert [track.type for track in merged.tracks[:2]] == ["video", "audio"]


@pytest.mark.skipif(FFMPEG is None or FFPROBE is None, reason="bundled tools are unavailable")
def test_burn_handles_difficult_path_characters(tmp_path: Path) -> None:
    media_dir = tmp_path / "dir with spaces [1080p]"
    media_dir.mkdir()
    source = media_dir / "Zażółć - 04.mkv"
    _sample_video(source)
    subtitle = media_dir / "Heroine's episode.pl.ass"
    subtitle.write_text(_ASS, encoding="utf-8")
    plan = CompositionPlan(
        source_path=source,
        variant=OutputVariant.BURN,
        burn_subtitle=subtitle,
        destination_dir=tmp_path / "output",
        temporary_root=tmp_path / "tmp",
    )
    service = CompositionService(CompositionConfig(), runner=StreamingRunner())

    result = service.compose(plan)

    assert result.status is CompositionStatus.COMPLETED
    assert result.output_path is not None
    assert result.output_path.stat().st_size > 0
```

**Weryfikacja kroku 7:**

```bash
uv run pytest tests/services/composition/test_composition_real.py -v
```

Krytyczne: drugi test przechodzi przez apostrof w nazwie napisów, spacje i nawiasy w katalogu
oraz polskie znaki — czyli dokładnie to, co jest w Twoim `workspace/`.

---

## 10. Krok 8 — adapter pipeline (macierz decyzji i pętla składania)

Ten krok zaczyna się od zmian w `anishift/pipeline/types.py` — nowych pól `FileOutcome`,
liczników w `PipelineReport` i protokołu `CompositionUi`. Diffy są w §11.1; kod poniżej ich
używa, więc muszą wejść pierwsze.

### 10.1. `anishift/pipeline/composition_runtime.py`

```python
"""Translate file outcomes into composition plans and assemble them."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from anishift.errors import AniShiftError, ErrorCode
from anishift.pipeline.narration import scope_id_for_source
from anishift.pipeline.types import CompositionUi, FileOutcome
from anishift.services.composition.probe import source_duration_us
from anishift.services.composition.service import CompositionService
from anishift.services.composition.types import (
    AttachedSubtitle,
    CompositionPlan,
    CompositionResult,
    CompositionStatus,
    OutputVariant,
    SubtitleRole,
)
from anishift.utils.logger import get_logger
from anishift.utils.safe_fs import safe_rmtree

__all__ = ["BurnEstimate", "build_plan", "compose_outcomes", "estimate_burn_cost"]

# ── Constants ────────────────────────────────────────────────────────────────

_FULL_TRACK_NAME: Final[str] = "Napisy PL"
"""Track name for the complete Polish subtitle stream."""

_DISPLAYED_TRACK_NAME: Final[str] = "Napisy poboczne PL"
"""Track name for on-screen signs and notes."""

_POLISH_LANGUAGE: Final[str] = "pol"
"""Language assigned to every track this application adds."""

_BURN_SECONDS_PER_MINUTE: Final[float] = 40.0
"""Rough render seconds per minute of video used for the pre-run estimate."""

_FAILED_STATUS: Final[str] = "failed"
"""Composition status stored when assembling one file raised a typed error."""

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BurnEstimate:
    """Predicted cost of rendering a batch, shown before work starts."""

    file_count: int
    estimated_seconds: float


def build_plan(
    outcome: FileOutcome,
    *,
    variant: OutputVariant,
    workspace_root: Path,
    scope_id: str,
    subtitle_kind: str = "ass",
) -> CompositionPlan | None:
    """Return the composition plan for one processed file, or ``None``.

    The truth tables from the stage requirements live here: an already-Polish
    source never receives a duplicate full track, and burning prefers the
    displayed-only stream whenever a lector exists.
    """
    destination: Path = _destination_dir(outcome, variant=variant, workspace_root=workspace_root)
    if variant is OutputVariant.BURN:
        burn_subtitle: Path | None = _burn_subtitle(outcome)
        if burn_subtitle is None and outcome.mixed_audio_path is None:
            return None
        return CompositionPlan(
            source_path=outcome.source,
            variant=variant,
            narration_audio=outcome.mixed_audio_path,
            burn_subtitle=burn_subtitle,
            source_subtitle_kind=subtitle_kind,
            scope_id=scope_id,
            temporary_root=workspace_root / "tmp" / scope_id,
            destination_dir=destination,
        )

    subtitles: tuple[AttachedSubtitle, ...] = _attached_subtitles(outcome)
    if not subtitles and outcome.mixed_audio_path is None:
        return None
    return CompositionPlan(
        source_path=outcome.source,
        variant=variant,
        narration_audio=outcome.mixed_audio_path,
        subtitles=subtitles,
        source_subtitle_kind=subtitle_kind,
        scope_id=scope_id,
        temporary_root=workspace_root / "tmp" / scope_id,
        destination_dir=destination,
    )


def _attached_subtitles(outcome: FileOutcome) -> tuple[AttachedSubtitle, ...]:
    """Return subtitle tracks to mux, skipping a duplicate Polish source."""
    attached: list[AttachedSubtitle] = []
    if outcome.translated_path is not None and not outcome.already_polish:
        attached.append(
            AttachedSubtitle(outcome.translated_path, SubtitleRole.FULL, _POLISH_LANGUAGE, _FULL_TRACK_NAME),
        )
    if outcome.displayed_path is not None:
        attached.append(
            AttachedSubtitle(
                outcome.displayed_path,
                SubtitleRole.DISPLAYED,
                _POLISH_LANGUAGE,
                _DISPLAYED_TRACK_NAME,
            ),
        )
    return tuple(attached)


def _burn_subtitle(outcome: FileOutcome) -> Path | None:
    """Return the single stream to render into the picture."""
    if outcome.mixed_audio_path is not None:
        return outcome.displayed_path
    if outcome.translated_path is not None:
        return outcome.translated_path
    return outcome.subtitle_path


def _destination_dir(outcome: FileOutcome, *, variant: OutputVariant, workspace_root: Path) -> Path:
    """Return where the artifact belongs for the requested variant."""
    if variant is OutputVariant.PLAYERS:
        return outcome.source.parent
    return workspace_root / "output"


def estimate_burn_cost(plans: tuple[CompositionPlan, ...], *, ffprobe: Path) -> BurnEstimate:
    """Return a coarse render-cost estimate shown before burning starts.

    The estimate scales with the playing time of each source, read through
    FFprobe. ``FileOutcome.audio_time_ms`` measures how long the audio stage
    ran, not how long the episode is, so it cannot be used here.
    """
    total_us: int = sum(source_duration_us(plan.source_path, ffprobe=ffprobe) for plan in plans)
    minutes: float = total_us / 60_000_000
    return BurnEstimate(file_count=len(plans), estimated_seconds=minutes * _BURN_SECONDS_PER_MINUTE)


def compose_outcomes(
    outcomes: dict[Path, FileOutcome],
    *,
    service: CompositionService,
    variant: OutputVariant,
    workspace_root: Path,
    ui: CompositionUi | None = None,
    cancel: threading.Event | None = None,
) -> dict[Path, FileOutcome]:
    """Assemble every finished file and record why the others were skipped.

    Shared by the full pipeline and by ``/compose`` so both take exactly the
    same decisions. One file's failure never stops the batch. The service is
    built by the caller, which keeps this loop testable without real binaries.
    """
    composed: dict[Path, FileOutcome] = dict(outcomes)
    plans: dict[Path, CompositionPlan] = {}
    for path, outcome in outcomes.items():
        plan: CompositionPlan | None = _plan_for(outcome, variant=variant, workspace_root=workspace_root)
        if plan is None:
            composed[path] = replace(outcome, composition_status=CompositionStatus.SKIPPED_NOTHING_TO_ADD.value)
            logger.info("Composition skipped", source=path.name, reason="nothing_to_add")
            continue
        plans[path] = plan
    if variant is OutputVariant.BURN and ui is not None:
        estimate: BurnEstimate = estimate_burn_cost(tuple(plans.values()), ffprobe=service.ffprobe)
        ui.on_burn_estimate(estimate.file_count, estimate.estimated_seconds)
    for path, plan in plans.items():
        if cancel is not None and cancel.is_set():
            break
        composed[path] = _compose_one(
            service,
            composed[path],
            plan,
            workspace_root=workspace_root,
            ui=ui,
            cancel=cancel,
        )
    return composed


def _plan_for(outcome: FileOutcome, *, variant: OutputVariant, workspace_root: Path) -> CompositionPlan | None:
    """Return the plan for one finished outcome, or ``None`` when unusable."""
    if outcome.status != "done":
        return None
    return build_plan(
        outcome,
        variant=variant,
        workspace_root=workspace_root,
        scope_id=scope_id_for_source(outcome.source, workspace_root=workspace_root),
        subtitle_kind=_subtitle_kind(outcome),
    )


def _compose_one(
    service: CompositionService,
    outcome: FileOutcome,
    plan: CompositionPlan,
    *,
    workspace_root: Path,
    ui: CompositionUi | None,
    cancel: threading.Event | None,
) -> FileOutcome:
    """Compose one file, keeping a typed failure local to that file."""
    try:
        result: CompositionResult = service.compose(plan, callbacks=ui, cancel=cancel)
    except AniShiftError as error:
        if error.context.code is ErrorCode.CANCELLED:
            raise
        logger.warning("Composition failed", source=plan.source_path.name, code=error.context.code.value)
        return replace(outcome, composition_status=_FAILED_STATUS, composition_warnings=(error.context.message,))
    if result.status is CompositionStatus.COMPLETED:
        _discard_scope(workspace_root, plan.scope_id)
    return replace(
        outcome,
        composed_path=result.output_path,
        composition_status=result.status.value,
        composition_warnings=result.warnings,
    )


def _discard_scope(workspace_root: Path, scope_id: str) -> None:
    """Remove the transient working directory of one finished file."""
    scope_dir: Path = workspace_root / "tmp" / scope_id
    if not scope_dir.exists():
        return
    try:
        safe_rmtree(scope_dir)
    except OSError:
        logger.warning("Transient scope directory could not be removed", scope_id=scope_id)


def _subtitle_kind(outcome: FileOutcome) -> str:
    """Return the subtitle format of the products written for one file."""
    subtitle: Path | None = outcome.translated_path or outcome.displayed_path or outcome.subtitle_path
    return "srt" if subtitle is not None and subtitle.suffix.casefold() == ".srt" else "ass"
```

### 10.2. `tests/pipeline/test_composition_runtime.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from anishift.pipeline.composition_runtime import build_plan, compose_outcomes
from anishift.pipeline.narration import scope_id_for_source
from anishift.pipeline.types import FileOutcome
from anishift.services.composition.errors import CompositionValidationError
from anishift.services.composition.types import (
    CompositionPlan,
    CompositionResult,
    CompositionStatus,
    OutputVariant,
    SubtitleRole,
)


def _outcome(tmp_path: Path, **overrides: object) -> FileOutcome:
    defaults: dict[str, object] = {
        "source": tmp_path / "Episode.mkv",
        "status": "done",
    }
    defaults.update(overrides)
    return FileOutcome(**defaults)  # type: ignore[arg-type]


def test_foreign_source_with_lector_adds_full_and_displayed(tmp_path: Path) -> None:
    outcome = _outcome(
        tmp_path,
        translated_path=tmp_path / "Episode.pl.ass",
        displayed_path=tmp_path / "Episode.displayed.pl.ass",
        mixed_audio_path=tmp_path / "Episode.eac3",
    )

    plan = build_plan(outcome, variant=OutputVariant.MERGE, workspace_root=tmp_path, scope_id="scope-1")

    assert plan is not None
    assert [subtitle.role for subtitle in plan.subtitles] == [SubtitleRole.FULL, SubtitleRole.DISPLAYED]
    assert plan.narration_audio is not None


def test_polish_source_never_duplicates_the_full_track(tmp_path: Path) -> None:
    outcome = _outcome(
        tmp_path,
        already_polish=True,
        translated_path=tmp_path / "Episode.pl.ass",
        displayed_path=tmp_path / "Episode.displayed.pl.ass",
        mixed_audio_path=tmp_path / "Episode.eac3",
    )

    plan = build_plan(outcome, variant=OutputVariant.MERGE, workspace_root=tmp_path, scope_id="scope-1")

    assert plan is not None
    assert [subtitle.role for subtitle in plan.subtitles] == [SubtitleRole.DISPLAYED]


def test_merge_without_material_returns_no_plan(tmp_path: Path) -> None:
    assert build_plan(_outcome(tmp_path), variant=OutputVariant.MERGE, workspace_root=tmp_path, scope_id="s") is None


def test_burn_prefers_displayed_when_a_lector_exists(tmp_path: Path) -> None:
    outcome = _outcome(
        tmp_path,
        translated_path=tmp_path / "Episode.pl.ass",
        displayed_path=tmp_path / "Episode.displayed.pl.ass",
        mixed_audio_path=tmp_path / "Episode.eac3",
    )

    plan = build_plan(outcome, variant=OutputVariant.BURN, workspace_root=tmp_path, scope_id="s")

    assert plan is not None
    assert plan.burn_subtitle == tmp_path / "Episode.displayed.pl.ass"


def test_burn_uses_full_subtitles_without_a_lector(tmp_path: Path) -> None:
    outcome = _outcome(tmp_path, translated_path=tmp_path / "Episode.pl.ass")

    plan = build_plan(outcome, variant=OutputVariant.BURN, workspace_root=tmp_path, scope_id="s")

    assert plan is not None
    assert plan.burn_subtitle == tmp_path / "Episode.pl.ass"


@pytest.mark.parametrize(
    ("variant", "expected_parent"),
    [(OutputVariant.MERGE, "output"), (OutputVariant.BURN, "output")],
)
def test_assembled_variants_target_the_output_directory(
    tmp_path: Path,
    variant: OutputVariant,
    expected_parent: str,
) -> None:
    outcome = _outcome(tmp_path, translated_path=tmp_path / "Episode.pl.ass")

    plan = build_plan(outcome, variant=variant, workspace_root=tmp_path, scope_id="s")

    assert plan is not None
    assert plan.destination_dir.name == expected_parent


def test_players_variant_targets_the_source_directory(tmp_path: Path) -> None:
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    outcome = _outcome(media_dir, translated_path=media_dir / "Episode.pl.ass")

    plan = build_plan(outcome, variant=OutputVariant.PLAYERS, workspace_root=tmp_path, scope_id="s")

    assert plan is not None
    assert plan.destination_dir == media_dir


class _StubService:
    def __init__(self, *, fail_for: frozenset[Path] = frozenset()) -> None:
        self.ffprobe = Path("ffprobe")
        self._fail_for = fail_for

    def compose(self, plan: CompositionPlan, **kwargs: Any) -> CompositionResult:
        if plan.source_path in self._fail_for:
            raise CompositionValidationError("merge failed")
        return CompositionResult(
            source_path=plan.source_path,
            variant=plan.variant,
            status=CompositionStatus.COMPLETED,
            output_path=plan.destination_dir / f"{plan.source_path.stem}.pl.mkv",
        )


def _done(tmp_path: Path, name: str) -> FileOutcome:
    return FileOutcome(
        source=tmp_path / f"{name}.mkv",
        status="done",
        translated_path=tmp_path / f"{name}.pl.ass",
    )


def test_one_failure_does_not_stop_the_batch(tmp_path: Path) -> None:
    failing = _done(tmp_path, "A")
    healthy = _done(tmp_path, "B")

    composed = compose_outcomes(
        {failing.source: failing, healthy.source: healthy},
        service=_StubService(fail_for=frozenset({failing.source})),
        variant=OutputVariant.MERGE,
        workspace_root=tmp_path,
    )

    assert composed[failing.source].composition_status == "failed"
    assert composed[healthy.source].composition_status == "completed"
    assert composed[healthy.source].composed_path is not None


def test_success_discards_the_scope_directory(tmp_path: Path) -> None:
    outcome = _done(tmp_path, "A")
    scope = tmp_path / "tmp" / scope_id_for_source(outcome.source, workspace_root=tmp_path)
    scope.mkdir(parents=True)

    compose_outcomes(
        {outcome.source: outcome},
        service=_StubService(),
        variant=OutputVariant.MERGE,
        workspace_root=tmp_path,
    )

    assert not scope.exists()


def test_failure_keeps_the_scope_directory(tmp_path: Path) -> None:
    outcome = _done(tmp_path, "A")
    scope = tmp_path / "tmp" / scope_id_for_source(outcome.source, workspace_root=tmp_path)
    scope.mkdir(parents=True)

    compose_outcomes(
        {outcome.source: outcome},
        service=_StubService(fail_for=frozenset({outcome.source})),
        variant=OutputVariant.MERGE,
        workspace_root=tmp_path,
    )

    assert scope.is_dir()
```

Do nagłówka pliku dochodzi jeszcze `from typing import Any` — używa go sygnatura `_StubService.compose`.

**Weryfikacja kroku 8:**

```bash
uv run pytest tests/pipeline/test_composition_runtime.py -v
```

Ten plik pokrywa macierz §7.3 i §7.4 wymagań (każdy wiersz obu tabel ma test) oraz trzy reguły
operacyjne: porażka jednego pliku nie zatrzymuje wsadu, sukces kasuje `tmp/<scope>/`, porażka
go zostawia.

---

## 11. Krok 9 — wpięcie w runner

### 11.1. `anishift/pipeline/types.py` — diff

```diff
 @dataclass(frozen=True, slots=True)
 class FileOutcome:
     ...
     audio_time_ms: float = 0.0
+    composed_path: Path | None = None
+    composition_status: str = ""
+    composition_warnings: tuple[str, ...] = ()
```

```diff
 @dataclass(frozen=True, slots=True)
 class PipelineReport:
     ...
+    composed_files: int = 0
+    skipped_compositions: tuple[tuple[Path, str], ...] = ()
+    failed_compositions: tuple[tuple[Path, str], ...] = ()
```

Protokół UI składania — postęp per plik oraz zapowiedź kosztu przed startem wypalania (§11.2b
wymagań). Mieszka w `pipeline/types.py`, bo koszt wsadu zna pipeline, nie domena składania:

```python
class CompositionUi(Protocol):
    """Composition progress and pre-run cost reporting owned by the CLI."""

    def on_composition_phase(self, scope_id: str, phase: str, percent: int) -> None:
        """Report one composition phase without rendering UI."""
        ...

    def on_burn_estimate(self, file_count: int, estimated_seconds: float) -> None:
        """Announce how much rendering the batch will cost before it starts."""
        ...
```

### 11.2. `anishift/pipeline/runner.py` — trzy zmiany

**A. Poprawka filtra wejść** (§11.2c wymagań):

`discover_inputs` przegląda wyłącznie `.mkv` i `.txt` w korzeniu `workspace/`
(`root.iterdir()`, bez rekursji — `runner.py:161`). Produkty napisowe to `.ass`/`.srt`, więc
filtr `.displayed` nie mógł odsiać żadnego z nich; odsiewał tylko źródła ze słowem `displayed`
w tytule. Odsiać trzeba za to własne produkty kontenerowe, gdyby użytkownik skopiował wynik
z `output/` z powrotem do `workspace/`.

```diff
-_DISPLAYED_INFIX: Final[str] = ".displayed"
-"""Infix used by displayed subtitle products."""
+_RESULT_ENDINGS: Final[tuple[str, ...]] = (".pl.mkv", ".pl.mp4")
+"""Endings of containers this application produced, never pipeline inputs."""
```

```diff
-        if path.is_file() and path.suffix.lower() in {_MKV_SUFFIX, _TXT_SUFFIX} and _DISPLAYED_INFIX not in path.name
+        if path.is_file() and path.suffix.lower() in {_MKV_SUFFIX, _TXT_SUFFIX} and not _is_own_result(path)
```

```python
def _is_own_result(path: Path) -> bool:
    """Return whether a file is a container this application produced."""
    return path.name.casefold().endswith(_RESULT_ENDINGS)
```

**B. Krok 5 — składanie po audio.** Cała pętla mieszka w `composition_runtime.compose_outcomes`
(krok 8), więc runner tylko buduje serwis i woła ją raz:

```python
def _compose_phase(
    outcomes: dict[Path, FileOutcome],
    *,
    context: AppContext,
    workspace_root: Path,
    ui: CompositionUi | None,
    cancel: threading.Event,
) -> dict[Path, FileOutcome]:
    """Assemble every finished file with the settings chosen by the user."""
    config: CompositionConfig = CompositionConfig(
        quality_preset=QualityPreset(context.user_settings.composition_quality_preset),
    )
    return compose_outcomes(
        outcomes,
        service=CompositionService(config),
        variant=OutputVariant(context.user_settings.output_variant),
        workspace_root=workspace_root,
        ui=ui,
        cancel=cancel,
    )
```

`QualityPreset(...)` i `OutputVariant(...)` konwertują wartości `Literal` z ustawień na typy
domeny — panel trzyma je jako łańcuchy, domena wyłącznie jako `StrEnum`.

**C. Raport końcowy** liczy trzy grupy zamiast jednej — złożone, pominięte i nieudane:

```python
def _composition_counters(outcomes: tuple[FileOutcome, ...]) -> tuple[int, tuple[tuple[Path, str], ...], tuple[tuple[Path, str], ...]]:
    """Return composed count plus skipped and failed files with their reasons."""
    composed: int = sum(1 for outcome in outcomes if outcome.composed_path is not None)
    skipped: tuple[tuple[Path, str], ...] = tuple(
        (outcome.source, outcome.composition_status)
        for outcome in outcomes
        if outcome.composition_status.startswith("skipped")
    )
    failed: tuple[tuple[Path, str], ...] = tuple(
        (outcome.source, outcome.composition_warnings[0] if outcome.composition_warnings else "")
        for outcome in outcomes
        if outcome.composition_status == "failed"
    )
    return composed, skipped, failed
```

### 11.3. `tests/pipeline/test_pipeline_runner.py` — nowe testy

Sprzątanie `tmp/<scope>/` i izolacja błędu są pokryte w kroku 8; tutaj zostaje wyłącznie
poprawka wykrywania wejść (§11.2c wymagań):

```python
def test_source_named_with_displayed_is_still_discovered(tmp_path: Path) -> None:
    (tmp_path / "Show.displayed.S01E01.mkv").write_bytes(b"x")
    assert discover_inputs(tmp_path) == [tmp_path / "Show.displayed.S01E01.mkv"]


def test_generated_products_are_not_discovered(tmp_path: Path) -> None:
    (tmp_path / "Show.displayed.pl.ass").write_text("", encoding="utf-8")
    (tmp_path / "Show.pl.mkv").write_bytes(b"x")
    assert discover_inputs(tmp_path) == []
```

**Weryfikacja kroku 9:**

```bash
uv run pytest tests/pipeline -v
```

---

## 12. Krok 10 — ustawienia

### 12.1. `anishift/config/user_settings.py` — diff

```diff
+CompositionQualityPreset = Literal["high", "balanced", "compact"]
+"""Named quality target for hardsub rendering."""
+
+_COMPOSITION_PRESETS: Final[frozenset[str]] = frozenset(("high", "balanced", "compact"))
+"""Accepted hardsub quality presets."""
+
+_DEFAULT_AUDIO_LANGUAGES: Final[tuple[str, ...]] = ("jpn", "eng", "zho")
+"""Preferred source audio languages, most wanted first."""
+
+_DEFAULT_SUBTITLE_LANGUAGES: Final[tuple[str, ...]] = ("pol", "eng")
+"""Preferred source subtitle languages, most wanted first."""
```

```diff
-    output_variant: OutputVariant = "merge"
+    output_variant: OutputVariant = "players"
-    move_results_to_output: bool = False
+    composition_quality_preset: CompositionQualityPreset = "balanced"
+    audio_language_priority: tuple[str, ...] = _DEFAULT_AUDIO_LANGUAGES
+    subtitle_language_priority: tuple[str, ...] = _DEFAULT_SUBTITLE_LANGUAGES
```

```diff
-    _clean_bool(filtered, "move_results_to_output")
+    _clean_string(filtered, "composition_quality_preset", _COMPOSITION_PRESETS)
+    _clean_language_tuple(filtered, "audio_language_priority")
+    _clean_language_tuple(filtered, "subtitle_language_priority")
```

```python
def _clean_language_tuple(payload: dict[str, Any], key: str) -> None:
    """Keep a key only when it is a list of plain language codes."""
    raw: object = payload.get(key)
    if not isinstance(raw, list) or not all(isinstance(item, str) and item.strip() for item in raw):
        payload.pop(key, None)
        return
    payload[key] = tuple(item.strip().casefold() for item in raw)
```

### 12.2. `anishift/services/extraction/tracks.py` — diff

Dziś wagi języków są zaszyte w dwóch słownikach (`_SUB_LANG_WEIGHT`, `_AUDIO_LANG_WEIGHT`).
Etap 7 zamienia je na jedną listę priorytetów podawaną z zewnątrz; domyślne listy odtwarzają
dzisiejszą kolejność wyborów.

```diff
-_SUB_LANG_WEIGHT: Final[dict[str, int]] = {"pol": 100, "pl": 100, "eng": 50, "en": 50}
-"""Subtitle language weights."""
-
-_SUB_LANG_DEFAULT: Final[int] = 10
-"""Weight for an unlisted subtitle language."""
-
-_AUDIO_LANG_WEIGHT: Final[dict[str, int]] = {"jpn": 100, "ja": 100, "eng": 40, ...}
-"""Audio language weights."""
-
-_AUDIO_LANG_DEFAULT: Final[int] = 20
-"""Weight for an unlisted audio language."""
+DEFAULT_AUDIO_PRIORITY: Final[tuple[str, ...]] = ("jpn", "eng", "zho")
+"""Audio languages preferred by the scorer, most wanted first."""
+
+DEFAULT_SUBTITLE_PRIORITY: Final[tuple[str, ...]] = ("pol", "eng")
+"""Subtitle languages preferred by the scorer, most wanted first."""
+
+_LANGUAGE_ALIASES: Final[dict[str, str]] = {
+    "ja": "jpn", "en": "eng", "pl": "pol", "zh": "zho", "chi": "zho", "chs": "zho", "cht": "zho",
+}
+"""Two-letter and legacy tags mapped to the form used in priority lists."""
+
+_TOP_LANGUAGE_SCORE: Final[int] = 100
+"""Score of the first language in a priority list."""
+
+_LANGUAGE_STEP: Final[int] = 10
+"""Score lost per position in a priority list."""
+
+_UNRANKED_LANGUAGE_SCORE: Final[int] = 0
+"""Score of a language absent from the priority list."""
```

```python
def _language_score(language: str, priority: tuple[str, ...]) -> int:
    """Return a descending score based on position in the priority list."""
    normalized: str = language.casefold()
    canonical: str = _LANGUAGE_ALIASES.get(normalized, normalized)
    if canonical not in priority:
        return _UNRANKED_LANGUAGE_SCORE
    return _TOP_LANGUAGE_SCORE - priority.index(canonical) * _LANGUAGE_STEP
```

```diff
-def score_subtitle_track(track: dict[str, Any]) -> float:
+def score_subtitle_track(track: dict[str, Any], priority: tuple[str, ...] = DEFAULT_SUBTITLE_PRIORITY) -> float:
     """Score a subtitle track for translation and narration."""
-    score = float(_SUB_LANG_WEIGHT.get(_track_language(track), _SUB_LANG_DEFAULT))
+    score = float(_language_score(_track_language(track), priority))
```

```diff
-def score_audio_track(track: dict[str, Any]) -> float:
+def score_audio_track(track: dict[str, Any], priority: tuple[str, ...] = DEFAULT_AUDIO_PRIORITY) -> float:
     """Score an audio track for use under the narrator."""
-    score = float(_AUDIO_LANG_WEIGHT.get(_track_language(track), _AUDIO_LANG_DEFAULT))
+    score = float(_language_score(_track_language(track), priority))
```

```diff
-def select_tracks(tracks: Sequence[TrackInfo]) -> TrackSelection:
+def select_tracks(
+    tracks: Sequence[TrackInfo],
+    *,
+    audio_priority: tuple[str, ...] = DEFAULT_AUDIO_PRIORITY,
+    subtitle_priority: tuple[str, ...] = DEFAULT_SUBTITLE_PRIORITY,
+) -> TrackSelection:
```

`select_audio_track` i `select_subtitle_track` dostają ten sam parametr i przekazują go do
funkcji scorujących. Wywołanie w `runner.py:1062` podaje listy z ustawień:

```diff
-        proposal = select_tracks(info.tracks)
+        proposal = select_tracks(
+            info.tracks,
+            audio_priority=context.user_settings.audio_language_priority,
+            subtitle_priority=context.user_settings.subtitle_language_priority,
+        )
```

Test regresyjny (wymagany w §16): dataset ścieżek z realnego MKV wybiera przy domyślnych
priorytetach dokładnie te same `audio_id` i `subtitle_id`, co dzisiejsze wagi.

### 12.3. `anishift/cli/settings_panel.py` — diff

```diff
-    _Field("output_variant", "Output variant"),
-    _Field("move_results_to_output", "Move results to output/"),
+    _Field("output_variant", "Output variant"),
+    _Field("composition_quality_preset", "Burn quality"),
+    _Field("audio_language_priority", "Audio language priority"),
+    _Field("subtitle_language_priority", "Subtitle language priority"),
```

**Weryfikacja kroku 10:**

```bash
uv run pytest tests/config tests/cli tests/services/extraction -v
uv run python -c "
from anishift.config.user_settings import UserSettings
s = UserSettings()
print(s.output_variant, s.composition_quality_preset, s.audio_language_priority)
assert not hasattr(s, 'move_results_to_output')
"
```

---

## 13. Krok 11 — `/compose` i raport

Wymaganie §6.4 mówi wprost: `/compose` ma działać także na MKV, który **nigdy nie przeszedł
pipeline'u**. `build_plan` przyjmuje `FileOutcome`, a ten powstaje dopiero w runnerze — więc
`/compose` potrzebuje własnego źródła outcomes, zbudowanego z tego, co leży na dysku. To robi
`pipeline/compose_only.py`; decyzje „co dołożyć" i cała pętla zostają wspólne z Enterem
(`compose_outcomes` z kroku 8).

Kolejność szukania materiału dla jednego MKV:

1. produkty wcześniejszych przebiegów — `{stem}.pl.<kind>` i `{stem}.displayed.pl.<kind>`
   w korzeniu `workspace/`, sidecar lektora obok źródła;
2. gdy produktów nie ma — napisy **ze źródła**, ale tylko jeśli wybrana ścieżka jest polska
   (`already_polish`); wyciąga je istniejące `extract_tracks` do `tmp/<scope>/compose/`;
3. gdy nadal nic — plik pominięty z powodem w raporcie.

### 13.1. `anishift/pipeline/compose_only.py`

```python
"""Build file outcomes from products already on disk for the /compose command."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Final

from anishift.bootstrap import AppContext
from anishift.pipeline.composition_runtime import compose_outcomes
from anishift.pipeline.narration import scope_id_for_source
from anishift.pipeline.runner import discover_inputs
from anishift.pipeline.types import CompositionUi, FileOutcome
from anishift.services.composition.config import CompositionConfig
from anishift.services.composition.service import CompositionService
from anishift.services.composition.types import OutputVariant, QualityPreset
from anishift.services.extraction.service import extract_tracks, identify
from anishift.services.extraction.tracks import select_tracks
from anishift.services.extraction.types import ExtractionResult, MediaInfo, TrackSelection
from anishift.utils.logger import get_logger

__all__ = ["compose_existing", "extracted_polish_outcome", "product_outcome"]

# ── Constants ────────────────────────────────────────────────────────────────

_MKV_SUFFIX: Final[str] = ".mkv"
"""Only containers can be assembled; TXT inputs carry no video."""

_SUBTITLE_SUFFIXES: Final[tuple[str, ...]] = (".ass", ".srt")
"""Subtitle formats this application writes."""

_NARRATION_SUFFIXES: Final[tuple[str, ...]] = (".eac3", ".m4a", ".mp3", ".opus", ".flac", ".wav")
"""Sidecar extensions produced by the audio codec profiles."""

logger = get_logger(__name__)


def compose_existing(
    context: AppContext,
    *,
    ui: CompositionUi | None = None,
    cancel: threading.Event | None = None,
) -> tuple[FileOutcome, ...]:
    """Assemble every workspace container from material already on disk.

    Nothing is translated or synthesized, and no setting is changed: the
    requested variant and quality still come from the user's preferences.
    """
    workspace_root: Path = context.workspace_root
    outcomes: dict[Path, FileOutcome] = {}
    for source in discover_inputs(workspace_root):
        if source.suffix.casefold() != _MKV_SUFFIX:
            continue
        outcome: FileOutcome | None = product_outcome(source, workspace_root=workspace_root)
        if outcome is None:
            outcome = extracted_polish_outcome(source, workspace_root=workspace_root, cancel=cancel)
        if outcome is None:
            logger.info("Composition input skipped", source=source.name, reason="no_material")
            continue
        outcomes[source] = outcome
    config: CompositionConfig = CompositionConfig(
        quality_preset=QualityPreset(context.user_settings.composition_quality_preset),
    )
    composed: dict[Path, FileOutcome] = compose_outcomes(
        outcomes,
        service=CompositionService(config),
        variant=OutputVariant(context.user_settings.output_variant),
        workspace_root=workspace_root,
        ui=ui,
        cancel=cancel,
    )
    return tuple(composed.values())


def product_outcome(source: Path, *, workspace_root: Path) -> FileOutcome | None:
    """Return an outcome built from earlier runs' products, when any exist."""
    full: Path | None = _first_subtitle(workspace_root, source.stem)
    displayed: Path | None = _first_subtitle(workspace_root, f"{source.stem}.displayed")
    narration: Path | None = _narration_sidecar(source)
    if full is None and displayed is None and narration is None:
        return None
    return FileOutcome(
        source=source,
        status="done",
        translated_path=full,
        displayed_path=displayed,
        mixed_audio_path=narration,
    )


def extracted_polish_outcome(
    source: Path,
    *,
    workspace_root: Path,
    cancel: threading.Event | None = None,
) -> FileOutcome | None:
    """Return an outcome carrying the source's own Polish subtitle track.

    This is the path required by §6.4 of the stage requirements: a container
    that already holds Polish subtitles can be burned without ever running
    translation or TTS.
    """
    info: MediaInfo = identify(source)
    proposal: TrackSelection = select_tracks(info.tracks)
    if not proposal.already_polish or proposal.subtitle_id is None:
        return None
    scope_id: str = scope_id_for_source(source, workspace_root=workspace_root)
    work_dir: Path = workspace_root / "tmp" / scope_id / "compose"
    work_dir.mkdir(parents=True, exist_ok=True)
    extracted: ExtractionResult = extract_tracks(
        info,
        TrackSelection(audio_id=None, subtitle_id=proposal.subtitle_id, already_polish=True),
        work_dir,
        cancel=cancel,
    )
    if extracted.subtitle_path is None:
        return None
    return FileOutcome(
        source=source,
        status="done",
        subtitle_path=extracted.subtitle_path,
        translated_path=extracted.subtitle_path,
        already_polish=True,
    )


def _first_subtitle(directory: Path, stem: str) -> Path | None:
    """Return the Polish product with this stem, in either written format."""
    for suffix in _SUBTITLE_SUFFIXES:
        candidate: Path = directory / f"{stem}.pl{suffix}"
        if candidate.is_file():
            return candidate
    return None


def _narration_sidecar(source: Path) -> Path | None:
    """Return the mixed narration written next to the source, if any."""
    for suffix in _NARRATION_SUFFIXES:
        candidate: Path = source.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None
```

Uwaga o macierzy: dla źródła polskiego bez produktów `already_polish=True` sprawia, że `merge`
świadomie nic nie dokłada (`skipped_nothing_to_add` — nie dublujemy istniejącej ścieżki), a `burn`
wypala wyciągnięte napisy. Dokładnie tak stanowi §7.2 i §7.4 wymagań.

### 13.2. `tests/pipeline/test_compose_only.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from anishift.pipeline.compose_only import extracted_polish_outcome, product_outcome
from anishift.platform.binaries import Binary, resolve_binary

MKVMERGE = resolve_binary(Binary.MKVMERGE)
FFMPEG = resolve_binary(Binary.FFMPEG)


def test_product_outcome_collects_products_from_an_earlier_run(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    source.write_bytes(b"x")
    (tmp_path / "Episode.pl.ass").write_text("", encoding="utf-8")
    (tmp_path / "Episode.displayed.pl.ass").write_text("", encoding="utf-8")
    (tmp_path / "Episode.eac3").write_bytes(b"a")

    outcome = product_outcome(source, workspace_root=tmp_path)

    assert outcome is not None
    assert outcome.translated_path == tmp_path / "Episode.pl.ass"
    assert outcome.displayed_path == tmp_path / "Episode.displayed.pl.ass"
    assert outcome.mixed_audio_path == tmp_path / "Episode.eac3"


def test_product_outcome_is_none_without_any_product(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    source.write_bytes(b"x")

    assert product_outcome(source, workspace_root=tmp_path) is None


@pytest.mark.skipif(MKVMERGE is None or FFMPEG is None, reason="bundled tools are unavailable")
def test_polish_source_without_any_previous_run_yields_subtitles(tmp_path: Path) -> None:
    source = _mkv_with_polish_subtitles(tmp_path)

    outcome = extracted_polish_outcome(source, workspace_root=tmp_path)

    assert outcome is not None
    assert outcome.already_polish is True
    assert outcome.translated_path is not None
    assert outcome.translated_path.stat().st_size > 0
```

`_mkv_with_polish_subtitles` buduje kontener z `ffmpeg -f lavfi` i dokłada `.ass` przez
`mkvmerge --language 0:pol`. Ten test jest **dowodem wymaganym w §4.2 wymagań**: przechodzi
wyłącznie wtedy, gdy metadane i napisy pochodzą z pliku, a nie ze snapshotu po ekstrakcji.

### 13.3. `anishift/cli/commands.py` — diff

```diff
+def _handle_compose(context: AppContext, options: frozenset[str]) -> bool:
+    """Assemble existing products without translating or synthesizing."""
+    del options
+    print_composition_summary(compose_existing(context, ui=CompositionConsole()))
+    return True
```

```diff
     "/auto": Command("/auto", "Switch to auto mode (Enter processes everything)", _handle_auto),
+    "/compose": Command(
+        "/compose",
+        "Assemble results from existing files, without translation or TTS",
+        _handle_compose,
+    ),
     "/doctor": Command("/doctor", "Run diagnostics and report your setup", _handle_doctor),
```

### 13.4. `anishift/cli/pipeline_ui.py` — nowe funkcje

```python
class CompositionConsole:
    """Render composition progress and the pre-run cost of burning."""

    def on_composition_phase(self, scope_id: str, phase: str, percent: int) -> None:
        """Print one phase line per completed decile of the operation."""
        if percent % _PHASE_STEP_PERCENT:
            return
        console.print(f"[gray]{phase} {scope_id}: {percent}%[/gray]")

    def on_burn_estimate(self, file_count: int, estimated_seconds: float) -> None:
        """Announce the batch size and rough duration before rendering."""
        if file_count == 0:
            return
        minutes: int = round(estimated_seconds / 60)
        console.print(
            f"{get_status_icon('info')} Burning {file_count} file(s), roughly {minutes} min — "
            f"press Ctrl+C to stop at any point.",
        )


def print_composition_summary(outcomes: tuple[FileOutcome, ...]) -> None:
    """Print one line per composed file and per skipped or failed file."""
    for outcome in outcomes:
        if outcome.composed_path is not None:
            console.print(f"{get_status_icon('success')} {outcome.source.name} -> {outcome.composed_path.name}")
        elif outcome.composition_status:
            console.print(f"{get_status_icon('warning')} {outcome.source.name}: {outcome.composition_status}")
        for warning in outcome.composition_warnings:
            console.print(f"    [gray]{warning}[/gray]")
```

`_PHASE_STEP_PERCENT` (10) trzyma wypis w ryzach: ffmpeg raportuje postęp kilka razy na sekundę,
a pełny pasek żyje w `_PipelineProgressRows` przy Enterze. `/compose` używa wersji tekstowej,
bo działa poza fazami pipeline'u.

### 13.5. `tests/cli/test_compose_command.py`

```python
from __future__ import annotations

from anishift.cli.commands import COMMANDS


def test_compose_command_is_registered() -> None:
    assert "/compose" in COMMANDS
    assert "translation" in COMMANDS["/compose"].summary.casefold()


def test_compose_command_takes_no_options() -> None:
    assert COMMANDS["/compose"].options == {}
```

**Weryfikacja kroku 11:**

```bash
uv run pytest tests/cli tests/pipeline/test_compose_only.py -v
uv run anishift   # /help pokazuje /compose; /compose składa bez klucza API
```

Krytyczne: `test_polish_source_without_any_previous_run_yields_subtitles` — bez niego `/compose`
działałby wyłącznie na plikach po wcześniejszym przebiegu, czyli wbrew §6.4 wymagań.

---

## 14. Krok 12 — ręczny wybór ścieżek (nic do zbudowania)

Wymaganie §6.5 jest **już spełnione w kodzie**:

| Element | Miejsce |
|---|---|
| deklaracja `choose_tracks(info, proposal)` | `pipeline/types.py:206` |
| implementacja z listą ścieżek i promptem | `cli/pipeline_ui.py:648` (`_ManualInteraction`) |
| wywołanie per plik, przed ekstrakcją | `runner.py:1063` |
| tryb auto bez pytania | `interaction is None` w tej samej linii |

Etap 7 nie dokłada tu ani jednej linii. Nowe jest wyłącznie to, co steruje **propozycją**
w trybie auto — priorytety języków z kroku 10.

**Weryfikacja kroku 12:**

```bash
uv run pytest tests/cli tests/services/extraction -v
uv run anishift   # /manual, Enter — pytanie o ścieżki pada per plik; /auto — nie pada
```

Test regresyjny do dołożenia w `tests/services/extraction/`: zmiana `audio_language_priority`
na `("eng", "jpn")` wybiera angielską ścieżkę tam, gdzie domyślne priorytety wybierały japońską.

---

## 15. Krok 13 — smoke E2E i dokumentacja

### 15.1. `scripts/smoke/run_e2e.ps1`

```powershell
# Manual end-to-end smoke for one episode.
# Usage: .\scripts\smoke\run_e2e.ps1 -Variant merge
param(
    [ValidateSet("players", "merge", "burn")]
    [string]$Variant = "players"
)

$ErrorActionPreference = "Stop"
$workspace = Join-Path $PSScriptRoot "..\..\workspace"
$sources = Get-ChildItem -Path $workspace -Filter *.mkv -File
if ($sources.Count -eq 0) { throw "No MKV in workspace/." }

Write-Host "Variant: $Variant, sources: $($sources.Count)"
uv run anishift
Write-Host "`nResults:"
Get-ChildItem -Path (Join-Path $workspace "output") -File | ForEach-Object {
    $size = [math]::Round($_.Length / 1MB, 1)
    Write-Host ("  {0} ({1} MB)" -f $_.Name, $size)
}
```

### 15.2. Dokumentacja do aktualizacji

- `anishift/services/composition/AGENTS.md` — utworzony w kroku 1, uzupełnić o realne pułapki
  napotkane podczas implementacji;
- `anishift/pipeline/AGENTS.md` — dopisać krok 5, `compose_only.py`, sprzątanie scope po sukcesie
  oraz **poprawić opis filtra** (dziś twierdzi, że `discover_inputs` pomija `.displayed` — po
  kroku 9 pomija własne kontenery `.pl.mkv`/`.pl.mp4`);
- `anishift/services/extraction/AGENTS.md` — dopisać `attachments` w `MediaInfo` i priorytety
  języków zamiast zaszytych wag;
- `anishift/cli/AGENTS.md` — dopisać `/compose`;
- `docs/plans/_index.md` — oznaczyć etap 7 jako wykonany;
- `docs/plans/etap-7-plan_v1.md` — skasować; zastąpiony przez ten plan.

**Weryfikacja kroku 13 — pełne bramki i ocena wizualna:**

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
.\scripts\smoke\run_e2e.ps1 -Variant merge
```

Ostatni krok wymaga **oceny wizualnej przez usera**: otworzyć wynikowy MKV i porównać wygląd
napisów ze źródłem. Wierności 1:1 nie da się sprawdzić automatycznie — to świadomy element
planu, nie przeoczenie.

---

## 16. Ryzyka i mitygacje

| Ryzyko | Mitygacja | Krok |
|---|---|---|
| Wierności napisów nie da się sprawdzić automatycznie | Jawna ocena wizualna na realnym odcinku; testy pilnują komend i metadanych | 13 |
| Wypalanie 27 odcinków to godziny | Zapowiedź kosztu z długości plików (`ffprobe`), postęp z procentem, bezpieczne przerwanie | 8, 11 |
| Apostrof łamie filtr napisów | `filter_safe_copy` obowiązkowe; test na realnej nazwie z apostrofem | 2, 7 |
| `MediaInfo` nie niesie załączników | Addytywne pole `attachments` z domyślną pustą krotką | 5 |
| `SubprocessRunner` nie strumieniuje postępu | Własny `StreamingRunner`; oba potoki drenowane w wątkach, cancel i timeout co 0,2 s | 3 |
| Cichy proces wisi mimo Ctrl+C i timeoutu | Dwa testy na procesie, który nic nie pisze na stdout | 3 |
| Zmiana scoringu psuje dotychczasowe wybory | Domyślne priorytety = dzisiejsza kolejność; test regresyjny na datasecie ścieżek | 10 |
| Kasowanie `tmp` usuwa za dużo | Wyłącznie `tmp/<scope>/` po zwalidowanym wyniku; dwa testy | 8 |
| Błąd jednego pliku wywala cały wsad | `_compose_one` łapie typowany błąd, oddaje status `failed`, leci dalej; test na dwóch plikach | 8 |
| `/compose` działa tylko po pełnym przebiegu | `compose_only` szuka produktów, a przy ich braku wyciąga polskie napisy ze źródła; test na świeżym MKV | 11 |

## 17. Definicja ukończenia

Zgodna z §14 wymagań:

- trzy tryby działają na realnym odcinku, wynik jest odtwarzalny;
- napisy w wyniku wyglądają 1:1 ze źródłem (ocena wizualna + zachowane załączniki);
- dołożone ścieżki stoją za oryginalnymi, z poprawnymi nazwami i flagami — sprawdzone na
  realnym kontenerze, nie tylko w komendzie;
- `/compose` składa bez tłumaczenia i TTS, nie zmieniając ustawień, **także na MKV, który nigdy
  nie przeszedł pipeline'u**;
- macierz §7 pokryta testami; porażka nic nie kasuje i nie zatrzymuje wsadu; sukces czyści
  `tmp/<scope>/`;
- raport podaje liczbę plików złożonych, pominiętych i nieudanych, każdy z powodem;
- przed wypalaniem widać liczbę plików i czas oszacowany z długości materiału;
- Ctrl+C i timeout działają także na procesie, który przestał raportować postęp;
- ścieżki z apostrofem, spacjami, nawiasami i polskimi znakami przechodzą wypalanie;
- `output_variant` steruje trybem, domyślnie `players`;
- pełne bramki jakości zielone; smoke E2E zielony.

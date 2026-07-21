# Etap 4 — tłumaczenie — PLAN IMPLEMENTACJI

> Kompletny plan implementacji domeny `anishift/services/translation/` — pierwszego rejestru silników w projekcie. Fundament pod etapy 5 (LLM) i 6 (TTS).
>
> **Zasada nadrzędna: RECYKLING MangaShift w 100%.** Dla każdego pliku plan mówi wprost: SKOPIUJ z `<ścieżka>` (podmiana `mangashift.`→`anishift.`) / PRZEPISZ z `<ścieżka referencji>` / NAPISZ OD ZERA (tylko gdy w MangaShift nie ma). Model implementujący NIE pisze od zera niczego co istnieje — inaczej halucynuje.
>
> Wymagania rozstrzygnięte: `etap-4-wymagania-v2.md`. Kod i komentarze PO ANGIELSKU, ten plan PO POLSKU.
>
> **Wersje ścieżek źródłowych (zweryfikowane, istnieją):**
> - MangaShift translation: `C:/Users/MattyMroz/Desktop/PROJECTS/MangaShift/mangashift/services/translation/`
> - mm_avh translator: `C:/Users/MattyMroz/Desktop/PROJECTS/mm_avh_working_space/modules/translator.py`
> - Referencje algorytmów: `c:/Users/MattyMroz/Desktop/PROJECTS/AniShift/scripts/tmp/text_chunker.py`, `srt_equalizer_reference.py`

---

## SPIS SEKCJI

- A) Drzewo struktury
- B) Reguły globalne (styl, importy, docstringi, ruff)
- C) SSOT — jedno źródło prawdy
- D) Pliki domeny (errors, constants, config, types, protocols, dedup, _retry, linebreak, chunking, service, __init__)
- E) Rejestr silników (`engines/__init__.py`)
- F) Silnik google
- G) Silnik deepl
- H) Silnik llm (szkielet — realizacja etap 5)
- I) Wpięcie w pipeline (runner, types)
- J) Ustawienia `/settings` (user_settings, settings_panel)
- K) Przepływ danych (diagram + opis)
- L) Kolejność implementacji (kroki 1..N z weryfikacją)
- M) Testy
- N) System LLM — pełny plan (§9 wymagań)
- O) Format znakowy / łamanie linii — mechanika szczegółowa

---

## A) DRZEWO STRUKTURY

```
anishift/services/translation/                      NOWY PAKIET
├── __init__.py            # publiczny interfejs domeny (re-export fasady/configu/typów/błędów/rejestru)
├── errors.py             # TranslationError → {Engine,Config,Auth,Quota,RateLimit}Error
├── constants.py          # Final: domyślny język, domyślne batch/retry/concurrency, limity znaków bazowe
├── config.py             # TranslationConfig (engine wymagany, target_lang, batch/retry/concurrency)
├── types.py              # BatchedLine, TranslatedLine, FileTranslation (raport)
├── protocols.py          # Protocol TranslationEngine (SYNC): engine_id, is_available, translate_batch, close
├── dedup.py              # deduplicate() + redistribute() — wspólne dla wszystkich silników
├── _retry.py             # własny sync retry z backoff (bez tenacity — utils nietykalny)
├── linebreak.py          # re-podział przetłumaczonej linii na wersy (R6b, własny algorytm)
├── chunking.py           # LatinPunctuator + char/word breaker (R6, przepisany text_chunker) — narzędzie txt
├── service.py            # TranslationService — fasada SYNC: dedup→batch→engine→fallback→wynik
└── engines/
    ├── __init__.py       # REJESTR: TranslationEngineId + _REGISTRY + available_engine_ids + create_engine
    ├── google/
    │   ├── __init__.py   # re-export GoogleService + GoogleConfig
    │   ├── config.py     # GoogleConfig (batch, max_chars, retries)
    │   ├── constants.py  # Final: separatory, limity, backoff
    │   ├── types.py      # (pusty — reużywa typów domeny)
    │   ├── _batching.py  # index-preserving batched translate (separator→newline→per-line ladder)
    │   └── service.py    # GoogleService (async→sync, jeden event loop na plik)
    ├── deepl/
    │   ├── __init__.py   # re-export DeeplService + DeeplConfig
    │   ├── config.py     # DeeplConfig (api_key, target defaults)
    │   ├── constants.py  # Final: MAX_CHARS (128 KiB), rate-limit params
    │   ├── types.py      # (pusty)
    │   ├── _lang_codes.py# to_deepl_code() mapowanie języków
    │   └── service.py    # DeeplService (sync SDK, is_available bez klucza)
    └── llm/              # SZKIELET — realizacja etap 5
        ├── __init__.py   # re-export LlmTranslateService + LlmTranslateConfig
        ├── config.py     # LlmTranslateConfig (max_repair_attempts, context_lines, shrink)
        ├── constants.py  # Final: SYSTEM_PROMPT (numeracja [N]), wzorce parsowania
        ├── types.py      # (pusty)
        └── service.py    # LlmTranslateService (numeracja [N], walidacja, shrink-do-1) — completer wstrzyknięty

anishift/pipeline/
├── runner.py             # ZMIANA: krok translate w _process_mkv + _process_txt
└── types.py              # ZMIANA: StepName += "translate"; FileOutcome += pola tłumaczenia

anishift/config/
├── user_settings.py      # ZMIANA: pola translation_* + target_lang + llm_*; _clean_str_list
└── settings.py           # BEZ ZMIAN (deepl_api_key już jest)

anishift/cli/
└── settings_panel.py     # ZMIANA: derywacja silnika z available_engine_ids() + nowe pola

anishift/errors.py        # BEZ ZMIAN (kody TRANSLATION_* już są; ew. dodać CANCELLED wariant — jest)

tests/services/translation/   NOWY
├── test_translation_registry.py     # smoke rejestru, lazy import
├── test_translation_dedup.py        # dedup determinizm, mapowanie
├── test_translation_linebreak.py    # podział na realnych PL zdaniach
├── test_translation_chunking.py     # chunker txt
├── test_translation_service.py      # fasada z fake enginem (bez sieci)
├── test_translation_google.py       # _batching ladder z fake callback
├── test_translation_deepl.py        # is_available, mapowanie błędów (mock SDK)
└── test_translation_network.py      # @pytest.mark.network — realne API (opt-in)
```

**Liczby:** ~24 nowe pliki źródłowe + 8 plików testów + 4 zmiany. Żaden plik serwisu > ~250 linii (zasada z planu strategicznego).

---

## B) REGUŁY GLOBALNE (obowiązują KAŻDY nowy plik)

Z `python` skill + CLAUDE.md (zweryfikowane przez subagenta):

1. **Linia 1: `"""docstring modułu."""`**, potem `from __future__ import annotations`.
2. **Importy 5 grup** (I001): future → stdlib → third-party → first-party absolutne → relatywne. Pusta linia między grupami, sortowane.
3. **`__all__`** w każdym module publicznym i `__init__.py` — sorted lista stringów z trailing comma.
4. **Lowercase generics** (`list[str]`, `dict[K,V]`, `tuple[X, ...]`), **`X | None`** nie `Optional`, `-> None` jawne.
5. **`TYPE_CHECKING`** dla `collections.abc` (Callable, Awaitable, Sequence), heavy deps, first-party annotation-only. **NIGDY `Final`/`Literal` w TYPE_CHECKING** (runtime values).
6. **`Final[...]` + docstring pod KAŻDĄ stałą**; grupowanie w `# ── Constants ──` (em-dash U+2500, total 80 znaków) tylko w plikach >200 linii.
7. **dataclass:** value object = `@dataclass(frozen=True, slots=True)`; mutowalny raport = `@dataclass(slots=True)`; `field(default_factory=...)` dla mutowalnych defaultów; `__slots__` niejawnie przez `slots=True`; pola dokumentowane w `Attributes:` class-docstring (nie per-field).
8. **Błędy:** message w zmiennej `msg = f"..."; raise XError(msg)` (EM101/102); `raise X from exc` (B904); nazwa kończy się `Error` (N818); **NIE blind `except Exception`** (BLE001) — łapać precyzyjnie; **NIE `except (A, B):` łączone** (ruff 0.15.21 bug — rozbić na osobne `except`); guard clauses, early return, max 2 poziomy zagnieżdżeń.
9. **Docstringi Google-style:** publiczny moduł (+Usage gdzie sensowne), publiczna klasa ZAWSZE (+Attributes), publiczna metoda/funkcja ZAWSZE, `__init__` z logiką, `__post_init__` walidujący; NIE typy w docstringu (są w sygnaturze).
10. **Logger:** loguru `{}` placeholdery (nie f-string, G004): `logger.debug("engine created: {}", engine_id)`.
11. **Zależności:** wszystko już w `pyproject.toml` — **zero `uv add`**.
12. **`# type: ignore[code]`** zawsze z kodem.

---

## C) SSOT — JEDNO ŹRÓDŁO PRAWDY (user podkreślił mocno)

Każde „źródło prawdy" ma DOKŁADNIE JEDNO miejsce. Zero duplikacji:

| Byt | Jedyne źródło | Kto derywuje (import, NIE przepisuje) |
|---|---|---|
| **Lista silników** (`google`, `deepl`, `llm`) | `engines/__init__.py`: `TranslationEngineId` (Literal) + `_REGISTRY` | panel `/settings` (przez `available_engine_ids()`), fasada (`create_engine`), walidacja user_settings, testy |
| **Limit znaków per silnik** | `constants.py` KAŻDEGO silnika (`google/constants.py` `MAX_CHARS_PER_REQUEST`, `deepl/constants.py`) | batching silnika (czyta swoją stałą) |
| **Mapowanie języków DeepL** | `deepl/_lang_codes.py` `to_deepl_code()` | tylko `deepl/service.py` |
| **Domyślny batch/retry/concurrency (bazowe)** | `translation/constants.py` | `TranslationConfig` defaults; per-silnik override w silniku |
| **Domyślne per-silnik** (google conservative) | `constants.py` silnika | `GoogleConfig`/`DeeplConfig` defaults |
| **System prompt LLM (numeracja)** | `engines/llm/constants.py` `SYSTEM_PROMPT` | tylko `llm/service.py` |
| **Reguły podziału linii** (spójniki, limit) | `linebreak.py` (stałe Final) | tylko `linebreak.py` (+ etap 7 woła funkcję) |

**Dodanie nowego silnika (np. przyszły provider LLM albo nowy tłumacz):**
1. Nowy podfolder `engines/<nowy>/` (5 plików wg wzorca silnika).
2. JEDEN wpis w `_REGISTRY` + dopisanie do `TranslationEngineId` Literal (JEDEN plik `engines/__init__.py`).
3. Koniec. Panel, walidacja, pipeline dostają go automatycznie przez `available_engine_ids()`.

**Zero zmian gdzie indziej.** Test inwariantu (`test_translation_registry.py`) pilnuje `set(get_args(TranslationEngineId)) == set(available_engine_ids())`.

⚠️ **Likwidacja obecnej duplikacji:** `settings_panel.py:33` ma dziś statyczną `_TRANSLATION_ENGINES = ("google", "deepl", "llm")`. Etap 4 ją USUWA — panel importuje `available_engine_ids()`.

---

## D) PLIKI DOMENY

### D.1 `errors.py` — SKOPIUJ z MangaShift + adaptuj bazę

**Skąd:** SKOPIUJ z `MangaShift/mangashift/services/translation/errors.py`, podmień:
- `from mangashift.errors import FatalError, MangaShiftError, TransientError` → `from anishift.errors import AniShiftError, FatalError, TransientError`
- Baza `MangaShiftError` → `AniShiftError`.

**Zawartość** (6 klas, liść — importuje tylko `anishift.errors`):

```python
"""Translation domain exception hierarchy.

All errors inherit from :class:`anishift.errors.AniShiftError`. Config, quota
and auth errors mix in :class:`anishift.errors.FatalError` (non-retryable).
Rate-limit mixes in :class:`anishift.errors.TransientError` (retryable).
"""
from __future__ import annotations
from anishift.errors import AniShiftError, FatalError, TransientError

class TranslationError(AniShiftError):
    """Base class for every translation-domain failure."""

class TranslationEngineError(TranslationError):
    """An engine failed to produce a translation."""

class TranslationConfigError(TranslationError, FatalError):
    """Invalid translation configuration (non-retryable)."""

class TranslationRateLimitError(TranslationError, TransientError):
    """Provider rate-limit hit (HTTP 429/503) — retryable."""

class TranslationQuotaError(TranslationError, FatalError):
    """Provider character quota exhausted — non-retryable until reset."""

class TranslationAuthError(TranslationError, FatalError):
    """Invalid or missing API key — non-retryable."""

__all__ = [ ... 6 nazw sorted ... ]
```

⚠️ **Uwaga na konstruktor:** `AniShiftError.__init__(message="", *, context=None)` różni się od `MangaShiftError`. Podklasy nadal działają — `TranslationConfigError(msg)` przekazuje `message` pozycyjnie, `AniShiftError` buduje domyślny `ErrorContext(UNKNOWN, msg)`. To OK dla guardów rejestru. Gdzie chcemy kod domenowy w `ErrorContext` (np. do runnera), rzucamy z `context=ErrorContext(code=ErrorCode.TRANSLATION_FAILED, ...)` — patrz fasada/runner. **Ulepszenie względem MangaShift:** MangaShift errors są proste stringi; AniShift może nieść `ErrorContext` z `ErrorCode` dla spójności z runnerem (który czyta `exc.context.code`). Rozstrzygnięcie: klasy jak wyżej (proste), a fasada mapuje na `TranslationError(context=...)` tam gdzie trafia do runnera.

### D.2 `constants.py` — SKOPIUJ + rozszerz

**Skąd:** SKOPIUJ z `MangaShift/.../constants.py`, dołóż concurrency i target lang.

```python
"""Translation domain constants. No provider secrets, no engine names."""
from __future__ import annotations
from typing import Final

DEFAULT_TARGET_LANG: Final[str] = "pl"
"""Default target language for translation."""

DEFAULT_SOURCE_LANG: Final[str] = "auto"
"""Default source language; ``auto`` lets the provider detect it."""

DEFAULT_BATCH_SIZE: Final[int] = 50
"""Lines joined into one provider request (subtitle batching by line count)."""

DEFAULT_MAX_CHARS: Final[int] = 4500
"""Per-request character budget fallback (engines override with their own limit)."""

DEFAULT_MAX_RETRIES: Final[int] = 3
"""Retry attempts on transient errors before giving up."""

DEFAULT_CONCURRENCY: Final[int] = 3
"""Concurrent batches per file (semaphore); conservative for API rate limits."""

__all__ = [ ... sorted ... ]
```

⚠️ Nazwy silników NIE tu (żyją w rejestrze — SSOT). Klucze API NIE tu.

### D.3 `config.py` — SKOPIUJ + adaptuj pola

**Skąd:** SKOPIUJ z `MangaShift/.../config.py` (forward-compatible dataclass z `__init__` custom, warn na unknown keys, guard na wymagane pola). Podmień importy `mangashift.`→`anishift.`. Dostosuj pola.

**Zawartość:** `@dataclass(slots=True, init=False) TranslationConfig`:
- `engine: str` — WYMAGANY, bez defaultu (front/panel decyduje; guard rzuca `TranslationConfigError` gdy pusty).
- `source_lang: str = DEFAULT_SOURCE_LANG`
- `target_lang: str = DEFAULT_TARGET_LANG`  ⚠️ (MangaShift ma `source_lang` wymagany — AniShift daje default `auto`, bo AniShift zawsze wykrywa źródło; `target_lang` z defaultem `pl`)
- `batch_size: int = DEFAULT_BATCH_SIZE`
- `max_chars_per_request: int = DEFAULT_MAX_CHARS`
- `max_retries: int = DEFAULT_MAX_RETRIES`
- `concurrency: int = DEFAULT_CONCURRENCY`
- `api_key: str = ""` — dla silników wymagających klucza (deepl); pusty dla google. Wstrzykiwany w composition root z `Settings`.

Custom `__init__(**kwargs)`: warn na unknown keys, guard `if not kwargs.get("engine"): raise TranslationConfigError(...)`, potem przypisanie pól z defaultami. Wzorzec 1:1 z MangaShift (tylko `source_lang` przestaje być wymagany — usuń jego guard, ma default `auto`).

**Ulepszenie:** MangaShift `TranslationConfig` NIE ma `concurrency` ani `api_key` (bo używa secret_provider). AniShift dodaje oba (concurrency z wymagań R7, api_key zamiast secret_provider — §4 wymagań-v2).

### D.4 `types.py` — PRZEPISZ (adaptacja do modelu etapu 3)

**Skąd:** BAZA z `MangaShift/.../types.py` (`BatchedLine`), ale `LineTranslation`/`TranslationResult` PRZEPISZ pod model AniShift (`TranslatedLine`, `FileTranslation` — patrz wymagania-v2 §3).

```python
"""Translation domain value types (plain dataclasses, no pydantic)."""
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class BatchedLine:
    """One line result from an engine batch, with a success flag.

    Attributes:
        text: Translated text, or the source text when the line failed.
        detected_lang: Source language the provider auto-detected; ``None`` when
            not reported.
        ok: ``False`` when the line was padded with its source on failure.
    """
    text: str
    detected_lang: str | None = None
    ok: bool = True

@dataclass(frozen=True, slots=True)
class TranslatedLine:
    """One translated spoken line: source paired with its Polish rendering.

    Attributes:
        start: Start time in ms, copied from the source SpokenLine.
        end: End time in ms, copied from the source SpokenLine.
        source_text: Original (single-line) text fed to the provider.
        text: Translated single-line text (for the narrator / TTS).
        lines: Translated text re-split into on-screen verses (for displayed
            subtitles). For spoken lines this is ``(text,)``.
        style: Style name copied from the source SpokenLine.
        ok: ``False`` when translation failed and text fell back to source.
    """
    start: int
    end: int
    source_text: str
    text: str
    lines: tuple[str, ...]
    style: str
    ok: bool = True

@dataclass(slots=True)
class FileTranslation:
    """Result of translating one file's spoken + displayed streams.

    Attributes:
        spoken: Translated narrator lines, in input order.
        displayed: Translated visible-texts of displayed events, in event order.
        engine_id: Id of the engine that actually produced the result (after
            any fallback).
        target_lang: Target language code.
        unique_lines: Distinct lines after deduplication.
        total_lines: All lines before deduplication.
        api_calls: Real provider requests issued (dedup savings show here).
        failed_lines: Lines that fell back to source (partial failure).
        error: Set only on a hard failure of the whole file (fallback chain
            exhausted); the file is then reported failed.
    """
    spoken: tuple[TranslatedLine, ...] = ()
    displayed: tuple[str, ...] = ()
    engine_id: str = ""
    target_lang: str = "pl"
    unique_lines: int = 0
    total_lines: int = 0
    api_calls: int = 0
    failed_lines: int = 0
    error: str | None = None

    @property
    def is_success(self) -> bool:
        """True when the file translated without a hard error."""
        return self.error is None

__all__ = ["BatchedLine", "FileTranslation", "TranslatedLine"]
```

### D.5 `protocols.py` — PRZEPISZ (async→sync)

**Skąd:** BAZA z `MangaShift/.../protocols.py`, ale **async→sync** (świadome odstępstwo R3). Usuń `LlmCompleter` z domeny? NIE — zostaje (llm engine go potrzebuje, etap 5). Usuń `SecretProvider` (wymagania-v2 §4 — AniShift nie ma UI-store BYOK).

⚠️ **UWAGA — kod poniżej pokazuje wariant z inline `engine_id`/`is_available`, ale OSTATECZNE rozstrzygnięcie (patrz „Poprawka do D.5" niżej) to `TranslationEngine(EngineInfo, Protocol)` z bazą `EngineInfo` z nowego `services/_base.py`.** Implementując: stwórz `services/_base.py` (SKOPIUJ z MangaShift), zaimportuj `EngineInfo`, i `class TranslationEngine(EngineInfo, Protocol):` BEZ powtarzania `engine_id`/`is_available` (dziedziczy je z EngineInfo). Reszta metod (`translate_batch`, `close`) jak w kodzie.

```python
"""Engine contract for the translation domain (sync).

``TranslationEngine`` is the contract every engine satisfies; the facade only
talks to this protocol. ``LlmCompleter`` is the minimal LLM contract the LLM
engine depends on — injected from the composition root so translation never
imports ``anishift.services.llm`` directly (independence contract).
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from anishift.services.translation.types import BatchedLine

@runtime_checkable
class TranslationEngine(Protocol):
    """Sync contract for a translation engine.

    The facade hands each engine an already-chunked batch of single-line texts
    and a caller language code; the engine returns one ``BatchedLine`` per input
    line, same order (failed lines carry source + ``ok=False``).
    """
    @property
    def engine_id(self) -> str:
        """Stable engine identifier (registry key)."""
        ...
    @property
    def is_available(self) -> bool:
        """Whether the engine can be used (key present, deps installed)."""
        ...
    def translate_batch(self, texts: list[str], *, source_lang: str, target_lang: str) -> list[BatchedLine]:
        """Translate one batch; output length must equal input length."""
        ...
    def close(self) -> None:
        """Release resources held by the engine."""
        ...

@runtime_checkable
class LlmCompleter(Protocol):
    """Minimal LLM contract the LLM translation engine depends on (sync).

    Injected from the composition root. The engine knows only this protocol,
    never the concrete LLM service (arrives in stage 5).
    """
    def complete(self, system: str, user: str) -> str:
        """Run a single chat completion and return the assistant text."""
        ...

__all__ = ["LlmCompleter", "TranslationEngine"]
```

⚠️ **Odstępstwa od MangaShift protocols:**
- MangaShift ma `TranslationEngine(EngineInfo, Protocol)` gdzie `EngineInfo` (`services/_base.py`) daje `engine_id`/`is_available`. AniShift **nie ma** `services/_base.py`. Rozstrzygam: **inline `engine_id`/`is_available` w Protocolu** (nie tworzę `_base.py` dla jednego użycia — YAGNI; gdyby TTS/llm w etapach 5/6 potrzebowały wspólnej bazy, wtedy wydzielić). Alternatywa: stwórz `anishift/services/_base.py` z `EngineInfo` teraz, skoro etapy 5/6 też będą go potrzebować. **Rozstrzygam ostatecznie: STWÓRZ `anishift/services/_base.py`** — SKOPIUJ z `MangaShift/mangashift/services/_base.py` (podmiana docstringu), bo to fundament pod 3 rejestry (translation/llm/tts) i etap 4 jest pierwszy — lepiej ustawić wzorzec teraz. `TranslationEngine(EngineInfo, Protocol)`.
- MangaShift `initialize()`/`cleanup()` async → AniShift sync `close()` (jedna metoda cleanup wystarcza; init leniwy w silniku). Silnik google/deepl tworzy klienta leniwie w `translate_batch` (pierwsze użycie) lub w `__init__`.
- Usunięty `SecretProvider`.

**Poprawka do D.5:** dodaj `anishift/services/_base.py` (SKOPIUJ z MangaShift), i `TranslationEngine(EngineInfo, Protocol)` importując `EngineInfo`. Wtedy Protocol nie powtarza `engine_id`/`is_available`.

### D.6 `dedup.py` — PRZEPISZ z mm_avh (logika) w kształcie AniShift

**Skąd:** LOGIKA z `mm_avh/modules/translator.py:161-170` (dedup przez `dict.fromkeys`, `translation_map`, redistribute). Kształt NAPISZ OD ZERA (mm_avh miał to zaszyte w metodzie, MangaShift nie ma osobnego `dedup.py`). Czyste funkcje, testowalne bez sieci (N7).

```python
"""Deduplicate identical lines so each unique text is translated once.

A line repeated N times costs one provider request, not N. The mapping is
deterministic (``dict.fromkeys`` preserves first-seen order), so the same input
always yields the same unique set and redistribution (N2).
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class DedupResult:
    """Deduplicated lines plus the mapping back to every occurrence.

    Attributes:
        unique: Distinct non-empty lines in first-seen order.
        index_map: For each original line index, the position in ``unique`` it
            maps to, or ``-1`` when the line was empty (skipped).
    """
    unique: tuple[str, ...]
    index_map: tuple[int, ...]

def deduplicate(lines: list[str]) -> DedupResult:
    """Collapse repeated lines to a unique set with a redistribution map.

    Args:
        lines: Cleaned single-line texts in order.

    Returns:
        The unique lines and a per-index map back onto them.
    """
    order: dict[str, int] = {}
    index_map: list[int] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            index_map.append(-1)
            continue
        if line not in order:
            order[line] = len(order)
        index_map.append(order[line])
    return DedupResult(unique=tuple(order), index_map=tuple(index_map))

def redistribute(translations: list[str], result: DedupResult, sources: list[str]) -> list[str]:
    """Fill every original position from the translated unique lines.

    Args:
        translations: Translated text per unique line (same length/order as
            ``result.unique``).
        result: The dedup result carrying the index map.
        sources: Original lines, used to pass empty lines through unchanged.

    Returns:
        One translated string per original line.
    """
    out: list[str] = []
    for position, source in zip(result.index_map, sources, strict=True):
        if position < 0:
            out.append(source)
        else:
            out.append(translations[position])
    return out

__all__ = ["DedupResult", "deduplicate", "redistribute"]
```

⚠️ Dedup działa na `line` (nie `line.strip()`) jako klucz — zachowuje dokładny tekst (mm_avh też trzymał marked lines). Empty → passthrough. Determinizm: `dict` insertion order (Python 3.7+).

### D.7 `_retry.py` — NAPISZ OD ZERA (mały sync retry)

**Skąd:** NAPISZ OD ZERA. MangaShift używa `utils/_retry.py` (tenacity, async) — AniShift `utils/` nietykalny + tenacity nie jest zależnością (wymagania-v2 §7.2). Wzorzec backoff z `extraction/service.py` (ręczna pętla) i idea z MangaShift `_BackoffWait`. Sync, ~35 linii.

```python
"""Small sync retry helper for network translation engines.

No tenacity dependency (utils/ is untouchable, tenacity is not a dependency).
Retries a callable on a given exception type with linear or exponential backoff.
"""
from __future__ import annotations
import time
from collections.abc import Callable
from typing import Literal, TypeVar

_T = TypeVar("_T")
BackoffKind = Literal["linear", "exponential"]

def call_with_retry(
    func: Callable[[], _T],
    *,
    max_attempts: int,
    retry_on: type[BaseException] | tuple[type[BaseException], ...],
    backoff: BackoffKind = "exponential",
    base_s: float = 1.0,
    cap_s: float | None = 15.0,
) -> _T:
    """Call ``func`` up to ``max_attempts`` times, backing off on ``retry_on``.

    Args:
        func: Zero-arg callable to invoke.
        max_attempts: Total number of calls (not extra retries).
        retry_on: Exception type(s) that trigger a retry; anything else raises.
        backoff: ``linear`` (base*n) or ``exponential`` (base*2**(n-1)).
        base_s: Base delay in seconds.
        cap_s: Optional upper bound on a single wait.

    Returns:
        The value returned by ``func``.

    Raises:
        BaseException: The last ``retry_on`` error when attempts run out, or any
            non-retryable error immediately.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except retry_on:
            if attempt >= max_attempts:
                raise
            raw = base_s * attempt if backoff == "linear" else base_s * (2 ** (attempt - 1))
            wait = raw if cap_s is None else min(raw, cap_s)
            time.sleep(wait)
    msg = "call_with_retry exhausted without returning"  # unreachable guard
    raise RuntimeError(msg)

__all__ = ["BackoffKind", "call_with_retry"]
```

⚠️ Ostatni `raise RuntimeError` jest nieosiągalny (pętla albo zwróci, albo re-raise), ale mypy strict wymaga jawnego return/raise na końcu.

### D.8 `linebreak.py` — NAPISZ OD ZERA (własny algorytm R6b)

**Skąd:** NAPISZ OD ZERA. Idea `split_at_half` PODEJRZYJ z `scripts/tmp/srt_equalizer_reference.py:153`. Bazę cięcia po frazach z `text_chunker.py` `LatinPunctuator.getPhrases`. Reguły hierarchii + ochronne wg wymagań-v2 §6.3.

**Pełny kod (~55 linii):**

```python
"""Re-split a translated line into readable subtitle verses.

We never reconstruct the source layout (Polish syntax differs); we build a new
readable split. Cut hierarchy: strong punctuation -> weak punctuation ->
conjunction/preposition -> closest to centre on a word boundary (the
``split_at_half`` idea, borrowed from srt_equalizer). Protective rules: max line
length, max two verses, no orphan words, do not split fixed phrases.
"""
from __future__ import annotations
import re
from typing import Final

# ── Constants ──────────────────────────────────────────────────────────────
DEFAULT_MAX_CHARS: Final[int] = 42
"""Default readable line length for on-screen subtitles (Netflix/BBC-ish)."""

MAX_LINES: Final[int] = 2
"""Maximum on-screen verses before we accept an over-length line."""

_STRONG_PUNCT: Final[re.Pattern[str]] = re.compile(r"[.!?…:]")
"""Strong sentence punctuation; best cut points (cut AFTER the mark)."""

_WEAK_PUNCT: Final[re.Pattern[str]] = re.compile(r"[,;—]")
"""Weak punctuation incl. Polish dialogue dash; second-best cut points."""

_CONJUNCTIONS: Final[frozenset[str]] = frozenset(
    {"i", "oraz", "ale", "że", "więc", "bo", "aby", "lub", "a", "czy", "gdy", "jak", "kiedy", "który", "ponieważ"}
)
"""Words we prefer to cut BEFORE (keeps the clause head with its clause)."""

_NON_BREAKING_HEADS: Final[frozenset[str]] = frozenset(
    {"w", "we", "z", "ze", "na", "do", "od", "po", "za", "o", "u", "pod", "nad", "przy", "bez", "dla"}
)
"""One-letter/short prepositions that must stay glued to the next word."""


def split_line(text: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> tuple[str, ...]:
    """Split ``text`` into readable verses; return one entry when it fits."""
    text = text.strip()
    if len(text) <= max_chars or " " not in text:
        return (text,)
    point = _best_cut(text, max_chars)
    left = text[:point].strip()
    right = text[point:].strip()
    if not left or not right:
        return (text,)
    return _cap((left, right), max_chars)


def _cap(parts: tuple[str, ...], max_chars: int) -> tuple[str, ...]:
    """Recurse into any part still over ``max_chars`` (bounded by MAX_LINES)."""
    out: list[str] = []
    for part in parts:
        out.extend(split_line(part, max_chars=max_chars) if len(part) > max_chars else (part,))
    return tuple(out)


def _best_cut(text: str, max_chars: int) -> int:
    """Return the best space index to cut at, honouring the hierarchy."""
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    center = len(text) // 2
    scored: list[tuple[float, int]] = []
    for i in spaces:
        prev_word = text[:i].rsplit(" ", 1)[-1]
        next_word = text[i + 1 :].split(" ", 1)[0].strip(".,!?…:;—")
        if prev_word.lower().rstrip(".,!?…:;—") in _NON_BREAKING_HEADS:
            continue  # do not split a preposition from its noun
        distance = abs(i - center)
        if _STRONG_PUNCT.search(prev_word[-1:]):
            distance /= 8  # strong punctuation just before the space wins big
        elif _WEAK_PUNCT.search(prev_word[-1:]):
            distance /= 4
        elif next_word.lower() in _CONJUNCTIONS:
            distance /= 2  # cut before a conjunction
        if _is_orphan(text[:i], text[i + 1 :]):
            distance *= 10  # penalise orphans hard
        scored.append((distance, i))
    if not scored:
        return _greedy_cut(text, max_chars)
    return min(scored, key=lambda pair: pair[0])[1]


def _is_orphan(left: str, right: str) -> bool:
    """True when either side is a single word (an orphan verse)."""
    return " " not in left.strip() or " " not in right.strip()


def _greedy_cut(text: str, max_chars: int) -> int:
    """Fallback: last space at or before ``max_chars`` (greedy)."""
    cut = text.rfind(" ", 0, max_chars + 1)
    return cut if cut > 0 else text.find(" ")


__all__ = ["DEFAULT_MAX_CHARS", "MAX_LINES", "split_line"]
```

⚠️ Algorytm celowo prosty (~55 linii), heurystyczny. Test na realnych PL zdaniach (M) potwierdzi jakość — jeśli daje słabe cięcia, dostrajamy wagi/listy. To jedyny NAPISANY OD ZERA algorytm — reszta to kopie.

### D.9 `chunking.py` — PRZEPISZ z text_chunker.py (wg python instructions)

**Skąd:** PRZEPISZ z `scripts/tmp/text_chunker.py` (LatinPunctuator + CharBreaker + WordBreaker). Doprowadź do standardu: typy, docstringi Google, `from __future__`, `Final`, lowercase generics, snake_case (obecny kod ma camelCase `getParagraphs`, `wordLimit` — zamień na `get_paragraphs`, `word_limit`). Domyślne: `sentence_length=750`, `chunk_limit=250` (R6).

**Struktura po przepisaniu:**
- `class LatinPunctuator:` — metody `get_paragraphs`, `get_sentences`, `get_phrases`, `get_words`, `_recombine`. Regexy jako `Final` stałe na poziomie modułu (nie inline w metodach). Docstringi.
- `class CharBreaker:` — `break_text` po znakach (dla txt).
- `class WordBreaker:` — `break_text` po słowach.
- `def chunk_text(text: str, *, method: Literal["char", "word"] = "char", limit: int = 750) -> list[str]:` — publiczna funkcja.

⚠️ To narzędzie dla ścieżki txt (mini-ficzer). Zgodnie z wymaganiami-v2 §12, ścieżka txt główna używa istniejącego `txt_to_spoken`; `chunking.py` jest dostępny jako opcja finezyjniejszego cięcia. **Jeśli implementacja pokaże że `txt_to_spoken` wystarcza w 100%, `chunking.py` można pominąć w etapie 4** (YAGNI) — ale plan go opisuje bo wymaganie R6 go wymienia. Rozstrzygnięcie do implementatora: napisz `chunking.py` tylko jeśli mini-ficzer txt→SRT wymaga cięcia po znakach lepszego niż `txt_to_spoken`. **Domyślnie: napisz, jest tani i wymagany R6.**

### D.10 `service.py` — PRZEPISZ (async→sync + fallback + dedup + linebreak)

**Skąd:** BAZA z `MangaShift/.../service.py` (fasada, cache silnika, `translate` per target). PRZEPISZ na sync + dodaj: dedup (D.6), fallback po łańcuchu (R9), produkcję `FileTranslation`, obsługę spoken+displayed, `cancel`.

**Sygnatury (ostateczne, spójne z I.2):**

```python
class TranslationService:
    """Sync translation facade over one engine with a fallback chain.

    Deduplicates lines, delegates a whole file's unique set to the engine, and on
    a hard engine failure retranslates the whole file with the next available
    engine in the chain. Accepts an injected engine for tests / the LLM engine.
    """
    __slots__ = ("_injected", "config", "fallback_chain")

    def __init__(
        self,
        config: TranslationConfig,
        *,
        engine: TranslationEngine | None = None,
        fallback_chain: tuple[str, ...] = (),
    ) -> None:
        """Create the facade; optionally inject an engine (tests / LLM DI)."""
        self.config = config
        self._injected = engine
        self.fallback_chain = fallback_chain

    def translate_file(
        self,
        spoken: list[SpokenLine],
        displayed: list[str],
        *,
        source_lang: str = "auto",
        target_lang: str = "pl",
        cancel: threading.Event | None = None,
    ) -> FileTranslation:
        """Translate one file's spoken + displayed streams with dedup + fallback."""
```

**Ciało `translate_file` (rozpisane konkretnie):**
1. **E2 guard:** `if not spoken and not displayed: return FileTranslation(target_lang=target_lang)`.
2. **Łańcuch:** `chain = (self.config.engine, *self.fallback_chain)`; dedup zachowując kolejność (`dict.fromkeys`). Jeśli `self._injected is not None` → chain = `(self._injected.engine_id,)` (wstrzyknięty silnik, jeden, bez fallbacku — tak jak MangaShift LLM DI).
3. **Iteracja po silnikach:**
   ```python
   spoken_texts = [line.text for line in spoken]
   last_error: str | None = None
   for engine_id in chain:
       if cancel is not None and cancel.is_set():
           raise TranslationError(context=ErrorContext(code=ErrorCode.CANCELLED, message="translation cancelled"))
       engine = self._build_engine(engine_id)
       if not engine.is_available:
           last_error = f"engine {engine_id} unavailable"
           continue
       try:
           return self._run(engine, spoken, spoken_texts, displayed, source_lang=source_lang, target_lang=target_lang)
       except TranslationQuotaError as exc: last_error = str(exc); continue
       except TranslationRateLimitError as exc: last_error = str(exc); continue
       except TranslationAuthError as exc: last_error = str(exc); continue
       except TranslationEngineError as exc: last_error = str(exc); continue
       finally:
           engine.close()
   return FileTranslation(target_lang=target_lang, error=last_error or "no available translation engine")
   ```
   ⚠️ Osobne `except` per typ (ruff bug — NIE łączyć `except (A,B)`).
   ⚠️ `finally: engine.close()` — zwalnia klienta po każdej próbie (nowy silnik per fallback).

4. **`_build_engine(engine_id)`:** jeśli `self._injected` — zwróć go. Inaczej: zbuduj kopię configu z podmienionym `engine` (`dataclasses.replace` NIE zadziała — config ma custom `__init__`; więc `TranslationConfig(engine=engine_id, source_lang=..., target_lang=..., batch_size=..., ...)` z pól `self.config`), potem `create_engine(new_config)`. ⚠️ To ROZSTRZYGA „jak zmienić engine per fallback": nowy config z innym `engine`, nowy silnik przez rejestr. Cache pomijamy (KISS — plik przetwarzany raz, fallback rzadki; cache silnika to przedwczesna optymalizacja).

**`_run(engine, spoken, spoken_texts, displayed, *, source_lang, target_lang)` — jeden przebieg jednym silnikiem:**
```python
def _run(self, engine, spoken, spoken_texts, displayed, *, source_lang, target_lang) -> FileTranslation:
    api_calls = 0; failed = 0
    # SPOKEN
    dedup_s = deduplicate(spoken_texts)
    batched_s = engine.translate_batch(list(dedup_s.unique), source_lang=source_lang, target_lang=target_lang) if dedup_s.unique else []
    api_calls += 1 if dedup_s.unique else 0
    unique_translated_s = [bl.text for bl in batched_s]
    unique_ok_s = [bl.ok for bl in batched_s]
    full_translated_s = redistribute(unique_translated_s, dedup_s, spoken_texts)
    full_ok_s = redistribute_flags(unique_ok_s, dedup_s)   # helper: map ok flags back
    spoken_lines = tuple(
        TranslatedLine(start=s.start, end=s.end, source_text=s.text, text=t, lines=(t,), style=s.style, ok=ok)
        for s, t, ok in zip(spoken, full_translated_s, full_ok_s, strict=True)
    )
    failed += sum(1 for ok in full_ok_s if not ok)
    # DISPLAYED (list[str] -> list[str])
    dedup_d = deduplicate(displayed)
    batched_d = engine.translate_batch(list(dedup_d.unique), source_lang=source_lang, target_lang=target_lang) if dedup_d.unique else []
    api_calls += 1 if dedup_d.unique else 0
    displayed_out = tuple(redistribute([bl.text for bl in batched_d], dedup_d, displayed))
    return FileTranslation(
        spoken=spoken_lines, displayed=displayed_out, engine_id=engine.engine_id, target_lang=target_lang,
        unique_lines=len(dedup_s.unique) + len(dedup_d.unique),
        total_lines=len(spoken_texts) + len(displayed),
        api_calls=api_calls, failed_lines=failed,
    )
```

⚠️ **Nowy helper `redistribute_flags`** — potrzebny bo `redistribute` bierze `sources` (stringi) do passthrough, a flagi `ok` nie mają passthrough (empty line → ok=True, bo nie tłumaczona). Dopisz do `dedup.py`:
```python
def redistribute_flags(flags: list[bool], result: DedupResult) -> list[bool]:
    """Map per-unique ok flags back to every original line (empty -> True)."""
    return [True if position < 0 else flags[position] for position in result.index_map]
```

**Batchowanie + concurrency:** silnik `translate_batch` bierze CAŁY unique-set i sam go batchuje (google `_batching` z semaphore/concurrency, deepl lista + byte-chunk). Fasada woła `translate_batch` raz per tor (spoken, displayed). ⚠️ `api_calls` w raporcie to liczba wywołań `translate_batch` fasady (1 spoken + 1 displayed max = 2), NIE realnych requestów HTTP (te są wewnątrz silnika, zależne od batch_size). To wystarcza do pokazania zysku dedupu w raporcie (unique < total). Jeśli chcemy realną liczbę requestów — silnik musiałby ją raportować; YAGNI w etapie 4, `api_calls` = wywołania fasady.

**Ctrl+C:** `cancel` sprawdzany na początku każdej iteracji łańcucha (kod wyżej). Silnik google (async) — `asyncio.run` nie jest przerywany w połowie, ale między plikami/silnikami cancel działa. To wystarcza (spójne z ekstrakcją, która sprawdza cancel między liniami stdout).

**Ulepszenia względem MangaShift:**
- async→sync (cała fasada).
- fallback łańcuch (MangaShift nie ma — ma per-language, my per-engine-chain).
- dedup wbudowany (MangaShift dedup jest gdzie indziej / brak).
- spoken+displayed dwa tory (MangaShift ma jeden „texts").
- `FileTranslation` raport z api_calls/unique/failed.

### D.11 `__init__.py` — SKOPIUJ + dostosuj eksporty

**Skąd:** SKOPIUJ wzorzec z `MangaShift/.../__init__.py` (thin re-exports, no heavy SDK). Dostosuj do typów AniShift.

```python
"""Translation service public surface (thin re-exports; engines lazy-load)."""
from __future__ import annotations
from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.engines import TranslationEngineId, available_engine_ids
from anishift.services.translation.errors import (
    TranslationAuthError, TranslationConfigError, TranslationEngineError,
    TranslationError, TranslationQuotaError, TranslationRateLimitError,
)
from anishift.services.translation.service import TranslationService
from anishift.services.translation.types import FileTranslation, TranslatedLine

__all__ = [ ... sorted ... ]
```

⚠️ **NIE importuj `create_engine`/silników tutaj** — lazy (N6). `available_engine_ids()` jest lekki (czyta `_REGISTRY`, nie importuje silników).

---

## E) REJESTR SILNIKÓW — `engines/__init__.py`

**Skąd:** SKOPIUJ z `MangaShift/.../engines/__init__.py` KROPKA W KROPKĘ, podmień `mangashift.`→`anishift.`, dodaj logger (kanon każe, MangaShift nie ma — ULEPSZ), usuń `secret_provider` (wymagania-v2 §4).

**Pełny plik:**

```python
"""Translation engine factory: registry-based engine construction.

Entry point: ``create_engine(config)`` -> concrete ``TranslationEngine``.
"""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Final, Literal

from anishift.services.translation.errors import TranslationConfigError
from anishift.utils.logger import get_logger

__all__ = ["TranslationEngineId", "available_engine_ids", "create_engine"]

logger = get_logger(__name__)

if TYPE_CHECKING:
    from anishift.services.translation.config import TranslationConfig
    from anishift.services.translation.protocols import TranslationEngine

TranslationEngineId = Literal["google", "deepl", "llm"]
"""Registry keys of translation engines; higher layers import this, never respell it."""

# engine_id -> (module_path, service_class, config_class)
_REGISTRY: Final[dict[TranslationEngineId, tuple[str, str, str]]] = {
    "google": ("anishift.services.translation.engines.google", "GoogleService", "GoogleConfig"),
    "deepl": ("anishift.services.translation.engines.deepl", "DeeplService", "DeeplConfig"),
    "llm": ("anishift.services.translation.engines.llm", "LlmTranslateService", "LlmTranslateConfig"),
}


def available_engine_ids() -> tuple[TranslationEngineId, ...]:
    """Return the registered translation engine ids (single source of truth)."""
    return tuple(_REGISTRY)


def create_engine(config: TranslationConfig) -> TranslationEngine:
    """Create a translation engine for the given config.

    Engines import lazily so heavy SDKs stay off the domain import path.

    Args:
        config: Facade config; ``config.engine`` selects the registry entry.

    Returns:
        A ``TranslationEngine`` implementation ready to translate.

    Raises:
        TranslationConfigError: If ``config.engine`` is empty, unknown, or is
            ``llm`` (needs an injected completer; build LlmTranslateService
            directly and pass it via ``TranslationService(engine=...)``).
    """
    engine_id = config.engine
    if not engine_id:
        msg = "translation.engine is required"
        raise TranslationConfigError(msg)
    if engine_id not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        msg = f"Unknown translation engine: {engine_id!r}. Available: {available}"
        raise TranslationConfigError(msg)
    if engine_id == "llm":
        msg = "The 'llm' engine needs an injected completer; build LlmTranslateService directly and pass it via TranslationService(engine=...)."
        raise TranslationConfigError(msg)
    module_path, class_name, _config_class = _REGISTRY[engine_id]
    module = importlib.import_module(module_path)
    engine_cls = getattr(module, class_name)
    engine: TranslationEngine = engine_cls(config)
    logger.debug("translation engine created: {} ({})", engine_id, class_name)
    return engine
```

✅ **Logger ZWERYFIKOWANY:** `anishift/utils/logger` eksportuje `get_logger(name) -> Logger` (ten sam interfejs co MangaShift, zweryfikowane w `anishift/utils/logger/__init__.py:70`). Domyślnie OFF wg CLAUDE.md, więc `logger.debug` jest bezpieczny (nic nie zapisuje bez włączenia). Import w grupie first-party. To NIE narusza „utils nietykalne" — tylko czytamy istniejące `get_logger`, nie modyfikujemy utils.

**KLUCZOWE dla SSOT:** `TranslationEngineId` + `_REGISTRY` obok siebie w JEDNYM pliku. Wszystko inne importuje `available_engine_ids()`.

---

## F) SILNIK GOOGLE

Wszystkie 6 plików SKOPIUJ z `MangaShift/.../engines/google/`, podmień importy, **async→sync**, usuń `secret_provider`/`validate_key`.

### F.1 `google/__init__.py` — SKOPIUJ 1:1
Re-export `GoogleConfig` + `GoogleService`. Podmień ścieżki importów. Bez zmian logiki.

### F.2 `google/config.py` — SKOPIUJ 1:1
`@dataclass(slots=True) GoogleConfig(batch_size, max_chars_per_request, max_retries)` + `__post_init__` walidacja. Dodaj `concurrency: int = 1` (google conservative — SSOT domyślnego concurrency google TU, bo google najbardziej rate-limit-wrażliwy, §10 wymagań-v2). Importy `mangashift.`→`anishift.`.

### F.3 `google/constants.py` — SKOPIUJ + dodaj limit
SKOPIUJ (RETRY_BACKOFF_BASE_S, RETRY_MAX_WAIT_S, ZERO_WIDTH, LINE_SEPARATOR, NEWLINE_MARKER). **Dodaj:**
```python
MAX_CHARS_PER_REQUEST: Final[int] = 15000
"""Google Translate hard limit per request (~15000 chars); SSOT of this limit."""
```
⚠️ (MangaShift constants nie miał tego jawnie — GoogleConfig `max_chars` default 4500 był z domeny; AniShift dodaje jawny limit Google 15000 jako SSOT limitu silnika R5a).

### F.4 `google/types.py` — SKOPIUJ 1:1 (pusty, `__all__ = []`)

### F.5 `google/_batching.py` — SKOPIUJ 1:1 (ZOSTAJE ASYNC — googletrans jest async)

⚠️ **DECYZJA ARCHITEKTONICZNA (rozstrzygnięta, koniec sprzeczności):** `_batching.py` **ZOSTAJE ASYNC 1:1 jak w MangaShift.** googletrans 4.x jest async pod spodem — więc `_batching` (który woła googletrans) MUSI być async. Sync jest tylko FASADA (`TranslationService`) i granica silnika: `GoogleService.translate_batch` (sync) owija całość w JEDEN `asyncio.run(...)` na plik (F.6). To jest wzorzec „sync fasada nad async silnikiem, jeden event loop na plik" — świadome, udokumentowane odstępstwo (fasada AniShift jest sync, ale googletrans wymusza async wewnątrz silnika google, jedynego async silnika).

**Skąd:** SKOPIUJ z `MangaShift/mangashift/services/translation/engines/google/_batching.py` **1:1** (funkcje: `_chunks`, `_restore`, `_per_line` (async), `_translate_chunk` (async), `_map_parts`, `translate_lines` (async)). Podmień TYLKO:
- importy `mangashift.`→`anishift.` (import `BatchedLine` z `anishift.services.translation.types`; `LINE_SEPARATOR`/`NEWLINE_MARKER`/`ZERO_WIDTH` z `anishift.services.translation.engines.google.constants`).
- **`except Exception:` → precyzyjne except** (BLE001). MangaShift ma broad `except Exception` w `_per_line` i `_translate_chunk` z komentarzem „debt". AniShift łapie precyzyjnie: silnik google rzuca błędy googletrans (nieznany typ) — więc łap `Exception` TYLKO jeśli nie da się precyzyjniej, ale z komentarzem `# noqa: BLE001` (googletrans nie ma stabilnej hierarchii wyjątków, więc broad-except na granicy zewnętrznej biblioteki JEST uzasadniony — dodaj komentarz „broad: googletrans has no stable exception hierarchy"). ⚠️ To wyjątek od „nie blind except" — dozwolony na granicy zewnętrznego API z komentarzem (engine-standard „broad except tylko na provider boundary z komentarzem"). Jeśli osobne `except` — nie łącz (ruff bug).
- `async def`/`await` — **NIE zmieniaj** (zostają async).

**Sygnatura `translate_lines` (async, bez zmian z MangaShift):**
```python
async def translate_lines(
    texts: list[str], *, batch_size: int, max_chars: int,
    translate_joined: Callable[[str], Awaitable[tuple[str, str | None]]],
) -> list[BatchedLine]:
```
`Callable`/`Awaitable` import w `TYPE_CHECKING` z `collections.abc`.

⚠️ Przy jednoliniowym input NEWLINE_MARKER jest no-op (brak `\n` w tekstach AniShift), ale mechanizm zostaje (bezpieczny, MangaShift-proven). Separator zero-width chroni join batcha — to esencja Google batchingu (test: Google MUSI dostać sklejone, nie rozbite; separator zero-width daje jeden request z wieloma liniami, Google widzi kontekst).

### F.6 `google/service.py` — SKOPIUJ + async→sync + usuń secret/validate

**Skąd:** SKOPIUJ z `MangaShift/.../google/service.py`, przekształć:
- `class GoogleService` implementuje sync Protocol.
- `__init__(self, config)` — bez `secret_provider`. Config: przyjmuje `TranslationConfig | GoogleConfig`, buduje `GoogleConfig` z pól fasady jeśli trzeba (wzorzec MangaShift `isinstance`).
- `engine_id` property = `"google"`.
- `is_available` = zawsze True (google darmowy) — ⚠️ MangaShift zwraca `self._client is not None` (po init); AniShift: `is_available` = True zawsze (klient leniwy, tworzony w translate_batch). Bo panel/walidacja pyta `is_available` PRZED tłumaczeniem — google zawsze dostępny.
- **async→sync na granicy silnika (spójne z F.5):** `_batching.py` zostaje async; `GoogleService.translate_batch` (SYNC, część Protocolu) owija całość w JEDEN `asyncio.run(...)`. To „jeden event loop na plik" — fasada woła `translate_batch` raz na plik z całym unique-setem, więc jeden `asyncio.run` na plik. ⚠️ NIE `asyncio.run` per batch (mm_avh bug `translator.py:141`).
- Usuń `validate_key` (AniShift nie ma secrets validation flow — to MangaShift UI-store).
- **Retry (async, inline w google/service.py):** googletrans jest async, więc `_retry.py` `call_with_retry` (sync, `time.sleep`) NIE nadaje się (blokowałby event loop). Napisz mały async retry inline: `_translate_once` async z pętlą `for attempt in range(max_attempts): try: ... except Exception: await asyncio.sleep(backoff)`. To NIE trafia do `_retry.py` (który jest sync, dla deepl). ~12 linii. Broad `except Exception` na granicy googletrans z komentarzem/`# noqa: BLE001` (googletrans brak stabilnej hierarchii).
- `close()` = drop client reference (sync).

**Struktura (sync fasada silnika + async środek):**
```python
def translate_batch(self, texts: list[str], *, source_lang: str, target_lang: str) -> list[BatchedLine]:
    if not texts:
        return []
    dest = (target_lang or "pl").lower()
    return asyncio.run(self._translate_all(texts, dest=dest))   # JEDEN event loop na plik

async def _translate_all(self, texts: list[str], *, dest: str) -> list[BatchedLine]:
    from googletrans import Translator          # lazy import (N6)
    client = Translator()
    async def _translate_joined(joined: str) -> tuple[str, str | None]:
        return await self._call_with_retry(client, joined, dest=dest)
    return await translate_lines(
        texts, batch_size=self._config.batch_size,
        max_chars=self._config.max_chars_per_request, translate_joined=_translate_joined,
    )
```
Gdzie `_call_with_retry` (async) robi retry z `await asyncio.sleep`. `translate_lines` = async z `_batching.py` (F.5).

⚠️ To jest jedyny async silnik. `asyncio.run` w `translate_batch` (granica sync Protocolu / async googletrans) jest świadomym, udokumentowanym odstępstwem od engine-standard „nie odpalaj asyncio.run wewnątrz engine'a" — bo AniShift fasada jest sync, a googletrans wymusza async; jeden `asyncio.run` na plik jest bezpieczny (nie zagnieżdżony, nie per-batch).

---

## G) SILNIK DEEPL

SKOPIUJ z `MangaShift/.../engines/deepl/`, async→sync, klucz z config (nie secret_provider/env).

### G.1 `deepl/__init__.py` — SKOPIUJ 1:1 (re-export DeeplConfig + DeeplService)

### G.2 `deepl/config.py` — PRZEPISZ (klucz w configu)
```python
@dataclass(slots=True)
class DeeplConfig:
    """Runtime config for the DeepL engine.

    Attributes:
        api_key: DeepL auth key (injected from Settings at the composition root;
            empty disables the engine).
        max_retries: Rate-limit retry attempts.
    """
    api_key: str = ""
    max_retries: int = 3
```
⚠️ MangaShift `DeeplConfig` ma `api_key_env` (nazwa env var) + czyta os.getenv. AniShift: `api_key` wprost (wypełniany z `Settings.deepl_api_key`). Silnik nie sięga do env.

### G.3 `deepl/constants.py` — SKOPIUJ + dodaj limit
```python
MAX_PAYLOAD_BYTES: Final[int] = 128 * 1024
"""DeepL request payload limit (128 KiB); SSOT of this limit."""

RATE_LIMIT_MAX_ATTEMPTS: Final[int] = 3
"""Retry attempts on DeepL 429 before failing."""

RATE_LIMIT_BASE_DELAY_S: Final[float] = 1.0
"""Base backoff delay for DeepL rate-limit retries."""
```
(MangaShift miał te dwie ostatnie jako module-level `_RATE_LIMIT_*` w service.py — przenieś do constants jako Final z docstringami. Usuń `API_KEY_ENV`.)

### G.4 `deepl/types.py` — SKOPIUJ 1:1 (pusty)

### G.5 `deepl/_lang_codes.py` — SKOPIUJ 1:1
`to_deepl_code()` mapowanie (en→EN-US, pt→PT-PT, auto→None). Podmień docstring/importy jeśli trzeba (plik jest self-contained). SSOT mapowania języków DeepL.

### G.6 `deepl/service.py` — SKOPIUJ + async→sync + klucz z config

**Skąd:** SKOPIUJ z `MangaShift/.../deepl/service.py`, przekształć:
- `_map_sdk_error(exc)` — SKOPIUJ 1:1 (mapuje deepl.TooManyRequests→RateLimit, QuotaExceeded→Quota, Authorization→Auth, DeepLException→Engine). Lazy `import deepl`. Łap precyzyjnie (już jest — `isinstance` na konkretne typy).
- `__init__(self, config)` — bez secret_provider. `self._config: DeeplConfig`, `self._client = None`.
- `engine_id` = `"deepl"`.
- `is_available` = `bool(self._config.api_key)` — ⚠️ MangaShift resolwuje przez secret_provider/env; AniShift: `bool(api_key)` z config. Prostsze.
- `_ensure_client` → **sync leniwy init w translate_batch**: jeśli brak klucza → `TranslationAuthError` (JEDNOZNACZNIE — spójne z E3 wymagań „wymuszenie deepl bez klucza = TranslationAuthError" i testem kroku 6; NIE ConfigError); potem `import deepl`; `self._client = deepl.Translator(self._config.api_key)`. Idempotentny (drugie wywołanie nie tworzy klienta od nowa).
- Usuń `validate_key` (httpx usage) — AniShift nie ma secrets validation flow. (⚠️ MangaShift ma `validate_key` z httpx GET /v2/usage — usuwamy, to część UI-store BYOK).
- **async→sync:** MangaShift owija sync SDK w `asyncio.to_thread`. AniShift **jest sync** — woła SDK bezpośrednio (bez to_thread). `translate_batch` sync:
```python
def translate_batch(self, texts, *, source_lang, target_lang) -> list[BatchedLine]:
    if not texts:
        return []
    self._ensure_client()  # raises TranslationAuthError if no key
    target = to_deepl_code(target_lang) or "EN-US"
    source = to_deepl_code(source_lang)
    return call_with_retry(
        lambda: self._translate_once(texts, target, source),
        max_attempts=RATE_LIMIT_MAX_ATTEMPTS,
        retry_on=TranslationRateLimitError,
        backoff="exponential",
        base_s=RATE_LIMIT_BASE_DELAY_S,
    )
```
- `_translate_once`: `try: results = self._client.translate_text(texts, target_lang=target, source_lang=source) except Exception as exc: raise _map_sdk_error(exc) from exc` — ⚠️ tu broad `except Exception` jest na granicy SDK (dozwolone z mapowaniem, jak engine-standard „broad except tylko na provider boundary z komentarzem"). Dodaj komentarz. Zwraca `[BatchedLine(text=r.text, detected_lang=_normalize_lang(...), ok=True) for r in results]`.
- `_normalize_lang` — SKOPIUJ 1:1.
- `close()` = drop client.

**DeepL batchowanie:** DeepL SDK bierze listę i zwraca w kolejności — natywny batch, bez separatorów (R6a: DeepL radzi sobie z raw, nie sklejamy). Ale limit payloadu 128 KiB — jeśli unique-set za duży, podziel na pod-batche po bajtach (`MAX_PAYLOAD_BYTES`). ⚠️ MangaShift deepl NIE dzielił (dawał całość) — AniShift dodaje podział po bajtach dla dużych plików (R5a). Prosty: `_chunk_by_bytes(texts, MAX_PAYLOAD_BYTES)` → pętla po pod-batchach → concat wyników. Zachowuje kolejność.

---

## H) SILNIK LLM (SZKIELET — realizacja etap 5)

⚠️ **KLUCZOWE: NIE kopiuj MangaShift llm 1:1** — MangaShift używa JSON, decyzja usera to numeracja `[N]` (✅). PRZEPISZ na numerację. Pełny plan formatu w sekcji N.

### H.1 `llm/__init__.py` — SKOPIUJ wzorzec (re-export)
Re-export `LlmTranslateConfig` + `LlmTranslateService`.

### H.2 `llm/config.py` — PRZEPISZ
```python
@dataclass(slots=True)
class LlmTranslateConfig:
    """Runtime config for the LLM translation engine.

    Attributes:
        max_repair_attempts: Times to re-ask on a line-count mismatch before
            shrinking the batch.
        context_lines: Neighbouring lines given as context (0 = none). Stage 5.
        min_batch_size: Batch size floor for the shrink-to-1 cascade.
    """
    max_repair_attempts: int = 2
    context_lines: int = 0
    min_batch_size: int = 1
```

### H.3 `llm/constants.py` — PRZEPISZ (numeracja `[N]`, NIE JSON)
```python
SYSTEM_PROMPT: Final[str] = (
    "You are a subtitle translator. Translate each numbered input line into the "
    "target language. Return ONLY the numbered lines, one per input line, in the "
    "form '[N] translation'. Keep the exact same numbers and count. Do NOT merge "
    "lines, do NOT add commentary, intro, summary, or markdown. One input line = "
    "one output line."
)
"""System prompt enforcing numbered [N] output, one line in = one line out."""

LINE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\s*\[(\d+)\]\s?(.*)$")
"""Matches a single '[N] text' output line; anything else is ignored."""
```

### H.4 `llm/types.py` — SKOPIUJ 1:1 (pusty)

### H.5 `llm/service.py` — PRZEPISZ (numeracja + walidacja + shrink)

**Skąd:** BAZA struktury z `MangaShift/.../llm/service.py` (klasa, `__init__` z completer, `translate_batch`, `_per_line` ladder), ale PARSER/FORMAT przepisany na numerację `[N]` (nie JSON). Completer wstrzyknięty (sync `LlmCompleter`).

```python
class LlmTranslateService:
    """Translation engine prompting an injected LLM for numbered [N] output.

    Does NOT import anishift.services.llm (independence). The completer is
    injected from the composition root. Integrity via a numbered round-trip with
    a fallback ladder: parse+validate -> repair retry -> shrink batch -> per-line
    -> pad source. Stage 5 wires the real completer and tests it.
    """
    __slots__ = ("_completer", "_config")

    def __init__(self, config, *, completer): ...

    @property
    def engine_id(self) -> str: return "llm"
    @property
    def is_available(self) -> bool: return self._completer is not None

    def translate_batch(self, texts, *, source_lang, target_lang) -> list[BatchedLine]:
        # build numbered prompt "[1] text\n[2] text..."
        # response = completer.complete(SYSTEM_PROMPT, user)
        # parsed = _parse_numbered(response, len(texts))  # validate indices 1..N each once
        # if parsed: return [...]
        # repair loop (max_repair_attempts) with explicit "you returned X, return exactly N"
        # if still failing: shrink (split batch in half, recurse) down to min_batch_size
        # per-line fallback: pad source ok=False
```

**`_parse_numbered(text, expected)`** — NAPISZ OD ZERA (odporny parser, sekcja N):
- linia po linii, bierz TYLKO pasujące `LINE_PATTERN` (`[N] text`); reszta (intro, markdown, „Oto tłumaczenie") ignorowana.
- zbuduj `dict[int, str]`; waliduj `set(keys) == set(range(1, expected+1))`.
- zwróć uporządkowaną listę lub `None` przy rozjeździe.

⚠️ **Status etapu 4 dla llm:** szkielet KOMPLETNY (klasa, prompt, parser, walidacja, shrink) ale NIE przetestowany end-to-end (brak modułu `services/llm` = brak completera). Testy jednostkowe parsera/walidacji z FAKE completerem (M) — te MOŻNA napisać w etapie 4 (fake zwraca numerowany tekst). Realizacja z realnym LLM + provider = etap 5. `create_engine` dla llm rzuca (guard), więc llm NIE jest osiągalny przez fasadę bez wstrzyknięcia — bezpieczne.

---

## I) WPIĘCIE W PIPELINE

### I.1 `pipeline/types.py` — ZMIANA

- `StepName` += `"translate"`:
```python
StepName = Literal["identify", "select", "extract", "split", "write", "translate", "txt"]
```
- `FileOutcome` += pola (mutowalny dataclass, dodaj z defaultami):
```python
    translation: FileTranslation | None = None   # translation result (spoken carried forward)
    translated_lines: int = 0                     # count for the report
    translation_engine: str = ""                  # which engine actually ran
    translation_failed_lines: int = 0             # partial-failure count
```
Import `FileTranslation` w TYPE_CHECKING (annotation-only, z `anishift.services.translation`). ⚠️ `FileOutcome` jest `slots=True` — dodanie pól OK.

- **`TranslationSettings` (NOWY value object w `pipeline/types.py`)** — parametry tłumaczenia rozwiązane raz z `AppContext`, żeby `_process_mkv` (który nie zna `AppContext`) je dostał:
```python
@dataclass(frozen=True, slots=True)
class TranslationSettings:
    """Translation parameters resolved once from AppContext for the runner.

    Attributes:
        engine: Selected translation engine id.
        target_lang: Target language code.
        fallback_chain: Ordered fallback engine ids.
        batch_size: Lines per request (0 = engine default).
        concurrency: Concurrent batches per file.
        max_retries: Retry attempts per batch.
        deepl_api_key: DeepL key (used by the deepl engine, ignored by google).
    """
    engine: str
    target_lang: str
    fallback_chain: tuple[str, ...]
    batch_size: int
    concurrency: int
    max_retries: int
    deepl_api_key: str
```
Dodaj `TranslationSettings` do `__all__` w `pipeline/types.py`.

### I.2 `pipeline/runner.py` — ZMIANA (krok translate)

**Importy do dodania w runnerze** (top-level, first-party): `from anishift.services.subtitles import visible_text`; `from anishift.services.translation.constants import DEFAULT_BATCH_SIZE`; `from .types import ... TranslationSettings`. `TranslationConfig`/`TranslationService` importowane LAZY wewnątrz `_translate_split`/`_process_txt` (żeby import runnera nie ciągnął silników — N6).

**W `_process_mkv`, po kroku `write` (linia ~187), przed budową finalnego `FileOutcome`:**

```python
        step = "translate"
        translation: FileTranslation | None = None
        if not selection.already_polish and (split.stats.spoken_lines or split.stats.displayed_events):
            translation = _translate_split(split, ts, cancel)   # E1: skip Polish; E2: skip empty
        # then include translation fields in the FileOutcome(...) below:
        #   translation=translation,
        #   translated_lines=len(translation.spoken) if translation else 0,
        #   translation_engine=translation.engine_id if translation else "",
        #   translation_failed_lines=translation.failed_lines if translation else 0,
```
⚠️ `ts: TranslationSettings` to nowy param `_process_mkv` (patrz niżej). E1 (already_polish) i E2 (zero spoken+displayed) → `translation` zostaje `None`, outcome bez tłumaczenia.

**Sygnatury do zmiany (dodanie param `ts: TranslationSettings`):**
- `run_pipeline` buduje `ts` z `context` (kod niżej), przekazuje do `_process_mkvs(mkvs, workspace_root, interaction, progress, cancel, ts)` i `_process_txt(path, ts)`.
- `_process_mkvs(..., ts)` — przekazuje `ts` do każdego `_process_mkv(..., ts=ts)` (obie ścieżki: manual i ThreadPoolExecutor).
- `_process_mkv(..., ts: TranslationSettings)`.

**Budowa `ts` w `run_pipeline`:**
```python
ts = TranslationSettings(
    engine=context.user_settings.translation_engine,
    target_lang=context.user_settings.target_lang,
    fallback_chain=tuple(context.user_settings.translation_fallback_chain),
    batch_size=context.user_settings.translation_batch_size,
    concurrency=context.user_settings.translation_concurrency,
    max_retries=context.user_settings.translation_max_retries,
    deepl_api_key=context.settings.deepl_api_key,
)
```

**Nowa funkcja `_translate_split` (spójna — buduje config, woła fasadę, zwraca gotowe `FileTranslation`):**
```python
def _translate_split(split: SubtitleSplit, ts: TranslationSettings, cancel: threading.Event) -> FileTranslation:
    """Translate the spoken and displayed streams of one split."""
    from anishift.services.translation import TranslationConfig, TranslationService
    config = TranslationConfig(
        engine=ts.engine,
        source_lang="auto",
        target_lang=ts.target_lang,
        batch_size=ts.batch_size if ts.batch_size > 0 else DEFAULT_BATCH_SIZE,  # 0 = engine default
        concurrency=ts.concurrency,
        max_retries=ts.max_retries,
        api_key=ts.deepl_api_key,   # used by deepl; ignored by google
    )
    service = TranslationService(config, fallback_chain=ts.fallback_chain)
    displayed_texts = _displayed_visible_texts(split)
    return service.translate_file(
        list(split.spoken),          # list[SpokenLine] — facade builds TranslatedLine with timings
        displayed_texts,             # list[str]
        source_lang="auto",
        target_lang=ts.target_lang,
        cancel=cancel,
    )
```
⚠️ **KLUCZOWE (rozstrzygnięcie sprzeczności):** `translate_file` przyjmuje `list[SpokenLine]` dla spoken (NIE list[str]) — bo fasada potrzebuje `start`/`end`/`style` do zbudowania `TranslatedLine`. Fasada wewnętrznie robi `[s.text for s in spoken]` do dedupu/tłumaczenia, potem buduje `TranslatedLine(start=s.start, end=s.end, source_text=s.text, text=translated, lines=(translated,), style=s.style, ok=ok)`. **Runner NIE buduje TranslatedLine** (żaden `_build_file_translation`) — dostaje gotowe `FileTranslation.spoken: tuple[TranslatedLine, ...]`. To usuwa wcześniejszą sprzeczność (D.10 fasada, K diagram — wszystko spójne: TranslatedLine buduje FASADA).

**`_displayed_visible_texts(split)`** — nowa mała funkcja w runnerze: iteruje `split.subs.events` (tylko Dialogue), synchronizuje z `split.decisions` (per-Dialogue index), dla `decision == "displayed"` zwraca `visible_text(event.text)` w kolejności zdarzeń displayed. Import `visible_text` z `anishift.services.subtitles`.
```python
def _displayed_visible_texts(split: SubtitleSplit) -> list[str]:
    """Return visible-texts of displayed Dialogue events, in order."""
    dialogue = [e for e in split.subs.events if e.type == "Dialogue"]
    return [
        visible_text(event.text)
        for event, decision in zip(dialogue, split.decisions, strict=True)
        if decision == "displayed"
    ]
```
⚠️ `split.decisions` jest per-Dialogue (nie per-event) — dlatego filtrujemy `dialogue`, nie `split.subs.events`. Zweryfikowane: `split_subtitles` liczy `decisions` dla `dialogue = [e for e in subs.events if e.type == "Dialogue"]` (service.py:163) — więc `zip(dialogue, decisions, strict=True)` jest poprawny.

**W `_process_txt` (mini-ficzer):** po `txt_to_spoken` dodaj translate. Displayed dla txt = pusty (txt to sam lektor):
```python
def _process_txt(path: Path, ts: TranslationSettings) -> FileOutcome:
    """Convert one text input into narrator lines and translate them."""
    try:
        spoken = txt_to_spoken(path)
        if not spoken:
            return FileOutcome(path, "done")
        from anishift.services.translation import TranslationConfig, TranslationService
        config = TranslationConfig(engine=ts.engine, source_lang="auto", target_lang=ts.target_lang,
                                   concurrency=ts.concurrency, max_retries=ts.max_retries, api_key=ts.deepl_api_key)
        service = TranslationService(config, fallback_chain=ts.fallback_chain)
        result = service.translate_file(list(spoken), [], source_lang="auto", target_lang=ts.target_lang)
        return FileOutcome(path, "done", spoken_lines=len(spoken),
                           translated_lines=len(result.spoken), translation_engine=result.engine_id, translation=result)
    except AniShiftError as exc:
        return _failed(path, "txt", exc.context.code, exc.context.message, exc.context.suggestion)
    except OSError as exc:
        return _failed(path, "txt", ErrorCode.IO_ERROR, str(exc), "Check file permissions")
```
⚠️ `translate_file(list(spoken), [])` — displayed pusty. Fasada obsługuje pusty displayed (E2 częściowe: displayed=[] → `FileTranslation.displayed=()`). Opcjonalny zapis SRT z txt (sekwencyjne timingi) — MINIMALNY, YAGNI: w etapie 4 wystarczy że tłumaczenie działa; zapis SRT można pominąć lub zrobić prosty (patrz wymagania-v2 §12). Nie rozbudowuj.

**Ctrl+C:** `cancel` już propaguje do `_process_mkv`; przekaż do `translate_file`. Fasada sprawdza między silnikami/batchami.

**Progress (R13):** krok translate reużywa istniejący `on_progress` callback. ⚠️ Dziś `on_progress` steruje paskiem podczas ekstrakcji (0-100%). Tłumaczenie też chce 0-100% (ukończone batche). Problem: jeden pasek na plik, dwa kroki (extract + translate). Rozstrzygam: pasek pliku pokazuje ZŁOŻONY postęp — ale prościej: extract i translate dzielą pasek (np. extract 0-50%, translate 50-100%) LUB translate resetuje pasek. **Rozstrzygam prosto:** krok translate aktualizuje pasek pliku od 0 do 100 po zakończeniu ekstrakcji (extract skończył = pasek na 100, translate re-używa tego samego task_id z nową fazą). Realnie: `on_progress` w translate liczy `ukończone_batche/wszystkie_batche * 100`. Fasada przyjmuje `on_progress: Callable[[int], None] | None`. Jeśli komplikacja z jednym paskiem dwóch faz — w etapie 4 pasek pliku pokazuje fazę translate (extract już był), błędy/retry/fallback w raporcie końcowym (`_render_report`), NIE osobny widget (R13). To spójne z etapem 3.

### I.3 `pipeline/__init__.py` — ZMIANA
Dodaj eksport jeśli nowe typy publiczne (raczej nie — `FileTranslation` eksportowany z `translation`, nie z pipeline).

---

## J) USTAWIENIA `/settings`

### J.1 `config/user_settings.py` — ZMIANA

**Dodaj pola do `UserSettings`** (§9 wymagania-v2):
```python
    translation_engine: str = "google"          # JUŻ jest
    translation_fallback_chain: list[str] = field(default_factory=lambda: ["google"])
    translation_batch_size: int = 0              # 0 = engine default
    translation_concurrency: int = 3
    translation_max_retries: int = 3
    target_lang: str = "pl"
    llm_model: str = ""                          # stage 5
    llm_temperature: float = 0.3                 # stage 5
    llm_top_p: float = 1.0                       # stage 5
    llm_max_output_tokens: int = 0               # stage 5
```
⚠️ `translation_fallback_chain: list[str]` — mutowalny default → `field(default_factory=...)` (B006/RUF012). Import `field`.

**Dodaj stałe zakresów (Final, sekcja Constants):**
```python
CONCURRENCY_RANGE: Final[tuple[int, int]] = (1, 16)
BATCH_SIZE_RANGE: Final[tuple[int, int]] = (0, 500)
MAX_RETRIES_RANGE: Final[tuple[int, int]] = (0, 10)
LLM_TEMPERATURE_RANGE: Final[tuple[float, float]] = (0.0, 2.0)
LLM_TOP_P_RANGE: Final[tuple[float, float]] = (0.0, 1.0)
LLM_MAX_TOKENS_RANGE: Final[tuple[int, int]] = (0, 32000)
```

**Dodaj `_clean_str_list`** (nowy walidator dla fallback_chain):
```python
def _clean_str_list(raw: dict[str, Any], key: str, allowed: frozenset[str]) -> None:
    """Drop ``key`` when it is not a list of allowed strings."""
    value = raw.get(key)
    if not isinstance(value, list) or any(item not in allowed for item in value):
        raw.pop(key, None)
```

**W `load_user_settings`** dodaj walidacje:
```python
    engine_ids = frozenset(available_engine_ids())   # imported from translation.engines
    _clean_string(filtered, "translation_engine", engine_ids)
    _clean_str_list(filtered, "translation_fallback_chain", engine_ids)
    _clean_number(filtered, "translation_batch_size", *BATCH_SIZE_RANGE)
    _clean_number(filtered, "translation_concurrency", *CONCURRENCY_RANGE)
    _clean_number(filtered, "translation_max_retries", *MAX_RETRIES_RANGE)
    # target_lang: keep any non-empty string (no closed set)
    _clean_number(filtered, "llm_temperature", *LLM_TEMPERATURE_RANGE)
    _clean_number(filtered, "llm_top_p", *LLM_TOP_P_RANGE)
    _clean_number(filtered, "llm_max_output_tokens", *LLM_MAX_TOKENS_RANGE)
```
⚠️ **Import `available_engine_ids`** w `user_settings.py` — to import z `translation.engines` (lekki, nie importuje silników). ⚠️ Ryzyko cyklu importu? `user_settings` → `translation.engines` → `translation.errors` → `anishift.errors`. Brak cyklu (translation nie importuje config). OK. Ale ⚠️ `available_engine_ids()` musi być wołane w funkcji (nie na module-level w user_settings), żeby uniknąć importu przy starcie. Rozstrzygam: import wewnątrz `load_user_settings` (lazy) LUB top-level (bezpieczny, lekki). Top-level OK bo `translation.engines` nie ciągnie silników.
⚠️ `target_lang` bez zamkniętego zbioru — waliduj tylko „niepusty string": mały helper lub inline. Rozstrzygam: `if not isinstance(filtered.get("target_lang"), str) or not filtered.get("target_lang"): filtered.pop("target_lang", None)`.

### J.2 `cli/settings_panel.py` — ZMIANA (derywacja z rejestru)

- **USUŃ** `_TRANSLATION_ENGINES: Final = ("google", "deepl", "llm")` (placeholder).
- **Zastąp** importem: `from anishift.services.translation.engines import available_engine_ids`. W `_step_field` dla `translation_engine`: `_cycle(available_engine_ids(), settings.translation_engine, delta)`.
- ⚠️ **Filtr `is_available`:** wymaganie mówi „lista = `available_engine_ids()` filtrowana przez `is_available()`". Ale `is_available` wymaga zbudowania silnika (deepl potrzebuje configu z kluczem). W panelu: zbuduj tymczasowy config per silnik z `context.settings` i sprawdź `is_available`. Prościej: dla panelu w etapie 4 pokaż wszystkie `available_engine_ids()` MINUS `"llm"` (llm nie działa bez etapu 5) — i deepl pokazuj zawsze (walidacja przy użyciu). LUB filtruj deepl przez `bool(context.settings.deepl_api_key)`. Rozstrzygam: panel pokazuje `available_engine_ids()` filtrowane: `llm` ukryty do etapu 5; `deepl` widoczny tylko gdy `context.settings.deepl_api_key` niepusty (E3). `google` zawsze. To realizuje „filtrowana przez is_available" bez budowania silników w panelu (panel zna klucz z `context.settings`).
- **Dodaj pola** do `_FIELDS`: `translation_concurrency` (cykl liczb / clamp), `translation_max_retries`, `target_lang`. `translation_fallback_chain` i llm_* — ⚠️ NIE w panelu w etapie 4 (multi-select/params = złożony UI); edytowalne ręcznie w `settings.json`. Dodaj `_step_field` gałęzie + `_value_text` formatowanie dla nowych prostych pól.
- Parametry LLM w panelu przychodzą z etapem 5.

⚠️ **Import cyklu:** `settings_panel` → `translation.engines` — OK (lekki).

---

## K) PRZEPŁYW DANYCH (diagram + opis)

```
run_pipeline(context)
  │  buduje translation_settings z context (engine, target, concurrency, retries, fallback, deepl_key)
  ▼
_process_mkvs (pliki sekwencyjnie/równolegle wg trybu)
  ▼
_process_mkv(mkv, ..., translation_settings, cancel)
  │  identify → select → extract → split → write (etap 3, bez zmian)
  │  ┌─────────────────── KROK translate (NOWY) ───────────────────┐
  │  │ E1 already_polish → skip                                    │
  │  │ E2 zero spoken+displayed → skip                             │
  │  │ spoken_texts = [SpokenLine z split.spoken]                  │
  │  │ displayed_texts = visible_text(displayed events)            │
  │  ▼                                                             │
  │  TranslationService(config, fallback_chain).translate_file(   │
  │      spoken, displayed, target_lang, cancel)                  │
  │  │                                                             │
  │  │  chain = [engine, *fallback] filtr is_available            │
  │  │  for engine_id in chain:                                    │
  │  │    ┌── dedup spoken (dict.fromkeys) ──┐                     │
  │  │    ├── dedup displayed ───────────────┤                     │
  │  │    │  create_engine(config) [lazy import silnika]           │
  │  │    │  engine.translate_batch(unique_spoken) ──┐            │
  │  │    │     google: asyncio.run(gather+semaphore, │            │
  │  │    │             separator batch, ladder)      │  RETRY     │
  │  │    │     deepl: SDK list batch, byte-chunk     │  backoff   │
  │  │    │  redistribute → per-line translations     │  na 429    │
  │  │    │  FASADA build TranslatedLine (timing/style │            │
  │  │    │    z SpokenLine — silnik NIE zna timingów) │            │
  │  │    └── displayed → lista przetłumaczonych stringów           │
  │  │    return FileTranslation(spoken, displayed, engine_id, ...) │
  │  │    except Quota/Engine/RateLimit/Auth → next engine         │
  │  │  chain wyczerpany → FileTranslation(error=...)              │
  │  └─────────────────────────────────────────────────────────────┘
  │  FileOutcome(translation=result, translated_lines=..., engine=...)
  ▼
PipelineReport → _render_report (raport końcowy: błędy/retry/fallback tu)
```

**Gdzie co wchodzi:**
- **dedup** → fasada (`service.translate_file`), przed silnikiem. Wspólny.
- **batching** → wewnątrz silnika (`google/_batching`, `deepl` byte-chunk).
- **podział linii (linebreak)** → NIE w etapie 4 dla spoken; dla displayed woła etap 7 przy zapisie. Etap 4 dostarcza `linebreak.split_line` jako narzędzie.
- **fallback** → fasada (pętla po łańcuchu).
- **spoken** → `FileTranslation.spoken` (tuple[TranslatedLine]) → `FileOutcome.translation` → (etap 6 TTS konsumuje).
- **displayed** → `FileTranslation.displayed` (tuple[str]) → (etap 7 wstrzykuje do ASS przez `replace_visible_text` + `linebreak`).
- **granica etap4/7:** etap 4 = przetłumaczone dane + narzędzie linebreak; etap 7 = wstrzyknięcie, warianty, nazewnictwo, muxowanie.

---

## L) KOLEJNOŚĆ IMPLEMENTACJI (kroki z weryfikacją)

Każdy krok kończy się zieloną bramką (`ruff check` + `ruff format --check` + `mypy` + `pytest`) na dodanych plikach.

**Krok 1 — baza domeny (bez silników).**
Pliki: `services/_base.py` (SKOPIUJ), `errors.py`, `constants.py`, `config.py`, `types.py`, `protocols.py`.
Weryfikacja: `from anishift.services.translation.config import TranslationConfig` działa; `TranslationConfig()` bez `engine` rzuca `TranslationConfigError`; `TranslationConfig(engine="google")` OK. Test: `test_translation_config`.

**Krok 2 — dedup + retry.**
Pliki: `dedup.py`, `_retry.py`.
Weryfikacja: `test_translation_dedup` — 1000 identycznych linii → `unique` długości 1, `index_map` wszystkie 0; empty passthrough; determinizm (dwa razy ten sam wynik). `test_retry` — `call_with_retry` ponawia na podanym wyjątku, nie na innym, respektuje `max_attempts`.

**Krok 3 — rejestr.**
Pliki: `engines/__init__.py` (SKOPIUJ z MangaShift).
Weryfikacja: `test_translation_registry` — `available_engine_ids() == ("google", "deepl", "llm")`; `create_engine(config(engine=""))` → ConfigError „required"; `create_engine(config(engine="xyz"))` → ConfigError z posortowaną listą; `create_engine(config(engine="llm"))` → ConfigError (completer); import rejestru NIE importuje googletrans/deepl (sprawdź `sys.modules` nie ma `googletrans`/`deepl` po imporcie rejestru — lazy N6); `set(get_args(TranslationEngineId)) == set(available_engine_ids())`.

**Krok 4 — linebreak + chunking.**
Pliki: `linebreak.py` (OD ZERA), `chunking.py` (PRZEPISZ text_chunker).
Weryfikacja: `test_translation_linebreak` — realne PL zdania dają sensowne cięcia (≤max_chars, ≤2 wersy, bez sierot, nie tnie zrostów jak „w domu"); `test_translation_chunking` — chunk_text tnie txt po znakach.

**Krok 5 — silnik google.**
Pliki: `engines/google/*` (SKOPIUJ + async→sync).
Weryfikacja: `test_translation_google` — `_batching.translate_lines` z FAKE async callback (bez sieci) zachowuje kolejność i długość; ladder działa (separator→newline→per-line); `is_available` = True. Test sieciowy `@pytest.mark.network` (opt-in): realne EN→PL, ta sama liczba linii.

**Krok 6 — silnik deepl.**
Pliki: `engines/deepl/*` (SKOPIUJ + async→sync + klucz z config).
Weryfikacja: `test_translation_deepl` — bez klucza `is_available`=False, translate_batch rzuca `TranslationAuthError`; mock SDK (Fake client) mapuje `QuotaExceededException`→`TranslationQuotaError`, `TooManyRequests`→`TranslationRateLimitError`; `to_deepl_code` mapowania. Test sieciowy: z realnym kluczem usera EN→PL.

**Krok 7 — silnik llm (szkielet).**
Pliki: `engines/llm/*` (PRZEPISZ na numerację).
Weryfikacja: `test_translation_llm_parse` — `_parse_numbered` z FAKE completerem (zwraca „[1] a\n[2] b"): waliduje indeksy, ignoruje śmieci przed/po, wykrywa rozjazd (brak `[2]`), shrink-do-1. (Bez realnego LLM — fake.) `create_engine(llm)` rzuca.

**Krok 8 — fasada.**
Pliki: `service.py`, `__init__.py`.
Weryfikacja: `test_translation_service` — z FAKE enginem (Protocol impl, bez sieci): `translate_file` dedupuje, buduje TranslatedLine z timingami, `FileTranslation.api_calls` < total gdy duplikaty; fallback — pierwszy engine rzuca Quota, drugi (fake) tłumaczy, `engine_id` = drugi; łańcuch pusty → `error` ustawiony; E2 zero linii → pusty result.

**Krok 9 — /settings.**
Pliki: `config/user_settings.py`, `cli/settings_panel.py`.
Weryfikacja: `test_user_settings` (rozszerz) — nowe pola default; walidacja `_clean_str_list` odrzuca zły fallback_chain; concurrency out-of-range → default; round-trip zapis/odczyt przeżywa restart. Panel: silnik derywowany z `available_engine_ids()` (nie placeholder); deepl ukryty bez klucza.

**Krok 10 — wpięcie runner.**
Pliki: `pipeline/types.py`, `pipeline/runner.py`.
Weryfikacja: `test_pipeline_runner` (rozszerz) — `StepName` ma „translate"; `_process_mkv` woła translate po write; `already_polish` pomija (E1); zero spoken pomija (E2); błąd tłumaczenia → outcome failed, reszta plików leci (E10). Smoke na realnym pliku z `../mm_avh_working_space/temp/dataset_ass/` (network, opt-in): przetłumaczone spoken+displayed, ta sama liczba linii, timingi nietknięte.

**Krok 11 — mini-ficzer txt.**
Pliki: `runner.py` `_process_txt`.
Weryfikacja: txt → tłumaczenie → (opcjonalny SRT). Test z fake enginem.

**Krok 12 — bramki + smoke e2e.**
Weryfikacja: pełne `uv run ruff check anishift/ tests/`, `ruff format --check`, `mypy anishift/ tests/`, `pytest` zielone. Smoke: Enter na obcym MKV robi extract→split→translate; polski MKV nie woła API.

---

## M) TESTY

Konwencja AniShift (z `tests/services/subtitles/`): pliki `test_*.py`, funkcje `test_<unit>_<scenario>_<expected>`, helpery `_event`/`_subs`, brak docstringów w testach, AAA. Markery: `@pytest.mark.network` (module-level `pytestmark`) dla realnego API. `per-file-ignores` tests: `D, S101, PLR2004, TRY003`.

**Fake engine (bez sieci, N7) — wzorzec Protocol+Fake (NIE mock.patch):**
```python
class _FakeEngine:
    """In-memory TranslationEngine for tests (no network)."""
    def __init__(self, *, fail_with=None, prefix="PL:"):
        self.calls = []
        self._fail_with = fail_with
        self._prefix = prefix
    @property
    def engine_id(self): return "fake"
    @property
    def is_available(self): return True
    def translate_batch(self, texts, *, source_lang, target_lang):
        self.calls.append(list(texts))
        if self._fail_with is not None:
            raise self._fail_with
        return [BatchedLine(text=f"{self._prefix}{t}", ok=True) for t in texts]
    def close(self): ...
```

**Co testować (per plik):**

- `test_translation_registry.py`: `available_engine_ids`, guard pusty/nieznany/llm, `sorted` w komunikacie, lazy import (`"googletrans" not in sys.modules` po imporcie rejestru), sync Literal↔registry (`get_args`).
- `test_translation_dedup.py`: 1000 duplikatów → 1 unique; index_map poprawny; empty passthrough; determinizm (dwa wywołania równe); `redistribute` odtwarza pełną listę.
- `test_translation_linebreak.py`: parametrize realne PL zdania — „Nie wiem, czy dam radę bo to trudne zadanie dla mnie" → 2 wersy ≤42, cięcie na przecinku/spójniku; „w domu" nie rozdzielone; brak sierot; krótkie zdanie → 1 wers; monstrualne → greedy fallback.
- `test_translation_chunking.py`: chunk_text char/word, limit respektowany, granice zdań.
- `test_translation_service.py`: dedup w fasadzie (api_calls < total); fallback (pierwszy fail→drugi ok, engine_id); łańcuch pusty→error; E2 zero linii; TranslatedLine timingi ze SpokenLine; cancel rzuca CANCELLED.
- `test_translation_google.py`: `_batching` ladder (fake callback): separator match → map; mismatch → newline → map; oba mismatch → per-line; empty pad ok=False; kolejność zachowana. (`@pytest.mark.network` osobno: realne EN→PL.)
- `test_translation_deepl.py`: is_available bez/z kluczem; mapowanie błędów SDK (fake client rzuca deepl exceptions); to_deepl_code; byte-chunk dużego batcha. (network: realny klucz usera.)
- `test_translation_llm.py`: `_parse_numbered` — poprawny numerowany parse; ignoruje intro/markdown/outro; wykrywa brak `[N]`; shrink-do-1; repair prompt. (fake completer, bez sieci.)
- `test_translation_network.py`: `pytestmark = pytest.mark.network`. Realne google + deepl na próbce EN→PL; smoke na pliku z datasetu (ta sama liczba linii, timingi).

**Rejestr testów w `pyproject.toml`:** `tests/` już w `testpaths`. `network` marker już zdefiniowany. Zero zmian konfiguracji.

---

## N) SYSTEM LLM — PEŁNY PLAN (§9 wymagań)

> Silnik `llm` w rejestrze od etapu 4 (szkielet). Realizacja/test z realnym providerem = etap 5 (brak `services/llm`). Format ROZSTRZYGNIĘTY: **numeracja `[N] tekst`** (✅, NIE JSON/TOON/XML).

**Implementowane TERAZ (etap 4):**
- Klasa `LlmTranslateService` (Protocol impl, completer wstrzyknięty).
- `SYSTEM_PROMPT` z numeracją + anty-gadanie (H.3).
- Builder promptu: `[1] tekst\n[2] tekst...`.
- `_parse_numbered(response, expected)` — odporny parser: bierz TYLKO linie `[N] tekst` (regex `LINE_PATTERN`), ignoruj wszystko inne (intro, markdown ```` ``` ````, outro). Zbuduj `dict[int,str]`, waliduj `keys == {1..N}`, zwróć uporządkowaną listę lub None.
- Walidacja liczby: brak `[k]` = wiadomo dokładnie która linia zgubiona.
- Ladder fallback: parse → repair retry (dopisz „zwróciłeś X zamiast N, zwróć DOKŁADNIE N, nie scalaj") → shrink batch (podziel na pół, rekurencja do `min_batch_size=1`) → per-line → pad source ok=False.
- Testy jednostkowe parsera/walidacji/shrink z FAKE completerem (bez sieci).

**Realizowane W ETAPIE 5 (nie teraz, brak modułu):**
- `services/llm/` (6 providerów, fasada) — completer.
- Wstrzyknięcie completera do `LlmTranslateService` przez `TranslationService(engine=LlmTranslateService(config, completer=...))`.
- Kontekst sąsiednich linii (A4) — `context_lines` w configu, budowa promptu z kontekstem. Ilość do zmierzenia.
- Backoff API (429/5xx) na poziomie completera (nie parsera).
- Parametry z `/settings` (temperature/top_p/max_tokens/model) → completer.
- Podział linii LLM (A6) — czy LLM dzieli sam (w promcie) czy wspólny `linebreak`. Domyślnie: displayed przez wspólny `linebreak` (etap 7); LLM-native podział jako opcja etapu 5.
- Realny test end-to-end z providerem.

**Dlaczego numeracja (dla planu, ✅ decyzja usera):** najtańsza tokenowo, walidacja O(N) bez parsera JSON, błąd lokalny (zgubiona linia = jedna luka, nie cały batch), odporna na śmieci (regex `[N]` wyłapuje tylko dobre linie). Walidacja liczby + shrink-do-1 obowiązkowa niezależnie od formatu.

**⚠️ Rozbieżność z MangaShift:** MangaShift `llm/service.py` używa JSON (`_parse` JSON array id/translated). NIE kopiuj — PRZEPISZ na numerację. Struktura klasy (ladder, per_line) analogiczna, ale parser/format inny.

---

## O) FORMAT ZNAKOWY / ŁAMANIE LINII — MECHANIKA SZCZEGÓŁOWA (user pytał wprost)

### O.1 Strategia per silnik (test na żywo — R6a)

| Silnik | `\n` w input | Strategia batchowania | Re-podział |
|---|---|---|---|
| **Google** | (brak — AniShift daje jednoliniowe) | join batcha separatorem zero-width (`LINE_SEPARATOR`), jeden request → Google widzi kontekst całości → split po separatorze | wynik jednoliniowy → re-podział przez `linebreak` (etap 7 dla displayed) |
| **DeepL** | (brak) | natywny batch listą (SDK bierze listę, zwraca w kolejności) | wynik jednoliniowy → `linebreak` |
| **LLM** | (brak) | numeracja `[N]` w jednym prompcie | LLM może dzielić sam (etap 5) lub `linebreak` |

**KLUCZOWE:** AniShift daje silnikom **jednoliniowe teksty** (spoken.text nie ma `\n`; displayed przez `visible_text()` też jednoliniowy). Więc problem „sklejać `\n`" (test: Google psuł rozbite wersy) **nie występuje na wejściu** — teksty są już sklejone. Test dowiódł: Google MUSI dostać sklejone → dostaje (jednoliniowe). Re-podział na wersy robimy PO tłumaczeniu (`linebreak`), tworząc NOWY czytelny układ (nie odtwarzając oryginału — niemożliwe). To jest sedno: **sklejanie = stan wejścia (już sklejone), re-podział = nowy układ po tłumaczeniu.**

### O.2 Google batching (mechanika `_batching.py`)

1. `_chunks(texts, batch_size, max_chars)` — grupuje linie w chunki: ≤`batch_size` linii I ≤`MAX_CHARS_PER_REQUEST` (15000) znaków. Każda linia: `text.replace("\n", NEWLINE_MARKER)` (no-op przy braku `\n`, ale bezpieczne).
2. `_translate_chunk` — **ladder** (odporność na rozjazd liczby):
   - próba 1: `LINE_SEPARATOR.join(chunk)` (zero-width `​###​`), jeden translate, split po separatorze. Jeśli `len(parts) == len(chunk)` → OK.
   - próba 2 (rozjazd): `"\n".join(chunk)`, translate, split po `\n`. Google czasem zachowuje `\n`.
   - próba 3 (dalej rozjazd): per-line (każda linia osobno). Wolne, ale gwarantuje kardynalność.
   - pad: pusta odpowiedź na niepusty input → source, ok=False.
3. `_restore(part)` — usuwa markery/separatory, `re.sub` whitespace, strip.

**Separator zero-width** — Google go NIE tłumaczy (zero-width space niewidoczny dla modelu), zachowuje jako granicę. To pozwala jednym requestem przetłumaczyć wiele linii z kontekstem, potem rozdzielić. To jest lepsze niż per-line (Google widzi kontekst) i niezawodne (separator przetrwa). Markery WIDOCZNE (`◍◍◍◍`) ODRZUCONE (test: ~20% gubi) — zero-width jest niewidoczny, nie kusi modelu do „tłumaczenia".

### O.3 DeepL batching

DeepL SDK `translate_text(list)` bierze listę, zwraca listę w kolejności — natywna kardynalność (bez separatorów, bez laddera). DeepL rozumie kontekst mimo podziału (test na żywo) i zachowuje `\n` — ale my dajemy jednoliniowe, więc nieistotne. Jedyna komplikacja: limit payloadu 128 KiB → `_chunk_by_bytes` dzieli unique-set na pod-batche po bajtach, każdy = jeden `translate_text` call. Kolejność zachowana przez concat.

### O.4 Re-podział `linebreak` (algorytm — D.8)

Hierarchia cięcia (dla polskiego, wg wymagań-v2 §6.3):
1. **mocna interpunkcja** `. ! ? … :` (po znaku) — waga distance/8
2. **słaba interpunkcja** `, ; —` (pauza dialogowa) — waga distance/4
3. **spójnik** (`i, oraz, ale, że, więc, bo, aby, lub, a, czy, gdy, jak, kiedy`, przed słowem) — waga distance/2
4. **najbliżej środka** na granicy słowa (idea `split_at_half`) — waga distance

Reguły ochronne:
- limit ~42 znaki/wers (konfigurowalny)
- max 2 wersy (rekurencja `_cap`)
- **bez sierot**: pojedyncze słowo w wersie → kara ×10 (wybierz inny punkt)
- **nie tnij zrostów**: prev_word ∈ `_NON_BREAKING_HEADS` (przyimki `w, na, z, do...`) → pomiń ten punkt (nie rozdzielaj przyimka od rzeczownika)
- **fallback greedy**: brak dobrego punktu → ostatnia spacja ≤ limit

Dotyczy **displayed** (widz czyta — układ ważny). **Spoken NIE dzielony** (lektor czyta ciągiem, §6.1 wymagań-v2) — `TranslatedLine.lines = (text,)`.

**Kto woła `linebreak`:** etap 7 (composition) przy wstrzykiwaniu displayed do ASS. Etap 4 dostarcza funkcję `linebreak.split_line` + przetłumaczone stringi. To trzyma granicę (`max_chars` displayed to ustawienie eksportu = etap 7).

---

## PODSUMOWANIE „SKĄD" DLA KAŻDEGO PLIKU (szybka ściąga dla implementatora)

| Plik | Skąd | Uwaga |
|---|---|---|
| `services/_base.py` | SKOPIUJ MangaShift `services/_base.py` | EngineInfo Protocol, fundament 3 rejestrów |
| `translation/errors.py` | SKOPIUJ MangaShift errors | baza→AniShiftError |
| `translation/constants.py` | SKOPIUJ + dodaj concurrency/target | — |
| `translation/config.py` | SKOPIUJ + dodaj concurrency/api_key, target default | source_lang default auto |
| `translation/types.py` | PRZEPISZ (BatchedLine skopiuj, reszta nowa) | TranslatedLine, FileTranslation |
| `translation/protocols.py` | PRZEPISZ async→sync | EngineInfo base, bez SecretProvider |
| `translation/dedup.py` | PRZEPISZ z mm_avh logika, kształt nowy | dict.fromkeys |
| `translation/_retry.py` | OD ZERA (sync, bez tenacity) | ~35 linii |
| `translation/linebreak.py` | OD ZERA (idea split_at_half) | ~55 linii, jedyny algorytm od zera |
| `translation/chunking.py` | PRZEPISZ text_chunker.py wg python | snake_case, typy, docstringi |
| `translation/service.py` | PRZEPISZ MangaShift async→sync + fallback+dedup | — |
| `translation/__init__.py` | SKOPIUJ wzorzec + dostosuj eksporty | lazy |
| `engines/__init__.py` | SKOPIUJ MangaShift 1:1 | + logger, - secret_provider |
| `engines/google/*` | SKOPIUJ MangaShift (6 plików) | async pod asyncio.run, - validate_key |
| `engines/deepl/*` | SKOPIUJ MangaShift (6 plików) | sync, klucz z config, - validate_key |
| `engines/llm/*` | PRZEPISZ (JSON→numeracja) | szkielet, completer wstrzyknięty |
| `pipeline/types.py` | ZMIANA | StepName+translate, FileOutcome+pola |
| `pipeline/runner.py` | ZMIANA | krok translate w _process_mkv/_process_txt |
| `config/user_settings.py` | ZMIANA | pola + _clean_str_list |
| `cli/settings_panel.py` | ZMIANA | derywacja z rejestru, - placeholder |

**Nic nie piszemy od zera poza `_retry.py`, `linebreak.py`, `dedup.py` (kształt), oraz nowymi typami/adaptacjami. Reszta = kopie MangaShift z podmianą importów i async→sync.**

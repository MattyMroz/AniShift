# AniShift — mapa repozytorium (stan na 2026-07-17)

> Materiał referencyjny dla agenta piszącego plan etapu 3/3.1. Wszystko zweryfikowane w kodzie, nie z pamięci.
> Branch: `feat/stage-3-extraction-subtitles` · HEAD: `9e002b9` · Python ≥3.14 · uv

## 1. Drzewo z liniami

### `anishift/` — 1876 linii, 20 plików

```
anishift/
├── __init__.py                    7    __version__ = "0.1.0"
├── bootstrap.py                  72    AppContext + bootstrap()  ← composition root
├── errors.py                    156    AniShiftError / ErrorCode / ErrorContext
├── cli/
│   ├── __init__.py                7
│   ├── banner.py                 47    show_banner()
│   ├── commands.py              187    COMMANDS registry + dispatch()   ← REJESTR KOMEND
│   ├── completer.py              62    SlashCompleter
│   ├── main.py                   88    Typer app (doctor, setup, default→shell)
│   ├── settings_panel.py        188    open_settings_panel()            ← PANEL
│   └── shell.py                  70    run_shell()                      ← REPL / Enter hook
├── config/
│   ├── __init__.py               37
│   ├── settings.py               65    Settings (pydantic-settings, ANISHIFT_*)
│   ├── user_settings.py         155    UserSettings + load/save
│   └── workspace.py             107    resolve_workspace_root, DEFAULT_SUBDIRS
├── platform/
│   ├── __init__.py               25
│   └── binaries.py              148    Binary, TOOL_DIR, resolve/require_binary
└── setup/
    ├── __init__.py               14
    ├── doctor.py                208    run_doctor() → list[CheckResult]
    ├── installer.py             510    ensure_binary ← WOŁANE W ETAPIE 3
    └── manifest.py              225    load_manifest() → tuple[Resource, ...]
```

### `utils/` — 4519 linii (NIETYKALNE, wykluczone z ruff+mypy)

```
utils/
├── __init__.py                   20    safe_move, safe_rmtree, safe_resolve, PathTraversalError
├── _portable.py                  70
├── device.py                    115    DeviceInfo, get_device (torch — AniShift NIE używa)
├── safe_fs.py                    99    safe_rmtree, safe_move (retry — Windows locking)
├── safe_path.py                  40    PathTraversalError, safe_resolve
├── secrets.py                    85    sanitize_secrets
├── timing.py                     23    MS_PER_SEC, elapsed_ms_since
├── rich_console/                708    ← UŻYWANE PRZEZ ANISHIFT
│   ├── __init__.py               61    console, RICH_THEME, Colors, ProgressBarManager
│   ├── console.py               375    console (patched print + auto-highlight)
│   ├── theme.py                 350    RICH_THEME (150+ styli), Colors
│   ├── utilities.py             247    get_status_icon, format_bytes, format_duration
│   └── progress/
│       ├── __init__.py           25
│       └── manager.py           676    ProgressBarManager, ProgressBarBuilder  ← ETAP 3.1
├── timer/                       385    Timer, ExecutionTimer, timed, format_duration
└── logger/                     2352    loguru wrapper — OFF, anishift/ NIE importuje
```

### `tests/` — 966 linii, 9 plików. **`conftest.py` NIE ISTNIEJE.**

```
test_banner.py 30 · test_binaries.py 61 · test_commands.py 98 · test_completer.py 62
test_doctor.py 61 · test_installer.py 369 · test_manifest.py 115 · test_setup_cli.py 44
test_user_settings.py 126
```

### `scripts/tmp/` — poza ruff i mypy, NIE zaimportowane nigdzie

```
number_in_words.py   192   NumberInWords — liczby → polskie słowa (etap 6)
text_chunker.py      150   LatinPunctuator, WordBreaker, CharBreaker (etap 6)
```

> ⚠️ **Plan strategiczny kłamie o `utils/`:** `cool_animation.py` i `execution_timer.py` **nie istnieją**. `ExecutionTimer` to klasa w `utils/timer/__init__.py:138`. `number_in_words`/`text_chunker` są w `scripts/tmp/`, nie w `utils/`.

---

## 2. Per moduł: API + zależności

### 2.1 `anishift/errors.py` (156) — hierarchia

**Zależności:** tylko stdlib. Liść grafu.

```python
__all__ = ["AniShiftError", "ErrorCode", "ErrorContext", "FatalError", "TransientError"]
```

```
Exception
└── AniShiftError            errors.py:110   .context: ErrorContext (zawsze istnieje)
    ├── TransientError       errors.py:145   retry-owalne
    └── FatalError           errors.py:152   NIE retry
```

**Konkretne błędy żyją w modułach domenowych, NIE w errors.py:**

| Klasa | Plik:linia | Baza |
|---|---|---|
| `WorkspaceRootNotResolvedError` | `config/workspace.py:48` | `FatalError` |
| `BinaryNotFoundError` | `platform/binaries.py:52` | `FatalError` |
| `ManifestError` | `setup/manifest.py:53` | `FatalError` |
| `InstallerError` | `setup/installer.py:93` | `FatalError` |
| `HashMismatchError` | `setup/installer.py:97` | `InstallerError` |
| `InstallCancelledError` | `setup/installer.py:101` | `InstallerError` |

**`ErrorCode(StrEnum)`** (`errors.py:33-88`) — kody dla etapu 3 **JUŻ ZAREZERWOWANE**:
```
EXTRACTION_FAILED, TRACK_NOT_FOUND          # extraction
SUBTITLE_PARSE_FAILED                        # subtitles
PIPELINE_FAILED, PIPELINE_STEP_FAILED        # pipeline
```
Pozostałe: `UNKNOWN, TIMEOUT, CANCELLED, CONFIG_INVALID, CONFIG_MISSING, FILE_NOT_FOUND, IO_ERROR, WORKSPACE_NOT_RESOLVED, BINARY_NOT_FOUND, BINARY_HASH_MISMATCH, TRANSLATION_*, LLM_*, TTS_*, AUDIO_FAILED, COMPOSITION_FAILED, NETWORK_ERROR, API_ERROR`

**`ErrorContext`** (`errors.py:91-107`) — `frozen=True, slots=True`, 5 pól: `code: ErrorCode`, `message: str`, `suggestion: str = ""`, `docs_url: str = ""`, `details: dict[str, Any] = field(default_factory=dict)`.

### 2.2 `anishift/bootstrap.py` (72) — composition root

```python
@dataclass(slots=True)            # bootstrap.py:29 — MUTOWALNY (nie frozen!)
class AppContext:
    settings: Settings            # klucze API z .env
    user_settings: UserSettings   # preferencje panelu
    workspace_root: Path

def bootstrap(*, settings: Settings | None = None, create_dirs: bool = True) -> AppContext
```

Kolejność (`:60-72`): `load_dotenv(override=False)` → `Settings()` → `load_user_settings()` → `resolve_workspace_root()` → opcjonalnie `ensure_workspace_dir()`.

> **Dokładnie 3 pola.** Dodanie 4. wymaga zmiany testów (`test_commands.py:20`, `test_banner.py:17`). Zero pipeline'u/loggera/executora — świadomie ubogi kontekst.

### 2.3 `anishift/config/workspace.py` (107)

```python
ENV_WORKSPACE_ROOT: Final[str] = "ANISHIFT_WORKSPACE_ROOT"      # :32
DEFAULT_SUBDIRS: Final[tuple[str, ...]] = ("tmp", "output")      # :41  ← TYLKO DWA
def resolve_workspace_root() -> Path                             # :77  NIE tworzy katalogu
def ensure_workspace_dir(root: Path) -> None                     # :96  idempotentne
```

Precedencja: env `ANISHIFT_WORKSPACE_ROOT` → `<repo>/workspace` (przez `parents[2]` + marker `pyproject.toml`). Brak → `WorkspaceRootNotResolvedError`.

### 2.4 `anishift/config/user_settings.py` (155) — ZERO importów z projektu

```python
Mode = Literal["auto", "manual"]                                 # :33
OutputVariant = Literal["players", "merge", "burn"]              # :36
TEMPO_RANGE: Final[tuple[float, float]] = (0.5, 2.0)             # :47  PUBLICZNE
VOLUME_RANGE: Final[tuple[int, int]] = (0, 100)                  # :50  PUBLICZNE
```

**`UserSettings`** — `@dataclass(slots=True)` **mutowalny**, 8 pól:

| pole | typ | default |
|---|---|---|
| `mode` | `Mode` | `"auto"` |
| `translation_engine` | `str` | `"google"` |
| `tts_engine` | `str` | `"edge"` |
| `voice` | `str` | `"pl-PL-MarekNeural"` |
| `tempo` | `float` | `1.0` |
| `volume` | `int` | `100` |
| `output_variant` | `OutputVariant` | `"merge"` |
| `move_results_to_output` | `bool` | `False` |

```python
def config_path() -> Path                 # :91   <repo>/config/settings.json
def load_user_settings() -> UserSettings  # :118  NIGDY nie rzuca
def save_user_settings(s) -> None         # :148  atomowy (.tmp → replace)
```

**Filozofia „nigdy nie rzucaj":** brak pliku / `OSError` / `JSONDecodeError` / nie-dict → `UserSettings()`. Nieznane klucze odfiltrowane, złe wartości → default per pole.

**Jak dodać pole:** (1) pole+docstring, (2) `_clean_*` w `load_user_settings`, (3) `_Field` w `settings_panel._FIELDS`, (4) **gałąź w `_step_field`** (bez niej pole martwe!), (5) ew. `_value_text`, (6) test. Stary JSON bez klucza → default, zero migracji.

### 2.5 `anishift/config/settings.py` (65)

`Settings(BaseSettings)`, `env_prefix="ANISHIFT_"`, 9 pól `str` default `""`: `deepl_api_key`, `elevenlabs_api_key`, `anthropic_api_key`, `gemini_api_key`, `openai_api_key`, `deepseek_api_key`, `openrouter_api_key`, `openai_compatible_api_key`, `openai_compatible_base_url`. **Tylko sekrety.** W testach: `Settings(_env_file=None)`.

### 2.6 `anishift/platform/binaries.py` (148)

```python
class Binary(StrEnum):              # :42   wartość = stem BEZ rozszerzenia
    BALCON = "balcon"; FFMPEG = "ffmpeg"; FFPROBE = "ffprobe"
    MKVEXTRACT = "mkvextract"       # ← ETAP 3
    MKVMERGE = "mkvmerge"           # ← ETAP 3 (mkvmerge -J = identify)

TOOL_DIR: Final[dict[Binary, str]] = {        # :58
    Binary.BALCON: "balabolka",               # UWAGA: jedyny przypadek katalog ≠ nazwa!
    Binary.FFMPEG: "ffmpeg", Binary.FFPROBE: "ffmpeg",
    Binary.MKVEXTRACT: "mkvtoolnix", Binary.MKVMERGE: "mkvtoolnix",
}

def is_windows() -> bool                             # :74
def external_bin_root() -> Path                      # :84   <repo>/external/bin
def resolve_binary(binary: Binary) -> Path | None    # :94
def require_binary(binary: Binary) -> Path           # :122  raises BinaryNotFoundError
```

Kolejność: Windows-only poza Windows → `None`; `external/bin/<TOOL_DIR[b]>/<stem>[.exe]`; **tylko poza Windows** `shutil.which()`. **Na Windows PATH NIE jest przeszukiwany.**

### 2.7 `anishift/setup/installer.py` (510) — **punkt wejścia etapu 3**

```python
def ensure_binary(binary: Binary) -> Path          # :369  BEZ kwargs, jeden argument
```

Logika (`:388-394`):
```python
path = resolve_binary(binary)
if path is not None:
    return path                       # fast path — zero I/O, zero sieci
resource_name = _resource_for(binary, load_manifest())
if resource_name is not None:
    ensure_resource(resource_name)    # pobiera JEDEN zasób, z paskiem
return require_binary(binary)         # raises BinaryNotFoundError
```

Rzuca: `InstallerError`, `HashMismatchError`, `BinaryNotFoundError` — wszystkie `FatalError`.

**Dwie filozofie błędów:** `ensure_*` (leniwe, domena) → **rzuca**. `run_setup` (jawne `/setup`) → **nigdy nie rzuca** per-zasób, błędy jako wpisy `failed`/`cancelled`.

Poza Windows `ensure_resource` dla `kind=="binary"` to **cichy no-op** (`:327`).

### 2.8 `anishift/setup/manifest.py` (225)

`Resource(name, kind, source, sha256, size_bytes, archive, members)` — wszystko `frozen=True, slots=True`. Manifest ma **tylko** `mkvtoolnix` (mkvextract+mkvmerge) i `ffmpeg` (ffmpeg+ffprobe). **Brak `balcon`** → `ensure_binary(Binary.BALCON)` rzuci.

### 2.9 `anishift/setup/doctor.py` (208)

`CheckStatus(StrEnum)`: OK/WARN/FAIL/SKIP. `CheckResult(name, status, message, suggestion="", details={})` — `frozen=True, slots=True`. `run_doctor()` → `[python_version, uv_installed, binaries, api_keys, workspace]` (kolejność przypięta testem).

### 2.10 `anishift/cli/shell.py` (70) — **TU WPINA SIĘ ENTER**

```python
while True:
    try:
        line = session.prompt("anishift > ")
    except EOFError:      break          # Ctrl+D
    except KeyboardInterrupt: break      # Ctrl+C  ← UWAGA
    stripped = line.strip()
    if not stripped:
        console.print("[warning]Pipeline in progress[/warning] — arrives in stage 3.")   # ← :63
        continue
    if stripped.startswith("/"):
        if not dispatch(stripped, context):
            break
        continue
    console.print("[gray]Type [/gray][info]/help[/info][gray] for commands...[/gray]")
```

> ## ⬅ **`shell.py:62-64` — DOKŁADNE MIEJSCE PODPIĘCIA**
> Gałąź `if not stripped:` — zastąpić `console.print(...)` wywołaniem pipeline'u. `context: AppContext` jest w scope, `continue` zostaje.
>
> **Ctrl+C:** dziś `KeyboardInterrupt` z `session.prompt()` **kończy REPL** (`:59-60`). Przerwanie *pipeline'u* bez wyjścia z shella wymaga osobnego `try/except` wokół wywołania. Precedens: `installer.py:460-467` (`threading.Event` + `wait(timeout=0.2)`).
>
> **Tryb:** `context.user_settings.mode` — `/auto`/`/manual` mutują w miejscu (`commands.py:76-81`), wartość zawsze aktualna.

### 2.11 `anishift/cli/commands.py` (187) — rejestr

```python
@dataclass(frozen=True, slots=True)
class Command:                                                    # :48
    name: str; summary: str
    handler: Callable[[AppContext, frozenset[str]], bool]         # False = wyjdź z REPL
    options: dict[str, str] = field(default_factory=dict)

COMMANDS: dict[str, Command] = {...}     # :138   7 komend: /auto /doctor /exit /help /manual /settings /setup
```

`dispatch` (`:155`): split → lookup → nieznana opcja = komunikat + `True` (handler nie leci) → `handler(context, options)`. Styl opcji: **Claude-Code** (`/setup force`), nie unix (`--force`).

**Jak dodać komendę:** handler `(AppContext, frozenset[str]) -> bool` → wpis w `COMMANDS` (alfabetycznie) → **completer i `/help` gratis** → **zaktualizuj `test_commands.py:27`** (asertuje dokładny zbiór 7 nazw!) → ciężkie importy w handlerze z `# noqa: PLC0415`.

### 2.12 `anishift/cli/settings_panel.py` (188)

`_FIELDS` (`:68`) — 8 wierszy. Klawisze: `up/down` = wiersz, `left/right/enter` = `_step_field(±1)` + **natychmiastowy save**, `escape/q` = wyjście.

**Jak dodać opcję:** pole w `UserSettings` → krotka `Final` → `_Field` w `_FIELDS` → **gałąź `elif` w `_step_field` (`:97-114`)** ← bez tego pole widoczne ale martwe → ew. `_value_text`. `Literal`-typowane wymagają `# type: ignore[assignment]` przy `_cycle`.

**Brak `test_settings_panel.py`** — panel niepokryty.

### 2.13 `utils/rich_console/` — publiczne API

```python
__all__ = ["RICH_THEME", "Colors", "ProgressBarBuilder", "ProgressBarManager",
           "StatusType", "console", "format_bytes", "format_duration",
           "format_percentage", "get_progress_color", "get_status_icon"]
```

**`console.print` jest zmonkeypatchowany** (`console.py:375`) — auto-highlight URL/ścieżek/liczb, ale tylko poza markupem Rich. `capsys` łapie normalnie.

Style używane w `anishift/`: `success`, `error`, `warning`, `info`, `gray`, `bold`, `ruby_red_bold`.

**`ProgressBarManager`** (`progress/manager.py:302`), sygnatura `:326-343`:
```python
ProgressBarManager(
    description="Processing...", total: int | None = None,
    colors: dict[int, tuple[str, str]] | None = None,
    bar: str = "rich",            # "rich" | "blocks" | "custom"
    custom_chars=None, unknown_style="ruby_red_bold",
    max_description_length=25, truncate_mode="end",
    show_bar=True, show_percentage=True, show_spinner=False,
    show_elapsed=True, show_eta=False, show_download=False, show_speed=True,
)
```
Metody: `__enter__`, `__exit__`, **`advance(amount=1)`** (`:576`), `update_style(current)` (`:588`).
`DEFAULT_COLORS` (`:318`): `{25: red_bold, 50: orange_bold, 75: yellow_bold, 100: green_bold}`.

**Kanoniczne użycie — `installer.py:272-282`.** **Wzór wielowątkowy z lockiem — `installer.py:420-447`** (manager NIE jest thread-safe).

> **ETAP 3.1:** `self.task: TaskID | None` (`:383`), `add_task` raz w `__enter__` (`:542-554`). **`rich.Progress` natywnie umie multi-task** — problem w naszym wrapperze. Najgłębszy bloker: kolumny trzymają styl na sobie (`ColoredPercentageColumn.render`, `:203-208` → `Text(..., style=self.style_name)`), kolumna współdzielona przez wszystkie wiersze → każdy pasek dostanie kolor ostatnio zaktualizowanego. **Fix: styl do `task.fields`.** `_BLOCK_BAR_COLORS` **nie istnieje** (nazwa zmyślona w notatkach 2.5).

---

## 3. Graf zależności

```
                          errors.py  (liść — tylko stdlib)
                              ↑
        ┌─────────────────────┼──────────────────────┬─────────────────┐
   config/workspace     platform/binaries      setup/manifest    setup/installer
        ↑                     ↑                      ↑                 ↑
        │                     └──────────┬───────────┘                 │
        │                          setup/doctor ←──── config/settings  │
        └──────── bootstrap.py ──────────┤                             │
                     ↑                   │                             │
        ┌────────────┼───────────────────┴─────────────────────────────┘
   cli/banner    cli/commands ──(lazy)──→ cli/settings_panel, setup/installer
                     ↑
                cli/completer
                     ↑
                 cli/shell  ←── bootstrap, banner, commands, completer
                     ↑
                 cli/main  (Typer; lazy import bootstrap+shell)

  utils.rich_console ← installer, commands, main, banner, shell
  config/user_settings — ZERO importów z projektu (liść)
```

**Bez cykli.** `commands.py` → `installer` **tylko leniwie** w handlerze + `TYPE_CHECKING`.

---

## 4. Wzorce do naśladowania

### 4.1 Szkielet modułu

```python
"""One-line summary ending with a period.

Longer paragraph explaining the *why*.

Public API:
    Thing: What it is.
    do_thing: What it does.
"""

from __future__ import annotations          # ZAWSZE, pierwszy

import json                                 # stdlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx                                # third-party

from anishift.errors import ErrorCode, ErrorContext, FatalError   # first-party
from utils.rich_console import console

__all__ = ["Thing", "do_thing"]             # posortowane, tuż po importach

# ── Constants ────────────────────────────────────────────────────────────────

_CHUNK_SIZE: Final[int] = 1 << 20
"""Docstring pod KAŻDĄ stałą Final — twardy wymóg repo."""


class ThingError(FatalError):
    """Raised when ..."""


@dataclass(frozen=True, slots=True)
class Thing:
    """Summary.

    Attributes:
        name: What it is.
    """

    name: str
```

### 4.2 Jak się rzuca błędy

**Wzorzec A — fabryka `_fail`** (`manifest.py:119`, `installer.py:144`):
```python
def _fail(message: str) -> ManifestError:
    """Build a :class:`ManifestError` with a consistent context."""
    return ManifestError(context=ErrorContext(
        code=ErrorCode.CONFIG_INVALID,
        message=f"resource manifest: {message}",
        suggestion="external/bin_hashes.json is broken — fix it or report a bug",
    ))

msg = f"resource {name} needs a source object"    # msg do zmiennej (TRY003/EM101)
raise _fail(msg)
```

**Wzorzec C — mapowanie obcego wyjątku, OSOBNY except na typ** (`installer.py:333-348`):
```python
try:
    _install_single(resource, root)
except httpx.HTTPError as exc:
    raise InstallerError(context=ErrorContext(code=ErrorCode.NETWORK_ERROR, ...)) from exc
except OSError as exc:                                    # OSOBNY blok! (bug ruff-format)
    raise InstallerError(context=ErrorContext(code=ErrorCode.IO_ERROR, ...)) from exc
```

Zawsze: `context=ErrorContext(...)`, `suggestion` z konkretną akcją, `from exc`. Nigdy `except Exception` (BLE001).

### 4.3 Typowy test

Plik `tests/test_<moduł>.py` (płasko). Funkcja `test_<co>_<oczekiwanie>` — pełne zdanie.

```python
"""Tests for the resource installer (no network — synthetic archives)."""

from __future__ import annotations
from pathlib import Path
import pytest

from anishift.setup import installer                    # moduł — do monkeypatch
from anishift.setup.installer import ensure_binary      # symbole — do wywołania
```
**Dwa importy tego samego modułu to celowy wzorzec.**

**Helpery — prywatne `_` na górze pliku, nie fixture'y:** `_zip()`, `_resource()`, `_context()`.
**Fixture'y — tylko gdy potrzebny `monkeypatch`** (2 w całym repo).
**Fake'i zamiast mocków:**
```python
def _never(_resource: Resource, _target: Path) -> None:
    raise AssertionError("download must not be called when already present")
```
**Injection pod testy w produkcyjnym API:** `install_resource(..., download: DownloadFn = _download_httpx)`, `ensure_resource(..., resources=None, dest_root=None)`.

**Asercje:** `is True/False/None`, `is CheckStatus.OK`, `pytest.raises(Err, match="...")`, `capsys.readouterr().out`.

**Per-file ignores:** `"tests/**" = ["D", "S101", "PLR2004", "TRY003"]` → **testy bez docstringów**.

> **`conftest.py` NIE ISTNIEJE.** Każdy plik samowystarczalny. Etap 3 wprowadzi pierwszy, jeśli potrzebuje — to nowy byt, świadoma decyzja.

### 4.4 Rendering — domena zwraca dane, CLI renderuje

```python
_STATUS_ICON: dict[CheckStatus, StatusType] = {...}
"""Maps a doctor check outcome to a ``rich_console`` status-icon name."""

for result in results:
    icon = get_status_icon(_STATUS_ICON.get(result.status, "info"))
    console.print(f"{icon} [bold]{result.name}[/bold]: {result.message}")
```
`run_doctor`/`run_setup` **nic nie drukują**. Etap 3: pipeline zwraca strukturę, `shell.py` renderuje. Wyjątek: `ProgressBarManager` żyje tam, gdzie leci strumień.

---

## 5. Punkty zaczepienia dla etapu 3

| # | Gdzie | Co |
|---|---|---|
| **1** | **`cli/shell.py:62-64`** | Gałąź `if not stripped:` → wywołanie pipeline'u. Rozważyć lokalny `except KeyboardInterrupt` (dziś Ctrl+C ubija REPL). |
| **2** | `setup/installer.py:369` | `ensure_binary(Binary.MKVMERGE)` przed `-J`; `ensure_binary(Binary.MKVEXTRACT)` przed ekstrakcją. Łapać `InstallerError`/`BinaryNotFoundError`. |
| **3** | `errors.py:55-59` | Kody **już są**. Nowe klasy → w modułach domenowych. **Nie dodawać do `errors.py`.** |
| **4** | `cli/commands.py:138` | Nowa komenda → handler + wpis. **Zaktualizować `test_commands.py:27`.** |
| **5** | `cli/settings_panel.py:68` + `:97` | Nowa opcja — 6 kroków. Bez gałęzi w `_step_field` pole martwe. |
| **6** | `bootstrap.py:29` | `AppContext` = 3 pola. Rozważyć: czy pipeline potrzebuje pola, czy wystarczy argument. |
| **7** | `config/workspace.py:41` | `DEFAULT_SUBDIRS = ("tmp","output")`. Discovery płasko w `workspace_root`. **Nie dodawać podkatalogów.** |
| **8** | `utils/rich_console/progress/manager.py:302` | 1 task, nie thread-safe. Multi-pasek = **etap 3.1**. |
| **9** | `pyproject.toml` | `pysubs2 1.8.1`, `pyasstosrt 1.5.0`, `pysrt 1.1.2`, `natsort 8.4.0` — **już są**. Nowa zależność **tylko `uv add`**. |
| **10** | `tests/` | Brak `conftest.py`. Dataset ASS **poza repo** (`../mm_avh_working_space/temp/dataset_ass/`) — testy regresji potrzebują decyzji o skipie w CI. |
| **11** | `external/bin_hashes.json` | Tylko `mkvtoolnix` + `ffmpeg`, Windows-only. **CI to ubuntu** — testy nie mogą zakładać zbundlowanych binarek. |

### Bramki jakości

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/          # strict, plugin pydantic
uv run pytest                          # testpaths=["tests"], addopts="-q"
```

**ruff:** py314, line-length 120, select `E,F,W,I,N,UP,B,S,BLE,G,T20,C4,SIM,RET,PTH,PT,TRY,PERF,PL,LOG,D,RUF`, ignore `D100,D104,D105,D107`, google. Exclude: `external`, `workspace`, `scripts/tmp`, **`utils`**.

⚠️ **Bug ruff 0.15.21 format:** psuje `except (A, B):` → `except A, B:`. **Rozbijać na osobne bloki.**
⚠️ **T20 włączone** → `print()` zabroniony. Zawsze `console.print`.

**Commity:** Conventional Commits (hook), **zero śladów AI**. Flow: branch → PR → CodeRabbit → merge.

---

## 6. Rzeczy zaskakujące

1. **`conftest.py` nie istnieje** — etap 3 wprowadzi pierwszy, jeśli potrzeba.
2. **`cool_animation.py`/`execution_timer.py` nie istnieją** (plan strategiczny kłamie). `ExecutionTimer` → `utils/timer/__init__.py:138`.
3. **`number_in_words`/`text_chunker` są w `scripts/tmp/`**, nie `utils/` — surowy mm_avh, bez typów, wyłączony z bramek. Etap 6.
4. **`utils/logger` (2352 linie) — `anishift/` NIE importuje ani razu.** OFF.
5. **Na Windows PATH nie jest przeszukiwany** — tylko `external/bin/`.
6. **`TOOL_DIR[BALCON] == "balabolka"`** — jedyny przypadek katalog ≠ nazwa.
7. **`console.print` zmonkeypatchowany** (`console.py:375`).
8. **`AppContext`/`UserSettings` mutowalne** (`slots` bez `frozen`); `Command`/`CheckResult`/`Resource`/`ErrorContext` — `frozen=True`.
9. **Docstring pod każdą stałą `Final`** — twardy wymóg repo, nietypowy w Pythonie.
10. **CI to tylko ubuntu-latest.** Testy Windows: `monkeypatch.setattr(module, "is_windows", lambda: True)` (wzór `test_installer.py:185`).
11. **`external/docs/{ffmpeg,mkvtoolnix}/*.html`** — zwendorowane manuale dla przypiętych wersji (`4a1ae15`), źródło prawdy o flagach CLI.

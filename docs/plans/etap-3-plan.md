# Etap 3.1 + 3 — plan wykonawczy

> Data: 2026-07-17 | Autor: Fable | Realizuje: `docs/plans/etap-3-wymagania.md` (zaakceptowane wymagania — kontrakt).
> Źródła zweryfikowane w kodzie: `docs/reference/stan-repo.md` (mapa repo), `../mm_avh_working_space/modules/{mkvtoolnix,track_selector,subtitle,style_classifier}.py` + `start.py` (materiał źródłowy portu), `utils/rich_console/progress/manager.py` (676 linii, przeczytany w całości), `external/docs/mkvtoolnix/mkvextract.html` (`--gui-mode` → `#GUI#progress N%`, potwierdzone w :191-198).
> Zasada: **KOD > AUDYT**. Wszystkie liczby w tym planie pochodzą z pomiarów opisanych w wymaganiach albo z lektury kodu — nic z pamięci.

Plan jest pisany tak, żeby agent kodujący **nie podejmował żadnych decyzji projektowych** — każda sygnatura, stała, nazwa pliku i wartość progu jest rozstrzygnięta tutaj. Tam, gdzie wartość musi wyjść z pomiaru (sufit równoległości, próg FBF, lista 2 znanych pudeł), plan podaje **dokładną procedurę pomiaru** i miejsce wpisania wyniku.

---

## Spis treści

- **Część I — Etap 3.1: multi-task progress** (§1–§7) — BLOKER dla R11, osobny PR.
- **Część II — Etap 3: ekstrakcja + refaktor napisów** (§8–§18) — drugi PR, zależny od pierwszego.
- **Aneksy A–G** — materiał wykonawczy: mapa edge case'ów, pełna mapa kodeków, dokładne ciała funkcji zmienionych w portach, implementacje wzorcowe najtrudniejszych funkcji, fixtura testowa ASS, mock-up raportu, checklist antywzorców + komunikaty commitów.

Dwa osobne branche i PR-y:

1. `feat/stage-3-1-multi-progress` → PR → CodeRabbit → merge do `main`.
2. `feat/stage-3-extraction-subtitles` (branch wg `stan-repo.md` już istnieje na `9e002b9`; jeśli jest — `git rebase main` po merge PR-u 3.1; jeśli nie — utworzyć z `main`) → PR → merge.

Nigdy commit na `main`. Commity Conventional Commits, **zero śladów AI** (zero `Co-Authored-By`, zero stopek — dotyczy też PR body).

---

# CZĘŚĆ I — ETAP 3.1: multi-task progress

## 1. Rozstrzygnięcie D6

**Decyzja: wariant (b) w wersji minimalnej — nowa klasa `MultiProgressManager` w nowym pliku `utils/rich_console/progress/multi.py` + chirurgiczny fix kolumn w `manager.py`. `ProgressBarManager` zostaje nietknięty poza kolumnami i NIE staje się wrapperem. Migracja `installer.py` NIE następuje.**

Uzasadnienie (rozważone oba warianty z D6):

1. **Najgłębszy bloker i tak wymusza dotknięcie kolumn.** Kolumny (`ColoredPercentageColumn.render`, `manager.py:203-208` → `Text(..., style=self.style_name)`) trzymają styl na sobie, a jedna instancja kolumny jest współdzielona przez wszystkie wiersze `rich.Progress` — przy N taskach każdy pasek dostałby kolor ostatnio zaktualizowanego. Fix („styl do `task.fields`, z fallbackiem na `self.style_name`") jest **wspólny dla obu wariantów D6** i **wstecznie zgodny** — stary jednotaskowy manager nie ustawia pola, więc fallback zachowuje dzisiejsze zachowanie co do znaku.
2. **Wariant (a) = większa operacja na quasi-nietykalnym kodzie.** Retrofit `ProgressBarManager` (676 linii) na multi-task oznacza: przeniesienie stanu per-task (`self.task:383`, `self.current_style:381`, `self.last_successful_progress:382`) do słownika, zmianę sygnatur `advance`/`update_style`, przebudowę `__enter__`/`__exit__` (`:538-574`) i migrację 2 call-site'ów (`installer.py:272`, `:428`) — czyli ryzyko regresji w działającym, przetestowanym pobieraczu z etapu 2.5 (369 linii testów w `test_installer.py`). Skill `simple`: chirurgiczne zmiany, nie refaktoryzuj tego, co nie jest zepsute.
3. **Wariant (b) z „obecny jako wrapper" odrzucony w połowie** — przepisanie 676 linii na wrapper to jeszcze większy churn niż (a), bez żadnej korzyści funkcjonalnej. Nowa klasa + stary bez zmian = minimalny diff.
4. **Duplikacji stylu nie ma.** User odrzucił duplikowanie stylu paska **do modułów domenowych** (jak w mm_avh `start.py:158-164`, gdzie ekstrakcja składa własny `rich.Progress`). Tu wszystko zostaje w `utils/rich_console/progress/`: `MultiProgressManager` **współdzieli** z `ProgressBarManager` klasy kolumn, `ProgressBarBuilder.blocks()` (`:103`) i `DEFAULT_COLORS` (`:318`). Jedyne zduplikowane ~10 linii to składanie listy kolumn — akceptowalne wobec ryzyka wariantu (a).
5. **`MultiProgressManager` obsługuje wyłącznie pasek `blocks`.** Powód techniczny: tryb `rich` używa `BarColumn`, który trzyma `complete_style` na kolumnie (`manager.py:490-495`) i **nie czyta `task.fields`** — per-task kolory w trybie `rich` wymagałyby subclassowania `BarColumn` i przebudowy jego renderu. Tryby `blocks`/`custom` idą przez `TextColumn("{task.fields[custom_bar]}")` (`:520`) — pole **już jest per-task**, kolor siedzi w markupie stringa. Blocks to zarazem wygląd używany w AniShift (installer `:275` używa `bar="blocks"`). Tryb `rich`/`custom_chars` w multi = YAGNI.
6. **Thread-safety wchodzi do środka.** `advance()` ma niezabezpieczone `self.last_successful_progress += amount` (`manager.py:582`) — dziś maskowane zewnętrznym lockiem w `installer.py:443-444`. `MultiProgressManager` dostaje wewnętrzny `threading.Lock` — ekstrakcja (ThreadPoolExecutor) woła go bez własnego locka.
7. **Beneficjent 2.5 (per-zasób paski pobieracza) → issue**, nie ten etap. Zero nieproszonych refaktorów.

**Konsekwencja:** sekcja „migracja 2 call-site'ów" z sugerowanego kształtu planu jest **pusta z uzasadnieniem** (§4).

## 2. Stan obecny — co dokładnie blokuje (plik:linia)

Wszystko zweryfikowane w `utils/rich_console/progress/manager.py`:

| # | Bloker | Miejsce | Mechanizm |
|---|--------|---------|-----------|
| 1 | Jeden task na managera | `:383` `self.task: TaskID \| None = None`; `add_task` wołane raz w `__enter__` (`:542-554`) | API nie przyjmuje task id — `advance(amount)` zawsze celuje w `self.task`. |
| 2 | Styl na kolumnie, nie na tasku | `ColoredPercentageColumn.render` `:203-208`; analogicznie `ColoredElapsedColumn:222`, `ColoredETAColumn:246`, `ColoredBytesColumn:270`, `ColoredSpeedColumn:290` | `Text(..., style=self.style_name)` — kolumna współdzielona przez wszystkie wiersze `Progress`, więc ostatni `_update_colors` (`:603-650`) przemalowuje **wszystkie** paski. |
| 3 | Stan koloru/postępu na managerze | `:381-382` `self.current_style`, `self.last_successful_progress` | Per-task musi być per-task. |
| 4 | `advance` nie jest thread-safe | `:582` `self.last_successful_progress += amount` | Dziś lock zewnętrzny (`installer.py:443-444`). |
| 5 | Custom bar per task JUŻ działa | `:520` `TextColumn("{task.fields[custom_bar]}")`, `:549-554` `custom_bar=` w `add_task`, `:676` `progress.update(self.task, custom_bar=bar)` | `task.fields` to natywny per-task mechanizm richa — to jest droga dla stylu. |

Fakty pomocnicze: `rich.Progress` natywnie umie multi-task (`add_task` zwraca `TaskID`, `update(task_id, ...)`). `_BLOCK_BAR_COLORS` **nie istnieje** — realne symbole to `DEFAULT_COLORS` (`:318-324`, progi `{25: red_bold, 50: orange_bold, 75: yellow_bold, 100: green_bold}`) i `ProgressBarBuilder.blocks()` (`:103-131`, rysuje `█▌░`).

**To jedyne dopuszczalne ruszenie `utils/`** (zatwierdzone przez usera). `utils/` jest poza bramkami ruff/mypy (`pyproject.toml:66` exclude, `:114` mypy exclude) — mimo to **nowy kod w `multi.py` piszemy w pełnym standardzie repo** (docstringi Google, `Final` z docstringami, typy) — to nowy plik, nie zabytek.

## 3. Zmiany plik po pliku

### 3.1.a `utils/rich_console/progress/manager.py` — fix kolumn (chirurgiczny)

Jedna nowa stała w sekcji `# ── Constants ──` (po `_MAX_DESCRIPTION_DISPLAY`, `:93`):

```python
_STYLE_FIELD: Final[str] = "style"
"""Per-task field name that overrides a column's shared ``style_name``."""
```

W **pięciu** klasach kolumn (`ColoredPercentageColumn`, `ColoredElapsedColumn`, `ColoredETAColumn`, `ColoredBytesColumn`, `ColoredSpeedColumn`) każda metoda `render` zamienia użycie `self.style_name` na lokalną zmienną z fallbackiem. Wzór — `ColoredPercentageColumn.render` (`:203-208`) po zmianie:

```python
    def render(self, task: Task) -> Text:
        """Render percentage or empty text for indeterminate tasks."""
        style = task.fields.get(_STYLE_FIELD) or self.style_name
        if task.total is None:
            return Text("", style=style)
        percentage = min(100, int(task.percentage))
        return Text(f"| {percentage:>3d}%", style=style)
```

Analogicznie w pozostałych czterech: pierwszą linią `render` jest `style = task.fields.get(_STYLE_FIELD) or self.style_name`, a każde wystąpienie `self.style_name` w tej metodzie zamienia się na `style`. Liczba wystąpień do podmiany: Percentage — 3 (`:206,207,208`), Elapsed — 1 (`:231`), ETA — 3 (`:249,252,256`), Bytes — 1 (`:276`), Speed — 2 (`:294,296`).

**Czego NIE ruszać:** `DynamicSpinnerColumn` (`:163-189`) — trzyma instancję `Spinner` ze stylem na sobie; `MultiProgressManager` nie używa spinnera, a przenoszenie stylu spinnera do fields wymagałoby per-task instancji `Spinner` — YAGNI. `BarColumn` konfiguracja (`:490-495`) — bez zmian (tryb `rich` pozostaje jednotaskowy). Cała reszta pliku — **bez zmian**.

Wsteczna zgodność: `ProgressBarManager` nigdy nie ustawia pola `"style"` w `task.fields`, więc `task.fields.get(_STYLE_FIELD)` zwraca `None` → fallback `self.style_name` → zachowanie identyczne jak dziś. To gwarantuje zero regresji w installerze bez dotykania go.

### 3.1.b `utils/rich_console/progress/multi.py` — NOWY plik (~230 linii)

Pełna specyfikacja — agent przepisuje 1:1 (docstringi włącznie; wolno tylko poprawić literówki):

```python
"""Multi-task progress manager with per-task colors and block-style bars.

Renders one block-style bar (``█▌░``) per task inside a single
``rich.Progress`` live display. Each task keeps its own color transition:
the style travels in ``task.fields`` so rows never repaint each other.
All mutating methods are thread-safe.

Usage:
    >>> with MultiProgressManager() as mp:
    ...     first = mp.add_task("episode 1.mkv")
    ...     second = mp.add_task("episode 2.mkv")
    ...     mp.update(first, 40)
    ...     mp.advance(second, 5)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from rich.progress import Progress, TaskID, TextColumn

from ..console import console
from .manager import (
    ColoredElapsedColumn,
    ColoredPercentageColumn,
    ProgressBarBuilder,
    ProgressBarManager,
)

if TYPE_CHECKING:
    from types import TracebackType

__all__ = ["MultiProgressManager"]

# ── Constants ────────────────────────────────────────────────────────────────

_STYLE_FIELD: Final[str] = "style"
"""Per-task field carrying the current Rich style of the task's row."""

_BAR_FIELD: Final[str] = "custom_bar"
"""Per-task field carrying the pre-rendered block bar markup."""

_BASE_INFO_WIDTH: Final[int] = 23
"""Character width reserved for the percentage and elapsed columns."""

_MAX_BAR_WIDTH: Final[int] = 40
"""Maximum bar width in characters."""

_MIN_BAR_WIDTH: Final[int] = 3
"""Minimum bar width to prevent a degenerate display."""

_ELLIPSIS: Final[str] = "..."
"""Suffix appended to descriptions truncated at the tail."""


@dataclass(slots=True)
class _TaskState:
    """Mutable per-task bookkeeping.

    Attributes:
        description: Truncated task label (without color markup).
        total: Total units of the task.
        completed: Units completed so far.
        style: Current Rich style of the task's row.
    """

    description: str
    total: int
    completed: int
    style: str


class MultiProgressManager:
    """Thread-safe multi-task progress display with per-task color transitions.

    Shares the block-bar builder, colored columns and the default color
    thresholds with :class:`ProgressBarManager`; differs in cardinality
    (many tasks) and thread safety (internal lock, no external lock needed).

    Example:
        >>> with MultiProgressManager() as mp:
        ...     task = mp.add_task("file.mkv", total=100)
        ...     mp.update(task, 100)
    """

    def __init__(
        self,
        *,
        colors: dict[int, tuple[str, str]] | None = None,
        max_description_length: int = 40,
    ) -> None:
        """Initialize the display without starting it.

        Args:
            colors: Color transitions as ``{percentage: (text, bar)}``;
                defaults to ``ProgressBarManager.DEFAULT_COLORS``.
            max_description_length: Longest description before tail truncation.
        """
        self._colors = colors or ProgressBarManager.DEFAULT_COLORS
        self._max_description_length = max(5, max_description_length)
        self._lock = threading.Lock()
        self._states: dict[TaskID, _TaskState] = {}
        self._bar_width = self._calculate_bar_width()
        initial_style = next(iter(self._colors.values()))[0]
        self._progress = Progress(
            TextColumn("{task.description}"),
            TextColumn(f"{{task.fields[{_BAR_FIELD}]}}", justify="left"),
            ColoredPercentageColumn(initial_style),
            ColoredElapsedColumn(initial_style),
            console=console,
            expand=False,
        )

    def __enter__(self) -> MultiProgressManager:
        """Start the live display and return self."""
        self._progress.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Stop the live display, leaving every task at its last state."""
        self._progress.stop()

    def add_task(self, description: str, *, total: int = 100) -> TaskID:
        """Add one bar row and return its id.

        Args:
            description: Row label; truncated at the tail when too long.
            total: Total units of the task (100 for percent-driven feeds).

        Returns:
            The task id accepted by :meth:`advance` and :meth:`update`.
        """
        with self._lock:
            label = self._truncate(description)
            style = self._style_for(0, total)
            task_id = self._progress.add_task(
                f"[{style}]{label}",
                total=total,
                **{
                    _STYLE_FIELD: style,
                    _BAR_FIELD: ProgressBarBuilder.blocks(self._bar_width, 0.0, style),
                },
            )
            self._states[task_id] = _TaskState(label, total, 0, style)
            return task_id

    def advance(self, task_id: TaskID, amount: int = 1) -> None:
        """Advance one task by *amount* units.

        Args:
            task_id: Task returned by :meth:`add_task`.
            amount: Units to add to the task's completed count.
        """
        with self._lock:
            state = self._states[task_id]
            self._apply(task_id, state, state.completed + amount)

    def update(self, task_id: TaskID, completed: int) -> None:
        """Set one task's absolute completed count.

        Args:
            task_id: Task returned by :meth:`add_task`.
            completed: Absolute completed units (clamped to the task total).
        """
        with self._lock:
            self._apply(task_id, self._states[task_id], completed)

    def _apply(self, task_id: TaskID, state: _TaskState, completed: int) -> None:
        """Write one task's new completed count, restyling when needed."""
        state.completed = max(0, min(state.total, completed))
        style = self._style_for(state.completed, state.total)
        ratio = state.completed / state.total if state.total else 0.0
        bar = ProgressBarBuilder.blocks(self._bar_width, ratio, style)
        fields = {_BAR_FIELD: bar}
        description: str | None = None
        if style != state.style:
            state.style = style
            fields[_STYLE_FIELD] = style
            description = f"[{style}]{state.description}"
        if description is not None:
            self._progress.update(task_id, completed=state.completed, description=description, **fields)
        else:
            self._progress.update(task_id, completed=state.completed, **fields)

    def _style_for(self, completed: int, total: int) -> str:
        """Return the transition style for a completed/total ratio."""
        percentage = min(100, int((completed / total) * 100)) if total else 0
        for threshold, (_text, bar_color) in sorted(self._colors.items()):
            if percentage <= threshold:
                return bar_color
        return next(reversed(list(self._colors.values())))[1]

    def _truncate(self, description: str) -> str:
        """Tail-truncate *description* to the configured maximum."""
        limit = self._max_description_length
        if len(description) <= limit:
            return description
        return description[: limit - len(_ELLIPSIS)] + _ELLIPSIS

    def _calculate_bar_width(self) -> int:
        """Fit the bar between the description and the info columns."""
        available = console.width - self._max_description_length - _BASE_INFO_WIDTH
        return max(_MIN_BAR_WIDTH, min(_MAX_BAR_WIDTH, available))
```

Uwagi wiążące dla agenta:

- `_style_for` celowo powiela logikę progową `_update_colors` (`manager.py:608-617`) w wersji czystej (bez mutacji kolumn) — kolumny czytają styl z `task.fields`, więc mutowanie ich stanu jest zbędne. Nie wyciągać wspólnej funkcji do `manager.py` — stara ścieżka zostaje nietknięta (chirurgia).
- `add_task` przekazuje pola przez `**{...}` bo nazwy pól są stałymi (`_STYLE_FIELD`, `_BAR_FIELD`) — nie hardcodować literałów drugi raz.
- `__exit__` **nie** domyka pasków do 100% (inaczej niż `ProgressBarManager.__exit__:565-567`) — przy wielu plikach pasek pliku, który padł, ma uczciwie zostać tam, gdzie stanął. To świadoma różnica.
- Metody publiczne: dokładnie `add_task`, `advance`, `update` + context manager. `advance` jest potrzebny na przyszłość (etap 6, TTS liczy linie) i do testów; ekstrakcja używa `update` (absolutny procent z mkvextract).

### 3.1.c Eksporty

`utils/rich_console/progress/__init__.py` — dopisać import i pozycję w `__all__` (alfabetycznie):

```python
from .multi import MultiProgressManager
```

`utils/rich_console/__init__.py` — analogicznie dopisać `MultiProgressManager` do importów z `.progress` i do `__all__` (alfabetycznie, obok `ProgressBarManager`).

## 4. Migracja call-site'ów `installer.py` — NIE MA

`installer.py:272` (`_install_single`) i `:428` (`_install_parallel`) zostają **bez zmian** — konsekwencja D6(b) z §1. Fix kolumn jest wstecznie zgodny (fallback), więc `/setup` zachowuje się identycznie. Per-zasób paski pobieracza → issue (§18). Weryfikacja braku regresji: `uv run pytest tests/test_installer.py` (369 linii istniejących testów) + ręczny `/setup` (patrz §6 krok 4).

## 5. Testy 3.1 (bez sieci)

Nowy plik `tests/test_multi_progress.py`. Konwencje repo: helpery `_`-prefiksowane na górze pliku, bez fixture'ów (poza `capsys`), asercje `is`/`==`, per-file-ignores dla testów już skonfigurowane. Import wzorem repo (dwa importy tego samego modułu nie są tu potrzebne — nie ma monkeypatchowania):

```python
"""Tests for the multi-task progress manager (no live display started)."""

from __future__ import annotations

import threading

from utils.rich_console import MultiProgressManager
```

Kluczowa technika: `rich.Progress.add_task`/`update` działają **bez** `start()` — testy stanu nie wchodzą w context manager, więc nic nie renderuje się do terminala. Tylko jeden test smoke używa `with` + `capsys`.

Lista testów (nazwy = pełne zdania, dokładnie te):

1. `test_add_task_returns_distinct_ids_and_initial_style` — manager bez `with`; 2 × `add_task`; id różne; `mp._progress.tasks[0].fields["style"] == "red_bold"` (pierwszy kolor `DEFAULT_COLORS`).
2. `test_tasks_keep_independent_styles_after_updates` — 2 taski, `update(a, 20)`, `update(b, 80)`; pole `style` taska a == `"red_bold"` (20 ≤ 25), taska b == `"green_bold"` (80 ≤ 100 przy progach 25/50/75/100 → pierwszy próg ≥ 80 to 100); style **różne** — to jest test na bloker #2.
3. `test_custom_bar_field_reflects_completion` — po `update(t, 50)` pole `custom_bar` zawiera `█` i `░`; po `update(t, 100)` nie zawiera `░`.
4. `test_update_clamps_to_total_and_zero` — `update(t, 150)` → completed 100; `update(t, -5)` → 0.
5. `test_advance_accumulates` — 3 × `advance(t, 10)` → completed 30.
6. `test_parallel_advance_is_thread_safe` — 4 wątki × 25 × `advance(t, 1)` (`threading.Thread`, join); completed == 100. Bez locka zewnętrznego.
7. `test_long_description_is_tail_truncated` — opis 60 znaków przy `max_description_length=20` → stan `description` ma długość 20 i kończy się `"..."`.
8. `test_context_manager_smoke` (`capsys`) — `with MultiProgressManager() as mp:` + 1 task + `update` do 100; wyjście bez wyjątku; `capsys.readouterr()` nie assertuje treści (rendering terminalowy), tylko brak wyjątku.
9. `test_single_task_manager_columns_fall_back_without_field` — regresja fixu z §3.1.a: `ProgressBarManager` (stary) tworzony bez `with`; jego kolumna `percentage_col.render` na tasku bez pola `style` zwraca `Text` ze stylem `== manager.percentage_col.style_name`. (Import `ProgressBarManager` z `utils.rich_console`; task budowany przez `manager.progress.add_task(...)` bez startu.)

Uwaga mypy: `utils/` jest poza mypy, ale **testy są w bramkach** — atrybuty prywatne (`mp._progress`) w testach są dopuszczalne (testujemy stan wewnętrzny; `SLF001` nie jest w select). Jeśli mypy zgłosi `Any` z nietypowanego `utils`, dodać adnotacje lokalne w teście (`mp: MultiProgressManager = ...` wystarcza — moduł ma pełne typy inline).

## 6. Kolejność implementacji 3.1 + weryfikacja każdego kroku

1. **Branch** `feat/stage-3-1-multi-progress` z aktualnego `main`.
   → weryfikacja: `git status` czysty, `uv run pytest` zielone na starcie (baseline).
2. **Fix kolumn w `manager.py`** (§3.1.a) — stała `_STYLE_FIELD` + 5 × `render`.
   → weryfikacja: `uv run pytest tests/test_installer.py` zielone (installer używa pasków w `_install_single`/`_install_parallel` przez fake'i — zero sieci); ręcznie: `uv run python -c "from utils.rich_console import ProgressBarManager; import time;\nwith ProgressBarManager('demo', total=50, bar='blocks') as pb:\n    [pb.advance(1) or time.sleep(0.02) for _ in range(50)]"` (jako plik w scratchpadzie, nie inline — wieloliniowy) — pasek przechodzi kolory jak dotychczas.
3. **`multi.py` + eksporty** (§3.1.b, §3.1.c).
   → weryfikacja: `uv run python` demo-skrypt w scratchpadzie: `with MultiProgressManager() as mp:` 3 taski aktualizowane naprzemiennie w pętli z `time.sleep(0.02)` — trzy paski, **różne kolory w tym samym momencie** (np. jeden na 20%, drugi na 60%, trzeci na 95%). To jest wizualna weryfikacja blokera #2.
4. **Testy** (§5).
   → weryfikacja: `uv run pytest tests/test_multi_progress.py -q` zielone; potem pełne bramki: `uv run ruff check anishift/ tests/ && uv run ruff format --check anishift/ tests/ && uv run mypy anishift/ tests/ && uv run pytest`.
5. **Ręczny sanity `/setup`** — `uv run anishift`, `/setup` (binarki już są → same „skipped", zero sieci); pasek nie pojawia się lub pojawia jak dotąd; wyjście bez błędu.
   → weryfikacja: brak zmian w zachowaniu.
6. **PR** `feat: stage 3.1 — multi-task progress in rich_console` — opis: co i dlaczego (D6), zrzut/nagranie demo 3 pasków mile widziane. CodeRabbit review → `/coderabbit` → merge.

## 7. Definition of Done — etap 3.1

- [ ] `MultiProgressManager` eksportowany z `utils.rich_console`; N pasków, każdy z własnym kolorem przejścia (weryfikacja wizualna z kroku 3 §6).
- [ ] Kolumny czytają styl z `task.fields` z fallbackiem — `ProgressBarManager` działa identycznie jak przed zmianą (`tests/test_installer.py` zielone bez modyfikacji).
- [ ] `advance`/`update` thread-safe bez zewnętrznego locka (test #6).
- [ ] `installer.py` — **zero zmian** w pliku (git diff pusty dla tego pliku).
- [ ] Bramki zielone: ruff check + format + mypy + pytest.
- [ ] PR zmergowany do `main` przed startem Części II.

---

# CZĘŚĆ II — ETAP 3: ekstrakcja + refaktor napisów

## 8. Rozstrzygnięcia decyzji

### 8.1 D1 — gdzie lądują pliki: wariant (b), doprecyzowany

**Decyzja:** pliki pośrednie w `workspace/tmp/<mkv_stem>/`, produkt obok MKV.

Konkretna struktura (na przykładzie `[shisha] Youjo Senki II - 01.mkv`):

```
workspace/
├── [shisha] Youjo Senki II - 01.mkv                  ← wejście, NIGDY nie ruszane (N1)
├── [shisha] Youjo Senki II - 01.displayed.ass        ← JEDYNY produkt etapu 3 (obok MKV)
└── tmp/
    └── [shisha] Youjo Senki II - 01/                 ← per-plik katalog roboczy
        ├── audio.aac                                  ← wyciągnięte audio (rozszerzenie z kodeka)
        └── subs.ass                                   ← wyciągnięte napisy — źródło prawdy, zostaje
```

Uzasadnienie: 1.4 GB audio nie zaśmieca folderu wrzutowego; produkt jest tam, gdzie user go szuka. Nazwy `audio.*`/`subs.*` (stałe, nie pochodne od pliku) — bo auto i manual wybierają **dokładnie jedną** ścieżkę audio i jedną napisową (niezmiennik §12), więc kolizje z E10 (dwie ścieżki tego samego kodeka) znikają konstrukcyjnie: nigdy nie ekstrahujemy dwóch ścieżek tego samego typu. Katalog per-plik izoluje pliki między MKV (E16). `tmp/<stem>/` jest czyszczony na starcie przetwarzania danego pliku (`utils.safe_rmtree` — retry na Windows locking) i **zostaje po przebiegu** — `audio.*` skonsumuje etap 6, `subs.*` to zachowany oryginał napisów. `DEFAULT_SUBDIRS` (`config/workspace.py:41`) **bez zmian** — per-plik katalogi to dane runtime, nie szkielet workspace.

Konsekwencja dla ponownego uruchomienia: `X.displayed.ass` jest nadpisywany (deterministycznie — N2). Jeśli user ręcznie edytował produkt, rerun go nadpisze — to zachowanie jawne i opisane; ochrona ręcznych poprawek to część issue D2(d) (§18).

### 8.2 D2 — cache: wariant (c) — BEZ cache, + issue na (d)

**Decyzja:** zgodnie z rekomendacją. Każdy przebieg: wyczyść `tmp/<stem>/`, ekstrahuj od zera. Ekstrakcja to sekundy; cache mm_avh (`mkvtoolnix.py:41,254` — plik >1024 B → skip) był ślepy (nie wiedział, z której ścieżki pochodzi plik) i stwarzał ryzyko cichego użycia złego pliku — dokładne przeciwieństwo N2/N4. E9 (plik już wyekstrahowany) → re-ekstrakcja. E19 (`film.ass` obok MKV) → etap 3 **nie czyta** zewnętrznych napisów z poziomu `workspace/` (discovery bierze tylko `*.mkv` i `*.txt`), więc konfliktu nie ma; scenariusz „zewnętrzne wygrywają" → issue (§18).

### 8.3 D3 — UNCERTAIN: wariant (b) — wyświetlaj przy niepewności

**Decyzja:** zgodnie z rekomendacją. Styl z werdyktem `UNCERTAIN` → linie idą do `displayed`. Koszt zmierzony: 0.7% linii, mediana 0/plik. **Konsekwencja dla regresji (ważne):** bazowe 95.86% zmierzono w polityce mm_avh (`UNCERTAIN` czytane — `select_dialog_styles`, `style_classifier.py:277-294`). Zmiana polityki może przesunąć liczbę „zgubił dialog" o style UNCERTAIN będące w ground truth DIALOG-iem. Dlatego test regresji (§14.5) liczy **dwa mapowania**:

- **mapowanie parytetowe** (`UNCERTAIN → spoken`, jak mm_avh) — twarde asercje DoD: `≥ 95.86%` i „zgubił dialog" ⊆ 2 znane pudła Fuji. To mierzy **port klasyfikatora** (który jest 1:1, więc musi przejść z definicji).
- **mapowanie produkcyjne** (`UNCERTAIN → displayed`, D3b) — liczone i raportowane przez `scripts/measure_split.py` (§14.7), bez twardej asercji. To jest „etap 3 dostarcza POMIAR": delta D3b trafia do PR i do issue #16.

Bez tego rozdzielenia D3(b) i DoD („zero nowych zgubił dialog poza 2 znanymi") byłyby wewnętrznie sprzeczne. DoD czytamy jako własność **klasyfikatora**, politykę D3 jako **decyzję produktową zmierzoną obok**.

### 8.4 D4 — format displayed przy wejściu SRT: wariant (b)

**Decyzja:** produkt w formacie wejścia (`.displayed.srt` dla SRT, `.displayed.ass` dla ASS/SSA). Realnie: dla SRT bez stylów heurystyka nie ma sygnału, więc **wszystkie linie SRT → spoken** i produkt `displayed` w ogóle nie powstaje (zero linii displayed → zero pliku; §11.6). Wariant (b) dotyczy ścieżki zapisu, która jest jedną linią kodu (`to_string(format_=kind)`), więc obsługujemy go w pełni, choć w praktyce dla SRT plik nie powstanie. SRT z tagami `{\an8}` (napisy „na górze") — znane ograniczenie: bez stylów nie odróżnimy ich od dialogu; czytamy (lepiej za dużo niż zgubić — spójne z E11). Odnotowane w §17.

### 8.5 D5 — tryb manual: wariant (b) teraz, (c) jako issue

**Decyzja:** manual pyta o **style**, pokazując werdykt klasyfikatora, liczbę linii (po dedupie i surową) i do 3 próbek tekstu na styl; Enter akceptuje propozycję auto. Dodatkowo manual pozwala **nadpisać wybór ścieżek** (Enter = propozycja auto): plan strategiczny (§D etap 3, „jak testować") wymaga „tryb manual pyta o wybór ścieżek", a auto-selektor bez żadnego mechanizmu nadpisania nie miałby wyjścia awaryjnego przy złym wyborze ścieżki. Obie interakcje żyją w **CLI** (`cli/pipeline_ui.py`, §13), nigdy w serwisach (N3 — zero `input()`/`sys.exit()` w serwisie). Manual działa **sekwencyjnie** (USTALONE: równoległy manual mm_avh to wyścig o stdin — nie portujemy) i **bez pasków live** (prompt w trakcie `rich.Live` łamie rendering — N8; manual to wyjście awaryjne, nie ścieżka główna). Półautomat (pytanie tylko o UNCERTAIN) → issue (§18).

### 8.6 D6 — rozstrzygnięte w §1 (wariant b, minimalny).

### 8.7 D7 — preferencje językowe: issue

**Decyzja:** zgodnie z rekomendacją — issue (§18). `track_selector` idzie 1:1 z regresją na 206 plikach (`temp/dataset.json` — istnieje, zweryfikowane: 206 wpisów `mkv` z `pick_sub`/`pick_aud`); konfigurowalne wagi natychmiast psują parytet.

### 8.8 Rozstrzygnięcia interpretacyjne (spoza listy D1–D7)

Rzeczy, które wymagania zostawiają domyślne, a agent kodujący nie może o nich decydować:

**I1 — „Collapse FBF PRZED klasyfikacją" realizuje wewnętrzny dedup portowanego klasyfikatora.** `classify_styles` (port `style_classifier.py:224-274`) już dziś liczy metryki na zdeduplikowanych liniach (`dedup_animation`, `:138-168`: ≥5 powtórzeń, mediana odstępu startów < 2000 ms) — czyli „klasyfikator dostaje 18 linii zamiast 1381" jest spełnione **przez port as-is**. Nasz osobny `collapse_fbf` (R6b, `start=min`, `end=max`) buduje **strumień spoken** (lektor czyta raz, w scalonym oknie czasowym) i NIE jest podawany klasyfikatorowi na wejściu. Powód: podanie klasyfikatorowi pre-zbitych eventów zmieniłoby jego metryki względem wersji mierzonej (95.86%) — a „ZERO strojenia" i regresja są ważniejsze niż literalne czytanie kolejności R6. Werdykty pozostają bitowo zgodne z mm_avh; DoD „1381 → 18" jest testowane na naszym sicie (odsiew rysunków + collapse) bezpośrednio na stylu `[Znaki]` pliku Fuji (§14.4).

**I2 — decyzja per linia = model danych, nie nowa heurystyka.** W etapie 3 sygnał klasyfikatora jest per-styl (port as-is); granulacja per linia bierze się z: (a) odsiewu rysunków per linia, (b) collapse FBF per grupa linii, (c) fallbacku E11/E12 per plik. Typ `Decision` przypisany **każdej linii** to rura, którą issue #16 wleje lepsze sygnały bez przebudowy. Agent NIE dodaje żadnych per-liniowych reguł ponad (a)–(c).

**I3 — displayed zachowuje WSZYSTKIE klatki animacji.** Collapse FBF dotyczy wyłącznie strumienia spoken. Linie displayed (w tym grupy FBF sklasyfikowane jako displayed) idą do produktu **w komplecie, nietknięte** — inaczej animacja typesettingu rozpadłaby się wizualnie. Grupa FBF sklasyfikowana jako spoken (SMS-y Fuji) w całości **znika z displayed** (decyzja jest rozłączna: linia jest spoken albo displayed, nigdy obie).

**I4 — detekcja rysunku: wyłącznie tag `\p1`–`\p9`.** R6a mówi wprost o `\p1-\p9`. mm_avh dodatkowo łapał ścieżki rysunkowe regexem `\b[mn] -?\d+` (`subtitle.py:55`) — NIE portujemy go do sita: bez tagu `\p` taki tekst renderuje się jako tekst (nie rysunek), a regex daje fałszywe trafienia (np. `I'm 5` zawiera `m 5`). Klasyfikator ma własny `_RE_DRAW` — nietknięty (port as-is).

**I5 — progi-literały klasyfikatora → nazwane stałe `Final` (wartości bit w bit te same).** `_classify_metrics` ma literały w porównaniach (`0.20`, `0.40`, `0.30`, `12`, `0.60` — `style_classifier.py:202-215`), które w `anishift/` łamią ruff `PLR2004` (magic value comparison; ignorowane tylko w `tests/**`). Wyciągamy **wyłącznie literały porównań** do stałych (§11.3) — zachowanie identyczne, regresja pilnuje, a przy okazji spełnia się warunek wstępny Tropu 5. Wag (`score += 0.35` itd.) NIE ruszamy — nie są porównaniami, ruff ich nie wymaga, mniejszy diff.

**I6 — R12 (TXT → SRT) w nowym modelu danych = TXT → spoken.** SRT w mm_avh był nośnikiem dla starych funkcji TTS; w AniShift spoken to stan w pamięci. Etap 3 dostarcza `txt_to_spoken()` (§11.7): plik `.txt` z `workspace/` → poprawnie pocięte linie do lektora (chunking zdaniowy), zero plików pośrednich. Stary chunker (`scripts/tmp/text_chunker.py`) ma 2 znane bugi i jest poza bramkami — piszemy prosty, samowystarczalny chunker (ok. 50 linii) zamiast go importować. „Zepsuta end-to-end" ścieżka mm_avh umiera przez przepisanie, nie łatanie. Jeśli user woli jednak plik SRT jako produkt — to jedna funkcja do zmiany; odnotować w PR.

**I7 — „pysubs2 przypięty" = przypięcie przez `uv.lock`.** Twarda reguła projektu: wersje `>=`, nigdy `==` w `pyproject.toml`. `uv.lock` trzyma dokładną wersję (dziś 1.8.1) i to on gwarantuje N2 (determinizm) w CI (`uv sync --frozen`). Zero zmian w `pyproject.toml` — `pysubs2`, `pysrt`, `natsort` już są. **Etap 3 nie dodaje żadnej nowej zależności.**

**I8 — subprocess a ruff S (bandit).** Etap 3 wprowadza pierwsze wywołania subprocess w `anishift/`. Reguła `S603` (subprocess call) wymaga adnotacji: wywołania używają **listy argumentów** (nigdy `shell=True`), a ścieżka binarki pochodzi z `ensure_binary()` (zaufana, absolutna). Na każdej linii `subprocess.run(...)`/`Popen(...)` — `# noqa: S603` z tym uzasadnieniem w komentarzu nad linią. Nie wyłączać S603 globalnie.

**I9 — pierwszy `conftest.py` wchodzi do repo.** Stan-repo: „conftest.py NIE ISTNIEJE — etap 3 wprowadzi pierwszy, jeśli potrzebuje". Potrzebuje: ścieżka do zbioru testowego poza repo (`../mm_avh_working_space/temp/`) jest współdzielona przez 3 pliki testów (klasyfikator-regresja, tracks-regresja, split-Fuji) i przez smoke; do tego wspólne skip-helpery (dataset nieobecny → skip, nie fail — CI to ubuntu-latest bez datasetu). Zawartość minimalna (§14.1).

**I10 — encoding napisów: UTF-8, błąd = E13.** mm_avh czytał ASS wyłącznie w UTF-8 (`subtitle.py:130`). Portujemy to samo (`pysubs2` z `encoding="utf-8"`); plik w innym kodowaniu (UTF-16 itp.) → `UnicodeDecodeError` → `SubtitleError` z kodem `SUBTITLE_PARSE_FAILED`, plik pominięty, reszta idzie dalej (E13 + R13). Auto-detekcja kodowań = YAGNI dopóki realny plik jej nie wymusi (do banku w issue, jeśli smoke ją wykryje).

## 9. Architektura: moduły, graf zależności, czego NIE importować

### 9.1 Nowe pliki (kompletna lista)

```
anishift/services/__init__.py                     ~5    docstring pakietu
anishift/services/extraction/__init__.py         ~25    re-eksporty
anishift/services/extraction/errors.py           ~15    ExtractionError
anishift/services/extraction/types.py            ~90    TrackInfo, MediaInfo, TrackSelection, ExtractionResult
anishift/services/extraction/tracks.py          ~290    port track_selector 1:1 + typowany wrapper select_tracks
anishift/services/extraction/service.py         ~260    identify, parse_media_info, extract_tracks, mapa kodeków
anishift/services/subtitles/__init__.py          ~30    re-eksporty
anishift/services/subtitles/errors.py            ~15    SubtitleError
anishift/services/subtitles/types.py            ~110    Decision, SpokenLine, StyleSample, SplitStats, SubtitleSplit
anishift/services/subtitles/text.py              ~90    is_drawing, visible_text, replace_visible_text
anishift/services/subtitles/classifier.py       ~300    port style_classifier 1:1 (z I5)
anishift/services/subtitles/service.py          ~260    load_subtitles, preview_styles, split_subtitles,
                                                        collapse_fbf, write_displayed
anishift/services/subtitles/txt.py               ~80    txt_to_spoken (I6)
anishift/pipeline/__init__.py                    ~20    re-eksporty
anishift/pipeline/types.py                      ~120    FileFailure, FileOutcome, PipelineReport,
                                                        ProgressReporter, PipelineInteraction
anishift/pipeline/runner.py                     ~260    discover_inputs, run_pipeline, _process_mkv, _process_txt
anishift/cli/pipeline_ui.py                     ~220    run_pipeline_command, manual prompts, render raportu
scripts/measure_split.py                        ~150    pomiar D3-delta + zysku FBF na 182 plikach (§14.7)
scripts/measure_parallel.py                      ~80    pomiar sufitu równoległości (§15 krok 12)
tests/conftest.py                                ~40    ścieżki datasetu + skip-helpery (I9)
tests/data/youjo_senki_identify.json                    fixture: przechwycone mkvmerge -J
tests/data/mushoku_identify.json                        fixture: przechwycone mkvmerge -J
tests/test_extraction_tracks.py                 ~200
tests/test_extraction_service.py                ~200
tests/test_subtitles_text.py                    ~120
tests/test_subtitles_classifier.py              ~150
tests/test_subtitles_split.py                   ~260
tests/test_subtitles_txt.py                      ~80
tests/test_pipeline_runner.py                   ~220
tests/test_regression_classifier.py             ~140    (skip bez datasetu)
tests/test_regression_tracks.py                 ~120    (skip bez datasetu)
tests/test_smoke_pipeline.py                    ~180    (skip bez binarek/plików/Windows)
```

Pliki modyfikowane: `anishift/cli/shell.py` (3 linie, §13.3). **Nic więcej.** W szczególności NIE ruszamy: `bootstrap.py` (`AppContext` zostaje przy 3 polach — pipeline dostaje context argumentem, punkt zaczepienia 6), `errors.py` (kody już są, `:55-59`), `commands.py` (żadnej nowej komendy — Enter to nie komenda), `settings_panel.py` (D7 = issue), `config/workspace.py` (D1 nie zmienia szkieletu).

Rozbieżności względem drzewa z planu strategicznego (§C) — świadome: `subtitles/cleanup.py` i `correction.py` to etapy 4–5 (nie tworzymy pustych plików); `styles.py` („hak na przyszły style_classifier") jest **nieaktualny** — klasyfikator już istnieje w mm_avh i wchodzi jako `classifier.py`; `extraction/tracks.py` zgodnie z planem. Plan strategiczny mówił też „pliki pośrednie obok MKV, jak dziś" — **nieprawda** (w mm_avh szły do `temp/`), rozstrzygnięte w D1.

### 9.2 Graf zależności (kto co importuje)

```
errors.py (root, liść)
   ↑
extraction/errors ── extraction/types ── extraction/tracks ── extraction/service
                                                                   ↑ (ensure_binary ← setup/installer)
subtitles/errors ── subtitles/types ── subtitles/text ─┬─ subtitles/classifier
                                                       └─ subtitles/service ── subtitles/txt
   ↑                                                        ↑
pipeline/types  (importuje: extraction/types, subtitles/types — TYLKO typy)
   ↑
pipeline/runner (importuje: extraction/service+tracks, subtitles/service+txt,
                 config/workspace [ensure_workspace_dir], setup/installer [ensure_binary],
                 utils [safe_rmtree], natsort)
   ↑
cli/pipeline_ui (importuje: pipeline/runner+types, utils.rich_console [console,
                 MultiProgressManager, get_status_icon], bootstrap [AppContext])
   ↑
cli/shell (lazy import pipeline_ui w gałęzi Enter)
```

Twarde zakazy importowe (agent NIE robi):

- `services/*` **nie importuje** `pipeline/*`, `cli/*`, `bootstrap`, `config/user_settings` — serwisy dostają ścieżki i parametry, nie znają trybu ani ustawień.
- `services/subtitles` **nie importuje** `services/extraction` (i odwrotnie) — łączy je wyłącznie runner.
- `services/*` **nie importuje** `utils.rich_console` — zero printów w serwisach (wzorzec 4.4 stan-repo: domena zwraca dane, CLI renderuje). Jedyny wyjątek z wzorca („ProgressBarManager żyje tam, gdzie leci strumień") realizujemy **callbackiem**: ekstrakcja dostaje `on_progress: Callable[[int], None]`, a pasek trzyma CLI.
- `pipeline/runner` **nie importuje** `utils.rich_console` ani `prompt_toolkit` — progress przychodzi jako `ProgressReporter` (Protocol), interakcja jako `PipelineInteraction` (Protocol). Runner jest w pełni testowalny bez terminala.
- Nikt nie importuje `scripts/*` ani niczego z `scripts/tmp/` (chunker z bugami — I6).
- `extraction`/`subtitles` **bez `engines/`** — zwykłe moduły (N5); rejestr silników istnieje tylko w tts/translation/llm (etapy 4–6).

### 9.3 Wzorce obowiązujące każdy nowy plik

Szkielet modułu, fabryka błędów `_fail`, osobne bloki `except` na typ (bug ruff 0.15.21 format psuje `except (A, B):`), `msg` do zmiennej przed `raise` (TRY003/EM101), `from __future__ import annotations` pierwszy, `__all__` po importach, stałe `Final` z docstringiem w sekcji `# ── Constants ──`, `dataclass(slots=True[, frozen=True])`, `Literal` dla zamkniętych zbiorów, max 2 poziomy zagnieżdżeń, guard clauses — wszystko wg wzorców 4.1–4.4 z `docs/reference/stan-repo.md`. `console.print` zamiast `print` (T20) — ale w serwisach i runnerze **żadnego printowania w ogóle**.

## 10. `anishift/services/extraction/` — plik po pliku

### 10.1 `errors.py`

```python
"""Extraction domain errors."""

from __future__ import annotations

from anishift.errors import FatalError

__all__ = ["ExtractionError"]


class ExtractionError(FatalError):
    """Raised when identifying an MKV or extracting its tracks fails."""
```

Kody używane przez ten moduł (już istnieją w `anishift/errors.py:55-56`): `EXTRACTION_FAILED`, `TRACK_NOT_FOUND`, plus generyczne `CANCELLED`, `IO_ERROR`. **Żadnych zmian w `errors.py`.**

### 10.2 `types.py`

```python
"""Extraction domain value objects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["ExtractionResult", "MediaInfo", "TrackInfo", "TrackSelection"]


@dataclass(frozen=True, slots=True)
class TrackInfo:
    """One track of an MKV container, as reported by ``mkvmerge -J``.

    Attributes:
        id: Track id used by mkvextract specs.
        type: Track type reported by mkvmerge (``video``/``audio``/``subtitles``).
        codec_id: Matroska codec id (e.g. ``S_TEXT/ASS``).
        language: ISO 639 language tag (may be empty).
        language_ietf: IETF language tag (may be empty).
        name: Track display name (may be empty).
        default: Container default-track flag.
        num_entries: Index-entry count (line-count proxy), when reported.
    """

    id: int
    type: str
    codec_id: str
    language: str
    language_ietf: str
    name: str
    default: bool
    num_entries: int | None


@dataclass(frozen=True, slots=True)
class MediaInfo:
    """Identified MKV container.

    Attributes:
        path: The container file.
        tracks: All tracks in mkvmerge order, sorted by id.
    """

    path: Path
    tracks: tuple[TrackInfo, ...]


@dataclass(frozen=True, slots=True)
class TrackSelection:
    """The audio and subtitle track chosen for the pipeline.

    Attributes:
        audio_id: Chosen audio track id, or None when the file has no audio.
        subtitle_id: Chosen subtitle track id, or None when none is usable.
        already_polish: Whether the chosen subtitle track is already Polish.
    """

    audio_id: int | None
    subtitle_id: int | None
    already_polish: bool


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Paths produced by one extraction run.

    Attributes:
        audio_path: Extracted audio file, or None when no audio was requested.
        subtitle_path: Extracted subtitle file, or None when none was requested.
    """

    audio_path: Path | None
    subtitle_path: Path | None
```

`type` w `TrackInfo` celowo jest `str`, nie `Literal` — mkvmerge może raportować typy spoza trójki (`buttons`); zamknięty `Literal` wybuchłby na egzotycznym pliku zamiast go zignorować.

### 10.3 `tracks.py` — port `track_selector.py` 1:1 + typowany wrapper

Struktura pliku: (1) docstring modułu, (2) sekcja portu **verbatim**, (3) typowany wrapper na końcu. Port kopiuje z `../mm_avh_working_space/modules/track_selector.py` **cały** zestaw: stałe (`_SUB_LANG_WEIGHT:33`, `_SUB_LANG_DEFAULT:41`, `_AUDIO_LANG_WEIGHT:44`, `_AUDIO_LANG_DEFAULT:56`, `_SIGNS_PENALTY:60`, `_DEFAULT_BONUS:68`, `_LINES_DIVISOR:71`, `_RE_SIGNS:78`), helpery (`_track_name:81`, `_track_language:103`, `_track_default:125`, `_is_signs_only:144`, `_lines_bonus:149`), funkcje score/select (`score_subtitle_track:172`, `score_audio_track:192`, `select_subtitle_track:211`, `select_audio_track:231`). Plik źródłowy jest już w stylu docelowym (Final z docstringami, `from __future__`), więc port to kopia z **dokładnie tymi** odchyleniami (wymusza mypy strict; zachowanie identyczne — regresja §14.6 pilnuje):

1. Adnotacje `dict` → `dict[str, Any]` (import `Any` z `typing`); `list[dict]` → `list[dict[str, Any]]`; analogicznie `Sequence` w nowym wrapperze.
2. `_track_name` i `_track_language`: wynik łańcucha `or` do zmiennej, return przez `str(...)` (Any → str pod `warn_return_any`):
   ```python
   value = track.get("language") or track.get("lang") or track.get("properties", {}).get("language") or ""
   return str(value).lower()
   ```
3. `_lines_bonus`: `return float(lines) / _LINES_DIVISOR`.
4. `select_subtitle_track` / `select_audio_track`: `return int(best["id"])`.
5. Docstring modułu przepisany pod AniShift (mówi CO robi, bez historii „Pillar 2 of MM_AVH" i bez deklarowanych procentów — reguła: docstringi bez historii decyzji).
6. Klucz sortowania `-t["id"]` → `-int(t["id"])` w obu `max(...)` (mypy).

Wrapper (na końcu pliku, sekcja `# ── Typed wrapper ──`):

```python
_POLISH_LANGS: Final[frozenset[str]] = frozenset({"pol", "pl"})
"""Subtitle language tags meaning the track is already Polish."""


def _selector_shape(track: TrackInfo) -> dict[str, Any]:
    """Return the flat dict shape the ported selector functions accept."""
    return {
        "id": track.id,
        "type": track.type,
        "language": track.language,
        "name": track.name,
        "default": track.default,
        "num_lines": track.num_entries,
    }


def select_tracks(tracks: Sequence[TrackInfo]) -> TrackSelection:
    """Pick the audio and subtitle track for the pipeline, by metadata alone.

    Only text subtitle tracks are offered to the selector; picture formats
    (PGS, VobSub) cannot be voiced, so a text track always wins over them.

    Args:
        tracks: All tracks of the container.

    Returns:
        The chosen track ids plus the already-Polish flag of the subtitle.
    """
    audio_shaped = [_selector_shape(t) for t in tracks if t.type == "audio"]
    text_shaped = [
        _selector_shape(t)
        for t in tracks
        if t.type == "subtitles" and is_text_subtitle_codec(t.codec_id)
    ]
    audio_id = select_audio_track(audio_shaped)
    subtitle_id = select_subtitle_track(text_shaped)
    subtitle = next((track for track in tracks if track.id == subtitle_id), None)
    already_polish = subtitle is not None and subtitle.language.lower() in _POLISH_LANGS
    return TrackSelection(audio_id=audio_id, subtitle_id=subtitle_id, already_polish=already_polish)
```

Płaski kształt (`language`/`name`/`default`/`num_lines`) jest **wprost obsługiwany** przez łańcuchy fallbacków helperów portu (`_track_language:117-122`, `_track_name:95-100`, `_track_default:137-141`, `_lines_bonus:162-169`) — zweryfikowane w źródle; to ten sam kształt co dataset testowy mm_avh. Flaga `already_polish` odtwarza `mkvtoolnix.py:398` (`sub_lang in ('pol','pl')`).

**KOREKTA WIĄŻĄCA — filtr kodeka PRZED selektorem (nie po).** Zweryfikowane w źródle: `select_subtitle_track` (`track_selector.py:211-229`) filtruje **wyłącznie** po `type == "subtitles"` — kodeka nie czyta w ogóle (zero wzmianek o `codec` w całym pliku). Bez filtra na wejściu selektor mógłby wybrać ścieżkę obrazkową, którą runner potem odrzuca (§12 krok 4) → **plik kończy bez napisów, choć ścieżka tekstowa leżała obok**. Realny przypadek: rip z BluRaya z PGS `pol` (100 pkt) + fansubowym ASS `eng` (50 pkt) — PGS wygrywa punktami i zostaje odrzucony, ASS przepada.

Filtrujemy **wejście**, nie logikę: port `track_selector.py` zostaje **1:1** (R4, regresja na 206 wpisach `dataset.json` nietknięta — ona podaje same ścieżki tekstowe, patrz §14.6). `_selector_shape` na `audio`/`subtitles` osobno jest zresztą wierniejsze niż mm_avh, który przekazywał całą listę i polegał na wewnętrznym filtrze po typie.

**Skutek dla §12 krok 4:** filtr w runnerze **zostaje** jako druga linia obrony (kontener bez ani jednej ścieżki tekstowej → `subtitle_id is None` → warning „no text subtitle track — skipping subtitles"), ale zmienia się jego komunikat: nie „wybrana ścieżka nie jest tekstowa" (to już niemożliwe), tylko „brak ścieżki tekstowej w pliku".

**Pomiar (dlaczego to nie jest teoretyzowanie i dlaczego nie jest pilne):** na całym materiale usera występują **wyłącznie** dwa kodeki napisów — `SubStationAlpha` 732× i `SubRip/SRT` 587× (206 MKV z `dataset.json`), a w 5 plikach roboczych (`workspace/` + `bugs/`) sam `S_TEXT/ASS`. Zero PGS/VobSub. Ryzyko nie występuje w dzisiejszym materiale — ale kosztuje dwie linijki i eliminuje całą klasę cichej awarii, więc wchodzi teraz.

**Test (§14.2, dopisać):** `test_select_tracks_prefers_text_over_picture` — kontener z `S_HDMV/PGS` `lang=pol` (id 2) i `S_TEXT/ASS` `lang=eng` (id 3) → `subtitle_id == 3`, `already_polish is False`. Bez filtra ten test daje `2` — to jest jego cały sens.

**KOREKTA WIĄŻĄCA — miejsce mapy kodeków.** Powyższa zmiana wymaga `is_text_subtitle_codec` w `tracks.py`, a §10.4 umieszcza ją w `service.py` — to dałoby import `tracks → service`, przy czym `service` woła `select_tracks` z `tracks`: **cykl importów**.

Rozwiązanie: `_CODEC_EXTENSION`, `_FALLBACK_EXTENSION`, `_TEXT_SUBTITLE_EXTENSIONS`, `format_extension()` i `is_text_subtitle_codec()` przenoszą się z §10.4 (`service.py`) do **§10.2 (`types.py`)**. Uzasadnienie: to czyste dane + dwie czyste funkcje bez I/O — dokładnie to, czym jest `types.py` w tej domenie. `service.py` importuje `format_extension` z `types` (nazwa pliku wyjściowego), `tracks.py` importuje `is_text_subtitle_codec` z `types`. Graf pozostaje acykliczny i zgodny z §9.2: `types` (liść) ← `tracks` ← `service`. Re-eksport w `__init__.py` (§10.5) bez zmian — obie funkcje nadal w publicznym API domeny.

### 10.4 `service.py` — identify + ekstrakcja

Sekcja stałych:

> ⚠️ **Stałe i funkcje kodeków przeniesione do §10.2 (`types.py`)** — patrz korekta w §10.3 (cykl importów `tracks → service`). Poniższy blok pozostaje jako specyfikacja ich treści; miejscem docelowym jest `types.py`, a `service.py` importuje z niego `format_extension`.

```python
_CODEC_EXTENSION: Final[dict[str, str]] = { ... }
"""Matroska codec id to output file extension (ported table)."""

_FALLBACK_EXTENSION: Final[str] = "mkv"
"""Extension for codec ids absent from the table."""

_TEXT_SUBTITLE_EXTENSIONS: Final[frozenset[str]] = frozenset({"ass", "srt", "ssa"})
"""Subtitle extensions stage 3 can actually process (R2)."""

_RE_GUI_PROGRESS: Final[re.Pattern[str]] = re.compile(r"^#GUI#progress\s+(\d+)%")
"""One ``--gui-mode`` progress line of mkvextract."""

_IDENTIFY_TIMEOUT_S: Final[float] = 120.0
"""Upper bound for ``mkvmerge -J`` on one file."""

_ERROR_TAIL_LINES: Final[int] = 8
"""How many trailing non-progress output lines land in an error message."""

_AUDIO_STEM: Final[str] = "audio"
"""Base name of the extracted audio file inside the per-file tmp dir."""

_SUBS_STEM: Final[str] = "subs"
"""Base name of the extracted subtitle file inside the per-file tmp dir."""
```

`_CODEC_EXTENSION` = pełna mapa z `mkvtoolnix.py:434-475` przepisana 1:1 (43 wpisy, od `A_AAC/MPEG2/*` po `V_VP9`). To dane, nie logika — port w całości, mimo że ścieżki obrazkowe (`S_HDMV/PGS` → `sup` itd.) nie mają handlera: mapa służy też do nazwania pliku przy przyszłych rozszerzeniach, a `_TEXT_SUBTITLE_EXTENSIONS` odcina nieobsługiwane formaty na poziomie decyzji (patrz `is_text_subtitle_codec` niżej i §12 krok 4).

Funkcje:

```python
def format_extension(codec_id: str) -> str:
    """Return the output file extension for a Matroska codec id."""
    return _CODEC_EXTENSION.get(codec_id, _FALLBACK_EXTENSION)


def is_text_subtitle_codec(codec_id: str) -> bool:
    """Tell whether a subtitle codec is a text format stage 3 can process."""
    return format_extension(codec_id) in _TEXT_SUBTITLE_EXTENSIONS


def parse_media_info(path: Path, payload: str) -> MediaInfo:
    """Parse ``mkvmerge -J`` JSON output into a typed :class:`MediaInfo`.

    Args:
        path: The container the payload describes.
        payload: Raw stdout of ``mkvmerge -J``.

    Returns:
        The typed container description, tracks sorted by id.

    Raises:
        ExtractionError: When the payload is not valid identify JSON.
    """


def identify(path: Path) -> MediaInfo:
    """Identify an MKV container with ``mkvmerge -J``.

    Args:
        path: The MKV file to identify.

    Returns:
        The typed container description.

    Raises:
        ExtractionError: When mkvmerge fails, times out or emits bad JSON.
        InstallerError: When the mkvmerge binary must be and cannot be installed.
        BinaryNotFoundError: When mkvmerge cannot be provided at all.
    """


def extract_tracks(
    info: MediaInfo,
    selection: TrackSelection,
    dest_dir: Path,
    *,
    on_progress: Callable[[int], None] | None = None,
    cancel: threading.Event | None = None,
) -> ExtractionResult:
    """Extract the selected tracks into *dest_dir* with live progress.

    Runs a single ``mkvextract --gui-mode`` process covering both tracks and
    reports its ``#GUI#progress N%`` lines through *on_progress*. Validates
    that every requested output file exists and is non-empty afterwards.

    Args:
        info: The identified container.
        selection: Which tracks to extract (either id may be None).
        dest_dir: Existing directory the output files are written into.
        on_progress: Called with the current percent (0-100) on every update.
        cancel: When set, the process is terminated and partial files removed.

    Returns:
        Paths of the extracted files (None for tracks not requested).

    Raises:
        ExtractionError: On non-zero exit, missing/empty output, bad track id,
            or cancellation (``ErrorCode.CANCELLED``).
    """
```

Implementacja — decyzje wiążące:

- **`identify`**: `exe = ensure_binary(Binary.MKVMERGE)` (fast path bez sieci, `installer.py:388-394`); `subprocess.run([str(exe), "--ui-language", "en", "-J", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=_IDENTIFY_TIMEOUT_S, check=False)` z `# noqa: S603` (I8). `--ui-language en` jak w mm_avh (`mkvtoolnix.py:126`) — komunikaty błędów po angielsku, JSON i tak jest neutralny. `returncode != 0` → `ExtractionError(EXTRACTION_FAILED)` z `stderr` w message i `details={"file": str(path)}`; `subprocess.TimeoutExpired` → osobny `except` → `ExtractionError(TIMEOUT... )` — użyć `ErrorCode.TIMEOUT`; oba przez fabrykę `_fail(code, message, suggestion)` lokalną w module (wzorzec A stan-repo 4.2, rozszerzony o parametr `code`).
- **`parse_media_info`**: `json.loads` → `KeyError`/`ValueError`/`TypeError` w osobnych blokach `except` → `ExtractionError(EXTRACTION_FAILED)`. Z `tracks[]` czyta per track: `id`, `type`, `properties.codec_id` (default `""`), `properties.language` (`""`), `properties.language_ietf` (`""`), `properties.track_name` (`""`), `properties.default_track` (False), `properties.num_index_entries` (None). Sort po `id` (jak `mkvtoolnix.py:150`). Sprawdza `container.recognized` i `container.supported` — którekolwiek False → `ExtractionError` („not a supported Matroska file").
- **`extract_tracks`**: buduje listę spec: `(selection.audio_id, dest_dir / f"{_AUDIO_STEM}.{ext}")` i analogicznie subs; `ext = format_extension(codec_id)` ścieżki znalezionej po id w `info.tracks` — id nieobecne w `info.tracks` → `ExtractionError(TRACK_NOT_FOUND)`. Puste spec (oba None) → `ExtractionResult(None, None)` bez odpalania procesu. Komenda: `[str(exe), "--ui-language", "en", "--gui-mode", str(info.path), "tracks", *[f"{tid}:{dest}" for ...]]` — **składnia „source przed mode"** wg synopsis zwendorowanego `mkvextract.html`; weryfikowana ręcznie w kroku 5 §15 (jeśli przypięta wersja jej nie przyjmie, jedyną dozwoloną korektą jest przestawienie na `[exe, "--gui-mode", "tracks", source, *specs]` — porządek argumentów to fakt binarki, nie decyzja projektowa).
- Proces: `Popen(cmd, stdout=PIPE, stderr=STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)` z `# noqa: S603`. `stderr=STDOUT` — jeden strumień, zero ryzyka deadlocku na pełnym buforze stderr. Pętla `for line in process.stdout:` — `--gui-mode` daje postęp **linia po linii** (zweryfikowane na 2 plikach; ~30 linii obejścia `read(1)` z `mkvtoolnix.py:299-331` **znika**, NIE portować). Każda iteracja: (1) `cancel.is_set()` → `process.terminate()`, `process.wait()`, skasować częściowe pliki wyjściowe (`dest.unlink(missing_ok=True)` dla każdego spec), `raise` `ExtractionError(CANCELLED)`; (2) match `_RE_GUI_PROGRESS` → `on_progress(min(100, int(...)))`; (3) linia nie-progress → do `collections.deque(maxlen=_ERROR_TAIL_LINES)` (materiał na komunikat błędu).
- Po pętli `process.wait()`; `returncode != 0` → `ExtractionError(EXTRACTION_FAILED)`: message z nazwą pliku i ogonem outputu, `suggestion="Check the MKV is readable and the disk has free space"`, `details={"command": ..., "tail": ...}` — to jest R13 („jasny komunikat co i gdzie").
- **N4**: po sukcesie, dla każdego spec: `dest.is_file() and dest.stat().st_size > 0`, inaczej `ExtractionError(EXTRACTION_FAILED)` z message wprost nazywającym znaną przypadłość („mkvextract exited 0 but wrote no data") i `details={"output": str(dest)}`. Na końcu `on_progress(100)` (gdy callback podany).
- `OSError` przy operacjach na plikach → osobny `except OSError` → `ExtractionError(IO_ERROR)` (E17). **Osobne bloki except** (bug ruff-format).

### 10.5 `__init__.py`

Re-eksport publicznego API: `ExtractionError`, `ExtractionResult`, `MediaInfo`, `TrackInfo`, `TrackSelection`, `extract_tracks`, `format_extension`, `identify`, `is_text_subtitle_codec`, `parse_media_info`, `select_tracks` — `__all__` posortowane.

## 11. `anishift/services/subtitles/` — plik po pliku

### 11.1 `errors.py`

```python
"""Subtitles domain errors."""

from __future__ import annotations

from anishift.errors import FatalError

__all__ = ["SubtitleError"]


class SubtitleError(FatalError):
    """Raised when loading, splitting or writing subtitles fails."""
```

Kod: `SUBTITLE_PARSE_FAILED` (istnieje, `errors.py:59`) + generyczny `IO_ERROR` przy zapisie.

### 11.2 `types.py`

```python
"""Subtitles domain value objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pysubs2 import SSAFile

    from anishift.services.subtitles.classifier import StyleVerdict

__all__ = ["Decision", "SpokenLine", "SplitStats", "SubtitleKind", "SubtitleSplit"]

Decision = Literal["spoken", "displayed"]
"""Per-line fate: read by the narrator or kept on screen."""

SubtitleKind = Literal["ass", "srt"]
"""Working format of a subtitle file (SSA is loaded and written as ASS)."""


@dataclass(frozen=True, slots=True)
class SpokenLine:
    """One line of narrator input, tags stripped, FBF runs collapsed.

    Attributes:
        start: Start time in milliseconds (minimum of a collapsed run).
        end: End time in milliseconds (maximum of a collapsed run).
        text: Visible text without ASS/HTML tags, single line.
        style: Source ASS style name (empty for SRT and TXT input).
    """

    start: int
    end: int
    text: str
    style: str


@dataclass(frozen=True, slots=True)
class SplitStats:
    """Split counters for reports and measurements.

    Attributes:
        total_events: Dialogue events in the source.
        spoken_events: Source events marked spoken (before collapsing).
        spoken_lines: Narrator lines after FBF collapsing.
        displayed_events: Source events kept for the displayed product.
        drawing_events: Events sieved out as vector drawings.
        collapsed_away: Spoken events removed by FBF collapsing.
    """

    total_events: int
    spoken_events: int
    spoken_lines: int
    displayed_events: int
    drawing_events: int
    collapsed_away: int


@dataclass(slots=True)
class SubtitleSplit:
    """Complete result of splitting one subtitle file.

    ``decisions`` is index-aligned with the source's Dialogue events in file
    order (the same filter ``event.type == "Dialogue"`` everywhere).

    Attributes:
        kind: Working format of the source.
        subs: The loaded source file, never mutated.
        decisions: Per-Dialogue-event fate, aligned with the source order.
        verdicts: Style-level classifier verdicts (empty for SRT input).
        spoken: Narrator lines, sorted by start time.
        stats: Split counters.
    """

    kind: SubtitleKind
    subs: SSAFile
    decisions: tuple[Decision, ...]
    verdicts: tuple[StyleVerdict, ...]
    spoken: tuple[SpokenLine, ...]
    stats: SplitStats
```

### 11.3 `classifier.py` — port `style_classifier.py` 1:1

Kopiowane z `../mm_avh_working_space/modules/style_classifier.py` w całości: stałe regeksowe (`_BACKSLASH:37`, `_RE_DRAW:38`, `_RE_POS:39`, `_RE_KARA:42`, `_RE_PUNCT:43`, `_RE_SONG:46`, `_RE_NOTE:49`, `_RE_SIGN:52`, `_RE_DLG:55`), progi (`_DEDUP_MIN_REPEAT:60` … `_SCORE_SIGN:79`), `Category:83`, `StyleVerdict:96`, `_StyleMetrics:115`, `dedup_animation:138`, `_classify_metrics:171`, `classify_styles:224`. **ZERO strojenia** — żadna wartość, żaden regex, żaden próg nie zmienia się. Dozwolone odchylenia (kompletna lista):

1. **I5** — literały porównań w `_classify_metrics` → stałe w sekcji Constants (wartości identyczne):
   ```python
   _FRAC_DIALOG_MIN: Final[float] = 0.20
   """File-share ratio at or above which a style earns the share score."""

   _POS_LOW_MAX: Final[float] = 0.40
   """Positioning ratio below which a style earns the low-positioning score."""

   _PUNCT_MIN: Final[float] = 0.30
   """Punctuation ratio above which a style earns the punctuation score."""

   _AVG_TEXT_MIN: Final[int] = 12
   """Average plain-text length at or above which a style earns the length score."""

   _POS_HIGH_MIN: Final[float] = 0.60
   """Positioning ratio above which a style is penalised as typesetting."""
   ```
   i podmiana w ciele: `if frac >= _FRAC_DIALOG_MIN:` itd. (5 porównań: `:202,204,206,208,214`). Wagi `+= 0.35/0.25/0.20/0.10/0.15`, `-= 0.25/0.30` oraz confidence `0.95/0.9/0.85/0.5` — **bez zmian, inline** (nie są porównaniami, PLR2004 ich nie dotyczy).
2. Docstring modułu przepisany: opisuje mechanikę (dedup animacji, metryki, kategorie), **bez** liczb walidacji („~99% agreement" ze źródła to nieaktualna historia — zmierzono 95.86%; docstringi nie niosą historii ani metryk).
3. `select_dialog_styles` (`:277-294`) — **NIE portować**: to polityka mm_avh (UNCERTAIN → czytaj), którą D3(b) odwraca; polityka mieszka w `service.py`. Martwy kod nie wjeżdża.
4. Trick `chr(92)` — **zostaje** (przeżywa py314 bez ostrzeżeń o escape'ach; identyczne skompilowane wzorce).
5. mypy strict: `metrics.items()` sort key `lambda kv: -kv[1].n` — typy się domykają (dataclass), zmiany niepotrzebne; jeśli mypy zgłosi cokolwiek, dozwolona wyłącznie adnotacja, nigdy zmiana zachowania.

### 11.4 `text.py` — operacje na tekście eventu

```python
"""Tag-safe text operations on ASS/SRT event text."""

from __future__ import annotations

import re
from typing import Final

__all__ = ["is_drawing", "replace_visible_text", "visible_text"]

# ── Constants ────────────────────────────────────────────────────────────────

_RE_TAG_BLOCK: Final[re.Pattern[str]] = re.compile(r"\{[^}]*\}")
"""One ASS override-tag block, ``{...}``."""

_RE_DRAW_TAG: Final[re.Pattern[str]] = re.compile(chr(92) + chr(92) + r"p[1-9]")
"""An ASS ``\\p1``-``\\p9`` tag switching the line into vector-drawing mode."""

_RE_HTML_TAG: Final[re.Pattern[str]] = re.compile(r"<[^>]+>")
"""One HTML-style formatting tag as found in SRT text."""

_RE_SOFT_BREAKS: Final[re.Pattern[str]] = re.compile(r"\\[Nnh]")
"""ASS line-break and hard-space escapes, normalised to a space."""

_RE_SPACES: Final[re.Pattern[str]] = re.compile(r"\s+")
"""Any whitespace run, collapsed to a single space."""


def is_drawing(text: str) -> bool:
    """Tell whether an event's raw text is a vector drawing (R6a)."""
    return bool(_RE_DRAW_TAG.search(text))


def visible_text(text: str) -> str:
    """Return the human-visible text of an event as a single line.

    Removes ``{...}`` override blocks and HTML-style tags, normalises ASS
    break escapes and whitespace runs to single spaces, and strips the ends.
    """
    without_tags = _RE_TAG_BLOCK.sub("", text)
    without_html = _RE_HTML_TAG.sub("", without_tags)
    normalised = _RE_SOFT_BREAKS.sub(" ", without_html)
    return _RE_SPACES.sub(" ", normalised).strip()


def replace_visible_text(text: str, new_text: str) -> str:
    """Replace the visible text of an event, keeping every tag block intact.

    The first visible segment is replaced by *new_text*; any further visible
    segments are dropped; all ``{...}`` blocks stay in their original order.

    Args:
        text: Raw event text, possibly containing ``{...}`` blocks.
        new_text: Replacement for the visible part.

    Returns:
        The rebuilt event text with an unchanged tag-block sequence.
    """
    parts: list[str] = []
    inserted = False
    last = 0
    for match in _RE_TAG_BLOCK.finditer(text):
        if not inserted and match.start() > last:
            parts.append(new_text)
            inserted = True
        parts.append(match.group(0))
        last = match.end()
    if not inserted:
        parts.append(new_text)
    return "".join(parts)
```

To jest zweryfikowany wzór z pomiaru („`re.compile(r"\{[^}]*\}")` + finditer + podmiana fragmentów między dopasowaniami"). **PUŁAPKA, której ten moduł jest zaporą:** `event.plaintext = "..."` KASUJE TAGI (zmierzone 2169→297) — w całym etapie 3 (i w przyszłych) **nigdzie nie wolno przypisywać do `event.plaintext`**; zapis tekstu wyłącznie przez `replace_visible_text` na `event.text`. Getter `event.plaintext` jest bezpieczny i klasyfikator (port) z niego korzysta — nie ujednolicać na siłę (port as-is). `replace_visible_text` w etapie 3 nie ma jeszcze konsumenta produkcyjnego (podmiana tekstu to etap 4) — wchodzi teraz, bo to zmierzony, ryzykowny fundament R8 i musi dostać testy zanim ktokolwiek go użyje.

### 11.5 `service.py` — split

Stałe:

```python
_FBF_MAX_GAP_MS: Final[int] = 500
"""Maximum gap between consecutive identical events merged as one FBF run."""

_SAMPLES_PER_STYLE: Final[int] = 3
"""How many sample lines the style preview collects per style."""

_SAMPLE_MAX_CHARS: Final[int] = 60
"""Sample line length cap in the style preview."""

_SUFFIX_KIND: Final[dict[str, SubtitleKind]] = {".ass": "ass", ".ssa": "ass", ".srt": "srt"}
"""File suffix to working format (R2: only these are supported)."""

_ENCODING: Final[str] = "utf-8"
"""The only subtitle encoding stage 3 reads and writes."""
```

Wartość `_FBF_MAX_GAP_MS = 500` to punkt startowy; **arbitrem jest test DoD** „Fuji `[Znaki]` 1381 → 18" (§14.4). Jeśli test da inną liczbę, jedyną dozwoloną zmianą jest ta stała (procedura: zmierzyć na pliku Fuji rozkład odstępów `next.start - prev.end` w grupach o identycznym tekście i ustawić najmniejszą wartość, przy której wychodzi 18; wynik wpisać do stałej i do PR). To nie jest strojenie klasyfikatora — to kalibracja naszego, nowego filtra względem zmierzonego wzorca.

Funkcje:

```python
def subtitle_kind(path: Path) -> SubtitleKind | None:
    """Return the working format for a file suffix, or None when unsupported."""
    return _SUFFIX_KIND.get(path.suffix.lower())


def load_subtitles(path: Path) -> SSAFile:
    """Load a subtitle file in UTF-8.

    Raises:
        SubtitleError: When the file is missing, unreadable or unparsable
            (``ErrorCode.SUBTITLE_PARSE_FAILED``).
    """


def preview_styles(subs: SSAFile) -> tuple[tuple[StyleVerdict, ...], dict[str, tuple[str, ...]]]:
    """Classify styles and collect sample lines for the manual prompt.

    Args:
        subs: The loaded subtitle file.

    Returns:
        The verdicts (classifier order) and, per style, up to
        ``_SAMPLES_PER_STYLE`` visible-text samples of non-drawing lines,
        each capped at ``_SAMPLE_MAX_CHARS`` characters.
    """


def collapse_fbf(events: Sequence[SSAEvent]) -> tuple[tuple[SpokenLine, ...], int]:
    """Collapse frame-by-frame runs of identical text into single lines (R6b).

    Events are grouped by ``(style, visible text)``; inside a group, sorted by
    start, consecutive events whose gap does not exceed ``_FBF_MAX_GAP_MS``
    form one run emitted as a single line with ``start=min`` and ``end=max``.
    Distant repeats stay separate lines. Events with empty visible text are
    dropped entirely.

    Args:
        events: The events marked spoken, in any order.

    Returns:
        The collapsed lines sorted by start time, and how many events were
        removed by collapsing.
    """


def split_subtitles(
    subs: SSAFile,
    *,
    kind: SubtitleKind,
    spoken_styles: Collection[str] | None = None,
    verdicts: Sequence[StyleVerdict] | None = None,
) -> SubtitleSplit:
    """Mark every Dialogue line spoken or displayed and build the spoken stream.

    ASS flow: drawings go to displayed (R6a); remaining lines follow their
    style's verdict — DIALOG means spoken, SIGN and UNCERTAIN mean displayed;
    when nothing ends up spoken, every non-drawing line becomes spoken (E12).
    SRT flow: every line is spoken. The source ``subs`` is never mutated.

    Args:
        subs: The loaded subtitle file.
        kind: Working format of the source.
        spoken_styles: Manual override — exactly these styles are spoken
            (drawings still go to displayed). None means classifier policy.
        verdicts: Pre-computed verdicts (avoids re-classifying after a
            preview). None means classify here.

    Returns:
        The full split result.
    """


def write_displayed(split: SubtitleSplit, dest: Path) -> Path | None:
    """Write the displayed product file, byte-deterministic and atomic.

    Copies the source info and every style, keeps all non-Dialogue events and
    the displayed Dialogue events in original order, and writes UTF-8 via a
    temporary file replaced into place. No file is written when there are no
    displayed Dialogue events.

    Args:
        split: The split to serialise.
        dest: Target path (``<stem>.displayed.<kind>``).

    Returns:
        The written path, or None when there was nothing to display.

    Raises:
        SubtitleError: On write failure (``ErrorCode.IO_ERROR``).
    """
```

Decyzje implementacyjne wiążące:

- **Filtr eventów** wszędzie identyczny: `dialogue = [e for e in subs.events if e.type == "Dialogue"]` (jak `classify_styles:236`). `decisions` jest krotką wyrównaną z tą listą — to niezmiennik zapisany w docstringu `SubtitleSplit`.
- **Kolejność decyzji ASS** (I2): (1) `is_drawing(e.text)` → `displayed` (+licznik `drawing_events`); (2) styl w zbiorze spoken → `spoken`, inaczej `displayed`. Zbiór spoken: z `spoken_styles` (manual) albo `{v.style for v in verdicts if v.category is Category.DIALOG}` (D3b: UNCERTAIN nie wchodzi). (3) Fallback E11/E12: jeśli po kroku 2 `spoken_events == 0` i istnieje ≥1 event nie-rysunkowy → wszystkie nie-rysunkowe przełączyć na `spoken` (rysunki nigdy — TTS czytałby współrzędne). Zero eventów Dialogue → pusty wynik (runner zamienia w warning „no dialogue events", plik idzie dalej bez produktu).
- **`collapse_fbf`** implementacja: `defaultdict` po kluczu `(event.style, visible_text(event.text))`; klucz z pustym tekstem → pomiń (nic do czytania); w grupie sort po `start`; skan liniowy budujący runy: nowy run gdy `event.start - current_end > _FBF_MAX_GAP_MS` (overlap i przyleganie → ten sam run; `current_end = max(current_end, event.end)`); run → `SpokenLine(start=run_min_start, end=run_max_end, text=key_text, style=key_style)`; `collapsed_away += len(run) - 1`. Wynik posortowany po `(start, end, style)` — pełny, deterministyczny porządek (N2). Świadomy kompromis (zapisany, nieusuwalny): dwa identyczne dialogowe eventy w odstępie < 500 ms scalą się w jedno odczytanie — akceptowalne, bo szybkie duble („Matte! Matte!") czytane raz brzmią naturalniej niż dwa razy, a FBF-y są bezpieczne w komplecie.
- **`preview_styles`**: woła `classify_styles(subs)` raz; próbki — pierwsze `_SAMPLES_PER_STYLE` nie-rysunkowych eventów każdego stylu w kolejności pliku, **bez duplikatów tekstu** (FBF dałby 3× to samo — zbierać do `dict.fromkeys`-podobnego zbioru zachowującego kolejność), każda przycięta do `_SAMPLE_MAX_CHARS` z `…` na końcu gdy ucięta.
- **`write_displayed`**: nowy `SSAFile()`; `out.info = dict(split.subs.info)`; `out.styles = {name: style.copy() for ...}` — pysubs2 `SSAStyle.copy()`; events: przejść `split.subs.events` w oryginalnej kolejności, wziąć te nie-Dialogue (komentarze zostają — wierność) oraz Dialogue z decyzją `displayed` (licznik po indeksie Dialogue). Serializacja: `out.to_string(format_=split.kind)`; zapis: `dest.with_name(dest.name + ".tmp")` → `write_text(..., encoding=_ENCODING)` → `Path.replace(dest)` (wzorzec atomowy z `user_settings.py:148`). Eventy displayed **współdzielone referencją** ze źródłem — wolno, bo nic ich nie mutuje (niezmiennik: cały moduł nie przypisuje do pól eventów).
- **`load_subtitles`**: `pysubs2.load(str(path), encoding=_ENCODING)`; osobne bloki `except` na: `FileNotFoundError`, `UnicodeDecodeError`, `OSError`, `pysubs2.exceptions.Pysubs2Error` (klasa bazowa formatów pysubs2) — każdy mapowany na `SubtitleError(SUBTITLE_PARSE_FAILED)` z sugestią i `from exc`. **Nie** `except Exception` (BLE001).

### 11.6 SRT — przebieg

`split_subtitles(..., kind="srt")`: wszystkie eventy Dialogue → `spoken`; `verdicts = ()`; spoken przez ten sam `collapse_fbf` (dla SRT grupy 1-elementowe — no-op poza sortem; jeden code path, zero rozgałęzień); `style` w `SpokenLine` = `event.style` (pysubs2 nada `"Default"` — akceptowalne). `displayed_events == 0` → `write_displayed` zwraca None → produkt nie powstaje (D4, §8.4). pysubs2 czyta SRT z tagami HTML (`<i>`) — `visible_text` je zdejmuje (`_RE_HTML_TAG`), a `{\an8}` zdejmuje `_RE_TAG_BLOCK` — pokrywa czyszczenie z `move_srt` (`subtitle.py:337`) bez mutowania źródła.

### 11.7 `txt.py` — TXT → spoken (R12, I6)

```python
_MAX_CHUNK_CHARS: Final[int] = 750
"""Longest narrator line built from plain text (matches the mm_avh call site)."""

_RE_SENTENCE_END: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?…])\s+")
"""Split point between sentences: end punctuation followed by whitespace."""


def txt_to_spoken(path: Path, *, max_chars: int = _MAX_CHUNK_CHARS) -> tuple[SpokenLine, ...]:
    """Convert a plain-text file into narrator lines (audiobook side quest).

    Reads UTF-8 text, collapses all whitespace, splits into sentences and
    greedily packs them into chunks of at most *max_chars* characters; a
    single sentence longer than the limit is split on word boundaries. Every
    line carries zero timings — the TTS stage paces plain-text input itself.

    Args:
        path: The ``.txt`` file.
        max_chars: Upper bound for one narrator line.

    Returns:
        The narrator lines in text order.

    Raises:
        SubtitleError: When the file cannot be read or decoded.
    """
```

Implementacja: `path.read_text(encoding="utf-8")` (błędy jak w `load_subtitles`, osobne excepty); normalizacja własną stałą `_RE_SPACES` (wzorzec `r"\s+"`; duplikat 2 linii zamiast importu prywatnej stałej z `text.py`); split zdaniowy; pakowanie zachłanne; zdanie > limit → `str.split()` na słowa i pakowanie słów (słowo dłuższe niż limit idzie w całości — nie tniemy słów w środku). Pełny kod: Aneks D.6. `SpokenLine(start=0, end=0, text=chunk, style="")`. Limit 750 = wartość z jedynego call-site'u mm_avh (`start.py:289-291`). Stary parametr `chunk_limit=250`/`split_method` — nie portowany: dwustopniowe cięcie było obejściem bugów chunkera, które tu nie istnieją.

### 11.8 `__init__.py`

Re-eksport: `Category`, `Decision`, `SpokenLine`, `SplitStats`, `StyleVerdict`, `SubtitleError`, `SubtitleKind`, `SubtitleSplit`, `classify_styles`, `collapse_fbf`, `is_drawing`, `load_subtitles`, `preview_styles`, `replace_visible_text`, `split_subtitles`, `subtitle_kind`, `txt_to_spoken`, `visible_text`, `write_displayed` — `__all__` posortowane.

## 12. `anishift/pipeline/` — types + runner

### 12.1 `types.py`

```python
"""Pipeline value objects and the protocols the runner is driven through."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from anishift.services.extraction.types import MediaInfo, TrackSelection
    from anishift.services.subtitles.classifier import StyleVerdict

__all__ = [
    "FileFailure",
    "FileOutcome",
    "FileStatus",
    "PipelineInteraction",
    "PipelineReport",
    "ProgressReporter",
    "StepName",
]

StepName = Literal["identify", "select", "extract", "split", "write", "txt"]
"""Pipeline step a failure is attributed to."""

FileStatus = Literal["done", "failed", "cancelled"]
"""Final state of one input file after a pipeline run."""


@dataclass(frozen=True, slots=True)
class FileFailure:
    """Why one file failed, ready for rendering (R13).

    Attributes:
        step: The step that failed.
        code: The ``ErrorCode`` value of the mapped domain error.
        message: Human-readable description of what went wrong.
        suggestion: Actionable fix hint (may be empty).
    """

    step: StepName
    code: str
    message: str
    suggestion: str


@dataclass(slots=True)
class FileOutcome:
    """Everything stage 3 produced (or failed to produce) for one input file.

    Attributes:
        source: The input file in the workspace.
        status: Final state of the file.
        audio_path: Extracted audio, when any.
        subtitle_path: Extracted subtitle source of truth, when any.
        displayed_path: The displayed product, when any was written.
        already_polish: Whether the chosen subtitles are already Polish (E4).
        spoken_lines: Narrator lines after collapsing.
        displayed_events: Events kept in the displayed product.
        drawing_events: Events sieved out as drawings.
        collapsed_away: Events removed by FBF collapsing.
        warnings: Non-fatal notes (no subtitles, unsupported codec, ...).
        failure: Failure details when ``status == "failed"``.
    """

    source: Path
    status: FileStatus
    audio_path: Path | None = None
    subtitle_path: Path | None = None
    displayed_path: Path | None = None
    already_polish: bool = False
    spoken_lines: int = 0
    displayed_events: int = 0
    drawing_events: int = 0
    collapsed_away: int = 0
    warnings: tuple[str, ...] = ()
    failure: FileFailure | None = None


@dataclass(frozen=True, slots=True)
class PipelineReport:
    """Outcome of one Enter press: one entry per discovered input file.

    Attributes:
        outcomes: Per-file outcomes in processing (natsorted) order.
    """

    outcomes: tuple[FileOutcome, ...]


class ProgressReporter(Protocol):
    """What the runner needs from a progress display (multi-bar shaped)."""

    def add_task(self, description: str, *, total: int = 100) -> int:
        """Register one bar row and return its id."""
        ...

    def update(self, task_id: int, completed: int) -> None:
        """Set one row's absolute completion."""
        ...


class PipelineInteraction(Protocol):
    """Manual-mode decision points, implemented by the CLI (never by services)."""

    def choose_tracks(self, info: MediaInfo, proposal: TrackSelection) -> TrackSelection:
        """Confirm or override the automatic track selection."""
        ...

    def choose_spoken_styles(
        self,
        source: Path,
        verdicts: Sequence[StyleVerdict],
        samples: Mapping[str, tuple[str, ...]],
    ) -> set[str] | None:
        """Return style names to speak, or None to accept classifier policy."""
        ...
```

`MultiProgressManager` spełnia `ProgressReporter` strukturalnie (`add_task(description, *, total=100) -> TaskID`, `update(task_id, completed)` — `TaskID` to `NewType` na `int`, zwrot `TaskID` tam, gdzie protokół deklaruje `int`, jest poprawny). Zero adapterów.

### 12.2 `runner.py`

Stałe:

```python
_WORKER_CAP: Final[int] = 4
"""Upper bound on parallel file workers (extraction is I/O bound, R10)."""

_WAIT_POLL_SECONDS: Final[float] = 0.2
"""Future-poll interval keeping Ctrl+C responsive on Windows."""

_MKV_SUFFIX: Final[str] = ".mkv"
"""Container suffix discovery picks up."""

_TXT_SUFFIX: Final[str] = ".txt"
"""Plain-text suffix discovery picks up (audiobook side quest, R12)."""

_TMP_DIR_NAME: Final[str] = "tmp"
"""Workspace subdirectory holding per-file working dirs."""

_DISPLAYED_INFIX: Final[str] = ".displayed"
"""Product-name infix: ``<stem>.displayed.<kind>``."""
```

`_WORKER_CAP = 4` to wartość startowa — **finalną ustala pomiar** (§15 krok 12, `scripts/measure_parallel.py`); wynik pomiaru nadpisuje stałą i ląduje w PR (DoD „sufit zmierzony").

Funkcje:

```python
def discover_inputs(root: Path) -> list[Path]:
    """List the workspace's input files, naturally sorted (R1).

    Picks ``*.mkv`` and ``*.txt`` directly in *root* (never in
    subdirectories), skipping ``*.displayed.*`` products. Sorted with
    ``natsort.os_sorted`` for the human episode order.
    """


def run_pipeline(
    context: AppContext,
    *,
    interaction: PipelineInteraction | None = None,
    progress: ProgressReporter | None = None,
) -> PipelineReport:
    """Process every input file in the workspace (one Enter press).

    Ensures the workspace skeleton (N9), discovers inputs, ensures the
    mkvtoolnix binaries once up front, then processes files — in parallel in
    auto mode, strictly sequentially when *interaction* is given. One file's
    failure never stops the others (R13); Ctrl+C cancels cleanly (E14).

    Args:
        context: The wired application context (workspace root).
        interaction: Manual-mode decision points; None means full auto.
        progress: Multi-bar display; None means no progress reporting.

    Returns:
        One outcome per discovered file, in discovery order.

    Raises:
        InstallerError: When the required binaries cannot be provided —
            a global precondition, not a per-file failure.
        BinaryNotFoundError: Same, when no install path exists.
    """


def _worker_count(item_count: int) -> int:
    """Return ``max(1, min(item_count, cpu_count() or 1, _WORKER_CAP))``."""


def _process_mkv(
    mkv: Path,
    workspace_root: Path,
    *,
    interaction: PipelineInteraction | None,
    on_progress: Callable[[int], None] | None,
    cancel: threading.Event,
) -> FileOutcome:
    """Run identify → select → extract → split → write for one MKV."""


def _process_txt(path: Path) -> FileOutcome:
    """Convert one plain-text file into narrator lines (R12)."""
```

Przebieg `run_pipeline` — krok po kroku (wiążące):

1. `ensure_workspace_dir(context.workspace_root)` (`config/workspace.py:96`, idempotentne — N9/E18).
2. `files = discover_inputs(...)`; pusto → `PipelineReport(())` (CLI renderuje komunikat E1 — runner nie drukuje).
3. Jeśli jest ≥1 MKV: `ensure_binary(Binary.MKVMERGE)` i `ensure_binary(Binary.MKVEXTRACT)` **raz, przed workerami** — jedno pobranie zamiast wyścigu N wątków o instalator (E6); błąd propaguje (globalny warunek wstępny — bez binarek każdy plik i tak padnie, więc R13 nie ma tu zastosowania). Pasek pobierania installera (jego własny, jednotaskowy) odpala się PRZED wejściem w `MultiProgressManager` — CLI wywołuje `run_pipeline` już wewnątrz kontekstu multi-paska, więc kolejność musi być: binarki zapewnia **CLI przed** otwarciem paska. KOREKTA WIĄŻĄCA: `ensure_binary` × 2 przenosi się do `cli/pipeline_ui.py` (krok przed `with MultiProgressManager()`); runner **zakłada**, że binarki są, a `identify`/`extract_tracks` i tak wołają `ensure_binary` (fast path, zero I/O) — podwójne wywołanie jest darmowe. Dzięki temu dwa systemy pasków nigdy nie żyją naraz (N8).
4. `cancel = threading.Event()`. Manual (`interaction is not None`) → pętla sekwencyjna po plikach (bez executora, bez progress-tasków). Auto → `ThreadPoolExecutor(max_workers=_worker_count(liczba MKV))`; najpierw dla każdego MKV `task_id = progress.add_task(mkv.name)` (kolejność discovery — paski w porządku naturalnym), potem submit `_process_mkv(..., on_progress=lambda pct, t=task_id: progress.update(t, pct))` (domknięcie z domyślnym argumentem — pułapka late-binding). Pliki `.txt` przetwarzane sekwencyjnie po MKV (natychmiastowe, bez pasków).
5. Pętla zbierająca wzorem `installer.py:459-467`: `pending = set(futures)`, `while pending: _done, pending = wait(pending, timeout=_WAIT_POLL_SECONDS)`; `except KeyboardInterrupt: cancel.set()` i **dokończyć zbieranie** (drugi `wait` bez timeoutu — workery kończą szybko po ustawieniu cancel; wynik: outcome'y `cancelled` dla przerwanych).
6. Wyniki futures: `future.result()` w try z **osobnymi** blokami `except AniShiftError` i `except OSError` — obie klasy mapowane na `FileOutcome(status="failed", failure=...)`; wyjątki programistyczne (inne) **propagują** (fail loud — bug ma być głośny, nie połknięty; BLE001 i tak zakazuje szerokiego except).
7. Zwrot `PipelineReport` w kolejności discovery (nie kolejności ukończenia).

Przebieg `_process_mkv` (każdy krok w try mapującym `AniShiftError` → `FileFailure(step=...)`; helper `_fail_outcome(mkv, step, exc) -> FileOutcome` tłumaczy `exc.context` na `FileFailure`):

1. **Katalog roboczy**: `work_dir = workspace_root / _TMP_DIR_NAME / mkv.stem`; jeśli istnieje → `safe_rmtree(work_dir)` (`utils/safe_fs.py` — retry na Windows locking; D2c); `work_dir.mkdir(parents=True)`.
2. **identify** → `info` (step `"identify"`).
3. **select**: `proposal = select_tracks(info.tracks)`; manual → `selection = interaction.choose_tracks(info, proposal)`, auto → `selection = proposal` (step `"select"`).
4. **Brak ścieżki tekstowej** (KOREKTA — patrz §10.3): filtr kodeka działa już **przed** selektorem, więc `selection.subtitle_id` nigdy nie wskazuje formatu obrazkowego. Ten krok obsługuje wyłącznie przypadek „kontener ma napisy, ale żadne nie są tekstowe" — czyli `selection.subtitle_id is None` przy niepustej liście ścieżek `type == "subtitles"` w `info.tracks`. Wtedy: warning `f"no text subtitle track ({n} picture-only) — skipping subtitles"` i przetwarzanie idzie dalej (samo audio). Rozróżnienie względem E2 („MKV bez napisów w ogóle") jest w komunikacie, nie w zachowaniu.
5. **Warnings E2/E3**: `subtitle_id is None` → warning „no usable subtitles — file will be skipped by later stages"; `audio_id is None` → warning „no audio track". Oba None → outcome `done` z warningami, **bez** ekstrakcji (krok 1 już wyczyścił work_dir — zostaje pusty; akceptowalne).
6. **extract** → `extract_tracks(info, selection, work_dir, on_progress=..., cancel=cancel)` (step `"extract"`). `ExtractionError` z kodem `CANCELLED` → outcome `cancelled` (nie `failed`) — rozpoznanie po `exc.context.code is ErrorCode.CANCELLED`.
7. **split** (tylko gdy są napisy): `kind = subtitle_kind(result.subtitle_path)` (zawsze trafi — krok 4 przepuścił tylko tekstowe); `subs = load_subtitles(...)`; manual → `verdicts, samples = preview_styles(subs)` + `chosen = interaction.choose_spoken_styles(mkv, verdicts, samples)` + `split = split_subtitles(subs, kind=kind, spoken_styles=chosen, verdicts=verdicts)`; auto → `split = split_subtitles(subs, kind=kind)` (step `"split"`). Zero eventów Dialogue → warning „subtitles contain no dialogue events" (E11-degenerat), bez produktu.
8. **write**: `dest = workspace_root / f"{mkv.stem}{_DISPLAYED_INFIX}.{split.kind}"`; `displayed_path = write_displayed(split, dest)` (step `"write"`).
9. Outcome `done` z licznikami ze `split.stats`, ścieżkami i `already_polish` z selection. Na końcu (finally, tylko przy sukcesie) `on_progress(100)` — `extract_tracks` już to robi; nie duplikować, wystarczy przebieg naturalny.

`_process_txt`: `spoken = txt_to_spoken(path)` → outcome `done` z `spoken_lines=len(spoken)` (step `"txt"` przy błędzie). Produktu plikowego nie ma (I6).

`discover_inputs`: `sorted_paths = os_sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in {_MKV_SUFFIX, _TXT_SUFFIX} and _DISPLAYED_INFIX not in p.name)` — `natsort.os_sorted` (odpowiednik `natsorted` mm_avh z porządkiem eksplorera Windows; mm_avh używał `natsorted` — na nazwach bez wielkich różnic wynik ten sam; wybieramy `os_sorted`, bo user patrzy na folder w Eksploratorze). Wykluczenie `.displayed.` chroni przed wciągnięciem własnych produktów przy hipotetycznym przyszłym rozszerzeniu discovery — dziś produkty `.ass`/`.srt` i tak nie łapią się na sufiksy, ale filtr jest tani i jawny.

## 13. CLI: `pipeline_ui.py` + podpięcie Enter w `shell.py`

### 13.1 `anishift/cli/pipeline_ui.py`

```python
"""Enter-key pipeline entry: progress, manual prompts and the report render.

The only place stage 3 talks to the terminal: services and the runner return
data (see the rendering pattern of ``doctor``/``setup``), this module turns
it into console output, hosts the multi-bar display and implements the
manual-mode prompts.
"""
```

Publiczne API — jedna funkcja:

```python
def run_pipeline_command(context: AppContext) -> None:
    """Process the workspace on Enter and render the report.

    Auto mode runs behind a multi-bar display; manual mode runs sequentially
    with prompts and no live bars. A pipeline-level error (binaries) is
    rendered as one error line; per-file errors arrive inside the report.
    """
```

Przebieg (wiążący):

1. `mode = context.user_settings.mode` — czytane w momencie Enter (komendy `/auto`/`/manual` mutują context w miejscu, `commands.py:76-81`).
2. **Binarki z góry** (korekta z §12.2 krok 3): `ensure_binary(Binary.MKVMERGE)`; `ensure_binary(Binary.MKVEXTRACT)` w try z osobnymi `except InstallerError` / `except BinaryNotFoundError` → `console.print(f"[error]{exc}[/error]")` + `suggestion` z `exc.context` w osobnej szarej linii → return. (Pasek pobierania installera renderuje się tutaj, zanim powstanie multi-pasek — N8.) Wywołanie tylko, gdy discovery ma ≥1 MKV — więc najpierw:
3. `report_paths = discover_inputs(context.workspace_root)` — TAK, CLI woła discovery raz dla komunikatu E1 i decyzji o binarkach; runner woła je ponownie (idempotentne, tanie). Pusto → `console.print("[warning]Workspace is empty[/warning] — drop MKV files into workspace/ and press Enter.")` → return.
4. Manual: `interaction = _ManualInteraction()`; `report = run_pipeline(context, interaction=interaction)` — bez pasków (§8.5). Auto: `with MultiProgressManager() as progress: report = run_pipeline(context, progress=progress)`.
5. Render raportu (poza kontekstem paska): per plik jedna linia zbiorcza + linie szczegółów:
   - `done`: ikona `success`, nazwa, ` spoken {n} · displayed {m} · drawings {d} · collapsed {c}`; `displayed_path` w osobnej szarej linii, gdy powstał; `already_polish` → dopisek `[info](already Polish)[/info]`.
   - warnings: per warning linia `get_status_icon("warning") + tekst`.
   - `failed`: ikona `error`, nazwa, `[{failure.step}] {failure.message}`; `suggestion` w szarej linii z `-> ` (wzorzec `_handle_doctor`, `commands.py:113-115`). To jest R13.
   - `cancelled`: ikona `warning`, „interrupted".
   - Stopka: `Done X · Failed Y · Cancelled Z` + gdy Z>0: „Interrupted — press Enter to run again."
6. Ikony przez `get_status_icon` i mapę modułową `_STATUS_ICON: dict[FileStatus, StatusType]` (wzorzec `commands.py:27-33`).

Manual — klasa prywatna `_ManualInteraction` (implementuje `PipelineInteraction`):

- `choose_tracks`: tabela ścieżek jak `_print_mkv_info` (`mkvtoolnix.py:192-215`) w stylach repo (`console.print`, kolumny ID/TYPE/CODEC/LANG/NAME); linia propozycji `AUTO: audio {id} ({lang}), subtitles {id} ({lang})`; dwa prompty `input()`: `Audio track id [{proposal}]: ` i `Subtitle track id [{proposal}] ('-' = none): ` — Enter akceptuje propozycję, `-` oznacza brak, liczba spoza istniejących id danego typu → komunikat i ponowny prompt (pętla). Wynik: nowy `TrackSelection`; `already_polish` przeliczone z języka finalnie wybranej ścieżki napisów (ta sama reguła co `select_tracks` — wyciągnąć w `tracks.py` prywatny helper `_is_polish(language: str) -> bool` i użyć w obu miejscach).
- `choose_spoken_styles`: nagłówek z nazwą pliku; per werdykt linia `"{i}. {style} — {category} ({confidence:.0%}, {line_count} lines{dedup_note})"` gdzie `dedup_note = f", animation {raw}→{n}"` gdy `raw_line_count > line_count` (wzorzec `subtitle.py:200-205`, bez emoji — reguła repo: bez emoji w wyjściu); pod spodem próbki wcięte szaro (max 3). Prompt: `Styles to speak [Enter = accept classifier]: ` — Enter → `return None`; numery rozdzielone spacjami → zbiór nazw stylów (walidacja zakresu, zła wartość → ponowny prompt). `input()` w CLI jest legalny (N3 zakazuje go w **serwisach**).

### 13.2 Ctrl+C

`KeyboardInterrupt` w trakcie pipeline'u łapie pętla zbierająca runnera (§12.2 krok 5) — nie ubija REPL-a (dziś Ctrl+C w `session.prompt` kończy shell, `shell.py:59-60` — to zachowanie promptu zostaje bez zmian). W trybie manual (sekwencyjnym, bez executora) `run_pipeline_command` dodatkowo opakowuje wywołanie w `try/except KeyboardInterrupt` → renderuje „Interrupted." i wraca do promptu. Częściowe pliki: ekstrakcja sprząta swoje wyjścia przy cancel (§10.4), `write_displayed` jest atomowy (tmp + replace) — E14 domknięte konstrukcyjnie.

### 13.3 `anishift/cli/shell.py` — DOKŁADNA zmiana (`:62-64`)

Przed:

```python
        if not stripped:
            console.print("[warning]Pipeline in progress[/warning] — arrives in stage 3.")
            continue
```

Po:

```python
        if not stripped:
            from anishift.cli.pipeline_ui import run_pipeline_command  # noqa: PLC0415

            run_pipeline_command(context)
            continue
```

Lazy import wzorem `commands.py:93` (ciężkie importy w miejscu użycia). Nic więcej w `shell.py` nie zmieniać — hint bar (`:38`) i komunikat `:69` już mówią „press Enter to process" i pozostają prawdziwe.

## 14. Testy

Konwencje wspólne (z repo): pliki płasko w `tests/`, funkcje `test_<co>_<oczekiwanie>`, helpery prywatne `_` na górze pliku, fake'y zamiast mocków, fixture'y tylko przy `monkeypatch`, per-file-ignores `["D", "S101", "PLR2004", "TRY003"]` już skonfigurowane. **T20 obowiązuje w testach** — żadnych printów; wszystko przez asercje. CI = ubuntu-latest **bez** datasetu, binarek i plików MKV — każdy test zależny od nich musi się **skipować**, nie failować.

### 14.1 `tests/conftest.py` — pierwszy conftest (I9)

```python
"""Shared dataset locations and skip guards for regression/smoke tests."""

from __future__ import annotations

from pathlib import Path
from typing import Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
"""AniShift repository root."""

MM_AVH_TEMP: Final[Path] = _REPO_ROOT.parent / "mm_avh_working_space" / "temp"
"""Out-of-repo measurement datasets (absent in CI)."""

DATASET_ASS: Final[Path] = MM_AVH_TEMP / "dataset_ass"
"""183 real ASS files for classifier regression."""

GROUND_TRUTH: Final[Path] = MM_AVH_TEMP / "ground_truth"
"""Per-style ground-truth packs (pack_*.json)."""

TRACKS_DATASET: Final[Path] = MM_AVH_TEMP / "dataset.json"
"""206 MKV track listings with validated picks."""

WORKSPACE: Final[Path] = _REPO_ROOT / "workspace"
"""The real workspace holding the smoke MKV files."""

FUJI_EPISODE_3: Final[Path] = DATASET_ASS / "140___Fuji__Kimi_to_Koete_Koi_ni_Naru_-_03__1080p_.mkv.ass"
"""The measured per-line-granularity exemplar (style ``[Znaki]``)."""
```

Bez fixture'ów — same stałe importowane przez testy (`from conftest import DATASET_ASS` działa w pytest bez `__init__.py`, bo conftest jest w sys.path testów). Skipy w plikach testowych: `pytestmark = pytest.mark.skipif(not DATASET_ASS.is_dir(), reason="mm_avh dataset not available")` — na poziomie modułu w obu plikach regresji.

### 14.2 `tests/test_extraction_tracks.py`

Testy syntetyczne — port zestawu z `mm_avh/tests/track_selector_test.py` (helpery `_sub`/`_aud` budujące płaskie dicty, przełożone na `TrackInfo`):

1. `test_audio_prefers_japanese_over_english`
2. `test_audio_default_bonus_breaks_ties_within_language_only` (kor+default przegrywa z eng)
3. `test_subtitle_prefers_polish_over_english`
4. `test_signs_only_polish_loses_to_full_english` (kara -200)
5. `test_line_count_breaks_tie_within_language`
6. `test_tie_resolves_toward_lower_id`
7. `test_select_tracks_returns_none_ids_without_audio_or_subtitles`
8. `test_already_polish_flag_follows_chosen_subtitle_language` — pol → True, eng → False, brak napisów → False.

### 14.3 `tests/test_extraction_service.py`

- `test_parse_media_info_reads_real_identify_payload` — fixture'y `tests/data/*.json` (przechwycone `mkvmerge -J` z obu MKV testowych — krok 4 §15): oba pliki mają id0 video, id1 audio jpn, id2 subtitles ASS; asercje na typy/kodeki/języki, Youjo Senki napisy `language == "pol"`.
- `test_parse_media_info_rejects_invalid_json` / `test_parse_media_info_rejects_unrecognized_container` — `pytest.raises(ExtractionError, match=...)`.
- `test_format_extension_maps_known_and_unknown_codecs` — `S_TEXT/ASS→ass`, `A_EAC3→ac3`, nieznany → `mkv`.
- `test_is_text_subtitle_codec_accepts_only_text_formats` — ASS/SSA/SRT True; `S_HDMV/PGS`, `S_VOBSUB` False.
- `test_progress_regex_parses_gui_mode_lines` — `"#GUI#progress 42%"` → 42; linie nie-progress → None (test na `_RE_GUI_PROGRESS` — dopuszczalny dostęp do prywatnej stałej w teście).
- `test_extract_tracks_validates_missing_and_empty_outputs` — fake procesu: `extract_tracks` z monkeypatchem `subprocess.Popen` na fake zwracający exit 0 i **nie piszący pliku** → `pytest.raises(ExtractionError, match="wrote no data")`; wariant z plikiem 0-bajtowym — to samo (N4/E8). Fake: klasa `_FakeProcess` z `stdout` = iterator linii, `wait()` → 0, `terminate()` no-op; monkeypatch przez fixture (wzorzec repo: dwa importy modułu — `from anishift.services.extraction import service` + symbole).
- `test_extract_tracks_reports_progress_and_success` — fake piszący pliki i emitujący `#GUI#progress 50%` / `100%` → callback dostał `[50, 100, 100]` (ostatnie ze zwieńczenia), wynik ma obie ścieżki.
- `test_extract_tracks_cancel_removes_partial_files` — cancel ustawiony przed pętlą; fake z plikiem częściowym; `pytest.raises(ExtractionError)`; `exc.context.code is ErrorCode.CANCELLED`; plik skasowany.
- `test_extract_tracks_with_no_selection_runs_nothing` — oba id None → `ExtractionResult(None, None)`, Popen nie wywołany (fake `_never`).

### 14.4 `tests/test_subtitles_*.py`

`test_subtitles_text.py`:

- `test_visible_text_strips_override_blocks_and_html` — `"{\\pos(1,2)}Hello <i>world</i>"` → `"Hello world"`.
- `test_visible_text_normalises_breaks_and_whitespace` — `"a\\Nb\\hc"` → `"a b c"`.
- `test_is_drawing_requires_p_tag` — `"{\\p1}m 0 0 l 1 1"` True; `"m 0 0 l 1 1"` False; `"I'm 5"` False (regresja na nieportowany regex ścieżek, I4).
- `test_replace_visible_text_keeps_every_tag_block` — wejście z 3 blokami i tekstem między nimi: liczba bloków przed == po, kolejność zachowana, nowy tekst obecny raz.
- `test_replace_visible_text_handles_no_tags_and_tag_only` — bez tagów → sam nowy tekst; sam blok → blok + nowy tekst na końcu.

`test_subtitles_classifier.py` (syntetyczne SSAFile przez `SSAFile.from_string` z ręcznie zbudowanym ASS):

- `test_dedup_collapses_dense_identical_lines` — 6 identycznych linii co 50 ms → 1 zachowana, 5 usuniętych.
- `test_dedup_keeps_distant_repeats` — 5 identycznych co 10 s → wszystkie zostają (mediana ≥ 2000).
- `test_drawing_heavy_style_is_sign` / `test_karaoke_style_is_sign` / `test_song_name_is_sign` — twarde reguły.
- `test_dialogue_named_low_pos_style_is_dialog` — shortcut `_RE_DLG`.
- `test_verdicts_sorted_by_descending_line_count`.
- `test_no_dialogue_events_returns_empty`.

`test_subtitles_split.py`:

- `test_drawings_always_go_to_displayed` — nawet w stylu DIALOG.
- `test_uncertain_style_goes_to_displayed` — styl bez sygnałów (UNCERTAIN) → linie displayed (D3b).
- `test_empty_spoken_falls_back_to_all_nondrawing_spoken` — plik z samymi SIGN-stylami → wszystkie nie-rysunkowe spoken (E12); rysunki dalej displayed.
- `test_manual_override_wins_over_classifier` — `spoken_styles={"Signs"}` → linie tego stylu spoken mimo werdyktu SIGN.
- `test_collapse_merges_contiguous_run_with_min_max_timing` — 4 eventy tej samej treści, przylegające → jeden SpokenLine z `start=min`, `end=max`, `collapsed_away == 3`.
- `test_collapse_keeps_separate_distant_runs` — te same treści w dwóch odległych blokach → 2 linie.
- `test_collapse_drops_empty_visible_text`.
- `test_srt_input_marks_everything_spoken_and_writes_no_product` (tmp_path).
- `test_decisions_align_with_dialogue_events_order`.
- `test_write_displayed_preserves_text_styles_and_timings` — zbuduj ASS z 8 stylami i tagami; split; zapis do tmp_path; wczytaj produkt: każdy event displayed ma **identyczne** `text`/`style`/`start`/`end` jak źródłowy odpowiednik; liczba stylów == 8; komentarze zachowane. (To DoD „tagi/style/timingi identyczne".)
- `test_write_displayed_is_byte_deterministic` — dwa zapisy → `read_bytes()` identyczne (N2).
- `test_write_displayed_returns_none_without_displayed_events`.
- `test_source_subs_object_is_not_mutated` — snapshot `to_string` przed/po split+write identyczny (N1 w pamięci).
- **`test_fuji_znaki_sieve_collapses_to_18`** (skipif bez datasetu; import `FUJI_EPISODE_3` z conftest) — wczytaj plik; eventy stylu `[Znaki]`: asercja `len == 1381` (strażnik wersji datasetu); po odsiewie rysunków + `collapse_fbf` → **18** linii. To pin dla `_FBF_MAX_GAP_MS` (DoD).

`test_subtitles_txt.py`:

- `test_txt_to_spoken_packs_sentences_up_to_limit` (tmp_path, mały limit np. 40).
- `test_txt_to_spoken_splits_oversized_sentence_on_words`.
- `test_txt_to_spoken_zero_timings_and_empty_style`.
- `test_txt_to_spoken_raises_domain_error_for_missing_file` — `pytest.raises(SubtitleError)`.

### 14.5 `tests/test_regression_classifier.py` (skipif bez datasetu)

Metryka odtwarza pomiar z wymagań — definicja wiążąca:

1. Wczytaj wszystkie `pack_*.json` (bez `_packs.json`) → `gt: dict[filename, dict[style, {cat, uncertain}]]`; kategorie GT: `DIALOG`, `ZNAK`, `PIOSENKA` (PIOSENKA liczy się jak ZNAK — nie-czytane).
2. Dla każdego pliku obecnego jednocześnie w GT i `dataset_ass`: `classify_styles(load_subtitles(...))`. Style oceniane: obecne w werdyktach (czyli ≥1 linia Dialogue — style „oznaczone na ślepo" odpadają same) **i** `uncertain == false` w GT (77 niepewnych ludzkich ocen poza metryką).
3. Mapowanie parytetowe (§8.3): predykcja „czytane" = `category in (DIALOG, UNCERTAIN)`; oczekiwanie „czytane" = `cat == "DIALOG"`.
4. Asercje twarde: `accuracy >= 0.9586`; zbiór pudeł typu „zgubił dialog" (oczekiwane czytane, predykcja nie) `<=` (issubset) `_KNOWN_MISSED_DIALOG`.

```python
_KNOWN_MISSED_DIALOG: Final[frozenset[tuple[str, str]]] = frozenset({
    # Filled in implementation step 8 (§15) from the first measured run:
    # the two Fuji ep. 3-4 style-level misses named in the requirements.
})
```

Procedura wypełnienia (krok 8 §15): pierwszy przebieg testu z pustym zbiorem wypisze pudła w komunikacie asercji (`assert missed <= _KNOWN_MISSED_DIALOG, f"new missed dialog: {sorted(missed)}"`); oczekiwane dokładnie 2 pary z plików `140___Fuji...03` i `141___Fuji...04`; wpisać je do stałej (z docstringiem „The two style-granularity misses measured at port time (Fuji 3-4)."). Jeśli wyjdzie cokolwiek innego niż te 2 — **STOP, port ma błąd**, wracać do diffu z `style_classifier.py` (nie poszerzać zbioru!).

### 14.6 `tests/test_regression_tracks.py` (skipif bez `dataset.json`)

Wczytaj `TRACKS_DATASET`; sekcja `mkv` (206 wpisów: `subs[]`, `auds[]` w płaskim kształcie + `pick_sub`, `pick_aud`). Dla każdego wpisu zbuduj `TrackInfo` z płaskich pól (`lang→language`, `lines→num_entries`, `name`, `default`; `language_ietf=""`, `codec_id` z `codec` bez mapowania — selektor go nie czyta) + sztuczny track `type="video"` nie jest potrzebny (selektor filtruje po typie). `select_tracks(...)`: zgodność `audio_id == pick_aud` i `subtitle_id == pick_sub` liczona osobno; asercje `>= 0.95` dla każdej (próg identyczny ze źródłowym testem mm_avh — R4 parytet). Dodatkowo asercja „pełny parytet z portem": wynik naszych `select_audio_track`/`select_subtitle_track` na dictach == wynik przez `select_tracks` na `TrackInfo` — dla każdego wpisu (to jest właściwy test 1:1; próg 0.95 dotyczy zgodności z ludzkim ground truth, nie portu).

### 14.7 `scripts/measure_split.py` — pomiar, nie test

Typowany skrypt (mypy strict; `scripts/**` ma ignorowane D i T20 — `print` dozwolony). Wejście: ścieżki jak conftest (zduplikowane stałe — scripts nie importuje z tests). Wyjście na stdout:

1. Metryka parytetowa (jak §14.5) — sanity: 95.86%.
2. Metryka produkcyjna D3b (`UNCERTAIN → displayed`): accuracy, liczba „przeczytał znak", liczba i lista „zgubił dialog" — **delta względem parytetu** (§8.3).
3. Zysk sita (Trop 2 — „do zmierzenia po etapie 3"): dla każdego pliku `split_subtitles` w auto; suma `drawing_events`, `collapsed_away`, `spoken_lines`; top-10 plików po `collapsed_away`.

Wyniki idą do opisu PR i do issue #16. Uruchomienie: `uv run python scripts/measure_split.py`.

### 14.8 `tests/test_pipeline_runner.py`

Monkeypatch kroków na poziomie modułu runnera (wzorzec repo: `from anishift.pipeline import runner` + `monkeypatch.setattr(runner, "identify", fake)`). Fake'i budują minimalne `MediaInfo`/`TrackSelection`/`SubtitleSplit`.

- `test_discover_inputs_returns_naturally_sorted_top_level_files` (tmp_path: `ep2.mkv`, `ep10.mkv`, `notes.txt`, `sub.ass`, katalog `tmp/x.mkv`) → `[ep2.mkv, ep10.mkv, notes.txt]`.
- `test_discover_inputs_skips_displayed_products`.
- `test_empty_workspace_returns_empty_report`.
- `test_failing_file_does_not_stop_the_next_one` — 2 pliki; fake `identify` rzuca `ExtractionError` dla pierwszego; report: `[failed, done]`, failure ma `step == "identify"`, message i suggestion niepuste (R13/E16).
- `test_unexpected_exception_propagates` — fake rzuca `RuntimeError` → `pytest.raises(RuntimeError)` (fail loud).
- `test_manual_mode_runs_sequentially_and_uses_interaction` — fake interaction rejestrujący wywołania; 2 pliki; kolejność wywołań ściśle plik-po-pliku; wybory interaction odzwierciedlone w outcome.
- `test_auto_mode_reports_progress_per_file` — fake `extract_tracks` woła `on_progress(50)`; fake reporter zbiera `(task_id, completed)`; każdy plik ma własny task.
- `test_cancelled_extraction_yields_cancelled_status` — fake rzuca `ExtractionError` z `ErrorCode.CANCELLED` → status `cancelled`.
- `test_no_subtitles_yields_done_with_warning` (E2) / `test_unsupported_subtitle_codec_is_skipped_with_warning`.
- `test_tmp_workdir_is_recreated_fresh` — istniejący `tmp/<stem>/stale.file` znika po przebiegu (D2c).
- `test_txt_file_produces_spoken_outcome`.
- `test_worker_count_clamps` — `_worker_count(1) == 1`, `_worker_count(100) <= _WORKER_CAP`.

### 14.9 `tests/test_smoke_pipeline.py` — realne pliki (lokalnie; CI skip)

```python
pytestmark = [
    pytest.mark.skipif(not is_windows(), reason="bundled binaries are Windows-only"),
    pytest.mark.skipif(resolve_binary(Binary.MKVMERGE) is None, reason="mkvtoolnix not installed"),
    pytest.mark.skipif(not _YOUJO.is_file(), reason="smoke MKVs not present"),
]
```

Pliki: `workspace/[shisha] Youjo Senki II - 01.mkv` (napisy pol — already_polish!), `workspace/[SubsPlease] Mushoku Tensei S3 - 03 (1080p) [8488B15C].mkv` (eng) + 3 pliki `BUG ...` obecne w workspace (nazwy w conftest smoke'a jako stałe; brakujący plik → skip tego parametru przez `pytest.param` z warunkiem). Test działa **na poziomie serwisów z wyjściem do `tmp_path`** — nie odpala pełnego `run_pipeline` na realnym workspace (nie śmiecimy produktami w folderze usera z testu):

- `test_identify_reports_three_tracks_and_languages` — oba pliki: id0 video, id1 audio jpn, id2 subtitles; Youjo `pol`, Mushoku `eng`.
- `test_selection_picks_audio_1_and_subs_2_with_polish_flag` — (1, 2); Youjo `already_polish is True`, Mushoku False (E4/E15 — nazwy ze spacjami i nawiasami przechodzą przez subprocess listą argumentów).
- `test_extract_produces_nonempty_outputs_and_leaves_source_untouched` — hash MKV (sha256 pierwszych 1 MiB + rozmiar — pełny hash 300 MB za wolny) przed/po identyczny; `audio.*`/`subs.*` w tmp_path niepuste (N1, N4).
- `test_split_and_write_displayed_end_to_end` — split wyciągniętych napisów; `spoken_lines > 0`; zapis displayed do tmp_path; wczytany produkt parsowalny; source ASS w tmp_path bajtowo nietknięty.
- `test_two_runs_are_byte_identical` — split+write dwa razy → identyczne bajty (N2, DoD determinizm).
- `test_bug_files_do_not_crash` — parametryzowany po 3 plikach BUG: identify → select → extract → split → write przechodzi bez wyjątku **albo** rzuca wyłącznie `AniShiftError` (błąd domenowy, nie traceback); wynik per plik odnotować w PR (to jest „Smoke: 3 pliki z bugs" z DoD — bugi tych plików dotyczą timingów/sekund w nazwie, etap 3 ma ich nie wywracać).

Pełny e2e przez Enter (prawdziwy workspace, oba MKV, paski, raport) — **weryfikacja ręczna** w kroku 13 §15, nie test automatyczny.

## 15. Kolejność implementacji + weryfikacja KAŻDEGO kroku

Warunek startu: PR 3.1 zmergowany (Część I). Branch: `feat/stage-3-extraction-subtitles` (rebase na `main`).

1. **Szkielety domen**: `services/__init__.py`, `extraction/{__init__,errors,types}.py`, `subtitles/{__init__,errors,types}.py` (bez logiki).
   → weryfikacja: `uv run ruff check anishift/ && uv run mypy anishift/` zielone; importy działają (`uv run python -c "import anishift.services.extraction, anishift.services.subtitles"`).
2. **`extraction/tracks.py`** (port + wrapper) + `tests/test_extraction_tracks.py` + `tests/conftest.py` + `tests/test_regression_tracks.py`.
   → weryfikacja: `uv run pytest tests/test_extraction_tracks.py tests/test_regression_tracks.py -q` — syntetyczne zielone, regresja ≥0.95/0.95 i pełny parytet portu na 206 wpisach.
3. **`subtitles/text.py`** + testy.
   → weryfikacja: `uv run pytest tests/test_subtitles_text.py -q`.
4. **Fixture'y identify**: `uv run python -c` (skrypt w scratchpadzie) wołający `mkvmerge -J` na obu MKV z workspace → zapis do `tests/data/*.json` (skrócić: zostawić `container` i `tracks`, wyciąć `attachments`/`chapters` jeśli ogromne — fixture ma być mały; NIE zmieniać wartości pól).
   → weryfikacja: pliki < 20 KB, poprawny JSON.
5. **`extraction/service.py`** + `tests/test_extraction_service.py`.
   → weryfikacja: testy zielone; **ręcznie**: skrypt w scratchpadzie: `identify` + `extract_tracks` na `[shisha] Youjo Senki II - 01.mkv` do katalogu w scratchpadzie z `on_progress=print`-owym callbackiem — procenty lecą rosnąco, powstają `audio.aac`(/właściwe rozszerzenie) i `subs.ass`, oba niepuste; `subs.ass` **bit w bit** identyczny z ekstrakcją mm_avh tej samej ścieżki (`fc.exe /b` z plikiem wyciągniętym ręcznie `mkvextract "<mkv>" tracks 2:ref.ass`). Tu też weryfikuje się składnia „source przed mode" (§10.4) — jeśli binarka odrzuci, zastosować jedyną dozwoloną korektę.
6. **`subtitles/classifier.py`** (port z I5) + `tests/test_subtitles_classifier.py`.
   → weryfikacja: testy zielone; diff logiczny z `style_classifier.py` obejrzany ręcznie (tylko dozwolone odchylenia z §11.3).
7. **`subtitles/service.py`** + `tests/test_subtitles_split.py` (z testem Fuji).
   → weryfikacja: `uv run pytest tests/test_subtitles_split.py -q`; test Fuji daje 18 — jeśli nie, kalibracja `_FBF_MAX_GAP_MS` wg procedury §11.5 i ponowny bieg.
8. **`tests/test_regression_classifier.py`** — pierwszy bieg z pustym `_KNOWN_MISSED_DIALOG`, wpisanie 2 zmierzonych pudeł Fuji 3-4, drugi bieg zielony.
   → weryfikacja: `accuracy >= 0.9586` w asercji; dokładnie 2 znane pudła. Inny wynik = błąd portu → wracać do kroku 6.
9. **`subtitles/txt.py`** + testy.
   → weryfikacja: `uv run pytest tests/test_subtitles_txt.py -q`.
10. **`pipeline/{types,runner}.py`** + `tests/test_pipeline_runner.py`.
    → weryfikacja: `uv run pytest tests/test_pipeline_runner.py -q`; `uv run mypy anishift/` zielone (protokoły strukturalne się domykają).
11. **`cli/pipeline_ui.py` + edycja `shell.py`**.
    → weryfikacja ręczna: `uv run anishift` → Enter na pełnym workspace (2 MKV + 3 BUG): 5 pasków, różne kolory w trakcie, raport per plik z licznikami; `X.displayed.ass` powstaje obok MKV; `/manual` → Enter → prompty ścieżek i stylów z próbkami, Enter-Enter akceptuje wszystko; Ctrl+C w połowie ekstrakcji → „Interrupted", REPL żyje, częściowych plików brak w `tmp/<stem>/`; pusty workspace (tymczasowo `ANISHIFT_WORKSPACE_ROOT` na pusty katalog) → komunikat E1.
12. **Pomiar sufitu równoległości** — `scripts/measure_parallel.py`: dla `workers in (1, 2, 4, 8)` trzykrotnie: wyczyść `tmp/`, zmierz `time.perf_counter` wokół ekstrakcji wszystkich 5 MKV (`ThreadPoolExecutor` + `extract_tracks`, bez pasków), wypisz mediany. Reguła wyboru: **najmniejsze** `workers`, którego mediana jest w granicach 110% najlepszej mediany. Wpisać do `_WORKER_CAP`, wyniki do PR.
    → weryfikacja: stała zaktualizowana, tabelka pomiarów w opisie PR.
13. **Smoke** — `tests/test_smoke_pipeline.py` + ręczny pełny przebieg Enter (auto) na obu MKV testowych: zrzut raportu do PR; sha256 obu MKV przed/po identyczne (N1); drugi Enter → identyczne bajty `displayed.ass` (N2).
    → weryfikacja: `uv run pytest tests/test_smoke_pipeline.py -q` zielone lokalnie.
14. **`scripts/measure_split.py`** + bieg; liczby (D3-delta, zysk sita) do PR i przygotowane pod issue #16.
    → weryfikacja: skrypt przechodzi mypy/ruff, wynik sensowny (parytet == 95.86%).
15. **Bramki całościowe + porządek**: `uv run ruff check anishift/ tests/ scripts/measure_split.py scripts/measure_parallel.py && uv run ruff format --check anishift/ tests/ && uv run mypy anishift/ tests/ && uv run pytest` — wszystko zielone; `git status` bez niezamierzonych plików (scratchpad poza repo!).
16. **PR** `feat: stage 3 — MKV extraction and subtitle split` — opis: decyzje D1-D7 jednym akapitem, tabela DoD (§16) z odhaczeniem, pomiary (regresja, D3-delta, sufit równoległości, smoke). CodeRabbit → `/coderabbit` → merge. Po merge: założyć issues (§18).

## 16. Definition of Done (mapowanie na wymagania §8)

| DoD z wymagań | Jak zweryfikowane |
|---|---|
| Enter przetwarza oba MKV testowe bez pytań (auto) | krok 11+13 §15, ręczny przebieg + smoke |
| Oryginalny ASS nietknięty po całym przebiegu (N1) | smoke: hash MKV; `test_source_subs_object_is_not_mutated`; `subs.*` w tmp nie jest nadpisywany po ekstrakcji |
| `displayed.ass`: tagi/style/timingi identyczne, tylko tekst podmieniony | `test_write_displayed_preserves_text_styles_and_timings` (w etapie 3 tekst = oryginał; mechanizm podmiany `replace_visible_text` przetestowany na zapas dla etapu 4) |
| Parytet ID ścieżek z `track_selector` (regresja) | `test_regression_tracks.py`: pełny parytet portu + ≥0.95 vs GT na 206 |
| Klasyfikator ≥95.86% na 182 plikach — automatyczny test | `test_regression_classifier.py` (mapowanie parytetowe, §8.3) |
| Zero nowych „zgubił dialog" poza 2 znanymi (Fuji 3-4) | asercja `missed <= _KNOWN_MISSED_DIALOG` |
| Rysunki (`\p1`) nie trafiają do lektora | `test_drawings_always_go_to_displayed` + E12-test (rysunki nie wchodzą do fallbacku) |
| Collapse FBF: 1381 → 18 na pliku Fuji | `test_fuji_znaki_sieve_collapses_to_18` |
| Determinizm: dwa przebiegi → identyczny bajt (N2) | `test_write_displayed_is_byte_deterministic` + smoke `test_two_runs_are_byte_identical`; pysubs2 przypięty przez `uv.lock` (I7) |
| Pasek live przez `--gui-mode`; wiele plików = wiele pasków | Część I (3.1) + `test_auto_mode_reports_progress_per_file` + weryfikacja wizualna kroku 11 |
| SRT na wejściu działa jak ASS (R2) | `test_srt_input_marks_everything_spoken_and_writes_no_product` + ścieżka wspólna w splicie |
| Błąd = jasny komunikat co i gdzie; nie przerywa reszty (R13) | `test_failing_file_does_not_stop_the_next_one` + render `failure.step/message/suggestion` |
| Zero `input()`/`sys.exit()` w serwisach (N3) | `Grep -n "input\(|sys\.exit" anishift/services anishift/pipeline` pusty (sprawdzić w kroku 15) |
| pysubs2 przypięty | `uv.lock` (I7) — zero zmian w pyproject |
| Równoległość: sufit zmierzony | krok 12 + `_WORKER_CAP` + tabela w PR |
| Bramki zielone | krok 15 |
| Smoke: oba MKV + 3 pliki z bugs | `test_smoke_pipeline.py` + raport w PR |

## 17. Ryzyka i czego pilnować

1. **`event.plaintext = ...` kasuje tagi** (2169→297, zmierzone). Zapora: jedyny zapis tekstu przez `replace_visible_text`; żaden kod etapu 3 nie mutuje eventów w ogóle. Przy review szukać przypisań do `.plaintext` i `.text` — ma ich nie być poza testami.
2. **Kolejność argumentów mkvextract** — plan zakłada „source przed mode" wg zwendorowanego manuala; mm_avh używał starszej („mode przed source"). Weryfikacja w kroku 5 §15 na przypiętej binarce; dozwolona tylko zamiana kolejności, nic więcej.
3. **Dryf regresji przez politykę D3** — rozbrojone rozdzieleniem mapowań (§8.3). Pilnować, żeby test regresji NIE używał polityki produkcyjnej.
4. **`_FBF_MAX_GAP_MS`** — wartość kalibrowana testem Fuji (18); nie „stroić" pod inne pliki. Skutki collapse na całym zbiorze raportuje `measure_split.py`, decyzje o zmianach → issue #16.
5. **pysubs2 a sekcje niestandardowe ASS** — pomiar wykazał zero strat na eventach/stylach/tagach; egzotyczne sekcje (`[Fonts]`, załączniki) mogą nie przetrwać `to_string`. Displayed to **produkt**, nie źródło prawdy (źródło zostaje w `tmp/<stem>/subs.ass` i obok w MKV) — strata sekcji fontów w produkcie jest akceptowalna; jeśli smoke pokaże realny plik z `[Fonts]`, odnotować w issue.
6. **Rich Live vs prompt** (N8) — pasek istnieje tylko w auto; manual bez pasków; paski installera nigdy równolegle z multi-paskiem (kolejność w §13.1 krok 2). Nie otwierać `MultiProgressManager` przed `ensure_binary`.
7. **Wątki + rich** — wszystkie mutacje przez `MultiProgressManager` pod jego lockiem; workery NIE drukują (zero `console.print` w runnerze/serwisach); raport renderowany po zamknięciu paska.
8. **Windows locking przy czyszczeniu `tmp/<stem>/`** — używać `utils.safe_rmtree` (retry), nie `shutil.rmtree`.
9. **CI ubuntu-latest** — wszystkie testy zależne od datasetu/binarek/MKV skipują się przez conftest-guardy; sprawdzić w PR, że CI jest zielone mimo skipów (skipy widoczne w logu jako `s`).
10. **Encoding** — UTF-8 only (I10); plik w UTF-16 padnie jako E13 z czytelnym komunikatem — to zachowanie zamierzone, nie bug.
11. **`os_sorted` vs `natsorted`** — przy wątpliwościach co do kolejności odcinków w raporcie porównać z Eksploratorem; wybór `os_sorted` jest świadomy (§12.2).
12. **Filtr kodeka MUSI być przed selektorem, nie po** (§10.3). `track_selector.py:211-229` filtruje tylko po `type == "subtitles"` — kodeka nie czyta w ogóle. Filtr po selekcji = ścieżka obrazkowa wygrywa punktami językowymi, zostaje odrzucona, a plik kończy bez napisów mimo tekstowej ścieżki obok. Przy review sprawdzić, że `select_tracks` dostaje **już przefiltrowaną** listę i że `test_select_tracks_prefers_text_over_picture` istnieje.
13. **Zakres** — etap 3 NIE zawiera: strojenia heurystyki (#16), cache/zewnętrznych napisów (D2d), preferencji językowych (D7), pół-automatu manuala (D5c), per-zasób pasków installera, tłumaczenia/TTS. Każda pokusa „przy okazji" = scope creep.

## 18. Issues do założenia po merge (dokładne tytuły)

1. `feat: zewnętrzne napisy wygrywają z ekstrakcją (D2d)` — scenariusze usera z wymagań §7-D2; wymaga własnych wymagań („skąd wiemy, że plik jest zewnętrzny"); zawiera też ochronę ręcznie edytowanego `displayed.ass` (§8.1).
2. `feat: /settings — preferencje językowe audio/napisów (D7)` — dziś zaszyte JP>EN>CH / PL>EN; wymaga aktualizacji regresji track-selectora.
3. `feat: manual półautomat — pytaj tylko o UNCERTAIN (D5c)` — po danych z issue #16.
4. `feat: per-zasób paski w run_setup (MultiProgressManager)` — beneficjent 3.1; migracja `installer.py:428` na multi-pasek.
5. Komentarz do **istniejącego issue #16** (heurystyka 100%): liczby z `scripts/measure_split.py` (metryka D3b, zysk sita R6, delta „przeczytał znak" po collapse) + przypomnienie tropów 3/5/7/8 z wymagań §9.

---

# ANEKSY — materiał wykonawczy

## Aneks A — mapa edge case'ów E1–E20 → mechanizm → test

Każdy edge case z wymagań §6 ma tu wskazany dokładny mechanizm w planie i test, który go pilnuje. Agent przy implementacji odhacza kolumnę „Test" — jeśli którykolwiek wiersz nie ma zielonego testu (albo odnotowanej weryfikacji ręcznej), etap nie jest skończony.

| # | Sytuacja | Mechanizm w planie | Test / weryfikacja |
|---|----------|--------------------|--------------------|
| E1 | `workspace/` puste | `discover_inputs` → pusta lista → CLI drukuje „Workspace is empty…" (§13.1 krok 3) | `test_empty_workspace_returns_empty_report` + ręcznie krok 11 §15 |
| E2 | MKV bez napisów | `select_tracks` → `subtitle_id=None` → warning, audio ekstrahowane, split pominięty (§12.2 `_process_mkv` krok 5) | `test_no_subtitles_yields_done_with_warning` |
| E3 | MKV bez audio | `audio_id=None` → warning, same napisy (§12.2 krok 5) | wariant w tym samym teście (parametryzacja) |
| E4 | Napisy już po polsku | `TrackSelection.already_polish` (port `mkvtoolnix.py:398`) → `FileOutcome.already_polish` → render `(already Polish)`; etap 4 skonsumuje | `test_already_polish_flag_follows_chosen_subtitle_language` + smoke (Youjo Senki `lang=pol`) |
| E5 | MKV z SRT zamiast ASS | `_SUFFIX_KIND`/`subtitle_kind` + ścieżka SRT w splicie (§11.6); D4(b) | `test_srt_input_marks_everything_spoken_and_writes_no_product` |
| E6 | Brak `mkvextract.exe` | `ensure_binary` × 2 w CLI przed paskiem (§13.1 krok 2); brak sieci → `InstallerError(NETWORK_ERROR)` renderowany z sugestią | `tests/test_installer.py` (istniejące) + render w §13.1 |
| E7 | mkvextract exit != 0 | `ExtractionError(EXTRACTION_FAILED)` z ogonem outputu + suggestion (§10.4) | fake procesu z exit 1 (wariant w `test_extraction_service`) |
| E8 | exit == 0, brak pliku | walidacja N4: `is_file() and st_size > 0` (§10.4) | `test_extract_tracks_validates_missing_and_empty_outputs` |
| E9 | Plik już wyekstrahowany | D2(c): `safe_rmtree(tmp/<stem>)` na starcie — zawsze świeżo (§12.2 krok 1) | `test_tmp_workdir_is_recreated_fresh` |
| E10 | Dwie ścieżki napisów tego samego kodeka | niezmiennik „dokładnie 1 audio + 1 subs" + stałe nazwy `audio.*`/`subs.*` (§8.1) — kolizja niemożliwa konstrukcyjnie | pokryte konstrukcją; asercja liczby spec w `test_extract_tracks_reports_progress_and_success` |
| E11 | ASS bez eventów `Dialogue` | pusty split + warning „subtitles contain no dialogue events" (§11.5, §12.2 krok 7) | `test_no_dialogue_events_returns_empty` + wariant runnera |
| E12 | Klasyfikator: zero `spoken` | fallback: wszystkie nie-rysunkowe → spoken (§11.5) | `test_empty_spoken_falls_back_to_all_nondrawing_spoken` |
| E13 | Uszkodzony ASS | `load_subtitles` → `SubtitleError(SUBTITLE_PARSE_FAILED)` → `FileOutcome failed`, reszta plików idzie (I10) | `test_failing_file_does_not_stop_the_next_one` (fake w kroku split) + test load na śmieciowym pliku |
| E14 | Ctrl+C | pętla poll 0.2 s + `cancel.set()` (§12.2 krok 5); ekstrakcja kasuje częściowe pliki (§10.4); zapis atomowy (§11.5) | `test_extract_tracks_cancel_removes_partial_files`, `test_cancelled_extraction_yields_cancelled_status` + ręcznie krok 11 §15 |
| E15 | Nazwa ze spacjami / PL znakami | subprocess **listą argumentów**, `pathlib` wszędzie, zero shella | smoke na obu MKV (nazwy z `[ ]`, spacjami) |
| E16 | 2+ MKV | discovery natsorted + executor; izolacja błędów (R13) | `test_failing_file_does_not_stop_the_next_one`, `test_discover_inputs_returns_naturally_sorted_top_level_files` |
| E17 | Brak miejsca na dysku | `except OSError` (osobny blok) → `IO_ERROR` → `FileOutcome failed` (§10.4, §12.2 krok 6) | fake `OSError` w runnerze (wariant testu izolacji) |
| E18 | Skasowany `workspace/` | `ensure_workspace_dir` na starcie `run_pipeline` (§12.2 krok 1) | `test_empty_workspace_returns_empty_report` na tmp_path bez podkatalogów |
| E19 | `film.ass` i `film.srt` obok siebie | poza zakresem: discovery nie czyta luźnych napisów (§8.2) → issue D2(d) | `test_discover_inputs_returns_naturally_sorted_top_level_files` (`.ass` w root ignorowany) |
| E20 | Wiele napisów w tym samym czasie | etap 3 zachowuje timingi bez zmian (collapse tylko scala identyczne teksty; różne teksty w tym samym czasie zostają osobno) — problem etapu 6 | `test_collapse_keeps_separate_distant_runs` + niezmienniki timingów w `test_write_displayed_preserves_text_styles_and_timings` |

## Aneks B — `_CODEC_EXTENSION` w całości (port `mkvtoolnix.py:434-475`, 1:1)

Do wklejenia w `extraction/service.py` — wartości przepisane ze źródła, nie zmieniać ani jednej:

```python
_CODEC_EXTENSION: Final[dict[str, str]] = {
    "A_AAC/MPEG2/*": "aac",
    "A_AAC/MPEG4/*": "aac",
    "A_AAC": "aac",
    "A_AC3": "ac3",
    "A_EAC3": "ac3",
    "A_ALAC": "caf",
    "A_DTS": "dts",
    "A_FLAC": "flac",
    "A_MPEG/L2": "mp2",
    "A_MPEG/L3": "mp3",
    "A_OPUS": "opus",
    "A_PCM/INT/LIT": "wav",
    "A_PCM/INT/BIG": "wav",
    "A_REAL/*": "rm",
    "A_TRUEHD": "truehd",
    "A_MLP": "mlp",
    "A_TTA1": "tta",
    "A_VORBIS": "ogg",
    "A_WAVPACK4": "wv",
    "S_HDMV/PGS": "sup",
    "S_HDMV/TEXTST": "txt",
    "S_KATE": "ogg",
    "S_TEXT/SSA": "ssa",
    "S_TEXT/ASS": "ass",
    "S_SSA": "ssa",
    "S_ASS": "ass",
    "S_TEXT/UTF8": "srt",
    "S_TEXT/ASCII": "srt",
    "S_VOBSUB": "sub",
    "S_TEXT/USF": "usf",
    "S_TEXT/WEBVTT": "vtt",
    "V_MPEG1": "mpeg",
    "V_MPEG2": "mpeg",
    "V_MPEG4/ISO/AVC": "h264",
    "V_MPEG4/ISO/HEVC": "h265",
    "V_MS/VFW/FOURCC": "avi",
    "V_REAL/*": "rm",
    "V_THEORA": "ogg",
    "V_VP8": "ivf",
    "V_VP9": "ivf",
}
"""Matroska codec id to output file extension (ported table)."""
```

Uwaga: `S_HDMV/TEXTST → "txt"` nie koliduje z discovery `.txt` — pliki ekstrakcji żyją w `tmp/<stem>/`, a discovery czyta wyłącznie top-level `workspace/` (§12.2). Filtr `is_text_subtitle_codec` i tak odetnie ten kodek przed ekstrakcją napisów (krok 4 `_process_mkv`).

## Aneks C — dokładne ciała funkcji zmienionych w portach

Wszystko inne w obu portach jest **verbatim** ze źródła. Poniżej komplet funkcji, których dotyczą dozwolone odchylenia — do wklejenia w tej postaci.

### C.1 `extraction/tracks.py` — helpery z mypy-poprawkami (§10.3)

```python
def _track_name(track: dict[str, Any]) -> str:
    """Return the track's display name from whichever field is present.

    Accepts the flat shape (``track_name``/``name``) and the raw mkvmerge
    JSON shape (``properties.track_name``).

    Args:
        track: A single track dict.

    Returns:
        The track name, or an empty string if none is set.
    """
    value = (
        track.get("track_name")
        or track.get("name")
        or track.get("properties", {}).get("track_name")
        or ""
    )
    return str(value)


def _track_language(track: dict[str, Any]) -> str:
    """Return the track's ISO 639 language tag from whichever field is present.

    Args:
        track: A single track dict.

    Returns:
        The language code (lowercased), or an empty string if none is set.
    """
    value = (
        track.get("language")
        or track.get("lang")
        or track.get("properties", {}).get("language")
        or ""
    )
    return str(value).lower()


def _track_default(track: dict[str, Any]) -> bool:
    """Return whether the track is flagged as the container default.

    Args:
        track: A single track dict.

    Returns:
        True if any default-flag field is truthy.
    """
    return bool(
        track.get("default_track")
        or track.get("default")
        or track.get("properties", {}).get("default_track")
    )


def _lines_bonus(track: dict[str, Any]) -> float:
    """Return the line-count tie-breaker, or 0.0 when the count is unknown.

    Args:
        track: A single track dict, optionally with a line-count field.

    Returns:
        ``lines / _LINES_DIVISOR``, or 0.0 if no usable count is present.
    """
    lines = track.get("num_lines")
    if lines is None:
        lines = track.get("lines")
    if lines is None:
        lines = track.get("properties", {}).get("num_index_entries")
    if lines is None:
        return 0.0
    return float(lines) / _LINES_DIVISOR


def select_subtitle_track(tracks: list[dict[str, Any]]) -> int | None:
    """Pick the subtitle track to translate and voice, by metadata alone.

    Args:
        tracks: All tracks of the MKV, mixed types.

    Returns:
        The chosen subtitle track's id, or None if the file has no subtitles.
    """
    subtitles = [t for t in tracks if t.get("type") == "subtitles"]
    if not subtitles:
        return None
    best = max(subtitles, key=lambda t: (score_subtitle_track(t), -int(t["id"])))
    return int(best["id"])


def select_audio_track(tracks: list[dict[str, Any]]) -> int | None:
    """Pick the original audio track for the narrator, by metadata alone.

    Args:
        tracks: All tracks of the MKV, mixed types.

    Returns:
        The chosen audio track's id, or None if the file has no audio.
    """
    audio = [t for t in tracks if t.get("type") == "audio"]
    if not audio:
        return None
    best = max(audio, key=lambda t: (score_audio_track(t), -int(t["id"])))
    return int(best["id"])
```

(`score_subtitle_track`, `score_audio_track`, `_is_signs_only` oraz wszystkie stałe — verbatim ze źródła, tylko adnotacje `dict` → `dict[str, Any]`.)

### C.2 `subtitles/classifier.py` — `_classify_metrics` po I5 (jedyna zmieniona funkcja)

```python
def _classify_metrics(metrics: _StyleMetrics, style: str, total: int) -> tuple[Category, float]:
    """Classify a style from its deduplicated metrics.

    Args:
        metrics: Accumulated style metrics (post-deduplication).
        style: Style name, used for name-based rules.
        total: Total deduplicated line count in the file, for the share ratio.

    Returns:
        Tuple of the category and the confidence.
    """
    n = metrics.n
    pos, draw, kara, punct = metrics.pos / n, metrics.draw / n, metrics.kara / n, metrics.punct / n
    avg, frac = metrics.txt / n, metrics.n / total

    # Hard SIGN rules.
    if draw > _DRAW_SIGN_RATIO:
        return Category.SIGN, 0.95
    if kara > _KARA_SONG_RATIO:
        return Category.SIGN, 0.95
    if _RE_SONG.search(style):
        return Category.SIGN, 0.9
    if _RE_NOTE.search(style):
        return Category.SIGN, 0.9

    # Confident dialogue variant with no positioning/drawing -- read it.
    if _RE_DLG.search(style) and pos < _DLG_MAX_POS_RATIO and draw == 0:
        return Category.DIALOG, 0.85

    # Weighted scoring for everything else.
    score = 0.0
    if frac >= _FRAC_DIALOG_MIN:
        score += 0.35
    if pos < _POS_LOW_MAX:
        score += 0.25
    if punct > _PUNCT_MIN:
        score += 0.20
    if avg >= _AVG_TEXT_MIN:
        score += 0.10
    if _RE_DLG.search(style):
        score += 0.15
    if _RE_SIGN.search(style):
        score -= 0.25
    if pos > _POS_HIGH_MIN:
        score -= 0.30

    if score >= _SCORE_DIALOG:
        return Category.DIALOG, round(min(score, 0.99), 2)
    if score <= _SCORE_SIGN:
        return Category.SIGN, round(min(1 - score, 0.95), 2)
    return Category.UNCERTAIN, 0.5
```

Różnice względem `style_classifier.py:171-221` — **wyłącznie** pięć nazw stałych w porównaniach (`0.20→_FRAC_DIALOG_MIN`, `0.40→_POS_LOW_MAX`, `0.30→_PUNCT_MIN`, `12→_AVG_TEXT_MIN`, `0.60→_POS_HIGH_MIN`). Wagi, konfidencje, kolejność reguł, `draw == 0` — bit w bit. `dedup_animation`, `classify_styles`, `Category`, `StyleVerdict`, `_StyleMetrics` i wszystkie regeksy — verbatim.

## Aneks D — implementacje wzorcowe najtrudniejszych funkcji

Poniższy kod jest wykonawczy (nie pseudokod). Agent wkleja i uzupełnia wyłącznie o elementy jawnie oznaczone `(docstring z §...)`.

### D.1 `extraction/service.py` — `extract_tracks` + pomocnicze

```python
def _fail(code: ErrorCode, message: str, suggestion: str) -> ExtractionError:
    """Build an :class:`ExtractionError` with a consistent context."""
    return ExtractionError(
        context=ErrorContext(code=code, message=message, suggestion=suggestion),
    )


def _build_specs(
    info: MediaInfo,
    selection: TrackSelection,
    dest_dir: Path,
) -> list[tuple[int, Path]]:
    """Return ``(track_id, output_path)`` pairs for the requested tracks.

    Raises:
        ExtractionError: When a selected id is absent from the container
            (``ErrorCode.TRACK_NOT_FOUND``).
    """
    by_id = {track.id: track for track in info.tracks}
    specs: list[tuple[int, Path]] = []
    for track_id, stem in ((selection.audio_id, _AUDIO_STEM), (selection.subtitle_id, _SUBS_STEM)):
        if track_id is None:
            continue
        track = by_id.get(track_id)
        if track is None:
            msg = f"{info.path.name}: track {track_id} not present in the container"
            raise _fail(ErrorCode.TRACK_NOT_FOUND, msg, "Re-run — the selection must match mkvmerge output")
        specs.append((track_id, dest_dir / f"{stem}.{format_extension(track.codec_id)}"))
    return specs


def _abort_cancelled(process: Popen[str], specs: list[tuple[int, Path]], source: Path) -> NoReturn:
    """Terminate mkvextract, remove partial outputs and raise CANCELLED."""
    process.terminate()
    process.wait()
    for _track_id, dest in specs:
        dest.unlink(missing_ok=True)
    msg = f"{source.name}: extraction cancelled"
    raise _fail(ErrorCode.CANCELLED, msg, "")


def _validate_outputs(source: Path, specs: list[tuple[int, Path]]) -> None:
    """Verify every requested output exists and is non-empty (N4)."""
    for track_id, dest in specs:
        if dest.is_file() and dest.stat().st_size > 0:
            continue
        msg = f"{source.name}: mkvextract exited 0 but wrote no data for track {track_id}"
        raise _fail(
            ErrorCode.EXTRACTION_FAILED,
            msg,
            "Known mkvextract quirk — check the output path is a valid Windows path",
        )


def extract_tracks(
    info: MediaInfo,
    selection: TrackSelection,
    dest_dir: Path,
    *,
    on_progress: Callable[[int], None] | None = None,
    cancel: threading.Event | None = None,
) -> ExtractionResult:
    """(docstring z §10.4)"""
    specs = _build_specs(info, selection, dest_dir)
    if not specs:
        return ExtractionResult(audio_path=None, subtitle_path=None)
    exe = ensure_binary(Binary.MKVEXTRACT)
    command = [str(exe), "--ui-language", "en", "--gui-mode", str(info.path), "tracks"]
    command += [f"{track_id}:{dest}" for track_id, dest in specs]
    tail: deque[str] = deque(maxlen=_ERROR_TAIL_LINES)
    # Argument list, trusted absolute binary path, no shell involved.
    with Popen(  # noqa: S603
        command,
        stdout=PIPE,
        stderr=STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    ) as process:
        stdout = process.stdout
        if stdout is None:  # pragma: no cover - Popen(stdout=PIPE) guarantees a pipe
            msg = f"{info.path.name}: mkvextract stdout unavailable"
            raise _fail(ErrorCode.EXTRACTION_FAILED, msg, "")
        for line in stdout:
            if cancel is not None and cancel.is_set():
                _abort_cancelled(process, specs, info.path)
            match = _RE_GUI_PROGRESS.match(line)
            if match:
                if on_progress is not None:
                    on_progress(min(100, int(match.group(1))))
                continue
            stripped = line.strip()
            if stripped:
                tail.append(stripped)
    if process.returncode != 0:
        joined = " | ".join(tail) or "no output"
        msg = f"{info.path.name}: mkvextract failed (exit {process.returncode}): {joined}"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg, "Check the MKV is readable and the disk has free space")
    _validate_outputs(info.path, specs)
    if on_progress is not None:
        on_progress(100)
    by_id = dict(specs)
    return ExtractionResult(
        audio_path=by_id.get(selection.audio_id) if selection.audio_id is not None else None,
        subtitle_path=by_id.get(selection.subtitle_id) if selection.subtitle_id is not None else None,
    )
```

Importy tego modułu: `from collections import deque`, `from subprocess import PIPE, STDOUT, Popen`, `import threading`, `from typing import NoReturn` (+ `subprocess.run`/`TimeoutExpired` dla `identify`). Testy monkeypatchują `service.Popen` (import symbolu do modułu, nie `subprocess.Popen` globalnie).

### D.2 `subtitles/service.py` — `collapse_fbf` + rdzeń `split_subtitles` + `write_displayed`

```python
def collapse_fbf(events: Sequence[SSAEvent]) -> tuple[tuple[SpokenLine, ...], int]:
    """(docstring z §11.5)"""
    groups: defaultdict[tuple[str, str], list[SSAEvent]] = defaultdict(list)
    for event in events:
        text = visible_text(event.text)
        if not text:
            continue
        groups[(event.style, text)].append(event)

    lines: list[SpokenLine] = []
    collapsed_away = 0
    for (style, text), group in groups.items():
        group.sort(key=lambda e: (e.start, e.end))
        run_start = group[0].start
        run_end = group[0].end
        run_size = 1
        for event in group[1:]:
            if event.start - run_end <= _FBF_MAX_GAP_MS:
                run_end = max(run_end, event.end)
                run_size += 1
                continue
            lines.append(SpokenLine(start=run_start, end=run_end, text=text, style=style))
            collapsed_away += run_size - 1
            run_start, run_end, run_size = event.start, event.end, 1
        lines.append(SpokenLine(start=run_start, end=run_end, text=text, style=style))
        collapsed_away += run_size - 1

    lines.sort(key=lambda line: (line.start, line.end, line.style, line.text))
    return tuple(lines), collapsed_away


def split_subtitles(
    subs: SSAFile,
    *,
    kind: SubtitleKind,
    spoken_styles: Collection[str] | None = None,
    verdicts: Sequence[StyleVerdict] | None = None,
) -> SubtitleSplit:
    """(docstring z §11.5)"""
    dialogue = [event for event in subs.events if event.type == "Dialogue"]
    if not dialogue:
        return SubtitleSplit(
            kind=kind, subs=subs, decisions=(), verdicts=(), spoken=(),
            stats=SplitStats(0, 0, 0, 0, 0, 0),
        )

    if kind == "srt":
        final_verdicts: tuple[StyleVerdict, ...] = ()
        spoken_set = {event.style for event in dialogue}
    else:
        computed = tuple(verdicts) if verdicts is not None else tuple(classify_styles(subs))
        final_verdicts = computed
        if spoken_styles is not None:
            spoken_set = set(spoken_styles)
        else:
            spoken_set = {v.style for v in computed if v.category is Category.DIALOG}

    decisions: list[Decision] = []
    for event in dialogue:
        if kind == "ass" and is_drawing(event.text):
            decisions.append("displayed")
        elif event.style in spoken_set:
            decisions.append("spoken")
        else:
            decisions.append("displayed")

    drawing_count = sum(1 for event in dialogue if kind == "ass" and is_drawing(event.text))
    if "spoken" not in decisions and drawing_count < len(dialogue):
        decisions = [
            "displayed" if kind == "ass" and is_drawing(event.text) else "spoken"
            for event in dialogue
        ]

    spoken_events = [event for event, decision in zip(dialogue, decisions, strict=True) if decision == "spoken"]
    spoken, collapsed_away = collapse_fbf(spoken_events)
    return SubtitleSplit(
        kind=kind,
        subs=subs,
        decisions=tuple(decisions),
        verdicts=final_verdicts,
        spoken=spoken,
        stats=SplitStats(
            total_events=len(dialogue),
            spoken_events=len(spoken_events),
            spoken_lines=len(spoken),
            displayed_events=len(dialogue) - len(spoken_events),
            drawing_events=drawing_count,
            collapsed_away=collapsed_away,
        ),
    )


def write_displayed(split: SubtitleSplit, dest: Path) -> Path | None:
    """(docstring z §11.5)"""
    if split.stats.displayed_events == 0:
        return None
    out = SSAFile()
    out.info = dict(split.subs.info)
    for name, style in split.subs.styles.items():
        out.styles[name] = style.copy()
    dialogue_index = 0
    for event in split.subs.events:
        if event.type != "Dialogue":
            out.events.append(event)
            continue
        if split.decisions[dialogue_index] == "displayed":
            out.events.append(event)
        dialogue_index += 1
    payload = out.to_string(format_=split.kind)
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        tmp.write_text(payload, encoding=_ENCODING)
        tmp.replace(dest)
    except OSError as exc:
        msg = f"{dest.name}: cannot write the displayed product: {exc}"
        raise SubtitleError(
            context=ErrorContext(code=ErrorCode.IO_ERROR, message=msg,
                                 suggestion="Check disk space and permissions"),
        ) from exc
    return dest
```

Uwagi: `zip(..., strict=True)` — długości list są niezmiennikiem; `event.style in spoken_set` dla SRT obejmuje wszystko (zbiór budowany ze wszystkich stylów) — jeden code path decyzji. Fallback E12 liczy `drawing_count < len(dialogue)` (jest co czytać poza rysunkami). `out.info = dict(...)` — kopia płytka wystarcza (wartości to stringi).

### D.3 `pipeline/runner.py` — `_process_mkv` (wzorzec „step-variable", płaski)

```python
def _process_mkv(
    mkv: Path,
    workspace_root: Path,
    *,
    interaction: PipelineInteraction | None,
    on_progress: Callable[[int], None] | None,
    cancel: threading.Event,
) -> FileOutcome:
    """(docstring z §12.2)"""
    warnings: list[str] = []
    step: StepName = "identify"
    try:
        work_dir = workspace_root / _TMP_DIR_NAME / mkv.stem
        if work_dir.exists():
            safe_rmtree(work_dir)
        work_dir.mkdir(parents=True)
        info = identify(mkv)

        step = "select"
        selection = select_tracks(info.tracks)
        if interaction is not None:
            selection = interaction.choose_tracks(info, selection)
        selection = _drop_unusable_subtitles(info, selection, warnings)
        if selection.audio_id is None:
            warnings.append("no audio track")
        if selection.audio_id is None and selection.subtitle_id is None:
            return FileOutcome(source=mkv, status="done", warnings=tuple(warnings))

        step = "extract"
        extracted = extract_tracks(info, selection, work_dir, on_progress=on_progress, cancel=cancel)

        displayed_path: Path | None = None
        split: SubtitleSplit | None = None
        if extracted.subtitle_path is not None:
            step = "split"
            split = _split_extracted(extracted.subtitle_path, mkv, interaction)
            if split.stats.total_events == 0:
                warnings.append("subtitles contain no dialogue events")
            step = "write"
            dest = workspace_root / f"{mkv.stem}{_DISPLAYED_INFIX}.{split.kind}"
            displayed_path = write_displayed(split, dest)
    except AniShiftError as exc:
        if exc.context.code is ErrorCode.CANCELLED:
            return FileOutcome(source=mkv, status="cancelled", warnings=tuple(warnings))
        return _failed_outcome(mkv, step, exc.context, warnings)
    except OSError as exc:
        context = ErrorContext(code=ErrorCode.IO_ERROR, message=str(exc),
                               suggestion="Check disk space and permissions")
        return _failed_outcome(mkv, step, context, warnings)

    stats = split.stats if split is not None else None
    return FileOutcome(
        source=mkv,
        status="done",
        audio_path=extracted.audio_path,
        subtitle_path=extracted.subtitle_path,
        displayed_path=displayed_path,
        already_polish=selection.already_polish,
        spoken_lines=stats.spoken_lines if stats else 0,
        displayed_events=stats.displayed_events if stats else 0,
        drawing_events=stats.drawing_events if stats else 0,
        collapsed_away=stats.collapsed_away if stats else 0,
        warnings=tuple(warnings),
    )
```

Pomocnicze (w tym samym pliku): `_drop_unusable_subtitles(info, selection, warnings)` — krok 4 z §12.2 (kodek nie-tekstowy → warning + `dataclasses.replace(selection, subtitle_id=None, already_polish=False)`; brak napisów w ogóle → warning „no usable subtitles — later stages will skip this file"); `_split_extracted(path, mkv, interaction)` — `subtitle_kind` + `load_subtitles` + (manual: `preview_styles` → `interaction.choose_spoken_styles`) + `split_subtitles`; `_failed_outcome(mkv, step, context, warnings)` — mapuje `ErrorContext` → `FileFailure(step, str(context.code), context.message, context.suggestion)`.

### D.4 `cli/pipeline_ui.py` — `_ManualInteraction`

```python
class _ManualInteraction:
    """Manual-mode prompts: track override and spoken-style selection."""

    def choose_tracks(self, info: MediaInfo, proposal: TrackSelection) -> TrackSelection:
        """Render the track table and let the user confirm or override ids."""
        console.print(f"[bold]{info.path.name}[/bold]")
        console.print("[warning]ID  TYPE        CODEC                 LANG   NAME[/warning]")
        for track in info.tracks:
            console.print(
                f"[warning]{track.id:2}[/warning]  [bold]{track.type:10}[/bold]  "
                f"{track.codec_id:20}  {track.language:5}  {track.name}",
            )
        audio_id = self._ask_track(info, "audio", proposal.audio_id)
        subtitle_id = self._ask_track(info, "subtitles", proposal.subtitle_id)
        chosen = next((t for t in info.tracks if t.id == subtitle_id), None)
        already_polish = chosen is not None and is_polish(chosen.language)
        return TrackSelection(audio_id=audio_id, subtitle_id=subtitle_id, already_polish=already_polish)

    def _ask_track(self, info: MediaInfo, track_type: str, proposal: int | None) -> int | None:
        """Prompt for one track id; Enter accepts the proposal, '-' means none."""
        valid = {t.id for t in info.tracks if t.type == track_type}
        label = "none" if proposal is None else str(proposal)
        while True:
            console.print(f"{track_type} track id [{label}] ('-' = none): ", end="")
            raw = input().strip()
            if not raw:
                return proposal
            if raw == "-":
                return None
            if raw.isdigit() and int(raw) in valid:
                return int(raw)
            console.print(f"[error]Invalid id[/error] — pick one of: {sorted(valid) or 'none'}")

    def choose_spoken_styles(
        self,
        source: Path,
        verdicts: Sequence[StyleVerdict],
        samples: Mapping[str, tuple[str, ...]],
    ) -> set[str] | None:
        """Show verdicts with line counts and samples; Enter accepts them."""
        console.print(f"[bold]{source.name}[/bold] — styles:")
        for index, verdict in enumerate(verdicts, start=1):
            note = (
                f", animation {verdict.raw_line_count}->{verdict.line_count}"
                if verdict.raw_line_count > verdict.line_count
                else ""
            )
            console.print(
                f"  [info]{index}.[/info] [bold]{verdict.style}[/bold] — {verdict.category.value} "
                f"({verdict.confidence:.0%}, {verdict.line_count} lines{note})",
            )
            for sample in samples.get(verdict.style, ()):
                console.print(f"       [gray]{sample}[/gray]")
        while True:
            console.print("Styles to speak [Enter = accept classifier]: ", end="")
            raw = input().strip()
            if not raw:
                return None
            tokens = raw.split()
            if all(token.isdigit() and 1 <= int(token) <= len(verdicts) for token in tokens):
                return {verdicts[int(token) - 1].style for token in tokens}
            console.print(f"[error]Invalid selection[/error] — numbers 1..{len(verdicts)} separated by spaces")
```

`is_polish(language)` — publiczny mały helper w `extraction/tracks.py` (`return language.lower() in _POLISH_LANGS`), użyty w `select_tracks` i tutaj (jedna definicja polskości — §13.1).

### D.5 `extraction/service.py` — `identify` + `parse_media_info`

```python
def identify(path: Path) -> MediaInfo:
    """(docstring z §10.4)"""
    exe = ensure_binary(Binary.MKVMERGE)
    command = [str(exe), "--ui-language", "en", "-J", str(path)]
    try:
        # Argument list, trusted absolute binary path, no shell involved.
        completed = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_IDENTIFY_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"{path.name}: mkvmerge -J timed out after {_IDENTIFY_TIMEOUT_S:.0f}s"
        raise _fail(ErrorCode.TIMEOUT, msg, "Check the drive is responsive, then retry") from exc
    except OSError as exc:
        msg = f"{path.name}: cannot run mkvmerge: {exc}"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg, "Re-run `anishift setup`") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        msg = f"{path.name}: mkvmerge -J failed (exit {completed.returncode}): {detail}"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg, "Check the file is a readable MKV")
    return parse_media_info(path, completed.stdout)


def parse_media_info(path: Path, payload: str) -> MediaInfo:
    """(docstring z §10.4)"""
    try:
        data = json.loads(payload)
    except ValueError as exc:
        msg = f"{path.name}: mkvmerge -J returned invalid JSON"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg, "Retry; report a bug if it persists") from exc
    container = data.get("container", {})
    if not (container.get("recognized") and container.get("supported")):
        msg = f"{path.name}: not a supported Matroska file"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg, "Only MKV containers are processed")
    tracks = [_parse_track(path, raw) for raw in data.get("tracks", [])]
    tracks.sort(key=lambda track: track.id)
    return MediaInfo(path=path, tracks=tuple(tracks))


def _parse_track(path: Path, raw: dict[str, Any]) -> TrackInfo:
    """Parse one mkvmerge track object into a :class:`TrackInfo`."""
    try:
        properties = raw.get("properties", {})
        entries = properties.get("num_index_entries")
        return TrackInfo(
            id=int(raw["id"]),
            type=str(raw.get("type", "")),
            codec_id=str(properties.get("codec_id", "")),
            language=str(properties.get("language", "")),
            language_ietf=str(properties.get("language_ietf", "")),
            name=str(properties.get("track_name", "")),
            default=bool(properties.get("default_track", False)),
            num_entries=int(entries) if entries is not None else None,
        )
    except KeyError as exc:
        msg = f"{path.name}: malformed track entry in identify output"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg, "Retry; report a bug if it persists") from exc
    except TypeError as exc:
        msg = f"{path.name}: malformed track entry in identify output"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg, "Retry; report a bug if it persists") from exc
    except ValueError as exc:
        msg = f"{path.name}: malformed track entry in identify output"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg, "Retry; report a bug if it persists") from exc
```

Trzy bliźniacze bloki `except` zamiast `except (KeyError, TypeError, ValueError)` — to nie stylistyka, to obejście buga ruff 0.15.21 format (psuje `except (A, B):` na niepoprawne `except A, B:`). Nie scalać.

### D.6 `subtitles/service.py` — `load_subtitles` + `preview_styles`; `subtitles/txt.py` — `txt_to_spoken`

```python
def _fail(message: str, suggestion: str) -> SubtitleError:
    """Build a :class:`SubtitleError` with a parse-failure context."""
    return SubtitleError(
        context=ErrorContext(code=ErrorCode.SUBTITLE_PARSE_FAILED, message=message, suggestion=suggestion),
    )


def load_subtitles(path: Path) -> SSAFile:
    """(docstring z §11.5)"""
    try:
        return pysubs2.load(str(path), encoding=_ENCODING)
    except FileNotFoundError as exc:
        msg = f"{path.name}: subtitle file not found"
        raise _fail(msg, "The extraction should have produced it — re-run the pipeline") from exc
    except UnicodeDecodeError as exc:
        msg = f"{path.name}: subtitle file is not UTF-8"
        raise _fail(msg, "Convert the subtitles to UTF-8 and retry") from exc
    except OSError as exc:
        msg = f"{path.name}: cannot read subtitle file: {exc}"
        raise _fail(msg, "Check file permissions") from exc
    except Pysubs2Error as exc:
        msg = f"{path.name}: subtitle file cannot be parsed: {exc}"
        raise _fail(msg, "The file may be corrupt — check it plays in a video player") from exc


def preview_styles(subs: SSAFile) -> tuple[tuple[StyleVerdict, ...], dict[str, tuple[str, ...]]]:
    """(docstring z §11.5)"""
    verdicts = tuple(classify_styles(subs))
    collected: dict[str, list[str]] = {verdict.style: [] for verdict in verdicts}
    for event in subs.events:
        if event.type != "Dialogue" or is_drawing(event.text):
            continue
        bucket = collected.get(event.style)
        if bucket is None or len(bucket) >= _SAMPLES_PER_STYLE:
            continue
        text = visible_text(event.text)
        if not text or text in bucket:
            continue
        if len(text) > _SAMPLE_MAX_CHARS:
            text = text[: _SAMPLE_MAX_CHARS - 1] + "…"
        bucket.append(text)
    samples = {style: tuple(bucket) for style, bucket in collected.items()}
    return verdicts, samples
```

(`Pysubs2Error` — import `from pysubs2.exceptions import Pysubs2Error`; to wspólna baza błędów formatu w pysubs2 1.8.x — zweryfikować nazwę w zainstalowanej wersji przy implementacji; jeśli inna, użyć faktycznej bazy z `pysubs2.exceptions`, nic więcej nie zmieniając.)

```python
def txt_to_spoken(path: Path, *, max_chars: int = _MAX_CHUNK_CHARS) -> tuple[SpokenLine, ...]:
    """(docstring z §11.7)"""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        msg = f"{path.name}: text file not found"
        raise _fail(msg, "Check the file still exists in workspace/") from exc
    except UnicodeDecodeError as exc:
        msg = f"{path.name}: text file is not UTF-8"
        raise _fail(msg, "Save the file as UTF-8 and retry") from exc
    except OSError as exc:
        msg = f"{path.name}: cannot read text file: {exc}"
        raise _fail(msg, "Check file permissions") from exc
    text = _RE_SPACES.sub(" ", raw).strip()
    if not text:
        return ()
    chunks: list[str] = []
    current = ""
    for sentence in _RE_SENTENCE_END.split(text):
        for piece in _word_pieces(sentence, max_chars):
            if not current:
                current = piece
            elif len(current) + 1 + len(piece) <= max_chars:
                current = f"{current} {piece}"
            else:
                chunks.append(current)
                current = piece
    if current:
        chunks.append(current)
    return tuple(SpokenLine(start=0, end=0, text=chunk, style="") for chunk in chunks)


def _word_pieces(sentence: str, max_chars: int) -> list[str]:
    """Split an oversized sentence on word boundaries; short ones pass through."""
    if len(sentence) <= max_chars:
        return [sentence]
    pieces: list[str] = []
    current = ""
    for word in sentence.split():
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current = f"{current} {word}"
        else:
            pieces.append(current)
            current = word
    if current:
        pieces.append(current)
    return pieces
```

`txt.py` ma **własne** `_fail` (bliźniacze do serwisowego — moduły domeny nie współdzielą prywatnych helperów między plikami) i **własną** stałą `_RE_SPACES` (identyczny wzorzec `r"\s+"`, z docstringiem) — 2 linie duplikacji zamiast eksportowania prywatnej stałej z `text.py` albo wołania `visible_text` (tekst `.txt` nie ma tagów do zdejmowania).

### D.7 `pipeline/runner.py` — `run_pipeline` + równoległość

```python
def run_pipeline(
    context: AppContext,
    *,
    interaction: PipelineInteraction | None = None,
    progress: ProgressReporter | None = None,
) -> PipelineReport:
    """(docstring z §12.2)"""
    ensure_workspace_dir(context.workspace_root)
    files = discover_inputs(context.workspace_root)
    if not files:
        return PipelineReport(outcomes=())
    mkvs = [path for path in files if path.suffix.lower() == _MKV_SUFFIX]
    txts = [path for path in files if path.suffix.lower() == _TXT_SUFFIX]
    cancel = threading.Event()
    outcomes: dict[Path, FileOutcome] = {}
    if interaction is not None:
        for mkv in mkvs:
            outcomes[mkv] = _process_mkv(
                mkv, context.workspace_root, interaction=interaction, on_progress=None, cancel=cancel,
            )
    elif mkvs:
        outcomes.update(_process_parallel(mkvs, context.workspace_root, progress=progress, cancel=cancel))
    for txt in txts:
        outcomes[txt] = _process_txt(txt)
    return PipelineReport(outcomes=tuple(outcomes[path] for path in files))


def _process_parallel(
    mkvs: Sequence[Path],
    workspace_root: Path,
    *,
    progress: ProgressReporter | None,
    cancel: threading.Event,
) -> dict[Path, FileOutcome]:
    """Process MKVs in parallel; Ctrl+C flips *cancel* and drains the workers."""
    task_ids: dict[Path, int] = {}
    if progress is not None:
        for mkv in mkvs:
            task_ids[mkv] = progress.add_task(mkv.name)
    futures: dict[Path, Future[FileOutcome]] = {}
    with ThreadPoolExecutor(max_workers=_worker_count(len(mkvs))) as pool:
        for mkv in mkvs:
            futures[mkv] = pool.submit(
                _process_mkv,
                mkv,
                workspace_root,
                interaction=None,
                on_progress=_progress_callback(progress, task_ids.get(mkv)),
                cancel=cancel,
            )
        pending = set(futures.values())
        try:
            while pending:
                _done, pending = wait(pending, timeout=_WAIT_POLL_SECONDS)
        except KeyboardInterrupt:
            cancel.set()
            wait(set(futures.values()))
    return {mkv: future.result() for mkv, future in futures.items()}


def _progress_callback(progress: ProgressReporter | None, task_id: int | None) -> Callable[[int], None] | None:
    """Bind one task id to the reporter; None reporter means no callback."""
    if progress is None or task_id is None:
        return None

    def _update(percent: int) -> None:
        progress.update(task_id, percent)

    return _update
```

`future.result()` na końcu **celowo bez try** — `_process_mkv` mapuje wszystkie błędy domenowe i `OSError` na `FileOutcome` w środku (D.3); to, co tu wyleci, jest bugiem programisty i MA wywrócić przebieg głośno (fail loud, §12.2 krok 6). Zamknięcie `_progress_callback` wiąże `task_id` przez argument funkcji — eliminuje pułapkę late-binding domknięć w pętli.

## Aneks E — syntetyczna fixtura ASS do testów splitu i klasyfikatora

Helper modułowy w `tests/test_subtitles_split.py` (i bliźniaczo w `test_subtitles_classifier.py` — bez współdzielenia przez conftest, pliki testowe są samowystarczalne wzorem repo):

```python
_ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{styles}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{events}
"""

_STYLE_ROW = (
    "Style: {name},Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
    "0,0,0,0,100,100,0,0,1,2,1,2,10,10,10,1"
)


def _ass(styles: list[str], events: list[str]) -> SSAFile:
    """Build an in-memory ASS file from style names and Dialogue rows."""
    payload = _ASS_HEADER.format(
        styles="\n".join(_STYLE_ROW.format(name=name) for name in styles),
        events="\n".join(events),
    )
    return SSAFile.from_string(payload)


def _row(start: str, end: str, style: str, text: str) -> str:
    """Build one Dialogue row."""
    return f"Dialogue: 0,{start},{end},{style},,0,0,0,,{text}"
```

Fixtura kanoniczna dla `test_drawings_always_go_to_displayed` / `test_uncertain_style_goes_to_displayed` / fallbacku E12 (wartości oczekiwane policzone z reguł klasyfikatora — agent NIE zmienia eventów, bo werdykty są od nich zależne):

```python
_MIXED = _ass(
    ["Default", "Znaki"],
    [
        # 24 dialogue rows: frac >= 0.20, no positioning, punctuation-rich,
        # avg length >= 12 -> score 0.90 -> DIALOG.
        *[
            _row(f"0:00:{sec:02d}.00", f"0:00:{sec + 1:02d}.50", "Default",
                 f"This is a long spoken sentence number {sec}.")
            for sec in range(0, 48, 2)
        ],
        # A drawing INSIDE the dialog style: must still be displayed (R6a).
        _row("0:00:50.00", "0:00:52.00", "Default", "{\\p1}m 0 0 l 100 0 100 100"),
        # FBF run in Znaki: same text, 5 frames back to back.
        *[
            _row(f"0:01:00.{cs:02d}", f"0:01:00.{cs + 4:02d}", "Znaki", "{\\pos(10,10)}SCHOOL GATE")
            for cs in range(0, 20, 4)
        ],
    ],
)
```

Oczekiwania: `Default` → DIALOG (spoken 24 linie), rysunek → displayed mimo stylu DIALOG, `Znaki` (pos-ratio 100% > 0.60, nazwa `_RE_SIGN` łapie „znak") → SIGN → displayed w komplecie (5 eventów w produkcie), collapse na spoken nie scala nic (różne teksty). Format czasu pysubs2: `H:MM:SS.cs` (centysekundy!) — `0:01:00.04` = 60.04 s; odstępy w runie FBF = 0 ms.

## Aneks F — mock-up raportu w konsoli (wzorzec renderu §13.1)

Auto, workspace z 2 plikami OK i 1 błędem (ikony wg `get_status_icon`; kolory pominięte w mock-upie):

```
✓ [shisha] Youjo Senki II - 01.mkv  spoken 348 · displayed 96 · drawings 41 · collapsed 210  (already Polish)
    -> workspace/[shisha] Youjo Senki II - 01.displayed.ass
✓ [SubsPlease] Mushoku Tensei S3 - 03 (1080p) [8488B15C].mkv  spoken 412 · displayed 63 · drawings 12 · collapsed 88
    -> workspace/[SubsPlease] Mushoku Tensei S3 - 03 (1080p) [8488B15C].displayed.ass
✗ broken-episode.mkv  [extract] broken-episode.mkv: mkvextract failed (exit 2): Error: ...
    -> Check the MKV is readable and the disk has free space
Done 2 · Failed 1 · Cancelled 0
```

Liczby w mock-upie są ilustracyjne; format linii jest wiążący. Warning renderowany między linią pliku a stopką: `⚠ episode.mkv: no usable subtitles — later stages will skip this file`.

## Aneks G — checklist antywzorców + komunikaty commitów

### G.1 Antywzorce (sprawdzać przy self-review i w PR)

- ⛔ Przypisanie do `event.plaintext` lub `event.text` gdziekolwiek w `anishift/` (grep przed PR: `\.plaintext\s*=` i `\.text\s*=` — dozwolone zero trafień poza testami).
- ⛔ Zmiana jakiejkolwiek wagi/progu/regexa klasyfikatora poza pięcioma nazwami z I5 (diff `classifier.py` vs `style_classifier.py` obejrzany linia po linii).
- ⛔ Port `read(1)` (`mkvtoolnix.py:299-331`), portu równoległego manuala, cache >1 KB (`:254`), `sys.exit()` (`:88,114`), `input()` w serwisach.
- ⛔ `engines/` w `extraction`/`subtitles`; nowe klasy błędów w `anishift/errors.py`; nowe pola w `AppContext`; nowe podkatalogi w `DEFAULT_SUBDIRS`.
- ⛔ `except Exception`/`except (A, B):` (BLE001 + bug ruff-format — zawsze osobne bloki), `print()` (T20), inline message w `raise` (TRY003 — `msg` do zmiennej).
- ⛔ `uv add`/`uv remove` — etap 3 niczego nie dodaje; ręczna edycja `pyproject.toml` zakazana zawsze.
- ⛔ Import `scripts/tmp/*` (chunker z bugami), import `utils.logger` (OFF), import `rich_console` w serwisach/runnerze.
- ⛔ Docstringi z historią/uzasadnieniami („changed because", „previously", procenty walidacji) — uzasadnienia żyją w TYM planie.
- ⛔ Emoji w wyjściu konsoli i w kodzie.
- ⛔ Rekonstrukcja ASS z SRT; stan wznowienia; strojenie heurystyki; jakikolwiek plik `spoken.*` na dysku.

### G.2 Sugerowane komunikaty commitów (Conventional Commits, granulacja = kroki §6/§15)

Część I: `feat(utils): per-task style field in progress columns` → `feat(utils): MultiProgressManager for multi-file progress` → `test: multi-task progress manager`.

Część II (kolejność kroków §15): `feat(extraction): domain skeleton and typed track model` → `feat(extraction): port track selector with typed wrapper` → `test: track selector parity and 206-file regression` → `feat(subtitles): tag-safe text operations` → `feat(extraction): identify and gui-mode extraction service` → `feat(subtitles): port style classifier` → `feat(subtitles): per-line split, FBF collapse and displayed writer` → `test: classifier regression against 182-file ground truth` → `feat(subtitles): plain-text to narrator lines` → `feat(pipeline): runner with per-file isolation and cancel` → `feat(cli): Enter runs the pipeline with multi-bar progress` → `chore: measure parallel extraction cap` → `test: smoke pipeline on real MKVs` → `chore: split measurement script`.

---

Koniec planu. Wymagania → `docs/plans/etap-3-wymagania.md`; mapa repo → `docs/reference/stan-repo.md`. Przy każdej sprzeczności między tym planem a kodem źródłowym mm_avh w kwestii portowanych wartości: **KOD mm_avh > plan** (wartości portu mają być bit w bit; plan cytuje je wtórnie).

# Etap 9.5 — plan implementacji: TUI w gramatyce wizualnej OpenCode

> Status: READY.
> Baseline: `6849f32d4b197aff3507266e55f3d7fbb5c674d4`, branch `feature/stage-9-product-tui`.
> Wymagania: [`etap-9.5-tui-opencode-wymagania.md`](etap-9.5-tui-opencode-wymagania.md)
> (identyfikatory `R-*`, `I-*`, `AC-*`, `Z-*` odnoszą się do tego dokumentu).
> Kontrakty nadrzędne: [`etap-9-wymagania.md`](etap-9-wymagania.md),
> [`etap-9-interfejs-wymagania.md`](etap-9-interfejs-wymagania.md),
> [`etap-9-plan.md`](etap-9-plan.md) (kroki 16–18 przejęte częściowo — patrz wymagania §1.3).
> Issue: [#38](https://github.com/MattyMroz/AniShift/issues/38) — 9.5 domyka część TUI;
> pozostałość (real-media E2E, load, CI E2E, zamknięcie issue) zostaje w Etapie 9.
> Wzornik: klon OpenCode 1.18.21 (`3a31c4e`), ścieżki cytowane względem
> `packages/tui/src/`. Kod referencyjny czytamy, nigdy nie linkujemy jako zależności.
> Kod pisany według skilli `simple` oraz standardów `AGENTS.md`; skille `python`
> i `instructions` przywoływane w `AGENTS.md` nie istnieją w repo na baseline —
> obowiązuje sekcja „Python" root `AGENTS.md` i reguły ruff/mypy.

## 1. Zasady realizacji (plan-specific)

- Każda faza kończy się działającym repo i pełnymi zielonymi bramkami:
  `uv run ruff check anishift/ tests/`, `uv run ruff format --check anishift/ tests/`,
  `uv run mypy anishift/ tests/`, `uv run pytest`. Zawsze na `anishift/ tests/`,
  nigdy na podkatalogu.
- Baseline testów: pełne `uv run pytest` = exit 0 (2034 passed / 8 skipped,
  zweryfikowane na `6849f32`). Testy legacy TUI/CLI wolno kasować wyłącznie w tym samym
  commicie, który zastępuje ich zachowanie nowymi testami albo usuwa testowany kod
  (F7). Liczba testów `tests/tui/` po F8 ≥ 29.
- `anishift/application/` jest w tym etapie **read-only** (wyjątek: nowy
  `tests/application/test_legacy_parity.py` w F7 — sam test, zero zmian produkcyjnych).
  Wyjątek drugi: `anishift/config/field_access.py` (D-6) to nowy moduł w `config/`,
  nie w `application/`.
- Nowe pliki produkcyjne ≤ ~400 linii. Zero nowych zależności (`textual`, `rich`,
  `typer` już są; fuzzy z `textual.fuzzy` — D-5). Jedyne operacje na zależnościach:
  `uv remove prompt-toolkit` w F7.
- Stary kod `anishift/tui/` żyje do momentu, w którym faza zastępuje jego konsumentów;
  nie utrzymujemy dwóch wersji tego samego ekranu dłużej niż jedną fazę.
- Rutynowa walidacja TUI przez `App.run_test()` + `Pilot`; ręczne klikanie nie jest
  kryterium ukończenia poza dwiema jawnymi bramkami HITL (AC-HITL-1 po F4,
  AC-HITL-2 w F7).
- Zero placeholderów na produkcji w żadnym momencie po F4 (I-3): faza nie zostawia
  ekranu-atrapy; jeśli ekran nie jest jeszcze przepisany, działa jego stara wersja.
- Kolory (hex) wolno wpisywać wyłącznie w `anishift/tui/theme.py` (I-2); strażnik
  AC-101 powstaje w F1, zanim powstanie pierwszy nowy `.tcss`.
- Komunikaty błędów UI: bez sekretów, pełnych ustawień, promptów, tekstów napisów/TTS
  i ścieżek absolutnych (I-7); używać `sanitize_event_message` z `application/events.py`
  tam, gdzie renderowane są zdarzenia.
- Commity `typ(scope): opis`; scope dla TUI to `cli` (lista w
  `scripts/hooks/check_commit_msg.py:37-58` nie zawiera `tui`; nie zmieniamy hooka bez
  zgody użytkownika — D-12). Zero śladów AI w commitach i PR.

## 2. Current State / Gap

| Obszar | Stan aktualny (zweryfikowany na baseline) | Stan wymagany (R-*) | Akcja |
|---|---|---|---|
| motyw / tokeny | zero `register_theme`/`App.theme`; `theme.tcss` 156 linii z 17 hexami; zero zmiennych `$...` | R-101–R-105: moduł palety, 2 motywy, 8 zmiennych własnych, zakaz hexów poza paletą | F1: `theme.py` + `styles/` + strażnik AC-101 |
| markery stanu | stany różnicowane wyłącznie kolorem (`theme.tcss:88-94`); brak spinnera, brak glifów | R-106: tabela glif+słowo+token; spinner braille | F1: moduł `icons` + AC-103 |
| skróty klawiszowe | **zero** `BINDINGS` w całym `anishift/tui/` | R-309: mapa globalna + per ekran; stopka z żywej keymapy | F3–F5: `BINDINGS` na App i każdym ekranie |
| dialogi | brak jakiegokolwiek dialogu; wybory przez `Select`/`Button` w formularzach | R-201–R-210: `SelectDialog` + 4 prymitywy, zasłona, szerokości 60/88/116 | F2: pakiet `dialogs/` |
| komendy | `commands.py` (41 linii): 7 komend, płaski enum, zero kategorii/predykatów/aliasów; brak palety | R-301–R-308: rejestr z predykatami, paleta ctrl+p, slash z fuzzy ×5 | F3: pakiet `commands/` + command bar v2 |
| ekran ustawień | `screens/settings.py` (189): jeden scroll 58 pól, debug-join dostępności (`:53-58`), draft+Save | R-401–R-410: drzewo dialogów, instant apply, 10 typów pól, sekrety read-only | F6: pakiet `settings/`; kasacja ekranu (Z-1/Z-2) |
| ekrany główne | placeholder na produkcji (`screens/base.py:34`); `execution.py` 52 linie szkieletu; StatusFooter = string z pipe'ami (`widgets/command_bar.py`) | R-501–R-504, R-112: pełne ekrany w gramatyce OpenCode | F4–F5: przepisanie wszystkich ekranów |
| entrypoint | `anishift` → `run_shell(bootstrap())` (`cli/main.py:53`); `run --preset` usunięty revertem `6849f32`; implementacja istnieje w `ed589c5` | AC-802: default TUI, `run --preset`, doctor/setup bez Textual | F7: przywrócenie z `ed589c5` po bramce HITL |
| kodowanie | `doctor` na cp1250 → `UnicodeEncodeError` (`cli/main.py:40-41` + ikony emoji w `utils/rich_console`); `run_anishift.bat` maskuje przez `chcp 65001` | R-701–R-704: reconfigure UTF-8 na granicy, check doctor, test cp1250 | F1: pierwszy krok etapu |
| legacy | REPL + panel + `anishift/pipeline/` (13 plików) + `tests/pipeline/` (10 plików) + `prompt-toolkit` działają równolegle | wymagania §3.2: usunięte po parytecie | F7: parity test → HITL → kasacja |
| testy TUI | 29 testów Pilot w 10 plikach na stare ekrany | AC-2xx–AC-5xx; liczba ≥ 29 | F2–F8: wymiana per faza |
| `config/presets.json` | dane użytkownika nieśledzone, nie w `.gitignore` (gitignored jest tylko `settings.json` — `.gitignore:291`) | czysty `git status` | F1: dopisanie do `.gitignore` |

## 3. Impact scan

- **Kontrakty publiczne bez zmian:** `AppService` (wszystkie metody z
  `application/service.py:131-327` wystarczają — zweryfikowano pokrycie potrzeb TUI:
  discover, register_external_*, presety, plan_auto/manual, execute/cancel,
  settings_catalog(draft)/snapshot/save, engine_availability, environment_statuses,
  doctor, setup). `setting_catalog(context)`, `RunEvent`/`EventBuffer`, `RunResult` —
  bez zmian.
- **Zagrożone testy:** `tests/tui/` (29 — wymieniane per faza); `tests/cli/test_main.py`
  (F7: default TUI); `tests/cli/{test_banner,test_commands,test_completer,
  test_compose_command,test_pipeline_ui,test_settings_panel,test_tts_settings}.py`
  i cały `tests/pipeline/` (F7: kasacja z legacy). Testy `tests/application/`,
  `tests/services/`, `tests/config/` — nietykane (poza nowym parity testem).
- **Test architektury** `tests/application/test_architecture.py` pilnuje kierunku
  importów — nowe moduły TUI nie mogą go złamać (TUI → tylko publiczna fasada
  `anishift.application`).
- **Konsumenci `anishift/tui/`:** wyłącznie `ed589c5` (launch_tui) — obecnie martwy
  import; nikt inny nie importuje TUI (grep). Konsumenci legacy CLI: `cli/main.py`
  (`run_shell`), testy legacy. Brak innych call sites.
- **Pułapka testowa:** `tests/` nie dostaje żadnego nowego `__init__.py`
  (pułapka conftest — `tests/AGENTS.md`); testy bez docstringów i komentarzy
  (hook `check_test_comments.py`).
- **Kolizje workstreamów:** brak — branch jest jedynym aktywnym; nieśledzone
  `docs/PROCESS.md` i `docs/workflow.txt` to notatki użytkownika, nie dotykamy.
- **`run_anishift.bat`:** bez zmian (`chcp 65001` + delegacja); po F7 bez argumentów
  otwiera TUI przez nowy entrypoint.

## 4. Technical Design — decyzje

### D-1. Struktura nowego `anishift/tui/` — przepisanie w miejscu, pakietami

Nowe TUI powstaje w tej samej ścieżce pakietu, w podpakietach o jednej
odpowiedzialności (każdy plik ≤ ~400 linii):

```text
anishift/tui/
├── AGENTS.md                    ZMIANA — granice + nowe konwencje (F8)
├── CLAUDE.md                    bez zmian (@AGENTS.md)
├── __init__.py                  eksport: AniShiftApp
├── app.py                       AniShiftApp: routing, globalne BINDINGS, timery,
│                                drenaż EventBuffer, bramka generacji (D-10)
├── theme.py                     JEDYNY właściciel hexów: tokeny, anishift-dark/-light,
│                                register_theme, get_theme_variable_defaults (D-2)
├── ui_state.py                  odczyt/zapis config/ui_state.json (motyw; D-7)
├── icons.py                     tabela R-106: glify, słowa, spinner braille
├── state.py                     SessionState, GroupIntentDraft, AutoPresetDraft-praca
├── messages.py                  typowane Message: CommandSubmitted, RunEventsReceived,
│                                RunCompleted, RunFailed, SettingsChanged
├── styles/
│   ├── base.tcss                layout aplikacji, command bar, status footer
│   ├── dialogs.tcss             zasłona, panel, filtr, wiersze, stopka akcji
│   └── screens.tcss             panele ekranów, tabele, nagłówki
├── commands/
│   ├── __init__.py
│   ├── spec.py                  CommandSpec (R-301) — frozen dataclass
│   ├── registry.py              CommandRegistry: register/unregister/dispatch,
│   │                            zapytania dla palety i slasha
│   ├── fuzzy.py                 rank_commands(): FuzzySearch + 5 reguł R-308
│   └── palette.py               open_palette(): SelectDialog nad rejestrem + Suggested
├── dialogs/
│   ├── __init__.py
│   ├── base.py                  DialogScreen(ModalScreen[T]): zasłona $overlay,
│   │                            panel $panel bez ramki, szerokości 60/88/116,
│   │                            top = height // 4, escape/ctrl+c, refocus
│   ├── select.py                SelectDialog (R-202–R-208): filtr, kategorie, ●,
│   │                            akcje stopki, multi, on_move, initial_highlight
│   ├── prompt.py                PromptDialog (R-209)
│   ├── number.py                NumberDialog (R-209)
│   ├── confirm.py               ConfirmDialog (R-209)
│   └── reorder.py               ReorderDialog (R-209)
├── settings/
│   ├── __init__.py
│   ├── tree.py                  korzeń: kategorie R-403, wiersze wartości,
│   │                            pętla nawigacji replace+initial_highlight (R-407)
│   └── editors.py               dispatch SettingSpec → dialog (R-405), zapis
│                                natychmiastowy przez AppService (R-408), sekrety R-409
├── screens/
│   ├── __init__.py
│   ├── workspace.py             tabela grup, zaznaczanie, konflikty, logo
│   ├── auto.py                  edytor presetu (pola AUTO_PRESET przez settings/editors)
│   ├── manual.py                lista grup + formularz intencji (pola MANUAL_RUN j.w.)
│   ├── preview.py               plan, nadpisania, koszty, Start z potwierdzeniem
│   ├── execution.py             wiersz per grupa, szczegóły, retry/fallback, cancel
│   ├── results.py               statusy terminalne, produkty, akcja „to Manual"
│   └── tools.py                 doctor + setup w workerze
└── widgets/
    ├── __init__.py
    ├── command_bar.py           ❯ + popup slash (R-305–R-306)
    ├── status_footer.py         segmenty + skróty z żywych BINDINGS (R-502)
    ├── group_table.py           DataTable grup ze stabilnymi kluczami
    ├── plan_view.py             lista operacji planu per grupa
    └── progress_table.py        wiersze wykonania + spinner
```

Stare pliki (`commands.py`, `theme.tcss`, `screens/base.py`, `screens/settings.py`,
`widgets/setting_field.py`, `widgets/intent_form.py`, stary `command_bar.py`) znikają
w fazie, która zastępuje ich ostatniego konsumenta. `CSS_PATH` przyjmuje listę ścieżek
(Textual `App.CSS_PATH: CSSPathType`), więc trzy pliki `.tcss` są legalne.

### D-2. Warstwa motywu

- `theme.py` definiuje frozen stałe palet (sekcja `# ── Constants ──`, docstring pod
  stałą) i buduje dwa `textual.theme.Theme`: `anishift-dark` (default), `anishift-light`.
  Tokeny bazowe = 11 slotów `Theme`; 8 zmiennych własnych z R-102 wchodzi przez
  `Theme.variables` oraz `AniShiftApp.get_theme_variable_defaults()` (fallbacki —
  Textual wymaga defaultu dla każdej zmiennej użytej w CSS, `app.py:1399-1421`).
- Wybór palety: punkt startowy to paleta ciemna o charakterze zbliżonym do motywu
  `opencode` (neutralne tło, jeden akcent primary); dokładne hexy wybiera wykonawca
  w `theme.py` i kalibruje na bramce AC-HITL-1 — to jedyna dozwolona swoboda wizualna.
- Motyw jest ładowany z `config/ui_state.json` przy starcie (`ui_state.py`:
  `load_ui_state() -> UiState`, `save_ui_state(state)` — zapis atomowy tmp+replace,
  zła zawartość → default + warning w logu, nigdy crash). Plik dopisany do
  `.gitignore` obok `config/settings.json`.
- Strażnik AC-101: `tests/tui/test_theme_guard.py` — regex hexów
  (`#[0-9a-fA-F]{3,8}\b`) po `anishift/tui/**/*.tcss` i `anishift/tui/**/*.py`
  z wyłączeniem `theme.py`; trafienie = fail z listą plików.

### D-3. Prymitywy dialogowe na `ModalScreen`

- `DialogScreen(ModalScreen[ResultT])`: kontener pełnoekranowy z tłem `$overlay`
  (TCSS z alfą — np. `background: black 60%` przez token), panel wycentrowany,
  `margin-top: height // 4` liczony w `on_resize`, szerokość wg `size`
  (R-110). Klik w zasłonę = dismiss(None). Wynik wraca przez
  `app.push_screen(dialog, callback)` / `dismiss(result)` — Textual-owy odpowiednik
  `replace`/`clear` OpenCode; **nie budujemy własnego stosu dialogów** (R-206): w danym
  momencie na stosie ekranów jest co najwyżej jeden `DialogScreen`, a „podmiana" to
  `dismiss` + natychmiastowy `push_screen` następnego z poziomu callbacku.
- `SelectDialog` — sygnatura publiczna (wiążąca, szczegóły implementacji wolne):

```python
@dataclass(frozen=True, slots=True)
class SelectOption[T]:
    value: T
    title: str
    description: str | None = None
    footer: Text | str | None = None
    category: str | None = None
    disabled: bool = False

@dataclass(frozen=True, slots=True)
class SelectAction[T]:
    label: str
    key: str
    action_id: str

class SelectDialog[T](DialogScreen["SelectOutcome[T]"]):
    def __init__(
        self,
        *,
        title: str,
        options: Sequence[SelectOption[T]],
        current: T | None = None,
        actions: Sequence[SelectAction[T]] = (),
        multi: bool = False,
        selected: frozenset[T] = frozenset(),
        on_move: Callable[[T], None] | None = None,
        initial_highlight: T | None = None,
        placeholder: str = "Search",
        size: DialogSize = DialogSize.MEDIUM,
    ) -> None: ...
```

  `SelectOutcome` niesie: `value` (wybór), `selected` (zbiór w multi), `action_id`
  (akcja stopki) albo `cancelled=True`. Filtr: `Input` z fokusem w `on_mount`
  (wzorzec `dialog-select.tsx:583-591`); lista: `OptionList` Textual z własnym
  renderem wiersza (● gutter + tytuł + footer po prawej, R-109). Klawisze z R-203
  jako `BINDINGS` dialogu.
- Pozostałe prymitywy dziedziczą po `DialogScreen` z kontraktami R-209.

### D-4. Rejestr komend i paleta

- `CommandSpec` — frozen dataclass wg R-301 (`title` jako `str | Callable[[], str]`,
  `enabled`/`suggested` jako `Callable[[], bool]` z defaultem `lambda: True/False`).
- `CommandRegistry` żyje na `AniShiftApp`; API:
  `register(scope_id: str, specs: Sequence[CommandSpec])`,
  `unregister(scope_id: str)`, `dispatch(name: str) -> bool`,
  `palette_entries() -> ...` (visible ∧ enabled), `slash_entries() -> ...`
  (j.w. ∧ `slash_name`). Ekran rejestruje swoje komendy w `on_mount`
  (scope = route id) i wyrejestrowuje w `on_unmount`; komendy globalne rejestruje App
  pod scope `"app"`. `dispatch` jest jedynym punktem wykonania (R-302) — paleta,
  slash, `action_*` z `BINDINGS` i przyciski wołają wyłącznie jego.
- Wbudowana paleta Textual wyłączona: `AniShiftApp.ENABLE_COMMAND_PALETTE = False`;
  `ctrl+p` w `BINDINGS` App otwiera naszą (`commands/palette.py` → `SelectDialog`
  z grupą „Suggested" — duplikaty z prefiksem `suggested:` w value, znikają przy
  filtrze; wzorzec `command-palette.tsx:63-76`).
- Startowy słownik komend (rozszerzalny per ekran):

| name | category | keys | slash | enabled / suggested |
|---|---|---|---|---|
| `nav.workspace` | Workspace | — | `workspace` | zawsze |
| `nav.auto` | Workspace | `a` (workspace) | `auto` | zawsze |
| `nav.manual` | Workspace | `m` (workspace) | `manual` | zawsze |
| `settings.open` | Settings | `s` (workspace) | `settings` | zawsze |
| `settings.themes` | Settings | — | `themes` | zawsze |
| `workspace.refresh` | Workspace | `r` (workspace) | `refresh` | zawsze |
| `run.preview` | Run | `p` (auto/manual) | `preview` | enabled: istnieje draft/preset dla zaznaczonych grup |
| `run.cancel` | Run | `c` (execution) | `cancel` | enabled: aktywny run; suggested: aktywny run |
| `results.open` | Run | — | `results` | enabled: istnieje wynik w sesji |
| `tools.open` | System | `t` (workspace) | — | zawsze |
| `tools.doctor` | System | — | `doctor` | zawsze |
| `tools.setup` | System | — | `setup` | suggested: doctor zgłasza FAIL binarki |
| `app.help` | Help | `f1` | `help` | zawsze |
| `app.quit` | System | `ctrl+q` | `quit` | zawsze |
| `palette.open` | — (hidden) | `ctrl+p` | — | hidden=True |

### D-5. Fuzzy bez nowej zależności

`commands/fuzzy.py`: `rank_commands(query, entries, limit=10)` używa
`textual.fuzzy.FuzzySearch.match()` po kluczach `slash_name`, `description`
i po każdym aliasie (alias podbija wynik pozycji, nie tworzy wpisu); wynik bazowy
mnożony ×2, gdy `slash_name.startswith(query)`; pusta kwerenda = kolejność
alfabetyczna; wynik zawsze niepusty przy niepustym słowniku (próg 0), przycięty
do 10. Wyrównanie kolumn robi renderer popupu (padding do najdłuższej nazwy + 2).
Ten sam moduł obsługuje filtr `SelectDialog` (klucze `title` ×2, `category` ×1,
bez limitu — R-205).

### D-6. Dostęp do wartości ustawień poza TUI

Czyste funkcje mapujące `SettingSpec` ⇄ `UserSettings` (dziś prywatne w
`anishift/tui/screens/settings.py:148-189`: `_setting_value`, `_assign_setting`,
`_setting_is_active`) przenoszą się jako publiczne do nowego modułu
`anishift/config/field_access.py`:

```python
def read_setting_value(settings: UserSettings, spec: SettingSpec) -> SettingValue: ...
def assign_setting_value(settings: UserSettings, spec: SettingSpec, value: SettingValue) -> None: ...
def setting_is_active(spec: SettingSpec, settings: UserSettings) -> bool: ...
```

Powód: logika jest domeną konfiguracji (zna profile TTS i `engine_options`), musi być
testowalna bez Textual i będzie użyta w trzech kontekstach (settings, auto, manual).
Testy: `tests/config/test_field_access.py` (przeniesione przypadki + profile).

### D-7. Zapis ustawień i stan UI

- Instant apply (R-408): `settings/editors.py` → `apply_setting(app_service, spec,
  value) -> str | None` (None = sukces, str = komunikat błędu bez ścieżek):
  `candidate = deepcopy(service.settings_snapshot())` → `assign_setting_value` →
  `spec.validate_value(value)` + `candidate.__post_init__()` →
  `service.save_settings(candidate)`. Kolejność pól profilu jak w obecnym kodzie
  (profil TTS przypisywany po polach silnika).
- `config/ui_state.json` (D-2) trzyma wyłącznie preferencje prezentacji (na start:
  `{"theme": "anishift-dark"}`). Nie jest częścią `UserSettings` i nie przechodzi
  przez `AppService` — to stan UI, wzorzec `kv.json` OpenCode.

### D-8. Pętla zdarzeń i własność stanu (bez zmian koncepcji, nowa implementacja)

Wzorce z obecnego `app.py` są poprawne i zostają odtworzone w nowym kodzie:
timer UI (75 ms) drenuje `EventBuffer` i publikuje `RunEventsReceived`;
`Worker(thread=True)` wykonuje blokujące `AppService.execute()`/`discover()`;
`SessionState.generation` + `run_id` bramkują spóźnione wyniki (I-6); zamknięcie
Execution pauzuje timer. Właścicielem `SessionState` jest App; ekrany czytają go
przez `self.app`; dialogi zwracają wyniki przez `dismiss`.

### D-9. Entrypoint, kodowanie i bramka legacy

- F1: `cli/main.py` na początku `main()`/modułu wykonuje
  `_reconfigure_console_streams()`: dla `sys.stdout`/`sys.stderr` z atrybutem
  `reconfigure` ustawia `encoding="utf-8"`, `errors="replace"` (R-702). Nowy check
  doctora `console encoding` (R-703) w `setup/doctor.py` — jedyna zmiana poza
  `cli/`+`tui/`+`config/` w tym etapie.
- F7: `_default` i `run --preset` przywracane na bazie diffu `ed589c5`
  (`git show ed589c5 -- anishift/cli/main.py tests/cli/test_main.py`), dostosowane do
  nowego `AniShiftApp`. `doctor`/`setup`/`run` nie importują Textual na ścieżce
  modułu (leniwe importy jak w `ed589c5`).
- Bramka legacy (technical gate, R z §1.4 wymagań):
  1. zielony `tests/application/test_legacy_parity.py` (AC-801) — hermetyczne
     wejścia, fake providerzy na publicznych kontraktach, porównanie: status per
     grupa, nazwy/rodzaje produktów, liczba wywołań providerów; bez timestampów
     i kolejności logów (wzorzec `etap-9-plan.md` §19.2);
  2. checklist parytetu funkcji REPL → TUI (tabela w F7);
  3. AC-HITL-2: smoke użytkownika na cmd (cp1250) i Windows Terminal — zamyka
     niewiadomą reverta `6849f32`;
  4. dopiero potem, w jednym commicie: kasacja legacy `cli/`, całego
     `anishift/pipeline/`, `tests/pipeline/`, legacy testów CLI, parity testu
     i `uv remove prompt-toolkit`.
  Jeśli HITL-2 nie przechodzi: STOP — entrypoint zostaje na legacy, wynik wraca do
  użytkownika z listą braków; kasacja nie następuje.
- `pipeline/` przy kasacji: żaden moduł produkcyjny nie może go importować
  (weryfikacja `rg 'anishift\.pipeline' anishift/` przed kasacją; na baseline
  importują go tylko legacy CLI i testy pipeline).

### D-10. Zakres ekranów wobec Etapu 9

Ekrany implementują zachowania z `etap-9-interfejs-wymagania.md` §5 w kształcie już
zrealizowanym przez obecne ekrany (te same wywołania `AppService`), ale z nową
warstwą prezentacji. Nie zmieniamy semantyki: workspace nie uruchamia pracy; auto —
jeden preset na zaznaczoną paczkę, akcje `Preview once`/`Save preset`/`Reset`/`Back`;
manual — niezależne drafty per grupa, rejestracja plików zewnętrznych przez
`register_external_*` w workerze z bramką generacji; preview — start tylko dla
`can_execute`, modal dla operacji płatnych/nadpisujących; results — statusy per grupa
i przejście do manual. Route `settings` znika z mapy ekranów (Z-4) — komenda
`settings.open` otwiera dialog.

### D-11. Strategia testów (szczegóły w §8)

Pilot dla każdego dialogu/ekranu/przepływu; testy jednostkowe dla `fuzzy`, `registry`,
`field_access`, `icons`, `theme` (strażniki); bez frameworka snapshotów (nowa
zależność bez potrzeby — wygląd ocenia HITL, zachowanie Pilot). Fake `AppService`
w `tests/tui/tui_fakes.py` (istnieje — rozszerzany), pełny przepływ na realnym
`AppService` + fake handlery (wzorzec `tests/application/fakes.py`).

### D-12. Commity i scope

Scope `cli` dla całości TUI (hook nie zna `tui`). Propozycja dodania scope `tui`
do `check_commit_msg.py` zostaje zgłoszona użytkownikowi jako opcja (§13); do decyzji
pozostaje `cli`.

### D-13. `tasks.json` — nie powstaje

Praca jest sekwencyjna (F2 zależy od F1, F4 od F2+F3, F6 od F2, F7 od wszystkich),
jednoosobowa i jednosesyjna per faza; frontier zawsze ma szerokość 1–2. Living plan
+ kolejność commitów wystarczą; osobny graf zadań byłby ceremonią.

## 5. Execution Plan — fazy

Każda faza: pełne bramki + commit(y) + działające repo. Weryfikacja fazy zawsze
obejmuje cztery komendy bramek (nie powtarzam ich w każdej fazie — skrót „bramki").

---

### F1 — fundamenty: kodowanie, higiena repo, motyw, ikony

**Cel:** usunąć blokery infrastrukturalne (crash cp1250, brudny `git status`)
i postawić design system, ZANIM powstanie pierwszy nowy widget (anty-wzorzec
Etapu 9 — design odkładany na koniec — jest tu odwrócony strukturalnie).

Kroki:

1. **UTF-8 na granicy procesu** (`anishift/cli/main.py`): funkcja
   `_reconfigure_console_streams()` wywoływana przed pierwszym wyjściem (D-9).
   Test: `tests/cli/test_console_encoding.py` — raport doctora pisany do strumienia
   `cp1250` (bufor `TextIOWrapper` z `encoding="cp1250"` podstawiony pod console)
   nie rzuca `UnicodeEncodeError` (AC-701).
2. **Check doctora `console encoding`** (`anishift/setup/doctor.py`): OK dla
   utf-8/65001, WARN + sugestia dla innych (R-703, AC-702). Test w istniejącym
   `tests/setup/` wg konwencji sąsiadów.
3. **`.gitignore`**: dopisać `config/presets.json` i `config/ui_state.json` w sekcji
   Project-specific obok `config/settings.json` (`.gitignore:291`).
4. **`anishift/tui/theme.py`** (D-2): tokeny R-102, palety `anishift-dark`
   i `anishift-light`, `register_themes(app)`. **`anishift/tui/ui_state.py`**:
   `UiState`, `load_ui_state`, `save_ui_state` (atomowo, odporne na złą zawartość).
5. **`anishift/tui/icons.py`**: tabela R-106 jako frozen struktury
   (`StatusGlyph(glyph, word, token)`), klatki spinnera, funkcja
   `status_text(state) -> Text` sklejająca glif+słowo w tokenowanym stylu.
6. **Strażniki**: `tests/tui/test_theme_guard.py` (AC-101 — hex tylko w `theme.py`),
   `tests/tui/test_icons.py` (AC-103 — kompletność tabeli stanów). Strażnik działa
   od tej fazy na starym `theme.tcss` — stary plik dostaje **wyjątek tymczasowy**
   (jawna lista `LEGACY_ALLOWED` w teście), usuwany w F4 razem z plikiem.

Dotknięte pliki: `anishift/cli/main.py`, `anishift/setup/doctor.py`, `.gitignore`,
nowe `anishift/tui/{theme,ui_state,icons}.py`, nowe testy.

Weryfikacja: bramki + `uv run anishift doctor` w konsoli cmd bez `chcp` (ręcznie,
raz — potwierdzenie realnego zachowania R-702).

Gate przejścia: AC-701, AC-702, AC-101 (z wyjątkiem legacy), AC-103 zielone.

Commity:
- `fix(cli): enforce UTF-8 console output at the process boundary`
- `feat(cli): add semantic theme tokens and status icons`
- `chore(repo): ignore user preset and UI state files`

---

### F2 — prymitywy dialogowe

**Cel:** jeden widget wyboru i cztery prymitywy — fundament całego UX (R-201–R-210).

Kroki:

1. `dialogs/base.py`: `DialogScreen` (D-3) + `DialogSize` (StrEnum: MEDIUM=60,
   LARGE=88, XLARGE=116). TCSS w `styles/dialogs.tcss` (zasłona, panel, nagłówek
   z klikalnym `esc`, pole filtra, wiersze, stopka akcji) — wyłącznie tokeny.
2. `dialogs/select.py`: `SelectDialog` wg sygnatury D-3 i kontraktu R-202–R-208
   (multi, on_move, initial_highlight, zachowanie kursora przy filtrze R-204,
   płaska lista przy niepustym filtrze). W F2 `SelectDialog` używa lokalnie
   `textual.fuzzy.FuzzySearch` (title ×2 + category ×1); F3 wydziela wspólną
   funkcję rankingu bez zmiany zachowania.
3. `dialogs/prompt.py`, `dialogs/number.py`, `dialogs/confirm.py`,
   `dialogs/reorder.py` wg R-209.
4. App jeszcze nie używa dialogów — to czysta biblioteka; stare ekrany działają.
   Testy dialogów montują je na minimalnej aplikacji testowej z zarejestrowanym
   motywem z F1.

Testy (Pilot, `tests/tui/`): `test_dialog_select.py` (AC-201–AC-204: fokus filtra,
marker vs kursor, akcje stopki + etykiety z keymapy, multi, wrap-around,
pageup/pagedown, initial_highlight, escape-refocus, klik w zasłonę),
`test_dialog_prompt.py`, `test_dialog_number.py` (AC-205), `test_dialog_confirm.py`,
`test_dialog_reorder.py` (AC-206).

Gate: AC-201–AC-206 zielone; bramki.

Commit: `feat(cli): add reusable dialog primitives for the TUI`

---

### F3 — rejestr komend, paleta, command bar, stopka

**Cel:** jedno wejście do wszystkiego (R-301–R-309), zanim powstaną nowe ekrany,
które będą się do rejestru wpinać.

Kroki:

1. `commands/spec.py` + `commands/registry.py` (D-4). `commands/fuzzy.py` (D-5)
   — wydzielenie wspólnego rankingu; `SelectDialog` przełącza się na niego.
2. `commands/palette.py`: paleta na `SelectDialog` (Suggested, kategorie, footer
   ze skrótem z keymapy, nie pokazuje samej siebie).
3. `widgets/command_bar.py` — **przepisany w miejscu**: `Input` z promptem `❯`
   renderowanym jako stały prefiks, popup slash (lista nad barem, max 10, nawigacja
   up/down/enter/tab/escape, fuzzy z pięcioma regułami), publikacja
   `CommandSubmitted`; wykonanie wyłącznie przez `registry.dispatch`. Nowa klasa
   `StatusFooter` przenosi się do `widgets/status_footer.py`; stare ekrany są
   w tym samym commicie przepięte na nowe widgety (konstruktory zgodne, czytają
   ten sam `SessionState`). Przejściowy mix wizualny na starych ekranach jest
   dozwolony maksymalnie do F5.
4. `widgets/status_footer.py`: segmenty + skróty aktywnego ekranu z żywych
   `BINDINGS` (R-502); ikony z `icons.py`.
5. `messages.py`: nowy zestaw typowanych wiadomości.
6. Stary `app.py` dostaje w tym kroku minimalny szew: instancję `CommandRegistry`,
   rejestrację komend globalnych z tabeli D-4 (nawigacyjne odwzorowane na
   istniejące `open_route`), `ENABLE_COMMAND_PALETTE = False`, `BINDINGS` globalne
   (`ctrl+p`, `/`, `f1`, `ctrl+q`) i handler palety. Stary parser
   `tui/commands.py` zostaje dla starych ścieżek do F4 (F4 go kasuje).

Testy: `test_command_registry.py` (predykaty enabled/suggested, scope'y per ekran,
dispatch jako jedyny punkt — AC-302), `test_fuzzy.py` (ranking: prefix ×2, próg 0,
limit 10, aliasy — AC-303, przypadki deterministyczne), `test_command_bar.py`
(AC-303, AC-304: pusty enter, nieznana komenda z sugestią, popup ≤10),
`test_palette.py` (AC-301), `test_status_footer.py` (skróty z BINDINGS — I-9).

Gate: AC-301–AC-304 zielone; bramki (stare testy ekranów zaktualizowane w tym samym
commicie tam, gdzie dotknęła je wymiana paska).

Commit: `feat(cli): add command registry palette and command bar`

---

### F4 — nowy App + ekrany Workspace, Auto, Manual, Preview

**Cel:** rdzeń przepływu planowania w nowej gramatyce; po tej fazie pierwsza
bramka HITL.

Kroki:

1. **`app.py` przepisany** (D-8): rejestracja motywów z `ui_state`, `SCREENS` bez
   `settings` (Z-4; do czasu F6 komenda `settings.open` otwiera tymczasowo stary
   `SettingsScreen` przez jawny adapter — jedyny świadomy dług fazy, skasowany
   w F6), timery (drain 75 ms pauzowany poza runem, footer ≤4/s tylko w runie —
   R-604), bramka generacji (I-6), obsługa `CommandSubmitted` przez registry.
   Kasacja `tui/commands.py` (stary parser) i `screens/base.py`
   (PlaceholderScreen — I-3).
2. **`screens/workspace.py`** + `widgets/group_table.py`: tabela grup
   (`DataTable`, stabilne row keys; kolumny: zaznaczenie `✓/○`, stem, źródło,
   sidecary, produkty, konflikty z `⚠ powód`), zaznaczanie `space`, sort/filtr,
   refresh w workerze z bramką generacji, nagłówek z małym logo ASCII (znika
   <100×30), `BINDINGS` wg R-309 + rejestracja komend ekranu.
3. **`screens/auto.py`**: edytor presetu — lista pól AUTO_PRESET renderowana jak
   korzeń ustawień (wiersz = etykieta + wartość + strzałka `▸`), edycja przez
   dialogi z F2 z ręcznym mapowaniem 8 pól AUTO_PRESET (pola są
   w `AutoPresetDraft`); F6 refaktoryzuje na wspólny dispatch bez zmiany
   zachowania. Akcje: `Preview once`, `Save preset`, `Reset`, `Back` (semantyka
   Etapu 9 — D-10).
4. **`screens/manual.py`**: lista grup po lewej, intencja wybranej grupy po prawej
   (wiersze pól MANUAL_RUN + produkty/burn/tracks przez dialogi F2); rejestracja
   plików zewnętrznych przez `register_external_*` w workerze; `Copy to selected`
   tworzy niezależne drafty.
5. **`screens/preview.py`** + `widgets/plan_view.py`: źródła, pominięte
   alternatywy, operacje w kolejności, produkty i nadpisania (`⚠` + ścieżka
   względna), silniki/fallbacki/limity, problemy blokujące; Start tylko dla
   `can_execute`, `ConfirmDialog` dla płatnych/nadpisujących (I-4), blokada
   podwójnego startu (I-5).
6. Kasacja starych: `screens/{workspace,auto,manual,preview}.py` (zastąpione),
   `widgets/intent_form.py`, stary `theme.tcss` + wpis `LEGACY_ALLOWED`
   w strażniku; `styles/screens.tcss` przejmuje layout.

Testy: wymiana `test_tui_workspace.py`, `test_auto.py`, `test_manual.py`,
`test_preview.py` na nowe scenariusze (min. dotychczasowy zakres: 20 grup,
sort/filter/select/refresh, 3 niezależne drafty manual, copy bez współdzielenia
stanu, preview blokujące, spóźniona inspekcja ignorowana) + nowe: BINDINGS ekranów,
komendy w palecie per ekran (AC-302), R-603 (100 grup w tabeli bez timeoutu).

Gate: bramki + **AC-HITL-1** — użytkownik ogląda workspace/auto/manual/preview na
własnym terminalu (lista kontrolna R-112 + czytelność w 256 kolorach). Brak
akceptacji = iteracja wyglądu w tej fazie; F5 nie startuje bez akceptacji.

Commity:
- `feat(cli): rebuild the Textual shell on the command registry`
- `feat(cli): rebuild workspace auto manual and preview screens`

---

### F5 — Execution, Results, Tools

**Cel:** obserwowanie i domykanie pracy (R-503–R-504).

Kroki:

1. **`screens/execution.py`** + `widgets/progress_table.py`: prealokowane wiersze
   per grupa (`natsorted`), glif+słowo stanu (spinner braille w running), bieżąca
   operacja, procent koalescowany ≤10/s per task, zdarzenia terminalne bez
   throttle; rozwijane szczegóły zadań z `retry n/m <engine>` i
   `fallback -> <engine>` (R-503, AC-502); filtr `f` (all/running/failed/done);
   `c` = cancel przez `ConfirmDialog`, idempotentny (R-504); komunikaty przez
   `sanitize_event_message`.
2. **`screens/results.py`**: sekcje `✓ succeeded / ⚠ partial / ✗ failed /
   ○ cancelled`, produkty utworzone i zachowane, bezpieczny błąd, akcja „Open in
   Manual" dla nieudanej grupy.
3. **`screens/tools.py`**: doctor/setup w workerze, wyniki jako lista
   glif+słowo+sugestia; komendy `tools.doctor`/`tools.setup` z palety trafiają
   w ten sam ekran i te same metody (bez drugiej implementacji).
4. Kasacja starych `screens/{execution,results,tools}.py` (zastąpione).

Testy: wymiana `test_execution.py`, `test_tui_results.py`, `test_tools.py`
+ scenariusze: input żywy podczas progressu (R-601), stary event nie zmienia
nowego runu (I-6), drugi cancel bez efektu, partial w Results, retry/fallback
widoczne (AC-502), resize (AC-503).

Gate: bramki; wszystkie ekrany produkcyjne bez placeholderów (I-3).

Commit: `feat(cli): rebuild execution results and tools screens`

---

### F6 — drzewo ustawień `/settings`

**Cel:** centralny wymóg UX etapu (R-401–R-410); pełne pokrycie katalogu (AC-407).

Kroki:

1. **`anishift/config/field_access.py`** (D-6) + `tests/config/test_field_access.py`.
   Stary ekran ustawień jest w tej fazie kasowany, więc funkcje przenoszą się bez
   okresu podwójnego życia.
2. **`settings/editors.py`**: `open_editor(spec, current, on_commit)` — dispatch
   po `value_type` i metadanych wg tabeli R-405 (10 typów; bool = toggle
   w miejscu, obsługiwany przez tree, nie przez editors); `apply_setting()`
   (D-7, R-408); `summarize_value(spec, value) -> str` dla wierszy korzenia.
3. **`settings/tree.py`**: budowa korzenia z `setting_catalog(context)` —
   kategorie R-403, filtr aktywności (`setting_is_active`), wiersze sekretów
   (R-409: `environment_statuses()` → `✓ configured`/`○ missing`, enter = dialog
   instrukcji), footer wyboru silnika z `engine_availability()` (R-410); pętla
   nawigacji `replace + initial_highlight` (R-407); przebudowa korzenia po zmianie
   pola kontekstowego (R-406).
4. Komenda `settings.open` przełączona z adaptera F4 na drzewo; **kasacja**
   `screens/settings.py` i `widgets/setting_field.py`; refaktoryzacja Auto/Manual
   na wspólny `settings/editors.py` (usunięcie ręcznego mapowania z F4).
5. Dialog `themes` (`settings.themes`): `SelectDialog` z `on_move` live preview
   i rollbackiem (R-208, AC-102), zapis do `ui_state.json`.

Testy: `test_settings_tree.py` (AC-401–AC-406: zapis jednej zmiany + powrót
z kursorem, escape bez zapisu, przebudowa po zmianie silnika + przywrócenie
profilu głosu, bool w miejscu, sekret read-only, walidacja inline),
`test_settings_editors.py` (dispatch per typ na syntetycznych specach),
**`test_settings_coverage.py`** (AC-407: konteksty edge / elevenbytes run6 /
run7 / elevenlabs / oba profile SAPI — każdy spec ma edytor; nieobsłużony
`value_type` lub spec = fail), `test_themes_dialog.py` (AC-102).

Gate: AC-401–AC-407, AC-102 zielone; bramki.

Commit: `feat(cli): add dialog-driven settings tree`

---

### F7 — entrypoint, parytet i usunięcie legacy

**Cel:** jedna ścieżka wykonania; domknięcie niewiadomej reverta (D-9).

Kroki:

1. **Parity test** `tests/application/test_legacy_parity.py` (AC-801): hermetyczny
   workspace (tmp_path, syntetyczne pliki, fake translation/TTS na publicznych
   kontraktach — wzorce z `tests/application/fakes.py` i `tests/pipeline/`),
   przebieg przez legacy `run_pipeline`/`compose_only` i przez
   `AppService.plan_auto + execute`; porównanie: status per grupa, zbiór
   (nazwa, rodzaj) produktów, liczba wywołań fake providerów. Bez timestampów
   i kolejności logów (wzorzec `etap-9-plan.md` §19.2).
2. **Checklist parytetu funkcji** (weryfikowana w review tej fazy):

| Funkcja legacy | Odpowiednik w TUI/CLI |
|---|---|
| Enter w REPL uruchamia pipeline na workspace | Workspace → Auto (preset) → Preview → Start; nieinteraktywnie `run --preset` |
| `/compose` (składanie z dysku, bez zmiany ustawień) | Manual: punkt startowy = gotowe produkty, products = kontenery; planner pomija TTS/translation |
| `/settings` (panel pełnoekranowy, zapis po każdym kroku) | dialog `/settings` (F6, zapis natychmiastowy) |
| `/setup`, `/doctor` | ekran Tools + CLI `setup`/`doctor` |
| `/help` + completer | paleta `ctrl+p`, slash-popup, `f1` |
| banner ASCII | logo w nagłówku workspace |
| prompt awarii LLM/TTS: `retry`/`settings`/`finish` | retry pozostaje w domenie silników; po runie Results → Manual (wznowienie od trwałych produktów); brak interaktywnego prompta w trakcie — świadoma zmiana, odnotowana w docs F8 |

3. **Entrypoint** (D-9): `_default` → `launch_tui()`; `run --preset` (exit 0 przy
   pełnym sukcesie, niezerowy przy partial/failure/cancel; stabilny raport
   tekstowy); testy `tests/cli/test_main.py` przywrócone z `ed589c5`
   i dostosowane; doctor/setup bez importu Textual.
4. **AC-HITL-2**: smoke użytkownika (cmd cp1250 + Windows Terminal): start TUI,
   pełny przepływ na próbnym workspace, wyjście. Wynik zapisany w opisie PR.
   Brak akceptacji = STOP i powrót do użytkownika z listą braków (bez kasacji;
   entrypoint wraca na shell jednym revertem commitu entrypointu).
5. **Kasacja** (jeden commit): `cli/{shell,commands,completer,pipeline_ui,
   settings_panel,banner,tts_settings}.py`; cały `anishift/pipeline/` (13 plików
   + AGENTS/CLAUDE); `tests/pipeline/` (10 plików); legacy testy CLI
   (`test_banner`, `test_commands`, `test_completer`, `test_compose_command`,
   `test_pipeline_ui`, `test_settings_panel`, `test_tts_settings`);
   `test_legacy_parity.py`; `uv remove prompt-toolkit`. Scenariusze pipeline
   o trwałej wartości istnieją już w `tests/application/` (streaming, recovery,
   scheduler) — przed kasacją porównać listy przypadków i przenieść brakujące
   do `tests/application/` w tym samym commicie.

Weryfikacja fazy (ponad bramki):

```bash
uv run anishift doctor
rg 'prompt_toolkit|anishift\.pipeline|run_shell|SlashCompleter' anishift tests
uv run pytest tests/cli tests/tui tests/application -v
uv lock --check
```

`rg` ma zwrócić pusty wynik; `Test-Path anishift/pipeline` i
`Test-Path tests/pipeline` → `False`.

Gate: AC-801 (przed kasacją), AC-802 (po), AC-HITL-2; bramki.

Commity:
- `test(pipeline): prove legacy and application parity`
- `feat(cli): launch the Textual interface by default`
- `refactor(pipeline): remove the legacy execution path`

---

### F8 — E2E przepływu, dokumentacja, domknięcie

**Cel:** dowód całości i aktualna prawda w docs.

Kroki:

1. **`tests/tui/test_flow.py`** (AC-501): realny `AppService` + realny planner,
   scheduler i `RunSession`; fake wyłącznie handlery graniczne
   (`tests/application/fakes.py`). Scenariusze Pilot:
   - workspace → auto → preview → execution → results (sukces + partial);
   - workspace → manual (3 grupy, niezależne intencje) → preview → cancel →
     results;
   - `/settings`: zmiana wartości → widoczna w preview następnego planu;
   - command bar i paleta na każdym ekranie; pusty/nieznany input bez efektów;
   - resize 100×30 i 80×24 (AC-503); podwójny Enter nie startuje dwóch runów
     (I-5).
2. **Sprzątanie**: grep placeholderów po `anishift/tui/` pusty; przegląd
   `styles/*.tcss` strażnikiem AC-101 (lista wyjątków legacy pusta).
3. **Docs**: `anishift/tui/AGENTS.md` (nowe granice: theme jedynym właścicielem
   kolorów, registry/dispatch, dialogi, zapis natychmiastowy ustawień, Pilot);
   `anishift/cli/AGENTS.md` (REPL usunięty, nowa mapa plików); root `AGENTS.md`
   (mapa katalogów bez `pipeline/`); `config/README.md` (`ui_state.json`);
   `docs/plans/_index.md` (wiersz 9.5 + jawna lista pozostałości Etapu 9:
   real-media E2E, load, CI E2E, zamknięcie #38); `README.md` jeśli opisuje REPL.
4. **Końcowy smoke**: `uv sync --frozen`, `uv run anishift doctor`,
   `./run_anishift.bat doctor`, bramki.

Gate: AC-501 zielony; liczba testów `tests/tui/` ≥ 29; bramki; DoD (§10)
odhaczone.

Commity:
- `test(cli): cover the full TUI flow end to end`
- `docs(repo): document the stage 9.5 interface`

## 6. Strategia testów

| Warstwa | Co | Narzędzie |
|---|---|---|
| unit | fuzzy ranking (przypadki deterministyczne), CommandRegistry (predykaty, scope'y), `field_access` (mapowanie 10 typów + profile), `icons` (kompletność), `ui_state` (zła zawartość → default) | pytest, bez Textual |
| strażniki | hex poza `theme.py` (AC-101), placeholdery (propozycja §13), pokrycie katalogu ustawień edytorami (AC-407), kodowanie cp1250 (AC-701) | pytest |
| widget/Pilot | każdy dialog (F2), command bar/paleta/stopka (F3), każdy ekran (F4–F5), drzewo ustawień (F6) — na fake `AppService` | `App.run_test()` + Pilot |
| przepływ/Pilot | `test_flow.py` na realnym `AppService` + fake handlery (F8) | Pilot |
| parytet | `test_legacy_parity.py` — istnieje tylko w F7 | pytest |
| HITL | AC-HITL-1 (wygląd, po F4), AC-HITL-2 (parytet użytkowy + konsola cp1250, w F7) | użytkownik |
| poza zakresem | real-media E2E, load 100 grup schedulera, snapshoty pikselowe | — (Etap 9 / świadome cięcie) |

Zasady: testy bez docstringów/komentarzy (hook); brak nowych `__init__.py` pod
`tests/`; fake na publicznych kontraktach, zero patchowania prywatnych helperów;
testy Pilot pytają o stan i wywołania API, nie o surowe bajty renderera; snapshotów
pikselowych nie wprowadzamy (wygląd ocenia HITL, zachowanie Pilot — D-11).

## 7. Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Eskalacja |
|---|---|---|---|
| **Powtórka porzucenia warstwy wizualnej** | ekrany powstają przed design systemem; „doszlifuję na końcu" | strukturalnie zablokowane: F1 stawia tokeny+strażnik AC-101 przed pierwszym widgetem; AC-HITL-1 blokuje F5 | brak akceptacji HITL-1 po 2 iteracjach → wrócić do użytkownika z wariantami palety |
| **Regres ustawień przy 58 polach** | pole bez edytora, zły zapis profilu TTS | AC-407 (pokrycie katalogu w 5 kontekstach) + `field_access` testowany bez UI + AC-403 (profil głosu) | nowy typ pola w katalogu bez wzorca → STOP, uzupełnić R-405 w wymaganiach |
| **Kodowanie Windows** | `UnicodeEncodeError`, krzaki w cmd | F1 pierwszą fazą; AC-701; smoke ręczny w F1 i HITL-2 w cmd | glify nieczytelne w conhost → degradacja słowem już wbudowana (R-106); trybu ASCII nie budować bez decyzji użytkownika |
| **Bus factor Textual = 1** | blokujący bug bez fixa upstream | pin `textual>=8.2.8`; wyłącznie stabilne API (Theme, ModalScreen, OptionList, DataTable, fuzzy); zero prywatnych modułów | bug blokujący na Windows → issue upstream + obejście lokalne; fork tylko z decyzją użytkownika |
| **Nieznana przyczyna reverta `6849f32`** | HITL-2 ujawnia powód, dla którego TUI nie nadaje się na default | technical gate D-9: entrypoint przełączany dopiero po HITL-2; kasacja legacy dopiero po przełączeniu | powód poza wyglądem (np. czas startu) → replan F7 |
| **Parytet niepełny** (funkcja REPL bez odpowiednika) | checklist F7, poz. „prompt awarii LLM/TTS" | świadoma zmiana zachowania opisana w checklist i docs; pozostałe pozycje mają odpowiedniki 1:1 | użytkownik żąda interaktywnego retry w trakcie runu → osobne wymaganie, poza 9.5 |
| **Drzewo dialogów myli fokusem/powrotem** | Pilot łapie zły `initial_highlight`; HITL łapie „gubię się" | pętla nawigacji w jednym module (`settings/tree.py`), testowana AC-401/402 | — |
| **Rozjazd starego i nowego UI w fazach przejściowych** | mix wizualny F3–F5 | dozwolony maks. jedną fazę; tabele kasacji per faza pilnują długu; I-3 od F4 | dług przekracza fazę → zatrzymać feature, dokończyć wymianę |
| **`DataTable`/`OptionList` nie udźwignie 100 grup** | test R-603 czerwony | DataTable Textual jest wirtualizowany — ryzyko niskie; w razie potrzeby uprościć render kolumn | trwały fail → uproszczenie kolumn, decyzja z użytkownikiem |

## 8. Expected Touch Set

Prawdopodobnie modyfikowane: `anishift/cli/main.py`, `anishift/setup/doctor.py`,
`.gitignore`, `anishift/tui/*` (całość — przepisanie), `tests/tui/*` (wymiana),
`tests/cli/test_main.py`, `anishift/tui/AGENTS.md`, `anishift/cli/AGENTS.md`,
root `AGENTS.md`, `docs/plans/_index.md`, `config/README.md`, `pyproject.toml`
+ `uv.lock` (wyłącznie przez `uv remove prompt-toolkit`).

Prawdopodobnie nowe: `anishift/tui/{theme,ui_state,icons}.py`,
`anishift/tui/{styles,commands,dialogs,settings}/…`,
`anishift/tui/widgets/status_footer.py`, `anishift/config/field_access.py`,
`tests/tui/{test_theme_guard,test_icons,test_dialog_select,test_dialog_prompt,
test_dialog_number,test_dialog_confirm,test_dialog_reorder,test_command_registry,
test_fuzzy,test_palette,test_status_footer,test_settings_tree,
test_settings_editors,test_settings_coverage,test_themes_dialog,test_flow}.py`,
`tests/config/test_field_access.py`, `tests/cli/test_console_encoding.py`,
przejściowo `tests/application/test_legacy_parity.py`.

Usuwane (F4–F7): stare pliki `anishift/tui/` wg tabel faz;
`anishift/cli/{shell,commands,completer,pipeline_ui,settings_panel,banner,
tts_settings}.py`; `anishift/pipeline/` (całość); `tests/pipeline/` (całość);
7 plików legacy testów CLI.

Poza zakresem dotyku: `anishift/application/` (całość), `anishift/services/`,
`anishift/config/` poza `field_access.py` i README, `scripts/hooks/` (bez zgody
użytkownika), `.github/workflows/ci.yml`, `run_anishift.bat`.

## 9. Coverage: wymagania → fazy → weryfikacja

| Wymaganie | Faza | Dowód |
|---|---|---|
| R-101–R-105 (tokeny, motywy) | F1, F6 (dialog themes) | AC-101, AC-102 |
| R-106 (markery) | F1, użycie F4–F6 | AC-103, AC-502 |
| R-107–R-112 (ramki, gęstość, szerokości, rozpoznawalność) | F2, F4–F5 | testy dialogów + AC-HITL-1 |
| R-201–R-208 (SelectDialog) | F2 | AC-201–AC-204 |
| R-209 (prompt/number/confirm/reorder) | F2 | AC-205, AC-206 |
| R-210 / I-9 (stopki z keymapy) | F2–F3 | AC-203, test_status_footer |
| R-301–R-304 (rejestr, paleta) | F3 | AC-301, AC-302 |
| R-305–R-308 (command bar, slash, fuzzy ×5) | F3 | AC-303, AC-304 |
| R-309 (BINDINGS ekranów) | F4–F5 | testy ekranów + I-9 |
| R-401–R-410 (ustawienia) | F6 (częściowo F4 dla auto/manual) | AC-401–AC-407 |
| R-501–R-504 (ekrany, execution) | F4–F5 | AC-502, AC-503, testy F5 |
| R-601–R-604 (responsywność) | F4–F5, F8 | AC-501, test R-603, przegląd timerów |
| R-701–R-704 (kodowanie) | F1 | AC-701, AC-702 |
| R-801–R-803 (degradacja) | F4, F8 | AC-503, AC-HITL-1 |
| I-1 (granice importów) | ciągle | istniejący test architektury |
| I-2, I-3 | F1, F4 | AC-101, grep F8 |
| I-4, I-5, I-6 | F4–F5, F8 | testy preview/execution/flow |
| I-7 (bezpieczne komunikaty) | F5 | `sanitize_event_message` + review |
| I-10 (bramki) | każda faza | cztery komendy bramek |
| AC-801, AC-802 (parytet, entrypoint) | F7 | testy F7 + HITL-2 |
| Z-1–Z-5 (delta względem Etapu 9) | F4, F6 | AC-401 nn., brak route settings |

## 10. Definition of Done

- `anishift` bez argumentów otwiera nowe TUI; `doctor`, `setup`, `run --preset`
  działają bez startu Textual; `run_anishift.bat` bez zmian deleguje.
- Wygląd zaakceptowany przez użytkownika (AC-HITL-1) i potwierdzony jako zamiennik
  REPL-a (AC-HITL-2); zero placeholderów, zero nakładających się tekstów, zero
  surowych hexów poza `theme.py`.
- `/settings` działa w modelu `/session`: drzewo dialogów, zapis natychmiastowy,
  powrót z zachowanym zaznaczeniem; komplet katalogu pól pokryty edytorami
  (AC-407) w trzech kontekstach (settings/auto/manual).
- Paleta `ctrl+p` z grupą „Suggested", slash z pięcioma regułami fuzzy, command bar
  `❯`, stopka ze skrótami z żywej keymapy — wszystko na jednym rejestrze i jednym
  widgecie wyboru.
- Execution/Results renderują retry, fallback, cancel i partial glifem i słowem;
  wejście działa podczas runu; spóźnione zdarzenia odrzucane.
- Żadna komenda nie kończy się `UnicodeEncodeError` niezależnie od strony kodowej
  konsoli; doctor raportuje kodowanie.
- Legacy REPL, panel, `anishift/pipeline/`, `tests/pipeline/` i `prompt-toolkit`
  usunięte po zielonym parytecie; grep `prompt_toolkit|anishift.pipeline` pusty.
- Testy: `tests/tui/` ≥ 29 testów; pełne bramki zielone; dokumentacja (AGENTS.md,
  `_index.md`) zaktualizowana; pozostałość Etapu 9 (E2E/load/CI/#38) jawnie
  odnotowana jako otwarta.

## 11. Kolejność commitów

| Faza | Commit |
|---:|---|
| F1 | `fix(cli): enforce UTF-8 console output at the process boundary` |
| F1 | `feat(cli): add semantic theme tokens and status icons` |
| F1 | `chore(repo): ignore user preset and UI state files` |
| F2 | `feat(cli): add reusable dialog primitives for the TUI` |
| F3 | `feat(cli): add command registry palette and command bar` |
| F4 | `feat(cli): rebuild the Textual shell on the command registry` |
| F4 | `feat(cli): rebuild workspace auto manual and preview screens` |
| F5 | `feat(cli): rebuild execution results and tools screens` |
| F6 | `feat(cli): add dialog-driven settings tree` |
| F7 | `test(pipeline): prove legacy and application parity` |
| F7 | `feat(cli): launch the Textual interface by default` |
| F7 | `refactor(pipeline): remove the legacy execution path` |
| F8 | `test(cli): cover the full TUI flow end to end` |
| F8 | `docs(repo): document the stage 9.5 interface` |

Branch: kontynuacja `feature/stage-9-product-tui` (23 commity przed `main`, bez
upstreamu). PR na `main` po F8; treść PR bez śladów AI.

## 12. Blocker / replan policy

- Zmieniła się nazwa/helper/struktura lokalna przy tym samym kontrakcie → adaptuj
  lokalnie, odnotuj w opisie commitu.
- Założenie `D-*` fałszywe (np. `OptionList` nie obsłuży wymaganego renderu wiersza)
  → zatrzymaj dotkniętą część, wybierz najbliższy równoważny mechanizm Textual
  (np. własny `render_line`), zaktualizuj `D-*` w tym planie.
- Wymaganie `R-*` okazuje się sprzeczne lub niewykonalne → wróć do wymagań
  (aktualizacja `etap-9.5-tui-opencode-wymagania.md`), nie decyduj po cichu.
- HITL czerwony → patrz ryzyka §7 (wygląd: iteracja w fazie; parytet: STOP F7).
- Czerwony test spoza TUI po zmianie → reproduce → localize; zmiany
  w `application/` są zakazane, więc regres tam oznacza błąd w teście albo w TUI.

## 13. Propozycje strażników — wymagają zgody użytkownika

Zgodnie z filozofią repo (regułę egzekwuje maszyna) do zatwierdzenia:

1. **Test hex-guard** (F1, AC-101): żaden plik `anishift/tui/` poza `theme.py`
   nie zawiera literału koloru. Rekomendacja: TAK — bez niego wróci antywzorzec
   `theme.tcss`.
2. **Test placeholder-guard** (od F4): fraza `placeholder`/`next implementation
   step` w `anishift/tui/` (poza argumentem `placeholder=` pól input) = fail.
   Rekomendacja: TAK.
3. **Test coverage katalogu ustawień** (F6, AC-407): każdy `SettingSpec` ma edytor.
   Rekomendacja: TAK — to strażnik „58 pól, nie podzbiór".
4. **Test kodowania cp1250** (F1, AC-701). Rekomendacja: TAK.
5. **Scope `tui` w `check_commit_msg.py`**: opcjonalny; bez zgody pozostaje `cli`.
   Rekomendacja: dodać dopiero, gdy user chce rozdzielić historię TUI od CLI.

Strażniki 1–4 są częścią planu faz jako zwykłe testy w `tests/` (pre-push/CI już
je łapie); nie dodajemy ich do hooków pre-commit.

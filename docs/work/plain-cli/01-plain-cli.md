# PLAN 01 — interaktywne CLI, Home i prawdziwy Auto

## 0. Status dokumentu

```text
STATUS: READY
MODE: CREATE
SPEC AUTHORITY: spec.md
BASELINE BRANCH: feature/plain-cli
BASELINE COMMIT: bc0841bdd4bc192587f5b3eff5952ed7c4ee1c32
TARGET BRANCH: work/interactive-cli/01-home-auto
FINAL COMMIT: feat(cli): add interactive home and automatic run
```

Ten dokument jest jedynym artefaktem wykonawczym dla pierwszego kroku budowy
Interactive CLI AniShift.

Nie tworzymy dla tego kroku:

- osobnego `spec.md`;
- `tasks.json`;
- folderu `.workflow`;
- dodatkowego masterplanu;
- raportu zapisywanego w repo;
- pełnoekranowego TUI;
- ustawień;
- trybu ręcznego;
- animowanej maskotki;
- managera presetów;
- systemu pobierania anime.

Plan jest jednym pionowym wycinkiem wykonywanym sekwencyjnie.

Ma dwa ręczne gate’y:

```text
GATE A: wygląd i feeling Home
GATE B: prawdziwy Auto, progress, retry/fallback, wynik i błędy
```

Nie wolno ominąć GATE A i napisać całej integracji przed pierwszym pokazaniem Home.

---

## 1. Authority

Wykonawca przed zmianą czyta w całości:

```text
spec.md
AGENTS.md
anishift/AGENTS.md
anishift/cli/AGENTS.md
anishift/application/AGENTS.md
anishift/utils/rich_console/AGENTS.md
tests/AGENTS.md
```

Następnie czyta wskazane pliki current state.

Wymagania są authority dla zachowania.

Plan rozstrzyga sposób wykonania PLANU 01.

Jeżeli requirements i plan są sprzeczne, agent zatrzymuje się i zgłasza blocker. Nie
wybiera wygodniejszego dokumentu.

---

## 2. Potwierdzony stan wejściowy

### 2.1. Git

Remote branch:

```text
feature/plain-cli
```

Potwierdzony commit:

```text
bc0841bdd4bc192587f5b3eff5952ed7c4ee1c32
```

Commit:

```text
chore(repo): ignore the preset store and drop the dead ui files
```

Agent lokalnie sprawdza:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline
```

Wymagane przed utworzeniem gałęzi:

```text
working tree: clean
branch: feature/plain-cli
HEAD: bc0841bdd4bc192587f5b3eff5952ed7c4ee1c32
```

Jeżeli HEAD jest inny:

- nie resetuj;
- nie rebase’uj;
- nie twórz branchu z innego punktu;
- zgłoś drift i poczekaj na decyzję.

### 2.2. Entry point

Aktualne `anishift/cli/main.py`:

- używa Typer;
- dla bare invocation natychmiast uruchamia domyślny preset;
- ma `doctor`, `setup`, `run --preset`;
- posiada stabilne exit codes;
- ma bezpieczne renderowanie błędów;
- konfiguruje UTF-8 przed outputem;
- konfiguruje logger wyłącznie na granicy procesu.

### 2.3. Auto backend

Istniejący `AppService` udostępnia:

```text
workspace_root
discover()
default_preset_id()
get_preset()
plan_auto()
execute()
cancel()
```

Nie trzeba tworzyć nowej fasady produktu.

### 2.4. Eventy

Istnieją:

```text
RUN_STARTED
TASK_QUEUED
TASK_STARTED
TASK_PROGRESS
TASK_RETRY
TASK_FALLBACK
TASK_FINISHED
GROUP_FINISHED
RUN_FINISHED
```

`RunEvent` niesie:

```text
run_id
sequence
kind
group_id
task_id
state
progress_percent
message
```

Komunikat jest sanitizowany w application layer.

### 2.5. Prawdziwe możliwości postępu

Zweryfikowane zachowanie current handlerów:

- translation emituje retry/fallback oraz `100` dopiero po zapisaniu pełnego wyniku;
- extraction emituje `100` dopiero po zakończeniu;
- composition emituje `100` dopiero po zakończeniu;
- audio emituje fazy jako `progress=0` plus message i `100` na końcu;
- TTS emituje prawdziwy procent z liczby wymaganych requestów.

Wniosek:

```text
TTS                  -> pasek procentowy
translation          -> pasek 0% → 100%
extraction           -> pasek 0% → 100%
normalization/split  -> pasek 0% → 100%
audio                -> spinner + nazwa fazy
composition          -> pasek 0% → 100%
publish              -> pasek 0% → 100%
```

Wartości pośrednie pojawiają się wyłącznie wtedy, gdy dostarcza je backend.
`MultiProgressManager` zachowuje własne przejście kolorów dla każdego wiersza.

### 2.6. Rich

Na baseline nadal istnieje:

```text
anishift/utils/rich_console/
```

wraz z:

```text
console
RICH_THEME
MultiProgressManager
ProgressBarManager
status icons
formatting helpers
```

Nie trzeba przywracać ich z `main`.

### 2.7. Legacy progress jako referencja

`main:anishift/cli/pipeline_ui.py` ma dobre zachowania prezentacyjne:

- jeden wiersz per plik;
- zmiana etapu w tym samym wierszu;
- TTS real percentage;
- retry w opisie;
- audio spinner;
- naturalna kolejność.

Nie można skopiować pliku 1:1, ponieważ zależy od starego `anishift.pipeline`.

W PLANIE 01 wolno przenieść **politykę prezentacji**, ale nie legacy imports ani legacy
runtime.

### 2.8. Zależności

Baseline ma:

```text
rich
typer
```

Nie ma:

```text
questionary
prompt-toolkit jako bezpośrednia zależność projektu
textual
```

### 2.9. Testy

Istniejące testy CLI zabezpieczają:

- jeden composition root;
- brak tracebacka dla błędów startupu;
- brak interaktywnego toolkitu w technicznych subkomendach;
- stabilny noninteractive `run --preset`;
- exit codes;
- bezpieczne ścieżki;
- empty/unready workspace;
- blocked plan;
- default preset;
- current bare invocation uruchamiające run.

Ostatni kontrakt zostanie świadomie zmieniony: bare invocation otworzy Interactive CLI.

---

## 3. Jedno pytanie PLANU 01

Plan odpowiada tylko na pytanie:

> Czy `uv run anishift` może otworzyć mały, schludny Interactive CLI, w którym
> domyślne `Auto` uruchamia istniejący backend, pokazuje prawdziwy Rich progress,
> retry/fallback, wynik i błędy, po czym wraca do Home, bez Textual i bez zmiany
> noninteraktywnego `run --preset`?

Po wykonaniu i ręcznej akceptacji odpowiedź musi brzmieć:

```text
TAK
```

---

## 4. Wynik widoczny dla użytkownika

### 4.1. Home

Docelowa struktura PLANU 01:

```text
                    slime   ANISHIFT (sześć wierszy)

                         ▶ Auto
                           Ręczny
                           Ustawienia
                           Wyjście

                         ↑↓ · Enter

~\Desktop\PROJECTS\AniShift                         v0.1.0
```

Właściwości:

- stały sześciowierszowy wordmark z jednoliniowym fallbackiem;
- prawdziwa transparentna maskotka 20×14 po lewej stronie wordmarku;
- cztery akcje;
- `Auto` domyślne;
- akcent `#5c9cf5` ograniczony do aktywnego wyboru;
- cieniowana paleta slime'a w wordmarku oraz marker `▶`;
- brak statusów konfiguracji;
- hint pod listą;
- katalog po lewej i wersja po prawej przy dolnej krawędzi terminala.

### 4.2. Auto

```text
Home
-> Enter
-> Skanowanie workspace
-> plan
-> progress
-> wynik
-> dowolny klawisz
-> Home
```

### 4.3. Translation

```text
⠹ Tłumaczenie · Odcinek 06 · 18 s
```

Nie ma procentu.

### 4.4. TTS

```text
Lektor · Odcinek 06   ███████████░░░   73%   00:24
```

### 4.5. Retry

```text
⠹ Ponowna próba · Gemini · 2/3 · Odcinek 06
```

### 4.6. Fallback

```text
⠹ Fallback · Gemini -> DeepL · Odcinek 06
```

### 4.7. Wynik

Przykład sukcesu:

```text
✓ Gotowe

Odcinek 06
  napisy: gotowe
  lektor: gotowy
  MKV: gotowe

Naciśnij dowolny klawisz, aby wrócić
```

Przykład częściowy:

```text
! Zakończono częściowo

Odcinek 06
  napisy: gotowe
  MKV: błąd
  powód: Container composition failed

Szczegóły: logs/anishift.log.jsonl
```

---

## 5. Zachowania celowo poza zakresem

PLAN 01 nie implementuje:

- prawdziwych Settings;
- formularzy konfiguracji;
- zapisu sekretów przez UI;
- selektora modeli;
- trybu Ręcznego;
- CRUD presetów;
- listy anime;
- pobierania anime;
- Chafa;
- Sixel;
- animacji maskotki;
- asset pipeline;
- finalnego pixel artu;
- obsługi myszy;
- własnego Esc bindingu;
- filtrowanych list;
- manualnego retry po zakończeniu;
- preview planu;
- edytora theme;
- zmian w schedulerze;
- zmian w handlerach domenowych;
- nowych eventów application layer;
- przywracania `anishift.pipeline`;
- przywracania `anishift/tui`.

Pozycje `Ręczny` i `Ustawienia` są w Home, lecz w PLANIE 01 prowadzą do krótkiego
tymczasowego komunikatu i powrotu.

Brak ich finalnej funkcjonalności nie jest FAIL PLANU 01.

---

## 6. Zaktualizowana mapa realizacji

```text
01 Interactive CLI + Home + Auto
   TEN PLAN

02 Settings
   NIE ZACZYNAĆ

03 Manual
   NIE ZACZYNAĆ

04 Mascot states + polish + cleanup
   NIE ZACZYNAĆ
```

PLAN 02 powstaje dopiero po:

```text
PLAN 01 VERIFIED / COMMITTED
```

---

## 7. Decyzje techniczne

### D-001 — biblioteka promptów

Użyć:

```text
questionary 2.1.1 lub kompatybilnej wersji rozwiązanej przez uv
```

Zależność dodać wyłącznie:

```bash
uv add questionary
uv add pillow
```

Nie edytować ręcznie `pyproject.toml` ani `uv.lock`.

Jeżeli `uv` nie potrafi rozwiązać Questionary na Pythonie 3.14:

- zatrzymać pracę;
- zgłosić blocker;
- nie przechodzić samowolnie na InquirerPy, Textual ani raw prompt_toolkit.

### D-002 — prompt_toolkit

`prompt_toolkit` może wrócić jako zależność przechodnia Questionary.

Kod AniShift nie importuje go bezpośrednio w PLANIE 01.

### D-003 — lokalizacja

Nowa warstwa znajduje się w:

```text
anishift/cli/interactive/
```

Dzięki temu:

- podlega istniejącym regułom `anishift/cli/AGENTS.md`;
- nie wymaga nowego top-level subsystemu;
- może być lazy-importowana;
- nie odtwarza `anishift/tui`.

### D-004 — Typer

Typer pozostaje właścicielem:

```text
doctor
setup
run --preset
process entrypoint
exit codes noninteractive
```

### D-005 — bare invocation

Bare callback lokalnie importuje i uruchamia:

```python
run_interactive(service)
```

### D-006 — wspólny flow Auto

Preflight Auto zostaje wyciągnięty z `main.py` do UI-neutralnego:

```text
anishift/cli/run.py
```

Interactive i noninteractive używają tego samego:

```text
discover
ready groups
preset
plan_auto
execute
```

### D-007 — expected refusal jako dane

Pusty workspace, brak gotowych grup i blocked plan nie są tracebackiem.

`run.py` zwraca strukturę refusal zamiast renderować UI.

### D-008 — progress owner

`RichRunProgress` jest jedynym ownerem terminalowego stanu przebiegu.

Nie zapisuje stanu do `AppService`, Settings ani globalnego store.

### D-009 — jedna linia per grupa

Renderer prealokuje wiersze na podstawie `ExecutionPlan.groups`.

### D-010 — task mapping

Renderer buduje mapę:

```text
task_id -> TaskKind
task_id -> group_id
group_id -> display label
```

na początku runu.

### D-011 — determinate progress

W PLANIE 01 determinate bar jest włączany tylko dla:

```text
TaskKind.SYNTHESIZE_SPEECH
```

Inny `TASK_PROGRESS=100` jest traktowany jako completion pulse.

### D-012 — Rich reuse

Użyć istniejącego `MultiProgressManager`.

Nie zmieniać jego publicznego API bez udowodnionego blockera.

### D-013 — Home prompt

Home używa publicznego `questionary.select()`.

Konfiguracja:

```text
pointer = "▶"
use_indicator = false
qmark = ""
message = ""
use_arrow_keys = true
use_jk_keys = false
use_emacs_keys = false
use_shortcuts = false
show_description = false
```

### D-014 — hint i dolny status

Hint i dolny status są jednym non-selectable `questionary.Separator` zbudowanym przez
lokalny adapter. Hint jest bezpośrednio pod listą. Ostatni bezpieczny wiersz pokazuje
katalog względem home po lewej i wersję po prawej.

### D-014A — geometria Home

Całe Home korzysta z jednego, czysto wyliczanego snapshotu geometrii:

```python
@dataclass(frozen=True, slots=True)
class HomeGeometry:
    terminal_columns: int
    terminal_rows: int
    content_width: int
    left_padding: int
    top_padding: int
    footer_padding: int
    show_mascot: bool
    show_full_wordmark: bool
    mascot_columns: int
    mascot_rows: int
```

Pure helper:

```python
def resolve_home_geometry(columns: int, rows: int = 24) -> HomeGeometry
```

Zasady:

- maskotka i wordmark mają stałe rozmiary i jeden wspólny poziomy offset;
- blok marki i menu jest wycentrowany poziomo oraz pionowo nad statusem;
- menu pozostaje zwarte, a etykiety są wyrównane do lewej w jego obrębie;
- pointer Questionary zawiera wymagany lewy padding, dzięki czemu marker `▶` nie
  zostaje przy krawędzi terminala;
- nieaktywne wiersze zachowują identyczne wcięcie;
- dolny status zajmuje pełną bezpieczną szerokość ostatniego wiersza;
- wąski terminal najpierw ukrywa maskotkę, potem przełącza wordmark na jednoliniowy
  i skraca ścieżkę od lewej;
- resize otwartego promptu wywołuje czysty rerender Home z nową geometrią, bez
  ciągłego `Live` ani osobnego wątku UI.

Nie używać wiodących spacji wpisanych osobno do każdej etykiety menu. Wcięcie ma mieć
jednego właściciela w adapterze promptów/geometrii.

### D-015 — styl

Styl Questionary jest lokalny:

```text
accent
text
muted
error
```

Nie przebudowywać `RICH_THEME`.

### D-016 — maskotka w PLANIE 01

`mascot.py` czyta wyłącznie spakowany `slime_transparent_4k.png` przez Pillow i
renderuje go jako true-color półbloki Rich. Nie uruchamia Chafa ani subprocessu.
Maskotka ma stały rozmiar 20×14. Brak assetu bezpiecznie degraduje Home do samego
wordmarku.

### D-017 — prompt boundary

`InteractivePrompts` jest małym adapterem wokół Questionary.

Kod pętli nie wywołuje `questionary.*` w wielu modułach.

### D-018 — testy bez terminala

Testy używają fake prompt adaptera i fake AppService.

### D-018A — jeden lifecycle terminala

`QuestionaryPrompts` otwiera dokładnie jeden alternate screen przez publiczny,
cross-platformowy output Prompt Toolkit. `run_interactive()` utrzymuje ten context
manager przez całą sesję. Home i Auto czyszczą ten sam output przy przejściu,
Questionary usuwa zatwierdzoną odpowiedź, a Rich Progress aktualizuje swoje wiersze
w miejscu. Wyjście z pętli przywraca poprzedni bufor powłoki.

### D-019 — techniczne subkomendy

Questionary i prompt_toolkit są lazy-importowane wyłącznie w bare path.

### D-020 — proces błędu

Expected errors są renderowane i wracają do Home.

Unexpected errors nadal docierają do `main()` process boundary.

---

## 8. Ownership po PLANIE 01

### 8.1. Composition root

```text
anishift.bootstrap.production_service
```

jest jedynym ownerem konstrukcji `AppService`.

### 8.2. Typer entrypoint

```text
anishift.cli.main
```

jest ownerem:

- wyboru interactive/noninteractive;
- technicznych subkomend;
- exit codes;
- setup UTF-8;
- setup loggera.

### 8.3. Auto flow

```text
anishift.cli.run
```

jest ownerem:

- przygotowania Auto;
- expected refusal;
- wykonania przygotowanego planu.

Nie renderuje Questionary ani Rich.

### 8.4. Interactive loop

```text
anishift.cli.interactive.app
```

jest ownerem:

- pętli Home;
- dispatchu czterech akcji;
- powrotu po wyniku;
- obsługi KeyboardInterrupt na poziomie sesji.

### 8.5. Prompt adapter

```text
anishift.cli.interactive.prompts
```

jest ownerem:

- stylu Questionary;
- select;
- pause;
- budowy footera;
- snapshotu szerokości i wysokości terminala.

### 8.6. Home

```text
anishift.cli.interactive.home
```

jest ownerem:

- tytułu;
- rozmieszczenia maskotki;
- dokładnej listy czterech akcji;
- wywołania select Home.

### 8.7. Mascot

```text
anishift.cli.interactive.mascot
```

jest ownerem dekodowania spakowanego PNG i konwersji do półbloków terminalowych.

### 8.8. Progress

```text
anishift.cli.interactive.progress
```

jest ownerem:

- mapowania eventów na Rich;
- jednej linii per grupa;
- spinner/bar;
- retry/fallback;
- terminal row.

### 8.9. Backend

```text
AppService / scheduler / handlers
```

pozostają ownerem rzeczywistej pracy i eventów.

---

## 9. Twarde inwarianty PLANU 01

### I01-001

Nie dodać `textual`.

### I01-002

Nie utworzyć `anishift/tui`.

### I01-003

Nie importować `questionary` na module-level w `anishift/cli/main.py`.

### I01-004

`doctor`, `setup` i `run --preset` nie mogą załadować Questionary ani prompt_toolkit.

### I01-005

Bare invocation buduje dokładnie jeden `AppService`.

### I01-006

Home ma dokładnie cztery akcje.

### I01-007

Auto jest pierwsze i domyślne.

### I01-008

Home nie pokazuje ustawień.

### I01-009

Maskotka czyta wyłącznie spakowany PNG, nie uruchamia subprocessu i nie może zablokować Home.

### I01-010

Progress używa istniejącego `MultiProgressManager`.

### I01-011

Tłumaczenie nie pokazuje pośredniego procentu.

### I01-012

TTS pokazuje eventowy procent.

### I01-013

Retry/fallback aktualizują istniejący wiersz.

### I01-014

Jedna grupa ma jeden wiersz.

### I01-015

Noninteractive output pozostaje zgodny z dotychczasowymi testami.

### I01-016

Expected refusal nie kończy interactive process tracebackiem.

### I01-017

Nie modyfikować application scheduler ani handlers.

### I01-018

Nie kopiować legacy `pipeline_ui.py`.

### I01-019

Nie dodawać globalnego UI state.

### I01-020

Nie commitować przed finalnym PASS.

---

## 10. Docelowe drzewo po PLANIE 01

```text
anishift/cli/
├── AGENTS.md
├── __init__.py
├── console.py
├── main.py
├── run.py
└── interactive/
    ├── __init__.py
    ├── app.py
    ├── assets/
    │   ├── __init__.py
    │   └── slime_transparent_4k.png
    ├── home.py
    ├── mascot.py
    ├── progress.py
    └── prompts.py

tests/cli/
├── test_console.py
├── test_main.py
├── test_run.py
├── test_interactive_app.py
├── test_interactive_home.py
└── test_interactive_progress.py
```

Nie tworzyć:

```text
anishift/interactive/
anishift/tui/
screens/
widgets/
routes/
dialogs/
ui_state.py
theme.py w interactive
event_bus.py
progress_manager.py będącego kopią utils
```

---

## 11. Dozwolone pliki

### 11.1. Pliki do utworzenia

```text
anishift/cli/run.py
anishift/cli/interactive/__init__.py
anishift/cli/interactive/app.py
anishift/cli/interactive/assets/__init__.py
anishift/cli/interactive/assets/slime_transparent_4k.png
anishift/cli/interactive/home.py
anishift/cli/interactive/mascot.py
anishift/cli/interactive/progress.py
anishift/cli/interactive/prompts.py
tests/cli/test_interactive_app.py
tests/cli/test_interactive_home.py
tests/cli/test_interactive_progress.py
```

### 11.2. Pliki do modyfikacji

```text
pyproject.toml            wyłącznie przez uv add
uv.lock                   wyłącznie przez uv add
anishift/cli/main.py
anishift/cli/AGENTS.md
tests/cli/test_main.py
tests/cli/test_run.py
```

### 11.3. Pliki tylko do odczytu

```text
AGENTS.md
anishift/AGENTS.md
anishift/application/AGENTS.md
anishift/application/events.py
anishift/application/planning.py
anishift/application/results.py
anishift/application/service.py
anishift/application/scheduler.py
anishift/application/scheduler_runtime.py
anishift/application/translation_handler.py
anishift/application/tts_handler.py
anishift/application/audio_handler.py
anishift/application/extraction_handler.py
anishift/application/composition_handler.py
anishift/bootstrap.py
anishift/config/presets.py
anishift/config/user_settings.py
anishift/utils/rich_console/AGENTS.md
anishift/utils/rich_console/__init__.py
anishift/utils/rich_console/progress/multi.py
anishift/utils/rich_console/theme.py
tests/AGENTS.md
```

### 11.4. Pliki i obszary zakazane

```text
anishift/application/**
anishift/services/**
anishift/config/**
anishift/pipeline/**
anishift/tui/**
anishift/setup/**
anishift/utils/rich_console/**
tests/application/**
tests/services/**
config/**
workspace/**
external/**
.github/**
scripts/hooks/**
```

Wyjątek: pliki z sekcji read-only wolno czytać, nie wolno modyfikować.

Jeżeli implementacja wymaga zmiany pliku spoza allowlisty:

```text
STOP
REPORT BLOCKER
NO SILENT SCOPE EXPANSION
```

---

## 12. Kontrakt `anishift/cli/run.py`

### 12.1. Cel

Oddzielić UI-neutralny Auto flow od rendererów Typer i Interactive CLI.

### 12.2. Publiczne DTO

Dodać:

```python
@dataclass(frozen=True, slots=True)
class AutoRunBlocker:
    scope: str
    message: str
```

```python
@dataclass(frozen=True, slots=True)
class AutoRunRefusal:
    message: str
    suggestion: str = ""
    blockers: tuple[AutoRunBlocker, ...] = ()
```

```python
@dataclass(frozen=True, slots=True)
class PreparedAutoRun:
    preset_id: str
    workspace: InspectedWorkspace
    group_ids: tuple[str, ...]
    plan: ExecutionPlan
```

Nazwy mogą zostać lokalnie dopasowane, jeżeli zachowują dokładnie ten kontrakt.

### 12.3. `prepare_auto_run`

Sygnatura:

```python
def prepare_auto_run(
    service: AppService,
    preset_id: str,
) -> PreparedAutoRun | AutoRunRefusal
```

Kolejność:

1. `workspace = service.discover()`;
2. jeżeli brak grup, zwróć refusal;
3. `preset = service.get_preset(preset_id)`;
4. `group_ids = ready_group_ids(workspace.groups)`;
5. jeżeli puste, zwróć refusal;
6. `plan = service.plan_auto(group_ids, preset)`;
7. zbierz blocking problems;
8. jeżeli istnieją, zwróć refusal z blockerami;
9. zaloguj bezpieczne metadane;
10. zwróć `PreparedAutoRun`.

### 12.4. Refusal messages

Zachować semantykę obecnych komunikatów:

```text
The workspace holds no source group to run.
No discovered source group is ready to run.
The plan cannot run because of a blocking problem.
```

Noninteractive renderer może nadal używać angielskich stabilnych komunikatów.

Interactive renderer tłumaczy warstwę prezentacji na polski.

### 12.5. `execute_auto_run`

Sygnatura:

```python
def execute_auto_run(
    service: AppService,
    prepared: PreparedAutoRun,
    sink: RunEventSink,
) -> RunResult
```

Ma wywołać:

```python
service.execute(prepared.plan, sink)
```

Nie łapie wyjątków prezentacyjnie.

### 12.6. Zakazy

`run.py` nie importuje:

- Rich;
- Questionary;
- Typer;
- `anishift.services`;
- scheduler;
- concrete handlers.

---

## 13. Kontrakt `anishift/cli/main.py`

### 13.1. Bare callback

Obecne:

```text
service -> _run_preset(default)
```

zastąpić:

```text
service -> lazy import run_interactive -> run_interactive(service)
```

### 13.2. Lazy import

Import Interactive CLI znajduje się wewnątrz bare branch.

### 13.3. Technical subcommands

`doctor`, `setup`, `run --preset` nie zmieniają publicznej składni.

### 13.4. Noninteractive run

`_run_preset` ma użyć `prepare_auto_run()` i `execute_auto_run()`.

### 13.5. Output compatibility

Zachować:

- exit codes;
- line-per-group report;
- relative path rendering;
- safe errors;
- `_QuietRunEvents` lub równoważny sink;
- brak spinnera/progress w `run --preset`.

### 13.6. Process boundary

Zachować kolejność:

```text
UTF-8
-> logger
-> Typer
-> critical unexpected exception
-> logger shutdown
```

### 13.7. Błąd startupu

Jeżeli `production_service()` nie powstanie:

- pokaż istniejący bezpieczny błąd;
- exit nonzero;
- nie próbuj uruchomić Home bez serwisu.

---

## 14. Kontrakt `interactive/prompts.py`

### 14.1. Cel

Jedno miejsce integracji Questionary.

### 14.2. Typ wyboru

Minimalny DTO:

```python
@dataclass(frozen=True, slots=True)
class PromptChoice:
    title: str
    value: str
```

W PLANIE 01 wystarczy `str` jako transport wartości.

### 14.3. Adapter

Publiczna klasa albo protokół:

```python
class InteractivePrompts(Protocol):
    def select(
        self,
        choices: Sequence[PromptChoice],
        *,
        default: str,
        footer: str,
    ) -> str: ...

    def pause(self, message: str) -> None: ...
```

Produkcja:

```python
class QuestionaryPrompts:
    ...
```

### 14.4. Questionary style

Zdefiniować lokalny styl z maksymalnie kilkoma klasami:

```text
pointer
highlighted
selected
text
separator
instruction
question
answer
validation-toolbar
```

Kolory:

```text
accent: #5c9cf5
text: #eeeeee
muted: #808080 / #3c3c3c
error: czerwony
```

### 14.5. Home select

Użyć publicznego `questionary.select`.

Nie importować `InquirerControl`, `Application` ani prywatnych helperów Questionary.

### 14.6. Footer

Dodać jako `questionary.Separator`.

Separator:

- jest ostatni;
- nie jest selectable;
- używa muted style;
- nie zmienia zwracanej wartości.

### 14.7. Terminal width i geometria

Pure helpers:

```python
def resolve_home_geometry(columns: int, rows: int = 24) -> HomeGeometry
def home_footer(version: str, directory: str, geometry: HomeGeometry) -> str
```

Zachowanie:

```text
szeroki terminal -> maskotka + pełny wordmark, wspólnie wycentrowane
średni terminal  -> pełny wordmark bez maskotki
wąski terminal   -> jednoliniowy ANISHIFT, menu i skrócona ścieżka
```

Adapter przekazuje do `questionary.select()` pointer z paddingiem należącym do
`HomeGeometry`, np. logicznie:

```text
<left padding>▶
```

Questionary samo wstawia równoważną pustą szerokość dla nieaktywnych pozycji, więc
wszystkie etykiety pozostają w jednej kolumnie.

Nie wpisywać paddingu do każdego `Choice.title`.

Nie czytać rozmiaru w testach bez możliwości wstrzyknięcia.

### 14.8. Pause

Użyć publicznego `questionary.press_any_key_to_continue()` albo równoważnego publicznego
API.

Nie używać surowego `input()`.

### 14.9. KeyboardInterrupt

Adapter nie połyka `KeyboardInterrupt`.

Pętla interactive podejmuje decyzję.

### 14.10. Zakazy

Nie dodawać:

- własnego keybinding managera;
- raw prompt_toolkit layout;
- mouse handlers;
- globalnego singletona sesji;
- command parsera.

---

## 15. Kontrakt `interactive/mascot.py`

### 15.1. Publiczne API

```python
def mascot_art(columns: int, rows: int) -> Text | None
```

### 15.2. Renderer

Renderer:

- czyta spakowany `assets/slime_transparent_4k.png` przez `importlib.resources`;
- zachowuje proporcje i przezroczystość;
- łączy po dwa piksele w znak `▀` albo `▄` z true-color foreground/background;
- cache'uje wyłącznie gotowy render dla danego rozmiaru;
- zwraca `None` przy braku lub uszkodzeniu assetu.

### 15.3. Zakazy

Nie uruchamia subprocessu, Chafa, Sixel ani zewnętrznego asset path użytkownika.

---

## 16. Kontrakt `interactive/home.py`

### 16.1. Action enum

```python
class HomeAction(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"
    SETTINGS = "settings"
    EXIT = "exit"
```

### 16.2. Dokładna kolejność

```python
AUTO
MANUAL
SETTINGS
EXIT
```

### 16.3. Publiczne API

```python
def ask_home_action(
    prompts: InteractivePrompts,
    *,
    version: str,
) -> HomeAction
```

### 16.4. Render

Przed promptem:

1. `console.clear()`;
2. render pionowego paddingu;
3. render maskotki 20×14 po lewej i stałego wordmarku po prawej, bez ramki;
4. render małego odstępu;
5. uruchom wycentrowany select z hintem i dolnym statusem.

### 16.5. Tytuł

Wordmark reużywa sześciowierszowego kroju z poprzedniego TUI bez importowania Textual.
Wypełnienie i obrys używają cieniowanej palety cyjan–fiolet–róż pochodzącej ze slime'a.
Nie otacza go ramka.

Wszystkie wiersze mają stałą szerokość 57 kolumn.

### 16.6. Choices

Label dokładnie:

```text
Auto
Ręczny
Ustawienia
Wyjście
```

### 16.7. Default

`AUTO`.

### 16.8. Brak statusów

Home nie pobiera:

- settings snapshot;
- model catalog;
- engine availability;
- workspace discovery;
- preset name.

### 16.9. Wąski terminal

Home zachowuje menu, ukrywa maskotkę, przełącza wordmark na jednoliniowy i skraca
ścieżkę od lewej.

### 16.10. Testowalność

Lista choices i default muszą być możliwe do sprawdzenia bez uruchamiania prawdziwego
Questionary.

---

## 17. Kontrakt `interactive/progress.py`

### 17.1. Publiczna klasa

```python
class RichRunProgress(RunEventSink):
    def __enter__(self) -> RichRunProgress: ...
    def __exit__(...) -> None: ...
    def emit(self, event: RunEvent) -> None: ...
```

Konstruktor przyjmuje:

```python
PreparedAutoRun
```

### 17.2. Prealokacja

Na wejściu:

1. zmapuj group IDs na czytelne `source.stem`;
2. zbuduj mapę tasków;
3. dodaj jeden wiersz per `plan.groups`;
4. zachowaj naturalną kolejność.

### 17.3. MultiProgressManager

Rekomendowane ustawienia:

```text
align = independent
show_bar = false
show_percentage = false
show_spinner = true
show_elapsed = true
show_eta = false
show_download = false
transient = false
```

`max_description_length` dopasować do realnych nazw, bez tworzenia osobnego layout
engine.

### 17.4. State per group

Minimalnie:

```text
task row id
current task id
current task kind
last event sequence
last real percent
terminal flag
```

### 17.5. TASK_QUEUED

Nie musi zmieniać aktywnego wiersza, jeśli inny task tej samej grupy już działa.

### 17.6. TASK_STARTED

- ustaw current task;
- ustaw etykietę etapu;
- spinner;
- wyłącz bar;
- nie resetuj grupy terminalnej.

### 17.7. TASK_PROGRESS — TTS

Dla `SYNTHESIZE_SPEECH`:

- clamp 0–100 zapewnia application;
- włącz bar;
- włącz percentage;
- wyłącz spinner;
- update completed.

### 17.8. TASK_PROGRESS — translation/extraction/composition

Jeżeli wartość jest tylko `100`:

- nie pokazuj paska;
- pozostaw spinner do `TASK_FINISHED`.

### 17.9. TASK_PROGRESS — audio

Jeżeli message niesie fazę:

- mapuj znane fazy na polski opis;
- pozostaw spinner;
- ignoruj `0` jako procent.

### 17.10. TASK_RETRY

- zmień opis na `Ponowna próba`;
- zachowaj nazwę grupy;
- pokaż bezpieczny message;
- użyj warning;
- nie dodawaj wiersza.

### 17.11. TASK_FALLBACK

Analogicznie:

```text
Fallback
```

### 17.12. TASK_FINISHED success

- jeżeli TTS miał realny bar, doprowadź do 100;
- zatrzymaj czas etapu dopiero, gdy grupa jest terminalna albo następny task wystartuje;
- opis może przejść na krótki completed state.

### 17.13. TASK_FINISHED failed

- czerwony `Błąd`;
- bezpieczny message;
- nie ujawniaj tracebacka;
- nie pozwól późniejszemu starszemu eventowi nadpisać.

### 17.14. GROUP_FINISHED

Zamroź wiersz:

```text
Gotowe
Błąd
Anulowano
Częściowo
```

Dokładne mapowanie partial może zostać potwierdzone z `RunResult`; event state nie musi
sam rozstrzygać partial.

### 17.15. RUN_FINISHED

Nie tworzy osobnego wiersza.

### 17.16. Sequence

Ignoruj event:

```text
sequence <= last accepted sequence for run
```

### 17.17. Po zamknięciu

`emit()` po `__exit__` jest no-op.

### 17.18. Thread safety

Nie dodawać zewnętrznego locka wokół każdej metody `MultiProgressManager`, ponieważ
manager już jest thread-safe. Lokalny lock jest dozwolony tylko dla własnych map stanu.

### 17.19. Treść

Nie renderować event message, jeżeli zawiera treść biznesową poza bezpiecznym retry/
fallback/error. `RunEvent` jest już sanitizowany, ale UI nadal ogranicza ekspozycję.

---

## 18. Kontrakt `interactive/app.py`

### 18.1. Publiczne API

```python
def run_interactive(
    service: AppService,
    prompts: InteractivePrompts | None = None,
) -> None
```

Brak zwracania Typer exit code w normalnej sesji.

### 18.2. Produkcyjne prompty

Gdy `prompts is None`:

```python
prompts = QuestionaryPrompts()
```

### 18.3. Pętla

```text
while true
    action = ask_home_action()
    dispatch
```

### 18.4. AUTO

Sekwencja:

1. wyczyść Home;
2. pokaż status `Skanowanie workspace`;
3. `prepare_auto_run`;
4. jeśli refusal, pokaż błąd i pause;
5. utwórz `RichRunProgress`;
6. wykonaj;
7. zamknij progress;
8. render result;
9. pause;
10. wróć do Home.

### 18.5. MANUAL i SETTINGS

W PLANIE 01:

- pokaż krótki neutralny komunikat;
- pause;
- wróć do Home.

Nie dodawać placeholderowego modułu Settings ani Manual.

### 18.6. EXIT

Kończy pętlę.

### 18.7. Ctrl+C na Home

Kończy pętlę bez tracebacka.

### 18.8. Ctrl+C podczas Auto

- zamknij progress;
- pokaż `Anulowano`;
- pause lub bezpośredni powrót zgodnie z realnym HITL;
- nie wyświetlaj tracebacka.

### 18.9. Expected exceptions

Łapać precyzyjnie:

- `AniShiftError`;
- `OSError`;
- `KeyboardInterrupt`.

Nie łapać ogólnego `Exception` poza process boundary.

### 18.10. Result renderer

Może być małą prywatną funkcją w `app.py`.

Nie tworzyć osobnego `results.py`, dopóki rzeczywisty kod nie przekroczy spójnej
odpowiedzialności.

### 18.11. Relative paths

Produkty pokazuj przez `relative_to(workspace_root)` z bezpiecznym fallbackiem do
nazwy pliku.

### 18.12. Powrót

Użyj `prompts.pause`.

---

## 19. Kontrakt `interactive/__init__.py`

Eksportować wyłącznie:

```python
run_interactive
```

Nie re-eksportować wewnętrznych rendererów.

---

## 20. Kontrakt testów

### 20.1. Ogólne zasady

Testy:

- bez docstringów;
- bez prose comments;
- bez `__init__.py` w `tests/cli`;
- bez network;
- bez realnego Questionary terminala;
- bez patchowania prywatnych internals biblioteki.

### 20.2. `test_interactive_home.py`

Wymagane przypadki:

1. cztery choices w dokładnej kolejności;
2. Auto jako default;
3. wartości mapują się na `HomeAction`;
4. hint znajduje się bezpośrednio pod listą;
5. dolny status ma cwd po lewej i wersję po prawej;
6. wordmark nie zawiera statusów konfiguracji;
7. Home renderuje spakowaną transparentną maskotkę;
8. maskotka, wordmark i menu są wycentrowane poziomo i pionowo;
9. menu jest zwartym, wycentrowanym blokiem;
10. marker nie zostaje przy skrajnej lewej krawędzi;
11. resize wywołuje czysty rerender ze stałymi wymiarami marki;
12. Ctrl+C propaguje do app loop.

### 20.3. `test_interactive_progress.py`

Użyć fake manager albo wstrzykiwalnej factory.

Wymagane:

1. jeden row per plan group;
2. natural order;
3. translation start = blokowy pasek `0%`;
4. translation progress 100 domyka istniejący pasek;
5. TTS progress 25 pokazuje bar 25;
6. TTS retry aktualizuje ten sam row;
7. fallback aktualizuje ten sam row;
8. audio phase 0 jest spinnerem z opisem;
9. group success freezes row;
10. group failure freezes error;
11. stale sequence jest ignorowana;
12. emit po close jest no-op;
13. safe group label;
14. brak drugiego row przy stage transition.

### 20.4. `test_interactive_app.py`

Fake prompts zwracają zaplanowaną sekwencję działań.

Wymagane:

1. Auto preparation refusal -> pause -> Home;
2. Auto success -> progress -> result -> Home;
3. Auto partial -> partial summary;
4. execution `AniShiftError` -> error -> Home;
5. `KeyboardInterrupt` podczas run -> cancelled -> Home/exit bez tracebacka;
6. Settings temporary action nie woła backendu;
7. Manual temporary action nie woła backendu;
8. Exit kończy pętlę;
9. jeden service instance;
10. default preset backendu jest użyty;
11. jedna sesja używa dokładnie jednego lifecycle natywnego alternate screen;
12. zatwierdzona odpowiedź Questionary jest usuwana przed Auto.

### 20.5. `tests/cli/test_run.py`

Zachować wszystkie testy `run --preset`.

Zmienić test bare invocation:

Obecny kontrakt:

```text
bare -> immediate run
```

Nowy kontrakt:

```text
bare -> lazy interactive launcher
```

Dodać test, który patchuje `run_interactive` przez import boundary bez uruchamiania realnego
Questionary.

### 20.6. `tests/cli/test_main.py`

Rozszerzyć listę forbidden modules technicznych subkomend o:

```text
questionary
prompt_toolkit
anishift.cli.interactive
```

### 20.7. Process probe

`doctor`, `setup`, `run --preset` w subprocess probe muszą raportować pustą listę tych
modułów.

---

## 21. Przepływy danych po PLANIE 01

### 21.1. Start

```text
uv run anishift
-> main()
-> UTF-8
-> logger
-> Typer callback
-> production_service()
-> lazy import interactive
-> run_interactive(service)
```

### 21.2. Home

```text
run_interactive
-> ask_home_action
-> centered Rich title
-> Questionary select
-> HomeAction
```

### 21.3. Auto preparation

```text
HomeAction.AUTO
-> Rich status
-> prepare_auto_run
-> AppService.discover
-> default preset
-> ready groups
-> plan_auto
-> PreparedAutoRun | AutoRunRefusal
```

### 21.4. Execution

```text
PreparedAutoRun
-> RichRunProgress enter
-> execute_auto_run
-> AppService.execute
-> scheduler
-> RunEventSink.emit
-> MultiProgressManager
-> RunResult
-> RichRunProgress exit
```

### 21.5. Translation

```text
TASK_STARTED translate
-> spinner

TASK_RETRY
-> same row / warning text

TASK_FALLBACK
-> same row / fallback text

TASK_PROGRESS 100
-> no fake bar

TASK_FINISHED
-> completed stage
```

### 21.6. TTS

```text
TASK_STARTED synthesize
-> spinner

TASK_PROGRESS 0..100
-> determinate bar

TASK_RETRY
-> same row / retry

TASK_FINISHED
-> complete
```

### 21.7. Result

```text
RunResult
-> stop Live
-> render summary
-> pause
-> Home
```

### 21.8. Noninteractive

```text
anishift run --preset default
-> main.run
-> prepare_auto_run
-> _QuietRunEvents
-> execute_auto_run
-> stable line report
-> stable exit code
```

No interactive import.

---

## 22. Kolejność implementacji

Agent wykonuje dokładnie poniższą kolejność.

### Krok 1 — baseline

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline
```

Jeżeli baseline prawidłowy:

```bash
git switch -c work/interactive-cli/01-home-auto
```

Nie commitować.

### Krok 2 — dependency gate

```bash
uv add questionary
```

Następnie:

```bash
uv sync --frozen --group dev
uv run python -c "import questionary; print(questionary.__version__ if hasattr(questionary, '__version__') else 'ok')"
```

Jeżeli dependency resolution lub import nie działa na Pythonie 3.14:

```text
STOP
BLOCKER
NO SUBSTITUTE LIBRARY
```

### Krok 3 — prompts adapter

Utworzyć:

```text
anishift/cli/interactive/__init__.py
anishift/cli/interactive/prompts.py
```

Zaimplementować:

- style;
- choice DTO;
- select;
- pause;
- footer helper;
- terminal width injection.

Dodać targeted test pure footer.

### Krok 4 — maskotka

Skopiować wyłącznie zaakceptowany `slime_transparent_4k.png` do package assets i
utworzyć `interactive/mascot.py`. Renderer używa Pillow i półbloków Rich, bez Chafa.

### Krok 5 — Home

Utworzyć:

```text
anishift/cli/interactive/home.py
tests/cli/test_interactive_home.py
```

Uruchomić:

```bash
uv run pytest tests/cli/test_interactive_home.py -q
```

### Krok 6 — lokalny visual runner

Nie dodawać throwaway scriptu do repo.

Uruchomić Home przez istniejący moduł lub krótkie `python -c` bez commita.

### Krok 7 — GATE A

Agent zatrzymuje się.

Raportuje:

```text
STATUS: READY_FOR_HOME_HITL
```

Nie implementuje jeszcze run flow ani progress.

Użytkownik testuje Home w Windows Terminal.

### Krok 8 — po PASS HOME

Dopiero po wiadomości:

```text
HOME PASS
```

kontynuować.

### Krok 9 — shared run flow

Utworzyć:

```text
anishift/cli/run.py
```

Przenieść logicznie preflight z `main.py`.

Najpierw zachować noninteractive testy.

Uruchomić:

```bash
uv run pytest tests/cli/test_run.py tests/cli/test_main.py -q
```

### Krok 10 — progress renderer

Utworzyć:

```text
anishift/cli/interactive/progress.py
tests/cli/test_interactive_progress.py
```

Zaimplementować event mapping.

Uruchomić:

```bash
uv run pytest tests/cli/test_interactive_progress.py -q
```

### Krok 11 — interactive loop

Utworzyć:

```text
anishift/cli/interactive/app.py
tests/cli/test_interactive_app.py
```

Podłączyć Home, Auto, result, errors, pause.

Całą pętlę uruchomić w jednym screen context dostarczonym przez `QuestionaryPrompts`.
Przejście do Auto ma wyczyścić natywny output przed preflightem, a powrót do Home ma
zastąpić wynik zamiast dopisywać kolejny ekran do scrollbacku. Prompt wyboru używa
`erase_when_done=True`, aby nie pozostawiać niebieskiego `Auto` nad progressem.

### Krok 12 — entrypoint

Zmodyfikować:

```text
anishift/cli/main.py
```

Bare -> Interactive.

`run --preset` -> shared run flow.

### Krok 13 — CLI docs

Zaktualizować:

```text
anishift/cli/AGENTS.md
```

Tylko fakty po zmianie:

- bare interactive;
- lazy toolkit imports;
- technical subcommands noninteractive;
- nowy katalog `interactive/`;
- wspólny `run.py`.

### Krok 14 — targeted tests

```bash
uv run pytest \
  tests/cli/test_interactive_home.py \
  tests/cli/test_interactive_progress.py \
  tests/cli/test_interactive_app.py \
  tests/cli/test_main.py \
  tests/cli/test_run.py \
  -q
```

### Krok 15 — static gates przed finalnym HITL

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
git diff --check
```

Nie uruchamiać jeszcze pełnego pytest, jeżeli targeted są zielone; pełny suite po finalnym
PASS.

### Krok 16 — diff review

```bash
git status --short
git diff --stat
git diff --name-only
git diff --check
```

Porównać z allowlistą.

### Krok 17 — GATE B

Agent raportuje:

```text
STATUS: READY_FOR_AUTO_HITL
```

Bez commita.

### Krok 18 — finalny HITL

Użytkownik testuje:

- Home;
- Auto;
- realny progress;
- realne tłumaczenie spinner;
- TTS percentage, jeśli plan ma TTS;
- retry/fallback przez fake/test lub realną awarię, jeśli bezpieczna;
- wynik;
- powrót;
- Ctrl+C;
- `run --preset`.

### Krok 19 — PASS

Po:

```text
PASS
```

uruchomić:

```bash
uv run pytest
git diff --check
```

### Krok 20 — commit

Jeden commit:

```text
feat(cli): add interactive home and automatic run
```

### Krok 21 — push

```bash
git push -u origin work/interactive-cli/01-home-auto
```

Raportować SHA.

---

## 23. GATE A — CO MASZ SPRAWDZIĆ W HOME

Agent ma wypisać tę instrukcję w ostatniej odpowiedzi przed przerwą.

### Przygotowanie

1. Otwórz zewnętrzny Windows Terminal.
2. Przejdź do repo.
3. Upewnij się, że aktywny branch to `work/interactive-cli/01-home-auto`.
4. Uruchom wskazaną przez agenta komendę podglądu Home.
5. Nie oceniaj jeszcze Auto, Settings ani Manual.

### HOME-01 — struktura

Sprawdź kolejność:

```text
kolorowy slime | sześciowierszowy ANISHIFT
Auto
Ręczny
Ustawienia
Wyjście
↑↓ · Enter
cwd                                             version
```

### HOME-02 — minimalizm

Sprawdź, że nie ma:

- modelu;
- głosu;
- workspace;
- presetu;
- statusu API;
- boxów;
- command bara.

### HOME-03 — wordmark

Sprawdź:

- sześć równych wierszy bez zawijania;
- cieniowaną paletę cyjan–fiolet–róż wspólną ze slime'em;
- wycentrowanie całego bloku razem ze slime’em;
- brak znaków ramki `+`, `-`, `|`;
- jednoliniowy fallback przy wąskim terminalu.

### HOME-04 — maskotka i centrum

Sprawdź:

- wyświetla się dostarczony slime bez czarnego prostokąta;
- proporcje slime'a pozostają naturalne;
- slime nie zmienia rozmiaru przy resize;
- slime, wordmark i menu tworzą zwarty blok bez ramki;
- blok jest wycentrowany poziomo i pionowo nad statusem.

### HOME-05 — menu

Sprawdź:

- cztery pozycje;
- `Auto` aktywne na start;
- marker z lewej;
- brak `[x]` po prawej;
- strzałki działają płynnie;
- Enter wybiera.

### HOME-06 — kolor

Sprawdź:

- aktywny wybór ma dokładnie odcień `#5c9cf5`;
- wordmark używa kontrolowanej palety slime'a bez jednolitego niebieskiego gradientu;
- treść jest jasna, a kreski i hint stonowane;
- brak chaosu kolorów;
- aktywna pozycja jest czytelna.

### HOME-07 — hint i dolny status

Sprawdź:

- `↑↓ · Enter` jest bezpośrednio pod listą;
- katalog jest po lewej, wersja po prawej;
- status jest w ostatnim wierszu terminala;
- obie części dochodzą do skrajnych bezpiecznych boków;
- brak nakładania;
- resize ponownie centruje Home bez rozrzucania elementów;
- wąskie okno ukrywa maskotkę, przełącza wordmark i skraca ścieżkę od lewej.

### HOME-08 — redraw

Przejdź po menu kilkanaście razy.

Oczekiwane:

- brak śmieci w scrollbacku;
- brak migania;
- brak podwójnych promptów;
- brak przesuwania layoutu.

### Raport

Jeżeli jest dobrze:

```text
HOME PASS
```

Jeżeli nie:

```text
HOME-XX
dokładny objaw
```

---

## 24. GATE B — CO MASZ SPRAWDZIĆ W APLIKACJI

### Przygotowanie

1. Użyj Windows Terminal.
2. Umieść znany działający MKV w workspace.
3. Upewnij się, że aktywna konfiguracja ma wymagane klucze.
4. Uruchom:

```bash
uv run anishift
```

### AUTO-01 — startup

Oczekiwane:

- Home;
- Auto active;
- pipeline nie startuje sam.

### AUTO-02 — Enter

Naciśnij Enter.

Oczekiwane:

- Home znika;
- pojawia się status skanowania;
- run startuje raz;
- brak drugiego promptu.

### AUTO-03 — wiersze

Przy wielu grupach:

- jedna linia per grupa;
- naturalna kolejność;
- brak dopisywania nowej linii przy każdym etapie.

### AUTO-04 — tłumaczenie

Podczas tłumaczenia:

- blokowy pasek Rich;
- nazwa grupy;
- elapsed;
- `0% → 100%` bez wymyślonych wartości pośrednich;
- brak tekstu napisów.

### AUTO-05 — TTS

Jeżeli przebieg obejmuje TTS:

- rzeczywisty pasek;
- procent rośnie;
- nie skacze wstecz;
- po retry wiersz nie znika.

### AUTO-06 — audio i composition

Oczekiwane:

- spinner/faza;
- brak fałszywego paska;
- ten sam wiersz.

### AUTO-07 — sukces

Oczekiwane:

- progress zatrzymany;
- krótkie podsumowanie;
- produkty względne;
- brak tracebacka;
- powrót po klawiszu.

### AUTO-08 — pusty workspace

Usuń/odsuń wejścia i uruchom Auto.

Oczekiwane:

- krótki komunikat;
- brak planowania;
- powrót Home;
- proces żyje.

### AUTO-09 — blocked/unready

Przetestuj, jeśli masz bezpieczny materiał.

Oczekiwane:

- przyczyna;
- brak execute;
- powrót.

### AUTO-10 — Ctrl+C na Home

Oczekiwane:

- czyste wyjście;
- brak tracebacka.

### AUTO-11 — Ctrl+C podczas runu

Oczekiwane:

- `Anulowano`;
- brak stuck progress;
- brak tracebacka;
- terminal odzyskuje kursor.

### AUTO-12 — technical command

Uruchom:

```bash
uv run anishift run --preset default
```

Oczekiwane:

- brak Home;
- brak Questionary;
- stabilny line output;
- prawidłowy exit code.

### AUTO-13 — doctor/setup help

```bash
uv run anishift doctor --help
uv run anishift setup --help
```

Oczekiwane:

- brak Interactive CLI;
- brak import error.

### AUTO-14 — retry/fallback

Jeżeli realne wywołanie wywoła retry:

- ten sam wiersz;
- opis `Ponowna próba`;
- brak nowej linii;
- po odzyskaniu etap kontynuuje.

Jeżeli nie da się bezpiecznie wymusić realnego retry, dowodem jest targeted test plus normalny
HITL pozostałych zachowań.

### AUTO-15 — konsola

Podczas całej checklisty:

```text
brak tracebacka w normalnych błędach
brak UnicodeEncodeError
brak prompt_toolkit warning
brak nested Live error
brak cursor corruption
brak sekretów
brak absolutnych ścieżek
brak wymyślonego pośredniego procentu translation
```

### AUTO-16 — interaktywny viewport

Uruchom Auto i obserwuj przejście z Home do przygotowania oraz progressu.

Oczekiwane:

- Home znika przed rozpoczęciem Auto;
- progress odświeża istniejące wiersze zamiast dopisywać historię zmian;
- wynik i powrót Home zastępują zawartość tego samego alternate screen;
- po wyjściu wraca poprzedni bufor powłoki i poprawny kursor.

### Raport

PASS:

```text
PASS
```

FAIL:

```text
AUTO-XX
dokładny objaw
```

---

## 25. Budżet zmiany

Budżet jest alarmem, nie celem pisania pod licznik.

### Produkcja

Orientacyjnie:

```text
anishift/cli/run.py                         100–220
interactive/prompts.py                     100–220
interactive/mascot.py                       20–70
interactive/home.py                         60–140
interactive/progress.py                    220–420
interactive/app.py                         140–280
```

### Testy

Orientacyjnie:

```text
test_interactive_home.py                    80–180
test_interactive_progress.py               180–340
test_interactive_app.py                    160–300
zmiany test_main/test_run                   40–140
```

### Alarm

Jeżeli diff przekracza:

```text
> 1400 nowych linii produkcyjnych
> 1200 nowych linii testów
> 16 zmienionych plików
```

agent zatrzymuje się i wyjaśnia, co spowodowało wzrost.

Nie tworzy kolejnego frameworka, by „uporządkować” przekroczenie.

---

## 26. Targeted verification

### Po Home

```bash
uv run pytest tests/cli/test_interactive_home.py -q
```

### Po run flow

```bash
uv run pytest tests/cli/test_run.py tests/cli/test_main.py -q
```

### Po progress

```bash
uv run pytest tests/cli/test_interactive_progress.py -q
```

### Po app loop

```bash
uv run pytest \
  tests/cli/test_interactive_home.py \
  tests/cli/test_interactive_progress.py \
  tests/cli/test_interactive_app.py \
  tests/cli/test_main.py \
  tests/cli/test_run.py \
  -q
```

### Static

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
```

### Po PASS

```bash
uv run pytest
```

---

## 27. Kontrola diffu

Końcowa lista może zawierać wyłącznie:

```text
pyproject.toml
uv.lock
anishift/cli/AGENTS.md
anishift/cli/main.py
anishift/cli/run.py
anishift/cli/interactive/__init__.py
anishift/cli/interactive/app.py
anishift/cli/interactive/assets/__init__.py
anishift/cli/interactive/assets/slime_transparent_4k.png
anishift/cli/interactive/home.py
anishift/cli/interactive/mascot.py
anishift/cli/interactive/progress.py
anishift/cli/interactive/prompts.py
tests/cli/test_main.py
tests/cli/test_run.py
tests/cli/test_interactive_app.py
tests/cli/test_interactive_home.py
tests/cli/test_interactive_progress.py
```

Każdy inny plik raportować jako:

```text
UNEXPECTED FILE
```

---

## 28. Obowiązkowy raport przed GATE A

```text
STATUS: READY_FOR_HOME_HITL

Branch:
work/interactive-cli/01-home-auto

Base:
bc0841bdd4bc192587f5b3eff5952ed7c4ee1c32

Commit:
NONE - awaiting HOME HITL

Implemented:
- Questionary dependency
- Pillow dependency
- prompt adapter
- Home
- packaged transparent mascot renderer

Changed files:
- ...

Targeted tests:
- home tests: PASS/FAIL
- ruff changed scope: PASS/FAIL
- mypy changed scope: PASS/FAIL
- git diff --check: PASS/FAIL

Unexpected files:
NONE albo pełna lista

CO MASZ TERAZ SPRAWDZIĆ W HOME:
[pełna praktyczna checklista HOME-01..HOME-08]

CELOWO JESZCZE NIE DZIAŁA:
- Auto backend
- Settings
- Manual
- animation
```

Agent nie odsyła użytkownika wyłącznie do numerów w pliku. Wypisuje instrukcję na
czacie.

---

## 29. Obowiązkowy raport przed GATE B

```text
STATUS: READY_FOR_AUTO_HITL

Branch:
work/interactive-cli/01-home-auto

Base:
bc0841bdd4bc192587f5b3eff5952ed7c4ee1c32

Commit:
NONE - awaiting final HITL

Interactive entry:
anishift/cli/interactive/app.py

Shared Auto flow:
anishift/cli/run.py

Progress owner:
anishift/cli/interactive/progress.py

Changed production files:
- ...

Changed test files:
- ...

Automated gates:
- targeted CLI: PASS/FAIL
- ruff: PASS/FAIL
- format: PASS/FAIL
- mypy current: PASS/FAIL
- mypy linux: PASS/FAIL
- git diff --check: PASS/FAIL

Noninteractive compatibility:
- run --preset tests: PASS/FAIL
- toolkit import probe: PASS/FAIL

Unexpected files:
NONE albo pełna lista

CO MASZ TERAZ SPRAWDZIĆ W APLIKACJI:
[pełna praktyczna checklista AUTO-01..AUTO-15]

CELOWO JESZCZE NIE DZIAŁA:
- Settings
- Manual
- Chafa
- animation
```

---

## 30. Reguła PASS / FAIL

### 30.1. HOME PASS

Po:

```text
HOME PASS
```

agent kontynuuje ten sam branch i working tree.

Nie tworzy commita po samym Home.

### 30.2. HOME FAIL

Użytkownik podaje:

```text
HOME-XX
objaw
```

Agent:

- nie integruje Auto;
- poprawia Home;
- uruchamia targeted test;
- ponownie raportuje READY_FOR_HOME_HITL.

### 30.3. Final PASS

Po:

```text
PASS
```

agent:

1. uruchamia pełny `uv run pytest`;
2. uruchamia `git diff --check`;
3. sprawdza allowlistę;
4. tworzy jeden commit;
5. pushuje branch;
6. raportuje SHA.

### 30.4. Final FAIL

Użytkownik podaje:

```text
AUTO-XX
objaw
```

Agent:

- nie tworzy końcowego commita;
- nie przechodzi do PLANU 02;
- poprawia ten sam branch;
- uruchamia potrzebne targeted tests;
- ponownie raportuje READY_FOR_AUTO_HITL.

---

## 31. Zakazane skróty implementacyjne

Nie wolno:

- przywrócić Textual;
- skopiować `archive/textual-tui`;
- skopiować `main:anishift/cli/pipeline_ui.py` 1:1;
- importować legacy `anishift.pipeline`;
- budować własnego select widgetu;
- używać raw prompt_toolkit;
- monkeypatchować Questionary;
- forka Questionary;
- otwierać więcej niż jeden alternate screen w jednej sesji;
- zagnieżdżać Rich Live albo budować własną pętlę redrawu;
- dodać globalny command loop;
- dodać slash commands;
- wstawić model/głos/status na Home;
- użyć `[x]` po prawej;
- pokazać fake translation percent;
- streamować tekst napisów do terminala;
- logować prompt/payload;
- kopiować inne PNG 4K poza zaakceptowanym `slime_transparent_4k.png`;
- uruchamiać Chafa;
- tworzyć mascot animation;
- modyfikować scheduler;
- dodawać eventy tylko pod UI;
- przechowywać RunEvent state w globalnym singletonie;
- łapać `Exception` w app loop;
- wyświetlać traceback dla expected errors;
- zmieniać noninteractive exit codes;
- importować Questionary w technical subcommands;
- commitować przed PASS;
- przechodzić do Settings lub Manual przy okazji.

---

## 32. Definicja ukończenia

PLAN 01 jest ukończony wyłącznie, gdy:

```text
[ ] Branch powstał z bc0841bdd4bc192587f5b3eff5952ed7c4ee1c32.
[ ] Questionary został dodany przez uv.
[ ] Textual nie wrócił.
[ ] Istnieje lazy interactive package.
[ ] Home ma dokładnie cztery akcje.
[ ] Auto jest domyślne.
[ ] Home nie pokazuje konfiguracji.
[ ] Marker jest po lewej.
[ ] Footer pokazuje wersję.
[ ] Wąski Home ukrywa maskotkę i skraca ścieżkę od lewej.
[ ] Maskotka używa spakowanego PNG i nie uruchamia subprocessu.
[ ] HOME HITL otrzymał PASS.
[ ] Auto używa wspólnego run flow.
[ ] run --preset używa tego samego preflight.
[ ] Technical subcommands nie ładują toolkitu.
[ ] Jedna grupa ma jeden progress row.
[ ] Translation używa dynamicznego paska `0% → 100%`.
[ ] TTS używa rzeczywistego procentu.
[ ] Audio phases używają spinnera.
[ ] Retry aktualizuje istniejący row.
[ ] Fallback aktualizuje istniejący row.
[ ] Group terminal freezes row.
[ ] Result odróżnia success/partial/failure/cancel.
[ ] Expected error wraca do Home.
[ ] Home, Auto i wynik używają jednego alternate screen.
[ ] Progress odświeża wiersze w miejscu bez historii kolejnych stanów.
[ ] Wyjście przywraca poprzedni bufor powłoki i kursor.
[ ] Błędy nie ujawniają sekretów.
[ ] Produkty są ścieżkami względnymi.
[ ] Ctrl+C nie zostawia tracebacka w normalnym workflow.
[ ] Targeted tests przechodzą.
[ ] Ruff przechodzi.
[ ] Ruff format przechodzi.
[ ] Mypy current przechodzi.
[ ] Mypy Linux przechodzi.
[ ] Diff check przechodzi.
[ ] Diff zawiera tylko allowlistę.
[ ] Agent wypisał pełny HOME HITL.
[ ] Agent wypisał pełny AUTO HITL.
[ ] Użytkownik podał finalny PASS.
[ ] Pełny pytest przeszedł po PASS.
[ ] Powstał dokładnie jeden końcowy commit.
[ ] Branch został wypchnięty.
```

Dopiero wtedy wolno napisać:

```text
PLAN 01 VERIFIED / COMMITTED
READY FOR PLAN 02 — SETTINGS
```

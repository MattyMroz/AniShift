---
kind: plan
status: implemented-awaiting-owner-acceptance
implementation_head: 7e3aecc
baseline: 30b6c4d1d352373b6941ecb9a1eafe41fc1e0183 (work/planning/automation-and-subtitles)
branch: work/local-automation/01-watch
created: 2026-09-05
---

# Plan 01: Czuwanie — nowy plik w bibliotece sam przechodzi Auto

## Cel

Proces czuwania działa w tle od zalogowania do Windows. Gdy w `workspace/` albo w jego podfolderze
serii pojawi się gotowy plik wideo, otwiera się okno terminala z obróbką tej partii przez
istniejące Auto, a po zakończeniu okno samo się zamyka. Zamknięcie okna nie kończy czuwania.
Gotowy odcinek jest dostępny od razu po własnym zakończeniu, tak jak dziś w Auto.

Ten plan jest pierwszym rezultatem [masterplanu](../masterplan.md) i zastępuje jego fazy P02–P04
oraz P12 prostszym mechanizmem: brak SQLite, brak kolejki komend, brak kopiowania do stagingu,
brak IPC między procesami poza kodem wyjścia. Pobieranie, wyszukiwanie i subskrypcje są
kolejnymi planami.

## Rezultat użytkownika

- `anishift autostart enable` rejestruje zadanie Windows i od razu uruchamia czuwanie; od tej pory
  czuwanie startuje przy każdym logowaniu, bez okna.
- Wrzucenie `Seria/odcinek-05.mkv` do biblioteki: po ~10 s od końca kopiowania otwiera się okno
  z ekranem Auto tylko dla tej partii. Produkty lądują obok źródła, w tym samym podfolderze.
  Po zakończeniu okno pokazuje wynik przez 10 s i zamyka się. Dowolny klawisz zamyka wcześniej.
- Plik dorzucony w trakcie obróbki czeka; po zamknięciu okna czuwanie od razu otwiera następne.
- Zamknięcie okna w trakcie (X albo Ctrl+C) anuluje tylko tę partię. Czuwanie trwa. Ta partia
  nie jest ponawiana, dopóki plik się nie zmieni albo czuwanie nie zostanie uruchomione ponownie.
- `anishift watch status` mówi, czy czuwanie działa; `anishift watch stop` je zatrzymuje;
  `anishift watch` uruchamia je w bieżącym terminalu (do podglądu i debugowania).
- `anishift autostart disable` usuwa zadanie i zatrzymuje czuwanie.

## Warunki końcowe

- [x] W01: discovery znajduje grupy w podfolderach `workspace/` z pominięciem `temp/` i katalogów
      zaczynających się od kropki; dwie serie z `01.mkv` mają różne `group_id`; płaska biblioteka
      zachowuje dotychczasowe `group_id`.
- [x] W02: grupa jest przyjmowana do partii tylko wtedy, gdy `group_is_ready` jest prawdą, brakuje
      jej co najmniej jednego produktu żądanego przez domyślny preset, a jej pliki źródłowe są
      stabilne (Algorytm). Gotowe grupy nie są przetwarzane ponownie.
- [x] W03: partia przechodzi przez `prepare_auto_run` i `execute_plan`; zero nowych handlerów,
      zero zmian w GraphScheduler i limitach dostawców. Czuwanie ma najwyżej jedno okno partii naraz.
- [x] W04: czuwanie jest jedną instancją na bibliotekę; druga instancja odmawia startu; `stop`
      kończy pętlę w ciągu jednego interwału; okno partii kończy się kodem 0/3/4/1 i czuwanie
      zapisuje wynik w pamięci ledgera.
- [x] W05: `anishift watch`, `watch stop`, `watch status`, `autostart enable|disable|status`
      istnieją, mają kody wyjścia 0/1 i nie zmieniają systemu bez jawnego wywołania.
- [~] W06: zadanie Windows uruchamia `pythonw.exe -m anishift.cli.main watch` jako bieżący
      użytkownik przy logowaniu, bez hasła i bez uprawnień administratora; `disable` usuwa tylko je.
- [x] W07: bramki root przechodzą; istniejące testy Auto, Manual, Home i `run --preset` przechodzą.
- [ ] W08: właściciel potwierdził: drop pliku, okno pojawia się samo, zero Enterów, pierwszy
      odcinek gotowy przed drugim, okno zamyka się samo, czuwanie po zalogowaniu bez okna.

## Nie-cel

Pobieranie i qBittorrent, wyszukiwanie tytułów, subskrypcje, SQLite, pozycja Czuwaj w Home,
kopiowanie źródeł do stagingu, rewizje produktów, MAL, mpv, obserwowanie folderów spoza
`workspace/`, blokada między oknem partii a ręcznie uruchomionym Auto w innym terminalu (dziś też
jej nie ma), przekazywanie postępu z okna do czuwania.

## Authority i baseline

| Źródło | Rola |
| --- | --- |
| Wypowiedzi właściciela z 2026-09-05 (ta rozmowa) | wymaganie: prosto, na obecnym Auto, bez nowego systemu kolejek; podfolder na serię; czuwanie jako proces w tle także po zamknięciu okna i od zalogowania; okno tylko na czas obróbki |
| [spec.md](../spec.md) R02, R11, R12, R13, R14, R15, R25 | wymagania adresowane tym planem |
| [masterplan.md](../masterplan.md) §1–§14 | decyzje kierunkowe; ten plan zastępuje D01–D03, D10, D11, D13, D17 dla zakresu lokalnego dropu |
| `AGENTS.md`, `anishift/AGENTS.md`, `anishift/application/AGENTS.md`, `anishift/cli/AGENTS.md`, `anishift/platform/AGENTS.md`, `tests/AGENTS.md` | reguły pracy, bramki, pułapki |
| Kod: `application/discovery.py`, `application/artifacts.py`, `application/selection.py`, `application/service.py`, `cli/run.py`, `cli/main.py`, `cli/console.py`, `cli/interactive/app.py`, `config/workspace.py`, `platform/binaries.py` | aktualne zachowanie |

**Baseline:** commit `30b6c4d` (5 commitów przed `main`, m.in. sterowanie presetem Auto). Gałąź
implementacji `work/local-automation/01-watch` odchodzi od tego commitu w osobnym worktree
`../AniShift-worktrees/local-automation-01-watch`. Główny checkout ma niezacommitowane zmiany
właściciela (`settings.py`, `field_catalog.py`, `docs/README.md`, `shadow-slave.md`); worktree ich
nie zawiera i nikt ich nie dotyka.

**Znane wcześniejsze failures:** ustalane w Fazie 0 w worktree.

## Stan aktualny

### Obecne zachowanie

- `discover_groups(root)` czyta tylko `root.iterdir()`; grupuje po parze (katalog, stem), ale
  `_build_source_group` woła `create_group_id(Path(), stem)`, więc ID zależy tylko od stemu.
  `discovery.py:80-104, 246`
- `create_group_id(relative_directory, stem)` już przyjmuje katalog względny i daje jeden bezpieczny
  komponent `group-<16 hex>`. `artifacts.py:160-168`
- `prepare_auto_run(service, preset_id)` bierze wszystkie `ready_group_ids`; `plan_auto` nie pomija
  grup z istniejącymi produktami (nieblokujący `product_overwrite`). `run.py:88-118`,
  `planner.py:1067-1074`
- Interaktywne Auto: `_start_auto` → wątek `_prepare_and_run` → `_execute_run` z `RichRunProgress`;
  po sukcesie `AUTO_DONE`, po problemie `MESSAGE`; oba wracają do Home po klawiszu. `_handle_idle`
  co 0,1 s. `run_interactive(service) -> None`. `app.py:235-240, 363-543, 599-601`
- `_interrupt` w trybie `AUTO` anuluje run przez `service.cancel(run_id)` i wraca do Home.
  `app.py:320-361`
- `run --preset` ma kody wyjścia 0/1/3/4 i cichy sink zdarzeń. `main.py:135-215`
- `configure_utf8_streams()` toleruje `sys.stdout is None` (pythonw). `console.py:21-30`
- Typer: `app.callback(invoke_without_command=True)` otwiera interaktywny tryb bez podkomendy.
  `main.py:86-94`
- `platform/` ma tylko `binaries.py` z `is_windows()`. Brak blokady procesu i integracji z Task
  Scheduler. `services/audio/commands.py:137` używa już `creationflags` dla procesów potomnych.
- `workspace/` dopuszcza jeden zarządzany podfolder `temp/`; `config/` trzyma `settings.json`
  i `presets.json`. `config/workspace.py`, `AGENTS.md`

### Gap

1. Brak rekurencji i katalogu w ID grupy.
2. Brak runu Auto dla wskazanego podzbioru grup.
3. Brak reguł „plik stabilny” i „grupa potrzebuje pracy”.
4. Brak procesu czuwania, blokady pojedynczej instancji, okna partii i komend.

### Istniejące rozwiązania do reuse

| Element | Ścieżka / symbol | Co wykorzystać | Ograniczenie |
| --- | --- | --- | --- |
| Discovery i inspekcja | `AppService.discover()` | cache po odcisku; probe tylko po zmianie | zmiana pliku wymusza reinspekcję wszystkich grup |
| Preflight Auto | `cli/run.py:prepare_auto_run` | odmowy, plan, blokery | dziś zawsze wszystkie gotowe grupy |
| Wykonanie i postęp | `execute_plan`, `RichRunProgress`, `_auto_content`, `_result_message` | identyczny ekran jak Auto | jeden aktywny run na proces |
| Gotowość grupy | `selection.group_is_ready` | konflikt/tekst | nie zna produktów |
| Kody wyjścia | `main.py:_run_exit_code` | 0/3/4 dla partii | brak |
| Wykrycie OS | `platform.binaries.is_windows` | rozgałęzienia | brak |
| Testy interaktywne | `tests/cli/test_interactive_auto_transition.py` | `SimpleNamespace` zamiast renderera | brak |
| Testy CLI | `tests/cli/test_main.py` | `CliRunner`, sondy w osobnym interpreterze | brak |

### Dowody

| Twierdzenie | Dowód | Status |
| --- | --- | --- |
| ID grupy ignoruje katalog | `discovery.py:246` | verified |
| Grupowanie rozróżnia katalogi | `discovery.py:136-148` | verified |
| Re-run Auto nie pomija gotowych grup | `planner.py:1067-1074`, `run.py:99` | verified |
| pythonw daje `sys.stdout is None` i CLI to toleruje | `console.py:23-25` | verified (kod), runtime do sprawdzenia w F5 |
| `CREATE_NEW_CONSOLE` z procesu bez konsoli otwiera nowe okno | dokumentacja Win32 `CreateProcess`; próba w F5 | assumed → F5 |
| Zamknięcie okna konsoli kończy proces potomny kodem ≠ 0 | zachowanie Windows (CTRL_CLOSE_EVENT) | assumed → F5 |
| Explorer trzyma docelowy plik bez współdzielenia zapisu | zachowanie CopyFile; próba w F3 | assumed → F3 |
| Niekompletne pliki qBittorrent mają `.!qB` | opcja klienta; stan u właściciela nieznany | assumed → Plan 02 |

## Zakres

### In scope

- Rekurencyjne discovery z katalogiem w ID grupy.
- `prepare_auto_run(..., group_ids=...)`.
- `application/watch.py`: stabilność, `needs_work`, ledger w pamięci.
- Okno partii: `run_interactive(service, batch=...)` z automatycznym zamknięciem i kodem wyjścia.
- Proces czuwania: pętla, blokada instancji, flaga stop, uruchamianie okna, odbiór kodu.
- Komendy: `watch`, `watch stop`, `watch status`, `watch batch` (ukryta), `autostart enable|disable|status`.
- `platform/process_lock.py`, `platform/autostart.py`.
- Dokumentacja: README, `AGENTS.md`, AGENTS obszarów, masterplan (uzgodnienie).

### Out of scope

Wszystko z Nie-cel. Także: ustawienia czuwania w panelu (stałe `Final` wystarczą), powiadomienia,
obserwowanie kilku bibliotek, pozycja w Home.

### Forbidden

- Drugi pipeline, nowe handlery, zmiana limitów GraphScheduler, zmiana `AppService.execute`.
- Nowe zależności. Skanowanie `temp/`.
- Przenoszenie, kasowanie lub zmiana nazw plików użytkownika.
- Dotykanie głównego checkoutu i zmian właściciela.
- Instalacja zadania Windows bez jawnego `autostart enable`; SYSTEM, admin, zapisane hasło,
  wake timers.
- Prompt Toolkit w procesie czuwania (import `anishift.cli.interactive` tylko w oknie partii).
- Prywatne media, `.env`, logi runtime w testach. Testy używają syntetycznych plików w `tmp_path`.

### Deferred

Konfiguracja interwałów; `.!qB` przez API klienta (Plan 02); lista Gotowe i Oglądaj; pozycja
Czuwaj w Home ze statusem i przełącznikiem; blokada wykonania między oknem partii a ręcznym Auto.

### Dozwolone decyzje lokalne

Nazwy prywatnych helperów, podział `watch.py` i `cli/watch.py` na funkcje, treść etykiet i
komunikatów, parametryzacja testów, wartości stałych `Final` w podanych zakresach.

### Zatrzymaj się i wróć po decyzję, gdy

- `discover()` na 200 grupach po jednej zmianie trwa ponad 30 s (pomiar w F3).
- Kontrola otwarcia daje fałszywe „gotowy” dla pliku kopiowanego przez Explorer.
- `CREATE_NEW_CONSOLE` z pythonw nie otwiera okna albo `schtasks` wymaga admina.
- Okno partii wymagałoby zmiany `AppService.execute` lub schedulera.

## Kontekst do przeczytania

| Kolejność | Źródło | Po co | Zakres |
| --- | --- | --- | --- |
| 1 | `AGENTS.md`; skille `simple` i `coding` z referencjami `python.md`, `comments-docstrings.md`, `testing.md` (absolutne ścieżki w zleceniu) | standard pracy | full |
| 2 | ten plan | kontrakt | full |
| 3 | `anishift/application/AGENTS.md`, `anishift/cli/AGENTS.md`, `anishift/platform/AGENTS.md`, `tests/AGENTS.md` | pułapki obszarów | full |
| 4 | `application/discovery.py`, `application/artifacts.py:160-200`, `application/selection.py`, `application/inspection.py:40-100` | F1, F3 | full / sekcje |
| 5 | `cli/run.py`, `cli/main.py`, `cli/console.py` | F2, F5 | full |
| 6 | `cli/interactive/app.py` | F4 | full |
| 7 | `tests/application/test_discovery.py`, `tests/cli/test_run.py`, `tests/cli/test_interactive_auto_transition.py`, `tests/cli/test_main.py`, `tests/platform/test_binaries.py` | wzorce testów | full |

## Impact scan

| Kontrakt / subsystem | Ryzyko wpływu | Obowiązek regresyjny |
| --- | --- | --- |
| `group_id` w root workspace | zmiana ID zepsułaby cache i Manual | root nadal `create_group_id(Path(), stem)`; test |
| `AppService.discover()` fingerprint | więcej plików, rekursja | `test_service.py`; test z podfolderem |
| `cleanup_orphaned_temp` | rekursja nie może wejść w `temp/` | test: `temp/x/a.mkv` nie jest grupą |
| Manual | widzi grupy z podfolderów | `test_interactive_*` przechodzą |
| `run_interactive` sygnatura | nowy parametr i wartość zwracana | `main.py:_default` bez zmiany semantyki |
| `run --preset` | brak zmian | `test_run.py` |
| `config/` | nowy podfolder `config/watch/` | `AGENTS.md` Dane runtime |
| Task Scheduler | zewnętrzny stan | tylko własna nazwa zadania |

## Target design

### Procesy

```text
Task Scheduler (ONLOGON, bieżący użytkownik)
  └─ pythonw.exe -m anishift.cli.main watch          # CZUWANIE: bez okna, bez Prompt Toolkit
        pętla co SCAN_INTERVAL_S:
          stop-flag? -> wyjdź
          okno partii żyje? -> poll, nic więcej
          discover() -> ledger.candidates()
          kandydaci -> Popen([anishift.exe, "watch", "batch", *group_ids], CREATE_NEW_CONSOLE)
          okno zakończone -> ledger.record(group_ids, exit_code)
  └─ anishift.exe watch batch <group-id>...          # OKNO PARTII: interaktywny renderer
        prepare_auto_run(group_ids) -> execute_plan -> ekran Auto
        wynik przez 10 s (dowolny klawisz zamyka) -> exit 0/3/4/1
```

Czuwanie nie wie nic o postępie; wie tylko, że okno żyje albo jaki kod zwróciło. Okno partii nie
skanuje; przetwarza dokładnie wskazane grupy. Pliki dorzucone w trakcie łapie następny skan
czuwania po zamknięciu okna. Jedno okno naraz, bo `AppService` dopuszcza jeden run na proces
i tak działa dzisiejsze Auto.

### Odpowiedzialności i ownership

| Element | Odpowiada za | Owner stanu | Nie odpowiada za |
| --- | --- | --- | --- |
| `application/discovery.py` MODIFY | rekurencyjny skan, katalog w ID | nic | stabilność |
| `application/watch.py` NEW | stabilność, `needs_work`, `WatchLedger` | ledger w pamięci procesu czuwania | procesy, UI |
| `cli/run.py` MODIFY | `prepare_auto_run(..., group_ids)` | nic | wybór grup |
| `cli/watch.py` NEW | pętla czuwania, flaga stop, uruchomienie okna, kody | `config/watch/daemon.lock`, `config/watch/stop` | reguły, UI |
| `cli/interactive/app.py` MODIFY | tryb partii: start bez Home, wynik z odliczaniem, kod wyjścia | `_ViewMode.BATCH_DONE` | skan |
| `cli/main.py` MODIFY | grupa `watch` (`invoke_without_command`), `autostart` | nic | logika |
| `platform/process_lock.py` NEW | blokada uchwytowa jednej instancji | plik blokady | polityka |
| `platform/autostart.py` NEW | `schtasks` create/delete/query/run | nic | UI |

### Source of truth

- co jest gotowe: pliki w bibliotece (produkty obok źródła) — jak dziś.
- stan pochodny: `WatchLedger` w pamięci procesu czuwania: `group_id → (fingerprint, wynik)`;
  ginie z procesem; po ponownym starcie każda niegotowa grupa dostaje jedną nową próbę.
- czy czuwanie działa: blokada `config/watch/daemon.lock` trzymana przez uchwyt; `daemon.pid`
  obok jest informacją, nie dowodem.
- polecenie stop: plik `config/watch/stop`; czuwanie usuwa go przy wyjściu.
- mutacje biblioteki: wyłącznie `execute_plan` w oknie partii.

### Docelowe drzewo

```text
anishift/
├── application/
│   ├── discovery.py            # MODIFY: rglob bez temp/ i .*, katalog w create_group_id
│   └── watch.py                # NEW: SourceSnapshot, is_stable, needs_work, WatchLedger
├── cli/
│   ├── main.py                 # MODIFY: grupa watch (daemon | stop | status | batch), autostart
│   ├── run.py                  # MODIFY: prepare_auto_run(group_ids=None)
│   ├── watch.py                # NEW: pętla czuwania, stop-flag, spawn okna, kody wyjścia
│   └── interactive/app.py      # MODIFY: run_interactive(service, batch=None) -> int, BATCH_DONE
├── platform/
│   ├── autostart.py            # NEW: schtasks
│   └── process_lock.py         # NEW: msvcrt.locking / fcntl.flock
└── AGENTS.md                   # MODIFY: workspace z podfolderami serii; config/watch/
config/watch/                   # runtime, gitignored razem z config/*
tests/
├── application/test_discovery.py   # MODIFY
├── application/test_watch.py       # NEW
├── cli/test_run.py                 # MODIFY
├── cli/test_watch.py               # NEW: pętla z wstrzykniętym spawnerem, zegarem, skanerem
├── cli/test_interactive_batch.py   # NEW
├── cli/test_main.py                # MODIFY: watch/autostart bez ładowania UI
└── platform/test_process_lock.py   # NEW (dwa procesy potomne)
    platform/test_autostart.py      # NEW (mock subprocess.run)
```

### Publiczne kontrakty

#### `discover_groups(root: Path) -> DiscoveryResult`

```text
wejście: root biblioteki
wyjście: grupy z root i podkatalogów poza `temp` (bezpośrednio pod root) i katalogami, których
         dowolny człon ścieżki względnej zaczyna się od "."
ID: create_group_id(parent.relative_to(root), stem); dla root parent względny == Path()
kolejność: po ścieżce względnej (casefold, potem surowa), deterministyczna
kompatybilność: płaska biblioteka daje identyczne ID i kolejność jak przed zmianą
```

#### `prepare_auto_run(service, preset_id, *, cancel=None, group_ids=None)`

```text
group_ids None -> jak dziś (wszystkie gotowe)
group_ids podane -> plan tylko dla tych spośród nich, które są gotowe; nieznane lub niegotowe ID
                    -> AutoRunRefusal z listą ID, bez wyjątku
```

#### `application/watch.py`

```text
SCAN_INTERVAL_S: Final[float] = 5.0          # dopuszczalne 2–30
QUIET_S: Final[float] = 10.0                 # dopuszczalne 5–60
PARTIAL_SUFFIXES: Final[frozenset[str]] = frozenset({".!qb", ".part", ".tmp", ".crdownload"})

@dataclass(frozen=True, slots=True)
class SourceSnapshot: path: Path; size: int; mtime_ns: int; first_seen: float

def snapshot_sources(group: InspectedSourceGroup, previous: Mapping[Path, SourceSnapshot], now: float)
    -> tuple[SourceSnapshot, ...]      # first_seen zachowane, gdy size i mtime bez zmian
def is_stable(snapshot: SourceSnapshot, now: float) -> bool
    # brak sufiksu częściowego, now - first_seen >= QUIET_S, open(path, "r+b") powiodło się
def needs_work(group: InspectedSourceGroup, preset: AutoPreset) -> bool
    # group_is_ready(group) and brakuje READY artefaktu dla któregoś requested_products;
    # ProductKind -> ArtifactKind po nazwie; MKV -> FINAL_MKV, MP4 -> FINAL_MP4
def source_fingerprint(snapshots) -> tuple[tuple[str, int, int], ...]

class WatchLedger:
    def candidates(self, workspace: InspectedWorkspace, preset: AutoPreset, now: float) -> tuple[str, ...]
        # aktualizuje snapshoty; zwraca ID grup: needs_work, stabilne, bez wpisu failed z tym samym fingerprintem
    def mark_started(self, group_ids) -> None
    def record_exit(self, group_ids, exit_code: int) -> None    # 0 -> done, inaczej failed(kod)
    def rows(self) -> tuple[WatchRow, ...]                       # do statusu/logów
```

#### `cli/watch.py`

```text
def run_daemon(service: AppService, *, spawner: Spawner, clock: Clock, sleep: Sleeper,
               state_dir: Path) -> int
    # 1 gdy blokada zajęta (druga instancja) albo workspace nierozwiązany; 0 po stop
    # pętla: stop-flag -> exit; dziecko żyje -> poll; discover -> candidates -> spawn; sleep
    # błędy discover/preflight logowane, pętla trwa (backoff 30 s po błędzie)
def request_stop(state_dir) -> None            # tworzy `stop`
def daemon_status(state_dir) -> DaemonStatus   # RUNNING(pid) | STOPPED, przez próbę blokady
def batch_command(argv_for: Sequence[str]) -> list[str]
    # [sys.executable-owner anishift.exe albo [sys.executable, "-m", "anishift.cli.main"]] + ["watch", "batch", *ids]
Spawner produkcyjny: subprocess.Popen(cmd, creationflags=CREATE_NEW_CONSOLE) na Windows,
                     zwykły Popen poza nim; zwraca obiekt z .poll() i .returncode
```

#### `run_interactive(service, *, batch: Sequence[str] | None = None) -> int`

```text
batch None -> jak dziś, zwraca 0
batch podane -> start od PREPARING dla group_ids; AUTO jak dziś; po runie BATCH_DONE:
                _result_message + „zamykam za N s”, odliczanie w _handle_idle, dowolny klawisz
                zamyka; odmowa -> MESSAGE z odliczaniem; zwraca 0 sukces, 3 partial/failed,
                4 anulowane, 1 odmowa; interrupt w AUTO anuluje run i kończy z 4
```

#### `platform/process_lock.py`

```text
class ProcessLock:
    def __init__(self, path: Path) -> None
    def acquire(self) -> bool         # nieblokujące; True gdy zdobyto; Windows msvcrt.locking LK_NBLCK 1 bajt; POSIX fcntl.flock LOCK_EX|LOCK_NB
    def release(self) -> None         # zwalnia i zamyka uchwyt; pliku nie usuwa
    context manager
```

#### `platform/autostart.py`

```text
TASK_NAME: Final[str] = "AniShift Watch"
def enable(command: Sequence[str]) -> None   # schtasks /Create /F /SC ONLOGON /RL LIMITED /TN … /TR "…"; potem /Run
def disable() -> None                        # schtasks /Delete /F /TN …; brak zadania nie jest błędem
def status() -> AutostartStatus              # ENABLED | DISABLED | MISSING przez /Query /FO CSV
def watch_command() -> list[str]             # [<venv>\Scripts\pythonw.exe, "-m", "anishift.cli.main", "watch"]
błędy: poza Windows AutostartUnsupportedError; niezerowy schtasks -> AutostartError (FatalError)
       z kodem i pierwszą linią stderr w ErrorContext.suggestion; oba w errors.py jako {Platform}Error
```

#### CLI

```text
anishift watch                  czuwanie w bieżącym terminalu; 0 po stop, 1 gdy już działa
anishift watch stop             0 po zapisaniu flagi (także gdy nic nie działa)
anishift watch status           0 i jedna linia: running (pid N) | stopped
anishift watch batch ID...      ukryta; kod jak run_interactive(batch=...)
anishift autostart enable       rejestruje i uruchamia; 0 / 1
anishift autostart disable      usuwa zadanie i zapisuje stop; 0 / 1
anishift autostart status       0 i jedna linia: enabled | disabled | missing
```

### Algorytm: stabilność

1. Każdy skan liczy snapshot plików źródłowych i sidecarów grupy; `first_seen` przechodzi z
   poprzedniego snapshotu, gdy `size` i `mtime_ns` się nie zmieniły, inaczej resetuje do `now`.
2. Plik jest stabilny, gdy nazwa nie kończy się sufiksem częściowym, `now - first_seen >= QUIET_S`
   i otwarcie `r+b` powiodło się (uchwyt zamknięty natychmiast).
3. Grupa jest kandydatem, gdy każdy jej plik źródłowy jest stabilny, `needs_work` jest prawdą i
   ledger nie ma wpisu `failed` z tym samym fingerprintem.

### Zachowanie okna partii

- **Start:** od razu ekran Auto (bez Home, bez menu), jak dziś po Enter w Auto.
- **Run:** identycznie jak Auto, klawisze kolejki działają. Ctrl+C anuluje i kończy kodem 4.
- **Wynik:** `_result_message` plus wiersz „Okno zamknie się za N s · dowolny klawisz zamyka”.
  Odliczanie od 10 s w `_handle_idle`. Odmowa preflightu: ten sam ekran z komunikatem odmowy.
- **Bardzo niski terminal:** jak Auto.
- **Wygląd oceniany przez człowieka:** czytelność wyniku i odliczania.

### Edge cases i failures

| Przypadek | Oczekiwane | Dowód |
| --- | --- | --- |
| Explorer kopiuje 2 GB MKV | rozmiar rośnie albo `r+b` odmawia → nie startuje; po ciszy startuje | automated (drugi uchwyt) + human |
| `odcinek.!qB` w podfolderze | ignorowany do zmiany nazwy | automated |
| Plik w `workspace/temp/run-1/` | nie jest grupą | automated |
| Dwie serie z `01.mkv` | dwie grupy, dwa ID, produkty w swoich folderach | automated |
| Grupa z kompletem produktów presetu | nie kandydat | automated |
| Grupa z `.pl.srt`, bez `.pl.mkv` | kandydat; planner reużywa napisy jak dziś | automated |
| Okno zwraca 3 (partial) | grupy partii `failed(3)`; brak ponowienia do zmiany pliku | automated |
| Użytkownik zamyka okno (X) | kod ≠ 0 → `failed`; czuwanie trwa; brak pętli otwierania | automated (spawner zwraca kod) + human |
| Drugi plik w trakcie partii | czeka; następny skan po wyjściu okna go bierze | automated |
| Druga instancja czuwania | `acquire` False → komunikat, kod 1 | automated (dwa procesy) |
| `stop` podczas partii | czuwanie kończy pętlę; okno kończy swoją partię samo | automated |
| Zabity proces czuwania | blokada zwolniona przez OS; `status` = stopped; stary `daemon.pid` nie jest dowodem | automated |
| `discover()` rzuca (np. brak narzędzia) | log, backoff 30 s, pętla trwa | automated |
| `autostart enable` poza Windows | odmowa, kod 1 | automated |
| `schtasks` zwraca błąd | komunikat bez pełnego stderr, kod 1 | automated (mock) |
| Zadanie już istnieje | `/F` nadpisuje własne | automated |

### Reuse i zależności

- użyj: `discover`, `group_is_ready`, `prepare_auto_run`, `execute_plan`, `RichRunProgress`,
  `_auto_content`, `_result_message`, `_run_exit_code`, `is_windows`, `sanitize_event_message`,
  istniejący logger plikowy z `main()`.
- nie duplikuj: discovery, planowania, wykonania, renderera, kodów wyjścia.
- nowa zależność: żadna. `msvcrt`, `fcntl`, `subprocess` ze stdlib.

## Plan wykonania

Gałąź `work/local-automation/01-watch` od `30b6c4d` w worktree
`../AniShift-worktrees/local-automation-01-watch`. Integrator: agent prowadzący. Fazy 1, 2, 3
idą równolegle do subagentów; 4 i 5 po nich (5 może iść do subagenta po ustaleniu sygnatury
`run_interactive`); 6 i 7 integrator. Każda faza kończy się commitem `typ(scope): opis`.

### Faza 0 — Preflight (integrator)

1. `git worktree add ../AniShift-worktrees/local-automation-01-watch -b work/local-automation/01-watch 30b6c4d`.
2. `uv sync` w worktree; pełne bramki; wynik jako baseline (liczby, failures z nazwami).
3. Sprawdź, że `external/bin` jest dostępne albo testy narzędziowe skipują.

**Gate:** bramki zielone albo failures spisane.

### Faza 1 — Rekurencyjne discovery (subagent A)

`discover_groups`: pliki z `rglob("*")` z filtrem (`temp` bezpośrednio pod root; człon od kropki),
sortowanie po ścieżce względnej; `_build_source_group(candidates, root)` z
`first.path.parent.relative_to(root)`. Testy: podfolder; `temp/`; ukryty katalog; dwie serie z tym
samym stemem; ID w root identyczne z `create_group_id(Path(), stem)`; kolejność niezależna od
kolejności systemu plików; symlink do katalogu nie jest śledzony.

**Pliki:** `discovery.py`, `tests/application/test_discovery.py`.
**Kontrola:** `uv run pytest tests/application/test_discovery.py tests/application/test_service.py`.
**Commit:** `feat(application): discover source groups in workspace subfolders`.

### Faza 2 — Podzbiór grup w preflight Auto (subagent B)

`prepare_auto_run(..., group_ids=None)`. Testy w `tests/cli/test_run.py`: podzbiór, nieznane ID,
niegotowe ID, `None` = dotychczasowe.
**Commit:** `feat(cli): let automatic runs target a subset of ready groups`.

### Faza 3 — Reguły czuwania (subagent C)

`application/watch.py` wg kontraktu. Testy `tests/application/test_watch.py` z `tmp_path`:
stabilność (sufiksy, cisza, plik otwarty do zapisu przez drugi uchwyt w tym samym teście),
`needs_work` dla każdego `ProductKind`, ledger: kandydaci, `mark_started`, `record_exit`, reset po
zmianie fingerprintu, `rows`. Pomiar: `discover()` na syntetycznej bibliotece 200 grup TXT.
**Commit:** `feat(application): add watch readiness rules and ledger`.

### Faza 4 — Okno partii (integrator)

`run_interactive(service, *, batch=None) -> int`; `_InteractiveApplication(service, batch)`;
start `_start_auto(group_ids)` zamiast Home; `_ViewMode.BATCH_DONE` z odliczaniem w
`_handle_idle`; kod wyjścia z `RunResult` przez istniejącą regułę 0/3/4; odmowa → 1; interrupt
w AUTO → cancel i 4. `main.py:_default` bez zmian semantyki. Testy
`tests/cli/test_interactive_batch.py` wzorem `test_interactive_auto_transition.py`: start bez
Home, wynik i odliczanie, klawisz zamyka, kody.
**Commit:** `feat(cli): run one automatic batch in a self-closing window`.

### Faza 5 — Czuwanie, blokada, autostart (subagent D po F1–F4)

`platform/process_lock.py` + test z dwoma procesami potomnymi (`subprocess`, izolowany katalog,
krótki czas życia). `cli/watch.py` + `tests/cli/test_watch.py` z wstrzykniętym spawnerem, zegarem
i `sleep`: brak kandydatów, kandydaci → spawn raz, dziecko żyje → brak drugiego spawn, kod 3 →
failed, stop-flag → wyjście 0, druga instancja → 1, błąd discover → backoff. `platform/autostart.py`
+ test z mockiem `subprocess.run` (argumenty, kody, nie-Windows, brak zadania przy disable).
`main.py`: grupa `watch` z `invoke_without_command=True`, `batch` z `hidden=True`, grupa
`autostart`. `test_main.py`: sonda, że `watch`, `watch status` i `autostart status` nie ładują
`anishift.cli.interactive` ani `prompt_toolkit`.

**Human checkpoint (integrator, po F5, przed F6):**

```text
Uruchom: w worktree `uv run anishift watch` w jednym terminalu
Zrób: skopiuj syntetyczny MKV z napisami do workspace/Test/ (nie prywatny odcinek)
Oczekiwany rezultat: po ~10 s od końca kopiowania otwiera się nowe okno z ekranem Auto;
                     po zakończeniu okno pokazuje wynik i zamyka się; terminal czuwania trwa
Zwróć uwagę na: czy w trakcie kopiowania nic nie startuje; czy zamknięcie okna X nie zabija czuwania
Przekaż wynik jako: opis + zrzut ekranu w raporcie
```

**Commity:** `feat(platform): add a single-instance process lock and the logon task`,
`feat(cli): add background watch with batch windows and autostart commands`.

### Faza 6 — Dokumentacja i uzgodnienie masterplanu (integrator)

README (komendy `watch`, `autostart`, podfoldery serii, jak działa okno); `AGENTS.md` Dane
runtime (`workspace/` z podfolderami serii, `temp/` jedyny zarządzany; `config/watch/`);
AGENTS obszarów (pułapki: rekursja omija `temp/`; czuwanie bez Prompt Toolkit; jedno okno naraz;
`schtasks` tylko własne zadanie; kody wyjścia okna). Masterplan: D01–D03 → „czuwanie jako proces
bez UI + okno partii na istniejącym Auto; stan = pliki biblioteki”; D10 → „biblioteka =
`workspace/` z podfolderami serii”; D11, D13 odłożone do Planu 02; D17 → „okno partii jest
monitorem i zamyka się samo”; D04 z zainstalowanym qBittorrent 5.2.3; karty P02–P04 i P12
oznaczone `superseded-by: plans/01-watch-mode.md`; §11 bez `active_pipeline_jobs`.
**Commit:** `docs(agents): describe background watch, series subfolders and the logon task`.

### Faza 7 — Bramki, odbiór, PR (integrator + właściciel)

Pełne bramki; `uv run anishift --help`; human acceptance; PR do `main` (docs planistyczne z gałęzi
planowania są osobnym PR właściciela).

## Dodatkowi wykonawcy

| Jednostka | Cel | Kontekst | Write scope | Wynik | Owner integracji |
| --- | --- | --- | --- | --- | --- |
| A | F1 | plan §F1 i kontrakt discovery; `discovery.py`, `artifacts.py`, testy | `discovery.py`, `test_discovery.py` | diff, wynik testów | integrator |
| B | F2 | plan §F2; `run.py`, `test_run.py` | `run.py`, `test_run.py` | diff, wynik testów | integrator |
| C | F3 | plan §F3 i kontrakt watch; `selection.py`, `intents.py`, `artifacts.py`, `inspection.py` | `watch.py`, `test_watch.py` | diff, wynik testów, pomiar | integrator |
| D | F5 | plan §F5 i kontrakty; `main.py`, `console.py`, `binaries.py`, `app.py` (sygnatura po F4) | `cli/watch.py`, `platform/*.py`, `main.py`, `errors.py` (dwie klasy), testy | diff, wynik testów, próba spawn | integrator |

A, B, C równolegle w tym samym worktree na rozłącznych plikach; commituje integrator po review
każdego diffu. D po F4. Każde zlecenie zaczyna się od przeczytania skilli `simple` i `coding`
z referencjami Pythona (absolutne ścieżki w zleceniu). Subagenci nie commitują i nie uruchamiają
pełnych bramek; uruchamiają targeted testy oraz `ruff`/`mypy` na swoich plikach.

## Strategia dowodu

| Twierdzenie | Kontrola | Dlaczego wystarcza |
| --- | --- | --- |
| Rekursja i ID | unit `test_discovery.py` | czysta funkcja na `tmp_path` |
| Podzbiór grup | unit `test_run.py` | fasada z fake'ami jak dziś |
| Stabilność i needs_work | unit `test_watch.py` z drugim uchwytem | odtwarza kopiowanie bez GUI |
| Okno partii | `test_interactive_batch.py` | wzorzec testów przejść |
| Pętla czuwania | `test_watch.py` z wstrzykniętym spawnerem | deterministyczne bez procesów |
| Blokada | dwa procesy potomne | jedyny wiarygodny dowód wyłączności |
| CLI i schtasks | `test_main.py`, `test_autostart.py` z mockiem | argumenty i kody bez dotykania systemu |
| Całość | bramki root + `anishift --help` | wymóg repo |
| Realny drop, okno, logowanie | human | automat tego nie widzi |

### Regression obligations

`tests/application/test_service.py`, `tests/cli/test_interactive_*.py`, `tests/cli/test_run.py`,
`tests/cli/test_main.py`.

### Human acceptance

- scenariusz: (1) `anishift autostart enable`; skopiuj własny MKV do `workspace/<Seria>/`;
  nie dotykaj klawiatury; (2) w trakcie obróbki dorzuć drugi plik; (3) po obu gotowych wyloguj
  i zaloguj; sprawdź `anishift watch status`; (4) `anishift autostart disable`; `status`.
- warunek PASS: okno pojawiło się samo i samo zamknęło; pierwszy odcinek gotowy zanim drugi
  wystartował; zero Enterów; po zalogowaniu `running`, bez okna; po `disable` `stopped`
  i `missing`.

## Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Kiedy eskalować |
| --- | --- | --- | --- |
| Fałszywa stabilność | realny drop startuje za wcześnie | podnieś `QUIET_S`; wymagaj trzech niezmienionych skanów | nadal startuje na częściowym pliku |
| Koszt `discover()` w czuwaniu | pomiar F3 > 30 s | ogranicz reinspekcję do zmienionych grup (osobny plan) | zawsze |
| pythonw bez konsoli nie otwiera okna | próba F5 | fallback: `cmd /c start` z `/MIN`; ostatecznie `conhost` | gdy żadne nie działa |
| Pętla otwierania po zamknięciu okna | okno wraca co 5 s | ledger `failed` dla kodu ≠ 0 już to blokuje; test | zawsze, gdy wystąpi |
| `schtasks` odmowa | „Access is denied” | komunikat z podpowiedzią; bez elevacji | zawsze |

## Lokalna adaptacja

Nazwy helperów, podział modułów na funkcje, teksty komunikatów, stałe w zakresach, parametryzacja
testów, dokładny format linii `status`.

## Materialna zmiana

Wymaga zatrzymania i decyzji właściciela: zmiana `AppService.execute` lub schedulera; dwa okna
naraz; trwały stan poza `config/watch/`; IPC postępu między procesami; folder spoza `workspace/`;
nowa zależność; inna baza gałęzi.

## Definition of Done

- [ ] W01–W07 z konkretnymi wynikami testów;
- [ ] W08 potwierdzone przez właściciela;
- [ ] bramki root zielone, `anishift --help` działa;
- [ ] zakres i zakazy zachowane; główny checkout nietknięty;
- [ ] masterplan i AGENTS uzgodnione;
- [ ] PR otwarty bez śladów generatora.

## Wynik wykonania (2026-09-05)

Gałąź `work/local-automation/01-watch`, worktree `../AniShift-worktrees/local-automation-01-watch`, HEAD `8289c47`.

| Commit | Faza |
| --- | --- |
| `df81082` | F1 discovery rekurencyjne |
| `319fb6f` | F2 `prepare_auto_run(group_ids=...)` |
| `3fa7b46` | F4 okno partii (`run_interactive(batch=...)`, `cli/exit_codes.py`) |
| `0958486` | F3 `application/watch.py` |
| `e5dfe46` | F5 `platform/process_lock.py`, `platform/autostart.py` |
| `129c2d9` | F5 `cli/watch.py`, komendy `watch` i `autostart` |
| `8289c47` | F6 README i AGENTS |

Dowody: ruff check i format czyste; mypy win32 i linux bez błędów (455 plików); pytest kod wyjścia 0
(3143 passed, 65 skipped wg raportu F5); `anishift --help` pokazuje `watch` i `autostart`.
Pomiar F3: `discover_groups` + `candidates` na 200 grupach ≈ 20 ms. Sonda `CREATE_NEW_CONSOLE`
otworzyła osobne okno. Próba na żywo w worktree z syntetycznym `workspace/Test/probe-01.txt`:
log `Watch started` → `Batch window started (1)` po 24 s → `Batch window finished (exit 1, brak kluczy
LLM w worktree)` → `watch stop` → `stopped`; katalog probe usunięty.

Odchylenia od planu: test pętli nazywa się `tests/cli/test_watch_daemon.py` (kolizja nazw modułów
z `tests/application/test_watch.py`); `disable()`/`status()` także odmawiają poza Windows; `.gitignore`
dostał `config/watch/`; okno zamknięte przez X kończy proces bez własnego kodu (Windows), więc czuwanie
zapisuje kod ≠ 0 i nie ponawia do zmiany pliku.

Próba właściciela `autostart enable` odsłoniła dwa błędy: `schtasks /SC ONLOGON` odmawia zwykłemu
użytkownikowi („Odmowa dostępu”), a wyjście `schtasks` jest w cp852, więc `text=True` psuło dekodowanie.
Commit `acbcf8e`: rejestracja z pliku XML (LogonTrigger i Principal bieżącego konta), stan z `/Query /XML`,
dekodowanie `oem`; sonda XML jako zwykły użytkownik: create/query/disable/delete wszystkie rc=0.
Gałąź została przeniesiona do głównego checkoutu, worktree usunięty (decyzja właściciela).

Pierwsze włączenie przez właściciela (`7e3aecc`): proces czuwania bez konsoli uruchamiał `mkvmerge`/`ffprobe`
do probowania, a Windows otwierał każdemu dziecku konsolowemu własne okno („tysiąc okien”). Fix: `CREATE_NO_WINDOW`
na każdym uruchomieniu narzędzi medialnych i `nvidia-smi`. Po fixie: `autostart enable` przeszło, `watch status`
= running, jedyne widoczne okno to okno partii w Windows Terminal (0 okien ConsoleWindowClass).

W06 spełnione (zadanie zarejestrowane bez admina, czuwanie działa). Nie wykonano: wylogowanie i zalogowanie,
W08 (odbiór), PR do `main`.

## Kontrakt wyniku

```text
status
commit SHA każdej fazy
zmienione pliki
wyniki: pytest (liczby), ruff, mypy, pomiar discover(), próba spawn okna
human feedback
odchylenia lokalne
materialne odkrycia
znane ograniczenia
rekomendowany następny plan (02: pobieranie przez qBittorrent do workspace/<Seria>/)
```

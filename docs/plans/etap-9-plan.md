# Etap 9 — plan implementacji modelu produktu, schedulera i Textual TUI

> Status: plan wykonawczy po dwóch audytach wymagań, wzorca Etapu 7 i bieżącej
> architektury (2026-08-09). Kontrakty poniżej są wiążące; implementacja nie może
> pozostawić wariantów „albo” do rozstrzygnięcia podczas kodowania.
> Data: 2026-08-09.
> Wymagania: [`etap-9-wymagania.md`](etap-9-wymagania.md) oraz
> [`etap-9-interfejs-wymagania.md`](etap-9-interfejs-wymagania.md).
> Issue: [#38](https://github.com/MattyMroz/AniShift/issues/38).
> Branch: `feature/stage-9-product-tui` po zaakceptowaniu tego planu.
> Dokument jest jednym planem backendu, application API, schedulera i TUI. Każdy krok
> wskazuje dokładne pliki, publiczne kontrakty, testy i dowód ukończenia. Kod należy
> pisać według skilli `python` i `instructions`, a każdą zmianę upraszczać skillem
> `simple`.

## 1. Zasady realizacji

- każdy krok kończy się działającym repo i zielonymi pełnymi bramkami;
- przed każdym commitem: `uv run ruff check anishift/ tests/`,
  `uv run ruff format --check anishift/ tests/`, `uv run mypy anishift/ tests/`,
  `uv run pytest`;
- nowe zachowanie powstaje test-first: najpierw test kontraktu, potem minimalny kod;
- plan zachowuje wykonawczą dokładność Etapu 7 w zakresie ścieżek, kontraktów,
  kolejności i dowodów, ale świadomie nie kopiuje pełnej treści 30+ przyszłych
  plików źródłowych. Bloki z `...` są wiążącymi publicznymi sygnaturami, nie kodem
  do wklejenia. Implementacja powstaje raz w repo; przed krokiem nie tworzy się
  kolejnego planu ani alternatywnej architektury;
- nowe pliki produkcyjne mają maksymalnie około 400 linii; istniejące god-files
  `pipeline/runner.py`, `cli/pipeline_ui.py`, `cli/settings_panel.py` i
  `config/user_settings.py` są zmniejszane wyłącznie w zakresie Etapu 9;
- application API, planner i scheduler nie importują `textual`, `typer`, Rich ani
  modułów `anishift.cli`/`anishift.tui`;
- TUI i CLI nie odczytują mediów ani konfiguracji bezpośrednio; wywołują wspólne
  use case'y application API;
- serwisy pozostają fasadami operacji. Nie czytają `UserSettings`, nie znają grafu
  ani kolejnego zadania;
- scheduler jest synchronicznym koordynatorem gotowości i ograniczonych pul
  wątków. Nie przepisujemy synchronicznych serwisów na sztuczne `async def` i nie
  dodajemy `ProcessPoolExecutor`, bo ciężka praca odbywa się w zewnętrznych
  procesach, sieciowych SDK i istniejącym runtime TTS;
- istniejące limity i semantyka kolejek LLM/TTS są zachowane do czasu przejęcia ich
  przez wspólny scheduler; nie utrzymujemy dwóch właścicieli tego samego limitu;
- anulowanie używa jednego idempotentnego tokenu opartego na `threading.Event`;
  późny wynik po cancel nie może zostać opublikowany;
- trwałe wyniki są publikowane atomowo obok źródła. `workspace/temp/<run>/<group>`
  przechowuje wyłącznie artefakty robocze i jest sprzątany w `finally`;
- rutynowa walidacja TUI jest automatyczna przez `App.run_test()` i `Pilot`;
  ręczne klikanie nie jest kryterium ukończenia;
- Textual spike jest odrzucalny. Nie ustanawia docelowego API i zostaje usunięty
  po przejściu bramki;
- stary REPL działa do minimalnego parytetu TUI, potem jest usuwany razem z
  `prompt_toolkit`; nie utrzymujemy trzeciego interfejsu;
- agent językowy, MyAnimeList i pobierarka nie należą do Etapu 9. Command bar
  zostawia im typowaną granicę, ale nie implementuje żadnego z nich;
- żadnego osobnego migratora danych użytkownika ani bazy danych. Loader ustawień
  rozumie poprzedni schemat i zapisuje nowy dopiero po jawnej akcji `Save`;
- testy nie otrzymują `__init__.py`, docstringów ani komentarzy;
- nowe zależności wyłącznie przez `uv add`/`uv remove`.

## 2. Decyzje architektoniczne

### 2.1. Jeden przepływ i jawny kierunek zależności

```text
Textual TUI ─┐
             ├─> application/AppService ─> planner ─> scheduler ─> task handlers ─> services
Typer CLI ───┘          │             │          │
                       │             │          └─ immutable ArtifactSnapshot
                       │             └─ pure ExecutionPlan
                       └─ typed snapshots, RunEvent i RunResult
```

| Warstwa | Właściciel decyzji | Nie może robić |
|---|---|---|
| `application/artifacts.py`, `intents.py`, `planning.py`, `results.py` | zamrożone typy i reguły bez I/O | importować discovery, scheduler, serwisy lub UI |
| `application/discovery.py`, `inspection.py`, `publisher.py` | kontrolowane I/O systemu plików i wzbogacanie artefaktów | podejmować decyzje produktowe |
| `application/planner.py` | deterministyczny DAG i konflikty na zwalidowanym snapshotcie | uruchamiać serwisy albo wykonywać I/O |
| `application/scheduler.py` | gotowość, admission, limity, cancel i numerowanie eventów | interpretować ustawienia UI albo mutować plan |
| `application/handlers.py` | adapter task → istniejący serwis; zwraca wynik, nie mutuje store | zmieniać graf ani rejestrować produktów |
| `application/service.py`, `sessions.py` | use case'y, jeden lifecycle runu i transakcja publikacji | zawierać widżety albo reguły providerów |
| `tui/` i `cli/` | prezentacja, draft formularza, wybór use case'u | duplikować reguły planera |

Płaski katalog `application/` jest świadomym wyborem KISS, ale nie jest płaską
warstwą zależności. Importy biegną wyłącznie od fasady i I/O w stronę zamrożonych
typów; modele nigdy nie importują modułów wykonawczych. Test architektury sprawdza
zakazane importy. Rozdzielenie na kolejne paczki jest dozwolone dopiero po realnym
przekroczeniu 400 linii lub pojawieniu się cyklu, nie z wyprzedzeniem.

### 2.2. Asynchroniczność i wielowątkowość

```text
Textual event loop
  ├─ timer UI: EventBuffer.drain() -> Textual Message -> render
  └─ Textual Worker(thread=True): AppService.execute(plan)
            └─ GraphScheduler.run()
                 ├─ ThreadPoolExecutor[extract]     limit N
                 ├─ ThreadPoolExecutor[translate]   limit per provider
                 ├─ ThreadPoolExecutor[tts-dispatch] limit group jobs
                 │    └─ jeden TtsService/TtsScheduler + jeden event-loop thread
                 ├─ ThreadPoolExecutor[audio]       limit N
                 └─ ThreadPoolExecutor[compose]     limit N
                         └─ FFmpeg/MKVToolNix/SDK lub istniejący worker
```

- jeden synchroniczny koordynator posiada stan grafu; worker nie mutuje
  `ExecutionPlan` ani wspólnego stanu tasków;
- każdy `Future` wraca przez `wait(..., FIRST_COMPLETED)` do koordynatora, który
  odblokowuje zależne taski;
- executory są tworzone per run, mają stabilne `thread_name_prefix` i kończą się w
  `shutdown(cancel_futures=True)`; wszystkie sieciowe SDK i subprocessy mają
  skończony timeout;
- scheduler nie submituje z góry całego runu. Dla zasobu obowiązuje
  `submitted_not_done <= worker_limit + max_pending_per_resource`; pozostałe
  gotowe taski zostają w stanie planera bez utworzonego `Future`;
- `ready_first` wpuszcza każde gotowe zadanie;
- `strict_natural` pozwala liczyć w tle, ale bramka publikacji/forwardowania czeka
  na rozstrzygnięcie wcześniejszej grupy;
- callbacki workerów tworzą `WorkerNotification`, nigdy `RunEvent`. Wyłącznie
  coordinator przydziela monotoniczny `sequence`, tworzy `RunEvent` i zapisuje go
  do thread-safe `EventBuffer`: skończona lista zmian stanu oraz coalesced najnowszy
  progress per task. Timer w głównej pętli Textual okresowo opróżnia bufor i publikuje
  Textual messages; worker wykonujący `AppService.execute()` nie obsługuje UI;
- TUI tylko konsumuje eventy i ogranicza renderowanie procentów; event terminalny
  nigdy nie jest odrzucany. TTS zachowuje własny pojedynczy event-loop thread —
  nie uruchamiamy `asyncio.run()` per task. Request-level concurrency, retry oraz
  circuit breaker należą nadal do `TtsScheduler`; graph scheduler ogranicza tylko
  liczbę aktywnych group-level TTS jobs. Runtime TTS zamyka się dokładnie raz po
  runie i nigdy raz na grupę.

### 2.3. Właściciele retry, fallbacku, artefaktów i cleanupu

| Odpowiedzialność | Jedyny właściciel |
|---|---|
| transport/request retry i circuit breaker providera | serwis domenowy translation/TTS/LLM |
| wybór następnego skonfigurowanego silnika | fasada domenowa wywoływana przez handler |
| ręczne ponowienie całego nieudanego taska po wyniku | nowy plan/run uruchomiony przez `AppService`, nie automatyczny resubmit schedulera |
| mapowanie provider retry/fallback na event | handler → `WorkerNotification`; coordinator → `RunEvent` |
| runtime artifact state | wyłącznie coordinator |
| run scope i końcowy cleanup | `RunSession` utworzony przez `AppService` |
| pliki robocze pojedynczego taska | handler do chwili zwrócenia `TaskResult` |

Scheduler nie powtarza retry wykonanego już przez provider. Po końcowym
`TransientError` albo `FatalError` oznacza task jako failed i blokuje tylko jego
zależne taski. Późny wynik po cancel lub po zamknięciu generacji jest odrzucany,
nie rejestrowany i nie publikowany.

### 2.4. Granica command bara

```text
❯ refresh
  └─ CommandRouter.parse("refresh") -> UiCommand.REFRESH -> AppService.discover()

❯ pobierz najnowszy odcinek ...       # przyszłość, nie Etap 9
  └─ AgentAdapter -> typed command -> plan preview -> confirmation -> application API
```

W Etapie 9 parser zna wyłącznie `auto`, `manual`, `settings`, `refresh`, `doctor`,
`setup` i `help`. Każde polecenie odpowiada widocznej akcji. Pusty albo nieznany
tekst nie ma efektu ubocznego.

## 3. Drzewo katalogów po etapie

```text
anishift/
├── application/                         NOWY — wspólny model produktu i use case'y
│   ├── AGENTS.md                        NOWY
│   ├── CLAUDE.md                        NOWY — @AGENTS.md
│   ├── __init__.py                      NOWY — mała publiczna fasada
│   ├── artifacts.py                     NOWY — Artifact, SourceGroup, nazwy i stany
│   ├── intents.py                       NOWY — AutoPreset, GroupIntent, decyzje usera
│   ├── planning.py                      NOWY — PlanTask, ExecutionPlan, błędy planu
│   ├── discovery.py                     NOWY — grupowanie plików bez probe
│   ├── inspection.py                    NOWY — probe/walidacja i enriched SourceGroup
│   ├── planner.py                       NOWY — deterministyczny DAG
│   ├── events.py                        NOWY — RunEvent i thread-safe event bridge
│   ├── cancellation.py                  NOWY — wspólny token wątków/subprocessów
│   ├── scheduler.py                     NOWY — bounded queues i koordynator grafu
│   ├── handlers.py                      NOWY — jawne adaptery tasków do serwisów
│   ├── publisher.py                     NOWY — atomowa publikacja sidecarów
│   ├── results.py                       NOWY w kroku 2, rozszerzony w 8 — wyniki wykonania
│   ├── sessions.py                      NOWY — jeden właściciel temp i cleanupu runu
│   └── service.py                       NOWY — AppService używany przez TUI/CLI
├── services/
│   ├── media/                           NOWY — neutralna granica kontenerów
│   │   ├── AGENTS.md                    NOWY
│   │   ├── CLAUDE.md                    NOWY — @AGENTS.md
│   │   ├── __init__.py                  NOWY
│   │   ├── types.py                     NOWY — neutralne tracki/probe
│   │   ├── probe.py                     NOWY — dispatch MKV/MP4
│   │   ├── mkv.py                       NOWY — adapter mkvmerge identify
│   │   └── mp4.py                       NOWY — adapter ffprobe identify
│   ├── extraction/
│   │   ├── service.py                   ZMIANA — neutralny dispatch MKV/MP4
│   │   ├── types.py                     ZMIANA — neutralny request/result
│   │   ├── mkv.py                       NOWY — ekstrakcja przez MKVToolNix
│   │   └── mp4.py                       NOWY — ekstrakcja/normalizacja przez FFmpeg
│   └── composition/                     ZMIANA — MKV/MP4 jako osobne cele
├── tui/                                 NOWY — wyłącznie prezentacja Textual
│   ├── AGENTS.md                        NOWY
│   ├── CLAUDE.md                        NOWY — @AGENTS.md
│   ├── __init__.py                      NOWY
│   ├── app.py                           NOWY — AniShiftApp i routing ekranów
│   ├── commands.py                      NOWY — parser krótkiego command bara
│   ├── messages.py                      NOWY — komunikaty UI z RunEvent
│   ├── state.py                         NOWY — stan sesji i drafty formularzy
│   ├── theme.tcss                       NOWY — stabilny layout >=100x30
│   ├── screens/
│   │   ├── workspace.py                 NOWY
│   │   ├── auto.py                      NOWY
│   │   ├── manual.py                    NOWY
│   │   ├── settings.py                  NOWY
│   │   ├── preview.py                   NOWY
│   │   ├── execution.py                 NOWY
│   │   ├── results.py                   NOWY
│   │   └── tools.py                     NOWY
│   └── widgets/
│       ├── command_bar.py               NOWY — stałe `❯` + status footer
│       ├── group_table.py               NOWY
│       ├── intent_form.py               NOWY
│       ├── plan_view.py                 NOWY
│       ├── progress_table.py             NOWY
│       └── setting_field.py             NOWY
├── config/
│   ├── field_catalog.py                 NOWY — UI-independent SettingSpec
│   ├── presets.py                       NOWY — wersjonowane presety auto
│   ├── user_settings.py                 ZMIANA — rozbicie, schema v2, jawny zapis
│   └── workspace.py                     ZMIANA — `temp`, bez `output`
├── bootstrap.py                         ZMIANA — buduje AppService i zależności
├── errors.py                            ZMIANA — WorkflowError i błędy wykonania
└── cli/
    ├── main.py                          ZMIANA — default TUI, `run --preset`
    ├── banner.py                        USUNIĘTY
    ├── commands.py                      USUNIĘTY
    ├── completer.py                     USUNIĘTY
    ├── shell.py                         USUNIĘTY
    ├── pipeline_ui.py                   USUNIĘTY
    ├── settings_panel.py                USUNIĘTY
    └── tts_settings.py                  USUNIĘTY

tests/
├── application/
│   ├── fakes.py                         NOWY — publiczne fake handlery/providerzy
│   ├── test_artifacts.py                NOWY
│   ├── test_architecture.py             NOWY — zakazane importy application/UI
│   ├── test_intents.py                  NOWY
│   ├── test_planning.py                 NOWY
│   ├── test_discovery.py                NOWY
│   ├── test_inspection.py               NOWY
│   ├── test_planner.py                  NOWY
│   ├── test_planner_properties.py       NOWY
│   ├── test_publisher.py                NOWY
│   ├── test_events.py                   NOWY
│   ├── test_cancellation.py             NOWY
│   ├── test_results.py                  NOWY
│   ├── test_sessions.py                 NOWY
│   ├── test_scheduler.py                NOWY
│   ├── test_handlers.py                 NOWY
│   └── test_service.py                  NOWY
├── services/media/
│   ├── test_probe_contract.py           NOWY
│   └── test_mp4.py                      NOWY
├── services/extraction/
│   └── test_mp4.py                      NOWY
├── tui/
│   ├── conftest.py                      NOWY — fake AppService
│   ├── test_app.py                      NOWY
│   ├── test_command_bar.py              NOWY
│   ├── test_workspace.py                NOWY
│   ├── test_auto.py                     NOWY
│   ├── test_manual.py                   NOWY
│   ├── test_settings.py                 NOWY
│   ├── test_preview.py                  NOWY
│   ├── test_execution.py                NOWY
│   ├── test_results.py                  NOWY
│   ├── test_tools.py                    NOWY
│   └── test_flow.py                     NOWY — Pilot E2E bez terminala
├── config/
│   ├── test_field_catalog.py            NOWY
│   └── test_presets.py                  NOWY
├── workspace/
│   └── test_temp_lifecycle.py           NOWY
├── e2e/
│   ├── conftest.py                      NOWY — małe realne media + fake providerzy
│   └── test_stage9_pipeline.py          NOWY — FFmpeg/MKVToolNix
└── load/
    └── test_stage9_scheduler.py         NOWY — 100 grup, limity i brak leaków
```

`__init__.py` nie jest dodawany do żadnego nowego katalogu pod `tests/`.
Docelowe drzewo nie zawiera `anishift/pipeline/` ani `tests/pipeline/`. Zachowane
typy trafiają do `application/planning.py` lub `application/results.py`, a zachowane
operacje do handlerów albo właściwych `services/`.

### 3.1. Co świadomie wykorzystujemy

| Istniejący element | Decyzja |
|---|---|
| rejestry translation/TTS/LLM | zachować; handler wybiera implementację przez istniejącą fasadę |
| `FileOutcome` i `PipelineReport` | adapter przejściowy; po parytecie zastąpić `GroupResult`/`RunResult` i usunąć razem z całym `pipeline/` |
| `llm_queue.py` i `tts_queue.py` | wykorzystać zachowanie jako test parytetu; docelowo usunąć bez utraty domenowego retry/fallback |
| `PipelineTtsRuntime` | przenieść potrzebny adapter do handlera; jeden `TtsService`/event-loop per run |
| `CompositionService` | zachować jako domenę „jak złożyć”; planner decyduje „co złożyć” |
| `safe_fs` i atomowe zapisy | ponownie użyć w publisherze |
| `doctor` i `setup` | bez zmiany kontraktu; tylko nowy adapter TUI |
| `run_anishift.bat` | zachować; bez argumentów otwiera nowy entrypoint TUI |

### 3.2. Czego nie budujemy

- ogólnego workflow engine ani frameworka pluginów;
- bazy danych, historii runów i migratora plików użytkownika;
- edytora grafu, napisów albo osi czasu;
- agenta, klienta MyAnimeList i pobierarki;
- GUI/webview/Tauri/NiceGUI równolegle do Textual;
- `ProcessPoolExecutor` ani własnego systemu RPC;
- osobnego `output/`; produkty trwałe leżą obok źródła;
- ręcznego sterowania listą etapów pipeline'u;
- snapshotów każdego ekranu i testów surowych bajtów terminala.

---

## 4. Krok 1 — odrzucalny spike Textual

Spike jest pierwszą bramką technologiczną, ale nie jest początkiem architektury
produkcyjnej. Ma odpowiedzieć tylko, czy Textual obsłuży 20 grup, formularz,
progress, cancel, resize i command bar bez własnego frameworka widgetów.

### 4.1. Zależność

```bash
uv add textual
```

Nie dodawać osobno Rich — jest już zależnością Textual i projektu. Nie dodawać
pluginów webowych ani snapshot frameworka w tym kroku.

### 4.2. `scripts/spikes/textual_stage9.py`

Jednorazowy plik zawiera lokalne fake modele, jedną `App`, tabelę 20 grup, modal
manual, symulowany worker i dolny `Input` z promptem `❯`. Nie importuje
`anishift.pipeline` i nie definiuje typów, które później trafią do produkcji.

Wymagane identyfikatory widgetów:

```python
GROUP_TABLE_ID = "group-table"
MANUAL_FORM_ID = "manual-form"
COMMAND_INPUT_ID = "command-input"
RUN_BUTTON_ID = "run-button"
CANCEL_BUTTON_ID = "cancel-button"
STATUS_ID = "status-footer"
```

### 4.3. `tests/spikes/test_textual_stage9.py`

Pilot automatycznie:

1. uruchamia aplikację w `size=(100, 30)`;
2. sprawdza 20 wierszy;
3. otwiera formularz manual i zmienia wartość;
4. wpisuje `refresh` po `❯` i sprawdza licznik;
5. uruchamia fake run, nadal porusza focusem i anuluje;
6. zmienia rozmiar poniżej minimum i sprawdza jednoznaczny komunikat;
7. potwierdza, że podwójny Enter nie uruchamia dwóch workerów.

**Bramka kroku 1:**

- PASS — commit spike, zapisz krótkie wnioski w tym planie, a plik usuń w kroku 13;
- FAIL — wykonaj `uv remove textual`, usuń oba pliki spike'a i potwierdź
  `uv lock --check`; nie wybieraj samodzielnie drugiego frameworka, tylko wróć do
  usera z wynikiem bramki. To jedyny punkt, w którym wybór Textual może wrócić do
  decyzji produktowej.

**Weryfikacja kroku 1:**

```bash
uv run pytest tests/spikes/test_textual_stage9.py -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
uv lock --check
```

**Oczekiwane:** Pilot kończy wszystkie siedem scenariuszy bez manualnego wejścia,
interfejs przyjmuje input podczas progressu, a licznik aktywnych workerów wraca do
zera po cancel.

**Wynik spike'a: PASS.** Pięć testów Pilota pokrywa wszystkie siedem scenariuszy:
20 grup, edycję formularza manualnego, komendę `refresh`, responsywność i anulowanie
workera, blokadę podwójnego startu oraz bezpieczny stan terminala `80x24`. Textual
pozostaje wyborem dla produkcyjnego TUI; spike zostaje usunięty w kroku 13.

---

## 5. Krok 2 — kontrakty artefaktów i intencji

Ten krok tworzy także `anishift/application/__init__.py`, `results.py`, `AGENTS.md`
i sprzężony `CLAUDE.md`. `results.py` zawiera na razie tylko `ProducedArtifact` i
`TaskResult`; krok 8 dodaje wyniki grupy/runu bez ponownej definicji tych klas.
`__init__.py` eksportuje wyłącznie stabilne typy potrzebne callerom; nie re-eksportuje
helperów I/O. Instrukcje katalogu zapisują kierunek importów z §2.1 i zakaz
zależności od UI.

### 5.1. `anishift/application/artifacts.py`

Publiczne typy mają postać zamrożonych dataclassów i `StrEnum`. Minimalny kontrakt:

```python
class ArtifactKind(StrEnum):
    VIDEO_MKV = "video_mkv"
    VIDEO_MP4 = "video_mp4"
    SOURCE_SUBTITLES = "source_subtitles"
    FULL_PL = "full_pl"
    SPOKEN_PL = "spoken_pl"
    DISPLAYED_PL = "displayed_pl"
    SOURCE_AUDIO = "source_audio"
    NARRATION_AUDIO = "narration_audio"
    NORMALIZED_SUBTITLES = "normalized_subtitles"
    TTS_CLIP = "tts_clip"
    TTS_MANIFEST = "tts_manifest"
    FINAL_MKV = "final_mkv"
    FINAL_MP4 = "final_mp4"
    STANDALONE_TEXT = "standalone_text"


class ArtifactState(StrEnum):
    MISSING = "missing"
    CANDIDATE = "candidate"
    READY = "ready"
    INVALID = "invalid"


class ArtifactLifetime(StrEnum):
    SOURCE = "source"
    INTERMEDIATE = "intermediate"
    DURABLE = "durable"


class GroupConflictKind(StrEnum):
    TXT_WITH_VIDEO = "txt_with_video"
    SOURCE_PATH_COLLISION = "source_path_collision"
    AMBIGUOUS_PRIMARY = "ambiguous_primary"


@dataclass(frozen=True, slots=True)
class GroupConflict:
    kind: GroupConflictKind
    message: str
    paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class Artifact:
    artifact_id: str
    group_id: str
    kind: ArtifactKind
    path: Path | None
    state: ArtifactState
    lifetime: ArtifactLifetime
    planned_destination: Path | None = None
    language: str | None = None
    subtitle_format: str | None = None
    audio_codec: str | None = None


@dataclass(frozen=True, slots=True)
class SourceGroup:
    group_id: str
    stem: str
    directory: Path
    artifacts: tuple[Artifact, ...]
    conflicts: tuple[GroupConflict, ...] = ()
```

`path=None` jest dozwolone wyłącznie dla zaplanowanego, jeszcze niewytworzonego
artefaktu. Artefakt w stanie `CANDIDATE`, `READY` albo `INVALID` zawsze ma ścieżkę.
`planned_destination` jest wymagane dla `DURABLE`, zabronione dla `INTERMEDIATE` i
dla źródła równe `path`; planner ustala je przed wykonaniem.
`artifact_id` i `group_id` są deterministyczne z grupy, rodzaju oraz — dla wejścia —
normalizowanej ścieżki względnej, nie z `hash()` ani losowego UUID. `SourceGroup`
udostępnia czyste metody wyboru po `ArtifactKind`, ale nie wykonuje I/O.

### 5.2. `anishift/application/intents.py`

```python
class RunMode(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class ProductKind(StrEnum):
    SOURCE_SUBTITLES = "source_subtitles"
    FULL_PL = "full_pl"
    SPOKEN_PL = "spoken_pl"
    DISPLAYED_PL = "displayed_pl"
    NARRATION_AUDIO = "narration_audio"
    MKV = "mkv"
    MP4 = "mp4"


class SubtitleSourcePolicy(StrEnum):
    AUTO = "auto"
    SIDECAR = "sidecar"
    EMBEDDED = "embedded"
    EXTERNAL = "external"
    READY_POLISH = "ready_polish"
    NONE = "none"


class BurnSubtitleProduct(StrEnum):
    NONE = "none"
    SOURCE = "source"
    FULL_PL = "full_pl"
    DISPLAYED_PL = "displayed_pl"


class MkvTrackProduct(StrEnum):
    SOURCE_SUBTITLES = "source_subtitles"
    FULL_PL_SUBTITLES = "full_pl_subtitles"
    DISPLAYED_PL_SUBTITLES = "displayed_pl_subtitles"
    NARRATION_AUDIO = "narration_audio"


class Mp4AudioSource(StrEnum):
    AUTO = "auto"
    ORIGINAL = "original"
    NARRATION = "narration"


class ExternalAudioRole(StrEnum):
    SOURCE_AUDIO = "source_audio"
    NARRATION_MIX = "narration_mix"


class SubtitleOutputFormat(StrEnum):
    PRESERVE = "preserve"
    ASS = "ass"
    SRT = "srt"


class TranslationAction(StrEnum):
    AUTO = "auto"
    TRANSLATE = "translate"
    DO_NOT_TRANSLATE = "do_not_translate"


@dataclass(frozen=True, slots=True)
class ProductIntent:
    requested_products: frozenset[ProductKind]
    burn_subtitle_product: BurnSubtitleProduct = BurnSubtitleProduct.NONE
    mkv_tracks: frozenset[MkvTrackProduct] = frozenset()
    mp4_audio_source: Mp4AudioSource = Mp4AudioSource.AUTO


@dataclass(frozen=True, slots=True)
class GroupIntent:
    group_id: str
    mode: RunMode
    products: ProductIntent
    subtitle_source_policy: SubtitleSourcePolicy = SubtitleSourcePolicy.AUTO
    translation_action: TranslationAction = TranslationAction.AUTO
    preferred_video_artifact_id: str | None = None
    selected_subtitle_artifact_id: str | None = None
    selected_audio_artifact_id: str | None = None
    selected_audio_track_id: int | None = None
    selected_subtitle_track_id: int | None = None
    source_subtitle_language: str | None = None
    external_audio_role: ExternalAudioRole | None = None
    subtitle_output_format: SubtitleOutputFormat = SubtitleOutputFormat.PRESERVE
```

`AutoPreset` przechowuje wszystkie pola wspólne z `GroupIntent` poza `group_id` i
manualnymi artifact/track ID. `apply_preset(preset, groups)` tworzy osobny
`GroupIntent` dla każdej zaznaczonej grupy.

### 5.3. `anishift/application/planning.py`

Definiuje `TaskKind`, `TaskState`, `PlanTask`, `GroupPlan`, `ExecutionPlan`,
`PlanProblem` oraz stabilny topologiczny porządek. `PlanTask` wskazuje wejściowe i
wyjściowe `artifact_id`, nie ścieżki wybierane w UI.

```python
@dataclass(frozen=True, slots=True)
class PlanTask:
    task_id: str
    group_id: str
    kind: TaskKind
    requires: tuple[str, ...]
    produces: tuple[str, ...]
    depends_on: tuple[str, ...]
    resource_key: str
    is_network: bool = False
    is_paid: bool = False


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    groups: tuple[GroupPlan, ...]
    tasks: tuple[PlanTask, ...]
    settings: RunSettingsSnapshot
    problems: tuple[PlanProblem, ...]

    @property
    def can_execute(self) -> bool:
        return not any(problem.is_blocking for problem in self.problems)
```

`RunSettingsSnapshot` jest osobnym zamrożonym modelem w tym pliku. Zawiera tylko
zwalidowane wartości potrzebne plannerowi i schedulerowi: profile providerów,
fallbacki, retry, kolejność i limity. Nie przechowuje draftu UI ani sekretów w
postaci przeznaczonej do renderowania.

### 5.4. `anishift/application/results.py` — kontrakty wyniku taska

Te typy należą wyłącznie do `results.py`; `planning.py` tylko je importuje tam,
gdzie adnotacja jest konieczna. Nie definiować ich ponownie w schedulerze:

```python
@dataclass(frozen=True, slots=True)
class ArtifactSnapshot:
    artifacts: Mapping[str, Artifact]

    def require_ready(self, artifact_id: str) -> Artifact: ...


@dataclass(frozen=True, slots=True)
class ProducedArtifact:
    artifact_id: str
    path: Path
    metadata: Mapping[str, str | int | bool]


@dataclass(frozen=True, slots=True)
class TaskResult:
    task_id: str
    outputs: tuple[ProducedArtifact, ...]
```

### 5.5. `anishift/application/cancellation.py` — minimalny Protocol

W tym samym kroku moduł udostępnia wąski Protocol potrzebny adapterom,
bez uruchamiania schedulera:

```python
class CancellationToken(Protocol):
    def is_cancelled(self) -> bool: ...
    def raise_if_cancelled(self) -> None: ...

class CommitCancellationToken(CancellationToken, Protocol):
    def commit_if_active(self, action: Callable[[], None]) -> bool: ...
```

Minimalny `CancellationToken` pozostaje granicą handlerów i serwisów. Rozszerzony
`CommitCancellationToken` zna wyłącznie scheduler. Fake `NeverCancelledToken` służy
testom kroków 3–7, a produkcyjny `EventCancellationToken` powstaje w kroku 8.
`commit_if_active()` serializuje tylko krótki finalny `replace()` z równoległym
`cancel()`; długa praca nadal sprawdza dwa pozostałe wywołania i nigdy nie wykonuje
się pod tą blokadą. Analogiczna
`RunSession.commit_if_generation()` obejmuje ten sam `replace()` blokadą generacji,
więc cleanup nie może zamknąć scope pomiędzy sprawdzeniem a publikacją.

### 5.6. `anishift/errors.py` — diff

Dodać `WorkflowError(AniShiftError)`, `PlanningError(WorkflowError)`,
`ExecutionError(WorkflowError)` i `RunConflictError(WorkflowError)`. Oczekiwane
konflikty planu pozostają wartościami `PlanProblem`; wyjątki służą uszkodzonemu
kontraktowi, próbie wykonania niewykonalnego planu i konfliktowi aktywnego runu.
Nie tworzyć drugiej hierarchii w `application/errors.py`.

### 5.7. Testy kroku 2

- `tests/application/test_artifacts.py` — nazwy, ID, final container never input;
- `tests/application/test_architecture.py` — model/planner bez importów I/O, UI i
  serwisów; TUI/CLI zależą tylko od publicznego `AppService`;
- `tests/application/test_intents.py` — niezależne kopie presetów i walidacja pól;
- `tests/application/test_planning.py` — acykliczność, stabilny porządek i problemy.

**Weryfikacja kroku 2:**

```bash
uv run pytest tests/application/test_artifacts.py tests/application/test_architecture.py tests/application/test_intents.py tests/application/test_planning.py -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** wszystkie modele są immutable i serializowalne w testach, planowany
artefakt może nie mieć jeszcze ścieżki runtime, a żaden worker nie otrzymuje
mutowalnego `ArtifactStore`.

---

## 6. Krok 3 — discovery i nazwane reguły

### 6.1. `anishift/application/discovery.py`

`discover_groups(root: Path) -> DiscoveryResult` wykonuje pojedynczy, posortowany
odczyt katalogu i rozdziela klasyfikację nazwy od grupowania. Nie odpala ffprobe,
mkvmerge ani parsera napisów.

`ArtifactName` jest wewnętrznym zamrożonym wynikiem parsera nazwy: `path`, `stem`,
`kind`, `is_primary`, `is_derived` i opcjonalny format/kodek. `DiscoveryResult`
zawiera posortowane `groups`, konflikty bez grupy i ostrzeżenia. Żaden z tych typów
nie przechowuje uchwytu pliku ani wyniku probe.

Reguły są jawnymi czystymi funkcjami o nazwach z wymagań:

```python
def is_primary_source(path: Path) -> bool: ...
def is_derived_product(path: Path) -> bool: ...
def classify_artifact(path: Path) -> ArtifactName | None: ...
def choose_primary_video(candidates: Sequence[Artifact]) -> Artifact | None: ...
def choose_auto_sidecar(candidates: Sequence[Artifact]) -> Artifact | None: ...
def group_candidates(candidates: Sequence[ArtifactName]) -> tuple[SourceGroup, ...]: ...
```

Kolejność `auto`: MKV przed MP4, exact-stem sidecar przed embedded, ASS przed SRT.
Sam produkt pochodny nie tworzy grupy. TXT z rdzeniem filmu daje konflikt.
Uszkodzony ASS pozostaje kandydatem; discovery nie zgaduje jego poprawności.

### 6.2. Kontrakt wejściowy dla inspekcji realizowanej w kroku 4

To jest obowiązkowa faza I/O pomiędzy discovery i czystym plannerem. Plik powstaje
dopiero w kroku 4, po dodaniu neutralnego probe. Przyjmuje
`DiscoveryResult`, uruchamia probe kontenerów, waliduje kandydatów ASS/SRT oraz
zwraca nowy, zamrożony `InspectedWorkspace`. Nie mutuje `SourceGroup` z discovery.

```python
@dataclass(frozen=True, slots=True)
class InspectedSourceGroup:
    source: SourceGroup
    artifacts: tuple[Artifact, ...]
    media_catalogs: Mapping[str, MediaCatalog]
    conflicts: tuple[GroupConflict, ...]


@dataclass(frozen=True, slots=True)
class InspectedWorkspace:
    groups: tuple[InspectedSourceGroup, ...]
    warnings: tuple[InspectionWarning, ...]


class WorkspaceInspector:
    def inspect(
        self,
        discovery: DiscoveryResult,
        *,
        cancel: CancellationToken,
    ) -> InspectedWorkspace: ...

    def register_external_subtitle(
        self,
        group: InspectedSourceGroup,
        path: Path,
        *,
        declared_language: str | None,
        cancel: CancellationToken,
    ) -> InspectedSourceGroup: ...

    def register_external_audio(
        self,
        group: InspectedSourceGroup,
        path: Path,
        *,
        role: ExternalAudioRole,
        cancel: CancellationToken,
    ) -> InspectedSourceGroup: ...
```

Walidacja napisów parsuje format, odrzuca pusty plik i ustawia `READY` albo
`INVALID`. Nie wykrywa języka z treści; język pochodzi z jednoznacznego suffixu,
metadanych tracka albo jawnej deklaracji manual. Zewnętrzne audio przechodzi pełny
decode przez FFmpeg, ma znany czas trwania i różnicę względem obrazu nie większą
niż konfigurowalny próg domyślny 1 s. Rejestracja nie kopiuje wejścia do katalogu
źródła — tworzy tylko zwalidowany artefakt sesji manual.

Po inspection wybór auto jest jednoznaczny: poprawny exact-stem ASS, następnie
poprawny exact-stem SRT, następnie track embedded według polityki języka. Przypadek
uszkodzonego `1.ass` i poprawnego `1.srt` wybiera SRT. Planner otrzymuje wyłącznie
`InspectedSourceGroup` i nie wykonuje sam żadnego I/O.

### 6.3. Testy discovery

Tabela golden obejmuje co najmniej:

| Pliki | Wynik |
|---|---|
| `1.mkv` | jedna grupa, MKV primary |
| `1.mp4` | jedna grupa, MP4 primary |
| `1.mkv`, `1.mp4` | jedna grupa, MKV auto, obie alternatywy |
| `1.ass`, `1.srt`, `1.mkv` | jedna grupa, ASS auto |
| `1.pl.srt` | zero grup auto |
| `1.txt` | jedna grupa standalone |
| `1.txt`, `1.mkv` | jedna grupa z blokującym konfliktem |
| `show.displayed.mkv` | zwykłe źródło, nie produkt |
| `show.pl.mkv` | produkt, nie źródło |

Property test losuje kolejność zwracaną przez filesystem i wymaga identycznego
`DiscoveryResult`.

**Weryfikacja kroku 3:**

```bash
uv run pytest tests/application/test_discovery.py -v
uv run pytest tests/pipeline/test_pipeline_runner.py -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** kolejność wpisów filesystemu nie zmienia grup ani konfliktów, a
discovery nie uruchamia probe ani parsera napisów.

---

## 7. Krok 4 — neutralny probe MKV/MP4

Ten krok tworzy `anishift/services/media/__init__.py`, `AGENTS.md` i sprzężony
`CLAUDE.md`. Publiczne eksporty obejmują wyłącznie neutralne typy i `MediaProbe`;
adaptery mkv/mp4 pozostają detalem paczki.

### 7.1. `anishift/services/media/types.py`

```python
class ContainerKind(StrEnum):
    MKV = "mkv"
    MP4 = "mp4"


class MediaTrackKind(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
    SUBTITLES = "subtitles"


@dataclass(frozen=True, slots=True)
class MediaTrack:
    track_id: int
    kind: MediaTrackKind
    codec_id: str
    language: str | None
    name: str | None
    is_default: bool
    is_forced: bool
    subtitle_format: str | None = None


@dataclass(frozen=True, slots=True)
class MediaCatalog:
    path: Path
    container: ContainerKind
    duration_us: int
    tracks: tuple[MediaTrack, ...]
    attachments: tuple[str, ...] = ()
```

### 7.2. `anishift/services/media/mkv.py` i `anishift/services/media/mp4.py`

- MKV adapter mapuje obecne `extraction.MediaInfo` na `MediaCatalog`;
- MP4 adapter uruchamia kontrolowane `ffprobe -show_streams -show_format -of json`;
- oba adaptery mapują brak języka do `None`, nie do magicznego `und`;
- adaptery wyłącznie identyfikują kontener; nie wykonują ekstrakcji;
- subprocess otrzymuje timeout i token anulowania, cancel zamyka proces;
- żadna logika poza adapterem nie sprawdza `.suffix == ".mkv"`.

### 7.3. `anishift/services/media/probe.py`

```python
class MediaProbe(Protocol):
    def identify(
        self,
        path: Path,
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> MediaCatalog: ...


class DefaultMediaProbe:
    def identify(
        self,
        path: Path,
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> MediaCatalog:
        match path.suffix.casefold():
            case ".mkv":
                return identify_mkv(path, cancel=cancel, timeout_s=timeout_s)
            case ".mp4":
                return identify_mp4(path, cancel=cancel, timeout_s=timeout_s)
            case _:
                raise UnsupportedMediaError(...)
```

`MediaError(WorkflowError)`, `MediaProbeError(MediaError)` oraz
`UnsupportedMediaError(MediaError)` trafiają do głównej hierarchii w
`anishift/errors.py`. Timeout i cancel nie są stringami w wyniku probe.

### 7.4. `anishift/services/extraction/{service,types,mkv,mp4}.py`

Probe i ekstrakcja pozostają osobnymi odpowiedzialnościami. `ExtractionService`
przyjmuje `ExtractionRequest(media_path, track_id, target_format, target_path)`,
token i timeout. Adapter MKV deleguje do obecnego MKVToolNix, adapter MP4 do FFmpeg.
Tekstowy track `mov_text`/`tx3g` z MP4 jest normalizowany do SRT; plan nie zakłada
embedded ASS w MP4. Każdy adapter zapisuje wyłącznie do wskazanego run scope,
sprawdza niepusty wynik i zwraca `ExtractionResult`, nigdy sam nie publikuje sidecara.

### 7.5. `anishift/application/inspection.py`

Zaimplementować dokładnie kontrakt z §6.2, teraz na gotowym `MediaProbe` i
`ExtractionService`. Minimalny `CancellationToken` Protocol (`is_cancelled()` i
`raise_if_cancelled()`) jest zdefiniowany w kroku 2, a implementacja oparta na
`threading.Event` powstaje w kroku 8; dzięki temu zależności kroków są zielone.

### 7.6. Testy kroku 4

- wspólny contract test dla fake payloadów MKV i MP4;
- snapshot neutralnego katalogu tego samego materiału w obu kontenerach;
- MP4 `mov_text`/`tx3g` extraction i normalizacja do SRT;
- brak/pusty output, timeout, cancel i bezpieczne znaki ścieżki;
- regresja istniejących testów MKV extraction.

`tests/application/test_inspection.py` dodaje: uszkodzony ASS + poprawny SRT,
embedded tracki MKV/MP4, ręcznie zadeklarowany język, nieznany język bez zgadywania,
zewnętrzny subtitle spoza workspace, zewnętrzne audio z pełnym decode i różnicą
czasu `<=1 s`/`>1 s`, uszkodzony decode oraz cancel podczas probe.

**Weryfikacja kroku 4:**

```bash
uv run pytest tests/services/media tests/services/extraction tests/application/test_inspection.py -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** ten sam materiał MKV/MP4 daje neutralny katalog, MP4 `mov_text`
staje się poprawnym SRT, cancel/timeout kończy subprocess, a zwalidowany workspace
jest jedynym wejściem do planera.

---

## 8. Krok 5 — deterministyczny planner DAG

### 8.1. `anishift/application/planner.py`

Publiczne API:

```python
def plan_auto(
    groups: Sequence[InspectedSourceGroup],
    preset: AutoPreset,
    settings: RunSettingsSnapshot,
) -> ExecutionPlan: ...


def plan_manual(
    groups: Sequence[InspectedSourceGroup],
    intents: Mapping[str, GroupIntent],
    settings: RunSettingsSnapshot,
) -> ExecutionPlan: ...
```

Planner pracuje od produktów wstecz:

1. tworzy wymagane artefakty końcowe;
2. wybiera lub tworzy producenta każdego brakującego artefaktu;
3. rekurencyjnie rozwiązuje wejścia producenta;
4. deduplikuje wspólne zależności;
5. wylicza `depends_on` i stabilny topological order;
6. waliduje deklaracje języka, dostępność artifact ID i kolizje bez wykonywania I/O;
7. dopiero na końcu zwraca preview z kosztami, siecią i nadpisaniami.

Minimalna tabela producentów:

| Artefakt | Producent |
|---|---|
| `SOURCE_SUBTITLES` | exact-stem source albo extraction |
| `FULL_PL` | translation albo Polish source bypass + split/write |
| `SPOKEN_PL` | split z polskiego dokumentu |
| `DISPLAYED_PL` | split z polskiego dokumentu |
| `NARRATION_AUDIO` | TTS + audio mix |
| `FINAL_MKV` | composition MKV |
| `FINAL_MP4` | composition MP4 |

Reguły krytyczne:

- `auto` nigdy nie używa derived product jako input;
- `manual` używa wyłącznie artifact ID wskazanego w `GroupIntent`;
- `.pl` bez tłumaczenia wymaga źródła zadeklarowanego jako `pol`;
- `TRANSLATE` wymusza tłumaczenie nawet dla artefaktu rozpoznanego jako polski;
- `DO_NOT_TRANSLATE` dla niepolskiego/nieznanego źródła może utworzyć wyłącznie
  `SOURCE_SUBTITLES` albo burn source; żądanie produktu `.pl` jest blokującym
  `PlanProblem`, a nie zmianą suffixu;
- `source_subtitles` exact-stem jest już spełniony i nie jest nadpisywany;
- external subtitle jest kopiowany tylko przy jawnym produkcie
  `source_subtitles` i tylko bez kolizji;
- `narration_audio` pozostaje w `temp`, jeżeli jest wyłącznie zależnością kontenera;
- oba kontenery współdzielą napisy i lektora, ale mają osobne taski composition;
- TXT tworzy tylko `.pl.srt` i nie wchodzi w multimedia;
- niewykonalny plan nie zawiera tasku płatnego gotowego do wykonania.

### 8.2. `tests/application/test_planner.py`

Parametryzacja obejmuje wszystkie scenariusze §9 wymagań, każdy pojedynczy produkt,
oba kontenery, wszystkie manualne punkty startowe i konflikty.

### 8.3. `tests/application/test_planner_properties.py`

Hypothesis nie jest dodawane tylko dla jednego testu, jeżeli nie jest już
zależnością. W takim wypadku deterministyczny generator w pytest buduje co najmniej
500 poprawnych kombinacji z ustalonym seedem. Inwarianty:

- graf jest acykliczny;
- każdy task ma producentów wymaganych wejść;
- brak zbędnego tasku;
- źródło nie jest targetem publikacji;
- identyczne wejście daje identyczny plan;
- żaden derived product nie jest inputem auto.

Testy obejmują również dwa źródła w grupie (`1.mkv` + `1.mp4`), dwa sidecary
(`1.ass` + `1.srt`), wymuszone tłumaczenie poprawnego `1.pl.srt`, zakaz fałszywego
`.pl` dla nieznanego języka oraz osobne manual intents trzech grup.

**Weryfikacja kroku 5:**

```bash
uv run pytest tests/application/test_planner.py tests/application/test_planner_properties.py -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** planner nie otwiera plików, ten sam snapshot zawsze daje identyczny
DAG, a żaden task sieciowy/płatny nie istnieje w niewykonalnym planie.

---

## 9. Krok 6 — publikacja i wielokrotne produkty

### 9.1. `anishift/application/publisher.py`

```python
@dataclass(frozen=True, slots=True)
class PublishRequest:
    source: Path
    destination: Path
    expected_kind: ArtifactKind


class ArtifactPublisher:
    def publish(self, request: PublishRequest) -> Artifact:
        ...
```

Publisher waliduje tymczasowy plik, kopiuje/przenosi go do tymczasowego siblinga,
wykonuje `replace()` dopiero po walidacji i nigdy nie usuwa poprzedniego produktu
przed sukcesem. Nie publikuje do `workspace/output`.

### 9.2. `anishift/services/composition/types.py` — kompatybilna zmiana

Nie zmieniać istniejącego `CompositionPlan` ani `OutputVariant` w miejscu, bo stary
runner używa ich do kroku 16. Dodać obok nich docelowy kontrakt jednego celu:

```python
class ContainerTarget(StrEnum):
    MKV = "mkv"
    MP4 = "mp4"


@dataclass(frozen=True, slots=True)
class ContainerCompositionRequest:
    source_video: Path
    destination: Path
    target: ContainerTarget
    burn_subtitle: Path | None
    attached_subtitles: tuple[AttachedSubtitle, ...]
    narration_audio: Path | None
    keep_original_audio: bool


@dataclass(frozen=True, slots=True)
class ContainerCompositionResult:
    source_path: Path
    target: ContainerTarget
    output_path: Path
    output_size_bytes: int
    source_size_bytes: int
    duration_ms: float
    warnings: tuple[str, ...] = ()
```

Jeden `GroupPlan` może zawierać dwa niezależne taski composition. Nowa metoda
`CompositionService.compose_container(request, *, cancel)` tworzy wyłącznie jeden
kontener i zwraca nowy `ContainerCompositionResult`. Używa istniejącego
`AttachedSubtitle` (`role`, `language`, `track_name`) zamiast definiować jego duplikat.
Nie zwraca ani nie rozmieszcza sidecarów. Legacy `CompositionResult`,
`compose(CompositionPlan)` i wszystkie ich pola pozostają bez zmiany do
automatycznego przełączenia callerów w kroku 16.

### 9.3. Adapter bez łamania starego runnera

- dodać w `application/handlers.py` adapter
  `build_composition_request(task, artifacts)`, początkowo nieużywany przez legacy;
- usunąć decyzję „co wypalać” z obecności lektora;
- korzystać z `burn_subtitle_product`, `mkv_tracks` i `mp4_audio_source` planera;
- destination zawsze obok wybranego źródła;
- nie czyścić `temp`; lifecycle należy wyłącznie do `RunSession`;
- nie usuwać ani nie zmieniać sygnatur `build_plan`, `compose_outcomes`,
  `composition_runtime.py` i `compose_only.py` w tym kroku.

### 9.4. Testy kroku 6

- awaria przed `replace()` zachowuje poprzedni plik bajt w bajt;
- MKV i MP4 z jednego planu używają tego samego narration artifact;
- MP4 bez burn i bez lektora działa;
- MKV z wybranym zbiorem tracków działa;
- composition nie publikuje sidecarów;
- źródło nigdy nie jest destination.

**Weryfikacja kroku 6:**

```bash
uv run pytest tests/application/test_publisher.py tests/services/composition tests/pipeline/test_composition_runtime.py -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** pełny legacy pipeline nadal przechodzi bez zmian, nowy kontrakt umie
zbudować niezależnie MKV i MP4, a awaria publikacji nie narusza starego produktu.

---

## 10. Krok 7 — typowany katalog ustawień i presety

### 10.1. `anishift/config/field_catalog.py`

```python
class SettingScope(StrEnum):
    GLOBAL = "global"
    ENGINE_PROFILE = "engine_profile"
    AUTO_PRESET = "auto_preset"
    MANUAL_RUN = "manual_run"
    SECRET = "secret"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class SettingSpec:
    setting_id: str
    label: str
    description: str
    value_type: SettingValueType
    default: SettingValue
    scope: SettingScope
    allowed_values: tuple[SettingValue, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    depends_on: tuple[SettingCondition, ...] = ()
    invalidates: frozenset[ArtifactKind] = frozenset()
    is_secret: bool = False
```

`setting_catalog(context) -> tuple[SettingSpec, ...]` jest jedynym źródłem pól TUI.
Specyfikacje zależne od silnika powstają z istniejących registry/options, bez live
requestów i bez syntezy.

Implementacja odwzorowuje jeden-do-jednego pełny katalog z §13 wymagań: globalne,
translation, LLM split, Edge, ElevenBytes run6/run7, oficjalny ElevenLabs, oba
profile SAPI, audio, composition oraz sekrety. Test porównuje jawny zbiór ID z
publicznymi polami `UserSettings` i opcjami registry; nowe pole bez decyzji
`visible/conditional/internal/removed` powoduje błąd, więc katalog nie może po
cichu przestać być pełny.

### 10.2. `anishift/config/presets.py`

- `AutoPresetFile(schema_version, presets, default_preset_id)`;
- `load_presets()` nigdy nie zwraca częściowo niepoprawnego presetu;
- `save_presets()` jest atomowe i wywoływane tylko po jawnej akcji;
- sekrety są typowo niedozwolone w modelu presetu;
- preset manual nie istnieje.

### 10.3. `anishift/config/user_settings.py` — rozbicie

Plik zachowuje publiczne `UserSettings`, `load_user_settings` i
`save_user_settings`, lecz definicje pól i helpery profili przenosi do małych
modułów. `schema_version=2`:

- usuwa trwałe `mode` jako decyzję pipeline'u;
- zapis v2 zawiera przejściowe, deprecated `output_variant` do kroku 16, ponieważ
  stary REPL nadal je odczytuje; pole nie jest pokazywane w nowym katalogu TUI;
- dodaje realne `translation_concurrency` 1–16;
- zachowuje globalne profile silników;
- legacy loader mapuje `players/merge/burn` oraz `output_variant` na domyślny zestaw
  produktów w pamięci;
- stary plik nie jest nadpisywany przy odczycie; dopiero `Save` zapisuje v2.

Po przełączeniu entrypointów w kroku 16 `output_variant` zostaje usunięte z modelu
i zapisu w tym samym commicie co ostatni caller. Do tego momentu test uruchamia
legacy `/compose` po zapisaniu schema v2 i dowodzi kompatybilności.

### 10.4. Test kontraktu katalogu

Jeden introspekcyjny test wymaga dla każdego widocznego pola: stabilnego ID, typu,
defaultu, zakresu, scope, opisu, sekretności i poprawnych zależności. Osobne case'y
pokrywają Edge, ElevenBytes run6/run7, ElevenLabs i oba profile SAPI.

**Weryfikacja kroku 7:**

```bash
uv run pytest tests/config/test_field_catalog.py tests/config/test_presets.py tests/config/test_user_settings.py -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** pełny katalog ma dokładnie jedno `SettingSpec` dla każdego
edytowalnego pola, sekret nigdy nie trafia do presetu, a zapis schema v2 nie psuje
starego `/compose` przed krokiem przełączenia.

---

## 11. Krok 8 — application events, cancel i wyniki

### 11.1. `anishift/application/events.py`

```python
class RunEventKind(StrEnum):
    RUN_STARTED = "run_started"
    TASK_QUEUED = "task_queued"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_RETRY = "task_retry"
    TASK_FALLBACK = "task_fallback"
    TASK_FINISHED = "task_finished"
    GROUP_FINISHED = "group_finished"
    RUN_FINISHED = "run_finished"


@dataclass(frozen=True, slots=True)
class RunEvent:
    run_id: str
    sequence: int
    kind: RunEventKind
    group_id: str | None
    task_id: str | None
    state: TaskState | None
    progress_percent: int | None
    message: str | None


@dataclass(frozen=True, slots=True)
class WorkerNotification:
    kind: WorkerNotificationKind
    task_id: str
    progress_percent: int | None = None
    message: str | None = None
```

`sequence` rośnie w jednym koordynatorze. UI ignoruje event z innym `run_id` lub
starszym sequence. `RunEventSink.emit()` jest observerem; jego błąd jest logowany,
ale nie zmienia wyniku tasku.

Worker/serwis emituje tylko `WorkerNotification`; nie zna `run_id`, sequence ani
stanu grafu. `EventBuffer.push(event)` jest thread-safe. `drain()` atomowo zwraca
wszystkie eventy terminalne/stanu oraz najwyżej ostatni progress per task i usuwa
je z bufora. Dzięki temu wolniejsze renderowanie TUI nie powoduje nieograniczonego
wzrostu pamięci, a żaden event terminalny nie ginie.

### 11.2. `anishift/application/cancellation.py`

`EventCancellationToken` implementuje Protocol z kroku 2, opakowuje
`threading.Event`, posiada `cancel()`,
`is_cancelled`, `raise_if_cancelled()` i jest bezpieczny dla wielokrotnego cancel.
Scheduler sprawdza go przed admission, handler przekazuje event do istniejących
serwisów, a subprocess watcher kończy proces.

### 11.3. `anishift/application/results.py` — rozszerzenie

Istniejące `TaskResult` pozostaje jednym typem; nie definiować drugiej klasy o tej
nazwie. Dodać `GroupResult` i `RunResult`. Wszystkie są immutable. `GroupStatus` rozróżnia
`succeeded`, `partial`, `failed`, `cancelled`. TUI `done` jest tylko filtrem
stanów terminalnych, nie wartością domeny.

### 11.4. `anishift/application/sessions.py`

`RunSession` jest jedynym właścicielem katalogu runu i generation gate. Otrzymuje
jawny `run_root` przy konstrukcji, tworzy scope przez context manager, udostępnia
`group_temp(group_id)`, `accepts_generation(generation)` i w swoim `__exit__`
wykonuje końcowy cleanup. Scheduler nie usuwa katalogów, publisher nie usuwa scope,
a handler odpowiada tylko za niedokończone pliki swojego taska. W tym kroku testy
używają katalogu tymczasowego pytest; podłączenie `workspace/temp` następuje w
kroku 11.

### 11.5. Testy kroku 8

- monotoniczne sequence i izolacja run IDs;
- wyjątek observera nie przerywa pracy;
- wielokrotny cancel jest idempotentny;
- wyniki częściowe zachowują ukończone produkty;
- brak pełnych ścieżek/sekretów w publicznym błędzie eventu.
- `EventBuffer.drain()` nie gubi terminalnych eventów i ogranicza progress;
- `RunSession` sprząta po sukcesie, wyjątku i cancel oraz odrzuca późną generację.

**Weryfikacja kroku 8:**

```bash
uv run pytest tests/application/test_events.py tests/application/test_cancellation.py tests/application/test_results.py tests/application/test_sessions.py -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** tylko coordinator tworzy numerowane `RunEvent`, cancel jest
idempotentny, a dokładnie jeden context manager posiada końcowy cleanup runu.

---

## 12. Krok 9 — strumieniowy scheduler grafu

### 12.1. `anishift/application/scheduler.py`

Publiczna granica:

```python
class TaskHandler(Protocol):
    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult: ...


class GraphScheduler:
    def run(
        self,
        plan: ExecutionPlan,
        *,
        cancel: CancellationToken,
        events: RunEventSink,
    ) -> RunResult: ...
```

Mutable `ArtifactStore` jest prywatnym runtime state tego modułu, nie częścią
`planning.py` ani publicznej fasady. `snapshot(task.requires)` zwraca nowy
`ArtifactSnapshot`. Tylko coordinator wywołuje `register(result.outputs)` i stosuje
regułę zależną od lifetime:

- `INTERMEDIATE` musi istnieć wewnątrz dokładnego run/group scope;
- handler zwraca `DURABLE` jako zwalidowany staging wewnątrz dokładnego run/group
  scope z `metadata["validated"] is True`, nigdy jako już opublikowany produkt;
- coordinator dopiero po sprawdzeniu cancel, generation gate i `strict_natural`
  atomowo przenosi staging pod dokładnie `planned_destination`, a do końcowego
  `TaskResult` wpisuje docelową ścieżkę i `metadata["published"] is True`;
- `SOURCE` nigdy nie może być outputem taska.

Rejestracja odrzuca brak pliku, staging poza scope, niezgodny `artifact_id`, brak
potwierdzenia walidacji oraz dwa różne wyniki dla tego samego ID. Task publikujący
trwały wynik produkuje dokładnie jeden artefakt, aby nie udawać atomowości transakcji
wieloplikowej. Store nie jest przekazywany workerowi.

Algorytm:

1. odrzuca plan z blokującym problemem;
2. buduje liczniki nierozstrzygniętych zależności i reverse edges;
3. umieszcza taski z licznikiem zero w bounded queue ich `resource_key`;
4. scheduler submituje najwyżej tyle tasków, ile pozwala pula zasobu, i emituje
   `queued/running/progress`;
5. koordynator odbiera ukończone `Future`, zapisuje `TaskResult` i zmniejsza liczniki;
6. awaria blokuje wyłącznie zależne taski tej grupy;
7. niezależne grupy pracują dalej;
8. po cancel scheduler nie przyjmuje nowej pracy, anuluje nieuruchomione future'y,
   sygnalizuje aktywne handlery i czeka na kontrolowany shutdown;
9. `finally` wywołuje `shutdown(cancel_futures=True)` dla pul; cleanup runu wykonuje
   zewnętrzny `RunSession` należący do `AppService`.

Nie używać jednego globalnego executora ani submitować wszystkich tasków z góry.
`concurrent.futures.wait(..., return_when=FIRST_COMPLETED)` służy wyłącznie do
odbioru zakończeń; typowane `TaskResult` pozostają właścicielem błędów domenowych.

### 12.2. Polityki zasobów

```python
@dataclass(frozen=True, slots=True)
class ResourceLimits:
    extraction: int
    translation: Mapping[str, int]
    tts_group_jobs: int
    audio: int
    composition: int
    max_pending_per_resource: int
```

- SAPI zawsze `1`;
- LLM maksymalnie `4`;
- `translation_concurrency` rzeczywiście ogranicza Google/DeepL;
- `tts_group_jobs` ogranicza tylko coarse jobs; provider cap i request-level
  concurrency pozostają wyłącznie w `TtsScheduler`;
- composition default `1`, aby nie wysycić dysku; ustawienie pozostaje internal;
- dla każdego zasobu
  `submitted_not_done <= worker_limit + max_pending_per_resource`; dalsze taski
  pozostają gotowe wyłącznie w stanie koordynatora.

### 12.3. `ready_first` i `strict_natural`

`NaturalOrderGate` otrzymuje uporządkowane group IDs. W `strict_natural` task może
się wykonać, ale jego wynik nie jest publikowany ani przekazany dalej, dopóki
wcześniejsza grupa nie osiągnie stanu terminalnego w tej samej kolejce. `skip()`
rozstrzyga grupę po błędzie/braku tasku, więc gate nie zakleszcza się.

### 12.4. `tests/application/test_scheduler.py`

Fake handler ma konfigurowalne opóźnienie, transient/fatal, liczniki active/max,
progress i kontrolowaną kolejność zakończeń. Testy:

- streaming tasku zależnego przed końcem całej fazy;
- limity per resource/provider;
- awaria jednej grupy nie zatrzymuje drugiej;
- strict gate, skip i brak deadlocku;
- cancel przed admission i podczas niekooperującego fake handlera;
- konflikt dwóch wyników o tym samym artifact ID;
- późny trwały wynik po cancel pozostaje stagingiem i jest usuwany z run scope bez
  zastąpienia wcześniejszego produktu;
- trwały wynik późniejszej grupy w `strict_natural` nie jest widoczny przed bramką;
- różna wielkość liter tego samego klucza providera nie tworzy osobnej puli;
- peak submitted-not-done nie przekracza admission window;
- executory mają ustalone prefiksy, skończony shutdown i nie zostawiają wątków.

Test prawdziwego anulowania subprocessu należy do handlerów w kroku 10; fake test
schedulera dowodzi admission i stanu grafu, nie zachowania FFmpeg.

**Weryfikacja kroku 9:**

```bash
uv run pytest tests/application/test_scheduler.py -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** streaming odblokowuje następcę bez bariery fazy, limity oraz admission
window nigdy nie są przekroczone, a scheduler nie mutuje artefaktów z workera i nie
wykonuje cleanupu sesji.

---

## 13. Krok 10 — handlery istniejących serwisów w trzech zielonych inkrementach

### 13.1. `anishift/application/handlers.py`

Nie tworzyć ogólnego plugin registry. `ExecutionHandlers` jest jawnym dataclassem
z jednym polem per rodzina operacji, a `execute_task()` używa `match TaskKind`.

```python
@dataclass(frozen=True, slots=True)
class ExecutionHandlers:
    media: MediaTaskHandler
    subtitles: SubtitleTaskHandler
    translation: TranslationTaskHandler
    tts: TtsTaskHandler
    audio: AudioTaskHandler
    composition: CompositionTaskHandler
    publish: PublishTaskHandler
```

Każdy handler:

- tłumaczy neutralny `PlanTask` na istniejący config serwisu;
- wywołuje sync fasadę bezpośrednio we właściwej puli zasobu;
- mapuje wyłącznie znane błędy AniShift/OSError;
- publikuje postęp przez observer;
- nie decyduje, który następny task uruchomić;
- nie czyta `UserSettings`.

### 13.2. Migracja `pipeline/runner.py`

Migracja odbywa się addytywnie:

1. obecny `run_pipeline` pozostaje dla starego REPL;
2. helpery pojedynczych operacji stają się handlerami bez zmiany zachowania;
3. testy runnera przepinają kontrakty na handlery;
4. po parytecie TUI `run_pipeline` staje się cienkim legacy adapterem;
5. adapter jest usuwany dopiero w kroku 16.

Nie przenosić jednocześnie całego 1500-liniowego pliku. Każdy wycięty fragment ma
najpierw test handlera i pozostawia delegację w starym miejscu.

Podział commitów jest obowiązkowy:

- **10A extraction/subtitles/translation:** probe, extraction, subtitle pipeline i
  translation; legacy runner deleguje te pojedyncze operacje;
- **10B TTS/audio:** `llm_runtime.py`, `narration.py`, `tts_runtime.py` oraz recovery
  są rozdzielone na domenowe wywołania handlerów bez zmiany wyniku;
- **10C composition/publish:** `composition_runtime.py` i `compose_only.py` delegują
  do nowego kontraktu kontenera/publishera, ale pozostają jako adaptery do kroku 16.

Po każdym podkroku pełne testy pozostają zielone. Nie ma commita zawierającego
jednocześnie migrację wszystkich siedmiu rodzin.

### 13.3. Jednoznaczna integracja LLM i TTS

- jeden `TtsService` i jeden jego event-loop thread istnieje przez cały run;
- group-level `TtsTaskHandler` jest uruchamiany w dedykowanej puli `tts-dispatch`,
  nigdy w wątku koordynatora i nigdy przez `asyncio.run()`;
- handler blokująco oczekuje na future zwrócone przez istniejący runtime TTS, a
  coordinator nadal odbiera zakończenie handlera przez `FIRST_COMPLETED`;
- request-level concurrency, retry i provider circuit breaker pozostają w
  `services/tts/TtsScheduler`; graph scheduler zna tylko `tts_group_jobs`;
- translation/LLM fallback wybiera domenowa fasada dokładnie raz; scheduler tylko
  mapuje ostateczny wynik i nie ponawia requestu;
- callback provider retry/fallback staje się `WorkerNotification`, a dopiero
  coordinator nadaje mu run ID i sequence;
- TTS zachowuje nakładanie audio N z syntezą N+1 i zamyka event loop dokładnie raz
  przy zamknięciu runu.

### 13.4. Testy kroku 10

- contract test każdego handlera z fake serwisem;
- obecne testy pipeline streaming i recovery bez zmian semantycznych;
- porównanie legacy `PipelineReport` z nowym `RunResult` dla reprezentatywnego runu;
- dwie grupy używają tego samego TTS event-loop threadu i nie mnożą provider cap;
- audio N nakłada się z TTS N+1, a po zamknięciu nie zostaje nazwany wątek TTS;
- cancel kończy kontrolowany fake subprocess extraction/audio/composition;
- każde wywołanie sieciowe ma skończony timeout;
- żadnego realnego API w testach domyślnych.

**Weryfikacja kroku 10:**

```bash
uv run pytest tests/application/test_handlers.py tests/pipeline -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** legacy i nowe handlery zwracają równoważne produkty/statusy, provider
retry nie jest wykonywany drugi raz przez graph scheduler, a po shutdownie nie
pozostaje subprocess ani event-loop TTS.

---

## 14. Krok 11 — `workspace/temp` i pełny lifecycle

To jedna atomowa zmiana kontraktu, nie stopniowa zgodność `tmp`/`temp`.

### 14.1. `anishift/config/workspace.py`

```diff
- DEFAULT_SUBDIRS = ("tmp", "output")
+ DEFAULT_SUBDIRS = ("temp",)
```

Nowe helpery:

```python
def run_temp_dir(root: Path, run_id: str) -> Path: ...
def group_temp_dir(root: Path, run_id: str, group_id: str) -> Path: ...
def cleanup_orphaned_temp(root: Path, *, active_run_ids: Collection[str]) -> tuple[Path, ...]: ...
```

Każda ścieżka przechodzi `safe_path`/`safe_fs`; cleanup nigdy nie przyjmuje rootu
workspace jako celu rekursywnego. Active run posiada marker/lock z PID i run ID.
Osierocony katalog jest usuwany tylko po potwierdzeniu, że właściciel nie działa.

### 14.2. Mechaniczne zmiany

Zamienić folder kontraktowy w:

- `pipeline/runner.py`;
- `pipeline/tts_runtime.py`;
- `pipeline/composition_runtime.py`;
- `pipeline/compose_only.py` do czasu usunięcia;
- `services/tts/artifacts.py` i komunikatach błędów;
- wszystkich testach, fake runtime'ach, `AGENTS.md`, `CLAUDE.md` i docs runtime.

Nie zmieniać suffixów atomowych `*.tmp`, `TemporaryDirectory` ani przypadkowych
zmiennych `tmp_path` — nie dotyczą nazwy katalogu workspace.

### 14.3. Lifecycle

`RunSession` z kroku 8 otrzymuje teraz `workspace/temp/<run_id>` jako `run_root`.
Wyłącznie on tworzy group scope i w swoim jednym `__exit__` usuwa cały run scope po
sukcesie, błędzie i cancel. Scheduler nie tworzy ani nie usuwa katalogów.
`AppService` w następnym kroku tylko otworzy `RunSession` context manager. Trwałe
produkty są wcześniej atomowo opublikowane obok źródła. Brak cleanupu trafia do
wyniku sesji jako ostrzeżenie i jest ponawiany przy kolejnym starcie.

**Weryfikacja kroku 11:**

```bash
uv run pytest tests/workspace/test_temp_lifecycle.py tests/application/test_sessions.py tests/pipeline tests/services/tts -v
rg 'workspace[/\\](tmp|output)|DEFAULT_SUBDIRS.*(tmp|output)' anishift tests
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

Polecenie `rg` ma zwrócić kod 1 i pusty wynik; ten wzorzec nie obejmuje `tmp_path`,
`TemporaryDirectory` ani suffixu `*.tmp`. Osobny test asertywnie wymaga
`DEFAULT_SUBDIRS == ("temp",)`.

**Oczekiwane:** po sukcesie, awarii, cancel i późnym wyniku istnieje wyłącznie
opublikowany produkt obok źródła; `workspace/temp` nie zawiera zakończonego runu.

---

## 15. Krok 12 — AppService i fake E2E backendu

### 15.1. `anishift/application/service.py`

```python
class AppService:
    def discover(self) -> InspectedWorkspace: ...
    def register_external_subtitle(
        self,
        group_id: str,
        path: Path,
        declared_language: str | None,
    ) -> InspectedSourceGroup: ...
    def register_external_audio(
        self,
        group_id: str,
        path: Path,
        role: ExternalAudioRole,
    ) -> InspectedSourceGroup: ...
    def list_presets(self) -> tuple[AutoPreset, ...]: ...
    def get_preset(self, preset_id: str) -> AutoPreset: ...
    def save_preset(self, draft: AutoPresetDraft) -> AutoPreset: ...
    def plan_auto(
        self,
        group_ids: Sequence[str],
        preset: AutoPreset | AutoPresetDraft,
    ) -> ExecutionPlan: ...
    def plan_manual(self, intents: Sequence[GroupIntent]) -> ExecutionPlan: ...
    def execute(self, plan: ExecutionPlan, sink: RunEventSink) -> RunResult: ...
    def cancel(self, run_id: str) -> bool: ...
    def settings_catalog(self) -> tuple[SettingSpec, ...]: ...
    def settings_snapshot(self) -> SettingsDraft: ...
    def save_settings(self, draft: SettingsDraft) -> UserSettings: ...
    def doctor(self) -> tuple[CheckResult, ...]: ...
    def setup(self, *, force: bool = False) -> tuple[ResourceResult, ...]: ...
```

`execute()` przyjmuje gotowy immutable plan; nie planuje ponownie. Aktywny run ma
snapshot ustawień. `save_settings()` nie wpływa na run w toku. Jednocześnie może
istnieć tylko jeden run tej lokalnej aplikacji; drugi start zwraca typowany konflikt.
`plan_auto()` przyjmuje także niezapisany draft, dlatego `Preview once` nie zapisuje
ustawień. `save_preset()` jest jedyną drogą trwałego zapisu presetu. `discover()`
obejmuje discovery + inspection i dopiero jego wynik może trafić do Workspace.
`execute()` otwiera dokładnie jeden `RunSession`, przekazuje schedulerowi run scope
i zawsze zamyka sesję wokół wykonania oraz publikacji.

### 15.2. `anishift/bootstrap.py`

Istnieje jeden composition root: `bootstrap(create_dirs=False) -> AppContext`
tworzy lekki kontekst, a `create_app_service(context) -> AppService` jest jedynym
lazy builderem konkretnych usług używanym przez TUI i CLI. `AppContext` nie zawiera
`app_service`, więc nie powstaje cykl. Ciężkie provider SDK pozostają lazy;
`bootstrap(create_dirs=False)` nadal wspiera doctor/import smoke.

### 15.3. `tests/application/fakes.py`

Fake implementują publiczne Protocols i potrafią: sukces, opóźnienie,
transient/fatal/corrupt, kontrolowany progress, active/max concurrency i zapis
wywołań. Nie patchują prywatnych helperów.

Testy używają **realnego `AppService`, planera, schedulera i `RunSession`**, a fake
podmieniają wyłącznie granice serwisów/handlerów. Nie tworzyć `FakeAppService` dla
backendowego E2E, bo ominąłby najważniejszą integrację.

### 15.4. `tests/application/test_service.py`

Pełny fake flow bez UI:

1. discover trzech grup;
2. plan auto na dwóch zaznaczonych;
3. preview nadpisania;
4. execute ze streaming events;
5. jedna grupa sukces, druga partial;
6. temp pusty, produkty opublikowane;
7. settings zmienione w trakcie nie wpływają na snapshot.

**Weryfikacja kroku 12:**

```bash
uv run pytest tests/application -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** realna fasada przechodzi discovery → inspection → plan → execute →
publish na fake handlerach, `Preview once` nie zapisuje presetu, a drugi run jest
odrzucony bez utworzenia katalogu. Backend jest testowalny bez TUI, ale etap nie
jest jeszcze ukończony.

---

## 16. Krok 13 — produkcyjny szkielet Textual i command bar

### 16.1. Usunięcie spike'a

Skasować `scripts/spikes/textual_stage9.py` i odpowiadający test. Wiedza ze spike'a
zostaje w docelowych komponentach, ale żaden lokalny fake typ nie trafia do
produkcji.

### 16.2. `anishift/tui/app.py`

`AniShiftApp(App[None])` dostaje `AppService` przez konstruktor. Nie uruchamia
bootstrapu w ekranach. Instaluje ekrany przez jawne ID i trzyma tylko `SessionState`.

W tym samym kroku utworzyć `tui/__init__.py`, `messages.py`, `state.py`,
`theme.tcss`, `AGENTS.md`, `CLAUDE.md` oraz wszystkie osiem plików screens jako
minimalne, importowalne placeholdery. Placeholder zawiera tytuł i Back, ale nie
udaje gotowego use case'u. Kroki 14–15 zastępują je produkcyjnymi ekranami. Dzięki
temu poniższe `SCREENS` nie importuje klas, które jeszcze nie istnieją.

```python
SCREENS = {
    "workspace": WorkspaceScreen,
    "auto": AutoScreen,
    "manual": ManualScreen,
    "settings": SettingsScreen,
    "preview": PreviewScreen,
    "execution": ExecutionScreen,
    "results": ResultsScreen,
    "tools": ToolsScreen,
}
```

Główny layout posiada content, stały `CommandBar` i status footer. Przy terminalu
poniżej 100×30 content zastępuje komunikat, ale command bar/help nadal umożliwia
bezpieczne wyjście.

`AniShiftApp` instaluje timer UI (docelowo 50–100 ms), który wywołuje wyłącznie
`EventBuffer.drain()` i mapuje wynik na typowane Textual `Message`. Worker
`thread=True` tylko uruchamia blokujące `AppService.execute()`; nigdy sam nie
opróżnia bufora ani nie dotyka widgetu. Po zamknięciu Execution timer/subskrypcja
jest wyłączana, a event z obcego `run_id` lub starej generacji jest ignorowany.

### 16.3. `anishift/tui/commands.py`

```python
class UiCommand(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"
    SETTINGS = "settings"
    REFRESH = "refresh"
    DOCTOR = "doctor"
    SETUP = "setup"
    HELP = "help"


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    command: UiCommand | None
    error: str | None = None
```

Parser wykonuje `strip().casefold()`, nie przyjmuje argumentów pipeline'u i zwraca
sugestie z `difflib.get_close_matches`. Pusty tekst ma `command=None`, `error=None`.

### 16.4. `anishift/tui/widgets/command_bar.py`

- `Input` ma prompt `❯` renderowany jako stały element, nie część wartości;
- command bar jest dockowany na dole nad footerem;
- submit publikuje typowaną wiadomość `CommandSubmitted`;
- nie wykonuje use case'u sam;
- status footer pokazuje workspace, preset/mode, run state i elapsed;
- branch Gita, koszt modelu i dane Codexa nie należą do AniShift.

### 16.5. Testy kroku 13

Pilot pokrywa focus, każdy command, sugestię, pusty Enter, mały terminal,
podwójny submit i stałą obecność `❯` po zmianie ekranu. Na każdym głównym ekranie
oraz poniżej 100×30 asertuje także widoczny status footer. Zmiana workspace,
preset/mode i run state aktualizuje właściwe segmenty; elapsed rośnie tylko podczas
runu. Footer nie zawiera brancha Gita, kosztu modelu ani danych deweloperskich.

**Weryfikacja kroku 13:**

```bash
uv run pytest tests/tui/test_app.py tests/tui/test_command_bar.py -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** każdy route importuje się po tym commicie, `❯` pozostaje widoczne
na wszystkich placeholderach i przy małym terminalu, a pusty/nieznany command nie
wywołuje metody `AppService`.

---

## 17. Krok 14 — Workspace, Auto, Manual i Preview

Pliki tego inkrementu są jednoznaczne: `screens/workspace.py` +
`widgets/group_table.py`, `screens/auto.py`, `screens/manual.py` +
`widgets/intent_form.py`, `screens/preview.py` + `widgets/plan_view.py` oraz ich
odpowiednie testy. Nie dodawać wspólnej abstrakcyjnej klasy ekranu; współdzielony
jest wyłącznie `SessionState` i małe widgety z faktycznie wspólnym kontraktem.

### 17.1. Workspace

`WorkspaceScreen` wywołuje wyłącznie `AppService.discover()` i otrzymuje już
`InspectedWorkspace`. `GroupTable` ma jeden wiersz per `InspectedSourceGroup`,
stabilne row keys, checkbox zaznaczenia, sort/filter, zwalidowane sidecary i tracki
embedded. Refresh zachowuje selection dla nadal istniejących group IDs i nie
uruchamia planu.

Discovery/inspection zawsze działa w `Worker(thread=True)`, bo może uruchamiać
ffprobe/FFmpeg. Ekran nadaje żądaniu monotoniczny `inspection_generation`; wynik
starszego refreshu lub zamkniętego ekranu jest ignorowany. Refresh podczas aktywnej
inspekcji anuluje poprzedni token, nie dotyka widgetów z wątku i nie blokuje inputu.

### 17.2. Auto

`AutoScreen` otrzymuje zaznaczone group IDs i jeden draft `AutoPreset`. Osobne
akcje:

- `Preview once` — tworzy plan z draftu bez zapisu;
- `Save preset` — jawnie zapisuje preset;
- `Reset` — wraca do zapisanego presetu;
- `Back` — zachowuje draft w sesji, niczego nie zapisuje.

Nie ma override per grupa. Grupa niewykonalna pokazuje `PlanProblem`; user może
wrócić do Workspace i ją odznaczyć albo przejść do Manual.

### 17.3. Manual

`ManualScreen` przechowuje `dict[group_id, GroupIntentDraft]`. Zmiana jednej grupy
nie mutuje drugiej. `Copy to selected` kopiuje wartości do nowych draftów. Pola są
aktywowane przez czyste selektory wynikające z katalogu/intencji, ale finalną
walidację zawsze wykonuje planner.

Wybór dowolnego pliku zewnętrznego nie dopisuje ścieżki bezpośrednio do draftu.
Ekran najpierw wywołuje `register_external_subtitle()` albo
`register_external_audio()`, pokazuje błąd walidacji, a dopiero zwrócone artifact ID
może trafić do `GroupIntentDraft`. To samo dotyczy jawnego języka i roli audio.
Obie rejestracje również działają w `Worker(thread=True)` z tokenem/generation gate;
spóźniony wynik nie zmienia innej grupy ani draftu po Back.

### 17.4. Preview

`PreviewScreen` pokazuje źródła, pominięte alternatywy, operacje, produkty,
nadpisania, provider/fallback/concurrency, network/paid i blocking problems.
Przycisk Start istnieje tylko dla `can_execute`; koszt/nadpisanie wymaga jawnego
modala. Podwójne aktywowanie jest blokowane session run state.

### 17.5. Testy kroku 14

- Workspace 20 grup, sort/filter/select/refresh;
- auto domyślnie wszystkie, następnie dwie zaznaczone;
- jeden preset bez per-group exception;
- trzy manual drafts z różnymi wejściami i produktami;
- copy nie współdzieli mutable state;
- preview wszystkich typów informacji i blocking start;
- command bar nadal działa na każdym ekranie.
- opóźniona inspection i walidacja external audio nie blokują focusu/inputu;
- spóźniony refresh/external result jest ignorowany po nowej generacji.

**Weryfikacja kroku 14:**

```bash
uv run pytest tests/tui/test_workspace.py tests/tui/test_auto.py tests/tui/test_manual.py tests/tui/test_preview.py -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** trzy grupy zachowują niezależne drafty, arbitrary external file
zawsze przechodzi inspection, a Preview pokazuje dokładnie te taski i produkty,
które potem otrzyma `execute()`.

---

## 18. Krok 15 — Settings, Execution, Results i Tools

Pliki tego inkrementu są jednoznaczne: `screens/settings.py` +
`widgets/setting_field.py`, `screens/execution.py` + `widgets/progress_table.py`,
`screens/results.py` oraz `screens/tools.py` wraz z testami o tych samych nazwach.
Placeholder z kroku 13 jest zastępowany w całości; nie zostawiać równoległej klasy.

### 18.1. Settings

Ekran buduje pola wyłącznie z `SettingSpec`. Używa kopii `SettingsDraft`; `Save`
wywołuje API, `Cancel` porzuca draft. Zmiana engine/model/voice przebudowuje aktywne
pola. Sekret pokazuje tylko configured/missing. Niedostępny silnik pozostaje
widoczny z powodem i akcją Tools.

### 18.2. Execution

Textual worker z `thread=True` wywołuje blokujące `AppService.execute()` poza pętlą
UI. `RunEvent` jest mapowany na jeden wiersz per grupa; szczegóły tasków są
rozwijane. Progress procentowy jest
coalesced do maksymalnie 10 renderów/s per task, lecz eventy terminalne są
renderowane w następnym ticku timera UI bez celowego throttle. Zamknięty ekran
zatrzymuje swój timer/subskrypcję. Cancel pozostaje
aktywny do zakończenia shutdownu i jest idempotentny.

### 18.3. Results

Pokazuje `succeeded/partial/failed/cancelled`, utworzone produkty, zachowane stare
produkty, bezpieczny błąd i akcję przejścia do manual dla grupy. Filtr `done`
obejmuje terminalne stany, nie jest stanem API.

### 18.4. Tools

`doctor` i `setup` biegną w workerze bez blokowania UI. Setup wymaga jawnej akcji,
wynik jest listą zasobów. Command bar `doctor`/`setup` nawiguje do tego samego
ekranu i nie posiada osobnej implementacji.

### 18.5. Testy kroku 15

- Settings Save/Cancel i dynamiczne provider fields;
- sekrety bez wartości;
- progress podczas aktywnego input/focus;
- retry/fallback i partial result;
- cancel podczas opóźnionego fake oraz idempotentny drugi cancel;
- stary event nie zmienia nowego runu;
- odłączenie ekranu nie zostawia UI tasków;
- Tools przez przycisk i command bar wywołuje te same metody fake API.

**Weryfikacja kroku 15:**

```bash
uv run pytest tests/tui/test_settings.py tests/tui/test_execution.py tests/tui/test_results.py tests/tui/test_tools.py -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** input i focus odpowiadają podczas pracy, każdy event terminalny
pojawia się dokładnie raz, cancel nie uruchamia nowej pracy, a Results odzwierciedla
`RunResult` bez własnej interpretacji backendu.

---

## 19. Krok 16 — entrypoint TUI, cienkie CLI i usunięcie całego legacy pipeline'u

### 19.1. `anishift/cli/main.py`

Docelowe komendy:

```text
anishift                       # Textual TUI
anishift doctor                # bez importu/startowania Textual App
anishift setup [--force]       # bez startowania TUI
anishift run --preset NAME     # nieinteraktywny auto preset
```

`run` zwraca exit code `0` przy pełnym sukcesie, kod niezerowy przy partial/failure
albo cancel i drukuje stabilny tekstowy raport. Nie przyjmuje manual intent flags.

### 19.2. Automatyczna bramka parytetu przed usunięciem

Przed kasowaniem uruchomić ten sam hermetyczny zestaw wejść przez legacy
`run_pipeline`/`compose_only` i przez `AppService`. Porównać status per grupa,
nazwy/rodzaje produktów, wybrane tracki, liczbę wywołań providerów i strukturę
kontenerów; nie porównywać timestampów ani kolejności logów. Dopiero zielony test
`tests/application/test_legacy_parity.py` pozwala wykonać usunięcia. Test zostaje
usunięty razem z legacy kodem w tym samym commicie, ponieważ nie ma już drugiej
implementacji do porównania; odpowiadające scenariusze pozostają w service/E2E.

### 19.3. Jednoznaczne usunięcia i przeniesienia

Po automatycznym teście parytetu usunąć:

- `cli/shell.py`;
- `cli/commands.py`;
- `cli/completer.py`;
- `cli/pipeline_ui.py`;
- `cli/settings_panel.py`;
- `cli/banner.py`;
- `cli/tts_settings.py`;
- `pipeline/__init__.py`, `AGENTS.md`, `CLAUDE.md`, `runner.py`, `compose_only.py`,
  `composition_runtime.py`, `llm_queue.py`, `llm_runtime.py`, `narration.py`,
  `recovery.py`, `tts_queue.py`, `tts_runtime.py` i `types.py` — cały katalog;
- `tests/cli/test_banner.py`, `test_commands.py`, `test_completer.py`,
  `test_compose_command.py`, `test_pipeline_ui.py`, `test_settings_panel.py` oraz
  `test_tts_settings.py`;
- cały `tests/pipeline/` po przeniesieniu każdego zachowanego scenariusza do
  `tests/application/`, `tests/services/` albo `tests/e2e/`;
- zależność przez `uv remove prompt-toolkit`.

Nie usuwać `doctor`, `setup`, Typera, logger boundary ani testów ich kontraktów.
Nie zostawiać `pipeline/types.py`: `FileOutcome` i `PipelineReport` znikają, a
potrzebne modele są już w `application/planning.py` i `application/results.py`.
Docelowo katalog `anishift/pipeline/` oraz `tests/pipeline/` nie istnieją.

### 19.4. `run_anishift.bat`

Nie wymaga specjalnej logiki: nadal deleguje argumenty do `uv run anishift %*`.
Bez argumentów nowy entrypoint otwiera TUI.

### 19.5. Testy kroku 16

- default entrypoint tworzy TUI;
- doctor/setup/run nie uruchamiają `Textual.App.run`;
- preset missing/invalid ma czytelny błąd i non-zero exit;
- CLI run korzysta z tego samego planera/schedulera co TUI;
- `rg 'prompt_toolkit|SlashCompleter|run_pipeline_command|anishift\.pipeline' anishift tests` jest pusty;
- `Test-Path anishift/pipeline` i `Test-Path tests/pipeline` zwracają `False`;
- schema v2 po tym kroku nie zapisuje już deprecated `output_variant`.

**Weryfikacja kroku 16:**

```bash
uv run pytest tests/cli tests/tui tests/application -v
uv run anishift doctor
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** istnieje jedna ścieżka wykonania przez `AppService`, cały stary
pakiet pipeline jest nieobecny, a `doctor`, `setup`, TUI i nieinteraktywny preset
korzystają z jednego composition root.

---

## 20. Krok 17 — hermetyczne E2E i test obciążeniowy

### 20.1. `tests/e2e/conftest.py`

Fixture tworzy mały deterministyczny film, audio i ASS/SRT przez prawdziwy FFmpeg,
a MKV przez MKVToolNix. Fake translation/TTS działają na publicznych kontraktach.
Test nie korzysta z danych `mm_avh` ani płatnej sieci.

### 20.2. `tests/e2e/test_stage9_pipeline.py`

Obowiązkowa macierz:

1. MKV embedded → wszystkie sidecary;
2. MKV embedded → lektor → MKV;
3. MKV embedded → lektor + displayed burn → MP4;
4. MP4 + exact-stem ASS → tłumaczenie → MKV i MP4;
5. gotowe `.pl`, manual → TTS bez translation;
6. gotowe audio, manual → composition bez TTS;
7. source subtitles → burn bez translation;
8. same sidecary bez composition;
9. dwa odcinki streaming bez bariery fazy.

Każdy wynik jest sprawdzany przez ffprobe/mkvmerge: tracki, language, codec i
duration. Burn jest dowodzony osobno: fixture umieszcza napis w znanym przedziale,
FFmpeg wyciąga klatkę z tego przedziału oraz klatkę kontrolną, a test porównuje
deterministyczny region obrazu/hash. Brak subtitle tracku sam nie jest dowodem burn.
Sam `Path.exists()` nie wystarcza. `workspace/temp` musi być pusty.

### 20.3. `.github/workflows/ci.yml`

Osobny job E2E instaluje/pobiera kontrolowane wersje FFmpeg i MKVToolNix, a potem
uruchamia marker `e2e`. Brak binarek jest błędem joba, nie stałym skipem.
Płatne/network testy pozostają opt-in.

Zwykły job i lokalne pełne `uv run pytest` wykluczają marker `e2e` przez domyślną
konfigurację pytest; test może lokalnie skipnąć wyłącznie przy braku binarek.
Dedykowany job najpierw wykonuje obowiązkowy preflight narzędzi, więc ten sam brak
kończy job błędem, a następnie uruchamia `uv run pytest -m e2e`. CI nie uruchamia
ciężkiego markera dwa razy.

### 20.4. `tests/load/test_stage9_scheduler.py`

Fake run co najmniej 100 grup sprawdza:

- maksymalne active count każdego zasobu;
- bounded queue size;
- ready_first i strict_natural przy odwrotnej kolejności zakończeń;
- brak deadlocku, tasków i katalogów po cancel/failure;
- peak active futures i peak submitted-not-done;
- maksymalny rozmiar `EventBuffer` po coalescingu;
- brak aktywnych runów, nazwanych worker threads i katalogów temp po wyniku.

`tracemalloc` może być wypisane diagnostycznie, ale nie jest bramką CI; alokator
Pythona oraz procesy FFmpeg czynią prosty pomiar before/after kruchym.

### 20.5. Automatyczne E2E TUI

`tests/tui/test_flow.py` przez Pilot używa realnego `AppService`, planera,
schedulera i `RunSession`; fake są tylko serwisy/handlery graniczne. Przechodzi bez
ręcznego klikania:

- Workspace → Auto → Preview → Execution → Results;
- Workspace → Manual dla trzech grup → Preview → cancel → Results;
- Settings edit → Cancel, potem edit → Save;
- command bar `❯` na każdym ekranie;
- status footer na każdym ekranie i w małym terminalu, wraz z aktualizacją
  workspace/preset/run/elapsed;
- resize 100×30 i poniżej minimum;
- podwójny Enter/click nie uruchamia dwóch runów.

**Weryfikacja kroku 17:**

```bash
uv run pytest -m e2e -v
uv run pytest tests/tui/test_flow.py tests/load/test_stage9_scheduler.py -v
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Oczekiwane:** real-media job nie może przejść bez binarek, burn zmienia wskazany
region klatki, 100 grup nie przekracza żadnego limitu, a pełny Pilot przechodzi od
TUI do realnej fasady i z powrotem do Results.

---

## 21. Krok 18 — dokumentacja i domknięcie

### 21.1. Aktualizacje

- `README.md` — uruchomienie TUI, CLI preset, workspace i produkty;
- root `AGENTS.md`/`CLAUDE.md` — tylko `workspace/temp`, bez `output`;
- `anishift/application/AGENTS.md` — granice planner/scheduler/handlers;
- `anishift/tui/AGENTS.md` — presentation-only, command bar, Pilot;
- root `AGENTS.md` — usunąć mapowanie nieistniejącego `pipeline/`; właścicielem
  wykonania jest `application/`;
- `anishift/config/AGENTS.md` — jawny Save, presets, schema v2;
- `docs/plans/_index.md` — Etap 9 jako wykonany dopiero po pełnym DoD;
- `docs/plans/plan-anishift.md` — link do wymagań i planu, bez przepisywania treści;
- issue #38 — zamknięcie dopiero po realnym smoke i zielonym CI.

### 21.2. Ostatni smoke

```bash
uv sync --frozen
uv run anishift doctor
.\run_anishift.bat doctor
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

Ręczna ocena może sprawdzić jedynie niedeterministyczne elementy płatnych providerów
i subiektywną jakość audio/wideo. Nie zastępuje Pilot E2E ani real-media E2E.
`uv run anishift run --preset default` nie jest bezwarunkowym smoke: na prawdziwym
workspace może uruchomić płatne API. Jego automatyczny odpowiednik działa na fake
providerach w testach, a manualne uruchomienie wymaga jawnie przygotowanych danych,
sekretów i potwierdzenia kosztu.

---

## 22. Kolejność commitów

Plan Etapu 7 nie narzucał commitów, ale skala Etapu 9 wymaga jawnych granic. Każdy
commit przechodzi pełne bramki i pozostawia działające repo.

| Krok | Commit |
|---:|---|
| 1 | `test(cli): validate Textual workflow spike` |
| 2 | `feat(pipeline): add artifact and intent contracts` |
| 3 | `feat(pipeline): group workspace artifacts deterministically` |
| 4 | `feat(extraction): unify MKV and MP4 media probing` |
| 5 | `feat(pipeline): plan product dependency graphs` |
| 6 | `feat(composition): support independent container products` |
| 7 | `feat(config): add typed settings catalog and presets` |
| 8 | `feat(pipeline): add run events cancellation and results` |
| 9 | `feat(pipeline): schedule ready tasks asynchronously` |
| 10A | `refactor(extraction): adapt subtitle and translation tasks` |
| 10B | `refactor(tts): adapt narration and audio tasks` |
| 10C | `refactor(composition): adapt container and publish tasks` |
| 11 | `refactor(repo): move runtime scratch data to temp` |
| 12 | `feat(pipeline): expose shared product workflows` |
| 13 | `feat(cli): add Textual shell and command bar` |
| 14 | `feat(cli): add product planning screens` |
| 15 | `feat(cli): add settings execution and results screens` |
| 16 | `refactor(pipeline): remove the legacy execution path` |
| 17 | `test(pipeline): cover stage 9 end-to-end workflows` |
| 18 | `docs(repo): document stage 9 product workflows` |

Scope `cli` obejmuje TUI, dopóki hook nie otrzyma osobnego zatwierdzonego scope.
Nie zmieniać hooka tylko dla nazwy `tui` bez zgody usera.

## 23. Macierz wymagań do kroków

| Wymaganie | Kroki |
|---|---|
| artefakty, grupy, nazwy i konflikty | 2–3 |
| inspection, arbitrary external subtitle/audio i język | 4 |
| MKV/MP4, neutralne tracki i MP4 extraction | 4 |
| auto/manual, produkty i planner | 2, 5 |
| oba kontenery i jawny burn | 6 |
| katalog ustawień i presety | 7 |
| async, kolejki, limity, retry/fallback | 8–10 |
| `workspace/temp`, cleanup i atomowość | 6, 11 |
| wspólne application API | 12 |
| Textual TUI i command bar `❯` | 1, 13–15 |
| cienkie CLI i usunięcie REPL | 16 |
| usunięcie całego `pipeline/` po parytecie | 16 |
| Pilot bez ręcznego klikania | 1, 13–17 |
| realne FFmpeg/MKVToolNix E2E | 17 |
| load 100 grup | 17 |
| docs i zamknięcie issue | 18 |

## 24. Ryzyka i mitygacje

| Ryzyko | Mitygacja | Krok |
|---|---|---:|
| Textual nie skaluje się do formularzy i 20 grup | odrzucalny spike przed produkcyjnym API | 1 |
| Powstaje drugi pipeline obok starego runnera | addytywne handlery, automatyczne porównanie legacy/new, potem usunięcie całego starego pakietu | 10, 16 |
| Dwa poziomy concurrency przekraczają limit providera | jeden właściciel limitu na raz; test active/max | 9–10 |
| Future kończy się już po cancel | token generacji blokuje późny commit, subprocess watcher i test shutdown | 8–10 |
| `strict_natural` zakleszcza późniejsze grupy | jawne `skip()` dla każdego stanu terminalnego | 9 |
| Auto używa starego produktu przez przypadek | planner property invariant i auto rebuild E2E | 5, 17 |
| Obcy tekst dostaje fałszywy suffix `.pl` | walidacja language + `do_not_translate` przed taskami | 5 |
| MKV i MP4 duplikują TTS/audio | DAG deduplikuje artifact producer, osobne tylko composition | 5–6 |
| Publikacja niszczy poprzedni poprawny wynik | temp sibling + validation + atomic replace | 6 |
| Cleanup usuwa obcy katalog | run/group IDs, marker aktywności i safe path guard | 11 |
| Zmiana `tmp`/`output` jest połowiczna | jeden atomowy krok z `rg` i pełnymi testami | 11 |
| TUI blokuje się podczas sync serwisu | Textual thread worker + event queue, Pilot input podczas progress | 9, 15 |
| Stare eventy psują nowy ekran/run | `run_id` + monotonic sequence + unsubscribe | 8, 15 |
| Command bar staje się ukrytym drugim CLI | tylko krótkie aliasy widocznych akcji, bez pipeline flags | 13 |
| Przyszły agent omija potwierdzenie | typowana granica command → plan preview → confirmation | 13 |
| Testy E2E stale skipują binarki | kontrolowany job CI instaluje narzędzia | 17 |
| Plan rośnie, a produkt nie działa | każdy krok ma działający inkrement i pełne bramki | wszystkie |

## 25. Definicja ukończenia

- `anishift` i `run_anishift.bat` bez argumentów otwierają Textual TUI;
- dolny command bar z dokładnym promptem `❯` jest stale widoczny, obsługuje krótkie
  odpowiedniki widocznych akcji i nie uruchamia niczego dla pustego/nieznanego inputu;
- status footer jest stale widoczny także poniżej minimalnego rozmiaru, aktualizuje
  workspace, preset/mode, run state i elapsed oraz nie pokazuje metryk deweloperskich;
- Workspace wykrywa MKV, MP4, TXT, sidecary, produkty i konflikty deterministycznie;
- auto stosuje jeden preset do zaznaczonego batcha, domyślnie wszystkich grup;
- manual posiada niezależny intent każdej grupy i pozwala wybrać tracki, produkty,
  gotowe `.pl`/`spoken.pl`, external subtitle i external audio;
- planner tworzy minimalny, acykliczny i deterministyczny DAG oraz blokuje
  niewykonalny plan przed siecią/płatną operacją;
- MKV i MP4 mogą powstać razem, współdzieląc ten sam lektor i napisy;
- composition tworzy tylko kontenery, sidecary publikuje application layer;
- ustawienia mają jeden typowany katalog, dynamiczne pola i jawny Save/Cancel;
- `translation_concurrency` działa naprawdę, a SAPI pozostaje na limicie `1`;
- scheduler strumieniuje po gotowości, respektuje limity, retry/fallback,
  ready-first/strict-natural i izoluje awarie grup;
- cancel jest idempotentny, kończy nowe admission i propaguje się do sieci,
  TTS oraz subprocessów;
- trwałe wyniki leżą obok źródła, stary poprawny produkt przeżywa nieudaną
  przebudowę, a `workspace/temp` jest sprzątnięty po sukcesie, błędzie i cancel;
- Execution pozostaje responsywny i posiada jeden stabilny wiersz per grupa;
- Results pokazuje sukces, partial, failure i cancel wraz z produktami per grupa;
- doctor, setup i `run --preset` działają bez uruchamiania TUI;
- stary REPL, slash commands, panel ustawień i `prompt_toolkit` są usunięte po parytecie;
- Pilot automatycznie pokrywa Auto, trzy plany Manual, Settings, Preview, Execution,
  Results, command bar, focus, resize, double-start i cancel;
- real-media E2E z FFmpeg/MKVToolNix i fake providerami działa w CI bez stałego skipa;
- load test 100 grup potwierdza limity, brak deadlocków, tasków i temp leaków;
- pełne bramki Ruff, format, mypy i pytest są zielone;
- issue #38 zostaje zamknięte dopiero po spełnieniu wszystkich punktów.

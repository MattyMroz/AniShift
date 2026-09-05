# PLAN 03 — tryb Ręczny: wybór odcinków, źródeł i produktów bez nowego TUI

## 0. Status dokumentu

```text
STATUS: COMMITTING — RUNTIME HITL DEFERRED BY USER
MODE: CREATE
SPEC AUTHORITY: spec.md
PREDECESSOR: PLAN 02 — Settings
BASELINE BRANCH: work/interactive-cli/02-settings
BASELINE COMMIT: b0c7f4d4f0a38d50c387d04073411b758ea56b70
TARGET BRANCH: work/interactive-cli/03-manual
FINAL COMMIT: feat(cli): add guided manual workflow
```

Plan jest gotowy po potwierdzeniu:

```text
PLAN 02 VERIFIED / COMMITTED
```

Finalny SHA PLANU 02: `b0c7f4d4f0a38d50c387d04073411b758ea56b70`.

PLAN 03 buduje jeden pionowy wycinek:

```text
Home -> Ręczny
→ discovery
→ wybór odcinków
→ globalne ustawienia jako defaults
→ opcjonalne decyzje per odcinek
→ plan_manual
→ minimalny preview
→ Start
→ ten sam Rich progress co Auto
→ wynik / błąd
→ Home
```

Nie budujemy pełnego „manual editor”.

Nie budujemy systemu ekranów.

Nie duplikujemy backendowego planera.

---

## 1. Authority

Przed zmianą wykonawca czyta:

```text
requirements.md
PLAN_01_INTERACTIVE_HOME_AUTO.md
PLAN_02_SETTINGS.md
AGENTS.md
anishift/AGENTS.md
anishift/cli/AGENTS.md
anishift/application/AGENTS.md
anishift/config/AGENTS.md
tests/AGENTS.md
```

Następnie current code po PLANIE 02:

```text
anishift/cli/interactive/app.py
anishift/cli/interactive/prompts.py
anishift/cli/interactive/progress.py
anishift/cli/interactive/settings.py
anishift/cli/run.py
anishift/application/service.py
anishift/application/intents.py
anishift/application/inspection.py
anishift/application/artifacts.py
anishift/application/selection.py
anishift/application/planner.py
anishift/application/planning.py
anishift/services/media/types.py
anishift/config/presets.py
```

Wykonawca czyta też istniejące testy:

```text
tests/application/test_intents.py
tests/application/test_planner.py
tests/application/test_service.py
```

Nie wolno projektować wizardu z pamięci dawnych ekranów Textual.

Current backend jest źródłem prawdy o legalnych kombinacjach `GroupIntent`.

---

## 2. Obowiązkowy baseline refresh

### 2.1. Warunek wejścia

Potrzebny jest dokładny:

```text
<PLAN_02_FINAL_SHA>
```

### 2.2. Kontrola Git

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline
```

Wymagane:

```text
clean
work/interactive-cli/02-settings
<PLAN_02_FINAL_SHA>
```

### 2.3. Przejrzyj diff PLANU 02

W szczególności sprawdź:

- jak `interactive/app.py` dispatchuje akcje;
- jak działa `prompts.py`;
- czy istnieje wspólny helper execute/progress z PLANU 01;
- jak pobrać current default output set;
- jakie publiczne metody AppService finalnie ustanowił PLAN 02;
- czy Settings zmienił `AutoPreset` semantics.

### 2.4. Drift dozwolony

Dozwolone lokalnie:

- inne nazwy helperów promptów;
- inny helper do renderowania safe error;
- mała zmiana signature UI-neutral execution flow;
- dodatkowy pure helper w `interactive`.

### 2.5. Drift wymagający replanu

STOP, jeśli PLAN 02:

- zmienił `GroupIntent` contract;
- zmienił `plan_manual()`;
- zmienił `InspectedWorkspace` / `InspectedSourceGroup` identity;
- zmienił `ProductIntent` semantics;
- przeniósł produkty poza default preset w sposób niezgodny z tym planem;
- pozwolił Interactive ominąć AppService;
- wprowadził globalny UI state wymagany do działania Settings.

---

## 3. Potwierdzony current state backendu

### 3.1. Discovery

`AppService.discover()` zwraca:

```text
InspectedWorkspace
    groups: tuple[InspectedSourceGroup, ...]
    warnings: tuple[InspectionWarning, ...]
```

`InspectedSourceGroup` zawiera:

```text
source
artifacts
media_catalogs
conflicts
```

`source.stem` jest dobrym user-facing identyfikatorem odcinka/grupy.

### 3.2. Artifact metadata

`Artifact` posiada między innymi:

```text
artifact_id
kind
path
state
language
subtitle_format
audio_codec
duration_us
```

User-facing lista nie musi pokazywać `artifact_id`.

### 3.3. Media tracks

`MediaCatalog` posiada:

```text
path
container
duration_us
tracks
```

`MediaTrack` posiada:

```text
track_id
kind
codec_id
language
name
is_default
is_forced
subtitle_format
```

To wystarcza do zbudowania czytelnych wyborów audio/subtitle bez nowych probe.

### 3.4. Source selection helpers

`application/selection.py` ma istniejące polityki:

```text
choose_primary_video
choose_auto_sidecar
group_is_ready
ready_group_ids
```

Interactive nie powiela algorytmów Auto.

### 3.5. GroupIntent

Manual jest reprezentowany przez dokładnie jeden `GroupIntent` per selected group.

Pola obejmują:

```text
group_id
mode
products
subtitle_source_policy
translation_action
preferred_video_artifact_id
selected_subtitle_artifact_id
selected_audio_artifact_id
selected_audio_track_id
selected_subtitle_track_id
source_subtitle_language
external_audio_role
subtitle_output_format
```

Manual selections są walidowane przez domenę i planner.

### 3.6. ProductIntent

`ProductIntent` pilnuje między innymi:

- minimum jednego produktu;
- MKV tracks tylko przy MKV;
- explicit MP4 audio tylko przy MP4;
- burn subtitles tylko przy MP4.

Interactive nie implementuje drugiej wersji tych inwariantów.

### 3.7. Planner

`AppService.plan_manual(intents)` wymaga:

```text
exactly one manual GroupIntent for every selected group
```

Planner:

- waliduje manual selections;
- wykrywa konflikty;
- tworzy `PlanProblem`;
- przy blocking problem tworzy plan bez executable tasks;
- nie wykonuje pracy.

### 3.8. External registration

AppService ma:

```text
register_external_subtitle(...)
register_external_audio(...)
```

Rejestracja:

- waliduje plik;
- aktualizuje cached inspected group;
- zachowuje backend ownership.

Interactive nie dodaje artefaktu ręcznie do tuple.

### 3.9. Progress

PLAN 01 ma już jeden realny renderer przebiegu.

Manual musi użyć dokładnie tej samej ścieżki execute/event sink/result rendering.

---

## 4. Current State / Gap

| Obszar | Stan po PLANIE 02 | Wymagany po PLANIE 03 | Akcja |
|---|---|---|---|
| Home | `Ręczny` placeholder | prawdziwy workflow | podłączyć |
| Discovery | backend działa | spinner + lista grup | użyć |
| Group choice | brak UI | checkbox list | dodać |
| Per-group defaults | default preset istnieje | manual intent defaults | zbudować thin projection |
| Subtitle choice | backend supports | warunkowy picker | dodać |
| Audio choice | backend supports | warunkowy picker | dodać |
| Products | Settings output działa | per-group override | dodać |
| Planner | plan_manual istnieje | preview/blocker | użyć |
| Execution | Auto path działa | wspólny Manual path | reuse |
| Persistence | global settings | manual overrides ephemeral | nie zapisywać |

---

## 5. Jedno pytanie PLANU 03

> Czy użytkownik może wejść w `Ręczny`, wybrać konkretne odcinki, zachować globalną
> konfigurację jako domyślną, nadpisać tylko potrzebne decyzje per odcinek, zobaczyć
> krótki plan i uruchomić istniejący backend bez powstania nowego systemu UI ani
> persistencji manualnych draftów?

Po wykonaniu:

```text
TAK
```

---

## 6. Wynik widoczny dla użytkownika

### 6.1. Start

Home:

```text
  Auto
● Ręczny
  Ustawienia
  Wyjście
```

Enter.

### 6.2. Discovery

Podczas inspection:

```text
⠹ Skanowanie plików...
```

Nie udajemy procentu.

### 6.3. Brak materiału

```text
Nie znaleziono materiału do przetworzenia.

Enter · powrót
```

### 6.4. Wybór grup

Przykład:

```text
WYBIERZ ODCINKI

● Buchigire! 01
● Buchigire! 02
● Buchigire! 03
○ Buchigire! 04
```

Domyślnie zaznaczone są wszystkie wykryte grupy, które mogą wejść do manualnego
workflow.

Grupy z oczywistym conflict/invalid state nie znikają bez śladu. Jeżeli ich nie można
bezpiecznie wybrać, są opisane krótkim powodem lub pokazane jako niedostępne zgodnie z
możliwościami Questionary.

### 6.5. Pusty wybór

```text
✗ Wybierz co najmniej jeden odcinek.
```

Wracamy do listy.

### 6.6. Tryb decyzji dla odcinka

Dla każdego wybranego group:

```text
Buchigire! 01

● Użyj ustawień domyślnych
  Dostosuj ten odcinek
  Wróć
```

Default to `Użyj ustawień domyślnych`.

Manual nie zmusza użytkownika do przejścia pięciu promptów dla każdego odcinka.

### 6.7. Dostosuj

Po `Dostosuj ten odcinek` użytkownik widzi tylko product-level decyzje:

```text
● Wynik
  Napisy źródłowe
  Audio źródłowe
  Wróć
```

Pozycje mogą być ukryte, jeśli dla konkretnego typu źródła są bez znaczenia.

### 6.8. Preview

Po zbudowaniu wszystkich intents:

```text
TRYB RĘCZNY

3 odcinki
Napisy: 3
Lektor: 2
MKV: 2
MP4: 0

● Uruchom
  Wróć do zmian
  Anuluj
```

To jest minimalny preview.

Nie wyświetlamy DAG-u tasków.

### 6.9. Execution

Po `Uruchom` znika wizard.

Rich renderer z PLANU 01 przejmuje terminal.

### 6.10. Koniec

Sukces/błąd używa tych samych surfaces co Auto.

---

## 7. Zachowania poza zakresem

PLAN 03 nie implementuje:

- trwałych draftów Manual;
- zapamiętywania manual selection per episode;
- historii manual runs;
- wizardu tworzenia presetów;
- edycji globalnego modelu/TTS w Manual;
- technical settings per episode;
- temp/top-p/retry/concurrency per episode;
- custom FFmpeg args;
- drag&drop;
- file picker GUI;
- playlisty;
- download anime;
- cover art;
- Textual;
- mouse-first UI;
- równoległego edytowania dwóch grup;
- pełnego tree view;
- szczegółowego task DAG preview.

---

## 8. Technical Design

### D03-01 — manual overrides są ephemeral

Manual state żyje wyłącznie w jednej sesji funkcji:

```text
interactive/manual.py
```

Nie zapisuje się do:

```text
settings.json
presets.json
localStorage
nowego manual.json
```

### D03-02 — global settings są defaults

Manual nie ma własnego modelu konfiguracji LLM/TTS.

`ExecutionPlan.settings` nadal powstaje z current global `UserSettings` przez AppService.

### D03-03 — default workflow pochodzi z default Auto preset

Dla selected group bazowy manual intent kopiuje z default preset:

```text
products
subtitle_source_policy
translation_action
source_subtitle_language
subtitle_output_format
```

ale ustawia:

```text
mode = MANUAL
```

Nie używać `apply_preset()`, jeśli zwraca `RunMode.AUTO`.

Utworzyć mały pure helper projekcji w `manual.py` albo istniejącej application boundary,
ale tylko jeśli nie ma już takiego helpera.

### D03-04 — „Użyj ustawień domyślnych” nadal tworzy Manual intent

Nie wywoływać `plan_auto` dla części grup i `plan_manual` dla innych.

Cały run manual używa:

```text
plan_manual()
```

Każdy selected group ma `RunMode.MANUAL`.

### D03-05 — ask only when meaningful

Wizard nie odpytuje bezwarunkowo o każdą możliwą właściwość.

Przykłady:

- jeden usable video -> nie pytaj o video;
- jeden sensowny subtitle source i default auto -> nie pytaj, dopóki user nie wybrał `Dostosuj`;
- brak productu wymagającego audio -> nie pytaj o audio;
- brak MKV/MP4 -> nie pytaj o container details;
- technical settings -> nigdy.

### D03-06 — products first w customizacji

W `Dostosuj` per group najpierw wybierz `Wynik`.

Dopiero potem wiadomo, czy source subtitle/audio decyzje są potrzebne.

### D03-07 — source choice jest projekcją inspected data

Interactive może formatować `Artifact` i `MediaTrack` jako user choices.

Nie zmienia source selection policy backendu.

### D03-08 — IDs pozostają value, nie label

Questionary choice ma:

```text
user-facing title
backend value = artifact_id / track_id / enum
```

Nie parsować labela z powrotem na ID.

### D03-09 — absolute paths nie dominują UI

W listach pokazujemy przede wszystkim:

```text
filename
language
track id
track name
codec
```

Pełną ścieżkę tylko przy external file input/error, gdy jest potrzebna.

### D03-10 — existing planner jest finalnym walidatorem

Interactive nie próbuje dowieść, że combination jest executable.

Po zbudowaniu intents:

```text
service.plan_manual(intents)
```

jest authority.

### D03-11 — blocking plan nigdy nie wykonuje się

Jeżeli:

```text
plan.can_execute == false
```

nie wołamy `execute`.

### D03-12 — blocked plan daje drogę powrotu

Pokaż concise blockers per group i:

```text
● Wróć do zmian
  Anuluj
```

### D03-13 — preview jest minimalny

Pokazujemy:

- liczbę grup;
- count requested public products;
- warnings/blockers;
- Start/Back.

Nie pokazujemy task IDs, resource keys ani całego artifact graph.

### D03-14 — execution path jest współdzielony

Manual po `ExecutionPlan` używa tej samej funkcji/komponentu wykonującego plan co Auto.

Jeżeli PLAN 01 stworzył tylko `run_auto()` bez reusable `execute_plan()`, PLAN 03 może
wyciągnąć najmniejszy UI-neutral common helper z istniejącego kodu.

Nie duplikować event sink/progress/error handling.

### D03-15 — external file registration idzie przez AppService

Nie tworzyć `Artifact` w Interactive.

### D03-16 — no second state store

Nie tworzyć:

```text
ManualStore
SessionState
Zustand-like store
state.json
```

Zwykłe lokalne dataclass/dict/list są wystarczające.

---

## 9. Ownership po PLANIE 03

### 9.1. Navigation

Owner:

```text
interactive/app.py
```

Tylko dispatchuje `Ręczny`.

### 9.2. Manual wizard

Owner:

```text
interactive/manual.py
```

Odpowiada za:

- discovery presentation;
- group select;
- local draft intents;
- per-group questions;
- preview;
- call `plan_manual`;
- przekazanie planu do wspólnego executor flow.

### 9.3. Prompt primitives

Owner:

```text
interactive/prompts.py
```

### 9.4. Global settings

Owner pozostaje config/AppService.

### 9.5. Input metadata

Owner pozostaje:

```text
application/inspection.py
services/media/types.py
```

### 9.6. Intent validity

Owner:

```text
application/intents.py
application/planner.py
```

### 9.7. Run execution

Owner:

```text
AppService.execute
cli/run.py / reusable run helper from PLAN 01
interactive/progress.py
```

---

## 10. Twarde inwarianty

### I03-001

Nie zapisuj manual draftów.

### I03-002

Nie modyfikuj globalnych Settings podczas manual wizardu.

### I03-003

Nie modyfikuj default preset przez per-group choices.

### I03-004

Każdy selected group dostaje dokładnie jeden `GroupIntent`.

### I03-005

Każdy intent ma `RunMode.MANUAL`.

### I03-006

Nie mieszaj `plan_auto` i `plan_manual` w jednym runie.

### I03-007

Nie wykonuj blocking planu.

### I03-008

Nie duplikuj backendowej source selection.

### I03-009

Nie parsuj labels do IDs.

### I03-010

Nie importuj planner internals do Interactive poza publicznymi contracts.

### I03-011

Nie dodawaj concrete service calls.

### I03-012

External registration wyłącznie AppService.

### I03-013

Manual używa globalnego translation/TTS config.

### I03-014

Manual używa wspólnego Rich progress.

### I03-015

Markery wyboru są po lewej.

### I03-016

Nie pytaj o niewidoczne techniczne parametry.

### I03-017

Nie przywracaj Textual.

### I03-018

Nie twórz nowego routera ekranów.

### I03-019

Cancel przed Start nie wykonuje backend tasków.

### I03-020

Return to changes zachowuje lokalne choices w tej sesji, ale nie persistuje ich.

---

## 11. Model lokalnego draftu Manual

### 11.1. Minimalny cel

Nie używać `GroupIntent` jako mutowalnego formularza, bo jest immutable.

W `manual.py` wolno mieć mały lokalny draft, np. dataclass, zawierający dokładnie pola
potrzebne do zbudowania `GroupIntent`.

### 11.2. Zakres draftu

Maksymalnie:

```text
group_id
products
subtitle_source_policy
translation_action
preferred_video_artifact_id
selected_subtitle_artifact_id
selected_audio_artifact_id
selected_audio_track_id
selected_subtitle_track_id
source_subtitle_language
external_audio_role
subtitle_output_format
```

Nie dodawać do draftu:

```text
LLM model
voice
tempo
gains
retry
progress
UI cursor
```

### 11.3. Default creation

Draft bierze default workflow z default preset i zero explicit selections.

### 11.4. Materialization

Jedna funkcja:

```text
draft -> GroupIntent(mode=MANUAL)
```

Powinna być czysta i łatwa do unit test.

---

## 12. Wybór grup

### 12.1. Source

Po `discover()` użyj `workspace.groups` w deterministycznej kolejności otrzymanej z
backendu.

Nie sortuj drugi raz, chyba że current contract nie gwarantuje kolejności; wtedy użyj
tej samej naturalnej reguły co backend, nie własnego locale sort.

### 12.2. Label

Podstawowo:

```text
group.source.stem
```

Jeżeli stem się duplikuje w różnych folderach, dodaj krótki relative directory suffix.

Nie pokazuj `group-<hash>`.

### 12.3. Default selected

Wszystkie grupy domyślnie selected.

Jeżeli grupa ma konflikt blokujący oczywisty już po inspection, nie ukrywaj jej.

Preferowane zachowanie:

```text
○ Nazwa odcinka · konflikt źródeł
```

jako disabled, jeśli Questionary public API pozwala.

Jeżeli disabled choice nie jest stabilne w aktualnej bibliotece, pokaż warning przed
pickerem i pozwól plannerowi potwierdzić blocker później zamiast implementować custom UI.

### 12.4. Empty selection

Reprompt.

---

## 13. Default/manual choice per group

Dla każdego selected group:

```text
● Użyj ustawień domyślnych
  Dostosuj ten odcinek
  Wróć
```

`Użyj ustawień domyślnych` nie oznacza Auto run.

Oznacza:

```text
manual GroupIntent
+ default preset workflow values
+ no explicit artifact/track overrides
```

`Wróć` wraca do group list bez utraty dotychczasowych lokalnych draftów.

---

## 14. Produkty per group

### 14.1. Source of default

Current default preset.

### 14.2. Visible products

Dokładnie te same cztery co Settings:

```text
Polskie napisy
Polski lektor
MKV
MP4
```

### 14.3. Marker

Left-only.

### 14.4. Minimum

At least one.

### 14.5. Mapping

To samo mapping co PLAN 02.

### 14.6. Derived container internals

Zachować backend/default policy.

Nie pytać o:

```text
mkv_tracks
burn_subtitle_product
mp4_audio_source
bitrate
composition quality
```

---

## 15. Translation action pozostaje domyślna

PLAN 03 nie dodaje osobnego promptu `Tłumaczenie` per odcinek.

Każdy lokalny draft dziedziczy:

```text
translation_action
```

z aktywnego domyślnego presetu i przekazuje ją do `GroupIntent`.

Powód:

- SPEC wymaga wyboru grup, źródeł i produktów, nie osobnego per-group translation mode;
- globalne Settings już decydują o silniku/modelu/promptach;
- dodatkowy prompt zwiększa liczbę kroków dla każdego odcinka;
- `READY_POLISH` i source policy pozostają domenowymi sposobami obsługi gotowych źródeł.

Jeżeli później powstanie realny przypadek użycia `force/skip translation` per odcinek, jest
to nowy requirement, nie ukryta funkcja tego planu.

---

## 16. Subtitle source per group

### 16.1. Kiedy pytać

Pytaj tylko, gdy selected products/planner path potrzebują subtitle-derived input albo
user jawnie wszedł w `Napisy źródłowe`.

### 16.2. Public choices

Lista może zawierać, zależnie od inspected group:

```text
Automatycznie
<ready sidecar ASS/SRT>
<ready Polish subtitle artifact>
<embedded subtitle track>
Plik zewnętrzny...
Brak
```

`Brak` można zaakceptować jako intent, ale planner ma prawo zablokować plan, jeśli
wybrane produkty wymagają napisów.

Nie próbuj ukrywać wszystkich kombinacji przez frontend heuristics.

### 16.3. Sidecar artifact

Value przechowuje exact `artifact_id`.

Policy musi odpowiadać semantyce planner contractu:

```text
SOURCE_SUBTITLES sidecar -> SIDECAR
ready Polish artifact   -> READY_POLISH
```

Przed implementacją wykonawca potwierdza dokładne mappingi w `planner.py` i
`tests/application/test_planner.py`.

Jeżeli current planner ma inny jawny mapping, plan adaptuje lokalną nazwę, ale nie
zmienia domain semantics.

### 16.4. Embedded track

Value:

```text
track_id
```

Policy:

```text
EMBEDDED
```

### 16.5. Automatycznie

Czyści explicit subtitle selections i przywraca default preset policy, albo `AUTO`,
jeśli user jawnie wybrał Auto source.

### 16.6. External

User wpisuje ścieżkę.

Interactive:

```text
Path input
→ AppService.register_external_subtitle
→ updated group
→ exact returned artifact_id
→ policy EXTERNAL
```

Jeżeli język nie wynika z metadata i current API wymaga declared language, zapytaj o
krótki ISO code tylko wtedy.

Nie twórz file picker GUI.

### 16.7. Label embedded track

Czytelny format, np.:

```text
#3 · jpn · ASS · Signs
```

Pomiń puste elementy.

Nie pokazuj `None`.

---

## 17. Video source per group

### 17.1. Kiedy pytać

Tylko jeśli istnieje więcej niż jeden usable video candidate i wybór ma znaczenie.

### 17.2. Default

`Automatycznie` = brak `preferred_video_artifact_id`.

### 17.3. Explicit

Value = exact `artifact_id`.

Label = filename + container.

Nie duplikować `choose_primary_video`.

---

## 18. Audio source per group

### 18.1. Kiedy pytać

Tylko gdy products wymagają źródłowego audio / narration path i grupa ma realny wybór,
lub user jawnie wszedł w `Audio źródłowe`.

### 18.2. Choices

Zależnie od inspected data:

```text
Automatycznie
<embedded audio track>
<registered external audio>
Plik zewnętrzny jako źródło...
Gotowy zewnętrzny lektor/mix...
```

### 18.3. Embedded

Value = `selected_audio_track_id`.

Nie ustawiaj `selected_audio_artifact_id` równocześnie.

### 18.4. Registered external

Value = `artifact_id`.

Role zgodna z artifact kind.

### 18.5. New external source audio

```text
path
→ register_external_audio(role=SOURCE_AUDIO)
→ returned artifact_id
```

### 18.6. New ready narration mix

```text
path
→ register_external_audio(role=NARRATION_MIX)
→ returned artifact_id
```

Planner potem rozstrzyga, czy wybrane products są z tym spójne.

### 18.7. Validation error

External file invalid/duration mismatch:

- safe error;
- pozostajemy przy tym group;
- nie tracimy innych draftów;
- nie dodajemy artefaktu ręcznie.

---

## 19. Minimalny preview

Po materializacji intents:

```text
service.plan_manual(intents)
```

### 19.1. Blocking problems

Renderuj grupowane po source stem:

```text
Buchigire! 02
  ✗ Brak poprawnego źródła napisów
```

Nie pokazuj artifact IDs, jeśli message jest wystarczający.

### 19.2. Warnings

Nieblokujące warnings mogą być pokazane jako jedna krótka lista.

### 19.3. Executable summary

Policz z `GroupPlan.intent.products` publiczne produkty.

Nie licz task kinds jako user products.

### 19.4. Start

Dopiero:

```text
Uruchom
```

wywołuje execution.

---

## 20. Wspólny execution flow

### 20.1. Preferowany kontrakt

Po PLANIE 01 powinien istnieć albo dać się minimalnie wydzielić helper:

```text
execute_plan(service, plan, ...)
```

który posiada:

- EventBuffer/sink;
- Rich progress;
- Ctrl+C/cancel policy;
- result rendering;
- safe error mapping.

### 20.2. Zakaz duplikacji

Nie kopiować z Auto:

```text
while drain events
retry row logic
fallback row logic
result summary
error handling
```

### 20.3. Refactor gate

Jeżeli PLAN 01 nie wydzielił reusable execution path, dozwolony jest mały refactor
`cli/run.py` bez zmiany Auto behavior.

Po refactorze testy Auto muszą przejść przed dalszym Manualem.

---

## 21. Docelowe drzewo

Minimalne:

```text
anishift/cli/interactive/
├── __init__.py
├── app.py
├── home.py
├── mascot.py
├── manual.py
├── progress.py
├── prompts.py
├── settings.py
└── settings_editors.py

tests/cli/
├── test_interactive_app.py
├── test_interactive_manual.py
├── test_interactive_progress.py
└── ...
```

Preferuj jeden `manual.py`.

Nie twórz od razu:

```text
manual/
manual_router.py
manual_store.py
manual_context.py
manual_controller.py
manual_view.py
manual_repository.py
```

Jeżeli `manual.py` przekracza ~800 linii produkcyjnych z dwiema wyraźnie niezależnymi
odpowiedzialnościami, zatrzymaj się przed rozbiciem i wyjaśnij potrzebę.

---

## 22. Expected Touch Set

### 22.1. Nowe

```text
anishift/cli/interactive/manual.py
tests/cli/test_interactive_manual.py
```

### 22.2. Modyfikowane

```text
anishift/cli/interactive/app.py
anishift/cli/interactive/prompts.py       tylko jeśli brakuje primitive
anishift/cli/run.py                       tylko jeśli potrzebny reusable execute helper
anishift/cli/AGENTS.md
```

### 22.3. Regression tests do modyfikacji warunkowo

```text
tests/cli/test_interactive_app.py
tests/cli/test_run.py
```

### 22.4. Read-only domyślnie

```text
anishift/application/service.py
anishift/application/intents.py
anishift/application/planner.py
anishift/application/planning.py
anishift/application/inspection.py
anishift/application/artifacts.py
anishift/application/selection.py
anishift/services/media/types.py
anishift/config/presets.py
```

### 22.5. Zakazane

```text
anishift/services/translation/**
anishift/services/tts/**
anishift/services/audio/**
anishift/services/composition/**
anishift/application/scheduler*
anishift/application/*_handler.py
anishift/tui/**
anishift/pipeline/**
.github/**
external/**
```

Jeżeli Manual wydaje się wymagać backend change, najpierw udowodnij brak capability w
AppService/planner.

---

## 23. Kontrakt `interactive/manual.py`

### 23.1. Publiczna odpowiedzialność

Jedno wejście logiczne:

```text
run_manual_interactive(service, prompts, renderer/executor dependencies)
```

Dokładna signature wynika z finalnego PLANU 01/02.

### 23.2. Co zawiera

- local draft dataclass;
- option projection helpers;
- group selection;
- per-group wizard;
- intent materialization;
- preview;
- dispatch shared execute flow.

### 23.3. Czego nie zawiera

- backend service clients;
- persistence;
- global state;
- progress implementation;
- JSON reading;
- model/TTS setting editing.

### 23.4. Pure helpers

Preferowane pure helpers dla testowalności:

```text
default_draft(...)
materialize_intent(...)
subtitle_choices(...)
audio_choices(...)
video_choices(...)
product_choices(...)
format_track_label(...)
format_artifact_label(...)
```

Nie tworzyć klas dla każdego helpera.

---

## 24. Kontrakt cancel/back

### 24.1. Group list cancel

Powrót Home.

### 24.2. Per-group `Wróć`

Powrót do listy grup lub poprzedniego logicznego poziomu.

Nie wykonuje runu.

### 24.3. Preview `Wróć do zmian`

Zachowuje local drafts i wraca do group customizations.

### 24.4. Preview `Anuluj`

Czyści local manual state przez zakończenie funkcji i wraca Home.

### 24.5. Ctrl+C przed execute

Bezpieczny powrót/exit według globalnej policy PLANU 01.

### 24.6. Ctrl+C podczas execute

Ten sam cancellation path co Auto.

---

## 25. Testy pure draft/intent

### M03-01

Default draft bierze current default preset.

### M03-02

Materialized intent ma `RunMode.MANUAL`.

### M03-03

Default intent nie ma explicit IDs.

### M03-04

Per-group products nie mutują preset object.

### M03-05

Subtitle artifact and track nie mogą być ustawione jednocześnie.

### M03-06

Audio artifact and track nie mogą być ustawione jednocześnie.

### M03-07

External role istnieje tylko przy external artifact.

### M03-08

Back/cancel nie persistuje.

---

## 26. Testy choice projection

### C03-01

Group labels używają stem.

### C03-02

Duplicate stems dostają disambiguation.

### C03-03

Subtitle choices zawierają ready sidecars.

### C03-04

Invalid subtitle artifacts nie są prezentowane jako usable selection.

### C03-05

Embedded subtitle tracks mają language/codec/name bez `None` spam.

### C03-06

Audio choices rozróżniają tracks i registered external.

### C03-07

Video choice nie powstaje przy jednym usable video.

### C03-08

Backend IDs są choice values, nie parsowane z title.

---

## 27. Testy workflow Manual

### W03-01

Home `Ręczny` wywołuje Manual.

### W03-02

Empty workspace wraca Home bez plan/execute.

### W03-03

Group picker domyślnie zaznacza wszystkie.

### W03-04

Empty group choice reprompt.

### W03-05

`Użyj ustawień domyślnych` tworzy manual intent.

### W03-06

Custom products są per-group.

### W03-07

Manual draft dziedziczy `translation_action` z default preset i nie pokazuje osobnego promptu.

### W03-08

Specific subtitle track trafia do selected track ID.

### W03-09

Specific sidecar trafia do selected artifact ID z prawidłową policy.

### W03-10

External subtitle woła AppService registration.

### W03-11

External audio woła AppService registration.

### W03-12

Registration error nie kasuje innych draftów.

### W03-13

`plan_manual` dostaje dokładnie selected group intents.

### W03-14

Blocking plan nie wywołuje execute.

### W03-15

Executable preview wymaga explicit Start.

### W03-16

Start używa wspólnego execution path.

### W03-17

Manual nie zapisuje settings/presets.

### W03-18

Auto regression po refactorze execution path.

---

## 28. Data flow — zwykły Manual

```text
Home -> Ręczny
→ AppService.discover
→ InspectedWorkspace
→ group checkbox
→ default preset
→ local ManualDraft per selected group
→ user accepts defaults
→ GroupIntent(MANUAL)
→ AppService.plan_manual
→ preview
→ shared execute_plan
→ Rich progress
→ result
→ Home
```

---

## 29. Data flow — custom subtitle track

```text
InspectedSourceGroup.media_catalogs
→ subtitle MediaTrack choices
→ select track_id
→ draft.selected_subtitle_track_id
→ policy EMBEDDED
→ GroupIntent
→ planner validates exact track
```

---

## 30. Data flow — external subtitle

```text
user path
→ AppService.register_external_subtitle
→ validated updated InspectedSourceGroup
→ returned/located Artifact ID
→ local draft
→ GroupIntent
→ planner
```

---

## 31. Data flow — external audio

```text
user path + role
→ AppService.register_external_audio
→ duration/decode validation
→ updated group
→ artifact ID
→ GroupIntent
→ planner
```

---

## 32. Data flow — blocked plan

```text
manual intents
→ AppService.plan_manual
→ ExecutionPlan(can_execute=false)
→ safe blocker list
→ Wróć do zmian / Anuluj
```

No execute.

---

## 33. Kolejność implementacji

### Krok 1 — baseline refresh

Potwierdź PLAN 02 final SHA i kontrakty.

### Krok 2 — branch

```bash
git switch -c work/interactive-cli/03-manual
```

### Krok 3 — audit planner tests

Przeczytaj dokładne testy manual selection/policies.

Zapisz sobie mapping:

```text
UI choice -> GroupIntent fields
```

Nie koduj przed tym.

### Krok 4 — pure local draft

Utwórz w `manual.py` draft + materialization.

Unit tests.

### Krok 5 — group projection

Dodaj labels/group checkbox.

### Krok 6 — default/manual choice

Podłącz `Użyj ustawień domyślnych` i `Dostosuj`.

### Krok 7 — products

Per-group product checkbox.

### Krok 8 — inherited translation action

Potwierdź testem, że draft zachowuje `translation_action` default presetu i że nie istnieje
osobny prompt translation action.

### Krok 9 — subtitle sources

Sidecar + embedded + external + auto.

Targeted tests.

### Krok 10 — video/audio sources

Tylko warunkowo potrzebne choices.

Targeted tests.

### Krok 11 — plan_manual + blockers

Bez execute.

### Krok 12 — minimal preview

Start/Back/Cancel.

### Krok 13 — shared execution

Jeżeli potrzebny mały refactor `cli/run.py`, wykonaj teraz i najpierw uruchom Auto
regression tests.

### Krok 14 — app dispatch

`Ręczny` przestaje być placeholderem.

### Krok 15 — targeted test suite

Manual + Auto regressions.

### Krok 16 — static gates

Ruff, format, mypy.

### Krok 17 — diff review

No unexpected backend changes.

### Krok 18 — READY_FOR_HITL

Nie commitować.

### Krok 19 — real HITL

Czekać.

### Krok 20 — PASS

Pełny pytest, jeden commit, push.

---

## 34. Budżet zmiany

### Produkcja

```text
manual.py              450–750
app.py delta             10–40
prompts.py delta           0–80
run.py delta               0–120
```

### Testy

```text
manual tests            450–850
run/app regressions       0–220
```

### Alarm

Jeżeli potrzeba:

```text
> 950 nowych linii production
> 1200 nowych linii tests
> 4 nowych production modules
```

STOP i wyjaśnienie.

Manual jest wizardem, nie nowym frontend frameworkiem.

---

## 35. Targeted verification

Minimalnie:

```bash
uv run pytest tests/cli/test_interactive_manual.py
uv run pytest tests/cli/test_interactive_app.py
uv run pytest tests/cli/test_run.py
uv run pytest tests/application/test_intents.py
uv run pytest tests/application/test_planner.py
```

Następnie:

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
```

Full pytest dopiero po manualnym PASS.

---

## 36. Kontrola diffu

Expected:

```text
anishift/cli/interactive/manual.py
anishift/cli/interactive/app.py
anishift/cli/interactive/prompts.py   opcjonalnie
anishift/cli/run.py                   opcjonalnie
anishift/cli/AGENTS.md
tests/cli/test_interactive_manual.py
tests/cli/test_interactive_app.py    opcjonalnie
tests/cli/test_run.py                opcjonalnie
```

Jeżeli zmieniono:

```text
planner.py
intents.py
inspection.py
services/**
```

bez uprzedniego blocker report:

```text
FAIL / REPLAN
```

---

## 37. HITL — przygotowanie

Agent przed testem wypisuje:

```text
CO MASZ TERAZ SPRAWDZIĆ W TRYBIE RĘCZNYM
```

Użytkownik przygotowuje workspace zawierający najlepiej:

- co najmniej 2 odcinki;
- jeden MKV z więcej niż jedną ścieżką napisów lub audio;
- opcjonalny sidecar ASS/SRT;
- jeden realny output flow z lektorem.

---

## 38. HITL-01 — wejście i discovery

1. `uv run anishift`;
2. wybierz `Ręczny`;
3. obserwuj discovery.

Oczekiwane:

- brak fake procentu;
- potem lista odcinków;
- Home nie zmienia się w dashboard;
- brak command input.

---

## 39. HITL-02 — wybór grup

1. przejdź listę;
2. odznacz jeden odcinek;
3. zatwierdź.

Oczekiwane:

- marker po lewej;
- wszystkie były preselected;
- odznaczony odcinek nie trafia do planu;
- nazwy są czytelne.

---

## 40. HITL-03 — default path

Dla pierwszego selected episode wybierz:

```text
Użyj ustawień domyślnych
```

Oczekiwane:

- nie pojawia się lawina pytań;
- globalne Settings są defaultem;
- grupa nadal jest manual intentem.

---

## 41. HITL-04 — custom products

Dla kolejnego episode:

1. `Dostosuj`;
2. `Wynik`;
3. ustaw inny product set.

Oczekiwane:

- left markers;
- minimum one;
- zmiana dotyczy tylko tej grupy;
- Settings i default preset pozostają bez zmiany.

---

## 42. HITL-05 — subtitle source

Na pliku z kilkoma źródłami:

1. wejdź `Napisy źródłowe`;
2. wybierz konkretny embedded track albo sidecar;
3. wróć;
4. zbuduj preview.

Oczekiwane:

- label ma language/track info;
- brak surowych hash IDs;
- planner akceptuje wybrane źródło;
- Auto default nie został zmieniony.

---

## 43. HITL-06 — external subtitle

Jeżeli chcesz przetestować:

1. wybierz `Plik zewnętrzny...`;
2. podaj prawidłowy ASS/SRT;
3. zatwierdź.

Oczekiwane:

- plik jest walidowany przez backend;
- invalid path daje safe error;
- po błędzie pozostajesz w current group;
- brak ręcznie skonstruowanego Artifact w UI.

---

## 44. HITL-07 — audio source

Na MKV z kilkoma audio tracks:

1. wybierz konkretny audio track;
2. wróć do preview.

Oczekiwane:

- czytelny language/name/codec;
- planner dostaje exact track ID;
- reszta grup używa defaults.

---

## 45. HITL-08 — blocker

Świadomie wybierz kombinację prowadzącą do blocker, jeżeli można to zrobić bez szkody,
np. product wymagający subtitles przy source `Brak`.

Oczekiwane:

- execute nie startuje;
- widzisz krótką przyczynę;
- można wrócić do zmian;
- lokalne pozostałe drafty nie giną.

---

## 46. HITL-09 — preview

Dla poprawnego planu sprawdź:

```text
liczbę odcinków
counts produktów
Uruchom / Wróć do zmian / Anuluj
```

Nie powinno być task DAG-u.

---

## 47. HITL-10 — real execute

Wybierz `Uruchom`.

Oczekiwane:

- ten sam Rich progress co Auto;
- translation = spinner bez fake %;
- TTS = real percentage;
- retry/fallback aktualizuje wiersz;
- result summary jest spójny z Auto.

---

## 48. HITL-11 — persistence isolation

Po zakończeniu:

1. wejdź Settings;
2. sprawdź global values;
3. uruchom Auto.

Oczekiwane:

- manual source choices nie zostały zapisane;
- per-group products nie zmieniły default preset;
- Auto nadal używa swoich global defaults.

---

## 49. HITL-12 — empty workspace

Na pustym workspace:

```text
Ręczny
```

ma dać krótki komunikat i powrót, bez tracebacka.

---

## 50. HITL-13 — cancel

Sprawdź anulowanie:

- group selection;
- per-group edit;
- preview;
- podczas realnego execute.

Przed Start zero pipeline side effects.

Podczas run ta sama cancel policy co Auto.

---

## 51. Obowiązkowy raport agenta

```text
STATUS: READY_FOR_HITL

Plan:
PLAN 03 — Manual

Branch:
work/interactive-cli/03-manual

Base:
<PLAN_02_FINAL_SHA>

Commit:
NONE — awaiting HITL

Manual owner:
...

Execution path:
Auto + Manual -> ...

Local manual state:
EPHEMERAL ONLY

Global settings mutation during manual:
NONE

Default preset mutation during manual:
NONE

Changed production files:
- ...

Changed test files:
- ...

Automated gates:
- manual tests: PASS/FAIL
- Auto regression: PASS/FAIL
- intents/planner regression: PASS/FAIL
- ruff: PASS/FAIL
- format: PASS/FAIL
- mypy: PASS/FAIL
- git diff --check: PASS/FAIL

Unexpected files:
NONE / list

CO MASZ TERAZ SPRAWDZIĆ W TRYBIE RĘCZNYM:
[pełna checklista dostosowana do realnego diffu]

CELOWO JESZCZE NIE DZIAŁA:
- finalna kolorowa maskotka
- animowane stany
- Chafa/Sixel
- download anime

Jeżeli coś nie działa, podaj HITL-XX i objaw.
```

---

## 52. PASS / FAIL

### PASS

Po user `PASS`:

```bash
uv run pytest
git diff --check
```

Jeden commit:

```text
feat(cli): add guided manual workflow
```

Push:

```text
work/interactive-cli/03-manual
```

### FAIL

Ten sam branch, zero finalnego commita, targeted fix, ponowny HITL.

---

## 53. Zakazane skróty

Nie wolno:

- odtworzyć starego `manual.py` Textual 1:1;
- utworzyć ManualStore;
- zapisywać draftów;
- zmieniać Settings z Manual;
- zmieniać default preset z Manual;
- pytać o technical knobs;
- tworzyć osobnego progress systemu;
- tworzyć osobnego error systemu;
- implementować source selection heuristics drugi raz;
- konstruować Artifact ręcznie;
- parsować labels do IDs;
- wykonywać blocking plan;
- używać `plan_auto` dla części manual run;
- modyfikować planner dla wygody UI bez blocker gate;
- dodać Textual;
- dodać slash commands;
- wymagać myszy;
- ogłosić DONE przed HITL.

---

## 54. Ryzyka i reakcje

### RISK-03-A — wizard robi się formularzem wszystkiego

Sygnał:

```text
każdy odcinek = kilkanaście promptów
```

Reakcja:

```text
default first
customization opt-in
conditional questions only
```

### RISK-03-B — frontend replikuje planner

Sygnał:

```text
manual.py ma własne reguły legalności kombinacji
```

Reakcja:

```text
zostaw tylko podstawowe UX guardy
planner = final validator
```

### RISK-03-C — manual choices przeciekają do global config

Sygnał:

```text
save_preset/save_setting podczas wizardu
```

Reakcja:

```text
usunąć persistence path
add isolation regression test
```

### RISK-03-D — duplikacja execute

Sygnał:

```text
Manual ma własny EventBuffer/ProgressManager mapping
```

Reakcja:

```text
wydziel wspólny execute_plan z istniejącego Auto
```

### RISK-03-E — external file feature rozrasta się w picker

Sygnał:

```text
GUI directory browsing / custom widget
```

Reakcja:

```text
plain path input
backend validation
```

---

## 55. Coverage

| Requirement area | Właściciel | Dowód |
|---|---|---|
| R-1000 shared settings | AppService plan snapshot | HITL-03/11 |
| group selection | manual.py | HITL-02 |
| per-group products | local draft | HITL-04 |
| subtitle source | inspected data -> intent | HITL-05/06 |
| audio source | media catalog -> intent | HITL-07 |
| no technical prompts | manual.py allowlist | całe HITL |
| GroupIntent | application contracts | unit/planner tests |
| blocking preview | plan_manual | HITL-08 |
| explicit Start | manual preview | HITL-09 |
| shared progress | run/progress | HITL-10 |
| no persistence | local state | HITL-11 |
| empty/cancel | manual flow | HITL-12/13 |

---

## 56. Definition of Done

```text
[ ] PLAN 02 ma VERIFIED / COMMITTED.
[ ] Baseline jest dokładnym finalnym SHA PLANU 02.
[ ] Powstał work/interactive-cli/03-manual.
[ ] Home Ręczny jest prawdziwą akcją.
[ ] Discovery używa AppService.
[ ] Empty workspace jest obsłużony.
[ ] Group list używa markerów po lewej.
[ ] Wszystkie usable grupy są domyślnie selected.
[ ] Empty group choice jest odrzucony.
[ ] Default path wymaga minimum pytań.
[ ] Każdy selected group tworzy manual GroupIntent.
[ ] Global settings są defaults.
[ ] Manual overrides nie persistują.
[ ] Default preset nie jest mutowany przez Manual.
[ ] Per-group products działają.
[ ] Translation action jest dziedziczona z default preset bez osobnego promptu.
[ ] Specific subtitle sidecar/track działa.
[ ] External subtitle registration używa AppService.
[ ] Specific audio track działa.
[ ] External audio registration używa AppService.
[ ] IDs są choice values, nie parsowane z labeli.
[ ] plan_manual jest finalnym walidatorem.
[ ] Blocking plan nigdy nie wykonuje execute.
[ ] Preview jest minimalny.
[ ] Start jest jawny.
[ ] Manual i Auto używają tego samego execution/progress path.
[ ] Translation nie dostało fake procentu.
[ ] TTS nadal ma real progress.
[ ] Cancel działa przed i podczas execute.
[ ] Nie dodano Textual.
[ ] Nie utworzono nowego UI store.
[ ] Targeted tests przechodzą.
[ ] Ruff przechodzi.
[ ] Format przechodzi.
[ ] Mypy przechodzi.
[ ] Diff check przechodzi.
[ ] Agent wypisał pełne CO MASZ TERAZ SPRAWDZIĆ.
[ ] Użytkownik podał PASS.
[ ] Pełny pytest przeszedł po PASS.
[ ] Powstał jeden finalny commit.
[ ] Branch został wypchnięty.
```

Dopiero wtedy:

```text
PLAN 03 VERIFIED / COMMITTED
READY FOR PLAN 04 — MASCOT + POLISH + CLEANUP
```

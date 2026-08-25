# Etap 10 - plan wykonawczy TUI AniShift

**Status:** READY
**Wymagania:** [`spec.md`](./spec.md)
**Manifest zadań:** [`tasks.json`](./tasks.json)
**Baseline kontraktu:** `6849f32d4b197aff3507266e55f3d7fbb5c674d4`
**Audytowana gałąź:** `feature/stage-9-product-tui`
**Gałęzie wykonawcze:** P-01 (T-001, T-002) na `feature/stage-9-product-tui`, T-003+ na `feature/stage-10-tui` odbitej od świeżego `main` po zmergowaniu etapu 9
**Referencja OpenCode:** `03bba464d46f3eddf74195919b1344aa937f7b11`

> Ten dokument definiuje JAK. Nie powtarza całej specyfikacji. Każde zadanie w `tasks.json` jest naturalną jednostką wykonawczą: implementacja, testy lokalne i potrzebna dokumentacja należą do jednego zadania, zamiast pięciu sztucznych subagentów.

## 0. Kontrakt wykonania

1. Przed pierwszą zmianą wykonawca sprawdza `git status --short`, `git rev-parse HEAD`, aktywną gałąź i różnicę względem baseline. Jeśli kod produkcyjny zmienił kontrakty opisane w §1-3, plan wraca do aktualizacji zamiast być realizowany na pamięć.
2. Wykonanie jest dwugałęziowe: faza P-01 (T-001, T-002) zamyka gałąź `feature/stage-9-product-tui`, która idzie PR-em do `main`; T-003+ startuje na nowej gałęzi `feature/stage-10-tui` odbitej od świeżego `main` dopiero po zmergowaniu etapu 9.
3. Każda faza kończy się działającym repo. Minimalne bramki: `ruff check`, `ruff format --check`, `mypy`, pełny `pytest`.
4. `anishift/application/` pozostaje źródłem use case'ów i może być zmieniane wyłącznie tam, gdzie plan jawnie rozszerza publiczną fasadę. TUI nie importuje konkretnych usług.
5. Do zakończenia P-03 TUI działa jako osobny prototyp; legacy shell pozostaje domyślnym wejściem. Backend nie jest podłączany przed akceptacją wyglądu.
6. Przeglądanie list, ustawień i modeli jest offline. Jedyny dozwolony test sieciowy z UI to pojedynczy, jawnie potwierdzony probe `/connect`.
7. Tokeny, nagłówki Authorization, prompty, treść napisów/TTS, pełne payloady i absolutne prywatne ścieżki nie trafiają do kodu, JSONC, testów, logów ani komunikatów UI.
8. Zależności zmienia się wyłącznie przez `uv add` / `uv remove`. Commity stosują istniejący zakres `cli`, dopóki hook repo nie zostanie osobno zmieniony za zgodą użytkownika.
9. T-009 jest twardą bramką. Zadania T-010+ nie startują bez jawnej akceptacji użytkownika.
10. `tasks.json` nie przechowuje statusu, przypisanego agenta ani logu decyzji. Orkiestrator może z niego tworzyć briefy zadań i prowadzić stan poza planem.

## 1. Stan obecny i luka

| Obszar | Stan zweryfikowany | Luka do stanu docelowego | Decyzja |
| --- | --- | --- | --- |
| Punkt wejścia | `anishift` bez argumentów uruchamia starą powłokę `prompt-toolkit`. | Docelowo ma uruchamiać Textual TUI. | Przełączenie dopiero w P-06 po pełnym przepływie i parytecie. |
| Aktualne TUI | Istniejące `anishift/tui/` jest odrzuconym prototypem; nie jest aktywnym punktem wejścia. | Warstwa ma zostać napisana od nowa, bez dziedziczenia złego layoutu. | Usunąć w T-002; zachować tylko sprawdzone idee: EventBuffer, generation guard, wykonawca thread. |
| Warstwa aplikacji | `AppService` obsługuje discovery, presety, plan auto/manual, execute, cancel, settings, doctor i setup. | Brakuje bezpiecznej operacji aktualizacji pojedynczego SettingSpec i fasady katalogu/probe modeli. | Rozszerzyć minimalnie w T-010/T-015/T-016. |
| Planner i scheduler | Nowa ścieżka aplikacyjna tworzy immutable `ExecutionPlan` i wykonuje graf. | Legacy `anishift/pipeline/` nadal istnieje równolegle. | Usunąć dopiero po hermetycznym teście parytetu T-026. |
| Ustawienia | `field_catalog.py` opisuje typy, zakresy, zależności i scope; `UserSettings` zapisuje atomowo. | Prywatne mapowanie wartości jest związane ze starym UI, brak kompletnego drzewa dialogów. | Wydzielić `field_access.py`, jeden dispatch edytorów i per-field commit. |
| Sekrety | `Settings` czyta env/.env; `env_file.py` potrafi atomowo zmienić klucz. | TUI nie ma bezpiecznej edycji/statusu kluczy ani tokenu Palantir. | Sekrety przez AppService, zamaskowany status, kanoniczny `ANISHIFT_PALANTIR_TOKEN`. |
| LLM | Rejestr ma Anthropic, Gemini, OpenAI, OpenAI-compatible, OpenRouter i DeepSeek. | Brak adaptera Palantir, katalogu aliasów i czterech protokołów proxy. | Dodać jeden engine `palantir` nad istniejącym neutralnym LLM API. |
| Modele Foundry | Użytkownik wskazał `opencode.corrected.jsonc`, ale plik nie znajduje się w bieżącym zestawie wejściowym. | Bez treści pliku nie wolno zakładać aliasów, RID-ów, enrollmentu ani endpointów. | Traktować go wyłącznie jako opcjonalne, sanityzowane źródło danych po faktycznym dostarczeniu; prawdą wykonawczą pozostaje lokalny `anishift.models.jsonc` + jawny probe. |
| Design | Brak zaakceptowanego design systemu. | Poprzednie TUI było zbyt ciężkie i nieintuicyjne. | Najpierw tokeny, logo, dialogi, composer i wizualna bramka akceptacji; dopiero potem backend. |
| Kodowanie | Launcher ustawia UTF-8, ale bezpośrednie CLI może trafić na cp1250. | Unicode status/logo może wywrócić proces. | Zabezpieczyć granicę procesu w T-001. |
| CI | Pełny CI działa na Ubuntu; produkt jest Windows-first. | Brak systematycznego smoke TUI/CLI na Windows. | Dodać skupiony Windows job w T-027. |

## 2. Analiza oddziaływania i kontrakty, których nie wolno zgubić

### 2.1. Publiczne kontrakty zachowywane

- `AppService.discover`, `register_external_subtitle`, `register_external_audio`, `list_presets`, `get_preset`, `save_preset`, `plan_auto`, `plan_manual`, `execute`, `cancel`, `settings_catalog`, `settings_snapshot`, `save_settings`, `doctor`, `setup`.
- `ExecutionPlan.can_execute`, uporządkowane `tasks`, problemy per grupa i immutable `RunSettingsSnapshot`.
- `EventBuffer` i `RunEvent` z bounded/coalesced progress oraz terminalnymi zdarzeniami.
- `UserSettings` z profilami TTS per engine+resolved voice, atomowy zapis i normalizacja wyborów.
- `SettingSpec.validate_value`, `depends_on`, `scope`, `allowed_values`, zakresy i 10 `SettingValueType`.
- Provider-neutralne `LlmRequest`, `LlmResponse`, `LlmUsage`, hierarchy błędów i retry w `LlmService`.

### 2.2. Miejsca oddziaływania

| Zmiana | Konsumenci | Główne ryzyko | Ochrona |
| --- | --- | --- | --- |
| Nowe pola modeli w `UserSettings` | bootstrap, snapshot planu, settings catalog, serializacja | stary settings.json, zły default | backward-compatible load + default + test round-trip |
| `AppService.update_setting` i sekrety | TUI settings, run snapshot | zapis częściowo poprawnego stanu | detached copy + pełna walidacja + atomowy commit |
| Adapter Palantir | translation runtime, `/connect`, status | przeciek tokenu, zły protokół | osobny config/auth/router + atrapa transportu + redakcja |
| Nowy `RunSettingsSnapshot` dla aliasu | planner/runtime | alias trafia do providera zamiast model ID | rozwiązywanie aliasu przed LlmConfig, test snapshot/runtime |
| Default TUI | Typer callback, launcher, testy CLI | doctor/setup importują Textual lub stają się wolne | lazy import wyłącznie w ścieżce no-args |
| Usunięcie pipeline | legacy CLI i testy | utrata zachowania/recovery | test parytetu i migracja wartościowych regresji przed kasacją |
| JSONC parser | build/lock, Windows, Python 3.14 | niekompatybilna zależność | `uv add json5`; czerwony resolver = replan D-10, bez własnego parsera |

### 2.3. Świadome zmiany zachowania

- Pusty Enter staje się podstawowym startem Auto; `/auto` pozostaje wyłącznie konfiguracją.
- Normalny, bezpieczny default Auto nie wymaga dodatkowego Preview. Plan jest tworzony zawsze, ale UI pokazuje dodatkowe potwierdzenie tylko przy blockerze, nowym nadpisaniu lub innym skutku wymagającym decyzji.
- Manual zawsze przechodzi przez Preview i jawny Start.
- Zwykły tekst nie uruchamia żadnego agenta ani pipeline; zachowanie przyszłego agenta pozostaje poza zakresem.
- Interaktywny prompt awarii legacy `retry/settings/finish` nie jest kopiowany 1:1. Wynik partial/failed prowadzi do Results i bezpiecznego replanu Manual.

## 3. Projekt techniczny

### D-01. Stack i granice zależności

- Python 3.14, Textual, Rich i Typer pozostają. Nie powstaje drugi frontend ani bridge do TypeScript/OpenTUI.
- Kierunek: `tui -> application -> config/services`; `application` nie importuje `tui`, `cli`, Textual, Typer ani Rich.
- `tui` może importować wyłącznie publiczne kontrakty z `anishift.application` i neutralne DTO z `anishift.config.field_catalog`. Dostęp do providerów, plików i narzędzi przechodzi przez AppService.
- Nowy kod produkcyjny jest dzielony według odpowiedzialności; orientacyjny limit ~400 linii na plik, ale nie tworzymy pustego modułu tylko dla limitu.

### D-02. Docelowe drzewo

```text
anishift/
├── cli/
│   ├── console.py                 # UTF-8 boundary
│   └── main.py                    # Typer, lazy TUI, doctor/setup/run
├── config/
│   ├── field_access.py            # SettingSpec <-> UserSettings
│   ├── model_catalog.py           # typed JSONC catalog
│   ├── settings.py                # env secrets incl. Palantir
│   └── user_settings.py           # primary/translation model choices
├── application/
│   ├── service.py                 # public facade extensions
│   └── runtime.py                 # alias -> concrete LLM config
├── services/llm/engines/
│   ├── __init__.py                # registry + palantir
│   └── palantir/
│       ├── __init__.py
│       ├── auth.py
│       ├── config.py
│       ├── protocols.py
│       ├── http.py
│       ├── normalize.py
│       ├── errors.py
│       └── service.py
└── tui/
    ├── __init__.py
    ├── __main__.py                # developerski/manualny launcher TUI przed i po zmianie entrypointu
    ├── app.py
    ├── auto_trigger.py
    ├── brand.py
    ├── lifecycle.py
    ├── messages.py
    ├── state.py
    ├── theme.py
    ├── tools.py
    ├── ui_state.py
    ├── workers.py
    ├── commands/                  # spec, registry, catalog, palette
    ├── dialogs/                   # base, select, value, reorder
    ├── models/                    # picker, connect
    ├── settings/                  # tree, editors, secrets
    ├── screens/                   # workspace, auto, manual, preview, execution, results, tools
    ├── widgets/                   # composer, footer, group table, plan, progress
    └── styles/                    # base, dialogs, screens
config/
└── anishift.models.example.jsonc           # bez sekretów; plik wykonawczy jest ignorowany przez Git
tests/
├── cli/
├── config/
├── application/
├── services/llm/
└── tui/                           # około 15 plików, scenariusze zamiast testu na każdy helper
```

### D-03. Design system i layout

- `theme.py` jest jedynym właścicielem literalnych kolorów. TCSS używa wyłącznie tokenów semantycznych.
- Główna rama od 100x30: statyczne logo, centralna treść, stały composer `❯`, pod nim zwarta stopka statusu i skrótów.
- Przy 80x24 logo przechodzi w wariant kompaktowy, opisy drugorzędne znikają, ale composer, paleta, dialog i wyjście pozostają dostępne.
- Dialogi mają przyciemnioną zasłonę i panel bez ciężkiej ramki. Rozmiary: 60/88/116 kolumn, zawsze ograniczone do terminala minus 2.
- Stan zawsze ma glif i słowo/pozycję strukturalną; kolor jest dodatkiem.

### D-04. Model stanu i lifecycle

`AniShiftApp` posiada jedną instancję `SessionState`:

```python
@dataclass(slots=True)
class SessionState:
    route: Route
    generation: int
    workspace: InspectedWorkspace | None
    selected_group_ids: set[str]
    default_preset_id: str
    auto_draft: AutoPresetDraft | None
    manual_drafts: dict[str, GroupIntentDraft]
    plan: ExecutionPlan | None
    active_run_id: str | None
    run_state: RunState
    events: list[RunEvent]
    result: RunResult | None
    feedback: UiFeedback | None
```

- Każda nowa operacja discovery/register/plan/run zwiększa lub przechwytuje `generation`.
- Wynik wykonawcy bez aktualnej generacji jest ignorowany. Zdarzenie przebiegu dodatkowo musi pasować do `active_run_id`.
- Fokus przed modalem jest zapamiętany i przywracany po `dismiss`.
- Timer EventBuffer istnieje tylko podczas runu; elapsed odświeża się maksymalnie 4 razy/s.

### D-05. Rejestr komend

`CommandSpec` jest frozen dataclass z polami: `name`, `slash_name`, `aliases`, `title`, `description`, `category`, `keys`, `hidden`, `enabled`, `suggested`, `handler`.

- Rejestr jest jedynym dispatch dla slash, palety, skrótu i przycisku.
- Katalog globalny zawiera dokładnie 14 slash commands z wymagań. Akcje ekranu są rejestrowane bez `slash_name`.
- Paleta jest projekcją visible+enabled. Przy pustym filtrze może dodać grupę Suggested; slash popup ma limit 10.
- `help` i stopki formatują klawisze bezpośrednio z rejestru/BINDINGS.

### D-06. Dialogi

Publiczne prymitywy:

```python
class SelectDialog[T](DialogScreen[SelectOutcome[T]]): ...
class ValueDialog(DialogScreen[SettingValue | None]): ...
class ReorderDialog(DialogScreen[tuple[str, ...] | None]): ...
class ConfirmDialog(DialogScreen[bool]): ...
```

- `SelectDialog`: filter focus, fuzzy, category, current marker, single/multi, action footer, disabled filtered out, initial_highlight.
- `ValueDialog`: string/optional/int/float/bool, widoczny zakres i format, walidacja na zmianę, Enter tylko dla poprawnej wartości.
- `ReorderDialog`: move/add/remove, Enter commit, Esc rollback.
- Drzewo ustawień nie stackuje wielu modalnych ekranów. Dziecko jest zastępowane rodzicem z zachowanym `initial_highlight`.

### D-07. Composer i exactly-once Auto

Maszyna stanu rozróżnia:

```text
EMPTY + Enter -> reserve generation -> AutoRequested
SLASH         -> registry.dispatch
PLAIN_TEXT    -> feedback "tekst nie wykonuje akcji"
RUNNING       -> Enter nie startuje niczego
```

- Rezerwacja następuje synchronicznie przed uruchomieniem wykonawcy planowania. Zrealizowana w T-007 jako `lifecycle.begin_planning`, bez osobnej flagi: `ALLOWED_RUN_TRANSITIONS` już odrzuca wejście w `planning` z `planning`, `running` i `cancelling`, więc `run_state` plus `generation` są jedynym źródłem prawdy.
- Trigger jest zwalniany po terminalnym wyniku plan/run albo po błędzie. Key repeat i drugi event z tą samą generacją są ignorowane.
- Auto wybiera default preset i zaznaczone grupy. Jeśli selekcja jest pusta, polityka jest jawna i stała: wszystkie gotowe grupy; jeśli nie ma gotowych grup, komunikat bez side effectu.
- Bezpieczny plan przechodzi do execution. Blocker nie uruchamia runu; nadpisanie/nieodwracalny skutek wymaga ConfirmDialog.

### D-08. Ustawienia i atomowy commit pola

Warstwa konfiguracji udostępnia:

```python
def read_setting_value(settings: UserSettings, spec: SettingSpec) -> SettingValue: ...
def assign_setting_value(settings: UserSettings, spec: SettingSpec, value: SettingValue) -> None: ...
def setting_is_active(spec: SettingSpec, settings: UserSettings) -> bool: ...
```

AppService dodaje minimalne metody:

```python
def update_setting(self, setting_id: str, value: SettingValue) -> UserSettings: ...
def update_secret(self, setting_id: str, value: str | None) -> None: ...
def reload_environment(self) -> Mapping[str, bool]: ...
```

- `update_setting`: deepcopy -> lookup active spec -> validate -> assign -> `__post_init__` -> atomic save -> swap in-memory.
- `update_secret`: allowlist wyłącznie SECRET specs, mapowanie do `ANISHIFT_*`, atomowy `.env`, reload; żadnego zwracania wartości.
- TUI pokazuje kategorię i aktualne skrócone wartości. Enter otwiera jeden editor, Enter commit, Esc rollback. Brak globalnego Save.

### D-09. Domeny ustawień

| Wejście | Zakres |
| --- | --- |
| `/auto` | presety i pola AUTO_PRESET; konfiguracja bez startu |
| `/translation` | translation engine/fallback/batching/retries oraz provider/model LLM |
| `/prompts` | prompt ID, style ID, module set |
| `/tts` | TTS engine/model/voice/profile, custom voices, audio output/mix |
| `/theme` | UI theme z live preview |
| `/model` | primary model alias, poza SettingSpec pipeline |
| `/connect` | token/status/provider/model probe; nie jest zwykłym drzewem preferencji |

Wspólny `editor_for(spec)` pokrywa 10 SettingValueType. Test coverage iteruje reprezentatywne konteksty engine/model/voice i failuje przy nieznanym typie.

### D-10. Katalog modeli JSONC

Plik wykonawczy: `config/anishift.models.jsonc` (ignorowany przez Git). Przykład w repo: `config/anishift.models.example.jsonc` bez sekretów.

```jsonc
{
  "schema_version": 1,
  "enrollment": { "base_url": "https://example.palantirfoundry.com" },
  "providers": {
    "foundry-openai": { "protocol": "openai_chat", "path": "/api/v2/llm/proxy/openai/v1" },
    "foundry-anthropic": { "protocol": "anthropic_messages", "path": "/api/v2/llm/proxy/anthropic/v1" },
    "foundry-google": { "protocol": "google_generate", "path": "/api/v2/llm/proxy/google/v1" },
    "foundry-xai": { "protocol": "xai_chat", "path": "/api/v2/llm/proxy/xai/v1" }
  },
  "models": {
    "foundry/gpt-main": {
      "provider": "foundry-openai",
      "model": "exact-model-id-or-rid",
      "label": "Foundry: model główny",
      "experimental": false,
      "limits": { "context": null, "input": null, "output": null }
    }
  },
  "defaults": { "primary": "foundry/gpt-main", "translation": "foundry/gpt-main" }
}
```

- Parser: `json5` dodany przez `uv add json5`. Jeżeli aktualny resolver nie wspiera Python 3.14/Windows, zadanie jest BLOCKED i wraca do D-10; zakaz własnego regexowego strippera komentarzy.
- Walidacja dataclass odrzuca nieznane protokoły, duplikaty aliasów, puste identyfikatory, brak providera i pola o nazwach sugerujących sekret.
- Początkowy przykład może zawierać sanityzowane aliasy z konfiguracji OpenCode użytkownika. Status dostępności nie jest zapisywany w katalogu; w nowej sesji każdy model zaczyna jako `niezweryfikowany`, dopóki jawny test połączenia nie potwierdzi inaczej.

### D-11. Adapter Palantir

Jeden registry ID `palantir`, jedna neutralna konfiguracja:

```python
@dataclass(frozen=True, slots=True)
class PalantirModelConfig:
    alias: str
    provider_id: str
    protocol: PalantirProtocol
    base_url: str
    provider_model_id: str
    token: str = field(repr=False)
```

- Token: najpierw `ANISHIFT_PALANTIR_TOKEN`; compatibility read `FOUNDRY_API_TOKEN`; zapis przez TUI wyłącznie do kanonicznej nazwy.
- `httpx.Client`/`AsyncClient` powstaje lazy przy complete/probe. Router tworzy headers/path/body zgodnie z protocol.
- Normalizer zwraca istniejący `LlmResponse` i usage, o ile provider je dostarcza.
- Klasyfikacja: auth, model/config, rate/quota, timeout, provider unavailable, blocked/output/context. Komunikat UI nie zawiera body/header/token.
- Dotychczasowi providerzy pozostają dostępni wewnętrznie; nowy picker produktu pokazuje wyłącznie modele katalogu Palantir.

### D-12. Role modeli i publiczna fasada

`UserSettings` otrzymuje `primary_model_alias`. Dla tłumaczenia pozostają `llm_provider` i `llm_provider_model_id`; przy `llm_provider="palantir"` model ID jest aliasem katalogu.

AppService dodaje:

```python
def model_catalog(self) -> ModelCatalog: ...
def save_model_catalog(self, catalog: ModelCatalog) -> None: ...
def probe_model(self, alias: str) -> ModelProbeResult: ...
```

- `/model` zmienia tylko primary alias.
- `/translation` zmienia provider i model tłumaczeniowy.
- Runtime rozwiązuje alias do konkretnego protocol/base URL/model ID przed LlmConfig.
- `/connect` wykonuje dokładnie jedno minimalne żądanie po potwierdzeniu i zapisuje status, czas oraz klasę błędu wyłącznie w stanie bieżącej sesji, nigdy w katalogu, odpowiedzi użytkowej ani sekrecie.

### D-13. Ekrany i przepływy

```text
START -> WORKSPACE
WORKSPACE --pusty Enter--> PLAN AUTO -> [confirm tylko gdy potrzeba] -> EXECUTION -> RESULTS
WORKSPACE --/auto--> AUTO CONFIG -> WORKSPACE
WORKSPACE --/manual--> MANUAL DRAFTS -> PREVIEW -> START -> EXECUTION -> RESULTS
RESULTS --Open in Manual--> MANUAL DRAFT nieudanej grupy
```

- Workspace nie uruchamia I/O poza jawnym refresh.
- Auto config nie uruchamia runu.
- Drafty Manual są niezależne dla każdego `group_id`; rejestracja pliku zewnętrznego odbywa się przez AppService w workerze.
- Preview renderuje ExecutionPlan bez duplikowania logiki planera.
- Execution renderuje RunEvent i umożliwia idempotentny cancel.
- Results zachowuje partial jako osobny stan i prowadzi do replanu.

### D-14. Event pump, błędy i redakcja

- `EventBuffer.drain()` działa co 75 ms podczas przebiegu. Postęp ma najwyżej 10 renderów/s na zadanie; zdarzenia terminalne trafiają do następnego tyknięcia timera.
- UI renderuje tylko `sanitize_event_message` i bezpieczne DTO. Nie renderuje `ErrorContext.details`, request/response body, promptów ani stderr.
- Status/debug operują allowlistą pól. Logi zawierają operation, provider/model alias, status, timing i count, ale nie treści.
- Każdy wykonawca ma terminalny message success/failure/cancel oraz generation.

### D-15. Responsywność i dostępność

- Pełny układ od 100x30; sterowalny fallback przy 80x24.
- Dialog szerokości `min(preset, terminal_width-2)` i wewnętrzny scroll.
- Tab order jest deterministyczny; `/` fokusuje composer, Esc zamyka modal/wraca, ctrl+p otwiera paletę, ctrl+q wyjście.
- Brak animacji wejścia. Timery działają tylko gdy ich stan jest widoczny.
- Każdy stan ma tekst; motyw 256-color pozostaje czytelny.

### D-16. Entrypoint i migracja legacy

1. Do T-024: `python -m anishift.tui` uruchamia TUI, `anishift` nadal legacy.
2. T-025: no args -> lazy launch TUI; doctor/setup/run pozostają nieinteraktywne.
3. T-026: tymczasowy parity test -> przeniesienie brakujących regresji -> usunięcie shell/pipeline/prompt-toolkit.
4. Po T-026 istnieje jedna produkcyjna ścieżka wykonania: AppService.

### D-17. Testowanie i bramki

- Unit: katalog, field access, registry, fuzzy, auto trigger, protocol mapping/normalization.
- Pilot: dialogi, composer, ustawienia, pickery, każdy ekran i pełne przepływy.
- Integracja: AppService z atrapami handlerów i transportu, parytet przed usunięciem legacy.
- Manual: T-009 wygląd; końcowy smoke Windows Terminal w T-027.
- Zero live network w domyślnym pytest. Probe testuje atrapa transportu; prawdziwy probe tylko z `/connect` po potwierdzeniu.

## 4. Plan wykonawczy

Ta sekcja jest właściwą instrukcją wykonawczą. `tasks.json` zawiera graf i lokalne kryteria, ale wykonawca przed rozpoczęciem zadania czyta odpowiadającą mu kartę poniżej. Karta jest kompletna decyzyjnie: wykonawca może dostosować nazwę prywatnego helpera do aktualnego repo, lecz nie może sam zmienić własności, publicznego kontraktu, zachowania użytkownika ani kolejności bramek.

### 4.1. Profile kontroli używane przez karty

**BRAMKA-UKIERUNKOWANA:** komendy wskazane w karcie zadania.

**BRAMKA-PEŁNA:**

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

Każde zadanie kodowe wykonuje najpierw BRAMKĘ-UKIERUNKOWANĄ, potem BRAMKĘ-PEŁNĄ. T-009 jest ręczną bramką bez commitu. Jeśli BRAMKA-PEŁNA ujawni błąd istniejący już w punkcie bazowym, wykonawca najpierw odtwarza go na bazowym commicie; nie przypisuje go automatycznie własnej zmianie.

## P-01 - Fundament i kontrolowany reset

### T-001 - Ustabilizować baseline i wyjście UTF-8

**Cel obserwowalny:** Potwierdzić aktualny stan gałęzi oraz zabezpieczyć wszystkie ścieżki CLI przed awarią kodowania na konsoli Windows.

**Zależności wykonawcze:** brak

**Najpierw przeczytaj:**
- `AGENTS.md`
- `anishift/cli/AGENTS.md`
- `anishift/setup/AGENTS.md`
- `anishift/cli/main.py`
- `anishift/setup/doctor.py`
- `anishift/utils/rich_console/`

**Zakres własności zadania:**
- `anishift/cli/main.py`
- `anishift/cli/console.py`
- `anishift/setup/doctor.py`
- `tests/cli/test_console.py`
- `tests/setup/test_doctor.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Nowy `anishift/cli/console.py` jest jedynym właścicielem rekonfiguracji strumieni.
- `configure_utf8_streams() -> None` jest idempotentne i toleruje strumienie bez `reconfigure`.
- `console_encoding_check() -> CheckResult` raportuje stan, ale nie blokuje działania CLI.

**Kolejność wykonania:**
1. Zapisz w Wynik zadania rzeczywisty branch, `HEAD`, wynik `git status --short` oraz różnicę kodu względem baseline. Dokumentacyjne commity po baseline nie wymagają replanu; zmiana publicznego API już tak.
2. Utwórz `anishift/cli/console.py`; iteruj wyłącznie po `sys.stdout` i `sys.stderr`, wywołuj `reconfigure(encoding="utf-8", errors="replace")` tylko gdy metoda istnieje i nie propaguj błędu dla strumienia testowego, którego nie da się rekonfigurować.
3. Wywołaj helper na początku `main()` przed pierwszym renderem Rich/Typer i przed komunikatem logera, ale nie na poziomie importu modułu.
4. Dodaj check kodowania do istniejącej listy `run_doctor`; OK dla UTF-8/UTF8/65001, WARN dla pozostałych z sugestią `chcp 65001` albo `PYTHONUTF8=1`.
5. W testach podstaw `TextIOWrapper` z cp1250 i znakiem niewspieranym; dowód ma obejmować faktyczną ścieżkę `_print_doctor_report`, nie sam helper.
6. Sprawdź, że `CliRunner().invoke(app, ["doctor"])` i `setup` nadal nie importują Textual.

**Przypadki brzegowe i pułapki:**
- `sys.stdout`/`stderr` może być `None`, StringIO albo wrapperem bez `reconfigure`.
- Uruchomienie testów przez bezpośredni import `app` omija `main`; test helpera i test ścieżki konsolowej muszą być rozdzielone.
- WARN doctora nie może zmieniać kodu wyjścia na failure.

**Lokalne kryteria akceptacji:**
- stdout i stderr są rekonfigurowane do UTF-8 z errors=replace, jeśli strumień udostępnia reconfigure.
- Raport doctor zapisany przez strumień cp1250 nie zgłasza UnicodeEncodeError.
- Doctor zwraca OK dla UTF-8/65001 i WARN z konkretną sugestią dla innych kodowań.
- Zmiana nie uruchamia Textual i nie zmienia dotychczasowego wejścia do legacy shell.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/cli/test_console.py tests/setup/test_doctor.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Potwierdzony baseline kodu.
- Bezpieczna granica UTF-8 używana później przez logo i glify TUI.
- Brak zmiany domyślnego entrypointu.

**Zakazy zadania:**
- Nie zmieniaj TUI, pipeline, providerów ani ustawień produktu.
- Nie zapisuj kodowania przez globalne monkeypatche bibliotek.

**Sugerowany commit:** `fix(cli): make console output safe on Windows code pages`

---

### T-002 - Usunąć odrzuconą warstwę TUI

**Cel obserwowalny:** Usunąć bieżący prototyp Textual i jego testy, pozostawiając działający legacy shell oraz nietknięty backend aplikacyjny.

**Zależności wykonawcze:** T-001

**Najpierw przeczytaj:**
- `anishift/tui/AGENTS.md`
- całe obecne `anishift/tui/`
- całe `tests/tui/`
- `anishift/cli/main.py`
- `git show 6849f32^..6849f32` dla reverta entrypointu

**Zakres własności zadania:**
- anishift/tui/**
- tests/tui/**
- `anishift/cli/main.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Legacy `run_shell()` pozostaje jedynym wejściem no-args do T-025.
- `anishift/application/` i `anishift/pipeline/` są nietykalne w tym zadaniu.
- Nowe TUI nie dziedziczy klas ekranów/widgetów ani `theme.tcss`; wzorce generation/EventBuffer/draftów wracają później jako nowa implementacja.

**Kolejność wykonania:**
1. Wykonaj `rg "anishift\.tui|from anishift import tui" anishift tests` i zapisz wszystkie realne call site’y.
2. Usuń stare pliki produkcyjne `anishift/tui/` oraz stare `tests/tui/`; nie kopiuj ich do katalogu `legacy`, `archive` ani `reference`.
3. Usuń martwe eksporty/importy wskazane przez grep. Nie dodawaj zastępczego placeholdera w produkcji.
4. Jeżeli Python package discovery lub test architektury wymaga istnienia pakietu, pozostaw wyłącznie minimalne `anishift/tui/__init__.py` bez importu Textual; w przeciwnym razie katalog może zostać odtworzony w T-003.
5. Uruchom `uv run anishift doctor`, `setup --help` i krótki smoke legacy shell, aby udowodnić, że reset prezentacji nie naruszył aktywnej ścieżki.
6. Pełne bramki muszą być zielone przed rozpoczęciem design systemu.

**Przypadki brzegowe i pułapki:**
- Nie usuwaj zależności `textual`; następne zadanie jej używa.
- Nie usuwaj testów aplikacji, które powstały razem z prototypem TUI, ale testują neutralne kontrakty.
- Nie modyfikuj reverta CLI, nawet jeśli nowy pakiet TUI chwilowo nie istnieje.

**Lokalne kryteria akceptacji:**
- Repozytorium nie zawiera produkcyjnych importów usuniętego anishift.tui.
- uv run anishift nadal otwiera legacy shell.
- doctor i setup nadal działają.
- Pełne bramki jakości pozostają zielone po usunięciu testów starej prezentacji.

**Weryfikacja ukierunkowana:**
- `rg 'anishift\.tui' anishift tests`
- `uv run anishift doctor`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Repo bez odrzuconej prezentacji.
- Lista jedynych zachowanych semantyk: `SessionState`/drafty, generation guard, EventBuffer drain, wykonawca thread; implementator T-004 odtwarza je z aktualnych kontraktów aplikacji, nie przez kopiowanie plików.

**Zakazy zadania:**
- Nie zmieniaj kontraktów AppService, planera, schedulera ani usług.
- Nie usuwaj prompt-toolkit ani legacy pipeline.

**Sugerowany commit:** `refactor(cli): remove the rejected Textual prototype`

---

## P-02 - Prototyp wizualny

### T-003 - Zbudować markę, motywy i responsywną ramę wizualną

**Cel obserwowalny:** Utworzyć semantyczny design system, statyczne logo ANISHIFT i style bazowe zgodne z ustaloną gramatyką.

**Zależności wykonawcze:** T-002

**Najpierw przeczytaj:**
- `spec.md` §6
- OpenCode `packages/tui/src/logo.ts`, `component/logo.tsx`, `routes/home.tsx`
- publiczne API `textual.theme.Theme` z wersji z locka
- `AGENTS.md` reguły stałych i docstringów

**Zakres własności zadania:**
- `anishift/tui/__init__.py`
- `anishift/tui/brand.py`
- `anishift/tui/theme.py`
- `anishift/tui/ui_state.py`
- `anishift/tui/styles/base.tcss`
- `anishift/tui/styles/screens.tcss`
- `tests/tui/test_brand.py`
- `tests/tui/test_theme.py`
- `tests/tui/test_ui_state.py`

**Kontrakty, które to zadanie ma ustanowić:**
- `theme.py` jest jedynym plikiem produkcyjnym TUI z literałami kolorów.
- Motywy mają stabilne ID `anishift-dark` i `anishift-light`.
- `brand.py` zwraca statyczny render pełny i kompaktowy; brak timera/animacji.
- `ui_state.py` przechowuje wyłącznie stan prezentacji, początkowo `theme`.

**Kolejność wykonania:**
1. Utwórz ponownie pakiet `anishift/tui/` oraz katalog `styles/`.
2. W `theme.py` zdefiniuj zamrożone palety dokładnie z wartości SPEC, mapę semantycznych zmiennych TCSS i `register_themes(app)`. Nie rozsiewaj `Color(...)` ani hexów po widgetach.
3. W `brand.py` zapisz jeden czterowierszowy wordmark `ANISHIFT`; renderer dzieli znaki na zakres `ANI` z tokenem muted i `SHIFT` z tokenem text/focus. Wariant compact to jednowierszowe `ANISHIFT`.
4. Dodaj czystą funkcję wyboru wariantu na podstawie wymiarów; poniżej progu funkcjonalne kontrolki mają pierwszeństwo przed logo.
5. W `ui_state.py` dodaj `UiState(theme: str)` oraz `load_ui_state`/`save_ui_state`; zapis `tmp -> replace`, nieznany motyw i zły JSON wracają do dark bez wyjątku.
6. Utwórz `base.tcss` i `screens.tcss` wyłącznie na zmiennych motywu. Zdefiniuj układ content/composer/footer, klasy compact i spacing bez pustych `Static`.
7. Testy mają sprawdzać dokładne ID motywów, round-trip UI state, brak hexów poza `theme.py`, stałą liczbę wierszy logo i wybór compact.

**Przypadki brzegowe i pułapki:**
- Szerokie znaki i emoji nie należą do logo; użyj znaków terminalowych o przewidywalnej szerokości.
- Plik `ui_state.json` leży obok `settings.json`, nie w workspace.
- Nie dodawaj trzeciego motywu, automatycznego wykrywania systemu ani OSC.

**Lokalne kryteria akceptacji:**
- Zarejestrowane są dokładnie dwa motywy: anishift-dark i anishift-light z paletami z wymagań.
- Logo ma pełny i kompaktowy wariant oraz nie zmienia szerokości podczas pracy.
- ui_state.json jest zapisywany atomowo i uszkodzony plik wraca do bezpiecznych wartości domyślnych.
- W żadnym TCSS nie ma literału koloru ani pustych wierszy użytych jako mechanizm layoutu.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_brand.py tests/tui/test_theme.py tests/tui/test_ui_state.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Gotowe tokeny i style bazowe dla wszystkich kolejnych komponentów.
- Stabilny wordmark do bramki wizualnej.
- Atomowy stan prezentacji niezależny od `UserSettings`.

**Zakazy zadania:**
- Nie twórz ekranu ustawień, palety, composera ani połączeń sieciowych.
- Nie dodawaj animacji, obrazów rastrowych, maskotki ani trzeciego motywu.

**Sugerowany commit:** `feat(tui): add the AniShift terminal design system`

---

### T-004 - Zbudować powłokę aplikacji i model stanu sesji

**Cel obserwowalny:** Utworzyć minimalną aplikację Textual z jednym właścicielem stanu, stałym obszarem treści, composerem-slotem i stopką-slotem.

**Zależności wykonawcze:** T-003

**Najpierw przeczytaj:**
- `spec.md` R-002, R-004, R-007, R-100, R-101
- `anishift/application/intents.py`
- `application/planning.py`
- `application/results.py`
- historyczna wersja `tui/state.py` tylko jako opis potrzebnych pól

**Zakres własności zadania:**
- `anishift/tui/app.py`
- `anishift/tui/state.py`
- `anishift/tui/lifecycle.py`
- `anishift/tui/messages.py`
- `anishift/tui/screens/__init__.py`
- `anishift/tui/screens/workspace.py`
- `anishift/tui/widgets/__init__.py`
- `anishift/tui/widgets/footer.py`
- `tests/tui/test_app_shell.py`
- `tests/tui/test_state.py`

**Kontrakty, które to zadanie ma ustanowić:**
- `AniShiftApp` jest jedynym właścicielem `SessionState`.
- Dozwolone route: `workspace`, `auto`, `manual`, `preview`, `execution`, `results`, `tools`; settings są dialogami, nie route.
- Stan runu ma jawne przejścia `idle -> planning -> running -> cancelling -> terminal`.
- Ekrany nie przechowują kopii globalnego run state ani aktywnego `run_id`.

**Kolejność wykonania:**
1. W `state.py` zdefiniuj `UiRoute` i `RunUiState` jako `StrEnum`, `GroupIntentDraft` zgodny z bieżącym `GroupIntent` oraz mały `SessionState` z workspace, selekcją, draftami, planem, aktywnym runem, wynikiem i generacjami.
2. Zachowaj konwersje `GroupIntentDraft.from_intent`, `clone_for` i `to_intent`; kolekcje mutable muszą być kopiowane głęboko.
3. W `lifecycle.py` umieść czyste operacje przejść stanu oraz decyzję, czy rezultat/event należy do aktualnej generacji. Nie umieszczaj logiki domenowej.
4. W `messages.py` utwórz typowane komunikaty prezentacyjne: nawigacja, wysłanie polecenia, żądanie Auto, workspace załadowany/błąd, plan gotowy/błąd, zdarzenia przebiegu, przebieg zakończony/błąd.
5. W `app.py` zbuduj powłokę z jednym hostem ekranu, stałym slotem composera i stopką. Na tym etapie host pokazuje poprawny empty state, nie tekst „coming later”.
6. Zaimplementuj resize: przełącz klasę compact bez przebudowy stanu i bez odmontowania composera.
7. Dodaj `footer.py`, który renderuje bezpieczną projekcję SessionState; skróty zostaną podłączone w T-005.
8. Pilot ma montować App bez AppService, sieci i systemu plików oraz sprawdzać nawigację, resize i zachowanie draftów.

**Przypadki brzegowe i pułapki:**
- Spóźniony komunikat z niższą generacją jest ignorowany.
- Zmiana route nie kasuje aktywnego runu ani draftów.
- Powrót z dialogu ma przywracać fokus elementowi, który go otworzył; ownership mechanizmu zostanie domknięty w T-006.

**Lokalne kryteria akceptacji:**
- Powłoka montuje się w App.run_test bez dostępu do sieci, narzędzi zewnętrznych i AppService.
- Zmiana 100x30 -> 80x24 nie powoduje wyjątku ani nakładania stałych obszarów.
- SessionState ma jawne pola route, focus, workspace, selected_groups, drafty, plan, run i result.
- Lifecycle przywraca fokus po zamknięciu warstwy modalnej.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_app_shell.py tests/tui/test_state.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Jednoznaczny model stanu i lifecycle.
- Powłoka gotowa na rejestr komend/dialogi/composer.
- Brak backendowych side effectów.

**Zakazy zadania:**
- Nie importuj konkretnych usług, providerów ani pipeline.
- Nie buduj własnego globalnego event loop poza Textual.

**Sugerowany commit:** `feat(tui): add the Textual application shell and session state`

---

### T-005 - Zbudować jeden rejestr komend, paletę i autocomplete

**Cel obserwowalny:** Wdrożyć jedno źródło prawdy dla dokładnie 14 komend, ich dostępności, skrótów, palety i slash autocomplete.

**Zależności wykonawcze:** T-004

**Najpierw przeczytaj:**
- `spec.md` §5, R-010..R-015
- OpenCode `command-palette.tsx` i keymap contract
- Textual `Binding`/`FuzzySearch` z wersji locka
- `tui/app.py` i `state.py` z T-004

**Zakres własności zadania:**
- `anishift/tui/commands/__init__.py`
- `anishift/tui/commands/spec.py`
- `anishift/tui/commands/registry.py`
- `anishift/tui/commands/catalog.py`
- `anishift/tui/commands/palette.py`
- `anishift/tui/app.py`
- `anishift/tui/widgets/footer.py`
- `tests/tui/test_command_registry.py`
- `tests/tui/test_palette.py`

**Kontrakty, które to zadanie ma ustanowić:**
- `CommandSpec` jest jedyną definicją nazwy, tytułu, opisu, kategorii, slash, aliasów, klawiszy i predykatów.
- `CommandRegistry.dispatch(name)` jest jedynym punktem wykonania komendy/akcji.
- Slash catalog ma dokładnie 14 nazw ze SPEC; akcje kontekstowe mają `slash_name=None`.
- Built-in command palette Textual jest wyłączona.

**Kolejność wykonania:**
1. Utwórz zamrożony `CommandSpec` z polami: `name`, `title`, `description`, `category`, `run`, `hidden`, `enabled`, `suggested`, `slash_name`, `slash_aliases`, `keys`.
2. W `registry.py` dodaj scope registration/unregistration, walidację duplikatów, lookup, `dispatch`, projekcję palette i slash. Predykaty oceniaj przy odczycie, nie przy rejestracji.
3. W `catalog.py` zapisz 14 globalnych komend oraz fabryki komend kontekstowych. Nie implementuj zachowania w katalogu; callbacks delegują do App/use-case handlers.
4. Ranking slash: normalizacja casefold, score z `textual.fuzzy`, prefiks x2, najlepszy score aliasu bez osobnego wpisu, stabilny tie-break po kolejności rejestracji/nazwie, limit 10.
5. Paleta używa `SelectDialog` dopiero po T-006; w tym zadaniu przygotuj adapter opcji i test jednostkowy. Integrację wizualną można zakończyć po merge T-006 bez drugiego registry.
6. App rejestruje globalne komendy raz; ekran rejestruje scope w mount i usuwa w unmount. Skróty i przyciski wołają `dispatch`, nie callback use case bezpośrednio.
7. Footer pobiera klawisze z registry/BINDINGS i renderuje tylko 4–5 najważniejszych aktywnych akcji.
8. Test negatywny ma dodać `/variant` do katalogu i wykazać czerwony guard dokładnego zbioru.

**Przypadki brzegowe i pułapki:**
- Disabled command nie pojawia się w palecie/slash, ale komenda naprawcza może pozostać enabled i po wybraniu pokazać konkretny missing state.
- Paleta nie może pokazywać komendy otwarcia samej palety.
- Alias nie zwiększa liczby widocznych pozycji.

**Lokalne kryteria akceptacji:**
- Rejestr odrzuca duplikaty nazw i pozwala rejestrować zakres globalny oraz zakres aktywnego ekranu.
- Paleta i slash pokazują wyłącznie enabled i visible commands.
- Fuzzy ranking preferuje prefiks, uwzględnia aliasy bez duplikowania wpisów i zwraca maksymalnie 10 sugestii w composerze.
- Help i stopka pobierają etykiety klawiszy z rejestru, nie z ręcznie wpisanego tekstu.
- Test potwierdza dokładny zbiór 14 slash commands oraz brak /variant.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_command_registry.py tests/tui/test_palette.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Jedno źródło prawdy komend i skrótów.
- Deterministyczny ranking dla composera i palety.
- Dokładnie 14 slash names.

**Zakazy zadania:**
- Nie dodawaj piętnastej komendy ani ukrytej alternatywnej ścieżki dispatch.
- Nie wykonuj use case bezpośrednio z widoku palety; zawsze przez registry.dispatch.

**Sugerowany commit:** `feat(tui): add the unified TUI command registry`

---

### T-006 - Zbudować wspólne prymitywy dialogowe

**Cel obserwowalny:** Dostarczyć jedną spójną ramę modalną oraz selektor, edytor wartości i edytor kolejności używane przez wszystkie domeny.

**Zależności wykonawcze:** T-003, T-004

**Najpierw przeczytaj:**
- `spec.md` R-030..R-034 i §6
- OpenCode `ui/dialog.tsx`, `ui/dialog-select.tsx`
- Textual `ModalScreen`, `OptionList`, `Input` public API
- `theme.py` i `lifecycle.py`

**Zakres własności zadania:**
- `anishift/tui/dialogs/__init__.py`
- `anishift/tui/dialogs/base.py`
- `anishift/tui/dialogs/select.py`
- `anishift/tui/dialogs/value.py`
- `anishift/tui/dialogs/reorder.py`
- `anishift/tui/styles/dialogs.tcss`
- `tests/tui/test_dialogs.py`

**Kontrakty, które to zadanie ma ustanowić:**
- W danym momencie istnieje najwyżej jeden dialog AniShift.
- `DialogScreen[T]` odpowiada za zasłonę, rozmiar, anulowanie i refocus; nie zna ustawień ani providerów.
- `SelectDialog[T]` jest jedynym selektorem listowym dla palety, modeli, głosów, promptów i ustawień.
- Dialog zwraca wynik; zapis/side effect należy do caller.

**Kolejność wykonania:**
1. Zdefiniuj `DialogSize` z szerokościami 60/88/116 i clamp `terminal_width - 2`; górna krawędź panelu w okolicy 1/4 wysokości.
2. W `base.py` zapamiętaj focus przed push, obsłuż click backdrop, Esc i Ctrl+C, a przy dismiss odtwórz fokus tylko gdy widget nadal istnieje.
3. Zdefiniuj `SelectOption[T]` (`value`, `title`, `description`, `footer`, `category`, `disabled`) oraz `SelectOutcome[T]` dla single/multi/action/cancel.
4. Select filtruje offline; przy pustym filtrze zachowuje kategorie/current, przy niepustym pokazuje płaski ranking. `current` ma marker niezależny od highlight.
5. Klawisze Select: up/down wrap, page ±10, home/end, Enter, Esc/Ctrl+C; multi używa Space do toggle i Enter do zatwierdzenia zbioru.
6. W `value.py` rozdziel Prompt i Number na dwa widgety/klasy w jednym module: tekst nie traci treści po błędzie; number pokazuje zakres, optional empty i krok przekazany przez spec.
7. Boolean nie potrzebuje osobnego modala, ale wspólny helper ma generować wynik toggle dla drzewa ustawień.
8. W `reorder.py` dodaj kursor, Shift+Up/Down move, add przez child select/prompt, delete z potwierdzeniem oraz commit/rollback całej listy.
9. Style dialogów używają wyłącznie tokenów; brak ciężkiej ramki i wielkich przycisków.
10. Pilot sprawdza realne keypressy/focus/dismiss, nie wywołuje handlerów prywatnych.

**Przypadki brzegowe i pułapki:**
- Wynik filtrowania pusty pokazuje `Brak wyników`, ale dialog pozostaje zamykalny.
- Disabled option nie może zostać zatwierdzona; decyzja czy ją ukryć czy pokazać z powodem jest własnością callera.
- Zmiana rozmiaru terminala podczas dialogu nie może wypchnąć panelu poza ekran.

**Lokalne kryteria akceptacji:**
- Dialog ma rozmiary medium/large/xlarge ograniczone do terminala minus 2 kolumny.
- Select obsługuje filtr, kategorie, current, disabled, single, multi, akcje i initial_highlight.
- Value editor obsługuje tekst, optional, int, float, boolean i walidację inline.
- Reorder obsługuje przesunięcie, dodanie, usunięcie, zatwierdzenie i rollback.
- Esc/ctrl+c anuluje i przywraca poprzedni fokus; Enter zatwierdza tylko poprawną wartość.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_dialogs.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Prymitywy używane bez forków przez wszystkie kolejne domeny.
- Jednoznaczny commit/rollback i refocus.
- Paleta T-005 może zostać podłączona bez nowego selektora.

**Zakazy zadania:**
- Nie twórz osobnych selektorów dla modeli, TTS, ustawień i palety.
- Nie zapisuj ustawień wewnątrz prymitywów; dialog zwraca wynik.

**Sugerowany commit:** `feat(tui): add reusable OpenCode-style dialog primitives`

---

### T-007 - Zbudować composer i dokładnie-jeden pusty Enter

**Cel obserwowalny:** Wdrożyć stały composer, slash popup i odporną na podwójne zdarzenia maszynę stanu pustego Enter.

**Zależności wykonawcze:** T-005, T-006

**Najpierw przeczytaj:**
- `spec.md` R-020..R-026, I-006..I-008
- `CommandRegistry` z T-005
- `SessionState` z T-004
- Textual `Input.Submitted` semantics

**Zakres własności zadania:**
- `anishift/tui/widgets/composer.py`
- `anishift/tui/auto_trigger.py`
- `anishift/tui/app.py`
- `anishift/tui/state.py`
- `tests/tui/test_composer.py`
- `tests/tui/test_auto_trigger.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Composer klasyfikuje submission na `EMPTY_AUTO`, `SLASH`, `PLAIN_TEXT`; klasyfikacja jest czysta.
- Auto trigger rezerwuje jedną generację przed uruchomieniem planning wykonawcy.
- Tylko `Input.Submitted` composera może uruchomić pusty Auto; globalny Enter nie ma takiego bindingu.
- Plain text nie emituje command ani use case.

**Kolejność wykonania:**
1. Utwórz `ComposerSubmissionKind` i czystą funkcję klasyfikacji po `strip()` oraz pierwszym znaku `/`.
2. Zbuduj widget composera z prefiksem `❯`, dokładnym placeholderem SPEC i popupem sugestii nad polem. Popup korzysta z `palette.slash_options(registry, query)`, nie z własnej listy.
3. Enter przy widocznym popupie wykonuje highlighted slash; Tab tylko uzupełnia nazwę; Esc chowa popup bez czyszczenia wartości.
4. W `auto_trigger.py` oprzyj rezerwację na maszynie run state z T-004; `reserve()` zwraca nową generation tylko wtedy, gdy bramka jest wolna, i od razu blokuje kolejne submission. Nie dodawaj drugiej maszyny stanu ani flagi obok `run_state`.
5. Po empty submit App publikuje `AutoRequested(generation)` i czyści pole dopiero po skutecznej rezerwacji.
6. Slash submit usuwa opcjonalny pierwszy `/`, rozwiązuje tylko `slash_name`, dispatchuje przez registry i czyści pole po rozpoznanej komendzie.
7. Unknown slash pozostawia aplikację bez side effectu i pokazuje jedną sugestię. Plain text pozostaje lub jest przywrócony w polu i dostaje krótki feedback o braku trybu rozmowy.
8. Release rezerwacji następuje przy plan failure/cancel przed runem albo po terminalnym run result; spóźniony release obcej generation nic nie robi.
9. Testy obejmują dwa Enter niemal jednocześnie, automatyczne powtarzanie klawisza, białe znaki, aktywny modal, planning/running/cancelling, Shift+Enter/paste i nieznany slash.

**Przypadki brzegowe i pułapki:**
- Nie stosuj debounce jako gwarancji exactly-once; może być tylko kosmetyczne.
- Puste Enter z composera bez zaznaczonych grup rozwiązuje selekcję zgodnie z T-018, nie tworzy drugiej ścieżki.
- IME nie jest obsługiwane przez surowy globalny Key handler, ponieważ trigger opiera się na zakończonym `Input.Submitted`.

**Lokalne kryteria akceptacji:**
- Whitespace-only + Enter publikuje jeden AutoRequested dla jednej generacji wejścia.
- Podwójny Enter, automatyczne powtarzanie klawisza, Enter podczas planning/running i spóźniony event nie tworzą drugiego runu.
- Slash command jest wykonywana przez rejestr; pusta komenda nie jest wysyłana do rejestru.
- Zwykły tekst nie wywołuje AppService ani side effectów.
- Shift+Enter, IME composition i paste nie są błędnie klasyfikowane jako pusty Auto.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_composer.py tests/tui/test_auto_trigger.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Gotowy composer i deterministyczny trigger do prototypu.
- Brak realnego `AppService`/planowania w tej fazie.
- Jednoznaczne messages dla T-016/T-018.

**Zakazy zadania:**
- Nie wywołuj prawdziwego AppService ani providerów.
- Nie dodawaj automatycznego startu z /auto ani z tekstu niebędącego slashem.

**Sugerowany commit:** `feat(tui): make empty Enter start exactly one Auto request`

---

### T-008 - Złożyć działający prototyp wizualny

**Cel obserwowalny:** Połączyć markę, powłokę, komendy, dialogi i composer w realny prototyp uruchamiany na Windows Terminal bez podłączania backendu.

**Zależności wykonawcze:** T-003, T-004, T-005, T-006, T-007

**Najpierw przeczytaj:**
- wyniki T-003..T-007
- `spec.md` AC-001..AC-011, AC-035
- `tests/tui/AGENTS.md`

**Zakres własności zadania:**
- `anishift/tui/__main__.py`
- `anishift/tui/app.py`
- `anishift/tui/screens/workspace.py`
- `anishift/tui/settings/__init__.py`
- `anishift/tui/settings/tree.py`
- `tests/tui/test_prototype_flow.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Prototyp dowodzi wyglądu i interakcji, nie kontraktów backendu.
- Tymczasowy launcher nie staje się domyślnym `anishift`.
- Prototyp ma te same produkcyjne widgety, które pozostaną po integracji.

**Kolejność wykonania:**
1. Dodaj `anishift/tui/__main__.py` jako jawny launcher prototypu albo tymczasowy `scripts/tmp/tui_prototype.py`; wybierz jedną drogę i zapisz ją w Wynik zadania. Preferencja: `python -m anishift.tui --prototype`, usuwając flagę w T-016.
2. Wstrzyknij mały, lokalny `PrototypeState`/callbacki wyłącznie na boundary launchera; nie dodawaj warstwy `TuiBackend` do produkcyjnej architektury.
3. Pokaż workspace z kilkoma syntetycznymi grupami, w tym selected/conflict/missing sidecar, aby ocenić gęstość i statusy.
4. Podłącz pełne logo/compact, composer, slash popup, Ctrl+P, `/tts` z 5–8 reprezentatywnymi polami, Number editor oraz `/theme` live preview.
5. Pusty Enter uruchamia jeden deterministyczny symulowany sequence `planning -> running -> result`; musi korzystać z prawdziwego auto trigger/state, ale nie z AppService.
6. Dodaj test Pilot przechodzący cały prototyp i resize 100x30/80x24.
7. Uruchom prototyp ręcznie w terminalu deweloperskim przed przekazaniem użytkownikowi; popraw oczywiste clipping/focus błędy, ale nie zmieniaj ustalonych decyzji produktu.
8. W Wynik zadania wypisz jedynie komendę uruchomienia i znane ograniczenia prototypu. Nie twórz raportu ani screenshot package.

**Przypadki brzegowe i pułapki:**
- Tryb demo ma być jawny w tytule/statusie, aby nie pomylić go z pipeline.
- Nie dodawaj placeholderów typu „ta funkcja powstanie później”; demo akcje mają faktyczne, ograniczone zachowanie.
- Nie buduj pełnego settings catalog przed bramką.

**Lokalne kryteria akceptacji:**
- python -m anishift.tui uruchamia pełnoekranowy prototyp bez legacy shell.
- Logo, composer, slash popup, paleta, /tts, edytor liczbowy i motyw działają klawiaturą.
- Pusty Enter pokazuje jeden spójny symulowany przebieg oraz wynik, bez drugiego startu.
- 80x24 pozostaje sterowalne, a 100x30 pokazuje pełny wariant.
- Pilot przechodzi reprezentatywny przepływ bez usług zewnętrznych.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_prototype_flow.py -q`
- `uv run python -m anishift.tui`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Jedna komenda do uruchomienia prototypu na Windows Terminal.
- Reprezentatywna mechanika gotowa do AC-HITL.
- Lista poprawek wyłącznie od użytkownika w T-009.

**Zakazy zadania:**
- Nie przełączaj jeszcze domyślnego entrypointu anishift.
- Nie importuj ProductionHandlerFactory, providerów ani plików mediów.

**Sugerowany commit:** `feat(tui): assemble the visual TUI prototype`

---

## P-03 - Bramka użytkownika

### T-009 - Przejść bramkę wizualną użytkownika

**Cel obserwowalny:** Uzyskać jawną akceptację prototypu na Windows Terminal przed podłączeniem backendu i rozbudową ekranów.

**Zależności wykonawcze:** T-008

**Najpierw przeczytaj:**
- `spec.md` §6 i AC-035
- Wynik zadania T-008

**Zakres własności zadania:**

**Kontrakty, które to zadanie ma ustanowić:**
- To ręczna bramka, nie zadanie kodowe.
- Brak jawnej akceptacji oznacza brak dispatchu T-010+.
- Poprawki wracają do właścicieli T-003..T-008 zamiast tworzyć nową warstwę.

**Kolejność wykonania:**
1. Uruchom prototyp na Windows Terminal w 100x30 i 80x24.
2. Przejdź klawiaturą: composer, slash popup, Ctrl+P, `/tts`, select, number, Esc/Enter, `/theme`, pusty Enter, `/exit`.
3. Sprawdź statyczne logo, różnicę ANI/SHIFT, brak wielkich kart, brak nakładania, widoczny focus/current marker, czytelność statusów bez polegania na kolorze.
4. Zbierz od użytkownika jednoznaczny wynik: zaakceptowane albo lista konkretnych poprawek.
5. Jeżeli poprawki są wymagane, zatrzymaj graf, zaadresuj je w odpowiednim tasku P-02 i powtórz całą bramkę.
6. Po akceptacji zapisz wyłącznie krótki fakt w runtime Wynik zadania/workflow state; nie modyfikuj planu ani nie twórz pliku raportu.

**Przypadki brzegowe i pułapki:**
- Akceptacja screenshotu z innego terminala nie zastępuje smoke użytkownika.
- Błąd funkcjonalny composera/dialogu jest poprawką P-02, nie „uwagą kosmetyczną”.

**Lokalne kryteria akceptacji:**
- Użytkownik jawnie zatwierdza kontynuację albo podaje poprawki.
- Wszystkie poprawki wizualne są wprowadzane w T-003..T-008 przed oznaczeniem tej bramki jako spełnionej.
- Bez akceptacji żadne zadanie zależne od T-009 nie startuje.

**Weryfikacja ukierunkowana:**
- `uv run python -m anishift.tui w Windows Terminal przy 100x30`
- `powtórzenie przy 80x24`
- `ręczne przejście: composer -> /tts -> edycja liczby -> Esc/Enter -> /theme -> pusty Enter`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Jawna zgoda na integrację backendu.
- Zamknięty wygląd podstawowych prymitywów; kolejne zadania nie przeprojektowują ich bez nowej decyzji użytkownika.

**Zakazy zadania:**
- Nie implementuj backendu ani nie omijaj bramki na podstawie screenshotu z innego terminala.
- Nie twórz osobnego raportu walidacyjnego; decyzja jest wpisem w rozmowie/Wynik zadania.

**Sugerowany commit:** brak commitu; bramka środowiska uruchomieniowego

---

## P-04 - Ustawienia i Foundry

### T-010 - Wydzielić dostęp do pól i atomowy zapis ustawień

**Cel obserwowalny:** Przenieść mapowanie SettingSpec <-> UserSettings do warstwy konfiguracji i udostępnić bezpieczną operację zmiany jednego pola przez AppService.

**Zależności wykonawcze:** T-009

**Najpierw przeczytaj:**
- `config/field_catalog.py` w całości
- `config/user_settings.py` w całości
- `config/env_file.py`
- `application/service.py`
- stare helpery `_setting_value/_assign_setting/_setting_is_active` z historii TUI

**Zakres własności zadania:**
- `anishift/config/field_access.py`
- `anishift/application/service.py`
- `anishift/config/user_settings.py`
- `anishift/config/env_file.py`
- `tests/config/test_field_access.py`
- `tests/config/test_env_file.py`
- `tests/application/test_settings_update.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Mapowanie `SettingSpec <-> UserSettings` należy do `config/field_access.py`, nie do TUI.
- `AppService.update_setting(setting_id, value)` jest atomową transakcją jednego pola.
- Sekret ma osobny kontrakt i nigdy nie jest elementem `UserSettings`.
- Aktywny `RunSettingsSnapshot` jest niezmienny po późniejszej zmianie preferencji.

**Kolejność wykonania:**
1. Utwórz `read_setting_value(settings, spec)`, `assign_setting_value(settings, spec, value)` i `setting_is_active(spec, settings)`; obsłuż pola top-level, listy/tuple/set, `elevenbytes_custom_voices`, `tts_profile.*` oraz `engine_options.*`.
2. Przenieś test cases ze starego SettingsScreen, ale nie importuj modułu TUI.
3. W AppService dodaj lookup spec po ID z bieżącego `settings_catalog(candidate)`; nie akceptuj nieaktywnego/nieistniejącego pola.
4. Dodaj `update_setting(setting_id: str, value: SettingValue) -> UserSettings`: snapshot, deepcopy, `spec.validate_value`, assign, `__post_init__`, saver, swap pod lockiem, zwrot deepcopy.
5. Dla secret scope dodaj osobny `update_environment_secret(setting_id, value, *, remove=False)` oparty na allowliście secret specs i `update_env_value`; wynik DTO zawiera tylko ID, configured i restart_required.
6. Nie próbuj podmieniać `_settings` aktywnego procesu po zapisie `.env`; status mówi `restart_required=True`. Probe T-015 może dostać świeży kandydat tokena jawnie.
7. Upewnij się, że zapis nie następuje przy błędzie żadnego etapu; test saver spy ma zero wywołań.
8. Testuj zmianę engine/voice i materializację profilu, listę fallback, custom voices, engine_options, złą wartość i concurrent snapshot runu.

**Przypadki brzegowe i pułapki:**
- Zmiana pola kontekstowego może sprawić, że kolejne pole stanie się nieaktywne; UI przebudowuje katalog po commicie.
- Sekret pusty nie jest automatycznie usuwany; remove ma oddzielną, potwierdzoną ścieżkę.
- AppService nadal może zachować `save_settings` dla CLI/testów; `update_setting` nie duplikuje serializacji.

**Lokalne kryteria akceptacji:**
- read_setting_value, assign_setting_value i setting_is_active pokrywają wszystkie istniejące SettingValueType.
- AppService.update_setting(setting_id, value) waliduje spec, post-init i zapis; przy błędzie nie zmienia pamięci ani dysku.
- Zmiana pola kontekstowego materializuje właściwy profil TTS i usuwa niezgodne engine_options zgodnie z UserSettings.
- Test udowadnia, że aktywny snapshot runu nie zmienia się po późniejszym zapisie preferencji.
- Aktualizacja lub usunięcie sekretu używa wyłącznie allowlisty pól SECRET, zapisuje atomowo do `.env` i zwraca DTO bez wartości sekretu.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/config/test_field_access.py tests/config/test_env_file.py tests/application/test_settings_update.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Publiczna, testowalna transakcja pojedynczego pola.
- UI-neutralny dostęp do wszystkich typów katalogu.
- Bezpieczny kontrakt sekretu dla T-011/T-015.

**Zakazy zadania:**
- Nie importuj Textual w config/application.
- Nie duplikuj walidacji SettingSpec w TUI.

**Sugerowany commit:** `feat(config): add atomic single-setting updates`

---

### T-011 - Podłączyć kompletne drzewa ustawień

**Cel obserwowalny:** Zastąpić prototyp /tts wspólnym dispatch edytorów i obsłużyć komplet aktywnych pól dla /auto, /translation, /prompts, /tts i /theme.

**Zależności wykonawcze:** T-010, T-005, T-006

**Najpierw przeczytaj:**
- `spec.md` R-040..R-048
- `field_catalog.py` i nowe `field_access.py`
- `AppService.update_setting/update_environment_secret`
- dialogi T-006
- `PromptRegistry`

**Zakres własności zadania:**
- `anishift/tui/settings/tree.py`
- `anishift/tui/settings/editors.py`
- `anishift/tui/settings/secrets.py`
- `anishift/tui/app.py`
- `tests/tui/test_settings.py`
- `tests/tui/test_settings_coverage.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Nie istnieje route ani slash `/settings`.
- Jedna fabryka editorów obsługuje każdy `SettingValueType` i jest współdzielona przez `/tts`, `/translation`, `/prompts`, Auto i Manual.
- Po commicie child dialog wraca do parent na edytowany wiersz; Esc wraca bez zapisu.
- Coverage test jest twardym guardem kompletności katalogu.

**Kolejność wykonania:**
1. Utwórz `settings/editors.py` z funkcją wyboru strategii po `SettingSpec.value_type`, `allowed_values`, `object_fields`, `is_secret`; zwracaj dialog/callback, nie zapisuj wewnątrz prymitywu.
2. Utwórz `settings/tree.py`, który bierze domain filter i snapshot, filtruje `scope`/`depends_on`, grupuje pola oraz buduje `SelectOption` z aktualnym podsumowaniem po prawej.
3. Zdefiniuj jawne mapy domen: TTS obejmuje silnik/model/głos/profile/audio; Translation obejmuje engine/fallback/batching/LLM model; Prompts obejmuje prompt/style/modules; Theme korzysta z UI state, nie SettingSpec.
4. Boolean przełączaj inline dopiero po potwierdzeniu Enter/Space; nadal wywołuje pojedyncze `update_setting`.
5. Object list custom voices: parent list aliasów + add/edit/remove; add/edit sekwencyjnie pyta o alias/label/voice_id, waliduje unikalność i commit całej tuple raz.
6. Secret row pokazuje tylko status; edycja ma puste pole, ustawienie zapisuje kanoniczny env key, usunięcie ma ConfirmDialog. Po sukcesie pokaż restart requirement.
7. Po zmianie `llm_provider`, `tts_engine`, `tts_provider_model_id`, `tts_voice_id` ponownie pobierz katalog i przebuduj parent.
8. Refaktoryzuj Auto/Manual później przez publiczną funkcję editor strategy; na tym etapie dodaj API pozwalające pracować z innym ownerem draftu niż `UserSettings`.
9. Coverage test iteruje reprezentatywne konteksty edge, elevenbytes run6/run7, elevenlabs, SAPI i każdy zwrócony spec musi mieć strategię.

**Przypadki brzegowe i pułapki:**
- Wolny string z patternem zachowuje wpis po błędzie.
- Optional numeric empty oznacza None, nie 0.
- Filtrowanie i movement nie wywołuje save ani network.
- Podsumowanie sekretu nigdy nie wywołuje `read_setting_value`.

**Lokalne kryteria akceptacji:**
- Każdy aktywny SettingSpec ma editor strategy; nieobsłużony typ powoduje czerwony test.
- Enter zatwierdza jedno pole i wraca na tę samą pozycję listy; Esc wraca bez zapisu.
- Zmiana tts_engine/model/voice odświeża zależne pola i zachowuje profile per głos.
- Sekret pokazuje missing/configured, nigdy wartość; po zmianie status środowiska jest odświeżony albo UI jawnie wymaga restartu zgodnie z wybraną implementacją AppService.
- Theme live preview cofa się po Esc i utrwala po Enter.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_settings.py tests/tui/test_settings_coverage.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Kompletne, domenowe drzewa ustawień bez monolitycznego formularza.
- Jedna fabryka editorów gotowa dla Auto/Manual.
- Dowód pokrycia wszystkich aktywnych speców.

**Zakazy zadania:**
- Nie twórz globalnego Save/Cancel ani wielkiego formularza.
- Nie uruchamiaj syntezy, tłumaczenia, model probe ani discovery przy przeglądaniu ustawień.

**Sugerowany commit:** `feat(tui): add dialog-driven per-field settings`

---

### T-012 - Wdrożyć lokalny katalog modeli JSONC

**Cel obserwowalny:** Dostarczyć wersjonowany, komentowalny katalog providerów i aliasów modeli Palantir bez sekretów oraz bez zgadywania dostępności enrollment.

**Zależności wykonawcze:** T-009

**Najpierw przeczytaj:**
- `spec.md` R-050..R-053
- dostępny faktycznie plik `opencode.corrected.jsonc`, jeśli wykonawca go otrzyma
- `config/user_settings.py` wzorzec atomowego zapisu
- PyPI/GitHub `json5` oraz wynik `uv` dla Python 3.14

**Zakres własności zadania:**
- `anishift/config/model_catalog.py`
- `config/anishift.models.example.jsonc`
- `.gitignore`
- `pyproject.toml`
- `uv.lock`
- `tests/config/test_model_catalog.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Runtime catalog to `config/anishift.models.jsonc`, repo example to `config/anishift.models.example.jsonc`.
- JSONC nie zawiera tokenu ani innych sekretów.
- Alias jest stabilnym ID użytkownika; provider model ID/RID jest wartością wysyłaną do proxy.
- Status dostępności jest sesyjny i nie jest zapisywany do catalog.

**Kolejność wykonania:**
1. Dodaj zależność wyłącznie `uv add json5`; nie edytuj ręcznie `pyproject.toml`/lock. Jeżeli resolver nie przechodzi na Python 3.14/Windows, zatrzymaj zadanie i przeplanuj zamiast pisać parser regex.
2. Zdefiniuj `ModelProtocol` z dokładnie czterema wartościami kontraktu oraz zamrożone DTO provider/model/catalog.
3. Przyjmij schema_version=1 i jawne root keys: `schema_version`, `enrollment_url`, `providers`, `models`; odrzucaj duplikaty aliasów/provider IDs i nieznane klucze, jeśli mogłyby ukryć literówkę kontraktu.
4. Provider entry przechowuje provider ID, protocol i relative proxy path; model entry przechowuje alias, provider ID, model ID/RID, label oraz bezpieczne metadata, np. context/output limits.
5. Waliduj HTTPS enrollment URL, relative route bez hosta, model-provider reference i role aliasy z UserSettings osobno.
6. Loader: brak pliku -> pusty poprawny catalog + actionable status; malformed -> typowany `ModelCatalogError` z bezpieczną lokalizacją względną.
7. Writer zapisuje deterministyczny JSON5/JSONC atomowo. Nie obiecuj zachowania komentarzy użytkownika, jeśli biblioteka tego nie zapewnia; w tym etapie TUI edytuje role, nie cały catalog.
8. Utwórz bezsekretowy example. Jeżeli `opencode.corrected.jsonc` nie jest dostępny, użyj strukturalnych placeholderów `replace-with-...`, nie wymyślaj RID-ów.
9. Dodaj `.gitignore` dla runtime catalog i testy load/validation/round-trip/malformed/secret canary.

**Przypadki brzegowe i pułapki:**
- Model publicznie znany, ale niewłączony w enrollment, pozostaje zwykłym lokalnym wpisem `unknown`.
- Nieznany protocol nie znika cicho; loader zwraca błąd konfiguracji.
- Enrollment URL nie może zawierać tokenu w query/fragment.

**Lokalne kryteria akceptacji:**
- ModelCatalog ma schema_version, enrollment.base_url, providers z protocol i relatywną path, models z aliasem/ID/etykietą/bezpiecznymi limitami oraz defaults; odrzuca duplikaty, nieznany provider, pusty model ID i nieobsługiwany protokół.
- Obsługiwane protokoły to openai_chat, anthropic_messages, google_generate i xai_chat.
- W katalogu nie ma pola token, api_key, authorization ani trwałego pola stanu dostępności.
- Brak/uszkodzony plik wykonawczy tworzy kopię bezpiecznego przykładu albo zwraca typowany błąd z instrukcją; nie nadpisuje cicho poprawnego pliku.
- Wczytanie i filtrowanie katalogu nie wykonuje sieci; status niezweryfikowany/zweryfikowany/błąd żyje w stanie bieżącej sesji TUI.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/config/test_model_catalog.py -q`
- `uv lock --check`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Typowany local model catalog.
- Bezsekretowy example i runtime path.
- Stabilne aliasy dla T-013..T-015.

**Zakazy zadania:**
- Nie umieszczaj tokena, nagłówków Authorization ani prywatnych RID-ów w przykładzie.
- Nie implementuj automatycznego GET /models ani live probe podczas load/filter.
- Nie edytuj pyproject.toml ręcznie; użyj uv add/uv remove.

**Sugerowany commit:** `feat(config): add the local Palantir model catalog`

---

### T-013 - Zbudować konfigurację, autoryzację i router protokołów Foundry

**Cel obserwowalny:** Utworzyć provider-neutralną konfigurację Palantir, pobieranie tokenu z env i bezpieczne routowanie żądań według protokołu katalogu.

**Zależności wykonawcze:** T-012

**Najpierw przeczytaj:**
- `services/llm/protocols.py`, `types.py`, `errors.py`, `_retry.py`
- existing OpenAI-compatible/Anthropic/Gemini adapters
- oficjalne Palantir provider-compatible proxy contracts wskazane w SPEC Basis
- `model_catalog.py`

**Zakres własności zadania:**
- `anishift/config/settings.py`
- `anishift/services/llm/engines/palantir/__init__.py`
- `anishift/services/llm/engines/palantir/config.py`
- `anishift/services/llm/engines/palantir/auth.py`
- `anishift/services/llm/engines/palantir/protocols.py`
- `anishift/services/llm/engines/palantir/errors.py`
- `tests/services/llm/test_palantir_config.py`
- `tests/services/llm/test_palantir_auth.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Warstwa transport/protocol nie implementuje `LlmEngine`; mapuje neutral request do jednego protokołu i surową odpowiedź do neutralnych danych.
- Authorization zawsze `Bearer <token>` budowane w jednym helperze.
- Base URL = znormalizowany enrollment URL; route pochodzi z validated provider entry.
- Response body/nagłówki nie trafiają do publicznego błędu.

**Kolejność wykonania:**
1. Utwórz pakiet `services/llm/engines/palantir/` z modułami `config`, `auth`, `http`, `protocols`, `normalize`, `errors`.
2. Zdefiniuj `PalantirConnectionConfig` (enrollment_url, provider route, protocol, model_id, token, timeout) z `repr=False` dla tokenu i walidacją połączenia URL+route.
3. W `auth.py` buduj allowlist headers; opcjonalne attribution/trace headers tylko jeśli mają bezpieczne wartości, nigdy z wejścia użytkownika bez walidacji.
4. W `protocols.py` zdefiniuj mapper per enum. Neutral `LlmMessage`/parts są źródłem; odrzuć kombinacje niewspierane zamiast po cichu tracić dane.
5. W `http.py` opakuj pojedynczy, wstrzykiwalny `httpx.Client`/transport, ustaw timeout, cancellation check przed/po request i limit odczytu błędnego body bez renderowania go.
6. W `normalize.py` mapuj text parts, usage, provider model ID i finish reason dla czterech protokołów. Brak wymaganych pól = `LlmRequestError`/błąd odpowiedzi dostawcy, nie KeyError.
7. Zbuduj klasyfikację HTTP: 401/403 auth, 404 model/route, 429 rate/quota według potwierdzonego payload marker bez ujawnienia body, timeout, 5xx unavailable, blocked output.
8. Fixtures testowe mają minimalne ręcznie zapisane odpowiedzi zgodne z oficjalnym shape; nie kopiuj prawdziwych response body użytkownika.
9. Test secret canary przeprowadza token przez config, request i wyjątek i sprawdza, że nie występuje w repr/str/log capture.

**Przypadki brzegowe i pułapki:**
- Provider route może mieć lub nie mieć końcowego slash; join nie może usuwać części ścieżki enrollment.
- Usage może być częściowe/brakujące; neutralny typ dostaje zera/None zgodnie z istniejącym kontraktem, nie zgadnięte liczby.
- xAI/Google beta nie zmieniają ogólnego retry; protocol mapper jest izolowany.

**Lokalne kryteria akceptacji:**
- Brak tokenu daje typowany błąd konfiguracji przed żądaniem sieciowym.
- Router wybiera builder/parser dla czterech protokołów i odrzuca nieznany protocol podczas load katalogu.
- Logi i str(error) nie zawierają tokenu, pełnego Authorization ani treść żądania.
- Konfiguracja nie tworzy klienta ani połączenia przed pierwszym complete/probe.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/services/llm/test_palantir_config.py tests/services/llm/test_palantir_auth.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Przetestowany transport i cztery mappers bez integracji registry.
- Bezpieczna klasyfikacja błędów.
- Wstrzykiwalny atrapa transportu dla T-014/T-015.

**Zakazy zadania:**
- Nie dodawaj tokena do JSONC, UserSettings, fixtures ani snapshotów.
- Nie wykonuj live requestu w testach domyślnych.

**Sugerowany commit:** `feat(llm): add Palantir proxy protocol adapters`

---

### T-014 - Dodać silnik Palantir do neutralnej warstwy LLM

**Cel obserwowalny:** Zaimplementować jeden lazy engine Palantir obsługujący cztery protokoły, normalizację odpowiedzi i klasyfikację błędów zgodną z LlmService.

**Zależności wykonawcze:** T-013

**Najpierw przeczytaj:**
- wynik T-013
- `services/llm/config.py`, `service.py`, `engines/__init__.py`, `protocols.py`
- `application/runtime.py` factory LLM/translation

**Zakres własności zadania:**
- `anishift/services/llm/engines/palantir/service.py`
- `anishift/services/llm/engines/palantir/http.py`
- `anishift/services/llm/engines/palantir/normalize.py`
- `anishift/services/llm/engines/__init__.py`
- `anishift/services/llm/config.py`
- `anishift/services/llm/service.py`
- `tests/services/llm/test_palantir_engine.py`
- `tests/services/llm/test_palantir_errors.py`

**Kontrakty, które to zadanie ma ustanowić:**
- `PalantirService` implementuje istniejący `LlmEngine` bez zmian kontraktu `LlmService`.
- Engine ID to stabilne `palantir`.
- Client jest lazy i zamykany idempotentnie.
- Retry pozostaje centralnie w `LlmService`; adapter nie dodaje drugiej pętli retry.

**Kolejność wykonania:**
1. Dodaj `palantir` do `LlmEngineId` i registry z lazy importem. `suggested_model_ids("palantir")` zwraca pustą tuple, bo źródłem modeli jest catalog.
2. Rozszerz `LlmConfig` minimalnie: albo typed `provider_options`/Palantir config, albo dedykowane pola potrzebne engine. Wybierz jedną ścieżkę bez wpychania catalog DTO do neutralnej warstwy; preferuj mały `extra: Mapping[str, JsonScalar]` tylko jeśli istniejące typing/serialization to akceptuje.
3. Zaimplementuj `PalantirService` tworzący transport dopiero przy pierwszym `complete` i delegujący mapping/normalize z T-013.
4. `is_available` dla Palantir wymaga tokenu, enrollment, route, protocol i model ID; nie wykonuje requestu.
5. Mapuj błędy adaptera na istniejące klasy `LlmAuthError`, `LlmModelError`, `LlmRateLimitError`, `LlmQuotaError`, `LlmTimeoutError`, `LlmProviderUnavailableError`, `LlmOutputBlockedError`, `LlmRequestError`.
6. Zachowaj observer/retry/cancel behavior `LlmService`; test integracyjny ma wymusić transient 5xx -> retry przez centralną warstwę.
7. Sprawdź, że wszystkie dotychczasowe engine IDs i tests pozostają bez zmian.
8. Dodaj eksporty wyłącznie w publicznych `services/llm/__init__.py` tam, gdzie potrzebne; TUI nadal nie importuje engine.

**Przypadki brzegowe i pułapki:**
- Nie twórz po jednym engine ID na protokół.
- Nie interpretuj aliasu jako provider model ID; resolution nastąpi w runtime T-015/T-016.
- Close przed first request i podwójny close muszą być bezpieczne.

**Lokalne kryteria akceptacji:**
- Każdy protokół ma hermetyczny test request mapping oraz response normalization.
- 401/403 -> auth, 404/model errors -> model/config, 408/timeout -> timeout, 429 -> rate/quota, 5xx -> provider unavailable; komunikaty są bezpieczne.
- Streaming response może zostać zebrany do neutralnej odpowiedzi bez przecieku surowych chunków do UI.
- Engine jest lazy, close jest idempotentne, cancellation jest respektowane między próbami.
- Pełne istniejące testy LLM pozostają zielone.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/services/llm/test_palantir_engine.py tests/services/llm/test_palantir_errors.py tests/services/llm -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Palantir jest pełnoprawnym neutralnym LLM engine.
- Existing providers bez regresji.
- Runtime może zbudować config z aliasu catalog.

**Zakazy zadania:**
- Nie usuwaj ani nie przepisuj istniejących adapterów Anthropic/Gemini/OpenAI/OpenRouter/DeepSeek.
- Nie loguj payloadu, promptu, tekstu napisów ani kompletnej odpowiedzi providera.

**Sugerowany commit:** `feat(llm): register Palantir as a provider-neutral engine`

---

### T-015 - Podłączyć role modeli, picker, /connect i prompty

**Cel obserwowalny:** Dodać niezależny wybór modelu głównego i tłumaczeniowego, picker oparty na katalogu oraz jawny test połączenia.

**Zależności wykonawcze:** T-011, T-012, T-014

**Najpierw przeczytaj:**
- `UserSettings`, `field_catalog`, `AppService`, `bootstrap`, `application/runtime.py`
- model catalog T-012
- Palantir engine T-014
- dialogi/settings tree

**Zakres własności zadania:**
- `anishift/config/user_settings.py`
- `anishift/config/field_catalog.py`
- `anishift/application/service.py`
- `anishift/tui/models/__init__.py`
- `anishift/tui/models/picker.py`
- `anishift/tui/models/connect.py`
- `tests/config/test_model_settings.py`
- `tests/tui/test_model_picker.py`
- `tests/tui/test_connect.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Persisted roles: `primary_model_alias` i `translation_model_alias`; obie opcjonalne przy pustym catalog.
- Alias jest rozwiązywany do provider/protocol/model przed utworzeniem `LlmConfig`.
- `/model` modyfikuje tylko primary; `/translation` tylko translation.
- `/connect` jest jedynym live probe i wykonuje maksymalnie jedno żądanie po Confirm.

**Kolejność wykonania:**
1. Dodaj dwa pola do `UserSettings` z backward-compatible load/save; brak starych keys daje None albo pierwszy jawnie skonfigurowany default tylko jeśli catalog wskazuje role - nie wybieraj losowo.
2. Dodaj `SettingSpec`/kategorie dla modelu tłumaczeniowego i ewentualnie provider Palantir; primary model pozostaje domeną `/model`, ale persistence korzysta z tego samego user settings transaction.
3. W bootstrap załaduj model catalog raz i wstrzyknij do AppService/runtime przez neutralny resolver, nie przez global singleton.
4. Dodaj publiczne DTO i metody AppService: `model_catalog_snapshot`, `model_statuses`, `select_primary_model(alias)`, `select_translation_model(alias)`, `probe_model(alias, token_candidate=None)`; żadna nie zwraca tokenu ani raw response.
5. Model status w sesji jest mapą alias -> unknown/verified/error + bezpieczny reason; nie zapisuj jej do JSONC/UserSettings.
6. Zbuduj picker `/model` na SelectDialog z provider category, current marker i status footer. Empty catalog prowadzi do `/init`/instrukcji pliku, nie do crasha.
7. W `/translation` połącz istniejące pola translation/LLM z niezależnym pickerem aliasu; po commit nie zmieniaj primary.
8. `/prompts` wykorzystuje istniejący `PromptRegistry` i wspólne editory; nie dodawaj edycji surowego promptu.
9. `/connect` prowadzi: enrollment URL -> token (puste, bez pokazywania starego) -> model alias -> podsumowanie bez sekretu -> Confirm kosztu/limitu -> jeden probe w workerze. Token candidate może być użyty tylko do tego requestu i zapisany dopiero po osobnym zatwierdzeniu.
10. W `application/runtime.py` rozwiąż translation alias do Palantir config tylko gdy selected LLM provider/engine tego wymaga; primary model nie wchodzi jeszcze do pipeline, ale status/persistence ma być gotowy dla przyszłego agenta.
11. Testuj niezależność ról, nieznany alias, brak tokenu, jednowywołaniowy test połączenia, cancel, brak sieci podczas przeglądania oraz redakcję.

**Przypadki brzegowe i pułapki:**
- Zmiana catalog na dysku po starcie nie zmienia bieżącego snapshotu bez jawnego reload/init.
- Wybrany alias usunięty z catalog jest widoczny jako invalid i blokuje tylko ścieżkę, która go potrzebuje.
- Probe nie może zmieniać roli modelu ani uruchamiać tłumaczenia pliku.

**Lokalne kryteria akceptacji:**
- /model pokazuje alias, etykietę, dostawcę, protokół i sesyjny stan dostępności oraz zapisuje wyłącznie primary_model_alias.
- /translation pozwala niezależnie ustawić dostawcę i model tłumaczeniowy bez zmiany modelu głównego.
- /prompts edytuje istniejące pola promptu zadania, stylu i modułów przez wspólne dialogi.
- /connect wybiera dokładnie jeden model, pokazuje ostrzeżenie o żądaniu i wykonuje maksymalnie jeden minimalny test po potwierdzeniu.
- Sukces testu ustawia stan `zweryfikowany` z czasem wyłącznie w bieżącej sesji; błąd ustawia `błąd` z bezpieczną klasą bez sekretu i treści odpowiedzi.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/config/test_model_settings.py tests/tui/test_model_picker.py tests/tui/test_connect.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Dwie niezależne role modelowe i gotowe UI.
- Publiczna bezpieczna fasada catalog/status/probe.
- Runtime translation potrafi zbudować Palantir LlmConfig.

**Zakazy zadania:**
- Nie wykonuj probe przy wejściu do /model, /translation, /status ani przy filtrze.
- Nie uznawaj wpisu z przykładu za dostępny bez probe albo jawnego statusu enrollment.
- Nie dodawaj /variant.

**Sugerowany commit:** `feat(tui): connect Palantir model roles to settings and the TUI`

---

### T-016 - Podłączyć TUI do AppService i zdarzeń wykonania

**Cel obserwowalny:** Zastąpić dane prototypowe prawdziwym composition root, wykonawcymi Textual, EventBuffer i bramką generacji/run ID.

**Zależności wykonawcze:** T-010, T-014, T-015

**Najpierw przeczytaj:**
- `AppService` pełne API
- `bootstrap.create_app_service`
- `application/events.py`
- powłoka/state/messages T-004/T-007
- stary `tui/app.py` tylko dla EventBuffer pattern

**Zakres własności zadania:**
- `anishift/bootstrap.py`
- `anishift/application/service.py`
- `anishift/application/runtime.py`
- `anishift/tui/app.py`
- `anishift/tui/workers.py`
- `anishift/tui/messages.py`
- `anishift/tui/state.py`
- `tests/tui/tui_fakes.py`
- `tests/tui/test_app_service_wiring.py`
- `tests/tui/test_event_pump.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Produkcja `AniShiftApp` wymaga `AppService`; prototype-only adapter zostaje usunięty.
- Każde blokujące wywołanie AppService działa w Textual wykonawca thread.
- App drenuje `EventBuffer` na timerze tylko podczas runu.
- Generation i `run_id` filtrują late results/events.

**Kolejność wykonania:**
1. Zmień konstruktor App na `AniShiftApp(service: AppService, workspace_label: str)` i usuń prototype conditionals z produkcyjnych widgetów.
2. W `workers.py` skonsoliduj wywołania discovery, external registration, planning, execution, doctor/setup/probe; wykonawca zwraca typed message z generation.
3. App przechowuje aktywny `EventBuffer`; timer 75–100 ms startuje paused, resume przy run, pause po terminalnym wyniku.
4. Przy zdarzenia przebiegu najpierw sprawdź UI generation, potem ustal/porównaj active run ID; sort sequence jest własnością EventBuffer.
5. Execution wykonawca łapie boundary exception, używa `sanitize_event_message` i publikuje `RunFailed`; nie łapie błędu w ekranie.
6. Start planning i start execution są osobnymi operacjami state machine; second request w reserved/planning/running zwraca false bez uruchomienia wykonawcy.
7. Bootstrap TUI odbywa się przez istniejące `bootstrap()` + `create_app_service()` w prototype launcher na razie; default CLI dopiero T-025.
8. Usuń tymczasowy symulowany przebieg T-008 i jego launcher/flagę, jeśli nie jest potrzebna do testów. Testy używają atrapy AppService na publicznym API.
9. Dodaj architecture assertion, że TUI nie importuje `anishift.services` ani `anishift.pipeline`.

**Przypadki brzegowe i pułapki:**
- Czy `RUN_STARTED` może dotrzeć po kilku zdarzeniach? Zgodnie z kontraktem sekwencją emitera powinien zaczynać od niego; nie zgaduj run ID z zdarzenia zadania.
- Run kończy się, zanim timer zdąży drain; wykonawca przed RunCompleted robi końcowy drain.
- Zamknięcie aplikacji podczas wykonawcy nie może wywołać UI mutation z martwego wątku.

**Lokalne kryteria akceptacji:**
- Production bootstrap tworzy AppService raz i przekazuje go do AniShiftApp.
- Discovery, register external, doctor, setup, plan i execute nie blokują wątku UI.
- Każdy wynik wykonawcy niesie generation; zdarzenia runu dodatkowo run_id; obce/stare wyniki są ignorowane.
- Postęp jest koalescowany, terminalne zdarzenia nie są opóźniane, a EventBuffer nie rośnie bez ograniczeń.
- Wyjątek procesu jest sanityzowany przed notify/result.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_app_service_wiring.py tests/tui/test_event_pump.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Produkcja TUI podłączona do jednej AppService boundary.
- Gotowy event pump i wykonawca coordinator.
- Kolejne ekrany implementują tylko projekcję/use-case calls.

**Zakazy zadania:**
- Nie wywołuj blocking AppService na wątku UI.
- Nie importuj anishift.services ani anishift.pipeline z anishift/tui.

**Sugerowany commit:** `feat(tui): wire the Textual shell to AppService`

---

## P-05 - Pełny produkt

### T-017 - Zbudować prawdziwy ekran workspace

**Cel obserwowalny:** Wyświetlić odkryte grupy, konflikty, sidecary i produkty oraz zapewnić stabilną selekcję i odświeżanie.

**Zależności wykonawcze:** T-016

**Najpierw przeczytaj:**
- `application/discovery.py`, `inspection.py`, `selection.py`
- `InspectedWorkspace/InspectedSourceGroup`
- historyczne testy i semantyka GroupTable
- T-016 wykonawca API

**Zakres własności zadania:**
- `anishift/tui/screens/workspace.py`
- `anishift/tui/widgets/group_table.py`
- `tests/tui/test_workspace.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Workspace jest route startowym i jedynym ownerem selection UI.
- Discovery i inspekcja zawsze działają w workerze; tabela nie czyta systemu plików.
- Selection key to stabilne `group_id`, nie indeks wiersza.
- Refresh zachowuje intersection starych selected IDs z nowymi groups.

**Kolejność wykonania:**
1. Zbuduj `GroupTable` na `DataTable` z row key=group_id i minimalnym zestawem pełnych kolumn: selected, natural name/stem, source kind, subtitle/audio summary, conflicts/status.
2. Natural sort używa już dostępnego `natsort`; filtr/sort nie zmienia selected set.
3. Przy mount, jeśli SessionState nie ma workspace, uruchom discovery i pokaż `Skanowanie workspace…`; przy refresh zwiększ inspection generation.
4. Po sukcesie podmień workspace tylko dla aktualnej generation, zachowaj selection intersection. Jeśli selection pusta po pierwszym discovery, domyślnie zaznacz wszystkie poprawne groups; konfliktowe pozostają widoczne, ale nie muszą być zaznaczone.
5. Space toggluje bieżącą group; akcja select all/clear może być kontekstowa, bez slash.
6. Panel szczegółów pokazuje artifacts/tracks/conflicts dla highlighted group; w compact mode jest ukryty lub otwierany Enter.
7. Błąd discovery daje bezpieczny feedback i akcję retry; nie kasuje poprzedniego poprawnego workspace przy nieudanym refresh.
8. Dodaj BINDINGS: a/m/s? Ustal zgodnie z command registry, ale nie twórz `/refresh`; `r` dispatchuje contextual refresh.
9. Testy: zero/1/100 groups, natural ordering, selection persistence, stale refresh ignored, input responsiveness podczas slow inspector.

**Przypadki brzegowe i pułapki:**
- Generated durable products nie mogą być rediscovered jako nowe source groups - to istniejący kontrakt discovery, którego test pozostaje zielony.
- Group usunięta z workspace znika też z manual_drafts albo draft jest oznaczony stale; wybierz usunięcie przy refresh, bo intent bez group nie może być planowany.
- Conflict text musi być zredagowany i względny.

**Lokalne kryteria akceptacji:**
- Tabela pokazuje zaznaczenie, nazwę, główne źródło, artefakty, wykryty stan oraz konflikt/ostrzeżenie słowem i glifem.
- Space przełącza grupę, zaznaczenie przeżywa sortowanie i refresh dla nadal istniejących group_id.
- Usunięta grupa znika z selekcji; nowa nie jest automatycznie zaznaczana poza jawną polityką Select all.
- Spóźniony refresh poprzedniej generacji nie nadpisuje nowszego workspace.
- 100 grup przewija się i filtruje bez blokującego I/O.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_workspace.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Prawdziwy, responsywny workspace i selection.
- Stabilne group IDs dla Auto/Manual.
- Contextual refresh działający przez registry.

**Zakazy zadania:**
- Nie uruchamiaj planowania ani pipeline przy zaznaczeniu lub refresh.
- Nie używaj ścieżek absolutnych jako etykiet głównych ani ID.

**Sugerowany commit:** `feat(tui): rebuild the workspace route`

---

### T-018 - Zbudować konfigurację i wykonanie Auto

**Cel obserwowalny:** Podłączyć presety Auto do wybranych grup oraz pusty Enter do bezpośredniego planowania i startu bez zbędnego formularza.

**Zależności wykonawcze:** T-017, T-011, T-007

**Najpierw przeczytaj:**
- `config/presets.py`, `AutoPresetDraft`, `ProductIntent`
- `AppService.list/get/save_preset`, `plan_auto`
- settings editors T-011
- auto trigger T-007

**Zakres własności zadania:**
- `anishift/tui/screens/auto.py`
- `anishift/tui/auto_trigger.py`
- `anishift/tui/app.py`
- `tests/tui/test_auto.py`

**Kontrakty, które to zadanie ma ustanowić:**
- `/auto` edytuje preset/draft i nigdy nie uruchamia planning.
- Pusty Enter rozwiązuje selected groups + default preset i uruchamia planning.
- Normalny wykonalny Auto może przejść bez dodatkowego Preview do Execution; ryzykowny/blokujący plan trafia do Preview.
- Default preset ID pochodzi z preset file, nie hardcoded UI poza fallbackem istniejącego API.

**Kolejność wykonania:**
1. Zbuduj Auto route/dialog pokazujący listę presetów z current/default, akcje edit, save as/update, reset i preview once.
2. Mapuj 8 pól AUTO_PRESET przez wspólną fabrykę editorów, ale commituj do `AutoPresetDraft`, nie do globalnego `UserSettings`.
3. Przy pustym Enter pobierz selection; jeśli workspace istnieje i selected puste, użyj jawnej domyślnej polityki: wszystkie groups bez blocking conflict. Jeżeli nadal pusto, release trigger i pokaż instrukcję.
4. Pobierz default preset przez `list_presets`/file default contract; nie zakładaj nazwy poza stable ID API.
5. Uruchom `plan_auto` w workerze z generation rezerwacji. Zapisz plan w SessionState tylko jeśli generation nadal aktualna.
6. Klasyfikuj plan: blocking -> Preview z problemami; overwrite/paid/destructive -> Preview/Confirm; zwykły safe -> bezpośrednio `start_execution(plan)`.
7. Przycisk/akcja Preview w Auto zawsze pokazuje Preview i nigdy nie execute.
8. Save preset waliduje draft przez `to_preset`; błąd pozostaje w Auto.
9. Testuj, że `/auto` wykonuje zero `plan_auto`; empty Enter dokładnie jedno; safe plan execute, risky plan preview, no groups release, double Enter guard.

**Przypadki brzegowe i pułapki:**
- `translation_is_paid`/`tts_is_paid` w snapshot może oznaczać koszt; potwierdzenie ma wynikać z plan metadata/problems, nie z nazwy engine w UI.
- Zmiana global settings po zbudowaniu planu nie zmienia immutable plan.
- Preset delete nie jest wymagany, jeśli istniejący API go nie obsługuje.

**Lokalne kryteria akceptacji:**
- /auto listuje presety, pozwala wybrać domyślny, edytować pola AUTO_PRESET, zapisać, zresetować i wrócić bez startu.
- Pusty Enter rezerwuje trigger, tworzy plan w workerze i przy planie bez blockerów/destrukcji przechodzi bezpośrednio do execution.
- Jeśli plan ma blocker, UI wraca z problemami bez startu; jeśli wykryto nową operację destrukcyjną/nadpisanie, pokazuje ConfirmDialog.
- Podwójny Enter nie wywołuje drugiego plan_auto ani execute.
- Zmiana default preset jest atomowo zapisana i widoczna po restarcie.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_auto.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Pełna konfiguracja Auto i domyślna ścieżka one-key.
- ExecutionPlan w SessionState dla Preview/Execution.
- Dokładnie jedna ścieżka planningu Auto.

**Zakazy zadania:**
- Nie dodawaj globalnego formularza Auto ani obowiązkowego Preview dla bezpiecznego domyślnego Auto.
- Nie uruchamiaj z /auto, wyboru presetu ani samego zapisu.

**Sugerowany commit:** `feat(tui): implement the default Auto workflow`

---

### T-019 - Zbudować workflow Manual i rejestrację źródeł

**Cel obserwowalny:** Zapewnić niezależne drafty intencji per grupa, wybór artefaktów/tracków i bezpieczną rejestrację plików zewnętrznych.

**Zależności wykonawcze:** T-017, T-011

**Najpierw przeczytaj:**
- `GroupIntent` i related enums
- `AppService.register_external_*`, `plan_manual`
- `InspectedSourceGroup` artifact/track contracts
- GroupIntentDraft T-004
- settings editors T-011

**Zakres własności zadania:**
- `anishift/tui/screens/manual.py`
- `tests/tui/test_manual.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Każda group ma niezależny `GroupIntentDraft`.
- Copy to selected wykonuje deep clone wartości, ale ustawia docelowy group_id i nie kopiuje artifact/track IDs, które nie należą do docelowej group.
- Rejestracja pliku zewnętrznego zawsze odbywa się przez AppService w workerze.
- Manual nigdy nie execute bez Preview+Start.

**Kolejność wykonania:**
1. Po wejściu utwórz brakujące drafty dla selected groups z bezpiecznych defaultów; zachowaj istniejące drafty tej samej group.
2. Layout duży: lista groups + pola wybranej group; compact: jedna lista i osobny detail view.
3. Użyj wspólnych editorów dla `MANUAL_RUN` speców i product intent collections. Caller przypisuje wynik do draftu, nie do `UserSettings`.
4. Opcje artifact/track generuj wyłącznie z aktualnego `InspectedSourceGroup`; pokaż ID/label/language/codec, ale nie pełne ścieżki.
5. Register external subtitle/audio: Prompt path/role/language, wykonawca AppService, generation guard; po sukcesie zastąp group w workspace i zaktualizuj opcje draftu.
6. Copy to selected kopiuje semantyczne wybory produktów/polityk; source-specific IDs czyść, chyba że taki sam artifact ID realnie istnieje w target group.
7. Podgląd materializuje `to_intent()` dla wszystkich wybranych grup i wywołuje `plan_manual` w workerze; każdy lokalny błąd walidacji jest przypisany do group.
8. Back zachowuje drafty w sesji; refresh usuwający group usuwa jej draft.
9. Testy obejmują 3 groups, independent sets, copy isolation, invalid artifact/track, external registration late result i obowiązkowy Preview.

**Przypadki brzegowe i pułapki:**
- Nie można jednocześnie wybrać artifact i embedded track tego samego rodzaju; `GroupIntent` waliduje, UI ma zapobiegać i pokazać błąd.
- Ścieżka zewnętrzna może być poza workspace; AppService nadaje stabilny ID.
- Manual dla jednej failed group z Results nie może nadpisać draftów pozostałych.

**Lokalne kryteria akceptacji:**
- Każda grupa ma niezależny draft; przełączenie grupy nie gubi zmian.
- Copy to selected kopiuje wartości, ale nie współdzieli mutowalnego obiektu.
- Sprzeczne artifact ID/track ID są blokowane przed plan_manual.
- Spóźniony wynik rejestracji pliku nie zmienia draftu po zmianie generacji lub grupy.
- Akcja Podgląd materializuje kompletny zestaw GroupIntent dla wybranych grup; Manual nigdy nie startuje bez Preview.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_manual.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Kompletne, niezależne intencje Manual.
- Jedna lista intents dla plan_manual.
- Bezpieczne external registration.

**Zakazy zadania:**
- Nie czytaj plików mediów bezpośrednio w TUI.
- Nie współdziel jednej instancji draftu między grupami.

**Sugerowany commit:** `feat(tui): implement independent manual group intents`

---

### T-020 - Zbudować Preview i bezpieczną bramkę Start

**Cel obserwowalny:** Renderować pełny plan wykonania, blockery, koszty i nadpisania oraz dopuścić Start wyłącznie dla poprawnego planu.

**Zależności wykonawcze:** T-018, T-019, T-006

**Najpierw przeczytaj:**
- `ExecutionPlan`, group plans, problems, tasks, artifacts
- `PlanView` historyczny tylko jako dane do pokazania
- ConfirmDialog T-006
- App start_execution T-016

**Zakres własności zadania:**
- `anishift/tui/screens/preview.py`
- `anishift/tui/widgets/plan_view.py`
- `anishift/tui/app.py`
- `tests/tui/test_preview.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Preview renderuje plan, nie rekonstruuje decyzji planera.
- Start jest enabled wyłącznie dla `plan.can_execute` i braku aktywnego runu.
- Potwierdzenie jest wymagane dla nadpisania/destrukcyjnego/płatnego skutku określonego przez plan, nie przez zgadywanie ekranu.
- Double Start nie może wywołać drugiego execute.

**Kolejność wykonania:**
1. Zbuduj `PlanView` grupujący plan per source group: wybrane źródła, operations w topological order, planned products, reuse/skip, warnings/problems i relative destinations.
2. Pokaż blocking problems na górze i wyłącz Start. Dla nonblocking warnings Start pozostaje możliwy.
3. Wylicz listę skutków wymagających potwierdzenia na podstawie danych planu: nadpisanie istniejącego artefaktu trwałego, flagi płatności/sieci lub jawny problem/advisory. Jeśli kontrakt planu nie ma wystarczającej informacji, dodaj neutralne metadane w warstwie planowania aplikacji zamiast zgadywać po nazwie zadania.
4. Start callback najpierw rezerwuje state transition, potem otwiera Confirm (jeśli potrzebny), następnie wywołuje App.start_execution raz.
5. Cancel Confirm/Back pozostawia plan w SessionState i nie release draftów.
6. Auto safe path może ominąć ekran, ale ten sam `start_execution`/guard jest używany; nie twórz osobnego execute callback.
7. Testuj blocking, warning, overwrite confirm cancel/confirm, double Enter/click, stale plan generation oraz plan z 0 tasks (reuse-only) jeśli `can_execute` dopuszcza.
8. Nie pokazuj provider request payloadów ani absolutnych paths.

**Przypadki brzegowe i pułapki:**
- Reuse-only plan może zakończyć się szybko; ekran Execution/Results nadal musi obsłużyć.
- Plan z partial source problems może być can_execute; tekst musi rozróżniać warning od blocker.
- Zmiana selection/draft po preview nie zmienia zapisanej plan; powrót i ponowne Preview buduje nowy.

**Lokalne kryteria akceptacji:**
- Preview pokazuje per grupę źródła, operacje w kolejności, produkty, pominięcia, warningi, blockery, modele/silniki i ścieżki docelowe względne.
- Start jest disabled, gdy can_execute=false.
- Nadpisanie, operacja płatna wymagająca jawnego potwierdzenia albo inny nieodwracalny skutek otwiera ConfirmDialog z konkretnym opisem.
- Start rezerwuje run przed workerem; podwójny Enter/klik nie tworzy dwóch execute.
- Back wraca do Auto albo Manual z zachowanym draftem.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_preview.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Jedna bezpieczna bramka Start dla Auto/Manual.
- Czytelny plan oparty na neutralnych DTO.
- Execution dostaje immutable plan i generation.

**Zakazy zadania:**
- Nie duplikuj reguł planera ani nie buduj planu w widgetach.
- Nie pokazuj pełnych promptów, sekretów ani absolutnych prywatnych ścieżek.

**Sugerowany commit:** `feat(tui): add executable plan preview and start gating`

---

### T-021 - Zbudować Execution, postęp i Cancel

**Cel obserwowalny:** Wyświetlać stabilny przebieg per grupa, retry/fallback i umożliwić idempotentne anulowanie bez zamrażania UI.

**Zależności wykonawcze:** T-020, T-016

**Najpierw przeczytaj:**
- `RunEventKind`, `TaskState`, `RunResult`, `GroupStatus`
- scheduler event sequence tests
- T-016 event pump
- historical progress table behavior

**Zakres własności zadania:**
- `anishift/tui/screens/execution.py`
- `anishift/tui/widgets/progress_table.py`
- `anishift/tui/app.py`
- `anishift/tui/state.py`
- `tests/tui/test_execution.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Jeden stabilny wiersz dla każdej grupy; szczegóły zadań są rozwijane, nie tworzą nowych tras.
- Aktualizacje postępu są koaleskowane do najwyżej 10 renderów/s na zadanie; zdarzenia terminalne renderują się natychmiast.
- Cancel jest contextual action, nie slash, i jest idempotentny.
- UI przyjmuje input podczas runu.

**Kolejność wykonania:**
1. Prealokuj rows dla `plan.groups` w natural order przed startem eventów.
2. Utrzymuj czysty model `ExecutionRowState` dla grupy/zadania; widget renderuje model, nie parsuje historii tekstowej.
3. Obsłuż wszystkie `RunEventKind`: queued/started/progress/retry/fallback/finished/group/run. Retry i fallback dopisuj jako bezpieczny tekst szczegółu.
4. Progress przechowuj latest percent; timer renderuje maksymalnie co 100 ms. TASK_FINISHED/GROUP_FINISHED/RUN_FINISHED wymuszają natychmiastowy refresh.
5. Spinner działa tylko dla widocznych running rows i nie utrzymuje globalnego timera po terminalnym stanie.
6. Filtr `f` cykluje all/running/failed/done; done jest UI filter obejmujący terminalne statusy.
7. Cancel action: Confirm z run ID niepokazywanym użytkownikowi, wywołanie `service.cancel(active_run_id)`, state -> cancelling tylko dla True; false pokazuje już zakończony/brak aktywnego.
8. Drugi Cancel podczas cancelling nie wywołuje service ponownie.
9. Test powolna atrapa handlera generuje 20 grup i zdarzenia postępu i równolegle wpisuje composer/otwiera help; brak utraty wejścia.
10. Test obcego run ID i starej generation nie zmienia row modelu.

**Przypadki brzegowe i pułapki:**
- TASK_PROGRESS może dotrzeć po terminalnym zdarzeniu zadania w tym tym samym opróżnieniu bufora wskutek sort? Sequence porządek rozstrzyga; starszy postęp ignoruj.
- Nie każde zadanie ma sensowny procent; pokaż spinner/operację bez sztucznego 0%.
- Cancellation result może zawierać częściowe produkty; Results jest źródłem terminalnej interpretacji.

**Lokalne kryteria akceptacji:**
- Każda grupa pokazuje glif+słowo stanu, bieżący zadanie, procent i rozwijane szczegóły.
- Retry i fallback są widoczne tekstowo z numerem próby i nazwą silnika/modelu.
- Filtr all/running/failed/done nie zmienia danych, tylko projekcję.
- Pierwszy Cancel przełącza stan na cancelling; kolejne są bezpieczne i nie wysyłają lawiny żądań.
- Composer, paleta i resize działają podczas aktywnego runu.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_execution.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Responsywny monitor runu i bezpieczny cancel.
- Kompletna projekcja eventów potrzebna Results/debug.
- Brak nieograniczonej historii progress.

**Zakazy zadania:**
- Nie renderuj surowego payloadu RunEvent ani stderr procesu.
- Nie anuluj runu samym Esc bez potwierdzenia.

**Sugerowany commit:** `feat(tui): add responsive execution progress and cancellation`

---

### T-022 - Zbudować Results i odzyskiwanie partial

**Cel obserwowalny:** Pokazać wynik per grupa, utworzone produkty, bezpieczne błędy i sensowne ścieżki ponowienia.

**Zależności wykonawcze:** T-021, T-019

**Najpierw przeczytaj:**
- `application/results.py` w całości
- `RunResult` z T-021
- `GroupIntentDraft.from_intent`
- publisher artifact contracts

**Zakres własności zadania:**
- `anishift/tui/screens/results.py`
- `anishift/tui/app.py`
- `anishift/tui/state.py`
- `tests/tui/test_results.py`

**Kontrakty, które to zadanie ma ustanowić:**
- `RunResult`/`GroupResult` są jedynym źródłem terminalnego statusu.
- Partial nie jest failure i pokazuje zachowane produkty.
- `Open in Manual` tworzy nowy/odłączony draft, nie wznawia wewnętrznego taska.
- Results jest dostępny tylko, gdy sesja ma wynik lub boundary failure.

**Kolejność wykonania:**
1. Zbuduj czysty mapper `RunResult -> ResultsViewModel` z sekcjami succeeded/partial/failed/cancelled, warnings i bezpieczne błędy.
2. Dla group pokaż trwałe products z typem i relative destination; nie pokazuj temp artifacts ani pełnych paths.
3. Boundary `RunFailed` bez RunResult jest osobnym globalnym failure state z instrukcją powrotu do workspace/manual.
4. Akcja details otwiera dialog/side panel z group operations/products/warnings; nie nowy system logów.
5. `Open in Manual` wybiera group, tworzy draft z aktualnego inspected group/defaultów lub zachowanego intent, czyści source-specific invalid IDs i nawiguje do Manual.
6. Akcje contextual: Workspace, Manual for failed/partial, ponowny Preview przez normalny plan; nie dodawaj `/results`.
7. App zapisuje wynik tylko dla aktualnej generation; late completion z poprzedniej jest ignorowane.
8. Testuj mixed result, cancelled with products, global failure, warning redaction, manual recovery isolation i command enabled predicate.

**Przypadki brzegowe i pułapki:**
- Produkt może istnieć mimo failed/partial; nie ukrywaj go.
- Missing destination/warning cleanup nie może wywrócić renderera.
- Nie obiecuj wznowienia na poziomie klipu/zadania.

**Lokalne kryteria akceptacji:**
- Results grupuje succeeded/partial/failed/cancelled glifem i słowem.
- Dla każdej grupy pokazuje trwałe produkty, zachowane artefakty, warningi i zredagowany błąd.
- Open in Manual tworzy niezależny draft dla wybranej nieudanej grupy i wraca do bezpiecznego planowania.
- Results pozostaje dostępny z rejestru tylko po istniejącym wyniku sesji.
- Spóźnione RunCompleted poprzedniej generacji nie podmienia aktualnego wyniku.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_results.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Terminalny ekran rozróżniający wszystkie statusy.
- Bezpieczna ścieżka odzyskania przez Manual/replan.
- DTO dla `/status`/`debug`.

**Zakazy zadania:**
- Nie obiecuj automatycznego resume, jeśli kontrakt aplikacji go nie zapewnia.
- Nie pokazuj pełnych ErrorContext.details ani absolutnych ścieżek.

**Sugerowany commit:** `feat(tui): add terminal results and partial recovery`

---

### T-023 - Podłączyć komendy narzędziowe i diagnostykę

**Cel obserwowalny:** Dokończyć /init, /status, /debug, /help, /doctor i /exit oraz spójnie podłączyć /connect i setup.

**Zależności wykonawcze:** T-016, T-015, T-005, T-006

**Najpierw przeczytaj:**
- `AppService.doctor/setup`, `CheckResult`, `ResourceResult`
- model statuses/probe T-015
- CommandRegistry exact catalog
- logger/redaction rules

**Zakres własności zadania:**
- `anishift/tui/tools.py`
- `anishift/tui/screens/tools.py`
- `anishift/tui/app.py`
- `tests/tui/test_tools.py`

**Kontrakty, które to zadanie ma ustanowić:**
- Narzędzia używają publicznej fasady i workerów działających w tle.
- `/status` i `/debug` renderują allowlist projekcji.
- `/init` proponuje działania, ale nic nie naprawia bez jawnego wyboru.
- `/exit` przy active run zawsze Confirm.

**Kolejność wykonania:**
1. W `tui/tools.py` zdefiniuj czyste view models dla status/debug/doctor/setup; fields są allowlistą, nie `asdict(Settings)`.
2. Zbuduj Tools route/dialog dla doctor results: status glyph+word, message, suggestion, opcjonalna contextual Setup action.
3. `/init` sprawdza workspace/config/catalog/secrets/binaries przez istniejące statusy i pokazuje najkrótszą sekwencję brakujących kroków.
4. `/status` pokazuje workspace group count/selection, preset, primary/translation aliases i sesyjny model status, engine readiness, run state/elapsed/result summary.
5. `/debug` dodaje version, Python/platform, console encoding, relative config names, last bezpieczne błędy classes/event counters; nie pełny event payload.
6. `/help` jest projekcją registry: dokładnie 14 slash + contextual bindings bieżącego ekranu.
7. `/exit` dispatchuje confirm przy planning/running/cancelling; podczas idle zamyka App. Ctrl+Q używa tej samej komendy.
8. Setup i Doctor działają w workers; setup nie uruchamia się przy mount ani samym `/init`.
9. Test secret/path/prompt canaries przez wszystkie widoki i notifications.

**Przypadki brzegowe i pułapki:**
- Doctor może zwrócić FAIL i nadal UI działa.
- Setup częściowo failed ma pokazać per resource wynik i pozostawić możliwość retry.
- Debug nie może importować prywatnego transportu Palantir.

**Lokalne kryteria akceptacji:**
- /init pokazuje brakujące kroki i może uruchomić setup po potwierdzeniu, lecz nie startuje pipeline.
- /status pokazuje workspace, selekcję, default preset, primary/translation model, engine readiness i run state bez sekretów.
- /debug dodaje wersje, kodowanie, ścieżki względne, ostatnie bezpieczne klasy błędów i stan katalogu; nie pokazuje promptów/body/tokenów.
- /doctor renderuje pełne CheckResult i sugestie; setup jest jawnie wywoływany, nie automatyczny przy wejściu.
- /help odzwierciedla dokładne 14 komend i żywe skróty; /exit respektuje active run.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_tools.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Komplet 14 komend ma realne zachowanie lub właściwy ekran.
- Bezpieczna diagnostyka i init flow.
- Gotowość do E2E convergence.

**Zakazy zadania:**
- Nie renderuj os.environ, Settings repr, headers, tokenów, pełnych command lines ani payloadów.
- Nie wykonuj setup, probe ani run bez jawnej akcji użytkownika.

**Sugerowany commit:** `feat(tui): finish TUI diagnostics and utility commands`

---

### T-024 - Zbiec pełny przepływ, responsywność i wydajność

**Cel obserwowalny:** Połączyć wszystkie ekrany i komendy w jeden spójny produkt oraz usunąć regresje fokusów, rozmiaru i responsywności.

**Zależności wykonawcze:** T-017, T-018, T-019, T-020, T-021, T-022, T-023

**Najpierw przeczytaj:**
- wszystkie Wynik zadanias T-017..T-023
- całe `tests/tui/`
- `spec.md` wszystkie AC
- full AppService fakes

**Zakres własności zadania:**
- anishift/tui/**
- `tests/tui/test_flow.py`
- `tests/tui/test_responsive.py`
- `tests/tui/test_performance.py`

**Kontrakty, które to zadanie ma ustanowić:**
- To zadanie konwergencji: nie dodaje nowych wymagań, commandów, providerów ani formatów.
- Pełny Pilot używa realnego AppService/planner/scheduler z atrapy handlerów granicznych.
- Defekt poprawia się w module właściciela, nie przez sleep/monkeypatch w teście.

**Kolejność wykonania:**
1. Zbuduj centralne `tests/tui/tui_fakes.py` tylko dla publicznych boundary dependencies; nie mockuj prywatnych widget handlers.
2. Dodaj E2E Pilot: workspace -> empty Enter -> safe Auto -> Execution -> Results.
3. Dodaj E2E Pilot: workspace -> Manual 3 groups -> Preview -> Start -> Cancel -> Results -> Open in Manual.
4. Dodaj przepływ ustawień/modeli: `/tts`, `/translation`, `/prompts`, `/model`, `/connect` atrapę jednego wywołania, `/status`, `/doctor`, `/exit`.
5. Dodaj responsive scenarios 100x30, 80x24 i resize z otwartym dialogiem/composer popup.
6. Dodaj performance scenarios: 100 groups scroll/filter/select w limicie 5 s; 20 groups dense progress i input; idle bez ciągłego refresh.
7. Uruchom grep guards: dokładnie 14 slash, brak `/variant`; brak hex poza theme; brak placeholder phrases; brak `anishift.services` import w TUI; brak unsafe canary.
8. Przejrzyj focus po każdym dismiss/route i znormalizuj BINDINGS konfliktujące z Input.
9. Uruchom pełne bramki co najmniej dwa razy po naprawach race/flaky; test nie może polegać na arbitralnym długim sleep.
10. Wykonaj lokalny smoke prototype/production launcher na terminalu i usuń pozostały demo code.

**Przypadki brzegowe i pułapki:**
- Testy xdist nie mogą współdzielić realnego config path; wszystkie persistence paths wstrzykiwane/tmp_path.
- Timer tests muszą używać `pilot.pause`/eventual assertions proporcjonalnie, nie 10-sekundowych sleep.
- Network markers nie uruchamiają realnego Foundry.

**Lokalne kryteria akceptacji:**
- Pilot przechodzi: workspace -> pusty Enter -> Auto execution -> Results.
- Pilot przechodzi: workspace -> /manual -> Preview -> Start -> Cancel -> Results.
- Pilot przechodzi ustawienia, model picker, /connect z atrapa transportuem, status, doctor i exit.
- 80x24 pozwala otworzyć composer/paletę i wyjść; 100x30 pokazuje pełny layout bez nakładania.
- 20 grup z gęstymi progress events zachowuje input; 100 grup przewija się w ustalonym limicie testu.
- Brak placeholderów, konkurencyjnych dispatch paths, surowych kolorów w TCSS i niezabezpieczonych komunikatów.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/tui/test_flow.py tests/tui/test_responsive.py tests/tui/test_performance.py -q`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Jeden spójny produkt TUI i pełny flow dowód.
- Brak tymczasowego demo/placeholderów.
- Gotowość do przełączenia CLI.

**Zakazy zadania:**
- Nie dodawaj nowych komend, ekranów, providerów ani formatu konfiguracji.
- Nie poluzowuj timeoutów testowych tylko po to, by ukryć blokujący kod UI.

**Sugerowany commit:** `test(tui): converge the complete TUI workflow`

---

## P-06 - Migracja i domknięcie

### T-025 - Przełączyć entrypoint i przywrócić tryb run CLI

**Cel obserwowalny:** Ustawić nowe TUI jako domyślne uruchomienie oraz zachować nieinteraktywne doctor, setup i run --preset bez importowania Textual na ich ścieżce.

**Zależności wykonawcze:** T-024

**Najpierw przeczytaj:**
- `anishift/cli/main.py`, `bootstrap.py`, `tui/__init__.py`
- revert commit `6849f32` i wcześniejsza implementacja `run --preset` jeśli dostępna w historii
- T-024 flow tests

**Zakres własności zadania:**
- `anishift/cli/main.py`
- `anishift/tui/__init__.py`
- `run_anishift.bat`
- `tests/cli/test_main.py`
- `tests/cli/test_run.py`

**Kontrakty, które to zadanie ma ustanowić:**
- No args lazy-importuje TUI i uruchamia AppService-backed `AniShiftApp`.
- `doctor`, `setup`, `run --preset` są nieinteraktywne i nie importują Textual na ścieżce.
- `run --preset` używa tej samej AppService path co TUI.
- Legacy shell nadal istnieje do zakończenia T-026, ale nie jest default.

**Kolejność wykonania:**
1. Wydziel `launch_tui()` w `cli/main.py` z lazy imports `bootstrap`, `create_app_service`, `AniShiftApp` wewnątrz funkcji.
2. Callback no-args wywołuje wyłącznie `launch_tui`; nie renderuje starego banneru/REPL.
3. Przywróć komendę Typer `run --preset <id>`: bootstrap, service.discover, wybór groups zgodny z default Auto, get preset, plan_auto, execute z EventBuffer/report sink.
4. Zdefiniuj stabilny tekstowy raport per group i exit codes: 0 tylko full success; partial/failed/cancelled/non-executable !=0.
5. Utrzymaj doctor/setup na istniejących bezpośrednich runnerach albo AppService tylko jeśli nie wymusza TUI importu.
6. Dodaj test `sys.modules`/import spy potwierdzający brak `textual`/`anishift.tui` dla doctor/setup/run.
7. Sprawdź `run_anishift.bat`: root resolution, UTF-8 i argument forwarding; nie zmieniaj go bez realnej potrzeby.
8. Manualny smoke no-args może uruchomić TUI, ale nie wykonuj jeszcze kasacji legacy.

**Przypadki brzegowe i pułapki:**
- Workspace bez groups w `run` daje konkretny nonzero, nie stack trace.
- Plan non-executable nie woła execute.
- KeyboardInterrupt w CLI run kończy się właściwym kodem i cleanup.

**Lokalne kryteria akceptacji:**
- uv run anishift bez argumentów uruchamia TUI.
- uv run anishift doctor i setup nie importują anishift.tui/textual na ścieżce wykonania.
- uv run anishift run --preset default zwraca 0 tylko przy pełnym sukcesie; partial/failure/cancel zwraca niezero.
- run_anishift.bat deleguje argumenty bez zmiany semantyki i zapewnia UTF-8.
- Test runnera używa atrapy AppService/handlers, bez sieci i mediów.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/cli/test_main.py tests/cli/test_run.py -q`
- `uv run anishift doctor`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Nowe TUI jest default.
- Nieinteraktywne CLI zachowane.
- Legacy dostępne tylko jako kod do testu parytetu/kasacji.

**Zakazy zadania:**
- Nie usuwaj jeszcze legacy shell/pipeline przed T-026.
- Nie importuj Textual na poziomie modułu cli/main.py dla subkomend technicznych.

**Sugerowany commit:** `feat(cli): launch the Textual interface by default`

---

### T-026 - Udowodnić parytet i usunąć legacy

**Cel obserwowalny:** Porównać nową ścieżkę aplikacyjną z legacy dla reprezentatywnych przypadków, przenieść brakujące regresje i usunąć prompt-toolkit shell oraz stary pipeline.

**Zależności wykonawcze:** T-025

**Najpierw przeczytaj:**
- całe `anishift/pipeline/` i `tests/pipeline/`
- legacy CLI files/tests
- application planner/scheduler tests
- T-025 CLI path

**Zakres własności zadania:**
- `tests/application/test_legacy_parity.py`
- tests/application/**
- `anishift/cli/shell.py`
- `anishift/cli/commands.py`
- `anishift/cli/completer.py`
- `anishift/cli/pipeline_ui.py`
- `anishift/cli/settings_panel.py`
- `anishift/cli/banner.py`
- `anishift/cli/tts_settings.py`
- anishift/pipeline/**
- tests/pipeline/**
- tests/cli/**
- `pyproject.toml`
- `uv.lock`
- `AGENTS.md`

**Kontrakty, które to zadanie ma ustanowić:**
- Legacy jest usuwane wyłącznie po zielonym hermetycznym parytecie.
- Parytet porównuje semantyczne statusy/products/provider calls, nie timestamps/log order.
- Wartościowe regresje migrują do application/services przed kasacją.
- Po tasku istnieje tylko jedna production execution path.

**Kolejność wykonania:**
1. Zbuduj tymczasowy `tests/application/test_legacy_parity.py` z identycznym tymczasowy workspace i atrapy dostawców dla legacy oraz AppService.
2. Pokryj co najmniej: safe Auto full success, already-Polish/reuse path, one group failure isolated, partial durable products, cancel/retry/fallback jeśli legacy ma stabilny odpowiednik, compose-only equivalent.
3. Porównaj group status, zbiór `(artifact kind, final filename)` i provider call counts. Jawne delty z SPEC, np. brak legacy promptu retry/settings/finish, nie są udawanym parytetem UI.
4. Jeśli test czerwony, sklasyfikuj: bug nowej application path, bug/quirk legacy albo świadoma delta. Bez rozstrzygnięcia nie przechodź dalej.
5. Przejrzyj każdy test `tests/pipeline`; przenieś scenariusz chroniący nadal istniejący kontrakt do `tests/application`/`tests/services` przed usunięciem.
6. Usuń legacy CLI files, cały `anishift/pipeline`, `tests/pipeline` i testy CLI wyłącznie legacy.
7. Uruchom `uv remove prompt-toolkit`; nie edytuj ręcznie dependency/lock.
8. Usuń tymczasowy parity test dopiero w tym samym lub kolejnym commicie po kasacji, jeżeli import legacy już nie istnieje; zachowaj jego scenariusze po stronie application tests.
9. Uruchom grep `prompt_toolkit|run_shell|anishift.pipeline|SlashCompleter`; wynik produkcja/tests musi być pusty poza ewentualną historią docs, którą aktualizuje T-027.
10. Zaktualizuj root/scoped AGENTS tylko w zakresie mapy usuniętych katalogów, jeśli inaczej bramki/dokumentacja są fałszywe.

**Przypadki brzegowe i pułapki:**
- Nie kasuj `application` handlerów powstałych w Etapie 9 tylko dlatego, że przypominają pipeline.
- Prompt-toolkit może być zależnością tranzytywną innego package; grep importów i direct dependency są właściwym kryterium.
- Test count może spaść, ale coverage scenariuszy nie.

**Lokalne kryteria akceptacji:**
- Tymczasowy test parytetu przechodzi przed kasacją.
- Po kasacji nie istnieją anishift/pipeline ani tests/pipeline, a rg nie znajduje prompt_toolkit, run_shell ani anishift.pipeline w produkcji/testach.
- prompt-toolkit jest usunięty wyłącznie przez uv remove i lock jest spójny.
- Domyślne TUI oraz CLI doctor/setup/run pozostają działające.
- Pełna liczba testów może zmaleć tylko o jawnie usunięte testy legacy zastąpione równoważnym pokryciem.

**Weryfikacja ukierunkowana:**
- `uv run pytest tests/application/test_legacy_parity.py -q przed usunięciem`
- `rg 'prompt_toolkit|run_shell|anishift\.pipeline' anishift tests po usunięciu`
- `uv lock --check`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Jedna execution path przez AppService.
- Brak legacy package/dependency/imports.
- Przeniesione regression obligations.

**Zakazy zadania:**
- Nie usuwaj legacy przy czerwonym parytecie albo nieprzeniesionym scenariuszu regresyjnym.
- Nie utrzymuj dwóch aktywnych ścieżek wykonania po zakończeniu zadania.

**Sugerowany commit:** `refactor(pipeline): remove the legacy execution path`

---

### T-027 - Domknąć Windows CI, granice architektury i dokumentację

**Cel obserwowalny:** Dodać wystarczające zabezpieczenia dla produktu Windows-only oraz zaktualizować istniejące dokumenty bez tworzenia osobnego pakietu raportów.

**Zależności wykonawcze:** T-026

**Najpierw przeczytaj:**
- `.github/workflows/ci.yml`, `pyproject.toml` gates
- root i scoped AGENTS/README/config docs/index
- wszystkie AC i finalny tree

**Zakres własności zadania:**
- `.github/workflows/ci.yml`
- `tests/application/test_architecture.py`
- `tests/cli/test_console.py`
- `tests/tui/test_flow.py`
- `AGENTS.md`
- `anishift/tui/AGENTS.md`
- `anishift/cli/AGENTS.md`
- `anishift/config/AGENTS.md`
- `config/README.md`
- `README.md`
- `docs/plans/_index.md`

**Kontrakty, które to zadanie ma ustanowić:**
- Linux CI zachowuje pełne bramki; Windows dodaje produktowo istotne smoke.
- Architecture guards egzekwują dependency direction.
- Aktualizowane są istniejące dokumenty; brak nowych reportów/ledgerów/CSV.
- Etap 10 może być oznaczony ukończony dopiero po CI i finalnym HITL.

**Kolejność wykonania:**
1. Rozszerz istniejący CI lub dodaj skupiony Windows job w tym samym workflow: checkout, setup-uv, `uv sync --frozen --group dev`, console tests, model catalog tests, TUI flow/responsive subset i CLI main/run.
2. Nie uruchamiaj real-media/network provider tests w Windows jobie; utrzymaj limit kosztu i timeout.
3. Rozszerz `tests/application/test_architecture.py`: application nie importuje textual/typer/rich/cli/tui; TUI nie importuje services/pipeline/platform concrete boundaries.
4. Dodaj/utrzymaj guards exact slash catalog, theme literals, secret canary i no legacy import jako zwykłe testy w istniejących katalogach.
5. Zaktualizuj `README.md`: uruchomienie, pusty Enter, `/auto` vs `/manual`, 14 komend, model catalog path, token env, `/connect`, CLI doctor/setup/run.
6. Zaktualizuj `anishift/tui/AGENTS.md`: ownership App/state/registry/dialogs/theme/workers; Pilot przez interakcję.
7. Zaktualizuj cli/config/root AGENTS oraz `config/README.md` tylko o aktualną mapę i pułapki; usuń informacje o legacy/panelu global Save.
8. Zaktualizuj `docs/plans/_index.md` z Etapem 10 i jawnie pozostaw otwarte backendowe rzeczy Etapu 9; nie zamykaj issue #38 automatycznie.
9. Uruchom pełne bramki, `uv sync --frozen`, `anishift doctor`, test uruchomieniowy bez argumentów i końcowy ręczny przepływ Windows: empty Auto, Manual Preview/Cancel, settings/model/connect z atrapą lub bezkosztowo, exit.
10. Dopiero po jawnej akceptacji użytkownika i zielonym CI zmień status aktywnego spec/plan zgodnie z workflow repo; sam plan pozostaje historią.

**Przypadki brzegowe i pułapki:**
- Windows path/codepage/file lock failure poprawiaj na boundary, nie w domenie.
- Docs nie zawierają prawdziwego enrollment URL/RID/tokena.
- Nie twórz validation report ani release dossier.

**Lokalne kryteria akceptacji:**
- Test architektury blokuje import textual/typer/rich/cli/tui w application oraz import services/pipeline w TUI.
- Windows CI uruchamia co najmniej sync frozen, kodowanie CLI, model catalog, TUI flow i pełny zestaw testów możliwy w czasie joba.
- README opisuje pusty Enter, 14 komend, /auto vs /manual, modele Foundry, token env i tryby CLI.
- AGENTS opisują własność theme, rejestru, dialogów, AppService boundary i zakaz sekretów.
- docs/plans/_index.md oznacza 10 jako ukończony dopiero po zielonym CI i akceptacji użytkownika.

**Weryfikacja ukierunkowana:**
- `uv sync --frozen --group dev`
- `uv run anishift doctor`
- Następnie wykonaj pełny zestaw **BRAMKA-PEŁNA**.

**Przekazanie do następnego zadania:**
- Finalny, utrzymywalny produkt i machine guards.
- Aktualna dokumentacja i CI.
- Workstream gotowy do finalize/PR, nie automatycznie zmergowany.

**Zakazy zadania:**
- Nie twórz nowych raportów walidacji, ledgerów, CSV ani schematów planistycznych.
- Nie zamykaj całego Etapu 9, jeśli jego pozostałe backendowe wymagania są nadal otwarte.

**Sugerowany commit:** `docs(repo): finish the AniShift TUI workstream`

---

## 5. Graf i sposób delegowania

`tasks.json` jest maszynowym grafem tych samych 27 kart. Nie jest samodzielnym briefem implementacyjnym.

### 5.1. Pakiet wejściowy jednego wykonawcy

Orkiestrator przekazuje wykonawcy dokładnie:

1. obiekt zadania z `tasks.json`;
2. fragmenty `spec.md` wskazane przez `spec_refs`, razem z powiązanymi inwariantami i AC;
3. sekcje `D-*` i `P-*` wskazane przez `plan_refs`;
4. pełną kartę `T-*` z §4, bez streszczania jej przez orkiestratora;
5. root `AGENTS.md` oraz każdy scoped `AGENTS.md` obowiązujący dla `scope`;
6. Wynik zadania bezpośrednich poprzedników, ale tylko ich `handoff`, `deviations` i publiczne kontrakty, bez całego logu sesji.

Nie wolno delegować samego obiektu JSON. `goal` opisuje wynik, a kolejność edycji, kontrakty, edge case'y i zakazy znajdują się w karcie `T-*`.

### 5.2. Procedura startowa wykonawcy

Przed edycją wykonawca:

1. sprawdza aktywną gałąź, `HEAD` i `git status --short`;
2. czyta przekazany pakiet wejściowy w podanej kolejności;
3. potwierdza istnienie plików wejściowych i publicznych symboli wymienionych w karcie;
4. uruchamia wskazany najtańszy test bazowy, jeżeli karta zakłada konkretne bieżące zachowanie;
5. zatrzymuje się i zwraca `BLOCKED`, gdy fałszywe jest materialne założenie `D-*`, brakuje outputu dependency albo realizacja wymaga zmiany SPEC.

Lokalna różnica nazwy helpera lub położenia prywatnego kodu nie blokuje zadania, o ile ownership i publiczny kontrakt pozostają identyczne.

### 5.3. Kontrakt Wynik zadania

Wykonawca zwraca orkiestratorowi zwięzły wynik w stałym układzie:

```text
result: completed | blocked
files_changed: [ścieżki]
contracts_established: [publiczne symbole / zachowania]
targeted_verification: [komenda -> wynik]
gate_all: pass | fail | not_run + powód
deviations: [lokalne odstępstwa od planu albo []]
handoff: [konkretne wyniki potrzebne następcom]
blocker: null | opis + wskazanie D/R/AC wymagającego replanu
```

Wynik zadania nie jest dopisywany do `tasks.json` ani `plan.md`; stan wykonania należy do orkiestratora. Następny wykonawca nie dziedziczy nieprzefiltrowanego chain-of-thought ani całego terminal logu.

### 5.4. Fale o rzeczywistej możliwości równoległości

- Po T-004: T-005 i T-006 mogą być realizowane równolegle, ale integrację palety wykonuje ostatni z nich bez duplikowania registry/selectora.
- Po T-009: T-010 i T-012 mogą być realizowane równolegle, ponieważ field access oraz model catalog mają oddzielne boundaries.
- Po T-012: T-013 może działać równolegle z końcówką T-011, o ile nie dotyka AppService/UserSettings.
- Po T-016/T-017: T-018 i T-019 mogą działać równolegle; obie gałęzie spotykają się w T-020.
- T-021, T-022 i T-023 są sekwencjonowane przez realne zależności stanu/wyników, nie dla wygody.

## 6. Strategia weryfikacji
### 6.1. Bramki po każdym zadaniu kodowym

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

Test ukierunkowany uruchamia się przed pełnymi bramkami, ale nigdy zamiast nich.

### 6.2. Dowody per warstwa

| Warstwa | Dowód |
| --- | --- |
| Konfiguracja | round-trip, zły typ, zły JSONC, zależności pól, atomowy zapis, brak sekretów |
| LLM Palantir | request mapping i response normalization per protokół, klasyfikacja błędów, cancellation, lazy client, redakcja |
| Primitives | Pilot klawiatury/fokusu/rollbacku/current marker/multi/reorder |
| Composer | dokładnie jeden trigger, IME/paste/Shift+Enter, plain text inert, running guard |
| Ekrany | publiczne wywołania AppService i wynik w SessionState, bez wywoływania prywatnych handlerów |
| Flow | realny AppService + atrapy handlerów granicznych; sukces/partial/cancel/stale event |
| Migracja | parytet przed kasacją, brak legacy importów po kasacji |
| Windows | console encoding + TUI flow + model catalog w jobie Windows oraz manualny terminal smoke |

### 6.3. Ręczne bramki

- **T-009:** design i ergonomia prototypu przed backendem.
- **T-027:** finalne wejście `anishift`, pusty Enter, Manual, ustawienia, model picker i wyjście na Windows Terminal.

Nie powstają osobne raporty walidacji. Wyniki są częścią Wynik zadania/CI i nie są kanonicznymi artefaktami planu.

## 7. Ryzyka i reakcje

| Ryzyko | Sygnał | Reakcja |
| --- | --- | --- |
| Powrót ciężkiego UI | duże formularze, kilka selektorów o tej samej mechanice, teksty się nakładają | zatrzymać fazę, wrócić do D-03/D-06; nie polerować po integracji |
| Empty Enter uruchamia dwa runy | dwa plan_auto/execute w teście automatyczne powtarzanie klawisza | naprawić rezerwację triggera przed workerem; nie dodawać debounce jako jedynej ochrony |
| Utrata pola ustawień | SettingSpec bez editor strategy | czerwony coverage test; uzupełnić wspólny dispatch, nie doraźny widget |
| Przeciek tokenu | token w repr/log/error/fixture/JSONC | natychmiast zatrzymać, usunąć materiał, poprawić allowlist/redakcję i dodać regresję |
| Fałszywa dostępność modelu | model z przykładu pokazany jako ready | status default `unknown`; ready wyłącznie po jawnej informacji/probe |
| Niekompatybilny JSONC parser | `uv add json5` nie rozwiązuje Python 3.14/Windows | BLOCKED; wybrać utrzymywaną bibliotekę i zaktualizować D-10; zakaz własnego parsera regex |
| Rozjazd protokołu Foundry | kontrakt z atrapą przechodzi, rzeczywisty endpoint zwraca 400/404 | zachować bezpieczny błąd; skorygować wyłącznie adapter danego protokołu i fixture testową z potwierdzonego kontraktu |
| UI zamraża się | Pilot nie przyjmuje wejścia podczas discovery/run | lokalizować blokujące wywołanie; przenieść do workera, nie zwiększać timeoutu |
| Parytet legacy czerwony | inne produkty/status/provider calls | nie usuwać legacy; ustalić czy to regres czy świadoma delta i zaktualizować wymagania/plan |
| Windows różni się od Ubuntu | kodowanie, sygnały, path/file lock | reprodukcja w Windows CI/manual; fix w boundary, bez platformowego monkeypatcha domeny |
| Scope rośnie o agenta/pluginy | potrzeba zwykłego tekstu lub `/variant` | zapisać jako osobny etap; 10 nie implementuje fikcyjnej funkcji |

## 8. Przewidywany zakres zmian

### Główne modyfikacje

- `anishift/tui/**` - pełne przepisanie.
- `tests/tui/**` - nowe testy scenariuszowe.
- `anishift/config/{settings,user_settings,field_catalog}.py` i nowe `field_access.py`, `model_catalog.py`.
- `anishift/application/{service,runtime}.py` oraz `bootstrap.py` - minimalne fasady/wiring.
- `anishift/services/llm/engines/palantir/**` i registry LLM.
- `anishift/cli/main.py`, nowy `console.py`, testy CLI.
- `config/anishift.models.example.jsonc`, `.gitignore`.
- `pyproject.toml`/`uv.lock` tylko przez uv.
- `.github/workflows/ci.yml` i istniejące README/AGENTS/index na końcu.

### Usunięcia warunkowe

- T-002: odrzucone `anishift/tui/**` i stare `tests/tui/**`.
- T-026 po parytecie: legacy pliki `anishift/cli/{shell,commands,completer,pipeline_ui,settings_panel,banner,tts_settings}.py`, całe `anishift/pipeline/**`, `tests/pipeline/**`, nieaktualne testy legacy CLI, zależność prompt-toolkit.

### Poza zakresem dotyku bez wykazanego powodu

- algorytmy ekstrakcji, napisów, translation chunking, TTS synthesis, audio i composition;
- hooki repo i lista scope commitów;
- real-media fixtures, zasoby binarne i workspace użytkownika;
- providerzy LLM niezwiązani z dodaniem wpisu registry Palantir.

## 9. Pokrycie: wymagania -> decyzja -> zadanie

| Zakres wymagań | Decyzje | Zadania |
| --- | --- | --- |
| R-001..R-008 platforma/design | D-01..D-04, D-15 | T-001..T-004, T-008, T-009, T-027 |
| R-010..R-015 komendy | D-05 | T-005, T-023, T-024 |
| R-020..R-027 composer/Auto/Manual | D-07, D-13 | T-007, T-018..T-020, T-024 |
| R-030..R-034 dialogi | D-06 | T-006, T-011, T-015, T-020 |
| R-040..R-048 ustawienia | D-08, D-09 | T-010, T-011, T-018, T-019 |
| R-050..R-060 modele/Foundry | D-10..D-12 | T-012..T-016 |
| R-070..R-086 workflow | D-13, D-14 | T-017..T-022, T-024 |
| R-090..R-094 narzędzia | D-05, D-12, D-14 | T-015, T-023 |
| R-100..R-109 jakość/migracja | D-13..D-17 | T-001, T-016, T-021, T-024..T-027 |
| I-001..I-019 | wszystkie decyzje | testy architektury i bramki każdego zadania |

### 9.1. Kryteria akceptacji i ich dowód

| Kryteria | Właściciel wykonania | Dowód wymagany przez plan |
| --- | --- | --- |
| AC-001..AC-002 | T-003, T-008, T-009, T-024, T-027 | Pilot resize + ręczna bramka Windows Terminal |
| AC-003..AC-004 | T-005, T-023 | test dokładnego katalogu, fuzzy i dispatch bez skutku ubocznego |
| AC-005..AC-008 | T-007, T-018, T-024 | Pilot composera i licznik wywołań AppService/auto trigger |
| AC-009 | T-019, T-020 | Pilot Manual -> Preview -> jawny Start |
| AC-010..AC-011 | T-006 | Pilot fokusu, rollbacku i walidacji dialogów |
| AC-012..AC-014 | T-010, T-011 | coverage SettingSpec, spy zapisu, canary sekretu |
| AC-015..AC-020 | T-012..T-015 | atrapa transportu, mapowanie czterech protokołów i klasyfikacja błędów |
| AC-021..AC-022 | T-017, T-024 | stabilna selekcja i scenariusz 100 grup bez blokowania wejścia |
| AC-023..AC-024 | T-018, T-020 | pełny Auto trigger oraz Confirm dla destrukcyjnego planu |
| AC-025..AC-030 | T-016, T-021..T-024 | stale-event guard, progress/retry/fallback, cancel, partial i responsywność |
| AC-031..AC-032 | T-001, T-025 | cp1250 regression oraz test lazy ścieżek CLI |
| AC-033..AC-034 | T-026 | parity test przed kasacją i grep/import gates po kasacji |
| AC-035 | T-009 | jawna akceptacja użytkownika zapisana w Wynik zadania |

## 10. Definicja ukończenia

- `anishift` bez argumentów uruchamia zaakceptowane TUI; `doctor`, `setup`, `run --preset` pozostają nieinteraktywne.
- Statyczne ANISHIFT, dwa motywy, compact mode, stały composer i stopka są spójne i nie nakładają się w 80x24/100x30.
- Katalog slash zawiera dokładnie 14 komend; `/variant` i akcje kontekstowe nie pojawiają się jako slash.
- Pusty Enter uruchamia dokładnie jeden default Auto, `/auto` nigdy nie startuje, zwykły tekst jest inert.
- Manual ma niezależne drafty, zawsze Preview i jawny Start.
- Pełny `SettingSpec` ma editor; commit jest per pole i atomowy; Esc nie zapisuje; sekrety są maskowane.
- Lokalny `anishift.models.jsonc` obsługuje provider/protocol/model aliases bez sekretów; model główny i tłumaczeniowy są niezależne.
- Adapter Palantir normalizuje cztery protokoły do neutralnego LLM API; `/connect` jest jedynym jawnym probe.
- Workspace/Preview/Execution/Results działają na AppService; UI pozostaje responsywne, stale events są ignorowane, cancel jest idempotentny.
- Legacy shell, legacy pipeline i prompt-toolkit są usunięte po zielonym parytecie; jedna ścieżka wykonania pozostaje.
- Pełne ruff/format/mypy/pytest i Linux/Windows CI są zielone; dokumentacja istniejąca opisuje aktualny produkt; brak dodatkowych raportów planistycznych.

## 11. Zasady blokad i przeplanowania

- **Drift repo bez zmiany kontraktu:** dostosuj lokalizatory i scope, odnotuj w Wynik zadania.
- **Drift zmieniający publiczny kontrakt AppService/SettingSpec/LLM:** zatrzymaj zależne zadania i zaktualizuj wymagania + D-* + dotknięte briefy.
- **Niewykonalny wymóg UX w Textual:** najpierw minimalny reproducer; wybierz najbliższy stabilny publiczny mechanizm Textual, bez prywatnego API. Jeśli zachowanie użytkownika się zmienia, wróć do wymagań.
- **Czerwona bramka wizualna:** wróć do P-02; nie buduj backendu pod odrzucony interfejs.
- **Czerwony parytet:** legacy zostaje; rozstrzygnij regresję kontra świadomą deltę.
- **Niepewna dostępność modelu/enrollment:** pozostaw `unknown`; nie blokuj przeglądania katalogu, blokuj jedynie start wymagający niepotwierdzonego/brakującego modelu z konkretną instrukcją.
- **Live provider wymaga nowego sekretu lub endpointu:** nie zgaduj; aktualizuj katalog/env po potwierdzonej informacji użytkownika.

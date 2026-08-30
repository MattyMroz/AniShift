---
kind: plan
status: implemented
baseline: c9e8f0e plus accepted docs/work/llm-translation/spec.md
created: 2026-08-30
---

# Plan: kompletny kontrakt JSON tłumaczenia LLM

## Cel

Zastąpić obecny system numerowanych odpowiedzi i rejestru promptów jednym
provider-agnosticznym silnikiem tłumaczenia na język polski, który wysyła napisy
jako czysty JSON, akceptuje wyłącznie kompletny wynik zgodny ze ścisłym kontraktem
JSON, ponawia niepoprawną odpowiedź z konkretnym polskim promptem korekcyjnym,
ładuje wersjonowane prompty Markdown z własnego modułu oraz pozwala użytkownikowi
wybrać wykryty styl bez przechowywania treści promptów w `config/`.

Plan obejmuje jeden końcowy rezultat. Kolejność działań niżej służy wyłącznie
bezpiecznej realizacji zależności i nie dzieli rezultatu na osobne wydania.

## Rezultat użytkownika

Po wybraniu silnika `llm` użytkownik wybiera wyłącznie styl tłumaczenia. AniShift
przekazuje każdą partię napisów do modelu w ustalonym JSON-ie, zapisuje wynik tylko
po pełnej walidacji, a po błędzie odpowiedzi ponawia żądanie z informacją, co model
zwrócił niepoprawnie. Dodanie pliku `styles/<name>.md` do modułu powoduje pojawienie
się `<name>` w ustawieniach po ponownym uruchomieniu aplikacji. Wartość
`Plików LLM jednocześnie` nadal ma zakres `1..4` i domyślną wartość `4`.

## Warunki końcowe

- [x] Do modelu trafia dokładnie `{"subtitles": [{"id": 0, "text": "..."}]}`,
  bez języków, tytułu, gatunku, streszczenia, słownika ani innych metadanych.
- [x] Akceptowana odpowiedź ma dokładnie postać
  `{"translations": [{"id": 0, "translated": "..."}]}` i przechodzi wszystkie
  walidacje struktury, liczby, typów, identyfikatorów, kolejności oraz treści.
- [x] Markdown, tekst przed lub po JSON-ie, alternatywne klucze, duplikaty,
  częściowy wynik i przerwany output są odrzucane w całości.
- [x] Każde ponowienie kontraktowe zachowuje trzy prompty podstawowe i identyczny
  JSON wejściowy, a na końcu dodaje wyrenderowany `retry.md` opisujący wyłącznie
  ostatni wykryty błąd.
- [x] Po wyczerpaniu limitu silnik zgłasza `TranslationEngineError`; nie zapisuje
  źródła jako udanego tłumaczenia i pozwala istniejącemu łańcuchowi silników
  uruchomić kolejny fallback.
- [x] `system.md`, `translation.md`, `retry.md` i `styles/neutral.md` są jedynymi
  źródłami treści promptów aplikacji, należą do paczki i dają się odczytać po
  zbudowaniu wheel.
- [x] Nie istnieje runtime'owy `config/prompts/`, stary rejestr
  `task/style/module/contract`, format `[N] text` ani pola ustawień
  `llm_prompt_id`, `llm_style_id`, `llm_module_ids`.
- [x] `config/settings.json` przechowuje tylko `llm_translation_style`; starszy
  plik ustawień ładuje się bez błędu, a kolejne zapisanie usuwa stare pola.
- [x] UI pokazuje wszystkie poprawne pliki `styles/*.md`, nie wykonuje I/O w
  pętli renderowania i nie pokazuje pól promptu głównego ani modułów.
- [x] Provider, model, parametry generowania, fallback silników i współbieżność
  plików zachowują dotychczasową semantykę.

## Nie-cel

Plan nie tworzy docelowej, rozbudowanej treści promptu tłumaczeniowego ani
biblioteki stylów. Nie zmienia tłumaczenia Google/DeepL, ekstrakcji, TTS, audio,
kompozycji, wyboru modelu ani sposobu uwierzytelniania dostawców.

Natywne structured output (`response_format`, JSON Schema,
`response_mime_type`) również nie należy do tego rezultatu. Jest to świadoma
decyzja kompatybilności: OpenRouter deklaruje tę funkcję tylko dla wybranych
modeli, a `openai_compatible` może wskazywać endpoint o dowolnych możliwościach.
Wspólną gwarancję daje prompt i lokalna walidacja. Natywny tryb może powstać
później dopiero jako jawna capability modelu/profilu, bez zgadywania po nazwie.

Ważne rozróżnienie techniczne: każdy provider otrzymuje całe żądanie HTTP jako
JSON, ale treść wiadomości modelu jest tekstem. „Czysty JSON na wejściu” oznacza
więc jeden `TextPart`, którego pełna zawartość jest serializacją obiektu JSON, a
nie provider-specificznym typem content block. To jest wspólny format obsługiwany
przez wszystkie obecne adaptery AniShift.

## Authority i baseline

| Źródło | Rola |
| --- | --- |
| `docs/work/llm-translation/spec.md` | zaakceptowany kontrakt rezultatu |
| root `AGENTS.md` oraz instrukcje obszarów `anishift/`, `config/`, `application/`, `cli/`, `translation/`, `translation/engines/llm/`, `services/llm/`, `tests/` | obowiązujące reguły repozytorium |
| `anishift/services/translation/engines/llm/` | rzeczywisty właściciel obecnego silnika i promptów |
| `anishift/application/runtime.py`, `planning.py`, `service.py` | rzeczywiste składanie konfiguracji i granicy LLM |
| `anishift/config/user_settings.py`, `field_catalog.py`, `field_access.py` | persistence i źródło pól UI |
| `anishift/cli/interactive/settings.py` | obecny panel ustawień |
| `apps/gemini_translator/src/translator.py` w `geminicli2api` | wzorzec ponowienia z opisem ostatniego błędu; nie jest authority dla liberalnego parsowania, 100 prób ani częściowego zapisu |
| [OpenAI Chat Completions](https://platform.openai.com/docs/api-reference/chat/create) | `json_object` i JSON Schema są opcjami zależnymi od modelu |
| [Claude structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) | funkcja ma jawną listę wspieranych rodzin modeli |
| [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output) | JSON Schema jest wspierane jako podzbiór specyfikacji i nadal wymaga walidacji aplikacji |
| [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/) | `json_object` wymaga odpowiedniego promptu i może zwrócić pustą treść |
| [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs) | wsparcie dotyczy wybranych modeli i należy sprawdzać `supported_parameters` |
| [xAI structured outputs](https://docs.x.ai/developers/model-capabilities/text/structured-outputs) | Grok obsługuje `json_object`/JSON Schema dla wspieranych modeli |

**Baseline:** branch `work/interactive-cli/04-mascot-polish`, commit `c9e8f0e`.
Przed rozpoczęciem implementacji jedyną zmianą worktree w tym workstreamie są
nieśledzone dokumenty `docs/work/llm-translation/`.

**Znany wcześniejszy failure:** targeted baseline z 2026-08-30 zakończył się
wynikiem `150 passed, 1 skipped, 1 failed`. Niezwiązany test
`tests/config/test_user_settings.py::test_defaults_include_all_panel_fields`
oczekuje `elevenbytes_vpn_enabled=True`, podczas gdy bieżący kod ma domyślnie
`False`. Implementacja nie może naprawiać tego przy okazji; końcowe porównanie ma
wykazać brak nowych failures. Pełne bramki pozostają obowiązkowe przed commitem,
więc ewentualny commit wymaga osobnej decyzji właściciela tego baseline failure.

## Stan aktualny

```text
CURRENT
tekst [N] + task/style/module/contract + opcjonalne metadane
    ↓
GAP
brak ścisłego JSON, wiele źródeł promptów, stary config i liberalny parser
    ↓
TARGET
trzy stałe prompty + jeden styl + czysty JSON + ścisła walidacja + retry.md
```

### Obecne zachowanie i przyczyna luki

- `LlmTranslateService` parsuje linie przez regex `LINE_PATTERN`; ignoruje tekst,
  który nie pasuje do `[N]`, więc odpowiedź z komentarzem może zostać przyjęta.
- `PromptComposer` buduje XML-owy blok z `source_language`, `target_language`,
  tytułem, streszczeniem i słownikiem. Są to dane zakazane przez nowy kontrakt.
- `PromptRegistry` łączy zasoby `.txt` z paczki i `config/prompts/`, obsługuje
  task/style/module/contract, wersje i fingerprinty. Nowy kontrakt ma trzy stałe
  role, jeden wybierany styl i nie potrzebuje rejestru.
- `LlmCompletionRequest` przenosi `PromptIdentity` i
  `omitted_context_items`, chociaż adapter runtime ich nie używa.
- `UserSettings`, `RunSettingsSnapshot`, field catalog i UI propagują stare trzy
  pola promptów aż do composition root.
- Przy błędnej odpowiedzi obecny silnik wykonuje jedną naprawę formatu, a po jej
  błędzie dzieli partię. Nie rozpoznaje konkretnego naruszenia kontraktu JSON.
- `config/README.md`, `.gitignore` i śledzony `config/prompts/` nadal opisują
  runtime'owe prompty użytkownika.
- `llm_max_concurrency` ma zakres `(1, 4)`, domyślną wartość `4`, walidację w
  `RunSettingsSnapshot` i dodatkowy limit `min(..., 4)` w schedulerze. To poprawny,
  niezależny kontrakt, który pozostaje nietknięty.

### Istniejące rozwiązania do reuse

| Element | Ścieżka / symbol | Co wykorzystać | Ograniczenie |
| --- | --- | --- | --- |
| provider-agnosticzne DI | `translation.protocols.LlmCompleter` | zachować brak importu `services.llm` w domenie tłumaczenia | uprościć payload requestu |
| mapowanie błędów LLM | `application.runtime._raise_translation_error` | zachować typowane błędy context/provider | nie logować odpowiedzi ani promptów |
| transport retry | `services.llm.LlmService` | pozostawić retry błędów przejściowych | oddzielić od retry niezgodnego JSON-u |
| fallback silników | `translation.service.TranslationService` | po terminalnym błędzie LLM przetłumaczyć cały plik następnym silnikiem | bez częściowego commitowania wyniku LLM |
| przygotowanie pustych linii | `TranslationService._prepare_file` | nadal nie wysyłać pustych napisów do providera | zachować mapowanie na oba strumienie |
| recovery rozmiaru | `LlmTranslateService._split` | zachować binarny podział dla context/output limitu | nie używać go do ukrywania błędnego JSON-u |
| zasoby paczki | `importlib.resources.files` używane przez obecny `PromptRegistry` | ładować pliki niezależnie od CWD i wheel | bez ścieżek runtime z `config/` |
| dynamiczne choices UI | `field_catalog.SettingSpec.allowed_values` | przekazać listę nazw stylów do istniejącego edytora | bez I/O w `SettingsController.render()` |
| tolerancyjny loader ustawień | `load_user_settings()` | ignorować stare i nieznane pola | brak promptowych fallbacków w kodzie |

## Zakres

### In scope

- nowy kontrakt JSON wejścia i wyjścia LLM;
- ścisła serializacja, walidacja i klasyfikacja naruszeń;
- cztery pliki Markdown należące do modułu: trzy role stałe i neutralny styl;
- wykrywanie kolejnych stylów `.md` bez rejestru i bez zmiany kodu;
- konfiguracja tylko nazwy stylu oraz migracja starego pliku settings;
- retry odpowiedzi niezgodnej z kontraktem, limitowane istniejącym ustawieniem
  `translation_max_retries`;
- zachowanie binarnego podziału wyłącznie dla limitu kontekstu lub outputu;
- usunięcie starego protokołu, zasobów, konfiguracji, UI i dokumentacji runtime;
- testy jednostkowe, integracyjne, pakietowe i regresyjne wymagane przez zmianę.

### Out of scope

- merytoryczne rozwijanie promptów ponad minimalną treść potrzebną do działania;
- dodatkowe style poza `neutral.md`;
- natywne structured output i capability discovery modeli;
- nowe pole konfiguracji liczby retry;
- język docelowy inny niż polski;
- zmiany providerów niezwiązane z istniejącym przekazywaniem wiadomości;
- naprawa zastanego failure dotyczącego `elevenbytes_vpn_enabled`;
- edycja historycznych planów i specyfikacji innych workstreamów.

### Forbidden

- nie dodawać Pydantic/YAML/Jinja ani nowej zależności do prostego kontraktu;
- nie trzymać treści promptów w stałych Pythona, JSON-ie, `config/` ani settings;
- nie wycinać JSON-u z Markdownu lub tekstu swobodnego;
- nie akceptować aliasów kluczy, listy bez obiektu root ani wyniku częściowego;
- nie wysyłać modelowi języków, metadanych materiału ani poprzedniej surowej
  odpowiedzi;
- nie logować promptów, wejściowego JSON-u, odpowiedzi ani tekstu napisów;
- nie zgadywać structured-output capability po nazwie dostawcy lub modelu;
- nie zmieniać `LLM_MAX_CONCURRENCY_RANGE`, wartości domyślnej `4`, schedulera ani
  etykiety `Plików LLM jednocześnie`;
- nie naprawiać pobocznych błędów i nie refaktoryzować innych domen.

### Dozwolone decyzje lokalne

- nazwy prywatnych helperów i prywatnego typu opisującego naruszenie JSON;
- rozdzielenie testów kontraktu i loadera między istniejące pliki testowe, o ile
  zachowany jest opisany zakres dowodu;
- użycie zwykłych dataclasses albo małych typów prywatnych; publiczny kontrakt i
  semantyka nie mogą się zmienić;
- dopasowanie dokładnego API `importlib.resources` do Python 3.14 bez zamiany na
  ścieżkę zależną od repozytorium.

### Zatrzymaj się i wróć po decyzję, gdy

- którykolwiek aktywny konsument poza wskazanym impact scan używa
  `PromptIdentity`, `PromptRegistry` albo starych pól promptowych;
- zasoby `.md` nie są pakowane przez aktualny `uv_build` i naprawa wymaga zmiany
  backendu budowania lub nowej zależności;
- wspierany adapter nie potrafi zachować oddzielnej wiadomości systemowej i
  uporządkowanych części użytkownika;
- realizacja wymaga zmiany publicznego kontraktu Google/DeepL, schedulera,
  współbieżności albo formatu plików napisów;
- jedynym sposobem na osiągnięcie JSON-u okaże się uzależnienie działania od
  natywnego `response_format`.

## Kontekst do przeczytania przed implementacją

Czytać w tej kolejności:

| Kolejność | Źródło | Po co | Zakres |
| --- | --- | --- | --- |
| 1 | `docs/work/llm-translation/spec.md` | obowiązujące wymagania i zakazy | cały plik |
| 2 | właściwe `AGENTS.md` od roota do zmienianego katalogu | reguły kodu, testów i granic domen | całe pliki |
| 3 | `translation/protocols.py`, `engines/llm/{config,constants,service}.py`, `engines/llm/prompts/` | obecny kontrakt, parser i prompty | całe pliki |
| 4 | `translation/service.py`, `errors.py`, `types.py` | puste linie, fallback, publiczny wynik | właściwe symbole |
| 5 | `application/{planning,service,runtime,scheduler_contracts}.py` | snapshot, composition root, retry i concurrency | właściwe symbole |
| 6 | `config/{user_settings,field_catalog,field_access}.py` | persistence, choices i migracja | właściwe symbole |
| 7 | `cli/interactive/settings.py` | widoczne pola i brak I/O renderu | sekcja translation i catalog snapshot |
| 8 | wskazane niżej testy | zastane kontrakty i styl testów | całe pliki dotknięte zmianą |

## Impact scan

| Kontrakt / subsystem | Ryzyko wpływu | Obowiązek regresyjny |
| --- | --- | --- |
| `TranslationEngine.translate_batch` | interfejs nadal przyjmuje source/target dla wszystkich silników | LLM nie serializuje języków; Google/DeepL bez zmian |
| `LlmCompleter` | zmienia się kształt translation-owned requestu | fake completer i runtime zachowują role/części w tej samej kolejności |
| provider adapters | części `TextPart` przechodzą istniejącym neutralnym API | zero zmian adapterów; ich pełne testy nadal przechodzą |
| batching i recovery | błędny parser może stracić lub przestawić napisy | testy kompletności, kolejności, splitu i jednej linii |
| fallback silników | terminalny błąd ma uruchomić istniejący fallback | test fasady potwierdzający brak częściowego sukcesu |
| settings persistence | usuwane są trzy pola, dodawane jedno | migracja schema 1/2, roundtrip schema 3, ignorowanie legacy |
| field catalog i UI | zmieniają się ID oraz dynamiczne choices | test allowed values, aktywności i zapisu wyboru |
| zasoby pakietu | pliki działające ze źródeł mogą zniknąć z wheel | build i inspekcja wheel plus test `importlib.resources` |
| błędy i logi | opis retry nie może ujawnić odpowiedzi | test bez surowego outputu; zachowanie reguł loggera |
| scheduler | nie jest częścią przebudowy promptów | istniejące testy `llm_max_concurrency=4` bez zmian |
| dokumentacja runtime | stare `config/prompts` wprowadzałoby w błąd | usunięcie sekcji, plików i reguły gitignore |

## Target design

### Odpowiedzialności i source of truth

| Element | Odpowiada za | Source of truth | Nie odpowiada za |
| --- | --- | --- | --- |
| `prompts/loader.py` | bezpieczny odczyt obowiązkowych Markdownów i listę stylów | zasoby paczki pod `prompts/` | skład JSON, retry, ustawienia użytkownika |
| `json_contract.py` | serializację wejścia, pełne parsowanie odpowiedzi i konkretną diagnozę | kodowy kontrakt JSON ze specyfikacji | jakość tłumaczenia i treść promptów |
| `LlmTranslateService` | batching, kolejność request parts, retry kontraktowe, split limitów i wynik `BatchedLine` | config silnika + loader + validator | provider SDK, persistence, UI |
| `translation.protocols.LlmCompletionRequest` | minimalny, typowany transport systemu i uporządkowanych części user | żądanie zbudowane przez silnik | prompt identity, metadata, native response format |
| `UserSettings.llm_translation_style` | trwały wybór jednej nazwy stylu | `config/settings.json` | treść i ścieżki promptów |
| field catalog | dostępne wartości wyboru stylu | wynik skanowania zasobów paczki | ręczna lista nazw stylów |
| application runtime | przekazanie stylu i limitu retry do silnika | immutable run snapshot | ładowanie promptów z `config/` |

Treści promptów istnieją tylko w `.md`. Kod przechowuje wyłącznie stałe nazwy
zasobów, placeholder promptu korekcyjnego oraz techniczne komunikaty walidatora.
Opis błędu wstawiany do `retry.md` jest stanem pochodnym jednej odrzuconej
odpowiedzi i nie jest zapisywany.

### Przepływ sterowania

```text
prepared non-empty subtitle texts
-> batch limited by max_batch_lines
-> ids 0..N-1 + json.dumps(ensure_ascii=False)
-> load system.md + translation.md + selected style.md + retry.md
-> LlmCompletionRequest
   system = system.md
   user_parts = (translation.md, style.md, exact input JSON)
-> provider-neutral LlmCompleter
-> whole response text
-> strict full-document JSON parser
   -> valid: ordered BatchedLine list
   -> contract violation: same base parts + same JSON + rendered retry.md
   -> context/output limit: discard + deterministic binary split
   -> exhausted retries/single-line size failure: TranslationEngineError
-> existing TranslationService whole-file fallback
```

### Docelowe drzewo

```text
anishift/services/translation/
├── protocols.py                                      # MODIFY
└── engines/llm/
    ├── AGENTS.md                                     # MODIFY
    ├── __init__.py                                   # MODIFY if exports change
    ├── config.py                                     # MODIFY
    ├── constants.py                                  # MODIFY
    ├── json_contract.py                              # NEW
    ├── service.py                                    # MODIFY
    └── prompts/
        ├── __init__.py                               # MODIFY
        ├── loader.py                                 # NEW
        ├── system.md                                 # NEW
        ├── translation.md                            # NEW
        ├── retry.md                                  # NEW
        ├── styles/
        │   └── neutral.md                            # NEW
        ├── composer.py                               # DELETE
        ├── registry.py                               # DELETE
        ├── types.py                                  # DELETE
        └── assets/                                   # DELETE recursively (tracked legacy files only)

anishift/application/
├── planning.py                                      # MODIFY
├── service.py                                       # MODIFY
└── runtime.py                                       # MODIFY

anishift/config/
├── user_settings.py                                 # MODIFY
├── field_catalog.py                                 # MODIFY
└── field_access.py                                  # KEEP unless tests expose a generic mapping gap

anishift/cli/interactive/settings.py                 # MODIFY
config/README.md                                     # MODIFY
config/prompts/                                      # DELETE tracked README/.gitkeep files
.gitignore                                           # MODIFY

tests/services/translation/test_translation_llm.py  # REWRITE relevant cases
tests/services/translation/test_translation_prompts.py # REWRITE as loader/resource tests
tests/services/translation/test_translation_service.py # MODIFY only for fallback regression if absent
tests/config/test_user_settings.py                   # MODIFY
tests/config/test_field_catalog.py                   # MODIFY
tests/config/test_field_access.py                    # MODIFY only if new scalar field needs coverage
tests/application/test_planning.py                   # MODIFY
tests/application/test_service.py                    # MODIFY
tests/application/test_runtime_config.py             # MODIFY
tests/application/test_settings_update.py            # MODIFY when catalog persistence is covered there
tests/application/test_scheduler.py                  # KEEP; run as regression
```

`CLAUDE.md` obok zmienianego `AGENTS.md` pozostaje sprzężonym wskaźnikiem i nie
otrzymuje niezależnej treści. Historyczne plany w `docs/plans/` oraz inne
workstreamy pozostają niezmienione; nowa specyfikacja jest authority dla tego
kontraktu.

### Publiczne kontrakty

#### `LlmTranslateConfig`

```text
max_batch_lines: int = 1000
style_name: str = "neutral"
max_contract_retries: int = wartość translation_max_retries ze snapshotu

validation:
- max_batch_lines > 0
- style_name po strip niepuste i jest wyłącznie nazwą, nie ścieżką
- max_contract_retries mieści się w istniejącym zakresie 0..10
```

`prompt_id`, `prompt_version`, `style_id`, `module_ids` i `context` znikają.

#### `LlmCompletionRequest`

```text
system: str
user_parts: tuple[str, ...]

normal request user_parts:
1. translation.md
2. styles/<selected>.md
3. exact input JSON

corrective request user_parts:
1. translation.md
2. styles/<selected>.md
3. the same exact input JSON
4. retry.md with the latest validation error substituted
```

`PromptIdentity`, `PromptPurpose` i `omitted_context_items` znikają, jeżeli końcowy
impact scan potwierdzi brak konsumentów. `_LlmCompleter` mapuje `system` na jeden
`LlmMessage(SYSTEM)` i `user_parts` na kolejno ułożone `TextPart` jednej wiadomości
`USER`. Nie łączy promptu systemowego z wiadomością użytkownika.

#### Wejście JSON

```json
{
  "subtitles": [
    {"id": 0, "text": "Hello."},
    {"id": 1, "text": "How are you?"}
  ]
}
```

- `json.dumps(..., ensure_ascii=False)`;
- root ma tylko `subtitles`;
- `id` jest pozycją `0..N-1`;
- każdy niepusty tekst ma osobny element, również gdy wartości się powtarzają;
- wewnętrzne nowe linie są escaped przez serializer i po odczycie nadal należą
  do `text`;
- JSON jest osobnym `TextPart`, bez nagłówka, code fence i XML-a.

#### Wyjście JSON

```json
{
  "translations": [
    {"id": 0, "translated": "Cześć."},
    {"id": 1, "translated": "Jak się masz?"}
  ]
}
```

- parser czyta całe `response.text` jednym `json.loads`;
- custom `parse_constant` odrzuca `NaN`, `Infinity` i `-Infinity`;
- `object_pairs_hook` odrzuca powtórzone klucze JSON, zanim zostaną nadpisane;
- root musi być obiektem z dokładnie jednym kluczem `translations`;
- tablica ma dokładnie `N` elementów;
- każdy element jest obiektem z dokładnie `id` i `translated`;
- `type(id) is int`, więc `bool` nie przechodzi jako liczba;
- ID są unikalne, dokładnie `0..N-1` i w tej samej kolejności;
- `translated` jest stringiem niepustym po `strip`; wynik usuwa wyłącznie
  zewnętrzne białe znaki, zachowując wewnętrzne podziały;
- żadna częściowa lista nie opuszcza parsera.

#### Prompt resources

```text
fixed resources: system.md, translation.md, retry.md
style resources: immediate children styles/*.md
default style: neutral
retry placeholder: one unique literal token, e.g. {{validation_error}}
```

Loader używa `importlib.resources.files` i UTF-8, normalizuje CRLF/CR do LF oraz
odrzuca brak, błąd odczytu i pustą treść. Nazwy stylów pochodzą wyłącznie ze stemów
bez rozszerzenia, są sortowane naturalnie i muszą być jednoznaczne również po
`casefold`, aby wynik był stabilny na Windowsie i w wheel. Surowa wartość settings
nigdy nie jest doklejana do ścieżki przed sprawdzeniem jej względem wykrytej listy.
`retry.md` musi zawierać dokładnie jeden placeholder błędu.

#### Persistence

```text
SETTINGS_SCHEMA_VERSION: 3
llm_translation_style: str = "neutral"
removed: llm_prompt_id, llm_style_id, llm_module_ids
unchanged: llm_max_concurrency: int = 4, allowed 1..4
```

Loader przyjmuje schema `1`, `2` i `3`, wykonuje dotychczasową migrację v1, ignoruje
stare pola promptów przez filtr znanych pól, a brak nowego pola daje `neutral`.
Jeżeli zapisany styl nie istnieje, wybiera `neutral`, jeśli jest dostępny; w innym
przypadku pierwszy poprawny styl w stabilnej kolejności. Brak jakiegokolwiek stylu
jest `TranslationConfigError`, bo oznacza uszkodzoną paczkę, nie stan do ukrycia
fallbackiem w Pythonie. Zapis zawsze emituje schema 3 i tylko nowe pole stylu.

### Algorytm retry i failure semantics

1. Pusta lista wejściowa zwraca pustą listę bez odczytu providera.
2. Każda niepusta partia otrzymuje jeden niezmienny string wejściowego JSON-u.
3. Pierwsza próba zawiera trzy części podstawowe bez `retry.md`.
4. Finish reason należący do `_OUTPUT_LIMIT_REASONS` jest zawsze odrzucany, nawet
   gdy prefix odpowiedzi wygląda jak poprawny JSON.
5. `TranslationContextLengthError` i output limit nie uruchamiają promptu
   korekcyjnego. Partia jest dzielona na stabilne połowy, ponieważ ponowienie tej
   samej wielkości nie usuwa przyczyny pojemnościowej.
6. Dla każdej innej odpowiedzi parser zwraca albo komplet tłumaczeń, albo jeden
   wewnętrzny opis ostatniego naruszenia. Opis zawiera techniczne oczekiwania, np.
   oczekiwaną i otrzymaną liczbę lub brakujące ID, ale nigdy surową odpowiedź.
7. Przy naruszeniu kontraktu następna próba zachowuje identyczne trzy części i
   identyczny input JSON, po czym dodaje wyrenderowany `retry.md` jako ostatnią
   część usera. Kolejne naruszenie zastępuje opis poprzedniego; historia nie rośnie.
8. `max_contract_retries` oznacza liczbę dodatkowych prób po pierwszej, czyli
   `0` daje jedną próbę, a domyślne `3` maksymalnie cztery completion responses.
9. Transportowe retry w `LlmService` pozostaje osobnym mechanizmem wewnątrz
   pojedynczego completion. Nie wolno traktować błędu sieciowego jako błędnego
   JSON-u ani doklejać `retry.md`, jeśli model nie zwrócił odpowiedzi.
10. Po wyczerpaniu retry kontraktowego powstaje jeden `TranslationEngineError`
    (`ErrorCode.TRANSLATION_FAILED`) z bezpieczną informacją o kategorii ostatniego
    naruszenia, bez payloadu. Błędna partia nie jest dzielona tylko po to, by ukryć
    niespełnianie schematu.
11. Jeżeli context/output limit wystąpi dla pojedynczego tekstu, powstaje terminalny
    `TranslationEngineError` zamiast rekurencji bez końca.
12. Facade odrzuca cały wynik danego silnika i uruchamia istniejący fallback dla
    całego pliku. Nie ma zapisu częściowego ani podstawiania źródła jako sukcesu.

### Zachowanie UI

- W sekcji tłumaczenia dla aktywnego `llm` pozostaje jedno pole `Styl` o ID
  `llm_translation_style`.
- Pola `Prompt` i `Moduły promptu` znikają.
- `allowed_values` powstaje ze skanu zasobów podczas budowania catalog snapshot;
  `SettingsController.render()` nie czyta dysku/paczki.
- Jeden styl nadal jest widocznym, pojedynczym wyborem; nie ukrywać pola.
- Więcej stylów daje zwykły wybór istniejącym edytorem string choices.
- Nieprawidłowy zapisany wybór jest znormalizowany przed renderem zgodnie z regułą
  persistence, więc UI nie pokazuje wiszącej wartości.
- `Plików LLM jednocześnie` pokazuje `4` domyślnie i nie pozwala przekroczyć `4`.
- Nie dodawać automatycznego doboru stylu, opisu gatunku ani edycji promptu w UI.

### Edge cases i wymagany dowód

| Przypadek | Oczekiwane zachowanie | Dowód |
| --- | --- | --- |
| zero tekstów | zero completion requests, pusty wynik | unit |
| powtórzone teksty | osobne ID i osobne wyniki | unit |
| tekst z `\n`, cudzysłowem i Unicode | poprawny roundtrip JSON bez ASCII escaping treści | unit |
| JSON z code fence/prefiksem/sufiksem | odrzucenie całej odpowiedzi | parametrized unit |
| `NaN`, duplicate key, bool jako ID | odrzucenie jako niepoprawny kontrakt | parametrized unit |
| brak/dodatkowy root lub item key | odrzucenie i konkretny correction | unit |
| zła liczba, duplicate/missing/unknown/order ID | odrzucenie z oczekiwaną wartością | parametrized unit |
| pusty lub nie-string `translated` | odrzucenie | unit |
| pierwszy błąd, potem poprawny JSON | dwa requesty; drugi ma tylko ostatni retry part | unit |
| kolejne różne błędy | retry nie akumuluje starszych opisów | unit |
| retry wyczerpane | terminalny error, zero częściowego wyniku | unit/integration |
| context/output limit dla wielu tekstów | deterministyczny split, komplet kolejności | unit |
| context/output limit dla jednego tekstu | terminalny error bez pętli | unit |
| brak/empty/non-UTF8 prompt lub brak placeholdera | `TranslationConfigError` | filesystem unit |
| dodatkowy `styles/funny.md` | lista `neutral`, `funny` bez edycji rejestru | filesystem unit |
| style różniące się tylko case | jawny błąd deterministyczności | filesystem unit |
| stary settings v2 | stare pola ignorowane, `neutral`, zapis tylko schema 3 | config integration |
| zniknięty wybrany styl | neutral, inaczej pierwszy; nigdy dangling value | config unit |
| wheel | wszystkie cztery pliki `.md` są obecne i czytelne | build inspection/smoke |
| UI | tylko Styl, bez Prompt/Moduły, concurrency 4 | catalog test + human smoke |
| fallback LLM → kolejny engine | cały plik przechodzi do fallbacku | integration |

## Plan wykonania

1. Przed edycją ponownie sprawdzić branch, commit, `git status --short` oraz
   targeted baseline. Nie nadpisywać zmian worktree spoza
   `docs/work/llm-translation/`. Zanotować, czy znany failure VPN nadal jest jedynym
   failure; każde inne niepowodzenie traktować jako nowy sygnał do wyjaśnienia.

2. Najpierw zdefiniować nowy mechaniczny kontrakt w testach tłumaczenia:
   zastąpić przypadki numerowanych linii tabelą wejście/wyjście JSON, pełną macierzą
   naruszeń, kolejnością `user_parts`, retry z najnowszym błędem, wyczerpaniem retry
   oraz oddzielnym splitem dla context/output limitu. Fake completer ma zapisywać
   wszystkie `LlmCompletionRequest`, aby test sprawdzał identyczność input JSON-u i
   brak poprzedniej odpowiedzi w następnym requestcie.

3. Utworzyć `json_contract.py` jako jedynego właściciela serializacji i walidacji.
   Użyć wyłącznie stdlib `json`; jawnie odrzucić stałe spoza JSON-u i powtórzone
   klucze. Zwracać kompletną uporządkowaną listę albo typowaną prywatną diagnozę,
   nigdy `None` bez przyczyny i nigdy częściowego wyniku. Diagnozy mają wystarczyć
   do wyrenderowania konkretnego retry, lecz nie mogą przenosić surowej odpowiedzi.

4. Zastąpić prompt registry prostym loaderem zasobów paczki. Dodać cztery minimalne
   polskie pliki `.md`, z czego `retry.md` ma jeden unikalny placeholder. Loader ma
   przyjmować wstrzykiwalny root/Traversable dla testów, natomiast produkcyjnie
   używać `importlib.resources.files`. Usunąć wersje, fingerprinty, moduły, custom
   root, XML context i fallbackowe treści Pythona. `constants.py` pozostawić tylko
   z udokumentowanymi `Final` nazwami zasobów, default style, placeholderem i
   finish reasons.

5. Przepisać `LlmTranslateConfig`, `LlmCompletionRequest` i `LlmTranslateService`
   według target design. Zachować provider-agnostic DI, `engine_id`, input policy,
   batching i split limitów. Usunąć `PromptIdentity`, `PromptPurpose`, context i
   nieużywane metadane dopiero po ponownym `rg` wszystkich konsumentów. LLM ma
   ignorować `source_lang`, nie serializować języków i jawnie odrzucać wywołanie z
   `target_lang != "pl"`, ponieważ jego implementacja obsługuje wyłącznie polski,
   mimo że wspólny protokół silników nadal przyjmuje ten parametr.

6. Zmienić composition root bez naruszania `services.llm`: `_LlmCompleter` mapuje
   system i user parts na istniejące `LlmMessage/TextPart`; `_LlmTranslationEngine`
   przestaje tworzyć `PromptRegistry(config/prompts)`; runtime przekazuje
   `style_name` i `max_contract_retries`. Provider SDK i adaptery nie otrzymują
   nowego `response_format`. Zachować obecne mapowanie błędów, anulowanie, retry
   transportowe i lifecycle close.

7. Przeprowadzić migrację settings jako schema 3: usunąć stare dataclass fields i
   ich cleaner, dodać `llm_translation_style`, walidować je listą loadera, obsłużyć
   schema 1/2/3 i zachować bezpieczne defaulty pozostałych pól. Zmienić
   `RunSettingsSnapshot`, jego walidację i `_run_settings_snapshot`; usunąć stare
   wartości z każdego konstruktora testowego. Nie dotykać żadnego miejsca
   `llm_max_concurrency` poza koniecznymi aktualizacjami sąsiednich argumentów.

8. Zmienić field catalog i UI: zastąpić trzy stare specs jednym string spec
   `llm_translation_style`, którego allowed values pochodzą z loadera; zmienić
   `_TRANSLATION_FIELDS`; usunąć specjalny warunek pustych modułów. Potwierdzić, że
   catalog snapshot powstaje poza metodą renderującą i że obecny generic editor
   poprawnie zapisuje scalar string bez specjalnej gałęzi w `field_access.py`.

9. Usunąć tracked `config/prompts/`, sekcję custom prompts z `config/README.md` i
   regułę `config/prompts/**/*.txt` z `.gitignore`. Usunąć stare `.txt`, registry,
   composer i types dopiero po przełączeniu wszystkich importów. Wykonać repo-wide
   `rg` dla `PromptRegistry`, `PromptComposer`, `PromptContext`, `PromptIdentity`,
   `llm_prompt_id`, `llm_style_id`, `llm_module_ids`, `numbered_output`,
   `LINE_PATTERN` i `config/prompts`; w aktywnym kodzie/testach/runtime docs wynik
   ma być pusty. Trafienia w historycznych planach pozostają świadomie bez edycji.

10. Zaktualizować lokalne `AGENTS.md` silnika LLM tak, aby opisywało JSON,
    ownership promptów, retry i zakaz metadanych zamiast starego numerowanego
    protokołu. Nie dopisywać historii zmiany. Sprawdzić, że sprzężony `CLAUDE.md`
    nadal wskazuje tę instrukcję i nie tworzyć drugiej kopii zasad.

11. Uzupełnić testy config/application/UI o schema 3, ignorowanie legacy,
    dynamiczną listę stylów, invalid style fallback, roundtrip nowego pola, snapshot
    runtime i brak starych specs. Zachować osobne regresje zakresu concurrency
    `1..4`, domyślnego `4` i schedulerowego limitu `4`. Testy promptów mają używać
    tymczasowego resource root, nie zapisywać do prawdziwego modułu ani `config/`.

12. Uruchomić targeted testy po każdej spójnej zmianie ownera, a po integracji
    wszystkie wskazane targeted testy razem. Każdy lokalny błąd zgodny z designem
    poprawić w tej samej iteracji i powtórzyć najmniejszy test, który go wykrył.
    Jeżeli failure wymaga zmiany schematu, ownership, retry semantics albo zakresu,
    zatrzymać implementację zamiast obchodzić test.

13. Zbudować sdist i wheel przez `uv build`. Sprawdzić zawartość wheel oraz
    odczytać zasoby przez `importlib.resources` z instalacji artefaktu, nie tylko z
    checkoutu. Brak któregokolwiek `.md` poprawić w konfiguracji `uv_build` bez
    ręcznego kopiowania plików po buildzie. Potwierdzić, że usunięte `.txt` i
    `config/prompts` nie weszły do artefaktu.

14. Uruchomić pełne bramki repo na wymaganych rootach, następnie smoke CLI i human
    acceptance. Porównać pełny pytest z baseline: wymagany jest brak nowych
    failures; znany failure VPN raportować oddzielnie i nie maskować. Nie tworzyć
    commita ani PR bez osobnego polecenia użytkownika.

## Strategia dowodu

| Twierdzenie | Kontrola | Dlaczego wystarcza |
| --- | --- | --- |
| input jest dokładnym JSON-em | unit na przechwyconym `user_parts[2]` + `json.loads` + exact equality | sprawdza bytes-level composition i semantykę |
| tylko pełny output przechodzi | parametrized parser tests wszystkich zakazanych kształtów | wykrywa liberalne salvage i częściowe wyniki |
| retry opisuje ostatni błąd | sekwencja dwóch różnych invalid responses i inspekcja requestów | dowodzi zastępowania, nie akumulacji |
| promptów nie ma w config/kodzie | repo-wide `rg` + doc cleanup | wykrywa drugie źródło prawdy |
| style są dynamiczne | temp resource root z jednym i wieloma `.md` + catalog test | nie opiera się na hard-coded liście |
| starszy settings działa | load v1/v2, save, reload i exact keys | dowodzi migracji oraz usunięcia legacy |
| wheel zawiera zasoby | `uv build`, lista wheel, importlib read po instalacji | checkout-only test nie wystarczyłby |
| fallback nie zapisuje części | facade integration z failing LLM i succeeding fallback | sprawdza granicę transakcyjną pliku |
| providerzy nie zostali naruszeni | pełne `tests/services/llm/` | request mapping pozostaje kompatybilny |
| concurrency nadal max 4 | config/planning/scheduler tests + human UI | chroni zgłoszony inwariant użytkownika |

### Targeted automated checks

```text
uv run pytest tests/services/translation/test_translation_llm.py tests/services/translation/test_translation_prompts.py tests/services/translation/test_translation_service.py
uv run pytest tests/config/test_user_settings.py tests/config/test_field_catalog.py tests/config/test_field_access.py
uv run pytest tests/application/test_planning.py tests/application/test_service.py tests/application/test_runtime_config.py tests/application/test_settings_update.py tests/application/test_scheduler.py
uv run pytest tests/services/llm/
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv build
```

Po targeted checks wykonać pełne bramki dokładnie z roota repozytorium:

```text
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

### Human acceptance

```text
Uruchom: uv run anishift
Zrób: Ustawienia -> Tłumaczenie; wybierz silnik LLM.
Oczekuj: widoczne jest jedno pole „Styl”, nie ma „Prompt” ani „Moduły promptu”.
Oczekuj: „Plików LLM jednocześnie” pokazuje 4 i nie pozwala ustawić 5.
Zmień: wybierz dostępny styl, zapisz, ponownie otwórz ustawienia.
Oczekuj: wybór przetrwał restart panelu.
Zwróć uwagę: brak błędu odczytu zasobów, brak ścieżek promptów w UI.
PASS: wszystkie powyższe obserwacje są zgodne.
```

Realne wywołanie płatnego modelu nie jest obowiązkową bramką planu. Jeżeli
użytkownik jawnie je dopuści i ma skonfigurowane credentials, dodatkowy smoke ma
użyć krótkich dwóch napisów oraz potwierdzić kompletny polski wynik; nie wolno
drukować requestu, promptów ani response body w raporcie.

## Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Kiedy eskalować |
| --- | --- | --- | --- |
| prompt `.md` nie wchodzi do wheel | brak na liście artefaktu/importlib failure | jawna konfiguracja package data w `uv_build`, ponowny build | gdy backend nie wspiera bez zmiany technologii |
| provider skleja `TextPart` | adapter test pokazuje join | zaakceptować join wyłącznie przy zachowaniu kolejności i system role; input nadal serializowany jako dokładny part | gdy provider wymaga otoczenia JSON tekstem |
| mnożenie transport × contract retry zwiększa koszt | test liczby calls i analiza ustawienia | zachować rozdział mechanizmów; raportować maksymalny bound | gdy wymagany jest wspólny globalny budget |
| stary config wskazuje custom style | schema 2 zawiera stary `llm_style_id` | ignorować i wybrać neutral zgodnie ze spec | gdy użytkownik zażąda migracji treści custom promptów |
| invalid JSON pojawia się często bez native mode | testy są zielone, realny model często retry | zebrać dowód per model; osobno zaplanować capability structured output | nie dodawać heurystyki w tym planie |
| historyczna dokumentacja wspomina stary registry | `rg` trafia w zamknięte plany/specs | pozostawić historię; nowa spec jest authority | gdy aktywny kod generuje UI na podstawie starego dokumentu |
| baseline VPN blokuje pełne pytest | dokładnie ten sam pojedynczy failure | udokumentować bez pobocznej poprawki | przed commitem wrócić po osobną decyzję |

## Lokalna adaptacja

Wykonawca może zmienić nazwę prywatnego loadera, prywatnych diagnoz i podział
helperów między `json_contract.py` a `service.py`, jeżeli drzewo pozostaje małe,
testy chronią ten sam kontrakt, a nie powstaje rejestr, drugi source of truth ani
nowa zależność. Może też dopasować listę istniejących test files po końcowym `rg`,
lecz nie może pominąć żadnego twierdzenia ze strategii dowodu.

## Materialna zmiana

Zatrzymania i aktualizacji specyfikacji oraz planu wymaga:

- obowiązkowe native structured output;
- przechowywanie promptów poza modułem lub dodanie custom prompt directory;
- więcej niż jeden wybierany prompt systemowy/tłumaczeniowy;
- inny język docelowy;
- zmiana schematu wejścia/wyjścia albo nazwy persisted style field;
- inne zasady retry, splitu lub częściowego wyniku;
- zmiana maksymalnej współbieżności `4`;
- nowa zależność lub zmiana ownership między `translation` i `services.llm`.

## Definition of Done

- [x] wszystkie warunki końcowe są spełnione;
- [x] nowe targeted testy przechodzą;
- [ ] pełne bramki nie mają nowych failures względem zapisanego baseline;
- [x] wheel zawiera i odczytuje wszystkie obowiązkowe prompty `.md`;
- [x] repo-wide scan nie znajduje legacy w aktywnym kodzie, testach ani runtime docs;
- [ ] human acceptance ustawień przechodzi;
- [x] nie wykonano zmian poza zakresem ani ukrytej materialnej adaptacji;
- [x] finalny raport podaje zmienione pliki, dokładne wyniki kontroli, stan znanego
  baseline failure, stan Git i wszelkie odchylenia;
- [x] nie utworzono commita ani PR bez osobnej zgody użytkownika.

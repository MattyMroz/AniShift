# Etap 5 — LLM — plan implementacji

Kompletny plan budowy ogólnej domeny LLM, sześciu providerów, modułowych
promptów i współbieżnej integracji z tłumaczeniem. Plan jest adaptacją dobrych
granic MangaShift do synchronicznego AniShift, a nie mechaniczną kopią.

> **Stan źródeł:** 2026-07-26, branch `main`, commit `9823644`.
> **Stan realizacji:** `IMPLEMENTED` na branchu `feature/llm-service` —
> dwie rundy review, pełne bramki repo, wheel oraz live smoke Gemini,
> OpenRouter i 600 linii one-shot zakończone powodzeniem.
> **Dokument wykonawczy:** kod aktualnego AniShift ma pierwszeństwo przed
> starszym audytem i planami. Ten plik nie oznacza, że etap został wdrożony.
>
> **Bramka wymagań:** [`etap-5-wymagania.md`](etap-5-wymagania.md) ma status
> `APPROVED — 2026-07-26` i jest źródłem prawdy dla zachowania produktu.
> Rozdział 3 poniżej zapisuje przyjęte decyzje P4–P13. Implementacja jest
> odblokowana, ale każda fala musi przejść własne testy i pełne bramki repo.

## 1. Wynik końcowy

Po zakończeniu etapu:

- `/settings` pozwala wybrać translation engine `llm`, jednego z sześciu
  providerów i sugerowany albo dowolny własny `provider_model_id`;
- pipeline tworzy ogólny, synchroniczny `LlmService`, ale translation zna tylko
  mały protokół `LlmCompleter`;
- pipeline uruchamia blokujące requesty w `ThreadPoolExecutor` z domyślnym
  `llm_max_concurrency=4`, bez zmiany publicznych kontraktów na async;
- zwykły strumień do 1000 niepustych linii wykonuje jedno completion;
- odpowiedź `[N]` przechodzi ścisłą walidację, jeden repair i adaptacyjny podział
  na stabilne połowy;
- błąd transportu uruchamia kontrolowany retry i circuit breaker; trwała awaria
  pauzuje nowe zadania i oferuje userowi `settings` albo `finish`;
- niepoprawny wynik modelu nigdy nie zostaje cicho uznany za tłumaczenie;
- `spoken` i tekstowe `displayed` jednego pliku tworzą jeden chronologiczny
  strumień wejściowy, dzięki czemu tytuły i znaki zachowują sąsiedni kontekst;
- Google i DeepL nadal deduplikują oba strumienie; LLM zachowuje każde
  wystąpienie `spoken`, a identyczne `displayed` deduplikuje;
- prompty są zasobami `.txt` wykrywanymi automatycznie z paczki i
  `config/prompts/`, składanymi deterministycznie;
- domyślny provider/model to Gemini `gemini-3.5-flash-lite`;
- korekta gotowego tłumaczenia nie wchodzi do Etapu 5;
- import `anishift.services.llm` nie importuje żadnego SDK providera;
- cały etap działa offline na fake'ach, a realna sieć jest potrzebna wyłącznie
  do ręcznych smoke testów.

## 2. Źródła prawdy i pierwszeństwo

### 2.1. Źródła repozytorium

1. Zaakceptowane decyzje z
   [etap-5-wymagania.md](etap-5-wymagania.md).
2. Aktualny kod pod `anishift/` i aktualne testy jako źródło faktów o stanie
   wejściowym, nie jako prawo do nadpisania wymagań.
3. [plan-anishift.md](plan-anishift.md).
4. [etap-5-llm.md](etap-5-llm.md) jako historyczny kierunek, nie gotowa
   specyfikacja.
5. [etap-3-plan.md](etap-3-plan.md) jako wzorzec szczegółowości planu.
6. [service-standard.md](../reference/mangashift-architecture/service-standard.md).
7. Pozostałe dokumenty z
   [mangashift-architecture](../reference/mangashift-architecture/) oraz
   [audyt-mm-avh](../reference/audyt-mm-avh/).
8. Fakty z MangaShift pod `../MangaShift/mangashift/`.

`audyt-mm-avh/audyt-pelny.md` jest kompilacją rozdziałów audytu. Nie jest
traktowany jako osobne, niezależne źródło decyzji.

### 2.2. Oficjalne źródła providerów

- [OpenAI — modele](https://developers.openai.com/api/docs/models)
- [OpenAI Python SDK](https://github.com/openai/openai-python)
- [Anthropic Python SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python)
- [Anthropic Messages API](https://platform.claude.com/docs/en/api/python/messages/create)
- [Gemini generate content](https://ai.google.dev/api/generate-content)
- [Google Gen AI Python SDK](https://googleapis.github.io/python-genai/)
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
- [OpenRouter quickstart](https://openrouter.ai/docs/quickstart)
- [OpenRouter errors](https://openrouter.ai/docs/api/reference/errors-and-debugging)

Model IDs oraz parametry SDK trzeba ponownie sprawdzić bezpośrednio przed
implementacją. Listy sugestii są snapshotem UX, nigdy walidatorem.

### 2.3. Reguła konfliktu

Jeżeli źródła się różnią:

1. zaakceptowane wymaganie wygrywa z planem i zastanym zachowaniem;
2. aktualny kod wygrywa z opisem starego stanu;
3. oficjalna dokumentacja SDK wygrywa z implementacją MangaShift;
4. architektura AniShift wygrywa z rozwiązaniem MangaShift przeznaczonym dla
   REST, async, bazy, SecretsStore albo lokalnego runtime modeli.

## 3. Przyjęte rozstrzygnięcia P4–P13

Poniższe punkty są zapisem decyzji usera rozwiniętym do postaci wykonawczej.
W razie konfliktu pierwszeństwo ma dokument wymagań.

### 3.1. P4 — system promptów

**Decyzja:**

- etap 5 dostarcza wbudowane, wersjonowane zasoby `.txt`;
- aplikacja wykrywa własne `.txt` z `config/prompts/{tasks,styles,modules}/`;
- user wybiera `prompt_id` i `style_id`;
- user nie edytuje wielostronicowej treści w `/settings`;
- dodanie własnego promptu nie wymaga zmiany kodu;
- JSON przechowuje wyłącznie ustawienia i identyfikatory, nie prompty;
- Markdown nie jest formatem assetów promptów;
- dodatkowy prompt nie oznacza dodatkowego wywołania modelu;
- edytor promptów i automatyczne otwieranie Notatnika/`$EDITOR` są odłożone.

`.txt` jest wybrany zamiast:

| Format | Decyzja | Powód |
|---|---|---|
| `.md` | odrzucony | składnia może zostać pomylona z semantyką promptu; plain text wystarcza |
| `.json` | odrzucony dla treści | wieloliniowy tekst wymaga ucieczek i jest trudny w review |
| stała w `.py` | odrzucona dla długich treści | miesza content z kodem i utrudnia edycję |
| `.txt` | przyjęty | brak narzuconej składni, czytelny diff, działa z `importlib.resources` |

### 3.2. P5 — lifecycle

**Decyzja:** publiczny kontrakt pozostaje synchroniczny i używa synchronicznych
klientów SDK:

- `openai.OpenAI`;
- `anthropic.Anthropic`;
- `google.genai.Client`.

Nie powstaje `asyncio.run()` ani osobna pętla event loop. Pipeline wykonuje
blokujące requesty przez `ThreadPoolExecutor`, ponieważ są I/O-bound, a repo ma
już sprawdzony model wątków. Domyślne `llm_max_concurrency=4`.

Każdy aktywny worker ma własny lifecycle klienta. Limiter i circuit breaker
providera są współdzielone i thread-safe. `LlmService` tworzy wybrany engine
dopiero przy pierwszym `complete()` i zamyka go przez `close()`/context manager.

### 3.3. P6 — retry a repair

**Decyzja:** retry transportowe i repair outputu są rozłączne:

- `LlmService` ponawia tylko błędy oznaczone `TransientError`;
- SDK mają wyłączone własne automatyczne retry, aby nie mnożyć prób;
- adapter translation ponawia tylko poprawę struktury odpowiedzi;
- repair nie ponawia auth, model-not-found, zły endpoint ani context-length;
- jeden repair naprawia wyłącznie strukturę odpowiedzi;
- context-length, output-length albo nieskuteczny repair dzielą batch na dwie
  stabilne połowy zamiast ponawiać identyczny request;
- circuit breaker po 429/przejściowej awarii zatrzymuje uruchamianie nowych
  requestów, respektuje `Retry-After`, a po sukcesie odbudowuje współbieżność
  `1 → 2 → 4`;
- po wyczerpaniu prób provider jest wyłączony dla bieżącego uruchomienia;
- domyślna ścieżka zwykłego pliku to jeden request per strumień.

### 3.4. P7 — błędy

**Decyzja:** każdy provider mapuje swoje SDK na wspólną hierarchię LLM.
Wyższe warstwy nigdy nie importują wyjątków SDK.

| Klasa LLM | Charakter | Retry | Kod |
|---|---|---:|---|
| `LlmConfigError` | fatal | nie | `LLM_CONFIG_INVALID` |
| `LlmAuthError` | fatal | nie | `LLM_AUTH_FAILED` |
| `LlmModelError` | fatal | nie | `LLM_MODEL_INVALID` |
| `LlmContextLengthError` | fatal | nie | `LLM_CONTEXT_EXCEEDED` |
| `LlmQuotaError` | fatal | nie | `LLM_QUOTA_EXHAUSTED` |
| `LlmPaymentError` | fatal | nie | `LLM_PAYMENT_REQUIRED` |
| `LlmRequestError` | fatal | nie | `LLM_REQUEST_FAILED` |
| `LlmRateLimitError` | transient | tak | `LLM_RATE_LIMITED` |
| `LlmTimeoutError` | transient | tak | `TIMEOUT` |
| `LlmProviderUnavailableError` | transient | tak | `LLM_PROVIDER_UNAVAILABLE` |
| `LlmCancelledError` | fatal | nie | `CANCELLED` |

`MOD anishift/errors.py` dodaje brakujące wartości
`LLM_CONFIG_INVALID`, `LLM_MODEL_INVALID`, `LLM_CONTEXT_EXCEEDED`,
`LLM_QUOTA_EXHAUSTED`, `LLM_PAYMENT_REQUIRED` i `LLM_RATE_LIMITED`;
istniejących kodów nie zmieniać.
W `services/llm/errors.py` klasy fatal dziedziczą po `LlmError` i
`FatalError`, transient po `LlmError` i `TransientError`.
`retry_after_s` jest jawnym atrybutem `LlmRateLimitError` oraz
`LlmProviderUnavailableError`, ponieważ provider może zwrócić `Retry-After`
także przy 503; nie chować tej wartości w parsowanym stringu. Każdy adapter
buduje `ErrorContext` z komunikatem bez body requestu, klucza i pełnego response
payloadu oraz z bezpieczną, actionable `suggestion`.

### 3.5. P8 — trwała awaria i kolejka

**Decyzja:** automatyczny płatny fallback providera jest niedozwolony.

- odkryte pliki trafiają do kolejki w naturalnej kolejności;
- zakończona ekstrakcja natychmiast udostępnia plik tłumaczeniu;
- rozpoczęte requesty mogą się zakończyć, ale po trwałej awarii nie startują nowe;
- terminal pokazuje liczbę gotowych i oczekujących plików;
- `settings` otwiera istniejący panel, waliduje nowego providera/model i wznawia
  tylko niewykonane pliki;
- plik, który ujawnił awarię, ma pierwszeństwo, potem wraca naturalna kolejność;
- `finish` kończy z gotowymi plikami i oznacza pozostałe jako niewykonane;
- wykonane pliki nigdy nie są tłumaczone ponownie po wznowieniu.

Błąd transportu albo nieodwracalnie niepoprawny output LLM jest mapowany na
`TranslationError`. Nie jest zamieniany na `BatchedLine(source, ok=False)`.

### 3.6. P9 — kontekst i dedup

**Decyzja na Etap 5:**

- Google i DeepL deduplikują oba strumienie;
- LLM zachowuje każde wystąpienie `spoken`;
- LLM deduplikuje identyczny tekst `displayed`;
- whitespace nie trafia do modelu, ale zachowuje pozycję w wyniku;
- kontekstem LLM są uporządkowane linie bieżącego batcha oraz jawne opcjonalne
  dane `PromptContext`;
- etap 5 nie zgaduje płci, mówcy ani sceny z timingu lub stylu;
- nie implementuje cross-batch memory;
- nie wysyła obrazu, audio ani wideo;
- opcjonalny glosariusz i kontekst mają limity znaków oraz liczby elementów.

Ta decyzja jest chirurgiczna: nie zmienia publicznego `list[str]` wszystkich
engine'ów na ciężki model napisów. Pełny occurrence object będzie potrzebny
dopiero, gdy realny konsument wymaga timingu, mówcy lub sceny.

### 3.7. P10 i P11 — korekta

**Decyzja:** korekta gotowego tłumaczenia nie wchodzi do Etapu 5.

Bez dodatkowego kontekstu podwaja czas i koszt, ale nie rozwiązuje błędów płci,
relacji ani znaczenia sceny. Nie powstają: correction service, correction prompt,
toggle, call purpose ani testy korekty. Temat pozostaje świadomie odroczony.

### 3.8. P12 — usage i koszt

**Decyzja:**

- `LlmResponse` przechowuje input/output/total tokens, latency, finish reason,
  providera i model;
- koszt jest raportowany tylko wtedy, gdy provider zwraca go bezpośrednio;
- etap 5 nie utrzymuje własnej tabeli cen;
- `pipeline/types.py` definiuje content-free `LlmCallRecord` z purpose,
  providerem, modelem, usage, latency, finish reason, prompt identity i
  opcjonalnym kodem błędu;
- `FileOutcome.llm_calls` rozdziela translation i repair przez `purpose`, bez
  importowania tych typów do `FileTranslation`;
- logi nie zapisują promptu, napisów ani kluczy;
- każdy call record przechowuje `prompt_id`, `prompt_version`, `style_id`
  i `prompt_fingerprint`;
- partial failure nie jest ukrywany w licznikach.

Nie obiecywać usage nieudanej próby, jeżeli provider go nie zwrócił. Podsumowanie
pokazuje liczbę completion, repair i retry, dostępne tokeny oraz liczbę
wykonanych/niewykonanych plików. Domyślnie nie zapisuje osobnego raportu JSON.

### 3.9. P13 — Definition of Done

**Decyzja:** obowiązkowe są testy offline wszystkich providerów, kontraktu,
registry, prompt composition, retry, circuit breakera, kolejki i pipeline.
Live smoke Gemini `gemini-3.5-flash-lite` oraz OpenRouter jest ręczny i
warunkowy — brak klucza nie psuje CI.

## 4. Czego nie kopiujemy z MangaShift

### 4.1. Odrzucone elementy

- async facade i async engine protocol;
- streaming bez konsumenta;
- `validate_key()` bez konsumenta;
- heurystyczny `count_tokens()` bez konsumenta;
- `SecretsStore`, baza i runtime freshness;
- warstwy REST, CLI LLM i frontend picker;
- `_portable.py`, llama-server, VRAM i lokalne backendy;
- `ProviderConfig.default_model`;
- `SUPPORTED_MODELS` jako zamknięta allowlista;
- sześć kopii `config.py` i `api_backend.py`, które różnią się głównie nazwą;
- provider-specific retry schowany w różnych engine'ach;
- ręczne przekształcanie system promptu Gemini w zwykłą wiadomość user;
- łapanie `Exception` w per-line fallbacku i ciche zwracanie source.

### 4.2. Elementy recyklingowane i poprawiane

- ogólna domena `services/llm`;
- lazy registry;
- mały publiczny facade;
- osobny adapter composition pomiędzy LLM i translation;
- shared OpenAI-compatible transport;
- provider-specific mapping Anthropic i Gemini;
- caller-owned `engine_id` i `provider_model_id`;
- engine identity zgodne z registry;
- provider SDK zamknięty we własnym pakiecie;
- strict output protocol w adapterze translation.

## 5. Docelowa architektura

### 5.1. Kierunek zależności

```text
CLI /settings
    │
    ▼
UserSettings + env Settings
    │
    ▼
pipeline/runner.py ───────► pipeline/llm_queue.py
    │                              │
    │                              ├── ThreadPoolExecutor(max_workers=4)
    │                              ├── natural-order pending queue
    │                              └── shared limiter + circuit breaker
    │
    ├──────────────────────► pipeline/llm_runtime.py
    │                              │
    │                              ▼
    │                      services/llm/LlmService
    │                              │
    │                              ▼
    │                      lazy provider registry
    ▼
TranslationService ───────► TranslationEngineFactory
                                    │
                                    ├── google
                                    ├── deepl
                                    └── LlmTranslateService
                                              │
                                              ▼
                                      LlmCompleter Protocol
```

### 5.2. Dozwolone importy

- `pipeline` może importować `services.llm` i `services.translation`;
- `pipeline/llm_queue.py` jest jedynym właścicielem współbieżności plików,
  priorytetu retry oraz interakcji `settings`/`finish`;
- `translation` może znać wyłącznie własny `LlmCompleter`;
- `services.llm` nie importuje `translation`, `pipeline`, `cli` ani config app;
- provider importuje tylko wspólne typy/config/errors LLM;
- jeden provider nie importuje drugiego;
- cztery OpenAI-compatible providery używają wspólnego modułu domenowego;
- prompt composer należy do translation LLM, nie do ogólnego LLM.

### 5.3. Zakazane importy

```text
services/translation  -X-> services/llm
services/llm          -X-> services/translation
services/llm          -X-> pipeline
provider A            -X-> provider B
config/user_settings  -X-> ciężkie SDK
prompt assets         -X-> provider SDK
```

### 5.4. Publiczny kontrakt LLM

```python
@dataclass(frozen=True, slots=True)
class TextPart:
    text: str


type LlmContentPart = TextPart


@dataclass(frozen=True, slots=True)
class LlmMessage:
    role: LlmRole
    parts: tuple[LlmContentPart, ...]


@dataclass(frozen=True, slots=True)
class LlmRequest:
    messages: tuple[LlmMessage, ...]


@dataclass(frozen=True, slots=True)
class LlmConfig:
    engine_id: str
    provider_model_id: str
    api_key: str = field(default="", repr=False)
    base_url: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    timeout_s: float = 60.0
    max_retries: int = 2
```

`LlmContentPart` jest celowo dziś aliasem jednego typu. Dodanie `ImagePart`,
`AudioPart` albo `VideoPart` poszerzy union i mapping providerów, ale nie zmieni
`LlmMessage`, `LlmRequest`, registry ani lifecycle.

### 5.5. Publiczna fasada

```python
with LlmService(config) as service:
    response = service.complete(request)
```

Właściwości:

- constructor nie importuje SDK i nie tworzy klienta;
- pierwsze `complete()` lazy-loaduje tylko wybrany engine;
- kolejne wywołania w tym samym kontekście używają tego samego klienta;
- `close()` jest idempotentne;
- wywołanie po `close()` nie reaktywuje po cichu usługi;
- brak globalnego active provider/model;
- brak singletona i globalnego cache klientów;
- jedna instancja fasady nie jest współdzielona pomiędzy workerami;
- limiter i circuit breaker są współdzielonym, thread-safe stanem providera,
  przekazywanym jawnie do instancji fasady.

Dokładna semantyka lifecycle:

- `__enter__()` zwraca fasadę bez tworzenia klienta;
- `complete(request, cancel=...)` tworzy engine i jego sync client dopiero przy
  pierwszej realnej próbie;
- `is_available` oznacza „konfiguracja ma wymagany key/base URL
  (`openai_compatible` wymaga tylko URL) i usługa nie
  została zamknięta”, a nie sieciowy health check ani poprawność klucza;
- brak klucza daje `False` przed requestem i `LlmAuthError` przy wymuszonym
  `complete()`;
- `close()` zamyka klienta, czyści referencje i ustawia trwały stan `_closed`;
- kolejne `close()` jest no-op, ale `complete()` po zamknięciu rzuca fatalny
  `LlmConfigError`; use-after-close nie jest chwilową awarią providera i nie
  może uruchamiać retry;
- engine i fasada muszą mieć jawnie typowane atrybuty `_engine`/`_client` oraz
  `_closed`; nie używać `Any` poza wąską granicą obiektu SDK.

## 6. Docelowe drzewo plików

Legenda:

- `ADD` — nowy plik;
- `MOD` — istniejący plik do zmiany;
- `DEL` — plik usuwany;
- `KEEP` — sprawdzony, bez planowanej zmiany.

```text
.gitignore                                                       MOD
config/
└── README.md                                                    MOD
anishift/
├── errors.py                                                   MOD
├── bootstrap.py                                                KEEP
├── config/
│   ├── settings.py                                             KEEP
│   └── user_settings.py                                        MOD
├── cli/
│   ├── AGENTS.md                                                MOD
│   ├── CLAUDE.md                                                MOD
│   └── settings_panel.py                                       MOD
├── pipeline/
│   ├── AGENTS.md                                                MOD
│   ├── CLAUDE.md                                                MOD
│   ├── types.py                                                MOD
│   ├── runner.py                                               MOD
│   ├── llm_runtime.py                                          ADD
│   └── llm_queue.py                                            ADD
└── services/
    ├── llm/                                                    ADD
    │   ├── AGENTS.md                                           ADD
    │   ├── CLAUDE.md                                           ADD
    │   ├── __init__.py                                         ADD
    │   ├── config.py                                           ADD
    │   ├── errors.py                                           ADD
    │   ├── protocols.py                                        ADD
    │   ├── types.py                                            ADD
    │   ├── service.py                                          ADD
    │   ├── _retry.py                                           ADD
    │   └── engines/
    │       ├── __init__.py                                     ADD
    │       ├── _openai_compatible.py                           ADD
    │       ├── anthropic/
    │       │   ├── __init__.py                                 ADD
    │       │   ├── constants.py                                ADD
    │       │   └── service.py                                  ADD
    │       ├── deepseek/
    │       │   ├── __init__.py                                 ADD
    │       │   ├── constants.py                                ADD
    │       │   └── service.py                                  ADD
    │       ├── gemini/
    │       │   ├── __init__.py                                 ADD
    │       │   ├── constants.py                                ADD
    │       │   └── service.py                                  ADD
    │       ├── openai/
    │       │   ├── __init__.py                                 ADD
    │       │   ├── constants.py                                ADD
    │       │   └── service.py                                  ADD
    │       ├── openai_compatible/
    │       │   ├── __init__.py                                 ADD
    │       │   ├── constants.py                                ADD
    │       │   └── service.py                                  ADD
    │       └── openrouter/
    │           ├── __init__.py                                 ADD
    │           ├── constants.py                                ADD
    │           └── service.py                                  ADD
    └── translation/
        ├── AGENTS.md                                            MOD
        ├── CLAUDE.md                                            MOD
        ├── __init__.py                                         MOD
        ├── dedup.py                                            MOD
        ├── protocols.py                                        MOD
        ├── service.py                                          MOD
        ├── types.py                                            MOD
        ├── engines/
        │   ├── AGENTS.md                                        MOD
        │   ├── CLAUDE.md                                        MOD
        │   ├── __init__.py                                     MOD
        │   ├── google/service.py                               MOD
        │   ├── deepl/service.py                                MOD
        │   └── llm/
        │       ├── AGENTS.md                                    MOD
        │       ├── CLAUDE.md                                    MOD
        │       ├── config.py                                   MOD
        │       ├── constants.py                                MOD
        │       ├── service.py                                  MOD
        │       └── prompts/
        │           ├── __init__.py                             ADD
        │           ├── composer.py                             ADD
        │           ├── registry.py                             ADD
        │           ├── types.py                                ADD
        │           └── assets/
        │               ├── tasks/
        │               │   └── anime_translation_v1.txt        ADD
        │               ├── styles/
        │               │   └── natural_polish_v1.txt           ADD
        │               ├── contracts/
        │               │   ├── numbered_output_v1.txt           ADD
        │               │   └── repair_numbered_output_v1.txt    ADD
        │               └── modules/                             ADD
tests/
├── config/
│   └── test_user_settings.py                                   MOD
├── cli/
│   └── test_settings_panel.py                                  ADD
├── pipeline/
│   ├── test_pipeline_runner.py                                 MOD
│   ├── test_pipeline_translate.py                              MOD
│   ├── test_llm_runtime.py                                     ADD
│   └── test_llm_queue.py                                       ADD
└── services/
    ├── llm/                                                    ADD
    │   ├── conftest.py                                         ADD
    │   ├── test_llm_registry.py                                ADD
    │   ├── test_llm_service.py                                 ADD
    │   ├── test_llm_retry.py                                   ADD
    │   ├── test_openai_compatible.py                           ADD
    │   ├── test_openai.py                                      ADD
    │   ├── test_deepseek.py                                    ADD
    │   ├── test_openrouter.py                                  ADD
    │   ├── test_anthropic.py                                   ADD
    │   └── test_gemini.py                                      ADD
    └── translation/
        ├── test_translation_dedup.py                            MOD
        ├── test_translation_registry.py                         MOD
        ├── test_translation_service.py                          MOD
        ├── test_translation_llm.py                              MOD
        └── test_translation_prompts.py                          ADD
```

### 6.1. Brak usuwanych plików

W tym etapie nie ma planowanej operacji `DEL`.

### 6.2. Pliki świadomie bez zmian

- `pyproject.toml` — trzy SDK już są zależnościami;
- `uv.lock` — brak nowej zależności;
- `.env.example` — ma wszystkie klucze i compatible base URL;
- `anishift/config/settings.py` — ma wszystkie sekrety;
- `anishift/bootstrap.py` — `AppContext` już niesie oba rodzaje settings.

`config/prompts/` jest katalogiem runtime usera i musi być gitignored. Kod nie
tworzy przykładowych promptów usera; tworzy brakujące kontrolowane podfoldery
`tasks/`, `styles/`, `modules/` przy pierwszym użyciu albo traktuje ich brak jako
pusty registry. `config/README.md` dokumentuje tę lokalizację bez kopiowania
treści promptów.

Nie dodawać `tests/services/llm/__init__.py`. Zgodnie z
`tests/AGENTS.md` nowe katalogi testowe pozostają bez pakietyzacji; wspólne fake
clients i fixtures żyją w lokalnym `conftest.py`. Nowe i zmieniane pary
`AGENTS.md`/`CLAUDE.md` tworzyć oraz synchronizować zgodnie ze skillem
`agents-md`, bez rozbieżnych instrukcji.

Jeżeli test zbudowanego wheel wykaże brak assetów `.txt`, dopiero wtedy dodać
minimalną konfigurację include w `[tool.uv.build-backend]`. Nie zmieniać jej
„na zapas”.

## 7. Specyfikacja domeny `services/llm`

### 7.1. `types.py`

Dodać:

- `LlmRole(StrEnum)` — `SYSTEM`, `USER`, `ASSISTANT`;
- `TextPart`;
- `LlmContentPart`;
- `LlmMessage`;
- `LlmRequest`;
- `LlmUsage`;
- `LlmResponse`.

Pola wyniku są jednoznaczne:

```python
@dataclass(frozen=True, slots=True)
class LlmUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reported_cost: float | None = None


@dataclass(frozen=True, slots=True)
class LlmResponse:
    text: str
    engine_id: str
    provider_model_id: str
    finish_reason: str
    latency_ms: float
    usage: LlmUsage
```

Inwarianty:

- `TextPart.text` nie może być pusty;
- request musi mieć co najmniej jedną wiadomość user;
- wszystkie części zachowują kolejność;
- response `provider_model_id` jest wartością faktycznie użytą;
- usage może być częściowe: brak danych to `None`, nie fałszywe `0`;
- `total_tokens` bierze wartość providera, a gdy jej brak liczy się tylko wtedy,
  gdy input i output są oba znane;
- `reported_cost` jest ustawiane wyłącznie z jawnej wartości zwróconej przez
  providera; brak oznacza `None`, nigdy estymację z lokalnej tabeli cen.

Inwarianty są egzekwowane w `__post_init__`, nie tylko opisane w docstringu.
Nieprawidłowy request rzuca `LlmRequestError`; `api_key` ma
`field(repr=False)`, aby zwykły `repr(config)` nie ujawniał sekretu.

### 7.2. `config.py`

`LlmConfig` jest `frozen=True, slots=True`.

Walidacja:

- `engine_id` niepusty;
- `provider_model_id` niepusty;
- `timeout_s > 0`;
- `max_retries >= 0`;
- `max_output_tokens is None or > 0`;
- `temperature is None or 0 <= value <= 2`;
- `top_p is None or 0 <= value <= 1`;
- `base_url`, podobnie jak key, może być pusty w samym value object;
- `LlmService.is_available` zwraca wtedy `False`, a wymuszone completion dla
  `openai_compatible` rzuca `LlmConfigError`; dzięki temu samo sprawdzenie
  dostępności nie wymaga konstruowania niepoprawnego configu drugi raz;
- pozostałe base URL mogą mieć provider default;
- model nie jest sprawdzany w `SUGGESTED_MODEL_IDS`.

Parametry opcjonalne wysyłać tylko, gdy nie są `None`. Jest to konieczne, bo
niektóre nowe modele odrzucają niestandardowe sampling parameters.

### 7.3. `protocols.py`

```python
@runtime_checkable
class LlmEngine(EngineInfo, Protocol):
    def complete(self, request: LlmRequest) -> LlmResponse: ...
    def close(self) -> None: ...


class LlmAttemptObserver(Protocol):
    def before_attempt(self) -> None: ...
    def on_transient_failure(self, error: LlmError) -> None: ...
    def on_success(self) -> None: ...
```

Nie dodawać:

- `initialize()`;
- `stream()`;
- `count_tokens()`;
- `validate_key()`.

Engine inicjalizuje swój klient lazy przy pierwszym completion. Publiczna
fasada nie wymaga osobnego „warm-up”.

### 7.4. `engines/__init__.py`

Registry jest jedynym źródłem prawdy:

```python
LlmEngineId = Literal[
    "anthropic",
    "deepseek",
    "gemini",
    "openai",
    "openai_compatible",
    "openrouter",
]
```

Publiczne funkcje:

- `available_engine_ids()`;
- `create_engine(config)`;
- `suggested_model_ids(engine_id)`.

`suggested_model_ids()` importuje tylko lekki `constants.py`. Nie importuje SDK.

### 7.5. Listy sugestii

Nie wpisywać do planu niezweryfikowanych, szybko starzejących się model IDs.
Przed zapisaniem constants sprawdzić oficjalny katalog każdego providera w tym
samym dniu. Rezultatem tej kontroli jest dokładna wartość
`SUGGESTED_MODEL_IDS` w sześciu lekkich `constants.py`; plan nie staje się przez
to allowlistą.

| Provider | Zawartość po weryfikacji |
|---|---|
| OpenAI | 2–4 aktualne modele ogólne wspierające text completion |
| Anthropic | 2–4 aktualne modele ogólne Claude |
| Gemini | `gemini-3.5-flash-lite` jako pierwszy default + 1–3 aktualne sugestie |
| DeepSeek | 2–4 aktualne, oficjalnie udokumentowane IDs/aliasy |
| OpenRouter | 2–4 popularne pełne slugi `vendor/model` |
| OpenAI-compatible | puste |

Reguły utrzymania:

- maksymalnie 2–4 sugestie na provider;
- tylko modele ogólne przydatne do tłumaczenia;
- żadnych setek chińskich, eksperymentalnych albo niszowych modeli;
- model usunięty z sugestii nadal może działać jako custom;
- aktualizacja listy jest prostym maintenance, nie migracją configu;
- test sprawdza typ, unikalność i niepuste stringi, nie dostępność sieciową.

Nie odrzucać oficjalnego aliasu tylko dlatego, że może wskazywać nowszy snapshot.
Sugestia ma pomagać w UI; provider jest jedynym walidatorem dostępności modelu.

### 7.6. `_retry.py`

Jeden helper LLM:

```python
def retry_transient(
    operation: Callable[[], LlmResponse],
    *,
    max_retries: int,
    observer: LlmAttemptObserver | None = None,
    cancel: threading.Event | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> LlmResponse:
    ...
```

Backoff:

- próba 0 natychmiast;
- kolejne opóźnienia deterministyczne: `1s`, `2s`, `4s`, ograniczone stałym
  capem; bez jittera, którego etap nie potrzebuje;
- `LlmRateLimitError` i `LlmProviderUnavailableError` niosą jawne
  `retry_after_s: float | None`; poprawne, nieujemne `Retry-After` zastępuje
  obliczony backoff;
- `max_retries` oznacza liczbę ponowień po pierwszej próbie;
- przed każdą próbą sprawdzić cancel;
- przed każdą próbą wywołać `observer.before_attempt()`, aby współdzielony
  circuit mógł zablokować start albo dopuścić pojedynczy probe;
- po transient error wywołać `observer.on_transient_failure(error)`;
- po sukcesie wywołać `observer.on_success()`;
- podczas backoffu użyć `cancel.wait(delay)` zamiast nieprzerywalnego
  `time.sleep(delay)`; bez eventu użyć wstrzykniętego `sleep`;
- nigdy nie łapać `BaseException`;
- testy wstrzykują fake `sleep`, więc są natychmiastowe.

`LlmService` przyjmuje opcjonalny observer przez constructor DI, a
`complete(request, cancel=...)` przekazuje observer i event do helpera.
`PipelineLlmCompleter` trzyma event jednego uruchomienia pipeline i podaje go
przy każdym completion, więc obecny `LlmCompleter` nie musi przyjmować parametru
anulowania. Cancel przed próbą albo podczas backoffu kończy się
`LlmCancelledError` z `ErrorCode.CANCELLED`; nie jest `TransientError`, nie jest mapowany
na fallback ani ponawiany. Trwającego blokującego requestu SDK nie da się
przerwać tym eventem — kończy go odpowiedź albo timeout.

### 7.7. `service.py`

Odpowiedzialności fasady:

- lazy `create_engine`;
- retry transient;
- idempotentne `close`;
- context manager;
- delegacja completion;
- brak promptów i logiki translation.

Nie duplikować retry w providerach.

## 8. Providerzy

### 8.1. Wspólne zasady

Każdy provider:

- ma stabilne `engine_id`;
- importuje SDK wewnątrz konstruktora klienta/metody lazy;
- przekazuje jawny model z `LlmConfig`;
- nie ma default model;
- nie waliduje modelu przez allowlist;
- mapuje role i ordered content parts;
- odrzuca nieobsługiwany content part, zamiast go pomijać;
- przekazuje `temperature`, `top_p` i limit outputu tylko gdy są jawnie
  ustawione; wyjątkiem jest wymagany przez Anthropic `max_tokens`, dla którego
  używa udokumentowanej domenowej stałej, gdy caller poda `None`;
- mierzy latency przez `time.perf_counter`;
- wyłącza SDK retry;
- zamyka klienta;
- mapuje finish reason i usage;
- normalizuje enum/string finish reason do stabilnego lowercase i nie zwraca
  pustego tekstu jako sukcesu (`LlmRequestError` z bezpiecznym reason);
- nie loguje treści requestu.

Każdy moduł ma jedną prywatną granicę tworzenia klienta (`_create_client` albo
injected private `client_factory`) używaną przez testy z fake SDK clientem.
Registry zawsze wywołuje publiczny konstruktor tylko z `LlmConfig`; test hook
nie przecieka do publicznego API. Provider łapie wyłącznie udokumentowane
wyjątki swojego SDK oraz `httpx` na granicy Gemini. Brak SDK jest mapowany
z `ImportError` na `LlmProviderUnavailableError`; inne błędy importu nie są
maskowane.

### 8.2. Shared OpenAI-compatible transport

`_openai_compatible.py` obsługuje:

- OpenAI;
- DeepSeek;
- OpenRouter;
- własny OpenAI-compatible endpoint.

Konfiguracja klienta:

```python
OpenAI(
    api_key=resolved_key,
    base_url=resolved_base_url,
    timeout=config.timeout_s,
    max_retries=0,
)
```

Endpoint na etap 5: Chat Completions. Powód:

- wspólny mianownik czterech providerów;
- text-only completion;
- brak agent tools i multi-turn state;
- OpenAI nadal wspiera ten endpoint;
- Responses API nie jest równym kontraktem dla wszystkich custom serwerów.

Wspólny transport dostaje jawny wariant parametru limitu:

- OpenAI direct: `max_completion_tokens`;
- DeepSeek, OpenRouter i generic OpenAI-compatible: `max_tokens`;
- gdy `max_output_tokens is None`, nie wysyłać żadnego;
- nigdy nie wysyłać obu i nie wykonywać automatycznej drugiej próby z inną
  nazwą po 400 — mogłoby to ukryć realny błąd endpointu.

Oba kwargs istnieją w zablokowanym `openai==2.45.0`; zgodność konkretnego proxy
potwierdza jego własna dokumentacja lub live smoke.

### 8.3. OpenAI

- default base URL SDK;
- API key wymagany;
- sugerowane modele w constants;
- `system` mapować na rolę akceptowaną przez Chat Completions;
- nie wprowadzać OpenAI-only reasoning options do ogólnego kontraktu etapu 5.

### 8.4. DeepSeek

- default base URL `https://api.deepseek.com`;
- API key wymagany;
- tylko aktualnie zweryfikowane IDs/aliasy trafiają do sugestii; nadal nie są
  whitelistą;
- obsłużyć `finish_reason="insufficient_system_resource"` jako unavailable;
- nie wymyślać nazw wersji na podstawie marketingowej nazwy modelu.

### 8.5. OpenRouter

- default base URL `https://openrouter.ai/api/v1`;
- API key wymagany;
- opcjonalne `HTTP-Referer` i `X-OpenRouter-Title` pozostają poza etapem 5,
  bo terminalowy AniShift nie potrzebuje rankingu aplikacji;
- 402 to fatal quota/payment;
- 502/503 to transient unavailable;
- `Retry-After` przekazać do wyjątku domenowego;
- dowolny slug jest dozwolony, nawet bez `/`, bo OpenRouter ma aliasy/routing.

### 8.6. OpenAI-compatible

- `base_url` wymagany;
- `provider_model_id` wymagany;
- pusty klucz dozwolony dla lokalnego serwera;
- do SDK przekazać bezpieczny placeholder wyłącznie dlatego, że klient OpenAI
  wymaga stringa; nie zapisywać go w settings;
- nie zgadywać Ollama/LM Studio/vLLM;
- nie doklejać `/v1` po cichu;
- błędny endpoint ma czytelny komunikat z sugestią sprawdzenia base URL.

### 8.7. Anthropic

- użyć `Anthropic`, nie `AsyncAnthropic`;
- system content przekazać top-level `system`;
- user/assistant content jako ordered content blocks;
- `max_tokens` jest wymagane — użyć jawnej wartości z config albo domenowego
  defaultu;
- klient `max_retries=0`;
- zmapować typed exceptions w kolejności od najbardziej szczegółowych;
- zamknąć klienta;
- nie wysyłać `temperature`/`top_p`, gdy `None`;
- test pokrywa model, który odrzuca niestandardowe sampling params.

### 8.8. Gemini

- użyć `genai.Client`;
- użyć `types.GenerateContentConfig(system_instruction=...)`;
- nie mapować system promptu na zwykłą wiadomość user;
- ordered text parts mapować do `types.Content`/`types.Part`;
- przekazać do klienta
  `HttpOptions(timeout=int(config.timeout_s * 1000), retry_options=HttpRetryOptions(attempts=1))`;
  w `google-genai==2.11.0` timeout jest w milisekundach, a `attempts=1`
  oznacza jedną próbę bez retry SDK;
- wywołać `client.close()`;
- mapować `usage_metadata`;
- puste `response.text` przy braku tekstowego candidate jest błędem requestu;
- deprecated sampling parameters wysyłać tylko, gdy user jawnie je ustawił.

### 8.9. Mapa wyjątków SDK

| Provider | SDK/HTTP | LLM error |
|---|---|---|
| OpenAI-compatible | `AuthenticationError`/401 | `LlmAuthError` |
| OpenAI-compatible | `PermissionDeniedError`/403 | `LlmAuthError` |
| OpenAI-compatible | 402 lub structured billing/payment | `LlmPaymentError` |
| OpenAI-compatible | 429 + structured `insufficient_quota` | `LlmQuotaError` |
| OpenAI-compatible | pozostałe `RateLimitError`/429 | `LlmRateLimitError` |
| OpenAI-compatible | `APITimeoutError`/408 | `LlmTimeoutError` |
| OpenAI-compatible | `APIConnectionError` | `LlmProviderUnavailableError` |
| OpenAI-compatible | 404 + structured model code | `LlmModelError` |
| OpenAI-compatible | pozostałe 404 | `LlmRequestError` z sugestią sprawdzenia endpointu |
| OpenAI-compatible | 400 context marker | `LlmContextLengthError` |
| OpenAI-compatible | >=500 | `LlmProviderUnavailableError` |
| Anthropic | `AuthenticationError` | `LlmAuthError` |
| Anthropic | `PermissionDeniedError` | `LlmAuthError` |
| Anthropic | structured billing/payment marker | `LlmPaymentError` |
| Anthropic | `RateLimitError` | `LlmRateLimitError` |
| Anthropic | `APITimeoutError` | `LlmTimeoutError` |
| Anthropic | `APIConnectionError` | `LlmProviderUnavailableError` |
| Anthropic | `NotFoundError` | `LlmModelError` |
| Anthropic | `InternalServerError` | `LlmProviderUnavailableError` |
| Anthropic | `OverloadedError`/529 | `LlmProviderUnavailableError` |
| Anthropic | `RequestTooLargeError`/413 | `LlmContextLengthError` |
| Gemini | 401/403 | `LlmAuthError` |
| Gemini | structured billing/payment marker | `LlmPaymentError` |
| Gemini | 404 | `LlmModelError` |
| Gemini | 429 + structured quota/daily-limit marker | `LlmQuotaError` |
| Gemini | pozostałe 429 | `LlmRateLimitError` |
| Gemini | deadline/timeout | `LlmTimeoutError` |
| Gemini | 500/503/504 | `LlmProviderUnavailableError` |
| Gemini | `httpx.TimeoutException` | `LlmTimeoutError` |
| Gemini | `httpx.NetworkError` | `LlmProviderUnavailableError` |
| OpenRouter | 402 | `LlmPaymentError` |
| dowolny | unsupported content part | `LlmRequestError` |

Kolejność obsługi musi iść od przypadków szczegółowych do bazowych:
structured quota/daily-limit przed ogólnym 429, OpenRouter 402 przed
nieznanym 4xx,
`APITimeoutError` przed `APIConnectionError`, typed status errors przed
`APIStatusError`, a w Gemini `ClientError`/`ServerError` przed bazowym
`APIError`. Nie rozpoznawać context-length ani model-not-found wyłącznie po
jednym angielskim zdaniu. Najpierw status/type/structured `code`/`status`,
dopiero potem ograniczony provider-specific fallback po znanym kodzie.
Nieznane 4xx są `LlmRequestError`; nieznane 5xx są transient unavailable.

## 9. System promptów

### 9.1. Własność

Ogólny LLM transportuje messages. Nie zna:

- anime;
- polskiego;
- `[N]`;
- glosariusza.

Cała ta semantyka należy do
`services/translation/engines/llm/prompts`.

### 9.2. Typy

```python
@dataclass(frozen=True, slots=True)
class PromptAsset:
    prompt_id: str
    version: int
    resource_path: str
    source: Literal["builtin", "user"]


@dataclass(frozen=True, slots=True)
class GlossaryEntry:
    source: str
    target: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class PromptContext:
    title: str = ""
    summary: str = ""
    glossary: tuple[GlossaryEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class ComposedPrompt:
    system: str
    user: str
    prompt_id: str
    prompt_version: int
    style_id: str
    fingerprint: str
    omitted_context_items: int = 0
```

### 9.3. Registry

Osobne registries:

- task prompts;
- styles;
- obowiązkowe contracts;
- opcjonalne modules.

Registry składa dwa kontrolowane źródła:

1. wbudowane assets z package resources;
2. własne `.txt` z `config/prompts/{tasks,styles,modules}/`.

Nazwa pliku bez rozszerzenia jest ID. Skanowanie:

- używa naturalnej, deterministycznej kolejności;
- ignoruje inne rozszerzenia;
- pusty plik, niepoprawne UTF-8 albo duplikat ID daje czytelny config error;
- nie podąża za ścieżkami wychodzącymi poza kontrolowane katalogi;
- ładuje ponownie registry przy otwarciu `/settings` i przed startem pipeline;
- stanowi SSOT dla pickerów promptu i stylu.

Custom `.txt` dostaje `version=1`; zmianę jego treści identyfikuje fingerprint,
więc user nie musi zmieniać nazwy pliku przy każdej edycji.

Wbudowane contracts nie są widoczne jako wymienny task/style i nie mogą zostać
wyłączone przez pliki usera.

### 9.4. Kolejność składania

System translation:

1. main task prompt zawierający stałe translation invariants;
2. selected style;
3. selected optional modules w naturalnej kolejności;
4. numbered output contract;
5. repair-format contract tylko w requestach repair.

User/dynamic data:

1. source and target language;
2. bounded title/summary;
3. bounded glossary serialized by code;
4. numbered input lines.

Każdy blok ma stabilne delimitery. Dynamiczne dane są oznaczone jako
untrusted:

```text
<untrusted_translation_data>
  <context>...</context>
  <glossary>...</glossary>
  <lines>
    [1] ...
  </lines>
</untrusted_translation_data>
```

Escape:

- dynamiczny tekst nie może zamknąć delimiterów;
- serializer zamienia `&`, `<`, `>`;
- model dostaje informację, że treść bloku nie jest instrukcją;
- nie składać promptu przez niekontrolowane `str.format(**raw_user_data)`.

### 9.5. Limity

Stałe startowe:

- maksymalnie 200 glossary entries;
- maksymalnie 100 znaków source term;
- maksymalnie 200 znaków target term;
- maksymalnie 300 znaków note;
- maksymalnie 8 000 znaków summary;
- maksymalnie 2 000 znaków title/metadata łącznie;
- nie obcinać pojedynczej wartości po cichu;
- pomijać nadmiar deterministycznie i raportować licznik.

### 9.6. Wersja i fingerprint

Fingerprint:

```text
sha256(
  canonical_utf8_lf_asset_1_bytes
  + NUL
  + canonical_utf8_lf_asset_2_bytes
  + NUL
  + ...
)
```

Loader dekoduje UTF-8 i normalizuje `CRLF`/`CR` do `LF` przed kompozycją oraz
fingerprintem. Fingerprint obejmuje wszystkie i tylko statyczne assety faktycznie użyte w
danym requestcie. Request repair ma więc inny fingerprint niż fast path.
Fingerprint nie obejmuje napisów, glosariusza ani kontekstu dynamicznego.
Dzięki temu:

- identyfikuje stabilny prefix;
- nie wycieka treść usera;
- nadaje się do raportu;
- zmiana treści lub whitespace innego niż końce linii jest świadomą zmianą
  fingerprintu.

### 9.7. Cache-friendly, nie cache-dependent

Etap 5:

- układa stabilny prefix zawsze identycznie;
- nie implementuje własnego prompt cache;
- nie wysyła provider-specific cache directives;
- nie uzależnia poprawności od cache hit;
- późniejszy explicit cache może korzystać z istniejącej granicy prefix/dynamic.

### 9.8. Test assetów w wheel

Test integracyjny:

1. `uv build`;
2. otworzyć wheel jako ZIP;
3. potwierdzić obecność wszystkich zadeklarowanych wbudowanych `.txt`;
4. zainstalować wheel do tymczasowego venv albo załadować resource;
5. potwierdzić UTF-8 i fingerprint.

Ten test może być osobnym ręcznym krokiem release, jeśli budowanie wheel w każdym
pytest jest za wolne.

Osobne testy registry tworzą `config/prompts/` w `tmp_path` i dowodzą wykrywania
task/style/module, ignorowania innych rozszerzeń oraz błędów duplicate/empty/UTF-8.

## 10. Adapter translation LLM

### 10.1. Kontrakt `LlmCompleter`

Pozostaje translation-owned i nie importuje `services.llm`, ale nie może zostać
przy dwóch stringach: taki kontrakt gubi finish reason oraz tożsamość promptu,
czyli łamie S29 i uniemożliwia odróżnienie uciętej odpowiedzi od zwykłego błędu
formatu.

```python
@dataclass(frozen=True, slots=True)
class PromptIdentity:
    prompt_id: str
    prompt_version: int
    style_id: str
    fingerprint: str
    purpose: Literal["translation", "translation_repair"]


@dataclass(frozen=True, slots=True)
class LlmCompletionRequest:
    system: str
    user: str
    identity: PromptIdentity


@dataclass(frozen=True, slots=True)
class LlmCompletionResult:
    text: str
    finish_reason: str


class LlmCompleter(Protocol):
    def complete(self, request: LlmCompletionRequest) -> LlmCompletionResult: ...
```

Composition adapter mapuje request na dwa typed `LlmMessage`, zwraca tylko
translation-owned wynik, a pełne metadata/usage zapisuje w swoich
`LlmCallRecord`. Translation nadal nie zna `LlmResponse` ani providerowych
typów. `finish_reason` jest normalizowany do małego, stabilnego stringa; limit
outputu omija bezcelowy repair tej samej wielkości i przechodzi od razu do
shrink, natomiast content filter/safety kończy engine błędem.

### 10.2. `LlmTranslateConfig`

Dodać pola:

- `max_batch_lines=1000`;
- `prompt_id`;
- `style_id`;
- `module_ids`;
- `prompt_context`;
- limity pozostają stałymi prompt domain.

Nie przyjmować ogólnego `TranslationConfig` i nie wyrzucać go po cichu. Fabryka
composition buduje jawny `LlmTranslateConfig`. Zwykły strumień do 1000
niepustych linii jest jednym completion. Większy strumień jest dzielony
deterministycznie tylko na granicy 1000 linii.

### 10.3. Fast path

1. Przygotuj wejście zgodnie z polityką bieżącego strumienia, ale pomiń
   whitespace-only pozycje z jawną mapą redystrybucji.
2. Jeżeli jest najwyżej 1000 niepustych linii, zbuduj jeden composed prompt.
3. Wywołaj jedno completion.
4. Większe wejście podziel na kolejne stabilne części po 1000 linii.
5. Sparsuj `[N]`.
6. Sprawdź dokładny zbiór indeksów.
7. Zwróć dokładnie tyle wyników, ile wejść.

### 10.4. Parser

Parser akceptuje:

- whitespace przed `[N]`;
- linie noise poza protokołem ignoruje tylko do momentu, gdy nie tworzą
  dodatkowego indeksu.

Parser odrzuca:

- brak indeksu;
- duplikat;
- indeks poza zakresem;
- dodatkowy indeks;
- nieciągły zbiór;
- scalone linie;
- puste tłumaczenie; whitespace-only source nie trafia do LLM i jest
  redystrybuowane osobno.

### 10.5. Repair

Repair:

- używa tego samego modelu;
- podaje ponownie oryginalny batch;
- dodaje krótki, stały moduł naprawy formatu;
- nie dołącza całej błędnej odpowiedzi, jeśli mogłaby zawierać nieograniczoną
  treść;
- wykonuje dokładnie jedną próbę;
- dostaje własny `PromptIdentity` i fingerprint obejmujący moduł repair.

### 10.6. Shrink

Po nieskutecznym repair, `LlmContextLengthError` albo `finish_reason`
oznaczającym limit outputu:

1. podziel batch na dwie stabilne połowy;
2. każdą połowę tłumacz tym samym algorytmem;
3. zatrzymaj dzielenie na pojedynczej linii;
4. jeśli pojedyncza linia nadal łamie kontrakt, rzuć
   `TranslationEngineError`;
5. nie zwracaj source jako sukcesu;
6. błąd całego pliku przekaż do orkiestratora kolejki.

### 10.7. Polityka input

Rozszerzyć `TranslationEngine` o:

```python
def input_policy(self, stream: TranslationStream) -> TranslationInputPolicy: ...
```

`TranslationInputPolicy = Literal["deduplicate", "preserve"]`.

- istniejąca klasyfikacja `DIALOG`/`SIGN`/`UNCERTAIN` pozostaje źródłem
  rozdziału `spoken`/`displayed`;
- wcześniejsze zwijanie animacji FBF pozostaje bez zmian;
- Google i DeepL: `deduplicate` dla `spoken` i `displayed`;
- LLM: `preserve` dla `spoken`, `deduplicate` dla `displayed`.

`TranslationService` wybiera ścieżkę bez `engine_id == "llm"` hardcode.

`MOD dedup.py` zastępuje nazwę zakładającą zawsze unikalny input neutralnym
`PreparedLines(texts, index_map)` oraz dodaje
`prepare_lines(lines, policy)`. Dla `deduplicate` zachowuje dokładnie obecne
zachowanie. Dla `preserve` zachowuje każde niepuste wystąpienie, a whitespace
mapuje na `-1`, dzięki czemu LLM nie dostaje pustych pozycji, ale wynik nadal ma
dokładną długość wejścia. `TranslationService` pyta o politykę osobno dla
`spoken` i `displayed`, układa obie grupy w jeden strumień według kolejności
eventów, a następnie rozprowadza odpowiedzi z powrotem do właściwych struktur.
Deduplikowany `displayed` trafia do providera tylko przy pierwszym wystąpieniu;
jedna odpowiedź zasila wszystkie powtórzenia animacji. Zmiana obejmuje
istniejące testy dedup oraz przypadek co najmniej 100 identycznych eventów.

### 10.8. Liczenie requestów

`FileTranslation.api_calls` liczy logiczne wywołania
`TranslationEngine.translate_batch`. Zwykły plik wykonuje jedno takie
wywołanie dla wspólnego chronologicznego strumienia `spoken` + `displayed`;
wewnętrzne chunki, fallbacki i requesty transportowe nadal nie zmieniają
semantyki tego pola. Zastępowanie go licznikiem HTTP wymagałoby rozszerzenia
kontraktu wszystkich engine'ów i nie jest potrzebne.

Surową liczbę wywołań fake engine sprawdzają testy `LlmService` i adaptera.
Raport produktu dostaje `LlmCallRecord` per wywołanie completera: purpose,
provider, model, finish reason, latency, usage, prompt identity oraz opcjonalny
kod błędu. Rekord nie zawiera promptu ani odpowiedzi. Retry wewnątrz
`LlmService` ma osobny licznik prób, aby podsumowanie rozróżniało completion,
repair i retry. Nie udawać dokładnego billingu nieudanych prób, jeśli
SDK/provider nie zwrócił usage.

### 10.9. Integralność layoutu ASS

- jeden event ASS jest jednym logicznym elementem tłumaczenia; wizualne wersy
  rozdzielone `\N` albo `\n` nie stają się osobnymi request items;
- provider dostaje czysty jednoliniowy tekst, natomiast surowy event zachowuje
  poza API authored breaki, `\h` i kotwice tagów inline;
- `spoken` po tłumaczeniu korzysta z polskiej heurystyki czytelnego reflow;
- `displayed` bez authored breaków korzysta z tej samej heurystyki, a
  `displayed` z authored layoutem zachowuje liczbę wersów, jeśli target ma
  dość granic słów, i wybiera naturalne polskie granice przybliżone proporcjami
  źródła; pojedyncze słowo nie jest sztucznie rozcinane ani uzupełniane pustą
  linią;
- niezmieniony tekst widoczny zwraca oryginalny raw event 1:1;
- tagi inline pozostają heurystycznie zakotwiczone względem tekstu, a tagi
  akcentujące są dosuwane do granic słów i nigdy nie rozcinają grafemu;
- `\h` zastępuje najbliższą spację targetu twardą spacją, ale nie jest
  sztucznie wstawiane wewnątrz pojedynczego słowa;
- eventy wektorowe `\pN` nie trafiają do translatora i są kopiowane bez zmian;
- pipeline zapisuje pełny `{stem}.pl.ass` oraz przetłumaczony displayed-only
  `{stem}.lektor.pl.ass` bez dodatkowego requestu.

## 11. Fabryka silników i granica błędu

### 11.1. Fabryka jako callable

```python
type TranslationEngineFactory = Callable[
    [str, TranslationConfig],
    TranslationEngine,
]
```

Jednometodowy `Protocol` nie daje tu wartości. Callable wystarcza produkcji,
closure pipeline i fake'om testowym.

### 11.2. Domyślna fabryka

Gdy factory nie jest wstrzyknięta:

- `TranslationService` używa małej funkcji, która kopiuje bazowy
  `TranslationConfig` z podmienionym `engine` i deleguje do obecnego
  `create_engine`;
- zachowanie Google/DeepL nie zmienia się;
- `llm` bez composition factory nadal daje czytelny config error.

### 11.3. Fabryka pipeline

Prywatna closure w `pipeline/llm_runtime.py`:

- tworzy osobny `PipelineLlmCompleter` dla aktywnego workera;
- Google/DeepL deleguje do registry;
- dla `llm` wymaga completera;
- buduje `LlmTranslateConfig` z settings oraz `PromptContext` bieżącego pliku;
- nie współdzieli klienta SDK między workerami;
- przyjmuje współdzielony limiter/circuit breaker jako jawną zależność.

### 11.4. TranslationService

Zmiany:

- usunąć parametr `engine=`;
- dodać `engine_factory=`;
- `_build_engine()` deleguje do factory;
- lokalne `engine: TranslationEngine | None = None`; budowa engine,
  `is_available` i `_run` są wewnątrz `try`, a `finally` wywołuje `close()`
  tylko gdy konstrukcja zwróciła obiekt — także dla `is_available=False`;
- wynik zwracamy dopiero po pełnym sukcesie;
- łapiemy precyzyjnie bazowy `TranslationError` i zwracamy bezpieczny
  `FileTranslation.error` oraz strukturalny `FileTranslation.error_context`;
- nie łapiemy `Exception`; błąd programistyczny nie może zostać ukryty jako
  błąd providera;
- `CANCELLED` zawsze przebija natychmiast;
- błąd LLM wraca do orkiestratora kolejki, który klasyfikuje go jako
  retry/pause/failure;
- automatyczny fallback do płatnego providera nie powstaje.

Istniejąca konfiguracja fallback Google/DeepL pozostaje kompatybilna dla tych
engine'ów, ale LLM nie przełącza providera ani modelu automatycznie. OpenRouter
jest używany wyłącznie po jawnym wyborze usera.

Testy fake engine przechodzą na fake factory. Nie dziedziczyć testowej klasy po
`TranslationService` tylko po to, aby nadpisać `_build_engine`.

`FileTranslation.error_context: ErrorContext | None` zachowuje typed `code`,
bezpieczny message i suggestion. Legacy `error: str | None` pozostaje dla
kompatybilności raportu, ale scheduler klasyfikuje wyłącznie po `error_context`,
nigdy przez parsowanie stringa.

## 12. Composition adapter

### 12.1. `pipeline/llm_runtime.py`

Odpowiedzialności:

- przechować lekkie `LlmSettings` i zbudować `LlmConfig` dopiero przy pierwszym
  rzeczywistym completion;
- stworzyć osobny `LlmService` dla workera;
- zamienić `LlmCompletionRequest` na ordered typed messages;
- wywołać sync completion;
- zwrócić `LlmCompletionResult`;
- zebrać metadata do beztreściowego `LlmCallRecord`;
- mapować LLM errors na translation errors;
- zamknąć service w `finally`, jeżeli został utworzony;
- przechowywać call records lokalnie dla jednego pliku, bez globalnego
  `current_file`.

Mapowanie:

| LLM | Translation |
|---|---|
| `LlmAuthError` | `TranslationAuthError` |
| `LlmRateLimitError` | `TranslationRateLimitError` |
| `LlmQuotaError` | `TranslationQuotaError` |
| `LlmPaymentError` | `TranslationQuotaError` z kodem payment |
| `LlmTimeoutError` | `TranslationEngineError` z kodem timeout |
| `LlmContextLengthError` | `TranslationContextLengthError` |
| config/model/request | `TranslationEngineError` |
| unavailable | `TranslationEngineError` |

Composition layer może importować obie domeny. Dzięki temu translation pozostaje
niezależne od LLM, a transportowe błędy nie są łapane jako anonimowy
`Exception`.

Każde mapowanie używa `raise ... from exc` i zachowuje bezpieczny
`ErrorContext`; nie kopiuje surowego response body. `LlmError` z kodem
`CANCELLED` przebija jako `TranslationError` o tym samym kodzie. Adapter łapie
wyłącznie `LlmError`, nie szerokie `Exception`.

`LlmCancelledError` jest mapowany na jawny translation-owned cancellation error
albo `TranslationError` z zachowanym `ErrorCode.CANCELLED`; nigdy na ogólny
engine failure.

`TranslationContextLengthError` należy do domeny translation i nie importuje
`services.llm`. `LlmTranslateService` łapie wyłącznie ten subtype, dzieli batch
na dwie stabilne połowy i ponawia mniejsze części. Pozostałe
`TranslationEngineError` propagują do schedulera bez adaptacyjnego splitu.

### 12.2. Lifecycle w pipeline

Dla jednego zadania pliku:

```python
with build_llm_runtime(settings, shared_provider_state, cancel) as runtime:
    translate_one_file(runtime)
```

Każdy worker ma własny `PipelineLlmCompleter`, `LlmService` i klient SDK.
Config/service/client powstają lazy przy pierwszym completion i są zamykane po
pliku. Pomiędzy workerami współdzielone są wyłącznie thread-safe:

- limiter providera;
- circuit breaker;
- stan ramp-up współbieżności;
- sygnał pauzy;
- cancellation event.

Żaden mutable klient SDK ani call-record buffer nie jest współdzielony. Runtime
zamyka service w `finally` także przy `KeyboardInterrupt` i cancellation.
`LlmTranslateService.close()` pozostaje no-op, bo nie jest właścicielem
completera.

Dla każdego pliku pipeline buduje osobną closure engine factory, aby przekazać
`PromptContext(title=source.stem)` bez globalnego mutable context. Summary
i glossary są w etapie 5 puste, chyba że jawny caller API poda je
programatycznie; panel nie udaje źródła danych, którego repo nie ma.

### 12.3. Status wyniku pliku

Aktualny runner może zapisać `FileTranslation.error`, ale pozostawić
`FileOutcome.status="done"`. Etap 5 musi to naprawić.

- `_translate_one`: gdy `result.is_success` jest `False`, ustawić status
  `failed`, zbudować `FileFailure(step="translate", code=TRANSLATION_FAILED, ...)`
  z bezpiecznego błędu wyniku, zachować wcześniejsze artefakty extraction
  i nie uruchamiać write;
- `_process_txt`: analogicznie zwrócić failed outcome ze step `txt` i przekazać
  ten sam pipeline cancel event do translation;
- `TranslationError` z `CANCELLED` mapować na `FileOutcome.status="cancelled"`,
  bez write;
- ukończony plik zachowuje `done` i nie jest wykonywany ponownie po wznowieniu;
- plik zatrzymany przez trwałą awarię wraca na początek pending queue;
- po każdym pliku, także failed/cancelled, lokalne call records trafiają do
  `FileOutcome.llm_calls`;
- osobny wynik przebiegu rozróżnia `done`, `failed`, `cancelled` i
  `not_processed`;
- częściowego przebiegu nie przedstawiać jako pełnego sukcesu.

## 13. Ustawienia

### 13.1. `UserSettings`

Zmienić/dodać:

```python
llm_provider: str = "gemini"
llm_provider_model_id: str = "gemini-3.5-flash-lite"
llm_temperature: float | None = None
llm_top_p: float | None = None
llm_max_output_tokens: int | None = None
llm_prompt_id: str = "anime_translation_v1"
llm_style_id: str = "natural_polish_v1"
llm_module_ids: tuple[str, ...] = ()
llm_max_concurrency: int = 4
```

Usunąć stare `llm_model`; repo nie ma jeszcze persisted runtime migration, ale
loader powinien jednorazowo przyjąć legacy key:

- migrację wykonać na surowym dict **przed** filtrowaniem przez
  `UserSettings.__dataclass_fields__`;
- jeśli `llm_provider_model_id` brak, a `llm_model` jest stringiem, przepisać
  jego `.strip()`;
- zapis zawsze używa nowej nazwy;
- unknown keys nadal są ignorowane.

`None` oznacza provider default. Nie zapisywać sztucznych `0` dla tokenów.
Loader potrzebuje osobnego cleanera akceptującego `None`; obecna
`_clean_number` odrzuca `None`, więc bez tej zmiany roundtrip nowych pól byłby
pozornie zielony tylko dla wartości liczbowych.

### 13.2. Walidacja user settings

- `llm_provider` z `available_engine_ids()`;
- model: dowolny `.strip()`-owany string, bez allowlist;
- model pusty jest dozwolony tylko dopóki translation engine nie jest `llm`;
- przy dowolnym uruchomieniu LLM pusty model daje config error;
- prompt/style/modules muszą istnieć w połączonym registry;
- sampling values mogą być `None`;
- `llm_max_concurrency` mieści się w `1..4`;
- sekrety nigdy nie trafiają do JSON.

### 13.3. `LlmSettings` w pipeline

Nowy frozen dataclass:

- provider;
- model;
- generation params;
- prompt/style/modules;
- max concurrency;
- timeout jako domenowa stała i retry z istniejącego
  `translation_max_retries` (nie dodawać drugiej gałki o tej samej semantyce);
- sześć kluczy;
- compatible base URL.

`_translation_settings(context)` rozwiązuje go raz. Provider-specific key jest
wybierany dopiero przy budowie LLM config.

Routing sekretów jest jawny:

- Gemini: `ANISHIFT_GEMINI_API_KEY`;
- OpenRouter: `ANISHIFT_OPENROUTER_API_KEY`;
- Anthropic: `ANISHIFT_ANTHROPIC_API_KEY`;
- DeepSeek: `ANISHIFT_DEEPSEEK_API_KEY`;
- OpenAI: `ANISHIFT_OPENAI_API_KEY`;
- compatible: `ANISHIFT_OPENAI_COMPATIBLE_API_KEY` i
  `ANISHIFT_OPENAI_COMPATIBLE_BASE_URL`.

Wszystkie sekrety pochodzą wyłącznie z env/`.env`; nie wolno ich kopiować do
`settings.json`, logów, wyjątków ani call records.

### 13.4. `/settings`

`_FIELDS` nie może pozostać statycznym tuple. Dodać czystą funkcję
`_visible_fields(settings)`, a po każdej zmianie clampować indeks aktywnego
wiersza. Provider/model/prompt/style/modules/concurrency są widoczne niezależnie od
aktualnego translation engine — inaczej user nie mógłby spełnić S7 ani
skonfigurować LLM przed jego wyborem. Tylko advanced generation rows mogą być
zwijane warunkowo:

1. LLM provider;
2. LLM model;
3. prompt;
4. style;
5. modules;
6. max concurrency;
7. opcjonalne advanced generation values.

Provider:

- cykl po sześciu registry IDs;
- provider bez klucza zawsze pozostaje widoczny i jest oznaczony `missing key`;
- `openai_compatible` wymaga base URL, ale może nie mieć key.

Model:

- lewo/prawo cykluje sugestie;
- gdy lista sugestii jest pusta, lewo/prawo jest no-op i hint prowadzi do `e`;
- klawisz `e` włącza inline edit przez stan `_PanelState`, bez uruchamiania
  drugiej `Application`;
- w edit mode user wpisuje dowolny ID;
- Enter zatwierdza i zapisuje;
- Escape odrzuca edycję;
- Backspace usuwa znak, zwykłe printable keys dopisują do bufora, a `q` w edit
  mode jest znakiem, nie wyjściem;
- custom model pozostaje custom i nie jest nadpisywany przy renderze;
- zmiana providera ustawia pierwszą sugestię, gdy model był pusty albo należał
  do sugestii poprzedniego providera; własny custom ID zachowuje i oznacza
  `custom — verify for provider`, zamiast niszczyć go automatycznie.

Panel wymaga małego, typowanego stanu edycji
`_PanelState(row, editing, buffer)`, nie słownika `dict[str, object]` ani
osobnego drugiego prompt-toolkit `Application`. Testować czyste funkcje listy
wierszy, zmian providera/modelu i obsługi bufora; nie symulować pełnego terminala
tam, gdzie nie trzeba.

### 13.5. Dostępność translation `llm`

`llm` zawsze pozostaje widoczne w pickerze. Dostępność jest osobnym markerem:

- `ready`, gdy wybrany provider ma wymagany key albo compatible base URL;
- `missing key`, gdy klucza brakuje;
- `missing base URL`, gdy compatible nie ma URL.

Jeżeli user ma zapisane `llm`, a klucz zniknął:

- panel nadal pokazuje bieżący wybór z markerem unavailable;
- pipeline zwraca czytelny błąd i przechodzi do interakcji `settings`/`finish`;
- loader nie resetuje cicho engine do Google.

## 14. Kolejka, circuit breaker i interakcja

### 14.1. Własność

`pipeline/llm_queue.py` jest centralnym schedulerem jednego `run_pipeline`.
Nie jest częścią domeny LLM ani translation. Odpowiada za:

- natural-order pending queue;
- maksymalnie cztery aktywne zadania;
- priorytet zadania naprawianego/ponawianego;
- pauzę po otwarciu circuit breakera;
- ramp-up `1 → 2 → 4`;
- interakcję `settings`/`finish`;
- końcowe rozróżnienie done/failed/not processed.

Stan schedulera jest per run, nigdy globalny. Testy uruchamiane równolegle przez
xdist nie mogą dzielić limitera ani circuit breakera.

### 14.2. Enqueue i naturalna kolejność

1. `discover_inputs()` zachowuje istniejący natural sort.
2. Po zakończeniu ekstrakcji plik natychmiast trafia do pending queue.
3. Scheduler wypełnia wolne sloty do aktualnego limitu.
4. Gotowy plik przechodzi do write/TTS bez czekania na pozostałe.
5. Rozpoczęte requesty nie są anulowane przez błąd innego requestu.
6. Niewysłane zadania pozostają w kolejce.
7. Repair i split odbywają się wewnątrz aktywnego zadania, więc zachowują jego
   slot i mają pierwszeństwo przed nowymi plikami.

### 14.3. Transient failure

Po 429, timeout, network error albo przejściowym 5xx:

1. facade wykonuje dozwolone retry i respektuje `Retry-After`/backoff;
2. circuit breaker blokuje start nowych zadań dla providera;
3. rozpoczęte zadania mogą się zakończyć;
4. najstarszy uszkodzony plik trafia na początek kolejki;
5. retry probe działa jako jedyne nowe zadanie;
6. po sukcesie limit rośnie `1 → 2 → llm_max_concurrency`;
7. po wyczerpaniu prób provider zostaje disabled do końca runu i przechodzi do
   trwałej interakcji.

Nie używać `sleep` w testach. Scheduler przyjmuje clock/backoff waiter albo
sterowalne `Event`/`Barrier`.

### 14.4. Trwała awaria

Auth, permission, payment, quota/daily limit, zły model, zły endpoint albo
wyczerpana trwała niedostępność:

- nie uruchamia nowych requestów;
- pozwala zakończyć aktywne;
- zachowuje gotowe pliki;
- zamyka klienty providera;
- pokazuje liczbę gotowych i oczekujących plików;
- kończy aktywny Rich Live przed wejściem w prompt interaktywny.

Terminal pokazuje:

```text
> settings
> finish
```

`settings` otwiera istniejący panel, waliduje nową konfigurację i wznawia tylko
niewykonane pliki. Plik, który ujawnił awarię, ma pierwszeństwo, potem wraca
naturalna kolejność. Nowy provider/model dostaje nowy per-run resilience state.

`finish` zachowuje gotowe wyniki, oznacza oczekujące jako `not_processed` z
bezpieczną przyczyną i nie raportuje przebiegu jako pełnego sukcesu. To jedyny
przypadek, gdy tryb auto wymaga decyzji usera.

### 14.5. File-local output failure

Wyczerpanie repair/split dla pojedynczej linii:

- oznacza wyłącznie ten plik jako `failed`;
- nie otwiera circuit breakera, bo transport i provider działają;
- nie pauzuje kolejki;
- nie anuluje aktywnych requestów;
- zwalnia slot dla następnego pliku w naturalnej kolejności.

### 14.6. Raport końcowy

Podsumowanie terminalowe pokazuje:

- done, failed i not processed;
- logical completions;
- repairs;
- transport retries;
- input/output/total tokens, jeśli dostępne;
- koszt tylko wtedy, gdy provider zwrócił go bezpośrednio.

Etap nie utrzymuje tabeli cen i domyślnie nie zapisuje JSON. Typowany wynik
pipeline zachowuje beztreściowe rekordy dla późniejszego jawnego eksportu.

## 15. Fale implementacji

Każda fala kończy się zielonymi testami swojego zakresu. Nie tworzyć wszystkich
providerów przed ustabilizowaniem kontraktu na jednym fake.

### Fala 0 — baseline i decyzje

1. Potwierdzić status `APPROVED` w `etap-5-wymagania.md`.
2. Potwierdzić zgodność tego planu z zaakceptowanymi wymaganiami.
3. Zweryfikować aktualne IDs sugestii i dokładne kontrakty SDK dla wersji
   z `uv.lock`.
4. Zanotować baseline:
   - pełne bramki;
   - import time;
   - istniejący pipeline Google;
   - jeden prawdziwy fixture ASS.
5. Potwierdzić feature branch, nie pracować na `main`.

**Bramka:** wymagania zatwierdzone, plan zsynchronizowany i baseline zielony.

### Fala 1 — typy, config, errors, registry

Pliki:

- `ADD services/llm/{__init__,config,errors,protocols,types}.py`;
- `ADD services/llm/engines/__init__.py`;
- `MOD errors.py`;
- testy registry/config/import-laziness.

**Bramka:**

```bash
uv run pytest tests/services/llm/test_llm_registry.py
uv run mypy anishift/ tests/
```

### Fala 2 — facade, retry i fake engine

Pliki:

- `ADD services/llm/service.py`;
- `ADD services/llm/_retry.py`;
- `ADD tests/services/llm/conftest.py`;
- test lifecycle/retry.

Scenariusze:

- constructor nic nie importuje;
- first call creates once;
- second call reuses;
- close once/idempotent;
- transient succeeds after retry;
- fatal exactly once;
- retry-after;
- exhausted transient;
- cancel during backoff.

### Fala 3 — OpenAI-compatible core + OpenAI-compatible provider

Najpierw generic compatible, bo daje bazę dla czterech providerów.

Pliki:

- `_openai_compatible.py`;
- `openai_compatible/*`;
- test mapping request/response/errors/close.

Testować fake SDK client przez injected client factory. Nie patchować sieci.

### Fala 4 — OpenAI, DeepSeek, OpenRouter

Każdy provider jako cienka konfiguracja wspólnego transportu.

Po każdym:

1. constants;
2. service;
3. registry entry;
4. test kontraktu;
5. test provider-specific status.

**Bramka:** import jednego nie ładuje pozostałych.

### Fala 5 — Anthropic i Gemini

Provider-specific mapping:

- system prompt;
- content parts;
- usage;
- finish reason;
- timeout/retry disable;
- close;
- typed errors.

**Bramka:** wszystkie sześć engine'ów spełnia runtime protocol.

### Fala 6 — prompt assets i composer

1. Dodać typy i registry.
2. Dodać `.txt`.
3. Dodać safe serializer.
4. Dodać limity.
5. Dodać fingerprint.
6. Dodać test resources.

**Bramka:** composer snapshot jest deterministyczny na Windows/Linux newline.
Loader normalizuje CRLF do `\n` przed fingerprintem.

### Fala 7 — naprawa adaptera translation LLM

1. Rozszerzyć config.
2. Wpiąć composer.
3. Zachować fast path `[N]`.
4. Oddzielić transport error od malformed output.
5. Zaimplementować repair.
6. Zaimplementować shrink.
7. Usunąć ciche source padding.
8. Udostępnić jeden czysty `parse_numbered()` dla fast path i repair.
9. Raportować completion call records.

### Fala 8 — input policy i fabryka

1. Dodać `TranslationInputPolicy` rozwiązywane osobno per strumień.
2. Uzupełnić trzy engine'i.
3. Dodać `PreparedLines`/`prepare_lines` i zmienić przygotowanie inputu
   w facade bez regresji whitespace.
4. Wprowadzić `TranslationEngineFactory`.
5. Przekazywać typed błąd LLM do schedulera zamiast automatycznego paid fallback.
6. Przepisać fake tests na factory.

**Bramka:** spoken preserve, displayed deduplicate, a awaria LLM nie uruchamia
niejawnego providera.

### Fala 9 — composition i pipeline

1. Dodać `LlmSettings`.
2. Zbudować config z env + user settings.
3. Dodać `PipelineLlmCompleter` i call records.
4. Dodać per-file closure engine factory.
5. Wpiąć MKV i TXT.
6. Zamknąć lifecycle osobno per worker/file.
7. Zebrać lokalne usage i prompt metadata per plik.
8. Przekazać cancel także do TXT.
9. Naprawić failed status dla MKV i TXT.

**Bramka:** fake provider przechodzi `/settings data -> runner -> translated file`.

### Fala 10 — `/settings`

1. Provider picker.
2. Suggestions.
3. Inline custom model editor.
4. Prompt/style/module picker z automatycznym wykrywaniem `config/prompts/`.
5. Max concurrency.
6. Availability markers, w tym zawsze widoczne `missing key`.
7. Migracja `llm_model`.
8. Modalny bufor custom ID i dynamiczne visible fields.

**Bramka:** custom ID roundtrip nie jest resetowany przez loader/panel.

### Fala 11 — scheduler, circuit breaker i interakcja

1. Dodać natural-order pending queue.
2. Połączyć extraction completion z natychmiastowym enqueue.
3. Dodać `ThreadPoolExecutor` z defaultem czterech workerów.
4. Dodać shared limiter i circuit breaker per run/provider.
5. Dodać retry priority oraz ramp-up `1 → 2 → 4`.
6. Dodać pauzę trwałej awarii.
7. Dodać komendy `settings` i `finish`.
8. Wznawiać tylko niewykonane pliki.
9. Dodać końcowe podsumowanie usage i stanu plików.

**Bramka:** testy na `Event`/`Barrier` dowodzą czterech równoległych requestów,
braku startu nowych zadań przy otwartym circuit i zachowania naturalnej kolejki.

### Fala 12 — dokumentacja i live smoke

1. Uaktualnić wskazane w drzewie pary `AGENTS.md`/`CLAUDE.md` przez skill
   `agents-md`, bez tworzenia nieproszonych tutoriali.
2. Uruchomić Gemini `gemini-3.5-flash-lite` z
   `ANISHIFT_GEMINI_API_KEY`.
3. Uruchomić OpenRouter z `ANISHIFT_OPENROUTER_API_KEY`.
4. Uruchomić custom compatible server, jeśli user go ma.
5. Przetłumaczyć realny fixture ASS około 600 linii one-shot.
6. Porównać line count/timing/style/tag.

### Fala 13 — pełne bramki

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

Potem:

```bash
uv build
```

Sprawdzić wheel assets i clean install smoke.

## 16. Macierz testów

### 16.1. Registry i lazy imports

- sześć dokładnych IDs;
- Literal i registry w synchronizacji;
- suggested model list nie jest allowlist;
- unknown engine -> config error;
- `openai_compatible` empty suggestions;
- import facade nie ładuje `openai`, `anthropic`, `google.genai`;
- create one engine nie ładuje pięciu pozostałych.

### 16.2. Config

- empty provider/model;
- custom model accepted;
- compatible URL required;
- compatible empty key accepted;
- invalid timeout/retries/ranges;
- all generation fields `None`;
- config frozen;
- secrets absent from repr, jeśli config repr może trafić do logu.

### 16.3. Lifecycle

- lazy client;
- reuse;
- close;
- double close;
- exception inside context still closes;
- complete after close fails clearly;
- missing SDK gives provider unavailable;
- missing key gives auth.

### 16.4. Retry

- connection;
- timeout;
- 429;
- 500/502/503/504;
- Retry-After;
- OpenRouter 402, structured quota i daily limit bez retry;
- fatal 400/401/403/404 once;
- 404 model code vs 404 bad endpoint;
- max retries exact;
- no real sleeping.

### 16.5. Provider request mapping

Per provider:

- roles;
- multiple ordered text parts;
- system separation;
- custom model;
- optional params omitted;
- max output mapping;
- OpenAI `max_completion_tokens` vs compatible `max_tokens`;
- response text;
- usage;
- finish reason;
- latency non-negative;
- close.
- Gemini timeout seconds→milliseconds i `attempts=1`;
- Anthropic 413/529 oraz kolejność typed exceptions;
- Gemini `ClientError`/`ServerError` i surowe `httpx` network/timeout.

### 16.6. Prompt composer

- exact module order;
- main/style lookup;
- discovery built-in + `config/prompts/{tasks,styles,modules}`;
- ignore non-`.txt`;
- empty/non-UTF-8/duplicate ID error;
- unknown ID;
- deterministic newline;
- fingerprint stable;
- dynamic data excluded from fingerprint;
- XML-like delimiter escaping;
- prompt injection text remains data;
- glossary ordering;
- all limits;
- omitted counter;
- UTF-8 Polish/Japanese;
- package resource present.

### 16.7. `[N]` protocol

- clean;
- noise;
- missing;
- duplicate;
- extra;
- out-of-range;
- reordered valid indices;
- empty result;
- markdown fence;
- repair success;
- repair exhaustion;
- shrink uneven batch;
- shrink to one;
- single-line failure raises;
- transport error never triggers repair.
- context/output limit skips identical retry and splits;
- one-shot do 1000 niepustych linii;

### 16.8. Translation facade

- Google/DeepL dedup unchanged;
- LLM spoken duplicates preserved;
- LLM displayed duplicates deduplicated;
- FBF collapse unchanged;
- factory creates selected ID;
- LLM typed failure reaches queue coordinator;
- no automatic paid provider fallback;
- failed translation -> failed `FileOutcome`, nie done bez pliku;
- close each engine;
- no mixed provider result;
- cancellation.

### 16.9. Pipeline

- LLM not selected -> no LLM import/client;
- LLM selected -> correct key;
- each provider key routing;
- compatible URL;
- MKV;
- TXT;
- translated file structure;
- error/warning report;
- usage aggregation;
- content-free call records z poprawnym purpose/prompt identity;
- call records przypisane do właściwego pliku także po failure;
- worker-local service/client lifecycle;
- terminal summary completion/repair/retry/tokens/provider cost.

### 16.10. Settings panel

- provider cycle;
- suggested model cycle;
- inline custom edit;
- cancel edit;
- provider missing key marker;
- compatible base URL;
- prompt/style/modules discovery;
- concurrency default 4 i validation `1..4`;
- migration old field;
- save/load every new field;
- corrupt JSON still defaults.

### 16.11. Live smoke

Markery:

- `@pytest.mark.network`;
- `@pytest.mark.integration`;
- `skipif` po brakującym key/URL.

Live smoke nie może wejść do zwykłej niezawodnej ścieżki CI.

Obowiązkowe ręczne scenariusze:

- Gemini `gemini-3.5-flash-lite` przez `ANISHIFT_GEMINI_API_KEY`;
- OpenRouter przez `ANISHIFT_OPENROUTER_API_KEY`;
- realny plik około 600 linii przechodzi one-shot;
- brak któregoś klucza daje skip, nie failure CI.

### 16.12. Scheduler i circuit breaker

- cztery requesty blokują się równolegle na kontrolowanych `Event`/`Barrier`;
- natural order pending queue;
- zakończenie ekstrakcji natychmiast enqueue'uje plik;
- gotowy plik przechodzi dalej bez czekania na pozostałe;
- active requests finish, unsent stay queued;
- 429 otwiera circuit i blokuje nowe requesty;
- najstarszy uszkodzony plik jest jedynym probe;
- sukces zwiększa limit `1 → 2 → 4`;
- fatal auth/quota/payment pokazuje `settings`/`finish`;
- `settings` wznawia tylko niewykonane pliki;
- `finish` zachowuje gotowe i oznacza resztę `not_processed`;
- żadnych timingowych `sleep` w testach.

## 17. Definition of Done

| Obszar | Dowód |
|---|---|
| Domena i providerzy | protocol, registry, lazy import i sześć fake contract tests |
| Settings | Gemini default, custom model, missing key, env-only secrets |
| One-shot | realny smoke ~600 linii i test jednej próby do 1000 |
| Output | parser, jeden repair, adaptive split i subtitle integrity |
| Retry | typed error mapping, Retry-After i dokładna liczba prób |
| Kolejka | cztery workery, natural order, pause/resume i ramp-up tests |
| Trwała awaria | `settings`/`finish`, brak ponowienia gotowych plików |
| Deduplikacja | spoken preserve, displayed deduplicate, Google/DeepL bez regresji |
| Layout ASS | inline tags zachowują kotwice, displayed authored breaks, drawings passthrough |
| Prompty | built-in + custom discovery, composer, fingerprint i safe data |
| Raport | content-free calls, completion/repair/retry/tokens/optional cost |
| Pakiet | wheel zawiera wbudowane prompt assets |
| Repo | cztery pełne bramki jakości |

Etap jest gotowy dopiero, gdy:

- wszystkie testy przechodzą;
- wheel zawiera prompt assets;
- nie ma importu cross-domain;
- nie ma zamkniętej walidacji modeli;
- nie ma `except Exception` bez precyzyjnego boundary i uzasadnionego `noqa`;
- nie ma sekretu ani prompt content w logu;
- custom model działa;
- Gemini `gemini-3.5-flash-lite` i OpenRouter przechodzą warunkowy live smoke;
- cztery requesty mogą działać równolegle;
- trwała awaria nie uruchamia automatycznego płatnego fallbacku;
- nie istnieje funkcja korekty gotowego tłumaczenia w Etapie 5.

## 18. Ryzyka i zabezpieczenia

| Ryzyko | Skutek | Zabezpieczenie |
|---|---|---|
| szybko starzejące się modele | martwy picker | suggestions, nie allowlist; custom ID |
| podwójny retry SDK + facade | koszt i latency | SDK retry off; jeden retry owner |
| auth potraktowany transient | bezsensowne próby | fatal hierarchy |
| malformed output jako transport error | błędny retry/circuit | osobne retry/repair |
| klient współdzielony między workerami | race i pomieszane rekordy | per-worker service/client |
| circuit bez centralnej kolejki | nowe requesty startują po awarii | jeden scheduler per run |
| dedup niszczy dialog | błędne tłumaczenie identycznych kwestii | spoken preserve |
| brak dedup znaków | koszt setek identycznych napisów | displayed deduplicate |
| prompt injection z napisów | model wykonuje tekst | safe serializer + untrusted block |
| prompt assets brak w wheel | runtime crash | build resource smoke |
| model odrzuca temperature | 400 | optional `None`, send only explicit |
| custom endpoint bez auth | SDK odrzuca pusty key | internal placeholder only |
| jeden ogromny batch | context/output error | limit 1000 + adaptacyjny split |
| testy concurrency oparte na czasie | flaky CI | `Event`/`Barrier`, fake clock |
| prompt usera trafi do repo | prywatna konfiguracja w commicie | runtime `config/prompts/` gitignored |
| log wycieka napisy | prywatność | metadata-only logs |

## 19. Antywzorce zakazane podczas implementacji

- `if provider == ...` w pipeline poza wyborem właściwego klucza;
- `if engine.engine_id == "llm"` w dedup;
- globalny aktywny model;
- fallback modelu ukryty w providerze;
- pełny katalog OpenRouter w repo;
- model allowlist validation;
- prompt w `settings.json`;
- prompt jako Markdown;
- provider importowany w `services/llm/__init__.py`;
- async facade bez potrzeby;
- `asyncio.run()` per batch;
- współdzielenie klienta SDK albo call-record bufferu między workerami;
- globalny circuit breaker przeżywający `run_pipeline`;
- timingowe `sleep` w testach concurrency;
- retry w SDK, providerze i facade jednocześnie;
- implementowanie korekty gotowego tłumaczenia w Etapie 5;
- source padding jako „sukces” po awarii;
- logowanie request/response body;
- ręczna edycja dependencies w `pyproject.toml`;
- implementacja multimediów bez konsumenta;
- agent research uruchamiany per batch;
- abstrahowanie hypothetical seventh provider przed ukończeniem sześciu.

## 20. Kolejność commitów

Proponowane małe commity, każdy po zielonych bramkach zakresu:

1. `feat(llm): add domain contracts and lazy registry`
2. `feat(llm): add sync facade lifecycle and retry`
3. `feat(llm): add openai-compatible providers`
4. `feat(llm): add anthropic and gemini providers`
5. `feat(translation): add modular prompt composer`
6. `fix(translation): preserve spoken context and deduplicate signs`
7. `feat(pipeline): wire llm completion into translation`
8. `feat(cli): add llm provider model and prompt settings`
9. `feat(pipeline): add concurrent llm queue and circuit breaker`
10. `feat(cli): add llm failure recovery commands`
11. `test(llm): add provider contract and live smoke coverage`

Przed każdym commitem uruchomić pełne bramki z root `AGENTS.md`. Jeżeli zakres
commitów okaże się zbyt szeroki, dzielić dalej, nie łączyć niezależnych fal.

## 21. Checklista wykonawcy

### Przed kodem

- [x] Potwierdzony plan.
- [x] Feature branch.
- [x] Wbudowane minimalne prompt assets i działający loader custom `.txt`.
- [x] Aktualne SDK docs sprawdzone.
- [x] Model suggestions sprawdzone.
- [x] Baseline gates zielone.

### Domena LLM

- [x] Typowane ordered parts.
- [x] Config z Gemini `gemini-3.5-flash-lite` jako default.
- [x] Errors z Transient/Fatal.
- [x] Registry lazy.
- [x] Suggestions nie są allowlist.
- [x] Sync lifecycle.
- [x] Jeden retry owner.
- [x] Six provider contract tests.

### Translation

- [x] Prompt assets `.txt`.
- [x] Deterministyczny composer.
- [x] Safe dynamic serializer.
- [x] `[N]` strict.
- [x] Repair osobno od retry.
- [x] Shrink.
- [x] Brak silent source success.
- [x] Input policy per stream.
- [x] Spoken preserve i displayed deduplicate.
- [x] Brak automatycznego paid provider fallback.

### Pipeline i UI

- [x] Provider/model z settings.
- [x] Custom model typing.
- [x] Keys tylko z env.
- [x] Compatible URL.
- [x] MKV i TXT.
- [x] Cztery worker-local clients.
- [x] Shared limiter/circuit per run.
- [x] Natural-order queue i retry priority.
- [x] `settings`/`finish`.
- [x] Dynamic custom prompt discovery.
- [x] Usage i prompt metadata.

### Weryfikacja

- [x] Ruff.
- [x] Format.
- [x] Mypy.
- [x] Full pytest.
- [x] Wheel assets.
- [x] Live smoke dostępnych providerów.
- [x] Subtitle integrity diff.
- [x] Brak sekretów/content w logach.

## 22. Najważniejsze punkty review

Reviewer ma zacząć od tych pytań:

1. Czy jakikolwiek błąd LLM może zostać uznany za sukces?
2. Czy trwała awaria zatrzymuje nowe requesty i oferuje `settings`/`finish`
   bez ponownego wykonywania gotowych plików?
3. Czy custom model przechodzi bez whitelist?
4. Czy import facade jest naprawdę lazy?
5. Czy SDK retry jest naprawdę wyłączone?
6. Czy system prompt Gemini jest system instruction?
7. Czy Anthropic nie dostaje roli `system` w messages?
8. Czy duplicate `spoken` pozostają oddzielne, a `displayed` są deduplikowane?
9. Czy cztery workery mają osobne klienty, ale wspólny per-run circuit?
10. Czy wheel zawiera `.txt`?
11. Czy prompt fingerprint nie zawiera danych usera?
12. Czy panel pozwala wpisać, a nie tylko wybrać model?
13. Czy custom `.txt` są wykrywane bez zmiany kodu?
14. Czy OpenRouter nigdy nie jest automatycznym płatnym fallbackiem?
15. Czy wspólny strumień zachowuje kontekst, deduplikację znaków i layout ASS?

## 23. Świadome odroczenia

Poza etapem 5 pozostają:

- obrazy, audio i wideo jako content parts;
- capabilities per model;
- analiza płci/mówcy/sceny;
- wydobywanie klatek i audio;
- research agent i automatyczny glossary builder;
- cross-episode glossary database;
- provider catalog API;
- pricing tables;
- własny lokalny runtime;
- publiczny streaming;
- LLM chat command;
- multi-provider routing;
- nazwane profile per funkcja;
- korekta gotowego tłumaczenia i osobny model correction;
- edytor promptów w terminalu oraz automatyczne otwieranie Notatnika/`$EDITOR`;
- automatyczne eval-driven wybieranie modelu.

Granice typów i composition są przygotowane tak, aby późniejsze dodanie tych
funkcji nie wymagało przeniesienia promptów do domeny LLM ani łamania
translation/LLM independence.

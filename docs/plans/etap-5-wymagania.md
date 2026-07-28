# Etap 5 — LLM — wymagania

> Status: **APPROVED — 2026-07-26**.
>
> Dokument definiuje zachowanie Etapu 5. Szczegóły wykonawcze znajdują się w
> [`etap-5-llm-plan.md`](etap-5-llm-plan.md).

## 1. Cel

Etap 5 dostarcza ogólną domenę LLM z sześcioma providerami i wykorzystuje ją
do tłumaczenia napisów. Publiczne API aplikacji pozostaje synchroniczne, a
pipeline wykonuje blokujące requesty równolegle przez kontrolowaną pulę wątków.

User może:

- wybrać LLM jako translation engine;
- wybrać providera i dowolny model;
- korzystać z promptów wbudowanych oraz własnych plików `.txt`;
- tłumaczyć do czterech plików równolegle;
- po trwałej awarii providera zmienić ustawienia i wznowić kolejkę albo
  zakończyć z już wykonanymi plikami.

Korekta gotowego tłumaczenia nie wchodzi do Etapu 5. Bez dodatkowego kontekstu
podwaja czas i koszt, a nie rozwiązuje błędów płci, relacji ani znaczenia sceny.

## 2. Providerzy i modele

Rejestr obejmuje dokładnie:

- `anthropic`;
- `deepseek`;
- `gemini`;
- `openai`;
- `openai_compatible`;
- `openrouter`.

Zasady:

- caller zawsze przekazuje `engine_id` i `provider_model_id`;
- provider nie wybiera modelu automatycznie;
- mała lista sugerowanych modeli służy tylko jako podpowiedź;
- dowolny własny model jest dozwolony;
- provider sprawdza dostępność modelu przy realnym requestcie;
- provider bez klucza pozostaje widoczny w `/settings` z oznaczeniem
  `missing key`;
- `openai_compatible` może działać bez klucza, ale wymaga `base_url`;
- domyślna konfiguracja to Gemini i `gemini-3.5-flash-lite`;
- OpenRouter nie jest automatycznym płatnym fallbackiem.

Klucze pochodzą wyłącznie z env/`.env`. Nie trafiają do `settings.json`,
logów, wyjątków ani raportów.

## 3. Publiczna domena LLM

Jedna domena `anishift.services.llm` udostępnia:

- typowane, uporządkowane wiadomości i części tekstowe;
- synchroniczne `complete()`;
- lifecycle `close()` i context manager;
- lazy import SDK i lazy utworzenie klienta;
- wspólną odpowiedź: tekst, provider, model, finish reason, latency i usage;
- wspólną hierarchię błędów;
- centralne retry transportowe.

Domena nie zna:

- anime;
- tłumaczenia;
- promptów `[N]`;
- pipeline;
- UI.

Translation zna tylko własny mały protokół completera. Composition root mapuje
go na ogólną domenę LLM.

## 4. Lifecycle i współbieżność

Kontrakty domen pozostają synchroniczne. Współbieżność realizuje pipeline przez
`ThreadPoolExecutor`, ponieważ:

- istniejący pipeline i SDK są blokujące;
- requesty LLM są I/O-bound;
- repo ma już sprawdzony model wątków dla ekstrakcji;
- nie ma potrzeby przebudowy wszystkich domen na `asyncio`.

Zasady wykonania:

- domyślnie `llm_max_concurrency = 4`;
- każdy aktywny worker ma własny lifecycle klienta;
- provider ma wspólny, thread-safe limiter i circuit breaker;
- odkryte pliki są uporządkowane naturalnie;
- zakończona ekstrakcja natychmiast udostępnia plik kolejce tłumaczenia;
- gotowy plik nie czeka na wynik pozostałych;
- rozpoczętych requestów nie anulujemy po błędzie innego requestu;
- niewysłane zadania pozostają w kolejce.

## 5. One-shot i protokół odpowiedzi

LLM tłumaczy napisy przez ścisły kontrakt:

```text
[1] translated line
[2] translated line
```

Fast path:

- maksymalnie 1000 niepustych linii jednego strumienia trafia do jednego
  completion;
- zwykły plik ma zostać przetłumaczony one-shot;
- parser wymaga dokładnego zbioru indeksów;
- dodatkowa proza bez indeksu może zostać zignorowana;
- brak, duplikat, dodatkowy indeks albo pusta linia jest błędem wyniku.

Po błędzie:

1. jeden request repair naprawia wyłącznie format;
2. po nieskutecznym repair lub odpowiedzi uciętej przez limit batch dzieli się
   na dwie stabilne połowy;
3. podział trwa do pojedynczej linii;
4. pojedyncza nieskuteczna linia kończy engine błędem;
5. tekst źródłowy nigdy nie jest zwracany jako udane tłumaczenie.

Context-length i output-length uruchamiają adaptacyjny podział, nie ponowienie
identycznego requestu.

## 6. Deduplikacja i kontekst

Istniejąca klasyfikacja `DIALOG`/`SIGN`/`UNCERTAIN` pozostaje źródłem podziału
na `spoken` i `displayed`.

Polityka LLM:

- `spoken` zachowuje każde wystąpienie i kolejność;
- wcześniejsze zwijanie jednej animacji FBF pozostaje;
- `displayed` deduplikuje identyczny tekst;
- whitespace nie trafia do modelu, ale zachowuje pozycję w wyniku;
- tytuł, summary i glosariusz są opcjonalnymi, ograniczonymi danymi;
- etap nie zgaduje płci, mówcy ani sceny;
- etap nie implementuje pamięci między batchami ani multimodalności.

Google i DeepL zachowują dotychczasową deduplikację obu strumieni.

## 7. Prompty

Prompty są zwykłymi plikami UTF-8 `.txt`.

Źródła:

```text
anishift/services/translation/engines/llm/prompts/assets/
config/prompts/
├── tasks/
├── styles/
└── modules/
```

Zasady:

- aplikacja automatycznie wykrywa `.txt` w kontrolowanych podfolderach;
- nazwa pliku bez rozszerzenia jest ID;
- plik pusty, nie-UTF-8 albo duplikat ID daje czytelny błąd;
- inne rozszerzenia są ignorowane;
- user może dodać własny prompt bez zmiany kodu;
- `/settings` pokazuje listę wykrytych promptów i stylów;
- dokładnie jeden task i jeden styl są wybierane dla requestu;
- obowiązkowy kontrakt `[N]` jest wbudowany i nie może zostać wyłączony;
- składanie ma deterministyczną kolejność;
- dynamiczne napisy, kontekst i glosariusz są escapowane i oznaczone jako
  niezaufane dane;
- ustawienia zapisują ID, nie treść promptu;
- edycja przez Notatnik/`$EDITOR` jest odłożona poza Etap 5.

## 8. Retry, circuit breaker i kolejka

Retry transportowe i naprawa outputu są rozłączne.

Retry obejmuje:

- timeout;
- problemy sieciowe;
- rate limit;
- przejściowe 5xx.

Retry nie obejmuje:

- błędnego lub brakującego klucza;
- braku płatności/karty;
- wyczerpanej quota lub dziennego limitu;
- błędnego modelu;
- błędnego endpointu;
- niepoprawnego requestu.

SDK providerów mają wyłączone własne automatyczne retry. Fasada LLM jest jednym
właścicielem retry.

Po 429 lub przejściowej awarii:

1. circuit breaker wstrzymuje uruchamianie nowych requestów;
2. rozpoczęte requesty mogą się zakończyć;
3. aplikacja respektuje `Retry-After` albo backoff;
4. najstarszy uszkodzony plik jest ponawiany sam;
5. po sukcesie współbieżność wraca stopniowo `1 → 2 → 4`;
6. po wyczerpaniu prób provider zostaje wyłączony dla bieżącego uruchomienia.

Błąd pojedynczego outputu nie zatrzymuje innych plików. Jego repair albo
podzielone części mają pierwszeństwo przed nowymi zadaniami, a pozostała kolejka
zachowuje porządek naturalny.

## 9. Trwała awaria i interakcja

Po auth, quota, braku płatności albo trwałej niedostępności:

- nowe requesty nie startują;
- aktywne requesty mogą się zakończyć;
- ukończone pliki pozostają gotowe;
- provider zostaje zamknięty;
- terminal pokazuje liczbę gotowych i oczekujących plików.

User dostaje dwie akcje w stylu komend terminalowych:

```text
> settings
> finish
```

`settings`:

- otwiera istniejący panel ustawień;
- pozwala wskazać zastępczego providera i model;
- waliduje nową konfigurację;
- wznawia tylko niewykonane pliki;
- plik, który ujawnił awarię, ma pierwszeństwo;
- pozostałe pliki zachowują porządek naturalny.

`finish`:

- kończy z już wykonanymi plikami;
- pozostałe oznacza jako niewykonane z czytelną przyczyną;
- nie przedstawia częściowego przebiegu jako pełnego sukcesu.

To jedyny dopuszczony przypadek, gdy tryb auto wymaga decyzji usera.

## 10. Błędy

Wspólna hierarchia rozróżnia co najmniej:

- config;
- auth/permission;
- model;
- context length;
- quota/payment;
- rate limit;
- timeout;
- provider unavailable;
- request/output;
- cancellation.

Każdy provider mapuje typed SDK exceptions i statusy HTTP na tę hierarchię.
Wyższe warstwy nie importują wyjątków SDK. Nieznane 4xx są fatal request,
nieznane 5xx są transient unavailable.

Komunikat zawiera bezpieczny opis i sugestię działania. Nie zawiera klucza,
pełnego requestu, promptu, napisów ani response body.

## 11. Raport użycia

Pipeline zbiera beztreściowe rekordy:

- purpose;
- provider i model;
- input/output/total tokens, jeśli zwrócone;
- latency;
- finish reason;
- prompt ID, wersję i fingerprint;
- opcjonalny bezpieczny kod błędu.

Końcowe podsumowanie terminalowe pokazuje:

- liczbę wykonanych i niewykonanych plików;
- liczbę completion, repair i retry;
- dostępne token usage;
- rzeczywisty koszt tylko wtedy, gdy provider zwraca go bezpośrednio.

Etap nie utrzymuje tabeli cen i domyślnie nie zapisuje osobnego raportu JSON.
Typowany wynik pipeline umożliwia późniejszy jawny eksport.

## 12. Definition of Done

- wszystkie sześć providerów spełnia jeden kontrakt;
- import domeny nie importuje żadnego SDK;
- Gemini `gemini-3.5-flash-lite` przechodzi live smoke z kluczem z `.env`;
- OpenRouter przechodzi live smoke z kluczem z `.env`;
- provider bez klucza jest widoczny jako `missing key`;
- custom model przechodzi przez panel i loader bez allowlisty;
- one-shot działa dla realnego pliku około 600 linii;
- batch do 1000 linii ma deterministyczny protokół i adaptacyjny podział;
- cztery requesty mogą działać równolegle;
- testy dowodzą pauzy, wznowienia, priorytetu retry i circuit breakera;
- trwała awaria oferuje `settings` albo `finish`;
- gotowe pliki nie są wykonywane ponownie po wznowieniu;
- spoken zachowuje wystąpienia, displayed deduplikuje;
- własne prompty z `config/prompts/` są automatycznie wykrywane;
- wheel zawiera prompty wbudowane;
- nie ma funkcji korekty w Etapie 5;
- Google i DeepL nie mają regresji;
- pełne bramki repo przechodzą:

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

Live smoke jest ręczny i warunkowy. Brak klucza nie psuje CI.

## 13. Poza zakresem

- korekta gotowego tłumaczenia;
- automatyczny płatny fallback na OpenRouter;
- edytor promptów w terminalu lub automatyczne otwieranie Notatnika;
- obraz, audio i wideo w requestach;
- analiza postaci, płci i scen;
- cross-batch i cross-episode memory;
- automatyczny glossary builder;
- pricing table;
- streaming;
- chat LLM;
- lokalny runtime modeli.

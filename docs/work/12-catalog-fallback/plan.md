---
kind: plan
status: draft
baseline: main @ 4365a51
created: 2026-10-25
---

# Plan: zapisane dane AniList zastępują AniList w czasie awarii

## 1. Cel

Wdrożyć `specification.md` (W1–W13) najmniejszą zmianą: plikowa kopia ostatniego udanego grafu franczyzy i
harmonogramu każdego wpisu, używana przez `AcquisitionService` tylko wtedy, gdy AniList zawiedzie. Panel i log mówią,
że działa kopia.

## 2. Rezultat użytkownika

Przy kolejnej awarii AniList subskrypcje nadal znajdują i pobierają odcinki, lista odcinków ma terminy, znane wpisy
się otwierają, a panel pokazuje „AniList nie odpowiada · dane z 21.10 17:14”.

## 3. Warunki końcowe

- [ ] W1–W13 mają testy, które przechodzą (§10).
- [ ] Przy działającym AniList istniejące testy przechodzą bez zmiany liczby żądań.
- [ ] Bramki z root `AGENTS.md` i pre-push (`mypy --platform linux`) przechodzą.
- [ ] Właściciel przeszedł checkpoint w panelu (§9).
- [ ] Decyzje D1–D6 ze `specification.md` są rozstrzygnięte przed fazą 1.

## 4. Nie-cel

Brak drugiego dostawcy danych, brak cache z TTL przy działającym AniList, brak zmiany klucza `anilist_id`, schematu
stanu i klasyfikacji H1.

## 5. Authority i baseline

| Źródło | Rola |
|---|---|
| `specification.md` | wymagania, zakazy, decyzje D1–D6 |
| `dependency-map.md` | stan kodu i dowód awarii |
| `research.md` | uzasadnienie wariantu, odrzucone alternatywy |
| root `AGENTS.md`, `anishift/AGENTS.md`, `anishift/services/catalog/AGENTS.md`, `anishift/application/AGENTS.md`, `tests/AGENTS.md` | reguły repo |
| `.agents/skills/simple/SKILL.md`, `.agents/skills/coding/SKILL.md` z `references/python.md`, `comments-docstrings.md`, `testing.md` | standard kodu |

**Baseline:** `main` @ `4365a51`; `uv run pytest tests/services/catalog` zielone 2026-10-25.

**Stan drzewa 2026-10-25:** w checkout trwa praca innych wykonawców (zmiany w `.github/workflows/ci.yml`,
`services/subtitles/fitting.py`, `scripts/hooks/check_mutating_assign.py` oraz workstreamy 13–19 w `docs/work/`).
Faza 0 sprawdza stan od nowa.

**Prace równoległe dotykające tych samych plików:**

- `docs/work/18-library-titles-covers/plan.md`: `AniListCatalog.covers`, `config/watch/posters/`,
  `AniListCatalog.search` dla tytułów Biblioteki;
- `docs/work/19-tvmaze-episode-titles/plan.md`: `TvMazeCatalog`, pola `_Remembered.titles` w `acquisition.py`,
  `read_listing`, `bootstrap.py`, `services/catalog/__init__.py` i `AGENTS.md`.

## 6. Stan aktualny

### 6.1 Zachowanie i luka

- Każda operacja AniList przy awarii kończy się `TitleCatalogError` `TITLE_CATALOG_FAILED`; nie ma żadnej trwałej
  kopii (dependency-map.md, §1, §6).
- Pamięć `_Remembered` trzyma graf i harmonogram 900 s (`acquisition.py:492-503`); po jej wygaśnięciu albo
  restarcie każda operacja potrzebuje AniList.
- Sprawdzenie subskrypcji zawodzi na grafie w `_episode_request` (`acquisition.py:1123`), choć ani.zip i Torrentio
  działają (dependency-map.md, §7).
- Log nie zapisuje powodu ani statusu porażki AniList (dependency-map.md, §6).

### 6.2 Reuse

| Element | Ścieżka / symbol | Co wykorzystać | Ograniczenie |
|---|---|---|---|
| Walidacja węzła grafu | `_collect_franchise` (`services/catalog/anilist.py:276-307`) przez cienką publiczną funkcję w `anilist.py` | odczyt zapisanych węzłów tym samym walidatorem co odpowiedź na żywo | sam walidator scala węzły; słownik odtwarzamy z pliku w zapisanej kolejności, nie przez ponowne scalanie (§8.3) |
| Kompletność łańcucha | `franchise_traversal` (`application/episode_selection.py:410-415`) | W3 i wybór kandydatów do W4 | — |
| Dekoder kandydata | `candidate_from_node` (`anilist.py:359-387`) | kandydaci z zapisanych węzłów | zwraca `None` bez romaji |
| Kontekst sezonu z grafu | `graph_season_context` (`application/acquisition.py:1434-1438`) | W5 | — |
| Normalizacja tytułów | `normalize_series`, `series_forms` (`acquisition.py:585-594`) | dopasowanie hasła w W4 | — |
| Wybór grafu zawierającego wpis | reguła `_known_graph` (`acquisition.py:1322-1339`) | ta sama kolejność preferencji dla W3 | dotyczy pamięci, nie plików |
| Zapis atomowy | wzorzec `ReadyStore._save` (`application/ready.py:306-314`) i `config/env_file.py:105-127` | plik tymczasowy w tym samym katalogu + `replace` | brak wspólnego helpera w `utils/` |
| Układ katalogów | `watch_dir()` (`anishift/paths.py:107-109`) | katalog `config/watch/catalog/` | `paths.py` tylko wylicza, nie tworzy |
| Krótka data w panelu | `_when` (`cli/interactive/subscription_texts.py:265-273`) | format `dd.mm HH:MM` | funkcja prywatna; dopuszczalne upublicznienie |
| Teksty odmów | `state_texts.py:85-87` | nowy powód D2 | — |
| Notka listy | `anime.py:1106-1111` | W8 | — |
| Wiersz statusu Subskrypcji | `subscription_warning` (`state_subscriptions.py:88-92`), `_adopt_subscriptions` (`state.py:1102-1105`), lista ownera (`automation.py:3650-3662`) | W9 | — |
| Wzorzec testu katalogu | `tests/services/catalog/test_anilist.py:20-45`, nagrania `tests/fixtures/search/anilist__franchise__*.json` | replay odpowiedzi bez sieci | — |
| Fałszywy katalog | `_TitleCatalog` w `tests/application/test_acquisition.py` (`schedule_fails`, `scheduled`) | testy fallbacku w usłudze | — |
| Przechwycenie logów | `loguru_logger.add(...)` w `tests/application/test_subscription_owner.py:415-418` | W12 | — |

### 6.3 Dowody

| Twierdzenie | Dowód | Status |
|---|---|---|
| Cooldown pomija żądanie harmonogramu i test to chroni | `acquisition.py:1292-1293`; `test_retry_after_the_block_restores_the_schedule_without_asking_ani_zip_again` (`titles.scheduled == []`) | verified |
| Harmonogram AniList zawiera przyszłe odcinki | research.md, §4.1 | verified |
| ani.zip, arm i Kitsu działały w awarii | dependency-map.md, §7 | verified |
| Panel bez rezydenta też buduje `AcquisitionService` | `bootstrap.py:75`, `anime.py:2175` (`isinstance(self._acquisition, AcquisitionService)`) | verified |

## 7. Zakres

### In scope

- `services/catalog/saved.py`: plikowa kopia grafów i harmonogramów.
- `AniListCatalog._post`: log powodu i statusu porażki (W12).
- Pola `as_of` w `FranchiseGraph`, `Franchise`, `SeasonAiring`, `TitleCandidate` oraz `catalog_as_of` w `EpisodeListing`.
- `AcquisitionService`: zapis po sukcesie, użycie kopii w czterech miejscach, log użycia kopii.
- Owner: odmowa nowej subskrypcji na kopii (D2), pole `catalog_as_of` na liście subskrypcji.
- Panel: notka na liście odcinków, w widoku wpisów i przy wynikach wyszukiwania; wiersz statusu Subskrypcji.
- `paths.py`, `bootstrap.py`, `services/catalog/AGENTS.md`, `services/catalog/__init__.py`, `config/README.md`,
  root `AGENTS.md` (sekcja „Dane runtime”, jedno zdanie o `config/watch/catalog/`), `docs/ideas.md` §5 i §7.

### Out of scope

- Drugi dostawca danych, TTL przy działającym AniList, okładki, tytuły odcinków TVmaze.
- Zmiany w rejestrze decyzji `decisions.jsonl` i `cases.jsonl`.

### Forbidden

- Rejestr silników, `engines/` lub wybór dostawcy w `services/catalog`.
- Nowa zależność, ręczna edycja `pyproject.toml`.
- Zmiana `WATCH_STATE_SCHEMA_VERSION`, kluczy stanu, golden H1, `episode_identity.py`.
- Odczyt kopii zamiast żądania, gdy AniList odpowiada.
- Pobieranie z wyprzedzeniem wpisów, których aplikacja nie odczytała.
- Zmiana plików w `config/`, `workspace/` właściciela i uruchamianie jego rezydenta; testy działają w `tmp_path`.
- Logowanie hasła wyszukiwania, ścieżek absolutnych, `ErrorContext.details`, treści odpowiedzi.

### Deferred

- Kalendarz Shikimori (D4), TTL dla oszczędności żądań.

### Dozwolone decyzje lokalne

- Nazwy prywatnych funkcji, kolejność argumentów, podział testów na pliki.
- Pomijanie zapisu, gdy bajty pliku byłyby identyczne.
- Upublicznienie `_when` albo mała funkcja formatująca w tym samym module.
- Sposób przekazania `as_of` grafu do `read_listing` (np. zwrot grafu zamiast samego `bool` w `_graph_movie`).

### Zatrzymaj się i wróć po decyzję, gdy

- zmiana wymaga podbicia schematu stanu, zmiany IPC bez wartości domyślnych albo zmiany golden H1;
- istniejący test koduje kontrakt sprzeczny z W2–W7 (nie wolno go osłabiać);
- workstream 18 albo 19 zmienił `read_listing`, `_Remembered` lub `bootstrap.py` tak, że plan przestaje pasować;
- regulamin AniList albo decyzja D1 wyklucza kopię.

## 8. Target design

### 8.1 Odpowiedzialności

| Element | Odpowiada za | Owner danych | Nie odpowiada za |
|---|---|---|---|
| `SavedCatalog` (`services/catalog/saved.py`) | zapis i odczyt plików, walidacja, limit, wybór grafu zawierającego wpis, lista kandydatów | pliki `config/watch/catalog/` | decyzję, kiedy użyć kopii |
| `AcquisitionService` | kiedy zapisać, kiedy użyć kopii, `as_of` w wynikach, log fallbacku | pamięć `_Remembered` | format plików |
| `AniListCatalog` | żądania i log porażki z powodem | — | kopia |
| `AutomationOwner` | odmowa D2, `catalog_as_of` listy subskrypcji | `WatchState` (bez zmian) | — |
| panel | teksty W8, W9, D3 | — | — |

### 8.2 Kontrakt `SavedCatalog`

```text
SavedCatalog(directory: Path, *, limit: int = SAVED_ENTRIES)
  save_graph(graph: FranchiseGraph) -> None
      zapisuje tylko graf kompletny (graph.complete); plik graph-<root_id>.json
  graph(anilist_id: int) -> FranchiseGraph | None
      plik tego wpisu; inaczej zapisany graf zawierający wpis bez brakującego łańcucha
      (franchise_traversal(...)[2] puste), preferencje jak _known_graph; wynik ma as_of
  save_schedule(schedule: SeasonAiring) -> None
      plik schedule-<anilist_id>.json
  schedule(anilist_id: int) -> SeasonAiring | None
      wynik ma as_of
  candidates() -> tuple[TitleCandidate, ...]
      węzły zapisanych grafów, dla których graph(id) zwróciłby graf; bez powtórzeń anilist_id; każdy z as_of
błędy: żadna metoda nie rzuca OSError ani błędu treści; zapis, który zawiódł, i plik nieczytelny są logowane
       (provider="saved_catalog", operation, error_class), plik uszkodzony = brak wpisu
efekty: katalog tworzony leniwie przy pierwszym zapisie; po zapisie usuwane najdawniej zmodyfikowane pliki
        danego rodzaju ponad limit
```

`SAVED_ENTRIES: Final[int] = 256` (D5). Katalog: `catalog_cache_dir() -> watch_dir() / "catalog"` w `paths.py`.

### 8.3 Format pliku

```text
{"version": 1, "saved_at": "<ISO 8601 UTC>", "kind": "graph" | "schedule", "data": {...}}
graph.data:    {"root_id": int, "queried": [int], "nodes": [[int, <surowy węzeł AniList>], ...]}   # kolejność = graph.nodes
schedule.data: {"anilist_id": int, "status": str, "episode_count": int | null,
                "episodes": [[int, int | null], ...],   # numer, airingAt w sekundach UTC
                "start_date": "YYYY-MM-DD" | null}
```

- Zapis grafu zachowuje dokładną kolejność `graph.nodes` jako listę par `[id, węzeł]`. Odczyt sprawdza każdy węzeł
  tym samym walidatorem co odpowiedź na żywo (cienka publiczna funkcja w `anilist.py` wokół `_collect_franchise`,
  wołana na kopii węzła i odrzucanym słowniku) oraz zgodność `id` pary z `id` węzła. Słownik `nodes` powstaje
  wprost z par, w kolejności z pliku, bez ponownego scalania. Powód: `parse_franchise_page` gwarantuje kolejność
  węzłów i krawędzi tylko przy odtwarzaniu oryginalnych stron, a widok franczyzy i wejście H1 biorą kolejność z grafu
  (`application/AGENTS.md`, `services/catalog/AGENTS.md`). `complete` liczy `franchise_traversal`; graf niekompletny
  albo bez `root_id` w węzłach = brak wpisu.
- Test równoważności: graf odczytany z pliku jest równy grafowi z replayu nagrania (`==` na `nodes`, `queried`,
  `complete` i lista `list(nodes)`), a `franchise_view` i `identity_target` dają identyczne wyniki.
- Odczyt harmonogramu odrzuca numery < 1, ujemne lub niecałkowite znaczniki czasu i nieznany status (status przez
  `TitleStatus`).
- Nieznana `version`, inny `kind` albo klucz pliku niezgodny z `root_id`/`anilist_id` = brak wpisu.
- Zapis: `tempfile.NamedTemporaryFile(dir=katalog, delete=False)` → `Path.replace`. `OSError` (na Windows także
  `PermissionError`, gdy inny proces czyta plik) → log i rezygnacja z zapisu.
- Nazwa pliku to stały prefiks rodzaju i liczba (`graph-123.json`, `schedule-123.json`), nigdy tekst z odpowiedzi;
  pliki nie zawierają ścieżek ani sekretów.

### 8.4 Nowe pola (wszystkie z wartością domyślną `None`)

| Typ | Plik | Pole | Kto ustawia |
|---|---|---|---|
| `FranchiseGraph` | `application/episode_selection.py:256-263` | `as_of: datetime \| None` | `SavedCatalog.graph` |
| `Franchise` | `episode_selection.py:246-253` | `as_of: datetime \| None` | `franchise_view` z `graph.as_of` |
| `EpisodeListing` | `episode_selection.py:302-315` | `catalog_as_of: datetime \| None` | `episode_listing(..., catalog_as_of=)` |
| `SeasonAiring` | `services/catalog/types.py:37-45` | `as_of: datetime \| None` | `SavedCatalog.schedule` |
| `TitleCandidate` | `types.py:61-77` | `as_of: datetime \| None` | `SavedCatalog.candidates` |

Protokół w `application/acquisition.py` obok `IdCatalog` (`:242-247`):

```text
class SavedTitleCatalog(Protocol):
    save_graph, graph, save_schedule, schedule, candidates   # sygnatury jak §8.2
AcquisitionService(..., saved_catalog: SavedTitleCatalog | None = None)
```

Typy z `services.catalog` tylko pod `TYPE_CHECKING`, zgodnie z `application/AGENTS.md`.

### 8.5 Przepływ w `AcquisitionService`

```text
_franchise_graph(id):
  pamięć świeża -> graf
  live = titles.franchise(id)
     sukces: pamięć jak dziś; saved.save_graph(live) gdy live.complete
     TITLE_CATALOG_FAILED: saved.graph(id) -> zapamiętaj w pamięci jak pobrany, log fallbacku
                           brak -> rzuć pierwotny błąd
_schedule(id):
  pamięć świeża -> (harmonogram, False)
  cooldown anilist -> saved.schedule(id) -> (kopia, False) | (None, True)      # bez wołania katalogu
  live sukces -> pamięć jak dziś; saved.save_schedule(live)
  TITLE_CATALOG_FAILED -> saved.schedule(id) -> (kopia, False) | (None, True)
read_listing:
  catalog_as_of = najwcześniejsza z (graph.as_of, schedule.as_of) różna od None
  schedule_warning tylko gdy brak harmonogramu ani na żywo, ani w kopii (bez zmian dla tej gałęzi)
find_titles(text):
  live; przy TITLE_CATALOG_FAILED -> saved.candidates() z aliasem lub native zawierającym normalize_series(text)
  (porównanie przez normalize_series obu stron), najwyżej TITLE_SEARCH_LIMIT; pusto -> rzuć pierwotny błąd
season_context(candidate):
  live; przy TITLE_CATALOG_FAILED -> saved.graph(candidate.anilist_id) -> graph_season_context; brak -> rzuć
```

- „Zapamiętaj w pamięci jak pobrany” oznacza tę samą regułę co `acquisition.py:868-873`: kopia trafia do
  `_Remembered` z bieżącym czasem. Skutek: przez 900 s (albo `max-age`) usługa nie pyta AniList o ten wpis — w
  awarii to jedna próba na wpis na okno pamięci zamiast dzisiejszych dwóch na każde sprawdzenie
  (dependency-map.md, §7) — a po powrocie AniList dane z kopii mogą być widoczne najwyżej tyle samo co dziś pamięć.
- Log fallbacku: `logger.warning("Saved catalog used", provider="anilist", kind=..., anilist_id=..., age_s=...)`;
  przy wyszukiwaniu bez hasła, tylko `count`.
- `_graph_movie` (`acquisition.py:963-970`) i `_known_status` (`:1306-1312`) działają na grafie z kopii bez zmian.
- `TitleCatalogError` łapany jest po kodzie `TITLE_CATALOG_FAILED`, jak w `_schedule` (`:1296-1298`). Inne błędy
  propagują jak dziś.

### 8.6 Owner i panel

- `_add_subscription` / `_subscription_draft` (`automation.py:3739-3759`, `:9088-9099`): gdy
  `read.listing.catalog_as_of` albo `franchise.as_of` nie jest `None` → odmowa `subscription_catalog_saved` (D2).
  Tekst w `state_texts.py:85-87`: „AniList nie odpowiada · nową subskrypcję dodasz po powrocie AniList”.
- `merge_listing` (`application/subscription_targets.py:520`): przegląd po migracji (`review_pending`) wymaga także
  `read.listing.catalog_as_of is None`. Bez tego `_reviewed` (`:692-702`) zamknąłby przegląd i mógł wstrzymać
  subskrypcję na podstawie kopii, a ten wynik trwa w stanie. Na kopii rekord w przeglądzie zostaje bez zmian, jak dziś
  przy ostrzeżeniu harmonogramu.
- Owner trzyma w pamięci, wyłącznie na swoim wątku, `_catalog_as_of: dict[str, datetime]` (klucz `subscription_id`).
  `_finish_subscription_check`
  wpisuje `result.read.listing.catalog_as_of`, gdy nie jest `None`, i usuwa klucz po odczycie na danych z AniList;
  usunięcie subskrypcji usuwa klucz. Owner publikuje `"catalog_as_of"` = najstarsza wartość albo `None` (ISO) obok
  `"problem"` w liście subskrypcji (`automation.py:3650-3662`) i w snapshocie (`:1774`). Restart czyści słownik.
- `subscription_warning(*, problem, shadow, catalog_as_of)` (`state_subscriptions.py:88-92`): kolejność problem →
  kopia → cień. Tekst D6: „AniList nie odpowiada · subskrypcje działają na danych z 21.10 17:14”.
- Lista odcinków (`anime.py:1106-1111`): gdy `listing.catalog_as_of` i brak innej notki → „AniList nie odpowiada ·
  dane z dd.mm HH:MM”. Widok wpisów: ta sama notka z `Franchise.as_of`.
- Wyniki wyszukiwania (`anime.py:2055-2069`): gdy któryś kandydat ma `as_of` → notka „AniList nie odpowiada ·
  wyniki tylko z zapisanych tytułów”.
- Godzina zawsze lokalna, format jak `subscription_texts._when`.

### 8.7 Edge cases i awarie

| Przypadek | Oczekiwane zachowanie | Dowód |
|---|---|---|
| AniList działa | bez odczytu kopii, zapis po sukcesie, wyniki bez `as_of` | unit (spy na `SavedCatalog`) |
| Awaria, brak kopii | błąd jak dziś, teksty jak dziś | unit + istniejące testy |
| Awaria, kopia sprzed 3 dni | wynik z `as_of`, notka z datą | unit |
| Cooldown 429 | harmonogram z kopii, katalog nie wołany | unit (`titles.scheduled == []`) |
| Graf niekompletny | nie zapisany; odczyt niekompletnego = brak | unit |
| Wpis tylko w grafie innego korzenia | graf korzenia, gdy łańcuch wpisu kompletny | unit |
| Plik uszkodzony / nieznana wersja / zła nazwa | brak wpisu, log `error_class` | unit |
| `replace` rzuca `PermissionError` | brak zapisu, log, wynik operacji bez zmian | unit (monkeypatch) |
| Dwa wątki zapisują ten sam wpis | plik czytelny, jeden z wyników | unit |
| Ponad 256 plików rodzaju | usunięte najdawniej zmodyfikowane | unit |
| Wyszukiwanie w awarii bez trafień | błąd `TITLE_CATALOG_FAILED`, nie „Nie znaleziono tytułu” | unit |
| Nowa subskrypcja na kopii | odmowa `subscription_catalog_saved` | unit ownera |
| Subskrypcja w przeglądzie po migracji, odczyt z kopii | rekord bez zmian, `review_pending` zostaje | unit `merge_listing` |
| Graf odczytany z pliku | ta sama kolejność węzłów i ten sam widok oraz cel H1 co z replayu | unit |
| Część subskrypcji na kopii, część na żywo | wiersz statusu z najstarszą datą, znika po ostatnim odczycie na żywo | unit ownera |
| Sprawdzenie subskrypcji na kopii | oferta, wybór, przekazanie do pobrania | integration |
| Powrót AniList | po wygaśnięciu pamięci dane na żywo, notki znikają, `catalog_as_of` = `None` | unit |

## 9. Plan wykonania

### Faza 0 — Preflight

1. `git status`, `git log -1`; zanotuj obce zmiany i nie dotykaj ich. Utwórz branch `work/catalog/01-anilist-fallback`
   od aktualnego `main` w głównym checkout (bez worktree).
2. Sprawdź, czy workstreamy 18 i 19 zostały scalone. Jeśli tak — przeczytaj ich diff w `acquisition.py`,
   `anilist.py`, `bootstrap.py`, `services/catalog/__init__.py` i dopasuj miejsca zmian. Jeśli nie — pracuj od `main`
   i zapisz w PR, że kolejny z nich robi rebase.
3. Potwierdź odpowiedzi właściciela na D1–D6. Odpowiedź inna niż rekomendacja zmienia plan tak:
   D1 = nie → zatrzymaj pracę i wróć do planowania; D2 = pozwalaj → pomiń odmowę z §8.6 i jej testy;
   D3 = nie → `find_titles` bez fallbacku i bez notki wyników; D4 = tak → osobny plan po tym; D5 → inna wartość
   `SAVED_ENTRIES` albo limit wieku w `SavedCatalog`; D6 → inne teksty.
4. `uv run pytest tests/services/catalog tests/application/test_acquisition.py -q` — baseline zielony.

**Gate:** czysty branch, znane decyzje, baseline zielony.

### Faza 1 — Kopia w `services/catalog`

**Pliki:** `services/catalog/saved.py` (CREATE), `types.py`, `anilist.py` (`_post`), `__init__.py`,
`application/episode_selection.py` (tylko pola `as_of`), `paths.py`, `services/catalog/AGENTS.md`,
`tests/services/catalog/test_saved.py` (CREATE), `tests/services/catalog/test_anilist.py`.

1. Pola `as_of` w `FranchiseGraph`, `SeasonAiring`, `TitleCandidate` (§8.4).
2. `SavedCatalog` według §8.2–§8.3.
3. `AniListCatalog._post` (`anilist.py:231-252`): przed każdym z pięciu `raise` błędu (`:240`, `:242`, `:246`, `:248`, `:251`)
   `logger.warning("AniList request failed", provider="anilist", reason=<_CatalogFailure>, status=<int | None>)`.
   Nie logować w `_catalog_error`, bo `candidate_from_node` łapie ten błąd przy zwykłym braku daty (`:369-372`).
4. `paths.catalog_cache_dir()`; eksport `SavedCatalog` w `services/catalog/__init__.py`.
5. `services/catalog/AGENTS.md`: plik `saved.py` i inwarianty (kopia tylko kompletnych grafów, odczyt przez
   `parse_franchise_page`, brak rzucania, limit).

**Testy (`unit`):** zapis–odczyt grafu z nagrania `anilist__franchise__387.json` i `101280.json` (replay jak
`test_anilist.py:20-45`); harmonogram; graf zawierający wpis; niekompletny pominięty; `candidates()` tylko otwieralne;
uszkodzony JSON, `version: 2`, zła nazwa; `PermissionError` na `replace`; dwa wątki; limit; log porażki AniList z
`reason` i `status` dla 403 z treścią z dokumentacji AniList (research.md, §4.1) i dla błędu transportu;
równoważność grafu z pliku i z replayu (§8.3).

**Pomiar:** czas `candidates()` i `graph(id)` dla wpisu spoza korzeni przy 256 kopiach największego nagrania
(`anilist__franchise__106509.json`). Wynik w PR. Jeśli wyszukiwanie w panelu na checkpoincie odczuwalnie się
zacina, zgłoś przed optymalizacją — nie dodawaj indeksu na zapas.

**Gate:** `uv run pytest tests/services/catalog -q`, `uv run mypy anishift/ tests/`.

### Faza 2 — Usługa i owner

**Pliki:** `application/acquisition.py`, `application/episode_selection.py` (`Franchise.as_of`,
`EpisodeListing.catalog_as_of`, `franchise_view`, `episode_listing`), `application/automation.py`,
`application/subscription_targets.py` (`merge_listing`, §8.6), `bootstrap.py`,
`tests/application/test_acquisition.py`, `tests/application/test_subscription_owner.py`,
`tests/integration/test_subscription_flow.py` (albo nowy plik obok, z `episode_download_support.py`).

1. Protokół `SavedTitleCatalog` i parametr `saved_catalog` (§8.4).
2. Przepływ §8.5 w `_franchise_graph`, `_schedule`, `read_listing`, `find_titles`, `season_context`.
3. `bootstrap._acquisition_service`: `saved_catalog=SavedCatalog(catalog_cache_dir())`.
4. Owner §8.6: odmowa D2, `_catalog_as_of`, pole w liście subskrypcji i snapshocie.

**Inwarianty:** istniejące testy `test_acquisition.py` przechodzą bez zmian, w tym
`test_retry_after_the_block_restores_the_schedule_without_asking_ani_zip_again` i
`test_expired_schedule_is_not_a_fallback_after_a_later_failure` (bez `saved_catalog` zachowanie jest dzisiejsze).

**Testy:**

- `unit` (`test_acquisition.py`): każdy wiersz §8.7 dotyczący usługi; `SavedCatalog` w `tmp_path`, `_TitleCatalog`
  z `schedule_fails` i nowym `franchise_fails`.
- `unit` (`test_subscription_owner.py`): odmowa D2; `catalog_as_of` ustawione po sprawdzeniu na kopii i
  wyczyszczone po sprawdzeniu na żywo.
- `unit` (`test_subscription_targets` albo istniejący plik testów `merge_listing`): rekord z `review_pending` na
  kopii zostaje bez zmian.
- `integration`: prawdziwe `AniListCatalog` + `httpx.MockTransport` z nagraniem grafu
  (`tests/fixtures/search/anilist__franchise__*.json`) i małą odpowiedzią harmonogramu zapisaną w teście (w repo nie ma
  nagrań `SCHEDULE_QUERY`) → pierwsza usługa odczytuje wpis i zapisuje kopię w `tmp_path`; druga usługa (restart)
  dostaje 403 z treścią z dokumentacji AniList → sprawdzenie subskrypcji daje ofertę i przekazanie do pobrania.
  Bez sieci, bez sekretów.

**Gate:** `uv run pytest tests/application tests/integration -q`.

### Faza 3 — Panel

**Pliki:** `cli/interactive/anime.py`, `cli/interactive/state.py`, `cli/interactive/state_subscriptions.py`,
`cli/interactive/state_texts.py`, ewentualnie `subscription_texts.py`; testy w `tests/cli/test_anime_episodes.py`,
`tests/cli/test_interactive_anime.py` i teście `state_subscriptions`.

1. Notki i wiersz statusu §8.6.
2. Testy `unit`: tekst notki z datą (lista, wpisy, wyniki), brak notki bez `as_of`, kolejność wiersza statusu,
   tekst odmowy D2. Istniejące asercje „Brak terminów emisji (AniList)” zostają.

**Human checkpoint (po bramkach, przed PR):**

```text
Uruchom: zamknij swój AniShift; z brancha uruchom `uv run anishift`, poczekaj na pierwszą rundę subskrypcji
         (zapełnia kopię w config/watch/catalog/).
Zrób:    awarię symuluje wpis `127.0.0.1 graphql.anilist.co` w `C:\Windows\System32\drivers\etc\hosts`
         (wymaga uprawnień administratora, po zmianie `ipconfig /flushdns`; opcjonalnie — usuń wpis po teście)
         albo poczekaj na rzeczywistą awarię. Otwórz Subskrypcje, potem Anime → wpis subskrypcji → odcinki,
         potem wyszukaj znany tytuł i tytuł, którego nigdy nie otwierałeś.
Oczekiwany rezultat: wiersz statusu Subskrypcji i notki z datą zapisu; lista odcinków z terminami;
         znany tytuł znaleziony z notką „wyniki tylko z zapisanych tytułów”; nieznany → „AniList nie odpowiada”.
Zwróć uwagę na: czytelność i długość tekstów, czy godzina jest lokalna, czy nic nie miga.
Przekaż wynik jako: krótką listę „OK / zmień tekst na …”.
```

**Gate:** akceptacja tekstów albo poprawki w tej samej fazie.

### Faza 4 — Dokumenty i PR

1. `config/README.md`: akapit o `watch/catalog/` (co zawiera, że można go usunąć bez utraty stanu).
2. Root `AGENTS.md`, „Dane runtime”: jedno zdanie o `config/watch/catalog/`.
3. `docs/ideas.md`: §5 „Cache metadanych AniList” — część „kopia na awarię” do §7 jako zrealizowana; TTL zostaje
   w §5. `docs/README.md`: wiersz workstreamu 12.
4. Pełne bramki (§10), push, PR do `main` z opisem decyzji D1–D6 i wyniku checkpointu.

## 10. Strategia dowodu

| Twierdzenie | Kontrola | Dlaczego wystarcza |
|---|---|---|
| Kopia powstaje i jest poprawna | unit `test_saved.py` na nagraniach | ten sam walidator co odpowiedź na żywo |
| Awaria nie zatrzymuje subskrypcji | integration z 403 po restarcie | przechodzi przez prawdziwy klient, kopię, usługę i ownera |
| Przy działającym AniList nic się nie zmienia | istniejące testy bez zmian + spy | liczba wywołań katalogu w istniejących testach |
| Cooldown nie woła katalogu | istniejący test + nowy z kopią | `titles.scheduled == []` |
| Panel mówi prawdę | unit tekstów + checkpoint | wygląd ocenia człowiek |
| Brak regresji H1 | `uv run pytest tests/application -k identity` + niezmienione golden | kopia ma ten sam kształt co live |

Komendy dowodu (z roota repo):

```bash
uv run pytest tests/services/catalog -q
uv run pytest tests/application/test_acquisition.py tests/application/test_subscription_owner.py -q
uv run pytest tests/integration -q
uv run pytest tests/cli -q
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest
```

Markery: nowe testy `@pytest.mark.unit` albo `@pytest.mark.integration`. Testów `network` nie dodajemy; gdyby
wykonawca uznał je za potrzebne, dostają `@pytest.mark.network` i są domyślnie pomijane (`tests/conftest.py`).
Nagrania: istniejące `tests/fixtures/search/anilist__franchise__*.json`; treść 403 przepisana z dokumentacji AniList.
Testy bez komentarzy i docstringów (hook `check_test_comments.py`).

## 11. Commity i branch

Branch: `work/catalog/01-anilist-fallback`. Jeden commit na temat, poprawki z review wchodzą do swojego commita.

1. `feat(services): save the last AniList franchise and schedule answers for each entry` — faza 1.
2. `feat(application): serve saved AniList data to subscriptions and the catalogue when AniList fails` — faza 2.
3. `feat(tui): tell when the catalogue runs on saved AniList data` — faza 3.
4. `docs(repo): describe the saved AniList data directory and close the AniList outage idea` — faza 4.

Scope'y z `scripts/hooks/check_commit_msg.py:37-61`. Bez stopek generatora w commitach i PR.

## 12. Przegląd krzyżowy

Autor implementacji nie ocenia jej sam. Po fazie 2 i po fazie 3: świeża instancja innego modelu (reguła krzyżowa z
root `AGENTS.md`) sprawdza kod względem tego planu i `specification.md`; panel — autor i jedno review.

## 13. Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Kiedy eskalować |
|---|---|---|---|
| Kopia pusta przy pierwszej awarii po wdrożeniu | log „Saved catalog used” nie występuje, odmowy jak dziś | kopia zapełnia się w pierwszej rundzie subskrypcji; opisać w PR | — |
| Przesunięcie emisji w trakcie awarii | wyszukiwanie przed emisją, brak wydań | dzisiejsze reguły H1 i ponowienia; notka pokazuje wiek danych | gdy właściciel zgłosi przegapiony odcinek → D4 |
| Konflikt z workstreamami 18/19 | konflikty merge w `acquisition.py`, `bootstrap.py` | rebase, zachować oba zestawy pól | zmiana kontraktu `read_listing` |
| Regulamin AniList | decyzja D1 | limit i brak prefetchu | D1 = nie |
| `PermissionError` na Windows przy `replace` | log zapisu | rezygnacja z zapisu, następny zapis nadpisze | powtarzalne logi w realnym użyciu |
| Stan rezydenta właściciela | — | testy w `tmp_path`; właściciel zamyka AniShift przed checkpointem | — |

## 14. Definition of Done

- [ ] W1–W13 działają i mają testy.
- [ ] Bramki przeszły; wynik komend w PR.
- [ ] Zakres i zakazy zachowane; brak zmian schematu stanu i H1.
- [ ] Checkpoint w panelu wykonany.
- [ ] Review krzyżowe zakończone.
- [ ] PR zawiera decyzje D1–D6 i znane ograniczenia.

## 15. Kontrakt wyniku wykonania

```text
status · zmienione pliki · wyniki komend z §10 · wynik checkpointu · odchylenia od planu
· odkrycia · znane ograniczenia · branch i commity · następny krok
```

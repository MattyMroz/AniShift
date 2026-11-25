---
kind: plan
status: accepted
baseline: 1f76e30 (main)
created: 2026-10-25
updated: 2026-11-26
---

# Plan: angielskie tytuły odcinków z TVmaze (issue #58)

Kontrakt wymagań: `specification.md` (decyzje D1-D7 rozstrzygnięte 2026-11-25). Dowody i kształt odpowiedzi TVmaze:
`research.md`. Plan nie ma otwartych decyzji; wykonawca zaczyna od fazy 0.

## Cel

`AcquisitionService.episodes()` zwraca listę, w której `ListedEpisode.title` daje tytuł w kolejności: angielski z
ani.zip, angielski z TVmaze, romaji z ani.zip, brak.

## Warunki końcowe

- [ ] `ListedEpisode` ma pola `title_en` i `title_romaji` oraz właściwość `title`; pola danych `title` nie ma nigdzie.
- [ ] `TvMazeCatalog` czyta tytuły po `tvdbShowId`, a `episodes()` wypełnia nimi brakujące `title_en`.
- [ ] `state.json` ma schemat 7 z kluczami `title_en` i `title_romaji`; stan właściciela przeniesiony skryptem.
- [ ] README (EN i PL) ma linię źródeł danych z linkiem do TVmaze.
- [ ] Bramki repo zielone, human checkpoint zaliczony.

## Nie-cel

Nazwy plików z tytułem odcinka należą do workstreamu 23; ten plan daje mu tylko źródło tytułu (sekcja „Source of
truth”).

## Stan aktualny i luka

- `anizip._title` skleja `en` i `x-jat` w jedno `ListedEpisode.title`, więc nikt dalej nie wie, czy tytuł jest
  angielski; D3 tego wymaga.
- Tytuły pochodzą tylko z ani.zip; w pomiarze z 2026-11-26 TVmaze ma prawdziwy angielski tytuł dla 16 wyemitowanych
  odcinków z samym romaji i 10 bez tytułu (`research.md`).
- Zapisany odcinek w `state.json` niesie klucz `title`, a `_decode_mapping` wymaga dokładnego zbioru kluczy.

### Istniejące rozwiązania do reuse

- `ArmCatalog` (`services/catalog/arm.py`) i jego testy: wzór adaptera, `USER_AGENT`, mapowanie błędów.
- `numbering_gap` (`application/episode_selection.py`): ta sama reguła niepewnej numeracji co H1.
- `_Remembered`, `_remembered`, `_memory_lock` (`application/acquisition.py`): pamięć rezydenta z LRU.
- `_bridge_failed` (`application/acquisition.py`): log awarii dostawcy bez treści.
- `parse_mapping` (`services/catalog/anizip.py`): jednorazowy skrypt migracji liczy nim oba tytuły z `raw_episodes`.
- `httpx.Client(..., follow_redirects=True)` z `bootstrap.py`: lookup 301 obsługuje klient.

## Zakres

### In scope

- Rozdzielenie języka tytułu w `ListedEpisode`, parserze ani.zip, zapisie `state.json` i wszystkich wywołaniach oraz
  testach.
- Adapter `TvMazeCatalog`, dostawca `tvmaze` w `_PROVIDERS`, czysta funkcja wypełnienia, cache i wiring.
- Jednorazowy skrypt migracji stanu właściciela (poza gitem).
- Linia źródeł danych w README, wpisy w `AGENTS.md` katalogów `services/catalog` i `application`.

### Forbidden

- Aliasy, druga ścieżka albo odczyt schematu 6; stare pole `title` znika w tym samym diffie.
- Zmiany H1: `episode_identity.py`, `episode_selection._episode_title`, `identity_target`.
- Zmiany UI w `cli/interactive/*` poza tym, co wymusza mypy (oczekiwane: żadnych, bo `title` zostaje właściwością).
- Nowa zależność, nowy `ErrorCode`, wyszukiwanie po tytule, zapis tytułów TVmaze na dysk.
- Zmiany plików w `config/` właściciela przed jego zgodą i zamknięciem rezydenta.

### Dozwolone decyzje lokalne

- Nazwy prywatnych helperów, kolejność funkcji w module, podział testów na pliki zgodny z nazwami modułów.

### Zatrzymaj się i wróć po decyzję, gdy

- odczyt TVmaze w teście `network` albo przy checkpoincie pokaże tytuł innego odcinka dla tej samej pary
  `(sezon, odcinek)` (przesunięcie numeracji);
- inny workstream podbije `WATCH_STATE_SCHEMA_VERSION` przed scaleniem tego (konflikt numeru i skryptu migracji);
- mypy pokaże konsumenta `ListedEpisode.title` jako pola danych spoza listy w mapie plików, którego nie da się przenieść
  na właściwość albo `title_en`/`title_romaji` bez zmiany zachowania.

## Kontekst do przeczytania

1. `AGENTS.md` (root), `anishift/AGENTS.md`, `anishift/services/catalog/AGENTS.md`, `anishift/application/AGENTS.md`
   (sekcje o stanie rezydenta i pobieraniu odcinków), `tests/AGENTS.md`.
2. Skille `simple`, `coding` z `references/python.md`, `comments-docstrings.md`, `testing.md`; `commit` przed commitem.
3. `services/catalog/arm.py` i `tests/services/catalog/test_arm.py`: wzór adaptera i testów.
4. `services/catalog/anizip.py` (`parse_mapping`, `_title`) i `tests/services/catalog/test_anizip.py`.
5. `application/episode_selection.py`: `ListedEpisode`, `ListedSpecial`, `AniZipMapping`, `EpisodeListing`,
   `numbering_gap`, `episode_listing`.
6. `application/acquisition.py`: `IdCatalog`, `ListingRead`, `_Remembered`, `_bridge_failed`, `AcquisitionService.__init__`,
   `episodes`, `read_listing`, `_mapping`, `_schedule`.
7. `application/watch_state.py`: `_LISTED_EPISODE_KEYS`, `_encode_mapping`, `_decode_mapping`; `application/control.py`
   `WATCH_STATE_SCHEMA_VERSION`.
8. `services/http_requests.py` `_PROVIDERS`; `bootstrap.py` `_acquisition_service`.
9. `research.md` w tym katalogu: kształt odpowiedzi TVmaze.

## Impact scan

| Kontrakt | Ryzyko | Obowiązek regresyjny |
| --- | --- | --- |
| `ListedEpisode` (IPC `encode_view`/`decode_view`, strict) | panel i rezydent muszą mieć ten sam kształt | test round-trip `EpisodeListing` przez `encode_view`/`decode_view` z oboma polami; rezydent restartowany razem z panelem |
| `state.json` (`_LISTED_EPISODE_KEYS`, wersja 6) | stary plik przestaje się wczytywać | test zapisu i odczytu schematu 7; test, że schemat 6 daje `ConfigError`; skrypt migracji na kopii, potem na stanie właściciela |
| H1 (`identity_target`, `_episode_title`) | tytuły TVmaze w kotwicach tożsamości | wypełnienie tylko na `EpisodeListing`; test, że `ListingRead.mapping` i `raw_episodes` są te same przed i po `episodes()`; golden H1 bez zmian |
| Automat (`read_listing`, `merge_listing`) | żądania TVmaze w cyklicznych kontrolach, zapis tytułów TVmaze | test: `read_listing` nie woła katalogu tytułów |
| Budżet żądań (`episode_requests`, limit `anilist`) | TVmaze liczony do budżetu AniList | `scope` liczy tylko wymienionych dostawców; test hosta `api.tvmaze.com` -> `tvmaze` |
| Odcinki specjalne (`ListedSpecial.title`) | zmiana `_title` psuje tytuły specjali | test parsera: special z samym `x-jat` ma ten tytuł, z `en` ma `en` |
| Architektura warstw | `application` importuje `services` | protokół `EpisodeTitleCatalog` w `acquisition.py` jak `IdCatalog`; `tests/application/test_architecture.py` zielony |

## Target design

### Odpowiedzialności

| Element | Odpowiada za | Nie odpowiada za |
| --- | --- | --- |
| `ListedEpisode` | przechowuje `title_en`, `title_romaji`; właściwość `title` wybiera `title_en or title_romaji` | pochodzenie tytułu |
| `anizip.parse_mapping` | dzieli `en` i `x-jat` z odrzuceniem placeholdera w nawiasach; special dostaje `en or x-jat` | TVmaze |
| `TvMazeCatalog` (`services/catalog/tvmaze.py`) | lookup, lista odcinków, filtr `regular`, odrzucenie placeholderów i dubli pary, oczyszczenie, błędy | cache, wybór serialu |
| `tvdb_show_id`, `fill_episode_titles` (`episode_selection.py`) | jedyne `tvdbShowId`; wypełnienie `title_en` według wymagań 3-6 specyfikacji | I/O |
| `AcquisitionService.episodes()` | warunek zapytania (D4), cache w `_Remembered`, obsługa awarii | zapis na dysk |

### Source of truth

- Autorytatywny tytuł odcinka: `ListedEpisode.title` w `EpisodeListing` z `AcquisitionService.episodes(anilist_id)`.
  Workstream 23 bierze tytuł stąd; nie czyta `raw_episodes`, zapisanego mapowania ani `read_listing`, bo tam nie ma
  tytułów TVmaze.
- Stan pochodny: tytuły TVmaze w `_Remembered.titles` (pamięć rezydenta, klucz `anilist_id`, wspólny LRU 64 wpisów).
- Zapis: `state.json` trzyma tylko tytuły ani.zip (`title_en`, `title_romaji`).

### Przepływ

```text
episodes(anilist_id)
-> read = read_listing(anilist_id)
-> read.movie albo brak title_source -> return read.listing
-> show = tvdb_show_id(read.mapping); None -> return read.listing
-> potrzebne = jakikolwiek odcinek: aired, title_en None, season i episode nie None,
   numbering_gap(read.mapping, number, read.tvdb_season, movie=False) is None
-> nie potrzebne -> return read.listing
-> titles = _Remembered.titles, gdy świeże (titles_at + titles_ttl_s > now),
   inaczej title_source.episode_titles(show) poza blokadą:
     sukces -> zapamiętaj z TTL 3600
     AniShiftError | OSError | ValueError -> _bridge_failed("tvmaze", error), zapamiętaj {} z TTL 900
-> return fill_episode_titles(read.listing, read.mapping, titles, read.tvdb_season)
```

### Publiczne kontrakty

```text
ListedEpisode (frozen, slots)
  number: int
  title_en: str | None = None
  title_romaji: str | None = None
  airs_at, season, episode, absolute, aired, airs_at_fallback: bez zmian
  @property title -> str | None: title_en or title_romaji
  wywołania z tytułem podają go słowem kluczowym (title_en=..., title_romaji=...)

ListedSpecial: bez zmian (title = en or x-jat)

TvMazeCatalog(http: httpx.Client, *, timeout_s: float = _TIMEOUT_S)
  episode_titles(tvdb_show_id: int) -> dict[tuple[int, int], str]
  żądania: GET {TVMAZE_URL}/lookup/shows params={"thetvdb": id} (klient podąża za 301, ciało serialu daje int "id");
           GET {TVMAZE_URL}/shows/{id}/episodes bez parametru specials
  wynik: {(season, number): name} tylko type == "regular", season i number typu int, nazwa po oczyszczeniu niepusta
         i nie placeholder; para występująca więcej niż raz jest pominięta; 404 lookupu -> {}
  błędy: TitleCatalogError(EPISODE_CATALOG_FAILED) dla transportu, statusu innego niż 200/404, ciała, które nie jest
         obiektem z int "id" albo listą odcinków
  logi: info "Episode titles read" provider="tvmaze" count=...; warning przy błędzie z provider i code

EpisodeTitleCatalog (Protocol, acquisition.py)
  episode_titles(tvdb_show_id: int) -> Mapping[tuple[int, int], str]

AcquisitionService.__init__: nowy parametr keyword-only episode_titles: EpisodeTitleCatalog | None = None

tvdb_show_id(mapping: AniZipMapping) -> int | None
  zbiór wartości "tvdbShowId" typu int > 0 z numerowanych wpisów raw_episodes; dokładnie jeden -> on, inaczej None

fill_episode_titles(listing: EpisodeListing, mapping: AniZipMapping, titles: Mapping[tuple[int, int], str],
                    tvdb_season: int | None) -> EpisodeListing
  replace(title_en=...) tylko gdy title_en is None, season i episode nie None, para w titles,
  numbering_gap(mapping, number, tvdb_season, movie=False) is None; reszta listy bez zmian
```

Stałe: `TVMAZE_URL: Final[str] = "https://api.tvmaze.com"` i `_TIMEOUT_S: Final[float] = 10.0` w adapterze;
`_PLACEHOLDER_TITLE = re.compile(r"Episode \d+", re.IGNORECASE)` z `fullmatch`; w `acquisition.py`
`_TVMAZE_CACHE_S: Final[int] = 3600` z docstringiem o `Cache-Control: max-age=3600` TVmaze; awaria używa
`_FALLBACK_CACHE_S`. Oczyszczenie nazwy: znaki kategorii Unicode `C*` zamienione na spację, potem
`" ".join(name.split())`.

Wywołanie `fill_episode_titles` nie przekazuje `movie`, bo `episodes()` kończy wcześniej dla filmu.

### Edge cases

| Przypadek | Oczekiwane zachowanie | Dowód |
| --- | --- | --- |
| Brak `tvdbShowId` albo dwa różne | brak zapytania, lista bez zmian | unit `episode_selection` i `acquisition` |
| `tvdbShowId` obok `null` | używa jedynego niepustego | unit |
| Lookup 404 | `{}`, zapamiętane 3600 s, bez logu błędu | unit adapter i service |
| 429, 500, zły JSON, ciało bez `id`, timeout | `TitleCatalogError`; lista z tytułami ani.zip; brak drugiej próby przez 900 s | unit service (zegar wstrzyknięty) |
| Placeholder `Episode 10`, pusta nazwa | brak tytułu | unit adapter |
| Wpis z `number: null` albo `type` inny niż `regular` | pominięty | unit adapter |
| Dubel pary w TVmaze | para pominięta | unit adapter |
| `title_en` z ani.zip istnieje | nie nadpisany | unit fill |
| Tylko `title_romaji` z ani.zip | `title_en` z TVmaze, `title` zwraca angielski | unit fill i property |
| Odcinek bez `season/episode` (dopełniony z liczby odcinków) | bez tytułu | unit fill |
| `numbering_gap` = `none` / `duplicate` / `tvdb_season` | bez tytułu | unit fill |
| Film | brak zapytania | unit service |
| Żaden wyemitowany odcinek nie potrzebuje tytułu | brak zapytania | unit service |
| Niewyemitowany odcinek po udanym zapytaniu | dostaje tytuł, gdy TVmaze go zna | unit fill |
| Znaki sterujące, wielokrotne spacje, antologia `A / B / C` | oczyszczone; antologia w całości | unit adapter |
| `read_listing` z automatu | zero wywołań katalogu tytułów | unit service |
| Brak wstrzykniętego katalogu | zachowanie jak przed zmianą | unit service |

## Mapa plików

| Ścieżka | Operacja | Rola |
| --- | --- | --- |
| `anishift/application/episode_selection.py` | MODIFY | `ListedEpisode.title_en`/`title_romaji`/`title`; `tvdb_show_id`, `fill_episode_titles` |
| `anishift/services/catalog/anizip.py` | MODIFY | `_title` zastąpione funkcją zwracającą parę `(en, romaji)`; special bierze `en or romaji` |
| `anishift/application/watch_state.py` | MODIFY | `_LISTED_EPISODE_KEYS`, `_encode_mapping`, `_decode_mapping` na `title_en`/`title_romaji` |
| `anishift/application/control.py` | MODIFY | `WATCH_STATE_SCHEMA_VERSION = 7` |
| `anishift/services/catalog/tvmaze.py` | CREATE | adapter wzorowany na `arm.py` |
| `anishift/services/catalog/__init__.py` | MODIFY | eksport `TvMazeCatalog` |
| `anishift/services/http_requests.py` | MODIFY | `"api.tvmaze.com": "tvmaze"` w `_PROVIDERS` |
| `anishift/application/acquisition.py` | MODIFY | `EpisodeTitleCatalog`, parametr `episode_titles`, pola `_Remembered.titles`, `titles_at`, `titles_ttl_s`, `episodes()` |
| `anishift/bootstrap.py` | MODIFY | `episode_titles=TvMazeCatalog(http)` w `_acquisition_service` |
| `anishift/services/catalog/AGENTS.md` | MODIFY | plik `tvmaze.py` i inwarianty: 404 = `{}`, placeholder, brak zapisu |
| `anishift/application/AGENTS.md` | MODIFY | jedno zdanie w „Pobieranie odcinków”: tytuł odcinka to `ListedEpisode.title` z `episodes()`, TVmaze tylko tam |
| `README.md`, `README.pl.md` | MODIFY | sekcja z jedną linią źródeł danych (faza 4) |
| `tests/services/catalog/test_tvmaze.py` | CREATE | adapter, `unit` i jeden `network` |
| `tests/fixtures/search/tvmaze__episodes__92844.json`, `tests/fixtures/search/manifest.json` | CREATE / MODIFY | przycięte nagranie Overgeared i wpis `tvmaze` w manifeście |
| `tests/services/catalog/test_anizip.py` | MODIFY | asercje na `title_en`/`title_romaji`, special |
| `tests/application/test_episode_selection.py` | MODIFY | nowe pola, `tvdb_show_id`, `fill_episode_titles` |
| `tests/application/test_acquisition.py` | MODIFY | `episodes()`: wypełnienie, cache, awaria, brak żądań w `read_listing` |
| `tests/application/test_watch_state.py` | MODIFY | schemat 7 i odrzucenie schematu 6 |
| `tests/services/test_http_requests.py` | MODIFY | host -> `tvmaze` |
| `tests/cli/test_anime_episodes.py`, `tests/cli/test_interactive_anime.py` | MODIFY | tytuły słowem kluczowym `title_en=` |
| `tests/config/test_bootstrap.py`, `tests/application/test_automation.py`, `tests/cli/test_resident.py` | MODIFY tylko gdy padną | dopuszczenie hosta albo brak katalogu tytułów |
| `scripts/tmp/migrate_episode_titles.py` | CREATE, poza gitem | jednorazowa migracja stanu właściciela, usunięta po użyciu |

READ ONLY: `episode_identity.py`, `subscription_targets.py`, `cli/interactive/*`.

## Plan wykonania

Gałąź `feat/tvmaze-episode-titles` w `.worktrees/tvmaze-episode-titles`. Commity według tematu, każdy według skilla
`commit`, scope z listy `--scopes`. Autor kodu i recenzent z różnych modeli (reguła krzyżowa `AGENTS.md`).

### Faza 0: preflight

1. `git status --short`, `git log --oneline -1` (oczekiwane: czysto, gałąź na `origin/main` albo nowszym).
2. Raz `uv sync` w tym worktree, potem tylko `uv run --no-sync`; nigdy `--active`.
3. Baseline: `uv run --no-sync pytest -n 6 tests/services/catalog tests/application/test_episode_selection.py
   tests/application/test_acquisition.py tests/application/test_watch_state.py tests/cli/test_anime_episodes.py`.
   Zapisz znane failures przed zmianą.
4. `git grep -n "WATCH_STATE_SCHEMA_VERSION: Final\[int\]" origin/main`: gdy nie 6, warunek stopu.

**Gate:** baseline zapisany, schemat 6 na `main`.

### Faza 1: język tytułu w kontrakcie (commit 1)

1. `ListedEpisode`: zamień pole `title` na `title_en` i `title_romaji`, dodaj właściwość `title` z jednolinijkowym
   docstringiem kontraktu.
2. `anizip.py`: funkcja zwraca `(en, romaji)` z tą samą regułą placeholdera w nawiasach; odcinek dostaje oba pola,
   special `en or romaji`.
3. `watch_state.py`: klucze `title_en`, `title_romaji` zamiast `title` w `_LISTED_EPISODE_KEYS`, kodowaniu i
   dekodowaniu; `control.py`: `WATCH_STATE_SCHEMA_VERSION = 7`.
4. Wszystkie konstruktory i asercje w testach przechodzą na `title_en=`/`title_romaji=` albo `.title`; mypy wskazuje
   pozostałe.
5. Testy: parser (odcinek z `en`, z samym `x-jat`, z `[Placeholder]`; special), `title` jako właściwość, round-trip IPC
   `EpisodeListing`, schemat 7 zapis i odczyt, schemat 6 -> `ConfigError`.

**Inwarianty:** H1 i jego golden bez zmian; UI bez zmian w kodzie.

**Kontrola:** bramki repo (niżej).

**Commit:** `refactor(repo): keep the language of episode titles` (scope `repo`, bo zmiana obejmuje `application` i
`services`; zachowanie widoczne bez zmian).

### Faza 2: adapter TVmaze (commit 2)

1. `tvmaze.py` według kontraktu; `_PROVIDERS`; eksport w `__init__.py`; wpis w `services/catalog/AGENTS.md`.
2. Nagranie: z odpowiedzi `GET https://api.tvmaze.com/shows/92844/episodes` zostaw w każdym wpisie tylko `id`, `name`,
   `season`, `number`, `type`; zapisz jako `tests/fixtures/search/tvmaze__episodes__92844.json`; w `manifest.json` klucz
   `tvmaze` z wpisem `{"file", "show_id": 92844, "thetvdb": 478752, "recorded_at", "trimmed": true,
   "source": "https://api.tvmaze.com", "license": "CC BY-SA"}`. Lookup w testach jako `httpx.Response(301,
   headers={"Location": "https://api.tvmaze.com/shows/92844"})` i ciało serialu `{"id": 92844, ...}` z kształtu w
   `research.md`.
3. Testy `unit` w `test_tvmaze.py` (pozycje adaptera z tabeli edge cases, `User-Agent`, brak parametru `specials`) i
   test `network`: TVDB 478752 -> `(1, 1) == "Legendary Class"`.
4. Test hosta w `tests/services/test_http_requests.py`.

**Commit:** `feat(services): read episode titles from TVmaze`.

### Faza 3: wypełnienie i cache (commit 3)

1. `episode_selection.py`: `tvdb_show_id`, `fill_episode_titles` (reuse `numbering_gap`).
2. `acquisition.py`: protokół, parametr, pola `_Remembered`, `episodes()` według przepływu; żądanie poza `_memory_lock`.
3. `bootstrap.py`: `episode_titles=TvMazeCatalog(http)`.
4. `application/AGENTS.md`: zdanie o źródle tytułu odcinka.
5. Testy z fałszywym katalogiem tytułów i wstrzykniętym zegarem: wypełnienie romaji i braków, brak nadpisania
   angielskiego, drugi odczyt z pamięci, awaria bez drugiej próby przez 900 s i ponowienie po 900 s, 404 bez ponowienia
   przez 3600 s, film, brak potrzeby zapytania, `read_listing` bez wywołań, `ListingRead.mapping` niezmienione.

**Commit:** `feat(repo): fill missing English episode titles from TVmaze` (scope `repo`, bo zmiana obejmuje
`application` i `bootstrap.py`).

### Faza 4: atrybucja (commit 4)

1. `README.md`, przed `## Documentation`:

   ```markdown
   ## Data sources

   Episode titles also come from [TVmaze](https://www.tvmaze.com) (CC BY-SA).
   ```

2. `README.pl.md`, przed `## Dokumentacja`:

   ```markdown
   ## Źródła danych

   Tytuły odcinków pochodzą też z [TVmaze](https://www.tvmaze.com) (CC BY-SA).
   ```

**Commit:** `docs(repo): credit TVmaze for episode titles`.

### Faza 5: migracja stanu właściciela i human checkpoint

1. `scripts/tmp/migrate_episode_titles.py` (gitignorowany, uruchamiany w worktree gałęzi:
   `uv run --no-sync python scripts/tmp/migrate_episode_titles.py <ścieżka state.json>`): czyta podany plik; przerywa, gdy
   `schema_version != 6`; dla `subscriptions[*].mapping` i `removed_subscription.mapping` (gdy nie `null`) każdemu
   wpisowi `episodes` usuwa `title` i ustawia `title_en`, `title_romaji` z
   `parse_mapping({"episodes": {klucz: raw_episodes[klucz]}, "mappings": {}})` dla `klucz = str(number)` (brak wpisu w
   `raw_episodes` -> oba `None`); ustawia `schema_version: 7`; zapis przez plik tymczasowy obok i `os.replace`, kopia
   oryginału jako `state.json.v6`.
2. Próba na kopii stanu w katalogu tymczasowym: `WatchStateStore(<kopia>/state.json).load()` z kodu gałęzi bez błędu,
   liczba subskrypcji i odcinków równa przed i po.
3. Właściciel zamyka rezydenta; skrypt na jego `config/watch/state.json`; wczytanie przez rezydenta z gałęzi.
4. Checkpoint:

   ```text
   Uruchom: uv run --no-sync anishift w worktree gałęzi (stary rezydent zamknięty)
   Zrób: Anime -> "Overgeared" -> Enter; potem "Even the Student Council Has Its Holes" -> Enter; potem szkic subskrypcji
   Oczekiwany rezultat: Overgeared E8 "Yatan's High Priest" zamiast romaji; Student Council E1-E8 z tytułami;
     odcinki z angielskim tytułem ani.zip jak dotąd; reszta braków "Odcinek N"
   Zwróć uwagę na: długie tytuły antologii w szerokości tabeli; lista bez sieci otwiera się bez błędu
   Przekaż wynik jako: krótka notatka, co się wyświetliło
   ```

5. Po zaliczeniu: usuń skrypt i `state.json.v6` dopiero po zgodzie właściciela.

**Gate:** właściciel potwierdza wynik; bez tego nie ma pushu ani PR.

## Strategia dowodu

Testy bez opisowej prozy (hook `no-test-prose`); scenariusz w nazwie testu; `pytestmark = pytest.mark.unit` jak w
`test_arm.py`; atrapy TVmaze tylko z polami z `research.md`.

| Twierdzenie | Kontrola |
| --- | --- |
| Kolejność tytułu i rozdzielenie języka | unit parser, property, fill |
| Adapter: lookup 301, filtr, placeholder, dubel pary, oczyszczenie, antologia, 404, błędy | unit na nagraniu i atrapach z `httpx.MockTransport` |
| Cache 3600 s, awaria 900 s, D4, film, `read_listing` bez TVmaze | unit service z fałszywym katalogiem i zegarem |
| Zapis `state.json` schemat 7, odrzucenie 6 | unit `test_watch_state.py` |
| IPC z nowym kształtem | unit round-trip `encode_view`/`decode_view` |
| H1 bez zmian | istniejące testy tożsamości i golden zielone |
| Prawdziwy TVmaze | `network`, domyślnie pomijany: `uv run --no-sync pytest -m network tests/services/catalog/test_tvmaze.py` |
| Wygląd w panelu | human checkpoint |

### Bramki repo (z korzenia worktree, przed każdym commitem)

```bash
uv run --no-sync ruff check anishift/ tests/
uv run --no-sync ruff format --check anishift/ tests/
uv run --no-sync mypy anishift/ tests/
uv run --no-sync pytest -n 6
```

Pre-push uruchamia dodatkowo mypy `--platform linux` i `anishift setup`.

## Ryzyka

| Ryzyko | Rozpoznanie | Reakcja |
| --- | --- | --- |
| Zły serial albo przesunięcie numeracji | w checkpoincie tytuł nie pasuje do odcinka | stop; nie rozluźniać reguł (D2) |
| Wolny TVmaze opóźnia otwarcie listy | czas `episodes()` przy pierwszym otwarciu | timeout 10 s, pamięć awarii 900 s |
| Konflikt numeru schematu z innym workstreamem | `WATCH_STATE_SCHEMA_VERSION` na `main` inny niż 6 przed scaleniem | stop, uzgodnić kolejność i jeden skrypt |
| Utrata stanu właściciela przy migracji | `load()` po skrypcie daje błąd | przywrócić `state.json.v6`, poprawić skrypt na kopii |
| Treść CC BY-SA w repo | nagranie w git | tylko 5 pól odcinka jednego serialu, adnotacja w manifeście (D6) |

## Definition of Done

- [ ] wymagania 1-10 i inwarianty specyfikacji pokryte testami; `network` pomijany domyślnie
- [ ] bramki repo zielone, hooki bez `--no-verify`
- [ ] przegląd innego modelu bez ustaleń blokujących
- [ ] stan właściciela w schemacie 7, skrypt usunięty
- [ ] human checkpoint zaliczony

## Kontrakt wyniku wykonania

```text
status; commity (SHA, nagłówek); wyniki bramek (komenda, liczby); wynik testu network;
wynik migracji (liczba subskrypcji i odcinków przed i po); odchylenia od planu; wynik checkpointu; następny krok
```

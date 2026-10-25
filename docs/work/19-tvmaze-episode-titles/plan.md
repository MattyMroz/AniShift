---
kind: plan
status: draft
baseline: 4365a51 (main)
created: 2026-10-25
---

# Plan: brakujące tytuły odcinków z TVmaze (issue #58)

Kontrakt wymagań: `specification.md`. Dowody: `research.md`. Plan wykonuje się dopiero po akceptacji decyzji D1-D7 przez właściciela.

## Cel

`AcquisitionService.episodes()` zwraca listę, w której odcinki bez tytułu dostają tytuł z TVmaze według wymagań 1-12 specyfikacji.

## Stan aktualny i luka

- Tytuły pochodzą tylko z ani.zip (`anizip.py` `_title`); luka to odcinki wyemitowane, które ani.zip jeszcze nie opisał (`research.md`: 6 z 93 braków dziś).
- Jedyny punkt wspólny dla UI to `AcquisitionService.episodes()` (`acquisition.py:876`), a `ListingRead` niesie już `mapping`, `tvdb_season` i `movie`.

## Zakres

### In scope

- Adapter `TvMazeCatalog` w `services/catalog/`.
- Czysta funkcja wyboru serialu i wypełnienia tytułów w `application/episode_selection.py`.
- Protokół, cache i wywołanie w `AcquisitionService.episodes()`; wiring w `bootstrap.py`.
- Wpis dostawcy `tvmaze` w `http_requests._PROVIDERS`.
- Testy, nagrane odpowiedzi, wpisy w AGENTS.md katalogu `services/catalog`, atrybucja w README (jeśli D5 tak).

### Out of scope / Forbidden

- Zmiany w `anizip.py`/`parse_mapping`, `raw_episodes`, `watch_state.py`, `subscription_targets.py`, H1 (`episode_identity.py`).
- Zmiany UI (`cli/interactive/*`): `episode.title or "Odcinek N"` pozostaje bez zmian.
- Nowy `ErrorCode`, nowa zależność (`uv add`), ręczna edycja `pyproject.toml`, wyszukiwanie po tytule.
- Zapis tytułów TVmaze do `config/` lub `workspace/`.
- Dotykanie rezydenta właściciela: testy działają na `httpx.MockTransport`, nie na jego stanie. Przed uruchomieniem zmian w żywym rezydencie właściciel zamyka AniShift (pamięć: rezydent czyta pliki z checkoutu).

### Zatrzymaj się i wróć po decyzję, gdy

- w testach na realnych nagraniach join po `(sezon, odcinek)` da sparowanie sprzeczne z ani.zip dla odcinka, który ma tytuł w obu źródłach (przesunięcie numeracji);
- okaże się, że `episodes()` jest wołane z kontekstu automatu (budżet żądań `anilist`) i nowy dostawca łamie budżet;
- właściciel zmieni D2 lub D3 (zmienia kontrakt `ListedEpisode`).

## Kontekst do przeczytania

| Kolejność | Źródło | Po co |
| --- | --- | --- |
| 1 | `AGENTS.md` (root), `anishift/AGENTS.md`, `anishift/services/catalog/AGENTS.md`, `anishift/application/AGENTS.md`, `tests/AGENTS.md` | reguły, markery, zakaz opisowej prozy w testach |
| 2 | `.agents/skills/simple`, `.agents/skills/coding/references/python.md`, `comments-docstrings.md`, `testing.md` | standard kodu |
| 3 | `services/catalog/arm.py` + `tests/services/catalog/test_arm.py` | wzorzec adaptera i testów |
| 4 | `application/acquisition.py` 242-250 (`IdCatalog`), 493-503 (`_Remembered`), 611-660 (`__init__`), 876-952 (`episodes`, `read_listing`), 1250-1285 | miejsce zmiany i cache |
| 5 | `application/episode_selection.py` 267-315, 480-502, 505-554 | `ListedEpisode`, `numbering_gap`, `episode_listing` |
| 6 | `services/http_requests.py` 46-58, 285 | tabela dostawców |
| 7 | `bootstrap.py` 90-145 | wiring |
| 8 | `docs/work/19-tvmaze-episode-titles/research.md` | próbki odpowiedzi |

## Impact scan

| Kontrakt | Ryzyko | Obowiązek regresyjny |
| --- | --- | --- |
| `raw_episodes`, H1 (`identity_target`) | tytuły TVmaze mogłyby zmienić anchory tytułów odcinków | wypełnienie tylko na `EpisodeListing.episodes`; test: `raw_episodes` i `listing` mapowania niezmienione |
| `state.json` (`merge_listing` zapisuje `read.mapping`) | trwałe zapisanie tytułów TVmaze | `episodes()` wypełnia kopię listy po `read_listing`; `ListingRead.mapping` nietknięte; test na `read_listing` bez żądań TVmaze |
| Budżet żądań (`episode_requests`, limit `anilist`) | `tvmaze` bez limitu w `scope` | `scope` liczy tylko wymienionych dostawców; test, że dodatkowe żądanie nie podnosi liczników anilist |
| Cooldown po 429 | wspólny dla dostawcy | wpis `api.tvmaze.com` -> `tvmaze` w `_PROVIDERS`; test na mapowanie hosta |
| IPC (`encode_view(EpisodeListing)`) | brak nowych pól | żadnych zmian w typie `ListedEpisode` |
| Architektura warstw | `application` nie importuje `services` bezpośrednio poza protokołami | protokół `EpisodeTitleCatalog` w `acquisition.py` jak `IdCatalog`; `tests/application/test_architecture.py` zielony |

## Target design

### Odpowiedzialności

| Element | Odpowiada za | Owner stanu |
| --- | --- | --- |
| `TvMazeCatalog` (`services/catalog/tvmaze.py`) | lookup 301, lista odcinków, filtr `regular`, odrzucenie placeholderów, oczyszczenie tytułu, mapowanie błędów | brak (klient HTTP wstrzykiwany) |
| `tvdb_show_id(mapping)` i `fill_episode_titles(...)` (`episode_selection.py`) | wybór jedynego `tvdbShowId`, reguły niepewności, wypełnienie tylko brakujących tytułów | brak (czyste funkcje) |
| `AcquisitionService.episodes()` | warunek wywołania, cache, obsługa błędu | `_Remembered` (pamięć rezydenta) |
| `bootstrap._acquisition_service` | złożenie zależności | brak |

### Source of truth

- Tytuł ani.zip: `ListedEpisode.title` z `mapping.episodes`; TVmaze tylko uzupełnia na wyjściu `episodes()`.
- Cache tytułów TVmaze: pola `_Remembered.titles` i `_Remembered.titles_until` (klucz: `anilist_id`, wspólny LRU 64 wpisów i `_memory_lock`).

### Przepływ

```text
episodes(anilist_id)
-> read = read_listing(anilist_id)
-> show = tvdb_show_id(read.mapping)           ; brak lub niejednoznaczny -> return read.listing
-> brak aired-episode bez tytułu z numbering_gap None -> return read.listing
-> titles = pamięć (świeża?) lub TvMazeCatalog.episode_titles(show)   ; błąd -> log, cache 900 s, return read.listing
-> fill_episode_titles(read.listing, read.mapping, titles, read.tvdb_season, movie=read.movie)
```

### Publiczne kontrakty

```text
TvMazeCatalog.episode_titles(tvdb_show_id: int) -> dict[tuple[int, int], str]
  wejście: ID serialu TheTVDB
  wyjście: {(season, number): name} tylko regular, bez placeholderów; 404 lookupu -> {}
  błędy: TitleCatalogError(EPISODE_CATALOG_FAILED) dla transportu, statusu != 200/404, złej treści
  efekty: 2 żądania GET (lookup z follow_redirects klienta, potem episodes?specials=1)

EpisodeTitleCatalog (Protocol, acquisition.py)
  episode_titles(tvdb_show_id: int) -> Mapping[tuple[int, int], str]

tvdb_show_id(mapping: AniZipMapping) -> int | None
fill_episode_titles(listing, mapping, titles, tvdb_season, *, movie: bool) -> EpisodeListing
  wypełnia tylko episode.title is None; klucz (episode.season, episode.episode) w titles;
  wymaga numbering_gap(mapping, episode.number, tvdb_season, movie=movie) is None
```

Stałe: `TVMAZE_URL = "https://api.tvmaze.com"` w adapterze; `_TIMEOUT_S = 10.0`; w `acquisition.py` `_TVMAZE_CACHE_S = 3600` ("odpowiada `Cache-Control: max-age=3600` TVmaze, zmierzone 2026-10-25"), błąd cache'owany `_FALLBACK_CACHE_S` (900). Placeholder: `re.compile(r"Episode \d+", re.I)` z `fullmatch`.

### Edge cases

| Przypadek | Oczekiwane zachowanie | Dowód |
| --- | --- | --- |
| Brak `tvdbShowId` / dwa różne | bez żądania, lista bez zmian | unit `episode_selection` |
| `tvdbShowId` obok wpisów `null` (Nia Liston) | używa jedynego niepustego | unit |
| Lookup 404 | `{}` , cache 3600 s, bez błędu | unit adapter + service |
| 429 / 500 / zła treść / timeout | `TitleCatalogError`, lista bez zmian, cache błędu 900 s | unit service |
| Placeholder `Episode 6` | brak tytułu | unit adapter |
| Tytuł ani.zip istnieje | nie nadpisany | unit fill |
| Odcinek bez `season/episode` (dopełniony z liczby odcinków) | bez tytułu | unit fill |
| `numbering_gap` = `duplicate` / `tvdb_season` / `none` | bez tytułu | unit fill |
| Film | bez żądania | unit service |
| Tytuł z kontrolnymi / wielokrotnymi spacjami | oczyszczony | unit adapter |
| Tytuł antologii `A / B / C` | zachowany w całości | unit adapter |
| Brak wstrzykniętego katalogu | zachowanie jak dziś | istniejące testy bez zmian |
| `read_listing` (automat) | zero żądań TVmaze | unit service (licznik MockTransport) |

## Mapa plików

| Ścieżka | Operacja | Rola |
| --- | --- | --- |
| `anishift/services/catalog/tvmaze.py` | CREATE | adapter, wzorowany na `arm.py` |
| `anishift/services/catalog/__init__.py` | MODIFY | eksport `TvMazeCatalog` |
| `anishift/services/catalog/AGENTS.md` | MODIFY | wpis pliku i inwariantów (placeholder, 404, brak zapisu) |
| `anishift/services/http_requests.py` | MODIFY | `"api.tvmaze.com": "tvmaze"` w `_PROVIDERS` |
| `anishift/application/episode_selection.py` | MODIFY | `tvdb_show_id`, `fill_episode_titles` |
| `anishift/application/acquisition.py` | MODIFY | protokół, parametr konstruktora, pola `_Remembered`, `episodes()` |
| `anishift/bootstrap.py` | MODIFY | `title_source=TvMazeCatalog(http)` |
| `tests/services/catalog/test_tvmaze.py` | CREATE | adapter, `unit` + jeden `network` |
| `tests/application/test_episode_selection.py` | MODIFY | funkcje czyste |
| `tests/application/test_acquisition.py` | MODIFY | cache, błąd, brak żądań w `read_listing` |
| `tests/services/test_http_requests.py` | MODIFY | host -> dostawca `tvmaze` |
| `tests/config/test_bootstrap.py`, `tests/application/test_automation.py` (asercja zbioru hostów w `MockTransport`, ok. linia 444), `tests/cli/test_anime_episodes.py` | MODIFY tylko jeśli wiring lub `episodes()` zaczyna w nich wołać `api.tvmaze.com` | dopuścić host lub wstrzyknąć brak katalogu; sprawdzić uruchomieniem |
| `tests/fixtures/search/tvmaze__lookup__<id>.json`, `tvmaze__episodes__<id>.json` i wpis w `manifest.json` | CREATE/MODIFY | nagrane wycinki |
| `README.md` | MODIFY (jeśli D5) | linia "Data sources" z linkiem do TVmaze (EN i PL) |

READ ONLY: `anizip.py`, `watch_state.py`, `subscription_targets.py`, `episode_identity.py`, `cli/interactive/*`.

## Plan wykonania

Branch: `work/services/01-tvmaze-episode-titles` (wzór `work/<obszar>/<nn>-<opis>`; numer potwierdzić wobec istniejących gałęzi w obszarze `services`). Wykonawca i recenzent z różnych rodzin modeli (reguła krzyżowa AGENTS.md).

### Faza 0: preflight

1. `git switch -c work/services/01-tvmaze-episode-titles` z aktualnego `main`.
2. `uv run pytest tests/services/catalog tests/application/test_acquisition.py tests/application/test_episode_selection.py -q` (baseline zielony przed zmianą).
3. Potwierdzić D1-D7 z właścicielem.

### Faza 1: adapter i dostawca HTTP (commit 1)

1. `tvmaze.py`: `TvMazeCatalog(http, *, timeout_s)`, `episode_titles`. Lookup `GET {TVMAZE_URL}/lookup/shows` z `params={"thetvdb": id}`; klient musi podążać za 301 (`follow_redirects=True` w bootstrap; test na `MockTransport` z 301 + 200). Status 404 -> `{}`. Potem `GET {TVMAZE_URL}/shows/{id}/episodes` z `params={"specials": 1}` (id z `response.url`, nie z konstrukcji ręcznej). Parsowanie: lista obiektów; pomijaj wpisy bez `season`/`number` typu `int` lub nie-`regular` lub z nazwą pustą/placeholderem; nazwa oczyszczona (`" ".join(name.split())`, bez znaków sterujących). Złe ciało -> `TitleCatalogError`.
2. Logi: `logger.info("Episode titles read", provider="tvmaze", count=...)`; `logger.warning("Episode titles failed", provider="tvmaze", code=...)`; bez treści odpowiedzi.
3. `_PROVIDERS` + eksport w `__init__.py` + AGENTS.md katalogu.
4. Testy adaptera (poniżej). Commit: `feat(services): read episode titles from TVmaze`.

### Faza 2: wypełnienie i cache (commit 2)

1. `episode_selection.py`: `tvdb_show_id` (zbiór dodatnich `int` z `tvdbShowId`; dokładnie jeden) i `fill_episode_titles` (reuse `numbering_gap`).
2. `acquisition.py`: protokół `EpisodeTitleCatalog`, parametr `title_source: EpisodeTitleCatalog | None = None`, pola `_Remembered.titles: Mapping[tuple[int, int], str] | None` i `titles_until: float`, `episodes()` według przepływu; łapie `(AniShiftError, OSError, ValueError)` jak sąsiednie wywołania mostów (`_bridge_failed`-podobny log z `provider="tvmaze"`); wywołanie pod `with self._memory_lock` tylko dla odczytu/zapisu cache, nie w trakcie żądania.
3. `bootstrap.py`: `title_source=TvMazeCatalog(http)`.
4. Testy aplikacji. Commit: `feat(application): fill missing episode titles from TVmaze`.

### Faza 3: dokumentacja i atrybucja (commit 3, jeśli D5 tak)

1. `README.md`: linia źródeł danych z linkiem. Commit: `docs(repo): credit TVmaze for episode titles`.

## Strategia dowodu

Wszystkie testy bez opisowych komentarzy i docstringów (`check_test_comments.py`); opis scenariusza w nazwie testu; `pytestmark = pytest.mark.unit` jak w `test_arm.py`.

| Twierdzenie | Kontrola |
| --- | --- |
| Adapter: lookup 301 -> lista, filtr `regular`, placeholder, oczyszczenie, antologia | `unit`, `httpx.MockTransport` na wycinkach z `tests/fixtures/search/tvmaze__*.json` |
| Adapter: 404 -> `{}`; 429/500/zły JSON/zła treść -> `TitleCatalogError` z `EPISODE_CATALOG_FAILED` | `unit`, parametryzacja jak w `test_arm.py` |
| Adapter: `User-Agent` = `USER_AGENT` | `unit` |
| `tvdb_show_id`: jedno / brak / dwa / obok `null` | `unit` |
| `fill_episode_titles`: nie nadpisuje, wymaga pary, `duplicate`/`tvdb_season`/film | `unit` |
| `episodes()`: wypełnia z fałszywego katalogu; drugi odczyt z cache bez żądania; błąd -> lista bez zmian i bez drugiej próby w 900 s; `read_listing` nie woła katalogu; `ListingRead.mapping.raw_episodes` niezmienione | `unit` z `fakes.py` |
| Host `api.tvmaze.com` -> dostawca `tvmaze` | `unit` |
| Realny TVmaze (lookup 440056 -> 93848, jakiś odcinek 1 ma niepusty tytuł) | `network`, domyślnie pomijany (`-m network`) |
| Cały UI nie zmienia się | przegląd: `git diff --stat` nie dotyka `cli/interactive/*` |

### Nagrane odpowiedzi

Wycinki z `research.md` zapisane w `tests/fixtures/search/` według konwencji `tvmaze__lookup__<tvdb>.json` (nagłówek `Location` i status) oraz `tvmaze__episodes__<show>.json` (kilka odcinków: 3 z tytułem, 2 placeholdery, 1 antologia), z wpisem w `manifest.json` (`recorded_at: 2026-10-25`, `trimmed: true`, źródło: TVmaze, licencja CC BY-SA). Bez sekretów: zapytania nie niosą klucza ani nagłówków poza `User-Agent`. Nagrane pole `externals`/`url` zostają, reszta (obrazki, opisy, `_links` poza wymaganymi) jest usuwana.

### Bramki repo (z roota, przed każdym commitem)

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

Pre-push: mypy dla bieżącej platformy i `--platform linux`, pytest (hook). Commity w formacie `typ(scope): opis` ze scope z `scripts/hooks/check_commit_msg.py` (`services`, `application`, `repo` są na liście), bez śladów AI; commity według tematu, nie według rund review.

## Human checkpoint

Po fazie 2 (przy zamkniętym rezydencie właściciela):

```text
Uruchom: uv run anishift (panel), Anime -> wyszukaj "Magical Explorer" lub "Even the Student Council Has Its Holes" -> Enter na wpisie
Zrób: otwórz listę odcinków, potem szkic subskrypcji
Oczekiwany rezultat: odcinki z tytułem TVmaze zamiast "Odcinek N" (Magical Explorer E5, Student Council E1-E4); reszta bez zmian
Zwróć uwagę na: długi tytuł antologii w szerokości tabeli, brak błędu przy wyłączonej sieci
Przekaż wynik jako: krótka notatka co się wyświetliło
```

## Ryzyka

| Ryzyko | Rozpoznanie | Reakcja |
| --- | --- | --- |
| Zły serial lub przesunięcie numeracji | w teście realnym różni się tytuł odcinka z obu źródeł dla tej samej pary | zatrzymać, nie rozluźniać reguł; D2/D3 |
| Wolny TVmaze blokuje otwarcie listy | czas `episodes()` | timeout 10 s, cache błędu 900 s, wyłączenie przez brak wstrzyknięcia |
| Treść CC BY-SA w repo | fixtures w git | minimalne wycinki, adnotacja w manifeście (D6) |
| Opóźnienie ani.zip zniknie i zysk spadnie do zera | przyszłe pomiary | kod jest mały i odwracalny; nic nie zapisuje się trwale |

## Definition of Done

- [ ] D1-D7 rozstrzygnięte przez właściciela
- [ ] wymagania 1-12 specyfikacji pokryte testami, `network` pomijany domyślnie
- [ ] `raw_episodes`, `state.json`, H1 niezmienione (test)
- [ ] bramki repo zielone, hooki bez `--no-verify`
- [ ] przegląd innego modelu bez ustaleń blokujących
- [ ] human checkpoint wykonany
- [ ] raport wykonania: status, commity, dowody, odchylenia

## Kontrakt wyniku wykonania

```text
status; zmienione pliki; wyniki bramek (komenda, wynik, liczby); wynik testu network (jeśli uruchomiony);
odchylenia od planu; decyzje D1-D7 w brzmieniu finalnym; stan repo i commity; rekomendowany następny krok
```

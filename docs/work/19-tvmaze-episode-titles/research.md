---
kind: research
status: final
baseline: 1f76e30 (main)
checked: 2026-11-26
---

# Research: tytuły odcinków z TVmaze (issue #58)

## Odpowiedź

TVmaze uzupełnia tytuły odcinków bez klucza i bez ryzyka złej numeracji. Dla wszystkich 23 subskrypcji z
`config/watch/state.json` mapowanie, którego używa aplikacja (ani.zip po AniList, a przy pustym wyniku ani.zip po AniDB),
ma dokładnie jedno `tvdbShowId`, a lookup TVmaze po nim trafia w 23 na 23. Łączenie po parze `(sezon, odcinek)` nie
pokazało żadnego przesunięcia: 169 odcinków ma angielski tytuł w obu źródłach i wszystkie różnice to pisownia.

Zysk po decyzji D3 (angielski TVmaze także zamiast romaji) dla 194 wyemitowanych odcinków:

- 168 ma angielski tytuł z ani.zip i zostaje bez zmian;
- 16 ma w ani.zip tylko romaji (`x-jat`), a TVmaze ma dla każdego prawdziwy angielski tytuł;
- 10 nie ma w ani.zip żadnego tytułu, a TVmaze ma dla każdego prawdziwy tytuł.

## Zakres i stan na dzień

- Pytanie: jak pokazać angielski tytuł odcinka z TVmaze tam, gdzie ani.zip go nie ma, także zamiast romaji.
- Stan na 2026-11-26, TVmaze API bez klucza, AniShift `main` @ `1f76e30`.
- Poza zakresem: zapas na wypadek awarii AniList (workstream 12) i nazwy plików (workstream 23, który użyje wyniku).

## Ustalenia: stan dziś w kodzie

| Pytanie | Odpowiedź | Gdzie |
| --- | --- | --- |
| Skąd tytuł odcinka | tylko ani.zip: `_title` zwraca `en`, a gdy brak, `x-jat`; cały napis w nawiasach kwadratowych (`[Kyouteki]`) to placeholder i odpada | `anishift/services/catalog/anizip.py` `_title`, `_PLACEHOLDER_TITLE`, `parse_mapping` |
| Język tytułu | `ListedEpisode.title: str \| None` nie mówi, czy to angielski, czy romaji; tę samą funkcję `_title` używają odcinki specjalne (`ListedSpecial.title`) | `application/episode_selection.py` `ListedEpisode`, `ListedSpecial` |
| AniList | kod nie czyta tytułów odcinków z AniList (brak `streamingEpisodes` w `anishift/`); AniList daje terminarz i liczbę odcinków | `episode_selection.episode_listing`, `acquisition.read_listing` |
| Złączenie listy | `episode_listing` łączy `mapping.episodes` z terminarzem AniList; numery bez wpisu ani.zip dostają `ListedEpisode(number)` bez tytułu i bez `season/episode` | `episode_selection.episode_listing` |
| Mapowanie po AniDB | gdy ani.zip po AniList nie zna odcinków, `_anidb_numbering` bierze mapowanie po AniDB z arm-server; `ListingRead.mapping` to mapowanie po tej zamianie | `acquisition.read_listing`, `_anidb_numbering` |
| Pewność numeracji | `numbering_gap` zwraca `none`, `duplicate` albo `tvdb_season`, gdy para `(seasonNumber, episodeNumber)` jest niepewna; dla filmu zawsze `None` | `episode_selection.numbering_gap` |
| Wyświetlanie | lista odcinków: `episode.title or ("Film" / "Odcinek N")`; szkic subskrypcji: `E{n}  {title or "Odcinek n"}` | `cli/interactive/anime_rows.py` `episode_row`, szkic w tym samym pliku |
| Skąd UI bierze listę | `AcquisitionService.episodes()` = `read_listing(...).listing`; panel woła ją przez rezydenta (`operation == "episodes"`) tylko po akcji użytkownika | `acquisition.episodes`, `automation.py` (`"episodes"`), `cli/interactive/anime.py` `_load_episodes`, `_load_draft` |
| Automat | cykliczne kontrole subskrypcji wołają `read_listing` i zapisują `ListingRead.mapping` | `automation.py` (`read_listing(..., saved=record.mapping)`), `subscription_targets.merge_listing` |
| Zapis na dysk | `_encode_mapping` zapisuje każdy `ListedEpisode` z kluczem `title`; `_decode_mapping` wymaga dokładnie zbioru `_LISTED_EPISODE_KEYS`; wersja schematu `WATCH_STATE_SCHEMA_VERSION = 6` | `application/watch_state.py`, `application/control.py` |
| Migracje | kod produktu nie migruje starych schematów; nowe pole to podbicie wersji i jednorazowy skrypt w `scripts/tmp/` (gitignorowany `tmp/`) | `application/AGENTS.md`, `.gitignore` |
| H1 | tożsamość odcinka czyta tytuły z `raw_episodes` własną funkcją `_episode_title`, nie z `ListedEpisode` | `episode_selection._episode_title`, `identity_target` |
| Pamięć rezydenta | `_Remembered` (LRU 64 wpisów pod `_memory_lock`) trzyma graf, mapowanie i terminarz z czasem pobrania; świeżość z `Cache-Control` ani.zip, inaczej `_FALLBACK_CACHE_S = 900` | `acquisition._Remembered`, `_remembered` |
| Log awarii mostu | `_bridge_failed(provider, error)` loguje dostawcę, kod i klasę błędu bez treści | `acquisition._bridge_failed` |
| Klient HTTP | jeden `httpx.Client(transport=request_control, follow_redirects=True)`; host spoza `_PROVIDERS` dostaje dostawcę `other` | `bootstrap.py`, `services/http_requests.py` `_PROVIDERS`, `_provider` |
| Wzorzec adaptera | `ArmCatalog`: klient wstrzykiwany, `USER_AGENT`, 404 jako brak wyniku, reszta jako `TitleCatalogError(EPISODE_CATALOG_FAILED)` | `services/catalog/arm.py`, `tests/services/catalog/test_arm.py` |

Konstruktory `ListedEpisode` z tytułem stoją w `anizip.parse_mapping`, `watch_state._decode_mapping` i w testach:
`tests/application/test_episode_selection.py`, `tests/cli/test_anime_episodes.py`, `tests/cli/test_interactive_anime.py`,
`tests/services/catalog/test_anizip.py` (asercje na `.title`). Część testów podaje tytuł pozycyjnie
(`ListedEpisode(1, "First", ...)`).

## Dowody: TVmaze

### Dokumentacja (https://www.tvmaze.com/api, odczyt 2026-11-26)

- Limit: "at least 20 calls every 10 seconds per IP address"; przekroczenie może dać HTTP 429. Odpowiedzi API są w cache
  load balancerów przez 60 minut.
- Lookup: "If the given ID can be matched, a HTTP 301 redirect to the show's URL will be returned. Otherwise, a HTTP 404
  is sent."
- Lista odcinków `/shows/:id/episodes`: "By default, specials are not included in the list".
- Licencja: "Use of the TVmaze API is licensed by CC BY-SA", z wymogiem podania TVmaze jako źródła.

### Zapytania na żywo (nagłówek `User-Agent: AniShift/0.1`, bez klucza, 2026-11-26)

```bash
curl -s -o /dev/null -D - -A "AniShift/0.1" "https://api.tvmaze.com/lookup/shows?thetvdb=478752"
curl -s -o /dev/null -D - -A "AniShift/0.1" "https://api.tvmaze.com/lookup/shows?thetvdb=999999999"
curl -s -A "AniShift/0.1" "https://api.tvmaze.com/shows/92844/episodes"
```

```text
lookup thetvdb=478752    -> 301, Location: https://api.tvmaze.com/shows/92844, Cache-Control: public, max-age=3600
lookup thetvdb=999999999 -> 404, Cache-Control: public, max-age=3600
GET /shows/67017/episodes            -> 200, 60 wpisów, wszystkie type "regular", season i number typu int
GET /shows/67017/episodes?specials=1 -> 200, 62 wpisy: dodatkowe 2 typu "insignificant_special" z number null
lookup ...&embed=episodes            -> 301 na /shows/92844 bez parametru embed: osadzenie odcinków ginie
```

Kształt potwierdzony odczytem; atrapy w testach mogą używać tylko tych pól.

Ciało serialu po przekierowaniu (`/shows/92844`), pola użyte w planie:

```json
{"id": 92844, "name": "Overgeared", "externals": {"tvrage": null, "thetvdb": 478752, "imdb": null}}
```

Element listy odcinków (pełny zestaw kluczy: `_links`, `airdate`, `airstamp`, `airtime`, `id`, `image`, `name`,
`number`, `rating`, `runtime`, `season`, `summary`, `type`, `url`), pola użyte w planie:

```json
{"id": 3762207, "name": "Even High School Boys Have Their Holes… / Ume Takes Responsibility", "season": 1, "number": 1, "type": "regular"}
```

Overgeared (TVmaze 92844), cała lista z 2026-11-26:

```text
1x1 Legendary Class                         1x7  Pagma's Sword Dance
1x2 First Step Towards Being a Blacksmith   1x8  Yatan's High Priest
1x3 Second Class                            1x9  Comrades in the Guild
1x4 Item Crafting Face-Off                  1x10 Episode 10   <- placeholder
1x5 Family's Trust                          1x11 Episode 11   <- placeholder
1x6 First Boss Raid                         1x12 Episode 12   <- placeholder
```

### Test zbiorczy na 23 subskrypcjach

Skrypt poza repo: dla każdej subskrypcji ani.zip po `anilist_id`, a przy braku odcinków arm-server i ani.zip po
`anidb_id` (jak `_anidb_numbering`); jedyne `tvdbShowId`; lookup i lista odcinków TVmaze; łączenie
`(seasonNumber, episodeNumber)` = `(season, number)` tylko dla `type == "regular"` i pary występującej raz. Romaji w
nawiasach kwadratowych liczony jako brak, jak w `_title`.

| Wynik | Liczba |
| --- | --- |
| subskrypcje z jednym `tvdbShowId` | 23 z 23 (5 dopiero przez mapowanie po AniDB) |
| lookup TVmaze udany | 23 z 23 |
| wyemitowane: angielski w ani.zip | 168 (TVmaze ma tytuł dla 168) |
| wyemitowane: tylko romaji w ani.zip | 16 (prawdziwy angielski w TVmaze: 16) |
| wyemitowane: bez tytułu w ani.zip | 10 (prawdziwy tytuł w TVmaze: 10) |
| niewyemitowane: bez tytułu w ani.zip | 81 (TVmaze: 6 prawdziwych, 64 placeholdery, 11 brak) |
| niewyemitowane: tylko romaji w ani.zip | 4 (prawdziwy angielski w TVmaze: 4) |
| placeholdery TVmaze | 64, wszystkie w kształcie `Episode N` |
| angielski w obu źródłach, inna pisownia | 29 z 169 |

Przykłady zamiany romaji na angielski: Overgeared E8 `Yatan no Saishichou` -> `Yatan's High Priest`, Magical Explorer
E8 `Sore wa Pink no Bakudan` -> `That's A Pink Bomb`, The World's Strongest Witch E8 ``Ten`i Shite Mita!`` ->
`I Tried Teleporting!`. Wypełnienia braków: Even the Student Council Has Its Holes! E1-E8 (tytuły antologii
`A / B / C`), Magic Repo Man E7 `Reunion` i E8 `Duel`.

Różnice pisowni (29) to apostrof ani.zip pisany odwrotnym apostrofem (``Family`s Trust`` / `Family's Trust`),
`Deja Vu` / `Déjà Vu`, dwukropek kontra myślnik i drobne słowa. Żadna nie wskazuje innego odcinka.

## Sprzeczności i niewiadome

- Zachowanie 429 TVmaze nie zostało sprowokowane; opis tylko z dokumentacji.
- Placeholdery inne niż `Episode N` nie wystąpiły w 2 pomiarach (2026-10-25 i 2026-11-26); nie zgadujemy ich.
- Pomiar z 2026-10-25 mówił, że TVmaze nie zna prawdziwych tytułów przed emisją; 2026-11-26 zna 10 (6 bez tytułu i 4 z
  romaji w ani.zip).
- Wyszukiwanie serialu po tytule nie jest potrzebne: każda subskrypcja ma `tvdbShowId` po zamianie na mapowanie AniDB.

## Wnioski

1. Łączenie po `(sezon, odcinek)` z mapowania `ListingRead.mapping` jest bezpieczne; daty i numery absolutne odpadają.
2. D3 wymaga rozdzielenia języka tytułu w `ListedEpisode` i w parserze ani.zip; ten kształt jest zapisany w
   `state.json`, więc zmiana podbija wersję schematu i wymaga jednorazowego skryptu.
3. Placeholdery `Episode N` trzeba odfiltrować, bo UI uznaje każdy niepusty tytuł za prawdziwy.
4. Koszt: 3 żądania fizyczne na serial (301, serial, odcinki) co najwyżej raz na godzinę i tylko przy wyemitowanym
   odcinku bez angielskiego tytułu; cache TVmaze trwa 60 minut.

## Źródła

- TVmaze API: https://www.tvmaze.com/api (odczyt 2026-11-26)
- Zapytania do `https://api.tvmaze.com/`, `https://api.ani.zip/mappings` i `https://arm.haglund.dev/api/v2/ids` (2026-11-26)
- Kod AniShift @ `1f76e30`: ścieżki w tabeli wyżej
- Stan: `config/watch/state.json` głównego checkoutu (tylko odczyt, 23 subskrypcje)

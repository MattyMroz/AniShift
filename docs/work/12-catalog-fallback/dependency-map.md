---
kind: research
status: completed
updated: 2026-10-25
baseline: main @ 4365a51
---

# Mapa zależności od AniList

Linie odnoszą się do `main` @ `4365a51`. Mapa obejmuje kod w `anishift/`, stan rezydenta i log awarii.

## 1. Odpowiedź w skrócie

- Jedynym klientem AniList jest `AniListCatalog` (`anishift/services/catalog/anilist.py:131`). Woła on jeden endpoint
  GraphQL `https://graphql.anilist.co` (`anilist.py:44`) przez wspólny `httpx.Client` z `RequestControl`
  (`anishift/bootstrap.py:111-112`, `:139`).
- Z AniList pochodzą cztery operacje: wyszukiwanie tytułu, graf franczyzy, harmonogram emisji i łańcuch prequeli.
  Każda kończy się przy awarii błędem `TitleCatalogError` z kodem `TITLE_CATALOG_FAILED` (`anilist.py:487-496`).
- Cache istnieje tylko w pamięci procesu: `_Remembered` w `AcquisitionService`, 64 wpisy LRU, świeżość 900 s albo
  `max-age` z ani.zip (`anishift/application/acquisition.py:173-176`, `:492-503`, `:1250-1255`). Restart rezydenta go
  czyści. Na dysku nie ma żadnej kopii odpowiedzi AniList.
- `anilist_id` jest kluczem całego stanu: subskrypcji, przypisań odcinków, potwierdzeń pobrań, zamówień legacy,
  rejestru decyzji i biblioteki. Inne źródła (ani.zip, arm-server, Kitsu) są dziś odpytywane **po** `anilist_id`
  i nie potrafią zastąpić wyszukiwania ani grafu franczyzy.
- W oknie awarii ani.zip, arm-server i Kitsu działały (§5). Aplikacja padała wyłącznie przez AniList.

## 2. Klient i operacje AniList

| Operacja | Miejsce | Zapytanie | Konsumenci |
|---|---|---|---|
| `search(text)` | `anilist.py:139-147`, `:209-221` | `SEARCH_QUERY` (`:59-64`), przy pustym wyniku jedna ponowna próba ze skróconymi słowami (`:478-484`) | `AcquisitionService.find_titles` (`acquisition.py:695-699`) → IPC `acquisition/titles` (`automation.py:9311-9314`) → panel Anime `_find_titles` (`cli/interactive/anime.py:2055-2069`), `ResidentSession.find_titles` (`cli/resident.py:184-186`) |
| `franchise(anilist_id)` | `anilist.py:157-183` | `_franchise_query()` głębokości 3, najwyżej 4 żądania (`:98-112`) | `AcquisitionService._franchise_graph` (`acquisition.py:861-874`) → `franchise()` (`:857-859`), `_context_graph` (`:1314-1320`), `_graph_movie` (`:963-970`), `_episode_request` (`:1120-1150`), `_torrentio_offer` (`:1180-1236`) |
| `airing_schedule(anilist_id)` | `anilist.py:185-207` | `SCHEDULE_QUERY`, do 200 stron (`:72-84`) | `AcquisitionService._schedule` (`acquisition.py:1287-1304`) → `read_listing` (`:880-952`); `AcquisitionService.airing_schedule` (`:850-855`) |
| `prequel_episodes(candidate)` | `anilist.py:149-151`, `:223-229`, `:395-410` | `RELATIONS_QUERY` po jednym na skok, do 8 skoków (`:53-54`, `:66-70`) | `AcquisitionService.season_context` (`acquisition.py:701-706`) → IPC (`automation.py:4705`) |

Pomocnicze funkcje bez sieci, ale z kształtem danych AniList:

- `candidate_from_node` (`anilist.py:359-387`) dekoduje węzeł AniList do `TitleCandidate`; używa go
  `graph_candidate` (`acquisition.py:1423-1431`).
- `graph_prequels` (`anilist.py:390-392`) liczy prequel z już pobranego grafu; używa go `graph_season_context`
  (`acquisition.py:1434-1438`).
- `OFFSET_FORMATS` (`anilist.py:56-57`) w `_first_season` (`acquisition.py:1453-1468`); `MAX_SCHEDULE_PAGES`
  (`anilist.py:83-84`) w budżecie żądań (`acquisition.py:532-538`, `:671-677`).

## 3. Dane i typy zależne od AniList

- `TitleCandidate` (`anishift/services/catalog/types.py:61-99`): `anilist_id`, tytuły romaji, english, native,
  synonimy, format, status, `prequel_ids`. `folder_title()` wybiera nazwę folderu (`types.py:96-99`).
- `SeasonAiring`, `EpisodeAiring` (`types.py:29-45`): harmonogram jednego `anilist_id`.
- `FranchiseGraph` (`anishift/application/episode_selection.py:256-263`): **surowy JSON węzłów AniList**. Stałe
  relacji, formatów i statusów są nazwami AniList (`episode_selection.py:73-107`).
- `identity_target` (`episode_selection.py:435-465`) buduje cel H1 z węzłów grafu: aliasy, format, `episodes`,
  tytuły innych serii. Klasyfikacja H1 jest zamrożona (`anishift/application/AGENTS.md`, sekcja „Pobieranie
  odcinków”). Wniosek: każde źródło grafu inne niż AniList zmienia wejście H1 i wymaga procedury regresji.
- `EpisodeListing` (`episode_selection.py:302-315`) łączy ani.zip i harmonogram AniList; `schedule_warning` i
  `schedule_retry_at` sygnalizują brak harmonogramu. `episode_listing` (`:505-554`) traktuje datę ani.zip jako
  `airs_at_fallback`, która nigdy nie potwierdza emisji.
- `EpisodeKey` (`episode_selection.py:352-357`): `anilist_id` + numer — klucz odcinka w ofertach i IPC.

## 4. `anilist_id` jako klucz trwałego stanu

| Miejsce | Pole i rola |
|---|---|
| `config/watch/state.json`, `subscriptions[]` | `SubscriptionRecord.anilist_id` (`application/subscription_targets.py:300-329`, pole `:304`); klucze zapisu `_SUBSCRIPTION_KEYS` (`application/watch_state.py:139-142`). Rekord trzyma też kopię `title`, `kitsu_id`, `mapping` (ani.zip), `catalog_status`, `episode_count`, `mapping_tvdb_season` (`subscription_targets.py:305-324`). Na żywym stanie: 20 subskrypcji, schemat 5 (`application/control.py:95`). |
| przypisania i potwierdzenia pobrań | `EpisodeChoice.anilist_id` (`control.py:384-399`), klucze `_ASSIGNMENT_KEYS` (`watch_state.py:373-379`) |
| zamówienia legacy | `LegacyScope`, `LegacyOrder` (`control.py:537-572`), `_LEGACY_ORDER_KEYS` (`watch_state.py:224`) |
| konflikty pobrań | `episode_conflict(state, anilist_id, number)` (`control.py:1088-1110`) |
| biblioteka | `DownloadedEpisode.anilist_id` (`application/library.py:173-177`), `untitled_series` i `name_series` (`library.py:210-240`) |
| rejestr decyzji | `config/watch/decisions.jsonl`, klucz `{"anilist_id", "number"}` (`application/acquisition_decisions.py:178-195`) |
| panel | wiersze subskrypcji i szczegóły przez `anilist_id` (`cli/interactive/state.py:496`, `state_subscriptions.py:84`), `_load_subscription` (`anime.py:460-479`) |

Wniosek: zmiana klucza na inny katalog oznacza migrację schematu stanu, rejestru decyzji i przypadków. Fallback musi
zachować `anilist_id` jako jedyny identyfikator wpisu.

## 5. Co już ma inne źródła

| Źródło | Plik | Wejście | Co daje | Czego nie daje |
|---|---|---|---|---|
| ani.zip | `services/catalog/anizip.py:39-74` | `anilist_id` albo `anidb_id` | odcinki z numeracją TVDB/absolutną, daty `airDateUtc`, `kitsu_id`, typ, liczba odcinków; 404 → pusty wpis (`:56-57`) | wyszukiwania tekstowego (`q` → 400 w badaniu z 2026-09-22, `docs/work/08-acquisition/research/anime-api-report.md`, §3), relacji franczyzy, statusu emisji |
| arm-server | `services/catalog/arm.py:45-66` | `anilist_id` | `anidb_id`, `thetvdb-season` | aplikacja nie czyta innych pól, choć odpowiedź zawiera także MAL, Kitsu, TVDB, ANN (research.md, §4.9) |
| Kitsu | `services/catalog/kitsu.py:42-66` | `anilist_id` | `kitsu_id` potwierdzony w obie strony | aplikacja nie używa wyszukiwania ani odcinków Kitsu |
| Torrentio | `services/torrents/torrentio.py` | `kitsu_id` + numer | kandydaci wydań | metadanych katalogu |
| zapis subskrypcji | `subscription_targets.py:533-543` | — | ostatni `catalog_status`, `episode_count`, `mapping` ani.zip | grafu franczyzy i harmonogramu AniList |

Pola `kitsu_id` i `tvdbShowId` występują wyłącznie jako dane z ani.zip, arm i Kitsu. W kodzie nie ma żadnego
alternatywnego wyszukiwania tytułów ani grafu relacji.

## 6. Zachowanie dziś przy awarii AniList

| Funkcja | Ścieżka błędu | Skutek |
|---|---|---|
| Panel Anime: szukanie tytułu | `find_titles` → `TitleCatalogError` → `_report(... provider="anilist")` (`anime.py:2060-2065`) | komunikat „AniList nie odpowiada · Spróbuj ponownie za chwilę” (`cli/interactive/anime_texts.py:94`); brak wyników |
| Panel Anime: otwarcie wpisu | `franchise` → wyjątek → `_catalog_failure` (`anime.py:2083-2091`, `:1609-1612`) | lista tytułów bez franczyzy; log `Anime catalogue command failed` (`anime.py:2008`) |
| Panel: subskrypcja → szczegóły | `_load_subscription` (`anime.py:468-471`) | ekran nie otwiera się mimo zapisanych danych subskrypcji |
| Lista odcinków | `read_listing`: brak grafu → `Listing franchise unavailable` (`acquisition.py:966-969`); brak harmonogramu → `Airing schedule unavailable` (`:1296-1300`) | lista z ani.zip i ostrzeżeniem „Brak terminów emisji (AniList)” (`anime.py:1106-1111`); `cut_point` zwraca `None` (`subscription_targets.py:496-497`) |
| Sprawdzenie subskrypcji | `subscription_check` → `_episode_request` → `_context_graph` → `franchise` (`acquisition.py:1120-1124`, `:1314-1316`) | `Subscription source failed` (`automation.py:3986-3992`), wynik `source_failed`, ponowienie po 60 s, potem co 300 s (`control.py:143`, `automation.py:4216-4234`); żaden odcinek nie jest pobrany |
| Dodanie subskrypcji | `_add_subscription` (`automation.py:3748-3754`) | odmowa `SOURCE_FAILED` |
| Nazwa serii w Bibliotece | `_series_title` (`automation.py:9077-9085`), wynik tylko w pamięci `_series_titles` (`automation.py:896`) | `Library series title unavailable`; zestaw nazwany od pliku (`library.py:233-235`) |
| Kontekst sezonu (stara ścieżka wyszukiwania wydań) | `season_context` (`acquisition.py:701-706`) | wyjątek do wywołującego |
| Cooldown 429 | `RequestControl` blokuje dostawcę (`services/http_requests.py:213-215`, `:273-282`), `_schedule` pomija żądanie (`acquisition.py:1292-1293`) | to samo co awaria, z terminem ponowienia |

Log nie mówi, **jak** AniList zawiódł: `_catalog_error` przenosi powód (`unreachable`, `rejected`, `malformed`) tylko
w `ErrorContext.details` (`anilist.py:494`), a reguła logowania zakazuje logowania `details`. Status HTTP trafia do
loga tylko na poziomie DEBUG (`http_requests.py:271`), którego plik nie zawiera.

## 7. Dowód z logu awarii

Źródło: `logs/anishift.log.jsonl`, okno 2026-10-20 17:04 – 2026-10-21 21:41 czasu lokalnego (+02:00). Liczono
skryptem po polach `message`, `name` i `extra`.

| Komunikat | Moduł | Liczba | Pierwszy – ostatni |
|---|---|---|---|
| `Franchise lookup failed` | `services.catalog.anilist` | 557 | 10-20 17:04 – 10-21 21:41 |
| `Listing franchise unavailable` | `application.acquisition` | 284 | 10-20 17:04 – 10-21 21:41 |
| `Airing schedule unavailable` | `application.acquisition` | 283 | 10-21 17:14 – 21:41 |
| `Subscription source failed` (`rate_limited: false`) | `application.automation` | 266 | 10-21 17:14 – 21:41 |
| `Library series title unavailable` | `application.automation` | 5 | 10-21 17:14 |
| `A control command failed` (`TITLE_CATALOG_FAILED`) | `application.automation` | 2 | 10-21 21:39 |
| `Anime catalogue command failed` | `cli.interactive.anime` | 2 | 10-21 21:39 |
| `Episode mapping completed` (ani.zip) | `services.catalog.anizip` | 199 | 10-21 17:14 – 21:40 |
| `Bridge IDs read` (arm) | `services.catalog.arm` | 284 | 10-20 17:04 – 10-21 21:41 |
| `Kitsu ID resolved` | `services.catalog.kitsu` | 60 | 10-21 17:14 – 21:40 |

Ustalenia:

- 10-20 o 17:04 była jedna porażka, a 20 s później udany odczyt. Właściwa awaria zaczęła się 10-21 o 17:14:14,
  przy starcie rezydenta, i trwała do jego zatrzymania o 21:38. Pierwszy udany odczyt nastąpił 10-22 o 11:10:40,
  przy następnym starcie. Faktyczny koniec awarii nie jest znany (rezydent nie działał).
- `rate_limited: false` i brak aktywnych `provider_locks` wskazują, że AniList nie odpowiadał kodem 429 z
  `Retry-After`. Czy był to 403 „API temporarily disabled”, 5xx czy brak połączenia — nie wiadomo (§6).
- 284 odczyty listy dały 557 porażek grafu. Dostępne dane wskazują na dwie próby grafu na jedno sprawdzenie
  subskrypcji: w `read_listing` (`acquisition.py:890`) i w `_episode_request` (`acquisition.py:1123`). Ponowienia
  po porażce idą co 60 s, potem co 300 s (`control.py:143`).
- Krótsze porażki AniList wystąpiły też 10-14, 10-16, 10-17 i 10-18 (od 1 do 6 komunikatów dziennie).
- W tym samym czasie działały ani.zip, arm-server i Kitsu.

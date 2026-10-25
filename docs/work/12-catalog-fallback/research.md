---
kind: research
status: completed
updated: 2026-10-25
baseline: main @ 4365a51
---

# Alternatywy dla AniList: co może przejąć katalog przy awarii

## 1. Odpowiedź

**Żaden darmowy serwis bez klucza nie zastępuje dziś AniList w całości.** AniList jako jedyny daje naraz wyszukiwanie,
typowany graf relacji z formatami i datami oraz harmonogram każdego odcinka. Graf w dokładnie tym kształcie zasila
zamrożoną klasyfikację tożsamości H1.

Najtańszą drogą do utrzymania działania jest **lokalna kopia ostatnich udanych odpowiedzi AniList**, używana tylko
wtedy, gdy AniList nie odpowiada. Zachowuje ona `anilist_id`, kształt danych i wejście H1 bez zmian.

Jedyny sensowny dodatkowy dostawca na później to **kalendarz Shikimori**: bez klucza, z kluczem MAL ID, z datą
najbliższego odcinka. Na dziś to opcja, nie wymóg (specification.md, D4).

Zakres i data: stan na **2026-10-25**, sprawdzany z tej maszyny. Zapytania pojedyncze, bez kluczy. Probe obejmowały
trzy subskrypcje bieżącego sezonu (jesień 2026): AniList `207329` / MAL `63431` (nowy tytuł), `159042` / `53913`
(Reincarnated as a Sword II) i `195516` / `61987`.

Oznaczenia: **DIRECT** — sprawdzone tu odpytaniem lub odczytem dokumentu; **REPORTED** — podane przez źródło;
**INFERENCE** — wniosek z kilku faktów; **UNKNOWN** — brak dowodu.

## 2. Wymagane funkcje

| Funkcja | Po co w AniShift |
|---|---|
| F1 wyszukiwanie po tekście | panel Anime, nazwy serii w Bibliotece |
| F2 franczyza i relacje z formatami | widok wpisów, kontekst sezonu, cel H1 |
| F3 harmonogram z datami odcinków | terminy subskrypcji, `cut_point`, kontrola dat w H1 |
| F4 liczba i numeracja odcinków | lista odcinków, cele subskrypcji |
| F5 tytuły w wielu językach | aliasy H1, zapytania do źródeł wydań |
| F6 mapowanie ID na AniList | zachowanie kluczy `anilist_id` |

## 3. Tabela porównawcza

| Kandydat | F1 | F2 | F3 | F4 | F5 | F6 | Klucz / token | Limit | Stan 2026-10-25 |
|---|---|---|---|---|---|---|---|---|---|
| **AniList** (obecny) | tak | tak, typowany graf | tak, `airingSchedule` z `airingAt` | tak | romaji, en, native, synonimy | — | nie | 90/min, obecnie 30/min (tryb degradacji) | działa; awaria 2026-10-21 (dependency-map.md, §7) |
| **Jikan** (MAL, scraping) | tak `/anime?q` | tak `/anime/{id}/relations` | tylko dzień i godzina emisji (`broadcast`), `/schedules` | tak | tak | przez arm/Fribb | nie | 3/s, 60/min | **publiczne API wyłączone 2026-10-01**; `api.jikan.moe` nie łączy się |
| **MAL API v2** (oficjalne) | tak `/anime?q` | `related_anime` | tylko `broadcast` | `num_episodes` | tak | przez arm/Fribb | **tak, `X-MAL-CLIENT-ID`** | nieopisany w odczytanym dokumencie | bez klucza 403 |
| **Kitsu** | tak `filter[text]` | `media-relationships` | **nie**: `airdate` = `null` dla bieżącego sezonu | `episodeCount` = `null` dla nowego tytułu | en, en_jp, ja_jp | `mappings` (już w repo) | nie | brak w znalezionych źródłach | działa (`kitsu.io` i `kitsu.app`) |
| **ani.zip** (już w repo) | nie (`q` → 400 we wcześniejszym badaniu) | nie | częściowo: `airDateUtc` z TVDB; brak dla nowych tytułów | tak, gdy mapowany | tak, gdy mapowany | tak, `mappings` | nie | brak w znalezionych źródłach | działa; `207329` zwraca puste `episodes` i `titles` |
| **arm-server** (już w repo) | nie | nie | nie | nie | nie | **tak, w obie strony** | nie | brak w znalezionych źródłach | działa, także dla `207329` |
| **TVmaze** | tak (seriale) | nie | **tak, `airstamp` każdego odcinka** w numeracji TVDB | tak | nazwa EN | `lookup/shows?thetvdb=` | nie | ≥20 wywołań / 10 s | działa; godzina różni się od AniList (§5) |
| **Shikimori** | tak `/api/animes?search` | `/api/animes/:id/related`, `/franchise` | **tylko najbliższy odcinek**: `/api/calendar` | tak | ru, en, ja | ID = MAL ID (INFERENCE z probe) | nie, wymaga `User-Agent` | 5 rps, 90 rpm | działa na `shikimori.io`; `shikimori.one` → 522 |
| **AnimeSchedule** | tak | tak | tak, z przesunięciami | tak | tak | ID AniList/MAL w danych (REPORTED we wcześniejszym badaniu) | **tak, token aplikacji** | w zakładce Rate Limits (nie odczytano) | bez tokenu `/timetables` → 401; wymaga atrybucji |
| **AniDB** | dump tytułów | tak | daty odcinków | tak | tak | przez arm/Fribb | rejestracja klienta (REPORTED) | UNKNOWN: oficjalna strona zwróciła 403 | nie badano odpytaniem |
| **ANN Encyclopedia** | tak `api.xml?title=~` | `related-prev`/`related-next` | nie | częściowo | tak | brak w ani.zip; jest w arm (`animenewsnetwork`) | nie | 1 żądanie/s/IP | działa; XML; wymaga linku zwrotnego |
| **Fribb/anime-lists** | — | — | — | — | — | **tak, plik JSON** | nie | GitHub raw | aktywne (push 2026-10-20) |
| **manami anime-offline-database** | offline | `relatedAnime` (bez typu relacji) | nie | `episodes`, `status` | `synonyms` | tak, `sources` | nie | — | **repozytorium zarchiwizowane**, ostatnie wydanie 2026-27 (2026-07-04) |

Nie badano: LiveChart, Simkl, TMDB, TheTVDB i notify.moe. Brak wpisu nie oznacza braku API, tylko brak dowodu w
tej rundzie.

## 4. Ustalenia per kandydat

### 4.1 AniList

- DIRECT: dokumentacja limitów podaje 90 żądań na minutę i ostrzeżenie: „The API is currently in a degraded state
  and is limited to 30 requests per minute”. Probe z 2026-10-25 zwrócił nagłówek `X-RateLimit-Limit: 30`.
  Po przekroczeniu limitu: 429 i minuta przerwy, z `Retry-After` i `X-RateLimit-Reset`. [1]
- DIRECT: w poważnej awarii AniList „may lower the rate limits” albo „temporarily suspend access”, ogłaszając to na
  Discordzie. Wtedy API odpowiada **403** z komunikatem „The AniList API has been temporarily disabled due to severe
  stability issues”. AniList może też ręcznie zablokować IP. [2]
- DIRECT, regulamin: „Using the AniList API as a backup or data storage service is strictly prohibited” oraz
  „Hoarding or mass collection of data from the AniList API is strictly prohibited”. Darmowe dla użytku
  niekomercyjnego. [3]
- INFERENCE: lokalna kopia wyłącznie wpisów, które aplikacja już odczytała dla użytkownika, z limitem liczby
  wpisów, jest cache'em klienta, a nie usługą kopii zapasowej ani masowym zbieraniem. To interpretacja, nie opinia
  prawna; decyzja należy do właściciela (specification.md, D1).
- DIRECT: `airingSchedule` wpisu `159042` (zapytanie jak `SCHEDULE_QUERY`) zwrócił na jednej stronie wszystkie 12
  odcinków sezonu, od 2026-09-30 do 2026-12-16, co tydzień o 15:30 UTC. Zapisany harmonogram zawiera więc także
  przyszłe daty znane w chwili zapisu.

### 4.2 Jikan

- DIRECT: OpenAPI Jikan v4 podaje limity 3/s i 60/min, cache 24 h oraz endpointy `/anime`, `/anime/{id}/full`,
  `/anime/{id}/relations`, `/anime/{id}/episodes`, `/schedules` (`filter`) i `/seasons/now`. [4]
- DIRECT: zgłoszenie #612 opisuje pełną awarię `api.jikan.moe` od 2026-08-28 (504 na wszystkich endpointach). [5]
- DIRECT: zgłoszenie #613 autora projektu: „Jikan public API was discontinued as of October 1, 2026”, z zaleceniem
  przejścia na własne instancje. [6]
- DIRECT: 2026-10-25 dwie próby połączenia z `api.jikan.moe` (rekordy DNS istnieją) skończyły się przekroczeniem
  czasu połączenia.
- Wniosek: Jikan odpada. Własna instancja oznacza utrzymanie serwera scrapującego MAL — to więcej niż cały problem.

### 4.3 MyAnimeList API v2

- DIRECT: klient bez logowania uwierzytelnia się nagłówkiem `X-MAL-CLIENT-ID`. Są endpointy `/anime?q`,
  `/anime/{anime_id}`, `/anime/season/{year}/{season}`, pola `broadcast` i `related_anime`. [7]
- DIRECT: `GET https://api.myanimelist.net/v2/anime/53913` bez nagłówka → 403.
- Wniosek: brak dat poszczególnych odcinków, potrzebny klucz. Nie spełnia F3; klucz to koszt utrzymania.

### 4.4 Kitsu

- DIRECT: `GET https://kitsu.io/api/edge/anime?filter[text]=...` znalazł tytuł `51014` (= MAL `63431` według arm).
  Atrybuty: `status=current`, `episodeCount=null`, `nextRelease=null`. Tytuły tylko `en`, `en_jp`, `ja_jp`.
- DIRECT: `/anime/51014/episodes` zwrócił 22 odcinki, wszystkie z `airdate=null`. `/anime/51014/media-relationships`
  zwrócił tylko `alternative_version` do mangi.
- DIRECT: repozytorium dokumentacji `hummingbird-me/api-docs` ostatni push 2024-08-17, `kitsu-server` 2026-06-20.
  `kitsu.app/api/edge` odpowiada 200.
- Wniosek: Kitsu może wspomóc F1, ale nie daje F3 ani pewnego F2 dla bieżącego sezonu.

### 4.5 ani.zip

- DIRECT: `GET https://api.ani.zip/mappings?anilist_id=207329` → 200, `episodes` = `{}`, brak `titles`,
  `kitsu_id=null`; `Cache-Control: public, max-age=900`.
- DIRECT: dla `195516` i `159042` ani.zip zawiera przyszłe `airDateUtc` (odcinki 5–8 i 4–8).
- Wniosek: ani.zip już jest w aplikacji i działało w czasie awarii, ale dla nowych tytułów bywa puste. Jego daty
  aplikacja traktuje świadomie tylko jako zapasowe (`airs_at_fallback`).

### 4.6 TVmaze

- DIRECT: dokumentacja: wyszukiwanie seriali, `/lookup/shows?thetvdb=:id`, `/shows/:id/episodes`, `/schedule`,
  `/schedule/web`, `/schedule/full`; cache 60 min; „at least 20 calls every 10 seconds per IP”; licencja CC BY-SA
  z obowiązkiem linku do TVmaze. [8]
- DIRECT: `lookup/shows?thetvdb=410378` → serial `63237` „Reincarnated as a Sword”, harmonogram środa 23:00.
  Odcinki S2E3–S2E12 mają `airstamp` od 2026-10-14 do 2026-12-16.
- Wniosek: dobre daty całego sezonu, ale w numeracji TVDB (sezon, odcinek), a nie lokalnej numeracji wpisu AniList.
  Potrzebuje TVDB ID i sezonu (arm je zwraca). Równoległy workstream `19-tvmaze-episode-titles` planuje już adapter
  TVmaze dla tytułów odcinków.

### 4.7 Shikimori

- DIRECT: dokumentacja v1: „API access is limited by 5rps and 90rpm”, ban IP bez poprawnego `User-Agent`.
  Endpointy `/api/animes`, `/api/animes/search`, `/api/animes/:id/related`, `/api/animes/:id/franchise`,
  `/api/calendar`. [9]
- DIRECT: `GET https://shikimori.io/api/calendar` → 200, 93 trwające tytuły z polami `next_episode` i
  `next_episode_at`. `shikimori.one` zwrócił 522 (dokumentacja i kalendarz).
- DIRECT: identyfikatory w kalendarzu pokrywają się z MAL ID (`63431`, `53913`, `61987`). INFERENCE: ID Shikimori =
  MAL ID; arm-server zamienia MAL ↔ AniList.
- Wniosek: najtańszy drugi harmonogram bez klucza, ale tylko dla **najbliższego** odcinka i z historią zmian domeny.

### 4.8 AnimeSchedule

- DIRECT: dokumentacja v3: publiczne endpointy są „for internal use only”, właściwe wymagają nagłówka
  `Authorization: Bearer` z tokenem aplikacji. [10]
- DIRECT: `GET https://animeschedule.net/api/v3/timetables/sub` bez tokenu → 401.
- REPORTED we wcześniejszym badaniu repo: wymóg widocznej atrybucji i poszanowania limitów
  (`docs/work/08-acquisition/research/anime-api-metadata-validation.md`, linia 403).
- Wniosek: najlepsze dane o przesunięciach emisji, ale token i atrybucja. Powód odłożenia z 08-acquisition nadal
  obowiązuje.

### 4.9 Mapowanie identyfikatorów

- DIRECT: arm-server (`/api/v2/ids?source=anilist&id=` i `source=myanimelist&id=`) zwraca w obie strony AniDB,
  AniList, ANN, Anime-Planet, aniSearch, IMDb, Kitsu, LiveChart, MAL, TMDB (+ sezon), TVDB (+ sezon). Dla nowego
  `207329` zwrócił komplet. README: dane z `Fribb/anime-lists`. [11]
- DIRECT: `Fribb/anime-lists` łączy `anime-offline-database` (fork `cedya77`, push 2026-10-25) i
  `Anime-Lists/anime-lists`. [12]
- DIRECT: `manami-project/anime-offline-database` jest zarchiwizowane; ostatnie wydanie `2026-27` z 2026-07-04,
  licencja ODbL. [13]
- Wniosek: mapowanie ID nie jest problemem — arm-server już jest w aplikacji. Dodatkowy plik offline nie jest
  potrzebny.

### 4.10 AniDB i ANN

- AniDB: oficjalna strona HTTP API zwróciła tu 403; limity są UNKNOWN. Wyszukiwarka pokazuje parametry
  `client`/`clientver`, czyli rejestrację klienta. [14] Nie rekomendujemy.
- ANN: XML, „rate-limited to 1 request per second per IP”, prośba o cache tygodniowy i link zwrotny. Search
  `api.xml?title=~reincarnated as a sword` zwrócił wpis `26756` z `related-prev`. Brak dat odcinków. [15]

## 5. Zgodność dat między źródłami

Godzina emisji najbliższego odcinka, UTC, odczyt 2026-10-25:

| Wpis | AniList | Shikimori | TVmaze | ani.zip |
|---|---|---|---|---|
| `207329` ep 4 | 2026-10-27 15:00 | 2026-10-27 15:00 | — | brak |
| `159042` ep 5 | 2026-10-28 15:30 | 2026-10-28 15:00 | S2E5 2026-10-28 14:00 | 2026-11-04 15:00 |
| `195516` ep 5 | 2026-10-30 14:00 | 2026-10-30 14:00 | nie sprawdzano | 2026-10-30 14:00 |

INFERENCE: źródła zastępcze potrafią różnić się godziną, a ani.zip nawet tygodniem (inna numeracja albo opóźnienie).
Zastąpienie dat AniList datami innego źródła zmieni terminy subskrypcji i wejście kontroli dat H1. Ostatnia znana
odpowiedź AniList jest wierniejsza niż świeża odpowiedź innego dostawcy, o ile nie zaszło przesunięcie emisji.

## 6. Sprzeczności i niewiadome

- UNKNOWN: przyczyna awarii 2026-10-21 (403, 5xx czy brak połączenia) — log jej nie zapisał (dependency-map.md, §6).
- UNKNOWN: jak często AniList przesuwa daty w trakcie sezonu. Od tego zależy, ile warte są zapisane harmonogramy w
  długiej awarii.
- UNKNOWN: limity Kitsu, ani.zip i arm-server — nie znaleziono ich w dokumentacji.
- Ograniczenie: każdy probe to jeden odczyt z jednej maszyny; dostępność to obserwacja, nie statystyka.

## 7. Rekomendacja

1. Zapisywać ostatnią udaną odpowiedź AniList (graf franczyzy, harmonogram) per `anilist_id` i używać jej, gdy
   AniList zawiedzie. Wyszukiwanie w awarii przeszukuje zapisane tytuły.
2. Nie dodawać teraz drugiego dostawcy. Kandydat na później: kalendarz Shikimori (MAL ID przez arm-server), tylko
   jako uzupełnienie harmonogramu dla trwających subskrypcji — jeśli praktyka pokaże, że zapisane daty nie wystarczają.
3. Nie używać Jikan (wyłączony), MAL API i AnimeSchedule (klucz lub token), AniDB (rejestracja, nieznane limity).

## 8. Źródła

Dostęp do wszystkich: 2026-10-25.

1. AniList, „Rate Limiting”, https://docs.anilist.co/guide/rate-limiting
2. AniList, „Considerations”, https://docs.anilist.co/guide/considerations
3. AniList, „Terms of Use”, https://docs.anilist.co/guide/terms-of-use
4. Jikan REST v4, OpenAPI, https://raw.githubusercontent.com/jikan-me/jikan-rest/master/storage/api-docs/api-docs.json
5. jikan-me/jikan-rest #612, „FULL OUTAGE: api.jikan.moe returns 504 on ALL endpoints since Aug 28”, https://github.com/jikan-me/jikan-rest/issues/612
6. jikan-me/jikan-rest #613, „Public API Discontinuation [1st Oct, 26]”, https://github.com/jikan-me/jikan-rest/issues/613
7. MyAnimeList API v2 reference, https://myanimelist.net/apiconfig/references/api/v2
8. TVmaze API, https://www.tvmaze.com/api
9. Shikimori API v1, https://shikimori.io/api/doc/1.0
10. AnimeSchedule API v3, https://animeschedule.net/api/v3/documentation
11. BeeeQueue/arm-server README, https://github.com/BeeeQueue/arm-server
12. Fribb/anime-lists README, https://github.com/Fribb/anime-lists
13. manami-project/anime-offline-database, https://github.com/manami-project/anime-offline-database (wydania: `/releases`)
14. AniDB, „HTTP API Definition”, https://wiki.anidb.net/HTTP_API_Definition (403 przy odczycie)
15. ANN Encyclopedia API, https://www.animenewsnetwork.com/encyclopedia/api.php
16. Badanie repo z 2026-09-22: `docs/work/08-acquisition/research/anime-api-report.md`, `anime-api-metadata-validation.md`

Odpytane endpointy (2026-10-25, każdy raz): `https://graphql.anilist.co` (3 zapytania), `https://api.jikan.moe/v4/anime/63431`
(i retry), `https://kitsu.io/api/edge/anime?filter[text]=…`, `/anime/51014/episodes`, `/anime/51014/media-relationships`,
`https://kitsu.app/api/edge/anime/46917`, `https://api.ani.zip/mappings?anilist_id={207329,195516,159042}`,
`https://arm.haglund.dev/api/v2/ids` (3 zapytania), `https://api.tvmaze.com/lookup/shows?thetvdb=410378`, `/shows/63237/episodes`,
`https://shikimori.io/api/calendar`, `https://api.myanimelist.net/v2/anime/53913`,
`https://animeschedule.net/api/v3/timetables/sub`, `https://cdn.animenewsnetwork.com/encyclopedia/api.xml?title=~…`.

---
kind: research
status: final
baseline: 4365a51 (main)
checked: 2026-10-25
---

# Research: tytuły odcinków z TVmaze (issue #58)

## Odpowiedź

TVmaze nadaje się jako źródło brakujących tytułów, ale zysk dziś jest wąski. Dla 20 subskrypcji z `config/watch/state.json` numeracja `(sezon, odcinek)` z ani.zip zgadza się z TVmaze w 20 na 20 seriali, a lookup po `tvdbShowId` z ani.zip działa bez klucza. Z 93 odcinków bez tytułu w ani.zip TVmaze ma prawdziwy tytuł dla 6; 62 to placeholdery `Episode N`, a 25 TVmaze w ogóle nie zna. Wartość to okno opóźnienia: odcinek wyemitowany, a ani.zip jeszcze bez tytułu.

## Zakres i stan na dzień

- Pytanie: jak najprościej uzupełnić `ListedEpisode.title` tam, gdzie go brak, bez nadpisywania istniejących tytułów.
- Stan na 2026-10-25, TVmaze API bez klucza, AniShift `main` @ `4365a51`.
- Poza zakresem: cały zapas na wypadek awarii AniList (równoległy workstream katalogu).

## Ustalenia: stan dziś w kodzie

Fakty z kodu (ścieżka + symbol).

| Pytanie | Odpowiedź | Gdzie |
| --- | --- | --- |
| Skąd tytuł odcinka | tylko ani.zip: `en`, a gdy brak, `x-jat` (romaji) | `anishift/services/catalog/anizip.py` `_title`, `parse_mapping` |
| AniList | kod nie czyta z niego tytułów odcinków (brak `streamingEpisodes` w `anishift/`); daje terminarz (`airs_at`) i liczbę odcinków | `application/episode_selection.py` `episode_listing` |
| Join | `episode_listing` łączy `mapping.episodes` (ani.zip) z terminarzem AniList; brakujące numery dostają `ListedEpisode(number)` bez tytułu | `episode_selection.py:505-554` |
| Pola numeracji | `ListedEpisode.season/episode/absolute` pochodzą z `seasonNumber/episodeNumber/absoluteEpisodeNumber` ani.zip | `anizip.py:92-101` |
| Surowe dane | `raw_episodes` zachowuje każde pole ani.zip, w tym `tvdbShowId`; zasilają H1 i nie wolno ich normalizować | `services/catalog/AGENTS.md`, `episode_selection.identity_target` |
| Wyświetlanie: Anime, lista odcinków | `episode.title or "Odcinek N"` (`"Film"` dla filmu) | `cli/interactive/anime_rows.py:111` |
| Wyświetlanie: szkic subskrypcji | `E{n}  {title or "Odcinek n"}` | `anime_rows.py:176`, szkic z `subscription_texts.py:111` |
| Subskrypcje (lista) i Biblioteka | nie pokazują tytułów odcinków (Biblioteka używa tytułu serii, Subskrypcje numeru `E{n}`) | `application/library.py:105`, `subscription_texts.py:167` |
| Skąd UI bierze listę | `AcquisitionService.episodes()` -> `read_listing().listing`; w UI przez rezydenta (`operation: "episodes"`) | `acquisition.py:876`, `automation.py:9318`, `cli/resident.py:215`, `anime.py:517,1681` |
| Odświeżanie | pamięć rezydenta `_Remembered.mapping` z TTL = `Cache-Control: max-age` ani.zip, a bez niego 900 s (`_FALLBACK_CACHE_S`); nic w tle | `acquisition.py:493-503, 1262-1285` |
| Zapis na dysk | `merge_listing` zapisuje `read.mapping` (w tym `episodes` z tytułami) w `config/watch/state.json`; porównania zmian numeracji czytają tylko `raw_episodes` | `subscription_targets.py:512-544, 629-645` |
| Kto jeszcze woła `read_listing` | automat subskrypcji (cykliczne kontrole): 4 miejsca w `automation.py` | `automation.py:3750,3928,5346,5675` |
| Klient HTTP | jeden `httpx.Client` (`follow_redirects=True`) z `RequestControl`; host spoza tabeli `_PROVIDERS` dostaje dostawcę `other` | `bootstrap.py:~116`, `http_requests.py:46-58, 285` |
| Wzorzec adaptera | `arm.py`: klient wstrzykiwany, 404 -> puste wyniki, reszta -> `TitleCatalogError(EPISODE_CATALOG_FAILED)` | `services/catalog/arm.py` |

Dane z `state.json` (tylko odczyt): przyszłe odcinki mają `"title": {"en": null}`, a każdy odcinek `raw_episodes` niesie `tvdbShowId`. Wszystkie 20 subskrypcji mają dokładnie jedno niepuste `tvdbShowId` (Ramparts of Ice i Nia Liston mają dodatkowo wpisy `null`).

Dodatkowe obserwacje o ani.zip (zapytania na żywo 2026-10-25):

- Overgeared (AniList 212888): ani.zip ma już tytuły E1-E4 (`Legendary Class` itd.), więc przykład z issue (E1) jest dziś pokryty przez ani.zip. Zostają E5+ bez tytułu.
- Even the Student Council Has Its Holes! (191656): ani.zip ma tytuły `ja` i `de` dla E1-E4, ale `en: null`, więc `_title` zwraca `None`. Tu TVmaze wypełnia lukę.
- Daty emisji różnią się o dni między ani.zip i TVmaze (Overgeared E1: ani.zip `2026-10-02`, TVmaze `2026-09-27`), więc daty nie nadają się do łączenia odcinków.

## Dowody: TVmaze

### Dokumentacja (https://www.tvmaze.com/api, odczyt 2026-10-25)

- Limit: "at least 20 calls every 10 seconds per IP address"; możliwe HTTP 429, zalecany ponowny odczyt po krótkiej przerwie. Cache po stronie TVmaze 60 minut.
- Lookup: `/lookup/shows?thetvdb=:id` lub `?imdb=:id`; dopasowanie daje 301 do `/shows/:id`, brak dopasowania 404.
- Lista odcinków: `/shows/:id/episodes`; specjale tylko z `specials=1`.
- Licencja: "licensed by CC BY-SA"; atrybucję spełnia link do TVmaze w aplikacji lub na stronie.
- Dokumentacja nie opisuje pól odcinka ani placeholderów nazw; to wiemy wyłącznie z odpowiedzi (niżej).

### Zapytania na żywo (nagłówek `User-Agent: AniShift/0.1`, bez klucza)

Lookup po TVDB (301, `Cache-Control: public, max-age=3600`):

```text
GET /lookup/shows?thetvdb=440056 -> 301 /shows/93848   (Magical Explorer)
GET /lookup/shows?thetvdb=470347 -> 301 /shows/94416   (Magic Repo Man = Kashita Maryoku wa Revo Barai de Kyousei Choushuu)
GET /lookup/shows?thetvdb=478752 -> 301 /shows/92844   (Overgeared)
GET /lookup/shows?thetvdb=463051 -> 301 /shows/94436   (Even the Student Council Has Its Holes!)
GET /lookup/shows?thetvdb=999999999 -> 404
```

Lista odcinków `GET /shows/{id}/episodes?specials=1` (200, `max-age=3600`); użyte pola: `season`, `number`, `name`, `type`, `airdate`, `airstamp`:

```text
Overgeared (92844)       1x1 "Legendary Class"  1x2 "First Step Towards Being a Blacksmith"
                         1x3 "Second Class"  1x4 "Item Crafting Face-Off"
                         1x5..1x12 "Episode 5" ... "Episode 12"        <- placeholdery
Magical Explorer (93848) 1x4 "Determination"  1x5 "Greetings, Tsukuyomi Magic Academy"
                         1x6 "Episode 6"  1x7 "Episode 7"            (tylko 7 z 13 odcinków)
Magic Repo Man (94416)   1x1 "Kicked Out"  1x2 "Contract"  1x3 "Investment"  1x4 "Powerful Foe"
                         1x5 "Episode 5"  1x6 "Episode 6"   (ani.zip E4 ma tylko x-jat "[Kyouteki]")
Student Council (94436)  1x1 "Even High School Boys Have Their Holes… / Ume Takes Responsibility"
                         1x2 "Savior Tan / The Seven Mysteries of the Academy and the Council's
                              Night Patrol / Komaro Is Here!"
                         1x5 "Episode 5"                             <- tytuł składany z segmentów antologii
```

Pola serialu (`/shows/92844`): `externals: {"thetvdb": 478752, "imdb": null, "tvrage": null}`, `premiered: 2026-09-27`, `type: Animation`, `language: Japanese`.

Wyszukiwanie po tytule: `GET /search/shows?q=Kashita%20Maryoku` oraz `?q=Revo%20Barai` zwróciły Magic Repo Man (94416) z angielską nazwą. Dopasowanie po fragmencie romaji zadziałało w tym jednym przypadku; wiarygodności wyszukiwania po tytule nie zmierzono (patrz niewiadome) i nie jest potrzebna, skoro ani.zip daje `tvdbShowId`.

### Test zbiorczy na 20 subskrypcjach

Skrypt (poza repo, w katalogu tymczasowym sesji): dla każdej subskrypcji lookup po jedynym `tvdbShowId` z `raw_episodes`, lista odcinków, join po `(seasonNumber, episodeNumber)` ani.zip = `(season, number)` TVmaze (tylko `type == regular`), 2 zapytania na serial, przerwa 0,6 s.

| Wynik | Liczba |
| --- | --- |
| seriale z udanym lookupiem | 20 z 20 |
| odcinki ani.zip bez tytułu (`en` i `x-jat` puste) | 93 |
| z tego: prawdziwy tytuł w TVmaze | 6 |
| z tego: placeholder `Episode N` w TVmaze | 62 |
| z tego: brak odcinka w TVmaze | 25 |
| odcinki z tytułem w obu źródłach | 80 |
| z tego: ten sam tytuł po normalizacji | 70 |
| z tego: inna pisownia | 10 |

Żaden z 80 wspólnych odcinków nie wskazuje przesunięcia numeracji. Dziesięć różnic to głównie romaji z ani.zip kontra angielski z TVmaze (`Atarashii Nichijou` / `A New Daily Life`, `Deja Vu` / `Déjà Vu`, `Fire Rat's Cloak` / `The Fire-Rat Cloak`). Sześć wypełnień: Student Council E1-E4, Magical Explorer E5, A Wild Last Boss E5.

Sezony: Apothecary Diaries (TVDB 431162, TVmaze 62 odcinki) i Sasaki and Peeps (422728, 18 odcinków) mają w TVmaze kolejne sezony w jednym serialu `(1,1)..(2,1)`, tak samo jak `seasonNumber` w ani.zip. TVmaze numeruje po sezonach TV (jak TVDB), nie po wpisach AniList. Kluczem łączenia jest `(sezon, odcinek)`, nigdy numer lokalny wpisu ani absolutny.

## Sprzeczności i niewiadome

- Zysk dziś jest skromny; nie mierzono, jak często TVmaze wyprzedza ani.zip w dłuższym oknie (próba: jedna doba, 20 seriali).
- Czy TVmaze podaje kiedykolwiek prawdziwy tytuł przed emisją: w próbie żaden niewyemitowany odcinek go nie miał (UNKNOWN poza próbą).
- Placeholdery inne niż `Episode N` (np. `TBA`) nie wystąpiły; nie zgadujemy ich.
- Skuteczność wyszukiwania po tytule i dacie premiery nie została zmierzona.
- Zachowanie 429 TVmaze nie zostało sprowokowane; tylko dokumentacja.
- Tytuły TVmaze są angielskie. Czy preferować je nad romaji `x-jat` z ani.zip, to decyzja właściciela (specification, D3).

## Wnioski (INFERENCE)

1. Join po `(sezon, odcinek)` jest bezpieczny, gdy `tvdbShowId` jest jednoznaczne; daty i numery absolutne odpadają.
2. Placeholdery trzeba odfiltrować, bo UI traktuje każdy niepusty tytuł jako prawdziwy.
3. Koszt jest niski: 2 żądania na serial, cache TVmaze 60 minut, więc cache w pamięci rezydenta na 60 minut pasuje do ich okna.
4. Odpowiedzi z TVmaze nie powinny trafiać do `raw_episodes` ani do zapisanej mapowania (H1 i porównania numeracji są na nich oparte).

## Źródła

- TVmaze API: https://www.tvmaze.com/api (odczyt 2026-10-25)
- Zapytania bezpośrednie do `https://api.tvmaze.com/` i `https://api.ani.zip/mappings` (2026-10-25)
- Kod AniShift @ `4365a51`: ścieżki w tabeli wyżej
- Stan: `config/watch/state.json` (tylko odczyt, 20 subskrypcji)

# Walidacja metadanych anime — część A

## Status i najważniejsza odpowiedź

**DONE — wykonany zakres A; odbiór Opus5 `ses_f363ca9a5ffeDVPeKHT7WzYist`: PASS WITH FINDINGS, bez błędów materialnych.** Uwagi uzupełniono na podstawie zapisanych źródeł; końcowa weryfikacja korekt przez Opus5 `ses_f3631f3eeffes5rFtRdza7pEta`: **PASS**. Stan odczytów: **2026-09-22, 15:16:59–15:22:22 UTC według zegara klienta**. Baseline: `0e8a6bf9194d2786d426d3f3a58f48272b3eb087`, branch `work/local-automation/06-efficiency`.

**ani.zip jest użytecznym dostawcą mapowań i list odcinków wybranego wpisu, ale nie wystarcza jako katalog całej franczyzy ani jako źródło prawdy o publikacji wydań.** Sześć pełnych odpowiedzi zawierało 89 obiektów odcinków i dodatków, 24 obiekty obrazów oraz 74 znormalizowane ścieżki pól. Odcinki mają równolegle kilka numeracji i dwie różnie nazwane daty, które rzeczywiście potrafią się różnić. Dodatki nie są jednorodną kategorią: obok recapów są komentarze, wywiad i galeria. Osobny wpis OVA nie musi należeć do `specialCount` sezonu.

**AnimeSchedule udostępniło anonimowo wyszukiwanie nazw, relacje i pola harmonogramu**, w tym konkretne przesunięcia japońskiej emisji i angielskiego dubbingu Slime. Nie jest to dziennik wszystkich zmian. Prywatny, dokumentowany interfejs wymaga tokenu aplikacji; anonimowy `/timetables` zwrócił **401** i nie był ponawiany. Wyniki wyszukiwania nie są gwarantowaną listą powiązań: zapytanie o Haibane zwróciło także dwa inne tytuły.

Oznaczenia dowodowe w raporcie:

- **DIRECT** — własny odczyt odpowiedzi, pomiar albo obliczenie z zachowanych danych.
- **REPORTED** — znaczenie lub gwarancja deklarowana w dokumentacji; nie dowód działania wszystkich wariantów live.
- **INFERENCE** — interpretacja danych, rekomendacja lub wniosek o potrzebnym modelu; nie potwierdzony kontrakt dostawcy.

## Kontrakt, zakres i sposób pomiaru

Zlecenie: [pełny brief](../briefs/anime-api-validation.md), część A i wspólne zasady; wymagania [R-04–R-20](workspace/.archive/acquisition/final/spec.md). Jedyny zapis w repo: niniejszy raport w katalogu `reports/` tego workstreamu. Własne skrypty i dowody mieszczą się w nowym katalogu:

```text
C:\Users\MATTYM~1\AppData\Local\Temp\opencode\anime-api-metadata-20260922-a\
```

Dalej nazywany **EVIDENCE**. Długi odpowiednik konta to `C:\Users\MattyMroz\AppData\Local\Temp\opencode\anime-api-metadata-20260922-a\`.

DIRECT: HEAD odpowiadał baseline. Zastane zmiany `AGENTS.md`, `docs/work/acquisition-simplification/` i `docs/work/local-automation-2/` zachowano. Odczytano cały brief, specyfikację i wymagane instrukcje. Badanie wykonano samodzielnie. Wynik nie korzysta z części B. Nie wywoływano Torrentio, nie pobierano mediów ani metainfo, nie uruchamiano qB/Sonarr, nie zmieniano aplikacji, konfiguracji, zależności ani starych raportów. Nie wykonano commitów.

### Budżet i instrument

DIRECT: wykonano **22 próby**, w tym **21 odpowiedzi HTTP i jeden błąd DNS**:

| Gałąź | Liczba prób | Cel |
| --- | ---: | --- |
| `api.ani.zip` | 9 | 6 reprezentatywnych wpisów, 1 nieznany ID, 1 próba `q`, 1 odczyt korzenia w poszukiwaniu dokumentacji |
| `ani.zip` | 1 | Strona projektu; błąd DNS |
| AnimeSchedule | 6 | Dokładnie 2 wyszukiwania anime, 3 strony dokumentacji, 1 próba timetables |
| AniList | 2 | Potwierdzenie ID w jednym zapytaniu oraz relacje Slime po wykryciu luki ani.zip |
| GitHub API | 3 | Ograniczone poszukiwanie dokumentacji ani.zip; brak ustalenia źródła autorytatywnego |
| GitHub raw | 1 | README projektu mapowań Fribb; nie uznano go za kontrakt ani.zip |

`probe.py` używa wyłącznie biblioteki standardowej Python 3.14.2. Żądania były sekwencyjne, z dwusekundową przerwą po każdej próbie, bez powtórek, cachebustingu i równoległego fanoutu. Batch miał najwyżej pięć żądań. Timeout wywołania HTTP: 30 s; guard przed kolejnym żądaniem po 145 s; limit terminala 210 s. Wszystkie rzeczywiste partie zakończyły się znacznie przed 180 s. `urlopen(timeout=30)` jest timeoutem operacji socketu, nie niezależnym twardym deadline całego ciała; nie napotkano powolnego strumieniowania ani timeoutu.

Pomiar `perf_counter` obejmuje `urlopen` i odebranie całego ciała przez `read()`, a więc także zestawienie połączenia widziane przez ten klient. Parsowanie JSON mierzone jest osobno, przed zapisem na dysk. `bytes` to długość odebranego ciała aplikacyjnego, nie wszystkich bajtów TCP/TLS. Żądano `Accept-Encoding: identity`; nie stwierdzono `Content-Encoding` w zachowanych nagłówkach. Wynik wypisywano z `flush=True`, ciało i metadane zamykano po każdej odpowiedzi. Zachowano tylko wybrane bezpieczne nagłówki, bez cookies i credentials.

Każdy plik `NAME.meta.json` zawiera URL, metodę, UTC początku/końca, status, `http_ms`, `json_parse_ms`, liczbę bajtów, SHA256 ciała, bezpieczne nagłówki i SHA256 instrumentu. Nie-JSON ma `.raw.body`; poprawny JSON ma `.raw.json`, nawet gdy MIME to `text/plain`. Dla pustego ciała i HTML `json_parse_ms` mierzy nieudaną próbę parsowania, a nie parsowanie JSON.

Instrument pomiarowy wszystkich prób: `instrument-8d5c98fcb42f.py`, SHA256 `8d5c98fcb42fcf163bdf668fde35748d47fa5b3e3cab66cb75d2c9b885e7df82`. Przed pierwszą próbą HTTP poprawiono lokalny błąd odczytu `Request.method` na `get_method()`; pierwotny snapshot pozostał w EVIDENCE. Nie zmieniło to żadnego pomiaru sieciowego.

**Ograniczenia pomiaru:** pojedynczy klient, pojedynczy odczyt każdego wpisu, brak percentyli i SLA. Nagłówki serwerowe `Date` były około 8–9 sekund wcześniejsze od zegara klienta. Nie korygowano zegarów; monotoniczne czasy HTTP nie zależą od tej różnicy. TTL cache nie mierzy częstotliwości importu danych źródłowych.

### Zachowany checkpoint po pierwszej partii

Po batch1 opublikowano checkpoint w rozmowie i zapisano go w tym pliku przed batch2. Potwierdzał dwa odczyty Slime, ich czasy 193,20/84,83 ms, cache HIT/900 s, potwierdzenie ID przez AniList, błąd DNS `ani.zip` i odczyt dokumentacji AnimeSchedule. Wtedy nie deklarowano kompletnej inwentaryzacji. Niniejszy dokument zastępuje stan roboczy wynikiem końcowym.

## Reprezentatywne przypadki i czasy

DIRECT: ID potwierdzono **przed odczytem ani.zip** przez publiczny katalog `https://graphql.anilist.co` (`catalog.raw.json`, query w `batch1.json`). `search` służył do odkrycia Titan/Haibane/OVA; Slime odczytano po ID z briefu i sprawdzono nazwy. Przyszły wpis wybrano z `NOT_YET_RELEASED`, rok 2027. Nie zgadywano produkcyjnych ID. Wyjątek jest jawny: syntetyczny `999999999` służył tylko do jednego testu błędu.

W tabeli „zwykłe + dodatki” oznacza wartości `episodeCount + specialCount` zgodne w tej próbie z liczbą kluczy liczbowych i `S…`; nie liczbę wydanych plików.

| Przypadek / plik NAME | AniList / Kitsu / AniDB | Zwykłe + dodatki = obiekty | HTTP ms | JSON ms | Bajty | Cache / Age |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Slime S1 / `slime-s1` | 101280 / 41024 / 13871 | 24 + 6 = 30 | 193,20 | 0,1745 | 38 008 | HIT / 43 s |
| Slime S4 / `slime-s4` | 182205 / 49235 / 18884 | 24 + 2 = 26 | 84,83 | 0,1001 | 16 042 | HIT / 24 s |
| Titan Final Season Part 2 / `titan-part2` | 131681 / 44240 / 16177 | 12 + 0 = 12 | 95,22 | 0,0870 | 12 374 | HIT / brak |
| Haibane Renmei / `haibane` | 387 / 354 / 271 | 13 + 3 = 16 | 201,04 | 0,1110 | 20 460 | EXPIRED / brak |
| Slime OVA / `slime-ova` | 106509 / 42022 / 14526 | 5 + 0 = 5 | 102,11 | 0,0656 | 5 823 | HIT / brak |
| Dungeon Meshi 2 / `future-dungeon` | 178031 / 48948 / 18687 | 0 + 0 = 0 | 184,87 | 0,0218 | 901 | EXPIRED / brak |

Wszystkie powyższe: HTTP 200, `Cache-Control: public, max-age=900, s-maxage=900`. Nieobecne `Age` nie oznacza zera. W sześciu odpowiedziach łącznie **78 zwykłych obiektów i 11 specials**, **93 608 bajtów** ciał. Czas HTTP w tej próbie: 84,83–201,04 ms, lecz cztery odpowiedzi były HIT, dwie EXPIRED; to obserwacja, nie prognoza wydajności hurtowej.

Zaokrąglony zakres **85–201 ms dotyczy wyłącznie tych sześciu poprawnych odczytów `/mappings`**, nie wszystkich żądań części A ani całej ścieżki wyszukiwania tytułu.

| Pozostały istotny odczyt | Status | HTTP ms | JSON ms | Bajty | Cache / uwaga |
| --- | ---: | ---: | ---: | ---: | --- |
| `unknown-id` | 404 | 158,12 | 0,0101 | 11 | EXPIRED, TTL 900 s, JSON string `"Not Found"` |
| `anizip-name-probe` | 400 | 127,58 | 0,0134 | 13 | MISS, TTL 60 s, JSON string `"Bad Request"` |
| `anizip-api-docs` | 404 | 116,42 | 0,0143 | 34 | JSON, TTL 900 s; korzeń nie dostarczył dokumentacji |
| `catalog` | 200 | 1 318,12 | 0,0417 | 2 528 | `no-cache, private`; limit 30, remaining 29 |
| `catalog-relations` | 200 | 1 485,65 | 0,0415 | 3 936 | `no-cache, private`; limit 30, remaining 29 |
| `schedule-slime` | 200 | 1 450,27 | 0,2417 | 41 194 | DYNAMIC, brak Cache-Control/Age |
| `schedule-haibane` | 200 | 458,39 | 0,0733 | 10 733 | DYNAMIC, brak Cache-Control/Age |
| `schedule-timetables` | 401 | 188,47 | nie dotyczy | 0 | Stop live tej usługi; bez obchodzenia auth |

Pełne czasy i statusy pozostałych odczytów dokumentacji zawiera `audit.json` oraz wszystkie `.meta.json`. Błąd DNS trwał 174,73 ms, ale **nie jest czasem odpowiedzi HTTP**.

## Co wynika z przypadków ani.zip

### Tożsamość, sezon, franczyza i numeracja

DIRECT: każdy z sześciu odczytów `mappings?anilist_id=…` zwrócił jeden obiekt z sześcioma polami korzenia: `titles`, `episodes`, `episodeCount`, `specialCount`, `images`, `mappings`. Nie było `relations`, listy sezonów, identyfikatora franczyzy, roku/sezonu kalendarzowego ani statusu emisji wpisu. Nie odczytywano listy po TVDB; wspólnego `thetvdb_id` nie uznano za gwarantowany graf relacji.

- **Slime S1E4:** lokalne `episode="4"`, `seasonNumber=1`, `episodeNumber=4`, `absoluteEpisodeNumber=4`, `anidbEid=207932`, `tvdbId=6843179`, tytuł `In the Kingdom of the Dwarves`. To konkretny obiekt, nie sam numer z nazwy pliku.
- **Slime S4E23:** `episode="23"`, `seasonNumber=4`, `episodeNumber=23`, absolute `95`, `anidbEid=315187`; potwierdzono dane wskazane w briefie własnym snapshotem.
- **Titan Part 2:** lokalne odcinki `1–12` odpowiadają TVDB sezonowi 4, odcinkom `17–28`, absolute `76–87`. Pierwszy to `Judgment`. Nie wolno stosować równania „lokalny odcinek 1 = TVDB S4E1”.
- **Slime OVA:** pięć zwykłych kluczy `1–5`, mimo że format to `OVA`. Dwa pierwsze bez pól TVDB; dla lokalnego `4` TVDB podaje sezon 0, odcinek 5. `airedBeforeSeasonNumber=1`, `airedBeforeEpisodeNumber=24` występują dla trzech obiektów, ale nie tworzą kompletnej kolejności oglądania wszystkich dodatków.
- **Wspólne serie:** Slime S1, S4 i OVA dzielą TVDB `352408`, IMDb `tt9054364` i TMDB `"82684"`, mają jednak różne AniList/Kitsu/AniDB. Cztery obrazy tych wpisów też są wspólne. INFERENCE: grafika lub ID serii telewizyjnej nie rozróżniają wybranego sezonu/OVA.

INFERENCE: `seasonNumber` to numer sezonu w numeracji odcinka powiązanego z TVDB, a nie `SPRING/FALL` czy rok emisji. `episode` i klucz obiektu zachowują lokalną numerację wpisu; absolutna numeracja jest dodatkowym, nieuniwersalnym mapowaniem. Źródła poszczególnych pól TVDB/AniDB wnioskujemy z nazw i zgrupowania danych; nie uzyskano autorytatywnej dokumentacji transformacji ani.zip.

### Dodatki jako rzeczywiste obiekty

DIRECT: odczytano wszystkie 11 obiektów o kluczach nieliczbowych, nie tylko `specialCount`:

| Wpis | Klucz | Zawartość / AniDB EID | Dostępna data i ograniczenie |
| --- | --- | --- | --- |
| Slime S1 | `S1` | `Tales: Veldora’s Journal`, 212772; overview opisuje recap | 2019-03-26, TVDB S0E1; to **nie sezon 1** |
| Slime S1 | `S2` | `Advance Screening Stage Greeting`, 228736 | 2018-09-17; 20 minut, brak TVDB |
| Slime S1 | `S3` | `Episode 7 Funimation Video Commentary`, 229951 | 2019-10-01; brak TVDB |
| Slime S1 | `S4` | `Episode 14 Funimation Video Commentary`, 229952 | 2020-02-04; brak TVDB |
| Slime S1 | `S5` | `Sukuwareru Ramiris E01`, 314887 | 2022-03-19; 3 minuty, summary wskazuje krótki film z YouTube |
| Slime S1 | `S6` | `Sukuwareru Ramiris E02`, 314888 | 2022-07-21; 4 minuty |
| Slime S4 | `S2` | `Dai 4 Ki: Kaitai Shinsho!`, 310694 | 2026-05-02; angielski tytuł tylko `Episode S2` |
| Slime S4 | `S1` | `Soushuuhen: Makoku Renbou no Ayumi`, 314294 | 2026-08-01; angielski tytuł tylko `Episode S1` |
| Haibane | `S3` | `Special Ending`, 22851 | 2003-04-25; 6 minut, brak TVDB |
| Haibane | `S1` | `Image Gallery`, 51363 | `airdate=""`; 2 minuty, brak TVDB |
| Haibane | `S2` | `Creators’ Interview`, 111376 | `airdate=""`; 15 minut, brak TVDB |

INFERENCE: `S…` grupuje rozmaite materiały, nie tylko fabularne OVA. Sam tytuł `Special Ending` nie potwierdza, że materiał jest creditless ED; w tej próbie nie było jawnego pola `OP`, `ED`, `creditless`, `recap`, `extraType` ani kluczy `C/T/P`. To **brak w próbce**, a nie twierdzenie o całym API. Nie ustalono semantyki niewidzianych prefiksów.

DIRECT: OVA `106509` ma własne pięć odcinków i `specialCount=0`; nie pojawia się jako te pięć odcinków w dodatkach S1. Dodatki S1 zawierają też materiały z 2022 r., kilka lat po finale sezonu. INFERENCE: „cały sezon + dodatki” nie da się bezpiecznie zamknąć na `episodeCount`, dacie finału albo sześciu wpisach `S…`. Potrzebna jest osobna decyzja o kwalifikacji dodatków i powiązaniu osobnych wpisów; niniejszy raport tej decyzji nie ustanawia.

### Daty, przyszłość i zakończenie

DIRECT: zachowano wielkość liter i oba pola: `airDate` oraz `airdate`. Dla **wszystkich 13 zwykłych odcinków Haibane** pierwsze jest dzień wcześniejsze, np. `2002-10-09` wobec `2002-10-10`; nie ma `airDateUtc`. Dla **Slime OVA E3** jest `airDate=2020-03-07`, `airdate=2020-03-27` — różnica 20 dni, której nie wyjaśnia strefa czasowa. Powód i poprawna data nie zostały rozstrzygnięte.

DIRECT: Titan E1 ma `airDate=2022-01-10`, `airDateUtc=2022-01-09T15:30:00Z`, `airdate=2022-01-10`. INFERENCE: data kalendarzowa bez strefy nie powinna być mechanicznie utożsamiana z dniem UTC. Nazwy oraz obecność identyfikatorów sugerują połączenie dat TVDB i AniDB, ale sam JSON nie zawiera jawnego provenance każdej daty.

DIRECT: przyszły względem odczytu **Slime S4E24** już istniał w odpowiedzi: `anidbEid=315188`, TVDB `11696762`, absolute 96, tytuł `The Hero Awakens`, `airDate=airdate=2026-09-25`, `airDateUtc=2026-09-25T14:00:00Z`. Brak `image`, `overview`, `rating`, `summary`. Nie wykonano dodatkowego HTTP dla tego odcinka. INFERENCE: istnienie obiektu i numeru nie dowodzi publikacji; to planowana informacja w momencie badania.

DIRECT: `finaleType` wystąpiło cztery razy: Slime S1 E24 `season`, Slime S4 E24 `midseason`, Titan Part 2 E12 `midseason`, Haibane E13 `series`. INFERENCE: nawet jawny marker końca części/sezonu nie oznacza końca franczyzy ani dostępności ostatniego wydania.

DIRECT: przyszły Dungeon Meshi 2 (`178031`) miał mapowania, tytuły i cztery obrazy, ale `episodes={}`, `episodeCount=0`, `specialCount=0`. AniList w tym samym badaniu wskazał `NOT_YET_RELEASED`, `FALL`, `2027`, format `ONA`; ani.zip podało `mappings.type="TV"`. To konflikt klasyfikacji i niekompletna lista przyszłych odcinków, nie „serial bez odcinków” ani potwierdzony termin premiery. Nie sprawdzano zapowiedzi wydawcy.

### Wyszukiwanie i błędy

DIRECT: `mappings?anilist_id=…` działa dla sześciu potwierdzonych ID. `mappings?q=Haibane%20Renmei` zwróciło 400/`"Bad Request"`; `anilist_id=999999999` zwróciło 404/`"Not Found"`. Błędny/nieznany ID nie jest tu poprawną pustą listą. Przyszły znany ID daje natomiast HTTP 200 i puste `episodes`.

DIRECT — inventory odpowiedzi błędów poza schematem 200: korzeń `api.ani.zip/` zwrócił obiekt `{"status":404,"error":"Not Found"}`: `status` integer i `error` string, oba obecne, nie-null. Dwa błędy `/mappings` były natomiast skalarnymi JSON stringami, bez pól. Nie można zakładać jednego formatu błędu dla wszystkich ścieżek.

INFERENCE: dla zweryfikowanej ścieżki trzeba najpierw uzyskać ID z katalogu. Nie potwierdzono nazwanego endpointu wyszukiwania ani.zip; jedna próba `q` nie dowodzi nieistnienia innej ścieżki wyszukiwania. Nie testowano pozostałych parametrów ID, list po TVDB ani obsługi wielu ID naraz.

## Pełna inwentaryzacja ani.zip

DIRECT: poniższe tabele pokrywają wszystkie **74 znormalizowane ścieżki** napotkane w sześciu odpowiedziach 200. Znormalizowano tylko dynamiczny klucz `episodes.*`; zachowano wszystkie klucze językowe. Liczba „brak” dotyczy istniejących obiektów rodzica. Wszystkie obecne wartości są nie-null z jedynym wyjątkiem `mappings.notifymoe_id`. Zero braków w próbce nie jest gwarancją wymagalności pola.

Definicja inventory wynika z `inspect.py:walk`, użytego też przez `offline.py`: liczymy ścieżki kluczy obiektów, w tym pola obiektów wewnątrz tablic, np. `images[].url`. Nie liczymy osobno samych elementów tablic, np. `images[]`, ani ich indeksów. Ta sama konwencja dotyczy 91 ścieżek AnimeSchedule; liczby 74 i 91 nie są liczbą wszystkich węzłów JSON.

Pełne liczniki i nieucięte przykłady: `mapping-inventory.json`. Wszystkie oryginalne wartości: sześć `.raw.json`; czytelne pełne kopie `.pretty.json`; przypadki i obiekty specjalne: `mapping-summary.json`. Typy poniżej to JSON: obiekt, tablica, string, integer, null.

### Korzeń i obrazy

| Ścieżka | Typ | Obecne / rodzice; null; brak | Przykład | Znaczenie i siła |
| --- | --- | --- | --- | --- |
| `titles` | obiekt | 6/6; 0; 0 | `en`, `ja`, `x-jat` | DIRECT mapa tytułów; INFERENCE etykiety językowe |
| `episodes` | obiekt | 6/6; 0; 0 | klucze `1`, `S1`; także `{}` | DIRECT mapa odcinków; pusta raz |
| `episodes.*` | obiekt | 89 obiektów / 6 map; 0; nie dotyczy | `episode="4"` | Dynamiczny klucz, nie jeden wymagany klucz schematu |
| `episodeCount` | integer | 6/6; 0; 0 | 24, 0 | DIRECT w tej próbie liczba kluczy liczbowych; nie dowód emisji |
| `specialCount` | integer | 6/6; 0; 0 | 6, 3, 0 | DIRECT w tej próbie liczba kluczy `S…` |
| `images` | tablica obiektów | 6/6; 0; 0 | 4 obrazy na wpis | DIRECT 24 elementy, żadnej pustej tablicy |
| `images[].coverType` | string | 24/24; 0; 0 | `Banner`, `Poster`, `Fanart`, `Clearlogo` | DIRECT wszystkie cztery zaobserwowane wartości |
| `images[].url` | string | 24/24; 0; 0 | `https://artworks.thetvdb.com/banners/graphical/79105-g.jpg` | URL; obrazów nie pobierano |
| `mappings` | obiekt | 6/6; 0; 0 | poniższe 12 pól | DIRECT identyfikatory i typ |

### Wszystkie pola `mappings`

Każde pole obecne 6/6, brak 0. Poza wskazanym `null` wszystkie wartości nie-null. Znaczenie identyfikatorów jest **INFERENCE z nazw i zgodności katalogu**, nie uzyskanym formalnym schematem ani.zip.

| Pole | Typ | Przykład | Znaczenie / ograniczenie |
| --- | --- | --- | --- |
| `animeplanet_id` | string | `haibane-renmei` | Slug Anime-Planet, nie liczba |
| `kitsu_id` | integer | 41024 | ID Kitsu; rozróżnia wpisy Slime |
| `mal_id` | integer | 37430 | ID MyAnimeList |
| `type` | string | `TV`, `OVA` | Wszystkie wartości z próby; konflikt `TV`/AniList `ONA` dla przyszłego wpisu |
| `anilist_id` | integer | 101280 | ID AniList, zgodne z wejściem wszystkich sześciu odczytów |
| `anisearch_id` | integer | 13436 | ID aniSearch |
| `anidb_id` | integer | 13871 | ID anime AniDB, odrębne od odcinkowego `anidbEid` |
| `notifymoe_id` | null | `null` | Null **6/6**; nie potwierdzono typu niepustej wartości |
| `livechart_id` | integer | 3132 | ID LiveChart |
| `thetvdb_id` | integer | 352408 | ID wspólnej serii; nie numer sezonu |
| `imdb_id` | string | `tt9054364` | ID IMDb; wspólne dla kilku wpisów |
| `themoviedb_id` | string | `"82684"` | String mimo cyfr; nie badano przestrzeni TV/movie ani wielokrotnych mapowań |

### Wszystkie pola obiektu `episodes.*`

Rodziców: **89**. Null: **0 dla każdego pola**. Nieuzyskany formalny kontrakt ani.zip oznacza, że semantyka źródła poniżej ma klasę INFERENCE; obecność, typ i przykład — DIRECT.

| Pole | Typ | Obecne / brak | Przykład | Znaczenie / ograniczenie |
| --- | --- | ---: | --- | --- |
| `tvdbShowId` | integer | 77 / 12 | 352408 | Powiązana seria TVDB |
| `tvdbId` | integer | 77 / 12 | 6843179 | Powiązany odcinek TVDB |
| `seasonNumber` | integer | 77 / 12 | 0, 1, 4 | Numer sezonu TVDB, 0 dla części dodatków |
| `episodeNumber` | integer | 77 / 12 | 17 | Numer w sezonie TVDB; może różnić się od klucza |
| `absoluteEpisodeNumber` | integer | 73 / 16 | 76, 95 | Numer absolutny; brak m.in. w OVA/specials |
| `title` | obiekt | 89 / 0 | `en: Judgment` | Mapa tytułów; czasem tylko placeholder |
| `airDate` | string | 77 / 12 | `2002-10-09` | Data z części TVDB, bez strefy; nie scalać z `airdate` |
| `airDateUtc` | string | 64 / 25 | `2022-01-09T15:30:00Z` | Timestamp UTC z części TVDB; brak dla całego Haibane |
| `runtime` | integer | 77 / 12 | 24 | Czas trwania z części TVDB; interpretacja minut |
| `overview` | string | 76 / 13 | opis spotkania Rimuru z Veldorą | Opis z części TVDB |
| `image` | string | 76 / 13 | `https://artworks.thetvdb.com/banners/episodes/352408/6843179.jpg` | Kadr odcinka, nie obraz sezonu |
| `episode` | string | 89 / 0 | `"1"`, `"S1"` | Zgodny z kluczem wszystkich 89 obiektów; nie rzutować bezwarunkowo na integer |
| `anidbEid` | integer | 89 / 0 | 315187 | Identyfikator odcinka AniDB |
| `length` | integer | 89 / 0 | 25, 2 | Czas trwania z części AniDB; różni się od `runtime` |
| `airdate` | string | 89 / 0 | `2002-10-10`, `""` | Data z części AniDB; dwa puste stringi (Haibane S1/S2) |
| `rating` | string | 82 / 7 | `"7.95"`, `"10.00"` | Ocena, nie JSON number; brak liczby głosów i gwarancji jakości |
| `summary` | string | 59 / 30 | opis z końcówką `Source: crunchyroll` | Drugi opis; brak nie jest pustym `overview` |
| `finaleType` | string | 4 / 85 | `season`, `midseason`, `series` | Marker finału o różnych zakresach |
| `airedBeforeSeasonNumber` | integer | 3 / 86 | 1 | Wskazanie umieszczenia dodatku przed sezonem |
| `airedBeforeEpisodeNumber` | integer | 3 / 86 | 24 | Wskazanie odcinka; dotyczy tylko części OVA |

### Wszystkie klucze tytułów

DIRECT — drobna pułapka tekstowa: `titles.pl` Slime S1 kończy się znakiem U+3164 (HANGUL FILLER), widocznym w raw jako `Odrodzony jako galaretaㅤ`. Wygląda jak odstęp, ale nie jest zwykłą spacją U+0020. Może wpływać na porównywanie i prezentację tytułu; surowej wartości nie zmieniono.

Każda poniższa wartość to **string**, null 0, pustych stringów nie zaobserwowano. Znaczenie etykiet językowych i `x-jat` jako romanizacji jest INFERENCE, nie gwarancja kompletności aliasów. `titles.x-jat="tensura"`/`"snk5"` pokazuje, że wybrany tytuł może być skrótem. Wartości nie są tablicami wszystkich synonimów danego języka. Tytuły w obcym języku nie dowodzą istnienia napisów ani audio w tym języku.

| Pole pod `titles` | Obecne / 6; brak | Przykład |
| --- | --- | --- |
| `ar` | 1; 5 | الهجوم على العمالقة: الجزء الاخير (2022) |
| `bg` | 1; 5 | Съюзът на Среброкрилите |
| `de` | 5; 1 | Haibane Renmei - Ailes Grises |
| `en` | 6; 0 | Delicious in Dungeon Season 2 |
| `es` | 1; 5 | La Federación de las Plumas de Carbón |
| `es-CA` | 1; 5 | Ales Grises |
| `fa` | 1; 5 | بال گچی ها |
| `fr` | 4; 2 | Ailes Grises |
| `id` | 1; 5 | Bereinkarnasi Malah Menjadi Slime |
| `it` | 2; 4 | Ali Grigie |
| `ja` | 6; 0 | ダンジョン飯 Season2 |
| `ko` | 4; 2 | 회색 날개의 연맹 |
| `pl` | 3; 3 | Haibane renmei: Stowarzyszenie szaropiórych |
| `ru` | 3; 3 | Союз Серокрылых |
| `th` | 2; 4 | เกิดใหม่ทั้งทีก็เป็นสไลม์ไปซะแล้ว |
| `tr` | 1; 5 | Bu Kez Şlam Olarak Yeniden Dünyaya Geldim |
| `uk` | 2; 4 | Союз сірокрилих |
| `x-jat` | 6; 0 | Dungeon Meshi Season 2 |
| `zh` | 1; 5 | 灰羽連盟 |
| `zh-Hans` | 4; 2 | 灰羽联盟 |
| `zh-Hant` | 2; 4 | 關於我轉生變成史萊姆這檔事 |

| Pole pod `episodes.*.title` | Obecne / 89; brak | Przykład |
| --- | --- | --- |
| `de` | 70; 19 | Sturmdrache Veldora |
| `en` | 89; 0 | Judgment |
| `es` | 40; 49 | Extra: ¿La tragedia de M? |
| `fr` | 55; 34 | Cocon - Tomber du ciel - Vieille maison |
| `hu` | 4; 85 | Újabb hétköznapok |
| `ja` | 84; 5 | 繭・空を落ちる夢・オールドホーム |
| `ko` | 3; 86 | 외전 : M의 비극? |
| `pl` | 13; 76 | Kokon; Sen o spadaniu; Stary dom |
| `ru` | 13; 76 | Кокон — Сон о падении с неба — Старый Дом |
| `tr` | 17; 72 | Fırtına Ejderi Veldora |
| `uk` | 1; 88 | Нові дні |
| `x-jat` | 84; 5 | Mayu - Sora o Ochiru Yume - Old Home |

## AnimeSchedule: co rzeczywiście zwrócono

DIRECT: dwa wywołania `/api/v3/anime?q=…` zwróciły łącznie **14 obiektów anime** i **91 znormalizowanych ścieżek pól**. Slime: `page=1`, `totalAmount=11`, 11 elementów. Haibane: `page=1`, `totalAmount=3`, 3 elementy. W tej próbie liczba elementów zgadzała się z totalAmount; nie testowano następnych stron ani limitu wyników. Nie należy uważać tej zgodności za dowód kompletności franczyzy.

DIRECT: poza Haibane wyszukiwarka zwróciła `Tsuihou sareta Cheat Fuyo Majutsushi…` i `Yuusha ni Narenakatta Ore wa… OVA`. INFERENCE: dopasowanie tekstowe wymaga weryfikacji tożsamości; `totalAmount` nie znaczy „tyle części tej serii”.

### Przesunięcia i czas

DIRECT: w obiekcie Slime S4 (`id=zNmQ`) było:

| Pole | Wartość |
| --- | --- |
| `status` | `Ongoing` |
| `premier` | `2026-04-03T00:00:00Z` |
| `subPremier` | `0001-01-01T00:00:00Z` |
| `dubPremier` | `2026-04-17T00:00:00Z` |
| `delayedTimetable` | `Delayed` |
| `delayedFrom` → `delayedUntil` | `2026-07-31T00:00:00Z` → `2026-08-07T00:00:00Z` |
| `dubDelayedTimetable` | `Delayed` |
| `dubDelayedFrom` → `dubDelayedUntil` | `2026-08-14T00:00:00Z` → `2026-08-21T00:00:00Z` |
| `subDelayedFrom`, `subDelayedUntil` | obie wartości sentinel `0001-01-01T00:00:00Z` |
| `jpnTime`, `subTime`, `dubTime` | odpowiednio godziny `14:00`, `15:00`, `15:00` z pełnych stringów daty |
| `updatedAt` | `2026-09-22T15:16:45.322Z` |

REPORTED: dokumentacja określa `premier` jako pierwszą emisję japońską, `subPremier`/`dubPremier` jako pierwsze **angielskie** sub/dub; nie wszystkie języki. Dla `jpnTime`, `subTime`, `dubTime` istotne są **tylko godzina i minuta**. Dlatego `jpnTime=2026-08-17T14:00:00Z` nie oznacza kolejnej emisji 17 sierpnia. `0001-01-01T00:00:00Z` jest udokumentowanym odpowiednikiem daty null, mimo typu string i braku JSON null.

DIRECT: wszystkie 42 obiekty override (14 anime × raw/sub/dub) miały `overrideDate` równą sentinelowi i oba liczniki 0. REPORTED: `episodesAired` to **liczba odcinków wyemitowanych w dacie override minus jeden**, a nie liczba wyemitowanych w całej serii. Nie testowano niezerowego override live.

DIRECT: pola przesunięć raw/dub wystąpiły niepuste także w zakończonym Slime S3 z datami 2024 r. Odpowiedź nie miała tablicy historii, poprzednich wartości, powodu każdej zmiany ani numeru odcinka dla każdego przesunięcia. `updatedAt` jest jednym timestampem obiektu. INFERENCE: to snapshot aktualnie przechowywanych danych, mogący zachować starsze przesunięcie, **nie event log i nie samodzielny sygnał „teraz opóźnione”**. Historia zmian wymagałaby innego źródła lub własnych kolejnych snapshotów; nie budowano takiego mechanizmu.

### Pełny inventory wyszukiwania AnimeSchedule

Wszystkie obecne wartości w tych dwóch odpowiedziach miały **JSON null=0 i pustych stringów/tablic/obiektów=0**. Sentinele dat są liczone osobno. Skrót `A` oznacza `$.anime[]`. Każde wymienione osobno pole w wierszu grupowym ma wskazany typ i licznik. Typy oraz liczniki są DIRECT. Znaczenie jest **REPORTED z dokumentacji Anime/Category/Season/Stats/Names/Relations/Websites**, chyba że oznaczono **I** (INFERENCE). Dokumentacja dotyczy interfejsu z tokenem; faktyczny typ anonimowego wyniku ma pierwszeństwo przy opisie próbki.

REPORTED — `schedule-docs.raw.txt:69–82`: pola o wartości null są w wielu przypadkach pomijane, ale nie jest to gwarancja; datetime stanowi wskazany wyjątek z wartością `0001-01-01T00:00:00Z`. Dlatego zero jawnych null w próbce nie oznacza kompletnych danych. Brak pola, JSON null, sentinel daty i liczba 0 wymagają odrębnej interpretacji zależnej od pola.

| Ścieżka | Typ | Obecne / rodzice; brak | Przykład i znaczenie |
| --- | --- | --- | --- |
| `$.page` | integer | 2/2; 0 | 1, bieżąca strona |
| `$.totalAmount` | integer | 2/2; 0 | 11, 3; total wyników, nie relacji |
| `$.anime` | tablica obiektów | 2/2; 0 | 11 i 3 elementy |
| `A.id` | string | 14/14; 0 | `mA78`, unikalne ID |
| `A.title` | string | 14/14; 0 | `Tensei shitara Slime Datta Ken`, tytuł prezentacyjny |
| `A.route` | string | 14/14; 0 | `haibane-renmei`, slug |
| `A.premier` | string daty | 14/14; 0 | `2002-10-09T17:28:00Z`, pierwsza emisja JP |
| `A.subPremier` | string daty | 14/14; 0 | sentinel; pierwsza emisja EN sub |
| `A.dubPremier` | string daty | 14/14; 0 | `2026-04-17T00:00:00Z`, pierwsza emisja EN dub |
| `A.month` | string | 14/14; 0 | `October`, najwcześniejszy miesiąc premiery |
| `A.year` | integer | 14/14; 0 | 2018, najwcześniejszy rok premiery |
| `A.season` | obiekt | 14/14; 0 | sezon kalendarzowy |
| `A.season.title` | string | 14/14; 0 | `Fall 2018`, etykieta |
| `A.season.year` | **string** | 14/14; 0 | `"2018"`; dokumentacja podaje int — realny rozjazd |
| `A.season.season` | string | 14/14; 0 | `Fall`, pora roku, nie sezon serialu |
| `A.season.route` | string | 14/14; 0 | `fall-2018`, slug sezonu kalendarzowego |
| `A.episodeOverride` | obiekt | 14/14; 0 | override emisji JP |
| `A.episodeOverride.overrideDate` | string daty | 14/14; 0 | sentinel 14/14; data odstępstwa |
| `A.episodeOverride.overrideEpisode` | integer | 14/14; 0 | 0, numer w dacie override |
| `A.episodeOverride.episodesAired` | integer | 14/14; 0 | 0, liczba w dacie override minus 1 |
| `A.subEpisodeOverride` | obiekt | 14/14; 0 | override EN sub |
| `A.subEpisodeOverride.overrideDate` | string daty | 14/14; 0 | sentinel 14/14 |
| `A.subEpisodeOverride.overrideEpisode` | integer | 14/14; 0 | 0 |
| `A.subEpisodeOverride.episodesAired` | integer | 14/14; 0 | 0, semantyka jak raw |
| `A.dubEpisodeOverride` | obiekt | 14/14; 0 | override EN dub |
| `A.dubEpisodeOverride.overrideDate` | string daty | 14/14; 0 | sentinel 14/14 |
| `A.dubEpisodeOverride.overrideEpisode` | integer | 14/14; 0 | 0 |
| `A.dubEpisodeOverride.episodesAired` | integer | 14/14; 0 | 0, semantyka jak raw |
| `A.delayedTimetable` | string | 2/14; 12 | `Delayed`, tekst dla raw |
| `A.delayedFrom` | string daty | 14/14; 0 | `2026-07-31T00:00:00Z`, przesunięcie od |
| `A.delayedUntil` | string daty | 14/14; 0 | `2026-08-07T00:00:00Z`, przesunięcie do |
| `A.subDelayedFrom` | string daty | 14/14; 0 | sentinel, przesunięcie EN sub od |
| `A.subDelayedUntil` | string daty | 14/14; 0 | sentinel, przesunięcie EN sub do |
| `A.dubDelayedTimetable` | string | 2/14; 12 | `Delayed`, tekst dla dubbingu |
| `A.dubDelayedFrom` | string daty | 14/14; 0 | `2026-08-14T00:00:00Z` |
| `A.dubDelayedUntil` | string daty | 14/14; 0 | `2026-08-21T00:00:00Z` |
| `A.jpnTime` | string daty | 14/14; 0 | `0002-01-01T15:00:00Z`; tylko HH:mm ma znaczenie |
| `A.subTime` | string daty | 14/14; 0 | `2023-04-06T15:01:00Z`; tylko HH:mm EN sub |
| `A.dubTime` | string daty | 14/14; 0 | `2023-04-06T15:01:00Z`; tylko HH:mm EN dub |
| `A.description` | string HTML | 14/14; 0 | opis Slime z `<br>`; nie plain text |
| `A.genres` | tablica obiektów | 14/14; 0 | gatunki, 88 elementów łącznie |
| `A.genres[].name` | string | 88/88; 0 | `Action` |
| `A.genres[].route` | string | 88/88; 0 | `action` |
| `A.studios` | tablica obiektów | 14/14; 0 | studia, 14 elementów |
| `A.studios[].name` | string | 14/14; 0 | `8bit` |
| `A.studios[].route` | string | 14/14; 0 | `8bit` |
| `A.sources` | tablica obiektów | 14/14; 0 | rodzaj pierwowzoru, **nie źródła plików** |
| `A.sources[].name` | string | 14/14; 0 | `Light Novel`, `Manga`, `Doujinshi` |
| `A.sources[].route` | string | 14/14; 0 | `light-novel` |
| `A.mediaTypes` | tablica obiektów | 14/14; 0 | format dzieła |
| `A.mediaTypes[].name` | string | 14/14; 0 | `TV`, `OVA`, `Movie` |
| `A.mediaTypes[].route` | string | 14/14; 0 | `tv`, `ova`, `movie` |
| `A.episodes` | integer | 13/14; 1 | 24, liczba odcinków, nie lista |
| `A.lengthMin` | integer | 13/14; 1 | 23, długość odcinka w minutach |
| `A.status` | string | 14/14; 0 | `Finished`, `Ongoing`, `Upcoming` |
| `A.createdAt` | string daty | 14/14; 0 | `2024-07-19T10:23:54.877Z`, utworzenie danych |
| `A.updatedAt` | string daty | 14/14; 0 | `2026-09-22T15:16:45.322Z`, aktualizacja obiektu |
| `A.imageVersionRoute` | string | 14/14; 0 | `anime/jpg/default/haibane-renmei-493047098a.jpg`, ścieżka CDN |
| `A.posterDominantColor` | string | 14/14; 0 | `86 85 109`; **I:** składowe dominującego koloru plakatu |
| `A.stats` | obiekt | 14/14; 0 | statystyki ocen/list |
| `A.stats.averageScore` | number (float/integer) | 14/14; 0 | 82,90874481201172; także 0; ocena ważona, nie jakość wydania |
| `A.stats.ratingCount` | integer | 14/14; 0 | 859, liczba ocen |
| `A.stats.trackedCount` | integer | 14/14; 0 | 2398, liczba list użytkowników |
| `A.stats.droppedCount` | integer | 14/14; 0 | 33, liczba porzuceń |
| `A.stats.trackedRating` | integer | 14/14; 0 | 25, pozycja popularności, nie ocena 25/100 |
| `A.stats.colorLightMode` | string | 14/14; 0 | `316E3A`, kolor HEX oceny |
| `A.stats.colorDarkMode` | string | 14/14; 0 | `4FB25D`, kolor HEX oceny |
| `A.names` | obiekt | 14/14; 0 | warianty nazw |
| `A.names.romaji` | string | 13/14; 1 | `Tensei Shitara Slime Datta Ken` |
| `A.names.english` | string | 13/14; 1 | `That Time I Got Reincarnated as a Slime` |
| `A.names.native` | string | 14/14; 0 | `転生したらスライムだった件` |
| `A.names.abbreviation` | string | 9/14; 5 | `TenSura` |
| `A.names.synonyms` | tablica stringów | 13/14; 1 | `Vita da Slime`, `転スラ` |
| `A.relations` | obiekt | 12/14; 2 | typowane relacje do slugów |
| `A.relations.sequels` | tablica stringów | 5/12; 7 | `tensei-shitara-slime-datta-ken-2nd-season` |
| `A.relations.prequels` | tablica stringów | 6/12; 6 | `tensei-shitara-slime-datta-ken-coleus-no-yume` |
| `A.relations.parents` | tablica stringów | 6/12; 6 | `tensei-shitara-slime-datta-ken` |
| `A.relations.other` | tablica stringów | 1/12; 11 | `genjitsu-no-rimuru-sunshine-in-the-slime` |
| `A.relations.sideStories` | tablica stringów | 3/12; 9 | `tensei-shitara-slime-datta-ken-ova` |
| `A.relations.spinoffs` | tablica stringów | 1/12; 11 | `tensura-nikki-tensei-shitara-slime-datta-ken` |
| `A.websites` | obiekt | 14/14; 0 | URL-e, często bez schematu `https://` |
| `A.websites.official` | string | 14/14; 0 | `www.ten-sura.com/` |
| `A.websites.mal` | string | 14/14; 0 | `myanimelist.net/anime/37430/Tensei_shitara_Slime_Datta_Ken` |
| `A.websites.aniList` | string | 14/14; 0 | `anilist.co/anime/101280/Tensei-Shitara-Slime-Datta-Ken/` |
| `A.websites.kitsu` | string | 13/14; 1 | `kitsu.io/anime/354`; są też slugi i domena `kitsu.app` |
| `A.websites.animePlanet` | string | 12/14; 2 | `www.anime-planet.com/anime/that-time-i-got-reincarnated-as-a-slime` |
| `A.websites.anidb` | string | 12/14; 2 | `anidb.net/anime/13871` |
| `A.websites.streams` | tablica obiektów | 12/14; 2 | 49 linków; nie wydania odcinków |
| `A.websites.streams[].platform` | string | 49/49; 0 | `apple`, `crunchyroll`, `netflix` |
| `A.websites.streams[].url` | string | 49/49; 0 | `apple.co/3L761v9` |
| `A.websites.streams[].name` | string | 49/49; 0 | `Apple TV`, etykieta linku |

Liczby dat-sentineli w 14 obiektach (DIRECT): `premier` 0; `subPremier` 12; `dubPremier` 8; `delayedFrom`/`delayedUntil` po 12; `subDelayedFrom`/`subDelayedUntil` po 14; `dubDelayedFrom`/`dubDelayedUntil` po 12; `jpnTime` 4; `subTime` i `dubTime` po 2. Niezerowe `jpnTime` z rokiem 0002 nie jest datą premiery — dokumentacja ogranicza znaczenie do godziny/minuty.

DIRECT: nie napotkano `subDelayedTimetable`, `delayedDesc`, `notes`, `days` ani `relations.alternatives`. REPORTED: dokumentacja je przewiduje; `days` ma pola bool `monday`–`sunday` przy wielu emisjach tygodniowo. Nie dopisano tych pól do inventory live. Nie znaleziono w payloadach listy wszystkich odcinków z osobnymi tytułami, absolute ani identyfikatorami AniDB EID; liczba `episodes` tego nie zastępuje.

### Timetables, auth i ograniczenia utrzymania

REPORTED — `schedule-anime-docs.raw.txt:491–557,744–767`: dokumentowany interfejs przewiduje `GET /anime/{slug}` oraz filtrowanie `GET /anime` po `anilist-ids`, `mal-ids` i `anidb-ids`, z powtórzeniem parametru dla wielu ID. `q` ma maksymalnie 200 znaków; `mt` wybiera dopasowanie `any` lub `all` (domyślnie `all`), a `st` sortowanie `popularity`, `score`, `alphabetic`, `releaseDate` lub `createdAt` (domyślnie `popularity`). Strona ma najwyżej 18 wpisów. To możliwości udokumentowane, **nie zbadane live** w tych wariantach; dwa anonimowe wyszukiwania po nazwie nie potwierdzają tego kontraktu ani jego limitów dla anonimowego endpointu.

REPORTED: [dokumentacja główna](https://animeschedule.net/api/v3/documentation) wymaga konta i aplikacji oraz `Authorization: Bearer …`. Publiczne endpointy bez tokenu są opisane jako wewnętrzne, niedokumentowane i z bardziej restrykcyjnymi limitami. [Dokumentacja limitów](https://animeschedule.net/api/v3/documentation/ratelimits) podaje globalnie 120 żądań/min, limit IP i aplikacji, możliwość zmiany limitu oraz nagłówki `X-RateLimit-*`. **Nie przenosimy 120/min na anonimowe wyszukiwanie**: nie otrzymano takich nagłówków w jego dwóch odpowiedziach.

DIRECT: `GET https://animeschedule.net/api/v3/timetables` bez tokenu zwrócił **401, puste ciało**, nie listę emisji. Instrument zablokował kolejne live tej usługi; nie tworzono konta, nie próbowano innych wariantów auth ani obejścia.

REPORTED, **nie potwierdzone live**: `/timetables` i `/timetables/{airType}` zwracają tydzień emisji, obsługują `raw`, `sub`, `dub`, `all`, a `year` i `week` wymagają się wzajemnie. Parametr `tz` domyślnie ma `Europe/London` i uwzględnia DST; dokumentacja ogólna mówi o UTC, ale ta sekcja podaje szczególny domyślny tryb timetables. Dokument nazywa identyfikator strefy „IATA”, choć przykłady są typu `Asia/Tokyo`/`America/New_York`; nie sprawdzano walidacji.

Dokumentowany obiekt **Timetable Anime** zawiera: stringi `title`, `route`, `romaji`, `english`, `native`, `delayedText`, `status`, `airType`, `imageVersionRoute`, `airingStatus`; daty `delayedFrom`, `delayedUntil`, `episodeDate`; integer `episodeNumber`, `subtractedEpisodeNumber`, `episodes`, `lengthMin`; bool `donghua`; `mediaTypes` jako tablicę kategorii; `streams` jako strukturę streamów. `episodes=0` oznacza nieznane; `subtractedEpisodeNumber` jest dolną granicą jednoczesnej paczki emisji. `airingStatus` ma przykłady `airing`, `aired`, `unaired`, `delayed-air`. Tryb sub może użyć raw, gdy brak sub. Żadnego z tych zachowań nie nazwano pomyślnym testem timetables.

REPORTED: wprowadzenie dokumentacji wymaga widocznego linku/atrybucji AnimeSchedule, poszanowania limitów, ograniczonego potrzebą cache oraz kontaktu przed zastosowaniem komercyjnym. To koszt wyboru dostawcy, nie wynik audytu prawnego. Brak Cache-Control w anonimowych odpowiedziach nie jest zgodą na bezterminowe przechowywanie ani dowodem braku wewnętrznego cache.

REPORTED — dokładna klauzula z `schedule-docs.raw.txt:51`: **„Cache API data only as needed and do not use it to train AI or machine learning models”.** Dotyczy ograniczenia cache i zakazu używania danych API do trenowania modeli. Sama ta klauzula nie jest zakazem inferencji LLM ani TTS; nie wyprowadzamy z niej też pełnej oceny dopuszczalności konkretnego zastosowania.

## AniList jako minimalne uzupełnienie relacji

DIRECT: dodatkowy odczyt wykonano dopiero po stwierdzeniu, że ani.zip nie zwraca relacji. `catalog-relations.raw.json` dla Slime S1 zawiera **9 krawędzi**: `SIDE_STORY` ×2, `SOURCE` ×2, `SPIN_OFF` ×1, `CHARACTER` ×3, `SEQUEL` ×1. `SIDE_STORY` wskazuje OVA `106509` i Ramiris `146503`; `SPIN_OFF` wskazuje Tensura Nikki `116741`. `SOURCE` prowadzi do noweli/mangi, nie do odcinków anime.

**Istotna rozbieżność DIRECT:** AniList dla S1 podaje `SEQUEL → Coleus no Yume (161802, OVA, 2023)`, podczas gdy AnimeSchedule S1 ma `sequels → 2nd-season`. INFERENCE: relacja sequel nie musi oznaczać „następny numerowany sezon TV”. Nie wolno użyć pierwszej krawędzi jako kompletnej kolejności sezonów ani mieszać krawędzi źródłowych, pobocznych i kontynuacji. Nie rozwijano rekurencyjnie całego grafu; badanie nie dowodzi pełnej kolejności franczyzy.

Inventory wszystkich wybranych pól katalogu (DIRECT; GraphQL zwraca pola zamówione w query, więc to nie pełny schemat AniList):

| Ścieżka / grupa | Typ i przykład | Null / brak oraz znaczenie |
| --- | --- | --- |
| `data` | obiekt | obecny w obu odpowiedziach; brak `errors` |
| `data.s1`, `s4`, `titan`, `haibane`, `ova` | obiekty Media | aliasy query, nie nazwy pól schematu |
| `data.future`, `.media` | obiekt Page, tablica 3 Media | wynik filtra przyszłych wpisów |
| `data.Media` | obiekt Slime S1 | wynik drugiego query |
| Media: `id` | integer, 101280 | obecne i nie-null we wszystkich wybranych obiektach |
| Media: `title` | obiekt | `romaji`, `english`, `native` |
| `title.romaji`, `title.native` | string | obecne i nie-null w próbie |
| `title.english` | string/null | np. `That Time I Got Reincarnated as a Slime`; null m.in. przy pobocznych wpisach |
| Media: `format` | string, `TV`, `OVA`, `ONA`, `MANGA`, `NOVEL` | obecny w query; nie-null w próbie |
| Media: `status` | string, `FINISHED`, `RELEASING`, `NOT_YET_RELEASED` | status katalogu, nie wydania pliku |
| Media: `season` | string/null, `FALL` | null dla dwóch węzłów SOURCE typu MANGA |
| Media: `seasonYear` | integer/null, 2018 | null dla dwóch węzłów SOURCE |
| Media: `siteUrl` | string, `https://anilist.co/anime/101280` | zamówiono w batch1 i węzłach relacji; brak w drugim root Media, bo nie zamówiono |
| `Media.startDate`, `Media.endDate` | obiekty | tylko drugie query |
| `startDate.year`, `.month`, `.day` | integer: 2018, 10, 2 | nie-null; pola wybrane dla Slime S1 |
| `endDate.year`, `.month`, `.day` | integer: 2019, 3, 19 | nie-null; brak strefy |
| `Media.episodes` | integer, 24 | tylko drugie query, nie-null |
| `Media.relations`, `.edges` | obiekt, tablica 9 krawędzi | tylko drugie query |
| `edges[].relationType` | string, `SIDE_STORY` | wszystkie pięć napotkanych kategorii opisano wyżej |
| `edges[].node` | obiekt Media | powtarza wybrane pola Media |
| `node.type` | string, `ANIME`/`MANGA` | tylko węzły relacji; istotne do filtrowania |

Brak niezamówionego pola w GraphQL nie świadczy o braku możliwości katalogu. Dodatkowe relacje AnimeSchedule nie zastępują stabilnego kontraktu: ich anonimowy payload ma już różny od dokumentacji typ `season.year`.

## Dokumentacja ani.zip: granica dowodu

DIRECT: `https://ani.zip/` nie rozwiązało się w DNS, `https://api.ani.zip/` zwróciło 404. Trzy ograniczone wyszukiwania repozytoriów GitHub nie ustaliły autorytatywnej dokumentacji ani implementacji tego endpointu. Nie podjęto zgadywania kolejnych ścieżek ani masowego przeszukiwania. W związku z tym nie ustalono formalnego SLA, licencji endpointu, gwarancji kompletności, harmonogramu importów, wszystkich parametrów i źródłowej semantyki każdego pola.

Pomocniczy README [Fribb/anime-lists](https://github.com/Fribb/anime-lists) opisuje mapowania, kolekcje i indeksy własnego projektu oraz rozdział przestrzeni ID TV/movie. Zachowano snapshot `mapping-upstream-readme.raw.body` z SHA256. **Nie potwierdzono, że obecny ani.zip używa tej wersji ani tego projektu jako źródła.** Schemat README różni się od live ani.zip, np. `anime-planet_id` wobec `animeplanet_id` i obiekt `themoviedb_id` wobec stringa. Dokumentowane tam kolekcje nie są dowodem, że odczyt ani.zip zwraca franczyzę. Odczyt dotyczył ruchomej gałęzi `master`; nie ustalono commit SHA upstream, więc dowodem pozostaje zapisane ciało z hashem i datą, nie deklaracja przypiętej wersji kodu.

INFERENCE: brak ustalonej licencji/SLA nie dowodzi zakazu używania ani nie gwarantuje dostępności. W rekomendacji można oprzeć się na sprawdzonym snapshotowym zachowaniu, ale nie na nieistniejącej w tym badaniu gwarancji dostawcy.

## Wpływ na wymagania i koszt integracji — bez implementacji

| Obszar | Co pokrywa dowód | Czego nie rozstrzyga |
| --- | --- | --- |
| R-04 wyszukiwanie | AniList potwierdza nazwę/ID; AnimeSchedule realnie szuka po `q`; ani.zip daje wielojęzyczne tytuły | Kompletność synonimów, ranking i pełna niezawodność dopasowania |
| R-05 sezony | AniList/AnimeSchedule mają typowane relacje; ani.zip ma numeracje odcinków | Jednoznaczna cała franczyza i kolejność sezonów/courów; relacje katalogów się różnią |
| R-06 nieciągły wybór | Konkretne obiekty odcinków w ani.zip dają listę do wskazania | Dostępne pliki wybranych odcinków |
| R-07 dodatki | Rzeczywiste recapy, galerie, komentarze, wywiad, osobna OVA | Pełny katalog dodatków, deduplikacja Ramiris między wpisami, polityka OP/ED |
| R-08–R-09 paczki/pokrycie | Tożsamość odcinka i przyszła data są odrębne od pliku | Dostępność publikacji i pokrycie paczek; metadane nie potwierdzają żadnego torrenta |
| R-10–R-14 subskrypcje | Mapowanie do wybranego wpisu; przyszły E24; pola przesunięć | Zakończenie subskrypcji, historia opóźnień i sygnał faktycznej publikacji |
| R-15–R-17 jakość | Opis dzieła, runtime, rating, linki platform | Kodek, bitrate, kompletność napisów/audio, jakość konkretnego wydania |
| R-18–R-20 awarie i kompletność | Rozróżnienie 200/pustych episodes, 400, 404 i 401; TTL cache | Recovery pobierania, trwały postęp i kompletność lokalnego materiału |

INFERENCE — rekomendacja ograniczona do informacji:

1. Rozważać ani.zip jako **wzbogacenie pojedynczego wybranego wpisu** o listę odcinków, identyfikatory, alternatywne numery i daty. Zachować oryginalny ID wpisu, klucz odcinka i źródłowe numeracje, zamiast redukować tożsamość do `SxxExx`.
2. Istniejący katalog AniList może nadal służyć nazwom i relacjom. Nie przyjmować wszystkich powiązań jako materiałów sezonu; Slime pokazuje różne grafy i obiekty spoza anime.
3. AnimeSchedule traktować jako opcjonalną informację o terminach, nie dowód istnienia wydania. Stabilniejsza integracja wymagałaby tokenu aplikacji i świadomego uwzględnienia jego kontraktu, limitów i zasad. To nie zgoda na wdrożenie.
4. Koszt adaptera to przede wszystkim rozróżnienie braku/null/pustego stringa/sentinela, wielu numeracji, konfliktujących dat i typów oraz częściowej wiedzy. Cache 900 s może ograniczyć HTTP ani.zip, lecz nie usuwa kosztu katalogu relacji i nie gwarantuje świeżości danych źródłowych.
5. Zachować oddzielne pojęcia **tożsamość dzieła/odcinka**, **plan emisji**, **publikacja odpowiedniego wydania** i **jakość/kompletność jego mediów**. Żadne z badanych pól metadanych nie scala tych czterech dowodów.

## Dowody, weryfikacja i ścieżki

W EVIDENCE znajdują się:

- `batch1.json`–`batch7.json` — dokładne URL-e i oba dokumenty query GraphQL.
- `probe.py`, `instrument-8d5c98fcb42f.py` — instrument i snapshot odpowiadający wszystkim pomiarom.
- `*.raw.json`, `*.raw.body`, `*.meta.json` — wszystkie surowe odpowiedzi, błąd transportu i metadane; bez modyfikacji ciał.
- `*.pretty.json` — pochodne czytelne JSON-y; za dowód bajtowy służą wyłącznie `.raw.*`.
- `mapping-inventory.json` — pełne 74 ścieżki, typy, null, braki i przykłady.
- `mapping-summary.json` — sześć przypadków, liczniki pól, wszystkie specials i wybrane odcinki.
- `schedule-inventory.md` — pełne 91 ścieżek publicznego wyszukiwania z licznikami i przykładami.
- `schedule-docs.raw.body`, `schedule-anime-docs.raw.body`, `schedule-ratelimits.raw.body` — pełne HTML źródeł; `.raw.txt` to pochodne tekstowe.
- `inspect.py`, `offline.py`, `audit.py`, `audit.json` — analiza offline i sprawdzenie integralności.
- `blocked.json` — po 401 zawiera `animeschedule.net`; po tej odpowiedzi nie było dalszych żądań tej usługi.

### SHA256 głównych surowych odpowiedzi

| Plik `.raw.json` | SHA256 |
| --- | --- |
| `slime-s1` | `73b8bcc92d97bcc0dd891adebcdbdc10d5f84e499f8e510011c11684f0cc87d2` |
| `slime-s4` | `c85d1ebfbfa3a62e0b5b8029cce898b7cd0ef43196b86a871e66685fa210e37c` |
| `titan-part2` | `b0444ac78566a1de7ccbade155011849e1b17a99cb0478714bbbf4f26d30a376` |
| `haibane` | `2f1d7f0736aa7c8383a2746e6e53adfa55d742b9cba19eaef958151ef7b5de52` |
| `slime-ova` | `1b2d92a7e4a9c916eb599a99235b3edaecd2c2cda2f379df72e759fb229146b4` |
| `future-dungeon` | `e604dd0327e9e4dab26f9f8350cb7acff189eea2800a2928aaf62e8e1b1ca165` |
| `schedule-slime` | `4be3be5cdf986245c0d74d055344a78e57d79a15666f0b7573ce935d614acb45` |
| `schedule-haibane` | `9eafd5cac7d276893b0b46bdec253929dbb4485c05beb978f30517ef19de0023` |
| `catalog` | `f313c35c716245f99fc86f96af390a7f172569d9172b6fce4c243973f0d6157b` |
| `catalog-relations` | `2082cd85132e0f191293daf327d17dbb669adea9dcbec79d76deb5790486febd` |

Każdy URL jest utrwalony w odpowiadającym `.meta.json`. Ważne bezpośrednie źródła: [Slime S1](https://api.ani.zip/mappings?anilist_id=101280), [Slime S4](https://api.ani.zip/mappings?anilist_id=182205), [Titan Part 2](https://api.ani.zip/mappings?anilist_id=131681), [Haibane](https://api.ani.zip/mappings?anilist_id=387), [OVA](https://api.ani.zip/mappings?anilist_id=106509), [Dungeon Meshi 2](https://api.ani.zip/mappings?anilist_id=178031), [dokumentacja AnimeSchedule](https://animeschedule.net/api/v3/documentation/anime). Link live może z czasem zwrócić inne dane; do review używać snapshotu.

Kontrola offline zakończyła się powodzeniem dla **22 zapisów prób**: sprawdzono SHA256, długość każdego ciała, SHA256 przypisanego snapshotu instrumentu, zgodność `episodeCount + specialCount` z liczbą obiektów oraz zgodność wszystkich 89 kluczy z `episode`. Dodatkowo wyliczono różnice dat, finaleType, puste wartości i sentinele. `verify_report.py` sprawdza pokrycie w tabelach raportu wszystkich 74 ścieżek ani.zip i 91 ścieżek AnimeSchedule oraz podstawową poprawność Markdown. Nie uruchamiano testów aplikacji, ponieważ nie zmieniono jej kodu. To weryfikacja artefaktów badania, nie test E2E integracji.

## Niewiadome, odchylenia i cleanup

- **UNKNOWN:** autorytatywny kontrakt/implementacja/licencja/SLA ani.zip, tempo odświeżania upstream oraz kompletność mapowań całego katalogu. Nie zastąpiono tych braków README innego projektu.
- **UNKNOWN:** reguły prefiksów innych niż napotkane `S`, pełne pokrycie OP/ED/recapów, poprawna kolejność wszystkich dodatków i deduplikacja materiału reprezentowanego w kilku katalogach.
- **UNKNOWN:** powód rozbieżności dat, zwłaszcza Slime OVA E3, i formatu przyszłego Dungeon Meshi 2. Nie wybrano arbitralnie źródła nadrzędnego.
- **BLOCKED w podpróbie:** timetables live wymaga auth (401); dokumentację odczytano, uwierzytelnionego payloadu nie uzyskano. Nie jest to blocker ukończenia raportu części A, bo luka jest jawna i ma dowód.
- **UNKNOWN:** faktyczne niezerowe override, historia wielokrotnych przesunięć, dokładny anonimowy rate limit AnimeSchedule. W sample wszystkie override były sentinelowe.
- **Odchylenie:** nie uzyskano strony głównej ani.zip przez DNS. W ramach szukania dokumentacji wykonano trzy zapytania GitHub i odczyt pomocniczego README, bez poszerzania badań live na inne platformy metadanych. Próba `q` i 401 timetables dostarczyły bezpośredniego dowodu granic endpointów.
- **Odbiór:** Opus5 `ses_f363ca9a5ffeDVPeKHT7WzYist` zakończył niezależny przegląd wynikiem **PASS WITH FINDINGS**, bez błędów materialnych. Doprecyzowano dokumentowane filtry i limity, brak/null/sentinel/0, klauzulę trenowania, U+3164, zakres czasów i definicję inventory. Korekty oczekują na końcową weryfikację; pierwotny wykonawca nie delegował badania.
- **Cleanup:** wszystkie procesy jednorazowe zakończyły się; nie ma uruchomionej usługi ani klienta pobierania. EVIDENCE pozostawiono celowo do review, bez usuwania danych. Jedyny własny plik w repo to niniejszy raport.

Wynik zamyka badanie informacji części A. Nie ustanawia architektury, polityki wyboru dodatków ani zgody na implementację.

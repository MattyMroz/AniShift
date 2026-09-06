---
kind: plan
status: accepted-in-progress
baseline: 097df5b (work/local-automation/01-watch, PR #51)
branch: work/local-automation/04-smart-search
created: 2026-09-06
---

# Plan 04: Mądre wyszukiwanie — tytuł po ludzku, komplet odcinków, zakres jednym ruchem

## Cel

Wpisujesz „solo leveling 1”, „mushoku tensei” albo „frieren 2” i dostajesz to, co miałeś na myśli: AniShift
rozpoznaje tytuł (angielski, romaji, alias), pokazuje sezon, rok i format do wyboru, ściąga z nyaa komplet
odcinków wybranej serii (nie tylko 75 najnowszych trafień), układa grupy od najnowszych wydań i pozwala
zaznaczyć zakres odcinków jednym poleceniem. Klawisz `O` bez zmian: od tego odcinka w górę, plus przyszłe.

## Rezultat użytkownika

- Anime → „solo leveling 1” → ekran **Tytuł**: `Solo Leveling · 2024 · TV · 12 odc. · zakończone ·
  Ore dake Level Up na Ken` i pod nim sezon 2, ReAwakening. Enter wybiera, Esc wraca do hasła.
- Wyniki tylko dla odc. 1 (bo hasło miało numer): `[SubsPlease] Solo Leveling · odc. 1 · 1080p · 97 seedów`,
  potem inne grupy. Stopka mówi: `filtr: odc. 1 · F pokaż wszystkie`.
- „mushoku tensei” → wybór sezonu (I, II, II Part 2, III w emisji) → dla III komplet odcinków każdej grupy,
  grupy w kolejności najnowszego wydania (Erai-raws, SubsPlease, MTBB, ASW), `S` przełącza na seedy.
- W wynikach: `Z` pyta o zakres (`4-10`, `5-`, `-3`) i zaznacza go w podświetlonej grupie; `A` zaznacza całą
  grupę; Space i Enter jak dotąd. Scenariusz „obejrzałem 4, chcę resztę i przyszłe”: `O` na odc. 5.
  Scenariusz „4–10 teraz, przyszłe później”: `Z` `4-10`, Enter, potem `O` na odc. 11 gdy wyjdzie.
- Każdy tytuł ma widoczny status: **zakończone**, **w emisji** (z liczbą odcinków, gdy AniList ją zna) albo
  **zapowiedź**. Nagłówek wyników powtarza go, a stopka podpowiada ruch: w emisji → `O obserwuj`,
  zakończone → `A cała grupa` / `Z zakres`.
- Gdy AniList nie odpowiada, ekran Tytuł jest pomijany, hasło idzie do nyaa jak dziś, z notką w stopce.
- Subskrypcja zapamiętuje hasło „tytuł + grupa”, więc godzinne sprawdzenie widzi komplet odcinków grupy.
- Grupy angielskie i francuskie razem: nyaa jest odpytywane w dwóch kategoriach (English-translated
  i Non-English-translated), a każda grupa ma znacznik języka napisów: `[Tsundere-Raws · FR]`, `[SubsPlease · EN]`.
  Raw (bez napisów) nigdy nie trafia na listę.
- Dziwne nazwy wydań trafiają do właściwej grupy: `Mushoku Tensei Jobless Reincarnation S03E10 SUBFRENCH 1080p
  CR WEB-DL AAC2.0 H.264-Tsundere-Raws (VOSTFR…)` → grupa Tsundere-Raws, seria „Mushoku Tensei Jobless
  Reincarnation”, odc. 10; `Solo.Leveling.Arise.from.the.Shadow.S02.MULTi.1080p.WEBRiP.x265-T3KASHi` → grupa
  T3KASHi, paczka sezonu. Dziś każdy taki odcinek jest osobną „grupą” z całą nazwą jako serią.

## Warunki końcowe

- [ ] M01: `parse_query("solo leveling 1")` → tytuł `solo leveling`, odcinki `{1}`; `"frieren 4-10"` → zakres
      4–10; `"mushoku tensei"` → brak filtra; `"odc 3"`, `"ep 3"`, `"e03"` rozpoznane; rok/`1080p` nie są odcinkiem.
- [ ] M02: `AniListCatalog.search(text)` zwraca do 7 kandydatów (romaji, angielski, synonimy, rok, sezon, format,
      liczba odcinków, status) w kolejności AniList; pusty wynik → jedna ponowna próba ze skróconymi słowami
      (`levell` → `leve`); błąd sieci/limitu → `TitleCatalogError` (transient), nigdy traceback.
- [ ] M03: `AcquisitionService.search_title(candidate, episodes)` odpytuje nyaa tytułem romaji i angielskim,
      potem `"{tytuł} {grupa}"` dla ≤ 5 grup z numerowanymi odcinkami, scala po infoHash; grupy, których seria
      pasuje do aliasu kandydata, są przed resztą; w obrębie tej kolejności grupy od najnowszej publikacji.
- [ ] M04: filtr odcinków z hasła ukrywa inne odcinki i paczki; `F` pokazuje wszystko; licznik w stopce.
- [ ] M05: `Z` (zakres) i `A` (cała grupa) zaznaczają; zakres poza dostępnymi odcinkami zaznacza część i mówi ile.
- [ ] M06: `S` przełącza kolejność grup najnowsze ↔ seedy; wybór trwa do końca sesji ekranu.
- [ ] M06a: status AniList jest mapowany `FINISHED → zakończone`, `RELEASING → w emisji`, `NOT_YET_RELEASED → zapowiedź`,
      `CANCELLED/HIATUS → przerwane`; widoczny w wierszu tytułu i w nagłówku wyników; stopka wyników zależy od statusu.
- [ ] M07: `O` zapisuje subskrypcję z `query = "{tytuł} {grupa}"`; stare wpisy działają bez migracji.
- [ ] M12: po wyborze tytułu wiersz grupy zachowuje zapis grupy (`[SubsPlease · EN] Mushoku Tensei S3`), nagłówek
      pokazuje nazwę kanoniczną (romaji · angielska), a pobranie i subskrypcja z tego ekranu zapisują pliki do jednego
      folderu `workspace/<tytuł angielski, a gdy AniList go nie ma: romaji>/` niezależnie od grupy
      (`series_directory_name(candidate.folder_title())`; decyzja właściciela 2026-09-06); `Subscription` dostaje
      opcjonalne pole `directory` (brak = dotychczasowa nazwa z serii, stare wpisy bez migracji).
- [ ] M13: numeracja sezonów. `TitleCandidate` dostaje `episode_offset` = suma odcinków łańcucha PREQUEL (TV/ONA,
      bez MOVIE/SPECIAL) z AniList (Solo Leveling S2: 12; Mushoku Tensei III: 36). Numer z nazwy wydania jest
      interpretowany: nazwa ze znacznikiem sezonu (`S02`, `S2`, `Season 2`, `2nd Season`, `II`/`III`, `Part 2`) →
      numer per sezon; bez znacznika i numer > liczba odcinków wybranego sezonu → numer absolutny, pokazywany jako
      `odc. 1 (13)`; bez znacznika i numer ≤ liczba odcinków, gdy sezon ma offset > 0 → prawdopodobnie inny sezon,
      wiersz trafia na koniec grupy z dopiskiem `sezon?`. Filtr z hasła, `Z`, subskrypcja i `next_episode` liczą
      w numeracji sezonu (jak lista właściciela), a `taken` po hashu, więc obie konwencje grup są bezpieczne.
- [ ] M14: polskie napisy. Wydania ze znacznikiem `MultiSub`/`Multi-Subs`/`MULTi` dostają etykietę `multi` w wierszu
      grupy (możliwe PL); pipeline już wybiera ścieżkę wg `subtitle_language_priority` i przy `pol` pomija tłumaczenie,
      więc plan tylko upewnia się, że `pol` jest pierwsze w priorytecie (ustawienie właściciela, nie kod).
- [ ] M15: wydania z dubbingiem (`English Dub`, `Dual-Audio` bez napisów, grupy Yameii) są ukryte jak < 1080p,
      z licznikiem w stopce; `Dual-Audio` z napisami zostaje.
- [ ] M16: qBittorrent jako wymaganie. `anishift doctor` ma wiersz `torrent client`: OK gdy port Web UI odpowiada,
      WARN „qBittorrent not running or Web UI off” z podpowiedzią `anishift qbit setup`, WARN „not installed” z
      `winget install qBittorrent.qBittorrent`, gdy brak `qbittorrent.exe` w standardowych lokalizacjach (sprawdzenie
      gniazdem i ścieżką, bez ładowania backendu). `anishift qbit setup`, gdy Web UI nie odpowiada, a proces
      qBittorrenta nie działa: dopisuje do `%APPDATA%\qBittorrent\qBittorrent.ini` klucze Web UI (localhost, port 8080,
      bez logowania z localhost, losowe hasło admina wymagane przez qBittorrent 5) po zrobieniu kopii `.anishift.bak`,
      i mówi „start qBittorrent, then run qbit setup again”; gdy proces działa, prosi o zamknięcie (ini jest nadpisywane
      przy wyjściu). Instalacji nie wykonuje.
- [ ] M10: `search_releases` odpytuje kategorie `1_2` i `1_3` (dwa zapytania, scalone po infoHash); `Release`
      dostaje `subtitle_language: "en" | "fr" | "multi" | None` rozpoznany z nazwy (`VOSTFR`, `SUBFRENCH`, `VF`,
      `FRENCH` → fr; `MULTi` → multi; kategoria English-translated bez znaczników → en); wiersz grupy pokazuje
      `· FR` / `· EN` / `· MULTI`.
- [ ] M11: `parse_release_name` rozpoznaje: `SxxEyy` w środku nazwy (seria = tekst przed), grupę na końcu po
      myślniku (`-Tsundere-Raws`, `-VARYG`, `-T3KASHi`) gdy brak `[Grupa]` z przodu, nazwy z kropkami zamiast spacji,
      rok po tytule, i usuwa z serii znaczniki techniczne (`1080p`, `720p`, `WEB-DL`, `WEBRiP`, `BILI`, `CR`, `NF`,
      `AAC2.0`, `DDP`, `H.264`, `x265`, `HEVC`, `Dual-Audio`, `MULTi`, `VOSTFR`, `SUBFRENCH`, `VF`, `READNFO`,
      tytuł odcinka po `SxxEyy`). Zestaw testów z 12 prawdziwych nazw z nyaa (2026-09-06), w tym ToonsHub, Cytox,
      AnoZu, Feibanyama, Breeze, VARYG, Tsundere-Raws, Xspitfire911, T3KASHi.
- [ ] M08: bramki root zielone; próba na żywo przez fasadę: „solo leveling 1” → SubsPlease odc. 1;
      „solo leveling season 2” + odc. 1 → SubsPlease `odc. 1 (13)`;
      „mushoku tensei” → 4 kandydatów, sezon III ma odc. 1–10 z ≥ 3 grup.
- [ ] M09: właściciel: przeszedł hasło → tytuł → zakres → Enter na klawiaturze i dostał pliki w `workspace/<Seria>/`.

## Nie-cel

Polskie tytuły (AniList zna tylko pojedyncze synonimy, np. „Czarodziejka z Księżyca”), kanji/kana jako hasło
lub zapytanie do nyaa (decyzja właściciela 2026-09-06), raw bez napisów,
RapidFuzz i lokalny katalog aliasów, tolerancja literówek innych niż ucięte końcówki, MAL, drugi indeks
poza nyaa, scraping HTML nyaa, zmiany w czuwaniu; w `subscriptions.json` tylko jedno opcjonalne pole `directory`.

## Authority i baseline

| Źródło | Rola |
| --- | --- |
| Właściciel 2026-09-06 (czat) | „wyszukiwarka jak w nyaa”, „solo leveling 1” ma działać, najnowsze na górze, łatwe żądanie odcinków, „obejrzałem 4, chcę 4–10 i dalsze w subskrypcji” |
| [spec.md](../spec.md) R03, R04, R05, R08, R09 | tytuły i aliasy, jawna tożsamość (fuzzy tylko porządkuje), 1080p+, pobieranie, subskrypcje |
| [brief.md](../brief.md) „Wyszukiwanie ma podpowiadać, reguła pobrania ma być ścisła”, D08 (AniList jako katalog) | decyzje |
| Plan 02, Plan 03 (wykonane) | ekran Anime, `AcquisitionService`, `SubscriptionService` |

Zweryfikowane 2026-09-06 (sondy `httpx`):

- RSS nyaa daje dokładnie 75 najnowszych trafień; `p=`, `s=`, `o=` są ignorowane. Dla „Solo Leveling” SubsPlease
  ma w tych 75 tylko 3 odcinki; „Solo Leveling SubsPlease” daje komplet 25. Tytuł romaji „Ore dake Level Up na Ken”
  też daje 75 trafień.
- nyaa szuka po tokenach: „Solo Leveling - 01” trafia w odc. 1, „solo leveling 1” nie (token `1` pasuje wszędzie).
- AniList GraphQL (`https://graphql.anilist.co`, bez klucza, limit ~30/min widoczny w `x-ratelimit-remaining`):
  „mushoku tensei” → 5 sezonów z romaji/angielskim/synonimami/rokiem/formatem/liczbą odcinków/statusem;
  „frieren 2” → `Sousou no Frieren 2nd Season`; prefiks „solo leve” trafia; literówki „solo levelling”,
  „sollo leveling”, „musoku tensei” → 0.
- `Release.published` (pubDate RSS) jest już parsowane; grupy są sortowane po seedach (`_group_order`).
- Kategoria `1_3` (Non-English-translated): „Mushoku Tensei” 75 trafień, 12 francuskich (Tsundere-Raws SUBFRENCH/MULTi);
  „Solo Leveling” 41 francuskich; „Heroine Saint” 22 (wszystkie Tsundere-Raws). Dziś wyszukiwanie używa tylko `1_2`.
- Nazwy bez `[Grupa]` i bez ` - ` (ToonsHub, Cytox, AnoZu, VARYG, Tsundere-Raws) dają dziś jedną „grupę” na odcinek
  z całą nazwą jako serią (sonda „Mushoku Tensei”: 42 grupy, z czego ~25 to takie duplikaty).
- AniList `relations` daje łańcuch PREQUEL z liczbą odcinków i formatem (Solo Leveling S2: prequel TV 12 + MOVIE 1;
  Mushoku Tensei III: prequel II Part 2, 12), więc offset numeracji absolutnej jest policzalny bez ręcznej tabeli.
- Planner wybiera ścieżkę napisów wg `subtitle_language_priority` i przy języku `pol` pomija tłumaczenie
  (`planner.py`, reguła `action is AUTO and language != "pol"`); MultiSub z PL nie wymaga zmian w pipeline.
- AniList zna polskie tytuły tylko wyjątkowo („Atak Tytanów”, „Miecz zabójcy demonów” → 0); francuskie bywają
  w synonimach („Le quartier des plaisirs”).
- Kod: `anishift/cli/interactive/anime.py` (stany QUERY/BUSY/RESULTS/DONE/PROBLEM, klawisze Space/Enter/O/Esc),
  `anishift/application/acquisition.py` (`search`, `catalog_releases`), `anishift/services/torrents/nyaa.py`
  (`search_releases`), `anishift/application/subscriptions.py` (`subscribe(query, choice)`).

## Różnica

```text
CURRENT STATE
  hasło → 1 zapytanie RSS (75 trafień) → grupy po seedach → Space/Enter/O
    ↓
GAP
  numer w haśle psuje trafienia; 75 trafień gubi starsze odcinki popularnych serii;
  brak wyboru sezonu/aliasu; brak kolejności po dacie; zaznaczanie tylko pojedynczo
    ↓
TARGET STATE
  hasło → intencja (tytuł, odcinki) → AniList: kandydaci → wybór → nyaa: romaji + angielski + per grupa
  → scalony katalog, aliasy najpierw, najnowsze na górze → filtr odcinków, Z/A/S → Space/Enter/O
```

## Impact scan

- `AcquisitionService.search(query)` zostaje (używa go `SubscriptionService.check`); dochodzi `find_titles`
  i `search_title`. `Subscription.query` bez zmiany typu; nowe wpisy dostają „tytuł grupa”.
- Ekran Anime dostaje jeden nowy stan (TITLES) i trzy klawisze; `HomeAction` i renderer bez zmian.
- Nowa granica sieciowa (AniList) w `bootstrap` na wspólnym `httpx.Client`; awaria AniList nie może zablokować
  wyszukiwania (fallback do surowego hasła).
- Reguła architektury: `anishift/cli/**` importuje tylko fasadę `anishift.application`; nowe typy przez
  `application/__init__.py` (lazy + TYPE_CHECKING).
- Limit AniList ~30 zapytań/min: jedno zapytanie na Enter, jedna ponowna próba przy pustym wyniku; nic w pętli.
- Do 7 zapytań nyaa na jeden wybór tytułu (2 tytuły + 5 grup) ≈ 2–3 s; wątek `anishift-anime` już istnieje,
  `Szukam…` z Esc anuluje.

## Target design

```text
anishift/services/catalog/__init__.py       # NEW: eksport
anishift/services/catalog/types.py          # NEW: TitleCandidate(anilist_id, romaji, english, native, synonyms,
                                            #      year, season, format, episodes, status) + aliases(): romaji, english i synonimy
                                            #      zapisane alfabetem łacińskim (bez pustych, casefold-unikalne); native tylko do wyświetlania
anishift/services/catalog/errors.py         # NEW: TitleCatalogError(TransientError), ErrorCode.TITLE_CATALOG_FAILED
anishift/services/catalog/anilist.py        # NEW: AniListCatalog(http, timeout_s).search(text, limit=7);
                                            #      GraphQL POST; pusty wynik → retry ze słowami uciętymi do 60 %
anishift/services/catalog/AGENTS.md         # NEW
anishift/services/torrents/query.py         # NEW: parse_query(text) -> SearchQuery(title, episodes: EpisodeRange|None)
anishift/services/torrents/nyaa.py          # MODIFY: kategorie 1_2 + 1_3, scalanie po infoHash, subtitle_language
anishift/services/torrents/names.py         # MODIFY: SxxEyy w środku, grupa po myślniku, kropki, znaczniki techniczne
anishift/services/torrents/types.py         # MODIFY: Release.subtitle_language
                                            #      EpisodeRange(first: Decimal|None, last: Decimal|None).contains(ep)
anishift/application/acquisition.py         # MODIFY: TitleCatalog Protocol; find_titles(text); search_title(candidate,
                                            #      episodes) -> ReleaseCatalog; catalog_releases(..., aliases, order)
anishift/application/__init__.py            # MODIFY: eksport SearchQuery, EpisodeRange, TitleCandidate, CatalogOrder
anishift/bootstrap.py                       # MODIFY: AniListCatalog na wspólnym httpx.Client
anishift/errors.py                          # MODIFY: TITLE_CATALOG_FAILED
anishift/cli/interactive/anime.py           # MODIFY: stan TITLES, filtr odcinków, klawisze Z/A/S/F, prompt zakresu
anishift/cli/interactive/prompts.py         # MODIFY tylko jeśli prompt zakresu wymaga nowego wiersza chrome
anishift/application/subscriptions.py       # MODIFY: pole directory (opcjonalne), subscribe(..., directory_name), check() pobiera do niego
README.md, anishift/{cli,application,services}/AGENTS.md   # MODIFY: opis
tests/services/catalog/test_anilist.py, tests/services/torrents/test_query.py,
tests/application/test_acquisition.py, tests/cli/test_interactive_anime.py   # tests
```

Kontrakty:

```text
parse_query(text) -> SearchQuery
  tytuł = tekst bez końcowego wskaźnika odcinka; wskaźnik: /(?:odc\.?|ep\.?|e)?\s*(\d{1,4}(?:\.\d)?)(?:\s*-\s*(\d{1,4})?)?$/i
  oraz "-N" (do N); liczba ≥ 1900 i ≤ 2100 albo z sufiksem "p" nie jest odcinkiem; tytuł nie może zostać pusty

AniListCatalog.search(text, limit=7) -> tuple[TitleCandidate, ...]
  query: Page(perPage: limit) { media(search: $s, type: ANIME, sort: SEARCH_MATCH) { id title{romaji english native}
         synonyms seasonYear season format episodes status } }
  pusto → retry z każdym słowem uciętym do max(3, int(len*0.6)); status ≠ 200 / brak "data" → TitleCatalogError

AcquisitionService.find_titles(text) -> tuple[TitleCandidate, ...]        # TitleCatalogError przechodzi wyżej
AcquisitionService.download(choices, directory_name=None)                 # None = dotychczasowa reguła per seria
SubscriptionService.subscribe(query, choice, directory_name=None); check() używa subscription.directory gdy jest
AcquisitionService.search_title(candidate, episodes=None, order=NEWEST) -> ReleaseCatalog
  zapytania: romaji, english (jeśli różny, casefold) → wydania; grupy z ≥1 numerowanym odcinkiem, ≤5 wg
  najnowszej publikacji → zapytanie "{romaji} {grupa}"; scal po infoHash; catalog_releases(aliases=candidate.aliases(),
  order=order, episodes=episodes)
catalog_releases(..., aliases=(), order=CatalogOrder.SEEDERS|NEWEST, episodes=None)
  klucz grupy: (0 jeśli normalize(seria) ∈ normalize(aliasy) else 1, -max(published) | -seeders, seria, grupa)
  normalize: NFKC, casefold, usunięcie znaków poza literami/cyframi/spacją, zbicie spacji
  episodes → choice.name.episode w zakresie; paczki ukryte; ReleaseCatalog.hidden liczy odrzucone jakością,
  ReleaseCatalog.filtered liczy odrzucone filtrem odcinków (nowe pole, default 0)

Ekran Anime:
  QUERY --Enter--> BUSY(find_titles) --0 kandydatów lub TitleCatalogError--> BUSY(search(raw)) --> RESULTS (notka)
                                     --≥1--> TITLES: "{romaji} · {rok} · {format} · {n} odc. · {status_pl} · {english}"
  TITLES --Enter--> BUSY(search_title) --> RESULTS ; Esc --> QUERY
  RESULTS nagłówek: "{romaji} · {status_pl}" (np. "Mushoku Tensei III · w emisji · 10/14 odc.")
  RESULTS: Space, Enter, O jak dziś; A = zaznacz odcinki podświetlonej grupy; Z = prompt "zakres (np. 4-10):" w stopce,
           Enter zatwierdza, Esc anuluje; S = najnowsze↔seedy (ponowne ułożenie bez sieci); F = zdejmij filtr odcinków
  stopka: "zaznaczone: N · filtr: odc. 4–10 · ukryte poniżej 1080p: H · Space/A/Z zaznacz · Enter pobierz · O obserwuj · S seedy · Esc"
  O: subscribe(f"{romaji} {grupa}", choice) gdy tytuł wybrany, inaczej subscribe(raw, choice) jak dziś
```

## Wykonanie

0. **Nazwy i kategorie** (services/torrents): M10, M11 z testami na prawdziwych nazwach; to samo w sobie poprawia
   dzisiejszy ekran, więc idzie jako pierwszy commit.
1. **Parser hasła i katalog AniList** (services): `query.py`, `catalog/*`, ErrorCode; testy jednostkowe z
   `httpx.MockTransport` (trafienia, pusto → retry, limit 429, brak `data`). Wyjście: `uv run pytest tests/services`.
2. **Fasada**: `find_titles`, `search_title`, `catalog_releases(aliases, order, episodes)`, eksporty, bootstrap;
   testy `test_acquisition.py` (scalanie po hash, kolejność aliasy→data, filtr, ≤5 zapytań grupowych).
   Sonda na żywo przez fasadę: M08.
3. **Ekran Anime**: TITLES, Z/A/S/F, prompt zakresu, stopka; testy ekranu (istniejące 26 + nowe klawisze).
4. **Dokumentacja**: README (sekcja Searching), AGENTS `services/catalog`, wynik w tym pliku, README pakietu.
5. **qBittorrent jako wymaganie** (M16): wiersz doctora, `qbit setup` piszący konfigurację Web UI, README Requirements.

Decyzje właściciela 2026-09-06 (czat): ekran Tytuł zawsze; dubbing angielski ukryty; folder angielski/romaji;
kolejność grup najnowsze + `S`; wybór „najlepszej grupy” i grupa zapasowa (R06) → plan 05 po odbiorze.

Sprzężenie: literówka niepokryta skróceniem słów = poza zakresem (nie wracać po RapidFuzz w tym planie);
AniList zmieni schemat lub limit → fallback do surowego hasła musi działać, test tego fallbacku jest w M02/M03;
nyaa zacznie stronicować RSS → zapytania per grupa zostają (tańsze niż strony).

## Dowód

Unit: parser (12 przypadków), AniList (5), katalog i scalanie (8), ekran (klawisze, filtr, fallback). Live przez
fasadę: M08. Human: M09 na klawiaturze, z uwagą na to, czy ekran Tytuł nie jest jednym krokiem za dużo, gdy
AniList daje jeden oczywisty wynik (decyzja właściciela po próbie: auto-wybór przy jednym kandydacie czy zawsze
lista).

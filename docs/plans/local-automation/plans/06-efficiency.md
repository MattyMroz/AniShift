---
kind: specification
status: awaiting-owner-acceptance
baseline: 167a181 (work/local-automation/05-polish)
branch: work/local-automation/06-efficiency
created: 2026-09-06
updated: 2026-09-06
---

# Plan 06: Szybciej i oszczędniej — specyfikacja

Trwałe ustalenia dla czuwania, subskrypcji, klienta torrent i rozruchu. Zastępuje pierwszą, za wąską wersję tego planu
(wykonanie zatrzymane przez właściciela 2026-09-06; szkice wykonawców w `git stash`). Po akceptacji powstaje szczegółowy
plan **tylko** dla etapu 06a; kolejne etapy dostają plan po wyniku poprzedniego.

## Cel

To samo zachowanie, te same pliki i presety, ale:

- nowy odcinek obserwowanej serii jest w qBittorrencie **do 10 min po publikacji przez grupę**, a poza oknem premiery
  program nie pyta nyaa wcale;
- czuwanie reaguje na nowe pliki, stop i subskrypcje **zawsze w ≤ 5 s**, także podczas partii i podczas sprawdzania
  subskrypcji;
- okno partii i czuwanie zaczynają pracę **w ≤ 1 s** zamiast 11–14 s;
- qBittorrent i procesor **nie pracują, gdy nie ma czego robić**;
- `subs list` mówi, **kiedy** i **dlaczego** program spodziewa się następnego odcinka.

Zero nowych zależności, zero zmian w formacie produktów, zero zmian ustawień właściciela bez jego decyzji.

## Stan wyjściowy — pomiary 2026-09-06 (biblioteka 83 grupy, 25 subskrypcji)

| Co | Dziś | Dowód |
| --- | --- | --- |
| Runda subskrypcji | 26 subskrypcji → 99 zapytań nyaa (≈ 200 GET) w 162 s; w tym czasie pętla nie skanuje biblioteki i nie widzi flagi stop | log 22:43–22:45; `cli/watch.py` `_watch_loop` jest jednowątkowa |
| Koszt jednej subskrypcji | zapytanie tekstowe + zapytanie doganiające, każde w 2 kategoriach = 4 GET, ~1,6 s; doganiające leci **zawsze**, gdy następny odcinek jeszcze nie wyszedł | `subscriptions.py` `_offered`; `checked_at` co ~2 s |
| Rytm | co godzinę wszystkie: ≈ 2 400 GET/dobę; odcinek czeka do 60 min; **podczas okna partii subskrypcje nie są sprawdzane wcale** (partia 10 grup ≈ 5,5 min, 17 grup ≈ 12 min) | `_watch_loop`: `continue` przed `_check_subscriptions`; log 22:34–22:39 |
| Awaria nyaa | timeout 20 s × 2 kategorie × 26 subskrypcji = do ~17 min blokady pętli (wyliczenie z kodu, nie zmierzone) | `nyaa.py` `DEFAULT_SEARCH_TIMEOUT_S`, brak bezpiecznika |
| Rozruch okna partii | 14,5 s do „Automatic run planned”; `discover()` w nowym procesie 11,4 s: pełne dekodowanie 83 plików lektora (0,7 s każdy, 57 s czasu wątków / 8), ffprobe 4 s, napisy 4 s; kolejny `discover()` w tym samym procesie 14 ms | log okna pid 32048; cProfile 23:30 |
| Okno partii 4 grup | 118 s: rozruch 14,5 s, ekstrakcja 5 s, LLM 48 s i 69 s **równolegle**, TTS + render ~15–20 s na grupę **sekwencyjnie** (`_TTS_GROUP_JOBS = 1`), odliczanie zamknięcia 10 s | log pid 32048 |
| Czuwanie w spoczynku | 61 MB, ~0,9 % rdzenia łącznie z rundą subskrypcji; skan co 5 s to same `stat()` (fingerprint), inspekcja tylko przy zmianie | `Get-Process`; `service.discover` |
| qBittorrent | 101 MB, 342 węzły DHT, DHT/PEX/LSD włączone, 1 839 s CPU od 05:00 (pobierania + DHT); 55 torrentów AniShift w stanie `stoppedUP`; musi działać stale | Web API `transfer/info`, `app/preferences` |
| nyaa | GET 0,4–0,6 s; **feed uploadera** `?page=rss&u=subsplease` = 75 najnowszych wydań grupy z ostatnich ~27 h (Erai-raws tak samo); `u=` + `q=` = pełna historia serii u tej grupy (Mushoku Tensei: 2023–2026) w jednym GET | sondy 23:1x |
| AniList | 403 „temporarily disabled” przez cały wieczór; ekran Anime działa z zapasowym dopasowaniem, ale bez sezonów i bez dat emisji | sonda 23:15 |
| Okna partii | 33 okna dziś; kody wyjścia 0 poza oknami zamkniętymi ręcznie | log |

## Rezultat użytkownika

- Subskrypcja ma **termin**: `subs list` pokazuje np. `next 12 · okno pn 17:10–23:10 (AniList + 45 min)` albo
  `next 12 · okno wt 15:00–21:00 (historia, co 7 dni)`, a po przegapionym oknie `spóźniony · co godzinę`, po serii
  zakończonej `zakończona · tylko subs check`.
- Nowy odcinek trafia do qBittorrenta do 10 min po publikacji. Poza oknem nyaa milczy.
- Czuwanie zawsze reaguje w ≤ 5 s: na nowy plik, na `watch stop`, na okno premiery, także gdy trwa partia albo gdy
  nyaa nie odpowiada.
- Okno partii startuje w ≤ 1 s po inspekcji z dysku; czuwanie po restarcie też.
- qBittorrent uruchamia się, gdy jest co pobrać, i wyłącza po skończonej pracy — ale tylko ta instancja, którą
  uruchomił AniShift, i tylko gdy nie ma w nim cudzych aktywnych torrentów. Ręcznie otwartego nie rusza.
- Nic nie zmienia się w plikach, presetach, kluczach ani w tym, co widać w oknie partii.

## Model rytmu subskrypcji (decyzje właściciela, obowiązujące)

Każda subskrypcja ma **termin publikacji** `expected_at` (UTC) i **odstęp** `cadence_days`. Stan wynika z terminu i zegara:

| Stan | Kiedy | Rytm zapytań |
| --- | --- | --- |
| `przed terminem` | `now < expected − 10 min` | **żaden** (przez tydzień nic się nie zmieni) |
| `okno` | `expected − 10 min ≤ now ≤ expected + 6 h` | co 10 min |
| `spóźniony` | okno minęło bez trafienia | co godzinę, aż do trafienia (patrz decyzja D1) |
| `bez terminu` | brak źródła terminu (nyaa i AniList nie odpowiedziały) | co godzinę jak dziś |
| `zakończona` | `next_episode > season_episodes` albo AniList `FINISHED` bez kolejnej emisji | **nigdy automatycznie**; tylko `subs check` |

Trafienie przesuwa termin: `expected_at = published(odcinek) + cadence`. Po trafieniu program **od razu** sprawdza,
czy wyszedł też kolejny numer (luki), i wraca do `przed terminem`.

### Źródło terminu (kolejność obowiązująca)

1. **AniList** `Media(id).nextAiringEpisode.airingAt` (+ `airingSchedule` na 2 kolejne odcinki, żeby przerwa w emisji
   była znana) **+ opóźnienie grupy**: różnica między `published` trafionego wydania a `airingAt` tego odcinka, uczona
   przy każdym trafieniu (mediana ostatnich 3), domyślnie 45 min. Wymaga `anilist_id` w subskrypcji: ekran Anime
   przekazuje id kandydata przy `F`; dla istniejących 25 subskrypcji id jest dobierane raz przez `search(series)`
   z dopasowaniem aliasów do `series_forms`, gdy AniList znów odpowie; bez dopasowania zostaje `None`.
2. **Historia publikacji grupy**: jeden GET `?page=rss&u=<grupa>&q=<seria>` daje daty wszystkich wydań tej serii
   u tej grupy; `cadence = mediana odstępów między kolejnymi numerami` (jeden odstęp wystarczy),
   `expected = ostatnia publikacja + cadence`. Jedna publikacja w historii: patrz decyzja D2.
3. Bez obu: `bez terminu`, co godzinę.

AniList, gdy odpowiada, **poprawia** termin z historii (przerwy w emisji, przesunięcia), ale nigdy nie jest warunkiem
działania. Dziś AniList leży, więc ścieżka 2 musi być pełnowartościowa, nie awaryjna.

### Jak wygląda jedno sprawdzenie w oknie (koszt)

- Subskrypcje w oknie są grupowane po uploaderze. **Jeden GET feedu uploadera** (`u=<grupa>`, 75 najnowszych, ≈ 27 h)
  obsługuje wszystkie subskrypcje tej grupy naraz; dopasowanie serii i sezonu robi istniejące `_new_episodes`/`_matches`.
  Zapytanie per seria wraca tylko wtedy, gdy feed uploadera nie sięga początku okna (najstarszy wpis młodszy niż
  `expected − 10 min`).
- Zapytanie doganiające po numerze leci **tylko dla luki** (`next_episode` mniejszy od najnowszego oferowanego numeru),
  nie „zawsze, gdy odcinek jeszcze nie wyszedł”.
- Wynik: w oknie premier **≈ 1 GET na grupę na 10 min** (dziś 2 grupy → 2 GET), zamiast 4 GET na subskrypcję na godzinę.
  Szacunek doby z 25 subskrypcjami: ≤ 150 GET zamiast ≈ 2 400, a odcinek czeka ≤ 10 min zamiast ≤ 60.

## Katalog scenariuszy

Każdy: co dziś (dowód) → co po → jak mierzymy. Priorytet: **A** rdzeń zamówienia, **B** wyraźny zysk, **C** dopełnienie.

### S1 (A) Termin premiery zamiast godzinnej pętli

Dziś: co godzinę wszystkie, 4 GET na subskrypcję, odcinek czeka do 60 min. Po: model rytmu wyżej. Miara: test z zegarem
(przed terminem 0 zapytań przez 6 dni; w oknie 6 zapytań/h na grupę; trafienie przesuwa termin; przegapione okno →
co godzinę; `season_episodes` przekroczone → 0 zapytań), smoke na żywo na najbliższej premierze (Buchigire pn).

### S2 (A) Feed uploadera zamiast zapytania per seria

Dziś: 26 subskrypcji → 99 zapytań. Po: 1 GET na grupę na sprawdzenie; per seria tylko dla luki lub gdy feed za krótki.
Miara: test z nagranym feedem uploadera (2 subskrypcje SubsPlease, 1 GET, obie trafione); licznik GET w logu rundy.

### S3 (A) Sprawdzanie subskrypcji nie blokuje pętli

Dziś: runda 162 s blokuje skan i stop; podczas partii subskrypcje nie są sprawdzane. Po: sprawdzenia biegną w jednym
wątku roboczym startowanym przez pętlę; pętla co 5 s skanuje, spawnuje okno, czyta stop **niezależnie** od rundy
i od trwającej partii. Wątek jest daemonem: `watch stop` nie czeka na trwający GET (≤ 20 s). Zapis
`subscriptions.json` tylko z tego wątku (CLI `subs check` to osobny proces; ostatni zapis wygrywa — jak dziś).
Miara: test pętli z fałszywym, wolnym sprawdzeniem (2 skany w czasie rundy; stop w ≤ 1 tick).

### S4 (A) Bezpiecznik nyaa

Dziś: awaria nyaa = do 17 min timeoutów w jednej rundzie. Po: pierwszy `TorrentSourceError` w rundzie kończy rundę
(reszta subskrypcji zostaje „do sprawdzenia”), następny tick próbuje ponownie; jeden wpis w logu na rundę. Miara: test
z fałszywym źródłem rzucającym błąd: 1 zapytanie, nie 26.

### S5 (A) `subs list` mówi kiedy i dlaczego

Dziś: `next: 12 · checked: <ISO>`. Po: stan, okno w czasie lokalnym, źródło terminu (AniList / historia / brak),
ostatnia decyzja (`trafienie 11 o 17:02`, `okno bez trafienia`, `nyaa nie odpowiada`). Log czuwania: jedna linia na
tick z liczbą sprawdzonych i pobranych. Miara: test formatu wiersza; przegląd właściciela.

### S6 (B) Inspekcja z dysku

Dziś: każdy nowy proces (okno partii, czuwanie po restarcie) płaci 11,4 s, głównie na pełne dekodowanie każdego
lektora. Po: `config/cache/inspection.json` z kluczem `(ścieżka względna, rozmiar, mtime_ns)` per artefakt i wartością
= stan, `duration_us`, język, katalog mediów (dla wideo). `discover()` sonduje tylko artefakty bez trafienia;
zapis atomowy po inspekcji; plik nieczytelny = ignorowany i odbudowany; wpisy plików, których już nie ma, są
usuwane przy zapisie. Semantyka bez zmian: zmieniony plik jest dekodowany w całości jak dziś. Rozważone i odrzucone:
zamiana dekodowania na `ffprobe` (10× taniej, ale traci walidację całego pliku). Miara: cold `discover()` ≤ 0,5 s na
dzisiejszej bibliotece; okno partii do „Automatic run planned” ≤ 3 s; test: zmieniony mtime jednego pliku → dokładnie
jedna sonda.

### S7 (B) qBittorrent na żądanie

Dziś: musi działać stale; 101 MB, 342 węzły DHT, CPU nawet bez pobierań. Po: `ensure_client()` uruchamia
`qbittorrent.exe` (ścieżka z `installed_executable()`), gdy Web UI nie odpowiada, czeka ≤ 20 s, zapisuje PID w
`config/watch/qbittorrent.pid`. `release_client()` wysyła `/app/shutdown` **tylko** gdy: PID zapisany = PID bieżącego
`qbittorrent.exe`, wszystkie torrenty kategorii `AniShift` zakończone, żaden torrent spoza kategorii nie pobiera ani
nie wysyła, i minęło 10 min od ostatniej pracy AniShift (decyzja D4). Ustawienie `qbittorrent_manage_process`
(domyślnie `true`) w `settings.json`; `doctor` pokazuje, czy klient jest zarządzany i czy jego własny autostart
Windows jest włączony (to właściciel decyduje, czy go wyłączyć). Start zminimalizowany do zasobnika: klucz w
`qBittorrent.ini` do potwierdzenia przez wykonawcę na prawdziwym pliku (`qbit setup` może go dopisać jak klucze Web UI).
Ręcznie otwarty klient (inny PID) nigdy nie jest zamykany. Miara: testy z fałszywym procesem i klientem; smoke:
w logu „client started by AniShift” → pobranie → partia → „client stopped by AniShift”.

### S8 (B) Pomiar przepustowości partii

Dziś: LLM już równolegle między grupami; TTS + render sekwencyjnie ~15–20 s/grupa (`_TTS_GROUP_JOBS = 1`); 10 grup
≈ 5,5 min. Pierwsza wersja planu mierzyła `translation_concurrency` — złe miejsce, dowód wyżej. Po: pomiar na kopii
4 rzeczywistych grup: TTS group jobs 1 vs 2 (limity głosów bez zmian). Jeśli skraca partię ≥ 25 % bez błędów TTS:
domyślna wartość nowej instalacji = 2, ustawienie właściciela bez zmian, README/`doctor` mówią, jak podnieść.
Jeśli nie: zapis wyniku i koniec. Miara: dwa przebiegi, czas do „Batch finished”.

### S9 (C) Krótsze okno partii

Dziś: odliczanie 10 s po każdym oknie; kolejne pliki czekają, aż okno się zamknie. Po: 3 s, gdy czuwanie ma już
kolejnych kandydatów (`watch batch --next-waiting`), inaczej 10 s (decyzja D3). Zysk mały (7 s na okno); wchodzi, bo
kosztuje jedną flagę.

### S10 (C) Cache ekranu Anime

Dziś: `F`/`S`/`Esc→Enter` powtarzają te same do 16 GET; AniList w awarii nie zna sezonów. Po: cache nyaa w pamięci
procesu, TTL 120 s, klucz `(zapytanie, kategorie)`; cache AniList na dysku `config/cache/anilist.json` (wyniki
`search` 7 dni, łańcuchy prequeli i emisje 30 dni, ≤ 1 MB, przycinanie najstarszych), przy błędzie sieci wpis
przeterminowany z notką „AniList nie odpowiada, dane z pamięci”. Miara: 2 wyszukania w TTL = 2 GET; round-trip cache.

### Rozważone i odrzucone (z dowodem)

- **Adaptacyjny skan 5 s → 30 s.** Skan bez zmian to same `stat()`; czuwanie zużywa < 1 % jednego rdzenia razem
  z rundą. Zysk niemierzalny, a stop i nowe pliki reagowałyby wolniej. Nie wchodzi.
- **Sprawdzenie dobowe przed terminem.** Właściciel: przez tydzień nic się nie zmienia. Nie wchodzi.
- **Seria zakończona co tydzień.** Właściciel: nigdy automatycznie. Nie wchodzi.
- **Cache tłumaczeń LLM.** Odcinki nie powtarzają linii, a gotowe tłumaczenie jest produktem na dysku i nie jest
  liczone ponownie. Nie ma czego cache’ować.
- **Usuwanie zakończonych torrentów z klienta.** 55 wpisów `stoppedUP` nic nie kosztuje; hash w kliencie chroni przed
  ponownym pobraniem. Nie wchodzi.
- **Import listy MAL / Jikan jako źródło emisji.** Osobna funkcja, nie wydajność; wraca, jeśli AniList będzie leżał
  dłużej niż tydzień. Odroczone.
- **Watchdog / zdarzenia systemu plików.** Nowa zależność; skan co 5 s wystarcza. Nie wchodzi.

## Impact scan

- `subscriptions.json`: nowe **opcjonalne** pola `anilist_id`, `expected_at`, `cadence_days`, `schedule_source`
  (`anilist` / `history` / `assumed` / `null`), `group_delay_s`, `missed_windows`, `finished`. Brak = dzisiejsze
  zachowanie; bez migracji; `_OPTIONAL_ENTRY_KEYS` rozszerzone.
- `settings.json`: pole `qbittorrent_manage_process` w `UserSettings` + `field_catalog` + testy kontraktu.
- `config/cache/` (gitignore) — inspekcja i AniList; usunięcie katalogu jest bezpieczne.
- `config/watch/qbittorrent.pid` — własność uruchomionego klienta.
- `cli/watch.py`: wątek sprawdzeń, tick co 5 s bez `continue` dla partii; `SUBSCRIPTION_CHECK_INTERVAL_S` zostaje
  jako rytm `bez terminu` / `spóźniony`.
- `services/torrents/nyaa.py`: parametr uploadera (`u=`) obok `q=`/`c=`; `TorrentSource.search` dostaje `uploader`.
- `services/catalog/anilist.py`: zapytanie o emisje (`nextAiringEpisode`, `airingSchedule`, `status`) — kształt pól
  do potwierdzenia w wykonaniu (masterplan 10.1 je wymienia; AniList dziś nie odpowiada).
- `acquisition.py`: `search_uploader(group, query=None)`, `ensure_client`/`release_client`.
- Okno partii: `watch batch --next-waiting`; ledger bez zmian.
- Ryzyko współbieżności `subscriptions.json`: daemon (wątek) i ręczne `subs check` mogą się nadpisać — jak dziś;
  akceptowane, bo `subs check` ręczne jest rzadkie; odnotowane w README.

## Nie-cele

VPS i zdalna praca; nowe zależności; zmiana formatu produktów i presetów; zmiana silników TTS/LLM; zmiana ustawień
właściciela bez decyzji (S8 zmienia tylko domyślne nowej instalacji); panel/GUI; scraping HTML nyaa; obsługa
klientów innych niż qBittorrent.

## Decyzje do podjęcia przez właściciela

| Nr | Pytanie | Rekomendacja |
| --- | --- | --- |
| D1 | `spóźniony`: co godzinę **bez końca**, czy po **2 kolejnych** przegapionych terminach (≈ 2 tygodnie ciszy) wstrzymać automatykę i pokazać `bez nowych odcinków od 2 tyg. · subs check`? | wstrzymać po 2 (chroni przed wiecznym pytaniem o serię, której koniec nie jest znany, bo AniList leży) |
| D2 | Jedna publikacja w historii (np. subskrypcja po 1. odcinku): założyć **7 dni** i oznaczyć `założone`, czy co godzinę do 2. odcinka? | założyć 7 dni |
| D3 | Odliczanie okna 10 s → 3 s, gdy czekają kolejne grupy? | tak |
| D4 | qBittorrent: wyłączać po **10 min** bezczynności AniShift, czy natychmiast po partii? | 10 min (w oknie premiery często wychodzi kilka serii pod rząd) |
| D5 | Kolejność etapów: 06a (S1–S5) → 06b (S6, S9) → 06c (S7) → 06d (S8) → 06e (S10); czy 06d/06e w ogóle? | tak, w tej kolejności; 06e jako ostatni, opcjonalny |

## Mapa etapów (po akceptacji szczegółowy plan tylko dla 06a)

| Etap | Scenariusze | Pliki (rozłączne między etapami) | Dowód końca |
| --- | --- | --- | --- |
| 06a Rytm premier | S1–S5 | `application/subscriptions.py`, `application/acquisition.py` (uploader), `services/torrents/nyaa.py`, `services/catalog/anilist.py` (emisje), `cli/watch.py`, `cli/main.py` (wiersz `subs list`), `cli/interactive/anime.py` (id kandydata), testy + `tests/integration` z nagranym feedem uploadera | testy z zegarem; runda 25 subskrypcji ≤ 5 GET; smoke na żywo na najbliższej premierze; `watch stop` ≤ 5 s podczas rundy |
| 06b Rozruch | S6, S9 | `application/{service,inspection}.py`, nowy `application/inspection_cache.py`, `paths.py`, `.gitignore`, `cli/interactive/app.py` (odliczanie), `cli/main.py` (`--next-waiting`), testy | cold `discover()` ≤ 0,5 s; okno do planu ≤ 3 s |
| 06c Klient na żądanie | S7 | `platform/qbittorrent_config.py`, `application/acquisition.py` (ensure/release), `config/user_settings.py` + `field_catalog.py`, `cli/main.py` (`qbit`, `doctor`), README, testy | smoke z logiem start/stop; ręcznie otwarty klient nietknięty (test z obcym PID) |
| 06d Pomiar partii | S8 | `scripts/tmp/` + zapis wyniku w tym pliku; ewentualnie domyślne `UserSettings`, README | dwa przebiegi i decyzja |
| 06e Cache Anime | S10 | `services/torrents/nyaa.py` (cache), `services/catalog/anilist.py` + `cache.py`, `bootstrap.py`, testy | testy TTL/round-trip |

Każdy etap: jeden wykonawca Opus po przeczytaniu skilli `simple` i `coding`, integracja i przegląd diffu przez
prowadzącego, bramki root, smoke na żywo, PR stacked na #53 (albo na poprzednim etapie). Feedback: błąd lokalny →
poprawka w etapie; fałszywe założenie (np. inne pola AniList) → przeplanowanie etapu; zmiana wymagania → do właściciela.

## Authority i baseline

Właściciel 2026-09-06: „co godzinę to nieoptymalne, mamy dokładne daty premier”; „co godzinę jest okej, ale po dacie
premiery”; „przez tydzień nic się nie zmieni, nie pytać”; seria zakończona nigdy automatycznie; „qBittorrent nie
powinien działać cały czas, ale nie może zamykać ręcznie otwartego”; „ma działać tak samo albo lepiej”; „znajdź więcej
scenariuszy”. Spec local-automation R09, R17, R18, R23, R24; masterplan 3.3 (kolejność tick), 10.1 (AniList), 10.2
(nyaa). Kod jak w „Impact scan”. Pomiary w tabeli „Stan wyjściowy” z dzisiejszego logu i sond.

# Torrentio jako źródło informacji o wydaniach anime — walidacja części B

## Status i najważniejsza odpowiedź

**Status: DONE w zakresie badania API i źródeł; brak akceptacji integracji lub dowodu E2E.** Pomiary wykonano 22 września 2026 r. Przyjęty i sprawdzony baseline AniShift: `0e8a6bf9194d2786d426d3f3a58f48272b3eb087`. Kontrakt: [pełny brief](../briefs/anime-api-validation.md), część B oraz zasady wspólne; wymagania: [spec.md](workspace/.archive/acquisition/final/spec.md), R-04–R-20. Raport jest samodzielnym wynikiem dotyczącym wydań. Badanie metadanych i harmonogramu należy do części A.

**Odbiór Opus5 `ses_f363d389cffezDZ8NuVvbrAhZX`: PASS WITH FINDINGS, bez błędów materialnych.** Doprecyzowania oparto na zapisanych danych i kodzie, bez zmiany historycznych klasyfikacji; końcowa weryfikacja korekt przez Opus5 `ses_f3631f3eeffes5rFtRdza7pEta`: **PASS**.

**Torrentio rzeczywiście dostarcza szybko listę kandydatów, również oznaczonych providerami innymi niż NyaaSi, oraz często wskazuje konkretny plik w paczce. Nie daje jednak wystarczającego dowodu tożsamości, bieżącej dostępności ani jakości napisów, aby na podstawie samej odpowiedzi automatycznie zatwierdzać pozyskanie.** To najważniejszy wniosek informacyjny, a nie zamówienie implementacji.

W sześciu różnych zapytaniach otrzymano łącznie **194 rekordy stream**, w tym 30 jawnie niezgodnych z żądanym materiałem według nazw. Dwie dodatkowe powtórki służyły wyłącznie pomiarowi. Najważniejsze wyniki:

- **DIRECT:** wszystkie osiem zapytań Torrentio zakończyło się HTTP 200; rzeczywiste czasy od rozpoczęcia żądania do odebrania ciała wyniosły **52,340–245,279 ms**. To mała próbka jednego środowiska, silnie zależna od cache, nie benchmark zimnego wyszukiwania ani obietnica SLA.
- **DIRECT + INFERENCE:** Slime S1E4 zwrócił 47 rekordów: 39 nazwowo zgodnych oraz 8 dotyczących spin-offu lub OAD/OVA. Cowboy Bebop E1 zwrócił 51 rekordów: 29 nazwowo zgodnych i 22 dotyczące innych materiałów, w tym menu i publikacji EPUB.
- **DIRECT:** Slime S4E23 zwrócił 40 rekordów, z czego jeden oznaczony NyaaSi, a 39 innymi providerami. Nie wynika z tego, że pozostałych hashy nie ma na Nyaa.
- **DIRECT:** Slime S4E24, wskazany w briefie jako przyszły względem dnia badania, zwrócił pustą listę. API nie podało przyczyny. To nie jest samodzielny dowód, że odcinek nie został nigdzie opublikowany.
- **DIRECT:** `infoHash` występował we wszystkich 194 rekordach. `fileIdx` i `behaviorHints.filename` występowały w 188. Brakowało ich w sześciu; brak nie oznacza indeksu zero.
- **DIRECT:** rozmiar i liczba seeders były tekstem z emoji w `title`, nie osobnymi polami liczbowymi. Nie otrzymano `leechers`, `peers`, czasu pomiaru seeders ani `videoSize`.
- **DIRECT, kod qB + INFERENCE:** qBittorrent pomija pliki paddingowe w swojej przestrzeni indeksów. Bezwarunkowe przyjęcie `Torrentio.fileIdx == qB.index` jest nieuzasadnione. Nie uruchamiano qB ani pobierania metainfo.

## Wyjaśnienie do odsłuchu

Najprościej powiedzieć, że Torrentio jest sprawnym katalogiem wskazówek o wydaniach. Po podaniu identyfikatora anime i numeru odcinka dostajemy listę potencjalnych plików. Lista może zawierać zarówno osobne wydania odcinka, jak i wskazania do plików wewnątrz dużej paczki. Właśnie ta druga możliwość jest cenna: nie trzeba utożsamiać całego torrenta z jednym odcinkiem.

Przykład ze Slime pokazuje jednocześnie zaletę i ograniczenie. Pierwszy wynik prowadził do paczki EMBER obejmującej kilka sezonów, dodatki i Slime Diaries. Odpowiedź wskazywała jednak konkretnie plik czwartego odcinka pierwszego sezonu. Następny wynik, z innej paczki, wskazywał czwarty odcinek Slime Diaries, czyli inny utwór. Numer odcinka się zgadzał, ale pełna tożsamość już nie. Taki wynik nie powinien być uznany za poprawny tylko dlatego, że dostawca zwrócił go pod właściwym identyfikatorem żądania.

Ten problem nie ograniczał się do bardzo rozbudowanej franczyzy. Dla Cowboy Bebop odpowiedź zawierała też Classic Stars, Mushoku Tensei, Dragon Ball, inne serie, menu innej produkcji i książkę elektroniczną. Z drugiej strony próbka Haibane Renmei była nazwowo spójna we wszystkich dziesięciu wynikach. Nie ma więc podstaw ani do uznania całego dostawcy za bezużytecznego, ani do traktowania jego dopasowań jako prawdy bez kontroli.

Informacje o dostępności również trzeba czytać ostrożnie. Liczba przy ikonie człowieka jest liczbą seeders przechowywaną przez dostawcę. Nie jest liczbą osób połączonych z naszym klientem. Odpowiedź nie mówi, kiedy tę liczbę zmierzono. Szybki HTTP nie rozstrzyga, czy torrent ruszy, czy wszystkie części wskazanego pliku są osiągalne ani jak długo potrwa pobranie.

Podobnie etykieta Multi Subs i polska flaga są deklaracją w opisie, a nie kontrolą ścieżek w pliku. Nie obejrzeliśmy napisów, nie sprawdziliśmy pełnych dialogów, tekstu ekranowego, formatu ASS ani synchronizacji. Nie można z tych etykiet wyprowadzić wniosku, że AniShift może bezpiecznie pominąć tłumaczenie.

Wynik badania jest zatem ograniczony, ale konkretny. Torrentio poszerza zestaw informacji o kandydatach i paczkach. Nie przejmuje odpowiedzialności za intencję użytkownika, prawidłowe rozpoznanie materiału, wybór pliku w qB, potwierdzenie kompletności ani późniejsze przetwarzanie. W tych miejscach pozostają realne kontrakty do spełnienia.

## Metoda, budżet i znaczenie etykiet dowodowych

W raporcie:

- **DIRECT** oznacza zawartość zapisanej odpowiedzi, pomiar lub bezpośrednio odczytany kod. Dowód z kodu nie oznacza wykonania tej ścieżki na hosted endpointzie.
- **REPORTED** oznacza deklarację dokumentacji, źródła zewnętrznego albo wejściowego briefu, bez dodatkowego potwierdzenia runtime.
- **INFERENCE** oznacza interpretację, ocenę zgodności nazw lub wniosek wynikający z dowodów.

Użyto Python 3.14.2 i wyłącznie biblioteki standardowej. Instrument `probe.py` wykonuje sekwencyjne GET przez `urllib.request`, z `timeout=30`, bez sztucznego cachebust, z dwusekundową przerwą między żądaniami. Maksymalnie pięć żądań w partii; wykonane partie mieściły się zdecydowanie poniżej 180 sekund, a limit terminala wynosił 210 sekund. Limit 30 sekund w urllib jest limitem operacji sieciowej, nie osobnym twardym deadline całego pobierania; w tej próbie wszystkie żądania zakończyły się poniżej sekundy.

Instrument ma dodatkowo guard przed rozpoczęciem kolejnej próby po przekroczeniu 145 sekund od początku partii (`probe.py:39–40`). To wcześniejsze zatrzymanie nowych żądań, nie zamiana limitu 180 sekund z briefu w twardy deadline trwającego odczytu.

`perf_counter` obejmował otwarcie HTTP i odczyt całego ciała. Osobno mierzono `json.loads`. Zapis danych na dysk i dwusekundowy odstęp nie wchodzą do czasu HTTP. `bytes` to liczba odebranych bajtów ciała, nie rozmiar pakietów TLS/TCP. Wysłano `Accept-Encoding: identity`. Każdy wynik jest natychmiast wypisywany z flush i zapisywany do pliku metadanych oraz ledgeru.

Zachowano dokładne ciała odpowiedzi, SHA-256, UTC start/koniec, status, URL, czas, liczbę bajtów i bezpieczne nagłówki. Dla JSON zachowano surowe bajty bez ponownej serializacji. `Date` serwera było około osiem sekund wcześniejsze niż zegar lokalny; nie korygowano zegarów. Czas monotoniczny nie zależy od tej różnicy. `Date`, `Age` i `Last-Modified` nie są datą pomiaru seeders.

**Budżet:** 8 GET do `torrentio.strem.fun`, 2 lookupy Kitsu dla identyfikatorów innych tytułów, 0 do ani.zip, 0 do AnimeSchedule. Odczyty publicznego kodu i dokumentacji są osobno w ledgerze. Pierwszy błędnie zapisany adres surowej wiki qB zwrócił 404; skorygowano strukturę URL na `/wiki/qbittorrent/qBittorrent/...`, co dało 200. Nie wystąpiły 403, 429 ani 5xx. Instrument blokował dalsze zapytania do hosta po takich statusach; nie było potrzeby użycia tej gałęzi.

Pełny ledger części B zawiera **32 odpowiedzi: 8 Torrentio + 2 Kitsu + 22 odczyty kodu i dokumentacji** (3 GitHub API i 19 GitHub raw). Statusy: 31 odpowiedzi 200 i jedna 404; zapis `audit.json` rozlicza ten sam zakres. To licznik całej części B, nie 32 zapytania o wydania.

Pierwszy checkpoint przekazano po partii obejmującej S1E4, S4E23, pin kodu Torrentio i dwa lookupy ID: podano oba pomiary, cache `UPDATING` oraz potwierdzone ID. Dalsza analiza odbywała się na zapisanych danych. Nie korzystano z automatycznej oceny PASS z poprzednich zadań.

### Zakres prób i pochodzenie ID

| Scenariusz | Ścieżka po `https://torrentio.strem.fun` | Podstawa identyfikatora |
| --- | --- | --- |
| Slime S1E4 | `/stream/series/kitsu:41024:4.json` | ID z briefu; nowe rzeczywiste zapytanie B i kontrola nazw |
| Slime S4E23 | `/stream/series/kitsu:49235:23.json` | ID z briefu; nowe zapytanie B |
| Slime S4E24 | `/stream/series/kitsu:49235:24.json` | ID i przyszłość odcinka jako REPORTED z briefu; harmonogram nie jest badaniem B |
| Slime S4E10 | `/stream/series/kitsu:49235:10.json` | ID z briefu; nowe zapytanie B |
| Haibane Renmei E1 | `/stream/series/kitsu:354:1.json` | DIRECT: Kitsu lookup po nazwie zwrócił `id=354`, `slug=haibane-renmei` |
| Cowboy Bebop E1 | `/stream/series/kitsu:1:1.json` | DIRECT: Kitsu lookup po nazwie zwrócił `id=1`, `slug=cowboy-bebop` |

Lookupy: `https://kitsu.io/api/edge/anime?filter[text]=Haibane%20Renmei&page[limit]=1` oraz `https://kitsu.io/api/edge/anime?filter[text]=Cowboy%20Bebop&page[limit]=1`. Nie wykonywano dodatkowych badań ich metadanych.

**Special — świadomie bez osobnego GET:** kod `addon.js:81–96` przyjmuje `kitsu:<liczba>:<liczba>` albo samo `kitsu:<liczba>`. Nie przyjmuje `S1` jako tokenu odcinka Kitsu. Gałąź IMDb przyjmuje liczbowy sezon i odcinek, ale to nie potwierdza mapowania konkretnego speciala. Nie uzyskano odrębnego potwierdzonego ID/składni dla wybranego speciala w budżecie dwóch lookupów. Dodatki oceniono tam, gdzie faktycznie pojawiły się w wynikach paczek. Nie wykonano zgadywanego zapytania o `S1` ani nie stwierdzono, że specials są globalnie niewspierane.

To ograniczenie identyfikatora, składni i przydzielonych lookupów w pierwotnej części B, nie globalna blokada dodatków. Późniejszy osobny follow-up po uzyskaniu mapy z A wykonał dwa GET dla Slime OVA i zamknął lukę braku bezpośredniej próby osobnego wpisu OVA. Jego 37 rekordów opisuje [aneks syntezy](anime-api-report.md); nie należą do bazowych 194 ani do ośmiu żądań B i nie dowodzą obsługi wszystkich specials.

## Liczebności, kompletność pól i trafność każdej próbki

Numery wierszy w dalszej części są liczone od 1 według kolejności w surowym `streams`. Ocena dotyczy nazw, katalogu w paczce, sezonu, tytułu i numeru odcinka razem. **„Nazwowo zgodny” nie oznacza zweryfikowanej zawartości pliku.** To INFERENCE na podstawie DIRECT tekstów.

Wariant „niejednoznaczny” zachowano dla samej numeracji absolutnej S4. Związek 23 z 95 występuje w nazwie jednego z wydań i jest zgłoszony w briefie, ale B nie zweryfikowało niezależnie mapowania katalogowego. Tak samo 10 z 82 jest zgłoszone w nazwie Asakura. Nie zamieniono tych poszlak w automatyczny PASS.

| Próbka | Streamy | Unikalne hashe | Unikalne `(hash, fileIdx)`* | Nazwowo zgodne | Niejednoznaczne | Błędne | Brak `fileIdx` / `filename` | Obecne `sources` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Slime S1E4 | 47 | 42 | 47 | 39 | 0 | 8 | 0 / 0 | 39 |
| Slime S4E23 | 40 | 40 | 40 | 35 | 5 | 0 | 2 / 2 | 6 |
| Slime S4E24 | 0 | 0 | 0 | 0 | 0 | 0 | nie dotyczy | 0 |
| Slime S4E10 | 46 | 46 | 46 | 45 | 1 | 0 | 0 / 0 | 42 |
| Haibane E1 | 10 | 10 | 10 | 10 | 0 | 0 | 0 / 0 | 10 |
| Bebop E1 | 51 | 50 | 51 | 29 | 0 | 22 | 4 / 4 | 23 |
| S1E4 powtórka | 47 | 42 | 47 | 39 | 0 | 8 | 0 / 0 | 39 |
| S4E23 powtórka | 40 | 40 | 40 | 35 | 5 | 0 | 2 / 2 | 6 |

\* W analizie brak `fileIdx` jest osobnym sentinelem `None`, nie zerem i nie prawidłowym selektorem. Liczba par z rzeczywiście obecnym indeksem wynosi odpowiednio 47, 38, 0, 46, 10 i 47 dla sześciu różnych zapytań. Nie znaleziono duplikatów par w obrębie żadnej próbki. Nie należy sumować liczby hashy jako globalnej liczby unikalnych torrentów: ta sama paczka Rutor występuje przy S4E10 i S4E23.

Ponowne zliczenie sześciu różnych odpowiedzi daje **187 globalnie unikalnych hashy w 194 rekordach**. Ten licznik nie obejmuje powtórek ani późniejszego follow-upu OVA.

**DIRECT, walidacja kształtu:** wszystkie 194 `infoHash` są tekstami o 40 znakach szesnastkowych; 188 obecnych `fileIdx` to nieujemne liczby całkowite, bez jawnego null i bez błędnego typu. Wszystkie rekordy mają tekstowe `name`, `title` i obiekt `behaviorHints` z tekstowym `bingeGroup`. W obecnych `filename` i `sources` nie znaleziono null ani błędnego typu. To walidacja kształtu, nie istnienia torrenta, zakresu indeksu ani zgodności z metainfo. Zbiorcza nazwa licznika `invalid_or_missing_fileIdx` w `analysis.json` w tych danych oznacza wyłącznie brak pola.

### Slime S1E4: paczka pomaga, ale miesza role materiałów

**DIRECT:** pierwszy wynik to NyaaSi/EMBER, hash `aa3d7f95745c1564da5dc335a6865a2cb1765ab2`, `fileIdx=3`, plik `S01E04-In the Kingdom of the Dwarves [D1DC0293].mkv`, ścieżka w `title`: `01. Season 1 + Special/...`. Opis pokazuje `👤 320` i `💾 592.94 MB`. Nazwa paczki obejmuje sezon 1, sezon 2, OVA, specials i Slime Diaries. Wybrany plik jest nazwowo zgodny z żądanym odcinkiem; nie potwierdzano faktycznej zawartości.

Osiem błędnych wierszy: **2, 9, 11, 12, 27, 34, 44, 47**. Trzy wskazują Slime Diaries/Tensura Nikki, pięć OAD/OVA. Szczególnie czytelna jest para Trix: ten sam hash `21ff74256476e035de1de7e04fa368a0abbe9886` ma wiersz 2 z `fileIdx=56`, ścieżką `Tensura Nikki/...S01E04...`, i wiersz 3 z `fileIdx=3`, ścieżką `01 - Season 1/...S01E04...`. Deduplikacja tylko po hashu usunęłaby rozróżnienie pomiędzy dwoma różnymi materiałami.

Wiersze 12 i 47 pokazują jeszcze subtelniejszy przypadek: basename wygląda jak zwykły `Tensei ... - 04`, lecz nazwa wydania nadrzędnego mówi `01 ~ 05 (OAD)`. Dlatego kontrola samego `behaviorHints.filename` albo samego numeru odcinka jest niewystarczająca.

### Slime S4E23 i E10: wiele providerów, część numeracji absolutnej

W S4E23 pierwsza pozycja to Doomdos/TorrentGalaxy, `Torrentio\n4k`, `behaviorHints.filename` z `Season 4 - 95`, `414.3 MB`, `👤 52`. Pole `title` jest tu ucięte i samo nie zachowuje numeru 95; tak samo jest w wierszu 17. Druga pozycja to Erai-raws/TorrentGalaxy, jawnie `4th Season - 23`, `927.39 MB`, `👤 247`, MultiSub i flagi, w tym polska. Jest to dobry przykład tego, że pierwszy wynik nie jest po prostu rekordem z największą liczbą seeders, a nazwa `4k` nie dowodzi najwyższej jakości.

Niejednoznaczne wiersze S4E23 to **1, 10, 12, 17, 38**, wskazujące odcinek absolutny 95. Wiersz 19 ma jednocześnie `4th Season - 23(95)` i jest nazwowo zgodny. Brak `fileIdx` i `filename` w wierszach **12 i 30**. Wiersz 30 zawiera czytelne `S04E23` w opisie, ale nadal nie ma konkretnego selektora pliku.

W S4E10 pierwszy wynik Asakura/NyaaSi ma `4th Season - 10`, dopisek `Episode 82`, `1.36 GB` i `👤 1020`. Wiersz 39 Kosaka zawiera wyłącznie absolutne 82 — pozostawiono niejednoznaczność mapowania. Wiersze Rutor pokazują wiele hashy paczek z zakresami kończącymi się na 12, 13, 14, 17, 18, 19, 20, 22 lub 23. Nazwa i rozmiar odcinka 10 mogą być takie same w różnych paczkach. Nie jest to dowód identyczności bajtowej plików ani przesłanka do powtórnego pozyskiwania tego samego żądanego odcinka.

Ten sam hash Rutor `8bc1d7ef5ab0715d2c457eeb996dd00800464d4d` występuje przy E10 z `fileIdx=9` i przy E23 z `fileIdx=22`. To DIRECT dowód, że endpoint przedstawia wybrane pliki jednej paczki przy różnych odcinkach. Nie jest to pełny manifest paczki.

### Slime S4E24: pusto, bez przyczyny

Całe ciało odpowiedzi ma 75 bajtów:

```json
{"streams":[],"cacheMaxAge":60,"staleRevalidate":14400,"staleError":604800}
```

Nie ma pola „niewydany”, statusu harmonogramu, wyjaśnienia błędu indeksowania ani deklaracji kompletności. Z perspektywy B można powiedzieć wyłącznie: w tej odpowiedzi nie znaleziono kandydatów. Ustalenie „jeszcze niewydany” wymaga niezależnej informacji czasowej i pozostaje domeną części A.

### Haibane i Bebop: starsze anime nie dają jednego prostego wyniku

Haibane E1 dało dziesięć nazwowo zgodnych wyników, wszystkie z etykietą NyaaSi. Pierwszy to `[DB]Haibane Renmei_-_01_...`, `fileIdx=0`, `299.62 MB`, `👤 87`. W wynikach są etykiety 1080p, 720p, 480p, DVDRip i DVD, a także `Torrentio` bez określonej jakości. Największa liczba seeders w próbce — 143 — dotyczy pozycji z etykietą 480p/DVD. Nie sprawdzano jakości mastera ani skalowania obrazu.

Bebop E1 zawiera 29 nazwowo zgodnych wyników. Pierwszy ma `S01E01 - Asteroid Blues`, paczkę `COWBOY BEBOP 1440p`, `1.69 GB`, `👤 18`. Wynik PHTM/nekoBT ma jawne `Cowboy Bebop - S01E01`, `1.06 GB`, `👤 290`. Są też paczki z dodatkami, filmem i wieloma produkcjami Shinichiro Watanabe, w których wybrany plik nadal wskazuje właściwy odcinek.

Błędne wiersze Bebop to **10–13, 16–28, 30, 34–36, 51**: 22 łącznie. Wśród nich są Classic Stars, Haibara-kun, Mushoku Tensei S3, Kyoukai Senki, Dragon Ball, inne jawnie odmienne tytuły koreańskie/chińskie oraz Grandmaster of Demonic Cultivation. Wiersz 24 wskazuje `SPs/...Menu 01...`, a 51 ma opis `[Light Novel] AHEAD Series Owari no Chronicle v01-02 (epub)`. Błędne przypisania są zatem szersze niż pomylenie sezonu.

Rozkład tych 22 błędów: **17 TorrentGalaxy, 4 NyaaSi, 1 EXT**. W próbce Bebop dwie z 19 pozycji TorrentGalaxy są nazwowo zgodne. To lokalna obserwacja, nie pomiar ogólnej jakości indeksu. Nie znamy przyczyny zasilenia błędnych rekordów. Kod odczytu pyta bazę po Kitsu ID i odcinku; nie ma podstaw, by bez dodatkowego dowodu przypisać błąd konkretnej warstwie ingestu albo traktować ID 1 jako specjalny sentinel.

## Providery poza Nyaa i znaczenie `sources`

Poniżej są **etykiety faktycznie widoczne w odpowiedziach**, wyciągnięte z fragmentu `⚙️` w `title`. Nie wykonano bezpośrednich odczytów tych indeksów. Powtórki Slime miały identyczne ciała, więc ich rozkład jest ten sam.

| Etykieta providera | S1E4 | S4E23 | S4E24 | S4E10 | Haibane E1 | Bebop E1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NyaaSi | 33 | 1 | 0 | 12 | 10 | 21 |
| TorrentGalaxy | 2 | 24 | 0 | 0 | 0 | 19 |
| nekoBT | 1 | 4 | 0 | 18 | 0 | 1 |
| Rutor | 5 | 1 | 0 | 12 | 0 | 0 |
| 1337x | 4 | 0 | 0 | 0 | 0 | 5 |
| EXT | 1 | 5 | 0 | 0 | 0 | 1 |
| ThePirateBay | 1 | 0 | 0 | 1 | 0 | 2 |
| EZTV | 0 | 5 | 0 | 2 | 0 | 0 |
| Cinecalidad | 0 | 0 | 0 | 1 | 0 | 0 |
| RARBG | 0 | 0 | 0 | 0 | 0 | 1 |
| TokyoTosho | 0 | 0 | 0 | 0 | 0 | 1 |

**DIRECT:** widziano dziesięć różnych etykiet poza NyaaSi. Zera w tej tabeli oznaczają brak danej etykiety w tej próbce, a nie globalny brak wydań u providera. Historyczna lub aktualna etykieta nie potwierdza, że indeks dziś działa i został właśnie odpytany.

**DIRECT, kod:** `repository.js` ma jeden `provider` na rekord torrentowy identyfikowany hashem. `streamInfo.js` przenosi go do opisu. Lista w `filter.js:3–123` deklaruje 25 opcji: YTS, EZTV, RARBG, 1337x, EXT, ThePirateBay, KickassTorrents, TorrentGalaxy, MagnetDL, HorribleSubs, NyaaSi, TokyoTosho, AniDex, nekoBT, Rutor, Rutracker, Comando, BluDV, MicoLeaoDublado, Torrent9, ilCorSaRoNeRo, MejorTorrent, Wolfmax4k, Cinecalidad i BestTorrents. Deklarowane opcje nie są dowodem bieżącego pokrycia. W szczególności BestTorrents w kodzie nie dowodzi znalezienia polskiego wydania w próbie.

**DIRECT + REPORTED:** `sources` jest tablicą stringów `tracker:...` i `dht:...`, zgodnie z dokumentacją Stremio. W sześciu różnych próbkach wystąpiło w 120 rekordach; łącznie 3122 wpisy `tracker` i 120 wpisów `dht`. To powtórzone wpisy w różnych streamach, nie 3242 unikalne źródła wydań. Nie ma tam obiektów z nazwą providera ani statystykami peers.

Kod `magnetHelper.js:78–96` pokazuje, że dla providerów anime `sources` może być zastępowane wspólną listą trackerów, a dla rosyjskich rozszerzane listą wspólną. Zatem nawet tracker o nazwie Nyaa nie dowodzi pochodzenia rekordu z indeksu Nyaa. Brak `sources` także nie oznacza braku trackerów w metainfo ani nieosiągalności DHT. Żadnego trackera ani swarmu nie kontaktowano.

## Pełny inventory pól napotkanych w próbce

Podstawą jest sześć różnych odpowiedzi, czyli 194 streamy. Dwie powtórki nie wnoszą nowych pól. Nie znaleziono dodatkowych kluczy poza poniższą listą. `sources[]` to opis elementu tablicy, nie osobny klucz JSON. Wszystkie obecne wartości w tej tabeli miały **zero jawnych null**.

| Ścieżka | Typ JSON i obecność | Przykład | Znaczenie i moc dowodu |
| --- | --- | --- | --- |
| `streams` | array, 6/6 korzeni | `[]` przy E24 | DIRECT: lista kandydatów; REPORTED: odpowiedź Stremio stream |
| `cacheMaxAge` | integer, 6/6 | `3600`, dla pustej listy `60` | DIRECT: sekundy parametru cache; kod mapuje do `max-age` |
| `staleRevalidate` | integer, 6/6 | `14400` | DIRECT: kod mapuje do `stale-while-revalidate` |
| `staleError` | integer, 6/6 | `604800` | DIRECT: kod mapuje do `stale-if-error` |
| `streams[].name` | string, 194/194 | `Torrentio\n1080p` | Etykieta dodatku i tekstowa jakość; nie pomiar wideo |
| `streams[].title` | string, 194/194 | nazwa wydania, czasem ścieżka, `👤 320 💾 592.94 MB ⚙️ NyaaSi` | Opis prezentacyjny, nie schema statystyk; może być skrócony znakiem `…` |
| `streams[].infoHash` | string, 194/194 | `aa3d7f95745c1564da5dc335a6865a2cb1765ab2` | REPORTED: identyfikator torrenta; DIRECT: poprawny kształt 40-hex w próbce |
| `streams[].fileIdx` | integer, 188/194; brak 6 | `3`, `0`, `109` | REPORTED: indeks pliku w torrencie; DIRECT: przekazany z `record.fileIndex`; nie numer odcinka |
| `streams[].behaviorHints` | object, 194/194 | obiekt z dwoma lub jednym kluczem | Opcjonalne wskazówki zachowania klienta |
| `streams[].behaviorHints.bingeGroup` | string, 194/194 | `torrentio\|1080p\|Erai-raws` lub `torrentio\|<hash>` | REPORTED: wybór podobnego streamu przy kolejnym odcinku; nie ID sezonu lub franczyzy |
| `streams[].behaviorHints.filename` | string, 188/194; brak 6 | `S01E04-In the Kingdom of the Dwarves [D1DC0293].mkv` | DIRECT: basename pliku; kod usuwa katalogi przez `split('/').pop()` |
| `streams[].sources` | array of string, 120/194; brak 74 | `tracker:...`, `dht:...` | REPORTED: wskazówki odkrywania peers; nie lista indeksów |
| `streams[].sources[]` | string, 3242 elementy | `tracker:http://tracker.opentrackr.org:1337/announce` | DIRECT: wyłącznie prefiksy `tracker` i `dht`; brak zagnieżdżonych pól |

### Co występuje jedynie jako tekst, a czego w ogóle nie otrzymano

DIRECT: w **33 z 194 rekordów** pole `title` zawiera znak ucięcia `…`. Pełniejsza nazwa może pozostawać w `behaviorHints.filename`, lecz basename nie odzyskuje całego katalogu paczki. Osobny mechanizm w kodzie `streamInfo.js:15–24` pomija linię ścieżki, gdy `sameInfo` jest prawdziwe: brak całkowitego indeksu pliku, względna różnica rozmiaru pliku i torrenta poniżej 5% albo tytuł pliku zawierający tytuł torrenta. To nie jest to samo co ucięcie `title` ani brak `sources`; liczba 74 braków `sources` w inventory nie jest licznikiem brakujących ścieżek. Nie podajemy niezweryfikowanej liczby braków ścieżki.

| Informacja | Stan live | Interpretacja |
| --- | --- | --- |
| Seeders | Tekst `👤 N` w 194/194 | Liczba do parsowania z prezentacji; nie ma pola `seeders` |
| Leechers | Brak strukturalnie i brak osobnego oznaczenia w opisach | **Nieznane, nie zero** |
| Peers / connected peers | Brak | Nie wykonano połączenia klienta torrent |
| Timestamp pomiaru seeders | Brak | Nagłówki cache nie zastępują tej informacji |
| Rozmiar | Tekst `💾 ... MB/GB` w 194/194 | Zaokrąglenie, nie dokładne bajty |
| `videoSize`, `size`, `torrentSize` | Brak pól we wszystkich streamach | Nie ma dokładnego rozmiaru wybranego wideo ani całej paczki |
| `filename` w korzeniu stream | Brak | Nazwa jest w `behaviorHints.filename`; czasem pełniejsza ścieżka w `title` |
| `description` | Brak | Dokumentacja Stremio opisuje następcę `title`, ale live używa `title` |
| `url`, `externalUrl` | Brak | Live badano zwykły wariant torrentowy, bez debrid |
| `subtitles` | Brak w 194 rekordach live | Kod `streamInfo.js:55` zawiera `subtitles: getSubtitles(record)`; brak w próbie nie oznacza globalnego braku obsługi napisów |
| Języki | Tekst flag i nazw, np. `Multi Subs`, `Dual Audio`, `Dubbed`, `Multi Audio` | Nie ma oddzielnych tablic języków audio i napisów ani ścieżek kontenera |
| Grupa | Nazwa w nawiasach lub sufiksie, czasem fragment `bingeGroup` | Nie ma osobnego `group` i oceny reputacji |
| Kodek / bit depth / audio | Nazwy: AV1, HEVC/x265, AVC/x264, 10bit, AAC, FLAC, Opus, TrueHD, MPEG2, XviD | Deklaracje w nazwach; brak technicznego pomiaru strumienia |
| Źródło obrazu | Tekst: BD/BDRip/BluRay, DVD, WEB-DL, WEBRip, TV, REMUX, CR, NF, BILI, AT-X | Nie mylić ze `sources` ani providerem indeksu |
| Rozdzielczość / quality | Tekst `name`, np. 4k, 1440p, 1080p, 810p, 720p, 480p, DVD, DVDRip, XviD, TeleSync; czasem brak | Nie zawsze jest to rozdzielczość; nie dowodzi faktycznej jakości |
| HDR / Dolby Vision | Brak osobnego pola; nie stwierdzono jednoznacznej etykiety HDR w próbce | Kod obsługuje parsowanie HDR, ale to nie dowód obecności HDR live |
| Czas trwania / bitrate / kompletność | Brak | Nie można obliczyć bitrate z samego rozmiaru ani zatwierdzić kompletnych mediów |
| Lista całej paczki / relacje extras | Brak | Endpoint zwraca kandydatów dla żądania; nie pełne drzewo plików |
| Flaga ucięcia / next page / total count | Brak | Liczba zwróconych streamów nie jest deklaracją kompletnego pokrycia |

## Seeders, leechers, rozmiary i napisy — granice danych

### Liczby seeders nie są pomiarem dostępności u użytkownika

**DIRECT, kod:** `streamInfo.js:25–28` formatuje `record.torrent.seeders` do `title`. `repository.js:20–33` przechowuje seeders w bazie, a zapytanie dla Kitsu wybiera rekordy uporządkowane po tym polu. Odczyt stream nie wykonuje w prześledzonej ścieżce zapytania o swarm. Nie znaleziono w publicznym drzewie kodu procesu, który pozwoliłby ustalić częstotliwość aktualizacji seeders. Taki harmonogram pozostaje nieznany.

| Próbka | Zakres liczb `👤` | Brak liczby w niepustych rekordach |
| --- | ---: | ---: |
| S1E4 | 1–320 | 0 |
| S4E23 | 2–247 | 0 |
| S4E24 | nie dotyczy | nie dotyczy |
| S4E10 | 1–1020 | 0 |
| Haibane E1 | 1–143 | 0 |
| Bebop E1 | 5–1202 | 0 |

**REPORTED, qB API:** `num_complete` i `num_incomplete` opisują liczby w swarmie, natomiast `num_seeds` i `num_leechs` w liście torrentów opisują połączenia klienta. To inne pojęcia niż tekst Torrentio. Nie odczytano żadnej z tych wartości z uruchomionego qB. Puste pole leechers nie może zostać zapisane jako zero; dodatnie seeders w opisie nie są gwarancją postępu pobierania.

### Rozmiar pliku nie jest rozmiarem całej paczki

**DIRECT, kod:** `streamInfo.js:27` formatuje `record.size`, a nie `record.torrent.size`. Model bazy odróżnia `File.size` od `Torrent.size`. `formatSize` dzieli przez potęgi **1024**, zaokrągla do dwóch miejsc i wyświetla etykiety `MB`, `GB` itd. Oznaczenia są więc prezentacyjne; przeliczenie z powrotem nie odzyska dokładnych bajtów. W kodzie zero lub sentinel `300000000` może także spowodować pominięcie rozmiaru, choć takich braków w tej próbce nie było.

Wskazanie EMBER `592.94 MB` odnosi się w modelu do rekordu wybranego pliku, nie całej kolekcji sezonów. Przy rekordach bez `fileIdx` nie potwierdzono, jak ingest wyznaczył `File.size`; nie należy na tej podstawie zapewniać, że znamy dokładny rozmiar jednego wideo. Dokumentowane Stremio `behaviorHints.videoSize` oznacza bajty pliku wideo, ale **nie wystąpiło w żadnej odpowiedzi**.

Duże różnice, np. S1E4 około 178 MB w jednym opisie i 5,9 GB w innym, nie są same w sobie oceną jakości. Nie mierzono bitrate, długości, mastera, filtrowania, skali, generacji kodowania ani jakości dźwięku.

### Flagi językowe są deklaracją, nie badaniem ścieżek

**DIRECT, kod:** `getLanguages` parsuje nazwy torrenta i pliku oraz deklarację języków providera. Dla anime usuwa wyświetlanie japońskiego; w określonych przypadkach ukrywa też samo angielskie oznaczenie. Brak flagi japońskiej nie dowodzi braku japońskiego audio. Sposób prezentacji nie rozdziela jednoznacznie języka audio od języka napisów.

W S4E23 widziano polską flagę m.in. przy Erai-raws, Onalrie i części ToonsHub/VARYG. W Bebop Erai-raws opis paczki zawiera `POL`, a prezentacja polską flagę. **Nie oceniono faktycznej kompletności dialogów, jakości tłumaczenia, piosenek, tekstu ekranowego, stylów ASS, fontów ani synchronizacji.** `ASSx2`, `MultiSub`, reputacja grupy i liczba flag pozostają deklaracjami nazw. Nie dają dowodu spełnienia R-17.

DIRECT z kodu: `streamInfo.js:55,118–131` przewiduje pobranie i wzbogacenie `subtitles`. Nie uzyskano takiego pola w badanych odpowiedziach ani nie przetestowano tej ścieżki. Jest to rozróżnienie możliwości widocznej w kodzie od faktycznie otrzymanych informacji o napisach.

Dodatkowy sygnał niepewności parsera: S4E23 wiersz 38 ma `name=Torrentio\nTeleSync`, choć filename opisuje przechwycenie `AT-X 1440x1080 MPEG2 AAC` i kończy się `.ts`. Rozbieżność jest DIRECT; hipoteza pomylenia TS z TeleSync to INFERENCE, nie zdiagnozowana przyczyna w parserze. Nie odrzucano ani nie oceniano tego obrazu po samej etykiecie.

## Paczki i kontrakt `fileIdx` → qBittorrent

### Co naprawdę deklarują źródła

**REPORTED, Stremio:** `infoHash` wskazuje torrent, a `fileIdx` indeks pliku. Brak `fileIdx` oznacza domyślny wybór największego pliku przez klienta Stremio. Dla AniShift nie jest to równoważne wyborowi żądanego odcinka. Dokumentacja nie daje gwarancji zgodności z indeksowaniem API qB.

**DIRECT, Torrentio:** `toStreamInfo` kopiuje `record.fileIndex` bez przeliczenia do `fileIdx`; `filename` powstaje tylko przy całkowitym `fileIndex`. Publiczny model przechowuje ten indeks, ale w sprawdzonym drzewie nie ma kodu ingestu ustalającego jego pierwotną kolejność. Obsługa Real-Debrid w kodzie używa `fileIndex + 1` przy porównaniu z ID usługi, co wspiera interpretację zera jako początku indeksowania. Nie dowodzi to wspólnej numeracji z qB, obsługi paddingu ani poprawności konkretnego rekordu live.

**REPORTED, qB WebAPI 5.0:** `GET /api/v2/torrents/files` daje m.in. `index`, `name` z relatywną ścieżką i dokładne `size`. `filePrio` przyjmuje ID plików; od API 2.8.2 dokumentacja zaleca użycie jawnego `index`, nie pozycji w potencjalnie przefiltrowanej tablicy. Brak metadanych jest błędem 409 przy zmianie priorytetu.

### Istotny wynik kontroli kodu qB

Zamrożony kod qBittorrent `705708085ccd957f42a315df7ef97aa27b0a85a6` pokazuje:

1. `TorrentInfo` przechodzi po natywnych indeksach libtorrent i dodaje je do `m_nativeIndexes` **tylko wtedy, gdy nie są plikami paddingowymi** (`torrentinfo.cpp:59–70`).
2. `filesCount()` zwraca długość tej przefiltrowanej listy, a `filePath` i `fileSize` odwołują się do `m_nativeIndexes[index]` (`121–125`, `149–180`).
3. WebAPI `getFiles` publikuje własny `index`, nazwę i rozmiar; `filePrioAction` waliduje ID względem własnej liczby plików (`torrentscontroller.cpp:326–364`, `1455–1494`).
4. `TorrentImpl::prioritizeFiles` mapuje priorytety z indeksów qB na indeksy natywne, z uwzględnieniem `.pad` (`torrentimpl.cpp:3030–3058`).

**INFERENCE:** jeżeli indeks w Torrentio obejmuje natywną listę wraz z paddingiem, a przed wybranym wideo jest padding, to numer może różnić się od qB. Przykład logiczny, nie wykonany test: natywne `[videoA, pad, videoB]` i bezpaddingowe `[videoA, videoB]` dają dla `videoB` odpowiednio 2 i 1. Nie ustalono, czy indeksy badanych torrentów rzeczywiście obejmują padding. Już sam brak tego ustalenia uniemożliwia obietnicę bezwarunkowej zgodności.

**Wniosek informacyjny:** `fileIdx` należy traktować jako wskazówkę dostawcy, którą trzeba uzgodnić z tożsamością torrenta, listą plików, pełną relatywną ścieżką i rozmiarem po stronie qB. Basename może być nieunikalny; tekstowy zaokrąglony rozmiar nie wystarcza jako dokładny identyfikator. W paczce należy również rozstrzygnąć pliki towarzyszące, zamiast utożsamiać jedno wideo z kompletnym materiałem. Odpowiedź Torrentio nie dostarczyła pełnego manifestu potrzebnego do potwierdzenia takich zależności.

**Nie wykonano testu runtime qB, lokalnego testowego torrenta, pobrania metainfo, połączeń DHT/tracker ani payloadu anime.** Przeanalizowany commit qB nie jest deklaracją wersji zainstalowanej u użytkownika. To source review kontraktu; nie E2E. R-08 i R-20 nie zostały zatwierdzone jako gotowa integracja.

## Rzeczywiste czasy HTTP i cache

Wszystkie poniższe statusy to 200. UTC pochodzi z lokalnego zegara; pełna precyzja i osobny koniec są w plikach `.meta.json`.

| Próbka | UTC start 2026-09-22 | HTTP do końca ciała, ms | JSON parse, ms | Bajty ciała | `CF-Cache-Status` | `Age`, s |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| S1E4 | 15:16:34.604442 | 154,465 | 0,609 | 75 793 | UPDATING | 6668 |
| S4E23 | 15:16:36.761639 | 52,340 | 0,166 | 24 435 | UPDATING | 6497 |
| S4E24 | 15:17:37.622190 | 237,761 | 0,016 | 75 | EXPIRED | brak |
| S4E10 | 15:17:39.861297 | 79,031 | 0,302 | 76 915 | UPDATING | 6517 |
| Haibane E1 | 15:17:41.956892 | 245,279 | 0,111 | 17 168 | MISS | brak |
| Bebop E1 | 15:17:44.216840 | 149,997 | 0,255 | 53 994 | EXPIRED | brak |
| S1E4 powtórka | 15:18:11.348980 | 79,317 | 0,344 | 75 793 | HIT | 96 |
| S4E23 powtórka | 15:18:13.430556 | 66,513 | 0,157 | 24 435 | HIT | 96 |

**DIRECT:** SHA-256 potwierdza identyczność ciał każdej pary powtórek. Zmieniły się nagłówki cache. S1E4 przyspieszyło, S4E23 w powtórce było wolniejsze; nie wyprowadzono z dwóch punktów stabilnego efektu optymalizacji. Nie obliczano percentyli.

Niepuste odpowiedzi miały `Cache-Control: max-age=3600, stale-while-revalidate=14400, stale-if-error=604800, public`. Pusta odpowiedź miała `max-age=60` i te same dwa okresy stale. `Content-Type` to `application/json; charset=utf-8`; `Content-Length` zgadzał się z odebranymi bajtami. Nagłówki `ETag` i `Expires` nie wystąpiły w tych odpowiedziach Torrentio; `Last-Modified` i `Date` zachowano. Brak `Age` w tabeli oznacza nieobecny nagłówek, nie zero.

**DIRECT, kod a live:** `addon.js` definiuje te same domyślne TTL HTTP. `cache.js` ma dodatkowo cache pamięciowe streamów na dwie godziny i Mongo na trzy dni oraz minutę dla pustych wyników, jeśli Mongo jest skonfigurowane. Nie wiemy, czy hosted endpoint używa dokładnie tego commita i konfiguracji. Dlatego `MISS` CDN nie oznacza zimnej bazy ani świeżego scrapowania. Nawet nowe `Last-Modified` nie jest datą ostatniego sprawdzenia każdego seeda.

**INFERENCE dla szybkości:** pomiar wskazuje, że samo pobranie listy kandydatów może być lekkim etapem. Nie zmierzono pełnego wyszukania tytułu, mapowania sezonu, wieloodcinkowego zlecenia, oczekiwania na metainfo ani transferu. Nie należy mnożyć najlepszego czasu przez liczbę odcinków i nazywać wyniku prognozą hurtowego pozyskania.

## Hosted, kod otwarty, autoryzacja i ograniczenia pokrycia

**DIRECT:** badane zwykłe endpointy hosted odpowiadały bez konta, klucza i konfiguracji debrid. Nie badano płatnych wariantów ani dostępności cache debrid. W odpowiedziach były hashe, nie bezpośrednie URL mediów.

**DIRECT, kod:** repo Torrentio ma licencję Apache License 2.0. README opisuje dodatek odpytywania już zebranych rekordów. Serwer Express, modele Sequelize z `DATABASE_URI`, opcjonalny Mongo cache i Redis limitera pokazują, że self-hosting warstwy dodatku jest odrębnym zagadnieniem od uzyskania oraz utrzymania danych. Sam publiczny kod nie daje dowodu dostępności kompletnej aktualnej bazy. W publicznym drzewie badanego commita są `addon` i `catalogs`, lecz nie znaleziono implementacji ingestu z indeksów; nie tworzono zastępczego scrapera.

**DIRECT, kod:** `serverless.js:25–34` definiuje 5000 żądań na 24 godziny według IP dla obsługiwanej trasy, z Redis. To deklaracja konkretnego kodu, nie potwierdzony limit produkcyjnego CDN i nie przyznany budżet do wykorzystania. Nasz limit pozostał 12, zużyto 8. Nie wywoływano prób obciążeniowych ani blokady limitera.

Ścieżka konfiguracji jest opcjonalna. Kod rozdziela konfigurację znakami `|` i `=`, a warianty debrid obsługują klucze usług. `serverless.js:106–124` definiuje resolver z `apiKey` w URL i przekierowaniem, a `realdebrid.js` konstruuje odpowiednie fragmenty ścieżek z kluczem. **REPORTED/DIRECT kodu, nie live:** konto i token dotyczą gałęzi debrid; nie są wymagane przez wykonane zapytania zwykłe. Tak skonfigurowany URL może zawierać sekret i nie powinien być traktowany jak publiczny identyfikator źródła. Żadnego klucza nie konfigurowano ani nie odczytywano.

**DIRECT, kod:** `getKitsuIdSeriesEntries` ma `limit: 500`; dalej działają filtry providerów, jakości i rozmiaru oraz sortowanie. W próbie użyto domyślnej ścieżki bez własnej konfiguracji; nie osiągnięto 500 wyników. Brak osiągnięcia limitu nie dowodzi pełnego pokrycia katalogu, a odpowiedź nie ma flagi „kompletne”. Jedno zapytanie o odcinek nie potwierdza dostępności całego sezonu z dodatkami.

Nie znaleziono w odczytanych materiałach SLA ani osobnej jednoznacznej licencji gwarantującej korzystanie z hosted endpointu i jego zbioru danych. **To brak ustalenia, nie dowód zakazu korzystania ani gwarancja dostępności.** Apache-2.0 dotyczy kodu; nie zastępuje warunków usługi ani nie zapewnia aktualności indeksów.

## Konsekwencje dla wymagań i koszt informacyjny ewentualnej integracji

Poniższe to wnioski, nie plan implementacyjny ani zmiana specyfikacji.

| Wymagania | Co badanie wspiera | Czego nie rozstrzyga |
| --- | --- | --- |
| R-04–R-05: tytuł i sezon | Zapytanie po potwierdzonym ID prowadzi do listy wydań | Torrentio nie zastępuje katalogu tytułów/relacji; błędne przypisania nie znikają dzięki ID |
| R-06–R-08: dowolny wybór, dodatki, paczki | Konkretny plik i hash są często dostępne; jedna paczka może obsługiwać wiele odcinków | Brak pełnego manifestu, właściwego mapowania dodatków i bezwarunkowej zgodności indeksów qB |
| R-09: pokrycie | Można jawnie pokazać „zwrócono N kandydatów” | Nie można z pustej listy wywieść „niewydany”, ani z listy niepustej „kompletny sezon” |
| R-10–R-14: subskrypcje i publikacja | Lista może być jednym sygnałem znalezienia kandydata | Nie dowodzi trwałości intencji, końca sezonu, polityki czekania lub deduplikacji |
| R-15–R-17: źródło, jakość, napisy | Istnieją deklaracje grupy, kodeka, źródła, języków, rozmiaru i seeders | Brak pomiaru jakości, aktualności peers i kontroli dialogów/tekstu ekranowego |
| R-18–R-20: awarie, wznowienie, kompletne wejścia | Udokumentowane kontrakty wskazują granicę z qB | Nie wykonano pobierania, recovery, restartu ani potwierdzenia kompletności mediów |

**INFERENCE:** najmniejszy rzeczywisty koszt integracji nie kończy się na odczycie JSON. Obejmuje utrzymanie mapowania tożsamości, ocenę pełnej nazwy i kontekstu pliku, rozróżnianie brakujących danych od zera, uzgadnianie indeksów oraz interpretację cache. Prezentacyjne pola seeders/rozmiaru/języków wymagają parsowania tekstu i tolerancji zmian formatu. Nie policzono liczby linii kodu ani roboczogodzin, bo nie wykonano projektu integracji.

Rekomendacja ogranicza się do informacji: **traktować Torrentio jako dodatkowe źródło kandydatów, nie źródło autorytatywnego potwierdzenia poprawności i gotowości materiału**. Próbka uzasadnia ten podział konkretnymi błędami, a nie hipotetyczną ostrożnością. Haibane oraz poprawne pliki w mieszanych paczkach są kontrdowodami wobec zbyt szerokiej tezy, że dostawca zawsze dopasowuje źle. Nie otwierano nowych dużych kandydatów ani kolejnych prób Sonarr.

## Dowody, odtwarzalność i pliki

Własny nowy katalog TEMP:

`C:\Users\MattyMroz\AppData\Local\Temp\opencode\anime-release-b-20260922-01\`

Równoważny używany przy wykonaniu prefiks: `C:\Users\MATTYM~1\AppData\Local\Temp\opencode\anime-release-b-20260922-01\`.

### Mapa pakietu dowodowego

- [`requests.jsonl`](file:///C:/Users/MattyMroz/AppData/Local/Temp/opencode/anime-release-b-20260922-01/requests.jsonl) — kolejność wszystkich GET, URL, statusy, UTC, czas HTTP, JSON parse, bajty, nagłówki, SHA i hash instrumentu.
- [`probe.py`](file:///C:/Users/MattyMroz/AppData/Local/Temp/opencode/anime-release-b-20260922-01/probe.py) oraz `probe-efa6cc071c378959f55ed2b5a62da78de8b969059439ce88c612ddf5c7a5917d.py` — wykonany instrument i identyczny snapshot; SHA-256 `efa6cc071c378959f55ed2b5a62da78de8b969059439ce88c612ddf5c7a5917d`.
- `request-invocations.txt` — odtworzone pojedyncze wywołania z tym samym instrumentem, etykietą i URL; wykonanie pierwotne grupowało je w sekwencyjne partie do pięciu, zgodnie z ledgerem. To dokumentacja wykonanych odczytów, nie zalecenie ich ponawiania.
- `*.body.json` / `*.body.txt` — dokładne odpowiedzi; `*.meta.json` — osobne rekordy pomiarowe.
- [`analysis.json`](file:///C:/Users/MattyMroz/AppData/Local/Temp/opencode/anime-release-b-20260922-01/analysis.json) — liczebności, providery, seeders tekstowe, obecność pól, kategorie i inventory dla sześciu różnych scenariuszy.
- [`classifications.json`](file:///C:/Users/MattyMroz/AppData/Local/Temp/opencode/anime-release-b-20260922-01/classifications.json) — 194 oceny z numerem wiersza, hashem, indeksem, nazwą, opisem i uzasadnieniem. Kategorie są wynikiem ręcznej oceny zapisanej w instrumencie, nie automatycznie wytrenowanym klasyfikatorem.
- `stream-rows.md` — czytelny wydruk wszystkich 194 rekordów do review, bez powtórek.
- `analyze.py` i `analyze-<SHA256>.py` — wykonana analiza offline i snapshot finalnej wersji; wcześniejsze wykonania służyły obejrzeniu danych i doprecyzowaniu inventory.
- `torrentio-head.body.json`, `torrentio-tree.body.json`, `torrentio-paths.txt`, `qb-head.body.json` — piny i mapa źródeł.
- [`audit.json`](file:///C:/Users/MattyMroz/AppData/Local/Temp/opencode/anime-release-b-20260922-01/audit.json) — wynik ponownego przeliczenia SHA i bajtów oraz sprawdzenia budżetów.
- `evidence-sha256.json` — manifest sum kontrolnych instrumentów i artefaktów w TEMP, bez samego manifestu.

Linki `file:///` wymagają dostępu do tej maszyny; mogą nie być klikalne w każdym rendererze. Pełna ścieżka powyżej pozostaje rozstrzygająca. TEMP jest pakietem lokalnym i nie został dołączony do kontroli wersji.

### SHA-256 surowych odpowiedzi Torrentio

| Plik `.body.json` | SHA-256 |
| --- | --- |
| `slime-s1e4` | `4fbcfe4073ca60992841237297a05158dbb8ece55fb21c207b7cbfeeb1d1a1f7` |
| `slime-s4e23` | `d2f6fed90c4e66fea8a06e23181d11fb0b519158f9ed9ebfb18daaa2ee382a8f` |
| `slime-s4e24` | `fda161623d94c76fba7b88c3d450d79abfe7770f5d54398079d17c9b440a0b6a` |
| `slime-s4e10` | `cbf2f3ad07a7c48d52434231e25e49da149e21a16e6025c39fd99fb0f9e4b28a` |
| `haibane-e1` | `312793a12d22fc12a3e078e8de4cd5c26d6b270e2f92a3014015c117592a4d3d` |
| `bebop-e1` | `189858afd9d7391bb06f5672f2db0b37d82abd9c75ccfdf7e6d23481aef2680e` |
| `slime-s1e4-repeat` | `4fbcfe4073ca60992841237297a05158dbb8ece55fb21c207b7cbfeeb1d1a1f7` |
| `slime-s4e23-repeat` | `d2f6fed90c4e66fea8a06e23181d11fb0b519158f9ed9ebfb18daaa2ee382a8f` |

### Źródła kontraktów i kodu

Wszystkie odczytane 2026-09-22, zachowane lokalnie z metadanymi i SHA w ledgerze.

1. **Torrentio pin:** [`39015cd654c587b041b327b6db701c423d4ebe97`](https://github.com/TheBeastLT/torrentio-scraper/tree/39015cd654c587b041b327b6db701c423d4ebe97), commit datowany 2026-09-15. Nie potwierdzono identyczności wersji wdrożonej hosted.
2. [`addon/lib/streamInfo.js`](https://github.com/TheBeastLT/torrentio-scraper/blob/39015cd654c587b041b327b6db701c423d4ebe97/addon/lib/streamInfo.js#L12-L56) — pola, tekst seeders/rozmiaru, indeks, basename; `L71–108` — języki i formatowanie rozmiaru. Snapshot `torrentio-streaminfo.body.txt`.
3. [`addon/lib/repository.js`](https://github.com/TheBeastLT/torrentio-scraper/blob/39015cd654c587b041b327b6db701c423d4ebe97/addon/lib/repository.js#L20-L53) — model torrent/file; `L135–146` — Kitsu i limit 500. Snapshot `torrentio-repository.body.txt`.
4. [`addon/addon.js`](https://github.com/TheBeastLT/torrentio-scraper/blob/39015cd654c587b041b327b6db701c423d4ebe97/addon/addon.js#L81-L96) — składnia ID; `L110–122` — pola cache. Snapshot `torrentio-addon.body.txt`.
5. [`addon/lib/magnetHelper.js`](https://github.com/TheBeastLT/torrentio-scraper/blob/39015cd654c587b041b327b6db701c423d4ebe97/addon/lib/magnetHelper.js#L78-L96) — `sources`; `filter.js`, `configuration.js`, `cache.js`, `serverless.js`, `index.js`, `moch/realdebrid.js`, `moch/mochHelper.js`, `README.md`, `LICENSE` — pozostałe opisane kontrakty. Snapshoty o odpowiadających prefiksach `torrentio-`.
6. **Stremio:** [Stream Object](https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/api/responses/stream.md), sekcje `infoHash/fileIdx`, `sources`, `behaviorHints`. Snapshot `stremio-stream.body.txt`, SHA `6bf67644eece77e6bceb2501de20e67bdd1585b48bc65dca8a92d06a411201ce`. Adres ruchomy; zapisany snapshot jest podstawą tego raportu.
7. **qB kontrakt:** [WebUI API qBittorrent 5.0](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-5.0%29), `Get torrent contents`, `Set file priority`, `Get torrent list`. Snapshot `qb-api-corrected.body.txt`, SHA `9a2ec0c4aebdfabd6172d5d6f9842889a52d4125e2afcb30b64264a5f89068ab`.
8. **qB kod:** pin [`705708085ccd957f42a315df7ef97aa27b0a85a6`](https://github.com/qbittorrent/qBittorrent/tree/705708085ccd957f42a315df7ef97aa27b0a85a6), commit datowany 2026-09-21. [`torrentinfo.cpp:59–70`](https://github.com/qbittorrent/qBittorrent/blob/705708085ccd957f42a315df7ef97aa27b0a85a6/src/base/bittorrent/torrentinfo.cpp#L59-L70), [`torrentscontroller.cpp:326–364`](https://github.com/qbittorrent/qBittorrent/blob/705708085ccd957f42a315df7ef97aa27b0a85a6/src/webui/api/torrentscontroller.cpp#L326-L364), [`torrentimpl.cpp:3030–3058`](https://github.com/qbittorrent/qBittorrent/blob/705708085ccd957f42a315df7ef97aa27b0a85a6/src/base/bittorrent/torrentimpl.cpp#L3030-L3058). Snapshoty `qb-torrentinfo.body.txt`, `qb-controller.body.txt`, `qb-torrentimpl.body.txt`.

## Niewiadome, odchylenia i zamknięcie

Pozostają jawnie nieustalone: częstotliwość aktualizacji seeders, pochodzenie i przyczyna błędnych przypisań, rzeczywista osiągalność plików, pełne pokrycie sezonów i dodatków, skład paczek, dokładne bajty mediów, zawartość ścieżek napisów, indeksowanie paddingu po stronie ingestu Torrentio, zgodność z konkretnym runtime qB oraz wersja i warunki hosted endpointu.

Odchylenia: bez osobnej próby special z braku potwierdzonego mapowania/składni konkretnego materiału; numeracja absolutna S4 pozostawiona warunkowa; jedna korekta URL dokumentacji po 404. To ograniczenia dowodowe, nie ukryte sukcesy. Przedstawione pomiary są nowymi pomiarami HTTP, nie wcześniejszymi 174/249 ms z briefu.

Przeprowadzono lokalną analizę wszystkich streamów, kontrolę kształtu pól, przeliczenie liczebności oraz SHA-256 i długości wszystkich zachowanych odpowiedzi. Nie wykonywano testów aplikacji AniShift, ponieważ nie zmieniono jej kodu. Późniejszy niezależny przegląd Opus5 `ses_f363d389cffezDZ8NuVvbrAhZX` zakończył się **PASS WITH FINDINGS**, bez błędów materialnych. Uzupełniono rozliczenie 32 odpowiedzi, 187 hashy, 33 uciętych opisów, pomijanie ścieżki przez `sameInfo`, obsługę napisów w kodzie, guard czasu i odsyłacz do próby OVA. Historyczne klasyfikacje pozostają bez zmian; korekty oczekują na końcową weryfikację.

**Cleanup:** instrumenty zakończyły się; nie uruchomiono usług ani procesów w tle wymagających zatrzymania. Nie pobrano magnetów, metainfo anime ani mediów, nie uruchomiono qB, nie kontaktowano trackerów, nie użyto kont i nie zmieniono produkcyjnego config/workspace. Jedynym własnym zapisem w repo jest niniejszy raport; dowody i instrumenty są w nowym TEMP. Bez commitów i dalszej delegacji. Zakres części B został zamknięty.

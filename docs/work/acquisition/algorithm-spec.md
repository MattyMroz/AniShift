---
kind: specification
status: zaakceptowana przez recenzentów (rundy 22–23: astra, opus55, sol61 bez uwag); czeka na akceptację właściciela; §3.1 i §3.5 zmienione decyzjami D1–D3 (2026-10-06) i poprawkami review v16, do review
updated: 2026-10-06
baseline: 9d828708
---

# Specyfikacja: algorytm pozyskiwania odcinka

Kontrakt tego, jak AniShift znajduje wydania odcinka, ocenia je i wybiera jedno. Ma pierwszeństwo przed [spec.md](spec.md) i [planem przepływu](plans/e1-przeplyw-subskrypcji.md) w punktach wymienionych w §10; reszta obu dokumentów obowiązuje bez zmian, w tym bezpieczniki planu przepływu (wykluczenie wypróbowanych, ochrona plików innych celów, limit 3 prób, bramka przyjęcia, H2). Podstawa: ustalenia właściciela i trzy pomiary z 2026-10-05 w [intent.md](intent.md).

## 1. Cel i warunek sukcesu

- **Ręczny wybór:** na górze listy stoi najlepsze wydanie właściwego odcinka, z widoczną oceną jakości i pewnością w %.
- **Subskrypcja:** pobiera właściwy odcinek w najlepszym dostępnym wydaniu, wkrótce po emisji. Lepiej nie pobrać niż pobrać zły odcinek. Każde niepowodzenie jest widoczne z powodem (§8).
- **Odbiór:** zestaw wzorcowy (§9) przechodzi, a właściciel potwierdza wynik na żywo na prawdziwych tytułach. Testy i dokumenty nie zamykają etapu.

## 2. Pojęcia

- **Wydanie** — jeden torrent, klucz: hash BTIH (40 znaków hex; base32 zamieniany na hex). Jeden wiersz listy.
- **Plik odcinka** — plik wideo wewnątrz wydania, identyfikowany ścieżką w torrencie. `fileIdx` Torrentio jest tylko podpowiedzią (U-18).
- **Kandydat** — para (wydanie, plik odcinka), oceniana przez H1 względem celu.
- **Spis plików** — kompletna lista plików torrenta: z TsukiHime `/torrents/{id}`, z odpowiedzi `200` wyszukania po hashu z kompletnym `files` ([a1-recon.md](a1-recon.md) N-1) albo z qBittorrenta po metadanych. Lista TsukiHime jest kompletna, gdy `len(files) == filecount`; lista krótsza (z wyszukania po hashu albo z `/torrents/{id}`) nie jest spisem — wydanie jest wtedy oceniane jak bez spisu, po nazwie, bez potwierdzenia pliku. Pliki z odpowiedzi `202` nie są spisem. Rekord Torrentio to **jeden znany plik**, nie spis.
- **Paczka** — wydanie z więcej niż jednym plikiem wideo odcinków: według spisu plików albo, bez spisu, według zakresu w nazwie wydania (`E01-E04`, `Batch`, istniejące `is_pack`). Pliki towarzyszące (napisy, `.mka`, fonty) nie tworzą paczki. Niejednoznaczny plik zostaje w zliczaniu: dodatkiem (niewliczanym, chyba że w spisie nie ma innego wideo) jest tylko plik ze znacznikiem NCOP/NCED/creditless (z numerem w dowolnej formie) albo w katalogu/z sufiksem dodatków Plex (także `Extras`), i to wyłącznie, gdy w całej ścieżce w torrencie (katalogi i nazwa pliku) po usunięciu tagów technicznych, CRC i numeru samego znacznika nie zostaje żaden znak liczbowy Unicode (cyfry dowolnego pisma, indeksy górne, liczby rzymskie). PV, CM, trailer, teaser, menu, preview, yokoku, OP i ED liczą się jako wideo odcinka. Znane ograniczenie: seria z NCOP/NCED/creditless w tytule, której pliki odcinków nie mają innych cyfr, może zostać uznana za dodatki.
- **Konflikt** — jawna sprzeczność z celem rozpoznana przez H1: werdykt `niezgodny` albo `niepewny` z powodem jawnej sprzeczności (inny sezon, część, dzieło, numer w tej samej numeracji, rodzaj materiału; np. „Package explicitly identifies a different season.”). Zamknięta lista powodów sprzeczności powstaje w planie z istniejących powodów H1 i ma test. Eksperymentalne weta z badania 2 nie są konfliktem.
- **Pewność** — estymata modelu (§4), że kandydat to zamówiony odcinek.
- **Jakość** — punkty cech wydania (§5), niezależne od pewności.
- **Użyteczny** — kandydat, którego automat mógłby przetworzyć: nie paczka, nie niejednoznaczny plik (§3.4), nie sam dubbing, bez `RAW`/`HardSub`, obsługiwany kontener, plik nieprzyjęty dla innego celu.
- **Dopuszczalny do automatu** — kandydat spełniający §6.2.

## 3. Źródła

### 3.1 Zestaw i zapytania

| Źródło | Zapytanie | Daje | Ścieżka |
| --- | --- | --- | --- |
| TsukiHime | AniList ID → `/animes/anilist/{anilist_id}` → wewnętrzne `id` → `/animes/{id}/episodes/{n}` (`n` = numer lokalny wpisu AniList) | pełna nazwa wydania, `sublangs`, `audiolangs`, `filecount`, wewnętrzne ID torrenta; bez seedów | szybka |
| Torrentio | Kitsu ID (ani.zip, bez niego Kitsu mappings, §3.5) → `kitsu:{id}:{n}`; film: istniejący `movie_streams` | jeden znany plik (`behaviorHints.filename`), seedy, rozmiar | szybka |
| Nyaa RSS | zapytania istniejącego `search_title` (romaji i angielski, warianty numeru, `MAX_REQUESTS`) | pełna nazwa, seedy, rozmiar, data | szybka |
| Knaben API v2 | te same zapytania co Nyaa; najwyżej 2 strony po 300 wyników na zapytanie | nazwa, seedy | dociągana |
| nekoBT | te same zapytania co Nyaa; najwyżej 2 strony po 100 | nazwa, tagi języków `A=` (audio), `F=` (fansuby), `S=` (napisy oficjalne) | dociągana |

- Wyniki źródeł tekstowych przechodzą przez H1 jak każde inne.
- **Budżet zapytań subskrypcji:** na jedno sprawdzenie celu:
  - TsukiHime (w żądaniach HTTP): lista odcinka celu najwyżej 2 strony po 100 (`limit=100`), lista poprzedniego odcinka (§6.3) najwyżej 2 strony po 100, plus 10 uzupełnień (§3.4) — razem najwyżej 14; ID tytułu TsukiHime zapamiętane dla subskrypcji. Lista celu przerwana przed ostatnią stroną = źródło niedokończone (§3.2); lista poprzedniego odcinka przerwana przed ostatnią stroną z PL na pobranych stronach daje „PL jest”, a bez PL jest traktowana jak błąd odczytu (§6.3: zostaje ostatnia udana obserwacja, bez niej „nieznane”) i nie zapisuje się jako nowa obserwacja. Tempo chwilowe pilnuje `RequestControl` według limitów TsukiHime; przekroczenie 30 s = źródło niedokończone (§3.2).
  - Torrentio: 1 żądanie.
  - Numeracja i ID (§3.5): ani.zip po AniList ID 1 żądanie jak dziś; do tego arm-server 1 przy każdym odczycie oraz ani.zip po AniDB ID 1 (puste `episodes`) i Kitsu mappings 2 (wprost i zwrotnie, brak Kitsu) tylko przy brakach — razem najwyżej 5 żądań na sprawdzenie.
  - Nyaa RSS: frazy dla tytułu romaji i angielskiego (bez duplikatów); `{tytuł}` = istniejące `base_title` danego zapisu (bez znacznika sezonu i podtytułu), a dla OVA i SPECIAL pełny tytuł zapisu z podtytułem (bez `base_title`); `{ss}` = indeks sezonu liczony z już pobranego grafu franczyzy tą samą regułą co istniejące `season_context` (cour go nie podnosi; formaty, cykle i niepełny graf jak tam), bez dodatkowych zapytań AniList: sezon 1 — `"{tytuł} - {NN}"`, a dla TV także `"{tytuł} S01E{NN}"`; sezon > 1 — `"{tytuł} - {NN}"` (numer lokalny) i `"{tytuł} S{ss}E{NN}"`; OVA i SPECIAL bez frazy `S{ss}E{NN}`; film bez numeru (punkt o formacie niżej). Numer absolutny tylko w ręcznym wyszukiwaniu. Najwyżej 4 frazy; każda w obu istniejących kategoriach, czyli najwyżej 8 żądań HTTP. Frazy obowiązują każde źródło, które ich używa. Automat nadal nie wybiera wydania bez potwierdzonej tożsamości (§6.2). Podstawa: [a1-recon.md](a1-recon.md) §2 (Frazy), N-5, §4, §6 i §8 (decyzje właściciela 2026-10-06).
  - Knaben i nekoBT: te same frazy, najwyżej 2 strony, raz na 60 min (§3.2), czyli najwyżej 8 żądań na źródło.
  - Najgorszy przypadek U-14 (30 celów, żaden nieznaleziony, pierwsza doba co 15 min): Nyaa ok. 11,5 tys. fraz = 23 tys. żądań/dobę; TsukiHime do ok. 40 tys. żądań/dobę (limit 100/min = 144 tys.); Knaben i nekoBT po ok. 5,8 tys. żądań. Typowo cel kończy się w pierwszych godzinach.
  - P-10 obejmuje każde źródło osobno: seria `429` danego źródła rzednie jego odpytywanie w pierwszej dobie do 30 min (źródła dociągane i tak są odpytywane raz na 60 min, a ich wyniki między odczytami zawsze według §3.2). W sprawdzeniu, w którym szybkie źródło jest pominięte przez P-10, decyzja używa jego ostatniego udanego wyniku dla celu z poprzedniego sprawdzenia (w pamięci, najwyżej 30 min; restart i wyłączenie źródła go usuwają; zmiana Q-03). Pominięcie nie jest nieudanym odczytem i nie zwiększa licznika wydań oczekujących (§6.2).
- **Według formatu wpisu AniList:** film (`MOVIE`) — TsukiHime `/episodes/1`, Torrentio `movie_streams`, zapytania tekstowe bez numeru. Każdy inny format (TV, ONA, OVA, SPECIAL, jedno- i wieloodcinkowe) — jak serial, z numerem lokalnym celu (jak dziś `prepare_episode`). Dostępność Pobierz dla filmu (U-21) rozstrzyga przypadek filmowy zestawu wzorcowego (§9). Dodatki `S…` z ani.zip pozostają informacją (W-06).
- Każde źródło ma przełącznik w Ustawieniach; domyślnie wszystkie włączone. Wyłączone źródło nie jest odpytywane w żadnym celu (także spisy plików i historia PL z TsukiHime). Źródło wydania nie jest pokazywane na liście.
- Każde źródło ma własny identyfikator dostawcy w istniejącym `RequestControl`.
- Odrzucone (pomiar w [intent.md](intent.md)): AnimeTosho, Torrentio po IMDb, Prowlarr i inne lokalne menedżery, Bitmagnet, Zilean, MediaFusion, własny serwer.

### 3.2 Czas i wyniki częściowe

- **Limit operacji źródła:** 30 s od startu, łącznie z oczekiwaniem na limity i stronicowaniem. Po limicie źródło jest „niedokończone”, a jego dotychczasowe wyniki są używane.
- **Lista (ręczny wybór):** wiersze pojawiają się w miarę odpowiedzi; po 3 s lista pokazuje to, co przyszło, a do końca stan „szukam jeszcze: …”. Nowe wiersze wstawiane są według kolejności §6.1; dopóki użytkownik nie przesunie kursora, kursor stoi na sugestii `*` (pierwszym wierszu grupy pierwszej, który może być sugestią), a po pierwszym ruchu zostaje na tym samym wydaniu (decyzja właściciela 2026-10-09, kursor na sugestii 2026-10-10); zaznaczenia zostają.
- **`D` bez podglądu (P-02) i subskrypcja:** decyzja po zakończeniu (albo limicie) wszystkich włączonych źródeł i uzupełnień spisów (§3.4); do tego czasu stan „szukam”.
- **Źródła dociągane w subskrypcji** (Knaben, nekoBT) są odpytywane najwyżej raz na 60 min na cel. Między odczytami decyzja używa ostatniego udanego wyniku tego źródła dla celu (wydania i seedy z chwili odczytu). Błąd odczytu zachowuje poprzedni wynik; wyłączenie źródła i restart rezydenta go usuwają. Brak jakiegokolwiek udanego odczytu = źródło niedokończone.

### 3.3 Scalanie

- Ten sam hash z kilku źródeł to jeden wiersz.
- **Nazwa wydania:** pierwsza dostępna w kolejności TsukiHime → Nyaa → nekoBT → Knaben → Torrentio (`release` Torrentio bywa ucięty).
- **Seedy:** największa wartość spośród źródeł, które je podają; brak u wszystkich → „?”.
- **Języki:** §5.2.
- **`RAW` i `HardSub`** rozpoznawane są z nazw i tagów wszystkich źródeł wydania przed wyborem nazwy wiersza; dodatni dowód z dowolnego źródła obowiązuje i nie kasuje go nazwa z innego źródła. Tag `HS` w bloku `{Tags:…}` nekoBT = `HardSub`. Przypadek wzorcowy (§9): ten sam hash z nazwą Nyaa/TsukiHime bez `HardSub` i nekoBT z `HS` → niedopuszczalny do automatu z powodem „hardsub”.
- **Sam dubbing** wynika wyłącznie z pełnej listy języków audio (`audiolangs` TsukiHime, `A=` nekoBT) rozstrzygniętej według zakresu i pierwszeństwa §5.2; tokeny audio w nazwach (`Polish audio`, `Lektor PL`) są informacją częściową — dodają język, nie dowodzą braku oryginalnego. **Znaczniki dubbingu** (lista zamknięta): istniejące `_DUBBED_RE`, tag Torrentio `Dubbed` oraz `PL dub`, `Polish dub`, `Dubbing PL`. Najwyższa niepusta pełna lista decyduje (niższa sprzeczna nie dodaje ani nie usuwa oryginalnej ścieżki); gdy zawiera oryginalne audio (`ja`, `zh` przy donghua, `ko`), to nie sam dubbing, gdy nie zawiera — sam dubbing. Dopiero bez żadnej pełnej listy audio znacznik `Dual-Audio`/`Multi-Audio` w nazwie któregokolwiek źródła wyklucza sam dubbing, a znacznik dubbingu działa tylko, gdy żadne źródło nie ma takiego znacznika. Przypadki wzorcowe (§9): `audiolangs=["ja","en"]` i niższa nazwa `English Dub` → nie sam dubbing; ucięty `release` Torrentio ze znacznikiem dubbingu i nazwa Nyaa z `Dual-Audio` → nie sam dubbing; `audiolangs=["en"]` i `A=ja,en` → sam dubbing; bez pełnej listy nazwa `Example - 01 [1080p] [Dual-Audio] [Polish audio]` → nie sam dubbing, PL audio obok oryginalnej (+15); bez pełnej listy `Example - 01 [1080p] [PL dub] [Napisy PL]` → sam dubbing (U-23: polski dubbing bez oryginalnej ścieżki).
- **Paczka** według §2: spis plików wygrywa z nazwą; bez spisu wystarcza zakres w nazwie dowolnego źródła.
- **Ten sam plik z dwóch źródeł:** ścieżka ze spisu plików; nazwa pliku z Torrentio łączona z nią po nazwie pliku, gdy w spisie jest dokładnie jedna taka.

### 3.4 Spisy plików i reprezentant wiersza

- Pewność i dopuszczalność liczone są na pliku odcinka. Bez żadnej nazwy pliku ocena idzie na nazwie wydania z dopiskiem „bez nazwy pliku”.
- **Ocena nazwy wydania:** osobna funkcja H1 oceniająca nazwę wydania jako tekst istniejącym parserem, bez udawania nazwy pliku i bez wymogu rozszerzenia wideo; daje werdykt i powód jak H1. Konflikt na nazwie wydania = konflikt (§2) z tej oceny. Służy liście, kolejce uzupełnień i wydaniom oczekującym; do automatu dopuszcza tylko jako kandydata „do weryfikacji po metadanych” (§6.2). Testy: poprawna nazwa, jawnie inny sezon lub odcinek, nazwa nierozstrzygalna.
- Spis plików z TsukiHime: ID torrenta z listy odcinka albo z wyszukania po hashu, gdy wydanie przyszło z innego źródła.
- **Kolejka uzupełnień celu:** wydania bez spisu, w kolejności liczonej na tym, co już wiadomo — w liście §6.1, w subskrypcji kolejność wyboru §6.2 (bez pewności) i tylko wydania bez konfliktu na nazwie, użyteczne według nazwy i niewykluczone dla celu. Jedno sprawdzenie wykonuje najwyżej 10 odczytów TsukiHime (wyszukanie po hashu i spis liczą się osobno; liczą się rzeczywiste żądania, więc odpowiedź `200` wyszukania po hashu z kompletnym `files` (§2) kończy wizytę bez drugiego odczytu, a z `files` krótszym niż `filecount` wizyta czyta `/torrents/{id}`) z początku kolejki. W jednym sprawdzeniu każde wydanie jest odwiedzane najwyżej raz (wyszukanie po hashu i spis to dwa kolejne odczyty tej samej wizyty); po nieudanym odczycie (`202`, pusta lista, błąd) ponowienie dopiero w następnym sprawdzeniu, za wydaniami jeszcze nieodwiedzonymi. Po każdym uzupełnieniu kolejność nieodwiedzonych liczona jest od nowa. Kolejka żyje w pamięci rezydenta; restart buduje ją od nowa, a w subskrypcji z uwzględnieniem trwale zapisanych nieudanych odczytów (§6.2).
- Pamięć spisów po hashu: tylko udane, niepuste i kompletne (§2) odpowiedzi.
- **Reprezentant wiersza:** spośród znanych plików wydania ten, który najlepiej pasuje do celu: werdykt `zgodny` → `niepewny` → konflikt, potem wyższa pewność, potem ścieżka alfabetycznie. Ręczny wybór wiersza wybiera ten plik.
- **Niejednoznaczny plik:** więcej niż jeden plik `zgodny` z celem → wiersz „niejednoznaczny plik”; ręcznie wybór pliku U-18c, automat niedopuszczalny.
- Przed pobraniem treści ostateczny plik wskazuje spis z qBittorrenta (U-18). W automacie wskazany plik (także po unikalnej nazwie, U-18a) przechodzi ponownie H1 na pełnej ścieżce ze spisu qBittorrenta i ponownie §6.2 (użyteczność, plik nieprzyjęty dla innego celu); wynik inny niż `zgodny` zatrzymuje próbę przed startem treści („Po metadanych”, §6.2).

### 3.5 Błędy

- Brak tytułu w TsukiHime, brak Kitsu ID, `403`/`429`/timeout/błąd źródła: wiersz stanu, np. „Torrentio: niedostępne (403)”, „TsukiHime: brak tytułu”; pozostałe źródła działają. W subskrypcji nie zużywa próby (przejście 8).
- Wszystkie włączone źródła zawiodły: „Brak wyników — źródła niedostępne”, nie „0 wydań”. Wszystkie wyłączone: „Wszystkie źródła wyłączone (Ustawienia)”.
- Pusta odpowiedź działającego źródła = brak kandydatów w tym źródle (R-08).
- **Numeracja (ani.zip) a Torrentio:** to dwie osobne rzeczy. Subskrypcja zapisuje mapowanie numeracji niezależnie od Kitsu ID (zmiana U-22); brak Kitsu wyłącza tylko Torrentio. Mapowanie odświeżane przy każdym udanym odczycie ani.zip; zmiana numeracji odcinka, który ją miał (niżej), to istniejący konflikt katalogu (przejście 23); uzupełnienie brakującej i naprawa sprzecznej konfliktem nie są.
- **Źródła numeracji i ID (D1, decyzja właściciela 2026-10-06):** pomiar 288 tytułów TV/ONA (RELEASING oraz lato i jesień 2026): ani.zip po AniList ID bez `episodes` 45,5%, bez Kitsu 44%; po połączeniu 37,5% i 23,3% (top 100: 12% → 6%, 24% → 3%) — [a1-recon.md](a1-recon.md) §11. Kolejność:
  1. ani.zip po AniList ID, jak dziś;
  2. przy każdym odczycie listy most AniList → AniDB przez arm-server (`GET https://arm.haglund.dev/api/v2/ids?source=anilist&id={id}`, jedno zapytanie, bez lokalnego stanu): daje AniDB ID i sezon TVDB (`thetvdb-season`, kontrola niżej); przy pustych `episodes` i znanym AniDB ID dalej ani.zip po `anidb_id`, którego odcinki zastępują puste. Brak (`null`) ID w odpowiedzi po AniDB nie nadpisuje ID już znanego;
  3. brak `kitsu_id`: Kitsu mappings po AniList ID; przyjęty tylko jednoznaczny wpis `anime`, którego lista mapowań zwrotnie zawiera ten AniList ID; oba odczyty po jednej stronie `page[limit]=20` i kompletne (bez `links.next`), inaczej Kitsu nieustalone, bez dalszych stron.

  Błąd albo brak mostu odbiera tylko jego część; reszta działa jak dotąd.
- **Numeracja celu:** cel ma numerację tylko wtedy, gdy mapowanie ma klucz jego numeru lokalnego z `seasonNumber` i `episodeNumber` (wpis bez nich, np. 172192-1, = bez numeracji) i nie jest ona sprzeczna. Sprzeczna: ten sam S/E ma niższy lokalny odcinek — numerację zachowuje najniższy, późniejsze są sprzeczne (204389, 159042, 213657: błędny zawsze późniejszy) — albo sezon w ani.zip różni się od sezonu TVDB z mostu (np. 198727; dotyczy każdego odcinka z innym sezonem). Ta sama reguła obowiązuje cel H1, listę, ponowienie oferty, `D` i subskrypcję. Nie dotyczy filmu (`MOVIE`): ma jeden cel bez numeracji odcinkowej, a sugestia i automat działają jak dotąd (np. 21519-1: ani.zip „Complete Movie” bez S/E). Powód trafia do rejestru decyzji.
- **Bez numeracji (brak albo sprzeczna, D2):** cel nie ma S/E, numeru absolutnego ani tytułu odcinka. Automat bierze nadal tylko `zgodny` (§6.2), a bez numeracji `zgodny` daje wyłącznie nazwa z tytułem (aliasem) tego wpisu AniList z jego znacznikiem sezonu lub części i numerem lokalnym (np. „Koori no Jouheki 2nd Season - 01”). Sezon z grafu franczyzy nie jest dowodem: wydanie z samym `SxxExx` zostaje `niepewne`, nie konflikt (ryzyko: BLEACH 185874 — graf S05, TVDB S17). Lista pokazuje wydania bez sugestii z powodem „brak numeracji”. Brak przyjmowalnego wydania daje zwykły powód §8.
- **Odświeżanie (D3):** numeracja brakująca albo sprzeczna jest czytana od nowa przy każdym sprawdzeniu subskrypcji, bez osobnego harmonogramu i bez pamięci w ownerze, z pominięciem pamięci odpowiedzi ani.zip (`max-age`) dla takiego celu; gdy się pojawi, następne sprawdzenie używa pełnej numeracji.

## 4. Pewność odcinka

- Kolumna **Pewność** pokazuje estymatę w %: model `conf_frozen_model.json` z badania 2 (regresja logistyczna L2 + kalibracja sigmoidowa, bez wet), przeniesiony do repo z niezmienionymi współczynnikami.
- Cechy liczy publiczna projekcja dowodów H1 (jedna funkcja w `episode_identity.py`, bez drugiego parsera), o dokładnie tej semantyce co `conf_model.py` z badania (w tym skalowanie i wybór tekstu bez pliku). Test: identyczne wektory cech i predykcje jak w badaniu na zapisanych przypadkach. Zmiana H1 przechodzi istniejącą procedurę (`plans/e1-integracja.md` §10.6).
- Kandydat z konfliktem pokazuje zamiast % krótki powód H1, np. „inny sezon (S01)”; szczegóły pokazują porównane numery i ich numeracje.
- Kalibracja potwierdzona jest tylko dla populacji korpusu E1; dla nowych źródeł i ocen bez nazwy pliku wartość jest estymatą bez potwierdzonej kalibracji (§7).
- Procent wpływa tylko na kolejność listy i sugestię (§6.1). Automat go nie używa (§6.2). To wyjątek od zakazu ML do tożsamości (spec.md §9): model nie rozstrzyga tożsamości w automacie.

## 5. Ocena jakości

### 5.1 Punkty

| Cecha | Punkty |
| --- | ---: |
| Polskie napisy | +40 |
| albo: polskie napisy niepotwierdzone (PL bez roli, §5.2) | +20 |
| Polska ścieżka audio obok oryginalnej | +15 |
| Angielskie napisy, gdy brak polskich napisów za +40 (także przy PL bez roli) | +10 |
| Rozdzielczość 1080p (także 1440×1080) | +20 |
| Rozdzielczość 2160p | +5 |
| Wydanie z platformy (WEB z NF, CR, ADN, AMZN, HIDIVE, BILI, DSNP) | +5 |
| Blu-ray lub remux | −10 |
| Seedy | 0–10 |

- Najwyżej jedna z dwóch pozycji PL napisów.
- **Jakość = max(0, suma)**; zakres 0–90. Sortowanie na wartości niezaokrąglonej; kolumna pokazuje liczbę całkowitą.
- **Seedy:** `10 × min(1, ln(1 + s) / ln(1 + 50))`; 5 seedów ≈ 4,6 pkt, 50 i więcej = 10 pkt. Brak danych = 5 pkt i „?”.
- Angielski dubbing, inne języki napisów, liczba języków, grupa, kodek, rozmiar: 0 pkt.

### 5.2 Rozpoznanie cech

**Zakres deklaracji:** języki wybranego pliku mają pierwszeństwo przed językami całego wydania. Języki całego wydania (pola TsukiHime wydania, tagi nekoBT, nazwa wydania) dotyczą kandydata, gdy wydanie nie jest paczką według §2 (spis, a bez spisu nazwa); gdy jest paczką, są dla tego pliku nieustalone (nie dają PL ani EN). Flaga PL Torrentio dotyczy znanego pliku z jej rekordu.

**Normalizacja kodów języków:** przed oceną i scalaniem kody są porównywane bez wielkości liter i po języku podstawowym tagu (`pl-PL` → `pl`, `ja-JP` → `ja`, `zh-Hant` → `zh`). Przypadek z kodami regionalnymi jest w zestawie wzorcowym (§9).

**Puste deklaracje:** brak pola i pusta lista (`[]`) to brak danych — nie wypierają deklaracji niższego rzędu. Niepusta lista bez danego języka to potwierdzony brak. Napisy i audio rozstrzygane osobno.

**Napisy nekoBT:** jedna deklaracja napisów = suma znormalizowanych `F=` (fansuby) i `S=` (napisy oficjalne). Brak języka ocenia się względem tej sumy; niepuste `S=` bez PL nie neguje PL z `F=`. Przypadek wzorcowy (§9): `F=` z `pl`, niepuste `S=` bez PL, bez deklaracji TsukiHime → PL napisy, +40, klasa PL, kończy czekanie (§6.3).

**Pierwszeństwo źródeł** (w tym samym zakresie): TsukiHime (`sublangs`/`audiolangs`, odczytane z plików) → tagi nekoBT → nazwa pliku → nazwa wydania. Wyższa deklaracja wygrywa ze sprzeczną niższą; jawna lista języków bez PL wygrywa z tokenem w nazwie.

- **PL napisy:** `pl` w `sublangs`, `pl` w napisach nekoBT (`F=` ∪ `S=`), tokeny napisów (`Napisy PL`, `PLsub`, `PL sub`, `Polish sub`).
- **PL audio:** `pl` w `audiolangs`, `pl` w tagu `A=`, tokeny `Lektor PL`, `Polish audio` oraz znaczniki polskiego dubbingu (§3.3). +15 „obok oryginalnej” tylko przy pełnej liście audio z oryginalnym językiem albo, bez pełnej listy, przy znaczniku `Dual-Audio`/`Multi-Audio`.
- **PL bez roli:** flaga PL Torrentio albo sam token `PL`/`POL`/`Polish`, bez deklaracji języków wyższego rzędu. Daje +20, nie kończy czekania na PL (§6.3).
- **EN napisy:** `en` w `sublangs` albo w napisach nekoBT (`F=` ∪ `S=`), tokeny `ENG sub`, `English sub`, `MultiSub`, `Multi-Subs`. Samo „MultiSub” nie oznacza PL.
- **Oryginalne audio:** `ja`; `zh` tylko przy donghua (AniList `countryOfOrigin = CN`); `ko` jako akceptowalne. Bez deklaracji audio zakładane oryginalne, chyba że wychodzi sam dubbing według §3.3.
- **Rozdzielczość, platforma, Blu-ray:** z nazwy. **`RAW`, `HardSub`:** z nazw i tagów wszystkich źródeł (§3.3).

### 5.3 Klasy

- **Klasa rozdzielczości (U-05 bez zmian):** 1080 (także 1440×1080) → 2160 → 720 → pozostałe znane, bliższe 1080 wyżej → nieznana.
- **Klasa PL napisów:** PL → PL bez roli → brak.
- **Klasa audio:** oryginalne (`ja`; `zh` przy donghua) → `ko`.
- 720p i niższe są ukryte na liście, gdy istnieje zgodny kandydat 1080p lub 2160p, który może być sugestią: bez konfliktu, nie sam dubbing, w obsługiwanym formacie (U-24; od 2026-10-10 ukrycie nigdy nie chowa sugestii z powodu wydania, którego nie da się zasugerować). Sama sugestia `*` jest zawsze widoczna, także gdy ma 720p lub mniej (2026-10-10).
- Sam dubbing bez oryginalnej ścieżki — na końcu listy (U-23). Nieobsługiwany kontener — wykluczony z powodem (U-06).

### 5.4 Kontrola wag

Wagi i klasy muszą odtworzyć kolejność właściciela (wszystkie 1080p, właściwy odcinek, oryginalne audio JA): F (PL + audio JA+PL, 60 seedów) = 85 > A (PL, JA, 80) = 70 > C (PL, JA+EN, 30) = 68,7 > E (PL, Multi Audio bez PL, 5) = 64,6 > B (bez PL, EN, JA+EN, 400) = 40 ≈ D (tylko EN, 900) = 40. Ta kolejność jest testem jednostkowym (dla automatu i dla listy przy równej pewności); zmiana wag lub klas, która ją łamie, jest błędem.

## 6. Wybór

### 6.1 Kolejność listy i sugestia

1. Kandydaci bez konfliktu: klasa rozdzielczości → klasa PL napisów → klasa audio → **jakość × pewność** malejąco → wyższa pewność → więcej seedów → hash.
2. Sam dubbing (§5.3).
3. Kandydaci z konfliktem, w tej samej kolejności wewnętrznej, z powodem.

**Ukrycie niezgodnych (decyzja właściciela 2026-10-10):** lista ręczna nie pokazuje wierszy z werdyktem H1 `MISMATCH`, a niepewne wiersze z konfliktem (`!`, werdykt `INSUFFICIENT`) zostają w grupie 3; kolejność, sugestia i automat liczone są jak dotąd na pełnej liście.

**Remisy ekranowe (reguła „B-tie”, decyzja właściciela 2026-10-07):** po ułożeniu pełnej listy powyższym kluczem każdy maksymalny blok **kolejnych** wierszy o identycznym podpisie — grupa (1–3), nieobsługiwany kontener, klasy, Jakość i Pewność **w postaci pokazanej na liście** (Jakość zaokrąglona do całości, Pewność do pełnego procentu, brak pewności jako osobna wartość) — jest układany wewnątrz: więcej seedów (brak danych = −1) → dokładne jakość × pewność (bez pewności: jakość) malejąco → hash. Od 2026-10-10 (decyzja właściciela) przed seedami w bloku decyduje werdykt H1: wiersz `zgodny` (`MATCH`) idzie przed niepewnym. Kolejność bloków się nie zmienia, a blok przerwany wierszem o innym podpisie się nie łączy, więc wiersz z widocznie gorszą Jakością lub Pewnością nigdy nie awansuje. Bloki liczone są na pełnej liście, przed ukryciem (U-24); ukrycie i sugestia używają tego porządku. Wzór jakości i sufit seedów (§5.1) bez zmian.

- Kolumny na końcu wiersza: **Jakość** i **Pewność**. Pełna nazwa wydania w wierszu.
- **Sugestia** (`*`) = pierwszy wiersz z punktu 1 (najwyżej w rankingu); gdy nie jest `zgodny` w H1 — z oznaczeniem „niepewne” (U-03, R-06; tak też w Bibliotece po pobraniu). `D` bez podglądu pobiera sugestię (O-5, decyzja właściciela 2026-10-06).
- Ręczny wybór kandydata innego niż `zgodny` wymaga potwierdzenia, a konfliktu — potwierdzenia z powodem H1 (R-04 bez zmian).

### 6.2 Dopuszczalność i wybór w automacie

Subskrypcja bierze tylko kandydata, który jednocześnie:

- ma werdykt H1 **zgodny** na nazwie pliku odcinka (§3.4) albo — gdy wydanie nie ma żadnej znanej nazwy pliku ani spisu — **zgodny** w ocenie nazwy wydania, a nazwa nie wskazuje paczki; taki kandydat jest „do weryfikacji po metadanych”: treść startuje dopiero po `zgodnym` H1 na pełnej ścieżce ze spisu qBittorrenta (§3.4), inaczej „Po metadanych” (niżej);
- jest **użyteczny** (§2), według spisu plików, a bez spisu — według nazwy;
- nie ma znanych 0 seedów, gdy istnieje dopuszczalny z seedami > 0 lub „?” w tej samej klasie rozdzielczości i klasie PL napisów (zero nigdy nie powoduje zejścia do gorszej klasy; takie wydanie jest próbowane, a gdy stoi — działa próg celu);
- nie należy do wydania wykluczonego dla celu (wcześniejsza próba);
- jego klasa rozdzielczości nie jest gorsza niż **próg celu** (niżej);
- nie blokuje go **wydanie oczekujące** (niżej).

**Wydanie oczekujące:** wydanie z kolejki uzupełnień subskrypcji (§3.4: bez spisu, bez konfliktu na nazwie, użyteczne według nazwy, niewykluczone), bez znanej nazwy pliku, dla którego w tym celu odczyt w TsukiHime (wyszukanie po hashu albo spis) **nie zakończył się jeszcze ostatecznie**. Blokuje wybór kandydata z gorszej klasy rozdzielczości, a w tej samej klasie — z gorszej klasy PL napisów, także gdy nie zmieściło się w budżecie tego sprawdzenia. Przestaje blokować, gdy dostanie spis, po niepowodzeniu rozstrzygającym (brak hasha w TsukiHime, pusta lista) albo po 3 niepowodzeniach przejściowych (`202`, `429`, błąd, limit czasu) w 3 różnych sprawdzeniach. Licznik rośnie o najwyżej 1 na sprawdzenie i tylko dla wydań, których odczyt w tym sprawdzeniu się nie udał; gdy TsukiHime jest w całości niedostępny (§3.5: awaria listy, limit czasu albo `429`/błąd, także w trakcie uzupełnień), niepowodzenie przejściowe dostaje w tym sprawdzeniu każde wydanie oczekujące, również spoza budżetu. Pominięcie TsukiHime w cooldownie dostawcy (§3.1) i zwykłe wyczerpanie budżetu nie są niedostępnością i nie zwiększają licznika. Blokada wygasa już w sprawdzeniu, w którym licznik osiąga 3, więc czekanie trwa najwyżej 3 sprawdzenia z niepowodzeniem. Stan niepowodzeń (rozstrzygające i licznik przejściowych) dla pary cel–hash owner zapisuje trwale razem ze stanem celu (jak wykluczenia), więc restart nie odtwarza wygasłych blokad ani nie zeruje licznika; przy odbudowie kolejki wydania nadal blokujące idą przed ponowieniami tych, które już blokować przestały. Przy wyłączonym TsukiHime nie ma wydań oczekujących. Kolejka idzie od najlepszej klasy, a budżet 10 obejmuje wyszukania po hashu i odczyty spisów, więc każda blokada trwa najwyżej tyle sprawdzeń, ile trzeba, by kolejka do niego doszła; powód „czekam na sprawdzenie wydań 1080p” jest widoczny.

**Próg celu:** najlepsza klasa rozdzielczości spośród prób celu uznanych za martwe (§6.5), z metadanymi lub bez. Zapisany trwale u ownera; działa niezależnie od tego, co zwracają źródła, i po restarcie. Progu nie ustawia próba zatrzymana po metadanych (paczka, niejednoznaczny plik) ani odrzucona przez kontrolę (H2, U-07/U-08). Tak „wydanie stoi” nigdy nie prowadzi do zejścia niżej, a wydanie złe treściowo nie blokuje innych klas. Martwe wydanie bez metadanych, które okazałoby się paczką, może więc zablokować niższą klasę — zgodnie z zasadą „lepiej nie pobrać”, z powodem widocznym (§8).

**Wybór:** wśród dopuszczalnych pierwszy według: klasa rozdzielczości → klasa PL napisów → klasa audio → znana nazwa pliku przed „do weryfikacji po metadanych” → **jakość** → więcej seedów → hash, z uwzględnieniem §6.3. Pewność nie wpływa na wybór automatu. Automat nie bierze `niepewnego` (usuwa dopuszczenie po `T_niepewny`).

**Wykluczenie i tożsamość próby:** próba wyklucza dla swojego celu całe wydanie (hash) — także gdy skończyła się przed poznaniem ścieżki pliku. Stare klucze `hash:fileIdx` działają tak samo. Ochrona „plik przyjęty dla innego celu” używa hasha i ścieżki ze spisu qBittorrenta. Każda próba ma własny trwały identyfikator, osobny od licznika zużytego limitu (identyfikator polecenia przyjęcia nie może się powtórzyć).

**Po metadanych:** gdy spis z qBittorrenta pokaże paczkę, niejednoznaczny plik, brak pliku `zgodnego` albo wskazany plik nie przejdzie ponownej kontroli (§3.4), próba jest zatrzymywana przed pobraniem treści (bez ręcznego wyboru pliku U-18c w automacie), wydanie wykluczone dla celu, a próba **nie zużywa** limitu (nic nie pobrano); powód widoczny. Test odbioru: zatrzymanie po metadanych → restart → przyjęcie innego wydania z niezmienionym licznikiem.

### 6.3 Czekanie na polskie napisy (subskrypcja)

Przy każdym należnym celu automat ustala historię PL na nowo z odczytu TsukiHime dla poprzedniego odcinka sezonu (ostatniego wyemitowanego przed celem), niezależnie od tego, czy subskrypcja go pobrała:

| Stan historii | Dowód | Zachowanie |
| --- | --- | --- |
| **PL jest** | w TsukiHime co najmniej jedno wydanie bez konfliktu z PL napisami (§5.2) albo wydanie przyjęte dla poprzedniego odcinka (ręcznie lub automatem) ma PL napisy | czekaj na PL do bufora „Czekaj na PL” (domyślnie 2 h) od `t_due` |
| **PL nie ma** | brak dowodu „PL jest”; od emisji poprzedniego odcinka minęły ≥ 24 h, jest co najmniej jedno wydanie bez konfliktu z niepustym `sublangs` dotyczącym tego odcinka według zakresu z §5.2, żadne nie ma PL napisów | bierz od razu najlepsze dopuszczalne |
| **nieznane** | wszystko inne: odcinek 1 sezonu, TsukiHime wyłączone lub bez tytułu, brak wydań, brak `sublangs` | czekaj do min(2 h, „Czekaj na PL”) od `t_due` |

- Lokalny dowód (wydanie przyjęte dla poprzedniego odcinka z PL napisami) jest sprawdzany przy każdym sprawdzeniu najpierw i zawsze daje „PL jest”, także wobec błędu odczytu i wcześniej zapisanego „PL nie ma”.
- Błąd odczytu TsukiHime zachowuje ostatnią udaną obserwację TsukiHime dla celu (zapisaną trwale u ownera); bez lokalnego dowodu i bez udanej obserwacji stan jest „nieznane”.

- **Ustawienie „Czekaj na PL”:** liczba godzin, domyślnie 2 (O-2, decyzja właściciela 2026-10-06); 0 = nigdy nie czekaj. Zmiana działa od najbliższego sprawdzenia (termin liczony od `t_due` z nową wartością).
- **„Pobierz teraz”:** w szczegółach subskrypcji, dla celu, który czeka na PL, akcja użytkownika kończy czekanie tylko dla tego celu i tylko dla bieżącego terminu. Automat od razu sprawdza cel i bierze pierwszego dopuszczalnego według §6.2 (dopuszczalność, próg celu i wydania oczekujące bez zmian; bez `niepewnego`). Bez dopuszczalnego kandydata cel zostaje należny, z powodem z §8. Decyzja przetrwa restart i trafia do rejestru decyzji.
- **W trakcie czekania:** gdy pierwszy w kolejności wyboru §6.2 dopuszczalny kandydat ma PL napisy — pobierz go od razu. Inaczej czekaj dalej.
- **Po buforze:** pobierz pierwszego dopuszczalnego według §6.2; gdy nie ma PL, powód „brak PL po {bufor}”.
- „PL bez roli” i sam polski dubbing nie kończą czekania.
- Ręczne pobranie w trakcie czekania rezerwuje cel (U-16, przejście 17).
- Stan historii i jego dowód trafiają do rejestru decyzji.
- Szczegóły subskrypcji pokazują stan, np. „PL: zwykle jest · czekam do 21:30”, „PL: brak w poprzednim odcinku · pobieram od razu”, „PL: nieznane · czekam do 19:30”.

### 6.4 Harmonogram

- Pierwsze sprawdzenie w `t_due` (P-1 = 0, jak w planie przepływu i obecnym `subscription_targets.py`), potem U-14; źródła dociągane według §3.2.

### 6.5 Pobieranie, które stoi

- Próba automatu bez przyrostu pobranych bajtów przez **10 min**, także bez metadanych (P-9: `T_metadane` = `T_zastój` = 10 min; czas pauzy się nie liczy) = martwa (przejście 11).
- Następna próba według §6.2 (próg celu). Brak dopuszczalnego → cel `należny`, szukanie wg U-14, powód widoczny. Wyczerpanie 3 prób → `wyczerpany` (przejście 16).
- Pobranie ręczne: bez automatycznej zamiany; po 10 min bez przyrostu stan „stoi od 10 min” przy odcinku.

### 6.6 Paczki

- Subskrypcja: niedopuszczalne (§6.2). Ręczny wybór: na liście według tych samych reguł.

## 7. Próg pewności dla automatu (przyszłość)

- Dziś automat używa §6.2, bo model przy progu 99% przepuścił na egzaminie 6 złych wydań, a `zgodny` H1 — 0.
- Każda decyzja automatu zapisuje w rejestrze decyzji pewność i jakość wszystkich kandydatów.
- Próg może rozszerzyć regułę `zgodny` dopiero, gdy na **świeżym** zbiorze z obecnych źródeł (nieużytym do strojenia ani wcześniejszych egzaminów) da nie więcej błędnych przyjęć niż `zgodny`, zero przyjęć nieustalonych i ECE ≤ 5 pp, a właściciel to zatwierdzi.

## 8. Powiadomienia

Każde niepowodzenie ma powód w szczegółach odcinka i jedno powiadomienie w zasobniku (`tray.notify`) na odcinek i powód:

- w terminie decyzji (`t_due` + max(czas czekania z §6.3, 2 h); przy „PL nie ma” i przy „Czekaj na PL” = 0 — `t_due` + 2 h) brak dopuszczalnego kandydata — „E6: brak pewnego wydania (12 wydań, 0 zgodnych)”; gdy blokuje próg celu — „E6: czekam na 1080p (dostępne 720p)”;
- próba martwa — „E6: wydanie stoi, biorę następne” albo „E6: wydanie stoi, brak następnego”;
- próba odrzucona przez kontrolę (H2, U-07/U-08) — „E6: wydanie odrzucone (…), biorę następne” albo „…, brak następnego”;
- próba zatrzymana po metadanych (§6.2) — z rzeczywistym powodem: „E6: wydanie okazało się paczką / ma niejednoznaczny plik / plik to nie ten odcinek, biorę następne” albo „…, brak następnego”;
- wyczerpane próby, 7 dób bez wydania (S-14 bez zmian);
- wszystkie źródła niedostępne dłużej niż 1 h dla należnego celu.

Pobranie bez PL po buforze nie jest niepowodzeniem: powód w szczegółach, bez powiadomienia.

## 9. Zestaw wzorcowy i odbiór

- Zestaw: 15 odcinków z badania 1 (AniList 210031, 159042, 189123, 185756, 195516, 204389, 154587, 140960, 130003), najnowsze odcinki 8 subskrypcji właściciela, jeden film i jeden wieloodcinkowy wpis OVA/SPECIAL.
- Dla każdego: zapisane surowe odpowiedzi źródeł, oczekiwana trójka na górze listy i oczekiwany wybór automatu (albo jego brak z powodem). Oczekiwania potwierdza właściciel przed kodem.
- Pokrycie nowej konfiguracji zapytań (§3.1) jest porównane z pomiarem z badania 1; spadek > 5 pp wymaga decyzji przed odbiorem.
- Testy offline odtwarzają zestaw z zapisanych odpowiedzi.
- Odbiór: właściciel na żywo, w `uv run anishift`, na wybranych przez siebie tytułach.

## 10. Pierwszeństwo przed spec.md i planem przepływu

| Miejsce | Zmiana |
| --- | --- |
| spec U-02, §8 (usługi), §11 „Nyaa jako drugie źródło” | Źródła §3. |
| spec §9 „szerokie wyszukiwanie Nyaa” | Nyaa RSS jest zwykłym źródłem, nie cichym zamiennikiem. |
| spec §9 „ML do tożsamości” | Wyjątek dla estymaty pewności (§4); tożsamość w automacie rozstrzyga H1. |
| spec U-03, R-06 | Lista pokazuje % zamiast szufladek; automat bierze tylko `zgodny`; „niepewne” = sugestia nie-`zgodna`. |
| spec U-04, R-02 | Klasy §5.3 i punkty §5; U-05 bez zmian jako pierwszy klucz. |
| spec R-07 | Te same klasy i punkty w liście i automacie; pewność tylko w liście i sugestii (§6.1, §6.2). Zamiana po nieudanej kontroli U-08 w ścieżce ręcznej = pierwszy dopuszczalny według §6.2 (bez czekania na PL) z wykluczeniem całego wypróbowanego hasha; brak takiego → problem do ręcznego wyboru, bez pobierania `niepewnego`. |
| spec §14 „Parametry przepływu” | Bez raportu P-2/P-5 (P-2 usunięte, P-5 zastąpione §6.2); odbiór według §1 i §9. |
| spec U-22 | Mapowanie numeracji zapisywane niezależnie od Kitsu ID (§3.5). |
| spec U-25 | Blu-ray −10 pkt; kodek bez wpływu. |
| spec U-21 | Film według przypadku zestawu wzorcowego (§9). |
| spec U-14, S-14 | Dochodzą powiadomienia §8. |
| spec Q-03 | Wyjątki: ostatni udany wynik szybkiego źródła pominiętego przez P-10, w pamięci, najwyżej 30 min (§3.1); dla Knaben i nekoBT wyłącznie reguła §3.2. |
| spec R-01, Q-02, Q-04 | Zapytania §3.1, limity §3.2, `RequestControl` per dostawca. |
| spec R-03, R-04 | Dochodzą kolumny Jakość i Pewność; potwierdzenia R-04 bez zmian. |
| spec R-05 | Brak seedów = „?” i 5 pkt; mało seedów obniża jakość; znane 0 seedów w automacie §6.2. |
| spec P-02 | `D` bez podglądu decyduje po wszystkich źródłach (§3.2). |
| plan §3.3, przejście 6, P-2 | Usunięte dopuszczenie `niepewnego`. |
| plan §3.3 wybór | Ograniczenia klasy i próg celu (§6.2). |
| plan §3.3 limit prób | Wyjątek: próba zatrzymana po metadanych nie zużywa limitu; tożsamość próby osobna od licznika (§6.2). |
| plan klucz pary (`hash:fileIdx`) | Wykluczenie całego hasha dla celu (§6.2). |
| plan P-5 | Zastąpione ograniczeniami klasy i progiem celu (§6.2). |
| plan P-9 | `T_metadane` = `T_zastój` = 10 min. |
| plan P-10 | Obejmuje wszystkie źródła, każde osobno; dociągane §3.2; budżet §3.1. |
| plan przejście 10 i diagram `metadane → wybór_pliku`, spec U-18(c), plan E3 D-11 (U-18c) | W automacie niejednoznaczny plik albo brak pliku `zgodnego` po metadanych zatrzymuje próbę bez ręcznego wyboru (§6.2); ręcznie U-18c bez zmian. |
| spec U-18 (a) w automacie | Ponowne H1 na pełnej ścieżce qBittorrenta przed startem treści (§3.4). |
| plan §3.3 dopuszczalność (`zgodny` na pliku), plan E3 D-10 | Dochodzi kandydat „do weryfikacji po metadanych” (wydanie bez nazwy pliku, `zgodny` w ocenie nazwy wydania), start treści dopiero po `zgodnym` H1 na ścieżce qBittorrenta (§6.2). |
| spec U-23 | Sam dubbing: na końcu listy; w automacie niedopuszczalny (§2 „Użyteczny”). |
| plan §5.6 (`check`, `selection`) | Źródła §3.1 zamiast `torrentio`/`anizip`; dochodzą pola pewności i jakości kandydatów (§7) oraz stanu historii PL z dowodem (§6.3). |
| spec R-02 sugestia | Sugestia = pierwszy wiersz rankingu §6.1, z oznaczeniem „niepewne”, gdy nie jest `zgodny` (§6.1, O-5). |

## 11. Poza zakresem

- Osobne pliki napisów PL z zewnątrz (etap E4).
- Wygląd list i szczegółów poza nowymi kolumnami (osobny etap).
- Strojenie wag ponad kontrolę §5.4 i zestaw wzorcowy.

## 12. Otwarte decyzje właściciela

Wszystkie rozstrzygnięte 2026-10-06 (właściciel; O-3 i O-4 według reguł obowiązujących, bez sprzeciwu właściciela).

- **O-1:** odcinek pobrany bez PL, wersja z PL pojawia się później — **zostawiamy**, bez ponownego pobierania i podmiany. Tłumaczenie jest podstawową drogą programu; lepsze napisy może dać E4.
- **O-2:** domyślne „Czekaj na PL” — **2 h** (pomiar: do 2 h 212, do 5 h 217 z 267 odcinków z PL). Do tego akcja „Pobierz teraz” (§6.3).
- **O-3:** poprzedni sezon nie jest używany dla odcinka 1 (pomiar: szczątkowa i sprzeczna historia starszych sezonów w TsukiHime, 6 z 15 bez danych). Odcinek 1 ma stan „nieznane” i czeka 2 h.
- **O-4:** koreańskie audio z PL napisami a japońskie bez PL — PL napisy wygrywają (klasa PL przed klasą audio).
- **O-5:** sugestia i `D` bez podglądu — **pierwszy wiersz rankingu** (§6.1); gdy nie jest `zgodny`, oznaczenie „niepewne”.

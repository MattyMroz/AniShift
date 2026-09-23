---
kind: research-report
status: completed
updated: 2026-09-22
baseline: 0e8a6bf9194d2786d426d3f3a58f48272b3eb087
---

# API anime dla AniShift: jakie dane dostajemy i co można na nich oprzeć

## 1. Najważniejsza odpowiedź

**Tak, istnieją usługi, które dostarczają listy odcinków anime, ich numerację i tytuły, a następnie kandydatów do pobrania z konkretnych torrentów. Odpowiedzi Torrentio zajmowały w naszych próbach od około 52 milisekund do 1,83 sekundy. Nie jest to jednak gotowa integracja ani jeden kompletny i bezbłędny katalog, który sam rozstrzyga wszystkie wybory.**

Najbardziej użyteczny podział jest następujący. Istniejący w AniShift katalog AniList pomaga znaleźć tytuł i powiązane produkcje. ani.zip wzbogaca wybrany wpis o odcinki, identyfikatory innych katalogów i numerację. Torrentio dostarcza kandydatów do pozyskania, często razem ze wskazaniem pliku w paczce. AnimeSchedule może dodatkowo dostarczać informacje o terminach i przesunięciach emisji.

**ani.zip nie przechowuje w sprawdzonych odpowiedziach torrentów ani liczby seedów. To Torrentio agreguje informacje o wydaniach.** Rozdzielenie tych ról jest kluczowe dla zrozumienia całego rozwiązania.

Kod sterujący pozostaje po naszej stronie: AniShift pamięta zamiar użytkownika, wybiera odpowiedni materiał, współpracuje z qBittorrentem i wykonuje przetwarzanie. Zewnętrzne usługi dostarczają danych. Nie trzeba w tym celu wbudowywać Sonarr ani utrzymywać jego własnej kompilacji.

Ten raport jest wynikiem badań, nie opisem wdrożonej integracji. Sonarr został odłożony zgodnie z decyzją użytkownika. Kod aplikacji AniShift nie był w tej partii zmieniany. Raport przygotowano do czytania i odsłuchu: najpierw wyjaśnienia, potem krótkie zestawienia i odnośniki do pełnych inwentaryzacji technicznych.

Uzupełniająca próba Slime OVA pokazała oba oblicza tych danych. Dla czwartego OVA otrzymano 16 nazwowo zgodnych kandydatów. Dla pierwszego OVA żaden z 21 rekordów nie potwierdzał nazwą pełnego tytułu z mapowania: 16 pozostało niejednoznacznych, a pięć było z nim sprzecznych. To ocena nazw i numeracji, nie zawartości mediów; konflikt kolejności pierwszych dwóch OVA nie rozstrzyga, który dostawca się myli.

**Stan odbioru:** badanie i raport są ukończone. Niezależne odbiory Opus5 części A (`ses_f363ca9a5ffeDVPeKHT7WzYist`) i B (`ses_f363d389cffezDZ8NuVvbrAhZX`) zakończyły się wynikiem **PASS WITH FINDINGS**, bez błędów materialnych. Uwagi z tych odbiorów oraz przeglądu syntezy uwzględniono. Końcowa weryfikacja korekt i syntezy przez Opus5 (`ses_f3631f3eeffes5rFtRdza7pEta`) zakończyła się wynikiem **PASS**; sprawdzono również wszystkie 57 lokalnych odnośników w czterech dokumentach. Jest to odbiór badań i dokumentacji, nie akceptacja integracji.

## 2. Co dokładnie przetestowaliśmy

Odczyty wykonano 22 września 2026 roku. Badanie metadanych objęło sześć wpisów: pierwszy i czwarty sezon Slime, osobną serię OVA Slime, drugą część finałowego sezonu Attack on Titan, Haibane Renmei oraz zapowiedziany kolejny wpis Dungeon Meshi. Dodatkowo odczytano dwa wyniki wyszukiwania AnimeSchedule i relacje Slime w AniList.

Bazowe badanie wydań, opisane w części B, objęło sześć różnych przypadków: Slime S1E4, S4E23, S4E24 i S4E10, a także pierwszy odcinek Haibane Renmei i Cowboy Bebop. Dwa zapytania powtórzono, aby porównać odpowiedzi i zachowanie cache. Dało to osiem odczytów Torrentio i 194 rekordy bez ponownego liczenia powtórek.

Po potwierdzeniu identyfikatora OVA w danych części A wykonano jeszcze dwa żądania GET: o czwarty i pierwszy odcinek Slime OVA, odpowiednio `kitsu:42022:4` i `kitsu:42022:1`. Łącznie badanie Torrentio obejmuje 10 żądań GET: osiem różnych przypadków i dwie powtórki. Uzupełnienie OVA dodało 37 rekordów do analizy, poza bazowymi 194. Suma 231 oznacza rekordy odpowiedzi, nie unikalne torrenty ani unikalne pliki w całym badaniu. Klasyfikacja bazowej próbki B pozostaje odrębna. Nie był to test obciążeniowy ani kontrola wszystkich pięciu OVA.

Mierzyliśmy rzeczywisty czas HTTP do odebrania całej odpowiedzi, wraz z kosztem zestawienia świeżego połączenia: rozwiązywaniem nazwy DNS oraz TCP/TLS widzianymi przez klienta. Nie izolowano czasów tych etapów; cache systemowy DNS nadal mógł mieć wpływ. Parsowanie JSON było mierzone oddzielnie. Zachowano surowe odpowiedzi, statusy, nagłówki cache, czas wykonania, liczbę bajtów i sumy kontrolne. Nie opieramy nowych liczb na wcześniejszych orientacyjnych czasach narzędzia webowego.

Nie pobierano anime, metainfo jego torrentów ani napisów. Nie uruchamiano transferów w qBittorrencie. Można więc ocenić pola API, nazwy, przypisania i czas otrzymania kandydatów, ale nie faktyczny obraz, kompletność dialogów czy osiągalność wszystkich części pliku.

## 3. Tytuły, sezony i relacje: co daje ani.zip

ani.zip przyjmuje identyfikator z katalogu, na przykład AniList, i zwraca jeden wzbogacony wpis. Odpowiedź ma tytuły w różnych językach, listę odcinków, liczbę zwykłych odcinków, liczbę dodatków, obrazy oraz mapowania identyfikatorów. W próbce występowały identyfikatory AniList, Kitsu, MyAnimeList, AniDB, TVDB, IMDb, TMDB, Anime-Planet, aniSearch i LiveChart. Niektóre pola bywają puste; identyfikatory nie zawsze są liczbami.

Najważniejsza praktyczna korzyść to przejście od wybranego anime w AniList do identyfikatora Kitsu używanego przez Torrentio oraz do dokładniejszych danych odcinków. Nie musimy zgadywać wszystkich nazw tego samego tytułu przy każdym żądaniu.

W danych pojawiły się nazwy angielskie, japońskie, romanizowane i wiele innych, w części wpisów także polskie. Tytuł w danym języku nie dowodzi istnienia audio lub napisów w tym języku. Pojedyncza wartość romanizowana może być skrótem, na przykład „tensura”, a nie pełną listą synonimów.

**Nie otrzymaliśmy gotowej listy wszystkich sezonów całej franczyzy.** Pierwszy sezon, czwarty sezon i OVA Slime miały różne identyfikatory anime, ale wspólne identyfikatory serii TVDB, IMDb i TMDB. Sam wspólny identyfikator lub identyczny plakat nie wystarcza do ustalenia, który wpis jest sezonem, dodatkiem lub osobną produkcją.

Relacje można uzupełniać z istniejącego AniList. Badanie potwierdziło powiązania do kontynuacji, historii pobocznych i spin-offu. Są też relacje do mangi i noweli, więc nie wszystko nadaje się do pobrania jako anime. Co więcej, katalogi nie zawsze rozumieją „sequel” tak samo: w przykładzie Slime AniList wskazywał OVA Coleus, a AnimeSchedule kolejny sezon telewizyjny. Pierwsza krawędź „sequel” nie jest zatem gotowym przyciskiem „następny sezon”.

Sprawdzone wywołanie ani.zip działa po ID. Próba parametru tekstowego `q` zwróciła błąd 400. Nie dowodzi to, że żaden inny endpoint wyszukiwania nie istnieje; oznacza tylko, że nie potwierdziliśmy takiej możliwości. Najprostsza obecnie zweryfikowana droga zachowuje AniList jako wejście do wyszukiwania tytułów.

## 4. Odcinki i przesunięcia numeracji

Obiekt odcinka może zawierać tytuł w kilku językach, opis, obraz, czas trwania, ocenę, datę, identyfikatory odcinkowe i kilka numeracji. To znacząco więcej niż sama liczba odcinków w sezonie.

Przykład Slime jest prosty: odcinek 23 czwartego sezonu ma numer absolutny 95. Odcinek 10 tego sezonu ma numer absolutny 82. To drugie mapowanie koordynator odczytał bezpośrednio z `slime-s4.raw.json` części A, z obiektu `episodes["10"]`; nie pochodzi ono z literalnej tabeli raportu A. Wydanie oznaczone „Season 4 - 95” może więc odpowiadać odcinkowi 23; sam brak zapisu S04E23 nie jest błędem.

Przykład Attack on Titan pokazuje trudniejszy przypadek. Osobny wpis „Final Season Part 2” ma lokalne odcinki od 1 do 12. W numeracji TVDB są to odcinki 17–28 sezonu 4, a w numeracji absolutnej 76–87. Zachowanie tych mapowań pozwala uniknąć błędnego utożsamienia lokalnego odcinka 1 z telewizyjnym S4E1.

Nie każde pole występuje zawsze. W 89 obiektach odcinków i dodatków numeracja absolutna była obecna 73 razy, a identyfikatory TVDB 77 razy. Identyfikator AniDB odcinka i lokalny klucz były obecne we wszystkich 89 obiektach tej próbki. To wynik próby, nie gwarancja schematu dla całego katalogu.

Odpowiedź zawiera również pole typu finału: koniec sezonu, części albo serii. Taki marker nie dowodzi jednak końca całej franczyzy, dostępności wszystkich plików ani braku późniejszych dodatków.

## 5. Dodatki: są, ale nie wszystkie znaczą to samo

ani.zip faktycznie zwraca obiekty specjalne, często pod kluczami takimi jak `S1` lub `S2`. **W tym miejscu S1 oznacza oznaczenie dodatku, nie sezon pierwszy.**

W sześciu badanych wpisach otrzymano 11 takich obiektów. Były wśród nich recap o Veldorze, wystąpienie promocyjne, komentarze do odcinków, krótkie materiały o Ramiris, specjalne zakończenie Haibane, galeria obrazów i wywiad z twórcami.

Z tego wynikają dwie ważne rzeczy. Po pierwsze, „dodatek” nie oznacza automatycznie odcinka fabularnego, który chcesz przetwarzać lektorem. Po drugie, lista specjalna przy sezonie nie zawiera koniecznie wszystkich związanych z nim OVA.

Slime OVA występuje jako osobny wpis z pięcioma zwykłymi kluczami odcinków i liczbą dodatków równą zero. Te pięć odcinków nie jest po prostu pięcioma specjalnymi pozycjami w odpowiedzi pierwszego sezonu. Jeden materiał może też być reprezentowany przez więcej niż jeden rodzaj powiązania katalogowego.

Uzupełniające odczyty Torrentio potwierdziły, że można uzyskać kandydatów dla takiego osobnego wpisu OVA. Czwarty lokalny odcinek mapuje się na TVDB S00E05, czyli piąty odcinek sezonu specjalnego. Pierwszy ujawnił konflikt: mapa przypisuje mu „Extra: The Tragedy of M?”, a trzy wyniki mają tytuł „Hey! Butts”, przypisany w mapie do odcinka drugiego. Dwa dalsze wyniki wskazują inny materiał z drugiego sezonu, oznaczony S2E00. Pozostałe 16 rekordów zachowuje historyczną ocenę niejednoznaczną. Jeden z nich ma jednak mocniejszy dowód numeracyjny: zapisany wcześniej listing TVDB w Sonarr łączy jego S00E02 z „The Tragedy of M?”. Nadal nie jest to kontrola zawartości pliku. Szczegóły i granice tej oceny zawiera aneks OVA.

**Możemy pokazać znalezione dodatki i ich tytuły. Nie możemy jeszcze obiecać automatycznego, kompletnego „cały sezon i wszystkie właściwe dodatki” bez dodatkowego ustalenia relacji oraz zakresu.** Brakuje jednolitego pola odróżniającego wszystkie recapy, OVA, wywiady, galerie i OP/ED. Nie należy dopisywać takich kategorii z pewnością, której dane nie dają.

## 6. Kiedy odcinek wychodzi, a kiedy rzeczywiście można go pobrać

To dwa różne pytania. ani.zip dostarcza daty związane z odcinkiem. W próbie był już obiekt przyszłego Slime S4E24, z planowaną datą 25 września 2026 i numerem absolutnym 96. Badanie wykonano 22 września. Istnienie obiektu nie oznaczało, że plik został opublikowany.

Nie wszystkie przyszłe wpisy mają listę odcinków. Dla kolejnego Dungeon Meshi istniał poprawny obiekt anime z tytułami i mapowaniami, ale lista była pusta. To inny stan niż błędny identyfikator, który zwrócił 404. Nie wolno interpretować pustej przyszłej listy jako anime bez planowanych odcinków.

Daty bywają sprzeczne. ani.zip zwraca pola `airDate` i `airdate`, różniące się wielkością litery. W danych Haibane różnica wynosiła jeden dzień dla wszystkich 13 odcinków; przy trzecim OVA Slime wynosiła 20 dni. Nie rozstrzygnięto, która data jest poprawna. Nie należy nadpisywać jednej drugą bez świadomej reguły i informacji o źródle.

AnimeSchedule dostarczyło pola przesunięć emisji, oddzielne informacje dla wersji japońskiej oraz angielskich napisów i dubbingu. W przykładzie Slime były konkretne przesunięcia tygodniowe. Nie dostaliśmy jednak historii wszystkich zmian. Starsze przesunięcia potrafią nadal pozostawać przy zakończonym sezonie, więc sam napis „Delayed” nie oznacza automatycznie, że aktualnie oczekiwany odcinek jest opóźniony.

Niektóre daty AnimeSchedule są umownymi wartościami pustymi, a w polach godzinowych istotna jest godzina i minuta, nie cały zapisany dzień. Traktowanie każdego takiego stringa jako terminu najbliższej emisji prowadziłoby do błędów. Publiczne wyszukiwanie działało bez konta; dokumentowany endpoint tygodniowego harmonogramu wymagał uwierzytelnienia i odpowiedział 401. Nie testowano go z tokenem.

Dokumentacja AnimeSchedule przewiduje także filtrowanie anime po identyfikatorach AniList, MyAnimeList i AniDB oraz pobranie konkretnego wpisu przez `/anime/{slug}`. To możliwości dokumentowane, nie sprawdzone w tej próbie live. Według dokumentacji pola z null bywają pomijane, a puste daty mają specjalną wartość. Brak pola, null, taki znacznik daty i liczba zero nie są zamiennymi stanami.

**Dla subskrypcji harmonogram może pomagać zdecydować, kiedy sprawdzać i co wyświetlić. Nie powinien sam zlecać pobrania ani kończyć oczekiwania.** Dopiero znalezienie odpowiedniego kandydata daje informację o potencjalnym wydaniu, a jego rzeczywista dostępność wymaga dalszej weryfikacji. Pusta odpowiedź Torrentio znaczy „brak wyników w tej odpowiedzi”, nie „na pewno jeszcze nie opublikowano”.

## 7. Co zwraca Torrentio i czy jest ograniczone do Nyaa

Torrentio zwraca listę kandydatów dla wskazanego odcinka. W podstawowej próbie były 194 rekordy, bez podwójnego liczenia powtórek. Każdy miał hash torrenta. W 188 rekordach były dodatkowo indeks i nazwa pliku. Sześć nie miało konkretnego selektora pliku. Osobne 37 rekordów OVA miało wszystkie trzy informacje: hash, indeks i nazwę pliku. Obecność tych pól nie jest dowodem poprawnej tożsamości materiału.

W 33 z bazowych 194 rekordów opis `title` był ucięty znakiem „…”. Dla Slime S4E23 w wierszach 1 i 17 numer 95 zachował się w `behaviorHints.filename`, nie w uciętym opisie. Kod może też pomijać osobną linię ścieżki pliku, między innymi przy zbliżonym rozmiarze pliku i torrenta lub nakładających się tytułach. Sam opis nie jest więc pełnym manifestem paczki, a nazwa końcowa pliku nie zastępuje całej ścieżki.

**Nie jest ograniczone do Nyaa.** W bazowej części B oprócz NyaaSi wystąpiło dziesięć etykiet: TorrentGalaxy, nekoBT, Rutor, 1337x, EXT, ThePirateBay, EZTV, Cinecalidad, RARBG i TokyoTosho. Próba OVA dodała HorribleSubs, co daje 11 różnych etykiet poza NyaaSi w całym badaniu. Są to etykiety pochodzenia zachowane w odpowiedzi, nie dowód, że wszystkie wymienione serwisy obecnie działają albo zostały odpytane na żywo.

W odpowiedzi dla Slime S4E23 tylko jeden z 40 rekordów miał etykietę NyaaSi. Przy starszym S4E10 było ich 12 z 46, a dla Haibane wszystkie 10. W OVA 4 etykietę NyaaSi miało 15 z 16 rekordów, a w OVA 1 — 16 z 21. Nie oznacza to, że hash opisany jako TorrentGalaxy nie występuje też na Nyaa. Odpowiedź nie przedstawia pełnej historii wszystkich indeksów, które znały dany torrent.

Pole `sources` ma inne znaczenie: zawiera wskazówki odkrywania peerów, czyli trackery i DHT. To nie lista serwisów, z których agregator zebrał wydania. Także tracker ze słowem „Nyaa” nie jest dowodem pochodzenia rekordu z Nyaa.

## 8. Seedy, peery, rozmiary i jakość: co wiemy naprawdę

### Liczba udostępniających

Liczba seeders jest dostępna w opisach, obok ikony człowieka. W 194 rekordach podstawowej próby można było ją odczytać. Nie jest jednak oddzielnym liczbowym polem JSON. AniShift musiałby wydobywać ją z tekstu i uwzględniać zmianę formatu prezentacji.

Seed oznacza uczestnika posiadającego kompletny torrent. Liczba przedstawiona przez Torrentio pochodzi z danych dostawcy. **Nie jest to pomiar liczby aktualnych połączeń naszego qBittorrenta. Nie ma też timestampu pomiaru tej liczby.** Dodatnia wartość nie gwarantuje, że transfer ruszy ani że będzie szybki.

Nie otrzymaliśmy liczby leechers, czyli uczestników nieposiadających jeszcze całości. Nie było też liczby wszystkich peerów lub peerów połączonych z naszym klientem. Brak takiego pola oznacza niewiadomą, nie zero. Po uruchomieniu zadania qBittorrent może dostarczać własne statystyki połączeń i informacje o swarmie, ale nie pobieraliśmy ich w tej próbie API.

### Rozmiar

Rozmiar również był tekstem w opisie, obok ikony dysku. Z odczytanego kodu wynika, że chodzi o rozmiar rekordu pliku, niekoniecznie całej paczki. Wartość jest zaokrąglona i prezentowana jako MB lub GB. Nie otrzymaliśmy pola z dokładnymi bajtami wybranego wideo ani pełnej paczki.

To wystarcza do orientacyjnej prezentacji, ale nie do jednoznacznego dopasowania dwóch plików po rozmiarze. Przy niektórych rekordach bez indeksu pliku nie ustalono także, jak dokładnie powstała wartość rozmiaru.

### Języki, napisy, kodek i rozdzielczość

W nazwach i opisach są oznaczenia takie jak 1080p, 720p, AV1, HEVC, AAC, FLAC, BluRay, WEB-DL, MultiSub lub Dual Audio. Pojawiają się też flagi języków, w tym polska. Dostępne bywają nazwy grup, a część danych można wydobyć z pola grupującego podobne wydania.

**Są to deklaracje i wyniki parsowania nazw, nie analiza pliku.** Nie ma strukturalnej listy ścieżek napisów, ich formatu, liczby dialogów, kompletności tłumaczenia czy synchronizacji. Flaga polska nie wystarcza do pominięcia tłumaczenia. Nie wolno też utożsamiać jakości 1080p z gwarancją lepszego obrazu niż dobre 720p.

Ten brak dotyczy badanych odpowiedzi. Zapisany kod Torrentio w `streamInfo.js:55` przewiduje `subtitles: getSubtitles(record)`, ale nie otrzymaliśmy tego pola live ani nie sprawdziliśmy działania tej ścieżki. Nie jest to dowód globalnego braku obsługi napisów przez usługę.

W próbce wystąpiła etykieta TeleSync przy nazwie sugerującej plik transportowy z emisji telewizyjnej. Nie zdiagnozowaliśmy przyczyny, ale już ta rozbieżność pokazuje, że etykiety należy traktować jako wskazówki, nie techniczny pomiar.

## 9. Pliki w paczkach: duża zaleta i istotna granica

Torrentio potrafi wskazać konkretne wideo w dużym torrencie. Dla Slime S1E4 pierwszy wynik EMBER obejmował paczkę z kilkoma sezonami i dodatkami, ale wskazanie dotyczyło pliku czwartego odcinka pierwszego sezonu. W innym przypadku ta sama paczka Rutor była zwracana dla E10 i E23 z różnymi indeksami plików.

To jest istotna przewaga nad wynikiem, który mówi tylko „znaleziono torrent z całą serią”. Nadal nie dostajemy jednak pełnej listy plików paczki, fontów, dodatkowych napisów i innych materiałów towarzyszących.

Nie potwierdziliśmy bezwarunkowej zgodności `fileIdx` z indeksem pliku w API qBittorrenta. Odczytany kod qB pomija pliki paddingowe w swojej numeracji. Nie ustalono, czy numer z bazy Torrentio uwzględnia je w ten sam sposób. To możliwa różnica kontraktów, nie wykazany błąd w każdej paczce.

Przed faktyczną selekcją trzeba uzgodnić wskazanie z rzeczywistą listą plików klienta: właściwym torrentem, ścieżką i tożsamością materiału. Sam numer bez kontroli nie wystarcza. Także sama nazwa końcowa może powtarzać się w kilku katalogach paczki. Brak `fileIdx` nie oznacza zera; domyślny wybór największego pliku przez Stremio nie jest bezpiecznym odpowiednikiem wyboru odcinka w AniShift.

## 10. Trafność: szybki wynik nie zawsze jest właściwym wynikiem

Najbardziej istotne ograniczenie znaleziono w samych odpowiedziach. Dostawca zwraca czasem rekordy błędnie przypisane do anime lub odcinka.

Dla Slime S1E4 w 47 rekordach wykonawca wskazał 8 błędnych: spin-off Slime Diaries oraz OAD lub OVA. Jeden torrent Trix występował zarówno ze wskazaniem poprawnego odcinka głównej serii, jak i odcinka spin-offu. Ten sam hash nie oznacza tego samego żądanego materiału.

Dla Cowboy Bebop E1 w 51 rekordach wskazano 22 błędne. Były wśród nich inne anime, plik menu i książka EPUB. Nie wystarczy więc zaufać, że zapytanie po poprawnym Kitsu ID automatycznie gwarantuje tożsamość każdej odpowiedzi.

Jednocześnie wszystkie 10 wyników Haibane było nazwowo zgodnych. Wyniki aktualnego sezonu Slime także wyglądały znacznie lepiej. Nie wyprowadzamy z tej małej, celowo trudnej próbki procentu błędów całej usługi.

W pierwotnej części B sześć wskazań Slime pozostawiono niejednoznacznych z powodu samej numeracji absolutnej. Raport A potwierdza mapowanie 23 na 95, a odczyt koordynatora z surowej odpowiedzi A potwierdza 10 na 82. To usuwa konkretną wątpliwość numeracji przy syntezie, ale nie jest kontrolą zawartości mediów. Nie zmieniamy historii odrębnej klasyfikacji B ani nie ogłaszamy wszystkich tych plików fizycznie poprawnymi na podstawie samego numeru.

Uzupełnienie OVA wzmacnia potrzebę takiej kontroli. Wszystkie 16 wyników OVA 4 było nazwowo zgodnych, ale OVA 1 wymaga zachowania rozróżnienia między 16 wynikami niejednoznacznymi a pięcioma sprzecznymi z mapą. Nie włączamy tych ocen do klasyfikacji bazowych 194 rekordów. Zgodność dwóch hashy OAD Erai-raws z historycznymi wynikami błędnie dopuszczonymi przez Sonarr jako S1E4 pokazuje również, że ten sam torrent może być właściwym kandydatem do OVA i niewłaściwym do odcinka sezonu głównego. To porównanie zapisanych dowodów, nie nowa próba Sonarr.

**Wniosek: Torrentio może szybko dostarczyć listę kandydatów, ale nie powinno samodzielnie zatwierdzać automatycznego pobrania.** Kontrola musi uwzględniać pełną tożsamość, rodzaj materiału, kontekst katalogu w paczce i rozpoznaną numerację. Proste sprawdzenie „czy w nazwie jest 04” przepuści błędny spin-off albo OAD.

## 11. Szybkość i świeżość danych

Wyniki pomiarów były następujące:

| Operacja | Zaobserwowany czas HTTP | Zakres |
| --- | --- | --- |
| ani.zip: mapa jednego anime i lista odcinków | Około 85–201 ms | Sześć wpisów; cztery odpowiedzi HIT i dwie EXPIRED w cache |
| Torrentio: bazowa próba B | 52,340–245,279 ms | Osiem żądań: sześć przypadków i dwie powtórki; mieszane stany cache |
| Torrentio: uzupełnienie OVA | 158,8581–1833,6603 ms | Dwa żądania; oba ze stanem cache MISS; wolniejsze dotyczyło OVA 4 |
| AnimeSchedule: wyszukiwanie tytułu | Około 458 ms i 1,45 s | Dwa wyszukiwania |
| AniList: użyte zapytania katalogowe | Około 1,32 s i 1,49 s | Dwa różne zapytania GraphQL |

Cały zbiór 10 żądań Torrentio ma zakres 52,340–1833,660 ms, po zaokrągleniu do trzech miejsc po przecinku. Pobranie gotowej listy może być bardzo szybkie, lecz wolniejszy wynik OVA 4 trwał około 1,83 sekundy i wyraźnie przekroczył zakres bazowej próby. Nie jest to pomiar całej ścieżki od wpisania nazwy do startu transferu. Nie należy sumować najlepszych wartości z różnych żądań i obiecywać takiego czasu każdego dnia.

ani.zip zwracało cache na 15 minut. Niepuste odpowiedzi Torrentio deklarowały godzinę zwykłej ważności, do czterech godzin obsługi starszego wyniku podczas odświeżania i do tygodnia przy błędzie. Puste odpowiedzi miały krótszy zwykły czas, jedną minutę. Są to dyrektywy cache, nie gwarancja, że każda odpowiedź będzie stara o maksymalnie taki czas ani że źródło zindeksowano właśnie teraz.

W pierwszych odczytach części wyników Torrentio nagłówek Age wskazywał około 1,8 godziny, a stan cache wynosił UPDATING. Późniejsze powtórki miały identyczne ciała i mniejszy Age. Szybkie zwrócenie odpowiedzi może więc wynikać z wcześniejszego przygotowania danych, nie z bieżącego przeszukania wszystkich indeksów. W obu odpowiedziach OVA nie było nagłówka Age; brak nie oznacza zera. Ich stan MISS dotyczy cache CDN i nie dowodzi zimnej bazy ani świeżego zebrania wydań z indeksów.

**Dla świeżych premier otwarta pozostaje szybkość pojawienia się nowego wydania w agregatorze.** Nasz najnowszy badany odcinek miał już kilka dni. Nie obserwowano momentu publikacji i opóźnienia indeksowania minuta po minucie. To osobny parametr od czasu HTTP.

Nie wykonano testu 30 odcinków dziennie ani obciążania usługi. Przy regularnym użyciu warto pobierać mapowanie wybranego anime raz i ponownie go używać zgodnie z zasadami cache, zamiast odpytywać je osobno dla każdego odcinka. To rekomendacja ograniczenia zbędnej pracy, nie wdrożony mechanizm.

## 12. Windows teraz, serwer później i utrzymanie

Te usługi udostępniają HTTP i JSON. Nasz kod Pythona może korzystać z tego samego kontraktu na Windowsie i później na serwerze Linux. Sam wybór zewnętrznego API nie wymaga dołączenia aplikacji C# ani jej kompilowania. qBittorrent i narzędzia mediów pozostają osobnymi zależnościami systemowymi; ich ścieżki i uruchamianie nadal zależą od platformy.

Własny kod nie oznacza pełnej niezależności. AniShift kontrolowałby swój stan i logikę, ale dostępność i jakość informacji zależałyby od usług zewnętrznych. Nie ustalono autorytatywnej dokumentacji, SLA ani wszystkich warunków ani.zip. Brak takich ustaleń nie jest ani gwarancją bezpłatnej trwałej usługi, ani dowodem zakazu użycia.

Publiczny kod Torrentio ma licencję Apache 2.0. Nie potwierdzono jednak, że uruchomienie tego kodu samodzielnie daje kompletną aktualną bazę. Odczytany projekt opisuje warstwę odpytywania zebranych rekordów; dostęp do danych i ich regularne zbieranie to osobny problem. Nie należy obiecywać, że awarię hostowanego API naprawimy prostym „postawimy sobie to samo”.

AnimeSchedule dokumentuje token aplikacji, limity i wymagania atrybucji. Anonimowe endpointy są według dokumentacji wewnętrzne i mają inne ograniczenia. Z tego względu jest rozsądne traktowanie harmonogramu jako opcjonalnego wzbogacenia, a nie warunku wykonania każdego ręcznego pobrania.

Dokumentacja zawiera też klauzulę: „Cache API data only as needed and do not use it to train AI or machine learning models”. To deklarowany warunek ograniczenia cache do potrzeb i zakaz trenowania modeli na danych API. Nie utożsamiamy go z zakazem inferencji LLM ani TTS; sam cytat nie rozstrzyga wszystkich warunków konkretnego zastosowania.

## 13. Co można zbudować na tych danych, a czego jeszcze nie potwierdzono

**Można rozważać szybki interfejs informacyjny:** wyszukać anime w istniejącym katalogu, pobrać listę odcinków z mapowaniami i pokazać kandydatów z Torrentio, z podaniem źródła, przybliżonego rozmiaru i zgłoszonych seedów. Przy nieznanych danych należy pokazać brak informacji, a nie wymyśloną wartość zero.

**Można rozważać wygodniejszy wybór:** użytkownik wskazuje odcinki, nie musi samodzielnie znać wszystkich aliasów ani numeracji absolutnej. Informacje o paczkach mogą zmniejszyć ręczne szukanie właściwego pliku.

**Nie ma jeszcze dowodu bezobsługowego, poprawnego pobierania wszystkich żądanych anime.** Trzeba rozstrzygnąć błędne kandydatury, selekcję plików po rzeczywistych metadanych torrenta, napisy oraz zachowanie przy niepełnych i starych danych. Dla automatu dziennego ważniejsze od wielkości listy będzie to, czy potrafi wybrać właściwy materiał i bezpiecznie odmówić nierozstrzygalnego wyboru.

Zakres zachowany po stronie AniShift obejmuje subskrypcje, zamiar „od 5”, kolejkę, zapobieganie duplikatom, potwierdzanie ukończenia pobrania, wznowienie i przetwarzanie. To istniejące odpowiedzialności, nie uzasadnienie do tworzenia ich drugiej kopii.

Wniosek po tej partii: **ani.zip jest obiecującym wzbogaceniem metadanych, Torrentio szybkim dodatkowym źródłem kandydatów, a AnimeSchedule opcjonalnym źródłem harmonogramu.** Nie rekomendujemy jeszcze wyłączenia dotychczasowego źródła ani automatycznej akceptacji pierwszego wyniku. Dalsza decyzja powinna opierać się na trafności i świeżości dla rzeczywistych wyborów użytkownika oraz kontrolowanym sprawdzeniu selekcji pliku, nie na kolejnej szerokiej liście narzędzi.

## 14. Ściąga: gdzie jest konkretna informacja

| Potrzeba | Źródło i stan |
| --- | --- |
| Nazwa anime i nazwy w innych językach | AniList, ani.zip; potwierdzone |
| Rok i sezon kalendarzowy | AniList, AnimeSchedule; nie mylić z numerem sezonu TVDB |
| Pełna franczyza i kolejność sezonów | Relacje częściowo dostępne; rozbieżności i brak gwarancji kompletności |
| Lista i tytuły odcinków | ani.zip; potwierdzone, nie wszystkie wpisy przyszłe mają listę |
| Numer lokalny, sezonowy i absolutny | ani.zip; potwierdzone w zróżnicowanych przypadkach |
| OVA, recapy i inne dodatki | Obiekty specjalne oraz osobne wpisy; dwa odczyty OVA potwierdziły kandydatów, ale ujawniły konflikt tożsamości OVA 1 |
| Planowana data i przesunięcia | ani.zip oraz AnimeSchedule; konflikty dat i brak historii zmian |
| Kandydaci do pobrania | Torrentio; istnieją błędne przypisania |
| Źródła poza Nyaa | 11 dodatkowych etykiet łącznie, w tym 10 w bazowej części B; nie gwarancja aktualności indeksów |
| Hash torrenta i indeks pliku | Torrentio; indeks bywa nieobecny i wymaga uzgodnienia z klientem |
| Pełna lista plików paczki | Nie w badanej odpowiedzi Torrentio; potrzebne metainfo/klient |
| Seeders | Tekst w opisie Torrentio; bez daty pomiaru |
| Leechers, aktywne połączenia | Brak w odpowiedziach Torrentio; informacje klienta to osobny etap |
| Rozmiar | Tekst zaokrąglony, zwykle wybranego pliku; brak dokładnych bajtów |
| Rozdzielczość, kodek, grupa, języki | Głównie deklaracje w nazwach i opisach |
| Rzeczywiste napisy i kompletność | Nie potwierdzone przez te odpowiedzi; wymagają kontroli materiału |

## 15. Dowody i raporty techniczne

Pełne wykazy obejmują wszystkie pola napotkane w badanych odpowiedziach. Nie są deklaracją wszystkich możliwych pól API w każdej wersji i konfiguracji.

- [Raport metadanych i harmonogramu](reports/anime-api-metadata-validation.md): 74 ścieżki pól ani.zip oraz 91 ścieżek anonimowego wyszukiwania AnimeSchedule, przykłady i liczby brakujących wartości.
- [Raport wydań Torrentio](reports/anime-api-release-validation.md): pełna lista pól streamów, rozkład providerów, ocena bazowych 194 rekordów, czasy i cache, źródła kodu i kontrakt plików. W A i B zapisano odbiory PASS WITH FINDINGS oraz korekty dokumentacji; historyczne klasyfikacje i surowe dane pozostają bez zmian. Uzupełnienie OVA jest opisane w tej syntezie.
- [Brief badań](briefs/anime-api-validation.md): zakres, budżety, zakazy, kryteria końca.
- [Specyfikacja potrzeb](final/spec.md): wymagania użytkownika i nierozstrzygnięte wybory.

Dowody lokalne metadanych: `C:\Users\MattyMroz\AppData\Local\Temp\opencode\anime-api-metadata-20260922-a\`. Dowody lokalne wydań: `C:\Users\MattyMroz\AppData\Local\Temp\opencode\anime-release-b-20260922-01\`. Znajdują się tam surowe ciała, metadane pomiarów, snapshoty instrumentów i wyniki kontroli integralności. Katalogi tymczasowe nie są opublikowanym archiwum i wymagają dostępu do tej maszyny.

Dowody lokalne OVA: `C:\Users\MattyMroz\AppData\Local\Temp\opencode\anime-api-ova-20260922-followup\`. Najważniejsze pliki:

- [Zbiorcza analiza OVA](file:///C:/Users/MattyMroz/AppData/Local/Temp/opencode/anime-api-ova-20260922-followup/analysis.json) i [mapowanie wejściowe](file:///C:/Users/MattyMroz/AppData/Local/Temp/opencode/anime-api-ova-20260922-followup/mapping-evidence.json): liczebności, obecność pól, etykiety providerów oraz fragment zapisanej mapy ani.zip z odwołaniem do jej źródła i sumy SHA-256.
- [Kandydaci OVA 4](file:///C:/Users/MattyMroz/AppData/Local/Temp/opencode/anime-api-ova-20260922-followup/ova-4.candidates.json) i [kandydaci OVA 1](file:///C:/Users/MattyMroz/AppData/Local/Temp/opencode/anime-api-ova-20260922-followup/ova-1.candidates.json): każdy rekord, jego numer w odpowiedzi, hash, indeks, nazwa oraz uzasadnienie oceny.
- [Pomiar OVA 4](file:///C:/Users/MattyMroz/AppData/Local/Temp/opencode/anime-api-ova-20260922-followup/ova-4.meta.json) i [pomiar OVA 1](file:///C:/Users/MattyMroz/AppData/Local/Temp/opencode/anime-api-ova-20260922-followup/ova-1.meta.json): URL, status, czas HTTP i parsowania JSON, nagłówki, bajty oraz SHA-256. Odpowiadają im surowe ciała `ova-4.raw.json` i `ova-1.raw.json`; `run.json` zapisuje wykonanie dokładnie dwóch GET.
- [Porównanie hashy z historycznym Sonarr](file:///C:/Users/MattyMroz/AppData/Local/Temp/opencode/anime-api-ova-20260922-followup/sonarr-hash-comparison.json): dwa zgodne hashe oraz ścieżka i SHA-256 historycznej odpowiedzi. To porównanie offline.
- [Historyczny listing odcinków TVDB w odpowiedzi Sonarr](file:///C:/Users/MattyMroz/AppData/Local/Temp/opencode/sonarr-search-20260922-f42a91/batch01/response-007.json): 110 rekordów, w tym 14 z sezonu 0. SHA-256: `88f27951ce5904dedcc5ed9e0432d9c516a1cd05a41412e13029b5c4e89e6e5e`. W aneksie wykorzystano go do dodatkowego porównania numerów i tytułów OVA, bez nowego odczytu runtime.

Linki `file:///` wymagają dostępu do tej maszyny i mogą nie działać jako klikalne odnośniki w każdym czytniku. Pełna ścieżka katalogu pozwala odnaleźć pliki bez takiej obsługi.

Źródła oryginalne: [ani.zip, Slime S4](https://api.ani.zip/mappings?anilist_id=182205), [ani.zip, Slime OVA](https://api.ani.zip/mappings?anilist_id=106509), [Torrentio, Slime S4E23](https://torrentio.strem.fun/stream/series/kitsu:49235:23.json), [Torrentio, Slime S1E4](https://torrentio.strem.fun/stream/series/kitsu:41024:4.json), [Torrentio, Slime OVA 4](https://torrentio.strem.fun/stream/series/kitsu:42022:4.json), [Torrentio, Slime OVA 1](https://torrentio.strem.fun/stream/series/kitsu:42022:1.json), [dokumentacja AnimeSchedule](https://animeschedule.net/api/v3/documentation), [kod Torrentio przypięty do badanego commita](https://github.com/TheBeastLT/torrentio-scraper/tree/39015cd654c587b041b327b6db701c423d4ebe97), [kontrakt streamów Stremio](https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/api/responses/stream.md). Linki usług mogą z czasem zwrócić inne dane; podstawą liczb są snapshoty z 22 września 2026.

## 16. Aneks: co dokładnie potwierdziła próba Slime OVA

### Dwa odczyty i granica klasyfikacji

Identyfikator Kitsu `42022` pochodzi z zapisanej odpowiedzi ani.zip dla AniList `106509`, nie ze zgadywania składni dodatków. Wykonano dwa GET 22 września 2026, kolejno o lokalny odcinek 4 i 1. Oba zakończyły się HTTP 200, bez ponowień i przekierowań. Czasy poniżej obejmują HTTP do odebrania całego ciała; parsowanie JSON mierzono osobno.

| Przypadek | Rekordy | Nazwowo zgodne | Niejednoznaczne | Sprzeczne z mapą | HTTP, ms | Cache |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| OVA 4, `kitsu:42022:4` | 16 | 16 | 0 | 0 | 1833,6603 | MISS |
| OVA 1, `kitsu:42022:1` | 21 | 0 | 16 | 5 | 158,8581 | MISS |

**Kategorie są wnioskowaniem z nazw, ścieżek i zapisanej mapy, nie kontrolą zawartości plików.** Dla OVA 1 brak potwierdzenia pełnego tytułu nie oznacza, że wszystkie 21 rekordów wskazuje błędną zawartość. Oznacza, że na tych dowodach nie można zatwierdzić zgodności z historią „Extra: The Tragedy of M?”.

Odpowiedź OVA 4 miała 28 190 bajtów, a parsowanie JSON trwało około 0,1429 ms. OVA 1 miała 34 224 bajty, z parsowaniem około 0,1401 ms. Obie deklarowały godzinę zwykłej ważności cache, cztery godziny obsługi starszego wyniku podczas odświeżania i tydzień przy błędzie. W żadnej nie było Age. Instrument tworzył osobne połączenie HTTPS dla każdego żądania, a pomiar obejmował DNS/TCP/TLS i odczyt ciała. Wolniejszy wynik OVA 4, około 1,83 sekundy, był pierwszym żądaniem procesu. Nie izolowano przyczyny różnicy: nie można przypisać jej TLS, cache ani pracy serwera na podstawie tych dwóch punktów.

### OVA 4: numer lokalny, numer TVDB i historyczne hashe

Mapa ani.zip przypisuje lokalnemu odcinkowi 4 tytuł „Extra: Rimuru’s Glamorous Life as a Teacher, Part 2”, AniDB EID `224626` i TVDB ID `7733387`, z sezonem 0 oraz odcinkiem 5. Dlatego zarówno oznaczenie OVA/OAD 04 w odpowiednim kontekście, jak i TVDB S00E05 wspierają zgodność nazwową.

Próg oceny nie oznacza jednak jednakowej siły wszystkich 16 dopasowań. **Cztery rekordy mają mocniejsze zakotwiczenie:** wiersze 1 i 6 podają jawny tytuł historii, a 4 i 7 numer TVDB S00E05. Pozostałe 12 opiera się na numerze 04 i kontekście OVA/OAD. Ich historyczna ocena „nazwowo zgodne” zakłada zgodność tej pozycji numeracji mimo konfliktu dwóch pierwszych odcinków; nie jest osobnym potwierdzeniem tytułu ani zawartości tych 12 plików. Dla OVA 1 samo 01 nie wystarczyło z powodu konfliktu wykazanego właśnie na tej pozycji.

Wiersze kandydatów liczymy od 1, według kolejności zapisanej odpowiedzi. Wiersz 1 to EMBER: hash `aa3d7f95745c1564da5dc335a6865a2cb1765ab2`, `fileIdx=28`, plik `S01OAD04-Rimuru's Glamorous Life as a Teacher, Part 2 [056F6D66].mkv` w katalogu `02. OVA/`. Wiersz 4 wskazuje S00E05 przy `fileIdx=92`, a wiersz 7 LostYears ma jednocześnie `S00E05 (OVA 04)`. To konkretne przykłady różnych numeracji wskazujących tę samą historię według mapy.

Ta sama paczka EMBER ma w zapisanych odpowiedziach indeks 3 dla S1E4, 28 dla OVA 4 i 25 dla OVA 1. Hash identyfikuje więc paczkę, a nie sam żądany odcinek.

Wiersze 11 i 15 to Erai-raws, odpowiednio 1080p i 720p, oba z `fileIdx=0`. Ich hashe to `6423825269d77d16ae5937f0d2f6ce3dfd25bea4` oraz `698e448f469913f2ddd2fa904b08cf7f0ba997bf`. Są zgodne z hashami historycznych wyników Sonarr zapisanych w `sonarr-hash-comparison.json`. Tam oba OAD miały `approved=true`, `mappedSeasonNumber=1`, `mappedEpisodeNumbers=[4]` i `episodeRequested=true`, czyli zostały błędnie dopuszczone jako S1E4. Porównanie potwierdza tożsamość hashy i historyczne przypisanie, nie fakt pobrania ani poprawność mediów.

### OVA 1: konflikt tytułu i kolejności

Zapisana mapa ani.zip przypisuje lokalnemu odcinkowi 1 tytuł „Extra: The Tragedy of M?” i AniDB EID `214956`. Nie zawiera dla niego numeracji TVDB. W tym samym źródłowym pliku mapy lokalny odcinek 2 ma tytuł „Extra: Hey! Butts!” i AniDB EID `210856`.

Dodatkowa korroboracja offline pochodzi z historycznej odpowiedzi Sonarr `batch01/response-007.json`, wskazanej w sekcji dowodów. Listing zawiera 110 odcinków, w tym 14 z sezonu 0. **S00E02** ma tytuł „The Tragedy of M?”, datę `2019-07-09` i TVDB ID `7205861`; **S00E03** ma „Hey! Butts!”, datę `2019-12-04` i TVDB ID `7205862`. S00E04, S00E05 i S00E06 mają kolejno TVDB ID `7651072`, `7733387` i `7733391`, zgodne z lokalnymi OVA 3, 4 i 5 w ani.zip. Jest więc dodatkowy dowód mapowania numerów i tytułów, mimo brakujących pól TVDB przy pierwszych dwóch obiektach ani.zip.

- **Trzy rekordy sprzeczne z tytułem mapy:** wiersze 1 i 8 EMBER oraz 9 LostYears mają jawne „Hey! Butts” przy oznaczeniu pierwszego OVA/OAD. LostYears łączy `S00E02 (OVA 01)` z „Hey! Butts!”, podczas gdy powyższy listing łączy S00E02 z „The Tragedy of M?”, a „Hey! Butts!” z S00E03. To konflikt numeru i tytułu wobec listingu TVDB oraz mapy ani.zip. Wiersz 1 wskazuje `fileIdx=25` w paczce EMBER; zgodność hasha paczki nie usuwa różnicy między historiami.
- **Dwa rekordy wskazujące inny materiał:** wiersz 4 Erai-raws zawiera `2nd Season - 00`, a wiersz 6 wskazuje S02E00. Ich nazwy są sprzeczne z żądaną historią OVA.
- **Szesnaście rekordów historycznie niejednoznacznych:** 15 ma tylko numer OVA/OAD 01 bez tytułu historii. Wiersz 5 ma S00E02 i jest **zgodny numeracyjnie z dodatkowym listingiem TVDB** dla „The Tragedy of M?”. To mocniejszy dowód dla tego jednego rekordu niż przy pierwotnej ocenie, choć brak tytułu w nazwie nadal nie potwierdza zawartości pliku. Zachowujemy konserwatywny historyczny podział 16 niejednoznacznych i 5 sprzecznych względem mapy; nie przepisujemy zapisanych klasyfikacji.

W tej samej odpowiedzi OVA 1 hash TorrentGalaxy `d795b2eb922106ab146e00b5104f3ea47da85529` wskazuje zarówno indeks 89 z S00E02 (wiersz 5), jak i indeks 99 z S02E00 (wiersz 6). To wyjaśnia 21 rekordów przy 20 unikalnych hashach w tej odpowiedzi.

Nie ustalono, czy konflikt pierwszych dwóch OVA powstał w mapie, numeracji wydań czy przypisaniu agregatora. Listing TVDB wzmacnia porównanie metadanych, ale wspólna linia ich pochodzenia nie daje niezależnego potwierdzenia zawartości mediów ani prawdziwej kolejności publikacji. Nie przypisujemy winy wydaniu ani dostawcy. Także numeryczna kolejność AniDB EID nie dowodzi chronologii. Rozstrzygnięcie przyczyny nadal wymaga dowodu, którego to badanie nie dostarczyło.

### Pola i etykiety w dodatkowych 37 rekordach

Wszystkie 37 rekordów miało hash, nieujemny całkowity `fileIdx`, nazwę pliku i tekstowe informacje o seeders oraz rozmiarze. W tym uzupełnieniu wystąpiły 22 unikalne hashe i 37 unikalnych par hash–indeks; to liczniki tylko próby OVA. `sources` występowało w 33 rekordach, a w czterech go brakowało. Uzupełnienie nie dostarczyło strukturalnych pól leechers, peers, napisów, dokładnych bajtów mediów ani czasu pomiaru seeders. Zakres deklarowanych seeders wynosił 2–320 dla OVA 4 oraz 1–320 dla OVA 1; nie był pomiarem połączeń klienta.

OVA 4 miała 15 etykiet NyaaSi i jedną TorrentGalaxy. OVA 1 miała 16 NyaaSi, dwie TorrentGalaxy, dwie HorribleSubs i jedną 1337x. HorribleSubs występuje jako etykieta providera w wierszach 13 i 20, a nie tylko jako nazwa grupy w nazwie pliku. To jeden nowy rodzaj etykiety względem części B, nie dowód działania historycznego serwisu obecnie.

**Wniosek aneksu:** osobny wpis OVA pozwala znaleźć kandydatów, ale nie usuwa potrzeby rozpoznania pełnej tożsamości odcinka. Dobre dopasowanie OVA 4 i konflikt OVA 1 wspólnie wyznaczają granicę dowodu. Nie potwierdzono kompletności wszystkich dodatków, osiągalności torrentów ani gotowości automatycznej integracji.

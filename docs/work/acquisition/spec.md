---
kind: specification
status: do-akceptacji-właściciela
updated: 2026-09-29
baseline: 0e8a6bf9194d2786d426d3f3a58f48272b3eb087
---

# Specyfikacja: wspólne pobieranie i subskrypcje anime

**Decyzja orkiestratora 2026-09-29, do potwierdzenia:** uproszczenia W-01/W-04/W-06, prezentacji R-03–R-06, zakresu P-01, ponowienia P-05 i dostępności S-01 według zaktualizowanego `ux.md`. Nie zmieniają heurystyki, rankingu, trwałości ani ochrony przed duplikatem.

## 1. Cel

Użytkownik znajduje anime, wybiera sezon i odcinki, a potem jednym działaniem **pobiera** je teraz albo **subskrybuje** przyszłe. Pobrane odcinki same przechodzą przez istniejące przetwarzanie (tłumaczenie, lektor) i trafiają do Biblioteki. Subskrypcje działają bez nadzoru, są widoczne w jednej zakładce i same znikają po zakończeniu sezonu.

Dziś pobieranie działa tylko ręcznie i wymaga wyboru grupy wydającej; subskrypcje w praktyce nie działają i nie wiadomo, jak nimi zarządzać (E:5709, E:6997). Ta specyfikacja zastępuje model „tytuł → grupa → wydanie” modelem „tytuł → sezon → odcinek → najlepsze wydanie”.

## 2. Użytkownik i intencja

Jeden użytkownik, Windows, jeden komputer, około 30 odcinków dziennie (A: „Aktualizacja kierunku”). Ogląda anime z polskim lektorem generowanym przez AniShift. Chce jak najmniej klikać i nadzorować.

Wiążące wypowiedzi właściciela z eksportu `session-ses_f3f3.md` (E:linia):

| Kotwica | Treść w skrócie |
| --- | --- |
| E:5535 | Tożsamość odcinka rozstrzyga heurystyka, nie model (Laya odłożona). |
| E:5709, E:6997 | Subskrypcje nie działają i nie widać, jak nimi zarządzać; „subskrypcja ma być drugą stroną monety pobierania”; system projektujemy od nowa. |
| E:8124 | Preferowane 1080p; gdy brak — można zejść niżej lub wyżej. Większy plik to zwykle lepsza jakość, ale to tylko intuicja; ~1,4 GB to przykład, nie reguła. |
| E:8124 | Wyszukiwarka pozwala pobrać albo zasubskrybować tytuł, który aktualnie wychodzi. Zakładka Subskrypcje: obecne subskrypcje + wejście do wyszukiwania. Z subskrypcji też można pobrać odcinki. |
| E:8124 | Subskrypcje usuwają się same po zakończeniu; ręczne usunięcie musi być możliwe i proste. |
| E:8124 | Na liście: tytuł, ile pobrano, czas do emisji następnego odcinka (liczony do emisji, nie do pojawienia się torrenta). |
| E:8124 | Odcinek pobrany → Przetwarzanie → Biblioteka; plik z internetu jest przetwarzany automatycznie tak samo jak plik z folderu. |
| E:8124 | „Jeśli jest język polski w napisach lub audio — definitywnie pobieramy.” Tłumaczenie ważniejsze niż typesetting. |
| E:8124 | Dodawanie subskrypcji proste i intuicyjne; wszystko ma działać szybko. |
| E:9687, E:9712 | Gdy brak PL, warto brać MultiSub i wydania Netflix/Crunchyroll; MultiSub nie zawsze jest oznaczony platformą. |
| E:9640 (asystent, niezakwestionowane) | „Jeśli PL jest tylko niepotwierdzoną flagą, najpierw szukać takiego kandydata w 1080p; nie schodzić do 480p wyłącznie z powodu flagi.” |
| E:9718 (asystent, niezakwestionowane) | Kolejność: właściwy odcinek → wskazówka PL → MultiSub → 1080p; platforma jako informacja. |
| E:6153, E:8100 | Dokumenty i raporty: „samo mięso, bez lania wody”, bez bełkotu. |
| Decyzja 2026-09-23 (odpowiedź na pakiet `final2/`) | „Jakość obrazka wygrywa”; 720p to ostateczność, gdy nie ma 1080p. Polski język nie przeważa nad niższą rozdzielczością. |
| Decyzja 2026-09-23 (odpowiedź na listę weta) | Automat wybiera zwykłe 1080p; 2160p ma być widoczne jako opcja; 720p i niżej nie są pokazywane, gdy istnieje 1080p lub 2160p. Wydania 4K i Blu-ray bywają zbyt ciężkie dla interpolacji klatek w odtwarzaczu właściciela. Usuwanie subskrypcji bez pytania, cofanie Ctrl+Z jak w Bibliotece. Szukanie: co 15 min przez pierwszą dobę, co godzinę przez 2 kolejne, potem raz dziennie; po 7 dniach bez wydania powiadomienie. Dodatki poza subskrypcją, ale mają być widoczne. Fonty z paczki niepotrzebne (właściciel ma własne). Lista MAL niepotrzebna — tytuły właściciel dodaje ręcznie. |
| Decyzja 2026-09-23 (odpowiedź na pakiet `final2/`) | Lektor jest generowany zawsze, także gdy wydanie ma polską ścieżkę dubbingu — dubbing bywa niezadowalający. |

Wcześniejszy roboczy kontrakt produktu A (R-01–R-20, Q-01–Q-04, S-01–S-08) jest odzyskany w `workspace/.archive/acquisition/final2/spec-a-odzyskana.md`. Jego mapowanie na tę specyfikację jest w §16.

## 3. Stan wyjściowy

Fakty potrzebne do zrozumienia zmiany. Źródła: kod na baseline, `research/subscriptions-current-state.md`, `research/planning-code-audit.md`, `research/anime-api-report.md`, raporty w `workspace/.archive/acquisition/reports/`.

### 3.1 Aplikacja dziś

- Zakładka Anime: wyszukanie tytułu w AniList, potem wyniki Nyaa pogrupowane według grup wydających. Użytkownik otwiera grupę, zaznacza wydania, `D` pobiera. Paczki, dubbing i nieznany język są ukrywane; w praktyce obowiązuje minimum 1080p.
- Subskrypcję tworzy się klawiszem `O` na podświetlonym wydaniu w wynikach Anime; wymaga nazwy grupy wydającej, która jest też częścią identyfikatora subskrypcji.
- Zakładka Subskrypcje istnieje jako druga z czterech. Panel startuje na Przetwarzaniu; do Subskrypcji prowadzi tylko ←/→ lub Tab. W terminalu węższym niż ok. 50 kolumn nazwa zakładki znika z nagłówka. Stopka listy: „Space aktywność · Enter odcinki · D dodaj · X usuń · F sprawdź”. `D` przełącza do Anime; `X` usuwa bez potwierdzenia; Enter otwiera wybór numerów, nie szczegóły.
- Istnieje jeden rezydent (`anishift watch`), jeden właściciel zapisu stanu (`AutomationOwner`), prywatny profil qBittorrent, graf przetwarzania, Biblioteka z Koszem i Ctrl+Z, Historia (30 dni, domyślnie 50 pozycji). Panel jest klientem rezydenta przez IPC (ramka do 1 MiB sprawdzana tylko przy odbiorze; przekroczenie zrywa połączenie).
- Pliki stanu: `config/watch/state.json` (WatchState, wersja 2), `config/subscriptions.json` (wersja 4). Użytkownik ma w nim rzeczywiste subskrypcje (m.in. seria dodana 2026-09-06 z listy MAL). Dochodzą `config/watch/decisions.jsonl` (rejestr decyzji automatu, [plan przepływu](plans/e1-przeplyw-subskrypcji.md) §5.6) i `config/watch/cases.jsonl` (lokalna baza zweryfikowanych przypadków, tamże §5.7).
- Dzisiejsze przetwarzanie wymaga napisów tekstowych przy wideo (`selection.py:199–211`). Osadzona ścieżka audio jest zawsze tłem do miksu z lektorem; nie ma drogi „polskie audio zamiast lektora”.
- Parametry subskrypcji są polami `AutomationPolicy` (`control.py:93–108`): opóźnienie po emisji 3 h, sprawdzanie co 1 h, okno 72 h, 3 próby przy błędzie źródła, przerwy 60 s i 300 s, zastój transferu 30 min. Opóźnienie 3 h, okno 72 h i 3 próby przy błędzie źródła zastępują P-1, U-14 i przejście 8 [planu przepływu](plans/e1-przeplyw-subskrypcji.md) (§3.6, §4).

### 3.2 Dlaczego subskrypcje „nie działają” — mechanizmy potwierdzone w kodzie

Konkretnej przyczyny u użytkownika nie ustalono. Potwierdzono mechanizmy, z których każdy daje objaw „nic się nie dzieje”:

1. Globalny problem subskrypcji albo niezakończone potwierdzenie zatrzymuje **cały** harmonogram subskrypcji; panel tego nie pokazuje (`automation.py:1298–1321,3398–3409`).
2. Błąd wyliczenia następnego terminu ustawia go na „brak” bez problemu i bez ponowienia (`automation.py:3410–3417`).
3. Wynik ręcznego „Sprawdź” z problemem jest pokazywany jako „Polecenie przyjęte” (`automation.py:3147–3157`, `state.py:829–863`).
4. Po 72 h bez wydania odcinek kończy się trwale jako brakujący; restart i `F` go nie wznawiają (`subscriptions.py:943–946,1537–1578`).
5. Odcinek przyszły bez indywidualnej daty nie dostaje okna wyszukiwania nawet po starcie sezonu (`subscriptions.py:1518–1534`).
6. Uzupełnianie zaległych odcinków nie pyta o numerację absolutną, którą ręczne wyszukiwanie uwzględnia (`subscriptions.py:1121–1124`).
7. Wydanie musi mieć dokładnie zapisaną grupę; paczki i numery poza sezonem są odrzucane; brak liczników przyczyn odrzucenia (`subscriptions.py:1654–1685`).
8. Lista pokazuje kropkę „włączona”, nie stan monitoringu; zakończony wpis wygląda jak aktywny (`state.py:1256–1263`).

### 3.3 Źródła danych — fakty z badań (2026-09-22)

- **Łańcuch identyfikatorów:** AniList `id` → ani.zip `mappings?anilist_id=<id>` → `mappings.kitsu_id` → Torrentio `stream/series/kitsu:<kitsu_id>:<numer lokalny>.json`. ani.zip działa tylko po ID (tekst → 400, nieznane ID → 404). Torrentio przyjmuje `kitsu:<id>:<n>`, `kitsu:<id>` i IMDb, nie przyjmuje kluczy dodatków `S1`.
- **AniList:** wyszukiwanie tytułów z aliasami, relacje (`PREQUEL`, `SEQUEL`, `SIDE_STORY`, `SPIN_OFF` i relacje do mangi/powieści), status, rok, format, harmonogram emisji z dokładnym czasem. „SEQUEL” nie zawsze wskazuje następny sezon (Slime → OVA). Limit ok. 30 zapytań/min. Czas odpowiedzi 1,32–1,49 s.
- **ani.zip:** lista odcinków z tytułami, numeracją lokalną, sezonową TVDB (77/89) i absolutną (73/89), identyfikatory innych katalogów, liczba zwykłych odcinków i dodatków. Dodatki pod kluczami `S1`, `S2`… to mieszanka recapów, komentarzy, galerii i wywiadów — bez pola rodzaju. OVA serii bywają osobnym wpisem z własnymi ID. Daty `airDate`/`airdate` bywają sprzeczne (1 dzień, 20 dni). Przyszły wpis może mieć pustą listę odcinków. Cache 15 min. Czas 85–201 ms. Brak dokumentacji i SLA.
- **Torrentio:** bez konta i debridu. Każdy kandydat ma `infoHash`; 188/194 mają `fileIdx` i nazwę pliku (tylko nazwa, bez ścieżki); tytuł bywa ucięty (33/194). **Nie zwraca adresu pliku .torrent — tylko hash.** Trackery w polu `sources` ma 120/194. Seedy i rozmiar to tekst w opisie; rozmiar dotyczy pliku, jest zaokrąglony; brak leechers i czasu pomiaru. Języki są deklaracjami z nazwy (flagi), bez podziału audio/napisy. 11 etykiet źródeł poza Nyaa. Cache: niepuste 1 h (do 4 h starszych przy odświeżaniu, 7 dni przy błędzie), puste 60 s. Czas 52–1834 ms. Limit w kodzie usługi: 5000 zapytań/24 h/IP (niepotwierdzony produkcyjnie). Brak SLA; własne uruchomienie kodu nie daje danych.
- **Błędne kandydatury Torrentio:** Slime S1E4 8/47 (spin-off, OAD), Cowboy Bebop E1 22/51 (inne anime, menu, EPUB). Ten sam hash bywa poprawny dla jednego odcinka i błędny dla innego (paczka z wieloma sezonami).
- **Heurystyka tożsamości — tylko prototyp badawczy, w aplikacji nie istnieje; powstaje w E1** (`workspace/.archive/acquisition/evidence/matching/prepare.py.txt`, funkcja `heuristic`). Prototyp na 231 zapisanych rekordach: 159 akceptacji zgodnych z etykietami, 55 nierozstrzygniętych (w tym 20 faktycznie zgodnych), 2 błędnie odrzucone (`slime-s1e4:33`, `bebop-e1:33`), 12,8 ms na całość. Próbka in-sample z trzech franczyz, etykiety i reguły tego samego autora. `workspace/.archive/acquisition/evidence/replay.py` odtwarza wynik offline. **Wymaganie właściciela (2026-09-23): przed użyciem w automacie heurystyka musi być sprawdzona na korpusie co najmniej 2000 tytułów** (N-02).
- **Język:** w 159 kandydatach 20 flag PL (17 przy 1080p), 0 deklaracji polskiego audio, 0 potwierdzeń pełnych polskich dialogów. Przy kolejności „PL przed rozdzielczością” flaga PL przy 720p i 480p wyprzedza 1080p bez flagi (S4E23: pozycje 13 i 14 przed 15; Bebop: 720p na 2 przed 1080p na 3); badanie zostawiło to jako otwarte (`research/polish-1080-selection-validation.md:65–67`). Kolejność zapasowa 720→2160 wobec 2160→720 nie zmieniła pierwszej sugestii (7/7).
- **qBittorrent 5.2.3** (próba syntetyczna z plikiem .torrent, bez magnetu, DHT wyłączone): wybór E1 i E3 z paczki bez E2 działa i przetrwa restart. Priorytet 0 nie gwarantuje zera zapisanych bajtów (wspólne kawałki). `progress=1` pliku nie gwarantuje pliku na dysku. Indeks pliku w qB różni się od surowego indeksu przy plikach paddingu. Po restarcie przez chwilę `checkingResumeData` z postępem 0. 6 s bez seedera nie dowodzi martwego źródła. **Pobierania metadanych przez magnet nie testowano.**

## 4. Ustalenia

Status `właściciel` — wynika z wypowiedzi właściciela. Status `inżynierska` — rozstrzygnięte przez autora pakietu na podstawie dowodów; obowiązuje, dopóki właściciel nie zawetuje (lista do weta: [README.md](README.md) §3).

Przepływ ścieżki ręcznej i subskrypcji (punkt odcięcia, cel, próba, dopuszczalność, limit prób, kontrola po pobraniu H2, rejestr decyzji, parametry P-1..P-10) definiuje zaakceptowany [plan przepływu](plans/e1-przeplyw-subskrypcji.md); wymagania poniżej odwołują się do jego sekcji.

| ID | Ustalenie | Skutek | Status, podstawa |
| --- | --- | --- | --- |
| U-01 | Jedna droga: tytuł → sezon → odcinki → Pobierz albo Subskrybuj. | Stary wybór grupy znika z interfejsu i z kodu. | właściciel, E:6997, E:8124 |
| U-02 | Katalog: AniList (tytuły, relacje, emisja) + ani.zip (odcinki, numeracja, Kitsu ID). Kandydaci: Torrentio. | Nyaa nie jest już wyszukiwarką w UI. Torrentio jest jedynym źródłem kandydatów dla subskrypcji i Pobierz; Nyaa nie jest drugim źródłem świeżych odcinków (pilot historyczny zamiast N-01, [plan przepływu](plans/e1-przeplyw-subskrypcji.md) §5.1). | inżynierska, `research/anime-api-report.md` §13; źródło: właściciel, decyzja 2026-09-28 |
| U-03 | Tożsamość kandydata rozstrzyga heurystyka: `zgodny` / `niezgodny` / `niepewny` + powód. Bez procentów. Ocena dotyczy pary (hash, plik), nie samego hasha. | Automat bierze `zgodny`. Gdy odcinek nie ma `zgodnego`, automat bierze najlepszego `niepewnego` (ta sama kolejność U-04) i oznacza odcinek w Bibliotece jako „niepewne wydanie”. Decyzja właściciela z 2026-09-26: lepiej pobrać za dużo niż nie pobrać, a niechciany plik właściciel pominie. `niezgodny` wyłącznie po jawnym wyborze użytkownika z potwierdzeniem (R-04). W subskrypcji `niepewny` tylko według dopuszczalności planu przepływu §3.3; w ścieżce ręcznej bez zmian. | właściciel E:5535; kształt wyniku inżynierska |
| U-04 | Kolejność zgodnych kandydatów: (1) klasa rozdzielczości (U-05), (2) w tej samej klasie deklaracja PL, (3) deklaracja MultiSub, (4) oznaczenie Netflix/Crunchyroll, (5) więcej seedów, nieznane na końcu, (6) kolejność odpowiedzi źródła. | Jakość obrazu wygrywa: 1080p bez PL wygrywa z 720p z PL. Wśród wydań 1080p pierwsze są polskie, potem MultiSub. Rozmiar, grupa i kodek są tylko informacją. W badaniu 17 z 20 flag PL było przy 1080p, więc polskie wydania zwykle nadal wygrywają. | właściciel, decyzja 2026-09-23; kolejność PL → MultiSub wewnątrz rozdzielczości: E:8124, E:9687, E:9718 |
| U-05 | Klasy rozdzielczości: 1080 (także 1440×1080) → 2160 → 720 → pozostałe znane, bliższe 1080 wyżej → nieznana. | 720p tylko jako ostateczność. Automat bierze 1080p, gdy istnieje; 2160p tylko, gdy nie ma 1080p. | właściciel, decyzja 2026-09-23 |
| U-06 | Kandydat w kontenerze, którego istniejące przetwarzanie nie obsługuje, jest pomijany z powodem „format nieobsługiwany”. | Brak pobrań, których nie da się przetworzyć. | inżynierska; w próbie 5 mp4, 1 ts, 1 avi na 159 |
| U-07 | Rzeczywisty język sprawdzamy po pobraniu (ścieżki w pliku). Deklaracja PL nie pomija tłumaczenia. | Decyduje zawartość, nie nazwa. | inżynierska, `research/polish-1080-selection-validation.md` |
| U-08 | Po pobraniu: lektor powstaje **zawsze**, także przy polskiej ścieżce dubbingu. Pełne polskie napisy → bez tłumaczenia. Tylko obce napisy → tłumaczenie. Brak użytecznych napisów → automatycznie jedno kolejne wydanie z rankingu; po drugiej porażce problem do ręcznego wyboru. Tło lektora wybiera istniejące ustawienie priorytetu języków audio; ta praca go nie zmienia. | Limit dwóch pobrań dotyczy tylko ścieżki ręcznej: nigdy więcej niż dwa pobrania jednego odcinka bez decyzji użytkownika. W subskrypcji obowiązuje limit 3 automatycznych prób na odcinek, potem problem i powiadomienie (plan przepływu §3.3). | właściciel E:8124 (tłumaczenie ważniejsze) i decyzja 2026-09-23 (lektor zawsze); limit dwóch pobrań inżynierska |
| U-09 | Subskrypcja obejmuje **jeden sezon** (jeden wpis katalogu) i jego zwykłe odcinki niewyemitowane w chwili dodania — cele według punktu odcięcia (plan przepływu §3.1). „Od N” jest wyliczane z punktu odcięcia, nie wybierane. | Wyemitowane przed dodaniem pobiera się ścieżką ręczną (§5.3); szkic zaznacza je domyślnie i „Dodaj” zleca je od razu (S-02, 2026-10-04). Nigdy nie przechodzi sama na kolejny sezon. Dodatki nie wchodzą do subskrypcji; pobiera się je jednorazowo. | właściciel E:8124, A:R-10; wyłączenie dodatków inżynierska (§3.3: dane nie odróżniają fabularnych OVA od wywiadów, klucze `S…` nie są odpytywalne w Torrentio) |
| U-10 | Subskrybować można wpis, który ma jeszcze przyszłe odcinki: status „w emisji”, „zapowiedziany” albo „przerwa w emisji”. Wpis zakończony ma tylko Pobierz. | Zapowiedziany sezon można dodać przed premierą. | właściciel E:8124 („aktualnie wychodzi”), A:R-03 (także przed startem sezonu) |
| U-11 | Subskrypcja kończy się sama, gdy AniList oznaczył wpis jako zakończony, liczba odcinków jest znana i każdy cel (plan przepływu §3.1) jest spełniony. Cel `wyczerpany` blokuje samozakończenie. | Znika z listy. Koniec emisji bez pobrania nie jest sukcesem. Nie czeka na koniec lektora. | właściciel E:8124; warunek inżynierska |
| U-12 | Ręczne Usuń kończy tylko monitoring. | Pobrane pliki, trwające pobrania i przetwarzanie zostają. | właściciel E:8124; skutki inżynierska |
| U-13 | Czas emisji pochodzi z AniList (`airingSchedule`). ani.zip służy do numeracji i tytułów. Odliczanie liczy czas do emisji; po emisji „Czeka na wydanie”. | Jedno źródło czasu; sprzeczne daty ani.zip nie sterują monitoringiem. | właściciel E:8124 (odliczanie do emisji); źródło inżynierska (§3.3) |
| U-14 | Szukanie po emisji: co 15 min przez pierwszą dobę, co godzinę do końca 3. doby, potem raz na dobę, aż do znalezienia, usunięcia albo zakończenia subskrypcji. Brak twardego końca szukania. Po 7 dobach bez zgodnego wydania: powiadomienie w zasobniku systemowym (istniejące `tray.notify`) i problem „Nie znaleziono E6 od 7 dni” na liście; szukanie trwa dalej raz na dobę. Harmonogram startuje od `t_due + T_start` (P-1), rzednie według P-10, a cel `wyczerpany` nie jest szukany (plan przepływu §3.1, §4). | Spóźnione wydanie zostanie znalezione bez ręcznego „ponów”. Szukanie odcinka kończy się w chwili znalezienia, więc typowe obciążenie jest małe. Najgorszy przypadek (30 odcinków/dzień, żaden nieznaleziony): 30 × 96 + 60 × 24 ≈ 4320 zapytań/dobę — blisko niepotwierdzonego limitu 5000/dobę/IP. Typowe opóźnienie i odpowiedzi 429 pokazuje rejestr decyzji po integracji (plan przepływu §5.1); przy zagrożeniu limitu E3 rzednie interwał 15 min (P-10). | właściciel, decyzja 2026-09-23; A:R-14; likwiduje mechanizm §3.2 pkt 4 |
| U-15 | Odcinek zakresu bez daty emisji jest szukany, gdy wpis jest „w emisji” lub „zakończony” i jego numer jest ≤ liczbie już wyemitowanych odcinków według AniList. Jego termin `t_due` to pierwsza obserwacja spełnienia tego warunku (plan przepływu §3.1). | Likwiduje mechanizm §3.2 pkt 5. | inżynierska |
| U-16 | Zlecony odcinek nie jest zlecany drugi raz: ani przez drugie Pobierz, ani przez subskrypcję, ani po restarcie, usunięciu pliku czy wygaśnięciu Historii. Ponowne pobranie tylko jawnym „Pobierz ponownie”. | Pamięć zleceń jest trwała i niezależna od Historii i subskrypcji. | A:R-13; kontrakt L:R-014/R-028 |
| U-17 | Z paczki pobieramy tylko pliki zamówionych odcinków i ich pliki towarzyszące o tej samej nazwie (napisy, audio). Fonty i reszta paczki nie są pobierane. | Mniejszy transfer. Typesetting może gorzej się wyświetlać — zgodnie z priorytetem tłumaczenia. | właściciel E:8124; reguła inżynierska |
| U-18 | Plik w paczce wskazujemy tak: `fileIdx` z Torrentio jest podpowiedzią; decyduje lista plików z qBittorrenta: (a) plik o tej samej, unikalnej nazwie; (b) inaczej heurystyka tożsamości na pełnych ścieżkach listy; (c) inaczej odcinek czeka na wybór użytkownika. | Nigdy „największy plik” ani samo `fileIdx`. | inżynierska (§3.3: padding, tylko nazwa pliku, kolizje nazw) |
| U-19 | Nowe pobrania trafiają płasko do roota workspace i są przetwarzane istniejącym Auto; wynik w Bibliotece. Plik próby automatycznej subskrypcji wchodzi do Auto tylko przy trwałym wyniku próby `przyjęta` (plan przepływu §3.4). | Bez nowych folderów serii. | kontrakt L:R-029 |
| U-20 | Istniejące subskrypcje użytkownika są przenoszone automatycznie przy pierwszym starcie nowej wersji (§5.6). | Nic nie ginie; nic nie jest pobierane masowo bez ruchu użytkownika. | inżynierska |
| U-21 | Filmy: widoczne w powiązaniach. Pobierz dla filmu tylko, jeśli pomiar E1 potwierdzi kandydatów Torrentio dla filmów (N-04). | Brak obietnicy bez dowodu. | inżynierska |
| U-22 | Kitsu ID sezonu jest zapisywane w subskrypcji przy jej dodaniu. | Awaria ani.zip blokuje tylko nowe tytuły, nie działające subskrypcje. | inżynierska (§3.3) |
| U-24 | „Inne wydania” pokazuje 1080p, 2160p i wydania o nieznanej rozdzielczości. Wydania 720p i niższe są ukryte, jeśli istnieje choć jedno zgodne 1080p lub 2160p; gdy nie ma żadnego — pokazywane są wszystkie. | Właściciel widzi 4K jako opcję, nie widzi zbędnych małych wydań. | właściciel, decyzja 2026-09-23 |
| U-25 | Kodek (H.264, HEVC, AV1) i pochodzenie wydania (WEB, Blu-ray) nie wpływają na wybór; są tylko informacją w „Inne wydania”. | Ranking bez dodatkowego kryterium. | właściciel, decyzja 2026-09-23 („nie ma znaczenia”) |
| U-23 | Wydanie oznaczone jako dubbing bez „Dual Audio”/„Multi Audio” (także polski dubbing bez oryginalnej ścieżki) jest ustawiane za wszystkimi innymi zgodnymi kandydatami. | Lektor nie ląduje na samym dubbingu zamiast oryginalnego audio; wydanie zostaje w „Inne wydania”. | inżynierska; dziś dubbing jest ukrywany w całości (`acquisition.py:740–747`) |

## 5. Wymagania funkcjonalne

### 5.1 Wyszukiwanie i katalog

- **W-01** Zakładka Anime ma jedno pole wyszukiwania. Pierwszy znak lub wklejenie na nieaktywnym ekranie zapytania rozpoczyna edycję i zachowuje tekst; Enter i `/` nadal aktywują pole. Szukanie uwzględnia nazwy angielskie, romaji i synonimy.
- **W-02** Lista tytułów pokazuje: rok premiery tego wpisu, tytuł (angielski, gdy istnieje, inaczej romaji), format. Nie pokazuje liczby odcinków ani wydań.
- **W-03** Lista tytułów jest posortowana: zapowiedzi bez daty premiery na górze, potem pełna data premiery AniList malejąco (sam rok liczy się jak koniec roku), remis alfabetycznie (naturalnie). Wpisy franczyzy w grupie: bez daty na górze, potem data rosnąco. Decyzja właściciela 2026-09-29 (H1).
- **W-04** Wybór tytułu pokazuje powiązane wpisy anime tej franczyzy w trzech grupach: „Sezony i części” (TV, TV short, ONA połączone relacją poprzednik/następca), „Dodatki” (OVA, special), „Filmy i inne” (film, spin-off, historia poboczna). Każdy wpis: rok, nazwa, format, status emisji. Kolejność w grupie: data premiery. Jedyna grupa nie ma nagłówka, niepełna lista mówi „Lista niepełna”. Dokładnie jeden wynik i jeden wpis kompletnej franczyzy bez dodatków przechodzi od razu do odcinków, Esc wraca do zapytania; wiele wpisów, dodatki (także ani.zip) i lista niepełna nie są pomijane. `G grupy` w stopce tylko dla wpisu dostępnego w starej drodze.
- **W-05** Relacje do mangi i powieści nie są pokazywane. „Zakończony” dotyczy tylko danego wpisu, nie franczyzy.
- **W-06** Wybór wpisu pokazuje listę jego odcinków: numer, tytuł, data emisji (czas lokalny), stan (§5.5). Źródło zastępczej daty nie zajmuje kolumny: szczegół bieżącego odcinka mówi „termin emisji niepotwierdzony (ani.zip)”. Awaria harmonogramu to jeden komunikat „Brak terminów emisji (AniList) · ponów za N s”, po ochłodzeniu instrukcja powrotu i ponownego wejścia, bez nowego klawisza. Dodatki `S…` z ani.zip są pokazane pod nagłówkiem „Dodatki” jako informacja, bez akcji pobrania. OVA mające własny wpis pobiera się z ich wpisu.
- **W-07** Przyszły odcinek bez obiektu w ani.zip jest pokazany, gdy AniList zna jego numer (z harmonogramu lub liczby odcinków).
- **W-08** Gdy AniList lub ani.zip nie odpowiada, widok mówi, które źródło zawiodło i kiedy można spróbować ponownie. Nie pokazuje „0 odcinków” i nie przełącza się na surowe wyszukiwanie Nyaa z powodu awarii. Gdy poprawnie zakończone wyszukiwanie AniList nie znalazło tytułu, pokazuje komunikat „Brak tytułu w AniList, szukam wydań na Nyaa” i przechodzi do wyszukiwania wpisanego hasła na Nyaa (stara lista wydań); wynik zachowuje informację o tym przejściu. Decyzja właściciela 2026-09-24.

### 5.2 Wybór wydania

- **R-01** Dla każdego wybranego odcinka aplikacja pyta Torrentio o kandydatów i ocenia każdego heurystyką tożsamości (U-03).
- **R-02** Kandydaci `zgodni` są ułożeni według U-04, U-05, U-06 i U-23. Pierwszy jest sugestią.
- **R-03** `I` z listy odcinków pokazuje wydania podświetlonego odcinka i oznaczoną sugestię. W tabeli: wydanie, obraz, deklarowany język (PL / MultiSub / inne) i seedy, widoczne także przy 50 kolumnach. Pod kursorem: nazwa pliku, przybliżony rozmiar, źródło NF/CR tylko gdy podane oraz krótki faktyczny powód, bez powtarzania pól tabeli. Bez indeksu pliku i pustych etykiet. Space/Enter wybiera jedno wydanie; `D` pobiera zaznaczone, a bez zaznaczenia — podświetlone, z potwierdzeniami R-04. Zwykłe `D` na liście odcinków nie wymaga podglądu; `P` otwiera tę samą listę alternatyw przed jawnym `D pobierz ponownie` (P-05), bez osobnego U04. Podstawa D/I/zaznaczeń: decyzja właściciela 2026-09-29; uproszczenie prezentacji i P: decyzja orkiestratora 2026-09-29, do potwierdzenia.
- **R-04** „Inne wydania” pokazuje wszystkich kandydatów odcinka z oceną tożsamości i powodem. Użytkownik może wybrać innego `zgodnego` bez pytania, `niepewnego` po potwierdzeniu „To wydanie może nie być tym odcinkiem”, a `niezgodnego` po potwierdzeniu z powodem heurystyki („Heurystyka uznała to za inny materiał: …”). Automat nigdy nie wybiera `niezgodnego`; `niepewnego` bierze tylko wtedy, gdy nie ma `zgodnego` (U-03). Ręczny wybór `niezgodnego` istnieje, bo prototyp heurystyki z badania błędnie odrzucił 2 zgodne wydania na 231.
- Prezentacja R-04: bez osobnej kolumny Tożsamość; w wierszach tekstowe wyjątki „niepewne”/„niezgodne”, pełny werdykt i krótki powód pod kursorem. `? szczegóły` pokazuje pełny powód heurystyki. R-04 przed skutkiem obowiązuje również po P, niezależnie od zgody na ponowienie.
- **R-05** Brak seedów lub rozmiaru pokazuje „?”, nie zero. Zero seedów nie wyklucza kandydata.
- **R-06** Brak zgodnego kandydata, ale jest `niepewny`: sugestią jest najlepszy `niepewny` z oznaczeniem „niepewne · …” i szczegółem „niepewny: <powód>” w U04/U04b. To niepewność tożsamości wskazanego odcinka; pobrany plik ma w Bibliotece oznaczenie „niepewne”. Brak `zgodnego` i `niepewnego`: „Brak pasującego wydania E6”, przy pustym źródle „Brak wydań w źródle”. Czas sprawdzenia i liczba niezgodnych w szczególe poniżej; pobranie bez sugestii wymaga ręcznego wyboru z „Inne wydania”.
- **R-07** Ta sama reguła wyboru obowiązuje dla Pobierz, subskrypcji i zamiany wydania po nieudanej kontroli zawartości (U-08): ta sama heurystyka i ranking. Dopuszczalność kandydata w subskrypcji określa plan przepływu §3.3.
- **R-08** Pusta odpowiedź Torrentio znaczy „brak kandydatów w źródle”, nie „odcinek nie wyszedł”.

### 5.3 Pobieranie jednorazowe

- **P-01** Na liście odcinków: Spacja/Enter zaznacza odcinek, `A` przełącza wszystkie/żadne spośród wyemitowanych zwykłych odcinków uprawnionych do zwykłego pobrania, `Z` pozwala wpisać listę i zakresy (`1,3,9-12`) albo „od N” (`5-`). Zaznaczenie 1 i 3 nie zamawia 2. Numery są całkowite — tak numerują odcinki ani.zip i harmonogram AniList; odcinki „.5” występują jako dodatki `S…` albo osobne wpisy.
- Prezentacja P-01: „Zaznaczone (n): …” łączy ciągłe numery, np. „Zaznaczone (4): 1–3, 7”; pusta linia znika. Jeden Esc zamyka zakres bez zastosowania, Ctrl+C z zaznaczonym tekstem nadal kopiuje. Limit partii dopiero przy przekroczeniu: „Limit: 100 odcinków · Z zmień zakres”, bez cichego obcinania ani dzielenia partii.
- **P-02** `D` dobiera i zleca sugestie zaznaczonych odcinków, a bez zaznaczeń — podświetlonego, bez osobnego podglądu i drugiego Enter. Odcinki bez sugestii lub z błędem źródła są wypisane jako niezlecone z powodem; nie blokują zlecenia reszty. Sugestia `niepewna` jest dopuszczona według U-03/R-06. Decyzja właściciela 2026-09-29.
- **P-03** Po zleceniu widok przechodzi do Przetwarzania i pokazuje zlecone odcinki (o ile użytkownik nie opuścił ekranu w trakcie).
- **P-04** Zlecenie jest trwałe: przetrwa zamknięcie panelu, restart rezydenta i komputera.
- Rozliczenie partii P-04: przyjęte odcinki są trwałe; po restarcie niedokończona reszta wymaga nowego świadomego D (plan E2 §8.7). UI informuje dopiero po faktycznym przerwaniu: „Nie zlecono E4–E8 · zaznacz je ponownie”, z rzeczywistymi numerami, bez stałej notki przy zwykłym D.
- **P-05** Odcinek zlecony, pobrany lub gotowy ma na liście swój stan i nie da się go zaznaczyć do zwykłego Pobierz. `P` („Pobierz ponownie”, E2) otwiera bezpośrednio listę alternatyw U04b z oznaczoną sugestią i ostrzeżeniem „Obecne pliki zostają”; dla konfliktu legacy „E… może być już zlecony · Obecne pliki zostają”. Zgodą jest `D pobierz ponownie` na tej liście, bez wcześniejszego pytania i osobnego U04. Zastępowane wydanie jest wyłączone; R-04 osobno chroni jawny niepewny/niezgodny wybór. Zgoda legacy dotyczy pokazanych danych, zmiana konfliktu ją unieważnia. Przyjęte wydanie `niepewne` zamienia się tylko w ten sposób, nigdy automatycznie (plan przepływu W-g). Ręczne zlecenie w trakcie subskrypcji rezerwuje jej cel (plan przepływu §3.6 przejścia 17–19). Powód quality/wrong_episode jest nieobowiązkowy, bez zgadywania motywacji.
- **P-06** Kilka odcinków z tej samej paczki to jeden transfer w qBittorrencie. Dołożenie odcinka do pobieranej paczki dopisuje jego pliki do tego transferu.
- **P-07** Odcinek przechodzi do przetwarzania, gdy wszystkie jego pliki są kompletne na dysku (qBittorrent zgłasza 100% i plik istnieje z oczekiwanym rozmiarem), niezależnie od pozostałych plików paczki. Próba subskrypcji przechodzi przed tłumaczeniem/TTS kontrolę po pobraniu H2, o ile H2 zostaje (plan przepływu §3.3 bramka przyjęcia, §5.4). Awaria włączonej H2 kończy tylko H2 wynikiem „niewykonana” (widocznym i zapisanym w rejestrze); przyjęcie nadal wymaga U-07/U-08 (bramka przyjęcia, plan przepływu §3.3, §3.6 przejścia 14–15).
- **P-08** Pliki paczki, których nikt nie zamówił, a które qBittorrent zapisał przez wspólne kawałki, nie są przetwarzane automatycznie.

### 5.4 Subskrypcje

- **S-01** Na liście odcinków wpisu spełniającego U-10 `S` w E3 otwiera szkic subskrypcji: tytuł, sezon, co zostanie pobrane później, data następnej emisji oraz wyemitowane odcinki zaznaczone do pobrania od razu (S-02). Szkic nie pokazuje „od odcinka N” (decyzja właściciela 2026-10-04: subskrybuje się cały tytuł; punkt odcięcia U-09 zostaje wewnętrzną regułą). Enter na „Dodaj subskrypcję” zapisuje. Do E3 `S` nie jest w stopce; naciśnięcie pokazuje „Subskrypcje: użyj G grupy”, gdy pominięto U02 i G działa z odcinków; inaczej „Subskrypcje: wróć do tytułów lub wpisów i użyj G”. Stare `O` pod `G` pozostaje dostępne. Decyzja właściciela 2026-09-29; ukrycie niedostępnej akcji i G z odcinków: decyzja orkiestratora 2026-09-29, do potwierdzenia.
- **S-02** (decyzja właściciela 2026-10-04, zastępuje usunięcie z planu przepływu §7) Szkic subskrypcji (S-01) pokazuje wyemitowane odcinki sezonu, które nie są jeszcze zamówione ani pobrane, i domyślnie je **zaznacza**; użytkownik może je odznaczyć (Space). „Dodaj subskrypcję” zapisuje subskrypcję i w tym samym kroku zleca zaznaczone odcinki zwykłą ścieżką ręczną `D` (P-02, §5.3), jak gdyby użytkownik nacisnął D na liście odcinków. Subskrypcja nadal obejmuje jako cele tylko odcinki niewyemitowane w chwili dodania (U-09, W-b); wyemitowane idą ścieżką ręczną (W-a) i pokazują się w Przetwarzaniu jak po D. Odmowa zlecenia odcinka nie cofa dodania subskrypcji; powód jest widoczny jak przy D. Cele subskrypcji są szukane po emisji (U-14, U-15).
- **S-03** Zakładka Subskrypcje pokazuje wszystkie aktywne subskrypcje w kolejności: najpierw wpisy z problemem, potem według najbliższej emisji, wpisy bez terminu i wstrzymane na końcu; remis alfabetycznie. Kolejność zmienia się tylko po emisji odcinka albo zmianie stanu, nie co sekundę. Kolumny (decyzja właściciela 2026-10-04): `Tytuł · Odcinki · Gotowe · Stan`. `Odcinki x/y`: x = odcinki tego sezonu pobrane przez AniShift (subskrypcją albo ręcznie) i nadal obecne na dysku, wyróżnione kolorem sukcesu, gdy x > 0; y = liczba odcinków sezonu według katalogu albo `?`. Niczego nie zakłada się z góry — odcinek, którego nie ma na dysku, się nie liczy. `Gotowe z` = odcinki przerobione z lektorem. Lista nie pokazuje zakresu („od N”, „E2–E12”) ani osobnego „Pobrano”. Stan to jedno z: odliczanie do emisji następnego odcinka, „Czeka na wydanie E6 (od 2 dni)”, „Kontrola E6”, „Termin nieznany”, „Przerwa w emisji”, „Wstrzymana”, opis problemu (np. „E6: wyczerpano próby (3 z 3)”).
- **S-04** Subskrypcję dodaje klawisz `D` na liście, widoczny w stopce klawiszy; nad listą nie ma wiersza „Dodaj”. Pusta lista mówi „Brak subskrypcji · D dodaj pierwszą”. `D` otwiera wyszukiwarkę Anime przy podświetlonej zakładce Subskrypcje; Esc wraca do listy; po dodaniu widok wraca do listy z nowym wpisem podświetlonym. Decyzja właściciela 2026-10-04.
- **S-05** Enter na subskrypcji otwiera szczegóły: odcinki zakresu z ich stanami, wynik ostatniego sprawdzenia, lista dodatków tego sezonu (klucze `S…` z ani.zip) i powiązanych wpisów OVA/special z AniList — tylko informacja, z przejściem do wpisu OVA, gdzie można go pobrać — oraz akcje: Pobierz zaznaczone, Wstrzymaj/Wznów, Szukaj teraz, Usuń.
- **S-06** „Szukaj teraz” wykonuje jedno sprawdzenie tej subskrypcji i pokazuje wynik: „Sprawdzono: E6 — 12 kandydatów, 0 zgodnych (8 niepewnych, 4 niezgodnych)” albo „Zlecono E6”.
- **S-07** Wstrzymaj zatrzymuje nowe zlecenia tej subskrypcji. Trwające pobrania i przetwarzanie trwają.
- **S-08** Delete usuwa subskrypcję od razu, bez pytania, i kończy monitoring (U-12). Ctrl+Z na liście subskrypcji przywraca ostatnio usuniętą subskrypcję z jej zakresem i stanem, także po restarcie — tak jak Kosz w Bibliotece.
- **S-09** Zakończona subskrypcja (U-11) znika z listy; w Historii pojawia się wpis „Subskrypcja zakończona: tytuł, sezon”, bez licznika (decyzja orkiestratora 2026-10-04: licznik w chwili zamknięcia wyprzedzałby inspekcję dysku; stan odcinków pokazuje Biblioteka).
- **S-10** Usunięte (plan przepływu §7): subskrypcja nie ma „Zmień od N”; zakres wynika z punktu odcięcia (U-09).
- **S-11** Globalna pauza Auto wstrzymuje nowe zlecenia wszystkich subskrypcji i zatrzymuje trwające transfery automatu, także próby subskrypcji, tak jak pauza E2 (transfer w fazie metadanych nie jest zatrzymywany); wznowienie je kontynuuje. Czas pauzy nie liczy się do limitów zastoju ani metadanych, a czas naliczony przed pauzą zostaje. Lista pokazuje pauzę w stałym wierszu nad wpisami. (decyzja orkiestratora 2026-10-02, potwierdzone przez właściciela 2026-10-02)
- **S-12** Problem jednej subskrypcji nie zatrzymuje pozostałych. Błąd całego monitoringu (np. zapis stanu) jest widoczny w stałym wierszu nad listą z przyczyną; monitoring ponawia próbę po czasie z ustawień i wraca sam, gdy przyczyna ustąpi.
- **S-14** Po 7 dobach bez zgodnego wydania odcinka subskrypcji rezydent wysyła jedno powiadomienie w zasobniku systemowym („Nie znaleziono Slime S4 E6 od 7 dni”), a lista pokazuje ten problem przy wpisie (U-14).
- **S-13** Każde sprawdzenie zapisuje w logu: subskrypcję, odcinek, liczby kandydatów według oceny tożsamości, decyzję (zlecono / brak / błąd źródła) — bez payloadów. Treść decyzji (kandydaci, oceny, wybór) trafia do rejestru decyzji (plan przepływu §5.6), nie do logu.
- **S-15** Aplikacja ma przełącznik trybu cienia: subskrypcje przechodzą maszynę stanów, ale zamiast próby zapisują propozycję w rejestrze decyzji, bez qBittorrenta i plików (plan przepływu §5.5). Przełącznik jest opcjonalny i nie jest bramką uruchomienia automatu.

### 5.5 Stany odcinka

Jeden odcinek ma w każdym widoku ten sam stan, wyliczany z trwałych danych rezydenta:

| Stan | Znaczenie |
| --- | --- |
| Nie zamówiono | Brak zlecenia; odcinek wyemitowany. |
| Nie wyemitowano | Brak zlecenia i subskrypcji; emisja w przyszłości albo nieznana. |
| Czeka na emisję | Objęty subskrypcją, emisja w przyszłości. |
| Czeka na wydanie | Po emisji, brak zgodnego kandydata. |
| Zlecono | Zlecenie zapisane; transfer jeszcze nie ruszył albo trwa pobieranie listy plików. |
| może być zlecony | Możliwy konflikt legacy, nie dowód przyjęcia. Zwykłe D/A/Z zablokowane; P wymaga obejrzenia konfliktu i jawnego D pobierz ponownie (plan E2 §8.3/§8.6). |
| Pobieranie | Transfer trwa; procent z qBittorrenta. |
| Pobrano | Pliki odcinka kompletne na dysku. |
| Kontrola | Próba subskrypcji: pliki kompletne, trwa kontrola po pobraniu (H2, U-07/U-08) — „Kontrola E6”. |
| Przetwarzanie | Przyjęty do grafu przetwarzania. |
| Gotowe | Produkty opublikowane w Bibliotece. |
| Problem | Konkretny powód, np. „Brak napisów w dwóch wydaniach”, „Nie ustalono pliku w paczce”, „E6: wyczerpano próby (3 z 3)”. |

„Kontrola niewykonana” to oznaczenie przyjętego odcinka po awarii H2 (P-07), nie osobny stan.

### 5.6 Przeniesienie istniejących subskrypcji

- **M-01** Aktywna stara subskrypcja z identyfikatorem AniList i numerem startu staje się subskrypcją tego wpisu z zachowanym stanem włączona/wyłączona; punkt odcięcia i cele według planu przepływu §3.2 (`t_sub` = data utworzenia starej subskrypcji). Gdy ma należne, niespełnione cele sprzed migracji, startuje jako **wstrzymana** i pobiera je dopiero po „Wznów” (U-20). Przypadki nierozstrzygalne zostają w ścieżce ręcznej z notką w szczegółach.
- **M-02** Odcinki oznaczone w starej subskrypcji jako przekazane (taken) są traktowane jako zlecone (U-16) i nie są pobierane ponownie.
- **M-03** Stara subskrypcja zakończona przez kalendarz, która ma niepobrane odcinki zakresu, staje się subskrypcją **wstrzymaną** z opisem „Zakończona przez starą wersję; brakuje E5–E8 · Wznów, aby pobrać”. Po „Wznów” automatycznie pobierane są tylko braki będące celami (plan przepływu §3.2, W-f).
- **M-04** Stara subskrypcja zakończona z kompletem pobrań nie pojawia się na liście.
- **M-05** Stara subskrypcja bez rozpoznawalnego wpisu AniList pojawia się z problemem „Nie rozpoznano sezonu — usuń i dodaj ponownie”.
- **M-06** Trwające stare pobrania kończą się i są przetwarzane tak jak dotąd: cel przetwarzania według ustawień z chwili przekazania do przetwarzania (tak działa obecna wersja).
- **M-07** Przed pierwszym zapisem w nowym formacie powstaje kopia obu plików stanu obok oryginałów.

### 5.7 Przetwarzanie, Biblioteka, Historia

- **B-01** Przetwarzanie pokazuje pobierane i przetwarzane odcinki istniejącymi paskami. Odcinek czekający na listę plików ma wiersz „Pobieranie listy plików”, bez procentu.
- **B-02** Pobrano i Gotowe są liczone osobno; odcinek może być jednocześnie pobrany i w przetwarzaniu.
- **B-03** Biblioteka, Kosz, Ctrl+Z, Historia i Ręczny działają jak dotąd (§13).

## 6. Wymagania jakościowe

- **Q-01** Renderowanie panelu nigdy nie wykonuje sieci ani zapisu. Każdy odczyt sieciowy działa w tle z widocznym stanem; Esc i Tab działają w trakcie.
- **Q-02** Wyszukanie tytułu: jedno zapytanie AniList (plus istniejąca jedna ponowna próba ze skróconym hasłem, gdy nic nie znaleziono). Wejście w tytuł: zapytania o relacje warstwami łańcucha sezonów — dla franczyzy Slime najwyżej 4. Wejście we wpis: jedno ani.zip i harmonogram AniList (strony po 25 odcinków); przy automatycznym pominięciu pojedynczego wpisu W-04 odczyt następuje już w ramach wyszukania, także dla sprawdzenia dodatków. Podgląd pobrania: jedno Torrentio na odcinek. Innych zapytań brak bez akcji użytkownika albo harmonogramu subskrypcji.
- **Q-03** Odpowiedź ani.zip wpisu i franczyza są ponownie używane przez czas z nagłówka `Cache-Control` ani.zip (brak nagłówka → zmierzone 15 min). Stany odcinków liczone są przy każdym odczycie. Odpowiedzi Torrentio nie są buforowane przez AniShift (usługa sama buforuje do 1 h).
- **Q-04** Zapytania Torrentio i ani.zip nie mają sztucznego odstępu; limity i ochłodzenie po 429 obsługuje istniejący `RequestControl` pod własnymi nazwami dostawców.
- **Q-05** Czasy etapów (tytuł → wpisy → odcinki → sugestia → zlecenie → metadane torrenta → start transferu → gotowy plik) są mierzone w E1–E2 i zapisywane w wynikach etapów. Nie ma wymyślonego progu; każde widoczne czekanie ma stan i można je przerwać.
- **Q-06** Komunikaty błędów są krótkie, po polsku, bez sekretów, pełnych URL-i i ścieżek absolutnych.
- **Q-07** Logowanie zgodnie z `AGENTS.md`: granice operacji, retry, błędy; bez payloadów, tytułów plików z dysku i ścieżek absolutnych.
- **Q-08** Rozmiar każdej odpowiedzi IPC jest ograniczony: widoki niosą aktywne zlecenia i ostatnie pozycje Historii, a listy odcinków subskrypcji są wysyłane tylko w szczegółach. Rezydent odmawia wysłania ramki powyżej limitu z jawnym błędem zamiast zrywać połączenie.

## 7. Inwarianty

- **I-01** Stan trwały zapisuje wyłącznie `AutomationOwner`. Panel wysyła polecenia i czyta widoki.
- **I-02** Zaznaczenie ≠ zlecenie ≠ pobrano ≠ gotowe. Żaden widok nie wyprowadza jednego z drugiego.
- **I-03** Odcinek zlecony nie jest zlecany ponownie bez jawnego „Pobierz ponownie” (U-16).
- **I-04** AniShift zmienia wyłącznie własne torrenty w prywatnym profilu qBittorrent. Usunięcie subskrypcji, zlecenia ani torrentu nie usuwa danych z dysku.
- **I-05** Nawigacja, odliczanie, render, restart i wygaśnięcie Historii nie tworzą zleceń.
- **I-06** Ten sam fizyczny odcinek z dwóch wejść (subskrypcja i Pobierz, dwa panele) daje jedno zlecenie i jeden przebieg przetwarzania.
- **I-07** Niezamówiony plik z paczki nie uruchamia automatycznego przetwarzania, także po restarcie.
- **I-08** Każda decyzja automatu (wybór wydania, zamiana wydania, pominięcie) ma zapisany powód widoczny w szczegółach odcinka. Powód trzyma właściciel zlecenia (`AutomationOwner`); rejestr decyzji jest kopią dowodową do przeglądu (plan przepływu §5.6).

## 8. Ograniczenia

- Windows jest jedyną platformą uruchomieniową. CI uruchamia pytest i smoke aplikacji tylko na Windows; lint i mypy na Ubuntu, z mypy także dla targetu Windows, zgodnie z `AGENTS.md` i `.github/workflows/ci.yml`. Nie ma testów runtime aplikacji na Linuksie.
- Python 3.14, istniejące zależności (`httpx`, `prompt_toolkit`, `rich`, `pydantic`). Nowa zależność tylko przez `uv add` i tylko po zgodzie właściciela.
- qBittorrent 5.x w prywatnym profilu AniShift, Web API.
- Pomiary E1 (N-02, N-04) i pilot historyczny zastępujący N-01 (plan przepływu §5.1) działają lokalnie na Windows właściciela, bo Torrentio blokuje VPS (HTTP 403). Próba N-03 działa lokalnie na Windows, bo dotyczy binarki qBittorrent używanej przez AniShift.
- Usługi zewnętrzne bez konta: AniList GraphQL, ani.zip `https://api.ani.zip/mappings?anilist_id=<id>`, Torrentio `https://torrentio.strem.fun/stream/series/kitsu:<id>:<n>.json`. Brak SLA; awaria usługi daje widoczny stan, nie obejście.
- Rozwiązanie korzysta z istniejącego rezydenta, IPC, grafu przetwarzania, Biblioteki i Historii. Nie powstaje drugi właściciel stanu, drugi scheduler, druga baza ani drugi rejestr zleceń. Katalog i Torrentio to zwykłe moduły, bez rejestru silników.

## 9. Zakazane

- Sonarr, Prowlarr i inne zewnętrzne menedżery pobierania.
- Model językowy lub ML do tożsamości odcinka (Laya).
- Szerokie wyszukiwanie tekstowe Nyaa jako cichy zamiennik niedostępnego źródła.
- Automatyczne przejście subskrypcji na kolejny sezon.
- Automatyczne pobieranie dodatków w ramach subskrypcji.
- Pobieranie całej paczki, gdy zamówiono jej część.
- Usuwanie plików użytkownika przy usuwaniu subskrypcji lub zlecenia.
- Dotykanie osobistego qBittorrenta użytkownika i torrentów spoza profilu AniShift.
- Wybór wydania na podstawie samego rozmiaru, liczby seedów albo nazwy grupy.

## 10. Zakres i poza zakresem

**W zakresie:** W-01–W-08, R-01–R-08, P-01–P-08, S-01–S-15 (bez usuniętego S-10; S-02 przywrócone 2026-10-04), stany §5.5, M-01–M-07, B-01–B-02, Q-01–Q-08, kontrola zawartości U-07/U-08, usunięcie starego wyboru grup, aktualizacja `AGENTS.md` i `README.md` w zmienianych obszarach.

**Poza zakresem:** synchronizacja z MAL/AniList, śledzenie obejrzanych odcinków, automatyczny typesetting, łączenie napisów z kilku wydań, zewnętrzne serwisy napisów, AnimeSchedule, powiadomienia (Discord itp.), odtwarzacz, nowe funkcje Ręcznego, nowe formaty tekstowe, zmiany TTS i tłumaczenia.

## 11. Odłożone

| Temat | Powód | Warunek powrotu |
| --- | --- | --- |
| Pobierz dla filmów | Endpoint filmowy Torrentio nie był badany | Pozytywny wynik N-04 w E1 |
| Automatyczne dodatki w subskrypcji | Dane nie odróżniają fabularnych OVA od wywiadów i galerii | Wiarygodne źródło rodzaju dodatku |
| Osobny plik audio PL obok wideo | Rzadkie, brak obserwacji | Zgłoszony przypadek |
| Nyaa jako drugie źródło świeżych odcinków | Decyzja 2026-09-28: nie jest potrzebne — Torrentio ma zgodne wydania dla wszystkich odcinków pilota (U-02, plan przepływu §5.1) | Rejestr decyzji pokaże odcinki bez wydania w Torrentio |
| Wyszukiwanie innych treści niż anime | Zgłoszone przez właściciela jako możliwe w przyszłości; poza tą pracą | Osobne zamówienie |
| AnimeSchedule (przesunięcia emisji) | Wymaga tokenu i atrybucji; AniList wystarcza | Zgłoszony problem z datami AniList |
| Biblioteka jako widok tytułów (pomysł właściciela 2026-10-01) | Poza zakresem E2; zależy od subskrypcji E3 | Etap E6 w masterplanie i osobny plan zaakceptowany przez właściciela |

## 12. Odrzucone

| Droga | Powód |
| --- | --- |
| Sonarr jako silnik | Decyzja właściciela; dublowałby właściciela stanu (`workspace/.archive/acquisition/report.md`) |
| Laya / model do tożsamości | Brak przewagi nad heurystyką; decyzja E:5535 |
| Wybór grupy wydającej przez użytkownika | Właściciel nie chce wybierać grupy (E:8124) |
| Minimum 1080p i minimum rozmiaru | Właściciel dopuszcza inne rozdzielczości; rozmiar to intuicja (E:8124) |
| Ranking „deklaracja PL przed rozdzielczością” (propozycja asystenta E:9718 i pierwsza wersja `final2/`) | Właściciel: jakość obrazu wygrywa, 720p to ostateczność (decyzja 2026-09-23) |
| 720p przed 2160p (`final/` D04, pierwsza wersja `final2/`) | Sprzeczne z „jakość obrazu wygrywa” |
| Twarde 72-godzinne okno szukania i ręczne „Ponów szukanie” | Powoduje objaw „subskrypcja stoi” (§3.2 pkt 4); zastąpione U-14 |
| Ścieżka „Ustal cel wcześniejszego pobrania” dla starych zleceń | M-06 zachowuje dotychczasowe zachowanie bez nowego ekranu i polecenia |
| Snapshoty stronicowania IPC z TTL i limitami pamięci | Żadne wymaganie tego nie żąda; Q-08 rozwiązuje ryzyko rozmiaru prościej |
| Plik-marker transakcji migracji | Migracja każdego pliku jest idempotentna i poprzedzona kopią (M-07) |
| Tryb katalogu „tylko zapisane” i klawisz K | „Pobierz ponownie” działa z listy odcinków po zwykłym wyszukaniu |

## 13. Chronione kontrakty

Ta praca nie zmienia poniższych zachowań (kontrakt `../local-automation-2/spec.md`). Każde ma test regresji w planie etapu, który dotyka danego obszaru. Jawne odstępstwa: PR-02 i PR-03.

| ID | L:R | Zachowanie |
| --- | --- | --- |
| PR-01 | 001–005, 018 | Jeden rezydent i właściciel; wiele paneli; Ręczny ma priorytet bez przerywania zadania; zamknięcie panelu nie zatrzymuje pracy. |
| PR-02 | 006–007, 012–014, 027 | Zakres „od N”, przyszłe odcinki, brak trackera oglądania, trwałe przyjęcia. Odstępstwa: obowiązkowa grupa i minimum 1080p (L:R-006/027) zastąpione przez U-04; Subskrybuj otwiera szkic, a nie kartę w zakładce (L:R-027); „od N” wyliczane z punktu odcięcia, bez edycji (U-09). |
| PR-03 | 008–011 | Sekundowy zegar bez sekundowego HTTP; wspólne limity źródeł. Odstępstwo: okno 72 h z L:R-010 zastąpione przez U-14; etykieta „Brak terminu” (L:R-008) → „Termin nieznany”. |
| PR-04 | 015, 021, 024, 030 | Prywatny profil qB, globalna pauza, wznowienie tylko własnych transferów, zamknięcie i autostart. |
| PR-05 | 016–017, 019–020, 028 | Kompletność przed przetwarzaniem, niezmienny snapshot przyjęcia runu, błędy z przyczyną, regeneracja, zachowanie starych wyników. Plik próby automatycznej subskrypcji wchodzi do Auto tylko przy wyniku `przyjęta` (U-19). |
| PR-06 | 022–023, 025, 043–044 | Home z marką, cztery zakładki, pierwsze wejście w Przetwarzanie, spokojny stan bezczynności, jeden renderer. |
| PR-07 | 026, 029, 031–032 | Presety, ustawienia, płaskie nowe pobrania, wspólne `ready/`, źródło czeka na zwolnienie. |
| PR-08 | 033–034, 038 | `subs/` czeka na parę; sam TXT/SRT w root nie uruchamia audio; nazwa pliku napisów nie dowodzi języka. |
| PR-09 | 035–037 | `translate/`, `audiobook/`, `cover/` bez zmian. |
| PR-10 | 039–042 | Biblioteka: Enter otwiera, F pokazuje, Delete do Kosza cały zestaw; Historia 30 dni/50 pozycji. |
| PR-11 | 045 | Brak wyświetlanych napisów to legalny stan, nie błąd. |
| PR-12 | 046–047 | Ctrl+Z przywraca dokładny ostatni usunięty zestaw, także po restarcie. |

## 14. Warunki sukcesu

| Obszar | Warunek | Instrument |
| --- | --- | --- |
| Wyszukiwanie | Dla 10 tytułów z listy właściciela, w tym Slime S1E4 (A:S-01), właściwy wpis i odcinek są osiągalne w ≤ 3 wyborach od wpisania nazwy | Scenariusz H1 |
| Tożsamość | Heurystyka zbudowana od zera na oznaczonym korpusie ≥ 2000 tytułów / ≥ 10 000 rekordów (odcinek + kandydat), po stałym losowym podziale stratyfikowanym z zapisanym ziarnem i sumami. Budowa wyłącznie na części roboczej; jednorazowy egzamin na części odłożonej, niewidzianej przez autora: 0 błędnych `zgodnych` wśród przypadków rozpoznawalnych z nazwy/metadanych; pozostałe raportowane jako „domena heurystyki 2” (plan E1 D6). Udział `niepewnych` i błędnych `niezgodnych` per warstwa przedstawiony właścicielowi do decyzji bez narzuconego progu. Porażka wymaga nowej części odłożonej; historyczne 231 rekordów to dane z etykietami i kontrole, bez parytetu z prototypem (decyzja właściciela 2026-09-24) | Testy jednostkowe na stałych oznaczonych próbkach + manifest podziału, dowód izolacji i raport jednorazowego egzaminu E1 (N-02) |
| Ranking | Kolejność U-04/U-05 na przypadkach granicznych (1080p bez PL vs 720p z PL, 2160p vs 720p, PL vs MultiSub w 1080p, MultiSub vs NF bez MultiSub, 1440×1080, brak seedów, nieobsługiwany kontener) | Testy jednostkowe |
| Pobieranie | Syntetyczna paczka: E1 i E3 bez E2, jeden transfer, restart w trakcie, oba odcinki w Bibliotece, E2 nieprzetworzone (A:S-08) | Test integracyjny z rzeczywistym qB na syntetyku |
| Pobieranie | Właściciel pobiera jeden prawdziwy odcinek i ogląda wynik w Bibliotece | Scenariusz H2 |
| Subskrypcje | Fake clock: emisja → wyszukanie → zlecenie; brak wydania 72 h → dalej raz na dobę; zakończenie sezonu → zniknięcie z listy; restart w każdym punkcie; problem jednego wpisu nie blokuje innych (A:S-03, S-04, S-06) | Testy integracyjne |
| Subskrypcje | Jeden aktualnie emitowany tytuł przez tydzień: odcinek pojawia się w Bibliotece bez dotykania aplikacji | Scenariusz H3 |
| Parametry przepływu | Raport kompromisu P-2, P-5 zaakceptowany przez właściciela; do tego czasu konfiguracja tymczasowa zaakceptowana razem z integracją | Raport według planu przepływu §4 |
| Kontrola po pobraniu | Decyzja H2: zostaje / wypada / tylko zapis | Pomiar według planu przepływu §5.4 |
| Historia | Replay całej bazy przypadków i części roboczej korpusu bez naruszeń przy każdej zmianie heurystyki lub parametrów | Test regresyjny według planu przepływu §5.7 |
| Migracja | Kopia rzeczywistego `subscriptions.json` i `state.json` właściciela przechodzi M-01–M-07 bez utraty wpisu | Test na kopii |
| Folder lokalny | Istniejące przetwarzanie MKV z workspace bez zmian (A:S-07) | Istniejące testy + H2 |
| Regresje | Pełne bramki `AGENTS.md` zielone; PR-01–PR-12 mają testy | CI + lokalne bramki |
| UX | Właściciel sam znajduje „Dodaj subskrypcję” i usuwa subskrypcję bez podpowiedzi | Scenariusz H3 |

## 15. Nierozstrzygnięte

Każda pozycja ma etap i metodę rozstrzygnięcia. Żadna nie blokuje planu etapu E1 — N-01–N-04 rozstrzyga E1, N-05 etap E4.

| ID | Pytanie | Dlaczego ważne | Rozstrzyga |
| --- | --- | --- | --- |
| N-01 | Po jakim czasie od emisji nowy odcinek ma zgodnego kandydata w Torrentio, a po jakim w Nyaa RSS? Czy Torrentio zawiera wszystkie zgodne wydania, które ma Nyaa (porównanie hashy tego samego odcinka)? | Czy Torrentio może być jedynym źródłem — dla subskrypcji i dla zwykłego Pobierz | Rozstrzygnięte 2026-09-28: pomiar na żywo (7 dni) zastąpiony pilotem historycznym; Torrentio jedynym źródłem (U-02). Opóźnienie Torrentio, 429 i M-6 potwierdza rejestr/cień po integracji (plan przepływu §5.1) |
| N-02 | Jak heurystyka działa na korpusie co najmniej 2000 tytułów (TV, kontynuacje, OVA, filmy, różne lata): jaki odsetek odcinków ma zgodnego kandydata i czy któryś `zgodny` jest błędny? | 231 rekordów z trzech franczyz to za mało (decyzja właściciela); za dużo `niepewnych` = automat nic nie pobierze | Pomiar E1: cały korpus oceniony przez dwa modele różnych rodzin (skrypt, klucz Palantir), z rekordami kontrolnymi o znanej etykiecie; niezgodności do trzeciego modelu i właściciela; cel 0 błędnych `zgodnych` rozpoznawalnych z nazwy/metadanych (plan E1 D6) |
| N-03 | Czy qBittorrent w prywatnym profilu AniShift pobiera metadane torrenta z samego hasha (magnet z trackerami z `sources`, DHT), zatrzymuje się przed zapisem treści i pozwala ustawić priorytety plików przed startem? Ile to trwa? | Bez tego nie ma pobierania z Torrentio (zwraca tylko hash) ani U-17 | Próba techniczna E1 (tylko metadane, bez treści) |
| N-04 | Czy Torrentio zwraca kandydatów dla filmów po `kitsu:<id>`? | U-21 | Pomiar E1 |
| N-05 | Jak rozpoznać w kontenerze „pełne napisy” wobec „tylko napisy ekranowe (signs)”? | U-08 | Próba na pobranych plikach w E4 |

## 16. Pochodzenie z wcześniejszych kontraktów

| Kontrakt A | Tutaj |
| --- | --- |
| A:R-01 wejście lokalne | U-19, PR-05–PR-09, A:S-07 w §14 |
| A:R-02 jednorazowe pozyskanie | U-01, §5.3 |
| A:R-03 subskrypcja, także przed startem sezonu | U-09, U-10, §5.4 |
| A:R-04 wyszukiwanie tytułu, rok, bez liczby odcinków | W-01–W-03 (kierunek lat: malejąco) |
| A:R-05 kontekst sezonu | W-04–W-07 |
| A:R-06 dowolny wybór | P-01 |
| A:R-07 cały sezon z dodatkami | Zmienione: dodatki pobiera się jawnie (W-06, U-09); dane nie pozwalają automatu |
| A:R-08 paczki | U-17, U-18, P-06–P-08 |
| A:R-09 rzetelność pokrycia | R-06, R-08, W-08, §5.5 |
| A:R-10 jeden sezon | U-09 |
| A:R-11 natychmiastowe uzupełnienie | Zaległe zaznaczone w szkicu i zlecone przy dodaniu ścieżką ręczną (S-02, 2026-10-04) |
| A:R-12 brak historii oglądania | Poza zakresem (tracker), P-01 |
| A:R-13 duplikaty | U-16, I-03, I-06 |
| A:R-14 publikacja, nie zakładany czas | U-13, U-14 |
| A:R-15 minimum decyzji o źródle | U-03, U-04 |
| A:R-16 jakość | U-04, U-05 |
| A:R-17 przydatność napisów | U-07, U-08 |
| A:R-18 odzyskiwanie | U-08, U-14, S-12 |
| A:R-19 pełne wyłączenie | P-04, I-05, M-07 |
| A:R-20 kompletne wejścia | P-07, P-08, I-07 |
| A:Q-01–Q-04 | Q-01–Q-05, §14 |
| A:S-01–S-08 | §14 |

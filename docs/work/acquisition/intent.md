---
kind: intent
status: w toku
updated: 2026-10-05
---

# Intencja: pozyskiwanie odcinków (wyszukiwanie, wybór, pobieranie)

Żywy zapis ustaleń z właścicielem. Obowiązujący kontrakt pozostaje w [spec.md](spec.md); tu trafia potrzeba, podstawa wyboru i to, co jeszcze nierozstrzygnięte. Po akceptacji ustalenia przechodzą do specyfikacji.

## Potrzeba

Właściciel klika subskrypcję (albo wybiera odcinki) i nie myśli o niczym więcej: właściwy odcinek w najlepszym dostępnym wydaniu pobiera się sam, wkrótce po emisji, i ląduje w Bibliotece. Nie może się zdarzyć, że wydanie istnieje w sieci, a aplikacja go nie znajduje.

## Obserwacje (2026-10-05)

- **Wyszukiwanie:** jedynym źródłem jest Torrentio po Kitsu ID (`application/acquisition.py:prepare_episode`). Tytuły bez Kitsu ID (AniList 210031) dają 0 wydań, nowe sezony prawie nic (159042: 1 wydanie). Wcześniej aplikacja szukała w Nyaa; decyzja U-02 z 2026-09-28 zastąpiła to Torrentio na podstawie pilota z 5 starymi serialami.
- **Nazwy:** Torrentio ucina tytuł do ok. 60 znaków; pełna nazwa pliku (`behaviorHints.filename`) przychodzi w tej samej odpowiedzi, ale ekran i wykrywanie PL/rozdzielczości jej nie używają.
- **Rozpoznanie odcinka (H1, `application/episode_identity.py`):** trzy szufladki zgodny / niepewny / niezgodny, projektowane pod „zero fałszywych zgodnych”; patrzy tylko na nazwy. Wiele poprawnych wydań jest niepewnych (159042 odc. 1: 12 z 25), a subskrypcja bierze tylko zgodne.
- **Ranking (`application/episode_selection.py:_rank_key`):** schodkowy — werdykt → kontener → sam dubbing → rozdzielczość → PL → MultiSub → platforma NF/CR → seedy. Niższe kryterium działa tylko przy remisie wyższych, więc znacznik „CR” w nazwie przebija 6× więcej seedów (zrzut Polar Opposites S1E1: ToonsHub 76 seedów nad Trix 121 i BluRay 510).
- **PL** wykrywane wyłącznie z nazwy lub flagi Torrentio; polskie napisy w MultiSub są niewidoczne.

## Pomiary źródeł (2026-10-05)

Skrypty i surowe dane: `%TEMP%\opencode\anime_*`, `%TEMP%\opencode\agg_*`.

- **TsukiHime** (`api.tsukihime.org/v1`, po AniList ID → odcinek; mirror Nyaa/nekoBT/TokyoTosho): najwięcej wydań przypisanych do odcinka, pełne nazwy, listy języków audio i napisów (`sublangs`), bez seedów.
- **nekoBT:** dodatkowe wydania z PL, których TsukiHime nie miał (np. Erai-raws Blue Box 1080p z PL).
- **Knaben API:** wieloźródłowy indeks (Nyaa, TokyoTosho, TPB, 1337x, RuTracker), seedy, szukanie tekstem; dodał 4–8 wydań na odcinek ponad TsukiHime.
- **Nyaa RSS:** w pomiarze podzbiór TsukiHime; daje seedy i daty.
- **Torrentio po Kitsu:** trochę unikalnych wydań i seedy, ale miesza odcinki (14 z 73 z innego odcinka). Po IMDb — wyniki z innych sezonów, odrzucone.
- **AnimeTosho:** 0 wyników, ogłoszone wyłączenie (X 2026), odrzucone.
- **Agregator „wszystkiego” nie istnieje.** Najbliżej: Knaben (publiczne API) i Prowlarr/Jackett (lokalny proces, dziesiątki trackerów). Crawler DHT lub własny serwer: wysoki koszt, ryzyko prawne, nadal bez gwarancji 100%.
- TsukiHime + nekoBT + Knaben na 3 odcinkach: 74 wydania zamiast 51 z samego TsukiHime.

## Ustalenia właściciela (2026-10-05)

- Wyniki z wielu źródeł; ten sam hash = ten sam torrent = jeden wiersz z połączonymi informacjami.
- Pełne nazwy ze wszystkich źródeł, również na ekranie.
- Zamiast szufladek i schodków: **wartość procentowa**. Pewność, że to właściwy odcinek, oraz ocena jakości liczona z wszystkich czynników razem (rozdzielczość, PL, MultiSub, Dual/Multi Audio, platforma, seedy) — jak w modelach predykcyjnych.
- Więcej seedów ma znaczenie (szybsze pobranie).
- Dual Audio / Multi Audio jako wybór właściciela, nie sztywna reguła.
- Napisy PL z zewnętrznych źródeł (np. dodatki Stremio) — chciane, osobny etap po działającym pozyskiwaniu wideo.
- Wygląd Subskrypcji i Biblioteki nie spełnia standardów — osobny etap.
- Bez kodu, dopóki właściciel nie zrozumie i nie zaakceptuje kierunku.

### Do czego służy heurystyka

- **Ręczny wybór (głównie starsze tytuły):** właściciel wybiera sam, ale na górze listy mają stać wydania, które heurystyka uznała za najlepsze, z widoczną wartością procentową.
- **Subskrypcja (nowe odcinki trwającego sezonu):** ma działać praktycznie bezbłędnie. Lepiej nie pobrać niż pobrać zły odcinek. Każde niepowodzenie (nic nie pobrano, odrzucono, pobrano coś wątpliwego) musi być widoczne i mieć podany powód — nic nie może przejść niezauważone.

### Najlepsze wydanie

- Wzorzec: **1080p + MultiSub zawierający PL + Multi/Dual Audio**, z platformy (Netflix, Crunchyroll, ADN i podobne), np. wydania ToonsHub.
- Polskie napisy są pierwszą zaletą. Przy wyborze między „PL” a „PL + Dual Audio z polską ścieżką” wygrywa Dual Audio; Dual Audio JA + EN nie jest zaletą.
- Języki, które się liczą: polski, japoński, angielski; przy donghua także chiński. Gdy istnieją wersje japońska i koreańska — wybieramy japońską (koreańska akceptowalna).
- **Cechy wydania wygrywają z seedami.** Seedy to umiarkowany czynnik szybkości (pobieranie i tak idzie w tle); nie mogą decydować same, ale martwe wydania trzeba unikać.
- **4K i Blu-ray nie są preferowane:** właściciel ogląda zwykle w 2× z interpolacją klatek; na 4K i ciężkich wydaniach Blu-ray odtwarzanie się zacina (sprawdzone 2026-10-05: Blu-ray wygląda świetnie, ale nie da się go interpolować). Preferowane lekkie 1080p WEB.
- **Blu-ray bez osobnej heurystyki:** Blu-ray wychodzi dopiero po zakończeniu sezonu, a o jego pobraniu właściciel decyduje ręcznie.
- **Audio:** liczy się polska ścieżka (wydania Multi Audio z PL zwykle mają też inne języki). **Angielski dubbing nie ma żadnej wartości** — właściciel go nie ogląda; „Dual Audio JA + EN” nie jest zaletą.
- **Napisy:** PL to główna zaleta. Inne języki poza EN dziś nic nie dają, bo tłumaczenie idzie z angielskiego; tłumaczenie wspierane wieloma językami (zaimki, czasowniki) to pomysł na przyszłość, nie wymaganie.
- **Seedy:** bardzo mało seedów (np. 5) to ryzyko, że wydanie się nie pobierze — kara. Różnica 400 vs 900 prawie nic nie zmienia (podobna prędkość) — malejące znaczenie.
- **Przykład kolejności właściciela (2026-10-05, wszystkie 1080p, właściwy odcinek):** F (napisy PL + audio JA + PL, 60 seedów) > A (napisy PL, audio JA, 80) > C (napisy PL, audio JA + EN, 30) > E (napisy PL, Multi Audio bez PL, 5 seedów — ryzyko) > B (bez PL, więcej języków, JA + EN, 400) ≈ D (tylko EN, JA, 900). B wobec D właściciel uznaje za trudne do rozstrzygnięcia.
- **Grupa nie jest kryterium samym w sobie** — liczy się zawartość wydania. Lista grup aktywnych dziś (z wielu źródeł, przegląd ostatnich lat) może powstać później jako analiza, nie jako reguła.

### Czekanie na polskie napisy w subskrypcji

- **Bufor w Ustawieniach:** maksymalny czas czekania na wydanie z polskimi napisami; domyślnie **5 h** (właściciel rozważał 1–2 h, za bezpieczne uznał 5 h). **Zmiana 2026-10-06:** po pomiarze (2 h → 212, 5 h → 217 z 267) domyślnie **2 h**, plus akcja „Pobierz teraz” dla czekającego odcinka; odcinek pobrany bez PL zostaje (bez podmiany), bo tłumaczenie jest podstawową drogą programu.
- W tym czasie tytuł jest sprawdzany często (np. co 15 min, jak w obecnym harmonogramie pierwszej doby U-14).
- Po upływie bufora bez PL pobiera się najlepsze dostępne wydanie (np. angielskie), z widocznym powodem.
- Podczas czekania użytkownik może ręcznie pobrać od razu dostępne wydanie; widzi, że odcinek czeka na PL.
- **Czy tytuł będzie miał PL (zaakceptowane 2026-10-05):** seria „uczy się” z własnej historii. Poprzednie odcinki miały wydanie z PL → czekamy; kolejne bez PL → przestajemy czekać i bierzemy od razu. Odcinek 1 nowego sezonu patrzy na poprzedni sezon z grafu franczyzy AniList. Seria bez historii: pierwszy odcinek czeka pełny bufor; bez PL kolejne nie czekają. Źródło wiedzy: `sublangs` TsukiHime (języki odczytane z pliku), nazwa tylko jako uzupełnienie. Szczegóły subskrypcji pokazują stan, np. „PL: zwykle jest, czekam do 5 h” albo „PL: brak w tej serii, pobieram od razu”.
- Podwójne pobieranie (szybkie, potem podmiana) odrzucone: dubluje przetwarzanie (tłumaczenie, lektor), zatyka kolejkę i zaśmieca dysk.
- Na dubbing PL subskrypcja nie czeka (pojawia się zwykle dużo później).

- **2026-10-05, po badaniu 3:** pierwszy odcinek bez historii czeka **2 h** (zamiast pełnego bufora). Bufor liczony przy każdym odcinku osobno. Pozostałe zmiany (poprzedni sezon, jeden bufor) — otwarte w `algorithm-spec.md` §12.

### Pewność i ocena na liście

- Przy każdym wydaniu dwie kolumny na końcu listy: **ocena jakości** i **pewność, że to właściwy odcinek** (w %). Na start obie, żeby dało się sprawdzać i debugować algorytm; gdy heurystyka okaże się dobra, może zostać jedna.
- Lista przy ręcznym wyborze to jedna kolejka ze wszystkich źródeł. Źródło wydania nie ma znaczenia i nie jest pokazywane; liczy się ułożenie.
- **Próg pewności dla subskrypcji nie jest decyzją właściciela** — ma wynikać z testu modelu na zbiorze danych (korpus E1). Istnieją sygnały unieważniające (np. inny sezon albo odcinek w nazwie), które wykluczają wydanie niezależnie od reszty.

### Pobieranie, które stoi

- Torrent, który przez **10 minut** nic nie pobiera, uznajemy za niedziałający i bierzemy następne wydanie z rankingu — bez schodzenia do gorszej jakości (np. 720p).

### Brak PL mimo deklaracji

- Zdarza się rzadko. Zamiast pobierać inne wydanie, lepiej poszukać osobnych polskich napisów (etap napisów zewnętrznych).

### Źródła

- **Zestaw źródeł niezaakceptowany.** Przed decyzją potrzebny pomiar szybkości: czas odpowiedzi każdego źródła i czas całego wyszukiwania przy wszystkich źródłach równolegle, razem z pokryciem.
- Źródła (konektory) można włączać i wyłączać w Ustawieniach, bo większość wyników się pokrywa.

### Zakres

- Filmy, OVA i odcinki specjalne są w zakresie.
- Wyszukiwanie tytułów (AniList) działa dobrze i zostaje.

### Paczki

- W subskrypcji paczki nie mają sensu (sezon jeszcze trwa, paczki są niepełne).
- W ręcznym wyborze paczki są dopuszczalne i sortowane tą samą heurystyką.

### Sukces

Na górze listy stoi, z wartością procentową, najbardziej dopracowane wydanie: 1080p, MultiSub z PL, Multi Audio — niekoniecznie z największą liczbą seedów.

## Kierunek roboczy (propozycja, nieuzgodniona)

1. Źródła: TsukiHime + nekoBT + Knaben + Torrentio, równolegle, scalanie po hashu.
2. Dwa wyniki na wydanie: pewność odcinka w % (skalibrowana na korpusie E1, > 10 000 oznaczonych nazw) i ocena jakości z wagami właściciela.
3. Subskrypcja: najlepsza jakość spośród wydań powyżej progu pewności.
4. Zestaw wzorcowy prawdziwych odcinków z poprawnymi odpowiedziami jako dowód przed odbiorem.

## Wyniki badań

### Badanie 1 — szybkość i pokrycie źródeł (2026-10-05, sol61; `%TEMP%\opencode\src_*`)

- Próba: 9 tytułów (6 nowych, 3 starsze: Frieren, SPY×FAMILY, Bocchi), 15 odcinków, 640 unikalnych kandydatów ze wszystkich 5 źródeł.
- Czas wyszukiwania (mediana na zimno): TsukiHime 0,7 s, Torrentio 0,3 s, Nyaa RSS 2,0 s, nekoBT 3,0 s (do 13,6 s), Knaben 5,2 s (do 13 s). Knaben i nekoBT są wolne przez stronicowanie i limity, nie przez serwer.
- Co tracimy bez źródła: Torrentio 17,8% (kluczowe dla starszych serii), Nyaa 10,8%, Knaben 8%, nekoBT 1,7% (ale unikalne wydania z PL, np. Erai Blue Box, FrixySubs Apothecary), TsukiHime 1,3% (mało unikalnych, ale najszybsze i ma języki).
- TsukiHime dla starszych serii: 0–1 wynik — nie zastępuje archiwum.
- Zestawy: TsukiHime + Torrentio + Nyaa = 88,9% pokrycia, ok. 2 s (14/15 prób < 3 s); + Knaben = 98,3%, ok. 4,5 s (do 13 s); wszystkie 5 = 100%, do 15 s.
- Rekomendacja: szybka trójka od razu, Knaben (i ewentualnie nekoBT) dociągane w tle — lista się uzupełnia.
- Nazwy plików: Torrentio ma je prawie zawsze (372/373); TsukiHime wymaga osobnego żądania na każdy torrent (ok. 0,1 s na żądanie, ale cała partia odcinka z limitem tempa: mediana 9 s, do 17 s) — pobierać tylko dla kilku najlepszych kandydatów, z cache po hashu.
- Ryzyka: TsukiHime ma 3 limity naraz (25/10 s, 60/30 s, 100/min); Knaben API v2 ma 4 dni; Torrentio bywa blokowane przez Cloudflare (403) i nie ma Kitsu dla części tytułów.

### Badanie 2 — model pewności (2026-10-05, astra; `%TEMP%\opencode\conf_results.md`)

- Korpus: `C:\Users\MattyMroz\acquisition-labels\split-v1-labels-fix3\` (52 577 rekordów, 2001 tytułów); ocena końcowa na odłożonym `exam-v2` (4000 rekordów).
- Dzisiejsza H1: „zgodny” obejmuje tylko **ok. 49% poprawnych wydań** (prawie bez błędów: 25 na 15 380). „Niepewny” to worek: 15 809 poprawnych i 4683 błędnych — naprawdę miesza dobre i złe.
- Prosty model procentowy (regresja logistyczna na sygnałach H1 + kalibracja) działa jako ranking, ale **nie jest jeszcze lepszy od „zgodny” w automacie**: przy progu 99% na egzaminie przepuścił 6 złych wydań (zgodny: 0), a łącznie przepuścił mniej poprawnych.
- Wartości procentowe są w miarę wiarygodne (np. przedział 98–99% → 98,6% faktycznie poprawnych), więc nadają się do kolumny „pewność” na liście.
- Twarde „weta” (konflikt numeru/sezonu) odrzucają też dużo poprawnych wydań, bo parser się myli (np. „Ken Deshita 2 - 01” czyta „2” jako numer odcinka). Konflikt trzeba pokazywać jako powód, nie jako „0%”.
- **Główna dźwignia dla TsukiHime: nazwy plików.** Bez listy plików wszystkie wydania TsukiHime dostają „brak wybranego pliku” i są niepewne.
- Nie zmierzono wpływu numeru odcinka podanego przez źródło ani potwierdzeń z wielu źródeł (brak danych w korpusie).

### Badanie 3 — polskie napisy w czasie (2026-10-05, sol6; `%TEMP%\opencode\pltime_*`)

- Próba: 54 tytuły z wiosny–jesieni 2026, 509 odcinków, 9439 wydań (TsukiHime + AniList).
- **Hipoteza właściciela potwierdzona:** gdy PL się pojawia, to zwykle szybko — mediana **ok. 37 min** po emisji (ok. 33 min wśród PL z pierwszej doby); do 1 h 55%, do 2 h 79%, do 5 h 81% (z tych, które w ogóle dostały PL). Między 2. a 5. godziną doszło tylko 5 odcinków na 509 — 5 h to bezpieczne maksimum, 2 h prawie tak samo dobre.
- **Seria uczy się z historii — mocno potwierdzone:** poprzedni odcinek miał PL → następny ma PL w 97%; nie miał → tylko w 3%. Ale 4 z 19 serii bez PL w odcinku 1 dostały PL później (np. Re:ZERO S4, Slime S4) — brak PL nie może trwale wyłączać czekania; ocenę aktualizować co odcinek.
- **Poprzedni sezon nie jest wiarygodnym wskaźnikiem:** historia starszych sezonów w TsukiHime jest szczątkowa (6 z 15 bez danych, sprzeczne pary, np. Polar Opposites S1 0/2 → S2 13/13). Używać tylko przy pełnej historii; inaczej „nieznane”.
- **Prawie połowa serii nie ma PL w ogóle** (18 z 40 tytułów z ≥ 5 odcinkami; 19 z 41 przy ≥ 2 odcinkach) — także duże tytuły (BLEACH, Dr. STONE, Grand Blue, Wistoria, Classroom of the Elite). Czekanie bez historii PL byłoby często zbędne.
- **Najszybsze PL:** ToonsHub (mediana 0,6 h), VARYG (0,6 h), Erai-raws (1 h); wolniej Onalrie, Judas, Trix, Ironclad, DKB (2–4 h). Platformy w nazwach: głównie CR, rzadziej NF i ADN.
- **„MultiSub” w nazwie nie oznacza PL:** 3252 wydania z MultiSub nie miały `pl`. Warunek PL tylko z `sublangs` (albo sprawdzonego pliku).
- Korekta: `source_date` TsukiHime jest poprawne; przesunięcie o 2 h dotyczy RSS Nyaa.

## Nierozstrzygnięte

Pytania do właściciela prowadzone w rozmowie; odpowiedzi dopisywane w „Ustaleniach”.

- **Badanie 1 — źródła:** szybkość i pokrycie TsukiHime, nekoBT, Knaben, Torrentio, Nyaa osobno i razem.
- **Badanie 2 — model pewności:** jak policzyć pewność odcinka w % i jaki próg dla subskrypcji, na korpusie E1.
- **Badanie 3 — polskie napisy w czasie:** dla kilkudziesięciu tytułów z ostatnich sezonów — czas od emisji do pierwszego wydania z PL i odsetek tytułów, które PL w ogóle dostają (historia TsukiHime). Sprawdzi hipotezę właściciela „od 30 min do kilku godzin” i domyślny bufor 5 h.
- **Podmiana po pobraniu:** co, gdy lepsze wydanie pojawi się po pobraniu słabszego.

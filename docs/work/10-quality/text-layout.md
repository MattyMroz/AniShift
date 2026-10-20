# Układ tekstu na ekranie — specyfikacja v4 (szkic)

Status: szkic orkiestratora, 2026-10-19. Czwarta próba po odrzuceniu trzech algorytmów łamania (U5 `16-line-breaks`, rewrite `20-line-breaking`, wcześniejsze łatki). Zastępuje [line-breaking.md](line-breaking.md) v1.9 i [fuzzy-line-breaks.md](fuzzy-line-breaks.md) oraz część A [fuzzy-signs-and-split.md](fuzzy-signs-and-split.md) w zakresie podziału na wiersze i rozmiaru szyldu. Nadrzędny cel pozostaje w [visual-quality.md](visual-quality.md); jego zdanie o „dużej przewadze przecinka” (§4) jest zastąpione przez §4.4 tego dokumentu.

Ten dokument mówi **co chcemy osiągnąć i po czym poznamy, że się udało**. Mechanika jest tylko tak szczegółowa, jak trzeba, żeby wykonawca nie zgadywał.

## 1. Cel

Każdy polski tekst, który AniShift kładzie na obraz — dialog czytany przez lektora, napis poboczny (szyld, napis ekranowy, tytuł, podpis, piosenka) — ma być ułożony tak, jak ułożyłby go staranny człowiek: czyta się go jednym spojrzeniem, nie rozrywa sensu, nie zasłania więcej obrazu, niż musi, i we wszystkich podobnych sytuacjach zachowuje się tak samo.

Po zakończeniu prawdą jest:

1. Jeden rdzeń układu decyduje o podziale na wiersze i rozmiarze dla wszystkich rodzajów tekstu. Rodzaje różnią się tylko parametrami pola (§3), nie osobnymi regułami cięcia.
2. Wynik każdego przypadku z katalogu (§6) należy do jego zbioru dopuszczalnych układów i nie łamie żadnego zakazu. Kryterium końca to 100% katalogu w tym jednym znaczeniu, nie procent zgodności.
3. Na zestawie bardzo trudnych scen (`workspace/.quality/experiments/v4-hard/`) żaden układ nie zostaje oceniony jako zły przez orkiestratora i dwóch recenzentów innej rodziny, a właściciel potwierdza wynik na obrazach stan wejściowy → nowy.
4. Spójność jest udowodniona, nie zadeklarowana: istnieje jeden zestaw wag, przy którym w każdym przypadku katalogu i ankiety najlepszy kandydat z **pełnej** przestrzeni należy do zbioru dopuszczalnych (§5.3). Jeśli taki zestaw nie istnieje, katalog jest sprzeczny i rozstrzyga właściciel, a nie łatka w kodzie.

## 2. Czego nauczyły trzy odrzucone próby

| Błąd | Skutek widoczny dla właściciela | Reguła tej specyfikacji |
| --- | --- | --- |
| Wybór właściciela spośród dwóch wariantów zamieniony w regułę ogólną (przypadek 04: widział tylko jeden wiersz i złe cięcie „z taką / złością”, a zapisano „55 znaków → jeden wiersz”) | rampa długości 40–62 znaków; jednowierszowe kwestie 53–56 znaków tam, gdzie właściciel chce dwóch | Decyzja właściciela to preferencja **parowa** między wariantami, które naprawdę widział (§5.3). Rekomendacje agentów nie są decyzjami właściciela. |
| Rekomendacje agentów i pytania właściciela zapisane jako jego decyzje (rejestr 19.10: pewne są tylko 2 decyzje parowe) | kalibracja na gustach agentów; właściciel nie poznaje swoich wyborów w wyniku | Kotwicami są tylko jawne wybory właściciela; brakujące zbiera ankieta (§5.4). |
| Przecinek z „dużą przewagą” nad równowagą (visual-quality §4) | „Wręcz przeciwnie, / te plotki…” 17/49 | Kurs wymiany interpunkcji na równowagę bierzemy z danych zawodowców (§4.4), nie z intuicji. |
| Rampa długości tylko po szerokości przy wąskiej Officinie | 60 znaków w jednym wierszu (U5) | Długość ocenia się w znakach (ilość do przeczytania) **i** w szerokości (droga oka, mieszczenie się); decyduje gorsza z dwóch miar (§4.1). |
| Trzy wiersze z progu, łatki leksykalne, osobne reguły dla podobnych przypadków | „raz tak, raz inaczej”; trzy wiersze, choć mieszczą się dwa | Jedna funkcja oceny dla wszystkich kandydatów i rodzajów; trzeci wiersz dialogu tylko w ratunku (§5.2). |
| Dialogi i szyldy w osobnych ścieżkach, szyldy odłożone | napisy poboczne bez poprawy | Jeden rdzeń, pole jako parametr (§3). |
| Galeria względem poprzedniego algorytmu, różne czcionki po bokach | nie da się ocenić postępu | Galeria zawsze: stan wejściowy (`replay/baseline`, układ sprzed prac nad jakością) → nowy, ta sama czcionka dialogów po obu stronach. |
| Ogłoszenie gotowości ze znanymi błędami i bez obejrzenia każdego obrazu | utrata zaufania | Koniec = §7; orkiestrator ogląda każdy obraz przed pokazaniem właścicielowi. |

## 3. Rodzaje tekstu i pole

### 3.1 Stan wejściowy (fakty z rozpoznania 2026-10-19)

- Dwie ścieżki układu w `anishift/services/subtitles/`: dialog (`layout_dialogue` w `linebreak.py`, liczy znaki, 42 × 2) i cała reszta wyświetlana (`split_for_layout` + `fit_signs`). Szyld jedno- i wielowierszowy, piosenka, karaoke i tekst z `\pos`/`\move`/`\frz`/`\clip` idą tą samą drugą ścieżką; pomijane są tylko rysunki (`service.py`, `layout_translated`).
- Wiedza o cięciu jest w dwóch rozjechanych rankingach w `linebreak.py`: dialog chroni „nie”, tytuły, imię z nazwiskiem, jednoliterowe słowa i nawiasy; szyld chroni tylko przyimki i frazy, więc szyld można przeciąć „nie / chciałem” albo „Jan / Kowalski”.
- Szerokość liczą trzy miary: znaki (dialog), Arial 64 px (`fit_signs`) i prawdziwa czcionka z emulacją zawijania libass (`geometry.py`), której na `08` nie używa ani dialog, ani szyld.
- Szyld jednowierszowy dłuższy niż 42 znaki dostaje dwa wiersze liczone po znakach, bez pomiaru miejsca.
- Karaoke (`\k`) jest tłumaczone i układane jak szyld, wbrew regule nienaruszalnej visual-quality §2.1.6; tagi `\ko` się zlepiają (Kaguya S1E06).
- Wstrzymane U4 (`18-signs` + niezacommitowane `q-signs`) pokazało skrajności, które ta specyfikacja musi wykluczyć: lista-ranking Kaguya (199 wierszy źródła, co drugi pusty, 100 słów przekładu) ściśnięta do 1,63%, bo puste wiersze liczono jako wiersze do wypełnienia, a szkoda zniekształcenia nasycała się przy 0,9; `\frz90\fscy1947` zmniejszone do 6%, bo prostokąty na ekranie liczono bez obrotu; 246 z 1250 obiektów ściśniętych poniżej 72% bez podłogi.

### 3.2 Jeden rdzeń: tekst w polu

Rdzeń dostaje tekst (z tagami ASS zakotwiczonymi w widocznym tekście) i **pole**. Pole opisuje, gdzie tekst ma się zmieścić i jak ma wyglądać. Rodzaje tekstu to tylko różne pola:

| Pole | Dialog (napis główny) | Napis poboczny w jednym wierszu | Napis poboczny wielowierszowy | Piosenka | Dymek MangaShift (później) |
| --- | --- | --- | --- | --- | --- |
| Szerokość wygodna | ok. 42 znaków czcionki dialogu | szerokość angielskiego oryginału | szerokość najszerszego wiersza oryginału | jak dialog (r1; nie szerokość oryginału) | kształt dymka |
| Szerokość maksymalna | obszar bezpieczny: 90% szerokości ekranu, także gdy marginesy stylu są węższe (r7); wiersz musi mieścić się bez zawijania libass (przy zawijaniu stylu — `\q2` lub odpowiednik dla tego zdarzenia) | ekran / ramka `\clip` / sąsiedzi | jw. | pas / ekran | dymek |
| Preferowana liczba wierszy | 1, dopóki mieści się z marginesem; 2, gdy szeroko; 3 tylko w ratunku (r6, r7) | 1 | najmniejsza, która mieści się w polu bez nadmiernego zmniejszenia; liczba wierszy oryginału nie wiąże (r2) | 1 ze zmniejszeniem, potem 2 (r1) | tyle, ile wypełnia kształt |
| Kształt dwóch wierszy | krótsza góra (wyraźnie), bez skrajnej nierównowagi | — | zrównoważony; proporcje oryginału tylko wtedy, gdy nie dają klepsydry ani poszarpania (s10, s29) | jak dialog | wypukły (środek najszerszy) |
| Zmniejszanie / ściskanie | nie | tak; zmniejszenie z zachowaniem proporcji przed ściśnięciem (q15) | jw. | tak, zmniejszenie, żeby zmieścić się w pasie / na ekranie (s17, s18, s28), przed dodaniem wiersza | tak (rozmiar czcionki) |
| Dzielenie wyrazów | nie | nie | nie | nie | tak (miękki dywiz) |

Nienaruszalne dla każdego pola: wyraz (grafem) nigdy nie jest rozcięty bez jawnego dywizu, treść się nie zmienia, położenie, ruch, obrót, maska, kolory szyldu zostają, litery szyldu nie rosną ponad oryginał, rysunki i karaoke bez zmian (visual-quality §2.1).

**Dzielenie wyrazów (pole dymka MangaShift; AniShift nie dzieli — także w szyldach, decyzja właściciela 20.10: „chyba nie ma sensu”):** miejsca podziału z polskich wzorców przenoszenia TeX/LibreOffice (Python: `pyphen` `pl_PL`; TypeScript: Hyphenopoly albo `hyphen` z wzorcami `pl`) jako miękkie łączniki U+00AD, które Pretext traktuje jako dozwolone cięcie z widocznym „-”. Wyjątki: słowa pisane wielką literą i obce (wzorce polskie dzielą je źle: „Ice-bla-de”, „Shi-no-miya”) tylko w ratunku; wyraz z łącznikiem łamany na istniejącym łączniku z powtórzeniem łącznika na początku nowego wiersza („przyczynowo- / -skutkowe”). Podział wyrazu to szkoda ważona, zawsze droższa niż cięcie między słowami.

### 3.3 Granica rdzenia

- **Rdzeń** (jeden moduł): analiza przerw (`anishift/text/gaps.py` — dziś tylko na odrzuconej gałęzi `20-line-breaking`; przenieść klasy przerw po weryfikacji, bez wag i kosztu z v1.9; ta sama analiza dla dialogu i szyldu), generowanie kandydatów (cięcia × skala), pomiar przez wstrzykniętą funkcję (`geometry.measure_text` z tagami, które trafią na dany wiersz; dla SRT bez profilu liczba grafemów), ocena szkód, poziomy ratunku. Wynik: wiersze, skala `fx`/`fy`, stopnie szkód, poziom ratunku, flagi do raportu.
- **Warstwa sceny** (zostaje w `fitting.py`): obiekty złożone z wielu zdarzeń (ten sam tekst nakładający się w czasie albo z przerwą ≤ 500 ms), ekran, ramka `\clip`, sąsiedzi i kolizje — filtruje posortowanych kandydatów rdzenia. Prostokąt obróconego tekstu to obwiednia obróconych rogów, także dla sąsiadów (`\frz`; `\frx`/`\fry` jako przybliżenie raportowane).
- **Poza rdzeniem**: zdarzenia karaoke (`\k`, `\ko`, `\kf`) i rysunki — bez zmiany układu.
- **Wiersze autorskie**: liczą się tylko wiersze z tekstem; puste wiersze autorskie (odstępy w listach) wracają na swoje miejsca. Lista, której przekład ma tyle samo pozycji co źródło, dzieli się na granicach pozycji.
- **MangaShift**: współdzieli analizę przerw i reguły (np. jako dane), nie kod wyboru — tam układ zapada w TypeScript, bo tylko tam pomiar zgadza się z rysowaniem.
- Po wdrożeniu znikają: oba rankingi w `linebreak.py` (publiczne `split_line`, `layout_dialogue`, `split_for_layout`, `split_lines` stają się cienkimi wejściami do rdzenia albo znikają), pomiar Arialem `_fit_sign` z podłogą 0,72, warianty K0–D, leksykon U5.

## 4. Co jest dobre, a co złe — stopnie, nie progi

Każdy możliwy układ (kandydat) dostaje stopień każdej szkody od 0 (brak) do 1 (pełna), a powyżej 1 dalej rośnie tam, gdzie zaznaczono. Stopnie zmieniają się płynnie: żadna szkoda nie skacze na jednej granicy znaków. Wygrywa kandydat o najmniejszej ważonej sumie szkód. Te same szkody obowiązują wszystkie pola; pole zmienia tylko punkty odniesienia.

### 4.1 Za długi wiersz

Jak bardzo wiersz męczy oko i zasłania obraz. Miarą jest **szerokość wiersza na ekranie** (prawdziwa czcionka, ułamek szerokości skryptu `PlayResX`), bo tak ocenia właściciel: „jeżeli da się zrobić w jednolinijkowcu i nie jest do samych krawędzi — jednolinijkowiec” (ankieta 19.10). Liczba znaków tego nie oddaje: pliki mają różne rozmiary czcionki dialogu, a ta sama liczba znaków to od 0,53 do 0,85 szerokości.

- **Druga miara: ilość do przeczytania (znaki).** Sama szerokość przepuściłaby 67–68-znakowy jeden wiersz w pliku z drobną czcionką (0,77 szerokości; sprawdzone w przeglądzie 19.10) — to błąd U5. Dlatego szkoda długości = większa z dwóch: szerokościowej i znakowej. Obie mają kolano z tej samej ankiety: jeden wiersz przy 56 znakach przeszedł (q17), przy 57 nie (q11). W plikach z czcionką jak w ankiecie obie miary dają ten sam wynik; w plikach z drobną czcionką decyduje znakowa.
- Ankieta: jeden wiersz wygrał przy szerokościach 0,39–0,76 (najszerszy, 0,76, właściciel nazwał granicą: „jeszcze z dwie, cztery litery po bokach i byłoby za dużo”), przegrał przy 0,80 i 0,85.
- Szkoda rośnie płynnie: bliska zera do ok. 0,55, rośnie, wyraźnie ostrzej od ok. 0,76; przekroczenie szerokości maksymalnej pola (dialog `\q2`: 90% ekranu; inaczej szerokość między marginesami) wyklucza kandydata poza ratunkiem.
- Dla SRT bez profilu: znaki przeliczone na szerokość współczynnikiem z kalibracji (ok. 0,0136 ekranu na znak przy typowym rozmiarze), jako przybliżenie.
- 42 znaki pozostają punktem odniesienia dla czytelnika, nie granicą: przy czcionce właściciela 42 znaki to ok. 0,55–0,6 szerokości, czyli „wygodny jeden wiersz”.

### 4.2 Złe miejsce cięcia

Jak bardzo cięcie rozrywa sens. Stopień zależy od klasy przerwy między wyrazami (`anishift/text/gaps.py`): koniec zdania < przecinek, myślnik, dwukropek < przed spójnikiem zdania < przed przyimkiem / między frazami < wewnątrz frazy < rozerwanie związku chronionego < jednoliterowy wyraz na końcu wiersza. Związki chronione mogą być rozerwane tylko w ratunku i są raportowane:

- przyimek | rzeczownik, „nie” | czasownik, „się” przy czasowniku, imię | nazwisko, liczba | rzeczownik, liczba | jednostka, liczba z separatorem tysięcy („10 000”), utarty zwrot (`idioms.txt`);
- **cięcie wewnątrz krótkiego cytatu** (cudzysłów „…” mieszczący się w jednym wierszu: d16, d18).

**Silna szkoda ważona (nie poziom): przymiotnik | rzeczownik w zgodzie** (także po rzeczowniku: „przyjęciu / powitalnym”) — z Morfeusza 2: para analiz przymiotnik/imiesłów przymiotnikowy + rzeczownik (nie przymiotnik + przymiotnik) o tej samej liczbie i wspólnym przypadku i rodzaju, żadne słowo bez odczytania czasownikowego, lewe słowo bez interpunkcji na końcu. Nie może być poziomem, bo właściciel sam wybrał takie cięcie, gdy jeden wiersz był za szeroki (q11 „we wszystkie / ciągi”; Morfeusz uznaje parę za zgodną). Pomiar 19.10: flaga przy 1% cięć zawodowców NF+AMZN (6 z 601), przy ok. 10% pozostałych przerw.

Zakazane zawsze (nienaruszalne): **wiersz zaczynający się od pauzy wtrącenia** (— / –), która nie jest myślnikiem mówcy — czytelnik bierze ją za kwestię drugiej osoby (d13, d14). Wymuszone granice: znaczniki punktów listy „(1)”, „(2)”… zaczynają wiersz, gdy punkty mieszczą się w swoich wierszach (d12).

**Granica stylu** (właściciel 20.10, s09): zmiana wielkości lub kroju między słowami (`s`, `n`, ``, `scx`/`scy`) oznacza granicę elementów. Jeśli w źródle był tam koniec wiersza — granica wymuszona; w przeciwnym razie silna preferencja cięcia w tym miejscu i szkoda za sklejenie tekstu o różnych wielkościach w jednym wierszu.

Słowo otwierające frazę na końcu wiersza („który”, „że”, „żeby”, spójnik) jest szkodą ważoną. Przysłówek stopnia oderwany od słowa, które określa („tak / bardzo”, „zbyt / długo”), jest szkodą ważoną (t02).

### 4.3 Nierówne wiersze i kształt

- **nierównowaga** — różnica długości wierszy względem całości; mała różnica prawie nic nie kosztuje, skrajna (jedno-dwa słowa nad długim wierszem albo odwrotnie) kosztuje dużo;
- **odwrócona piramida** (dialog) — górny wiersz dłuższy od dolnego: wyraźna szkoda. Ankieta: krótsza góra wygrała z cięciem po kropce („Gdzie się podziała / moja stara pianka? Przecież tu leżała.” wobec „…pianka? / Przecież tu leżała.”) i z symetrycznym odbiciem (21/34 wobec 34/21) — u właściciela ta preferencja jest silniejsza niż u zawodowców. Nie usprawiedliwia jednak skrajnej nierównowagi (17/50 przegrało z 27/40) ani rozerwania związku chronionego (d15);
- **sierota** — jedno słowo samo w wierszu, górnym albo dolnym, także ze znakiem interpunkcyjnym („Nie!”, „Tak,”, „O, / naprawdę?”). Zasada właściciela (19.10: „jak 1 słowo to się nie opłaca”, „albo 1 słowo [i] znak w linii” — odczytane jako słowo z interpunkcją; do potwierdzenia w ankiecie): układ z wierszem jednowyrazowym przegrywa z jednym wierszem, dopóki jeden wiersz mieści się w szerokości maksymalnej pola; gdy się nie mieści, rdzeń szuka innego cięcia, a sierota zostaje tylko w ratunku. Wyjątek: wiersz mówcy w kwestii dwóch osób („– Tak.”) nie jest sierotą.

### 4.4 Interpunkcja a równowaga

Cięcie po interpunkcji jest lepsze od cięcia bez niej, ale nie za każdą cenę. Kurs wymiany („ile znaków nierównowagi wart jest przecinek, kropka, myślnik”) pochodzi z wyborów zawodowych polskich tłumaczy (Netflix, Amazon, Crunchyroll; model warunkowego wyboru cięcia w `experiments/lb-research/opus55/`, gdzie równowaga jest najsilniejszym czynnikiem) i z ankiety właściciela (§5.4; przypadek „Wręcz przeciwnie, / te plotki…” 17/49 wobec 29/38 trafia do ankiety, bo dotąd był tylko jego pytaniem).

Pomiar 19.10 (`scratchpad/v4-agree`, model warunkowego wyboru na 1668 kwestiach dwuwierszowych, kurs liczony wprost tam, gdzie istnieje cięcie zrównoważone z różnicą ≤ 6 znaków):

| Granica | Do jakiej różnicy długości wierszy wygrywa z cięciem zrównoważonym (NF+AMZN) |
| --- | --- |
| koniec zdania | ok. 25–30 znaków |
| przecinek | ok. 20 znaków (21–25: pół na pół; ≥ 31: 0 z 4) |
| przed spójnikiem | ok. 10–20 znaków |

- Kara za nierównowagę lepiej pasuje liczona w znakach niż w proporcji i rośnie szybciej niż liniowo.
- Przy przecinku dającym różnicę ≥ 25 znaków, gdy istnieje cięcie zrównoważone, zawodowcy wybrali cięcie zrównoważone 41 razy na 47, przy ≥ 31 znakach (jak 17/49) 15 na 15.
- Zawodowcy **nie** preferują krótszej góry (51% kwestii); preferencja „górna krótsza, dolna dłuższa” pochodzi od właściciela („oczywiście, że są tylko miękkie wymagania”), więc jest lekka i nigdy nie usprawiedliwia skrajnej nierównowagi.

### 4.7 Czego listy słów nie widzą

Ślepa ocena 19.10: złe cięcia algorytmów to głównie przymiotnik | rzeczownik, terminy i frazeologizmy; listy słów z `08` wykryły 5 z 31. Źródło wiedzy o składni to decyzja z pomiarem: listy + morfologia (Morfeusz 2: zgoda przymiotnika z rzeczownikiem w przypadku, liczbie i rodzaju, rozpoznanie „się” przy czasowniku; zgoda właściciela 19.10 pod warunkiem, że poprawia całość — wchodzi tylko, jeśli ślepa ocena (§7.3) z morfologią ma mniej złych cięć niż bez niej, a katalog i ankieta nie tracą; `morfeusz2` 1.99.15 uruchomiony 19.10 na Pythonie 3.14 w środowisku tymczasowym; słownik `pl.sgjp.sgjp-2026.06.01` na licencji typu BSD z prawem redystrybucji; analiza bez dezambiguacji, więc cecha to „istnieje zgodna para analiz”). Parser spaCy odpada (modele GPL-3.0, wcześniej gorszy na danych). Morfologia wchodzi tylko, jeśli obniża odsetek złych cięć w ślepej ocenie (§7.3), i zawsze z listami jako źródłem awaryjnym.

### 4.5 Dodatkowy wiersz

Każdy wiersz ponad preferowaną liczbę pola zasłania obraz i dodaje skok oka. Dla dialogu: drugi wiersz ma małą szkodę (krótka kwestia w jednym wierszu wygrywa, długa w dwóch), trzeci dużą (tylko ratunek). Dla napisu pobocznego: zmiana liczby wierszy względem oryginału.

### 4.6 Napisy poboczne: rozmiar i miejsce

- **zniekształcenie** — ściśnięcie liter (`\fscx` względem `\fscy`); rośnie bez nasycenia (1,6% nigdy nie kosztuje tyle co 50%); poniżej skali minimalnej pola przechodzi do poziomu „unikane za wszelką cenę”;
- **za mały** — zmniejszenie, gdy obok było miejsce; wysokość liter w pikselach ekranu, czytelność przy x2 (punkty odniesienia z visual-quality §12: kara od ok. 30 px, pełna przy ok. 16 px — do potwierdzenia przez właściciela);
- **wystaje** — ponad ramkę `\clip` (ostrzej) albo szerokość angielskiego tekstu (łagodniej, wolne tło);
- **wzrost w pionie** — dodatkowy wiersz szyldu, gdy pole ma znaną wysokość;
- **poza ekranem / nachodzi na inny napis bardziej niż oryginał** — filtr warstwy sceny; tylko w ratunku, zawsze raportowane.

Ankieta (pyt. 15, etykieta „Sekretarz Samorządu Uczniowskiego Akademii Shuchiin” na wąskiej tablicy): zmniejszenie z zachowaniem proporcji do szerokości oryginału (C) > ściśnięcie w poziomie (B, dopuszczalne) > wystawanie poza tablicę (A) i dwa wiersze wychodzące poza tablicę w pionie (D). Krótki szyld (pyt. 5): jeden wiersz. Wniosek: dla szyldu zmniejszenie ma mniejszą szkodę niż ściśnięcie tej samej skali, a każde wyjście poza ramkę ma szkodę większą niż oba; dodatkowy wiersz szyldu jest dopuszczalny tylko wtedy, gdy mieści się w wysokości pola.

Środków, których nie używamy, nie zmienia ta specyfikacja: bez `\fsp`, bez zmiany czcionki szyldu, bez przesuwania, bez skracania tekstu.

## 5. Jak rdzeń wybiera

### 5.1 Przestrzeń stanów

Kandydaci to wszystkie podziały widocznego tekstu na 1…K wierszy w dozwolonych przerwach (spacje, myślniki mówców, autorskie `\N` jako silna preferencja tylko tam, gdzie pole tak mówi) oraz, dla pól, które na to pozwalają, skale rozmiaru i ściśnięcia z dyskretnej siatki. Bez zachłannego cięcia: dla dialogu (K ≤ 3) przegląd pełny; dla pól z wieloma wierszami (szyldy, listy: s13 ma 7, s29 ok. 12) programowanie dynamiczne po granicach wierszy z tą samą funkcją oceny (szkody są sumą po wierszach i cięciach, więc DP daje to samo optimum co pełny przegląd; kształt wobec wzorca proporcji liczony per wiersz). Pomiar wiersza w pamięci podręcznej po (zdarzenie, tekst wiersza, skala).

### 5.2 Ratunek

Gdy żaden kandydat nie spełnia reguł nienaruszalnych i unikanych za wszelką cenę, rdzeń kolejno dopuszcza: rozerwanie związku chronionego, dodatkowy wiersz ponad maksimum pola, wyjście poza pole; zawsze wybiera najmniejsze naruszenie i zapisuje je w raporcie przebiegu. Słowo nie jest rozcinane nigdy (poza dywizem w polu, które na to pozwala).

### 5.3 Kalibracja i dowód spójności

Funkcja oceny jest ważoną sumą stopni szkód, więc każda preferencja „układ X lepszy od Y” to liniowa nierówność względem wag. Zbiór nierówności tworzą:

1. **katalog** (§6) — pierwszy z dopuszczalnych układów każdego przypadku ma wygrać ze wszystkimi niedopuszczalnymi kandydatami tego przypadku (pozostałe dopuszczalne nie są ograniczane); kandydaci szersi niż pole nie biorą udziału;
2. **preferencje parowe właściciela** — tylko jego jawne wybory między wariantami, które widział. Rejestr z 19.10 (przegląd wszystkich jego wiadomości z sesji 17–19.10) znalazł **dwie** pewne decyzje parowe (dwa wiersze lepsze od trzech na Kaguyi; algorytm `u6` lepszy od `u5` jako całość). Rekomendacje przypadków `fuzzy-spec/cases` 01–36, galerie g01–g30, „Wręcz przeciwnie” 29/38 i „Minato” to rekomendacje agentów albo pytania właściciela, nie jego wybory — nie są kotwicami. Brakujące preferencje zbiera **ankieta** (§5.4);
3. **wybory zawodowców** jako prior dla wzajemnych proporcji szkód cięcia i równowagi (miękko: dopuszczalne naruszenia z karą).

Narzędzie kalibracji rozwiązuje ten układ (program liniowy z marginesem) z wymaganiami:

- filtry nienaruszalne i szerokość pola usuwają kandydatów przed kalibracją (nie są wagami);
- ograniczenia monotoniczności: kolejność klas przerw z §4.2 jest kolejnością wag (cięcie wewnątrz frazy nigdy nie tańsze niż po przecinku; każda klasa ma wagę dodatnią), szkoda długości nie maleje z szerokością;
- odpowiedzi „oba dobre” z ankiety (q09, q16, q17) to pary miękkie z małym zapasem, nie twarde;
- ocena zawsze w **pełnej** przestrzeni kandydatów: najlepszy kandydat przypadku musi należeć do zbioru dopuszczalnych (dla pytań ankiety: wybór właściciela albo układ, który recenzent uzna za co najmniej równy — taki układ dopisuje się do zbioru jawnie);
- test z pominięciem jednego przypadku (każdy przypadek katalogu i ankiety liczony przy wagach z pozostałych) raportowany obok wyniku treningowego;
- wrażliwość ±10% każdej wagi policzona i raportowana (nie jest warunkiem wykonalności — zob. niżej).

Wynik:

- **wykonalny** → wagi z największym marginesem; zapisane w kodzie jako nazwane stałe z odwołaniem do raportu kalibracji;
- **niewykonalny** → lista najmniejszego zbioru sprzecznych przypadków; idzie do właściciela jako pytanie z obrazami, nigdy jako łatka.

Wrażliwość (zmiana 19.10 po kalibracji): wymóg „przy wagach ±10% żaden przypadek nie zmienia wyniku” odpada. Granica właściciela przy długości jest z natury ostra (jeden wiersz 0,77 szerokości wygrywa, 0,80 przegrywa — d28, q11), więc żaden zestaw wag nie utrzyma przypadków przy kolanie przy dowolnej zmianie o 10%; wymóg dawał niewykonalność bez wartości dla właściciela. Kalibracja wymaga marginesu (twardego dla katalogu i ankiety, miękkiego dla odpowiedzi „oba dobre” i zawodowców), a wrażliwość ±10% i test z pominięciem jednego przypadku są raportowane z listą przypadków przy kolanie.

**Prototyp 19.10** (`scratchpad/v4-cal/cal2.py`; cechy: szerokość z węzłami 0,55–0,90, klasy przerw `gaps()`, nierównowaga i dłuższa góra w szerokości, drugi i trzeci wiersz, sierota, związki chronione, pauza na początku wiersza, cytat, zgoda z Morfeusza, słowo otwierające na końcu wiersza; program liniowy `highs`):

| Trening | Test | Wynik |
| --- | --- | --- |
| ankieta (18 par dialogowych) | — | 18/18 spełnione jednym zestawem wag |
| ankieta + zawodowcy NF+AMZN+CR (6441 par miękkich) | katalog dialogów (26 oznaczonych, nieuczony) | 19/26; błędy: d09, d11, d12, d15, d16, d18, d25 |
| ankieta + zawodowcy + katalog | katalog | 25/26; ankieta nadal 18/18; d15 wymaga ochrony zgody przymiotnika (wpisane w §4.2) |

Czego prototyp **nie** dowodzi (przegląd 19.10): „18/18” znaczy tylko, że wybór właściciela wygrywa z pokazanym przegranym — w pełnej przestrzeni najlepszy kandydat różnił się od wyboru w 4 pytaniach (q06 „na nasz / temat”, q14 „że to ty / trafiłaś”, q10 i q19 jeden wiersz, w q19 0,78 — za granicą); katalog prototypu odbiegał od §6 (d06, d09), więc względem §6 wynik to 24/27; prototyp nie miał filtra szerokości ani monotoniczności, a wrażliwości nie liczono. Prototyp pokazuje tylko kierunek: cechy szerokości, kształtu i klas przerw wystarczają do pogodzenia ankiety z praktyką zawodowców bez sprzeczności. Dowód spójności daje dopiero narzędzie kalibracji z wymaganiami powyżej, uruchomione na ostatecznym katalogu.

### 5.4 Ankieta preferencji właściciela

Gust właściciela jest jedynym źródłem tam, gdzie badania nie dają odpowiedzi (§4.1, §4.3, §4.6). Zbieramy go raz, krótko, przed kalibracją: około 20 pytań „który wariant czyta się lepiej”, każdy z dwoma (najwyżej trzema) wariantami tego samego tekstu na prawdziwej klatce, z czcionką właściciela, bez opisów technicznych i bez liczb znaków na obrazie. Osie pytań:

| Oś | Co rozstrzyga | Przykładowe pary |
| --- | --- | --- |
| Długość: jeden wiersz czy dwa, przy dobrym cięciu | kształt szkody „za długi” | ta sama kwestia przy ok. 32, 38, 44, 48, 52, 56, 60 znakach: jeden wiersz vs najlepsze cięcie |
| Długość przy słabym cięciu | jak długość waży wobec złego miejsca cięcia | ok. 48 i 55 znaków: jeden wiersz vs cięcie wewnątrz frazy |
| Krótkie kwestie w dwóch wierszach („dwulinijkowce, nawet jeżeli są małe”) | czy drugi wiersz ma koszt przy krótkim tekście | ok. 28–36 znaków: jeden wiersz vs dwa krótkie |
| Interpunkcja a równowaga | kurs wymiany przecinka na równowagę | przecinek dający 17/49 vs cięcie bliżej środka; przecinek 22/40 vs 30/32 |
| Kształt: krótsza góra czy dłuższa | szkoda „odwrócona piramida” | dwa zdania: długie + krótkie (cięcie po kropce, dłuższa góra) vs cięcie w pierwszym zdaniu (krótsza góra) |
| Trzy wiersze | potwierdzenie ratunku | długa kwestia: dwa długie wiersze vs trzy krótsze |
| Szyld: dłuższy przekład na wąskiej tablicy | zniekształcenie vs zmniejszenie vs dwa wiersze vs wystawanie | jeden szyld w 3–4 wariantach |
| Szyld krótki | czy krótki szyld dzielić | jeden wiersz vs dwa |

Odpowiedzi trafiają do rejestru preferencji parowych z obrazem i dokładnymi układami. Pytanie, na które właściciel odpowie „bez różnicy”, zapisujemy jako równoważność (oba warianty dopuszczalne), nie jako preferencję.

**Wynik ankiety (19.10, obrazy i układy: `workspace/.quality/experiments/v4-quiz/`, `quiz.json`).** Szerokość = ułamek szerokości ekranu, prawdziwa czcionka.

| Pyt. | Oś | Wybór właściciela | Przegrany | Komentarz właściciela |
| --- | --- | --- | --- | --- |
| 1 | długość | jeden wiersz 0,67 | 22/26 zn. po przecinku | „dużo miejsca po bokach” |
| 2 | długość | jeden wiersz 0,53 | 16/21 zn. | |
| 3 | długość | „Zjadłeś obiad sam jak palec, / a potem…” | jeden wiersz 0,85 | „prawie cała szerokość, trzeba latać wzrokiem” |
| 4 | sierota | jeden wiersz 0,74 | „myślę, / że on może…” | „u góry jedno słowo, brzydko wygląda” |
| 5 | krótki szyld | jeden wiersz | dwa wiersze | „bardziej pasuje do obrazu” |
| 6 | przecinek | „Wręcz przeciwnie, te plotki / na nasz temat…” 27/40 | 17/50 po przecinku | „harmonijniej, bez dysproporcji” |
| 7 | sierota | jeden wiersz 0,68 | „… wszystkiego, / co?” | „jedna rzecz pod spodem — w ogóle złe” |
| 8 | krótka | jeden wiersz | 13/16 | |
| 9 | długość | jeden wiersz 0,69 | 23/28 po przecinku | „oba dobre, skłaniam się ku jednemu, margines akceptowalny” |
| 10 | kształt | 21/34 | 34/21 | „góra mniejsza, dół większy — harmonia” |
| 11 | długość, słabe cięcie | „Magia ingerująca we wszystkie / ciągi przyczynowo-skutkowe.” | jeden wiersz 0,80 | „strasznie długi, lepiej podwójnie” |
| 12 | długość | jeden wiersz 0,44 | 15/16 | |
| 13 | trzy wiersze | dwa wiersze 0,70/0,83 | trzy wiersze | „trzylinijkowiec źle wygląda; góra powinna być mniejsza” |
| 14 | przecinek | „Z kilometra było widać, / że to ty…” 23/33 | 29/27 „że to / ty” | „u góry mniej, na dole więcej” |
| 15 | szyld na wąskiej tablicy | C: zmniejszony do szerokości oryginału | B ściśnięty (też dopuszczalny), A wystaje, D dwa wiersze poza tablicą | „C — lepszy odstęp dookoła, naturalniej” |
| 16 | przecinek | „Co jest złego w tym, że ktoś / naprawdę…” 28/33 | 20/41 po przecinku | „oba poprawne, B bardziej symetryczne” |
| 17 | długość | jeden wiersz 0,76 | 25/30 po przecinku | „granica — jeszcze dwie, cztery litery i za dużo” |
| 18 | długość | jeden wiersz 0,64 | 20/23 | |
| 19 | kształt | „Gdzie się podziała / moja stara pianka? Przecież tu leżała.” 18/38 | 37/19 po kropce | „dobry podział słownictwa” |
| 20 | długość, słabe cięcie | jeden wiersz 0,68 | 26/21 między przymiotnikami | „margines po obu stronach” |

**Runda 2 (19.10, `v4-quiz/round2/`, `round2.json`):**

| Pyt. | Oś | Wybór właściciela | Przegrany | Komentarz właściciela |
| --- | --- | --- | --- | --- |
| r1 | piosenka w pasie | jeden wiersz zmniejszony do 83% | dwa wiersze zmniejszone do 60%; dwa w pełnym rozmiarze zjeżdżające z pasa | „muzyka powinna być w jednej linijce” |
| r2 | krótki napis dwuwierszowy w oryginale („KAŻDE / ZDOBYCZĄ”) | bez różnicy, skłania się ku jednemu wierszowi | — | „krótkie zdanie, może być w jednej linii” |
| r3 | zgoda przymiotnika a krótsza góra | „Czy cosplay na przyjęciu powitalnym / jest naprawdę konieczny?” | „…przyjęciu / powitalnym jest…” | „przyjęcie powitalne to jedna sentencja” |
| r4 | pauza na końcu wiersza a przecinek | „Jeśli to prawdziwa miłość, przyjmę ją — / nawet za cenę wyrzucenia ze szkoły.” (39/35) | „…miłość, / przyjmę ją — nawet…” (26/49) | |
| r5 | długa kwestia u góry ekranu | pytanie niejasne dla właściciela; rozstrzyga zasada z q3 (jeden wiersz 0,86 szerokości → dwa wiersze) | | „górny może być trochę dłuższy od dolnego, ale przy strasznie dużej proporcji wykluczone — złota proporcja” |
| r6 | dwa szerokie a trzy wiersze | „…czterdzieści procent wyparcia, / a na dobitkę permanentny brak snu.” (dwa) | trzy wiersze po przecinkach | |
| r7 | jw. | dwa wiersze, choć dolny (1713 px) wychodzi poza marginesy stylu (pole 1470 px), mieszcząc się na ekranie | trzy wiersze | „trzykolumnowe to przesada” |

**Runda 3 (19.10, `v4-quiz/round3/`) — rozstrzyga sprzeczności kalibracji:** t01 (d24) „…czterdzieści procent / wyparcia, a na dobitkę…” (53/44) > „…wyparcia, / a na dobitkę…” (63/34) — równowaga wygrywa ze słabym cięciem wewnątrz frazy rzeczownikowej; t02 (d06) „…dzisiaj / tak bardzo chciałem…” > „…dzisiaj tak / bardzo…” — przysłówek stopnia zostaje ze słowem, które określa (§4.2). Korekta r1: jeden wiersz piosenki w pełnym rozmiarze mieści się (0,69 ekranu; wcześniejsza notatka 2116 px była błędem pomiaru czcionką zastępczą); wybór właściciela bez zmian.

Wnioski: (1) piosenka — jeden wiersz (w pełnym rozmiarze, a gdy się nie mieści — ze zmniejszeniem) przed dodaniem wiersza; (2) liczba wierszy szyldu nie jest wiązana z oryginałem — krótki tekst w jednym wierszu (zamyka otwarte pole w §3.2); (3) zgoda przymiotnika z rzeczownikiem waży więcej niż odwrócona piramida; (4) piramida nie jest bezwzględna — przy dobrej granicy (pauza na końcu wiersza) równowaga 39/35 wygrywa z przecinkiem 26/49; (5) trzeci wiersz dialogu ma szkodę większą niż szeroki dolny wiersz, a szerokością maksymalną dialogu jest obszar bezpieczny ekranu (90% szerokości), nie marginesy stylu.

Uwaga właściciela o wielkości napisów: układ zapisujemy względem rozdzielczości skryptu, a skala napisów w mpv powiększa wszystko proporcjonalnie, więc marginesy zostają; zawijania zależnego od rozmiaru nie robimy (libass tnie bez sensu zdania). Właściciel: „chyba nie warto komplikować”.

## 6. Katalog przypadków

Każdy przypadek ma **zbiór dopuszczalnych układów** i **zakazy**. Wynik rdzenia musi należeć do zbioru dopuszczalnych; w kalibracji (§5.3) każdy dopuszczalny ma wygrać ze wszystkimi niedopuszczalnymi. Oznaczenie **[A]** — który z dopuszczalnych wygrywa, rozstrzyga ankieta (§5.4); do tego czasu zbiór jest szerszy, ale zakazy obowiązują już teraz. Obrazy stanu wejściowego: `workspace/.quality/experiments/v4-hard/<id>.png`, dane: `cases.json`. Propozycje orkiestratora z 19.10, do przeglądu przez dwóch recenzentów i do korekty po ankiecie.

### 6.1 Dialogi (zestaw trudny)

| Id | Tekst (znaki) | Stan wejściowy | Dopuszczalne | Zakazane |
| --- | --- | --- | --- | --- |
| d01 | Bo... chcę zobaczyć twój paskudny, klauni ryj. (46) | Bo... / chcę… | jeden wiersz; „Bo... chcę zobaczyć / twój paskudny, klauni ryj.” [A] | sierota „Bo...” |
| d02 | wiem, że ty też jesteś dobrym chłopakiem, Iori. (47) | wiem, / że… | jeden wiersz; „wiem, że ty też jesteś / dobrym chłopakiem, Iori.” [A] | sierota „wiem,” |
| d03 | człowiek dałby się pokroić za zimne piwko, co? (46) | … piwko, / co? | jeden wiersz; „człowiek dałby się pokroić / za zimne piwko, co?” [A] | sierota „co?” |
| d04 | Każdy ma dwie minuty na autoprezentację, jasne? (47) | … / jasne? | jeden wiersz; „Każdy ma dwie minuty / na autoprezentację, jasne?” [A] | sierota „jasne?” |
| d05 | Po tej dwójce wszystkiego się można spodziewać! (47) | … się / można… | jeden wiersz; „Po tej dwójce wszystkiego / się można spodziewać!” [A] | — |
| d06 | Niech to szlag! Akurat dzisiaj tak bardzo chciałem porozmawiać z Shinomyią! (75) | … tak / bardzo… | „Niech to szlag! Akurat dzisiaj / tak bardzo chciałem porozmawiać z Shinomyią!” | „tak / bardzo”; jeden wiersz; dłuższa góra „…dzisiaj tak bardzo / chciałem…” |
| d07 | Kąt powinien wynosić sto trzydzieści osiem stopni. (50) | … sto / trzydzieści… | „Kąt powinien wynosić / sto trzydzieści osiem stopni.”; jeden wiersz [A] | rozcięty liczebnik złożony |
| d08 | Posiadająca ponad tysiąc spółek zależnych Grupa Shinomiya to jeden z Wielkiej Czwórki — największych konglomeratów Japonii, (123) | 60/62 | dwa wiersze na granicy frazy, jeśli mieszczą się w polu (q13: dwa szerokie > trzy); inaczej „Posiadająca ponad tysiąc spółek zależnych / Grupa Shinomiya to jeden z Wielkiej Czwórki — / największych konglomeratów Japonii,” | wiersz zaczynający się od pauzy wtrącenia; wiersz poza polem |
| d09 | Oto przed wami uparty osobnik, który do tej pory z uporem maniaka twierdził, że smartfon nie jest mu do niczego potrzebny. (122) | 57/64, libass zawija do 4 | dwa albo trzy wiersze, żaden nie zawijany przez libass [A] | „z uporem / maniaka”; układ, który libass zawija sam |
| d10 | Pozwoli mi to również w pełni legalnie i w usprawiedliwiony sposób uwiecznić cyfrowo tę niewypowiedzianie słodką istotę! (120) | 59/60 | jedyny układ dwuwierszowy w polu: „Pozwoli mi to również w pełni legalnie i w usprawiedliwiony / sposób uwiecznić cyfrowo tę niewypowiedzianie słodką istotę!” (0,835/0,864) — wygrywa z trzema wierszami (trzeci wiersz = ratunek; r6, r7: „trzy linie to przesada”); decyzja orkiestratora 19.10 wg zasad właściciela, do potwierdzenia | „słodką / istotę”, „niewypowiedzianie / słodką”; trzy wiersze; wiersz poza polem (zakaz „uwiecznić / cyfrowo” był regułą orkiestratora bez potwierdzenia właściciela — zdjęty 19.10) |
| d11 | Zorganizujmy więc imprezę świąteczną dla całego samorządu! Udostępnię swoją chatę na tę zacną okoliczność! (106) | 58/47 | „…samorządu! / Udostępnię…”; trzy wiersze [A: kształt, trzy wiersze] | cięcie wewnątrz frazy przy dostępnej granicy zdania |
| d12 | (1) W SPRAWIE RELACJI Z PRZEWODNICZĄCYM (2) W SPRAWIE STUDIÓW ZA GRANICĄ (3) W SPRAWIE TEGO DOROSŁEGO POCAŁUNKU (111) | 2 wiersze + zawinięcie libass | trzy wiersze, każdy od znacznika „(n)” | cięcie wewnątrz punktu listy |
| d13 | Jeśli to prawdziwa miłość, przyjmę ją — nawet za cenę wyrzucenia ze szkoły. (75) | … ją / — nawet… | „Jeśli to prawdziwa miłość, przyjmę ją — / nawet za cenę wyrzucenia ze szkoły.” (r4: wygrało z „…miłość, / przyjmę ją — nawet…”) | wiersz zaczynający się od pauzy wtrącenia (wygląda jak drugi mówca) |
| d14 | a dzięki tej nienagannej postawie — mimo że przyszedł z zewnątrz — (66) | … / — mimo… — | „a dzięki tej nienagannej postawie — / mimo że przyszedł z zewnątrz —” | jw. |
| d15 | Czy cosplay na przyjęciu powitalnym jest naprawdę konieczny? (60) | … przyjęciu / powitalnym… | „Czy cosplay na przyjęciu powitalnym / jest naprawdę konieczny?” (r3) | przymiotnik \| rzeczownik; „Czy cosplay /” |
| d16 | W następnym odcinku „The Iceblade Sorcerer Shall Rule the World”: (65) | … „The / Iceblade… | „W następnym odcinku / „The Iceblade Sorcerer Shall Rule the World”:” | cięcie wewnątrz tytułu w cudzysłowie, gdy mieści się w wierszu |
| d17 | W relacjach damsko-męskich zasada „Kto pierwszy się zakocha, ten przegrywa” to absolutny dogmat! (96) | … się / zakocha… | „W relacjach damsko-męskich zasada / „Kto pierwszy się zakocha, ten przegrywa” to absolutny dogmat!” (r7: dwa > trzy, choć dolny wychodzi poza marginesy stylu) | „się / zakocha”; cięcie wewnątrz cytatu, gdy cytat mieści się w wierszu |
| d18 | Co tam jeszcze jest? „Szum rzecznego nurtu”... „Podwodny szmer”... (66) | „Szum / rzecznego… | „Co tam jeszcze jest? / „Szum rzecznego nurtu”... „Podwodny szmer”...” | cięcie wewnątrz krótkiego cytatu |
| d19 | Skąd aż tylu ludzi, którzy już TO zrobili?! (43) | Skąd / … | jeden wiersz; „Skąd aż tylu ludzi, / którzy już TO zrobili?!” [A] | sierota „Skąd” |
| d20 | Jeszcze ani razu w życiu się nie spóźniłem! (43) | Jeszcze / … | jeden wiersz [A]; „Jeszcze ani razu w życiu / się nie spóźniłem!” | sierota „Jeszcze” |
| d21 | Przecież to twoja ukochana młodsza siostrzyczka. (48) | … młodsza / siostrzyczka. | jeden wiersz; „Przecież to twoja / ukochana młodsza siostrzyczka.” [A] | przymiotnik \| rzeczownik, sierota |
| d22 | Jeśli napiszę do pana Jinshiego z prośbą... (43) | 13/29 | jeden wiersz [A] | „do pana / Jinshiego” |
| d23 | nie spłonie, dopóki cała woda nie wyparuje? (43) | 12/30 | jeden wiersz; „nie spłonie, / dopóki…” [A: przecinek, długość] | — |
| d24 | Sześćdziesiąt procent szczęścia, czterdzieści procent wyparcia, a na dobitkę permanentny brak snu. (98) | … czterdzieści / procent… | „Sześćdziesiąt procent szczęścia, czterdzieści procent / wyparcia, a na dobitkę permanentny brak snu.” (t01: 53/44 > 63/34); „…wyparcia, / a na dobitkę…” (r6: dwa > trzy) | liczebnik \| rzeczownik; trzy wiersze (zakaz „cięcia wewnątrz członu wyliczenia” był regułą orkiestratora — właściciel go odrzucił w t01) |
| d25 | Czy oni nie zdają sobie sprawy, że są uprzywilejowanymi uczniami tej prestiżowej akademii? (90) | … że są / uprzywilejowanymi… | „Czy oni nie zdają sobie sprawy, / że są uprzywilejowanymi uczniami tej prestiżowej akademii?”; „…że są uprzywilejowanymi / uczniami…”; trzy wiersze [A] | „że są /” na końcu wiersza |
| d26 | Wystarczy, że wskoczę w kostium kąpielowy, a przewodniczący straci dla mnie głowę w ułamku sekundy! (99) | 42/56 | „Wystarczy, że wskoczę w kostium kąpielowy, / a przewodniczący straci dla mnie głowę w ułamku sekundy!”, jeśli dolny mieści się w polu; inaczej trzy wiersze na granicach fraz | „kostium / kąpielowy”, „w ułamku / sekundy”, „głowę / w”; wiersz poza polem |
| d27 | Dziwię się, że same chcą sobie zrobić taką krzywdę. (51) | 10/37 | jeden wiersz | „Dziwię się, /” (sierota z przecinkiem); „…chcą / sobie zrobić…” |
| d28 | Taki właśnie bezmiar geniuszu kryje Kaguya Shinomiya! (53) | 20/32 | jeden wiersz; „Taki właśnie bezmiar geniuszu / kryje Kaguya Shinomiya!” | „Kaguya / Shinomiya” |
| d29 | Jak tak pomyśleć, to słyszałem, że jeśli różnica w ilorazie inteligencji wynosi ze dwadzieścia punktów, (103) | 48/54 | „Jak tak pomyśleć, to słyszałem, że jeśli różnica / w ilorazie inteligencji wynosi ze dwadzieścia punktów,”; „Jak tak pomyśleć, to słyszałem, / że jeśli różnica w ilorazie…” — oba tylko w polu; inaczej trzy wiersze na granicach fraz | „ze dwadzieścia / punktów”, „w ilorazie / inteligencji”, „różnica w / ilorazie”; wiersz poza polem |
| d30 | mojej wielkiej pani, nie robiąc ci krzywdy. (43) | 21/20 | jeden wiersz; „mojej wielkiej pani, / nie robiąc ci krzywdy.” [A] | — |

**Rozstrzygnięcia [A] po ankiecie** (zasada „jeden wiersz, dopóki nie dochodzi do krawędzi”; szerokość jednego wiersza w nawiasie): jeden wiersz — d01 (0,63), d02 (0,66), d03 (0,65), d04 (0,69), d05 (0,68), d07 (0,70), d19 (0,56), d20 (0,59), d21 (0,68), d22 (0,57), d23 (0,59), d27 (0,71), d28 (0,77; dopuszczalne też „Taki właśnie bezmiar geniuszu / kryje Kaguya Shinomiya!”), d30 (0,56). d09: dwa wiersze wychodzą poza pole (0,94), więc trzy wiersze „Oto przed wami uparty osobnik, / który do tej pory z uporem maniaka twierdził, / że smartfon nie jest mu do niczego potrzebny.”. Otwarte (do drugiej, krótkiej rundy ankiety, jeśli prototyp nie rozstrzygnie zgodnie z zasadami): d10, d17, d24 — trzy wiersze z dobrymi cięciami wobec dwóch szerokich ze słabszym cięciem.

Wspólne dla wszystkich dialogów: tagi (kursywa, kolor) zostają na tych samych słowach co w źródle i nigdy w środku słowa (d15, d16, d27, d28 pokazują dziś kursywę w złym miejscu); żaden wiersz nie jest zawijany przez libass inaczej, niż zaplanował rdzeń.

### 6.2 Napisy poboczne (zestaw trudny)

| Id | Sytuacja | Stan wejściowy | Wymagane | Zakazane |
| --- | --- | --- | --- | --- |
| s01 | „Zagrożenie dla bezpieczeństwa” zamiast „Safety Hazard”, panel przy lewej krawędzi | wystaje poza ekran | mieści się na ekranie; środek (zmniejszenie, ściśnięcie, dwa wiersze) [A] | wyjście poza ekran bardziej niż oryginał |
| s02 | tablica kredowa, 23 → 44 znaki | dwa wiersze w ramce | dwa wiersze w ramce bez nachodzenia | — |
| s03 | wiadomość w ramce nad dialogiem | dwa wiersze ~60 znaków | mieści się w szerokości ramki oryginału | wiersz szerszy niż ramka; nachodzenie na dialog pod spodem bardziej niż w oryginale |
| s04 | lista trzech zabaw na kartce | „Papierowe / sumo” | cięcia na granicach pozycji listy, **jeśli przekład je zachował**; tu przekład zlał pozycje w jeden tekst, więc układ ich nie odtworzy — tylko raport (zależność od tłumaczenia, poza zakresem rdzenia) | — |
| s05 | wzór „… x … x … + … = ?” nad japońskim tekstem | dwa wiersze nachodzą | bez nachodzenia na inny napis; liczba wierszy po rundzie 2 ankiety | wzrost w pionie nachodzący na inny napis |
| s06 | drobny tekst plakatu | prawie nieczytelny | czytelny przy x2 albo zgłoszony w raporcie | — |
| s07 | „trzeci sezon Grand Blue Dreaming został potwierdzony!” | „Grand / Blue Dreaming” | nazwa własna w jednym wierszu | cięcie wewnątrz nazwy |
| s08 | tytuł zapowiedzi 23 → 37 znaków | szerszy niż japoński tytuł | w szerokości oryginału albo lekko szerszy bez nachodzenia | nachodzenie na japoński tytuł |
| s09, s10 | tytuły odcinków: większy nagłówek „Odcinek pierwszy:” + tytuł | trzeci wiersz najdłuższy i ściśnięty / krótki środek | nagłówek w osobnym wierszu (zmiana `s`, właściciel 20.10: „Odcinek pierwszy jest wyraźnie inny”; także bez zmiany stylu: etykieta z dwukropkiem w pierwszych 1–3 słowach napisu pobocznego, po której jest dalszy tekst, to granica wymuszona — decyzja właściciela 20.10, s10), reszta zrównoważona: „Odcinek pierwszy: / Chłopiec, który jest najsilniejszym magikiem na świecie, / bierze udział w wielkim turnieju bitew magicznych”; „Odcinek drugi: / Chłopiec, który jest najsilniejszym magiem na świecie, / przywdziewa maskę” | sklejenie nagłówka z tytułem w jednym wierszu; kształt klepsydry; ściśnięcie zlewające litery |
| s11 | tabliczka „Grynszpanowy Pawilon” | kilka pikseli | czytelna albo raport | zmniejszenie poniżej czytelności bez konfliktu, który by je wymuszał |
| s12 | ranking z punktami | „406 / pkt” | liczba z jednostką razem | rozbicie liczby i jednostki |
| s13 | podpis „Has a tea ceremony license” + 6 pustych wierszy + „Knowledgeable” | 7 wierszy po jednym słowie na japońskim tekście | dwa wiersze z tekstem na miejscach wierszy źródła, puste odstępy na swoich miejscach | traktowanie pustych wierszy jako miejsc do wypełnienia |
| s14 | dymek myśli | sierota „mi” | „Mam wrażenie, / że Pes kogoś / mi przypomina...” (dwa wiersze wychodzą poza dymek — sprawdzone na obrazie) | sierota „mi” |
| s15 | podpis postaci przy górnej krawędzi | górny wiersz ucięty | mieści się na ekranie (jeden wiersz ze zmniejszeniem albo wzrost w dół) | wyjście poza ekran |
| s16 | etykieta „Sekretarz Samorządu…” | drugi wiersz poza etykietą | w etykiecie | — |
| s17 | piosenka OP „Miłość to wojna!” × 3 przy górnej krawędzi | pierwszy wiersz nad ekranem | liczba wierszy źródła, na ekranie | wyjście poza ekran |
| s18 | piosenka ED w czarnym pasie | „skończysz / szkołę”, drugi wiersz na obrazie | cięcie po sensie, w pasie | rozerwany związek; zjazd z pasa, gdy źródło było jednowierszowe |
| s19, s20 | list przykryty japońskim pismem | „oraz to, /”; „nie / mogę” | bez sieroty, „nie” przy czasowniku | „nie / mogę” |
| s21 | etykieta „Przypis: nie potrafi pływać” | „ć” wychodzi poza etykietę | w etykiecie | — |
| s23 | karta potwora w pasie na jeden wiersz | dwa wiersze bardzo małe, na japońskim tekście | jeden wiersz jak źródło, zmniejszenie w granicach czytelności | dodatkowy wiersz nachodzący na inny napis |
| s25 | kartka „Come to the roof / - Peek-a-Boo Seniors” | półpauza na końcu górnego wiersza | „Zbiórka na dachu / – Starsi z Peek-a-Boo” (podpis od półpauzy, jak w źródle) | przeniesienie autorskiej półpauzy podpisu na koniec wiersza |
| s26 | obrócona wiadomość | „romantyczne / miejsce” | cięcie po sensie | przymiotnik \| rzeczownik |
| s28 | piosenka ED w czarnym pasie | drugi wiersz na obrazie | w pasie | — |
| s29 | zastrzeżenie, wiele wierszy wyrównanych do prawej | 12 poszarpanych wierszy | liczba wierszy z tekstem jak w źródle, proporcje zbliżone | poszarpany kształt przy dostępnym zrównoważonym |
| s30 | karta postaci w pasie na jeden wiersz | dwa wiersze na japońskim tekście | jeden wiersz ze zmniejszeniem w granicach czytelności | jw. s23 |

Poza zakresem układu, raportowane: czcionki szyldów bez polskich liter (s13–s16, s21, s27; decyzja właściciela o czcionce zastępczej z visual-quality §12), przykrycie przez inne napisy wynikające z kolejności warstw (s19, s20, s24).

Obserwacja z zestawu: 10 z 30 trudnych dialogów ma 90–123 znaki, bo przekład jednej kwestii zajmuje tyle, co dwa angielskie wiersze. Układ nie skróci tekstu (reguła nienaruszalna); limit długości przekładu to osobna, otwarta decyzja właściciela (visual-quality §12).

### 6.3 Przypadki krańcowe

| Id | Sytuacja | Wymagane |
| --- | --- | --- |
| e01 | słowo szersze niż pole | jeden wiersz z tym słowem, przepełnienie w raporcie, słowo nierozcięte |
| e02 | tekst bez spacji (CJK, URL) | bez cięcia albo cięcie tylko na dozwolonych znakach; raport |
| e03 | kwestia dwóch mówców z myślnikami | wiersz na mówcę; myślnik mówcy nie jest sierotą ani pauzą wtrącenia |
| e04 | trzech mówców | trzy wiersze (ratunek, raport) albo dwóch mówców w wierszu zgodnie z ratunkiem |
| e05 | autorskie `\N` w polskim źródle (normalizacja polskich napisów) | traktowane jak każdy tekst do ułożenia, bez wiązania do autorskiego cięcia |
| e06 | twarda spacja `\h` | nigdy cięcie w `\h` |
| e07 | tag w środku słowa (gradient, `\k`) | zdarzenie karaoke nietknięte; gradient — tag zostaje w słowie, cięcie tylko między słowami |
| e08 | zmiana rozmiaru w wierszu (`\fs`) | pomiar z tagami danego wiersza |
| e09 | kwestia identyczna z angielską | bajtowo identyczna (visual-quality §2.1.7) |
| e10 | SRT bez profilu | ta sama ocena, pomiar w grafemach, bez skali |
| e11 | lista z pustymi wierszami i przekładem o tej samej liczbie pozycji | pozycje na swoich wierszach, puste wiersze na swoich miejscach, bez ściskania |
| e12 | szyld obrócony (`\frz`) przy krawędzi albo przy sąsiedzie | prostokąt = obwiednia obróconych rogów; żadnego zmniejszenia wynikającego z nieobróconego prostokąta |
| e13 | bardzo długa kwestia (≥ 130 znaków) | trzy wiersze w ratunku, raport; nigdy wiersz zawijany przez libass |
| e14 | długa kwestia w pliku z drobną czcionką dialogu (60–70 znaków przy 0,7–0,78 szerokości) | dwa wiersze — decyduje miara znakowa (§4.1); test regresji błędu U5 |
| e15 | dwa dialogi naraz, układane przez libass jeden nad drugim | każdy układany osobno; suma wierszy raportowana (kolizja), bez przesuwania |
| e16 | animowana skala `\t(\fs…)`, `\t(\fscx…)` | pomiar przy największej skali animacji |
| e17 | wzrost liczby wierszy przy `\an7–9` (rośnie w dół) i `\an1–3` (rośnie w górę) | kierunek wzrostu wg `\an` uwzględniony w filtrze ekranu (s15, s17) |
| e18 | jąkanie „N-nie”, „W-wiesz” | traktowane jak jedno słowo; samo w wierszu jest sierotą |
| e19 | kwestia jednego mówcy dłuższa niż wiersz w kwestii dwóch mówców (e03) | mówca może zająć dwa wiersze tylko w ratunku (trzy wiersze łącznie, raport) |
| e20 | tekst pionowy (`\frz90`, kolumna) | bez zmiany liczby wierszy; zmniejszenie; prostokąt po obrocie |
| e21 | polskie litery dorysowane czcionką zastępczą (s13–s16) | pomiar z czcionką zastępczą; przy `\q2` zapas pomiaru, żeby niedoszacowanie nie wypchnęło tekstu poza ekran |

## 7. Kiedy praca jest skończona

Procent zgodności z zawodowcami nie jest miarą jakości: „78%” oznaczało 78,8% identycznych cięć na NF+AMZN, a z pozostałych 21,2% ślepa ocena uznała za złe cięcia ok. 4,2% kwestii [2,6; 6,5], za drobne przegrane ok. 10%, resztę za równoważne albo lepsze. Na Crunchyroll zawodowiec był zły w 24% niezgodności, więc zgodność karze też poprawianie jego błędów. Miarą jest **odsetek złych cięć w ślepej ocenie**.

1. Katalog 100%.
2. Zestaw trudny: zero układów ocenionych jako złe (orkiestrator + dwóch recenzentów innej rodziny, każdy obraz obejrzany).
3. Ślepa ocena ≥ 150 losowych kwestii dwuwierszowych z napisów zawodowców (A/B w losowej kolejności, co najmniej dwóch sędziów, kryteria jak w `scratchpad/v4-agree`): odsetek złych cięć algorytmu nie wyższy niż zawodowców NF+AMZN (ok. 1%) z dokładnością przedziału ufności; stan odniesienia: stary algorytm 6,3%, najlepszy model 19.10 4,2%. Zgodność z NF+AMZN raportowana pomocniczo.
4. Stan wejściowy → nowy na całym replayu: dla każdego rodzaju pola liczba układów, w których któraś szkoda rdzenia (§4) ma stopień „bardzo” (rozerwany związek chroniony, sierota, długość ponad kolano z ankiety, szyld poza ekranem lub ramką), nie rośnie i spada tam, gdzie stan wejściowy ją miał. Stopnie liczy rdzeń, nie osobny próg znakowy.
5. Bramki repo, czas na odcinek w granicach minut.
6. Właściciel potwierdza na wskazanych obrazach.

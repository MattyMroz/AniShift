---
kind: report
status: pending-human
baseline: work/quality/21-text-layout @ 1b67f0d1
resulting-state: work/quality/21-text-layout (WEIGHTS w layout.py, nowe klasy przerw w gaps.py)
completed: 2026-10-19
---

# Kalibracja rdzenia układu tekstu — raport

Kontrakt: [text-layout.md](../text-layout.md) §4.2, §5.3, §7, plan [02-text-layout.md](../plans/02-text-layout.md) fazy C i E. Stan po siódmej rundzie (napisy poboczne, sekcja „Runda 7”); wcześniej piąta runda (sekcja niżej); czwarta runda: nowe klasy przerw z polskiej składni (po ślepej ocenie 160 kwestii NF+AMZN, w której rdzeń ciął źle w 5,0% kwestii), poprawki z przeglądu kodu faz A–C i ponowna kalibracja.

## Wynik

Kalibracja z morfologią jest **wykonalna**: brak zbiorów sprzecznych i konfliktów poziomów. Pary twarde katalogu i ankiety mają margines, pary „oba dobre” (q09, q16, q17, r02) i pary zawodowców są miękkie. Wagi są w `WEIGHTS` w `anishift/services/subtitles/layout.py` (6 cyfr znaczących); test katalogu liczy wynik ponownie na tych zaokrąglonych wagach.

| Miara | Wynik |
| --- | --- |
| Katalog i ankieta w pełnej przestrzeni kandydatów (z układami powyżej trzech wierszy) | **83/83** (`tests/services/subtitles/test_text_layout_catalogue.py`) |
| Test z pominięciem jednego zdarzenia | **71/83**; niespełnione: d06, d15, d25, d28, q10, q11, q15, q19, r03, s02, s26, t02 |
| Wrażliwość ±10% (tylko raport) | `length_comfortable` ×0,9 → q10; ×1,1 → d06, d28, t02; `extra_line` ×0,9 → d28, ×1,1 → q10, s02; `cut_degree` ×0,9 → d06, t02; `cut_phrase` ×1,1 → e06, e13; `cut_modifier` ×0,9 → e13; `shrink` ×0,9 → s02; `over_comfort` ×0,9 → s02, ×1,1 → s26 |
| Przypadki przy kolanie (jeden wiersz 0,74–0,80) | d28 0,771 (jeden wiersz), q04 0,741 (jeden), q10 0,748 (dwa), q11 0,800 (dwa), q14 0,789 (dwa), q17 0,768 (dwa; „oba dobre”), q19 0,783 (dwa), e14 0,798 (dwa) |
| Zawodowcy NF+AMZN | 441 kwestii uczących, 13 pominiętych (układ zawodowca poza poziomem 0), 1319 par miękkich, 174 naruszone; strata par „oba dobre” 4,50 |
| Bez morfologii | niewykonalne: {r03}, {d15} — morfologia zostaje |
| Czas pełnej kalibracji (oba warianty, LOO, wrażliwość) | ok. 6 min |

LOO i wrażliwość pokazują to samo co wcześniej: przy kolanie długości (0,74–0,80) i przy krótszej górze wynik zależy od pojedynczych odpowiedzi właściciela. q15 (szyld zmniejszony do szerokości oryginału) i s29 (lista zastrzeżeń) doszły do listy LOO, bo bez swojego zdarzenia kalibracja nie ma przypadku, który wiąże wagi zmniejszenia i nierówności wielu wierszy.

Najważniejsze wagi (runda 7): długość 165,2 (od 0,55) i 293,3 (od 0,76), drugi wiersz 33,7, wystawanie poza oryginał 152,9, ściśnięcie 86,2, zmniejszenie 78,2, małe litery 0,95, związki chronione, `auxiliary` i jednoliterowy wyraz 52,2, `after_opener` 32,4, `particle` 22,3, `degree` 19,9, `modifier` 7,8, `phrase`, `abbreviation`, `prepositional` 6,8, `before_preposition` 4,2, zgoda przymiotnika 6,8, nierównowaga ponad 20 znaków 2,24 na znak, dłuższa góra 0,43 na znak; brakujący wiersz szyldu 0. Klasy od końca zdania do „przed spójnikiem współrzędnym” mają wagę 0,001, więc o takich cięciach decyduje kształt.

**Szkoda „za mały” (`small`) do rundy 6 miała wagę 0 — to był brak danych, nie błąd cechy** (w rundzie 7 dostała 0,95, bo pary s02 wiążą zmniejszenie). Stopień liczy się poprawnie (np. 15 391 z 45 729 kandydatów s29 ma go powyżej zera). W katalogu są pary, w których przegrany ma mniejsze litery od zwycięzcy (r01: 51, s14: 19, s10: 15, q15: 2), ale każdy taki przegrany przegrywa już przez zmniejszenie: litery spadają poniżej 30 px dopiero przy skali ok. 0,36–0,59 (litery 51–84 px), gdzie szkoda zmniejszenia jest duża. Program liniowy minimalizuje sumę wag przy zachowanym marginesie, więc wagi, której żadna para nie wymaga, nie podnosi. Żeby szkoda działała, katalog potrzebuje przypadku, w którym zmniejszenie samo przegrywa tylko przez czytelność (np. drobny tekst s06, s11 — dziś poza rdzeniem).

## Runda 7 (faza E: napisy poboczne)

Napisy poboczne idą przez rdzeń z polem `sign_field` (to samo pole buduje katalog i produkcja w `fitting.py`). Do katalogu doszły przypadki §6.2 z polem zmierzonym czcionką typesettera (`layout_catalogue.py`, tagi pierwszego bloku angielskiego zdarzenia): s02 (tablica: dwa wiersze zamiast jednego mocno zmniejszonego), s13 (dwa wiersze z tekstem, puste wiersze autorskie odtwarza integracja), s17 i s28 (piosenka w jednym wierszu), s23 i s30 (karta w pasie na jeden wiersz), s25 (podpis od półpauzy, granica wymuszona). s26 dostało jawny układ dopuszczalny, bo przypadek bez listy układów nie daje kalibracji żadnej pary (z samą regułą wynik łamał zakaz „romantyczne / miejsce”). s02 to pierwszy przypadek, w którym dodatkowy wiersz szyldu wygrywa ze zmniejszeniem do 50%: wagi zmniejszenia, ściśnięcia i wystawania wzrosły kilkukrotnie, drugi wiersz staniał z 87,7 do 33,7, a długość dialogu przesunęła się na stromą część (165,2 + 293,3 zamiast 422,2 + 36,3). Kolejność zmniejszenie < ściśnięcie (q15) zostaje.

Wynik: wykonalna, katalog i ankieta 83/83, test z pominięciem jednego zdarzenia 71/83 (doszły s02, s26 — bez nich nic nie wiąże ich wag), bez morfologii nadal niewykonalna ({r03}, {d15}). Test produkcyjny: 54 dialogi przez `layout_translated` bez zmian, 15 przypadków s* katalogu przez `layout_translated` + `fit_signs` (s13 oczekiwanie niespełnione: kolumna źródła wystaje poza lewą krawędź, więc produkcja ogranicza szerokość do szerokości oryginału i wybiera trzy wiersze w 89% zamiast dwóch w 40%; oznaczone `xfail`), 30 przypadków s01–s30: wynik nie wychodzi poza ekran i nie zasłania innych napisów bardziej niż oryginał albo raport liczy ratunek.

## Runda 6 (ścieżka produkcyjna)

Galeria replayu v4 pokazała jednowierszowe kwestie ponad kolanem ankiety (q11 0,80, „Cóż z ciebie…” 0,83, „Kraina Cienia…” 0,80), choć katalog przechodził. Przyczyny:

- **Pomiar katalogu a pomiar produkcji.** Katalog sumuje szerokości słów, produkcja mierzy cały wiersz; całe wiersze dialogu wychodzą o 0,13–0,94% węższe. Kalibracja trzymała q11 z marginesem 0,08 punktu oceny, czyli ok. 0,0003 szerokości, więc 0,4% różnicy odwracało wynik. Teraz każda para twarda dialogu ma też wiersz policzony przy szerokościach o 1% mniejszych (`MEASURE_TOLERANCE`); waga stromej części długości wzrosła z 3,5 do 36,3.
- **Cytat na całą kwestię.** Cięcie wewnątrz cytatu było poziomem ratunku, gdy cytat mieścił się w polu (90% ekranu), więc cytat szeroki na 0,83 nigdy nie dzielił się na dwa wiersze. „Krótki cytat” (§4.2) to teraz cytat nie szerszy niż kolano długości pola (0,76 dla dialogu).

Po przeglądzie fazy D: granica stylu w polu dialogu jest szkodą ważoną `mixed_style`, a nie poziomem ratunku (w polach szyldów bez zmian). Katalog nie ma przypadku dialogu z granicą stylu, więc kalibracja daje jej wagę 0. Etykieta wymaga po dwukropku nazwy z dwóch wyrazów z wielkiej litery, a nazwisko przestaje się wiązać tylko przed drugą etykietą tego samego tekstu („Siodłak / Korekta:”; „Jan Kowalski: Nie wrócę” i „Pamiętaj: To jest” bez zmian).

Kalibracja: wykonalna, katalog i ankieta 76/76, test z pominięciem jednego zdarzenia 66/76 (d06, d15, d25, d28, q10, q11, q19, r03, s14, t02), bez morfologii niewykonalna ({r03}, {d15}). Nowy test `test_text_layout_production.py` puszcza 54 przypadki dialogu katalogu i ankiety przez `layout_translated` z ich parami i czcionką dialogu właściciela; na kodzie sprzed poprawki pada na q11.

## Runda 5 (po ślepej ocenie Crunchyroll)

Ślepa ocena 200 kwestii CR (dwóch sędziów zgodnie) wskazała dziewięć złych cięć rdzenia. Zmiany klas (`gaps.py`, `idioms.txt`, testy w `tests/text/test_gaps.py`):

| Klasa / reguła | Zmiana | NF+AMZN: cięcia zawodowców / pozostałe | CR: cięcia / pozostałe |
| --- | --- | --- | --- |
| `degree` | zamknięta lista operatorów gradacji, aproksymacji i stopniowania analitycznego z M. Grochowski, „Gradacja” (IJP PAN): znacznie, nieznacznie, zupełnie, całkowicie, kompletnie, absolutnie, zanadto, zbytnio, nazbyt, nadmiernie, wielce, wysoce, strasznie, ogromnie, odrobinę, prawie, niemal, niemalże, niespełna, raczej, mniej, bardziej, najmniej, najbardziej, dosyć; wyjątkowo, niezwykle, okropnie jako intensyfikatory tej samej klasy | 0 / 0,16% | 0,63% / 0,33% |
| `idiom` | no to, no i, no więc, no cóż, a więc, a zatem, i tak; pary formularzowe imię i nazwisko, data i miejsce | 0 / 0,05% | 0 / 0,01% |
| `label` | wyraz z wielkiej litery zakończony dwukropkiem przed wartością z wielkiej litery („Korekta: Michał”); nazwa własna nie wiąże się z następującą etykietą („Siodłak / Korekta:”) | 0 / 0 | 0 / 0,08% (etykieta), 0,27% / 0,03% (zdjęte `name`) |
| `auxiliary` | forma „być” lub czasownika modalnego przed frazą przyimkową, która nie jest utartym zwrotem, nie jest przerwą posiłkową („będziemy / w tej samej klasie”) | 0 / 0,50% (zdjęte) | 0,89% / 0,53% (zdjęte) |

Fraza przyimkowa przez przymiotnik („w tej / samej klasie”) nie wymagała zmiany wagi: przegrywała, bo jedyna alternatywa („będziemy / w tej…”) była błędnie liczona jako przerwa posiłkowa. „w południowym / regionie” (CR #61) to skutek wymuszenia dwóch wierszy w próbie: alternatywa „przechowywanych / w południowym regionie Binan.” ma sierotę, czyli poziom ratunku, a w zwykłym układzie kwestia mieści się w jednym wierszu.

Granica stylu (wskazanie właściciela 19.10): `Field.style_breaks` — przerwy, na których zmienia się krój, rozmiar, skala albo waga (`geometry.style_changes`). Wiersz łączący dwa style podnosi poziom ratunku (flaga `mixed`), a zmiana stylu w miejscu końca wiersza źródła jest granicą wymuszoną. s09 ma w katalogu wymuszoną granicę po „Odcinek pierwszy:” i układ właściciela. s10 nie ma zmiany stylu w źródle („Episode 02\NThe Boy Who Is the\N…” bez tagów): wymaganie układu właściciela z osobnym nagłówkiem daje niewykonalność ({s10}), bo żadna cecha rdzenia nie odróżnia nagłówka bez zmiany stylu — s10 zostaje z regułą `no_hourglass`, decyzja do właściciela.

Kalibracja po rundzie 5: wykonalna, katalog i ankieta 76/76, test z pominięciem jednego zdarzenia 64/76 (bez zmian: d06, d15, d25, d28, q10, q11, q15, q19, r03, s14, s29, t02), wariant bez morfologii nadal niewykonalny ({r03}, {d15}). Wagi prawie bez zmian; `cut_before_subordinator` spadła z 2,67 do 0,001.

Próby ślepe przeliczone przy nowych wagach (bez nowej oceny sędziów): NF+AMZN — 13 ze 160 układów inne niż w kluczu, identyczne z zawodowcem 130 (wcześniej 122), z 12 złych pozycji zmieniło się 10 (bez zmian: „wrócimy / i wyruszymy”, „z tobą / poćwiczę”); CR — 7 z 200 innych, identyczne z zawodowcem 125 (wcześniej 121), z 9 złych pozycji zmieniło się 6 (bez zmian: „Nie dali / nam”, „Imię / i nazwiskoTani” — sklejony wyraz w źródle, utarty zwrot go nie obejmuje, „w południowym / regionie”).

## Nowe klasy przerw (runda 4)

Wszystkie z zamkniętych list albo morfologii, z testami w `tests/text/test_gaps.py`; źródła list w kodzie i w `idioms.txt`. Fałszywe alarmy: odsetek oznaczonych cięć zawodowców (601 cięć NF+AMZN, 1118 CR) wobec odsetka oznaczonych pozostałych przerw (3787 NF+AMZN, 7337 CR); liczone tylko tam, gdzie nowa reguła zmienia klasę przerwy.

| Klasa / reguła | Poziom | NF+AMZN: cięcia zawodowców / pozostałe | CR: cięcia / pozostałe |
| --- | --- | --- | --- |
| liczebnik nieokreślony lub zbiorowy \| rzeczownik (`number`: kilka, wielu, parę, tyle, dwoje, oboje…) | chroniony | 0 / 0,24% | 0,27% / 0,33% |
| `dużo`, `mało`, `sporo` jako `degree`; `degree` także przed frazą przyimkową („tak / bez zapowiedzi”), chyba że po nim utarty zwrot („tak w ogóle”) | ważony | 0 / 0,18% | 0,09% / 0,11% |
| partykuła przed słowem, które określa (`particle`: nawet, jedynie, właśnie, już, jeszcze, też, także, również, przynajmniej, zwłaszcza, szczególnie, akurat) | ważony (poziom 4, jak słowo otwierające) | 0 / 1,40% | 1,25% / 1,36% |
| `sobie`, `siebie`, `sobą` jak „się” (ta sama reguła i wyjątki) | chroniony | 0 / 0,82% | 0,27% / 0,48% |
| utarte zwroty z Wikisłownika (frazy przyimkowe spoza przyimków złożonych: „co najmniej”, „w porządku”, „wraz z”…; „tak zwany” z odmianą; „co do”) | chroniony | 0 / 0,11% | 0 / 0,03% |
| fraza przyimkowa przez zaimek dzierżawczy („pod jej / uczucia”; po przyimku „jej/jego/ich” są dzierżawcze) i koniec przyimka złożonego („z punktu widzenia / …”) | chroniony (`after_preposition`) | 0 / 0,42% i 0 / 0,26% | 0,18% / 0,52% i 0,09% / 0,10% |
| fraza przyimkowa przez przymiotnik zgodny z Morfeusza („w tej / sprawie”) | ważony (`prepositional`) | 0 / 1,58% | 1,07% / 1,84% |
| etykieta z dwukropkiem i wartością liczbową („WYS.: / 4,5 KM”, `label`) | chroniony | 0 / 0,05% | 0 / 0 |
| powtórzenie z myślnikiem („BAM - / BAM”, `repetition`) | chroniony | 0 / 0,05% | 0 / 0 |
| przerwa bierze klasę najszkodliwszą ze wszystkich dowodów (przegląd kodu): „i / …”, „a / …” → jednoliterowy wyraz; „dr. / Kowalski” → `name` | jak klasa | 0 / 9,48% | 0,54% / 7,29% |

Fraza przyimkowa przez przymiotnik była najpierw chroniona; wtedy q11 („Magia ingerująca we wszystkie / ciągi przyczynowo-skutkowe.”, wybór właściciela) dawał konflikt poziomów, bo „we wszystkie / ciągi” leżało na poziomie ratunku. Zgodnie z §4.2 (zgoda przymiotnika jest szkodą ważoną właśnie z powodu q11) dostała własną klasę ważoną.

**Węższa reguła Morfeusza (wdrożona):** słowo odpada z pary tylko przy odczycie osobowym lub przeszłym (`fin`, `praet`, `bedzie`, `aglt`, `winien`); tryb rozkazujący, bezokolicznik i inne odczyty czasownikowe są pomijane. Zgoda zapala się przy 3 z 601 cięć zawodowców NF+AMZN (0,50%, bez zmian) i przy 9,19% pozostałych przerw (wcześniej 8,93%); na CR 5,19% wobec 9,43% (wcześniej 5,10% wobec 9,21%). Rozdzielczość cechy rośnie, „usprawiedliwiony sposób” jest już parą zgodną.

## Poprawki z przeglądu kodu (fazy A–C)

1. **Programowanie dynamiczne = pełny przegląd.** DP liczy się dla każdej skali poziomej, której wymaga jakikolwiek odcinek słów (nie tylko skale najlepszego układu bez skali), a przy polu z krótszą górą trzyma poprzedni wiersz w stanie. Siatka skal zaokrągla każdy punkt załamania w dół i w górę do pełnego procentu — bez tego DP znajdował skale lepsze od pełnego przeglądu (5 z 48 przypadków recenzenta). Reproducer recenzenta: 0 rozbieżności z 48; test `test_dynamic_programming_finds_the_optimum_of_the_exhaustive_search` pada po usunięciu siatki albo stanu krótszej góry.
2. **Za dużo wymuszonych granic** (czterech mówców, lista „(1)…(4)” przy trzech wierszach ratunku) nie wywraca już rdzenia: granice są zwalniane, wiersz może je połączyć i dostaje flagę `joined` w poziomie ratunku (e04, e19). Test.
3. **Najszkodliwsza klasa** — jak w tabeli wyżej; test `test_gaps` utrwalający „i” jako `after_opener` poprawiony.
4. **Wydajność:** pamięć podręczna szerokości wierszy i liczby grafemów, DP tylko w polu, gdy wszystkie wiersze mogą się zmieścić, pomijanie przebiegów DP, których dolne ograniczenie (szkody globalne plus szkody wierszy przy najmniejszej skali) nie może pobić najlepszego układu. s29: 2,6 s zamiast 25 s; kalibracja 6 min 45 s zamiast 28 min.
5. **Kalibracja widzi układy powyżej trzech wierszy:** gdy DP rdzenia znajduje taki układ lepszy od pierwszego dopuszczalnego, narzędzie dopisuje parę twardą i rozwiązuje ponownie (aż do braku nowych par); przypadek z regułą `not_ragged` (s29) dostaje za cel najlepszy układ bez bardzo poszarpanego wiersza. Bez tego s29 wypadał ze zbioru dopuszczalnych przy nowych wagach.
6. Raport: ten dokument zastępuje wcześniejsze zdania o odporności par na ±10% i o braku wag i testu.
7. Jakość: jednolinijkowy docstring `_COORDINATORS`, typ `SSAFile` i stała `_RE_FONT_SIZE` w `layout_catalogue.py`, listy spójników i przyimków oraz myślniki mówców mają jedno źródło w `gaps.py` (`linebreak.py` i `layout.py` je importują).

## Próby ślepe

**Nowa próba (CR):** arkusz `scratchpad/v4-blind2/blind.txt`, klucz `scratchpad/v4-blind2/key.json` (scratchpad sesji orkiestratora). 200 losowych kwestii dwuwierszowych Crunchyroll (ziarno 20261020); kalibracja używa tylko NF+AMZN, a poprzednia próba była z NF+AMZN, więc żadna z tych kwestii nie była widziana. Rdzeń (najlepszy układ dwuwierszowy, morfologia, pomiar w znakach) daje układ identyczny z zawodowcem w **121 z 200 (60,5%)** — w kluczu `same: true`, poza arkuszem; w arkuszu **79** par A/B w losowej kolejności liter. Komenda: `python -m scripts.subtitle_quality.layout_calibrate --blind-only --blind-families cr --blind-seed 20261020 --blind-size 200 --blind <katalog> --out <plik>`.

**Poprzednia próba (NF+AMZN, 160 kwestii) przy nowych wagach:** z 38 spornych pozycji układ rdzenia zmienił się w **10**; 8 z nich jest teraz identycznych z zawodowcem. Z 12 spornych pozycji, w których któryś sędzia ocenił rdzeń jako zły, zmieniło się 9 („pod jej uczucia”, „kilka zabłąkanych”, „z punktu widzenia zarówno rojalistów”, „sobie siebie / w roli”, „WYS.: 4,5 KM”, „co najmniej”, „tak bez zapowiedzi”, „Nawet czujniki”, „BAM - BAM - BAM”); bez oceny nowych układów. Słabe cięcia przy dostępnym lepszym („rozświetla / serca”, „wrócimy / i wyruszymy”, „z tobą / poćwiczę”) zostały bez zmian — to nie są błędy klas, tylko wymiana równowagi na miejsce cięcia. Dwie pozycje wcześniej identyczne z zawodowcem są teraz inne: „A rycerze / tylko pilnują…” i „Jeśli stanowią zagrożenie / dla wioski, musimy…” (waga nierównowagi spadła z 0,82 do 0,45 na znak).

## Jak liczono

Narzędzie: `python -m scripts.subtitle_quality.layout_calibrate --out <plik.json>` (z `--quality-root` wskazującym `workspace/.quality`). Katalog z pomiarami: `tests/services/subtitles/data/text_layout_catalogue.json` (odświeża go `python -m scripts.subtitle_quality.layout_catalogue --fonts <folder czcionek mpv>`).

| Element | Ustawienie | Źródło |
| --- | --- | --- |
| Cechy (szkody) | `HARMS` w `layout.py`: dwie miary długości (szerokość i znaki × 0,76/56), klasy przerw z `gaps.py`, zgoda przymiotnika (Morfeusz), nierównowaga w znakach z kolanami 6/10/20/25/30, dłuższa góra, liczba wierszy względem preferowanej, ściśnięcie, zmniejszenie, małe litery (16–30 px), wystawanie poza szerokość oryginału | spec §4.1–§4.6 |
| Poziomy przed wagami | 1) wiersz poza polem (90% ekranu dla dialogu), 2) wiersz ponad maksimum pola, 3) rozerwany związek chroniony, cięcie w krótkim cytacie, sierota, połączone wymuszone granice | spec §5.2 |
| Filtry | słowo nigdy nierozcięte, wiersz nie zaczyna się od pauzy wtrącenia, wiersz na mówcę, punkty listy „(n)” od nowego wiersza, gdy się mieszczą | spec §4.2, e03 |
| Pary twarde | pierwszy dopuszczalny układ każdego przypadku wygrywa z marginesem ze wszystkimi niedopuszczalnymi kandydatami swojego poziomu ratunku (do trzech wierszy z pełnego przeglądu, powyżej — z DP rdzenia, dopisywane w kolejnych rundach) | spec §5.3 |
| Pary miękkie | q09, q16, q17, r02 | spec §5.3 |
| Zawodowcy | NF+AMZN, 601 kwestii dwuwierszowych; 160 odłożonych na próbę ślepą (ziarno 20261019) | spec §5.3 p. 3, §7.3 |
| Monotoniczność | waga klasy przerwy nie maleje z poziomem `TIERS` (§4.2); każda waga klasy ≥ 0,001 marginesu | spec §5.3 |
| Cel | kolejno: najmniejsza strata par miękkich ankiety, najmniejsza strata zawodowców, najmniejsza suma wag | spec §5.3 |

Katalog: 76 przypadków rdzenia (d01–d30, s07, s09, s10, s14, s19, s20, s26, s29, e01–e04, e06, e13, e14, e18, e19 oraz 29 pytań ankiety z rund 1–3), 34 przypadki warstwy sceny lub integracji bez testu rdzenia (fazy D–E).

## Historia rozstrzygnięć (skrót)

- Wymóg odporności każdej pary na ±10% odpadł (decyzja koordynatora 19.10): granica właściciela przy długości jest ostra (d28 0,77 jeden wiersz, q11 0,80 dwa), więc wymóg dawał niewykonalność. Wrażliwość i LOO są tylko raportowane.
- Runda 3 ankiety: t01 (d24, 53/44 > 63/34) usunęła zakaz cięcia wewnątrz członu wyliczenia; t02 (d06, „…dzisiaj / tak bardzo…”) dała klasę `degree`.
- r1: notatka pytania podawała ok. 2116 px dla wiersza piosenki; pomiar daje ok. 1333 px (0,69 szerokości) — jeden wiersz w pełnym rozmiarze wygrywa z dwoma. Pole piosenki ma szerokość wygodną „jak dialog” (r01 a q15).
- d10: dwa wiersze mieszczą się w polu, więc trzy są niedopuszczalne; przyjęty tylko „Pozwoli mi to również w pełni legalnie i w usprawiedliwiony / sposób uwiecznić cyfrowo tę niewypowiedzianie słodką istotę!” (decyzja koordynatora, do potwierdzenia przez właściciela).
- s29 przyjmuje każdy układ w polu bez bardzo poszarpanego wiersza.
- Bez morfologii katalog i ankieta są niewykonalne ({r03}, {d15}), więc morfologia zostaje (bramka §4.7 „katalog i ankieta nie tracą”); warunek „mniej złych cięć w ślepej ocenie” rozstrzygną oceny sędziów.

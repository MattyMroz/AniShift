# Jak mają wyglądać polskie napisy

Status: projekt v2 do akceptacji agentów i właściciela. Data: 2026-10-18.

Ten dokument jest nadrzędny wobec specyfikacji technicznych: [fuzzy-signs-and-split.md](fuzzy-signs-and-split.md) (szyldy, lektor, kursywa i kolory) i [fuzzy-line-breaks.md](fuzzy-line-breaks.md) (łamanie dialogów). Mówi, **co chcemy osiągnąć, po czym poznać, że się udało, i gdzie są granice tego, co program może wiedzieć**. Gdy specyfikacja techniczna przeczy temu dokumentowi, poprawiamy specyfikację.

Podstawa:

- research: [typesetting-principles.md](research/typesetting-principles.md) (Netflix, BBC, Karamitroglou, PWN, Aegisub, przewodnik unanimated, badanie eye-tracking, policzona praktyka Shishy), [fonts.md](research/fonts.md) (dopasowanie czcionek w libass, pokrycie polskich liter w korpusie, test mpv właściciela), [code-map.md](research/code-map.md);
- galerie przed/po w `workspace/.quality/experiments/visual-fixes/`;
- decyzje właściciela z 17–18.10.2026.

## W skrócie

1. Polski napis ma wyglądać, jakby typesetter od początku robił go dla polskiego tekstu. Dobra praca jest niewidoczna: widz czyta, nie zauważa dopasowywania.
2. Reguły mają trzy poziomy. **Nienaruszalne** nie łamiemy nigdy. **Unikane za wszelką cenę** łamiemy tylko wtedy, gdy nie ma innego wyjścia, i zawsze to raportujemy. **Ważone** cechy porównujemy ze sobą: wygrywa wariant, który w sumie najmniej szkodzi.
3. Ważność cech to **wagi**, nie kolejka. Duża szkoda w mniej ważnej cesze może przeważyć małą szkodę w ważniejszej. Tak działa logika rozmyta, o którą prosił właściciel: „trochę / średnio / bardzo”, a nie jedna granica.
4. Profesjonaliści oceniają napis względem **obrazu**. AniShift obrazu nie widzi, więc za obraz podstawia **angielski typesetting**: zakłada, że typesetter dopasował go do kadru. To przybliżenie ma znane słabe strony (sekcja 9).
5. Dialogi dostają czcionkę wybraną przez właściciela, dołączoną do MKV. Szyldy zostają w czcionkach typesettera.
6. Ostatecznie ocenia człowiek, patrząc na kadr, a przy ruchu i szybkim tempie na krótki fragment w mpv. Liczby służą tylko do znajdowania przypadków do obejrzenia.

## 1. Kto ogląda i w jakich warunkach

| Warunek | Skutek dla napisów |
| --- | --- |
| Widz to właściciel, na komputerze, w mpv z libass (konfiguracja `C:\Users\MattyMroz\Videos\mpv\portable_config\mpv.conf`) | Prawdą o wyglądzie jest to, co narysuje libass z tą konfiguracją. Galerie rysujemy FFmpeg z libass; zgodność z mpv właściciela trzeba potwierdzić zrzutem z mpv na kilku przypadkach. |
| Często ogląda na x2 | Napis jest na ekranie o połowę krócej niż w oryginale. Czytelność szyldu „w czasie wyświetlania” waży więcej niż przy x1. |
| Dialogi słyszy od lektora | Z ekranu czyta głównie szyldy. Szyldy są najważniejsze, dialogi drugie, a liczba znaków na sekundę w dialogu ma niską wagę. |
| Ekran ultrawide | Napisy nie uciekają w czarne pasy dzięki ustawieniu mpv `sub-ass-force-margins = no`. AniShift nie przesuwa napisów. |
| W mpv brakujące polskie litery czcionki dorysowuje czcionka z `sub-font` (u właściciela Officina) | Słowo w czcionce bez polskich liter miesza dwa kroje. To widoczny błąd, nie kosmetyka. |
| Domyślny tryb zapisu: polskie dialogi i szyldy, wszystko wyświetlane | Każda zmiana układu jest widoczna, więc nie ma ścieżek, na których błąd przejdzie niezauważony. |

## 2. Trzy poziomy reguł

### 2.1 Nienaruszalne

Tych reguł program nie łamie nigdy, także w wyjściu awaryjnym. Wariant, który wymagałby ich złamania, w ogóle nie powstaje.

1. Żaden wyraz ani znak (grafem) nie jest rozcięty między wiersze.
2. Program nie zmienia, nie skraca ani nie gubi treści przekładu. Zmienia tylko układ: rozmiar, ściśnięcie, podział na wiersze, miejsce cięcia.
3. Położenie, ruch, obrót, maska (`\clip`), kolory i przezroczystość szyldu zostają jak w oryginale.
4. Czcionka szyldu zostaje czcionką typesettera. Wyjątek dotyczy tylko stylów dialogowych (sekcja 5).
5. Litery szyldu nie są większe niż w oryginale. Powiększanie nie ma podstawy, bo program nie wie, czy obok jest miejsce.
6. Rysunki (`\p`) i karaoke openingów oraz endingów zostają nietknięte.
7. Napis identyczny z angielskim zostaje bajtowo identyczny.

### 2.2 Unikane za wszelką cenę

Te reguły program łamie tylko wtedy, gdy **żaden** wariant ich nie spełnia. Wtedy wybiera wariant, który łamie je najmniej, i zapisuje przypadek w raporcie przebiegu. To ostatnia deska ratunku, nie zwykła ścieżka.

1. Szyld wychodzi poza ekran bardziej niż angielski oryginał.
2. Szyld nachodzi na inny napis bardziej niż w oryginale.
3. Dialog ma więcej niż dwa wiersze.
4. Dialog wychodzi poza ekran albo libass zawija go sam inaczej, niż zaplanował program.
5. Związek słów chroniony w sekcji 4 zostaje rozdzielony.

### 2.3 Cechy ważone

Wszystko inne to cechy, które oceniamy stopniowo i ważymy ze sobą (sekcje 3 i 4). Żadna nie jest progiem. Liczby z wytycznych (42 znaki, 17 znaków na sekundę, piramida) są punktami odniesienia, nie granicami. Potwierdza to praktyka Shishy: 24–25% jej wierszy ma ponad 42 znaki, a górny wiersz jest krótszy tylko w 56% łamań.

Jak program ocenia „trochę / średnio / bardzo”: każda szkoda dostaje stopień od 0 (brak) do 1 (pełna) i rośnie płynnie między dwoma punktami, bez skoku. Szkody łączą się tak, że każda kolejna dokłada się do sumy, a ważniejsza cecha dokłada więcej. Szczegóły liczbowe są w specyfikacjach technicznych; tu obowiązuje zasada: **żadna szkoda nie zmienia się skokowo na jednej granicy, a każda liczba w specyfikacji technicznej ma przypadek z galerii, który ją uzasadnia, albo jest oznaczona jako do kalibracji.**

## 3. Szyld: kiedy wygląda dobrze

Szyld to napis na ekranie: tablica, plakat, tytuł odcinka, podpis przy postaci, odgłos, okładka.

| Cecha | Waga | Co znaczy „trochę / bardzo” źle | Podstawa |
| --- | --- | --- | --- |
| **Czytelny w czasie wyświetlania** | najwyższa | trochę: drobny, ale do odczytania przy x2; bardzo: trzeba zatrzymać obraz albo nie da się odczytać | Aegisub, unanimated: czytelność ważniejsza niż wierność wielkości |
| **Litery niezniekształcone** | wysoka | trochę: ściśnięcie, którego widz nie zauważa; bardzo: litery wyraźnie wąskie albo spłaszczone | unanimated: skalowanie zniekształca; Shisha ściskała do 77–79% przy dopasowaniu; **brak źródła progu**, kalibracja na galerii |
| **Mieści się tam, gdzie mieścił się oryginał** | wysoka przy ramce znanej z napisów (maska, rysunek); średnia, gdy znana jest tylko szerokość angielskiego tekstu | trochę: wystaje o kilka procent; bardzo: wyraźnie wychodzi poza tablicę lub ramkę | wzorzec obrazu w źródłach; nasz zastępnik: angielski typesetting |
| **Zachowuje kształt i hierarchię** | średnia | trochę: inna proporcja wierszy; bardzo: znika różnica wielkości ważnego słowa (np. „Anioł” w szyldzie piekarni) | unanimated: podział „if the words allow it”; Shisha dzieliła szyld z jednego wiersza na dwa |
| **Nie jest niepotrzebnie mały** | średnia | trochę: zmniejszony, choć obok było miejsce; bardzo: mocno zmniejszony bez żadnego konfliktu | galeria 18.10: „Zdam na Uniwersytet Shirahama!”, podpis stacji Shirahama |
| **Brak sieroty w wielowierszowym szyldzie** | wysoka | jednoliterowe słowo albo przyimek na końcu wiersza szyldu | PWN 54.8.1 (tytuły), Shisha: 0 przypadków |
| **Jednolity krój słowa** | wysoka | polskie litery dorysowane z innej czcionki | fonts.md: 106 ze 184 krojów korpusu nie ma co najmniej jednej polskiej litery |

Jak cechy działają razem, na przykładach z galerii:

- **„Safety Hazard” → „Zagrożenie dla bezpieczeństwa”.** Zmniejszenie do 72% zostawia tekst poza ekranem, czyli łamie regułę 2.2.1, a istnieje wariant bez tego. Ten wariant odpada, zanim zaczniemy ważyć. Wśród dozwolonych wygrywa lekkie ściśnięcie połączone ze zmniejszeniem, czyli wybór właściciela B: czytelność „średnio”, zniekształcenie „trochę”. ([obraz](../../../workspace/.quality/experiments/fuzzy-spec2/cases/a1-grand-blue-safety-hazard.png))
- **„Zdam na Uniwersytet Shirahama!”** Nic nie koliduje i nic nie wychodzi poza ekran. Zmniejszenie daje szkodę „niepotrzebnie mały: średnio”, zostawienie szerszego tekstu daje „wystaje ponad szerokość angielskiego: trochę”. Przy znanej ramce wygrałoby zmniejszenie, przy wolnym tle zostawienie. ([obraz](../../../workspace/.quality/experiments/visual-fixes/signs/03.png))
- **„piętnastyPojawił”.** Dwa sąsiednie szyldy się zlewają, czyli złamana jest reguła 2.2.2. Każdy wariant, który rozdziela napisy, wygrywa z każdym wariantem bez odstępu. ([obraz](../../../workspace/.quality/experiments/visual-fixes/styles/04.png))
- **„Czerwony” przy あか.** Szyld bez konfliktu, przekład dwa razy szerszy od angielskiego. Ściśnięcie i zmniejszenie mają koszt, zostawienie też, bo tekst wyraźnie wystaje ponad szerokość oryginału. Rozstrzyga czytelność: szyld jest duży i znosi zmniejszenie. ([obraz](../../../workspace/.quality/experiments/visual-fixes/signs/05.png))

**Szyld wielowierszowy w oryginale.** Zachowujemy liczbę wierszy, dopóki czytelność nie spada do „bardzo źle”. Wtedy wolno zmienić podział, bo czytelność ma najwyższą wagę. Do potwierdzenia przez właściciela (sekcja 12, punkt 3).

**Szyld w czcionce bez polskich liter.** Program nie zmienia czcionki szyldu (reguła 2.1.4), więc libass dorysuje brakujące litery z czcionki zastępczej. Zostaje to raportowane jako szkoda „jednolity krój: bardzo źle”. Czy dla takich szyldów wolno użyć całej czcionki zastępczej, rozstrzyga właściciel (sekcja 12, punkt 6).

**Środki, których nie używamy:** odstępy między literami (`\fsp`; Shisha nie użyła ich w żadnym z 45 szyldów), zmiana czcionki szyldu, przesuwanie szyldu, skracanie tekstu przez program.

## 4. Dialog: kiedy wygląda dobrze

| Cecha | Waga | Co znaczy „źle” | Podstawa |
| --- | --- | --- | --- |
| **Cięcie po sensie** | najwyższa | trochę: cięcie wewnątrz frazy bez rozrywania związku; bardzo: przyimek od rzeczownika („do / armii”), imię od nazwiska, „się” i „nie” od czasownika, stałe wyrażenie („wysadzić / w powietrze”), złożenie („anielsko-apostolskim / duetem”) | Netflix §4, BBC §3.4 („priority given to linguistic considerations”), eye-tracking; Shisha: 56% łamań po interpunkcji, 0 po przyimku |
| **Brak jednoliterowego słowa na końcu wiersza** | wysoka | „w”, „z”, „i”, „a” na końcu górnego wiersza | Netflix §4 (łam przed przyimkiem i spójnikiem), PWN, Shisha 0/64 |
| **Bez sieroty** | wysoka | jedno krótkie słowo samo w wierszu (przykład „Romantica!”) | praktyka; galeria 18.10 |
| **Jeden wiersz, gdy mieści się na szerokość** | średnia | dwa wiersze krótkiej kwestii | Netflix §12; Shisha zostawia długie kwestie w jednym wierszu do szerokości ramki |
| **Długość wiersza** | niska | trochę: kilka znaków ponad punkt odniesienia; bardzo: wiersz blisko szerokości ekranu | Netflix 42, BBC 37 albo 68% szerokości, Karamitroglou ok. 35; Shisha do ok. 57 znaków w ramce 1600 px |
| **Kształt (krótszy wiersz na górze)** | niska; 1–2 słowa w górnym wierszu: średnia | wyraźnie dłuższy wiersz na górze | Netflix PL §12; BBC daje pierwszeństwo językowi; Shisha 56% |
| **Znaki na sekundę** | niska | dużo powyżej 17 | Netflix PL §16; właściciel słyszy dialog od lektora |

**Gwarancja a heurystyka.** Program rozpoznaje związki słów z zamkniętych list: przyimki, spójniki, zaimki, czasowniki posiłkowe, tytuły, imiona pisane wielką literą, „się” i „nie”. Stałych wyrażeń i złożeń spoza list nie rozpozna; „wysadzić w powietrze” na liście nie ma. Takie przypadki chroni tylko ogólna preferencja cięcia po interpunkcji. Dlatego cięcie po przecinku musi mieć **dużą** przewagę nad cięciem krótszym o kilka znaków, a galeria musi zawierać kwestie, w których te dwa cięcia konkurują. To dokładnie błąd z obrazów [05](../../../workspace/.quality/experiments/visual-fixes/line-breaks/05.png) i [06](../../../workspace/.quality/experiments/visual-fixes/line-breaks/06.png).

**Ratunek.** Gdy żaden układ chroniący związki słów się nie mieści, wolno rozdzielić związek (reguła 2.2.5), nigdy wyraz. Taki przypadek trafia do raportu.

**Dialog przy szyldzie.** Gdy dialog na dole zasłania szyld, cierpi czytelność obu. Przenoszenie dialogu do góry jest dziś poza zakresem, bo program nie przesuwa napisów; raport liczy takie kolizje.

**Wielu mówców w jednym napisie.** Kwestie dwóch osób z myślnikami idą w osobnych wierszach. Napis nadal ma najwyżej dwa wiersze, chyba że inaczej się nie da (reguła 2.2.3).

## 5. Czcionka dialogów

Decyzja właściciela z 18.10: dialogi mają jego czcionkę. Czcionki wydań to zwykle Arial, Trebuchet MS albo Gandhi Sans: kroje bez charakteru, a Gandhi Sans (główna czcionka dialogów w 20 z 40 par) nie ma liter ą, ć, ę, ń, ś, ź, ż. Ustawienie `sub-font` w mpv nie działa na pliki ASS, bo styl z pliku ma pierwszeństwo.

Wymagania:

1. Podmieniamy czcionkę w stylach, w których większość linii czyta lektor. Linie szyldów w takim stylu zachowują czcionkę typesettera.
2. Lokalne zmiany czcionki w linii dialogu (`\fn`, np. pismo odręczne) zostają, bo to zamierzony efekt typesettera.
3. Plik czcionki dołączamy do MKV jako załącznik. Odcinek wygląda tak samo w każdym odtwarzaczu, bez instalowania czcionki.
4. Czcionka musi mieć wszystkie polskie litery. Jeśli ich nie ma, program jej nie użyje i zgłosi to w panelu.
5. Kursywa i pogrubienie: jeśli czcionka ma takie warianty, dołączamy je i libass ich użyje. Jeśli nie ma, libass sztucznie pochyla i pogrubia litery. Czy to wygląda dobrze, oceniamy na galerii.
6. Wielkość: dwie czcionki o tym samym rozmiarze mogą wyglądać na różnie duże. Domyślnie zachowujemy rozmiar ze stylu. Potrzebę korekty oceniamy na galerii.
7. Łamanie wierszy mierzy już nową czcionką. Officina jest o 7% węższa od Gandhi Sans Bold i o 15% od Trebuchet MS Bold, więc zmieni miejsca cięcia.
8. SRT nie ma stylów. Czcionkę ustawia wtedy odtwarzacz (`sub-font`), więc AniShift nic nie zmienia.
9. Plik czcionki wybiera właściciel w ustawieniach panelu.

**Fakt z 18.10 (test mpv właściciela):** w `mpv.conf` jest `sub-font = "ITC Officina Sans Std PL Book"`. Pliku w odmianie Book nie ma na dysku. Nazwa „ITC Officina Sans Std PL Book” to nazwa rodziny zapisana w obu obecnych plikach, Bold i Bold Italic, więc mpv rysuje napisy plikiem **Bold**. Czcionka, którą właściciel ogląda i lubi, to więc Officina Bold.

## 6. Lektor: kiedy decyduje dobrze

1. Lektor czyta każdą kwestię mówioną przez postać, także krótkie okrzyki („Huh?”, „Can it!”).
2. Lektor nie czyta szyldów, tytułów odcinków, odgłosów ani piosenek.
3. Przy wątpliwości lektor raczej czyta. Zgubiona kwestia kosztuje więcej niż przeczytany szyld, bo widz traci treść, a szyld nadal widzi na ekranie.
4. Kopie tej samej linii (animacja, warstwy poświaty) lektor czyta raz, także gdy kopie są w różnych stylach.
5. Decyzję podejmujemy raz, na angielskim źródle. Polski plik, ścieżka lektora i plik szyldów ją dziedziczą. Dziś klasyfikacja działa trzy razy, na różnych plikach, i może dać różne wyniki ([code-map.md](research/code-map.md) §0.2).

**Granice rozpoznania.** Program nie słyszy dźwięku i nie widzi obrazu. Rozpoznaje kwestie po stylu, położeniu, interpunkcji, wersalikach i polu aktora. Zawsze zostaną przypadki sporne, np. „Next Time” i „Preview”, tytuł odcinka w stylu dialogu albo przyśpiewka w tekście. Jak je traktować, rozstrzyga właściciel ([fuzzy-signs-and-split.md](fuzzy-signs-and-split.md) §E). Research nie znalazł profesjonalnych zasad dla polskiego lektora.

## 7. Kursywa i kolory

1. Wyróżnienie trafia na polskie słowo o tym samym znaczeniu co wyróżnione słowo angielskie, także przy innym szyku. Dla najwyżej dwóch wyróżnień w linii znaczenie przenosi tłumacz (znaczniki).
2. Wyróżnienie nigdy nie zaczyna się ani nie kończy w środku słowa.
3. Gradienty litera po literze (kolorowe tytuły) rozkładamy równo na polskie litery. To efekt wizualny, nie znaczenie.
4. Gdy polski tekst nie ma odpowiednika wyróżnionego słowa (np. brakuje „ja”), wyróżnienie znika. Nie przenosimy go na przypadkowe słowo.
5. Wielokolorowy tytuł z więcej niż dwoma wyróżnieniami (Iceblade) dostaje rozkład na granicach słów. Utrata koloru jednego słowa to akceptowalna szkoda, kolor w środku słowa nie jest akceptowalny.

## 8. Wypalanie do MP4

Wypalony napis musi wyglądać jak w MKV, w tych samych czcionkach. Fakt z 18.10: wypalanie przekazuje FFmpeg plik ASS bez katalogu czcionek, więc szyldy wychodzą Arialem ([fonts.md](research/fonts.md)). To błąd do naprawy razem z czcionką dialogów, bo oba wymagają katalogu czcionek odcinka.

## 9. Czego program nie widzi i jak to zastępujemy

| Czego nie wie | Czym to zastępujemy | Kiedy zastępstwo zawodzi |
| --- | --- | --- |
| Gdzie na obrazie jest tablica, japoński tekst, twarz | Szerokość i położenie angielskiego typesettingu; maski i rysunki zapisane w napisach | Angielski napis był węższy niż wolne miejsce (niepotrzebnie zmniejszamy) albo typesetter zostawił tekst bez dopasowania |
| Czy szyld jest ważny dla fabuły | Nic: każdy szyld dopasowujemy tak samo | Drobne szyldy tła dostają tyle samo uwagi co tytuł odcinka |
| Jak wygląda ruch między klatkami | Ocena w kilku punktach toru; takie szyldy raportujemy jako „przybliżone” | Szyld, który po drodze wjeżdża na inny napis |
| Jaką czcionką libass narysuje tekst, gdy pliku brakuje | Indeks czcionek odcinka dopasowany tak jak w libass (rodzina, pełna nazwa, nazwa PostScript) i sprawdzenie polskich liter; brak pliku oznacza wynik „przybliżony” | Czcionki systemowe innego komputera |
| Napisów wpalonych w obraz | Nic | Polski szyld na wpalonym japońskim napisie |

## 10. Jak sprawdzamy

1. **Galeria przed/po na tym samym polskim tekście.** Różnicę na obrazie robi wtedy wyłącznie kod.
2. **Ocena człowieka według sekcji 2–8.** Najpierw ogląda orkiestrator, obraz po obrazie, i nazywa każdy przypadek „lepiej / bez zmian / gorzej”. Pogorszenia pokazuje razem z poprawami. Potem ogląda właściciel.
3. **Krótkie fragmenty w mpv** dla szyldów ruchomych i szybkich scen, przy prędkości x2. Statyczna klatka nie pokaże, czy szyld da się przeczytać w czasie.
4. **Celowe przypadki trudne:** cięcie po przecinku kontra krótsze cięcie, szyld na wolnym tle, sąsiednie szyldy, szyld wielowierszowy, czcionka bez polskich liter, gradientowy tytuł, dialog w czcionce właściciela z kursywą.
5. **Liczby** (szerokość, kolizje, długość wierszy, odsetek zmian) wskazują przypadki do obejrzenia. Same niczego nie dowodzą.
6. **Reguła regresji:** zmiana wchodzi tylko wtedy, gdy na obrazach jest lepiej i nie widać nowych pogorszeń, których nie da się uzasadnić ważeniem cech.

## 11. Czego potrzebujemy i po co

| Rzecz | Po co | Stan |
| --- | --- | --- |
| Pillow | mierzy szerokość tekstu prawdziwą czcionką odcinka | już w projekcie |
| fonttools | czyta wewnętrzne nazwy czcionek (żeby wybrać ten sam plik co libass) i sprawdza polskie litery | nowa zależność, zgoda właściciela z 18.10 |
| FFmpeg z libass | rysuje napisy jak mpv: galerie, sprawdzenie pomiaru, wypalanie MP4 z katalogiem czcionek | już w projekcie |
| mkvmerge | dołącza czcionkę dialogów do MKV jako załącznik (`--attach-file`); załączniki źródła kopiuje już dziś | już w projekcie |
| baza testowa | 40 par napisów z klatkami i czcionkami w `workspace/.quality/` | gotowa |

Nie potrzebujemy rozpoznawania obrazu, OCR ani modelu językowego do decyzji o układzie.

## 12. Decyzje właściciela

Rozstrzygnięte 18.10: rekomendacje z raportu nocnego przyjęte jako wartości domyślne, zgoda na fonttools, czcionka właściciela w dialogach.

Otwarte:

1. **Szyld szerszy od angielskiego na wolnym tle** (sekcja 3, „Zdam na Uniwersytet Shirahama!”): jak bardzo karać? Program nie odróżni wolnego tła od ramki. Propozycja: przy szyldzie bez maski i rysunku kara rośnie powoli, więc lekkie wystawanie przegrywa dopiero z wyraźnym zmniejszeniem. Ustawienie na galerii.
2. **Minimalna czytelna wielkość szyldu:** żadne źródło jej nie podaje. Ustalimy ją na galerii, na szyldach od dużych tytułów po drobne podpisy.
3. **Szyld wielowierszowy:** czy czytelność może zmienić liczbę wierszy oryginału (sekcja 3)? Propozycja: tak, gdy zachowanie wierszy daje „bardzo źle” w czytelności.
4. **Limit długości tłumaczenia:** czy wprowadzić. Shisha skraca szyldy po sensie („CARD DECLINED” → „Odmowa”); program tego nie robi.
5. **Plik czcionki dialogów:** Officina Bold i Bold Italic z folderu mpv (to, co dziś faktycznie widzisz), czy inna czcionka?
6. **Szyld w czcionce bez polskich liter:** zostawić mieszanie krojów czy dla całego takiego szyldu użyć czcionki zastępczej? Propozycja: na razie zostawić i raportować liczbę przypadków, decyzja po galerii.

---
kind: report
status: blocked
baseline: work/quality/21-text-layout @ 56da1979
resulting-state: work/quality/21-text-layout @ 61992e09
completed: 2026-10-19
---

# Kalibracja rdzenia układu tekstu — raport

Kontrakt: [text-layout.md](../text-layout.md) §5.3, plan [02-text-layout.md](../plans/02-text-layout.md) faza C. Stan po rundzie 3 ankiety (t01, t02) i decyzjach koordynatora z 19.10.

## Stan po drugiej decyzji koordynatora (19.10, wieczór)

Decyzje: wymóg odporności ±10% odpada (pary twarde katalogu i ankiety z samym marginesem; wrażliwość i LOO tylko raportowane), pole piosenki „jak dialog” potwierdzone, morfologia zostaje, d10 dostaje dwa jawne układy ważne tylko w polu dialogu, s29 przyjmuje każdy układ bez bardzo poszarpanego wiersza (żaden wiersz nie odbiega od średniej ponad najwyższe kolano nierównowagi z §4.4) i bez wyjścia poza pole.

Wynik: kalibracja nadal **niewykonalna** — z morfologią jedynym minimalnym zbiorem sprzecznym jest **{d10}**, bez morfologii {r03}, {d15}, {d10}.

**d10:** pierwszy jawny układ („…w usprawiedliwiony sposób / uwiecznić cyfrowo…”) ma górny wiersz 0,94 szerokości, więc nie mieści się w polu; wygrywać ma drugi: „Pozwoli mi to również w pełni legalnie / i w usprawiedliwiony sposób uwiecznić cyfrowo / tę niewypowiedzianie słodką istotę!” (0,54/0,66/0,50). Dominuje go „…sposób uwiecznić / cyfrowo tę niewypowiedzianie słodką istotę!” (te same klasy przerw: przed spójnikiem i `phrase`, lepsza równowaga, krótsza dłuższa góra). Zakaz „uwiecznić / cyfrowo” (czasownik | przysłówek) pochodzi z katalogu §6, a rdzeń nie ma cechy, która go wyraża; właściciel tej pary nie oceniał.

Diagnostyka bez d10 (wagi niewpisane): wykonalne, **75/76** przypadków w zbiorze dopuszczalnych; jedyny niespełniony to d10, dla którego rdzeń wybiera dwa wiersze z zakazanym „usprawiedliwiony / sposób” (zgoda przymiotnika przegrywa tu z długością trzeciego wiersza). 192 z 1414 par zawodowców naruszonych.

Do decyzji: (a) pokazać właścicielowi „…uwiecznić / cyfrowo…” obok drugiego jawnego układu d10 — jeśli gorszy, rdzeń potrzebuje klasy „czasownik | określający go przysłówek”; (b) albo zdjąć zakaz z §6. Wag `Final`, testu katalogu i próby ślepej nadal nie ma; po rozstrzygnięciu jedna komenda (`layout_calibrate --blind`) da wyniki, LOO, wrażliwość, listę przypadków przy kolanie i arkusz ślepy (zawodowiec kontra rdzeń z morfologią, identyczne układy poza arkuszem).

Niżej stan sprzed tej decyzji.

## Wynik w jednym zdaniu (przed drugą decyzją)

Kalibracja była **niewykonalna**: z morfologią wyłącznie przez wymóg odporności ±10% na parach ankiety (z samym marginesem wykonalna), bez morfologii także bez tego wymogu.

## Jak liczono

Narzędzie: `python -m scripts.subtitle_quality.layout_calibrate --out <plik.json> [--blind <katalog>]`. Katalog z pomiarami: `tests/services/subtitles/data/text_layout_catalogue.json` (odświeża go `python -m scripts.subtitle_quality.layout_catalogue --fonts <folder czcionek mpv>`).

| Element | Ustawienie | Źródło |
| --- | --- | --- |
| Cechy (szkody) | `HARMS` w `layout.py`: dwie miary długości (szerokość i znaki × 0,76/56), klasy przerw z `gaps.py` (od rundy 3 także `degree`: przysłówek stopnia przed słowem, które określa), zgoda przymiotnika (Morfeusz), nierównowaga w znakach z kolanami 6/10/20/25/30, dłuższa góra, liczba wierszy względem preferowanej, ściśnięcie, zmniejszenie, małe litery (16–30 px), wystawanie poza szerokość oryginału | spec §4.1–§4.6, t02 |
| Poziomy przed wagami | 1) wiersz poza polem (90% ekranu dla dialogu), 2) wiersz ponad maksimum pola, 3) rozerwany związek chroniony, cięcie w krótkim cytacie, sierota | spec §5.2 |
| Filtry | słowo nigdy nierozcięte, wiersz nie zaczyna się od pauzy wtrącenia, wiersz na mówcę, punkty listy „(n)” od nowego wiersza, gdy się mieszczą | spec §4.2, e03 |
| Pary twarde | pierwszy dopuszczalny układ każdego przypadku wygrywa ze **wszystkimi** niedopuszczalnymi kandydatami swojego poziomu ratunku; każda para odporna na zmianę dowolnej wagi o ±10%, poza przypadkami ocenionymi „oba dobre” (q09, q16, q17, r02) | spec §5.3, decyzja koordynatora 19.10 |
| Pary miękkie | q09, q16, q17, r02 | spec §5.3 |
| Zawodowcy | NF+AMZN, 601 kwestii dwuwierszowych; 160 odłożonych na próbę ślepą (ziarno 20261019); z 441 pozostałych 13 pominiętych (układ zawodowca poza poziomem 0), 1414 par miękkich | spec §5.3 p. 3, §7.3 |
| Monotoniczność | waga klasy przerwy nie maleje z poziomem `TIERS` (§4.2); każda waga klasy ≥ 0,001 marginesu | spec §5.3 |
| Cel | kolejno: najmniejsza strata par miękkich ankiety, najmniejsza strata zawodowców, największy margines | spec §5.3 |

Katalog: 76 przypadków rdzenia (d01–d30, s07, s09, s10, s14, s19, s20, s26, s29, e01–e04, e06, e13, e14, e18, e19 oraz 29 pytań ankiety z rund 1–3), 34 przypadki warstwy sceny lub integracji bez testu rdzenia (fazy D–E). Pomiar sumą słów zgadza się z pomiarem całych wierszy prototypu do 0,005 szerokości ekranu.

## Zmiany po rundzie 3

- **t01:** właściciel wybrał „…czterdzieści procent / wyparcia, a na dobitkę…” (53/44) zamiast 63/34. Zakaz „cięcia wewnątrz członu wyliczenia” z d24 usunięty; d24 i r06 przyjmują 53/44, potem 63/34. Sprzeczność {q19, r06} i {d24, q19} znikła.
- **t02:** właściciel wybrał „…dzisiaj / tak bardzo…”. Nowa klasa przerwy `degree` w `gaps.py` (tak, bardzo, zbyt, za, coraz, aż, całkiem, nieco, trochę, dość, równie, „tak samo”). Sprzeczność {d06} znikła.
- **r1:** jeden wiersz w pełnym rozmiarze (0,69 ekranu) wygrywa z dwoma. Pojawiła się sprzeczność {q15, r01}: q15 wymaga, by szyld zmniejszony do szerokości oryginału wygrał z szyldem szerszym od oryginału, a r01 — by piosenka w pełnym rozmiarze, szersza od oryginału, wygrała ze zmniejszoną. Rozwiązanie bez nowej wagi: spec §3.2 daje piosence szerokość wygodną „jak dialog lub oryginał”; przyjąłem „jak dialog” (pole piosenki bez odniesienia do szerokości oryginału). **To interpretacja do potwierdzenia.**

## Sprzeczności (stan obecny)

| Wariant | Minimalne zbiory sprzeczne | Bez wymogu ±10% |
| --- | --- | --- |
| z morfologią | {q04, q11, q13, q19, r03}, {d15, q04, q11, q13, q19}, {d15, d28, q06, q10, q11, q13, q18, r05} | wykonalne |
| bez morfologii | {r03}, {d15} | niewykonalne |

Konfliktów poziomów nie ma.

### Z morfologią: tylko odporność ±10%

Przy najlepszym kompromisie odporność łamią pary, w których o wyniku decyduje długość jednego wiersza blisko kolana:

| Przypadek | Wybór (musi wygrać) | Rywal |
| --- | --- | --- |
| q04 | jeden wiersz 0,74 | „myślę, że on może znaleźć / odpowiedź na twoje pytanie.” |
| d28 | jeden wiersz 0,77 | „Taki właśnie bezmiar / geniuszu kryje Kaguya Shinomiya!” |
| q18 | jeden wiersz 0,64 | „W sumie to myślałem, / żeby nic nie odpisywać.” |
| q11 | „Magia ingerująca we wszystkie / ciągi przyczynowo-skutkowe.” | jeden wiersz 0,80 |
| q13 | „Zabawa, … odgadnąć, / o czym myśli drugi, …” | „…odgadnąć, o czym / myśli drugi, …” |
| r03, d15 | „…przyjęciu powitalnym / jest naprawdę konieczny?” | „…przyjęciu / powitalnym jest…” |

Jeden wiersz o szerokości 0,77 ma wygrać (d28), a 0,80 przegrać (q11); różnica 0,03 szerokości nie wytrzymuje zmiany wag długości lub drugiego wiersza o 10%. Podobnie zgoda przymiotnika ma wygrać z dłuższą górą (r03, d15) przy jednoczesnej silnej preferencji krótszej góry (q19). Z samym marginesem wszystko się godzi, więc nie jest to sprzeczność gustu, tylko za mały odstęp między decyzjami właściciela jak na wymóg ±10%.

### Bez morfologii

r03 i d15 przegrywają na każdej cesze: lista końcówek klasyfikuje „powitalnym | jest” jako `modifier`, a górny wiersz jest dłuższy. Bez zgody przymiotnika z Morfeusza katalog i ankieta tracą — warunek bramki morfologii „katalog i ankieta nie tracą” (§4.7) przemawia za morfologią; warunku „mniej złych cięć w ślepej ocenie” nie da się sprawdzić bez wag.

## Diagnostyka: z morfologią, z samym marginesem (nie wynik kalibracji)

Ten sam program, ale pary twarde bez wymogu ±10% (skrypt poza repozytorium). Wag z tego przebiegu nie wpisano do kodu.

- W zbiorze dopuszczalnych przy wagach z całości: **74/76**. Niespełnione: d10 (zakazane „usprawiedliwiony / sposób”; przypadek bez jawnego układu, więc bez pary w kalibracji), s29 (11 wierszy zamiast 13 źródłowych).
- Test z pominięciem jednego zdarzenia: **63/76**. Niespełnione: d06, d10, d15, d25, d28, q06, q10, q11, q19, r03, s14, s29, t02.
- Wrażliwość ±10% (przypadki, których układ się zmienia): `length_comfortable` ×0,9 → q10, q11, q17, q19; ×1,1 → d06, d28, t02; `extra_line` ×0,9 → d28; ×1,1 → q10, q11, q17, q19; `cut_degree` ×0,9 → d06, t02; `cut_phrase` ×0,9 → s29, ×1,1 → e13; `cut_modifier` ×0,9 → e13.
- Zawodowcy: 192 z 1414 par naruszonych.

## Odkrycie w danych ankiety (r1)

Notatka pytania r1 podawała ok. 2116 px dla pełnego wiersza piosenki; pomiar i przerenderowany obraz dają ok. 1333 px (0,69 szerokości). Koordynator potwierdził błąd; r1 zakodowano jako „jeden wiersz w pełnym rozmiarze wygrywa z dwoma”.

## Czego nie zrobiono

- Wagi `Final` w `layout.py`, test „każdy przypadek katalogu i każde pytanie ankiety w zbiorze dopuszczalnych”, oficjalne LOO i wrażliwość — wymagają wykonalnej kalibracji.
- Próba ślepa morfologii — wymaga wag obu wariantów, a wariant bez morfologii jest niewykonalny nawet z samym marginesem. Komenda z `--blind` zapisze `blind.txt` i `key.json`, gdy wagi będą istnieć.

## Do decyzji

1. **Wymóg ±10% na parach ankiety:** pozostałe sprzeczności wynikają wyłącznie z niego. Możliwości: odporność tylko dla katalogu §6 (sprawdzone: nadal jeden zbiór sprzeczny {d15, d28, q11, q13, q19}, bo d15 i d28 są przypadkami katalogu), mniejszy wymóg, sam margines (wykonalne, wyniki jak w diagnostyce), albo dodatkowe pytanie do właściciela o kwestie w odstępie 0,74–0,80 szerokości (q04, d28, q11), żeby rozsunąć jego decyzje.
2. **Pole piosenki:** potwierdzić „szerokość wygodna jak dialog” (r01 a q15).
3. **Bramka morfologii:** bez morfologii katalog i ankieta są niewykonalne (r03, d15). Czy to wystarcza, czy próba ślepa ma porównać wariant z morfologią z wariantem bez niej skalibrowanym bez r03 i d15.
4. **d10 i s29** nie mają jawnego układu w katalogu, więc nie wchodzą do kalibracji i przegrywają; warto dopisać po jednym dopuszczalnym układzie.

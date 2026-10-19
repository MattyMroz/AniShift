---
kind: report
status: blocked
baseline: work/quality/21-text-layout @ 56da1979
resulting-state: work/quality/21-text-layout @ 9165a732
completed: 2026-10-19
---

# Kalibracja rdzenia układu tekstu — raport

Kontrakt: [text-layout.md](../text-layout.md) §5.3, plan [02-text-layout.md](../plans/02-text-layout.md) faza C.

## Wynik w jednym zdaniu

Kalibracja jest **niewykonalna** w obu wariantach (z morfologią i bez): nie istnieje zestaw wag, przy którym każdy przypadek katalogu i każda odpowiedź z ankiety wygrywa w pełnej przestrzeni kandydatów. Wag nie wpisano do kodu, próby ślepej nie zbudowano. Zgodnie ze specyfikacją sprzeczności idą do właściciela, nie do kodu.

## Jak liczono

Narzędzie: `python -m scripts.subtitle_quality.layout_calibrate --out <plik.json> [--blind <katalog>]`. Katalog z pomiarami: `tests/services/subtitles/data/text_layout_catalogue.json` (odświeża go `python -m scripts.subtitle_quality.layout_catalogue --fonts <folder czcionek mpv>`).

| Element | Ustawienie | Źródło |
| --- | --- | --- |
| Cechy (szkody) | `HARMS` w `layout.py`: dwie miary długości (szerokość i znaki × 0,76/56), klasy przerw z `gaps.py`, zgoda przymiotnika (Morfeusz), nierównowaga w znakach z kolanami 6/10/20/25/30, dłuższa góra, liczba wierszy względem preferowanej, ściśnięcie, zmniejszenie, małe litery (16–30 px), wystawanie poza szerokość oryginału | spec §4.1–§4.6 |
| Poziomy przed wagami | 1) wiersz poza polem (90% ekranu dla dialogu), 2) wiersz ponad maksimum pola, 3) rozerwany związek chroniony, cięcie w krótkim cytacie, sierota | spec §5.2 |
| Filtry | słowo nigdy nierozcięte, wiersz nie zaczyna się od pauzy wtrącenia, wiersz na mówcę, punkty listy „(n)” od nowego wiersza, gdy się mieszczą | spec §4.2, e03 |
| Pary twarde | pierwszy dopuszczalny układ każdego przypadku wygrywa ze **wszystkimi** niedopuszczalnymi kandydatami swojego poziomu ratunku; pary katalogu (§6) z odpornością na zmianę dowolnej wagi o ±10%, pary ankiety z samym marginesem | spec §5.3 |
| Pary miękkie | q09, q16, q17 („oba dobre”), r02 („bez różnicy”) | spec §5.3 |
| Zawodowcy | NF+AMZN, 601 kwestii dwuwierszowych; 160 odłożonych na próbę ślepą (ziarno 20261019); z 441 pozostałych 13 pominiętych (układ zawodowca poza poziomem 0), 1414 par miękkich | spec §5.3 p. 3, §7.3 |
| Monotoniczność | waga klasy przerwy nie maleje z poziomem `TIERS` (§4.2); każda waga klasy ≥ 0,001 marginesu | spec §5.3 |
| Cel | kolejno: najmniejsza strata par miękkich ankiety, najmniejsza strata zawodowców, największy margines (najmniejsza suma wag przy marginesie 1) | spec §5.3 |

Katalog: 74 przypadki rdzenia (d01–d30, s07, s09, s10, s14, s19, s20, s26, s29, e01–e04, e06, e13, e14, e18, e19 oraz 27 pytań ankiety), 34 przypadki warstwy sceny lub integracji opisane w pliku bez testu rdzenia (fazy D–E). Pomiar sumą słów zgadza się z pomiarem całych wierszy prototypu do 0,005 szerokości ekranu.

## Sprzeczności

Najmniejsze zbiory sprzeczne (każdy kolejny po odłożeniu ostatniego przypadku poprzedniego):

| Wariant | Zbiory |
| --- | --- |
| z morfologią | {q19, r06}, {d24, q19}, {d24, d28, q06, q11, q18, r03, r05}, {d15, d24, d28, q11}, {d06} |
| bez morfologii | {r03}, {q19, r06}, {d24, q19}, {d15}, {d06} |

Konfliktów poziomów (niedopuszczalny kandydat z niższym poziomem ratunku niż wybór) nie ma.

### 1. d06 — „tak / bardzo” (niewykonalne nawet bez wymogu ±10%)

Dopuszczalny: „Niech to szlag! Akurat dzisiaj / tak bardzo chciałem porozmawiać z Shinomyią!” (30/44). Zakazany w katalogu: „…Akurat dzisiaj tak / bardzo chciałem…” (34/40). Obie przerwy mają tę samą klasę (`phrase`), zakazany jest równiejszy i też ma krótszą górę, więc przy każdych nieujemnych wagach jest lepszy. Rdzeń nie wie, że „tak bardzo” to jedna grupa (przysłówek stopnia + przysłówek); nie ma jej w `idioms.txt` ani w regułach §4.2.

### 2. q19 przeciw r06 i d24 — krótsza góra a „procent / wyparcia” (niewykonalne nawet bez wymogu ±10%)

- q19 (wybór właściciela): „Gdzie się podziała / moja stara pianka? Przecież tu leżała.” (18/38, przerwa `phrase`) wygrywa z „…pianka? / Przecież tu leżała.” (37/19, koniec zdania). Wynika z tego: waga(fraza) − waga(koniec zdania) < 18 × waga(dłuższa góra) − [przyrost nierównowagi z 18 do 20 znaków].
- r06 i d24 (wybór właściciela i katalog): „Sześćdziesiąt procent szczęścia, czterdzieści procent wyparcia, / a na dobitkę permanentny brak snu.” (63/34, przecinek, górny wiersz 0,89 szerokości) ma wygrać ze wszystkimi kandydatami, w tym z „…czterdzieści procent / wyparcia, a na dobitkę…” (52/45, przerwa `phrase`), którego katalog d24 zakazuje („cięcie wewnątrz członu wyliczenia”), a którego właściciel nie widział (w r6 porównał tylko z trzema wierszami). Wynika: waga(fraza) − waga(przecinek) > 22 × waga(dłuższa góra) + [przyrost nierównowagi z 7 do 29 znaków] + [nadwyżka długości wiersza 0,89].
- Ponieważ waga(przecinek) ≥ waga(koniec zdania), oba warunki nie mogą zajść jednocześnie przy żadnej nieujemnej wadze dłuższej góry i niemalejącej nierównowadze. Rdzeń nie widzi, że „procent / wyparcia” rozrywa grupę rzeczownika z dopełniaczem.

### 3. Bez morfologii: r03 i d15 (oczekiwane)

„Czy cosplay na przyjęciu powitalnym / jest naprawdę konieczny?” przegrywa z „…przyjęciu / powitalnym jest…” na każdej cesze: lista końcówek przymiotnika klasyfikuje przerwę „powitalnym | jest” jako `modifier` (wyższy poziom niż `phrase`), a górny wiersz jest dłuższy. Bez zgody przymiotnika z Morfeusza katalog i ankieta tracą — to pierwszy wynik bramki morfologii (§4.7).

### 4. Zbiory sprzeczne tylko przez wymóg ±10%

{d24, d28, q06, q11, q18, r03, r05} i {d15, d24, d28, q11} są wykonalne przy samym marginesie. Oba zawierają d24 ze sprzeczności 2, więc ich los zależy od jej rozstrzygnięcia.

## Diagnostyka (nie jest wynikiem kalibracji)

Liczone skryptami poza repozytorium, żeby pokazać, czy reszta katalogu się trzyma. Wag z tych przebiegów nie wolno traktować jako wag rdzenia.

| Przebieg | Wykonalny | W zbiorze dopuszczalnych (74) | Niespełnione |
| --- | --- | --- | --- |
| z morfologią, bez {d06, d24, q19, r06} | tak | 68 | d06, d24, q19, r06 (odłożone), d10 (zakazane „usprawiedliwiony / sposób”; przypadek bez jawnego układu, więc bez pary w kalibracji), s29 (12 wierszy zamiast 13 źródłowych) |
| bez morfologii, bez {d06, d15, d24, q19, r03, r06} | tak | 66 | jak wyżej oraz d15 i r03 (cięcie przymiotnik / rzeczownik) |
| z morfologią + dwie cechy próbne: rzeczownik / rzeczownik w dopełniaczu (bez odczytów nierzeczownikowych) i przysłówek stopnia / przysłówek lub przymiotnik jako przerwa wewnątrz frazy | nie | — | nowe zbiory: {q06, q11, q19, r03, r06}, {d24, q06, q11, q19, r03}, {d15, d24, q06, q11, q19}, {d06, d15, d24} — niewykonalne także bez wymogu ±10% |

Wniosek z ostatniego wiersza: dwie dodatkowe cechy nie wystarczają. Przy nich preferencja krótszej góry z q19 nadal zderza się z r06 i z kilkoma innymi wyborami właściciela w pełnej przestrzeni. Dokładanie kolejnych cech na ślepo byłoby łataniem pod przypadki.

## Odkrycie w danych ankiety (r1)

Notatka pytania r1 (`round2.json`) zakłada, że piosenka „Oczko! Nim mrugniesz, skończysz szkołę, więc ruszaj do dzieła!” w pełnym rozmiarze ma ok. 2116 px i nie mieści się na ekranie. Pomiar (`geometry.measure_text`, czcionka KG Fall For You z pary) i obraz `r01.png` dają ok. 1333 px, czyli 0,69 szerokości. Właściciel nie widział więc jednego wiersza w pełnym rozmiarze, który się mieścił. W katalogu r1 zapisano jako „jeden wiersz w dowolnej skali wygrywa z dwoma wierszami” (to rzeczywiście rozstrzygnął), bez wymuszania skali 83%.

## Czego nie policzono

- Test z pominięciem jednego przypadku i wrażliwość ±10% — wymagają wag; narzędzie liczy je automatycznie, gdy kalibracja stanie się wykonalna.
- Próba ślepa morfologii (≥ 150 kwestii, trzy układy w losowej kolejności liter, klucz osobno) — wymaga wag obu wariantów. Ta sama komenda z `--blind` zapisze `blind.txt` i `key.json`, gdy wagi będą istnieć.

## Co musi rozstrzygnąć właściciel lub orkiestrator

1. **d06:** czy rdzeń ma znać grupę „przysłówek stopnia + określane słowo” („tak bardzo”, „zbyt długo”), np. z krótkiej listy przysłówków stopnia, czy zakaz w katalogu d06 jest za ostry.
2. **q19 / r06 / d24:** pokazać właścicielowi na obrazie „…czterdzieści procent / wyparcia, a na dobitkę permanentny brak snu.” (52/45) obok jego wyboru 63/34. Jeśli 52/45 jest gorszy, rdzeń potrzebuje wiedzy o grupie rzeczownika z dopełniaczem; jeśli nie gorszy, katalog d24 i ankieta r6 przyjmują go jako dopuszczalny.
3. **Siła preferencji krótszej góry (q19):** diagnostyka z dodatkowymi cechami pokazuje, że w pełnej przestrzeni wybór q19 zderza się też z q06, q11 i r03. Potrzebne pytanie do właściciela z obrazami par, które wtedy rywalizują, albo decyzja, że ankietę ocenia się tylko w parach, które właściciel widział (dziś spec §5.3 wymaga pełnej przestrzeni).
4. **Interpretacja odporności:** przyjęto, że wymóg ±10% (spec §5.3) dotyczy przypadków katalogu, a dla ankiety wrażliwość jest tylko raportowana. Wymóg dla wszystkich par daje w wariancie z morfologią 8 zbiorów sprzecznych zamiast 5.

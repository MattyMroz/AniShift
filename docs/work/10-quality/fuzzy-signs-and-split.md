# Rozmyte heurystyki szyldów: dopasowanie, podział dialog/szyld, granice stylów — v4

Status: projekt do akceptacji (runda 3.2). Najpierw akceptują agenci, potem właściciel; kod powstaje po obu akceptacjach.
Data: 2026-10-18. Gałąź robocza: `work/quality/07-fuzzy-line-breaks`.
Dowody: audyt `workspace/.quality/experiments/rigidity-audit/report.md`, galeria i modele w `workspace/.quality/experiments/fuzzy-spec2/`: `cases/index.md`, `model.py` → `model-v31.md`, `model_b.py` → `model_b.json` i `model_b_changes.txt`, `model_b_regression.py` → `model_b_regression.txt`. Historia i ograniczenia dowodów: `fuzzy-spec2/notes.md`; stan v2 w `fuzzy-spec2/v2-snapshot/`.
Siostra: `fuzzy-line-breaks.md` (v3.1, zaakceptowana). Ten dokument używa jej modułu łamania do cięć wielowierszowych.

**Zakres dowodów.** `model_b.py` liczy reguły §B na korpusie. `model.py` sprawdza tylko **wybór** §A.4–A.6 wśród kandydatów wyrenderowanych przez libass: filtry działają na prostokątach `measure_boxes`, a szkody na wymiarach wariantów wyliczonych z `fx`, `fy` i `e` ze skali szerokości i wysokości K0 zmierzonych przez libass (`model.py:95–96`). Geometria produkcyjna z A.2–A.3 (spany, pomiar fontem, zawijanie, prostokąty) jest estymacją. Jej zgodność z libass wykazujemy dopiero przy kalibracji (krok F1). Liczby w §A.7 i §B.6 pochodzą z przebiegu modeli z 2026-10-18.

## Aneks v4 (2026-10-18) — nadrzędny wobec wskazanych sekcji

Powód: research [measurement.md](research/measurement.md), [fonts.md](research/fonts.md), [split-and-styles.md](research/split-and-styles.md), cel [visual-quality.md](visual-quality.md) v2.1 i przegląd planu 01 (`reviews/01-plan-*.md`). Gdzie aneks przeczy dalszym sekcjom, obowiązuje aneks.

**A.3 Pomiar (zastępuje metodę „getlength z kerningiem w rozmiarze fs”).** Pillow + fontTools: pomiar glifów w stałym rozmiarze 1000 px i skalowanie liniowe; skala `fs / (winAscent + winDescent)` (fallback typo/bbox jak libass) × `fscx/100`; bez kerningu (libass nie kerninguje bez `Kerning: yes`; taki plik dostaje status przybliżony); szerokość wiersza od lewej krawędzi atramentu pierwszego glifu do prawej ostatniego, plus `fsp·fscx/100` między znakami; obrys tylko przy `\3a < FF` lub `BorderStyle 3`, cień tylko przy `\4a < FF`; blur `+1,83·σ` na stronę (σ = max(`\blur`, `\be`)); `BorderStyle 3`: pudełko z advance + `2·bord` (+`shad`), wysokość +2 px; synteza kursywy + 0,34 × wznios; wysokość z atramentu, interlinia `fs·fscy/100`. Zmierzona zgodność z libass: p90 1,14%, p99 3,4% (n = 4622). Tolerancja `u` dla prawdziwego fontu = 0,012 (p90 zmierzone); dla zdarzeń z glifem zastępczym ten sam pomiar z krojem zastępczym, status przybliżony.

**A.3 Dopasowanie czcionek (zastępuje klucz „1/16, 4, 6”).** Klucze: p3 ID1 (rodzina), p3 ID4 (pełna nazwa), nazwa PostScript; bez rozróżniania wielkości liter; ID16 nie jest kluczem. Pełna nazwa/PS wybiera krój od razu; rodzina wybiera wariant o najmniejszym `73·|Δwaga|/256` + kara kursywy (+1 brak, +4 niechciana). Gdy rodzina jest w czcionkach odcinka (załączniki MKV, czcionka dialogów), wybór tylko spośród nich; w przeciwnym razie czcionki systemowe. Synteza pogrubienia, gdy waga żądana > waga kroju + 150. Brakujący glif: inne kroje tej rodziny z glifem, potem **Arial** tej samej wagi i nachylenia (tak robi FFmpeg i domyślne mpv; mpv właściciela używa węższej Officiny, więc pomiar jest ostrożny). Osadzone `[Fonts]` ASS: poza zakresem tej wersji (status przybliżony, gdy rodzina nie jest znaleziona).

**A.2/A.5 Ramka i kolizje.** Znana ramka = maska `\clip` szyldu. Rysunków `\p` nie łączymy z tekstem (G). Kara FRAME rośnie wolniej dla szyldu bez `\clip` niż z `\clip` (wartości do kalibracji na galerii, decyzja właściciela otwarta). Filtr kolizji ma tolerancję pomiaru jak filtr ekranu: prostokąty sąsiadów i kandydata zmniejszamy o `1 px + u·W/2` z każdej strony przed liczeniem `ΔI`. Ruch (`\move`, `\t`) oceniamy w stanie początkowym i końcowym, status przybliżony. Raport liczy też kolizje szyldu z dialogiem.

**A.4 Szyld wielowierszowy.** Bez zmian: liczba wierszy jak w źródle, D nie istnieje. Zmiana liczby wierszy jest odłożona (visual-quality §3). Cięcia wielowierszowe i kandydat D biorą wyłącznie z modułu łamania (`linebreak.split_lines`), nie z własnej logiki.

**B Podział dialog/szyld — obowiązuje wariant minimalny, pełna reguła B jest odłożona.** Na 245 + 182 plikach wariant minimalny daje 120/120 zmian zgodnych z B, naprawia 23 szyldy z etykiet bez nowych błędów i utrzymuje test regresji 0,9888; pełne B dokłada tylko 5 unikalnych kwestii kosztem 43 szyldów, 12 dubli, 12 niepewnych i spadku regresji do 0,933 (split-and-styles.md H2). Zmiany w obecnym `classifier.py`/`service.py`:
1. `\balt\b` w nazwach dialogowych (`_RE_DLG`).
2. `RE_SONG_NAME` w rozpoznaniu stylu piosenki.
3. Weto linii w stylu DIALOG → SIGN, gdy jednocześnie **etykieta** (brak `[.!?…"»”]`, brak przecinka, brak końcowego myślnika) i **forma** (wersaliki: `rise(udział; 0,6; 0,85) ≥ 0,5`, albo zapis tytułowy z położeniem); linia chroniona (≤ 3 słowa, przy krawędzi, bez położenia) zostaje.
4. Fallback „nic nie czytane → czytaj wszystko” pomija style piosenek (`_RE_SONG`, `RE_SONG_NAME`), karaoke > 0,3 i rysunki > 0,3.
5. Kopie tej samej kwestii w różnych stylach (ten sam znormalizowany tekst, start w odległości ≤ 500 ms) są czytane raz.
6. Decyzje liczymy raz, na źródle: `SPLIT_SUBTITLES` dostaje źródło jako opcjonalne drugie wejście i przenosi decyzje na zdarzenia `Dialogue` `FULL_PL` w tej samej kolejności, sprawdzając tożsamość (czas startu i końca). Brak źródła, SRT bez zgodności albo różnica tożsamości → klasyfikacja `FULL_PL` jak dziś i ostrzeżenie w logu. TTS nie klasyfikuje ponownie `SPOKEN_PL`; dla `FULL_PL` i `SOURCE_SUBTITLES` zostaje klasyfikacja.
Test regresji E8 zostaje na progu 0,9586 (wariant minimalny ma 0,9888).

**C Granice stylów — obowiązuje wariant minimalny, pełne C (StyleState, T1/T2) jest odłożone.** Zmiany w `text.py`: (1) bloki bez `\` (komentarze) nie tworzą granic ani znaczników; (2) T3 zastąpione faktem o stylu: `\i0`/`\b0` otwiera zakres, gdy styl bazowy ma ten atrybut. Daje 447 odzyskanych akcentów (98% strat T3) i usuwa 869 fałszywych zakresów (split-and-styles.md H4). Wyróżnienie pominięte przez tłumacza: jak dziś, rozkład na granicach słów (usuwanie odłożone).

**E — wartości domyślne do czasu galerii (właściciel 18.10 przyjął rekomendacje jako domyślne):** E1 a7 = C, a10 = D; E2 czytelność wg A.6, parametry do kalibracji; E3 FRAME na wolnym tle łagodniej (wyżej); E4 fonttools — zgoda właściciela; E5 próg 0,3 — nie dotyczy (B odłożone); E6–E7 — nie dotyczy w wariancie minimalnym (weto „etykieta × forma” decyduje o wersalikach); E8 próg regresji bez zmian; E9 fallback bez stylów piosenek — przyjęte (B.4 wyżej).

## W skrócie dla właściciela

1. **Szyldy (A).** Mierzymy prawdziwym fontem odcinka. Zamiast Ariala i podłogi 72% wybieramy jeden z pięciu wariantów skali.
2. Dwa ostre filtry: szyld nie wychodzi bardziej poza ekran niż angielski i nie zasłania nowego napisu, jeśli istnieje wariant bez tego.
3. Kryterium „0 naruszeń filtrów” sprawdzamy renderem libass na szyldach statycznych zmierzonych prawdziwym fontem. Szyldy ruchome, obracane, z fontem zastępczym i niezmierzone dopasowujemy tak samo, ale raportujemy je osobno, bez obietnicy.
4. Wśród dopuszczalnych wygrywa wariant o najmniejszej szkodzie. Szkody to: rozmiar, zniekształcenie, szerokość ponad oryginał i wzrost w pionie.
5. Model odtwarza Twój wybór B w a1–a6. W a2 i a9 B to ten sam wariant co C.
6. **Czytanie (B).** Każda linia dostaje „dialogowość” 0–1 i jest czytana od 0,3. Szyld w stylu dialogu wypada, gdy ma dwa silne znaki szyldu.
7. Na etykietach: 425/425 kwestii czytanych, 23 szyldy mniej czytane, 6 nowych szyldów czytanych.
8. Ryzyko B: test regresji stylów spada z bramki 0,9586 do 0,933, bez nowej zgubionej kwestii. Wynika to z czytania małych stylów szyldów ze zdaniami (pytanie E8).
9. **Kursywa i kolory (C).** Akcenty na początku wersu („*Water*?”), negacja kursywy, kolor obrysu i przezroczystość dostają znaczniki, więc w przekładzie trafiają na właściwe słowa.
10. Pytania do Ciebie są w §E.

**Oznaczenia:** **F** fakt sprawdzony w kodzie, danych albo przebiegu modelu; **W** wniosek lub propozycja.
`rise(x; a; b)` wynosi 0 dla x ≤ a, rośnie liniowo i osiąga 1 dla x ≥ b; `fall` = 1 − `rise`; `NOR(…)` = 1 − ∏(1 − składnik).

## 0. Zasady wspólne

1. **Ostry filtr, potem ocena.** Zakazy rozstrzygamy ostro. Rozmytą ocenę stosujemy tylko wśród dopuszczalnych. Gdy dopuszczalnych brak, działa jawny, raportowany **poziom ostateczny**.
2. **Jedna agregacja.** Szkody łączymy wzorem `S = NOR(cᵢ·αᵢ)`. Wynik nie jest zaokrąglany przed wyborem. Rozstrzygnięcie stosujemy tylko przy dokładnie równym S.
3. **Jedna definicja cechy.** Każda cecha ma jedno źródło. Ta sama obserwacja nie zasila dwóch reguł tej samej strony.
4. **Pogorszenie względem źródła.** Wada, którą miał już angielski napis, nie obciąża przekładu.
5. **Jedna decyzja na obiekt.** Serie klatkowe, stosy warstw i kopie dostają jeden wynik.

## A. Dopasowanie szyldu

### A.1 Stan obecny (F)

`fitting.py` mierzy Arialem 64 px bez `\fn/\fs/\fsp` (`_width`). Ma tolerancję 3% (`_WIDTH_TOLERANCE`, l. 27) i podłogę `_MIN_SCALE = 0.72` (l. 24). Obie osie mnoży przez wspólny czynnik (l. 70–71), więc różne `\fscx/\fscy` źródła zachowują proporcję. Działa per zdarzenie: `fit_sign_text(event, text, subs)` jest wołane z `service.py:432`.

Audyt: 982 zmienione szyldy, z czego 192 wymaga skali poniżej podłogi, a 176 po dopasowaniu jest szerszych niż ramka (miara: font stylu). Błąd Ariala wobec fontu stylu ma p90 7,0% i maksimum 21,5%.

### A.2 Obiekt, status i geometria

- **Obiekt** to zdarzenia (bez `\p`) o tym samym tekście widocznym źródła, nakładające się w czasie albo z przerwą ≤ 500 ms (`_FBF_MAX_GAP_MS`). Styl i warstwa nie mają znaczenia. Wszystkie zdarzenia obiektu dostają te same mnożniki `fx`, `fy`, nakładane na ich własne `\fscx/\fscy`, w tym `\t` i `\r`. Prostokąt obiektu to suma prostokątów zdarzeń.
- **Agregacja obiektu.** `n` i `n₂` (A.4) liczymy dla każdego zdarzenia z jego własnymi W i `e`, a obiekt bierze najmniejsze. Każdy stopień α (A.6) liczymy dla każdego zdarzenia z jego własnymi `px`, W i H, a obiekt bierze największy. Filtry działają na sumie prostokątów. Wspólne `fx`, `fy` muszą zmieścić najciaśniejsze zdarzenie, a szkodę widać na zdarzeniu, które cierpi najbardziej. Przykład: ten sam tekst w fs=20 i fs=60 (PlayResY 1080, bez `\fscy`) daje to samo `n` = 0,6, bo glify skalują się z fs. B ma więc `fy` = 0,75, a SIZE obiektu pochodzi ze zdarzenia fs=20 (wynikowe `px` 15, `leg` 0,36, SIZE 0,46), nie fs=60 (wynikowe `px` 45, `leg` 0, SIZE 0,21).
- **Status.** Obiekt jest **statyczny**, gdy wszystkie jego spany zmierzono prawdziwym fontem (A.3, bez fontu ani glifu zastępczego) i żadne jego zdarzenie nie ma: `\move`, `\org`, niezerowego `\frz`/`\fr`, `\frx`, `\fry`, `\fax`, `\fay` ani `\t` zmieniającego `\fs`, `\fscx`, `\fscy`, `\fsp`, `\fr…`, `\fa…` lub `\clip`. Każdy inny obiekt jest **przybliżony**.
- **Prostokąt zdarzenia** liczymy w pikselach skryptu (`PlayRes`).
  - Szerokość wiersza: `W = Σ_span advance(span) · fscx/100 + fsp · (grafemy − 1) + 2·bord + shad`.
  - Wysokość: `H = Σ_wiersze max_span(fs) · fscy/100 + 2·bord + shad`. Dla wielu wierszy W to szerokość najszerszego wiersza.
  - `fx` i `fy` mnożą tylko składnik glifów i `fsp`; obrys i cień, `e = 2·bord + shad`, się nie skalują.
  - Kotwica pochodzi z `\pos` albo z marginesów i `\an`.
  - `bord` i `shad` są skalowane zgodnie z `ScaledBorderAndShadow`.
- **Geometria przybliżona.** `\move` daje sumę prostokątów w obu końcach toru. `\t` daje sumę stanu początkowego i końcowego. `\frz` daje AABB rogów obróconych wokół `\org` (lub kotwicy) w kącie początkowym i końcowym. `\frx/\fry/\fax/\fay` pomijamy. Filtry działają na tej geometrii, ale bez gwarancji (A.5).
- **Zawijanie libass.** Bez `\q2` i `WrapStyle 2` wiersz szerszy niż `PlayResX − MarginL − MarginR` łamiemy zachłannie po zmierzonych słowach, a potem wyrównujemy wiersze jak libass. Pojedyncze słowo szersze niż dostępna szerokość zostaje w jednym wierszu. Kandydat zawinięty przez libass, także K0, ma tyle wierszy, ile daje zawinięcie, i tak liczy GROW (przypadek a4).
- **Region widoczny** to część wspólna ekranu i sumy prostokątów `\clip` obiektu. Wektorowy `\clip` przybliżamy jego AABB, a `\iclip` nie zmienia regionu.
- **Ramka** to W źródła. Rysunków `\p` nie parujemy z tekstem.
- **Sąsiedzi do kolizji** to współwidoczne zdarzenia tekstowe spoza obiektu:
  - dialog w tekście ostatecznym;
  - inne szyldy w prostokącie K0 przekładu, czyli przed ich dopasowaniem. Warianty A–C sąsiada go nie poszerzają, a jego D może go podwyższyć; taki przypadek trafia do raportu.

  `ΔI = I(kandydat) − I(źródło)`, gdzie I to suma pól przecięć z sąsiadami w px². Kolizji z napisem wpalonym w obraz nie wykrywamy.

### A.3 Pomiar prawdziwym fontem

- **Indeks fontów** budujemy raz na odcinek z trzech źródeł:
  1. załączniki MKV, jednym `mkvextract attachments`, jak `scripts/quality/render.py::_extract_attachments`;
  2. katalog `fonts/` pary w skryptach jakości;
  3. fonty systemu.

  Kluczem są rekordy tabeli `name` (1/16, 4, 6, także lokalizowane) oraz bold/italic z OS/2, czyli dopasowanie jak w libass. Wymaga `uv add fonttools` (E4).
- **Spany:** stan `\fn, \fs, \fscx, \fsp, \b, \i, \bord, \shad`; `\r` i `\rStyl` resetują do stylu.
- **Rozmiar.** `\fs` to w libass wysokość `winAscent + winDescent` (bez metryk OS/2: `ascender − descender`). Pillow dostaje więc `size = fs · unitsPerEm / (winAscent + winDescent)`. Szerokość mierzy `getlength` z kerningiem.
- **Niepewność `u`:**
  - prawdziwy font: p90 błędu szerokości wobec libass (`measure_boxes`) z kalibracji na 982 szyldach. Bramka wdrożenia to p90 ≤ 3%. Do kalibracji `u` jest parametrem; model liczy 0,03;
  - brak fontu albo brak glifu w `cmap`: pomiar Arialem lub fontem zastępczym, `u = 0,07` (p90 błędu Ariala z audytu) i status przybliżony.
  - p90 opisuje zbiór, nie ogranicza błędu pojedynczego obiektu.
- **`unmeasured`.** Gdy geometrii nie da się wyznaczyć (nieparsowalne wartości tagów, brak stylu), mierzymy szerokość Arialem z `u = 0,07`, a obiekt dostaje status przybliżony. Kandydatów wybiera samo S, bo filtrom brakuje prostokąta.
- **Koszt.** Pillow mierzy wiersz w ~0,2 ms (F). `mkvextract` + `fonttools` to jeden przebieg na odcinek; czas zmierzymy w kroku F1. Mierzymy obiekty, nie zdarzenia (F: Kaguya S1E02 to 3795 zdarzeń, ale 106 unikalnych trójek font/źródło/przekład).
- **Kontrakt writera:** `fit_signs(subs, texts, fonts) -> dict[int, str]` zamiast `fit_sign_text`, wołane raz na plik w `_translated_file` (`service.py:397–434`). `texts` to przekład po `replace_visible_text`; `fonts` to indeks z kroku potoku, który zna MKV. Najpierw sprawdzamy, czy rozszerzyć `services/composition/fonts.py`.

### A.4 Kandydaci

`n` = (W źródła − e) / (W przekładu − e) dla jednego wiersza; `n₂` to samo dla najszerszego wiersza przekładu w dwóch wierszach (`e` z A.2).

| Kandydat | fx | fy | Warunek |
| --- | --- | --- | --- |
| K0 | 1 | 1 | zawsze |
| A proporcjonalny | min(1, n) | min(1, n) | n < 1 |
| B mieszany | min(1, n) | min(1, n / 0,8) | n < 1 |
| C poziomy | min(1, n) | 1 | n < 1 |
| D dwa wiersze | min(1, n₂) | min(1, n₂) | źródło jednowierszowe, ≥ 2 słowa, bez `\q2`/`WrapStyle 2`; cięcie z modułu łamania |

Gdy n ≥ 0,8, B i C to ten sam wariant (fy = 1). Tak jest w a2 i a9.

**Źródło wielowierszowe.** Przekład dzielimy na tyle wierszy, ile ma źródło, z cięciami według `fuzzy-line-breaks.md`. `n` liczymy po najszerszym wierszu. D nie istnieje.

**Ostro odrzucamy:** powiększenie, cięcie słowa, zmianę geometrii (`\pos`, `\move`, `\org`, `\clip` i obroty zostają), zmianę `\p`, karaoke OP/ED. Tekst identyczny ze źródłem daje wynik bajtowo identyczny.

### A.5 Filtry i poziomy ostateczne

1. **Filtr ekranu.** Wyjście poza region widoczny liczymy osobno w poziomie i w pionie, jako przyrost względem źródła, w px skryptu, po zawinięciu libass:
   - poziom: dopuszczalne ≤ 1 px + `u` · W kandydata;
   - pion: dopuszczalne ≤ 1 px.
2. **Filtr kolizji.** Kandydat z `ΔI > 0` jest niedopuszczalny.

Kolejność: najpierw ekran, potem kolizja, potem najmniejsze S (A.6).

**Poziomy ostateczne:**

- `fallback_screen`: gdy ekranu nie przechodzi żaden kandydat, pulą są kandydaci o najmniejszym `max(przyrost poziomy, przyrost pionowy)`;
- `fallback_collision`: gdy w puli nikt nie ma `ΔI = 0`, zostają kandydaci o najmniejszym ΔI.

Remis w puli rozstrzyga najmniejsze S.

**Zakres obietnicy (W).** Filtry działają na estymacji A.2, więc nie dają gwarancji z samej konstrukcji. „0 przyrostów wyjścia poza ekran i kolizji” to kryterium empiryczne §D: sprawdzamy je renderem libass (`measure_boxes`) na obiektach statycznych. To, czy istniał kandydat spełniający filtr, rozstrzyga ten sam pomiar libass, nie wzór. Obiekty przybliżone przechodzą tę samą procedurę, bez obietnicy. Raport liczy je osobno.

### A.6 Szkody i wybór

`px = fs · fscy/100 · 1080 / PlayResY` to wysokość wiersza w px 1080p. `q = fx/fy`.

| Szkoda | Stopień α | c |
| --- | --- | --- |
| SIZE rozmiar | `1 − (1 − 0,9·leg)(1 − 0,5·shrink)`, gdzie `leg = rise(min(px_źródła; 30) − px; 0; 14)`, `shrink = fall(fy; 0,4; 1,0)` | 1,0 |
| DIST zniekształcenie | `fall(q; 0,5; 0,8)`; q ≥ 0,8 nie szkodzi | 0,9 |
| FRAME szerzej niż oryginał | `rise(max(0; W_kand/W_źródła − 1 − u); 0; 0,25)` | 0,6 |
| GROW wzrost w pionie | `rise((H_kand − H_źródła)/H_źródła; 0; 1)` | 0,4 |

SIZE to jedna szkoda „rozmiar” z dwoma składnikami:

- `leg` to bezwzględna czytelność, działająca tylko dla małego tekstu (drabina a0);
- `shrink` to utrata rozmiaru oryginału, działająca także dla dużego tekstu (a1: 90 → 51 px, `leg = 0`).

Kolizja nie ma już szkody, bo rozstrzyga ją filtr.

Wybór to najmniejsze S w puli z A.5. Przy równym S kolejno decydują: mniej wierszy, większe fy, większe fx, a na końcu K0 przed innymi.

### A.7 Wyniki na galerii (F, `model-v31.md`)

Wybór wśród wariantów wyrenderowanych przez libass, nie przebieg geometrii A.2 (zob. „Zakres dowodów”).

| Arkusz | Status | Recenzenci | Model | S wybranego / najbliższy inny wariant |
| --- | --- | --- | --- | --- |
| a1 Grand Blue, poza ekranem | statyczny | B | B | 0,365 / D 0,447 (K0: ekran +287 px) |
| a2 Detective, tytuł | statyczny | B = C | B = C | 0,000 / A 0,107 |
| a3 Kaguya, ramka `\p` | przybliżony (font zastępczy) | B | B | 0,082 / A 0,233 |
| a4 Kaguya, 49 warstw przy krawędzi | przybliżony | B | B | 0,188 / A 0,317 (K0 i D: ekran +11 px) |
| a5 Seihantai „Czerwony” | przybliżony | B | B | 0,429 / A 0,512 |
| a6 Seihantai „Publiczny” | przybliżony | B | B | 0,174 / A 0,306 (K0: kolizja +96 px²) |
| a7 Seihantai, stacja | statyczny | — | C | 0,150 / B 0,168, prawie remis (E1) |
| a8 Kaguya, `\clip` | przybliżony | — | B | 0,026 / C 0,074 |
| a9 Kaguya, font zastępczy | przybliżony (font zastępczy) | — | B = C | 0,000 / K0 0,038 |
| a10 Seihantai, `\move`, przekład 2,7× dłuższy | przybliżony | — | D | 0,833 / C 0,905 (K0: ekran +31 px) |

Model odtwarza 6/6 ocen recenzentów. Względem v3 zmieniły się:

- statusy a3 i a9 (font zastępczy);
- S w a5 i a10, bo `e` się nie skaluje. Ich FRAME 0,08 to artefakt galerii: `fx` wariantów liczono jeszcze liniowo, a `n` z A.4 dałby FRAME 0;
- K0 w a4 liczy dwa wiersze zawinięcia libass, ale i tak odpada na filtrze ekranu.

Żaden wybór się nie zmienił.

## B. Podział dialog / szyld

### B.1 Stan obecny (F)

`classifier.py`:

- schodkowy wynik stylu (l. 169–188), progi 0,55/0,25, kategoria `UNCERTAIN`;
- wczesny `return DIALOG, 0.85` po samej nazwie stylu (l. 167–168);
- `line_category` (l. 235–244): actor szyldu daje SIGN poza wyjątkiem Fuji; `UNCERTAIN` rozstrzyga nazwa; `\an4–6` w stylu DIALOG daje SIGN.

`service.py`:

- `collapse_fbf` scala zdarzenia o kluczu `(styl, tekst)` z przerwą ≤ 500 ms;
- gdy nic nie jest czytane, czytane jest wszystko poza rysunkami (l. 259–261).

Potwierdzone błędy:

- `Alt` w Joshiraku i Uzaki jest gubione;
- „TWO GENIUSES' WAR OF LOVE” w `Default` jest czytane;
- `_RE_SONG` nie łapie `EDup`, `OP_EN_blue`, `ED1 - ENG`, `IN01`.

### B.2 Ostre reguły

- Rysunek `\p` → szyld. SRT → wszystko czytane. Jawne `spoken_styles` → wybór po stylu, jak dziś.
- **Styl piosenki lub notki** (styl „ostry”) → szyld. Należą tu style, w których:
  - rysunki mają > 0,3 udziału albo karaoke > 0,3;
  - nazwa pasuje do `_RE_SONG`, `_RE_NOTE` albo nowego wzorca `RE_SONG_NAME` = `(?:^|[^a-z])(?:nc)?(?:op|ed|ins|insert|in(?=[0-9]))(?:[0-9]+|up|down|bg)?(?:$|[^a-z])` (bez rozróżniania wielkości liter).
- **Actor szyldu** (`_RE_SIGN_ACTOR`, fullmatch) → szyld. Wyjątek: linia jest zdaniem (B.4), nie ma położenia (B.4) i należy do stylu bazowego (B.3). Taka linia przechodzi zwykłą ocenę.

### B.3 Styl bazowy i cechy stylu

Statystyki liczymy jak dziś na zdarzeniach po `dedup_animation`. Dla stylu bierzemy:

- n — liczbę linii;
- f — udział linii stylu we wszystkich liniach;
- p — udział linii z **położeniem** w definicji z B.4;
- i — udział linii z interpunkcją zdaniową;
- L — średnią długość tekstu.

**Jedna definicja położenia.** p liczymy tą samą cechą co położenie linii. `\fad`, `\clip` i `\t` przestały więc liczyć się jako pozycjonowanie. Bez tej zmiany styl dialogu z `\fad` w każdej linii nie miałby szans na odczyt (styl z p ≥ 0,5 i n ≥ 10 daje D ≤ 0,26). Koszt na korpusie (F, przebieg kontrolny z dawnym `_RE_POS`): +14 odczytów i +1 czytany szyld z etykietą. To głównie tytuły Kusuriya (`Title`, `Ep_Title`, `Next_Ep_Title`) i przyśpiewka Marumaru `Wahaha` (E7).

**Styl bazowy** to styl o największym n spośród stylów nieostrych z p < 0,5. Remis rozstrzyga wcześniejsze pierwsze wystąpienie. Wtedy:

- `i_rel = i / i_bazy`, gdy `i_bazy > 0`, w przeciwnym razie `i_rel = i`;
- `sim` to średnia 7 zgodności z bazą (sama baza ma sim = 1):
  - nazwa fontu (1/0);
  - rozmiar `max(0; 1 − |Δ|/max(1; rozmiar_bazy))`;
  - bold (1/0);
  - italic (1/0);
  - kolumna wyrównania, równa 1 tylko wtedy, gdy oba style są poza środkowym rzędem i mają tę samą kolumnę;
  - MarginV `max(0; 1 − |Δ|/max(10; MarginV_bazy))`, czyli wartość w [0, 1];
  - kolor wypełnienia (1/0).

  Kolor obrysu pomijamy (`Alt` to drugi mówca).

**Brak bazy** (wszystkie style ostre albo pozycjonowane), brak definicji bazy w `[V4+ Styles]` albo brak definicji ocenianego stylu: `sim = 0,5` (także dla samej bazy bez definicji). Bez bazy także `i_rel = i`. Wtedy RS3 = 0, a RS8 działa w pełni (0,7), czyli celowo po stronie szyldu. Dotyczy 40 z 245 plików korpusu (F): głównie plików samych szyldów i NC. Gdy w takim pliku nic nie przekroczy progu, działa dzisiejszy fallback „czytaj wszystko” (B.5).

| Reguła | Strona | Stopień | c |
| --- | --- | --- | --- |
| RS1 | dialog | min(rise(f; 0,10; 0,25); fall(p; 0,15; 0,35)) | 0,85 |
| RS2 | dialog | min(rise(i; 0,25; 0,5); fall(p; 0,15; 0,35)) | 0,6 |
| RS4 | dialog | min(rise(L; 6; 10); 1 − rise(p; 0,5; 0,7); rise(i_rel; 0,25; 0,5)) | 0,3 |
| RS5 | szyld | rise(p; 0,5; 0,7) | 0,85 |
| RS6 | szyld | min(fall(i_rel; 0,25; 0,5); rise(n; 3; 8)) | 0,85 |
| RS3 wygląd | dialog | rise(sim; 0,75; 0,9) | 0,8 |
| RS7d wygląd | dialog | nazwa pasuje do `_RE_DLG` | 0,2 |
| RS8 wygląd | szyld | fall(sim; 0,5; 0,7) | 0,7 |
| RS7s wygląd | szyld | nazwa pasuje do `_RE_SIGN` | 0,2 |

`d_s = NOR(RS1, RS2, RS4)`, `s_s = NOR(RS5, RS6)`, `look_d = NOR(RS3, RS7d)`, `look_s = NOR(RS8, RS7s)`.

### B.4 Cechy linii

- **zdanie:** tekst zawiera `[.!?…"»”]` albo kończy się `—`, `–` lub `-`;
- **etykieta** = brak zdania i brak przecinka;
- **wersaliki:** `caps = rise(udział wielkich liter; 0,6; 0,85)` przy ≥ 2 literach, w przeciwnym razie 0;
- **zapis tytułowy:** ≥ 2 słowa, co najmniej jedno ma > 3 litery, a każde słowo > 3 litery zaczyna się wielką;
- `form = max(caps; tytułowy) · etykieta`;
- **położenie** (1/0): `\pos`, `\move`, `\org`, niezerowe `\fr…` (`\frz0` się nie liczy), inline `\an` w innej kolumnie niż styl albo efektywne `\an` (inline lub ze stylu) w środkowym rzędzie. Środek ekranu to miejsce szyldu, nie napisu dialogowego. Dlatego styl środkowego rzędu ma p = 1 i nie może być bazą;
- **krawędź:** z y pierwszego `\pos`/`\move` liczymy `max(rise(y/PlayResY; 0,7; 0,8); fall(y/PlayResY; 0,2; 0,3))`; bez nich krawędź = 0 dla `\an4–6`, a w pozostałych przypadkach 1;
- **osoba:** actor niepusty, < 50% zdarzeń pliku, nie actor szyldu.

| Strona | Składnik | c |
| --- | --- | --- |
| dialog | zdanie · krawędź · (1 − położenie) | 0,7 |
| dialog | zdanie · (1 − krawędź) | 0,5 |
| dialog | osoba | 0,3 |
| szyld | form | 0,75 |
| szyld | położenie · etykieta | 0,6 |
| szyld | położenie · zdanie | 0,3 |

`s_lin = NOR(składniki szyldu)`, `d_l = NOR(look_d, składniki dialogu)`, `s_l = NOR(look_s, składniki szyldu)`.

### B.5 Dialogowość, weto, serie i próg

- `D_s = 0,5 + (d_s − s_s)/2` oraz `D_l = 0,5 + (d_l − s_l)/2`. Brak dowodów daje 0,5.
- `w = 0,4 + 0,4 · rise(n; 3; 10)` i `D⁰ = w · D_s + (1 − w) · D_l`.
- **Weto.** Są trzy silne wskazówki: `caps ≥ 0,5`, etykieta i położenie.
  - Weto działa przy co najmniej 2 silnych wskazówkach.
  - Wyjątek: linia **chroniona**, czyli ≤ 3 słowa, krawędź ≥ 0,5 i brak położenia.
  - Weto daje `D = min(D⁰; 1 − s_lin)`, a bez weta `D = D⁰`.
  - Weto liczy wyłącznie dowody linii. Wygląd stylu (`look_s`) siedzi już w D⁰. Gdyby wszedł także do limitu, ciąg dalszy zdania małą literą w stylu niepodobnym do bazy mógłby spaść z 0,40 do 0,12.
- **Serie.** Serie `collapse_fbf` (ten sam styl i tekst, przerwa ≤ 500 ms) wyznaczamy przed maską. Cała seria dostaje decyzję zdarzenia o największym D. Ostre szyldy mają D = 0 i biorą udział w tym wyborze.
- **Ograniczenie zachowane z dziś (F).** Klucz `(styl, tekst)` scala także identyczne kwestie różnych actorów, jeśli dzieli je ≤ 500 ms. Na korpusie dotyczy to 51 czytanych serii. Część to chóry („Happy New Year.” dwóch postaci), część to dwie osobne kwestie („Hey.” SATO i YAMADA). Zmiana klucza dotyka sprzężenia `collapse_fbf` ↔ writer (`AGENTS.md` subtitles), więc zostaje poza zakresem.
- **Fallback pliku**, jak dziś (`service.py:259`): gdy nic nie jest czytane, czytane jest wszystko poza rysunkami. Korpus (F): dziś 35 plików, v3 39 (E9).
- **Czytamy, gdy D ≥ 0,3.** Próg to heurystyka kosztowa, nie skalibrowane prawdopodobieństwo. Utrata kwestii jest kilka razy gorsza od przeczytanego szyldu; dla k = 2,5 wzór 1/(1 + k) daje ≈ 0,29.

### B.6 Wyniki (F, `model_b.py`, 2026-10-18, 245 plików)

Poprawka `\frz0` z v3.1 nie zmienia żadnej decyzji na korpusie (`model_b_changes.txt` identyczny z v3).

| Etykiety wysokiej pewności (`labels/split-labels.csv`) | Dziś czyta | v3 czyta |
| --- | --- | --- |
| dialog (425) | 425 | 425 |
| szyld (8732) | 55 | 38 (23 naprawione, 6 nowych) |

Korpus bez plików OP/ED/NC ma 201 zmienionych unikalnych linii (pełny korpus: 204):

- **108 przestaje być czytanych:**
  - szyldy wersalikami lub z położeniem („TWO GENIUSES' WAR OF LOVE”, „LITTLE KAGUYA”, „WATER-BASED - ALL PURPOSE PAINT”);
  - szyldy Joshiraku („Skin Cream”, „Whirling Lake”);
  - style `OP1-Light_cyber_…` (`RE_SONG_NAME`).
- **93 zaczyna być czytanych:**
  - kwestie `Alt` w Joshiraku i Uzaki;
  - „Next Time”/„Preview”, tytuły Kusuriya, Iceblade i Joshiraku `brush2` (także opisy produktów);
  - zdania z położeniem w first-kiss i Kaguya S3 (`Shenanigans`, `GJM_Main_1080p`);
  - fragmenty liter z `\pos` w Uzaki 03 („O”, „u”, „c”, „h”, „!”) (E7).

**Test regresji stylów** (`model_b_regression.py`, zbiór `mm_avh`, 984 style) liczy styl jako dialog, gdy v3 czyta **ściśle ponad połowę** jego linii. Remis to szyld (4 style, wszystkie szyldy). Styl bez ocenianych linii też jest szyldem, bo nie ma czytanej linii (11 stylów, wszystkie szyldy). Wynik: 918/984 = 0,933 wobec bramki 0,9586, zero nowych zgubionych stylów dialogu, a allowlista bez zmian. Według samego `D_s > 0,25` wynik to 0,898 i jeden nowy zgubiony styl (`Masamune - Alter`). Dlatego bramka musi liczyć decyzje linii, nie samą kategorię stylu.

Spadek dokładności to 64 style szyldów, w których v3 czyta ponad połowę linii. Są to małe style ze zdaniami, np.:

- Dr Stone `Acquired_Text`, `Sign_Basic`;
- Isekai Nonbiri `Q2`–`Q11`;
- `selfplug`, `On Top`, Qwaser `… sign N`.

Przy n ≤ 4 waga stylu wynosi ≤ 0,46, więc zdanie samo przekracza próg (E8).

Kontrpróby (arkusz `cases/b1-split-counter-examples.png`):

| Przypadek | Dziś | v3 |
| --- | --- | --- |
| „CHRISTMAS CAKE ACCEPTING ORDERS” `\an4` w `Default` | nie czyta | nie czyta (weto) |
| „IRRITATED” `\an7`, „KAGUYA” z `\pos` (first-kiss) | czyta | nie czyta (weto, D = 0,10) |
| „TWO GENIUSES' WAR OF LOVE” bez tagów | czyta | nie czyta (weto, D = 0,25) |
| Koori „WATER-BASED - ALL PURPOSE PAINT” `\an8` | czyta | nie czyta (D = 0,25) |
| Koori „EEK”, „IRRITATED” `\an8` (kolumna jak styl) | czyta | czyta (chronione, E6) |
| Seihantai „Huh?” dwóch postaci, 0,6 s | czyta oba | czyta oba |
| Kaguya „Kaguya!” + kopie `\move` | czyta raz | czyta raz |
| „THAT CAN'T POSSIBLY BE SEX!!” `\an9` | czyta | czyta (zdanie) |

## C. Granice stylów

### C.1 Stan obecny (F)

`text.py::_marked_boundaries` (l. 280–296) bierze wewnątrzwersowe granice tagów przy krawędzi słowa. Nie stawia znaczników, gdy:

- granic jest > 4;
- któraś leży w środku słowa;
- pierwsza ma `\i0/\b0/\u0/\s0`;
- któryś zakres nie ma słów.

`_span_markers` paruje granice naprzemiennie. Skutek:

- „{\i1}Water{\i0}?”, „{\i1}Why{\i0} are you here?” i negacja kursywy w stylu kursywnym tracą akcent;
- granica samego efektu (`\bord`, `\blur`) bywa uznana za zakres.

`_monotonic_anchors` (l. 494–502) przesuwa kotwice markerów, gdy wcześniejszy tag trafi dalej niż marker.

### C.2 Kontrakt (W)

1. **Stan bazowy.** `StyleState(italic, bold, underline, strikeout, primary_colour, outline_colour, alpha, fontname)` pochodzi ze stylu zdarzenia. `alpha` to czwórka 1a–4a; `\alpha` ustawia wszystkie cztery. `\r` przywraca stan stylu, a `\rStyl` stan stylu nazwanego. Definicje bierzemy ze słownika stylów pliku (`subs.styles`), przekazanego razem z `base`. Nieznany `\rStyl` działa jak `\r`, tak jak w libass.
2. **Stan efektywny** to stan każdego grafemu po przejściu tagów. Tagi, które nie zmieniają atrybutów z pkt 1 (`\bord`, `\blur`, `\fs`, `\fad`, `\pos`, `\t` itp.), są **efektami**. Atrybut, który zmienia się wewnątrz któregoś słowa linii (gradient), jest w tej linii efektem. Atrybut o tej samej wartości na wszystkich słowach linii należy do bazy tej linii (C.3).
3. **Zakres** to maksymalny ciąg całych słów o tym samym stanie efektywnym, różnym od bazowego. Liczymy go na tekście połączonym ze wszystkich wersów, więc może przechodzić przez `\N` i zaczynać się na początku wersu. Kolejne słowa w różnych stanach tworzą osobne zakresy. Zakresy są więc zawsze sekwencyjne i nigdy zagnieżdżone, zgodnie z walidacją kolejności `<s1></s1><s2></s2>` (`text.py:355`).
4. **Cała linia.** Zakres obejmujący wszystkie słowa linii nie jest akcentem. Tagi krawędzi i tak zostają na krawędzi. Jawny wyjątek: linia z jednym słowem, po którym poza zakresem stoi interpunkcja (`{\i1}Water{\i0}?` → `<s1>Water</s1>?`).
5. **Wybór** najwyżej 2 zakresów (`s1`, `s2`, w kolejności tekstu). Ważność zakresu to waga najważniejszego atrybutu różnego od bazy:
   - kursywa i pogrubienie: 1,0;
   - kolor wypełnienia, kolor obrysu i font: 0,6;
   - przezroczystość, podkreślenie i przekreślenie: 0,4.

   Remis rozstrzyga wcześniejszy zakres.
6. **Reszta.** Granice niewybranych zakresów i efekty przy krawędzi słowa idą przez warstwę granic słów, jak dziś (`_snapped`). Efekty w środku słowa rozkładamy jak dziś (`_spread_inside`). To zastępuje warunki T1–T3 z C.1.
7. **Round-trip.**
   - `marked_text(text, base)` wysyła znaczniki, a `restore_markers` bez zmian odtwarza je po łamaniu.
   - `replace_visible_text(text, new_text, base)` ustawia tagi granic wybranych zakresów na pozycjach znaczników, także na otwarciu na pozycji 0.
   - **Kotwice znaczników są stałe.** Nieoznaczony tag, który w źródle poprzedza otwarcie, przycinamy do ≤ pozycji otwarcia. Tag po zamknięciu przycinamy do ≥ pozycji zamknięcia. Tag między nimi trafia do przedziału [otwarcie, zamknięcie].
   - `_monotonic_anchors` porządkuje wyłącznie nieoznaczone tagi.
   - Walidacja pozostaje ostra: kolejność, niepusty zakres, słowa bez stylu zostają, gdy źródło je miało, oraz `strip_span_markers(marked) == visible_text`. Przy uszkodzeniu stosujemy rozkład jak dziś.
8. **Przekazanie stylu bazowego** (`base` i słownik stylów pliku):
   - `translation_handler.py` w `spoken_lines` (l. 420), `displayed_lines` (l. 430) i `translation_verses` (l. 453);
   - writer `service.py:428`;
   - `fit_signs` (A.3).

   Dla SRT bazą jest stan domyślny (atrybuty wyłączone, kolory domyślne).

### C.3 Przypadki (baza: domyślny `SSAStyle`, wypełnienie białe, obrys czarny)

| Źródło | `marked_text` v3 |
| --- | --- |
| `{\i1}Water{\i0}?` | `<s1>Water</s1>?` (wyjątek pkt 4) |
| `{\i1}Why{\i0} are you here?` | `<s1>Why</s1> are you here?` |
| `This scene is inspired by\N{\i1}Idiots Are Coming in Tanks{\i0} (1964).` | `This scene is inspired by <s1>Idiots Are Coming in Tanks</s1> (1964).` |
| `For {\i0}you{\i1} to call them excellent,` w stylu kursywnym | `For <s1>you</s1> to call them excellent,` |
| `{\i1}A{\i0} b {\i1}c{\i0} d {\i1}e{\i0} f` | `<s1>A</s1> b <s2>c</s2> d e f` |
| `{\c&H0000FF&}Red {\i1}hot{\i0} sword{\c&HFFFFFF&} here` | `<s1>Red</s1> <s2>hot</s2> sword here` (trzy zakresy sekwencyjne, wybór 1,0 i wcześniejszy 0,6) |
| `I hear a {\1a&H80&}ghost{\1a&H00&} voice.` | `I hear a <s1>ghost</s1> voice.` |
| `{\fnArial\pos(605,317)}EP 2{\3c&H93CC2E&\c&HFFFFFF&}\h\h\hDeath Games and Demons` | `EP 2 <s1>Death Games and Demons</s1>` (obrys, jak dziś) |
| `T{\3c&H1&}h{\3c&H2&}e {\3c&H3&}Ice` | bez znaczników (`\3c` zmienia się w słowie → efekt) |
| `{\i1}but if I did,{\i0}\N{\i1}it wouldn't be for her.{\i0}` | bez znaczników (cała linia) |
| `{\b0}Sign` w niepogrubionym stylu | bez znaczników (brak zmiany stanu) |
| `{\b1}Isn't that just {\i1}adorable{\i0}?` w niepogrubionym stylu | `Isn't that just <s1>adorable</s1>?` (`\b1` na wszystkich słowach należy do bazy linii) |

**Zmiana szyku z efektem i akcentem.**

- Źródło: `I really, truly {\bord4}really {\i1}love{\i0} it.`, gdzie `\bord4` jest efektem.
- `marked_text`: `I really, truly really <s1>love</s1> it.`
- Przekład: `<s1>Uwielbiam</s1> to naprawdę, szczerze.`
- Warstwa słów stawia `{\bord4}` na pozycji 13 („naprawdę”), a znaczniki dają otwarcie 0 i zamknięcie 9. Tag poprzedza otwarcie, więc przycinamy go do 0.
- Wynik: `{\bord4}{\i1}Uwielbiam{\i0} to naprawdę, szczerze.`
- Bez przycięcia `_monotonic_anchors` przesunąłby oba tagi kursywy na 13 i akcent by zniknął: `Uwielbiam to {\bord4}{\i1}{\i0}naprawdę, szczerze.`

## D. Kryteria akceptacji i zmiany testów

**A** (pomiar libass `measure_boxes` po obu stronach, 982 szyldy):

- Model odtwarza oceny recenzentów w a1–a6 i ma opisane wybory w a7–a10.
- Obiekty statyczne (kryterium empiryczne, pomiar libass zarówno wyniku, jak i istnienia kandydata):
  - 0 przekroczeń filtra ekranu (1 px + u·W poziomo, 1 px pionowo), gdy istniał kandydat w tolerancji;
  - 0 przyrostów kolizji wobec sąsiadów z A.2, gdy istniał kandydat bez kolizji;
  - liczby `fallback_screen` i `fallback_collision` w raporcie.
- Obiekty przybliżone (także z fontem zastępczym) i `unmeasured`: osobny raport z tymi samymi liczbami, bez progu.
- Zgodność estymacji A.2 z libass (W, H, liczba wierszy po zawinięciu) raportowana przy kalibracji.
- **Szerszy od oryginału** to W wyniku > (1 + u) · W źródła. Wynik v3 musi mieć ich mniej niż dzisiejszy writer zmierzony tak samo; 176 z audytu to szacunek starą miarą.
- Rozkład px raportowany. Kalibracja: p90 ≤ 3% (do tego czasu `u` jest kryterium, nie wynikiem).

**B:**

- 0 utraconych kwestii z etykietami „dialog / wysoka” (v3: 425/425).
- Każda zmiana decyzji na korpusie wypisana (`model_b_changes.txt`) i przejrzana.
- `test_regression_classifier.py`: allowlista `_KNOWN_MISSED_DIALOG` się nie powiększa (v3: bez zmian). Dokładność liczona na decyzjach linii; próg w E8.
- Wiersze tabeli kontrprób B.6 jako testy jednostkowe.

**C:**

- Przypadki C.3 i przykład zmiany szyku jako testy.
- Więcej zdarzeń ze znacznikami niż 450 (dziś).
- Każde zdarzenie korpusu zachowuje multizbiór tagów w wyniku `replace_visible_text`, jak dziś.
- Zdarzenia, które dziś mają znaczniki, a w v3 nie mają lub mają inne zakresy (np. `\bord`/`\blur` przy granicy słowa), są wypisane i przejrzane.

**Zawsze:** bramki jakości repo.

**Zmiana API (B).** `StyleVerdict(style, category, dialogue_score, look_dialogue, look_sign, hard, base, line_count, raw_line_count)`:

- `dialogue_score = D_s` zastępuje `confidence`;
- `look_*` to `look_d` i `look_s`;
- `hard` oznacza ostry styl z B.2, a `base` styl bazowy.

`Category` służy tylko do podglądu w UI: DIALOG przy D_s ≥ 0,55, SIGN przy D_s ≤ 0,25, w przeciwnym razie UNCERTAIN. `main_dialogue_style` zwraca styl z `base`. `line_category` zastępuje `line_dialogue_score` (B.4–B.5). Usuwamy wczesny `return DIALOG, 0.85` (`classifier.py:167`).

**Zmienione testy** (każda zmiana do akceptacji w przeglądzie; `fx`, `fy` = wybrany kandydat, `n` = zmierzony iloraz):

| Test | Rodzaj | Zmiana |
| --- | --- | --- |
| `test_sign_fitting.py::_fit` (l. 17) | mechaniczna | woła `fit_signs(subs, {0: target}, fonts)` |
| `…::test_long_sign_scales_both_axes_inside_the_first_block_and_respects_readability_floor` (l. 40) | wartości + nazwa | bez „floor”; B: `\fscx{80·n}\fscy{120·n/0,8}` w pierwszym bloku |
| `…::test_scaling_preserves_geometry_and_scales_inline_animation_and_reset` (l. 53) | wartości | geometria bez zmian; `\fscx{120fx}\fscy{150fy}\t(0,500,\fscx{180fx}\fscy{200fy})`, `\rOther\fscx{60fx}\fscy{80fy}` (obiekt przybliżony) |
| `…::test_reset_style_name_ignores_surrounding_whitespace` (l. 67) | wartości | `\rOther \fscx{60fx}\fscy{80fy}` |
| `…::test_mirrored_scale_keeps_its_sign` (l. 75) | wartości | `\fscx{100fx}\fscy{100fy}\fscx{−50fx}`; znak zostaje |
| `…::test_scale_resets_keep_the_fitted_named_style_across_blocks` (l. 89) | wartości | `60fx` / `80fy` w trzech resetach |
| `…::test_intermediate_scale_tracks_measured_width_instead_of_using_the_floor` (l. 100) | wartości + pomiar | `fx = n` z nowego pomiaru zamiast `_arial_ratio`, `fy = min(1; n/0,8)`; bez warunku `0.72 <` |
| `…::test_scale_values_accept_ass_whitespace` (l. 114) | wartości | `\fscx{100fx}\fscy{100fy}\fscx{120fx} \fscy{150fy} ` |
| `…::test_sign_that_libass_would_wrap_gets_a_balanced_break_and_per_line_fit` (l. 128) | sens + nazwa | K0 oceniany jako zawinięty przez libass (GROW), D niedopuszczalne (`\pos(900,1)` przy górnej krawędzi), wygrywa B w jednym wierszu; zostają asercje bloków tagów i `\pos(900,1)\fs120` |
| `…::test_floor_keeps_one_line_unless_libass_would_wrap_only_the_translation` (l. 153, 5 przypadków) | wartości + nazwa | `fits-screen`, `wrap-style-none`, `inline-no-wrap`, `malformed-width` dają B jednowierszowe `\fscx{100n}\fscy{100n/0,8}` (niepoprawny `PlayResX` jak libass); `source-already-wrapped` (`\fs200`) to bliski wybór B/D zależny od pomiaru — **otwarte**: oczekiwanie ustalamy w F2 przebiegiem modelu |
| `…::test_translated_writer_fits_signs_but_does_not_resize_dialogue` (l. 161) | wartości | `{\fscx{100fx}\fscy{100fy}\pos(10,10)}Czerwony`; dialog bez zmian |
| `test_subtitles_text.py`, 9 wywołań `marked_text` i 28 wywołań `replace_visible_text` | mechaniczna | nowy argument `base` (domyślny `SSAStyle`) |
| `…::test_marked_text_leaves_more_than_two_ranges_unmarked` (l. 175) | oczekiwanie + nazwa | `<s1>A</s1> b <s2>c</s2> d e f` |
| `…::test_marked_text_leaves_a_range_opened_at_the_verse_start_unmarked` (l. 264) | oczekiwanie + nazwa | `<s1>Why</s1> are you here?` |
| `…::test_marked_text_leaves_a_word_closed_before_punctuation_unmarked` (l. 268) | oczekiwanie + nazwa | `<s1>Water</s1>?` |
| `…::test_marked_text_leaves_a_range_opened_at_a_later_verse_start_unmarked` (l. 272) | oczekiwanie + nazwa | znacznik na tytule (C.3) |
| `test_subtitles_split.py::_verdict` (l. 97), l. 86, l. 213–214; `test_subtitles_translated_write.py` l. 348–349 | mechaniczna | nowe pola `StyleVerdict`: DIALOG/UNCERTAIN/SIGN → `dialogue_score` 0,9/0,5/0,1, `look` 0, `hard` False, `base` = DIALOG o największym `line_count` |
| `test_subtitles_split.py::test_split_resolves_uncertain_style_by_dialogue_name` (l. 138) | sens + nazwa | bez `verdicts=`: „Club Activities” czytane w `Default`, `Main` i `Black` (D⁰ ≈ 0,70 / 0,45 / 0,39; `Main` i `Black` nie mają definicji stylu, więc sim = 0,5; nazwa daje tylko 0,2) |
| `test_regression_classifier.py` | definicja | styl = dialog, gdy v3 czyta ściśle ponad połowę jego linii (remis i styl bez linii = szyld); allowlista bez zmian; próg w E8 |

**Bez zmian w oczekiwaniach** (sprawdzone ręcznie na wzorach B.4–B.5 albo C.2):

- `test_sign_fitting.py`:
  - l. 48, 82 (zakazy);
  - l. 108: K0 wygrywa remis S = 0, bo nadmiar 1% ≤ u, które zastępuje tolerancję 3%; test ustala u ≥ 0,01;
  - l. 121: podział jak źródło.
- `test_subtitles_text.py`:
  - l. 152, 156, 161, 166 (obrys jest atrybutem), 171 (gradient) i 277;
  - wszystkie testy `replace_visible_text` l. 63–262, także l. 191 (zakres `\3c` do końca linii) i l. 258.
- `test_subtitles_split.py`: l. 84, 104, 116, 124, 147, 166, 176 i 208. Do l. 166 dochodzi test, że zdanie z `\an5` jest czytane (D ≈ 0,72).

**Nowe testy:** C.3, przykład zmiany szyku, wiersze B.6, filtr kolizji (a6), `fallback_screen` (a1 bez dopuszczalnych), status przybliżony (`\move`, `\frz`, font zastępczy).

## E. Pytania do właściciela

1. **a7 i a10.** W a7 model wybiera C (ściśnięcie 75%) minimalnie przed B. W a10 wybiera dwa wiersze D zamiast C ściśniętego do 37%. Zgoda?
2. **Drabina a0.** Od ilu px tekst jest „za mały”? Dziś kara rośnie od 30 px i jest pełna przy 16 px.
3. **Wolne tło.** Czy tekst szerszy od oryginału (a2, a5) ma być karany (FRAME), czy tylko przy ramce lub `\clip`?
4. **`fonttools`.** Zgoda na nową zależność?
5. **Próg czytania 0,3** (heurystyka: utrata kwestii ok. 2,5× gorsza od przeczytanego szyldu). Zgoda?
6. **Krótkie wersaliki.** Okrzyki wersalikami przy krawędzi w kolumnie stylu („EEK”, „IRRITATED” w Koori) będą czytane. Te z `\pos`, `\move` albo `\an` innej kolumny („KAGUYA”, „IRRITATED” `\an7`) będą pomijane. Zgoda?
7. **Nowe odczyty.** Czytane będą: „Next Time”/„Preview”, tytuły odcinków (Kusuriya, Iceblade), opisy produktów (Joshiraku), pojedyncze litery z `\pos` (Uzaki: „O”, „u”, „c”, „h”, „!”) i przyśpiewka `Wahaha`. Akceptujesz?
8. **Bramka regresji stylów.** v3 daje 0,933 zamiast 0,9586, bez zgubionej kwestii; różnica to 64 czytane małe style szyldów ze zdaniami. Obniżyć próg do 0,93 (w trybie linii), czy przed wdrożeniem zaostrzyć wagę stylu dla małych n?
9. **Pliki NC/ED.** Fallback „nic nie czytane → czytaj wszystko” czyta wtedy piosenkę (39 plików w v3). Wyłączyć go dla stylów piosenek?

## F. Priorytety wdrożenia

Każdy krok to osobny PR z galerią przed i po.

1. **Pomiar:** indeks fontów, spany, kalibracja `u` i zgodności estymacji A.2 z libass, `fit_signs` z obiektami i statusem (A.2–A.3).
2. **A:** kandydaci, filtry ekranu i kolizji, szkody, raport poziomów ostatecznych (A.4–A.6).
3. **B:** profil stylu, linia, weto, serie, `RE_SONG_NAME`, API, test regresji (B.2–B.5).
4. **C:** stan bazowy, zakresy, wybór, stałe kotwice i przekazanie `base` (C.2).

## G. Poza zakresem

- analiza obrazu i OCR;
- parowanie tekstu z rysunkami `\p`;
- dokładna geometria `\frx/\fry/\fax` i animacji między końcami;
- zmiana geometrii;
- piosenki OP/ED;
- klasyfikacja przez LLM;
- wersaliki w tłumaczeniu;
- rozdzielanie serii `collapse_fbf` według actora.

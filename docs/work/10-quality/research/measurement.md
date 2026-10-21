---
kind: research
id: R3-measurement
updated: 2026-10-18
baseline: work/quality/08-fuzzy-quality @ 2301cd0
---

# Pomiar szerokości i wysokości napisu tak, jak rysuje go libass

## Odpowiedź

Produkcja powinna mierzyć tekst **Pillow + fontTools, prawdziwym fontem, jako prostokąt atramentu (ink), bez kerningu, w stałym dużym rozmiarze referencyjnym**, z obrysem i cieniem doliczanymi tylko wtedy, gdy są widoczne, z poprawką na `\blur` i z glifami zastępczymi mierzonymi w Arialu.
Na 4622 statycznych zdarzeniach z 36 par (35 rodzin fontów, bez auto-wrap) taki pomiar odbiega od prostokąta libass o p50 0,18%, p90 1,14%, p99 3,4% i maksymalnie 17,8%.
Maksimum przypada na jednoznakowy szyld 16 px. Dla zdarzeń o szerokości ≥ 100 px wynik to p90 0,68% i maksimum 5,6%.
Koszt to 0,19 ms na zdarzenie z ciepłym cache i 0,70 ms z zimnym. libass przez FFmpeg zostaje narzędziem kalibracji, nie produkcji.

Formuła z §A.2–A.3 (`getlength` w rozmiarze rzeczywistym z kerningiem, advance + `2·bord + shad`) daje p90 4,2% i maksimum 18,8%. Nie spełnia ±2%.

## Zakres i stan na dzień

- Dane: `workspace/.quality/library/*` i `corpus-pairs/*` z `output.pl.ass` i `fonts/`: 36 par (19 `library`, 17 `corpus-pairs`). Pominięto `certain-dark-item-*` i `kaguya-s1-05` (brak `output.pl.ass`) oraz Nia Liston (żadne zdarzenie nie przeszło parowania i filtrów).
- Próba: pary zdarzeń EN↔PL z `pair_events`, przy czym oba zdarzenia są statyczne i mają wszystkie fonty w `fonts/` pary. Na epizod wybrano do 120 szyldów i do 40 dialogów, równomiernie w czasie i bez duplikatów `(styl, tekst)`. Daje to 2333 pary, czyli 4666 zdarzeń: 1235 szyldów i 2290 dialogów w zbiorze czystym. Szczegóły są w `analysis.txt`.
- Za zdarzenie statyczne uznano brak tagów `\move`, `\t(`, `\org`, `\fr*`, `\fax/\fay`, `\p1+`, `\k`, `\fade(`, `\fs±`, `\fn@`, `\q1/\q3` i `\fe`. Odrzucono `\fad`, który w połowie zdarzenia nie daje pełnej krycia, czas > 20 s, puste wiersze `\N\N` oraz zdarzenia obcięte przez kanwę pomiarową (29).
- Wzorzec: `scripts/quality/render.py::measure_boxes`, czyli libass 0.17.5 (`commit 0.17.5-8-gb2fe9d877`) w FFmpeg z `external/bin`, z dostawcą fontów `directwrite (with GDI)`. Wzorzec nie był modyfikowany ani duplikowany.
- Środowisko: Windows 11, Python 3.14.7, Pillow 12.3.0, FreeType 2.14.3, fontTools 4.67.0 (tylko `uv run --no-sync --with fonttools`, bez zmiany zależności projektu).

## Metoda

1. **Indeks fontów** (`measure_lib.py::font_index`, `select_face`). fontTools czyta nazwy `name` 1/16 (rodzina) i 4/6 (pełna, PostScript), `usWeightClass`, bit kursywy, `unitsPerEm`, `winAscent/winDescent` (z fallbackiem typo/bbox jak `set_font_metrics` w libass) i `cmap`. Krój wybieramy jak libass: dopasowanie rodziny i najmniejsze `|Δwaga| + |Δnachylenie|`.
2. **Spany** (`parse_event`): stan `\fn \fs \fscx \fscy \fsp \b \i \bord \xbord \ybord \shad \xshad \yshad \blur \be \alpha \1a \3a \4a \an \q \r`, z rozbiciem na wiersze po `\N` (oraz `\n` przy `WrapStyle 2`) i `\h` jako U+00A0.
3. **Skala:** piksele skryptu na jednostkę em = `fs / (winAscent + winDescent)`, co odpowiada `FT_SIZE_REQUEST_TYPE_REAL_DIM` w libass. W poziomie mnożymy przez `fscx/100`, w pionie przez `fscy/100`.
4. **Estymatory szerokości** (`estimate`, `analyse.py::methods`):

| nazwa | definicja |
| --- | --- |
| `arial` | dzisiejszy `fitting.py`: `_width` × `_pixel_scale` + `2·bord + shad` |
| `spec_A3` | §A.2–A.3 dosłownie: Pillow `getlength` (BASIC, kerning legacy) w rozmiarze `fs·upem/(winA+winD)` + `fsp·(g−1)` + `2·bord + shad` |
| `ref_kern` | jak wyżej, ale w rozmiarze referencyjnym 1000 px i przeskalowane (bez hintingu) |
| `nokern` | suma advance pojedynczych znaków w 1000 px (bez kerningu) |
| `adv_vis` | `nokern` + obrys/cień tylko widoczne |
| `ink_vis` | prostokąt atramentu (`getmask2(char).getbbox()` w 1000 px, od lewej krawędzi pierwszego do prawej krawędzi ostatniego glifu) + widoczny obrys/cień; dla `BorderStyle 3` z `bord > 0` prostokąt z advance |
| `ink_vis_blur` | `ink_vis` + `2·k·σ`, σ = max(`\blur`, `\be`), k = 1,83 |
| `final_fb` | `ink_vis_blur`, ale glify spoza `cmap` mierzone systemowym Arialem tej samej wagi i nachylenia |

5. **Wysokość:** `h_spec_A2` = Σ wierszy `fs·fscy/100` + `2·bord + shad`, czyli formuła §A.2. `h_ink` to atrament: linia bazowa wiersza k = linia k−1 + descent(k−1) + ascent(k), gdzie ascent + descent = `fs·fscy/100`; do tego widoczny obrys/cień i blur.
6. **Błąd** = |estymata − libass| / libass dla szerokości i wysokości prostokąta `measure_boxes` (piksele skryptu, prawa krawędź wyłączna). Zbiór „czysty” to zdarzenia z prawdziwym fontem, bez brakujących glifów, bez syntezy pogrubienia lub kursywy i bez prognozy auto-wrap: 3525 zdarzeń.

## Ustalenia

### Kontrole syntetyczne (`controls.py` → `controls.json`, PlayRes 1920×1080, fonty pary Iceblade S02E01)

| próbka | libass W | estymata atramentu (+e) | uwaga |
| --- | ---: | ---: | --- |
| `AVAV…` / `AAAA…VVVV` Arial 100 px, bez nagłówka | 1076 / 1076 | 1074,2 | libass **nie kerninguje** |
| to samo z `Kerning: yes` | 963 / 1069 | 1074,2 | kerning włączony nagłówkiem |
| „Zażółć gęślą jaźń”: Arial / Trebuchet / Georgia / Times / Impact / Tahoma | 684 / 651 / 643 / 627 / 558 / 616 | 683,6 / 650,6 / 644,1 / 625,4 / 557,2 / 615,5 | ±1,6 px |
| „Hello World” Arial `\bord3` / `\bord8` / `\bord8\3a&HFF&` | 455 / 465 / 449 | 454,9 / 464,9 / 448,9 | niewidoczny obrys nie poszerza |
| `\shad6` / `\shad6\4a&HFF&` / `\bord4\shad6` | 455 / 449 / 463 | 454,9 / 448,9 / 462,9 | |
| `\bord4\blur1` / `\blur3` / `\blur8` / `\be3` | 459 / 465 / 477 / 460 | 456,9 + blur | nadmiar 1,0–1,3 σ na stronę |
| `\blur3` bez obrysu (biały tekst) | 461 | 448,9 + blur | nadmiar 2,0 σ na stronę (zależy od kontrastu) |
| `\fscx50` / `\fscx150` / `\fsp10` / `\fsp10\fscx150` | 225 / 673 / 549 / 824 | 224,4 / 673,3 / 548,9 / 823,3 | `\fsp` skaluje się z `\fscx` |
| `BorderStyle 3`, `bord 4` / `+shad6` / `bord 0` | 470 / 476 / 449 | 470,5 / 476,5 / 448,9 | pudełko z advance; `bord 0` = brak pudełka |
| syntetyczna kursywa Impact `\i1` | 409 | 407,5 | ścięcie 0x5700/0x10000 ≈ 0,34 × wznios atramentu |
| syntetyczne pogrubienie Impact `\b1` | 388 | 385,4 | +2,6 px, bez korekty |
| Arial `\i1`, gdy w `fonts/` są tylko Regular i Bold | 471 | 470,7 przy syntetycznym ścięciu Regular | libass nie sięgnął po systemowy `ariali.ttf` |
| dwa wiersze `\fs60` / `\fs120`, wysokość | 170 | 169,6 | reguła linii bazowej potwierdzona |

Dodatkowy fakt: Pillow `getbbox` zwraca w poziomie pudełko **advance** (0…advance), nie atrament. Atrament daje `getmask2(...).getbbox()` (Arial „H”: `getbbox` 0–1479, maska 164–1314 = `glyf` xMin–xMax).

### Korpus: szerokość (`analysis.txt`)

| grupa | n | `arial` p50/p90/max % | `spec_A3` | `final_fb` |
| --- | ---: | --- | --- | --- |
| wszystkie czyste | 3525 | 17,5 / 28,2 / 86,6 | 1,3 / 4,2 / 18,8 | 0,2 / 1,0 / 13,3 |
| EN / PL | 2049 / 1476 | 18,1 / 26,5 / 84,3 · 16,8 / 30,7 / 86,6 | 1,2 / 4,1 / 18,0 · 1,5 / 4,4 / 18,8 | 0,2 / 1,0 / 13,3 · 0,2 / 1,0 / 13,3 |
| dialog | 2290 | 18,5 / 27,4 / 49,7 | 1,3 / 3,6 / 11,3 | 0,1 / 0,7 / 5,6 |
| szyld | 1235 | 13,3 / 29,0 / 86,6 | 1,2 / 6,0 / 18,8 | 0,3 / 1,4 / 13,3 |
| 640×360 / 1080p | 1615 / 1830 | 16,1 / 31,4 / 49,7 · 19,4 / 25,6 / 86,6 | 1,6 / 4,0 / 17,6 · 1,0 / 4,6 / 18,8 | 0,2 / 1,1 / 5,6 · 0,1 / 0,8 / 13,3 |
| libass W ≥ 100 px / < 100 px | 3129 / 396 | — | 1,2 / 3,5 / 18,8 · 3,7 / 9,3 / 18,0 | 0,1 / 0,6 / 5,6 · 1,1 / 2,6 / 13,3 |
| wielowierszowe | 739 | 16,7 / 31,1 / 77,1 | 1,2 / 4,2 / 11,1 | 0,2 / 0,7 / 9,4 |

Wszystkie zdarzenia statyczne bez auto-wrap (czyste, z fontem zastępczym i z syntezą) mają dla `final_fb` n = 4622: p50 0,18, p90 1,14, p95 1,69, p99 3,42, max 17,8%. 74 zdarzenia przekraczają 3%, a 3138 z 4622 estymat jest mniejszych od libass (mediana −0,38 px skryptu: libass zaokrągla piksele krawędzi w górę). p90 |błędu| wynosi 3,0 px w skali 1080p.

**Per font** (`final_fb`, p50 / p90 / max %; rodziny z n ≥ 5, pełna tabela w `analysis.txt`):
Trebuchet MS (1166) 0,2/0,7/3,0; Gandhi Sans (992) 0,1/0,4/5,6; Times New Roman (188) 0,4/1,4/4,1; Roboto Medium (160) 0,4/1,2/2,9; Expo Sans Pro (134) 0,1/0,4/1,9; Arial (126) 0,2/0,8/2,2; FOT-MatisseElegantoPro-EB (119) 0,4/3,1/9,4; FOT Manyo Sosho Std (113) 0,4/1,3/4,3; Comic Sans MS (98) 0,9/2,0/2,7; Georgia (85) 0,1/0,3/0,4; Bradley Hand ITC (54) 0,1/0,2/0,2; FOT Rodin Pro UB (52) 1,2/3,4/3,4; Woodland ITC (36) 0,0/0,1/0,1; Iwata Mincho Old Pro H-TR (31) 1,1/2,0/3,0; Verdana (21) 0,5/0,9/1,5; Lato (16) 0,4/3,4/3,4; Kozuka Gothic (14) 1,0/13,3/13,3 (szyld „I”, 16 px, `\blur1.5`).
Rodziny powyżej 2% p90 (FOT-MatisseElegantoPro-EB, FOT Rodin Pro UB, Lato, Kozuka, Iwata Mincho Old Pro H) to wyłącznie szyldy Kaguya, wszystkie z `\blur`.

**Iloraz PL/EN**, czyli wielkość, której używa dopasowanie (1444 przetłumaczone pary czyste):

| metoda | p50 % | p90 % | max % | > 3% |
| --- | ---: | ---: | ---: | ---: |
| Arial bez obrysu (jak `fitting.py`) | 1,7 | 6,2 | 64,1 | 433 |
| `spec_A3` | 0,6 | 2,0 | 8,8 | 57 |
| `final_fb` | 0,2 | 0,8 | 4,1 | 6 |

p90 Ariala (6,2%) jest zgodne z audytem (7,0%, inna miara: font stylu zamiast libass).

### Korpus: wysokość

| grupa | n | `h_spec_A2` p50/p90/max % | atrament + blur p50/p90/max % |
| --- | ---: | --- | --- |
| wszystkie czyste | 3525 | 16,0 / 43,6 / 71,1 | 2,1 / 4,5 / 33,2 |
| jednowierszowe | 2786 | 16,0 / 44,3 / 71,1 | 2,2 / 5,0 / 33,2 |
| wielowierszowe | 739 | 8,2 / 15,2 / 29,5 | 1,1 / 2,9 / 20,0 |
| `BorderStyle 3` | 37 | 1,6 / 10,1 / 20,0 | 1,6 / 10,1 / 20,0 |

Formuła §A.2 liczy pudełko wiersza, nie atrament. Zawyża wysokość o medianę +7 px skryptu (+16%), więc jest konserwatywna. Estymata atramentu ma medianę −0,74 px (libass +1 px na zaokrągleniu) i p90 3,0 px w skali 1080p. Interlinia libass = `fs·fscy/100` (ascent + descent przy REAL_DIM); potwierdzają to wielowierszowe p90 2,9% i kontrola z mieszanym `\fs`.
`BorderStyle 3` jest w libass o ~2 px wyższy od Σ`fs` + `2·bord`, co przy 640×360 daje 10% (n = 37).

### Auto-wrap

Reguła „suma advance wiersza > `PlayResX − MarginL − MarginR` i brak `\q2` / `WrapStyle 2`” wskazała 12 zdarzeń. libass zawinął wszystkie 12, co widać po wysokości o ≥ pół wiersza większej. Wśród pozostałych 4622 żadne nie urosło o pół wiersza. Na tych 12 zdarzeniach szerokość jest błędna o p50 53% (jest tam szerokość po zawinięciu), więc emulacja zawijania z §A.2 jest konieczna. Liczby wierszy po zawinięciu tu nie testowano.

## Werdykty hipotez

| H | werdykt | liczby |
| --- | --- | --- |
| **H1** Pillow BASIC `getlength` + skala `\fs/\fscx/\fsp` + `2·bord + shad` w ±2% p90 | **obalona w wersji dosłownej, potwierdzona po trzech poprawkach** | `spec_A3`: p90 4,2%, max 18,8% (n = 3525). Pomiar w 1000 px, prostokąt atramentu, widoczność obrysu/cienia i blur dają p90 1,0%. Na całej próbie statycznej z fontem zastępczym i syntezą: p90 1,14% (n = 4622). Dla tekstów PL z polskimi znakami: p90 1,0% (n = 1476 czystych) i 0,4% (n = 610 z glifem zastępczym, `final_fb`). |
| **H2** RAQM zmniejsza błąd o > 1 pp | **obalona** | `features.check('raqm')` = False w Pillow 12.3.0 na tym Windows (brak FriBiDi; `harfbuzz` = None). Ważniejsze: libass 0.17.5 **nie kerninguje** bez `Kerning: yes` (kontrola: 1076 = 1076), a nagłówek ma 0 z 284 plików ASS w `corpus/`, `library/` i `corpus-pairs/`. Kerning HarfBuzz zwiększyłby więc błąd. Kerning legacy w BASIC nie ma wpływu (`ref_kern` = `nokern` we wszystkich grupach). |
| **H3** udziały źródeł błędu | **potwierdzona i rozdzielona**, tabela niżej | Największe źródła: łożyska boczne (advance zamiast atramentu), blur, obrys/cień i glify zastępcze. Hinting jest mniejszy, kerning zerowy. PlayRes/LayoutRes i `ScaledBorderAndShadow` nie występują w danych. |
| **H4** Pillow < 1 ms na zdarzenie | **potwierdzona** | 0,19 ms (ciepły cache), 0,70 ms (zimny, w tym maski 1000 px na znak), parsowanie 0,014 ms; n = 4666. Indeks fontTools: 0,07 s na parę (2,5 s na 36 par). |
| **H5** libass za wolny na zdarzenie, wystarczający do kalibracji | **potwierdzona** | Sekwencyjnie 1080p (kanwa 3840×2160): 1 zdarzenie 2,43 s, 10 zdarzeń 1,44 s, 100 zdarzeń 7,05 s, czyli narzut ~0,8–2,4 s na wywołanie i ~62 ms na zdarzenie. 640×360: 0,34 s / 0,37 s / 0,60 s (46 zdarzeń), czyli ~6–7 ms na zdarzenie. Cała próba 4666 zdarzeń przy 4 równoległych procesach: 113 s. |

### H3: udziały (podzbiór, w którym źródło działa; p50 / p90 / max %)

| źródło | podzbiór | n | bez korekty | z korektą |
| --- | --- | ---: | --- | --- |
| hinting (`getlength` w rozmiarze rzeczywistym → 1000 px) | czyste | 3525 | 1,3 / 4,2 / 18,8 | 0,9 / 3,2 / 20,4 |
| hinting | 640×360 | 1615 | 1,6 / 4,0 / 17,6 | 0,8 / 2,6 / 18,5 |
| kerning legacy BASIC | czyste | 3525 | 0,9 / 3,2 / 20,4 | 0,9 / 3,2 / 20,4 |
| łożyska boczne (advance → atrament) | bez blur i BS3 | 2765 | 0,8 / 2,5 / 11,4 | 0,2 / 0,8 / 5,6 |
| obrys i cień (`2·bord + shad`) | `e > 0` | 2983 | 1,8 / 5,7 / 20,9 | 0,2 / 0,7 / 5,6 |
| widoczność obrysu/cienia (`\3a`/`\4a` = FF) | kontrole (2 próbki) | 2 | +16 / +6 px | 0 / 0 px |
| blur/`\be` (+2·k·σ) | z blur | 723 | 2,0 / 8,6 / 47,5 | 0,3 / 1,7 / 13,3 |
| `BorderStyle 3` (pudełko z advance) | BS3 | 37 | 1,0 / 2,3 / 3,7 | 0,1 / 0,8 / 2,2 |
| font zastępczy (brakujące glify z Ariala) | brak glifu | 610 | 0,4 / 4,4 / 19,1 | 0,1 / 0,4 / 4,8 |
| synteza pogrubienia (bez korekty) | `synth_bold` | 487 | — | 0,6 / 2,1 / 17,8 |
| synteza kursywy (ścięcie 0,34) | kontrola | 1 | 391,7 vs 409 px | 407,5 vs 409 px |
| PlayRes ≠ LayoutRes, `ScaledBorderAndShadow: no` | — | 0 | brak przypadków | — |
| kwantyzacja wzorca (piksel całkowity) | libass W < 100 px | 396 | — | 1,1 / 2,6 / 13,3 |

Stała blur jest odporna w przedziale k = 1,83–2,0: p90 1,9–2,2% na 1219 zdarzeniach z blur, przy k = 1,0 p90 5,1%, przy k = 0 p90 10,8%. Dopasowana na EN daje k = 1,85, a na PL p90 1,9%. 1171 z 1219 zdarzeń z blur pochodzi jednak z Kaguya (MTBB).

## Gdzie estymacja zawodzi

1. **Fonty bez polskich znaków.** 617 z 2333 zdarzeń PL (26%) ma glif spoza `cmap` stylu. Najczęściej: Gandhi Sans (447, font dialogów m.in. Grand Blue i Detective), FOT-MatisseElegantoPro-EB (53), Iwata Mincho (54) i fonty dekoracyjne Kaguya. Brakujące znaki: `ąćęłńŚśźŻż` oraz `-` (U+002D) w jednym foncie. libass (DirectWrite) bierze je z **systemowego Ariala tej samej wagi i nachylenia** (`Gandhi Sans -> Arial-BoldMT`, `-> Arial-BoldItalicMT`, `-> ArialMT`). Przewidywane rodziny z brakami zgadzają się z logiem libass w 47 na 47 przypadków. Bez modelowania tego błąd ma p90 4,4% i max 19%, z modelowaniem p90 0,4% i max 4,8%. libass próbuje najpierw innych krojów tej samej rodziny (kontrola: Comic Sans → `ComicSansMS-Bold` dla `ąćęńś`, potem fallback dla `ż`).
2. **Wybór kroju.** Gdy rodzina jest w załącznikach, libass wybiera tylko spośród nich (Arial `\i1` → syntetyczne ścięcie Regular, mimo systemowego `ariali.ttf`). Indeks musi stosować tę samą regułę, inaczej pomyli syntezę z prawdziwą kursywą (8 px na 471).
3. **Blur.** Widoczny zasięg zależy od kontrastu z tłem: na kanwie `measure_boxes` (RGB 1,2,3) czarny obrys z blur daje 1,0–1,3 σ na stronę, a biały tekst 2,0 σ. Na prawdziwym obrazie zasięg zależy od klatki. k = 1,83 to kalibracja względem kanwy, nie względem widoku.
4. **Małe szyldy.** Przy szerokości < 100 px p90 to 2,6%, a max 13,3%, bo ±1 px wzorca to kilka procent.
5. **Syntetyczne pogrubienie** jest nieznacznie węższe niż w libass (mediana −0,5%), z wyjątkiem pojedynczych liter.
6. **Auto-wrap** wymaga emulacji (§A.2), bo sama szerokość wiersza przed zawinięciem jest wtedy błędna o ~50%.
7. **Dynamiczne zdarzenia** (`\move`, `\t`, `\fr*`) i `\fs±` nie były mierzone. Jako dynamiczne odrzucono 142 340 zdarzeń, z czego ~10 tys. na każdy odcinek Grand Blue.

## Rekomendacja

**Metoda produkcyjna (W)** to pomiar w FreeType przez Pillow z indeksem fontTools:

1. Indeks krojów z załączników MKV / `fonts/` (+ system tylko dla rodzin nieobecnych w załącznikach). Wybór: rodzina z nazw 1/16, potem pełna nazwa 4/6; najmniejsze `|Δwaga| + |Δnachylenie|`.
2. Skala `fs / (winAscent + winDescent)` (fallback typo/bbox jak libass) × `fscx/100`. Pomiar w **stałym rozmiarze 1000 px** i skalowanie liniowe, nie `truetype(size=fs·…)`.
3. **Bez kerningu**, czyli suma `getlength(znak)`. Plik z `Kerning: yes` (0 w korpusie) dostaje status przybliżony, bo BASIC nie stosuje kerningu GPOS, a RAQM nie jest dostępne.
4. Szerokość wiersza = prawa krawędź atramentu ostatniego glifu − lewa krawędź pierwszego (`getmask2(znak).getbbox()`, cache per krój i znak) + `fsp·fscx/100` między znakami. Wiersze wyrównane wg advance i `\an`. Spacje na końcach się nie liczą.
5. Obrys `bord` po obu stronach tylko przy `\3a < FF` (lub BS3). Cień `shad` po stronie przesunięcia tylko przy `\4a < FF`. Blur: `+k·σ` na stronę, k ≈ 1,8–2,0.
6. `BorderStyle 3` z `bord > 0`: pudełko = advance + `2·bord` (+`shad`), wysokość = Σ`fs·fscy/100` + `2·bord` (+`shad`) + ~2 px.
7. Syntetyczna kursywa: + 0,34 × wznios atramentu z prawej. Glif spoza `cmap`: najpierw inne kroje rodziny, potem Arial tej samej wagi i nachylenia.
8. Wysokość: atrament z linią bazową `b_k = b_{k−1} + desc_{k−1} + asc_k`, gdzie `asc + desc = fs·fscy/100`. Dla filtrów konserwatywnych dopuszczalne jest pudełko wiersza §A.2, które zawyża o medianę 16%.

**Wpływ na specyfikacje (W):**

- §A.3 „`getlength` z kerningiem w rozmiarze `fs·upem/(winA+winD)`” należy zastąpić punktami 2–4. Samo przejście z advance na atrament i pomiar w 1000 px obniża p90 z 4,2% do 1,0%.
- `u` dla prawdziwego fontu: p90 zmierzone 1,14% (szyldy 1,70%, dialog 0,59%), p95 1,69%. Bramka §D „p90 ≤ 3%” jest spełniona z zapasem. Zapas τ = 0,98 z `fuzzy-line-breaks.md` (2%) pokrywa p95 dialogów (0,92%).
- `u = 0,07` dla fontu zastępczego jest za wysokie, gdy fallback jest modelowany Arialem (zmierzone p90 0,4%). Zależy to jednak od dostawcy fontów odtwarzacza (patrz niewiadome).
- Stała przesunięcia +1 px skryptu skompensuje systematyczne niedoszacowanie (68% estymat poniżej libass).

**Zakres kalibracji (W):** `measure_boxes` offline. Ten zestaw (36 par, 4666 zdarzeń, 113 s przy 4 procesach) jako test regresji estymatora, z progami p90 ≤ 1,5% i p99 ≤ 4% dla zdarzeń ≥ 100 px. Ponowna kalibracja przy nowym fontcie / grupie wydawniczej z blur (k), przy zmianie wersji libass/FFmpeg albo dostawcy fontów. W produkcji libass co najwyżej jako wsadowa weryfikacja kandydatów: dla 106 unikalnych obiektów × 5 kandydatów przy 1080p to ~35 s i ~13 GB surowych klatek w potoku.

## Sprzeczności i niewiadome

- **Odtwarzacz właściciela:** wzorzec to libass w FFmpeg z DirectWrite. mpv właściciela może mieć inną wersję libass, inny font zastępczy (`sub-font`, `embeddedfonts`) i inny nagłówek kerningu. Nie mierzono.
- **PlayRes/LayoutRes i `ScaledBorderAndShadow: no`:** w danych 0 przypadków. `measure_boxes` renderuje w PlayRes z `LayoutRes = PlayRes`, więc nie odtwarza korekty proporcji ani obrysu nieskalowanego. W `corpus/` są 4 skrypty Uzaki 848×480 (proporcje 1,767 zamiast 1,778) i 3 bez nagłówka SBAS; ich wpływ jest niezmierzony.
- **Blur:** k skalibrowane głównie na jednej grupie (MTBB/Kaguya) i na sztucznym tle.
- **Ligatury:** libass stosuje ligatury HarfBuzz przy `\fsp = 0`, a estymator ich nie modeluje. W wynikach nie widać tego jako osobnego źródła błędu, ale osobno tego nie badano.
- **Emulacja zawijania:** reguła wykrycia zadziałała 12/12, ale liczby wierszy i szerokości po zawinięciu nie porównano z libass.
- **Zdarzenia dynamiczne** są poza próbą, z definicji statusu przybliżonego.

## Dowody i odtworzenie

Skrypty i wyniki: `C:\Users\MattyMroz\Desktop\PROJECTS\AniShift\workspace\.quality\experiments\research-measurement\`

- `measure_lib.py` — indeks, spany, estymatory; `controls.py` → `controls.json`; `corpus.py` → `corpus-rows.json`, `corpus-calls.json`, `timing.json`; `reestimate.py` (dodaje `est_fb`); `analyse.py` → `analysis.txt`; `timing_libass.py` → `timing-libass.json`; pliki robocze libass (`.ass`, `.log`) w `work/`.

Komendy (cwd = worktree `AniShift-wt\fuzzy`; `uv run` zamiast samego `.venv\Scripts\python.exe`, bo potrzebne jest fontTools spoza zależności projektu):

```bash
E=../../AniShift/workspace/.quality/experiments/research-measurement
PYTHONIOENCODING=utf-8 uv run --no-sync --with fonttools python -B $E/controls.py
PYTHONIOENCODING=utf-8 uv run --no-sync --with fonttools python -B $E/corpus.py        # 2 min 25 s
PYTHONIOENCODING=utf-8 uv run --no-sync --with fonttools python -B $E/reestimate.py
PYTHONIOENCODING=utf-8 uv run --no-sync --with fonttools python -B $E/timing_libass.py
cd $E && PYTHONIOENCODING=utf-8 python -B analyse.py
```

Kod libass i parametry: `scripts/quality/render.py::measure_boxes` (`PAD_FRACTION` 0,5, tło RGB 1,2,3, `-v verbose`), log `fontselect` i `Glyph … not found` w `work/*/measure-*.log`.

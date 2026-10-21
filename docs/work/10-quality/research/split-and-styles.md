# Podział dialog/szyld i granice stylów: stan rzeczywisty i najtańsze poprawki

Data: 2026-10-18. Kod: worktree `AniShift-wt/fuzzy`, gałąź `work/quality/08-fuzzy-quality`, commit `2301cd0`.
Dane: 245 plików ASS (`library/` 19, `corpus-pairs/` 21, `corpus/` 205), etykiety `labels/split-labels.csv`, zbiór regresji `mm_avh_working_space/temp` (182 pliki, 984 style). Model specyfikacji: `experiments/fuzzy-spec2/model_b.py` (v3.1).
Skrypty i wyniki: `workspace/.quality/experiments/research-split/`.

## Odpowiedź

1. Obecny kod gubi realne kwestie, ale mało: **9 linii** w stylach `Alt` (Joshiraku 7, Uzaki 2). Na etykietach strat nie widać (425/425), bo etykiety nie obejmują tych serii.
2. Reguła B naprawia wszystko, co trzeba, ale czyta też za dużo. Trzy małe zmiany w obecnym klasyfikatorze dają **dokładnie te same 108 pominięć** co B i te same 9 odzyskanych kwestii `Alt`, bez nowych szyldów i bez spadku w teście regresji (0,9888 zamiast 0,933 w B).
3. Fallback „nic nie czytane → czytaj wszystko” nie uratował dialogu w żadnym z 427 plików. Odpala się na plikach samych piosenek, szyldów i notek. Wykluczenie stylów piosenek z fallbacku wycisza piosenki w 14/14 plików.
4. W granicach stylów największe straty to nie T1/T2, tylko **T3** (440 zdarzeń kwestii, 148 unikalnych) i **fałszywe zakresy z bloków komentarzy** `{**-san}`, `{*}` (869 zdarzeń, 774 unikalne). Obie sprawy załatwiają dwie wąskie zmiany w `text.py`. T1/T2 w kwestiach to prawie wyłącznie gradienty i kinetyka (1 prawdziwy akcent).
5. Podwójne czytanie tej samej kwestii istnieje, ale rzadko (26 par dziś). B dodaje 17 par: wszystkie 11 „odzyskanych” linii stylu `Shenanigans` to kopie linii z `GJM_Main_1080p`.

**Oznaczenia:** F — fakt z kodu, danych lub przebiegu; W — wniosek; R — rekomendacja; N — niewiadoma.

## Zakres i metoda

- „Dziś” to produkcyjne `split_subtitles` z gałęzi 08, łącznie z fallbackiem. „B” to `model_b.evaluate` (v3.1). Oba zapisane per linia w `lines.jsonl` (`split_eval.py`). Liczby fallbacku zgadzają się ze specyfikacją: 35 i 39 plików (F).
- Etykiety (`split-labels.csv`) obejmują tylko linie oflagowane i `UNCERTAIN` z kilku serii. Grand Blue, Kaguya S1, First Kiss i część biblioteki. Nie ma w nich Joshiraku ani Uzaki (F). Dlatego straty kwestii szukałem także heurystycznie na korpusie: linia nieczytana, ze znakiem zdania, bez `\pos/\move/\org`, poza stylem ostrym, bez czytanej linii o tym samym tekście w odległości ≤ 1 s (`h1_h2.py`). Kandydatów przejrzałem ręcznie.
- Bez wideo. Decyzje „kwestia czy szyld” opierają się na tekście, tagach, stylu i sąsiedztwie.
- Wariant minimalny testowałem na kodzie produkcyjnym przez podmianę regexów i otoczkę `line_category` (`minimal.py`). Kod repo pozostał bez zmian.

## H1 — gubione kwestie w `Alt` i małych stylach: potwierdzona, mała skala

**F.** Na etykietach: dialog 425/425 czytany dziś i w B (`h1_h2.py`).
**F.** Korpus, wszystkie linie stylów `Alt*` w Joshiraku i Uzaki (`q_alt.py`): Joshiraku 45, z czego dziś czytane 38; Uzaki 5, czytane 3. **Gubione: 9**, B czyta wszystkie (D 0,90–0,93):

| Plik | Czas [ms] | Tekst |
| --- | --- | --- |
| Joshiraku 03 – Dialogue | 700680, 703060 | „I don't think—”, „What the—” |
| Joshiraku 06 – Dialogue | 664140 | „Yo!” |
| Joshiraku 09 – Dialogue | 391700, 501980 | „I'm sick of this.”, „Birds?” |
| Joshiraku 12 – Dialogue | 376520, 456440 | „Terrifying?!”, „Nooo!” |
| UzakiBD_02 – Dialogue | 46990, 443510 | „Have a nice day.”, „Can it!” |

**F.** Heurystyka znalazła 108 unikalnych kandydatów. Poza tymi 9 są to:
- szyldy i tekst ekranowy: Seihantai `Basic Sign` (16), Grand Blue `boxed`/`REd 2`/`ryokan`/`Next Ep Title`/`cut-outs`, certain-dark-item `Signs`;
- rap z piosenki wstawionej w Kaguya S3 (`MiyukiRap`, `HayaRap`, `ChikaRap`, `KaguyaRap`; 26 linii);
- „Wahaha” z Marumaru (3);
- linie First Kiss z `\an4/\an6` (6), czyli dymki albo wiadomości w telefonie (N).

Innych zgubionych zwykłych kwestii nie znalazłem (W, w granicach filtru heurystyki).

## H2 — reguła B: naprawia, ale czyta 43 szyldy i 12 dubli ponad minimum

**F.** B zmienia 200 unikalnych linii: 108 przestaje być czytanych, 92 zaczyna.
- **108 pominięć:** żadna z tych linii nie ma znaku zdania (`h1_h2.py`). W próbce 11/11 to szyldy albo tekst piosenki.
- **92 nowe odczyty** (przejrzane wszystkie):

| Kategoria | Wiersze | Przykłady |
| --- | --- | --- |
| prawdziwa kwestia | 22 | `Alt` ×9; Kaguya S3 ep09 `GJM_Main_1080p` z `\an5` ×12 (4 unikalne × 3 kopie odcinka); „Beef bowl!” |
| kopia już czytanej kwestii (dubel) | 12 | `Shenanigans` ×11, `ZahuSigns` „I want them” |
| szyld lub piosenka | 46 | tytuły Kusuriya ×14 i Iceblade ×6, „Preview” ×8, `brush2` ×5, `blood`, Uzaki „O”,„u”,„c”,„h”,„!”, „ling?”, `Wahaha` ×3, NCED przez fallback ×3 |
| niepewne (dymek albo czat w First Kiss) | 12 | „Are you okay? Try not to overdo it READ”, „GOOD NIGHT!! SEE YOU LATER” |

**Losowe 20 zmian** (`h2_sample20.json`, seed 18), ocena ręczna:
- **11 pominięć — wszystkie trafne.** Wersalikowe szyldy First Kiss („PROSECUTOR KAGUYA (COLD AS ICE)”, „NO OCCUPANCY”, „MIYUKI SHIROGANE”), „Sushi Gosakimaru” w Joshiraku, tekst OP „Make your dreams of luster into reality” ×2.
- **9 odczytów:**
  - 2 kwestie: `Alt` „Nooo!”, „I don't think—”;
  - 2 duble: `Shenanigans` „Ah, you're so amazing.” i „That way, Kaguya won't…”, kopie linii `GJM_Main_1080p` sprzed ≤ 500 ms;
  - 2 szyldy: `blood` „You're going to Hell!” z `\pos\frx\fry`, `brush2` opis koron ceramicznych;
  - 2 wiadomości czatu w First Kiss (`\an6`, dopisek „READ”);
  - 1 przyśpiewka „Wahaha!”.

**F, wariant minimalny** (`minimal.py`, `minimal.json`, `minimal_veto2.json`):

| Wariant | Zmiany | Zgodne z B | Etykiety: szyld czytany | Regresja mm_avh (większość linii) |
| --- | --- | --- | --- | --- |
| dziś | — | — | 55 | 973/984 = 0,9888 |
| `alt` w `_RE_DLG` | +9 | 9/9 | 55 | 0,9888 |
| `RE_SONG_NAME` w stylu piosenki | −14, +3 | 17/17 | 55 | 0,9888 |
| weto linii (niżej) | −94 | 94/94 | 32 | 0,9888 |
| wszystkie trzy | −108, +12 | **120/120** | **32** (23 naprawione, 0 nowych) | **0,9888** |
| B (v3.1) | −108, +92 | — | 38 (23 naprawione, 6 nowych) | 0,933 |

Weto linii w stylu DIALOG zamienia linię na SIGN, gdy spełnione są dwa warunki:
- **etykieta:** brak `[.!?…"»”]`, brak przecinka i brak końcowego myślnika;
- **forma:** wersaliki (`rise(udział; 0,6; 0,85) ≥ 0,5`) albo zapis tytułowy z położeniem.

Linia chroniona (≤ 3 słowa, przy krawędzi, bez położenia) zostaje. To dokładnie te przypadki, w których weto B daje D < 0,3.

Pierwsza próba weta liczyła po prostu „≥ 2 silne wskazówki”. Odrzucała 65 linii więcej, w tym zdania wersalikami („THAT CAN'T POSSIBLY BE SEX!!”) i kwestię Uzaki 01. Forma musi więc być mnożona przez etykietę, jak w B.

**W.** Ponad wariant minimalny B dodaje 80 odczytów:
- 13 wierszy prawdziwych kwestii (5 unikalnych): Kaguya S3 ep09 i „Beef bowl!”;
- 43 szyldy;
- 12 dubli;
- 12 niepewnych.

Do tego test regresji spada z 0,9888 do 0,933. Dziś te zyski nie są warte kosztu.

## H3 — fallback czyta piosenki: potwierdzona, prosta reguła wystarcza

**F.** Fallback odpala się w 35 plikach dziś i 39 w B (z 245). W zbiorze mm_avh: 0 z 182 (`h3_mm.py`). Pliki z B (`h3.py`):

| Rodzaj | Plików | Uwagi |
| --- | --- | --- |
| osobne pliki TS/Notes z repo Kaleido | 23 | same szyldy lub notki tłumacza („Heya! This is an additional track…”); artefakt układu źródeł, nie realna ścieżka MKV |
| piosenki: NCOP/NCED, INS, OP1/ED1 | 14 | Joshiraku INS ×3, NCED/NCOP ×6, Kaguya NCOP/NCED ×3, Uzaki OP1/ED1 |
| części batcha GJM z samymi szyldami | 2 | Kaguya2-05 Part2, Kaguya3-11 Part2 |

Fallback nie uratował dialogu w żadnym przypadku na 427 plikach (F).

**F.** Dziś piosenki są czytane w Joshiraku NCOP1/NCED (gg) także bez fallbacku: `OPup`, `EDup`, `OPdown`, `EDdown` mają kategorię DIALOG, bo `_RE_SONG` ich nie łapie. W B zamiast tego odpala się fallback, więc wynik jest ten sam: piosenka czytana.

**F.** Reguła „fallback nigdy nie czyta stylów ostrych” (`_RE_SONG` + `RE_SONG_NAME`, karaoke > 0,3, rysunki > 0,3):
- w 11/14 plików piosenek nie czyta nic;
- w pozostałych 3 czyta tylko szyldy: KaguyaBD-NCOP `iFanzSigns` (43 linie, głównie pojedyncze litery), Joshiraku_NCOP1 `OPSign` (33), NCED2 (gg) `joshi-brush` „The End” (2);
- tekstu piosenki nie czyta w żadnym pliku.

Rozpoznanie pliku NC po nazwie odpada, bo `split_subtitles` nie zna nazwy pliku.

## H4 — granice stylów: główne straty to T3 i komentarze, nie T1/T2

Miara: zdarzenia czytane (dziś), poza plikami z fallbackiem, unikalne `(plik, styl, surowy tekst)`.
Reguła C odtworzona w `h4_styles.py::spec_c` (stan bazowy ze stylu, atrybut zmienny w słowie = efekt, atrybut wspólny dla wszystkich słów = baza linii, najwyżej 2 zakresy). Daje oczekiwane wyniki dla wszystkich przypadków z tabeli C.3 specyfikacji (F, test w sesji).

| Dziś | Zdarzeń (unikalnych tekstów) | Co z tym robi C |
| --- | --- | --- |
| znaczniki z prawdziwą zmianą atrybutu | 1482 (662) | zostają |
| **znaczniki bez zmiany atrybutu** | **876 (777)**, w tym 869 to wyłącznie bloki komentarzy | znikają |
| T3 (pierwsza granica `\i0/\b0`) | 458 (159) | **447 (155) dostaje znacznik**: 440 to negacja w stylu kursywnym lub pogrubionym, 7 to otwarcie na początku wersu |
| T1 (> 4 granice) | 22 | 1 akcent (gra słów „train/training”), reszta to kinetyka per litera i gradient `\3c` |
| T2 (granica w słowie) | 45 | 0 akcentów: odsłanianie `\alpha` („The moun-tains”), kinetyka |
| T4 (fragment bez słów) | 424 | 6 akcentów zablokowanych przez komentarz `{**-san}` („you actually {\i1}do{\i0} like him, Kashiwagi{**-san}”) |

Przykłady T3 (dziś bez znacznika, C oznacza dobrze):
- „For {\i0}you{\i1} to call them excellent,” (`Returner - Italic`);
- „How {\i0}weak{\i1}.”;
- „I read the {\i0}Plants{\i1} book”;
- „{\i1}I'm{\i0} gonna knock off your whole—”.

Fałszywe zakresy (dziś, `marked_text` na gałęzi 08):
- `Kaguya{**-san}, let's go home together!` → `Kaguya<s1>, let's go home together!</s1>`;
- `{*}Mistress Kaguya{*Kaguya-sama}, please!` → `Mistress Kaguya<s1>, please!</s1>`.

To głównie przełączniki honoryfikatów GJM. Na ekranie nic się nie psuje, bo komentarz jest niewidoczny. Szum trafia jednak do promptu tłumaczenia w ~774 unikalnych kwestiach.

Szyldy (zdarzenia wyświetlane): T1 i T2 to ok. 123 tys. unikalnych surowych zdarzeń, głównie klatki animacji i karaoke. C oznacza w nich 664 zdarzenia, głównie akcenty kolorem („Kaguya Wants to be {\c…}Confessed To”). T4 w szyldach to 5452 zdarzenia z kolorem samej interpunkcji („Lucky{\c…}!”). Dla lektora zysk jest zerowy, dla wyglądu szyldów mały (W).

## H5 — podwójne czytanie: istnieje, rzadkie; B je zwiększa

**F** (`h5c.py`, `h5_echo.json`). Liczone są pary czytanych serii z tym samym tekstem po normalizacji, odległe o ≤ 500 ms, w innym stylu albo z kopią wersalikami. Pliki z fallbackiem pominięte.
- **Dziś 26 par:**
  - `GJM_Main`/`GJM_Overlap` 19: zwykle dwie postacie mówią to samo jednocześnie, np. „Right away!” `C/Y`, „Heave-ho! Heave-ho!”, czyli chór czytany dwa razy;
  - Joshiraku `Default`/`Alt` 3: chór „Don't worry! Don't worry!”;
  - First Kiss 4: szyld-echo wersalikami czytany obok kwestii („Yay!” + „YAY”, „Number one...” + „NUMBER ONE”).
- **B: 43 pary.** Dochodzą `Shenanigans` 11, `ZahuSigns` 5 i tytuł Iceblade `Sign_Basic` obok tej samej kwestii w `Main` (1).
- **Ścisłe nakładanie w czasie** (`h5b.py`): dziś 6 par, B 7.

## Rekomendacja zakresu (R)

**Podział (B), wąsko, w obecnym `classifier.py`/`service.py`:**
1. `Alt` jako nazwa dialogowa (`\balt\b` w `_RE_DLG`): +9 kwestii, 0 skutków ubocznych na 245 + 182 plikach. Wersja ogólna (podobieństwo do stylu bazowego) może poczekać, aż pojawi się przypadek, którego nazwa nie łapie.
2. `RE_SONG_NAME` w rozpoznaniu stylu piosenki: −14 odczytów tekstu OP.
3. Weto linii „etykieta × forma” w stylu DIALOG (definicja w H2): −94 szyldy, 23 szyldy z etykiet naprawione, 0 zdań utraconych.
4. Fallback z pominięciem stylów ostrych: koniec czytania piosenek w plikach NC/INS.

**Granice (C), wąsko, w `text.py`:**
5. Bloki bez `\` (komentarze) nie tworzą granic: −869 fałszywych zakresów i +6 odblokowanych akcentów.
6. T3 zastąpione faktem o stylu: `\i0/\b0` otwiera zakres, gdy styl ma ten atrybut: +440 akcentów (98% strat T3).

**Odłożyć:**
- usunięcie C6 i czytanie zdań z położeniem (zysk 5 unikalnych kwestii wobec 43 szyldów, 12 dubli i 12 niepewnych);
- pełne C dla T1/T2 (1 akcent w kwestiach).

Jeśli wrócą, potrzebują dwóch zabezpieczeń:
- deduplikacji echa: ten sam tekst w innym stylu w ciągu 500 ms;
- minimum liter w linii, żeby nie czytać pojedynczych liter typu Uzaki „O u c h”.

## Niewiadome (N)

- Linie First Kiss z `\an4/\an6`: dymki, wiadomości czy kwestie? Potrzebna klatka.
- Rap w Kaguya S3 (`*Rap`, 26 linii): piosenka czy kwestia? Decyzja właściciela.
- Pliki TS/Notes Kaleido nie są realnymi ścieżkami. Liczby fallbacku bez nich: 16 plików, w tym 14 piosenek.
- Kwestie bez znaku zdania i z `\pos` są poza filtrem H1. Jeśli giną, ta analiza ich nie widzi.
- Odtworzenie C w `spec_c` jest uproszczone: nie obsługuje `\2c`, `\4c`, `\3a` ani `\t` jako zmiany atrybutu.

## Odtworzenie

Interpreter `AniShift-wt\fuzzy\.venv\Scripts\python.exe -B`, cwd = worktree, `PYTHONIOENCODING=utf-8`. Kolejność:
1. `split_eval.py` → `lines.jsonl`, `files.json`;
2. `h1_h2.py` → `h1_candidates.tsv`, `h2_changes.tsv`, `h2_sample20.json`;
3. `q_alt.py`, `q_grp.py`;
4. `minimal.py`: pierwszy przebieg (5 wariantów, weto „≥ 2 wskazówki”) dał `minimal.json`; obecna wersja pliku liczy weto „etykieta × forma” i zapisuje `minimal_veto2.json`;
5. `h3.py`, `h3_mm.py`;
6. `h4_styles.py` → `h4_counts.json`, `h4_examples.json`; potem `h4b.py`, `h4c.py`;
7. `h5.py`, `h5b.py` → `h5_strict.json`; `h5c.py` → `h5_echo.json`.

Wszystko leży w `workspace/.quality/experiments/research-split/`.

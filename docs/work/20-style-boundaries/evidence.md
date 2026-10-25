---
kind: evidence
status: complete
updated: 2026-10-25
baseline: drzewo robocze na gałęzi work/subtitles/03-pr66-review-fixes (z main 4365a51)
---

# Dowody: granice stylów po tłumaczeniu (#34)

## Pytanie

Co z [#34](https://github.com/MattyMroz/AniShift/issues/34) już działa, a gdzie inline'owy styl ASS (kursywa, kolor, przezroczystość na fragmencie linii) nadal ginie, przesuwa się albo obejmuje zły fragment, gdy polski szyk różni się od źródła.

## Metoda

Wszystko tylko do odczytu: bez płatnych API, bez zmian w `workspace/` i `config/`. Skrypty pomocnicze leżały w scratchpadzie sesji i nie trafiają do repo. Każdy wynik da się odtworzyć poniższymi krokami.

1. **Gotowe produkty (`workspace/ready/`).** Źródłowy ASS nie leży w `ready/`, tylko w MKV, więc angielskie ścieżki ASS wyciągnąłem `mkvextract` do scratchpada. Zdarzenia `Dialogue` sparowałem po kolei według startu, końca i warstwy. Linię uznaję za akcent, gdy przynajmniej jedno, ale nie każde całe słowo ma inny stan kursywy, pogrubienia, podkreślenia, przekreślenia, koloru wypełnienia, koloru obrysu albo przezroczystości.
2. **Wykluczenie plików z polskim źródłem.** 32 z 47 pełnych plików `.pl.ass` w `ready/` (razem z `Nowy folder/`) ma obok siebie MKV z własną ścieżką `pol` (np. `CR_Polish`). AniShift normalizuje wtedy polski tekst wydawcy, a nie tłumaczy. Przykład: w `Kusuriya no Hitorigoto 3rd Season - 04 … .pl.ass` nie ma ani jednego `\i1`, bo nie ma go w polskiej ścieżce CR (l. 95, 107). Takich plików nie liczę jako błędów tłumaczenia.
3. **Era kodu.** Znaczniki `<sN>` weszły w `ecc7222` (2026-10-17 22:25), negacja i komentarze w `3beee3d` (2026-10-18 16:35), a do `main` przez #61 (2026-10-21). Pliki starsze pokazują dawne mapowanie proporcjonalne, czyli pierwotny błąd z #34.
4. **Powtórka dzisiejszego writera na prawdziwych odpowiedziach LLM.** `workspace/.quality/experiments/styles/` zawiera odpowiedzi LLM ze znacznikami z 2026-10-17. Odtworzyłem dla nich dzisiejszy przepływ: `split_subtitles` → `spoken_lines`/`displayed_lines` → `_with_source_markers` → `layout_translated` (bez czcionki dialogów). Długości strumieni zgadzają się dla Yasei 03 i Iceblade S02E02.
5. **Powtórka bez znaczników.** Dla prawdziwych przekładów LLM z `workspace/.quality/corpus-pairs/*/output.pl.ass` (2026-10-17, sprzed znaczników) i starych plików z `ready/` jako przekład podałem widoczny polski tekst bez `\N`, tak jak dziś dostaje go writer. To dokładnie dzisiejsza ścieżka dla linii, którym `marked_text` nie daje znaczników, oraz dla Google, DeepL i każdej odpowiedzi LLM z uszkodzonymi znacznikami.
6. **Spis przyczyn.** Na 254 źródłowych plikach ASS (`workspace/.quality/corpus` i ścieżki wyciągnięte z `ready/`) policzyłem unikalne linie z akcentem, czyli pary `(styl, surowy tekst)`, oraz powód braku znaczników według warunków `_marked_boundaries`.

## Stan dziś: przepływ znaczników

| Krok | Miejsce | Co się dzieje | Gdzie znacznik może zginąć albo trafić źle |
| --- | --- | --- | --- |
| 1. Źródło → tekst dla tłumacza | `anishift/application/translation_handler.py:417-439` (`spoken_lines`, `displayed_lines`, `_marked`) | `marked_text(event.text, styl źródła)` z pierwszego zdarzenia kwestii; `SpokenLine.text` zostaje bez znaczników | wersy łączy spacja (`text.py:145`, `visible_text`), więc tłumacz nie widzi `\N` |
| 2. Wybór granic | `anishift/services/subtitles/text.py:280-296` (`_marked_boundaries`), `304-317` (`_closes_a_range`), `62` (limit 4) | znaczniki dostają tylko granice **wewnątrz wersu** przy krawędzi słowa | brak znaczników, gdy: granica leży na krawędzi wersu (mówca w osobnym wersie), zakres otwiera blok z początku linii, a pierwsza granica go zamyka (`{\i1}Why{\i0} …`), granic jest > 4, granica leży w słowie albo zakres nie ma słów |
| 3. Deduplikacja i silnik | `anishift/services/translation/service.py:209-236`; `engines/google/service.py:82`, `engines/deepl/service.py:127` | klucz deduplikacji zawiera znaczniki; Google i DeepL je usuwają | Google/DeepL zawsze idą ścieżką bez znaczników |
| 4. Prompt i odpowiedź | `engines/llm/prompts/system.md:36, 95-106`; `engines/llm/line_contract.py:84` | LLM ma zwrócić każdy znacznik raz, w tej samej kolejności, wokół słów o tym samym znaczeniu | parser nie sprawdza znaczników; błąd ujawnia się dopiero przy zapisie i nie jest nigdzie liczony |
| 5. Przypisanie przekładu | `translation_handler.py:442-457` (`translated_texts`, `_with_source_markers`) | znaczniki zostają tylko wtedy, gdy miało je źródło | znacznik zmyślony przez LLM jest usuwany (dobrze) |
| 6. Kopie i FBF | `anishift/services/subtitles/service.py:637-643` (`_event_translations`) | kopie kwestii biorą przekład pierwszego zdarzenia | kopia z inną strukturą tagów odrzuca znaczniki i przechodzi na rozkład |
| 7. Tagi na przekładzie | `anishift/services/subtitles/linebreak.py:78-84` (`tagged_line`) → `text.py:175-185, 359-406` (`replace_visible_text`, `_placed_tags`, `_marker_anchors`) | całe znaczniki ustawiają tagi swoich granic; reszta tagów idzie mapowaniem proporcjonalnym przyciąganym do krawędzi słów (`_map_globally` 448-466, `_snapped` 476-488) | (a) przekład jest jednowersowy, a źródło ma kilka wersów, więc tagi z krawędzi wersów lądują proporcjonalnie, czasem w kwestii drugiego mówcy; (b) uszkodzone znaczniki, zła kolejność, pusty zakres albo zakres pochłaniający wszystkie słowa dają ciche przejście na rozkład |
| 8. Styl przy odczycie znaczników | `linebreak.py:83` bierze styl zdarzenia po `restyle_dialogue`/`restyle_signs`; `restyle.py:221-225` (`clone.bold = clone.bold or font.bold`), `204-218` (kolor tekstu mpv) | `marked_text` liczy granice na stylu źródła, a `replace_visible_text` na stylu klonu | inny styl może dać inny zbiór granic; wtedy liczba znaczników się nie zgadza i są odrzucane (ryzyko widoczne w kodzie, nieobserwowane w danych) |
| 9. Łamanie dialogu | `linebreak.py:58-75` | rdzeń układa wiersze; `reflow_visible_text` zachowuje tagi względem liter | przenosi błąd z kroku 7, sam niczego nie psuje |

## Wyniki

### A. Gotowe produkty z dzisiejszym mechanizmem: 7 z 7 poprawnych

Pliki tłumaczone (bez polskiego źródła) zapisane po 2026-10-18 16:35: Tantei S2-03, Sasaki and Peeps S02E03, Iceblade S02E03, Laid-Off S01E03, Tensei Kizoku S3-04, Dark Summoner 03. Mają 7 unikalnych linii z akcentem; we wszystkich LLM zachował znaczniki, a styl trafił na właściwe słowa:

- `Tantei … Season 2 - 03 … .pl.ass` l. 84 `it's {\i1}my{\i0} house` → `w {\i1}moim{\i0} własnym domu`, l. 86 `{\i1}I'm{\i0}` → `to {\i1}ja{\i0} jestem`, l. 103 negacja `{\i0}Perfect Record{\i1}` po zmianie szyku na początek linii;
- `Sasaki.and.Peeps.S02E03 … .pl.ass` l. 51 (szyld `EP 3` / tytuł w innym obrysie), l. 224 `{\i1}pewną osobę{\i0}` (jedno słowo → dwa), l. 350 `{\i1}tobie{\i0}`;
- `The.Iceblade … S02E03 … .pl.ass` l. 290 `{\i1}przekozackie{\i0}`.

### B. Powtórka writera na zapisanych odpowiedziach LLM: 6 z 7 poprawnych

`experiments/styles/runs/*.json`: LLM zwrócił znaczniki w kolejności w 56 z 56 oznaczonych linii (4 odcinki). Dzisiejszy writer kładzie z nich tagi poprawnie, np. `I {\i1}do{\i0} want her` → `{\i1}Chcę{\i0}, żeby je odzyskała!`, `Episode {\t(…\c…)}15` → `Odcinek {\t(…)}piętnasty`.

Jedyny inny wynik: szyld Yasei 03 `A {\c&HFEFDFE&}Flying, Handsome Man Appeared!` (`pairs/[Erai-raws] Yasei … - 03 …/source.en.ass` l. 23 i dalej, 27 zdarzeń klatka po klatce). Rodzajnik „A” znika w przekładzie, LLM obejmuje znacznikiem całe zdanie, walidacja (`_marker_anchors`, `text.py:402-405`) je odrzuca, a rozkład barwi pierwsze słowo: `Pojawił {\c&HFEFDFE&}się latający przystojniak!`. To styl pozycyjny (pierwsze słowo karty tytułowej), więc wynik jest dyskusyjny, a nie jednoznacznie błędny. Zob. decyzję D4 w specyfikacji.

### C. Linie bez znaczników: realne błędy dzisiejszego kodu

Powtórka writera z punktu 5 metody na prawdziwych przekładach LLM:

| # | Plik i linia źródła | Źródło | Dzisiejszy wynik | Błąd |
| --- | --- | --- | --- | --- |
| C1 | `experiments/styles/pairs/[Erai-raws] Koori no Jouheki 2nd Season - 03 …/source.en.ass` l. 374 (przekład: `output.pl.ass` l. 376) | `{\c&Hffffff&}-I don't need them now.\N{\c&Hffffff&}{\i1}-I need to be careful.{\i0}` | `{\c&Hffffff&}– Teraz już ich nie {\c&Hffffff&}{\i1}zbieram.\N– Muszę uważać.{\i0}` | **#34 dokładnie**: kursywa drugiego mówcy obejmuje ostatnie słowo pierwszego. Do tłumacza trafia `-I don't need them now. -I need to be careful.` bez znaczników |
| C2 | `corpus-pairs/grand-blue-s2-06/source.en.ass` l. 272 | `{\i1}That's{\i0} where you're going?` | `{\i1}I ty{\i0} tam idziesz?` | akcent na złych słowach (powinno być „tam”); zakres od początku linii nie dostaje znaczników |
| C3 | `corpus-pairs/kaguya-s1-03/source.en.ass` l. 162 | `{\i1}You're{\i0} society's "darker side"!` | `{\i1}To ty jesteś{\i0} tą „mroczną stroną społeczeństwa”!` | zakres rozlany na trzy słowa (sens niesie „ty”) |
| C4 | `corpus-pairs/grand-blue-s2-10/source.en.ass` l. 490 (szyld, 6 kolorowych wersów) | `…\N{\c&H64199F&}Your Honkers Will Pierce…\N{\c&H000000&}Learn from…\N{\c&H914A80&}Top Secret…` | `…rozmiaru\N{\c&H64199F&}miseczki. Twoje zderzaki…\N…Ściśle\N{\c&H914A80&}tajne…` | kolor nagłówka zaczyna się w środku poprzedniej pozycji listy (dwa miejsca) |
| C5 | `corpus-pairs/grand-blue-s2-10/source.en.ass` l. 491 (szyld) | `{\c&HF5DBAE&}Magic Girl Lalako the Movie\N{\c&HCFBADE&}-Farming Saga Conclusion-` | `…Film\N– {\c&HCFBADE&}Zwieńczenie Sagi Rolniczej` | myślnik podtytułu w kolorze tytułu (drobne) |
| C6 | `corpus-pairs/kaguya-s1-04/source.en.ass` l. 4396–4397 (szyld odsłaniany `\clip`) | `…unanimously \N{\1a&H00&}forbid…\N{\1a&HFF&}student council` | `…\Nw {\1a&HFF&}samorządzie uczniowskim` | faza odsłaniania przesunięta o słowo; efekt animacji, nie akcent |

Spis przyczyn (punkt 6) pokazuje skalę dla kwestii lektora: na 1109 unikalnych linii z akcentem 1032 (93,1%) dostaje dziś znaczniki. Bez znaczników zostaje 73 (6,6%) z zakresem otwartym blokiem z początku linii lub wersu (np. 27 klatek Uzaki `{\pos(…)\fscx…\i1\bord…}There{\i0} you are!`, Kaguya `{\i1}I{\i0} will be the one feeding {\i1}you{\i0}`), 3 z mówcą albo zakresem w osobnym wersie (Koori, Koukaku, Joshiraku) i 1 z ponad 4 granicami. W szyldach (3413 unikalnych) bez znaczników zostaje: 546 linii z ponad 4 granicami (głównie kinetyka liter i odsłanianie `\alpha`), 387 z granicą na krawędzi wersu, 132 z kolorem samej interpunkcji, 108 z granicą w słowie i 44 z zakresem od początku linii. Zakresy zagnieżdżone praktycznie nie występują: 1 linia w kwestiach i 66 w szyldach (animacje), a 99,9% kwestii ma najwyżej 2 zakresy.

### C′. Linie oznaczane dziś źle: zamknięcie stylu tuż przed `\N`

Tag zamykający na końcu wersu (`{\i0}\N`) leży na krawędzi wersu, więc nie jest granicą znacznika. Zostaje tylko otwarcie, a zakres sięga do końca linii. Dotyczy to 11 unikalnych kwestii w korpusie (1% kwestii z akcentem), np.:

- `corpus/kaguya-sama/s1/GJM-source/BDs and Batching/Kaguya-sama/Kaguya06-Batch.ass` l. 112: `If anything I'm actually {\i1}bothered{\i0}\N by all the rumors about us!` → do tłumacza idzie `If anything I'm actually <s1>bothered by all the rumors about us!</s1>`, a `{\i0}` trafia proporcjonalnie, np. `Prawdę mówiąc, {\i1}przeszkadzają mi{\i0}\Nte wszystkie plotki o nas!`;
- dziewięć podobnych linii GJM w Kaguya S2–S3 (`{\i1}you'd{\i0}\N`, `{\i1}aware{\i0}\N`, `{\i1}some{\i0}\N`, …);
- angielska ścieżka `[Erai-raws] Katainaka no Ossan Kensei ni Naru II - 02` l. 24 (w praktyce plik ma polskie źródło, więc idzie normalizacją): `-{\i1\c&Hffffff&\fnTrebuchet MS}That's so like him.{\c}{\fn\i0}\N-Master.` daje znacznik na obu mówcach `-<s1>That's so like him. -Master.</s1>`, a wynik `…podobne.\N–{\c}{\fn\i0} Mistrzu.` ma kursywę na myślniku drugiego mówcy.

### D. Ścieżka bez znaczników jest ślepa na sens

Te same prawdziwe przekłady podane bez znaczników, czyli dzisiejsze zachowanie dla Google, DeepL i odrzuconych znaczników:

| # | Plik i linia `.pl.ass` | Źródło | Wynik bez znaczników | Wynik LLM ze znacznikami |
| --- | --- | --- | --- | --- |
| D1 | `ready/The.Detective.Is.Already.Dead.S02E01 … .pl.ass` l. 251 | `It's that I {\i1}can't{\i0}.` | `nie potrafię {\i1}ich zdobyć{\i0}.` (źle) | brak danych (plik sprzed znaczników) |
| D2 | `ready/Nowy folder/[SubsPlease] Lv999 no Murabito - 08 … .pl.ass` l. 354 | `listen to me {\i1}once{\i0}!` | `chociaż raz {\i1}posłuchać{\i0}!` (źle, powinno być „raz”) | brak danych |
| D3 | `ready/[Erai-raws] Tantei … Season 2 - 03 … .pl.ass` l. 84 | `it's {\i1}my{\i0} house` | `moim {\i1}własnym{\i0} domu` (źle) | `{\i1}moim{\i0}` (dobrze, A) |
| D4 | ten sam plik, l. 86 | `when {\i1}I'm{\i0} the detective` | `{\i1}ja jestem{\i0}` (za szeroko) | `{\i1}ja{\i0}` (dobrze) |
| D5 | ten sam plik, l. 103 | `Saikawa Yui-san's {\i0}Perfect Record{\i1}!` | `Perfect Record w {\i0}wykonaniu Saikawy Yui{\i1}!` (odwrócone) | `{\i0}Perfect Record{\i1} w wykonaniu…` (dobrze) |
| D6 | `ready/[Erai-raws] Tantei … Season 2 - 02 … .pl.ass` l. 102 | `I hope they {\i1}do{\i0} find you!` | `Oby {\i1}cię{\i0} nakryli!` (wzmacniające „do” nie ma odpowiednika) | brak danych |

Pierwotny błąd z #34 widać jeszcze w plikach sprzed znaczników: `ready/[SubsPlease] Sasaki to Pii-chan S2 - 02 … .pl.ass` l. 64 `Odci{\3c…}nek` (kolor rozcina słowo), l. 233 `{\i1}mnie?!{\i0}` (kursywa na interpunkcji), `ready/The.Iceblade … S02E02 … .pl.ass` l. 378 `{\i1}odstawiamy tę szopkę?{\i0}`. Dzisiejszy kod nie rozcina już słów i trzyma interpunkcję poza zakresem (testy `test_replace_visible_text_never_splits_a_word_with_a_colour_tag`, `…keeps_italic_off_trailing_punctuation…`).

## Wnioski

**Z #34 działa:**

- zakres w środku wersu (do dwóch zakresów, najwyżej 4 granice) idzie do LLM jako `<sN>` i trafia na przetłumaczone słowa niezależnie od długości i szyku (A: 7/7, B: 6/7, LLM zwraca znaczniki 56/56);
- tag nigdy nie rozcina słowa ani grafemu poza efektami w słowie; interpunkcja zostaje poza zakresem;
- negacja kursywy w stylu kursywnym i bloki komentarzy są obsłużone;
- zmyślone znaczniki są usuwane, a uszkodzone przechodzą na rozkład bez awarii.

**Z #34 nie działa (DoD issue niespełnione):**

1. **Mówca albo zakres w osobnym wersie** (C1, C4, C5): wersy są łączone przed tłumaczeniem, a granica na krawędzi wersu nie dostaje znacznika, więc ląduje proporcjonalnie. To dokładnie scenariusz z #34 i nie ma na niego testu regresji.
2. **Zakres otwarty blokiem z początku linii** (C2, C3; 73 unikalne kwestie, 6,6%): świadomie wyłączony (`_closes_a_range`, test `test_marked_text_leaves_a_range_opened_at_the_verse_start_unmarked`), a rozkład zgaduje słowo.
3. **Zamknięcie stylu tuż przed `\N`** (C′; 11 unikalnych kwestii): zakres sięga do końca linii, a tag zamykający ląduje proporcjonalnie.
4. **Ryzyko niezgodności stylu** (krok 8): `marked_text` i `replace_visible_text` liczą granice na różnych stylach po klonowaniu dialogu.

## Sprawdzenie projektu prototypem

Reguły W1–W3 ze specyfikacji sprawdziłem prototypem `_marked_boundaries` w scratchpadzie (podmiana funkcji w procesie, bez zmian w repo), tylko dla `marked_text`. Ustawienia tagów (W4–W5) prototyp nie obejmuje.

- Wszystkie oczekiwane `marked_text` z katalogu K zgadzają się z prototypem.
- Kwestie z akcentem bez znaczników: 77 → 3. Zostają: `Joshiraku 04 - Dialogue (gg).ass` l. 201 (ponad 4 granice), `Joshiraku 07 - Dialogue (gg).ass` l. 478 (pusty zakres między `{\fscx140\i0}` a `{\fscx100}`) i `[Erai-raws] Seihantai na Kimi to Boku 2nd Season - 05` l. 538 (`This isn't like {\i0}that!{\i1}`, negacja do końca linii w stylu kursywnym). Pierwsza wersja prototypu liczyła styki pustych wersów (`\N\N`) podwójnie; po ich złączeniu (decyzja lokalna w planie) tablica `Joshiraku 06 - Dialogue (gg).ass` l. 947 dostaje znaczniki.
- Zmienia się `marked_text` 85 unikalnych kwestii: 74 dostają znaczniki pierwszy raz, a 11 z C′ dostaje poprawny zakres. Pozostałe 1037 oznaczanych dziś kwestii zostaje bez zmian.
- W szyldach zmienia się 478 unikalnych linii: 386 dostaje znaczniki pierwszy raz (np. Grand Blue `Cakey\N{\c…}Café` → `Cakey <s1>Café</s1>`), w 90 zmienia się zakres (np. Kaguya `I {\c…}refuse to \N{\c…}ever do it again.` → `I <s1>refuse to</s1> ever do it again.`), a 2 tracą znaczniki, bo z cięciami na stykach przekraczają 4 granice (czat telefonu w `[lycoris.cafe] Toumei na Yoru ni Kakeru … - 07`, l. 130 i 172).

**Świadomie poza naprawą (ścieżka bez znaczników):** D1–D6 to rozkład proporcjonalny, który bez wyrównania słów nie zna sensu. Dotyczy Google i DeepL oraz rzadkich odrzuceń w LLM; w danych LLM zachował znaczniki w 56/56 i 7/7 przypadków.

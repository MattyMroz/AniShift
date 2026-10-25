---
kind: specification
status: draft
updated: 2026-10-25
---

# Specyfikacja: granice stylów po tłumaczeniu (#34)

## Cel

Inline'owy styl ASS z fragmentu linii (kursywa, pogrubienie, podkreślenie, przekreślenie, kolor wypełnienia, kolor obrysu) trafia po tłumaczeniu na polskie słowa o tym samym znaczeniu albo na kwestię tego samego mówcy, także gdy polski szyk i długości są inne niż w źródle. Zamyka [#34](https://github.com/MattyMroz/AniShift/issues/34).

## Użytkownik i intencja

Właściciel ogląda polskie napisy w mpv. Kursywa głosu zza kadru, wyróżnione słowo i kolor mówcy mają zostać przy właściwych słowach. Styl jednego mówcy nigdy nie może przejść na drugiego.

## Stan wyjściowy

Pełne dowody, ścieżki i linie: [evidence.md](evidence.md).

- Zakres w środku wersu (najwyżej 2 zakresy, 4 granice) idzie do LLM jako `<sN>…</sN>` i trafia dobrze: 7/7 w gotowych produktach, 6/7 w powtórce na zapisanych odpowiedziach, a LLM zwraca znaczniki w 56/56 linii.
- Znaczników nie dostaje granica na krawędzi wersu, więc kwestia drugiego mówcy w osobnym wersie (Koori 03, l. 374) dostaje kursywę na ostatnim słowie pierwszego mówcy.
- Znaczników nie dostaje też zakres otwarty blokiem z początku linii i zamknięty w jej środku (73 z 1109 unikalnych kwestii z akcentem, 6,6%), więc akcent ląduje na zgadniętym słowie (Grand Blue S2E06, l. 272).
- Zamknięcie stylu tuż przed `\N` nie jest granicą, więc 11 kwestii dostaje dziś zakres do końca linii (Kaguya06, l. 112).
- `marked_text` liczy granice na stylu źródła, a `replace_visible_text` na stylu klonu dialogu (`restyle.py:221-225` może włączyć pogrubienie, `204-218` zmienia kolor tekstu).
- Bez nienaruszonych znaczników (Google, DeepL, odrzucenie) styl idzie mapowaniem proporcjonalnym przyciąganym do krawędzi słów, które nie zna sensu.

## Pojęcia

- **Atrybut zakresu:** kursywa `\i`, pogrubienie `\b`, podkreślenie `\u`, przekreślenie `\s`, kolor wypełnienia `\c`/`\1c`, kolor obrysu `\3c`.
- **Stan efektywny:** wartości atrybutów zakresu na danym grafemie, wynikające ze stylu źródłowego zdarzenia i tagów przed tym grafemem. `\r` i `\rStyl` przywracają stan stylu zdarzenia, bo `marked_text` zna tylko ten styl. Kolory porównuje się jako wartość BGR bez kanału alfa, niezależnie od zapisu (`&HFFFFFF&`, `&Hffffff&`).
- **Styk wersów:** wszystkie tagi z końca wersu k−1 i z początku wersu k, traktowane jako jedno miejsce w tekście złączonym z wersów.
- **Blok początku linii:** tagi stojące przed pierwszym widocznym grafemem zdarzenia.
- **Nienaruszone znaczniki:** odpowiedź, którą dziś przyjmuje `_marker_anchors` (właściwe znaczniki w kolejności, niepuste zakresy, słowa poza zakresem zostają, gdy miało je źródło).

## Ustalenia

- Heurystyki mają postać logiki rozmytej na wartościach lingwistycznych. Ta zmiana nie wprowadza nowej heurystyki ani progu: granica zakresu jest faktem (stan atrybutu zmienia się albo nie), a tam, gdzie potrzebny jest sens, rozstrzyga LLM znacznikami. Mapowanie proporcjonalne zostaje jedynie zapasem.
- Limity napisów (42 znaki, 17 CPS) są wytycznymi. Zmiana ich nie dotyka; łamanie robi dalej rdzeń układu.
- Twarde są tylko zakazy chroniące sens (sekcja „Zakazy chroniące sens”).
- Kontrakt znaczników pozostaje bez zmian: składnia `<sN>…</sN>` (`anishift/text/markers.py`), najwyżej 2 zakresy i 4 granice, zakresy kolejno i bez zagnieżdżeń, ten sam prompt LLM.
- Tłumacz dalej dostaje linię bez `\N` (wersy złączone spacją). Rdzeń układu jest jedynym miejscem łamania.

## Wymagania funkcjonalne

- **W1. Zakres od początku linii.** Gdy pierwsza granica linii (wewnątrz wersu albo na styku z W2) wyłącza wyróżnienie (`\i`, `\b`, `\u`, `\s`) włączone blokiem początku linii, a to wyróżnienie nie jest bazą linii w dzisiejszym sensie (`_closes_a_range`: nie trwa na ostatnim grafemie albo nie wraca na dalszej granicy, przy czym granice z W2 też się liczą), `marked_text` otwiera zakres na pierwszym grafemie: `{\i1}Why{\i0} are you here?` → `<s1>Why</s1> are you here?`. Gdy wyróżnienie jest bazą linii, obowiązuje dzisiejsza negacja (K9).
- **W2. Zmiana stanu na styku wersów.** Styk wersów jest granicą zakresu wtedy i tylko wtedy, gdy stan efektywny któregoś atrybutu zakresu różni się między ostatnim grafemem przed stykiem a pierwszym grafemem po nim. Powtórzony tag bez zmiany (`{\c&Hffffff&}` na każdym wersie, `{\i0}\N{\i1}` w linii całej kursywą) granicą nie jest. Reguła obejmuje zarówno otwarcie na początku wersu (`\N{\i1}-I need…`), jak i zamknięcie na jego końcu (`{\i1}bothered{\i0}\N by…`). Styki o tej samej pozycji w tekście złączonym (puste wersy `\N\N`) są jednym stykiem.
- **W3. Te same warunki co dziś.** Do granic z W1 i W2 stosują się obecne warunki `_marked_boundaries`: najwyżej 4 granice, żadna granica w słowie, każdy zakres zawiera słowo. W linii, w której pojawiło się cięcie z W1 albo W2, dochodzi jeden warunek: poza zakresami zostaje przynajmniej jedno słowo, bo zakres całej linii nie jest akcentem. Linie bez takiego cięcia zachowują dzisiejsze warunki bez zmian.
- **W4. Ustawienie tagów.** Przy nienaruszonych znacznikach granice zakresów z W1 i W2 stoją dokładnie na pozycjach znaczników. Wszystkie tagi styku wersów przechodzą razem na pozycję znacznika.
- **W5. Podział bloku początku linii.** Dla zakresu z W1 na pozycję znacznika przechodzą tylko polecenia wyróżnienia, które ten zakres otwierają. Pozostałe polecenia bloku (`\pos`, `\an`, `\fscx`, `\bord`, `\q` i inne) zostają na początku linii, w tej samej kolejności: `{\pos(960,1024)\i1}There{\i0} you are!` + `O, <s1>tu</s1> jesteś!` → `{\pos(960,1024)}O, {\i1}tu{\i0} jesteś!`.
- **W6. Ten sam styl po obu stronach.** `replace_visible_text` liczy granice znaczników na stylu, z którego powstał klon dialogu albo szyldu (`clone_source`), czyli na tym samym stylu, który dostał `marked_text`.
- **W7. Bez znaczników bez zmian.** Gdy przekład nie ma nienaruszonych znaczników (Google, DeepL, odrzucenie, linia bez granic), wynik `replace_visible_text` jest bajtowo taki jak dziś.
- **W8. Regresja #34.** Dwie kwestie różnych mówców w osobnych wersach, z różnym stylem i nierówną długością przekładu, zachowują styl swojego mówcy po `layout_dialogue`.

## Inwarianty

- **I1.** Linia, która dziś dostaje znaczniki i nie ma granicy z W1 ani W2, dostaje identyczny `marked_text`.
- **I2.** Polecenia override zdarzenia zostają zachowane co do liczby i kolejności. Jedyna dozwolona zmiana bloków to podział bloku początku linii z W5 na dwa.
- **I3.** Tag nie rozcina słowa ani grafemu, z wyjątkiem efektów stojących w środku słowa już w źródle.
- **I4.** `strip_span_markers(marked_text(x)) == visible_text(x)`.
- **I5.** `SpokenLine.text` (wejście TTS, klucz FBF) nie zawiera znaczników.
- **I6.** Rysunki, karaoke i kwestia z przekładem równym tekstowi źródła zostają bajtowo bez zmian.
- **I7.** Granice zakresów zachowują kolejność ze źródła.

## Zakazy chroniące sens

- **Z1.** Przy nienaruszonych znacznikach styl jednego mówcy nie obejmuje słów drugiego.
- **Z2.** Przy nienaruszonych znacznikach granica zakresu nie leży gdzie indziej niż znacznik.
- **Z3.** Tag nie rozcina słowa (I3).

## Zakazane

- Zmiana promptu LLM, składni znaczników, limitu 2 zakresów i 4 granic.
- Zmiana ścieżki bez znaczników (`_map_anchors`, `_snapped`, `_spread_inside`, `_monotonic_anchors`) i wag rdzenia układu.
- Nowa zależność, nowy moduł, nowa stała progowa.
- Wysyłanie `\N` do tłumacza.
- Zmiany w `restyle.py`, `fitting.py`, `layout.py` i w silnikach tłumaczenia.

## Zakres

- `marked_text` i `_marked_boundaries` w `anishift/services/subtitles/text.py`: W1–W3.
- `_placed_tags` w tym samym pliku: W4–W5.
- `tagged_line` w `anishift/services/subtitles/linebreak.py`: W6.
- Testy z katalogu przypadków i dostosowanie istniejących oczekiwań (lista w planie).
- Aktualizacja pułapek `text.py` w `anishift/services/subtitles/AGENTS.md`.
- Ta sama reguła obejmuje kwestie i szyldy, bo `marked_text` jest wspólne (zob. D1).

## Poza zakresem

- Ścieżka bez znaczników (Google, DeepL, uszkodzone znaczniki), która wymagałaby wyrównania słów źródła i przekładu.
- Więcej niż 2 zakresy, zakresy zagnieżdżone, efekty w słowie, kinetyka i odsłanianie `\alpha`.
- Atrybuty spoza listy: przezroczystość, krój `\fn`, rozmiar `\fs`. `\rStyl` nie wnosi stanu stylu nazwanego (liczy się jak `\r`).
- Licznik odrzuconych znaczników w raporcie układu.
- SRT jako źródło (znaczniki HTML działają jak dziś).

## Odłożone

- Kolory i krój otwierane blokiem początku linii (W1 tylko dla wyróżnień): w kwestiach brak przypadku w danych, a w szyldach to styl pozycyjny (D2).
- Reset `\rStyl` na styku wersów jako granica mówcy: brak w danych (K17).
- Licznik odrzuceń znaczników w `LayoutReport`: wymaga zmiany API `replace_visible_text`; wróci, gdy potrzebny będzie pomiar na przebiegach właściciela.

## Odrzucone

- Wysyłanie wersów (`\N`) do tłumacza: wiąże polski szyk z angielskim podziałem i odwraca decyzję, że rdzeń układu jest jedynym miejscem łamania.
- Odwrócenie zakresu (zakres na słowach bez stylu) dla W1: przy zmianie szyku zostawia akcent na początku linii (sprawdzone: `{\i1}Co ty{\i0} tu robisz, czemu?`).

## Katalog przypadków

Oczekiwane wyniki dla stylu domyślnego `SSAStyle()` (biały tekst, bez wyróżnień), chyba że zaznaczono inaczej. „Dziś” oznacza wynik obecnego kodu, sprawdzony uruchomieniem.

| # | Źródło | `marked_text` | Odpowiedź tłumacza | Oczekiwany wynik `replace_visible_text` | Dziś |
| --- | --- | --- | --- | --- | --- |
| K1 | `{\i1}Why{\i0} are you here?` | `<s1>Why</s1> are you here?` | `Co ty tu robisz, <s1>czemu</s1>?` | `Co ty tu robisz, {\i1}czemu{\i0}?` | bez znaczników: `{\i1}Co ty{\i0} tu robisz, czemu?` |
| K2 | `{\pos(960,1024)\i1}There{\i0} you are!` | `<s1>There</s1> you are!` | `O, <s1>tu</s1> jesteś!` | `{\pos(960,1024)}O, {\i1}tu{\i0} jesteś!` | bez znaczników |
| K3 | jak K1 | jak K1 | `<s1>Czemu</s1> tu jesteś?` | `{\i1}Czemu{\i0} tu jesteś?` | ten sam wynik bez znaczników |
| K4 | `{\i1}I{\i0} will be the one feeding {\i1}you{\i0}, Shinomiya!` | `<s1>I</s1> will be the one feeding <s2>you</s2>, Shinomiya!` | `To <s1>ja</s1> będę karmić <s2>ciebie</s2>, Shinomiya!` | `To {\i1}ja{\i0} będę karmić {\i1}ciebie{\i0}, Shinomiya!` | bez znaczników: `{\i1}To{\i0} ja … {\i1}ciebie{\i0}` |
| K5a | `{\c&Hffffff&}-I don't need them now.\N{\c&Hffffff&}{\i1}-I need to be careful.{\i0}` (Koori 03) | `-I don't need them now. <s1>-I need to be careful.</s1>` | `– Teraz już ich nie zbieram. <s1>– Muszę uważać.</s1>` | `{\c&Hffffff&}– Teraz już ich nie zbieram. {\c&Hffffff&}{\i1}– Muszę uważać.{\i0}`; po `layout_dialogue` (bez profilu): `{\c&Hffffff&}– Teraz już ich nie zbieram.\N{\c&Hffffff&}{\i1}– Muszę uważać.{\i0}` | `…nie {\c&Hffffff&}{\i1}zbieram.\N– Muszę uważać.{\i0}` (Z1 złamany) |
| K5b | jak K5a | jak K5a | `– Teraz już ich nie zbieram, nie są mi już do niczego potrzebne. <s1>– Uważaj.</s1>` | `{\c&Hffffff&}– Teraz już ich nie zbieram, nie są mi już do niczego potrzebne. {\c&Hffffff&}{\i1}– Uważaj.{\i0}` | kursywa zaczyna się w kwestii pierwszego mówcy |
| K5c | jak K5a | jak K5a | `– Teraz już ich nie zbieram. – <s1>Muszę uważać.</s1>` | `{\c&Hffffff&}– Teraz już ich nie zbieram. – {\c&Hffffff&}{\i1}Muszę uważać.{\i0}` (myślnik bez kursywy, dopuszczalne) | jak K5a |
| K6 | `{\i1}-Hi.{\i0}\N-Hello.` | `<s1>-Hi.</s1> -Hello.` | `<s1>– Cześć.</s1> – Witaj.` | `{\i1}– Cześć.{\i0} – Witaj.` | bez znaczników |
| K7 | `{\c&H00FFFF&}-Hi!\N{\c&HFFFFFF&}-Hello!` | `-Hi! <s1>-Hello!</s1>` | `– Hej! <s1>– Cześć!</s1>` | `{\c&H00FFFF&}– Hej! {\c&HFFFFFF&}– Cześć!` | bez znaczników |
| K8 | `This scene is inspired by\N{\i1}Idiots Are Coming in Tanks{\i0} (1964).` | `This scene is inspired by <s1>Idiots Are Coming in Tanks</s1> (1964).` | `Scenę zainspirował film <s1>Idioci jadą czołgami</s1> (1964).` | `Scenę zainspirował film {\i1}Idioci jadą czołgami{\i0} (1964).` | bez znaczników |
| K9 | `{\i1\q2}Isn't it just oh so {\i0}convenient{\i1}\N that the door would get stuck?` (styl pogrubiony) | `Isn't it just oh so <s1>convenient</s1> that the door would get stuck?` | `Jakie to <s1>wygodne</s1>, że drzwi akurat się zacięły.` | `{\i1\q2}Jakie to {\i0}wygodne{\i1}, że drzwi akurat się zacięły.` | bez znaczników |
| K10 | `{\i0}Why\N{\i1}are {\i0}you here?` (styl kursywny) | `Why <s1>are</s1> you here?` | `Czemu tu <s1>jesteś</s1>?` | `{\i0}Czemu tu {\i1}jesteś{\i0}?` | bez znaczników |
| K11 | `{\c&Hffffff&}You're always going on\N{\c&Hffffff&}about doing things for others,` | bez znaczników | dowolna | jak dziś | bez znaczników |
| K12 | `{\i1}I was scared of change,{\i0}\N{\i1}so I kept thinking.{\i0}` | bez znaczników (cała linia) | dowolna | jak dziś (`…keeps_split_verse_prefixes_together_at_a_word_start`) | bez znaczników |
| K13 | `{\i1}Water{\i0}?` | bez znaczników (cała linia, W3) | `Woda?` | `{\i1}Woda{\i0}?` | to samo |
| K14 | `{\i0}Why {\i0}are you here?{\i1}` (styl kursywny) | bez znaczników | dowolna | jak dziś | to samo |
| K15 | `{\i1}A{\i0} b {\i1}c{\i0} d {\i1}e{\i0} f` | bez znaczników (> 4 granice) | dowolna | jak dziś | to samo |
| K16 | `T{\3c&H1&}h{\3c&H2&}e {\3c&H3&}Ice` | bez znaczników (granica w słowie) | dowolna | jak dziś | to samo |
| K17 | `-Hi.\N{\rAlt}-Hello.` | bez znaczników (`\rAlt` liczony jak `\r`, więc stan się nie zmienia) | dowolna | jak dziś | to samo |
| K18 | `{\c&H0000FF&}Red{\c&HFFFFFF&} sword is here` | `Red <s1>sword is here</s1>` (bez zmian) | `<s1>Tu jest miecz</s1> czerwony` | jak dziś: odrzucone, `{\c&H0000FF&}Tu jest{\c&HFFFFFF&} miecz czerwony` (zob. D2) | to samo |
| K19 | `Well, she {\i0}did{\i1} spend so much time alone\Nthat it pushed her into a rampage.` (styl kursywny) | `Well, she <s1>did</s1> spend…` (bez zmian) | `Cóż, była sama tak długo, że aż wpadła w szał.` (bez znaczników) | jak dziś: `Cóż, {\i0}była{\i1} sama…` (zob. D3) | to samo |
| K20 | `The {\c&H0000FF&}Red{\c&HFFFFFF&} Sword` | `The <s1>Red</s1> Sword` (bez zmian) | `<s1></s1>Czerwony Miecz` | jak dziś: rozkład (`…falls_back_when_markers_wrap_nothing`) | to samo |
| K21 | `thanks to {\i1}someone{\i0}...` | bez zmian | `przez <s1>pewną osobę</s1>...` | `przez {\i1}pewną osobę{\i0}...` | to samo |
| K22 | `{\c&H0600A9&\pos(1,2)}A {\c&HFEFDFE&}Flying, Handsome Man Appeared!` | bez zmian | `<s1>Pojawił się latający przystojniak!</s1>` | jak dziś: odrzucone, `{\c&H0600A9&\pos(1,2)}Pojawił {\c&HFEFDFE&}się latający przystojniak!` (zob. D4) | to samo |
| K23 | jak K4 | jak K4 | `<s2>Ciebie</s2> będę karmić <s1>ja</s1>, Shinomiya!` | rozkład jak dla linii bez znaczników (zła kolejność) | — |
| K24 | `Hello {\i1}my {\b1}dear{\b0} friend{\i0}` | `Hello <s1>my</s1> dear <s2>friend</s2>` (bez zmian) | `Witaj, <s1>mój</s1> drogi <s2>przyjacielu</s2>` | `Witaj, {\i1}mój{\b1} drogi {\b0}przyjacielu{\i0}` | to samo |
| K25 | dowolne z K1–K10 | jak wyżej | przekład Google/DeepL (znaczniki usunięte) | jak dziś (W7) | to samo |
| K27 | `If anything I'm actually {\i1}bothered{\i0}\N by all the rumors about us!` (Kaguya06) | `If anything I'm actually <s1>bothered</s1> by all the rumors about us!` | `Prawdę mówiąc, raczej <s1>przeszkadzają</s1> mi te wszystkie plotki o nas!` | `Prawdę mówiąc, raczej {\i1}przeszkadzają{\i0} mi te wszystkie plotki o nas!` | `…<s1>bothered by all the rumors about us!</s1>`, a `{\i0}` ląduje proporcjonalnie |
| K28 | `-{\i1\c&Hffffff&\fnTrebuchet MS}That's so like him.{\c}{\fn\i0}\N-Master.` (Katainaka 02) | `-<s1>That's so like him.</s1> -Master.` | `– <s1>To do niego podobne.</s1> – Mistrzu.` | `– {\i1\c&Hffffff&\fnTrebuchet MS}To do niego podobne.{\c}{\fn\i0} – Mistrzu.` | `-<s1>That's so like him. -Master.</s1>`; kursywa na myślniku drugiego mówcy |
| K26 | `-Hi!\N{\c&HFFFFFF&}-Hello!` w stylu `Default` z żółtym tekstem, zdarzenie przeniesione do klonu `Default (dialog)` z białym tekstem | `-Hi! <s1>-Hello!</s1>` | `– Hej! <s1>– Cześć!</s1>` | `– Hej! {\c&HFFFFFF&}– Cześć!` (granice liczone na `Default`, W6) | bez znaczników; po W2 bez W6 znaczniki zostałyby odrzucone przez niezgodność stylu |

## Warunki sukcesu

- **S1 (test).** Każdy wiersz katalogu K1–K28 jest testem jednostkowym i przechodzi. K5a, K5b i K26 przechodzą przez `layout_dialogue` albo `tagged_line`.
- **S2 (pomiar na korpusie).** Spis unikalnych kwestii z akcentem na tym samym zbiorze 254 plików, co w evidence, pokazuje najwyżej 3 kwestie bez znaczników (dziś 77): Joshiraku 04 l. 201, Joshiraku 07 l. 478, Seihantai 05 l. 538, z powodami jak w evidence (prototyp).
- **S3 (przegląd zmian).** Lista wszystkich linii korpusu (kwestie i szyldy), dla których `marked_text` zmienia się względem stanu sprzed zmiany, jest wypisana i przejrzana. Każda zmiana wynika z cięcia W1 albo W2 (razem z warunkiem W3 w tej samej linii). Zmiana w linii bez takiego cięcia łamie I1.
- **S4 (regresja bez znaczników).** `python -m scripts.subtitle_quality replay` przed zmianą i po niej, porównane `--compare … --events`, daje zero różnic zdarzeń (W7).
- **S5 (zapisane odpowiedzi LLM).** Testy integracyjne na `workspace/.quality/experiments/styles` przechodzą bez zmian oczekiwań, a powtórka writera na tych odpowiedziach daje te same 7 wyników co w evidence (B).
- **S6 (bramki repo).** ruff, ruff format, mypy (także `--platform linux`) i pytest przechodzą.
- **S7 (ocena człowieka).** Właściciel akceptuje katalog K przed kodem. Po kodzie orkiestrator przegląda listę z S3, a właściciel ocenia w mpv jedną linię dwóch mówców i jedną z zakresem od początku linii z najbliższego tłumaczonego odcinka, który je ma.

## Nierozstrzygnięte (do decyzji właściciela)

- **D1. Czy reguła obejmuje też szyldy?** `marked_text` jest wspólne dla kwestii i szyldów. Według prototypu W2 zmienia 478 unikalnych linii szyldów: 386 dostaje znaczniki (np. `Cakey\N{\c…}Café`, Grand Blue S2E10 l. 491), 90 dostaje dokładniejszy zakres, a 2 linie czatu telefonu (lycoris 07, l. 130 i 172) tracą znaczniki przez limit 4 granic. Szyldy z ponad 2 zakresami (listy, odsłanianie) zostają bez zmian. **Rekomendacja:** tak, jedna reguła dla obu, bo osobna wymagałaby parametru rodzaju linii, a każdą zmianę szyldu i tak wypisuje S3. Dwie utracone linie przyjmujemy: mają więcej niż dwa kolory wersów, więc i dziś znaczniki obejmują tylko część z nich.
- **D2. Czy W1 ma objąć kolory i krój otwierane blokiem początku linii?** Dziś taki zakres oznaczany jest odwrotnie (na słowach bez koloru) i działa, dopóki szyk zostaje (K18). W kwestiach nie ma przypadku w danych. W szyldach to zwykle styl pozycyjny pierwszego słowa (Yasei: „The”, „A”), gdzie rodzajnik znika w przekładzie. **Rekomendacja:** nie teraz, tylko wyróżnienia `\i \b \u \s`.
- **D3. Co, gdy wyróżnione słowo nie ma polskiego odpowiednika** (wzmacniające „do”/„did”, K19, D6 w evidence)? Dziś rozkład kładzie styl na zgadniętym słowie. Możliwość: przy nienaruszonych znacznikach z pustym zakresem albo przy jawnym pominięciu postawić oba tagi obok siebie (brak widocznego wyróżnienia, polecenia zachowane). Danych o częstości brak; w 14 realnych liniach ścieżki LLM ani razu. **Rekomendacja:** zostawić jak dziś i wrócić, gdy licznik odrzuceń (odłożony) pokaże skalę.
- **D4. Zakres obejmujący cały przekład** (rodzajnik źródła znika, K22). Dziś walidacja go odrzuca, a pierwsze polskie słowo dostaje kolor pierwszego słowa źródła. **Rekomendacja:** zostawić. To styl pozycyjny karty tytułowej, a wynik wygląda jak w źródle.
- **D5. Zmiana oczekiwań istniejących testów.** Pięć testów zapisuje dziś brak znaczników dla przypadków z W1–W2 (lista w planie). **Rekomendacja:** zmienić ich oczekiwania i nazwy zgodnie z K1, K8, K9, K10 i `{\i1}You're{\i0} society's darker side!` → `<s1>You're</s1> society's darker side!`.

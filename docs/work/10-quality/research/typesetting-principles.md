# Jak profesjonaliści oceniają, że napis wygląda dobrze

Status: research do specyfikacji celu (`visual-quality.md`). Stan na 2026-10-18. Baseline: worktree `AniShift-wt/fuzzy`, commit `2301cd0`.

Zakres: łamanie i kształt dialogów, typesetting szyldów przy dłuższym przekładzie, czytelność, polskie „sierotki”, praktyka Shishy, zasady lektora. Poza zakresem: timing, kolory, ruch.

Pewność cytatów. Teksty BBC, Karamitroglou, PWN i przewodnika unanimated pobrałem w surowej postaci (curl) i cytuję dosłownie. Netflix i dokumentacja Aegisub przeszły przez narzędzie, które wyciąga treść modelem (WebFetch, prośba o dosłowne cytaty). Przed decyzją opartą na jednym zdaniu z tych dwóch źródeł warto je otworzyć ręcznie. Badanie Gerber-Morón i Szarkowskiej czytałem bezpośrednio w PDF.

## Odpowiedź w skrócie

1. **Sens przed kształtem.** BBC daje pierwszeństwo kryterium językowemu nad geometrycznym, Karamitroglou też, a eye-tracking potwierdza preferencję widzów dla łamania składniowego. Shisha łamie tak samo: 56% ręcznych łamań po interpunkcji, zero po przyimku lub jednoliterowym słowie.
2. **Gdzie łamać:** po interpunkcji, przed spójnikiem, przed przyimkiem. Czego nie rozdzielać: rzeczownika od przymiotnika, imienia od nazwiska, czasownika od posiłkowego, zwrotnego „się” i przeczenia (Netflix, BBC).
3. **Rozcięty wyraz** jest wśród źródeł najmocniej potępiony (BBC: „especially disruptive”).
4. **Najwyżej dwa wiersze** (Netflix, BBC, Karamitroglou, Aegisub).
5. **Długość wiersza to proxy szerokości.** Źródła podają 42 (Netflix PL), 37 (BBC teletext, poza nim 68% szerokości obrazu) i ok. 35 znaków (Karamitroglou). Shisha ma 24–25% wierszy dłuższych niż 42 znaki, a w jej ramce mieści się 57 znaków.
6. **Kształt jest słabym kryterium.** Netflix PL zaleca piramidę z krótszym wierszem na górze i odradza 1–2 słowa w górnym wierszu. U Shishy górny wiersz jest krótszy tylko w 56% łamań.
7. **Jednoliterowe słowo na końcu wiersza.** Według PWN w tekście ciągłym wolno je zostawić, w tytułach należy przenieść. W dialogach zakaz wynika już z reguły „łam przed przyimkiem i spójnikiem”, a w szyldach z reguły dla tytułów (to mój wniosek).
8. **Szyld: czytelność przed wiernością miejsca i kształtu.** Przewodnik unanimated: „much better to sacrifice font size and orientation if the result is well readable”. Aegisub: „Will you be able to make the translation easily legible?”.
9. **Żadne znalezione źródło nie podaje liczbowej granicy ściśnięcia `\fscx` ani minimalnej czytelnej wielkości szyldu.** Te liczby trzeba skalibrować na galerii.
10. **Shisha wielkość szyldu ustawia wyłącznie przez `\fscx`/`\fscy`.** Nie używa `\fs` ani `\fsp`. Do zmieszczenia tekstu ściska go do 77–79% szerokości (pasek TV). Dzieli szyld na dwa wiersze, gdy angielski miał jeden, i skraca treść po sensie („CARD DECLINED” → „Odmowa”).
11. **Szyld nie może iść w jednym napisie z dialogiem.** Netflix każe usuwać szyld powtórzony w dialogu, a przy kolizji z napisem ekranowym dialog podnosi do góry.
12. **Lektor:** nie znalazłem źródła zasad, co czyta polski lektor. Decyzje z `visual-quality.md` §4 zostają decyzjami właściciela.

## 1. Dialog: co mówią źródła

### 1.1 Netflix: Polish Timed Text Style Guide

URL: <https://partnerhelp.netflixstudios.com/hc/en-us/articles/216787928-Polish-Timed-Text-Style-Guide>. Dostęp 2026-10-18. Strona nie ma daty aktualizacji, ostatni wpis w change logu: 2025-10-17.

- §3: „42 characters per line”.
- §16: „Adult programs: Up to 17 characters per second”.
- §12 Line Treatment: „Maximum two lines.”, „Text should usually be kept to one line, unless it exceeds the character limitation.”, „Prefer a bottom-heavy pyramid shape for subtitles when multiple line break options present themselves”, „avoid having just one or two words on the top line.”
- §21: „Please ensure subtitles are positioned accordingly to avoid overlap with on-screen text.”, „Where subtitles are raised, avoid creating sequences where subtitles jump up and down.”
- §9: „Forced narratives that are redundant (e.g. identical to onscreen text or covered in the dialogue) must be deleted.”, „Never combine a forced narrative with dialogue in the same subtitle.”
- §18: „Only subtitle plot-pertinent songs if the rights have been granted.”
- Polski przewodnik **nie** mówi, gdzie łamać wiersz, ani nie wspomina o jednoliterowych słowach. Obowiązują reguły ogólne.

### 1.2 Netflix: wymagania ogólne

URL: <https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617-Timed-Text-Style-Guide-General-Requirements>. Ostatni wpis w change logu: 2022-10-07.

- §4: „The line should be broken: after punctuation marks, before conjunctions, before prepositions”. „The line break should not separate: a noun from an article, a noun from an adjective, a first name from a last name, a verb from a subject pronoun, a prepositional verb from its preposition, a verb from an auxiliary, reflexive pronoun or negation”.
- §5: przy nieuniknionej kolizji z tekstem u góry i u dołu ekranu „the subtitle should be placed where easier to read.”

### 1.3 BBC Subtitle Guidelines

URL: <https://www.bbc.co.uk/accessibility/forproducts/guides/subtitles/>. Na stronie: „Version 1.2.5”. Dostęp 2026-10-18, surowy HTML.

- §3.1: 37 znaków w teletekście, w innych formatach „68% of the width of a landscape 16:9 video”. Przy czcionkach proporcjonalnych „impossible to determine the width of the line based on the number of characters alone”.
- §3.4: „The ideal line-break will be at a piece of punctuation like a full stop, comma or dash.” Nie rozdzielać: rodzajnika i rzeczownika, przyimka i dalszej frazy, spójnika i dalszej frazy, zaimka i czasownika, części złożonego czasownika. „However, since the dictates of space within a subtitle are more severe than between subtitles, line breaks may also take place after a verb.”
- §3.4: „Line breaks within a word are especially disruptive to the reading process and should be avoided. Ideal formatting should therefore compromise between linguistic and geometric considerations but with priority given to linguistic considerations.”
- §3.6: „In general, ‘long and thin’ subtitles are less disruptive of picture content than are ‘short and fat’ subtitles, but this is not always the case.”
- §3.9: zdanie dzielone między kolejne napisy tnie się na granicach zdań składowych. „Random segmentation must certainly be avoided”.
- §3.9: „Because line breaks require considering all of the above, they are better inserted manually. Implementers should avoid automatic line breaking.”

### 1.4 Karamitroglou (1998), „A Proposed Set of Subtitling Standards in Europe”

URL: <https://translationjournal.net/journal/04stndrd.htm> (Translation Journal 2(2)).

- „A maximum of two lines of subtitles should be presented at a time.” Pojedynczy wiersz zajmuje dolną pozycję.
- „Each subtitle line should allow around 35 characters […] An increase in the number of characters, attempting to fit over 40 per subtitle line, reduces the legibility of the subtitles because the font size is also inevitably reduced.”
- „Segmentation at the highest nodes: Subtitled text should appear segmented at the highest syntactic nodes possible.”
- „From a single-line to a two-line subtitle: It is better to segment a long single-line subtitle into a two-line subtitle, distributing the words on each line.” Ta reguła **przeczy** Netflixowi (zob. §5).

### 1.5 Badanie z widzami: Gerber-Morón i Szarkowska (2018)

„Line breaks in subtitling: an eye tracking study on viewer preferences”, Journal of Eye Movement Research 11(3):2, doi 10.16910/jemr.11.3.2. PDF: <https://ddd.uab.cat/pub/artpub/2018/238546/joueyemov_a2018v11n3p2.pdf>.

- Streszczenie, s. 1: „We tested 21 English, 26 Spanish and 21 Polish hearing people […] Our results show that viewers prefer syntactically segmented line breaks.”
- S. 2, za Karamitroglou: „If geometry is in conflict with syntax, then preference is given to the latter”. Za Carrollem i Ivarssonem: „the upper line should preferably be shorter to keep as much of the image as free”.
- **Ograniczenie**, s. 5: „The subtitles used in this study were in English.” Polacy oceniali angielskie napisy, więc badanie nie dowodzi niczego o łamaniu polskiego tekstu.

### 1.6 Polska norma typograficzna: jednoliterowe słowa

- PWN, zasady pisowni [204] 54.8.1 (strona sjp.pwn.pl zwracała 500, tekst z kopii w Internet Archive): „Jednoliterowe spójniki i przyimki (a, i, u, w itd.) mogą pozostawać na końcu wiersza w tekście ciągłym, natomiast w tytułach książek i ich rozdziałów winny być przenoszone do następnego wiersza.”
- Poradnia PWN, Adam Wolański, „sieroty na końcu wiersza”, 28.01.2008 (<https://sjp.pwn.pl/poradnia/haslo/sieroty-na-koncu-wiersza;8893.html>, tekst z Internet Archive), cytuje „Polszczyznę na co dzień”: „w wierszach tekstu, które liczą powyżej 40 znaków, nie należy pozostawiać na końcu wiersza jednoliterowych spójników i przyimków”. Uzasadnienie dotyczy tekstu justowanego: przy prawym marginesie powstają „nienaturalnie duże odstępy”.
- O napisach filmowych wprost: **brak źródła**. Polski przewodnik Netflixa nie porusza tematu.
- Wniosek: napisy są wyśrodkowane, nie justowane, więc typograficzne uzasadnienie nie przenosi się na nie wprost. Ten sam efekt daje jednak reguła Netflixa „łam przed spójnikiem i przyimkiem”, bo „w”, „z”, „o”, „u”, „i”, „a” trafiają wtedy na początek następnego wiersza. Szyld bywa bliższy tytułowi niż tekstowi ciągłemu, więc dla szyldów pasuje ostrzejsza część reguły 54.8.1.

## 2. Szyldy: co mówią źródła

### 2.1 Dokumentacja Aegisub: wprowadzenie do typesettingu

URL: <https://aegisub.org/docs/latest/typesetting/>.

- „the holy grail of sign typesetting is to make the subtitle look like it's a part of the image that was always there.”
- „Is the sign actually important to the plot?” oraz „Will you be able to make the translation easily legible?”. Przy braku miejsca: „consider putting a translation note as a normal 'toptitle' instead.”
- O szyldzie czytanym na głos: „should consider skipping the sign typeset because having both text and dialogue may overload the viewer.”
- O dialogu: „Sometimes you can compress the text horizontally a bit to squeeze it in”, a kiedy indziej „split the text block into two different lines and display one after the other”. „Make sure that no more than two lines of text are visible at a time.”

### 2.2 Przewodnik typesettingu unanimated

URL: <https://unanimated.github.io/ts/>. Strony `ts-positioning.htm`, `ts-examples.htm`, `ts-fonts.htm` i `ts-basics.htm`, surowy HTML.

- O tytule odcinka: „no need to go crazy trying to match the position and orientation of the sign while sacrificing readability.” Po przykładzie: „It's much better to sacrifice font size and orientation if the result is well readable and looks good.”
- „If the JP is in the middle and you can't exactly fit the typeset in the middle as well, you may split it like this (if the words allow it).”
- „Sometimes masking is obviously the better option, because you don't wanna use \fs15 and make it look bad and unreadable at the same time.”
- „Using \fscx150 doesn't exactly produce the same results as having an actually "wide" font.” Oraz: „Sometimes extremes are needed to either match the original or to fit the sign where you need it.”
- O obrysie: „make sure you can actually afford it without making the font look unreadable.”

### 2.3 Czego nie znalazłem

- Liczbowej granicy akceptowalnego ściśnięcia poziomego (`\fscx`) w fansubach ani w typografii. Szukałem w dokumentacji Aegisub, w przewodniku unanimated i w ogólnych źródłach typograficznych: **brak źródła**. Znalazłem tylko jakościowe ostrzeżenia, że skalowanie zniekształca litery.
- Minimalnej czytelnej wielkości szyldu w pikselach: **brak źródła**. BBC i Netflix nie definiują wielkości dla szyldów.
- Ogólnodostępnych przewodników stylu GJM ani Kaleido dotyczących dopasowania szyldów: w tej sesji **brak źródła**.

## 3. Praktyka Shishy, policzona na korpusie

Skrypty i wyniki: `workspace/.quality/experiments/research-principles/`. Dane: `shisha_practice.py` → `shisha-practice.json`; widok `shisha-practice-view.txt`; długie wiersze `wrap_check.py` → `wrap-check.txt`; render `wrap_longest.py` → `longest-both.png`. Para: `corpus-pairs/certain-dark-item-0{1,2}/` (`reference.pl.ass` Shishy, `source.en.ass` VARYG/CR). Klasyfikację łamań robi heurystyka z listami słów, nie ręczna ocena, więc kategorie są przybliżone.

**Uwaga o błędnym pomiarze:** mój pierwszy szacunek szerokości (Pillow) wskazał, że libass zawija 22 i 43 jednowierszowe zdarzenia. Render libass go obalił: 57- i 55-znakowe wiersze mieszczą się w jednym wierszu. Pola `single_line_wider_than_box_auto_wrapped_by_libass` i `auto_wrap_simulated_*` w `shisha-practice.json` są niewiarygodne. Nie należy ich używać.

### 3.1 Dialog

| Miara | PL 01 | PL 02 | EN 01 | EN 02 |
|---|---:|---:|---:|---:|
| Zdarzenia dialogowe | 466 | 378 | 423 | 358 |
| Zdarzenia z ręcznym `\N` | 41 (8,8%) | 23 (6,1%) | 157 (37,1%) | 149 (41,6%) |
| Wiersze > 42 znaki | 111 (23,8%) | 96 (25,4%) | 0 | — |
| Wiersze > 47 znaków | 63 | 69 | 0 | — |
| Najdłuższy wiersz (znaki) | 68 | 55 | 42 | — |
| CPS, mediana / p90 | 11,4 / 16,1 | 11,6 / 16,7 | 12,9 / 19,2 | — |
| Zdarzenia z CPS > 17 | 33 (7,1%) | 31 (8,2%) | 93 (22,0%) | — |

CPS liczę jako wszystkie znaki ze spacjami podzielone przez czas trwania. Kreska oznacza wartość nieodczytaną w tej sesji (jest w JSON).

- **Ramka:** styl `Toaru` to Fontin Sans 72 pt bold na 1080p z marginesami 160 px, czyli 1600 px szerokości. Render libass: wiersze 57- i 55-znakowe mieszczą się w jednym wierszu, a zawijają się dopiero 68- i 64-znakowe (dwa przypadki w odcinku 01). libass dzieli je na „Dlatego w rankingu wyprzedza cię / inna esperka władająca elektronami.” i „torturują je fizycznie i psychicznie, / by rozwinąć ich zdolności.”
- **Rodzaj ręcznego łamania** (64 zdarzenia z obu odcinków): po interpunkcji 36 (56%), przed spójnikiem 5, przed przyimkiem 4, **po przyimku lub jednoliterowym słowie 0**, inne 19. Wśród „innych” są cięcia wewnątrz frazy: „Wiem, jak cię cieszy zdobycie / rzadkiego gadżetu z ulubioną postacią.”, „Ujawnienie tych badań mocno podważy / zaufanie do Miasta Akademickiego.”
- **Kształt:** górny wiersz krótszy w 36 z 64 łamań (56%). Shisha nie trzyma się piramidy.
- **Dzielenie zdań między zdarzenia:** 24 i 31 zdarzeń kończy się przecinkiem lub myślnikiem. Żadne zdarzenie nie kończy się przyimkiem ani jednoliterowym słowem.
- Wniosek: Shisha ogranicza wiersz szerokością ramki, nie liczbą znaków. Długą kwestię zostawia w jednym wierszu, a ręcznie łamie głównie po interpunkcji.

### 3.2 Szyldy

Próba: obiekty tekstowe stylu `Znaki`, bez rysunków `\p`, fontów-faktur (Grain), dingbatów i symboli. Każdy tekst liczę raz na krój i zaokrągloną skalę, więc 35 klatek trackingu daje jeden obiekt. Wynik: 26 obiektów w 01 i 19 w 02.

| Miara | PL 01 | PL 02 |
|---|---:|---:|
| Zmiana `\fs` | 0 | 0 |
| Zmiana `\fsp` | 0 | 0 |
| `\fscx/\fscy`: mediana (min–max) | 0,879 (0,46–1,202) | 0,968 (0,771–1,352) |
| Ściśnięte w poziomie (< 0,95) | 14 | 7 |
| Proporcjonalne (0,95–1,05) | 10 | 9 |
| Rozciągnięte (> 1,05) | 2 | 3 |
| Obiekty wielowierszowe | 5 | 4 |
| Najmniejsza wysokość pisma (rozmiar ASS × `\fscy`) | 33,5 px | 23,7 px |

- Wielkość powstaje wyłącznie z `\fscx`/`\fscy` przy bazowym rozmiarze 50, bez `\fs` i `\fsp`.
- Większość anizotropii odwzorowuje proporcje japońskich liter i perspektywę, a nie dopasowanie do ramki. Przykłady: plakat 124/270 (0,46), tablica szkoły 86/175 (0,495), wizytówka 65/138. Ściśnięcie wyraźnie służące zmieszczeniu tekstu widać w pasku TV: „Rozwój nowych zdolności w Mieście Akademickim”, `\fscx79\fscy100`, jeden wiersz w miejsce trzech angielskich. Podobnie „Wydanie specjalne”: 64/83. To dwa punkty danych, nie pomiar percepcji.
- **Dzielenie na wiersze:** „ONE MONTH PRIOR - 6/30” → „Miesiąc wcześniej\N30 czerwca”, „#2 SAIAI KINUHATA - NEWCOMER” → „#2 Nowa członkini\NKinuhata”. W obu przypadkach z jednego wiersza robią się dwa. Wielowierszowe angielskie szyldy (tablica szkoły, plakat, TV) stają się osobnymi obiektami.
- **Skracanie po sensie:** „CARD DECLINED” → „Odmowa”.
- **Najmniejszy tekst** to 23,7 px na telefonie („Głośnomówiący”, „Dom rodzinny”). `shisha-report.md` ocenia go jako mniej czytelny kompromis.
- **Porównanie z EN jest niemiarodajne.** Angielskie szyldy tego wydania to nietypesetowany tekst u góry (Arial 22 przy 360p, czyli 66 px przy 1080p). Stosunek wysokości PL/EN w parach czasowych waha się od 0,36 do 3,88. Na tym korpusie nie da się sprawdzić reguły „polski szyld nie większy od angielskiego”.

## 4. Lektor

- Zasad, co czyta polski lektor (szyldy, tytuły, piosenki, okrzyki), w dostępnych źródłach **nie znalazłem**. Wyszukiwanie dało tylko ogólne prace o przekładzie lektorskim. Pełnego tekstu z ejournals.eu nie udało się pobrać (timeout).
- Pokrewne zasady napisów (nie lektora): Netflix usuwa szyld powtórzony w dialogu i zakazuje łączenia szyldu z dialogiem w jednym napisie (§9), a piosenki tłumaczy tylko wtedy, gdy są istotne dla fabuły i są prawa (§18). Aegisub odradza typesetting szyldu czytanego na głos.

## 5. Co z tego wynika dla AniShift

„Twarde” oznacza zgodność źródeł lub kryterium bez sensownego wyjątku. „Miękkie” oznacza preferencję, którą się waży. Waga jest moją oceną na podstawie zgodności źródeł i praktyki Shishy.

### Dialog

| Cecha | Rodzaj | Waga | Podstawa |
|---|---|---|---|
| Wyraz nie jest rozcięty | twarde | — | BBC §3.4, Netflix |
| Najwyżej 2 wiersze | twarde (trzeci tylko jako raportowany wyjątek, do decyzji właściciela) | — | Netflix §12, BBC, Karamitroglou, Aegisub |
| Łamanie po interpunkcji, przed spójnikiem lub przyimkiem | miękkie | wysoka | Netflix §4, BBC §3.4; Shisha: 56% po interpunkcji |
| Bez rozdzielania rzeczownika i przymiotnika, imienia i nazwiska, czasownika i „się”/„nie”/posiłkowego | miękkie | wysoka | Netflix §4, BBC §3.4 |
| Bez jednoliterowego słowa i przyimka na końcu wiersza | miękkie, bliskie twardego | wysoka | wynika z Netflix §4; PWN 54.8.1 i Wolański; Shisha 0/64 |
| Szerokość mieści się w ramce | twarde przy ramce, miękkie przy liczbie znaków | wysoka | BBC §3.1 (szerokość, nie znaki); Shisha do 57 znaków |
| Jeden wiersz, gdy się mieści | miękkie | średnia | Netflix §12; przeczy mu Karamitroglou |
| Długość wiersza w znakach | miękkie | niska | Netflix 42, BBC 37, Karamitroglou 35; Shisha: 24–25% wierszy > 42 |
| Piramida, bez 1–2 słów w górnym wierszu | miękkie | niska (1–2 słowa u góry: średnia) | Netflix PL §12; BBC: geometria po języku; Shisha 56% |
| CPS ≤ 17 | miękkie | niska dla właściciela (dialog słyszy od lektora) | Netflix PL §16; Shisha p90 ok. 16–17 |
| Dialog u góry przy kolizji z napisem ekranowym, bez skakania | miękkie | średnia | Netflix §5/§21 |

### Szyld

| Cecha | Rodzaj | Waga | Podstawa |
|---|---|---|---|
| Czytelny w czasie wyświetlania | miękkie, ale nadrzędne nad wiernością położenia i orientacji | najwyższa | Aegisub, unanimated |
| Brak zniekształcenia przez skalę | miękkie | wysoka | unanimated (`\fscx` ≠ wąski krój); Shisha ściska do 0,77–0,79 przy dopasowaniu; **brak źródła progu** |
| Podział na 2 wiersze zamiast mocnego zmniejszenia | miękkie | średnia | unanimated („if the words allow it”); Shisha: 2 przypadki 1 → 2 wiersze |
| W szyldzie wielowierszowym bez jednoliterowego słowa na końcu wiersza | miękkie, bliskie twardego | wysoka | PWN 54.8.1 (tytuły), mój wniosek |
| Bez `\fsp` jako środka dopasowania | wniosek z praktyki | — | Shisha 0/45 obiektów; unanimated wspomina `\fsp` tylko jako „might help a bit” |
| Krótsze tłumaczenie, gdy nie da się czytelnie zmieścić | środek z praktyki | — | Shisha („Odmowa”); wymaga decyzji o limicie (pytanie 3 z 18.10) |

### Gdzie źródła się nie zgadzają

1. **Jeden wiersz czy dwa.** Netflix: jeden, dopóki tekst się mieści. Karamitroglou: długi pojedynczy wiersz lepiej podzielić na dwa. Shisha robi jak Netflix, ale mierzy szerokością.
2. **Kształt.** Netflix PL zaleca piramidę z krótszym wierszem na górze. BBC daje pierwszeństwo kryterium językowemu i woli napisy „long and thin”. Shisha nie trzyma się żadnego kształtu (56%).
3. **Limit długości.** 42 (Netflix PL), 37 (BBC), ok. 35 (Karamitroglou). Wszystkie to liczby znaków dla napisów telewizyjnych. Shisha na 1080p dopuszcza do ok. 57 znaków w jednym wierszu.
4. **Sierotki.** PWN dopuszcza je w tekście ciągłym i zakazuje w tytułach. Wolański łączy zakaz z wierszami powyżej 40 znaków i z justowaniem. O napisach żadne źródło nie mówi.
5. **Czytelność a wierność.** Aegisub i unanimated stawiają czytelność ponad wierność położenia i wielkości. Szkic `visual-quality.md` stawia angielski oryginał jako wzorzec i zakazuje polskiego szyldu większego od angielskiego. Źródła nie znają takiego zakazu: dla nich wzorcem jest obraz, nie angielski typesetting.

### Wpływ na szkic `visual-quality.md`

- „Profesjonaliści (Shisha) łamią po sensie, nie po kształcie” (§3.5): potwierdzają to pomiary z §3.1 tego dokumentu.
- „42 znaki to zalecenie, nie granica” (§3.4): potwierdza Shisha (24–25% wierszy powyżej 42) i BBC §3.1 (szerokość ważniejsza od liczby znaków).
- „Lekkie ściśnięcie w poziomie jest niewidoczne” (§2.2) i „80% mało widoczne” (§6): **brak źródła**. Shisha w dwóch przypadkach dopasowania użyła 77–79%. To praktyka, nie dowód niewidoczności.
- Minimalna czytelna wielkość (§10.2): **brak źródła**. Najmniejszy tekst Shishy (23,7 px wysokości ASS) jej własny raport ocenia jako mniej czytelny.
- Jednoliterowe słowo na końcu wiersza nie występuje w szkicu wprost. Źródła i Shisha (0/64) uzasadniają je jako cechę o wysokiej wadze dla dialogu i szyldu.

## 6. Niewiadome

- Dosłowna treść stron Netflix i Aegisub (cytaty przez narzędzie streszczające).
- Granica ściśnięcia `\fscx` i minimalna czytelna wielkość: tylko pomiar na galerii z oceną właściciela.
- Zasady polskiego lektora: brak źródła.
- Czy wnioski z jednej grupy (Shisha, dwa odcinki) uogólniają się na polskie fansuby.
- Badanie z widzami dotyczyło angielskich napisów, nie polskich.

## Źródła

- Netflix, Polish Timed Text Style Guide: <https://partnerhelp.netflixstudios.com/hc/en-us/articles/216787928-Polish-Timed-Text-Style-Guide> (dostęp 2026-10-18).
- Netflix, Timed Text Style Guide: General Requirements: <https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617-Timed-Text-Style-Guide-General-Requirements> (dostęp 2026-10-18).
- BBC Subtitle Guidelines v1.2.5: <https://www.bbc.co.uk/accessibility/forproducts/guides/subtitles/> (dostęp 2026-10-18).
- Karamitroglou F., A Proposed Set of Subtitling Standards in Europe, Translation Journal 2(2), 1998: <https://translationjournal.net/journal/04stndrd.htm>.
- Gerber-Morón O., Szarkowska A., Line breaks in subtitling, JEMR 11(3):2, 2018: <https://ddd.uab.cat/pub/artpub/2018/238546/joueyemov_a2018v11n3p2.pdf>.
- PWN, zasady pisowni [204] 54.8: <https://sjp.pwn.pl/zasady/;629563.html> (strona zwracała 500, tekst z Internet Archive).
- PWN Poradnia, A. Wolański, „sieroty na końcu wiersza”, 2008: <https://sjp.pwn.pl/poradnia/haslo/sieroty-na-koncu-wiersza;8893.html> (tekst z Internet Archive).
- Aegisub, Typesetting Introduction: <https://aegisub.org/docs/latest/typesetting/>.
- unanimated, Typesetting in Aegisub: <https://unanimated.github.io/ts/>.
- Korpus: `workspace/.quality/corpus-pairs/certain-dark-item-0{1,2}/`, `workspace/.quality/shisha-report.md`.

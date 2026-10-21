# Łamanie polskich napisów dialogowych — research od podstaw (opus55)

Zlecenie: `LB-research-v2`. Tryb: research, bez kodu produkcyjnego. Stan na 19.10.2026.
Eksperymenty i dane: `C:\Users\MattyMroz\Desktop\PROJECTS\AniShift\workspace\.quality\experiments\lb-research\opus55\` (dalej `EXP\`).
Środowiska tymczasowe: `C:\Users\MATTYM~1\AppData\Local\Temp\lb-research\opus55\.venv` (lekkie narzędzia, dalej `TMPVENV`) oraz `.venv-torch` (Stanza i PyTorch). Skrypty importujące `anishift` uruchamiałem interpreterem worktree'u `AniShift-wt\fuzzy\.venv` (dalej `WTVENV`).

Oznaczenia: **[F]** fakt sprawdzony (pomiar albo przeczytane źródło), **[W]** wniosek z faktów, **[H]** hipoteza, **[D]** decyzja dla właściciela.

---

## 1. Streszczenie dla właściciela

1. Najlepsze rozwiązanie to jedna prosta reguła wyboru. Program rozważa każdy możliwy układ: jeden wiersz, każde cięcie na dwa i wyjątkowo trzy wiersze. Każdemu układowi liczy jedną „cenę”: za długość najdłuższego wiersza, za to, jak źle wypada miejsce cięcia, za nierówne wiersze i za samotne słowo. Wybiera układ najtańszy.
2. Takie rozwiązanie ma prawie każdy element starego algorytmu z gałęzi `08` (u6-font, ten, który „działa”). Zmienia się jedno: decyzję podejmuje jedna wspólna cena, a nie kaskada list i wyjątków. Nie proponuję uporządkowanej wersji 16, tylko zastąpienie rdzenia 08 jedną funkcją kosztu. Z 08 zostają listy słów (jako awaryjne źródło informacji), obsługa myślników mówców i znaczników `<sN>`.
3. Na Twoich 66 przykładach (38 przypadków A–D, 20 decyzji z galerii i 8 znanych złych cięć) prototyp trafia 54 na 66 przy uczciwym sprawdzeniu, czyli strojeniu bez sprawdzanego przykładu. Stary algorytm 08 w ustawieniach produkcyjnych (42 znaki, najwyżej 2 wiersze) trafia 44 na 66. Na 593 profesjonalnych kwestiach Netflixa i Amazona prototyp tnie dokładnie tam, gdzie tłumacz, w 81% przypadków.
4. 42 znaki to norma produkcyjna (Netflix PL), nie wynik badań. Żadne przeczytane badanie nie wyznacza 42 jako optimum. Polska fundacja dostępności podaje 40, BBC 37 (to limit teletekstu), Karamitroglou około 35.
5. Twoja intuicja, że zwarty blok czyta się szybciej, nie ma ani potwierdzenia, ani obalenia w kontrolowanych badaniach. Testu „ten sam tekst w jednym długim wierszu kontra w dwóch krótkich” w przeczytanych pracach po prostu nie ma. Dlatego długość jest u mnie wartością rozmytą liczoną od szerokości ekranu: cena zaczyna rosnąć przy około 60% szerokości (≈ 37 znaków typowym fontem), a przy pełnej szerokości osiąga maksimum.
6. 42 zostaje „złotym środkiem”: przy typowej szerokości 42 znaki kosztują około 0,2 z 1. Długi jeden wiersz wygrywa, gdy jedyne możliwe cięcia są złe, np. w Twoim przypadku 13 i 04.
7. Trzy wiersze: badanie Szarkowskiej i Gerber-Morón pokazało dłuższe czytanie i większy deklarowany wysiłek przy trzech wierszach, bez spadku rozumienia. W regule trzy wiersze mają stałą dopłatę i wygrywają tylko wtedy, gdy dwa się nie mieszczą albo oba możliwe cięcia na dwa wiersze są wyraźnie złe.
8. Kształt (piramida czy równe wiersze) nie jest stałą regułą. Badania pokazują, że ludzie wybierają według sensu, nie kształtu. W profesjonalnym korpusie górny wiersz bywa krótszy i dłuższy prawie tak samo często (846 do 805). Krótki górny wiersz jest jednak rzadziej akceptowany niż krótki dolny, więc kara za nierówność trochę mocniej dotyka „wysokiej czapki”.
9. Sens cięcia jest ważniejszy niż wyrównanie wierszy. To zgodne z badaniami, z Twoimi wyborami i z profesjonalistami: cięcie po kropce wygrywa z cięciem w środku zdania do nierównowagi około 50%, a cięcie po przecinku jest prawie tak dobre.
10. Tłumacz (LLM) nie powinien stawiać `\N`. Modele językowe słabo liczą znaki, a w ogóle nie znają szerokości fontu. Każda zmiana promptu oznacza płatne ponowne tłumaczenie, a mamy też DeepL i Google, które tego nie zrobią. Podział zostaje w kodzie, deterministyczny, z pomiarem fontu.
11. Analizator gramatyki: zmierzyłem sześć narzędzi na naszych danych. Lekki model `spaCy pl_core_news_sm` (26 MB, 0,3 s ładowania, 0,5 s na 500 kwestii, bez PyTorcha) daje +4 punkty nad samymi listami słów na Netflixie i Amazonie. Stanza z PyTorchem daje +6, ale kosztuje około 1 GB instalacji i 2,6 GB RAM. Różnica 2 punktów mieści się w niepewności pomiaru, więc PyTorch odpada.
12. Haczyk licencyjny: polskie modele spaCy są na licencji GPL-3.0, a modele UDPipe na CC BY-NC-SA (niekomercyjna). Repo nie ma pliku LICENSE. To Twoja decyzja (sekcja 5).
13. Ułożenie odcinka (500 kwestii) z analizą gramatyki i pomiarem fontu to szacunkowo 2–3 sekundy, nie minuty.
14. Prototyp wciąż myli się w 8 przypadkach. Są wśród nich „woli / Artemis” (parser bierze „Artemis” za podmiot) i Twój przypadek 07: wolisz tam trzy wiersze przy wtrąceniu, choć dwa się mieszczą. Opisuję je w sekcji 5 jako decyzje, nie zamiatam pod dywan.

---

## 2. Tezy i ich weryfikacja

| # | Teza | Dowód za | Dowód przeciw | Werdykt |
|---|---|---|---|---|
| T1 | 42 znaki to naukowo uzasadnione optimum | Netflix PL §3 „42 characters per line”; Karakanta 2020 używa 42 jako kryterium | Karakanta §3.3: wartości „chosen according to the TED subtitling guidelines”; FKBB: 40, BBC: 37 (techniczne, teletekst), Karamitroglou: ~35; brak eksperymentu wyznaczającego 42 | **Obalona jako „optimum”**; 42 to norma zgodności [F] |
| T2 | Profesjonaliści traktują 42 jako twardy limit | 7083 zdarzeń z NF/AMZN/CR: żaden jednowierszowy napis > 42 zn., p99 = 41; łącznie 1 wiersz 45 zn. na 3609 wierszy dwuwierszowych [F] | — | **Potwierdzona dla korpusu** [F], ale to cecha normy dostawcy, nie czytelności |
| T3 | Jeden długi wiersz czyta się wolniej niż dwa krótsze | Karamitroglou §5 (twierdzenie bez danych); zalecenia BBC/ESIST | Netflix PL §12 każe trzymać jeden wiersz do limitu; Shaikh 2005: 95 CPL czytane najszybciej (ciągły tekst); Bernard 2002: brak różnic czasu | **Nierozstrzygnięta** — brak kontrolowanego testu w przeczytanej literaturze [F] |
| T4 | Cięcie niezgodne ze składnią szkodzi | Gerber-Morón i Szarkowska 2018: preferencja cięcia składniowego we wszystkich 10 kategoriach (ηp² do .63); Gerber-Morón i in. 2018: więcej powrotów do napisu (.37 vs .25) i wyższy deklarowany wysiłek | Rozumienie bez różnic (p = .52/.40); czas czytania i liczba fiksacji bez różnic | **Potwierdzona dla komfortu i preferencji; nie dla rozumienia** [F] |
| T5 | Piramida (dolny dłuższy) jest lepsza | Netflix PL §12 „bottom-heavy pyramid”; ESIST: górny krótszy | Karamitroglou: równe; JEMR 2018: wybór według sensu, nie kształtu; korpus: górny krótszy 846 vs dłuższy 805 | **Obalona jako stała reguła** [F]; słaba preferencja przeciw bardzo krótkiemu górnemu wierszowi [F, korpus] |
| T6 | Trzy wiersze szkodzą | Szarkowska i Gerber-Morón 2018: dłuższy czas absolutny i proporcjonalny, większy wysiłek, osoby niesłyszące jednogłośnie za dwoma | Rozumienie bez różnic (p = .28/.38); zmienione też grupowanie zdarzeń | **Częściowo** — koszt wysiłku tak, szkoda dla rozumienia nie wykazana [F] |
| T7 | Analizator składni poprawia cięcie względem list słów | NF+AMZN, n = 593: lex 73,4%; spaCy sm +4,0 pp [95% CI +1,3; +6,9]; UDPipe +4,2 [+1,5; +7,1]; Stanza +6,1 [+2,9; +8,9] [F] | CR, n = 1075: żaden parser nie bije list (część ludzkich cięć CR jest po przyimkach) [F] | **Potwierdzona na czystych źródłach**; mały efekt |
| T8 | PyTorch (Stanza) jest wyraźnie lepszy od lekkich | +2,1 pp nad spaCy sm na NF+AMZN [F] | Przedziały ufności się pokrywają; koszt ≈ 1 GB instalacji, 2,6 GB RAM, 6 s ładowania [F] | **Obalona** — przewaga w granicach błędu |
| T9 | Stary algorytm 08 „działa” i jest dobrą bazą | Na korpusie tnie złymi klasami rzadziej niż ludzie (po przyimku 0,1% vs 1,7%) [F]; galeria: właściciel woli u6 | Twój złoty zbiór: 44/66 przy produkcyjnych 2 wierszach [F] (38/66 przy dopuszczeniu 3 wierszy: wtedy nadmiar trzech wierszy w c02, c03, c19, c36, c39); łamanie jednowierszowych mieszczących się w ekranie (c04, c11, c13, c14, c15, c24); brak trzech wierszy, gdy są konieczne (c26, c27, c33); brak wiedzy o frazach („naszą wspólną / przyszłość”, „się / zakocha”) | **Dobra baza dla zasad i list, zła dla decyzji o liczbie wierszy** |
| T10 | Tłumacz (LLM) powinien stawiać `\N` | Matusov 2019: hybryda model + ograniczenia; MuST-Cinema `<eol>`/`<eob>` (relacja wtórna) | PositionID (Wang i in. 2024): LLM słabo kontrolują długość; brak znajomości szerokości fontu; DeepL/Google tego nie zrobią; koszt i niedeterminizm | **Obalona dla AniShift** [W] |
| T11 | Jedna reguła może wyjaśnić wybory właściciela i profesjonalistów | Prototyp v2: 54/66 LOO na zbiorze właściciela przy 81,1% na NF+AMZN [F] | 8 błędów, w tym 1 sprzeczność wewnątrz zbioru (c07 kontra „trzy, gdy mieszczą się dwa”) | **Potwierdzona w przybliżeniu** [F] |

---

## 3. Pytania badawcze P1–P6

### P1. Czytelność — badania, nie wytyczne

Szczegółowy przegląd z cytatami: `EXP\lit-p1-readability.md` (wykonawca: astra; sprawdziłem lokalizatory dla tez T1–T6). Najważniejsze ustalenia:

**42 i inne liczby.** [F]
- Netflix PL §3: „42 characters per line”. To wymóg dostawcy, bez opisu badania.
- BBC §3.1: 37 wynika z teletekstu („at least 3 of the 40 available bytes are used for control codes”). BBC zaznacza też, że przy fontach proporcjonalnych „impossible to determine the width of the line based on the number of characters alone”.
- Karamitroglou 1998 §2: „around 35 characters”, z uzasadnieniem pomniejszania fontu.
- FKBB 2019 s. 2: „do 40 znaków, bo maksymalnie tyle można sprawnie przeczytać”, uzasadnione doświadczeniem redakcyjnym, nie eksperymentem.
- Karakanta i in. 2020 §3.3: 42 CPL i 21 CPS „chosen according to the TED subtitling guidelines”. To benchmark generowania napisów, nie badanie widzów.
- Źródła progu 39 nie odnaleziono.

**Długość wiersza a ruch oka.** [F]
- Literatura typograficzna dotyczy ciągłego tekstu. Dyson i Kipping 1998: różnice znikały po odjęciu przewijania. Bernard 2002: brak różnic czasu przy 45/76/132 CPL. Shaikh 2005: 95 CPL najszybciej, a odczucie „szybciej przy 35” było mylne.
- Rayner 1998 s. 380: pole percepcyjne jest małe („no more than 3–4 letters to the left of fixation”). Tezy „oko obejmuje cały wiersz jednym spojrzeniem” nie da się z tego wyprowadzić.
- Slattery i Vasilev 2019: przejście na kolejny wiersz (return sweep) wnosi błąd ruchowy, ale jego zmniejszenie nie przyspieszało czytania.
- [W] Twoja hipoteza o „zamiataniu wzrokiem” jest wiarygodna mechanistycznie: długi wiersz to dłuższe sakady poziome. Drugi wiersz wnosi jednak return sweep. Bilansu nikt dla napisów nie zmierzył.

**Cięcie składniowe.** [F] Gerber-Morón i Szarkowska 2018 (JEMR 11(3)), Gerber-Morón, Szarkowska i Woll 2018 (JEMR 11(4)):
- Preferencja cięcia składniowego jest silna. Dla polskich uczestników wynosiła 64–95% w zależności od kategorii; najmocniejsza „zdanie | zdanie” (95%).
- Cięcie niezgodne ze składnią podniosło deklarowaną trudność, wysiłek i frustrację oraz liczbę powrotów do napisu (.37 vs .25, p = .001, tylko eksperyment 1).
- Nie zmieniło rozumienia, czasu czytania ani liczby fiksacji.
- Perego 2010, według relacji wtórnej: średnia fiksacja dłuższa o 12 ms, bez spadku rozumienia.
- Uwaga: w tych badaniach Polacy czytali napisy angielskie.

**Kształt.** [F] JEMR 2018: „the overwhelming majority of participants made their choices based on semantic and syntactic units rather than subtitle shape”. Zalecenia są sprzeczne: Netflix chce piramidy dolnej, ESIST krótszego górnego wiersza, Karamitroglou równych wierszy, a w konflikcie „sacrifice geometry”.

**Trzy wiersze.** [F] Szarkowska i Gerber-Morón 2018 („Two or three lines”):
- Przy trzech wierszach dłuższy czas proporcjonalny (np. polscy uczestnicy 42 → 45%) i większy wysiłek.
- Rozumienie bez różnic (89,5% vs 87,0%, p = .28).
- Osoby niesłyszące jednogłośnie wybrały dwa wiersze.
- BBC i DCMP dopuszczają 3 wiersze wyjątkowo; KRRiT 2016 §5 „w wyjątkowych sytuacjach – w trzech linijkach”.

**Zasłanianie obrazu.** [F] BBC §3.6: „‘long and thin’ subtitles are less disruptive of picture content than are ‘short and fat’ subtitles, but this is not always the case”. Netflix PL §12: „Text should usually be kept to one line, unless it exceeds the character limitation”. Dla AniShift nie znalazłem badania kosztu zasłaniania wyrażonego liczbą. [W] Uzasadnia to jednak, że jeden wiersz nie jest porażką: wygrywa, gdy drugi wiersz niczego nie daje (brak dobrego cięcia).

**Luki** (jawnie niedostępne): Perego 2010, Rajendran 2013, Dyson i Haselgrove 2001 (tylko abstrakt), Szarkowska i Bogucka, Gerber-Morón i in. 2020 (rozmiar ekranu, PDF 403), książki Díaz Cintas/Remael i Ivarsson/Carroll, dokument STAW, zasady redakcyjne TVP.

### P2. Gdzie ciąć — zasady układania polskiego dialogu

Najpierw zasady, potem mechanika. Zasady pochodzą z FKBB 2019 pkt 4, Netflix General §4 („The line break should not separate … a verb from an auxiliary, reflexive pronoun or negation”), ESIST (jednostki sensu) oraz z pomiaru: jak często profesjonaliści tną w danej klasie granicy względem liczby okazji (`EXP\fuzzyproto-pl_core_news_sm.json`).

**Hierarchia granic** (od najlepszej). W nawiasie akceptowalność A z korpusu NF+AMZN, gdzie 1 oznacza najlepsze, 0 nigdy:

1. koniec zdania (1,00);
2. przecinek, średnik, dwukropek (0,94); wielokropek (0,74, z całego korpusu);
3. granica podmiot | orzeczenie (0,51); inne granice bez interpunkcji między dużymi częściami zdania (0,50);
4. rzeczownik | dopełniacz (0,40); nazwa własna lub wyrażenie wielowyrazowe (0,39); myślnik (0,34, ale patrz katalog: wtrącenia);
5. czasownik | dopełnienie tuż obok (0,26); posiłkowy | główny (0,24); przymiotnik | rzeczownik (0,16);
6. po słowie jednoliterowym (0,12); rozcięta fraza dwuwyrazowa (0,12);
7. **nigdy w korpusie NF+AMZN** (0,00): spójnik na końcu wiersza, po przyimku, oderwane „nie”, oderwane „się”.

**Co zawsze razem** (zasady „unikane za wszelką cenę”):
- przyimek z tym, co rządzi (np. „z balastem”);
- „nie” z czasownikiem;
- „się” z czasownikiem, któremu towarzyszy (również przy szyku swobodnym: „się / zakocha” jest złe);
- jednoliterowe w, z, o, u, i, a z następnym słowem;
- spójnik z tym, co wprowadza (cięcie przed spójnikiem, nie po nim);
- imię z nazwiskiem i z honoryfikatorem;
- liczba z jednostką lub rzeczownikiem („1,4 miliarda”, „25 kg”);
- skrót z tym, co określa („ul. Długiej”, „godz. 17.30”);
- frazeologizm („raz na zawsze”, „po prostu”, „w ogóle”).

**Kiedy łamać zdanie.** Gdy cała kwestia nie mieści się w jednym wierszu bez wyraźnej ceny długości, a granica między zdaniami albo po przecinku daje rażąco nierówny układ. Pomiar (`asymmetry.py`, korpus, jedyna dostępna granica danego typu) pokazuje, jak często profesjonaliści biorą takie cięcie zależnie od nierównowagi:

| Granica | Nierównowaga 0–0,5 | 0,5–0,6 | 0,6–0,7 | > 0,7 |
|---|---|---|---|---|
| koniec zdania | 89–100% | 38% | 10% | 0% |
| przecinek | 94%, 81%, 71%, 47%, 28% (kubełki 0,1 do 0,5) | 14% | 0% | — |

Nierównowaga to |L − P| / (L + P).

Przy dużej nierównowadze (≥ 0,4) liczy się też, który wiersz jest długi:

| Układ | koniec zdania | przecinek |
|---|---|---|
| górny dłuższy | 75% | 26% |
| górny krótszy | 42% | 9% |

[F] Krótki górny wiersz jest więc mniej akceptowany niż krótki dolny.

**Co da się wykryć i czym** [F, pomiar P3]:
- (a) Sama morfologia (Morfeusz 2) wykrywa przyimki, zgodę przymiotnika z rzeczownikiem i „się”. Daje +3,2 pp nad listami na NF+AMZN [CI +0,8; +5,7]. Nie widzi drzewa, więc nie wie, czy „Artemis” należy do „woli”.
- (b) Parser zależnościowy daje rozpiętość wspólnego poddrzewa, łuki przecinające granicę i typy relacji (amod, nmod, obj, flat, expl:pv dla „się”). To najlepsze ogólne źródło: +4 do +6 pp.
- (c) Chunker płytki: dla polskiego nie znalazłem utrzymywanego narzędzia z kołami cp314 (nie badałem dalej).
- (d) Reguły na tokenach to obecne listy 08. Przyzwoite (69,5% na całym korpusie), ale ślepe na frazy spoza list („naszą wspólną / przyszłość”, „wpływ / psychiczny”).

**Miara „nie rozcinaj małego poddrzewa”.** [F] W prototypie jest to dodatek wj · (1 − s/n), gdzie s to rozmiar najmniejszego poddrzewa zawierającego oba słowa przy granicy, a n liczba słów. Dopasowane wj = 0,6 jest największą wartością w siatce. Ta ogólna, nieręczna miara poprawiła zgodność z Twoim zbiorem, np. g04 („skrzywdziłam / tylu innych…” jest dobre, bo łączy je dopiero całe zdanie). Liczba przeciętych łuków bez uwzględnienia rozpiętości okazała się w logicie słabszym sygnałem niż klasa relacji (`EXP\eval-*-dep.json`, wagi `func_dangling`, `sub_2`, `sub_3`).

### P3. Narzędzia dla polskiego — przegląd i pomiar

**Dostępność i koszt** [F] (Python 3.14.7, Windows, `uv pip install --dry-run` i instalacja w `TMPVENV`; rozmiary z dysku):

| Narzędzie | Koło cp314 win_amd64 | Instalacja / model | RAM szczyt | Ładowanie | 500 kwestii | Licencja modelu | Jakość (UD PDB, z meta lub publikacji) |
|---|---|---|---|---|---|---|---|
| listy 08 (`lex`) | — | 0 | — | 0 | ~0 | repo | — |
| Morfeusz 2 1.99.15 | tak | słownik SGJP 2026.06.01 | 78 MB | 0,05 s | 0,09 s | nie sprawdziłem w tym badaniu | tylko analiza, bez dezambiguacji |
| UDPipe 1 (`ufal.udpipe` 1.4.0.1) | tak | model 25,5 MB | 184 MB | 1,41 s | 1,45 s | **CC BY-NC-SA** (strona UDPipe 1 Models) | brak liczby dla PL w odczytanym fragmencie |
| spaCy 3.8.16 `pl_core_news_sm` | tak | 26 MB | 195 MB | 0,28 s | 0,55 s | **GPL-3.0** (meta modelu) | UPOS 0,969, UAS 0,873, LAS 0,793 |
| `pl_core_news_md` | tak | 62 MB | 358 MB | 0,62 s | 0,58 s | GPL-3.0 | 0,977 / 0,891 / 0,817 |
| `pl_core_news_lg` | tak | 612 MB | 907 MB | 1,45 s | 0,56 s | GPL-3.0 | 0,978 / 0,896 / 0,825 |
| Stanza 1.15.0 + torch 2.14.1 | tak | 616 MB venv + 345 MB modeli | 2631 MB | 6,1 s | 6,42 s | kod Apache-2.0; licencji modelu PL nie sprawdziłem | — |
| Trankit 0.3.5, onnxruntime 1.31.0 | koła są (dry-run) | — | — | — | — | — | nie mierzyłem; Trankit wymaga PyTorcha |

Komendy:
- pomiar parsowania: `TMPVENV\Scripts\python.exe EXP\parse.py <narzędzie>`, wyniki w `EXP\parses-*.json`; liczby czasu i RAM z ostatniej linii wyjścia;
- spaCy przeparsowane ponownie z dodatkowymi tekstami: 5893 teksty, 0,29 s ładowania, 0,51 s na 500.

HerBERT i polish-roberta to enkodery bez głowic parsowania. Wymagałyby treningu i ONNX-u; nie badałem, bo nie było podstaw sądzić, że pobiją parser UD przy tym koszcie. UDPipe 2, COMBO, KRNNT, Concraft i Toygger pominąłem z powodu wymagań PyTorch/TF albo serwisu; nie mierzyłem.

**Jakość na naszych danych** [F]:
- Korpus: 22 polskie napisy profesjonalne z MKV w `workspace` (NF 5, AMZN 6, CR 11), `EXP\corpus.py`, `EXP\pl-subs\`.
- Zestaw oceny: 1668 dwuwierszowych kwestii, w których ludzkie cięcie jest kandydatem z oboma wierszami ≤ 42; trafienie losowe 23,5%.
- Ten sam algorytm dla każdego narzędzia: logit warunkowy po kandydatach, walidacja krzyżowa z pominięciem całej serii. Komenda: `WTVENV python EXP\evaluate.py <narzędzie> <tryb>`; istotność: `EXP\significance.py` (bootstrap).

| Źródło informacji | top-1, cały korpus (CV) | NF+AMZN (n = 593), różnica do `lex` [95% CI] | CR (n = 1075) |
|---|---|---|---|
| sama interpunkcja + równowaga | 65,5% | — | — |
| listy 08 (`lex`) | 69,5% | 73,4% (baza) | baza |
| Morfeusz | 69,2% | +3,2 [+0,8; +5,7] | gorzej lub równo |
| UDPipe | 69,8% | +4,2 [+1,5; +7,1] | gorzej lub równo |
| spaCy sm | 70,7% | +4,0 [+1,3; +6,9] | gorzej lub równo |
| spaCy md | 70,1% | +3,5 | — |
| spaCy lg | 70,1% | +4,0 | — |
| Stanza | 70,8% | +6,1 [+2,9; +8,9] | gorzej lub równo |
| Stanza + listy | 71,0% | — | — |

[W] CR jest zaszumiony: ludzie tną tam po przyimkach („ważniejsze od / ochrony”, „cierpią przez / wysokie podatki”), więc model uczony na CR uczy się złych cięć. Dlatego tabelę akceptowalności A biorę z NF+AMZN. Nauczona tam daje 81,6% na NF+AMZN i 63,8% na CR; nauczona na CR daje 68,5% na NF+AMZN (`EXP\fuzzyproto.py`).

**Klasy złych cięć** (`WTVENV python EXP\classes.py stanza`, % kwestii, parser referencyjny Stanza) [F]:

| Klasa | ludzie (korpus) | stary 08 | odrzucony 16 |
|---|---|---|---|
| po przyimku | 1,7 | 0,1 | 0,1 |
| oderwane „się” | 1,2 | 0,8 | 0,1 |
| oderwane „nie” | 0,3 | 0 | 0 |
| spójnik na końcu wiersza | 2,5 | 0,3 | 0,2 |
| przymiotnik \| rzeczownik | 2,1 | 2,1 | 0,1 |
| zgodność z cięciem ludzkim | — | 58,4% | 44,7% |
| nie dwa wiersze, choć ludzie dali dwa | — | 10,0% | 21,4% |

[W] Stary 08 robi mało rażących cięć. Jego słabości to przymiotnik | rzeczownik (brak wiedzy o frazie) i decyzja o liczbie wierszy, nie listy. Odrzucony 16 rzadko tnie źle, ale często odmawia dwóch wierszy; to Twoje „60 znaków w jednym wierszu”.

**Rekomendacja narzędzia:** `spaCy pl_core_news_sm` jako źródło klas granic, z listami 08 jako awaryjnym źródłem przy braku modelu. Alternatywa bez GPL: UDPipe 1 (ta sama jakość, ale NC) albo same listy i Morfeusz (−1 do −4 pp). Decyzja licencyjna: sekcja 5.

### P4. Tłumacz (LLM) jako źródło podziału

**Literatura** (`EXP\lit-p4-mt-segmentation.md`, wykonawca: gemini-pro; poniżej oznaczam, co sprawdziłem sam):
- [F] Wang i in. 2024, *PositionID: LLMs can Control Lengths, Copy and Paste with Explicit Positional Awareness* (arXiv:2410.07035). Abstrakt: „LLMs still encounter challenges with length control, frequently failing to adhere to specific length constraints due to their token-level operations”. Sprawdziłem abstrakt na arXiv.
- [F] Matusov, Wilken, Georgakopoulou 2019, *Customizing Neural Machine Translation for Subtitling*, WMT19 (metadane PDF ACL sprawdzone). Teza raportu gemini: model łamania plus twarde ograniczenia długości w beam search. Szczegółów i liczb HTER nie zweryfikowałem.
- [F] Karakanta i in. 2020: patrz P1. Wniosek autorów: „the essence of a good subtitle goes beyond matching a predetermined length”.
- Bez samodzielnej weryfikacji: MuST-Cinema i Papi i in. 2023 (`<eol>`/`<eob>`, systemy end-to-end lepsze od kaskadowych w metryce Sigma), Karakanta 2022 (metryka Sigma), Wilken 2022 (SubER), Álvarez 2017 (CRF). Prace „Cui i in. 2026” podane przez gemini nie zweryfikowałem; nie opieram na nich wniosków.

**Kod tłumaczenia w repo** (tylko odczyt) [F]:
- Są trzy silniki: `deepl`, `google`, `llm`.
- Google zakłada linie jednowierszowe (`engines\google\AGENTS.md`: „Kod zakłada, że każda linia wejścia jest jednoliniowa”).
- Prompt `engines\llm\prompts\translation.md` nie zawiera instrukcji łamania.
- Przekład trafia do `layout_translated` jako tekst nierozbity.

**Ocena wariantów:**

| Wariant | Jakość | Determinizm | Koszt i wznowienie | Ryzyko |
|---|---|---|---|---|
| (a) kod z pomiarem fontu | prototyp: 81% top-1 na NF+AMZN, 54/66 u właściciela | pełny | zero; zmiana reguły = przeliczenie układu bez tłumaczenia | błędy parsera (np. „Artemis”) |
| (b) LLM podaje wskazówki, kod decyduje | [H] może pomóc przy frazach, których parser nie widzi | niepełny; wskazówki zmieniają się między przebiegami | każda zmiana promptu = płatne ponowne tłumaczenie; cache tłumaczeń musi przechowywać znaczniki; DeepL/Google nie dadzą wskazówek → dwa tryby jakości | znaczniki psują przekład lub kontrakt `<sN>`; regresje trudne do testowania |
| (c) LLM decyduje sam | [W] gorsza: nie zna szerokości fontu, słabo liczy znaki (PositionID) | brak | jak (b) plus poprawki kodu i tak potrzebne | wiersze za szerokie, niespójność między odcinkami |

**Wniosek:** (a). Wariant (b) jest wykonalny technicznie: prompt dostaje instrukcję „oznacz granice fraz”, a translator zwraca znacznik usuwany przed TTS. Wymaga jednak zmiany kontraktu tłumaczenia dla jednego z trzech silników i płatnych przebiegów do oceny. Proponuję wrócić do niego dopiero wtedy, gdy wariant (a) z parserem osiągnie plateau na złotym zbiorze, a błędy będą frazowe (P5, lista błędów).

### P5. Logika rozmyta — jedna decyzja bez sztywnych progów

**Konstrukcja.** Ważona agregacja stopni rozmytych z wyborem minimum kosztu, w rodzaju Takagi–Sugeno rzędu 0 z rankingiem zamiast defuzyfikacji. Mamdani z defuzyfikacją jest tu zbędny, bo wynik to wybór jednego z dyskretnych układów, nie liczba. Dla każdego układu U (1 wiersz, każde cięcie na 2 wiersze, każde dwa cięcia na 3 wiersze, z wymuszonymi cięciami mówców):

```
u        = szerokość najdłuższego wiersza / dostępna szerokość (piksele, pomiar fontu; w prototypie znaki / znaki przy u = 1)
DŁUGI(u) = rise(u; 0,60; 1,00)                      # 0 do 60% szerokości, 1 przy pełnej
koszt(1 wiersz)   = DŁUGI(u)                         # u > 1: układ niedopuszczalny
koszt(n wierszy)  = 0,3 · DŁUGI(u_max)
                  + Σ_cięć [ (1 − A(klasa)) + 0,6 · (1 − s/n) ]   # s/n tylko dla cięć bez interpunkcji
                  + 0,6 · (Lmax − Lmin)/ΣL                         # równowaga
                  + 0,4 · liczba wierszy jednowyrazowych            # sierota
                  + 0,3 · [n = 3]                                   # dopłata za trzeci wiersz
wybór = argmin koszt; remis → mniej wierszy
```

`rise` to istniejące `anishift/services/subtitles/fuzzy.py:rise`. Stałe dopasowano na zbiorze właściciela w siatce 972 kombinacji (`EXP\proto_v2.py`, siatka `GRID`). Tabela A pochodzi z NF+AMZN i nie była strojona na właścicielu.

**Zmienne językowe i przynależności:**
- *Długość wiersza* (miara: szerokość w pikselach względem miejsca między marginesami; do ilości tekstu znaki są tylko przybliżeniem):
  - „krótki”: u ≤ 0,6 (≈ ≤ 37 zn. przy 62 zn. na pełną szerokość);
  - „długi”: przynależność liniowa od 0,6 do 1,0; 42 zn. ≈ 0,68 → 0,2; 52 zn. ≈ 0,84 → 0,6;
  - „niemieszczący się”: u > 1, zakaz.
  - [W] To odpowiada obserwacjom: profesjonaliści przechodzą na dwa wiersze przy 40–44 zn. (162 jednowierszowe vs 254 dwuwierszowe), a właściciel akceptuje jeden wiersz do ~0,8 szerokości (c13, c24).
  - Dlaczego szerokość, a nie znaki: BBC §3.1 (font proporcjonalny); u właściciela ten sam tekst 52 zn. to 0,84 szerokości w jednym serialu i 0,75 w innym (`EXP\px_per_char.json`: od 48 do 70 zn. na pełną szerokość).
- *Siła granicy* (z parsera): A(klasa) z hierarchii P2 plus rozpiętość poddrzewa s/n.
- *Równowaga*: (Lmax − Lmin)/ΣL, liniowo.
- *Liczba wierszy*: dopłata 0,3 za trzeci; jeden wiersz bez dopłaty.

**Jak to unika skrajności** [W]:
- Brak klifów: każdy składnik jest ciągły (liniowy), więc zmiana o jeden znak zmienia koszt o ułamek, a nie przerzuca decyzji między 1 a 3 wierszami.
- Żadna kara nie dominuje: najgorsze cięcie kosztuje około 1,0–1,6, pełna długość 1,0, pełna nierówność 0,6. Ocena każdego układu ma te same składniki, w tej samej skali.
- Jedna reguła dla wszystkich przypadków: nie ma osobnej gałęzi „za długie, więc tnij” ani „krótki tekst, więc nie tnij”. Liczba wierszy wynika z porównania cen.
- Co jest twarde (nienaruszalne, z `visual-quality.md`): wiersz mieści się w pikselach, słowo nie jest rozcinane, myślnik mówcy zaczyna wiersz, najwyżej 3 wiersze.

**Wyniki** [F] (`WTVENV python EXP\proto_v2.py pl_core_news_sm`, wyjście `EXP\proto-v2-out.txt` i `EXP\proto-v2-pl_core_news_sm.json`; baza: `WTVENV python EXP\owner_baseline.py`):

| Metoda | Zbiór właściciela (66) | NF+AMZN top-1 (593) | CR top-1 (1075) |
|---|---|---|---|
| stary 08, `split_line` 42 zn., 2 wiersze (ustawienia produkcyjne `LayoutLimits()`) | 44 (66,7%) | — | — |
| stary 08, 42 zn., do 3 wierszy | 38 (57,6%) | — | — |
| stary 08, max = szerokość przypadku, 2 wiersze | 36 (54,5%) | — | — |
| prototyp v1 (bez skrótów, list, poddrzewa, 3 wiersze tylko z musu) | 40/59 fit, 36/59 LOO | — | — |
| **prototyp v2** | **58 fit, 54 LOO (81,8%)** | **81,1%** | 63,9% |

Uwagi do pomiaru:
- Zbiór właściciela: 38 przypadków `fuzzy-spec/cases` (bez 31: jedno słowo 115 zn.), oczekiwany układ = wiersze wariantu `recommendation_v2` z `manifest.json`.
- Galeria: 20 decyzji „dwa wiersze, nie jeden” (g01–g15, g24–g27, g30). Galeria świadczy o liczbie wierszy, nie o miejscu cięcia: u6 ma tam też złe cięcia, np. „prima / materii”, „szkoła / przetrwania”. Te układy to wyjście u6, czyli 08, więc ta część zbioru sprzyja 08.
- Złe cięcia (8): „musi / zniknąć”, „naszą wspólną / przyszłość”, „klejnoty / Yamamoto”, „pasa / z balastem”, „wpływ / psychiczny”, „woli / Artemis”, „się / zakocha” (g28), „A co / w kolejnym…” (g29). Dwa z nich (b5, b6) odtworzyłem z fragmentów; pełne zdania znalazłem w galerii.
- Szerokość przypadków: z pomiaru `v2_measurement`. Szerokość galerii: oszacowana z px/znak tego samego serialu; dla serii bez pomiaru przyjąłem 62 zn. To przybliżenie i ryzyko.

**Wymagane przykłady — liczbowo i słownie** (najtańsze 2–3 układy; „dł” = długość, „cięcie” = szkoda granicy, „bal” = nierówność):

| Przyp. | Wybór (koszt) | Konkurenci | Słownie |
|---|---|---|---|
| g01 | „że w obronie interesów klienta / wszystkie chwyty są dozwolone.” 0,50 | jeden wiersz 0,71 (u = 0,88) | Dobra granica podmiot–orzeczenie, równe wiersze: taniej niż długi wiersz |
| g02 | „Ludzie zamieszkujący te ziemie / popełnili straszliwe grzechy.” 0,51 | „…popełnili / straszliwe grzechy.” 0,75; jeden wiersz 0,92 (u = 0,97) | Twoje „60 znaków w jednym wierszu” przegrywa wyraźnie |
| g05 | „Za kwestionowanie woli / Artemis odbieram…” 0,64 **(błąd)** | „Za kwestionowanie / woli Artemis…” 0,79; jeden wiersz 0,88 | Dwa wiersze słusznie; spaCy bierze „Artemis” za podmiot, więc „woli \| Artemis” wygląda na granicę zdania. Błąd parsera |
| g08 | „Jednak po rebelii klanu Shi / wiele osób zostało stracone.” 0,51 | 0,75; jeden wiersz 0,80 | Zgodnie z u6 |
| g20 | „Przepraszam. Idź z Midorikawą i resztą. / Baw się dobrze.” 0,27 | jeden wiersz 0,46; „Przepraszam. / Idź…” 0,73 | Asymetria: cięcie po kropce z długim górnym wierszem wygrywa; „Przepraszam.” na górze kosztuje dodatkowo karę za sierotę |
| g29 | „A co w kolejnym odcinku / „Grand Blue Dreaming”?” 0,61 | jeden wiersz 0,67; „A co w kolejnym / odcinku…” 1,04 | Tytuł razem, „A co” nie zostaje samo; jeden wiersz blisko, bo u = 0,87 |
| c03 (= c37) | „Żeby rozwalić zwykłych aniołów, / mógłbym wysadzić … z nimi.” 0,46 | cięcie „wysadzić / w powietrze” 0,88; trzy wiersze 0,91 | Przecinek bije wyrównanie mimo dolnego wiersza 0,89 szerokości; trzy wiersze niepotrzebne |
| c07 | „Upewniłam się, że wszyscy – a zwłaszcza / Przewodniczący – poszli…” 1,14 **(błąd)** | trzy wiersze wg Twojego wyboru 1,43 | Myślnik wtrącenia ma niską akceptowalność w korpusie (0,34), bo profesjonaliści rzadko łamią przy myślniku; decyzja w sekcji 5 |
| c33 | 3 wiersze „…złością przez całe to / wyjątkowo długie spotkanie / …” 1,36 **(błąd)** | Twój układ 1,73 | Trzy wiersze słusznie (dwa się nie mieszczą), ale cięcie „to / wyjątkowo” wygrywa przez błędne klasy; parser nie łączy „przez całe to … spotkanie” |
| c13 | jeden wiersz 0,44 (u = 0,77) | „Osiągnęliśmy rozejm / z Sokołem…” 0,61 | Zgodnie z Twoją regułą „nie łamać tylko dlatego, że przekracza 42” |
| c04 | jeden wiersz 0,62 (u = 0,85) | „Dlaczego się na mnie / z taką złością…” 0,66 | Blisko remisu; wygrywa jeden wiersz |
| c36 | „Martwię się o ciebie, / bo od wczoraj…” 0,42 | „…bo od wczoraj / nie odpowiadasz…” 0,70 | Przecinek przed „bo” wygrywa z równymi wierszami |
| b2 | „I to ja traktuję / naszą wspólną przyszłość…” 0,90 | stary układ „naszą wspólną / przyszłość” nie jest w pierwszej trójce | Fraza „naszą wspólną przyszłość” zostaje razem |

### P6. Wydajność i integracja

**Czas** [F]:
- spaCy sm: 0,24–0,29 s ładowania i 0,48–0,51 s na 500 kwestii (`parse.py`).
- Wybór układu w Pythonie (wszystkie układy 1–3 wiersze): 0,82 s na 500 kwestii (pomiar inline w `WTVENV`, `EXP\proto_v2.py`, `parts` + `choose`, szerokość 62 zn.).
- `geometry.measure_text` dla wszystkich ciągłych przedziałów słów 500 kwestii (8568 przedziałów): 0,54 s, 0,064 ms na przedział (`WTVENV python EXP\time_measure.py`, `fonts=None`). Z prawdziwymi fontami czas może być większy; nie zmierzyłem.
- [W] Razem około 2–3 s na odcinek: rząd wielkości poniżej limitu „kilku minut”. Stanza dodałaby ~6 s ładowania i ~7 s na 500 kwestii.

**Integracja** (tylko odczyt kodu worktree `fuzzy`) [F]:
- Dialog: `service.py:_laid_out_text` → `linebreak.py:layout_dialogue(event, text, profile, limits)` → `split_line(strip_span_markers(text), max_chars, max_lines)` → `restore_markers` → `replace_visible_text` lub `reflow_visible_text`. Nową decyzję wpina się w miejsce `split_line` wewnątrz `layout_dialogue`. Dostaje ona `event` i `profile`, więc może mierzyć szerokość przez `measure_text` i `available_width`. Sygnatura `layout_dialogue` i obsługa `<sN>` (`strip_span_markers` i `restore_markers`) zostają.
- Szyldy: `split_for_layout` i `split_lines(event, text, count, profile)` zostają bez zmian (kontrakt `fit_signs`).
- `\q2` i automatyczne zawijanie: przy `WrapStyle` 0/3 libass zawija sam, gdy wiersz przekracza szerokość. Nowa decyzja ma gwarantować u ≤ 1, a `wrap_text` służy jako sprawdzian, że libass nie doda łamania (jak w aneksie v5: zgodność 5406/5406). Przy `\q2` brak zawijania czyni u ≤ 1 jedyną ochroną przed wyjściem poza ekran.

**Model:**
- Ładowany leniwie, raz na proces (moduł z `functools.cache` na `spacy.load`), w domenie `subtitles`. Nie jest to silnik z rejestrem, bo nie ma wyboru użytkownika.
- Bez modelu (brak pakietu, błąd ładowania): klasy z list 08, czyli tryb `lex` (−1 pp na całym korpusie, −4 pp na NF+AMZN), z ostrzeżeniem w logu.

**Testy deterministyczne:**
- złoty zbiór (66 + przyszłe przypadki) jako test parametryczny z zamrożonymi parsami (JSON z tokenami), żeby test nie zależał od wersji modelu;
- osobny test zgodności parsera na 20 zdaniach (wykryje zmianę modelu);
- test regresji na korpusie NF+AMZN z progiem top-1.

---

## 4. Rekomendacja techniczna

**Narzędzie:** `spaCy pl_core_news_sm` (26 MB, bez PyTorcha) jako źródło klas granic. Fallback: listy z 08 (`_NON_BREAKING_HEADS`, `_CONJUNCTIONS`, `_TITLE_HEADS` itd.) i `anishift.text.boundaries.is_false_sentence_break` dla skrótów. Przy odrzuceniu GPL: UDPipe 1 (NC) albo Morfeusz 2 + listy.

**Decyzja:** jedna funkcja kosztu z P5. Gotowa do specyfikacji:

| Element | Definicja | Wartość wyjściowa | Źródło |
|---|---|---|---|
| u | szerokość najdłuższego wiersza / `available_width` (lub 90% PlayResX przy `\q2`, jak w aneksie v5) | — | BBC §3.1, pomiar |
| DŁUGI(u) | `rise(u; 0,60; 1,00)` | 0,60 / 1,00 | dopasowanie do właściciela; zgodne z korpusem 40–44 zn. |
| waga długości w układzie wielowierszowym | 0,3 | 0,3 | dopasowanie |
| A(klasa) | tabela z NF+AMZN (P2) | 1,00…0,00 | korpus, nie strojona |
| lista przecinków wyliczenia | cięcie po przecinku wewnątrz wyliczenia rzeczowników: A = 0,5 | 0,5 | przyjęte z ręki [D] |
| rozpiętość poddrzewa | +0,6 · (1 − s/n) dla cięć bez interpunkcji | 0,6 | dopasowanie |
| równowaga | 0,6 · (Lmax − Lmin)/ΣL | 0,6 | dopasowanie; korpus asymetrii |
| sierota | 0,4 za wiersz jednowyrazowy | 0,4 | korpus (orphan), właściciel |
| dopłata za 2 wiersze | 0 | 0 | dopasowanie |
| dopłata za 3 wiersze | 0,3 | 0,3 | dopasowanie; Szarkowska i Gerber-Morón 2018 |
| twarde | u ≤ 1 dla każdego wiersza wielowierszowego; brak rozcięcia słowa; myślnik mówcy zaczyna wiersz; ≤ 3 wiersze; kropka skrótu nie jest końcem zdania | — | `visual-quality.md` |

**Ocena jakości (bramka akceptacji):**
- złoty zbiór właściciela, z każdym nowym rozstrzygnięciem dopisywanym jako przypadek: ≥ 54/66 (stan prototypu; stary 08 produkcyjnie: 44/66) i zero nowych błędów w znanych złych cięciach;
- NF+AMZN top-1 ≥ 80% (prototyp: 81,1%);
- klasy złych cięć na korpusie nie wyższe niż u 08 (po przyimku ≤ 0,1%, „się” ≤ 0,8%, przymiotnik | rzeczownik ≤ 2,1%);
- czas ≤ 10 s na odcinek;
- przed wdrożeniem: galeria przed/po na prawdziwym pomiarze fontu, ocena właściciela.

**Koszt:**
- zależności: `spacy` z thinc, numpy itd. (cały `TMPVENV` razem z UDPipe, Morfeuszem i narzędziami pomocniczymi miał 251 MB bez modeli; samego spaCy osobno nie mierzyłem) + model 26 MB (przez `uv add` właściciela, z URL koła modelu);
- czas ≈ 2–3 s na odcinek;
- kod: jedna funkcja kosztu i tabela A w miejscu `_split`/`_dialogue_cut` z 08. Listy 08 zostają jako fallback.

**Stary 08: uporządkować czy zastąpić?** [W] Zastąpić rdzeń decyzji. Zachować:
- listy (fallback i uzupełnienie dla skrótów i tytułów);
- `_speaker_start`;
- `restore_markers` i `<sN>`;
- `split_for_layout` (szyldy).

Uzasadnienie: dobre cechy 08 to unikanie złych klas (tabela P3) i to, że nie tnie jednowierszowych ponad potrzebę przy 42. Wynikają one z list, nie z rekurencyjnego `_split`. Błędy 08 na Twoim zbiorze (22 przy ustawieniach produkcyjnych) to w połowie decyzja o liczbie wierszy (6: łamanie mieszczącego się jednego wiersza; 4: brak koniecznych trzech wierszy lub wiersza na mówcę), a w połowie miejsce cięcia (12), głównie brak wiedzy o frazach. Jedna funkcja kosztu naprawia oba bez dodawania warstw.

---

## 5. Ryzyka, niewiadome i decyzje dla właściciela

1. **[D] Licencja.** Modele spaCy PL są GPL-3.0, UDPipe CC BY-NC-SA, a repo nie ma pliku LICENSE. Opcje: (a) spaCy i licencja projektu zgodna z GPL; (b) UDPipe i akceptacja „niekomercyjne”; (c) bez parsera: listy + Morfeusz, o 1–4 pp gorzej. Licencji słownika Morfeusza i modeli Stanzy nie sprawdziłem.
2. **[D] Wtrącenie z myślnikami (c07).** Wolisz trzy wiersze, choć mieszczą się dwa. Jednocześnie krytykujesz „trzy wiersze tam, gdzie mieszczą się dwa”. Jedna reguła nie spełni obu. Propozycja: myślnik wtrącenia ma wysoką akceptowalność (jak przecinek), ale trzy wiersze tylko przy u > 0,8 w najlepszym układzie dwuwierszowym.
3. **[D] Długi jeden wiersz vs dobre cięcie (c11 u = 0,90, c15 u = 0,98).** Twoje przypadki porównywały jeden wiersz tylko ze złym cięciem („1,4 / miliarda”, „się / bawił”). Prototyp wybiera dwa wiersze z dobrym cięciem („Z nami przy drinku / będziesz się bawił…”). Galeria (g02, g05, g07) mówi, że tak wolisz. Potwierdź.
4. **Błędy parsera** (b6/g05 „woli / Artemis”, c08 „zakwitające / kwiaty”, c19 „Rada”): spaCy myli obce imiona z podmiotem, a imiesłowy z czasownikami. [H] Zgoda przymiotnika z rzeczownikiem z Morfeusza poprawi c08; „Artemis” wymaga wiedzy, że nazwa po rzeczowniku jest dopełnieniem. To realny limit lekkiego parsera, a Stanza ma ten sam błąd.
5. **Skróty z liczbą** (c10 „godz. / 17.30”): `is_false_sentence_break` naprawia kropkę skrótu, ale nie wiąże skrótu z liczbą. Dodać „skrót | następny token” do klasy „nigdy” (lista `_TITLE_HEADS` z 08 to częściowo robi).
6. **Szerokości galerii są oszacowane** z px/znak tego samego serialu, a przy części serii przyjęte (62 zn.). Przed specyfikacją powtórzyć ocenę na prawdziwym pomiarze fontu.
7. **Dopasowanie na 66 przykładach** to mały zbiór (8 stałych). Spadek z 58 do 54 przy LOO pokazuje lekkie przeuczenie. Stałe traktować jako punkt wyjścia; każdą nową decyzję dopisywać do zbioru.
8. **Nie istnieje badanie „jeden długi vs dwa krótkie” dla polskiego dialogu.** Próg długości opiera się na Twoich wyborach i normie profesjonalistów, nie na okulografii.

---

## 6. Katalog przypadków brzegowych

Każdy wiersz wynika z tej samej reguły z P5, chyba że kolumna „Źródło” mówi „decyzja”. „Spr.” = sprawdzone w prototypie (id przypadku).

| Przypadek | Przykład | Oczekiwany układ | Uzasadnienie w regule | Źródło / status |
|---|---|---|---|---|
| bardzo krótka kwestia | „Uciekaj!” | 1 wiersz | DŁUGI = 0, każde cięcie kosztuje > 0 | rozstrzygnięte; spr. c01 |
| tuż pod 42 zn. | „Czy aby na pewno zajmują się tylko masażem?” (43) | 1 wiersz przy u = 0,70 | DŁUGI(0,70) = 0,25 < najlepsze cięcie | właściciel c24; spr. |
| tuż nad 42, mieści się | „Osiągnęliśmy rozejm z Sokołem z klanu Estebanów.” (48) | 1 wiersz przy u = 0,77 | 0,44 < 0,61 | właściciel c13; spr. |
| 52–62 zn. z dobrym cięciem | g02, g13 | 2 wiersze | długość 0,6–0,9 > cięcie 0,5–0,6 | galeria; spr. |
| dwa zdania symetryczne | „Najpierw…”, c34 | cięcie po kropce/przecinku | A = 1,0, bal ≈ 0 | rozstrzygnięte |
| dwa zdania, pierwsze długie | g20 „Przepraszam. Idź z Midorikawą i resztą. / Baw się dobrze.” | po kropce, górny dłuższy | bal 0,27 < szkoda cięcia w zdaniu ≥ 0,5; korpus: do nierównowagi 0,5 w 89–100% | korpus; spr. g20 |
| dwa zdania, pierwsze krótkie | „Przepraszam. / Idź z Midorikawą…” | krótki górny tylko gdy brak innych dobrych cięć | sierota +0,4; korpus: krótki górny akceptowany rzadziej (42% vs 75%) | korpus; [D] próg nierówności |
| trzy i więcej zdań | c26 | 3 wiersze, po zdaniu w wierszu | dwa nie mieszczą się; cięcia po kropce | właściciel c26; spr. |
| dialog dwóch osób | „- Kufer ze złotem? / - Widać? Całe szczęście.” | wiersz na mówcę | twarde: myślnik mówcy zaczyna wiersz | Netflix, właściciel c05; spr. |
| trzech mówców | c06 | 3 wiersze | twarde | właściciel c06; spr. |
| mówca z długą kwestią | c27 | 3 wiersze: mówca 1 / mówca 2 cz. 1 / cz. 2 | cięcie wymuszone + wolne cięcie po przecinku | właściciel c27; spr. |
| wtrącenie z myślnikami | c07 | [D] 2 lub 3 wiersze | konflikt (sekcja 5.2) | **decyzja** |
| nawias | „(…)” | cięcie przed nawiasem lub po nim | nawias zamykający = koniec frazy (punct_class) | wytyczne; nie spr. |
| cytat / tytuł w cudzysłowie | g29 „A co w kolejnym odcinku / „Grand Blue Dreaming”?” | tytuł razem | cięcie w tytule: name/mwe A = 0,39 + małe poddrzewo | galeria g29; spr. |
| imię i nazwisko | „Futari Shizuka” | razem | flat → name/mwe | właściciel c09; spr. |
| honoryfikator | „Satou-san” | razem (jedno słowo z łącznikiem) | słowa nie rozcinamy | twarde |
| wyliczenie nazw | c08 „z Azumą, Satou i Watanabe” | razem, jeśli się da | przecinek wyliczenia A = 0,5 | właściciel c08; **błąd parsera** |
| liczba z rzeczownikiem | c11 „1,4 miliarda ludzi” | nie ciąć wewnątrz | nmod + małe poddrzewo | właściciel c11; [D] jeden wiersz u = 0,9 |
| jednostki, daty, godziny | c23 „25\hkg”, c10 „godz. 17.30” | `\h` zostaje twardą spacją; skrót + liczba razem | `\h` nie jest kandydatem; skrót: [D] klasa „nigdy” | właściciel c23 spr.; c10 błąd |
| skróty z kropką | „dr”, „ul.”, „np.”, „tzw.” | kropka skrótu nie kończy zdania | `is_false_sentence_break` | `anishift/text/boundaries.py`; spr. c10 częściowo |
| wielokropek na początku/końcu | c30 „Ja... nie wiem, czy potrafię.” | wielokropek przy swoim słowie | A(wielokropek) = 0,74; słowa nie rozcinamy | spr. c30 |
| „?!” | „Czy ty właśnie miałeś zamiar nazwać mnie suką?!” | znak końca jak kropka | punct_class traktuje „?!” jako koniec zdania | rozstrzygnięte |
| wyrazy obce, łacina | g10 „prima materii” | razem | parser: flat/compound; błąd w u6 | galeria; prototyp wybiera „prima materii / …” |
| bardzo długie słowo | c31 (115 zn.) | 1 wiersz (overflow dopuszczony, słowa nie tniemy) | twarde: brak spacji = brak kandydatów | właściciel c31 |
| kwestia bez spacji | j.w. | j.w. | j.w. | j.w. |
| „się” | c15 „będziesz się / bawił”, g28 „się / zakocha” | „się” przy czasowniku | expl:pv → klasa „się” A = 0 | właściciel; spr. |
| jednoliterowe na granicy | „w”, „z”, „i”, „a” | zawsze z następnym słowem | A = 0,12 (jedna litera) lub 0 (przyimek) | FKBB pkt 4; korpus |
| przeczenie „nie” | c14 „nie pojawi się” | „nie” przy czasowniku | A = 0 | Netflix General §4 |
| spójniki i, a, ale, że, bo, który | c39 „/ i kupiłem”, c36 „/ bo od” | cięcie przed spójnikiem | spójnik na końcu A = 0; przed nim A wysokie (granica zdań) | właściciel c39 spr. |
| frazeologizm | „raz na zawsze”, „po prostu”, „w ogóle” | razem | fixed/flat lub małe poddrzewo; b1 | spr. b1 |
| kursywa / `<sN>` | c29, c12 | układ jak bez tagów; znaczniki wracają na swoje słowa | decyzja na tekście bez znaczników; `restore_markers` | P6; spr. c29 (tekst) |
| nie mieści się w dwóch | c33 | 3 wiersze | jedyne dopuszczalne | właściciel c33; cięcie: błąd |
| nie mieści się w trzech | > 3 × szerokość | 3 wiersze + raport overflow | twarde ≤ 3 | [D] czy skracać przekład |
| `\q2`, wąskie marginesy | c02, c33 | u liczone od 90% PlayResX przy `\q2`; od marginesów zdarzenia | `available_width` | aneks v5; spr. przez pomiar przypadków |
| tagi ASS w środku | c34 `{\fs36\fscx110}` | pomiar z tagami | `measure_text` mierzy z tagami | właściciel c34 |
| piosenki, szyldy | — | poza zakresem: `split_for_layout` + `fit_signs` | — | granica zakresu |

---

## 7. Źródła

Literatura (pełne lokalizatory i cytaty w `EXP\lit-p1-readability.md`):
- Gerber-Morón, Szarkowska 2018, *Line breaks in subtitling…*, JEMR 11(3): https://pmc.ncbi.nlm.nih.gov/articles/PMC7733619/
- Gerber-Morón, Szarkowska, Woll 2018, *The impact of text segmentation on subtitle reading*, JEMR 11(4): https://pmc.ncbi.nlm.nih.gov/articles/PMC7901653/
- Szarkowska, Gerber-Morón 2018, *Viewers can keep up with fast subtitles*, PLOS ONE: https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0199331
- Szarkowska, Gerber-Morón 2018, *Two or three lines…*, Perspectives (manuskrypt UCL): https://discovery.ucl.ac.uk/10054421/3/Szarkowska_Two%20or%20three%20lines_a%20mixed-methods%20study%20on%20subtitle%20processing%20and%20preferences_plain_FINAL.pdf
- Kruger, Szarkowska, Krejtz 2015 (przegląd): https://refractory-journal.com/kruger-szarkowska-krejtz/
- Raport SURE 2018: https://avt.ils.uw.edu.pl/wp-content/uploads/sites/170/2018/07/SURE_Project_Report.pdf
- Dyson, Kipping 1998: https://journals.uc.edu/index.php/vl/article/download/5671/4535
- Bernard i in. 2002: https://web.archive.org/web/20170618194327/http://psychology.wichita.edu/surl/usabilitynews/42/text_length.asp
- Shaikh 2005: https://web.archive.org/web/20170918212943/http://psychology.wichita.edu/surl/usabilitynews/72/LineLength.asp
- Slattery, Vasilev 2019: https://pmc.ncbi.nlm.nih.gov/articles/PMC6647890/
- Rayner 1998: http://wexler.free.fr/library/files/rayner%20(1998)%20eye%20movements%20in%20reading%20and%20information%20processing.%2020%20years%20of%20research.pdf
- Karakanta, Negri, Turchi 2020, IWSLT: https://aclanthology.org/2020.iwslt-1.26.pdf
- Matusov, Wilken, Georgakopoulou 2019, WMT: https://aclanthology.org/W19-5209.pdf
- Wang i in. 2024, PositionID: https://arxiv.org/abs/2410.07035
- Niezweryfikowane samodzielnie (relacja gemini): Karakanta i in. 2022 https://aclanthology.org/2022.lrec-1.328.pdf; Papi i in. 2023 https://aclanthology.org/2023.tacl-1.77.pdf; Wilken i in. 2022 https://aclanthology.org/2022.iwslt-1.1.pdf; Lison, Tiedemann 2016 https://aclanthology.org/L16-1147.pdf

Wytyczne:
- Netflix PL: https://partnerhelp.netflixstudios.com/hc/en-us/articles/216787928-Polish-Timed-Text-Style-Guide
- Netflix General: https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617-Timed-Text-Style-Guide-General-Requirements
- BBC: https://www.bbc.co.uk/accessibility/forproducts/guides/subtitles/
- ESIST: https://www.esist.org/wp-content/uploads/2016/06/Code-of-Good-Subtitling-Practice.PDF.pdf
- Karamitroglou 1998: https://translationjournal.net/journal/04stndrd.htm
- FKBB 2019: https://kulturabezbarier.org/wp-content/uploads/2019/12/Napisy-dla-nieslyszacych_zasady-tworzenia_2019.pdf
- KRRiT 2016: http://www.archiwum.krrit.gov.pl/krrit/aktualnosci/news,2213,stanowisko-w-sprawie-jakosci-i-sposobu-realizacji--napisow-dla-nieslyszacych-w-utworach.html
- DCMP: https://dcmp.org/learn/597-captioning-key---text

Narzędzia:
- UDPipe 1 Models (licencja CC BY-NC-SA): https://ufal.mff.cuni.cz/udpipe/1/models
- model UDPipe PL PDB 2.5: https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/3da49192-d502-483b-8592-66eb503b8e60/content
- spaCy `pl_core_news_*` 3.8.0: licencja i metryki z `meta.json` zainstalowanych modeli w `TMPVENV`

Dane i skrypty: `EXP\corpus.py`, `stats.py`/`stats.json`, `dataset.py`/`dataset.json`, `parse.py`, `evaluate.py`, `significance.py`, `classes.py`, `asymmetry.py`, `fuzzyproto.py`, `px_per_char.py`, `make_extra.py`, `gallery_gold.json`, `proto_cases.py` (v1), `proto_v2.py`, `proto-v2-out.txt`, `owner_baseline.py`, `time_measure.py`, `run_baseline.py`.

---
kind: specification
status: v4
updated: 2026-10-18
---

# Rozmyte łamanie polskich dialogów — v4

Właściciel 18.10: implementacja rusza po akceptacji planu 01 i tej specyfikacji przez trzech recenzentów (astra, sol6, claude); decyzje otwarte mają wartości domyślne (rekomendacje przyjęte 18.10), a właściciel akceptuje wynik na galerii przed/po.

## Aneks v4 (2026-10-18) — nadrzędny wobec wskazanych sekcji

Powód: cel [visual-quality.md](visual-quality.md) v2.1, research [measurement.md](research/measurement.md) i [fonts.md](research/fonts.md), przegląd planu 01 oraz przeliczenie modelu na przypadkach 01–39 (`workspace/.quality/experiments/fuzzy-spec/cases/model-v32.md`). Gdzie aneks przeczy dalszym sekcjom, obowiązuje aneks.

1. **Czcionka (zastępuje zakaz zmiany fontu z §1 i „W skrócie”).** Style dialogowe mogą dostać czcionkę właściciela przez klon stylu (visual-quality §5, plan 01 D7). Łamanie mierzy czcionką klonu.
2. **Pomiar (§2, „Dopasowanie”).** Metoda i dopasowanie czcionek jak w aneksie v4 A.3 `fuzzy-signs-and-split.md`: Pillow + fontTools, 1000 px, atrament, widoczny obrys/cień, blur; p90 zgodności z libass 1,14%, dla dialogów 0,59%, więc τ = 0,98 pokrywa p95 dialogów (0,92%).
3. **Liczba wierszy — ratunek dwustopniowy (zastępuje miękkie COUNT jako jedyny mechanizm, §3–§4).** Kandydaci z trzema wierszami (najwyżej dwa cięcia; czterech wierszy generator nie tworzy) wchodzą do oceny tylko wtedy, gdy żaden kandydat z ≤ 2 wierszami nie przechodzi filtra mieszczenia. Kolejność ratunku: (1) ≤ 2 wiersze z ochronami; (2) ≤ 2 wiersze z rozluźnionymi ochronami fraz (`relaxed_phrases`); (3) 3 wiersze; (4) `overflow_unavoidable`. Wynik na 01–39: zmienia się tylko 07 (B, 3 wiersze → A/C, 2 wiersze); 06, 26, 27, 33 bez zmian, bo żaden układ dwuwierszowy się tam nie mieści.
4. **Jednoliterowe słowo na końcu wiersza (§2, SYN).** Cięcie bezpośrednio po słowie jednoliterowym (w, z, o, u, i, a…) jest chronione jak cięcie po przyimku (ochrona, nie tylko SYN = 1); rozluźniane tylko w kroku ratunku (2). Wynik na 01–39: żaden wybór się nie zmienia (rośnie tylko Q przegranych 02 D i 39 A).
5. **Kształt przy mocnej granicy (§3, SHAPE).** SHAPE pomija parę wierszy rozdzieloną mocną granicą INT (koniec zdania, przecinek, średnik, dwukropek), tak jak dziś pomija zmianę osoby. Powód: przypadek 38 („…anielsko-apostolskim duetem, / który za nią pobiegł…”) wygrywał cięciem po przecinku tylko w części zakresu szerokości; z tą regułą wygrywa przy każdej skali ≥ 0,52. Wynik na 01–39: zmienia się tylko 18 (A → B, zgodnie z rekomendacją galerii; usuwa znany wyjątek z §5 pyt. 8).
6. **Przypadki 37–39 jako kontrakt testów:** 37 A (cięcie po przecinku), 38 A (cięcie po przecinku), 39 B (cięcie przed „i”). To przypadki z galerii przed/po 18.10 (`visual-fixes/line-breaks/05.png`, `06.png`), które nocny kod złamał źle.
7. **SRT.** SRT zapisywane z ASS dostaje podziały mierzone profilem stylu źródła (te same co ASS). SRT ze źródła SRT nie ma stylów, więc działa tryb `unmeasured`; jego filtr znakowy jest jawnym wyjątkiem od zasady „bez twardych progów”, bo bez pomiaru nie ma innej miary.
8. **Decyzje właściciela (§5) — wartości domyślne 18.10:** 1 (03 B), 3 (33 B), 4 (28 D), 5 (31 `overflow_unavoidable`), 6 (pomiar i τ = 0,98), 7 (filtr `unmeasured`), 9 (`max_chars_per_line` tylko w `unmeasured`) — przyjęte jako rekomendacje; 2 (07) — rozstrzyga ratunek z pkt 3, właściciel zobaczy 07 na galerii; 8 (18) — rozstrzyga pkt 5.

## W skrócie dla właściciela

Wybieramy wszystkie widoczne granice i zapisujemy je jawnie jako `\N`; SRT dostaje te same podziały.
Odtwarzacz docelowy: mpv/libass. Bez nowych twardych spacji, zmiany źródłowego `\q`, fontu lub czasu.
Jedna ocena łączy szkody sensu i geometrii. Dopasowanie jest wcześniejszym filtrem bezpieczeństwa.
Proponowany próg to 98% szerokości po marginesach, liczony dla widocznego tekstu z obrysem/cieniem.
Pierwsze ryzyko planu: do wdrożenia pomiaru prawdziwym fontem wszystkie eventy idą trybem `unmeasured`.
Reguły językowe korzystają wyłącznie z tekstu i zamkniętych list; brak dowodu oznacza szkodę 0,6.
Przecinek jest umownym sygnałem granicy, nie dowodem pełności składniowej; jego koszt pokazuje 18.
Gdy żaden układ chroniący frazy się nie mieści, wolno rozdzielić frazę, ale nie wyraz ani grafem.
W [galerii](../../../workspace/.quality/experiments/fuzzy-spec/cases/index.md) przeliczono 36 przypadków bez ręcznych etykiet językowych.
Względem v2: 18 B → A (do decyzji), 28 brak → D (`Jan / Kowalski`); 31 nadal nie mieści się.
To kontrakt do zatwierdzenia, nie dowód działania pełnego generatora ani profilu mpv właściciela.

## 1. Wejście i zapis

Jednostką jest wynikowy event dialogowy: polski tekst, kotwice tagów, czas, pochodzenie,
autorskie granice i dostępne mapowanie wypowiedzi. Nie wymaga ręcznych relacji językowych.
Profil obejmuje fonty z `fonts/` par, załączników MKV/osadzonych fontów ASS, style,
override’y, marginesy, rozdzielczość i konfigurację mpv/libass. Tłumaczenie jest wspólne;
layout następuje per event przy rekonstrukcji, po mapowaniu wypowiedzi na target.
Reuse: `pysubs2`, `subtitles/text.py` (`reflow_visible_text`), `text/graphemes.py`,
`text/boundaries.py`, listy/helpery `translation/linebreak.py`, `fitting.py` (`_play_width`, marginesy).
Pomiar Arialem z `fitting.py` nie jest pomiarem fontu odcinka; nie dodajemy parsera NLP ani LLM.

Każde wybrane cięcie zapisujemy jako `\N`; eksport SRT zamienia je na nową linię.
Zachowujemy źródłowe `\q`, istniejące `\h` i zakres tagów; bez emulacji rebalance/`wrap_lines_smart`.
Sprawdzamy dopasowanie każdego jawnego wiersza i brak dodatkowego auto-wrap w docelowym profilu.
Polskie źródło bez granic może pozostać jednym wierszem, jeżeli mieści się i wygrywa ocenę.

## 2. Warunki, dowody językowe i dopasowanie

**Nienaruszalne:** słowa, interpunkcja, kolejność grafemów, tekst TTS, czasy, font,
pozycja, warstwa i zakresy tagów. Ciąć tylko łamliwy separator: nigdy wnętrze wyrazu,
grafemu, tagu, liczby/zakresu ani istniejącego `\h`; nie odrywać otwierającego nawiasu/
cudzysłowu od prawej strony ani zamykającego od lewej. Szyldy/piosenki/rysunki poza zakresem.
Wynik ma być idempotentny. Pusty/tagowy event pozostaje bez zmian.

**Ochrony fraz:** rozpoznane pary nazwy/inicjały, tytuły/skróty z dopełnieniem,
liczba–jednostka/mnożnik, przyimek z początkiem grupy, negacja, lokalne `się` i frazy z list.
Są ostre na pierwszym poziomie, a w ostatecznym ratunku stają się `α_SYN=1` (§4).
Nieznanego idiomu ani relacji nie wolno ogłaszać rozpoznaną lub twardo chronioną.

Poniższa tabela definiuje **wszystkie** sygnały; normalizacja słów przez `_clean`/`_tail`
z `linebreak.py`, indeksy cięć w znormalizowanym widocznym tekście. Heurystyka nie jest parserem.

| Klasa / aktywacja | Deterministyczny dowód i ograniczenie |
| --- | --- |
| Ochrona nazwy/skrótu | `_names_pair`: dwa wyrazy z wielkiej litery, nie ALL CAPS, bez interpunkcji między nimi; `_TITLE_HEADS`; `is_false_sentence_break` z `text/boundaries.py` (tam są skróty EN/PL i inicjały). To konserwatywna heurystyka, nie słownik osób. Przecinek przerywa nazwę. |
| Ochrona liczby | Token `\d+(?:[.,–-]\d+)*` przed tokenem zaczynającym się literą: konserwatywne przybliżenie jednostki/mnożnika, także nieznanego. Interpunkcja kończąca token przerywa ochronę (`17.30, obok`); separator dziesiętny wewnątrz liczby nie. Sam token liczby/zakresu nigdy nie jest dzielony. |
| Ochrona przyimka/frazy | `_NON_BREAKING_HEADS` z następnym słowem, wnętrze dokładnego dopasowania `_PREPOSITIONS_MULTIWORD`/`_CONJUNCTIONS_MULTIWORD` (2–4 tokeny). Interpunkcja kończąca lewy token przerywa ochronę. |
| Ochrona negacji | Literalne `nie` + następne słowo, chyba że bezpośrednio poprzedza je przyimek: `na nie` chroni przyimek, ale nie tworzymy `nie cały`. |
| Ochrona lokalnego `się` | Przed `się`: lewy token w `_VERB_HEADS` lub `_REFLEXIVE_HEADS`; po `się`: następny lub poprzedzający `się` token w `_VERB_HEADS` (także `będziesz się / bawił`). Inna forma czasownika nie jest automatycznie dowiedziona. |
| SYN: modalne/posiłkowe = 1 | Cięcie bezpośrednio po `_VERB_HEADS`, jeśli nie ma interpunkcyjnej granicy. Lista nie zawiera `mógłbym`; brak rozpoznania przechodzi do kolejnych reguł. |
| SYN: określenie/podmiot/spójnik = 0,9 | Lewy token w `_PRONOUN_HEADS` lub `_CONJUNCTIONS` (także `a`/`i`); albo kończy się `_ADJECTIVE_ENDINGS`, a prawy nie rozpoczyna grupy. Całą regułę 0,9 pomijamy dla homonimów `{nim, im, jak, tylko}` oraz zaimka z `_PRONOUN_HEADS` bezpośrednio po przyimku: brak dowodu = 0,6, nie rozpoznanie składni. Końcówki nie zawierają `ące`; `mógłbym` spełnia `ym`. |
| SYN: idiom / nieznana relacja | Nie ma słownika idiomów ani analizatora zależności. Nierozpoznane cięcie = 0,6, chyba że ma niżej zdefiniowany sygnał neutralny. Nie obiecujemy wykrycia `wysadzić / w powietrze`. |
| SYN: neutralne = 0 | Granica interpunkcyjna z następnego wiersza tabeli, zmiana osoby albo początek grupy: prawy token w `_NON_BREAKING_HEADS`, `_CONJUNCTIONS` lub `{który, która, które}`. To sygnał powierzchniowy, nie dowód pełnej frazy. |
| INT: mocna granica, `m=1` | Po `, ; :`, po pełnym końcu `. ! ? 。 ！ ？` z odrzuceniem `is_false_sentence_break`, albo po każdym z pary samodzielnych myślników wtrącenia. Parujemy kolejne niebędące zmianą osoby myślniki; nieparzysty ostatni nie daje dowodu. Wielokropki `…` i `...` są jawnie wyłączone (`m=0`), mimo `SENTENCE_ENDINGS`/`_STRONG_CUT`; skrót i sam początek grupy też dają `m=0`. |
| SYN: odległe `się`, co najmniej 0,25 | `się` bezpośrednio przed przyimkiem: każde późniejsze cięcie w tej samej części zakończonej pełnym końcem zdania dostaje minimum 0,25, **z wyjątkiem mocnej granicy INT i zmiany osoby**. Nie szukamy nieznanego czasownika; to zastępnik zależności, nie ręczna relacja z `patrzysz`. |
| Zmiana osoby | Mapowanie metadanych albo pierwszy segment od myślnika i kolejne od myślnika po pełnym końcu zdania, poza cytatem/skrótem/wtrąceniem. Wielokropek nie wystarcza; myślnik zostaje z pierwszym słowem. Dowolna liczba osób. |

Kolejność SYN: ochrona frazy → interpunkcja/osoba → prawy spójnik lub `{który, która, które}` →
modalne → nagłówek/końcówka → prawy przyimek → domyślne 0,6; następnie odległe `się` poza INT/osobą.
Domyślne 0,6 oznacza brak dowodu, nie pewność cięcia wewnątrz grupy. Neutralnych cięć
między rozpoznanymi grupami nie karzemy 0,6 (uwaga argon); nieznanych nie zerujemy.
**Przecinek sam daje `m=1`, SYN=0:** świadoma tania heurystyka spójna z rachunkiem;
nie dowodzi domknięcia wtrącenia. Znana regresja 18 wymaga decyzji właściciela (§5).
Niepewne mapowanie osób: zachować autorskie/translatora granice, `uncertain`, przepuścić pipeline;
rozpoznane przepełnienie raportować. Niepewna relacja językowa stosuje tabelę, nie passthrough.

**Jedna definicja „mieści się”:** każdy wiersz ma `u=W/A ≤ τ`, proponowane **`τ=0,98`**.
Produkcja współdzieli [pomiar §A.3](fuzzy-signs-and-split.md#a3-pomiar-warunek-wstępny): FreeType/Pillow,
prawdziwy font odcinka (`\fn/\fs`, wariant i zakres tagów), advance z `\fscx/\fsp` oraz bbox
powiększony o `\bord/\shad` jako `W`; `A` = szerokość po marginesach w tych samych jednostkach.
libass przez FFmpeg (`scripts/subtitle_quality/render.py`) służy wyłącznie jako wzorzec kalibracji.
Auto-wrap przewidujemy oddzielnie: skorygowany advance > A przy efektywnym wrap innym niż 2
(`\q2`/`WrapStyle 2` wyłącza go); taki wiersz odrzucamy. Cache metryk segmentów: O(b²) na event.
Próg obowiązuje w generatorze, obu grafach ratunkowych i wyborze; `0,98<u≤1` nie spełnia dopasowania.
Zapas 2% jest mniejszy od dopuszczonego limitu 3% dla p90 błędu w siostrzanym §D (nie wyniku kalibracji);
nie gwarantuje dopasowania. Kalibracja błędu i auto-wrap dla profilu poprzedza wdrożenie (§5, pyt. 6).
Filtr jest nadrzędny wobec sensu, także w paśmie zapasu — do zatwierdzenia przez właściciela.
W galerii pasmo zapasu: 22 C / 32 C (`u≈0,995`) i 33 A (`≈0,987`);
15 B/C (`≈0,979`) tuż poniżej; 07 D (`≈1,003`) powyżej nominalnego A, choć widać je w kadrze.

Bez profilu lub przy nieznanych/animowanych metrykach: cały event `unmeasured`.
Zastąpić W liczbą grafemów ze spacjami L, A przez `ceil(1,3·L_ref)`; ten sam próg τ.
Dla L_ref=42 dopuszczamy najwyżej 53 grafemy/wiersz. To **domniemany filtr**, bez gwarancji
pikselowej; mnożnik 1,3 i τ wymagają akceptacji. Nie wolno uznać braku pomiaru za W=0.

## 3. Zmienne i jedna agregacja

`R(x;a,b)=clamp((x−a)/(b−a),0,1)`. Powtórzenia szkody agregujemy maksimum.
`L_ref=max_chars_per_line` (42), `N_ref=max_lines_per_event` (2); n = liczba wierszy eventu,
p = liczba wypowiedzi. N_ref jest miękkim centrum, także N_ref=1; przy pomiarze
`max_chars_per_line` nie wpływa na wynik. L_ref działa tylko w `unmeasured`, także w jego filtrze.
Żadne z tych ustawień nie ogranicza budżetu generatora.

| Reguła | Aktywacja α (maksimum po wierszach/granicach) | Singleton c |
| --- | --- | --- |
| SYN — sens | Wartości i kolejność z §2 dla wybranych cięć; brak cięć = 0 | 0,95 |
| INT — ukryta granica | `m·R(u;0,60;0,90)` wewnątrz wiersza; bez pomiaru `m·R(L/L_ref;0,9;1,3)` | 0,45 |
| TIGHT — ciasnota | `R(u;0,88;0,98)`; bez pomiaru wyłącznie `R(max(0,L/L_ref−1);0;0,5)` | 0,25 |
| FRAG — fragmentacja | Maksimum: przecięta wypowiedź poza mocną granicą `1−R(U;0,75;0,95)`; niesamodzielna sierota `1−R(liczba_słów;1;3)` | 0,45 |
| COUNT — liczba wierszy | `R(max(0,n−max(N_ref,p));0;N_ref)` | 0,45 |
| AUTH — zmiana autorstwa | `1−zachowane/max(źródłowe,kandydata)` dla jawnych granic polskiego autora; inaczej 0 | 0,25 |
| SHAPE — kształt | `R((W_góra−W_dół)/max(W_góra,W_dół);0;0,5)`; bez pomiaru L | 0,15 |

`m=1` wyłącznie, gdy przynajmniej jedna wykryta mocna granica pozostaje **wewnątrz**
wiersza. SHAPE to maksimum po wszystkich sąsiednich parach w obrębie tej samej wypowiedzi,
również przy ≥3 wierszach; pomija pary rozdzielone zmianą osoby. Bez par = 0.
FRAG liczy `U` **per wypowiedź**, jako sumę W jej wierszy / A (przybliżenie bez usuniętych
spacji); bez pomiaru suma L/L_ref. Potem maksimum po wypowiedziach, nigdy suma całego eventu.
Obowiązkowa zmiana osoby nie jest fragmentacją. Sieroty oceniamy tylko wewnątrz rozbitej
wypowiedzi; liczymy tokeny z literą/cyfrą, bez samotnego myślnika. Całe zdanie nie jest sierotą:
musi zaczynać się na początku wypowiedzi lub po pełnym końcu zdania i samo nim kończyć.
AUTH liczy zapisane granice, nie zawinięcia renderera; puste oba zbiory = 0. W galerii
pochodzenie daje `source=reference.pl.ass` lub jawne granice syntetycznego wejścia, nie ID przypadku.

Wynik **`Q=1−∏(1−c_iα_i)`** (noisy-OR) minimalizujemy dla wszystkich siedmiu szkód.
Silna szkoda sensu waży więcej niż geometria, lecz nie tworzy absolutnego porządku.
Wyprowadzenie Sugeno i monotoniczność: [notatki](../../../workspace/.quality/experiments/fuzzy-spec/notes.md).
CPS pozostaje diagnostyką. Pomiar i kanał znakowy nigdy nie karzą równocześnie tego samego eventu.

## 4. Generator, wybór i ratunek

1. Rozpatrzyć wszystkie kombinacje 0–3 legalnych cięć geometrycznych, obowiązkowe granice
   osób poza budżetem, oraz legalny układ źródłowy. Koszt `Σ C(b,k), k=0..3`; bez wiązki.
2. Z mieszczących się według §2 wybrać najmniejsze Q. Jeśli brak, zbudować graf legalnych
   granic: krawędź istnieje tylko dla wiersza spełniającego **ten sam `u≤τ`**.
   Ratunek: najmniej wierszy, potem najmniejsze Q — enumeracja ścieżek o k wierszach, ograniczona przez C(b,k−1), bez obietnicy minimum poza przeszukaną przestrzenią.
3. Gdy cały graf chroniący frazy nie ma ścieżki, poluzować **wszystkie ochrony fraz** z §2
   do SYN=1 (także nazwę/frazy z list), zostawiając nienaruszalne warunki i osoby.
   Ponowić pełną enumerację i w razie potrzeby graf z identycznym progiem; `relaxed_phrases`.
4. Dopiero brak ścieżki także wtedy: zachować tekst i autorskie granice, `overflow_unavoidable`,
   przepuścić pipeline. W `unmeasured` oznacza to niewykonalność **filtra znakowego**, nie dowód pikselowy.

Identyczne minima Q: zachowanie legalnego źródła, mniej cięć, kolejność indeksów.
Nie obiecywać minimum Q poza przeszukaną przestrzenią. 28 ma ratunkowe `Jan / Kowalski`;
31 to jeden za szeroki wyraz bez legalnego separatora, więc pozostaje przepełnieniem.
Zmiana fontu/okna/profilu wymaga ponownego dopasowania; SRT wymaga znanego profilu mpv.

## 5. Kontrola i decyzje właściciela

Rachunek detektorów na zmierzonych wierszach, **bez ręcznych etykiet językowych**;
Q przed filtrem, `×` = odrzucenie. [Wszystkie wyniki](../../../workspace/.quality/experiments/fuzzy-spec/cases/model-v31.md).
Starsze C oceniono po odczytanych widokach; produkcja musi zapisać ich granice jawnie.

| Przypadek | Aktywne reguły → Q | Minimum galerii |
| --- | --- | --- |
| 02 | B: brak → 0; C: TIGHT → 0,2500 × | B (=A) |
| 03 | A: INT/SHAPE → 0,3026; B: TIGHT → 0,0875; C: SYN/INT → 0,8612; D: SYN/COUNT/SHAPE → 0,6738 | B |
| 07 | A/C: SYN/INT/SHAPE → 0,7007; B: COUNT/SHAPE → 0,2997; D: INT/TIGHT → 0,5875 × | B |
| 16 | B: INT → 0,1918; C: INT/TIGHT → 0,5875 ×; D zmienia `\q` | B (=A) |
| 17 | B: brak → 0; C: INT/TIGHT → 0,5472 | B (=A) |
| 20 | B: SHAPE → 0,1500; C: SYN/AUTH → 0,8912 | B (=A) |
| 22 | B: brak → 0; C: INT/TIGHT → 0,5875 × zapas | B (=A) |

08 B nadal wygrywa (0,0924 < A 0,5700): `z Azumą` jest początkiem grupy, nie wyjątkiem.
18 zmienia minimum na A (0,2536 < B 0,3028); powierzchniowy przecinek nie rozpoznaje wtrącenia.
28 D: Q=0,9725, u≈0,793 — wybór ratunkowy mimo szkody nazwy i sierot; 31 bez dopasowania.
Minima dotychczasowych 34 przypadków bez zmian względem v3; rekomendacja trafia w minimum w 34/36.
Nowe rendery: 35 B (=A), Q=0,0327 — prawy spójnik/homonim; 36 B, Q=0 — `martwię się o ciebie, bo…`.
Wyjątki pozostają: 18 oraz nierozwiązywalny 31. Mini-tabela: wszystkie 7 wierszy potwierdzone.

1. **03 B/D:** zatwierdzić B (dłuższy dół) zamiast trzech fraz? Idiom nie jest wykrywany; B wygrywa innymi sygnałami.
2. **07 B/D:** zaakceptować trzy wiersze przy górze? D widoczne w kadrze, ale poza przyjętym obszarem i progiem.
3. **33 B/D:** zaakceptować B z miękką odległą ochroną `się`, zamiast uciętego D?
4. **28:** zatwierdzić ostateczne zmiękczenie ochron fraz i widoczne `Jan / Kowalski` w D?
5. **31:** zaakceptować zachowanie tekstu z `overflow_unavoidable`, gdy za szeroki jest sam wyraz?
6. **Zapas/profil:** zatwierdzić pomiar FreeType/Pillow z obrysem/cieniem i τ=0,98 po kalibracji wobec libass? Zapas 2% < dopuszczony limit 3% dla p90 nie daje gwarancji; sprawdzić błąd, auto-wrap i ASS/SRT w mpv (15, 07, pasmo zapasu).
7. **Bez pomiaru:** zatwierdzić domniemany filtr `L≤0,98·ceil(1,3·L_ref)` zamiast wygranej 80-znakowego wiersza?
8. **18 A/B:** zaakceptować A przy tej heurystyce, czy zamówić ogólną regułę domknięcia wtrącenia z osobną walidacją? Nie dodawać wyjątku dla `wersja`/`Nanaki`.
9. **Limit znaków:** zaakceptować brak wpływu `max_chars_per_line` przy pomiarze i jego użycie wyłącznie w `unmeasured`?

Przed implementacją (zmienione aneksem v4 i decyzją właściciela 18.10): akceptacja trzech recenzentów, wartości domyślne decyzji z aneksu pkt 8, pełny generator, tagi,
idempotencja i wspólna ścieżka ASS/SRT. Galeria jest lokalna/gitignored, nie dołączona do klonu Git.

---
kind: specification
status: v1 (do przeglądu)
updated: 2026-10-19
supersedes: fuzzy-line-breaks.md (dla dialogów)
---

# Łamanie polskich dialogów na wiersze — specyfikacja v1

Właściciel 18.10 odrzucił przepisany algorytm z gałęzi `work/quality/16-line-breaks` jako błędny i przekombinowany. Wskazał stary algorytm z `work/quality/08-fuzzy-quality` (replay `u6-font`) jako lepszy i działający. Ta specyfikacja zastępuje `fuzzy-line-breaks.md` w części o dialogach. Opiera się na trzech niezależnych badaniach z 18–19.10:

- [research/line-breaking-astra.md](research/line-breaking-astra.md) — literatura, narzędzia NLP, próba obalenia rankingu;
- [research/line-breaking-opus55.md](research/line-breaking-opus55.md) — literatura, pomiar sześciu narzędzi, korpus profesjonalnych polskich napisów (Netflix, Amazon, Crunchyroll), prototyp jednej funkcji kosztu;
- [research/line-breaking-inventory.md](research/line-breaking-inventory.md) — co już mamy w kodzie i dokumentach, stary a odrzucony algorytm, MangaShift.

Oznaczenia: **[B]** wynik badań lub pomiaru (z odnośnikiem do raportu), **[W]** wniosek orkiestratora, **[K]** stała do kalibracji według §8, **[D]** decyzja właściciela.

## 1. Cel i zakres

1. Polska kwestia dialogowa dostaje układ, który człowiek uzna za naturalny: jeden wiersz, gdy to wystarcza, dwa, gdy pomagają, trzy tylko wyjątkowo. Podział wypada tam, gdzie kończy się fraza.
2. Decyzję podejmuje **jedna reguła** stosowana tak samo do każdej kwestii: wybór najtańszego układu w przestrzeni wszystkich dopuszczalnych układów. Bez osobnych gałęzi „za długie, więc tnij”, bez łatek pod pojedyncze przykłady.
3. Wartości są rozmyte. 42 znaki to punkt odniesienia i miękkie maksimum, które wolno przekroczyć, gdy cięcie byłoby gorsze. Nie ma progów „co do znaku”.
4. Zakres: dialogi (`layout_dialogue`). Szyldy zachowują kontrakty `split_lines(event, text, count, profile)` i `split_for_layout(...)`, ale korzystają z tej samej analizy przerw (§3). Dzielenie wyrazów (MangaShift, ciasne szyldy) jest poza zakresem; kontrakt analizy ma tylko nie zamykać tej drogi.

## 2. Zasady układania polskiego dialogu

### 2.1 Co mówią badania [B]

- Cięcie zgodne ze składnią jest wyraźnie preferowane przez widzów (Gerber-Morón i Szarkowska 2018: 64–95% zależnie od kategorii; „zdanie | zdanie” 95%). Cięcie niezgodne podnosi deklarowany wysiłek, frustrację i liczbę powrotów oka do napisu (0,37 wobec 0,25). Rozumienie się nie zmienia. Wniosek: sens cięcia to najważniejsze kryterium, ale jako koszt, nie jako absolutne pierwszeństwo.
- 42 to norma dostawcy (Netflix PL), a nie wynik eksperymentu. Polska fundacja dostępności (FKBB 2019) podaje 40, BBC 37 (techniczny limit teletekstu), Karamitroglou ok. 35. Nie istnieje badanie „ten sam tekst w jednym długim wierszu kontra w dwóch krótkich” dla napisów.
- Kształt nie jest stałą regułą. Ludzie wybierają według sensu, nie kształtu. W 7083 profesjonalnych polskich napisach górny wiersz bywa krótszy i dłuższy prawie tak samo często (846 do 805). Krótki górny wiersz jest jednak akceptowany rzadziej niż krótki dolny.
- Trzy wiersze wydłużają czytanie i zwiększają wysiłek, choć nie obniżają rozumienia (Szarkowska i Gerber-Morón 2018). Wytyczne dopuszczają je wyjątkowo. W korpusie profesjonalnym nie ma ani jednego trzywierszowego napisu.
- Drugi wiersz zasłania więcej obrazu. BBC: wiersze „long and thin” zwykle mniej przeszkadzają niż „short and fat”. Jeden wiersz jest więc pełnoprawną opcją, a nie porażką.

### 2.2 Hierarchia granic (od najlepszej) [B]

Akceptowalność `A` z korpusu Netflix + Amazon (593 dwuwierszowe kwestie): jak często profesjonalista tnie w danej klasie granicy względem liczby okazji. 1 oznacza najlepszą, 0 nigdy.

| Klasa granicy | `A` (start) | Przykład |
| --- | --- | --- |
| koniec zdania | 1,00 | „Wrócę jutro. / Zaczekaj na mnie.” |
| przecinek, średnik, dwukropek | 0,94 | „Martwię się o ciebie, / bo od wczoraj…” |
| wielokropek | 0,74 | „Ja… / nie wiem, czy potrafię.” |
| podmiot / orzeczenie, inna granica dużych części zdania | 0,50 | „Ludzie zamieszkujący te ziemie / popełnili straszliwe grzechy.” |
| rzeczownik / dopełniacz | 0,40 | „klejnoty / Yamamoto” |
| wewnątrz nazwy własnej, wyrażenia wielowyrazowego | 0,39 | „Futari / Shizuka” |
| myślnik wewnątrz zdania | 0,34 | patrz §7, wtrącenia |
| czasownik / dopełnienie tuż obok | 0,26 | „miałeś / zamiar” |
| posiłkowy / główny | 0,24 | „będziesz / się bawił” |
| przymiotnik / rzeczownik | 0,16 | „wpływ / psychiczny” |
| po słowie jednoliterowym; rozcięta fraza dwuwyrazowa | 0,12 | „w / domu” |
| spójnik na końcu wiersza, po przyimku, oderwane „nie”, oderwane „się” | 0,00 | „że / …”, „z / balastem”, „nie / chcę”, „się / zakocha” |

Tabela `A` jest wyliczona z danych, nie strojona ręcznie. Liczby to punkt startowy; ostateczną tabelę wylicza skrypt kalibracji z korpusu (§8).

### 2.3 Co zawsze razem (unikane za wszelką cenę, `A` ≈ 0)

Przyimek z tym, czym rządzi; „nie” z czasownikiem; „się” z czasownikiem, któremu towarzyszy, także w szyku swobodnym; jednoliterowe w, z, o, u, i, a z następnym słowem; spójnik z tym, co wprowadza (cięcie przed spójnikiem, nie po nim); imię z nazwiskiem i honoryfikatorem; liczba z jednostką lub rzeczownikiem („1,4 miliarda”, „25 kg”); skrót z tym, co określa („godz. 17.30”, „dr Kowalski”); frazeologizm („raz na zawsze”, „po prostu”, „w ogóle”).

To nie są zakazy, tylko bardzo wysoki koszt. Gdy żaden inny układ nie jest dopuszczalny, wygrywa najmniejsze zło i zdarzenie trafia do raportu (§5.4).

### 2.4 Zdania i asymetria [B] [W]

- Cięcie po kropce jest najmocniejszą granicą. Długi górny i krótki dolny wiersz nie są same w sobie błędem.
- Profesjonaliści biorą cięcie po kropce w 89–100% przy nierównowadze do 0,5, w 38% przy 0,5–0,6, w 10% przy 0,6–0,7 i nigdy powyżej 0,7 (nierównowaga = |L − P| / (L + P)). Po przecinku: od 94% przy małej nierównowadze do 28% przy 0,4–0,5.
- Gdy pierwsze zdanie jest długie, a drugie krótkie, zwykle wygrywa cięcie po kropce z dłuższym górnym wierszem. Cięcie wewnątrz pierwszego zdania wygrywa dopiero przy skrajnej nierównowadze albo gdy cięcie po kropce się nie mieści. Wynika to z tej samej funkcji kosztu (§4): szkoda cięcia w zdaniu wobec kary za nierównowagę.
- Gdy pierwsze zdanie jest krótkie, a drugie długie, obowiązuje ta sama reguła. Krótki górny wiersz kosztuje trochę więcej (kara za sierotę przy jednym słowie, mocniejsza kara za „wysoką czapkę”).
- Trzy krótkie zdania nie dostają trzech wierszy dlatego, że są trzy kropki. Grupują się w jeden albo dwa wiersze.

## 3. Warstwa analizy: przerwy i ich siła

Moduł `anishift/text/gaps.py` (nazwa robocza). Nie importuje `anishift.services`, nie ma przełączników domenowych (`anishift/text/AGENTS.md`), zależy od `boundaries.py` i `graphemes.py`. Wejście: słowa widocznego tekstu bez tagów ASS i bez znaczników `<sN>` (spacje twarde `\h`/NBSP nie są przerwami). Wyjście: rekord dla każdej przerwy między sąsiednimi słowami.

```python
@dataclass(frozen=True, slots=True)
class Gap:
    """Evidence for a line break between two neighbouring words."""

    kind: GapKind  # boundary class from the table in §2.2
    strength: float  # acceptability A of the class, 1 best … 0 never
    pause: bool  # the left word ends a sentence or a clause (punctuation)
    turn: bool  # a new speaker starts after the gap
    span: float  # 1 − s/n: how small the smallest phrase joining both words is (0 when unknown)
```

Źródła dowodu, w tej kolejności, bez nowych pojęć:

1. Interpunkcja i skróty z `anishift/text/boundaries.py` (`period_ends_sentence`, `is_false_sentence_break`). Semantykę wielokropka rozstrzyga ta specyfikacja: wielokropek ma własną klasę `ellipsis`, nie jest końcem zdania.
2. Struktura: myślnik dialogowy (`turn`), znak otwierający na końcu lub zamykający na początku wiersza (klasa „nigdy”), granice cudzysłowu i nawiasu.
3. Listy słów ze starego `linebreak.py` (z adnotacjami źródeł Wikisłownika) oraz ogólne klasy z odrzuconego leksykonu: enklityki, liczba przed rzeczownikiem lub jednostką, „się” po czasowniku posiłkowym, odmienione określniki. Bez list pod pojedyncze przykłady (`GENITIVE_HEADS`, `_NOT_ADJECTIVES` i podobne nie wracają).
4. Opcjonalny parser zależnościowy (§6). Może tylko zmienić klasę przerwy na dokładniejszą i ustawić `span`; nigdy nie usuwa ani nie dodaje zakazu z pkt 2. Bez parsera wynik jest deterministyczny i pełny (pkt 1–3).

Jedna funkcja `gaps()` zastępuje dwa rozjechane rankingi starego algorytmu (`_dialogue_*` i `_best_cut`/`_weight`). Szyldy (`split_lines`, `split_for_layout`) liczą swoje proporcje na tych samych przerwach.

## 4. Warstwa wyboru: jedna funkcja kosztu

### 4.1 Kandydaci

Wszystkie układy z 1, 2 i 3 wierszami przy cięciach wyłącznie na przerwach (§3), z wymuszonymi cięciami przed każdym myślnikiem mówcy (`turn`). Przy ≤ 30 słowach to najwyżej 435 układów dwuwierszowych i 4060 trzywierszowych; wyliczenie jest wyczerpujące, bez programowania dynamicznego.

### 4.2 Filtr mieszczenia (twardy)

Układ jest dopuszczalny, gdy każdy wiersz mieści się w dostępnej szerokości zdarzenia:

- zdarzenie zawijane przez libass: emulacja `wrap_text` nie przewiduje zawinięcia, a glify mieszczą się między marginesami (`geometry.measure_text`, `available_width`; zgodność emulacji z libass 5406/5406);
- zdarzenie niezawijane (`\q2`, `WrapStyle 2`, rozpoznane przez efektywny tryb zawijania): dostępna szerokość to szersza z dwóch wartości, czyli miejsce między marginesami albo szerokość najszerszego wiersza źródła, ale nie więcej niż wyśrodkowane 90% `PlayResX`. Polski napis nie wychodzi więc poza ekran bardziej niż angielski;
- bez profilu stylu (SRT bez stylów): miara znakowa z `LayoutLimits.max_chars` jako punktem odniesienia, filtr przy 1,3 × `max_chars` [K];
- metryki animowane (`\t` zmieniające `\fs`, `\fscx`, `\fsp`) albo brak jakiegokolwiek fontu z glifami: tryb znakowy jak wyżej.

Dostępna szerokość ≤ 0 (marginesy zajmują ekran): bez wyjątku, tekst w jednym wierszu i raport `overflow_unavoidable`.

### 4.3 Koszt układu

Dla układu `U` z wierszami `w₁ … wₖ` i cięciami `c₁ … cₖ₋₁`:

```text
znaki(w)  = liczba widocznych grafemów wiersza
u(w)      = zmierzona szerokość wiersza / dostępna szerokość (z §4.2)
DŁUGI(w)  = max(rise(znaki(w); 38; 62), rise(u(w); 0,60; 1,00))          [K]

koszt(U) = λ_k · max_i DŁUGI(wᵢ)                                          λ₁ = 1, λ₂ = λ₃ = 0,3 [K]
         + Σ_cięć [ (1 − A(cⱼ)) + β · span(cⱼ) · [cⱼ bez interpunkcji] ]   β = 0,6 [K]
         + γ · nierównowaga(U)                                              γ = 0,6 [K]
         + δ · liczba_wierszy_jednowyrazowych(U)                            δ = 0,4 [K]
         + ε · [k = 3]                                                      ε = 0,3 [K]

nierównowaga(U) = (max znaki − min znaki) / Σ znaki   (wysoka czapka liczona × 1,25 [K])
wybór = argmin koszt(U); przy remisie mniej wierszy, potem wcześniejsze cięcie
```

`rise(x; a; b)` = 0 dla x ≤ a, liniowo do 1 dla x ≥ b (istniejące `anishift/services/subtitles/fuzzy.py`). Wszystkie składniki są ciągłe, w tej samej skali i żaden sam nie przekracza ok. 1,6.

**Dlaczego dwie miary długości** [W]: znaki mierzą ilość tekstu do przeczytania i nie zależą od fontu; szerokość mierzy drogę oka po ekranie („zamiatanie wzrokiem”). Wiersz jest długi, gdy długi jest w którymkolwiek sensie. Sama szerokość zawiodła z wąską Officiną (60 znaków ≈ 0,8 szerokości, w odrzuconym U5 jeden wiersz); same znaki zawodzą przy szerokich fontach. Rampa znakowa jest zgodna z danymi: właściciel akceptuje pojedyncze wiersze 43–55 znaków (przypadki 04, 13, 14, 24) i odrzuca 60 znaków (galeria `obecny-vs-nowe-lamanie` 02); profesjonaliści przechodzą na dwa wiersze przy 40–44 znakach.

### 4.4 Liczba wierszy

- Jeden i dwa wiersze konkurują wyłącznie kosztem.
- Trzy wiersze wchodzą do porównania tylko wtedy, gdy żaden układ z ≤ 2 wierszami nie przechodzi filtra §4.2, albo gdy kwestia ma trzech mówców (trzy wymuszone cięcia `turn` dają co najmniej trzy wiersze). Uzasadnienie: właściciel ocenił trzy wiersze tam, gdzie mieszczą się dwa, jako przesadę (galeria 20); korpus profesjonalny nie ma trzywierszowych napisów.
- Gdy żaden układ z ≤ 3 wierszami nie przechodzi filtra: najmniej szkodliwy układ trzywierszowy według tego samego kosztu (bez filtra) i raport `overflow_unavoidable`. Więcej niż trzech wierszy nie tworzymy; tekstu nie skracamy.

## 5. Reguły nienaruszalne i raport

1. Tekst, kolejność słów, interpunkcja, grafemy, tagi ASS i znaczniki stylu są identyczne przed i po układzie; zmieniają się tylko podziały `\N`.
2. Słowa nie rozcinamy; `\h`/NBSP nie jest miejscem cięcia.
3. Myślnik mówcy zaczyna wiersz.
4. Raport w `LayoutReport` (istniejące liczniki dialogu) plus flagi `DialogueLayout.flags`: `three_lines`, `overflow_unavoidable`, `unmeasured`, `costly_cut` (wybrany układ zawiera cięcie z `A` < 0,2).

## 6. Parser zależnościowy (opcjonalny dowód)

- Kandydat: `spaCy` 3.8.16 z modelem `pl_core_news_sm` 3.8.0 (koło cp314 dla Windows, model 26 MB, bez PyTorcha, ok. 0,3 s ładowania i 0,5 s na 500 kwestii) [B].
- Wpływ zmierzony: +4,0 pp trafności miejsca cięcia nad samymi listami na Netflix + Amazon (95% CI +1,3…+6,9; opus55), brak przewagi na zaszumionym Crunchyroll i na zewnętrznym dokumencie (astra: 237 wobec 238 na 392). Lepiej trzyma frazy rzeczownikowe („czerwonego wojownika”, „naszą wspólną przyszłość”). Myli obce imiona z podmiotem („woli / Artemis”).
- Stanza (PyTorch) nie daje przewagi poza niepewnością pomiaru, a kosztuje ok. 1 GB instalacji i 1,1–2,6 GB RAM: odrzucona.
- Zasada: parser wchodzi do produkcji tylko wtedy, gdy na zbiorach kontrolnych (§8) poprawia wynik bez regresji w znanych złych cięciach. Ładowany leniwie, raz na proces, w domenie `subtitles`; brak pakietu, brak modelu albo błąd wyrównania tokenów oznacza tryb list z ostrzeżeniem w logu, nigdy błąd przetwarzania.
- Licencja modelu `pl_core_news_*` to GPL-3.0; repozytorium nie ma pliku licencji. Dodanie zależności jest osobnym commitem do decyzji właściciela [D].

## 7. Katalog przypadków brzegowych

Każdy wiersz wynika z reguły §4, chyba że kolumna „Status” mówi inaczej. „Spr.” oznacza przypadek sprawdzony w prototypie badań (identyfikator przypadku z `fuzzy-spec/cases` lub galerii).

| Przypadek | Przykład | Oczekiwany układ | Z czego wynika | Status |
| --- | --- | --- | --- | --- |
| bardzo krótka kwestia | „Uciekaj!” | 1 wiersz | DŁUGI = 0, każde cięcie kosztuje > 0 | spr. c01 |
| tuż pod 42 znakami | „Czy aby na pewno zajmują się tylko masażem?” (43) | 1 wiersz | DŁUGI ≈ 0,2 < najlepsze cięcie | spr. c24 |
| tuż nad 42, dobre cięcie słabe | „Osiągnęliśmy rozejm z Sokołem z klanu Estebanów.” (48) | 1 wiersz | DŁUGI ≈ 0,42 < koszt cięcia + krótkiego wiersza | spr. c13 |
| 50–62 znaki z dobrym cięciem | „Ludzie zamieszkujący te ziemie / popełnili straszliwe grzechy.” | 2 wiersze | DŁUGI 0,5–1,0 > koszt cięcia podmiot/orzeczenie | galeria 02 |
| długi jeden wiersz, wszystkie cięcia złe | „Dlaczego się na mnie z taką złością cały czas patrzysz?” | 1 wiersz, gdy się mieści | cięcia ≥ 0,6, DŁUGI 0,7 | spr. c04 |
| dwa zdania podobnej długości | „Wrócę jutro. Zaczekaj na mnie.” | 1 wiersz, gdy krótkie; inaczej po kropce | koszt cięcia po kropce = 0 | — |
| dwa zdania, pierwsze dłuższe | „Przepraszam. Idź z Midorikawą i resztą. / Baw się dobrze.” | po kropce, górny dłuższy | nierównowaga 0,27 < szkoda cięcia w zdaniu | spr. g20 |
| dwa zdania, pierwsze bardzo krótkie | „Wiem. Zrobiłeś wszystko, o co cię prosiłam.” | 1 wiersz albo „Wiem. Zrobiłeś wszystko, / o co cię prosiłam.” | sierota „Wiem.” +0,4, wysoka czapka | — |
| trzy i więcej krótkich zdań | „Wiem. Rozumiem. Zaczekam.” | 1 wiersz albo 2 po kropce | trzeci wiersz tylko przy braku miejsca | — |
| trzy długie zdania, dwa wiersze się nie mieszczą | c26 | 3 wiersze, po zdaniu w wierszu | §4.4 | spr. c26 |
| dialog dwóch osób | „- Kufer ze złotem? / - Widać? Całe szczęście.” | wiersz na mówcę | cięcie `turn` wymuszone | spr. c05 |
| trzech mówców | „- Idziesz? - Za chwilę. - Poczekajcie!” | 3 wiersze | trzy wymuszone cięcia | spr. c06 |
| mówca z długą kwestią | c27 | 3 wiersze: mówca 1 / mówca 2 / reszta mówcy 2 | wymuszone cięcie + wolne cięcie, gdy 2 się nie mieszczą | spr. c27 |
| więcej niż trzech mówców | 4 krótkie kwestie z myślnikami | 3 wiersze: dwa mówcy w jednym wierszu tam, gdzie najtaniej | najwyżej 3 wiersze; raport | [W] |
| wtrącenie w myślnikach | „Upewniłam się, że wszyscy – a zwłaszcza Przewodniczący – poszli już do domów.” | cięcie przed wtrąceniem albo po nim, nie w środku; 2 wiersze, gdy się mieszczą | klasa myślnika wtrącenia = klasa przecinka; wnętrze wtrącenia = klasa frazy | [D] c07 (właściciel wybrał 3 wiersze) |
| nawias | „Znam go (to mój brat) od lat.” | cięcie przed nawiasem albo po nim | znak otwierający na końcu / zamykający na początku = „nigdy” | — |
| tytuł w cudzysłowie | „A co w kolejnym odcinku „Grand Blue Dreaming”?” | „A co w kolejnym odcinku / „Grand Blue Dreaming”?” albo 1 wiersz | cudzysłów otwierający to granica frazy; wnętrze tytułu = nazwa wielowyrazowa | spr. g29 |
| imię i nazwisko | „Jan Kowalski czeka na dworcu.” | razem | klasa nazwy (0,39) + mały `span` | spr. c09 |
| honoryfikator | „Yamamoto-san”, „Kato-senpai” | jedno słowo | słowa nie rozcinamy | reguła §5 |
| wyliczenie nazw | „z Azumą, Satou i Watanabe” | razem, jeśli się da | przecinek wyliczenia = 0,5 [K] | c08 |
| liczba z rzeczownikiem | „1,4 miliarda ludzi” | razem | klasa liczby ≈ 0 | c11 |
| jednostka, data, godzina | „20 kg”, „19 października o 17:30”, „godz. 17.30” | razem | `\h` nie jest przerwą; skrót + liczba ≈ 0 | c23, c10 |
| skróty z kropką | „np. jutro”, „dr Kowalski”, „tzw. problem” | kropka skrótu nie jest końcem zdania | `is_false_sentence_break` | — |
| wielokropek na początku | „…nie wiem, czy wrócę.” | wielokropek przy swoim słowie | słowa nie rozcinamy | — |
| wielokropek w środku | „Ja… nie wiem, czy potrafię.” | cięcie po wielokropku dopuszczalne | klasa `ellipsis` 0,74 | spr. c30 |
| „?!” i „!!” | „Naprawdę?! Nie wierzę!” | znaki przy słowie; po nich granica zdania | koniec zdania | — |
| wykrzyknienie z przecinkiem na początku | „O, naprawdę tak myślisz?” | 1 wiersz albo cięcie dalej, nie „O, / naprawdę…” | wiersz jednowyrazowy +0,4 i krótka kwestia | lekcja U5 |
| wyrazy obce, łacina, francuski | „prima materii”, „déjà vu” | razem | parser: `flat`/`fixed`; bez parsera: obce słowa z wielkiej litery lub kursywą jako jedna fraza [W] | galeria 10 |
| bardzo długie słowo | 115 znaków bez spacji | 1 wiersz, raport overflow | brak kandydatów | c31 |
| kwestia bez spacji | „…” | jak wyżej | — | — |
| „się” po czasowniku | „będziesz się bawił” | „się” przy czasowniku, nie „się / bawił” | „się” po posiłkowym = klasa „nigdy” | c15 |
| „się” przed czasownikiem | „Kto pierwszy się zakocha” | nie „się / zakocha” | oderwane „się” = 0 | galeria 20 (U5) |
| „się” odległe | „Dlaczego się na mnie z taką złością patrzysz?” | wolno ciąć między frazami pośrednimi | koszt maleje z odległością (parser) / lista bez kary dla odległego | c04 |
| jednoliterowe na granicy | „w”, „z”, „i”, „a” | zawsze z następnym słowem | ≈ 0 (przyimek) lub 0,12 | c02 |
| samodzielne jednoliterowe | „O!”, „A!” | wolno zakończyć nim wiersz | koniec zdania | — |
| przeczenie | „nie chciałem” | „nie” przy czasowniku | oderwane „nie” = 0 | c14 |
| „nie” jako zaimek | „na nie” | zwykła granica frazy | lista odróżnia „na nie” | — |
| spójniki i, a, ale, że, bo, który | „Martwię się o ciebie, bo od wczoraj nie odpowiadasz.” | cięcie przed spójnikiem | spójnik na końcu = 0 | c36, c39 |
| frazeologizm | „raz na zawsze”, „po prostu”, „w ogóle” | razem; granica po całym zwrocie dozwolona | klasa frazy wielowyrazowej | — |
| kursywa / wyróżnienie | „{\i1}Gdyby…{\i0}błagała{\i1}…” | układ jak bez znaczników; znaczniki wracają na swoje słowa | decyzja na tekście bez `<sN>`, potem `restore_markers` | test z rundy U5 zachowany |
| tagi ASS w środku | `{\fs36\fscx110}` | pomiar z tagami; cięcie tylko w widocznej spacji | `measure_text` mierzy z tagami | c34 |
| nie mieści się w dwóch | c33 | 3 wiersze | §4.4 | c33 |
| nie mieści się w trzech | tekst > 3 szerokości | najtańsze 3 wiersze + raport | §4.4 | [D] skracanie przekładu |
| `\q2` z szerokimi marginesami | kaguya | szerokość wg §4.2 | — | galeria 20 |
| wąski ekran / wysokie skalowanie | `\fscx` 150 | pomiar ze skalą | `measure_text` | — |
| SRT bez stylów | plik SRT | tryb znakowy, ta sama funkcja kosztu | §4.2 | — |
| piosenki, szyldy, rysunki | — | poza dialogami: `split_for_layout`, `fit_signs` | zakres | — |
| szyld-lista (wiele wierszy źródła, przekład bez struktury) | ranking kaguya | poza tą specyfikacją: zasada dla szyldów w aneksie U4 | lekcja U4 | do aneksu szyldów |

## 8. Kalibracja, ocena i bramki akceptacji

### 8.1 Zbiory

| Zbiór | Wielkość | Rola |
| --- | --- | --- |
| profesjonalne polskie napisy z MKV w `workspace` (Netflix 5, Amazon 6, Crunchyroll 11; `experiments/lb-research/opus55/pl-subs/`) | 7083 zdarzeń, 593 dwuwierszowe NF+AMZN, 1075 CR | tabela `A` (tylko NF+AMZN), kalibracja stałych, walidacja z pominięciem całej serii |
| Shisha, `certain-dark-item` 01–02 | 64 dwuwierszowe + 780 jednowierszowych | ludzka kontrola anime |
| zewnętrzny SRT „Steal This Film II” | 392 dwuwierszowe | kontrola spoza anime |
| zbiór właściciela: przypadki 01–39 (`fuzzy-spec/cases`, warianty `recommendation_v2`) + decyzje z galerii + znane złe cięcia | 66 | zgodność z gustem; każda nowa decyzja właściciela dopisywana |
| korpus replay (37 par, 14 677 zdarzeń dialogu) | — | statystyki klas cięć, liczba wierszy, czas |

### 8.2 Procedura

1. Tabela `A` wyliczona skryptem z NF+AMZN (częstość cięcia w klasie / liczba okazji), z przypisaniem klas tym samym kodem `gaps()`, który działa w produkcji.
2. Stałe [K] (rampy DŁUGI, λ, β, γ, δ, ε, mnożnik czapki) dobierane w siatce na zbiorze właściciela i NF+AMZN, z walidacją z pominięciem całej serii (NF+AMZN) i pojedynczego przypadku (zbiór właściciela). Prawdziwy pomiar fontu (nie szacunek pikseli na znak).
3. Dwa warianty mierzone tym samym kodem: listy bez parsera i listy + `pl_core_news_sm`. Parser zostaje tylko przy poprawie bez regresji (§8.3).
4. Wrażliwość: wynik nie może się materialnie zmienić przy zmianie każdej stałej o ±10%.

### 8.3 Bramki

1. Reguły §5 na wszystkich zbiorach: zero zmian tekstu, zgubionych tagów, rozciętych słów.
2. Zbiór właściciela (walidacja z pominięciem przypadku): co najmniej 54/66 (prototyp badań), stary algorytm ma 44/66; zero powtórzeń znanych złych cięć.
3. NF+AMZN trafność miejsca cięcia: co najmniej 80% (prototyp 81,1%).
4. Korpus replay: pojedynczy wiersz > 55 znaków lub u > 0,9 w ≤ 1% kwestii jednowierszowych; klasy złych cięć nie częstsze niż u starego algorytmu (po przyimku ≤ 0,1%, oderwane „się” ≤ 0,8%, przymiotnik / rzeczownik ≤ 2,1%); trzy wiersze tylko z przyczyn §4.4.
5. Czas: ułożenie 500 kwestii ≤ 10 s z pierwszym ładowaniem modelu.
6. Galeria przed/po z czcionką właściciela po obu stronach (`compare --font`), obejrzana przez orkiestratora obraz po obrazie, potem właściciel.

## 9. Integracja i kontrakty

- `layout_translated(...)`, `layout_dialogue(event, text, profile, limits) -> DialogueLayout`, `split_lines(event, text, count, profile)`, `split_for_layout(...)`: sygnatury bez zmian. W `layout_dialogue` rekurencyjne `_split`/`_dialogue_cut` ustępuje `gaps()` + wyborowi z §4; `profile` zaczyna służyć pomiarowi.
- `LayoutLimits(max_chars, max_lines)`: `max_chars` zmienia znaczenie z limitu na punkt odniesienia rampy znakowej (rampa DŁUGI przesuwa się z ustawieniem: 38 i 62 przy 42), `max_lines` (domyślnie 2) ogranicza zwykłe układy; trzeci wiersz tylko z przyczyn §4.4, nigdy więcej niż 3. Ustawienia w panelu zostają.
- Testy, które kodują twardy limit 42 znaków (`test_subtitles_linebreak.py:87-91, 225-229`), zmieniają oczekiwania zgodnie z §4; pozostałe testy starego kontraktu (zakazy, mówcy, frazy, skróty, NBSP, kolejność słów) zostają.
- Infrastruktura do zachowania z odrzuconej gałęzi (sprawdzona): rozpoznanie efektywnego trybu zawijania (`wraps_automatically`), obsługa braku miejsca między marginesami, tryb znakowy dla metryk animowanych, test znaczników „błagała”.
- Chunkery tłumaczenia i TTS bez zmian (mają twarde limity żądań).
- Logowanie: jedna linia podsumowania na plik (istniejący `LayoutReport`), bez tekstów kwestii.

## 10. Decyzje dla właściciela

1. **Licencja modelu spaCy (GPL-3.0)**, jeśli parser przejdzie bramki §8.3. Bez niego algorytm działa na listach (badania: o 1–4 pp gorzej na profesjonalnych napisach).
2. **Przypadek 07 (wtrącenie w myślnikach):** wybrałeś trzy wiersze, choć mieszczą się dwa, a jednocześnie trzy wiersze tam, gdzie mieszczą się dwa, oceniasz jako przesadę. Specyfikacja przyjmuje dwa wiersze z cięciem przed wtrąceniem albo po nim. Do potwierdzenia na galerii.
3. **Długi jeden wiersz a dobre cięcie (11: u = 0,90; 15: u = 0,98):** twoje wybory porównywały jeden wiersz tylko ze złym cięciem („1,4 / miliarda”, „się / bawił”). Reguła wybierze dwa wiersze z dobrym cięciem. Do potwierdzenia na galerii.
4. **Dzielenie wyrazów w szyldach** (z myślą o MangaShift): poza zakresem; reguła nienaruszalna 2.1.1 `visual-quality.md` zostaje.

## 11. Poza zakresem

Wskazówki granic od tłumacza (LLM): odłożone do czasu, gdy wariant lokalny osiągnie plateau, a błędy będą frazowe; wymagałyby zmiany kontraktu tłumaczenia i płatnych przebiegów. Implementacja dla MangaShift (front, `pretext`), dzielenie wyrazów (`pyphen` z filtrami) i zasada dla szyldów-list (aneks U4).

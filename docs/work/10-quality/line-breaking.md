---
kind: specification
status: v1.1 (po przeglądzie astra, sol6, opus55)
updated: 2026-10-19
supersedes: fuzzy-line-breaks.md (dla dialogów)
---

# Łamanie polskich dialogów na wiersze — specyfikacja v1.1

Właściciel 18.10 odrzucił przepisany algorytm z gałęzi `work/quality/16-line-breaks` jako błędny i przekombinowany. Wskazał stary algorytm z `work/quality/08-fuzzy-quality` (replay `u6-font`) jako lepszy i działający. Ta specyfikacja zastępuje `fuzzy-line-breaks.md` w części o dialogach. Opiera się na trzech niezależnych badaniach z 18–19.10:

- [research/line-breaking-astra.md](research/line-breaking-astra.md) — literatura, narzędzia NLP, próba obalenia rankingu;
- [research/line-breaking-opus55.md](research/line-breaking-opus55.md) — literatura, pomiar sześciu narzędzi, korpus profesjonalnych polskich napisów (Netflix, Amazon, Crunchyroll), prototyp jednej funkcji kosztu;
- [research/line-breaking-inventory.md](research/line-breaking-inventory.md) — co już mamy w kodzie i dokumentach, stary a odrzucony algorytm, MangaShift.

v1.1 zamyka przegląd v1:
- trzy poziomy reguł zamiast jednej skończonej kary (§3);
- koszt każdego dodatkowego wiersza (§5.3);
- ratunek minimalizujący przepełnienie (§5.4);
- definicja zmiany mówcy i wtrącenia (§4.2);
- jedna tabela klas ze źródłem każdej wartości (§4.3);
- walidacja bez przecieku i mierzalne bramki (§9);
- semantyka `max_lines` (§10);
- uzupełniony katalog (§8).

Oznaczenia: **[B]** wynik badań lub pomiaru (z odnośnikiem), **[W]** wniosek orkiestratora, **[K]** stała dobierana według §9, **[D]** decyzja właściciela.

## 1. Cel i zakres

1. Polska kwestia dialogowa dostaje układ, który człowiek uzna za naturalny: jeden wiersz, gdy to wystarcza, dwa, gdy pomagają, trzy tylko wyjątkowo. Podział wypada tam, gdzie kończy się fraza.
2. Decyzję podejmuje **jedna reguła** stosowana tak samo do każdej kwestii: najpierw reguły nienaruszalne i unikane za wszelką cenę (§3), potem wybór najtańszego układu (§5). Bez gałęzi „za długie, więc tnij” i bez łatek pod pojedyncze przykłady.
3. Wartości są rozmyte. 42 znaki to punkt odniesienia i miękkie maksimum, które wolno przekroczyć, gdy cięcie byłoby gorsze. Nie ma progów jakości „co do znaku”; jedyne ostre granice to fizyczne mieszczenie i reguły nienaruszalne.
4. Zakres: dialogi (`layout_dialogue`). Szyldy zachowują kontrakty `split_lines(event, text, count, profile)` i `split_for_layout(...)`, ale korzystają z tej samej analizy przerw (§4). Dzielenie wyrazów (MangaShift, ciasne szyldy) jest poza zakresem; kontrakt analizy nie zamyka tej drogi.

## 2. Zasady układania polskiego dialogu

### 2.1 Co mówią badania [B]

- **Cięcie zgodne ze składnią** jest wyraźnie preferowane przez widzów (Gerber-Morón i Szarkowska 2018: 64–95% zależnie od kategorii; „zdanie | zdanie” 95%). Cięcie niezgodne podnosi deklarowany wysiłek, frustrację i liczbę powrotów oka do napisu (0,37 wobec 0,25). Rozumienie się nie zmienia.
- **42 znaki** to norma dostawcy (Netflix PL), nie wynik eksperymentu. FKBB 2019 podaje 40, BBC 37 (limit teletekstu), Karamitroglou ok. 35. Nie istnieje badanie „ten sam tekst w jednym długim wierszu kontra w dwóch krótkich” dla napisów.
- **Kształt** nie jest stałą regułą: ludzie wybierają według sensu. W 7083 profesjonalnych polskich napisach górny wiersz bywa krótszy i dłuższy prawie tak samo często (846 do 805). Krótki górny wiersz jest jednak akceptowany rzadziej niż krótki dolny.
- **Trzy wiersze** wydłużają czytanie i zwiększają wysiłek, bez spadku rozumienia (Szarkowska i Gerber-Morón 2018). Wytyczne dopuszczają je wyjątkowo. W korpusie profesjonalnym nie ma ani jednego trzywierszowego napisu.
- **Drugi wiersz zasłania więcej obrazu.** BBC: wiersze „long and thin” zwykle mniej przeszkadzają niż „short and fat”. Jeden wiersz jest pełnoprawną opcją, a dodatkowy wiersz ma swój koszt.

### 2.2 Zdania i asymetria [B] [W]

- Cięcie po kropce jest najmocniejszą granicą. Długi górny i krótki dolny wiersz nie są same w sobie błędem.
- Profesjonaliści biorą cięcie po kropce w 89–100% przypadków przy nierównowadze do 0,5, w 38% przy 0,5–0,6, w 10% przy 0,6–0,7 i nigdy powyżej 0,7. Po przecinku: od 94% przy małej nierównowadze do 28% przy 0,4–0,5. Nierównowaga = (dłuższy − krótszy) / suma, w znakach.
- Gdy pierwsze zdanie jest długie, a drugie krótkie, zwykle wygrywa cięcie po kropce z dłuższym górnym wierszem. Cięcie wewnątrz pierwszego zdania wygrywa dopiero przy skrajnej nierównowadze albo gdy cięcie po kropce się nie mieści. Wynika to z §5: koszt cięcia w zdaniu wobec kary za nierównowagę.
- Krótkie pierwsze zdanie i długie drugie: ta sama reguła. Jednowyrazowy górny wiersz kosztuje dodatkowo (§5.3, `δ`).
- Trzy krótkie zdania nie dostają trzech wierszy dlatego, że są trzy kropki. Grupują się w jeden albo dwa wiersze, bo każdy dodatkowy wiersz kosztuje (`ζ`).

## 3. Trzy poziomy reguł

Zgodnie z `visual-quality.md` (nienaruszalne / unikane za wszelką cenę / ważone):

1. **Nienaruszalne** (filtr kandydatów, nigdy nie łamane):
   - tekst, kolejność słów, interpunkcja, grafemy, tagi ASS i znaczniki stylu są identyczne przed i po; zmieniają się tylko podziały `\N`;
   - słowa nie rozcinamy, a twarda spacja (`\h`, NBSP) nie jest miejscem cięcia;
   - znak otwierający (`„`, `(`, `«`, `[`) nie kończy wiersza, a zamykający lub interpunkcja nie zaczyna wiersza;
   - przed każdą zmianą mówcy (§4.2) jest podział wiersza.
2. **Unikane za wszelką cenę** (przerwa `protected`): cięcia, które profesjonaliści robią w 0% przypadków albo które wytyczne zakazują. Układ z takim cięciem wchodzi do wyboru tylko w ratunku (§5.4), gdy nie ma żadnego mieszczącego się układu bez niego. Lista klas w §4.3.
3. **Ważone** — wszystko inne. Rozstrzyga koszt z §5.3.

## 4. Analiza przerw

### 4.1 Kontrakt

Moduł `anishift/text/gaps.py` (nazwa robocza). Nie importuje `anishift.services`, nie ma przełączników domenowych (`anishift/text/AGENTS.md`), zależy od `boundaries.py` i `graphemes.py`. Wejście: słowa widocznego tekstu, bez tagów ASS i bez znaczników `<sN>`, rozdzielone zwykłymi spacjami (twarde spacje łączą słowa). Wyjście: rekord dla każdej przerwy między sąsiednimi słowami.

```python
@dataclass(frozen=True, slots=True)
class Gap:
    """Evidence for a line break between two neighbouring words."""

    kind: GapKind  # boundary class from §4.3
    banned: bool  # breaking here violates an inviolable rule (§3.1)
    protected: bool  # breaking here is avoided at all costs (§3.2)
    turn: bool  # a new speaker starts after the gap (§4.2)
    span: float  # 1 − s/n from a dependency parse: how small the phrase joining both words is; 0 without a parse
```

Siła przerwy `A(kind)` pochodzi z tabeli §4.3. Jedna funkcja `gaps()` zastępuje dwa rozjechane rankingi starego algorytmu (`_dialogue_*` i `_best_cut`/`_weight`). Szyldy liczą swoje proporcje na tych samych przerwach.

### 4.2 Mówcy, wtrącenia, myślniki

- **Zmiana mówcy (`turn`):** myślnik dialogowy (`-`, `–` albo `—`, po którym następuje spacja), stojący na początku tekstu albo po końcu zdania (`.`, `!`, `?`, `…`) i spacji. Myślnik na początku tekstu kwestii jednego mówcy nie wymusza cięcia (przed nim nie ma przerwy).
- **Wtrącenie:** para myślników `–`/`—` otoczonych spacjami wewnątrz zdania („wszyscy – a zwłaszcza Przewodniczący – poszli”). Przerwa po pierwszym myślniku i po drugim to klasa `parenthetical`; myślnik zostaje na końcu wiersza („wszyscy – / a zwłaszcza…”), bo wiersz zaczynający się od myślnika wygląda jak nowy mówca. Przerwa przed myślnikiem wtrącenia: `banned`.
- **Łącznik i półpauza bez spacji** (`biało-czerwony`, `20–30`, `Kaguya-sama`) są częścią słowa i nie tworzą przerwy.
- Pojedynczy myślnik ze spacjami w zdaniu, bez pary, to klasa `dash`.

### 4.3 Klasy przerw

Źródło wartości:
- **dane** — `A` wyliczane skryptem z korpusu Netflix + Amazon (§9.2), jako zgodnie z prototypem badań `A = √(r / r_max)`, gdzie `r` = liczba cięć ludzkich w klasie / liczba okazji tej klasy; klasy z mniej niż 20 okazjami biorą wartość startową;
- **wytyczne** — klasa chroniona z Netflix General §4, FKBB 2019 i polskiej normy typograficznej (0% w korpusie albo zakaz w wytycznych).

| Klasa (`kind`) | Wykrycie bez parsera | Z parserem | `A` start | Poziom | Źródło |
| --- | --- | --- | --- | --- | --- |
| `sentence` — po końcu zdania | `period_ends_sentence`, `!`, `?` | — | 1,00 | ważone | dane |
| `clause` — po `,` `;` `:` | znak | — | 0,94 | ważone | dane |
| `ellipsis` — po wielokropku w środku | znak | — | 0,74 | ważone | dane |
| `parenthetical` — po myślniku wtrącenia | §4.2 | — | 0,34 | ważone | dane (klasa myślnika) |
| `dash` — po pojedynczym myślniku | §4.2 | — | 0,34 | ważone | dane |
| `phrase` — inna granica bez interpunkcji | domyślna | podmiot / orzeczenie, granica dużych części zdania | 0,50 | ważone | dane |
| `nominal` — rzeczownik / dopełniacz | — | `nmod` | 0,40 | ważone | dane |
| `name` — wewnątrz nazwy wielowyrazowej | para słów z wielkiej litery (poza początkiem zdania), tytuł + nazwa | `flat`, `fixed`, `flat:foreign` | 0,39 | ważone | dane |
| `object` — czasownik / dopełnienie obok | — | `obj`, `iobj` | 0,26 | ważone | dane |
| `auxiliary` — posiłkowy / główny | lista czasowników posiłkowych i modalnych | `aux` | 0,24 | ważone | dane |
| `modifier` — przymiotnik / rzeczownik | końcówki przymiotnikowe (słaby dowód) | `amod`, `det` | 0,16 | ważone | dane |
| `after_preposition` — po przyimku, także złożonym | lista przyimków | `case` | 0 | chronione | wytyczne + dane |
| `after_single_letter` — po słowie jednoliterowym | długość słowa | — | 0 | chronione | wytyczne |
| `before_conjunction_end` — spójnik na końcu wiersza | lista spójników | `cc`, `mark` | 0 | chronione | wytyczne + dane |
| `negation` — oderwane „nie” od czasownika | „nie” przed słowem, z wyjątkami („na nie”) | `advmod:neg` | 0 | chronione | wytyczne + dane |
| `reflexive` — „się” oderwane od sąsiedniego czasownika | „się” obok czasownika z listy / po posiłkowym | `expl:pv` z sąsiednim czasownikiem | 0 | chronione | wytyczne + dane |
| `number` — liczba / rzeczownik lub jednostka | cyfry, liczebnik + słowo | `nummod` | 0 | chronione | wytyczne |
| `abbreviation` — skrót / następne słowo | `is_false_sentence_break` (np., dr, godz., ul.) | — | 0 | chronione | wytyczne |
| `idiom` — wewnątrz stałego wyrażenia | lista wyrażeń wielowyrazowych ze starego `linebreak.py` | `fixed` | 0 | chronione | wytyczne |

Uwagi:
- Klasa `reflexive` dotyczy „się” przy czasowniku, z którym tworzy człon („będziesz się bawił”, „się zakocha”). „Się” odległe od czasownika („Dlaczego się na mnie z taką złością patrzysz?”) nie chroni przerw między frazami pośrednimi: bez parsera ochrona obejmuje tylko przerwę bezpośrednio między „się” a sąsiednim czasownikiem.
- Klasa `modifier` bez parsera to słaby dowód (końcówki przymiotników mylą się z rzeczownikami); dlatego tabela `A` dla trybu bez parsera jest wyliczana osobno tym samym skryptem na klasyfikacji samych list (§9.2).
- Wyrazy obce pisane małą literą bez kursywy („prima materii”, „déjà vu”) bez parsera nie są rozpoznawane — znane ograniczenie trybu list.
- Listy pochodzą ze starego `linebreak.py` (adnotacje źródeł Wikisłownika) i ogólnych klas z odrzuconego leksykonu (enklityki, liczba przed rzeczownikiem, „się” po posiłkowym, odmienione określniki). Listy pod pojedyncze przykłady (`GENITIVE_HEADS`, `_NOT_ADJECTIVES` i podobne) nie wracają.

## 5. Wybór układu

### 5.1 Kandydaci

Wszystkie układy z cięciami na przerwach, które nie są `banned`, z cięciem na każdej przerwie `turn`. Liczba wierszy: od liczby wymuszonej przez mówców do górnej granicy z §5.4. Przy 30 słowach (29 przerw) to najwyżej 29 układów dwuwierszowych i 406 trzywierszowych; wyliczenie jest wyczerpujące.

### 5.2 Filtr mieszczenia (fizyczny)

Układ mieści się, gdy każdy wiersz mieści się na ekranie tak, jak go narysuje odtwarzacz:

- **zdarzenie zawijane przez libass:** emulacja `wrap_text` nie przewiduje zawinięcia, a glify mieszczą się w dostępnej szerokości (`geometry.measure_text`, `available_width`; zgodność emulacji z libass 5406/5406);
- **zdarzenie niezawijane** (`\q2`, `WrapStyle 2`, rozpoznane przez efektywny tryb zawijania): rzeczywisty zasięg poziomy wiersza, liczony od kotwicy (`\pos`, `\an`, marginesy), mieści się w wyśrodkowanym obszarze 90% `PlayResX`. Jeżeli najszerszy wiersz źródła wychodził poza ten obszar, granicą jest zasięg źródła: polski napis nie wychodzi poza ekran bardziej niż angielski;
- **brak pomiaru** (SRT bez stylów, metryki animowane przez `\t` zmieniające `\fs`/`\fscx`/`\fsp`, brak fontu z glifami): szacunek fizycznego zawijania odtwarzacza w znakach `W_c` [K, start 70 przy domyślnym foncie mpv w 1080p]. To granica techniczna, nie jakościowa; rampa długości (§5.3) kończy się przed nią (`b_c < W_c`), więc nie powstaje klif w środku oceny;
- **dostępna szerokość ≤ 0:** żaden układ się nie mieści; ratunek §5.4 krok 5.

### 5.3 Koszt układu

Dla układu `U` z `k` wierszami `w₁…wₖ`; „wolne cięcia” to cięcia niewymuszone przez mówców:

```text
znaki(w) = liczba widocznych grafemów wiersza
u(w)     = zmierzona szerokość wiersza / dostępna szerokość (§5.2); w trybie bez pomiaru nie istnieje
DŁUGI(w) = max(rise(znaki(w); a_c; b_c), rise(u(w); 0,60; 1,00))          a_c = 40, b_c = 66 [K]

koszt(U) = λ_k · max_i DŁUGI(wᵢ)                                            λ₁ = 1, λ_{k≥2} = λ = 0,3 [K]
         + Σ_wolnych cięć [ (1 − A(cⱼ)) + β · span(cⱼ) · [cⱼ bez interpunkcji] ]   β = 0,6 [K]
         + ζ · (k − k_mówców)                                               ζ = 0,2 [K]
         + γ · nierównowaga(U)                                              γ = 0,6 [K]
         + δ · liczba wierszy jednowyrazowych utworzonych przez wolne cięcia   δ = 0,4 [K]

nierównowaga(U) = (najdłuższy − najkrótszy) / suma znaków wierszy oddzielonych wolnymi cięciami (0 bez wolnych cięć)
k_mówców        = liczba wierszy wymuszona zmianami mówcy (1 bez zmian)
```

`rise(x; a; b)` to 0 dla x ≤ a, liniowo do 1 dla x ≥ b (istniejące `anishift/services/subtitles/fuzzy.py`). `ζ` to koszt zasłonięcia obrazu przez każdy dodatkowy wiersz. Wybór: najmniejszy koszt; przy remisie mniej wierszy, potem wcześniejsze pierwsze cięcie.

**Dlaczego dwie miary długości** [W]: znaki mierzą ilość tekstu do przeczytania i nie zależą od fontu; szerokość mierzy drogę oka po ekranie („zamiatanie wzrokiem”). Sama szerokość zawiodła z wąską Officiną (60 znaków ≈ 0,8 szerokości, w odrzuconym U5 jeden wiersz), same znaki zawodzą przy szerokich fontach. Start rampy znakowej 40–66 [B, recenzja opus55] zostawia c04 (55 znaków) w jednym wierszu i dzieli galerię 02 (60 znaków), zgodnie z wyborami właściciela.

**Przykłady kontrolne kosztu** (wartości startowe, miara znakowa; ostateczne liczby z kalibracji):
- „Dzisiaj będzie pięknie. Chodźmy na spacer.” (42): jeden wiersz 0,077; po kropce 0 + 0,2 + 0,6 · 5/41 = 0,27 → **jeden wiersz**;
- „Idę spać. Idź spać.” (19): jeden wiersz 0; po kropce 0,2 → **jeden wiersz**;
- „Ludzie zamieszkujący te ziemie popełnili straszliwe grzechy.” (60): jeden wiersz 0,77; podmiot / orzeczenie 0,5 + 0,2 + γ · 1/61 ≈ 0,71 → **dwa wiersze** (blisko; kalibracja ma utrzymać ten wybór);
- „Dlaczego się na mnie z taką złością cały czas patrzysz?” (55): jeden wiersz 0,58; najlepsze cięcie `phrase` 0,5 + 0,2 + nierównowaga ≥ 0,7 → **jeden wiersz**.

### 5.4 Liczba wierszy i ratunek

`L = max_lines` z `LayoutLimits` (ustawienie panelu 1–4, domyślnie 2) to liczba wierszy dopuszczona w zwykłym wyborze. Kroki, pierwszy niepusty wygrywa (wewnątrz kroku: koszt §5.3):

1. układy z ≤ L wierszami, mieszczące się, bez przerw `protected`;
2. układy z ≤ L wierszami, mieszczące się, z przerwami `protected` (raport `protected_cut`);
3. układy z L + 1 wierszami (najwyżej 3), mieszczące się, bez `protected` (raport `extra_line`);
4. jak 3, z `protected`;
5. przepełnienie: spośród istniejących układów z ≤ max(L + 1, 3) wierszami najmniejsze największe wyjście poza dostępną szerokość (w pikselach albo znakach), przy remisie koszt §5.3 (raport `overflow_unavoidable`).

Zmiany mówcy są nienaruszalne: gdy mówców jest więcej niż wierszy dopuszczonych w krokach 1–5, liczba wierszy równa się liczbie mówców (raport `many_speakers`). Tekst z mniejszą liczbą słów niż wierszy ma tyle wierszy, ile słów. Przy L = 1 kwestia jednego mówcy zostaje w jednym wierszu, o ile się mieści.

Dlaczego trzeci wiersz tylko w ratunku: właściciel ocenił trzy wiersze tam, gdzie mieszczą się dwa, jako przesadę (galeria 20), a korpus profesjonalny nie ma trzywierszowych napisów.

## 6. Parser zależnościowy (opcjonalny dowód)

- Kandydat: `spaCy` 3.8.16 z modelem `pl_core_news_sm` 3.8.0 (koło cp314 dla Windows, model 26 MB, bez PyTorcha, ok. 0,3 s ładowania i 0,5 s na 500 kwestii) [B].
- Wpływ zmierzony: +4,0 pp trafności miejsca cięcia nad samymi listami na Netflix + Amazon (95% CI +1,3…+6,9; opus55) oraz brak przewagi na zaszumionym Crunchyroll i na zewnętrznym dokumencie (astra: 237 wobec 238 na 392). Rzetelny zakres to 0–4 pp. Lepiej trzyma frazy rzeczownikowe („czerwonego wojownika”, „naszą wspólną przyszłość”), myli obce imiona z podmiotem („woli / Artemis” — znane ograniczenie).
- Stanza (PyTorch) nie daje przewagi poza niepewnością pomiaru, a kosztuje ok. 1 GB instalacji i 1,1–2,6 GB RAM: odrzucona.
- Parser tylko zmienia klasę przerwy na dokładniejszą i ustawia `span`; nie zdejmuje `banned`. Klasy chronione z wykrycia list zostają chronione także z parserem.
- Ładowany leniwie, raz na proces, w domenie `subtitles`. Brak pakietu, brak modelu albo błąd wyrównania tokenów oznacza tryb list z ostrzeżeniem w logu, nigdy błąd przetwarzania.
- Wchodzi do produkcji tylko po spełnieniu bramki G5 (§9.3). Licencja modelu `pl_core_news_*` to GPL-3.0 [D].

## 7. Raport

`LayoutReport` (istniejące liczniki) i flagi `DialogueLayout.flags`: `protected_cut`, `extra_line`, `overflow_unavoidable`, `many_speakers`, `unmeasured`. Jedna linia podsumowania na plik, bez tekstów kwestii.

## 8. Katalog przypadków brzegowych

Każdy wiersz to kontrakt testu i wynika z §3–§5, chyba że kolumna „Status” mówi inaczej. Statusy: **test** — przypadek do testu jednostkowego lub złotego zbioru; **[D]** — decyzja właściciela; **ograniczenie** — znane, raportowane.

| Przypadek | Przykład | Oczekiwany układ | Z czego wynika | Status |
| --- | --- | --- | --- | --- |
| pusty tekst albo same tagi | `{\an8}` | bez zmian | brak słów | test |
| jedno słowo | „Uciekaj!” | 1 wiersz | brak przerw | test |
| same wykrzyknienia, onomatopeje | „Hę?!”, „Ehhh…” | 1 wiersz | koszt 0 jednego wiersza | test |
| krótka kwestia z dwóch zdań | „Idę spać. Idź spać.” | 1 wiersz | `ζ` > 0 | test |
| tuż pod 42 znakami | „Czy aby na pewno zajmują się tylko masażem?” (43) | 1 wiersz | DŁUGI ≈ 0,12 | test (c24) |
| tuż nad 42, cięcia średnie | „Osiągnęliśmy rozejm z Sokołem z klanu Estebanów.” (48) | 1 wiersz | DŁUGI ≈ 0,31 < cięcie + `ζ` | test (c13) |
| 55 znaków, cięcia średnie | „Dlaczego się na mnie z taką złością cały czas patrzysz?” | 1 wiersz | 0,58 < 0,7 | test (c04) |
| 60 znaków, dobre cięcie | „Ludzie zamieszkujący te ziemie / popełnili straszliwe grzechy.” | 2 wiersze | 0,77 > 0,71 | test (galeria 02) |
| dwa zdania, pierwsze dłuższe | „Przepraszam. Idź z Midorikawą i resztą. / Baw się dobrze.” | po kropce | nierównowaga mała wobec cięcia w zdaniu | test (galeria 20 starej rundy) |
| dwa zdania, pierwsze jednowyrazowe | „Wiem. Zrobiłeś wszystko, o co cię prosiłam.” | 1 wiersz, gdy DŁUGI mały; inaczej „Wiem. Zrobiłeś wszystko, / o co cię prosiłam.” | `δ` za „Wiem.” | test |
| trzy krótkie zdania | „Wiem. Rozumiem. Zaczekam.” | 1 wiersz | `ζ` | test |
| trzy długie zdania, 2 wiersze się nie mieszczą | c26 | 3 wiersze, po zdaniu w wierszu | §5.4 krok 3 | test (c26) |
| dwóch mówców | „- Kufer ze złotem? / - Widać? Całe szczęście.” | wiersz na mówcę | `turn` | test (c05) |
| trzech mówców | „- Idziesz? / - Za chwilę. / - Poczekajcie!” | 3 wiersze | `turn` | test (c06) |
| czterech mówców | „- Idziesz? - Za chwilę. - Poczekajcie! - Już!” | 4 wiersze, raport `many_speakers` | mówcy nienaruszalni | test |
| mówca z długą kwestią | c27 | mówca 1 / mówca 2 / reszta mówcy 2 | wolne cięcie w ratunku | test (c27) |
| jeden mówca z myślnikiem na początku | „- Chodźmy już.” | bez wymuszonego cięcia | myślnik na początku tekstu | test |
| wtrącenie w myślnikach | „Upewniłam się, że wszyscy – a zwłaszcza Przewodniczący – poszli już do domów.” | cięcie po myślniku: „…wszyscy – / a zwłaszcza Przewodniczący – poszli…” albo po drugim myślniku; 2 wiersze, gdy się mieszczą | `parenthetical`; przed myślnikiem `banned` | [D] c07 |
| wtrącenie i drugi mówca | „- Wszyscy – a zwłaszcza on – poszli. - Dobrze.” | 2 wiersze, wtrącenie nie jest mówcą | §4.2 | test |
| zakres z półpauzą | „Kosztuje 20–30 zł.” | „20–30 zł” razem | półpauza bez spacji to słowo; `number` | test |
| nawias | „Znam go (to mój brat) od lat.” | cięcie przed nawiasem albo po nim | `(` na końcu i `)` na początku `banned` | test |
| tytuł w cudzysłowie | „A co w kolejnym odcinku „Grand Blue Dreaming”?” | „A co w kolejnym odcinku / „Grand Blue Dreaming”?” albo 1 wiersz | `„` nie kończy wiersza; wnętrze tytułu `name` | test (galeria 29) |
| imię i nazwisko | „Jan Kowalski czeka na dworcu.” | razem | `name` | test (c09) |
| honoryfikator | „Yamamoto-san”, „Kato-senpai” | jedno słowo | łącznik bez spacji | test |
| liczba z rzeczownikiem | „1,4 miliarda ludzi na całym świecie” | „1,4 miliarda” razem | `number` chronione | test (c11, [D]) |
| jednostka, godzina | „To waży 20 kg.”, „godz. 17.30” | razem | `number`, `abbreviation` | test (c23, c10) |
| skróty z kropką | „np. jutro”, „dr Kowalski”, „tzw. problem” | kropka skrótu nie jest końcem zdania | `abbreviation` | test |
| wielokropek na początku | „…nie wiem, czy wrócę.” | wielokropek przy słowie | jedno słowo | test |
| wielokropek w środku | „Ja… nie wiem, czy potrafię.” | cięcie po wielokropku dopuszczalne | `ellipsis` | test (c30) |
| „?!”, „!!” | „Naprawdę?! Nie wierzę!” | po nich granica zdania | `sentence` | test |
| wykrzyknienie z przecinkiem na początku | „O, naprawdę tak myślisz?” | 1 wiersz albo cięcie dalej, nie „O, / naprawdę…” | `δ` + `ζ` | test (lekcja U5) |
| wyrazy obce z wielkiej litery | „Grand Blue Dreaming”, „Artemis” | razem, gdy para z wielkiej litery | `name` | test |
| wyrazy obce małą literą | „prima materii”, „déjà vu” | razem tylko z parserem | `flat:foreign` | ograniczenie trybu list |
| wtręty japońskie bez spacji | „「すごい」 – powiedziała.” | jedno słowo | brak spacji | test |
| bardzo długie słowo | 115 znaków bez spacji | 1 wiersz, `overflow_unavoidable` | §5.4 krok 5 | test (c31) |
| grupa z twardymi spacjami szersza od ekranu | „25\hkg\h…” | bez cięcia wewnątrz, raport | `\h` nie jest przerwą | test |
| „się” po posiłkowym | „Z nami będziesz się bawił” | nie „się / bawił” | `reflexive` | test (c15) |
| „się” przed czasownikiem | „Kto pierwszy się zakocha” | nie „się / zakocha” | `reflexive` | test |
| „się” odległe | „Dlaczego się na mnie z taką złością patrzysz?” | wolno ciąć między frazami pośrednimi | `reflexive` tylko obok czasownika | test |
| jednoliterowe na granicy | „w domu”, „i kupiłem” | zawsze z następnym słowem | `after_single_letter` | test (c02) |
| samodzielne jednoliterowe | „O! Spójrz!” | „O!” może zamknąć wiersz | `sentence` przed `after_single_letter` | test |
| przeczenie | „nie chciałem” | „nie” przy czasowniku | `negation` | test (c14) |
| „nie” jako zaimek | „liczę na nie” | zwykła przerwa | wyjątek listy | test |
| spójniki i, a, ale, że, bo, który | „Martwię się o ciebie, bo od wczoraj nie odpowiadasz.” | cięcie przed spójnikiem | `before_conjunction_end` | test (c36, c39) |
| frazeologizm | „raz na zawsze”, „po prostu”, „w ogóle” | razem; granica po całym zwrocie dozwolona | `idiom` | test |
| kursywa / wyróżnienie | „{\i1}Gdyby…{\i0}błagała{\i1}…” | układ jak bez znaczników; znaczniki na swoich słowach | `strip_span_markers` → wybór → `restore_markers` | test |
| tagi ASS w środku | `{\fs36\fscx110}` | pomiar z tagami; cięcie tylko w widocznej spacji | `measure_text` | test (c34) |
| tagi `\k` w dialogu | `{\k20}Na{\k30}prawdę` | cięcie tylko w widocznej spacji | widoczne słowa | test |
| `\N` od tłumacza | „Tak.\NNie.” | usunięte i ułożone od nowa | wejście bez `\N` | test |
| ponowne ułożenie | wynik układu podany jeszcze raz | identyczny wynik | idempotencja | test |
| `\q2` z szerokimi marginesami | kaguya | zasięg w 90% ekranu albo nie szerzej niż źródło | §5.2 | test |
| `\pos` / `\an` przy krawędzi | dialog z `{\an1\pos(50,1000)}` | zasięg od kotwicy w obszarze | §5.2 | test |
| skala `\fscx` | `{\fscx150}` | pomiar ze skalą | `measure_text` | test |
| SRT bez stylów | plik SRT | tryb znakowy, ta sama funkcja kosztu | §5.2 | test |
| metryki animowane | `{\t(0,1000,\fs80)}` | tryb znakowy | §5.2 | test |
| nie mieści się w dwóch | c33 | 3 wiersze, jeśli rzeczywisty pomiar nie mieści dwóch | §5.4 | [D] c33 |
| nie mieści się w trzech | tekst > 3 szerokości | najmniejsze przepełnienie z ≤ 3 wierszy | §5.4 krok 5 | test |
| zerowa dostępna szerokość | marginesy 500/500 przy 1000 | 1 wiersz (lub wiersze mówców), raport | §5.2, §5.4 | test |
| piosenki, szyldy, rysunki | — | poza dialogami: `split_for_layout`, `fit_signs` | zakres | — |
| szyld-lista | ranking kaguya | poza tą specyfikacją | aneks szyldów (U4) | — |

## 9. Kalibracja, ocena i bramki

### 9.1 Zbiory

| Zbiór | Wielkość | Rola |
| --- | --- | --- |
| profesjonalne polskie napisy z MKV w `workspace` (`experiments/lb-research/opus55/pl-subs/`: Netflix 5, Amazon 6, Crunchyroll 11) | 7083 zdarzeń; 593 dwuwierszowe NF+AMZN; 1075 CR | tabela `A` (tylko NF+AMZN), kalibracja, walidacja po seriach |
| Shisha, `certain-dark-item` 01–02 | 64 dwuwierszowe + 780 jednowierszowych | kontrola anime (jedna grupa) |
| zewnętrzny SRT „Steal This Film II” | 392 dwuwierszowe | kontrola spoza anime |
| zbiór właściciela: przypadki 01–39 (`fuzzy-spec/cases`, `recommendation_v2`) + decyzje z galerii + znane złe cięcia | 66 rekordów, po usunięciu duplikatów tekstu mniej (c03/c37, c20/c21, c22/c32, g05/b6, g07/b5) | zgodność z gustem; każda nowa decyzja właściciela dopisywana |
| korpus replay (37 par, 14 677 zdarzeń dialogu) | — | klasy cięć, liczba wierszy, porównanie ze starym algorytmem |

### 9.2 Procedura

1. Zbiory deduplikowane po znormalizowanym tekście; walidacja grupowa (zbiór właściciela: z pominięciem grupy tekstu; NF+AMZN: z pominięciem całej serii). Tabela `A` i stałe [K] liczone wyłącznie na części treningowej każdego podziału.
2. Klasy przerw przypisuje ten sam kod `gaps()`, który działa w produkcji. Dwie tabele `A`: dla trybu list i dla trybu z parserem, z tego samego korpusu.
3. Stałe [K] (`a_c`, `b_c`, `λ`, `β`, `γ`, `δ`, `ζ`, `W_c`) dobierane w siatce na prawdziwym pomiarze fontu (profil zdarzenia, a w galerii czcionka właściciela).
4. Metryki raportowane osobno: zgodność całego układu (liczba wierszy i miejsca cięć) oraz trafność miejsca cięcia **warunkowo** dla referencji dwuwierszowych.
5. Stary algorytm mierzony tym samym kodem oceny, tym samym klasyfikatorem klas i na tych samych zbiorach.

### 9.3 Bramki

| Bramka | Warunek |
| --- | --- |
| G1 nienaruszalne | zero zmian tekstu, zgubionych tagów, rozciętych słów, wierszy zaczynających się od interpunkcji, mówców bez własnego wiersza |
| G2 zbiór właściciela | walidacja grupowa: co najmniej 80% zgodnych układów i co najmniej o 8 punktów procentowych więcej niż stary algorytm; ze znanych złych cięć powtarza się najwyżej „woli / Artemis” (znane ograniczenie, §6) |
| G3 NF+AMZN | trafność miejsca cięcia (referencje dwuwierszowe, walidacja po seriach) co najmniej 75% i co najmniej 10 pp więcej niż stary algorytm |
| G4 replay | dla każdej klasy chronionej częstość nie wyższa niż u starego algorytmu; pojedyncze wiersze z DŁUGI ≥ 0,8 w najwyżej 0,5% kwestii jednowierszowych; trzy wiersze tylko z przyczyn §5.4 |
| G5 parser | wariant z parserem wchodzi tylko, gdy w G2 i G3 jest nie gorszy, w G3 lepszy z dolną granicą 95% CI bootstrap > 0, a w G4 bez nowych regresji; inaczej produkcja działa na listach |
| G6 wrażliwość | zmiana każdej stałej [K] o ±10% zmienia wynik G2 najwyżej o 2 przypadki i G3 najwyżej o 2 pp |
| G7 czas | ułożenie 500 kwestii z zimnym importem modelu: najwyżej 60 s (właściciel dopuszcza kilka minut na odcinek) |
| G8 galeria | przed/po z czcionką właściciela po obu stronach (`compare --font`), obejrzana przez orkiestratora obraz po obrazie, potem właściciel |

## 10. Integracja i kontrakty

- `layout_translated(...)`, `layout_dialogue(event, text, profile, limits) -> DialogueLayout`, `split_lines(event, text, count, profile)`, `split_for_layout(...)`: sygnatury bez zmian. W `layout_dialogue` rekurencyjne `_split`/`_dialogue_cut` ustępuje `gaps()` + wyborowi z §5; `profile` służy pomiarowi.
- `LayoutLimits(max_chars, max_lines)`: `max_chars` (domyślnie 42) przesuwa rampę znakową (`a_c` = `max_chars` − 2, `b_c` = `max_chars` + 24 przy wartościach startowych); `max_lines` to `L` z §5.4. Ustawienia w panelu zostają.
- Testy, które kodują twardy limit 42 znaków (`test_subtitles_linebreak.py:87-91, 225-229`), zmieniają oczekiwania zgodnie z §5; pozostałe testy starego kontraktu (zakazy, mówcy, frazy, skróty, NBSP, kolejność słów) zostają.
- Infrastruktura z odrzuconej gałęzi do przeniesienia (sprawdzona): rozpoznanie efektywnego trybu zawijania (`wraps_automatically`), obsługa braku miejsca między marginesami, tryb znakowy dla metryk animowanych, test znaczników „błagała”.
- Chunkery tłumaczenia i TTS bez zmian (twarde limity żądań).

## 11. Decyzje dla właściciela

1. **Licencja modelu spaCy (GPL-3.0)**, jeśli parser przejdzie G5. Bez niego algorytm działa na listach (badania: 0–4 pp gorzej na profesjonalnych napisach).
2. **Przypadek 07 (wtrącenie w myślnikach):** wybrałeś trzy wiersze, choć mieszczą się dwa. Specyfikacja daje dwa wiersze z cięciem po myślniku wtrącenia. Do potwierdzenia na galerii.
3. **Przypadek 33:** wybrałeś trzy wiersze; przy rzeczywistym pomiarze dwa mogą się mieścić, a wtedy reguła da dwa. Do potwierdzenia na galerii.
4. **Długi jeden wiersz a dobre cięcie (11: u = 0,90; 15: u = 0,98):** porównywałeś jeden wiersz tylko ze złym cięciem („1,4 / miliarda”, „się / bawił”). Reguła wybierze dwa wiersze z dobrym cięciem, jeśli takie istnieje. Do potwierdzenia na galerii.
5. **Dzielenie wyrazów w szyldach** (z myślą o MangaShift): poza zakresem; reguła nienaruszalna 2.1.1 `visual-quality.md` zostaje.

## 12. Poza zakresem

Wskazówki granic od tłumacza (LLM): odłożone do czasu, gdy wariant lokalny osiągnie plateau, a błędy będą frazowe; wymagałyby zmiany kontraktu tłumaczenia i płatnych przebiegów. Implementacja dla MangaShift (front, `pretext`), dzielenie wyrazów (`pyphen` z filtrami) i zasada dla szyldów-list (aneks U4).

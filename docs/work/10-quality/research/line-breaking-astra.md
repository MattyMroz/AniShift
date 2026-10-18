# Łamanie polskich dialogów: niezależny research i próba obalenia prostego rankingu

Stan: 18–19.10.2026. Kontrakt: `LB-research-v2`. Baseline: `work/quality/08-fuzzy-quality`, `03e60a66c14be3e57b0451f5a9408b3226587149`.
Tryb: research; eksperymenty poza kodem aplikacji, bez płatnych wywołań i zmian zależności projektu.

## 1. Streszczenie dla właściciela

Rekomenduję poprawianie działającego rdzenia `08`, z zachowaniem jego kontraktów, zamiast zastąpienia go odrzuconym `16` lub niezweryfikowanym rankingiem.
Najpierw należy chronić jednostki znaczenia, a długość, kształt i zasłanianie obrazu porównywać jako koszty, nie jako kolejkę absolutnych pierwszeństw.
Badania wspierają preferencję składniowych cięć, lecz nie dowodzą uniwersalnego optimum 42 znaków, przewagi piramidy ani normy 2–4 fiksacji.
Jeden wiersz jest poprawnym wynikiem; dwa pomagają, gdy istnieje dobre cięcie, a jeden staje się wyraźnie szeroki.
Asymetria po końcu zdania jest zwykle lepsza niż rozcięta fraza, ale jej przewaga nie jest bezwarunkowa.
Trzy wiersze powinny pozostać ratunkiem, a nie sposobem wyrównywania długości; odrębnie trzeba zachować jawnych trzech mówców.
`spaCy/pl_core_news_sm` jest szybkim kandydatem do dalszego eksperymentu, ale nie wykazano jego przewagi w samym wyborze miejsca cięcia nad starym algorytmem ani wariantem bez parsera.
W pełnym układzie 64 dwuwierszowych kwestii Shishy uzyskał 60 zgodnych podziałów wobec 54 starego algorytmu; po ustaleniu liczby wierszy i zastąpieniu geometrii miarą znakową wynik spaCy spada do 55, a na 392 kwestiach dokumentu nie wygrywa z wariantem bez parsera.
Wspólny prototyp z parserem pogorszył także trzy z sześciu wymaganych przykładów galerii, więc nie należy wdrażać jego obecnych wag.
Stanza nie wykazała przewagi nad lekkimi narzędziami, a potrzebowała około 177 sekund na 1237 tekstów i 1,12 GB szczytowej pamięci procesu.
Tłumacz powinien na razie dostarczać tekst i znaczniki stylu, a lokalny kod decydować o układzie z pomiarem fontu.
Największą niewiadomą pozostaje zgodność z gustem właściciela na nowych, niezależnie ocenionych odcinkach: 39 regresji oraz jeden dokument nie zastępują takiej próby.

## 2. Tezy i ich weryfikacja

| Teza | Dowód za / przeciw | Werdykt |
|---|---|---|
| 42 jest optimum ludzkiego czytania | Netflix ustanawia limit; Karakanta przyjmuje go dla TED, nie bada percepcji; BBC używa także szerokości | Punkt odniesienia, nie odkryte optimum [S3–S7] |
| Krótsze wiersze zawsze czyta się szybciej | Dyson/Kipping: w ciągłym tekście 100 znaków szybciej niż 25, choć preferowano 55 | Nie; osobno mierzyć szybkość, zrozumienie i preferencje [S11] |
| Nieskładniowe cięcie szkodzi | Preferencje, wysiłek i rewizyty; brak jednolitego efektu na wszystkie miary i rozumienie | Mocny kierunek, bez uniwersalnej liczbowej kary [S1–S2] |
| Piramida jest zawsze najlepsza | Wytyczna Netflix, polskie wytyczne dopuszczają odstępstwa; brak izolowanego eksperymentu | Słaby koszt estetyczny, nie veto [S3–S6] |
| Trzy wiersze są zawsze błędem | Netflix ogranicza do dwóch; FKBB dopuszcza wyjątki, BBC uwzględnia format | Ratunek produktowy; brak pomiaru optimum dla anime [S3–S5] |
| Parser rozwiąże łamanie | Poprawia część krótkich fraz; galeria 05/08/29 pokazuje regresje wspólnego rankingu | Narzędzie dowodowe, nie gotowy segmenter |
| PyTorch jest konieczny | Stanza 58/64, spaCy 60/64; dokument odpowiednio 234/392 i 237/392 | Brak uzasadnienia kosztu w tej próbie |
| Stary algorytm trzeba wyrzucić | Stary 54/64 Shishy; 6/6 galerii z definicji, bo referencja = stary układ; ma konkretne błędy fraz i próg 42 | Zachować bazę i poprawiać najwęższy punkt |
| 39 etykiet to niezależny gold właściciela | Test z `q-breaks`, część wyborów roboczych/delegowanych; `model-v32.md`, aneksy | Kontrakt regresji o mieszanej proweniencji |
| Publiczny korpus to dowolna redystrybucja | Oficjalny SRT filmu dostępny; brak nazwanej licencji napisów | Lokalna ewaluacja; nie dołączać treści korpusu do publicznej paczki |

## 3. P1 — czytelność, długość i obraz

### 3.1 Co faktycznie zmierzono

**Gerber-Morón i Szarkowska, 2018 [S1], pełny tekst.** Eksperyment 1: 68 osób, w tym 21 polskojęzycznych; eksperyment 2: 40 osób słyszących, słabosłyszących i głuchych. Oceniano pary statycznych kadrów z **angielskimi** napisami. Podział między zdaniami wybierano w 86% i 90% odpowiednich prób. Dane oka miały mniejsze próby niż dane preferencji. Nie wszystkie konstrukcje i miary dawały ten sam efekt. Polscy uczestnicy nie oznaczają polskiego materiału.

**Badanie segmentacji w dynamicznym filmie [S2], pełny tekst, tabele 9–16.** Dwa około minutowe klipy, węgierskie audio i angielskie napisy; zmieniano podział przy tym samym tekście i czasie. Próby 74 i 46 osób częściowo się nakładają (27 uczestników), więc nie wolno ich sumować. Nieskładniowa segmentacja zwiększała trudność (`F(1,71)=15,584; p<0,001`), wysiłek (`p=0,007`) i frustrację (`p<0,001`). W eksperymencie 1 rewizyty wzrosły z 0,25 do 0,37 (`p=0,001`, częściowe eta² 0,158); nie wystąpił główny efekt segmentacji dla wszystkich miar fiksacji. Nie wykryto różnicy rozumienia (`p=0,523` i `0,403`), ale tylko pięć pytań na klip i możliwy efekt pułapu nie pozwalają orzec równoważności.

**Perego i in. 2010 [S10]: dostęp tylko do abstraktu i omówień.** Nie używam wtórnie przytaczanych czasów fiksacji jako własnego odczytu tabel. Wynik bez wykrytej szkody rozumienia nie obala preferencji składni ani nie dowodzi, że każde złe cięcie jest obojętne.

**Dyson/Kipping 1998 [S11]: tylko abstrakt wydawcy.** Dwa eksperymenty ciągłego czytania ekranowego: 100 znaków czytano szybciej niż 25 przy podobnym rozumieniu; subiektywnie najłatwiejsze było 55. Nie ma tu filmu, krótkiej ekspozycji ani konkurencji z obrazem. Dyson 2004 [S12] jest przeglądem, nie eksperymentem ustanawiającym długość napisów; pełny tekst zablokowany, odczytano abstrakt.

**Wniosek:** mniej poziomego ruchu oka nie musi oznaczać mniej pracy całkowitej — dochodzą powroty do nowego wiersza, rozpoznawanie składni i czas patrzenia na obraz. Nie znaleziono tu izolowanego eksperymentu wyznaczającego granicę „od N znaków dwa wiersze są lepsze”, przewagę dolnej piramidy ani optimum trzech wierszy dla poziomego anime. „2–4 fiksacje obejmują cały napis” jest hipotezą właściciela, nie zweryfikowaną normą; liczby zależą także od definicji obszaru i czasu ekspozycji.

### 3.2 Skąd liczby i kształty

| Źródło | Rzeczywisty kontrakt | Czego nie dowodzi |
|---|---|---|
| Netflix PL §§3, 8, 12, 16 [S3] | 42 znaki, zwykle jeden wiersz, maksimum dwa, preferencja dolnej piramidy bez 1–2 słów u góry; 17 cps dorośli, 13 dzieci | Fizjologicznego optimum 42; font jest dobierany do tego limitu |
| BBC §§3.1, 3.3–3.6 [S4] | 37 w Teletext, ograniczenie szerokości dla proporcjonalnych fontów; priorytet języka nad geometrią; „long and thin” może mniej zasłaniać obraz | Że 37 jest optymalną liczbą czytelniczą; to ograniczenie 40 pól pomniejszonych o kody sterujące |
| FKBB 2019, s. 2–4 PDF [S5] | Do 40 znaków, zwykle dwa wersy; trzeci dla przekazu głównie słownego, np. publicystyki; składnia uzasadnia odstępstwo od krótszej góry | Eksperymentu identyfikującego ostry próg 40 |
| Karamitroglou 1998, części „Number of lines”, „Text segmentation” [S6] | Około 35 znaków; prostokąt i najwyższe węzły składni; dwa zdania najlepiej osobno | Że ponad 40 zawsze szkodzi przy niezmienionym foncie; jego argument zakłada konieczność zmniejszenia fontu |
| DCMP, „Text”, „Line Division” [S13] | Preferowane dwa; warunkowo 3–4 w captionach | Domyślnego układu anime |

Pochodzenia wartości **32 i 39** jako rzekomych uniwersalnych limitów nie ustalono. Nie przypisuję ich bez dowodu STAW, EBU ani TVP. Nie uzyskano pełnych rozdziałów książek Ivarssona/Carrolla i Díaz Cintas/Remael; poglądy cytowane za innymi pracami pozostają wtórne.

### 3.3 Odpowiedzi praktyczne

- Dwa zdania: najpierw rozważ granicę po kropce. Długi górny i krótki dolny wiersz nie są same w sobie błędem; cięcie wewnątrz pierwszego zdania może wygrać, jeżeli alternatywa jest niemieszcząca się albo skrajnie niewygodna, ale nie dla kilku znaków równowagi.
- Krótkie pierwsze zdanie i długie drugie: identyczna reguła. Nie zamieniać „krótsza góra” w nagrodę za jedno słowo u góry. Samodzielne „Nie!” ma jednak większą kompletność niż „A co”.
- Trzy krótkie zdania: nie generować trzech wierszy dlatego, że są trzy kropki; grupować pełne zdania w jeden lub dwa wiersze.
- Drugi wiersz kosztuje wysokość zasłoniętego obrazu, ale bez obrazu nie znamy semantycznego kosztu zasłonięcia twarzy lub szyldu. Liczba wierszy jest zastępnikiem, nie pomiarem utraty informacji.
- Widz AniShift słyszy lektora i często ogląda x2; wyników dla SDH lub angielskiego tekstu nie przenosić bezpośrednio na to użycie.

## 4. P2 — polskie jednostki i wykrywalność

Podstawa językowa: FKBB [S5], BBC [S4], Netflix wymagania ogólne §4 [S14]. Relacje techniczne: Universal Dependencies [S15]. Preferencja granic to **siła dowodu**: koniec zdania, kompletne zdanie składowe, granica fraz, dopiero wnętrze frazy. Przecinek jest wskazówką, nie dowodem domknięcia. Nie każdy podmiot musi być w tym samym wierszu co orzeczenie.

| Jednostka | Rozpoznanie tanie | Co wnosi parser / ograniczenie |
|---|---|---|
| Przyimek z grupą: „w kolejnym odcinku” | Słownik przyimków chroni następny token | `case` wskazuje rzeczownik, ale długi łuk nie powinien sklejać całej kwestii |
| Zgoda: „wpływ psychiczny”, „czerwonego wojownika” | POS + zgodny przypadek/rodzaj/liczba sugerują związek | `amod` uwzględnia również szyk przestawny; sama zgodność bywa przypadkowa |
| Rząd: „woli Artemis”, „klejnoty Yamamoto” | Sam dopełniacz nie wystarcza; nazwy obce często nieodmienne | `nmod` pomaga, lecz ma wiele funkcji i bywa błędne |
| „nie”, posiłkowe, enklityki | Dosłowne tokeny; nie mylić „na nie” z negacją | `advmod`, `aux`, `expl`; lokalny zakaz mocniejszy niż odległy łuk |
| „się” | Brak stałego kierunku „zawsze do lewego/prawego” | `expl` wiąże z czasownikiem, ale swobodny szyk wymaga malejącego kosztu z odległością |
| Imię/nazwisko, nazwa/tytuł | Wielkie litery są tylko heurystyką | `flat`, NER lub znany span; obce tytuły mogą być źle analizowane |
| Liczba i jednostka, data/godzina | Tokenizacja i mały rozpoznawacz zapisu | Nie wymaga ciężkiego parsera; liczebniki słowne bywają `nummod` |
| Spójniki i zaimki względne | Preferuj przed „i”, „ale”, „że”, „który”, nie po nich | `cc`/`mark` mogą mieć długi łuk; trzeba chronić także lokalną funkcję wprowadzającą |
| Frazeologizmy | Istniejące frazy i kontekst; samo POS nie wystarcza | `fixed` nie pokrywa wszystkich idiomów, „wysadzić w powietrze” nie musi być jednym poddrzewem |

**Krótkie przecinane łuki** są dobrym ogólnym sygnałem: kara za `amod` między sąsiednimi słowami powinna być większa niż za odległą zależność `się`–czasownik. Nie należy karać jednakowo każdego łuku: każde drzewo zdania przecina większość naturalnych granic, a wymaganie „nie tnij żadnego poddrzewa” często wymusza jeden bardzo długi wiersz. Suma bez nasycenia karze długie zdania tylko za liczbę relacji. W prototypie zastosowano sumę nasycaną do 1 i wagę odwrotną do długości łuku; galeria wykazała, że nawet to jest zbyt silne jako samodzielna ocena kompletności.

Płytki chunker może wystarczyć do lokalnych grup rzeczownikowych, ale nie znaleziono sprawdzonego gotowego polskiego chunkera z lepszym bilansem wdrożenia niż badane parsery. Morfeusz zwraca alternatywne analizy morfologiczne; do przypisania jednej analizy potrzebuje dezambiguacji, a do zależności — kolejnego mechanizmu. Składanie trzech bibliotek tylko po to, by odtworzyć gotowy parser, nie jest prostsze.

## 5. P3 — narzędzia i pomiar

### 5.1 Co uruchomiono i co tylko sprawdzono

Stan kół i zależności zapisano z PyPI JSON w `metadata.json`. `py3-none-any` dowodzi dostępności paczki, nie zgodności całego stosu. **Uruchomiono** UDPipe 1, spaCy sm i Stanza; pozostałe pozycje to przegląd, nie benchmark.

| Narzędzie | Windows / Python 3.14 | Kod / model; ciężar i funkcja | Werdykt |
|---|---|---|---|
| UDPipe 1, `ufal.udpipe 1.4.0.1`, Polish PDB UD2.5 | Koło cp314 win_amd64, działający pomiar | Kod MPL-2.0; modele UD2.5 CC BY-NC-SA wg wydawcy; model 25 523 919 B; C++ tokenizer/tagger/parser | Najmniejszy stos, lecz model z ograniczeniem niekomercyjnym nie jest bezwarunkowym domyślnym zasobem publicznego produktu [S16] |
| spaCy 3.8.16 + sm 3.8.0 | Koło cp314 i działający stos | MIT kod; **GPL-3.0 model**, 26 684 938 B po instalacji; CPU Thinc/tok2vec, parser i morphologizer | Szybki kandydat do następnej próby, bez wykazanej przewagi samego cięcia; dystrybucja modelu wymaga osobnej decyzji [S17] |
| spaCy md/lg 3.8.0 | Ten sam runtime; nie instalowano modeli | GPL-3.0; dodatkowe wektory; zgłoszone archiwa ok. 47/547 MiB wymagają sprawdzenia konkretnego assetu przed pobraniem | Lepszy LAS nie dowodzi lepszego cięcia; brak własnych wyników |
| Stanza 1.15.0, `pdb_charlm` | Działa z torch 2.14.1 cp314 | Kod Apache-2.0; dokumentacja modeli zastrzega prawa korpusów i ODC-By w zakresie praw Stanfordu; około 360,46 MB pobranych plików z manifestem | Ciężki komparator, bez przewagi layoutu; **nie absolutny sufit jakości całej rodziny** [S18] |
| UDPipe 2 | Brak testu lokalnego; README mówi o testowaniu tylko na Linuksie | Python-only, MPL-2.0, tokenizacja przez UDPipe1; README `udpipe-2`: TF1 do treningu, TF2 dopuszczony do inferencji, lokalny REST | Nie mylić z binarnym UDPipe1 ani przypisywać PyTorcha; brak dowodu gotowego stosu Windows/cp314 [S19] |
| Trankit 1.1.2 | Koło py3 jest, ale **`torch>=1.6.0,<=2.0.1`** blokuje standardowy stos cp314 | Apache-2.0 kod; transformer/adapters; licencje i rozmiar konkretnych wag oddzielnie | Nie ogłaszać zgodności tylko dlatego, że nowy torch ma koło [S20] |
| COMBO 4.0.14 | py3; `torch>=2`, transformers, peft i dalsze zależności; nie wykonano instalacji | Parser zależnościowy, współczesny ciężki stos; licencja konkretnych wag niezweryfikowana | Nie ma własnego pomiaru ani podstaw do dokładnego kosztu/LAS [S21] |
| Morfeusz 2 1.99.15 | `cp310-abi3-win_amd64`, 9 688 808 B koła; zgodny tag ABI, bez uruchomienia | BSD kod; słownik analiz morfologicznych, nie parser | Sam nie wystarczy do zależności [S22] |
| Concraft-pl / KRNNT / Toygger | Concraft osobny stos; KRNNT legacy TensorFlow/Keras; Toygger niewystarczająco zweryfikowany | Dezambiguacja/tagowanie, nie gotowy zamiennik dependency parsera | Nie zalecam składania własnego stosu; brak pomiaru cp314 [S23] |
| HF HerBERT / polskie RoBERTa / ONNX | onnxruntime 1.31.0 ma cp314 win_amd64 | Enkoder nie ma automatycznie `head/deprel`; potrzebne wytrenowane głowice i dekoder; klasyfikacja POS też wymaga głowicy | Nie znaleziono zweryfikowanego gotowego polskiego pakietu parsera ONNX do tej integracji; nie twierdzę, że nie istnieje [S24] |
| NLTK 3.10.3 / Polyglot 16.7.4 | NLTK py3; Polyglot i PyICU bez odpowiednich kół w aktualnym PyPI | NLTK algorytmy, nie gotowy polski parser; Polyglot głównie POS i inne zadania | Brak przewagi funkcjonalnej; brak kół oznacza koszt kompilacji, nie matematyczną niemożliwość [S25] |

**Licencje:** publiczność repozytorium nie rozstrzyga kompatybilności z GPL, NC ani praw do modeli. Nie należy przepisywać licencji kodu na wagi. W szczególności karta HF Stanza i dokumentacja UD nie dają podstaw do bezwarunkowego „wszystkie modele Apache”. Research lokalny nie jest decyzją o bundlowaniu.

### 5.2 Publikowane metryki składniowe — nie ranking layoutu

| Model i zbiór | UPOS / UAS / LAS (%) | Źródło i zastrzeżenie |
|---|---|---|
| UDPipe1 PDB UD2.5, raw | 97,1 / 86,5 / 82,7 | [S16] §1.4, wiersz Polish-PDB; gold tok LAS 83,2 |
| UDPipe1 LFG UD2.5, raw | 96,7 / 90,9 / 87,4 | Inny treebank; nie wyciągać przewagi nad PDB |
| spaCy sm / md / lg 3.8.0 | 96,94 / 87,33 / 79,27; 97,66 / 89,10 / 81,73; 97,83 / 89,59 / 82,54 | `performance` w meta.json [S17], źródło PDB2.8/NKJP |
| Stanza v1.5.1 charlm, PDB UD2.12 | 98,63 / 93,73 / 91,73 | [S18] **historyczna tabela**, nie własna ocena pobranych wag 1.15 |
| Trankit **large**, PDB UD2.5 | 99,16 / 96,43 / 94,88 | [S20], tabela podpisana `Trankit[large]`; nie przypisywać modelowi base |

LAS mierzy etykietowane łuki składni, nie komfort widza. Inne wersje UD, tokenizacja, dane i modele uniemożliwiają prosty ranking z tej tabeli. Nie przytaczam niepotwierdzonych dokładnych liczb COMBO, Toyggera ani HerBERT jako parsera.

### 5.3 Dane i uczciwe jednostki oceny

Katalog eksperymentów, dalej **E**: `C:/Users/MattyMroz/Desktop/PROJECTS/AniShift/workspace/.quality/experiments/lb-research/astra/`.

| Grupa | Wielkość | Pochodzenie / zastosowanie |
|---|---:|---|
| `contract39` | 39 | `_EXPECTED` testu z **odrzuconego** worktree `q-breaks`; nie test starego baseline i nie 39 niezależnych głosów właściciela |
| `human` | 64 | Jawne dwuwierszowe kwestie Shishy, dwa odcinki `certain-dark-item`; style `Toaru*` |
| `human-other` | 780 | Jednowierszowe kwestie tych samych dwóch odcinków; potrzebne, aby nie nagradzać bezwarunkowego robienia dwóch wierszy |
| `human-external` | 392 | Unikalne dwa fizyczne wiersze oficjalnego polskiego SRT „Steal This Film II”; 679 cue, 450 dwuwierszowych przed filtrami; autorzy wymienieni przez wydawcę [S26] |
| `gallery` | 6 | Obrazy 01, 02, 05, 08, 20, 29; referencją jest **stary układ**, nie niezależny ludzki gold |

Łącznie 1281 rekordów, 1237 unikalnych tekstów. Korpus zewnętrzny został opublikowany przez twórców filmu, z autorami Spiechu, Alek, Kasiamilewska i Toopko; nie udowodniono ręcznego autorstwa każdego cięcia ani statusu zawodowego każdego autora. To dostępne ludzkie przybliżenie, **nie spełnienie mocniejszego żądania 300 profesjonalnie zweryfikowanych kwestii anime**. Filtry i źródła są w `human-corpus/provenance.md`; 392/392 podziałów sprawdzono z fizycznymi wierszami SRT. Cztery cue miały nadmiarowe spacje: referencje normalizowano wewnątrz wierszy, bez przesuwania granic.

Nie trenowano parserów ani nie dostrajano wag per narzędzie. Wagi ustalono raz po poznaniu przypadków `contract39` i galerii, więc **39 i galeria to zbiory rozwojowe, nie holdout**. Nie zachowano dowodu zamrożenia wag przed wglądem w Shishę (`human` i `human-other`), dlatego jej wyniki również traktuję jako eksploracyjne, nie niezależną walidację. Dokument dodano jako próbę zewnętrzną; nie był to jednak prerejestrowany test, a późniejsze diagnostyczne spany wybrano po obejrzeniu wyników. Dwa odcinki tego samego fansubu i jeden dokument oznaczają silną zależność próbek. Nie wolno przedstawiać 392 kwestii jako 392 niezależnych filmów.

Geometria ASS: istniejące `geometry.py`, fonty odcinka i systemowe, dla galerii replay `u6-font` plus pliki Officiny właściciela. Przypadki 01–39 zachowują własne profile z `A.ass`, nie podmieniono im wszystkich fontów na Officinę. `gallery-context.json` wskazuje dokładny event i styl. Metryki pochodzą z modelu geometrii aplikacji; nie wykonano nowej walidacji renderu libass ani pełnej oceny ruchu w mpv.

### 5.4 Wyniki wspólnego rankingu

`surface` to ten sam ranking bez zależności, z interpunkcją i istniejącym `_dialogue_protected`; **nie** stary algorytm. `old` to niezmieniony `split_line` baseline. Kontrola wykazała zgodność jego cięć z `layout_dialogue` na wszystkich 889 rekordach lokalnych.

**Pełny wybór liczby wierszy i granic, z geometrią ASS — zgodność dokładna:**

| Grupa | Stary | Bez parsera | spaCy sm | UDPipe1 | Stanza |
|---|---:|---:|---:|---:|---:|
| 39 regresji | 17/39 | 19/39 | 30/39 | 30/39 | 30/39 |
| Shisha, 64 dwuwierszowe | 54/64 (84,38%) | 54/64 | **60/64 (93,75%)** | 58/64 | 58/64 |
| Shisha, 780 jednowierszowych | 637/780 | 703/780 | 742/780 | 744/780 | 739/780 |
| 6 galerii, zgodność ze starym | 6/6 z definicji | 6/6 | **3/6** | 3/6 | 3/6 |

**Wyłącznie miejsce cięcia przy znanej liczbie wierszy**, wspólna miara znakowa zamiast odgadywania fontu:

| Grupa | Bez parsera | spaCy sm | UDPipe1 | Stanza |
|---|---:|---:|---:|---:|
| Shisha, 64 | 53 | 55 | 54 | 56 |
| Dokument, 392 | **238 (60,71%)** | 237 (60,46%) | 236 (60,20%) | 234 (59,69%) |

Druga tabela izoluje sygnał językowy w zadaniu boundary-only; nie jest oceną renderowanego układu. W `benchmark.json` pozostawiono również eksperymentalne wyniki pełnego layoutu dokumentu z `len/60`, ale **nie traktujemy ich jako jakości ekranowej**, bo brak fontu, marginesów i rozdzielczości. Stary algorytm daje tam 208/392, spaCy 128/392; różnicę silnie determinuje wybór jednego wiersza, nie poprawność granicy.

**Punkt odniesienia starego algorytmu:** na Shishy sam wybrał referencyjną liczbę wierszy we wszystkich 64 przypadkach i uzyskał 54/64 wobec 55/64 spaCy z drugiej tabeli. Na 358 kwestiach dokumentu, na których stary sam wybrał dwa wiersze, wyniki wynoszą: stary 208, surface 225, spaCy 221, UDPipe 218, Stanza 215. To porównanie orientacyjne: stary zachowuje własny wybór liczby wierszy i pomiar (ASS dla Shishy, proxy `len/60` dla dokumentu), a pozostałe kolumny mają zadaną liczbę wierszy i miarę znakową. Wybrany podzbiór 358 nie zastępuje pełnych 392. **Nie wykazano przewagi parsera w samym miejscu cięcia**; przesłankami do kolejnej próby są wynik rozwojowych 39, eksploracyjny pełny układ Shishy i wybrane po inspekcji spany, nie dowód generalizacji.

**Próba obalenia przewagi:** spaCy vs surface na 64 kwestiach: 8 trafień zyskanych, 2 utracone, dokładny test znaków/McNemara `p=0,1094`; eksploracyjny sparowany bootstrap różnicy: 0 do 18,75 punktu procentowego. Dokument: 47 zysków, 48 strat, `p=1`; bootstrap −5,10 do +4,34 pp. spaCy vs Stanza na dokumencie: 13 zysków, 10 strat, `p=0,6776`. To nie dowód równoważności, lecz brak wykazanej przewagi ciężkiego modelu. Bootstrap po cue nie oddaje niepewności między seriami; do decyzji produktowej potrzebny jest holdout po odcinkach.

### 5.5 Klasy błędów

Nie użyto ocenianego parsera jako własnego sędziego. Automatyczne flagi powierzchniowe i mały jawny audyt spanów są odrębne od trafności względem referencji. Diagnostyczne spany wybrano po inspekcji przykładów, więc nie są reprezentatywnym estymatorem częstości błędów.

| Klasa i mianownik | Stary | Surface | spaCy / UDPipe / Stanza | Znaczenie |
|---|---:|---:|---:|---|
| Po jednoliterowym słowie, 64 Shishy | 0/64 | 0/64 | 0/64 każdy | Wąska reguła powierzchniowa |
| Po rozpoznanym prostym przyimku, 64 Shishy | 0/64 | 0/64 | 0/64 każdy | Nie obejmuje wszystkich grup przyimkowych |
| Rozcięta fraza rzeczownikowa, 4 wskazane wystąpienia Shishy | 2/4 | 4/4 | 0/4 każdy | „czerwonego wojownika”, „światowej konferencji”, „innymi piętrami”, „każdą materię” |
| Rozcięta fraza rzeczownikowa, 3 wskazane wystąpienia w 39 | 1/3 | 3/3 | 1/3 każdy | U starego i parserów pozostaje przypadek 33 |
| Rozcięty idiom, 2 wskazane wystąpienia w 39 | 2/2 | 2/2 | 0/2 każdy | Mała próba diagnostyczna, nie ogólna skuteczność idiomów |
| Lokalna konstrukcja czasownikowa z „się”, `stf2-pl-0039`, dwa wiersze | — | 1/1 | 0/1 każdy | Jedno wskazane wystąpienie dokumentu |
| Granica obok „się”, 392 dokumentu, pełny wariant proxy | 13 | 9 | 3 / 4 / 3 | **Nie jest liczbą błędów**; „się” może poprawnie zamykać frazę |

Przykłady z rzeczywistych różnic: surface `Najbardziej lubię czerwonego / wojownika, bo jest superaśny!`, spaCy `Najbardziej lubię czerwonego wojownika, / bo jest superaśny!`; surface `na światowej / konferencji`, parser zachowuje całą grupę. Kontrprzykład dokumentu `stf2-pl-0023`: spaCy zostawia zaimek względny na końcu wiersza, a surface tnie przed nim. Granica po kompletnym idiomie **nie rozcina samego idiomu** i nie powinna być tak liczona. Samo odejście od referencji nie jest błędem: `Zleciłem ludziom z podziemia / podrobienie naszych danych…` i alternatywny podział wymagają oceny w kontekście, nie automatycznej etykiety.

**Ograniczenie obowiązkowego pomiaru:** pełnego odsetka wszystkich błędów fraz rzeczownikowych, idiomów i „się” na całym zbiorze nie ustalono niezależną ręczną anotacją. Podano odtwarzalne wąskie liczniki i przykłady, zamiast pozornej pełnej miary jakości lingwistycznej.

## 6. P4 — tłumacz a podział

### 6.1 Literatura i zakres transferu

Karakanta 2020 [S7], pełny PDF s. 4–8: `<eol>` to kolejny wiersz, `<eob>` kolejny napis. Średnie pauzy przy braku granicy / `<eol>` / `<eob>` wynosiły 0,039 / 0,074 / 0,551 s; to korelacja i inne zadanie niż geometryczny reflow gotowego eventu. Limit 42 pochodzi z przyjętego kontraktu TED, nie eksperymentu percepcyjnego.

MuST-Cinema [S8], s. 3–7: siedem języków, bez polskiego; utracone `<eol>` w części treningowej, zachowane lepiej w dev/test. Modele potrafią przewyższyć prosty licznik, ale dane są tłumaczeniami TED, a zgodność granic nie jest oceną widza. Sigma [S9], s. 2–8, rozdziela jakość tłumaczenia od segmentacji; autorzy wymagają walidacji korelacji z ludzkimi osądami. W AniShift tekst jest ten sam, więc na początek wystarczą exact/F1 granic i ocena par, bez dodawania złożonej metryki MT.

Matusov 2019 [S27], s. 4–7: BiLSTM segmenter plus ograniczenia i adaptacja MT, en→es, dwóch postedytorów; 36,87% wzrostu produktywności dotyczy całego workflow, **nie samego łamania**. Nowszy VC-LLM 2025 [S28] poprawia automatyczną zgodność segmentów chińskich reklam 0,3334→0,9031, ale zmienia cały model i zadanie; nie izoluje polskich `<eol>` ani komfortu widza. W sprawdzonych źródłach nie znaleziono kontrolowanego porównania LLM i lokalnego segmentera polskich wierszy na identycznym tekście. To luka przeglądu, nie twierdzenie o nieistnieniu pracy.

### 6.2 Trzy warianty

| Wariant | Jakość i determinizm | Koszt, cache, wznowienie | Ocena |
|---|---|---|---|
| A: lokalny kod | Zna rzeczywisty font, ten sam tekst daje ten sam układ przy przypiętych wersjach | Zero nowych tokenów API; zmiana wag nie wymaga nowego przekładu | Rekomendowany teraz |
| B: LLM proponuje granice fraz, kod wybiera | Może rozumieć idiom/kontekst; wskazówki niewiążące, walidowane do granic słów | Dodatkowe tokeny i kontrakt; stare przekłady nie zyskują wskazówek bez nowego wywołania | Wykonalny eksperyment po wyczerpaniu lekkiego wariantu |
| C: LLM wyznacza finalne `\N` | Brak wiarygodnej wiedzy o kształcie glifów, marginesach, fallbackach; model może zmienić tekst | Retłumaczenie przy zmianie promptu, niedeterminizm zdalny, ryzyko powtórnej opłaty | Nie zalecam finalnego autorytetu LLM |

**Fakty z kodu:** `line_contract.py` wymaga `[N] tekst`, zachowuje kolejność i ucieczki; `LlmTranslateService._translate_batch` naprawia tylko brakujące numery, a odpowiedzi trzyma w pamięci. `TranslationTaskHandler._translate_subtitles` wywołuje tłumaczenie, potem writer, który wykonuje layout. `RunJournal` zapisuje gotowe zadania i `inflight` dla pracy płatnej/sieciowej; nie jest trwałym cache odpowiedzi każdego batcha i nie zawiera wersji promptu jako klucza wyników. Nie można obiecać odzyskania każdej ukończonej odpowiedzi po awarii przed zapisem produktu.

**Minimalny kontrakt B, gdy zostanie zamówiony:** osobny typ pola z offsetami/spans, nigdy luźna proza ani nowe rekordy `[N]`; usunięcie wskazówek musi odtwarzać dokładny tekst i `<sN>`. Walidacja odrzuca wskazówkę poza granicą słowa, a nie tekst przekładu. Zapisać wersję promptu, model, hash tekstu i wskazówki przy zaakceptowanym przekładzie; układ przechowywać oddzielnie lub deterministycznie regenerować. To zmiana API/writera/persistencji, a nie dopisanie jednego zdania do promptu.

Bez płatnego pomiaru nie podaję ceny w złotych: dodatkowy koszt `ΔC = (ΔTin·Pin + ΔTout·Pout)/10^6 + retry`, z rzeczywistym cennikiem wybranego modelu. Brak osobnego requestu w B nie oznacza zerowego kosztu tokenów. Stary ukończony produkt może być ułożony ponownie lokalnie; żądanie nowych wskazówek wymaga ich osobnego pozyskania.

## 7. P5 — jedna decyzja rozmyta i jej obalenia

### 7.1 Konstrukcja badanego wariantu R0

Wybrano ważoną agregację stopni przynależności i ranking, zamiast silnika Mamdaniego z osobnymi regułami/defuzyfikacją. Takagi–Sugeno nie daje tu korzyści nad jawną sumą czterech kosztów. Wszystkie wartości poniżej są **hipotezami inżynierskimi**, nie parametrami wyprowadzonymi z eye-trackingu.

`rise(x;a,b)=clip((x-a)/(b-a),0,1)`, `fall=1-rise`; reuse `subtitles/fuzzy.py`.

```text
L = max_po_wierszach(max(rise(znaki;32,62), rise(szerokość/ramka;0.65,0.95)))
O = max_po_wierszach(fall(liczba_słów;1,3))  [0 dla jednego wiersza]
A(b) = min(1, suma_przeciętych_łuków(w(relacja)/odległość_słów))
P(b) = 1 po końcu zdania, 0.75 po przecinku/średniku/dwukropku/myślniku, inaczej 0
S(b) = max(ochrona_bazowa_0_lub_1, (0.2 + 0.8*A(b))*(1-P(b)))
S = max(max_po_cięciach(S(b)), 0.7*O)
N = min(1, (liczba_wierszy-1)/2)
B = (najszerszy-najwęższy)/najszerszy  [0 dla jednego wiersza]
Q = 0.50*S + 0.32*L + 0.24*N + 0.06*B
wygrywa najmniejsze Q; remis: mniej wierszy, wcześniejsza granica
```

Waga łuku 1 dla `case,amod,nmod,nummod,flat,fixed,compound,aux,expl,det,mark`, 0,3 dla pozostałych poza `punct/root`. MWT parsera mapuje się do nierozdzielnych słów powierzchniowych; „Mógłbym” nie jest trzema miejscami cięcia. 42 leży na rampie, nie jest przełącznikiem. Można nazwać `rise(c;32,42)` „długi”, ale nasycenie całego kosztu już przy 42 usuwałoby różnicę między 43 a 70; R0 używa szerokiej rampy do 62.

Kandydaci: jeden wiersz i wszystkie cięcia na spacjach; trzy dopiero, gdy żaden z ≤2 nie przejdzie geometrii. Geometria używa `measure_text` i `wrap_text` po odtworzeniu tagów. R0 nie implementuje całego kontraktu produkcyjnego: brak kompletnej ochrony NBSP i jawnych granic mówców, ratunek bez fit nie minimalizuje jeszcze samego overflow. To benchmark sygnału, nie gotowy moduł.

### 7.2 Dwanaście rzeczywistych decyzji R0 ze spaCy

`/` oznacza wiersz, `u` szerokość/ramkę; wektor to `[S,L,N,B]`. Wyniki z `summary.json` i `verification.json`; dokładny tekst wszystkich wariantów jest w JSON. Galeria używa Officiny; przypadki 01–39 własnych profili.

| Przypadek i wynik | u; wektor → Q | Ocena względem celu |
|---|---|---|
| 01: `Uciekaj!` | 0,117; [0,0,0,0] → 0 | Jeden wiersz, poprawnie |
| 03: `Żeby rozwalić zwykłych aniołów, / mógłbym wysadzić w powietrze całą przecznicę razem z nimi.` | 0,479/0,912; [0,070;0,873;0,5;0,475] → 0,463 | Poprawa względem starego `wysadzić / w powietrze`; dłuższy dół uzasadniony |
| 04: `Dlaczego się na mnie z taką złością cały czas patrzysz?` | 0,818; [0;0,767;0;0] → 0,245 | Poprawnie jeden; odległe „się” nie wymusza cięcia |
| 06: `- Idziesz? - Za chwilę. - Poczekajcie!` | 0,530; [0;0,2;0;0] → 0,064 | **Błąd kontraktu mówców**; wymagane trzy osobne kwestie, nie do naprawy samym balansem |
| 07: `Upewniłam się, że wszyscy – a zwłaszcza / Przewodniczący – poszli już do domów.` | 0,796/0,762; [0,801;0,485;0,5;0,042] → 0,678 | **Błąd frazy**. Referencja po pierwszym myślniku ma Q=0,967; odziedziczona ochrona myślnika daje S=1 i źle blokuje wtrącenie |
| 33: `…wyjątkowo długie / spotkanie w obecności wszystkich naszych przyjaciół patrzysz?` | 0,985/0,939; [1;1;0,5;0,046] → 0,943 | **Błąd względem referencji 3-wierszowej, wynik = stary**, choć dwa mieszczą się w tym pomiarze. Referencja Q=0,609, ale nie była generowana; konflikt bramki, nie wag, bez regresji względem starego |
| Galeria 01: `że w obronie interesów klienta / wszystkie chwyty są dozwolone.` | 0,422/0,436; [0,340;0;0,5;0,031] → 0,292 | Jak stary, sensowna granica |
| Galeria 02: `Ludzie zamieszkujący te ziemie / popełnili straszliwe grzechy.` | 0,431/0,394; [0,260;0;0,5;0,086] → 0,255 | Jak stary; nie robi szerokiego pojedynczego wiersza |
| Galeria 05: całość `Za kwestionowanie woli Artemis odbieram ci tytuł kardynała.` | 0,842; [0;0,9;0;0] → 0,288 | **Regresja**; stary podział po Artemis Q=0,407, za duża kara składni |
| Galeria 08: całość `Jednak po rebelii klanu Shi wiele osób zostało stracone.` | 0,768; [0;0,8;0;0] → 0,256 | **Regresja/nadmierna wrażliwość**; stary podział Q=0,256232 przegrywa o 0,000232 |
| Galeria 20: `Przepraszam. Idź z Midorikawą i resztą. / Baw się dobrze.` | 0,500/0,195; [0;0,233;0,5;0,609] → 0,231 | Asymetria przegrywa ze spójnością zdań, zgodnie ze starym |
| Galeria 29: całość `A co w kolejnym odcinku „Grand Blue Dreaming”?` | 0,873; [0;0,744;0;0] → 0,238 | **Regresja**; referencyjne cięcie przed tytułem dostaje S=1, Q=0,621 |

R0 został świadomie pozostawiony z tymi porażkami, zamiast dopisywania wyjątków do galerii. Lepszy wynik agregatu nie wystarcza do akceptacji. Ciągły koszt nie oznacza ciągłego wyniku: `argmin` dwóch dyskretnych układów zawsze ma granicę zmiany zwycięzcy. Można ograniczać wrażliwość, nie obiecywać jej całkowitego usunięcia.

### 7.3 Co ma przejść do specyfikacji, a co nie

Rekomendowana **konstrukcja** to ten sam mały ranking czterech kosztów, z jednym generatorem i jedną oceną na wszystkich przypadkach; liczby R0 nie są rekomendowanymi parametrami produkcyjnymi. Potrzebne poprawki wynikają z klas przyczyn, nie numerów przykładów:

1. Przekazać prawdziwe jednostki wejścia: niełamliwe spacje, spany stylu, jawne zmiany mówcy. To ograniczenia kandydatów, nie estetyczne wyjątki.
2. Oddzielić **lokalnie rozrywaną jednostkę** od dowolnego przeciętego łuku i od niepewności parsera. Nie kodować całego „braku dowodu” jako prawie zakazu cięcia; galeria 29 obala tę strategię.
3. Zachować mocne granice wtrąceń i zdań; koszt sieroty zależny od kompletności wypowiedzi, nie wyłącznie liczby słów. „Przepraszam.” nie jest tym samym co „A co”.
4. Sprawdzić wrażliwość wag i marginesów na niezależnym zbiorze, zamiast podbijać karę długości aż galeria wyjdzie. Zbyt silne S prowadzi do jednego szerokiego wiersza; zbyt silne L do rozrywania fraz.
5. Utrzymać wyjątek trzech wierszy wyłącznie zgodny z przyjętym kontraktem. **33 ujawnia konflikt**: konkretna etykieta chce trzech, choć pomiar dopuszcza dwa. Trzeba rozstrzygnąć etykietę/profil lub dopuścić składniowy ratunek; żaden zestaw wag nie naprawi kandydata wykluczonego bramką.

### 7.4 Katalog zachowań do specyfikacji

Poniższe układy są zaleceniami przy dostatecznej szerokości i braku jawnego ograniczenia źródła, nie deklaracją, że R0 je wszystkie realizuje. Wspólny mechanizm: nienaruszalność treści/spans → dopuszczalne układy i geometria → S/L/N/B. `W` oznacza wytyczne [S3–S6,S14], `P` kontrakt produktu, `D` potrzebną decyzję właściciela. Brak indywidualnego eksperymentu dla danego polskiego zdania.

| Przypadek → przykład | Oczekiwane zachowanie / układ | Uzasadnienie, status |
|---|---|---|
| Bardzo krótki: `Uciekaj!` | Jeden wiersz | N bez korzyści z drugiego; W/P |
| Tuż pod/nad 42: warianty `Nie wiem, czy jutro zdążymy na spotkanie.` z dodanym `wszyscy` | Samo przekroczenie 42 nie wymusza cięcia; ocenić tę samą granicę po przecinku | P, rampy do kalibracji |
| Dwa podobne zdania: `Wrócę jutro. Zaczekaj na mnie.` | Jeden, jeśli zwarty; przy potrzebie dwóch po kropce | S kontra N/L; W |
| Długie + krótkie: `Zrobiłem wszystko, o co mnie prosiłaś. Naprawdę.` | Rozważyć po kropce; nie ciąć frazy dla piramidy | S > małe B; W/D dla skrajnej asymetrii |
| Krótkie + długie: `Wiem. Zrobiłeś wszystko, o co cię prosiłam.` | Ta sama ocena, bez automatycznej nagrody za krótką górę | W/P |
| Trzy+ zdań: `Wiem. Rozumiem. Zaczekam.` | Jeden lub dwa, nie tyle wierszy co zdań | N; W/P |
| Dwie osoby: `- Idziesz? - Za chwilę.` | `- Idziesz? / - Za chwilę.` | Jawna struktura mówców; W/P |
| Trzy osoby | Trzy jawne kwestie zachowane, raport wyjątku | P, przypadek 06; R0 tego nie spełnia |
| Wtrącenie: `wszyscy – a zwłaszcza Przewodniczący – poszli…` | Cięcie przed całym wtrąceniem lub po nim, nie po „zwłaszcza” | S, W/P; błąd R0 nr 07 |
| Nawias: `Znam go (to mój brat) od lat.` | Nawias z zawartością, bez osieroconego znaku | Ograniczenie tokenów + S; W |
| Tytuł: `A co w kolejnym odcinku „Grand Blue Dreaming”?` | `A co w kolejnym odcinku / „Grand Blue Dreaming”?` | Chronić tytuł, ale dopuścić granicę przed nim; P, galeria 29 |
| Imię/nazwisko: `Jan Kowalski czeka na dworcu.` | Nie `Jan / Kowalski`; przy koniecznym ratunku raport | W/P |
| Honoryfikator: `Yamamoto-san`, `Kato-senpai` | Cały token; oddzielny `senpai` ocenić kontekstowo | Grafem/token P; obcy kontekst niepewny |
| Liczba/jednostka: `To waży 20 kg i kosztuje 15 zł.` | `20 kg`, `15 zł` razem | Lokalny span, W/P |
| Data/godzina: `Spotkajmy się 19 października o 17:30.` | Nie rozcinać zapisu godziny, zachować datę jako grupę | Token/S, P |
| Skróty: `np. jutro`, `dr Kowalski`, `tzw. problem` | Kropka skrótu nie jest premiowaną granicą zdania | Reuse `is_false_sentence_break`, P |
| Wielokropek: `…nie wiem, czy wrócę…` | Nie uznawać automatycznie za domknięcie zdania | Może oznaczać zawahanie; W, pełna reguła do specyfikacji |
| `Naprawdę?! Nie wierzę!` | Znaki zostają z tokenem; rozważyć pełne zdania | S i nienaruszalność, W/P |
| Obce słowa: `To było déjà vu, Yamamoto-san.` | Nie zmieniać pisowni; chronić rozpoznaną jednostkę | Parser PL ma niepewność; P |
| Długi wyraz: `najnieprawdopodobniejszy…` | Nigdy nie przeciąć; jeśli nie mieści się, jawny overflow | P, bez ukrytego skrócenia |
| Brak spacji | Jeden nierozdzielny ciąg; overflow jeśli konieczny | P |
| Lokalne `się`: `chcę się uczyć`, `się zakocha` | Chronić lokalny człon orzeczenia, nie przyklejać zawsze do jednej strony | W + polski szyk |
| Odległe `się`: `Dlaczego się… patrzysz?` | Malejący koszt odległego łuku; wolno ciąć pośrednie frazy | P/D, 04 i 33 |
| Jednoliterowe `w/z/i/a` | Nie kończyć nimi wiersza, jeśli jest poprawny wariant | W/P; nie rozciągać na samodzielne wykrzyknienie `O!` |
| `nie`: `nie chciałem`, ale `na nie` | Chronić rzeczywistą negację, odróżnić zaimek | S + kontekst, P |
| `i/a/ale/że/bo/który` | Zwykle początek nowego wiersza z wprowadzaną frazą | W; nie dowodzi tego sam POS |
| `raz na zawsze`, `po prostu`, `w ogóle` | Nie rozcinać wnętrza; granica po całym zwrocie może być poprawna | S; nie obiecywać kompletności słownika |
| `<sN>…</sN>` | Układ na widocznym tekście, znaczniki wracają na te same słowa | P, `restore_markers` |
| Tagi ASS wewnątrz tekstu | Granica tylko w widocznym separatorze; style i kotwice zachowane | P, `reflow_visible_text` |
| `\h` / NBSP | Nie staje się zwykłą spacją przez `.split()` | P; prototyp wymaga adaptera produkcyjnego |
| Nie mieści się w dwóch | Trzy jako ratunek po sprawdzeniu geometrii; brak rozwiązania → jawny overflow | W/P; nie zmieniać treści ani czasu |
| `\q2`, wąskie marginesy | Nie zakładać automatycznego ratunku libass; zmierzyć rzeczywisty obszar i położenie | P; próg 90% z odrzuconej specyfikacji nie jest prawem fizycznym |
| Piosenki/szyldy/rysunki | Poza dialogowym rankingiem; kontrakt `split_lines` szyldów zachowany | P |

## 8. P6 — koszt i integracja

### 8.1 Własne pomiary CPU

Windows x64, CPython 3.14.7; identyfikator CPU zapisany przez `platform.processor`: `Intel64 Family 6 Model 198 Stepping 2, GenuineIntel`. Pomiar pojedynczej sesji, nie kontrolowany benchmark sprzętowy. spaCy batch 64, UDPipe po kwestii, Stanza po kwestii i dwa wątki torch; różnice obejmują te strategie.

| Narzędzie | Załadowanie z importami | Analiza | Peak working set procesu | Estymacja 500 kwestii, bez layoutu |
|---|---:|---:|---:|---:|
| spaCy sm | 5,315 s / 5,069 s | 845: 0,433 s; dodatkowe 392: 0,226 s | 379,20 MB maksimum dwóch przebiegów | ok. 0,27 s + jednorazowe ładowanie |
| UDPipe1 | 1,365 s / 1,459 s | 845: 2,721 s; dodatkowe 392: 1,997 s | 197,97 MB | ok. 1,91 s + ładowanie |
| Stanza charlm | 9,120 s | 1237: 177,422 s | 1122,62 MB | ok. 71,71 s + ładowanie |

Estymacja jest liniowym przeskalowaniem czasu i liczby kwestii, nie bezpośrednim pomiarem konkretnego odcinka; długość i batchowanie zmieniają wynik. Peak obejmuje interpreter i zależności, nie jest samym rozmiarem wag. Stanza z tymi ustawieniami mieści się w kilku minutach, lecz brak korzyści jakościowej nie uzasadnia kosztu.

Wybór i pomiar fontem dla **500 rzeczywistych kolejnych kwestii Shishy**: 2331 kandydatów, **1,733 s** w końcowej kontroli z ciepłym cache fontów i zapisanymi analizami spaCy. Cała ostatnia runda porównania 1281 rekordów, wszystkie systemy i dodatkowe zadanie fixed: **10,925 s**, bez parsowania, obejmuje inicjalizację profili/fontów. To nie czas całego pipeline MKV→MKV.

Koszt dyskowy według plików dystrybucji: UDPipe 2,42 MB + model 25,52 MB; spaCy 92,09 MB + sm 26,68 MB + co najmniej NumPy 42,08 MB i Thinc 9,83 MB, plus pozostałe zależności; Stanza 5,92 MB + torch 476,04 MB + modele około 360,46 MB. Mieszane środowisko badawcze miało 805,18 MB przed dodaniem wag Stanza — **nie przypisywać tej całości spaCy ani Stanzie**. Instalacja Stanza/torch w istniejącym venv trwała 22,321 s, pobranie modeli 24,036 s; zależy to od cache i łącza.

### 8.2 Granice architektury

`layout_translated(...)` pozostaje właścicielem przejścia przekład→układ eventów; `layout_dialogue` miejscem decyzji dialogowej. Zachować publiczne `split_lines(event,text,count,profile)` i `split_for_layout` dla szyldów. Nie przenosić parsera do translation ani nie tworzyć rejestru silników NLP dla jednej wybranej implementacji.

Jeżeli parser przejdzie przyszłą akceptację: lazy-load raz na proces/worker, po raz pierwszy przy potrzebnym dialogu; analiza tego samego tekstu raz, geometria osobno dla eventów. Nie pobierać modelu przy imporcie. Przypiąć wersję i hash; brak/uszkodzenie modelu ma jawnie włączyć istniejący stary algorytm. Wynik parsera musi być mapowany do offsetów tekstu bez tagów; przy błędzie wyrównania fallback, a nie zgadywanie indeksów. Testy z zapisanymi analizami mają badać kontrakt decyzji, osobny smoke rzeczywisty model i zgodność offsetów.

Tagi: `strip_span_markers` → wybór granic na niezmienionym tekście → `restore_markers` → istniejące `reflow_visible_text` lub `replace_visible_text`; pomiar po przypisaniu docelowego stylu i kotwic. W benchmarku sprawdzono zachowanie słów oraz baseline, **nie dowiedziono pełnego round-trip wszystkich `<sN>`, gradientów i `\h`**. Pełna integracja musi zachować istniejące testy tych kontraktów.

## 9. Rekomendacja i kryteria przyjęcia

**Decyzja teraz:** stary rdzeń zostaje punktem odniesienia; R0 nie jest kandydatem do merge. Następna próba powinna porównać minimalną korektę starego rdzenia bez parsera z tą samą korektą wspartą przez `spaCy sm`, przy zachowaniu geometrii i kontraktów, ale dopiero po specyfikacji rozwiązującej konflikty 06/07/33/29. spaCy jest szybkim kandydatem eksperymentalnym, nie wykazanym zwycięzcą jakości samego cięcia. UDPipe1 jest mniejszy i porównywalny w tej próbie, jednak ograniczenie NC modelu utrudnia bezwarunkową dystrybucję. Nie ma podstaw do PyTorcha ani zmiany promptu tłumaczenia.

**Proponowane kryteria do zatwierdzenia — nie nowe strażniki repo:**

1. Zero zmian tekstu, czasów, znaczników znaczenia, grafemów i szyldowego API; identyczny wynik po ponownym layoutowaniu.
2. Zgodność 39/39 dopiero po uzgodnieniu referencji z właścicielem, z zapisanym pochodzeniem każdej decyzji; rozstrzygnięcie 33 zamiast dopasowywania kodu do sprzecznych przesłanek.
3. Brak regresji w sześciu obowiązkowych kadrach, także z Officiną i przy x2; nowe przypadki oceniane w ślepym porównaniu stare/nowe/remis.
4. Osobny holdout co najmniej 300 dwuwierszowych kwestii **z kilku serii**, plus całe odcinki z jednowierszowymi. Minimalnie dwa niezależne osądy miejsc spornych; dopuszczalne alternatywne granice zamiast jednego arbitralnego gold.
5. Raportować osobno exact/F1 granic, liczbę wierszy, naruszenia klas językowych, overflow/auto-wrap, zgubione tagi, czas i pamięć. Nie uznawać zwiększenia zgodności CPL za poprawę czytelności.
6. Zysk jakości musi utrzymać się przy zmianie wag o ±10% i na nowych odcinkach; wariant ciężki wymaga dodatniej przewagi w sparowanym porównaniu i materialnego zysku ocen właściciela. Roboczy budżet: 500 kwestii <120 s na tym komputerze, włącznie z pierwszym ładowaniem; liczba do zatwierdzenia, nie wynik naukowy.

## 10. Ryzyka i nierozstrzygnięcia

- **Nie ma gotowych zaakceptowanych wag.** Własny prototyp ujawnia regresje, a podmiana parsera ich nie usuwa. Nie przedstawiam samej formuły jako rozwiązania produkcyjnego.
- **Konflikt trzech wierszy w 33:** etykieta vs bramka dwóch mieszczących się wierszy. To decyzja celu/profilu, nie drobna kalibracja.
- **Domena i gold:** 392 z jednego dokumentu, 64 łamania z dwóch odcinków; znana zgodność z referencją nie jest oceną wszystkich poprawnych układów.
- **Model ciężki:** zmierzono Stanza charlm, nie najsilniejszy dostępny transformer. Brak przewagi tego modelu nie dowodzi braku możliwej przewagi Trankit-large/COMBO; nie ma jednak dowodu uzasadniającego dalszy ciężar produkcyjny.
- **Licencje i dostarczenie:** wybór lokalnego narzędzia nie rozstrzyga zgodności bundlowania modelu z licencją projektu. NC UDPipe i GPL polskiego spaCy są realnymi różnicami, nie licencją samego wrappera.
- **Pomiar obrazu:** obecna geometria aplikacji jest sprawdzonym wcześniej narzędziem, lecz tutaj nie powtórzono walidacji libass. Udział szerokości i liczba wierszy nie rozpoznają treści obrazu.
- **Zakres dowodu:** nie przeprowadzono pełnego niezależnego znakowania wszystkich klas błędów, nowego badania widzów ani płatnego porównania LLM. Te brakujące dowody są nazwane, nie zastąpione deklaracją sukcesu.

## 11. Odtwarzalność i artefakty

Interpreter **PY**: `C:/Users/MATTYM~1/AppData/Local/Temp/lb-research/astra/venv/Scripts/python.exe`.
Modele: `C:/Users/MATTYM~1/AppData/Local/Temp/lb-research/astra/models/`.
W poniższych poleceniach `${PY}` i `${E}` oznaczają pełne ścieżki z tego raportu; cudzysłowy są konieczne dla ścieżek Windows.

```bash
PYTHONIOENCODING=utf-8 "${PY}" -B "${E}/prepare.py"
PYTHONIOENCODING=utf-8 "${PY}" -B "${E}/models.py" udpipe
PYTHONIOENCODING=utf-8 "${PY}" -B "${E}/models.py" stanza
PYTHONIOENCODING=utf-8 "${PY}" -B "${E}/analyze.py" spacy
PYTHONIOENCODING=utf-8 "${PY}" -B "${E}/analyze.py" udpipe
HF_HOME="C:/Users/MATTYM~1/AppData/Local/Temp/lb-research/astra/hf" PYTHONIOENCODING=utf-8 "${PY}" -B "${E}/analyze.py" stanza
PYTHONIOENCODING=utf-8 "${PY}" -B "${E}/gallery_context.py"
PYTHONIOENCODING=utf-8 "${PY}" -B "${E}/benchmark.py"
PYTHONIOENCODING=utf-8 "${PY}" -B "${E}/summarize.py"
PYTHONIOENCODING=utf-8 "${PY}" -B "${E}/verify.py"
PYTHONIOENCODING=utf-8 "${PY}" -B "${E}/error_audit.py"
PYTHONIOENCODING=utf-8 "${PY}" -B "${E}/metadata.py"
```

`analyze.py` uzupełnia zapisany cache: ponowne uruchomienie na kompletnym pliku zmierzy **zero nowych tekstów**, nie powtórzy podanego benchmarku. Do nowego pomiaru użyć oddzielnego katalogu z kopią danych/skryptu i bez `analysis-*.json`; nie usuwać dowodów starego przebiegu. `human-corpus/` ma własne `acquire.py`, `build_records.py`, `verify.py`; uruchomić je tym samym interpreterem przed `analyze.py`, jeśli odtwarzamy zbiór od zera. `literature/download_extract.py` pobiera pięć źródłowych PDF-ów. `models.py` zapisuje manifest na nowo; odtworzenie pobrania przeprowadzać na kopii eksperymentu, nie nadpisując pomiaru historycznego.

Najważniejsze pliki: `dataset.json` (pochodzenie), `analysis-*.json` (łuki i czasy), `benchmark.json` (każda decyzja i trzech najlepszych kandydatów), `summary.json` (porównania sparowane, rozmiary i hashe), `verification.json` (889 zgodności baseline, zachowanie słów dla 1281 rekordów, pomiar 500), `error-audit.json` (jawne spany), `metadata.json` (PyPI i metryki), `literature/evidence.md` (strony PDF, zakres dostępu).

Model UDPipe pobrany z [S29]: SHA-256 `ffe6ab0f604f88f82a7d8e8096d94491f99336d0d4c8e2b9700d28190f352e46`, 25 523 919 B; manifest `download-udpipe.json`. Stanza: osiem plików modeli plus `resources.json`, hashe w `download-stanza.json`. Shisha: SHA-256 `d16e93af5b8a6d3d6df503c0b2663776069b351afc98d980f251c12e7769da10` i `63d9854c39250d8a2b684ee647e487becfee2c023cf138b748b3cf865a472f16`; SRT filmu `0bae077bb89a468d5df79e91f590485213e37348a32438cb424687f99721428e`.

## 12. Źródła

- **S1:** Gerber-Morón, Szarkowska, *Line breaks in subtitling: an eye tracking study on viewer preferences* (2018), metody, wyniki eksperymentów 1–2: <https://pmc.ncbi.nlm.nih.gov/articles/PMC7733619/>; DOI <https://doi.org/10.16910/jemr.11.3.2>.
- **S2:** *The impact of text segmentation on subtitle reading*, metody i tabele 9–16: <https://pmc.ncbi.nlm.nih.gov/articles/PMC7901653/>.
- **S3:** Netflix, Polish Timed Text Style Guide, §§3,7,8,12,16, ostatni change log 2025-10-17: <https://partnerhelp.netflixstudios.com/hc/en-us/articles/216787928-Polish-Timed-Text-Style-Guide>.
- **S4:** BBC Subtitle Guidelines v1.2.5, §§3.1–3.10: <https://www.bbc.co.uk/accessibility/forproducts/guides/subtitles/>.
- **S5:** Fundacja Kultury bez Barier, *Napisy dla osób niesłyszących i słabosłyszących — zasady tworzenia* (2019), s. 2–4,10–11 PDF: <https://kulturabezbarier.org/wp-content/uploads/2019/12/Napisy-dla-nieslyszacych_zasady-tworzenia_2019.pdf>.
- **S6:** Karamitroglou (1998), *A Proposed Set of Subtitling Standards in Europe*: <https://translationjournal.net/journal/04stndrd.htm>.
- **S7:** Karakanta, Negri, Turchi (2020), *Is 42 the Answer to Everything in Subtitling-oriented Speech Translation?*, s. 4–8 PDF: <https://aclanthology.org/2020.iwslt-1.26/>; <https://aclanthology.org/2020.iwslt-1.26.pdf>.
- **S8:** Karakanta, Negri, Turchi (2020), *MuST-Cinema*, s. 3–7 PDF: <https://aclanthology.org/2020.lrec-1.460/>; <https://aclanthology.org/2020.lrec-1.460.pdf>.
- **S9:** Karakanta, Buet, Cettolo, Yvon (2022), *Evaluating Subtitle Segmentation for End-to-end Generation Systems*, s. 2–8 PDF: <https://aclanthology.org/2022.lrec-1.328.pdf>.
- **S10:** Perego i in. (2010), *The cognitive effectiveness of subtitle processing*, tylko abstrakt/omówienia: <https://doi.org/10.1080/15213269.2010.502873>.
- **S11:** Dyson, Kipping (1998), *The Effects of Line Length and Method of Movement on Patterns of Reading from Screen*, abstrakt: <https://journals.uc.edu/index.php/vl/article/view/5671>.
- **S12:** Dyson (2004), *How physical text layout affects reading from screen*, abstrakt, BIT 23(6),377–393: <https://doi.org/10.1080/01449290410001715714>.
- **S13:** DCMP Captioning Key — Text: <https://dcmp.org/learn/597-captioning-key---text>.
- **S14:** Netflix General Requirements §4: <https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617-Timed-Text-Style-Guide-General-Requirements>.
- **S15:** Universal Dependencies, opis relacji i polszczyzny: <https://universaldependencies.org/u/dep/>; <https://universaldependencies.org/pl/index.html>.
- **S16:** UDPipe1, modele UD2.5, licencja i §1.4 performance: <https://ufal.mff.cuni.cz/udpipe/1/models>; <https://github.com/ufal/udpipe/blob/master/LICENSE>; <http://hdl.handle.net/11234/1-3131>.
- **S17:** spaCy metadata 3.8.0, `license`, `sources`, `performance`: <https://raw.githubusercontent.com/explosion/spacy-models/master/meta/pl_core_news_sm-3.8.0.json>; <https://raw.githubusercontent.com/explosion/spacy-models/master/meta/pl_core_news_md-3.8.0.json>; <https://raw.githubusercontent.com/explosion/spacy-models/master/meta/pl_core_news_lg-3.8.0.json>.
- **S18:** Stanza performance, jawna wersja tabeli i zastrzeżenia licencji: <https://stanfordnlp.github.io/stanza/performance.html>; wagi <https://huggingface.co/stanfordnlp/stanza-pl>; kod <https://github.com/stanfordnlp/stanza/blob/main/LICENSE>.
- **S19:** UDPipe2, status prototypu i lokalne źródła: <https://ufal.mff.cuni.cz/udpipe/2>; <https://github.com/ufal/udpipe/tree/udpipe-2>.
- **S20:** Trankit, tabela `large`: <https://trankit.readthedocs.io/en/latest/performance.html>; ograniczenie torch <https://pypi.org/pypi/trankit/1.1.2/json>.
- **S21:** COMBO: <https://gitlab.clarin-pl.eu/syntactic-tools/combo-nlp>; zależności <https://pypi.org/pypi/combo-nlp/4.0.14/json>.
- **S22:** Morfeusz: <http://morfeusz.sgjp.pl/>; koła <https://pypi.org/pypi/morfeusz2/1.99.15/json>.
- **S23:** Concraft <https://github.com/kawu/concraft-pl>; KRNNT <https://github.com/kwrobel-nlp/krnnt>. Toygger: brak dostatecznie zweryfikowanego źródła w tym przeglądzie.
- **S24:** HerBERT <https://huggingface.co/allegro/herbert-base-cased>; runtime <https://pypi.org/pypi/onnxruntime/1.31.0/json>.
- **S25:** <https://pypi.org/pypi/nltk/3.10.3/json>; <https://pypi.org/pypi/polyglot/16.7.4/json>; <https://pypi.org/pypi/pyicu/2.16.2/json>.
- **S26:** Wydawca filmu, atrybucja napisów: <https://www.stealthisfilm.com/Part2/download.php>; oryginalny SRT <https://www.stealthisfilm.com/subtitles/Steal%20This%20Film%20II.pl.srt>. Shisha: lokalne `shisha-report.md`, `shisha-original/`, źródło <http://animesub.info/forum/viewtopic.php?id=263801> i wskazany tam folder <https://mega.nz/folder/dHoEwRRa#MheeXN4HTypR_XSxrBCe9Q>.
- **S27:** Matusov, Wilken, Georgakopoulou (2019), *Customizing Neural Machine Translation for Subtitling*, s. 4–7: <https://aclanthology.org/W19-5209.pdf>.
- **S28:** Qian i in. (2025), *VC-LLM*, §§4.2,5.2,6.2–6.3, tabela 1: <https://arxiv.org/html/2504.05673v1>.
- **S29:** Użyty plik UDPipe: <https://raw.githubusercontent.com/jwijffels/udpipe.models.ud.2.5/master/inst/udpipe-ud-2.5-191206/polish-pdb-ud-2.5-191206.udpipe>.
- **S30:** PyPI manifesty badanych runtime: <https://pypi.org/pypi/ufal.udpipe/1.4.0.1/json>; <https://pypi.org/pypi/spacy/3.8.16/json>; <https://pypi.org/pypi/stanza/1.15.0/json>; <https://pypi.org/pypi/torch/2.14.1/json>.

Źródła lokalne: `visual-quality.md`, `fuzzy-line-breaks.md`, pięć wcześniejszych raportów w tym katalogu, `fuzzy-spec/cases/model-v32.md`, galeria `obecny-vs-nowe-lamanie/index.md`, oba `linebreak.py` (`fuzzy` i `q-breaks`), `geometry.py`, `text.py`, `translation/engines/llm/{service,line_contract}.py`, `application/{translation_handler,recovery}.py`. Wyniki wcześniejszego researchu, np. p90 zgodności z libass 1,14%, **nie są własnymi pomiarami tego raportu**.

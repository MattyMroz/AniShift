# Przyszły etap: silnik layoutu i jakości napisów

Status: plan przyszłego, samodzielnego etapu po ukończeniu bieżącego planu.
Dokument nie opisuje gotowej implementacji i nie rozszerza zakresu obecnego PR.

## 1. Cel i zakres

Dokument zbiera zasady potrzebne do automatycznego łamania polskiego tekstu
w napisach ASS. Łączy trzy różne warstwy, których nie należy mieszać:

1. **reguły techniczne Unicode i ASS** — gdzie podział jest w ogóle możliwy;
2. **polską składnię i typografię** — których elementów zdania nie należy
   rozdzielać;
3. **praktykę napisową** — maksymalną liczbę wersów, czytelność, kształt
   napisu i znaczenie oryginalnego układu.

To nie jest pełny podręcznik polskiej typografii ani specyfikacja wszystkich
tagów ASS. Mapowanie tagów ASS i zmiany w parserze są osobnym, późniejszym
zadaniem.

Ustalona konwencja nazw plików pozostaje bez zmian:

```text
{nazwa}.pl.ass
{nazwa}.spoken.pl.ass
{nazwa}.displayed.pl.ass
```

## 2. Najważniejsza decyzja

Algorytm nie powinien odtwarzać `\N` wyłącznie na podstawie proporcji długości
oryginalnych wersów.

Proporcja, na przykład `9 : 17`, jest użyteczną informacją o zamierzonym
układzie, ale może być tylko jednym z kryteriów. Po tłumaczeniu zmieniają się
szyk, długość słów i granice fraz. Podział, który zachowuje proporcję, lecz
rozrywa polską jednostkę składniową, jest gorszy od mniej równego podziału
zgodnego ze składnią.

Kolejność ważności powinna być następująca:

1. nie uszkodzić tekstu, grafemów, tagów ani twardych separatorów;
2. nie utworzyć zabronionego podziału interpunkcyjnego;
3. zachować polskie jednostki składniowe i znaczeniowe;
4. uszanować funkcję oryginalnego podziału;
5. zmieścić tekst w profilu szerokości;
6. dopiero potem optymalizować proporcję i kształt wersów.

Badanie z udziałem między innymi polskich widzów wykazało preferencję dla
podziałów zgodnych ze składnią. Polscy uczestnicy częściej wskazywali jednostki
semantyczne i składniowe niż kształt piramidy jako podstawę wyboru
([Gerber-Morón i Szarkowska, 2018](https://discovery.ucl.ac.uk/id/eprint/10051115/)).

## 3. Poziomy reguł

W przyszłym algorytmie każda potencjalna granica między tokenami powinna
otrzymać jeden z czterech poziomów.

| Poziom | Znaczenie | Zachowanie |
|---|---|---|
| `FORBIDDEN` | podział technicznie lub językowo błędny | kandydat jest odrzucany |
| `STRONG_AVOID` | podział wyraźnie pogarsza składnię lub czytelność | używany tylko przy braku poprawnej alternatywy |
| `NEUTRAL` | poprawna, lecz niewyróżniająca się granica | oceniana przez pozostałe kryteria |
| `PREFERRED` | naturalna granica składniowa lub interpunkcyjna | otrzymuje premię |

Jeśli wszystkie granice są zabronione, algorytm nie powinien rozcinać wyrazu.
Powinien pozostawić przekroczony limit, użyć jednego wersu albo zgłosić
kontrolowane przepełnienie. Dla napisów łamanie wewnątrz wyrazu jest gorszym
fallbackiem niż umiarkowanie zbyt długi wers.

## 4. Twarde zakazy

### 4.1. Grafem, wyraz i tekst techniczny

Nie wolno dzielić:

- wewnątrz klastra grafemowego, na przykład między literą a znakiem
  diakrytycznym lub wewnątrz złożonego emoji;
- wewnątrz zwykłego wyrazu;
- bezpośrednio przed polskim znakiem zamykającym;
- bezpośrednio po znaku otwierającym;
- w miejscu objętym twardą spacją ASS `\h`;
- wewnątrz liczby, daty, godziny, adresu, ścieżki, URL-a lub adresu e-mail;
- wewnątrz tokenu kontrolnego albo tagu ASS.

Unicode UAX #14 dostarcza dobry poziom bazowy: zabrania między innymi podziału
przed zamykającą interpunkcją, po otwierającej interpunkcji, wewnątrz liczb
i między literami tworzącymi wyraz. Sam standard zaznacza jednak, że wybór
optymalnego miejsca wymaga dostosowania językowego i analizy wyższego poziomu
([Unicode UAX #14](https://unicode.org/reports/tr14/)).

### 4.2. Interpunkcja

Drugi wers nie może zaczynać się od:

```text
, . ; : ! ? … % ‰ ° ) ] } » ” ’
```

Pierwszy wers nie może kończyć się otwierającym znakiem:

```text
( [ { „ «
```

Znaki zamykające należą do tekstu po ich lewej stronie, a znaki otwierające do
tekstu po prawej. Wielokropek powinien pozostać jednym znakiem `…` i nie może
zostać odłączony od poprzedzającego słowa.

Przykłady:

```text
ŹLE:
Powiedział (
że wróci).

ŹLE:
Powiedział, że wróci
.

DOBRZE:
Powiedział,
że wróci.
```

### 4.3. Jednostki nierozdzielne

Jako `FORBIDDEN` należy potraktować co najmniej:

- imię i nazwisko: `Jan Kowalski`;
- inicjał i nazwisko: `J. Kowalski`;
- tytuł lub skrót tytułu i nazwisko: `prof. Kowalski`;
- liczbę i jednostkę: `10 km`, `40 osób`, `20 zł`;
- numer i jego określenie: `str. 2`, `rozdz. 4`;
- pełną datę i godzinę;
- człony liczby oraz zakres liczbowy: `10–20`;
- wieloczłonowy wyraz z dywizem: `biało-czerwony`;
- dwuczłonową nazwę własną, jeśli została rozpoznana: `Nowy Sącz`;
- operator lub symbol związany z operandem, jeśli tekst ma charakter
  matematyczny albo techniczny.

Polskie materiały typograficzne wymieniają między innymi liczbę z jednostką,
tytuł z nazwiskiem, inicjał z nazwiskiem i numer części jako miejsca wymagające
odstępu niełamliwego
([polskie wprowadzenie do LaTeX-a](https://www.fuw.edu.pl/~grzelak/PTI/lshort2e_pl.pdf)).

Linebreaker ma jedynie chronić jednostkę, a nie poprawiać jej zapis. Dotyczy to
także procentów: profile redakcyjne mogą używać zarówno `2%`, jak i `2 %`.
Oba warianty powinny pozostać nierozdzielne.

## 5. Polskie związki składniowe

### 5.1. Jednoliterowe wyrazy

Jednoliterowe spójniki i przyimki nie powinny pozostawać na końcu wersu.
Podstawowy zestaw to:

```text
a i o u w z
```

Poprawny podział następuje **przed** takim wyrazem albo dopiero po całej
tworzonej przez niego grupie:

```text
ŹLE:
Spotkamy się w
domu.

DOBRZE:
Spotkamy się
w domu.
```

Ta reguła jest obecna zarówno w polskich zaleceniach napisowych, jak
i typograficznych
([Fundacja Kultury bez Barier, 2019](https://dostepna.malopolska.pl/images/wydawnictwa/Napisy-dla-nieslyszacych_zasady-tworzenia_2019.pdf),
[Zintegrowana Platforma Edukacyjna](https://zpe.gov.pl/a/przeczytaj/DG2whzY8q)).

Nie jest to jednak bezwarunkowe prawo polskiej typografii dla każdego
krótkiego wiersza. Poradnia Językowa Uniwersytetu Łódzkiego wskazuje, że przy
wierszach krótszych niż 40 znaków usuwanie wszystkich takich „sierot” nie jest
obligatoryjne, bo może pogorszyć odstępy i czytelność
([Poradnia Językowa UŁ](https://www.poradnia-jezykowa.uni.lodz.pl/szczegoly/sieroty-na-koncu-wiersza)).
Napisy nie są jednak justowanym składem książkowym, a polskie wytyczne
napisowe osobno zalecają nie zostawiać spójników i przyimków na końcu. Dla
AniShift powinna to być zatem bardzo silna kara, nie techniczny zakaz Unicode.

Nie należy automatycznie rozszerzać twardego zakazu na **wszystkie** wyrazy
dwu- i trzyliterowe. Niektóre wydawnictwa tak robią we własnym profilu
redakcyjnym, lecz nie jest to uniwersalna reguła polskich napisów. Krótkie
wyrazy można objąć karą estetyczną, a nie globalnym zakazem.

### 5.2. Przyimek z grupą nominalną

Nie rozdzielamy przyimka od rzeczownika, zaimka lub początku grupy, którą
wprowadza:

```text
ŹLE:
Wracam do
mojego starego domu.

DOBRZE:
Wracam
do mojego starego domu.
```

Jednocześnie podział **przed** przyimkiem jest często dobrym kandydatem.
Zalecenie „dziel przed przyimkiem” nie oznacza więc „oddziel przyimek od
rzeczownika”. Oznacza: przenieś całą frazę przyimkową do następnego wersu.

Wielowyrazowe przyimki trzeba najpierw rozpoznać wewnętrznie, na przykład:

```text
ze względu na
w związku z
bez względu na
z powodu
na podstawie
```

Nie zawsze da się utrzymać taki przyimek wraz z całym bardzo długim
dopełnieniem, ale nie należy rozrywać samego wyrażenia przyimkowego.

### 5.3. `nie` z czasownikiem

Partykuła `nie` i czasownik stanowią dla łamania napisów jedną jednostkę.

```text
ŹLE:
Proszę, nie
biegaj.

DOBRZE:
Proszę,
nie biegaj.
```

Dotyczy to również konstrukcji wielowyrazowych, w których `nie` neguje
orzeczenie:

```text
nie będzie biegać
nie mógł odpowiedzieć
nie powinien był wychodzić
```

Polskie wytyczne dla napisów wprost zabraniają oddzielania partykuły `nie` od
czasownika. Ogólne zalecenia Netflixa także nie pozwalają oddzielać czasownika
od negacji
([Fundacja Kultury bez Barier, 2019](https://dostepna.malopolska.pl/images/wydawnictwa/Napisy-dla-nieslyszacych_zasady-tworzenia_2019.pdf),
[Netflix — General Requirements](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617-Timed-Text-Style-Guide-General-Requirements)).

Samo wykrycie słowa `nie` wyrażeniem regularnym nie wystarczy. `Nie` może
negować również rzeczownik, przymiotnik, liczebnik albo całą frazę. Docelowy
algorytm powinien co najmniej rozpoznawać formę czasownikową po prawej stronie,
a przy braku analizy morfosyntaktycznej stosować ostrożną karę zamiast
nieograniczonego zakazu.

### 5.4. `się` z czasownikiem

Zaimka zwrotnego `się` nie oddzielamy od czasownika, z którym tworzy
orzeczenie:

```text
ŹLE:
On boi
się ciemności.

ŹLE:
On się
boi ciemności.

DOBRZE:
On
się boi ciemności.
```

Polskie wytyczne napisowe wymieniają tę relację wprost. W praktyce trzeba
obsłużyć oba szyki: `boi się` i `się boi`.

### 5.5. Czasownik z elementami orzeczenia

Silnie unikamy rozdzielania:

- czasownika posiłkowego od formy głównej: `będzie biegać`;
- czasownika modalnego od bezokolicznika: `musi wyjść`;
- form czasu przeszłego i przyszłego złożonego;
- czasownika od krótkiego zaimka dopełnieniowego, jeśli tworzą ścisłą całość;
- orzeczenia imiennego, jeśli podział tworzy fałszywe oczekiwanie znaczeniowe.

Nie każdy taki podział jest błędem gramatycznym. Dlatego jest to zwykle
`STRONG_AVOID`, a nie zawsze `FORBIDDEN`.

### 5.6. Grupa nominalna

Silnie unikamy rozdzielania:

- przymiotnika od rzeczownika: `czerwony samochód`;
- liczebnika od rzeczownika: `trzy osoby`;
- zaimka wskazującego od rzeczownika: `ten człowiek`;
- nazwy własnej na części;
- określenia od elementu określanego.

Przy długiej grupie należy wybierać najwyższą dostępną granicę składniową, a nie
mechanicznie trzymać całą grupę za wszelką cenę.

```text
LEPIEJ:
Niezwykle stary
drewniany dom

GORZEJ:
Niezwykle stary drewniany
dom
```

### 5.7. Spójniki

Nie zostawiamy spójnika na końcu pierwszego wersu. Granica **przed** spójnikiem
jest zwykle lepsza:

```text
ŹLE:
Chciałem zostać, ale
musiałem wrócić.

DOBRZE:
Chciałem zostać,
ale musiałem wrócić.
```

Nie jest to bezwzględny zakaz dla każdego wyrazu mogącego pełnić funkcję
spójnika. Funkcja słowa zależy od zdania. Bez parsera składniowego rozsądny jest
słownik najczęstszych spójników połączony z interpunkcją i ostrożną karą.

## 6. Naturalne miejsca podziału

Kandydaci powinni otrzymywać premię w tej kolejności:

1. po końcu zdania;
2. po średniku, dwukropku albo przecinku rozdzielającym zdania składowe;
3. przed spójnikiem rozpoczynającym pełną frazę lub zdanie;
4. przed pełną frazą przyimkową;
5. między samodzielnymi grupami składniowymi;
6. w zwykłej granicy między słowami.

Nie każda interpunkcja jest automatycznie dobrym miejscem. Przecinek może
znajdować się wewnątrz krótkiego wtrącenia, a dwukropek może silnie wiązać
krótką zapowiedź z następującą treścią. Punktacja powinna uwzględniać długość
obu powstałych wersów.

Polskie zalecenia dla napisów mówią, że każdy napis powinien tworzyć całość
składniową, najlepiej zakończoną interpunkcją. Ogólne wytyczne Netflixa
preferują podział po interpunkcji oraz przed spójnikiem lub przyimkiem
([Fundacja Kultury bez Barier, 2019](https://dostepna.malopolska.pl/images/wydawnictwa/Napisy-dla-nieslyszacych_zasady-tworzenia_2019.pdf),
[Netflix — General Requirements](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617-Timed-Text-Style-Guide-General-Requirements)).

## 7. Myślnik, półpauza i dywiz

Te znaki mają różne funkcje i wymagają osobnych reguł.

### 7.1. Znak dialogu

Myślnik lub stosowany w plikach napisowych dywiz dialogowy rozpoczyna kwestię
i należy do następującej po nim wypowiedzi:

```text
- Kim jesteś?
- Nikim ważnym.
```

Nie wolno zostawić samego znaku na końcu wersu ani oddzielić go od pierwszego
słowa. Gdy jeden event zawiera dwóch rozmówców, każda kwestia powinna zajmować
osobny wers i stanowić samodzielną całość. Taką konwencję opisują zarówno
polskie wytyczne dostępnościowe, jak i polski przewodnik Netflixa
([Fundacja Kultury bez Barier, 2019](https://dostepna.malopolska.pl/images/wydawnictwa/Napisy-dla-nieslyszacych_zasady-tworzenia_2019.pdf),
[Netflix — Polish Timed Text Style Guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/216787928-Polish-Timed-Text-Style-Guide)).

### 7.2. Myślnik wewnątrz zdania

Myślnik interpunkcyjny jest otoczony spacjami. Polska tradycja składu zaleca,
aby nie przenosić go samotnie na początek następnego wiersza. Dla napisów
traktujemy to jako silną preferencję, a nie uniwersalny zakaz: przy bardzo
wąskim polu i dwóch wersach może nie istnieć idealne rozwiązanie.

```text
PREFEROWANE:
To było niemożliwe –
a jednak próbował.

UNIKAĆ:
To było niemożliwe
– a jednak próbował.
```

Wyjątkiem jest oczywiście myślnik będący znacznikiem nowej kwestii dialogowej.
Wtedy jego prawidłowym miejscem jest początek wersu.

Zalecenie o nieprzenoszeniu pauzy na początek pochodzi z tradycyjnego składu
drukarskiego i było formułowane dla szerokich wierszy. Nie należy udawać, że
jest bezwzględnym prawem dla wszystkich napisów
([Janusz Nowacki, „TeXnologia a typografia”](https://poledyt.amu.edu.pl/download/Janusz%20Nowacki.pdf)).

### 7.3. Dywiz wewnątrz wyrazu

Dywiz w `biało-czerwony` nie jest myślnikiem. Druk dopuszcza podział takiego
wyrazu przy zachowaniu określonych reguł, lecz AniShift nie powinien dzielić
wyrazów w napisach. Cały token pozostaje w jednym wersie:

```text
bardzo jasny
biało-czerwony znak
```

### 7.4. Półpauza w zakresach i relacjach

Zakresy i połączenia typu `10–20`, `Warszawa–Kraków` oraz wynik meczu powinny
pozostać nierozdzielne. Półpauza bez spacji działa tu wewnątrz jednej jednostki,
a nie jako granica zdania.

Rada Języka Polskiego rozróżnia interpunkcyjny myślnik lub półpauzę od
ortograficznego łącznika
([RJP PAN](https://rjp.pan.pl/roznice-miedzy-myslnikiem-polpauza-a-lacznikiem/)).

## 8. Cudzysłowy, nawiasy i wtrącenia

Otwierający cudzysłów lub nawias wiąże się z następującym tekstem, a zamykający
z poprzedzającym:

```text
ŹLE:
Powiedział: „
Wracam jutro”.

DOBRZE:
Powiedział:
„Wracam jutro”.
```

Jeżeli cały cytat lub krótkie wtrącenie mieści się w jednym wersie, warto go
zachować razem. Długiego cytatu nie trzeba traktować jako niepodzielnego:
wewnątrz stosuje się zwykłe reguły składniowe, pilnując par znaków.

## 9. Zasady specyficzne dla napisów

### 9.1. Liczba wersów i szerokość

Profil docelowy powinien mieć konfigurowalne limity. Dwa użyteczne punkty
odniesienia to:

- do 40 znaków na wers i najwyżej dwa wersy w polskich wytycznych Fundacji
  Kultury bez Barier;
- 42 znaki na wers i najwyżej dwa wersy w polskim profilu Netflixa.

Nie są to prawa języka polskiego ani uniwersalne wartości dla każdego stylu
ASS. Czytelna szerokość zależy też od fontu, rozmiaru, skalowania, marginesów,
pozycji i rozdzielczości. Liczenie samych znaków jest przybliżeniem.

### 9.2. Jeden czy dwa wersy

Jeżeli cały tekst mieści się bezpiecznie w jednym wersie, nie należy tworzyć
dwóch tylko po to, aby odtworzyć historyczne `\N`. Wyjątkiem jest authored
layout, który sam niesie znaczenie lub jest częścią typesettingu ekranowego.

Netflix zaleca zwykle jeden wers, a dwa dopiero po przekroczeniu limitu.
Polskie wytyczne dostępnościowe dopuszczają maksymalnie dwa wersy, z wyjątkami
dla szczególnych programów
([Netflix — Polish Timed Text Style Guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/216787928-Polish-Timed-Text-Style-Guide),
[Fundacja Kultury bez Barier, 2019](https://dostepna.malopolska.pl/images/wydawnictwa/Napisy-dla-nieslyszacych_zasady-tworzenia_2019.pdf)).

### 9.3. Kształt napisu

Przy kilku równie dobrych podziałach preferujemy:

- brak jedno- lub dwuwyrazowego osamotnionego wersu;
- umiarkowanie zbliżone długości;
- przy napisach u dołu ekranu krótszy wers górny i dłuższy dolny;
- zachowanie przybliżonej proporcji oryginalnych wersów, jeśli oryginalny
  układ był świadomy.

Kształt jest kryterium pomocniczym. Nie może wygrać ze składnią. Polski
przewodnik Netflixa preferuje „cięższą” dolną linię, a polskie wytyczne
dostępnościowe uzasadniają krótszą górną linię mniejszym zasłanianiem obrazu.

### 9.4. Dwie osoby w jednym evencie

Każdy rozmówca otrzymuje osobny wers. Wers zaczyna się znacznikiem dialogowym
i powinien zawierać zamkniętą kwestię:

```text
- Idziesz?
- Za chwilę.
```

Nie próbujemy równoważyć takich wersów kosztem połączenia wypowiedzi ani
przenosić jednej kwestii do wersu drugiego rozmówcy.

### 9.5. Tekst ekranowy

Tekst `displayed` często jest elementem kompozycji obrazu. Polskie wytyczne
dostępnościowe zalecają, by układ tłumaczenia był podobny do układu tekstu
widocznego na ekranie. Dlatego dla `displayed` oryginalna liczba wersów,
proporcje i pozycje powinny ważyć więcej niż dla zwykłego dialogu.

Nie oznacza to bezwarunkowego kopiowania granic. Po polsku nadal nie wolno
utworzyć `nie\Nbiegać`, `w\Ndomu` ani oddzielić imienia od nazwiska.

## 10. Jak traktować oryginalne `\N`

Oryginalny podział należy przechować jako metadane, a nie wysyłać do translatora
jako dwa niezależne zdania.

Trzeba przy tym rozróżnić trzy źródła podziału:

1. **jawny podział w gotowym polskim tekście** — zwykle jest decyzją autora
   i należy go zachować;
2. **podział strukturalny** — na przykład dwie osoby, poezja, karaoke,
   podpis i treść albo świadome pozycjonowanie; nie wolno go zgubić podczas
   normalizacji;
3. **podział tekstu źródłowego przed tłumaczeniem** — jest wskazówką o układzie,
   ale nie narzuca miejsca polskiego cięcia, bo składnia może się zmienić.

Przykład źródłowy:

```text
Episode 3\NLife Back at Home
```

Do tłumaczenia powinien trafić jeden spójny tekst:

```text
Episode 3 Life Back at Home
```

Po otrzymaniu:

```text
Odcinek 3: Życie z powrotem w domu
```

algorytm generuje kandydatów **w polskim tłumaczeniu**. Metadane źródła mówią:

- były dwa wersy;
- ich widoczne długości miały określoną proporcję;
- podział mógł być celowy;
- rodzaj eventu to dialog albo tekst ekranowy.

Poprawny wynik:

```text
Odcinek 3:
Życie z powrotem w domu
```

jest wybierany dlatego, że dwukropek daje naturalną granicę, a nie dlatego, że
indeks znaku odpowiada indeksowi źródłowego `\N`.

### 10.1. Dlaczego translator nie powinien dostawać osobnych wersów

Oddzielne tłumaczenie:

```text
Episode 3
Life Back at Home
```

może odebrać drugiemu fragmentowi kontekst pierwszego. Problem dotyczy nie
tylko LLM, ale również Google Translate i DeepL. Provider powinien zobaczyć
pełną jednostkę semantyczną, natomiast AniShift sam odpowiada za layout.

### 10.2. Dlaczego nie wystarczy wkleić `\N` z powrotem

Indeks słowa lub proporcja znaków nie przechowują relacji składniowych.
Tłumaczenie może:

- zmienić kolejność wyrazów;
- połączyć albo rozdzielić frazy;
- dodać polski przyimek;
- zamienić rzeczownik na czasownik;
- zmienić liczbę grafemów bez zmiany sensu.

Dlatego proporcja źródłowa jest celem estetycznym, nie pozycją do mechanicznego
wstawienia.

## 11. Proponowany model wyboru

Bezpieczniejszy od jednej sumy ważonej jest porządek leksykograficzny. Każdy
kandydat otrzymuje krotkę, a algorytm porównuje kolejne pola dopiero przy
remisie wcześniejszych:

```text
(
    hard_violation_count,
    structural_violation_count,
    syntactic_damage_class,
    overflow,
    orphan_penalty,
    source_ratio_error,
    line_balance_error,
    top_heavy_penalty,
    distance_from_center,
)
```

Znaczenie pól:

1. `hard_violation_count` — uszkodzenie grafemu, tagu, `\h`, liczby lub
   interpunkcji; kandydat powinien zostać odrzucony;
2. `structural_violation_count` — utrata granicy rozmówców, pusty albo trzeci
   wers i podobne naruszenia formatu;
3. `syntactic_damage_class` — od naturalnej granicy zdania przez neutralną
   granicę aż po rozdzielenie `nie`, `się`, przyimka, nazwy lub orzeczenia;
4. `overflow` — przekroczenie limitu szerokości;
5. `orphan_penalty` — osamotnione słowo, krótki spójnik albo przyimek;
6. `source_ratio_error` — różnica względem proporcji authored layoutu;
7. pozostałe pola — geometria i estetyka.

Takie porównanie gwarantuje, że nawet idealne `9 : 17` nie przebije lepszego
podziału składniowego. Nie można też sumą wielu małych premii „wykupić”
naruszenia twardej reguły.

Klasy szkody składniowej mogą mieć na przykład następującą kolejność:

| Klasa | Granica |
|---:|---|
| `0` | wymuszona granica autorska lub strukturalna |
| `1` | po końcu zdania |
| `2` | po średniku, dwukropku, przecinku lub myślniku |
| `3` | przed spójnikiem rozpoczynającym pełny człon |
| `4` | przed pełną frazą przyimkową |
| `5` | neutralna granica fraz |
| `20` | rozdzielenie określenia od wyrazu określanego |
| `30` | rozdzielenie czasownika pomocniczego lub modalnego od formy głównej |
| `40` | rozdzielenie `nie`, `się`, przyimka, nazwy albo tytułu od nazwiska |

Klasy `20–40` są kandydatami awaryjnymi, a nie technicznymi granicami Unicode.
Jeżeli nie istnieje dobry wariant mieszczący się w limicie, wynik powinien
ujawnić overflow albo potrzebę kondensacji, zamiast po cichu wybrać efektowny,
lecz językowo zły podział.

### 11.1. Sugerowany przebieg

1. Rozdziel tekst widoczny od tagów ASS, zachowując kotwice.
2. Segmentuj tekst na klastry grafemowe i tokeny.
3. Wyznacz technicznie dopuszczalne granice według Unicode.
4. Oznacz polskie jednostki nierozdzielne.
5. Dodaj cechy składniowe i interpunkcyjne.
6. Policz szerokość każdego wariantu w profilu danego stylu.
7. Dodaj metadane oryginalnego layoutu.
8. Odrzuć granice zabronione.
9. Wybierz wariant o najniższym koszcie.
10. Odtwórz tagi i wstaw `\N` w wybranej granicy tokenów.
11. Sprawdź niezmienniki po rekonstrukcji.

## 12. Niezmienniki do przyszłych testów

Każdy test powinien potwierdzać nie tylko wynik wizualny, ale również brak
utraty danych.

### 12.1. Niezmienniki tekstowe

- po usunięciu wstawionego `\N` tekst ma tę samą sekwencję grafemów i słów;
- nie zniknął ani nie został dodany znak interpunkcyjny;
- nie rozdzielono `\h`;
- tagi ASS występują w tej samej kolejności i liczbie;
- bloki rysunkowe nie zostały potraktowane jak język naturalny.

### 12.2. Minimalny zestaw przypadków językowych

```text
nie biegać
nie będzie biegać
boi się ciemności
się boi ciemności
w starym domu
Jan Kowalski
prof. Jan Kowalski
10 kilometrów
17.30
biało-czerwony
Warszawa–Kraków
„bardzo ważne słowa”
(bardzo ważne słowa)
Chciałem zostać, ale musiałem wrócić.
To było niemożliwe – a jednak próbował.
```

### 12.3. Minimalny zestaw przypadków napisowych

- jeden krótki wers bez wymuszonego podziału;
- dwa wersy z naturalnym podziałem po interpunkcji;
- dwie kwestie dialogowe;
- długi tekst ekranowy z authored layoutem;
- oryginalne proporcje `9 : 17`, które są zgodne ze składnią;
- oryginalne proporcje `9 : 17`, które kolidują ze składnią;
- brak poprawnego podziału w limicie;
- tag kursywy przecinający planowaną granicę;
- `\h` w pobliżu najlepszego geometrycznie miejsca;
- łączone grafemy i emoji;
- długi niepodzielny URL;
- zakres liczbowy z półpauzą.

## 13. Czego nie przenosić bezpośrednio z druku

Typografia książkowa pomaga zidentyfikować silne związki i zachowanie znaków,
ale strona i napis filmowy mają inne ograniczenia.

Nie przenosimy automatycznie:

- dzielenia wyrazów na sylaby;
- reguł wdów, bękartów i szewców odnoszących się do akapitów i stron;
- justowania oraz regulowania odstępów;
- zakazu wszystkich dwu- i trzyliterowych słów właściwego konkretnemu
  wydawnictwu;
- zasad przeznaczonych dla wierszy mających ponad 50–60 znaków;
- kształtu piramidy jako wartości ważniejszej od składni.

Z druku warto natomiast zachować:

- twarde spacje w jednostkach nierozdzielnych;
- rozróżnienie myślnika, półpauzy i dywizu;
- zakaz sierot jednoliterowych;
- wiązanie liczb, jednostek, skrótów i nazw;
- podstawowe zachowanie nawiasów, cudzysłowów i interpunkcji.

## 14. Biblioteka czy własny algorytm

Nie należy oczekiwać jednej biblioteki, która jednocześnie:

- rozumie polską składnię;
- zna konwencje napisowe;
- zachowuje strukturę ASS;
- uwzględnia szerokość konkretnego stylu;
- odtwarza authored layout.

Rozsądny podział odpowiedzialności to:

- standard Unicode do technicznych możliwości podziału;
- tokenizer i opcjonalny analizator morfosyntaktyczny do języka polskiego;
- własna, jawna warstwa reguł i kar AniShift;
- parser ASS jako źródło tagów, stylu i metadanych layoutu.

Decyzję o konkretnej bibliotece należy podjąć dopiero po zbudowaniu korpusu
przykładów i benchmarku. Reguły z tego dokumentu powinny być testami
akceptacyjnymi niezależnymi od wybranego narzędzia.

## 15. Źródła i ich rola

### Źródła pierwszoplanowe

- [Fundacja Kultury bez Barier, „Napisy dla niesłyszących — zasady tworzenia”, aktualizacja 2019](https://dostepna.malopolska.pl/images/wydawnictwa/Napisy-dla-nieslyszacych_zasady-tworzenia_2019.pdf)
  — polskie zasady napisowe, w tym 40 znaków, dwa wersy, związki
  międzywyrazowe, `nie`, `się`, spójniki i dialog.
- [Netflix, Polish Timed Text Style Guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/216787928-Polish-Timed-Text-Style-Guide)
  — współczesny profil produkcyjny dla polskich napisów: 42 znaki, dwa wersy,
  kształt, dialog i tekst ekranowy.
- [Netflix, Timed Text Style Guide: General Requirements](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617-Timed-Text-Style-Guide-General-Requirements)
  — ogólne reguły podziału składniowego; nie wszystkie są specyficzne dla
  polskiego.
- [Unicode Standard Annex #14, Unicode Line Breaking Algorithm](https://unicode.org/reports/tr14/)
  — techniczna warstwa dopuszczalnych miejsc podziału, wymagająca dostosowania
  językowego.
- [Rada Języka Polskiego PAN, „Zasady pisowni i interpunkcji polskiej”](https://rjp.pan.pl/app/uploads/2026/03/Zalacznik-do-komunikatu-11-25-wersja-ostateczna-jednolita.pdf)
  — aktualna ortografia, pisownia `nie`, łączniki i dzielenie wyrazów.

### Źródła wspierające

- [Instytut Badań Edukacyjnych, „Wskazówki dla autorów i redaktorów”](https://efs-archiwum.men.gov.pl/wp-content/uploads/2024/01/Zalacznik-nr-13-Wskazowki-dla-redaktorow.pdf)
  — materiał przygotowany na zlecenie MEN; powtarza dla polskich napisów
  ochronę `nie`, `się`, przyimków, nazw i określeń. Sam dokument zaznacza, że
  ma charakter roboczy, dlatego nie jest traktowany jak norma.
- [EBU I44, „Subtitling for television”](https://tech.ebu.ch/docs/i/i044.pdf)
  — europejski kontekst dostępności i segmentacji; nie jest źródłem
  specyficznie polskiej składni.
- [O. Gerber-Morón, A. Szarkowska, „Line breaks in subtitling: an eye tracking study on viewer preferences”, 2018](https://discovery.ucl.ac.uk/id/eprint/10051115/)
  — empiryczne wsparcie dla podziału według jednostek składniowych, również
  w grupie polskiej.
- [Poradnia Językowa Uniwersytetu Łódzkiego, „Sieroty na końcu wiersza”](https://www.poradnia-jezykowa.uni.lodz.pl/szczegoly/sieroty-na-koncu-wiersza)
  — ważne zastrzeżenie, że przy krótkich wierszach drukarska reguła
  jednoliterowych sierot nie jest bezwarunkowa.
- [Zintegrowana Platforma Edukacyjna, „Wykorzystanie zasad typograficznych w edytorze tekstu”](https://zpe.gov.pl/a/przeczytaj/DG2whzY8q)
  — polskie sieroty i twarde spacje.
- [Janusz Nowacki, „TeXnologia a typografia”](https://poledyt.amu.edu.pl/download/Janusz%20Nowacki.pdf)
  — tradycyjny skład, pauza, dywiz i jednostki nierozdzielne; część reguł
  dotyczy szerokiego składu drukarskiego, nie bezpośrednio napisów.
- [Polskie tłumaczenie „Nie za krótkiego wprowadzenia do systemu LaTeX2e”](https://www.fuw.edu.pl/~grzelak/PTI/lshort2e_pl.pdf)
  — praktyczne przykłady odstępów niełamliwych i rozróżnienia kresek.

Norma PN-P-55366:1983 dotycząca między innymi składu i dzielenia została
wycofana w 2014 r. Jej reguł nie należy przedstawiać jako aktualnie
obowiązującej normy. Brak jednej aktywnej polskiej normy, która rozstrzygałaby
całe łamanie napisów, jest powodem jawnego rozdzielenia reguł technicznych,
językowych, platformowych i estetycznych.

Źródła sprawdzono 27 lipca 2026 r.

## 16. Stan obecnego algorytmu

Audyt z 27 lipca 2026 r. pokazuje, że obecny
[`linebreak.py`](../../../anishift/services/translation/linebreak.py) ma już
wartościowe podstawy:

- limit preferowany 42 znaków i najwyżej dwa wersy w zwykłym reflow;
- preferowanie końca zdania, słabszej interpunkcji i granicy przed spójnikiem;
- ochronę prostych i wielowyrazowych polskich przyimków;
- ochronę części wielowyrazowych spójników;
- unikanie jednowyrazowego osamotnionego wersu;
- brak dzielenia pojedynczego słowa;
- zachowanie liczby i przybliżonych proporcji authored wersów w
  `split_for_layout()`.

Nie implementuje jednak jeszcze pełnego kontraktu z tego dokumentu:

- `split_line()` zwija wszystkie białe znaki do jednej spacji, więc jawny hard
  break przekazany bez osobnych metadanych znika;
- nie chroni `nie` ani `się` z czasownikiem;
- nie rozpoznaje imienia z nazwiskiem, inicjału lub tytułu z nazwiskiem;
- nie chroni ogólnie liczby z jednostką, walutą albo procentem;
- nie modeluje grup nominalnych ani czasownikowych;
- nie ma osobnej walidacji znaków otwierających i zamykających;
- nie rozpoznaje strukturalnie dwóch rozmówców;
- szeroka klasa `_WEAK_CUT` opisuje znaki Unicode, ale nie jakość polskiego
  miejsca podziału;
- mnożniki odległości mogą pozwolić geometrii przebić lepszą klasę
  składniową;
- `split_for_layout()` zachowuje głównie liczbę i proporcje wersów źródła,
  bez rozpoznania, czy podział był strukturalny, językowy czy przypadkowy;
- kara za osamotnienie obejmuje jeden wyraz, ale nie górny wers z dwoma
  słowami;
- nie ma preferencji krótszego górnego wersu;
- szerokość jest liczona znakami, bez metryk stylu ASS.

To lista luk do późniejszego projektu i testów. Nie oznacza, że każda pozycja
powinna zostać rozwiązana jednym rozbudowanym parserem.

## 17. Otwarte decyzje przed implementacją

1. Czy limit ma być liczony znakami, grafemami, pikselami, czy hybrydowo?
2. Czy authored `\N` w `displayed` ma być silną preferencją, czy czasem twardym
   ograniczeniem?
3. Jak rozpoznać, że event jest tytułem lub kompozycją graficzną, a nie
   zwykłym dialogiem?
4. Czy do polskiej analizy wystarczy tokenizer i słowniki, czy benchmark
   uzasadni parser morfosyntaktyczny?
5. Jak karać przepełnienie względem naruszenia słabszego związku składniowego?
6. Jak mierzyć rzeczywistą szerokość tekstu przy tagach `\fscx`, `\fsp`,
   zmianach fontu i pozycjonowaniu?
7. Jak oznaczać oryginalny podział jako świadomy, przypadkowy albo wynikający
   wyłącznie z limitu źródłowego?

Do czasu rozstrzygnięcia tych pytań dokument jest specyfikacją zasad i zestawem
przypadków testowych, a nie zgodą na automatyczną zmianę istniejącego
algorytmu.

## 18. Decyzja o wydzieleniu osobnego etapu

Pierwotne zadanie dotyczyło poprawienia miejsca wstawiania `\N`. Analiza
wykazała, że trwałe rozwiązanie obejmuje znacznie większy obszar:

- semantyczne i typograficzne łamanie polskich zdań;
- zachowanie autorskiego layoutu napisów;
- rozróżnienie podziałów strukturalnych i estetycznych;
- mapowanie tagów oraz pozycji ASS;
- zachowanie stylów, gradientów, rysunków i animacji;
- pomiar szerokości renderowanej według fontu i override tags;
- ocenę jakości napisów, timingów, CPS i WPM;
- deduplikację oraz rekonstrukcję animowanych napisów ekranowych;
- opcjonalną analizę morfosyntaktyczną;
- przyszłe narzędzia waveform, spektrogramu i zmian scen.

Nie jest to poprawka do pojedynczej funkcji. To osobny silnik layoutu napisów,
który wymaga własnego planu, korpusu testowego i oddzielnego runu
implementacyjnego.

Decyzja z 27 lipca 2026 r.:

- nie rozszerzać o ten projekt obecnego etapu ani obecnego PR;
- nie zmieniać teraz zachowania produkcyjnego `linebreak.py`;
- zachować obecny algorytm jako działający baseline;
- wrócić do tego dokumentu po ukończeniu głównego planu AniShift;
- potraktować przyszłą implementację jako osobny etap, roboczo „etap 9”;
- przed kodowaniem ponownie ustalić rzeczywisty zakres i kolejność podzadań.

Numer etapu jest roboczy. Ostateczny numer zależy od kolejności ukończenia
pozostałych etapów z głównego planu.

## 19. Audyt Subtitle Edit

### 19.1. Dlaczego ten projekt jest ważny

[Subtitle Edit](https://github.com/SubtitleEdit/subtitleedit) to dojrzały
edytor napisów zawierający wiele mechanizmów zbieżnych z potrzebami AniShift.
Nie jest biblioteką Pythona i nie powinien być dołączany do pipeline jako
ciężki proces tylko po to, aby wstawić jeden podział wiersza.

Jego wartość polega na czym innym:

- pokazuje sprawdzone rozwiązania problemów napisowych;
- zawiera wiele lat przypadków brzegowych i poprawek;
- może być źródłem zachowań referencyjnych;
- pozwala porównać wynik AniShift z dojrzałym narzędziem;
- ma osobne mechanizmy dla tekstu, timingów, ASS, OCR i audio;
- pozwala uniknąć wymyślania od zera elementów, które już rozwiązano.

Nie należy kopiować całej architektury. Subtitle Edit jest dużą aplikacją
edytorską z UI, historią kompatybilności i wieloma funkcjami poza zakresem
AniShift. Należy wybierać konkretne algorytmy oraz przypadki testowe.

### 19.2. Pliki wymagające przyszłego audytu kodu

Najważniejsze znalezione punkty wejścia:

- [`TextSplit.cs`](https://github.com/SubtitleEdit/subtitleedit/blob/main/src/libse/Common/TextSplit.cs)
  — generowanie wszystkich możliwych podziałów i wybór najlepszego;
- [`TextSplitResult.cs`](https://github.com/SubtitleEdit/subtitleedit/blob/main/src/libse/Common/TextSplitResult.cs)
  — ocena długości, szerokości renderowanej, balansu i kształtu;
- [`Utilities.cs`](https://github.com/SubtitleEdit/subtitleedit/blob/main/src/libse/Common/Utilities.cs)
  — `AutoBreakLine`, ochrona dialogów, piosenek i reinsercja tagów;
- katalog [`src/libse`](https://github.com/SubtitleEdit/subtitleedit/tree/main/src/libse)
  — niezależniejsza część domenowa programu;
- katalog [`tests`](https://github.com/SubtitleEdit/subtitleedit/tree/main/tests)
  — przypadki regresyjne, które należy zmapować na potrzeby AniShift;
- katalog [`Dictionaries`](https://github.com/SubtitleEdit/subtitleedit/tree/main/Dictionaries)
  — listy językowe, skróty, spellcheck i reguły korekcyjne.

Przyszły audyt nie może zatrzymać się na jednym pliku `TextSplit.cs`.
`AutoBreakLinePrivate()` przygotowuje tekst, wykrywa strukturę i przenosi tagi,
a `TextSplitResult` oblicza część wyniku. Dopiero ten zestaw pokazuje pełne
zachowanie.

### 19.3. Mechanizm `TextSplit`

Rdzeń algorytmu Subtitle Edit:

1. tworzy kandydata dla każdej możliwej granicy;
2. oddziela wszystkie kandydatury od kandydatur dozwolonych;
3. filtruje granice przez `CanBreak`;
4. potrafi preferować granicę dialogu;
5. potrafi preferować koniec zdania;
6. potrafi preferować przecinek;
7. może mierzyć szerokość w pikselach;
8. przy remisie może preferować układ bottom-heavy;
9. w ostateczności wybiera podział najbliższy równowadze.

To dobry model bazowy dla AniShift, ponieważ przy dwóch wersach liczba
kandydatur jest mała. Dla `n` słów istnieje najwyżej `n - 1` granic pomiędzy
słowami. Nie potrzeba ciężkiego algorytmu składu całego akapitu.

AniShift powinna przejąć zasadę „oceń wszystkich kandydatów”, ale zastąpić
ogólną ocenę własną hierarchią:

- techniczne zakazy Unicode i ASS;
- struktura eventu;
- polskie związki składniowe;
- limity napisowe;
- rzeczywista szerokość;
- estetyka i proporcje.

### 19.4. Przygotowanie i odtwarzanie tekstu

`AutoBreakLinePrivate()` w Subtitle Edit realizuje kilka ważnych kroków:

- rozpoznaje istniejące linie dialogowe;
- chroni część zapisów piosenek;
- usuwa istniejące line breaks, gdy wolno wykonać reflow;
- tymczasowo usuwa wybrane tagi HTML;
- tymczasowo usuwa tagi override ASS;
- przechowuje tagi wraz z pozycją;
- wykonuje wybór podziału na tekście widocznym;
- wstawia tagi ponownie;
- sprząta odstępy wokół nowej linii;
- przesuwa wybrane tagi zamykające na poprawną stronę podziału.

To potwierdza podstawową decyzję AniShift: translator, analizator składniowy
i algorytm layoutu nie powinny bezpośrednio operować na surowym tekście ASS.
Potrzebują tekstu widocznego oraz osobnego modelu kotwic.

Nie wolno jednak przepisać uproszczenia „indeks znaku przed usunięciem tagu”
bez sprawdzenia. AniShift musi uwzględnić:

- klastry grafemowe;
- wiele tagów w jednym bloku `{...}`;
- zmianę fontu lub rozmiaru wewnątrz eventu;
- tagi pozycyjne i transformacje;
- rysunki ASS;
- `\N`, `\n` i `\h`;
- animacje karaoke;
- nakładające się style i reset `\r`;
- tekst powtarzany w wielu eventach animacji.

### 19.5. `CanBreak` i listy wyjątków

Subtitle Edit ma mechanizm list „nie łam po tym wyrażeniu”. Domyślna ochrona
jest jednak znacznie płytsza niż docelowe wymagania AniShift:

- kilka skrótów, między innymi `Mr.` i `Dr.`;
- opcjonalne listy językowe;
- niektóre zasady interpunkcyjne;
- osobne zachowania dla wybranych języków.

To dobry punkt rozszerzeń, ale nie kompletna polska analiza. AniShift potrzebuje
osobnych reguł dla:

- `nie` i `się` przy czasowniku;
- przyimków i dopełnień;
- spójników oraz rozpoczynanych przez nie członów;
- imion, nazwisk, tytułów i inicjałów;
- liczb, jednostek, walut oraz procentów;
- czasowników modalnych i pomocniczych;
- grup nominalnych;
- markerów dialogowych;
- strukturalnych podziałów displayed.

### 19.6. Funkcje warte wykorzystania w tym etapie

| Obszar Subtitle Edit | Potencjalne użycie w AniShift |
|---|---|
| Auto balance / `TextSplit` | wybór najlepszego `\N` |
| pixel-width calculation | layout według realnej szerokości, nie liczby znaków |
| do-not-break lists | polskie twarde i miękkie zależności |
| ASS tag extraction/reinsertion | zachowanie formatowania i gradientów |
| style/layer/tag filters | klasyfikacja i diagnostyka `displayed` |
| merge same text | animowane, powtarzalne napisy ekranowe |
| merge same time codes | porządkowanie nakładających się eventów |
| line length, CPS, WPM | raport jakości przed eksportem |
| overlap and gap checks | wykrywanie konfliktów timingów |
| compare/statistics | raport before/after i regresje |
| spellcheck dictionaries | opcjonalna kontrola polskiego tekstu |

### 19.7. Funkcje warte osobnych przyszłych etapów

Subtitle Edit posiada również funkcje, które nie należą bezpośrednio do
linebreakera, ale mogą być wartościowe dla AniShift:

- OCR napisów PGS, VobSub i innych formatów obrazkowych;
- monitor rzeczywistej pozycji napisów obrazkowych;
- waveform oraz spektrogram;
- wykrywanie i wizualizację zmian scen;
- dopasowanie początku i końca cue do klatek oraz zmian scen;
- profile minimalnych odstępów i czasów wyświetlania;
- lint i raporty błędów;
- zaawansowane narzędzia ASSA;
- efekty, animacje i podgląd typesettingu;
- naprawianie typowych błędów tekstowych;
- rozpoznawanie i usuwanie oznaczeń dla niesłyszących;
- porównywanie oryginału i tłumaczenia;
- OCR tekstu wypalonego bezpośrednio w obrazie.

Dokumentacja do późniejszego audytu:

- [Subtitle Edit — overview](https://subtitleedit.github.io/subtitleedit/overview.html);
- [Subtitle Edit — main window i lista narzędzi](https://subtitleedit.github.io/subtitleedit/features/main-window.html);
- [Subtitle Edit — settings i profile](https://subtitleedit.github.io/subtitleedit/features/settings.html);
- [Subtitle Edit 5 — nowe funkcje](https://subtitleedit.github.io/subtitleedit/features/whats-new-in-se5.html);
- [Subtitle Edit — audio visualizer](https://subtitleedit.github.io/subtitleedit/features/audio-visualizer.html);
- [Subtitle Edit — OCR](https://subtitleedit.github.io/subtitleedit/features/ocr.html);
- [Subtitle Edit — FAQ ASSA i słowniki](https://subtitleedit.github.io/subtitleedit/faq.html).

### 19.8. Funkcje, których AniShift nie powinna przejmować

AniShift ma lub planuje własne rozwiązania dla:

- tłumaczenia;
- LLM;
- TTS;
- ekstrakcji MKV;
- składania pliku wynikowego;
- burn-in;
- terminalowego workflow;
- ustawień providerów;
- retry i kolejek API.

Nie ma sensu zastępować tych domen odpowiednikami Subtitle Edit. Należy
korzystać z niego tylko tam, gdzie ma dojrzalszą wiedzę napisową.

### 19.9. Ważna lekcja z błędów Subtitle Edit

W Subtitle Edit zgłoszono problem, w którym linie były dzielone przed
tłumaczeniem. Prowadziło to do utraty kontekstu i gorszych wyników translatora:

- [problem z podziałem przed tłumaczeniem](https://github.com/SubtitleEdit/subtitleedit/issues/8658);
- [problemy z zachowaniem struktury w tłumaczeniu LLM](https://github.com/SubtitleEdit/subtitleedit/discussions/8868).

AniShift nie powinna kopiować tego zachowania. Ustalony kontrakt pozostaje:

1. zrekonstruować pełny tekst logiczny eventu;
2. przetłumaczyć pełny tekst;
3. dopiero potem wybrać polski layout;
4. zachować poza tekstem wszystkie kotwice potrzebne do odtworzenia ASS.

### 19.10. Dostęp przez CLI

Subtitle Edit udostępnia operacje `/BalanceLines` i `/SplitLongLines` w trybie
batch:

- [lista operacji CLI](https://github.com/SubtitleEdit/subtitleedit/issues/8080).

Może to posłużyć do porównania wyników w benchmarku. Nie powinno być
produkcyjną implementacją AniShift, ponieważ wymagałoby:

- osobnego programu;
- zapisu i ponownego odczytu plików;
- mapowania ustawień;
- zależności od jego profilu;
- utraty kontroli nad naszym modelem ASS;
- trudniejszej diagnostyki i dystrybucji.

## 20. Dostępne biblioteki i standardy

### 20.1. Unicode UAX #14

[Unicode UAX #14](https://unicode.org/reports/tr14/) wyznacza technicznie
dopuszczalne miejsca łamania linii. Chroni między innymi klasy znaków
otwierających, zamykających, liczby, część symboli i klastry zależne.

UAX #14 nie wybiera najlepszego punktu. Zwraca zbiór możliwości, z którego
wyższa warstwa musi wybrać pozycję na podstawie szerokości, języka i celu
renderowania.

W AniShift powinien odpowiadać za legalność granicy, nie za jej jakość
składniową.

### 20.2. `uniseg`

[`uniseg`](https://pypi.org/project/uniseg/) jest czysto pythonową
implementacją segmentacji Unicode:

- grapheme clusters;
- word boundaries;
- sentence boundaries;
- line-break opportunities;
- Unicode-aware wrapping.

Zalety:

- brak natywnej kompilacji;
- zgodność z testami Unicode;
- gotowa implementacja UAX #14;
- możliwość uniknięcia ręcznego odtwarzania dużej części standardu.

Ograniczenia:

- nie zna polskiej składni;
- nie rozumie ASS;
- nie wie, czy authored `\N` jest strukturalne;
- nie mierzy fontu i stylu eventu;
- sam nie wybierze najlepszego napisu.

Kandydat do prototypu powinien być porównany z minimalnym własnym filtrem.
Decyzja o zależności wymaga benchmarku czasu, rozmiaru oraz pokrycia naszych
przypadków.

### 20.3. ICU i PyICU

[ICU BreakIterator](https://unicode-org.github.io/icu/userguide/boundaryanalysis/)
potrafi wyznaczać granice tekstowe zgodnie z Unicode i locale. Dostęp z
Pythona zapewnia PyICU.

Nie jest pierwszym wyborem dla AniShift:

- wymaga natywnej biblioteki ICU;
- komplikuje instalację i dystrybucję;
- nadal nie rozwiązuje polskiej składni napisowej;
- jest większym narzędziem niż potrzebuje prosty dwuwersowy layout.

Należy je zachować jako punkt porównania, nie domyślną zależność.

### 20.4. `unicode-linebreak`

[`unicode-linebreak`](https://pypi.org/project/unicode-linebreak/) udostępnia
binding Pythona do implementacji UAX #14 w Rust.

Znalezione ograniczenia:

- ostatnie wydanie pakietu pochodzi z 2023 r.;
- brak buildów dla współczesnego Pythona 3.14;
- zwraca indeksy bajtowe, co komplikuje mapowanie do indeksów tekstu;
- rozwiązuje tylko techniczne granice.

Nie jest obecnie preferowany względem `uniseg`.

### 20.5. Pyphen i algorytmy TeX

[`Pyphen`](https://pyphen.org/) i wzorce TeX służą przede wszystkim do
dzielenia wyrazów. W AniShift słowa w napisach nie powinny być automatycznie
przenoszone z dywizem.

Algorytm Knutha-Plassa optymalizuje całe akapity, odstępy i justowanie. Można
z niego zaczerpnąć ideę globalnej oceny, ale dla maksymalnie dwóch wersów
prostsze i czytelniejsze jest sprawdzenie wszystkich granic pomiędzy słowami.

### 20.6. Standardowe `textwrap`

[`textwrap`](https://docs.python.org/3/library/textwrap.html) jest
przeznaczony do prostego zawijania tekstu według liczby znaków.

Nie zapewnia:

- polskiej składni;
- ochrony ASS;
- rozróżnienia strukturalnych podziałów;
- rzeczywistej szerokości fontu;
- oceny jakości napisu.

Może być baseline testowym, ale nie docelowym silnikiem.

### 20.7. Biblioteki formatów napisowych

W osobnym audycie należy porównać:

- [`pysubs2`](https://pypi.org/project/pysubs2/) — formaty i obiekty napisów;
- [`srt`](https://pypi.org/project/srt/) — prosty model SRT;
- [`pysrt`](https://pypi.org/project/pysrt/) — starsza biblioteka SRT;
- [`subtitlekit`](https://pypi.org/project/subtitlekit/) — nowszy zestaw
  operacji korekcyjnych i optymalizacyjnych.

Nie należy zastępować obecnego parsera bez testu round-trip na rzeczywistych
plikach anime. Najważniejsza jest bezstratność ASS, a nie liczba obsługiwanych
formatów.

## 21. Analiza spaCy

### 21.1. Czym jest spaCy

[spaCy](https://spacy.io/) jest produkcyjną biblioteką NLP. Numer `3.8` jest
wersją spaCy, a nie oznaczeniem Pythona 3.8.

Aktualnie zbadana wersja:

- spaCy `3.8.14`, wydana 29 marca 2026 r.;
- polski model `pl_core_news_sm` `3.8.0`;
- model zawiera tokenizer, tagger, morphologizer, dependency parser,
  lemmatizer, sentence segmenter i NER;
- [karta polskiego modelu](https://spacy.io/models/pl);
- [pl_core_news_sm — pliki i rozmiar](https://huggingface.co/spacy/pl_core_news_sm/tree/main);
- [pl_core_news_sm — wyniki modelu](https://huggingface.co/spacy/pl_core_news_sm).

Model potrafi oznaczać części mowy i relacje pomiędzy wyrazami. To pozwala
oszacować, czy granica rozrywa jedną konstrukcję składniową.

### 21.2. Zweryfikowane przykłady

Test lokalny z poprawnym tekstem Unicode rozpoznał:

| Zdanie | Rozpoznana relacja |
|---|---|
| `Naprawdę nie mogę teraz wrócić.` | `nie → mogę`, `wrócić → mogę` |
| `Jutro spotkamy się przed starym kinem.` | `się → spotkamy`, `starym → kinem` |
| `Anna Kowalska przyniosła nam dobrą wiadomość.` | `Kowalska → Anna`, `dobrą → wiadomość`, encja osoby |
| `Temperatura wzrosła do 30 °C.` | `30 → °`, `C → °` |
| `Chciałem przyjść, ale zabrakło czasu.` | `przyjść → chciałem`, człon po `ale` |

To pokazuje, że analiza może dostarczyć sygnały trudne do pokrycia samymi
listami słów.

Nie dowodzi jeszcze, że wynikowy linebreaking jest lepszy. Relacje trzeba
zamienić na poprawną ocenę kandydatów i porównać na korpusie napisów.

### 21.3. Benchmark wydajności

Benchmark wykonano lokalnie 27 lipca 2026 r. na tym samym komputerze, na którym
rozwijany jest AniShift:

- Python 3.13;
- spaCy `3.8.14`;
- `pl_core_news_sm` `3.8.0`;
- wejście: krótkie polskie cue podobne do napisów;
- przetwarzanie batchowe przez `nlp.pipe`;
- osobny pomiar z pełnym pipeline i bez NER.

Wyniki:

| Pomiar | Wynik |
|---|---:|
| ładowanie modelu | około 0,3–0,8 s |
| 350 cue bez NER | 0,334 s |
| 2000 cue bez NER | 1,889 s |
| przepustowość bez NER | około 1050 cue/s |
| 2000 cue z pełnym pipeline | 2,172 s |
| przepustowość pełnego pipeline | około 921 cue/s |
| wzrost RSS po załadowaniu | około 73 MiB |
| RSS procesu po zachowaniu 2000 dokumentów | około 190 MiB |

W normalnym pipeline nie trzeba zachowywać wszystkich obiektów `Doc`, więc
szczyt pamięci może być niższy. Analiza jednego odcinka nie jest problemem
czasowym względem ekstrakcji, API tłumaczeniowego i TTS.

### 21.4. Problem Pythona 3.14

AniShift używa obecnie Pythona 3.14.2. Próba instalacji spaCy `3.8.14`
w jednorazowym środowisku CPython 3.14 zakończyła się błędem resolvera:

```text
spacy==3.8.14 has no wheels with a matching Python ABI tag cp314
```

Dostępne gotowe koła kończą się na `cp313`. Problem dotyczy również natywnych
zależności, między innymi `blis`:

- [zgłoszenie braku buildów dla Pythona 3.14](https://github.com/explosion/spaCy/issues/13885);
- [pakiety aktualnego wydania spaCy](https://pypi.org/project/spacy/).

Nie należy:

- obniżać wersji całego AniShift tylko dla linebreakera;
- przepisywać spaCy;
- budować całego stosu Cython i natywnych zależności bez mierzalnego zysku;
- blokować głównego pipeline brakiem opcjonalnego analizatora.

### 21.5. Możliwy worker Python 3.13

Jeżeli benchmark jakości wykaże wyraźną przewagę analizy składniowej, możliwy
jest osobny lokalny worker:

```text
AniShift / Python 3.14
        │
        │ JSON Lines przez stdin/stdout
        ▼
spaCy worker / Python 3.13
```

Kontrakt workera:

- uruchamiany maksymalnie raz na pipeline;
- model ładowany tylko raz;
- wszystkie cue przekazywane batchowo;
- wynik zawiera wyłącznie tokeny, zakresy i potrzebne relacje;
- brak zapisu tekstu do plików;
- kontrolowany timeout;
- awaria uruchamia deterministic fallback;
- worker nie zmienia tekstu ani timingów;
- ładowanie może działać równolegle z ekstrakcją lub tłumaczeniem;
- po pojawieniu się stabilnego `cp314` worker może zostać usunięty.

To rozsądne technicznie, ale nie może zostać wdrożone tylko dlatego, że jest
możliwe.

### 21.6. Kryterium przyjęcia spaCy

spaCy trafia do produkcyjnego rozwiązania wyłącznie wtedy, gdy:

- poprawia wynik na ręcznie ocenionym korpusie;
- nie wprowadza nowych twardych naruszeń;
- poprawia przypadki, których nie da się łatwo pokryć regułą;
- koszt całego odcinka pozostaje poniżej 1 s na sprzęcie testowym;
- jest uruchamiane batchowo;
- ma bezpieczny fallback;
- wynik bez workera pozostaje poprawny i deterministyczny.

Analiza spaCy powinna tworzyć miękkie kary. Nie może ustanawiać twardych
zakazów, ponieważ parser statystyczny może pomylić się na:

- urwanych wypowiedziach;
- elipsach;
- japońskich imionach;
- onomatopejach;
- tekstach ekranowych;
- celowo nienaturalnym szyku;
- poezji i piosenkach;
- fragmentach bez pełnego zdania.

## 22. Docelowa architektura przyszłego silnika

### 22.1. Rozdzielenie odpowiedzialności

Docelowy silnik powinien mieć co najmniej cztery logiczne warstwy:

1. **ASS structure** — odczyt eventu, stylów, tagów, rysunków i kotwic;
2. **visible text** — tekst przeznaczony do tłumaczenia i analizy;
3. **layout candidates** — legalne miejsca podziału i ich ocena;
4. **reconstruction** — odtworzenie tagów, podziałów i plików wynikowych.

Nie oznacza to automatycznie czterech klas ani nowych pakietów. Podział ma
opisywać odpowiedzialność i testy, a implementacja powinna pozostać możliwie
mała.

### 22.2. Model danych eventu

Przed translacją lub reflow event powinien móc reprezentować:

- pełny tekst logiczny;
- tekst widoczny;
- surowy tekst ASS;
- styl i warstwę;
- start i koniec;
- znaczniki `spoken` i `displayed`;
- informację o rysunku;
- kotwice tagów inline;
- typy separatorów `\N`, `\n`, `\h`;
- authored segmenty i ich proporcje;
- marker dwóch mówców;
- marker piosenki lub poezji;
- informację o duplikacji lub animacji;
- zmiany fontu, rozmiaru, skali i spacingu;
- pozycjonowanie oraz transformacje wpływające na layout.

Model nie może uznawać, że każdy istniejący `\N` ma ten sam charakter.

### 22.3. Proponowany pipeline

1. Odczytaj event ASS bez utraty surowej reprezentacji.
2. Rozpoznaj rysunek i eventy bez tekstu językowego.
3. Wyodrębnij strukturę oraz kotwice tagów.
4. Zbuduj pełny tekst logiczny do tłumaczenia.
5. Przetłumacz pełny tekst bez wymuszania źródłowego layoutu.
6. Odbierz polski tekst i znormalizuj tylko bezpieczne białe znaki.
7. Wygeneruj wszystkie legalne granice Unicode.
8. Nałóż twarde ograniczenia ASS i struktury.
9. Nałóż reguły polskie.
10. Opcjonalnie dołącz miękką ocenę parsera składniowego.
11. Policz szerokość kandydatów.
12. Oceń limity, sieroty, balans i bottom-heavy.
13. Wybierz najlepszego kandydata leksykograficznie.
14. Odtwórz tagi, `\N`, `\h` i pozostałe kotwice.
15. Zweryfikuj niezmienniki round-trip.
16. Zapisz pełny, spoken i displayed plik wynikowy.

### 22.4. Twarde filtry

Kandydat powinien zostać odrzucony, jeśli:

- dzieli klaster grafemowy;
- dzieli słowo;
- zostawia znak otwierający na końcu pierwszego wersu;
- rozpoczyna drugi wers znakiem zamykającym lub interpunkcją końcową;
- dzieli liczbę lub liczbę z jednostką;
- rozrywa blok techniczny;
- narusza granicę dwóch mówców;
- rozdziela nierozdzielny anchor ASS;
- niszczy rysunek;
- daje pusty wers;
- przekracza dozwoloną liczbę wersów;
- zmienia kolejność widocznego tekstu.

### 22.5. Ocena leksykograficzna

Nie należy używać jednej sumy ważonej jako jedynego mechanizmu. Duża poprawa
balansu mogłaby wtedy przebić ważniejszą regułę składniową.

Przykładowy klucz:

```python
(
    hard_violation_count,
    structural_damage,
    overflow_width,
    syntactic_damage,
    source_layout_damage,
    orphan_penalty,
    width_imbalance,
    top_heavy_penalty,
    distance_from_preferred_break,
)
```

Kolejność i dokładne pola muszą zostać ustalone na benchmarku. Ważna jest
zasada: geometria nie może kupić rozdzielenia ważnej jednostki językowej.

### 22.6. Fallback

Silnik musi mieć kontrolowane poziomy awaryjne:

1. najlepszy kandydat bez twardych naruszeń i bez overflow;
2. najlepszy kandydat bez twardych naruszeń z minimalnym overflow;
3. zachowanie bezpiecznego authored podziału;
4. pozostawienie jednego wersu z raportem overflow;
5. jawny wynik wymagający kondensacji tekstu.

Nie wolno losowo rozluźniać zakazów ani tracić tekstu po wyczerpaniu
kandydatów.

## 23. Pomiar szerokości i fonty ASS

### 23.1. Dlaczego liczba znaków nie wystarcza

Te napisy mają podobną liczbę znaków, ale inną szerokość:

```text
iiiiiiiiii
MMMMMMMMMM
```

Na wynik wpływają:

- font;
- rozmiar;
- bold i italic;
- `\fscx` i `\fscy`;
- `\fsp`;
- fallback fontu;
- znaki CJK;
- ligatury i kerning;
- klastry grafemowe;
- zmiana fontu wewnątrz eventu;
- marginesy i rozdzielczość skryptu.

### 23.2. Kandydaci do audytu

Przyszły spike powinien porównać:

- [HarfBuzz](https://harfbuzz.github.io/) — shaping tekstu;
- [FreeType](https://freetype.org/) — metryki fontów;
- [libass](https://github.com/libass/libass) — rzeczywisty renderer ASS;
- Pillow z odpowiednim backendem fontów;
- mechanizm pixel-width z Subtitle Edit;
- prostszy model oparty na szerokościach grafemów.

Najdokładniejszy wynik może wymagać HarfBuzz/FreeType albo wykorzystania
libass. Nie należy dodawać ciężkiego stosu, zanim test nie pokaże, że sama
liczba grafemów i proste metryki są niewystarczające dla `spoken`.

### 23.3. Różne traktowanie `spoken` i `displayed`

`spoken`:

- zwykle korzysta z jednego docelowego stylu;
- może być bezpiecznie reflowowane według polskiej składni;
- szerokość jest łatwiejsza do przewidzenia;
- priorytetem jest czytelność.

`displayed`:

- częściej ma authored kompozycję;
- może używać wielu stylów i tagów w jednym evencie;
- może zawierać tekst częścią grafiki;
- może być animowane przez powtarzające się eventy;
- częściej wymaga zachowania pozycji i proporcji;
- powinno silniej preferować oryginalny layout strukturalny.

Nie oznacza to dwóch całkowicie osobnych algorytmów. Powinny współdzielić
parser, kotwice i walidację, ale mieć inne profile oceny.

## 24. Deduplikacja, animacje i displayed

### 24.1. Problem

W napisach ekranowych jeden tekst może występować dziesiątki lub setki razy,
ponieważ:

- pojawia się stopniowo;
- przesuwa się;
- zmienia kolor;
- jest częścią karaoke;
- gradient jest realizowany wieloma eventami;
- poszczególne warstwy budują jeden efekt;
- kolejne eventy różnią się tylko tagami lub timingiem.

Tłumaczenie każdego eventu osobno jest kosztowne i może dać niespójne wyniki.

### 24.2. Docelowe rozróżnienie

Należy odróżnić:

- identyczny tekst widoczny z innymi tagami;
- prefiksy rosnącego tekstu;
- eventy składające się na jeden gradient;
- powtarzalny znak miejsca;
- kilka niezależnych wystąpień tego samego tekstu;
- spoken i displayed zawierające ten sam tekst;
- event pełniący jednocześnie dwie role.

Deduplikacja tłumaczenia może współdzielić wynik językowy, ale rekonstrukcja
musi zachować każdy event, jego timing, styl, warstwę i tagi.

### 24.3. Źródła wzorców

Do audytu:

- Subtitle Edit: merge same text i merge same time codes;
- Aegisub: model eventów, stylów, warstw i karaoke;
- libass: semantyka renderowania;
- realne pliki anime z animowanymi signs;
- obecny `dedup.py` AniShift i klasyfikator displayed.

## 25. Waveform, spektrogram i zmiany scen

### 25.1. Dlaczego mogą być przydatne

Wizualizacja dźwięku nie jest potrzebna do samego `\N`, ale może później
pomóc w:

- ocenie, czy cue pokrywa się z mową;
- wykrywaniu ciszy pomiędzy wypowiedziami;
- przesuwaniu granic cue;
- rozpoznawaniu dwóch rozmówców;
- szukaniu konfliktu narracji z tekstem ekranowym;
- dopasowaniu TTS do dostępnego okna;
- wykrywaniu scen, w których należy zachować displayed;
- diagnostyce różnic między napisami i audio;
- ręcznej korekcie w przyszłym UI.

### 25.2. Elementy Subtitle Edit do zbadania

- waveform i spektrogram;
- napisy jako segmenty na osi czasu;
- snap początku i końca do zmian scen;
- oznaczanie przerw i ciszy;
- profile czerwonych i zielonych stref;
- podgląd before/after korekty timingów;
- kontrola minimalnych odstępów;
- generowanie/import zmian scen.

Materiały:

- [Audio Visualizer](https://subtitleedit.github.io/subtitleedit/features/audio-visualizer.html);
- [Main Window — waveform i shot changes](https://subtitleedit.github.io/subtitleedit/features/main-window.html);
- [FFmpeg `showwavespic`](https://ffmpeg.org/ffmpeg-filters.html#showwavespic).

To powinien być osobny podetap po ustabilizowaniu tekstu i layoutu. Nie należy
łączyć wizualizatora z pierwszą poprawką linebreakera.

## 26. Benchmark jakości

### 26.1. Dlaczego jest obowiązkowy

Nie istnieje jeden algorytm ani jedna norma, które automatycznie gwarantują
najlepszy polski napis. „Najlepszy” musi oznaczać wynik lepszy na rzeczywistym
korpusie, a nie bardziej rozbudowany kod.

Benchmark ma oddzielić:

- poprawną segmentację Unicode;
- poprawną polską składnię;
- dobry layout;
- zachowanie authored structure;
- poprawne ASS;
- szybkość;
- przypadkowe sukcesy heurystyki.

### 26.2. Korpus

Minimalny korpus powinien zawierać 200–500 ręcznie ocenionych eventów:

- krótkie i długie spoken;
- pełne zdania i elipsy;
- `nie` oraz `się`;
- czasowniki modalne i pomocnicze;
- przyimki jedno- i wielowyrazowe;
- imiona japońskie i zachodnie;
- liczby, daty, godziny, waluty i jednostki;
- dwa głosy;
- piosenki;
- teksty ekranowe;
- tytuły odcinków;
- eventy z wieloma stylami;
- gradienty;
- karaoke;
- rysunki;
- animowane duplikaty;
- authored `\N` dobre i złe;
- tekst przepełniający limit;
- błędne spacje przy interpunkcji;
- Unicode i klastry wielokodopunktowe.

Każdy przypadek powinien posiadać:

- surowy event;
- tekst źródłowy;
- polskie tłumaczenie;
- oczekiwany layout lub zbiór akceptowanych layoutów;
- opis chronionej reguły;
- informację, czy podział jest strukturalny;
- oczekiwany round-trip tagów;
- kategorię błędu.

### 26.3. Porównywane warianty

1. obecny `linebreak.py`;
2. prosty środek znakowy;
3. Subtitle Edit `/BalanceLines`;
4. port mechanizmu kandydatów bez polskich reguł;
5. nowy deterministic Polish engine;
6. deterministic engine z pixel width;
7. deterministic engine z opcjonalnym spaCy;
8. ręczny wynik referencyjny.

### 26.4. Metryki

Metryki automatyczne:

- liczba twardych naruszeń;
- liczba rozdzielonych zależności;
- overflow znakowy i pikselowy;
- liczba osieroconych wersów;
- odległość od ręcznie zaakceptowanej granicy;
- zachowanie widocznego tekstu;
- zachowanie tagów i stylów;
- deterministyczność;
- czas na cue i odcinek;
- szczyt pamięci;
- liczba fallbacków.

Metryki ręczne:

- naturalność składniowa;
- szybkość odczytu;
- zasłanianie obrazu;
- sens authored layoutu;
- poprawność dwóch mówców;
- jakość displayed;
- liczba poprawek wymaganych od człowieka.

Do zbadania jako inspiracja:

- [SubER — metryka jakości napisów](https://arxiv.org/abs/2205.05805);
- [Sigma — ocena segmentacji napisów](https://arxiv.org/abs/2205.09360);
- [badanie eye-trackingowe podziałów](https://pmc.ncbi.nlm.nih.gov/articles/PMC7733619/).

### 26.5. Budżet wydajności

Wstępne kryteria:

- deterministic layout nie może być zauważalny względem parsowania pliku;
- cały odcinek bez NLP powinien mieścić się znacznie poniżej 100 ms;
- opcjonalna analiza składniowa powinna mieścić się poniżej 1 s;
- model, jeśli użyty, ładuje się raz;
- brak requestów sieciowych dla layoutu;
- brak pracy per duplikat po deduplikacji językowej;
- obliczenia można batchować;
- błędy analizatora nie zatrzymują eksportu.

Dokładne progi należy potwierdzić benchmarkiem, nie intuicją.

## 27. Przegląd innych edytorów i narzędzi

### 27.1. Cel przyszłego przeglądu

Subtitle Edit nie może być jedynym źródłem inspiracji. Osobne zadanie
badawcze powinno przejrzeć inne dojrzałe edytory i wybrać z każdego najlepsze
elementy.

Nie chodzi o zestawienie liczby funkcji. Dla każdego projektu należy znaleźć:

- algorytm lub moduł;
- przypadki testowe;
- model danych;
- sposób zachowania stylów;
- sposób prezentacji błędów;
- mechanizmy timingów i audio;
- rozwiązania, których AniShift jeszcze nie ma;
- wady, których nie należy kopiować.

### 27.2. Projekty pierwszego priorytetu

#### Aegisub

- [repozytorium Aegisub](https://github.com/Aegisub/Aegisub);
- [dokumentacja Aegisub](https://aeg-dev.github.io/AegSite-hugo/);
- [typesetting, timing i edycja](https://aeg-dev.github.io/AegiSite/docs/3.2/editing_subtitles/).

Obszary do audytu:

- pełny model ASS/SSA;
- style, warstwy i override tags;
- podgląd video;
- timing do waveform;
- karaoke;
- Automation/Lua;
- wizualny typesetting;
- font collector;
- sprawdzanie brakujących fontów;
- zachowanie skryptu ASS przy round-trip.

#### Subtitle Composer

- [strona Subtitle Composer](https://subtitlecomposer.kde.org/);
- [repozytorium KDE Invent](https://invent.kde.org/multimedia/subtitlecomposer).

Obszary do audytu:

- waveform;
- praca z dwoma napisami;
- synchronizacja;
- OCR formatów obrazkowych;
- skrypty;
- model błędów i korekt;
- timeline;
- integracja z odtwarzaczem.

#### Subtitld

- [strona i opis funkcji Subtitld](https://subtitld.org/en);
- [repozytorium Subtitld](https://github.com/jonata/subtitld).

Obszary do audytu:

- implementacja w Pythonie;
- timeline i retiming;
- slicing oraz merge;
- transkrypcja;
- architektura MPV/FFmpeg;
- rozwiązania, które można łatwo porównać z AniShift.

#### Jubler

- [strona Jubler](https://jubler.org/);
- [repozytorium Jubler](https://github.com/teras/Jubler).

Obszary do audytu:

- waveform;
- spellcheck;
- style;
- preview;
- korekta i transformacje tekstu;
- operacje batch.

### 27.3. Projekty drugiego priorytetu

- Gaupol;
- Gnome Subtitles;
- Subtitle Workshop / Tero Subtitler;
- VisualSubSync;
- Amara;
- CaptionHub;
- OOONA;
- EZTitles;
- WinCAPS;
- FAB Subtitler;
- DaVinci Resolve i Premiere jako wzorce UX, nie źródła kodu;
- YouTube Studio jako wzorzec prostego workflow timingów.

W przypadku narzędzi zamkniętych analizuje się publiczne zachowanie,
dokumentację, profile jakości i UX. Nie należy uzależniać planu od dostępu do
ich kodu.

### 27.4. Narzędzia specjalistyczne

Osobno należy przejrzeć:

- libass — renderowanie i zgodność ASS;
- FFmpeg — waveform, sceny, audio i filtry;
- HarfBuzz/FreeType — shaping oraz metryki;
- WhisperX i forced alignment — granice słów w audio;
- stable-ts — korekta timingów Whisper;
- ffsubsync — automatyczna synchronizacja napisów;
- Hunspell — polski spellcheck;
- Morfeusz2 — polska morfologia;
- Stanza — alternatywny parser zależnościowy;
- narzędzia OCR PGS/VobSub;
- biblioteki detekcji scen.

### 27.5. Macierz audytu

Każdy projekt powinien otrzymać w raporcie:

| Pole | Pytanie |
|---|---|
| funkcja | jaki problem rozwiązuje? |
| jakość | czy wynik jest lepszy od AniShift? |
| algorytm | jak wybiera wynik? |
| wejście | jakie dane i metadane wykorzystuje? |
| ASS | czy zachowuje style, tagi i rysunki? |
| audio | czy korzysta z waveform, ciszy lub scen? |
| szybkość | ile kosztuje operacja? |
| testy | jakie przypadki regresyjne posiada? |
| integracja | kopiować ideę, portować mechanizm czy tylko porównywać? |
| ryzyko | czego nie kopiować? |

Wynikiem nie ma być lista programów, lecz uporządkowany katalog mechanizmów
do wykorzystania w AniShift.

## 28. Proponowany podział przyszłego etapu

Nie wykonywać całego zakresu jednym commitem ani jednym niepodzielnym zadaniem.

### 28.1. Faza badawcza

1. Zamrozić baseline obecnego `linebreak.py`.
2. Zbudować ręcznie oceniony korpus.
3. Przeskanować Subtitle Edit.
4. Przeskanować pozostałe edytory.
5. Porównać biblioteki Unicode i formatów.
6. Spisać decyzję o parserze składniowym.

Wynik: raport porównawczy i zatwierdzony kontrakt.

### 28.2. Faza struktury ASS

1. Wprowadzić bezstratny model widocznego tekstu i kotwic.
2. Zachować `\N`, `\n`, `\h` i tagi.
3. Rozpoznać rysunki.
4. Dodać round-trip fixtures.
5. Naprawić nazewnictwo oraz generowanie plików:

```text
{nazwa}.pl.ass
{nazwa}.spoken.pl.ass
{nazwa}.displayed.pl.ass
```

Wynik: tłumaczenie może zmieniać tekst bez niszczenia struktury.

### 28.3. Faza deterministic layout

1. Wygenerować legalne granice.
2. Wdrożyć ocenę wszystkich kandydatów.
3. Dodać twarde reguły.
4. Dodać polskie kary składniowe.
5. Dodać profile spoken/displayed.
6. Dodać fallback.

Wynik: szybki silnik bez NLP.

### 28.4. Faza render width

1. Porównać char count, grapheme count i pixel width.
2. Zmapować tagi wpływające na szerokość.
3. Obsłużyć fallback fontów.
4. Zintegrować wybraną metodę.

Wynik: limit odpowiada faktycznemu obrazowi.

### 28.5. Faza eksperymentalnego NLP

1. Uruchomić spaCy offline na korpusie.
2. Zamienić relacje na miękkie kary.
3. Porównać jakość z deterministic engine.
4. Zmierzyć czas i pamięć.
5. Odrzucić NLP, jeśli zysk jest mały.
6. Jeśli wygra, wdrożyć worker z fallbackiem.

Wynik: decyzja oparta na danych.

### 28.6. Faza jakości i diagnostyki

1. Dodać raport hard violations.
2. Dodać overflow i jakość layoutu.
3. Dodać CPS/WPM oraz timing checks.
4. Dodać porównanie before/after.
5. Udostępnić dane przyszłemu UI.

Wynik: użytkownik wie, co zostało zmienione i dlaczego.

### 28.7. Faza audio i wizualizacji

1. Zbadać waveform i spektrogram.
2. Zbadać ciszę i granice mowy.
3. Zbadać shot changes.
4. Ustalić wpływ na timing i TTS.
5. Zaprojektować UI dopiero po sprawdzeniu wartości danych.

Wynik: osobna decyzja, bez blokowania layoutu tekstowego.

## 29. Definition of Done przyszłego etapu

Etap można uznać za ukończony dopiero, gdy:

- pełny tekst logiczny jest tłumaczony jako całość;
- źródłowy layout jest metadanymi, nie częścią requestu;
- tagi ASS nie trafiają do translatora;
- wszystkie tagi wracają w poprawne miejsca;
- style, warstwy, timingi i rysunki są zachowane;
- gradienty i animacje nie są spłaszczane;
- `spoken` i `displayed` otrzymują poprawne pliki końcowe;
- deduplikacja nie usuwa unikalnego layoutu eventów;
- hard breaks strukturalne są zachowane;
- estetyczne authored breaks mogą zostać poprawione;
- polskie związki składniowe mają pierwszeństwo przed geometrią;
- nielegalne granice Unicode są odrzucane;
- limit jest liczony w sposób odpowiadający renderowaniu;
- bottom-heavy jest preferencją, nie bezwzględnym zakazem;
- każdy fallback jest jawny i testowany;
- wynik jest deterministyczny;
- awaria opcjonalnego NLP nie blokuje pipeline;
- cały odcinek jest analizowany bez zauważalnego opóźnienia;
- korpus regresyjny obejmuje spoken, displayed, ASS i anime typesetting;
- AniShift wypada co najmniej tak dobrze jak Subtitle Edit na wspólnych
  przypadkach i lepiej na polskich zależnościach;
- raport pokazuje overflow, naruszenia i użyty fallback;
- pełne bramki jakości repo są zielone.

## 30. Warunek wznowienia prac

Do tego etapu należy wrócić dopiero po zakończeniu bieżącego głównego planu.
Nowy run powinien rozpocząć się od:

1. ponownego przeczytania tego dokumentu;
2. sprawdzenia aktualnego stanu kodu;
3. aktualizacji linków i wersji narzędzi;
4. potwierdzenia zakresu z użytkownikiem;
5. wydzielenia brancha;
6. zbudowania korpusu, zanim zmieni się produkcyjny algorytm;
7. podziału implementacji na małe commity z pełnymi bramkami jakości.

Ten dokument ma zachować wszystkie ustalenia, ale nie jest poleceniem
realizacji ich w obecnym PR.

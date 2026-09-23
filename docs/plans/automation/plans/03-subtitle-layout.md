---
kind: plan
status: deferred
baseline: 369efcd (main 6eef7d1)
created: 2026-09-05
branch: work/automation/04-dialog-layout (A), work/automation/05-ass-render-proof (B)
---

# Plan 03: układ dialogu polskiego i ozdobnego ASS

Odłożone decyzją właściciela na rzecz użytecznej automatyzacji. Bieżący status:
GitHub #22, #23 i #34. Nie jest bramką importu/pobierania; przed wykonaniem
odświeżyć design na aktualnym kodzie.

## Cel

Etap A: dialog łamie się według jawnej hierarchii bez utraty słów, grafemów
i tagów, nie zaczyna wersu od `się` decyzją algorytmu, a konflikt ograniczeń
kończy się jawną degradacją i diagnozą, która dociera do użytkownika.
Etap B: eksperyment mierzy, które klasy ozdobnych eventów tracą geometrię
po tłumaczeniu, i jakie są granice tego pomiaru, zanim powstanie kod.

## Hierarchia (S01, S02, S04)

1. Niezmienność: sekwencja słów, grafemów, interpunkcji, tagów i `\h`.
2. Twarde reguły (już istniejące, `FORBIDDEN`): brak cięcia przed `się`,
   po prostym przyimku, wewnątrz frazy wielowyrazowej.
3. Ostrożne kary (nowe, mnożnik jak `_TRAILING_CONJUNCTION_PENALTY`): cięcie
   po `się`, po `nie`, między liczbą a następnym słowem, między dwoma
   kolejnymi słowami z wielkiej litery w środku zdania. Kara, nie zakaz, bo
   końcówki i kapitalizacja nie są wiarygodną analizą składni.
4. Czytelność: najwyżej `max_lines`, brak jednowyrazowego wersu.
5. Geometria: `max_chars`; szerokość względem PlayRes tylko w etapie B.
6. Estetyka: równowaga, dolny wers cięższy.

Degradacja: gdy 2 koliduje z 5, wygrywa 2, a wynik niesie diagnozę
`overflow`. Gdy nie ma żadnego niechronionego cięcia, tekst zostaje jednym
wersem z diagnozą `no_safe_cut`; nigdy cięcie w słowie i nigdy `_greedy_cut`.
Tekst nie jest skracany ani parafrazowany.

## Etap A: dialog

### Stan i gap

`_protected` działa; obejścia w `_best_cut` i `_proportional_boundaries`;
brak kar dla `się` po czasowniku, `nie`, liczb, nazw; przepełnienie bez
diagnozy; `split_line` publiczne i zwraca krotkę.

### Zmiany

- `services/translation/linebreak.py` MODIFY: warianty z diagnozami dla obu ścieżek,
  `split_line_diagnosed(...) ->
  LineSplit` NEW (`verses: tuple[str, ...]`, `diagnostics: tuple[LayoutDiagnostic, ...]`);
  analogiczny `split_for_layout_diagnosed` zachowuje kontekst authored layout.
  `split_line` i `split_for_layout` pozostają z dotychczasową sygnaturą jako
  cienkie wrappery zwracające same wersy. Usunąć fallback do `_greedy_cut`
  i pełnej listy kandydatów; dodać kary z punktu 3.
- `services/translation/types.py` MODIFY: `LayoutDiagnostic` NEW
  (`code`, `length`, `limit`).
- `application/translation_handler.py` MODIFY: używa wariantu z diagnozami;
  liczniki (`layout_overflow`, `layout_no_safe_cut`, `layout_unsupported`)
  trafiają do `ProducedArtifact.metadata`; przy niezerowych licznikach
  agregator wyników przekłada liczniki na jedno ostrzeżenie w `RunResult.warnings`.
  Handler zwraca `TaskResult`, nie tworzy bezpośrednio `RunResult`; test przechodzi
  przez rzeczywiste miejsce agregacji w schedulerze/serwisie i renderer.
- `cli/interactive/app.py` MODIFY (mała): widok zakończenia Auto pokazuje
  ostrzeżenia z `RunResult.warnings`, jeśli jeszcze ich nie renderuje.
- Nie ruszać `chunking.py`, `text/`, klasyfikatora, promptów, polityki
  integralności tłumaczenia.

### Korpus

`tests/services/translation/test_translation_linebreak.py` MODIFY: zdania
`nie biegać`, `boi się ciemności`, `się boi ciemności`, `w starym domu`,
`Jan Kowalski`, `10 kilometrów`, `biało-czerwony`, cytat w cudzysłowie,
dialog dwóch osób przy szerokościach 14, 20, 30, 42; przypadki negatywne:
tekst, w którym każde cięcie jest chronione, daje jeden wers z diagnozą,
nie cięcie przed `się`. Regresja Q07 zostaje. Kary sprawdzać przez
porównanie wyboru cięcia, nie przez twarde asercje o gramatyce.

### Human checkpoint

Po testach przedstawić niewielką tabelę syntetycznych przykładów przed/po.
Oglądanie odcinka i odsłuch są odłożone; nie są warunkiem odbioru planu
ani obowiązkiem właściciela podczas tej iteracji.

## Etap B: ozdobny ASS jako eksperyment

### Pytanie i hipoteza

Które klasy eventów displayed tracą geometrię lub semantykę po
`replace_visible_text` + `split_for_layout`, i czy przepełnienie da się
zmierzyć? Hipoteza: eventy z tagami tylko w nagłówku linii przeżywają;
tagi śródtekstowe, karaoke i `\t` w środku tracą znaczenie; przepełnienie
zależy od fontu, którego nie mamy.

### Minimalny setup

- `docs/plans/automation/proof/render_proof.py` NEW: dla każdego eventu
  korpusu renderuje klatki przed i po tłumaczeniu na jednolitym tle
  `color=c=0xFF00FF:s=<PlayResX>x<PlayResY>:r=10:d=<czas>` przez
  `ffmpeg -vf ass=<plik>:fontsdir=<dir>`, próbkując czasy 0%, 25%, 50%,
  75% i ostatnią klatkę eventu. Maska różnicy = różnica wobec osobnej klatki bez napisów wygenerowanej
  identycznymi ustawieniami i konwersją kolorów, z tolerancją szumu; bbox z maski, nie z „niebiałych pikseli”. Wynik:
  tabela `event, klasa tagów, czas, bbox przed, po, kontakt z krawędzią,
  tagi zachowane`.
- Font: jeden font OFL (np. Noto Sans), przypięta wersja/hash i kopia licencji
  w `proof/fonts/`, wskazany w stylach
  korpusu. Ograniczenie nazwane w raporcie: dowód dotyczy transformacji
  tagów i geometrii względem PlayRes, nie metryk fontu użytkownika.
- Przepełnienie poza kadr: klatka jest przycięta, więc kontakt bbox
  z krawędzią jest sygnałem, nie miarą. Jeśli kontakt wystąpi, drugi krok
  eksperymentu sprawdza, czy libass przez wiązanie Pythona potrafi
  renderować na płótnie z marginesem; do tego czasu raport pisze
  „kontakt z krawędzią — możliwe przycięcie”, nie liczbę pikseli poza kadrem.
  Brak kontaktu też nie dowodzi braku overflow (event może być całkiem poza kadrem).
  Nie dodawać bindingu libass bez osobnego eksperymentu i zgody na zależność.
- Korpus syntetyczny `tests/services/subtitles/data/layout_corpus.ass` NEW:
  po jednym evencie dla `\pos`, `\move`, `\clip`, `\t` w nagłówku, `\t`
  w środku, `\fs` w środku, `\fn` w środku, `\r`, `\k` na sylabach, `\N`
  2 i 3 wersy, `\h`, `\an8`, `\p1`. Bez prywatnego materiału.
- PlayRes to układ skryptu, nie automatycznie rozmiar wideo. Dodać kontrolowany
  wariant rzeczywistego rastra 16:9 z innym PlayRes oraz prezentację w viewport
  ultrawide z pasami; nie rozciągać napisów do szerokości monitora.
  `LayoutResX/Y`, proporcje pikseli i rozmiar storage odnotować, gdy mają znaczenie.
  Próbki czasowe obejmują też granice `move`, `t` i karaoke; stałe pięć próbek
  nie gwarantuje zauważenia krótkiej transformacji.
  Konfiguracja odtwarzacza użytkownika nie jest zmieniana; README dostaje
  jedno zdanie, że w mpv `sub-ass-override=force|strip` zmienia układ
  niezależnie od pliku, a `sub-ass-force-margins` domyślnie jest wyłączone.

### Kryterium wyboru i decyzja O12

Klasy z zachowaną geometrią i tagami: bez zmian kodu. Rysunki: już
kopiowane. Karaoke i tagi śródtekstowe: raport podaje liczbę i przykłady,
a właściciel decyduje w O12 między (a) obecnym zachowaniem plus liczniki
`layout_unsupported` w ostrzeżeniach, (b) kopiowaniem eventu bez tłumaczenia
z oznaczeniem produktu jako niepełnego w wyniku, (c) odmową grupy. Do tej
decyzji polityka integralności nie zmienia się; plan nie wprowadza cichego
kopiowania nietłumaczonego karaoke jako kompletnego produktu.

### Co usunąć po eksperymencie

Skrypt zostaje jako dowód powtarzalny; do testów wchodzi tylko część bez
`ffmpeg` (round-trip tagów na korpusie).

## Forbidden

Globalna zamiana tekstu, zakaz słowa, skracanie tłumaczenia, zmiana promptów,
nowa zależność NLP, zmiana konfiguracji odtwarzacza, wymaganie odsłuchu
teraz, zmiana sygnatury `split_line`, twarde reguły oparte na końcówkach.

## Stop

Etap A zatrzymuje się, gdy korpus wymaga analizy morfologicznej dla więcej
niż przypadków brzegowych. Etap B kończy się raportem; A06 rusza po O06
i O12.

# Etap 4 — chunker + linebreak: plan i mechanika (przepisane od zera)

> Ten dokument opisuje DWA narzędzia tekstowe domeny tłumaczenia oraz naprawę
> sześciu martwych punktów z audytu DoD. Językiem prostym: CO robi każda rzecz
> i PO CO. Kod po angielsku, ten opis po polsku.
>
> Źródło kompletnych list słownikowych: Wikisłownik (spójniki 195 haseł,
> przyimki 217 haseł), pobrane przez API MediaWiki. URL-e w komentarzach `Final`.

---

## 1. Dlaczego dwa narzędzia, nie jedno

Są DWA różne zadania tnące tekst, i mają wspólny fundament:

| Narzędzie | Wejście | Wyjście | Po co |
|---|---|---|---|
| **chunking** (`chunking.py`) | długi txt (dowolny język) | kawałki ≤ limit znaków | pociąć plik `.txt` na kawałki, które mieszczą się w jednym żądaniu tłumacza, potem złożyć z powrotem SRT |
| **linebreak** (`linebreak.py`) | jedna przetłumaczona linia (polski) | 1–2 wersy na ekran | podzielić długą polską linię napisu na czytelne wersy dla widza |

**Wspólny fundament (likwidacja duplikacji — zarzut D):** obie rzeczy muszą
rozpoznać "gdzie w tekście jest granica frazy". Zamiast dwóch niezależnych
list interpunkcji, jedno źródło prawdy: **`chunking._PHRASE_CUT_CHARS`** —
kompletny zbiór znaków-separatorów zbudowany z kategorii Unicode
(`unicodedata`, kategorie `Pd/Pe/Pf/Po`). `linebreak` importuje ten zbiór i
buduje z niego swoje klasy interpunkcji (mocna vs słaba), zamiast wpisywać
`.!?…:` z głowy. Jedna baza, dwa zastosowania.

---

## 2. chunking.py — jak działa (txt → kawałki)

Cel: wziąć plik `.txt` (napisy bez timingów, dowolny język źródłowy) i pociąć
na kawałki nie dłuższe niż limit znaków, tak by NIE ciąć w środku słowa ani
zdania, jeśli się da. Potem każdy kawałek dostaje jeden wiersz SRT z timingiem.

Algorytm to hierarchiczne, zachłanne grupowanie (bez zmian względem obecnego —
kod jest dobry, oparty na `unicodedata`, przetestowany):

1. **Paragrafy** — tnij na pustych liniach.
2. **Zdania** — tnij po `. ! ? … 。 ！ ？` + spacja; skróty (`Dr.`, `itd.`) NIE
   kończą zdania (lista skrótów PL+EN).
3. **Frazy** — tnij po każdym znaku z `_PHRASE_CUT_CHARS` (przecinki, myślniki,
   nawiasy zamykające, cudzysłowy zamykające — wszystkie języki przez Unicode).
   Nawiasy/cudzysłowy OTWIERAJĄCE (`Ps`/`Pi`) NIE tną — fraza nie zaczyna się
   tuż za `(`.
4. **Słowa** — ostateczność; apostrof (`don't`) zostaje w słowie.

Na każdym poziomie `_Breaker._merge` grupuje kawałki zachłannie do limitu; gdy
pojedynczy kawałek przekracza limit, schodzi poziom niżej (rekursja).
`CharBreaker` liczy znaki, `WordBreaker` liczy słowa. Publiczna funkcja:
`chunk_text(text, *, method="char", limit=750)`.

**Naprawa martwoty (punkt 4):** `chunking` był gotowy ale bez konsumenta.
Konsument to teraz `subtitles/srt.py::spoken_to_srt` w ścieżce txt→SRT (patrz §5).

---

## 3. linebreak.py — jak działa (linia → wersy)

Cel: przetłumaczona linia napisu bywa za długa na ekran. Widz musi ją przeczytać
w mgnieniu, więc dzielimy na maksymalnie DWA krótkie wersy w naturalnym miejscu.
NIE odtwarzamy układu oryginału (polska składnia jest inna) — budujemy nowy,
czytelny podział.

**Hierarchia miejsc cięcia** (od najlepszego):

1. **Mocna interpunkcja** — cięcie tuż PO `. ! ? … :` (koniec myśli).
2. **Słaba interpunkcja** — tuż PO `, ; —` (pauza).
3. **Przed spójnikiem/przyimkiem** — cięcie PRZED `i / ale / że / ponieważ /
   podczas gdy / ze względu na …` (głowa zdania podrzędnego zostaje z nim).
4. **Najbliżej środka** — na granicy słowa, gdy nic wyżej nie pasuje
   (idea `split_at_half`).

**Reguły ochronne:**

- **max_chars** — preferowana długość wersu (domyślnie 42, standard napisowy).
- **max 2 wersy** — po dwóch akceptujemy przedłużenie zamiast trzeciego wersu.
- **bez sierot** — żaden wers to pojedyncze słowo (kara punktowa w scoringu).
- **nie odrywaj przyimka** — `w domu`, `ze względu na` nie pękają w środku;
  cięcie tuż po jedno-/dwuliterowym przyimku jest zabronione.

**Kompletne listy słownikowe (naprawa punktu 6):**

- `_CONJUNCTIONS` — 74 spójniki jednowyrazowe, alfabetycznie, z Wikisłownika.
- `_CONJUNCTIONS_MULTIWORD` — spójniki wielowyrazowe (`podczas gdy`, `mimo że`,
  `chyba że` …). Patrzymy 2–3 słowa do przodu; cięcie przed CAŁĄ frazą.
- `_NON_BREAKING_HEADS` — przyimki proste + warianty fonetyczne (kanon szkolny),
  których nie odrywamy od następnego słowa.
- `_PREPOSITIONS_MULTIWORD` — przyimki wielowyrazowe (`ze względu na`,
  `w związku z` …). Nie tniemy w ich środku.

**Naprawa martwoty (punkt 2):** `split_line` był wołany tylko w teście. Teraz
`TranslationService` woła go dla KAŻDEJ linii displayed (widz czyta na ekranie),
wypełniając `TranslatedLine.lines` realnie podzielonymi wersami. Dla spoken
`lines=(text,)` — lektor czyta ciągiem, podział wizualny go nie dotyczy.

---

## 4. Wspólny algorytm krok po kroku (linebreak, z wielowyrazowymi)

```
split_line(text, max_chars):
  text = normalizuj spacje, strip
  jeśli len(text) <= max_chars lub brak spacji → zwróć (text,)
  point = _best_cut(text, max_chars)
  left, right = text[:point], text[point:]  (strip)
  jeśli któryś pusty → zwróć (text,)  # nie dało się ciąć sensownie
  zwróć _cap((left, right), max_chars)  # rekurencja jeśli wers wciąż za długi

_best_cut(text, max_chars):
  dla każdej pozycji spacji i:
    prev_word = słowo tuż przed spacją
    jeśli prev_word (bez interpunkcji) to przyimek z _NON_BREAKING_HEADS → pomiń
    jeśli spacja jest w środku frazy wielowyrazowej (przyimek/spójnik) → pomiń
    distance = |i - środek|
    jeśli prev_word kończy się mocną interpunkcją → distance /= 8
    elif słabą → distance /= 4
    elif następne 1–3 słowa tworzą spójnik (jedno- lub wielowyrazowy) → distance /= 2
    jeśli cięcie tworzy sierotę → distance *= 10
  zwróć pozycję o najmniejszym distance (albo greedy fallback)
```

Wielowyrazowe obsługujemy przez `_phrase_at(words, index)` — skleja 2–3 kolejne
słowa (bez interpunkcji, lowercase) i sprawdza w zbiorze fraz. To jedno miejsce
decyduje i o "nie tnij w środku frazy", i o "tnij przed frazą-spójnikiem".

---

## 5. txt → SRT (naprawa punktu 4) — end-to-end

Nowy plik `subtitles/srt.py`:

```
spoken_to_srt(lines: tuple[TranslatedLine, ...], dest: Path) -> Path
```

Buduje `pysubs2.SSAFile`, dla każdej `TranslatedLine` wstawia `SSAEvent`
(start/end ms, text z `\N`-połączonych wersów), zapisuje jako SRT atomowo
(tmp + replace), spójnie z `write_displayed`.

Ścieżka txt w runnerze (`_process_txt`):

```
spoken = txt_to_spoken(path)          # istniejące — dzieli po zdaniach (750)
result = service.translate_file(...)  # tłumaczy
srt = spoken_to_srt(result.spoken, path.with_suffix(".pl.srt"))  # NOWE: zapis
```

`txt_to_spoken` już tnie sensownie (zdania, 750 znaków); `chunking.chunk_text`
jest użyty jako fundament fraz w linebreak i dostępny jako opcja precyzyjniejsza.
Timingi: txt nie ma czasów, więc SRT dostaje sekwencyjne przedziały stałej
długości (czytelne, deterministyczne) — plik jest lektorski, nie do wyświetlania
z wideo.

---

## 6. Naprawa 6 martwych punktów — mapa

| # | Zarzut | Naprawa |
|---|---|---|
| 1 | R6a NEWLINE_MARKER martwy | USUŃ `NEWLINE_MARKER` z google (`_batching`, `constants`); udokumentuj że wejście jest zawsze jednoliniowe (`visible_text` zwija `\n`). Separator zero-width batcha ZOSTAJE (esencja Google batchingu). |
| 2 | linebreak niewpięty | `service.py` woła `split_line` dla displayed → `TranslatedLine.lines` realnie podzielone. |
| 3 | concurrency martwy | USUŃ parametr z całego łańcucha (config, service, google, runner, pipeline types, user_settings, panel). Sekwencyjność jest świadoma (anty-rate-limit), więc parametr jest zbędny (YAGNI). |
| 4 | txt→SRT nie istnieje | `subtitles/srt.py::spoken_to_srt` + wpięcie w `_process_txt`; zapisuje `.pl.srt`. |
| 5 | brak smoke na ASS | `test_translation_network.py` + real ASS z `dataset_ass/` (skipif brak): spoken przetłumaczony, ta sama liczba linii, timingi nietknięte. |
| 6 | listy niekompletne | Kompletne listy ze słownika (74 spójniki + wielowyrazowe, przyimki + wielowyrazowe), alfabetycznie, `# source:` URL. |

**Punkty częściowe:** DeepL retry podłączony do `config.max_retries` (nie stała).
Warianty eksportu = granica etapu 7 (udokumentowane, bez composition w etapie 4).

---

## 7. Kolejność realizacji (z weryfikacją)

1. `chunking.py` — **PRZEPISAĆ OD ZERA** wg §8 (NIE "bez zmian algorytmu" — ta wersja była błędna, sprzeczna z decyzją usera). Eksportuje bazę fraz + realny skrypt testowy w `scripts/`.
2. `linebreak.py` OD ZERA — kompletne listy, wielowyrazowe, wspólna baza →
   `test_translation_linebreak` (realne PL, ≤max, ≤2 wersy, bez sierot, nie tnie
   zrostów, wielowyrazowe całe).
3. `google` — usuń NEWLINE_MARKER → `test_translation_google` zielony.
4. `_retry`/deepl — `config.max_retries` w retry → `test_translation_deepl`.
5. usuń concurrency (łańcuch) → mypy + testy user_settings/panel zielone.
6. `service.py` — wepnij `split_line` w displayed → `test_translation_service`.
7. `subtitles/srt.py` + `_process_txt` → `test_translation_txt_srt` end-to-end.
8. `test_translation_network.py` — real ASS smoke.
9. Bramki: ruff check + format --check + mypy + pytest — wszystko zielone.

---

## 8. chunking.py — PRZEPISANIE OD ZERA (decyzja usera, spec wiążący)

> Obecny `chunking.py` DZIAŁA i jest wpięty (txt→SRT), ale user uznał kod za niedbały i każe **napisać go OD ZERA porządnie** (nie łatać). Zachować SENS (hierarchiczne cięcie txt na kawałki ≤limit), poprawić KOD i podejście. Poniżej wiążący kontrakt.

### 8.1 Wymóg nadrzędny — wielojęzyczność po znakach
Chunker tnie tekst w **dowolnym języku** (napisy źródłowe bywają EN/JP/inne). Podział opiera się na **znakach ASCII + Unicode**, nie na listach słów per język. `_PHRASE_CUT_CHARS` (kategorie Unicode `Pd/Pe/Pf/Po` przez `unicodedata`) to DOBRE podejście — zostaje jako fundament cięcia fraz. **Zakaz mieszania "wyjątków per język"** wpisanych na sztywno w jedną regexową listę jak obecne `_ABBREVIATIONS` (PL+EN sklejone) — to jest to, co user nazwał niedbałym.

### 8.2 Twardy wymóg — DWA limity
- **`char_limit = 750`** — duże kawałki (grupowanie zdań).
- **`chunk_limit = 250`** — mniejsze pod-kawałki (drugi domyślny parametr cięcia).
- **OBA parametry MUSZĄ istnieć** (subagent wcześniej usunął `chunk_limit=250` jako "martwą stałą" — to był błąd, plan go wymagał). Sterowalne argumentem funkcji. Nazwy do ustalenia przez Fable, ale semantyka: 750=domyślny duży, 250=mniejszy pod-podział.

### 8.3 Skróty (Mr./Dr./np./itd.) — problem językowy, Fable dobiera rozwiązanie
Skróty z natury zależą od języka (kropka po "Dr" wygląda jak koniec zdania). Obecna ręczna lista PL+EN jest zła (mieszana, niekompletna). **Realna liczba skrótów: PL ~40-60, EN ~30-50** (skończone, rozsądne). Profesjonalny NLP (NLTK Punkt) NIE trzyma ręcznych list per język — używa **heurystyki** ("kropka + następne słowo z małej litery = środek zdania") + małej listy wsparcia.

**Fable dobiera podejście** (user: "oczywiście Fable ma to zrobić"), spełniając wymóg wielojęzyczności. Rekomendowana hybryda:
1. heurystyka bazowa (wielojęzyczna, bez list): kropka + następne słowo małą literą → nie koniec zdania,
2. mała lista wsparcia najczęstszych skrótów PL+EN (te ~40+40, dla przypadków z wielką literą po skrócie, np. `Dr. Smith`).

Jeśli Fable wybierze pełne listy — pobrać z Wikisłownika jak spójniki w `linebreak.py` (`# source:` URL, alfabetycznie, single + multiword). **NIE zostawiać legacy angielskich skrótów sklejonych z polskimi w jednym regexie.** Decyzja + uzasadnienie w raporcie.

### 8.4 Jakość kodu (python instructions, skill `simple`)
- **Znaki wprost, nie przez kody** — `"…"` zamiast `chr(0x2026)` tam gdzie znak jest drukowalny i czytelny (SSOT stałych OK, ale nie zaciemniać).
- **Komentarze WHY, nie WHAT** — usunąć `# Cut categories: Pd (dashes)...` (opisuje co widać w kodzie).
- **`_APOSTROPHES`** — user: "dodane bez zamówienia, do przemyślenia". Zostaw TYLKO jeśli realnie chroni `don't`/apostrofy w cięciu; inaczej usuń.
- Docstringi Google-style dla publicznych funkcji + każdej `Final`. Guard clauses, ≤2 poziomy zagnieżdżeń, `dataclass(slots=True)` gdzie pasuje.
- Zachować DOBRE: `frozenset({Pd,Pe,Pf,Po})` + generator Unicode; hierarchiczna struktura cięcia (paragraf→zdanie→fraza→słowo, rekurencja na nadwymiarowych).

### 8.5 Realny skrypt testowy — WYMÓG USERA
User chce **zobaczyć na własne oczy** jak chunker tnie, w terminalu (nie tylko testy jednostkowe w tle). Utwórz `scripts/` skrypt (np. `scripts/chunk_demo.py`) uruchamiany `uv run python scripts/chunk_demo.py`:
- bierze przykładowe teksty **PL, EN i inny język** (np. JP lub DE),
- pokazuje jak chunker tnie je na kawałki przy `char_limit=750` i `chunk_limit=250`,
- drukuje czytelnie: wejście → lista kawałków z długościami, żeby user zobaczył granice cięcia i że nic nie ginie.

### 8.6 Weryfikacja (kryteria sukcesu)
- Testy jednostkowe: żaden kawałek > limit; nic nie ginie (suma tekstu = wejście bez zmian poza normalizacją spacji); skróty nie tną zdania (`Dr. Smith` = jedno zdanie); cięcie na znakach Unicode działa dla nie-łacińskich.
- **Skrypt w `scripts/` odpalony w terminalu przez usera** — widzi realne cięcie.
- Bramki: ruff + format + mypy + pytest zielone.
- Chunker nadal wpięty w `_process_txt` (txt→SRT), nie zepsuty.

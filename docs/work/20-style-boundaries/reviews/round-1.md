---
kind: review
status: pass-with-findings
reviewed-state: docs/work/20-style-boundaries/{evidence,specification,plan}.md, 2026-10-25
date: 2026-10-25
---

# Review: granice stylów po tłumaczeniu, runda 1

## Zakres

- **Przedmiot:** `evidence.md`, `specification.md`, `plan.md` z tego katalogu.
- **Baseline:** drzewo robocze na gałęzi `work/subtitles/03-pr66-review-fixes` (z `main` 4365a51).
- **Authority:** issue #34, `AGENTS.md` repo i obszarów, zasady właściciela (logika rozmyta dla heurystyk, specyfikacja przed kodem, limity jako wytyczne), skille `specification`, `planning`, `review`.
- **Ryzyka:** wniosek bez dowodu, cel liczbowy bez pomiaru, plan łamiący inwarianty, ukryta zmiana dzisiejszych wyników.
- **Poza review:** kod (jeszcze go nie ma), zachowanie LLM na nowych znacznikach.

**Niezależność:** to kontrola autorska. Zlecenie zabraniało tworzenia subagentów, więc nie ocenia jej świeża instancja innego modelu. Zgodnie z regułą krzyżową z `AGENTS.md` przed akceptacją właściciela potrzebny jest przegląd innej rodziny modeli.

## Werdykt

**Status:** PASS WITH FINDINGS (kontrola autorska).

**Najważniejszy powód:** każde twierdzenie o stanie dziś ma plik, linię i odtworzenie na obecnym kodzie. Reguły `marked_text` z projektu sprawdził prototyp na korpusie i dał wszystkie oczekiwania katalogu. Niesprawdzona prototypem zostaje część „ustawienie tagów” (W4–W5).

## Findings poprawione w trakcie

### Poważne

#### Cel S2 bez pomiaru

- **Miejsce:** pierwsza wersja `specification.md`, S2 („najwyżej 1 kwestia bez znaczników”).
- **Dowód:** liczba wynikała ze spisu przyczyn, a nie z reguł. Prototyp W1–W3 dał 3, bo `{\i1}That's{\fscx140\i0} {\fscx100}what…` ma pusty zakres, a `This isn't like {\i0}that!{\i1}` to negacja do końca linii.
- **Reakcja:** S2 = 3 z nazwanymi liniami.

#### Pominięta kategoria: zamknięcie przed `\N`

- **Miejsce:** evidence i spec przed prototypem.
- **Dowód:** prototyp zmienił 11 linii oznaczanych dziś. Każda miała `{\i0}\N`, więc dziś zakres sięgał końca linii (Kaguya06 l. 112, Katainaka 02 l. 24).
- **Reakcja:** sekcja C′ w evidence, W2 obejmuje zamknięcia, K27 i K28 w katalogu.

#### W3 łamał I1

- **Miejsce:** W3, pierwsza wersja („poza zakresami zostaje słowo” dla każdej linii).
- **Dowód:** warunek dotknąłby linie oznaczane dziś bez nowych cięć.
- **Reakcja:** W3 działa tylko w liniach z cięciem W1 albo W2.

#### Kolejność faz nie dawała testowalnego W6

- **Miejsce:** plan, faza W6 przed W1–W5.
- **Dowód:** bez W1 i W2 obie strony odrzucają te same linie, więc K26 nie ma czego sprawdzić.
- **Reakcja:** W6 po W1–W5, osobny commit po głównym.

### Mniejsze

- Prototyp liczył styki pustych wersów (`\N\N`) podwójnie. Teraz styki o tej samej pozycji są jednym stykiem (W2, decyzja lokalna w planie); tablica Joshiraku 06 l. 947 dostaje znaczniki.
- `\rStyl` było jednocześnie „poza zakresem” i częścią stanu. Ujednolicone: liczy się jak `\r`.

## Findings otwarte

### Poważne

#### Ustawienie tagów (W4–W5) bez prototypu

- **Miejsce:** plan, algorytm, krok 6.
- **Dowód:** prototyp objął tylko `marked_text`. `_placed_tags` łączy granice kluczem `(segment, offset)`, a cięcia styku żyją na krawędzi dwóch wersów.
- **Wpływ:** możliwy rozjazd kluczy, czyli znaczniki odrzucone mimo poprawnego `marked_text`.
- **Minimalna reakcja:** testy K5–K10, K27 i K28 przez `replace_visible_text` są w planie przed implementacją, a ryzyko jest w tabeli ryzyk. Akceptowalne, jeśli recenzent kodu sprawdzi te testy jako pierwsze.

### Mniejsze

- **Mało danych o ścieżce LLM.** Wniosek „ścieżka ze znacznikami działa” stoi na 14 realnych liniach i 56/56 zwrotach znaczników. Zachowania LLM na nowych zakresach (cała kwestia mówcy z myślnikiem, zakres od pierwszego słowa) nie zmierzono, bo bez płatnych wywołań się nie da. K5c opisuje dopuszczalny wariant z myślnikiem poza zakresem.
- **C1 to rekonstrukcja.** Przekład Koori 03 pochodzi z odpowiedzi LLM z 2026-10-17, kiedy tłumacz widział jeszcze wersy; do powtórki złączyłem go w jedną linię. Dzisiejsze sformułowanie może być inne, ale klasa błędu (proporcjonalne ustawienie tagu styku) zależy tylko od braku znacznika.
- **Wielkość S3.** Prototyp przewiduje 85 zmienionych kwestii i 478 zmienionych szyldów. Przegląd jest duży; decyzja D1 to rozstrzyga.
- **K26 a wygląd mpv.** Klon dialogu dostaje biały tekst (`restyle.py:204-218`), więc różnica koloru pierwszego mówcy i tak znika. W6 chroni granice, nie przywraca koloru. Poza zakresem.
- **Odstępstwo od zlecenia.** Poza `gh issue view` uruchomiłem tylko do odczytu `git log`, `git show --stat`, `git branch -a` i `git merge-base --is-ancestor`, żeby ustalić baseline i erę plików. Stanu repo nie zmieniłem.

## Zgodność z kontraktem zlecenia

| Wymaganie zlecenia | Stan | Dowód |
| --- | --- | --- |
| Pełny przepływ znaczników z liniami i miejscami utraty | pass | evidence, tabela „Stan dziś” |
| 10–20 realnych przypadków z plikiem i linią | pass | evidence: C1–C6, C′ (3 opisane, 11 policzonych), D1–D6, B (Yasei 03) |
| Najmniejsza zmiana i katalog przypadków brzegowych | pass | specification: W1–W8, K1–K28 (zagnieżdżenia K24, cała linia K12/K13, wiele zakresów K4/K15, słowo znika K19/K22, słowo się dzieli K21) |
| Otwarte decyzje z rekomendacją | pass | D1–D5 |
| Plan: pliki, testy z markerami bez prozy, bramki, branch, commity | pass | plan |
| Bez zmian w kodzie, configu, workspace; bez płatnych API i subagentów | pass | zapis tylko w tym katalogu; ekstrakcja i prototypy w scratchpadzie |

## Wykonane kontrole

```text
mkvmerge -J / mkvextract: 15 tłumaczonych .pl.ass sparowanych ze źródłem; 32 z 47 wykluczone jako normalizacja PL
spis przyczyn: 254 pliki ASS, 1109 unikalnych kwestii i 3413 szyldów z akcentem
powtórka layout_translated na experiments/styles (Yasei 03, Iceblade S02E02): 7 unikalnych linii, 6 zgodnych
powtórka layout_translated na corpus-pairs bez znaczników: 18 linii bez znaczników (C2–C6)
layout_dialogue na Koori 03 l. 374: kursywa na „zbieram.” (C1)
prototyp W1–W3: 23/23 oczekiwań marked_text; kwestie bez znaczników 77 → 3
```

## Niewykonane lub nierozstrzygające kontrole

- Prototyp W4–W5 (ustawienie tagów).
- Zachowanie LLM na nowych znacznikach (wymaga płatnych wywołań).
- Ocena w mpv.

## Zalecany następny krok

1. Przegląd tej trójki dokumentów przez inną rodzinę modeli (`astra` albo `sol6`), skupiony na W1–W5, K5–K10 i D1.
2. Akceptacja właściciela: katalog K i decyzje D1–D5.
3. Dopiero potem wykonanie planu.

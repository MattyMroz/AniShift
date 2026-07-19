# Etap 4 — przegląd modułu translation: ustalenia (robocze)

> Zbieramy ustalenia przechodząc plik po pliku. To NIE plan implementacji — notatnik decyzji usera podczas przeglądu. Naprawy PO przeglądzie całości.

## Architektura — POTWIERDZONA, nie ruszamy

- Wszystko jest na swoim miejscu. Czanker zostaje w `translation/`.
- Tłumaczenie i ścieżka txt→SRT — na swoim miejscu.

## Zakres produktu — USTALONE

- **Tłumaczenie novelek/książek → NIE** (inna para kaloszy, wymaga specjalnego promptu literackiego, LLM zrobi się osobno). Nie robimy tego w tłumaczarce napisów.
- **txt → czankowanie → SRT → lektor → TAK** (szybki lektor do audiobooków). To tylko nadanie struktury (czankowanie + zamiana na SRT), potem normalna ścieżka.
- **Przepływ txt:** wrzuć txt do temp → zamień na czanki → tryb auto: opcjonalnie tłumaczy (flaga) → zlektoruje. Flaga wyłącza tłumaczenie.

## Ustalenia per plik

### chunking.py
- **Czanker MA sens** (tnie tekst — używa go tłumaczenie do cięcia przed API + ścieżka txt do audiobooka). ZOSTAJE.
- **PROBLEM: API czankera ma być w 100% POPRAWNE** — obecnie niedbałe:
  - martwa maszyneria (chunk_text/CharBreaker/WordBreaker nie wpięte w produkcję — do wpięcia w txt→SRT)
  - `_ABBREVIATIONS` legacy z angielskiego (Assn, Ave, Comdr...) + polskie niekompletne
  - **`chunk_limit=250` ZNIKNĄŁ z kodu — subagent usunął jako "martwą stałą" NIE sprawdzając że PLAN go wymaga** (etap-4-wymagania.md linie 53, 135, 164, 256). To 2. domyślny parametr cięcia txt (750=duże kawałki zdań, 250=mniejsze pod-kawałki). MUSI WRÓCIĆ przy naprawie chunkera + wpięciu w txt→SRT. Dowód że porządki wyrzuciły część specyfikacji.
  - `chr(0x2026)` nieczytelne (znaki przez kody zamiast wprost)
  - komentarze WHAT (# Cut categories...) do usunięcia
  - `_APOSTROPHES` dodane bez zamówienia — do przemyślenia
- **DOBRE (zostaje):** `frozenset({Pd,Pe,Pf,Po})` + generator znaków Unicode (kompletne, sensowne); struktura CharBreaker/WordBreaker (logiczna).

### linebreak.py
- **DZIAŁA poprawnie** (zweryfikowane na realnych zdaniach + interpunkcji): tnie po spójnikach, wielowyrazowe (`podczas gdy`, `ze względu na`) trzymane razem, krótkie nie dzielone, cudzysłowy/myślniki zachowane.
- **KIEDY dzieli — USTALONE (fakt o napisach anime):**
  - Napisy anime są POWSZECHNIE podwójne w oryginale: `coś tam \N coś tam` (2 wersy, angielski podział).
  - Napisy POLSKIE (`already_polish`) → JUŻ podzielone ludzko, NIE dzielimy.
  - Napisy OBCE (EN/JP→PL) → tłumaczymy → oryginalny podział `\N` się psuje (polskie słowa gdzie indziej) → DZIELIMY na nowo po polsku.
  - **Kod robi to POPRAWNIE:** `split_line` wołany tylko w `_translate_displayed` (przy tłumaczeniu); `_should_translate` pomija `already_polish` (runner:224,272). Czyli dzieli tylko przetłumaczone obce napisy, polskie zostawia.
- Mankament drobny: myślnik dialogowy ASCII `-` (nie `—`) czasem zostaje w środku wersu. Edge case.
- Jakość KODU w środku (374 linie) — jeszcze nie przejrzana.

### service.py — BŁĄD: podział linii zepsuty dla SRT
- **`_ASS_LINE_BREAK = "\N"` zahardkodowany na ASS** (service.py:33, użyty :199) — używany ZAWSZE, bez rozróżnienia formatu.
- **service.py NIE WIE jaki format** (ass/srt) — TranslationService nie dostaje `kind`.
- **Skutek:** ASS→`\N` OK; SRT→wstawia `\N` ale SRT wymaga zwykłego entera `\n` → w SRT pokaże się dosłownie "\N" zamiast podziału. **PODZIAŁ LINII ZEPSUTY DLA SRT.**
- Program obsługuje OBA formaty (wymagania R2) → to realny błąd. Nikt nie wyłapał bo brak testu na SRT (potwierdza zarzut o brakujących testach bitowych).
- **Do naprawy:** service musi znać format i użyć `\N` (ASS) albo `\n` (SRT). LUB podział robić na etapie zapisu (composition/etap 7) gdzie format jest znany.

### config.py (TranslationConfig)
- ✅ **DOBRE, user zadowolony** — wszystko sparametryzowane (engine, source_lang, batch_size, max_chars_per_request, max_retries, api_key), domyślne jako nazwane stałe `DEFAULT_*` (nie magiczne liczby), dataclass. NIE RUSZAĆ. Wzorzec do naśladowania.

## Ustalenia ogólne (do wszystkich plików)

- **Wybór tłumaczarki może być NONE** — da się wyłączyć tłumaczenie (txt→lektor bez tłumaczenia; napisy już po polsku). Flaga/opcja w settings.
- **TESTY: ZERO docstringów i komentarzy** — ale TYLKO pliki Z TESTAMI (`test_*.py`, funkcje `test_...`). Nazwy testów + asercje samo-opisujące. Wyjątek dyrektyw `# type: ignore`/`# noqa`. Wymaga wyjątku reguły D w pyproject dla test_*.
  - **`conftest.py` = WYJĄTEK, docstringi ZOSTAJĄ** — to konfiguracja pytest (stałe Final DATA_DIR/MM_AVH_TEMP/TRACKS_DATASET + fixtury), infrastruktura nie testy, CLAUDE.md wymaga docstringów dla Final.
- **Cięcie linii (linebreak) tylko przy TŁUMACZENIU obcych napisów.** Polskie (already_polish) mają gotowy podział, nie ruszamy.
- **Pełny przepływ podwójnej linii — ZWERYFIKOWANY, działa:**
  1. Napis obcy podwójny `coś tam \N coś tam` (2 wersy).
  2. `visible_text` (etap 3) ZWIJA `\N` → sklejone jedno zdanie (żeby tłumacz dostał całe zdanie, nie urwane pół).
  3. Tłumaczenie → przetłumaczone długie zdanie (>42 znaki, bo to były 2 wersy).
  4. `split_line` DZIELI z powrotem na wersy (bo za długie).
  - Kod: runner `_displayed_visible_texts` (skleja) → `_translate_displayed` (tłumaczy) → `split_line` (dzieli). POPRAWNE.

---

## PEŁNA DIAGNOZA MODUŁU (agent opus) — CO NIE GRA

### RDZEŃ NIEZROBIONY (najgorsze):
- **S1: Program NIE zapisuje przetłumaczonego ASS.** Tłumaczenie żyje w pamięci i ginie (runner.py:222-240). `replace_visible_text` (narzędzie do wstrzyknięcia tekstu do ASS z zachowaniem tagów) ISTNIEJE ale nieużywane. Zero wariantów eksportu (całościowy/lektorski/spoken). Zero reasemblacji pliku. Działa TYLKO txt→SRT. TO JEST SEDNO ETAPU 4.
- **S2: Cały chunker martwy** (chunk_text/CharBreaker/WordBreaker/LatinPunctuator ~200 linii, nieużywane produkcyjnie). Mini-ficzer txt→SRT NIE używa chunkera. `chunk_limit=250` z planu nieobecny.
- **S3: `BatchedLine.detected_lang`** produkowane w całym łańcuchu, nigdy czytane. Martwy kanał.

### BUGI DZIAŁANIA:
- **max_chars_per_request=4500 nadpisuje limity silników** (config.py:48 + constants.py:20). Google tnie na 4500 zamiast 15000 (SSOT google=15000 ignorowany). Marnuje 2/3 requestu, więcej wywołań = ryzyko bana. `DEFAULT_MAX_CHARS=4500` to wartość z głowy.
- **DeepL IGNORUJE batch_size** — DeeplConfig nie ma pola batch_size, chunkuje tylko po bajtach. `translation_batch_size` dla DeepL = no-op.
- **`\N` zahardkodowany dla ASS** (service.py:33,199) — zepsuty dla SRT (wstawi dosłowne "\N"). service nie zna formatu.
- **split_line NIE egzekwuje limitu znaków ani MAX_LINES** — 2 wersy po 59 znaków przy limicie 10. MAX_LINES martwa stała. Brak rekurencji (plan ją zakładał).

### NIEZAIMPLEMENTOWANE vs WYMAGANIA:
- **R5/R7: batching per silnik + równoległość NIE istnieją na fasadzie.** Zero semaforów/gather/concurrency. `translation_concurrency` nie ma w kodzie ani settings.
- **R6a Google-sklejaj/DeepL-raw bezprzedmiotowe** — visible_text zwija \n przed tłumaczeniem, więc cały ladder multiline w google/_batching.py działa na danych bez \n. Złożoność bez zastosowania.
- **Panel /settings wystawia TYLKO engine + max_retries** — brak fallback_chain, batch_size (są w UserSettings ale user nie zmieni z UI). "Panel steruje wszystkim" niezrealizowane.
- **target_lang, concurrency brak w settings** (wymagania §4).

### RETRY ROZJAZD:
- Google: liniowy inline backoff + blind except Exception (N8 zakazuje). DeepL: wykładniczy przez _retry helper. Dwa różne systemy dla "prostych API" mimo że R8 chciał jeden wzorzec.
- `_lang_codes.py` (deepl): niekompletna lista (_OVERRIDES tylko en/pt), bez walidacji nieobsługiwanych.

### DOBRE (nie ruszać):
- config.py (sparametryzowane), dedup.py, errors.py, rejestr silników, linebreak listy (76 spójników kompletne), LLM szkielet.

### BRAKUJĄCE TESTY:
- **KRYTYCZNE: test bitowy ASS round-trip** (wczytaj→przetłumacz→ZAPISZ→porównaj cały plik identyczny poza tekstem). NIE ISTNIEJE i NIE DA SIĘ napisać bo kod zapisujący ASS nie istnieje (S1).
- displayed re-split w pliku, fallback przez prawdziwy create_engine, already_polish/edge cases runnera, limit znaków respektowany, deepl retry/quota, linebreak przekroczenie limitu.

### TOP 5:
1. Nie produkuje przetłumaczonego ASS (S1) — sedno niezrobione
2. Chunker martwy + txt nie używa chunkera + brak 250 (S2)
3. Bug 4500 nadpisuje limit silnika (Google 4500 zamiast 15000)
4. Batching+równoległość nie istnieją; DeepL ignoruje batch_size; brak concurrency
5. split_line nie egzekwuje limitu ani MAX_LINES — R6b pozorne

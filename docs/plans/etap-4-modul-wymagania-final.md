# Etap 4 — moduł translation — WYMAGANIA FINALNE (jedno źródło prawdy)

> Ten dokument ZASTĘPUJE rozproszone rundy (`etap-4-wymagania.md`, `-v2.md`, `etap-4-plan.md`, `etap-4-przeglad-ustalenia.md`). To jedno źródło prawdy całego modułu `anishift/services/translation/` + jego wpięcia w pipeline.
>
> Napisany po diagnozie i **weryfikacji realnego kodu przez czytanie i uruchomienie** (nie z pamięci). Diagnoza z `etap-4-przeglad-ustalenia.md` była częściowo NIEAKTUALNA — moduł jest dużo dojrzalszy niż opisywała (fasada, dedup, fallback, rejestr, testy — GOTOWE). Ten dokument prostuje obraz i zostawia TYLKO realne, zweryfikowane braki.
>
> Legenda: ✅ decyzja usera (nietykalna) · 🔧 realny brak do naprawy (zweryfikowany) · ✔ zrobione i dobre (nie ruszać) · ⚠️ niespójność wyprostowana.

---

## A) Cel i zakres (prostym językiem)

**Co moduł robi:** bierze linie wyprodukowane przez etap 3 (dialogi do lektora = `spoken`, napisy na ekranie = `displayed`) i tłumaczy je na **polski** przez wybrany silnik (Google / DeepL / — w przyszłości — LLM). AniShift jest jednocześnie **lektorem** (czyta `spoken`) i **tłumaczarką napisów** (produkuje przetłumaczony `displayed`), więc tłumaczy oba tory.

**Trzy wejścia:**
1. **ASS** (napisy anime ze stylami/tagami) → przetłumaczony ASS (ten sam format).
2. **SRT** (napisy proste, np. z Netflixa) → przetłumaczony SRT (ten sam format).
3. **TXT** (goły tekst) → audiobook: czankowanie na linie → tłumaczenie → SRT lektorski. To „szybki lektor".

**Co moduł NIE robi:**
- **Nie tłumaczy novelek/książek literacko** — to inny produkt (wymaga promptu literackiego, robimy osobno w LLM). Tłumaczarka napisów ≠ tłumacz literacki.
- **Nie składa wariantów w pliki/ścieżki MKV** — to etap 7 (composition). Etap 4 PRODUKUJE przetłumaczone dane i zapisuje przetłumaczony plik napisów; muxowanie wariantów, nazewnictwo ścieżek, wybór formatu eksportu = etap 7.

**Kluczowe decyzje usera (nietykalne):**
- ✅ **Target zawsze `pl`** — zero multi-języka (`TARGET_LANG="pl"` w `constants.py`).
- ✅ **Silnik może być NONE** — flaga wyłącza tłumaczenie (txt→lektor bez tłumaczenia; napisy już polskie). Realizacja: pusty łańcuch / `already_polish` / brak dostępnego silnika → plik przechodzi bez tłumaczenia.
- ✅ **Format wyjścia = jak wejście** (ASS→ASS, SRT→SRT). `\N` dla ASS, `\n` dla SRT.
- ✅ **User ma klucz DeepL Free** (`:fx`, 500k znaków/mies., 39-znakowy klucz w `.env` — zweryfikowane).

---

## B) Przepływ end-to-end

### B.1 Ścieżka MKV/AST/SRT (główna)

```
MKV → [etap 3: identify → select → extract → split → write displayed(oryginał)]
    → KROK translate (etap 4):
         E1  already_polish → pomiń (napisy już polskie)
         E2  zero spoken i zero displayed → pomiń (nic do tłumaczenia)
         │
         ├─ spoken:    [SpokenLine, ...]  (start/end/style + text bez \n)
         └─ displayed: [visible_text(event), ...]  (widoczny tekst zdarzeń displayed)
         │
         ▼  TranslationService.translate_file(spoken, displayed, cancel)
         │   • dedup obu torów osobno (dict.fromkeys — 1 linia = 1 request)
         │   • łańcuch [engine, *fallback] filtrowany is_available
         │   • engine.translate_batch(unique) z retry/backoff na 429/503
         │   • redistribute → per-line
         │   • FASADA buduje TranslatedLine (timing/style ze SpokenLine)
         │   • displayed: re-podział przetłumaczonej linii na wersy (linebreak)
         ▼  FileTranslation(spoken: tuple[TranslatedLine], displayed: tuple[str], engine_id, raport)
         │
         ▼  🔧 ZAPIS przetłumaczonego pliku napisów na dysk  ← SEDNO (S1)
         │   • wstrzyknij przetłumaczony displayed z powrotem do zdarzeń ASS/SRT
         │     przez replace_visible_text (zachowaj TAGI/STYLE/TIMINGI)
         │   • join wersów formatem: \N (ASS) / \n (SRT)  — format-aware
         │   • zapis do <stem>.pl.<kind> (ten sam format co wejście)
         ▼  FileOutcome(translation=result, translated_path=<stem>.pl.<kind>, ...)
```

**Co się dzieje z przetłumaczonym tekstem (krytyczne — obecnie ginie w pamięci):**
`spoken` (dla lektora) żyje w `FileTranslation.spoken` i płynie do etapu 6 (TTS) przez `FileOutcome.translation` — NIE zapisuje się na dysk jako osobny artefakt (✅). `displayed` (napisy dla widza) MUSI trafić z powrotem do pliku napisów tego samego formatu — to jest S1, obecnie niezrobione: fasada produkuje `FileTranslation.displayed`, ale runner nigdzie go nie zapisuje. Narzędzie `replace_visible_text` (`subtitles/text.py`) ISTNIEJE i jest gotowe, ale NIEUŻYWANE.

### B.2 Ścieżka TXT (mini-ficzer audiobook)

```
TXT → txt_to_spoken (czankowanie po zdaniach/słowach, chunk_limit)
    → TranslationService.translate_file(spoken, displayed=[])
    → spoken_to_srt(result.spoken, <stem>.pl.srt)   ← JUŻ DZIAŁA
```

### B.3 Warianty eksportu (granica z etapem 7 — udokumentowane, NIE implementowane w etapie 4)

Etap 7 składa z danych etapu 4 trzy warianty (zależnie od trybu `/settings`):
- **całościowy** (`{stem}.pelny.pl.ass`) — displayed + spoken po polsku,
- **lektorski** (`{stem}.lektor.pl.ass`) — tylko displayed po polsku (lektor czyta dialogi),
- **spoken** — same przetłumaczone dialogi.

Tryb MKV merge: warianty jako ścieżki w kontenerze (`--track-name "Polski (pełny)"`). Tryb player: sufiksy wariantu przed kodem języka (MPV wymaga `sub-auto=fuzzy`). Wybór formatu ASS/SRT: tylko w trybie player. **To wszystko robi etap 7.** Etap 4 zapisuje JEDEN przetłumaczony plik napisów (`{stem}.pl.<kind>`, format jak wejście) jako dowód i wsad dla etapu 7.

---

## C) Wymagania funkcjonalne

Numeracja spójna z poprzednimi rundami (R = funkcjonalne). Stan każdego: ✔ zrobione / 🔧 do naprawy.

### Rdzeń (rejestr, fasada, dedup) — ZROBIONE, nie ruszać
- **R1 ✔ Krok `translate` w pipeline** — jest w `_process_mkv` (po `write`) i `_process_txt`. `StepName` ma `"translate"`.
- **R2 ✔ Rejestr silników** — `engines/__init__.py`: `_REGISTRY`, `available_engine_ids()`, `create_engine()`, guardy (pusty/nieznany/llm → `TranslationConfigError` z posortowaną listą), lazy `importlib`, logger. `TranslationEngineId = Literal["google","deepl","llm"]`.
- **R3 ✔ Fasada sync** — `TranslationService`, zero `if engine_id == ...`, cache pominięty (plik raz).
- **R4 ✔ Dedup unikalnych** — `dedup.py` (`deduplicate`/`redistribute`/`redistribute_flags`), `dict.fromkeys`, deterministyczny. Wspólny; silnik nie deduplikuje sam. Spoken i displayed dedupują się osobno.
- **R9 ✔ Fallback = cały plik od nowa** — fasada iteruje `[engine, *fallback_chain]`, filtruje `is_available`, przy `Quota/RateLimit/Auth/Engine` idzie do następnego; łańcuch pusty → `FileTranslation.error` (plik failed, reszta leci).
- **R10 ✔ Pomijanie już-polskich** — `_should_translate` guard na `already_polish`.
- **R12 ✔ Błąd jednego pliku nie ubija reszty** — `_process_mkv` łapie precyzyjnie, zwraca failed outcome.

### Zapis wyniku — 🔧 SEDNO NIEZROBIONE
- **R14 🔧 (S1) Zapis przetłumaczonego pliku napisów.** Po tłumaczeniu displayed MUSI trafić z powrotem do pliku napisów tego samego formatu:
  - iteruj zdarzenia displayed pliku, wstrzyknij przetłumaczony `visible_text` przez `replace_visible_text` (zachowaj `{...}` tagi, style, timingi zdarzenia),
  - **zachowaj strukturę pliku jak etap 3** (`write_displayed` wzorzec: kopia `info`/`styles`/eventów, tylko tekst dialogu podmieniony),
  - zapis atomowy (`.tmp` + `replace`) do `<stem>.pl.<kind>`,
  - format wyjścia = format wejścia (ASS→ASS, SRT→SRT).
  - **Test bitowy** (patrz §F): wczytaj realny ASS → przetłumacz → zapisz → plik identyczny z oryginałem POZA tekstem dialogu (liczba eventów, style, timingi, tagi bez zmian).

### Podział linii — 🔧 częściowo
- **R15 🔧 Format-aware line break.** Displayed re-dzielony na wersy joinowany separatorem zależnym od formatu: `\N` dla ASS, `\n` dla SRT. Obecnie zahardkodowany `\\N` w `service.py` (linia 33/199) — **zepsuty dla SRT** (wstawia dosłowne „\N"). Fasada / warstwa zapisu musi znać `kind`.
- **R6b 🔧 split_line egzekwuje limit + rekurencja + MAX_LINES.** `linebreak.split_line` tnie po hierarchii (interpunkcja→spójnik→środek, listy PL kompletne — ✔ dobre), ale zwraca tylko `(left, right)` bez rekurencji: gdy wers wciąż > `max_chars`, nie dzieli dalej; `MAX_LINES` (=2) to martwa stała. Naprawa: rekurencja w nadwymiarowe części ograniczona przez `MAX_LINES` (po osiągnięciu limitu wersów akceptuj dłuższy wers, nie tnij w nieskończoność).
- **R6a ✔ Wieloliniowe napisy per silnik** — `SpokenLine.text` NIE ma `\n` (`visible_text` zwija whitespace), więc dla spoken problem sklejania nie istnieje. Displayed przepuszczane przez `visible_text` → jednoliniowe. Google joinuje batch zero-width separatorem i re-splituje (`_batching.py`); DeepL batch listą. Markery widoczne odrzucone (✅). To działa.

### Batching, limity, równoległość — 🔧
- **R5 🔧 Batching napisów po liczbie linii per silnik.** Google batchuje w `_batching._chunks` (batch_size + max_chars). DeepL 🔧 **ignoruje batch_size** — `DeeplConfig` nie ma pola `batch_size`, tnie tylko po bajtach (`_chunk_by_bytes`). Naprawa: DeepL respektuje `batch_size` (limit linii) obok limitu bajtów.
- **R5a 🔧 Twardy limit znaków per request + bug 4500.** Google SSOT = 15000 (`google/constants.py`), DeepL = 128 KiB (`deepl/constants.py`) — DOBRE. ALE 🔧 **bug 4500 LIVE**: `TranslationConfig.max_chars_per_request` defaultuje `DEFAULT_MAX_CHARS=4500`, a `GoogleService.__init__` KOPIUJE `config.max_chars_per_request` nad swój SSOT 15000 → przez fasadę Google dostaje 4500 (zweryfikowane uruchomieniem). Marnuje 2/3 requestu, więcej wywołań = ryzyko bana. Naprawa: silnik ma używać SWOJEGO limitu (SSOT w `google/constants.py`); domenowy `max_chars` nie może go zaniżać poniżej limitu silnika. Najprościej: usuń `max_chars_per_request` z `TranslationConfig` (silnik trzyma własny) — patrz §D.
- **R7 🔧 Równoległość / concurrency — NIE ISTNIEJE.** Zero semaforów/gather na fasadzie. `translation_concurrency` nie ma w kodzie. Wymaganie: batche w pliku równolegle (semaphore, konserwatywny, konfigurowalny). ⚠️ **Rozstrzygnięcie (simple, krok 1 — kwestionuj wymóg):** obecny runner auto-mode już puszcza PLIKI równolegle (ThreadPoolExecutor). Dokładanie concurrency batchy WEWNĄTRZ pliku przy równoległych plikach = zwielokrotnienie obciążenia API × liczba plików × concurrency → prosta droga do bana Google. Google jest sekwencyjny „by design" (`_batching` bez gather) właśnie po to. **Dla etapu 4 concurrency batchy pozostaje 1 (sekwencyjne batche w pliku); równoległość jest na poziomie PLIKÓW (już jest).** Dodajemy `translation_concurrency` do settings jako parametr konfiguracyjny (przeżywa restart, sterowalny), ale realne zrównoleglanie batchy odkładamy do skryptu obciążeniowego (Tropy) — YAGNI teraz, ryzyko bana realne. To świadome odstępstwo, uzasadnione bezpieczeństwem API.

### Retry — 🔧 ujednolicić
- **R8 🔧 Retry + backoff — JEDEN wzorzec.** DeepL używa `_retry.call_with_retry` (wykładniczy, precyzyjny wyjątek). Google 🔧 ma WŁASNY inline backoff w `_call_with_retry` (`google/service.py:84`) + `except Exception` (blind, N8/BLE001 stłumione noqa). Naprawa: Google używa tego samego `call_with_retry` co DeepL (jeden wzorzec, R8), łapiąc precyzyjny typ zamiast blind `except Exception`.
- **R8a ✔ Limit ponowień konfigurowalny** — `translation_max_retries` w settings, range 0..10.

### TXT / chunker — 🔧
- **R6 🔧 chunk_limit=250 + chunker.** `chunking.py` (`LatinPunctuator`/`CharBreaker`/`WordBreaker`/`chunk_text`) jest MARTWY produkcyjnie — txt path używa `txt_to_spoken` (chunk po zdaniach, max 750). Z `chunking.py` żywe są tylko `ZERO_WIDTH`, `SENTENCE_ENDINGS`, `phrase_cut_chars` (import przez google/linebreak). `chunk_limit=250` (z planu) NIE ISTNIEJE. **Rozstrzygnięcie — patrz §D (co usunąć).**

### Progres, silniki
- **R11 ✔ Silniki google, deepl (+ llm szkielet)** — wszystkie w rejestrze. Google darmowy (`is_available`=True), DeepL `is_available`=`bool(api_key)`, llm guard w `create_engine`.
- **R13 ✔ Progress: pasek per plik** — runner reużywa `MultiProgressManager`/`on_progress`. (Krok translate nie ma jeszcze własnego postępu — akceptowalne: pasek pliku, błędy w raporcie końcowym.)

### Niefunkcjonalne (N)
- **N1 ✔** Źródło nietknięte — `SpokenLine` frozen, tłumaczenie tworzy `TranslatedLine`.
- **N2 ✔** Determinizm dedup — `dict.fromkeys`.
- **N3 ✔** Zero `sys.exit()`/`input()` w serwisie.
- **N6 ✔** Lazy import silników — rejestr nie importuje googletrans/deepl.
- **N7 ✔** Testowalność bez sieci — dedup/linebreak/chunking/rejestr/fasada z fake enginem; realne API tylko `@pytest.mark.network`.
- **N8 🔧** Nie blind `except Exception` — łamane w `google/service.py:90` i `_batching.py:60,84` (noqa BLE001). Naprawa min.: Google service retry przez `call_with_retry` z precyzyjnym typem. `_batching` ladder fallback (per-line na dowolny błąd batcha) — świadomy szeroki łap, ale zawężyć do wyjątków googletrans jeśli się da; jeśli googletrans nie ma stabilnej hierarchii, zostaw z noqa i komentarzem WHY (jest).

---

## D) Co USUNĄĆ (martwe/legacy) — decyzja per rzecz

Zasada simple krok 2: domyślnie kasuj. Każda pozycja z uzasadnieniem.

| Rzecz | Decyzja | Uzasadnienie |
|---|---|---|
| **`BatchedLine.detected_lang`** (produkowane w google `_batching`, deepl service, typie) | **USUŃ** kanał | Nigdy nie czytane (S3 zweryfikowane — grep: tylko zapis, zero odczytu poza testami). Martwy kanał danych. AniShift zawsze tłumaczy na `pl` z `auto` — wykryty język źródła do niczego nie służy. Usuń pole z `BatchedLine`, przestań je produkować w silnikach. |
| **`chunk_text` / `CharBreaker` / `WordBreaker` / `WordBreaker`+`_Breaker`** w `chunking.py` | **USUŃ** martwą maszynerię | Nieużywane produkcyjnie (txt path = `txt_to_spoken`). ~200 linii bez konsumenta. ZOSTAW tylko to co żywe: `ZERO_WIDTH`, `SENTENCE_ENDINGS`, `phrase_cut_chars` (używane przez google/linebreak). Plik `chunking.py` skurczy się do współdzielonych stałych/funkcji punktacji Unicode. `chunk_limit=250` — NIE dodawaj (nie ma konsumenta; `txt_to_spoken` ma własny `max_chars=750`; dodanie 250 = wymóg bez odbiorcy). **⚠️ Świadome odstępstwo od `chunk_limit=250` z planu:** wymóg zakładał pełny chunker w txt path; realnie txt path go nie potrzebuje (simple krok 1: kwestionuj wymóg — 250 nie ma konsumenta). Jeśli user upiera się przy 250 → wraca jako `txt_to_spoken(max_chars=250)` parametr, ale bez maszynerii CharBreaker. |
| **`_ABBREVIATIONS` legacy angielskie** (Assn, Ave, Capt, Comdr, Corp, Cpl, Gov, Hon, Inc, Lieut, Ltd, Rev, Univ, Jan..Dec, dept, ed, est, vol, vs) w `chunking.py` | **USUŃ** angielskie, jeśli `get_sentences` zostaje | `get_sentences` należy do `LatinPunctuator` — jeśli usuwamy `CharBreaker`/`chunk_text`, `LatinPunctuator.get_sentences` też traci konsumenta produkcyjnego. Wtedy CAŁA klasa `LatinPunctuator` do usunięcia (razem z `_ABBREVIATIONS`, regexami zdań/paragrafów). Zostaje tylko `_PHRASE_CUT_CHARS`/`phrase_cut_chars()` + `SENTENCE_ENDINGS` + `ZERO_WIDTH` (używane). To najczystsze cięcie. |
| **`_APOSTROPHES`** w `chunking.py` | zostaje jeśli używane w `_PHRASE_CUT_CHARS` exclude | Używane w `_punctuation_chars(exclude=SENTENCE_ENDINGS+_APOSTROPHES)` — żywe (chroni `don't`). Zostaw. |
| **`max_chars_per_request` w `TranslationConfig`** | **USUŃ** z domenowego configu | Źródło buga 4500. Limit znaków należy do SILNIKA (SSOT w `google/constants.py`=15000, `deepl/constants.py`=128KiB). Domenowy config nie powinien go nieść ani zaniżać. Usuń pole; silnik używa swojej stałej. (`DEFAULT_MAX_CHARS` w domenowym `constants.py` też usuń jeśli osierocony.) |
| **`MAX_LINES` w `linebreak.py`** | **WEPNIJ** (nie usuwaj) | Martwa stała, ale sensowna — wepnij w rekurencję split_line (R6b): po `MAX_LINES` wersach akceptuj dłuższy wers zamiast ciąć dalej. |
| **`_ASS_LINE_BREAK` hardkod w `service.py`** | **NAPRAW** na format-aware | Nie usuwaj — zamień na parametr `kind`-zależny (`\N`/`\n`). |
| Martwa maszyneria multiline google (marker ladder) | **ZOSTAW** | `_batching.py` separator+ladder DZIAŁA i chroni index↔index (zweryfikowane testem). Nie martwe — to rdzeń gwarancji kolejności Google. |

---

## E) Konfiguracja /settings

Panel steruje wszystkim, co ma sens sterować z UI. Wzorzec `TranslationConfig` (✔ dobry, sparametryzowany — NIE ruszać wzorca) + `user_settings` walidacja `_clean_*`.

**Pola w `UserSettings` (stan obecny — większość ZROBIONA):**

| pole | typ | default | walidacja | stan |
|---|---|---|---|---|
| `translation_engine` | `str` | `"google"` | ∈ `available_engine_ids()` | ✔ |
| `translation_fallback_chain` | `list[str]` | `["google"]` | `_clean_str_list` ∈ engine_ids | ✔ |
| `translation_batch_size` | `int` | `0` (=auto) | `BATCH_SIZE_RANGE` 0..500 | ✔ |
| `translation_max_retries` | `int` | `3` | `MAX_RETRIES_RANGE` 0..10 | ✔ |
| `translation_concurrency` | `int` | `1` | `CONCURRENCY_RANGE` 1..16 | 🔧 dodać (parametr; realne zrównoleglanie odłożone — R7) |
| `llm_model`/`llm_temperature`/`llm_top_p`/`llm_max_output_tokens` | — | — | zakresy | ✔ (etap 5) |

`target_lang` — ✅ zawsze `pl`, NIE pole (SSOT `constants.TARGET_LANG`). Nie dodawać do settings (multi-język odrzucony).

**Panel (`settings_panel.py`) — stan:** ✔ derywuje engine z `available_engine_ids()` (llm ukryty, deepl gdy klucz), edytuje `translation_engine` + `translation_max_retries` + mode/tts/voice/tempo/volume/output. `fallback_chain`, `batch_size`, `concurrency`, params LLM = ręczna edycja `settings.json` w etapie 4 (multi-select UI = późniejszy refaktor panelu, ✅ user planuje refaktor UI). To KISS — nie budujemy multi-select w etapie 4.

---

## F) Testy wymagane

Zasada: **testy bez docstringów/komentarzy** (nazwy + asercje samoopisujące; `conftest.py` wyjątek — docstringi zostają). Stan obecny: 10 plików testów translation + `test_pipeline_translate` + `test_subtitles_srt`, wszystkie zielone (~824 testów).

**🔧 KRYTYCZNY brakujący — TEST BITOWY ASS round-trip:**
- Wczytaj realny ASS (z `../mm_avh_working_space/temp/dataset_ass/`, 183 pliki) → zbuduj split → przetłumacz przez FAKE engine (deterministyczny, bez sieci, np. prefix „PL:") → ZAPISZ cały przetłumaczony plik → **porównaj że identyczny z oryginałem POZA tekstem dialogu**:
  - liczba zdarzeń Dialogue displayed = bez zmian,
  - style (sekcja `[V4+ Styles]`) = bajt w bajt,
  - timingi (start/end każdego eventu) = bez zmian,
  - tagi `{...}` w tekście = zachowane (tylko widoczny tekst podmieniony),
  - separator wersów = `\N` (nie `\n`).
- To samo dla **SRT** (separator `\n`, nie dosłowne „\N").
- Wzorzec liczby jak etap 3 (2483 eventy → 2483). Bez sieci (fake engine) → deterministyczny, w bramce `pytest`.

**Edge case'y do pokrycia (część już jest):**
- E1 already_polish pomija (✔ `test_should_translate_skips_polish`).
- E2 zero linii → dalej (✔ `test_empty_streams_return_empty_result`).
- fallback quota → następny silnik (✔ `test_fallback_chain_uses_next_engine_on_quota`).
- łańcuch wyczerpany → error (✔ `test_exhausted_chain_sets_error`).
- Ctrl+C → `TranslationError` (✔ `test_cancel_raises_translation_error`).
- 🔧 **bug 4500** — test że Google zbudowany przez fasadę używa 15000, nie 4500.
- 🔧 **split_line limit** — przetłumaczona monstrualna linia dzielona do ≤max_chars (z rekurencją) albo akceptowana po MAX_LINES.
- 🔧 **format-aware** — displayed SRT dostaje `\n`, ASS `\N`.
- 🔧 **DeepL batch_size** — respektuje limit linii (mock SDK).

**Network smoke (opt-in `-m network`):** realny Google EN→PL (✔ jest); dodać realny DeepL z kluczem usera (39-znakowy `:fx` obecny) — ta sama liczba linii, timingi nietknięte.

---

## G) Co ZOSTAJE (dobre — nie przepisywać)

- **`config.py`** (`TranslationConfig`) — forward-compatible, warn na unknown keys, guard na `engine`, sparametryzowany. ✔ Wzorzec. (Tylko usunąć `max_chars_per_request` — źródło buga.)
- **`dedup.py`** — czyste funkcje, deterministyczne, testowalne. ✔
- **`errors.py`** — hierarchia `TranslationError → {Engine,Config,Auth,Quota,RateLimit}Error` z mixinami `Transient/Fatal`. ✔
- **`engines/__init__.py`** — rejestr kanoniczny, guardy, lazy. ✔
- **`_retry.py`** — sync `call_with_retry`, backoff, precyzyjny wyjątek. ✔ (Google ma go zacząć używać.)
- **`linebreak.py` listy** — spójniki/przyimki PL kompletne z Wiktionary (single + multiword), `_NON_BREAKING_HEADS`, hierarchia wag. ✔ (Tylko dodać rekurencję/MAX_LINES.)
- **`protocols.py`** — `TranslationEngine` (sync), `LlmCompleter`. ✔
- **`types.py`** — `TranslatedLine`/`FileTranslation`. ✔ (Usunąć `detected_lang` z `BatchedLine`.)
- **`engines/llm/`** — szkielet (numeracja `[N]`, walidacja) — realizacja/test etap 5. ✔
- **`subtitles/text.py`** — `visible_text`/`replace_visible_text` — narzędzia zapisu ASS. ✔ (S1 ma ich zacząć używać.)
- **`subtitles/service.py` `write_displayed`** — wzorzec reasemblacji ASS (kopia info/styles/eventów, atomowy zapis). ✔ (S1 wzoruje się na nim.)

---

## Podsumowanie realnych braków do naprawy (KROK 2)

1. **S1 (R14):** zapis przetłumaczonego displayed ASS/SRT na dysk (`replace_visible_text`, format-aware, test bitowy).
2. **R15:** format-aware line break `\N`/`\n` (usuń hardkod).
3. **R5a bug 4500:** silnik używa swojego limitu (usuń `max_chars_per_request` z domenowego configu).
4. **R6b/MAX_LINES:** `split_line` rekurencja + egzekwowanie limitu + MAX_LINES.
5. **R5 DeepL batch_size:** respektuj limit linii obok bajtów.
6. **R8/N8 retry:** Google używa wspólnego `call_with_retry`, precyzyjny wyjątek.
7. **S3 martwe:** usuń `detected_lang`; usuń martwą maszynerię chunkera + angielskie `_ABBREVIATIONS`.
8. **R7 concurrency:** dodaj parametr `translation_concurrency` do settings (realne zrównoleglanie batchy odłożone — bezpieczeństwo API).

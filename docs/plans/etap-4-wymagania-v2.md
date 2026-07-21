# Etap 4 — tłumaczenie — WYMAGANIA v2 (przemyślane i rozstrzygnięte)

> Ten dokument to **przemyślana, rozstrzygnięta wersja wymagań** — moje (Fable) przejście przez `etap-4-wymagania.md` własnymi słowami, z rozstrzygnięciem KAŻDEGO otwartego 🏗️ i wyłapaniem niespójności. To jest tablica prawdy gotowa do implementacji. Plan implementacji (kod, kolejność, testy) żyje osobno w `etap-4-plan.md`.
>
> Legenda: ✅ = decyzja usera (nietykalna), 🏗️→✔ = otwarte 🏗️ które TU rozstrzygam, ⚠️ = niespójność którą prostuję.
>
> Fundament: przeczytałem w całości realny kod etapu 3 (`anishift/services/subtitles/`, `pipeline/runner.py`, `config/`), cały moduł `mangashift/services/translation/` (26 plików), `mm_avh/modules/translator.py`, `scripts/tmp/text_chunker.py` + `srt_equalizer_reference.py`, oraz standardy architektury (engine-factory / engine / service / naming-glossary).

---

## 0. Streszczenie w jednym akapicie

Etap 4 dodaje domenę `anishift/services/translation/` — **pierwszy rejestr silników** w projekcie. Linie wyprodukowane przez etap 3 (`spoken` w pamięci jako `tuple[SpokenLine, ...]` + `displayed` jako zdarzenia w `SSAFile`) przechodzą przez fasadę `TranslationService`, która przez rejestr `engines/__init__.py` wybiera silnik (`google`/`deepl`/`llm`), deduplikuje unikalne linie, tnie na batche, tłumaczy z retry+fallback, a przetłumaczone teksty re-dzieli na wersy własnym algorytmem hierarchicznym. Kod jest **sync** (świadome odstępstwo od MangaShift, które jest async pod REST). Wynik to nowy typ `TranslatedLine` (źródło `SpokenLine` nietknięte). Silnik `llm` istnieje w rejestrze od teraz jako szkielet (adapter), ale jego realizacja/test to etap 5. Wszystko sterowalne z `/settings`.

---

## 1. Fakty z realnego kodu (fundament, zweryfikowane czytaniem)

Te fakty są **ZWERYFIKOWANE** (przeczytałem pliki), nie założone:

1. **Etap 3 produkuje `SpokenLine(start: int, end: int, text: str, style: str)`** — `frozen=True, slots=True` (`anishift/services/subtitles/types.py:22`). Tekst jest już po `visible_text()` (bez tagów ASS/HTML, whitespace scollapsowany do pojedynczych spacji, `\N`/`\n`/`\h` zamienione na spację) oraz po collapse FBF. **KRYTYCZNE:** `SpokenLine.text` NIE zawiera `\n` — `visible_text()` (`text.py:42`) robi `_RE_SPACES.sub(" ", ...)`, więc każda spoken linia to JEDNA linia bez łamania. To zmienia obraz R6a (patrz §5).
2. **`displayed` to zdarzenia w `SSAFile`**, nie oczyszczony tekst. Etap 3 pisze plik `<stem>.displayed.<kind>` przez `write_displayed()` (`service.py:205`) — kopiuje oryginalne zdarzenia `Dialogue` sklasyfikowane jako `displayed`, z zachowaniem tagów ASS i oryginalnego łamania (`\N`). Ten plik jest w oryginalnym języku. Etap 4 ma go przetłumaczyć.
3. **`SubtitleSplit`** (`types.py:44`) niesie: `kind`, `subs: SSAFile` (pełny plik), `decisions: tuple[Decision, ...]` (per zdarzenie Dialogue: `"spoken"`/`"displayed"`), `verdicts`, `spoken: tuple[SpokenLine, ...]`, `stats`. To jest kompletny materiał do produkcji wariantów.
4. **Runner NIE wypuszcza dziś `spoken` ani przetłumaczonego `displayed`** — `_process_mkv` (`runner.py:132`) liczy statystyki i pisze oryginalny displayed przez `write_displayed`. `spoken` żyje tylko w `split.spoken` i ginie. Etap 4 wpina krok `translate` po `write` w `_process_mkv`.
5. **`FileOutcome`** (`pipeline/types.py:41`) jest `@dataclass(slots=True)` (mutowalny), ma pola `spoken_lines`, `displayed_events`, `already_polish`. Etap 4 dołoży pola raportu tłumaczenia.
6. **`StepName`** (`pipeline/types.py:24`) = `Literal["identify", "select", "extract", "split", "write", "txt"]`. Dojdzie `"translate"`.
7. **Klucz DeepL** — `Settings.deepl_api_key` (`config/settings.py:53`, env `ANISHIFT_DEEPL_API_KEY`), domyślnie `""`. User MA klucz Free (`:fx`).
8. **`UserSettings.translation_engine: str = "google"`** (`user_settings.py:77`) już istnieje jako placeholder. Panel (`settings_panel.py:33`) ma statyczną listę `("google", "deepl", "llm")` z komentarzem „real list arrives in stage 4".
9. **Wzorzec walidacji `UserSettings`**: `load_user_settings()` filtruje po `known` polach, potem `_clean_string`/`_clean_number`/`_clean_bool` odrzucają wartości spoza dozwolonego zbioru/zakresu → fallback do defaultu (`user_settings.py:96-145`). Zapis atomowy przez `.tmp` + `replace`.
10. **`extraction` = zwykły moduł** (funkcje w `service.py`, re-export w `__init__.py`, `errors.py` liść po `AniShiftError`). `subtitles` tak samo. To wzorzec „zwykłego serwisu" AniShift.
11. **`AniShiftError`** (`errors.py:110`) niesie `ErrorContext(code, message, suggestion, docs_url, details)`. `TransientError`/`FatalError` to mixiny-podklasy. `ErrorCode` (StrEnum) MA już `TRANSLATION_FAILED`, `TRANSLATION_ENGINE_ERROR`, `TRANSLATION_RATE_LIMITED` (`errors.py:62-64`) — etap 4 je konsumuje.
12. **`MultiProgressManager`** (`utils/rich_console/progress/multi.py:197`) — `add_task(description, *, total=100, ...) -> TaskID`, `update(task_id, completed)`. Runner używa go przez Protocol `ProgressReporter` (`pipeline/types.py:66`). Etap 4 reużywa 1:1 — jeden pasek per plik.
13. **`_process_mkvs`** ma dwie ścieżki: manual (sekwencyjnie, z `interaction`) i auto (ThreadPoolExecutor per plik + `MultiProgressManager`). `cancel: threading.Event` propaguje Ctrl+C.
14. **Zależności JUŻ w `pyproject.toml`**: `deepl>=1.30.0`, `googletrans>=4.0.2`, `httpx>=0.28.1`, `anthropic`, `google-genai`, `openai`. **Zero `uv add` potrzebne dla etapu 4.** ⚠️ (wymagania mówiły „sprawdź co jest" — sprawdziłem: wszystko jest).
15. **`utils/_retry.py` NIE istnieje w AniShift** — MangaShift ma `mangashift/utils/_retry.py` (tenacity), ale `anishift/utils/` jest 1:1 z mm_avh i **nietykalny** (CLAUDE.md). Etap 3 (`extraction/service.py`) robi retry ręcznie (backoff w pętli). ⚠️ To znaczy: **nie mogę skopiować `build_retry` do utils**. Rozstrzygnięcie w §7.

---

## 2. Cel etapu (moimi słowami)

Zamienić linie z etapu 3 (angielskie/obce) na polskie przez **rejestr silników**. AniShift jest jednocześnie lektorem (czyta `spoken`) i tłumaczarką napisów (produkuje przetłumaczony `displayed`), więc **tłumaczymy oba tory**. Silniki: `google` (darmowy, bez klucza), `deepl` (oficjalne API, klucz usera), `llm` (rejestr od teraz, realizacja etap 5). Etap 4 PRODUKUJE przetłumaczone linie — składanie ich w pliki/ścieżki MKV to etap 7.

---

## 3. Model danych i typ wyniku — 🏗️→✔ ROZSTRZYGNIĘTE

### 3.1 Typ wyniku: `TranslatedLine`

`SpokenLine` jest `frozen` — nie mutujemy (N1). Tłumaczenie tworzy nowy typ. **Rozstrzygam:**

```python
@dataclass(frozen=True, slots=True)
class TranslatedLine:
    """One translated line: source paired with its Polish rendering."""
    start: int          # skopiowane z SpokenLine (timing nietknięty)
    end: int
    source_text: str    # oryginał (z SpokenLine.text) — do odwracalności / raportu
    text: str           # przetłumaczony tekst (JEDNA linia, bez \n — dla spoken)
    lines: tuple[str, ...]  # przetłumaczony tekst PO re-podziale na wersy (dla displayed / czytelności)
    style: str          # skopiowany ze źródła
    ok: bool = True     # False = tłumaczenie padło, text == source_text (fallback padding)
```

**Uzasadnienie kształtu:**
- `start`/`end`/`style` skopiowane → etap 6 (TTS) i etap 7 (composition) mają komplet bez sięgania do `SpokenLine`.
- `source_text` zostaje → odwracalność (N1), raport, debug, i re-tłumaczenie fallbackiem bez gubienia oryginału.
- `text` (jedna linia) vs `lines` (krotka wersów) — **rozdzielam dwa byty**: lektor (TTS) czyta `text` ciągiem (A6 wymagań: lektor czyta ciągiem, podział mu niepotrzebny), a napisy dla widza (`displayed`) potrzebują `lines` (czytelne wersy). Jedno pole nie obsłuży obu bez zgadywania konsumenta. Dla spoken `lines` może być `(text,)` (jeden wers).
- `ok` — spójne z MangaShift `BatchedLine.ok`/`LineTranslation.ok`. Padding źródłem przy porażce pojedynczej linii.

### 3.2 Osobny typ dla `displayed`?

`displayed` to zdarzenia ASS z tagami, nie `SpokenLine`. Tłumaczenie displayed operuje na `visible_text()` zdarzenia, a wynik trzeba wstrzyknąć z powrotem zachowując tagi (`replace_visible_text()` z `subtitles/text.py` — JUŻ ISTNIEJE, `text.py:45`). **Rozstrzygam:** `displayed` NIE dostaje osobnego value-objectu w etapie 4. Etap 4 tłumaczy listę stringów (visible_text zdarzeń displayed) i zwraca listę przetłumaczonych stringów w tej samej kolejności; **wstrzyknięcie z powrotem do `SSAFile` przez `replace_visible_text` to etap 7 (composition)**. Etap 4 dostarcza dane, etap 7 układa. To trzyma granicę czysto (§8).

### 3.3 Kontener wyniku dla całego pliku: `TranslationResult` / `FileTranslation`

Fasada zwraca strukturę na cały plik:

```python
@dataclass(slots=True)
class FileTranslation:
    """Result of translating one file's spoken + displayed streams."""
    spoken: tuple[TranslatedLine, ...]       # przetłumaczone linie lektora
    displayed: tuple[str, ...]               # przetłumaczone visible-texty zdarzeń displayed (kolejność = kolejność displayed events)
    engine_id: str                           # który silnik faktycznie użyty (po fallbacku)
    target_lang: str
    unique_lines: int                        # ile unikalnych po dedupie (raport)
    total_lines: int                         # ile wszystkich (raport)
    api_calls: int                           # ile wywołań translate_batch fasady (max 2: spoken+displayed); pokazuje że dedup zadziałał (unique<total). Realna liczba HTTP jest wewnątrz silnika (batch_size) — nie liczona w etapie 4 (YAGNI)
    failed_lines: int                        # ile linii padło (ok=False)
    error: str | None = None                 # ustawiony tylko przy twardej porażce całego pliku (łańcuch wyczerpany)
```

`error is None` = sukces (może częściowy, patrz `failed_lines`). `error is not None` = plik `failed`, runner puszcza resztę (R12).

---

## 4. Rejestr silników (R2, N4) — kanon, bez odstępstw

Wg `engine-factory-standard.md` kropka w kropkę. `TranslationEngineId = Literal["google", "deepl", "llm"]`. `_REGISTRY` = SSOT. `available_engine_ids()` + `create_engine()`. Guard: pusty → `TranslationConfigError`; nieznany → `TranslationConfigError` z `", ".join(sorted(_REGISTRY))`; **trzeci guard**: `engine_id == "llm"` → `TranslationConfigError` (llm wymaga wstrzykniętego completera, budowany wprost — wzorzec MangaShift `engines/__init__.py:72`). Lazy `importlib`. Logger + `logger.debug` po konstrukcji (kanon każe, MangaShift dziś nie ma — ULEPSZAMY).

**Sygnatura konstrukcji (odstępstwo WYMUSZONE translation, z tabeli factory-standard):** `create_engine(config, *, secret_provider=None)`, konstrukcja `engine_cls(config, secret_provider=secret_provider)`. `secret_provider` to zastrzyk źródła klucza z composition root (BYOK). **Rozstrzygam dla AniShift:** AniShift nie ma `SecretsStore` (to MangaShift-ism, UI store kluczy). AniShift czyta klucze z `Settings` (pydantic-settings, `.env`). Więc `SecretProvider` w AniShift = cienki Protocol z jedną metodą `get_key(provider) -> str | None`, a jego implementacja czyta z `Settings`. Ale **prościej (KISS):** silnik `deepl` może dostać klucz wprost przez swój `config.api_key` (wypełniany z `Settings.deepl_api_key` w composition root — runnerze). Rozstrzygam **wariant prostszy**: brak `SecretProvider` w ogóle. `create_engine(config)` bez dodatkowego param; klucz DeepL wstrzykiwany do `DeeplConfig.api_key` przy budowie configu w runnerze/fasadzie. Uzasadnienie: AniShift ma jedno źródło klucza (`.env`→`Settings`), nie ma UI-store z BYOK, więc cała warstwa `SecretProvider` to niepotrzebna abstrakcja (skill simple krok 2: usuń część). Silnik `google` nie potrzebuje klucza (`is_available` = zawsze True). Silnik `llm` dostaje completer wprost (etap 5).

**SSOT — jedno miejsce listy silników:** `_REGISTRY` w `engines/__init__.py`. Panel `/settings`, walidacja, pipeline — WSZYSTKO derywuje z `available_engine_ids()`. Dodanie silnika = nowy podfolder + jeden wpis. Zero powtórzeń listy (dziś `settings_panel.py:33` ma statyczną kopię — etap 4 ją LIKWIDUJE, panel czyta rejestr).

---

## 5. Obsługa wieloliniowych napisów per silnik (R6a) — ⚠️ PROSTOWANIE + rozstrzygnięcie

### 5.1 Kluczowe prostowanie na podstawie realnego kodu

Wymagania R6a mówią o sklejaniu `\n` w spoken. ALE: **`SpokenLine.text` NIE MA `\n`** (§1.1 — `visible_text` collapse'uje whitespace). Więc dla **spoken** problem sklejania `\n` **nie istnieje** — spoken to już jedna linia. R6a w pełni dotyczy tylko **displayed** (zdarzenia ASS zachowują `\N`).

⚠️ To jest realna niespójność między wymaganiami (pisanymi zanim etap 3 był skończony, na modelu SRT) a kodem. **Prostuję:** strategia per-silnik dotyczy głównie **displayed**. Ale zostawiam mechanizm ogólny, bo:
- displayed zdarzenia mają `\N` (ASS newline), które `visible_text` zamienia na spację — więc jeśli tłumaczymy `visible_text(displayed_event)`, to też dostajemy jedną linię. **Chyba że** chcemy zachować oryginalny podział displayed. Tu jest sedno: dla displayed CHCEMY czytelnego podziału na ekranie.

### 5.2 Rozstrzygnięcie strategii per silnik (jak w Protocolu)

Cała mechanika `\n` w MangaShift (`_batching.py`) używa `NEWLINE_MARKER` (zero-width) do ochrony `\n` WEWNĄTRZ linii przy joinie batcha. Test na żywo (wymagania) pokazał: **Google psuje kontekst przy surowym `\n`, DeepL nie**. Więc:

**🏗️→✔ Jak wyrazić „sklejanie per silnik" w Protocolu:** silnik dostaje **czyste jednoliniowe teksty** (bo spoken i tak jest jednoliniowy, a displayed przepuszczamy przez `visible_text` przed tłumaczeniem — dostajemy jednoliniowy string). Silnik zwraca jednoliniowy przetłumaczony string. **Re-podział na wersy robi DOMENA po tłumaczeniu** (R6b, wspólny algorytm), NIE silnik. To eliminuje potrzebę per-silnik strategii `\n` na poziomie Protocolu — Protocol jest prosty:

```python
def translate_batch(self, texts: list[str], *, source_lang: str, target_lang: str) -> list[BatchedLine]: ...
```

gdzie `texts` to jednoliniowe stringi. Silnik Google wewnętrznie joinuje batch separatorem (zero-width, MangaShift `_batching.py`) i re-splituje; DeepL używa natywnego batcha listą. **To co MangaShift już robi.** Różnica per-silnik (join separatorem vs lista) żyje WEWNĄTRZ silnika (`google/_batching.py` vs `deepl/service.py`), nie w Protocolu. ✔ To jest odpowiedź na „jak wyrazić w Protocolu" — **nie wyrażamy, bo Protocol dostaje jednoliniowe teksty, a różnica batchowania to szczegół implementacji silnika.**

**Markery `\n`→`◍◍◍◍` ODRZUCONE dla Google** (R6a, test): potwierdzam — MangaShift `_batching.py` używa zero-width `NEWLINE_MARKER` tylko dlatego, że MangaShift tłumaczy manga-linie które MOGĄ mieć `\n`. AniShift daje jednoliniowe teksty, więc `NEWLINE_MARKER` w praktyce nie ma czego chronić (brak `\n` w input). Zostawiam mechanizm w skopiowanym `_batching.py` (działa, nie szkodzi, przy jednoliniowym input jest no-op), ale to nie jest ścieżka markerowa z mm_avh (` ◍◍◍◍ `) — to zero-width, którego test NIE odrzucił (odrzucił widoczne markery dla Google). ✔

---

## 6. Re-podział na wersy (R6b) — WŁASNY algorytm — 🏗️→✔ ROZSTRZYGNIĘTE

### 6.1 Kogo dotyczy

- **`displayed`** (widz czyta na ekranie) — TAK, kluczowe. Po tłumaczeniu displayed to jedna linia; trzeba ją rozbić na czytelne wersy (max 2 linie, ~42 znaki).
- **`spoken`** (lektor) — 🏗️→✔ **NIE dzielimy dla TTS**. Lektor czyta ciągiem (A6: „lektor czyta ciągiem"). `TranslatedLine.text` (jedna linia) idzie do TTS. `TranslatedLine.lines` dla spoken = `(text,)`. Uzasadnienie: podział wersów spoken nie ma odbiorcy (TTS ignoruje łamanie), więc to martwa robota (skill simple: nie rób czego nikt nie konsumuje). ALE liczę `lines` też dla spoken „na wszelki wypadek" — NIE, kasuję to, YAGNI. Dla spoken `lines=(text,)`.
- Wyjątek: gdy przetłumaczona linia przekracza twardy limit silnika/czytelności — dzielimy nawet spoken? Nie — dla spoken nie ma limitu wersów (TTS przyjmie długi string). Limit znaków silnika (R5a) dotyczy REQUESTU do API, nie długości pojedynczej linii wyniku. Więc spoken = jedna linia zawsze.

### 6.2 Gdzie umieścić chunker / linebreak — 🏗️→✔ ROZSTRZYGNIĘTE

Wymagania dają dwa kandydaty: `utils/text_chunker.py` (uniwersalne) albo `translation/linebreak.py` (blisko konsumenta). **Rozstrzygam: `anishift/services/translation/linebreak.py`** dla re-podziału linii (R6b) oraz **`anishift/services/translation/chunking.py`** dla txt-chunkingu po znakach (R6, mini-ficzer).

Uzasadnienie:
- `utils/` jest **nietykalny** (1:1 z mm_avh, CLAUDE.md). Nie wolno tam wrzucać nowego kodu poza „nowe pliki obok" — ale `text_chunker` to nie utility mm_avh, to nowy byt. Wrzucenie do `utils/` łamałoby zasadę „utils nietykalne = tylko to co jest w mm_avh 1:1". Więc utils odpada.
- Re-podział linii jest konsumowany WYŁĄCZNIE przez tłumaczenie (displayed) — nikt inny go nie woła. Umieszczenie blisko konsumenta (`translation/`) = wysoka spójność, niskie sprzężenie (GRASP). Gdyby w przyszłości TTS/composition go potrzebował, przeniesienie to trywialny ruch.
- **Rozdzielam dwa narzędzia** bo to dwa różne zadania: (a) `chunking.py` = tekst txt → chunki po ZNAKACH na granicach zdań/fraz (LatinPunctuator z `text_chunker.py`, R6, mini-ficzer txt→SRT); (b) `linebreak.py` = jedna przetłumaczona linia → wersy po ZNAKACH z hierarchią interpunkcja→spójnik→środek (R6b, własny algorytm). Choć oba tną tekst, mają różne wejścia/wyjścia i różne reguły (chunking nie ma limitu 2 wersów ani reguły sierot; linebreak ma). Łączenie ich to fałszywe DRY (skill simple).

### 6.3 Algorytm linebreak (R6b) — pełna specyfikacja

**Wejście:** jedna przetłumaczona linia (string), `max_chars` (~42, konfigurowalny), `max_lines=2`.
**Wyjście:** `tuple[str, ...]` wersów (1 lub 2, wyjątkowo więcej jeśli tekst monstrualny).
**NIE odtwarzamy oryginalnego układu** (niemożliwe — składnia PL się zmienia). Tworzymy NOWY czytelny podział.

Hierarchia punktów cięcia (od najlepszego), idea `split_at_half` z `srt_equalizer_reference.py:153` (rekurencja, najbliżej środka + bonus):
1. **mocna interpunkcja**: `. ! ? … :` (po znaku, przed spacją)
2. **słaba interpunkcja**: `, ; —` (pauza dialogowa i średnik — których `srt_equalizer` NIE ma, dlatego własny)
3. **spójnik/przyimek** (przed słowem): `i, oraz, ale, że, więc, bo, aby, lub, a, oraz, czy, gdy, jak, kiedy` (rozszerzalna lista)
4. **najbliżej środka na granicy słowa** (fallback, idea `split_at_half`)

Reguły ochronne:
- limit `~42` znaki/wers (konfigurowalny w `/settings`)
- max 2 wersy (jeśli po podziale wers wciąż > limit i to displayed — dopuszczamy 3, ale sygnalizujemy; realnie napisy rzadko tego wymagają)
- **bez sierot**: żaden wers nie może być pojedynczym słowem (jeśli podział rodzi sierotę — cofnij, wybierz gorszy punkt)
- **nie tnij zrostów**: przyimek + rzeczownik (`w domu`, `na stole`), przymiotnik przed rzeczownikiem — nie rozdzielaj (punkt cięcia przed przyimkiem, nie po)
- **fallback**: gdy fragment > limit i brak dobrego punktu → `split_greedy` (na spacjach, wzorzec `srt_equalizer_reference.py:134`)

Zero zależności, ~40-60 linii. `srt_equalizer` (MIT) tylko jako referencja do podejrzenia idei `split_at_half` — NIE instalujemy (mamy czysty tekst, nie pliki SRT).

**Wejściowa baza:** `LatinPunctuator.getPhrases()` z `text_chunker.py` już tnie po `[,;:]`, ` - `, `—` — to daje punkty 1-2 za darmo. Punkt 3 (spójniki) i reguły ochronne dopisuję. Punkt 4 (środek) z `split_at_half`.

---

## 7. Retry, backoff, fallback (R8, R9) — 🏗️→✔ + ⚠️ prostowanie

### 7.1 Dwa systemy retry (R8)

- **System 1 (google, deepl):** retry z backoff na `429/503/5xx`/rate-limit. Bez „dogadywania".
- **System 2 (llm):** numeracja + walidacja liczby + retry z dogadywaniem + shrink-do-1. Realizacja etap 5.

### 7.2 ⚠️ Brak `build_retry` w AniShift — rozstrzygnięcie

MangaShift silniki używają `mangashift.utils._retry.build_retry` (tenacity, async). AniShift **nie ma** tego pliku, `utils/` jest nietykalny, `tenacity` **nie jest** zależnością. **Rozstrzygam: własny mały helper retry w domenie translation** — `anishift/services/translation/_retry.py`, sync, ~30 linii, bez tenacity. Wzorzec: pętla z `time.sleep` + backoff (linear/exponential), łapie precyzyjnie podany typ wyjątku (`TransientError`/rate-limit). Uzasadnienie: (a) nie dodaję zależności `tenacity` dla 30 linii (YAGNI), (b) sync = prostszy (AniShift nie ma event loopu poza silnikiem google), (c) extraction już robi backoff ręcznie w pętli — spójne. To NIE jest w `utils/` (nietykalny), tylko w domenie.

### 7.3 Fallback = cały plik od nowa (R9) ✅

Silnik pada (wyczerpany retry / quota / niedostępny) → **cały plik od nowa następnym DOSTĘPNYM silnikiem z łańcucha**. Bez sklejania połówek (unika zgrzytu jakości). Łańcuch pusty/wyczerpany → `FileTranslation.error` ustawiony, plik `failed`, reszta plików leci. Fallback żyje w FASADZIE (`TranslationService`), nie w silniku — fasada iteruje łańcuch `[engine_id, *fallback_chain]`, filtruje przez `is_available`, próbuje po kolei.

### 7.4 Priorytet ponowień (R8b) ✅

Najwcześniejsze batche w najwcześniejszym pliku pierwsze. Pliki i tak sekwencyjnie (R7), więc priorytet plików załatwiony. Batche w pliku równolegle (semaphore) — przy retry, najwcześniejszy batch ma priorytet (składamy wyniki w kolejności indeksów, więc naturalnie zachowane).

---

## 8. Równoległość (R7) ✅ + granica etap4/etap7 — 🏗️→✔

### 8.1 Równoległość

- **Pliki: sekwencyjnie** (natsorted). ⚠️ Uwaga: dziś runner auto-mode robi pliki RÓWNOLEGLE (ThreadPoolExecutor, `runner.py:99`). Ale to dla EKSTRAKCJI (I/O-bound, dysk). Dla tłumaczenia (API rate-limit) pliki muszą iść sekwencyjnie, żeby nie mnożyć rate-limitu × liczba plików. **Rozstrzygam:** krok `translate` w `_process_mkv` jest wywoływany W ramach przetwarzania jednego pliku; jeśli runner puszcza pliki równolegle, to każdy wątek robi swój `translate` — to ZWIELOKROTNIA obciążenie API. Więc: **tłumaczenie wewnątrz `_process_mkv` samo w sobie nie zrównolegla plików** (bo jest per-plik), ale musi mieć własny wewnętrzny limit współbieżności batchy, a runner… Problem: auto-mode równolegli pliki. Rozstrzygnięcie w planie: krok translate w `_process_mkv` używa **jednego event loopu na plik** (dla google async) i semaphore na batche W TYM pliku. Przy równoległych plikach to nadal ryzyko rate-limitu. **Bezpieczne rozstrzygnięcie:** ustawić konserwatywny domyślny concurrency (np. 3-5 batchy) i konserwatywny worker_count — LUB (lepiej) dodać flagę, że pliki z tłumaczeniem idą sekwencyjnie. Rozstrzygam: **etap 4 trzyma concurrency batchy niskie i konfigurowalne; kwestię „pliki równolegle vs sekwencyjnie przy tłumaczeniu" oznaczam jako świadome ryzyko** — domyślnie zostawiam istniejącą równoległość plików runnera, ale z NISKIM concurrency batchy per plik (semaphore=3), bo realny throughput API i tak ogranicza. Skrypt obciążeniowy (Tropy) zmierzy optimum.
- **Batche w pliku: równolegle**, semaphore = `translation_concurrency` (konserwatywny, konfigurowalny). Google async natywnie; deepl sync przez… — patrz niżej.
- **Google async→sync:** MangaShift google jest async (googletrans 4.x async). AniShift = sync fasada. **Jeden event loop na plik** (nie `asyncio.run` per batch — mm_avh robił to źle, `translator.py:141`). Rozstrzygam: silnik google trzyma jednoliniowe teksty, fasada woła silnik przez `asyncio.run(engine.translate_all(...))` RAZ na plik, wewnątrz silnika `asyncio.gather` z semaphore po batchach. To jest „jeden event loop na plik".
- **DeepL sync:** deepl SDK jest sync. Batche równolegle przez `ThreadPoolExecutor` (semaphore) LUB sekwencyjnie. Rozstrzygam: deepl batche sekwencyjnie w pierwszej wersji (deepl SDK bierze listę = jeden request na batch, a batche i tak są duże) — prostsze, deepl rate-limit łagodniejszy. Concurrency deepl konfigurowalny, default 1-2.

### 8.2 Granica etap 4 / etap 7 — 🏗️→✔ ROZSTRZYGNIĘTE

**Etap 4 PRODUKUJE:**
- `spoken: tuple[TranslatedLine, ...]` — przetłumaczone linie lektora (w pamięci, do TTS w etapie 6)
- `displayed: tuple[str, ...]` — przetłumaczone visible-texty zdarzeń displayed, w kolejności zdarzeń displayed

**Etap 7 (composition) UKŁADA:**
- wstrzyknięcie `displayed` z powrotem do `SSAFile` przez `replace_visible_text` (zachowanie tagów) + re-podział na wersy przy wstrzyknięciu
- produkcja wariantów (całościowy / lektorski / spoken) jako pliki/ścieżki MKV
- nazewnictwo (`{stem}.pelny.pl.ass` / `--track-name`), muxowanie, wybór formatu (ASS/SRT), default-track

⚠️ **Napięcie:** re-podział displayed na wersy (R6b) to etap 4 (produkuje `lines`) czy etap 7 (przy wstrzyknięciu)? **Rozstrzygam:** etap 4 produkuje `displayed` jako przetłumaczone stringi JEDNOLINIOWE (surowy wynik tłumaczenia) ORAZ udostępnia funkcję `linebreak` (w `translation/linebreak.py`) jako publiczne narzędzie domeny. Faktyczny re-podział displayed przy zapisie do ASS robi etap 7, wołając `linebreak`. Dla spoken re-podział nie jest potrzebny (§6.1). To trzyma etap 4 = „dane + narzędzie", etap 7 = „układanie". Alternatywa (etap 4 od razu dzieli displayed) też jest OK, ale wtedy etap 4 musiałby znać `max_chars` displayed (ustawienie eksportu) — a to sprawa etapu 7. Więc **linebreak jako narzędzie, wywołanie w etapie 7**. ✔

**Co etap 4 wypuszcza z runnera:** `_process_mkv` po kroku `translate` trzyma `FileTranslation` i zapisuje do `FileOutcome` liczby raportu (spoken przetłumaczone, api_calls, failed). `spoken` NIE ląduje na dysk (✅ wymaganie). `displayed` przetłumaczony — w etapie 4 jeszcze NIE zapisujemy przetłumaczonego pliku displayed (to robi etap 7); etap 4 może opcjonalnie nadpisać `<stem>.displayed.<kind>` przetłumaczoną wersją dla widoczności/smoke, ale to należy do granicy — **rozstrzygam: etap 4 NIE zapisuje przetłumaczonego displayed na dysk** (to etap 7), trzyma w pamięci / w `FileTranslation`. Dla smoke-testu (DoD) etap 4 może mieć tryb debug zapisujący przetłumaczony ASS, ale nie w produkcyjnej ścieżce.

⚠️ **Problem przepływu:** `FileTranslation.spoken` żyje w pamięci `_process_mkv` i… ginie po zwrocie `FileOutcome` (bo etapy 6/7 jeszcze nie istnieją). To jest OK dla etapu 4 — etap 4 udowadnia że tłumaczenie działa (raport + smoke), a konsumpcja `spoken`/`displayed` przyjdzie z etapami 6/7. **Ale** trzeba gdzieś te dane zaparkować lub przynajmniej nie gubić kontraktu. Rozstrzygam: `FileOutcome` dostaje pole `translation: FileTranslation | None = None` — outcome niesie wynik tłumaczenia dalej. Etapy 6/7 go skonsumują. Etap 4 raportuje z niego liczby.

---

## 9. Ustawienia `/settings` (R sekcja 4) — 🏗️→✔ kształt pól

**Rozstrzygam: pola PŁASKIE na `UserSettings`** (nie zagnieżdżone per-silnik), z per-silnik defaultami trzymanymi jako STAŁE w kodzie silnika/domeny (SSOT limitów tam gdzie silnik). Uzasadnienie: `UserSettings` jest `@dataclass(slots=True)` serializowany do płaskiego JSON przez `asdict`; zagnieżdżone dict per-silnik komplikowałyby walidację `_clean_*` (dziś płaska). Płaskie pola + walidacja wzorem `_clean_string`/`_clean_number`. Batch/concurrency per-silnik: rozstrzygam **jedno pole `translation_batch_size` i `translation_concurrency` wspólne** w v1 (bo user i tak wybiera jeden silnik naraz), a per-silnik DEFAULT (gdy pole nie ustawione lub =0 = „auto") bierze się ze stałej silnika. To upraszcza panel (mniej pól) i trzyma SSOT limitów w silniku. Gdyby user chciał per-silnik — łatwo dodać później (YAGNI).

Pola dodane do `UserSettings`:

| pole | typ | default | walidacja | uwaga |
|---|---|---|---|---|
| `translation_engine` | `str` | `"google"` | ∈ `available_engine_ids()` | JUŻ istnieje |
| `translation_fallback_chain` | `list[str]` | `["google"]` | każdy ∈ engine_ids | ⚠️ list w dataclass — patrz niżej |
| `translation_batch_size` | `int` | `0` (=auto→stała silnika) | `>= 0`, `<= 500` | 0 = default silnika |
| `translation_concurrency` | `int` | `3` | `1..16` | semaphore batchy |
| `translation_max_retries` | `int` | `3` | `0..10` | limit ponowień/batch |
| `target_lang` | `str` | `"pl"` | niepusty string | język docelowy |
| `llm_model` | `str` | `""` | (etap 5) | provider_model_id |
| `llm_temperature` | `float` | `0.3` | `0.0..2.0` | (etap 5) |
| `llm_top_p` | `float` | `1.0` | `0.0..1.0` | (etap 5) |
| `llm_max_output_tokens` | `int` | `0` (=auto) | `0..32000` | (etap 5) |

⚠️ **`translation_fallback_chain: list[str]`** — `asdict`/`json` serializuje listę OK, ale `_clean_*` nie obsługuje list. Rozstrzygam: dodać `_clean_str_list(raw, key, allowed)` — waliduje że to lista stringów z dozwolonego zbioru, inaczej fallback do `["google"]`. Wzorzec spójny z istniejącymi `_clean_*`.

⚠️ **Panel `settings_panel.py` a fallback_chain/llm params** — panel dziś edytuje proste pola (cykl wartości strzałkami). Lista fallback i parametry LLM to bardziej złożony UI. Rozstrzygam: w etapie 4 panel derywuje `translation_engine` z `available_engine_ids()` (likwidacja placeholdera) i dodaje proste pola (`translation_concurrency`, `translation_max_retries`, `target_lang` jako cykl/liczba). `translation_fallback_chain` i parametry LLM edytowalne przez ręczną edycję `settings.json` (plik jest hand-editable — user_settings docstring to mówi) w v1; pełny UI listy fallback = późniejszy refaktor panelu (session-log user planuje refaktor UI). To jest KISS — nie budujemy multi-select UI w etapie 4. Parametry LLM w panelu przychodzą z etapem 5 (gdy jest realny wybór providera/modelu).

---

## 10. Silniki (R11) — rozstrzygnięcia

- **`google`** — googletrans 4.x, async→sync (jeden event loop na plik), darmowy, `is_available` = zawsze True. Kopia MangaShift `engines/google/` + `_batching.py`. Retry przez własny `_retry`. **Ulepszenie:** MangaShift google jest „sequential by design (no gather)" — ale AniShift chce batche równolegle z semaphore. Rozstrzygam: zachowuję sekwencyjność w OBRĘBIE mechanizmu batchowania MangaShift (bezpieczne dla rate-limitu Google), ale fasada może puścić kilka batchy przez gather+semaphore jeśli concurrency>1. Konserwatywny default. Faktycznie: Google jest najbardziej rate-limit-wrażliwy, więc default concurrency dla google = 1-2 (stała silnika), mimo globalnego defaultu 3.
- **`deepl`** — oficjalne API (`deepl` 1.30.0), klucz z `Settings.deepl_api_key` wstrzyknięty do `DeeplConfig.api_key`. Batch natywny (lista). `is_available` = `bool(api_key)`. `QuotaExceededException` → `TranslationQuotaError` → sygnał fallbacku. Kopia MangaShift `engines/deepl/` (bez `secret_provider` — klucz wprost w configu). ⚠️ MangaShift deepl czyta klucz z `os.getenv` lub secret_provider; AniShift czyta z `Settings` — rozstrzygam: `DeeplConfig.api_key: str` wypełniany w composition root (fasada/runner) z `context.settings.deepl_api_key`. Silnik nie sięga do env sam. DeepL desktop (pyautogui) = MARTWY, nie portuję (✅).
- **`llm`** — cienki adapter → fasada `services/llm` (etap 5). W rejestrze od teraz. `create_engine` dla llm rzuca (wymaga wstrzykniętego completera). Szkielet: `engines/llm/` z `service.py` (LlmTranslateService implementujący Protocol, ale z completerem wstrzykniętym), `config.py`, `constants.py` (system prompt z numeracją `[N]`), `types.py`. **Format: numeracja `[N] tekst`** (✅ decyzja usera, NIE JSON — ⚠️ MangaShift llm używa JSON! Muszę PRZEPISAĆ silnik llm na numerację, nie kopiować 1:1). Realizacja/test etap 5. Etap 4 dostarcza szkielet + prompt + parser numeracji + walidację (opisane, nie w pełni przetestowane bo brak modułu llm).

---

## 11. Dedup (R4, N2) — wspólny, deterministyczny

Linia powtórzona N razy tłumaczy się 1×, mapowanie z powrotem przez `dict.fromkeys` (zachowuje kolejność = determinizm N2). Wspólne dla WSZYSTKICH silników — silnik nigdy nie deduplikuje sam. Logika z mm_avh `translator.py:161-170` (dedup przez `dict.fromkeys`, `translation_map`, fill z powrotem). Umiejscowienie: `anishift/services/translation/dedup.py` (czyste funkcje: `deduplicate(lines) -> (unique, index_map)`, `redistribute(unique_translations, index_map) -> full_list`). Testowalne bez sieci (N7).

**Dedup działa na jednoliniowych tekstach** (spoken.text i visible_text(displayed)). Spoken i displayed dedupują się **osobno** (różne tory) LUB razem? Rozstrzygam: **osobno** — spoken i displayed to różne listy, dedupujemy każdą osobno (prościej, granice czyste). Choć wspólny dedup dałby minimalnie lepszy zysk (linia w spoken i displayed identyczna), komplikacja mapowania z powrotem na dwa tory nie warta (skill simple).

---

## 12. Mini-ficzer txt→SRT (R6, §8) — 🏗️→✔ jak spiąć

Etap 3 ma `txt_to_spoken()` (`subtitles/txt.py`) — czyta txt, tnie na `SpokenLine` po zdaniach/słowach (max 750 znaków), timing 0. Discovery `.txt` już w runnerze (`_process_txt`, `runner.py:230`).

**Rozstrzygam:** mini-ficzer = ścieżka txt w runnerze dostaje krok translate. `_process_txt` dziś tylko liczy `txt_to_spoken`. Po etapie 4: `txt_to_spoken` → dedup → translate → (opcjonalnie zapis SRT). Chunker po ZNAKACH (`chunking.py`, sentence_length=750, chunk_limit=250) to alternatywna ścieżka cięcia txt — ⚠️ ale `txt_to_spoken` już tnie txt (po zdaniach, max_chars=750). Nie duplikujmy. Rozstrzygam: `txt_to_spoken` zostaje jako źródło linii z txt (już działa), `chunking.py` (LatinPunctuator) używam TYLKO jeśli potrzebne finezyjniejsze cięcie po frazach — w praktyce `txt_to_spoken` wystarcza. **Prostuję wymaganie R6:** chunker po znakach z `text_chunker.py` jest nadmiarowy wobec istniejącego `txt_to_spoken` dla ścieżki txt. Zachowuję `chunking.py` jako narzędzie (przepisany `text_chunker`) dostępne, ale ścieżka txt→SRT używa istniejącego `txt_to_spoken`. Domyślne `sentence_length=750` już jest w `txt.py` (`_MAX_CHUNK_CHARS=750`). SRT z txt: po tłumaczeniu linie txt (timing 0) → zapis jako SRT z sekwencyjnymi timingami (mini-ficzer). To granica z etapem 7, ale prosty przypadek — rozstrzygam: mini-ficzer txt→SRT dostaje minimalny zapis SRT w etapie 4 (bo txt nie idzie przez MKV merge). Zapis SRT: liczba linii = liczba przetłumaczonych, timingi syntetyczne (proporcjonalne do długości, jak `srt_equalizer` split_subtitle) lub sekwencyjne stałe. Prosty wariant: stałe okna.

⚠️ To jest najbardziej „mętny" obszar wymagań. Trzymam go MINIMALNY: txt→tłumaczenie→SRT jako prosty przypadek, `chunking.py` istnieje ale ścieżka główna używa `txt_to_spoken`. Nie rozbudowuję.

---

## 13. Edge case'y — potwierdzenie

| # | Sytuacja | Zachowanie | Realizacja |
|---|---|---|---|
| E1 | `already_polish` | Pomiń translate | Guard w `_process_mkv` przed krokiem translate |
| E2 | Zero spoken | Nic do tłumaczenia, dalej | `if not spoken and not displayed: return` w fasadzie |
| E3 | DeepL bez klucza | `is_available`=False, znika z panelu; wymuszenie=`TranslationAuthError` | `DeeplConfig.api_key` pusty |
| E4 | DeepL quota | `QuotaExceededException`→`TranslationQuotaError`→fallback | mapowanie w `deepl/service.py` |
| E5 | Google 429/503 | Retry backoff→po wyczerpaniu fallback | `_retry` + fasada |
| E6 | Rozjazd liczby linii | Retry (batch→per-line ladder, MangaShift `_batching`) | `_batching.py` ladder |
| E7 | Brak sieci | Błąd domenowy, retry, fallback/failed | łapać `httpx`/`OSError` precyzyjnie |
| E8 | Linia > limit znaków | Batch respektuje limit (R5a); pojedyncza linia > limit rzadka — chunkujemy przed wysłaniem | `_chunks` w batchingu |
| E9 | Ctrl+C | Przerywa czysto | `cancel: threading.Event` propagowany do fasady; sprawdzać między batchami |
| E10 | 2+ pliki, jeden pada | Reszta leci | `_process_mkv` łapie, zwraca failed outcome |
| E11 | Wszystkie silniki niedostępne | Plik failed, „brak dostępnego silnika" | fasada iteruje łańcuch, pusty→error |

⚠️ **E9 Ctrl+C w fasadzie** — dziś `cancel` propaguje do `extract_tracks`. Tłumaczenie musi też przyjąć `cancel: threading.Event` i sprawdzać go między batchami (i przerywać event loop google). Rozstrzygam: fasada `translate` przyjmuje opcjonalny `cancel`, sprawdza przed każdym batchem, rzuca `TranslationError(code=CANCELLED)` — spójne z extraction.

---

## 14. Definition of Done (uzupełniony)

Bazowy DoD z wymagań + moje uzupełnienia:
- [ ] Krok `translate` w `_process_mkv` po `write`; `StepName` += `"translate"`; `FileOutcome` += `translation`
- [ ] Rejestr `engines/__init__.py` wg kanonu; smoke: nieznany id=`TranslationConfigError` z posortowaną listą; `llm` guard
- [ ] Import rejestru NIE importuje googletrans/deepl (test lazy)
- [ ] Dedup: 1000 identycznych linii=1 wywołanie; mapowanie deterministyczne
- [ ] Fasada sync, cache silnika per engine_id, zero `if engine_id==`
- [ ] Google async→sync, jeden event loop na plik
- [ ] DeepL: bez klucza `is_available`=False; z kluczem tłumaczy; quota→fallback
- [ ] Fallback: silnik pada→cały plik następnym; łańcuch pusty→failed, reszta leci
- [ ] Retry backoff na 429/503; limit konfigurowalny; własny `_retry` (bez tenacity)
- [ ] `linebreak.py`: hierarchia interpunkcja→spójnik→środek, limit ~42, max 2 wersy, bez sierot, nie tnij zrostów; test na realnych PL zdaniach
- [ ] `TranslatedLine` (frozen), źródło `SpokenLine` nietknięte
- [ ] Tłumaczymy spoken ORAZ displayed (displayed jako lista stringów, wstrzyknięcie=etap7)
- [ ] `already_polish`→pomija; zero spoken→dalej
- [ ] Ctrl+C przerywa czysto; błąd jednego pliku nie ubija reszty
- [ ] Zero `input()`/`sys.exit()` w serwisie; nie blind `except Exception`
- [ ] Parametry `/settings` przeżywają restart; panel derywuje silniki z rejestru (likwidacja placeholdera)
- [ ] Mini-ficzer txt→SRT działa
- [ ] Smoke na realnym pliku z datasetu → przetłumaczone spoken+displayed, ta sama liczba linii, timingi nietknięte
- [ ] LLM: szkielet+rejestr+prompt numeracji+parser+walidacja opisane (realizacja etap 5)
- [ ] Bramki: ruff + format + mypy + pytest zielone

---

## 15. Rozstrzygnięcia wszystkich 🏗️ (podsumowanie)

| 🏗️ z wymagań | Rozstrzygnięcie |
|---|---|
| Typ wyniku `TranslatedLine` | `frozen` dataclass: start/end/source_text/text/lines/style/ok (§3.1) |
| Granica etap4/etap7 | etap4=dane (spoken TranslatedLine + displayed stringi) + narzędzie linebreak; etap7=wstrzyknięcie+warianty+nazewnictwo (§8.2) |
| Sklejanie per silnik w Protocolu | Nie wyrażamy w Protocolu — silnik dostaje jednoliniowe teksty; różnica batchowania (join vs lista) wewnątrz silnika (§5.2) |
| Limit znaków jako atrybut silnika | Tak — stała `MAX_CHARS_PER_REQUEST` w `constants.py` silnika (SSOT limitu tam) (§4, §9) |
| Gdzie chunker/linebreak | `translation/linebreak.py` (re-podział) + `translation/chunking.py` (txt); NIE utils (nietykalny) (§6.2) |
| Batch per silnik vs globalny | Globalne pole `translation_batch_size` (0=auto→stała silnika); per-silnik default w silniku (§9) |
| Kształt pól /settings | Płaskie na `UserSettings`, walidacja `_clean_*` + nowy `_clean_str_list` (§9) |
| Czy spoken potrzebuje podziału | NIE — lektor czyta ciągiem; `lines=(text,)` dla spoken (§6.1) |
| Jak spiąć mini-ficzer z txt | `txt_to_spoken` (istnieje) → translate → zapis SRT; `chunking.py` jako narzędzie (§12) |
| E8 pojedyncza linia > limit | Chunkujemy przed wysłaniem (`_chunks`) (§13) |
| SecretProvider | USUNIĘTY (KISS) — klucz DeepL wprost w `DeeplConfig.api_key` z `Settings` (§4) |
| Kontekst sąsiednich linii LLM (A4) | Etap 5 — szkielet zostawia miejsce, ilość kontekstu do zmierzenia (§10) |
| LLM podział linii (A6) | Etap 5; w etapie 4 displayed dzieli wspólny `linebreak` (§6.1) |

---

## 16. Świadome odstępstwa od wymagań (z uzasadnieniem)

1. **R6a sklejanie spoken `\n`** — spoken NIE MA `\n` w AniShift (visible_text collapse'uje). Strategia per-silnik dotyczy głównie displayed; dla spoken to no-op. (§5.1)
2. **R6 chunker po znakach dla txt** — nadmiarowy wobec istniejącego `txt_to_spoken`; ścieżka txt używa istniejącego narzędzia, `chunking.py` zachowany jako opcja. (§12)
3. **`build_retry`/tenacity** — nie kopiujemy (utils nietykalny, tenacity nie jest zależnością); własny sync `_retry` w domenie. (§7.2)
4. **`SecretProvider`** — usunięty (AniShift ma jedno źródło klucza `.env`→Settings, brak UI-store BYOK). (§4)
5. **LLM JSON→numeracja** — MangaShift llm używa JSON; przepisujemy na numerację `[N]` (✅ decyzja usera). (§10)
6. **Panel fallback_chain/LLM params** — w etapie 4 tylko proste pola derywowane z rejestru; multi-select fallback + LLM params przez ręczną edycję JSON / etap 5. (§9)

Wszystko inne — zgodne z wymaganiami i ich duchem.

# etap 4 — tłumaczenie (pierwszy rejestr silników)

> cel: działa rejestr wg wzorca §E (engine-factory-standard) na mniejszej domenie: google + deepl, z dedupem i czyszczeniem znaczników.
> zależności: etap 3. logika z `mm_avh/modules/translator.py`.
> DoD: parytet wyników z dzisiejszym translatorem na pliku testowym; rejestr przechodzi smoke (nieznany engine_id = ConfigError z posortowaną listą dostępnych).

## pliki do stworzenia/zmiany

### `anishift/services/translation/__init__.py` (NOWY)
- **odpowiedzialność:** publiczny interfejs domeny tłumaczenia.
- **zawartość:** `__all__` + re-export fasady (`TranslationService`), configu, typów, błędów.

### `anishift/services/translation/errors.py` (NOWY)
- **odpowiedzialność:** błędy domenowe tłumaczenia.
- **zawartość:** `TranslationError` (podklasa `AnishiftError`), `TranslationConfigError` (dla guardów rejestru), `TranslationAuthError` (brak/zły klucz — czytelny komunikat zamiast tracebacka). liść — importuje tylko `anishift.errors`.
- **wzorzec z MangaShift:** `services/<domena>/errors.py` jako liść (engine-factory-standard, decyzja 6).

### `anishift/services/translation/config.py` (NOWY)
- **odpowiedzialność:** config domeny tłumaczenia.
- **zawartość:** `@dataclass(slots=True) TranslationConfig` — `engine_id: str` WYMAGANY bez defaultu (front/panel decyduje, serwis waliduje), język docelowy, batch size; walidacja w `__post_init__` z docstringiem. zero defaultu silnika w serwisie.
- **wzorzec z MangaShift:** domain-config z engine-standard ("serwer=wykonawca, front decyduje").

### `anishift/services/translation/constants.py` (NOWY)
- **odpowiedzialność:** stałe domeny.
- **zawartość:** `Final[...]` z docstringami: domyślny język docelowy (`pl`), limity batcha, format markera nowej linii. bez kluczy API, bez nazw silników (te żyją w rejestrze).

### `anishift/services/translation/protocols.py` (NOWY)
- **odpowiedzialność:** kontrakt silnika tłumaczenia.
- **zawartość:** `Protocol TranslationEngine`: `engine_id: str`, `is_available() -> bool`, `translate_batch(lines, source_lang, target_lang) -> list[str]`, `close()`. silnik dostaje CZYSTE linie (po dedupe i cleanup) — dedup i tagi to sprawa domeny, nie silnika.
- **wzorzec z MangaShift:** `protocols.py` z service-standard (u nas sync — świadome odstępstwo).

### `anishift/services/translation/types.py` (NOWY)
- **odpowiedzialność:** typy domeny.
- **zawartość:** dataclassy: request tłumaczenia pliku (ścieżka SRT, języki), raport wyniku (liczba linii, liczba unikalnych, liczba wywołań API, błędy per batch).

### `anishift/services/translation/dedup.py` (NOWY)
- **odpowiedzialność:** dedup unikalnych linii + marker nowej linii — zachowane 1:1 funkcjonalnie.
- **zawartość:** czyste funkcje: `deduplicate(lines)` (unikalne linie tłumaczone 1×, mapowanie z powrotem na wszystkie wystąpienia), wstawianie/przywracanie markera `\n` (marker generowany per run, sprawdzany na kolizję z tekstem), batchowanie, kontrola liczby odpowiedzi (rozjazd cardinality → mniejszy batch → pojedyncze linie, jak dziś). wspólne dla WSZYSTKICH silników (google/deepl/llm) — silnik nigdy nie deduplikuje sam.
- **skąd logika:** `modules/translator.py` (mm_avh) — dedup, markery, fallback batch→linie→pojedynczo.

### `anishift/services/translation/service.py` (NOWY)
- **odpowiedzialność:** fasada — przebieg tłumaczenia pliku SRT przez wybrany silnik.
- **zawartość:** `TranslationService` — trzyma config; `translate_srt(path, ...)`: wczytanie SRT (pysrt) → cleanup znaczników (z `subtitles/cleanup.py`) → dedup/markery/batch (z `dedup.py`) → `create_engine(config)` (cache instancji per engine_id) → `translate_batch` per batch → przywrócenie markerów i duplikatów → zapis SRT (te same timingi i liczba linii). ZERO `if engine_id == ...` — fasada nie zna żadnego konkretnego silnika. sync.
- **wzorzec z MangaShift:** fasada domeny z service-standard + engine-factory-standard (cache per engine_id).
- **skąd logika:** przebieg z `modules/translator.py`.

### `anishift/services/translation/engines/__init__.py` (NOWY)
- **odpowiedzialność:** rejestr silników tłumaczenia — JEDYNE źródło prawdy o zestawie silników.
- **zawartość:** dokładnie wg engine-factory-standard, kolejność sekcji: docstring → `from __future__` → importy (importlib top-level, `TranslationConfigError` top-level) → `__all__` (`["TranslationEngineId", "available_engine_ids", "create_engine"]`) → logger → `TYPE_CHECKING` → `TranslationEngineId = Literal["google", "deepl"]` (w etapie 5 dojdzie `"llm"`) → `_REGISTRY: Final[dict[TranslationEngineId, tuple[str, str, str]]]` (komentarz `# engine_id -> (module_path, service_class, config_ref)`) → `available_engine_ids()` → `create_engine(config)`.
  - guard: pusty `engine_id` → `TranslationConfigError("translation.engine_id is required")`; nieznany → `TranslationConfigError` z `", ".join(sorted(_REGISTRY))`.
  - lazy `importlib.import_module` — googletrans/deepl NIE importowane na starcie apki.
- **wzorzec z MangaShift:** kanoniczny szablon z `engine-factory-standard.md` (kopiuj kropka w kropkę, podmiana `mangashift.` → `anishift.`).

### `anishift/services/translation/engines/google/__init__.py`, `config.py`, `constants.py`, `service.py` (NOWE)
- **odpowiedzialność:** silnik `google` — googletrans v4.
- **zawartość:**
  - `__init__.py` — re-export `GoogleTranslationService` + `GoogleConfig`, `__all__`.
  - `config.py` — `@dataclass(slots=True) GoogleConfig` (limity batcha, timeouty), walidacja w `__post_init__`.
  - `constants.py` — `Final` stałe: limity znaków per request, mapowanie kodów języków.
  - `service.py` — implementacja Protocolu; googletrans jest async pod spodem → wrapper async→sync z JEDNYM event loopem na cały plik (nigdy `asyncio.run()` per linia); fallback batch → linie → pojedynczo (parytet z dziś); import googletrans wewnątrz metod (lazy).
- **wzorzec z MangaShift:** kształt pakietu silnika z engine-standard.
- **skąd logika:** tor google z `modules/translator.py`.

### `anishift/services/translation/engines/deepl/__init__.py`, `config.py`, `constants.py`, `service.py` (NOWE)
- **odpowiedzialność:** silnik `deepl` — oficjalne DeepL API.
- **zawartość:** analogicznie do google; `config.py` — klucz API wstrzykiwany z `Settings` (`.env`, `ANISHIFT_DEEPL_API_KEY`); `service.py` — jeden klient DeepL na run, `is_available()` = fałsz bez klucza (znika z panelu), brak klucza przy wymuszeniu = `TranslationAuthError` (nie traceback); import `deepl` lazy. DeepL desktop NIE wchodzi (martwy).
- **skąd logika:** tor deepl API z `modules/translator.py`.

### `anishift/pipeline/runner.py` (ZMIANA)
- **odpowiedzialność:** krok 3 — tłumaczenie.
- **zawartość:** po refaktorze: detekcja plików już po polsku → pominięcie tłumaczenia (jak dziś); pozostałe → `TranslationService.translate_srt()` z engine_id z ustawień panelu; progress przez rich_console.
- **skąd logika:** warunek pomijania z `modules/translator.py`/`mkv_processing.py`.

### `anishift/cli/settings_panel.py` (ZMIANA)
- **odpowiedzialność:** wybór silnika tłumaczenia derywowany z rejestru.
- **zawartość:** lista opcji silnika = `available_engine_ids()` filtrowana przez `is_available()` — koniec statycznej zaślepki z etapu 2.

## kolejność implementacji

1. szkielet domeny (`errors`, `config`, `constants`, `protocols`, `types`) → weryfikacja: importy przechodzą, `TranslationConfig` bez engine_id rzuca błąd.
2. `dedup.py` → weryfikacja: testy jednostkowe — 1000 identycznych linii = 1 pozycja; marker przeżywa round-trip; rozjazd cardinality odpala fallback.
3. rejestr `engines/__init__.py` → weryfikacja: smoke — nieznany id = ConfigError z posortowaną listą; import rejestru NIE importuje googletrans/deepl (test lazy-importu).
4. silnik `google` → weryfikacja: SRT angielski → polski, ta sama liczba linii i timingi.
5. silnik `deepl` → weryfikacja: jw. + bez klucza `is_available()` = False, wymuszenie = TranslationAuthError.
6. `service.py` fasada + krok 3 w runnerze + panel → weryfikacja: Enter-auto na obcym MKV robi extract → refactor → translate; polski MKV nie woła API.

## jak testować

SRT angielski → polski oboma silnikami; plik z 1000 powtórzeń tej samej linii tłumaczy 1 request; znaczniki ASS nie przechodzą do tłumaczenia; brak klucza deepl = czytelny błąd domenowy, nie traceback. parytet wyników z dzisiejszym translatorem na pliku testowym.

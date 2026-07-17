# etap 5 — serwis llm (trzeci rejestr): dostawcy, silnik tłumaczenia llm, korekta

> cel: ogólne narzędzie LLM w apce — 6 dostawców za jedną fasadą (recykling 1:1 z `mangashift/services/llm/`), podpięte jako trzeci silnik tłumaczenia i opcjonalna korekta napisów przed lektorem.
> zależności: etap 4 (rejestr translation musi istnieć, żeby wpiąć silnik `llm`). może iść równolegle z etapem 6.
> DoD: rejestr llm przechodzi ten sam smoke co translation (nieznany id = ConfigError z posortowaną listą); `llm` widoczny w panelu obok google/deepl z wyborem dostawcy+modelu; korekta default OFF; async klientów SDK nie wycieka ponad sync fasadę.

## zasada nadrzędna etapu

To NIE jest pisanie od nowa — to przenosiny sprawdzonego kodu MangaShift: kopiowanie plik po pliku z podmianą wyłącznie ścieżek importów `mangashift.` → `anishift.`. Pomijamy TYLKO pliki `_portable.py` (manifest zależności pod setup-wizard MangaShift — w AniShift zależności LLM to zwykłe zależności projektu). Jedyna adaptacja merytoryczna: fasada sync-first (async klienci SDK żyją wewnątrz silników).

## pliki do stworzenia/zmiany

### `anishift/services/llm/__init__.py` (NOWY — kopia 1:1)
- **odpowiedzialność:** publiczny interfejs domeny llm.
- **zawartość:** `__all__` + re-exporty jak w MangaShift.
- **wzorzec z MangaShift:** `mangashift/services/llm/__init__.py`.

### `anishift/services/llm/config.py` (NOWY — kopia 1:1)
- **odpowiedzialność:** config domeny llm.
- **zawartość:** `LlmConfig` — `engine_id` WYMAGANY + mapa `providers[engine_id] -> ProviderConfig` (klucz API, `base_url` dla openai_compatible, `provider_model_id`, limity); nieużywany dostawca nie musi być skonfigurowany. `ProviderConfig` per dostawca. budowanie z `Settings` (klucze z `.env`).
- **wzorzec z MangaShift:** `mangashift/services/llm/config.py`.

### `anishift/services/llm/constants.py` (NOWY — kopia 1:1)
- **odpowiedzialność:** stałe domeny llm (limity retry, timeouty, domyślne parametry generacji).

### `anishift/services/llm/errors.py` (NOWY — kopia 1:1)
- **odpowiedzialność:** hierarchia błędów llm.
- **zawartość:** `LlmError`, `LlmConfigError`, `LlmAuthError`, `LlmProviderUnavailableError`, błąd przejściowy (retryowalny) — baza przepięta na `anishift.errors`.

### `anishift/services/llm/protocols.py` (NOWY — kopia 1:1)
- **odpowiedzialność:** `Protocol LlmEngine` — kontrakt dostawcy (engine_id, is_available, metoda completion).

### `anishift/services/llm/types.py` (NOWY — kopia 1:1)
- **odpowiedzialność:** typy domeny: `LlmResponse`, `LlmRole`, `LlmUsage`, typ wiadomości.

### `anishift/services/llm/service.py` (NOWY — kopia z adaptacją sync)
- **odpowiedzialność:** fasada llm — `create_engine` + retry na błędach przejściowych.
- **zawartość:** jak MangaShift; adaptacja: publiczne metody sync (async klient SDK wołany wewnątrz silnika, nie wycieka ponad fasadę); cache instancji per engine_id; retry/backoff na `LlmProviderUnavailableError`/429/5xx.

### `anishift/services/llm/_openai_compat.py` (NOWY — kopia 1:1)
- **odpowiedzialność:** wspólny backend na openai SDK dla 4 silników (openai, deepseek, openrouter, openai_compatible) — 4 silniki, 1 klient.
- **zawartość:** klient chat-completions z konfigurowalnym `base_url`, mapowanie błędów na hierarchię llm.

### `anishift/services/llm/engines/__init__.py` (NOWY — kopia 1:1)
- **odpowiedzialność:** rejestr 6 dostawców — SSOT.
- **zawartość:** wg engine-factory-standard: `LlmEngineId = Literal["anthropic", "deepseek", "gemini", "openai", "openai_compatible", "openrouter"]`, `_REGISTRY`, `available_engine_ids()`, `create_engine()` (guardy jak w standardzie, `engine_id = config.engine_id`) + extras PO create_engine: `supported_models(provider_id)` — czyta katalog modeli z lekkiego `constants.py` silnika BEZ importu SDK (SSOT pickera modeli w panelu); `openrouter`/`openai_compatible` zwracają pusty katalog (model = wolny slug).
- **wzorzec z MangaShift:** `mangashift/services/llm/engines/__init__.py` + engine-factory-standard (specyfika llm).

### 6 pakietów silników (NOWE — kopie 1:1): `engines/anthropic/`, `engines/gemini/`, `engines/openai/`, `engines/deepseek/`, `engines/openrouter/`, `engines/openai_compatible/`
każdy pakiet = 5 plików: `__init__.py`, `api_backend.py`, `config.py`, `constants.py`, `service.py`.
- **odpowiedzialność:** adapter jednego dostawcy do Protocolu `LlmEngine`.
- **zawartość per plik:**
  - `__init__.py` — re-export service+config, `__all__`.
  - `constants.py` — katalog `provider_model_id` (lekki, bez importu SDK — czytany przez `supported_models()`), defaulty.
  - `config.py` — dataclass slots dostawcy (klucz, model, base_url gdzie dotyczy), walidacja `__post_init__`.
  - `api_backend.py` — klient SDK (anthropic → SDK `anthropic`; gemini → `google-genai`; openai/deepseek/openrouter/openai_compatible → delegacja do `_openai_compat.py`); import SDK lazy (wewnątrz metod).
  - `service.py` — implementacja Protocolu, mapowanie odpowiedzi na `LlmResponse`, `is_available()` = fałsz bez klucza.
- **wzorzec z MangaShift:** `mangashift/services/llm/engines/<id>/` — kopiować bez wymyślania.

### `anishift/services/translation/engines/llm/__init__.py`, `config.py`, `constants.py`, `service.py` (NOWE)
- **odpowiedzialność:** cienki adapter — Protocol tłumacza → fasada `services/llm` (jedyny nowy kod tego etapu).
- **zawartość:**
  - `config.py` — dataclass: który dostawca llm i `provider_model_id` (z ustawień panelu), parametry batcha.
  - `constants.py` — prompt tłumaczeniowy (system prompt: tłumacz batch linii, zachowaj liczbę i kolejność, nie ruszaj markerów), limity linii per request.
  - `service.py` — implementuje Protocol tłumacza (`translate_batch` na batchu linii PO dedupie — dedup zostaje wspólny w domenie translation); pod spodem woła fasadę `LlmService`; kontrola liczby zwróconych linii (rozjazd = błąd/fallback jak w dedup.py); `is_available()` = czy skonfigurowany dostawca ma klucz.
  - `__init__.py` — re-export.
- **wzorzec z MangaShift:** kształt pakietu silnika z engine-standard; zero drugiego toru tłumaczenia w pipeline.

### `anishift/services/translation/engines/__init__.py` (ZMIANA)
- **odpowiedzialność:** wpis `llm` w rejestrze translation.
- **zawartość:** `"llm"` dopisany do `TranslationEngineId` i `_REGISTRY` (trójka: moduł adaptera, klasa, config). nic więcej.

### `anishift/services/subtitles/correction.py` (NOWY)
- **odpowiedzialność:** opcjonalna korekta polskich linii przed lektorem (czyszczenie, naturalna polszczyzna) przez fasadę llm — default OFF.
- **zawartość:** funkcja `correct_srt(path, llm_service, ...)` — czyta SRT, wysyła batche TEKSTU linii z promptem korekty (prompt w stałej: popraw literówki/szyk, nie parafrazuj, nie zmieniaj liczby linii), zapisuje wynik; NIGDY nie dotyka timingów ani liczby linii (twarda walidacja: rozjazd = odrzucenie korekty batcha, zostaje oryginał); raport co zmieniono (liczba linii zmienionych).

### `anishift/pipeline/runner.py` (ZMIANA)
- **odpowiedzialność:** opcjonalny krok korekty po tłumaczeniu, przed tts.
- **zawartość:** if z ustawienia `correction_enabled` (default OFF) → `correction.correct_srt(...)`; z wyłączoną korektą przebieg bitowo identyczny jak po etapie 4.

### `anishift/config/settings.py` (ZMIANA)
- **odpowiedzialność:** klucze dostawców llm z `.env`.
- **zawartość:** pola: `ANISHIFT_ANTHROPIC_API_KEY`, `ANISHIFT_GEMINI_API_KEY`, `ANISHIFT_OPENAI_API_KEY`, `ANISHIFT_DEEPSEEK_API_KEY`, `ANISHIFT_OPENROUTER_API_KEY`, `ANISHIFT_OPENAI_COMPATIBLE_API_KEY` + `ANISHIFT_OPENAI_COMPATIBLE_BASE_URL` — wszystkie opcjonalne (brak klucza gasi dostawcę w panelu, nie apkę). aktualizacja `.env.example`.

### `anishift/cli/settings_panel.py` (ZMIANA)
- **odpowiedzialność:** wybór dostawcy llm i modelu + przełącznik korekty.
- **zawartość:** gdy silnik tłumaczenia = `llm`: picker dostawcy (z `available_engine_ids()` rejestru llm, filtrowany przez `is_available()` — dostawca bez klucza znika) i modelu (lista z `supported_models()` — SSOT, panel niczego nie przepisuje; dla openrouter/openai_compatible wolny wpis sluga); przełącznik "korekta napisów przez LLM" TAK/NIE (default NIE); zapis do `config/settings.json`.

## kolejność implementacji

1. kopia `services/llm/` (rdzeń: config/constants/errors/protocols/types/_openai_compat/service) z podmianą importów → weryfikacja: import pakietu przechodzi, mypy/ruff czyste.
2. kopia 6 pakietów silników + rejestr → weryfikacja: smoke rejestru z każdym engine_id (create bez klucza = LlmAuthError/is_available False, nieznany id = ConfigError z listą); import rejestru nie importuje żadnego SDK (test lazy).
3. adaptacja sync fasady → weryfikacja: wywołanie completion na jednym skonfigurowanym dostawcy zwraca `LlmResponse` z sync kodu, zero wycieku coroutines.
4. adapter `translation/engines/llm/` + wpis w `_REGISTRY` translation → weryfikacja: tłumaczenie testowego SRT silnikiem `llm` — ta sama liczba linii i timingi.
5. `subtitles/correction.py` + krok w runnerze (default OFF) → weryfikacja: korekta zmienia tylko tekst; z OFF pipeline identyczny jak po etapie 4.
6. panel (dostawca+model+korekta) + `settings.py`/`.env.example` → weryfikacja ręczna: dostawca bez klucza niewidoczny; wybór modelu z listy `supported_models()`.

## jak testować

smoke rejestru z każdym engine_id; tłumaczenie SRT silnikiem `llm` daje polski SRT o tej samej liczbie linii i timingach; korekta zmienia tylko tekst, nigdy timingi; brak klucza dostawcy = czytelny LlmAuthError (nie traceback), dostawca bez klucza znika z panelu; z wyłączoną korektą pipeline bitowo identyczny jak po etapie 4.

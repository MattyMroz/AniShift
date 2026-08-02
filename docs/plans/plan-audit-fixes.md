# Plan napraw po audycie (2026-08-02)

Audyt statyczny całego repo (pipeline, services, cli/config/setup/platform/utils)
pod kątem kontraktów `simple` + `python instructions`, kontraktu loggera,
duplikacji i wydajności. Branch roboczy: `chore/stage-6.3-audit-fixes`.

## Znaleziska

### Istotne

- `anishift/utils` było w całości wykluczone z ruff i mypy (`pyproject.toml`) —
  bramki nie strzegły utils wbrew filozofii „twardych strażników"; realna
  regresja w `safe_fs`/`secrets`/`device` przeszłaby przez CI bez ostrzeżenia.
- `anishift/services/translation/dedup.py` — martwy w produkcji: jedyny import
  to jego własny test; `TranslationService._prepare_file` reimplementuje
  bogatszą wersję (dwa strumienie, polityka per strumień). Dwie równoległe
  implementacje mogą się cicho rozjechać.
- ~140 linii niemal identycznego mapowania błędów SDK zduplikowane w TRZECH
  adapterach: `services/llm/engines/_openai_compatible.py`,
  `services/llm/engines/gemini/service.py` i
  `services/llm/engines/anthropic/service.py`; widoczna już drobna dywergencja
  w detekcji markerów. Nowy kod błędu trzeba dziś dodawać ręcznie w trzech
  miejscach.

### Drobiazgi (jakość, nie bugi)

- `pipeline/llm_queue.py` — limit współbieżności LLM `4` jako goły literał
  w 4 miejscach (209, 266, 310, 311) zamiast stałej `Final`; częściowa edycja
  rozjechałaby pulę wątków z rampą circuit breakera. Ramp `2 if ... else 4`
  do zapisania czytelniej (podwajanie do sufitu).
- `services/tts/artifacts.py` — 9 raise'ów `TtsResumeError(message)` bez
  `suggestion` w `ErrorContext`, niespójnie z resztą domeny TTS.
- `cli/settings_panel.py:133` — docstring `_translation_engines` sam sobie
  przeczy („filtered by availability", a nic nie filtruje) + nieużywany
  parametr `context`.
- `setup/__init__.py:3` — historyczny docstring („installer arrives later" —
  dawno przybył); narusza regułę „WHAT, nie historia".
- `services/audio/{timeline,resume,commands}.py` — helpery always-raise typowane
  `-> None` zamiast `-> Never`, niespójnie z poprawnymi wzorcami obok
  (`audio/service.py`, `audio/probe.py`).
- `services/subtitles/service.py:332-341` — dopasowanie przetłumaczonych eventów
  liniowym skanem O(n²); przy typowym odcinku pomijalne, przy bardzo dużych
  plikach zauważalne. Indeks słownikowy po `(style, text)` daje O(n).
- `anishift/utils` po zdjęciu exclude: 95 znalezisk ruff (PLC0415, PT*, TRY300,
  PLR2004, BLE001, RUF001/2, S108, F841, SIM117...) + 337 błędów mypy w 8
  plikach (głównie brakujące `-> None` i parametry generyków w testach
  pakietów). Celowe znaki `ℹ`/`×`/`–` w ikonach statusu → `allowed-confusables`.
- `/settings` — panel nie eksponuje wszystkich ustawień faktycznie używanych
  w runtime; inwentaryzacja poniżej (sekcja „Inwentaryzacja /settings").

### Poza zakresem tego brancha (świadomie)

- Rozmiar `pipeline/runner.py` (1441 linii) i `open_settings_panel` (~300
  linii) — uzasadnione `noqa`, refaktor UI/pipeline planowany osobno.
- Problemy heurystyk ASS na realnych MKV — osobny wątek; ASS bywa niepoprawny
  u źródła, wymaga iteracji na żywych plikach.

## Plan napraw (kolejność wykonania)

1. `pyproject.toml`: zdjąć exclude `anishift/utils` z ruff i mypy; per-file-ignores
   dla `anishift/utils/*/tests/**` (jak `tests/**`) i `anishift/utils/*/examples/**`
   (jak `scripts/**`); `allowed-confusables` dla `ℹ`, `×`, `–`.
2. `anishift/utils` — naprawić wszystkie znaleziska ruff+mypy: pliki root
   (device.py, safe_fs.py) + pakiety `logger`, `rich_console`, `timer`
   (delegowane subagentom; realne poprawki, `noqa` tylko dla udokumentowanych
   celowych wzorców z komentarzem WHY).
3. `pipeline/llm_queue.py`: stała `_MAX_PROVIDER_CONCURRENCY: Final` + ramp
   przez podwajanie do sufitu.
4. Usunąć `services/translation/dedup.py` + `tests/.../test_translation_dedup.py`;
   zaktualizować `services/translation/AGENTS.md`.
5. Wydzielić wspólne helpery SDK do `services/llm/engines/_sdk_helpers.py`
   (status, retry-after, normalizacja payloadu, budowa typed errorów);
   kaskady klasyfikacji błędów zostają per provider, bo kodują semantykę
   providera — ich scalenie zmieniałoby zachowanie.
6. `services/tts/artifacts.py`: uzupełnić `ErrorContext` z `suggestion`
   w 9 raise'ach.
7. Docstringi: `cli/settings_panel.py:_translation_engines` (+ martwy parametr),
   `setup/__init__.py`.
8. `-> Never` w always-raise helperach `services/audio/`.
9. `services/subtitles/service.py`: indeks `(style, text)` → lista okien
   czasowych, dopasowanie O(n).
10. Pełne bramki (`ruff check`, `ruff format --check`, `mypy`, `pytest`)
    i commity per logiczna zmiana.

## Inwentaryzacja /settings

Stan na 2026-08-02. Dodanie brakujących pozycji do panelu to osobny task
(panel i tak czeka refaktor UI). Referencje plikowe wg audytu.

### Pola `UserSettings` zapisywane w `config/settings.json`, ale bez wiersza w panelu

- `translation_fallback_chain` (default `["google"]`) — konsumowane w
  `pipeline/runner.py`; dziś zmiana tylko ręcznie w `config/settings.json`.
- `translation_batch_size` (default `0` = default silnika, zakres 0-500) —
  konsumowane przez `TranslationConfig.batch_size`.
- `llm_temperature`, `llm_top_p`, `llm_max_output_tokens` (wszystkie
  default `None`) — konsumowane przez `LlmConfig` w `llm_runtime.py`.
- Uwaga: panelowy „Max retries" (`translation_max_retries`) po cichu ustawia
  TAKŻE `LlmSettings.max_retries` (`runner.py`) — etykieta tego nie mówi.

### Ustawienia tylko przez env/`.env` (`ANISHIFT_*`), panel pokazuje co najwyżej dostępność

- Klucze API: `deepl`, `anthropic`, `gemini`, `openai`, `deepseek`,
  `openrouter`, `openai_compatible` (+ `openai_compatible_base_url`).
  Edytowalny z panelu jest wyłącznie klucz ElevenLabs.
- `workspace_root` (env `ANISHIFT_WORKSPACE_ROOT`, czytany wprost z environ).

### Gałki serwisów zaszyte na sztywno w miejscu wywołania (bez pola w settings)

- `TranslationConfig.source_lang` — literal `"auto"` w `runner.py`.
- `TtsConfig.request_timeout_s` (30 s; sapi 10 s), `shutdown_deadline_s`,
  `queue_capacity` (formuła `max(2, 2*concurrency)`), `metadata_cache_root`.
- Fallbacki `_DEFAULT_ENGINE_CONCURRENCY` (edge 16 / elevenbytes 85 /
  elevenlabs 4 / sapi 1) w `tts_runtime.py`.
- `max_active_batches` — literal `4` w `tts_runtime.py:536`.
- `AudioConfig`: `narrator_sample_rate` (48 kHz), `sample_width`, `channels`
  (kontrakt v1 mono), `normalization_concurrency` (16),
  `operation_timeout_s` (30 s), `shutdown_grace_s` (5 s),
  `flac_compression_level` (5).
- `LlmSettings.timeout_s` / `LlmConfig.timeout_s` (60 s) — nigdy nie nadpisywane.

### Wiersze panelu bez działania (placeholdery renderujące stałą)

- `tts_timeline_policy` (jedyna legalna wartość `serialize`),
  `tts_resume_enabled`, `tts_debug_artifacts`, `tts_sapi_architecture`
  (read-only pochodna wybranego głosu SAPI).

### Martwe ustawienia (zapisywane/eksponowane, nigdzie nie konsumowane)

- `output_variant` (panel pozwala cyklować players/merge/burn — nic tego nie
  czyta) — kandydat: podpiąć w pipeline ALBO usunąć z panelu.
- `move_results_to_output` (toggle w panelu bez konsumenta; wyniki zawsze
  lądują wg `runner.py` obok MKV).
- `translation_concurrency` (walidowane pole modelu; docstring obiecuje
  semafor, który nie istnieje).
- Legacy shimy `UserSettings.volume` / `.voice` / `.tempo` — `volume` to
  znany placeholder do rozdzielenia na voice vs overall przy realnym audio.

# Etap 4 — plan realizacji braków (wg `etap-4-modul-wymagania-final.md`)

> Stan zastany zweryfikowany czytaniem kodu i testów (working tree, branch `feat/stage-4-translation`).
> Braki 3 (bug 4500), 4 (R15 format-aware), 5 (R6b split_line), 6 (R5 DeepL batch_size),
> 8 (detected_lang usunięty), 9 (R7 `translation_concurrency` w settings) — **już zrobione**
> w poprzedniej iteracji i pokryte testami (`test_translation_google.py:62`,
> `test_subtitles_translated_write.py` `\N`/`\n`, `test_translation_linebreak.py:56`,
> `test_translation_deepl.py:68`, `user_settings.py:108/189`). Zostają do weryfikacji bramkami.

## Krok 1 — R14 (S1): zapis CAŁOŚCIOWY zamiast lektorskiego

- `anishift/services/subtitles/service.py`: `write_translated_displayed`/`_translated_displayed_file`
  → `write_translated`/`_translated_file`. Iteracja po WSZYSTKICH eventach Dialogue:
  - displayed → przetłumaczone wersy per event (jak dotąd, w kolejności eventów),
  - spoken → mapa `(style, visible_text(event)) → wersy` (odwrotność `collapse_fbf`);
    brak klucza (np. pusty visible_text) → event bez zmian,
  - non-Dialogue → kopiowane 1:1; guard: `total_events == 0` → None.
- `anishift/pipeline/runner.py` `_write_translated`: przyjmuje cały `FileTranslation`,
  buduje `displayed_verses` + mapę spoken (`split_line` na kopii do pliku; tor TTS
  `FileTranslation.spoken` NIETKNIĘTY — bez łamania). Warunek zapisu: `result.is_success`
  (nie tylko `result.displayed` — SRT ma sam spoken i też dostaje plik).
- Eksporty: `subtitles/__init__.py`, `service.py __all__`; update użyć w
  `test_subtitles_translated_write.py` i `test_translation_network.py`.
- **Weryfikacja:** test bitowy na realnym ASS z `../mm_avh_working_space/temp/dataset_ass/`
  (FAKE engine "PL:"): liczba eventów Dialogue BEZ ZMIAN (całościowy), style bajt-w-bajt,
  timingi bez zmian, tagi `{...}` zachowane, separator `\N`; to samo dla SRT (`\n`,
  zero dosłownego `\N`). Uruchomienie testów + raport liczb przed/po.

## Krok 2 — R6: chunker `chunk_text` wpięty w `_process_txt`

- `anishift/services/subtitles/txt.py`: wydziel `read_txt(path) -> str` (czytanie + błędy);
  `txt_to_spoken` używa go dalej (funkcja ZOSTAJE — rozkaz usera, chunkera NIE usuwać).
- `anishift/pipeline/runner.py` `_process_txt`: `read_txt → chunk_text(text) →
  SpokenLine per kawałek (whitespace zwinięty do jednej linii) → translate → spoken_to_srt`.
- **Weryfikacja:** test w `test_pipeline_translate.py` — spy na `chunk_text` (wywołany)
  + wynikowy SRT z przetłumaczonymi kawałkami; istniejący test txt dalej zielony.

## Krok 3 — R8/N8: Google przez wspólny retry z `_retry.py`

- `_retry.py`: wspólna formuła backoff + `call_with_retry_async` (google jest async —
  sync `call_with_retry` blokowałby event loop; to samo API i semantyka, jeden moduł SSOT).
- `google/service.py` `_call_with_retry`: wywołuje wspólny helper z PRECYZYJNYM wyjątkiem
  `httpx.HTTPError` (jedyna stabilna klasa transient googletrans 4.0.2) zamiast blind
  `except Exception`. Parse-błędy lecą od razu do laddera per-line (pad source).
- **Weryfikacja:** testy — retry na `httpx.ConnectError` (sukces po ponowieniu),
  nie-transient (`ValueError`) rzuca bez ponowień; `call_with_retry_async` unit.

## Krok 4 — bramki (twarde kryterium)

```
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```
Każdy krok domknięty dopiero po zielonym uruchomieniu, nie po napisaniu.

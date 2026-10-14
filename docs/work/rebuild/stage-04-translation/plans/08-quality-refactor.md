# Etap 4 — refaktor jakości modułu `translation`

Cel: doprowadzić `anishift/services/translation/` (+ testy) do porządku wg skilli
`simple` i `python instructions`. Kod, który user nie boi się czytać: czysty,
spójny, zero duplikatów, wszystko posortowane, docstringi zwięzłe. Bez zmian
zachowania — same porządki. Dowód: bramki + smoke na realnych danych.

## Co jest źle (znalezione) i co robię

### 1. Komentarze w testach — ma być ZERO
- `tests/services/translation/` — 22 linie komentarzy `#` w 8 plikach.
- `tests/pipeline/test_pipeline_translate.py` — 1 komentarz.
- **Robię:** usuwam wszystkie. Gdzie komentarz niósł sens testu → koduję go w
  nazwie testu (np. `test_..._triggers_ladder`) albo w danych, tak by test był
  samoopisujący bez komentarza.

### 2. Zduplikowane / źle umieszczone stałe
- `_ZERO_WIDTH = chr(0x200B)` w `chunking.py` **i** `ZERO_WIDTH = chr(0x200B)` w
  `engines/google/constants.py` — ta sama wartość w dwóch miejscach.
  **Robię:** `chunking.py` to źródło prawdy dla zero-width (jest niżej w grafie
  importów, google i tak importuje z domeny). Eksportuję jedną stałą, google
  konsumuje ją zamiast redefiniować literał.
- `_SENTENCE_ENDINGS = SENTENCE_ENDINGS` (`chunking.py:28`) — pusty alias
  „backwards-compatible" (a modułu jeszcze nikt z zewnątrz nie zamroził; to
  historia decyzji, zakazana). **Robię:** kasuję alias, w 2 miejscach używam
  wprost `SENTENCE_ENDINGS`.
- `_ASS_LINE_BREAK = "\\N"` (`service.py:33`) — łatka-stała w pliku serwisu.
  Jest używana raz, w jednej metodzie. **Robię:** zostaje jako nazwana stała
  (magic-string `"\\N"` zasługuje na nazwę), ale przenoszę semantycznie: to stała
  domenowa formatu napisów. Zostawiam w `service.py` w sekcji Constants — jedno
  użycie, brak innego konsumenta, przenoszenie do współdzielonego pliku byłoby
  przeinżynierowaniem (YAGNI). Weryfikuję że to jedyne sensowne miejsce.

### 3. Martwe stałe / pliki / dane
- `DEFAULT_CHUNK_LIMIT` (`chunking.py:22`) — eksportowana, **nigdzie nieużywana**.
  **Robię:** usuwam (stała + `__all__`).
- `engines/google/types.py`, `engines/deepl/types.py`, `engines/llm/types.py` —
  trzy pliki `__all__: list[str] = []` z docstringiem, **nigdy nieimportowane**.
  Silniki importują `BatchedLine` wprost z domenowego `types.py`. Puste
  scaffoldingowe pliki. **Robię:** usuwam wszystkie trzy.
- Rejestr `_REGISTRY` trzyma 3-elementową krotkę `(module, service, config)`, ale
  `config_class` nigdy nie jest używany (`_config_class` wyrzucany). Martwa
  kolumna danych. **Robię:** upraszczam do 2-krotki `(module, service)`.
- `LlmTranslateConfig.context_lines` — pole nigdzie nieczytane, docstring „Stage 5".
  Spekulatywna konfiguracja na przyszłość (YAGNI). **Robię:** usuwam; wróci w
  etapie 5, gdy będzie realnie użyte.

### 4. Niealfabetyczne listy
- `_CONJUNCTIONS_MULTIWORD` (`linebreak.py`) — nieposortowana.
- `_PREPOSITIONS_MULTIWORD` (`linebreak.py`) — nieposortowana.
  (`_CONJUNCTIONS` i `_NON_BREAKING_HEADS` już są posortowane — zostają.)
  **Robię:** sortuję obie krotkami wg domyślnego `sorted()` — dokładnie ta sama
  konwencja, której już używa posortowany `_CONJUNCTIONS` w tym pliku (spójność).

### 5. Docstringi bez wartości / rozdęte
- Przechodzę każdy docstring. Skracam te, które parafrazują nazwę; usuwam
  „backwards-compatible alias" (historia); przycinam gadatliwe wstępy modułów tam,
  gdzie nie niosą WHY.

### 6. Testy — edge case'y i realny smoke
- Uzupełniam braki edge-case'ów (pusty, sam znak, jedno słowo, długie słowo,
  wielowyrazowe spójniki, JP/PL mieszane, obce znaki, sieroty).
- Dodaję `scripts/tmp/smoke_translation.py` — pokazuje NA OCZY (print) wynik
  chunkera na realnym txt, linebreaka na realnych polskich zdaniach, oraz
  tłumaczenia realnego ASS (skipif brak `../mm_avh_working_space/...`).

## Kolejność (algorytm 5 kroków: najpierw KASUJ, potem upraszczaj)

1. Usuń martwe: 3× `types.py`, `DEFAULT_CHUNK_LIMIT`, `context_lines`,
   `config_class` w rejestrze, alias `_SENTENCE_ENDINGS`. → weryfikacja: import + testy.
2. Odduplikuj zero-width (jedno źródło). → weryfikacja: testy google + chunking.
3. Posortuj 2 listy multiword. → weryfikacja: testy linebreak (kept-whole).
4. Wyczyść komentarze w testach (23), przenieś sens do nazw. → weryfikacja: grep = 0.
5. Przytnij docstringi. → weryfikacja: ruff D.
6. Uzupełnij edge-case testy + smoke script. → weryfikacja: pytest, ręczny smoke.
7. Bramki: ruff check + format + mypy + pytest (+ `-m network` z kluczem DeepL).

## Kryteria sukcesu (weryfikowalne)

- `grep '#' tests/services/translation/*.py tests/pipeline/test_pipeline_translate.py`
  (poza `noqa`/`type: ignore`) = 0.
- Zero duplikatu `chr(0x200B)` w module (jedno źródło).
- Obie listy multiword: `list == sorted(list)`.
- Zero nieużywanych plików/stałych/pól wprowadzonych recyklingiem.
- ruff check + format --check + mypy: czysto. pytest: zielono.
- Smoke drukuje realne wyniki (chunker/linebreak/ASS) bez wyjątku.

# logger

Przenośny (współdzielony z mm_avh): logger oparty na loguru z mostem stdlib, sinkami JSON/Rich, scrubbingiem sekretów i readerami logów.

## Mapa katalogów

- `core.py` — `setup_mode`, most stdlib→loguru (`InterceptHandler`), konfiguracja z env
- `config.py` — modele pydantic (Console/File/Logger/Preset) + `get_level_priority`
- `modes.py` — presety DEV/PRODUCTION/SILENT + `get_mode_config`
- `scrubber.py` — maskowanie sekretów w treści logów
- `stats.py` — thread-safe statystyki (globalny singleton `_stats`)
- `log_reader.py` — prosty reader JSON (nie-chainable) dla CLI
- `log_viewer.py` — renderowanie logów przez Rich
- `cli.py` — CLI do przeglądania plików logów JSON
- `timing.py` — context manager `log_duration` (most `utils.timer.Timer` → loguru)
- `_time_helpers.py` — helpery zakresu czasowego dla readerów
- `handlers/` — sinki (console/rich/json); `readers/` — chainable readery + aggregator
- `formatters/` — formatter JSON; `examples/` — dema + presety JSON; `tests/`

## Pułapki

- Scrubbing sekretów działa TYLKO poza DEV (`logger.configure(patcher=...)` za `if not is_dev`) — w DEV klucze/tokeny lecą do logów niezamaskowane. `core.py:136`
- `setup_mode` na starcie robi `logger.remove()` — kasuje WSZYSTKIE istniejące sinki loguru (także dodane z zewnątrz) przed dodaniem swoich. `core.py:89`
- Sink `errors.log.jsonl` NIE powstaje w SILENT, mimo że główny plik SILENT i tak na niego wskazuje. `core.py:122`, `modes.py:79`
- `InterceptHandler` wyłącza logger `uvicorn.access` (`disabled = True`) — jego logi znikają bez śladu. `core.py:157`
- W `apply_filters` filtr czasu woła `filter_by_time` na pełnym zbiorze i NADPISUJE `logs`, kasując wcześniejszy filtr `--level`. `cli.py:147`
- Reader leniwie woła `read_all()` gdy `_logs` puste; dla realnie pustego pliku warunek jest zawsze prawdziwy — plik parsowany przy każdym wywołaniu. `log_reader.py:77`
- `resolve_time_window` przy `minutes/hours/days` zawsze wymusza `end = now`; priorytet minutes > hours > days. `_time_helpers.py:32`
- Override `file_path` w env działa tylko dzięki specjalnej obsłudze w `get_mode_config` (pop do `file`) — `LoggerConfig` ma `extra="forbid"` i odrzuciłby surowe `file_path`. `core.py:190`, `modes.py:119`

## Konwencje

- Dwa różne `LogReader`: prosty (`log_reader.py`) i chainable (`readers/`); docstring odsyła do `readers.LogReader` dla fluent API. `log_reader.py:2`
- `log_viewer.py` importuje prywatne symbole (`_LEVEL_BADGE`, `_LEVEL_COLOR`, `_LEVEL_ICON`, `_show_icons`) z `handlers/console.py`. `log_viewer.py:22`
- Statystyki na globalnym singletonie `_stats`; `increment_stat` (wołane przez sinki) mutuje ten sam obiekt. `stats.py:77`
- Style z configu (`time_style`, `logger_name_style` itd.) to nazwy stylów Rich z `RICH_THEME`. `config.py:113,147`
- `_VENDOR_LOGGERS` (torch, httpx, transformers, PIL...) przypięte na WARNING — logi poniżej celowo tłumione. `core.py:30`
- `timing.py` zależy od `utils.timer.Timer`; `log_viewer.py`/`cli.py` używają wspólnej `..rich_console` — komponenty spoza pakietu. `timing.py:19`

## Komenda

- CLI: `python -m <pkg>.logger.cli <log_file> [--recent 10 | --level ERROR --table | --stats]`.

## Uwaga

- Docstringi importują jako `from logger import ...` (goły `logger`) — realny prefiks to `anishift.utils.logger`.

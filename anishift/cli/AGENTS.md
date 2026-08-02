# cli

REPL prompt_toolkit, komendy `/`, panel `/settings`, banner. Typer entry point `anishift` (default = shell).

## Pliki

- `main.py` — Typer entry point, subkomendy `doctor`/`setup`, default = shell
- `shell.py` — REPL prompt_toolkit routujący linie do komend/pipeline
- `commands.py` — rejestr `/komend`, opcji, dispatch i walidacja
- `completer.py` — completer prompt_toolkit dla `/komend`
- `pipeline_ui.py` — render pipeline na Enter: prompty, progres, raport
- `settings_panel.py` — pełnoekranowy panel `/settings` sterowany strzałkami, auto-save
- `banner.py` — startowy banner ASCII + linia statusu

## Pułapki

- Pusta linia w REPL (nie `/`-komenda) uruchamia pipeline — jawnego triggera brak, samo Enter przetwarza workspace. `shell.py:61-69`
- Opcje `/komend` to gołe tokeny w stylu Claude-Code (`/setup force`), NIE uniksowe flagi; ten sam efekt w CLI Typer to jednak `--force`. `commands.py:125,162-165` vs `main.py:66-69`
- `dispatch` traktuje wszystkie tokeny po nazwie jako opcje przez `frozenset` — duplikaty i kolejność tracone; nieznana opcja tylko ostrzega i utrzymuje REPL. `commands.py:178-187`
- `main()` konfiguruje publiczne `utils/logger` przez `setup_mode_from_env()` z
  wyłączonym sinkiem terminalowym i zawsze zamyka kolejkę przez
  `shutdown_logger()`. Nie dodawaj sinka konsolowego obok Rich Live; diagnostyka
  aplikacji trafia do `logs/anishift.log.jsonl`. `main.py`
- `_ensure_binaries` sprawdza MKVToolNix tylko gdy w inputach jest `.mkv`, i musi wykonać się PRZED startem Rich Live (inaczej prompt instalatora zderzy się z Live). `pipeline_ui.py:54-67`
- W panelu `/settings` `Enter` NIE zatwierdza/wychodzi — działa jak `→` (cykluje wartość); wyjście to tylko `Esc`/`q`. `settings_panel.py:193-201`
- Każda zmiana w panelu jest natychmiast zapisywana na dysk (`save_user_settings` po każdym kroku) — brak anulowania. `settings_panel.py:184-196`
- Panel zawsze pokazuje `llm` i wszystkich providerów; brak sekretu jest markerem `missing key`/`missing base URL`, nie powodem ukrycia lub resetu wyboru. `settings_panel.py`
- Panel pokazuje wszystkie silniki TTS również gdy są niedostępne. Brak klucza,
  SDK, hosta albo głosu jest stanem availability przy pozycji, nie powodem jej
  ukrycia. `tts_settings.py`, `settings_panel.py`
- TTS fields są zależne od silnika: run7/ElevenLabs pokazuje voice options, Edge
  native controls, SAPI architecture/rate/volume. Zmiana głosu przywraca jego
  zapisany profil. `settings_panel.py`, `tts_settings.py`
- W automatycznym pipeline trwała awaria LLM lub TTS zamyka Live przed promptem
  i wymaga `retry`, `settings` albo `finish`; `finish` zachowuje gotowe wyniki i
  oznacza resztę `not_processed`. `pipeline_ui.py`
- Automatyczny pipeline daje każdemu inputowi jeden prealokowany wiersz
  `natsorted`: extraction → translation → rzeczywisty procent TTS → spinner
  audio → stan terminalny. Retry ponownie otwiera ten sam wiersz zamiast dodawać
  nowy. Manualny wybór stylów nie używa `_PipelineProgressRows`. `pipeline_ui.py`
- Manualny prompt stylów: Enter (pusto) zwraca `None` = akceptacja klasyfikatora, nie pusty zbiór. `pipeline_ui.py:149-161`

## Konwencje

- Completer aktywuje się wyłącznie po wiodącym `/`. `completer.py:31-40`
- `COMMANDS` jest jedynym źródłem prawdy — completer, `/help`, sugestie i walidacja z niego wynikają. `commands.py:1-7,84-88`
- Ciężkie importy odraczane lokalnie (`noqa: PLC0415`) — prompt_toolkit/loguru/bootstrap poza ścieżką importu do użycia. `main.py:49-51,84`
- Shell trzyma `.shell_history` obok `config/settings.json` (poza `workspace/`). `shell.py:25-33`
- Domyślna akcja Typera (bez subkomendy) odpala shell przez `invoke_without_command=True` + `no_args_is_help=False`. `main.py:20-25`
- Panel czerpie zakresy z `config.user_settings`, rejestr tłumaczeń z
  `services.translation.engines`, a katalog TTS z leniwego registry i pasywnych
  availability probes. Budowa katalogu nie może wykonywać płatnej syntezy ani
  live network probe. `settings_panel.py`, `tts_settings.py`

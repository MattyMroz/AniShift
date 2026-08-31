# cli

Jedyna granica procesu: Typer entry point `anishift`. Bez subkomendy uruchamia Interactive CLI; techniczne subkomendy pozostają nieinteraktywne.

## Pliki

- `main.py` — Typer app, `main()` (console script), subkomendy `doctor`/`setup`/`run --preset`, bare = Interactive CLI
- `console.py` — jedyny właściciel rekonfiguracji stdout/stderr na UTF-8 + check dla doctora
- `run.py` — wspólny, UI-neutralny preflight Auto oraz wykonanie zaakceptowanego planu
- `interactive/` — lazy-loaded Home, jeden renderer Prompt Toolkit, maskotka, Settings, Manual i wspólny postęp

## Pułapki

- `main()` woła `configure_utf8_streams()` PRZED jakimkolwiek outputem, a dopiero
  potem konfiguruje logger; nie odwracaj tej kolejności. `main.py`
- `main()` konfiguruje publiczne `utils/logger` przez `setup_mode_from_env()` z
  wyłączonym sinkiem terminalowym i zawsze zamyka kolejkę przez
  `shutdown_logger()`. Nie dodawaj sinka konsolowego obok raportu; diagnostyka
  aplikacji trafia do `logs/anishift.log.jsonl`. `main.py`
- Gołe `anishift` otwiera Interactive CLI. Interactive Auto i `anishift run --preset`
  dzielą `prepare_auto_run()`, a `execute_auto_run()` deleguje do wspólnego
  `execute_plan()` używanego także przez Manual. Nie dubluj discovery, planowania
  ani wykonania. `main.py`, `run.py`, `interactive/app.py`
- `TerminalRenderer` jest jedynym ownerem aplikacji Prompt Toolkit, klawiszy i
  alternate screen przez całą sesję. Nie zastępuj go `console.screen()`:
  Rich pomija alternate screen na części konfiguracji `legacy_windows`. Home, Auto i
  wynik czyszczą ten sam output. `interactive/prompts.py`, `interactive/app.py`
- Auto usuwa menu, ale zachowuje markę oraz esencjonalną stopkę z cwd/version.
  Jeden `MultiProgressManager` renderuje postęp pod marką. Resize przebudowuje
  wyłącznie ten widok przez publiczne API; nie dodawaj viewportu, wrappera `Live`,
  ukrywania wierszy ani technicznych ekranów pośrednich.
  `interactive/app.py`, `interactive/progress.py`, `interactive/prompts.py`
- `run --preset` ma stabilny kontrakt kodów wyjścia: `0` sukces, `1` odmowa startu,
  `3` run niepełny/failed, `4` anulowany. `2` jest zarezerwowane dla błędów użycia
  Typera — nie używaj go. `main.py`
- `run --preset` odmawia PRZED wykonaniem, gdy workspace jest pusty, żadna grupa
  nie jest gotowa albo plan ma blokujący `PlanProblem`. Odmowa to zdanie + hint,
  nigdy traceback. `main.py`
- Cały output nieinteraktywny przechodzi przez `_safe()` → `sanitize_event_message`;
  nie echuj `str(exc)` ani ścieżek bezpośrednio. `main.py`
- `_QuietRunEvents` celowo gubi wszystkie eventy postępu — raport ma być
  parsowalny, bez przeplotu. Nie dodawaj tam renderowania. `main.py`
- `RichRunProgress` prealokuje jeden pasek na plik w naturalnej kolejności i odtwarza przejścia
  legacy `_PipelineProgressRows`: `Extracting` od razu ma pasek i procent,
  `Extracted`, `Translating`, `Translated` i `Synthesizing` reużywają ten sam
  wiersz, a spinner jest dozwolony wyłącznie dla faz audio. Techniczne taski nie
  otrzymują osobnych wierszy. Etykieta zachowuje konkretną nazwę źródła wraz z
  rozszerzeniem; procent ekstrakcji i TTS pochodzi wyłącznie z eventu backendu.
  `interactive/progress.py`
- Home ma dokładnie `Auto`, `Ręczny`, `Ustawienia`, `Wyjście`. Settings działa w tym
  samym rendererze, a mutacje `settings.json`, `presets.json` i `.env` przechodzą
  przez `AppService`. Manual przechowuje drafty wyłącznie lokalnie, rejestruje pliki
  zewnętrzne przez `AppService`, waliduje przez `plan_manual()` i przekazuje zaakceptowany
  plan do tej samej ścieżki wykonania oraz postępu co Auto.
  `interactive/app.py`, `interactive/settings.py`, `interactive/manual.py`, `run.py`
- `SettingsController.render()` korzysta wyłącznie z lokalnego, odświeżonego snapshotu;
  nie wykonuj w nim I/O ani wywołań sieciowych, bo renderer odświeża klatkę cyklicznie.
  Katalog modeli jest tylko do odczytu, a probe działa wyłącznie po jawnej akcji.
  Wyjątkiem są `_offset` i `_visible_count`: budżet wierszy znany jest dopiero w
  renderze, więc tam zapisywany jest skorygowany offset dla następnego klawisza.
  `interactive/settings.py`
- Klawisze mają jedną tabelę: `_NORMALISED_KEYS` w `prompts.py`. Na Windowsie każdy
  klawisz specjalny przychodzi z pustym `data`, więc `Keys.Any` zlepia je w
  nierozróżnialne `"any"` — nowy klawisz MUSI dostać własny binding, inaczej nie da
  się go odróżnić. `interactive/prompts.py`
- Przewijanie listy ma własny `_offset`, niezależny od kursora. Klawiatura zawsze
  dociąga widok do kursora (`_follow_cursor`), kółko myszy odczepia widok i nie
  rusza zaznaczenia, a pierwszy klawisz nawigacji dociąga go z powrotem. Wyznaczanie
  okna jest liniowe (`_visible_window`); nie wracaj do przeszukiwania par
  `(start, end)`. `interactive/settings.py`
- Kółko myszy wymaga `_WheelControl`, bo klatka ma dokładnie tyle wierszy co okno i
  domyślny scroller Prompt Toolkit gubi zdarzenie. Nie zastępuj tego
  `ScrollablePane` ani drugim oknem. `interactive/prompts.py`
- Zmiana liczby strzałką NIE zapisuje od razu: ląduje w `_pending` i utrwala się po
  `_SAVE_DELAY_SECONDS` bezczynności, sprawdzanych w `after_render` (nie w
  `render()`, bo tam I/O jest zabronione). Każdy inny klawisz, zejście z wiersza,
  wyjście z kategorii i zamknięcie panelu utrwalają natychmiast — żadne wyjście nie
  może zgubić zmiany. Lista pokazuje wartość oczekującą, nie zapisaną.
  `interactive/settings.py`, `interactive/prompts.py`, `interactive/app.py`
- Ostatnim wierszem każdego poziomu Ustawień jest `Cofnij` i jest przyklejony poza
  przewijaną listą. Nie wciągaj go z powrotem do okna przewijania.
  `interactive/settings.py`
- Lista własnych głosów jest osobnym poziomem nawigacji (`_voices_open`), tak jak
  `_connection`, a nie edytorem skalarnym: jeden głos to jedna linia
  `alias | nazwa | ID`, puste pole usuwa głos, a `parse_setting_input` NADAL odrzuca
  `OBJECT_LIST` — kolekcję składa panel i zapisuje jednym `update_setting`, bo
  `assign_setting_value` sam wycofuje wybór usuniętego aliasu.
  `interactive/settings.py`, `interactive/settings_editors.py`
- `_KNOWN_LAYOUT_GAPS` jest puste i test tego pilnuje: każde nowe pole edytowalne
  MUSI być osiągalne z panelu albo mieć wpis z powodem w `_FIELDS_COVERED_ELSEWHERE`.
  `interactive/settings.py`
- Home ma zatwierdzonego skaczącego slime'a z `assets/mascot/idle/01.gif`,
  sześciowierszowy wordmark, cztery akcje, hint i stopkę z cwd/version. GIF ma być
  animowany: `TerminalRenderer.after_render` wysyła kolejne klatki SIXEL; nie zastępuj
  go statycznym PNG ani półblokami. VS Code korzysta z tracked
  `terminal.integrated.enableImages=true`.
  `interactive/home.py`, `interactive/mascot_native.py`, `interactive/prompts.py`
- Wielkość maskotki jest wyrażona w WIERSZACH TEKSTU (`_FRAME_ROWS`), nie w pikselach:
  `side = _FRAME_ROWS * wysokość_komórki`. Stała liczba pikseli wygląda na mniejszą w
  terminalu o większym foncie (Windows Terminal 10×20 px) niż w VS Code (7×17 px), bo
  obok stoi większy wordmark — user porównuje maskotkę do tekstu, nie do ekranu.
  Skalowanie do rezerwacji w komórkach też jest złe: daje wielkość zależną od szerokości
  komórki. `terminal_cell_size()` pyta o `CSI 16 t`, w razie braku odpowiedzi o
  `CSI 14 t`, a bez odpowiedzi zostaje `_ASSUMED_CELL`. Zapytanie działa tylko na realnej
  konsoli (`isatty`), przywraca poprzedni `ConsoleMode` i ma 250 ms budżetu.
  `interactive/mascot_native.py`
- `NativeMascotImage` rozdziela DWA różne rozmiary i nie wolno ich mieszać: `layout_rows`
  (= `_FRAME_ROWS`) rezerwuje miejsce w layoucie, a `cell_rows`/`cell_columns` opisują to,
  co realnie namalowane, i tylko one sterują kasowaniem. Rozjazd bierze się z
  `_TOP_PAD_DIVISOR`: pół komórki przezroczystego paddingu nad maskotką opuszcza ją o pół
  wiersza, więc obraz zajmuje jeden wiersz więcej niż rezerwacja i zwisa w puste miejsce
  pod marką. `interactive/mascot_native.py`, `interactive/prompts.py`
- Przesunięcie maskotki w prawo wewnątrz klatki jest WSPÓLNE dla całej animacji
  (`_shared_right_shift`, ograniczone najszerszą klatką). Dosuwanie każdej klatki osobno
  do krawędzi wygląda jak rozciąganie w lewo, bo klatki przysiadu są szersze od klatek
  wyskoku. `interactive/mascot_native.py`
- Marka jest wyśrodkowana na szerokości terminala, a maskotka wyrównana DOŁEM do
  wordmarku (`_beside`). Nie przesuwaj bloku marki poza środek. `interactive/home.py`
- Dwa różne kasowania maskotki, nie zamieniaj ich rolami: klatka-do-klatki nadpisuje
  spacjami sam prostokąt obrazu (tanie, bez migotania przy ~17 fps), a ZNIKNIĘCIE
  (Ustawienia, Auto, Ręczny, wyjście) robi `\x1b[2J` plus `renderer.reset()` i
  `invalidate()`. Ani ECH (`\x1b[X`), ani nadpisanie spacjami nie usuwa rastra SIXEL —
  obraz nie żyje w buforze tekstu. `\x1b[2J` czyści tylko ekran alternatywny, więc jest
  bezpieczne; NIE dodawaj `RIS` (`\x1bc`) ani `\x1b[3J`, bo te kasują historię terminala
  usera. Kasowanie wołaj z `after_render`, nigdy z callbacku treści — `renderer.reset()`
  w trakcie renderu jest reentrantny. `interactive/prompts.py`
- Maskotkę widzi wyłącznie Home; Auto, Manual, Settings i komunikaty nie rezerwują
  dla niej miejsca. `MascotController` nie ma własnego workera ani bezpośredniego
  zapisu do terminala. Brak obsługi obrazu lub zbyt mały terminal degraduje widok do
  fallbacku albo braku maskotki. Resize wywołuje czysty rerender bez rozciągania layoutu.
  `interactive/home.py`, `interactive/prompts.py`
- Auto i Ręczny nie mają ekranu pośredniego: `PREPARING` i `MANUAL_PREPARING`
  renderują dokładnie klatkę Home, bez spinnera i bez komunikatu skanowania. Skan
  workspace startuje w tle przy wejściu do Home (`_prewarm_workspace`), więc pierwszy
  widok po Enterze to już postęp albo lista Ręcznego. Nie dodawaj tam ekranu ładowania.
  `interactive/app.py`
- `configure_utf8_streams()` musi znosić `None`, `StringIO` i strumienie bez
  `reconfigure`; jest idempotentne. `console.py`

## Konwencje

- Ciężkie importy odraczane lokalnie (`noqa: PLC0415`) — `bootstrap`,
  `anishift.application` i `anishift.cli.interactive` poza ścieżką importu Typera.
  Subkomendy techniczne (`doctor`, `setup`, `run --preset`) nie mogą ładować
  prompt_toolkit ani Interactive CLI; pilnują tego testy CLI. `main.py`
- Jest dokładnie jedna droga budowy fasady: `bootstrap.production_service()`.
  Entry point nie ma drugiej ścieżki konstrukcji. `main.py`
- Opcje CLI to uniksowe flagi (`--force`, `--preset`), nie gołe tokeny. `main.py`

## Testy

```bash
uv run pytest tests/cli -v
```

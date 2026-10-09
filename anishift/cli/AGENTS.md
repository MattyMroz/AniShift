# cli

Jedyna granica procesu: Typer entry point `anishift`. Bez subkomendy uruchamia Interactive CLI; techniczne subkomendy pozostają nieinteraktywne.

## Pliki

- `main.py` — Typer app, `main()` (console script), subkomendy `doctor`/`setup`/`run --preset`, grupy `watch` i `autostart`, bare = Interactive CLI
- `console.py` — jedyny właściciel rekonfiguracji stdout/stderr na UTF-8 + check dla doctora
- `run.py` — wspólny, UI-neutralny preflight Auto (także dla wskazanego podzbioru grup) oraz wykonanie zaakceptowanego planu
- `exit_codes.py` — kody wyjścia 0/1/3/4 i `run_exit_code()` wspólne dla `run --preset` i okna partii
- `watch.py` — granica rezydenta bez renderera: blokada, IPC, obserwator plików i ikona; stara pętla pozostaje wyłącznie dla testów porównawczych
- `control.py` — cienki klient rezydenta: `open_control()` (start na żądanie) i `resident_status()`
- `resident.py` — sesja panelu: biblioteka, rezerwacje, podgląd zamiaru, zewnętrzne źródła, Start i wynik przez kanał
- `interactive/` — lazy-loaded Home, jeden renderer Prompt Toolkit, maskotka, Settings, Manual i wspólny postęp

## Pułapki

- `interactive/anime_panel.py`, `anime_state.py` and `anime_view.py` render every live
  `AnimeController` screen. The controller projects owner views and delegates input to the panel.
  The pure renderer receives a snapshot and clock; its text hit map excludes tabs, markers,
  checkboxes and padding. Selection summaries and range editing reserve bottom rows.
  `anime_clipboard.py` sends BOM-prefixed UTF-16LE bytes to Windows `clip.exe`.
  Selected-text Ctrl+C/C precedes navigation; unselected Ctrl+C keeps back/blur semantics.
  `_WheelControl` converts Prompt Toolkit character positions to terminal cells before the
  optional mouse callback. Keep CJK/combining characters aligned with the hit map.
- `main._default` catches resident `ControlError`, reports a Polish connection failure and
  exits with `EXIT_REFUSED`; service cleanup also runs when session construction fails.
- `anishift watch` uruchamia rezydenta bez importu Prompt Toolkit; `watch resident` jest aliasem.
  `watch batch` odmawia z komunikatem migracyjnym. Panel i `run --preset` łączą się z właścicielem
  lub uruchamiają go na żądanie. Zamknięcie panelu nie anuluje zaakceptowanej pracy.
  Status sprawdza też dawną blokadę, aby wykryć stary proces przed przełączeniem. `main.py`, `watch.py`
- `run_resident()` zdobywa blokadę PRZED zapisem `instance.json` i klucza, więc przegrany wyścig
  kończy się `EXIT_REFUSED` bez śladu w katalogu stanu. Rezydent nie importuje `cli.interactive`
  ani Prompt Toolkit. `watch.py`
- Tray result clicks open Library; only an owner-validated set ID selects an episode.
  Unknown callbacks open Library without guessing a result. `panel_open` carries navigation;
  a newly launched panel receives its pending target through `panel_attach` after subscribing,
  with owner revalidation. Settings defers navigation until editing ends. Ordinary icon
  activation requests Home. Library Enter still validates playback. `resident.py`,
  `interactive/state.py`, `interactive/app.py`
- Rezydent uruchamia `DirectoryWatch` przed pierwszym uzgodnieniem biblioteki i zamyka go przed
  zwolnieniem blokady. Zdarzenia i kontrola trafiają do tego samego właściciela; tylko inspekcja
  działa w puli I/O. `watch.py`
- `spawn_resident()` startuje `pythonw -m anishift.cli.main watch resident` z
  `DETACHED_PROCESS | CREATE_NO_WINDOW` i strumieniami do `DEVNULL`; poza Windows
  `start_new_session=True`. `watch.py`
- `resident_status()` nie startuje rezydenta — czyta `instance.json` i próbuje `status`; tylko
  udana odpowiedź dowodzi działania. `open_control()` jest jedynym miejscem, które uruchamia
  rezydenta na żądanie klienta. `control.py`
- Panel zawsze łączy się z rezydentem; ukryte flagi `--resident` niczego nie zmieniają
  (`del resident` w `main.py`). Auto, Ręczny i regeneracja korzystają z `ResidentSession`;
  panel dostaje `PlanPreview`, nie graf wykonania. Oddzielna sesja edycji chroni wybrane
  grupy od zaznaczenia do Start lub Esc. Wyjście z panelu odłącza go bez anulowania runu.
  Zewnętrzne źródła są ponownie rejestrowane przy podglądzie po odświeżeniu biblioteki.
  „Dokończ poprzednią pracę” w Ręcznym wymaga tego samego zakresu grup co zapisane zlecenie;
  `plan_resume` odczytuje zweryfikowany pozostały graf, a Start zachowuje ID zlecenia.
- Anime uses `ResidentSession` for catalogue reads, offers, episode downloads and `subscription_add`.
  It has no group catalogue. Receipts and admissions belong to the owner.
- `S` on titles, entries (announcements included) and episodes opens the U06 draft, computed locally
  by `subscription_texts.subscription_draft` from the facade's `cut_point`/`is_target`; Esc returns
  to the source screen. The draft lists aired, unordered episodes before the cut, all marked, with
  the cursor on the first one; a successful add first orders the marked ones through the ordinary
  D batch (its own `command_id`; a refusal never undoes the subscription), then calls the panel's
  `show_list(id, notice)`, which opens Subscriptions, shows a batch refusal and highlights the new
  row once the owner lists it. A draft batch (`_list_batch`) keeps reporting to the list through
  `notify_list`: late per-episode refusals, and an unknown answer that Enter on the list replays
  under the same command ID (`replay_list_batch`) before Enter opens details again.
  `_list_hold` defers late notices until `show_list` has opened the list.
  `interactive/anime.py`, `interactive/subscription_texts.py`, `interactive/state.py`
- The Subscriptions tab in `StateController` renders owner `subscriptions_list` rows. Enter opens U08
  (the Anime episode screen with a subscription status row, every target including numbers beyond the
  catalogue, and „Dodatki tego sezonu” with related OVA/special entries whose Enter opens their U03), D opens the Anime
  search whose Esc returns to the list, W/Space pause/resume, F `subscription_check`, Delete/X remove,
  Ctrl+Z restore. U08 hands W/F/X to the panel through `take_subscription_command`, so command
  workers stay in `StateController`. T, only on a highlighted target whose `EpisodeStatus.polish_wait_until`
  is set, sends `subscription_check` with its `number` and replaces `P ponownie` in the footer; the row Stan
  is `Czeka na PL`/`Bez czekania PL`, the facts line `E{n} polish_line` names the wait of the highlighted
  target (else the lowest target with a Polish state), and a
  `target_not_waiting` refusal rereads episode states (`polish_refused`). F shows `Sprawdzam…`, then the `subscription_checked` result
  for `CHECK_SHOWN_S`, measured by the injected clock: `check_state` in the Stan column, `check_text`
  first beneath the table. Beneath the table stands only what the highlighted row hides: the full state
  when it differs from the short one, dropped columns, then a truncated title (`anime_view._unshown`). U08 leads its notice with the last check;
  `?` there lists every subscription fact (`_subscription_facts`) wrapped and scrollable, so 50-column
  terminals reach the full title, Odcinki (`on_disk/episode_count`) and Gotowe. Row states and columns come only from `subscription_texts` (`row_state`,
  `row_columns`, `row_summary`). The list is `render_anime` with `AnimeScreen.SUBSCRIPTIONS`: one row
  per subscription, fixed Stan width, optional columns dropped before the title shrinks below
  `_TITLE_FLOOR`; an empty list renders as DETAILS with one message row. The context's status row
  shows only a monitoring problem or shadow mode; the global pause appears only in the bottom status
  line, kept at 50×12 by dropping the blank row beneath the table. Problem and conflict states use the ordinary state style. While `AnimeController.in_subscriptions`
  (U08 or the D search) the Subscriptions tab is highlighted, tab keys count from it, and any tab switch
  drops that context first, including an open range editor and marks (an admitted batch survives). `anishift subs` offers `list`, `check` and `remove` through the owner. `interactive/state.py`,
  `interactive/anime_view.py`, `main.py`
- `ResidentSession.episode_offer_start/get` i `episode_choose` współdzielą kanał katalogu; oferta
  należy do jego sesji. Panel wywołuje `get` po starcie i `episode_offer_partial`, przyjmuje tylko
  rosnące rewizje, a `failed` kończy ofertę niezależnie od rewizji. Wybór wysyła
  `offer_id/revision/info_hash/path`; zmiana reprezentanta lub oceny/potwierdzeń daje `offer_changed`.
  `interrupt_reads` unieważnia ofertę. Partie używają głównego kanału i przeżywają rozłączenie.
  Mutacje odcinków wymagają jawnego `command_id`; zachowuj go przy odzyskiwaniu utraconej odpowiedzi.
  `ControlError.connection_lost` (EOF/OSError, timeout odpowiedzi, obcy `command_id`; nie
  `request_too_large`) zamyka połączenie klienta w `ControlClient.call`; kolejne wywołanie łączy się
  od nowa i niczego nie wysyła ponownie. Spóźniona odpowiedź ginie z połączeniem — wynik odzyskuje
  się przez receipt, powtarzając polecenie z tym samym `command_id`. `platform/local_control.py`
  Utrata obserwacji wywołuje `disconnect()` przed ponownym połączeniem: zamyka bezczynne kanały,
  ale zachowuje kanał katalogu z `_open_offer` i wywołania w toku. Po ponownym `observe` panel
  odzyskuje ofertę przez `get`. Tylko odebrana odmowa kończy partię D; błąd bez odpowiedzi
  zachowuje jej `command_id` do ponowienia przez Enter.
- Processing uses `StateController._processing_rows` for rendering, selection, actions and
  counts. A processing request plus `RichRunProgress.group_active` must prove started,
  nonterminal work; the owner's `accepted` state can already contain executing tasks.
  Cached progress alone is insufficient. Every live admitted request awaiting its first
  task appears as preparation, including local Manual work before progress restore. All visible
  bars use numeric zero fallback before any measurement, including initial and replayed snapshots.
  Unknown backend facts stay unknown; unavailable readings retain the last verified display values.
  Recorded downloads also appear, using measured transfer bars and static metadata/pause/problem labels.
  Uncertain acquisitions are excluded from download/handoff rows regardless of cached transfer state;
  live admitted processing remains governed by its request and events. Filtered rows lose their timers.
  Anime admission updates its episode rows without changing tabs. Recorded hashes come
  from owner snapshots, never a UI store.
  Terminal work is reached through History, and recycling/relocation actions through Library.
  Progress labels come from the preview's source names, with `Materiał` for absent/ID-only
  legacy labels. `interactive/state.py`, `interactive/progress.py`, `interactive/anime.py`
- `StateController` opens History with H inside Processing; S or `/` uses the shared
  `TextInput` and suppresses application hotkeys while typing. Default rows are the latest
  50 terminal materials; explicit search includes retained order/download/regeneration boundaries.
  Enter uses `ResidentSession.library_result` validation: completed sidecar-only video sets
  open their recorded source video through the OS association, preferring MKV over MP4.
  Final video products retain priority; missing or changed main products still refuse.
  F passes `playback=False` to reveal the confirmed main product. History
  failures remain visible across renders. `interactive/state.py`, `resident.py`
- Library Details Enter/F submits the exact selected `LibraryFileIdentity` for owner membership
  and freshness validation; informational rows have no file action. Delete previews and submits
  the whole set in one worker session without a confirmation screen. Ctrl+Z delegates
  last-deletion Undo to the owner. Library shows material names, not operation rows or routine
  busy/success/global-progress messages; completed deletion removes the row and Undo restores it.
  Partial leftovers remain accessible. Synchronous action
  refusals survive unrelated snapshots but not a changed selection/view; late action results
  cannot overwrite a newer context. `interactive/state.py`, `resident.py`
- P prepares the owner's retry proposal; confirmation transfers local work to Manual with
  owner revalidation, or admits an explicit remote repeat. Pause never blocks P; under pause only
  rows with owner-projected `automatic` (request origin, or `AcquisitionConfirmation.manual` for
  downloads) show `Wstrzymano` and freeze their timers; a missing field counts as automatic. `interactive/state.py`, `interactive/app.py`
- `run_interactive(service, batch=...)` zwraca kod wyjścia jak `run --preset` i po wyniku odlicza
  10 s w `_handle_idle`, dowolny klawisz zamyka; `interrupt` w partii anuluje run i kończy kodem 4.
  Test buduje aplikację ręcznie? Ustaw też `_batch` i `_closing_at`. `interactive/app.py`

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
- Auto ma trzy regiony: przyklejony nagłówek z marką i maskotką, przewijana kolejka,
  przyklejona stopka. Maskotka może stać wyłącznie w nagłówku: rastra SIXEL nie da
  się przyciąć. Budżet kolejki uwzględnia rzeczywistą wysokość marki i pustą linię.
  Bardzo niski terminal pomija branding, zachowując kolejkę i liczniki ukrytych plików.
  `interactive/app.py`, `interactive/prompts.py`
- `_QueueView.following` znaczy „widok jest na żywo": kolejka trzyma się aktywnej
  pracy, dowolne przewinięcie ją odczepia, a wyłącznie `End` wraca do
  żywej pracy — NIE do ostatniego pliku. `visible` znany jest dopiero w renderze,
  więc ustawia go `fit()`, tak jak `_visible_count` w Ustawieniach. `interactive/app.py`
- `_fit_frame` obcina KAŻDY wiersz do szerokości terminala. Wiersz szerszy zawinąłby
  się, zepchnął resztę w dół i przesunął wiersz ekranowy maskotki. `interactive/app.py`
- Auto usuwa menu, ale zachowuje markę oraz esencjonalną stopkę z cwd/version.
  `RichRunProgress` przygotowuje wiersze Rich Text dla tego samego renderera
  Prompt Toolkit. Paski korzystają z gradientu `palette.py`; nie twórz obok nich
  osobnego `Live` ani `MultiProgressManager`. Resize przebudowuje wspólny widok.
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
- `RichRunProgress` preallocates new file rows at zero in natural order; live task starts
  initialize their own percentage at zero. Later unmeasured activity keeps the last percentage
  and freezes elapsed time. Processing task bars require evidence of actual start;
  download bars use client measurements, and unmeasured handoffs display zero.
  Downloads use the identical phase/name, gradient, percentage and elapsed layout as TTS.
  Their panel-local monotonic clock counts observed transfer activity and freezes on pause
  or lost confirmation; never derive it from acquisition timestamps. Unobserved elapsed
  time displays fixed-width numeric zero. ID-only label suppression belongs to remote
  `from_snapshot`, not the local source-label constructor.
  `Extracted`, `Translate`, `Translated` i `TTS` reużywają ten sam
  wiersz. Procent pochodzi z pomiaru backendu; `progress_percent=None` z komunikatem
  oznacza aktywność bez znanego procentu. Nie wyliczaj pozornego postępu z upływu czasu.
  Techniczne taski nie otrzymują osobnych wierszy. Etykieta zachowuje konkretną nazwę
  źródła wraz z rozszerzeniem; przycinanie odbywa się dopiero w renderze według
  komórek terminala. `✓ Done` zachowuje gradient. Procent opisuje bieżący task; etykiety `Extracted`
  i `Translated` wymagają ukończenia wszystkich tasków danego etapu.
  `interactive/progress.py`
- Run niepełny, anulowany albo z ostrzeżeniami pokazuje przewijany wynik grup:
  przyczyny błędów, zapisane i zachowane produkty oraz lokalizację logu.
  Treść przechodzi przez sanitizację i ten sam renderer. `interactive/app.py`
- Home rezydenta ma kolejność `Panel`, `Ręczny`, `Ustawienia`, `Wyjście`. Settings działa w tym
  samym rendererze, a mutacje `settings.json`, `presets.json` i `.env` przechodzą
  przez `AppService`. Manual przechowuje drafty wyłącznie lokalnie, rejestruje pliki
  zewnętrzne przez `AppService`, waliduje przez `plan_manual()` i przekazuje zaakceptowany
  plan do tej samej ścieżki wykonania oraz postępu co Auto.
  `interactive/app.py`, `interactive/settings.py`, `interactive/manual.py`, `run.py`
- `AnimeController` owns catalogue navigation and owner command correlation. `StateController`
  renders the same PANEL heading and tabs for every tab pinned to the top (below 16 rows without
  blank lines, below 12 without PANEL); the episode title column yields width so Stan stays whole; key hints are pinned
  to the bottom above the status line, and only the content between them is centered vertically
  and by its actual cell width. `_anime_top` is the heading height for mouse hit-testing.
  `anime_view` returns a body of exactly the given rows: notice and summary sit directly above
  the keys, the table keeps its position when they change, and `AnimeFrame.first_row` locates
  the first data row. Columns are sized from content, using the shared menu pointer,
  `pack_keys` footer and existing theme roles.
  Key hints pack into at most two lines without duplicates; navigation hints drop first.
  Never introduce an Anime-specific palette, background, tab strip or separators. Render performs
  no I/O. `AnimePanel` owns text selection,
  copying and row interactions. Mouse events travel through `app` → `state` → `AnimePanel`.
  TITLES is skipped only when every result belongs to visible `Franchise.entries`; one complete,
  released entry can skip ENTRIES. Premiere ordering uses the application facade. The initial
  cursor is the first released row; announcements can be highlighted for `S`, but Enter only names them.
  D submits at most 100 keys and stays on the episode list. Pending mutations are blocked;
  I reads only the cursor. Owner events and receipts correlate by command ID and episode key.
  Each admitted result clears its mark without a background flash; marks keep `[x]` while sending
  and after a refusal, whose Stan label and notice name the owner's reason.
  A truncated release name is shown in full in the notice; its details stay under `?`. Unknown results retain their exact
  ID/payload for Enter replay; a fresh controller reads `episode_states` instead. Esc/Tab discard
  late catalogue navigation but never cancel an admitted batch. Anime never gates D/I/P on the
  global pause and shows no pause notice; only an owner refusal is reported, keeping marks.
  O toggles automation explicitly and never resubmits a refused download.
  On table and list screens the context line sits directly above the column labels, separated by
  the global-status row (blank unless set); context and table form one block centered between
  tabs and keys, and a scrolling table keeps the context fixed above its labels.
  The search screen, and work started from it (`_busy_return` QUERY), has no context line: the field
  sits on the middle content row, with `ANIME` and one blank line above it; the field is `> ` plus `TextInput.render` at
  `anime_state.query_left` (a 32-cell box centered until the text widens it) or the blue busy sentence.
  The context names the current screen: `_shown_entry` (episodes/releases of that entry) is set
  when an entry opens and cleared by the `_screen` setter on QUERY/TITLES/ENTRIES, which show
  `Anime`. `_entry` only remembers the last entry for a fast reopen and never drives the text.
- Every aired, inactive episode remains selectable, including ready, downloaded and failed ones.
  D submits new and repeated keys together through the owner's durable batch. The owner reuses
  repeat candidate exclusion and protected admission replacement. Active ordered/downloading/processing
  rows show cancellation guidance instead of submitting duplicate work. P remains the explicit offer view.
- Zakres odcinków zastępuje zaznaczenia i przyjmuje nieciągłe numery całkowite; nawigacja i powroty
  z podglądu zachowują zaznaczenia oraz kursor. Film ma jeden wiersz Film i `EpisodeKey(id, 1)`;
  podgląd wymaga mapowania. Enter na kandydacie nic nie robi. `interactive/anime.py`
- `_REASON_TEXTS` pokrywa dokładnie `episode_identity.REASONS`. Błąd programistyczny oceny tożsamości
  przerywa cały podgląd, loguje tylko `error_class` i nigdy nie tworzy niepewnej sugestii.
  Tylko IPC INTERNAL + `command_failed` nowej operacji katalogowej sugeruje restart rezydenta;
  `response_too_large` jest osobnym problemem. Wejście H1 i reguły regresji: `application/AGENTS.md`.
- Terminy ponowienia pochodzą z `provider_locks` ownera, przekazywanych przy dołączeniu i zdarzeniu
  `state_changed`, albo lokalnego `AcquisitionService.blocked_until`. Terminy Nyaa i Torrentio są
  osobne. Awaria harmonogramu zachowuje listę odcinków i ostrzeżenie; jawne ponowne wejście ponawia
  odczyt harmonogramu. Renderowanie odliczania nie ponawia zapytań. `interactive/anime.py`, `interactive/state.py`
- Empty AniList results show `Nie znaleziono tytułu`; no Nyaa fallback opens. Missing ani.zip
  mapping retains the domain's AniList episode rows. D/I use the ordinary episode APIs.
  `anime_view.spinner_frame` is the shared Rich dots animation for Anime and Manual.
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
- Paste uses `Keys.BracketedPaste` → `paste:`; the editor rejects control characters
  and masks secrets. Left/Right/Home/End move the text cursor in shared `TextInput`.
  AnimeController owns input focus: the first character or paste activates the idle query and
  inserts its text; Enter and `/` also activate it. This implicit activation is query-only. Focused
  arrows edit, Enter submits, and Esc or unselected Ctrl+C blurs without clearing.
  Selected Ctrl+C copies without blurring. Range prompts open focused and close on one Esc or
  unselected Ctrl+C without applying. Panel derives arrow routing from
  that focus; Tab/Backtab always switch, preserving drafts but blurring inputs and
  invalidating late completions. Only focused fields render a caret or selection;
  the shared block caret highlights the existing grapheme, or one trailing space at
  end of input, without inserting a character into the text.
  `interactive/text_input.py`, `interactive/state.py`, `interactive/anime.py`
- Edycja pól tekstowych ma jeden model `interactive/text_input.py`, oparty na `Buffer`
  i `Document` Prompt Toolkit. Wyszukiwarka, zakres odcinków, ścieżki Manual i ustawienia
  używają tego samego kursora, zaznaczenia, kasowania i undo.
  Nie dopisuj osobnych operacji na stringach w kontrolerach. Kopiowanie zaznaczenia
  ma pierwszeństwo przed wyjściem przez Ctrl+C; walidacja i moment zapisu należą do pola.
- Nieudany zapis zachowuje `_pending` i widoczny błąd; idle nie ponawia go co klatkę.
  Kolejne klawisze mogą ponowić zapis, a dwa kolejne Ctrl+C po ostrzeżeniu jawnie
  porzucają edycję. Brak zmiany nie zapisuje pliku. `interactive/settings.py`
- Picker może naprawić nieaktualny alias Palantira bez oznaczania go jako gotowego
  do wykonania. Domyślne `engine_availability()` sprawdza wybrany model; pominięcie
  tego warunku jest wyłącznie granicą wyboru nowego modelu. `application/service.py`
- Przewijanie listy ma własny `_offset`, niezależny od kursora. Klawiatura zawsze
  dociąga widok do kursora (`_follow_cursor`), kółko myszy odczepia widok i nie
  rusza zaznaczenia, a pierwszy klawisz nawigacji dociąga go z powrotem. Wyznaczanie
  okna jest liniowe (`_visible_window`); nie wracaj do przeszukiwania par
  `(start, end)`. `interactive/settings.py`
- Kółko myszy wymaga `_WheelControl`, bo klatka ma dokładnie tyle wierszy co okno i
  domyślny scroller Prompt Toolkit gubi zdarzenie. Nie zastępuj tego
  `ScrollablePane` ani drugim oknem. `interactive/prompts.py`
- Zapis stanu panelu ma dziesięć reguł i JEDNO źródło:
  `docs/work/plain-cli/06_state_persistence.md`. Cztery łamane najczęściej:
  (1) nawigacja — `↑↓`, `PageUp`/`PageDown`, `Home`/`End`, kółko — NIGDY nie zmienia
  stanu; kulka `●` stoi na zapisanej wartości, a wybiera `Enter`;
  (2) zapis jest cichy, sukces nie ma komunikatu — także reset — a `Przywróć domyślne`
  jest ZAWSZE wejściem w potwierdzenie, bo akcja wykonana wprost z wiersza wygląda jak
  wiersz, który nic nie robi; wiersz statusu jest wydany ZAWSZE
  (`_STATUS_ROWS`), więc nic nie skacze między dwoma klawiszami;
  (3) każde wyjście, także awaryjne, utrwala `_pending` przez `SettingsController.close()`
  bez czekania na deadline (`app.py: _close_settings`, wołane też z `finally` sesji);
  (4) zapis bez różnicy nie istnieje (`_already_stored`), a niepoprawna wartość w trakcie
  pisania milczy — błąd należy do jawnego zatwierdzenia. Panel NIE MA akcji „Zapisz";
  wyjątki na `Enter` są dwa i mają powód: sekret (pół klucza nie może trafić do `.env`)
  oraz linia własnego głosu (pół linii nie jest głosem). Ekran WYNIK odmawia odznaczenia
  ostatniego produktu, żeby znaczniki nie kłamały o zapisanym stanie.
  `interactive/settings.py`, `interactive/app.py`
- Wiersz nosi wartość sformatowaną przy BUDOWIE listy, więc każda zmiana widoczna
  natychmiast musi przebudować `_items` (`_refresh_menu`) — inaczej strzałka rusza
  `_pending`, a liczba na ekranie doczeka dopiero opóźnionego zapisu i wygląda na
  zlagowaną. `interactive/settings.py`
- Zmiana liczby strzałką NIE zapisuje od razu: ląduje w `_pending` i utrwala się po
  `_SAVE_DELAY_SECONDS` bezczynności, sprawdzanych w `after_render` (nie w
  `render()`, bo tam I/O jest zabronione). Każdy inny klawisz, zejście z wiersza,
  wyjście z kategorii i zamknięcie panelu utrwalają natychmiast — żadne wyjście nie
  może zgubić zmiany. Lista pokazuje wartość oczekującą, nie zapisaną.
  `interactive/settings.py`, `interactive/prompts.py`, `interactive/app.py`
- Edytor tekstowy startuje z zapisaną wartością w buforze, więc PIERWSZY wpisany znak
  ją ZASTĘPUJE (`_Editor.pristine`), a `backspace` ją edytuje. Doklejanie znaku do
  podpowiedzi robiło z `2` liczbę `23` i przy zakresie 1-4 blokowało wpisywanie samymi
  błędami. `interactive/settings.py`
- Każdy ekran Ustawień ma `Przywróć domyślne` nad `Cofnij`, zakresowo dla swoich pól
  (`_SCOPE_FIELDS`). Wiersz ma JEDNĄ ścieżkę na wszystkich ekranach, root włącznie:
  `_open_scoped_reset` → `_EditorAction.RESET_SCOPE` → `_reset_scope`, a pytanie ma
  zawsze kształt `PRZYWRÓCIĆ DOMYŚLNE · <ZAKRES>?` (root = scope `all`, tytuł
  `WSZYSTKO`). Root resets shared preferences, the video preset and owner-held recipes.
  Auto resets all three base recipes; its child screens reset only their own recipe.
  Output resets the video preset under its existing identity. Recipe fields use
  `ResidentSession.recipes/update_recipe/reset_recipe`, never a second settings file.
  Ordinary saved preference edits reload the owner before new orders use them.
  Reset preferencji idzie polami w kolejności
  ekranu i pomija te, które po drodze przestały być aktywne, bo zmiana silnika
  przebudowuje resztę. JEDEN wyjątek od kolejności ekranu: zakres `translation`
  zaczyna się od `_TRANSLATION_MODEL_FIELDS`, bo `llm_provider` i
  `llm_provider_model_id` zależą od silnika `llm` — reset `translation_engine`
  (domyślnie `google`) zdejmuje ten warunek i model zostałby po cichu pominięty.
  Połączenia resetu nie mają — tam rolę domyślnego stanu pełni `Usuń klucz`.
  `interactive/settings.py`
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
- Home ma skaczącego slime'a z `assets/mascot/idle/01.gif`, responsywny
  wordmark, cztery akcje, hint i stopkę z cwd/version. GIF ma być
  animowany: `TerminalRenderer.after_render` wysyła kolejne klatki SIXEL. Pierwsza
  klatka interaktywna ma już gotową maskotkę; nie dodawaj startup placeholdera.
  Konstruktor renderera nie koduje obrazu. `run()` sprawdza obsługę SIXEL i metryki,
  przygotowuje animację, dopiero potem uruchamia pętlę wejścia. VS Code korzysta z tracked
  `terminal.integrated.enableImages=true`.
  `interactive/home.py`, `interactive/mascot_native.py`, `interactive/prompts.py`
- Wielkość maskotki jest wyrażona w WIERSZACH TEKSTU (`MASCOT_FRAME_ROWS`), nie w pikselach:
  `side = MASCOT_FRAME_ROWS * wysokość_komórki`. Stała liczba pikseli wygląda na mniejszą w
  terminalu o większym foncie (Windows Terminal 10×20 px) niż w VS Code (7×17 px), bo
  obok stoi większy wordmark — user porównuje maskotkę do tekstu, nie do ekranu.
  Skalowanie do rezerwacji w komórkach też jest złe: daje wielkość zależną od szerokości
  komórki. Produkcyjne `native_mascot_cell()` sprawdza atrybut `4` odpowiedzi DA
  i rozmiar komórki przed startem pętli wejścia; brak wsparcia SIXEL pomija kodowanie.
  Zapytanie działa tylko na realnej konsoli (`isatty`), przywraca poprzedni `ConsoleMode`
  i ma 250 ms budżetu. Nie odczytuj raportów terminala z workera ani podczas obsługi klawiszy.
  `interactive/mascot_native.py`
- `NativeMascotImage.layout_rows` określa nominalną wysokość obrazu; rezerwacja
  renderera i kasowanie używają `cell_rows`/`cell_columns`, czyli całego rastra.
  Padding nad obrazem zwiększa go o wiersz, którego nie wolno liczyć jako pustego
  odstępu nad postępem. Wordmark wyrównuje się do nominalnej wysokości, nie do
  dodatkowego wiersza rastra. `interactive/mascot_native.py`, `interactive/home.py`, `interactive/prompts.py`
- Przesunięcie maskotki w prawo wewnątrz klatki jest WSPÓLNE dla całej animacji
  (`_shared_right_shift`, ograniczone najszerszą klatką). Dosuwanie każdej klatki osobno
  do krawędzi wygląda jak rozciąganie w lewo, bo klatki przysiadu są szersze od klatek
  wyskoku. `interactive/mascot_native.py`
- Marka jest wyśrodkowana na szerokości terminala, a maskotka wyrównana DOŁEM do
  wordmarku (`_beside`). Nie przesuwaj bloku marki poza środek. `interactive/home.py`
- Trzy kolory marki (azure, fiolet, czerwień maskotki) mają JEDNO źródło:
  `interactive/palette.py`. Wordmark i paski postępu biorą z niego gradient, a panel styl
  `brand_accent` doklejany do konsoli przez `push_theme(BRAND_THEME)` — generyczny
  `purple_bold` z motywu `rich_console` nie występuje już w żadnym widoku i test tego
  pilnuje. Tekst akcentu zachowuje oryginalny azure, a pomoc i stopka mają kontrastowy
  szary. Czerwień gradientu nie oznacza błędu; błędy zachowują styl `error`.
  `interactive/palette.py`, `interactive/prompts.py`, `interactive/home.py`
- Klatka-do-klatki nadpisuje sam prostokąt obrazu. Zniknięcie lub przesunięcie
  rastra obsługuje `before_render`: `reset(leave_alternate_screen=False)` oraz
  buforowane `\x1b[2J`, wysłane razem z nową klatką tekstu. Domyślne `reset()`
  wychodzi z alternate screen i odsłania starą konsolę. Nie kasuj w callbacku treści
  ani po narysowaniu nowego widoku. Końcowy redraw (`application.is_done`) nie może
  malować rastra po przywróceniu konsoli. Nie używaj `RIS` ani `\x1b[3J`, które
  kasują historię użytkownika. `interactive/prompts.py`
- Maskotkę pokazują Home i Auto, jeśli pozostaje miejsce na obsługę; Manual,
  Settings i komunikaty nie rezerwują jej miejsca. `MascotController` nie ma własnego workera ani bezpośredniego
  zapisu do terminala. Brak obsługi obrazu lub zbyt mały terminal degraduje widok do
  fallbacku albo braku maskotki. Resize wywołuje czysty rerender bez rozciągania layoutu.
  `interactive/home.py`, `interactive/prompts.py`
- Wordmark jest nieruchomy i nie ma średniego wariantu. Gdy pełny napis nie mieści
  się obok maskotki, pozostaje sama maskotka. Tekstowy podskok korzysta z zegara
  renderera i stałej rezerwacji; nie koduj obrazów w `render()`. `interactive/home.py`
- Etap ma osobną 14-kolumnową rezerwację przed nazwą źródła. Pasek rośnie do
  40 kolumn przed rozszerzaniem długiego tytułu; nazwa wykorzystuje resztę miejsca.
  `interactive/progress.py`
- Auto i Ręczny nie mają ekranu pośredniego: `PREPARING` i `MANUAL_PREPARING`
  renderują dokładnie klatkę Home, bez spinnera i bez komunikatu skanowania. Skan
  workspace startuje w tle przy wejściu do Home (`_prewarm_workspace`), więc pierwszy
  widok po przygotowaniu to postęp albo lista Ręcznego. Prewarm może przygotować
  brakujące narzędzia; instalator działa bez własnego renderera. Nie dodawaj ekranu ładowania.
  `interactive/app.py`
- Prompt Toolkit ogranicza redraw do 30 fps, a resize i odświeżanie czasu sprawdza
  co 100 ms. Zachowaj `mouse_support=True`: kółko przewija kolejkę, ustawienia i wynik.
  `interactive/prompts.py`
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

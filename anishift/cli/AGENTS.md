# cli

Jedyna granica procesu: Typer entry point `anishift`. Bez subkomendy uruchamia Interactive CLI; techniczne subkomendy pozostają nieinteraktywne.

## Pliki

- `main.py` — Typer app, `main()`, `doctor`/`setup`/`run --preset`, grupy `watch`, `autostart` i `subs`; bare = Interactive CLI
- `console.py` — jedyny właściciel rekonfiguracji stdout/stderr na UTF-8 + check dla doctora
- `run.py` — wspólny, UI-neutralny preflight Auto (także dla podzbioru grup) i wykonanie zaakceptowanego planu
- `exit_codes.py` — kody wyjścia i `run_exit_code()` wspólne dla `run --preset` i okna partii
- `watch.py` — granica rezydenta bez renderera: blokada, IPC, obserwator plików i ikona; `run_daemon` to stara pętla tylko dla testów porównawczych
- `control.py` — cienki klient rezydenta: `open_control()` (start na żądanie) i `resident_status()`
- `resident.py` — `ResidentSession`: biblioteka, rezerwacje, podgląd, zewnętrzne źródła, Start i wynik przez kanał
- `interactive/` — Home, jeden renderer Prompt Toolkit, maskotka, Settings, Manual, panel i wspólny postęp
- `interactive/state.py` — `StateController`: szkielet panelu, klawisze, workery, zdarzenia ownera. Treść zakładek
  w czystych `state_subscriptions.py`, `state_processing.py` (z Historią), `state_library.py` i liściu
  `state_texts.py`; importy tylko `state` → `state_*` → `state_texts`. `PANEL_ACTIONS` leży w `actions.py`.
- `interactive/anime.py` — `AnimeController` (stan, klawisze, mysz, workery); importy `anime` → `anime_rows`/`anime_releases`
  → liść `anime_texts` (`stated` importuje `state.refusal_text` leniwie); reeksportuje `EPISODE_REASON_LABELS` dla
  `state_processing.py`. Render w `interactive/anime_view.py`; `AnimePanel` posiada zaznaczenie, kopiowanie i wiersze.

## Proces, rezydent i IPC

- `main()` woła `configure_utf8_streams()` PRZED jakimkolwiek outputem, dopiero potem logger
  (`setup_mode_from_env()` bez sinka terminalowego, zawsze `shutdown_logger()`); diagnostyka idzie do
  `logs/anishift.log.jsonl`, nie dodawaj sinka konsolowego. `configure_utf8_streams()` znosi `None`, `StringIO`
  i strumienie bez `reconfigure`, jest idempotentne. `main.py`, `console.py`
- Jedna droga budowy fasady: `bootstrap.production_service()`. Ciężkie importy odraczane lokalnie
  (`noqa: PLC0415`): `doctor`, `setup`, `run --preset` i `watch` nie ładują Prompt Toolkit ani
  `cli.interactive` (testy CLI). Opcje to uniksowe flagi (`--force`, `--preset`).
- `main._default` łapie `ControlError`, zgłasza po polsku błąd połączenia i kończy `EXIT_REFUSED`; cleanup usług
  biegnie też, gdy budowa sesji zawiedzie. Ukryte flagi `--resident` niczego nie zmieniają (`del resident`).
- `watch resident` to ukryty alias `watch`; `watch batch` odmawia z wyjaśnieniem zastępstwa. Panel i `run --preset`
  łączą się z ownerem lub uruchamiają go na żądanie; zamknięcie panelu nie anuluje zaakceptowanej pracy. Status
  sprawdza też dawną blokadę, by wykryć stary proces.
- `run_resident()` zdobywa blokadę PRZED zapisem `instance.json` i klucza: przegrany wyścig kończy się
  `EXIT_REFUSED` bez śladu w katalogu stanu. `DirectoryWatch` startuje przed pierwszym uzgodnieniem biblioteki,
  zamyka się przed zwolnieniem blokady; zdarzenia i kontrola idą do jednego ownera, tylko inspekcja w puli I/O.
  Transport zamyka `_close_acquisition` po `_close_client`; `AutomationOwner.serve` go nie zamyka. `watch.py`
- `spawn_resident()`: `pythonw -m anishift.cli.main watch resident`, `DETACHED_PROCESS | CREATE_NO_WINDOW`, `DEVNULL`.
- `resident_status()` nie startuje rezydenta: czyta `instance.json` i próbuje `status`; tylko udana odpowiedź
  dowodzi działania. `open_control()` to jedyny start na żądanie klienta. `control.py`
- Auto, Ręczny i regeneracja idą przez `ResidentSession`; panel dostaje `PlanPreview`, nie graf. Osobna sesja
  edycji chroni wybrane grupy od zaznaczenia do Start lub Esc. Zewnętrzne źródła rejestruje się ponownie przy
  podglądzie po odświeżeniu biblioteki. „Dokończ poprzednią pracę” wymaga zakresu grup zapisanego zlecenia;
  `plan_resume` czyta zweryfikowany pozostały graf, Start zachowuje ID zlecenia. `resident.py`
- Kliknięcie wyniku w zasobniku otwiera Bibliotekę; odcinek wybiera tylko set ID zwalidowany przez ownera, nieznany
  callback nie zgaduje. `panel_open` niesie nawigację; nowy panel dostaje cel przez `panel_attach` po subskrypcji,
  z rewalidacją. Settings odkłada nawigację do końca edycji; zwykła aktywacja ikony prosi o Home.
- `episode_offer_start/get` i `episode_choose` współdzielą kanał katalogu; oferta należy do jego sesji. Panel woła
  `get` po starcie i `episode_offer_partial`, przyjmuje tylko rosnące rewizje, `failed` kończy ofertę niezależnie
  od rewizji, `interrupt_reads` ją unieważnia. Partie idą głównym kanałem i przeżywają rozłączenie.
- Mutacje odcinków wymagają jawnego `command_id`; zachowuj go przy odzyskiwaniu odpowiedzi. `ControlError.connection_lost`
  (EOF/OSError, timeout, obcy `command_id`; nie `request_too_large`) zamyka połączenie w `ControlClient.call`;
  następne wywołanie łączy się od nowa i niczego nie powtarza. Spóźniona odpowiedź ginie z połączeniem — wynik
  odzyskuje receipt przy powtórzeniu z tym samym `command_id`. Utrata obserwacji woła `disconnect()`: zamyka
  bezczynne kanały, zachowuje kanał katalogu z `_open_offer` i wywołania w toku; po `observe` panel odzyskuje ofertę
  przez `get`. Tylko odebrana odmowa kończy partię D; błąd bez odpowiedzi zachowuje `command_id` do ponowienia
  Enterem. `platform/local_control.py`
- Restart rezydenta sugeruje tylko IPC INTERNAL + `command_failed` nowej operacji katalogowej (nie `response_too_large`).

## Wyjście nieinteraktywne

- `run --preset`: `0` sukces, `1` odmowa startu, `3` niepełny/failed, `4` anulowany; `2` zarezerwowane dla Typera.
  Odmawia PRZED wykonaniem przy pustym workspace, braku gotowej grupy albo blokującym `PlanProblem`; odmowa to
  zdanie + hint, nigdy traceback. `main.py`
- Cały output nieinteraktywny idzie przez `_safe()` → `sanitize_event_message`; nie echuj `str(exc)` ani ścieżek.
  `_QuietRunEvents` celowo gubi eventy postępu, żeby raport był parsowalny.
- Interactive Auto i `run --preset` dzielą `prepare_auto_run()`; `execute_auto_run()` deleguje do `execute_plan()`
  używanego też przez Manual. Nie dubluj discovery, planowania ani wykonania. `run.py`
- `run_interactive(service, batch=...)` zwraca kod jak `run --preset`, po wyniku odlicza 10 s w `_handle_idle`;
  `interrupt` w partii anuluje run i kończy kodem 4. Test budujący aplikację ręcznie ustawia `_batch` i `_closing_at`.
  `anishift subs` (`list`, `check`, `remove`) działa przez ownera.

## Renderer i wejście

- `TerminalRenderer` jest jedynym ownerem aplikacji Prompt Toolkit, klawiszy i alternate screen przez całą sesję;
  nie zastępuj go `console.screen()` (Rich pomija alternate screen przy części `legacy_windows`). Zachowaj
  `mouse_support=True`; redraw do 30 fps, resize i zegar co 100 ms. `interactive/prompts.py`
- Render nie robi I/O ani sieci (klatka odświeża się cyklicznie). Wyjątek: `_offset` i `_visible_count`, bo budżet
  wierszy znany jest dopiero w renderze. Opóźnione zapisy sprawdza `after_render`.
  `_fit_frame` obcina KAŻDY wiersz do szerokości terminala; szerszy zawinąłby się i przesunął raster maskotki.
- Klawisze mają jedną tabelę `_NORMALISED_KEYS`. Na Windowsie klawisz specjalny ma puste `data`, więc `Keys.Any`
  zlepia je w `"any"` — nowy klawisz MUSI dostać własny binding. Paste: `Keys.BracketedPaste` → `paste:`.
- Kółko wymaga `_WheelControl` (domyślny scroller gubi zdarzenie przy klatce równej oknu); nie zastępuj go
  `ScrollablePane` ani drugim oknem. Przelicza pozycje znaków na komórki przed callbackiem — CJK i znaki łączące
  muszą zgadzać się z mapą trafień.
- Edycja tekstu ma jeden model `interactive/text_input.py` (`Buffer`/`Document`): wyszukiwarka, zakres, ścieżki
  Manual i ustawienia dzielą kursor, zaznaczenie, kasowanie i undo; nie dopisuj operacji na stringach w
  kontrolerach. Edytor odrzuca znaki sterujące i maskuje sekrety; kursor podświetla istniejący grafem, nie wstawia
  znaku. Kopiowanie zaznaczenia wygrywa z wyjściem przez Ctrl+C. Fokus posiada `AnimeController`; niejawna
  aktywacja (znak, paste, Backspace) tylko w zapytaniu; Tab/Backtab zawsze przełączają, zachowując drafty, gasząc
  fokus i unieważniając spóźnione dopełnienia. `anime_clipboard.py` wysyła do `clip.exe` UTF-16LE z BOM.
- Mysz ma jedno źródło `interactive/pointer.py` (`PointerGesture`, tagi `mark_row`/`mark_target`/`mark_crumbs`,
  pola `TextInput.render`). Anime idzie `app` → `state` → `AnimePanel`, reszta przez `FrameSelection`;
  `app._follow_click` zamienia `Click` na istniejące ścieżki klawiszy. Drugi klik działa na kursor z pierwszego,
  bez ponownego `select`, bo lista może się przesunąć; ekrany tekstowe tagują `mark_row(..., opens=False)`.
  Gesty, hover i zaznaczenie: `test_interactive_mouse.py`, `test_interactive_hover.py`.
- Paleta ma jedno źródło `interactive/palette.py` (gradient wordmarku i pasków, `brand_accent` przez
  `push_theme(BRAND_THEME)`); `purple_bold` nie występuje w widokach (test). Czerwień gradientu to nie błąd, błędy
  mają styl `error`. Nie twórz palety, tła ani separatorów specyficznych dla Anime.

## Panel

- Cztery zakładki mają jeden słownik klawiszy (`actions.py`); stopka i pomoc `?` powstają z `ScreenActions`, łańcuchy
  `if` obsługi zostają. Zestawy klawiszy, ciche aliasy, stopkę, `_DESCRIPTIONS` i `mark_keys` pilnuje
  `tests/cli/test_panel_keys.py`. Układ ramki, puste listy i progi wysokości: `test_panel_frame.py`,
  `test_anime_view.py`, `test_library_columns.py`. `anime_view.shown_rows` to jedyna liczba wierszy renderu i
  stronicowania; `AnimeFrame.first_row` i `_anime_top` służą trafieniom myszy; puste teksty list tylko z
  `StateController._empty_text`. Linia statusu (`_global_status`) liczy wyłącznie `material_counts` ownera.
- Anulowanie w Przetwarzaniu uzbraja `_question`; anuluje tylko Enter, inny klawisz, klik w wiersz lub wyjście kasują.
  X znaczy „zatrzymaj”: anulowane zlecenie blokuje Auto dla tej samej wersji źródła jak błąd
  (`control._latest_request_blocks`); wraca tylko przez jawne P albo nową wersję źródła.
- Anime czyta katalog, oferty, pobrania i `subscription_add` przez `ResidentSession`; nie ma katalogu grup, receipt
  i przyjęcia należą do ownera, kolejność premier daje fasada. Korelacja po `command_id` + kluczu odcinka. Esc/Tab
  odrzucają spóźnioną nawigację katalogu, nigdy przyjętej partii.
- D wysyła najwyżej 100 kluczy (nowe i powtórki razem) trwałą partią ownera; aktywne wiersze dostają wskazówkę
  anulowania zamiast duplikatu. Nieznany wynik zachowuje ID/payload do ponowienia Enterem; świeży kontroler czyta
  `episode_states`. Pauza globalna nie blokuje D/I/P; O poza zapytaniem przełącza automat i nie ponawia odmowy.
- Odcinek z `EpisodeStatus.retry_group` (nieudane lub anulowane przetwarzanie, wideo na dysku) jest niewybieralny i nie wchodzi do
  partii D. P, a bez zaznaczeń także D, oddaje grupę przez `take_retry`; `StateController` otwiera Przetwarzanie
  jak `show_processing`, stawia kursor na tym wierszu i przygotowuje `retry_proposal` tą samą drogą co Historia
  (H → P). Samo D/P niczego nie pobiera; gdy stan zdążył się zmienić, owner może zwrócić propozycję `reacquire`,
  którą wykonuje dopiero jawny Enter.
- Lista wydań to `episode_selection.visible(offer.candidates, offer.suggestion)` — nie filtruj jej w UI drugi raz.
  Kursor, zaznaczenia i sugestia śledzą wiersze po hashu lub równości, nigdy po indeksie oferty. Odmowa z
  `REPEATABLE_REASONS` zostawia listę z P (`_repeatable_offer`). `_Screen.FILES` to tylko wybór pliku paczki.
  `_REASON_TEXTS` pokrywa dokładnie `episode_identity.REASONS`; błąd programistyczny oceny tożsamości przerywa
  podgląd, loguje tylko `error_class` i nie tworzy niepewnej sugestii.
- Film ma jeden wiersz i `EpisodeKey(id, 1)`. Zakres zastępuje zaznaczenia; nawigacja zachowuje zaznaczenia i kursor.
  Pusty wynik AniList nie otwiera fallbacku Nyaa; brak mapowania ani.zip zachowuje odcinki AniList.
  `anime_view.spinner_frame` to wspólna animacja Anime i Manual.
- Terminy ponowienia: `provider_locks` ownera albo `AcquisitionService.blocked_until`; render odliczania nie odpytuje.
- Draft subskrypcji liczy lokalnie `subscription_texts.subscription_draft` z `cut_point`/`is_target` fasady. Udane
  dodanie zamawia zaznaczone zwykłą partią D z własnym `command_id`; odmowa partii nie cofa subskrypcji. Partia
  draftu raportuje przez `notify_list`, nieznaną odpowiedź ponawia `replay_list_batch` z tym samym ID, a
  `_list_hold` trzyma spóźnione komunikaty, aż `show_list` otworzy listę.
- Subskrypcje renderują wiersze `subscriptions_list`; stany i kolumny tylko z `subscription_texts` (`row_state`,
  `row_columns`, `row_summary`), polskie zdania tylko z `notice_text` fasady. Widok odcinków subskrypcji oddaje
  W/R/F/X przez `take_subscription_command`, a odtwarzanie przez `take_playback` (`_play` → `_open_episode`
  Biblioteki), więc workery zostają w `StateController`. T tylko na celu z `polish_wait_until`; odmowa
  `target_not_waiting` odświeża stany. Czas wyniku sprawdzenia mierzy wstrzyknięty zegar (`CHECK_SHOWN_S`). Zmiana
  zakładki porzuca kontekst subskrypcji z edytorem zakresu i zaznaczeniami, nie przyjętą partię. Układ i teksty:
  `test_subscriptions_panel.py`, `test_subscription_draft.py`.
- Przetwarzanie używa `_processing_rows` do renderu, wyboru i akcji. Wiersz zlecenia wymaga dowodu rozpoczętej,
  nieterminalnej pracy (`RichRunProgress.group_active`); `accepted` może mieć wykonujące się taski, sam cache postępu
  nie wystarcza; żywe zlecenie bez taska to przygotowanie. Niepewne pobrania nie trafiają do wierszy. Hashe tylko
  ze snapshotów ownera. Nieznane fakty zostają nieznane; brak odczytu zachowuje ostatnie zweryfikowane wartości.
  Nieudane albo anulowane zlecenie (`failed`/`partial`/`cancelled`), którego wideo źródłowe owner widzi na dysku
  (`_local_primary`), przychodzi jako wiersz `waiting`
  z `attention` i `reason=processing_failed` (`Błąd`, licznik „do sprawdzenia”); zostaje do ponowienia, bez X.
  P na nim (`failed_group`) przygotowuje `retry_proposal` jak Historia; nic nie ponawia się samo. Del na nim
  (`deletable_set`) idzie tą samą drogą co Del w Bibliotece (`_delete_now`, `deletion_preview/start`, Kosz). Owner
  daje `set_id` = `unrecorded_set_id(group_id)` tylko grupie spoza `_ready_library`; ta przestrzeń nazw nigdy nie
  trafia w zestaw Biblioteki, a nieudana grupa Biblioteki nie dostaje Del. Owner rzutuje taką grupę przez
  `unrecorded_set`. Wiersz chowają tylko `_hidden` i aktywne usuwania (`deleting_sets`), nie historyczne
  `pending_deletions`; Ctrl+Z (poza Historią) woła `deletion_undo` jak Biblioteka.
  Na aktywnym wierszu Del pozostaje cichym aliasem X.
- P przygotowuje propozycję ponowienia ownera: lokalna praca idzie do Ręcznego z rewalidacją, zdalna dostaje jawne
  powtórzenie. Pauza nie blokuje P; `Wstrzymano` i zamrożone liczniki tylko dla wierszy z `automatic` (brak pola =
  automatyczny).
- Historia (50 ostatnich materiałów): Enter waliduje przez `library_result`, F daje `playback=False`; błędy zostają.
- Biblioteka wysyła dokładne `LibraryFileIdentity` do walidacji ownera. Del ukrywa wiersz w tej klatce i usuwa na
  własnym wątku; wiersz wraca z odmową, jeśli snapshot nie potwierdzi operacji. Ctrl+Z deleguje Undo do ownera.
  Etykiety z `library_label` fasady i pól `series/season/episode` (`state_library._series_label`), inaczej z pliku.
  Brak akcji P i wiersza relokacji — owner sam ponawia relokacje. Odmowy przeżywają obce snapshoty, nie zmianę
  wyboru; spóźniony wynik nie nadpisze nowszego kontekstu. Testy: `test_library_actions.py`, `test_library_columns.py`.

## Auto, postęp i maskotka

- Auto: przyklejony nagłówek (marka + maskotka), przewijana kolejka, przyklejona stopka. Maskotka tylko w
  nagłówku — rastra SIXEL nie da się przyciąć. `_QueueView.following` znaczy „na żywo”: przewinięcie odczepia,
  tylko `End` wraca do żywej pracy (nie do ostatniego pliku); `visible` ustawia `fit()`. Brak ekranu ładowania:
  `PREPARING` renderuje klatkę Home, skan startuje w tle (`_prewarm_workspace`). `interactive/app.py`
- `RichRunProgress` daje wiersze Rich Text temu samemu rendererowi; nie twórz `Live` ani `MultiProgressManager`.
  Procent tylko z pomiaru backendu (`progress_percent=None` = aktywność bez procentu), nigdy z upływu czasu. Zegar
  pobrań jest lokalny i monotoniczny, liczy obserwowany transfer, nie znaczniki pozyskania. Wycinanie etykiet
  ID-only należy do `from_snapshot`. Etykiety etapów tylko w `_ACTIVE_LABEL`/`_AUDIO_LABEL`; brak wpisu pokazuje
  `Przetwarzanie`. `_row_geometry` liczy z najdłuższej nazwy listy — każdy osobny wiersz dostaje te same `names`.
  Szczegóły: `test_interactive_progress.py`.
- Home: `Panel`, `Ręczny`, `Ustawienia`, `Wyjście`. Mutacje `settings.json`, `presets.json` i `.env` idą przez
  `AppService`. Manual trzyma drafty lokalnie, rejestruje pliki zewnętrzne przez `AppService`, waliduje
  `plan_manual()` i wykonuje ścieżką Auto. Wynik niepełny pokazuje się przez sanitizację w tym samym rendererze.
- Maskotkę animuje `TerminalRenderer.after_render`; konstruktor nie koduje obrazu, `run()` sprawdza SIXEL i metryki
  przed pętlą wejścia, bez placeholdera. Rozmiar w WIERSZACH (`MASCOT_FRAME_ROWS` × wysokość komórki), nie w
  pikselach. `native_mascot_cell()` pyta terminal tylko przy `isatty`, przywraca `ConsoleMode`, ma 250 ms; nie czytaj
  raportów terminala z workera ani przy klawiszach. Rezerwacja i kasowanie: `cell_rows`/`cell_columns`, wordmark:
  `layout_rows`. Przesunięcie w prawo wspólne dla animacji (`_shared_right_shift`). `MascotController` nie ma
  workera ani zapisu do terminala. VS Code wymaga śledzonego `terminal.integrated.enableImages=true`.
- Zniknięcie lub ruch rastra obsługuje `before_render`: `reset(leave_alternate_screen=False)` + buforowane `\x1b[2J`
  z nową klatką; domyślne `reset()` odsłania starą konsolę, końcowy redraw (`is_done`) nie maluje rastra. Nie używaj
  `RIS` ani `\x1b[3J` — kasują historię użytkownika. `interactive/prompts.py`

## Ustawienia

- Reguły zapisu: `docs/work/02-plain-cli/plans/05-panel-state-persistence.md` §1; zakresy resetu: `docs/reference/settings.md`. Każde
  wyjście utrwala `_pending` przez `SettingsController.close()` (`app._close_settings`, też z `finally` sesji).
- Strzałka na liczbie ląduje w `_pending` i utrwala się po `_SAVE_DELAY_SECONDS` w `after_render`. Wiersz niesie
  wartość z BUDOWY listy, więc natychmiast widoczna zmiana wymaga `_refresh_menu`. Nieudany zapis zachowuje
  `_pending` i błąd, idle nie ponawia co klatkę; dwa Ctrl+C po ostrzeżeniu porzucają edycję. Pierwszy wpisany znak
  ZASTĘPUJE zapisaną wartość (`_Editor.pristine`), Backspace ją edytuje.
- Reset ma jedną ścieżkę `_open_scoped_reset` → `_EditorAction.RESET_SCOPE` → `_reset_scope` (`_SCOPE_FIELDS`) i zawsze
  wchodzi w potwierdzenie. Idzie polami w kolejności ekranu, poza `translation`: najpierw `_TRANSLATION_MODEL_FIELDS`,
  bo reset silnika na `google` zdjąłby warunek modelu LLM. Receptury tylko przez
  `ResidentSession.recipes/update_recipe/reset_recipe`, nigdy drugi plik ustawień.
- `Cofnij` jest przyklejony poza przewijaną listą. Własny `_offset`: klawiatura dociąga (`_follow_cursor`), kółko
  odczepia; okno liczy liniowe `_visible_window`.
- Własne głosy to osobny poziom (`_voices_open`); `parse_setting_input` NADAL odrzuca `OBJECT_LIST` — kolekcję składa
  panel i zapisuje jednym `update_setting`. `_KNOWN_LAYOUT_GAPS` jest puste (test): nowe pole musi być osiągalne z
  panelu albo mieć powód w `_FIELDS_COVERED_ELSEWHERE`. Katalog modeli tylko do odczytu, probe po jawnej akcji.
- Lektor przy `elevenreader` ma sekcję SESJA (`_tts_items`): wiersz stanu z `elevenreader_session()` i akcję
  logowania w wątku jak `_start_probe`; `Esc` zwalnia panel, a spóźniony wynik ginie po `_generation`. Zaległe
  sprzątanie konta (`SessionRecord.cleanup_pending`) dodaje wiersz `elevenreader-cleanup` przy każdym silniku (sam
  wiersz w SESJA, gdy wybrany jest inny silnik), którego Enter uruchamia
  to samo logowanie, bo `sign_in` kończy sprzątanie. Etykiety
  głosów pochodzą z `ELEVENREADER_VOICES` fasady, nie z listy w panelu.
- Picker naprawia nieaktualny alias Palantira bez oznaczania gotowości; `engine_availability()` sprawdza wybrany model.

## Testy

```bash
uv run pytest tests/cli -v
```

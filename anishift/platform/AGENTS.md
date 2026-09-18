# platform

Kod zależny od systemu: wykrycie OS i ścieżki binarek (`binaries.py`), blokada jednej instancji procesu (`process_lock.py`), lokalny kanał sterowania rezydenta (`local_control.py`), zadanie Windows przy logowaniu (`autostart.py`), klucze Web UI w ustawieniach qBittorrenta (`qbittorrent_config.py`). `__init__.py` to re-eksport binarek.

## Pułapki

- `child_processes.py` przypisuje proces rezydenta Windows do Job Object: narzędzia
  potomne kończą się także po nagłym zabiciu właściciela. Prywatny qBittorrent i panel
  są uruchamiane z jawnym breakaway. Nie zamykaj uchwytu joba ręcznie w żywym rezydencie.
- `ManagedQBittorrent` dowodzi własności przez PID, czas utworzenia, własną binarkę
  i katalog profilu potwierdzony w API. GUI przejęte przez użytkownika blokuje automatyczne
  zamknięcie. Zwolnienie ukończonego torrenta zachowuje media (`deleteFiles=false`).
- `ManagedQBittorrent.released_hashes()` reads and validates only the existing `process.json`.
  Do not replace it with `_load()`: that path can initialize the profile and change ACLs.
  New download admission invalidates the matching release receipt.
- `recycle.py` runs bounded native workers. `restore_worker.py` resolves the exact saved receipt
  inside the virtual Recycle Bin, moves it through Shell to recorded same-volume staging and
  publishes by checked file handle without replacement. Keep parent/path/identity guards;
  never use global Shell Undo or rename raw bin files. `FILE_RENAME_INFO.FileName` needs a
  terminating WCHAR outside `FileNameLength`; uncertain staging stays recorded for explicit recovery.
- Odczyt transferów prywatnego GUI pozostaje dostępny po ręcznym przejęciu; mutacje nadal
  wymagają własności. Zamknięcie przejętego klienta nie jest awarią startu i nie uruchamia go ponownie.
- `tray.py` ładuje oryginalną maskotkę z pakietowego `app.ico` bez importowania frontendu.
  The v4 callback carries the event in the low word of `lParam` and the icon ID in the high word,
  never a notification ID. Balloons are serialized; only a shown balloon in an uninterrupted
  click-consumed lifecycle may select its owner-validated result. Timeout, hide or lost lifecycle
  revokes targeting for the icon lifetime. Icon activation still opens Home; notification clicks
  request Library navigation. `open_path` opens Library results after caller validation.
  Delivery failures retire only the active balloon; later offers remain eligible even while
  targeting is revoked. Failed submissions are never retried; retiring a balloon cancels its timer.
- `DirectoryWatch` zakłada pierwszy odczyt `ReadDirectoryChangesW` przed uruchomieniem wątku.
  Oczekiwanie jest blokujące, a stop używa osobnego zdarzenia; przed zamknięciem uchwytów
  anuluje i rozlicza overlapped I/O. Pusty bufor oznacza overflow i pełne uzgodnienie, nie brak
  zmian. Niewspierany nośnik przechodzi w jawny `polling`. `directory_watch.py`
- qBittorrent nadpisuje `%APPDATA%\qBittorrent\qBittorrent.ini` przy wyjściu, więc `enable_web_ui` odmawia,
  dopóki proces działa (`tasklist`), a przed zapisem kopiuje plik do `qBittorrent.ini.anishift.bak`. Dopisuje
  wyłącznie BRAKUJĄCE klucze na końcu sekcji `[Preferences]`, zachowując CRLF/LF i każdą inną linię bez zmian.
  `qbittorrent_config.py`
- qBittorrent 5 nie uruchomi Web UI bez hasła, nawet przy `WebUI\LocalHostAuth=false`, więc zapis dokłada
  `WebUI\Password_PBKDF2` (PBKDF2-HMAC-SHA512, 100 000 iteracji, 64 B, `"@ByteArray(salt:hash)"`). Hasło wraca
  z `enable_web_ui` TYLKO wtedy, gdy powstało teraz; nie trafia ani do logu, ani do pliku jawnym tekstem.
  `qbittorrent_config.py`
- `is_running()` dekoduje odpowiedź `tasklist` jako UTF-8 z `errors="replace"`, nie stroną `oem` jak
  `autostart.py`: dopasowywany jest wyłącznie ASCII-owy `"qbittorrent.exe"`, a kodek `oem` nie istnieje poza
  Windows, gdzie biegną testy CI. `qbittorrent_config.py`

- `ProcessLock` trzyma uchwyt przez cały czas życia procesu; plik blokady zostaje po zakończeniu i jego
  istnienie NIE oznacza zajętej blokady. Sprawdzaj przez nieblokujące `acquire()`. `process_lock.py`
- Kanał sterowania to `\\.\pipe\anishift-<12 hex
  z sha256 katalogu stanu>`, poza nim `<state_dir>/control.sock`. Nigdy TCP i nigdy `send`/`recv`
  (pickle) — wyłącznie `send_bytes`/`recv_bytes` z JSON i limitem `MAX_FRAME_BYTES`; `recv_bytes`
  z limitem podnosi `OSError` i psuje połączenie, więc ramka ponad limit kończy je bez odpowiedzi.
  `local_control.py`
- `PipeListener.accept()` blokuje na `WaitForMultipleObjects(..., INFINITE)`, więc `close()` budzi
  wątek accept własnym połączeniem do siebie; samo zamknięcie listenera go nie odblokuje.
  `local_control.py`
- `ipc.Listener` powstaje BEZ `authkey`: klucza dowodzi wątek danego połączenia
  (`deliver_challenge`/`answer_challenge` z terminem `HANDSHAKE_TIMEOUT_S` pilnowanym przez
  `threading.Timer` zamykający połączenie). Klient milczący albo rozłączony psuje wtedy tylko swój
  wątek, a nie pętlę accept. Po stronie klienta `ipc.Client` idzie na wątek pomocniczy, bo
  `PipeClient` sam ponawia `WaitNamedPipe` i żaden timer go nie przerwie. `local_control.py`
- `instance.json` NIE dowodzi działania rezydenta — dowodem jest udane połączenie i odpowiedź na
  `status`. Plik powstaje dopiero PO zdobyciu `resident.lock`, więc przegrany wyścig go nie dotyka.
  `local_control.py`, `cli/watch.py`
- Klucz `control.key` powstaje przez `os.open(..., O_CREAT|O_EXCL|O_WRONLY, 0o600)`, a na Windows
  dodatkowo `icacls /inheritance:r /grant:r "<konto>:F"`; nieudany `icacls` to warning, nie awaria.
  Klucza nie ma w logach ani w komunikatach. `local_control.py`
- Rozgałęzienie po systemie idzie przez `is_windows()`, nie przez `sys.platform`, żeby test mógł
  wymusić obie ścieżki; wyjątkiem jest alias `ChannelConnection`, bo `PipeConnection` istnieje w
  typeshed tylko na win32. `local_control.py`
- Wolny subskrybent nie rośnie w nieskończoność: `_EventOutbox` trzyma ostatnie zdarzenie per
  (zdarzenie, `run_id`, `task_id`/`group_id`), więc `state_changed` scala się do jednej pozycji,
  a przy `MAX_OUTBOX_EVENTS` pierwszy wylatuje wpis nieterminalny. Gdy wszystkie są terminalne,
  usuwany jest najstarszy; pełny stan odtwarza snapshot. Nadmiarowe połączenie dostaje `REFUSED`.
  `local_control.py`
- Serwer przypisuje `session_id` połączenia, którego klient nie może podać w JSON. Odpowiedzi
  obsługuje osobny wątek z ograniczoną kolejką, więc wolny podgląd nie blokuje odczytu EOF
  i zwolnienia rezerwacji przez `on_disconnect`. `local_control.py`
- `resident_command()` to `watch_command()` z dopiskiem `resident`, więc obie drogi startu mają
  jedno źródło ścieżki `pythonw.exe`. `autostart.py`
- `autostart.py` zarządza wyłącznie zadaniem `AniShift Watch`. Rejestruje je z pliku XML
  (`schtasks /Create /XML`: LogonTrigger i Principal bieżącego konta, InteractiveToken,
  LeastPrivilege), bo `schtasks /SC ONLOGON` odmawia zwykłemu użytkownikowi. Stan czyta z
  `/Query /XML` (`Settings/Enabled`), a nie z lokalizowanej kolumny CSV; brak zadania rozpoznaje
  po niezerowym `/Query`, nie po tekście błędu. Wyjście `schtasks` dekoduje stroną `oem` z
  `errors="replace"` (polski Windows pisze cp852). Poza Windows odmawia; `enable` od razu
  uruchamia zadanie. `autostart.py`

- `FFMPEG`/`FFPROBE` dzielą podkatalog `"ffmpeg"`, `MKVEXTRACT`/`MKVMERGE` dzielą `"mkvtoolnix"` — jeden podfolder trzyma po dwie binarki. `binaries.py`
- Niepusty plik w `external/bin/` ma pierwszeństwo; fallback `shutil.which` działa
  także na Windows. Plik 0 B nie jest gotową binarką w żadnym źródle. `binaries.py`
- `external_bin_root` pochodzi z `anishift/paths.py`. `bundled_binary_path` dokłada katalog narzędzia z `TOOL_DIR` i nazwę właściwą dla systemu; instalator i zarządca procesu korzystają z tego samego układu. `binaries.py`

## Konwencje

- `is_windows()` istnieje, by wołający NIE rozgałęziali sami po OS przy doborze rozszerzenia i fallbacku PATH. `binaries.py`
- Rozszerzenie `.exe` doklejane tylko na Windows przez `_exe_name`; gdzie indziej goły stem. `binaries.py:89-91`
- `BinaryNotFoundError` dziedziczy po `FatalError` i podnosi się z pełnym `ErrorContext` (`ErrorCode.BINARY_NOT_FOUND`). `binaries.py:52-53,141-148`
- Komunikat naprawczy `require_binary` różni się per OS: poza Windows dokleja podpowiedź o ręcznym dorzuceniu binarki do `external/bin/<tool>`. `binaries.py:138-140`
- `external/bin/<tool>/` jest gitignored, pobierane przez `anishift setup`. `binaries.py:3,138`
- `settings_path()` odmawia poza Windows i bez `%APPDATA%`; `installed_executable()` sprawdza `%ProgramFiles%`,
  `%ProgramFiles(x86)%` i `%LOCALAPPDATA%\Programs`, a dopiero na końcu `PATH`. Instalacji nie wykonuje —
  doctor podpowiada `winget install qBittorrent.qBittorrent`. `qbittorrent_config.py`

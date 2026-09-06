# platform

Kod zależny od systemu: wykrycie OS i ścieżki binarek (`binaries.py`), blokada jednej instancji procesu (`process_lock.py`), zadanie Windows przy logowaniu (`autostart.py`), klucze Web UI w ustawieniach qBittorrenta (`qbittorrent_config.py`). `__init__.py` to re-eksport binarek.

## Pułapki

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
- `external_bin_root` liczy repo-root jako `parents[2]` — twardo zakłada głębokość `anishift/platform/binaries.py`; przeniesienie modułu zepsuje ścieżkę. `binaries.py`

## Konwencje

- `is_windows()` istnieje, by wołający NIE rozgałęziali sami po OS przy doborze rozszerzenia i fallbacku PATH. `binaries.py`
- Rozszerzenie `.exe` doklejane tylko na Windows przez `_exe_name`; gdzie indziej goły stem. `binaries.py:89-91`
- `BinaryNotFoundError` dziedziczy po `FatalError` i podnosi się z pełnym `ErrorContext` (`ErrorCode.BINARY_NOT_FOUND`). `binaries.py:52-53,141-148`
- Komunikat naprawczy `require_binary` różni się per OS: poza Windows dokleja podpowiedź o ręcznym dorzuceniu binarki do `external/bin/<tool>`. `binaries.py:138-140`
- `external/bin/<tool>/` jest gitignored, pobierane przez `anishift setup`. `binaries.py:3,138`
- `settings_path()` odmawia poza Windows i bez `%APPDATA%`; `installed_executable()` sprawdza `%ProgramFiles%`,
  `%ProgramFiles(x86)%` i `%LOCALAPPDATA%\Programs`, a dopiero na końcu `PATH`. Instalacji nie wykonuje —
  doctor podpowiada `winget install qBittorrent.qBittorrent`. `qbittorrent_config.py`

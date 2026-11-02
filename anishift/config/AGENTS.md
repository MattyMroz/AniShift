# config

Ustawienia i `Settings` (pydantic-settings, prefix `ANISHIFT_`, z `.env`), preferencje trwałe w `config/settings.json` edytowane wprost w pliku, katalog modeli oraz bootstrap workspace.

## Pliki

- `settings.py` — klucze API, token Palantira, qBittorrent, `workspace_root` i `subscription_shadow` z env / `.env` przez pydantic-settings
- `user_settings.py` — preferencje workflow i silników, trwałe w `config/settings.json`
- `field_catalog.py` — typowany, niezależny od UI katalog pól ustawień (`SettingSpec`)
- `field_access.py` — jedyne tłumaczenie między `SettingSpec` a polem `UserSettings`
- `env_file.py` — atomowa edycja pojedynczej wartości w `.env` (zapis sekretu)
- `model_catalog.py` — projekcja wbudowanej listy z `services/llm/engines/palantir/constants.py` na DTO aplikacji; bez odczytu plików i sieci
- `presets.py` — wersjonowane presety trybu automatycznego w `config/presets.json`
- `workspace.py` — rozwiązywanie i bootstrap katalogu workspace

## Pułapki

- `config_path()` NIE leży w tym pakiecie, tylko w `anishift/paths.py` — import `anishift.config` wciąga rejestry audio/translation/llm/tts, więc warstwa prezentacji bierze samą ścieżkę z `paths`. `anishift.config` tylko ją re-eksportuje. `anishift/paths.py`
- Repo root i domyślne katalogi wylicza wyłącznie `anishift/paths.py`. `workspace.py` rozstrzyga override oraz sprawdza marker `pyproject.toml` przed użyciem domyślnego workspace; brak markera nadal oznacza błąd.
- `elevenlabs_api_key` jest tylko dla silnika `elevenlabs`; silnik `elevenbytes` go NIE używa (ma własny wbudowany klucz). `settings.py`
- Token Palantira ma dwa źródła (`ANISHIFT_PALANTIR_TOKEN` i nieprefiksowany `FOUNDRY_API_TOKEN`), ale precedencji NIE rozstrzyga ten pakiet — deleguje ją do `resolve_palantir_token` w adapterze LLM, a pole kompatybilnościowe czyści po walidacji. `settings.py`
- Walidacja `UserSettings` zależy od runtime'owego `available_engine_ids()` — dozwolone id silników nie są stałą, tylko wynikiem rejestru wołanym przy każdym `load_user_settings`. `user_settings.py`
- `_clean_number` celowo odrzuca `bool` przed sprawdzeniem `int|float` (bo `bool` jest podklasą `int`) — `true` w JSON nie przejdzie jako liczba. `user_settings.py`
- `resolve_workspace_root` zwraca ścieżkę, ale NIE tworzy jej na dysku — katalog powstaje dopiero przez `ensure_workspace_dir`. `workspace.py`
- `ensure_workspace_dir` rzuca `NotADirectoryError` (spoza hierarchii AniShift), gdy root istnieje jako plik nie-katalog. `workspace.py`
- Głosy ElevenReadera (alias, etykieta, ID) żyją tylko w `VOICES` silnika; `user_settings.py` i `field_catalog.py`
  je czytają. Zmiana silnika nie przenosi obcego głosu: `_normalize_tts_selection` daje ElevenBytes `dallin` (chyba
  że alias jest własnym głosem ElevenBytes), ElevenLabs zamiast aliasu ElevenReadera domyślne `dallin`, a
  ElevenReaderowi `fronczewski`. Współbieżność ElevenReadera nie jest
  polem panelu (zawsze 1, jak SAPI).
- Modele, możliwości i opcje Palantira należą do serwisu LLM; `model_catalog.py` tylko je projektuje. Nie dodawaj tu parsera ani drugiej listy modeli. Adres enrollmentu pozostaje preferencją (`UserSettings.palantir_enrollment_base_url`), nie polem katalogu.

## Konwencje

- `settings.json` i `presets.json` leżą w `<repo>/config/`, celowo POZA `workspace/`, by folder na MKV został czysty. Oba są gitignorowane i edytowane ręcznie. Katalog modeli jest wbudowany w kod serwisu LLM.
- Wbudowany preset `default` żąda `full_pl` oraz `narration_audio`, więc normalny Auto
  planuje prawdziwy TTS i miks. Silnik oraz głos nadal pochodzą z `UserSettings`.
  `presets.py`, `field_catalog.py`
- Kolejność rozstrzygania workspace w `resolve_workspace_root`: argument `override` (`bootstrap` podaje `Settings.workspace_root`), potem `os.environ["ANISHIFT_WORKSPACE_ROOT"]`, na końcu `<repo>/workspace` (wymaga markera `pyproject.toml`). `workspace.py`
- System env ma pierwszeństwo nad `.env`; nieznane klucze ignorowane (`extra="ignore"`, `case_sensitive=False`). `settings.py`
- Zapis preferencji i presetów atomowy: `<name>.tmp` + `replace`. `user_settings.py`, `presets.py`
- `load_user_settings` nigdy nie rzuca — brak/nieczytelny/zły-typ/poza-zakresem cicho wraca do defaultów, nieznane klucze odfiltrowane po `__dataclass_fields__`. `user_settings.py`
- `DEFAULT_SUBDIRS` = `("tmp", *TASK_DIRECTORIES)`, czyli `tmp` plus foldery zadaniowe `subs`, `translate`, `audiobook`, `cover`. `ensure_workspace_dir` zwraca `WorkspaceConflict` dla każdej zarezerwowanej nazwy zajętej plikiem albo dowiązaniem: to miejsce zostaje nietknięte, pozostałe powstają. Run scope ma marker PID/run ID, a cleanup usuwa tylko bezpiecznie zweryfikowane, nieaktywne katalogi bez żywego właściciela. `workspace.py`

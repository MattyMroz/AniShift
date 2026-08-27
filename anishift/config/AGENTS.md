# config

Ustawienia i `Settings` (pydantic-settings, prefix `ANISHIFT_`, z `.env`), preferencje edytowane przez ekrany ustawień TUI, katalog modeli oraz bootstrap workspace.

## Pliki

- `settings.py` — klucze API i token Palantira z env / `.env` przez pydantic-settings
- `user_settings.py` — preferencje workflow i silników, trwałe w `config/settings.json`
- `field_catalog.py` — typowany, niezależny od UI katalog pól ustawień (`SettingSpec`)
- `field_access.py` — jedyne tłumaczenie między `SettingSpec` a polem `UserSettings`
- `env_file.py` — atomowa edycja pojedynczej wartości w `.env` (zapis sekretu)
- `model_catalog.py` — katalog dostawców i aliasów modeli z `config/anishift.models.jsonc`
- `presets.py` — wersjonowane presety trybu automatycznego w `config/presets.json`
- `workspace.py` — rozwiązywanie i bootstrap katalogu workspace

## Pułapki

- `config_path()` NIE leży w tym pakiecie, tylko w `anishift/paths.py` — import `anishift.config` wciąga rejestry audio/translation/llm/tts, więc warstwa prezentacji bierze samą ścieżkę z `paths`. `anishift.config` tylko ją re-eksportuje. `anishift/paths.py:38`
- Repo root liczy się w DWÓCH miejscach po różnych regułach: `paths.py` bierze `parents[1]` bez markera, a inferencja workspace `parents[2]` z markerem `pyproject.toml` i twardym błędem, gdy markera nie ma. `anishift/paths.py:33`, `workspace.py:88-99`
- `elevenlabs_api_key` jest tylko dla silnika `elevenlabs`; silnik `elevenbytes` go NIE używa (ma własny wbudowany klucz). `settings.py:114`
- Token Palantira ma dwa źródła (`ANISHIFT_PALANTIR_TOKEN` i nieprefiksowany `FOUNDRY_API_TOKEN`), ale precedencji NIE rozstrzyga ten pakiet — deleguje ją do `resolve_palantir_token` w adapterze LLM, a pole kompatybilnościowe czyści po walidacji. `settings.py:151-170`
- Walidacja `UserSettings` zależy od runtime'owego `available_engine_ids()` — dozwolone id silników nie są stałą, tylko wynikiem rejestru wołanym przy każdym `load_user_settings`. `user_settings.py:851`
- `_clean_number` celowo odrzuca `bool` przed sprawdzeniem `int|float` (bo `bool` jest podklasą `int`) — `true` w JSON nie przejdzie jako liczba. `user_settings.py:523`
- `resolve_workspace_root` zwraca ścieżkę, ale NIE tworzy jej na dysku — katalog powstaje dopiero przez `ensure_workspace_dir`. `workspace.py:102,128`
- `ensure_workspace_dir` rzuca `NotADirectoryError` (spoza hierarchii AniShift), gdy root istnieje jako plik nie-katalog. `workspace.py:136`
- `model_catalog` jest tylko do CZYTANIA — nic w aplikacji nie zapisuje `anishift.models.jsonc`, bo zapis zniszczyłby komentarze użytkownika. Adres enrollmentu jest więc preferencją (`UserSettings.palantir_enrollment_base_url`), nie polem katalogu. `model_catalog.py:1-18`

## Konwencje

- `settings.json`, `presets.json`, `ui_state.json` i `anishift.models.jsonc` leżą w `<repo>/config/`, celowo POZA `workspace/`, by folder na MKV został czysty. `anishift/paths.py:38`
- Override workspace czyta się bezpośrednio z `os.environ["ANISHIFT_WORKSPACE_ROOT"]`, nie przez `Settings` (który by go pominął przez `extra="ignore"`). `workspace.py:43,77`
- System env ma pierwszeństwo nad `.env`; nieznane klucze ignorowane (`extra="ignore"`, `case_sensitive=False`). `settings.py:102-107`
- Zapis preferencji i presetów atomowy: `<name>.tmp` + `replace`. `user_settings.py:908-910`, `presets.py:122-124`
- `load_user_settings` nigdy nie rzuca — brak/nieczytelny/zły-typ/poza-zakresem cicho wraca do defaultów, nieznane klucze odfiltrowane po `__dataclass_fields__`. `user_settings.py:826,849`
- `DEFAULT_SUBDIRS` = dokładnie `("temp",)`. Run scope ma marker PID/run ID, a cleanup usuwa tylko bezpiecznie zweryfikowane, nieaktywne katalogi bez żywego właściciela. `workspace.py:52,55`

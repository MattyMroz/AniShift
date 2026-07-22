# config

Ustawienia i `Settings` (pydantic-settings, prefix `ANISHIFT_`, z `.env`), preferencje panelu `/settings` oraz bootstrap workspace.

## Pliki

- `settings.py` — klucze API / env z `.env` przez pydantic-settings
- `user_settings.py` — preferencje panelu `/settings`, trwałe w `config/settings.json`
- `workspace.py` — rozwiązywanie i bootstrap katalogu workspace

## Pułapki

- `elevenlabs_api_key` jest tylko dla silnika `elevenlabs`; silnik `elevenbytes` go NIE używa (ma własny wbudowany klucz). `settings.py:31`
- Walidacja `UserSettings` zależy od runtime'owego `available_engine_ids()` z `services.translation.engines` — dozwolone id silników nie są stałą, tylko wynikiem rejestru wołanym przy każdym `load_user_settings`. `user_settings.py:24,183`
- `_clean_number` celowo odrzuca `bool` przed sprawdzeniem `int|float` (bo `bool` jest podklasą `int`) — `true` w JSON nie przejdzie jako liczba. `user_settings.py:147`
- `resolve_workspace_root` zwraca ścieżkę, ale NIE tworzy jej na dysku — katalog powstaje dopiero przez `ensure_workspace_dir`. `workspace.py:92,96`
- `ensure_workspace_dir` rzuca `NotADirectoryError` (spoza hierarchii AniShift), gdy root istnieje jako plik nie-katalog. `workspace.py:102-104`

## Konwencje

- `settings.json` panelu leży w `<repo>/config/`, celowo POZA `workspace/`, by folder na MKV został czysty. `user_settings.py:127-129`
- Override workspace czyta się bezpośrednio z `os.environ["ANISHIFT_WORKSPACE_ROOT"]`, nie przez `Settings` (który by go pominął przez `extra="ignore"`). `workspace.py:32,54`
- System env ma pierwszeństwo nad `.env`; nieznane klucze ignorowane (`extra="ignore"`, `case_sensitive=False`). `settings.py:44-50`
- Zapis preferencji atomowy: `<name>.tmp` + `replace`. `user_settings.py:205-207`
- `load_user_settings` nigdy nie rzuca — brak/nieczytelny/zły-typ/poza-zakresem cicho wraca do defaultów, nieznane klucze odfiltrowane po `__dataclass_fields__`. `user_settings.py:168-197`
- `DEFAULT_SUBDIRS` = dokładnie `("tmp", "output")` — zgodne z regułą „tylko te dwa podfoldery w workspace". `workspace.py:41-44`
- Root repo (`parents[2]` + marker `pyproject.toml`) liczony niezależnie dla configu i dla inferencji workspace. `user_settings.py:124`, `workspace.py:65`

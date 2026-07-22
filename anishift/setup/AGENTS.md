# setup

Pobieranie, weryfikacja SHA256 i instalacja zewnętrznych binarek z manifestu `external/bin_hashes.json`, plus health-checki.

## Pliki

- `installer.py` — download, weryfikacja SHA256, atomowa instalacja
- `manifest.py` — wczytanie i walidacja manifestu `external/bin_hashes.json`
- `doctor.py` — synchroniczne health-checki (lista `CheckResult`)

## Pułapki

- Off-Windows `ensure_resource` dla `kind=="binary"` to cichy no-op — polega na fallbacku PATH w `binaries.py`. `installer.py:327`
- Off-Windows `run_setup` oznacza binarki jako `unavailable` („install via your OS package manager"), nie instaluje. `installer.py:495`
- `_resource_for` mapuje binarkę na zasób po `Path(member.dest).name` z odciętym `.exe` — nazwa pliku docelowego MUSI równać się `Binary.value`, inaczej binarka nie zostanie znaleziona. `installer.py:363`
- `is_installed` uznaje plik o rozmiarze 0 bajtów za brakujący — pusty artefakt wymusza reinstalację. `installer.py:136`
- Przerwany download (`cancelled`) NIE jest błędem instalacji — raportowany jako „will retry on next start" i ponawiany przy następnym starcie. `installer.py:405`
- `check_api_keys` bez skonfigurowanych kluczy zwraca `WARN`, nigdy `FAIL` — brak kluczy nie oblewa doktora. `doctor.py:160`

## Konwencje

- Path-traversal sprawdzany dwukrotnie: przy ładowaniu manifestu (`_parse_member`) i po `resolve()` w `extract_members`. `manifest.py:159`, `installer.py:177`
- Instalacja atomowa: download i ekstrakcja do `tempfile.TemporaryDirectory`, do `dest_root` wchodzi dopiero zweryfikowany plik przez `shutil.move`. `installer.py:240`
- `wait(..., timeout=_WAIT_POLL_SECONDS)` w pętli zamiast blokującego `wait` — by Ctrl+C był responsywny na Windows. `installer.py:456`
- `size_bytes`/`_clean_number` odrzucają `bool` osobnym `isinstance(..., bool)` (bool jest podtypem int). `manifest.py:181`
- `sha256` z manifestu wymuszany na lowercase przy parsowaniu. `manifest.py:196`
- `_MAX_PARALLEL=2` — równoległe pobieranie ograniczone do 2 zasobów naraz. `installer.py:83`

## Decyzje

- Doctor to jeden płaski, synchroniczny moduł (bez `doctor_checks/`, bez async) — checków jest ~6. `doctor.py:1`
- `source` w manifeście to tagged union po `source.type`; dziś tylko `url`, nowe źródło dodaje literal + fetcher, nie nową strukturę. `manifest.py:5,35`
- Dwa wejścia instalacyjne: `ensure_binary`/`ensure_resource` (leniwe, jedna binarka, rzuca) vs `run_setup` (bulk, równolegle, błędy jako wpisy raportu, nigdy nie crashuje). `installer.py:8`
- `ensure_binary` jest jedynym leniwym wejściem dla kodu domenowego etapów 3 (extraction) i 6 (audio). `installer.py:369`
- Jedyny format archiwum to `zip`, jedyny `kind` to `binary`, jedyny `SourceType` to `url` (Literal/frozenset). `manifest.py:32-47`

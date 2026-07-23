# anishift

Pakiet aplikacji. Composition root i hierarchia błędów tutaj; reszta w modułach-dzieciach.

## Moduły (każdy ma własny AGENTS.md)

- `cli/` — REPL, komendy `/`, panel `/settings`, banner
- `pipeline/` — orkiestracja etapów i paski postępu
- `services/` — domeny (extraction, subtitles, translation); wybór silnika przez rejestr w `engines/`
- `setup/` — pobieranie i instalacja zewnętrznych binarek
- `platform/` — kod zależny od systemu (binarki, wykrycie OS)
- `config/` — Settings, preferencje panelu, workspace
- `utils/` — logger, rich_console, timer + przenośne helpery; zero zależności od AniShift

## Luźne pliki

- `bootstrap.py` — composition root
- `errors.py` — hierarchia błędów

## Fakty

- Hierarchia błędów 3-poziomowa: `AniShiftError` → `{Domain}Error` → Specific, plus miksy `TransientError` / `FatalError` do dispatchu retry w silnikach (`isinstance(err, TransientError)`). `errors.py:33-157`
- `ErrorContext` (frozen, slots) niesie `code` + `message` + `suggestion` + `docs_url` + `details`; `AniShiftError` bez `context` buduje domyślny `UNKNOWN`. `errors.py:91-142`
- `bootstrap()` to jedyny composition root — ładuje `.env` (`override=False`), resolves Settings + workspace, zwraca `AppContext`; `create_dirs=False` pomija tworzenie katalogów (testy). `bootstrap.py:42-70`

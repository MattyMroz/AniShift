# anishift

Pakiet aplikacji. Composition root i hierarchia błędów tutaj; reszta w modułach-dzieciach.

## Moduły (każdy ma własny AGENTS.md)

- `application/` — czysty model produktu, planowanie i wykonawcze use case'y dla wszystkich UI
- `cli/` — REPL, komendy `/`, panel `/settings`, banner
- `pipeline/` — orkiestracja ekstrakcji, tłumaczenia, TTS i audio oraz paski postępu
- `services/` — domeny audio, extraction, llm, subtitles, translation i tts
- `text/` — bezdomenowe granice Unicode, skróty i segmentacja grafemów
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
- `bootstrap()` to jedyny composition root — buduje `Settings(_env_file=env_path())`,
  ładuje preferencje panelu, rozwiązuje workspace i zwraca `AppContext`;
  `create_dirs=False` pomija tworzenie katalogów. `bootstrap.py`

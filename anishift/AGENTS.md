# anishift

Pakiet aplikacji. Composition root i hierarchia błędów tutaj; reszta w modułach-dzieciach.

## Moduły (każdy ma własny AGENTS.md)

- `application/` — czysty model produktu, planowanie i wykonawcze use case'y
- `cli/` — Typer entry point: gołe `anishift` otwiera interfejs Prompt Toolkit, plus subkomendy techniczne i `run --preset`
- `services/` — domeny audio, catalog, composition, extraction, fonts, llm, media, subtitles, torrents, translation i tts
- `text/` — bezdomenowe granice Unicode, skróty i segmentacja grafemów
- `setup/` — pobieranie i instalacja zewnętrznych binarek
- `platform/` — kod zależny od systemu (binarki, wykrycie OS)
- `config/` — Settings, preferencje panelu, workspace
- `utils/` — logger, rich_console, timer + przenośne helpery; zero zależności od AniShift

## Luźne pliki

- `bootstrap.py` — composition root
- `errors.py` — hierarchia błędów
- `paths.py` — jedno źródło układu wspólnych katalogów aplikacji: repo, workspace, konfiguracja, stan, binarki i logi. Funkcje tylko wyliczają ścieżki; nie tworzą katalogów. Prywatne pliki i struktury robocze domen pozostają przy swoich modułach. Plik leży poza `config/`, bo import `anishift.config` wciąga rejestry silników.

## Fakty

- Błąd konkretny dziedziczy po `{Domain}Error` i po `TransientError` albo `FatalError`, które służą do dispatchu retry w silnikach (`isinstance(err, TransientError)`). `errors.py`
- `ErrorContext` (frozen, slots) niesie `code` + `message` + `suggestion` + `docs_url` + `details`; `AniShiftError` bez `context` buduje domyślny `UNKNOWN`. `errors.py`
- `bootstrap()` buduje `Settings(_env_file=env_path())`, ładuje preferencje panelu, rozwiązuje workspace i zwraca
  `AppContext` (`create_dirs=False` pomija tworzenie katalogów); `production_service()` składa z niego jedną fasadę
  `AppService` (`create_app_service`). `bootstrap.py`

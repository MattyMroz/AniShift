# docs/reference — materiały referencyjne

Baza wiedzy dla AniShift (materiały historyczne, nie aktywne plany). Aktywne plany etapów: `../plans/`. Pomysły na przyszłość: `../plans/future/`.

## `audyt-mm-avh/` — audyt starego kodu mm_avh

Szczegółowa analiza projektu `mm_avh_working_space` (poprzednik AniShift), na której oparto decyzje przebudowy. Skopiowane z `mm_avh_working_space/docs/brainstorms/audyt/`.

| plik | zawartość |
|---|---|
| `00-mapa-projektu.md` | mapa całego projektu mm_avh |
| `01-root-config.md` | konfiguracja root, pliki startowe |
| `02-modules-ekstrakcja-merge.md` | ekstrakcja MKV + merge (mkvtoolnix) |
| `03-modules-napisy.md` | obsługa napisów (ASS→SRT, refaktor) |
| `04-modules-tts.md` | silniki TTS starego kodu |
| `05-utils.md` | audyt utils/ |
| `06-wzorzec-mangashift.md` | jak mm_avh mapuje się na wzorce MangaShift |
| `07-binarki-vs-python.md` | decyzja: binarki .exe vs biblioteki Python |
| `08-wzorzec-echoreader-tts.md` | wzorzec EchoReader dla TTS (retry, voice_settings) |
| `09-tui-stack.md` | wybór stacku UI (prompt_toolkit + rich) |
| `audyt-pelny.md` | pełny audyt zbiorczy (~320 KB) |
| `wzor-raportu.md` | szablon raportu audytu |

## `mangashift-architecture/` — standardy architektury MangaShift

Wzorce, których AniShift przestrzega (zasada: recykling MangaShift w 100%). Skopiowane z `mm_avh_working_space/docs/mangashift-architecture-ref/`.

Kluczowe: `engine-factory-standard.md` (rejestr silników), `engine-standard.md`, `naming-glossary.md` (nazewnictwo), `pipeline-step-standard.md`, `service-standard.md`, `docelowa-architektura-jedno-zrodlo.md`.

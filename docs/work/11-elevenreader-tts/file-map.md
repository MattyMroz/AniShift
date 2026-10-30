---
kind: file-map
status: draft
baseline: AniShift main f5fff6b; ElevenDownloaderPro stan roboczy z 2026-10-30 (bez zmian); prototyp SCR z 2026-10-30
updated: 2026-10-30
---

# Mapa plików: silnik ElevenReader, głośność i tempo

Operacje: **DODAĆ**, **ZMIENIĆ**, **USUNĄĆ**, **BEZ ZMIAN** (czytać, nie ruszać). Kolumna „Etap” odsyła do
`plan.md` §9. Ścieżki względne wobec roota AniShift. `SCR` i `DATA` jak w `plan.md`.

## 1. Źródła logiki (tylko do odczytu)

### Prototyp `SCR`

| Plik | Co bierzemy | Etap |
|---|---|---|
| `record.py` | kolejność: biblioteka → upload → konto (głos, prędkość 1x) → dokument → Play 64x → nagranie → sprzątanie (głos, tempo, DELETE); wzór, nie kod do skopiowania | E7 |
| `snapcut.py` | reguła cięcia i parametry (`Params`) | E4 |
| `bounds.py` | `load_lines` (podział czasów znaków po `<break>`), `splice_times`, `to_decoded`, `to_server` | E1, E7 |
| `envelope.py` | poziom RMS ramek 10 ms przy 16 kHz, czas ramki na osi serwera | E2, E4 |
| `rebuild_cuts.py` | wycinanie klipów z dekodu 48 kHz | E9 |
| `measure_clips.py` | `speech_span` (−45 dBFS, ramki 10 ms) jako wzór trimu i pomiar „dłuższe niż okno” | E2 |
| `snap-report.md`, `loudness-report.md` | liczby, kryteria i projekt wpięcia | wszystkie |
| `tantei/`, `edge02/`, `edge03/` | nagrania, czasy znaków, wzorcowe cięcia — dane testów zgodności i K1; kopiowane do `DATA` w E0 | E0, E1, E4, K1 |

### ElevenDownloaderPro (cały katalog BEZ ZMIAN; wiedza o trasie, kod piszemy od nowa w standardzie repo)

| Plik | Co bierzemy | Co odpada |
|---|---|---|
| `src/downloader.py` | `launch_chrome`, `connect`, `fresh_page`, `SPEED_JS`, `speed_script`, `Recorder.on_sent/on_frame/write_chunk/repeated_prefix`, `trim_chunk`, `rfind_all`, `Monitor.check_speed`, stałe | klawisze `msvcrt`, dopisywanie do pliku, `print`, `SystemExit`, stały port 9222, `Monitor.report` |
| `src/auto.py` | `button`, `open_library` (bez pętli 120 min), `upload`, `reset_reading_speed`, `Job.start/press_play/step`, `PLAYER_STATE_JS`, stałe czasowe | katalogi `input/done/failed`, `--parallel`, `run_all`, `free_output`, drukowanie komendy wznowienia |
| `src/timestamps.py` | `mp3_duration_ms`, `mp3_cut_ms`, tabele ramek (wiedza dla `utils/mp3_frames.py`) | SRT, JSON, zdania, słowa |
| `src/clips.py` | nic (stara heurystyka zastąpiona przez `SCR:snapcut.py`) | całość |
| `.chrome-profile/`, `.browser-profile/`, `workspace/` | nic — nie otwierać | całość |

## 2. AniShift — pliki dotknięte zmianą

### Utils i tekst

| Ścieżka | Operacja | Zmiana | Etap |
|---|---|---|---|
| `anishift/utils/mp3_frames.py` | DODAĆ | nagłówki ramek z `FrameHeader.duration_ms`, długość, cięcie przed czasem, miejsca sklejeń zgodne z dekoderem FFmpeg, `to_decoded(server_ms, splices, frame_ms)` (długość ramki z pierwszej ramki nagrania, bez stałej) | E1 |
| `anishift/utils/_portable.py`, `anishift/utils/AGENTS.md` | ZMIENIĆ | wpis `mp3_frames.py` | E1 |
| `anishift/text/boundaries.py`, `anishift/text/AGENTS.md` | ZMIENIĆ | `ends_sentence` | E8 |

### Domena audio

| Ścieżka | Operacja | Zmiana | Etap |
|---|---|---|---|
| `anishift/services/audio/mp3.py` | ZMIENIĆ | parser ramek z `utils/mp3_frames.py`; własne tabele usunięte | E1 |
| `anishift/services/audio/levels.py` | DODAĆ | `frame_levels`, `speech_bounds` | E2 |
| `anishift/services/audio/normalize.py` | ZMIENIĆ | trim brzegów po FFmpeg; `_neutral_wav` usunięte | E2 |
| `anishift/services/audio/fingerprint.py` | ZMIENIĆ | normalizacja wersja 2 (`edge_trim`); miks wersja 4 (`narrator_over_source_lu`, limiter) | E2, E3 |
| `anishift/services/audio/commands.py` | ZMIENIĆ | `loudness_command`; komenda dekodu nagrania do mono s16le | E3, E4 |
| `anishift/services/audio/probe.py` | ZMIENIĆ | `measure_integrated_loudness` | E3 |
| `anishift/services/audio/service.py` | ZMIENIĆ | `_render_output`: pomiar i `narrator_gain_db` | E3 |
| `anishift/services/audio/output.py` | ZMIENIĆ | `RenderInputs.narrator_gain_db`, `alimiter … level=0` | E3 |
| `anishift/services/audio/config.py` | ZMIENIĆ | `narrator_mix_base_gain_db` → `narrator_over_source_lu = 7.5` | E3 |
| `anishift/services/audio/segmentation.py` | DODAĆ | reguła cięcia (`cut_points`) | E4 |
| `anishift/services/audio/AGENTS.md` | ZMIENIĆ | trim, pomiar głośności, limiter, cięcie | E2–E4 |
| `anishift/services/audio/{timeline,types}.py` | ZMIENIĆ | martwa ścieżka `PcmStorage.WAV` (`_copy_wav`) usunięta po zniknięciu `_neutral_wav` | E2 |
| `anishift/services/audio/{channels,resume,transcode}.py` | BEZ ZMIAN | — | — |

### Domena TTS

| Ścieżka | Operacja | Zmiana | Etap |
|---|---|---|---|
| `anishift/services/tts/types.py` | ZMIENIĆ | `max_document_chars`; `DocumentPart`, `DocumentSynthesisRequest`, `PartTiming`, `EngineDocumentResult`, `ClipSpan`, `SplitResult` | E5 |
| `anishift/services/tts/protocols.py` | ZMIENIĆ | `DocumentTtsEngine` (`document_chars`, `synthesize_document`), `ClipSplitter` | E5 |
| `anishift/services/tts/scheduler.py` | ZMIENIĆ | `submit(call=…)`, `ScheduledSynthesis.result`, `TtsQuotaError` w circuit, konstruktor z `locality` zamiast silnika | E5 |
| `anishift/services/tts/service.py` | ZMIENIĆ | `_run_document_batch` (grupowanie przez `engine.document_chars`, sprzątanie poprzedniej próby), parametr `splitter` | E5 |
| `anishift/services/tts/errors.py`, `anishift/errors.py` | ZMIENIĆ | `TtsQuotaError`, `ErrorCode.TTS_QUOTA_EXHAUSTED` | E5 |
| `anishift/services/tts/config.py` | ZMIENIĆ | `elevenreader_profile_root` | E5 |
| `anishift/services/tts/__init__.py`, `AGENTS.md` | ZMIENIĆ | eksport, kontrakt dokumentu | E5 |
| `anishift/services/tts/engines/__init__.py`, `engines/AGENTS.md` | ZMIENIĆ | `elevenreader` w rejestrze, `is_document_engine` | E7 |
| `anishift/services/tts/engines/elevenreader/` | DODAĆ | pakiet silnika (§3) | E7 |
| `anishift/services/tts/{chunking,validation,fingerprint,resume,artifacts,cancellation}.py` | BEZ ZMIAN | używane przez ścieżkę dokumentu | — |
| `anishift/services/tts/engines/{edge,elevenbytes,elevenlabs,sapi}/` | BEZ ZMIAN | I1 | — |

### Platforma

| Ścieżka | Operacja | Zmiana | Etap |
|---|---|---|---|
| `anishift/platform/installed.py` | DODAĆ | `find_installed(locations, stem)` | E6 |
| `anishift/platform/private_dir.py` | DODAĆ | `restrict_directory(root)` z kodu `_protect_profile` | E6 |
| `anishift/platform/qbittorrent_config.py` | ZMIENIĆ | `installed_executable` przez `find_installed` | E6 |
| `anishift/platform/qbittorrent_process.py` | ZMIENIĆ | `_protect_profile` przez `restrict_directory` | E6 |
| `anishift/platform/AGENTS.md` | ZMIENIĆ | dwa nowe moduły | E6 |
| `anishift/platform/process_lock.py` | BEZ ZMIAN | blokada profilu Chrome | — |

### Aplikacja, konfiguracja, CLI, setup

| Ścieżka | Operacja | Zmiana | Etap |
|---|---|---|---|
| `anishift/application/tts_handler.py` | ZMIENIĆ | łączenie kwestii urwanych w `_narration_batch` za flagą `join_open_lines` | E8 |
| `anishift/application/planning.py` | ZMIENIĆ | pole snapshotu `narrator_over_source_lu` | E3 |
| `anishift/application/runtime.py` | ZMIENIĆ | `_audio_config` (E3); `join_open_lines=False` (E8); `_tts_config`, `splitter`, `join_open_lines=is_document_engine(...)` (E9) | E3, E8, E9 |
| `anishift/application/service.py` | ZMIENIĆ | snapshot (E3); głosy, `tts_is_paid`, sesja i logowanie ElevenReader (E9) | E3, E9 |
| `anishift/application/__init__.py` | ZMIENIĆ | eksport DTO sesji | E9 |
| `anishift/application/tts_clips.py` | ZMIENIĆ | `split_clip`, `recording_timeout_s` | E9 |
| `anishift/application/AGENTS.md` | ZMIENIĆ | łączenie kwestii, splitter | E8, E9 |
| `anishift/paths.py` | ZMIENIĆ | `elevenreader_dir()` | E9 |
| `anishift/config/user_settings.py` | ZMIENIĆ | pole `narrator_over_source_lu`, Dallin offset 0 (E3); gałąź `elevenreader`, profile, reset obcego aliasu (E9) | E3, E9 |
| `anishift/config/field_catalog.py` | ZMIENIĆ | pole głośności (E3); modele, głosy, profile `elevenreader` (E9) | E3, E9 |
| `anishift/config/AGENTS.md` | ZMIENIĆ | aliasy głosów między silnikami | E9 |
| `anishift/cli/interactive/settings.py` | ZMIENIĆ | „Głośność lektora” w LU (E3); etykieta silnika, sekcja SESJA (E9) | E3, E9 |
| `anishift/cli/AGENTS.md` | ZMIENIĆ | akcja logowania | E9 |
| `anishift/setup/doctor.py`, `anishift/setup/AGENTS.md` | ZMIENIĆ | `check_elevenreader()` | E9 |
| `.gitignore` | ZMIENIĆ | `config/elevenreader/` | E0 |
| `pyproject.toml`, `uv.lock` | ZMIENIĆ (tylko `uv add playwright`) | `playwright` | E7 |
| `config/README.md`, `docs/reference/settings.md` | ZMIENIĆ | katalog `elevenreader/`, silnik, głośność w LU | E9 |
| `README.md`, `README.pl.md`, `docs/README.md`, `docs/ideas.md` | ZMIENIĆ | silnik, logowanie, ryzyko; status workstreamu | E10 |
| `scripts/tmp/migrate_narrator_loudness.py` | DODAĆ i USUNĄĆ | jednorazowa migracja `config/settings.json` (nie commitowana) | E3 |

### Testy

| Ścieżka | Operacja | Etap |
|---|---|---|
| `tests/utils/test_mp3_frames.py` (nowy katalog bez `__init__.py`) | DODAĆ | E1 |
| `tests/services/audio/test_audio_mp3.py` | BEZ ZMIAN zachowania | E1 |
| `tests/services/audio/test_audio_levels.py` | DODAĆ | E2 |
| `tests/services/audio/test_audio_normalize.py`, `test_audio_fingerprint.py`, `test_audio_timeline.py` | ZMIENIĆ | E2, E3 |
| `tests/services/audio/test_audio_channels_output.py`, testy `probe`, `commands`, `service` | ZMIENIĆ | E3 |
| `tests/services/audio/test_audio_segmentation.py` (w tym test zgodności z `DATA`) | DODAĆ | E4 |
| `tests/application/test_runtime_config.py`, `tests/config/test_user_settings.py`, `tests/config/test_field_catalog.py`, `tests/cli/test_interactive_settings_steps.py` | ZMIENIĆ | E3, E9 |
| `tests/services/tts/test_tts_scheduler.py`, `test_tts_service.py`, `test_tts_contract.py` | ZMIENIĆ | E5 |
| `tests/services/tts/test_tts_document_service.py` | DODAĆ | E5 |
| `tests/platform/test_installed.py`, `test_private_dir.py` | DODAĆ | E6 |
| `tests/services/tts/test_tts_elevenreader_{config,api_backend,recorder,service,service_data,network}.py`, `elevenreader_fakes.py` | DODAĆ | E7 |
| `tests/services/tts/test_tts_registry.py` | ZMIENIĆ | E7 |
| `tests/text/test_boundaries.py`, `tests/application/test_tts_handler.py` | ZMIENIĆ | E8 |
| `tests/application/test_tts_clips_split.py` | DODAĆ | E9 |
| `tests/setup/test_doctor.py`, `tests/cli/test_interactive_settings_*.py`, `tests/test_paths.py` | ZMIENIĆ | E9 |

## 3. Drzewo nowego silnika

```text
anishift/services/tts/engines/elevenreader/
├── AGENTS.md        # NEW
├── __init__.py      # NEW  bez importu playwright
├── constants.py     # NEW  URL-e, endpointy, stałe EDP, skrypty JS, VOICES
├── config.py        # NEW  ElevenReaderConfig.from_tts_config, resolve_voice, find_chrome, ścieżki profilu
├── types.py         # NEW  głos, stany biblioteki i logowania, SessionRecord, AccountCleanup, UploadedRead,
│                    #      PlayerState, AlignmentChunk
├── api_backend.py   # NEW  karta Playwright (leniwie): mapowanie statusów HTTP i błędów Playwright, ReaderPage
│                    #      (biblioteka, upload, dokument, Play, odtwarzacz, prędkość strony), user_config i
│                    #      DELETE dokumentu, session.json, require_signed_in, sign_in
├── browser.py       # NEW  specyficzny: Chrome + CDP, blokada i ACL profilu, ChromeMissingError, ChromeBusyError
├── recorder.py      # NEW  specyficzny: ramki WS → MP3 + czasy znaków
└── service.py       # NEW  ElevenReaderTtsEngine, document_text, part_spans (czasy kwestii po tagach <break>)
```

Runtime (gitignored):

```text
config/elevenreader/        # ACL: tylko bieżące konto
├── chrome-profile/         # profil Chrome z sesją
├── chrome.lock             # ProcessLock: jedna przeglądarka na profil
└── session.json            # {"signed_in": bool, "checked_at": ISO-8601}
```

Staging przebiegu (istniejący układ `TtsResumeRepository` pod `workspace/tmp/`): nagranie dokumentu jako
`clips/.clip-*.mp3.tmp`, wycięte klipy jako `clips/.clip-*.wav.tmp`, zatwierdzone `clips/clip-<key>.wav`,
`manifest.json`. Pliki dekodu dla cięcia w `TemporaryDirectory(prefix="anishift-split-")`, usuwane przed powrotem.

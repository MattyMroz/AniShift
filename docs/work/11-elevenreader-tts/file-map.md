---
kind: file-map
status: draft
baseline: AniShift main 4365a51; ElevenDownloaderPro stan roboczy z 2026-10-25 (bez zmian)
updated: 2026-10-25
---

# Mapa plików: silnik ElevenReader

Operacje: **DODAĆ**, **ZMIENIĆ**, **ZREFAKTORYZOWAĆ** (zmiana struktury bez zmiany zachowania),
**USUNĄĆ**, **BEZ ZMIAN** (czytać, nie ruszać). Ścieżki względne wobec roota repozytorium.

## 1. ElevenDownloaderPro — źródło logiki (cały katalog: BEZ ZMIAN)

Repozytorium jest tylko źródłem do przeczytania. Stan: ostatni commit `7e3fd94`, a `src/auto.py`, `src/clips.py`,
`src/timestamps.py` i `docs/` nie są zacommitowane (`docs/report.md:87`). Wykonawca czyta pliki z dysku, nie z
historii gita.

| Ścieżka | Rola | Co bierzemy do AniShift | Co odpada |
|---|---|---|---|
| `README.md` | opis użycia, pomiary, ostrzeżenia | fakty: szybkość, kolejność, cache, timeouty | instrukcje Tampermonkey |
| `docs/report.md` | raport końcowy EDP (2026-10-18) | fakty o formacie, limitach, ryzykach | lista błędów autora |
| `docs/research/capabilities.md` | pola HTTP/WS, kalkulator kosztu, ryzyka | pola ramek, `char_count`, koszty, ryzyka | pomysły audiobook/EPUB |
| `docs/research/elevenreader-tags.md` | test znaczników tekstu | reguła: bez znaczników, nawiasy neutralizowane | cała reszta |
| `pyproject.toml` | zależności `playwright>=1.64.0`, `miniaudio>=1.71` | wersja Playwright jako punkt odniesienia | `miniaudio` (AniShift dekoduje FFmpeg) |
| `uv.lock` | lock EDP | nic | całość |
| `script.js` | userscript Tampermonkey: przejęcie `AudioContext` i `WebSocket` w stronie | nic (wiedza: przyspieszenie przez `playbackRate`) | całość |
| `src/downloader.py` | ręczne nagrywanie: Chrome + CDP, `Recorder`, `Monitor`, klawisze `msvcrt` | `launch_chrome`, `connect`, `fresh_page`, `SPEED_JS`, `Recorder.on_frame/write_chunk/repeated_prefix`, `trim_chunk`, `rfind_all`, kontrola prędkości z `Monitor.check_speed` | klawisze, dopisywanie do pliku, `print`, `SystemExit`, statusy MB |
| `src/auto.py` | automatyczny upload i nagrywanie z katalogów | `upload`, `open_library` (krócej), `set_reading_speed`, `Job.start/press_play/step`, stałe czasowe | katalogi `input/done/failed`, `--parallel`, `free_output`, podpowiedź `downloader.py` |
| `src/timestamps.py` | czasy znaków → SRT/JSON, ramki MP3 | `mp3_frames`, `mp3_duration_ms`, `mp3_cut_ms` (jako wiedza dla `utils/mp3_frames.py`), `load_timeline`, `BREAK_TAG` | SRT, JSON, zdania, słowa |
| `src/clips.py` | cięcie nagrania na klipy według SRT | `normalize_timeline`, `find_line`, `find_anchored`, `locate_lines`, `silences`, `estimate_delay`, `find_boundaries`, `place_in_run`, `quietest_dip`, `pad_in_gaps`, `snap_lines`, `frame_table`, `cut_frames`, `stream_ranges` | parser SRT, `prepare`, `verify`, CLI, `miniaudio` |
| `workspace/output/lektor_pl*.{mp3,align.jsonl,txt}` | prawdziwe nagrania lektora właściciela (2026-10-24) | materiał do eksperymentu dryfu i testu cięcia — tylko lokalnie, kopia do zbioru poza repo | nigdy do repo (głos `famous`) |
| `.chrome-profile/`, `.browser-profile/` | profile Chrome z sesją konta | nic — nie otwierać | całość |
| `.agents/`, `.claude/`, `__pycache__/`, `.venv/` | narzędzia | nic | całość |

## 2. AniShift — pliki dotknięte zmianą

### Domena TTS

| Ścieżka | Rola dziś | Operacja | Co się zmienia |
|---|---|---|---|
| `anishift/services/tts/types.py` | typy neutralne | ZMIENIĆ | `EngineCapabilities.max_document_chars: int \| None = None`; nowe `DocumentPart`, `DocumentSynthesisRequest`, `PartTiming`, `EngineDocumentResult`, `ClipSpan`, `SplitResult` |
| `anishift/services/tts/protocols.py` | protokoły silnika, walidatora, assemblera | ZMIENIĆ | `DocumentTtsEngine`, `ClipSplitter` |
| `anishift/services/tts/scheduler.py` | retry, circuit, timeout prób | ZREFAKTORYZOWAĆ | `submit` przyjmuje wywołanie próby (`call`) zamiast budować żądanie i samemu wołać `engine.synthesize`; generyczny wynik |
| `anishift/services/tts/service.py` | fasada, ścieżka per kwestia | ZMIENIĆ | ścieżka dokumentu `_run_document_batch`; parametr `splitter`; dotychczasowa ścieżka używa nowego `submit` |
| `anishift/services/tts/errors.py` | hierarchia błędów TTS | ZMIENIĆ | `TtsQuotaError(TtsError, FatalError)` |
| `anishift/services/tts/scheduler.py` (`_opens_circuit`) | warunek circuit | ZMIENIĆ | `TtsQuotaError` otwiera circuit |
| `anishift/services/tts/config.py` | `TtsConfig` | ZMIENIĆ | `elevenreader_profile_root: Path \| None = None`, `elevenreader_email`, `elevenreader_password` (`repr=False`, puste domyślnie) |
| `anishift/services/tts/__init__.py` | eksport publiczny | ZMIENIĆ | eksport nowych typów, protokołów i `TtsQuotaError` |
| `anishift/services/tts/engines/__init__.py` | rejestr | ZMIENIĆ | `TtsEngineId` i `_REGISTRY` z `elevenreader` |
| `anishift/services/tts/AGENTS.md` | reguły domeny | ZMIENIĆ | kontrakt dokumentu, `ClipSplitter`, scheduler `call` |
| `anishift/services/tts/engines/AGENTS.md` | reguły rejestru | ZMIENIĆ | kolejność i opis `elevenreader/` |
| `anishift/services/tts/engines/elevenreader/` | — | DODAĆ | nowy pakiet silnika (drzewo w sekcji 3) |
| `anishift/services/tts/chunking.py`, `validation.py`, `fingerprint.py`, `resume.py`, `artifacts.py`, `cancellation.py` | wspólne mechanizmy | BEZ ZMIAN | używane przez ścieżkę dokumentu |
| `anishift/services/tts/engines/{edge,elevenbytes,elevenlabs,sapi}/` | istniejące silniki | BEZ ZMIAN | inwariant I1 |

### Domena audio i utils

| Ścieżka | Rola dziś | Operacja | Co się zmienia |
|---|---|---|---|
| `anishift/utils/mp3_frames.py` | — | DODAĆ | jedno źródło parsowania nagłówka ramki MPEG: `parse_frame_header`, `iter_frames`, `frames_duration_ms`, `cut_before_ms` |
| `anishift/utils/_portable.py` | manifest przenośności | ZMIENIĆ | wpis `mp3_frames.py` |
| `anishift/utils/AGENTS.md` | mapa utils | ZMIENIĆ | wpis `mp3_frames.py` |
| `anishift/services/audio/mp3.py` | inspekcja strumienia MP3 | ZREFAKTORYZOWAĆ | `_parse_frame_header` i tabele bitrate zastąpione `utils/mp3_frames.py`; dodane `frame_table` i `cut_frames` |
| `anishift/services/audio/segmentation.py` | — | DODAĆ | czysty algorytm: obwiednia głośności, cisze, opóźnienie, granice, padding (port z `src/clips.py`) |
| `anishift/services/audio/commands.py` | komendy FFmpeg | ZMIENIĆ | `envelope_wav_command` (mono 16 kHz PCM WAV) |
| `anishift/services/audio/AGENTS.md` | reguły audio | ZMIENIĆ | segmentacja i cięcie ramkami |
| `anishift/application/tts_clips.py` | `FfmpegClipService`: walidacja, sklejanie | ZMIENIĆ | `split_clip` — implementacja `ClipSplitter` |

### Aplikacja, konfiguracja, platforma, CLI, setup

| Ścieżka | Rola dziś | Operacja | Co się zmienia |
|---|---|---|---|
| `anishift/paths.py` | układ katalogów | ZMIENIĆ | `elevenreader_dir()` = `config_dir() / "elevenreader"` |
| `.gitignore` | ignorowane pliki | ZMIENIĆ (faza 0, przed pierwszym plikiem profilu) | `config/elevenreader/` |
| `config/README.md` | opis `config/` | ZMIENIĆ | akapit o `elevenreader/` |
| `anishift/platform/installed.py` | — | DODAĆ | `find_installed(locations, stem)` — wspólne wyszukiwanie zainstalowanego programu |
| `anishift/platform/qbittorrent_config.py` | `installed_executable` | ZREFAKTORYZOWAĆ | używa `find_installed` |
| `anishift/platform/private_dir.py` | — | DODAĆ | `restrict_directory(root)` — ACL tylko dla bieżącego konta (przeniesione z `qbittorrent_process._protect_profile`) |
| `anishift/platform/qbittorrent_process.py` | `_protect_profile` | ZREFAKTORYZOWAĆ | woła `restrict_directory`, mapuje błąd na dotychczasowy |
| `anishift/platform/AGENTS.md` | reguły platformy | ZMIENIĆ | dwa nowe moduły |
| `anishift/platform/process_lock.py` | `ProcessLock` | BEZ ZMIAN | blokada profilu Chrome |
| `anishift/application/runtime.py` | budowa handlerów | ZMIENIĆ | `_tts_config` (timeout, backoff, profil, dane logowania), `_tts_handler` (wstrzyknięcie `splitter`) |
| `anishift/application/service.py` | fasada `AppService` | ZMIENIĆ | `_tts_allowed_voice_ids`, `tts_is_paid`, `elevenreader_sign_in()`, `elevenreader_session()`, DTO `ElevenReaderSession`, `ElevenReaderSignIn` |
| `anishift/application/__init__.py` | publiczna fasada aplikacji | ZMIENIĆ | eksport dwóch DTO (panel importuje tylko fasadę) |
| `anishift/application/tts_handler.py` | adapter zadania TTS | BEZ ZMIAN | kontrakt wsadów bez zmian |
| `anishift/application/planning.py`, `planner.py` | snapshot, zasoby | BEZ ZMIAN | `resource_key=tts:<profil>` już serializuje pliki |
| `anishift/config/settings.py` | `Settings` z `.env` | ZMIENIĆ | `elevenreader_email`, `elevenreader_password` (`repr=False`) — tylko w gałęzi logowania danymi (D2) |
| `anishift/config/user_settings.py` | preferencje panelu | ZMIENIĆ | gałąź `elevenreader` w normalizacji, etykiecie i rozwiązywaniu głosu; profile domyślne dwóch głosów; reset aliasów obcego silnika |
| `anishift/config/field_catalog.py` | katalog pól | ZMIENIĆ | modele/głosy/profile `elevenreader`; ukryta współbieżność; specyfikacje sekretów (gałąź D2) |
| `anishift/config/AGENTS.md` | reguły config | ZMIENIĆ | pułapka aliasów głosów między silnikami |
| `anishift/cli/interactive/settings.py` | ekran Ustawień | ZMIENIĆ | etykieta silnika, wiersz akcji „Zaloguj / sprawdź sesję”, wiersz stanu sesji, połączenie ElevenReader (gałąź D2) |
| `anishift/cli/AGENTS.md` | reguły CLI | ZMIENIĆ | akcja logowania ElevenReader |
| `anishift/setup/doctor.py` | health-checki | ZMIENIĆ | `check_elevenreader()` |
| `anishift/setup/AGENTS.md` | reguły setup | ZMIENIĆ | opis checku |
| `pyproject.toml`, `uv.lock` | zależności | ZMIENIĆ (tylko przez `uv add playwright`) | `playwright` |
| `docs/reference/settings.md` | opis ustawień | ZMIENIĆ | silnik i głosy ElevenReader |
| `README.md`, `README.pl.md` | instrukcja | ZMIENIĆ | akapit o silniku, logowaniu i ryzyku |
| `docs/ideas.md` | pomysły | ZMIENIĆ | wpis „Lektor przez ElevenReader” → status i link do workstreamu |
| `docs/README.md` | mapa workstreamów | ZMIENIĆ | wiersz `11-elevenreader-tts` |

### Testy

| Ścieżka | Operacja | Zakres |
|---|---|---|
| `tests/utils/test_mp3_frames.py` | DODAĆ | nagłówki, ID3, przerwy, długość, cięcie |
| `tests/services/audio/test_audio_mp3.py` | ZMIENIĆ | `frame_table`, `cut_frames`; dotychczasowe testy bez zmian |
| `tests/services/audio/test_audio_segmentation.py` | DODAĆ | cisze, opóźnienie, granice bez ciszy, padding |
| `tests/application/test_tts_clips_split.py` | DODAĆ | `split_clip` z prawdziwym FFmpeg na syntetycznym MP3 (`integration`) |
| `tests/services/tts/test_tts_scheduler.py` | ZMIENIĆ | nowe `submit(call=...)`; te same scenariusze |
| `tests/services/tts/test_tts_service.py` | ZMIENIĆ | dotychczasowe scenariusze na nowym `submit` |
| `tests/services/tts/test_tts_document_service.py` | DODAĆ | ścieżka dokumentu: resume, brakujące kwestie, retry, circuit, postęp, limit dokumentu |
| `tests/services/tts/test_tts_contract.py` | ZMIENIĆ | pola nowych typów, protokoły, brak zakazanych importów |
| `tests/services/tts/test_tts_registry.py` | ZMIENIĆ | `EXPECTED_ENGINE_IDS` z `elevenreader` |
| `tests/services/tts/elevenreader_fakes.py` | DODAĆ | fałszywe strony, ramki, przeglądarka (bez prozy) |
| `tests/services/tts/test_tts_elevenreader_config.py` | DODAĆ | aliasy, model, współbieżność, profil |
| `tests/services/tts/test_tts_elevenreader_document.py` | DODAĆ | budowa dokumentu, neutralizacja nawiasów |
| `tests/services/tts/test_tts_elevenreader_recorder.py` | DODAĆ | ramki, duplikaty, ponowne połączenie, kompletność |
| `tests/services/tts/test_tts_elevenreader_alignment.py` | DODAĆ | oś czasu, lokalizacja kwestii, kotwice |
| `tests/services/tts/test_tts_elevenreader_errors.py` | DODAĆ | mapowanie statusów HTTP na błędy TTS |
| `tests/services/tts/test_tts_elevenreader_engine.py` | DODAĆ | silnik na fałszywej przeglądarce: błędy, anulowanie, głos, sesja |
| `tests/services/tts/test_tts_elevenreader_network.py` | DODAĆ | `network`, zgoda przez zmienną środowiska, krótki dokument |
| `tests/data/elevenreader/frames-anon.jsonl` | DODAĆ | nagrane ramki z audio zastąpionym syntetycznym MP3 |
| `tests/platform/test_installed.py`, `tests/platform/test_private_dir.py` | DODAĆ | wspólne helpery platformy |
| `tests/platform/test_qbittorrent_config.py`, `test_qbittorrent_process.py` | BEZ ZMIAN (mają przejść) | regresja refaktoru |
| `tests/config/test_user_settings.py`, `tests/config/test_field_catalog.py` | ZMIENIĆ | gałąź `elevenreader`, reset aliasów |
| `tests/cli/test_interactive_settings_*.py` | ZMIENIĆ | wiersze akcji i etykiety |
| `tests/setup/test_doctor.py` | ZMIENIĆ | `check_elevenreader` |
| `tests/application/test_runtime_config.py` | ZMIENIĆ | `_tts_config` dla `elevenreader` |
| `tests/test_paths.py` | ZMIENIĆ | `elevenreader_dir` |

## 3. Docelowe drzewo nowego silnika

```text
anishift/services/tts/engines/elevenreader/
├── AGENTS.md          # NEW  pułapki: CDP, profil, blokada, głos, sekrety, brak retry w transporcie
├── __init__.py        # NEW  eksport ElevenReaderTtsEngine, ElevenReaderConfig, sign_in, read_session
├── constants.py       # NEW  URL-e, fragmenty endpointów, stałe czasowe, aliasy i ID głosów, skrypty JS
├── config.py          # NEW  ElevenReaderConfig.from_tts_config, resolve_voice
├── document.py        # NEW  budowa tekstu dokumentu z kwestii, neutralizacja, podział na dokumenty
├── recorder.py        # NEW  czyste parsowanie ramek WS: audio, alignment, duplikaty, ponowne połączenie
├── alignment.py       # NEW  oś czasu znaków, lokalizacja kwestii → PartTiming
├── browser.py         # NEW  Chrome + CDP: start, port, blokada profilu, ACL, zamknięcie
├── page.py            # NEW  akcje strony: biblioteka, upload, otwarcie, prędkość, głos, Play, stan
├── session.py         # NEW  wykrycie zalogowania, logowanie interaktywne, opcjonalne logowanie danymi, session.json
├── errors.py          # NEW  mapowanie statusów HTTP i stanów strony na błędy TTS
└── service.py         # NEW  ElevenReaderTtsEngine (DocumentTtsEngine)
```

Runtime (gitignored, poza repozytorium kodu):

```text
config/elevenreader/   # ACL: tylko bieżące konto
├── chrome-profile/    # profil Chrome z sesją (cookies)
├── profile.lock       # ProcessLock: jedna przeglądarka na profil
└── session.json       # {"signed_in": bool, "checked_at": ISO-8601} — bez sekretów
```

Staging przebiegu (istniejący mechanizm, bez zmian układu):

```text
workspace/temp/<run_id>/tts/<group_id>/tts/   # TtsResumeRepository (runtime.py: resume_root=run_root/"tts")
├── clips/.clip-*.mp3.tmp                     # tymczasowe: nagranie dokumentu i wycięte klipy
├── clips/clip-<key>.mp3                      # zatwierdzone klipy kwestii (artifacts.py:95)
└── manifest.json                             # resume per kwestia (artifacts.py:48-50)
```

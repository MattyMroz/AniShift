---
kind: plan
status: draft
baseline: AniShift main 4365a51 (merge PR #66), czyste drzewo; ElevenDownloaderPro stan roboczy 2026-10-25
created: 2026-10-25
---

# Plan: silnik lektora ElevenReader w AniShift

Plan jest samowystarczalnym kontraktem dla świeżego wykonawcy. Wymagania (`F*`, `N*`), inwarianty (`I*`),
ograniczenia (`O*`), zakazy (`Z*`) i decyzje (`D*`) pochodzą z `specification.md`; tu są tylko odwołania. Mapa
plików: `file-map.md`. Intencja: `intent.md`.

Skróty: **EDP** = repozytorium `C:\Users\MattyMroz\Desktop\PROJECTS\ElevenDownloaderPro` (tylko do odczytu). Ścieżki
EDP zaczynają się od `EDP:`; ścieżki bez prefiksu są w AniShift. Numery linii odnoszą się do stanu z 2026-10-25
(AniShift `4365a51`; EDP stan roboczy na dysku, bo trzy pliki `src/` nie są zacommitowane).

## 1. Cel

Dodać do AniShift silnik TTS `elevenreader`, który czyta polskie kwestie odcinka głosem Piotra Fronczewskiego albo
Adama z ElevenReadera (Eleven v4), przez prawdziwy Chrome z zalogowaną sesją, z cięciem nagrania na klipy kwestii.
Silnik działa w Auto, Ręcznym i subskrypcjach bez zmian w ich przepływie. `elevenbytes` zostaje zapasem.

## 2. Rezultat użytkownika

- Ustawienia → Lektor → Silnik: „ElevenReader”. Głos: „Piotr Fronczewski” albo „Adam”.
- Ustawienia → Lektor → „Zaloguj / sprawdź sesję”: otwiera okno Chrome, po zalogowaniu pokazuje „✓ Zalogowano”.
- Przetwarzanie odcinka pokazuje postęp syntezy rosnący z odbieranym tekstem.
- Wygasła sesja, brak kredytów albo blokada konta kończą syntezę komunikatem po polsku z jedną akcją naprawczą.
- `anishift doctor` mówi, czy Chrome jest dostępny i czy sesja była ostatnio ważna.
- Przełączenie silnika na „ElevenBytes” przywraca dotychczasowy lektor.

## 3. Warunki końcowe

- [ ] Rejestr zawiera `elevenreader`; testy rejestru i kontraktu przechodzą (F1, I2).
- [ ] Ścieżka dokumentu w `TtsService` przechodzi testy resume, brakujących kwestii, retry, circuit i postępu (F2–F4, N7).
- [ ] `FfmpegClipService.split_clip` tnie syntetyczne nagranie w ciszy (U5, N2).
- [ ] Silnik przechodzi testy na fałszywej przeglądarce: błędy, anulowanie, głos, sesja (F7, F8, F15, F16, F20–F22, N4).
- [ ] Panel i `doctor` obsługują silnik (F9–F14, F17–F19).
- [ ] Bramki S1 zielone; test sieciowy S2 uruchomiony przez właściciela; checkpoint ucha S3 zaakceptowany.
- [ ] Powrót na `elevenbytes` sprawdzony (S4); review krzyżowe bez findingów krytycznych i poważnych (S5); skan
      sekretów czysty (S6).

## 4. Nie-cel

Najbliższa podobna rzecz poza planem: etap 6 jakości (głośność lektora). Plan dostarcza tylko korektę głośności per
głos, istniejącą dziś dla każdego profilu (`anishift/config/field_catalog.py:1004-1013`). Pomiar i automatyczne
dopasowanie głośności zostają w `docs/work/10-quality/masterplan.md` etap 6.

## 5. Authority i baseline

| Źródło | Rola |
|---|---|
| `specification.md` | wymagania, zakazy, decyzje |
| `intent.md` | potrzeba i odrzucone drogi |
| `AGENTS.md` (root), `anishift/AGENTS.md`, `tests/AGENTS.md` | reguły repo |
| `anishift/services/tts/AGENTS.md`, `anishift/services/tts/engines/AGENTS.md` i AGENTS.md silników | granice domeny TTS |
| `anishift/services/audio/AGENTS.md` | granice domeny audio |
| `anishift/config/AGENTS.md`, `anishift/cli/AGENTS.md`, `anishift/setup/AGENTS.md`, `anishift/platform/AGENTS.md`, `anishift/application/AGENTS.md` | reguły dotkniętych obszarów |
| `.agents/skills/coding/references/python.md`, `comments-docstrings` w `coding/SKILL.md`, sekcja „Testy i dowody” | standard kodu |
| kod AniShift na `4365a51` | stan aktualny |
| kod i dokumenty EDP | źródło logiki trasy, stan aktualny EDP |
| faza 0 tego planu | brakujące fakty o ElevenReaderze |

**Baseline:** `main` na `4365a51`, czyste drzewo; rezydent AniShift działa z tego checkoutu.

**Znane wcześniejsze failures:** nieznane. Faza 0 uruchamia bramki na baseline i zapisuje wynik przed pierwszą
zmianą. Każdy failing test z baseline jest wymieniony z nazwą w raporcie fazy 0 i nie jest „naprawiany” w tym
planie bez decyzji orkiestratora.

## 6. Stan aktualny: jak naprawdę działa ElevenDownloaderPro

### 6.1. Co jest w repozytorium

- Dwa niezależne narzędzia: stary userscript `EDP:script.js` (Tampermonkey) i narzędzia Pythona w `EDP:src/`
  (`EDP:README.md:1-12`, `:34-38`).
- `EDP:pyproject.toml`: `requires-python = ">=3.14"`, zależności `miniaudio>=1.71`, `playwright>=1.64.0`; brak
  `build-system`, więc to nie jest instalowalny pakiet.
- Moduły importują się płasko, przez katalog skryptu na `sys.path`: `from timestamps import ...`
  (`EDP:src/downloader.py:31`), `from downloader import ...` (`EDP:src/auto.py:23-37`).
- Trzy z czterech plików `src/` nie są w historii gita (`EDP:docs/report.md:87`: „Nic nie jest zacommitowane”;
  status roboczy pokazuje `?? src/auto.py`, `?? src/clips.py`, `?? src/timestamps.py`).

### 6.2. Endpointy i protokół

| Element | Wartość | Źródło |
|---|---|---|
| strona biblioteki | `https://elevenreader.io/reader/library` | `EDP:src/auto.py:53` |
| dokument | `https://elevenreader.io/reader/library/{read_id}` | `EDP:src/auto.py:169` |
| upload | `POST .../v1/reader/reads/add/v2`, odpowiedź JSON z `read_id`, `char_count` | `EDP:src/auto.py:56`, `:141-145` |
| strumień | `wss://api.elevenlabs.io/v1/reader/reads/stream/v2/{read_id}` | `EDP:docs/research/capabilities.md:18` |
| ramki klienta | `listening_speed`, `position`, `listening_position`, `stream_id` | `EDP:docs/research/capabilities.md:22-25` |
| ramki serwera | `type: "config"` (`maxReadingSpeed`), `audio`, `alignment.chars`, `alignment.charStartTimesMs`, `alignment.charDurationsMs`, `isFinal` | `EDP:docs/research/capabilities.md:26-31` |
| dodatkowe odczyty strony | `GET reads/{id}`, `GET customer` (`current_credits`), `GET user_config` (`playback_speed_rate`, `voice_expressiveness`, `default_voice_id`, `feature_flags`), `GET voices` | `EDP:docs/research/capabilities.md:42-66` |

Protokół jest wewnętrzny i nieudokumentowany; `stream/v2` stoi za flagą `stream_read_v2_enabled`
(`EDP:docs/research/capabilities.md:154`). EDP **nie wysyła żadnych własnych żądań**: upload robi kliknięciem w
interfejs, a dane czyta z ruchu, który strona i tak wykonuje (`EDP:docs/research/capabilities.md:152`).

Przebieg jednego dokumentu w `EDP:src/auto.py`:

1. `open_library` otwiera bibliotekę i czeka na widoczny przycisk „Import” do 45 s; przy awarii serwisu ponawia
   co minutę do 120 minut (`EDP:src/auto.py:121-134`, stałe `:65-69`).
2. `upload`: klik „Import”, `set_input_files` na `input[type=file]`, klik „Upload”, przechwycenie odpowiedzi
   `add/v2` (`EDP:src/auto.py:137-145`).
3. `Job.start`: podpięcie nasłuchu WebSocket, `goto` do dokumentu, czekanie na „Play” do 10 minut, ustawienie
   prędkości czytania, ustawienie przyspieszenia strony, klik „Play” (`EDP:src/auto.py:179-195`).
4. `set_reading_speed`: przycisk z tekstem jak `2.65x` otwiera popover, pole `input[aria-label="Playback rate"]`
   dostaje `1`, Enter, Escape (`EDP:src/auto.py:86-90`, `:148-157`).
5. `Job.step` co sekundę: brak audio 60 s po „Play” → ponowny klik, najwyżej 3 razy; koniec, gdy suwak odtwarzacza
   jest w 30 znakach od końca albo odebrano `char_count` znaków i od 10 s nie przyszło nic nowego; przestój 5 minut
   przed końcem = porażka (`EDP:src/auto.py:71-84`, `:197-216`, `PLAYER_STATE_JS` `:92-100`).
6. `finish`: porównanie odebranych znaków z `char_count`, ostrzeżenie o nadmiarze (`EDP:src/auto.py:225-246`).

### 6.3. Format audio

- MP3 128 kb/s, 44,1 kHz, w paczkach base64 od około 2 KB do około 230 KB (`EDP:docs/report.md:17`,
  `EDP:docs/research/capabilities.md:27`).
- Paczki są dopisywane do pliku w kolejności przyjścia (`EDP:src/downloader.py:221-223`). Paczki ≥ 8 KiB o
  identycznym skrócie SHA-1 (audio + znaki) są pomijane jako duplikaty (`EDP:src/downloader.py:72-73`, `:206-211`).
- Plik może zawierać kilka osobno zakodowanych strumieni rozdzielonych tagami ID3 lub obcymi bajtami;
  `EDP:src/clips.py:332-346` dekoduje je osobno, bo jednorazowe dekodowanie całego pliku rozjechało zegar o 0,34 s
  (`EDP:docs/report.md:75`). Nie wiadomo, czy dryf dotyczy FFmpeg, czy tylko dekodera `miniaudio` (patrz faza 1, E1).
- Długość liczona z ramek: 1152 próbki na ramkę MPEG-1 Layer III (`EDP:src/timestamps.py:21-31`, `:65-86`).

### 6.4. Format timestampów

- Na znak, nie na słowo: `chars[]`, `charStartTimesMs[]` (start od początku paczki), `charDurationsMs[]`
  (`EDP:docs/research/capabilities.md:28-30`).
- `EDP:src/downloader.py:244-253` zapisuje linię `align.jsonl` na paczkę: `offset_ms` (pozycja paczki w nagraniu =
  suma długości wcześniejszych ramek), `chars`, `start_ms`, `dur_ms`, opcjonalnie `resume`.
- Czas bezwzględny znaku = `offset_ms + start_ms` (`EDP:src/timestamps.py:99-117`).
- Tekst wraca dosłownie, razem z tagami `<break time="0.6s"/>` między akapitami i `<break time="2s"/>` na końcu
  (`EDP:docs/research/capabilities.md:28`, `:36`). `EDP:src/timestamps.py:33-34` rozpoznaje tag wyrażeniem
  `<break[^>]*(?:/>|$)`.
- Słowne czasy i zdania EDP wylicza samo (`EDP:src/timestamps.py:132-167`); serwer ich nie przysyła.
- Czasy znaków wyprzedzają faktyczną mowę o około 0,3 s (`EDP:docs/report.md:39`, `EDP:src/clips.py:13-14`).
- Pole `normalizedAlignment` jest akceptowane jako zamiennik `alignment` (`EDP:src/downloader.py:204`).

### 6.5. Limity, chunking, retry, rate limity

- Dokument jest jednostką: EDP nie dzieli tekstu; dokumenty do około 97 000 znaków przeszły
  (`EDP:docs/research/capabilities.md:101`). Twardego limitu długości kod nie ustala.
- Koszt: 1 kredyt na 10 000 znaków, łącznie z tagami `<break>` (`EDP:docs/report.md:35`); około 21 znaków na tag
  między akapitami (`EDP:docs/research/capabilities.md:118`).
- Przepustowość: jedna sesja około 4,5–5,5x czasu rzeczywistego niezależnie od przyspieszenia strony powyżej 16x
  (`EDP:README.md:143`, `EDP:docs/report.md:32-34`).
- Równoległość: od 2026-10-19 nowy strumień zamyka starszy, więc jeden dokument naraz (`EDP:docs/report.md:33`).
- Cache: ten sam tekst tym samym głosem drugi raz przychodzi około 58x szybciej i bez kredytów
  (`EDP:README.md:144`). Nie wiadomo, czy cache działa przy ponownym uploadzie identycznego tekstu jako nowego
  dokumentu.
- Ochrona: flagi `device_rate_limit_enabled`, `ip_ban_check_enabled`, aktywny App Check
  (`EDP:docs/research/capabilities.md:64`, `:152`).
- Retry w EDP: czekanie na serwis 1 minuta × 120 (`EDP:src/auto.py:121-134`), 3 kliknięcia „Play”
  (`EDP:src/auto.py:80-81`), brak automatycznego ponowienia całego dokumentu; porażka przenosi plik do `failed/`
  i drukuje komendę ręcznego wznowienia (`EDP:src/auto.py:240-246`).
- Ponowne połączenie strumienia: ramka `config` po odebraniu tekstu oznacza nowy strumień; pierwsze zdanie może
  przyjść drugi raz, więc `repeated_prefix` szuka początku nowej paczki w ostatnich 20 000 znakach i przycina
  powtórzenie razem z audio (`EDP:src/downloader.py:195-196`, `:257-312`). Kontrola kompletności wymaga
  tolerancji (`EDP:docs/research/capabilities.md:101`, `:160`).
- Model zależy od ustawionej prędkości czytania: 1x → v4, około 3x → v2 (`EDP:docs/report.md:36`).

### 6.6. Uwierzytelnienie

- Brak tokenów, kluczy i plików cookies w kodzie. Sesja to zalogowany profil Chrome w `EDP:.chrome-profile/`
  (`EDP:src/downloader.py:38-39`). Pierwsze logowanie robi człowiek w otwartym oknie (`EDP:README.md:57`).
- Chrome jest uruchamiany jako zwykły proces z `--remote-debugging-port=9222`, `--user-data-dir`, `--no-first-run`,
  `--no-default-browser-check`, a Playwright podłącza się `connect_over_cdp` (`EDP:src/downloader.py:44-45`,
  `:454-475`). Komentarz modułu: tak, aby działało logowanie Google (`EDP:src/downloader.py:3`).
- Brak automatycznego logowania, odświeżania i wykrywania wygaśnięcia sesji. Po wylogowaniu `open_library` czeka
  na przycisk „Import”, którego nie ma, i traktuje to jak awarię serwisu.
- Pliki profilu istnieją: `EDP:.chrome-profile/` i starszy `EDP:.browser-profile/`; oba w `EDP:.gitignore:294-295`.
  Ten plan ich nie otwiera.

### 6.7. Zależności

- Python 3.14, `playwright>=1.64.0` (API synchroniczne), `miniaudio>=1.71` (tylko `clips.py`), zainstalowany Google
  Chrome w `Program Files`, `Program Files (x86)` lub `%LOCALAPPDATA%` (`EDP:src/downloader.py:47-55`).
- Windows: `msvcrt.getwch` do klawiszy (`EDP:src/downloader.py:18`, `:337-339`).
- Playwright nie pobiera własnych przeglądarek — EDP używa zainstalowanego Chrome przez CDP.

### 6.8. Co jest w JS, a co w Pythonie

- `EDP:script.js` jest niezależnym userscriptem: podmienia `AudioContext.prototype.createBufferSource`, by
  odtwarzać 16x, i owija `window.WebSocket`, by zbierać pole `audio` (`EDP:script.js:25-69`). Narzędzia Pythona go
  nie używają.
- W Pythonie są dwa skrypty JS wstrzykiwane do strony: `SPEED_JS` (ustawia `playbackRate` buforów audio na
  `window.__edpSpeed`, `EDP:src/downloader.py:99-140`) i `PLAYER_STATE_JS` (odczyt suwaka odtwarzacza,
  `EDP:src/auto.py:92-100`). Reszta logiki — nasłuch ramek, zapis, czasy, cięcie — jest w Pythonie.

### 6.9. Co da się użyć bez przeglądarki

- Bez przeglądarki: parsowanie ramek, kontrola duplikatów i powtórzeń, oś czasu znaków, lokalizacja kwestii,
  wykrywanie ciszy, cięcie ramek MP3 (`EDP:src/downloader.py:156-312`, `EDP:src/timestamps.py`,
  `EDP:src/clips.py:155-611`). To są czyste funkcje i dają się testować offline.
- Z przeglądarką: logowanie, upload, otwarcie dokumentu, prędkość, odtwarzanie, odbiór ramek. Zastąpienie
  przeglądarki własnym klientem WebSocket oznaczałoby podrabianie protokołu za App Check — zakazane (Z1).

## 7. Stan aktualny: jak działa TTS w AniShift

### 7.1. Rejestr i kontrakty

- `TtsEngineId = Literal["edge", "elevenbytes", "elevenlabs", "sapi"]` i leniwy `_REGISTRY` modułów jako stringów
  (`anishift/services/tts/engines/__init__.py:18-38`); nieznane ID → `TtsConfigError`
  (`anishift/services/tts/engines/__init__.py:56-67`).
- `TtsEngine`: `engine_id`, `is_available`, `capabilities`, `synthesis_profile`, `availability(live=...)`,
  `list_voices()`, `synthesize(request, cancel=...)`, `close()` (`anishift/services/tts/protocols.py:86-123`).
- `SynthesisRequest` niesie jeden tekst i prywatne `destination` (`anishift/services/tts/types.py:260-273`);
  `EngineClipResult` opisuje jeden klip (`anishift/services/tts/types.py:276-286`).
- `EngineCapabilities` (`anishift/services/tts/types.py:218-233`) bez pojęcia dokumentu.
- `ClipValidator` i `ClipAssembler` są protokołami domeny implementowanymi w aplikacji przez FFmpeg
  (`anishift/services/tts/protocols.py:36-60`, `anishift/application/tts_clips.py:17-100`).

### 7.2. Silnik `elevenbytes` (wzorzec adaptera)

- Konfiguracja z `TtsConfig` w `ElevenBytesConfig.from_tts_config`, bez sieci w konstruktorze
  (`anishift/services/tts/engines/elevenbytes/config.py:22-56`, `service.py:75-98`).
- `availability(live=False)` zwraca stan z pamięci; `live=True` robi probe (`service.py:110-133`).
- `synthesize` waliduje żądanie, sprawdza anulowanie przed i po żądaniu, zapisuje bajty do `destination`
  (`service.py:147-176`). Transport ma `retries=0` (`engines/elevenbytes/AGENTS.md:9-10`).
- Profil syntezy (`SynthesisProfile`) wchodzi do fingerprintu resume (`service.py:84-93`).

### 7.3. Scheduler

- Jeden `TtsScheduler` na cykl życia silnika: kolejka priorytetowa (retry przed nowymi, potem `batch_rank`,
  `request_rank`), `max_concurrency` workerów, semafor `queue_capacity` (`anishift/services/tts/scheduler.py:74-117`).
- `_attempt` buduje żądanie przez `request_factory(attempts)` i woła `engine.synthesize` pod
  `asyncio.timeout(request_timeout_s)` albo bez limitu, gdy `scheduler_timeout_enabled=False`
  (`scheduler.py:105`, `:224-260`).
- Retry tylko dla `TransientError`, do `max_retries`, z opóźnieniem z `retry_backoff_seconds` albo `retry_after_s`
  błędu (`scheduler.py:294-328`, `:380-390`); dla silników lokalnych bez opóźnienia (`:381-382`).
- Circuit: błąd trwały auth/config/voice albo wyczerpany błąd przejściowy kończy całą kolejkę i blokuje nowe
  żądania (`scheduler.py:338-344`, `:426-429`).
- Domyślne wartości: `max_retries=3`, backoff `(15, 30, 60, 120)`, timeout 30 s (`anishift/services/tts/config.py:19-35`);
  wyjątki: `elevenbytes` 45 s i backoff `(5, 10, 15, 30)`, `sapi` 10 s (`anishift/application/runtime.py:127-133`);
  `elevenbytes` z VPN wyłącza timeout schedulera (`runtime.py:651`).
- Współbieżność to `tts_request_concurrency` z profilu głosu (`anishift/application/service.py:1057-1069`),
  `queue_capacity = max(2, 2 × concurrency)` (`runtime.py:644`).

### 7.4. Przepływ od napisów do klipów

1. Planner tworzy zadanie `SYNTHESIZE_SPEECH` z zasobem `tts:<silnik>`, więc pliki idą po jednym
   (`anishift/application/planner.py:832-835`, `anishift/application/AGENTS.md:184-186`).
2. `TtsTaskHandler.execute` czyta skrypt (spoken PL, pełne PL, napisy źródłowe albo TXT), dzieli na `SpokenLine`
   i buduje `SpeechBatch(group_id, rank, requests)` z kwestii mających litery lub cyfry
   (`anishift/application/tts_handler.py:221-268`, `:541-562`).
3. `TtsService.synthesize` uruchamia batch na własnej pętli asyncio w wątku `anishift-tts`
   (`anishift/services/tts/service.py:248-288`, `:341-377`).
4. `_run_batch` dla każdej kwestii: dzielenie według limitów silnika, tożsamość resume, odczyt resume, a przy braku —
   próba przez scheduler, walidacja dekodowaniem, opcjonalne sklejenie części, zatwierdzenie
   (`service.py:402-768`).
5. `build_narration_manifest` wymaga statusu `COMPLETED`; brak klipu kwestii przerywa zadanie
   (`anishift/application/tts_handler.py:399-444`).
6. Szyldy: drugi batch tej samej grupy, klipy umieszczane w wolnych przerwach (`tts_handler.py:287-366`).

### 7.5. `narration_timeline` i miks

- `NarrationTimeline.SOURCE_TIMES` umieszcza klip w oknie napisu; `CONTINUOUS` układa klipy jeden po drugim
  (`anishift/application/tts_handler.py:565-575`).
- `plan_timeline` ustawia klip na czasie okna albo za poprzednim, bez obcinania; długość klipu pochodzi z dekodowania
  (`anishift/services/audio/timeline.py:31-89`).
- Normalizacja klipów i tempo końcowe (`tts_postprocess_tempo`) w `AudioService.prepare_clip`
  (`anishift/application/runtime.py:293-315`).
- Gain narratora `narrator_mix_base_gain_db + voice_mix_offset_db` tylko przy miksie z oryginałem
  (`anishift/services/audio/AGENTS.md:36-37`).

### 7.6. Ustawienia

- `.env` i środowisko: `Settings` (pydantic-settings, prefiks `ANISHIFT_`, `extra="ignore"`), m.in.
  `elevenlabs_api_key` (`anishift/config/settings.py:55-117`).
- Preferencje panelu: `UserSettings` w `config/settings.json`: `tts_engine="elevenbytes"`,
  `tts_provider_model_id="run6"`, `tts_voice_id="dallin"`, `tts_voice_profiles` (`user_settings.py:242-284`).
- Logika per silnik w łańcuchach `if`: `tts_voice_label` (`user_settings.py:334-352`),
  `resolved_tts_voice_id` (`:355-371`), `_normalize_tts_selection` (`:445-474`),
  `_drop_incompatible_tts_options` (`:476-484`), `_tts_model_values` i `_tts_voice_values`
  (`field_catalog.py:1348-1378`), `_profile_defaults` (`field_catalog.py:1381-1389`), `_tts_allowed_voice_ids`
  (`anishift/application/service.py:1036-1045`).
- Pułapka: dla `elevenbytes` każdy niepusty identyfikator spoza aliasów jest traktowany jako własny głos
  (`engines/elevenbytes/AGENTS.md:15-16`), a `_normalize_tts_selection` resetuje tylko głosy SAPI i Edge
  (`user_settings.py:449-452`). Alias nowego silnika po przełączeniu na `elevenbytes` zostałby więc wysłany do proxy
  jako ID głosu. Plan to naprawia (F11).

### 7.7. Panel Ustawień

- Kategoria „Lektor” wyświetla pola z `_TTS_FIELDS` (`anishift/cli/interactive/settings.py:222-242`); etykiety
  silników w `_ENGINE_LABELS` (`settings.py:343-358`).
- „Połączenia” edytują sekrety `.env` przez `_CONNECTIONS` (`settings.py:488-510`) i `AppService`.
- Test pilnuje, by każde edytowalne pole było osiągalne (`_KNOWN_LAYOUT_GAPS` puste, `settings.py:294`).
- Wzorzec akcji w tle: `_start_probe` z wątkiem, generacją i `_Feedback` (`settings.py:1627-1660`).

### 7.8. `setup` i `doctor`

- `doctor` to płaska lista synchronicznych checków bez sieci poza Web UI qBittorrent
  (`anishift/setup/doctor.py:256-283`); brak kluczy to WARN (`anishift/setup/AGENTS.md:19`).
- `setup` pobiera binarki z manifestu; nie instaluje programów systemowych (`anishift/setup/AGENTS.md:3`).

### 7.9. Błędy i logowanie

- `AniShiftError` → `TtsError` → konkretne, z miksami `TransientError` / `FatalError`
  (`anishift/services/tts/errors.py:28-150`); kody w `ErrorCode` (`anishift/errors.py:80-94`); brak kodu dla
  wyczerpanych kredytów.
- Logowanie przez `get_logger(__name__)`; bez sekretów, payloadów, tekstów TTS, nagłówków, podpisanych URL-i i
  ścieżek absolutnych (`AGENTS.md`, sekcja „Dane runtime”).

### 7.10. Platforma

- `ProcessLock` — blokada pliku na proces (`anishift/platform/process_lock.py:32-60`).
- `_protect_profile` zawęża katalog do bieżącego konta przez `icacls ... /inheritance:r /grant:r konto:(OI)(CI)F`
  (`anishift/platform/qbittorrent_process.py:633-653`); drugi, plikowy wariant z ostrzeżeniem zamiast błędu jest w
  `anishift/platform/local_control.py:943-975`.
- `installed_executable()` szuka programu w `%ProgramFiles%`, `%ProgramFiles(x86)%`, `%LOCALAPPDATA%\Programs` i na
  `PATH` (`anishift/platform/qbittorrent_config.py:236-246`).
- Rezydent przypisuje procesy potomne do Job Object, więc kończą się z nim (`anishift/platform/AGENTS.md:51-53`).

## 8. Luka

```text
CURRENT: silnik = jedno żądanie tekstu → jeden klip; brak przeglądarki, sesji, dokumentu, cięcia.
   ↓
GAP: ElevenReader czyta dokument, nie kwestię; wymaga zalogowanego Chrome; audio przychodzi strumieniem
     z czasami znaków; klipy kwestii trzeba wyciąć z nagrania; brak kodu błędu kredytów; brak akcji logowania.
   ↓
TARGET: kontrakt dokumentu w domenie TTS + scheduler wykonujący dowolną próbę + cięcie w domenie audio
        + silnik `elevenreader` + sesja w config/elevenreader/ + panel i doctor.
```

Przyczyna, dla której nie wystarczy nowy adapter za istniejącym `TtsEngine.synthesize`: scheduler przekazuje silnikowi
po jednym żądaniu (`scheduler.py:224-235`), a `_run_batch` rozdziela kwestie na niezależne próby
(`service.py:478-516`). Silnik nie widzi całego batcha, więc nie może zebrać kwestii w dokument bez sprzęgania prób
w ukrytym stanie. Jedno źródło prawdy o retry i resume zostaje we wspólnej warstwie tylko wtedy, gdy dokument staje
się jawną próbą schedulera.

## 9. Istniejące rozwiązania do reuse

| Element | Ścieżka / symbol | Co wykorzystać | Ograniczenie |
|---|---|---|---|
| retry, circuit, timeout | `TtsScheduler` | całe zachowanie | wymaga uogólnienia `submit` (sekcja 13.5) |
| resume klipów | `TtsResumeRepository.lookup/commit_clip/validate_temporary_clip/temporary_clip_path` | bez zmian, per kwestia | nagranie dokumentu to zwykły plik tymczasowy, nie wpis manifestu |
| fingerprint | `SynthesisIdentity`, `SynthesisProfile` | tożsamość kwestii | kontekst sąsiednich kwestii nie wchodzi do tożsamości (świadomie) |
| walidacja klipu | `FfmpegClipService.validate_clip` | walidacja wyciętych klipów (nagranie waliduje dekodowanie obwiedni) | — |
| wzorzec protokołu FFmpeg | `ClipAssembler` → `FfmpegClipService.join_clips` | wzór dla `ClipSplitter.split_clip` | — |
| komendy FFmpeg | `anishift/services/audio/commands.py`, `SubprocessRunner` | nowa komenda obwiedni WAV | stdout jest tekstem, więc PCM idzie przez plik WAV |
| odczyt WAV | `wave` (stdlib), wzór `probe_pcm_wav` (`anishift/services/audio/probe.py`) | odczyt próbek obwiedni | — |
| nagłówki MP3 | `anishift/services/audio/mp3.py:_parse_frame_header` | wydzielić do `anishift/utils/mp3_frames.py` | utils bez zależności od AniShift |
| blokada | `ProcessLock` | blokada profilu Chrome | blokada per proces |
| ACL katalogu | `qbittorrent_process._protect_profile` | wydzielić `restrict_directory` | błąd mapowany przez wołającego |
| wyszukanie programu | `qbittorrent_config.installed_executable` | wydzielić `find_installed` | — |
| ścieżki | `anishift/paths.py` | `elevenreader_dir()` | funkcje nie tworzą katalogów |
| redagowanie sekretów | `anishift/utils/secrets.py` (`cookie`, `password`, `token`) | logger już redaguje klucze | nie zastępuje zakazu logowania URL-i |
| akcja w tle w panelu | `SettingsController._start_probe` | wzór wątku, generacji, feedbacku | — |
| sekrety `.env` | `_CONNECTIONS`, `AppService.update_environment_setting`, `env_file.py` | gałąź D2 | — |
| logika EDP | sekcja 6, `file-map.md` §1 | port, nie import | — |

## 10. Dowody

| Twierdzenie | Dowód | Status |
|---|---|---|
| EDP nagrywa z prawdziwego Chrome przez CDP | `EDP:src/downloader.py:454-475` | verified |
| ramki zawierają audio i czasy znaków | `EDP:src/downloader.py:181-255`, `capabilities.md:26-31` | verified (kod + dokument autora) |
| czasy wyprzedzają mowę o ~0,3 s | `EDP:docs/report.md:39` | reported (pomiar autora EDP) |
| jeden strumień naraz | `EDP:docs/report.md:33` | reported |
| v4 przy prędkości 1x | `EDP:docs/report.md:36` | reported |
| identyfikatory głosów Adam / Fronczewski | brak w kodzie i dokumentach EDP | unknown → faza 0 |
| sposób wyboru głosu w odtwarzaczu | brak w kodzie EDP | unknown → faza 0 |
| metody logowania na elevenreader.io | brak w EDP; publiczne źródła nie rozstrzygają (wyszukiwanie 2026-10-25) | unknown → faza 0 |
| czy `--headless=new` działa dla uploadu i odtwarzania | `EDP:README.md:84` (opcja istnieje) | reported, do potwierdzenia w fazie 0 |
| dryf zegara przy dekodowaniu całego pliku FFmpeg | `EDP:docs/report.md:75` dotyczy innego dekodera | unknown → faza 1, E1 |
| Chrome 136+ ignoruje port debugowania dla domyślnego profilu | <https://developer.chrome.com/blog/remote-debugging-port>, odczyt 2026-10-25 | verified (źródło producenta) |
| zakaz automatycznej ekstrakcji w polityce ElevenLabs | <https://elevenlabs.io/use-policy> §12, „Last Updated: 09 October 2026”, odczyt 2026-10-25 | verified |
| Fronczewski jako głos „Iconic Voices” w ElevenReader | <https://elevenlabs.io/pl/blog/piotr-fronczewski>, wynik wyszukiwania 2026-10-25 | supported |
| TTS nie widzi całego batcha | `scheduler.py:224-235`, `service.py:478-516` | verified |
| alias obcego silnika przeszedłby do `elevenbytes` jako ID | `user_settings.py:449-452`, `engines/elevenbytes/AGENTS.md:15-16` | verified |

## 11. Wykorzystanie timestampów

### 11.1. Co dziś zastępuje czasy znaków

AniShift nie zna czasu mowy wewnątrz klipu. Długość klipu mierzy pełne dekodowanie FFmpeg
(`anishift/application/tts_clips.py:37-77`, `:102-118`), a oś czasu umieszcza klip na początku okna napisu albo
za poprzednim klipem i zapisuje rozjazd (`drift_ms`) w planie (`anishift/services/audio/timeline.py:54-81`). Tempo
końcowe zmienia cały klip (`tts_postprocess_tempo`). Nie ma przycinania ciszy na brzegach klipu.

### 11.2. Do czego ten plan używa czasów znaków

| Zastosowanie | W MVP? | Uzasadnienie |
|---|---|---|
| Lokalizacja kwestii w nagraniu dokumentu (pierwsza i ostatnia litera kwestii) | **tak, konieczne** | bez tego nie wiadomo, który fragment nagrania należy do której kwestii |
| Punkt wyjścia do cięcia w ciszy (granica = środek przerwy między kwestiami, korygowany o opóźnienie mowy) | **tak, konieczne** | `EDP:src/clips.py:382-514`; same czasy bez ciszy ucinają słowa (`EDP:docs/report.md:39`) |
| Kontrola kompletności: odebrane znaki wobec `char_count` | **tak** | wykrywa urwane nagranie przed cięciem (`EDP:src/auto.py:231-246`) |
| Przycinanie powtórzeń po ponownym połączeniu strumienia | **tak** | inaczej kwestia dostałaby powtórzone zdanie (`EDP:src/downloader.py:257-312`) |
| Postęp syntezy (odebrane znaki / `char_count`) | **tak** | pomiar backendu zamiast zgadywania (N7) |
| Dopasowanie mowy do okna napisu | nie | robi to dziś oś czasu na dekodowanej długości; czasy znaków nie dają nic więcej |
| Przycinanie ciszy na brzegach klipu | nie (pośrednio tak) | cięcie w ciszy z marginesem 100 ms przed i 150 ms po (`EDP:src/clips.py:47-51`) daje już krótkie brzegi |
| Kontrola tempa | nie | tempo końcowe per głos istnieje; zmiana tempa ElevenReadera powyżej 1x przełącza model na v2 |
| Raport jakości (np. kwestie dłuższe niż okno) | nie | `TimelinePlacement.drift_ms` istnieje; słowne czasy odłożone |

### 11.3. Wniosek

Czasy znaków są w MVP potrzebne wyłącznie po to, aby z jednego nagrania dokumentu otrzymać klip każdej kwestii
(plus kompletność, powtórzenia i postęp). Po wycięciu klipy wchodzą do istniejącej drogi AniShift bez żadnych
metadanych czasowych — domena TTS nadal nie przekazuje dalej timestampów (`anishift/services/tts/AGENTS.md:25-26`).

## 12. Integracja: warianty i wybór

### 12.1. Trzy warianty

| Kryterium | A. Kopia z refaktorem | B. Zależność `uv add` (ścieżka lub git) | C. Proces zewnętrzny |
|---|---|---|---|
| Jedno źródło prawdy o retry, resume, błędach | tak — wspólny scheduler i resume AniShift | nie — EDP ma własną pętlę czekania i ponowień (`EDP:src/auto.py:121-134`) | nie — dwa procesy, dwa stany |
| Typowane błędy i anulowanie | tak | wymaga przebudowy EDP | tylko `terminate` i parsowanie stdout |
| Async w pętli TTS | Playwright async API | EDP używa sync API (`EDP:src/downloader.py:29`) | n/d |
| Wybór głosu | do zbudowania | do zbudowania w EDP | do zbudowania w EDP |
| Zmiana EDP | brak | konieczna (pakiet, API, błędy) — sprzeczne z Z3 | konieczna (tryb jednego dokumentu) |
| CI (Windows/Ubuntu), `pip-audit` | działa | ścieżka lokalna nie istnieje w CI; prywatny git wymaga tokenu | EDP poza CI |
| Kod widoczny publicznie | tak (D7) | tylko przy prywatnym repo | tylko przy prywatnym repo |
| Duplikat logiki między repo | tak — EDP zostaje osobnym narzędziem | nie | nie |

### 12.2. Wybór: A

Wariant A daje jeden model błędów, retry i resume w AniShift, działa w CI i nie wymaga zmian w EDP. Duplikat
logiki między repozytoriami jest świadomy: EDP to narzędzie właściciela do audiobooków z innym cyklem życia, a
AniShift potrzebuje tylko części tej logiki w innej formie (async, typowane błędy, brak katalogów `input/`).
Wewnątrz AniShift nie powstaje żaden duplikat: wspólne parsowanie ramek MPEG i ochrona katalogów są wydzielane do
jednego źródła (sekcja 12.4).

### 12.3. Co z EDP odpada

- `EDP:script.js` w całości.
- Ręczny tryb `EDP:src/downloader.py`: klawisze `msvcrt`, `handle_key`, `read_keys`, `next_free_output`, dopisywanie do
  istniejącego pliku z offsetem, `RESUME_MARK`, `Monitor.report` i statusy MB.
- `EDP:src/auto.py`: katalogi `input/`, `done/`, `failed/`, `pending_inputs`, `free_output`, `--parallel`, `run_all`,
  `replace_page`, drukowanie komendy ręcznego wznowienia, czekanie 120 minut wewnątrz próby.
- `EDP:src/timestamps.py`: SRT, JSON, zdania, słowa, `split_words`, `split_sentences`, CLI.
- `EDP:src/clips.py`: parser SRT, `prepare`, `verify`, `edge_levels`, CLI, dekodowanie przez `miniaudio`.
- Stała `CDP_PORT = 9222`: zastąpiona wolnym portem wybranym w czasie uruchomienia.
- Zależność `miniaudio`: dekodowanie robi FFmpeg (już wymagany, `anishift/application/runtime.py:216-217`).

### 12.4. Co w AniShift zrefaktoryzować, żeby nie było duplikatu

| Duplikat, który by powstał | Refaktor |
|---|---|
| drugi parser nagłówka ramki MPEG w silniku (obok `anishift/services/audio/mp3.py:146-176`) | `anishift/utils/mp3_frames.py` jako jedyne źródło; `mp3.py` go używa |
| trzecia funkcja ACL katalogu obok `qbittorrent_process._protect_profile` i `local_control._restrict_to_current_user` | `anishift/platform/private_dir.restrict_directory` z kodu `_protect_profile`; qBittorrent woła nową funkcję. Plikowy wariant w `local_control` ma inną semantykę (ostrzeżenie zamiast błędu, plik zamiast drzewa) i zostaje; plan to zgłasza, nie łączy |
| druga funkcja szukania zainstalowanego programu obok `qbittorrent_config.installed_executable` | `anishift/platform/installed.find_installed(locations, stem)`; qBittorrent i Chrome z niej korzystają |
| druga pętla retry w silniku (wzór EDP: 120 × 1 minuta) | brak — awaria serwisu to `TtsProviderUnavailableError(retry_after_s=60)` dla wspólnego schedulera |
| drugi mechanizm resume (EDP: dopisywanie do pliku) | brak — resume per kwestia w `TtsResumeRepository` |
| druga walidacja MP3 | brak — `FfmpegClipService.validate_clip` |

Wiedza nie jest kopiowana do dwóch miejsc w AniShift: algorytm ciszy żyje tylko w `services/audio/segmentation.py`,
lokalizacja kwestii tylko w `engines/elevenreader/alignment.py`, protokół strony tylko w
`engines/elevenreader/page.py`.

## 13. Target design

### 13.1. Odpowiedzialności i ownership

| Element | Odpowiada za | Owner danych/stanu | Nie odpowiada za |
|---|---|---|---|
| `TtsTaskHandler` (bez zmian) | skrypt → `SpeechBatch`, manifest narracji | czasy napisów | silnik, dokument |
| `TtsService` | wybór ścieżki per kwestia albo dokument, resume, zatwierdzanie klipów, postęp | manifest resume | strona, Chrome, cięcie |
| `TtsScheduler` | kolejka, retry, circuit, timeout prób | stan circuit | budowa żądania |
| `ClipSplitter` (`FfmpegClipService.split_clip`) | obwiednia, cisze, granice, cięcie ramek | pliki wyciętych klipów (tymczasowe) | lokalizacja kwestii |
| `ElevenReaderTtsEngine` | jedna próba dokumentu: przeglądarka, upload, odtwarzanie, nagranie, lokalizacja kwestii | nagranie dokumentu (tymczasowe), proces Chrome | retry, resume |
| `session.py` | stan sesji, logowanie interaktywne, opcjonalne logowanie danymi | `config/elevenreader/session.json` | sekrety w plikach |
| `browser.py` | proces Chrome, port, blokada profilu, ACL | `config/elevenreader/chrome-profile/`, `profile.lock` | protokół strony |
| `UserSettings` / `field_catalog` | wybór silnika, głosu, profile głosów | `config/settings.json` | sesja |
| `Settings` | e-mail i hasło z `.env` (tylko gałąź D2) | `.env` | — |
| `doctor` | pasywna diagnoza | — | uruchamianie przeglądarki |

### 13.2. Source of truth

- Wybór silnika i głosu: `UserSettings.tts_engine`, `tts_voice_id` w `config/settings.json`.
- Identyfikatory głosów: `engines/elevenreader/constants.py` (`VOICES`), jedyne miejsce w kodzie.
- Sesja: cookies w `config/elevenreader/chrome-profile/` (zarządza Chrome). `session.json` jest stanem pochodnym
  (ostatnia obserwacja), nigdy podstawą decyzji o syntezie — silnik zawsze sprawdza sesję na stronie.
- Gotowe klipy kwestii: `manifest.json` repozytorium resume grupy.
- Nagranie dokumentu: plik tymczasowy jednej próby; usuwany po cięciu albo po porażce.

### 13.3. Przepływ sterowania

```text
TtsTaskHandler.execute
  -> TtsService.synthesize(batch)
       -> _run_batch: engine = create_engine(config)
          capabilities.max_document_chars is None ? ścieżka per kwestia (bez zmian zachowania)
                                                  : _run_document_batch
  _run_document_batch:
       for request: skip niemowy | resume hit | pending
       documents = _plan_documents(pending, max_document_chars)
       for document:
          scheduler.submit(call=attempt -> engine.synthesize_document(DocumentSynthesisRequest),
                           accept_result=splitter.split_clip -> validate każdego klipu)
          commit_clip dla każdej znalezionej kwestii; brakująca -> błąd kwestii
       flush manifestu, _batch_result
  ElevenReaderTtsEngine.synthesize_document:
       browser.ensure() (lock, Chrome, CDP) -> session.require_signed_in()
       page.upload(document.txt) -> read_id, char_count
       page.open(read_id) -> set_reading_speed(1) -> ensure_voice(voice_id) -> set_page_speed(16) -> play
       recorder: ramki WS -> plik nagrania + oś czasu znaków; postęp
       koniec / przestój / anulowanie
       alignment.locate(parts, timeline) -> PartTiming[]
       -> EngineDocumentResult
```

### 13.4. Kontrakty domeny TTS (nowe i zmienione)

Wszystkie typy: `@dataclass(frozen=True, slots=True)`, w `anishift/services/tts/types.py`, eksportowane w
`anishift/services/tts/__init__.py`.

```text
EngineCapabilities (zmiana)
  + max_document_chars: int | None = None
    None  -> silnik per kwestia (wszystkie dzisiejsze silniki, bez zmiany konstruktorów)
    int>0 -> silnik dokumentowy; TtsService nigdy nie woła jego synthesize()

DocumentPart
  request_id: str           # id kwestii z SpeechRequest
  text: str                 # tekst kwestii po walidacji domeny (bez neutralizacji — robi ją silnik)

DocumentSynthesisRequest
  request_id: str           # "<scope_id>:document:<n>:attempt:<a>"
  parts: tuple[DocumentPart, ...]      # co najmniej jedna, kolejność czytania
  voice_id: str
  provider_model_id: str
  options: EngineOptions
  recording: Path           # prywatna ścieżka tymczasowa z TtsResumeRepository.temporary_clip_path(MP3)
  deadline_s: float
  progress: Callable[[int, int], Awaitable[None]] | None = field(default=None, compare=False)
                            # (odebrane_znaki, znaki_dokumentu); wyjątek observera nie przerywa syntezy

PartTiming
  request_id: str
  start_ms: float           # pierwsza litera kwestii w nagraniu, zegar ramek MP3
  end_ms: float             # koniec ostatniej litery; end_ms > start_ms

EngineDocumentResult
  request_id: str
  recording: Path           # == request.recording
  format: AudioFormat       # MP3
  engine_id: str
  provider_model_id: str
  voice_id: str
  request_time_ms: float
  parts: tuple[PartTiming, ...]        # tylko znalezione kwestie, rosnąco po start_ms, bez duplikatów id

ClipSpan
  request_id: str
  start_ms: float
  end_ms: float
  destination: Path         # prywatna ścieżka tymczasowa klipu

SplitResult
  written: tuple[str, ...]  # request_id zapisanych klipów, w kolejności spans
  boundaries_without_silence: int     # liczba granic postawionych w „dołku” albo na samych czasach
```

Protokoły w `anishift/services/tts/protocols.py`:

```text
@runtime_checkable
class DocumentTtsEngine(TtsEngine, Protocol):
    async def synthesize_document(self, request: DocumentSynthesisRequest, *,
                                  cancel: CancellationToken) -> EngineDocumentResult: ...

@runtime_checkable
class ClipSplitter(Protocol):
    def split_clip(self, source: Path, spans: tuple[ClipSpan, ...],
                   expectation: ClipExpectation) -> SplitResult: ...
```

Kontrakt `split_clip`:

- wejście: `source` to nagranie MP3 (bez osobnej walidacji — dekodowanie obwiedni jest walidacją; błąd dekodowania
  albo brak ramek → `ValueError`); `spans` niepuste, rosnące po `start_ms`, rozłączne;
- wyjście: każdy `destination` z `written` zawiera kompletne ramki MP3 pokrywające mowę kwestii z marginesami;
- błędy: `RuntimeError` / `OSError` / `ValueError` przy awarii FFmpeg lub danych (jak `join_clips`,
  `anishift/application/tts_clips.py:98-100`); `TtsService` mapuje je na `TtsClipValidationError`;
- efekty uboczne: pliki `destination` i jeden tymczasowy WAV obwiedni w katalogu tymczasowym systemu, usuwany przed
  powrotem.

Nowy błąd w `anishift/services/tts/errors.py`:

```text
class TtsQuotaError(TtsError, FatalError):
    """Provider account has no credits left for synthesis."""
    error_code = ErrorCode.TTS_QUOTA_EXHAUSTED
```

`ErrorCode.TTS_QUOTA_EXHAUSTED = "TTS_QUOTA_EXHAUSTED"` w `anishift/errors.py` obok kodów TTS (`:80-94`).
`_opens_circuit` dodaje `TtsQuotaError` do błędów trwałych otwierających circuit (`scheduler.py:426-429`).

`TtsConfig` (`anishift/services/tts/config.py`) dostaje pola specyficzne dla silnika, na wzór `elevenlabs_api_key`
(`config.py:42`):

```text
elevenreader_profile_root: Path | None = None
elevenreader_email: str = field(default="", repr=False)
elevenreader_password: str = field(default="", repr=False)
```

### 13.5. Uogólnienie schedulera

Zmiana w `anishift/services/tts/scheduler.py` bez zmiany zachowania dotychczasowych silników:

```text
@dataclass(frozen=True, slots=True)
class ScheduledSynthesis[R]:
    result: R | None
    error: TtsError | None
    attempts: int

TtsScheduler.submit[R](
    call: Callable[[int], Awaitable[R]],          # numer próby -> wynik providera; jedno wywołanie providera
    *, batch_rank, request_rank, cancel,
    accept_result: Callable[[R], Awaitable[R]],
    on_result: Callable[[R], Awaitable[None]] | None = None,
    on_retry: Callable[[int, int, float, TtsError], Awaitable[None]] | None = None,
) -> ScheduledSynthesis[R]
```

- `_WorkItem` przechowuje `call` zamiast `request_factory`; kolejki trzymają `_WorkItem[Any]` (dozwolony jawny
  `Any`, `pyproject.toml:105`).
- `_attempt` wykonuje `await work.call(work.attempts)` pod tym samym `asyncio.timeout`; mapowanie wyjątków,
  `_accept`, `_handle_error`, `_retry_delay`, circuit — bez zmian.
- Konstruktor nadal dostaje `engine` (potrzebny do `capabilities.locality` w `_retry_delay`).
- `_ProviderAttempt` w `service.py` daje `call=lambda attempt: engine.synthesize(attempt_ctx.request_for_attempt(attempt), cancel=self._cancel)`;
  pole `ScheduledSynthesis.clip` zmienia nazwę na `result` — wszystkie użycia w `service.py:667-690` i testach
  aktualizowane w tym samym commicie.

### 13.6. Algorytm ścieżki dokumentu w `TtsService`

`TtsService.__init__` dostaje parametr `splitter: ClipSplitter | None = None` obok `assembler`
(`service.py:223-246`). `_run_batch` po `_ensure_runtime` sprawdza `engine.capabilities.max_document_chars`.

```text
_run_document_batch(batch, engine, scheduler, callbacks):
  1. jeżeli splitter is None albo not isinstance(engine, DocumentTtsEngine):
        wszystkie kwestie mowy -> _failed_execution(TtsUnsupportedError("Document synthesis requires a clip splitter"))
  2. dla każdej kwestii w kolejności batcha:
        niemowa -> _skipped_execution
        chunks = chunk_speech_text(text, max_chars=capabilities.max_text_chars, max_bytes=None)   # jak service.py:536-540
        len(chunks) != 1 -> _failed_execution(TtsInputError)    # kwestia dłuższa niż limit dokumentu
        identity = SynthesisIdentity(scope, request_id, text, chunks=chunks, profile=engine.synthesis_profile)
        lookup -> trafienie -> _cached_execution
        inaczej -> pending
     powiadom postęp po każdej kwestii rozstrzygniętej bez providera
  3. documents = _plan_documents(pending, max_document_chars):
        zachłannie w kolejności batcha; dokument zamyka się, gdy suma len(text) następnej kwestii przekroczyłaby limit
  4. dla każdego dokumentu po kolei (nigdy równolegle; max_concurrency=1):
        outcome = await scheduler.submit(call, accept_result, on_result, on_retry, batch_rank, request_rank=pierwszej kwestii)
          call(a):   recording = repository.temporary_clip_path(MP3); zapamiętaj ścieżkę
                     -> engine.synthesize_document(DocumentSynthesisRequest(..., recording, deadline_s=config.request_timeout_s, progress=...))
          accept(r): własność wyniku (ścieżka, engine_id, provider_model_id, voice_id) jak _ProviderAttempt.accept_result
                     spans = ClipSpan dla każdego r.parts z nową ścieżką tymczasową
                     split = await to_thread(splitter.split_clip, recording, spans, expectation)
                       (RuntimeError, OSError, ValueError) -> TtsClipValidationError (przejściowy => ponowienie dokumentu)
                     dla każdego zapisanego klipu: receipt = repository.validate_temporary_clip(...)
                       None -> TtsClipValidationError
                     zapamiętaj receipts; return r
        outcome.error -> każda kwestia dokumentu = _failed_execution(outcome.error); usuń ścieżki
        inaczej, dla każdej kwestii dokumentu:
             receipt jest -> commit_clip(identity, path, expectation, can_commit, validation_receipt=receipt)
                             -> SpeechClip(attempts=outcome.attempts, from_resume=False)
             receipt brak -> _failed_execution(TtsClipValidationError("Line was not found in the recording"))
        usuń nagranie i niezatwierdzone ścieżki
  5. repository.flush(); _batch_result(batch, ordered, engine)
```

Księgowanie: `provider_calls` i `retries` dokumentu trafiają do pierwszej kwestii dokumentu, pozostałe kwestie mają
`provider_calls=0`, `retries=0`, aby `SpeechBatchStats` liczył wywołania providera, nie kwestie
(`service.py:926-960`).

Postęp: `progress(received, total)` → `SpeechBatchProgress.received_required_requests = rozstrzygnięte +
floor(received / total × liczba_kwestii_dokumentu)`, ograniczone do liczby kwestii dokumentu; observer przez
`_safe_callback` (`service.py:894-900`). Po zatwierdzeniu — zwykłe `_notify_execution` per kwestia.

Anulowanie: `self._cancel` trafia do `synthesize_document`; `can_commit(generation)` chroni commit jak dziś.

### 13.7. Domena audio: segmentacja i cięcie

`anishift/utils/mp3_frames.py` (bez importów AniShift):

```text
@dataclass(frozen=True, slots=True)
class FrameHeader: offset: int; size: int; sample_rate: int; channels: int; samples: int; version: int

parse_frame_header(data: bytes, offset: int) -> FrameHeader | None   # MPEG-1/2/2.5 Layer III; z mp3.py:146-176
iter_frames(data: bytes) -> Iterator[FrameHeader]                     # pomija ID3v2 i obce bajty (EDP:timestamps.py:65-81)
frames_duration_ms(data: bytes) -> float                              # suma samples*1000/sample_rate
cut_before_ms(data: bytes, cut_ms: float) -> tuple[bytes, float]      # EDP:timestamps.py:89-96, tolerancja 0,5 ms
```

`anishift/services/audio/mp3.py` zachowuje `read_mp3_stream_properties` z tym samym zachowaniem i błędami
(`tests/services/audio/test_audio_mp3.py` bez zmian zachowania) i dodaje:

```text
Mp3Frame: start: int; end: int; start_ms: float; end_ms: float
frame_table(data: bytes) -> tuple[Mp3Frame, ...]              # EDP:clips.py:302-312
cut_frames(data, frames, start_ms, end_ms) -> tuple[bytes, float, float]   # EDP:clips.py:315-321, 2 ramki rezerwy
stream_ranges(frames) -> tuple[tuple[int, int], ...]          # EDP:clips.py:332-335
```

`anishift/services/audio/segmentation.py` (czysty port `EDP:src/clips.py:349-514`, te same stałe i nazwy znaczeń):

```text
WINDOW_MS=10, ENVELOPE_RATE=16000, LOUD_FLOOR_DBFS=-60, SILENCE_BELOW_SPEECH_DB=15, MIN_GAP_MS=120,
DELAY_SEARCH_MS=(-500, 1000, 10), SNAP_TOLERANCE_MS=400, DIP_MS=50, DIP_SEARCH_MS=200,
PAD_BEFORE_MS=100, PAD_AFTER_MS=150, MIN_DBFS=-120, FULL_SCALE=32768

envelope(samples: Sequence[int], sample_rate: int) -> list[float]
silences(levels) -> list[Span]
estimate_delay(points, gaps) -> float
snap_spans(spans: Sequence[Span], levels: Sequence[float]) -> tuple[Placement, ...]
    Placement: clip: Span, speech: Span, start_kind: BoundaryKind, end_kind: BoundaryKind
    BoundaryKind: SILENCE | DIP | TIMING   (StrEnum)
    brak mowy w całym nagraniu -> padding na samych czasach (EDP:clips.py:517-520)
```

`anishift/services/audio/commands.py`: `envelope_wav_command(ffmpeg, source, destination)` →
`ffmpeg -nostdin -hide_banner -loglevel error -i <source> -ac 1 -ar 16000 -c:a pcm_s16le -f wav -y <destination>`.

`FfmpegClipService.split_clip` (`anishift/application/tts_clips.py`):

```text
1. data = source.read_bytes(); frames = frame_table(data); brak ramek -> ValueError
2. pcm = obwiednia według wyniku E1 (faza 1):
     E1 zdane -> jedno envelope_wav_command dla całego pliku, odczyt przez wave + array('h')
     E1 niezdane -> stream_ranges; dla każdego strumienia osobny plik tymczasowy MP3 i osobne dekodowanie;
                    próbki dopasowane do oczekiwanej długości strumienia (obcięcie albo dopełnienie zerami,
                    EDP:clips.py:338-346)
3. levels = envelope(pcm, 16000); placements = snap_spans([Span(s.start_ms, s.end_ms) for s in spans], levels)
4. dla każdej pary (span, placement): clip, _, _ = cut_frames(data, frames, placement.clip.start_ms, placement.clip.end_ms)
     span.destination.write_bytes(clip)
5. usuń katalog z WAV; zwróć SplitResult(written, boundaries_without_silence = liczba krawędzi != SILENCE)
```

WAV obwiedni powstaje w `tempfile.TemporaryDirectory(prefix="anishift-envelope-")`, nie w katalogu `clips/`
repozytorium resume (tam wolno leżeć tylko plikom w układzie `TtsArtifactLayout`, `anishift/services/tts/artifacts.py:95-110`).

Limit czasu dekodowania obwiedni: `FfmpegClipService` ma dziś jeden `timeout_s=30` (`runtime.py:216-226`), dobry
dla klipów kwestii. Dekodowanie nagrania dokumentu (do około 54 minut audio) dostaje osobny parametr konstruktora
`recording_timeout_s` (wartość w `runtime.py`: 300 s); walidacja klipów zostaje przy 30 s.

Logowanie w `split_clip` (bez ścieżek i tekstu): `spans`, `boundaries_without_silence`, `delay_ms`, `duration_ms`.

### 13.8. Silnik `elevenreader` — moduły

#### `constants.py`

```text
ENGINE_ID = "elevenreader"
PROVIDER_MODEL_ID = "eleven_v4"
ENDPOINT_ID = "elevenreader-web-stream-v2"
ADAPTER_VERSION = "elevenreader-v1"
LIBRARY_URL = "https://elevenreader.io/reader/library"                 # EDP:auto.py:53
DOCUMENT_URL_TEMPLATE = LIBRARY_URL + "/{read_id}"                    # EDP:auto.py:169
ADD_ENDPOINT = "/v1/reader/reads/add/v2"                              # EDP:auto.py:56
STREAM_PATH = "/v1/reader/reads/stream/v2/"                           # capabilities.md:18
SUPPORTED_UPLOAD_SUFFIX = ".txt"
MAX_DOCUMENT_CHARS = 50_000        # połowa największego zmierzonego dokumentu (~97 000; capabilities.md:101)
READING_SPEED = "1"                # EDP:auto.py:86
PAGE_SPEED = 16.0                  # >16x nic nie daje (README.md:143); 64x potrafi zawisnąć przed końcem
LIBRARY_LOAD_S = 45; READY_TIMEOUT_S = 600; ACTION_TIMEOUT_S = 120     # EDP:auto.py:59-66
START_TIMEOUT_S = 60; PLAY_ATTEMPTS = 3; STALL_S = 300                # EDP:auto.py:77-84
END_IDLE_S = 10; END_SLACK_CHARS = 30                                 # EDP:auto.py:71-75
POLL_S = 1.0; SPEED_CHECK_S = 3.0; SPEED_TOLERANCE = 0.01             # EDP:auto.py:282, downloader.py:145-149
MIN_DEDUP_BYTES = 8 * 1024; TAIL_CHARS = 20_000; MIN_PROBE_CHARS = 10 # EDP:downloader.py:72-79
CONNECT_ATTEMPTS = 30; CONNECT_RETRY_S = 0.5                          # EDP:downloader.py:57-61
CHROME_LOCATIONS = (("PROGRAMFILES", r"Google\Chrome\Application\chrome.exe"),
                    ("PROGRAMFILES(X86)", r"Google\Chrome\Application\chrome.exe"),
                    ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe"))  # EDP:downloader.py:47-55
CHROME_STEM = "chrome"
CHROME_FLAGS = ("--no-first-run", "--no-default-browser-check")      # EDP:downloader.py:458-460, bez force-dark
HEADLESS_FLAGS = ("--headless=new", "--window-size=1600,1000", "--autoplay-policy=no-user-gesture-required")
SPEED_SCRIPT, SPEED_STATE_SCRIPT, PLAYER_STATE_SCRIPT     # dosłowny port EDP:downloader.py:99-143, auto.py:92-100;
                                                          # zmienne window.__anishiftSpeed* zamiast __edp*
VOICES: Final[dict[str, ElevenReaderVoice]] = {
    "fronczewski": ElevenReaderVoice(alias="fronczewski", label="Piotr Fronczewski", voice_id=<z fazy 0>, language="pl"),
    "adam":        ElevenReaderVoice(alias="adam",        label="Adam",              voice_id=<z fazy 0>, language=<z fazy 0>),
}
DEFAULT_VOICE_ALIAS = "fronczewski"
SESSION_FILE = "session.json"; PROFILE_DIR = "chrome-profile"; LOCK_FILE = "profile.lock"
SIGN_IN_TIMEOUT_S = 600
```

Selektory strony (`IMPORT_BUTTON = "Import"`, `UPLOAD_BUTTON = "Upload"`, `PLAY_BUTTON = "Play"`, pole
`input[type=file]`, `input[aria-label="Playback rate"]`, wzorzec przycisku prędkości `^\d+([.,]\d+)?x$`) pochodzą z
`EDP:src/auto.py:89-90`, `:116-118`, `:140-155`. Selektory wyboru głosu i logowania uzupełnia faza 0.

#### `config.py`

```text
@dataclass(frozen=True, slots=True)
class ElevenReaderConfig:
    voice: ElevenReaderVoice
    profile_root: Path
    headless: bool              # stała decyzji D9 z fazy 0; nie pole ustawień
    email: str = field(default="", repr=False)
    password: str = field(default="", repr=False)

    @classmethod from_tts_config(config: TtsConfig) -> ElevenReaderConfig
       provider_model_id.casefold() != "eleven_v4" -> TtsConfigError(field provider_model_id)
       max_concurrency != 1 -> TtsConfigError(field max_concurrency)       # U8
       engine_options niepuste -> TtsUnsupportedError
       native_rate/volume/pitch nie None -> TtsUnsupportedError
       elevenreader_profile_root is None -> TtsConfigError(field elevenreader_profile_root)
       voice = resolve_voice(config.voice_id)

resolve_voice(alias_or_id: str) -> ElevenReaderVoice
    alias (casefold) albo dokładne voice_id z VOICES; inaczej TtsVoiceError("Unknown ElevenReader voice")
```

#### `document.py`

```text
neutralize(text: str) -> str
    "[" -> "(", "]" -> ")"; każdy ciąg białych znaków -> " "; strip()
document_text(parts: Sequence[DocumentPart]) -> str
    "\n\n".join(neutralize(p.text) for p in parts) + "\n"        # EDP:clips.py:203-208 (wariant A, D4)
document_chars(parts: Sequence[DocumentPart]) -> int
    sum(len(neutralize(p.text)) for p in parts)                  # separatory akapitów nie wchodzą do limitu
```

Podział batcha na dokumenty należy do `TtsService` (zna resume i kolejność) i istnieje raz, jako prywatne
`_plan_documents` w `anishift/services/tts/service.py`. Limit `max_document_chars` liczy **sumę długości tekstów
kwestii** bez separatorów; `neutralize` nigdy nie wydłuża tekstu, więc silnik, sprawdzając `document_chars(parts)
<= MAX_DOCUMENT_CHARS`, nie odrzuci dokumentu złożonego przez `TtsService`.

#### `recorder.py` (czyste, bez Playwright)

```text
@dataclass(frozen=True, slots=True)
class AlignmentChunk: offset_ms: float; chars: tuple[str, ...]; start_ms: tuple[float, ...]; dur_ms: tuple[float, ...]

class DocumentRecorder:
    __init__(out: BinaryIO)
    on_frame(payload: str | bytes) -> None          # port Recorder.on_frame (EDP:downloader.py:181-201)
    chunks: tuple[AlignmentChunk, ...]               # w pamięci, nie na dysku
    received_chars: int
    total_bytes: int
    last_audio_at: float | None                      # zegar wstrzykiwany (monotonic)
    duplicates_skipped: int; reconnect_trims: int; frames_without_text: int; non_json_frames: int
```

Zachowanie identyczne z EDP: ramka `config` po odebranym tekście uzbraja dopasowanie powtórzenia
(`downloader.py:195-196`); `audio` dekodowane z base64; skrót SHA-1 audio + JSON znaków dla paczek ≥ 8 KiB
(`:203-211`); `repeated_prefix` z `rfind_all` (`:257-296`); przycięcie przez `cut_before_ms` z `utils/mp3_frames.py`
(`:298-312`); offset następnej paczki += `frames_duration_ms(chunk)` (`:230`). Różnice: brak `print`; liczniki
zamiast logów per ramka; `isFinal` ustawia flagę `final`; ramki binarne i nie-JSON tylko liczone.

#### `alignment.py` (czyste)

```text
load_timeline(chunks) -> tuple[str, list[float], list[float]]        # EDP:timestamps.py:99-117 bez RESUME_MARK
normalize_timeline(text) -> tuple[str, list[int]]                    # EDP:clips.py:218-231 (tagi break pomijane)
locate_parts(parts: Sequence[DocumentPart], chunks) -> tuple[PartTiming, ...]
    # EDP:clips.py:250-278: kursor do przodu, MAX_SKIP_CHARS=300, kotwice ANCHOR_CHARS=12 na brzegach
    # klucz kwestii = normalize(neutralize(part.text)); kwestia bez liter i cyfr nie trafia do dokumentu (niemowa)
    # nieznaleziona kwestia -> pominięta w wyniku (F3)
completeness(received_chars, char_count) -> Completeness: COMPLETE | MISSING | EXCESS
    MISSING gdy received < char_count; EXCESS gdy received > char_count (log ostrzeżenia, nie błąd)
```

#### `browser.py`

```text
class ChromeSession (async context manager, jeden na silnik)
    __init__(profile_root: Path, *, headless: bool, chrome: Path | None = None)
    async start() -> BrowserContext
        profile_root.mkdir(parents=True, exist_ok=True); restrict_directory(profile_root)   # najpierw katalog
        lock = ProcessLock(profile_root / LOCK_FILE); not lock.acquire() -> TtsProviderUnavailableError(retry_after_s=60,
              "ElevenReader browser profile is busy")
        profile = profile_root / PROFILE_DIR; profile.mkdir(exist_ok=True)
        chrome = find_installed(CHROME_LOCATIONS, CHROME_STEM) albo TtsConfigError("Google Chrome was not found")
        port = wolny port: socket bind ("127.0.0.1", 0), odczyt, zamknięcie
        Popen([chrome, f"--remote-debugging-port={port}", f"--user-data-dir={profile}", *CHROME_FLAGS,
               *(HEADLESS_FLAGS if headless else ()), "about:blank"],
              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
              # wzorzec z anishift/platform/qbittorrent_process.py:649; bez getattr `mypy --platform linux` odrzuci
              # atrybut dostępny tylko na Windows
        playwright = await async_playwright().start()   # import leniwy wewnątrz funkcji
        browser = connect_over_cdp(f"http://127.0.0.1:{port}") z CONNECT_ATTEMPTS × CONNECT_RETRY_S
             porażka -> TtsProviderUnavailableError(retry_after_s=60, "Chrome did not accept the automation connection")
        context = browser.contexts[0]; add_init_script(SPEED_SCRIPT z prędkością 1)
    async new_page() -> Page            # zamyka puste karty startowe (EDP:downloader.py:491-497)
    async close()                       # page/browser close, playwright.stop, terminate → wait 2 s → kill, lock.release;
                                        # każdy krok w try/finally, lock zwalniany zawsze; idempotentne
```

Proces Chrome jest dzieckiem rezydenta, więc Job Object zamyka go razem z rezydentem
(`anishift/platform/AGENTS.md:51-53`); `close()` jest drogą normalną.

#### `page.py`

```text
async open_library(page) -> LibraryState: READY | SIGNED_OUT | UNAVAILABLE
    goto(LIBRARY_URL); czekaj na widoczny "Import" do LIBRARY_LOAD_S
    SIGNED_OUT: adres strony albo widoczny element logowania (selektory z fazy 0)
async upload(page, document_file: Path) -> UploadedRead(read_id: str, char_count: int)
    EDP:auto.py:137-145; status odpowiedzi add/v2 != 2xx -> errors.map_http_status(status, retry_after)
async open_document(page, read_id) -> None          # goto, czekaj "Play" do READY_TIMEOUT_S
async set_reading_speed(page) -> None               # EDP:auto.py:148-157
async ensure_voice(page, voice: ElevenReaderVoice) -> None    # mechanizm z fazy 0 (sekcja 13.11)
async set_page_speed(page, speed: float) -> None    # window.__anishiftSetSpeed w każdej ramce (EDP:downloader.py:347-353)
async check_page_speed(page, speed) -> SpeedCheck   # EDP:downloader.py:389-404
async press_play(page) -> None                      # EDP:auto.py:190-195
async player_state(page) -> PlayerState(value: float, max: float)   # EDP:auto.py:92-100
```

#### `session.py`

```text
@dataclass(frozen=True, slots=True)
class SessionState: signed_in: bool; checked_at: datetime

read_session(profile_root: Path) -> SessionState | None          # brak/uszkodzony plik -> None
write_session(profile_root: Path, state: SessionState) -> None   # atomowo: .tmp + replace
async require_signed_in(page, config) -> None
    stan = open_library(page)
    READY -> write_session(True); return
    SIGNED_OUT i email+hasło i gałąź D2 włączona -> jedno logowanie formularzem (selektory z fazy 0) -> ponownie open_library
    SIGNED_OUT (dalej) -> write_session(False); TtsAuthError(suggestion="Ustawienia → Lektor → Zaloguj / sprawdź sesję")
    UNAVAILABLE -> TtsProviderUnavailableError(retry_after_s=60)
async sign_in(profile_root: Path, *, timeout_s: float = SIGN_IN_TIMEOUT_S) -> SignInOutcome
    ChromeSession(headless=False); open_library; READY -> SIGNED_IN
    inaczej co POLL_S sprawdzaj widoczność "Import" na bieżącej stronie do timeout_s albo zamknięcia okna
    wynik zapisany przez write_session; BUSY gdy lock zajęty; NO_CHROME gdy brak Chrome
SignInOutcome: StrEnum SIGNED_IN | SIGNED_OUT | BUSY | NO_CHROME | FAILED
```

#### `errors.py`

Tabela mapowania w sekcji 13.12. Jedna funkcja `map_http_status(status: int, retry_after: float | None) -> TtsError`
i `map_playwright_error(error) -> TtsError`. Komunikaty po angielsku (jak w całej domenie), bez URL-i i treści
odpowiedzi.

#### `service.py`

```text
class ElevenReaderTtsEngine:                         # spełnia DocumentTtsEngine
    engine_id = "elevenreader"
    capabilities = EngineCapabilities(locality=REMOTE, native_output_formats=(MP3,), supports_concurrency=False,
        supports_native_rate=False, supports_native_volume=False, supports_pitch=False, supports_voice_settings=False,
        requires_api_key=False, min_text_chars=1, max_text_chars=MAX_DOCUMENT_CHARS, max_text_bytes=None,
        availability_probe=AvailabilityProbeKind.REMOTE, max_document_chars=MAX_DOCUMENT_CHARS)
    __init__(config: TtsConfig, *, browser_factory=ChromeSession)     # bez I/O
    synthesis_profile = SynthesisProfile(engine_id, ENDPOINT_ID, PROVIDER_MODEL_ID, resolved_voice_id=voice.voice_id,
        provider_output_id="mp3_44100_128", provider_source_format=MP3, adapter_version=ADAPTER_VERSION,
        voice_settings={"reading_speed": "1", "document_layout": "paragraph_per_line"})
    is_available / availability(live=False) -> CONFIG: READY gdy Chrome znaleziony, inaczej MISSING_BINARY
    availability(live=True) -> bez przeglądarki: stan CONFIG + read_session; MISSING_KEY, gdy ostatnie sprawdzenie
                               mówi „nie zalogowano” (przeglądarkę uruchamia tylko synteza i akcja logowania)
    list_voices() -> VoiceInfo dla obu głosów
    synthesize(...) -> TtsUnsupportedError("ElevenReader synthesizes whole documents")
    synthesize_document(request, cancel) -> EngineDocumentResult         # algorytm 13.9
    close() -> zamknięcie przeglądarki, stan CACHED SERVICE_UNAVAILABLE
```

### 13.9. Algorytm jednej próby dokumentu

```text
synthesize_document(request, cancel):
  0. walidacja: parts niepuste; voice_id == config.voice.voice_id albo alias; model == eleven_v4; options puste
     cancel.is_cancelled -> TtsCancelledError
  1. browser = await self._browser()          # leniwe, jedno na silnik; ponowne użycie między dokumentami
     page = await browser.new_page(); page.set_default_timeout(ACTION_TIMEOUT_S * 1000)
  2. await require_signed_in(page, config)
  3. document_chars(parts) > MAX_DOCUMENT_CHARS -> TtsInputError; text = document_text(parts)
     plik = TemporaryDirectory(prefix="anishift-elevenreader-") / "anishift.txt" (utf-8); usunięty w finally
     read = await upload(page, plik)          # każda próba wgrywa nowy dokument: nowy dokument zawsze startuje od
                                              # początku (EDP:README.md:79), a ponownie otwarty wraca do
                                              # last_listened_char_offset (capabilities.md:49)
  4. with request.recording.open("wb") as out: recorder = DocumentRecorder(out)
     page.on("websocket", ws -> STREAM_PATH in ws.url ? ws.on("framereceived", recorder.on_frame) : pomiń)
        # adres WS tylko porównywany w pamięci; nigdy logowany
  5. await open_document(page, read.read_id); await set_reading_speed(page); await ensure_voice(page, config.voice)
     await set_page_speed(page, PAGE_SPEED); await press_play(page); attempts_play = 1; played_at = now
  6. pętla co POLL_S:
       cancel.is_cancelled -> TtsCancelledError
       co SPEED_CHECK_S: check_page_speed -> brak skryptu: wstrzyknij; zła prędkość: ustaw ponownie
       postęp: recorder.received_chars zmienił się -> await request.progress(received, read.char_count)
       brak audio: now - played_at >= START_TIMEOUT_S -> attempts_play < PLAY_ATTEMPTS ? press_play : TtsTimeoutError
       stan = player_state; player_done = max > 0 and max - value <= END_SLACK_CHARS
       text_done = read.char_count > 0 and received >= read.char_count
       (player_done or text_done) and now - last_progress >= END_IDLE_S -> koniec
       now - last_progress >= STALL_S -> TtsTimeoutError("ElevenReader recording stalled")
  7. completeness MISSING -> TtsClipValidationError("ElevenReader recording is incomplete")
     EXCESS -> log ostrzeżenia z liczbami
  8. timings = locate_parts(parts, recorder.chunks); brak żadnej -> TtsClipValidationError
  9. page.close(); return EngineDocumentResult(..., parts=timings, request_time_ms)
  finally: odpięcie nasłuchu, zamknięcie karty; przeglądarka zostaje do close(), CHYBA ŻE próba skończyła się
           anulowaniem (`TtsCancelledError`, `asyncio.CancelledError`) albo błędem przeglądarki — wtedy silnik od razu
           wywołuje `ChromeSession.close()` (zamknięcie Chrome i zwolnienie blokady), bo `TtsService.close()` może
           przerwać pętlę po `shutdown_deadline_s` przed `engine.close()` (`service.py:299-326`, `scheduler.py:154-167`)
  wyjątki Playwright -> map_playwright_error
```

Każde długie oczekiwanie Playwright (biblioteka do 45 s, upload, „Play” do 600 s, akcje do 120 s) jest
wykonywane przez helper `_unless_cancelled(awaitable, cancel)`: `asyncio.wait({task, cancel.wait()},
return_when=FIRST_COMPLETED)`; gdy pierwsze skończy się anulowanie, zadanie Playwright jest anulowane, karta
zamykana, a silnik zgłasza `TtsCancelledError`. Bez tego anulowanie w trakcie czekania na „Play” trwałoby do 10
minut, bo scheduler nie przerywa aktywnej próby (`scheduler.py:169-188` obsługuje tylko kolejkę), a
`CancellationToken.wait()` istnieje właśnie do tego (`protocols.py:76-78`).

Ponowne kliknięcie „Play” to czynność odtwarzacza w ramach jednej próby, nie nowy upload ani nowe żądanie
syntezy; dlatego nie łamie zakazu Z6. Każde inne ponowienie należy do schedulera.

### 13.10. Uwierzytelnienie i sekrety

- **Gdzie leżą cookies:** w `config/elevenreader/chrome-profile/` (profil Chrome). AniShift nie czyta ani nie
  eksportuje cookies; zarządza nimi Chrome. Katalog `config/elevenreader/` jest w `.gitignore` i dostaje ACL
  `restrict_directory` przy utworzeniu katalogu (i przy każdym starcie, gdy katalog powstał bez ACL — wywołanie jest
  idempotentne i tanie, bo dotyczy jednego katalogu, nie rekursji `/T`) (wzór `anishift/platform/qbittorrent_process.py:633-653`).
- **Token:** brak tokenów po stronie AniShift; strona sama uwierzytelnia swoje żądania.
- **Logowanie automatyczne:** ważna sesja w profilu = brak działań człowieka (F15). Wariant z e-mailem i hasłem
  tylko w gałęzi D2 (faza 4b): `ANISHIFT_ELEVENREADER_EMAIL`, `ANISHIFT_ELEVENREADER_PASSWORD` w `.env`, pola
  `Settings.elevenreader_email` i `elevenreader_password` (`repr=False`), przekazywane przez `TtsConfig` jak
  `elevenlabs_api_key` (`anishift/application/runtime.py:657`). Edycja w Ustawienia → Połączenia → ElevenReader.
- **Odświeżanie:** robi strona ElevenReadera w Chrome; AniShift niczego nie odświeża.
- **Wygaśnięcie w środku odcinka:**
  - przed uploadem: `require_signed_in` zgłasza `TtsAuthError` (trwały, otwiera circuit); kwestie odcinka kończą
    się błędem, przebieg pokazuje sugestię; po zalogowaniu ponowienie (P w Przetwarzaniu) czyta tylko brakujące
    kwestie (F4);
  - w trakcie nagrywania: strona przestaje przysyłać audio albo przekierowuje → przestój (`TtsTimeoutError`,
    przejściowy) → ponowienie dokumentu przez scheduler → `require_signed_in` w następnej próbie wykrywa wylogowanie
    i zgłasza `TtsAuthError`. Brak częściowego zatwierdzania kwestii z urwanego nagrania: próba albo kończy się
    kompletnym nagraniem, albo jest odrzucona (krok 7).
- **Panel:** w kategorii Lektor przy `elevenreader`: wiersz „Sesja ElevenReader” z wartością z `session.json`
  („zalogowano · 25.10 14:03”, „nie zalogowano · …”, „nie sprawdzono”) i akcja „Zaloguj / sprawdź sesję”.
- **Doctor:** F18, F19; czyta `session.json` i sprawdza Chrome przez `find_installed`; nie uruchamia przeglądarki.
- **Zero sekretów:** e-mail i hasło nigdy w `TtsConfig.__repr__` (`repr=False`), nigdy w `RunSettingsSnapshot`
  (snapshot odrzuca pola sekretów, `anishift/application/AGENTS.md:40-42`), nigdy w logach (logger redaguje klucze
  z `password`; dodatkowo kod nie przekazuje tych wartości do `bind`). Adres WebSocketu, `read_id`, odpowiedzi HTTP i
  tekst dokumentu nie są logowane.

### 13.11. Głosy

- Aliasy i etykiety: `fronczewski` → „Piotr Fronczewski”, `adam` → „Adam” (F9). Uwaga: właściciel napisał
  „Franczewski”; poprawna nazwa w EDP i w źródłach to „Fronczewski” (`EDP:docs/research/capabilities.md:10`).
- Identyfikatory `voice_id`: ustala faza 0 z odpowiedzi `GET voices`, którą strona sama pobiera
  (`EDP:docs/research/capabilities.md:65`), i wpisuje do `VOICES`. Język „Adama” również z tej odpowiedzi.
- Domyślny: `fronczewski` (D3).
- Wybór w panelu: pole „Głos” z dwoma wartościami (`field_catalog._tts_voice_values`), etykiety przez
  `UserSettings.tts_voice_label`.
- Wybór w odtwarzaczu (`page.ensure_voice`): mechanizm ustala faza 0 i wpisuje do planu fazy 4 jako jedną z dróg:
  - **G1 (preferowana):** wybór głosu w odtwarzaczu dokumentu przed „Play” (selektory z fazy 0);
  - **G2:** zmiana domyślnego głosu w ustawieniach konta przez interfejs, gdy odtwarzacz nie ma wyboru.
  Weryfikacja (F8): po starcie strumienia silnik porównuje identyfikator głosu z adresu WebSocketu (nazwa parametru
  z fazy 0; wartość tylko w pamięci) albo z elementu odtwarzacza; niezgodność → zamknięcie karty i `TtsVoiceError`.
- Istniejący wybór `elevenbytes`: F11 — `_normalize_tts_selection` w gałęzi `elevenbytes` traktuje alias albo ID
  głosu ElevenReadera jak głos obcego silnika i ustawia Dallin; gałąź `elevenreader` ustawia `fronczewski` dla
  każdego głosu spoza `VOICES`. Własne głosy i profile pozostają w `config/settings.json`.

### 13.12. Odporność: klasyfikacja błędów

| Sytuacja | Wykrycie | Błąd | Klasa | Reakcja schedulera |
|---|---|---|---|---|
| brak Chrome | `find_installed` → None | `TtsConfigError` | trwały | circuit, sugestia instalacji Chrome |
| profil zajęty (logowanie w panelu, inny Chrome) | `ProcessLock.acquire()` False, CDP nie odpowiada | `TtsProviderUnavailableError(retry_after_s=60)` | przejściowy | ponowienie po ≥ 60 s |
| serwis niedostępny (502 itp.) | brak „Import” 45 s bez przekierowania, status 5xx | `TtsProviderUnavailableError(retry_after_s=60)` | przejściowy | ponowienie |
| wylogowano | `open_library` → SIGNED_OUT, status 401 | `TtsAuthError` | trwały | circuit; sugestia logowania |
| odmowa dostępu / blokada konta | status 403 przy uploadzie | `TtsAuthError` (`details={"status": 403}`) | trwały | circuit; sugestia sprawdzenia konta i powrotu na `elevenbytes` |
| brak kredytów | status 402 przy uploadzie (do potwierdzenia, sekcja 22) | `TtsQuotaError` | trwały | circuit; sugestia doładowania lub `elevenbytes` |
| limit żądań | status 429 | `TtsRateLimitError(retry_after_s=Retry-After)` | przejściowy | ponowienie z `max(backoff, retry_after)` |
| brak audio po 3 × „Play” | pętla 13.9 krok 6 | `TtsTimeoutError` | przejściowy | ponowienie |
| przestój 5 minut | pętla 13.9 krok 6 | `TtsTimeoutError` | przejściowy | ponowienie |
| niekompletne nagranie | krok 7 | `TtsClipValidationError` | przejściowy | ponowienie (nowy upload tego samego tekstu) |
| żadna kwestia nie znaleziona | krok 8 | `TtsClipValidationError` | przejściowy | ponowienie |
| zły głos | `ensure_voice` / weryfikacja | `TtsVoiceError` | trwały | circuit |
| awaria przeglądarki (Playwright `Error`) | wyjątek | `TtsProviderUnavailableError(retry_after_s=60)` | przejściowy | ponowienie z nową przeglądarką |
| timeout akcji Playwright | `TimeoutError` Playwright | `TtsTimeoutError` | przejściowy | ponowienie |
| anulowanie | `cancel.is_cancelled` | `TtsCancelledError` | trwały | koniec bez ponowienia |
| cięcie nie powiodło się | wyjątek splittera | `TtsClipValidationError` (w `accept_result`) | przejściowy | ponowienie dokumentu |
| jedna kwestia nie znaleziona | brak w `parts` | `TtsClipValidationError` tej kwestii | — | kwestia `FAILED`, reszta zatwierdzona |

Po awarii przeglądarki silnik zamyka `ChromeSession` i tworzy nową w następnej próbie.

Konfiguracja przebiegu dla `elevenreader` w `anishift/application/runtime.py`:

```text
_TTS_REQUEST_TIMEOUT_S["elevenreader"] = 3600.0     # dokument 50 000 znaków ≈ 54 min audio / 4,6 ≈ 12 min + narzut
_TTS_RETRY_BACKOFF_S["elevenreader"] = (60.0, 120.0, 300.0, 600.0)
scheduler_timeout_enabled = True                    # limit całej próby; przestój łapie silnik
shutdown_deadline_s = 15.0                          # czas na zamknięcie Chrome przy końcu przebiegu (domyślnie 5 s)
max_concurrency = 1, queue_capacity = 2
elevenreader_profile_root = elevenreader_dir()
```

### 13.13. Limity, ban, zapas, wznawianie, idempotencja, rezydent

- **Limity:** jeden dokument naraz (U8); żadnych równoległych kart; brak dodatkowych żądań poza tymi, które
  wykonuje strona; prędkość strony 16x.
- **Ban:** `TtsAuthError` z 403 i `TtsQuotaError` otwierają circuit, więc w jednym przebiegu nie ma dalszych prób;
  automat rezydenta nie ponawia przebiegu sam (ponowienie jest decyzją użytkownika:
  `anishift/application/AGENTS.md:55-57`).
- **Zapas `elevenbytes` (D1, ręczny):** komunikat błędu kończy się zdaniem „Możesz przełączyć silnik lektora na
  ElevenBytes w Ustawieniach → Lektor”. Zmiana silnika unieważnia artefakty TTS (`field_catalog._TTS_INVALIDATES`),
  więc ponowienie czyta cały odcinek jednym głosem.
- **Wznawianie po przerwaniu:** zamknięcie rezydenta → `shutdown` kończy aktywne taski bez anulowania, reszta
  `PAUSED` (`anishift/application/AGENTS.md:38-39`); jeśli proces zginie, Job Object kończy Chrome; zatwierdzone
  kwestie są w manifeście resume; „Dokończ poprzednią pracę” czyta tylko brakujące kwestie (F4).
- **Idempotencja kwestii:** klucz resume = `request_id` + fingerprint (tekst kwestii, profil z głosem i
  `document_layout`); ponowny commit tej samej kwestii zastępuje plik atomowo (`resume.py:205-279`). Każda próba
  dokumentu wgrywa nowy dokument, bo ponownie otwarty dokument wznawia od zapisanej pozycji
  (`last_listened_char_offset`, `EDP:docs/research/capabilities.md:49`), a nowy zawsze startuje od początku
  (`EDP:README.md:79`). Koszt: najwyżej `max_retries + 1` wpisów w bibliotece na dokument (D5).
- **Skutki uboczne na koncie:** `set_reading_speed` zapisuje prędkość 1x w ustawieniach konta ElevenReadera
  (`playback_speed_rate` w `user_config`, `EDP:docs/research/capabilities.md:62`), więc aplikacja właściciela na
  telefonie też zacznie od 1x; droga G2 wyboru głosu zmienia domyślny głos konta. Oba skutki trafiają do README i
  outcome; plan ich nie cofa (każde cofnięcie to kolejna automatyzacja strony).
- **Rezydent i scheduler zadań:** zasób `tts:elevenreader` serializuje pliki (`planner.py:832`); długa synteza
  (minuty) nie blokuje tłumaczenia kolejnych plików; ledger `config/watch/` dostaje tylko nie-sekretne ustawienia
  przebiegu (silnik, ID głosu); `decisions.jsonl` bez zmian.

### 13.14. Zachowanie UI w Ustawieniach

- Stan początkowy (Lektor, silnik `elevenreader`): Silnik, Model / endpoint (`eleven_v4`), Głos, Ponowień, Tempo
  końcowe, Korekta głośności głosu, Kodek, Bitrate, sekcja „SESJA”: wiersz „Sesja ElevenReader” (tylko odczyt) i
  akcja „Zaloguj / sprawdź sesję”. Brak „Syntez jednocześnie” i „VPN ElevenBytes”.
- Interakcja: Enter na akcji → `_Feedback("Otwieram Chrome… zaloguj się w oknie przeglądarki", "info")`, praca w
  wątku jak `_start_probe`; wynik: `✓ Zalogowano`, `✗ Nie zalogowano`, `✗ Lektor właśnie nagrywa — spróbuj po
  zakończeniu`, `✗ Nie znaleziono Google Chrome`, `✗ Nie udało się sprawdzić sesji`.
- Loading: wiersz akcji wyłączony, gdy `_busy`.
- Błąd: feedback w stylu `error`; nic nie zapisuje się do `.env`.
- Klawiatura i mysz: istniejące mechanizmy menu; brak nowych klawiszy.
- Wygląd: bez zmian stylu panelu (pamięć właściciela: wygląd panelu zostaje).

### 13.15. Edge cases

| Przypadek | Oczekiwane zachowanie | Dowód |
|---|---|---|
| batch bez kwestii mowy | jak dziś: same `SKIPPED`, bez przeglądarki | unit (service) |
| wszystkie kwestie z resume | brak przeglądarki i uploadu | unit (service, fałszywy silnik liczy wywołania) |
| część z resume | dokument tylko z brakujących | unit |
| kwestia z `[Muzyka]` | w dokumencie `(Muzyka)`, lokalizacja działa | unit (document, alignment) |
| kwestia z wielokropkiem i myślnikiem | bez zmian tekstu | unit |
| dwie identyczne kwestie obok siebie | lokalizacja kursorem do przodu daje dwa różne zakresy | unit (alignment) |
| powtórzenie po ponownym połączeniu | audio i znaki przycięte, liczba `reconnect_trims` | unit (recorder) |
| duplikat paczki ≥ 8 KiB | pominięty | unit |
| duplikat paczki < 8 KiB (krótka pauza) | zachowany | unit |
| ramka bez `alignment` | audio zapisane, czas zachowany | unit |
| `normalizedAlignment` zamiast `alignment` | obsłużone | unit |
| `char_count` mniejsze niż odebrane | ostrzeżenie, nie błąd | unit |
| `char_count` większe niż odebrane | `TtsClipValidationError` | unit (engine, fałszywa strona) |
| kwestia nieznaleziona | ta kwestia `FAILED`, reszta zatwierdzona, batch `PARTIAL` | unit (service) |
| szyld nieznaleziony | jak dziś dla każdego silnika: batch szyldów `PARTIAL`, `build_narration_manifest` odrzuca wynik (`tts_handler.py:408-409`), zadanie TTS kończy się błędem, ponowienie czyta tylko brakujący szyld | unit (service) + istniejące testy handlera |
| dokument > 50 000 znaków | podział na kilka dokumentów | unit (service) |
| pojedyncza kwestia > 50 000 znaków | `TtsInputError` tej kwestii | unit (service) |
| anulowanie w trakcie nagrywania | `TtsCancelledError` w ≤ 2 × `POLL_S`, karta zamknięta | unit (engine) |
| przeglądarka padła | `TtsProviderUnavailableError`, nowa sesja w kolejnej próbie | unit (engine) |
| profil zajęty | `TtsProviderUnavailableError(retry_after_s=60)` | unit (browser, fałszywy lock) |
| zmiana głosu w ustawieniach | nowy fingerprint, brak trafień resume | unit (fingerprint) |
| `elevenreader` → `elevenbytes` | głos Dallin | unit (user_settings) |
| `elevenbytes` z aliasem `fronczewski` w pliku | głos Dallin | unit (user_settings) |
| nagranie bez ciszy między dwiema kwestiami | granica w „dołku”, licznik `boundaries_without_silence` | unit (segmentation) |
| nagranie z kilkoma strumieniami ID3 | `stream_ranges` > 1, cięcie poprawne | integration (split_clip) |
| CDP port zajęty w wyścigu | ponowienie połączenia, potem `TtsProviderUnavailableError` | unit (browser) |
| doctor bez Chrome przy innym silniku | SKIP | unit (doctor) |

## 14. Zakres wykonania

### 14.1. In scope

- Faza 0: spike na koncie właściciela (fakty z sekcji 22), baseline bramek.
- `anishift/utils/mp3_frames.py` i refaktor `anishift/services/audio/mp3.py`.
- `anishift/services/audio/segmentation.py`, `envelope_wav_command`, `FfmpegClipService.split_clip`.
- Kontrakt dokumentu w domenie TTS, `TtsQuotaError`, uogólniony scheduler, ścieżka dokumentu w `TtsService`.
- Pakiet `anishift/services/tts/engines/elevenreader/` z testami.
- `anishift/platform/installed.py`, `anishift/platform/private_dir.py` i refaktor qBittorrent.
- `paths.py`, `.gitignore`, `config/README.md`, `runtime.py`, `application/service.py`, `user_settings.py`,
  `field_catalog.py`, `cli/interactive/settings.py`, `setup/doctor.py`.
- Gałąź D2 (logowanie danymi) — tylko gdy faza 0 da wynik „konto e-mail, formularz bez captchy”.
- Dokumentacja: AGENTS.md dotkniętych obszarów, `docs/reference/settings.md`, README EN i PL, `docs/ideas.md`,
  `docs/README.md`, `outcomes/` tego workstreamu.

### 14.2. Out of scope

- Audiobooki z rozdziałami, karaoke, eksport słownych czasów, monitor kredytów.
- Usuwanie dokumentów z biblioteki ElevenReadera (D5).
- Zmiana `TtsTaskHandler`, plannera, ownera rezydenta, osi czasu i miksu.
- Etap 6 jakości (głośność lektora).
- Plikowy wariant ACL w `local_control.py`.
- Linux.

### 14.3. Forbidden

- Z1–Z7 ze specyfikacji.
- Zmiana zachowania istniejących silników i ich testów (I1).
- Nowe zależności poza `playwright`; `miniaudio` jest zakazane (FFmpeg już jest).
- `playwright install` i pobieranie przeglądarek Playwright.
- Logowanie `ws.url`, `read_id`, odpowiedzi HTTP, tekstu dokumentu, e-maila, ścieżek absolutnych.
- Uruchamianie testów sieciowych silnika bez jawnej zgody właściciela w tej sesji (koszt kredytów, ryzyko konta).
- Zmiana plików, które czyta działający rezydent (`config/settings.json`, `.env`, `config/watch/`), bez prośby do
  właściciela o zamknięcie rezydenta (pamięć właściciela: zmiany plików runtime przy działającym rezydencie zepsuły
  wcześniej pięć tłumaczeń).
- Worktrees i `uv --active` (pamięć właściciela); praca w głównym checkoucie na gałęzi roboczej.
- Commit na `main`; stopki AI w commitach i PR.

### 14.4. Deferred

- Ponowne użycie wgranego dokumentu (wymaga przewinięcia odtwarzacza na początek; mechanizm nieznany).
- Słowne czasy w raporcie jakości.
- Usuwanie dokumentów z biblioteki po sukcesie.
- Odczyt `current_credits` przed i po odcinku.

### 14.5. Dozwolone decyzje lokalne

- Nazwy prywatnych helperów, kolejność funkcji w modułach, podział `page.py`/`session.py`, jeśli granice z sekcji
  13.8 zostają.
- Dokładne brzmienie angielskich komunikatów błędów i polskich komunikatów panelu w granicach sekcji 13.14.
- Dokładne selektory strony z fazy 0, o ile żaden nie wymaga obchodzenia zabezpieczeń.
- Wartości stałych czasowych z EDP ±50%, jeśli test fazy 6 pokaże potrzebę, z wpisem w outcome.
- Struktura fałszywych obiektów testowych.

### 14.6. Zatrzymaj się i wróć po decyzję, gdy

- faza 0 pokaże, że wybór głosu wymaga czegokolwiek poza klikaniem w interfejs strony;
- faza 0 pokaże, że upload lub odtwarzanie nie działa w Chrome sterowanym przez CDP;
- konto zostanie zablokowane albo strona pokaże ostrzeżenie o naruszeniu zasad;
- E1 i wariant per strumień oba nie spełnią kryterium dryfu;
- `split_clip` na prawdziwym nagraniu daje więcej niż 10% granic bez ciszy przy wariancie akapitów (EDP: 19 na
  304, `EDP:docs/report.md:64`);
- refaktor schedulera zmienia zachowanie choćby jednego istniejącego testu schedulera lub serwisu;
- potrzebna byłaby zmiana `TtsTaskHandler`, `plan_timeline` albo `SpeechBatch`;
- `playwright` nie instaluje się albo nie działa na Python 3.14 w CI.

## 15. Kontekst do przeczytania

| Kolejność | Źródło | Po co | Zakres |
|---|---|---|---|
| 1 | `.agents/skills/simple/SKILL.md`, `.agents/skills/coding/SKILL.md`, `.agents/skills/coding/references/python.md` | standard pracy | full |
| 2 | `AGENTS.md`, `anishift/AGENTS.md`, `tests/AGENTS.md` | reguły repo | full |
| 3 | `docs/work/11-elevenreader-tts/{intent,specification,file-map,plan}.md` | kontrakt | full |
| 4 | `anishift/services/tts/AGENTS.md`, `engines/AGENTS.md`, `engines/elevenbytes/AGENTS.md` | granice TTS | full |
| 5 | `anishift/services/tts/{types,protocols,config,errors,scheduler,service}.py` | kontrakt i ścieżka per kwestia | full |
| 6 | `anishift/services/tts/{resume,fingerprint,artifacts}.py` | resume | symbole `lookup`, `commit_clip`, `temporary_clip_path`, `SynthesisProfile` |
| 7 | `anishift/services/tts/engines/elevenbytes/{service,config}.py` | wzorzec adaptera | full |
| 8 | `anishift/application/{tts_handler,tts_clips,runtime}.py` | kompozycja | full `tts_clips.py`; `runtime.py:208-290`, `:636-660`; `tts_handler.py:195-445` |
| 9 | `anishift/services/audio/{AGENTS.md,mp3.py,commands.py,probe.py}` | audio | full `mp3.py`; komendy i `probe_pcm_wav` |
| 10 | `EDP:src/downloader.py`, `EDP:src/auto.py`, `EDP:src/timestamps.py`, `EDP:src/clips.py` | logika do portu | full |
| 11 | `EDP:docs/research/capabilities.md`, `EDP:docs/report.md`, `EDP:README.md` | fakty trasy | full |
| 12 | `anishift/config/{AGENTS.md,user_settings.py,field_catalog.py}` | ustawienia | `user_settings.py:150-490`; `field_catalog.py:220-260`, `:899-1110`, `:1340-1401` |
| 13 | `anishift/cli/interactive/settings.py` | panel | `:60-130`, `:150-300`, `:340-520`, `:940-1240`, `:1620-1700` |
| 14 | `anishift/setup/{AGENTS.md,doctor.py}` | doctor | full |
| 15 | `anishift/platform/{AGENTS.md,process_lock.py,qbittorrent_config.py,qbittorrent_process.py}` | platforma | `process_lock.py` full; `qbittorrent_config.py:200-250`; `qbittorrent_process.py:620-660` |
| 16 | `tests/services/tts/{test_tts_scheduler,test_tts_service,test_tts_contract,test_tts_registry,test_tts_elevenbytes}.py` | wzorce testów | full |

### Warunkowo

| Warunek | Źródło | Po co |
|---|---|---|
| gałąź D2 | `anishift/config/{settings.py,env_file.py}`, `anishift/application/service.py:600-830`, `tests/application/test_environment_secrets.py` | sekrety `.env` |
| E1 niezdane | `EDP:src/clips.py:327-346` | dekodowanie per strumień |
| zmiana panelu | `tests/cli/test_interactive_settings_*.py`, `tests/cli/test_panel_keys.py` | testy układu |
| zmiana `paths.py` | `tests/test_paths.py` | konwencja testów ścieżek |

## 16. Impact scan

| Kontrakt / subsystem | Ryzyko wpływu | Obowiązek regresyjny |
|---|---|---|
| `TtsScheduler.submit` (zmiana sygnatury) | każdy silnik i test schedulera/serwisu | wszystkie testy `tests/services/tts/` bez zmian asercji zachowania |
| `ScheduledSynthesis.clip` → `result` | `service.py` i testy | wyszukanie `\.clip\b` w `anishift/services/tts` i `tests/services/tts` = 0 starych użyć |
| `EngineCapabilities` (nowe pole z domyślną) | fałszywe silniki w testach, konstruktory silników | konstruktory bez zmian; test kontraktu pól |
| `anishift/services/audio/mp3.py` | walidacja MP3 klipów wszystkich silników | `tests/services/audio/test_audio_mp3.py`, `test_audio_probe.py` bez zmian |
| `qbittorrent_process._protect_profile` | prywatny profil qBittorrent rezydenta | `tests/platform/test_qbittorrent_process.py`, `test_selective_qbittorrent.py` |
| `qbittorrent_config.installed_executable` | doctor, setup qBittorrent | `tests/platform/test_qbittorrent_config.py`, `tests/setup/test_doctor.py` |
| `UserSettings._normalize_tts_selection` | ładowanie `config/settings.json` właściciela | `tests/config/test_user_settings.py`; nowy test aliasu obcego silnika |
| `field_catalog` | panel, reset, walidacja | `tests/config/test_field_catalog.py`, `tests/cli/test_interactive_settings_*` |
| rejestr TTS (`TtsEngineId`) | `UserSettings` waliduje silnik przez rejestr (`user_settings.py:446`) | `tests/services/tts/test_tts_registry.py` |
| `AppService._run_settings_snapshot` | `RunSettingsSnapshot` w ledgerze | `tests/application/test_service.py`, `test_runtime_config.py` |
| `_tts_allowed_voice_ids` | odmowa głosu w `TtsTaskHandler` | `tests/application/test_tts_handler.py` |
| `.gitignore` | wyciek profilu do gita | `git check-ignore -v config/elevenreader/chrome-profile/x` |
| zależność `playwright` | lock, `pip-audit`, CI Ubuntu mypy | `uv run pip-audit` (jak w CI), mypy `--platform linux` |
| rezydent (Job Object, wątki) | proces Chrome po zamknięciu rezydenta | scenariusz ręczny fazy 6 |
| testy równoległe (xdist) | `ProcessLock` i pliki w `tmp_path` | testy bez współdzielonych ścieżek |
| `check_test_comments.py` | proza w nowych testach i `elevenreader_fakes.py` | hook pre-commit |

## 17. Testy

### 17.1. Zasady

- Każdy nowy plik testowy ma dokładnie jeden marker poziomu przez `pytestmark` (`unit`, `integration` albo `e2e`);
  `network` jest markerem zdolności dodawanym obok (`pyproject.toml:146-153`).
- Testy `network` są pomijane domyślnie (`tests/conftest.py:30-36`); test silnika dodatkowo wymaga zmiennej
  `ANISHIFT_ELEVENREADER_LIVE=1` i `pytest.skip` bez niej, bo kosztuje kredyty.
- Zero prozy: brak docstringów, komentarzy opisowych i samodzielnych stringów w testach, `conftest.py` i
  `elevenreader_fakes.py`; scenariusz w nazwie `test_<jednostka>_<scenariusz>_<oczekiwanie>` (hook
  `check_test_comments.py`).
- Bez `__init__.py` w nowych katalogach testów (`tests/AGENTS.md:7-8`); nowy katalog `tests/utils/` też bez niego.
- Izolacja przez `monkeypatch` i `tmp_path`; testy niezależne od kolejności (xdist).
- Fixture z nagranymi odpowiedziami: `tests/data/elevenreader/frames-anon.jsonl` — prawdziwe ramki z fazy 0 dla
  tekstu testowego, z polem `audio` zastąpionym syntetycznymi ramkami MP3 o tej samej liczbie ramek (głos `famous`
  nie trafia do repo, Z4), bez adresów, nagłówków i identyfikatorów. Skrypt anonimizacji jest jednorazowy w
  `scripts/tmp/` (gitignorowany) i nie jest commitowany.
- Materiał prawdziwego głosu do eksperymentów (E1, kalibracja cięcia) leży poza repo:
  `../mm_avh_working_space/temp/elevenreader/` (wzorzec `MM_AVH_TEMP`, `tests/conftest.py:17`); testy na nim są
  `integration` z `skipif(not path.is_file())`.

### 17.2. Testy kontraktu silnika

`tests/services/tts/test_tts_contract.py` (rozszerzenie):

- `test_document_types_have_exact_fields` — pola `DocumentPart`, `DocumentSynthesisRequest`, `PartTiming`,
  `EngineDocumentResult`, `ClipSpan`, `SplitResult` w kolejności z sekcji 13.4.
- `test_document_types_are_frozen_and_slotted`.
- `test_engine_capabilities_default_to_request_synthesis` — `max_document_chars is None` dla fałszywego silnika z
  dotychczasowym konstruktorem.
- `test_document_engine_protocol_extends_engine_contract` — fałszywy silnik dokumentowy spełnia `TtsEngine` i
  `DocumentTtsEngine`.
- istniejący `test_tts_domain_does_not_import_pipeline_or_other_domains` musi przejść z nowym pakietem.
- `test_elevenreader_package_does_not_import_playwright_at_import_time` — import `anishift.services.tts.engines.elevenreader`
  w procesie potomnym nie dodaje `playwright` do `sys.modules` (wzór: `tests/services/tts/test_tts_registry.py`).

### 17.3. Bramki

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest
```

Ostatnie dwie odpowiadają hookowi pre-push i CI (`AGENTS.md`, „Twarde strażniki”). Zawsze na `anishift/ tests/`,
nigdy na podkatalogu.

## 18. Plan wykonania

Kolejność i zależności:

```text
F0 preflight + spike (właściciel przy koncie)
 ├─> F1 audio: wspólne ramki MP3, segmentacja, split_clip, eksperyment E1
 ├─> F2 TTS: kontrakt dokumentu, scheduler, ścieżka dokumentu        (niezależna od F1, potrzebuje tylko protokołu)
 └─> F3 silnik: części czyste (config, document, recorder, alignment, errors)   (potrzebuje F0 dla fixture)
F1 + F2 + F3 ─> F4 silnik: przeglądarka, strona, sesja, platforma, rejestr
F4 ─> F4b gałąź D2 (tylko gdy F0 da „e-mail bez captchy”)
F4 ─> F5 kompozycja, ustawienia, panel, doctor
F5 ─> F6 checkpoint ucha właściciela
F6 ─> F7 dokumentacja, review, PR
```

F1, F2 i F3 mogą iść równolegle u różnych wykonawców (sekcja 20), bo dotykają rozłącznych plików; integruje F4.

---

### Faza 0 — Preflight i spike

**Cel:** potwierdzić baseline i zdobyć fakty, których kod EDP nie ustala, bez pisania kodu produkcyjnego.

**Wejście:** zgoda właściciela na sesję przy koncie (kilkaset znaków, około 0,03 kredytu); właściciel zamyka
rezydenta AniShift na czas F0 (zmiana plików runtime i porównanie bramek na spokojnym checkoucie).

**Działania:**

1. `git status` (czyste drzewo), `git log -1` (`4365a51`).
2. Utwórz gałąź `work/tts/01-elevenreader` z `main` (sekcja 19). Bez worktree.
2a. **Zanim powstanie jakikolwiek plik profilu:** dopisz `config/elevenreader/` do `.gitignore` (sekcja projektu,
   `.gitignore:289-296`), sprawdź `git check-ignore -v config/elevenreader/chrome-profile/Default` i zacommituj
   osobno jako `chore(repo): ignore the ElevenReader browser profile`. Repozytorium jest publiczne; profil zawiera
   cookies sesji.
3. Uruchom bramki z sekcji 17.3 na baseline; zapisz liczby testów i każdy failing test.
4. Napisz jednorazowy skrypt w `scripts/tmp/elevenreader_spike.py` (gitignorowany katalog `tmp/`,
   `.gitignore:151`), który:
   - tworzy `config/elevenreader/` i zawęża go tym samym poleceniem `icacls` co
     `anishift/platform/qbittorrent_process.py:643-649` (sprawdza, że Chrome działa z profilem bez dostępu SYSTEM i
     Administratorów — Chrome 127+ szyfruje cookies przez uprzywilejowaną usługę (App-Bound Encryption,
     <https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html>, odczyt 2026-10-25); wynik do `spike-results.md`
     jako S0.10);
   - uruchamia Chrome z nowym katalogiem `config/elevenreader/chrome-profile/` (nie z profilem EDP — D6), z
     `--remote-debugging-port=<wolny>`, okno widoczne;
   - podłącza Playwright async `connect_over_cdp`;
   - otwiera bibliotekę; właściciel loguje się ręcznie;
   - zapisuje do pliku **tylko** rzeczy z listy niżej, przefiltrowane w kodzie skryptu — nigdy cookies, nagłówki,
     wartości tokenów, adres e-mail.
5. Zbierz i zapisz w `docs/work/11-elevenreader-tts/research/spike-results.md` (po polsku, bez sekretów):
   - **S0.1 metody logowania:** jakie przyciski widzi strona logowania (Google / Apple / e-mail), adres strony
     logowania bez parametrów zapytania, czy formularz e-mail ma captchę; którą metodą loguje się właściciel;
   - **S0.2 sygnał wylogowania:** co widać w bibliotece bez sesji (przekierowanie, element) — selektor;
   - **S0.3 głosy:** z odpowiedzi `GET .../v1/reader/voices` (odczyt odpowiedzi strony w `page.on("response")`):
     `voice_id`, `name`, `language`, `category` dla wpisów, których `name` zawiera „Fronczewski” lub „Adam”;
   - **S0.4 wybór głosu:** czy odtwarzacz dokumentu ma wybór głosu (selektor przycisku i listy, nazwa w liście), czy
     tylko ustawienia konta (droga G1 albo G2, sekcja 13.11);
   - **S0.5 weryfikacja głosu:** nazwy parametrów zapytania adresu WebSocket (bez wartości poza porównaniem
     `voice_id` z S0.3: zapisz tylko „zgodny/niezgodny”) — czy niesie głos;
   - **S0.6 tryb bez okna:** krótki dokument (tekst testowy z sekcji 18.0.1) nagrany w `--headless=new` — sukces lub
     opis porażki (D9);
   - **S0.7 ramki:** zapis ramek WS dla tekstu testowego do `../mm_avh_working_space/temp/elevenreader/frames-raw.jsonl`
     (poza repo; zawiera głos), liczba paczek, liczba tagów ID3 w złożonym MP3, czy występuje `normalizedAlignment`;
   - **S0.8 odpowiedzi:** kształt JSON odpowiedzi `add/v2` (nazwy pól, bez wartości), statusy HTTP widziane w sesji;
   - **S0.9 model:** czy jakakolwiek odpowiedź lub ramka nazywa model (np. `eleven_v4`); jeśli nie — zapisz „brak”;
   - **S0.10 ACL profilu:** czy po zawężeniu ACL sesja przetrwała zamknięcie i ponowne uruchomienie Chrome.
6. Utwórz anonimizowaną fixture `tests/data/elevenreader/frames-anon.jsonl` z S0.7 (audio zastąpione syntetycznymi
   ramkami o tej samej liczbie ramek; skrypt w `scripts/tmp/`); nie commituj jej przed F3.
7. Przedstaw właścicielowi wyniki S0.1–S0.6 i poproś o decyzje D2, D3, D9 (oraz pozostałe, jeśli jeszcze otwarte).

#### 18.0.1. Tekst testowy

```text
Pierwsza kwestia testowa.

[Muzyka] Druga kwestia, z nawiasem.

Trzecia kwestia... z wielokropkiem — i myślnikiem.
```

Około 110 znaków plus tagi `<break>`; koszt pomijalny.

**Pliki:** `scripts/tmp/elevenreader_spike.py` (nie commitowany), `docs/work/11-elevenreader-tts/research/spike-results.md`
(commitowany z dokumentacją workstreamu), `tests/data/elevenreader/frames-anon.jsonl` (do F3).

**Kontrakty:** brak w kodzie produkcyjnym.

**Testy:** brak nowych; bramki baseline.

**Komendy dowodu:**

```bash
git status --short
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
git check-ignore -v scripts/tmp/elevenreader_spike.py
```

**Kryterium wyjścia:** `spike-results.md` ma odpowiedź na S0.1–S0.9 (albo jawne „nie da się ustalić” z
powodem); `VOICES` ma oba `voice_id`; wiadomo, czy droga G1 czy G2; właściciel podjął D2, D3, D9.

**Checkpoint właściciela (konto):**

```text
Uruchom: uv run python scripts/tmp/elevenreader_spike.py
Zrób: zaloguj się w otwartym oknie Chrome tak jak zwykle; odpowiedz, jakiej metody użyłeś.
Oczekiwany rezultat: skrypt kończy się komunikatem „spike done” i plikiem wyników bez sekretów.
Zwróć uwagę na: ostrzeżenia strony o nietypowej aktywności, prośby o weryfikację — zatrzymaj wtedy pracę.
Przekaż wynik jako: metoda logowania (Google/e-mail/inna), decyzje D2, D3, D9, ewentualne ostrzeżenia.
```

**Gate:** bez S0.3 i S0.4 nie startuje F4 (F1–F3 mogą trwać).

---

### Faza 1 — Audio: wspólne ramki MP3, segmentacja, cięcie

**Cel:** jedno źródło parsowania ramek MPEG i protokół cięcia nagrania w ciszy, z dowodem na dryf zegara.

**Wejście:** F0 krok 3 (baseline); dla E1 — nagranie z S0.7 albo `EDP:workspace/output/lektor_pl.mp3` skopiowane
przez właściciela do `../mm_avh_working_space/temp/elevenreader/`.

**Działania:**

1. `anishift/utils/mp3_frames.py`: przenieś logikę `_parse_frame_header` i tabele z
   `anishift/services/audio/mp3.py:37-176` (MPEG-1, MPEG-2, MPEG-2.5, Layer III, kanały), dodaj `iter_frames`
   (pomijanie ID3v2 jak `EDP:src/timestamps.py:77-80` i obcych bajtów), `frames_duration_ms`, `cut_before_ms`.
   Stałe z `Final` i docstringiem pod przypisaniem, nagłówek `# ── Constants ──`.
2. `anishift/services/audio/mp3.py`: `read_mp3_stream_properties` korzysta z `parse_frame_header`; zachowanie,
   komunikaty i kody `AudioProbeError` bez zmian; usuń zduplikowane tabele i `_parse_frame_header`; dodaj
   `Mp3Frame`, `frame_table`, `cut_frames`, `stream_ranges`.
3. `anishift/utils/_portable.py` i `anishift/utils/AGENTS.md`: wpis `mp3_frames.py`.
4. `anishift/services/audio/segmentation.py`: port funkcji z `EDP:src/clips.py:349-514` i `:517-520` z typami z
   sekcji 13.7; `Span`, `Placement`, `BoundaryKind`; bez I/O.
5. `anishift/services/audio/commands.py`: `envelope_wav_command`.
6. Eksperyment **E1** (sekcja 18.1.1); wynik zapisz w `research/e1-envelope-drift.md`.
7. `anishift/application/tts_clips.py`: `FfmpegClipService.split_clip` według wyniku E1 (sekcja 13.7); stała
   rezerwy ramek `RESERVOIR_FRAMES = 2` w `mp3.py`.
8. `anishift/services/audio/AGENTS.md`: segmentacja jako czysty moduł, cięcie ramkami bez transkodowania,
   wynik E1.

#### 18.1.1. Eksperyment E1: dryf zegara przy dekodowaniu całego pliku przez FFmpeg

```text
pytanie:     czy jedno dekodowanie całego nagrania FFmpeg do 16 kHz mono zachowuje zegar ramek MP3?
hipoteza:    tak, poza stałym przesunięciem startowym < 60 ms (opóźnienie enkodera), które estimate_delay wchłania
setup:       nagranie z kilkoma strumieniami (S0.7 albo lektor_pl.mp3), frame_table, stream_ranges
pomiar:      dla każdej granicy strumienia k: t_frames(k) z frame_table; t_pcm(k) = pozycja początku ciszy/mowy
             po granicy w PCM z jednego dekodowania vs w PCM z dekodowania samego strumienia k;
             dryf(k) = t_pcm_whole(k) - t_frames(k) - dryf(0)
kryterium:   max |dryf(k)| ≤ 20 ms dla wszystkich k -> jedno dekodowanie; inaczej dekodowanie per strumień
usuń potem:  skrypt pomiaru z scripts/tmp/
```

Wynik E1 jest decyzją techniczną planu, nie właściciela.

**Pliki:**

- `anishift/utils/mp3_frames.py` — DODAĆ
- `anishift/utils/_portable.py`, `anishift/utils/AGENTS.md` — ZMIENIĆ
- `anishift/services/audio/mp3.py` — ZREFAKTORYZOWAĆ + DODAĆ funkcje
- `anishift/services/audio/segmentation.py` — DODAĆ
- `anishift/services/audio/commands.py` — ZMIENIĆ
- `anishift/services/audio/AGENTS.md` — ZMIENIĆ
- `anishift/application/tts_clips.py` — ZMIENIĆ (wymaga typów `ClipSpan`, `SplitResult` z F2; do czasu scalenia F2
  `split_clip` może przyjmować lokalne typy z tą samą strukturą — wybór jednej drogi przy integracji w F4)
- `tests/utils/test_mp3_frames.py`, `tests/services/audio/test_audio_segmentation.py`,
  `tests/application/test_tts_clips_split.py` — DODAĆ
- `tests/services/audio/test_audio_mp3.py` — ZMIENIĆ (nowe testy; stare bez zmian)

Aby uniknąć zależności F1 od F2, wykonawca F1 commituje `split_clip` dopiero po scaleniu F2 albo implementuje F1 po
F2 na tej samej gałęzi. Domyślna kolejność commitów: commit 2 (wspólne ramki MPEG z F1) → commit 3 (scheduler z F2)
→ commit 4 (kontrakt dokumentu z F2 razem z `segmentation.py`, `envelope_wav_command` i `split_clip` z F1).

**Kontrakty:** sekcja 13.7.

**Testy:**

`tests/utils/test_mp3_frames.py` (`unit`):

- `test_parse_frame_header_reads_mpeg1_layer3_mono`
- `test_parse_frame_header_reads_mpeg2_layer3_stereo`
- `test_parse_frame_header_rejects_reserved_sample_rate`
- `test_parse_frame_header_rejects_non_layer3`
- `test_iter_frames_skips_id3_between_streams`
- `test_iter_frames_skips_stray_bytes`
- `test_frames_duration_ms_sums_1152_samples_per_mpeg1_frame`
- `test_cut_before_ms_drops_frames_starting_before_cut`
- `test_cut_before_ms_returns_empty_when_cut_is_after_end`

`tests/services/audio/test_audio_mp3.py` (`unit`, nowe):

- `test_frame_table_reports_byte_ranges_and_times`
- `test_cut_frames_keeps_two_reservoir_frames_before_span`
- `test_cut_frames_at_recording_start_has_no_reservoir`
- `test_stream_ranges_splits_on_id3_gap`

`tests/services/audio/test_audio_segmentation.py` (`unit`, sygnał syntetyczny: listy poziomów dBFS):

- `test_envelope_reports_one_level_per_10ms_window`
- `test_silences_find_gaps_of_at_least_120ms`
- `test_silences_ignore_gaps_shorter_than_120ms`
- `test_estimate_delay_recovers_300ms_audio_lag`
- `test_snap_spans_places_boundaries_in_silence`
- `test_snap_spans_uses_quietest_dip_without_silence`
- `test_snap_spans_falls_back_to_timings_without_speech`
- `test_snap_spans_pads_100ms_before_and_150ms_after_within_gaps`
- `test_snap_spans_keeps_boundaries_in_order`

`tests/application/test_tts_clips_split.py` (`integration`; wymaga FFmpeg z `anishift setup`, wzór istniejących
testów integracyjnych audio; `skipif` gdy `resolve_binary(Binary.FFMPEG)` zwraca `None`):

- `test_split_clip_cuts_synthetic_recording_into_line_clips` — nagranie z trzech tonów 440 Hz po 1 s rozdzielonych
  0,4 s ciszy, zakodowane FFmpeg do MP3 128 kb/s 44,1 kHz w `tmp_path`; spany przesunięte o −300 ms względem tonów;
  oczekiwane: trzy klipy, każdy dekoduje się (`validate_clip`) i trwa 1,0–1,6 s.
- `test_split_clip_reports_boundaries_without_silence` — dwa tony bez przerwy; `boundaries_without_silence >= 1`.
- `test_split_clip_removes_its_envelope_file` — po wywołaniu w katalogu `source` nie ma pliku WAV.
- `test_split_clip_raises_value_error_for_file_without_frames`.
- `test_split_clip_on_real_recording_cuts_every_line` — `skipif` bez materiału w
  `../mm_avh_working_space/temp/elevenreader/`; spany z `align.jsonl` EDP przez port `locate` (po F3) albo z pliku
  pomocniczego zbioru; oczekiwane: liczba klipów = liczba kwestii, każdy klip > 0 ms.

**Komendy dowodu:**

```bash
uv run pytest tests/utils tests/services/audio tests/application/test_tts_clips_split.py -q
uv run pytest tests/services/audio/test_audio_mp3.py tests/services/audio/test_audio_probe.py -q
uv run ruff check anishift/ tests/
uv run mypy anishift/ tests/
```

**Kryterium wyjścia:** stare testy audio bez zmian i zielone; nowe zielone; `research/e1-envelope-drift.md` z
liczbami i wyborem drogi; `grep -n "_MPEG1_BITRATES_KBPS" anishift/services/audio/mp3.py` nic nie zwraca (jedno
źródło tabel).

**Checkpoint właściciela:** brak (zmiana bez wpływu na słyszalny wynik).

---

### Faza 2 — Domena TTS: kontrakt dokumentu, scheduler, ścieżka dokumentu

**Cel:** `TtsService` umie zsyntetyzować batch silnikiem dokumentowym z resume per kwestia, a dotychczasowe silniki
działają identycznie.

**Wejście:** baseline zielony.

**Działania:**

1. `anishift/errors.py`: `ErrorCode.TTS_QUOTA_EXHAUSTED`.
2. `anishift/services/tts/errors.py`: `TtsQuotaError(TtsError, FatalError)`; eksport.
3. `anishift/services/tts/types.py`: pole `max_document_chars` (ostatnie, z domyślną `None`) i typy z sekcji 13.4.
4. `anishift/services/tts/protocols.py`: `DocumentTtsEngine`, `ClipSplitter`.
5. `anishift/services/tts/scheduler.py`: uogólnienie z sekcji 13.5; `_opens_circuit` z `TtsQuotaError`.
6. `anishift/services/tts/service.py`:
   - per kwestia: `_ProviderAttempt` daje `call`; `ScheduledSynthesis.result`;
   - parametr `splitter`; `_run_document_batch`, `_synthesize_document`, prywatne `_plan_documents`;
   - postęp dokumentu (sekcja 13.6).
7. `anishift/services/tts/config.py`: pola `elevenreader_*` (sekcja 13.4).
8. `anishift/services/tts/__init__.py`: eksport nowych typów, protokołów i błędu.
9. `anishift/services/tts/AGENTS.md`: sekcja „Silniki dokumentowe” — kontrakt, `ClipSplitter`, zasada „TtsService
   nigdy nie woła `synthesize` silnika dokumentowego”, scheduler przyjmuje `call`; doprecyzowanie zdania „TTS nie
   [...] przyjmuje timestampów” (`AGENTS.md:25-26`): domena nie przyjmuje czasów napisów; czasy znaków providera
   istnieją tylko wewnątrz próby dokumentu i nie wychodzą poza domenę.

**Pliki:** jak wyżej + `tests/services/tts/test_tts_scheduler.py`, `test_tts_service.py`, `test_tts_contract.py`,
`test_tts_config.py` (ZMIENIĆ), `tests/services/tts/test_tts_document_service.py` (DODAĆ).

**Kontrakty:** sekcje 13.4–13.6.

**Testy:**

Istniejące (`test_tts_scheduler.py`, `test_tts_service.py`): zmiana wyłącznie wywołań `submit` i nazwy pola
`result`; asercje zachowania identyczne. Diff tych plików ogranicza się do tych miejsc (sprawdzenie w review).

`tests/services/tts/test_tts_document_service.py` (`unit`; fałszywy silnik dokumentowy, fałszywy splitter piszący
syntetyczne ramki MP3, fałszywy walidator zwracający `ClipValidation` jak w istniejących testach serwisu):

- `test_document_engine_receives_all_missing_lines_in_one_document`
- `test_document_engine_is_not_started_when_every_line_resumes`
- `test_document_contains_only_lines_missing_from_resume`
- `test_non_speech_lines_are_skipped_without_document`
- `test_line_not_found_in_recording_fails_only_that_line`
- `test_batch_with_missing_line_is_partial`
- `test_document_over_limit_is_split_in_batch_order`
- `test_single_line_over_document_limit_fails_with_input_error`
- `test_transient_document_error_retries_whole_document`
- `test_split_failure_retries_whole_document`
- `test_auth_error_opens_circuit_for_following_documents`
- `test_quota_error_opens_circuit`
- `test_document_progress_reports_received_lines_from_characters`
- `test_progress_observer_failure_does_not_stop_synthesis`
- `test_cancel_during_document_commits_nothing`
- `test_document_without_splitter_fails_as_unsupported`
- `test_document_engine_synthesize_is_never_called`
- `test_provider_calls_are_counted_once_per_document`
- `test_committed_lines_resume_after_failed_document_retry`
- `test_recording_and_uncommitted_clips_are_removed_after_document`

`test_tts_contract.py`: testy z sekcji 17.2.

`test_tts_scheduler.py` (nowe): `test_submit_runs_any_provider_call_with_retry`,
`test_quota_error_opens_circuit`.

**Komendy dowodu:**

```bash
uv run pytest tests/services/tts -q
uv run pytest tests/application/test_tts_handler.py tests/application/test_runtime_config.py -q
git diff --stat main -- tests/services/tts/test_tts_scheduler.py tests/services/tts/test_tts_service.py
uv run mypy anishift/ tests/
uv run ruff check anishift/ tests/
```

**Kryterium wyjścia:** wszystkie testy TTS i handlera zielone; żaden istniejący test nie stracił asercji; nowy
plik testów zielony; `grep -rn "request_factory" anishift/services/tts` zwraca 0 wyników.

**Checkpoint właściciela:** brak.

---

### Faza 3 — Silnik: części czyste

**Cel:** przetestowana offline logika silnika: konfiguracja, dokument, ramki, wyrównanie, mapowanie błędów.

**Wejście:** F0 (fixture `frames-anon.jsonl`, `voice_id` z S0.3), F1 krok 1 (`utils/mp3_frames.py`), F2 krok 3–4
(typy i protokoły).

**Działania:**

1. `engines/elevenreader/constants.py` — sekcja 13.8; `VOICES` z S0.3; skrypty JS jako stałe `Final[str]`.
2. `engines/elevenreader/config.py` — sekcja 13.8.
3. `engines/elevenreader/document.py` — `neutralize`, `document_text`.
4. `engines/elevenreader/recorder.py` — `DocumentRecorder`, `AlignmentChunk`.
5. `engines/elevenreader/alignment.py` — `load_timeline`, `normalize_timeline`, `locate_parts`, `completeness`.
6. `engines/elevenreader/errors.py` — `map_http_status`, `map_playwright_error` (Playwright importowany tylko pod
   `TYPE_CHECKING`; dopasowanie po klasie z leniwie importowanego modułu wewnątrz funkcji).
7. `engines/elevenreader/__init__.py` — eksport bez importu Playwright.
8. `engines/elevenreader/AGENTS.md` — pułapki: brak retry w transporcie, brak logowania URL-i, `read_id` i tekstu,
   jedna przeglądarka, blokada profilu, głos z `VOICES`, 16x, prędkość czytania 1x, nawiasy.
9. Commit fixture `tests/data/elevenreader/frames-anon.jsonl` (po kontroli: brak `wss://`, `https://`, `Cookie`,
   `token`, adresu e-mail).

**Pliki:** sekcja 13.8 (bez `browser.py`, `page.py`, `session.py`, `service.py`), testy niżej,
`tests/services/tts/elevenreader_fakes.py` (pomocnicze budowanie ramek, bez prozy).

**Kontrakty:** sekcja 13.8.

**Testy** (`unit`):

`tests/services/tts/test_tts_elevenreader_config.py`:

- `test_config_resolves_alias_to_voice`
- `test_config_accepts_exact_voice_id`
- `test_config_rejects_unknown_voice_with_voice_error`
- `test_config_rejects_model_other_than_eleven_v4`
- `test_config_rejects_concurrency_above_one`
- `test_config_rejects_engine_options`
- `test_config_rejects_native_rate_volume_pitch`
- `test_config_requires_profile_root`
- `test_config_repr_hides_email_and_password`

`tests/services/tts/test_tts_elevenreader_document.py`:

- `test_neutralize_replaces_square_brackets_with_parentheses`
- `test_neutralize_collapses_whitespace_and_newlines`
- `test_neutralize_keeps_polish_letters_ellipsis_and_dashes`
- `test_document_text_separates_lines_with_blank_line`
- `test_document_text_ends_with_newline`

`tests/services/tts/test_tts_elevenreader_recorder.py` (ramki z `elevenreader_fakes.py` i `frames-anon.jsonl`):

- `test_recorder_writes_audio_in_arrival_order`
- `test_recorder_offsets_chunks_by_mp3_frame_duration`
- `test_recorder_accepts_normalized_alignment`
- `test_recorder_skips_identical_large_chunk`
- `test_recorder_keeps_identical_small_chunk`
- `test_recorder_trims_text_repeated_after_reconnect`
- `test_recorder_skips_chunk_entirely_repeated_after_reconnect`
- `test_recorder_counts_binary_and_non_json_frames_without_failing`
- `test_recorder_marks_final_frame`
- `test_recorder_keeps_audio_of_chunk_without_text`
- `test_recorder_replays_anonymized_fixture_to_expected_char_count`

`tests/services/tts/test_tts_elevenreader_alignment.py`:

- `test_load_timeline_makes_char_times_absolute`
- `test_locate_parts_finds_each_line_between_break_tags`
- `test_locate_parts_matches_neutralized_brackets`
- `test_locate_parts_uses_anchors_when_middle_differs`
- `test_locate_parts_skips_line_missing_from_recording`
- `test_locate_parts_assigns_identical_neighbour_lines_in_order`
- `test_locate_parts_returns_start_before_end`
- `test_completeness_reports_missing_and_excess`
- `test_locate_parts_on_anonymized_fixture_finds_three_lines`

`tests/services/tts/test_tts_elevenreader_errors.py`:

- `test_status_401_maps_to_auth_error`
- `test_status_403_maps_to_auth_error_with_status_detail`
- `test_status_402_maps_to_quota_error`
- `test_status_429_maps_to_rate_limit_with_retry_after`
- `test_status_5xx_maps_to_provider_unavailable_with_60s_retry`
- `test_error_messages_never_contain_urls`

**Komendy dowodu:**

```bash
uv run pytest tests/services/tts -q -k elevenreader
uv run python -I -c "import sys, anishift.services.tts.engines.elevenreader as m; assert 'playwright' not in sys.modules"
uv run ruff check anishift/ tests/
uv run mypy anishift/ tests/
git grep -n -i -E "wss://|cookie|bearer|@gmail" -- tests/data/elevenreader
```

**Kryterium wyjścia:** testy zielone; ostatnie polecenie nie zwraca nic; import pakietu nie ładuje Playwright.

**Checkpoint właściciela:** brak.

---

### Faza 4 — Silnik: przeglądarka, strona, sesja, platforma, rejestr

**Cel:** działający silnik dokumentowy zarejestrowany jako `elevenreader`.

**Wejście:** F1, F2, F3 scalone na gałęzi; S0.1–S0.6 z F0.

**Działania:**

1. `uv add playwright` (bez `playwright install`). Sprawdź, że `uv.lock` i `pyproject.toml` zmieniły się tylko o
   tę zależność i jej przechodnie.
2. `anishift/platform/installed.py`: `find_installed(locations: tuple[tuple[str, str], ...], stem: str) -> Path | None`
   (logika `qbittorrent_config.py:236-246`); `qbittorrent_config.installed_executable` woła ją z dotychczasowymi
   lokalizacjami.
3. `anishift/platform/private_dir.py`: `restrict_directory(root: Path) -> None` z kodu
   `qbittorrent_process._protect_profile` (`:633-653`), z błędem `PrivateDirectoryError(FatalError)` (z kontekstem
   `ErrorCode` istniejącym dla platformy albo nowym `PLATFORM_ACL_FAILED` — wybór lokalny, zapis w outcome);
   `_protect_profile` woła ją i mapuje błąd na dotychczasowy `_unavailable(...)` z tym samym komunikatem.
4. `anishift/platform/AGENTS.md`: dwa moduły.
5. `engines/elevenreader/browser.py`, `page.py`, `session.py`, `service.py` — sekcje 13.8–13.10, z drogą G1 albo
   G2 z S0.4 i selektorami z S0.1, S0.2, S0.4.
6. `anishift/services/tts/engines/__init__.py`: `TtsEngineId` i `_REGISTRY` z `elevenreader` po `elevenlabs`.
7. `anishift/services/tts/engines/AGENTS.md`: kolejność i opis adaptera.
8. Testy niżej.

**Pliki:** jak wyżej + `tests/platform/test_installed.py`, `tests/platform/test_private_dir.py`,
`tests/services/tts/test_tts_elevenreader_engine.py`, `tests/services/tts/test_tts_elevenreader_network.py`,
`tests/services/tts/test_tts_registry.py` (ZMIENIĆ).

**Kontrakty:** sekcje 13.8–13.12.

**Testy:**

`tests/platform/test_installed.py` (`unit`): `test_find_installed_prefers_first_existing_location`,
`test_find_installed_skips_unset_variables`, `test_find_installed_falls_back_to_path`,
`test_find_installed_returns_none_when_missing`.

`tests/platform/test_private_dir.py` (`unit`, `monkeypatch` na `subprocess.run` i `is_windows`):
`test_restrict_directory_calls_icacls_with_inheritance_removed`, `test_restrict_directory_raises_on_icacls_failure`,
`test_restrict_directory_uses_chmod_off_windows`, `test_restrict_directory_requires_account_name`.

Regresja: `tests/platform/test_qbittorrent_config.py`, `test_qbittorrent_process.py`,
`test_selective_qbittorrent.py`, `tests/setup/test_doctor.py` — bez zmian i zielone.

`tests/services/tts/test_tts_elevenreader_engine.py` (`unit`; `FakeBrowser`, `FakePage`, `FakeWebSocket` w
`elevenreader_fakes.py` z metodami używanymi przez `page.py`; zegar wstrzykiwany; `POLL_S` patchowany na 0;
fałszywe obiekty przekazywane przez `cast("Page", fake)` — bez produkcyjnych `Protocol` tylko dla testów):

- `test_engine_records_document_and_returns_part_timings`
- `test_engine_sets_reading_speed_before_play`
- `test_engine_selects_configured_voice_before_play`
- `test_engine_refuses_stream_with_other_voice`
- `test_engine_uploads_a_new_document_on_every_attempt`
- `test_engine_presses_play_again_after_start_timeout`
- `test_engine_times_out_after_three_play_attempts`
- `test_engine_times_out_after_stall`
- `test_engine_reports_incomplete_recording`
- `test_engine_reports_progress_from_received_characters`
- `test_engine_cancels_within_two_polls_and_closes_page`
- `test_engine_cancel_interrupts_long_wait_for_play`
- `test_engine_closes_browser_and_releases_lock_after_cancellation`
- `test_engine_maps_signed_out_library_to_auth_error`
- `test_engine_maps_unavailable_library_to_provider_unavailable`
- `test_engine_maps_upload_status_codes`
- `test_engine_restarts_browser_after_crash`
- `test_engine_synthesize_single_request_is_unsupported`
- `test_engine_never_logs_stream_url_or_document_text` (`caplog`/sink loguru jak w istniejących testach logowania)
- `test_engine_availability_never_starts_browser`
- `test_engine_profile_changes_with_voice`
- `test_browser_reports_busy_profile_as_provider_unavailable`
- `test_browser_reports_missing_chrome_as_config_error`
- `test_browser_releases_lock_and_terminates_chrome_on_close`
- `test_session_write_is_atomic_and_contains_no_secrets`
- `test_session_read_ignores_corrupt_file`

`tests/services/tts/test_tts_elevenreader_network.py` (`e2e` + `network`):

- `test_live_document_of_three_lines_yields_three_clips` — pomijany bez `ANISHIFT_ELEVENREADER_LIVE=1`; używa
  prawdziwego profilu `config/elevenreader/`, tekstu z 18.0.1, `TtsService` z prawdziwym `FfmpegClipService`.

`test_tts_registry.py`: `EXPECTED_ENGINE_IDS = ("edge", "elevenbytes", "elevenlabs", "elevenreader", "sapi")`.

**Komendy dowodu:**

```bash
uv run pytest tests/services/tts tests/platform tests/setup -q
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv export --frozen --all-groups --no-emit-project --format requirements.txt --output-file $env:TEMP\audit-requirements.txt
uvx pip-audit --requirement $env:TEMP\audit-requirements.txt --disable-pip --strict
```

Po zgodzie właściciela (koszt kredytów):

```bash
$env:ANISHIFT_ELEVENREADER_LIVE = "1"; uv run pytest -m network tests/services/tts/test_tts_elevenreader_network.py -q
```

**Kryterium wyjścia:** bramki zielone; test sieciowy uruchomiony przez właściciela daje trzy klipy (S2); rezydent nie
był modyfikowany w trakcie (zamknięty przez właściciela na czas testu sieciowego, bo test używa profilu).

**Checkpoint właściciela (konto):**

```text
Uruchom: zamknij rezydenta AniShift, potem polecenie testu sieciowego wyżej.
Zrób: nic — test działa bez okna (albo z oknem przy D9 = okno).
Oczekiwany rezultat: 1 passed; w bibliotece ElevenReadera pojawia się jeden nowy dokument zaczynający się od „Pierwsza kwestia testowa.”
Zwróć uwagę na: ostrzeżenia na koncie, liczbę nowych dokumentów (ma być jeden).
Przekaż wynik jako: wynik pytest i liczba nowych dokumentów.
```

---

### Faza 4b — Gałąź D2: logowanie e-mailem i hasłem (warunkowa)

**Warunek wejścia:** F0 S0.1 = „konto e-mail, formularz bez captchy” i decyzja D2 = „tak”. Inaczej faza jest
pomijana, a outcome zapisuje powód.

**Działania:**

1. `anishift/config/settings.py`: `elevenreader_email: str = Field(default="", repr=False)`,
   `elevenreader_password: str = Field(default="", repr=False)` w sekcji `# TTS`.
2. `anishift/config/field_catalog.py`: specyfikacje sekretów tych pól jak dla istniejących kluczy (wzór pól
   `is_secret` czytanych przez `AppService.environment_statuses`, `anishift/application/service.py:610-620`).
3. `anishift/application/runtime.py`: przekazanie do `TtsConfig.elevenreader_email/password`.
4. `engines/elevenreader/session.py`: `_sign_in_with_password(page, email, password)` — wypełnienie formularza
   selektorami z S0.1, jedna próba, czekanie na „Import” do 60 s; porażka → dalej `TtsAuthError`.
5. `anishift/cli/interactive/settings.py`: `_Connection("elevenreader", "ElevenReader", "elevenreader_password",
   "elevenreader_email")`; sprawdź, że edytor adresu nie wymusza formatu URL dla `elevenreader_email` (jeśli
   wymusza — osobny edytor tekstu w tym samym wzorcu, decyzja lokalna).
6. `anishift/setup/doctor.py`: `_API_KEYS` bez zmian (to nie klucz API); `check_elevenreader` raportuje
   „logowanie automatyczne skonfigurowane: tak/nie” bez wartości.

**Testy** (`unit`): `test_settings_repr_hides_elevenreader_credentials`,
`test_engine_signs_in_with_password_once_when_session_expired`,
`test_engine_raises_auth_error_when_password_sign_in_fails`,
`test_password_never_reaches_logs_or_run_snapshot` (rozszerzenie `tests/application/test_environment_secrets.py`),
`test_settings_connections_list_elevenreader` (CLI).

**Kryterium wyjścia:** testy zielone; ręczny scenariusz: właściciel wylogowuje się w oknie Chrome, uruchamia test
sieciowy; test przechodzi po automatycznym zalogowaniu.

---

### Faza 5 — Kompozycja, ustawienia, panel, doctor

**Cel:** silnik wybieralny i używany przez Auto, Ręczny i subskrypcje; sesja widoczna w panelu i w `doctor`.

**Wejście:** F4.

**Działania:**

1. `anishift/paths.py`: `elevenreader_dir() -> Path` = `config_dir() / "elevenreader"`, eksport w `__all__`.
2. `.gitignore`: linia `config/elevenreader/` jest już od F0 (krok 2a); tylko sprawdź `git check-ignore`.
3. `config/README.md`: akapit o `elevenreader/` (profil Chrome z sesją, blokada, `session.json`; ACL; nie kopiować
   między kontami).
4. `anishift/application/runtime.py`:
   - `_TTS_REQUEST_TIMEOUT_S["elevenreader"] = 3600.0`, `_TTS_RETRY_BACKOFF_S["elevenreader"] = (60.0, 120.0, 300.0, 600.0)`;
   - `_tts_config`: `elevenreader_profile_root=elevenreader_dir()` i `shutdown_deadline_s=15.0` dla
     `elevenreader`, dla innych silników bez zmian;
   - `_tts_handler`: `TtsService(..., splitter=clips)`.
5. `anishift/application/service.py`:
   - `_tts_allowed_voice_ids`: gałąź `elevenreader` → `tuple(voice.voice_id for voice in VOICES.values())`;
   - `tts_is_paid`: `{"elevenbytes", "elevenlabs", "elevenreader"}`;
   - DTO warstwy aplikacji obok `ModelProbeResult` (`anishift/application/service.py:137-190`):
     `ElevenReaderSession(signed_in: bool | None, checked_at: datetime | None)` i
     `ElevenReaderSignIn(StrEnum)`: `SIGNED_IN`, `SIGNED_OUT`, `BUSY`, `NO_CHROME`, `FAILED`; eksport w
     `anishift/application/__init__.py` — panel importuje tylko publiczną fasadę aplikacji
     (`tests/application/test_architecture.py:126-143`), więc typy silnika nie wychodzą do CLI;
   - `elevenreader_session() -> ElevenReaderSession` (mapowanie `read_session(elevenreader_dir())`);
   - `elevenreader_sign_in() -> ElevenReaderSignIn` (synchronicznie: `asyncio.run(sign_in(elevenreader_dir()))`,
     import leniwy z `# noqa: PLC0415`, mapowanie `SignInOutcome` → DTO, `logger.info` granicy z wynikiem, bez danych
     konta).
6. `anishift/config/user_settings.py`:
   - stałe profili dwóch głosów (`_ELEVENREADER_*_PROFILE_KEY`), `default_tts_voice_profiles` z
     `TtsVoiceProfileSettings(concurrency=1)` dla obu;
   - `tts_voice_label`: gałąź `elevenreader` → etykieta z `VOICES`;
   - `resolved_tts_voice_id`: gałąź `elevenreader` → `resolve_voice(...).voice_id`, a dla nieznanego aliasu sam alias
     (walidację robi silnik);
   - `ensure_active_tts_profile`: `concurrency=1` dla `elevenreader` (jak `sapi`);
   - `_normalize_tts_selection`: gałąź `elevenreader` (model `eleven_v4`, głos spoza aliasów i ID → `fronczewski`);
     gałąź `elevenbytes` traktuje alias i ID głosu ElevenReadera jak głos obcego silnika (→ Dallin);
     gałąź `elevenlabs` (ostatnia, `user_settings.py:465-474`) dostaje `eleven_v4` w zbiorze modeli obcych silników
     (→ `DEFAULT_MODEL_ID`) i zamienia alias albo ID głosu ElevenReadera na pusty głos — domyślny głos `elevenlabs`
     w katalogu to `""` (`field_catalog.py:1373-1374`), więc panel wymusi wybór; gałęzie `edge` i `sapi` już
     resetują każdy obcy głos (`:455-464`);
     profil `elevenreader:*` zawsze ma `concurrency=1` (ręczna edycja pliku nie może dać innej wartości);
   - `_drop_incompatible_tts_options`: `elevenreader` czyści `engine_options`.
7. `anishift/config/field_catalog.py`: `_tts_model_values` (`("eleven_v4",)`), `_tts_voice_values`
   (`("fronczewski", "adam")`, domyślny `fronczewski`), `_profile_defaults` (rozwiązanie aliasu), ukrycie
   `tts_profile.concurrency` dla `elevenreader` (`field_catalog.py:1016`), `_engine_profile_specs` → `()`.
8. `anishift/config/AGENTS.md`: pułapka „alias głosu obcego silnika musi być resetowany w gałęzi każdego silnika”.
9. `anishift/cli/interactive/settings.py`:
   - `_ENGINE_LABELS["elevenreader"] = "ElevenReader"`;
   - `_CHOICE_LABELS` dla `("tts_voice_id", "fronczewski")` i `("tts_voice_id", "adam")`, jeśli wybór głosu korzysta z
     `_CHOICE_LABELS` (sprawdzić; inaczej etykieta z `tts_voice_label`);
   - w gałęzi `_Category.TTS` przy `tts_engine == "elevenreader"`: `_MenuItem("elevenreader-session", "Sesja
     ElevenReader", <stan>, "SESJA")` (bez akcji) i `_MenuItem("elevenreader-sign-in", "Zaloguj / sprawdź sesję",
     "", "SESJA")`;
   - akcja `elevenreader-sign-in` → `_start_sign_in` w wzorcu `_start_probe` (`settings.py:1627-1660`): `_busy`,
     generacja, wątek demona `anishift-elevenreader-sign-in`, `_Feedback` z sekcji 13.14, `_refresh_menu` po wyniku;
   - `_KNOWN_LAYOUT_GAPS` zostaje puste.
10. `anishift/setup/doctor.py`: `check_elevenreader(preferences: UserSettings | None = None, *, finder=find_installed,
    session_reader=read_session) -> CheckResult`; `run_doctor` dodaje go po `check_api_keys`. Statusy F18.
11. `anishift/setup/AGENTS.md`, `anishift/cli/AGENTS.md`: wpisy.

**Testy:**

- `tests/test_paths.py`: `test_elevenreader_dir_lives_in_config_dir`, `test_elevenreader_dir_follows_config_override`.
- `tests/application/test_runtime_config.py`: `test_elevenreader_config_uses_profile_dir_and_long_timeout`,
  `test_elevenreader_handler_injects_clip_splitter`, `test_other_engines_get_no_elevenreader_profile`.
- `tests/application/test_service.py` (albo właściwy plik snapshotu): `test_elevenreader_offers_both_voices`,
  `test_elevenreader_counts_as_paid_network_tts`.
- `tests/config/test_user_settings.py`: `test_elevenreader_defaults_to_fronczewski`,
  `test_elevenreader_unknown_voice_falls_back_to_fronczewski`, `test_elevenbytes_drops_elevenreader_alias_to_dallin`, `test_elevenlabs_drops_elevenreader_model_and_voice`,
  `test_edge_and_sapi_drop_elevenreader_voice`, `test_elevenreader_profile_concurrency_is_forced_to_one`,
  `test_elevenreader_profile_has_concurrency_one`, `test_switching_engines_keeps_custom_voices_and_profiles`,
  `test_elevenreader_label_is_piotr_fronczewski`.
- `tests/config/test_field_catalog.py`: `test_elevenreader_model_and_voice_values`,
  `test_elevenreader_hides_concurrency`, `test_elevenreader_has_no_engine_option_specs`.
- `tests/cli/test_interactive_settings_*.py`: `test_tts_category_shows_elevenreader_session_rows`,
  `test_sign_in_action_reports_signed_in`, `test_sign_in_action_reports_busy_browser`,
  `test_sign_in_rows_hidden_for_other_engines`, układ bez luk (`_KNOWN_LAYOUT_GAPS`).
- `tests/setup/test_doctor.py`: `test_check_elevenreader_skips_other_engines`,
  `test_check_elevenreader_fails_without_chrome`, `test_check_elevenreader_warns_without_profile`,
  `test_check_elevenreader_warns_after_signed_out_check`, `test_check_elevenreader_ok_after_signed_in_check`,
  `test_check_elevenreader_never_starts_browser`.

**Komendy dowodu:**

```bash
uv run pytest
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
git check-ignore -v config/elevenreader/chrome-profile/Default
uv run anishift doctor
```

**Kryterium wyjścia:** pełne bramki zielone; `git check-ignore` potwierdza ignorowanie; `doctor` pokazuje wiersz
ElevenReader zgodny z F18 dla bieżących ustawień (SKIP, jeśli silnik inny).

**Checkpoint właściciela (panel, bez ucha):**

```text
Uruchom: zamknij rezydenta; uv run anishift
Zrób: Ustawienia → Lektor → Silnik: ElevenReader; Głos: Piotr Fronczewski; „Zaloguj / sprawdź sesję”.
Oczekiwany rezultat: okno Chrome otwiera bibliotekę bez logowania (profil z F0), panel pokazuje „✓ Zalogowano”.
Zwróć uwagę na: czy wiersze są czytelne, czy brak zbędnych pól (współbieżność, VPN).
Przekaż wynik jako: OK albo lista zauważonych problemów.
```

---

### Faza 6 — Checkpoint ucha właściciela

**Cel:** decyzja właściciela, czy głos, tempo i głośność ElevenReadera są lepsze niż `elevenbytes` na prawdziwym
odcinku, oraz pomiar czasu syntezy (N3).

**Wejście:** F5; zalogowana sesja; jeden odcinek z polskimi napisami w `workspace/` (wybór właściciela, najlepiej
z bazy 3 odcinków etapu 0 jakości — `docs/work/10-quality/masterplan.md`).

**Działania wykonawcy przed checkpointem:**

1. Pełne bramki zielone na końcowym commicie fazy 5.
2. Właściciel uruchamia rezydenta ponownie dopiero teraz (nowy kod).
3. Po przebiegu wykonawca zbiera z logu (`logs/anishift.log.jsonl`) liczby: czas zadania TTS, liczba kwestii,
   `boundaries_without_silence`, ponowienia, `received_chars`/`char_count` — bez tekstu i ścieżek.

**Scenariusz 6A — głos i cięcie:**

```text
Uruchom: rezydent z gałęzi; Ustawienia → Lektor: ElevenReader, Piotr Fronczewski; Ręczny → wybrany odcinek → Start.
Zrób: obejrzyj 5 minut odcinka z lektorem (mpv), w tym fragment z szybką wymianą kwestii.
Oczekiwany rezultat: każda kwestia brzmi w całości; brak urwanych pierwszych i ostatnich sylab; brak powtórzonych zdań.
Zwróć uwagę na: ucięte słowa na początku/końcu kwestii, zlewające się kwestie, angielskie wtrącenia, głośne oddechy.
Przekaż wynik jako: OK / lista znaczników czasu z problemem (mm:ss) i rodzaj problemu.
```

**Scenariusz 6B — tempo:**

```text
Uruchom: ten sam wynik.
Zrób: oglądaj jak zwykle (także na x2, jeśli tak oglądasz).
Oczekiwany rezultat: lektor nie zostaje w tyle za scenami dłużej niż kilka sekund.
Zwróć uwagę na: narastające opóźnienie w scenach z dużą ilością dialogu.
Przekaż wynik jako: OK albo propozycja tempa końcowego (np. 1,1) do Ustawienia → Lektor → Tempo końcowe.
```

Po zmianie tempa: drugi przebieg tego samego odcinka używa resume TTS (klipy bez zmian), zmienia się tylko miks.

**Scenariusz 6C — głośność:**

```text
Uruchom: ten sam wynik.
Zrób: porównaj głośność lektora z oryginałem w scenie cichej i głośnej.
Oczekiwany rezultat: lektor słyszalny, nie dominuje.
Zwróć uwagę na: za cicho w scenach akcji, za głośno w cichych.
Przekaż wynik jako: korekta głośności głosu w dB (Ustawienia → Lektor → Korekta głośności głosu).
```

Uwaga: dopasowanie głośności do materiału to etap 6 jakości; tutaj tylko stała korekta per głos.

**Scenariusz 6D — Adam:**

```text
Uruchom: Ustawienia → Lektor → Głos: Adam; Ręczny → ten sam odcinek → Start.
Zrób: posłuchaj 2 minut.
Oczekiwany rezultat: głos Adam czyta po polsku zrozumiale.
Zwróć uwagę na: akcent, błędy wymowy polskich słów.
Przekaż wynik jako: OK / nie nadaje się; preferowany głos domyślny.
```

**Scenariusz 6E — zapas:**

```text
Uruchom: Ustawienia → Lektor → Silnik: ElevenBytes; Ręczny → ten sam odcinek → Start.
Oczekiwany rezultat: przebieg kończy się jak przed zmianą, głosem Dallin.
Przekaż wynik jako: OK / błąd.
```

**Scenariusz 6F — wygasła sesja (opcjonalny, bez kosztu):**

```text
Uruchom: Ustawienia → Lektor → Zaloguj / sprawdź sesję; w oknie Chrome wyloguj się; zamknij okno.
Zrób: Ręczny → krótki plik → Start.
Oczekiwany rezultat: przebieg kończy się błędem z sugestią „Ustawienia → Lektor → Zaloguj / sprawdź sesję”; po zalogowaniu ponowienie działa.
Przekaż wynik jako: OK / treść komunikatu.
```

**Kryterium wyjścia:** właściciel akceptuje 6A–6E (S3, S4); wartości tempa i korekty zapisane w profilu głosu;
wnioski i liczby w `outcomes/01-elevenreader-engine.md`. Feedback „ucięte słowa” wraca do F1/F3 (parametry
segmentacji, wariant D4) jako lokalna poprawka; feedback „zły głos/model” wraca do właściciela jako decyzja
kierunku.

---

### Faza 7 — Dokumentacja, review, PR

**Cel:** scalalny PR z kompletną dokumentacją i niezależnym review.

**Działania:**

1. Aktualizacja: `README.md` i `README.pl.md` (akapit: silnik ElevenReader, wymagany Chrome, logowanie w
   Ustawieniach, ryzyko ToS i bana jednym zdaniem, zapas `elevenbytes`, skutki uboczne na koncie z §13.13); `docs/reference/settings.md` (pola);
   `docs/ideas.md` (wpis §4 „Lektor przez ElevenReader” → „zrobione, workstream 11”, bez usuwania historii
   motywacji); `docs/README.md` (wiersz workstreamu 11).
2. Outcome `docs/work/11-elevenreader-tts/outcomes/01-elevenreader-engine.md` według szablonu OUTCOME ze skilla
   `coding`.
3. Review krzyżowe (sekcja 20): inny model niż autor; findingi krytyczne i poważne naprawione w commitach
   właściwych tematów (pamięć właściciela: poprawki z review wracają do commita swojego tematu — przez `git commit
   --fixup` i `git rebase --autosquash` bez trybu interaktywnego, albo nowym commitem tematu, jeśli przepisywanie
   historii wypchniętej gałęzi jest niepożądane).
4. Skan sekretów (S6):

   ```bash
   git diff main...HEAD | Select-String -Pattern "mateuszmroz|@gmail\.com|set-cookie|reads/stream/v2/[A-Za-z0-9]"
   git diff --name-only main...HEAD | Select-String -Pattern "chrome-profile|session\.json|frames-raw|\.mp3$"
   ```

   Oba bez wyników (pierwszy wzorzec dopuszcza stałą `STREAM_PATH` bez identyfikatora).
5. Push gałęzi i PR (sekcja 19).

**Kryterium wyjścia:** PR otwarty, CI zielone, review bez findingów krytycznych i poważnych, właściciel zna
otwarte decyzje i wynik checkpointu.

## 19. Git

### 19.1. Gałąź

`work/tts/01-elevenreader` z `main` (`4365a51`), w głównym checkoucie (bez worktree). Wzorzec nazw:
`work/subtitles/02-single-word-break-crash` (`4365a51`), `work/tui/02...` (pamięć właściciela).

### 19.2. Commity

Format `typ(scope): opis` ze scope z `scripts/hooks/check_commit_msg.py:37-61`; jeden commit na spójny temat;
poprawki review wracają do commita tematu; bez `Co-Authored-By` i stopek generatora (reguła repo wygrywa z
domyślną atrybucją narzędzia). Treść commita: po pustej linii co i dlaczego, po kolejnej „Verification:” z
faktycznie uruchomionymi komendami i wynikiem (skill `coding` §18).

| # | Commit | Faza | Zawartość |
|---|---|---|---|
| 1 | `docs(tts): plan the ElevenReader narrator engine` | przed F0 | `docs/work/11-elevenreader-tts/` (ten zestaw) i `research/spike-results.md` po F0 |
| 1a | `chore(repo): ignore the ElevenReader browser profile` | F0 krok 2a | `.gitignore` |
| 2 | `refactor(audio): share MPEG frame parsing through utils` | F1 | `utils/mp3_frames.py`, `audio/mp3.py`, `_portable.py`, AGENTS.md, testy |
| 3 | `refactor(tts): let the scheduler run any provider attempt` | F2 | `scheduler.py`, `service.py` (per kwestia), testy schedulera i serwisu |
| 4 | `feat(tts): synthesize whole documents and split them into line clips` | F2 + F1 | typy, protokoły, `TtsQuotaError`, ścieżka dokumentu, `segmentation.py`, `envelope_wav_command`, `split_clip`, testy |
| 5 | `refactor(platform): share installed-program lookup and private directory protection` | F4 | `installed.py`, `private_dir.py`, qBittorrent, testy |
| 6 | `build(deps): add playwright for the ElevenReader engine` | F4 | `pyproject.toml`, `uv.lock` (tylko przez `uv add`) |
| 7 | `feat(tts): add the ElevenReader engine` | F3 + F4 | pakiet `elevenreader/`, rejestr, fixture, testy, AGENTS.md |
| 8 | `feat(config): offer ElevenReader voices in settings` | F5 | `paths.py`, `config/README.md`, `user_settings.py`, `field_catalog.py`, `runtime.py`, `application/{service,__init__}.py`, testy |
| 9 | `feat(cli): sign in to ElevenReader from settings` | F5 | `cli/interactive/settings.py`, testy CLI, `cli/AGENTS.md` |
| 10 | `feat(setup): check ElevenReader readiness in doctor` | F5 | `doctor.py`, testy, `setup/AGENTS.md` |
| 11 | `feat(config): sign in to ElevenReader with saved credentials` | F4b (warunkowo) | `settings.py`, `session.py`, połączenie w panelu, testy |
| 12 | `docs(repo): document the ElevenReader narrator` | F7 | README EN/PL, `docs/reference/settings.md`, `docs/ideas.md`, `docs/README.md`, outcome |

Kolejność 2 → 3 → 4 jest wymuszona przez zależność typów; 5 i 6 przed 7.

### 19.3. Zależności

Tylko `uv add playwright`. Bez ręcznej edycji `pyproject.toml`. Bez `playwright install`. Sprawdzenie:

```bash
git diff main -- pyproject.toml
uv export --frozen --all-groups --no-emit-project --format requirements.txt --output-file $env:TEMP\audit-requirements.txt
uvx pip-audit --requirement $env:TEMP\audit-requirements.txt --disable-pip --strict
```

(komendy audytu jak w `.github/workflows/ci.yml:58-60`, plik wyjściowy poza repozytorium).

### 19.4. PR

Tytuł: `feat(tts): add the ElevenReader narrator engine`. Opis po angielsku, bez stopek AI, w układzie:

```text
## Summary
- New `elevenreader` TTS engine: reads every missing line of an episode in one ElevenReader document through the
  owner's signed-in Chrome profile and cuts the recording into line clips at silences.
- TTS domain: document synthesis contract, `ClipSplitter`, scheduler runs any provider attempt, `TtsQuotaError`.
- Audio: shared MPEG frame parsing (`anishift/utils/mp3_frames.py`), silence segmentation, frame-accurate cuts.
- Settings: engine, Piotr Fronczewski / Adam voices, sign-in action, doctor check.

## Risk
Automating ElevenReader breaks its terms and may get the account banned. `elevenbytes` stays available; switching
back is one setting.

## Verification
<commands and observed results from F4–F6>

## Owner checks
<6A–6E results>
```

## 20. Dodatkowi wykonawcy

Zgodnie z `AGENTS.md` (orkiestrator koordynuje; `astra` i `opus55` kodują; review robi inny model). Briefy według
`.agents/skills/subagent/assets/SUBAGENT-BRIEF.template.md`, każdy zaczyna od polecenia przeczytania w całości
`simple`, `coding/SKILL.md` i `coding/references/python.md` (pamięć właściciela).

| Jednostka | Cel | Kontekst | Write scope | Wynik | Owner integracji |
|---|---|---|---|---|---|
| W-F1 | faza 1 bez `split_clip` | plan §13.7, §18 F1; `EDP:src/timestamps.py`, `EDP:src/clips.py` | `anishift/utils/mp3_frames.py`, `_portable.py`, `utils/AGENTS.md`, `audio/{mp3,segmentation,commands}.py`, `audio/AGENTS.md`, testy F1 | diff + wyniki komend F1 | orkiestrator |
| W-F2 | faza 2 | plan §13.4–13.6, §18 F2 | `anishift/errors.py`, `services/tts/{types,protocols,scheduler,service,config,errors,__init__}.py`, `services/tts/AGENTS.md`, testy F2 | diff + wyniki | orkiestrator |
| W-F3 | faza 3 | plan §13.8, §18 F3, `spike-results.md` | `services/tts/engines/elevenreader/{constants,config,document,recorder,alignment,errors,__init__}.py`, `AGENTS.md`, testy F3, fixture | diff + wyniki | orkiestrator |
| W-F4 | faza 4 (+4b) | całość planu | pliki F4 | diff + wyniki + checkpoint | orkiestrator |
| W-F5 | faza 5 | plan §13.10–13.14, §18 F5 | pliki F5 | diff + wyniki | orkiestrator |
| R-n | review krzyżowe każdej fazy | plan, spec, diff fazy | read-only | raport `review` | orkiestrator |

W-F1, W-F2, W-F3 są niezależne semantycznie i mogą biec równolegle (najwyżej dwie instancje jednego modelu).
W-F3 potrzebuje `utils/mp3_frames.py` i typów z F2: albo startuje po commitach 2 i 4, albo używa ich szkiców z
tego planu i dostosowuje się przy integracji (zadanie orkiestratora). Pilot fan-outu: brak — jednostki nie są
powtarzalne.

Zasada krzyżowa: autor fazy nie robi jej review; review robi świeża instancja innego modelu.

## 21. Strategia dowodu

| Twierdzenie | Kontrola | Dlaczego wystarcza |
|---|---|---|
| dotychczasowe silniki bez zmian | istniejące testy TTS/audio/platform/config bez zmian asercji, diff testów ograniczony do API | testy kodują kontrakt; diff pokazuje brak osłabienia |
| scheduler wykonuje dowolną próbę z retry i circuit | unit schedulera | fałszywe wywołania i zegar |
| resume per kwestia w trybie dokumentu | unit `test_tts_document_service.py` | fałszywy silnik liczy wywołania i kwestie |
| cięcie nie ucina mowy | integration na syntetycznym nagraniu + materiał właściciela (skipif) + ucho 6A | syntetyk sprawdza mechanikę, ucho jakość |
| zegar obwiedni zgodny z zegarem ramek | E1 z liczbami | pomiar wprost |
| protokół strony (upload, odtwarzanie, głos) | unit na fałszywej stronie + test sieciowy S2 | fałszywa strona sprawdza logikę, test sieciowy realną granicę |
| brak sekretów | testy logowania silnika, testy `repr`, skan S6 | trzy niezależne instrumenty |
| panel i doctor | testy CLI i doctor + checkpoint F5 | układ + oko |
| jakość głosu, tempo, głośność | checkpoint F6 | tylko człowiek |
| CI | bramki lokalne + CI na PR | te same komendy |

### Regression obligations

- `tests/services/tts/**`, `tests/services/audio/**`, `tests/application/test_tts_handler.py`,
  `tests/application/test_runtime_config.py`, `tests/platform/test_qbittorrent_*.py`,
  `tests/config/test_user_settings.py`, `tests/config/test_field_catalog.py`, `tests/cli/test_interactive_settings_*.py`,
  `tests/setup/test_doctor.py` — zielone na każdym commicie od 2 do 12.

### Human acceptance

- Co testy nie potwierdzają: brzmienie głosu, naturalność granic klipów, tempo wobec scen, głośność, zachowanie
  konta.
- Scenariusze: F0 (konto), F4 (test sieciowy), F5 (panel), F6 (6A–6F).
- PASS: akceptacja właściciela 6A–6E bez otwartych problemów „ucięte słowo” i „zły głos”.

## 22. Niewiadome i jak je zamknąć

| Niewiadoma | Dlaczego istotna | Jak zamknąć | Kiedy |
|---|---|---|---|
| `voice_id` Fronczewskiego i Adama, język Adama | F9, I4 | S0.3 | F0 |
| wybór głosu: odtwarzacz czy ustawienia konta | F8, droga G1/G2 | S0.4 | F0 |
| czy adres WS niesie głos | weryfikacja F8 | S0.5 | F0 |
| metody logowania, captcha | D2, F16 | S0.1 | F0 |
| sygnał wylogowania | F16, `open_library` | S0.2 | F0 |
| tryb bez okna | D9 | S0.6 | F0 |
| status HTTP przy braku kredytów | mapowanie `TtsQuotaError` | nie da się wywołać bez wyczerpania konta; przyjęte 402 i komunikat; przy pierwszym wystąpieniu w praktyce log statusu (bez treści) i korekta mapowania | po wdrożeniu |
| status przy blokadzie konta | F20 | jak wyżej; przyjęte 403 | po wdrożeniu |
| czy cache serwera działa dla nowego dokumentu o tym samym tekście | koszt ponowień między przebiegami | odłożone (sekcja 14.4) | — |
| dryf FFmpeg | droga dekodowania obwiedni | E1 | F1 |
| twardy limit długości dokumentu | `MAX_DOCUMENT_CHARS` | nie badamy; 50 000 to połowa zmierzonego maksimum | — |
| czy Chrome pod Job Object rezydenta działa poprawnie | N5 | test sieciowy uruchomiony z rezydentem w F6 | F6 |
| czy Playwright async działa w pętli wątku `anishift-tts` na Windows | przeglądarka w silniku | test sieciowy F4 przez `TtsService` | F4 |
| czy sterownik Playwright otwiera okno konsoli pod `pythonw` | wygoda, N5 | obserwacja w F6 z rezydentem | F6 |
| czy Chrome działa z profilem zawężonym ACL (bez SYSTEM) | F13, sesja | S0.10 | F0 |
| plan konta („darmowa trasa” vs `plan: ultra`, `capabilities.md:55`) | koszt, limit 24 h/dobę | nie wpływa na kod; właściciel zna swoje konto | — |

## 23. Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Kiedy eskalować |
|---|---|---|---|
| ban albo ograniczenie konta | 403, ostrzeżenie na stronie, e-mail od ElevenLabs | circuit; właściciel przełącza na `elevenbytes` | natychmiast; bez prób obejścia |
| zmiana interfejsu strony (selektory) | `TtsTimeoutError` na akcjach, test sieciowy czerwony | poprawka selektorów w `page.py`/`constants.py` | gdy zmiana wymaga czegoś poza klikaniem |
| zmiana protokołu WS | brak `alignment`, `TtsClipValidationError` | analiza ramek nową sesją spike | gdy dane do cięcia znikną |
| przeniesienie na model v2 | zmiana barwy, inne tempo | kontrola prędkości 1x | gdy 1x przestanie dawać v4 |
| ucięte słowa | checkpoint 6A, wysoki `boundaries_without_silence` | strojenie stałych segmentacji ±50%, potem decyzja D4 | gdy > 10% granic bez ciszy |
| za wolne tempo głosu | 6B, rosnący `drift_ms` | tempo końcowe profilu głosu | gdy tempo > 1,25 psuje głos |
| CDP na porcie localhost dostępny dla innych procesów lokalnych | — | port losowy, przeglądarka tylko na czas nagrania; ryzyko przyjęte dla jednoosobowego PC | gdy na PC pracują inni użytkownicy |
| profil z sesją skopiowany lub wyciekł | — | ACL, `.gitignore`, skan S6 | przy każdym wycieku: wylogowanie wszystkich sesji na koncie |
| głos `famous` w publicznym repo | skan plików MP3 w diffie | zakaz Z4, fixture z syntetycznym audio | natychmiast |
| Playwright nie wspiera Python 3.14 na CI | `uv add` lub CI czerwone | wersja zgodna z EDP (`>=1.64.0`, działa na 3.14 u właściciela) | gdy brak wheela |
| rezydent zawieszony na nagrywaniu | przestój bez postępu | `STALL_S`, timeout schedulera 3600 s, anulowanie | gdy przestój mimo audio |
| refaktor schedulera psuje inne silniki | czerwone istniejące testy | cofnięcie commita 3 i poprawka | zawsze przed commitem 4 |
| okno konsoli sterownika Playwright (Node) pod `pythonw` rezydenta | migające okno w tle podczas syntezy | sprawdzenie w F6; jeśli występuje — start sterownika z `CREATE_NO_WINDOW` przez dostępną opcję Playwright albo zgłoszenie do decyzji | gdy nie da się ukryć bez łatki biblioteki |

## 24. Plan wycofania

1. **Natychmiastowy, bez kodu:** Ustawienia → Lektor → Silnik: ElevenBytes. Silnik `elevenbytes` jest nietknięty
   (I1), więc to pełny powrót.
2. **Usunięcie sesji:** zamknąć rezydenta, usunąć `config/elevenreader/` (profil, blokada, `session.json`); opcjonalnie
   wylogować sesje na koncie ElevenReadera.
3. **Wycofanie kodu przed merge:** zamknąć PR, usunąć gałąź; `main` bez zmian.
4. **Wycofanie kodu po merge:** `git revert` commitów 7–12 w odwrotnej kolejności (silnik, ustawienia, panel,
   doctor, dokumentacja) — commity 2–5 (wspólne ramki, scheduler, kontrakt dokumentu, platforma) mogą zostać, bo
   nie zmieniają zachowania innych silników; `uv remove playwright` przy wycofaniu commita 6.
5. `config/settings.json` z `tts_engine="elevenreader"` po wycofaniu kodu: `_normalize_tts_selection` ustawi
   `elevenbytes`, bo silnika nie ma w rejestrze (`anishift/config/user_settings.py:446-448`).

## 25. Lokalna adaptacja

Wykonawca może bez przeplanowania: dopasować nazwy prywatnych funkcji i podział helperów w granicach modułów z
sekcji 13.8; dobrać dokładne selektory z fazy 0; zmienić komunikaty w granicach sensu; przesunąć test między
plikami tego samego obszaru; zmienić stałe czasowe w granicach sekcji 14.5 z wpisem w outcome; wybrać kod błędu
platformy dla `restrict_directory`.

## 26. Materialna zmiana

Wymaga zatrzymania i przeplanowania: warunki z sekcji 14.6; potrzeba zmiany `SpeechBatch`, `TtsTaskHandler`,
`plan_timeline` lub manifestu resume; nowa zależność poza `playwright`; potrzeba drugiej przeglądarki lub
równoległych dokumentów; potrzeba zapisu sekretu poza `.env`; zmiana domyślnego silnika.

## 27. Definition of Done

- [ ] F1, F2, F3, F4, F5 zakończone z kryteriami wyjścia; F4b zakończona albo pominięta z zapisanym powodem.
- [ ] Bramki S1 zielone na końcowym commicie; CI zielone na PR.
- [ ] Test sieciowy S2 uruchomiony przez właściciela.
- [ ] Checkpoint F6 (6A–6E) zaakceptowany; tempo i korekta głośności zapisane.
- [ ] Review krzyżowe bez findingów krytycznych i poważnych (S5).
- [ ] Skan S6 czysty.
- [ ] Zakres i zakazy zachowane; brak zmian w EDP.
- [ ] Outcome z dowodami, odchyleniami, otwartymi niewiadomymi.

## 28. Kontrakt wyniku

```text
status: ACCEPTED | PENDING HUMAN | PARTIAL | BLOCKED | REPLAN REQUIRED
finalny rezultat: co działa, na jakim odcinku sprawdzono
zmienione elementy: lista commitów z hashami
konkretne dowody: komendy i wyniki (liczby testów, exit code), E1, test sieciowy, logi liczbowe z F6
human feedback: wyniki 6A–6F, decyzje D1–D11
lokalne odchylenia: wartości stałych, selektory, kod błędu platformy
materialne odkrycia: wyniki S0.1–S0.9, zachowanie konta
znane ograniczenia: niewiadome z sekcji 22, które zostały
stan repo: gałąź, ostatni commit, PR
rekomendowany następny krok: etap 6 jakości na nowym głosie albo poprawki z 6A
```

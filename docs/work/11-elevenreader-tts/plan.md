---
kind: plan
status: draft
baseline: AniShift main f5fff6b (merge PR #76), czyste drzewo; prototyp SCR z 2026-10-30
created: 2026-10-25
updated: 2026-10-30
---

# Plan: silnik lektora ElevenReader, mierzona głośność i tempo na głos

Plan jest kontraktem dla świeżych wykonawców. Wymagania (`F*`, `N*`), inwarianty (`I*`), ograniczenia (`O*`),
zakazy (`Z*`) i decyzje (`D*`) są w `specification.md`; tu są odwołania. Mapa plików: `file-map.md`.

Skróty:

- **EDP** = `C:\Users\MattyMroz\Desktop\PROJECTS\ElevenDownloaderPro` (tylko do odczytu; ścieżki `EDP:`).
- **SCR** = `C:\Users\MATTYM~1\AppData\Local\Temp\claude\c--Users-MattyMroz-Desktop-PROJECTS-AniShift\805265a0-dc59-4be6-b614-414304044433\scratchpad\er\`
  (prototyp; ścieżki `SCR:`). Po fazie 0 te same dane leżą w **DATA** =
  `workspace/.quality/elevenreader/` (gitignorowane; stała `QUALITY_DIR` w `tests/conftest.py`).
- Symbole podaję z nazwą; numery linii tylko tam, gdzie zostały sprawdzone na `f5fff6b`.

## 1. Cel

1. Dodać silnik TTS `elevenreader`, który czyta odcinek głosem Piotra Fronczewskiego albo Adama (Eleven v4) przez
   prawdziwy Chrome z zalogowaną sesją i tnie nagranie na klipy kwestii heurystyką ciszy.
2. Ustawić głośność lektora pomiarem względem oryginału, z limiterem na wyjściu.
3. Przycinać ciszę na brzegach klipów i dać każdemu głosowi własne tempo i korektę.

`elevenbytes` zostaje zapasem dostępnym jednym wyborem w Ustawieniach.

## 2. Rezultat użytkownika

- Ustawienia → Lektor → Silnik „ElevenReader”, Głos „Piotr Fronczewski” albo „Adam”.
- Ustawienia → Lektor → „Zaloguj / sprawdź sesję” otwiera okno Chrome i kończy się wynikiem.
- Przetwarzanie pokazuje postęp syntezy rosnący z odbieranym tekstem.
- Lektor każdego głosu, także Dallina, leży 7,5 LU nad oryginałem; szczyty nie przesterowują.
- Po każdym nagraniu biblioteka ElevenReadera i ustawienia konta są takie jak przed nim.
- Wygasła sesja, brak kredytów albo blokada konta kończą syntezę komunikatem po polsku z jedną akcją naprawczą.
- `anishift doctor` mówi, czy Chrome jest dostępny i czy sesja była ostatnio ważna.

## 3. Warunki końcowe

- [ ] Etapy 1–9 zakończone z dowodami z §9; bramki S1 zielone.
- [ ] Test zgodności cięcia na Tantei (N2) zielony; punkt kontrolny K1 (Edgerunners) zamknięty.
- [ ] Migracja `config/settings.json` właściciela wykonana skryptem z `scripts/tmp/`, sprawdzona i skrypt usunięty.
- [ ] K2 (test sieciowy) i K3 (ucho właściciela, oba głosy) zaakceptowane; powrót na `elevenbytes` sprawdzony (S5).
- [ ] Review krzyżowe bez findingów krytycznych i poważnych (S6); skan sekretów czysty (S7).

## 4. Decyzja: kod nagrywania w AniShift czy EDP jako narzędzie zewnętrzne

| Kryterium | A. Port do AniShift (`uv add playwright`, profil w `config/elevenreader/`) | B. Wywołanie EDP jako procesu |
|---|---|---|
| Stabilność źródła | kod w repo, pod bramkami i CI | `EDP:src/auto.py`, `timestamps.py`, `clips.py` niezacommitowane (`git status` EDP: `??`); każda zmiana w EDP po cichu zmienia AniShift |
| Punkt wejścia | własny kontrakt dokumentu | EDP nie ma trybu „jeden dokument, głos, wynik JSON”; trzeba go dopisać w EDP (zakaz Z3) |
| Błędy i retry | typowane błędy → wspólny scheduler (circuit, backoff) | `SystemExit` i `print`; własna pętla czekania do 120 min (`EDP:src/auto.py`, `open_library`); klasyfikacja przez parsowanie stdout |
| Anulowanie | `CancellationToken` w każdej pętli i oczekiwaniu | tylko `terminate` procesu |
| Profil i sesja | jeden profil AniShift, akcja logowania w panelu, `doctor` | profil EDP i stały port 9222 (`EDP:src/downloader.py`, `CDP_PORT`); konflikt, gdy właściciel nagrywa audiobook w EDP |
| Cykl życia Chrome | dziecko rezydenta, Job Object kończy je z rezydentem | wnuk przez `uv run` w innym projekcie |
| Koszt | ok. 700–900 linii kodu i testy; duplikat logiki między repo | mniej kodu w AniShift, ale zmiany w EDP i parser logów |

**Decyzja właściciela: A.** Jedno źródło prawdy o błędach, retry, resume i anulowaniu jest warunkiem reguły właściciela
„każdy błąd obsłużony i widoczny”. B tej reguły nie spełni bez przebudowy EDP, a EDP ma pozostać nietknięte.
Duplikat między repo jest świadomy: EDP służy audiobookom i ma inny cykl życia. Wewnątrz AniShift duplikatu nie ma
(§7.13).

Port oznacza adaptację, nie kopię 1:1. Z EDP i prototypu bierzemy wiedzę o trasie (kolejność kroków, endpointy,
pola ramek, stałe czasowe zmierzone przez autora), a kod piszemy od nowa w standardzie repo: `coding` i `simple`,
async Playwright zamiast sync, typowane błędy zamiast `SystemExit`, `get_logger` zamiast `print`, stan w jednym
właścicielu, guard clauses, zero legacy. Odpada wszystko, czego AniShift nie potrzebuje: tryb ręczny i klawisze,
katalogi `input/done/failed`, dopisywanie do pliku, `--parallel`, stały port, własne pętle czekania, statusy MB.

## 5. Authority i baseline

| Źródło | Rola |
|---|---|
| `specification.md`, `intent.md` | wymagania, zakazy, decyzje |
| `AGENTS.md`, `anishift/AGENTS.md`, `tests/AGENTS.md` | reguły repo |
| AGENTS.md w `anishift/services/tts/`, `services/tts/engines/`, `services/audio/`, `application/`, `config/`, `cli/`, `setup/`, `platform/`, `utils/`, `text/` | reguły obszarów |
| `.agents/skills/{simple,coding,subagent}/SKILL.md`, `coding/references/python.md` | standard pracy |
| `SCR:record.py`, `SCR:snapcut.py`, `SCR:bounds.py`, `SCR:envelope.py`, `SCR:snap-report.md`, `SCR:loudness-report.md` | działający prototyp i pomiary |
| `EDP:src/downloader.py`, `EDP:src/auto.py` | logika trasy do portu |

**Baseline:** `main` na `f5fff6b`, czyste drzewo; rezydent właściciela działa z tego checkoutu.

**Znane wcześniejsze failures:** nieznane; faza 0 je zapisuje.

## 6. Stan aktualny i luka

### 6.1. Trasa ElevenReader (prototyp `SCR:record.py`, zweryfikowany 2026-10-30)

1. Chrome z własnym profilem, `--headless=new`, `--remote-debugging-port`; Playwright `connect_over_cdp`
   (`EDP:src/downloader.py`, `launch_chrome`, `connect`). Init script przyspiesza bufory audio strony 64x
   (`SPEED_JS`).
2. Biblioteka `https://elevenreader.io/reader/library`; przycisk „Import”, `input[type=file]`, „Upload”; odpowiedź
   `POST …/v1/reader/reads/add/v2` niesie `read_id`, `char_count` i nagłówek `authorization` (`EDP:src/auto.py`,
   `upload`).
3. Konto: `GET/POST https://api.elevenlabs.io/v1/reader/user_config` z tokenem strony; prototyp ustawia
   `default_voice_id` i `playback_speed_rate = 1.0`, a na końcu przywraca poprzedni głos (`SCR:record.py`,
   `set_voice`; `EDP:src/auto.py`, `reset_reading_speed`). Odpowiedź ma flagi `device_rate_limit_enabled`,
   `ip_ban_check_enabled` (`SCR:user_config.json`).
4. Dokument `…/reader/library/{read_id}`; „Play”; ramki WebSocket `…/v1/reader/reads/stream/v2/{read_id}?voice_id=…`
   z polami `audio` (MP3 base64), `alignment.chars`, `charStartTimesMs`, `charDurationsMs`, `isFinal`; ramki
   wysyłane niosą `listening_speed` (`EDP:src/downloader.py`, `Recorder`).
5. Koniec: suwak odtwarzacza w 30 znakach od końca albo odebrano `char_count` znaków, i 10 s bez nowego audio;
   brak audio 60 s po „Play” → ponowne „Play” do 3 razy; przestój 5 min → porażka (`EDP:src/auto.py`, `Job.step`).
6. Po nagraniu `DELETE https://api.elevenlabs.io/v1/reader/reads/{read_id}` (HTTP 200 w prototypie).
7. Wynik Tantei: 19 038 znaków, upload 10–12 s, nagrywanie 245 s na głos, `chars_received == char_count`,
   `voice_in_stream_url: true` (`SCR:tantei/record.json`). Ten sam tekst tym samym głosem drugi raz przychodzi z cache
   serwera bez kredytów (`EDP:README.md`).
8. Tekst wraca z tagami `<break time="0.6s"/>` wokół każdego akapitu i `<break time="2s"/>` na końcu
   (`SCR:edge02/record.log`). `<break>` wpisany w tekst dokumentu serwer ignoruje, a `[pause]` lektor czyta na
   głos. Pauzę między kwestiami daje dopiero osobny akapit „…”: lektor go nie czyta, przerwy rosną o 30–50 ms, a złych
   granic na Edgerunners 02 zostaje 0 (Fronczewski) i 1 (Adam) zamiast 4 i 7 (`DATA:snap-report.md` §11–§13).

### 6.2. Cięcie (`SCR:snap-report.md`)

- Każde nagranie ma 22 uszkodzone ramki (sklejenia paczek). Dekoder je pomija, więc PCM jest krótsze o 26,1 ms na
  sklejenie. Oś czasu MP3 (pts) zgadza się z czasami serwera co do ms; czas z indeksu próbki trzeba przeliczać
  (`SCR:bounds.py`, `splice_times`, `to_decoded`).
- Reguła `SCR:snapcut.py` daje 100% poprawnych granic na 2 × 323 granicach. 6 granic bez pewnej ciszy to kwestie
  urwane w pół zdania z przerwą 0 ms w napisach.

### 6.3. Głośność i tempo (`SCR:loudness-report.md`)

- Obecny Dallin leży +7,6 LU nad oryginałem; głosy ElevenReadera surowo o 4 LU ciszej i różnią się między sobą o
  11 dB. Współczynnik szczytu 21–22 dB wymaga limitera.
- Tempo: Fronczewski 1,45, Adam 1,35, Dallin 1,25 wyrównują mowę do 6,8–7,0 sylab/s.
- Przycięcie ciszy na brzegach przy tempie 1,25: kwestie dłuższe niż okno `elevenbytes` 30 → 10, Fronczewski
  46 → 24, Adam 28 → 17 (próg −45 dBFS, ramki 10 ms; `SCR:measure_clips.py`, `speech_span`).

### 6.4. AniShift (`f5fff6b`)

- `TtsEngine.synthesize` przyjmuje jedno `SynthesisRequest` (`anishift/services/tts/protocols.py`). `TtsScheduler.submit`
  przyjmuje `request_factory` i sam woła `engine.synthesize` (`anishift/services/tts/scheduler.py:119-153`, `_WorkItem`
  `:61-72`); wynik `ScheduledSynthesis.clip` (`:39-44`). `_opens_circuit` (`:426-429`) obejmuje `TtsAuthError`,
  `TtsConfigError`, `TtsVoiceError` i wyczerpane błędy przejściowe.
- `TtsService.__init__(config, *, resume_root, validator, assembler=None, engine_factory=create_engine)`
  (`anishift/services/tts/service.py:223-246`).
- `EngineCapabilities` bez pojęcia dokumentu (`anishift/services/tts/types.py:219-233`); `AudioFormat` ma `WAV`.
- `TtsTaskHandler._narration_batch` buduje żądania i okna (`anishift/application/tts_handler.py:541-562`);
  `_placement_window` (`:572-576`).
- `FfmpegClipService` waliduje MP3 i WAV oraz skleja części (`anishift/application/tts_clips.py`).
- Gain narratora: `config.narrator_mix_base_gain_db + config.voice_mix_offset_db` w `render_command`
  (`anishift/services/audio/output.py:116`); `amix … normalize=true`, brak limitera. `_render_output`
  (`anishift/services/audio/service.py:500-552`). `mix_fingerprint` z `_MIX_ALGORITHM_VERSION = 3`
  (`anishift/services/audio/fingerprint.py:25`, sekcja `gain` `:98-102`).
- `narrator_mix_base_gain_db` występuje w: `services/audio/{config,output,fingerprint}.py`,
  `application/planning.py:185,288`, `application/runtime.py:665`, `application/service.py:1100`,
  `config/user_settings.py:284,866`, `config/field_catalog.py:346,1253-1257`, `cli/interactive/settings.py:243,1990`
  i 9 testach (`grep -rn narrator_mix_base_gain_db`). `ProcessingRequest.settings` zapisuje snapshot jako słownik
  bez ścisłego schematu (`application/watch_state.py`, `_decode_settings`), więc zmiana nazwy pola nie psuje
  odczytu `state.json`.
- `normalize_clip` ma szybką ścieżkę `_neutral_wav`, która zwraca WAV bez przetwarzania
  (`anishift/services/audio/normalize.py`), oraz cache `_cached_raw_pcm`. `plan_timeline` liczy długość z
  `NormalizedClip.frame_count` (`anishift/services/audio/timeline.py`).
- Profile głosów: `default_tts_voice_profiles()` — Dallin `postprocess_tempo=1.25`, `voice_mix_offset_db=-2.0`
  (`anishift/config/user_settings.py:214-221`); u właściciela −1,5 w `config/settings.json`.
- `anishift/text/boundaries.py` ma `SENTENCE_ENDINGS` i `CLOSING_MARKS`.
- `numpy` nie jest zależnością runtime (`uv tree --no-dev`); obliczenia energii idą przez stdlib (`array`,
  `math.sumprod`).

### 6.5. Luka

```text
CURRENT: silnik = jedno żądanie → jeden klip; stały gain narratora bez limitera; klipy z ciszą na brzegach;
         brak przeglądarki, sesji, dokumentu, cięcia.
GAP:     ElevenReader czyta dokument; wymaga zalogowanego Chrome; klipy trzeba wyciąć z nagrania; głosy różnią
         się poziomem o 11 dB; kwestie urwane w pół zdania nie mają ciszy do cięcia.
TARGET:  kontrakt dokumentu w TTS + scheduler wykonujący dowolną próbę + cięcie i trim w audio + pomiar
         głośności w miksie + łączenie kwestii urwanych + silnik `elevenreader` + sesja w config/elevenreader/.
```

Nowy adapter za `TtsEngine.synthesize` nie wystarczy: scheduler podaje silnikowi po jednym żądaniu, a
`_run_batch` rozdziela kwestie na niezależne próby, więc silnik nie widzi całego odcinka.

## 7. Target design

### 7.1. Odpowiedzialności

| Element | Odpowiada za | Owner stanu | Nie odpowiada za |
|---|---|---|---|
| `TtsTaskHandler` | skrypt → `SpeechBatch`, łączenie kwestii urwanych i szyldy w batchu kwestii (tylko z flagą `reads_document`), manifest narracji | czasy napisów | silnik, dokument |
| rejestr TTS (`engines/__init__.py`) | `is_document_engine(engine_id)`: jedyne źródło wiedzy, który silnik czyta dokumentem | — | budowa silnika |
| `TtsService` | ścieżka per kwestia albo dokument, resume, commit klipów, postęp, `open_end` granic | manifest resume | strona, Chrome, cięcie |
| `TtsScheduler` | kolejka, retry, circuit, timeout prób | stan circuit | budowa żądania |
| `FfmpegClipService.split_clip` | dekodowanie nagrania, wywołanie cięcia, zapis klipów WAV | pliki tymczasowe klipów | czasy kwestii |
| `services/audio/segmentation.py` | czysta reguła cięcia na poziomach energii | — | FFmpeg, pliki |
| `services/audio/levels.py` | poziomy RMS w ramkach 10 ms, zakres mowy | — | progi decyzji |
| `utils/mp3_frames.py` | nagłówki ramek MPEG, długość, cięcie przed czasem, miejsca sklejeń | — | dekodowanie |
| `AudioService` | trim brzegów (normalizacja), pomiar głośności, gain, limiter | resume audio | providerzy |
| `ElevenReaderTtsEngine` | jedna próba dokumentu: Chrome, sesja, konto, upload, nagranie, czasy kwestii | nagranie (tymczasowe), proces Chrome | retry, resume, cięcie |
| `UserSettings`, `field_catalog` | silnik, głos, profile głosów, `narrator_over_source_lu` | `config/settings.json` | sesja |

### 7.2. Kontrakty domeny TTS

Typy `@dataclass(frozen=True, slots=True)` w `anishift/services/tts/types.py`, eksport w `__init__.py`:

```text
EngineCapabilities (zmiana)
  + max_document_chars: int | None = None     # None: silnik per kwestia (bez zmian konstruktorów)

DocumentPart:             request_id: str; text: str
DocumentSynthesisRequest: request_id: str                     # "<scope_id>:document:<n>"
                          parts: tuple[DocumentPart, ...]      # ≥ 1, kolejność czytania
                          voice_id: str; provider_model_id: str; options: EngineOptions
                          recording: Path                      # temporary_clip_path(MP3) z TtsResumeRepository
                          deadline_s: float
                          progress: Callable[[int, int], Awaitable[None]] | None = field(default=None, compare=False)
PartTiming:               request_id: str; start_ms: float; end_ms: float   # czas serwera = oś MP3; end > start
EngineDocumentResult:     request_id: str; recording: Path; format: AudioFormat (MP3); engine_id: str
                          provider_model_id: str; voice_id: str; request_time_ms: float
                          parts: tuple[PartTiming, ...]        # dokładnie jedna na część, w kolejności
ClipSpan:                 request_id: str; start_ms: float; end_ms: float; open_end: bool; destination: Path
SplitResult:              written: tuple[str, ...]; uncertain_boundaries: int
```

Protokoły w `protocols.py`:

```text
class DocumentTtsEngine(TtsEngine, Protocol):
    def document_chars(self, parts: tuple[DocumentPart, ...]) -> int: ...   # długość wysyłanego dokumentu
    def validate_part(self, part: DocumentPart) -> None: ...                # TtsInputError, gdy części nie da się przeczytać
    async def synthesize_document(self, request: DocumentSynthesisRequest, *,
                                  cancel: CancellationToken) -> EngineDocumentResult: ...

class ClipSplitter(Protocol):
    def split_clip(self, source: Path, spans: tuple[ClipSpan, ...],
                   expectation: ClipExpectation) -> SplitResult: ...
```

`split_clip`: `spans` niepuste, w kolejności czytania; każdy `destination` dostaje klip WAV mono 48 kHz PCM S16LE;
błędy `RuntimeError`/`OSError`/`ValueError` (jak `join_clips`), które `TtsService` mapuje na
`TtsClipValidationError`.

`anishift/errors.py`: `ErrorCode.TTS_QUOTA_EXHAUSTED`. `anishift/services/tts/errors.py`:
`class TtsQuotaError(TtsError, FatalError)`. `_opens_circuit` dodaje `TtsQuotaError`.

`TtsConfig` (`anishift/services/tts/config.py`): `+ elevenreader_profile_root: Path | None = None`.

### 7.3. Scheduler wykonuje dowolną próbę

```text
ScheduledSynthesis[R]: result: R | None; error: TtsError | None; attempts: int      # pole clip → result
TtsScheduler.submit[R](call: Callable[[int], Awaitable[R]], *, batch_rank, request_rank, cancel,
                       accept_result: Callable[[R], Awaitable[R]],
                       on_result: Callable[[R], Awaitable[None]] | None = None,
                       on_retry: … = None) -> ScheduledSynthesis[R]
```

`_WorkItem` trzyma `call` zamiast `request_factory`; `_attempt` robi `await work.call(work.attempts)` pod tym samym
`asyncio.timeout`. Retry, circuit, `_retry_delay`, `_handle_error` bez zmian. Ścieżka per kwestia przekazuje
`call=lambda a: engine.synthesize(attempt.request_for_attempt(a), cancel=self._cancel)`. Wszystkie użycia `.clip`
przechodzą na `.result` w tym samym commicie.

Konstruktor: `TtsScheduler(*, locality: EngineLocality, config, clock)`. Scheduler potrzebuje od silnika wyłącznie
lokalności (`SYSTEM` ponawia bez opóźnienia), więc nie trzyma jego instancji.

### 7.4. Algorytm cięcia (port `SCR:snapcut.py`, `SCR:bounds.py`, `SCR:envelope.py`)

Stałe w `anishift/services/audio/segmentation.py` pod `# ── Constants ──`:
`NOISE_DBFS = -35.0`, `MIN_SILENCE_MS = 80.0`, `OPEN_MIN_SILENCE_MS = 150.0`, `BEFORE_MS = 600.0`,
`AFTER_MS = 900.0`, `BIAS_MS = 200.0`, `DISTANCE_WEIGHT = 0.25`, `FRAME_MS = 10.0`, `ENVELOPE_RATE = 16_000`.

```text
wejście: levels (dBFS ramek 10 ms nagrania zdekodowanego do mono 16 kHz), splices (utils/mp3_frames),
         spans: kolejne (start_ms, end_ms, open_end) w czasie serwera
1. czas ramki k na osi serwera = k·10 + frame_ms · (liczba sklejeń ≤ k·10)              # envelope.py
   frame_ms = FrameHeader.duration_ms pierwszej ramki nagrania (utils/mp3_frames); bez stałej długości ramki
2. dla granicy (i, i+1):
     min_len = OPEN_MIN_SILENCE_MS jeśli open_end_i, inaczej MIN_SILENCE_MS
     anchor  = (end_i + start_{i+1}) / 2 + BIAS_MS
     lo = max(end_i − BEFORE_MS, (start_i + end_i)/2);  hi = min(start_{i+1} + AFTER_MS, (start_{i+1} + end_{i+1})/2)
     cisze = ciągłe ramki z lo ≤ t < hi i poziomem < NOISE_DBFS; cisza = [t_pierwszej, t_ostatniej + 10]
     kandydaci: długość ≥ min_len; wynik = długość − DISTANCE_WEIGHT · |środek − anchor|; max
     jest kandydat → cięcie = środek ciszy
     brak         → cięcie = anchor ograniczony do [lo, hi]; uncertain += 1
3. klip i = [cięcie_{i−1}, cięcie_i]; pierwszy od 0, ostatni do końca nagrania (czas ostatniej ramki + 10)
4. granice klipów → oś zdekodowanego PCM: to_decoded(ms, splices, frame_ms) → indeks próbki w dekodzie 48 kHz
```

Różnica wobec prototypu jest jedna: granica bez ciszy nie scala klipów (kontrakt TTS wymaga klipu na kwestię),
tylko dostaje cięcie w `anchor` i ostrzeżenie. Na Tantei wszystkie 6 takich granic to kwestie urwane z przerwą
0 ms (40, 58, 152, 169), które łączenie kwestii (§7.6) usuwa jeszcze przed nagraniem.

`FfmpegClipService.split_clip`:

```text
1. data = source.read_bytes(); frame_ms = next(iter_frames(data)).duration_ms; splices = splice_times(data)
   (utils); brak ramek → ValueError
2. dwa dekodowania przez CommandRunner do plików tymczasowych w TemporaryDirectory(prefix="anishift-split-"):
     mono 16 kHz s16le (poziomy) i mono 48 kHz s16le (klipy); wejście z jawnym `-f mp3` (bez niego FFmpeg
     rozpoznaje plik z obcymi bajtami na początku jako inny format); timeout `recording_timeout_s` (300 s)
3. levels = frame_levels(pcm16k, 16_000); cuts = cut_points(levels, splices, spans) (segmentation)
4. dla każdego span: wycinek PCM 48 kHz → WAV (`wave`) w span.destination
5. log: spans, uncertain_boundaries, duration_ms (bez ścieżek i tekstu); SplitResult
```

Dekodowanie 48 kHz i zapis WAV odtwarzają `SCR:rebuild_cuts.py`, z którego powstał odsłuch właściciela.

### 7.5. Wspólne ramki MPEG (`anishift/utils/mp3_frames.py`, bez importów AniShift)

```text
FrameHeader(offset, size, sample_rate, channels, samples, version)
parse_frame_header(data, offset) -> FrameHeader | None     # z services/audio/mp3.py (_parse_frame_header)
iter_frames(data) -> Iterator[FrameHeader]                 # pomija ID3v2; ramka ważna, gdy następna też jest ważna
frames_duration_ms(data) -> float                          # EDP:src/timestamps.py, mp3_duration_ms
cut_before_ms(data, cut_ms) -> tuple[bytes, float]         # EDP:src/timestamps.py, mp3_cut_ms
splice_times(data) -> tuple[float, ...]                    # SCR:bounds.py, splice_times (oś zdekodowana)
to_decoded(server_ms, splices, frame_ms) -> float          # SCR:bounds.py; frame_ms = FrameHeader.duration_ms
```

Model zgodny z dekoderem FFmpeg (sprawdzone na syntetycznym MP3 i nagraniach Tantei, Edgerunners 02 i 03):

- ciąg bajtów między ramkami, który zaczyna się nagłówkiem (ramka, po której nie stoi poprawny nagłówek, plus obce
  bajty, np. ID3 nowego strumienia), dekoder gubi w całości: czas serwera liczy go jako jedną ramkę, a
  `splice_times` zwraca jego miejsce; dotyczy też takiego ciągu tuż po ID3 na początku pliku;
- obce bajty bez nagłówka przed pierwszą ramką (śmieci, drugi tag ID3) dekoder pomija bez straty: nie są ani
  czasem serwera, ani sklejeniem;
- ostatnią ramkę, po której stoją obce bajty do końca pliku, dekoder odtwarza: liczy się jak zwykła ramka.

`services/audio/mp3.py` używa `parse_frame_header` i traci własną kopię tabel; `read_mp3_stream_properties`
zachowuje zachowanie i błędy.

### 7.6. Łączenie kwestii urwanych (tylko silnik dokumentowy)

Łączenie jest potrzebne wyłącznie silnikowi, który czyta cały odcinek jednym dokumentem: tylko tam powstaje
granica bez pauzy, której nie da się bezpiecznie przeciąć. Silniki „kwestia po kwestii” (`elevenbytes`,
`elevenlabs`, `edge`, `sapi`) wysyłają każdą linijkę osobnym żądaniem i nie dostają łączenia.

Miejsce: `TtsTaskHandler._narration_batch`, bo tylko tam są czasy napisów potrzebne do reguły i do okna
połączonej kwestii; domena TTS czasów nie zna (I2), a kontrakt „klip na żądanie” zostaje nietknięty. Handler
dostaje keyword-only `reads_document: bool` w konstruktorze; `runtime._tts_handler` ustawia go z
`is_document_engine(snapshot.tts_profile_id)` z rejestru TTS (`frozenset({"elevenreader"})` obok `_REGISTRY`,
bez importu silnika). Dla `elevenbytes` i `elevenlabs` flaga jest `False`, więc `_narration_batch` działa jak dziś.

`anishift/text/boundaries.py` dostaje `ends_sentence(text) -> bool`: ostatni znak po `rstrip()` należy do
`SENTENCE_ENDINGS`, `CLOSING_MARKS` albo `"` (zbiór prototypu `. ! ? … " ”` jest w nim zawarty).

```text
tylko gdy reads_document i timeline is SOURCE_TIMES, po odfiltrowaniu kwestii bez mowy:
  kwestia i łączy się z i+1, gdy not ends_sentence(text_i) i start_{i+1} ≤ end_i
  łączymy wyłącznie pary: wynik połączenia nie łączy się dalej
  połączona: request_id = f"{group_id}-{order_i}", text = text_i + " " + text_{i+1},
             okno = _placement_window(start_i, end_{i+1}), order = order_i
```

Próg „przerwa ≤ 0 ms” pochodzi z pomiaru: wszystkie 11 kwestii urwanych Tantei miało przerwę 0 ms
(`SCR:snap-report.md` §4). Szyldy się nie łączą.

**Szyldy w tym samym dokumencie.** Przy `reads_document` i trybie `sign_narration` innym niż `off` handler dokłada
do batcha kwestii żądania wszystkich kandydatów szyldów (`{group_id}-sign-{grupa}`, rangi po kwestiach, okno napisu
szyldu). Jedna synteza daje jeden dokument i jedno nagranie (dopóki limit znaków nie podzieli batcha). Wynik dzieli
się po `request_id`: kwestie przechodzą ścisły `build_narration_manifest`, szyldy wersję dopuszczającą szyld bez
klipu (pominięty albo nieudany), który wypada z ostrzeżeniem i grupą w `signs_unrecorded`.
Dalej działa bez zmian ta sama ścieżka: normalizacja kwestii, `select_signs` na zmierzonych klipach, okna szyldów z
wyboru. Silnik „kwestia po kwestii” (`reads_document = False`) robi to co dotąd: najpierw kwestie, potem
`reachable_signs` na ułożonych kwestiach i drugi batch tylko z szyldami osiągalnymi. Różnica jest jedna i świadoma:
silnik dokumentowy czyta też szyldy, których nie da się umieścić (długości kwestii nie są znane przed nagraniem), a
`sign_chars_synthesized` to pokazuje. Walidacja wejścia szyldów (rodzaj, tryb, serwis audio, plik) biega przed
syntezą w obu ścieżkach. Identyfikator dokumentu bierze numer z licznika `TtsService`, więc jest unikalny w
przebiegu.

### 7.7. Przycinanie ciszy na brzegach (`normalize_clip`)

`anishift/services/audio/levels.py`:

```text
frame_levels(pcm: array[int], sample_rate: int) -> list[float]     # RMS dBFS ramek 10 ms, math.sumprod, 1e-12
speech_bounds(levels, threshold_dbfs) -> tuple[int, int] | None    # pierwsza i ostatnia ramka powyżej progu
```

Po zapisaniu surowego PCM (już po `atempo`) `normalize_clip` liczy `speech_bounds(levels, -45.0)` i zapisuje
wycinek `[pierwsza − 30 ms, ostatnia + 10 ms + 30 ms]` przyciętego do pliku; brak ramek powyżej progu → klip bez
zmian. Trim jest obróbką audio, nie cechą silnika, i obejmuje klipy każdego silnika. Zakres dla `elevenbytes`
czeka na potwierdzenie właściciela (D1); gdyby odpowiedź brzmiała „tylko ElevenReader”, flaga trafia do
`AudioRenderRequest` z tego samego `is_document_engine` (zmiana lokalna w E2 i E9). Stałe `EDGE_TRIM_DBFS = -45.0` (pomiar §6.3) i `EDGE_TRIM_MARGIN_MS = 30.0` (ochrona przed trzaskiem;
dozwolona lokalna zmiana 0–50 ms, z wpisem w outcome). Szybka ścieżka `_neutral_wav` znika (zwracała klip bez
przetwarzania). `normalization_fingerprint`: wersja 1 → 2 i sekcja `edge_trim` z obiema stałymi.

### 7.8. Mierzona głośność w miksie

```text
commands.loudness_command(ffmpeg, path):
  ffmpeg -hide_banner -nostdin -nostats -v info -i <path> -map 0:a:0
         -af aformat=channel_layouts=stereo,ebur128=framelog=quiet -f null -
probe.measure_integrated_loudness(path, *, ffmpeg, runner, timeout_s, cancel) -> float
  parsuje ze stderr wartość I z bloku "Summary:"; "-inf" albo brak → AudioDecodeError (typowany, z sugestią)
AudioService._render_output, tylko gdy request.source_audio_path is not None:
  narrator_I = measure(narrator.wav); source_I = measure(source_audio_path)      # timeout render_timeout_s, cancel
  narrator_gain_db = source_I + config.narrator_over_source_lu + config.voice_mix_offset_db − narrator_I
RenderInputs + narrator_gain_db: float
render_command: volume narratora = narrator_gain_db; po amix:
  [mixed]alimiter=limit=0.891251:attack=5:release=50:level=0:latency=1[limited]   # −1 dBFS; level=0 obowiązkowe
AudioConfig: narrator_mix_base_gain_db → narrator_over_source_lu: float = 7.5 (bez aliasu)
mix_fingerprint: wersja 3 → 4 → 5; gain: narrator_over_source_lu, voice_offset_db, original_db; limiter: parametry;
                 wersja 5 = pomiar oryginału po downmiksie do stereo
```

Pomiar źródła dotyczy oryginału przed `original_gain_db` (wzór z `SCR:loudness-report.md` §4), słyszanego jak w
stereo: przed `ebur128` stoi standardowy downmix swresample (`aformat=channel_layouts=stereo`). Cel +7,5 LU
kalibrowano na stereo, więc przy źródle 5.1 lektor w kanale centralnym ma ten sam odstęp od oryginału, który słychać
po downmiksie. Mono i stereo mierzą się identycznie jak wcześniej (sprawdzone: −28,6 i −25,6 LUFS bez zmian). Samo
`-ac 2` jako opcja wyjścia nie wystarcza: FFmpeg przekształca dźwięk dopiero za filtrem pomiaru (5.1 testowe:
−22,9 LUFS z `-ac 2` i bez). Pomiar na Edgerunners 2 E02 (E-AC-3 5.1(side)): całość −24,5 LUFS, po downmiksie
−25,2 LUFS, studyjna ścieżka AAC stereo tego samego pliku −21,7 LUFS. Trafienie resume
(`_output_hit`) nie mierzy. Narrator-only bez zmian (bez gainu, bez limitera). Zmierzone wartości są funkcją już
hashowanych wejść, więc nie wchodzą do fingerprintu.

### 7.9. Tempo i korekta na głos

`default_tts_voice_profiles()`:

| Klucz profilu | `postprocess_tempo` | `voice_mix_offset_db` |
|---|---|---|
| Dallin (`elevenbytes`, istniejący klucz) | 1,25 | 0,0 (było −2,0) |
| `elevenreader:T5l58N8RNz5DKoClpKIJ` (Fronczewski) | 1,45 | +0,5 |
| `elevenreader:hIssydxXZ1WuDorjx6Ic` (Adam) | 1,35 | +2,5 |

Panel: „Głośność lektora” to `narrator_over_source_lu` w LU; „Korekta głośności głosu” to `voice_mix_offset_db` w
LU względem celu. Współbieżność głosów ElevenReadera nie jest edytowalna (zawsze 1).

### 7.10. Silnik `elevenreader`

```text
anishift/services/tts/engines/elevenreader/
├── AGENTS.md       pułapki: CDP, profil, blokada, konto, sekrety, brak retry w transporcie
├── __init__.py     eksport ElevenReaderTtsEngine, sign_in, read_session (bez importu playwright)
├── constants.py    URL-e, endpointy, stałe czasowe z EDP, skrypty JS (SPEED, PLAYER_STATE), VOICES
├── config.py       ElevenReaderConfig.from_tts_config, resolve_voice, find_chrome, ścieżki profilu i session.json
├── types.py        ElevenReaderVoice, LibraryState, SignInOutcome, SessionRecord, AccountSettings, AccountCleanup,
│                   UploadedRead, PlayerState, AlignmentChunk
├── api_backend.py  jedna karta Playwright (Playwright ładowany leniwie, jak SDK w elevenlabs):
│                   map_http_status, map_playwright_error i fabryki błędów (auth, voice, unavailable);
│                   ReaderPage: open_library → READY | SIGNED_OUT | UNAVAILABLE, upload, open_document, press_play,
│                   player_state, set_page_speed, check_page_speed, watch_stream;
│                   konto tokenem strony: prepare_account (default_voice_id + playback_speed_rate), clean_account
│                   (przywrócenie, DELETE reads, sierota po tytule); sesja: read_session, write_session,
│                   save_cleanup, load_cleanup (atomowo), require_signed_in, sign_in (okno widoczne, kończy
│                   sprzątanie) → SignInOutcome
├── browser.py      [specyficzny] ChromeSession: ProcessLock, restrict_directory, wolny port, Popen, CDP, close;
│                   ChromeMissingError, ChromeBusyError (wzór: sapi/worker.py, elevenbytes/vpn.py)
├── recorder.py     [specyficzny] czyste: ramki WS → plik MP3 + AlignmentChunk w pamięci; duplikaty, powtórzenia po
│                   reconnect, listening_speed z ramek wysyłanych (wzór: EDP:src/downloader.py, Recorder, trim_chunk)
└── service.py      ElevenReaderTtsEngine (DocumentTtsEngine; document_chars = len(document_text)); document_text;
                    part_spans: czasy znaków + części → PartTiming na kwestię (SCR:bounds.py, load_lines)
```

**Tekst dokumentu (`document_text`, wynik K1, `DATA:snap-report.md` §13.5).** Każda kwestia to jeden akapit po
zamianie nawiasów kwadratowych na okrągłe i białych znaków na pojedyncze spacje. Między kwestiami stoi osobny akapit
`LINE_SEPARATOR = "…"` (`constants.py`): `"\n\n{LINE_SEPARATOR}\n\n".join(teksty) + "\n"`. Bez `<break>` (serwer go
ignoruje i sam stawia `<break time="0.6s"/>` wokół każdego akapitu) i bez `[pause]` (czytane na głos). Kwestie
przechodzą wcześniej filtr `is_speech_text`, więc żadna nie składa się z samego separatora, a wielokropek na końcu
kwestii („filmik…”) zostaje w jej tekście. `document_chars` to długość tego tekstu, więc separator zmienia się w
jednym miejscu.

**Czasy kwestii (`part_spans(chunks, parts)`).**

1. Tekst serwera dzieli się na ciągach tagów `<break …>` rozdzielonych białymi znakami; taki ciąg to jedna granica
   (ostatni tag może być ucięty na końcu tekstu).
2. Segment przycięty z białych znaków, który jest pusty albo równy `LINE_SEPARATOR` w całości, jest pomijany.
3. Liczba pozostałych segmentów musi równać się liczbie części, a tekst każdego segmentu tekstowi części po tej samej
   neutralizacji co w dokumencie; niezgodność → `TtsClipValidationError` (bez tekstu w `details`), nigdy
   dopasowanie na siłę.
4. `PartTiming` kwestii to start jej pierwszego i koniec ostatniego znaku na osi serwera.

`constants.VOICES`:

```text
"fronczewski": ElevenReaderVoice(alias="fronczewski", label="Piotr Fronczewski", voice_id="T5l58N8RNz5DKoClpKIJ")
"adam":        ElevenReaderVoice(alias="adam",        label="Adam",              voice_id="hIssydxXZ1WuDorjx6Ic")
DEFAULT_VOICE_ALIAS = "fronczewski"; PROVIDER_MODEL_ID = "eleven_v4"; MAX_DOCUMENT_CHARS = 50_000; LINE_SEPARATOR = "…"
PAGE_SPEED = 64.0; READING_SPEED = 1.0; wartości stałych czasowych z EDP:src/auto.py (READY 600 s, ACTION 120 s,
LIBRARY_LOAD 45 s, END_IDLE 10 s, END_SLACK 30 znaków, START 60 s, PLAY_ATTEMPTS 3, STALL 300 s)
i EDP:src/downloader.py (MIN_DEDUP_BYTES 8 KiB, TAIL_CHARS 20 000, MIN_PROBE_CHARS 10, CONNECT 30 × 0,5 s)
```

`synthesis_profile`: `engine_id="elevenreader"`, `endpoint_id="elevenreader-web-stream-v2"`,
`provider_model_id="eleven_v4"`, `resolved_voice_id=voice.voice_id`, `provider_output_id="pcm_s16le_48000_cut"`,
`adapter_version="elevenreader-v1"`, `voice_settings={"reading_speed": "1", "document_layout": "line_separator_paragraph"}`.

`capabilities`: `locality=REMOTE`, `native_output_formats=(MP3,)`, `supports_concurrency=False`,
`max_text_chars=MAX_DOCUMENT_CHARS`, `max_document_chars=MAX_DOCUMENT_CHARS`, reszta `False`/`None` jak w
`elevenbytes`. `synthesize()` → `TtsUnsupportedError`. `availability(live=False)`: Chrome znaleziony → READY,
inaczej MISSING_BINARY; `live=True` dodatkowo czyta `session.json` (bez przeglądarki).

**Algorytm jednej próby `synthesize_document(request, cancel)`:**

```text
0. walidacja: parts niepuste; voice zgodny z config; model eleven_v4; options puste; cancel → TtsCancelledError
1. browser = leniwe ChromeSession(headless=True) na silnik; page = new_page()
2. require_signed_in(page): READY → session.json(signed_in) | SIGNED_OUT → session.json(not) + TtsAuthError
   | UNAVAILABLE → TtsProviderUnavailableError(retry_after_s=60)
3. document_chars(parts) > MAX → TtsInputError (ta sama metoda, którą TtsService grupuje dokumenty); plik .txt w TemporaryDirectory(prefix="anishift-elevenreader-")
   upload → (read_id, char_count, token)                       # token i read_id tylko w pamięci
   od tej chwili wpis „usuń dokument” jest zarejestrowany do sprzątania
4. prepare_account(token, voice_id): zapamiętaj poprzednie default_voice_id i playback_speed_rate (wpis „przywróć
   konto” rejestrowany przed zapisem); zapisz voice_id i 1.0; odczytaj ponownie i sprawdź; niezgodność → TtsVoiceError
5. recorder na request.recording; page.on("websocket") tylko dla STREAM_PATH; ws.url porównywany w pamięci
6. open_document → set_page_speed(64) → press_play; pętla co 1 s (EDP Job.step):
     cancel → TtsCancelledError
     recorder.listening_speed ∉ {None, 1.0} → TtsProviderUnavailableError("streamed with Eleven v2")
     co 3 s check_page_speed; postęp → request.progress(received, char_count)
     brak audio 60 s → ponowne Play (≤ 3) → TtsTimeoutError; przestój 300 s → TtsTimeoutError
     (player_done albo received ≥ char_count) i 10 s ciszy → koniec
7. żaden adres strumienia nie zawierał voice_id → TtsVoiceError (F8)
8. received < char_count → TtsClipValidationError("incomplete"); received > char_count → ostrzeżenie z liczbami
9. timings = part_spans(recorder.chunks, parts); niezgodna liczba albo treść kwestii → TtsClipValidationError
10. EngineDocumentResult(parts = PartTiming w kolejności parts)
finally (sukces, błąd, anulowanie, asyncio.CancelledError):
         odpięcie nasłuchu; sprzątanie konta — przywrócenie głosu i tempa, DELETE reads/{read_id} — każdy krok
         osobno, z własnym krótkim limitem czasu, odporne na anulowanie (asyncio.shield); udany krok znika z
         AccountCleanup, nieudany zostaje; potem zamknięcie karty; przy anulowaniu albo błędzie przeglądarki
         ChromeSession.close() dopiero po sprzątaniu
wyjątki Playwright → map_playwright_error (api_backend.py)
```

Każde długie oczekiwanie Playwright idzie przez helper `_unless_cancelled(awaitable, cancel)`
(`asyncio.wait({task, cancel.wait()}, FIRST_COMPLETED)`), więc anulowanie nie czeka do 10 minut na „Play”.
Ponowne „Play” to czynność odtwarzacza w jednej próbie, nie retry (Z6).

**Sprzątanie (U14, F28).** Śmieci na koncie nie zostają w żadnej ścieżce. Zaległe kroki z `AccountCleanup`
silnik wykonuje na początku następnej próby (po `require_signed_in`, przed uploadem) i w `close()`, gdy przeglądarka
jeszcze działa. Krok, który zawiedzie także w `close()`, daje ostrzeżenie w logu (bez `read_id` i tokenu: tylko
rodzaj kroku i status) i komunikat w panelu „ElevenReader: nie udało się posprzątać konta — usuń ostatni dokument
„anishift” z biblioteki i sprawdź głos w aplikacji”. Wynik nagrania pozostaje ważny. Plik wgrywany ma stałą nazwę
`anishift.txt`, więc właściciel rozpozna go w bibliotece.

### 7.11. Ścieżka dokumentu w `TtsService`

`TtsService.__init__` dostaje `splitter: ClipSplitter | None = None`. `_run_batch` po `_ensure_runtime` wybiera
`_run_document_batch`, gdy `engine.capabilities.max_document_chars is not None`.

```text
1. splitter is None albo silnik nie spełnia DocumentTtsEngine → każda kwestia mowy: TtsUnsupportedError
2. każda kwestia: niemowa → SKIPPED; chunking (max_text_chars) ≠ 1 część → TtsInputError tej kwestii;
   engine.validate_part(część) rzuca TtsInputError → ten błąd tej kwestii (ta sama funkcja, którą silnik sprawdza
   części przed uploadem);
   tożsamość resume (SynthesisIdentity, profil silnika); trafienie → cached; reszta → pending
3. dokumenty: zachłannie w kolejności batcha, póki engine.document_chars(części) ≤ max_document_chars; to ta sama
   funkcja, którą silnik liczy i sprawdza wysyłany dokument (tekst, separatory między kwestiami, znak końcowy),
   więc separator zmienia się w jednym miejscu; kwestia z document_chars((część,)) > limit → TtsInputError
4. dokumenty po kolei; scheduler.submit(call, accept_result, …):
     call(a): usuń nagranie i klipy poprzedniej próby; recording = repository.temporary_clip_path(MP3)
              → engine.synthesize_document(...)
     accept(r): własność wyniku jak _ProviderAttempt.accept_result;
                spans = ClipSpan(part, timing, open_end = not ends_sentence(text), nowa ścieżka WAV)
                split = await to_thread(splitter.split_clip, recording, spans, expectation(WAV))
                (RuntimeError, OSError, ValueError) → TtsClipValidationError (przejściowy)
                każdy klip → repository.validate_temporary_clip; None → TtsClipValidationError
     błąd → każda kwestia dokumentu FAILED z tym błędem; sukces → commit_clip każdej kwestii
     zawsze: usuń nagranie i niezatwierdzone pliki
5. flush; _batch_result
```

`provider_calls` i `retries` dokumentu liczone na pierwszej kwestii dokumentu. Postęp:
`rozstrzygnięte + floor(received / total × liczba kwestii dokumentu)` przez `_safe_callback`.

### 7.12. Sesja, konto, sekrety

- Cookies żyją w `config/elevenreader/chrome-profile/`; AniShift ich nie czyta. `config/elevenreader/` jest w
  `.gitignore` i dostaje `restrict_directory` przy każdym starcie (idempotentne).
- Token strony istnieje tylko w pamięci jednej próby; nie trafia do logów, wyjątków, `details` ani plików.
- `session.json`: `{"signed_in": bool, "checked_at": ISO-8601, "restore": {…} | null, "delete_document": bool}`,
  zapis atomowy; zaległe sprzątanie konta bez `read_id` i tokenu.
- Wygaśnięcie przed uploadem → `TtsAuthError` (trwały, circuit), sugestia „Ustawienia → Lektor → Zaloguj / sprawdź
  sesję”; po zalogowaniu ponowienie czyta tylko brakujące kwestie. Wygaśnięcie w trakcie → przestój → ponowienie →
  następna próba wykrywa SIGNED_OUT.
- `sign_in`: `ChromeSession(headless=False)`, biblioteka; READY → SIGNED_IN; inaczej co 1 s sprawdza „Import” do
  600 s albo zamknięcia okna. BUSY, gdy blokada profilu zajęta (trwa nagrywanie); NO_CHROME; FAILED.

### 7.13. Reuse zamiast drugiej wersji

| Duplikat, który by powstał | Rozwiązanie |
|---|---|
| drugi parser ramek MPEG (silnik i audio) | `utils/mp3_frames.py`; `services/audio/mp3.py` z niego korzysta |
| zestaw znaków końca zdania w handlerze i w TTS | `text.boundaries.ends_sentence` |
| poziomy RMS w trim i w cięciu | `services/audio/levels.py` |
| trzecia funkcja ACL katalogu | `platform/private_dir.restrict_directory` z kodu `_protect_profile`; qBittorrent ją woła |
| druga funkcja szukania programu | `platform/installed.find_installed(locations, stem)`; qBittorrent i Chrome |
| druga pętla retry (EDP: 120 × 1 min) | brak; awaria serwisu to `TtsProviderUnavailableError(retry_after_s=60)` |
| drugi mechanizm resume | brak; `TtsResumeRepository` per kwestia |

### 7.14. Odporność: klasyfikacja błędów

| Sytuacja | Błąd | Klasa | Reakcja |
|---|---|---|---|
| brak Chrome | `TtsConfigError` | trwały | circuit; sugestia instalacji Chrome |
| profil zajęty (logowanie w panelu) | `TtsProviderUnavailableError(retry_after_s=60)` | przejściowy | ponowienie |
| serwis niedostępny, 5xx, awaria przeglądarki | `TtsProviderUnavailableError(retry_after_s=60)` | przejściowy | ponowienie z nową przeglądarką |
| wylogowano, 401 | `TtsAuthError` | trwały | circuit; sugestia logowania |
| 403 (blokada konta) | `TtsAuthError(details={"status": 403})` | trwały | circuit; sugestia powrotu na `elevenbytes` |
| brak kredytów (402, do potwierdzenia w K2) | `TtsQuotaError` | trwały | circuit; sugestia `elevenbytes` |
| 429 | `TtsRateLimitError(retry_after_s=Retry-After)` | przejściowy | ponowienie |
| głos nie ustawił się / brak w adresie strumienia | `TtsVoiceError` | trwały | circuit |
| strumień v2 zamiast v4 | `TtsProviderUnavailableError` | przejściowy | ponowienie (prędkość ustawiana od nowa) |
| brak audio, przestój, timeout akcji | `TtsTimeoutError` | przejściowy | ponowienie |
| nagranie niekompletne, niezgodna liczba kwestii, błąd cięcia | `TtsClipValidationError` | przejściowy | ponowienie (cache serwera: bez kredytów) |
| anulowanie | `TtsCancelledError` | trwały | koniec bez ponowienia |
| sprzątanie konta nieudane (przywrócenie głosu i tempa, DELETE) | — | ponowienie przy następnej próbie i `close()`, potem ostrzeżenie w logu i komunikat w panelu | nagranie ważne |

Każdy komunikat trwałego błędu kończy się zdaniem o przełączeniu silnika na ElevenBytes w Ustawieniach → Lektor.

Konfiguracja przebiegu w `anishift/application/runtime.py`: `_TTS_REQUEST_TIMEOUT_S["elevenreader"] = 3600.0`,
`_TTS_RETRY_BACKOFF_S["elevenreader"] = (60.0, 120.0, 300.0, 600.0)`, `shutdown_deadline_s = 15.0`,
`max_concurrency = 1`, `queue_capacity = 2`, `elevenreader_profile_root = paths.elevenreader_dir()`,
`scheduler_timeout_enabled = False` dla silnika dokumentowego (`is_document_engine`), tak jak dziś dla
`elevenbytes` przez VPN: silnik sam pilnuje `deadline_s` dokumentu i sprzątania konta, więc zewnętrzny
`asyncio.timeout` schedulera nie może przerwać próby w połowie sprzątania.

### 7.15. Panel Ustawień (bez zmiany wyglądu)

Kategoria Lektor przy `elevenreader`: Silnik, Model (`eleven_v4`, tylko odczyt), Głos (2 wartości), Ponowień, Tempo
końcowe, Korekta głośności głosu, Kodek, Bitrate; sekcja „SESJA”: „Sesja ElevenReader” (z `session.json`:
„zalogowano · 30.10 14:03”, „nie zalogowano · …”, „nie sprawdzono”) i akcja „Zaloguj / sprawdź sesję” (wątek jak
`SettingsController._start_probe`; wyniki: „✓ Zalogowano”, „✗ Nie zalogowano”, „✗ Lektor właśnie nagrywa —
spróbuj po zakończeniu”, „✗ Nie znaleziono Google Chrome”, „✗ Nie udało się sprawdzić sesji”). Brak „Syntez
jednocześnie” i „VPN ElevenBytes”. Kategoria Dźwięk: „Głośność lektora” w LU ponad oryginał.

## 8. Zakres

**In scope:** etapy 0–10 z §9.

**Out of scope:** audiobooki, karaoke, monitor kredytów, logowanie e-mailem, próg ciszy względny wobec głosu,
plikowy wariant ACL w `local_control.py`, zmiana osi czasu (`plan_timeline`) i ownera rezydenta, Linux.

**Forbidden:** Z1–Z9; zmiana zachowania syntezy istniejących silników poza I1; zależności poza `playwright`
(`numpy`, `miniaudio` zakazane); `playwright install`; logowanie `ws.url`, `read_id`, tokenu, odpowiedzi HTTP,
tekstu dokumentu, ścieżek absolutnych; testy sieciowe bez zgody właściciela w tej sesji; zmiana plików czytanych
przez rezydenta (`config/settings.json`, `.env`, `config/watch/`) bez prośby do właściciela o jego zamknięcie;
worktrees i `uv --active`; commit na `main`; stopki AI.

**Deferred:** ponowne użycie wgranego dokumentu między przebiegami; słowne czasy w raporcie jakości; odczyt
`current_credits` przed i po odcinku.

**Dozwolone decyzje lokalne:** nazwy prywatnych helperów; podział `api_backend.py` przy
zachowaniu granic §7.10; brzmienie komunikatów w granicach §7.15; margines trimu 0–50 ms; stałe czasowe EDP ±50%
po pomiarze w K2 (wpis w outcome); struktura fałszywych obiektów testowych.

**Zatrzymaj się i wróć po decyzję, gdy:**

- K1 pokaże, że próg −35 dBFS nie działa na innym materiale bez zmiany reguły (np. potrzeba progu względnego);
- na nagraniu z K3 log pokaże granice `uncertain`, a właściciel usłyszy w nich ucięte słowo;
- test zgodności cięcia (N2) nie przejdzie po wiernym porcie;
- refaktor schedulera zmieni zachowanie choć jednego istniejącego testu schedulera lub serwisu;
- potrzebna byłaby zmiana `plan_timeline` albo `SpeechBatch`;
- strona pokaże ostrzeżenie o naruszeniu zasad albo konto zostanie zablokowane;
- `playwright` nie zainstaluje się albo nie działa na Python 3.14 lub w `mypy --platform linux`.

## 9. Etapy

### 9.0. Mapa zależności

```text
E0 preflight (orkiestrator)
 ├─> E1 utils/mp3_frames ─┬─> E2 trim brzegów ─> E3 głośność ─> E4 cięcie (+ K1)
 │                        └─────────────────────────────────────> E7 silnik (recorder, lines)
 ├─> E8 łączenie kwestii urwanych za flagą (+ ends_sentence) ─> E5 kontrakt dokumentu TTS ─> E7 silnik (service)
 └─> E6 platforma (installed, private_dir) ─────────────────────────────────────────> E7 silnik (browser)
E3 + E4 + E5 + E7 + E8 ─> E9 integracja aplikacji ─> E10 K2, K3, dokumentacja, review, PR
```

Pasy zapisu (rozłączne):

| Pas | Etapy | Zakres zapisu |
|---|---|---|
| audio | E1 → E2 → E3 → E4 | `anishift/utils/mp3_frames.py`, `anishift/services/audio/`, w E3 także zmiana nazwy pola w `application/{planning,runtime,service}.py`, `config/{user_settings,field_catalog}.py`, `cli/interactive/settings.py`, `scripts/tmp/` |
| tts | E5 | `anishift/services/tts/{types,protocols,scheduler,service,errors,config,__init__}.py`, `anishift/errors.py` |
| silnik | E6 → E7 | `anishift/platform/`, `anishift/services/tts/engines/`, `pyproject.toml`/`uv.lock` przez `uv add` |
| aplikacja | E8 | `anishift/application/tts_handler.py`, `anishift/text/boundaries.py`, jedna linia w `application/runtime.py` (`_tts_handler`; E3 zmienia tam tylko `_audio_config`) |
| integracja | E9 | `application/{tts_clips,runtime,service,__init__}.py`, `config/`, `cli/interactive/settings.py`, `setup/doctor.py`, `paths.py`, `config/README.md`, docs |

Każdy etap ma własne testy w `tests/<obszar>/` swojego pasa. Pasy są niezależne semantycznie; równolegle mogą
pracować tylko wtedy, gdy orkiestrator dopuści kilku piszących w jednym checkoucie: wtedy każdy uruchamia testy
swojego obszaru, a pełne bramki i commit idą po kolei (jeden commit naraz). Bez tej zgody kolejność dowolna w
obrębie fali: fala 1 = E8 (najpierw, mały), E1, E5, E6; fala 2 = E2–E4, E7; fala 3 = E9; fala 4 = E10.

Każdy wykonawca dostaje w briefie wprost: zero legacy (stara nazwa, ścieżka i format znikają w tym samym diffie,
bez aliasów i warstw zgodności), reuse przed nowym kodem, brak prozy w testach, bramki na `anishift/ tests/`.

---

### E0. Preflight (orkiestrator)

1. `git status` czyste, `git log -1` = `f5fff6b`. Gałąź `work/tts/01-elevenreader` z `main`, bez worktree.
2. **Pilne:** skopiuj dane prototypu z SCR (katalog tymczasowy sesji) do DATA:
   `SCR/tantei/{anishift-test-*.mp3, anishift-test-*.align.jsonl, cuts-*.json, lines.json, episode.txt, record.json}`,
   `SCR/edge02/`, `SCR/edge03/`, `SCR/*.py`, `SCR/*.md`. DATA leży poza repo (głos `famous`, Z4).
3. Dopisz `config/elevenreader/` do `.gitignore` (blok `config/`), sprawdź
   `git check-ignore -v config/elevenreader/chrome-profile/Default`, commit
   `chore(repo): ignore the ElevenReader browser profile`.
4. Bramki S1 na baseline; zapisz liczby i failing testy.

**Gate:** DATA kompletne; `.gitignore` zacommitowany; baseline zapisany.

### E1. Wspólne ramki MPEG (pas audio)

**Cel:** jedno źródło parsowania ramek dla audio i silnika.
**Pliki:** NEW `anishift/utils/mp3_frames.py`; MODIFY `anishift/services/audio/mp3.py`, `anishift/utils/AGENTS.md`,
`anishift/utils/_portable.py` (wpis manifestu przenośności); NEW `tests/utils/test_mp3_frames.py` (bez
`__init__.py`).
**Kontrakt:** §7.5.
**Testy:** nagłówki MPEG-1/2/2.5 i `FrameHeader.duration_ms`, ID3v2, obce bajty na początku i na końcu;
`frames_duration_ms`; `cut_before_ms` (granica tolerancji 0,5 ms); `splice_times` na syntetycznym MP3 z wstawioną
uszkodzoną ramką 462 B; `to_decoded` ze sklejeniami i bez nich; test integracyjny
`skipif(not DATA)`: `splice_times` nagrania Tantei daje 22 miejsca, a `frames_duration_ms` = 814 210 ms ± 1.
**Dowody:** `uv run pytest tests/utils tests/services/audio/test_audio_mp3.py` bez zmian istniejących asercji;
bramki S1.
**Zależy od:** E0. **Odblokowuje:** E2 (pośrednio), E4, E7.

### E2. Przycinanie ciszy na brzegach (pas audio)

**Cel:** F12.
**Pliki:** NEW `anishift/services/audio/levels.py`; MODIFY `normalize.py` (trim po FFmpeg; usunięcie
`_neutral_wav`), `fingerprint.py` (`_NORMALIZATION_ALGORITHM_VERSION` 1 → 2, sekcja `edge_trim`),
`services/audio/AGENTS.md`; testy `tests/services/audio/test_audio_levels.py` (NEW), `test_audio_normalize.py`,
`test_audio_fingerprint.py`.
**Kontrakt:** §7.7.
**Testy:** `frame_levels` na sinusie o znanej amplitudzie (dBFS ± 0,1); `speech_bounds` dla ciszy wokół tonu, dla
samej ciszy (None); normalizacja klipu z 300 ms ciszy po obu stronach daje długość tonu + 2 × 30 ms ± 10 ms;
klip bez mowy zostaje cały; fingerprint zmienia się przy zmianie progu; test fast-path przepisany na nowe
zachowanie (WAV neutralny też przechodzi trim).
**Dowody:** bramki S1; pomiar na DATA (skrypt jednorazowy w `scripts/tmp/`, potem usunięty): liczba kwestii
dłuższych niż okno na Tantei przy tempie 1,25 po trimie z marginesem 30 ms: Dallin 12, Fronczewski 27, Adam 20
(bez marginesu 10/24/17 jak w §6.3). Margines 30 ms zostaje, bo chroni ciche końcówki słów; koszt to 2–3 kwestie
na odcinek nieznacznie dłuższe niż okno.
**Zależy od:** E0.

### E3. Mierzona głośność i limiter (pas audio)

**Cel:** F13–F16, Z9.
**Pliki:** MODIFY `services/audio/{commands,probe,service,output,config,fingerprint}.py`, `services/audio/AGENTS.md`;
zmiana nazwy pola w `application/{planning,runtime,service}.py`, `config/{user_settings,field_catalog}.py`,
`cli/interactive/settings.py` (etykieta „Głośność lektora”, jednostka LU), testy z `grep -rn
narrator_mix_base_gain_db tests`; `default_tts_voice_profiles` Dallin `voice_mix_offset_db = 0.0`; NEW
`scripts/tmp/migrate_narrator_loudness.py` (jednorazowy).
**Kontrakt:** §7.8. Po zmianie `grep -rn narrator_mix_base_gain_db anishift tests` = 0.
**Skrypt migracji:** czyta `config/settings.json`, usuwa `narrator_mix_base_gain_db`, wpisuje
`narrator_over_source_lu = 7.5`, ustawia `voice_mix_offset_db = 0` w profilu Dallina, zapis atomowy z kopią `.bak`.
Uruchamia orkiestrator po prośbie do właściciela o zamknięcie rezydenta; potem właściciel otwiera panel i widzi
„Głośność lektora 7,5 LU”; skrypt jest usuwany (nie trafia do commita).
**Testy:** `loudness_command` (dokładne argumenty); parser `Summary:` na zapisanym stderr FFmpeg (w tym `-inf` →
`AudioDecodeError`); `render_command` z `narrator_gain_db` i limiterem `level=0`; narrator-only bez `volume` i bez
`alimiter`; `_render_output` liczy gain z dwóch pomiarów (fałszywy runner); trafienie resume nie mierzy;
fingerprint wersja 4 i zmiana przy innym `narrator_over_source_lu`; test integracyjny z prawdziwym FFmpeg:
`measure_integrated_loudness` na dwóch wygenerowanych sygnałach (szum różowy, ton) różniących się o znaną liczbę dB
zwraca różnicę ± 0,2 LU, a pełny render z głośnym narratorem ma true peak wyjścia ≤ −0,9 dBTP.
**Dowody:** bramki S1; `grep` = 0; render Tantei z DATA każdym z trzech głosów: lektor 7,5 ± 0,3 LU nad
oryginałem (Adam 9,5 ± 0,3), true peak ≤ −0,9 dBTP.
**Zależy od:** E2 (wspólne pliki `fingerprint.py`, `commands.py`). E9 zaczyna się po E3 (wspólne pliki `config/`).

### E4. Cięcie nagrania na kwestie (pas audio)

**Cel:** F9, F10, N2.
**Pliki:** NEW `anishift/services/audio/segmentation.py`, testy `tests/services/audio/test_audio_segmentation.py`;
MODIFY `services/audio/AGENTS.md`, `commands.py` (komenda dekodowania nagrania do mono s16le w zadanej
częstotliwości, jeśli istniejąca `decode_command` się nie nadaje).
**Kontrakt:** §7.4, kroki 1–3 jako czyste funkcje (`server_frame_times`, `cut_points` → `CutDecision(at_ms,
uncertain)`), bez plików i FFmpeg. Adapter `split_clip` powstaje w E9.
**Testy:** syntetyczne poziomy: wybór dłuższej ciszy bliżej kotwicy; cisza 100 ms wystarcza dla kwestii zamkniętej
i nie wystarcza dla otwartej; brak ciszy → `anchor` i `uncertain`; okno ograniczone połową kwestii; przeliczenie
czasu ramek przy sklejeniach. **Test zgodności** (`integration`, `skipif(not DATA)`): dla obu głosów Tantei, po
wczytaniu czasów znaków z `align.jsonl` (helper testowy) i poziomów z dekodu 16 kHz, `cut_points` równa się
`cuts-<głos>.json` (±10 ms) na wszystkich granicach, które prototyp ciął; na 3 scalonych granicach daje `uncertain`.
**Dowody:** bramki S1; wynik testu zgodności z liczbami.
**Punkt kontrolny K1 (walidacja Edgerunners 02 i 03):** nagrania obu odcinków już są (`SCR:edge02`,
`SCR:edge03`), walidacja prototypem trwa. Gdy E4 jest gotowy, orkiestrator uruchamia `cut_points` na nagraniach z
`DATA/edge02`, `DATA/edge03` i ocenia granice tym samym instrumentem co prototyp (`SCR:verify_clips.py`,
`SCR:edges.py`; CrisperWhisper tylko przez MangaShift, poza AniShift). PASS: zero wycieków i ucięć poza znanym
szumem pisowni. FAIL z tymi samymi parametrami → poprawka stałych w E4 i ponowny test zgodności; FAIL wymagający
innej reguły → stop i decyzja (§8).
**Zależy od:** E1, E2 (`levels.py`).

### E5. Kontrakt dokumentu w domenie TTS (pas tts)

**Cel:** F2–F4, F6, N7, I2, I3.
**Pliki:** MODIFY `anishift/services/tts/{types,protocols,scheduler,service,errors,config,__init__}.py`,
`anishift/errors.py`, `anishift/services/tts/AGENTS.md`; testy `tests/services/tts/test_tts_scheduler.py`,
`test_tts_service.py`, `test_tts_contract.py`; NEW `test_tts_document_service.py`.
**Kontrakt:** §7.2, §7.3, §7.11. `ends_sentence` pochodzi z E8; E5 go nie definiuje.
**Testy:** wszystkie istniejące testy schedulera i serwisu przechodzą po zmianie `submit(call=…)` i `.result` bez
zmiany asercji zachowania; nowe: pola i zamrożenie typów; `max_document_chars` domyślnie `None`; fałszywy silnik
dokumentowy i fałszywy splitter: wszystkie kwestie z resume → zero wywołań silnika; część z resume → dokument tylko
z brakujących; podział na dokumenty przy limicie; kwestia ponad limit → `TtsInputError` tej kwestii; błąd splittera
→ ponowienie; `TtsQuotaError` otwiera circuit; postęp rośnie z `progress`; brak splittera → `TtsUnsupportedError`;
`open_end` w `ClipSpan` zgodny z `ends_sentence`; anulowanie przed commitem.
**Dowody:** bramki S1; `grep -rn "\.clip\b" anishift/services/tts tests/services/tts` bez starych użyć pola
`ScheduledSynthesis.clip`.
**Zależy od:** E0; przed użyciem `ends_sentence` w `_run_document_batch` — E8 (mały, robiony pierwszy w fali 1).

### E6. Platforma: wspólne helpery (pas silnik)

**Cel:** reuse §7.13.
**Pliki:** NEW `anishift/platform/installed.py` (`find_installed(locations, stem) -> Path | None`), NEW
`anishift/platform/private_dir.py` (`restrict_directory(root)`, błąd `PlatformError` z polskim komunikatem w
wołającym); MODIFY `qbittorrent_config.py` (`installed_executable` używa `find_installed`),
`qbittorrent_process.py` (`_protect_profile` woła `restrict_directory` i mapuje błąd jak dziś),
`platform/AGENTS.md`; NEW `tests/platform/test_installed.py`, `test_private_dir.py`.
**Testy:** nowe helpery (monkeypatch środowiska, fałszywe `subprocess.run`); istniejące
`tests/platform/test_qbittorrent_config.py`, `test_qbittorrent_process.py`, `tests/setup/test_doctor.py` bez zmian.
**Dowody:** bramki S1.
**Zależy od:** E0.

### E7. Silnik `elevenreader` (pas silnik)

**Cel:** F1, F5, F7, F8, F17, F18, F20–F23, F25–F28, N1, N4, N5.
**Pliki:** NEW pakiet §7.10 z AGENTS.md; MODIFY `anishift/services/tts/engines/__init__.py` (`TtsEngineId`,
`_REGISTRY`, `is_document_engine` z `frozenset({"elevenreader"})`; test: silnik ma `max_document_chars` wtedy i
tylko wtedy, gdy `is_document_engine` zwraca `True`), `anishift/services/tts/engines/AGENTS.md`; `uv add playwright` (bez `playwright install`); NEW testy
`tests/services/tts/test_tts_elevenreader_{config,api_backend,recorder,service,service_data}.py`,
`tests/services/tts/elevenreader_fakes.py`, `test_tts_elevenreader_network.py` (`network`, plus zmienna
`ANISHIFT_ELEVENREADER_LIVE=1`); MODIFY `test_tts_registry.py`, `test_tts_contract.py`.
**Kolejność wewnątrz:** części czyste (`constants`, `config`, `types`, mapowanie błędów w `api_backend`) mogą powstać przed E1 i
E5; `recorder` po E1; `browser` po E6; `service` po E5.
**Kontrakt:** §7.10, §7.12, §7.14.
**Testy:** `resolve_voice` (alias, ID, nieznany → `TtsVoiceError`); `from_tts_config` odrzuca inny model,
`max_concurrency ≠ 1`, brak `elevenreader_profile_root`; `document_text` (nawiasy, białe znaki, akapit „…” między kwestiami); recorder: duplikat
≥ 8 KiB pominięty, < 8 KiB zachowany, powtórzenie po ramce `config` przycięte razem z audio, ramka bez
`alignment`, `normalizedAlignment`, `listening_speed` z ramek wysyłanych; `part_spans`: podział po
`<break …/>` (także tag rozcięty między paczkami), dwa sąsiednie tagi to jedna granica, akapit „…” nie jest
kwestią, „filmik…” na końcu kwestii zostaje w jej tekście, białe znaki na brzegach, końcowy `<break time="2s"/>` bez
pustej kwestii, niezgodna liczba albo treść → błąd, zgodność z `SCR:bounds.py` na DATA (Tantei i `edge02c`, `skipif`); `map_http_status` (401, 402, 403, 429 z `Retry-After`, 5xx);
silnik na fałszywej stronie i przeglądarce: SIGNED_OUT → `TtsAuthError` i `session.json`, głos niezgodny po
zapisie → `TtsVoiceError`, brak `voice_id` w adresie strumienia → `TtsVoiceError`, v2 → błąd przejściowy,
niekompletne nagranie, niezgodna liczba kwestii, anulowanie w trakcie (≤ 2 s, Chrome zamknięty, blokada
zwolniona), przywrócenie głosu i tempa oraz `DELETE` wołane po sukcesie, błędzie, anulowaniu i
`asyncio.CancelledError`; nieudany krok zostaje w `AccountCleanup`, wykonuje się na początku następnej próby i w
`close()`, a trwała porażka daje ostrzeżenie i komunikat; import pakietu w procesie
potomnym nie ładuje `playwright`; test logów: żaden rekord nie zawiera tokenu, `read_id` ani adresu WS.
**Dowody:** bramki S1 (w tym `mypy --platform linux`); `uv run pip-audit` na eksportowanym locku jak w CI.
**Zależy od:** E1, E5, E6.

### E8. Łączenie kwestii urwanych za flagą (pas aplikacja)

**Cel:** F11, U5, I1.
**Pliki:** MODIFY `anishift/text/boundaries.py` (`ends_sentence`), `anishift/text/AGENTS.md`,
`anishift/application/tts_handler.py` (`TtsTaskHandler(…, reads_document: bool)`, `_narration_batch`),
`anishift/application/runtime.py` (`_tts_handler` przekazuje na razie `reads_document=False`; E9 podmienia na
`is_document_engine(...)`); testy `tests/text/` i `tests/application/test_tts_handler.py`.
**Kontrakt:** §7.6.
**Testy:** `ends_sentence` dla `. ! ? … " ” »` i przecinka; `reads_document=False` → żądania identyczne jak przed
zmianą (ten sam skrypt, te same `request_id`, teksty i okna); `reads_document=True`: para urwana z przerwą 0 ms →
jedno żądanie z oknem obu; przerwa 1 ms → dwa żądania; kwestia zakończona kropką → dwa; trzy kolejne urwane → para + pojedyncza;
`CONTINUOUS` (TXT) → bez łączenia; kolejność `order` rosnąca; manifest narracji z połączoną kwestią przechodzi
`build_narration_manifest`. Na DATA (`skipif`): `lines.json` Tantei daje 11 połączeń.
**Dowody:** bramki S1.
**Zależy od:** E0.

### E9. Integracja aplikacji (pas integracja)

**Cel:** F1–F28 działają w produkcie.
**Pliki:**

- `anishift/application/tts_clips.py`: `FfmpegClipService.split_clip` (§7.4, adapter) i parametr
  `recording_timeout_s`; `anishift/application/runtime.py`: `_tts_config` (§7.14), `_tts_handler` wstrzykuje
  `splitter` i `reads_document=is_document_engine(snapshot.tts_profile_id)`.
- `anishift/paths.py`: `elevenreader_dir() = config_dir() / "elevenreader"`; `config/README.md`.
- `anishift/config/user_settings.py`: gałąź `elevenreader` w `tts_voice_label`, `resolved_tts_voice_id`,
  `_normalize_tts_selection` (F19: obcy alias → głos domyślny silnika docelowego), profile §7.9.
- `anishift/config/field_catalog.py`: modele, głosy i profile `elevenreader` z listy silnika (`VOICES`), ukryta
  współbieżność.
- `anishift/application/service.py`: `_tts_allowed_voice_ids`, `tts_is_paid` (ElevenReader: tak),
  `elevenreader_session()`, `elevenreader_sign_in()` i DTO; eksport w `application/__init__.py` (panel importuje
  fasadę).
- `anishift/cli/interactive/settings.py`: `_ENGINE_LABELS["elevenreader"] = "ElevenReader"`, sekcja SESJA (§7.15).
- `anishift/setup/doctor.py`: `check_elevenreader()` (F24) w `run_doctor`.
- AGENTS.md: `application/`, `config/`, `cli/`, `setup/`; `docs/reference/settings.md`.

**Testy:** `split_clip` z prawdziwym FFmpeg na syntetycznym MP3 trzech tonów z ciszą i jednym sklejeniem
(`integration`): trzy WAV 48 kHz o oczekiwanych długościach ± 20 ms; ścieżka dokumentu end-to-end z fałszywym
silnikiem i prawdziwym splitterem; `user_settings`: przełączenia `elevenreader` ↔ `elevenbytes` i obcy alias w
pliku → Dallin; `field_catalog` pola widoczne/ukryte; panel: wiersze SESJA i akcja, stany wyniku; `doctor`
FAIL/WARN/SKIP; `runtime` daje `TtsConfig` §7.14, w tym `scheduler_timeout_enabled is False` dla `elevenreader` i
`True` dla `elevenbytes` bez VPN (`tests/application/test_runtime_config.py`); `paths`.
**Dowody:** bramki S1; `uv run anishift doctor` przy silniku `elevenreader` bez sesji → WARN z sugestią.
**Zależy od:** E3, E4, E5, E7, E8.

### E10. Odbiór (orkiestrator i właściciel)

1. **K2 — konto i test sieciowy** (zgoda właściciela; rezydent zamknięty): akcja „Zaloguj / sprawdź sesję”;
   `ANISHIFT_ELEVENREADER_LIVE=1 uv run pytest -m network tests/services/tts/test_tts_elevenreader_network.py`
   (trzy kwestie, oba głosy); sprawdzenie, że głos konta wrócił i dokument zniknął z biblioteki. Jeśli strona da
   okazję zobaczyć odpowiedź na brak kredytów — zapis statusu w outcome (§7.14, 402).
2. **K3 — ucho właściciela:** jeden prawdziwy odcinek w Ręcznym, osobno Fronczewski i Adam; potem ten sam odcinek
   na `elevenbytes` (S5).

   ```text
   Uruchom: anishift → Ustawienia → Lektor → ElevenReader, głos; Ręczny → odcinek → Start
   Zrób: obejrzyj 5 minut z lektorem; powtórz z drugim głosem i z ElevenBytes
   Oczekiwany rezultat: lektor słyszalny ponad muzyką i dialogiem jak dziś Dallin; bez uciętych słów;
                        tempo zbliżone do Dallina; brak przesterów
   Zwróć uwagę na: końcówki kwestii, kwestie przechodzące w następny napis, głośne sceny
   Przekaż wynik jako: OK albo minuta odcinka + co słychać
   ```

3. README EN i PL (silnik, logowanie, ryzyko regulaminu), `docs/README.md`, `docs/ideas.md`, outcome
   `outcomes/01-elevenreader-engine.md`.
4. Review krzyżowe całej gałęzi innym modelem niż autor (S6); skan sekretów (S7):
   `git grep -n -i -E "@gmail|authorization: |u:[A-Za-z0-9]{20}|chrome-profile/Default" -- anishift tests` = 0,
   a `git status --ignored config/elevenreader` pokazuje katalog jako ignorowany.
5. PR do `main`.

## 10. Zasady testów i bramki

- Każdy plik testowy ma dokładnie jeden marker poziomu (`unit`, `integration`, `e2e`) przez `pytestmark`;
  `network` jako marker zdolności.
- Zero prozy w testach, `conftest.py` i `elevenreader_fakes.py`; scenariusz w nazwie
  `test_<jednostka>_<scenariusz>_<oczekiwanie>`.
- Bez `__init__.py` w nowych katalogach testów; izolacja `tmp_path`/`monkeypatch` (xdist).
- Dane prawdziwego głosu tylko w DATA; testy na nich `integration` z `skipif(not path.is_file())`.
- Fixture ramek do repo tylko z audio zastąpionym syntetycznymi ramkami MP3 (skrypt jednorazowy w `scripts/tmp/`).

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest
```

## 11. Git

- Gałąź `work/tts/01-elevenreader`; commity `typ(scope): opis` ze scope z `scripts/hooks/check_commit_msg.py`; jeden
  commit na temat (np. ramki MPEG, trim, głośność, cięcie, kontrakt dokumentu, platforma, silnik, łączenie kwestii,
  integracja, dokumentacja); poprawki z review wchodzą do commita swojego tematu.
- Zależność wyłącznie `uv add playwright`; commit razem z silnikiem.
- PR po E10, bez stopek AI.

## 12. Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja |
|---|---|---|
| ban konta, zmiana warunków | 403, ostrzeżenie strony | stop; `elevenbytes`; decyzja właściciela |
| zmiana wewnętrznego API lub interfejsu strony | błędy selektorów, brak ramek | błąd przejściowy → po wyczerpaniu circuit z sugestią `elevenbytes`; poprawka `api_backend.py`/`constants.py` |
| próg −35 dBFS nie przenosi się na inny materiał | K1, `uncertain` > 0 w logu | korekta stałych; przy zmianie reguły stop (§8) |
| dane prototypu znikną z katalogu tymczasowego | brak plików SCR | E0 krok 2 jako pierwszy ruch |
| `atempo` 1,45 słyszalnie szarpie | K3 | niższe tempo w profilu; trim już skraca kwestie |
| brak kredytów nierozpoznany | inny status niż 402 | mapowanie z K2; do tego czasu błąd przejściowy → circuit po retry |
| migracja przy działającym rezydencie | rezydent nadpisuje `settings.json` | prośba o zamknięcie przed skryptem |
| `playwright` a Python 3.14, CI, `mypy --platform linux` | błędy instalacji lub typów | stop (§8) |
| trim brzegów zmienia odbiór Dallina | K3 na `elevenbytes` | D1 |
| sprzątanie konta nie dojdzie do skutku (np. zerwana sesja) | ostrzeżenie i komunikat z §7.10 | ponowienie przy następnej próbie; ręczne usunięcie według komunikatu |

## 13. Wycofanie

- Silnik: przełączenie na `elevenbytes` w Ustawieniach (bez kodu). Usunięcie silnika: revert commitów silnika i
  integracji (łączenie kwestii znika razem z `is_document_engine`); trim i głośność są niezależne od silnika.
- Głośność: revert commita E3 wymaga odwrotnego skryptu migracji `settings.json`.
- Profil Chrome: usunięcie `config/elevenreader/`.

## 14. Definition of Done

- [ ] Wymagany rezultat działa na prawdziwym odcinku obydwoma głosami i na `elevenbytes`.
- [ ] Bramki S1 zielone na końcowym commicie; test zgodności cięcia zielony; K1, K2, K3 zamknięte.
- [ ] Zero legacy: `narrator_mix_base_gain_db`, `_neutral_wav`, `ScheduledSynthesis.clip` nie istnieją.
- [ ] Skrypty z `scripts/tmp/` uruchomione, sprawdzone i usunięte.
- [ ] Review krzyżowe bez findingów krytycznych i poważnych; skan sekretów czysty.
- [ ] Outcome z dowodami, odchyleniami i stanem gałęzi.

## 15. Kontrakt wyniku etapu

```text
status: ACCEPTED | PENDING HUMAN | PARTIAL | BLOCKED | REPLAN REQUIRED
zmienione pliki i commit
komendy dowodu z wynikiem (liczby testów, exit code)
czego nie uruchomiono i dlaczego
odchylenia lokalne i materialne odkrycia
następny etap, który odblokowano
```

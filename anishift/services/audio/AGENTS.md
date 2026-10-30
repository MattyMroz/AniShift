# services/audio

Samodzielna domena montażu klipów głosu na osi czasu oraz renderowania finalnego
sidecara audio przez FFmpeg.

## Granica

- Audio przyjmuje neutralne `AudioRenderRequest`/`TimedAudioClip`; nie zna ASS/SRT,
  klasyfikacji napisów ani providerów TTS.
- `AudioService` posiada normalizację klipów, timeline, mapowanie kanałów, miks,
  codec produktu, resume i własność finalnego sidecara.
- Pipeline dostarcza timing, source audio i katalog tymczasowy; TTS dostarcza
  zwalidowane klipy.

## Twarde reguły

- `AudioService` rozwiązuje FFmpeg i FFprobe już w konstruktorze. Brak binarek ma
  pozostać typed `AudioConfigError` z sugestią `anishift setup`. `service.py`
- Polityka v1 to wyłącznie `serialize`, mono PCM S16LE. Nowa polityka timeline
  wymaga osobnej implementacji i fingerprint version bump. `config.py`,
  `fingerprint.py`
- `paragraph_pauses` rozdziela kolejne klipy stałą ciszą `_PARAGRAPH_GAP_MS`
  (jedyny literał tej wartości): N fragmentów dostaje N-1 przerw, bez ciszy na
  początku i na końcu. Żądanie z własnymi czasami nie dostaje ani milisekundy
  więcej. Flaga wchodzi do `narration_fingerprint`, więc gapless manifest nigdy nie
  jest trafieniem resume. `timeline.py`, `fingerprint.py`
- Każdy klip każdego silnika przechodzi przez FFmpeg i po `atempo` traci ciszę na
  brzegach: zostaje zakres od pierwszej do ostatniej ramki 10 ms powyżej
  `EDGE_TRIM_DBFS` plus `EDGE_TRIM_MARGIN_MS` z obu stron; klip bez takiej ramki
  zostaje cały. Nie ma ścieżki „neutralny WAV bez przetwarzania”: wynikiem
  normalizacji jest zawsze surowy PCM. Zmiana progu albo marginesu wchodzi do
  `normalization_fingerprint` (sekcja `edge_trim`). `normalize.py`, `levels.py`
- `levels.py` jest jedynym źródłem poziomów RMS w ramkach `FRAME_MS` (trim i cięcie
  nagrania); obliczenia przez stdlib (`array`, `math.sumprod`), bez numpy. `levels.py`
- Cięcie nagrania dokumentu na kwestie to czyste funkcje bez plików i FFmpeg: czasy
  ramek idą na oś serwera (`server_frame_times`, długość ramki MP3 z pierwszego
  nagłówka), a `cut_points` daje jedną `CutDecision` na granicę. Granica bez
  dość długiej ciszy nie scala klipów: tnie w kotwicy ograniczonej do okna i jest
  `uncertain`. Stałe są 1:1 z prototypu i przechodzą test zgodności na nagraniach
  z `quality_dir()`; zmiana progu lub okna wymaga ponownego testu. `segmentation.py`
- Brak klipów spoken zwraca `skipped_no_spoken`; nie twórz pustego narratora ani
  kopii oryginalnego audio. `service.py`
- `scope_id` jest jednym bezpiecznym segmentem ścieżki i nie może być nazwą
  urządzenia Windows. `service.py`
- Nie polegaj na implicit channel remap FFmpeg. Nieznany layout jest błędem;
  MP3 jawnie redukuje surround do stereo, a E-AC-3 redukuje 7.1 do 5.1(side).
  `channels.py`
- Narrator stereo trafia do obu kanałów z równą mocą; dla surround trafia tylko
  do kanału centralnego. `channels.py`
- Gain narratora jest mierzony, nie stały: przy miksie z oryginałem `AudioService`
  mierzy `ebur128` całego `narrator.wav` i oryginału (przed `original_gain_db`) i
  ustawia gain `source_I + narrator_over_source_lu + voice_mix_offset_db − narrator_I`.
  Trafienie resume nie mierzy; wynik pomiaru nie wchodzi do fingerprintu, bo zależy
  tylko od już hashowanych plików. `service.py`, `probe.py`
- Pomiar bez mierzalnej głośności (`-inf`, brak `Summary:` albo wartość na bramce
  bezwzględnej −70 LUFS, czyli cisza lub sygnał krótszy niż 400 ms) jest
  `AudioDecodeError`, nigdy cichym gainem z liczby −70. Fixture testu miksu z
  oryginałem musi więc być słyszalnym sygnałem dłuższym niż 400 ms. `probe.py`
- Miks z oryginałem kończy `MIX_LIMITER` (−1 dBFS, `level=0`, `latency=1`), jedyne
  źródło tej wartości także dla `mix_fingerprint`. Narrator-only pozostaje bez gainu
  i bez limitera. `output.py`, `fingerprint.py`
- Finalny miks używa `duration=longest`; oczekiwana długość to maksimum narratora
  i źródła. Nie skracaj wyniku do długości wideo. `output.py`
- Finalny path zastępuje rozszerzenie źródła rozszerzeniem codeca; AAC używa
  `.m4a`, Opus używa `.opus`. `output.py`

## Resume i zapis

- `write_timeline` zapisuje bezpośrednio do wskazanego pliku. Atomiczność należy
  do `AudioService`, który przekazuje ścieżkę tymczasową. `timeline.py`,
  `service.py`
- Nowy sidecar jest walidowany pod nazwą tymczasową, a następnie atomowo zastępuje
  istniejący plik docelowy niezależnie od wcześniejszej własności. `service.py`
- Uszkodzony manifest jest przenoszony do `manifest.corrupt.*.json`; nowszy
  schema version jest błędem, nie kandydatem do kwarantanny. `resume.py`
- Blokady manifestu są tylko process-local. Nie zakładaj bezpieczeństwa dwóch
  równoległych procesów AniShift dla tego samego scope. `resume.py`
- Resume narratora nie przelicza timeline, więc placements pochodzą z manifestu
  (`commit_narration` zapisuje je razem z fingerprintem narratora). `AudioRenderResult.placements`
  jest puste tylko dla `skipped_no_spoken`. `service.py`, `resume.py`
- Zapisane placements muszą opisywać DOKŁADNIE klipy swojego renderu: powtórzony
  `request_id` to uszkodzony manifest (kwarantanna), a zbiór `request_id` różny od
  `clip_ids` żądania oznacza brak trafienia i przeliczenie od nowa — nigdy podstawienia
  cudzej osi czasu. `resume.py`, `service.py`

## Subprocessy i callbacki

- Subprocessy są pollowane, a cancel/timeout wykonuje `terminate`, potem `kill`
  po grace period. Nie zastępuj tego blokującym `subprocess.run`. `commands.py`
- Observer postępu nie posiada wykonania: jego wyjątek jest ignorowany.
  `service.py`

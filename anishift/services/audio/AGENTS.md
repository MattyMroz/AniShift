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
- Brak klipów spoken zwraca `skipped_no_spoken`; nie twórz pustego narratora ani
  kopii oryginalnego audio. `service.py`
- `scope_id` jest jednym bezpiecznym segmentem ścieżki i nie może być nazwą
  urządzenia Windows. `service.py`
- Nie polegaj na implicit channel remap FFmpeg. Nieznany layout jest błędem;
  MP3 jawnie redukuje surround do stereo, a E-AC-3 redukuje 7.1 do 5.1(side).
  `channels.py`
- Narrator stereo trafia do obu kanałów z równą mocą; dla surround trafia tylko
  do kanału centralnego. `channels.py`
- `narrator_mix_base_gain_db + voice_mix_offset_db` obowiązuje tylko podczas
  miksowania z oryginalnym audio. Narrator-only pozostaje bez gainu. `output.py`
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
- Resume narratora może zwrócić `plan=None`; nie zakładaj, że historyczne
  placements są odtwarzane z manifestu. `service.py`

## Subprocessy i callbacki

- Subprocessy są pollowane, a cancel/timeout wykonuje `terminate`, potem `kill`
  po grace period. Nie zastępuj tego blokującym `subprocess.run`. `commands.py`
- Observer postępu nie posiada wykonania: jego wyjątek jest ignorowany.
  `service.py`

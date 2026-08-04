# services/composition

Samodzielna domena składania: bierze źródłowy kontener i gotowe artefakty, oddaje
jeden zweryfikowany plik wynikowy.

## Granica

- Composition przyjmuje `CompositionPlan` ze ścieżkami plików i decyzją, co dołożyć.
- NIE zna ASS/SRT jako formatu, `pysubs2`, `SubtitleSplit`, `FileTranslation`
  ani `SpeechBatch`.
- Decyzję „co dołożyć" podejmuje `pipeline/composition_runtime.py`; composition
  odpowiada wyłącznie za „jak to złożyć".

## Zakazane zależności

- `pysubs2`
- `anishift.pipeline`
- `anishift.services.subtitles`
- `anishift.services.translation`
- `anishift.services.tts`

## Twarde reguły

- Kod wyjścia i stderr sprawdzane ZAWSZE. mkvmerge `1` to sukces z ostrzeżeniem,
  `2` to błąd. `commands.py`
- Nic nie jest kasowane w tej domenie poza własnym plikiem częściowym. Sprzątanie
  `tmp/` należy do pipeline. `service.py`
- Źródłowy plik nie jest nigdy przenoszony ani przemianowywany. Zapis idzie do
  pliku tymczasowego i dopiero po walidacji zastępuje cel. `service.py`
- Brak materiału zwraca `SKIPPED_NOTHING_TO_ADD`, nigdy pustą komendę. `service.py`
- Apostrof w ścieżce łamie filtr napisów FFmpeg niezależnie od escapowania —
  napisy do wypalania ZAWSZE przechodzą przez `filter_safe_copy`. `paths.py`
- mkvmerge nie potrafi pisać do pliku, który czyta. `commands.py`
- Wypalanie zawsze przekodowuje wideo; `-c:v copy` z filtrem napisów nie istnieje.
- Observer postępu nie posiada wykonania: jego wyjątek jest ignorowany. `service.py`

## Konwencje

- mkvmerge v100: `--default-track-flag` i `--forced-display-flag`; stare
  `--default-track`/`--forced-track` NIE istnieją. `commands.py`
- Bez `--track-order`. mkvmerge układa ścieżki w kolejności plików, więc dołożone
  lądują za całym źródłem. Wymienienie tylko dołożonych przesunęłoby oryginalne
  audio i napisy ZA nie. `commands.py`
- Decyzja `-c:a copy` dotyczy pliku faktycznie mapowanego do wyniku (sidecar
  lektora, gdy istnieje), nie pierwszej ścieżki źródła. `service.py`
- Walidacja merge sprawdza NAZWY dołożonych ścieżek. Liczenie polskich ścieżek
  przepuszcza merge, który nic nie dołożył do już polskiego źródła. `probe.py`
- Oba potoki procesu drenowane w wątkach: cichy proces musi dać się anulować i
  ubić po timeoucie, a duży stderr nie może zakleszczyć runnera. `commands.py`
- Postęp merge z `--gui-mode` (`#GUI#progress N%`), postęp renderu z
  `-progress pipe:1 -nostats` (`out_time_us`). `commands.py`
- Filtr `ass=` dla ASS (pełna wierność stylów), `subtitles=` tylko dla SRT.
- MP4 nie przyjmuje ASS ani załączników; stylowane napisy istnieją tam wyłącznie
  jako wypalone w obrazie.
- Rozdziały źródła przechodzą do MP4 same, jako ścieżka `bin_data`/`text`
  z handlerem `SubtitleHandler` — to rozdziały QuickTime, nie zabłąkane napisy.

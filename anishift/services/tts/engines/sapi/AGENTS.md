# services/tts/engines/sapi

Lokalny adapter Windows SAPI przez trwały, architekturowo właściwy proces
PowerShell i wersjonowany protokół JSON Lines.

## Bezpieczeństwo uruchomienia

- Nie uruchamiaj live probe bez jawnej zgody użytkownika. Probe syntetyzuje
  `Test.` i głos IVONA może pokazać modal wygasłej licencji. Pasywna enumeracja
  głosów nie mówi.
- `sapi_worker.ps1` jest package assetem. Każdy wheel smoke musi potwierdzić
  `anishift/services/tts/engines/sapi/sapi_worker.ps1`.
- Destination musi już istnieć jako pusty, zwykły `.clip-*.wav.tmp` w katalogu
  `clips`, bez symlinków/junctions. Python i PowerShell niezależnie walidują tę
  własność. `service.py`, `sapi_worker.ps1`

## Profile i architektura

- `max_concurrency` musi wynosić dokładnie `1`; worker i COM są sekwencyjne.
  `config.py`
- Resolver przyjmuje wyłącznie wbudowane profile, pełne nazwy i identyfikatory
  `nazwa@x86|x64`. Sama enumeracja obcego głosu nie czyni go wybieralnym.
  `config.py`
- Host nie pochodzi z `PATH`: x64 używa `System32`, x86 używa `SysWOW64` pod
  `WINDIR`. Głosy enumeruj osobno dla obu hostów. `config.py`, `service.py`
- Zosia używa WPM mapowanego na skalę SAPI -10..10 i głośności ułamkowej ×100;
  Agnieszka używa bezpośrednich skal SAPI. `config.py`
- Rate/volume muszą być liczbami, ale nie `bool`; nie koercuj tekstu.
  `config.py`
- Voice/rate/volume są ustawiane raz przed pętlą workera. Zmiana profilu wymaga
  nowego procesu. `sapi_worker.ps1`

## Worker i protokół

- Protokół JSON Lines ma limit 256 KiB i własną wersję po obu stronach. Zmieniaj
  wersję równocześnie w Pythonie i PowerShellu. `protocol.py`, `sapi_worker.ps1`
- Jeden worker jest chroniony `asyncio.Lock`. Cancel, timeout, pipe failure albo
  błędna odpowiedź musi wyrzucić proces, aby spóźnione stdout nie trafiło do
  następnego requestu. `worker.py`
- Sukces musi zgadzać się po `request_id` i dokładnym output path. `worker.py`
- stdout jest wyłącznie protokołem; pasywny probe akceptuje jedną niepustą linię.
  stderr jest stale drenowany i ignorowany. `worker.py`
- Close wysyła EOF, czeka do `shutdown_deadline_s`, potem hard-kill. Zachowaj tę
  kolejność. `worker.py`
- Zwykła synteza sprawdza RIFF/WAVE i rozmiar; pełna walidacja PCM należy do live
  probe oraz dalszej warstwy audio. `service.py`

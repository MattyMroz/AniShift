# services/tts/engines/elevenlabs

Oficjalny adapter ElevenLabs. Synteza może zużywać płatny limit.

## Bezpieczeństwo kosztu

- Nie wykonuj live synthesis ani testu sieciowego bez jawnej zgody użytkownika.
- SDK jest importowane i inicjalizowane leniwie przy pierwszej operacji runtime;
  samo utworzenie backendu nie może ładować SDK. `api_backend.py`
- Klucz może być pusty podczas composition. Brak ma być widoczny przez
  availability albo typed auth error, nie przez ukrycie providera. `config.py`
- Automatyczne retry SDK jest wyłączone (`max_retries=0`). Każda płatna próba
  należy do wspólnego retry/circuit TTS. `api_backend.py`
- Cancel jest sprawdzany przed płatnym requestem i dopiero po całym streamie; nie
  zakładaj możliwości przerwania requestu w locie. `service.py`

## Konfiguracja i request

- Native rate/volume/pitch są zakazane. Ustawienia ElevenLabs przechodzą tylko
  przez allowlistowane `engine_options`. `config.py`, `options.py`
- `speed` jest opcją providera w zakresie `0.7–1.2`, ale capability
  `supports_native_rate` pozostaje false. `options.py`, `service.py`
- Liczby muszą być rzeczywistym `int`/`float`, nie tekstem ani `bool`.
  `options.py`
- Każdy request musi dokładnie powtarzać model, voice ID i rozstrzygnięte opcje
  silnika. Nie dodawaj per-request override. `service.py`
- Model i voice ID podlegają ograniczonej gramatyce `[A-Za-z0-9._-]`.
  `config.py`
- Limit to 10 000 znaków bez osobnego limitu bajtów. `service.py`

## Głosy i wynik

- Dla silnika gotowego do probe `availability(live=True)` wymusza pobranie listy
  głosów. Stan closed/missing SDK/missing key wraca bez sieci. Normalny cache jest
  ważny 300 s; dyskowa tożsamość konta to SHA-256 klucza, bez zapisu klucza.
  `service.py`
- Nieprawidłowy lub obcy cache głosów jest cicho ignorowany, bez kwarantanny.
  `service.py`
- Audio jest składane w pamięci, walidowane tylko po magic bytes i zapisywane
  bezpośrednio do prywatnego destination TTS. Pełne decode należy do dalszej
  warstwy. `api_backend.py`, `service.py`
- Bezpieczny błąd API nie może ujawniać response body ani tekstu wyjątku SDK.
  `api_backend.py`

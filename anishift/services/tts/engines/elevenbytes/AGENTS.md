# services/tts/engines/elevenbytes

Adapter publicznego proxy ElevenBytes; różnice względem wspólnej domeny TTS.

## Kontrakt providera

- Adapter nie przyjmuje klucza użytkownika. Request używa publicznego tokenu
  klienta webowego z `constants.py`; nie przenoś go do `.env`.
- Transport HTTP ma `retries=0`. Retry, circuit i limity należą wyłącznie do
  wspólnego `TtsService`. `api_backend.py`
- `run6` odrzuca wszystkie engine options. Eksperymentalny `run7` przyjmuje
  wyłącznie cztery jawne opcje z `config.py`.
- Opcje numeryczne `run7` muszą być rzeczywistym `int`/`float`, ale nie `bool`;
  `use_speaker_boost` musi być rzeczywistym `bool`. Nie koercuj tekstu.
- Alias `dallin` jest case-insensitive; każdy inny niepusty identyfikator jest
  traktowany jako custom provider voice ID. `config.py`
- Opcje requestu mogą być puste albo dokładnie równe konfiguracji silnika. Nie
  wolno nadpisywać profilu per request. `service.py`

## Pułapki

- `availability(live=False)` jest tylko stanem cache. Dopiero `live=True`
  wykonuje probe sieci. `service.py`
- Probe obniża dostępność tylko dla 401/403/429 oraz 5xx; inne 4xx nie oznaczają
  globalnej awarii proxy. `api_backend.py`
- Cancel nie przerywa aktywnego requestu HTTP; jest sprawdzany przed i po nim.
  `service.py`
- Odpowiedź musi wyglądać jak MP3. Brak `Content-Type` jest dozwolony, ale
  nieznany niepusty typ i brak ramki MPEG w początkowym oknie są błędem.
  `api_backend.py`
- Engine zapisuje bajty bezpośrednio do przekazanej ścieżki. Przekazuj wyłącznie
  prywatny destination przygotowany przez warstwę TTS. `service.py`
- Ustawienia `run7` są częścią `SynthesisProfile`; ich zmiana musi unieważniać
  resume fingerprint. `service.py`

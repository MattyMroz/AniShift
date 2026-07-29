# services/tts/engines/edge

Adapter Edge TTS z automatycznym patchem jakości dla przypiętej wersji pakietu.

## Patch zależności

- Obsługiwana jest dokładnie wersja `edge-tts` z `SUPPORTED_EDGE_TTS_VERSION`.
  Inna wersja daje `UNSUPPORTED_VERSION`; nie próbuj patchować jej heurystycznie.
- Konstruktor najpierw wykonuje patch, a backend importujący `edge_tts` powstaje
  dopiero dla wyniku ready. `service.py`
- Patch zmienia równocześnie format w `communicate.py` i metadane bitrate w
  `constants.py`. Każdy marker musi wystąpić dokładnie raz w starej albo nowej
  postaci. `patch.py`
- Zapis patcha jest staged + fsync + replace. Błąd drugiego replace przywraca
  pierwszy plik; zachowaj rollback dwóch plików. `patch.py`

## Kontrakt providera

- `engine_options` są zakazane. Rate, volume i pitch przechodzą wyłącznie przez
  dedykowane native fields jako podpisane stringi providera; liczby odrzucaj.
  `config.py`
- Limit wejścia to 4096 bajtów UTF-8, nie znaków. `service.py`
- Jeśli request ustawia którekolwiek native field, cała trójka rate/volume/pitch
  musi być identyczna z profilem silnika. `service.py`
- Transport wykonuje jedną próbę. Stream ignoruje nie-audio events i składa MP3
  w pamięci; retry należy do wspólnego `TtsService`. `api_backend.py`
- Cancel nie przerywa aktywnego streamu; jest sprawdzany przed requestem i przed
  zapisem wyniku. `service.py`
- `availability(live=False)` sprawdza tylko lokalny patch. Dopiero `live=True`
  odpytuje zdalną listę głosów. `service.py`
- HTTP 401/403 oznacza niedostępność usługi, nie brak klucza użytkownika.
  `api_backend.py`

# Domena LLM

Synchroniczna, provider-neutral domena completion. `LlmService` jest właścicielem
cyklu życia klienta i jedynego retry.

## Twarde reguły

- Retry dotyczy wyłącznie `TransientError` i pozostaje w `_retry.py`; retry SDK
  musi być wyłączony.
- Zachowuj rozróżnienie przejściowego rate limit od trwałego
  quota/payment/auth/model/config.
- Providerów i ich SDK ładuj leniwie. Publiczne `__init__.py` oraz registry nie
  mogą eager-importować implementacji providerów.
- Providery zgodne z Chat Completions buduj na wspólnym
  `OpenAiCompatibleTransport`, bez kopiowania transportu.
- Nigdy nie ujawniaj `LlmConfig.api_key`, `fallback_api_key` ani `fallback_origin`
  w repr, błędach, logach ani rekordach.
- `FilePart` waliduje MIME i dane; `LlmMessage` wymaga tekstu i dopuszcza pliki
  tylko w roli `USER`. Adapter sprawdza możliwości providera/modelu przed wysłaniem.
- Instancja providera należy do jednego synchronicznego workera; współbieżność
  organizuje pipeline przez osobne klienty i wspólny observer.
- Pusta albo zablokowana przez safety odpowiedź jest błędem, nigdy sukcesem.
- Sukces providera zakończony po ustawieniu `cancel` jest odrzucany jako
  `LlmCancelledError`; nie może przejść do zapisu pliku.

## Mapa

- `service.py`, `_retry.py` — facade, lifecycle i retry.
- `config.py`, `types.py`, `protocols.py`, `errors.py` — publiczne kontrakty.
- `engines/anthropic/`, `engines/gemini/` — natywne adaptery SDK.
- `engines/{openai,deepseek,openrouter,openai_compatible}/` — wrappery wspólnego
  transportu OpenAI-compatible.
- `engines/*/constants.py` — lekkie sugestie modeli dla UI, bez importu SDK;
  `openai_compatible` nie ma tego modułu, a rejestr zwraca pustą listę sugestii.
- `engines/palantir/constants.py` — źródło listy modeli, możliwości, opcji i wariantów;
  `anishift/config/model_catalog.py` tylko przekłada je na DTO aplikacji.
- `engines/palantir/config.py`, `service.py` — rozwiązanie aliasu/wariantu i polityka
  parametrów generowania; `protocols.py`, `normalize.py` — serializacja i odpowiedzi.
- `engines/palantir/accounts.py`, `http.py` — konta/cooldown i wspólny failover HTTP.

## Pułapki

- Natywny OpenAI używa `max_completion_tokens`; pozostałe endpointy kompatybilne
  `max_tokens`.
- Palantir OpenAI i xAI współdzielą Responses, nie Chat Completions. Wynik streamu Responses
  pochodzi ze zdarzenia terminalnego; delty służą tylko raportowaniu postępu.
- `PalantirService._generation_options` pomija `temperature` i `top_p` przy
  aktywnym myśleniu OpenAI/xAI lub Claude. Wariant zastępuje kompletne poddrzewo opcji.
- Failover Palantira działa tylko po HTTP 429/≥500, przed odczytem body; błędy sieci,
  body i generowania nie przełączają kont. Retry całej próby pozostaje w `_retry.py`.
- Cooldown Palantira trwa 60 s, jest wspólny procesowo i kluczowany originem.
  Snapshot kont powstaje raz na próbę; lock nigdy nie obejmuje HTTP.
- Anthropic wymaga `max_tokens` i ma lokalny bezpieczny default.
- `openai_compatible` wymaga base URL, ale klucz może być pusty.
- Zwykłe 429 to przejściowy rate limit; fatal quota wymaga strukturalnego sygnału
  wyczerpania limitu.

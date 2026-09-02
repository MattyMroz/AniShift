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
- Nigdy nie ujawniaj `LlmConfig.api_key` w repr, błędach, logach ani rekordach.
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
- `engines/palantir/` — proxy Foundry nad czterema protokołami wire
  (`wire_protocol.py`), z własnym auth i routingiem.
- `engines/*/constants.py` — lekkie sugestie modeli dla UI, bez importu SDK.

## Pułapki

- OpenAI używa `max_completion_tokens`; pozostałe endpointy kompatybilne
  `max_tokens`.
- Anthropic wymaga `max_tokens` i ma lokalny bezpieczny default.
- `openai_compatible` wymaga base URL, ale klucz może być pusty.
- Zwykłe 429 to przejściowy rate limit; fatal quota wymaga strukturalnego sygnału
  wyczerpania limitu.
- `StreamingLlmEngine` jest opcjonalny i implementuje go tylko palantir;
  `LlmService.complete` sam wybiera strumień przez `isinstance`. Strumieniują
  wyłącznie `GOOGLE_GENERATE` i `OPENAI_CHAT` — pozostałe protokoły cicho
  spadają na zwykłe completion, więc `on_text` nigdy nie dostaje wywołania i
  wołający nie może zakładać, że postęp przyjdzie.

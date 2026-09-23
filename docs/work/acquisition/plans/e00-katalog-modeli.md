---
kind: plan
status: zaakceptowany
version: 4
baseline: 4b5e3f1
branch: work/acquisition/00-model-catalog
created: 2026-09-23
---

# Plan E00: rozbudowa serwisu LLM — listy modeli, multimodalność, Palantir jak OpenCode

## Cel

Rozbudować istniejący, samowystarczalny serwis `anishift/services/llm/`:

1. **Każdy silnik ma własną, aktualną listę modeli** w swoim katalogu. Palantir dostaje ją jako jedyny, który jej dziś nie ma; pozostałe listy są odświeżone według oficjalnych źródeł dostawców.
2. **Multimodalność w całym serwisie.** Wiadomość użytkownika może zawierać obraz, PDF, audio i wideo. Każdy silnik wysyła je w formie swojego API albo odmawia przed wysłaniem.
3. **Palantir jak OpenCode:**
   - 20 modeli z typami plików i poziomami myślenia;
   - OpenAI przez `/responses`;
   - wybór poziomu myślenia;
   - mechanizm drugiego konta przy limicie.

## Granica zmiany

| Obszar | Zmiana |
| --- | --- |
| `anishift/services/llm/**` | Cała praca E00 |
| `anishift/config/model_catalog.py` | Cienkie mapowanie listy z `services/llm/engines/palantir/constants.py` na istniejące typy (`ModelCatalog`, `ModelEntry`, `ProviderEntry`, `CatalogDefaults`); bez parsowania pliku. Konsumenci (`application/*`, `cli/*`) bez zmian. |
| `anishift/cli/interactive/settings.py:1943` | **Jedna linia (wyjątek do akceptacji):** klucz etykiety grupy `"palantir:openai_chat"` → `"palantir:openai_responses"`. Bez tego nagłówek grupy OpenAI w wyborze modelu zmieni się na `PALANTIR:OPENAI_RESPONSES`. |
| `config/anishift.models.example.jsonc`, lokalny `config/anishift.models.jsonc`, wpis `config/anishift.models.jsonc` w `.gitignore` | Usunięte — lista żyje w serwisie |
| `pyproject.toml` / `uv.lock` | `uv remove json5` (jedynym użytkownikiem jest parser katalogu) |
| `README.md:176`, `config/README.md` | Zdania o pliku katalogu zastąpione informacją, że lista modeli Palantir jest w serwisie |
| `anishift/config/AGENTS.md` | Reguła o pliku katalogu zastąpiona informacją, że `model_catalog.py` mapuje listę z serwisu (faza 5) |
| Testy poza serwisem, które używają usuwanych symboli | `tests/config/test_model_catalog.py`, `tests/config/test_model_settings.py`, `tests/application/test_service.py`, `tests/cli/test_interactive_settings_models.py`, `tests/test_paths.py` — fixture katalogu budowane wprost z `ModelCatalog(...)` zamiast parsowania JSONC |
| Test poza serwisem czytający części wiadomości | `tests/application/test_runtime_config.py:139-140` (`part.text` na `LlmContentPart`) — faza 1: jawne sprawdzenie, że część jest `TextPart`, bez filtrowania; treść i kolejność promptów nadal sprawdzane |
| Ustawienia, UI (poza linią wyżej), tłumaczenie, runtime, rezydent, `config/settings.py` | **Bez zmian.** Wybór poziomu myślenia i drugiego konta w panelu oraz odczyt drugiego tokena z `.env` to osobny krok po E00; serwis ma je gotowe w `LlmConfig`. |

## Stan aktualny (kod na `4b5e3f1`)

- **Rejestr** (`services/llm/engines/__init__.py:40-77`): wpis = moduł, klasa, moduł sugestii (`constants.py`, `SUGGESTED_MODEL_IDS`); `palantir` i `openai_compatible` mają `None`. Aplikacja czyta sugestie przez `suggested_model_ids` (`application/service.py:671`); sugestie są niewiążące (dopuszczone własne ID).
- **Listy modeli są nieaktualne:**
  - `openai/constants.py`: `gpt-5.4*`;
  - `gemini/constants.py`: `gemini-3.5-flash-lite`, `gemini-3.5-flash`, `gemini-3.6-flash`;
  - `anthropic/constants.py`: `claude-sonnet-5`, `claude-haiku-4-5`, `claude-opus-5`.
- **Treść wiadomości to tylko tekst** — `types.py:46` (`LlmContentPart = TextPart`). Inne części odrzucają:
  - `anthropic/service.py:241-255`;
  - `gemini/service.py:275-289`;
  - `_openai_compatible.py:269-285`;
  - `palantir/protocols.py:280-297`.
- **Palantir:**
  - lista w `config/anishift.models.jsonc` (19 modeli, bez `gpt-6-astra`, bez typów plików i wariantów), parsowana przez `config/model_catalog.py` (`json5`);
  - OpenAI przez `/chat/completions`;
  - strumień tylko dla OpenAI Chat i Google (`palantir/service.py:43-53`), xAI i Anthropic bez strumienia;
  - jedno konto: `LlmConfig.base_url` = pełna trasa providera sklejona w `application/runtime.py:497-511`, `LlmConfig.api_key` = token;
  - odczyt Google bez strumienia wkleja części `thought` (`palantir/normalize.py:412-421`).
- **Zależności:** aplikacja zależy od serwisu (`config/settings.py` → `palantir_token`, `config/model_catalog.py` → `wire_protocol`, `runtime.py` → `palantir_model_config`), nigdy odwrotnie. Plan zachowuje ten kierunek.
- **Próby na żywo** (konto 1): [../outcomes/e00.md](../outcomes/e00.md), 214 prób, 20 modeli. Wszystkie formy żądań Palantir z tego planu przechodzą. Nie wystąpiły zdarzenia `error` / `response.failed`, więc ich kształt pochodzi z dokumentacji. Trzy odrzucane warianty są usunięte ze skilla OpenCode (`agents@a2174c1`).

## Docelowa struktura

```text
anishift/services/llm/
├── __init__.py                   # MODIFY: eksport FilePart, Modality
├── types.py                      # MODIFY: FilePart, Modality, LlmContentPart = TextPart | FilePart, reguła ról
├── config.py                     # MODIFY: reasoning_variant, fallback_origin, fallback_api_key (repr=False)
├── wire_protocol.py              # MODIFY: OPENAI_CHAT -> OPENAI_RESPONSES
├── AGENTS.md                     # MODIFY
└── engines/
    ├── __init__.py               # MODIFY: palantir rejestruje constants
    ├── _openai_compatible.py     # MODIFY: image_url i file w Chat Completions; file_modalities per provider
    ├── anthropic/constants.py    # MODIFY: lista wg dokumentacji Anthropic
    ├── anthropic/service.py      # MODIFY: bloki image/document
    ├── gemini/constants.py       # MODIFY: lista wg dokumentacji Google
    ├── gemini/service.py         # MODIFY: types.Part.from_bytes(data=..., mime_type=...)
    ├── openai/constants.py       # MODIFY: lista wg dokumentacji OpenAI
    ├── openai/service.py         # MODIFY: file_modalities = {image, pdf}
    ├── openrouter/service.py     # MODIFY: file_modalities = {image, pdf}
    ├── deepseek/service.py       # MODIFY: file_modalities = {} (odmowa)
    ├── openai_compatible/service.py  # MODIFY: file_modalities = {image}
    └── palantir/
        ├── constants.py          # NEW: providery i 20 modeli
        ├── accounts.py           # NEW: kolejność kont i cooldown
        ├── config.py             # MODIFY: modalności, request_options, konta
        ├── protocols.py          # MODIFY: pliki, opcje, Responses (OpenAI i xAI)
        ├── normalize.py          # MODIFY: wspólny odczyt Responses, błędy generowania, filtr thought
        ├── http.py               # MODIFY: wysyłka przez konta, zdarzenia błędów strumienia
        └── service.py            # MODIFY: strumień Responses, wybór konta
anishift/config/model_catalog.py  # MODIFY: mapowanie z palantir/constants.py
anishift/cli/interactive/settings.py  # MODIFY: 1 linia (klucz etykiety grupy)
config/anishift.models.example.jsonc  # DELETE
README.md, config/README.md       # MODIFY
tests/services/llm/…              # MODIFY/NEW
tests/config/…, tests/application/test_service.py, tests/cli/test_interactive_settings_models.py, tests/test_paths.py  # MODIFY
```

## Szczegóły

### 1. `FilePart` (`types.py`)

```text
Modality = Literal["text", "image", "pdf", "audio", "video"]
FilePart(media_type: str, data: bytes = field(repr=False), name: str = "")
  image/png | image/jpeg | image/webp -> image
  application/pdf                    -> pdf
  audio/*                            -> audio
  video/*                            -> video
  inny typ albo puste data           -> LlmRequestError
  modality: właściwość wyliczona z media_type
LlmContentPart = TextPart | FilePart
Reguła ról: FilePart tylko w wiadomości USER; w SYSTEM i ASSISTANT -> LlmRequestError przy tworzeniu LlmMessage
Każda wiadomość nadal wymaga co najmniej jednego TextPart (sam plik bez tekstu -> LlmRequestError), jak dziś
```

Reguła ról wynika z API: `system` przyjmuje tylko tekst w Anthropic, Chat Completions i Responses; `assistant` w Chat Completions nie przyjmuje plików.

### 2. Multimodalność w silnikach

| Silnik | Obraz | PDF | Audio / wideo | Typy przyjmowane |
| --- | --- | --- | --- | --- |
| `anthropic` (SDK) | `{"type":"image","source":{"type":"base64","media_type":…,"data":…}}` | `{"type":"document","source":{"type":"base64","media_type":"application/pdf","data":…}}` | odmowa | stała silnika `{image, pdf}` |
| `gemini` (SDK) | `types.Part.from_bytes(data=…, mime_type=…)` | jak obraz | jak obraz | stała silnika `{image, pdf, audio, video}` |
| `openai`, `openrouter` | `{"type":"image_url","image_url":{"url":"data:…;base64,…"}}` | `{"type":"file","file":{"filename":…,"file_data":"data:application/pdf;base64,…"}}` | odmowa | `OpenAiCompatibleProvider.file_modalities` = `{image, pdf}` |
| `openai_compatible` | jak wyżej | odmowa | odmowa | `{image}` |
| `deepseek` | odmowa | odmowa | odmowa | `{}` |
| `palantir` | pkt 4 | | | per model z `palantir/constants.py` |

- Wiadomość z samym tekstem: żądanie silników `anthropic`, `gemini`, `openai`, `openrouter`, `deepseek`, `openai_compatible` jest identyczne jak dziś, łącznie z separatorem `"\n"` między częściami tekstu w Chat Completions.
- Palantir zmienia obudowę żądania i opcje (pkt 4), ale zachowuje treść, kolejność części tekstu i dotychczasowe separatory. Dziś `_joined_text()` (`palantir/protocols.py:300-302`) skleja części przez `"\n"` dla OpenAI i xAI; Anthropic i Google dostają osobne bloki. Tłumaczenie wysyła osobne części: instrukcję, styl i dane (`translation/engines/llm/service.py:247-258`).
- Odmowa to `LlmRequestError` przed wywołaniem SDK/HTTP, z nazwą typu pliku i silnika.

### 3. Listy modeli

**Palantir — `palantir/constants.py` (nowy):**
- **providery:** id, protokół, ścieżka proxy (jak w dzisiejszym przykładzie JSONC). `foundry-openai` przechodzi na `openai_responses` w fazie 3, razem z transportem.
- **20 modeli:** alias (jak dziś, np. `foundry/gpt-5.5`), id modelu, etykieta, limity, typy plików, `reasoning`, opcje domyślne, warianty.
- **Wartości:** przepisane z `agents/skills/opencode/assets/opencode.jsonc@a2174c1`, w nazwach pól żądania:

| OpenCode | Pole żądania |
| --- | --- |
| `reasoningEffort` | `reasoning.effort` (OpenAI, xAI) |
| `store` | `store` (OpenAI, xAI) |
| `thinking` | `thinking` (Anthropic) |
| `effort` | `output_config.effort` (Anthropic) |
| `thinkingConfig` | `generationConfig.thinkingConfig` (Google) |

  Pomijane: `include`, `reasoningSummary` (rozmowa wieloturowa) i `toolStreaming` (narzędzia).
- **`SUGGESTED_MODEL_IDS`** = aliasy w kolejności listy; rejestr traktuje Palantira jak inne silniki.
- **Warunek samowystarczalności:** `palantir/constants.py` nie importuje niczego spoza `anishift/services/llm/` (ani `anishift.config`, ani `anishift.application`); kierunek zostaje: aplikacja → serwis. Test importu to sprawdza.
- **`CATALOG_DEFAULTS`:** `primary = foundry/gpt-5.6-sol`, `translation = foundry-google/gemini-3.5-flash-lite` (jak dziś).
- **Jak silnik znajduje model:** `PalantirService` szuka specyfikacji (typy plików, opcje, warianty, `reasoning`) po `LlmConfig.alias` w `palantir/constants.py`; alias spoza listy → `LlmConfigError`. Testy silnika przechodzą z aliasów testowych (`"foundry/main"`, `"test"`) na prawdziwe aliasy z listy.

**`config/model_catalog.py`:**
- `load_model_catalog()` mapuje stałe modułu na `ModelCatalog` (`issues = ()`, `schema_version` bez znaczenia, zostaje 1);
- usuwane: `parse_model_catalog`, `ensure_model_catalog_file`, `model_catalog_path`, `model_catalog_example_path`, stałe nazw plików, sprawdzanie sekretów w pliku;
- aliasy się nie zmieniają, więc zapisany wybór właściciela (`foundry-google/gemini-3.8-flash`) działa.

**Pozostałe silniki** — `SUGGESTED_MODEL_IDS` wg oficjalnej dokumentacji (stan 2026-09-23):

| Silnik | Lista | Źródło |
| --- | --- | --- |
| `openai` | `gpt-6-sol`, `gpt-6-luna`, `gpt-6-astra` | [developers.openai.com/api/docs/models](https://developers.openai.com/api/docs/models) |
| `anthropic` | `claude-opus-5-5`, `claude-sonnet-5`, `claude-haiku-4-5`, `claude-fable-5-1` | [platform.claude.com/…/models/overview](https://platform.claude.com/docs/en/about-claude/models/overview) |
| `gemini` | `gemini-3.8-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-pro-preview` | [ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models) |
| `deepseek`, `openrouter` | bez zmian (brak nowego źródła) | — |

Wyłączenie „modeli, których jeszcze nie ma” (Opus 5.5, GPT-6 Sol/Luna) dotyczy listy Palantir, bo nie ma ich w Foundry. U samych dostawców już są (dokumentacja wyżej), więc trafiają na listy silników natywnych (potwierdzone przez właściciela 2026-09-23: Foundry dodaje nowe modele z opóźnieniem; do listy Palantir dopisujemy je, gdy się tam pojawią).

### 4. Palantir

**Formy żądań** (potwierdzone w fazie 0):

| Protokół | Trasa | Tekst | Obraz | PDF | Audio / wideo |
| --- | --- | --- | --- | --- | --- |
| `openai_responses` | `/responses` | `input_text` | `input_image`, data URL | `input_file` (`filename`, `file_data`) | odmowa |
| `xai_responses` | `/responses` | jak OpenAI | jak OpenAI | odmowa | odmowa |
| `anthropic_messages` | `/messages` | `text` | `image` base64 | `document` base64 | odmowa |
| `google_generate` | `:generateContent` | `text` | `inlineData` | `inlineData` | `inlineData` |

- Wiadomość systemowa w Responses: rola `system`, treść jako zwykły tekst.
- Typ pliku spoza typów modelu jest odrzucany przed wysłaniem.

**Zmiana dla żądań tekstowych (świadoma, 1:1 z OpenCode):** każdy model dostaje opcje domyślne ze swojej listy:
- Gemini: `thinkingConfig` z `includeThoughts: true` i `thinkingBudget: -1`; myśli są odfiltrowane;
- Claude z `thinking` w specyfikacji modelu: `thinking: adaptive`; Opus 4.5 nie ma `thinking` (jak w OpenCode) i zachowuje temperaturę;
- OpenAI i xAI: `store: false`; OpenAI idzie przez `/responses`.

Tłumaczenie właściciela (dziś `foundry-google/gemini-3.8-flash`) potwierdza checkpoint w fazie 6.

**Poziom myślenia:**
- `LlmConfig.reasoning_variant`: `None` = opcje domyślne;
- nazwa spoza wariantów modelu → `LlmConfigError`.

**Temperatura i `top_p`** — polityka AniShift: nie są wysyłane, gdy model myśli:
- OpenAI i xAI z `reasoning`, chyba że wariant to `none`;
- Claude z `thinking`.

Faza 0: OpenAI z myśleniem i Claude z `thinking` temperaturę odrzucają; xAI ją przyjmuje, więc dla xAI to polityka, nie wymóg proxy.

**Limit odpowiedzi:** OpenAI i xAI dostają `max_output_tokens`; Anthropic i Google jak dziś.

**Strumień:**
- OpenAI `/responses` ze strumieniem: tekst z `response.output_text.delta`, odpowiedź z ostatniego zdarzenia `response.completed`, `response.incomplete` albo `response.failed`;
- `incomplete` z `incomplete_details.reason == "max_output_tokens"` daje `finish_reason = max_output_tokens`, więc tłumaczenie dzieli partię jak dziś (`translation/engines/llm/service.py:34`);
- Google strumieniuje jak dziś; xAI i Anthropic zostają bez strumienia.

**Błędy generowania** — jedno mapowanie dla trzech kształtów z dokumentacji OpenAI Responses:
- zdarzenie `{"type":"error","code":…,"message":…}`;
- zdarzenie `response.failed` z `response.error.code`;
- odpowiedź JSON ze `status: "failed"` i `error.code`.

| Kod | Status | Błąd |
| --- | --- | --- |
| `server_error` | 500 | przejściowy, ponawiany przez `_retry.py` |
| `rate_limit_exceeded` | 429 | przejściowy, ponawiany przez `_retry.py` |
| inny | 400 | fatalny |

Błąd generowania nie przełącza konta.

**Google:** części `thought` nie trafiają do tekstu, także bez strumienia.

**Usuwany kod Chat Completions w Palantirze:**
- `_build_openai_chat`, `_chat_completions_request`;
- `merge_openai_stream`, `openai_stream_delta`;
- `_extract_chat_completions`, `_chat_block_signal`;
- `_OPENAI_MAX_TOKENS_KEY`, `_COMPATIBLE_MAX_TOKENS_KEY`.

**Drugie konto (tylko mechanizm serwisu):**
- `LlmConfig.fallback_origin` (`repr=False`) i `fallback_api_key` (`repr=False`); `fallback_origin` walidowany jak `_require_base_url` (`palantir/config.py:113-121`: tylko `https`, bez query i fragmentu) oraz bez ścieżki — sam `https://host`;
- adres konta 2 = trasa konta 1 z podmienionym schematem i hostem, jak `withHost` w `foundry-rotate.js:45-49`;
- konto 1 zostaje w `base_url`/`api_key`, więc sprawdzanie dostępności w `LlmService` i w tłumaczeniu się nie zmienia;
- odczyt tokena 2 z `.env` i pole w panelu — po E00.

```text
konta = [konto 1, konto 2 jeśli fallback_origin i fallback_api_key]
cooldown 60 s na całe konto; stan wspólny w procesie, pod threading.Lock, z funkcją resetu dla testów
dla próby:
  pula = konta bez cooldownu; jeśli pusta -> wszystkie konta (jak foundry-rotate.js:120-123)
  każde konto z puli najwyżej raz:
    odpowiedź 429 albo >= 500 -> cooldown, następne konto
    inna odpowiedź -> zdejmij cooldown; zwróć albo rzuć
    błąd sieci, zła treść odpowiedzi 200, błąd generowania -> rzuć bez przełączania
  wszystkie zawiodły -> błąd ostatniej odpowiedzi idzie do _retry.py
```

**Pola Palantira w innych silnikach:** `reasoning_variant`, `fallback_origin` albo `fallback_api_key` ustawione dla silnika innego niż `palantir` → `LlmConfigError`, żeby nic nie było cicho ignorowane.

## Kolejność prac

- **Wykonawca:** subagent Claude Code `general-purpose` z modelem `opus`; przed kodem czyta skille `simple` i `coding` (`python.md`, `comments-docstrings.md`, `testing.md`).
- **Review:** `astra` (OpenCode, `foundry/gpt-6-astra`) i niezależny Claude Opus (świeży subagent, tylko odczyt).
- **Odstępstwo od `AGENTS.md`** (tam koduje `astra`, a sprawdza `opus5`) — decyzja właściciela z 2026-09-23 w rozmowie: „będzie twój [subagent] kodował, a potem astra to oceni”.
- **Po każdej fazie:** `ruff check`, `ruff format --check`, `mypy` (win32 i linux), `pytest`.
- **Commit:** na `work/acquisition/00-model-catalog`, bez śladów AI.

| Faza | Zakres | Commit |
| --- | --- | --- |
| 1 | `FilePart`/`Modality`, reguła ról; pliki w `anthropic`, `gemini`, `_openai_compatible` (+ `file_modalities` providerów); eksport; `tests/application/test_runtime_config.py:139-140` | `feat(llm): accept image, pdf, audio and video parts in every engine` |
| 2 | `palantir/constants.py` (20 modeli, `foundry-openai` jeszcze `openai_chat`), rejestr, `config/model_catalog.py`, usunięcie plików katalogu, `uv remove json5`, testy poza serwisem, README | `feat(llm): keep the palantir model list inside its engine` |
| 3 | Palantir: `openai_responses` (enum, lista, builder, reader, strumień), linia etykiety w `settings.py`, pliki, `reasoning_variant`, temperatura, błędy generowania, filtr `thought`, usunięcie kodu Chat Completions; testy spoza serwisu z `OPENAI_CHAT`/`openai_chat` (`tests/cli/test_interactive_settings_models.py:38`, `tests/config/test_model_settings.py:57-67, 394`) | `feat(llm): send files and reasoning variants through palantir responses` |
| 4 | Palantir: drugie konto; walidacja pól Palantira w innych silnikach | `feat(llm): fail over between two palantir accounts` |
| 5 | Listy `openai`, `anthropic`, `gemini`; `services/llm/AGENTS.md`, `config/AGENTS.md` | `feat(llm): refresh model suggestions from provider documentation` |
| 6 | Próby na żywo przez `LlmService`: każdy model Palantir, typ pliku i wariant na koncie 1; `probe_palantir_model` dla jednego modelu z każdej rodziny; konto 2 (token i adres podane wprost skryptowi), gdy właściciel da token. Review `astra` + Opus; tłumaczenie jednego odcinka przez właściciela; PR do `main` | — |

## Testy (bez sieci)

- **`FilePart`:** typy, odmowa pustych danych i nieznanego typu, plik w `SYSTEM`/`ASSISTANT` odrzucony, `repr` bez danych.
- **Każdy silnik:**
  - tekst identyczny jak dziś (regresja; dla Palantira zob. „Palantir, tekst”);
  - obraz, PDF, audio/wideo w formie z tabeli;
  - wiadomość mieszana tekst+plik;
  - odmowa niewspieranego typu przed wywołaniem SDK/HTTP.
- **Palantir, tekst:** treść, kolejność i separatory części tekstu jak dziś (przy nowej obudowie `/responses` i opcjach).
- **Palantir, lista:**
  - 20 modeli, rejestr, `suggested_model_ids("palantir")`;
  - `load_model_catalog()` daje dzisiejsze aliasy + `foundry/gpt-6-astra`;
  - wszystkie opcje i warianty mają znane pola.
- **Palantir, żądania:**
  - każdy protokół × tekst/obraz/PDF/audio/wideo;
  - wariant; nieznany wariant;
  - temperatura przy myśleniu i przy `none`.
- **Palantir, strumień Responses:** zwykły, ucięty `max_output_tokens`, `response.failed`, zdarzenie `error`.
- **Błędy generowania przez `LlmService` + `_retry.py`:** ponawiane i nie, w strumieniu i bez.
- **Failover przez `LlmService`** — w obu ścieżkach: ze strumieniem (OpenAI, Google) i bez (Anthropic, xAI):
  - 429 i 5xx przełączają;
  - 401, błąd sieci i błąd generowania nie przełączają;
  - start z kontem 1 w cooldownie;
  - oba konta w cooldownie, a ponowienie `_retry.py` wysyła żądanie;
  - jedno konto;
  - reset stanu między testami.
- **Pola Palantira ustawione dla innego silnika** → `LlmConfigError`.
- **Google:** `thought` odfiltrowane w strumieniu i bez.
- **UI:** etykieta grupy „PALANTIR FOUNDRY · OPENAI” dla `palantir:openai_responses`.

## Zakazy

- Zmiany poza tabelą „Granica zmiany”.
- Odczyt czegokolwiek z OpenCode w runtime; zmiany w repo `agents`; kod pod Linuksa; nowe zależności.
- Logowanie tokenów, nagłówków, adresów kont, promptów i danych plików.

## Warunki końcowe

- [ ] Każdy silnik ma listę modeli w swoim katalogu; Palantir ma 20 modeli, w Ustawieniach widać GPT-6 Astra; listy `openai`, `anthropic` i `gemini` odpowiadają dokumentacji dostawców.
- [ ] Obraz i PDF przechodzą przez każdy silnik, który je przyjmuje; pozostałe odmawiają przed wysłaniem.
- [ ] Palantir: `reasoning_variant`, `/responses` dla OpenAI i mechanizm drugiego konta działają w serwisie.
- [ ] Tłumaczenie działa (checkpoint właściciela).
- [ ] Bramki zielone; próby z fazy 6 zaliczone; review `astra` i Opus bez uwag poważnych.

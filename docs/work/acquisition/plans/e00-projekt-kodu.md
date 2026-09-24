---
kind: plan
status: zaakceptowany (astra, 2× Opus 5.5, orkiestrator)
baseline: e9d40d8
branch: work/acquisition/00-model-catalog-v2
created: 2026-09-24
---

# Projekt kodu E00

Uzupełnienie planu [e00-katalog-modeli.md](e00-katalog-modeli.md): plan mówi, co ma działać; ten dokument mówi, jak ma wyglądać kod. Autor projektu: `astra`. Sekcja „Rozstrzygnięcia” jest nadrzędna wobec reszty dokumentu.

## Rozstrzygnięcia

Rozstrzygają niejednoznaczności planu wskazane przez autora projektu oraz uwagi dwóch niezależnych przeglądów projektu.

1. **Limit próby połączenia:** `runtime.py` bez zmian. W fazie 6 raport rozróżnia „HTTP i generowanie działają” od „przyszedł tekst”.
2. **Alias a `provider_model_id` i protokół:** ID i protokół pochodzą z `LlmConfig`; alias daje tylko możliwości i opcje modelu. Bez walidatora zgodności.
3. **Wiadomość mieszana w Responses:** sąsiednie `TextPart` łączone przez `"\n"`, plik przerywa grupę i zostaje na swoim miejscu. Jedna pętla w `_responses_item`.
4. **`fallback_origin`:** reguły `_require_base_url` (tylko `https`, bez query i fragmentu) plus ścieżka pusta albo `/`. Nic więcej: bez sprawdzania portu, userinfo, IP ani hosta.
5. **Klucz cooldownu:** origin konta.
6. **Niepełne konto 2:** brak jednego z pól oznacza jedno konto, bez błędu.
7. **Testy nieznanego aliasu i złego originu:** po jednym teście tabelarycznym; origin: `http://…`, adres ze ścieżką, adres z query. Żadnych innych zniekształconych wejść.
8. **Lokalny `config/anishift.models.jsonc`:** to niezmieniona kopia przykładu. Wykonawca go nie rusza; usuwa go orkiestrator po sprawdzeniu, że AniShift nie działa. Commity dodają pliki jawnie, nigdy `git add -A`.
9. **Obsada i gałąź (decyzja właściciela z 2026-09-24, zastępuje obsadę z planu):** koduje `astra`; gałąź `work/acquisition/00-model-catalog-v2`. Akceptacja wymaga zgody trzech niezależnych recenzentów (świeża sesja `astra` i dwa świeże Claude Opus 5.5) oraz orkiestratora.
10. **Przycięte testy:**
    - failover: rodziny × {429, 500}, bez 503;
    - pola Palantira w innym silniku: jeden silnik × trzy pola (reguła brzmi „silnik inny niż `palantir`”, nie zależy od konkretnego silnika).
11. **Nazwa pliku PDF:** pusta `FilePart.name` daje `"document.pdf"` — jedna stała w `engines/_sdk_helpers.py`, używana przez Chat Completions i Palantir Responses.
12. **Commity tematyczne,** nie na fazę ani rundę review; poprawki z review trafiają do commita swojego tematu:
    1. `feat(llm): accept image, pdf, audio and video parts in every engine`
    2. `feat(llm): keep the palantir model list inside its engine`
    3. `feat(llm): send files and reasoning variants through palantir responses`
    4. `feat(llm): fail over between two palantir accounts`
    5. `feat(llm): refresh model suggestions from provider documentation`
13. **Listy modeli wszystkich silników natywnych (decyzja właściciela z 2026-09-24, rozszerza fazę 5):** `openai_compatible` bez listy (model wpisuje użytkownik); pozostałe według źródeł z 2026-09-24:
    - `openai`: `gpt-6-sol`, `gpt-6-luna`, `gpt-6-astra`;
    - `anthropic`: `claude-opus-5-5`, `claude-sonnet-5`, `claude-haiku-4-5`, `claude-fable-5-1`;
    - `gemini`: `gemini-3.8-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-pro-preview`;
    - `deepseek`: `deepseek-flash`, `deepseek-v4-pro` ([api-docs.deepseek.com/quick_start/pricing](https://api-docs.deepseek.com/quick_start/pricing));
    - `openrouter`: `openai/gpt-6-sol`, `anthropic/claude-opus-5.5`, `google/gemini-3.8-flash`, `deepseek/deepseek-v4.1-flash` (sprawdzone w `https://openrouter.ai/api/v1/models`).
14. **DeepSeek przyjmuje obrazy:** `deepseek` dostaje `file_modalities = {image}` zamiast `{}` — `deepseek-flash` przyjmuje `image_url` z data URL w Chat Completions ([api-docs.deepseek.com/guides/vision](https://api-docs.deepseek.com/guides/vision/)).
15. **Martwy kontrakt katalogu (przegląd kodu, runda 1; rozszerza granicę o same usunięcia):** z `config/model_catalog.py` znikają nieczytane pola i typy (`schema_version`, `issues`, `defaults`, `experimental`, `limits`, `CatalogIssue`, `CatalogSection`, `CatalogDefaults`, `ModelLimits`, `CATALOG_SCHEMA_VERSION`), a z serwisu `CATALOG_DEFAULTS` i limity w `PalantirModel`. U konsumentów znikają wyłącznie martwe gałęzie: `ModelCatalogError` z obsługą w `application/service.py`, gałąź pustego katalogu i filtry placeholderów `replace-with-`, jeśli po sprawdzeniu nic innego z nich nie korzysta.
16. **Jeden standard treści mieszanej:** Chat Completions i Responses łączą sąsiednie `TextPart` przez `"\n"` jedną wspólną funkcją; plik przerywa grupę. Anthropic i Google zachowują osobne bloki. Kształt bloków Anthropic Messages (tekst, obraz, dokument) istnieje raz, w `_sdk_helpers.py`, dla obu silników. Odmowa niewspieranego pliku w każdym silniku odbywa się tak samo: raz dla całego żądania, na początku budowania, jednym helperem.
17. **Nowe modele Palantira:** `gpt-6-sol` i `gpt-6-luna` dopisane do listy (22 modele). Próba na żywo 2026-09-24: przyjmują warianty `none`, `low`, `medium`, `high`, `xhigh`, `max` i obrazy; PDF proxy odrzuca (HTTP 400), więc typy plików = `{image}`.
18. **Przegląd kodu, runda 2:** `PalantirModel.reasoning` usunięte — myślenie OpenAI/xAI wynika z protokołu i `reasoning.effort` (każdy model GPT i Grok myśli); treść listy Palantira to dane potwierdzane próbą na żywo, testy sprawdzają tylko strukturę (unikalność aliasów, zgodność sugestii, ścieżki pól), bez listy aliasów i bez liczby modeli; pusty strumień (bez zdarzeń) daje błąd przejściowy w każdym protokole; martwe gałęzie `provider is None` przy wbudowanej liście znikają (`application/service.py`, `application/runtime.py`); separator `"\n"` istnieje w jednej funkcji.

Poniżej odwołania **§1–§4** oznaczają punkty sekcji „Szczegóły” zaakceptowanego planu. Sygnatury pomijają `self`, gdy nie powoduje to niejasności. Szacunki obejmują fizyczne linie dodane/usunięte, również wymianę istniejących testów.

## Faza 1

### 1. Plik po pliku

| Plik | Zmiana i odpowiedzialność | Podstawa |
|---|---|---|
| `services/llm/types.py` | Dodać `Modality = Literal["text", "image", "pdf", "audio", "video"]`. | §1 |
| jw. | Dodać frozen/slotted `FilePart(media_type: str, data: bytes = field(repr=False), name: str = "")`; `__post_init__() -> None` odrzuca puste dane i nieobsługiwany MIME. | §1 |
| jw. | Dodać `FilePart.modality -> Modality` jako **właściwość**, bez osobnego zapisanego pola; korzysta z `_file_modality(media_type: str) -> Modality`, która mapuje MIME albo rzuca istniejącym `_raise_request_error`. | §1 |
| jw. | Zmienić alias na `LlmContentPart = TextPart \| FilePart`. | §1 |
| jw. | Dodać `LlmMessage.__post_init__() -> None`: wymaga `TextPart`; odrzuca `FilePart` poza `USER`. | §1 |
| `services/llm/__init__.py` | Eksportować `FilePart`, `Modality`. | Faza 1 |
| `engines/_sdk_helpers.py` | Dodać `require_file_modality(part: FilePart, *, accepted: frozenset[Modality], engine_id: str) -> None`; komunikat zawiera silnik i typ pliku. | §2 |
| `engines/_openai_compatible.py` | Rozszerzyć `OpenAiCompatibleProvider` o wymagane `file_modalities: frozenset[Modality]`. | §2 |
| jw. | Przebudować `_build_completion_kwargs(request: LlmRequest) -> dict[str, object]`; mapowanie treści deleguje do `_message_content(message: LlmMessage) -> str \| list[dict[str, object]]`. | §2 |
| jw. | Dodać `_content_block(part: LlmContentPart) -> dict[str, object]`: tekst, `image_url` lub PDF `file`; odmowa modalności przed kodowaniem pliku. | §2 |
| `engines/{openai,openrouter,deepseek,openai_compatible}/service.py` | Uzupełnić istniejące `_PROVIDER`: odpowiednio `{image,pdf}`, `{image,pdf}`, `{}`, `{image}`. Konstruktory bez zmian. | §2 |
| `engines/anthropic/service.py` | Zastąpić `_text_blocks` przez `_content_blocks(parts: tuple[LlmContentPart, ...]) -> list[dict[str, object]]`; dodać `_content_block(part: LlmContentPart) -> dict[str, object]`. Istniejący `_build_completion_kwargs` używa nowych bloków. | §2 |
| `engines/gemini/service.py` | Zastąpić `_google_text_parts` przez `_google_parts(parts: tuple[LlmContentPart, ...], *, types_module: ModuleType) -> list[object]`; tekst zachowuje dotychczasową formę, plik używa `Part.from_bytes`. | §2 |
| `engines/palantir/protocols.py` | W istniejącym `_texts(message: LlmMessage) -> list[str]` usunąć wyłącznie powtórzony wymóg niepustej wiadomości; do fazy 3 pozostaje odmowa plików. | Przeniesienie reguły §1 |
| `tests/application/test_runtime_config.py` | W istniejącym teście promptów sprawdzić `isinstance(part, TextPart)` dla każdej części, następnie porównać pełną treść i kolejność. Bez filtrowania. | Granica zmiany |

Kolejność w `complete()` zostaje bez zmian: builder rzuca odmowę przed wywołaniem SDK (`create`), co spełnia plan.

### 2. Gdzie żyją reguły

- **MIME → modalność, niepuste dane:** tylko `types.py`.
- **Co najmniej jeden tekst, plik wyłącznie w `USER`:** tylko `LlmMessage`.
- **Przyjęcie modalności przez silnik/model:** jeden helper `require_file_modality`; zbiory możliwości należą do odpowiedniego providera.
- **Kształt API:** właściwy adapter.
- **Tekst Chat Completions:** nadal zwykły string z `"\n".join(...)`; lista bloków pojawia się tylko dla wiadomości mieszanej.

Znikają powtórzone kontrole „wiadomość musi zawierać tekst” z `_openai_compatible`, Anthropic, Gemini i Palantira. Rozróżnienie `TextPart`/`FilePart` w mapperze jest wyborem reprezentacji, nie ponowną walidacją obiektu.

### 3. Przepływ danych

`FilePart` → walidacja MIME/danych → `LlmMessage` sprawdza tekst i rolę → mapper sprawdza możliwości providera → serializacja SDK → istniejący transport i normalizacja.

Dla wiadomości mieszanej zachowana jest kolejność części. Nie przesuwamy wszystkich plików na początek ani wszystkich tekstów na koniec.

### 4. Co nie powstaje

- Osobne klasy `ImagePart`, `PdfPart`, `AudioPart`, `VideoPart`.
- Walidacja magic bytes, rozszerzeń, zawartości PDF, rozdzielczości czy długości nagrania.
- Ładowanie ścieżek, pobieranie URL-i, upload manager.
- Obsługa dowolnych obiektów w `parts`, np. `SimpleNamespace(kind="image")`.
- Powtórne kontrole roli i obecności tekstu w każdym silniku.
- Zapisana kopia `modality` obok `media_type`.

### 5. Testy

**`test_llm_registry.py` — rozszerzenie obecnego miejsca testowania kontraktów:**

- `test_file_part_maps_media_type_to_modality` — parametry: PNG/JPEG/WebP/PDF/audio/video.
- `test_file_part_rejects_empty_data_or_unknown_media_type` — parametry dwóch powodów odmowy.
- `test_file_part_repr_hides_data`.
- `test_message_rejects_file_outside_user_role` — `SYSTEM`, `ASSISTANT`.
- `test_message_requires_text_part` — pusta krotka i sam plik; przeniesienie istniejącej kontroli z testów providerów.

**Istniejące pliki providerów:**

- `test_anthropic_maps_mixed_file_content` — obraz/PDF, tekst–plik–tekst.
- `test_anthropic_rejects_unsupported_file_before_sdk_call` — audio/video.
- `test_gemini_maps_mixed_file_content` — obraz/PDF/audio/video.
- `test_chat_provider_maps_mixed_file_content` w `test_openai_compatible.py` — tabela klas providerów × wspierana modalność.
- `test_chat_provider_rejects_unsupported_file_before_sdk_call` — tabela niewspieranych kombinacji, z asercją pustego rejestru wywołań.
- Rozszerzyć `test_openai_compatible_maps_ordered_messages_and_optional_parameters` na cztery wrappery; sprawdzać niezmieniony string i separator.
- Zachować istniejące `test_anthropic_maps_ordered_messages_and_normalizes_response` oraz `test_gemini_maps_ordered_contents_and_normalizes_response` jako regresję tekstu.

**Wymiana/usunięcie:**

- `test_anthropic_rejects_unsupported_content_part`, `test_gemini_rejects_unsupported_content_part` i `test_every_protocol_rejects_an_unsupported_content_part` zastąpić testami prawdziwego `FilePart`; fikcyjny trzeci rodzaj części przestaje być kontraktem.
- `test_every_protocol_rejects_a_message_without_any_text_part` zastąpić pojedynczym testem `LlmMessage`.
- W fake’ach `test_llm_service.py`, `test_llm_registry.py`, `test_llm_retry.py` zawęzić typ przez asercję przed `.text`; w helperze retry można bezpośrednio użyć otrzymanego `text`.

### 6. Szacunek rozmiaru

- Kod: **+130–175 / −45–65**.
- Testy: **+180–240 / −35–60**.
- Większość dodatku testowego to tabela modalności i wykorzystanie istniejących fake’ów; bez nowego frameworka fixtures.

## Faza 2

### 1. Plik po pliku

**`engines/palantir/constants.py` — nowy, lekki moduł danych (§3):**

Dwie frozen/slotted klasy:

```python
PalantirProvider(provider_id: str, protocol: ModelProtocol, path: str)

PalantirModel(
    alias: str,
    provider_id: str,
    model_id: str,
    label: str,
    context_tokens: int,
    input_tokens: int,
    output_tokens: int,
    file_modalities: frozenset[Modality],
    reasoning: bool,
    options: Mapping[str, object],
    variants: Mapping[str, Mapping[str, object]],
)
```

Stałe:

- `PALANTIR_PROVIDERS: tuple[PalantirProvider, ...]` — cztery trasy; OpenAI jeszcze `OPENAI_CHAT`.
- `PALANTIR_MODELS: tuple[PalantirModel, ...]` — 22 wpisy w kolejności assetu.
- `SUGGESTED_MODEL_IDS` — wyliczone z `PALANTIR_MODELS`.
- `CATALOG_DEFAULTS: Mapping[str, str]` — dwa aliasy z planu.
- Wspólne stałe opcji i wariantów dla rodzin.

Dopuszczalne cztery małe konstruktory danych, eliminujące powtarzanie wartości rodzin:

```python
_gpt(model_id: str, label: str, levels: tuple[str, ...]) -> PalantirModel
_claude(model_id: str, label: str, levels: tuple[str, ...], *, output_tokens: int) -> PalantirModel
_gemini(model_id: str, label: str) -> PalantirModel
_grok(model_id: str, label: str) -> PalantirModel
```

Opus 4.5 jest jednym jawnym wpisem wyjątkowym: brak `thinking` i wariantów, inne limity. Nie dodajemy argumentów do konstruktora rodziny wyłącznie dla tego wyjątku.

**Pozostałe pliki:**

| Plik | Zmiana | Podstawa |
|---|---|---|
| `engines/__init__.py` | W `_REGISTRY["palantir"]` ustawić moduł sugestii; funkcje bez zmiany sygnatur. | §3 |
| `config/model_catalog.py` | Przebudować `load_model_catalog() -> ModelCatalog` na bezpośrednią projekcję stałych. Zachować DTO, `CatalogSection`, `CatalogIssue`, `ModelCatalogError`, `CATALOG_SCHEMA_VERSION`. | §3, konsumenci bez zmian |
| jw. | Usunąć `parse_model_catalog`, `ensure_model_catalog_file`, obie funkcje ścieżek, stałe plikowe oraz **wszystkie prywatne helpery parsera**: od `_catalog_error` do `_parse_defaults`. | §3 |
| `config/anishift.models.example.jsonc`, lokalny odpowiednik, `.gitignore` | Usunięcia wskazane w planie; lokalny plik: Rozstrzygnięcie 8. | Granica zmiany |
| `pyproject.toml`, `uv.lock` | Wyłącznie wynik `uv remove json5`. | Granica zmiany |
| `README.md`, `config/README.md` | Zastąpić instrukcję katalogu plikowego wskazaniem listy w serwisie. | Granica zmiany |

**Ważny szczegół:** `ModelCatalogError` musi zostać, mimo że nowy loader go nie zgłasza: `application/service.py:45,949` nadal importuje i obsługuje tę klasę. Usunięcie wymagałoby zakazanej zmiany konsumenta.

### 2. Gdzie żyją reguły

- Modele, limity, możliwości, opcje i warianty: wyłącznie `palantir/constants.py`.
- `config/model_catalog.py`: wyłącznie przełożenie na istniejące DTO.
- Katalog zwraca `schema_version=1`, `issues=()`, `experimental=False`.
- Opcje zapisane są już w nazwach pól HTTP; runtime nie zna nazw OpenCode.
- Poprawność wbudowanej tabeli sprawdzają testy, nie parser uruchamiany przy starcie.

### 3. Przepływ danych

`PALANTIR_MODELS` → `load_model_catalog()` → obecny model wyboru aplikacji/UI.

Równolegle: `SUGGESTED_MODEL_IDS` → istniejący leniwy rejestr.

Nie ma odczytu OpenCode ani JSONC podczas działania aplikacji.

### 4. Co nie powstaje

- Nowa domena katalogów, loader, repozytorium lub rejestr modeli.
- Kopia klas `ModelCatalog` w serwisie.
- Runtime’owa walidacja zaufanych stałych: pól, limitów, duplikatów, schematu.
- Import DTO aplikacyjnych do `palantir/constants.py`.
- Głęboko zamrażany własny format JSON, generator źródeł ani synchronizator OpenCode.
- Automatyczna migracja prywatnych, dodatkowych aliasów z usuwanego pliku.

### 5. Testy

**Nowy `test_palantir_constants.py`:**

- `test_palantir_model_list_matches_expected_aliases` — jawna lista 22 aliasów, kolejność, jednoznaczność.
- `test_palantir_suggestions_expose_model_aliases` — wynik publicznego rejestru.
- `test_palantir_options_and_variants_use_known_request_fields` — parametry rodzin; sprawdza również zagnieżdżone pola, np. `generationConfig.thinkingConfig`.
- Rozszerzyć istniejącą próbę świeżego importu o `palantir.constants`: brak `anishift.config`, `anishift.application`, SDK i transportu. To istniejący test izolacji, nie nowy mechanizm.

**`tests/config/test_model_catalog.py`:**

- `test_load_model_catalog_maps_builtin_models` — projekcja porównana z `PALANTIR_MODELS` (aliasy, providery, limity, etykiety); zbiór aliasów = dzisiejsze + Astra; dwa defaults; `issues=()`.
- Przebudować istniejący `test_loading_and_filtering_the_catalog_performs_no_network_access` na wbudowaną listę.
- Zachować test DTO bez sekretów/stanu dostępności.
- Zachować istniejącą kontrolę języka etykiet, kierując ją na wbudowany katalog.

Usunąć wszystkie `test_parse_*`, `test_ensure_*`, test brakującego pliku i odczytu runtime JSONC; ich kontrakt jest jawnie usuwany.

**Migracja istniejących fixtures:**

- `tests/config/test_model_settings.py::_catalog` — zwraca `ModelCatalog(...)`; pusty katalog konstruowany wprost.
- `tests/application/test_service.py::_catalog` — analogicznie.
- `tests/services/llm/test_palantir_config.py` — usunąć `_catalog_source` i `test_model_catalog_load_keeps_an_unsupported_protocol_visible_as_a_configuration_issue`.
- `tests/test_paths.py` — usunąć wyłącznie import i asercję ścieżki katalogu.
- `tests/cli/test_interactive_settings_models.py` już konstruuje DTO bez parsera; w tej fazie nie potrzebuje edycji.

### 6. Szacunek rozmiaru

- Kod: **+230–285 / −515–535** — nowa tabela około 200–250 linii, projekcja około 30.
- Testy: **+130–180 / −500–550**.
- Dodatkowo usunięcie **171 linii** przykładowego JSONC oraz mechaniczny diff lockfile.

## Faza 3

### 1. Plik po pliku

#### Konfiguracja i serwis

| Plik | Symbole | Podstawa |
|---|---|---|
| `wire_protocol.py` | Zamienić `OPENAI_CHAT` na `OPENAI_RESPONSES = "openai_responses"`, bez aliasu kompatybilnościowego. | §4 |
| `palantir/constants.py` | Zmienić protokół `foundry-openai`. | §3–§4 |
| `services/llm/config.py` | Dodać `reasoning_variant: str \| None = None`. | §4 |
| `palantir/config.py` | Dodać `palantir_model(alias: str) -> PalantirModel`: odszukanie wpisu albo `LlmConfigError`. | §3 |
| jw. | Dodać `request_options(model: PalantirModel, variant: str \| None) -> dict[str, object]`: defaulty + wybrany wariant, nieznany wariant → `LlmConfigError`. | §4 |
| jw. | Rozszerzyć `PalantirGenerationOptions` o `request_options: Mapping[str, object]`; `PalantirModelConfig` o `file_modalities: frozenset[Modality] = frozenset()`. | §4 |
| `palantir/service.py` | `__init__(config: LlmConfig, *, client: httpx.Client \| None = None) -> None` odszukuje i zachowuje `_model: PalantirModel`; istniejący `_resolve_model_config(config: LlmConfig, model: PalantirModel) -> PalantirModelConfig` przekłada możliwości modelu. | §3–§4 |
| jw. | Przebudować `_generation_options() -> PalantirGenerationOptions`: wariant oraz pominięcie `temperature`/`top_p`, gdy model myśli — OpenAI i xAI: `PalantirModel.reasoning` i `reasoning.effort` w rozwiązanych opcjach jest nieobecne albo różne od `"none"` (opcje domyślne GPT i Groka nie mają tego pola, a model myśli); Claude: rozwiązane opcje zawierają `thinking`. | §4 |
| jw. | Podmienić wpisy `_STREAM_MERGERS`, `_STREAM_TEXTS`; publiczne `complete`/`complete_stream` bez zmiany API. | §4 |

Publiczne `palantir_model_config(...)` zachowuje obecną sygnaturę, bo wywołuje je runtime. Wyszukiwanie modelu z listy należy do `PalantirService`, a nie do fabryki używanej przez aplikację.

#### Budowanie żądania — `palantir/protocols.py`

- Zachować sygnaturę `build_palantir_request(config, request, options=None, *, stream=False) -> PalantirHttpRequest`.
- Na wejściu sprawdzać modalności plików przez wspólny helper; tylko raz dla całego żądania.
- Zastąpić `_build_xai_responses` i `_build_openai_chat` jednym:

```python
_build_responses(
    config: PalantirModelConfig,
    request: LlmRequest,
    options: PalantirGenerationOptions,
) -> PalantirHttpRequest
```

- Dodać:
  - `_responses_item(message: LlmMessage) -> dict[str, Any]` — system/assistant jako string, user jako uporządkowane bloki.
  - `_responses_file(part: FilePart) -> dict[str, Any]` — obraz/PDF.
  - `_anthropic_block(part: LlmContentPart) -> dict[str, Any]`.
  - `_google_part(part: LlmContentPart) -> dict[str, Any]`.
  - `_data_url(part: FilePart) -> str` — wspólna reprezentacja plików Responses.
- Przebudować istniejące `_build_anthropic_messages`, `_build_google_generate`, `_generation_config` bez zmiany parametrów.
- Usunąć `_chat_completions_request`, `_texts`, `_joined_text`, `_CHAT_COMPLETIONS_ROUTE`, `_OPENAI_MAX_TOKENS_KEY`, `_COMPATIBLE_MAX_TOKENS_KEY`.
- `_streaming_variant(...)` przełącza OpenAI Responses; Google zachowuje obecną trasę.

**Scalanie opcji jest płytkie i celowe:** wszystkie warianty z assetu zastępują kompletne poddrzewo opcji — `reasoning`, `output_config` lub `generationConfig.thinkingConfig`. Nie potrzeba ogólnego recursive merge. Builder Google osobno łączy gotowe `generationConfig` z jawnymi limitami generowania, tworząc nowy słownik.

#### Odpowiedź i błędy

**`palantir/normalize.py`:**

- `_extract_xai_responses` → `_extract_responses(payload: Mapping[str, Any], alias: str) -> _Extracted`; używany przez oba protokoły.
- Dodać `merge_responses_stream(events: tuple[Mapping[str, Any], ...]) -> Mapping[str, Any]`: zwraca obiekt `response` z ostatniego zdarzenia terminalnego (`completed`, `incomplete`, `failed`); bez zdarzenia terminalnego zwraca `{}`.
- Dodać `responses_stream_delta(event: Mapping[str, Any]) -> str`: wyłącznie `response.output_text.delta`.
- W istniejącym `normalize_palantir_response(...)` wykryć `status == "failed"` przed kontrolą blokady i tekstu.
- W `_joined_text_parts(...)` pomijać `thought`; obecny filtr strumieniowy zachować.
- Usunąć `merge_openai_stream`, `openai_stream_delta`, `_extract_chat_completions`, `_chat_block_signal` i osierocone `_chat_usage`.

**`palantir/errors.py`:**

```python
palantir_generation_error(code: object, *, alias: str) -> LlmError
```

Jedno mapowanie: `server_error → 500`, `rate_limit_exceeded → 429`, reszta → `400`; dalej wykorzystać `palantir_status_error` bez przekazywania surowej wiadomości providera.

**`palantir/http.py`:**

- Istniejący konsument SSE rozpoznaje zdarzenie `type == "error"`, wyciąga kod i zgłasza `palantir_generation_error`. `response.failed` obsługuje normalizer przez `status == "failed"` w obiekcie terminalnym.
- Zachować istniejącą obsługę Google `{"error":{"code":429}}`; to odrębny istniejący format.
- Sygnatury transportu w tej fazie bez zmian.

**UI:** jedna zamiana klucza w `settings.py:1943`.

### 2. Gdzie żyją reguły

- Alias i wariant: `palantir/config.py`.
- Polityka temperatury: wyłącznie `PalantirService._generation_options`.
- Dozwolone pliki: specyfikacja modelu; egzekucja na wejściu `build_palantir_request`.
- Serializacja: `protocols.py`.
- Błędy generowania: jedno mapowanie w `errors.py`; HTTP/normalizer tylko rozpakowują odpowiedni format.
- Ucięcie i `finish_reason`: `_extract_responses`.
- Retry: dotychczasowe `_retry.py`.

**Istotne:** strumienia nie „naprawiamy” konkatenacją delt po braku zdarzenia końcowego. Delty służą postępowi; wynik pochodzi z odpowiedzi terminalnej. Brak terminala: `merge_responses_stream` zwraca `{}`, `_extract_responses` przy braku `status` od razu, przed sprawdzeniem `output`, zwraca `_Extracted("", "unknown", usage)`, a istniejący normalizer mapuje to na błąd przejściowy (`normalize.py:195-196`), jak dziś dla Chat. Ten sam skutek ma JSON xAI bez `status`. Parametr testu `test_palantir_engine.py:315-327` przechodzi z `OPENAI_CHAT` na `OPENAI_RESPONSES`.

### 3. Przepływ danych

```text
LlmConfig.alias
→ PalantirModel
→ defaulty / reasoning_variant
→ PalantirGenerationOptions
→ build_palantir_request
→ HTTP albo SSE
→ końcowy payload
→ wspólny reader Responses / reader Anthropic / reader Google
→ LlmResponse
```

`incomplete/max_output_tokens` zachowuje również pusty tekst. Już istniejący normalizer dopuszcza pustą odpowiedź przy limicie (`normalize.py:207`), a tłumaczenie rozpoznaje ten sygnał (`translation/.../service.py:34,194–195`).

### 4. Co nie powstaje

- Drugi builder i reader tylko dlatego, że OpenAI i xAI mają różne nazwy providerów.
- Chat Completions jako fallback Palantira.
- Rekurencyjny merger dowolnych konfiguracji.
- Walidator zgodności alias–model ID–trasa, którego plan nie zamawia.
- Streaming Anthropic/xAI, tool calls, historia Responses, encrypted reasoning.
- Automatyczne zwiększanie limitu tokenów lub zmiana parametrów runtime.
- Osobne testy każdego małego helpera serializującego.

### 5. Testy

**Żądania — nowy `test_palantir_requests.py`:**

- `test_palantir_request_maps_protocol_and_content` — cztery protokoły × tekst/obraz/PDF/audio/video; oczekiwana forma albo odmowa.
- `test_palantir_text_preserves_order_and_separators` — system/user/assistant, kilka tekstów; Responses zachowuje `"\n"`, Anthropic/Google osobne bloki.
- `test_palantir_mixed_content_preserves_order` — tekst–plik–tekst.
- `test_palantir_request_applies_reasoning_variant` — jeden wariant na rodzinę (OpenAI, xAI, Claude, Google).
- `test_palantir_request_rejects_unknown_variant`.
- `test_palantir_sampling_follows_thinking_policy` — OpenAI default/high/none, xAI default/low, Claude adaptive/Opus 4.5, Google; jednocześnie `temperature` i `top_p`. OpenAI default i xAI default: bez `temperature` i `top_p`.

**Silnik/strumień — `test_palantir_engine.py`:**

- `test_responses_stream_reports_deltas_and_uses_terminal_response` — zastępuje dwa testy strumienia Chat.
- `test_responses_token_limit_preserves_split_signal` — OpenAI stream i xAI JSON; tekst częściowy albo sam element reasoning.
- `test_responses_stream_reports_generation_failure` — `response.failed`, `error`.
- `test_google_filters_thought_parts` — stream/non-stream.
- `test_palantir_rejects_unknown_alias` — alias spoza listy daje `LlmConfigError`.

**Retry — `test_palantir_errors.py`:**

- `test_generation_failure_retry_through_llm_service` — parametry trzech formatów × `server_error`, `rate_limit_exceeded`, kod fatalny. Prawdziwy `LlmService` i `_retry.py`, podmieniona wyłącznie granica HTTP; liczba prób i końcowa klasa błędu.

**UI:**

- `test_palantir_responses_group_keeps_openai_label`.

**Migracja istniejących testów:**

- Testy request/response Chat w `test_palantir_config.py` i `test_palantir_engine.py` stają się testami Responses.
- Test pustej, zablokowanej, wadliwej odpowiedzi pozostaje, zmienia się fixture JSON.
- `test_request_builder_covers_every_protocol_the_catalog_can_declare` przestaje wymagać **czterech różnych funkcji**; oba Responses mają wspólną.
- `test_stream_error_event_is_not_silently_ignored` zachowuje dotychczasowy numeryczny format jako przypadek Google.
- We wszystkich fixture’ach tworzących `PalantirService` używać prawdziwego aliasu właściwej rodziny.
- Zmienić enum w wskazanych testach CLI/config oraz w fixture `tests/application/test_service.py` utworzonej w fazie 2.

### 6. Szacunek rozmiaru

- Kod: **+220–300 / −185–240**.
- Testy: **+330–450 / −210–300**.
- Największą pozycją jest wymiana istniejących fixture’ów Chat i tabela żądań, nie nowe mechanizmy.

## Faza 4

### 1. Plik po pliku

**`services/llm/config.py` (§4):**

- Dodać `fallback_origin: str = field(default="", repr=False)`.
- Dodać `fallback_api_key: str = field(default="", repr=False)`.
- W istniejącym `LlmConfig.__post_init__()` odrzucać ustawione trzy pola Palantira przy innym `engine_id`. Bez powielania kontroli w konstruktorach providerów.

**`palantir/config.py`:**

```python
require_palantir_origin(origin: str) -> None
```

Reguły `_require_base_url` (tylko `https`, bez query i fragmentu) plus ścieżka pusta albo `/`; błąd wskazuje `fallback_origin` i nie ujawnia wartości. Bez kontroli portu, userinfo, IP i hosta.

**`palantir/accounts.py` — nowy:**

```python
PalantirAccount(number: int, origin: str = field(repr=False), token: str = field(repr=False))

palantir_accounts(config: LlmConfig) -> tuple[PalantirAccount, ...]
account_order(accounts: tuple[PalantirAccount, ...]) -> tuple[PalantirAccount, ...]
start_cooldown(account: PalantirAccount) -> None
clear_cooldown(account: PalantirAccount) -> None
reset_cooldowns() -> None
account_request(built: PalantirHttpRequest, account: PalantirAccount) -> PalantirHttpRequest
```

- `palantir_accounts`: konto 1 z istniejącego URL/tokena; konto 2 tylko przy obu polach. Walidacja tokena przez istniejący helper.
- `account_order`: jeden snapshot puli na próbę; bez gotowych kont zwraca całość.
- Cooldown: `dict[str, float]` kluczowany originem, `time.monotonic()`, stałe 60 s, wspólny `threading.Lock`.
- `account_request`: podmienia scheme/netloc i `Authorization`; zachowuje trasę, query SSE, body oraz nagłówek Anthropic.

**`palantir/auth.py`:**

Rozszerzyć istniejącą funkcję:

```python
validated_palantir_token(token: str, *, field_name: str = PALANTIR_TOKEN_ENV_VAR) -> str
```

Pozwala nazwać `fallback_api_key` przy błędzie drugiego tokena, bez drugiego walidatora.

**`palantir/http.py`:**

Do `send_palantir_request` i `stream_palantir_request` dodać wymagany keyword-only `accounts: tuple[PalantirAccount, ...]`.

Przebudować istniejący `_send` na wspólne otwarcie odpowiedzi dla obu ścieżek:

```python
_send(
    client: httpx.Client,
    built: PalantirHttpRequest,
    *,
    alias: str,
    accounts: tuple[PalantirAccount, ...],
) -> httpx.Response
```

Używa `client.build_request` + `client.send(..., stream=True)`:

1. bierze pulę raz;
2. otwiera odpowiedź danego konta;
3. na 429/≥500 ustawia cooldown;
4. zamyka pomijaną odpowiedź przed następnym kontem;
5. inna odpowiedź → `clear_cooldown(account)` i zwrot tej odpowiedzi; gdy każde konto z puli dało 429/≥500 → zwrot ostatniej odpowiedzi błędnej.

Odczyt body w `send_palantir_request` i iteracja SSE w `stream_palantir_request` pozostają pod tym samym mapowaniem co otwarcie odpowiedzi: `httpx.TimeoutException` → `LlmTimeoutError`, `httpx.TransportError` → `LlmProviderUnavailableError`.

Obaj konsumenci przejmują odpowiedź w `closing(...)`; zwykły ją odczytuje, strumieniowy konsumuje SSE. Klasyfikacja końcowego HTTP może korzystać z jednego `_status_failure(response: httpx.Response, *, alias: str) -> LlmError`.

**`palantir/service.py`:** zbudować `_accounts` w konstruktorze i przekazywać do obu funkcji transportu. Publiczne API bez zmian.

### 2. Gdzie żyją reguły

- Konfiguracja kont i cooldown: `accounts.py`.
- Decyzja o przełączeniu: wyłącznie surowy status HTTP w `_send`.
- Rozpakowanie body, SSE i błędy generowania: po wyborze odpowiedzi.
- Ponowienie całej próby: wyłącznie `_retry.py`.

Nie wolno decydować o failoverze przez `except LlmRateLimitError`: ta sama klasa może oznaczać błąd generowania w odpowiedzi HTTP 200, a plan zakazuje wtedy przełączenia.

### 3. Przepływ danych

```text
gotowe żądanie protokołu
→ snapshot kont poza cooldownem, ewentualnie wszystkie
→ podmiana originu i tokena
→ nagłówki odpowiedzi HTTP
→ failover wyłącznie po 429/≥500
→ odczyt body/SSE
→ normalizacja lub błąd
→ istniejące retry
```

Lock obejmuje wyłącznie odczyt/zapis tabeli terminów, nigdy HTTP ani oczekiwanie.

### 4. Co nie powstaje

- Account manager z lifecycle, scheduler, circuit breaker.
- Round-robin, przypinanie konta, konfigurowalny cooldown.
- Persistence cooldownów, liczniki błędów, odświeżanie tokenów.
- Failover na błędzie sieci, parsera, safety lub generowania.
- Osobne pętle przełączania dla stream i non-stream.
- Nowy retry lub sleep w transporcie.
- Walidacja dowolnych par kont, automatyczna deduplikacja lub porównywanie tokenów.

### 5. Testy

**Nowy `test_palantir_accounts.py`, wszystkie przepływy przez `LlmService`:**

- `test_http_limit_or_server_error_switches_account` — cztery rodziny × 429/500; sprawdza host/token i niezmienione body/trasy.
- `test_non_failover_failure_stays_on_account` — 401, błąd sieci przy otwarciu, timeout przy odczycie body (ścieżka zwykła), błąd generowania; stream/non-stream. Dla przejściowych błędów odróżnia retry od zmiany konta.
- `test_account_cooldown_is_shared_between_services` — pierwsza instancja chłodzi konto 1, druga zaczyna od 2, także dla innej rodziny; po 60 s konto 1 wraca.
- `test_retry_uses_accounts_when_both_are_cooling_down` — oba odmawiają, `_retry.py` rzeczywiście wysyła kolejną próbę; każde konto najwyżej raz na próbę.
- `test_single_account_preserves_retry_behavior` — stream/non-stream.
- `test_fallback_origin_rejects_invalid_origin` — `http://…`, adres ze ścieżką, adres z query.

Lokalna fixture resetuje stan **przed i po** teście; bez globalnego fixture całego repo. Zegar patchowany, bez rzeczywistego czekania 60 sekund.

**`test_llm_registry.py`:**

- `test_non_palantir_config_rejects_palantir_settings` — jeden silnik × trzy pola.
- Rozszerzyć istniejący test ukrywania sekretów w `repr` o oba nowe pola.

### 6. Szacunek rozmiaru

- Kod: **+150–200 / −30–55**.
- Testy: **+220–300 / −0–10**.
- `accounts.py` około 75–95 linii; pozostały koszt to wspólne otwarcie HTTP i przekazanie kont.

## Faza 5

### 1. Plik po pliku

| Plik | Zmiana | Podstawa |
|---|---|---|
| `engines/openai/constants.py` | `SUGGESTED_MODEL_IDS`: `gpt-6-sol`, `gpt-6-luna`, `gpt-6-astra`. | §3 |
| `engines/anthropic/constants.py` | `claude-opus-5-5`, `claude-sonnet-5`, `claude-haiku-4-5`, `claude-fable-5-1`. | §3 |
| `engines/gemini/constants.py` | `gemini-3.8-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-pro-preview`. | §3 |
| `services/llm/AGENTS.md` | Udokumentować właścicieli reguł, pliki, Responses, reasoning i granicę failover/retry. | Faza 5 |
| `config/AGENTS.md` | Zastąpić opis plikowego katalogu projekcją listy z serwisu. | Faza 5 |

Żadne funkcje ani klasy nie dochodzą.

### 2. Gdzie żyją reguły

Sugestie nadal należą do `constants.py` danego silnika i pozostają niewiążące. Lista Palantira jest osobnym, zamkniętym kontraktem.

### 3. Przepływ danych

Dotychczasowy `suggested_model_ids(engine_id)` → istniejący konsument aplikacji/UI.

### 4. Co nie powstaje

- Pobieranie modeli z API.
- Automatyczne odświeżanie dokumentacji.
- Przepisywanie modeli natywnych do Palantira.
- Walidowanie własnych ID na podstawie sugestii.

### 5. Testy

Wyłącznie aktualizacja istniejących:

- `test_anthropic_registry_and_suggestions_are_lazy`.
- `test_gemini_registry_and_suggestions_are_lazy`.
- `test_openai_suggestions_are_small_unique_strings` — uzupełnić o dokładną oczekiwaną listę.

DeepSeek, OpenRouter i pusty katalog custom endpointu zachowują istniejące testy.

### 6. Szacunek rozmiaru

- Kod: **+7–12 / −6–10**.
- Testy: **+8–15 / −5–10**.
- Instrukcje: około **20–35 zmienionych linii**.

## Faza 6

- **Wykonawca:** orchestrator. Skrypt `scripts/tmp/e00_live.py` (katalog jednorazowy, poza commitami) woła `LlmService` z `LlmConfig` zbudowanym przez istniejące `Settings` i `palantir_llm_config`; token czyta aplikacja, skrypt go nie wypisuje.
- **Macierz na koncie 1:** każdy z 22 modeli × (tekst z opcjami domyślnymi; każdy typ pliku z jego listy; każdy wariant). Małe pliki próbne: PNG, PDF, MP3, MP4.
- **`probe_palantir_model`:** jeden model z każdej rodziny; raport rozróżnia „HTTP i generowanie działają” od „przyszedł tekst” (Rozstrzygnięcie 1).
- **Konto 2:** gdy właściciel poda token; adres i token przekazane wprost skryptowi.
- **Wynik:** tabela zbiorcza w `docs/work/acquisition/outcomes/e00.md` (bez treści odpowiedzi, tokenów i adresów).
- **Checkpoint właściciela:** tłumaczenie jednego odcinka.

## Podsumowanie

### Łączny szacunek

| Obszar | Dodane | Usunięte | Przyrost netto |
|---|---:|---:|---:|
| Kod Python | **737–972** | **781–905** | około **−168 do +191** |
| Testy Python | **868–1185** | **750–930** | około **−62 do +435** |

Poza tym: usunięcie przykładowego JSONC, aktualizacja dokumentacji i diff wygenerowany przez `uv remove json5`. Przedziały wynikają z wymienionych tabel danych, mapperów i migracji testów; nie są limitem, do którego należy dopasowywać kod. Szacunek sprzed przycięcia testów w Rozstrzygnięciu 10 i poprawek przeglądu; rzeczywisty rozmiar testów będzie mniejszy.

### Pięć najważniejszych decyzji

1. **`LlmMessage` jest jedynym właścicielem wymogu tekstu i reguły ról.**
2. **Tabela Palantira jest źródłem prawdy; katalog aplikacyjny jest jej cienką projekcją.**
3. **OpenAI i xAI współdzielą builder i reader Responses; stara ścieżka Chat znika.**
4. **Opcje wariantów zastępują znane kompletne poddrzewa — bez uniwersalnego recursive merge.**
5. **Failover działa na statusie HTTP przed odczytem treści; retry pozostaje w `_retry.py`.**

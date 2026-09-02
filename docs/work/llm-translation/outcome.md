---
kind: outcome
status: superseded
baseline: c9e8f0e plus accepted docs/work/llm-translation/spec.md
resulting-state: implementation in working tree, no commit
completed: 2026-08-30
superseded-by: docs/work/llm-translation/plan-numbered-lines.md
---

# Outcome: JSON contract for LLM translation

Kontrakt JSON opisany niżej został zastąpiony kontraktem numerowanych linii
(`line_contract.py`), a `json_contract.py` usunięty. Ten dokument pozostaje
zapisem tego, co ten etap faktycznie dowiózł, nie opisem aktualnego stanu kodu.

## Status

- status: implementation complete; human settings smoke pending
- branch / environment: `work/interactive-cli/04-mascot-polish`, Windows, Python 3.14.2
- resulting commit: none
- working tree: scoped implementation, tests and workstream documents are uncommitted
- human acceptance: pending

## Finalny rezultat

Silnik LLM wysyła napisy jako osobny, ścisły JSON i akceptuje wyłącznie kompletny
wynik zgodny z kontraktem `translations`. Trzy bazowe prompty oraz jeden wybrany
styl są polskimi zasobami Markdown należącymi do modułu i trafiają do wheel.
Błędna odpowiedź dostaje ograniczone retry z bezpieczną diagnozą ostatniego
naruszenia; wyłącznie limity kontekstu lub wyjścia uruchamiają podział partii.

Konfiguracja schema 3 przechowuje tylko `llm_translation_style`. UI otrzymuje
cache'owaną, naturalnie posortowaną listę poprawnych `styles/*.md`, a limit plików
LLM pozostaje `1..4` z wartością domyślną `4`.

## Zrealizowany zakres

| Element | Wynik | Dowód |
| --- | --- | --- |
| Wejściowy i wyjściowy kontrakt JSON | done | testy serializacji i ścisłej walidacji |
| Retry oraz failure semantics | done | testy kolejnych naruszeń, wyczerpania, splitu i fallbacku całego pliku |
| Packaged Markdown prompts | done | build wheel, lista archiwum i import bezpośrednio z wheel |
| Migracja ustawień schema 1/2/3 | done | testy loadera, roundtripu i usunięcia pól legacy |
| Wybór jednego stylu w UI/catalog | done | test katalogu ustawień i skan zasobów |
| Human smoke ustawień | not done | wymaga ręcznego otwarcia ekranu ustawień |

## Zmiany

| Ścieżka / element | Zmiana | Powód |
| --- | --- | --- |
| `translation/engines/llm/json_contract.py` | ścisła serializacja i walidacja JSON | jeden provider-agnosticzny kontrakt |
| `translation/engines/llm/prompts/` | loader i cztery zasoby `.md` | prompty jako część instalowanej aplikacji |
| `translation/engines/llm/service.py` | retry kontraktowe i split tylko po limitach | brak częściowych lub liberalnie odzyskanych wyników |
| `translation/protocols.py`, `application/runtime.py` | `system` oraz uporządkowane `user_parts` | osobne role i czysty JSON jako `TextPart` |
| settings, planning, field catalog i UI | jedno pole `llm_translation_style`, schema 3 | usunięcie starego registry i prompt IDs |
| `config/prompts/`, stary composer/registry/types/assets | usunięte | jedno źródło prawdy w module LLM |
| testy translatora, konfiguracji i runtime | przepisane lub rozszerzone | ochrona nowego kontraktu i migracji |

## Dowody automatyczne

```text
uv run ruff check anishift/ tests/
PASS

uv run ruff format --check anishift/ tests/
PASS (418 files formatted)

uv run mypy <21 changed source and test paths>
PASS (no issues in 21 source files)

uv run pytest <translator/config/runtime targeted paths> -n 0 -q
PASS (170 tests; known unrelated VPN assertion excluded)

uv run python scripts/hooks/check_const_docstrings.py
PASS

uv run python scripts/hooks/check_test_comments.py
PASS

uv build --wheel
PASS: dist/anishift-0.1.0-py3-none-any.whl

wheel importlib.resources smoke
PASS: imported anishift from wheel, styles=('neutral',), all four prompts non-empty
```

Pełny `uv run mypy anishift/ tests/` pozostaje czerwony z 37 zastanymi błędami w
trzech testach interaktywnego CLI. Pełny `uv run pytest` zakończył się wynikiem
2149 passed, 48 failed, 2 collection errors i 7 skipped; awarie dotyczą zastanego
interaktywnego CLI, command CLI, przykładowego model catalog oraz znanej asercji
domyślnego VPN. Zmieniony zakres przechodzi w całości.

## Review

- zakres: kontrakt JSON, prompty, retry, migracja ustawień, UI catalog i wheel
- findingi: sortowanie nie było naturalne; config nie odrzucał ścieżki stylu;
  terminalny błąd nie zawierał ostatniej bezpiecznej kategorii; brakowało kilku
  edge-case tests
- poprawki: `natsorted`, walidacja separatorów ścieżki, bezpieczna ostatnia
  diagnoza, testy casefold/Unicode/pustej partii/fallbacku
- wynik ponownej kontroli: PASS dla implementacji; human acceptance PENDING

## Human feedback

| Checkpoint | Wynik | Korekta | Re-check |
| --- | --- | --- | --- |
| Ekran tłumaczenia pokazuje tylko `Styl` i `Plików LLM jednocześnie` | pending | brak | pending |
| Jeden styl `neutral` jest widoczny i wybieralny | pending | brak | pending |

## Odchylenia lokalne

| Odchylenie | Dlaczego nie zmienia kontraktu | Dowód |
| --- | --- | --- |
| Lista packaged styles jest cache'owana do restartu procesu | pliki są zasobami wersji aplikacji, a cache usuwa I/O z kolejnych renderów | catalog i loader tests |
| Pełne bramki repo pozostają czerwone | failures są poza diffem i zmieniony zakres ma osobne zielone kontrole | pełny output oraz targeted suite |

## Materialne odkrycia

- odkrycie: bieżąca gałąź ma znacząco rozjechane testy interaktywnego CLI
- dowód: 37 błędów mypy oraz większość z 48 pytest failures dotyczy `tests/cli/`
- wpływ: nie można uczciwie oznaczyć pełnych bramek ani human acceptance jako pass
- potrzebna decyzja: osobny workstream naprawy CLI, bez rozszerzania translatora

## Finalne kontrakty

- owner stanu: `anishift/services/translation/engines/llm/`
- source of truth: `json_contract.py` oraz packaged `prompts/*.md`
- publiczne API/schema: `LlmCompletionRequest(system, user_parts)` i settings schema 3
- lifecycle: load prompts, complete, strict parse, bounded correction albo size split
- kompatybilność: settings v1/v2 są migrowane; provider adapters i dalszy wynik pipeline pozostają bez zmian

## Znane ograniczenia i follow-up

- Ręczny smoke ekranu ustawień nie został wykonany.
- Rozbudowanie treści promptów i dodatkowe style pozostają osobnym krokiem.
- Zastane awarie pełnego suite nie należą do tego workstreamu.

## Stan do dalszej pracy

- pliki wymagane do przeczytania: `spec.md`, `plan.md`, ten `outcome.md`
- dokładny następny krok: ręcznie otworzyć ustawienia translatora LLM i zaakceptować dwa checkpointy UI
- czego nie zakładać: pełny suite repozytorium nie jest obecnie zielony
- czy potrzebny jest świeży kontekst: nie dla smoke UI; tak dla osobnej naprawy CLI

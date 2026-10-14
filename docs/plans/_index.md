# Historyczne plany etapów AniShift

> Bieżący punkt wejścia: [dokumenty](../README.md); pomysły na później: [ideas.md](../ideas.md). Poniższy spis jest historią, nie kolejką wykonania.

> źródło historyczne dla etapów 1–8: [`plan-anishift.md`](plan-anishift.md) (legacy roadmap). wzorce: [`../reference/mangashift-architecture/`](../reference/mangashift-architecture/) (engine-factory-standard, engine-standard, naming-glossary).
> zasady wspólne: recykling MangaShift 1:1, prostota (KISS/YAGNI), rejestr silników TYLKO w tts/translation/llm, fasady sync, zero kodu poza planem etapu.
> artefakty workstreamu etapu 10 (wymagania, plan, graf zadań) leżą w [`../work/10-tui/`](../work/10-tui/), nie w `docs/plans/`. ich część interfejsowa jest już historyczna — patrz status etapu 10.

| etap | plik | cel (1 zdanie) | zależy od |
|---|---|---|---|
| 1 | [stage-1-foundation.md](stage-1-foundation.md) | **ZROBIONE** — pakiet `anishift` z configiem, workspace, platform i doktorem, uruchamialny przez `uv run anishift`. | — |
| 2 | [stage-2-shell.md](stage-2-shell.md) | **ZROBIONE** — interaktywny shell z REPL, komendami i ustawieniami. | 1 |
| 2.5 | [stage-2.5-binary-downloader-v2.md](stage-2.5-binary-downloader-v2.md) | **ZROBIONE** — manifest, leniwe pobieranie MKVToolNix/FFmpeg oraz `setup`/`doctor`. | 2 |
| 3 | [stage-3-extraction-refactor.md](stage-3-extraction-refactor.md) | **ZROBIONE** — ekstrakcja ścieżek i przygotowanie napisów. | 1, 2, 2.5 |
| 4 | [stage-4-translation.md](stage-4-translation.md) | **ZROBIONE** — tłumaczenie Google/DeepL z deduplikacją i czyszczeniem znaczników. | 3 |
| 4.5 | — (issue #21) | **W TOKU** — agentyzacja repo: twarde strażniki (hooki/ruff/pre-push/CI), AGENTS.md per moduł, standardy review. Proces, nie kod produktu. | — |
| 5 | [stage-5-llm.md](stage-5-llm.md) | **ZROBIONE** — serwis LLM, silnik tłumaczenia i opcjonalna korekta napisów. | 4 |
| 6 | [stage-6-tts-audio.md](stage-6-tts-audio.md) | **ZROBIONE** — silniki TTS i osobny tor audio FFmpeg. | 4 (równolegle z 5) |
| 6.1 | [stage-6.1-shared-text-primitives.md](stage-6.1-shared-text-primitives.md) | **ZROBIONE** — wspólne granice Unicode i grafemy dla translation/TTS. | 6 |
| 7 | [stage-7-requirements.md](stage-7-requirements.md) + [stage-7-plan.md](stage-7-plan.md) | **ZROBIONE** — składanie players/MKV/MP4, `/compose` i pełny pipeline. | 6 |
| 8 | [wymagania](stage-8-requirements.md) + [plan](stage-8-binary-distribution.md) | **ZROBIONE** — launcher Windows, audyt legacy, walidacja i zamknięcie roadmapu. | 7 |
| 9 | [produkt](stage-9-requirements.md) + [interfejs](stage-9-interface-requirements.md) + [plan](stage-9-plan.md) | **CZĘŚCIOWO** — dostarczono model artefaktów, strumieniowy scheduler i application API (`AppService`); warstwa Textual TUI odrzucona, przepisywana w etapie 10. historyczne issue #38 nadal opisuje odrzucony Textual; wspólny rdzeń jest już na main po PR #41. | 8 |
| 10 | [wymagania](../work/10-tui/spec.md) + [plan](../work/10-tui/plan.md) + [zadania](../work/10-tui/tasks.json) | **ZAMKNIĘTY INACZEJ** — utrzymano silnik LLM Palantir, format `anishift.models.jsonc`, usunięcie `anishift/pipeline/` i pytest Windows w CI. Warstwa Textual TUI po testach na żywo ODRZUCONA jako nadmiarowa: obecny interaktywny terminal używa Prompt Toolkit, gołe `anishift` otwiera Home. Pełny snapshot TUI zachowany na gałęzi `archive/textual-tui`. | 9 |

## graf zależności

```text
1 → 2 → 2.5 → 3 → 4 → 5 (llm)
                      └→ 6 (tts+audio) → 6.1 (text) → 7 (e2e) → 8 (closure) → 9 (product/UI model) → 10 (TUI rewrite)
```

etapy 5 i 6 mogły iść równolegle. decyzje etapu 9 są podejmowane po zamknięciu starego roadmapu w etapie 8. etap 10 przepisał odrzuconą warstwę TUI z etapu 9, po czym sam interfejs graficzny został porzucony — obecny frontend to Prompt Toolkit, a nie dawny Textual ani etap przejściowy bez menu.

## reguły obowiązujące w każdym etapie

- każdy etap kończy się działającą apką (zero half-done).
- trwałe produkty powstają obok źródła w `workspace/`; dane robocze jednego runu trafiają do `workspace/temp/` i są sprzątane po zakończeniu.
- domenowe configi: dataclass `slots=True`, wymagany `engine_id` bez defaultu — default trzyma panel (`config/settings.json`).
- błędy domenowe (podklasy `anishift/errors.py`), nigdy `sys.exit()` ani goły traceback do usera.
- `utils/` — dawniej nietykalne; reguła zniesiona, całość docelowo doprowadzana do standardu (patrz issue #21).

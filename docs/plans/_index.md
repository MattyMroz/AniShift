# plany etapów AniShift — spis

> źródło prawdy dla etapów 1–8: [`plan-anishift.md`](plan-anishift.md) (legacy roadmap). wzorce: `mangashift-architecture-ref/` (engine-factory-standard, engine-standard, naming-glossary).
> zasady wspólne: recykling MangaShift 1:1, prostota (KISS/YAGNI), rejestr silników TYLKO w tts/translation/llm, fasady sync, zero kodu poza planem etapu.

| etap | plik | cel (1 zdanie) | zależy od |
|---|---|---|---|
| 1 | [etap-1-fundament.md](etap-1-fundament.md) | **ZROBIONE** — pakiet `anishift` z configiem, workspace, platform i doktorem, uruchamialny przez `uv run anishift`. | — |
| 2 | [etap-2-shell.md](etap-2-shell.md) | **ZROBIONE** — interaktywny shell z REPL, komendami i ustawieniami. | 1 |
| 2.5 | [etap-2.5-pobieracz-binarek-v2.md](etap-2.5-pobieracz-binarek-v2.md) | **ZROBIONE** — manifest, leniwe pobieranie MKVToolNix/FFmpeg oraz `setup`/`doctor`. | 2 |
| 3 | [etap-3-ekstrakcja-refaktor.md](etap-3-ekstrakcja-refaktor.md) | **ZROBIONE** — ekstrakcja ścieżek i przygotowanie napisów. | 1, 2, 2.5 |
| 4 | [etap-4-tlumaczenie.md](etap-4-tlumaczenie.md) | **ZROBIONE** — tłumaczenie Google/DeepL z deduplikacją i czyszczeniem znaczników. | 3 |
| 4.5 | — (issue #21) | **W TOKU** — agentyzacja repo: twarde strażniki (hooki/ruff/pre-push/CI), AGENTS.md per moduł, standardy review. Proces, nie kod produktu. | — |
| 5 | [etap-5-llm.md](etap-5-llm.md) | **ZROBIONE** — serwis LLM, silnik tłumaczenia i opcjonalna korekta napisów. | 4 |
| 6 | [etap-6-tts-audio.md](etap-6-tts-audio.md) | **ZROBIONE** — silniki TTS i osobny tor audio FFmpeg. | 4 (równolegle z 5) |
| 6.1 | [etap-6.1-shared-text-primitives.md](etap-6.1-shared-text-primitives.md) | **ZROBIONE** — wspólne granice Unicode i grafemy dla translation/TTS. | 6 |
| 7 | [etap-7-wymagania.md](etap-7-wymagania.md) + [etap-7-plan.md](etap-7-plan.md) | **ZROBIONE** — składanie players/MKV/MP4, `/compose` i pełny pipeline. | 6 |
| 8 | [wymagania](etap-8-wymagania.md) + [plan](etap-8-dystrybucja-binarek.md) | **ZROBIONE** — launcher Windows, audyt legacy, walidacja i zamknięcie roadmapu. | 7 |
| 9 | [produkt](etap-9-wymagania.md) + [interfejs](etap-9-interfejs-wymagania.md) + [plan](etap-9-plan.md) | **PLAN** — model artefaktów, strumieniowy scheduler, application API i Textual TUI z command barem `❯`; gotowe do realizacji po akceptacji planu. | 8 |

## graf zależności

```text
1 → 2 → 2.5 → 3 → 4 → 5 (llm)
                      └→ 6 (tts+audio) → 6.1 (text) → 7 (e2e) → 8 (closure) → 9 (product/UI model)
```

etapy 5 i 6 mogły iść równolegle. decyzje etapu 9 są podejmowane po zamknięciu starego roadmapu w etapie 8.

## reguły obowiązujące w każdym etapie

- każdy etap kończy się działającą apką (zero half-done).
- trwałe produkty powstają obok źródła w `workspace/`; dane robocze jednego runu trafiają do `workspace/temp/` i są sprzątane po zakończeniu.
- domenowe configi: dataclass `slots=True`, wymagany `engine_id` bez defaultu — default trzyma panel (`config/settings.json`).
- błędy domenowe (podklasy `anishift/errors.py`), nigdy `sys.exit()` ani goły traceback do usera.
- `utils/` — dawniej nietykalne; reguła zniesiona, całość docelowo doprowadzana do standardu (patrz issue #21).

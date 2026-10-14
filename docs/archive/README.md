# Archiwum AniShift

Zakończone, porzucone i zastąpione etapy. Dokumenty zachowują kontekst swoich
commitów; nie są bieżącą kolejką ani gwarancją obecnego zachowania aplikacji.
Aktualny punkt wejścia: [dokumenty](../README.md), dalsze pomysły: [ideas.md](../ideas.md).

„Zrobione” oznacza dostarczony zakres, niekoniecznie scalony do `main`.
PR #57 i #59 nadal czekają na merge. „—” oznacza brak osobno ustalonego PR.

| Katalog / plik | Co to było | Status | PR |
|---|---|---|---|
| [stages/plan-anishift.md](stages/plan-anishift.md), [plan-audit-fixes.md](stages/plan-audit-fixes.md) | Pierwotna roadmapa i poprawki audytu | zastąpione przez kolejne etapy | [#36](https://github.com/MattyMroz/AniShift/pull/36), [#37](https://github.com/MattyMroz/AniShift/pull/37) |
| [Etap 1](stages/stage-1-foundation.md) | Pakiet, config, workspace, platforma i doctor | zrobione | [#9](https://github.com/MattyMroz/AniShift/pull/9) |
| [Etap 2](stages/stage-2-shell.md), [pierwszy plan](stages/2026-07-12-stage-2-shell.md) | Interaktywny shell z REPL i ustawieniami | zrobione; interfejs zastąpiony przez Prompt Toolkit | [#10](https://github.com/MattyMroz/AniShift/pull/10) |
| [Etap 2.5](stages/stage-2.5-binary-downloader-v2.md), [wymagania](stages/stage-2.5-requirements.md), [pierwszy plan](stages/2026-07-16-stage-2.5-binary-downloader.md) | Manifest, pobieranie MKVToolNix/FFmpeg, setup/doctor | zrobione | [#14](https://github.com/MattyMroz/AniShift/pull/14), [#15](https://github.com/MattyMroz/AniShift/pull/15) |
| [Etap 3](stages/stage-3-extraction-refactor.md) i `stages/stage-3-*` | Ekstrakcja ścieżek i przygotowanie napisów | zrobione | [#18](https://github.com/MattyMroz/AniShift/pull/18) |
| [Etap 4](stages/stage-4-translation.md), `stages/stage-4-*`, [kolejka](stages/translation-queue-requirements.md) | Tłumaczenie Google/DeepL, deduplikacja i czyszczenie znaczników | zrobione | [#19](https://github.com/MattyMroz/AniShift/pull/19) |
| Etap 4.5 ([issue #21](https://github.com/MattyMroz/AniShift/issues/21)) | Agentyzacja repo: hooki, ruff, pre-push, CI, AGENTS.md i review | zrobione w zakresie strażników; issue pozostaje otwarte | [#24](https://github.com/MattyMroz/AniShift/pull/24), [#25](https://github.com/MattyMroz/AniShift/pull/25) |
| [Etap 5](stages/stage-5-llm.md) i `stages/stage-5-*` | Serwis LLM, tłumaczenie i opcjonalna korekta | zrobione | — |
| [Etap 6](stages/stage-6-tts-audio.md) i `stages/stage-6-*` | Silniki TTS i osobny tor audio FFmpeg | zrobione; dalsza wydajność odłożona w ideas.md | [#30](https://github.com/MattyMroz/AniShift/pull/30), [#32](https://github.com/MattyMroz/AniShift/pull/32) |
| [Etap 6.1](stages/stage-6.1-shared-text-primitives.md) | Granice Unicode i grafemy dla translation/TTS | zrobione | [#28](https://github.com/MattyMroz/AniShift/pull/28) |
| [Etap 7](stages/stage-7-requirements.md), [plan](stages/stage-7-plan.md), [E2E](stages/stage-7-assembly-e2e.md) | Składanie players/MKV/MP4, compose i pełny pipeline | zrobione | [#33](https://github.com/MattyMroz/AniShift/pull/33) |
| [Etap 8](stages/stage-8-requirements.md), [plan](stages/stage-8-binary-distribution.md) | Launcher Windows, audyt legacy i zamknięcie roadmapy | zrobione | [#35](https://github.com/MattyMroz/AniShift/pull/35), [#36](https://github.com/MattyMroz/AniShift/pull/36), [#37](https://github.com/MattyMroz/AniShift/pull/37) |
| [Etap 9](stages/stage-9-requirements.md), [interfejs](stages/stage-9-interface-requirements.md), [plan](stages/stage-9-plan.md) | Model artefaktów, scheduler i AppService; propozycja Textual | zrobione: rdzeń; porzucone: Textual (historyczne issue #38) | [#39](https://github.com/MattyMroz/AniShift/pull/39), [#41](https://github.com/MattyMroz/AniShift/pull/41) |
| [textual-tui/](textual-tui/) | Etap 10: Palantir, katalog modeli, usunięcie pipeline i Textual TUI | zrobione: wspólny rdzeń; porzucone: interfejs Textual (snapshot na `archive/textual-tui`) | [#41](https://github.com/MattyMroz/AniShift/pull/41) |
| [plain-cli/](plain-cli/) | Obecny frontend Prompt Toolkit | zrobione | [#41](https://github.com/MattyMroz/AniShift/pull/41) |
| [reliability-audit/](reliability-audit/) | Audyt niezawodności, hardening i terminal polish | zrobione; dalszy odbiór i kwalifikacja odłożone w ideas.md | [#41](https://github.com/MattyMroz/AniShift/pull/41), [#50](https://github.com/MattyMroz/AniShift/pull/50) |
| [llm-translation/](llm-translation/) | Tłumaczenie LLM i przejście z JSON na numerowane linie | zrobione | — |
| [automation/](automation/) | Pierwszy pakiet automatyzacji | zastąpione przez lokalną automatyzację | — |
| [local-automation-v1/](local-automation-v1/) | Watch, wyszukiwanie, pobieranie i subskrypcje | zrobione; dalszy zakres zastąpiony przez etap 06 i pozyskiwanie | [#51](https://github.com/MattyMroz/AniShift/pull/51) |
| [local-automation-06/](local-automation-06/) | Manual, Auto i subskrypcje — etap 06 | zrobione | [#56](https://github.com/MattyMroz/AniShift/pull/56) |
| [local-automation-2/](local-automation-2/) | Foldery zadaniowe i dalszy model lokalnej pracy | zastąpione przez etap 06 i pozyskiwanie | [#56](https://github.com/MattyMroz/AniShift/pull/56), [#59](https://github.com/MattyMroz/AniShift/pull/59) |
| [acquisition/](acquisition/) | Katalog modeli, wybór odcinka, pobieranie, subskrypcje i algorytm E00–A1 | zrobione na stosie; E6/E4/E5 odłożone w ideas.md | [#57](https://github.com/MattyMroz/AniShift/pull/57), [#59](https://github.com/MattyMroz/AniShift/pull/59) |
| [tui-unify/](tui-unify/) | Ujednolicenie czterech zakładek panelu | zrobione na stosie; dalsze pomysły odłożone w ideas.md | [#59](https://github.com/MattyMroz/AniShift/pull/59) |
| [reports/](reports/) | Raport implementacji TTS i audio z etapu 6 | zrobione | — |

Obowiązujący [manifest zapisu stanu panelu](../reference/panel-state-persistence.md)
i [procedura regresji H1 (§10.6)](../reference/episode-identity-integration.md#106-zasada-regresji)
leżą w `reference/`, razem z [materiałem do przyszłego layoutu napisów](../reference/subtitle-layout-engine.md).

## Kontekst dawnego indeksu etapów

Źródło historyczne dla etapów 1–8: [plan-anishift.md](stages/plan-anishift.md).
Wzorce: [architektura MangaShift](../reference/mangashift-architecture/).
Dawne zasady wspólne: recykling MangaShift 1:1, KISS/YAGNI, rejestr silników
tylko w tts/translation/llm, fasady sync, zero kodu poza planem etapu.

```text
1 → 2 → 2.5 → 3 → 4 → 5 (llm)
                      └→ 6 (tts+audio) → 6.1 (text) → 7 (e2e) → 8 (closure) → 9 (product/UI model) → 10 (TUI rewrite)
```

Etapy 5 i 6 mogły iść równolegle. Etap 9 następował po zamknięciu starej roadmapy
w etapie 8. Etap 10 przepisał odrzuconą warstwę TUI etapu 9, po czym również jego
interfejs graficzny porzucono. Obecny frontend to Prompt Toolkit.

Dawne reguły etapów (kontekst historyczny):

- Każdy etap kończy się działającą aplikacją, bez częściowego rezultatu.
- Trwałe produkty powstają obok źródła w `workspace/`; dane robocze runu trafiają do `workspace/temp/` i są sprzątane po zakończeniu.
- Domenowe configi: dataclass `slots=True`, wymagany `engine_id` bez defaultu; default trzyma panel (`config/settings.json`).
- Błędy domenowe z `anishift/errors.py`, nigdy `sys.exit()` ani goły traceback do użytkownika.
- Dawna nietykalność `utils/` została zniesiona; standaryzację opisywało issue #21.

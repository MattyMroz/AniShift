# plany etapów AniShift — spis

> źródło prawdy: `docs/plan-anishift.md` (FINAL, 2026-07-12). wzorce: `mangashift-architecture-ref/` (engine-factory-standard, engine-standard, naming-glossary).
> zasady wspólne: recykling MangaShift 1:1, prostota (KISS/YAGNI), rejestr silników TYLKO w tts/translation/llm, fasady sync, zero kodu poza planem etapu.

| etap | plik | cel (1 zdanie) | zależy od |
|---|---|---|---|
| 1 | [etap-1-fundament.md](etap-1-fundament.md) | **ZROBIONE** — pakiet `anishift` z configiem, workspace, platform i doktorem, uruchamialny przez `uv run anishift`. | — |
| 2 | [etap-2-shell.md](etap-2-shell.md) | interaktywny shell (banner + REPL prompt_toolkit + `/komendy` + `/settings`) jako pusta skorupa bez pipeline. | 1 |
| 2.5 | [etap-2.5-pobieracz-binarek-v2.md](etap-2.5-pobieracz-binarek-v2.md) | pobieracz zasobów zewnętrznych: manifest + leniwe pobieranie mkvtoolnix/ffmpeg na żądanie (`ensure_binary`) + `anishift setup`/`/setup` do pobrania z góry. | 2 |
| 3 | [etap-3-ekstrakcja-refaktor.md](etap-3-ekstrakcja-refaktor.md) | Enter zaczyna działać: MKV z `workspace/` → wyciągnięte ścieżki + napisy przerobione do SRT (kroki 1-2 runnera). | 1, 2, 2.5 |
| 4 | [etap-4-tlumaczenie.md](etap-4-tlumaczenie.md) | pierwszy rejestr silników (google + deepl) z dedupem i czyszczeniem znaczników — krok 3 runnera. | 3 |
| 5 | [etap-5-llm.md](etap-5-llm.md) | serwis llm (6 dostawców, recykling 1:1 z MangaShift) + trzeci silnik tłumaczenia `llm` + opcjonalna korekta napisów. | 4 |
| 6 | [etap-6-tts-audio.md](etap-6-tts-audio.md) | rozbicie god-files TTS na rejestr 5 silników + osobny tor audio ffmpeg — krok 4 runnera. | 4 (równolegle z 5) |
| 7 | [etap-7-skladanie-e2e.md](etap-7-skladanie-e2e.md) | składanie wyniku (players / merge mkv / burn mp4) i pełne e2e od Enter do gotowego pliku. | 6 |
| 8 | [etap-8-dystrybucja-binarek.md](etap-8-dystrybucja-binarek.md) | migracja danych usera i wyburzenie starego kodu (dystrybucja binarek przeniesiona do etapu 2.5). | 7 |

## graf zależności

```text
1 → 2 → 2.5 → 3 → 4 → 5 (llm)
                      └→ 6 (tts+audio) → 7 (e2e) → 8 (migracja+kasacje)
```

etapy 5 i 6 mogą iść równolegle (tts nie korzysta z llm). etap 8 dopiero gdy 7 ma parytet ze starym kodem — nic starego nie kasujemy wcześniej.

## reguły obowiązujące w każdym etapie

- każdy etap kończy się działającą apką (zero half-done).
- pliki pośrednie powstają obok MKV w `workspace/`; robocze w `workspace/tmp/`; wyniki w `output/` tylko gdy włączone w `/settings`.
- domenowe configi: dataclass `slots=True`, wymagany `engine_id` bez defaultu — default trzyma panel (`config/settings.json`).
- błędy domenowe (podklasy `anishift/errors.py`), nigdy `sys.exit()` ani goły traceback do usera.
- `utils/` nietykalne — nowe rzeczy tylko jako nowe pliki obok.

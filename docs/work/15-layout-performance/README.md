# 15-layout-performance

Wydajność układu linii dialogu: `layout_dialogue` rośnie ponadkwadratowo z liczbą słów (320 słów: 5,5 s / 42 s; 1000 słów: ponad 1000 s i 2,2 GB), więc uszkodzony plik napisów może zawiesić rezydenta. Realne linie dialogu mają najwyżej 19 słów i liczą się w 0,04 s.

Status: diagnoza i plan gotowe (2026-10-25), bez zmian w kodzie. Czeka na akceptację właściciela i wykonanie.

| Plik | Treść |
|---|---|
| [diagnosis.md](diagnosis.md) | pomiary n = 19…640 w obu trybach, `cProfile` n = 160, przyczyna z plikiem i linią, górna granica korpusu (101 plików, 22 439 linii dialogu) |
| [plan.md](plan.md) | twardy limit `MAX_DIALOGUE_WORDS = 50` na wejściu `layout_dialogue`, fallback nierozbity bez `{\q2}`, licznik `dialogue_too_long`, testy, bramki, branch `work/subtitles/03-dialogue-word-limit`, commit `perf(subtitles): …` |

## Dowody poza repo

Skrypty i surowe wyniki leżą w scratchpadzie sesji diagnosty (katalog tymczasowy, może zniknąć); kluczowe liczby są przepisane do `diagnosis.md`:

`C:\Users\MATTYM~1\AppData\Local\Temp\claude\c--Users-MattyMroz-Desktop-PROJECTS-AniShift\b1c6e9d7-f377-43d2-802f-da71c0f1b1b3\scratchpad\perf\`

| Plik | Co robi |
|---|---|
| `bench.py` | czasy `layout_dialogue` dla podanych n, z profilem i bez; `prof <n> profile\|none` daje `cProfile` |
| `measure_build.py` | czas i pamięć samej tabeli par w `_measure` |
| `corpus_lines.py` | skan `workspace/ready` (tylko odczyt): najdłuższe linie dialogu i szyldów, histogram |
| `identity.py` | dowód tożsamości: `layout_translated` na korpusie z oryginalnym i z ograniczonym `layout_dialogue` (monkeypatch w pamięci), 0 różnic; tryb `pathological` mierzy fallback dla 1000 i 5000 słów |
| `bench_notrace.md`, `bench_limits.md`, `bench_640.md`, `bench_out.md` (z `tracemalloc`), `measure_build_out.md`, `corpus_out.md`, `identity_out.md`, `pathological_out.md`, `prof160_profile.txt`, `prof160_none.txt` | surowe wyniki |

Uruchomienie z katalogu repo: `PYTHONPATH=<katalog perf> uv run python <katalog perf>\<skrypt>.py …` (`identity.py` i `measure_build.py` importują `bench`).

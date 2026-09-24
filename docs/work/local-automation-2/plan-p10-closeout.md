# Plan: domknięcie P10 i wejście w P11

Status: **READY do wykonania**
Specyfikacja: [spec.md](spec.md)
Plan workstreamu: [plan.md](plan.md)
Gałąź: `work/local-automation/06-efficiency`
Data: 2026-09-14

Ten plan zamyka jeden rezultat: **faza P10 zacommitowana zgodnie z siedmioma punktami `plan.md` i próbami rozstrzygającymi z jego linii 411.** Nie obejmuje P11–P18; ich kolejność i warunki wejścia są na końcu jako mapa, nie jako zakres tej pracy.

## 1. Sprawdzony stan wyjściowy

Zweryfikowane uruchomieniem, nie z pamięci.

**Zacommitowane:**

| Commit | Zakres |
|---|---|
| `d110852` | ponawianie relokacji do `ready/`, gdy czytelnik trzyma plik |
| `dfcfcf3` | całe P09: foldery zadaniowe, `workflows.py`, migracja stanu 1→2 |
| `8b2190d` | zapis faktów P09 w `AGENTS.md` |

**Niezacommitowane:** 26 zmienionych plików, +1687/−187, dwa nowe pliki testów (`tests/application/test_readiness.py`, `tests/application/test_translate_only.py`).

**Bramki:** wszystkie pięć zielone, `4210 passed, 15 skipped`. 15 pominięć to baseline: 9 sieciowych, 6 bramek symlink/junction na nieuprzywilejowanym Windows.

**Znane flaki zależne od obciążenia pod `-n 19`, wszystkie w obszarze gniazd rezydenta/panelu, żadna w terenie P10:**

- `tests/cli/test_resident.py::test_two_racing_residents_leave_exactly_one_owner`
- `tests/application/test_scheduler.py::test_strict_natural_keeps_later_durable_staging_private`
- `tests/cli/test_interactive_state.py::test_download_view_distinguishes_saved_orders_from_measured_progress`

Nie podnosić żadnego timeoutu, żeby je uciszyć.

## 2. Luka

W drzewie znajduje się mechanizm, którego `plan.md` P10 nie zamawia i którego specyfikacja zabrania: plik nazwany jak produkt AniShift, leżący w miejscu wejściowym bez pasującego źródła, jest promowany na nowe źródło i uruchamia pracę.

Dowody przeciw temu mechanizmowi:

- **AC-018** — własna publikacja i dwa zdarzenia plikowe nie tworzą nowego zlecenia.
- **R-038**, spec linia 72 — konwencje `.pl`, `.spoken.pl`, `.displayed.pl` pozostają nazwami produktów AniShift.
- **R-034**, spec linia 76 — plik w złym miejscu pozostaje nienaruszony z jedną wskazówką właściwego folderu; ostrzeżenie `ORPHAN_ARTIFACT` jest tu zachowaniem kontraktowym, nie defektem.
- **D-016**, plan linia 105 — poświadczenie produktu i wybór pliku użytkownika mają odrębne pochodzenie.

Trzy niezależne review potwierdziły przy okazji, że mechanizm jest niestabilny: przesuwa tożsamość grup przy niezmienionych ścieżkach i po usunięciu źródła zleca tłumaczenie własnego wyniku. Naprawa nie jest potrzebna, bo funkcja nie ma podstawy w kontrakcie.

## 3. Stan docelowy

Discovery klasyfikuje plik dokładnie jak przed tym mechanizmem: nazwa produktu oznacza produkt, plik bez grupy daje jedno ostrzeżenie. Pozostałe zachowania P10 zostają. Faza zacommitowana na gałęzi feature.

## 4. Zakres

**In scope:** R1–R4 poniżej.

**Out of scope:** P11–P18; `products.py`; `paths.py`; schemat stanu; wygląd interfejsu.

**Forbidden:**

- Wciąganie stanu (`ReadyGroup`, dziennik publikacji) do `discovery.py`. D-016 mówi o odrębnym pochodzeniu, a zasilanie `ReadyGroup` należy do P12.
- Feature flags (`plan.md` linia 18).
- Podnoszenie timeoutów i osłabianie asercji.
- `git push`, PR, issues, tagi. Commity lokalne na gałęzi feature są w porządku.
- Zwykłe komentarze w kodzie. Dopuszczalne wyłącznie nagłówki `# ── ... ───` i dyrektywy `# noqa`, `# type:`, `# pragma`.

**Escalation:** jeżeli usunięcie mechanizmu impulsów wywali test, który nie dotyczy promowania nazwy produktu na źródło, zatrzymać się i zgłosić — oznacza to, że mechanizm został wpleciony głębiej, niż wynika z review.

## 5. Kroki

### R1. Usunąć mechanizm impulsów

**Plik:** `anishift/application/discovery.py`.

Usunąć `_resolved_impulses`, `_impulse_candidates`, `_impulse_order`, `_impulse_source`, `_names_own_product` oraz ich wywołanie w `_discovered`. `classify_artifact(path, route)` wraca do roli jedynej klasyfikacji pliku. Rozstrzygnąć, czy `_classify_source` ma dalszą rację bytu, czy wraca do `classify_artifact`.

Publiczny `changed_group_stems` traci połowę impulsową i zostaje wyłącznie ze świadomością trasy — patrz R2.

**Testy do usunięcia:** przypadki zakładające, że samotny plik o nazwie produktu tworzy grupę (w `tests/application/test_discovery.py` i `tests/application/test_automation.py`).

**Testy do przywrócenia:** `test_a_translated_text_alone_only_warns` oraz `test_final_container_never_creates_source_group`. Zostały przepisane pod ten mechanizm, a kodowały kontrakt.

**Sprawdzenie:** samotny `translate/Foo.pl.txt` nie tworzy grupy i daje jedno ostrzeżenie; `Film.mkv` obok `Film.pl.mkv` nadal rozpoznaje drugi jako gotowy produkt i nie planuje pracy.

### R2. Zachować to, co naprawiało realny błąd

**Plik:** `anishift/application/automation.py`.

`_invalidate_changed_inputs` zachowuje świadomość trasy przy wyznaczaniu rdzenia nazwy — bez niej `cover/Episode.png` nie unieważniał niczego, co jest defektem względem R-004/AC-005. Usunąć tylko część wynikającą z impulsów.

`_fresh_sources` i `_file_origin` wracają do filtra `is_derived_product`. Po R1 własna publikacja znów jest jedynym przypadkiem, który ten filtr miał odsiewać, więc uzasadnienie jego zniesienia przestaje istnieć.

**Sprawdzenie:** zmiana `cover/Episode.png` unieważnia podgląd właściwej grupy; własna publikacja nie dostaje pochodzenia `USER`.

### R3. Dopisać brakującą próbę rozstrzygającą

`plan.md` linia 411 wymaga próby z **częściowo skopiowanym sidecarem**. Obecne pokrycie używa pustego pliku albo zamockowanego uchwytu, co nie jest tym samym zjawiskiem. Test ma odtworzyć plik rosnący między skanami i pokazać, że grupa czeka, zamiast wejść do wykonania.

### R4. Bramki, review, commit

Z katalogu głównego, nigdy na podkatalogu:

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest -n 19 --tb=short
```

Wszystkie pięć musi przejść. Przed commitem mechaniczny skan każdego zmienionego pliku: zero zwykłych komentarzy, zero CRLF. Świeże review całości P10, potem commit ze scope z listy w `scripts/hooks/check_commit_msg.py`.

## 6. Co zostaje w drzewie bez zmian

Potwierdzone przez review jako zgodne z kontraktem:

| Zachowanie | Kontrakt |
|---|---|
| rozpoznawanie źródła głównego według miejsca, ID grup zachowane | P10.1, D-016 |
| predykaty gotowości per cel, jeden stabilny powód oczekiwania | P10.2 |
| inspection bez `_catalog_video_duration` bez wideo, walidacja bajtów | P10.3 |
| produkt translated TXT, źródło nigdy nie podmienione własnym wynikiem | P10.4 |
| translate-only TXT→TXT, SRT→SRT, ASS/SSA→ASS, bez TTS w grafie | P10.5, R-034 |
| akapity, kolejność i kompletność w `TranslationTaskHandler` | P10.6, AC-049 |
| obowiązkowa para w `subs`, także w Ręcznym | P10.7, R-033, AC-047 |
| polskie dialogi przed angielskimi, znaki/forced nie udają dialogów | R-038 |
| recepty folderów docierają do Auto i do podglądu | R-037, D-017 |
| odrzucanie pustego produktu tekstowego przy publikacji | I-002 |
| szpiedzy TTS i tłumaczenia z licznikiem zero dla translate-only | plan linia 411 |

SSA jest domknięte poza discovery: `discovery.py` `SOURCE_SUBTITLE_FORMATS`, `services/subtitles/service.py` `_SUFFIX_KIND` i `inspection.py` mapują `.ssa` na rodzinę ASS. D-016 linia 107 nie ma tu długu.

## 7. Długi przeniesione do dalszych faz

- **P12:** `inspection._inspect_non_video` nigdy nie oznacza `FINAL_MKV`/`FINAL_MP4` jako `READY`, więc gotowy kontener obok źródła byłby komponowany w każdym cyklu. Defekt sprzed tego workstreamu, dotyczy rozpoznawania produktów.
- **P12:** zasilanie `ReadyGroup` przy udanej publikacji oraz `ready.py::_destinations` klasyfikujące domyślną trasą.
- **P14/P18:** podłączenie `preflight` do startu rezydenta — `refused_names` z `AppContext.workspace_conflicts`, `occupied_names` z `occupied_task_dirs`.
- **P15:** czytanie `PendingDeletion.files` jako odcisku pliku.
- **P13:** bogatsza tożsamość pliku w `complete_files`.
- **Infrastruktura testów:** trzy flaki z sekcji 1 zależne od obciążenia. Osobna decyzja, nie łatanie timeoutem.

## 8. Mapa dalszych faz

Kolejność jest wymuszona przez `plan.md` sekcję 6; każda faza korzysta ze sprawdzonego wyniku poprzednich.

| Faza | Rezultat | Warunek wejścia |
|---|---|---|
| P11 | audiobook z TXT/SRT przez istniejące TTS i audio, bez fikcyjnego wideo | P10 zacommitowane |
| P12 | `cover` i trwały zestaw wynikowy | P11 |
| P13 | zakres subskrypcji i postęp pobrania na poziomie materiału | P12 |
| P14 | stałe czuwanie, globalna pauza, pełne zakończenie | P13 |
| P15 | Biblioteka, szczegóły, bezpieczny Kosz | P14 |
| P16 | nowa nawigacja z istniejących kontrolerów | P15, odbiór wizualny właściciela |
| P17 | recepty, historia, zegary, końcowe spięcie | P16 |
| P18 | próby całego przepływu i kontrolowane przełączenie | P17, odbiór wizualny właściciela |

P16 i P18 mają punkt kontrolny człowieka: wygląd i ergonomię ocenia właściciel w terminalu, nie status dokumentu.

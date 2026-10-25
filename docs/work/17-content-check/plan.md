---
kind: plan
status: draft
baseline: main @ 4365a51
created: 2026-10-25
---

# Plan: kontrola zawartości po pobraniu (E4)

Kontrakt: [specification.md](specification.md). Dowody stanu: [current-state.md](current-state.md). Plan zakłada rekomendacje D1–D8 ze specyfikacji; inna decyzja właściciela w D1, D2, D3, D6 lub D8 wymaga aktualizacji planu przed fazą, której dotyczy.

## Cel

Po pobraniu odcinka (subskrypcja i D z listy) kontrola przed nazwaniem wyznacza werdykt napisów `polskie` / `obce` / `brak` jedną regułą roli ścieżki; `brak` odrzuca plik i uruchamia istniejącą (subskrypcja) albo nową jednorazową (pobranie ręczne) zamianę wydania. Planner używa tej samej reguły.

## Warunki końcowe

- [ ] `MediaTrack` niesie liczbę zdarzeń napisów z MKV i MP4.
- [ ] Jedna reguła roli w `selection.py`; planner nie ma własnego wzorca ani flagi `forced` jako dowodu rozstrzygającego.
- [ ] Próba subskrypcji bez napisów dialogowych jest odrzucana i następna próba bierze inne wydanie w budżecie 3 prób.
- [ ] Pobranie ręczne bez napisów dialogowych dostaje jedną automatyczną zamianę; druga porażka albo brak kandydata daje widoczny problem.
- [ ] Stan w schemacie 6 z migracją i kopią; restart nie dubluje zamiany.
- [ ] Bramki zielone; H4 zaliczone przez właściciela.

## Nie-cel

Polskie napisy z zewnętrznych źródeł (`docs/ideas.md` §1.5), wykrywanie błędnego tagu języka, sprzątanie legacy `services/extraction/tracks.py`.

## Authority i baseline

| Źródło | Rola |
|---|---|
| `specification.md` (ten katalog) | wymagania i decyzje |
| `docs/work/08-acquisition/specification.md` U-07, U-08, R-07, I-08 | wymagania nadrzędne |
| `docs/work/08-acquisition/plans/12-a1-acquisition-algorithm.md` §5.12 | punkt podpięcia `replacement` |
| `docs/work/08-acquisition/plans/06-e1-subscription-flow.md` §3.3, przejścia 13–18 | bramka przyjęcia, brak H2 dla zleceń ręcznych |
| `AGENTS.md`, `anishift/AGENTS.md`, `anishift/application/AGENTS.md`, `anishift/services/media/AGENTS.md`, `anishift/services/extraction/AGENTS.md`, `tests/AGENTS.md` | reguły repo |
| `current-state.md` | stan kodu i danych |

**Baseline:** `main` @ `4365a51`, drzewo czyste.

**Znane wcześniejsze failures:** brak znanych; F0 je ustala.

## Istniejące rozwiązania do reuse

| Element | Ścieżka / symbol | Co wykorzystać | Ograniczenie |
|---|---|---|---|
| Kontrola przed nazwaniem | `automation.py` `_passed_check`, `_check_episode`, `_identify`, `_reject_attempt` | jedno miejsce odczytu sondy i odrzucenia | dziś tylko subskrypcja |
| Zamknięcie próby i kolejna próba | `subscription_targets.settle_target`, `after_close`, `excluded`; `automation._settled_target`, `_attempt_fact`, `_closed_attempt` | ścieżka subskrypcji bez zmian logiki | powód odrzucenia to `rejected` + `verification` |
| Reguła zamiany | `subscription_choice.replacement`, `choice_candidate` | wybór zamiany ręcznej | wejście `ChoiceCandidate` |
| Wyszukiwanie odcinka | `AcquisitionService.search_episode`, `automation._download_episode` (wzorzec puli I/O) | świeże kandydaty | tylko w puli I/O |
| Przyjęcie | `automation._admit_episode(previous=…)`, `_replace_episode_scope`, `_replacement_ready` | zamiana z poprzednikiem | `previous` musi być ostatnim przyjęciem klucza |
| Teksty powodów | `episode_commands._REJECTIONS`, `cli/interactive/anime_texts.py` | jeden wpis na nowy powód | — |
| Rejestr decyzji | `acquisition_decisions.append_decision` + allowlista | wpis wyniku | nowe klucze trzeba dopisać do allowlisty |
| Migracja stanu | `watch_state.py` (kopie `.e2-/.e3-/.a1-migration.bak`, `_SUPPORTED_SCHEMA_VERSIONS`) | wzorzec podbicia wersji | — |
| Fake sondy w testach | `tests/application/fakes.py` `FakeMediaProbe`, `_Probe` w `test_subscription_attempts.py`, `test_subscription_scenarios.py` | scenariusze ownera | dziś zwracają katalog bez napisów (patrz Impact scan) |

## Zakres

### In scope

Wymagania 1–19 specyfikacji, migracja 5 → 6, teksty powodów, dokumentacja w zmienianych obszarach.

### Out of scope

Pozycje „Poza zakresem” specyfikacji; zmiany UI poza tekstem powodu; zmiana ostrzeżenia `subtitle_dialogue_missing` dla plików wrzuconych ręcznie.

### Forbidden

- zmiana rankingu, `usable`, `admissible`, `replacement`, `choice_key`, `MAX_ATTEMPTS`, czekania na PL;
- nowa zależność (`uv add`), parsowanie ASS lub ekstrakcja w kontroli;
- wywołanie sieci lub `search_episode` na wątku ownera;
- osłabienie istniejących testów; zmiana fake sondy, która ukrywa regresję (dozwolone: dodanie ścieżki dialogowej jako domyślnej zawartości fake'a, patrz F2);
- worktree i `uv --active`; commit na `main`.

### Dozwolone decyzje lokalne

Nazwy prywatnych helperów, dokładne nazwy testów przy zachowaniu treści scenariusza, rozmieszczenie stałych w `selection.py`, kolejność commitów w obrębie fazy.

### Zatrzymaj się i wróć po decyzję, gdy

- F0 pokaże, że żadne pole `mkvmerge -J` nie odtwarza `NUMBER_OF_FRAMES` dla wszystkich ścieżek napisów;
- odrzucone przyjęcie ręczne nie da się zamknąć istniejącą drogą `_closed_attempt`/`_replace_episode_scope` bez nowego stanu transferu;
- zmiana reguły w plannerze zmienia wynik któregokolwiek istniejącego testu plannera poza przypadkiem `forced` przy znanym tempie dialogu;
- migracja wymaga zmiany danych, nie tylko wersji.

## Kontekst do przeczytania

| Kolejność | Źródło | Po co | Zakres |
|---|---|---|---|
| 1 | `.agents/skills/simple/SKILL.md`, `.agents/skills/coding/SKILL.md`, `references/python.md`, `comments-docstrings.md`, `testing.md` | standard pracy | full |
| 2 | `AGENTS.md` (root, `anishift/`, `application/`, `services/media/`, `services/extraction/`, `tests/`) | reguły i pułapki | full |
| 3 | `specification.md`, `current-state.md` | kontrakt i stan | full |
| 4 | `automation.py` | `_publish_episode`…`_reject_attempt` (`:6579-6798`), `_download_episode`, `_admit_download_offer`, `_admit_episode`, `_admission_refusal` (`:5663-5870`), `_attempt_notice` (`:4647`), `_settled_target` (`:4447`), `_attempt_fact`, `_closed_attempt` (`:8532-8620`) | symbols |
| 5 | `control.py` `EpisodeAssignment` (`:450-533`); `watch_state.py` wersjonowanie i migracje | inwariant i schemat | symbols |
| 6 | `planner.py` `_select_embedded_track`, `_is_non_dialogue`, `_track_rank` | wspólna reguła | symbols |
| 7 | `services/media/{types,mkv,mp4}.py`, `services/extraction/service.py` `_parse_track` | liczba zdarzeń | full |

## Impact scan

| Kontrakt / subsystem | Ryzyko | Obowiązek regresyjny |
|---|---|---|
| Fake sondy zwracają katalog tylko z wideo (`test_subscription_attempts.py:80`, `test_subscription_scenarios.py`, `fakes.py`) | po E4 każda próba w tych testach dostanie werdykt `brak` i zostanie odrzucona | domyślny katalog fake'a dostaje tekstową ścieżkę dialogową z liczbą zdarzeń; przypadki `video=False` bez zmian; pełny `tests/application` zielony |
| Planner (`test_planner.py`, `test_planner_properties.py`) | wspólna reguła zmienia degradację | testy bez liczby zdarzeń zachowują wynik (reguła zapasowa); nowy test: `forced` z tempem dialogu nie jest degradowany |
| `MediaTrack` (pozycyjne konstruktory w testach) | nowe pole psuje wywołania | pole na końcu z wartością domyślną `None` |
| Inwariant `EpisodeAssignment._check_attempt` | przyjęcie ręczne z wynikiem kontroli dziś niedozwolone | testy `test_watch_state.py` na obu źródłach; starsze stany bez `verification` dla ręcznych wczytują się |
| Schemat stanu | starszy kod nie zna nowej semantyki | wersja 6, migracja, kopia, test na kopii stanu |
| `_reserve_publication` wymaga kontroli tylko dla subskrypcji | ręczne nazwanie po kontroli | ręczne przyjęcie z `skipped` nadal publikuje (K-09) |
| Rejestr decyzji (allowlista) | nowy klucz odrzucony cicho | test zapisu wpisu z nowym kluczem |
| Inspekcja workspace (`WorkspaceInspector` cache) | nowe pole w katalogu | test parsowania; cache bez zmian |

## Target design

### Odpowiedzialności

| Element | Odpowiada za | Nie odpowiada za |
|---|---|---|
| `services/media` | liczba zdarzeń ścieżki w `MediaTrack.entries` (`int \| None`) | rola ścieżki |
| `application/selection.py` | `subtitle_role(track, duration_us) -> (rola, niepewna)` i `subtitle_content(tracks, duration_us, *, companion) -> (werdykt, niepewny)`; stałe progów D1 i wzorzec tytułu | I/O, decyzja o zamianie |
| `application/planner.py` | wybór ścieżki z degradacją według `subtitle_role` | własny wzorzec |
| `application/download_verification.py` | `MeasuredMedia` z werdyktem napisów; stała powodu `NO_DIALOGUE_SUBTITLES` | kontrola czasu bez zmian |
| `AutomationOwner` | odrzucenie przed nazwaniem dla obu źródeł; zamiana ręczna i jej limit; recovery | ranking |

### Reguła roli (D1)

```text
entries = track.entries (None, gdy brak albo 0)
rate = entries / (duration_us / 60e6), gdy entries i duration_us > 0
rate < 2.5            -> szyldy, pewna
rate >= 5.0           -> dialog, pewna
inaczej               -> szyldy, gdy forced albo tytuł ~ sign|song|forced; inaczej dialog; niepewna
```

Werdykt pliku: ścieżki tekstowe (`subtitle_format in {ass, srt}`) w roli dialog; jest `pol` → `polskie`; jest inna → `obce`; towarzysz `ass`/`srt` w zestawie → co najmniej `obce`; inaczej `brak`. Niepewny, gdy rozstrzygająca ścieżka ma rolę niepewną.

### Przepływ

```text
zestaw kompletny
-> _check_basis: subskrypcja (czas + napisy) albo ręczne (tylko napisy, ExpectedEpisode(None))
-> _identify (jedna sonda) -> MeasuredMedia(..., subtitles=werdykt)
-> brak obrazu albo werdykt brak -> reject:<powód>, niezależnie od record_only
-> subskrypcja: istniejące zamknięcie próby i następna próba
-> ręczne: zapis reject + kolejka zamiany w puli I/O
   -> search_episode -> choice_candidate -> replacement(excluded = hashe przyjęć klucza)
   -> owner: _admit_episode(command_id = "content-replace:<admission_id>", previous = odrzucone)
   -> brak kandydata albo limit -> problem SUBTITLES_MISSING w statusie odcinka
```

Limit ręczny (D2): zamiana tylko, gdy `previous_admission_id` odrzuconego przyjęcia nie wskazuje przyjęcia z `reject:no_dialogue_subtitles`.

Recovery: przy starcie ownera i po każdym zapisie odrzucenia owner kolejkuje zamianę dla każdego ręcznego przyjęcia z `reject:no_dialogue_subtitles`, które nie ma następcy (`previous_admission_id` innego przyjęcia) i spełnia limit. Deterministyczny `command_id` i receipt chronią przed drugim przyjęciem.

### Model danych

```text
MediaTrack.entries: int | None = None      # >= 0, tylko napisy
MeasuredMedia.subtitles: SubtitleContent | None   # alias Literal["polish", "foreign", "none"] w selection.py; None = nie badano
MeasuredMedia.subtitles_uncertain: bool = False
EpisodeAssignment.verification             # dozwolone także dla AdmissionSource.MANUAL
WATCH_STATE_SCHEMA_VERSION = 6             # migracja 5 -> 6 bez zmiany danych
kopia przed pierwszym zapisem: state.json.e4-migration.bak
decisions.jsonl: kind "check", nowe klucze "subtitles", "subtitles_uncertain"; kind "replacement" dla zamiany ręcznej
EpisodeReason.SUBTITLES_MISSING = "subtitles_missing"
```

Inwarianty `EpisodeAssignment` po zmianie: wynik kontroli może mieć każde przyjęcie; opublikowana próba subskrypcji nadal wymaga zaliczonej kontroli; opublikowane przyjęcie ręczne może nie mieć kontroli (przyjęcia sprzed E4, `skipped`), ale nigdy nie ma `reject:`; `verified_stamp` jak dziś.

### Edge cases i failures

| Przypadek | Oczekiwane zachowanie | Dowód |
|---|---|---|
| Jedyna ścieżka pełna z `forced=1` (Dark Summoner) | dialog, werdykt `obce`, bez ostrzeżenia planera | unit |
| Szyldy z tytułem `English` i `forced=1`, 9 zdarzeń (Judas) | szyldy | unit |
| `Forced`, 36 zdarzeń / 23,7 min | szyldy | unit |
| Tajski AMZN, 188 / 23,6 min | dialog | unit |
| PL `Forced` 10 + PL bez tytułu 296 (Sparks) | `polskie`, wybrana PL pełna | unit planera |
| Brak liczby zdarzeń, tytuł `Signs & Songs` | szyldy, niepewna | unit |
| Brak liczby, bez słów i flagi | dialog, niepewna | unit |
| `entries == 0` | jak brak liczby | unit |
| Tempo 3,0/min, bez słów | dialog, niepewna | unit |
| Czas kontenera 0 | jak brak liczby | unit |
| Tylko napisy obrazkowe | `brak` | unit |
| Brak ścieżek napisów | `brak` | unit |
| Towarzysz `.ass` w zestawie, MKV bez napisów | `obce`, bez odrzucenia | integration |
| Kontrola niewykonana | publikacja bez werdyktu | integration (istniejące + ręczne) |
| Subskrypcja: 1. wydanie bez napisów, 2. z napisami | 2. przyjęte, cel spełniony po publikacji | integration |
| Subskrypcja: 3 wydania bez napisów | `EXHAUSTED`, powiadomienie z powodem | integration |
| Ręczne: 1. bez napisów, zamiana z napisami | jedna zamiana, publikacja zamiany | integration |
| Ręczne: obie bez napisów | problem `SUBTITLES_MISSING`, brak trzeciego pobrania | integration |
| Ręczne: brak kandydata zamiany | problem `SUBTITLES_MISSING` | integration |
| Restart między odrzuceniem a przyjęciem zamiany | dokładnie jedno przyjęcie zamiany | integration |
| Ręczne „Pobierz ponownie” po dwóch porażkach i znów brak | bez automatycznej zamiany (D2) | integration |
| Wczytanie stanu v5 | migracja do 6, kopia `.e4-migration.bak`, dane bez zmian | integration |

## Mapa plików

| Ścieżka | Operacja | Rola zmiany |
|---|---|---|
| `anishift/services/media/types.py` | MODIFY | `MediaTrack.entries` + walidacja `>= 0` i tylko dla napisów |
| `anishift/services/media/mkv.py` | MODIFY | mapowanie liczby zdarzeń (pole wybrane w F0) |
| `anishift/services/extraction/types.py`, `service.py` | MODIFY tylko gdy F0 wybierze tag statystyk | odczyt pola do `TrackInfo` |
| `anishift/services/media/mp4.py` | MODIFY | `nb_frames` strumienia napisów, `None` gdy brak lub nienumeryczne |
| `anishift/application/selection.py` | MODIFY | reguła roli i werdykt, stałe D1 |
| `anishift/application/planner.py` | MODIFY | degradacja przez `selection.subtitle_role`; usunięte `_NON_DIALOGUE_SUBTITLE_NAME`, `_is_non_dialogue`; `_MediaTrackView.entries` |
| `anishift/application/download_verification.py` | MODIFY | `MeasuredMedia.subtitles`, `NO_DIALOGUE_SUBTITLES`, `measured_media` liczy werdykt |
| `anishift/application/control.py` | MODIFY | inwariant `_check_attempt`, `WATCH_STATE_SCHEMA_VERSION = 6` |
| `anishift/application/watch_state.py` | MODIFY | wersja 6, migracja, kopia `.e4-migration.bak` |
| `anishift/application/automation.py` | MODIFY | `_check_basis` dla ręcznych, odrzucenie mimo `record_only`, zamiana ręczna i recovery, status `SUBTITLES_MISSING`, wpisy rejestru |
| `anishift/application/episode_commands.py` | MODIFY | `EpisodeReason.SUBTITLES_MISSING`, `_REJECTIONS["no_dialogue_subtitles"] = "brak napisów dialogowych"` |
| `anishift/application/acquisition_decisions.py` | MODIFY | allowlista `subtitles`, `subtitles_uncertain` |
| `anishift/cli/interactive/anime_texts.py` | MODIFY | etykieta kolumny Stan `SUBTITLES_MISSING`: „Brak napisów” (limit `_EPISODE_STATUS_WIDTH`); w notce istniejący `_REPEAT_HINT` „P pobierz ponownie” |
| `anishift/application/AGENTS.md`, `anishift/services/media/AGENTS.md` | MODIFY | kontrakt kontroli, schemat 6, pole `entries` |
| `docs/ideas.md`, `docs/work/08-acquisition/masterplan.md`, `docs/README.md` | MODIFY | status E4 |
| `scripts/tmp/e4_entries_check.py` | CREATE (jednorazowy, F0) | porównanie pól `mkvmerge -J` z `ffprobe`, tylko odczyt |
| `tests/services/media/test_probe_contract.py`, `tests/services/media/test_mp4.py` | MODIFY | testy pola `entries` |
| `tests/application/test_subtitle_roles.py` | CREATE | reguła roli i werdykt (`selection.py` nie ma dziś własnego pliku testów) |
| `tests/application/test_planner.py` | MODIFY | degradacja na wspólnej regule |
| `tests/application/test_download_verification.py` | MODIFY | werdykt w `measured_media` |
| `tests/application/test_subscription_attempts.py`, `test_subscription_scenarios.py`, `tests/application/fakes.py` | MODIFY | domyślna ścieżka dialogowa w fake'ach; scenariusze subskrypcji |
| `tests/application/test_content_replacement.py` | CREATE | scenariusze zamiany ręcznej |
| `tests/application/test_watch_state.py` | MODIFY | migracja 5 → 6, inwariant |
| `tests/data/mkvmerge-subtitle-counts.json` | CREATE | syntetyczny wycinek `mkvmerge -J` (bez mediów) z polem wybranym w F0 |

## Plan wykonania

Branch: `work/acquisition/05-content-check` (wzorzec `work/acquisition/<nn>-<slug>`; jeśli `05` jest zajęte, następny wolny numer). Jedna gałąź, jeden PR.

### F0 — Preflight

1. `git status` czysty, branch od `main`.
2. Bramki repo na baseline; zapisz ewentualne failures.
3. `uv run python -I scripts/tmp/e4_entries_check.py`: dla każdego MKV z `workspace/ready/` (tylko odczyt) `mkvmerge -J` i `ffprobe -show_streams`; dla każdej ścieżki napisów porównaj `NUMBER_OF_FRAMES` z `num_index_entries` i z polem tagu statystyk w JSON mkvmerge (jeśli istnieje). Wynik: liczba zgodnych / niezgodnych per pole.

**Gate:** jedno pole zgodne dla wszystkich 790 ścieżek → to pole idzie do `MediaTrack.entries` (preferencja: tag statystyk, potem `num_index_entries`). Inaczej stop i decyzja.

### F1 — Liczba zdarzeń i reguła roli

1. `MediaTrack.entries`; mapowanie MKV (pole z F0) i MP4 (`nb_frames`).
2. `selection.subtitle_role`, `selection.subtitle_content`, stałe D1 pod `# ── Constants`.
3. Planner na wspólnej regule; usunięcie kopii wzorca.

**Testy (wszystkie `@pytest.mark.unit`):**

```text
tests/services/media/test_probe_contract.py
  test_mkv_subtitle_track_carries_its_event_count
  test_mkv_subtitle_track_without_a_count_has_no_entries
  test_media_track_rejects_entries_on_audio
  test_media_track_rejects_negative_entries
tests/services/media/test_mp4.py
  test_mp4_subtitle_stream_carries_its_frame_count
  test_mp4_subtitle_stream_without_frames_has_no_entries
tests/application/test_subtitle_roles.py
  test_role_by_event_rate  [parametrize: judas_forced_english_9, forced_36, thai_amzn_188, subsplease_forced_251, short_episode_251_in_12_min]
  test_role_between_thresholds_falls_back_to_title_and_flag  [parametrize: signs_title, forced_flag, plain]
  test_role_without_a_count_falls_back_to_title_and_flag  [parametrize: none, zero, no_duration]
  test_content_is_polish_with_a_polish_dialogue_track
  test_content_is_foreign_when_polish_is_only_signs
  test_content_is_foreign_for_a_language_outside_the_priorities
  test_content_is_none_without_text_subtitles
  test_content_is_none_with_only_signs
  test_content_is_foreign_with_a_companion_subtitle_file
  test_content_is_uncertain_when_the_deciding_track_fell_back
tests/application/test_planner.py
  test_a_forced_track_with_a_dialogue_rate_is_not_demoted
  test_a_polish_signs_track_with_a_count_loses_to_polish_dialogue
  (istniejące test_only_non_dialogue_subtitles_stay_usable_with_a_warning, test_polish_signs_track_loses_to_english_dialogue, test_manual_selected_signs_track_is_honoured_without_demotion — bez zmian i zielone)
```

Fixture'y: `MediaTrack(...)` i `MediaCatalog(...)` w kodzie testu; przypadki z `current-state.md` §5 jako krotki `(entries, duration_us, forced, title)`; wycinek JSON `tests/data/mkvmerge-subtitle-counts.json`.

**Gate:** testy F1 i cały `tests/application/test_planner*.py` zielone; mypy.

**Commity:**

```text
feat(services): carry subtitle event counts in media catalogs
feat(application): classify signs-only subtitle tracks by event rate
```

### F2 — Odrzucenie w kontroli i ścieżka subskrypcji

1. `MeasuredMedia.subtitles` z `measured_media`; `NO_DIALOGUE_SUBTITLES`.
2. `_check_episode`: odrzucenie przy werdykcie `brak` także w `record_only`; wpis `check` z `subtitles`, `subtitles_uncertain`.
3. Tekst powodu w `_REJECTIONS`.
4. Fake sondy: domyślny katalog z tekstową ścieżką dialogową (`entries` w tempie dialogu); parametr do wyłączenia napisów.

**Testy:**

```text
tests/application/test_download_verification.py            @pytest.mark.unit
  test_a_catalog_is_measured_with_its_subtitle_content
  test_a_catalog_without_dialogue_subtitles_measures_none
tests/application/test_subscription_attempts.py              @pytest.mark.integration
  test_an_attempt_without_dialogue_subtitles_is_rejected_before_naming_also_in_record_only
  test_an_attempt_with_only_signs_is_rejected_and_the_next_try_excludes_its_hash
  test_an_attempt_with_a_companion_subtitle_file_is_not_rejected
  test_an_unchecked_attempt_is_never_rejected_for_subtitles
tests/application/test_subscription_scenarios.py             @pytest.mark.integration
  test_a_release_without_subtitles_is_replaced_by_the_next_ranked_one
  test_three_releases_without_subtitles_exhaust_the_target_with_the_subtitle_reason
tests/application/test_acquisition_decisions.py              @pytest.mark.unit
  test_a_check_entry_keeps_the_subtitle_verdict
tests/application/test_episode_commands.py (albo istniejący plik notice_text)   @pytest.mark.unit
  test_the_subtitle_rejection_has_a_polish_phrase
```

**Gate:** cały `uv run pytest` zielony (fake'i z F2 nie mogą zmienić wyniku istniejących scenariuszy).

**Commit:** `feat(application): reject downloads without dialogue subtitles before naming`

### F3 — Zamiana w ścieżce ręcznej i schemat 6

1. Inwariant `EpisodeAssignment` (model danych wyżej); `WATCH_STATE_SCHEMA_VERSION = 6`, migracja 5 → 6, kopia `.e4-migration.bak`, `_SUPPORTED_SCHEMA_VERSIONS`.
2. `_check_basis` dla `AdmissionSource.MANUAL`: wideo z zestawu, `ExpectedEpisode(None)`; kontrola czasu dla ręcznych nie odrzuca (I-02).
3. Zapis odrzucenia ręcznego; kolejka zamiany w puli I/O (licznik `_active_io`, wzorzec `_download_episode`); `replacement` na `choice_candidate` z `search_episode`; przyjęcie na wątku ownera z `command_id = "content-replace:<admission_id>"` i `previous`.
4. Limit D2; status `SUBTITLES_MISSING`; recovery przy starcie ownera.
5. Odrzucone przyjęcie ręczne zamyka się istniejącą drogą `_replace_episode_scope` / `_closed_attempt`; plik zostaje w stagingu do istniejącego sprzątania (D3).
6. `_record_check` zapisuje wpis także dla przyjęcia ręcznego (`entry="manual"`, bez `subscription_id`); zamiana i jej brak dostają wpis `replacement`.
7. Pauza (D8): zamiana ręczna dziedziczy pochodzenie USER pierwotnego D i działa w pauzie tak jak ręczne transfery (`AcquisitionConfirmation.manual`); zamiana subskrypcji podlega pauzie jak dziś.
8. Stan „Sprawdzam plik” (`_checking`) pokazuje się także dla ręcznych w czasie sondy; etykieta bez zmian.
9. Etykieta w `anime_texts.py`.

**Testy:**

```text
tests/application/test_watch_state.py                        @pytest.mark.integration
  test_a_schema_five_state_migrates_to_six_with_a_backup_and_unchanged_data
  test_a_manual_assignment_may_carry_a_download_check
  test_a_published_assignment_never_carries_a_rejection
tests/application/test_content_replacement.py                @pytest.mark.integration
  test_a_manual_download_without_subtitles_is_replaced_once
  test_a_failed_replacement_shows_the_subtitle_problem_and_downloads_nothing_more
  test_no_replacement_candidate_shows_the_subtitle_problem
  test_a_restart_after_the_rejection_admits_exactly_one_replacement
  test_a_user_redownload_after_two_failures_gets_no_automatic_replacement
  test_a_manual_download_with_polish_subtitles_is_published_unchanged
  test_an_unchecked_manual_download_is_published
  test_the_replacement_search_never_runs_on_the_owner_thread
  test_a_paused_owner_still_replaces_a_manual_download_without_subtitles
  test_a_manual_check_and_its_replacement_are_journaled_without_names
tests/cli/test_anime_episodes.py                              @pytest.mark.unit
  test_episode_problem_reason_overrides_ordinary_state_label  [nowy przypadek parametrize: subtitles_missing → "Brak napisów"]
  (istniejące strażniki test_every_owner_reason_has_a_stan_label_or_an_explicit_fallback i test_every_refused_stan_label_fits_its_column obejmą nowy powód bez zmian)
```

Fake'i: `FakeMediaProbe` z kolejką katalogów; źródło wydań z `tests/application/fakes.py` lub `test_acquisition.py` (wzorzec istniejący, bez sieci); `tmp_path` dla stanu.

**Gate:** pełne bramki; test migracji na kopii prawdziwego `config/watch/state.json` wykonany przez właściciela albo za jego zgodą (kopia w `tmp_path`, oryginał nietknięty).

**Commit:** `feat(application): replace a manual download without dialogue subtitles once`

### F4 — Dokumentacja i H4

1. `anishift/application/AGENTS.md`: kontrola zawartości dla obu źródeł, schemat 6, limit ręczny, recovery zamiany. `anishift/services/media/AGENTS.md`: `entries`.
2. `docs/ideas.md` §2: status pozycji; masterplan 08 E4; `docs/README.md`.
3. H4 (poniżej).

**Commit:** `docs(repo): record the post-download content check`

**Human checkpoint (H4):**

```text
Uruchom: właściciel zamyka rezydenta, przełącza checkout na branch, startuje AniShift.
Zrób: (a) D na odcinku Erai-raws CR z CR_Polish; (b) D na odcinku SubsPlease (tylko EN).
Oczekiwany rezultat: (a) w Przetwarzaniu brak zadania tłumaczenia, jest lektor; (b) tłumaczenie i lektor; oba bez odrzucenia.
Zwróć uwagę na: czy szczegóły odcinka nie pokazują fałszywego „Brak napisów”; state.json.e4-migration.bak powstał.
Przekaż wynik jako: OK / opis odcinka i co pokazał panel.
```

## Strategia dowodu

| Twierdzenie | Kontrola | Dlaczego wystarcza |
|---|---|---|
| Pole aplikacji = liczba zdarzeń | F0 na 52 plikach | ten sam materiał co pomiar progów |
| Reguła roli poprawna | unit na przypadkach granicznych z danych | przypadki leżą przy obu progach i przy obu sygnałach zapasowych |
| Planner bez regresji | istniejące testy plannera + nowe | chronią obecny wybór PL/EN i Ręczny |
| Subskrypcja zamienia wydanie | integration ownera z fake sondą | przechodzi przez prawdziwe `settle_target` i zapis stanu |
| Zamiana ręczna jednorazowa i trwała | integration z restartem | receipt i recovery na prawdziwym `WatchStateStore` |
| Migracja | integration na `tmp_path` | wzorzec poprzednich migracji |
| Odbiór | H4 | jakość ścieżki PL / EN ocenia człowiek |

### Bramki

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest
```

Przed commitem w testach: zero opisowych komentarzy i docstringów (hook `check_test_comments.py`); stałe w kodzie aplikacji z docstringiem pod przypisaniem (`check_const_docstrings.py`).

## Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Kiedy eskalować |
|---|---|---|---|
| Pliki bez cue/statystyk | `entries` brak lub 0 | reguła zapasowa D1 | gdy H4 lub rejestr pokaże fałszywe odrzucenie |
| Progi z 52 plików nie pasują do fansubów `Signs & Songs` | wpis `subtitles_uncertain` albo zgłoszenie właściciela | przypadek do testów regresyjnych, korekta progu | każda zmiana progu → właściciel |
| Zamiana ręczna ściga się z „Pobierz ponownie” użytkownika | `_admission_refusal` zwraca `EPISODE_CHANGED` | zamiana odpada bez skutku, wpis w rejestrze | — |
| Migracja psuje stan | test na kopii | stop przed F3 merge | zawsze |
| Fake'i ukrywają regresję | scenariusz bez napisów przechodzi bez odrzucenia | test negatywny w F2 | — |

## Definition of Done

- [ ] warunki końcowe spełnione;
- [ ] bramki zielone z wynikami w raporcie;
- [ ] H4 zaliczone;
- [ ] przegląd krzyżowy innym modelem bez otwartych findingów krytycznych i poważnych;
- [ ] PR z opisem bez śladów generatora.

## Kontrakt wyniku

```text
status; wynik F0 (pole i liczby zgodności); zmienione pliki; wyniki bramek; wyniki testów nowych;
H4; odchylenia od planu; stan gałęzi i commity; następny krok
```

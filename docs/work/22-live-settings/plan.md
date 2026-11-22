# Ustawienia na żywo: każdy krok bierze ustawienia z chwili startu

## Kontrakt właściciela (2026-11-22)

1. Ustawienie to jednorazowa operacja w chwili zapisu. Każdy krok (task) czyta ustawienia w chwili, gdy **startuje**.
2. Krok wykonany zostaje taki, jaki jest. Krok w trakcie kończy się na ustawieniach, z którymi ruszył. Każdy krok,
   który jeszcze nie ruszył, bierze bieżące ustawienia — także w zleceniu, które już trwa (przykład: dwa odcinki
   przyjęte razem, tłumaczone po kolei; zmiana modelu między nimi → drugi odcinek tłumaczy już nowy model).
3. Nigdy nie ma sytuacji, w której wywołanie dostaje stare ustawienia.
4. Ponowienie (P) i wznowienie to szczególny przypadek tej samej zasady: ponawia się tylko to, co nie zostało zrobione
   albo padło. Gotowe tłumaczenie zostaje także po zmianie modelu tłumaczenia (nowe tłumaczenie zamawia się jawnie:
   „Regeneruj polskie napisy”).
5. Krok, który padł w połowie (brak tokenów w tłumaczeniu, błąd w połowie nagrania), idzie od nowa w całości, na
   ustawieniach z chwili ponowienia. Żaden produkt nie jest sklejony z części zrobionych na różnych ustawieniach.
   Pamięć klipów TTS w obrębie runu może zostać tylko wtedy, gdy odcisk klipu (`SynthesisProfile`) jest identyczny,
   czyli klip powstałby tak samo.

Odwraca to decyzje z `docs/work/06-local-automation/06-efficiency/plans/01-implementation.md` §5.1 (snapshot w
kontekście zlecenia) i `docs/work/07-local-automation-2/plans/02-implementation.md` (ok. linii 119: „RunSettingsSnapshot
nadal zachowuje ustawienia przyjęcia. Nie odczytywać globalnego nowego głosu w połowie starego runu”).

## Stan wyjściowy (rozpoznanie)

Ustawienia są dziś zamrażane w 8 miejscach:

1. `ExecutionPlan.settings` (`planning.py`).
2. `PlanTask.resource_key` / `is_paid` / `is_network` i parametry (`sign_narration`, `output_profile`).
3. Kopia w `RunJournal` (checkpoint JSON).
4. `ProcessingRequest.settings` w `state.json` (`control.py`, `watch_state.py`).
5. `RunRequest.plan` w koordynatorze i `worker_limit(..., context.plan.settings)`.
6. `ProductionHandlerFactory` (`runtime.py`) buduje raz na run `TranslationService`, `TtsService`,
   `_ConfiguredAudioService` (tempo), `CompositionService` i `DialogueFont`; sekrety `Settings` też raz na run.
7. `natural_gate` (`scheduler_runtime.py`) przy rejestracji runu.
8. `_palantir_translation_config` czyta `load_user_settings()` z dysku (niespójne z resztą).

Łatki: `rebind_translation` (PR #130) i `rebind_settings` + `_VOICE_SETTINGS` (commit `5d34747` na tej gałęzi)
podmieniają pola pole po polu. `5d34747` ma błąd w runie wielogrupowym: gdy grupa 1 ma nagrane klipy i czeka na MIX,
a grupa 2 czeka na TTS, MIX grupy 1 dostaje nowe tempo, choć szyldy grupy 1 dopasowano do klipów w starym tempie
(`tts_handler.py` przez `_ConfiguredAudioService.prepare_clip`, `runtime.py`).

Ślady ustawień w gotowych produktach pośrednich: tempo (TTS dopasowuje szyldy do klipów po tempie, MIX stosuje tempo
na surowych klipach; manifest go nie zapisuje), czcionka dialogów (tłumaczenie i normalizacja układają ASS czcionką,
kompozycja dołącza pliki czcionki z ustawień), `sign_narration` (obecność kandydatów szyldów), profil audio (kodek
miksu). Głos, model i silnik zostają tylko w treści klipu.

Pamięci podręczne: klipy TTS (`services/tts/fingerprint.py`, `SynthesisProfile`) i audio
(`services/audio/fingerprint.py`) mają poprawne klucze, ale żyją w `run_root` (nowy `run_id` je gubi). Tłumaczenie nie
ma pamięci; jego wynik to artefakt `READY` w dzienniku.

Jednorazowe nadpisania (`overrides` w IPC, `plan_auto/plan_manual(overrides=)`, `decode_overrides`,
`RunSettingsSnapshot.with_overrides`) istnieją tylko w API i testach; żaden ekran ich nie wysyła.

Martwe albo zdublowane pola `RunSettingsSnapshot`: `tts_voice_label` (0 czytelników), `llm_is_network`,
`llm_is_paid` (tylko lista rebind), `translation_is_network` (zawsze `True`), `tts_timeline_policy` (walidacja dopuszcza
tylko `"serialize"`), `audio_profile_id` (= `audio_output_profile`), `audio_duration_tolerance_us` (serwis go nie
ustawia).

## Projekt

1. **Plan nie niesie ustawień.** Znika `ExecutionPlan.settings`; z `PlanTask` znikają dostawca w `resource_key`,
   `is_paid`, `is_network`. Zostaje rodzina zasobu wynikająca z rodzaju taska (`translation`, `tts`, `audio`,
   `composition`, `extraction`).
2. **Koordynator czyta ustawienia przy wysłaniu taska.** `GraphCoordinator(settings_provider)` zastępuje
   `limits_provider`; przy wysłaniu kandydata koordynator bierze jeden snapshot `run_settings()` i z niego liczy klucz
   zasobu (`tts:<silnik>`, `llm:<dostawca>`, `translation:<silnik>`), limit (`ResourceLimits.from_settings`) i koszt
   (`journal.started(task, paid)`). `handler.execute(task, artifacts, settings, ...)` dostaje niezmienny snapshot z tej
   chwili. Task w toku kończy na swoim snapshocie.
3. **Usługi leniwe, w obrębie runu, kluczowane konfiguracją.** W `runtime.py` słownik `TtsConfig → TtsService`
   (analogicznie tłumaczenie, audio, kompozycja), zamykany na końcu runu. Dwa taski z tą samą konfiguracją dzielą
   usługę (limit kart ElevenReadera = 2 i `tts_request_concurrency` nie mogą się mnożyć). Sekrety `Settings` czytane
   przy starcie taska. `_palantir_translation_config` bez odczytu z dysku.
4. **Ślady z wyniku poprzedniego kroku, nie z bieżących ustawień.** Tempo zapisane w manifeście TTS; MIX czyta je z
   manifestu (`_ConfiguredAudioService` znika). Plik czcionki dialogów zapisuje krok układający ASS jako pole
   wyprodukowanego artefaktu; kompozycja dołącza tę czcionkę. `sign_narration` wychodzi z grafu: split ASS przy lektorze
   zawsze pisze kandydatów szyldów (tani, lokalny krok), a TTS czyta tryb przy starcie.
5. **Ustawienia kształtujące graf zostają trzy:** `audio_output_profile`, `subtitle_language_priority`,
   `audio_language_priority`. Wiążą się przy planowaniu grupy. Zmiana któregoś z nich w trakcie zlecenia: owner
   przeplanowuje pozostałą część aktywnych zleceń przez tę samą drogę co ponowienie (pkt 6) — taski w toku kończą,
   nierozpoczęte idą według nowego planu.
6. **Ponowienie i wznowienie to jedna droga: `rebase(fresh_plan, checkpoint)`.** Świeży plan powstaje z zapisanych
   intencji (`GroupIntent`, `RebuildRequest`, wybór źródeł) i bieżących ustawień. Krok ukończony w dzienniku zostaje,
   gdy jego `PlanTask` jest identyczny w świeżym planie, a każde jego wejście jest źródłem albo wynikiem przeszczepionego
   kroku. Checkpoint dostaje listę `done` ukończonych tasków. Niezmiennik: bez zmian ustawień wynik równa się
   dzisiejszemu `journal.plan`. Zmiana profilu audio robi od nowa MIX/TRANSCODE/PUBLISH (TTS zostaje, bez płatnego
   wywołania); zmiana języka robi od nowa extract i wszystko za nim; zmiana modelu czy silnika niczego gotowego nie
   unieważnia. `inflight`, `pending/staged` i dowody publikacji działają jak dziś. `STALE_PREVIEW` porównuje tylko graf.

## Kroki (commity tematyczne)

1. **Usuń.** `rebind_settings`, `_rebound_task`, `_TRANSLATION_SETTINGS`, `_VOICE_SETTINGS`, `RunJournal.rebind` i ich
   wywołania w `automation.py`; martwe pola z listy wyżej (`tts_timeline_policy` → stała w `_audio_config`,
   `audio_duration_tolerance_us` → stała plannera, `audio_profile_id` scalone z `audio_output_profile`); cały mechanizm
   `overrides` (`with_overrides`, `decode_overrides`, ładunek IPC, argumenty serwisu, `resident.plan_auto`); w
   `anishift/application/AGENTS.md` zasady o rebind, „run w toku kończy na ustawieniach…”, zdanie o
   `reload_preferences`/snapshocie trwających zleceń i opis `ProcessingRequest` z pełnym snapshotem.
2. **Plan bez ustawień** (`planning.py`, `planner.py`, projekcje podglądu: koszt liczony przy podglądzie z bieżących
   ustawień).
3. **Koordynator** (`scheduler.py`, `scheduler_contracts.py`, `scheduler_runtime.py`, `service.py`, `recovery.py`).
4. **Usługi przy starcie taska** (`runtime.py`, `tts_handler.py`, `translation_handler.py`, `subtitle_handler.py`,
   `composition_handler.py`, `audio_handler.py`).
5. **Ślady** (manifest TTS z tempem, czcionka na artefakcie, kandydaci szyldów zawsze przy ASS z lektorem).
6. **Wznowienie przez `rebase`** i przeplanowanie aktywnych zleceń po zmianie ustawienia kształtującego graf
   (`recovery.py`: checkpoint z `done`, czysta `rebase`, `RunJournal.replace_plan`; `automation.py`: `_plan` gałąź
   resume, `_admit`, `_resume_restored`; `ProcessingRequest.settings` znika, ścieżkę lektora daje plan z dziennika).
7. **Migracja jednorazowa** w `scripts/tmp/` (nie w kodzie produktu): usuwa `settings` z `requests` w `state.json`
   (podbicie schematu) i przepisuje checkpointy runów na nowy format z `done` (= taski świeżego planu, których wszystkie
   `produces` są `READY` w dzienniku). Uruchamia ją prowadzący po zatrzymaniu rezydenta; potem skrypt znika.

## Testy

Do zmiany albo usunięcia (kodują stary kontrakt): `test_planner.py` (rebind, tolerancja i koszt ze snapshotu,
overrides), `test_service.py` (overrides), `test_automation.py` (overrides; `test_a_resumed_run_translates_with_the_engine_chosen_after_it_failed`
zostaje jako test akceptacyjny), `test_scheduler.py` (`manual_context_keeps_its_own_settings`, limity),
`test_recipe_settings.py` (odwraca się), `test_runtime_config.py`, `test_control.py`, `test_watch_state.py`.

Nowe:

1. Dwie grupy w jednym runie: zmiana modelu tłumaczenia albo silnika TTS po wysłaniu taska grupy 1 → grupa 2 dostaje
   nowe ustawienia, task w toku stare.
2. Zmiana silnika, gdy task czeka w kolejce → limit i klucz zasobu nowego silnika.
3. `inflight` według kosztu z chwili wysłania.
4. Zmiana tempa między TTS a MIX → miks bierze tempo z manifestu.
5. Zmiana czcionki między tłumaczeniem a kompozycją → kontener ma czcionkę, którą ułożono ASS.
6. Zmiana `sign_narration` off→smart po splicie → TTS czyta szyldy.
7. `rebase`: bez zmian = dziennik; zmiana profilu audio nie wywołuje TTS; zmiana języka robi extract od nowa.
8. Przypadek właściciela: TTS ElevenBytes pada z 429, przełączenie na `elevenreader`, P → usługa TTS `elevenreader`,
   tłumaczenie nie idzie drugi raz.
9. Dwa taski TTS z tą samą konfiguracją dzielą jedną usługę.
10. Tłumaczenie przerwane w połowie (błąd) → ponowienie tłumaczy cały plik od nowa na bieżącym modelu.

## Warunek sukcesu

- Bramki: `ruff check`, `ruff format --check`, `mypy anishift/ tests/`, `pytest -n 6` zielone.
- W kodzie nie ma `ExecutionPlan.settings`, `rebind*`, `overrides` ani martwych pól.
- Na żywo: rezydent z tej gałęzi; zmiana silnika lektora w trakcie zlecenia działa na odcinkach, których TTS jeszcze
  nie ruszył.

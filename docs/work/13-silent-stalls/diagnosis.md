# Diagnoza: ciche zatrzymania rezydenta (stan z 2026-10-25)

Status: diagnoza bez zmian w kodzie i danych. Tylko odczyt `config/watch/`, `logs/`, `workspace/` oraz kodu.
Dowody: DIRECT = sprawdzone w kodzie albo uruchomione na danych; ASSUMED = wniosek bez pełnego potwierdzenia.
Czasy z logu są lokalne (`+02:00`), czasy ze stanu i `decisions.jsonl` w UTC (różnica 2 h).

## Podsumowanie

| # | Problem | Przyczyna | Status |
|---|---------|-----------|--------|
| 1 | Dwa odcinki nigdy nie weszły do przetwarzania | Pobrane MKV nie mają żadnej ścieżki napisów; Auto uznaje grupę za niegotową i pomija ją bez śladu | DIRECT |
| 2 | Magical Explorer S01E05 | To faktyczny odcinek 5; zła jest tylko data w `mapping.episodes` (ani.zip). Powtórki `no_match` poprzedzają przyjęcie | DIRECT (numeracja), ASSUMED (premiera 2 odcinków naraz) |
| 3 | 17 failed + 5 partial | Wszystkie 22 są historyczne; produktów brak dla Solo Leveling 01-04, Laid-Off Mage S01E02, Slime S04E01 (duplikat) | DIRECT |
| 4 | 22 acquisitions `uncertain` | Wysyłka do klienta nigdy niepotwierdzona; nic nie blokują poza dwoma wpisami Blue Box | DIRECT |
| 5 | `workspace/temp/` 532 MB | `retain_runs` trzyma staging każdego nieudanego zlecenia na zawsze; 3 katalogi bez znacznika właściciela nie są sprzątane nigdy | DIRECT |
| 6 | 19x `TTS_TIMEOUT` | Jeden jednosekundowy wybuch pierwszej fali żądań (rank 0-19), bez skutku; współbieżność 85 możliwa, niedowiedziona | DIRECT (przebieg), ASSUMED (przyczyna po stronie proxy) |

---

## 1. Pobrane odcinki nigdy nie trafiły do przetwarzania

### Objaw

`Magical.Explorer.S01E05...ToonsHub.mkv` (group `group-ff01423f74795750`) i `Kashita.Maryoku...S01E04...ToonsHub.mkv`
(group `group-55419e02a62ce6bd`): acquisition `complete`, log „Episode set published and handed to Auto”
(24.10 19:01:47 i 20:02:12), w `history.jsonl` tylko `download_confirmed`, brak `order_admitted`, brak `requests`,
brak błędu i powiadomienia. Oba pliki leżą dziś w `workspace/` (root), nietknięte
(`Magical...mkv` 712 065 293 B, 24.10 19:01; `Kashita...mkv` 1 146 073 440 B, 24.10 20:01).

### Przyczyna (DIRECT)

Oba MKV zawierają wyłącznie strumień wideo i audio, zero ścieżek napisów. Auto nigdy nie zakłada zlecenia dla grupy, która
według `resolve_readiness` nie jest gotowa, i robi to bez logu, wpisu w `decisions.jsonl` i powiadomienia.
Pobranie przeszło kontrolę, bo `download_verification` celowo sprawdza tylko wideo i czas trwania
(docstring `Verification`: „without asserting identity or subtitle usability”).

Ścieżka w kodzie od „handed to Auto” do zlecenia:

1. `automation.py:6849` `_settle_publication` loguje „handed to Auto” i wywołuje `files_changed(DirectoryChange(... "transfer_complete"))`.
2. `files_changed` (`automation.py:911`) → `_inspect_changes` → `_inspect_library` (`discover`) → `_Inspected` → `_refresh_automatic` (wywołania m.in. `automation.py:1153-1211`) (`automation.py:1315`) → `_admit_library` (`automation.py:1329`).
3. `_admit_library` woła `self._ledger.candidates(...)` (`automation.py:1354`). `WatchLedger._is_candidate` (`watch.py:162`) zwraca `False`, gdy `not needs_work(group, preset, recipes)`.
4. `needs_work` (`watch.py:93`): `if not group_is_ready(group): return False`.
5. `group_is_ready` → `resolve_readiness` → `_video_readiness` (`selection.py:199`, linia 210):
   brak sidecara i `not _has_embedded_text(group)` → `ReadinessReason.SUBTITLE_SOURCE_MISSING`.
6. Grupa nie trafia do `ready`, więc `_start_automatic` (`automation.py:1406`) nie jest nawet wywołane.
   Druga cicha furtka w tym samym miejscu: `automation.py:1411` `if not plan.can_execute or not plan.tasks: return`.

Odtworzenie na danych (skrypt `scratchpad/stalls/p5.py`: `DiscoveryIndex(workspace).discover()` + `WorkspaceInspector(DefaultMediaProbe()).inspect()` + `resolve_readiness`, tylko odczyt):

```text
group-55419e02a62ce6bd workspace GroupReadiness(ready=False, reason=SUBTITLE_SOURCE_MISSING) ['video_mkv'] tracks: VIDEO, AUDIO
group-ff01423f74795750 workspace GroupReadiness(ready=False, reason=SUBTITLE_SOURCE_MISSING) ['video_mkv'] tracks: VIDEO, AUDIO
```

Identyfikatory grup z odtworzenia są równe `assignments[0].group_id` ze stanu. Niezależnie `external/bin/ffmpeg/ffprobe.exe`:
`stream|index=0|codec_name=h264|codec_type=video` i `stream|index=1|codec_name=eac3|codec_type=audio|tag:language=jpn`,
brak strumienia `subtitle` w obu plikach (rozdziały: Prologue/Intro/Part 1).

Porównanie z odcinkiem, który przeszedł: `Even.the.Student.Council...S01E04...MSubs-ToonsHub` (nazwa zawiera `MSubs`)
wszedł do przetwarzania 19:32:01 (log `Media identification`, `Sign candidates written` 19:32:15). Widoczne pola acquisition/assignment (`verdict`, `verification`, `traits.unusable`, `publication`, `cleaned`)
obu odrzuconych nie różnią się od odcinków, które przeszły (`verdict: match`, `verification: no_contradiction`,
`traits.unusable: []`, `publication: null`, `cleaned: true`). Różni je wyłącznie zawartość kontenera.

Dlaczego wybrano wydanie bez napisów (Magical): `decisions.jsonl` (`kind:selection`, 24.10 17:00:07Z) – wybrany `164ba1d9...`
miał `quality 35`, `confidence 0.9993`, `after_metadata:false`; lepsze (`quality 45/40`) miały `failures ... transient:2`
w `targets[5].failures` (ASSUMED: nie udało się pobrać ich metadanych, więc odpadły jako „tried/transient”). Nazwa wydania nie
zawiera `MSubs`/`MultiSub`, a ranking `release_quality.py` nie karze braku deklaracji napisów (brak tokenu jest neutralny).

### Wpływ

Subskrypcja uznaje cel za `satisfied` (`targets[5].state: satisfied`, `targets[4]` Kashita tak samo), więc nie szuka innego
wydania. Pliki zostają w root `workspace/`, widoczne w panelu Przetwarzanie jako „Brak napisów”
(`cli/interactive/state_processing.py:49`), ale bez powiadomienia. Dotyczy każdego przyszłego odcinka, którego najlepiej
oceniane wydanie jest bez napisów (np. ToonsHub bez `MSubs`).

### Proponowana naprawa

Dwie warstwy, w tej kolejności:

1. Zapobieganie (przyczyna): w `_check_episode` (`automation.py:6699`) po `_identify` odrzucać próbę, gdy ani kontener, ani
   przemieszczony zestaw plików nie mają źródła napisów. Zmiany: `download_verification.py` – pole `subtitle_streams` w
   `MeasuredMedia`/`measured_media`, nowa stała `NO_SUBTITLE_STREAM`, wyjątek przy `record_only` obok `NO_VIDEO_STREAM`
   (`download_verification.py:137`), zmiana docstringu `Verification`. Odrzucenie idzie istniejącą drogą
   `VERIFICATION_REJECT` → `_reject_attempt` (`automation.py:6787`) → subskrypcja próbuje kolejnego kandydata
   (`targets[*].failures`). To odwraca świadomą decyzję „weryfikacja nie ocenia użyteczności napisów”, więc wymaga akceptacji właściciela.
2. Widoczność (siatka bezpieczeństwa): gdy grupa z pochodzenia `BACKGROUND` jest niegotowa dłużej niż okno stabilizacji,
   jednokrotnie zalogować `logger.warning("A downloaded episode cannot start", reason=...)` i dopisać rekord do `decisions.jsonl`
   (jest `append_decision`), w `_admit_library` przed filtrem `eligible`. Bez nowych stanów.

Test regresyjny, który najpierw pada:
`tests/application/test_download_verification.py::test_container_without_any_subtitle_track_is_rejected` (kontener z wideo
i audio, bez napisów → `verify(...)` daje `reject`/`no_subtitle_stream`; dziś `no_contradiction`) oraz
`tests/application/test_automation.py::test_subscription_download_without_subtitles_tries_the_next_release`
(fałszywy probe bez ścieżki napisów → próba odrzucona, cel nie jest `satisfied`, brak „handed to Auto”).

### Odzysk (bez ręcznej edycji stanu)

Zlecenia nie ma, więc `retry_prepare`/`resume` nie pomogą: `_retry_proposal` (`automation.py:7893`) bez `current` zwróci
`manual` z pustymi `intents`, a `plan_manual` skończy się problemem `subtitle_source_missing` (`planner.py:1089`).
Dwie drogi:

- A (zalecana, kontener ma dobre wideo): dostarczyć napisy i pozwolić Auto je podjąć. Przez panel Ręczny/`register_external_subtitle`
  (`resident.py:418`, `group_id` + ścieżka `.ass`/`.srt` + język), następnie `plan_manual` → `start`; albo położyć napisy obok pliku
  jako sidecar o identycznym stemie (`...-ToonsHub.ass`), po czym grupa staje się `needs_work` i Auto weźmie ją sam.
  Napisy trzeba skądś wziąć (np. wydanie Erai-raws MultiSub tego samego odcinka).
- B: pobrać inne wydanie z napisami przez panel Anime → odcinek → wybór kandydata (`episode_choose`, `resident.py:277`,
  z `conflict_confirmed=True`, bo odcinek jest już `ADMITTED`). Stare MKV z rootu potem usunąć ręcznie, bo to osobna grupa.

---

## 2. Magical Explorer: czy to właściwy odcinek

### Objaw

Plik ma `S01E05` i `number 5`, a `subscriptions[080a03dac8c848e8].mapping.episodes` podaje `5 → 2026-10-31`, `4 → 2026-10-24 ("Determination")`.

### Przyczyna (DIRECT dla numeracji, ASSUMED dla premiery)

Są dwa niezależne źródła dat w jednej subskrypcji:

- `mapping.episodes`/`raw_episodes` pochodzą z ani.zip (numeracja TVDB): `1→10-03, 2→10-10, 3→10-17, 4→10-24, 5→10-31`.
- `targets[*].due_at` pochodzi z harmonogramu AniList (`subscription_targets.py:679` `_due_at` → `anilist_date`): `4→10-17, 5→10-24, 6→10-31`.

Odcinek jest numerowany jak w AniList i u wydawców: Erai-raws „04” pobrany 17.10 (`history.jsonl`, `download_confirmed` 17:03Z),
ToonsHub `S01E05` opublikowany 24.10 w oknie 15:00Z + bufor 2 h (`targets[5].polish_buffer_min: 120`, admisja 17:00:06Z).
Gdyby plik był odcinkiem 4 z numeracją przesuniętą o 1, musiałby istnieć wcześniej niż jego emisja według żadnego źródła;
tymczasem Erai „03” było dostępne już 10.10, czyli za TVDB o tydzień przed jego odcinkiem 3. Najprostsze wyjaśnienie: ani.zip/TVDB
nie zna podwójnej premiery (odcinki 1 i 2 razem 03.10; ASSUMED, bo nie czytałem źródła AniList), przez co wszystkie
odcinki ≥2 ma przesunięte o tydzień. Z `ffprobe` nie da się tego potwierdzić z pliku: brak tytułu, brak napisów, rozdziały
`Prologue/Intro/Part 1`, czas 1420,002 s (oczekiwane 1500 s, `duration_within_tolerance`).

Wniosek: pobrano faktyczny odcinek 5 (w numeracji wydawców i AniList). `mapping.episodes` ma błędne daty, ale służy tylko do
oczekiwanego czasu trwania (`raw_episodes["5"].length = 25`) i tytułów, więc rozjazd nie zmienił wyniku.

### Powtarzane sprawdzenia `no_match` (DIRECT)

To nie są sprawdzenia po przyjęciu. `grep` po `Subscription checked` dla `080a03dac8c848e8`: 17:00, 17:15, 17:30, 17:45, 18:00, 18:15,
18:30, 18:45 (osiem razy `no_match`), potem 19:00:05 `decision: proposed`, 19:00:07 „Episode admitted”. Dla `b228e811af80f446`:
18:30–19:45 (sześć razy `no_match`), 20:00:09 `proposed`, 20:00:10 „Episode admitted”. Po przyjęciu zero kolejnych sprawdzeń
dla tych numerów. Kod: `automation.py:4094`: `outcome = "proposed" if choice else "no_match" if offer.candidates else "no_candidates"`;
`no_match` = są kandydaci, ale żaden jeszcze nie spełnia warunków (Magical: `match: 0` do 18:00, bufor Polish 120 min;
Kashita: jedyny kandydat `mismatch`, `match: 1` dopiero 20:00). Cykl 15 min to zamierzone odpytywanie okna do chwili wyboru.
Wpis „Subscription next search ... number 5 at 2026-10-25T17:00” po przyjęciu to tylko zaplanowane następne sprawdzenie
(`_log_next_search`, `automation.py:3847`), a pole `number` pochodzi z `last_check`.

### Wpływ

Brak błędu danych. Ryzyko pozostaje przy innych tytułach: gdy AniList i ani.zip rozjadą się o odcinek, `expected_episode`
bierze długość i tytuł z błędnego klucza.

### Proponowana naprawa

Opcjonalna, tania: ostrzeżenie w logu, gdy `anilist_date(episode)` i `mapping.episodes[number].airs_at` różnią się o więcej niż 3 dni
(`subscription_targets.py`, przy budowie celów). Test: `tests/application/test_subscriptions.py` (fałszywy harmonogram z przesunięciem
o tydzień → ostrzeżenie). Nie jest to blokada ani zmiana wyboru.

### Odzysk

Nie dotyczy. Odcinek jest poprawny; jego jedyny problem to brak napisów (punkt 1).

---

## 3. Stare nieudane i częściowe zlecenia (17 failed, 5 partial)

Skrypt `scratchpad/stalls/p9.py`/`p13.py`/`p20.py`: dla każdego zlecenia sprawdziłem `ready/` i resztę workspace po stemie,
późniejsze zlecenia tej samej grupy, `logs/errors.log.jsonl` oraz obecność wejść z dziennika `config/watch/runs/<id>.json`.

| Odcinek | Zlecenia | Stan produktów dziś | Przyczyna (errors.log) |
|---------|----------|---------------------|------------------------|
| Solo Leveling [ASW] 01 | 6 (1 partial + 5 failed), 17.09 | BRAK w `ready/` i w workspace | `split_subtitles` `ExecutionError UNKNOWN` (17.09 18:19 i 5 kolejnych prób). Log nie podaje komunikatu (ASSUMED: błąd układu napisów, naprawiany od tego czasu w `services/subtitles`) |
| Solo Leveling [ASW] 02 | 6 (1 partial + 5 failed) | BRAK | to samo, group `fc33b526` |
| Solo Leveling [ASW] 03 | 5 (1 partial + 4 failed) | BRAK | to samo, group `447be466` |
| Solo Leveling [ASW] 04 | 1 partial | BRAK | to samo, group `e05fd7ac` (17.09 21:28) |
| The Laid-Off Cheat-Granting Mage S01E02 (ToonsHub) | 1 failed, 13.10 | BRAK (w `ready/` jest tylko S01E03; E01 wyrzucone przez właściciela 16.10) | `translate_subtitles` `LLM_REQUEST_FAILED` (14.10 00:22, „Translation engine chain exhausted”) |
| That Time I Got Reincarnated as a Slime S04E01 (VARYG) | 1 failed, 01.10 | brak tej kopii; odcinek ten sam co dwie udane kopie DUAL i MULTi z 30.09/01.10 (które też nie leżą dziś w `ready/`) | `translate_subtitles` `LLM_REQUEST_FAILED` (01.10 20:51) |
| Nowy Dokument tekstowy.txt | 1 failed, 21.09 | plik testowy dalej w roocie workspace | `synthesize_speech` `TTS_CONFIG_INVALID` |
| Yasei no Last Boss 2nd Season 04 (Erai-raws) | 1 partial, 17.10 | JEST komplet: `ready/Yasei no Last Boss ... - 04 ... [AA82A5A0].{mkv,eac3,pl.ass,displayed.pl.ass}` | `synthesize_speech` `TTS_ENGINE_UNAVAILABLE` po 4 próbach (17.10). Właściciel puścił ją ponownie jako grupę bez prefiksu `[Erai-raws]` (zlecenie `run-7bdb34ccb615`, succeeded 17.10 22:38), stare zlecenie `492cfbc8` zostało jako `partial` |

Zrekonstruowane wnioski (DIRECT): w żadnym z 22 zleceń wejścia z dziennika nie istnieją na dysku poza `Nowy Dokument tekstowy.txt`
(`p20.py`: wszystkie `False`). Trzy kolejne błędy z `errors.log` (`normalize_subtitles IndexError`, 22-23.10) nie wchodzą do tej puli:
zlecenia zostały ponowione 23.10 17:04 (generation 2) i zakończyły się `succeeded` (np. Tsuihou S01E17, Exiled Heavy Knight S01E17).
Pięć błędów `CONFIG_MISSING` z 23.09 nie ma w `requests` (uruchomienia poza rezydentem).

### Wpływ

Brakujące dziś: Solo Leveling 01-04 (ASW), Laid-Off Mage S01E02. Slime S04E01 (VARYG) i Yasei 04 są pokryte innymi
wynikami. Pozostałe wpisy to szum w stanie (`requests` 162, z czego 22 martwe).

### Proponowana naprawa

Brak dedykowanej komendy kasującej martwe zlecenie, więc stan rośnie. Najmniejsza zmiana: w tym samym miejscu, w którym
rozwiązujemy retencję stagingu (punkt 5), zlecenie `failed/partial`, którego wejścia już nie istnieją i którego grupa ma nowsze
zlecenie albo produkty w `ready`, uznać za rozstrzygnięte (nie pokazywać w panelu, nie retencjonować). Test regresyjny:
`tests/application/test_automation.py::test_failed_request_with_missing_inputs_is_not_retained`.

### Odzysk

- Laid-Off Mage S01E02: `acquisition` `3a2de0171f` ma `nyaa_release_id: None`, więc `retry_prepare` zwróci odmowę
  `retry_reference_missing` (`automation.py:7938`). Droga: panel Anime → odcinek 2 → wybór wydania (`episode_choose`, `conflict_confirmed=True`).
- Solo Leveling 01-04: to samo przez panel Anime (stare pobrania `04688c53`/`1825e2c6`/`be98a2d0` są `uncertain`, patrz punkt 4,
  a wejść ASW już nie ma). Zdecyduj najpierw, czy ten serial jest w ogóle potrzebny.
- Slime S04E01, Yasei 04, Nowy Dokument tekstowy: nic do odzyskania.

---

## 4. 22 acquisitions w stanie `uncertain`

### Co to znaczy (DIRECT)

`AcquisitionState.UNCERTAIN` (`control.py:210`) ustawia się, gdy wysłanie pobrania do klienta nie zostało potwierdzone:
`_reconcile_acquisitions` (`automation.py:5879`) i `transfers._uncertain` (`transfers.py:344`) przy `PENDING_SEND` bez śladu w kliencie,
albo `_send_selective` przy wyjątku `add_metadata` (`automation.py:6254`). Skład (`p14.py`):

- 13 wpisów `background` z subskrypcji sprzed migracji (id `3c216e7a3cd4`...; `updated_at` 2026-09-17 15:39), bez `assignments`,
  z `directory` nazwy serialu (Clevatess S2, Dogulwang, Re:Zero 16 i inne);
- 7 wpisów `user` z 16-17.09 (Solo Leveling Raze/ToonsHub i cztery bez tytułu), bez `assignments`;
- 2 wpisy `user` z 04.10 (`0b5fcf5e`, `de07aad0`), Blue Box S2 odcinek 1 (anilist 189123), `selective`, `applied_revision: 0`.

### Czy blokują (DIRECT)

- Nie wchodzą do `_working_transfers` (`automation.py:2901`: tylko `ACCEPTED`/akcja resume), więc nic nie pobierają i nie pollują.
- Nie tworzą konfliktu odcinka: `episode_conflict` (`control.py` obok `auto_admissible`) czyta `protected_assignments` i
  `legacy_scope`; 20 wpisów bez `assignments` i z `legacy_scope: null` jest dla niego niewidocznych.
- Dwa wpisy Blue Box mają `assignments`, więc dla `(189123, 1)` `episode_conflict` zwraca `ADMITTED` i ponowny wybór odcinka 1 wymaga
  `conflict_confirmed`. W praktyce odcinek 1 powstał trzecią próbą (`595fe751`, `Blue.Box.S02E01...`, succeeded 04.10 21:33), więc
  szkoda ogranicza się do jednego dodatkowego potwierdzenia.
- Koszt stały: przy każdym starcie `_recover_acquisition_confirmations` (`automation.py:1101`) pyta klienta o te hashe. Gdyby któryś
  znalazł się w qBittorrent, `_reconcile_acquisitions` przestawiłby go na `ACCEPTED` i pobieranie ruszyłoby samo (do dziś nie
  nastąpiło po wielu restartach, więc hashy tam nie ma).

### Proponowana naprawa

Nie zmieniać kodu bez potrzeby; ewentualnie dodać do istniejącego `_reconcile_acquisitions` rozstrzygnięcie `UNCERTAIN` bez
`assignments`, `updated_at` starszym niż `search_window_s` i brakiem hasha w kliencie jako `FAILED` (`problem=REMOVED_FROM_CLIENT`).
Test: `tests/application/test_automation.py::test_legacy_uncertain_transfer_missing_from_client_is_failed`.

### Odzysk (bezpiecznie)

Użyć istniejącej komendy `transfer` z `action: "cancel"` (`automation.py:7481`), dostępnej w panelu jako anulowanie pobrania w zakładce
Przetwarzanie (`state_processing.py:232`). `cancel` przechodzi w `_perform_action` (`automation.py:7565`) → `FAILED`, a
`qBittorrent /torrents/delete` dla nieznanego hasha jest bezskutkowe (ASSUMED: zachowanie API klienta; nie testowano). Nie wolno użyć
`resume`: wznowiłoby pobranie wrześniowych wydań. Rozpocząć od dwóch wpisów Blue Box, potem reszta. Przed anulowaniem sprawdzić
w kliencie, że żaden z tych 22 hashy nie jest tam obecny.

---

## 5. `workspace/temp/`: 27 pozycji, 532 MB

### Skład (DIRECT, `p16.py`)

25 katalogów `run-*` + `.acquisition` (pusty) + `.gitkeep`.

- 22 katalogi należą do 22 zleceń `failed`/`partial`: Solo Leveling 18 katalogów po ok. 23 MB (około 414 MB), Slime 35 MB,
  Laid-Off Mage 35 MB, Yasei 48 MB (414 plików, klipy TTS), Nowy Dokument 0 MB.
- 3 katalogi bez żadnego zlecenia: `run-1bca499b80e85603`, `run-a2de2650395e079d`, `run-a9ddf755b99af4b5` (28.08, 0 MB, puste podkatalogi grup, bez pliku `.anishift-owner`).

### Dlaczego nie są sprzątane (DIRECT)

1. `service.py:~583` `_finish_run`: gdy zlecenie z dziennikiem się nie powiodło, `session.preserve()` i `retain_runs((run_id,))`;
   `RunSession.__exit__` (`sessions.py:~118`) pomija `_cleanup`.
2. `automation.py:839` przy każdym starcie: `service.retain_runs(request_id dla każdego zlecenia o stanie != SUCCEEDED)`.
   `_retained_runs` (`service.py:258`) rośnie i nigdy nie jest zmniejszane (`grep` – jedyne użycia: inicjalizacja, `update`, odczyt w `_start_run`).
3. `cleanup_orphaned_temp` (`workspace.py:183`) działa tylko na początku `_start_run` (`service.py:529`) i pomija katalogi z `active`
   (w tym retained) oraz takie, gdzie `_owner_pid` jest `None` (`workspace.py:201`: brak/niepoprawny `.anishift-owner`). Trzy katalogi z sierpnia
   nie mają znacznika, więc nie zostaną skasowane nigdy.

### Czy blokują wznawianie (DIRECT)

Nie. To retencja umożliwia `resume` (`_validate_resume_root`, `sessions.py:~124`), a nowy run ma nowe `run_id`, więc nie koliduje.
W tych 22 przypadkach wznowienie i tak jest niemożliwe, bo żaden plik wejściowy z dziennika nie istnieje (punkt 3). Staging nie zawiera
niczego, czego nie da się odtworzyć: wyniki tłumaczenia przy `LLM_REQUEST_FAILED` nie powstały, a przy Solo Leveling jedyny istotny
koszt (tłumaczenie LLM) i tak wymaga wejścia, którego już nie ma.

### Co jest bezpieczne do usunięcia

Uwaga: stan `config/watch/runs/*.json` i `requests` pozostaje, więc panel dalej pokaże te zlecenia jako `failed/partial` i
`retry_prepare` zaproponuje `resume`, które padnie na walidacji wejść. Dlatego sama kasacja katalogów nie zamyka tematu.

| Grupa | MB | Bezpieczne? |
|-------|----|-------------|
| 3 katalogi bez zlecenia (28.08) | 0 | tak, nic ich nie referuje |
| Yasei 04 `run-492cfbc8a5b59f22` | 48 | tak, komplet produktów jest w `ready/` |
| Slime S04E01 `run-3e625795ab7708f3` | 35 | tak, duplikat; wejścia nie ma |
| Laid-Off Mage `run-58dedd9259cd2b64` | 35 | tak, wejścia nie ma (do odzyskania tylko ponownym pobraniem) |
| Nowy Dokument `run-87a998bcfa11d10a` | 0 | tak, plik testowy |
| 18 katalogów Solo Leveling | ~414 | tak, jeśli właściciel potwierdzi, że serial jest niepotrzebny; wejść ASW nie ma |

Kasować przy zatrzymanym rezydencie (reguła z pamięci: stan i staging czyta proces) i najlepiej razem z oczyszczeniem punktów 3 i 4.

### Proponowana naprawa

`automation.py:839`: retencjonować tylko zlecenia `PAUSED` lub takie, których wejścia z dziennika nadal istnieją (`RunJournal.load` + `validate_inputs`
już są używane w `_inspect_journal`, `automation.py:1287`). Pozostałe staging dostaje się do istniejącego `cleanup_orphaned_temp`
przy następnym uruchomieniu zlecenia. Marker-less katalogi usunąć jednorazowo ręcznie (nie warto kodu).
Test regresyjny najpierw padający: `tests/application/test_automation.py::test_failed_run_with_missing_inputs_is_not_retained_across_restart`
(stan z `FAILED` i nieistniejącym wejściem + katalog `run-*` z markerem martwego PID → po `AutomationOwner(...)`
i starcie nowego runu katalog znika; dziś zostaje).

### Odzysk

Nie dotyczy (czyszczenie, nie utrata danych).

---

## 6. Timeouty TTS

### Przebieg (DIRECT, log)

Nie 20:0x, tylko 24.10 19:33:25 (lokalnie), w uruchomieniu odcinka Even the Student Council S01E04 (grupa `776f0949`).
W jednej sekundzie 19 ostrzeżeń `TTS retry 1/3 scheduled in 5.000s` z `TTS_TIMEOUT`, `request_rank` 0-17 i 19
(żądanie 18 się powiodło). Brak ostrzeżeń drugiej próby, brak błędu, `Audio render started` 19:34:04, grupa w `ready` 19:34:13.
Render audio ruszył z 454 klipami (log `Audio render started`). Efekt: 19 klipów spóźnionych o około 50 s (45 s limitu + 5 s opóźnienia).

### Konfiguracja (DIRECT)

- `requests[*].settings`: `tts_request_concurrency: 85` we wszystkich 162 zleceniach; 85 to wbudowana domyślna wartość profilu Dallin
  (`config/user_settings.py:215`), nie przypadkowe ustawienie.
- `runtime.py:127` limit żądania ElevenBytes 45 s (`_TTS_REQUEST_TIMEOUT_S`), `runtime.py:130` opóźnienia ponowień 5/10/15/30 s,
  `runtime.py:651` timeout schedulera włączony (VPN wyłączony).
- `scheduler.py:231` `asyncio.timeout(self._timeout_s)` obejmuje całe `engine.synthesize`; `api_backend.py:74` pula `httpx` ma
  `max_connections = max_concurrency = 85`; scheduler tworzy 85 workerów (`scheduler.py:115`), kolejka `2 * 85`.

### Czy współbieżność to przyczyna

Wzorzec (DIRECT): timeouty tylko w pierwszej fali (rank 0-19), w tej samej sekundzie, bez kolejnych. To pasuje do zimnego startu
proxy `teamsp.org/xi/run6.php` lub jednoczesnego otwarcia 85 połączeń TLS, a nie do stałego przeciążenia (wtedy timeouty rozkładałyby się na późniejsze fale).
Statystyka z całego logu (`p19.py`, 27 dni, około 140 renderów audio): `TTS_TIMEOUT` łącznie 2, 1, 4, 2, 2, 1 i dziś 19, czyli
jednorazowy skok; poważniejsze były `TTS_ENGINE_UNAVAILABLE` (14.10: 81, 17.10: 210, 18.10: 38) i `TTS_CLIP_INVALID` (17.10: 152),
które wyglądają na awarie dostawcy, a ostatnia seria zakończyła zlecenie Yasei 04 po 4 próbach.
ASSUMED: współbieżność 85 może zwiększać ryzyko throttlingu proxy; log retry nie zawiera statusu HTTP ani czasu, więc nie da się tego rozstrzygnąć
z danych. Nie ma dowodu, że 85 jest przyczyną tych 19 timeoutów.

### Wpływ

Pomijalny (opóźnienie pierwszej fali), ale seria `ENGINE_UNAVAILABLE` z 17.10 kosztowała całe zlecenie.

### Zalecenie

Nie zmieniać 85 na podstawie tego jednego zdarzenia. Zamiast tego:
1. Dodać do logu retry status HTTP i czas żądania (`api_backend.py`, pole w `TtsTimeoutError`/`TtsProviderUnavailableError.context.details` już istnieje jako mechanizm), żeby kolejne zdarzenie dało dowód.
2. Opcjonalnie rozpędzić pierwszą falę (stopniowe wypuszczanie workerów w `TtsScheduler.__init__`) zamiast 85 naraz. Test: `tests/services/tts/test_tts_contract.py::test_first_wave_is_ramped_up` (po `N` pierwszych żądaniach liczba równoczesnych wywołań rośnie stopniowo; dziś wszystkie startują jednocześnie).
3. Jeśli seria powtórzy się w pierwszych sekundach przebiegu, wtedy zmierzyć 40/60 równoczesnych żądań; do tego czasu ASSUMED.

### Odzysk

Nie dotyczy (przebieg zakończony). Dla Yasei 04 odzysk już nastąpił (punkt 3).

---

## Kolejność proponowanych działań

1. Punkt 1: decyzja właściciela (odrzucanie wydań bez napisów) + odzysk dwóch odcinków przez napisy lub inne wydanie.
2. Punkt 5 i 3: zwolnienie retencji martwych zleceń (jedna zmiana w `automation.py:839`) i jednorazowe sprzątanie katalogów.
3. Punkt 4: anulować 22 wpisy `uncertain` przez `transfer cancel` po sprawdzeniu klienta.
4. Punkt 6: najpierw logowanie statusu HTTP, bez zmiany współbieżności.
5. Punkt 2: opcjonalne ostrzeżenie o rozjazdzie dat.

Skrypty pomocnicze: `C:\Users\MATTYM~1\AppData\Local\Temp\claude\c--Users-MattyMroz-Desktop-PROJECTS-AniShift\b1c6e9d7-f377-43d2-802f-da71c0f1b1b3\scratchpad\stalls\`
(`lg.py` filtr logu po czasie, `p5.py` odtworzenie gotowości grup, `p9/p13/p20.py` analiza zleceń, `p14.py` acquisitions `uncertain`, `p16.py` staging, `p19.py` statystyka TTS).

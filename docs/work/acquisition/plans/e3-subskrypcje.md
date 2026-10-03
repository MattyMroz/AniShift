---
kind: plan
status: draft v4.1 (v4 PASS WITH FINDINGS w czwartym review `astra`; trzy drobne poprawki)
baseline: 200de8a na work/acquisition/03-subscriptions
created: 2026-10-02
---

# Plan E3: subskrypcje na wspólnym mechanizmie E2

## 1. Status, rezultat, authority

**Status:** szkic v4 do ponownego review `astra`. Wykonanie po PASS planu. Wersja 2 wprowadziła
poprawki 14 findingów pierwszego review i decyzje orkiestratora A–E z 2026-10-02 (§1.3).
Wersja 3 poprawia 10 findingów drugiego review. Cztery z nich usuwa uproszczeniami, które
zdejmują całe mechanizmy (§1.3, decyzje F–I): auto-przyjęcie tylko `zgodnych`, H2 na pliku w
stagingu przed rezerwacją nazw, pauza wyłącznie na mechanizmie E2 i domena zamknięcia bez
wyjątków. Wersja 4 poprawia 5 findingów trzeciego review. `previous` następnej próby wynika
wprost z reguły `_admission_refusal`. Własność pauzy jest niezmiennikiem stanu, stosowanym
przy każdym zapisie, a nie oceną w rundzie. W pauzie żaden zegar próby nie biegnie. Wynik H2
jest związany z tożsamością pliku (`file_stamp`) sprawdzaną przy kopiowaniu.

**Jeden rezultat:** subskrypcja (wpis AniList + Kitsu ID + punkt odcięcia) sama pobiera
nowe odcinki sezonu: znajduje kandydata, zleca go i kontroluje plik po pobraniu.
Po sezonie znika. Działa na tym samym mechanizmie co ręczne „Pobierz” z E2.
Stare subskrypcje przechodzą bez utraty danych i bez masowych pobrań.

**Rezultat użytkownika (H3):** w zakładce Subskrypcje dodaje subskrypcję (`D` → wyszukaj →
`S` → Dodaj), widzi odliczanie, wstrzymuje, szuka teraz, usuwa i cofa (`Ctrl+Z`), a przez
tydzień bez dotykania aplikacji nowe odcinki same trafiają do Biblioteki.

**Baseline:** `200de8a` (`docs(repo): record owner acceptance of e2 and the e3 execution loop`),
branch `work/acquisition/03-subscriptions`; drzewo czyste poza dwoma nieśledzonymi plikami
researchu (`research/e3-wymagania.md`, `research/e3-stan-kodu-subskrypcji.md`). Ostrzeżenia
`Permission denied` dla `workspace/temp/pytest-*` są nieszkodliwe.

**Znane wcześniejsze failures (flaky, nie blokują gate'u przy jednym czystym powtórzeniu):**
`test_material_identity_survives_bundle_metadata_preparation_processing_and_ready[True]`,
`test_selected_pack_…` (port UDP / start qB), `test_resident_repeat_preserves_a_local_source…`
(`WinError 32`), `test_private_clients_download_concurrently_reconnect_and_stop_independently`
(okno qB na pulpicie).

### 1.1 Authority

| Źródło | Rola |
| --- | --- |
| `docs/work/acquisition/spec.md` §4 (U-01–U-25), §5.4 (S-01–S-15), §5.5, §5.6 (M-01–M-07), §6 (Q), §7 (I), §13 (PR) | wymagania |
| `docs/work/acquisition/masterplan.md` §E3 (l. 103–107) | rezultat i zakres etapu |
| `docs/work/acquisition/plans/e1-przeplyw-subskrypcji.md` §3–§5 | maszyna stanów, parametry P-1–P-10, H2, cień, rejestr |
| `docs/work/acquisition/ux.md` §8–§13 (U06, U07, U08, stany, H3, klawisze) | zachowanie UI |
| `docs/work/acquisition/plans/e2-pobieranie.md` §8–§13, `outcomes/e2.md` | mechanizm E2 do reuse, forma planu |
| `docs/work/acquisition/plans/e2-refaktoryzacja.md` B1, C1, D1 (l. 298–321) | decyzje przekazane do E3 |
| `docs/work/acquisition/petla-wykonania.md` | pętla wykonania (wiążąca) |
| `docs/work/acquisition/research/e3-wymagania.md`, `research/e3-stan-kodu-subskrypcji.md` | inwentarz wymagań i kodu; numery linii zweryfikowane niżej w kodzie |
| `AGENTS.md` root, `anishift/AGENTS.md`, `anishift/application/AGENTS.md`, `anishift/cli/AGENTS.md`, `anishift/services/AGENTS.md`, `anishift/services/media/AGENTS.md`, `tests/AGENTS.md` | reguły repo i pułapki |

Decyzje oznaczone **[DO-2026-10-02]** to decyzje orkiestratora z 2026-10-02, które
właściciel ma jeszcze potwierdzić. Właściciel przekazał je słowami „lecimy, nie pytaj”.
Wykonanie na nie nie czeka.

### 1.2 Odchylenia od wcześniejszych dokumentów

| Nr | Dokument | Było | Jest w E3 | Powód |
| --- | --- | --- | --- | --- |
| O-1 | `petla-wykonania.md` §E3; E2 (naprzemienność autorów) | autorzy faz naprzemiennie | autor wszystkich faz `opus55`, recenzent `astra` | decyzja właściciela 2026-10-01/02 (`petla-wykonania.md:43`) |
| O-2 | `masterplan.md:106` „odczyt `ffprobe` w `services/media`” | nowy adapter `ffprobe` | H2 czyta czas i liczbę strumieni przez istniejący `MediaProbe.identify` (`DefaultMediaProbe`, `services/media/probe.py:30-56`): MKV → `mkvmerge -J`, MP4 → `ffprobe`. Kontrolowany jest kompletny plik w stagingu transferu, który ma oryginalną nazwę z rozszerzeniem, przed rezerwacją nazw publikacji (D-29). Nowego adaptera ani zmiany `probe.py` nie ma | reuse; `MediaCatalog` ma już `duration_us` i ścieżki (`services/media/types.py:51-71`). Subskrypcja przyjmuje wyłącznie obsługiwane kontenery (U-06), więc dla MKV czas pochodzi z kontenera, nie ze strumienia wideo jak w helperze. Przy trybie „tylko zapis” (D-07) ta różnica nie decyduje o przyjęciu. **[DO-2026-10-02]** |
| O-3 | `spec.md` S-15, `e1-przeplyw` §5.5 „przełącznik aplikacji” | bez określenia formy | przełącznik to pole `Settings.subscription_shadow` (env `ANISHIFT_SUBSCRIPTION_SHADOW`), bez UI | YAGNI; przełącznik nie jest bramką i nie służy właścicielowi na co dzień. **[DO-2026-10-02]** |
| O-4 | `e1-przeplyw` §3.6 w. 21 i `spec.md` S-11 (przed 2026-10-02: „aktywna próba kończy się” w pauzie globalnej) | próba trwa w pauzie globalnej | **Decyzja orkiestratora A w brzmieniu v4:** pauza globalna `O` działa jak w E2. Nie przyjmuje nowych prób. Zatrzymuje trwające transfery automatu z zastosowaną selekcją (`applied_revision > 0`), w tym próby subskrypcji, a wznowienie je kontynuuje. Transfer w fazie metadanych nie jest zatrzymywany, bo E2 nie umie bezpiecznie wznowić transferu zatrzymanego przed listą plików (D-30). Owner w pauzie go nie obserwuje ani nie rozlicza. **Żaden zegar próby (zastój, metadane) nie nalicza czasu pauzy, a czas naliczony przed pauzą zostaje** (D-30). Pauza pojedynczej subskrypcji (S-07) nie zatrzymuje próby. `spec.md` S-11 i `e1-przeplyw` §3.6 w. 21a zsynchronizowano z adnotacją „decyzja orkiestratora 2026-10-02, potwierdzone przez właściciela 2026-10-02” | jeden kontrakt pauzy dla całego automatu; jedna reguła zegarów zamiast osobnej dla metadanych |
| O-5 | — | usunięte w v2 | Decyzja orkiestratora C: U-22 obowiązuje w pełni (D-27) | — |
| O-6 | `spec.md:57` (`AutomationPolicy`: 3 h, 1 h, 72 h) | harmonogram z polityki | harmonogram U-14 jako stałe w nowym czystym module (§5.5). Pola polityki zostają w schemacie (bez migracji usuwania), nowy kod ich nie czyta | U-14 zastępuje L:R-010 (`spec.md:281`, PR-03 `spec.md:295`) |
| O-7 | `e1-przeplyw` §3.3 „bramka przyjęcia = H2 + U-07/U-08” | U-07/U-08 w bramce | w E3 bramka = H2. U-07/U-08 to E4 (`e3-wymagania.md` §6.1) | zakres etapów masterplanu. Ryzyko przejściowe przyjęte w `masterplan.md:151`. **[DO-2026-10-02]** |
| O-8 | `spec.md` W-08 (fallback Nyaa przy braku tytułu w AniList) | przejście na Nyaa | zostaje zachowanie zastane po E2: „Nie znaleziono tytułu”, bez fallbacku (`cli/AGENTS.md`, „Empty AniList results…”). E3 niczego tu nie zmienia | decyzja z `masterplan.md:175` nie jest potrzebna do E3, bo drogi nie ma już w UI. Usunięcie zaplecza Nyaa to E5 |
| O-9 | `e1-przeplyw` §3.3 l. 82-84 i §3.6 w. 6; `e1-heurystyka-wyszukiwarka-weryfikator.md` H-3 | `niepewny` przyjmowany automatycznie po `T_niepewny`, gdy numer w nazwie wskazuje cel i nie ma jawnej sprzeczności | **Decyzja F:** w E3 subskrypcja przyjmuje automatycznie wyłącznie `zgodne` (D-10). Cel, dla którego są tylko `niepewne`, zostaje „Czeka na wydanie” i podlega S-14. Szczegóły (U08) i „Szukaj teraz” pokazują liczby według werdyktu, a D/I/P pozwalają pobrać `niepewne` ręcznie (R-06, `ux.md:126`, `161`). `T_niepewny` (P-2) w E3 nie jest używany | Warunek „numer wskazuje cel” nie ma w H1 źródła prawdy. Werdykt i powód go nie ustalają (§2.1), a każda próba wyprowadzenia go z parsera zostawiała luki (`12.5`, numeracja sezonowa, powód reszty nazwy maskujący sprzeczność paczki). Dane: egzamin 2 H1 v10.3 dał 0 błędnych `zgodnych` na 3 911 rekordach. Pokrycie `zgodny` poprawnych kandydatów wynosi 69,6% dla tytułów 2021+ (96/138) i 46,9% ogółem (303/646). `zgodny ∪ niepewny` daje 93–100% odcinków (`outcomes/e1.md:31`, `masterplan.md:92`). Na odcinek jest zwykle kilku poprawnych kandydatów Torrentio, więc pokrycie per odcinek dla świeżych wydań jest wyższe niż per rekord. To szacunek, nie pomiar: korpus nie ma metryki per odcinek dla v10.3. Pomiar daje rejestr `check` w H3 (§9.1). Luki H1, które zostają w ścieżce ręcznej: Director's Cut/Broadcast/Theatrical/Remastered i `[1440×1080]` dają fałszywe `niepewne`. **[DO-2026-10-02], potwierdzone przez właściciela 2026-10-02 (P-4)** |

### 1.3 Decyzje orkiestratora 2026-10-02 (wiążące dla v2)

| Nr | Decyzja | Gdzie w planie |
| --- | --- | --- |
| A | Pauza globalna działa jak w E2: bez nowych prób, transfery automatu z zastosowaną selekcją zatrzymane i po wznowieniu kontynuowane, faza metadanych nie jest zatrzymywana ani obserwowana. Żaden zegar próby nie nalicza czasu pauzy; czas naliczony przed pauzą zostaje (v4, D-30, potwierdzone przez właściciela 2026-10-02). Zsynchronizowano `spec.md` S-11 i `e1-przeplyw` §3.6 w. 21a | O-4, D-30, §5.5, E-9 |
| B | Paczka mieszana: transfer z choć jednym aktywnym przypisaniem ręcznym jest ręczny dla pauzy („manual wins”), niezależnie od kolejności dołączania. W pauzie owner stosuje własność pauzy jako niezmiennik przy **każdym** zapisie stanu, więc nie zależy od tego, czy biegnie runda transferów (v4). Testy obu kolejności i restartu | D-04, §5.6, E-13 |
| C | U-22 obowiązuje: pełne ostatnie mapowanie ani.zip, przyjęte z odczytu na żywo, jest trwałe w rekordzie. Awaria ani.zip (wyjątek albo pusta odpowiedź 404) nie blokuje działających subskrypcji, także po restarcie. H1 bez zmian; O-5 usunięte | D-27, §5.2, §5.6, E-14 |
| D | Autozamknięcie tylko po rzeczywistym spełnieniu (pobrano/gotowe) **wszystkich** trwałych celów. Samo zlecenie (`manual`, `legacy_ordered`) nie spełnia. Cel poza zmniejszoną liczbą odcinków nie wypada z domeny: blokuje zamknięcie i jest widoczny jako konflikt do rozliczenia przez użytkownika (v3) | D-23, §5.4 `completed`, E-8 |
| E | Pozostałe findingi poprawione według minimalnych poprawek recenzenta albo inną uzasadnioną drogą (raporty v2 i v3) | całość |
| F | Subskrypcja przyjmuje automatycznie tylko `zgodne`; `niepewne` zostają w ścieżce ręcznej (v3, potwierdzone przez właściciela 2026-10-02) | O-9, D-10, E-4, P-4 |
| G | H2 sprawdza kompletny plik wideo w stagingu transferu przed rezerwacją nazw publikacji. Odrzucona próba nie ma więc publikacji, a jej przypisanie po potwierdzonym anulowaniu przestaje być chronione (v3). Wynik przyjęty zapisuje się razem z rezerwacją i z `file_stamp` sprawdzonego pliku; kopiowanie wymaga tej samej tożsamości pliku (v4) | D-12, D-29, §5.7 |
| H | Każdy odczyt ani.zip na potrzeby subskrypcji zwraca jeden wynik: projekcję, użyte mapowanie i jego pochodzenie (na żywo albo z zapisu). To samo mapowanie trafia do oceny kandydatów w tym samym sprawdzeniu (v3) | D-27, §5.3 |
| I | Stare potwierdzenia nie są zmieniane w migracji. Ich zakres trafia do `legacy_orders`, więc referencje konfliktu P nie zmieniają się (v3) | D-14, §5.14 |

## 2. CURRENT STATE → GAP → TARGET

### 2.1 Stan aktualny (zweryfikowany w kodzie)

| Twierdzenie | Dowód | Status |
| --- | --- | --- |
| Subskrypcje żyją w osobnym pliku `config/subscriptions.json` (schemat 4) zapisywanym przez `SubscriptionStore`, nie przez ownera | `application/subscriptions.py:417-457` (`SubscriptionStore.load/save/_upgrade`); `bootstrap.py:142-152` | verified |
| Model starej subskrypcji: seria + grupa wydań Nyaa, `taken_episodes`, `episodes: tuple[EpisodeOrder]`, `end_state`, `anilist_id: int \| None`, `added_at`, `enabled` | `subscriptions.py:196-311` | verified |
| Sprawdzanie: owner wywołuje `SubscriptionService.check_due` na puli I/O. Wyszukanie przez Nyaa po grupie, przyjęcie bez klucza odcinka (`AcquisitionConfirmation` z `subscription_id`, `legacy_scope`) | `automation.py:3714-3755`, `3826-3890`; `3756-3800` (`_schedule_subscriptions`, `_poll_subscriptions`) | verified |
| Mutacje subskrypcji z panelu idą przez receipt „pending” i drugi plik: `_finish_local_command` stosuje je do `SubscriptionService` po zapisie receipt | `automation.py:6277-6344`; `416-419`, `439`, `444` (rodzaje poleceń) | verified |
| Ochrona I-06 dla starych zleceń liczy `LegacyScope` z `subscriptions.json` przy każdym przyjęciu (`_legacy_scopes`). Nieczytelny plik → odmowa `LEGACY_UNREADABLE` | `automation.py:4702-4731`, `4534-4536`, `3899` | verified |
| Ręczne „Pobierz” E2: `prepare_episode(key)` → H1 `suggestion` → `_admit_episode` z `AdmissionSource.MANUAL`, origin `USER`, jeden zapis z receipt, potem cykl transferów | `automation.py:4504-4568`, `4570-4654`; `episode_selection.py:445-458` | verified |
| `AdmissionSource` ma tylko `MANUAL`, `LEGACY`; `EpisodeAssignment` nie ma pól próby ani wyniku kontroli | `control.py:194-199`, `400-422` | verified |
| Publikacja zestawu do roota (= wejście do Auto) następuje w `_settle_publication` po `publish_set`. Prywatna kopia w `publication_path` istnieje wcześniej | `automation.py:5330-5351`, `5409-5421` | verified |
| `WatchState` schemat 3, bez pola subskrypcji. Kopia `.e2-migration.bak` obu plików przed pierwszym zapisem schematu 3 | `control.py:79`, `822-838`; `watch_state.py:94`, `311-378` | verified |
| Powiadomienia: owner publikuje zdarzenie `notification`, rezydent pokazuje dymek przez `TrayIcon.notify`. Jednokrotność chroni `WatchState.notified` | `automation.py:6868-6932`; `platform/tray.py:192` | verified |
| Rejestr decyzji: `append_decision(path, kind, payload)` z białą listą pól `_FIELDS`, bez pola `attempt` | `acquisition_decisions.py:92-200` | verified |
| H2 istnieje tylko jako skrypt `scripts/tmp/download_verification.py` (gitignored): `expected_episode`, `MediaProbe`, `verify(mode="record_only")` (odrzuca wtedy tylko `no_video_stream`), `next_step` | `scripts/tmp/download_verification.py:58-264` | verified |
| ani.zip zachowuje surowy obiekt odcinków (`AniZipMapping.raw_episodes`), więc `length`/`runtime` są dostępne. AniList w kodzie nie pobiera `duration` | `episode_selection.py:221-231`; brak `duration` w `services/catalog/anilist.py` (grep) | verified |
| `EpisodeListing` daje `status`, `episode_count`, `aired`, `kitsu_id`, odcinki z `airs_at` i `airs_at_fallback` (data ani.zip). Daje też `schedule_warning`/`schedule_retry_at` | `episode_selection.py:198-247` | verified |
| Panel: zakładka „Subskrypcje” w `StateController` korzysta ze starego `SubscriptionDraft`, poleceń `subscription_get/range/repeat/enable/disable/remove`, `subscriptions_check` i `subscription_retry_prepare` | `cli/interactive/state.py:82`, `453-656`, `941-994`, `1219-1330`; `cli/interactive/subscriptions.py:1-124`; `cli/resident.py:127-374` | verified |
| W Anime (U03) klawisz `S` nie ma obsługi (D5 z E2) | brak trafień `text:s` w `cli/interactive/anime*.py` (grep); `cli/AGENTS.md` „no … subscription-creation route” | verified |
| Technika `anishift subs list/remove/check` czyta `SubscriptionService` wprost i woła stare rodzaje IPC | `cli/main.py:359-420` | verified |
| Stara pętla `run_daemon` (tylko testy porównawcze) woła `service.subscriptions.check_all()` | `cli/watch.py:245-261` | verified |
| Limit ramki IPC 1 MiB | `platform/local_control.py:70` `MAX_FRAME_BYTES` | verified |
| Owner ma wstrzykiwany zegar `clock: Clock = lambda: datetime.now(UTC)` | `automation.py:481`, `573`, `586` | verified |
| `SubscriptionStore.load()` dla wersji < 4 zapisuje plik (`_upgrade` → `save`), więc nie jest odczytem bez skutków | `subscriptions.py:435-456` | verified |
| `WatchStateStore.load()` bez `state.json` zwraca stan domyślny bez żadnej migracji | `watch_state.py:332-335` | verified |
| Prywatna kopia publikacji to `publication_path / str(file.index)`, bez rozszerzenia; `DefaultMediaProbe.identify` wybiera adapter po rozszerzeniu i dla innego rzuca `UnsupportedMediaError` | `automation.py:7207-7211`, `5331-5335`; `services/media/probe.py:43-56` | verified |
| `_publish_episode` najpierw zapisuje `EpisodePublication` (rezerwacja nazw, `_reserve_publication`), potem kopiuje z `staging_path(root, operation_id)` do prywatnej kopii, potem `publish_set`. Plik w stagingu ma ścieżkę torrenta z oryginalnym rozszerzeniem | `automation.py:5320-5371`; `_copied(data, private, file)` `7207-7211` | verified |
| Kilka starych subskrypcji może mieć ten sam `anilist_id` (różne grupy; ID = seria + grupa + AniList) | `subscriptions.py:381-402` | verified |
| Po potwierdzonym anulowaniu (`FAILED` + `requested_action == "cancel"`) albo `removed_from_client` wypada z `protected_assignments` tylko przypisanie **bez** publikacji (`item.publication is not None` zostaje chronione). `_admission_refusal` z `previous` wymaga, by ostatnie chronione przypisanie klucza miało ten `admission_id`. Bez `previous` każde chronione przypisanie klucza daje `episode_admitted` | `control.py:514-520`, `951-963`; `automation.py:4193-4200`, `4680-4688` | verified |
| `_replace_episode_scope` oznacza poprzednie przypisanie `replaced=True` i podnosi `selection_revision`. Zastąpione przypisanie zostaje chronione (konflikty, pliki), ale wypada z `active_assignments` i `wanted_files`. Start nowej treści czeka na `_replacement_ready` (zastosowana rewizja poprzedniego zakresu) | `automation.py:7094-7101`, `5293-5310`; `control.py:509-512` | verified |
| `AniZipCatalog.mapping()` dla 404 zwraca pusty `AniZipMapping` (bez Kitsu ID i odcinków), a nie wyjątek | `services/catalog/anizip.py:49-50` | verified |
| Pamięć mapowań `AcquisitionService` (`_Remembered`) żyje tylko w procesie i ma limit wpisów (LRU). Restart ją czyści | `acquisition.py:392-402`, `831-836` | verified |
| `episodes()` przy awarii AniList zwraca listę z `schedule_warning` i bez dat AniList, zamiast błędu | `acquisition.py:764-783` | verified |
| Zastój liczy `TransferInspector` z kolejnych obserwacji. `idle_s` rośnie tylko między dwiema obserwacjami w stanie pobierania (`_DOWNLOADING_STATES`, w tym `metaDL`). `reset_clock()` zachowuje naliczone `idle_s` i wyklucza przerwę; `restart_idle()` usuwa pomiar. Timeout metadanych to `idle_s >= METADATA_TIMEOUT_S` | `transfers.py:50-52`, `127-130`, `232-261`; `automation.py:5137-5142` | verified |
| `_record_progress` **zastępuje** całą mapę pomiarów rekordami z bieżącej inspekcji, więc pomiar hasha pominiętego w tej inspekcji przepada. `inspect()` bez potwierdzeń wraca przed `_record_progress` i mapy nie rusza | `transfers.py:139-144`, `232-247` | verified (review v3 finding 3) |
| `_schedule_transfers` i `_poll_transfers` biorą potwierdzenia `_polled(...) and _working(...)` albo z oczekującą akcją (`_transfer_action`). W pauzie `_working` jest prawdziwe tylko dla `manual`. `_settle_selection` (z timeoutem metadanych) i `_publish_episode` wymagają `_may_settle` → `_working`. W pauzie owner więc nie obserwuje i nie rozlicza transferów automatu, ale wykonuje ich oczekujące akcje | `automation.py:4804-4841`, `4857-4890`, `5127-5142`, `5320-5322`, `7104-7120` | verified (review v3 finding 2) |
| E2 nie zatrzymuje transferu selektywnego przed listą plików: polecenie `stop` dla `applied_revision == 0` daje `TRANSFER_METADATA_PENDING`, a resume zatrzymanego transferu bez listy plików kończy go problemem `_METADATA_STOPPED` („cannot resume safely”), bez ponownego add | `automation.py:6052-6053`, `6164-6166`, `2627`; `application/AGENTS.md` („Resume bez potwierdzonej selekcji…”) | verified |
| W pauzie polecenie `transfer resume` dla nieręcznego transferu jest odrzucane (`PAUSED`) | `automation.py:6050-6051` | verified |
| Jedynym zapisem stanu ownera jest `_save(candidate)`; `_commit` i wszystkie mutacje przez niego przechodzą. `_stopped_transfers` **nadpisuje** `pause_owned_transfers` zbiorem z bieżącego wyliczenia | `automation.py:6359-6382`, `2563-2588` | verified |
| `_episode_assignments(key)` zwraca chronione przypisania klucza posortowane tak, że niezastąpione są na końcu. `_admission_refusal` z `previous` wymaga `matches[-1].admission_id == previous`, a z `previous` pomija kontrolę duplikatu | `automation.py:4193-4200`, `4680-4688` | verified (review v3 finding 1) |
| `_replace_episode_scope` podnosi `selection_revision` także wtedy, gdy wskazane przypisanie jest już `replaced` | `automation.py:7094-7101` | verified |
| `copy_staged` sprawdza `file_stamp` źródła tylko w trakcie kopiowania (przed i po). `file_stamp` = (rozmiar, `mtime_ns`, urządzenie, inode) zwykłego pliku. Kopia wideo powstaje w `_copied` tylko, gdy `PublishedFile.stamp is None` | `acquisition_staging.py:93-125`; `automation.py:7207-7211` | verified (review v3 finding 4) |
| Pauza zatrzymuje tylko nieręczne transfery z `applied_revision > 0` (`_working_transfers`). Wznowienie (`_resumed_transfers`, `_resumable`) dotyczy hashy z `pause_owned_transfers` z rozliczonym stopem pauzy. `_finish_pause_restore` działa w każdej rundzie `_record_transfers`, ale tylko przy `auto_enabled`. `_resumable` filtruje stare subskrypcje przez `_enabled_subscriptions`, które czyta `subscriptions.json` | `automation.py:2563-2639`, `5488`, `7254-7279` | verified |
| `_episode_conflict_reference` hashuje m.in. `encode_view(item.legacy_scope)`, więc zmiana `legacy_scope` zmienia referencję konfliktu | `automation.py:7086-7091` | verified |
| `episode_states` przyjmuje 1–100 kluczy jednego wpisu. Panel Anime pyta tylko o wyemitowane odcinki, w partiach | `episode_commands.py:107-115`; `cli/interactive/anime.py:1130-1143` | verified |
| `AutomationOwner` rezydenta powstaje w `cli/watch.py`, nie w `bootstrap.py` | `cli/watch.py:352-364` | verified |
| Rejestr odrzuca pole spoza `_FIELDS` | `acquisition_decisions.py:45`, `94` | verified |
| Nowe przypisanie dołącza do istniejącego aktywnego transferu tego hasha bez zmiany `origin`. `manual` liczy się z `origin` i `subscription_id` całego potwierdzenia, więc o pauzie decyduje pierwszy autor transferu | `automation.py:4598-4621`; `control.py:497-502` | verified |
| H1 zwraca `INSUFFICIENT` także przed oceną numeru (rok, reszta nazwy, nawias, sąsiednie dzieło) oraz przy braku albo niezgodności numeru. Werdykt i powód nie mówią, czy numer w nazwie wskazuje cel. Powód reszty nazwy jest zwracany przed kontrolą paczki, więc może maskować sprzeczność sezonu paczki. Parser czyta `12.5` jako numer 12 z resztą `5` | `episode_identity.py:1168-1253`, `675-687`; review v2 finding 1 | verified |
| `_aired` zwraca `None` dla każdego statusu poza `RELEASING` z harmonogramem i `FINISHED` (HIATUS, brak harmonogramu) | `episode_selection.py:584-589` | verified |
| Anime blokuje otwarcie zapowiedzi: `_start_franchise` i `_start_episodes` wracają dla `NOT_YET_RELEASED` | `cli/interactive/anime.py:1061-1064`, `1113-1118` | verified |
| `_mapping()` po wygaśnięciu cache czyta ani.zip ponownie i propaguje błąd, więc `prepare_episode` pada przy awarii ani.zip | `acquisition.py:789-793`, `838-850` | verified |
| `_episode_conflicts` czyta `service.subscriptions` i buduje referencje konfliktu z `taken_episodes` i `EpisodeOrder` (wejście potwierdzenia P przy konflikcie legacy) | `automation.py:4202-4229`; wywołania `4274`, `4368`, `4542` | verified |
| Nieczytelny `subscriptions.json` już dziś blokuje każde przyjęcie D (`LEGACY_UNREADABLE`) | `automation.py:4675-4679`, `4702-4710` | verified |

### 2.2 Gap (przyczyny, dla których subskrypcje dziś nie spełniają E3)

1. **Drugi model i drugi plik.** Subskrypcja to grupa wydań Nyaa w osobnym pliku. Jej
   przyjęcia nie mają klucza odcinka (`legacy-unkeyed`, `outcomes/e2.md:188`), więc I-06
   wobec ręcznego „Pobierz” jest tylko przybliżeniem przez `LegacyScope`.
2. **Zły harmonogram.** 3 h opóźnienia, okno 72 h i twarde porzucenie (`spec.md:57`, `281`)
   zamiast U-14 i powiadomienia po 7 dobach.
3. **Brak maszyny stanów celu i próby.** Nie ma limitu 3 prób, wykluczania wypróbowanych
   par, kontroli H2 przed Auto ani autozamknięcia.
4. **Brak drogi UI.** Nie ma `S` w U03, szkicu U06, listy U07 z odliczaniem, szczegółów U08
   ani `Ctrl+Z`.
5. **Mutacje przez dwa pliki.** Receipt „pending” plus drugi zapis (`automation.py:6277-6344`)
   to druga ścieżka spójności obok zwykłego zapisu ownera.

### 2.3 Target (skrót)

- Subskrypcja i jej cele są częścią `WatchState` (schemat 4), jedyny autor: `AutomationOwner`.
- Próba celu = zwykłe przyjęcie E2 przez `_admit_episode` z `AdmissionSource.SUBSCRIPTION`,
  kluczem `EpisodeKey`, `RequestOrigin.BACKGROUND` i numerem próby. I-06 działa jak dla
  „Pobierz”.
- Czysty moduł `subscription_targets.py` liczy przynależność, terminy U-14/U-15, stan celu po
  zamknięciu próby, dopuszczalność kandydata i autozamknięcie, bez I/O i z jawnym `now`.
- H2 (`download_verification.py` w `application/`) kontroluje kompletny plik wideo w stagingu
  przed rezerwacją publikacji, a kopia wymaga tej samej tożsamości pliku (D-29). Wynik
  „przyjęta” to jedyna droga pliku próby do Auto.
- Panel: `S` w U03 → U06; zakładka Subskrypcje (U07) z odliczaniem i `D/W/F/Del/X/Ctrl+Z`;
  U08 = istniejący widok odcinków Anime z nagłówkiem subskrypcji.
- Migracja: jednorazowe przeniesienie `subscriptions.json` do schematu 4 przy wczytaniu, z
  kopią `.e3-migration.bak` obu plików. Po migracji `subscriptions.json` jest zamrożony.
- Stara ścieżka subskrypcji (sprawdzanie Nyaa, polecenia, receipt „pending”, stary szkic
  panelu) zostaje usunięta w zakresie, którego wymaga migracja (C1). Reszta zaplecza grup
  zostaje do E5.

## 3. Zakres

### 3.1 In scope

S-01, S-03–S-09, S-11–S-15; M-01–M-07; U-01 (dla subskrypcji), U-02, U-03, U-08 (limit 3 prób),
U-09–U-16, U-19, U-20, U-22; I-01–I-08 dla nowej ścieżki; Q-01–Q-08 dla nowych poleceń i
widoków; H2 w trybie „tylko zapis” w przepływie; rejestr decyzji (`check`, `selection`,
`attempt`, `escalation`, `proposal`); tryb cienia; aktualizacja scoped `AGENTS.md` i
`README.md` w zmienianych obszarach; `outcomes/e3.md`.

### 3.2 Out of scope (z powodem)

- U-07/U-08 (język i napisy po pobraniu), automatyczna wymiana wydania bez napisów, N-05 — E4.
- Usunięcie zaplecza grup Nyaa (`search_title`, `_group_queries`, `catalog_releases`,
  `order_groups`, `ResidentSession.search/download`, polecenie ownera `download`), `run_daemon`,
  flagi `--resident`, czytnik `subscriptions.json` po migracji — E5 (`e2-refaktoryzacja.md` D1).
- Biblioteka jako widok tytułów — E6.
- Pobieranie zaległych wyemitowanych odcinków przez subskrypcję (S-02 usunięte), dodatki/OVA w
  subskrypcji, kolejne sezony, filmy w subskrypcji, drugie źródło wydań (RSS Nyaa z
  `outcomes/e1.md:543-545`: U-02 rozstrzyga Torrentio jako jedyne źródło; opóźnienie
  indeksowania mierzy rejestr `check`, D-17).
- Strojenie P-2/P-5 i decyzja H2 §5.4 (zostaje/wypada) — po zebraniu rejestru, poza E3.
- Rotacja `decisions.jsonl` (D-16).

### 3.3 Forbidden

- Drugi owner, drugi scheduler, drugi rejestr przyjęć, zapis stanu poza `AutomationOwner`
  (I-01), odtwarzanie stanu z `decisions.jsonl` lub Historii.
- Zapis do `subscriptions.json` po migracji; usunięcie lub nadpisanie tego pliku i kopii.
- Fallback „największy plik”, pobieranie całej paczki, `deleteFiles=true`, dotykanie torrentów
  spoza prywatnego profilu (I-04).
- Zwiększanie `MAX_FRAME_BYTES` zamiast ograniczenia odpowiedzi (Q-08).
- Nowa zależność; ręczna edycja `pyproject.toml`.
- Zmiana H1 (`episode_identity.py`, golden) bez procedury z `application/AGENTS.md`.
- Druga paleta, druga lista zakładek, drugi edytor tekstu lub drugi renderer w panelu
  (`cli/AGENTS.md`).
- `sleep` w testach harmonogramu; zegar wyłącznie wstrzykiwany.
- Czytanie prywatnych danych właściciela przez wykonawcę (`config/subscriptions.json`,
  `config/watch/*`, `config/qbittorrent/`, `.env`, `workspace/`). Test na kopii prywatnego stanu
  robi orkiestrator (§9.2).

### 3.4 Deferred

Decyzja H2 §5.4 i ewentualny tryb `enforce` z eskalacją przy powtarzanym odrzuceniu długości
(D-08); P-2/P-5 z rejestru; rotacja rejestru; fallback W-08; usunięcie czytnika starego pliku i
pól `AutomationPolicy` dla starego harmonogramu (E5).

## 4. Decyzje

| Nr | Decyzja | Uzasadnienie | Status |
| --- | --- | --- | --- |
| D-01 | **Source of truth subskrypcji = `WatchState` (schemat 4).** Pola: `subscriptions`, `removed_subscription` (jedno miejsce na `Ctrl+Z`), `legacy_orders` (zmaterializowane `LegacyScope` starych zleceń) | jeden autor i jeden atomowy zapis z receipt (I-01). Znika ścieżka „pending” przez drugi plik i odczyt pliku przy każdym przyjęciu. Stan celu i próby musi i tak siedzieć u ownera (`e1-przeplyw` §3.3, l. 76-78). Rozmiar mały (dziesiątki subskrypcji × kilkadziesiąt celów) | [DO-2026-10-02] |
| D-02 | `subscriptions.json` po udanej migracji jest **zamrożony** (tylko kopia M-07 i źródło migracji). Nikt go nie zapisuje; czytnik usuwa E5 | brak dwóch źródeł prawdy; możliwy downgrade przez przywrócenie kopii | [DO-2026-10-02] |
| D-03 | Uszkodzony lub nieczytelny `subscriptions.json` przy migracji → `ConfigError` przy wczytaniu stanu, rezydent nie startuje (komunikat i wskazówka jak dla uszkodzonego `state.json`: przywróć `subscriptions.json.e3-migration.bak` albo `.v<n>.bak`). Oba pliki zostają bez zmian bajtów. Brak pliku = zero subskrypcji. **Tryb częściowy (ręczne D i Biblioteka bez subskrypcji) nie powstaje.** Bez starego pliku nie da się wyliczyć `legacy_orders`, więc ochrona I-06 przed ponownym zleceniem starych odcinków byłaby fałszywa. Już dziś nieczytelny plik blokuje każde D (`LEGACY_UNREADABLE`, `automation.py:4675-4679`). Panel wymaga rezydenta (`cli/AGENTS.md`), więc tryb częściowy byłby nowym stanem całego ownera | reguła `WatchStateStore` „uszkodzony JSON → `ConfigError`, nigdy pusty stan” (`application/AGENTS.md`); cicha utrata subskrypcji jest gorsza niż odmowa | [DO-2026-10-02], pytanie P-2 |
| D-04 | Pobrania subskrypcji mają `RequestOrigin.BACKGROUND` i `AdmissionSource.SUBSCRIPTION`. **Decyzja B („manual wins”):** `AcquisitionConfirmation.manual` dla potwierdzenia selektywnego wynika z aktywnych przypisań. Jest prawdziwe, gdy choć jedno `active_assignments` ma `source == MANUAL` (albo jest jawnym ponownym pobraniem, `previous_operation_id`), niezależnie od kolejności dołączania i od zapisanego `origin`. Dla potwierdzeń legacy (bez `assignments`) reguła zostaje bez zmian (`control.py:497-502`). Ta sama własność wybiera priorytet USER/BACKGROUND przekazania do przetwarzania. **Pauza stosuje ją jako niezmiennik przy każdym zapisie stanu** (§5.6): w pauzie każdy `_save` zatrzymuje pracujący transfer, który nie jest ręczny, i wznawia wstrzymany pauzą transfer, który stał się ręczny, gdy jego stop pauzy jest rozliczony. Nowej trwałej akcji nie ma: używane są istniejące `pause_owned_transfers` i akcje `stop`/`resume` pauzy, które owner wykonuje także w pauzie (`_transfer_action`) | S-11, priorytet USER > BACKGROUND, wyjątki katalogu dla Auto; własność wyliczana ze stanu działa po restarcie bez migracji | decyzja orkiestratora B |
| D-05 | U03 `S` wraca (S-01) i otwiera U06. Dodatkowo `D` w U07 otwiera U01 (S-04) | spec S-01 obowiązuje. Ukrycie `S` w E2 (D5) dotyczyło E2. H3 krok 1 używa obu (`ux.md:338`) | rozstrzyga konflikt §4.3 researchu |
| D-06 | Daty ani.zip (`airs_at_fallback`) nigdy nie sterują harmonogramem. Odcinek z samą datą ani.zip jest „bez daty” (U-15). UI może pokazać datę z dopiskiem jak dziś (W-06) | U-13 | rozstrzyga konflikt §4.4 |
| D-07 | H2 w E3 działa w trybie **„tylko zapis”** (`e1-przeplyw` §4 l. 221-222, §5.4 l. 326-330): odrzuca wyłącznie `no_video_stream`, rozjazdy długości trafiają tylko do rejestru. Bramka przyjęcia E3 = wynik H2 inny niż odrzucenie | decyzji §5.4 nie podjęto (brak realnej pary; `outcomes/e1.md`, `outcomes/e2.md` bez pomiaru P95); obowiązuje konfiguracja tymczasowa | wg dokumentu |
| D-08 | **Wczesna eskalacja przy powtarzanym odrzuceniu długości: w E3 nie jest implementowana.** W trybie „tylko zapis” długość nigdy nie odrzuca, więc reguła nie miałaby wejścia. Reguła na moment włączenia `enforce` (zapis dla decyzji §5.4): drugie kolejne odrzucenie tego samego celu z tym samym powodem długości (`fragment_duration` albo `compilation_or_extended_duration`) → cel `wyczerpany` z powodem „sprzeczna długość”, bez trzeciej próby | YAGNI. Masterplan każe rozstrzygnąć, co tu robi się w obu wariantach | [DO-2026-10-02] |
| D-09 | Parametry tymczasowe: `T_start` = 0, `T_niepewny` nieużywany w E3 (O-9), `N_prób` = 3, `T_rozdzielczość` = 0, `T_kontroli` = 30 s z jednym ponowieniem, `T_metadane` = istniejące `METADATA_TIMEOUT_S` 600 s (`automation.py:373`), `T_zastój` = istniejące `transfer_stall_s` 30 min (`control.py:121`) | `e1-przeplyw` §4 l. 189-198, 221-222 | wg dokumentu |
| D-10 | **Decyzja F:** subskrypcja przyjmuje automatycznie wyłącznie kandydata z werdyktem `MATCH` (`zgodny`). `INSUFFICIENT` i `MISMATCH` nigdy nie są dopuszczalne dla automatu. Cel z samymi `niepewnymi` zostaje `due` („Czeka na wydanie”), harmonogram U-14 i S-14 działają dalej, a `last_check` pokazuje liczby według werdyktu (S-06). Ręczne D/I/P w U08 pozwala pobrać `niepewnego` istniejącą drogą E2 (R-06). Nie ma nowej funkcji w `episode_identity.py`, zbioru `IDENTITY_CONFLICTS` ani pola `uncertain` | O-9; H1 nie ma źródła prawdy dla warunku „numer wskazuje cel” (§2.1). `zgodny` ma 0 błędów na egzaminie 2. Usuwa całą klasę błędów z review v2 finding 1 (ułamki, numeracja sezonowa, zamaskowana sprzeczność paczki) | [DO-2026-10-02], potwierdzone przez właściciela 2026-10-02 (P-4) |
| D-11 | **Próbę zużywają:** przyjęcie (licznik rośnie przy zapisie przyjęcia), a wynik końcowy zamyka ją jako martwą lub odrzuconą: brak metadanych w `T_metadane`, zastój ≥ `T_zastój`, usunięcie z klienta (`removed_from_client`), niezgodność selekcji, której nie naprawia ponowny odczyt, odrzucenie H2, zastąpienie ręczne. **Nie zużywają:** błąd źródła (sieć, 429, 403), awaria ani.zip/AniList, lokalny błąd publikacji lub I/O (`PUBLICATION_FAILED`, `FINALIZATION_FAILED`). Te ostatnie to problem bez zamykania próby, ponawiany jak w E2. Niejednoznaczny plik w paczce (U-18c) → próba czeka na ręczny wybór U05 (`e1-przeplyw` §3.6 w. 10). Problem jest widoczny w U07, licznik nie rośnie drugi raz | `e1-przeplyw` §3.6 w. 8, 10, 11, 13, 17; błąd dysku nie jest winą wydania | [DO-2026-10-02] dla podziału I/O |
| D-12 | **Zamknięcie próby i następna próba (decyzja G).** Próba martwa albo odrzucona nigdy nie ma publikacji: H2 działa przed rezerwacją nazw (D-29), a martwa nie dotarła do kompletu plików. Zamknięcie zapisuje owner na swoim wątku, w jednym zapisie: wynik próby w przypisaniu (`verification`/powód), stan celu, `tried` i wycofanie zakresu. **Własny torrent** (jedynym aktywnym przypisaniem transferu jest ta próba): istniejące anulowanie bez plików (`requested_action="cancel"`, `automation.py:6054-6091`, I-04). Po potwierdzonym anulowaniu (`FAILED`) przypisanie bez publikacji wypada z `protected_assignments`. **Torrent współdzielony:** zakres próby wycofuje istniejące `_replace_episode_scope` (`replaced=True`, `selection_revision + 1`, priorytet 0 przez zwykłą selekcję E2). Przypisanie zostaje chronione, ale nie blokuje już kompletności transferu. **Następna próba** (`_admit_episode`): `previous` wynika z tej samej listy, którą sprawdza `_admission_refusal` (§2.1), czyli z `matches = _episode_assignments(key)` z bieżącego stanu, liczonego na wątku ownera tuż przed przyjęciem. `matches` puste → `previous=None`. Każde przypisanie w `matches` jest zamkniętą próbą tego celu (`source == SUBSCRIPTION`, ten `subscription_id`, `verification` z odrzuceniem albo zamknięcie z D-11) → `previous = matches[-1].admission_id`. To obejmuje także wcześniejsze próby, nie tylko bezpośrednio poprzednią: np. próba 1 zastąpiona na współdzielonym torrencie (nadal chroniona) i próba 2 anulowana na własnym (już niechroniona) dają `previous` = próba 1. W każdym innym przypadku (przypisanie ręczne, aktywna próba albo przypisanie innej ścieżki) próby nie ma, a cel przechodzi według D-13, więc nowsze zlecenie ręczne zawsze wygrywa. Wynik zależy tylko od trwałego stanu, więc po restarcie jest ten sam. `_replace_episode_scope` nie zmienia przypisania, które już jest `replaced` (bez drugiego podniesienia `selection_revision`, §2.1). Gdy anulowanie własnego torrentu nie jest jeszcze potwierdzone, następnej próby nie ma, a cel czeka (`attempting` z zamkniętą próbą, bez nowego terminu źródła). Trwałe przyjęcie następnej próby i pozwolenie na start jej treści są rozdzielone jak w E2: przyjęcie zapisuje się od razu, a start czeka na `_replacement_ready`, czyli na zastosowaną rewizję poprzedniego zakresu. Deduplikację po restarcie daje receipt `sub:{id}:{number}:{attempt}`. Limit liczy `attempts` celu, nie przyjęcia. Pary (hash, plik) wypróbowane dla celu są wykluczone (`SubscriptionTarget.tried`) | `e1-przeplyw` §3.4 l. 114-116; reuse E2 (§2.1: `protected_assignments`, `_replace_episode_scope`, `_replacement_ready`); review v2 finding 2 | [DO-2026-10-02] |
| D-13 | Ręczne „Pobierz” odcinka będącego celem (D/P w Anime lub U08) → cel `zlecony_ręcznie`. Aktywna próba automatu zostaje zastąpiona (D-12) i liczy się do limitu. Zlecenie ręczne doprowadzone do publikacji → `spełniony`. Kończy się problemem → reguła stanu po zamknięciu (szukanie w pozostałym limicie) | `e1-przeplyw` §3.6 w. 17-19 | wg dokumentu |
| D-14 | **Decyzja I.** Stare zlecenia subskrypcji są w migracji materializowane do `WatchState.legacy_orders` jako `LegacyOrder(anilist_id, number, reference, operation_id, complete)`. Zakres i zbiór wejść liczy dzisiejsza reguła `_legacy_scopes` (`automation.py:4711-4731`), czyli trzy źródła: `taken_episodes`, `EpisodeOrder` ORDERED/COMPLETE oraz stare potwierdzenia z `subscription_id` powiązanej subskrypcji i `legacy_scope is None`. `reference` to **ten sam napis** co dziś w `_episode_conflicts`: `subscription:{id}:{number}` i `subscription:{id}:{number}:{hash}:{acquisition_id}:{repeat_id}` dla zleceń z pliku (`automation.py:4218-4228`), a `_episode_conflict_reference(item)` dla starego potwierdzenia (`automation.py:7086-7091`). **Migracja nie zmienia żadnego `AcquisitionConfirmation`**, także `legacy_scope`, więc referencja z hashem potwierdzenia jest identyczna przed migracją, po niej i po restarcie. Potwierdzenie P przy konflikcie legacy wiąże te same tożsamości. `operation_id` = ID starego potwierdzenia (dla zleceń z pliku `None`). `complete` = stan `COMPLETE` starego `EpisodeOrder`; dla potwierdzenia spełnienie czyta się na żywo z jego stanu (D-23), bo stare transfery trwają dalej (M-06). Cel pokryty starym zleceniem → `zlecony_ręcznie` z powodem `legacy_ordered` (M-02) | U-16; jedna reguła zamiast kopii; usuwa odczyt pliku przy przyjęciu i w `_episode_conflicts`; review v2 finding 9 | [DO-2026-10-02] |
| D-15 | `Ctrl+Z`: jedno trwałe miejsce `removed_subscription` (ostatnio usunięta, z celami i zużytymi próbami). Kolejne usunięcie je nadpisuje. Przywrócenie odmawia, gdy istnieje już subskrypcja tego `anilist_id` | S-08 „ostatnio usuniętą”; prostsze niż kosz | [DO-2026-10-02] |
| D-16 | Rotacji `decisions.jsonl` w E3 nie ma. Raport H3 podaje rozmiar pliku. Próg zatrzymania i decyzji: 50 MB | `e1-przeplyw` §5.6 l. 356 „jeśli w ogóle”; szacunek ok. 300 linii na cel w 7 dni | [DO-2026-10-02] |
| D-17 | Każdy odczyt Torrentio i ani.zip w sprawdzeniu dopisuje `check` (§5.6 l. 354) z `aired_at`. Raport H3 liczy z nich opóźnienie indeksowania (ryzyko `masterplan.md:107`) | jedyne źródło dowodu opóźnienia | wg dokumentu |
| D-18 | **Przegląd migracji jest osobny od pauzy.** Migrowany rekord dostaje trwałe `migrated_at` (chwila migracji) i `review_pending=True`. Pauzę ustawia tylko zastany stan: stara wyłączona → `paused=True, pause_reason="user"`; `end_state` ∈ {MISSING, UNCERTAIN} → `migrated_missing` (M-03); inaczej rekord **nie jest wstrzymany** (M-01). `review_pending` blokuje tylko nowe próby. Odświeżenie listy (odczyt bez prób) owner planuje dla każdego rekordu z `review_pending`, także wstrzymanego: od razu po starcie, potem z odstępem `policy.retry_delays_s` po błędzie albo po niepełnym odczycie. **Udane** jest tylko odświeżenie z kompletnymi danymi: mapowanie odczytane na żywo z Kitsu ID (nie pusta odpowiedź 404, nie zapis) i lista bez `schedule_warning` (`acquisition.py:764-783`). Odczyt z `schedule_warning` przegląd odkłada do `schedule_retry_at` albo do następnego odstępu `retry_delays_s`. Udane odświeżenie wylicza cele i zdejmuje `review_pending` w tym samym zapisie. Gdy jest cel z `due_at < migrated_at`, niepokryty starym zleceniem (`legacy_ordered`), rekord dostaje `paused=True, pause_reason="migrated_due"` (W-f, U-20). Inaczej zostaje bez zmian. Cele z `due_at >= migrated_at` są zwykłymi celami. Restart przed końcem przeglądu: `review_pending` jest trwałe, odświeżenie rusza znowu, a `migrated_at` się nie zmienia | M-01 („stan zostaje bez zmian bez zaległych celów”) i `e1-przeplyw` §3.2 l. 68-70 wymagają porównania z chwilą migracji. Odświeżenie nie tworzy prób | [DO-2026-10-02] |
| D-19 | Oczekujące receipt starych rodzajów (`receipt.pending` z `subscription_*`) w chwili migracji: `subscription_remove` → stara subskrypcja nie jest przenoszona; `subscription_enable/disable` → stosowane do flagi wstrzymania; `subscription_add/range/repeat` → odrzucone. `pending` czyszczone, liczba w logu | okno trwa sekundy; bez starego serwisu nie da się ich dokończyć | [DO-2026-10-02] |
| D-20 | **B1:** projekcja stanu odcinka zostaje w ownerze (`_episode_status`, `automation.py:4040`). Nowy czysty moduł konsumuje gotowe `EpisodeStatus` jako jawne wejście i nie liczy statusu transferu sam. Wydzielenia z F-11 nie robimy | `e2-refaktoryzacja.md:300-309` „jeśli E3 tego nie potrzebuje, projekcja zostaje” | decyzja planu |
| D-21 | **C1:** usuwane jest tylko to, co po migracji stałoby się drugim źródłem prawdy albo martwym wywołaniem starego pliku (lista §6.3). Reszta F-08 zostaje do E5 | `e2-refaktoryzacja.md:311-313` | decyzja planu |
| D-22 | Limit 100 subskrypcji (odmowa `subscription_limit`). **Żadna odpowiedź IPC subskrypcji nie zawiera listy celów.** `subscriptions_list` zwraca zwarte wiersze. `subscription_get` zwraca nagłówek, liczniki celów według `TargetState`, najwyżej jeden cel z problemem, `last_check` i dodatki. Stan każdego odcinka w U08 przychodzi z istniejącej projekcji `episode_states` (ograniczonej i testowanej w E2), rozszerzonej o stan celu (§5.13). Liczba celów nie ma limitu w modelu i nie wpływa na rozmiar ramek | Q-08 bez sztucznego limitu celów i bez utraty celów; ok. 250 B na wiersz → < 30 KiB | [DO-2026-10-02] |
| D-23 | **Decyzja D:** autozamknięcie (U-11) wymaga rzeczywistego spełnienia **każdego** trwałego celu rekordu. Cel jest `satisfied` dopiero po potwierdzonym pobraniu: przypisanie tego `EpisodeKey` (próba subskrypcji albo zlecenie ręczne) ma `handed_off`, albo dla celu `legacy_ordered` pokrywający `LegacyOrder` ma `complete` lub jego `operation_id` wskazuje potwierdzenie w stanie `COMPLETE`. Samo zlecenie (`manual`, `legacy_ordered` z samym `taken`/`ORDERED`) nie spełnia. `exhausted` blokuje zamknięcie. **Korekta liczby odcinków nie wyłącza celów:** cel z `number > episode_count` zostaje zwykłym celem, jest dalej szukany według swojego terminu i blokuje zamknięcie. U07 i U08 pokazują wtedy wyliczony (nie zapisany) konflikt „AniList podaje {n} odcinków, a subskrypcja czeka na E{m} · pobierz ręcznie albo usuń”. Rozliczenie należy do użytkownika: D/P w U08 albo usunięcie subskrypcji | `spec.md` U-11, I-02 (`spec.md:101`, `224`); `e1-przeplyw` §3.6 w. 18 („pobranie potwierdzone”); review v2 finding 3 | `spec.md` U-11, I-02 (`spec.md:101`, `224`); `e1-przeplyw` §3.6 w. 18 („pobranie potwierdzone”) | decyzja orkiestratora D |
| D-24 | Usunięcie subskrypcji z aktywną próbą: próba kończy się normalnie, a przyjęta trafia do Auto. Po odrzuceniu nie ma następnej próby (`e1-przeplyw` §3.6 w. 22) | wg dokumentu | wg dokumentu |
| D-25 | Autor wszystkich faz `opus55`, recenzent `astra`, commit po PASS każdej fazy, potem test na żywo orkiestratora | `petla-wykonania.md:43` | decyzja właściciela (O-1) |
| D-26 | **Kilka starych subskrypcji tego samego `anilist_id`** (różne grupy, `subscriptions.py:381-402`) scala się w migracji w jeden rekord. Wybór: `subscription_id` i `subscribed_at` z najstarszego `added_at` (remis: mniejsze ID). `merged_from` = ID wszystkich scalonych w kolejności. `paused`: rekord jest wstrzymany przez użytkownika tylko wtedy, gdy każdy scalony był wyłączony. `migrated_missing` tylko wtedy, gdy każdy scalony niekompletny miał MISSING/UNCERTAIN. Zakończone kompletne (M-04) pomija się przed scaleniem. Zlecenia i powiązania nie tracą się: `legacy_orders` liczy się ze **wszystkich** starych subskrypcji (z ich ID w referencjach konfliktu, D-14). Stare potwierdzenia zostają bez żadnej zmiany (decyzja I, D-14); ich zakres niesie `LegacyOrder` z `operation_id`. Punkt odcięcia: najstarsze `added_at`, więc cele obejmują wszystko, czego chciał którykolwiek wpis. Cele pokryte starym zleceniem dowolnej grupy są `manual`/`legacy_ordered`. Wpisy bez `anilist_id` (M-05) nie są scalane | inwariant „jeden rekord na `anilist_id`” (§5.2); żadnego zlecenia ani transferu nie ubywa | [DO-2026-10-02] |
| D-27 | **U-22 (decyzje C i H).** Rekord trzyma `mapping`, czyli **pełne** ostatnie `AniZipMapping` przyjęte z odczytu na żywo. Wszystkie pola są zachowane bez wybierania, w tym cały `raw_episodes`, kolejność i tytuły odcinków oraz dodatki, więc `identity_target`, lista odcinków i H2 dostają z zapisu to samo wejście co na żywo. Kodek w `watch_state.py` serializuje `AniZipMapping` 1:1 (`max_age_s` jako `None`). **Jeden wynik operacji:** nowa metoda `AcquisitionService.read_listing(anilist_id, *, saved: AniZipMapping \| None = None) -> ListingRead(listing, mapping, live: bool)`. `episodes()` staje się `read_listing(id).listing` (jedna ścieżka kodu). `prepare_episode(key, *, mapping: AniZipMapping \| None = None)` przy podanym `mapping` używa go zamiast odczytu ani.zip. Owner w jednym sprawdzeniu przekazuje do każdego `prepare_episode` dokładnie mapowanie z `ListingRead` tego sprawdzenia, więc lista celów i ocena kandydatów nie rozjeżdżają się. **Kiedy zapis zastępuje odczyt:** odczyt ani.zip rzuca (`AniShiftError`/`OSError`/`ValueError`, `acquisition.py:846-850`) albo zwraca mapowanie bez Kitsu ID (404 daje pusty `AniZipMapping`, `anizip.py:49-50`), a `saved` jest podane → `ListingRead(…, saved, live=False)`, a rejestr `check` dostaje `mapping_source="snapshot"`. Bez `saved` zachowanie zostaje jak dziś (wyjątek albo pusty wynik). **Zapis do rekordu** tylko z `live=True`, bez konfliktu K-06 (zgodne Kitsu ID), na wątku ownera. Odczyt `live=False` nie aktualizuje mapowania ani `refreshed_at`, nie zdejmuje `catalog_conflict` i nie kończy przeglądu migracji. Graf AniList i Torrentio bez zmian (ich awaria to błąd źródła, §3.6 w. 8). H1 bez zmian | `spec.md:112`, `masterplan.md:142`; reuse istniejącego typu i buildera; pamięć usługi nie przeżywa restartu (§2.1), więc sama pamięć podręczna nie spełnia U-22; review v2 findings 4–5 | decyzja orkiestratora C |
| D-28 | **Nieznany punkt odcięcia przy dodaniu:** `cut_point(listing, now) -> int \| None`. `NOT_YET_RELEASED` → 0. `RELEASING`/`HIATUS` → liczba odcinków z datą **AniList** `airs_at <= now`, gdy lista ma choć jedną datę AniList. Inaczej (brak harmonogramu, awaria harmonogramu `schedule_warning`, same daty ani.zip) → `None`. `subscription_add` przy `None` odmawia `subscription_cut_unknown`, bez zapisu. U06 pokazuje „Nie wiadomo, które odcinki już wyszły — spróbuj ponownie później” i nie ma przycisku Dodaj. `listing.aired` (`_aired`) nie jest używane jako punkt odcięcia | 0 przy `None` objęłoby wcześniejsze odcinki (W-b, U-09); D-06 zakazuje dat ani.zip | [DO-2026-10-02] |
| D-29 | **H2 na stagingu (decyzja G):** gdy wszystkie pliki przypisania próby są kompletne (`complete_files`), a przed `_reserve_publication`, owner kontroluje plik wideo przypisania w `staging_path(root, operation_id) / <ścieżka torrenta>`. Plik ma tam oryginalną nazwę z rozszerzeniem, więc wystarcza istniejący `MediaProbe.identify` (dispatch po rozszerzeniu, `probe.py:43-56`). Owner dostaje `media_probe: MediaProbe` w konstruktorze, a rezydent przekazuje `DefaultMediaProbe()` w `cli/watch.py` (miejsce budowy ownera, §2.1). Bez zmian w `services/media`. **Wiązanie z bajtami (v4):** owner bierze `file_stamp` pliku wideo przed kontrolą i po niej. Różne → kontrola się nie liczy i powtarza w następnej rundzie. Wynik przyjęty (`verification` inne niż `reject:*`) zapisuje się **w tym samym zapisie co rezerwacja publikacji** (`_reserve_publication`), razem z `verified_stamp`. Kopia wideo (`copy_staged`) dostaje `expected=verified_stamp` i odmawia (`_CHANGED_WHILE_COPIED`), gdy `file_stamp` źródła przed kopiowaniem jest inny. Nie ma trwałego wyniku H2 bez rezerwacji, więc nie ma wyniku, który pozwala pominąć kontrolę przed kopią. Restart przed zapisem rezerwacji: kontrola biegnie od nowa. Restart po zapisie rezerwacji, a przed kopią: kopia sprawdza zapisany `verified_stamp`. Plik zmieniony po kontroli daje istniejący problem publikacji E2 (lokalny błąd, D-11: bez zużycia próby, widoczny w U07, droga ręczna P) | `automation.py:5320-5371`; `acquisition_staging.py:93-125`; odrzucona próba nie ma publikacji (D-12); review v3 finding 4 | [DO-2026-10-02] |
| D-30 | **Zegary w pauzie globalnej (decyzja A w brzmieniu v4).** Jedna reguła: w pauzie owner nie obserwuje ani nie rozlicza transferów automatu (E2, §2.1), więc **żaden zegar próby nie nalicza czasu pauzy**, a czas naliczony przed nią zostaje. Zostaje sposób, w jaki E2 przerwę już wyklucza: wznowienie woła `reset_clock()` (`automation.py:2551`). Zmienia się jedna rzecz w `TransferInspector`: `inspect(..., held: frozenset[str] = frozenset())`, a `_record_progress` zachowuje pomiar hasha z `held`, którego nie ma w bieżącej obserwacji, jako `replace(previous, downloading=False)`, zamiast go usuwać. Owner w `_poll_transfers` podaje `held` = hashe potwierdzeń `_polled`, pominiętych tylko dlatego, że `_working` jest fałszywe. Ręczny transfer odpytywany w pauzie nie kasuje więc pomiaru transferu automatu (9 min + pauza + 1 min = 10 min). Hash spoza `held` traci pomiar jak dziś, więc nowa operacja tego samego hasha (po `COMPLETE`/`FAILED`) nie dziedziczy starego `idle_s`. **Metadane:** transfer w fazie metadanych (`applied_revision == 0`) nie jest zatrzymywany. E2 tego zabrania (`TRANSFER_METADATA_PENDING`, `_METADATA_STOPPED`, §2.1), a zatrzymanie oznaczałoby martwą próbę albo ponowne add. Klient w pauzie może dokończyć metadane i sam zatrzymuje transfer (`MetadataReceived`); selekcję owner robi po wznowieniu. Jego timeout liczy tylko czas obserwacji poza pauzą. **Odrzucony model** „pauza zatrzymuje także metadane, a po wznowieniu nowy termin”: wymaga wznawiania transferu zatrzymanego przed listą plików, czego E2 celowo nie robi. Restart procesu zaczyna pomiar od nowa jak w E2 (pomiar jest w pamięci). Ponowienie H2 (`T_kontroli`, w. 14) to termin w pamięci ownera. W pauzie H2 nie rusza (`_may_settle`), a po wznowieniu albo restarcie kontrola biegnie od początku. Zegary celu (U-14, S-14) liczą się bezwzględnie od `t_due` (K-07). W pauzie nie ma sprawdzeń, a po wznowieniu krok U-14 wynika z wieku celu | decyzja orkiestratora A; K-07; `transfers.py:127-130`, `139-144`, `232-261`; review v3 findings 2–3 | decyzja orkiestratora A (brzmienie v4 potwierdzone przez właściciela 2026-10-02) |

## 5. Target design

### 5.1 Odpowiedzialności

| Element | Odpowiada za | Owner stanu | Nie odpowiada za |
| --- | --- | --- | --- |
| `application/subscription_targets.py` (NEW, czysty) | typy trwałe subskrypcji i celu; punkt odcięcia; przynależność celu; `t_due`; terminy U-14; stan po zamknięciu próby; dopuszczalność kandydata; autozamknięcie; kolejność S-03 | — (funkcje bez stanu, jawne `now`) | I/O, statusu transferu (dostaje `EpisodeStatus`), H1 |
| `application/subscription_migration.py` (NEW, czysty) | `subscriptions.json` (zdekodowane `Subscription`) + stan schematu 3 → stan schematu 4 | — | odczytu plików i kopii (robi to `watch_state.py`) |
| `application/download_verification.py` (NEW, czysty) | reguły H2 przeniesione ze skryptu: `ExpectedEpisode`, `expected_episode`, `MediaProbe` (wynik pomiaru skryptu; w kodzie nazwa `MeasuredMedia`, bo `MediaProbe` to już protokół w `services/media`), `Verification`, `verify` | — | uruchamiania narzędzia (owner woła wstrzyknięty `MediaProbe.identify`, D-29) |
| `AutomationOwner` (`automation.py`, MODIFY) | polecenia IPC subskrypcji, termin sprawdzenia, przebieg sprawdzenia na puli I/O, przyjęcie próby przez `_admit_episode`, zamykanie prób, H2 przed rezerwacją publikacji, niezmiennik własności pauzy w `_save`, powiadomienia, Historia, cień | jedyny autor `WatchState` | reguł przejść (woła `subscription_targets`) |
| `watch_state.py` (MODIFY) | schemat 4, odczyt 1–4, migracja do 4 z kopią `.e3-migration.bak` (także bez `state.json`), odczyt starego pliku bez zapisu przez `decode_subscriptions`, kodek pełnego `AniZipMapping` | plik stanu | decyzji produktowych |
| `subscriptions.py` (MODIFY) | nowa czysta `decode_subscriptions(text) -> tuple[Subscription, ...]` (wydzielona z `SubscriptionStore.load`, bez zapisu); `load()` jej używa, zachowanie bez zmian | — | migracji do schematu 4 |
| `acquisition.py` (MODIFY) | `read_listing` → `ListingRead`, `episodes()` przez nie, parametr `mapping` w `prepare_episode` (D-27) | pamięć usługi | trwałości mapowania (robi owner) |
| Panel (`cli/interactive/state.py`, `anime.py`, `anime_view.py`, `cli/resident.py`) | U06, U07, U08, klawisze, wiersz globalny, odliczanie z lokalnego zegara | brak stanu trwałego | sieci w renderze (Q-01) |

### 5.2 Model danych (schemat 4)

```text
SubscriptionRecord (frozen, w WatchState.subscriptions)
  subscription_id: str            # nowe: token_hex; migrowane: stare ID (zachowuje korelację logów)
  anilist_id: int | None          # None tylko dla M-05
  kitsu_id: int | None            # U-22; None tylko dla M-05 i migrowanych przed pierwszym odświeżeniem
  mapping: AniZipMapping | None   # D-27; pełne ostatnie mapowanie z odczytu na żywo; None jak kitsu_id
  title: str                      # etykieta wpisu z katalogu (sanityzowana przy wyświetlaniu)
  subscribed_at: str              # t_sub, ISO UTC
  cut: int | None                 # n_cut z D-28 dla nowych; None tylko dla migrowanych (reguła §5.14 pkt 4)
  paused: bool
  pause_reason: str | None        # None | "user" | "migrated_due" | "migrated_missing"
  migrated_at: str | None         # D-18; chwila migracji, trwała
  review_pending: bool            # D-18; blokuje próby do pierwszego udanego odświeżenia
  merged_from: tuple[str, ...]    # D-26; stare ID scalone w ten rekord (pusta dla nowych)
  problem: str | None             # kod problemu subskrypcji: "season_unrecognized" (M-05) | "catalog_conflict" (K-06) | None
  catalog_status: str | None      # ostatni TitleStatus AniList
  episode_count: int | None
  refreshed_at: str | None        # ostatnie udane odświeżenie listy
  checked_at: str | None          # ostatnie sprawdzenie źródła
  last_check: SubscriptionCheck | None  # wynik do S-06/U08: numer, liczby wg werdyktu H1, decyzja
  targets: tuple[SubscriptionTarget, ...]
  migrated_from: str | None       # "subscriptions.json" dla przeniesionych

SubscriptionTarget
  number: int                     # lokalny numer zwykłego odcinka (EpisodeKey(anilist_id, number))
  due_at: str | None              # t_due; None = oczekuje emisji bez znanej daty
  state: TargetState
  attempts: int                   # 0..3, trwały
  tried: tuple[str, ...]          # wykluczone pary "hash:index" (casefold)
  admission_id: str | None        # aktywna albo ostatnia próba
  reason: str | None              # powód I-08 (EpisodeReason / kod subskrypcji)
  notified_late: bool             # S-14 wysłane
  check_skipped: bool             # H2 „niewykonana” (oznaczenie „Kontrola niewykonana”)

TargetState (StrEnum): awaiting_airing | due | attempting | satisfied | exhausted | manual
  (polskie nazwy z planu przepływu: oczekuje_emisji, należny, w_próbie, spełniony, wyczerpany, zlecony_ręcznie)

EpisodeAssignment (MODIFY, pola opcjonalne):
  subscription_id: str | None = None
  attempt: int | None = None          # 1..3 dla AdmissionSource.SUBSCRIPTION
  verification: str | None = None     # wynik H2: "no_contradiction" | "inconclusive:<reason>" | "skipped" | "reject:<reason>"
  verified_stamp: FileStamp | None = None  # D-29; file_stamp wideo w stagingu z chwili kontroli; istniejący typ i kodek jak PublishedFile.stamp
AdmissionSource: + SUBSCRIPTION = "subscription"

AniZipMapping (D-27): istniejący typ (`episode_selection.py:221-231`) zapisany 1:1, z całym
  raw_episodes; max_age_s zapisywane jako None

ListingRead (D-27, wynik operacji, nietrwały): listing: EpisodeListing, mapping: AniZipMapping, live: bool

LegacyOrder (D-14): anilist_id: int, number: int | None, reference: str,
  operation_id: str | None, complete: bool
  -> .scope = LegacyScope(anilist_id, number)

WatchState (MODIFY): + subscriptions: tuple[SubscriptionRecord, ...] = ()
                    + removed_subscription: SubscriptionRecord | None = None
                    + legacy_orders: tuple[LegacyOrder, ...] = ()
WATCH_STATE_SCHEMA_VERSION = 4
```

Inwarianty (walidowane w `__post_init__` jak w istniejących typach `control.py`):
`0 <= attempts <= 3`; `state == attempting` ⇒ `admission_id` ustawione; `exhausted` ⇒
`attempts == 3` albo powód „sprzeczna długość” (D-08, nieużywane w E3); numery celów
unikalne i dodatnie; `anilist_id is None` ⇒ `problem == "season_unrecognized"` i brak celów;
co najwyżej jedna subskrypcja na `anilist_id` (migracja zapewnia to scaleniem, D-26);
`review_pending` ⇒ `migrated_at` ustawione; `cut is None` ⇒ `migrated_at` ustawione;
`mapping is None` ⇔ `kitsu_id is None`; przypisanie `SUBSCRIPTION` z `publication` ⇒
`verification` ustawione i różne od `reject:*`; `verified_stamp` ⇒ `verification` przyjęte
(nie `skipped`, nie `reject:*`); przypisanie `SUBSCRIPTION` z `publication` i `verification`
innym niż `skipped` ⇒ `verified_stamp` ustawione. Dekoder `watch_state.py` odrzuca rekord bez
niego (`ConfigError`); test dekodera: brak `verified_stamp` przy publikacji i przyjętym wyniku →
odmowa, przy `skipped` → poprawny odczyt. Walidacja wersjonowana jak w
`watch_state.py`: dokument 4 musi mieć trzy nowe sekcje, dokument 3 nie może ich mieć.

Koszt stanu: pełne mapowanie ani.zip to szacunkowo 1–2 KiB na odcinek (surowe pola odcinka,
w tym opisy). Dla 100 subskrypcji po ok. 25 odcinków daje to kilka MiB. Budżet E2 (`state.json`
≤ 64 MiB, P95 `save()` ≤ 1 s, `e2-pobieranie.md:392`) mierzy się ponownie z subskrypcjami
(§8, F3).

### 5.3 Przepływ sterowania

```text
dodanie: U06 Enter -> IPC subscription_add{command_id, anilist_id}
  -> owner: pula I/O: acquisition.read_listing(anilist_id)  (ani.zip + harmonogram, cache Q-03)
  -> owner wątek: wymaga live=True z Kitsu ID (inaczej source_failed);
     cut_point(listing, now); None -> odmowa subscription_cut_unknown (D-28)
     inaczej targets(listing, t_sub, n_cut) + mapping z ListingRead (D-27)
  -> jeden _save(state + receipt) -> odpowiedź {subscription_id, from_number}
termin: _schedule_subscriptions() = min(next_check_at(sub, now)) po rekordach z terminem -> _subscriptions_at (monotonic)
sprawdzenie (pula I/O, osobno każda subskrypcja, wyjątek jednej nie przerywa reszty — S-12):
  read = acquisition.read_listing(id, saved=record.mapping)          (jeden wynik, D-27)
  -> owner wątek: merge_listing(record, read, now) (nowe cele, t_due, K-06, przegląd D-18;
     zapis mapowania tylko z read.live)
  dla każdego celu due bez aktywnej próby, gdy próby dozwolone (§5.5):
     acquisition.prepare_episode(key, mapping=read.mapping)   (Torrentio + H1 rank; check do rejestru)
     -> owner wątek: ponowny odczyt rekordu i celu; choose_candidate(offer, target, now)
        -> cień? proposal : _admit_episode(... SUBSCRIPTION, attempt+1, previous wg D-12)
cykl transferów E2 (bez zmian) -> pliki przypisania kompletne
  -> [assignment.source == SUBSCRIPTION, bez publication] stamp; H2 na pliku w stagingu; stamp (D-29, pula I/O)
       stamp przed != po -> bez wyniku, powtórka w następnej rundzie
       reject -> owner wątek: zamknij próbę z verification (D-12), cel wg reguły stanu po zamknięciu
       inaczej -> owner wątek: _reserve_publication + verification + verified_stamp (jeden zapis)
               -> kopia (copy_staged, expected=verified_stamp dla wideo) -> publish_set -> handed_off -> Auto   (U-19)
pauza (owner, każdy _save przy auto_enabled == False): niezmiennik własności pauzy (§5.6)
settle (owner, po każdym przejściu przypisania): settle_target(target, EpisodeStatus, now)
```

### 5.4 Maszyna stanów celu (implementacja reguł `e1-przeplyw` §3.3–§3.6)

Czyste funkcje w `subscription_targets.py`; owner tylko je stosuje i zapisuje:

- `cut_point(listing, now) -> int | None`: reguła D-28 (z dat AniList `airs_at`, nigdy z
  `listing.aired` ani `airs_at_fallback`). `None` = dodanie niemożliwe.
- `is_target(episode, t_sub, n_cut)`: `airs_at` z AniList (nie `airs_at_fallback`) > `t_sub`;
  bez daty: `number > n_cut`. Przynależność nie zmienia się po zmianie daty (§3.1 l. 58):
  numer raz dodany do `targets` zostaje.
- `merge_listing(record, read: ListingRead, now)`: dopisuje nowe cele (nowe numery w AniList
  lub ani.zip spełniające `is_target`) i przelicza `due_at`. Data → `airs_at`. Bez daty →
  pierwsza obserwacja U-15 (`status` ∈ {RELEASING, FINISHED} i `number <= aired`); raz
  ustawione `due_at` dla celu bez daty nie cofa się. Przejścia 1–3 z §3.6 (w. 2–3):
  `awaiting_airing ↔ due` tylko bez aktywnej próby. Rozjazd Kitsu ID odczytu na żywo z
  `record.kitsu_id` → `problem = "catalog_conflict"`, bez nowych prób i bez zapisu mapowania
  (w. 23). Zdjęcie tylko po zgodnym odczycie na żywo (w. 24). `read.live == False` nie zmienia
  `problem`, `mapping`, `refreshed_at` ani `review_pending`, ale cele i `due_at` z harmonogramu
  AniList liczy normalnie.
- `after_close(target, now, n_max=3)`: `attempts >= 3` → `exhausted`; `now < due_at` →
  `awaiting_airing`; inaczej `due`.
- `settle_target(target, status: EpisodeStatus | None, h2: str | None, legacy_complete: bool, now)`:
  przypisanie próby `handed_off` → `satisfied`. Zamknięcie z D-11 → `after_close`. Ręczne
  przypisanie nowsze niż próba → `manual` (D-13). `manual` + przypisanie tego klucza
  `handed_off` → `satisfied`. `manual` z `legacy_ordered` + `legacy_complete` → `satisfied`
  (D-23). `manual` + problem → `after_close`. Samo przyjęcie, `PENDING_SEND`, transfer albo
  stare `taken`/`ORDERED` nie dają `satisfied` (I-02).
- `eligible(candidate, target, now)`: werdykt `MATCH` (D-10); `facts.supported is not False`
  (U-06); para nie w `tried`; para nie jest plikiem przyjętym dla innego celu subskrypcji;
  rozdzielczość < 1080p tylko po `T_rozdzielczość` (= 0). Wybór: pierwszy dopuszczalny w
  kolejności `offer.candidates` (już posortowanej przez `rank_candidates`,
  U-04/U-05/U-23).
- `completed(record) -> bool` (U-11, decyzja D): `catalog_status == FINISHED`, `episode_count`
  znane, **każdy** cel rekordu `satisfied` (żaden `exhausted`, `attempting`, `due`,
  `awaiting_airing` ani `manual` bez spełnienia), a dla rekordu ze znanym `cut` istnieje cel
  dla każdego numeru `cut+1..episode_count` (brakujący numer → nie zamyka). Celu nic nie
  wyłącza. Cel z `number > episode_count` blokuje zamknięcie, a projekcja wiersza U07/U08
  wylicza z niego konflikt „AniList podaje {n} odcinków, a subskrypcja czeka na E{m}”
  (D-23). Licznik „pobrano y/y” w S-09 = spełnione / wszystkie cele.
- `display_order(records, now)` (S-03): problem → najbliższe `due_at`/emisja → bez terminu →
  wstrzymane; remis po tytule (`casefold`).

### 5.5 Harmonogram i zegar

`next_search_at(target, last_checked, now)` liczony od `due_at` (bezwzględnie, restart nie
zeruje, K-07): krok 15 min dla `now - due_at < 24 h`, 1 h dla `< 72 h`, potem 24 h; pierwsze
sprawdzenie o `due_at + T_start` (0). `next_check_at(record, now)` = minimum z celów `due`
bez aktywnej próby oraz z terminu odświeżenia listy. Odświeżenie listy: o najbliższym
`airs_at` celu, inaczej co 24 h; dla `HIATUS` i dat dalszych niż doba 24 h. Blokada dostawcy
`RequestControl` (Q-04, P-10) przesuwa termin i nie zużywa próby (`automation.py:3806-3824`
`_restore_provider_locks`, `_save_provider_lock` zostają).

Owner przelicza `_subscriptions_at` przez istniejące `_schedule_subscriptions`/
`_poll_subscriptions` (`automation.py:3756-3800`); zmienia się tylko źródło terminu:
`subscription_targets.next_check_at` zamiast `service.next_check_at`. W testach zegar
`clock` (`automation.py:573`) jest atrapą, a termin monotoniczny wylicza się z różnicy
`deadline - clock()`. Testy wołają `_poll_subscriptions` z przesuniętą atrapą zegara i
monotonicznego czasu (patch `time.monotonic` w module, jak w istniejących testach ownera;
wykonawca sprawdza istniejący wzorzec w `tests/application/test_automation*.py`). Bez `sleep`.

**Próby dozwolone**, gdy wszystkie: `not record.paused`, `not record.review_pending`,
`record.problem is None`, `policy.auto_enabled`, usługa acquisition dostępna.
**Termin sprawdzenia** (każdy wymaga `policy.auto_enabled` i usługi acquisition):

| Rekord | Termin |
| --- | --- |
| z dozwolonymi próbami | cele (U-14) i odświeżenie listy |
| `review_pending` (także wstrzymany) | tylko odświeżenie: od razu, potem `schedule_retry_at` albo `retry_delays_s` (D-18) |
| `problem == "catalog_conflict"`, niewstrzymany | tylko odświeżenie naprawcze co `retry_delays_s` (ostatni krok powtarzany), niezależnie od prób; zgodny odczyt na żywo zdejmuje problem (w. 24) |
| `season_unrecognized` albo wstrzymany bez `review_pending` | brak terminu |

Pauza globalna zatrzymuje wszystkie terminy. Przegląd i odświeżenie naprawcze ruszają po
wznowieniu, bo `review_pending` i `problem` są trwałe. `_subscriptions_problem` (błąd zapisu
stanu) → stały wiersz U07 i ponowienie po `policy.retry_delays_s` (istniejące pole, S-12).

**Pauza globalna (decyzja A, D-30):** bez nowych prób i sprawdzeń. Transfery prób subskrypcji z
zastosowaną selekcją zatrzymuje pauza E2 (nie są `manual`, D-04), a wznowienie je
kontynuuje. Faza metadanych nie jest zatrzymywana. Owner nie obserwuje i nie rozlicza w pauzie
żadnego transferu automatu, więc żaden zegar próby (zastój, metadane) nie nalicza czasu pauzy.
Pomiary sprzed pauzy chroni `held` w `TransferInspector`, a przerwę wyklucza `reset_clock()`
przy wznowieniu. Zegary celu (U-14, S-14) liczą się bezwzględnie od `t_due`.

### 5.6 Integracja z bramką przyjęcia E2 i I-06

- Próba = `_admit_episode(command_id, choice, previous=..., conflict=())` z nowymi
  argumentami `source=AdmissionSource.SUBSCRIPTION`, `origin=RequestOrigin.BACKGROUND`,
  `subscription_id`, `attempt` (MODIFY sygnatury; ścieżka MANUAL bez zmian).
  `command_id = f"sub:{subscription_id}:{number}:{attempt}"`. Receipt czyni powtórzenie po
  restarcie idempotentnym (`automation.py:4579-4585`).
- `previous` wg D-12: z `_episode_assignments(key)` bieżącego stanu, ta sama lista i ten sam
  ostatni element, które sprawdza `_admission_refusal`. Liczone na wątku ownera tuż przed
  `_admit_episode`. Wykluczenie poprzedniego kandydata: filtr `tried` (pary są trwałe w celu,
  więc nie zależą od tego, czy poprzednie przypisanie jest jeszcze chronione).
  `_replace_episode_scope` dostaje strażnika: przypisanie już `replaced` zostaje bez zmian i bez
  podniesienia `selection_revision`.
- **Paczka mieszana (decyzja B):** `AcquisitionConfirmation.manual` wg D-04. **Własność pauzy
  jest niezmiennikiem stanu**, a nie zdarzeniem rundy. `_save(candidate)` przy
  `candidate.policy.auto_enabled == False` stosuje czystą `_pause_ownership(candidate)`,
  zanim zapisze stan. Działa więc przy każdej mutacji (przyjęcie, zastąpienie, anulowanie,
  polecenie `transfer`, wynik rundy), także gdy w pauzie nie biegnie żadna runda. Funkcja robi
  dwie rzeczy istniejącymi akcjami pauzy. (1) Transfer pracujący według `_working_transfers`
  (nieręczny, `applied_revision > 0`, bez stop/cancel), **którego hasha nie ma jeszcze w
  `pause_owned_transfers`**, dostaje stop pauzy i dołącza do zbioru. To `_stopped_transfers` z
  sumą zamiast nadpisania zbioru (§2.1). Hash już w zbiorze oznacza stop rozliczony w tym
  epizodzie pauzy. Dotyczy to także transferu, który qB pokazał zatrzymany przed wysłaniem
  stopu: `_settled_stop` zeruje wtedy `requested_action`, `action_pending` i `action_sent`
  (`automation.py:6114-6115`, `6172-6177`), a transfer wraca do `_working_transfers`
  (`2618-2628`). Taki transfer nie dostaje kolejnego stopu, a `action_sent` nie jest
  ustawiane na `True`. Zbiór opuszcza tylko przez resume w (2), jawne `stop`/`cancel`
  (`automation.py:6077-6081`) albo wznowienie `O`.
  (2) Transfer z `pause_owned_transfers`, który jest teraz ręczny i ma rozliczony stop pauzy
  (warunki `_resumable`), dostaje resume i tylko on opuszcza zbiór. Gdy funkcja dodała akcję,
  `_save` woła `_schedule_transfers()`. Oczekujące akcje owner wykonuje także w pauzie
  (`_transfer_action`, §2.1), więc runda powstaje bez pollingu w tle. Nierozliczony stop
  (spóźniony z workera) czeka na rozliczenie (`_settled_stop`). Zapis tego rozliczenia w
  `_record_transfers` też przechodzi przez `_save`, więc resume przychodzi w tym samym zapisie.
  Funkcja jest idempotentna: drugi `_save` na jej wyniku nie dodaje akcji ani rundy. Test w
  F3/E-13: qB pokazuje transfer już zatrzymany → stop pauzy rozliczony przez `_settled_stop` →
  kolejne zapisy w pauzie bez nowej akcji i bez rundy, także po restarcie ownera. Przy
  `set_auto(False)` daje ten sam wynik co dzisiejsze
  `_stopped_transfers`. W pauzie nie wznawia transferu nieręcznego (polecenie `resume` jest
  wtedy odrzucane, §2.1), więc kontraktu E2 nie zmienia. Ręczność jest liczona, nie zapisywana,
  a wejście jest trwałe, więc po restarcie wynik jest ten sam. `_finish_pause_restore` zostaje
  bez zmian dla wznowienia. `_resumable` filtruje stare subskrypcje przez ID niewstrzymanych
  rekordów i ich `merged_from` ze stanu zamiast `_enabled_subscriptions` (usuwane, §6.3). W
  pauzie nie powstają nowe próby (§5.5), więc mieszanie w pauzie zachodzi tylko przez ręczne D
  albo zniknięcie przypisania ręcznego.
- Konflikty: `_admission_refusal` (`automation.py:4586`) i `episode_conflict`
  (`control.py:951`) bez zmian. Odmowa `episode_admitted` (cel zlecony gdzie indziej) →
  `manual`; odmowa `episode_possibly_admitted` (`LegacyScope`) → `manual` z powodem
  `legacy_ordered`. Subskrypcja nigdy nie potwierdza konfliktu legacy sama.
- `_legacy_scopes()` (`automation.py:4702`) czyta odtąd `scope` z `self._state.legacy_orders`;
  nie czyta pliku i nie zwraca `None` (I-06, koniec `LEGACY_UNREADABLE` dla subskrypcji).
  Migracja nie zmienia starych potwierdzeń (D-14). Gałąź `subscription_id` w
  `_legacy_episode_records` (`automation.py:4186-4190`) jest usuwana (C1), bo jej zakres i
  referencję niesie odtąd `LegacyOrder` z `operation_id`.
- `_episode_conflicts(key)` (`automation.py:4202-4229`) bierze odtąd referencje
  `_episode_conflict_reference` z `_legacy_episode_records(key)` (potwierdzenia z własnym
  `legacy_scope`) oraz `reference` z `legacy_orders` pokrywających klucz (`scope.covers`). Nie
  czyta `service.subscriptions`. Zbiór referencji dla danego klucza jest identyczny przed
  migracją i po niej, bo żaden hash wejściowy się nie zmienia (D-14).
- Nowe przyjęcia subskrypcji są zawsze kluczowane (`EpisodeKey`). `legacy-unkeyed` zostaje
  wyłącznie dla starych zleceń i polecenia `download` (E5).

### 5.7 H2 w przepływie

- Moment: przypisanie `SUBSCRIPTION` bez `publication`, wszystkie jego pliki w
  `complete_files`, w `_publish_episode` tuż przed `_reserve_publication`
  (`automation.py:5320-5328`), przy tych samych warunkach co publikacja (`_may_settle`,
  `_working`). Kontrola na puli I/O: `stamp = file_stamp(wideo)`, potem
  `media_probe.identify(staging_path(root, operation_id) / <ścieżka wideo przypisania>, cancel,
  timeout_s=30)` (D-29), potem ponowny `file_stamp`. Różne stampy albo `None` → brak wyniku,
  powtórka w następnej rundzie. Wynik → wejście `verify` (`duration_seconds=duration_us/1e6`,
  liczby strumieni wideo i audio). `ExpectedEpisode` z `raw_episodes[str(number)]` mapowania
  rekordu (D-27; `length` → `runtime`; AniList `duration` nie jest pobierane, więc źródło
  `anilist.duration` nie występuje). `verify(mode="record_only")`.
- Timeout albo `MediaProbeError` z uszkodzonego JSON → jedno ponowienie po 30 s (w. 14). Drugi
  raz albo brak binarki (`require_binary`) → `verification="skipped"`, `check_skipped=True`,
  przyjęcie trwa (w. 15) i wpis `escalation` „kontrola niewykonana”. Kontener spoza
  {mkv, mp4} nie występuje (U-06). Gdyby wystąpił, `UnsupportedMediaError` daje `skipped` z
  powodem `unsupported_container` w rejestrze.
- `reject:no_video_stream` → próba odrzucona (D-11, D-12). Nie ma rezerwacji nazw ani kopii, a
  pliki w roocie nie powstają. Staging znika istniejącym cleanupem (`clean_staging`,
  `acquisition_staging.py:190`) po zwolnieniu transferu, jak dla każdego nieopublikowanego
  przypisania. Wykonawca dowodzi testem, że odrzucony plik nie pojawia się w roocie, a
  przypisanie po potwierdzonym anulowaniu nie jest chronione.
- Wynik trwały (D-29): odrzucenie zapisuje się razem z zamknięciem próby. Wynik przyjęty
  (także `skipped`) zapisuje się w tym samym zapisie co rezerwacja publikacji
  (`_reserve_publication` dostaje `verification` i `verified_stamp`; dla `skipped` stamp
  `None`). Nie ma więc stanu „przyjęte, bez rezerwacji”, który pozwoliłby pominąć kontrolę.
  Przypisanie `SUBSCRIPTION` bez `publication` zawsze przechodzi kontrolę od nowa, także po
  restarcie (bez skutków). Przypisanie z rezerwacją, ale bez kopii (restart w tym oknie),
  kopiuje wideo z `expected=verified_stamp`. `copy_staged(source, destination, size, *,
  expected: FileStamp | None = None)` przy podanym `expected` odrzuca źródło, którego
  `file_stamp` przed kopiowaniem jest inny (`_CHANGED_WHILE_COPIED`). Ścieżka E2 bez `expected`
  działa jak dziś. Odrzucenie daje istniejący problem publikacji (D-11, bez zużycia próby,
  bez publikacji do roota). To samo dotyczy każdej zmiany pliku po ostatnim odczycie stempla
  przy kontroli, także przed zapisem rezerwacji: rezerwacja zapisuje stempel z kontroli, więc
  zmianę wykrywa dopiero `copy_staged(expected=)`.
  Ponownego H2 po rezerwacji nie ma, bo odrzucenie przypisania z publikacją zostawiłoby
  chroniony klucz (D-12). Stan UI „Kontrola E6” (`spec.md:187`) to przypisanie z kompletem
  plików, bez `publication` i bez `handed_off`.
- Przypisania `MANUAL` H2 nie przechodzą (`e1-przeplyw` w. 18).

### 5.8 Rejestr decyzji

`append_decision` (`acquisition_decisions.py:189`) bez zmian mechaniki. `_FIELDS` rozszerzone
o: `path` (`manual`/`subscription`/`shadow`), `subscription_id`, `attempt`, `attempt_result`
(`accepted`/`dead`/`rejected`/`replaced`), `verification`, `measured_s`, `expected_s`,
`duration_source`, `due_at`, `aired_at`, `result` (zamknięta lista z `e1-przeplyw` §5.6 dla
`check`), `excluded` (liczba wykluczonych par), `mapping_source` (`live`/`snapshot`, D-27).
Test istniejącego odrzucania pól spoza `_FIELDS` obejmuje każdy nowy wpis. Rodzaje:

| `kind` | Kiedy |
| --- | --- |
| `check` | po każdym odczycie Torrentio/ani.zip w sprawdzeniu subskrypcji; bez nazw i hashy |
| `selection` | przy starcie próby (istniejące `admission_decision`, z `path=subscription`, `attempt`) |
| `proposal` | w trybie cienia zamiast `selection` (ta sama treść, bez przyjęcia) |
| `attempt` | przy zamknięciu próby: numer, wynik, wynik H2 i powód |
| `escalation` | 7 dni bez wydania, wyczerpanie, konflikt katalogu, kontrola niewykonana |
| `correction` | bez zmian (E2) |

Owner jest jedynym piszącym (istniejące wywołania z wątku ownera, `automation.py:4645`,
`4656-4660`). Rejestr nie służy do odtwarzania stanu.

### 5.9 Tryb cienia (S-15)

`Settings.subscription_shadow: bool = False` (pydantic-settings, env
`ANISHIFT_SUBSCRIPTION_SHADOW`), czytane przy budowie ownera rezydenta w `cli/watch.py`
(`watch.py:352-364`); wykonawca bierze `Settings` z istniejącego źródła usługi, bez drugiego
odczytu `.env`. Gdy włączone,
maszyna stanów działa tak samo aż do `choose_candidate`, a potem zapisuje `proposal` zamiast
przyjęcia. Cel zostaje `due`, licznik prób stoi, qB i pliki nie są dotykane. U07 pokazuje
stały wiersz „Tryb cienia — subskrypcje tylko zapisują propozycje”. Nie jest bramką wdrożenia;
H3 biegnie z cieniem wyłączonym.

### 5.10 Powiadomienia (Windows, zasobnik)

Reuse `_publish_notification(title, message, target=None)` (`automation.py:6917`) i zdarzenia
`notification` obsługiwanego przez rezydenta (`TrayIcon.notify`, `platform/tray.py:192`).
Jednokrotność: klucz w `WatchState.notified` (`NotificationKey`, `control.py:88`) postaci
`(f"subscription:{id}:{number}", kind, "")`, gdzie `kind` ∈ {`late`, `exhausted`}.
`notified_late` w celu zachowuje się przy `Ctrl+Z`. Teksty: tytuł „Subskrypcja”, treść
„Nie znaleziono {tytuł} E{n} od 7 dni” albo „{tytuł} E{n}: wyczerpano próby (3 z 3)”, po
`sanitize_event_message`. Kliknięcie: `target=None` → istniejące zachowanie (panel/Home).
Nowej funkcji zasobnika nie ma.

### 5.11 Historia (S-09)

`history.py`: nowy `HistoryKind.SUBSCRIPTION_FINISHED` dodany do domyślnego zestawu
terminalnego (`history.py:145-152`). Wpis „Subskrypcja zakończona: {tytuł}, pobrano y/y”
dopisuje owner przy autozamknięciu, w tym samym kroku co usunięcie rekordu ze stanu (stan
pierwszy; Historia jest nieautorytatywna).

### 5.12 IPC (Q-08)

| Polecenie | Wejście | Wyjście / skutek | Mutuje (receipt) |
| --- | --- | --- | --- |
| `subscriptions_list` | — | `{subscriptions: [SubscriptionRow], shadow: bool, problem: str \| None}`; wiersz: id, tytuł, `from_number`, `downloaded`, `targets_total \| None`, `ready`, stan wiersza S-03 (kod + liczby + `due_at`), `paused`, `pause_reason`, `problem` | nie |
| `subscription_get` | `subscription_id` | nagłówek rekordu, liczniki celów wg `TargetState`, `first_target`/`last_target` (zakres numerów celów), najwyżej jeden cel z problemem, wyliczony konflikt liczby odcinków (D-23), `last_check`, `review_pending`, dodatki (`ListedSpecial`) z mapowania rekordu (D-22). Bez listy celów | nie |
| `subscription_add` | `command_id`, `anilist_id` | `{subscription_id, from_number}` albo odmowa: `subscription_exists`, `subscription_not_airing` (U-10), `subscription_cut_unknown` (D-28), `subscription_limit`, `source_failed` | tak |
| `subscription_pause` / `subscription_resume` | `command_id`, `subscription_id` | idempotentne; `resume` zdejmuje każdy `pause_reason` | tak |
| `subscription_remove` | `command_id`, `subscription_id` | rekord → `removed_subscription`; aktywne próby trwają (D-24) | tak |
| `subscription_restore` | `command_id` | przywraca `removed_subscription`; odmowa `subscription_exists` / `nothing_to_restore` | tak |
| `subscription_check` | `command_id`, `subscription_id` | jedno sprawdzenie na puli I/O, potem zdarzenie `subscription_checked` z `last_check` (S-06). Działa także dla wstrzymanej subskrypcji jako odczyt bez prób | receipt partii jak `episode_download` |

Usuwane rodzaje (C1): `subscription_enable`, `subscription_disable`, `subscription_range`,
`subscription_repeat`, `subscriptions_check`, `subscription_retry_prepare` oraz stary kształt
`subscription_add`. `subscription_get` i `subscriptions_list` zmieniają kształt odpowiedzi.
Nieznany rodzaj ze starego panelu kończy się istniejącą odmową; panel pokazuje „Rezydent
nie wykonał polecenia…” (`ux.md:298`). Każda odpowiedź mieści się w `MAX_FRAME_BYTES` z
zapasem. Test buduje 100 subskrypcji o maksymalnej długości pól (tytuł Unicode, problem,
`last_check`) i jedną z 2000 celów i 300 dodatkami, po czym sprawdza rozmiar zakodowanych
ramek `subscriptions_list` i `subscription_get`. Dla celu 2000 odcinków (w tym przyszłych)
panel pyta `episode_states` w 20 partiach po ≤ 100 kluczy (limit `validate_episode_keys`);
test sprawdza rozmiar każdej ramki i komplet stanów celu.

### 5.13 Panel

- **`S` w Anime** (`anime.py`): działa w U03 (lista odcinków) oraz na wierszu wpisu w U02
  (tytuły) i na ekranie wpisów. **Zapowiedzi:** Enter na wierszu `NOT_YET_RELEASED` dalej nic
  nie otwiera (`anime.py:1063`, `1117`), ale `S` na takim wierszu wczytuje listę odcinków
  istniejącym workerem odczytu (`acquisition.episodes` przez ownera; pusta lista jest
  poprawna) i otwiera U06 bez U03. Dla wpisu spełniającego U-10 (`listing.status` ∈
  {RELEASING, NOT_YET_RELEASED, HIATUS}) otwiera U06; dla innego pokazuje notkę „Ten wpis nie
  ma przyszłych odcinków”. Wpis już subskrybowany → notka „Ten sezon jest już subskrybowany ·
  Enter pokaż” → U08 (`ux.md:234`). `S` wraca do stopki U02/U03 i wpisów. Esc z U06 wraca na
  ekran, z którego otwarto szkic.
- **U06**: szkic liczony lokalnie z wczytanego `EpisodeListing` (bez sieci). Używa tych samych
  funkcji `cut_point`/`is_target` z fasady `anishift.application` (jedno źródło reguły).
  Teksty wg `ux.md:207-234`; dla `cut_point is None` (D-28) tekst odmowy bez przycisku Dodaj.
  Enter na „Dodaj subskrypcję” → `subscription_add`; po sukcesie
  przejście do U07 z podświetlonym nowym wpisem (S-04). Odpowiedź ownera jest autorytatywna:
  wiersz pokazuje `from_number` z odpowiedzi.
- **U07** (zakładka Subskrypcje w `StateController`): pierwszy wiersz „D Dodaj subskrypcję”
  (pusta lista: „Brak subskrypcji”), stały wiersz globalny (pauza / błąd monitoringu / cień),
  dwa wiersze na subskrypcję wg `ux.md:238-260`. Odliczanie z zegara renderera co sekundę,
  bez IPC; kolejność z `display_order` liczonego przy odebraniu snapshotu, nie co klatkę
  (S-03). Klawisze: Enter → U08; `D` → zakładka Anime U01 z trybem „dodaj subskrypcję” (Esc
  wraca do U07); `W`/Space → pause/resume; `F` → `subscription_check` i wynik w drugim
  wierszu na 10 s; `Delete`/`X` → remove, notka „Usunięto {tytuł} · Ctrl+Z cofnij”;
  `Ctrl+Z` → restore. Nowy klawisz `Delete` dostaje własny binding w `_NORMALISED_KEYS`
  (`prompts.py`), jeśli go tam nie ma (pułapka `cli/AGENTS.md`).
- **U08**: istniejący ekran odcinków Anime dla `anilist_id` subskrypcji z nagłówkiem
  subskrypcji (`ux.md:262-284`), kolumną Stan z jednego modelu stanów (D7 z E2 + stany
  subskrypcji §5.5 spec: „Czeka na emisję”, „Czeka na wydanie”, „Kontrola”, problem) i
  sekcją „Dodatki tego sezonu” (`ListedSpecial`, tylko informacja). Dodatkowe klawisze
  `W`/`F`/`X`; D/I/P/Space/A/Z bez zmian. Projekcja stanu odcinka: owner rozszerza
  `episode_states` o stan celu, gdy odcinek jest celem aktywnej subskrypcji i nie ma
  silniejszego stanu E2 (zlecenie/transfer/przetwarzanie/gotowe wygrywa). Jedna projekcja
  w ownerze (D-20). W trybie U08 `_read_episode_states` (`anime.py:1130-1143`) pyta o
  wyemitowane odcinki **i** każdy numer z zakresu celów `first_target..last_target` z
  `subscription_get` (także przyszłe i poza listą katalogu), w istniejących partiach
  `_MAX_BATCH`. Poza U08 zachowanie zostaje bez zmian. Konflikt
  liczby odcinków (D-23) widać w nagłówku U08 i w drugim wierszu U07.
- Usuwane: `cli/interactive/subscriptions.py` (`SubscriptionDraft`), gałęzie starego szkicu i
  zakresu w `state.py`, metody `ResidentSession.set_range/repeat/_subscription/follow/
  subscription_retry_proposal` (`resident.py:127-374`). Ścieżka P z Historii dla starych
  pobrań subskrypcji (`proposal.action == "subscription"`, `state.py:768-794`) zostaje
  zastąpiona odmową ownera `legacy_subscription_retry` z tekstem „Pobierz ten odcinek
  ponownie z Anime (P)”.

### 5.14 Migracja M-01–M-07

Migracja biegnie w `WatchStateStore.load()` w dwóch przypadkach: (a) `state.json` w wersji
1–3 (1–2 po istniejącym łańcuchu); (b) **brak `state.json` przy istniejącym
`subscriptions.json`**. W przypadku (b) bazą jest `_fresh_state()` (`watch_state.py:303-305`),
a migracja zapisuje wynik od razu. `state.json` w wersji 4 nigdy nie uruchamia migracji, więc
`subscriptions.json` po niej nie jest już czytany. Owner woła `load()` przy starcie, zanim
przyjmie pierwsze polecenie, więc oba wejścia są zabezpieczone przed pierwszą mutacją.

1. **Odczyt bez skutków:** bajty `subscriptions.json` czytane raz i dekodowane nową czystą
   `decode_subscriptions(text)` (wydzieloną z `SubscriptionStore.load`, wersje 1–4,
   `subscriptions.py:425-437`). **`SubscriptionStore.load()` i jego `_upgrade`/`save` nie są
   wołane w migracji**, więc stary plik nie jest zapisywany ani nie powstaje nowa kopia
   `.v<n>.bak`. Uszkodzony albo nieczytelny → `ConfigError` (D-03) bez zapisu czegokolwiek.
2. **M-07:** przed zapisem schematu 4 kopia bajt w bajt `state.json` (jeśli istnieje) i
   **tych samych przeczytanych bajtów** `subscriptions.json` do `*.e3-migration.bak`.
   Istniejącej kopii nie nadpisuje. Brak `subscriptions.json` tylko loguje, brak `state.json`
   tylko loguje. Błąd kopii → `ConfigError` `IO_ERROR` bez zapisu nowego formatu. Reuse
   mechanizmu `.e2-migration.bak` (`watch_state.py:94`, `378`) przez sparametryzowanie sufiksu
   wersją docelową, bez drugiej kopii kodu.
3. `subscription_migration.migrate(state, legacy, now) -> WatchState` (czysta):
   - `legacy_orders` = `LegacyOrder` ze **wszystkich** starych subskrypcji i ze starych
     potwierdzeń powiązanych subskrypcji bez `legacy_scope` (D-14, D-26);
   - `acquisitions` bez żadnej zmiany (D-14: stabilne referencje konfliktu);
   - pending receipt wg D-19;
   - stare subskrypcje: `end_state == COMPLETE` → pomijane (M-04); `anilist_id is None` →
     osobny rekord z `problem="season_unrecognized"`, bez celów (M-05); pozostałe grupowane po
     `anilist_id` i scalane wg D-26 w rekord z `subscribed_at` = najstarsze `added_at`,
     `cut=None`, `targets=()`, `migrated_at=now`, `review_pending=True`, `merged_from`.
     `paused`/`pause_reason` wg D-18/D-26 (`user`, `migrated_missing` albo brak pauzy).
     `kitsu_id=None` i `mapping=None` do pierwszego odświeżenia.
4. **Przegląd (D-18):** pierwsze udane odświeżenie (kompletne dane na żywo, D-18): `merge_listing` z `cut=None`. Celem jest
   odcinek z datą AniList > `subscribed_at`. Cel pokryty `legacy_orders` jest od razu
   `manual`/`legacy_ordered`. Odcinek bez daty nie jest celem, dopóki AniList nie poda daty
   (nierozstrzygalne, `e1-przeplyw` §3.2 l. 71-72); notka w U08: „Odcinki bez daty z czasu
   starej wersji — pobierz ręcznie”. W tym samym zapisie: `review_pending=False`, mapowanie i
   `kitsu_id`. Gdy jest cel `due`/`awaiting_airing` z `due_at < migrated_at` niepokryty starym
   zleceniem: `paused=True, pause_reason="migrated_due"` z opisem „Wstrzymana — przeniesiona;
   zaległe E…–E… · W wznów” (M-01). `migrated_missing` zostaje z opisem „Zakończona przez
   starą wersję; brakuje E…–E… · W wznów” (M-03). Zamknięcie migrowanego rekordu (U-11)
   wymaga spełnienia wszystkich celów; warunku zakresu `cut+1..episode_count` nie ma, bo brak
   `cut` (§5.4).
5. M-06: stare transfery (`AcquisitionConfirmation` bez `assignments`) idą dalej istniejącą
   ścieżką legacy. Migracja nie zmienia ich stanu ani ustawień przetwarzania.
6. Drugi `load()` nie zmienia bajtów (idempotencja). Nieznana wersja → `ConfigError`.
7. **Awaria zapisu:** wyjątek `save()` w migracji → `ConfigError`. Zostają bajty obu wejść i
   ewentualnie kopie `.e3-migration.bak`. Następny `load()` powtarza migrację od tych samych
   bajtów z tym samym wynikiem, z nowym `migrated_at`, bo poprzedni zapis nie powstał.

### 5.15 Edge cases

| Przypadek | Zachowanie | Dowód |
| --- | --- | --- |
| Restart w trakcie próby (metadane, pobieranie, kontrola) | uzgodnienie E2; brak ponownego przyjęcia (receipt `sub:…:attempt`); kontrola H2 powtórzona | integration, świeży owner na tym samym stanie |
| Plik w stagingu zmieniony po H2: (a) w trakcie kontroli, (b) po kontroli przed rezerwacją, (c) po rezerwacji, z restartem przed kopią | (a) brak wyniku, powtórka; (b) i (c) rezerwacja ma stempel z kontroli, więc kopia odmawia (`expected` ≠ `file_stamp`): problem publikacji, bez publikacji do roota i bez zużycia próby (D-29) | unit ownera z prawdziwym `copy_staged` na `tmp_path` (D-29) |
| Data emisji przesunięta w przyszłość przy `due` bez próby | `awaiting_airing` z nowym `due_at` | unit |
| AniList podaje mniej odcinków niż cele | cele zostają (przynależność stała) i są szukane dalej; cel `> episode_count` blokuje zamknięcie; U07/U08 pokazują wyliczony konflikt do rozliczenia przez użytkownika (D-23) | unit, D-23 |
| Awaria ani.zip (wyjątek, timeout, pusta odpowiedź 404) przy działającej subskrypcji, także po restarcie ownera | odświeżenie i oferta używają mapowania rekordu (D-27); próby trwają; `check` z `mapping_source=snapshot`; mapowanie, `refreshed_at` i `problem` bez zmian | unit ownera + prawdziwy `AniZipCatalog` na `httpx.MockTransport` |
| Konflikt Kitsu ID, potem zgodny odczyt | odświeżenie naprawcze ma termin mimo braku prób; zgodny odczyt na żywo zdejmuje `catalog_conflict` | unit ownera (§5.5) |
| Awaria harmonogramu AniList w pierwszym przeglądzie migracji | `review_pending` zostaje; ponowienie po `schedule_retry_at`/`retry_delays_s`; zakończenie dopiero z kompletnymi danymi | unit ownera (D-18) |
| Dodanie wpisu HIATUS bez harmonogramu albo przy awarii harmonogramu | `subscription_cut_unknown`, brak zapisu (D-28) | unit, cli |
| Anulowanie martwej albo odrzuconej przez H2 próby → zapis → restart → następna próba | po potwierdzonym anulowaniu drugie przyjęcie z `previous=None` (brak chronionych przypisań klucza), `attempts=2`, ten sam cel; przed potwierdzeniem brak przyjęcia; także dla próby bez metadanych | unit ownera (D-12) |
| Próba na torrencie współdzielonym odrzucona przez H2 | zakres wycofany (`replaced`), transfer kończy się dla pozostałych przypisań; następna próba z `previous` = ostatnie chronione przypisanie klucza | unit ownera (D-12) |
| Współdzielony → własny → trzecia próba: próba 1 zastąpiona na współdzielonym (chroniona), próba 2 anulowana na własnym (niechroniona) | trzecie przyjęcie z `previous` = próba 1, bez `episode_admitted` i `episode_changed`; `selection_revision` współdzielonego transferu nie rośnie drugi raz; to samo po restarcie | unit ownera (D-12) |
| Klucz ma chronione przypisanie ręczne nowsze niż zamknięta próba | brak następnej próby, cel `manual` (D-13) | unit ownera (D-12) |
| Ręczne D dołącza w pauzie do transferu próby subskrypcji wstrzymanego pauzą | transfer ręczny, wznowiony w zapisie rozliczającym stop pauzy; po zniknięciu przypisania ręcznego stop pauzy w tym samym zapisie, także bez innych aktywnych transferów | unit ownera, ze stopem rozliczonym i nierozliczonym, po restarcie (D-04) |
| Próba dołącza do transferu ręcznego przed pauzą, potem pauza i restart | transfer ręczny pracuje w pauzie i po restarcie | unit ownera (D-04) |
| Restart przed końcem przeglądu migracji | `review_pending` i `migrated_at` bez zmian; odświeżenie po starcie | unit (D-18) |
| Odcinek z samą datą ani.zip | traktowany jako bez daty (D-06) | unit |
| Dwie subskrypcje różnych wpisów trafiają w ten sam plik | para przyjęta dla innego celu nie jest dopuszczalna (`eligible`) | unit |
| 429 z Torrentio | `check` z `429`; termin przesunięty przez blokadę dostawcy; brak zużycia próby | integration z atrapą źródła |
| Zapis stanu zawodzi w sprawdzeniu | `_subscriptions_problem`, stały wiersz, ponowienie; brak skutku w qB | integration |
| Subskrypcja usunięta w trakcie sprawdzenia (wynik wraca z puli) | wynik odrzucony na wątku ownera po ponownym odczycie rekordu: `subscription_id` nieobecny, subskrypcja wstrzymana albo cel w innym stanie niż przy starcie sprawdzenia | unit ownera |
| `Ctrl+Z` po emisji, która nastąpiła w czasie usunięcia | cel wraca jako `due` i jest szukany | unit |
| Cel `exhausted`, użytkownik `P` w U08 | zwykłe ręczne pobranie → `manual` | integration |

## 6. Mapa plików

### 6.1 CREATE

| Ścieżka | Rola |
| --- | --- |
| `anishift/application/subscription_targets.py` | typy §5.2 i czyste reguły §5.4–§5.5 |
| `anishift/application/subscription_migration.py` | czysta migracja §5.14 pkt 3 |
| `anishift/application/download_verification.py` | port reguł H2 ze `scripts/tmp/download_verification.py` (bez `next_step`: decyzję o następnej próbie podejmuje maszyna stanów; bez CLI i pydantic skryptu, jeśli wejście daje `MediaCatalog`) |
| `tests/application/test_subscription_targets.py` | reguły, harmonogram na atrapie zegara |
| `tests/application/test_subscription_migration.py` | M-01–M-06, idempotencja, D-19 |
| `tests/application/test_download_verification.py` | port testów reguł; syntetyki z `h2_synthetics.py` przez `tmp_path` |
| `tests/application/test_subscription_owner.py` | owner: IPC, sprawdzenie, próby, H2, cień, powiadomienia, autozamknięcie, restart |
| `tests/cli/test_subscriptions_panel.py` | U06, U07, U08, klawisze, renderowanie bez I/O |
| `tests/integration/test_subscription_flow.py` | prawdziwy prywatny qB i syntetyczny torrent (reuse helperów E2 z `tests/integration/episode_download_support.py`) |
| `docs/work/acquisition/outcomes/e3.md` | wynik etapu (F4) |

### 6.2 MODIFY

| Ścieżka | Rola |
| --- | --- |
| `anishift/application/control.py` | `WATCH_STATE_SCHEMA_VERSION = 4`; `AdmissionSource.SUBSCRIPTION`; pola `EpisodeAssignment`; trzy pola `WatchState`; `LegacyOrder`; `AcquisitionConfirmation.manual` wg D-04 |
| `anishift/application/watch_state.py` | wersja 4, walidacja wersjonowana, migracja do 4 (także bez `state.json`), kopia `.e3-migration.bak` (sparametryzowany mechanizm E2), kodek `SubscriptionRecord`/`AniZipMapping`/`LegacyOrder` |
| `anishift/application/subscriptions.py` | tylko wydzielenie `decode_subscriptions` (§5.14 pkt 1) i usunięcia §6.3 |
| `anishift/application/acquisition.py` | `read_listing`/`ListingRead`, `episodes()` przez `read_listing`, `mapping` w `prepare_episode` (D-27) |
| `anishift/application/automation.py` | polecenia §5.12; `_schedule_subscriptions`/`_poll_subscriptions` z nowym terminem, przeglądem migracji i odświeżeniem naprawczym; przebieg sprawdzenia; `_admit_episode` z `source/origin/subscription_id/attempt`; settle celów po przejściach przypisań; zamykanie prób i `previous` (D-12); strażnik `replaced` w `_replace_episode_scope`; H2 w `_publish_episode` przed `_reserve_publication`, rezerwacja z `verification`/`verified_stamp`, `expected` w `_copied` (D-29); `media_probe` w konstruktorze; `_legacy_scopes` i `_episode_conflicts` ze stanu; `_pause_ownership` w `_save` i suma w `_stopped_transfers` (D-04, §5.6); `held` w `_poll_transfers` (D-30); `_resumable` bez `_enabled_subscriptions`; powiadomienia; Historia; cień; usunięcia §6.3 |
| `anishift/application/transfers.py` | `inspect(..., held=...)`; `_record_progress` zachowuje pomiar hasha z `held` nieobecnego w obserwacji jako `downloading=False` (D-30). Test: pomiar przeżywa inspekcję innego transferu, a hash spoza `held` traci pomiar jak dziś |
| `anishift/application/acquisition_staging.py` | `copy_staged(..., expected: FileStamp \| None = None)`; przy `expected` różnym od `file_stamp` źródła przed kopiowaniem → `_CHANGED_WHILE_COPIED` (D-29). Test: zgodny stamp kopiuje, inny odmawia bez kopii, `None` jak dziś |
| `anishift/application/acquisition_decisions.py` | pola `_FIELDS` §5.8 |
| `anishift/application/episode_commands.py` | nowe `EpisodeReason` dla stanów celu i odmów (np. `SUBSCRIPTION_AWAITING_RELEASE`, `SUBSCRIPTION_EXHAUSTED`, `LEGACY_ORDERED`); test pokrycia etykiet z F-03 obejmuje nowe wartości |
| `anishift/application/history.py` | `HistoryKind.SUBSCRIPTION_FINISHED` |
| `anishift/application/__init__.py` | eksport fasady: nowe typy i `cut_point`/`is_target` dla panelu; usunięcie eksportów starego modelu, których panel już nie używa (`SubscriptionService` zostaje tylko dla `bootstrap`/migracji, jeśli potrzebny) |
| `anishift/application/service.py` | `AppService.subscriptions` usunięte (D-21), jeśli po zmianach nie ma konsumentów; ścieżka starego pliku przekazana do `WatchStateStore` jak dziś (`watch_state.py:311-316`) |
| `anishift/bootstrap.py` | koniec budowy `SubscriptionService` (`bootstrap.py:142-152`) |
| `anishift/config/settings.py` | `subscription_shadow: bool = False` |
| `anishift/cli/interactive/state.py` | zakładka Subskrypcje = U07; usunięcie starego szkicu i zakresu; P z Historii dla starych subskrypcji |
| `anishift/cli/interactive/anime.py`, `anime_view.py`, `anime_state.py` | `S` → U06; U06; tryb U08 (nagłówek, stany celu, Dodatki, `W/F/X`); tryb „dodaj subskrypcję” z U07 |
| `anishift/cli/interactive/prompts.py` | binding `Delete`, jeśli brak |
| `anishift/cli/resident.py` | metody sesji dla poleceń §5.12; usunięcie `set_range/repeat/_subscription/follow/subscription_retry_proposal` |
| `anishift/cli/main.py` | `subs list/remove/check <id>` przez IPC nowych rodzajów (`subs check` wymaga ID, S-06) |
| `anishift/cli/watch.py` | budowa ownera rezydenta (`watch.py:352-364`): `media_probe=DefaultMediaProbe()` i `subscription_shadow` z `Settings` usługi; usunięcie `_check_subscriptions` z pętli `run_daemon` (`watch.py:245-261`); pętla zostaje do E5 |
| `anishift/application/AGENTS.md`, `anishift/cli/AGENTS.md`, `AGENTS.md` (sekcja Dane runtime), `README.md` | opis nowego modelu, źródła prawdy, zamrożonego pliku i panelu |
| testy `acquisition` w `tests/application/` | `read_listing` (na żywo, wyjątek z zapisem, 404 przez prawdziwy `AniZipCatalog` na `httpx.MockTransport`, bez zapisu), `episodes()` bez zmiany zachowania, `prepare_episode(mapping=…)` bez odczytu ani.zip |
| testy istniejące, które kodują stare kontrakty subskrypcji (`tests/application/test_subscriptions*.py`, `tests/application/test_automation*.py`, `tests/cli/test_*subscription*`) | test usunąć tylko razem z usuniętym kontraktem (§6.3); test kontraktu nadal obowiązującego przenieść na nowy model |

Ścieżki testów istniejących wykonawca ustala grepem `subscription` w `tests/`. Lista wyżej to
reguła, nie inwentarz.

### 6.3 DELETE (C1: tylko to, co wymusza przeniesienie)

| Element | Dlaczego teraz |
| --- | --- |
| `SubscriptionService` poza `SubscriptionStore.load` i dekoderami (`subscriptions.py:460-2041` w części sprawdzania, zakresu, powtórek, kalendarza) | po migracji byłby drugim źródłem prawdy; jedyny zostający konsument to migracja |
| owner: `_check_subscriptions`, `_admit_subscription`, `_new_acquisition`, `_record_subscription`, `_check_due_subscriptions` (stara treść), `_retry_subscription_checks`, `_reconcile_subscription_sources`, `_enabled_subscriptions`, `_subscription_counts`, `_subscription_mutation`, gałęzie `subscription_*` w `_finish_local_command`, `_subscription_command` routing starych rodzajów, `_subscription_retry_proposal`, gałąź `subscription_id` w `_legacy_episode_records`, gałąź `service.subscriptions` w `_episode_conflicts` (zastąpiona `legacy_orders`, §5.6) | wołają stary serwis lub plik (`automation.py:2631-2639`, `3366-3540`, `3714-3890`, `4175-4191`, `4202-4229`, `4733-4756`, `6242-6355`) |
| `cli/interactive/subscriptions.py` | stary szkic grupy wydań |
| `ResidentSession.set_range/repeat/_subscription/follow/subscription_retry_proposal` | stare rodzaje IPC |
| `cli/watch.py:_check_subscriptions` | woła usunięty serwis |

Zostaje do E5 (świadomie): `SubscriptionStore` i dekodery starego pliku (czytnik migracji),
`search_title`, `_group_queries`, `catalog_releases`, `order_groups`, polecenie ownera
`download`, `ResidentSession.search/download`, `run_daemon`, pola `AutomationPolicy`
`release_delay_default_s`/`recheck_interval_s`/`search_window_s`.

Jeżeli usunięcie z listy pociąga za sobą usunięcie elementu z listy „zostaje do E5”, bo
staje się nieosiągalny, wykonawca go **nie** usuwa i zgłasza to w wyniku. Nieużywany kod
zostaje do E5.

### 6.4 READ ONLY

`episode_identity.py` (klasyfikacja H1, golden),
`episode_selection.py` (ranking, `suggestion`, `identity_target`, typy), `services/media/*`, `services/catalog/*`, `services/torrents/*`,
`platform/tray.py`, `platform/local_control.py`, `scripts/tmp/download_verification.py`,
`scripts/tmp/h2_synthetics.py`, `scripts/tmp/test_download_verification.py` (źródło portu).

## 7. Plan wykonania

Jeden brief dla `opus55` na cały etap (`.agents/skills/subagent/assets/SUBAGENT-BRIEF.template.md`),
fazy wykonywane po kolei. Po każdej fazie: autor sam iteruje do „gotowe do commita” →
orkiestrator sprawdza diff, PNG i bramki → `astra` recenzuje całą fazę i oddaje wszystkie
findingi naraz → poprawki → `astra` weryfikuje do PASS → orkiestrator commituje
(`feat(application): …`/`feat(cli): …`, scope z `scripts/hooks/check_commit_msg.py`) →
`uv run anishift watch stop`, potem `uv run anishift` → test na żywo z tabeli fazy.
Właściciel dostaje wynik dopiero po F4.

### F0 — Preflight (orkiestrator, bez commita)

1. `git status`, `git log --oneline -3` = baseline. Zapisz wyniki bramek baseline (lista
   flaky z §1).
2. Wykonawca czyta: ten plan, `application/AGENTS.md`, `cli/AGENTS.md`, `tests/AGENTS.md`,
   skille `coding` (+`python.md`, `testing.md`, `comments-docstrings.md`), `simple`.
3. Orkiestrator robi kopię prywatnego stanu do testu migracji (§9.2, krok 1) przed
   pierwszym uruchomieniem kodu F1.

**Gate:** baseline zapisany, kopia istnieje.

### F1 — Stan, migracja i lista Subskrypcje (pierwsza widoczna wartość)

**Cel:** stare subskrypcje właściciela przeniesione do `WatchState` i widoczne w nowej
liście U07 z poprawnym stanem. Wstrzymanie, usunięcie i `Ctrl+Z` działają. Stara ścieżka
nie sprawdza już niczego. Nic nie jest pobierane automatycznie.

**Działania:**

1. `subscription_targets.py`: typy §5.2, `after_close`, `display_order`, inwarianty.
2. `control.py` + `watch_state.py` + `subscriptions.py`: schemat 4, walidacja wersjonowana,
   `decode_subscriptions`, kopia `.e3-migration.bak`, migracja (`subscription_migration.py`)
   wg §5.14 pkt 1–3, 5–7, w tym przypadek bez `state.json`, scalenie D-26 i `LegacyOrder` D-14.
3. Owner: `_legacy_scopes` i `_episode_conflicts` ze stanu (§5.6); polecenia
   `subscriptions_list`, `subscription_get` (bez dodatków),
   `subscription_pause/resume/remove/restore`; usunięcia §6.3. Owner w F1 nie ma terminu
   sprawdzeń ani przeglądu: `_schedule_subscriptions` zwraca brak terminu, dopóki F2 nie
   podłączy nowego. Migrowane rekordy czekają z `review_pending=True` i nie robią prób.
4. Panel: U07 (wiersze z danymi rekordu; dla `review_pending` stan „Sprawdzam przeniesioną
   subskrypcję”, a dla wstrzymanych powód; opis problemu M-05), `W/Space`, `Delete/X`,
   `Ctrl+Z`, stały wiersz pauzy. `D` i `F` w F1 pokazują notkę „Dostępne po aktualizacji” —
   usuwa ją F2 (jedyna tymczasowość, znika w następnej fazie).
5. `cli/main.py` `subs list/remove` przez IPC. `cli/watch.py` bez `_check_subscriptions`.

**Inwarianty:** brak zapisu do `subscriptions.json` w każdej ścieżce (także wersji 1–3 tego
pliku); drugi `load()` bez zmiany bajtów; `episode_download`/`episode_choose` nie odmawiają
`LEGACY_UNREADABLE` z powodu pliku subskrypcji; stare transfery (M-06) przechodzą istniejące
testy E2 bez zmian.

**Dowody:**

- unit: migracja każdej kombinacji `enabled × end_state × anilist_id` (M-01–M-05, D-18, D-19);
  plik subskrypcji w wersjach 1, 2, 3 i 4 → identyczne bajty pliku po migracji i brak nowej
  kopii `.v<n>.bak`; brak `state.json` + istniejący plik subskrypcji → migracja i zapis;
  brak obu → stan domyślny bez zapisu; awaria `save()` → `ConfigError`, oba wejścia bez
  zmian bajtów, następny `load()` kończy migrację; dwie stare subskrypcje tego samego sezonu
  (różne grupy, jedna wyłączona, jedna z `taken`, jedna z potwierdzeniem w kliencie) →
  jeden rekord, `merged_from` z oboma ID, żadne zlecenie ani `legacy_scope` nie ginie (D-26);
  `legacy_orders` (zakres i `reference`) = wynik dzisiejszych `_legacy_scopes` i
  `_episode_conflicts` na tych samych danych, także dla starego potwierdzenia bez
  `legacy_scope`; `acquisitions` po migracji równe wejściu (test porównawczy na fixture stanu
  schematu 3 i pliku schematu 4); kopie `.e3-migration.bak` bajt w bajt, istniejąca kopia nienadpisana,
  błąd kopii → `ConfigError` bez zapisu; uszkodzony plik → `ConfigError`; idempotencja.
- unit ownera: pause/resume/remove/restore z receipt i powtórzonym `command_id`; restore
  przy istniejącym `anilist_id` → odmowa; I-06: przyjęcie ręczne odcinka pokrytego
  `legacy_orders` → `episode_possibly_admitted`; P (propozycja i potwierdzenie konfliktu
  legacy) dla odcinka z samym `taken` bez `AcquisitionConfirmation` daje te same referencje
  przed migracją, po niej i po restarcie ownera.
- cli: render U07 (pusta lista, pauza, problem M-05, przegląd migracji, wstrzymana przez użytkownika i `migrated_missing`), klawisze, brak
  I/O w renderze (istniejący wzorzec testów `StateController`), PNG przy 120 i 50 kolumnach.
- regresja: pełny `uv run pytest -n auto`.

**Test na żywo (orkiestrator):** restart rezydenta na kopii roboczej prywatnego stanu nie
jest możliwy bez ruszania danych właściciela, więc najpierw krok §9.2 na kopii w katalogu
tymczasowym (`ANISHIFT_WORKSPACE_ROOT` i katalog konfiguracji wskazane na kopię; wykonawca
ustala mechanizm wskazania katalogu `config/` z `anishift/paths.py`, a gdy go nie ma —
patrz §10, R-3). Dopiero po PASS: restart prawdziwego rezydenta. Sprawdzić: istnieją
`config/watch/state.json.e3-migration.bak` i `config/subscriptions.json.e3-migration.bak`;
liczba wierszy U07 = liczba starych subskrypcji minus zakończone kompletne, minus scalone
duplikaty sezonu (D-26); SHA-256 `config/subscriptions.json` bez zmian; żadnego nowego
transferu w qB; Biblioteka i Przetwarzanie bez zmian.

**Gate:** bramki repo PASS; `astra` PASS; test na żywo zgodny.

### F2 — Dodawanie, harmonogram, sprawdzenie i tryb cienia

**Cel:** subskrypcję można dodać z `S` w U03 i z `D` w U07. Lista pokazuje odliczanie i stany
oczekiwania. Owner według U-14/U-15 sprawdza źródło, wybiera kandydata (H1) i zapisuje
`check`/`proposal`, **ale nie przyjmuje prób** — cała F2 działa jak tryb cienia. Przełącznik
S-15 zostaje stałym trybem, który F3 tylko zwalnia.

**Działania:**

1. `subscription_targets.py`: `cut_point`, `is_target`, `merge_listing`, `next_search_at`,
   `next_check_at`, `eligible` (tylko `MATCH`, D-10), `completed` (zamknięcie wykonuje F3).
2. Owner: `subscription_add` (pula I/O → zapis, D-28, mapowanie D-27), termin
   `_schedule_subscriptions` z `next_check_at`, przeglądem migracji i odświeżeniem naprawczym
   (§5.5), przebieg sprawdzenia per subskrypcja z izolacją wyjątków (S-12), odświeżenie listy
   z D-18 dla migrowanych, `read_listing` i `prepare_episode(mapping=…)` w `acquisition.py`
   (D-27), `check`/`proposal` w rejestrze, log S-13
   (`logger.info("Subscription checked", subscription_id, number, match, uncertain,
   mismatch, decision)`, bez tytułów i payloadów), `subscription_check` z wynikiem S-06,
   `subscription_get` z dodatkami.
3. `Settings.subscription_shadow`; w F2 owner zachowuje się tak, jakby był włączony
   niezależnie od wartości (jedna gałąź kodu: `admit = not shadow and attempts_enabled`,
   gdzie `attempts_enabled` włącza F3).
4. Panel: `S` w U02/wpisach/U03, także na zapowiedzi (§5.13) → U06; `D` w U07 → U01 → `S` →
   U06 → powrót do U07 z podświetleniem;
   `F` z wynikiem 10 s; U08 (nagłówek, stany celu, Dodatki); stany „Czeka na emisję”,
   „Czeka na wydanie E8 (od 5 h)”, „Termin nieznany”, „Przerwa w emisji”.
5. `subs check <id>` w CLI.

**Inwarianty:** brak przyjęć i transferów z subskrypcji; Q-02: jedno odświeżenie listy i jedno
Torrentio na cel na sprawdzenie; zegar wyłącznie wstrzykiwany; render bez I/O.

**Dowody:**

- unit (atrapa zegara, bez `sleep`): przynależność W-b/U-09 (`airs_at > t_sub`, bez daty
  `> n_cut`, zapowiedź = wszystkie), `cut_point` dla RELEASING, HIATUS z datami i bez,
  awarii harmonogramu i samych dat ani.zip (D-28), U-15, D-06, kroki U-14 na granicach 24 h i
  72 h, przesunięcie daty (w. 2–3), K-06 konflikt Kitsu, `display_order` S-03; `eligible`
  odrzuca każdy `INSUFFICIENT` i `MISMATCH` niezależnie od wieku celu; kodek mapowania:
  zapisane i wczytane `AniZipMapping` jest równe wejściu (w tym kolejność `raw_episodes`,
  tytuły, dodatki), a `identity_target` z wczytanego daje wynik identyczny z wejściowym dla
  każdego numeru.
- owner: sprawdzenie dwóch subskrypcji, z których jedna rzuca błąd źródła → druga
  sprawdzona (S-12); 429 → blokada dostawcy i nowy termin; awaria ani.zip (wyjątek oraz 404
  przez prawdziwy `AniZipCatalog` na `httpx.MockTransport`) przy zapisanym mapowaniu →
  sprawdzenie i `proposal` działają, `check` z `mapping_source=snapshot`, mapowanie i
  `refreshed_at` bez zmian (U-22); to samo po restarcie ownera na tym samym stanie; bez
  zapisanego mapowania (nowy tytuł) → błąd źródła; `prepare_episode` dostaje mapowanie z
  `ListingRead` tego samego sprawdzenia (atrapa liczy odczyty ani.zip: jeden na
  sprawdzenie); `subscription_add` dla `FINISHED` → `subscription_not_airing` (U-10); HIATUS
  bez dat → `subscription_cut_unknown` bez zapisu; duplikat → `subscription_exists`; limit
  100; przegląd migracji: wstrzymany rekord z `review_pending` dostaje odświeżenie,
  opóźniony przegląd (cel wyemitowany między `migrated_at` a odświeżeniem) nie wstrzymuje
  rekordu, restart przed końcem przeglądu go ponawia, a awaria harmonogramu albo zapis
  zamiast odczytu na żywo go nie kończy (D-18); konflikt Kitsu → odświeżenie naprawcze ma
  termin → zgodny odczyt zdejmuje problem (§5.5); rozmiary ramek wg §5.12 (Q-08); `check` i
  `proposal` mają tylko pola z `_FIELDS`, w tym `mapping_source` (test istniejącego
  `_evidence`).
- cli: U06 (nieznana liczba odcinków, zapowiedź bez dat, pauza globalna, „już
  subskrybowany”, nieznany punkt odcięcia), pełna droga wyszukiwarka → zapowiedź na liście
  tytułów → `S` → U06 → Dodaj przy pustej liście odcinków, Esc z U06 wraca na ekran
  wyjściowy; U07 z odliczaniem (atrapa zegara renderera), U08; PNG 120/50 kolumn.

**Test na żywo (orkiestrator):** dodać jedną subskrypcję tytułu w emisji (S i D); sprawdzić
odliczanie, „Od odc.” zgodne z AniList, brak transferu w qB po `F`; w `decisions.jsonl` są
nowe linie `check`/`proposal` (sprawdzić tylko liczbę linii i `kind`, bez treści); migrowane
subskrypcje po odświeżeniu mają stan M-01/M-03 zgodny z danymi.

**Gate:** jak F1.

### F3 — Próby, H2, wyczerpanie, powiadomienia, autozamknięcie

**Cel:** subskrypcja sama zleca próby przez bramkę E2, kontroluje plik H2 przed Auto, ponawia
do 3 prób, powiadamia po 7 dobach i po wyczerpaniu, zamyka się po sezonie. Cień działa
wyłącznie, gdy `subscription_shadow=True`.

**Działania:**

1. `download_verification.py` (port + testy przez `tmp_path`); `media_probe: MediaProbe` w
   konstruktorze ownera, w rezydencie `DefaultMediaProbe()` z `cli/watch.py` (D-29).
2. `_admit_episode` z `source/origin/subscription_id/attempt`; `choose_candidate` →
   przyjęcie; `tried`, `previous` wg D-12.
3. Settle celu po każdym przejściu przypisania (w miejscach, gdzie owner zapisuje zmianę
   potwierdzenia: `_replace_acquisition` i uzgodnienia), zamykanie prób wg D-11 i D-12
   (anulowanie własnego torrentu albo wycofanie zakresu na współdzielonym), następna próba
   wg D-12; `attempt` w rejestrze.
4. H2 przed `_reserve_publication` z wiązaniem `file_stamp` i `expected` w `copy_staged`
   (§5.7, D-29), stan „Kontrola”, oznaczenie „Kontrola niewykonana”.
5. Ręczne zastąpienie (D-13), `manual` wg D-04 z niezmiennikiem pauzy w `_save` (§5.6),
   `held` w `TransferInspector` (D-30), `episode_states` z celem (§5.13 U08).
6. S-14 i wyczerpanie: powiadomienia §5.10, `escalation`.
7. U-11: `completed` wg D-23 → usunięcie rekordu + Historia S-09 + wiersz znika; konflikt
   liczby odcinków w U07/U08.

**Inwarianty:** plik próby wchodzi do Auto wyłącznie po `handed_off` przypisania z
`verification` różnym od `reject:*` (U-19); I-06 między subskrypcją, D i drugim panelem;
I-05: render, nawigacja, odliczanie i restart nie tworzą przyjęć; I-07 bez zmian.

**Dowody (scenariusze end-to-end na atrapie zegara i atrapach źródeł; masterplan §5.1
researchu):**

| Nr | Scenariusz | Oczekiwane |
| --- | --- | --- |
| E-1 | emisja → sprawdzenie → `zgodny` → przyjęcie → metadane → pobieranie → H2 `no_contradiction` → publikacja → Auto | cel `satisfied`; jedno przyjęcie; `selection` + `attempt accepted` |
| E-2 | brak kandydatów 7 dób | kroki U-14; jedno powiadomienie `late`; szukanie co 24 h dalej |
| E-3 | trzy próby w dwóch kolejnościach: (i) metadane timeout, `no_video_stream`, zastój; (ii) `no_video_stream`, metadane timeout, zastój. Każda na własnym torrencie (potwierdzone anulowanie → `previous=None`), wariant na torrencie współdzielonym (wycofanie zakresu → `previous`) oraz wariant mieszany: współdzielony → własny → trzecia próba (`previous` = próba 1), także z restartem przed trzecim przyjęciem | cel `exhausted`; trzy różne pary w `tried`; drugie i trzecie przyjęcie nie dostaje `episode_admitted` ani `episode_changed`; odrzucona przez H2 próba nie ma publikacji ani pliku w roocie; przed potwierdzeniem anulowania nie ma następnego przyjęcia; start treści następnej próby na współdzielonym czeka na `_replacement_ready`; jedno powiadomienie; brak czwartej próby; restart między anulowaniem a następnym przyjęciem nie zmienia wyniku ani nie daje drugiego przyjęcia (receipt) |
| E-4 | dla należnego celu tylko `niepewne` przez 7 dób, potem pojawia się `zgodny` | brak próby z `niepewnym` w każdym wieku celu; jedno powiadomienie `late`; `last_check` i `F` pokazują liczbę `niepewnych`; po pojawieniu się `zgodnego` próba z nim; ręczne D w U08 na `niepewnym` przechodzi istniejącą drogą E2 i daje `manual` |
| E-5 | restart ownera w każdym punkcie E-1 (po przyjęciu, po add, w trakcie pobierania, w trakcie H2, po rezerwacji przed kopią, po publikacji) | brak drugiego przyjęcia/publikacji; stan ciągły; po rezerwacji kopia sprawdza `verified_stamp`, bez drugiej kontroli |
| E-6 | D w Anime na celu `due` oraz na celu `attempting` | `manual`; aktywna próba zastąpiona i policzona |
| E-7 | dwie subskrypcje, jedna z ciągłym błędem źródła | druga kończy E-1 (S-12) |
| E-8 | sezon `FINISHED`: (a) wszystkie cele `satisfied`; (b) jeden `exhausted`; (c) jeden `manual` tylko zlecony (przyjęty, niepobrany); (d) jeden `legacy_ordered` z samym `taken`, a drugi z `COMPLETE`; (e) AniList zmniejszył liczbę odcinków: cel nadmiarowy niespełniony (bez próby, `exhausted`, z aktywną próbą), potem ręczne D tego celu albo usunięcie subskrypcji; (f) stare potwierdzenie `legacy_ordered` przechodzi w `COMPLETE` po migracji | (a) rekord usunięty, Historia `SUBSCRIPTION_FINISHED` „pobrano y/y”; (b), (c), (d `taken`) brak zamknięcia; (d `COMPLETE`) spełniony; (e) brak zamknięcia w każdym wariancie, konflikt widoczny w U07/U08, zamknięcie dopiero po pobraniu tego celu, usunięcie działa jak S-08; (f) spełniony bez nowego zapisu `LegacyOrder` |
| E-9 | pauza subskrypcji w trakcie próby; pauza globalna: (i) w fazie pobierania po 9 min zastoju (`T_zastój` = 10 min w teście), pauza dłuższa niż 10 min, wznowienie, 1 min zastoju, w dwóch wariantach: bez innych transferów oraz z równoległym ręcznym pobieraniem odpytywanym w pauzie; (ii) w fazie metadanych po 9 min (`T_metadane` = 10 min w teście), pauza dłuższa niż 10 min, w obu wariantach, potem wznowienie i 1 min bez listy plików; (iii) metadane przychodzą w pauzie | S-07: próba trwa, nowe sprawdzenia i próby stoją (`spec.md` S-07, korekta 2026-10-03); (i) transfer zatrzymany i wznowiony, w pauzie brak zamknięcia, po wznowieniu zastój = 9 + 1 min → próba martwa dokładnie wtedy w obu wariantach (pomiar przeżywa odpytywanie ręcznego transferu, przerwa wykluczona); (ii) transfer nie jest zatrzymany, w pauzie brak timeoutu, po wznowieniu timeout dokładnie po 9 + 1 min; (iii) selekcja i start treści dopiero po wznowieniu; w pauzie brak nowych prób (D-30) |
| E-10 | usunięcie z aktywną próbą odrzuconą przez H2 | brak następnej próby (D-24); `Ctrl+Z` przywraca z `attempts` |
| E-11 | cień włączony | `proposal`, brak przyjęcia, qB nietknięty |
| E-12 | H2 timeout ×2 i brak binarki | `skipped`, przyjęcie, `escalation` |
| E-13 | paczka mieszana (decyzja B): (i) D dołącza w pauzie do transferu próby wstrzymanego pauzą, ze stopem pauzy rozliczonym i ze stopem jeszcze w drodze (spóźniony wynik workera); (ii) próba dołącza do transferu ręcznego **przed** pauzą, potem pauza i restart ownera; (iii) przypisanie ręczne zastąpione albo anulowane w pauzie, gdy to był jedyny aktywny transfer (brak innych rund); każdy wariant także po restarcie ownera | (i) transfer wznowiony w zapisie, który rozlicza stop, inne transfery automatu zostają w `pause_owned_transfers`; (ii) transfer pracuje w pauzie i po restarcie; (iii) ten sam zapis, który usuwa przypisanie ręczne, dodaje stop pauzy i hash do `pause_owned_transfers`, a `_schedule_transfers` daje rundę, która wysyła stop; wznowienie `O` go kontynuuje; wynik nie zależy od kolejności ani restartu |
| E-14 | awaria ani.zip (wyjątek, timeout i pusta odpowiedź 404) przy działającej subskrypcji z zapisanym mapowaniem, także po restarcie ownera | sprawdzenie, przyjęcie i H2 (`ExpectedEpisode` z mapowania rekordu) działają; `check` z `mapping_source=snapshot`; mapowanie rekordu bez zmian |

Integracja z prawdziwym prywatnym qB (`tests/integration/test_subscription_flow.py`, reuse
fixture E2 i syntetycznego torrenta `outcomes/e2.md:110-111`): E-1 na **rzeczywistym układzie
stagingu E2** (H2 na pliku w `staging_path`, prawdziwy `DefaultMediaProbe`; poprawny MKV daje
`no_contradiction`, nie `skipped`), E-3 (odrzucenie `no_video_stream` na pliku bez wideo z
syntetyku, brak pliku w roocie, następna próba po potwierdzonym anulowaniu) oraz E-5 po
restarcie procesu ownera.

**Koszt stanu (F3, budżet E2):** fixture z `e2-pobieranie.md:392` (10 000 zakończonych
przyjęć selektywnych + 10 aktywnych) plus 100 subskrypcji z pełnymi mapowaniami ani.zip
(surowe odcinki w rozmiarze realnej odpowiedzi, z opisami), w tym jedna z 2000 celów i
mapowaniem 2000 odcinków, oraz `legacy_orders` 5000 wpisów. Pełny `state.json` ≤ 64 MiB,
P95 pełnego `WatchStateStore.save()` ≤ 1 s, ta sama metoda (rozgrzewka + 20 zapisów, bez
mocków). Zapisać rozmiar, P50/P95 i sprzęt. Przekroczenie zatrzymuje gate i wymaga
przeplanowania zapisu; progu się nie podnosi.

**Test na żywo (orkiestrator):** na subskrypcji z F2 albo dodanej na odcinek, który właśnie
wyemitowano: obserwacja przyjęcia w Przetwarzaniu, H2 („Kontrola E…”), Auto, wynik w
Bibliotece; `decisions.jsonl` zawiera `selection` i `attempt` z `path=subscription`; zero
transferów spoza zamówionego odcinka (lista plików qB). Gdy w oknie testu nic nie wychodzi,
test na żywo ogranicza się do restartu i potwierdzenia, że owner nie przyjął niczego bez
emisji, a pełny dowód daje H3.

**Gate:** jak F1 + integracja z qB PASS na pulpicie orkiestratora + koszt stanu w progach
budżetu E2.

### F4 — Odbiór etapu

1. Aktualizacja `application/AGENTS.md` (sekcja „Katalog wydań i subskrypcje” zastąpiona
   nowym modelem; zdanie o `LEGACY_UNREADABLE`), `cli/AGENTS.md` (Subskrypcje, `S`), root
   `AGENTS.md` (Dane runtime: subskrypcje w `state.json`, `subscriptions.json` zamrożony),
   `README.md` (subskrypcje). Usunięcie nieaktualnych zdań, bez nowej prozy ponad potrzebę.
2. `outcomes/e3.md`: fazy, autorzy, commity, dowody, odchylenia, otwarte ryzyka.
3. Orkiestrator: restart, pełny scenariusz §9.1 kroki 1–3, rozmiar `decisions.jsonl`,
   przekazanie właścicielowi H3 krok 4.

**Gate:** `astra` PASS dla dokumentów; H3 rozpoczęte. E3 `ACCEPTED` dopiero po H3.

## 8. Strategia dowodu i bramki

| Twierdzenie | Kontrola | Dlaczego wystarcza |
| --- | --- | --- |
| Migracja nie gubi subskrypcji ani zleceń | unit na fixture + test na kopii prywatnego stanu (§9.2) | fixture pokrywa kombinacje; kopia pokrywa realne dane |
| Jedno zlecenie odcinka z dwóch wejść (I-06) | owner: subskrypcja vs D vs drugi panel; integracja E-5 | ta sama bramka `_admit_episode`/`episode_conflict` |
| Harmonogram U-14/U-15 | unit na atrapie zegara na granicach | reguła czysta |
| Plik próby do Auto tylko po przyjęciu (U-19) | owner E-3 + integracja z qB (pliki w roocie) | obserwacja roota, nie stanu |
| Limit 3 prób i wykluczanie par | E-3 | trzy różne przyczyny zamknięcia, H2 jako pierwsza i druga porażka |
| Następna próba po zamknięciu (D-12) | E-3 + edge cases §5.15 | `previous` z tej samej listy co `_admission_refusal`; własny, współdzielony i mieszany ciąg prób; restart |
| Wynik H2 dotyczy kopiowanych bajtów | edge case „plik zmieniony po H2” + E-5 | `file_stamp` przed i po kontroli, zapis z rezerwacją, `expected` przy kopii |
| Izolacja (S-12) | E-7 | wyjątek w jednej subskrypcji |
| Q-08 | rozmiary ramek wg §5.12 (100 wierszy, 2000 celów, `episode_states` w partiach ≤ 100) | odpowiedzi nie zawierają list celów (D-22) |
| Koszt `state.json` po przeniesieniu subskrypcji | pomiar budżetu E2 w F3 (`e2-pobieranie.md:392`) | ten sam próg i metoda co E2 |
| Migracja nie zapisuje starego pliku | test bajtów pliku wersji 1–4 + SHA w teście na żywo F1 | `decode_subscriptions` bez zapisu |
| Migracja nie zmienia referencji konfliktu P | test porównawczy F1 + E2 P po migracji | potwierdzenia bez zmian (D-14) |
| H2 kontroluje właściwy plik | integracja E-1/E-3 na układzie stagingu E2 | rzeczywista ścieżka `staging_path` i prawdziwy `DefaultMediaProbe` |
| U-22 | E-14 + kodek mapowania 1:1 + 404 przez prawdziwy adapter | ten sam builder, to samo wejście; pusta odpowiedź nie nadpisuje zapisu |
| Brak martwych stanów odświeżania | edge cases §5.15 (konflikt → zgodny odczyt, awaria harmonogramu w przeglądzie) | termin naprawczy niezależny od prób |
| Paczka mieszana i pauza | E-13, E-9 | obie kolejności, stop w drodze, restart, obie fazy próby, brak innych rund, równoległe ręczne pobieranie |
| Autozamknięcie tylko po pobraniu | E-8 (a)–(f) | zlecenie bez pobrania nie zamyka; korekta liczby nie wyłącza celu |
| Automat nie przyjmuje `niepewnych` | E-4 + unit `eligible` | jedyna reguła dopuszczalności to `MATCH` |
| Q-01 | testy renderu bez I/O (istniejący wzorzec) | regresja kontraktu panelu |
| Brak regresji E2 | pełny pytest + istniejące testy integracyjne E2 | kontrakty E2 mają testy |
| UI zgodne z ux §8–§10 | PNG orkiestratora 120/50 kolumn + H3 | ocena wizualna |

Bramki przed każdym commitem (root `AGENTS.md`):

```text
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest -n auto
hooki pre-commit (check_test_comments, check_const_docstrings) i commit-msg
```

Wąsko w iteracji: `uv run pytest -o addopts="" -p no:cacheprovider <pliki>`. Flaky z §1:
jedno powtórzenie; drugi czerwony przebieg = finding.

## 9. Odbiór

### 9.1 H3 (właściciel, po F4)

```text
Uruchom: uv run anishift (po restarcie rezydenta zrobionym przez orkiestratora)
1. Subskrypcje → D → wyszukaj tytuł w emisji → S → Dodaj.
   Oczekiwane: szkic z „Od odc.”, notka o wyemitowanych; wpis na liście z odliczaniem;
   wyemitowane odcinki nie są zlecane.
2. Przejrzyj przeniesione stare subskrypcje.
   Oczekiwane: aktywne bez zaległych — aktywne; z zaległymi — wstrzymane i nic nie pobierają
   do W; po W pobierają tylko cele po dacie utworzenia; zakończone z brakami — wstrzymane z
   opisem; bez rozpoznanego sezonu — problem „Nie rozpoznano sezonu — usuń i dodaj ponownie”.
3. Delete na jednej, potem Ctrl+Z.
   Oczekiwane: znika bez pytania; wraca z tym samym zakresem; pliki na miejscu.
4. Nie dotykaj aplikacji 7 dni.
   Oczekiwane: nowe odcinki w Bibliotece z lektorem; zakończony sezon znika z listy
   i ma wpis w Historii.
Przekaż wynik jako: numer kroku, co zobaczyłeś, zgodne/niezgodne, uwaga.
```

PASS: wszystkie cztery kroki zgodne. Orkiestrator dołącza z rejestru: liczbę prób, przyjęć,
odrzuceń H2, eskalacji, opóźnienie emisja → pierwszy kandydat (mediana, P90) i rozmiar
`decisions.jsonl`.

### 9.2 Test migracji na kopii prywatnego stanu (orkiestrator, F1)

1. Rezydent zatrzymany (`uv run anishift watch stop`). Kopia `config/watch/state.json` i
   `config/subscriptions.json` do katalogu tymczasowego
   `C:\Users\MATTYM~1\AppData\Local\Temp\opencode\e3-migration\` (tylko orkiestrator, nie
   wykonawca). Oryginały nietknięte.
2. Uruchomienie samej migracji na kopii przez `WatchStateStore(path, subscriptions_path=...)
   .load()` w jednorazowym skrypcie `scripts/tmp/e3_migration_check.py` (gitignored). Skrypt
   wypisuje wyłącznie liczby: subskrypcje stare/nowe wg `pause_reason`/`problem`/
   `review_pending`, liczbę scalonych duplikatów sezonu (D-26), liczbę `legacy_orders`,
   SHA-256 zakodowanej sekcji `acquisitions` przed migracją i po niej (równe: potwierdzenia bez
   zmian, D-14), zgodność kopii `.bak` (SHA-256), SHA-256 kopii `subscriptions.json` przed i po
   (bez zmian) i brak zmiany bajtów przy drugim `load()`. Zgodność zakresów i referencji:
   ten sam skrypt uruchomiony na baseline `200de8a` wypisuje SHA-256 posortowanego zbioru
   (`anilist_id`, numer, referencje) z dzisiejszych `_legacy_scopes`/`_episode_conflicts`, a na
   nowym kodzie SHA-256 tego samego zbioru z `legacy_orders` i `_episode_conflicts`. Tylko skróty
   i liczby, bez tytułów i hashy.
3. PASS: liczby zgodne z oczekiwaniami z M-01–M-05; oba skróty `acquisitions` równe; oba skróty
   zakresów i referencji równe; zero błędów. Dopiero wtedy restart
   prawdziwego rezydenta (F1 test na żywo).

## 10. Ryzyka i reakcje

| Nr | Ryzyko | Jak rozpoznać | Reakcja | Eskalacja |
| --- | --- | --- | --- | --- |
| R-1 | `automation.py` (7608 linii) rośnie i miesza osie | diff ownera > ~800 linii netto | logika przejść tylko w `subscription_targets.py`; owner tylko zapis i wywołania; usunięcia §6.3 równoważą przyrost | gdy reguła przejścia musi powstać w ownerze — zatrzymaj, przeplanuj D-20 |
| R-2 | Zamykanie prób wymaga sygnałów, których E2 nie zapisuje trwale (np. zastój tylko w pamięci inspektora) | test E-3 nie da się napisać bez nowego pola | zapis powodu w istniejącym `problem` potwierdzenia, które owner już ustawia | nowe pole trwałe poza §5.2 → przeplanowanie schematu |
| R-3 | Brak sposobu wskazania katalogu `config/` na kopię | `anishift/paths.py` nie ma override | test migracji wyłącznie przez `WatchStateStore` z jawnymi ścieżkami (§9.2 pkt 2); bez uruchamiania rezydenta na kopii | — |
| R-4 | Cleanup nie usuwa nieopublikowanego zestawu odrzuconego przez H2 | test §5.7 czerwony | użyć istniejących warunków `clean_staging` (manifest + zwolnienie) | potrzeba nowej reguły usuwania plików → zatrzymaj (K-09, I-04) |
| R-5 | Opóźnienie indeksowania Torrentio dłuższe niż zakładane | rejestr `check` w H3 | brak zmiany w E3; raport dla właściciela | decyzja o źródle (U-02) |
| R-6 | Flaky testy maskują regresję | ten sam test czerwony dwa razy | traktuj jako finding | — |
| R-7 | Niezgodność kształtu IPC przy starym panelu i nowym rezydencie | panel pokazuje odmowę nieznanego polecenia | istniejący komunikat `ux.md:298`; restart obu | — |
| R-8 | Korekta AniList (mniej odcinków albo renumeracja) | cel z numerem > `episode_count` | cele stałe i nadal szukane; rekord się nie zamyka; konflikt widoczny w U07/U08 do rozliczenia przez użytkownika (D-23) | renumeracja obejmująca istniejące cele → K-06, problem |
| R-9 | Rozmiar `decisions.jsonl` | > 50 MB w H3 | stop i decyzja właściciela (D-16) | — |
| R-10 | Niezmiennik pauzy w `_save` zmienia zapis, którego wywołujący oczekuje w postaci dokładnie podanej (porównanie z `self._state`, receipt), albo tworzy stop w kółko dla transferu rozliczonego bez wysłania (`_settled_stop`) | istniejące testy pauzy E2 albo receipt czerwone; test E-13 „qB już zatrzymany” pokazuje kolejną akcję lub rundę | wywołujący porównują z `self._state` po zapisie, nie z kandydatem; niezmiennik nie dotyka pól poza `acquisitions` i `pause_owned_transfers`; stop tylko dla hasha spoza `pause_owned_transfers` (§5.6) | potrzeba wywoływania niezmiennika poza `_save` w więcej niż jednym miejscu → §10.2 |
| R-11 | Pełne mapowania ani.zip rozdymają `state.json` | pomiar F3 ponad próg | zapis tylko pól surowego odcinka czytanych przez `identity_target`, listę odcinków i H2, z zachowaniem kolejności i wszystkich odcinków, oraz test identyczności `identity_target` | dalej ponad próg → przeplanowanie (osobny plik wymaga decyzji, §10.2) |
| R-12 | Auto-przyjęcie tylko `zgodnych` daje za mało pobrań świeżych odcinków (O-9) | rejestr `check` w H3: odsetek należnych celów z samymi `niepewnymi` po 24 h | raport dla właściciela z liczbami; ścieżka ręczna działa | decyzja właściciela (P-4): zostaje albo osobny plan dopuszczalności `niepewnych` z nową regułą H1 według procedury `application/AGENTS.md` |

### 10.1 Dozwolone decyzje lokalne

Nazwy prywatnych helperów i stałych; dokładne kody `EpisodeReason` dla nowych stanów (z
testem pokrycia etykiet); rozbicie testów na pliki; dokładne teksty polskie poza cytowanymi w `ux.md`; sposób patchowania zegara zgodny z
istniejącym wzorcem testów ownera; kolejność kolumn U07 w ramach `ux.md`.

### 10.2 Zatrzymaj się i wróć po decyzję, gdy

- trzeba zapisać stan poza `WatchState` albo zapisać `subscriptions.json`;
- trzeba zmienić H1, golden lub ranking;
- `_admit_episode` wymaga zmiany semantyki dla `MANUAL`;
- usunięcie z §6.3 łamie test kontraktu, który nadal obowiązuje;
- schemat wymaga pola spoza §5.2;
- decyzji A (pauza globalna, D-30) albo B (D-04) nie da się wykonać bez zmiany kontraktu E2
  innego niż opisany w §5.5–§5.6;
- H2 na pliku w stagingu wymaga zmiany kolejności publikacji E2 innej niż wstawienie
  kontroli przed `_reserve_publication` i `expected` w `copy_staged`;
- pauza wymaga obserwacji albo rozliczania transferów automatu w pauzie (D-30) albo zmiany
  `TransferInspector` szerszej niż `held`;
- następnej próby (D-12) nie da się przyjąć bez zmiany `_admission_refusal` albo
  `protected_assignments`;
- zapisane mapowanie D-27 nie odtwarza `identity_target` identycznie albo budżet stanu jest
  przekroczony;
- test migracji na kopii daje liczby niezgodne z M-01–M-05.

Lokalny błąd zgodny z designem → poprawka w tej samej iteracji. Fałszywe założenie →
zatrzymanie dotkniętej części i przeplanowanie. Zmiana wymaganego zachowania → właściciel.

## 11. Pytania do właściciela (wykonanie nie czeka; domyślne w nawiasie)

| Nr | Pytanie | Rekomendacja i bezpieczna domyślna |
| --- | --- | --- |
| P-1 | Gdy wyłączysz automatykę (`O`), trwające pobrania subskrypcji stają, a po włączeniu ruszają dalej. Czas wyłączenia nie liczy się do limitów „brak postępu” i „brak listy plików”, więc pauza nie unieważnia próby. Pobranie, które dopiero czeka na listę plików, nie jest zatrzymywane, bo zatrzymanego w tej fazie nie da się bezpiecznie wznowić. Czy to akceptujesz? | tak (decyzja A v4, D-30) |
| P-2 | Uszkodzony `subscriptions.json` przy aktualizacji: zablokować start rezydenta z komunikatem, czy przenieść resztę stanu bez subskrypcji? | blokować (D-03); bez starego pliku ochrona przed ponownym zleceniem starych odcinków byłaby fałszywa, a już dziś taki plik blokuje D; naprawa = przywrócenie kopii |
| P-3 | Przeniesiona subskrypcja ze starym odcinkiem tylko „zleconym” (bez dowodu pobrania) nie zamknie się sama po sezonie (decyzja D). To samo dotyczy odcinka, którego AniList po korekcie już nie liczy. Zostaje na liście z opisem, aż pobierzesz ten odcinek ręcznie (D w U08) albo usuniesz subskrypcję. Czy to akceptujesz? | tak; to jedyna droga zgodna z U-11 („koniec bez pobrania nie jest sukcesem”) |
| P-4 | Subskrypcja pobiera sama tylko wydania ocenione jako zgodne. Jeśli dla odcinka są wyłącznie niepewne, czeka na zgodne, po 7 dniach powiadamia, a niepewne możesz pobrać ręcznie (D w szczegółach). Czy to akceptujesz zamiast automatycznego pobierania niepewnych po 72 h? | tak (O-9); 0 błędnych zgodnych na egzaminie, a reguła dla niepewnych nie miała pewnego źródła numeru; po H3 decyzja z liczbami z rejestru (R-12) |

## 12. Tabela pokrycia wymagań (`research/e3-wymagania.md`)

| ID | Gdzie | Uwagi |
| --- | --- | --- |
| S-01 | F2, §5.13 | D-05 |
| S-02 | wyłączone | usunięte w spec; `is_target` gwarantuje |
| S-03 | F1 (lista), F2 (odliczanie, stany) | `display_order` |
| S-04 | F2 | `D` w U07 |
| S-05 | F2 (U08, dodatki) | akcje D/W/F/X |
| S-06 | F2 | `subscription_check`, wynik 10 s |
| S-07 | F1 (pause), F3 (próba trwa) | E-9 |
| S-08 | F1 | D-15 |
| S-09 | F3 | §5.11 |
| S-10 | wyłączone | usunięte w spec |
| S-11 | F1 (wiersz), F3 (brak prób, transfery zatrzymane, zegary) | decyzja A v4, O-4, D-30, E-9, P-1 |
| S-12 | F2, F3 | E-7, `_subscriptions_problem` |
| S-13 | F2 | log + rejestr |
| S-14 | F3 | §5.10, E-2 |
| S-15 | F2 (cień stały), F3 (przełącznik) | §5.9, O-3 |
| M-01 | F1, F2 (przegląd) | D-18, D-26 |
| M-02 | F1 | D-14, D-26 |
| M-03 | F1, F2 | `migrated_missing` |
| M-04 | F1 | pomijane |
| M-05 | F1 | `season_unrecognized` |
| M-06 | F1 | istniejąca ścieżka legacy, regresja E2 |
| M-07 | F1 | `.e3-migration.bak` z tych samych bajtów, bez zapisu starego pliku, §5.14, §9.2 |
| U-01 | F2 | jedna droga tytuł → sezon → odcinki → S |
| U-02 | F2/F3 | tylko Torrentio; RSS Nyaa wyłączony (§3.2) |
| U-03 | F2 (wybór), F3 (próba) | D-10 (tylko `zgodne`, O-9), E-4 |
| U-04, U-05, U-23, U-24, U-25 | reuse | ranking `rank_candidates` bez zmian; U-24 dotyczy widoku „Inne wydania” (E2) |
| U-06 | F3 | `facts.supported` |
| U-07 | wyłączone (E4) | O-7 |
| U-08 | F3 (limit 3 prób) | lektor bez zmian; część o napisach — E4 |
| U-09 | F2 | `is_target`, `cut_point` D-28, U06 bez edycji |
| U-10 | F2 | `subscription_not_airing`; `S` na zapowiedzi (§5.13) |
| U-11 | F3 | `completed`, decyzja D, D-23, E-8 |
| U-12 | F1 | remove nie dotyka plików i transferów |
| U-13 | F2 | D-06 |
| U-14 | F2 | §5.5 |
| U-15 | F2 | `merge_listing` |
| U-16 | F1, F3 | `legacy_orders`, receipt |
| U-17, U-18 | reuse E2 | selekcja plików bez zmian |
| U-19 | F3 | §5.7, D-29 (wynik związany z `file_stamp`) |
| U-20 | F1, F2 | migracja przy pierwszym starcie; `migrated_due` po przeglądzie (D-18) |
| U-21 | wyłączone | filmy poza subskrypcją (spec §6.4 researchu) |
| U-22 | F2, F3 | decyzja C, D-27, E-14 |
| Q-01 | F1–F3 | render bez I/O |
| Q-02 | F2 | jedno odświeżenie i jedno Torrentio na cel |
| Q-03 | reuse | cache ani.zip w `AcquisitionService` |
| Q-04 | F2 | `RequestControl`, blokady dostawcy |
| Q-05 | F2 | stany oczekiwania; Esc w U01/U06 jak w Anime |
| Q-06 | F1–F3 | `sanitize_event_message`, polskie komunikaty |
| Q-07 | F2/F3 | `get_logger`, bez payloadów |
| Q-08 | F2, F3 | D-22, rozmiary ramek §5.12, budżet stanu |
| I-01 | F1 | D-01 |
| I-02 | F3 | stany celu ≠ stany przypisania; `satisfied` tylko po pobraniu (D-23); jedna projekcja |
| I-03 | F3 | receipt `sub:…:attempt`, `tried`, D-12 |
| I-04 | F3 | D-12, remove bez plików |
| I-05 | F2/F3 | termin tylko z harmonogramu; test restartu |
| I-06 | F1, F3 | §5.6, `legacy_orders` z referencjami (D-14) |
| I-07 | reuse E2 | bez zmian |
| I-08 | F3 | `SubscriptionTarget.reason` + rejestr |
| PR-01–PR-12 | regresja | pełny pytest; Biblioteka/Kosz/Historia bez zmian poza S-09 |
| Decyzja odłożona 1 (wczesna eskalacja H2) | D-08 | — |
| Decyzja odłożona 2 (P-1–P-10) | D-09 | strojenie poza E3 |
| Decyzja odłożona 3 (W-08) | O-8 | — |
| Decyzja odłożona 4 (G w UI) | zrobione w E2 (`cli/AGENTS.md`); E3 dodaje S/D | — |
| Decyzja odłożona 5 (retencja rejestru) | D-16 | — |
| Decyzja odłożona 6 (cień) | §5.9 | — |
| Decyzja odłożona 7 (port H2) | §5.7, O-2, D-29 | `tmp_path` w testach |
| Decyzja odłożona 8 (stany w ownerze) | §5.4, D-20 | — |
| Konflikty researchu §4.1–§4.6 | O-6; S-02 usunięte; D-05; D-06; U-08 limit 3 w subskrypcji (§5.4); W-g: automat nie przyjmuje `niepewnych` (O-9), więc nie ma auto-podmiany | — |

## 13. Definition of Done

- [ ] F1–F4 wykonane, każda z `astra` PASS, commitem i testem na żywo.
- [ ] Bramki repo PASS na ostatnim commicie.
- [ ] Test migracji na kopii (§9.2) PASS przed pierwszym restartem prawdziwego rezydenta.
- [ ] Zero zapisów do `subscriptions.json` w migracji i po niej (test bajtów wersji 1–4 + SHA w teście na żywo).
- [ ] Budżet stanu E2 (≤ 64 MiB, P95 `save()` ≤ 1 s) spełniony z subskrypcjami (F3).
- [ ] Decyzje orkiestratora A–D i F–I mają zielone scenariusze E-3, E-4, E-5, E-8, E-9, E-13, E-14, edge case „plik zmieniony po H2” i test porównawczy referencji F1.
- [ ] Zakazy §3.3 zachowane; usunięcia tylko z §6.3.
- [ ] `outcomes/e3.md` z dowodami; H3 przekazane właścicielowi.

## 14. Kontrakt wyniku wykonawcy (każda faza)

```text
status
finalny rezultat fazy
zmienione pliki
dowody (komendy i wyniki bramek, nazwy testów, PNG)
lokalne odchylenia (z §10.1)
materialne odkrycia (z §10.2)
znane ograniczenia
stan repo (bez commita — commituje orkiestrator)
rekomendowany następny krok
```

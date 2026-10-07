---
kind: plan
status: v18 zaakceptowany przez recenzenta astra (2026-10-06); oczekiwania K0 do potwierdzenia właściciela (historia: v8 zaakceptowany w rundzie 7; v9 = decyzje właściciela O-1..O-5 i „Pobierz teraz”; v10 = gwarancja sprawdzenia i stan PL celu; v11 = rozliczenie ze snapshotu i odświeżenie panelu; v12 = okresowe odświeżenie jednej strony; v13 = odczyt okna przy przewijaniu; v14 = okno usunięte, rewizja subskrypcji w `_status`; v14 zaakceptowany przez recenzentów astra i sol61 w rundzie 13 oraz przez właściciela 2026-10-06; v15 = wyniki K0 i decyzje W1–W3, O1–O9 z `a1-recon.md`, do review; v16 = numeracja wg decyzji D1–D3: most arm-server → AniDB, Kitsu mappings z kontrolą zwrotną, numeracja sprzeczna per odcinek, brak numeracji bez blokady automatu; v17 = poprawki review v16: numeracja per cel (`numbering_gap`), duplikat zachowuje najniższy odcinek, uzupełnienie i naprawa bez konfliktu katalogu, pominięcie pamięci ani.zip, kompletność Kitsu; v18 = `mapping_tvdb_season` w rekordzie (ocena zapisanego mapowania jego własnym sezonem mostu)); wykonanie po potwierdzeniu zestawu wzorcowego w K0
baseline: 9d82870 na work/acquisition/03-subscriptions
created: 2026-10-06
---

# Plan A1: algorytm pozyskiwania odcinka

## 1. Status, rezultat, authority

**Status:** v18 zaakceptowany przez recenzenta astra (2026-10-06); oczekiwania K0 do potwierdzenia właściciela. Kontraktem jest [algorithm-spec.md](../algorithm-spec.md) (dalej „spec A”). Plan
niczego w nim nie zmienia; luki i sprzeczności z kodem opisuje §11.

**Jeden rezultat:** AniShift szuka odcinka w pięciu źródłach (TsukiHime, Torrentio, Nyaa RSS,
Knaben, nekoBT), scala wyniki po hashu, pokazuje na liście kolumny **Jakość** i **Pewność**
i układa listę według spec A §6.1, a subskrypcja wybiera wydanie według spec A §6.2–§6.5
(tylko `zgodny` H1, klasy, próg celu, wydania oczekujące, czekanie na PL, weryfikacja po
metadanych), z powodem i powiadomieniem przy każdym niepowodzeniu (spec A §8). Reguła wyboru
zamiany R-07 jest czystą funkcją z punktem podpięcia dla wyzwalacza U-08, który dostarcza E4
(§5.12).

**Warunek sukcesu (spec A §1):**

1. Test offline zestawu wzorcowego (§9 planu) przechodzi: dla każdego przypadku zgodna trójka
   na górze listy i wybór automatu (albo jego brak z powodem) potwierdzone przez właściciela w K0.
2. Pokrycie nowej konfiguracji zapytań na 15 odcinkach badania 1 wynosi co najmniej 95% jego
   640 unikalnych hashy (jednostka i mianownik w §9.3).
3. Bramki repo zielone po każdym commicie: `uv run ruff check anishift/ tests/`,
   `uv run ruff format --check anishift/ tests/`, `uv run mypy anishift/ tests/`,
   `uv run mypy --platform linux anishift/ tests/`, `uv run pytest`.
4. Właściciel potwierdza na żywo w `uv run anishift` na wybranych tytułach (K16).

**Authority:** spec A ma pierwszeństwo przed `spec.md` i `plans/e1-przeplyw-subskrypcji.md`
w punktach spec A §10; reszta obu dokumentów obowiązuje. Bezpieczniki przepływu zostają:
wykluczenie wypróbowanych, ochrona plików innych celów, limit 3 prób, bramka przyjęcia
(`_admit_episode`, `automation.py:5187`), bramka rozliczenia poprzednika (`_replacement_ready`,
`automation.py:5883`), H2.

**Decyzje otwarte (spec A §12):** plan implementuje reguły obowiązujące. Każda decyzja ma jedno
miejsce w kodzie (§6.7 planu), więc zmiana decyzji to zmiana jednej stałej lub jednej funkcji.

## 2. Zasady wykonania

- Pętla na krok: autor koduje i testuje → przegląd innym modelem (inna rodzina) → poprawki →
  weryfikacja recenzenta → pełny `uv run pytest` → commit → restart rezydenta → kontrola na żywo,
  jeśli krok ją ma.
- Branch: `work/acquisition/04-algorithm` od HEAD `work/acquisition/03-subscriptions` (K0).
  Commity `typ(scope): opis`, scope z `scripts/hooks/check_commit_msg.py`.
- Każdy commit zostawia działające zachowanie: zmiana typu idzie w jednym commicie ze wszystkimi
  konsumentami; nowa ścieżka zastępuje starą dopiero w kroku, który ją w całości przełącza (§7).
- Reuse przed nowym kodem (lista z miejscami w §5). Nie powstaje drugi parser nazw, drugi
  limiter żądań, drugi rejestr decyzji, druga bramka przyjęcia ani drugi kanał zdarzeń.
- Moduły czyste (`release_quality`, `episode_confidence`, `episode_releases`,
  `subscription_choice`) dopisywane są do `_PURE_MODULES` w `tests/application/test_architecture.py`;
  nie importują `anishift.services`, `httpx`, `os`.
- Zależności: żadnych nowych. httpx, pydantic i stdlib (`xml.etree`, `math`, `base64`,
  `concurrent.futures`) wystarczą.
- Diagnostyka: `logger = get_logger(__name__)`; logowane są granice odczytu źródła (źródło,
  wynik, liczba wyników, czas), wycofanie źródła, zatrzymanie po metadanych.
  Bez URL-i z frazą, pełnych nazw wydań i ścieżek absolutnych.

## 3. Mapa spec → kod → test

Skróty: `app/` = `anishift/application/`, `svc/` = `anishift/services/torrents/`,
`cli/` = `anishift/cli/interactive/`, `t/app/` = `tests/application/`. Kolumna „Krok” wskazuje
krok z §7.

### 3.1 Sekcje §2–§9

| Spec A | Reguła | Kod (plik → symbol) | Test | Krok |
| --- | --- | --- | --- | --- |
| §2 Wydanie | klucz BTIH 40 hex, base32 → hex | `app/episode_releases.py` → `info_hash_hex` | `t/app/test_episode_releases.py::test_info_hash_hex_*` (hex, base32, wielkie litery, zły tekst) | K1 |
| §2 Plik odcinka | ścieżka w torrencie; `fileIdx` tylko podpowiedź; pola H1 Torrentio bez utraty | `app/episode_releases.py` → `ReleaseFile(path, filename, size, from_listing, file_index)`, `identity_candidate`, `EpisodeRelease.files`; `app/transfers.py` → `episode_files` (:360) | `test_episode_releases.py::test_merge_releases_file_from_listing_wins`, `::test_torrentio_file_keeps_filename_and_path`; `test_episode_selection.py::test_rank_torrentio_equivalent_to_conf_model`; istniejące testy `episode_files` | K5, K6, K13 |
| §2 Kandydat | para (wydanie, plik), H1 względem celu | `app/episode_selection.py` → `RankedCandidate` | `t/app/test_episode_selection.py` | K6 |
| §2 Spis plików | TsukiHime `/torrents/{id}` lub qBittorrent; rekord Torrentio = jeden plik | `svc/tsukihime.py` → `TsukiHimeSource.torrent_files` → `TsukiHimeListing`; `app/episode_releases.py` → `EpisodeRelease.listing` | `tests/services/torrents/test_tsukihime.py`; `test_episode_releases.py::test_merge_releases_torrentio_file_is_not_listing` | K8, K5 |
| §2 Paczka | >1 plik wideo odcinków wg spisu; bez spisu zakres w nazwie / `is_pack`; towarzyszące nie liczą się | `app/episode_releases.py` → `is_pack` (używa `VIDEO_EXTENSIONS` z `episode_identity.py:35` i `pack_name` wstrzykniętego z `ReleaseName.is_pack`, `svc/types.py:38`) | `test_episode_releases.py::test_is_pack_*` (spis z `.mka`/`.ass`, `E01-E04`, `Batch`, spis wygrywa z nazwą); `tests/services/torrents/test_names.py::test_season_only_before_quality_block_is_pack` (`[ZigZag] … S01 [1080p …]`, Breeze; O8) | K5 |
| §2 Konflikt | zamknięta lista powodów H1 (19 powodów `INSUFFICIENT` + każdy `MISMATCH`) | `app/episode_identity.py` → `CONFLICT_REASONS` (§5.3), `is_conflict`, `conflict_label` | `t/app/test_episode_identity.py::test_conflict_reasons_subset_of_reasons`, `::test_every_mismatch_is_conflict`, `::test_insufficient_conflict_cases`, `::test_conflict_label_for_every_reason`, `::test_classify_dual_before_release_group_is_technical_metadata` (154587-28), `::test_classify_mapped_absolute_number_stays_ambiguous` (O7 wycofane — 154587-1 i 140960-12 zostają niepewne); `test_episode_search.py::test_unresolved_season_stays_in_completion_queue` | K2, K9 |
| §2 Pewność / Jakość | estymata modelu / punkty cech | `app/episode_confidence.py` → `confidence`; `app/release_quality.py` → `quality_score` | `test_episode_confidence.py`, `test_release_quality.py` | K3, K4 |
| §2 Użyteczny | nie paczka, nie niejednoznaczny, nie sam dubbing, bez RAW/HardSub, kontener, plik nieprzyjęty | `app/subscription_choice.py` → `usable` | `t/app/test_subscription_choice.py::test_usable_*` (po jednym na warunek) | K12 |
| §2 Dopuszczalny | §6.2 | `app/subscription_choice.py` → `admissible` | `test_subscription_choice.py::test_admissible_*` | K12 |
| §3.1 tabela, TsukiHime | AniList → id → `/episodes/{n}`, `limit=100`, ≤2 strony | `svc/tsukihime.py` → `anime_id`, `episode_page`; `app/episode_search.py` → `_tsukihime_answer` | `test_tsukihime.py::test_episode_page_*` (stronicowanie, `total`, 404 = brak tytułu) | K8, K9 |
| §3.1 Torrentio | `kitsu:{id}:{n}`; film `movie_streams` | `svc/torrentio.py` (`streams` :37, `movie_streams` :41) przez protokół `StreamSource` (`app/acquisition.py:195`); adaptacja w `app/episode_search.py` → `_torrentio_answer` | `tests/services/torrents/test_torrentio.py`; `test_episode_search.py::test_torrentio_answer_movie_and_series` | K8, K9 |
| §3.1 Nyaa RSS | frazy jak `search_title` (romaji, angielski), obie kategorie, każda osobnym wywołaniem | istniejące `TorrentSource` (`app/acquisition.py:159`, `NyaaSource` w `bootstrap.py:110–115`); `app/episode_search.py` → `_nyaa_answer`, `_release_stream` (jedyna konwersja `Release` → `StreamCandidate`) | `test_episode_search.py::test_nyaa_queries_both_categories`, `::test_release_stream_fields` | K9 |
| §3.1 Knaben | te same frazy, ≤2 strony × 300; GET `/v2/search`, hash małymi literami (O1) | `svc/knaben.py` → `KnabenSource.search` (`PagedSource`) | `tests/services/torrents/test_knaben.py` (w tym `::test_search_get_params_as_recorded`, `::test_hash_lowercased`) | K8 |
| §3.1 nekoBT | te same frazy, ≤2 strony × 100; blok `{Tags:…}`: `A=`, `F=`, `S=`, flagi bez `=` (`HS`), sklejone kody regionalne → język podstawowy, F∪S (O5) | `svc/nekobt.py` → `NekoBTSource.search`, `parse_feed`, `language_tags` | `tests/services/torrents/test_nekobt.py` (w tym `::test_language_tags_regional_codes`, `::test_language_tags_flags`) | K8 |
| §3.1 budżet TsukiHime | ≤2+2 strony + 10 uzupełnień = ≤14; ID tytułu zapamiętane | `app/episode_search.py` → `EpisodeSearch.subscription_check`; `SubscriptionRecord.tsukihime_id` | `test_episode_search.py::test_subscription_check_tsukihime_budget_14`; `test_watch_state.py::test_tsukihime_id_roundtrip` | K11, K12 |
| §3.1 lista przerwana | celu = niedokończone; poprzedniego: PL na stronach = „PL jest”, inaczej błąd odczytu | `app/episode_search.py` → `previous_history`; `app/subscription_choice.py` → `polish_history` | `test_episode_search.py::test_previous_history_truncated_*` (z PL, bez PL) | K14 |
| §3.1 Torrentio 1 żądanie, Nyaa ≤4 frazy ≤8 żądań | frazy `"{tytuł} - {NN}"`, `"{tytuł} S{ss}E{NN}"` (TV także `S01E{NN}` w sezonie 1, W1), OVA/SPECIAL bez `S{ss}E{NN}` i z pełnym podtytułem (W2), bez absolutnego w subskrypcji; frazy wspólne dla Nyaa, Knaben, nekoBT | `app/episode_search.py` → `episode_phrases(candidate, context, number, *, manual, absolute)` (z `base_title`, `svc/names.py:157`, poza OVA/SPECIAL; `{ss}` z już pobranego grafu franczyzy regułą `season_context`, `app/acquisition.py:593`, bez zapytań AniList — O6, `a1-recon.md` N-5) | `test_episode_search.py::test_episode_phrases_*` (sezon 1 TV z `S01E{NN}`, sezon 2, cour, OVA/SPECIAL z podtytułem bez `S{ss}E`, ręczne z absolutnym, ≤4, bez duplikatów), `::test_season_index_from_graph_no_anilist_requests` | K9 |
| §3.1 Knaben/nekoBT ≤8 żądań, raz na 60 min | odczyt co 60 min na cel w subskrypcji | `app/episode_search.py` → `_PulledCache` | `test_episode_search.py::test_pulled_source_read_once_per_hour` | K12 |
| §3.1 P-10 per źródło, ostatni wynik ≤30 min | seria 429 rzednie źródło do 30 min; pominięte szybkie źródło = ostatni wynik z pamięci ≤30 min; pominięcie ≠ niepowodzenie | `app/episode_search.py` → `_FastCache`, `SourceState.SKIPPED`; P-10 z `RequestControl.blocked_until` (`anishift/services/http_requests.py:91`) | `test_episode_search.py::test_skipped_fast_source_uses_last_result_30_min`, `::test_skipped_source_not_counted_as_failure`; `test_subscription_choice.py::test_pending_skipped_does_not_increment` | K12 |
| §3.1 format | `MOVIE` → `/episodes/1`, `movie_streams`, fraza bez numeru; inne formaty jak serial | `app/episode_search.py` → `episode_phrases`, `EpisodeRequest.movie` | `test_episode_search.py::test_movie_*`; przypadek filmowy w `test_acquisition_reference.py` | K9, K16 |
| §3.1 przełączniki | domyślnie wszystkie włączone; wyłączone nie jest odpytywane (też spisy i historia PL) | `anishift/config/user_settings.py` → `UserSettings.source_*`; `app/episode_search.py` → `SourceSwitches` | `tests/config/test_user_settings.py::test_sources_default_all_enabled`; `tests/config/test_field_catalog.py::test_acquisition_specs_are_persisted_fields`; `t/app/test_automation.py::test_source_switch_through_settings_api_reaches_owner`; `test_episode_search.py::test_disabled_tsukihime_no_listing_no_history` | K9, K14 |
| §3.1 źródło niewidoczne na liście | brak kolumny źródła | `cli/anime.py` (wiersze ofert) | `tests/cli/test_anime_episodes.py::test_offer_row_has_no_source_column` | K10 |
| §3.1 RequestControl per dostawca | własny identyfikator hosta | `anishift/services/http_requests.py` → `_provider` (:194) | `tests/services/test_http_requests.py::test_provider_*` | K7 |
| §3.1 odrzucone źródła | AnimeTosho itd. nie istnieją w kodzie | brak kodu | `tests/config/test_bootstrap.py::test_acquisition_sources_are_exactly_five` | K9 |
| §3.2 limit 30 s | z perspektywy wywołującego: łącznie z limitami, oczekiwaniem na wspólny odczyt i stronicowaniem; po limicie wyniki dotychczasowe | `http_requests.py` → `_Operation.deadline` (zegar monotoniczny), sprawdzenie przed żądaniem, `future.result(timeout=remaining)` każdego wywołującego, wewnętrzna pula z `copy_context().run`, `DeadlineExceeded`; `app/episode_search.py` → `SourceResult(state=UNFINISHED, failure=TIMEOUT, streams=…)` | `test_http_requests.py::test_deadline_caller_times_out_while_transport_hangs`, `::test_deadline_follower_shorter_ends_alone`, `::test_follower_joins_after_leader_timeout`, `::test_budget_through_both_pools`; `test_episode_search.py::test_source_timeout_keeps_partial` | K7, K9 |
| §3.2 lista na bieżąco, 3 s, „szukam jeszcze”, wybór w trakcie | wiersze w miarę odpowiedzi; po 3 s lista (także bez wierszy) z „szukam jeszcze: …”; kursor i zaznaczenia po hashu; wybór przed końcem wyszukiwania weryfikowany na rewizji ownera | §5.10: `episode_offer_start` (krótkie, praca w `_active_io`) → `EpisodeSearch.manual_offer(on_partial)` + snapshot po `FIRST_SNAPSHOT_S` → `AutomationOwner._store_partial_offer` (rewizje) → zdarzenie `episode_offer_partial` (sygnał) → `platform/local_control.py` `_event_key` (:821) → `cli/interactive/state.py` `_forward_anime` (:1016) → `cli/anime.py` → `episode_offer_get`; `episode_choose(offer_id, revision, info_hash, path)` | `test_episode_search.py::test_manual_offer_partial_after_first_source`, `::test_manual_offer_snapshot_at_3s_without_results`; `t/app/test_automation.py::test_offer_start_returns_before_search`, `::test_offer_get_searching_then_ready`, `::test_offer_failure_before_first_snapshot`, `::test_offer_failure_after_partial`, `::test_choose_refused_when_assessment_changed_since_revision`, `::test_shutdown_with_blocked_source_and_late_429`; `tests/platform/test_local_control.py::test_offer_partial_events_coalesce_per_offer`; `tests/cli/test_anime_episodes.py::test_choose_during_search_before_slow_source`, `::test_final_event_before_start_response`, `::test_final_revision_without_new_candidates`, `::test_offer_after_3s_pending_line_without_rows`, `::test_partial_offer_keeps_cursor_on_hash`; `tests/cli/test_interactive_state.py::test_observe_loss_keeps_open_offer`, `::test_catalog_session_closed_expires_offer` | K9, K10b |
| §3.2 `D` bez podglądu i subskrypcja | decyzja po wszystkich źródłach i uzupełnieniach | `app/automation.py` → `_episode_download` (:5020) na `AcquisitionService.search_episode`; subskrypcja na `subscription_check` | `t/app/test_automation.py::test_episode_download_waits_for_all_sources` | K9, K12 |
| §3.2 dociągane | ostatni udany wynik między odczytami; błąd zachowuje; wyłączenie i restart usuwają; brak udanego = niedokończone | `app/episode_search.py` → `_PulledCache` | `test_episode_search.py::test_pulled_*` (cztery przypadki) | K12 |
| §3.3 jeden hash = jeden wiersz | scalanie | `app/episode_releases.py` → `merge_releases` | `test_episode_releases.py::test_merge_releases_same_hash_one_row` | K5 |
| §3.3 nazwa | TsukiHime → Nyaa → nekoBT → Knaben → Torrentio | `merge_releases` → `NAME_PRIORITY` | `::test_merge_releases_name_priority` | K5 |
| §3.3 seedy | max ze źródeł; brak → `None` („?”) | `merge_releases` | `::test_merge_releases_seeders_max_or_unknown` | K5 |
| §3.3 RAW/HardSub | z nazw i tagów wszystkich źródeł; `HS` nekoBT | `app/release_quality.py` → `release_traits` (pola `raw`, `hardsub`) | `test_release_quality.py::test_hardsub_from_nekobt_tag_wins` (przypadek wzorcowy) | K4 |
| §3.3 sam dubbing | pełna lista audio wg §5.2; znaczniki dubbingu (lista zamknięta); `Dual-Audio`/`Multi-Audio` bez pełnej listy | `release_quality.py` → `dub_only`, `DUB_MARKERS`, `DUBBED_RE` (przeniesione z `svc/names.py:90`) | `test_release_quality.py::test_dub_only_*` — pięć przypadków wzorcowych z §3.3 | K4 |
| §3.3 paczka | spis wygrywa z nazwą; bez spisu dowolne źródło | `episode_releases.py` → `is_pack` | `::test_is_pack_listing_wins`, `::test_is_pack_any_source_name` | K5 |
| §3.3 ten sam plik z dwóch źródeł | ścieżka ze spisu; nazwa Torrentio łączona, gdy dokładnie jedna | `merge_releases` → `_attach_torrentio_file` (przenosi też deklarację `TORRENTIO_FLAG` na dopasowany plik) | `::test_merge_releases_torrentio_name_joined_once`, `::test_merge_releases_torrentio_name_ambiguous_kept_alone`, `::test_torrentio_flag_follows_matched_listing_file` | K5 |
| §3.4 pewność na pliku; „bez nazwy pliku” | ocena na pliku; inaczej na nazwie wydania | `app/episode_selection.py` → `rank_candidates` | `test_episode_selection.py::test_rank_without_file_name_marks_release_only` | K6 |
| §3.4 ocena nazwy wydania | osobna funkcja H1, bez rozszerzenia | `app/episode_identity.py` → `classify_release_name` | `test_episode_identity.py::test_classify_release_name_match`, `::_other_season`, `::_other_episode`, `::_unresolved` | K2 |
| §3.4 spis z TsukiHime | ID z listy albo wyszukanie po hashu, potem spis w tej samej wizycie; btih `200` z kompletnym `files` (`len(files) == filecount`) = spis bez drugiego GET, krótsze → `/torrents/{id}`, tam też krótsze → brak spisu (O2), btih `202` = `PENDING`, ID zachowane (O3); wynik rozróżnia sukces, pustą listę, brak hasha, `202`, `429`, błąd, limit czasu | `svc/tsukihime.py` → `torrent_by_hash`, `torrent_files`; `app/episode_search.py` → `ReadOutcome`, `_listing_read`, `failure_kind` | `test_tsukihime.py::test_torrent_by_hash_*` (w tym `::test_torrent_by_hash_200_files_is_listing`, `::test_btih_partial_files_reads_torrent`, `::test_torrent_files_partial_is_not_listing`, `::test_torrent_by_hash_202_files_not_listing`), `::test_torrent_files_*`, `::test_episode_page_offset_param_start_field`; `test_episode_search.py::test_source_outcome_end_to_end` (od odpowiedzi/wyjątku do `SubscriptionTarget.failures`) | K8, K9, K12 |
| §3.4 kolejka uzupełnień | kolejność, ≤10 odczytów, jedna wizyta, ponowienie w następnym, przeliczanie | `app/episode_search.py` → `CompletionQueue(order)`; lista: `episode_selection.list_order` (K9), subskrypcja: `subscription_choice.completion_order` (K12) | `test_episode_search.py::test_completion_queue_*` (budżet 10, wizyta = 2 odczyty, retry za nieodwiedzonymi, przeliczanie); `::test_completion_queue_restart_keeps_blocking_first` | K9, K12 |
| §3.4 pamięć spisów | tylko udane, niepuste, kompletne | `episode_search.py` → `_ListingCache` | `::test_listing_cache_skips_empty_and_202`, `::test_listing_cache_skips_partial` | K9 |
| §3.4 reprezentant | `zgodny` → `niepewny` → konflikt, pewność, ścieżka | `episode_selection.py` → `representative` | `test_episode_selection.py::test_representative_*` | K6 |
| §3.4 niejednoznaczny plik | >1 `zgodny`; ręcznie U-18c; automat nie | `episode_selection.py` → `RankedCandidate.ambiguous`; `subscription_choice.usable`; ścieżka ręczna po metadanych: `transfers.episode_files` (:360, zgodne pliki przed skrótem po nazwie) | `::test_rank_two_matching_files_ambiguous`; `test_subscription_choice.py::test_usable_rejects_ambiguous`; `test_transfers.py::test_episode_files_two_matches_ambiguous`; `test_automation.py::test_manual_ambiguous_file_waits_for_u18c` | K6, K12, K13 |
| §3.4 ponowne H1 po metadanych | pełna ścieżka qBittorrenta, ponownie §6.2 | `app/transfers.py` → `metadata_check`; `app/automation.py` → `_settle_selection` (:5717) | `t/app/test_transfers.py::test_metadata_check_*`; `test_subscription_attempts.py::test_after_metadata_*` | K13 |
| §3.5 błędy źródeł | wiersz stanu; pozostałe działają; nie zużywa próby; przyczyna (limit czasu, limit dostawcy, błąd) przez rzeczywiste adaptery; wyniki częściowe zachowane | `episode_search.py` → `SourceResult(state, failure)`, `failure_kind`, `source_line`; `automation.py` → `_subscription_outcome` (:3855), `_subscription_failure` (:3790) | `test_episode_search.py::test_source_line_*`, `::test_source_outcome_end_to_end` (w tym timeout 2. kategorii Nyaa); `test_subscription_attempts.py::test_source_failure_does_not_consume_attempt` | K9, K12 |
| §3.5 wszystkie zawiodły / wyłączone | dwa osobne komunikaty | `episode_search.py` → `offer_status` | `::test_offer_status_all_failed`, `::test_offer_status_all_disabled` | K9 |
| §3.5 pusta odpowiedź | brak kandydatów, nie błąd | adaptery zwracają `()` | testy adapterów `::test_*_empty_is_not_error` | K8 |
| §3.5 numeracja a Torrentio (U-22) | mapowanie bez Kitsu; brak Kitsu wyłącza tylko Torrentio; zmiana numeracji zapisanych odcinków = konflikt katalogu niezależnie od Kitsu (`subscription_targets.merge_listing`, `test_numbering_change_*`, K11); zmiana numeracji odcinka, który ją miał = konflikt; uzupełnienie z braku i naprawa sprzecznej nie (`test_numbering_filled_*`, `test_duplicate_repaired_not_conflict`); cel bez numeracji (`numbering_gap`, §5.5) lista bez sugestii z "brak numeracji" | `app/subscription_targets.py` → `SubscriptionRecord.__post_init__` (:220-222); `app/acquisition.py` → `read_listing` (:777, pusty `AniZipMapping` zamiast wyjątku, `ListingRead.tvdb_season`), `search_episode`; `automation.py` oferta (:4871-4878), `D` (:5135-5140); `episode_search.py` → `SourceState.NO_KITSU`, `EpisodeRequest.numbering` | `t/app/test_subscription_targets.py::test_record_mapping_without_kitsu`; `t/app/test_acquisition.py::test_read_listing_live_without_kitsu`, `::test_read_listing_404_does_not_replace_saved_mapping`; `t/app/test_automation.py::test_offer_without_numbering_shows_releases`, `::test_d_without_numbering_does_not_admit`, `::test_repeat_without_numbering_has_no_suggestion` (pięć przypadków §5.9) | K9, K9b, K11 |
| §3.5 źródła numeracji i ID (D1), §3.1 budżet | arm-server przy każdym odczycie listy (AniDB ID, `thetvdb-season`); puste `episodes` → ani.zip po `anidb_id`; brak Kitsu → Kitsu mappings z kontrolą zwrotną (oba odczyty kompletne, `page[limit]=20`, bez `links.next`); `null` nie nadpisuje znanego ID; błąd mostu odbiera tylko jego część; najwyżej 5 żądań | `services/catalog/arm.py` → `ArmCatalog.ids`; `services/catalog/kitsu.py` → `KitsuCatalog.kitsu_id`; `services/catalog/anizip.py` → `AniZipCatalog.mapping_by_anidb`; `app/acquisition.py` → `_bridged_mapping`, `read_listing` (:777) | `t/services/catalog/test_arm.py::test_ids_reads_anidb_and_tvdb_season`; `t/services/catalog/test_kitsu.py::test_kitsu_from_mappings_with_reverse_check`, `::test_kitsu_candidate_with_next_link_is_unresolved`, `::test_kitsu_incomplete_reverse_is_unresolved`, `::test_kitsu_ambiguous_is_unresolved`, `::test_kitsu_request_count`; `t/services/catalog/test_anizip.py::test_mapping_by_anidb`; `t/app/test_acquisition.py::test_numbering_falls_back_to_anidb`, `::test_anidb_nulls_do_not_overwrite_ids`, `::test_bridge_failure_keeps_anilist_mapping`, `::test_listing_bridge_requests_within_budget` | K9b |
| §3.5 numeracja celu i sprzeczna | numeracja tylko przy kluczu celu z S/E; S/E niższego lokalnego odcinka (najniższy zachowuje) albo sezon ≠ `thetvdb-season` → odcinek bez numeracji; jedna reguła dla H1, listy, ponowienia, `D`, subskrypcji; powód w rejestrze | `app/episode_selection.py` → `numbering_gap`; `ListingRead.tvdb_season`; `acquisition_decisions._FIELDS` → `numbering` | `t/app/test_episode_selection.py::test_numbering_gap_missing_key`, `::test_numbering_gap_without_season_episode`, `::test_numbering_gap_duplicate_keeps_lowest`, `::test_numbering_gap_tvdb_season`; `t/app/test_acquisition_decisions.py::test_numbering_field` | K9b, K15 |
| §3.5 bez numeracji (D2) | cel bez S/E, absolutu i tytułu; `zgodny` tylko z tytułu wpisu i numeru lokalnego; samo `SxxExx` → `niepewny` bez konfliktu; automat decyduje jak zwykle | `episode_selection.identity_target(..., numbering)`; `episode_identity._identity_conflict` (:635-640) nowy powód spoza `CONFLICT_REASONS`; bez `Blocker.NO_NUMBERING` | `t/app/test_episode_identity.py::test_entry_title_local_number_without_numbering`, `::test_sxxexx_without_numbering_stays_uncertain`; `test_subscription_owner.py::test_no_numbering_decides_on_entry_title` | K2, K9b, K12 |
| §3.5 odświeżanie (D3) | numeracja czytana przy każdym sprawdzeniu, bez pamięci w ownerze; cel bez numeracji pomija pamięć `max_age_s` ani.zip | `read_listing` w każdym sprawdzeniu subskrypcji | `test_subscription_owner.py::test_numbering_appears_on_next_check`; `t/app/test_acquisition.py::test_subscription_read_bypasses_mapping_cache` (puste i sprzeczne) | K9b, K12 |
| §4 model | współczynniki bez zmian | `app/episode_confidence.py` → `_WEIGHTS`, `_PLATT_*`, `confidence` | `test_episode_confidence.py::test_model_matches_research_json` | K3 |
| §4 projekcja dowodów | jedna publiczna funkcja H1 na kontrakcie kandydata H1 (`release`, `path`, `filename`), semantyka `conf_model.py:16–88` | `episode_identity.py` → `identity_evidence(target, candidate)` | `test_episode_confidence.py::test_features_match_research_cases`, `::test_features_filename_differs_from_path`, `::test_features_path_without_filename`, `::test_features_release_only` | K3 |
| §4 konflikt zamiast % | krótki powód; szczegóły z numerami | `episode_identity.py` → `conflict_label`; `cli/anime.py` → `_candidate_details` (:2411) | `test_episode_identity.py::test_conflict_label_*`; `tests/cli/test_anime_episodes.py::test_conflict_row_shows_reason` | K2, K10 |
| §4 kalibracja tylko E1 | informacja w szczegółach | `cli/anime.py` → `_candidate_details` | `test_anime_episodes.py::test_details_confidence_uncalibrated_note` | K10 |
| §4 tylko lista i sugestia | automat nie czyta `confidence` | `ChoiceCandidate` bez pola pewności | `test_subscription_choice.py::test_choose_ignores_confidence`; test architektury | K12 |
| §5.1 punkty | tabela, max(0, suma), 0–90, seedy log | `release_quality.py` → `quality_score`, `seed_points` | `test_release_quality.py::test_quality_points_*`, `::test_seed_points_*` (0, 5 ≈ 4,6, 50, 400, `None` = 5) | K4 |
| §5.2 zakres deklaracji | deklaracje pliku (TsukiHime per plik, nazwa pliku, flaga Torrentio) przed deklaracjami wydania; paczka → deklaracje wydania nieustalone | `release_quality.py` → `LanguageDeclaration.file`, `release_traits(file=…)`; `episode_releases.py` → `ReleaseFile.declarations` | `test_release_quality.py::test_pack_release_languages_ignored`, `::test_file_declaration_beats_release`; `test_episode_selection.py::test_two_files_different_languages_traits_follow_representative` | K4, K5, K6 |
| §5.2 normalizacja kodów | bez wielkości liter, język podstawowy | `release_quality.py` → `language_code` | `::test_language_code_regional` (`pl-PL`, `ja-JP`, `zh-Hant`) | K1 |
| §5.2 puste deklaracje | brak / `[]` = brak danych; niepusta bez języka = brak | `release_quality.py` → `_declared` | `::test_empty_list_does_not_override_lower` | K4 |
| §5.2 napisy nekoBT | `F=` ∪ `S=` | `release_quality.py` (deklaracja `NEKOBT`) | `::test_nekobt_fansub_pl_with_official_without_pl` (przypadek wzorcowy) | K4 |
| §5.2 pierwszeństwo | TsukiHime → nekoBT → plik → wydanie | `release_quality.py` → `DECLARATION_PRIORITY` | `::test_higher_declaration_wins_*` | K4 |
| §5.2 PL / PL audio / PL bez roli / EN / rozdzielczość, platforma, Blu-ray | tokeny i pola | `release_quality.py` → `_PL_SUB_RE`, `_PL_AUDIO_RE`, `_PL_BARE_RE`, `_EN_SUB_RE`, `_PLATFORM_RE`, `_BLURAY_RE` | po jednym teście na regułę, w tym `MultiSub` ≠ PL | K4 |
| §5.2 oryginalne audio | `ja`; `zh` tylko przy `countryOfOrigin = CN`; `ko` akceptowalne | `services/catalog/anilist.py` → pole `countryOfOrigin` w zapytaniach (:61, `_FRANCHISE_FIELDS` :101) i `_candidate` (:370); `services/catalog/types.py` → `TitleCandidate.country` (:62); `episode_search.py` → `EpisodeRequest.donghua`; `release_quality.py` → `original_audio` | `tests/services/catalog/test_anilist.py::test_candidate_country_of_origin`; `test_release_quality.py::test_donghua_zh_is_original`, `::test_japanese_title_zh_not_original`; `test_episode_search.py::test_request_donghua_from_country` | K1, K4, K9 |
| §5.3 klasy | rozdzielczość (U-05), PL, audio | `release_quality.py` → `resolution_class`, `polish_class`, `audio_class`, `class_key` | `::test_resolution_class_order`, `::test_polish_class_order`, `::test_audio_class_order` | K4 |
| §5.3 720p ukryte; sam dubbing na końcu; kontener wykluczony | U-24, U-23, U-06 | `episode_selection.py` → `list_order`, `visible`; istniejące `_container` | `test_episode_selection.py::test_low_resolution_hidden_with_matching_1080`, `::test_dub_only_after_regular`, istniejące testy kontenera | K6 |
| §5.4 kontrola wag | F > A > C > E > B ≈ D | `release_quality.py` | `test_release_quality.py::test_owner_order_f_a_c_e_b_d`; `test_subscription_choice.py::test_choose_owner_order`; `test_episode_selection.py::test_list_owner_order_equal_confidence` | K4, K6, K12 |
| §6.1 kolejność listy | klucz w trzech grupach | `episode_selection.py` → `list_order` | `::test_list_order_*` | K6 |
| §6.1 kolumny | Jakość, Pewność na końcu, pełna nazwa | `cli/anime_state.py` → `AnimeRow` (:57); `cli/anime_view.py` → `_spec` (:301), `_values` (:332) | `tests/cli/test_anime_view.py::test_offer_columns_quality_confidence_last` | K10 |
| §6.1 sugestia (O-5) | pierwszy wiersz grupy 1; gdy nie `zgodny` — „niepewne”; `D` bez podglądu pobiera sugestię | `episode_selection.py` → `suggestion` (:448); `automation.py` → `_admit_download_offer` (:5162–5168, bez zmian reguł) | `::test_suggestion_is_first_group_one_row`, `::test_suggestion_marks_uncertain`, `::test_suggestion_skips_conflict_and_dub_only`, `::test_suggestion_none_when_group_one_empty`; `test_automation.py::test_d_takes_uncertain_first_row` | K6 |
| §6.1 potwierdzenia R-04 | bez zmian | istniejące w `cli/anime.py` i `automation.py` (:4997) | istniejące testy w `tests/cli/test_anime_episodes.py` (bez zmian zachowania) | K10 |
| §6.2 warunki | `zgodny` na pliku / „do weryfikacji po metadanych”; użyteczny; zero seedów; wykluczone; próg; oczekujące | `subscription_choice.py` → `admissible`, `decide`; wywołanie w `automation.py` → `_subscription_outcome` (:3855, zamiast `eligible` :3869–3871) | `test_subscription_choice.py::test_admissible_*`, `::test_zero_seeds_*` (zastąpione w tej samej klasie; nigdy zejście niżej) | K12 |
| §6.2 wydanie oczekujące | blokada, wygaśnięcie (spis, rozstrzygające, 3 przejściowe w 3 sprawdzeniach), +1 na sprawdzenie, TsukiHime niedostępne = wszystkie, trwałe | `subscription_choice.py` → `pending_blocks`, `record_failures(outcomes)`; `SubscriptionTarget.failures` | `test_subscription_choice.py::test_pending_*` (9 przypadków), `::test_record_failures_by_outcome` (7 wyników `ReadOutcome`); `test_watch_state.py::test_failures_roundtrip`; `test_subscription_owner.py::test_pending_survives_restart` | K11, K12 |
| §6.2 próg celu | najlepsza klasa martwych prób (definicja §5.9); trwały; nie ustawiają `failed`, `removed`, odrzucenie H2/U-07/U-08 ani zatrzymanie po metadanych | `SubscriptionTarget.threshold`; `subscription_choice.raise_threshold`; ustawiany w `automation.py` → `_settled_target` (:4173) z `EpisodeChoice.traits.resolution` | `test_subscription_choice.py::test_threshold_*`; `test_subscription_scenarios.py::test_stalled_1080_blocks_720_after_restart`, `::test_dead_attempt_after_compaction_uses_snapshot` | K11, K13 |
| §6.2 wybór | klucz bez pewności | `subscription_choice.py` → `choice_key` | `::test_choice_key_order`, `::test_known_file_before_after_metadata` | K12 |
| §6.2 wykluczenie hasha, stare `hash:fileIdx`, ochrona pliku, trwały ID próby | `tried` przechowuje hash (tylko dla własnego celu); ochrona innych celów po hashu i ścieżce qBittorrenta; `started` | `subscription_targets.py` → `excluded`, `SubscriptionTarget.started`; `subscription_choice.py` → `protected_files`, `is_taken` (zastępuje `_taken_pairs`, `automation.py:3919–3927`); konsumenci `_subscription_outcome` i `transfers.metadata_check`; `automation.py` → `_admit_attempt` (:3947, polecenie `sub:{id}:{n}:{started}` zamiast :3973) | `test_subscription_targets.py::test_excluded_legacy_pair_key`; `test_subscription_choice.py::test_protected_*`, `::test_tried_hash_excluded_only_for_own_target`; `test_transfers.py::test_metadata_check_uses_protected_paths`; `test_subscription_migration.py::test_four_to_five_*`; `test_subscription_attempts.py::test_attempt_command_id_never_repeats` | K11, K12, K13 |
| §6.2 następna próba po rozliczeniu poprzednika | wybór nie omija bramki rozliczenia | wybór: `_subscription_outcome`; przyjęcie: `_admit_attempt` + `_attempt_previous` (:3964); start treści: `_may_start_selection` (:5873) → `_replacement_ready` (:5883) bez zmian | `test_subscription_scenarios.py::test_next_release_chosen_content_waits_for_previous_settlement` | K13 |
| §6.2 po metadanych | zatrzymanie, wykluczenie, bez zużycia limitu; restart → inne wydanie z tym samym licznikiem | `transfers.py` → `metadata_check`; `automation.py` → `_stop_after_metadata` | `test_subscription_attempts.py::test_after_metadata_restart_admits_other_same_count` | K13 |
| §6.3 historia PL | trzy stany, lokalny dowód najpierw (trwały snapshot cech przyjęcia), błąd zachowuje obserwację | `subscription_choice.py` → `polish_history`; `SubscriptionTarget.polish`; `EpisodeChoice.traits` (§6.1 planu) | `test_subscription_choice.py::test_polish_history_*` (≥8 przypadków); `test_subscription_owner.py::test_local_polish_evidence_survives_restart_and_compaction` | K11, K14 |
| §6.3 bufor, 0, zmiana od najbliższego sprawdzenia | ustawienie godzin | `user_settings.py` → `subscription_polish_wait_h`; `subscription_choice.py` → `wait_until` | `::test_wait_until_*`; `test_user_settings.py::test_polish_wait_range` | K9, K14 |
| §6.3 „Pobierz teraz” (O-2) | kończy czekanie tylko dla celu i bieżącego terminu; od razu sprawdzenie i pierwszy dopuszczalny §6.2 bez `niepewnego`; bez kandydata cel należny z powodem §8; trwałe, w rejestrze decyzji | istniejące polecenie `subscription_check` (`automation.py:3548`, `_request_subscription_check` :3654–3668) z `number` celu; `SubscriptionTarget.polish_skip`; `subscription_choice.decide` (`ChoiceState.skip_wait`); U08 klawisz `T` | `test_subscription_choice.py::test_skip_wait_*`; `test_subscription_owner.py::test_download_now_*`; `tests/cli/test_subscriptions_panel.py::test_download_now_key`, `::test_polish_state_per_target`, `::test_polish_state_refreshes_on_revision`, `::test_download_now_refusal_refreshes`; `test_subscription_owner.py::test_subscriptions_revision_changes_only_on_target_state`; `test_subscription_targets.py::test_next_search_at_unsettled_skip_is_now` | K14 |
| §6.3 w trakcie / po buforze | pierwszy z PL od razu; po buforze pierwszy dopuszczalny z powodem | `subscription_choice.py` → `decide` | `::test_decide_waiting_takes_polish_first`, `::test_decide_after_buffer_reason` | K14 |
| §6.3 PL bez roli i dubbing nie kończą | | `subscription_choice.decide` | `::test_decide_bare_polish_keeps_waiting` | K14 |
| §6.3 ręczne pobranie rezerwuje | istniejące U-16 | bez zmian (`automation.py`) | istniejący test rezerwacji w `test_subscription_owner.py` | — |
| §6.3 rejestr i szczegóły | stan i dowód; tekst w szczegółach | `acquisition_decisions.py` → `_FIELDS` (:45); `cli/subscription_texts.py` → `polish_line`; `cli/anime.py` → `_subscription_facts` (:888) | `test_acquisition_decisions.py::test_polish_history_fields`; `tests/cli/test_subscriptions_panel.py::test_polish_line_*` | K14, K15 |
| §6.4 harmonogram | P-1 = 0, U-14 | bez zmian (`subscription_targets.py`) | istniejące testy harmonogramu | — |
| §6.5 stoi 10 min | martwa, także bez metadanych; pauza się nie liczy | `control.py` → `AutomationPolicy.transfer_stall_s` = 600; `automation.py` → `METADATA_TIMEOUT_S` (:410) = 600 | `test_subscription_migration.py::test_four_to_five_stall_default_only`; istniejące testy zastoju z nową wartością | K11, K13 |
| §6.5 następna próba / należny / wyczerpany | istniejące przejścia 11, 16 | `_settled_target` (:4173, `settle_target`) zamyka martwą próbę i podnosi próg; następny wybór w `_subscription_outcome` | `test_subscription_scenarios.py::test_stalled_next_*` | K13 |
| §6.5 ręczne „stoi od 10 min” | etykieta, bez zamiany | `episode_commands.py` → `EpisodeStatus.stalled_since`; `cli/anime.py` → etykieta | `tests/cli/test_anime_episodes.py::test_manual_stalled_label` | K13 |
| §6.6 paczki | auto niedopuszczalne; lista według reguł | `subscription_choice.usable`; `episode_selection.list_order` | pokryte wyżej | K6, K12 |
| §7 rejestr pewności i jakości | wszystkie kandydaty decyzji | `acquisition_decisions.py`; `automation.py` → `_record_decision` (:5296) | `test_acquisition_decisions.py::test_selection_candidates_quality_confidence` | K15 |
| §7 próg przyszły | bez kodu | — | — (poza zakresem wykonania; dane zbiera K15) | — |
| §8 powiadomienia | jedno na odcinek i powód; sześć rodzajów; bez PL po buforze bez powiadomienia | `automation.py` → `_notify_target` (reuse `tray.notify`, `anishift/platform/tray.py:192`, i trwałych `NotificationKey`, `watch_state.py:1629`); `subscription_texts.py` → `failure_notice` | `t/app/test_notification.py::test_notice_once_per_target_reason`, `::test_notice_*` (po jednym na rodzaj), `::test_no_polish_after_buffer_silent` | K15 |
| §8 źródła niedostępne > 1 h | per należny cel; początek przeżywa restart; reset przy udanym wyniku (także pustym), braku włączonych źródeł i końcu należności | `SubscriptionTarget.sources_down_since` (§6.1 planu); `subscription_choice.sources_down`; `automation.py` → `_subscription_outcome` (§6.4) | `test_notification.py::test_sources_down_notice_once_across_restart`; `test_subscription_choice.py::test_sources_down_reset_by_empty_success`, `::test_sources_down_not_started_when_all_disabled`; `test_subscription_owner.py::test_sources_down_per_target`, `::test_sources_down_cleared_when_target_settles` | K11, K12, K15 |
| §9 zestaw wzorcowy | fixtury (~17 MB w całości, W3), oczekiwania, pokrycie, offline; replay z `content-type` wg źródła, osobne zestawy dozwolonych zapytań dla ręcznego i subskrypcji (O9) | `tests/fixtures/acquisition/reference/`; `t/app/test_acquisition_reference.py` | §9 planu | K0, K16 |

### 3.2 Wiersze §10

| # | Miejsce (spec A §10) | Realizacja | Test | Krok |
| --- | --- | --- | --- | --- |
| 1 | spec U-02, §8, §11 | pięć adapterów, `EpisodeSearch` | `test_bootstrap.py::test_acquisition_sources_are_exactly_five`, testy adapterów | K8, K9 |
| 2 | spec §9 „szerokie Nyaa” | Nyaa zwykłym `TorrentSource` w `EpisodeSearch` (konwersja `_release_stream`), bez ścieżki zamiennika | `test_episode_search.py::test_nyaa_is_regular_source` | K9 |
| 3 | spec §9 ML | `confidence` tylko w `episode_selection` i UI; `subscription_choice` bez pola | `test_subscription_choice.py::test_choose_ignores_confidence`; test architektury: `subscription_choice` nie importuje `episode_confidence` | K3, K12 |
| 4 | spec U-03, R-06 | `%` w kolumnie, `suggestion` + „niepewne” | `test_episode_selection.py::test_suggestion_marks_uncertain`; `test_anime_episodes.py::test_uncertain_mark` | K6, K10 |
| 5 | spec U-04, R-02 | `release_quality` klasy i punkty | `test_release_quality.py` | K4 |
| 6 | spec R-07 | wspólne `release_quality` i `subscription_choice` dla listy, automatu i zamiany. **Reguła w A1:** czysta `subscription_choice.replacement` (§5.6, §5.12). **Wyzwalacz w E4:** kontrola U-08 i wywołanie reguły w ścieżce ręcznej (spec A §11; `e3-subskrypcje.md` O-7; `e2-pobieranie.md:118`); A1 nie dodaje kontroli ani stanu zamiany | `test_subscription_choice.py::test_replacement_*` (§5.12) | K12 |
| 7 | spec §14 | brak raportu P-2/P-5; odbiór K16 | `test_acquisition_reference.py` | K16 |
| 8 | spec U-22 | inwariant rekordu poluzowany, `read_listing` bez Kitsu | `test_subscription_targets.py::test_record_mapping_without_kitsu`; `test_acquisition.py::test_read_listing_live_without_kitsu` | K11 |
| 9 | spec U-25 | `_BLURAY_RE` −10, kodek 0 | `test_release_quality.py::test_bluray_minus_ten`, `::test_codec_no_points` | K4 |
| 10 | spec U-21 | przypadek filmowy | `test_acquisition_reference.py` (przypadek `movie`) | K16 |
| 11 | spec U-14, S-14 | powiadomienia §8 | `test_notification.py` | K15 |
| 12 | spec Q-03 | `_FastCache` ≤30 min; dociągane `_PulledCache` | `test_episode_search.py::test_skipped_fast_source_uses_last_result_30_min` | K12 |
| 13 | spec R-01, Q-02, Q-04 | frazy, deadline 30 s, dostawcy w `RequestControl` | `test_episode_phrases_*`, `test_deadline_*`, `test_provider_*` | K7, K9 |
| 14 | spec R-03, R-04 | kolumny; potwierdzenia bez zmian | `test_anime_view.py::test_offer_columns_quality_confidence_last` | K10 |
| 15 | spec R-05 | `seed_points(None)` = 5, „?”; zero seedów w §6.2 | `test_release_quality.py::test_seed_points_unknown`; `test_subscription_choice.py::test_zero_seeds_*` | K4, K12 |
| 16 | spec P-02 | `_episode_download` na pełnym wyniku `search_episode` | `test_automation.py::test_episode_download_waits_for_all_sources` | K9 |
| 17 | plan §3.3, przejście 6, P-2 | usunięte dopuszczenie `niepewnego` (`eligible`, `subscription_targets.py:456`, zastąpione `subscription_choice.admissible`) | `test_subscription_choice.py::test_admissible_rejects_uncertain` | K12 |
| 18 | plan §3.3 wybór | `decide` z progiem i oczekującymi | `::test_threshold_*`, `::test_pending_*` | K12 |
| 19 | plan §3.3 limit prób | `attempts` zwracany po metadanych; `started` rośnie | `test_subscription_attempts.py::test_after_metadata_restart_admits_other_same_count` | K11, K13 |
| 20 | plan klucz pary | `excluded` po hashu; stare klucze | `test_subscription_targets.py::test_excluded_legacy_pair_key` | K11 |
| 21 | plan P-5 | usunięty `T_niepewny` (stałe i gałąź w `automation.py`) | `test_subscription_choice.py::test_admissible_rejects_uncertain`; brak symbolu w `rg` jako dowód | K12 |
| 22 | plan P-9 | 600 s dla metadanych i zastoju | `test_transfers.py::test_metadata_timeout_600`; `test_subscription_migration.py::test_four_to_five_stall_default_only` | K11, K13 |
| 23 | plan P-10 | per źródło, dociągane, budżet | `test_episode_search.py::test_skipped_*`, `::test_subscription_check_tsukihime_budget_14` | K12 |
| 24 | plan przejście 10, U-18c, E3 D-11 | `metadata_check` → stop w automacie | `test_subscription_attempts.py::test_after_metadata_ambiguous_stops` | K13 |
| 25 | spec U-18(a) w automacie | ponowne H1 na ścieżce qBittorrenta | `test_transfers.py::test_metadata_check_unique_name_reclassified` | K13 |
| 26 | plan §3.3 dopuszczalność, E3 D-10 | `ChoiceCandidate.after_metadata` | `test_subscription_choice.py::test_admissible_release_name_only_after_metadata` | K12 |
| 27 | spec U-23 | `dub_only` na końcu; `usable` odrzuca | `test_episode_selection.py::test_dub_only_after_regular`; `test_subscription_choice.py::test_usable_rejects_dub_only` | K6, K12 |
| 28 | plan §5.6 | rejestr: `sources`, `quality`, `confidence`, `conflict`, `polish_history`, `numbering` | `test_acquisition_decisions.py::test_selection_fields_a1` | K15 |
| 29 | spec R-02 sugestia (O-5) | `suggestion` = pierwszy wiersz §6.1 + „niepewne” | `test_episode_selection.py::test_suggestion_is_first_group_one_row` | K6 |

## 4. Drzewo zmian

```text
anishift/
├── AGENTS.md                                 [EDIT] mapa: nowe moduły czyste i źródła pozyskiwania
├── bootstrap.py                              [EDIT] wiring pięciu źródeł i EpisodeSearch w _acquisition_service (:90)
├── application/
│   ├── AGENTS.md                             [EDIT] reguły A1: automat bez pewności, schemat 5, oferta częściowa, punkt podpięcia zamiany dla E4
│   ├── __init__.py                           [EDIT] eksport ReleaseTraits zamiast ReleaseFacts (:125, :283) i typów oferty
│   ├── release_quality.py                    [NEW]  czyste: cechy wydania, deklaracje języków per plik, klasy, punkty
│   ├── episode_confidence.py                 [NEW]  czyste: zamrożony model pewności (wagi + Platt)
│   ├── episode_releases.py                   [NEW]  czyste: hash BTIH, scalanie źródeł po hashu, pliki z deklaracjami, paczka
│   ├── subscription_choice.py                [NEW]  czyste: dopuszczalność, wybór, próg, oczekujące, historia PL, „Pobierz teraz” (skip_wait), zamiana, chronione pliki, zegar niedostępności
│   ├── episode_search.py                     [NEW]  orkiestracja źródeł: kontrakt źródła, konwersja Nyaa, klasyfikacja błędów, kompletność, limity czasu, cache, kolejka uzupełnień
│   ├── episode_identity.py                   [EDIT] identity_evidence, classify_release_name, CONFLICT_REASONS, powód "mapped bez numeracji celu" (D2)
│   ├── episode_selection.py                  [EDIT] RankedCandidate z jakością i pewnością, list_order, representative, suggestion = pierwszy wiersz (O-5), numbering_gap, identity_target(numbering)
│   ├── acquisition.py                        [EDIT] search_episode (lista, D, brak numeracji); subscription_check; U-22 w read_listing; mosty numeracji i ID (D1-D3) w read_listing; prepare_episode przez streams_releases do K12
│   ├── subscription_targets.py               [EDIT] SubscriptionTarget/Record v5 (w tym polish_skip); excluded; inwariant U-22
│   ├── subscription_migration.py             [EDIT] migrate_to_five (bez importu legacy); migrate kończy na schemacie 4
│   ├── watch_state.py                        [EDIT] schemat 5: osobna ścieżka 4 → 5 (legacy tylko do kopii), wersjonowane klucze i receipt, kopia .a1-migration.bak
│   ├── control.py                            [EDIT] schemat 5, stall 600, ChoiceTraits w EpisodeChoice, EpisodeAssignment.stopped
│   ├── transfers.py                          [EDIT] metadata_check po metadanych (ponowne H1 i §6.2)
│   ├── automation.py                         [EDIT] wybór, chronione pliki, po metadanych, próg, czekanie PL, powiadomienia, cykl oferty z rewizjami, subscriptions_revision w _status (zwiększana w _save), _publish_state po T
│   ├── acquisition_decisions.py              [EDIT] K6: offer_check/candidate_proposal bez facts; K15: nowe pola rejestru (w tym numbering)
│   └── episode_commands.py                   [EDIT] EpisodeOfferView.revision/pending_sources/source_lines, EpisodeStatus.stalled_since/polish_wait_until/polish_skipped
├── config/
│   ├── user_settings.py                      [EDIT] przełączniki pięciu źródeł, subscription_polish_wait_h
│   └── field_catalog.py                      [EDIT] SettingSpec dla nowych ustawień (GLOBAL)
├── platform/
│   └── local_control.py                      [EDIT] _event_key (:821) scala episode_offer_partial per command_id i klucz
├── services/
│   ├── http_requests.py                      [EDIT] dostawcy nowych hostów (w tym arm, kitsu), okna TsukiHime, deadline wywołującego, pula z copy_context, DeadlineExceeded/ProviderCooldown/BudgetExhausted
│   ├── catalog/
│   │   ├── anilist.py                        [EDIT] countryOfOrigin w zapytaniach (:61, :101) i _candidate (:370)
│   │   ├── anizip.py                         [EDIT] mapping_by_anidb (ten sam parser, parametr anidb_id)
│   │   ├── arm.py                            [NEW]  ArmCatalog.ids: AniList → AniDB ID i thetvdb-season (arm-server)
│   │   ├── kitsu.py                          [NEW]  KitsuCatalog.kitsu_id: Kitsu mappings po AniList ID z kontrolą zwrotną
│   │   └── types.py                          [EDIT] TitleCandidate.country (:62)
│   └── torrents/
│       ├── AGENTS.md                         [EDIT] opis źródeł i limitów
│       ├── __init__.py                       [EDIT] eksport nowych adapterów
│       ├── names.py                          [EDIT] DUBBED_RE z release_quality (dotąd _DUBBED_RE :90)
│       ├── nyaa.py                           [EDIT] przyczyna HTTPStatusError przy statusie ≠ 200 (:161–162)
│       ├── torrentio.py                      [EDIT] StreamCandidate.source = "torrentio" w _stream (:79)
│       ├── tsukihime.py                      [NEW]  adapter TsukiHime (id tytułu, strona odcinka, spis z językami plików, po hashu)
│       ├── knaben.py                         [NEW]  adapter Knaben API v2 (PagedSource)
│       └── nekobt.py                         [NEW]  adapter nekoBT torznab (PagedSource, tagi języków)
└── cli/
    ├── AGENTS.md                             [EDIT] kolumny Jakość/Pewność, oferta częściowa
    ├── resident.py                           [EDIT] episode_offer_start/episode_offer_get (krótkie), episode_choose z offer_id/revision/info_hash/path, disconnect przy otwartej ofercie
    └── interactive/
        ├── anime.py                          [EDIT] wiersze ofert, rewizje oferty, wybór w trakcie bez nowej generacji, szczegóły, etykieta „stoi”, klawisz T w U08; po odmowie T jedno refresh_episode_states
        ├── anime_state.py                    [EDIT] AnimeRow.quality, AnimeRow.confidence
        ├── anime_view.py                     [EDIT] dwie kolumny na końcu wiersza oferty
        ├── state.py                          [EDIT] _forward_anime (:1016) przekazuje episode_offer_partial; po ponownym observe sygnał do get oferty; number w subscription_check (:509)
        ├── settings.py                       [EDIT] kategoria „Pobieranie” z przełącznikami i godzinami PL
        └── subscription_texts.py             [EDIT] polish_line, failure_notice

tests/
├── application/
│   ├── fakes.py                              [EDIT] fałszywe źródła (StreamSource, TorrentSource, PagedSource, TsukiHime; wstrzymywane na Event) dla testów ownera
│   ├── test_architecture.py                  [EDIT] cztery nowe moduły w _PURE_MODULES
│   ├── test_release_quality.py               [NEW]  punkty, klasy, języki, dubbing, kontrola wag §5.4
│   ├── test_episode_confidence.py            [NEW]  równoważność z modelem i cechami badania
│   ├── test_episode_releases.py              [NEW]  hash, scalanie, pliki z deklaracjami, paczka
│   ├── test_subscription_choice.py           [NEW]  §6.2, §6.3 (w tym skip_wait), próg, oczekujące, zamiana
│   ├── test_episode_search.py                [NEW]  kontrakt źródeł, frazy, budżety, limity czasu, cache, kolejka, oferta częściowa
│   ├── test_acquisition_reference.py         [NEW]  zestaw wzorcowy i pokrycie offline (§9)
│   ├── test_episode_identity.py              [EDIT] ocena nazwy wydania, konflikt
│   ├── test_episode_selection.py             [EDIT] nowy RankedCandidate, kolejność, sugestia (pierwszy wiersz + niepewne), reprezentant
│   ├── test_episode_commands.py              [EDIT] nowe pola widoków
│   ├── test_acquisition.py                   [EDIT] search_episode, brak numeracji, U-22, mosty numeracji (K9b)
│   ├── test_acquisition_decisions.py         [EDIT] K6: ranking przez streams_releases bez facts (:68–74); K15: nowe pola rejestru
│   ├── test_automation.py                    [EDIT] D po wszystkich źródłach, cykl oferty, dowód wyboru na rewizji, przełącznik przez API ustawień
│   ├── test_subscription_targets.py          [EDIT] SubscriptionTarget/Record v5, excluded, U-22
│   ├── test_subscription_migration.py        [EDIT] 4 → 5 bez importu legacy, 1–3 → 4 → 5
│   ├── test_watch_state.py                   [EDIT] round-trip schematu 5, kopia, wersjonowane klucze
│   ├── test_subscription_attempts.py         [EDIT] po metadanych, ID próby, źródła nie zużywają próby
│   ├── test_subscription_owner.py            [EDIT] restart z oczekującymi, progiem i lokalnym dowodem PL; „Pobierz teraz” (restart, brak kandydata)
│   ├── test_subscription_scenarios.py        [EDIT] stoi → próg → następne, bramka rozliczenia
│   ├── test_transfers.py                     [EDIT] metadata_check, 600 s
│   ├── test_selective_transfers.py           [EDIT] dopasowanie do nowego wyniku metadanych
│   └── test_notification.py                  [EDIT] powiadomienia §8, niedostępność przez restart
├── platform/
│   └── test_local_control.py                 [EDIT] scalanie zdarzeń oferty po offer_id
├── services/
│   ├── test_http_requests.py                 [EDIT] dostawcy, okna, deadline wywołującego (wiszący transport, dołączający), budżet przez obie pule, typy błędów
│   ├── catalog/
│   │   ├── test_anilist.py                   [EDIT] countryOfOrigin
│   │   ├── test_anizip.py                    [EDIT] mapping_by_anidb
│   │   ├── test_arm.py                       [NEW]  odpowiedzi arm-server (213805, 204389), 404, błąd
│   │   └── test_kitsu.py                     [NEW]  kontrola zwrotna, niejednoznaczny wpis, 404
│   └── torrents/
│       ├── test_tsukihime.py                 [NEW]  adapter na zapisanych odpowiedziach
│       ├── test_knaben.py                    [NEW]
│       ├── test_nekobt.py                    [NEW]
│       ├── test_torrentio.py                 [EDIT] pole source
│       └── test_names.py                     [EDIT] DUBBED_RE bez zmiany zachowania
├── config/
│   ├── test_user_settings.py                 [EDIT] nowe pola i ich czyszczenie
│   ├── test_field_catalog.py                 [EDIT] nowe SettingSpec = pola UserSettings
│   └── test_bootstrap.py                     [EDIT] pięć źródeł
├── cli/
│   ├── test_anime_episodes.py                [EDIT] kolumny, rewizje oferty, wybór w trakcie (integracyjny), 3 s bez wierszy, dwa klienty, konflikt, „stoi”
│   ├── test_anime_view.py                    [EDIT] układ kolumn
│   ├── test_interactive_state.py             [EDIT] przekazanie episode_offer_partial, utrata obserwacji vs zamknięcie sesji katalogu
│   ├── test_resident.py                      [EDIT] start oferty zwalnia _catalog_lock, revision wyboru, disconnect przy otwartej ofercie
│   ├── test_interactive_settings_layout.py   [EDIT] kategoria „Pobieranie”
│   └── test_subscriptions_panel.py           [EDIT] linia PL, powód niepowodzenia, klawisz T pobierz teraz
└── fixtures/acquisition/
    ├── confidence-model.json                 [NEW]  kopia conf_frozen_model.json (bez zmian)
    ├── confidence-cases.json                 [NEW]  kandydaci (release/path/filename), wektory cech i predykcje z badania 2
    └── reference/
        ├── expectations.json                 [NEW]  oczekiwania potwierdzone przez właściciela
        ├── coverage-baseline.json            [NEW]  640 hashy badania 1 per przypadek i źródło, gone z dowodem, unverified
        └── <case>.json                       [NEW]  surowe odpowiedzi źródeł per przypadek
                                                     (wszystkie pliki reference/ jako .json.gz, §9.1)

scripts/tmp/a1_record_reference.py            [NEW, jednorazowy] nagranie fixtur (scripts/tmp/ jest na jednorazowe skrypty)
```

Bez `[DEL]` na poziomie plików. Znikają symbole (wymienione w §5): `ReleaseFacts`, `release_facts`,
`_rank_key`, `eligible`, `candidate_pair`, `_taken_pairs`, `_episode_queries`, `_episode_base`,
blokujące IPC `episode_offer` (zastąpione w K10b), stara ścieżka
`prepare_episode` dla subskrypcji (po K12), `_DUBBED_RE` (przeniesione) i gałąź `T_niepewny`.

## 5. Specyfikacja per plik

Każdy `[EDIT]` wskazuje istniejący symbol. Sygnatury są kontraktem planu; nazwy prywatnych
helperów wybiera autor.

### 5.1 `anishift/application/release_quality.py` [NEW, czysty]

Odpowiedzialność: deklaracje języków i nazwy → cechy, klasy i punkty jakości (spec A §5). Jedno
źródło reguł jakości dla listy, automatu i zamiany (R-07).

```python
class LanguageSource(StrEnum): TSUKIHIME, NEKOBT, FILE_NAME, RELEASE_NAME, TORRENTIO_FLAG

@dataclass(frozen=True, slots=True)
class LanguageDeclaration:
    source: LanguageSource
    file: str | None                   # ścieżka pliku w torrencie; None = deklaracja całego wydania
    subtitles: frozenset[str] | None   # None i frozenset() = brak danych (§5.2)
    audio: frozenset[str] | None
    complete_audio: bool               # pełna lista (TsukiHime audiolangs, nekoBT A=)
    polish_bare: bool = False          # flaga PL Torrentio lub sam token PL/POL/Polish

class PolishClass(IntEnum): POLISH = 0; BARE = 1; NONE = 2
class AudioClass(IntEnum): ORIGINAL = 0; KOREAN = 1
class ResolutionClass(IntEnum): FULL_HD = 0; UHD = 1; HD = 2; OTHER = 3; UNKNOWN = 4

@dataclass(frozen=True, slots=True)
class ReleaseTraits:
    polish: PolishClass
    polish_audio_beside_original: bool
    english_subtitles: bool
    audio: AudioClass
    dub_only: bool
    raw: bool
    hardsub: bool
    resolution: int | None
    platform: bool
    bluray: bool
    seeders: int | None

def language_code(code: str) -> str
def release_traits(names: Sequence[str], tags: Sequence[str], declarations: Sequence[LanguageDeclaration],
                   *, file: str | None, pack: bool, donghua: bool, seeders: int | None) -> ReleaseTraits
def resolution_class(resolution: int | None) -> tuple[ResolutionClass, int]   # (klasa, odległość od 1080)
def class_key(traits: ReleaseTraits) -> tuple[int, ...]                        # rozdzielczość → PL → audio (O-4)
def seed_points(seeders: int | None) -> float
def quality_score(traits: ReleaseTraits) -> float                              # niezaokrąglone, 0–90
```

- `release_traits(file=…)` bierze deklaracje z `file == file` (zakres pliku) przed deklaracjami
  `file is None` (zakres wydania); przy `pack=True` deklaracje wydania są pomijane (spec A §5.2:133).
- `donghua` pochodzi z `TitleCandidate.country == "CN"` (droga w §5.9); bez danych `False`.
- Stałe `Final` z docstringami: punkty (`POLISH_POINTS = 40.0` …), `PLATFORMS`, `DUB_MARKERS`,
  `DECLARATION_PRIORITY`, `DUBBED_RE`.
- Reuse: `_resolution`/`_resolution_class` z `episode_selection.py` przenoszone tutaj;
  `DUBBED_RE` przeniesiony z `services/torrents/names.py:90`, a `names.py` importuje go stąd
  (services → application to istniejący kierunek, `torrentio.py:13`). Jedno źródło prawdy.
- Wołają: `episode_selection.rank_candidates`, `subscription_choice`, `automation._episode_choice` (snapshot).

### 5.2 `anishift/application/episode_confidence.py` [NEW, czysty]

```python
def features(evidence: IdentityEvidence) -> dict[str, float]
def confidence(evidence: IdentityEvidence) -> float        # 0..1
```

- `_WEIGHTS: Final[Mapping[str, float]]`, `_PLATT_INTERCEPT`, `_PLATT_LOGIT` — literalna kopia
  `conf_frozen_model.json` (`weights`, `platt.intercept`, `platt.logit`). `selected_threshold`
  (0,99) nie jest przenoszony: automat go nie używa (spec A §4, §7).
- `features` odtwarza słownik `x` z `conf_model.py:57–87` 1:1 (te same klucze, skalowanie
  `residual_words`, `pack` z `release`, `multiseason` z `_multiple_works(release, identity)`).
  Weta (`conf_model.py:37–56`) nie są cechą ani konfliktem (spec A §2).
- Test: stałe równe `tests/fixtures/acquisition/confidence-model.json`; wektory i predykcje równe
  `confidence-cases.json` (tolerancja 1e-9).
- Wołają: `episode_selection.rank_candidates`. Nie importuje go `subscription_choice` (test architektury).

### 5.3 `anishift/application/episode_identity.py` [EDIT]

Istniejące: `REASONS` (:133), `IdentityVerdict` (:189), `IdentityAssessment` (:198), `_Target` (:206),
`_Parsed` (:229), `classify` (:1180), `classify_many` (:1188), `VIDEO_EXTENSIONS` (:35).

```python
@dataclass(frozen=True, slots=True)
class IdentityEvidence:                 # projekcja tego, co conf_model.features() brał z prywatnych helperów
    assessment: IdentityAssessment
    kind: str
    mode: str
    selected: str                       # filename albo ostatni człon path
    path: str
    release: str
    anchor: bool
    broad: bool
    number: Decimal | None
    season: int | None
    part: int | None
    local: int | None
    episode: int | None
    absolute: int | None
    target_season: int | None
    target_part: int | None
    named_season: int | None
    residual: str
    residual_ok: bool
    episode_anchor: bool
    year_ok: bool
    multiple_works: bool

def identity_evidence(target: Mapping[str, object], candidate: Mapping[str, object]) -> IdentityEvidence
def classify_release_name(target: Mapping[str, object], name: str) -> IdentityAssessment
CONFLICT_REASONS: Final[frozenset[str]]   # podzbiór REASONS: inny sezon/część/dzieło/numer, rodzaj materiału
def is_conflict(assessment: IdentityAssessment) -> bool
def conflict_label(assessment: IdentityAssessment) -> str   # „inny sezon (S01)”
```

- `candidate` to ten sam kontrakt co `classify(target, candidate)`: klucze `release`, `path`,
  `filename`. Wybór tekstu jest identyczny z `conf_model.py:20–26`: `selected = filename or
  basename(path)`, tekst = `selected or release`, rozszerzenie wideo zdejmowane tylko, gdy jest.
  Ocena „bez nazwy pliku” to kandydat `{"release": name}` — ta sama projekcja, bez osobnej flagi.
- `identity_evidence` składa dokładnie te wywołania, których używał `conf_model.features()`
  (`_target`, `classify`, `_prepare`, `_parse`, `_absolute_echo`, `_year`, `_episode_residual`,
  `_multiple_works`); nie powstaje drugi parser. `_structural_decision` nie jest używane przez projekcję,
  bo zasila tylko weta poza K3.
- `classify_release_name` używa tego samego parsera bez wymogu rozszerzenia wideo; werdykty
  `classify` bez zmian, więc goldeny `identity-golden.json`, `identity-231.json`,
  `identity-regressions.json` zostają nietknięte (dowód: ich testy zielone bez edycji fixtur).
  Zmiana choć jednego werdyktu `classify` uruchamia procedurę `plans/e1-integracja.md` §10.6.
- `is_conflict(a)` = `a.verdict is MISMATCH` (każdy `niezgodny`) **albo** `a.verdict is
  INSUFFICIENT and a.reason in CONFLICT_REASONS` (spec A §2:25). `MATCH` nigdy.
- **`CONFLICT_REASONS` (zamknięta lista, 19 powodów z `REASONS` :133–184; kryterium: nazwa jawnie
  deklaruje coś sprzecznego z celem, nie brak danych)** — z etykietą `conflict_label`:

  | Powód (`REASONS`) | Etykieta |
  | --- | --- |
  | `Season marker conflicts with the target numbering system.` (:137) | inny sezon |
  | `Part/cour marker conflicts with the target.` (:138) | inna część |
  | `Local and mapped numbering conflict.` (:148) | inny numer |
  | `Package directory explicitly identifies Plex extra material.` (:150) | dodatek |
  | `Package explicitly identifies a neighboring work.` (:151) | inne dzieło |
  | `Package explicitly identifies a different season.` (:152) | inny sezon |
  | `Package explicitly identifies a different part/cour.` (:153) | inna część |
  | `Package explicitly identifies a different final season.` (:154) | inny sezon |
  | `Package ordinal part/cour conflicts with the target.` (:158) | inna część |
  | `Package localized movie format conflicts with the target.` (:159) | inny rodzaj (film) |
  | `Package explicitly identifies a different language-specific media format.` (:162) | inny rodzaj materiału |
  | `Package explicitly identifies non-episode material.` (:165) | nie odcinek |
  | `Package explicitly identifies a different media type.` (:166) | inny rodzaj materiału |
  | `Package year conflicts with target metadata.` (:167) | inne dzieło (rok) |
  | `Package explicitly identifies a numbered sequel.` (:168) | kontynuacja |
  | `Selected file or work directory identifies a neighboring catalogue work.` (:170) | inne dzieło |
  | `Selected directory has a numbered season conflicting with the target.` (:171) | inny sezon |
  | `Selected TV variant conflicts with the target editing variant.` (:172) | inny wariant montażu |
  | `Selected filename more specifically identifies a neighboring work.` (:181) | inne dzieło |

- **Powody łączone „conflicts … or is unresolved” (:156, :157, :163) — poza listą.** Ten sam tekst
  powstaje dla liczby innej niż cel **i** dla liczby nierozpoznanej (`number is None or number not in
  …`, :830, :841, :911), także gdy zapis jest zgodny z celem, ale parser go nie zna (cel sezon 11,
  `Example 第十一季/01.mkv` → `_context_number` daje `None`, :812–818). Konflikt wyklucza wydanie
  z kolejki uzupełnień i ze zbioru oczekujących (spec A :80, :185), więc fałszywy konflikt mógłby
  odblokować gorsze wydanie; brak oznaczenia jest bezpieczny (wydanie zostaje `niepewny`, blokuje
  i czeka). A1 nie rozdziela tych powodów i nie zmienia goldenów H1 (§10.6 `e1-integracja.md`).
- **Poza listą (brak danych, nie sprzeczność):** trzy powody łączone wyżej, `The required part/cour is not established.`,
  `A franchise alias does not identify this installment.`, `Movie segment or numbering requires…`,
  `OVA/special needs…`, `No unambiguous selected episode number.`, `Bare number is not the local
  episode…`, `Package contains an unresolved sequel qualifier.`, `Package contains an unresolved
  continuation marker.`, `Package contains an uncatalogued title suffix.`, `Package Russian season
  declaration is unresolved.` (sam znacznik bez liczby), `Titleless file lacks…`, `Release editing
  variant is not established…`, `Malformed candidate metadata.`, `No selected file.`, `Malformed
  target or archived identity metadata.`, `Unresolved leading bracket…`, `Filename year is missing
  from or conflicts with runtime target metadata.` (łączony, ale rok bywa po prostu nieobecny —
  znacznik nie musi istnieć, więc gałąź „missing” dominuje; poza listą), `Unconsumed filename text…`.
- Testy: `test_conflict_reasons_subset_of_reasons` (`CONFLICT_REASONS <= REASONS`, 19 elementów,
  bez :156, :157, :163); `test_every_mismatch_is_conflict` (wszystkie 4 powody `MISMATCH`: :141, :176,
  :178, :179); `test_insufficient_conflict_cases` — pozytywne: `classify` na nazwach z innym sezonem
  pakietu (`S02` przy celu S01), innym dziełem w katalogu, rokiem pakietu sprzecznym; negatywne:
  brak numeru, nieustalona część, nieobecny rok, nieskatalogowany sufiks oraz cel sezon 11 +
  `Example 第十一季/01.mkv` (`niepewny`, nie konflikt); `test_conflict_label_for_every_reason`;
  `test_episode_search.py::test_unresolved_season_stays_in_completion_queue` (to samo wydanie
  zostaje w kolejce uzupełnień i w zbiorze oczekujących).
- **Cel bez numeracji (spec A §3.5 D2, K2):** dziś nazwa `Koori no Jouheki S02E01` przy celu bez
  `season` daje `Season marker conflicts with the target numbering system.` (sprawdzone na
  `classify`), czyli konflikt, choć celowi brakuje danych, a nazwa niczemu nie przeczy. Zmiana:
  w `_identity_conflict` (`episode_identity.py:635-640`) przy `parsed.mode == "mapped"`
  i `target.season is None` powstaje nowy powód `Mapped numbering cannot be checked without target
  numbering.` (`INSUFFICIENT`, dopisany do `REASONS`, poza `CONFLICT_REASONS`, które zostają
  19-elementowe). Werdykt pozostaje `INSUFFICIENT`; zmienia się tylko powód, więc golden z takim
  celem przechodzi procedurę `e1-integracja.md` §10.6. Ścieżka `_local_decision` bez zmian:
  `[Erai-raws] Koori no Jouheki 2nd Season - 01` przy tym samym celu daje już `MATCH` („Specific work
  title and local episode match…”), a `Koori no Jouheki - 01` zostaje `A franchise alias does not
  identify this installment.` Testy (`test_episode_identity.py`):
  `test_entry_title_local_number_without_numbering` (213805-1, Erai → `zgodny`),
  `test_sxxexx_without_numbering_stays_uncertain` (`S02E01` romaji i angielski → `niepewny`,
  `is_conflict` fałsz).

### 5.4 `anishift/application/episode_releases.py` [NEW, czysty]

```python
SourceName = Literal["tsukihime", "nyaa", "nekobt", "knaben", "torrentio"]
NAME_PRIORITY: Final[tuple[SourceName, ...]] = ("tsukihime", "nyaa", "nekobt", "knaben", "torrentio")

def info_hash_hex(value: str) -> str | None                         # 40 hex lub base32 → hex, inaczej None

@dataclass(frozen=True, slots=True)
class ReleaseFile:
    path: str | None                    # spis: rzeczywista ścieżka w torrencie; Torrentio: druga linia tytułu
    filename: str | None                # Torrentio: behaviorHints.filename (niezależne od path); spis: None
    size: int | None
    from_listing: bool                  # ze spisu (TsukiHime/qBittorrent) czy rekord Torrentio
    file_index: int | None              # fileIdx Torrentio; spis: None

    def identity_candidate(self, release: str) -> dict[str, object]   # kontrakt classify/identity_evidence

@dataclass(frozen=True, slots=True)
class EpisodeRelease:
    info_hash: str
    name: str
    names: tuple[str, ...]              # wszystkie nazwy źródeł (RAW/HardSub, paczka)
    tags: tuple[str, ...]
    sources: frozenset[SourceName]
    seeders: int | None
    size_text: str | None
    files: tuple[ReleaseFile, ...]
    listing: bool                       # files pochodzi ze spisu
    file_hint: int | None               # fileIdx Torrentio
    declarations: tuple[LanguageDeclaration, ...]   # deklaracje plików (file = path) i wydania (file = None)
    torrent_id: int | None              # TsukiHime
    trackers: tuple[str, ...]

def merge_releases(streams: Sequence[StreamCandidate], listings: Mapping[str, TsukiHimeFiles],
                   *, pack_name: Callable[[str], bool]) -> tuple[EpisodeRelease, ...]
def is_pack(release: EpisodeRelease, *, pack_name: Callable[[str], bool]) -> bool
```

- **Pola H1 bez utraty (uwaga 7):** plik Torrentio zachowuje oryginalne `path = StreamCandidate.path`
  (`torrentio.py:110`) i `filename = StreamCandidate.file_name` (`behaviorHints.filename`, :108),
  więc `identity_candidate(release)` daje dokładnie dzisiejszy kandydat
  `{"release", "path", "filename"}` (`episode_selection.py:438`), a `identity_evidence` liczy
  `selected = filename or basename(path)` jak `conf_model.py:20–24`. Plik ze spisu ma
  `path` = rzeczywista ścieżka, `filename = None` (selected = ostatni człon ścieżki).
  `_attach_torrentio_file` wiąże rekord Torrentio z plikiem spisu, gdy `filename` (albo ostatni
  człon `path`) jest równy ostatniemu członowi dokładnie jednej ścieżki spisu; wtedy wiersz używa
  pliku spisu (ścieżka rzeczywista), a `file_index` i nazwa Torrentio zostają w nim jako podpowiedź.
  Bez jednoznacznego dopasowania plik Torrentio zostaje osobnym `ReleaseFile` z oryginalnymi polami.
- `TsukiHimeFiles` to czysty rekord aplikacji (`tuple[ListedFile, ...]`, `ListedFile(path, size,
  subtitle_languages, audio_languages)`) zdefiniowany tutaj; adapter TsukiHime go wypełnia
  (kierunek services → application jak dla `StreamCandidate`).
- Deklaracje TsukiHime z pliku spisu dostają `file = path`; `sublangs`/`audiolangs` wiersza listy
  odcinka i tagi nekoBT — `file = None`; język z nazwy pliku Torrentio i flaga PL — `file` = ścieżka
  pliku spisu dopasowanego po nazwie, gdy dopasowanie jest jednoznaczne (`_attach_torrentio_file`),
  inaczej ścieżka znanego pliku Torrentio.
- `pack_name` wstrzykuje `lambda n: parse_release_name(n).is_pack` (`names.py:119`, `types.py:38`)
  z warstwy wywołującej (`episode_search`), żeby moduł pozostał czysty — jedna reguła paczki.
- Wołają: `episode_search`, `episode_selection.rank_candidates`.

### 5.5 `anishift/application/episode_selection.py` [EDIT]

Istniejące: `StreamCandidate` (:251), `EpisodeKey`, `ReleaseFacts` (:276), `RankedCandidate` (:289),
`EpisodeOffer` (:298), `release_facts` (:415), `rank_candidates` (:434), `suggestion` (:448),
`_rank_key` (:624), `_resolution`, `_resolution_class`, `_container`.

- `StreamCandidate` dostaje pola z wartościami domyślnymi: `source: str = "torrentio"`,
  `subtitle_languages: tuple[str, ...] = ()`, `audio_languages: tuple[str, ...] = ()`,
  `language_tags: tuple[str, ...] = ()`, `file_count: int | None = None`, `torrent_id: int | None = None`.
  Typ nie jest trwały (stan ownera zapisuje `TorrentioReference`, `control.py:324`) — bez migracji.
- `RankedCandidate`: zostaje `stream` (reprezentant), `identity`; `facts` zastępują
  `traits: ReleaseTraits`, `quality: float`, `confidence: float | None` (None przy konflikcie),
  `conflict: bool`, `ambiguous: bool`, `release_name_only: bool`, `supported: bool | None`,
  `files: tuple[str, ...]`.
- `rank_candidates(target, releases: Sequence[EpisodeRelease], *, donghua: bool) -> tuple[RankedCandidate, ...]`
  — dla każdego znanego pliku: `classify` + `identity_evidence` na
  `file.identity_candidate(name)` (§5.4: oryginalne `release`, `path`, `filename`), `representative`,
  potem `release_traits(file=representative.path)`; bez pliku: `classify_release_name` i kandydat
  `{"release": name}`. Test `test_rank_torrentio_equivalent_to_conf_model`: odpowiedź Torrentio
  (fixtura) → `parse_streams` → `merge_releases` → `rank_candidates` daje te same werdykty co
  `classify` na `{"release", "path", "filename"}` i te same cechy co `conf_model.features()`,
  także gdy `filename` ≠ ostatni człon `path`.
- `streams_releases(streams) -> tuple[EpisodeRelease, ...]` = `merge_releases(streams, {}, pack_name=…)`
  — jedyna droga ze `StreamCandidate` do rankingu dla kodu sprzed K9/K12.
- `list_order`, `visible` (U-24), `suggestion(candidates, *, numbering: bool) -> tuple[int | None, bool]` (`numbering=False` → `(None, …)`, §5.9).
- **Numeracja odcinka (spec A §3.5, K9b):** `identity_target(graph, selected_id, mapping, number, *,
  numbering: bool = True)` (:333); `numbering=False` → wpis odcinka `{}` (bez `season`, `episode`,
  `absolute`, `episode_title`), reszta celu bez zmian. Nowa czysta
  `numbering_gap(mapping: AniZipMapping, number: int, tvdb_season: int | None, *, movie: bool) -> str | None` —
  **jedyna reguła numeracji celu**, wołana dla konkretnego numeru lokalnego; dla filmu (`movie=True`, format `MOVIE`) zawsze `None` (spec A §3.5: sugestia i automat jak dotąd); inaczej `"none"`, gdy brak
  klucza `str(number)` w `raw_episodes` albo wpis nie ma całkowitych `seasonNumber` i `episodeNumber`;
  `"duplicate"`, gdy tę samą parę ma niższy lokalny odcinek (najniższy zachowuje numerację);
  `"tvdb_season"`, gdy `seasonNumber` i `tvdb_season` są znane i różne; inaczej `None` (cel ma
  numerację). `tvdb_season=None` = bez kontroli sezonu. Testy: `test_numbering_gap_missing_key`
  (mapowanie tylko z odcinkiem 1, cel 2), `test_numbering_gap_without_season_episode` (172192-1),
  `test_numbering_gap_duplicate_keeps_lowest` (204389: odcinek 1 ma S02E01, odcinek 2 sprzeczny),
  `test_numbering_gap_tvdb_season` (198727), `test_numbering_gap_skips_movie` (21519-1: „Complete Movie” bez S/E → `None`), `test_identity_target_without_numbering`.
- **Sugestia (O-5, spec A §6.1:171):** indeks pierwszego wiersza grupy 1 `list_order` (bez konfliktu,
  nie sam dubbing) i `uncertain = verdict is not MATCH`; pusta grupa 1 → `(None, False)`. Zastępuje
  dzisiejsze szukanie najpierw `zgodnego` (`_SUGGESTED_VERDICTS`, :448–461). `D` bez podglądu bierze tę
  sugestię przez istniejące `_admit_download_offer` (`automation.py:5162–5168`) bez nowych reguł: tak
  jak dziś przy braku `zgodnego` przyjmuje `niepewny` z `confirmed=False` i werdyktem w wyborze,
  a odmawia (`NO_SUGGESTION`) przy braku sugestii, `MISMATCH` albo `supported is False`. Potwierdzenia
  R-04 dotyczą tylko ręcznego wyboru z listy (§5.10 pkt 7), jak dziś. Testy
  (`test_episode_selection.py`): `test_suggestion_is_first_group_one_row` (niepewny nad `zgodnym` →
  sugestia = niepewny), `test_suggestion_marks_uncertain`, `test_suggestion_skips_conflict_and_dub_only`,
  `test_suggestion_none_when_group_one_empty`; `test_automation.py::test_d_takes_uncertain_first_row`.
- Znikają: `ReleaseFacts`, `release_facts`, `_rank_key`. **Wszyscy konsumenci zmieniani w tym samym
  commicie (K6, uwaga 5):**
  - `acquisition.py:836` `prepare_episode` → `rank_candidates(target, streams_releases(streams), donghua=…)`;
    `prepare_episode` i `offer` działają tak do K12 (subskrypcja) i K9 (lista);
  - `acquisition_decisions.py` `offer_check` (:149–164) i `candidate_proposal` (:201–208): pole
    `facts` zastępują `traits`, `quality`, `confidence`, `conflict`, `supported` (te same pola co
    rejestr §6.6; K15 dopisuje tylko `sources`, `polish_history`, `blocker`);
  - `tests/application/test_acquisition_decisions.py:68–74` odtwarza ranking przez
    `streams_releases` i porównuje nowe pola zamiast `facts`;
  - `automation.py` (:3869–3871 przez `eligible`, :4806–4808, :4936, :4995 `facts.supported`, :5162),
    `subscription_targets.eligible` (:456–464, `facts.supported` → `supported`),
    `application/__init__.py` (:125, :283), `cli/interactive/anime.py` (:1146–1161, :1893, :2411).

### 5.6 `anishift/application/subscription_choice.py` [NEW, czysty]

```python
@dataclass(frozen=True, slots=True)
class ChoiceCandidate:                  # świadomie bez pewności (spec A §4, §6.2)
    info_hash: str
    file: str | None
    verdict: IdentityVerdict
    after_metadata: bool
    traits: ReleaseTraits
    quality: float
    pack: bool
    ambiguous: bool
    supported: bool
    taken: bool                         # plik przyjęty dla innego celu

class ReadOutcome(StrEnum):             # wynik odczytu TsukiHime (wyszukanie po hashu albo spis)
    LISTED = "listed"; EMPTY = "empty"; NO_HASH = "no_hash"                          # rozstrzygające / sukces
    PENDING = "pending"; RATE_LIMITED = "rate_limited"; FAILED = "failed"; TIMEOUT = "timeout"  # przejściowe

class Blocker(StrEnum): NONE, PENDING, THRESHOLD, NO_ADMISSIBLE, WAITING_POLISH, SOURCES_DOWN
class PolishHistory(StrEnum): PRESENT, ABSENT, UNKNOWN

def usable(candidate: ChoiceCandidate) -> bool
def admissible(candidate: ChoiceCandidate, *, excluded: Collection[str], threshold: int | None) -> bool
def choice_key(candidate: ChoiceCandidate) -> tuple[object, ...]
def completion_order(releases: Sequence[ChoiceCandidate]) -> tuple[str, ...]
def pending_blocks(pending: Collection[ChoiceCandidate], candidate: ChoiceCandidate) -> bool
def record_failures(failures: Sequence[ReadFailure], outcomes: Mapping[str, ReadOutcome], *,
                    tsukihime_down: bool, pending: Collection[str]) -> tuple[ReadFailure, ...]
def raise_threshold(threshold: int | None, dead: ResolutionClass) -> int
def polish_history(local_polish: bool, observation: PolishObservation | None) -> PolishHistory
def wait_until(due: datetime, history: PolishHistory, wait_h: int) -> datetime
def decide(candidates: Sequence[ChoiceCandidate], state: ChoiceState, now: datetime) -> ChoiceDecision
def replacement(candidates: Sequence[ChoiceCandidate], *, excluded: Collection[str]) -> ChoiceCandidate | None
```

- `record_failures`: `LISTED` usuwa wpis (wydanie dostało spis); `EMPTY`, `NO_HASH` → `decisive=True`;
  `PENDING`, `RATE_LIMITED`, `FAILED`, `TIMEOUT` → `transient += 1` najwyżej raz na sprawdzenie;
  `tsukihime_down=True` dolicza przejściowe każdemu oczekującemu spoza `outcomes`. Wynik jest
  zapisywany w `SubscriptionTarget.failures` w tym samym `_save` co wynik sprawdzenia.
- `ChoiceDecision`: `candidate: ChoiceCandidate | None`, `blocker: Blocker`, `reason: str`,
  `wait_until: datetime | None`.
- **„Pobierz teraz” (spec A §6.3:209):** `ChoiceState.skip_wait: bool` = pominięcie aktywne
  (`target.polish_skip.due == target.due_at`, §6.1). `decide` przy `skip_wait` pomija tylko czekanie na PL: bierze pierwszego
  `admissible` według `choice_key` (dopuszczalność, próg celu i `pending_blocks` bez zmian;
  `niepewny` odpada w `admissible`); bez kandydata zwraca blocker z §8 jak dziś, a cel zostaje
  należny. `wait_until` się nie zmienia. Testy (`test_subscription_choice.py`):
  `test_skip_wait_takes_first_admissible_without_polish`, `test_skip_wait_keeps_threshold_and_pending`,
  `test_skip_wait_never_uncertain`, `test_skip_wait_without_candidate_keeps_reason`,
  `test_skip_wait_expires_when_due_moves`.
- `replacement` = pierwszy `admissible` według `choice_key` bez czekania na PL i bez progu celu,
  z wykluczeniem całego hasha każdego wypróbowanego wydania (`excluded`); `niepewny` nigdy, bo
  `admissible` go odrzuca; brak → `None` (problem do ręcznego wyboru). Kontrakt i testy: §5.12.
- Stałe: `MAX_TRANSIENT_FAILURES: Final[int] = 3`, `UNKNOWN_WAIT_H: Final[int] = 2`,
  `ABSENT_AFTER_H: Final[int] = 24`, `SOURCES_DOWN_NOTICE_H: Final[int] = 1`.
- Zastępuje `eligible` (`subscription_targets.py:456`) i `candidate_pair` (:450).
- Wołają: `automation._subscription_outcome` (:3855), `automation._settled_target` (:4173,
  `raise_threshold`), `episode_search` (`completion_order`); `replacement` w A1 tylko testy, wywołanie
  dodaje E4 (§5.12).

### 5.7 `anishift/application/episode_search.py` [NEW, I/O]

Odpowiedzialność: jedyne miejsce, które odpytuje źródła dla odcinka, pilnuje budżetów i limitów
czasu, trzyma pamięć wyników i prowadzi kolejkę uzupełnień.

**Jeden kontrakt źródła (uwaga 4):** `EpisodeSearch` dostaje adaptery przez protokoły dopasowane
do ich naturalnych API; tłumaczenie `EpisodeRequest` na wywołania, konwersja typów, klasyfikacja
błędów i składanie stron odbywają się wyłącznie tutaj, w funkcjach `_<źródło>_answer`, które zawsze
zwracają `SourceResult`. Każde wywołanie adaptera to **jedno** żądanie (jedna strona, jedna
kategoria), więc wynik wcześniejszych wywołań nie ginie, gdy późniejsze zawiedzie.

```python
class StreamSource(Protocol): ...                     # istniejący, app/acquisition.py:195 (streams, movie_streams)
class TorrentSource(Protocol): ...                    # istniejący, app/acquisition.py:159: search(query, *, categories) -> tuple[Release, ...]
class PagedSource(Protocol):                          # Knaben, nekoBT
    def search(self, phrase: str, page: int) -> TextPage: ...
@dataclass(frozen=True, slots=True)
class TextPage:
    streams: tuple[StreamCandidate, ...]
    total: int | None                                 # znana liczba wyników; None = nieznana
class TsukiHimeApi(Protocol):
    def anime_id(self, anilist_id: int) -> int | None: ...
    def episode_page(self, anime_id: int, number: int, offset: int) -> TsukiHimePage: ...
    def torrent_by_hash(self, info_hash: str) -> TsukiHimeLookup: ...
    def torrent_files(self, torrent_id: int) -> TsukiHimeLookup: ...

@dataclass(frozen=True, slots=True)
class EpisodeRequest:
    key: EpisodeKey
    number: int                         # numer lokalny (MOVIE → 1)
    movie: bool
    donghua: bool
    kitsu_id: int | None
    tsukihime_id: int | None
    phrases: tuple[str, ...]
    target: Mapping[str, object]
    numbering: bool                     # False: brak numeracji odcinka albo numeracja sprzeczna (§3.5)

class SourceState(StrEnum): DONE, UNFINISHED, FAILED, DISABLED, SKIPPED, NO_TITLE, NO_KITSU
class FailureKind(StrEnum): TIMEOUT, RATE_LIMITED, ERROR

@dataclass(frozen=True, slots=True)
class SourceResult:
    source: SourceName
    state: SourceState                  # DONE = wszystkie zaplanowane wywołania udane (kompletny)
    streams: tuple[StreamCandidate, ...]  # przy UNFINISHED: wyniki wywołań udanych przed przerwaniem
    failure: FailureKind | None         # przyczyna FAILED/UNFINISHED
    detail: str | None                  # „403”, „timeout”

def failure_kind(error: BaseException) -> FailureKind

class EpisodeSearch:
    def __init__(self, *, torrentio: StreamSource, nyaa: TorrentSource, knaben: PagedSource, nekobt: PagedSource,
                 tsukihime: TsukiHimeApi, request_control: RequestControl, clock: Callable[[], float],
                 pack_name: Callable[[str], bool], source_timeout_s: float = SOURCE_TIMEOUT_S) -> None
    def manual_offer(self, request: EpisodeRequest, switches: SourceSwitches,
                     on_partial: Callable[[SearchSnapshot], None] | None = None) -> SearchOutcome
    def subscription_check(self, request: EpisodeRequest, switches: SourceSwitches,
                           failures: Sequence[ReadFailure], excluded: Collection[str]) -> SearchOutcome
    def previous_history(self, request: EpisodeRequest, switches: SourceSwitches) -> PolishObservation | None
    def forget(self, source: SourceName) -> None

def episode_phrases(candidate: TitleCandidate, context: SeasonContext, number: int, *, manual: bool,
                    absolute: int | None) -> tuple[str, ...]
def source_line(result: SourceResult) -> str
def offer_status(results: Sequence[SourceResult]) -> str | None
```

- Adaptacja Torrentio: `request.kitsu_id is None` → `NO_KITSU`; `request.movie` →
  `movie_streams(kitsu_id)`, inaczej `streams(kitsu_id, number)`.
- **Nyaa (uwaga 4c):** jedyne miejsce konwersji `Release` → `StreamCandidate` to
  `episode_search._release_stream(release)` (`source="nyaa"`, `release=title`, `info_hash`, `seeders`,
  `size_text`, język z `subtitle_language` jako deklaracja wydania). `_nyaa_answer` woła istniejące
  `TorrentSource.search(phrase, categories=(category,))` **osobno dla każdej kategorii**
  (`categories.py:17`), więc `NyaaSource` w `bootstrap.py:110–115` i `search_releases` zostają bez
  zmian, a wynik pierwszej kategorii przeżywa błąd drugiej (dziś `search_releases` traci go,
  `nyaa.py:131–141`). Scalanie po hashu robi `merge_releases`, nie adapter.
- **Klasyfikacja błędów (uwaga 4b):** adaptery dalej opakowują błędy w `TorrentSourceError`
  z zachowaną przyczyną (`raise … from error`: `torrentio.py:57–61`, `nyaa.py:159–160`; nowe adaptery
  tak samo; `nyaa.py:161–162` dostaje przyczynę `httpx.HTTPStatusError` z odpowiedzi, żeby status nie
  ginął). `failure_kind(error)` idzie łańcuchem `__cause__` (wzorzec `source_error`,
  `acquisition_decisions.py:167–181`, wspólny helper `http_status(error)`): `httpx.TimeoutException`
  (w tym `DeadlineExceeded`, §5.9) → `TIMEOUT`; `ProviderCooldown` (§5.9) albo status `429` →
  `RATE_LIMITED`; reszta → `ERROR`. `BudgetExhausted` (§5.9) kończy źródło jako `UNFINISHED` bez
  przyczyny awarii.
- **Kompletność (uwaga 4d):** źródło `DONE` tylko, gdy każde zaplanowane wywołanie (frazy × strony,
  kategorie) się udało; błąd po co najmniej jednym udanym wywołaniu → `UNFINISHED` + zebrane
  `streams` + `failure`; błąd pierwszego → `FAILED` (bez wyników). `DONE` z `()` = udany pusty wynik.
- **TsukiHime (uwaga 4a):** `TsukiHimeLookup` = `(status: int, torrent_id | files)` dla
  `200`/`202`/`404`/`429`; inne błędy adapter zgłasza `TorrentSourceError` z przyczyną. Wizyta
  kolejki = `torrent_by_hash` → przy `200` z ID **w tej samej wizycie** `torrent_files(id)`; `200`
  z ID to etap pośredni, nigdy `LISTED`/`EMPTY`. Wyjątek (O2, `a1-recon.md` N-1: 78/78 list
  identycznych): btih `200` z kompletnym `files` (`len(files) == filecount`, spec A §2) daje od razu
  pliki i kończy wizytę jednym odczytem (`LISTED`), bez `torrent_files`; budżet liczy rzeczywiste
  żądania. btih `200` z `files` pustym albo krótszym niż `filecount` → `torrent_files(id)` jak dotąd.
  btih `202` → `PENDING` także z niepustym `files` (to nie spis, O3); ID z `202` wolno zachować.
  `_listing_read` mapuje wynik ostatniego odczytu wizyty: spis `200` + kompletne pliki → `LISTED`,
  spis `200` pusto albo z listą krótszą niż `filecount` → `EMPTY` (brak spisu: wydanie oceniane po
  nazwie, bez potwierdzenia pliku, bez wpisu do `_ListingCache`), btih `404` → `NO_HASH`, `202`
  (btih albo spis) → `PENDING`, `429` → `RATE_LIMITED`, wyjątek → `failure_kind` (`TIMEOUT` /
  `RATE_LIMITED` / `ERROR` → `FAILED`).
- Testy od odpowiedzi lub wyjątku adaptera do `ReadOutcome` i trwałego licznika
  (`test_episode_search.py::test_source_outcome_end_to_end`, parametryzowany, `httpx.MockTransport`
  + prawdziwe adaptery + `RequestControl` + `record_failures` + `SubscriptionTarget.failures`):
  Torrentio `ReadTimeout` → `FAILED/TIMEOUT`; Nyaa: 1. kategoria `200`, 2. `ReadTimeout` →
  `UNFINISHED/TIMEOUT` z wynikami 1. kategorii; aktywny cooldown → `RATE_LIMITED`; Nyaa `429` →
  `RATE_LIMITED`; TsukiHime btih `200`+ID i spis `202` → `PENDING`, `transient` +1; btih `200`+ID
  i spis `200 []` → `EMPTY`, `decisive`; btih `404` → `NO_HASH`; spis `ReadTimeout` → `TIMEOUT`,
  `transient` +1; drugi taki odczyt w tym samym sprawdzeniu nie dolicza.
- Fan-out: `concurrent.futures.ThreadPoolExecutor`; każde źródło otwiera własny
  `request_control.scope(reason, limits, deadline_s=SOURCE_TIMEOUT_S)` **wewnątrz** swojego wątku
  (`ContextVar` nie przechodzi do wątku puli); `SOURCE_TIMEOUT_S: Final[float] = 30.0`, nadpisywane
  w konstruktorze w testach. Po `DeadlineExceeded` źródło kończy się `UNFINISHED/TIMEOUT` z wynikami
  zebranymi do tej chwili.
- `on_partial(SearchSnapshot)` po każdym zakończonym źródle i uzupełnieniu oraz **jednorazowo po
  `FIRST_SNAPSHOT_S: Final[float] = 3.0`** od startu, także gdy żadne źródło nie skończyło (uwaga 14):
  wtedy snapshot ma pusty ranking i wszystkie włączone źródła w `pending`, a lista pokazuje tylko
  linię „szukam jeszcze: …” bez wierszy. `SearchSnapshot` to pełny bieżący ranking i lista
  oczekujących źródeł (nie przyrost), więc scalanie zdarzeń po stronie IPC jest bezpieczne (§5.10).
  Testy: `test_manual_offer_snapshot_at_3s_without_results` (wszystkie źródła zablokowane, zegar
  i timer wstrzyknięte); `tests/cli/test_anime_episodes.py::test_offer_after_3s_pending_line_without_rows`.
- **Brak numeracji (uwaga 12, spec A §3.5 D2):** `numbering` = `numbering_gap(read.mapping, number,
  read.tvdb_season, movie=read.movie) is None` dla numeru celu (§5.5, §5.9), liczone raz przy budowie
  `EpisodeRequest` i razem z nim przekazywane do `identity_target`. `numbering=False` → cel H1 bez numeracji odcinka
  (`identity_target(..., numbering=False)`, §5.5), Torrentio `NO_KITSU` tylko przy braku Kitsu ID,
  pozostałe źródła odpytywane, ranking jak zwykle, `suggestion = None`, `offer_status` = „brak
  numeracji”. Subskrypcja wybiera jak zwykle (§5.6): przyjmuje tylko `zgodny`.
- Pamięć: `_FastCache` (≤30 min, P-10), `_PulledCache` (Knaben, nekoBT, 60 min),
  `_ListingCache` (spisy po hashu, tylko `LISTED`); `forget` przy wyłączeniu źródła.
- `CompletionQueue(order)`: ≤10 odczytów na wywołanie, wizyta = wyszukanie po hashu + spis
  (albo samo wyszukanie, gdy btih `200` ma kompletne `files`, `len(files) == filecount`, O2),
  przeliczanie kolejności po każdym uzupełnieniu. `manual_offer` używa porządku `list_order`,
  `subscription_check` — `completion_order` i trwałych `failures` (blokujące przed ponowieniami).
- `episode_phrases` zastępuje `_episode_queries` (`acquisition.py:1045`) i `_episode_base` (:1064);
  reuse `base_title` (`names.py:157`; dla OVA/SPECIAL pełny tytuł z podtytułem, W2) i reguły
  `season_context` (`acquisition.py:593`) liczonej na już pobranym grafie franczyzy, bez zapytań
  AniList (O6; `a1-recon.md` N-5: indeks zgodny 21/21, 0 zamiast 19 zapytań). Fraza `S01E{NN}`
  także w sezonie 1 TV (W1); OVA/SPECIAL bez `S{ss}E{NN}` (W2); MOVIE bez numeru jak dotąd.
- Wołają: `AcquisitionService.search_episode` i `subscription_check` (§5.9).

### 5.8 Adaptery `anishift/services/torrents/` [NEW]

- `tsukihime.py` — przeniesienie WIP z `%TEMP%\opencode\tsukihime-wip\tsukihime.py`:
  `TsukiHimeSource(client: httpx.Client)` implementuje `TsukiHimeApi`; `torrent_files` zwraca
  pliki z `filename`, `size`, `sublangs`, `audiolangs` (pola widoczne w `src_measure.py`) jako
  `TsukiHimeFiles`. `TSUKIHIME_URL: Final = "https://api.tsukihime.org/v1"`. `torrent_by_hash`
  używa `/torrents/btih/{btih}` (kształt: `a1-recon.md` N-1 — `200` z `id` i `files`, `202` z `id`,
  `404` przy braku; O2, O3). `episode_page` wysyła parametr `offset`, czyta `start` z odpowiedzi,
  `limit=100` (większy daje `422`; O4, N-2).
- `knaben.py` — `KnabenSource.search(phrase, page) -> TextPage` (`PagedSource`): `GET
  https://api.knaben.org/v2/search` z parametrami jak w nagraniu (`q`, `s=300`, `f=page × 300`,
  `o=date`, `dead`); pola `hash` (→ małe litery), `title`, `seeders`, `magnetUrl`, `total.value`
  (O1, N-3).
- `nekobt.py` — `NekoBTSource.search(phrase, page) -> TextPage` (`PagedSource`), `parse_feed(xml)`,
  `language_tags(text) -> NekoTags`: parser bloku `{Tags:…}` z sufiksu tytułu — `A=`, `F=`, `S=`,
  flagi bez `=` (`HS` = HardSub), sklejone kody regionalne (`es419`, `frfr`, `zhhans`) → język
  podstawowy, napisy = F ∪ S (O5, N-4); `seeders` i `infohash` z `torznab:attr`; reuse `xml.etree`
  i limit `MAX_BODY_BYTES` jak `nyaa.py:65`.
- Nyaa: bez nowego adaptera (§5.7); jedyna zmiana w `nyaa.py`: przyczyna `httpx.HTTPStatusError`
  przy statusie ≠ 200 (:161–162).
- Wszystkie: błąd → `TorrentSourceError` z zachowaną przyczyną (`raise … from error`), pusta
  odpowiedź → `()`.

### 5.9 Pozostałe `[EDIT]` w aplikacji i usługach

- `services/http_requests.py` — limit czasu operacji źródła z perspektywy wywołującego (spec A §3.2:59).
  Stan zastany: dołączający czeka `future.result()` bez limitu (:120–121), a timeouty httpx działają
  per odczyt gniazda, więc nie ograniczają całości. Kontrakt: **wywołujący czeka na wynik najwyżej
  `remaining`**; fizyczne żądanie działa ze stałymi timeoutami httpx i może przeżyć wywołującego
  najwyżej o nie (zaufane publiczne API, ograniczona pula — §10.1).
  - **Wyjątki:** `DeadlineExceeded(httpx.TimeoutException)`, `ProviderCooldown(httpx.TransportError)`
    (:143–145), `BudgetExhausted(httpx.TransportError)` (:159–161). Podtypy zachowują dzisiejsze
    łapanie `httpx.HTTPError` i pozwalają `failure_kind` (§5.7) rozróżnić przyczynę.
  - **Deadline:** `_Operation` (:41) dostaje `deadline: float | None` z `time.monotonic()`;
    `request_scope` (:52) i `RequestControl.scope` (:104) przyjmują `deadline_s: float | None`;
    zagnieżdżony scope nie zmienia operacji rodzica (jak dziś, :54–56).
  - **Czekanie:** `handle_request` (:108) w operacji z deadline'em: przed żądaniem `remaining <= 0`
    → `DeadlineExceeded` bez wysyłki; lider zleca `_admit` + `_send` (bez zmian) do wewnętrznej puli
    `ThreadPoolExecutor(max_workers=10)` przez `contextvars.copy_context().run`, więc w wątku puli
    `_charge` (:154) i `_send` (:164) widzą `_OPERATION` lidera (budżet i powód operacji lidera);
    lider i dołączający czekają `future.result(timeout=remaining)` **własnej** operacji
    i po przekroczeniu dostają `DeadlineExceeded` tylko dla siebie. Dołączający nie nalicza budżetu
    (jak dziś). Operacja bez deadline'u (qBittorrent, katalog) idzie jak dziś, w wątku wywołującego.
  - **Właściciel wspólnego `Future` (R4-4):** w ścieżce z pulą rozwiązanie `Future`
    (`set_result`/`set_exception`) i usunięcie wpisu `_active[key]` robi wyłącznie funkcja workera
    w puli, w swoim `finally` (dziś robi to wywołujący, :122–133). Timeout wywołującego nie dotyka ani
    `Future`, ani `_active`, więc dopóki żądanie trwa, nowy dołączający dostaje ten sam wynik.
    Test `test_follower_joins_after_leader_timeout` (lider timeoutuje → transport dalej wisi → nowy
    dołączający → transport zwolniony → dołączający dostaje wynik, transport wywołany raz).
  - `RequestControl.close()` (:135) zamyka pulę (`shutdown(wait=False, cancel_futures=True)`), potem
    transport.
  - `_provider` (:194) rozpoznaje `api.tsukihime.org`, `api.knaben.org`, `nekobt.to`; okna
    przesuwne TsukiHime (25/10 s, 60/30 s, 100/min) obok `REMOTE_INTERVAL_S` (:36).
  - **Zebrane wyniki:** każde wywołanie adaptera to jedno żądanie (§5.7), więc `DeadlineExceeded`
    przerywa tylko bieżące; `_<źródło>_answer` zwraca wyniki wcześniejszych jako `UNFINISHED/TIMEOUT`.
  - Testy (`tests/services/test_http_requests.py`, transport wstrzymywany na `threading.Event`):
    `test_deadline_caller_times_out_while_transport_hangs` (deadline 0,2 s, transport wisi →
    `DeadlineExceeded` ≤ 0,45 s); `test_deadline_follower_shorter_ends_alone` (dołączający 0,2 s dostaje
    timeout, lider 2 s dostaje wynik po zwolnieniu transportu); `test_deadline_expired_before_request_not_sent`;
    `test_budget_through_both_pools` (limit 1 na dostawcę, dwa fizyczne żądania w jednej operacji
    przez pulę `EpisodeSearch` i pulę `RequestControl` → drugie `BudgetExhausted`, `counts()` ma powód
    operacji, nie `user`); `test_follower_not_charged`; `test_cooldown_and_budget_error_types`; oraz
    `test_episode_search.py::test_source_timeout_keeps_partial` (strona 1 udana, strona 2 przekracza
    deadline → `UNFINISHED/TIMEOUT` z wynikami strony 1).
- `services/catalog/anilist.py` — `countryOfOrigin` w polach wyszukiwania (:61) i `_FRANCHISE_FIELDS`
  (:101); `_candidate` (:370) ustawia `country`. `services/catalog/types.py` — `TitleCandidate`
  (:62) `country: str | None = None` (wartość domyślna: zapisane fixtury AniList bez pola dają `None`).
- `services/torrents/names.py:90` — `_DUBBED_RE` zastąpiony importem `DUBBED_RE` z `release_quality`.
- `services/torrents/torrentio.py:79` `_stream` — `source="torrentio"`; bez innych zmian.
- `bootstrap.py:90` `_acquisition_service` — pięć adapterów na wspólnym `httpx.Client`
  z `RequestControl`, `EpisodeSearch` przekazany do `AcquisitionService`.
- `acquisition.py`:
  - `AcquisitionService.__init__` (:508) dostaje `episode_search`;
  - K9: `search_episode(key, switches, on_partial=None) -> tuple[EpisodeOffer, dict[str, object]]`
    dla oferty (`automation.py:4878`), `D` (`automation.py:5140`) i `offer` (:810, IPC `automation.py:8383`),
    na mapowaniu i `tvdb_season` z `ListingRead` (niżej), bez drugiego odczytu ani.zip;
  - **brak numeracji już na odczycie listy (uwaga 12, F):** `ListingRead` (:381) dostaje
    `tvdb_season: int | None` (z mostu) i `numbering_source`; numeracja konkretnego celu to zawsze
    `numbering_gap(read.mapping, number, read.tvdb_season, movie=read.movie)` (§5.5), bez flagi dla całego wpisu;
    `ListingRead.movie` = format wpisu `MOVIE`; `read_listing` go nie zna (`SeasonAiring` nie ma formatu), więc przed `numbering_gap` liczy go jak `acquisition.py:819–822`: `self._context_graph(anilist_id, now).nodes[anilist_id].get("format") == _MOVIE_FORMAT`
    i ten sam, z którego powstaje `EpisodeRequest.movie` — jedno źródło dla wszystkich wywołań.
    `read_listing` (:777) przy
    błędzie ani.zip bez `saved` nie zgłasza wyjątku (dziś :784–786), tylko bierze pusty
    `AniZipMapping` — ten sam co ani.zip `404` (`services/catalog/anizip.py:49–50`) — więc oba
    przypadki dają cel bez numeracji niezależnie od wyjątku; lista odcinków powstaje z harmonogramu
    AniList (`episode_listing`, `episode_selection.py:363–412`, działa bez mapowania). Mapowanie bez
    odcinków nie jest żywe (`live = fetched and bool(mapping.raw_episodes)`), więc `404` nie nadpisuje zapisanego.
    Konsumenci: `episodes` (:773), oferta (`automation.py:4871–4878`) i `D` (:5135–5140) wołają
    `read_listing` i przekazują wynik do `search_episode` → `EpisodeRequest(numbering=…)` dla numeru celu (§5.7);
    subskrypcja (`automation.py:3770–3773`) przy `numbering=False` nie liczy błędu źródła i wybiera
    zwykłą drogą §5.6 na celu bez numeracji (spec A §3.5 D2; bez osobnego blokera); brak
    przyjmowalnego wydania daje zwykły bloker §5.6 i powód §8. Testy od
    ownera przez `ResidentSession`, parametryzowane po pięciu przypadkach celu bez numeracji: ani.zip
    `500` i `404` bez zapisanego mapowania, brak klucza celu przy niepustym mapowaniu (odcinek 2 przy
    mapowaniu z samym 1), wpis celu bez `seasonNumber`/`episodeNumber` (172192-1), odcinek sprzeczny
    (204389-2, przy pełnej numeracji odcinka 1 — kontrola: odcinek 1 ma sugestię)
    (MockTransport, arm-server bez AniDB ID): `t/app/test_automation.py::test_offer_without_numbering_shows_releases`
    (wiersze widoczne, `suggestion is None`, „brak numeracji”, Torrentio `NO_KITSU`),
    `::test_d_without_numbering_does_not_admit`, `test_subscription_owner.py::test_no_numbering_decides_on_entry_title`
    (wydanie z tytułem wpisu i numerem lokalnym przyjęte; samo `SxxExx` bez przyjęcia, brak wpisu
    w `failures`, kolejne sprawdzenie zaplanowane), oraz
    `t/app/test_acquisition.py::test_read_listing_404_does_not_replace_saved_mapping`;
  - **mosty numeracji i ID (spec A §3.1, §3.5 D1–D3, K9b):** `read_listing` (:777) po `_mapping`
    (:866) woła `_bridged_mapping(anilist_id, mapping)`:
    1. `ArmCatalog.ids(anilist_id) -> ArmIds(anidb_id: int | None, tvdb_season: int | None)` przy
       każdym odczycie (`GET https://arm.haglund.dev/api/v2/ids?source=anilist&id={id}`; `404` → oba
       `None`);
    2. puste `mapping.episodes` i znane `anidb_id` → `AniZipCatalog.mapping_by_anidb(anidb_id)`
       (`GET https://api.ani.zip/mappings?anidb_id={id}`, ten sam `parse_mapping`); jego `episodes`,
       `specials`, `raw_episodes`, `episode_count` zastępują puste, a `kitsu_id`/`catalog_type`
       zostają z pierwszego odczytu, gdy odpowiedź AniDB ma `null`;
    3. `kitsu_id is None` → `KitsuCatalog.kitsu_id(anilist_id)`: `GET
       https://kitsu.io/api/edge/mappings?filter[externalSite]=anilist/anime&filter[externalId]={id}&include=item&page[limit]=20`;
       dokładnie jeden `item` typu `anime`, potem `GET /anime/{kitsu}/mappings?page[limit]=20` musi
       zawierać `anilist/anime` = ten AniList ID. Każdy z dwóch odczytów musi być kompletny (bez
       `links.next`); inaczej, przy niejednoznaczności albo błędzie → `None` (Kitsu nieustalone),
       bez dalszych stron, najwyżej 2 żądania.

    Wynik jest zwykłym `AniZipMapping` (bez nowych pól i bez zmiany schematu `watch_state`), więc
    numeracja z AniDB jest zapisywana i porównywana w `merge_listing` (K11) jak ta z ani.zip.
    `ListingRead` dostaje `tvdb_season = ids.tvdb_season` i `numbering_source: str` (`anilist` /
    `anidb` / `none`); rejestr (§6.6) zapisuje `numbering_source` celu z numeracją, inaczej wynik
    `numbering_gap`. Błąd mostu (`TitleCatalogError`, `httpx.HTTPError`, `ValueError`) jest logowany
    (`provider`, `code`) i odbiera tylko swój krok. Bez pamięci w ownerze i bez osobnego
    harmonogramu: każde sprawdzenie czyta od nowa (D3). `_mapping` (:866) zachowuje dzisiejszą pamięć
    `max_age_s` dla pierwszego odczytu, z jednym wyjątkiem: `read_listing(anilist_id, saved, *,
    targets: Collection[int] = ())` — sprawdzenie subskrypcji podaje numery sprawdzanych celów,
    a gdy mapowanie z pamięci daje któremuś `numbering_gap(mapping, n, tvdb_season, movie=read.movie) is not None`, ani.zip jest czytane
    od nowa (jedno żądanie zamiast odpowiedzi z pamięci, budżet bez zmian). Lista i `D` pamięć
    zachowują. Dostawcy `arm` i `kitsu` w `http_requests._provider`
    (:194) i `RequestControl`. Testy (`t/app/test_acquisition.py`): `test_numbering_falls_back_to_anidb` (213805: puste
    `episodes`, arm → AniDB 20168, ani.zip po AniDB → S02E01, `kitsu_id` 50827 zachowany),
    `test_anidb_nulls_do_not_overwrite_ids`, `test_bridge_failure_keeps_anilist_mapping` (arm `500`,
    Kitsu `404`), `test_listing_bridge_requests_within_budget` (najwyżej 5 żądań, spec A §3.1),
    `test_subscription_read_bypasses_mapping_cache` (parametryzowany: puste `episodes` i odcinek
    sprzeczny; drugie sprawdzenie przed `max_age_s` robi nowy odczyt ani.zip, a cel z numeracją
    korzysta z pamięci), `t/services/catalog/test_kitsu.py::test_kitsu_candidate_with_next_link_is_unresolved`,
    `::test_kitsu_incomplete_reverse_is_unresolved`, `::test_kitsu_ambiguous_is_unresolved`,
    `::test_kitsu_request_count` (dokładnie 2 żądania, żadnej kolejnej strony),
    oraz `test_subscription_owner.py::test_numbering_appears_on_next_check` (drugie sprawdzenie
    z pełną numeracją bez restartu);
  - **numeracja do końca przetwarzania oferty (R4-2):** `EpisodeOffer` dostaje `numbering: bool = True`
    ustawiane przez `search_episode` z `EpisodeRequest.numbering` tego celu (ta sama wartość co w celu H1); jedyne miejsce wyliczania sugestii to
    `episode_selection.suggestion(candidates, *, numbering)` (§5.5) → brak sugestii przy `numbering=False`. Wołają je
    `search_episode` i `_repeat_episode_offer` (`automation.py:4932–4936`, z `offer.numbering`), więc
    ponowienie oferty (:4923) i `D` legacy (:5160–5162) nie odtwarzają sugestii bez numeracji. Test
    `t/app/test_automation.py::test_repeat_without_numbering_has_no_suggestion` (te same pięć
    przypadków co wyżej, wcześniejsze przyjęcie odcinka + nowe niewykluczone wydanie → oferta
    ponowienia bez sugestii, `D` bez przyjęcia);
  - K12: `subscription_check(key, mapping, record_state) -> SubscriptionSearch` zastępuje
    `prepare_episode` w subskrypcji (`automation.py:3781`); `prepare_episode` (:814) znika;
  - K11: `read_listing` (:777) uznaje mapowanie za żywe bez Kitsu (`live = fetched and bool(mapping.raw_episodes)`).
- `subscription_targets.py` — `SubscriptionTarget` (:128) i `SubscriptionRecord` (:180) nowe pola
  (§6.1); inwariant (:220–222) zastąpiony „`kitsu_id` wymaga mapowania”; `excluded(target) ->
  frozenset[str]` (hash z kluczy `hash` i starych `hash:fileIdx`); usunięte `eligible` (:456),
  `candidate_pair` (:450) w K12.
  **Konflikt numeracji niezależny od Kitsu (K11, R6-1):** dziś `merge_listing` wykrywa konflikt
  tylko po zmianie `kitsu_id` (:368–370), a przy `read.live` zastępuje mapowanie bez porównania
  (:387–393). Spec A :91 i `e1-przeplyw-subskrypcji.md:182`: zmiana numeracji to konflikt, który
  blokuje nowe próby i zachowuje dotychczasową numerację. Zmiana: przy `read.live` i zapisanym
  `record.mapping` dla każdego klucza `raw_episodes` zapisanego mapowania porównywana jest trójka
  `(seasonNumber, episodeNumber, absoluteEpisodeNumber)` — dokładnie pola, które `identity_target`
  bierze do celu H1 (`episode_selection.py:343–350`) — z tym samym kluczem nowego mapowania
  (brak klucza = trójka `None`). Porównywane są tylko odcinki, które w zapisanym mapowaniu miały
  numerację: `numbering_gap(record.mapping, n, record.mapping_tvdb_season, movie=read.movie) is None` (§5.5, spec A §3.5) —
  zapisane mapowanie oceniane jest sezonem mostu z odczytu, który je zapisał, nie bieżącym; `None`
  (nieznany, także po migracji 4 → 5) = tylko S/E i duplikaty, jak przy braku mostu. Gdy mapowanie
  się aktualizuje, `mapping_tvdb_season = read.tvdb_season`; przy konflikcie oba pola zostają.
  Odcinek bez numeracji albo sprzeczny w zapisanym mapowaniu może dostać dowolną nową trójkę bez
  konfliktu (uzupełnienie z `None`, naprawa duplikatu), a u odcinka z numeracją pole `None`
  w zapisanym, które dostaje wartość, też nie jest zmianą. Różnica znanego pola → `replace(record, problem=CATALOG_CONFLICT)` bez zmiany
  mapowania (jak :370). Klucz `kitsu_id` X → Y nadal jest konfliktem (:369); X → `None` przy
  niezmienionej numeracji nie jest: mapowanie się aktualizuje, `kitsu_id=None` wyłącza tylko
  Torrentio. Nowy klucz odcinka, tytuł (`title`) i data (`airDateUtc`, `anizip.py:82`) nie wchodzą do porównania.
  Owner nie szuka przy konflikcie (`_searchable`, `automation.py:8298–8299`), a `problem` jest
  trwały, więc blokada przeżywa restart; konflikt znika jak dziś (:393), gdy kolejny żywy odczyt
  ma znów tę samą numerację. Testy (`test_subscription_targets.py`):
  `test_numbering_change_without_kitsu_is_conflict` (`kitsu_id=None`, inny `absoluteEpisodeNumber`
  odcinka 3), `test_numbering_change_same_kitsu_is_conflict`, `test_added_episode_or_title_date_not_conflict`,
  `test_kitsu_disappears_same_numbering_not_conflict` (mapowanie zaktualizowane, `kitsu_id is None`),
  `test_conflict_keeps_previous_mapping`, `test_numbering_filled_from_none_not_conflict`,
  `test_duplicate_repaired_not_conflict`, `test_saved_season_mismatch_then_fixed_without_bridge_not_conflict`
  (A: zapisane S01E01 przy `mapping_tvdb_season=2`, nowe S02E01 przy niedostępnym moście),
  `test_saved_numbering_change_with_new_bridge_season_is_conflict` (B: zapisane S01E01 przy
  `mapping_tvdb_season=1`, nowe S02E01 przy moście S02); `test_subscription_owner.py::test_numbering_conflict_blocks_attempts_after_restart`
  (zmiana numeracji odcinka, który ją miał → brak przyjęcia → restart ownera → nadal brak przyjęcia),
  `::test_numbering_filled_after_restart_not_conflict` (parametryzowany: `None` → pełna, duplikat →
  poprawna; zapis, restart ownera, żywy odczyt → mapowanie zaktualizowane, bez `CATALOG_CONFLICT`,
  przyjęcie możliwe), `::test_bridge_season_scenarios_after_restart` (A i B: zapis z sezonem mostu,
  restart ownera, żywy odczyt → A bez konfliktu, B `CATALOG_CONFLICT` i brak przyjęcia).
- `control.py` — `WATCH_STATE_SCHEMA_VERSION = 5` (:90); domyślne `transfer_stall_s = 600`;
  `EpisodeChoice` (:347) `traits: ChoiceTraits | None = None`; `EpisodeAssignment` (:412)
  opcjonalne `stopped: str | None`; `compact_acquisition` (:662)
  zachowuje `choice.traits` (czyści tylko to, co dziś).
- `watch_state.py` — §6.2.
- `subscription_migration.py` — `migrate` (:53) ustawia `schema_version=_SCHEMA_FOUR` zamiast
  `WATCH_STATE_SCHEMA_VERSION` (:80); nowe `migrate_to_five(state) -> WatchState`.
- `transfers.py` — `metadata_check(files, assignment, target, taken) -> MetadataCheck` obok
  `episode_files` (:360); reuse `classify`, `subscription_choice.usable` i `choice.traits`.
  **Niejednoznaczny plik w ścieżce ręcznej (K13, R6-2):** `episode_files` (:360–386) dziś zwraca
  plik o unikalnej nazwie reprezentanta (:368–372), zanim policzy pliki zgodne H1, więc
  `Example E01 [1080p].mkv` i `Example E01 [720p].mkv` (oba `MATCH`) dają automatycznie plik
  reprezentanta, a `_settle_selection` (`automation.py:5740–5753`) startuje treść; spec A :83
  wymaga wtedy ręcznego wyboru (U-18c). Zmiana w jednym miejscu: `matched` liczone najpierw;
  `len(matched) > 1` → `()`; dopiero potem skrót po unikalnej nazwie i pojedyncze `matched`.
  Pusty wynik zostawia przypisanie niezmapowane (`_episode_bindings`, :8020–8045), czyli istniejący
  stan U-18c: treść nie startuje, a spis qB jest liczony od nowa po restarcie — bez nowego stanu.
  Jawny wybór (`episode_file_choose`) mapuje przypisanie, więc `_episode_bindings` go pomija (:8027).
  Bez zmian: jeden zgodny plik (z nazwą reprezentanta albo bez), paczka wybrana ręcznie z jednym
  zgodnym plikiem odcinka, przypisania już zmapowane. Testy: `test_transfers.py::test_episode_files_two_matches_ambiguous`,
  `::test_episode_files_single_match_unchanged`, `::test_episode_files_pack_single_match_unchanged`,
  `::test_episode_files_unique_name_without_other_match`; `test_automation.py::test_manual_ambiguous_file_waits_for_u18c`
  (ręczny wybór → metadane z dwoma zgodnymi → brak startu, `episode_files` oferuje oba → restart →
  nadal czeka → `episode_file_choose` → start wybranego pliku).
- `automation.py` (wybór i rozliczenie — uwaga 5):
  - wybór: `_subscription_outcome` (:3855) — `eligible` (:3869–3871) zastępuje
    `subscription_choice.decide` na wyniku `subscription_check`; `ChoiceCandidate.taken` z jednej
    projekcji chronionych plików (niżej) i wybranych w tej rundzie;
  - **ochrona pliku (uwaga 11, spec A §6.2 „Wykluczenie i tożsamość próby”):** `_taken_pairs`
    (:3919–3927, klucz `hash:fileIdx` z `reference.file_index`) zastępuje czyste
    `subscription_choice.protected_files(acquisitions, except_key) -> frozenset[tuple[str, str | None]]`:
    dla każdego `protected_assignments` innego celu para `(hash, ścieżka qBittorrenta)` z
    `assignment.files` (`FileReservation`, `control.py:421`) i `video_path` (:426, przeżywa
    kompaktowanie); przypisanie bez znanej ścieżki daje `(hash, None)` = chroniony cały hash do
    czasu poznania pliku. `is_taken(hash, path, protected)` (ścieżki porównywane po `casefold`):
    `(hash, None) in protected` albo `(hash, path) in protected`; kandydat bez znanej ścieżki jest
    zajęty, gdy hash ma jakikolwiek chroniony plik. Konsumenci: `_subscription_outcome` (przed
    wyborem, ścieżka reprezentanta) i `transfers.metadata_check` (po metadanych, ścieżka z qB).
    Wykluczenie całego hasha (`excluded`) dotyczy tylko celu, który go wypróbował. Testy
    (`test_subscription_choice.py`): `test_protected_same_path_different_file_index_taken`,
    `test_protected_other_path_same_hash_not_taken`, `test_protected_unbound_assignment_protects_hash`,
    `test_protected_survives_compaction_via_video_path`, `test_tried_hash_excluded_only_for_own_target`;
    `test_transfers.py::test_metadata_check_uses_protected_paths`;
  - przyjęcie: `_admit_attempt` (:3947) — `started += 1`, `tried += (hash,)`, polecenie
    `sub:{id}:{n}:{started}` (:3973), `attempts += 1`; `_attempt_previous` (:3964) bez zmian;
  - rozliczenie: `_settled_target` (:4173) — martwa próba (definicja niżej) podnosi `threshold`
    z `choice.traits.resolution`; zatrzymanie po metadanych zwraca `attempts`;
  - **martwa próba (fakt, spec A §6.5, przejście 11; spec A §6.2 „Próg celu”):** próba automatu
    bez przyrostu pobranych bajtów przez 10 min, także bez metadanych (timeout metadanych =
    10 min); czas pauzy się nie liczy. **Nie są martwe i nie ustawiają progu:** `failed`, `removed`,
    odrzucenie przez kontrolę (H2, U-07/U-08), zatrzymanie po metadanych (paczka, niejednoznaczny
    plik);
  - bramka startu treści: `_may_start_selection` (:5873) → `_replacement_ready` (:5883) bez zmian;
  - po metadanych: `_settle_selection` (:5717) woła `metadata_check` i `_stop_after_metadata`;
    `METADATA_TIMEOUT_S` (:410) = 600;
  - oferta: `_episode_offer` (:4851), `_store_episode_offer` (:4909), wybór (:4967–5000) — §5.10;
  - **zamykanie (C):** praca oferty jest w `_active_io` (§5.10 pkt 1), więc `_drained` (:1072–1075)
    czeka na nią najdłużej do limitu źródeł. Callback cooldownu z transportu
    (`_restore_provider_locks`, :4500–4503) dziś czeka na pętlę (`_on_owner`, :1108–1118: `future.result()`
    bez limitu), więc spóźnione `429` po zatrzymaniu pętli blokuje wątek na zawsze. Zmiana: callback
    tylko wstawia `partial(self._persist_provider_lock, provider, until)` do `_queue` i nie czeka;
    `_persist_provider_lock` woła `_save_provider_lock` (:4505) i łapie jego `OSError` (problem już
    zapisany w `_subscriptions_problem`). Wpis wstawiony po zatrzymaniu pętli nie jest obsłużony:
    cooldown zostaje tylko w pamięci `RequestControl` (bez zapisu na dysk) — dopuszczalne, bo
    rezydent i tak się kończy. `run()` (:964–968) po `self._pool.shutdown(wait=True)` woła
    `request_control.close()` (§5.9). Test `test_automation.py::test_shutdown_with_blocked_source_and_late_429`:
    oferta z zablokowanym źródłem (`source_timeout_s=0,5`), w trakcie `shutdown`, potem transport
    oddaje `429` z `Retry-After` → `run()` wraca ≤ 2 s i żaden wątek nie czeka na pętlę;
  - `_episode_choice` (:7725) zapisuje `ChoiceTraits` z `candidate.traits`;
  - `_check_basis` (:5981) i `_reject_attempt` (:6118) bez zmian (H2 tylko dla subskrypcji);
  - `_record_decision` (:5296) z nowymi polami; powiadomienia przez `NotificationKey`.
  - **„Pobierz teraz” (K14, spec A §6.3:209):** bez nowego polecenia IPC — istniejące
    `subscription_check` (:3548 → `_request_subscription_check`, :3654–3668), które już zapisuje
    stan przez `_commit` i uruchamia sprawdzenie `manual=True` (:3667), dostaje opcjonalne `number`
    w ładunku. Z `number`: odmowa (`REFUSED`, „cel nie czeka na PL”), gdy cel nie jest należny albo
    nie czeka na PL; inaczej w tym samym `_commit` cel dostaje `polish_skip = {"due": due_at, "at":
    self._clock(), "settled": False}`, a do rejestru decyzji idzie wpis `action = "skip_polish_wait"` (§6.6). Sprawdzenie
    bierze cel jak każdy należny i woła `decide` ze `skip_wait=True` (§5.6). Bez `number` polecenie
    działa jak dziś („Szukaj teraz”).
    **Gwarancja sprawdzenia (R9-1):** samo `_request_subscription_check` nie wystarcza — przy
    trwającym sprawdzeniu nie startuje nowego (:3660–3667), worker ma wcześniejszy snapshot
    (:3762–3767), a po restarcie harmonogram liczy od `checked_at` (U-14). Dlatego źródłem prawdy jest
    stan celu: `subscription_targets.next_search_at` (:398–415) dla celu z **nierozliczonym**
    pominięciem (§6.1) zwraca `polish_skip.at` (≤ teraz), więc `search_targets` (:418–425) i
    `next_check_at` (:428, :446) widzą cel jako natychmiast należny. Po zakończeniu bieżącej rundy
    `_subscriptions_checked` → `_schedule_subscriptions` (:3743–3746) i po restarcie harmonogram
    planuje sprawdzenie od razu; jeden worker na subskrypcję zostaje (`_subscription_checks`,
    :3708). **Rozliczenie (R10-1, dowód ze snapshotu, bez porównań czasu):** worker bierze snapshot
    (:3762–3764) przed odczytem zegara (:3767–3768), więc `checked_at` nie dowodzi, że runda widziała
    akcję. Dlatego `_SubscriptionRead` (:644) dostaje pole `searched: tuple[tuple[int, PolishSkip |
    None], ...]` — numer i `polish_skip` z podglądu snapshotu dla każdego celu sprawdzonego w pętli
    :3778–3787 (dopisywane razem z `offers.append`). `_finish_subscription_check` (:3798) przy
    `failure is None` ustawia `settled = True` tylko tym celom, których bieżące `polish_skip` jest
    nierozliczone i równe wartości (`due`, `at`) z `searched` — w tym samym zapisie co przyjęcie albo
    wynik bez kandydata. Runda ze snapshotem sprzed akcji, runda bez tego celu i runda z błędem źródeł
    nie rozliczają. Po rozliczeniu cel wraca do siatki U-14, a `skip_wait` dla tego `due_at` nadal
    obowiązuje. Testy (`test_subscription_owner.py`):
    `test_download_now_admits_first_admissible_without_polish`, `test_download_now_only_this_target`
    (inny czekający cel dalej czeka), `test_download_now_while_other_check_running` (worker innego
    celu tej subskrypcji wstrzymany na `Event` → `T` dla E6 → po zwolnieniu E6 sprawdzony bez
    przesuwania zegara, jeden worker naraz), `test_download_now_between_snapshot_and_clock` (worker
    zatrzymany po snapshocie, przed odczytem zegara → `T` dla E6 → runda bez E6 → `settled is false`
    → E6 sprawdzony w następnej rundzie bez siatki U-14), `test_download_now_settles_with_equal_clock`
    (zegar testowy stoi: akcja i runda w tej samej chwili → rozliczenie po rundzie z E6),
    `test_download_now_survives_restart` (zapis akcji → restart przed sprawdzeniem → sprawdzenie od
    razu, przyjęcie bez czekania; po rozliczeniu i restarcie `settled` zostaje),
    `test_download_now_no_double_admission`, `test_download_now_settled_returns_to_grid` (po wyniku bez
    kandydata następne sprawdzenie wg U-14, nadal bez czekania na PL),
    `test_download_now_without_candidate_stays_due` (powód §8, brak przyjęcia),
    `test_download_now_expires_with_new_due`, `test_download_now_refused_when_not_waiting`,
    `test_download_now_recorded_in_decisions`; `test_subscription_targets.py::test_next_search_at_unsettled_skip_is_now`.
  - **Stan PL celu w panelu (R9-2):** istniejąca projekcja `episode_states` (`_target_status`,
    :4671–4684) dla należnego celu dopisuje do `EpisodeStatus` `polish_wait_until: str | None`
    (ISO, gdy cel czeka na PL: `subscription_choice.wait_until(due_at, polish_history(lokalny dowód,
    target.polish), polish_wait_h) > now` i bez aktywnego pominięcia) oraz `polish_skipped: bool`
    (pominięcie aktywne).
    **Odświeżenie (R10-2, R13):** `_status()` (:1657–1661) nie zawiera stanu celów, a panel odświeża
    `episode_states` tylko przy `payload != self._snapshot` (`state.py:984–986`). Owner dokłada do
    `_status()` jedną liczbę `subscriptions_revision` (atrybut ownera w pamięci, start 0; nie trafia do
    `state.json`). Jedyne miejsce zwiększania: `_save` (:7057–7075), po `self._state = candidate`
    (:7070), gdy `candidate.subscriptions != previous.subscriptions` — tam przechodzą wszystkie zapisy
    stanu celów: akcja `T` (`_request_subscription_check` → `_commit` → `_save`, :7053), rozliczenie
    i obserwacja PL w `_finish_subscription_check` (`_save`, :3824–3831), zmiany subskrypcji
    (`_commit_subscriptions`, :3597–3598) i zamknięcie celów przez `_settled_targets` (:4127–4170,
    wołane w `_save`, :7060). Zapis transferów bez zmiany `subscriptions` (`_record_transfers`, :6276)
    rewizji nie zmienia. Rewizja gwarantuje odświeżenie przy zmianie stanu celów; nie jest filtrem —
    bramka nadal porównuje cały payload, więc zmiany innych pól statusu (postęp transferu, liczniki
    HTTP, `automation.py:1662–1665`, :1690–1692) wyzwalają pełny odczyt jak dziś (zachowanie istniejące,
    nie regresja A1). Ścieżka bez zapisu (`_commit` dla niemutujących, :7049–7051) nie zmienia subskrypcji.
    Publikacja: `_request_subscription_check` po zapisie `polish_skip` woła `_publish_state()` (dziś
    nie publikuje); rozliczenie już kończy się `_publish_state()` (:3853). Panel bez zmian w bramce
    i w odczycie: zmieniona rewizja daje `payload != snapshot` → istniejące `refresh_episode_states`
    → istniejący pełny `_read_episode_states` (:1786–1803). Po odmowie `T` (cel już nie czeka, §5.9)
    panel woła raz istniejące `refresh_episode_states`. Koszt: pełny odczyt to do ~20 porcji
    `episode_states` przy 2000 celów, przy każdej zmianie payloadu statusu — tak samo jak dziś; A1
    dokłada tylko odczyty przy zmianie stanu celów — ryzyko w §10. Testy:
    `tests/cli/test_subscriptions_panel.py::test_polish_state_per_target` (owner → ładunek → panel: dwa
    cele, „Czeka na PL do HH:MM” i „Pobieram bez czekania na PL”; `T` tylko dla czekającego),
    `::test_polish_state_refreshes_on_revision` (dwa `state_changed` różniące się tylko
    `subscriptions_revision` → panel ponownie czyta `episode_states`; `T` znika, wiersz pokazuje
    „Pobieram bez czekania na PL”), `::test_download_now_refusal_refreshes` (odmowa `T` → jeden
    odczyt `episode_states`) oraz `test_subscription_owner.py::test_download_now_publishes_state
    i `::test_subscriptions_revision_changes_only_on_target_state` (zapis transferu nie zmienia
    rewizji; akcja `T` i rozliczenie sprawdzenia ją zwiększają).
- `acquisition_decisions.py:45` `_FIELDS` — `sources`, `candidates[].quality`,
  `candidates[].confidence`, `candidates[].conflict`, `polish_history`, `source_states`, `blocker`,
  `numbering` (§6.6).
- `config/user_settings.py` — `UserSettings` (:242) pola z §6.5; `load_user_settings` (:796) i
  `_MISSING` (:171) — brakujący klucz dostaje wartość domyślną (do potwierdzenia testem w K9, N-6).
- `config/field_catalog.py` — `SettingSpec` (:158) dla sześciu pól, `SettingScope.GLOBAL`;
  `setting_id` = **nazwa pola `UserSettings`** (`source_tsukihime`, …, `subscription_polish_wait_h`),
  bo `setting_is_persisted` i `_preference_value`/`_assign_preference` szukają go w
  `UserSettings.__dataclass_fields__` (`field_access.py:119–121`, `:254–257`, `:277–281`); bez
  aliasów z kropką (uwaga 8).

### 5.10 Oferta częściowa i wybór w trakcie wyszukiwania (uwagi 2, 3)

Stan zastany: odczyt oferty to jedno blokujące `channel.call` pod `_catalog_lock` przez cały czas
wyszukiwania (`resident.py:246–264`, `:567–590`), więc `episode_choose` na tym samym kanale czeka
na koniec odczytu; wybór w panelu woła `_start_work` (`anime.py:1904`, :1863), które podnosi
`_generation` i odrzuca dalsze widoki. Oferta należy do sesji połączenia kanału katalogu
(`session_id` per połączenie, `local_control.py:613`; `automation.py:4979–4981`); zdarzenia idą
osobnym połączeniem obserwacji (`resident.py:322–336`). Spec A §3.2 wymaga wyboru, gdy wiersze
jeszcze dochodzą — dlatego odczyt przestaje blokować kanał.

**Cykl życia oferty:**

1. **Start (krótkie wywołanie).** `ResidentSession.episode_offer_start(key, *, repeat,
   previous_admission_id, command_id)` (zastępuje `episode_offer`, `resident.py:246`) idzie przez
   `_episode_interaction` i trzyma `_catalog_lock` tylko na czas odpowiedzi. Owner (`_episode_offer`,
   :4851) sprawdza żądanie jak dziś, zakłada `OfferSession(offer_id=generation, key, revisions,
   final=False, failed: str | None = None, closed=False)` w `_episode_offers[session_id]`, zleca wyszukiwanie w puli ownera z `_active_io += 1`
   i rozliczeniem w `finally` przez `self._queue.put(self._finish_io)` (wzorzec :3717–3745 i
   :1393–1400; także po błędzie i unieważnieniu) i odpowiada `{offer_id, instance_id}`. Podczas
   zamykania start dostaje `SHUTTING_DOWN` (:1385–1387).
2. **Snapshoty.** `on_partial` przez `_on_owner(partial(self._store_partial_offer, …))` zapisuje
   `revisions[revision] = EpisodeOfferView` (rosnące `revision`, wszystkie rewizje bieżącej oferty)
   i publikuje sygnał `{"event": "episode_offer_partial", "payload": {"offer_id"}}`. **Pomyślny koniec
   wyszukiwania** to jedna akcja na ownerze (`_store_final_offer`): zapis **nowej** rewizji N+1
   z końcowym widokiem (także gdy kandydaci się nie zmienili; bez oczekujących źródeł), `final = True`
   i ten sam sygnał. Sama flaga na rewizji N nie dotarłaby do panelu, który przyjmuje tylko wyższe
   rewizje. Snapshot jest odrzucany, gdy oferta sesji ma inne `offer_id` albo `closed` (jak
   `_store_episode_offer`, :4919).
   **Błąd:** praca oferty łapie błędy domenowe i I/O jak dziś (`AniShiftError`, `OSError`, `ValueError`,
   w tym błąd H1) i zapisuje je przez `_on_owner` jako `failed = komunikat` (`refusal_text`/`failure_code`
   jak w `D`, :5141–5143) z sygnałem; nigdy jako pusty sukces. Każdy inny wyjątek (błąd
   programistyczny; `except Exception  # noqa: BLE001` jak :3728) zapisuje `failed` z ogólnym komunikatem, jest logowany i przerywa ofertę bez
   tworzenia kandydata. `finally` zawsze rozlicza `_active_io`.
3. **Odczyt (krótkie wywołanie).** `episode_offer_get(offer_id)` zwraca stan `OfferSession`:
   `{"state": "searching"}` (brak rewizji — panel zostaje w „Szukam”), `{"state": "ready",
   "revision", "final", "view"}` (ostatnia rewizja) albo `{"state": "failed", "message"}` (terminalny;
   wcześniejsze rewizje nie są już do wyboru). Nieznane `offer_id` albo brak oferty w sesji →
   `offer_expired`.
4. **Transport.** `ControlClient.call` bez zmian (`local_control.py:528–552`); `_event_key`
   (:821–827) scala `episode_offer_partial` po `(event, offer_id)`; `state.py` `_forward_anime`
   (:1016–1023) przekazuje zdarzenie.
5. **Panel (bez wyścigu startu).** Zdarzenia przed odpowiedzią startową są ignorowane. Po odpowiedzi
   startowej panel **zawsze raz** woła `episode_offer_get`, potem każde zdarzenie (rewizja albo błąd)
   tylko wyzwala `get`; stan `ready` przyjmuje wyłącznie rewizję wyższą od pokazanej. `failed` nie
   ma rewizji i jest rozróżniany po polu `state`: panel przyjmuje go zawsze (stan końcowy, `get` po nim
   zwraca już tylko `failed`), pokazuje komunikat zamiast listy i ignoruje dalsze zdarzenia. Podmiana
   widoku trzyma kursor i zaznaczenia po `info_hash`. Do pierwszego snapshotu ekran „Szukam”, potem
   lista z linią „szukam jeszcze: …” (najpóźniej po 3 s, §5.7).
6. **Wybór w trakcie (krótkie wywołanie).** `_choose_release` (`anime.py:1888`) nie woła
   `_start_work`; `episode_choose(offer_id, revision, info_hash, path, deviation_confirmed,
   conflict_confirmed, command_id)` idzie tą samą sesją, owner obsługuje je w pętli sterującej,
   podczas gdy wyszukiwanie trwa w puli. Po przyjęciu oferta `closed`, panel wraca do odcinków
   (`_finish_episode_choice`).
7. **Dowód wyboru po stronie ownera (uwaga 3).** Klient przesyła tylko identyfikatory i
   potwierdzenia. Owner bierze z `revisions[revision]` wiersz pokazany użytkownikowi (reprezentant,
   werdykt H1, konflikt, wymagane potwierdzenia R-04, :4987–4989) i porównuje z tym samym hashem
   w ostatniej rewizji; jakakolwiek różnica → `STALE_PREVIEW` z powodem `offer_changed`, także przy
   przysłanym potwierdzeniu. Bez różnicy: istniejące sprawdzenie potwierdzeń (:4995–5000). Rewizja
   nieznana → `offer_expired` (:4981).
8. **Utrata obserwacji ≠ utrata sesji katalogu (R3-4).** Zerwanie połączenia obserwacji nie zamyka
   oferty: panel po ponownym `observe` woła `episode_offer_get` na niezmienionym kanale katalogu
   i kontynuuje. Wywołanie w `state.py:942–944` zostaje, zmienia się to, co ono zamyka: dziś utrata obserwacji woła
   `self._parent.disconnect()`, a `ResidentSession.disconnect` (`resident.py:493–500`) zamyka kanał
   katalogu, gdy `_catalog_lock` jest wolny — przy krótkich wywołaniach jest wolny prawie zawsze,
   więc każde zerwanie obserwacji zabijałoby ofertę. Zmiana: `disconnect` nie zamyka kanału katalogu,
   gdy sesja ma otwartą ofertę (`_open_offer: int | None`, ustawiane przez `episode_offer_start`,
   czyszczone po przyjęciu wyboru, `offer_expired` i `interrupt_reads`); kanał martwy (np. restart
   rezydenta) wykryje następne `get` przez `connection_lost` → `_drop` (:562–565).
9. **Zamknięcie sesji katalogu = wygaśnięcie.** `Esc`/nowy odczyt (`interrupt_reads`,
   `resident.py:204–211`), zamknięcie albo utrata kanału katalogu kończą sesję po stronie ownera
   (`_release_session`, `automation.py:1417–1419`, usuwa ofertę). Następne `get` lub `episode_choose`
   (nowa sesja) dostaje `offer_expired`, a panel pokazuje „Oferta wygasła — otwórz ponownie”.
   Wyszukiwanie w puli kończy się najpóźniej po limicie źródeł; jego snapshoty są odrzucane.
10. **Rozmiar.** Snapshot podlega istniejącemu limitowi odpowiedzi (`anime.py:1596`); przekroczenie
    daje stan „Widok nieaktualny” i nie przerywa odczytu.

Testy:
- `test_automation.py::test_offer_start_returns_before_search`, `::test_partial_offer_stored_with_revision`,
  `::test_partial_offer_dropped_after_close`, `::test_offer_work_counted_in_active_io` (także po
  wyjątku źródła i po zamknięciu oferty `_active_io` wraca do 0);
  `::test_offer_get_searching_then_ready` (start → natychmiastowy `get` przy wstrzymanych źródłach →
  `searching`; po 3 s `ready` z linią „szukam jeszcze”); `::test_offer_failure_before_first_snapshot`
  i `::test_offer_failure_after_partial` (wyjątek domenowy i programistyczny → `get` daje `failed`
  z komunikatem, brak kandydata, `_active_io == 0`); `tests/cli/test_anime_episodes.py::test_offer_failed_shows_error` (także po pokazanej rewizji N:
  `failed` zastępuje listę mimo braku wyższej rewizji);
  `tests/cli/test_anime_episodes.py::test_final_revision_without_new_candidates` (panel pokazał
  częściową rewizję N z `final=False` → owner kończy bez nowych kandydatów → `get` daje N+1
  z `final=True`, panel ją przyjmuje i usuwa „szukam jeszcze”) i
  `t/app/test_automation.py::test_final_store_adds_revision` (koniec zapisuje N+1 i sygnał w jednej akcji);
- `test_automation.py::test_choose_refused_when_assessment_changed_since_revision` — ten sam hash
  i plik; rewizja 1 `zgodny`, rewizja 2 `niepewny`; wybór z rewizją 1 (z potwierdzeniem i bez) →
  `offer_changed`; z rewizją 2 i potwierdzeniem → przyjęty; `::test_choose_same_assessment_older_revision_ok`;
  `::test_choose_ignores_client_assessment`;
- **integracyjny** `tests/cli/test_anime_episodes.py::test_choose_during_search_before_slow_source`:
  owner z fałszywymi źródłami (Knaben wstrzymany na `threading.Event`), `ResidentSession` przez
  `local_control`, panel; pierwszy snapshot → wybór → przyjęcie zapisane, zanim Knaben zostanie
  zwolniony; po zwolnieniu snapshot zamkniętej oferty nie zmienia widoku;
- `tests/cli/test_anime_episodes.py::test_final_event_before_start_response` (zdarzenie `final`
  dociera przed odpowiedzią startową → panel po starcie woła `get` i od razu pokazuje stan końcowy,
  bez czekania na limit), `::test_lower_revision_ignored`, `::test_partial_offer_keeps_cursor_on_hash`;
- `tests/cli/test_interactive_state.py::test_observe_loss_keeps_open_offer` (zerwane połączenie
  obserwacji, rezydent żyje → po ponownym `observe` `get` zwraca ofertę, wybór przyjęty);
  `::test_catalog_session_closed_expires_offer` (zamknięty kanał katalogu → `offer_expired`, panel
  pokazuje komunikat);
- `test_local_control.py::test_offer_partial_events_coalesce_per_offer`;
  `tests/cli/test_resident.py::test_offer_start_releases_catalog_lock`,
  `::test_disconnect_keeps_catalog_with_open_offer`.

### 5.11 CLI [EDIT]

- `cli/resident.py:246` `episode_offer` → `episode_offer_start(key, *, repeat, previous_admission_id,
  command_id)` i `episode_offer_get(offer_id)` (krótkie, §5.10); `episode_choose` (:266) wysyła
  `offer_id`, `revision`, `info_hash`, `path` i potwierdzenia zamiast pełnego kandydata;
  `disconnect` (:482) zostawia kanał katalogu przy otwartej ofercie (`_open_offer`, §5.10 pkt 8).
- `cli/interactive/anime.py` — wiersze ofert (:1146–1161) bez kolumny źródła, z jakością
  i pewnością; `receive`, `_start_owner_offer` (:1855), `_load_owner_offer` (:1871) i
  `_choose_release`/`_send_choice` (:1888–1921) według §5.10; `_candidate_details`
  (:2411) z porównaniem numerów i notą o kalibracji; `_subscription_facts` (:888) z `polish_line`;
  `_subscription_key` (:572–589) dostaje `"text:t"` → `subscription_check` z `number` podświetlonego
  celu, tylko gdy jego `EpisodeStatus.polish_wait_until` jest ustawione (wiersz pokazuje „Czeka na PL
  do HH:MM”, a przy `polish_skipped` „Pobieram bez czekania na PL”); stopka U08 pokazuje wtedy „T pobierz teraz” (wolny klawisz:
  U08 ma Space, A, Z, D, I, P, ?, W, F, X, Esc, `ux.md:279`, :288). `state.py` (:509) przekazuje
  `number` w ładunku. Test `tests/cli/test_subscriptions_panel.py::test_download_now_key` (klawisz tylko
  przy celu czekającym na PL, ładunek z numerem).
- `cli/interactive/anime_state.py` — `AnimeRow` (:57) `quality: str`, `confidence: str`.
- `cli/interactive/anime_view.py` — `_spec` (:301) i `_values` (:332) z dwiema kolumnami na końcu.
- `cli/interactive/settings.py` — `_Category` (:344) `DOWNLOAD`, `_SCOPE_FIELDS` (:354).
- `cli/interactive/state.py` — `_forward_anime` (:1016); po ponownym `observe` sygnał dla ekranu
  anime, żeby wołał `episode_offer_get` (§5.10 pkt 8); `disconnect` (:943–944) bez zmian w wywołaniu.
- `episode_commands.py` — `EpisodeOfferView` (:65) `revision: int`, `pending_sources`,
  `source_lines`; `EpisodeStatus` (:95) `stalled_since: str | None`, `polish_wait_until: str | None = None`,
  `polish_skipped: bool = False` (§5.9, R9-2).

### 5.12 Reguła zamiany R-07 i punkt podpięcia dla E4 (K12)

Zakres A1: tylko reguła wyboru zamiany. Kontrola U-07/U-08 i automatyczne kolejne wydanie po
braku napisów należą do E4 (`plans/e3-subskrypcje.md:70` O-7 [DO-2026-10-02],
`plans/e2-pobieranie.md:118`); zlecenie ręczne nie przechodzi H2 (`plans/e1-przeplyw-subskrypcji.md:176`,
przejście 18). A1 nie zmienia `_check_basis` ani `_reject_attempt`, nie dodaje stanu zamiany
ani ponawiania po restarcie.

- **Reguła (spec A §10, R-07):** `subscription_choice.replacement(candidates, *, excluded)` —
  pierwszy `admissible` według `choice_key` (§6.2) bez czekania na PL i bez progu celu;
  `excluded` wyklucza cały hash każdego wypróbowanego wydania; `niepewny` nigdy (odrzuca go
  `admissible`); brak kandydata → `None`, czyli problem do ręcznego wyboru.
- **Punkt podpięcia dla E4:** wyzwalacz U-08 woła `replacement` na `candidates` z
  `AcquisitionService.search_episode` (§5.9, pełne źródła) i `excluded` = hashe wypróbowanych
  wydań odcinka (`subscription_targets.excluded` dla subskrypcji, hashe przyjęć klucza dla ścieżki
  ręcznej); przyjęcie wyniku przez istniejące `_admit_episode` z `previous=` odrzuconym przyjęciem,
  start treści przez `_replacement_ready`. Limit zamian, trwałość i widok problemu projektuje E4.
  Kontrakt zapisany w docstringu `replacement` i w `anishift/application/AGENTS.md` (K12).

Testy (`test_subscription_choice.py`): `test_replacement_first_admissible_by_choice_key`,
`test_replacement_ignores_polish_wait_and_threshold`, `test_replacement_excludes_whole_hash`
(inny plik tego samego hasha też odpada), `test_replacement_never_uncertain`,
`test_replacement_none_when_no_admissible`.

## 6. Trwały stan, migracja i ustawienia

### 6.1 Schemat 5 stanu ownera (`config/watch/state.json`)

`SubscriptionRecord` (`subscription_targets.py:180`):

| Klucz JSON | Typ | Znaczenie | Spec A |
| --- | --- | --- | --- |
| `tsukihime_id` | `int \| null` | zapamiętane wewnętrzne ID tytułu TsukiHime; `null` = jeszcze nieznane albo brak tytułu (ponawiane przy sprawdzeniu) | §3.1 |
| `mapping` (istniejący) | jak dziś | dozwolony także przy `kitsu_id = null`; `kitsu_id` bez mapowania niedozwolone | §3.5, U-22 |
| `mapping_tvdb_season` | `int \| null` | sezon TVDB z mostu z odczytu, który zapisał `mapping`; `null` = nieznany (tylko S/E i duplikaty); ocena zapisanego mapowania w `merge_listing` (§5.9) | §3.5 |

`SubscriptionTarget` (`subscription_targets.py:128`):

| Klucz JSON | Typ | Znaczenie | Spec A |
| --- | --- | --- | --- |
| `tried` (istniejący) | lista tekstów | wykluczenia celu; nowe wpisy = 40-hex hash; stare `hash:fileIdx` czytane jako wykluczenie hasha (`excluded`) bez przepisywania | §6.2 |
| `started` | `int ≥ attempts` | trwały licznik rozpoczętych prób; źródło identyfikatora polecenia przyjęcia; rośnie zawsze, także przy próbie zatrzymanej po metadanych | §6.2 |
| `attempts` (istniejący) | `int ≤ 3` | zużyty limit; zwracany przy zatrzymaniu po metadanych | §6.2 |
| `threshold` | `int 0..4 \| null` | `ResolutionClass` najlepszej martwej próby | §6.2 |
| `failures` | lista `{"hash", "decisive": bool, "transient": 0..3}` | niepowodzenia odczytów TsukiHime para cel–hash | §6.2 |
| `polish` | `null \| {"state": "present" \| "absent" \| "unknown", "observed_at": ISO}` | ostatnia **udana** obserwacja TsukiHime historii PL | §6.3 |
| `sources_down_since` | `ISO \| null` | **per cel** (uwaga 9): chwila pierwszego sprawdzenia tego celu, w którym wszystkie włączone źródła zawiodły; reguły ustawiania i czyszczenia w §6.4; przeżywa restart | §8 |
| `polish_skip` | `null \| {"due": ISO, "at": ISO, "settled": bool}` | „Pobierz teraz” (O-2): `due` = `due_at` celu w chwili akcji, `at` = chwila akcji (zegar ownera, tożsamość akcji), `settled` = `false` przy zapisie. **Aktywne**, gdy `due == due_at` (przesunięcie terminu unieważnia); **nierozliczone**, gdy aktywne i `settled is false`; `settled` ustawia tylko owner wg §5.9 (dowód ze snapshotu, bez porównań czasu); przeżywa restart | §6.3 |

`EpisodeChoice` (`control.py:347`) — trwały snapshot cech przyjętego wydania (uwaga 4), pod
kluczem `traits` przypisania:

| Klucz JSON | Typ | Znaczenie | Używa |
| --- | --- | --- | --- |
| `traits.polish` | `"polish" \| "bare" \| "none"` | klasa PL napisów reprezentanta w chwili przyjęcia | lokalny dowód „PL jest” (§6.3) |
| `traits.resolution` | `int 0..4` | `ResolutionClass` w chwili przyjęcia | próg celu martwej próby (§6.2) |
| `traits.unusable` | lista z `raw`, `hardsub`, `dub_only` | cechy wykluczające z nazw i tagów | `metadata_check` (§3.4) |

`compact_acquisition` (`control.py:662–688`) czyści `target`, `release`, `trackers`,
`file_index`, `files`, `file_map`, ale **nie** `traits`, więc snapshot przeżywa cleanup i restart.
Zapis: `_episode_choice` (`automation.py:7725`) dla każdego przyjęcia (ręczne, `D`, subskrypcja).
Przypisania sprzed schematu 5 mają `traits = null`: brak lokalnego dowodu PL; martwa
próba bez snapshotu dostaje klasę z `reference.release` przez `release_quality`, a przy pustej
nazwie — `UNKNOWN`, które nie blokuje żadnej klasy.

`EpisodeAssignment` (`control.py:412`): opcjonalne `stopped: "pack" | "ambiguous" | "no_match" |
"taken" | "recheck"` w `_OPTIONAL_ASSIGNMENT_KEYS`
(`watch_state.py:365`). `AutomationPolicy.transfer_stall_s`: domyślnie 600.

Walidacja w `__post_init__`: `started >= attempts`, `threshold` w zakresie, hashe w `failures`
unikalne i 40-hex, `transient <= MAX_TRANSIENT_FAILURES`. `_strict_object` (`watch_state.py:1679`)
odrzuca nieznane klucze — dlatego zestawy kluczy są wersjonowane (§6.2).

### 6.2 Migracja do schematu 5 (uwaga 1)

Stan zastany: `load` (`watch_state.py:459–461`) woła `_upgrade` dla każdej starszej wersji, a
`_upgrade` → `_migrated` (:481–489, :517–521) zawsze dekoduje zamrożony `subscriptions.json` i
woła `migrate` (`subscription_migration.py:53`), które zastępuje `subscriptions`, `legacy_orders`
i `removed_subscription` (:78–84) oraz rozlicza oczekujące receipt `subscription_*` (:59–69).
Dla stanu 4 to zniszczyłoby rekordy, cele, usuniętą subskrypcję i receipt — dlatego ścieżka 4 → 5
jest osobna:

- `_upgrade(content, stored)` (:481) rozróżnia dwie rzeczy (uwaga 6): **odczyt bajtów**
  `subscriptions.json` (`_legacy_bytes`, :531) wyłącznie do kopii bajt w bajt oraz **dekodowanie
  i import** legacy (`_decode_legacy` + `migrate`, `_migrated` :517–523):
  - `stored.schema_version == 4` → bajty legacy czytane tylko dla `.a1-migration.bak`;
    `migrated = migrate_to_five(stored)` **bez** `_decode_legacy` i bez `migrate`; uszkodzony lub
    różny od stanu `subscriptions.json` nie wpływa na wynik;
  - `stored.schema_version <= 3` → `migrate_to_five(migrate(stored, _decode_legacy(legacy), now))`
    (najpierw import E3 do schematu 4 z rozliczeniem dawnych receipt `subscription_*`, potem A1);
  - wynik przechodzi `_decode_state(json.loads(json.dumps(_encode_state(migrated))))` jak dziś,
    przed kopiami.
- **Kopie są warunkiem zapisu:** `_preserve_before_migration` (:539–550) tworzy wymagane kopie
  przed `_write_migrated` (:525); błąd kopii (`_keep_backup`) daje `ConfigError` `IO_ERROR` i
  **zatrzymuje zapis schematu 5** — `state.json` zostaje bajtowo w schemacie 4 (wzorzec E2/E3).
- **Receipt (uwaga 6):** `_decode_receipt` (:1597–1606) dziś wymaga `pending ∈ {None, "cancel"}`
  dla `schema_version == WATCH_STATE_SCHEMA_VERSION`; po podbiciu do 5 warunek byłby tylko dla 5
  i przepuszczałby niepoprawny dokument 4. Ograniczenie zostaje wersjonowane:
  `schema_version >= _SCHEMA_FOUR` → `pending ∈ {None, "cancel"}`. Oczekujące `subscription_*`
  istnieją tylko w dokumentach 1–3 i rozlicza je `migrate` na ścieżce 1–3 → 4 → 5.
- `_migrate_without_state` (:503) — legacy obecne: `migrate_to_five(migrate(...))`; brak: `_fresh_state()`
  w schemacie 5.
- `migrate` (`subscription_migration.py:80`) ustawia `schema_version=_SCHEMA_FOUR` (stała zamiast
  `WATCH_STATE_SCHEMA_VERSION`), więc jego semantyka pozostaje „do schematu 4”.
- `migrate_to_five(state)`: `started = attempts`, `threshold = None`, `failures = ()`, `polish = None`,
  `sources_down_since = None` (cel), `tsukihime_id = None`, `mapping_tvdb_season = None`, `traits = None`; `tried`, receipt,
  `legacy_orders`, `removed_subscription` bez zmian; `transfer_stall_s == 1800` → `600`, inna
  wartość zostaje.
- Wersjonowane dekodowanie przed ścisłą walidacją: `_decode_target` (:1122), `_decode_subscription`
  (:1080) i `_decode_assignment` (:1462) dostają `schema_version` i porównują klucze z
  `_TARGET_KEYS_V4`/`_TARGET_KEYS_V5` (analogicznie rekord); dokument 4 nie może mieć nowych
  kluczy, dokument 5 musi je mieć (wzorzec `_schema_four_facts`, :974–981). `_schema_four_facts`
  porównuje z `_SCHEMA_FOUR` zamiast `WATCH_STATE_SCHEMA_VERSION`, więc sekcje 4 są wymagane
  także w 5.
- `_SUPPORTED_SCHEMA_VERSIONS` (:121) z 5; `_MIGRATION_BACKUP_SUFFIXES` + `5: ".a1-migration.bak"`
  (kopia `state.json` i `subscriptions.json` bajt w bajt, istniejącej nie nadpisuje — wzorzec
  `_preserve_before_migration`, :539–550); kopia `state.json.v4.bak` jak dziś (:484–487).
- Odczyt schematu 5 przez kod 4 nie jest wspierany (jak przy 3 → 4); kopie pozwalają wrócić.

Testy (`test_subscription_migration.py`, `test_watch_state.py`, na plikach w `tmp_path`):

1. `test_four_to_five_keeps_owner_state_without_legacy_file` — stan 4 z rekordami, usuniętą
   subskrypcją, celami z próbami, poprawnymi receipt (bez `pending` i z `pending="cancel"`)
   i `legacy_orders`, brak `subscriptions.json` → wszystko zachowane, nowe pola z wartościami
   domyślnymi.
2. `test_four_to_five_does_not_decode_frozen_file` — `subscriptions.json` różny od stanu oraz
   osobno uszkodzony (niepoprawny JSON) → wynik jak w (1), plik niezmieniony, a jego bajty
   tylko w `.a1-migration.bak`.
3. `test_three_to_five_imports_legacy_then_upgrades` — ścieżka 1–3 → E3 → A1, w tym rozliczenie
   oczekującego receipt `subscription_*` przez `migrate`.
4. `test_schema_four_rejects_pending_subscription_receipt` — dokument 4 z `pending="subscription_add"`
   → `ConfigError`, bez zapisu.
5. `test_four_to_five_stall_default_only` — `1800 → 600`, `900` bez zmian.
6. `test_four_to_five_backups` — `.a1-migration.bak` i `state.json.v4.bak` bajtowo równe źródłu;
   drugi `load()` nie zmienia bajtów i nie tworzy kopii.
7. `test_four_to_five_backup_failure_blocks_write` — błąd zapisu kopii → `ConfigError` `IO_ERROR`,
   `state.json` bajtowo w schemacie 4.
8. `test_schema_five_roundtrip`, `test_schema_four_rejects_five_keys`, `test_schema_five_requires_keys`.
9. `test_excluded_legacy_pair_key` — stare `hash:fileIdx` wykluczają hash.

Dowód na żywo (K11): właściciel uruchamia rezydenta na kopii swojego `config/watch/state.json`,
sprawdza listę subskrypcji, próby celów i obecność `.a1-migration.bak`.

### 6.3 Stan wyłącznie w pamięci rezydenta

Ostatni wynik szybkiego źródła (≤30 min), wynik dociąganego (60 min), spisy plików po hashu,
kolejka uzupełnień i rewizje oferty częściowej. Restart i wyłączenie źródła je usuwają
(spec A §3.1, §3.2, §3.4). Początek niedostępności wszystkich źródeł jest trwały per cel (§6.1,
`SubscriptionTarget.sources_down_since`), nie w pamięci.

### 6.4 Ścieżka „źródła niedostępne > 1 h” (decyzja orkiestratora)

Zegar jest **per cel** (uwaga 9; spec A §8: „dla należnego celu”), bo sprawdzenie szuka każdego
należnego celu osobno (`automation.py:3777–3787`, `search_targets`, `subscription_targets.py:418–425`)
i dwa cele jednej subskrypcji mogą mieć przeciwne wyniki.

- Czysta `subscription_choice.sources_down(previous, results, now) -> datetime | None` na wyniku
  `subscription_check` danego celu:
  - **awaria** = co najmniej jedno źródło włączone i każde włączone ma `FAILED`, `UNFINISHED`
    bez wyników albo `SKIPPED` bez wyniku z pamięci → `previous or now`;
  - **reset** (`None`): którekolwiek źródło `DONE` — także udany pusty wynik `DONE` + `()` —
    albo `UNFINISHED` z wynikami; żadne źródło nie jest włączone (brak włączonych nie rozpoczyna
    awarii); `NO_KITSU`/`NO_TITLE` bez innych źródeł nie są awarią.
- `_subscription_outcome` zapisuje wynik w `SubscriptionTarget.sources_down_since` w tym samym
  `_save` co `last_check`. Koniec należności celu (spełniony, zlecony ręcznie, wyczerpany,
  usunięty z celów) czyści pole przez `settle_target`/`merge_listing`.
- Powiadomienie dla należnego celu, gdy `now >= sources_down_since + SOURCES_DOWN_NOTICE_H`;
  jednokrotność przez trwały `NotificationKey(subscription, number, "sources_down")`. Termin
  następnego sprawdzenia po restarcie wynika z U-14, więc powiadomienie pada w pierwszym
  sprawdzeniu po upływie 1 h.
- Testy: `test_notification.py::test_sources_down_notice_once_across_restart` (awaria w t0 →
  restart w t0 + 30 min → awaria w t0 + 45 min bez powiadomienia → t0 + 60 min jedno →
  t0 + 75 min bez drugiego); `test_subscription_choice.py::test_sources_down_reset_by_empty_success`
  (awaria → `200 []` → awaria: zegar startuje od nowa od trzeciego sprawdzenia);
  `::test_sources_down_not_started_when_all_disabled`; `test_subscription_owner.py::test_sources_down_per_target`
  (dwa należne cele jednej subskrypcji: jeden z awarią, drugi z wynikami — tylko pierwszy ma zegar
  i powiadomienie); `::test_sources_down_cleared_when_target_settles`.

### 6.5 Ustawienia

| Pole `UserSettings` = `SettingSpec.setting_id` | Domyślnie | Zakres |
| --- | --- | --- |
| `source_tsukihime` | `True` | bool |
| `source_torrentio` | `True` | bool |
| `source_nyaa` | `True` | bool |
| `source_knaben` | `True` | bool |
| `source_nekobt` | `True` | bool |
| `subscription_polish_wait_h` | `2` (O-2: `DEFAULT_POLISH_WAIT_H = 2`) | `0..48` |

- `setting_id` to dokładnie nazwa pola `UserSettings` (uwaga 8; `field_access.py:119–121`,
  `:254–257`, `:277–281`); grupowanie w kategorii „Pobieranie” robi `cli/interactive/settings.py`
  (`_Category`, `_SCOPE_FIELDS`), nie identyfikator.
- Żyją w `config/settings.json` panelu (`config/user_settings.py`), nie w stanie ownera: to
  preferencje użytkownika, jak inne pola GLOBAL. Owner ich nie zapisuje.
- Droga do rezydenta: publiczne `assign_setting_value` (`field_access.py:97`) +
  `save_user_settings` (`user_settings.py:868`) → polecenie `_reload_settings`
  (`automation.py:3477`) → `self._service.reload_preferences()`; owner czyta `SourceSwitches`
  i `polish_wait_h` z `settings_snapshot()` (`service.py:717`) na początku każdego sprawdzenia
  i każdej oferty, więc zmiana działa od najbliższego sprawdzenia. Wyłączenie źródła woła
  `EpisodeSearch.forget(source)`.
- Testy: `tests/config/test_field_catalog.py::test_acquisition_specs_are_persisted_fields`
  (`setting_is_persisted(spec)` dla sześciu specyfikacji);
  `t/app/test_automation.py::test_source_switch_through_settings_api_reaches_owner` —
  `assign_setting_value(settings, spec("source_knaben"), False)` → `save_user_settings` →
  polecenie `reload_settings` (`automation.py:1569`) → następne wyszukiwanie nie woła Knaben i ma `SourceState.DISABLED`.

### 6.6 Rejestr decyzji (`config/watch/decisions.jsonl`)

Dopisywanie bez zmiany poprzednich wpisów; nowe klucze w `_FIELDS` (`acquisition_decisions.py:45`):
`sources` (stan każdego źródła), `candidates[]` z `quality`, `confidence`, `conflict`, `verdict`,
`pack`, `after_metadata`; `polish_history` (`state`, `evidence`: `local` / `tsukihime` / `none`),
`blocker`; `numbering` celu: `anilist` / `anidb` / `none` / `duplicate` / `tvdb_season` (spec A §3.5:
źródło numeracji albo powód jej braku); przy „Pobierz teraz” `action = "skip_polish_wait"`. Bez nazw plików z dysku i URL-i.

### 6.7 Miejsca zależne od decyzji O-x

Wszystkie rozstrzygnięte 2026-10-06 (spec A §12).

| Decyzja (rozstrzygnięta) | Jedyne miejsce |
| --- | --- |
| O-1: odcinek bez PL zostaje, bez ponownego pobrania i podmiany | brak kodu podmiany; `subscription_choice.decide` kończy cel po przyjęciu |
| O-2: domyślnie 2 h + „Pobierz teraz” | `user_settings.DEFAULT_POLISH_WAIT_H = 2`; `SubscriptionTarget.polish_skip` i `ChoiceState.skip_wait` (§5.6) |
| O-3: bez poprzedniego sezonu | `EpisodeSearch.previous_history` zwraca `None` dla odcinka 1 |
| O-4: PL przed audio | `release_quality.class_key` (używany przez `list_order` i `choice_key`) |
| O-5: sugestia = pierwszy wiersz grupy 1, „niepewne”, gdy nie `zgodny` | `episode_selection.suggestion` |

## 7. Kroki implementacji

Każdy krok to osobny commit, który przechodzi bramki: `uv run ruff check anishift/ tests/`,
`uv run ruff format --check anishift/ tests/`, `uv run mypy anishift/ tests/`,
`uv run mypy --platform linux anishift/ tests/`, `uv run pytest`. Dowód kroku = wynik tych komend
+ wymienione testy + review innego modelu. „Zachowanie po kroku” mówi, co działa po commicie.

**K0. Branch, rekonesans, zestaw wzorcowy (bez kodu produkcyjnego).**
`git switch -c work/acquisition/04-algorithm` od HEAD `work/acquisition/03-subscriptions`.
`scripts/tmp/a1_record_reference.py` nagrywa surowe odpowiedzi (§9), sprawdza N-1..N-6 i N-8 (§10.2)
i zapisuje fixtury; `coverage-baseline.json` z `src_analysis.json`. Orkiestrator spisuje
`expectations.json` jako propozycję. **Właściciel potwierdza oczekiwania przed K1.** Dowód:
fixtury w repo, raport niewiadomych w `docs/work/acquisition/a1-recon.md`.

**K1. Typy i normalizacja.** `info_hash_hex`, `language_code`, nowe pola `StreamCandidate`,
`TitleCandidate.country` z `countryOfOrigin`. Zachowanie: bez zmian widocznych.

**K2. H1: nazwa wydania i konflikt.** `classify_release_name`, `CONFLICT_REASONS`, `is_conflict`
(każdy `MISMATCH` + `INSUFFICIENT` z listy, §5.3), `conflict_label`; goldeny bez edycji poza O7.
**O7 (`a1-recon.md` §7, §8):** w `classify_release_name` i/lub `classify` jawny konflikt
sezonu/odcinka (`_identity_conflict`, `episode_identity.py:635–640`) jest rozpoznany przed odrzuceniem
„Unconsumed filename text…” (:1260–1265): 154587-1 (`[FrixySubs] … S02E01`) i 140960-12 (`… S02E12`
VARYG) dają konflikt; token `DUAL` (`.DUAL-VARYG`, 154587-28) to metadana techniczna. Inne werdykty
bez rozluźnienia: 213805-1 (brak numeracji), 210031-13 (sprzeczny tytuł), 204389-2 (mapowanie)
zostają jak są. Zmiana werdyktu goldena tylko procedurą `e1-integracja.md` §10.6.
**O7 wycofane:** każda wczesna sprzeczność przed „Unconsumed…” dała na korpusie fałszywe konflikty dla rekordów poprawnych (najwęższa: 17, inny system sezonów), więc 154587-1 i 140960-12 zostają niepewne, a zostaje tylko token `DUAL` — decyzja 2026-10-07 (`outcomes/e1.md`, H1 v10.5).
**D2 (spec A §3.5, §5.3 „Cel bez numeracji”):** powód `Mapped numbering cannot be checked without
target numbering.` poza `CONFLICT_REASONS` przy celu bez `season`; testy
`test_entry_title_local_number_without_numbering`, `test_sxxexx_without_numbering_stays_uncertain`.

**K3. Pewność.** `identity_evidence(target, candidate)`, `episode_confidence`, fixtury modelu
i przypadków (z różnicami filename/path/release i bez pliku).

**K4. Jakość.** `release_quality` w całości (deklaracje per plik, dubbing, klasy, punkty, donghua).

**K5. Scalanie.** `ReleaseFile` z oryginalnymi `path`/`filename`/`file_index` (§5.4),
`merge_releases` z deklaracjami plików, `_attach_torrentio_file`, `is_pack`. **O8 (`a1-recon.md`
§7, §8):** `names.py:67–69` `_SEASON_ONLY_RE` rozpoznaje `S01` przed blokiem `[1080p …]` jako
sezon bez odcinka → paczka (`[ZigZag] Bocchi the Rock! S01 …`, `[Breeze] Frieren … S01 …`).

**K6. Ranking listy + wszyscy konsumenci (uwaga 5).** Nowy `RankedCandidate`, `rank_candidates`
na `EpisodeRelease`, `streams_releases`, `representative`, `list_order`, `visible`, `suggestion`;
w tym samym commicie: `acquisition.py:836` (`prepare_episode` przez `streams_releases`, działa do
K12), `acquisition_decisions.py` `offer_check` (:149–164) i `candidate_proposal` (:201–208),
`tests/application/test_acquisition_decisions.py:68–74`, `eligible`
(`subscription_targets.py:456–464`) na `candidate.supported` bez zmiany semantyki, `automation.py`
(:3869–3871, :4806–4808, :4936, :4995, :5162), `application/__init__.py` (:125, :283), `anime.py`
(:1146–1161, :1893, :2411). Test `test_rank_torrentio_equivalent_to_conf_model`. Zachowanie: lista
z Torrentio w nowym porządku; subskrypcja jak dotąd przez `prepare_episode`.

**K7. RequestControl.** Dostawcy, okna TsukiHime, deadline wywołującego, wewnętrzna pula
z `copy_context().run`, podtypy błędów, `close()` zamyka pulę (§5.9, uwaga 1, decyzje A–B). Testy
z §5.9 (w tym `test_deadline_caller_times_out_while_transport_hangs`, `test_follower_joins_after_leader_timeout`,
`test_budget_through_both_pools`); `Future` i `_active` rozlicza tylko worker puli.

**K8. Adaptery.** `tsukihime.py` (z plikami i statusami `TsukiHimeLookup`), `knaben.py`, `nekobt.py`
(`PagedSource`, `TextPage`), `source` w Torrentio, przyczyna `HTTPStatusError` w `nyaa.py:161–162`;
testy na fixturach z K0 przez `httpx.MockTransport`. Według `a1-recon.md` §3 i §8: Knaben GET
z hashem małymi literami (O1); btih `200` z kompletnym `files` (`len(files) == filecount`) = spis bez drugiego GET, krótsze → `/torrents/{id}`, tam też krótsze → brak spisu; `202` = `PENDING` z ID
(O2, O3); odcinki TsukiHime `offset` → `start`, `limit` 100 (O4); nekoBT blok `{Tags:…}` (O5).

**K9. Wyszukiwanie ręczne i `D`.** `episode_search.py` (kontrakt źródeł §5.7: Nyaa per kategoria
i `_release_stream`, `failure_kind`, kompletność, TsukiHime w jednej wizycie, snapshot po 3 s, brak
numeracji z `ListingRead`, frazy, limity czasu, `_ListingCache`, kolejka w porządku `list_order`;
frazy wg spec A §3.1 po decyzjach 2026-10-06: `S01E{NN}` w sezonie 1 TV (W1), OVA/SPECIAL bez
`S{ss}E{NN}` z pełnym podtytułem (W2), `{ss}` z grafu franczyzy bez zapytań AniList (O6) —
`a1-recon.md` §2 (Frazy), N-5, §4, §6, §8),
`AcquisitionService.search_episode` dla oferty (`automation.py:4878`), `D` (:5140) i `offer` (:8383); `read_listing` bez wyjątku przy braku numeracji (§5.9, F);
pola ustawień i `SettingSpec` o `setting_id` = nazwa pola (§6.5); wiring w `bootstrap.py`.
Subskrypcja dalej przez `prepare_episode` (`automation.py:3781`) do K12. Testy:
`test_source_outcome_end_to_end`, `test_source_timeout_keeps_partial`,
`test_manual_offer_snapshot_at_3s_without_results`, `test_offer_without_numbering_shows_releases`, `test_d_without_numbering_does_not_admit`,
`test_repeat_without_numbering_has_no_suggestion` (`EpisodeOffer.numbering`, `suggestion(…, numbering)`),
`test_unresolved_season_stays_in_completion_queue`,
`test_source_switch_through_settings_api_reaches_owner`. Zachowanie: lista i `D` z pięciu źródeł
z wierszami stanu; przełączniki działają bez restartu. Na żywo: właściciel otwiera listę odcinka
i przełącza źródło.

**K9b. Numeracja i mosty ID (spec A §3.1, §3.5 D1–D3).** Adaptery `services/catalog/arm.py`
(`ArmCatalog.ids`), `services/catalog/kitsu.py` (`KitsuCatalog.kitsu_id` z kontrolą zwrotną),
`AniZipCatalog.mapping_by_anidb`; dostawcy `arm` i `kitsu` w `http_requests._provider`;
`_bridged_mapping` w `read_listing`, `ListingRead.tvdb_season` i `numbering_source`, `read_listing(..., targets)` z pominięciem pamięci (§5.9);
`numbering_gap` (film pomijany, `test_numbering_gap_skips_movie`) i `identity_target(..., numbering)` (§5.5); `EpisodeRequest.numbering` per
odcinek (§5.7); wiring w `bootstrap.py`. Dogranie do zestawu wzorcowego odpowiedzi arm-server,
ani.zip po AniDB i Kitsu mappings przypadków 213805-1, 204389-1, 204389-2, 210031-1 tym samym
`scripts/tmp/a1_record_reference.py` (§9.1). Oczekiwanie 213805-1 zmienia się: cel dostaje S02E01
z AniDB, więc wydania `S02E01` mogą być zgodne. Orkiestrator wylicza nową propozycję jak w K0
(`a1-recon.md` §10 ma tylko cel z grafu, `06e78bb8`, nie cel z AniDB) — **właściciel potwierdza ją
przed commitem K9b.** Testy: z §5.5 i §5.9 („mosty numeracji i ID”), `test_arm.py`, `test_kitsu.py`,
`test_anizip.py::test_mapping_by_anidb`. Zachowanie: lista 213805 ma numerację S02E01, a 210031
wiersz Torrentio; odcinek 2 z 204389 pokazuje „brak numeracji”, a odcinek 1 ma numerację. Na żywo: właściciel otwiera
listę 213805-1.

**K10. UI listy.** Kolumny Jakość i Pewność, powód konfliktu, szczegóły z notą kalibracji.

**K10b. Oferta częściowa i wybór w trakcie (uwagi 2, 3, 14).** Cykl §5.10: `episode_offer_start`,
zdarzenia z rewizjami, `episode_offer_get`, `episode_choose` z `offer_id`/`revision`/`info_hash`/`path`,
weryfikacja wyboru na zapisanej rewizji ownera, stan `get` (`searching`/`ready`/`failed`), panel z `get` po starcie i tylko rosnącymi rewizjami, praca oferty w `_active_io`, nieblokujący callback cooldownu, `disconnect` z otwartą ofertą (owner,
`local_control.py`, `resident.py`, `state.py`, `anime.py`). Testy z §5.10, w tym integracyjny
`test_choose_during_search_before_slow_source`, `test_final_event_before_start_response`,
`test_offer_get_searching_then_ready`, `test_offer_failure_before_first_snapshot`, `test_offer_failure_after_partial`,
`test_final_revision_without_new_candidates`, `test_final_store_adds_revision`, `test_observe_loss_keeps_open_offer`, `test_catalog_session_closed_expires_offer`, `test_shutdown_with_blocked_source_and_late_429`. Na żywo:
wiersze dopływają, kursor zostaje na wydaniu, „szukam jeszcze: …”, wybór przed końcem
wyszukiwania.

**K11. Schemat 5.** Pola §6.1 (w tym `SubscriptionTarget.sources_down_since`), migracja §6.2
(bajty legacy tylko do kopii, kopia warunkiem zapisu, wersjonowane receipt), `excluded`,
`ChoiceTraits` zapisywane w `_episode_choice`, U-22 w całości (inwariant rekordu i `read_listing`), konflikt numeracji niezależny od Kitsu
w `merge_listing` (§5.9, testy `test_numbering_change_*`, `test_numbering_conflict_blocks_attempts_after_restart`; uzupełnienie z braku i naprawa sprzecznej bez konfliktu przez `numbering_gap` z K9b: `test_numbering_filled_from_none_not_conflict`, `test_duplicate_repaired_not_conflict`, `test_numbering_filled_after_restart_not_conflict`; `SubscriptionRecord.mapping_tvdb_season` (§6.1), scenariusze A/B: `test_saved_season_mismatch_then_fixed_without_bridge_not_conflict`, `test_saved_numbering_change_with_new_bridge_season_is_conflict`, `test_bridge_season_scenarios_after_restart`),
`stall_s = 600`. Zachowanie: subskrypcje działają jak dotąd na nowym schemacie. Na żywo: rezydent
na kopii stanu właściciela (§6.2).

**K12. Wybór automatu.** `subscription_choice` (bez historii PL), `EpisodeSearch.subscription_check`
z budżetem §3.1, `_FastCache`, `_PulledCache`, `completion_order`, trwałe `failures`;
`AcquisitionService.subscription_check` zastępuje `prepare_episode` w `_check_subscriptions`
(:3781); wybór w `_subscription_outcome` z `protected_files` zamiast `_taken_pairs` (uwaga 11),
przyjęcie w `_admit_attempt` (`started`); cel bez numeracji przechodzi zwykły wybór (spec A §3.5 D2,
bez osobnego blokera; `test_no_numbering_decides_on_entry_title`, `test_numbering_appears_on_next_check`); usunięte `eligible`,
`candidate_pair`, `_taken_pairs`, `prepare_episode`, gałąź `T_niepewny`; `sources_down` per cel
ustawiane i czyszczone (bez powiadomienia — K15); czysta reguła `replacement` z testami i opisanym
punktem podpięcia dla E4 (§5.12).

**K13. Po metadanych, zastój, próg.** `metadata_check` (z `protected_files` na ścieżkach qB),
`episode_files` liczy zgodne pliki przed skrótem po nazwie (§5.9, `test_manual_ambiguous_file_waits_for_u18c`),
`_stop_after_metadata` (zwrot limitu, wykluczenie, `stopped`), próg w `_settled_target` z
`traits.resolution` tylko dla prób martwych (§5.9: 10 min bez przyrostu bajtów, także bez metadanych,
bez czasu pauzy), 600 s. Testy
`test_subscription_scenarios.py::test_threshold_not_raised_by_failed_removed_rejected_or_stopped`
i `::test_paused_time_not_counted_as_stall`. Testy odbioru:
zatrzymanie po metadanych → restart → inne wydanie z tym samym licznikiem;
`test_next_release_chosen_content_waits_for_previous_settlement`;
`test_dead_attempt_after_compaction_uses_snapshot` (rozdzielczość tylko z nazwy, restart po
kompaktowaniu). Na żywo: subskrypcja testowa na wydaniu-paczce.

**K14. Czekanie na PL.** `previous_history`, `polish_history` (lokalny dowód z `traits.polish`
przypisań poprzedniego odcinka), `wait_until`, `decide`, `polish_line`. Test:
`test_local_polish_evidence_survives_restart_and_compaction` (przyjęcie z PL tylko w `sublangs` →
restart + kompaktowanie → TsukiHime niedostępne → „PL jest”). „Pobierz teraz”:
`polish_skip` z rozliczeniem w `next_search_at`, `ChoiceState.skip_wait`, `number` w
`subscription_check`, stan PL celu w `episode_states`, klawisz `T` w U08 (§5.6, §5.9, §5.11); testy
`test_skip_wait_*`, `test_next_search_at_unsettled_skip_is_now`, `test_download_now_*` (w tym trwające
sprawdzenie innego celu, restart, brak podwójnego przyjęcia, brak kandydata), `test_download_now_key`,
`test_polish_state_per_target`, `test_polish_state_refreshes_on_revision`, `test_download_now_refusal_refreshes`, `test_subscriptions_revision_changes_only_on_target_state`. Na żywo: wiersze celów pokazują „Czeka na PL do HH:MM”; na celu
czekającym na PL właściciel wciska `T` → cel pobiera się od razu (albo pokazuje powód §8), wpis
w `decisions.jsonl`, po restarcie rezydenta cel nie wraca do czekania.

**K15. Powiadomienia i rejestr.** §8 przez `NotificationKey`, w tym §6.4; pola rejestru §6.6.

**K16. Zestaw wzorcowy, pokrycie i odbiór.** `test_acquisition_reference.py` (§9); aktualizacja
AGENTS.md. Odbiór właściciela na żywo w `uv run anishift`. Replay (O9, `a1-recon.md` §1 „Format
fixtury”, §2): `MockTransport` ustawia `content-type` według źródła (XML dla Nyaa i nekoBT, JSON dla reszty);
replay ręczny i subskrypcyjny mają osobne zestawy dozwolonych zapytań. Fixtury ~17 MB w całości (W3).

## 8. Graf zależności

```text
K0 ─► K1 ─┬─► K2 ─► K3 ───────────┐
          ├─► K4 ─► K5 ───────────┼─► K6 ─► K9 ─┬─► K10 ─► K10b ─┐
          └─► K7 ─► K8 ───────────┘             └─► K11 ─────────┴─► K12 ─► K13 ─► K14 ─► K15 ─► K16
```

K6 wymaga K3 i K5; K9 wymaga K6 i K8; K9b wymaga K2 i K9 i stoi między K9 a K10/K11 (K10, K11
i dalsze wymagają K9b); K12 wymaga K10b i K11 (wspólne fragmenty `automation.py`
i `EpisodeOfferView`).

Strumienie (najwyżej 2 naraz):

| Faza | Strumień A | Strumień B |
| --- | --- | --- |
| po K1 | K2 → K3 | K4 → K5 |
| po K3 i K5 | K7 → K8 | K6 |
| po K9b | K10 → K10b (CLI, IPC, oferta w `automation.py` :4851–4995) | K11 (schemat, migracja, `_episode_choice`) |
| od K12 | sekwencyjnie (wspólne `_check_subscriptions`, `_settled_target`) | — |

## 9. Zestaw wzorcowy

### 9.1 Miejsce i format

`tests/fixtures/acquisition/reference/<anilist_id>-<number>.json.gz` — JSON spakowany gzipem
(`mtime=0`), bo hook `check-added-large-files` odrzuca pliki powyżej 500 KB; testy czytają go przez
`gzip.decompress`. Tak samo `expectations.json.gz`, `coverage-baseline.json.gz`,
`recording-log.json.gz` i `probes/n2.json.gz`:

```json
{
  "case": "210031-1",
  "anilist": {"id": 210031, "format": "TV", "country": "JP"},
  "number": 1,
  "captured_at": "2026-10-..",
  "responses": [{"method": "GET", "url": "https://api.tsukihime.org/v1/...", "status": 200, "body": "..."}]
}
```

Odtworzenie przez `httpx.MockTransport` po (metoda, URL, treść POST); brak odpowiedzi = błąd testu.
`expectations.json`: `{"<case>": {"top3": [hash, hash, hash], "automatic": {"hash": "...|null",
"reason": "..."}, "confirmed_by_owner": true}}`. Skrypt nagrywający: `scripts/tmp/a1_record_reference.py`
(katalog jednorazowych skryptów z mapy repo); fixtury śledzone w git. Rozmiar zmierzony w K0:
~17 MB; decyzja właściciela 2026-10-06 (W3): fixtury zostają w całości, bez przycinania; pola
`links`/`links_audio` w treściach TsukiHime są zastępowane przy nagraniu (`a1-recon.md` §1, §2 „Sanityzacja”).

### 9.2 Przypadki

- §9 badanie 1 (15): 210031-1, 210031-13, 159042-1, 189123-1, 185756-1, 185756-2, 195516-1,
  204389-1, 204389-2, 154587-1, 154587-28, 140960-1, 140960-12, 130003-1, 130003-12.
- §9: najnowsze odcinki 8 subskrypcji właściciela (lista z `config/watch/state.json` w K0).
- §9: jeden film (`MOVIE`) i jeden wieloodcinkowy wpis OVA/SPECIAL (wybiera właściciel w K0).
- §3.3 (syntetyczne, `test_release_quality.py`): hash z nazwą Nyaa/TsukiHime bez `HardSub` i nekoBT
  z `HS` → niedopuszczalny „hardsub”; `audiolangs=["ja","en"]` + `English Dub` → nie sam dubbing;
  ucięty `release` Torrentio z dubbingiem + Nyaa `Dual-Audio` → nie sam dubbing; `audiolangs=["en"]`
  i `A=ja,en` → sam dubbing; `Example - 01 [1080p] [Dual-Audio] [Polish audio]` → nie sam dubbing,
  +15; `Example - 01 [1080p] [PL dub] [Napisy PL]` → sam dubbing.
- §5.2: kody regionalne (`pl-PL`, `ja-JP`, `zh-Hant`); nekoBT `F=` z `pl`, niepuste `S=` bez PL →
  +40, klasa PL, kończy czekanie; dwa pliki w jednym wydaniu z różnymi `sublangs` → cechy
  reprezentanta; flaga PL Torrentio przypięta do pliku spisu po nazwie.
- §5.4: F, A, C, E, B, D w kolejności właściciela.
- §6.2: zatrzymanie po metadanych → restart → inne wydanie z niezmienionym licznikiem.
- spec A §6.2–§6.3: wydanie stoi 1080p → próg blokuje 720p po restarcie; oczekujące 1080p blokuje 720p do
  3 niepowodzeń; „PL jest” czeka do bufora, „PL nie ma” bierze od razu, „nieznane” 2 h.

### 9.3 Pokrycie (uwaga 10)

- **Źródło bazy:** `%TEMP%\opencode\src_analysis.json`, pole `cases[].hashes[<źródło>]` dla 15
  odcinków badania 1; suma `cases[].union` = `total_union` = 640 unikalnych hashy (`intent.md:122`;
  wcześniejsze 74 wydania z `intent.md:34` to inna, 3-odcinkowa próba i nie jest bazą). K0 kopiuje
  te hashe do `coverage-baseline.json` (`{"<case>": {"union": [...], "<źródło>": [...]}}`).
- **Jednostka:** unikalny hash wydania w obrębie przypadku (para przypadek–hash).
- **Bramka (stała):** licznik / **640** ≥ 95%, gdzie licznik = pary bazy obecne w scalonej liście
  nowej konfiguracji (§3.1) odtworzonej z fixtur. Mianownik się nie zmienia; zanik wydań w źródłach
  nie obniża progu.
- **Pokrycie diagnostyczne (osobny raport, nie bramka):** ten sam licznik / (640 − potwierdzone
  `gone`). Para jest `gone` tylko z dowodem: skrypt K0 powtarza zapytanie z badania 1
  (`src_measure.py`) w **każdym** źródle, w którym para wtedy wystąpiła, i każde z tych powtórzeń
  jest kompletne (`200`, wszystkie strony do `total`, bez limitu, cooldownu, błędu ani ucięcia
  treści), a hasha w nim nie ma. Awaria, `429`, cooldown, `202`, deadline albo niepełna odpowiedź
  dają `unverified`, nie `gone`. `coverage-baseline.json` zapisuje `gone` z dowodem (źródło, zapytanie,
  `total`, liczba stron) i `unverified` osobno.
- **Decyzja:** spadek > 5 pp (bramka < 95%) wymaga decyzji właściciela przed odbiorem (spec A §9:253),
  **także** gdy pokrycie diagnostyczne pokazuje, że spadek wyjaśnia zanik wydań; raport per
  przypadek i per źródło podaje obie liczby.
- **Testy:** `test_reference_coverage_gate_against_640`; `test_coverage_diagnostic_excludes_only_proven_gone`
  (para z awarią powtórzenia nie wypada z mianownika diagnostycznego);
  `test_coverage_detects_loss_with_same_top3` — z fixtur jednego przypadku usuwane są odpowiedzi
  Knaben, trójka na górze się nie zmienia, a funkcja pokrycia spada poniżej progu.

## 10. Ryzyka i niewiadome

### 10.1 Ryzyka

| Ryzyko | Wykrycie | Reakcja |
| --- | --- | --- |
| projekcja `identity_evidence` rozjeżdża się z `conf_model.py` | test równoważności K3 (z wariantami filename/path/release) | poprawić projekcję; modelu nie zmieniać |
| nowa funkcja H1 zmienia werdykty `classify` | goldeny E1 czerwone | procedura `e1-integracja.md` §10.6 |
| migracja 4 → 5 gubi stan ownera | testy §6.2 (1)–(2) | ścieżka bez `migrate`; bez zielonych testów brak commitu K11 |
| limity TsukiHime przekroczone w szczycie U-14 | 429 w licznikach `RequestControl.counts`, testy okien | P-10 rzednie; budżet §3.1 bez zmian |
| fizyczne żądanie przeżywa wywołującego po jego limicie | `test_deadline_caller_times_out_while_transport_hangs` | wywołujący kończy w terminie; żądanie trwa najwyżej do stałych timeoutów httpx, a w oknie dostawcy może zostać wysłane już dla nikogo (≤ 1 żądanie na wywołującego, bo kolejne nie startują po limicie); zaufane publiczne API, pula ograniczona do 10 |
| zamykanie rezydenta czeka na ofertę | `test_shutdown_with_blocked_source_and_late_429` | `run()` czeka najwyżej do limitu źródeł; wątki puli `RequestControl` nie są czekane (`wait=False`), wyjście procesu najwyżej do stałych timeoutów httpx; spóźniony cooldown zostaje bez zapisu na dysk |
| snapshot oferty częściowej przekracza limit odpowiedzi | `anime.py:1596`, test rozmiaru | widok nieaktualny, odczyt trwa; ewentualne odchudzenie snapshotu |
| wybór w trakcie aktualizacji trafia w zmieniony wiersz | testy §5.10 pkt 7 | `offer_changed` i ponowny wybór |
| zdarzenie oferty przed odpowiedzią startową albo zgubione przy zerwaniu obserwacji | `test_final_event_before_start_response`, `test_observe_loss_keeps_open_offer` | `get` zawsze po starcie i po ponownym `observe` |
| powody łączone „conflicts … or is unresolved” (:156, :157, :163) poza listą: jawnie inny sezon w tym zapisie nie jest oznaczony konfliktem | `test_insufficient_conflict_cases`, `test_unresolved_season_stays_in_completion_queue` | bezpieczne (§5.3): wydanie zostaje `niepewny`, automat go nie wybiera, a blokuje i czeka; ręcznie wymaga potwierdzenia odchylenia |
| otwarta oferta trzyma martwy kanał katalogu po restarcie rezydenta | `test_catalog_session_closed_expires_offer` | następne `get` dostaje `connection_lost` → `_drop` → „Oferta wygasła” |
| przypisanie bez znanej ścieżki chroni cały hash i blokuje inny plik tego wydania | `test_protected_unbound_assignment_protects_hash` | świadomie zachowawcze do poznania pliku („lepiej nie pobrać”); po metadanych ochrona zawęża się do ścieżki |
| Nyaa per kategoria zmienia liczbę żądań | `test_nyaa_queries_both_categories`, liczniki `RequestControl.counts` | tyle samo żądań co `search_releases` (jedno na kategorię); budżet §3.1 bez zmian |
| arm-server (pochodna Fribb, odświeżana ok. co 24 h, bez opublikowanego limitu) opóźnia albo gubi most; dla 204389 nie ma TVDB | `test_bridge_failure_keeps_anilist_mapping`, liczniki `RequestControl.counts` dla `arm` | błąd odbiera tylko most: zostaje numeracja z ani.zip po AniList; `tvdb_season = None` wyłącza tylko kontrolę sezonu (duplikat S/E 204389 nadal wykryty); `429` przez `RequestControl` |
| sezon TVDB z mostu różni się od ani.zip bez realnej sprzeczności | `test_numbering_gap_tvdb_season`, rejestr `numbering = tvdb_season` | bezpieczne: odcinek bez numeracji, automat przyjmuje tylko tytuł wpisu z numerem lokalnym (spec A §3.5 D2) |
| fixtury za duże | pomiar w K0: ~17 MB | rozstrzygnięte (W3): zostają w całości, `links`/`links_audio` zastępowane przy nagraniu |
| pokrycie < 95% względem 640 | K16 | decyzja właściciela przed odbiorem (spec A §9), także przy spadku wyjaśnionym zanikiem |
| wątki fan-outu i puli `RequestControl` a `ContextVar` scope | `test_budget_through_both_pools` | scope otwierany w wątku źródła; pula `RequestControl` przez `copy_context().run` |
| pełny odczyt stanów odcinków przy dużej subskrypcji: do ~20 porcji `episode_states` przy 2000 celów na każdą zmianę `subscriptions_revision` | `test_subscriptions_revision_changes_only_on_target_state`, liczba wywołań w `test_polish_state_refreshes_on_revision` | zachowanie istniejące: pełny odczyt następuje przy każdej zmianie payloadu statusu (także postęp transferu co 1 s), jak przed A1; A1 dodaje tylko odczyty przy zmianie stanu celów; przy odczuwalnym koszcie — osobna zmiana odczytu stronicowanego |

### 10.2 Niewiadome (sprawdzane w K0)

Wszystkie zamknięte w K0 (`a1-recon.md` §3); decyzje W1–W3 (właściciel) i O1–O9 (orkiestrator)
z 2026-10-06 wpisane w kroki K2, K5, K8, K9, K16 i mapę §3.

- N-1 (zamknięta): btih bez względu na wielkość liter; `404` przy braku; `200` z `id` i `files`
  (78/78 list identycznych z `/torrents/{id}`); `202` z `id`, `filecount` i niepełnym `files` (11–16 z 28) → O2, O3.
- N-2 (zamknięta): odpowiedź `{total, start, limit, results}`; parametr `offset` wraca jako `start`;
  `limit` > 100 → `422` → O4.
- N-3 (zamknięta): wyszukiwanie przez GET (`q`, `s`, `f`, `o=date`, `dead`), `hash` wielkimi
  literami, `title`, `seeders`, `magnetUrl`, `total.value`; strony 300 → O1.
- N-4 (zamknięta): blok `{Tags:…;A=…;F=…;S=…}` w sufiksie tytułu, flagi bez `=` (`HS`), sklejone
  kody (`es419`, `frfr`, `ptbr`, `zhhans`), `seeders`/`infohash` w `torznab:attr`, `limit=100` +
  `offset` → O5.
- N-5 (zamknięta): indeks `season_context` zgodny z grafem franczyzy 21/21, ale wymaga 19 zapytań
  AniList → O6; SPECIAL 194884 → W2.
- N-6 (zamknięta): częściowy plik v3 uzupełniany wartościami domyślnymi, v2 migrowany, nieznane
  klucze pomijane, schemat 4 odrzuca cały plik → nowe pola bez podnoszenia
  `SETTINGS_SCHEMA_VERSION` (3).
- N-8 (zamknięta): `countryOfOrigin` wraca; 101972 (Mo Dao Zu Shi) = `CN`, pozostałe `JP`.

## 11. Odchylenia i blokery

- **B-1 i B-2 (rozstrzygnięte):** A1 implementuje tylko regułę wyboru zamiany R-07 jako czystą
  funkcję z testami i punktem podpięcia (§5.12, K12). H2 nie obejmuje ręcznych pobrań
  (`plans/e1-przeplyw-subskrypcji.md:176`, przejście 18); kontrola U-07/U-08 i jej wyzwalacz to E4
  (`plans/e3-subskrypcje.md:70` O-7, `plans/e2-pobieranie.md:118`). Do czasu E4 nieudane ręczne
  pobranie nie dostaje automatycznego kolejnego wydania.
- **N-7 (rozstrzygnięta przez spec A §6.5 i §6.2 „Próg celu”):** definicja martwej próby w §5.9.
- Odrzucona interpretacja v1 („niedostępność od startu rezydenta”) zastąpiona trwałym
  `sources_down_since` per cel (§6.4).
- Odejście od dzisiejszego kontraktu IPC: blokujące `episode_offer` zastępują krótkie
  `episode_offer_start` / `episode_offer_get` i zdarzenia z rewizjami (§5.10), bo spec A §3.2 wymaga
  wyboru przed końcem wyszukiwania; `application/AGENTS.md` („`episode_offer` trzyma jedną interakcję
  na połączenie”) aktualizuje K10b.

## 12. Poza zakresem (spec A §11)

- Osobne pliki napisów PL z zewnątrz (E4), w tym ocena użyteczności napisów.
- Kontrola U-07/U-08, wyzwalacz zamiany w ścieżce ręcznej, jej limit, trwałość i widok (E4;
  A1 dostarcza tylko regułę `replacement`, §5.12).
- Wygląd list i szczegółów poza nowymi kolumnami.
- Strojenie wag ponad §5.4 i zestaw wzorcowy; próg pewności dla automatu (§7) — tylko zbieranie danych.
- Wsparcie Linuksa.

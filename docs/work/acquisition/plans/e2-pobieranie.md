---
kind: plan
status: draft
baseline: 65b34a471d48eb8abf7b8cacc1b363f5e386445c
branch: work/acquisition/02-download
created: 2026-09-29
parent: ../masterplan.md
---

# Plan E2: jednorazowe pobieranie nową drogą

## 1. Cel i rezultat użytkownika

Nowe Anime dostarcza zamówiony odcinek do Biblioteki: wybór odcinków → sugerowane albo wskazane wydanie → magnet → lista plików → wybrane pliki → istniejące Auto → gotowy wynik. Zlecenie jest trwałe i dotyczy odcinka, a transfer może być wspólny dla kilku odcinków.

Na ekranie odcinków **Space** zaznacza, **A** przełącza wszystkie/żadne, **Z** ustala zakres, **D** pobiera sugestie zaznaczonych odcinków, a bez zaznaczeń odcinek pod kursorem. **I** otwiera wydania tego odcinka z seedami i wyborem konkretnego wydania. **P** pozwala świadomie pobrać inne wydanie już zleconego odcinka, z potwierdzeniem i podglądem. **S** jest zarezerwowane dla E3. Dotychczasowe pobieranie i subskrybowanie pod **G** pozostają dostępne.

```text
TERAZ: nowe Anime kończy się na ofercie; stare pobieranie przyjmuje hash i zapisuje do workspace
    ↓
LUKA: brak trwałego celu odcinka, selekcji plików magnetu, izolacji paczki i wspólnej deduplikacji
    ↓
PO E2: jedno przyjęcie odcinka → selektywny transfer w stagingu → pełny zestaw do Auto → Biblioteka
```

## 2. Warunki końcowe

- [ ] D i I prowadzą do trwałego przyjęcia przez `AutomationOwner`; zamknięcie panelu nie zatrzymuje przyjętej pracy.
- [ ] `WatchState` pamięta odcinek i kolejne jawne pobrania niezależnie od Historii, subskrypcji i obecności plików.
- [ ] Jedna paczka daje jeden aktywny transfer; dołożenie odcinka rozszerza jego wybór plików.
- [ ] U-18: unikalna nazwa, następnie H1 na pełnych ścieżkach qB, następnie U05. Sam `fileIdx` nigdy nie uprawnia do pobrania.
- [ ] U-17/P-07: tylko zamówione wideo i odpowiadające mu napisy/audio; wszystkie pliki odcinka mają dowód qB oraz istnieją z oczekiwanym rozmiarem, zanim odcinek trafi do Auto.
- [ ] I-06 działa dla D ↔ D, D ↔ G, D ↔ stare subskrypcje dla kluczy potwierdzonych według §8.3, także przy różnych hashach, dwóch panelach i restarcie. `legacy-unkeyed` zachowuje deduplikację fizyczną; brak deduplikacji między różnymi hashami subskrypcji bez AniList ID jest jawnym ograniczeniem do E3.
- [ ] I-07: niezlecone E2 z paczki E1/E2/E3, również pusty albo częściowo zapisany MKV, nie trafia do skanu, Przetwarzania ani Biblioteki. Obowiązuje także po restarcie i ponownym uzgodnieniu workspace.
- [ ] P nie nadpisuje poprzedniego wyniku, wyklucza zastępowaną parę wydanie/plik i pokazuje nowy wybór przed zatwierdzeniem.
- [ ] `decisions.jsonl` zawiera rzeczywiste `check` i `selection` ścieżki ręcznej oraz korekty; nie jest źródłem stanu wykonania.
- [ ] Q-08 obejmuje odpowiedzi **i zdarzenia**, a listy główne nie przesyłają całej trwałej historii przyjęć ani list odcinków wszystkich subskrypcji.
- [ ] Migracja na kopii rzeczywistego stanu, syntetyk z prawdziwym qB i restartem, regresje M-06, pełne bramki i niezależne review mają zapisane wyniki. H2 ma rzeczywisty wynik właściciela albo jawny status `PENDING HUMAN`.

## 3. Nie-cel

E3: nowa maszyna subskrypcji, harmonogram, autozamknięcie, migracja zakresów subskrypcji, usunięcie G, tryb cienia, kontrola H2 zawartości dla automatu. E4: pomijanie tłumaczenia PL, wymiana wydania po braku napisów. E5: usuwanie starego zaplecza i szerokie sprzątanie. Nie zmieniamy reguł H1 ani rankingu, nie projektujemy drugiego schedulera i nie rozwijamy Linuksa.

**Dwa znaczenia H2:** w tym planie „odbiór H2” oznacza scenariusz właściciela z `ux.md` §12; nie oznacza heurystyki kontroli zawartości z planu przepływu §5.4. Ta druga nie jest elementem ręcznego pobierania E2.

## 4. Authority i baseline

| Źródło | Co rozstrzyga |
| --- | --- |
| Brief `e2-plan`, decyzje właściciela i orkiestratora z 2026-09-29 | D bez osobnego podglądu zwykłego pobrania, I z wyborem, A wszystkie/żadne, S dla E3, tymczasowe N-03, pozostawienie G, pełne Q-08 |
| [masterplan.md](../masterplan.md) §E2 | jeden rezultat etapu, zależności, M-06, I-06/I-07, prawdziwy qB, migracja i odbiór |
| [spec.md](../spec.md) U-03–U-08, U-16–U-19, P-01–P-08, M-06/M-07, Q-01–Q-08, I-01–I-08, PR-01–PR-12 | wymagania i chronione kontrakty |
| [ux.md](../ux.md) U03–U05, §11–§14 | P, wybór pliku, komunikaty, nawigacja, mały terminal; wyjątki klawiszy opisane w §13 tego planu |
| [e1-przeplyw-subskrypcji.md](e1-przeplyw-subskrypcji.md) §2, §3.4, §3.6, §5.6–§5.7 | ręczny wybór, zakaz automatycznej wymiany przyjętego niepewnego, rejestr i zweryfikowane przypadki |
| [e1-wybor-odcinka.md](e1-wybor-odcinka.md) §10 oraz [e1-integracja.md](e1-integracja.md) §9–§10 | istniejące kontrakty E1, builder celu, ranking, zasada regresji H1 |
| [outcomes/e1.md](../outcomes/e1.md), integracja 2026-09-29 i N-03 z 25.09 | dowody poprzednika, ograniczenia, znany fail środowiskowy |
| root/scoped `AGENTS.md`, skille `simple`, `planning`, `coding`, `workflow`, `subagent`, `review` | wykonanie, język, własność, bramki i przeglądy krzyżowe |

**Zweryfikowany baseline planowania:** `work/acquisition/01-episode-selection @ 65b34a471d48eb8abf7b8cacc1b363f5e386445c`. Drzewo na wejściu bez zmian raportowanych przez Git; `git status` zgłosił odmowę dostępu do siedmiu starych katalogów pytest pod `workspace/temp/`. Nie są dowodem zmian w kodzie ani powodem do ich usuwania.

**Drift przy zamknięciu planu (2026-09-29):** HEAD i branch pozostały bez zmian, lecz równoległa praca zmieniła 11 śledzonych plików: `anishift/application/{__init__.py,episode_selection.py}`, `anishift/cli/AGENTS.md`, `anishift/cli/interactive/anime.py`, `anishift/services/catalog/{anilist.py,types.py}`, `docs/work/acquisition/ux.md`, `tests/application/test_episode_selection.py`, `tests/cli/{test_anime_episodes.py,test_interactive_anime.py}` i `tests/services/catalog/test_anilist.py`. Obejrzany diff obejmuje m.in. kolejność premier, pomijanie listy tytułów dla jednej franczyzy, G na ekranie wpisów, A wszystkie/żadne i stałą widoczność seedów. To zmiany spoza sesji planistycznej; nie ustalono ich autorstwa ani akceptacji. Tabela §5 opisuje bazowy SHA, nie końcowe brudne drzewo. F0 ma uzgodnić wynik tej pracy z orkiestratorem, ponownie sprawdzić kod i aktualny UX oraz skorygować pozostały zakres F6; nie odtwarzać już wdrożonego A ani cofać nowej nawigacji. Do tego czasu plan pozostaje `draft`, a numery linii są wskazówkami do baseline. **Rozliczone w F0:** zmiany to zrecenzowane poprawki H1 (`046c841`); aktualne odwołania — §5 i [outcome E2](../outcomes/e2.md).

Wykonanie na **`work/acquisition/02-download` od HEAD E1**, piętrowo. F0 zapisuje rzeczywisty SHA rozgałęzienia i ewentualny diff względem powyższego baseline. Nie pracować na `main`. Commit/PR/push wyłącznie z upoważnienia orkiestratora/właściciela; `typ(scope): opis`, scope z hooka. E1–E3 nie trafiają osobno do `main` przed akceptacją E3.

**Stan odbioru E1:** dokument wyniku nadal mówi `PARTIAL`, H1 oczekuje. Brief przekazuje nowszy feedback właściciela H1 i delegację „zrób wszystkie etapy, potem pogadamy”; pozwala planować i wykonywać E2, ale nie jest dowodem zaliczenia wszystkich 10 tytułów H1. F0 zapisuje tę różnicę, bez dopisywania fikcyjnego PASS.

**Znany wcześniejszy fail:** na `efafddd` raportowano ruff/format/mypy obu platform PASS oraz pytest **5695 passed, 21 skipped, 1 failed**: `tests/platform/test_qbittorrent_process.py::test_private_clients_download_concurrently_reconnect_and_stop_independently`. Otwarte okno qB uniemożliwia oczekiwane automatyczne zamknięcie; fail występował także na F0 E1. W tej pracy planistycznej nie uruchamiano tych bramek ponownie. Nie naprawiać testu ani polityki zamykania przy okazji E2; F0 i outcome rozróżniają ten fail od każdej nowej regresji.

### D-01 — tymczasowe dopuszczenie N-03

Orkiestrator, na podstawie delegacji właściciela, **tymczasowo dopuszcza puste `.mkv` w stagingu powstające po ustawieniu priorytetów**. Warunki: zero eksportu tych plików do workspace/Biblioteki, negatywny test I-07 oraz sprzątnięcie własnych pustych pozostałości po zakończeniu zlecenia, a dla wspólnego transferu po zakończeniu ostatniego korzystającego z niego zlecenia. Nie wolno sprzątać katalogu używanego przez drugi odcinek.

To decyzja tymczasowa orkiestratora w ramach delegacji właściciela, nie nowy pozytywny pomiar N-03. **Nie pytać właściciela ponownie w F0**; przedstawić decyzję i dowody do potwierdzenia w raporcie końcowym. Dowód z 25.09: metadane i mapowanie 3/3, 0 bajtów treści, ale pliki istniały po priorytetach. Czasy metadanych: 1,014 / 8,246 / 2,222 s, qB 5.2.3. Jeżeli właściciel odrzuci D-01, zatrzymać dopuszczanie nowych magnetów i wrócić do **pilota F0 oraz §8.4/F2**, gdzie skupiona jest polityka dodania i selekcji. Najpierw nowy pomiar mechanizmu bez pustych plików; inne źródło `.torrent` wymaga decyzji właściciela. Nie zmieniać rankingu i nie pobierać całej paczki jako obejścia. Przyjętych zleceń ani plików użytkownika nie kasować.

## 5. Stan aktualny zweryfikowany w kodzie

Odwołania `plik:linia` zaktualizowano w F0 do `dd01982ef766ca680713b331de5644d824b945ce` (kod identyczny z `046c841`). Baseline wykonania: `work/acquisition/02-download`, drzewo bez zmian raportowanych przez Git; ostrzeżenia dostępu do siedmiu starych katalogów pytest jak w §4. Drift i zamieniona sekwencja autorów są zapisane w [outcome E2](../outcomes/e2.md). Wykonawca śledzi także symbole, gdy numery przesuną się po fazie.

| Fakt | Dowód | Znaczenie dla E2 |
| --- | --- | --- |
| `EpisodeKey` to AniList ID + lokalny numer, a `StreamCandidate` zachowuje hash, `file_index`, nazwę i trackery | `anishift/application/episode_selection.py:250–272` | użyć istniejącej tożsamości; film = numer 1 |
| H1 dostaje `release/path/filename`, bez dowodów; sugestia bierze zgodnego, potem niepewnego, pomija jawnie nieobsługiwane | `episode_selection.py:431–458`; `episode_identity.py:1168–1182` | nie pisać drugiego rankera ani klasyfikatora |
| Oferta czyta Torrentio, buduje cel i zwraca `EpisodeOffer`; nie tworzy przyjęcia | `anishift/application/acquisition.py:723–745` | dodać transakcję przyjęcia i dowodową projekcję odczytu |
| Stare `download` wysyła `.torrent` do roota workspace, zatrzymany do rezerwacji nazw | `acquisition.py:594–612` | nie używać tego wprost do nowego magnetu |
| Nowe D wyłącznie otwiera OFFER; A przełącza wszystkie/żadne, ale stan trwałego odcinka nie jest uwzględniany; CANDIDATES nie przyjmuje wyboru | `anishift/cli/interactive/anime.py:752–843,935–1010` | F6 zachowuje wdrożony toggle A i dodaje ochronę zleconych; D/I nadal wymagają zmiany UI |
| Stare D przekazuje same `ReleaseChoice`, bez wybranego wpisu AniList | `anime.py:1155–1167`; `anishift/cli/resident.py:270–275` | G musi przekazać kontekst do wspólnej bramki I-06 |
| Przyjęcie starego download zapisuje receipt przed HTTP i deduplikuje wszystkie zapisane hashe | `anishift/application/automation.py:3292–3383` | zachować write-before-effect; hash nie zastępuje odcinka |
| Stare subskrypcje bronią hasha i pary subscription/episode/repeat | `automation.py:3497–3554` | wspólne przyjęcie musi objąć także ten punkt |
| `AcquisitionConfirmation` opisuje wydanie/transfer, nie katalogowy odcinek; `WatchState.acquisitions` jest trwałe | `anishift/application/control.py:275–324,541–558` | rozszerzenie tego modelu, nie drugi magazyn zleceń |
| Wersja stanu 2; zapis temp + fsync + backup + replace; migracja wersji jest idempotentna | `anishift/application/watch_state.py:84–96,257–297,329–345` | nowa wersja 3, zachować ścisły odczyt 1/2 |
| `TransferInspector` zna priorytety i kompletność plików, ale zestaw bierze z wszystkich plików z priorytetem > 0 | `anishift/application/transfers.py:211–252,309–343` | źródłem zamówionego zakresu musi być owner, nie zmiana priorytetu w GUI |
| Dowód pliku wymaga `progress=1`, dostępności i zgodnego rozmiaru; stan `checkingResumeData` blokuje kompletność | `transfers.py:41–53,309–343` | reuse kontroli, kompletność per przypisany odcinek |
| Nazwy są spłaszczane przez `flat_layout`; Auto sprawdza `complete_files`; stare kończenie zwalnia cały hash | `transfers.py:260–279`; `automation.py:1049–1060,3722–3821` | nie zwalniać paczki po pierwszym gotowym odcinku; nie publikować niepełnego zestawu |
| Discovery pomija rootowe `temp/`, dotfiles, symlinki i junctions | `anishift/application/discovery.py:265–288` | staging w `temp/.acquisition/`, bez nowego skanera |
| Cleanup runów wymaga markera procesu; sesja runu to bezpośrednie dziecko `temp/` | `anishift/config/workspace.py:183–212`; `anishift/application/sessions.py:47–59` | transfer nie jest runem; jego staging nie może używać markera `RunSession` |
| qB API ma add/stop/start/remove/files/rename, nie ma `stopCondition` ani `filePrio` | `anishift/services/torrents/qbittorrent.py:112–173` | wąskie rozszerzenie API i protokołu |
| Manager zapisuje własność hashy przed add, pilnuje profilu, zwalnia z `deleteFiles=false` dopiero po kompletności całego transferu | `anishift/platform/qbittorrent_process.py:100–115,154–183,197–214,248–273` | zachować własność, rozszerzyć selekcję, nie modyfikować obcych torrentów |
| N-03 używało `stopped=false`, `stopCondition=MetadataReceived`, `autoTMM=false`, `contentLayout=Original`, `useDownloadPath=false`, potem 0 dla wszystkich i 1 dla wybranego | `scripts/tmp/magnet_probe.py:315–360` — lokalny artefakt nieśledzony w Git, niedostępny w czystym checkout; raport `workspace/.archive/acquisition/evidence/e1/magnet/probe-20260925T103445Z.json:13–54,539–564` | `stopped=true` nie zastępuje pobrania metadanych; kontrakt opcji jest zapisany w §8.4, pilot F0 ma własny odtwarzalny dowód; nie importować skryptu do aplikacji |
| Odpowiedź ponad 1 MiB jest odmawiana; eventy nie mają kontroli rozmiaru | `anishift/platform/local_control.py:477–484,655–668,689–695` | Q-08 wymaga wspólnej ochrony wysyłki i ograniczenia projekcji |
| Status wysyła wszystkie acquisitions i Bibliotekę; lista subskrypcji wysyła także wszystkie episodes i work_states | `automation.py:1339–1381,3113–3120,5360–5385`; publikacja `4868–4869` | odchudzić projekcje, pozostawić trwały ledger nienaruszony |
| Istnieje test z prawdziwymi prywatnymi qB, lokalnym HTTP i syntetycznym torrentem | `tests/platform/test_qbittorrent_process.py:305–478` | wzorzec izolacji i teardown; nie dowodzi jeszcze magnetu ani selektywnej paczki |

**Impact scan:** krytyczne granice to przyjęcie starej subskrypcji, pauza i shutdown, restart między zapisem a qB, wybór plików współdzielonego transferu, publikacja wieloplikowego odcinka, rezerwacje nazw i ReadyStore, Kosz/Undo, projekcje statusu używane przez panel oraz wcześniejsze dane bez AniList ID. Zakres testów w §10 pokrywa te granice.

## 6. Zakres wykonania

### In scope

- Rozszerzenie istniejących przyjęć w WatchState o tożsamość i pokrycie odcinków, selekcję i bezpieczne przekazanie do Auto; migracja 1/2 → 3.
- Magnet i priorytety w prywatnym qB; U-18, U05, P-06/P-07, restart, pauza, izolacja I-07, cleanup własnego stagingu.
- Wspólne przyjęcie dla nowego D/I/P, G i istniejącego callbacku subskrypcji; M-06 dla już trwających starych transferów.
- Stan odcinka i powód w odczytach ownera; oznaczenie niepewnego wyniku w Bibliotece bez zmiany jej pozostałych akcji.
- UI z §8.1, rejestr ścieżki ręcznej, pełne Q-08, pomiary Q-05, syntetyki, migracja na kopii i odbiór H2.

### Out of scope / deferred

- Nowe subskrybowanie przez S, zmiana ich harmonogramu, ponowienia automatu, H2 zawartości i `cases.jsonl` jako działająca baza z procesem cotygodniowych przeglądów — E3. E2 daje materiał w rejestrze; obserwacji nie awansuje automatycznie na etykiety.
- Kontrola U-07/U-08 i automatyczne drugie wydanie po braku napisów — E4. W E2 błąd istniejącego planera jest widoczny, bez automatycznego zakupu kolejnego wydania.
- Naprawa starego kalkulatora sezonów, przebudowa całego `anime.py`, zmiana filtrów G, usuwanie Nyaa — poza E2.
- Naprawa znanego `test_qbittorrent_process`, porządkowanie starych katalogów pytest, nowe funkcje Historii i Biblioteki — poza E2.

### Forbidden

- Odczyt korpusu egzaminacyjnego i ponowny egzamin; strojenie H1 lub rankingu przy implementacji selekcji plików.
- Drugi owner, scheduler, rejestr przyjęć albo odtwarzanie stanu wykonania z `decisions.jsonl`/Historii.
- Fallback „największy plik”, zaufanie samemu indeksowi Torrentio, pobranie całej paczki, start transferu przed zapisanym i sprawdzonym wyborem.
- Kasowanie plików użytkownika, `deleteFiles=true`, nadpisywanie istniejącego wyniku, modyfikowanie osobistego profilu qB.
- Obcinanie list IPC bez jawnego komunikatu, zwiększanie limitu ramki zamiast Q-08, snapshoty stronicowania z TTL.
- Nowa zależność bez zgody; ręczna zmiana zależności w `pyproject.toml`; refaktory poza koniecznym przepływem.

### Dozwolone decyzje lokalne

Nazwy prywatnych helperów i nowych typów, dokładny podział kodu w podanych modułach, fixture syntetyczne, etykiety zgodne znaczeniowo, rozmiar partii odczytów w limicie ramki, częstotliwość kontroli w ramach istniejącego pollera. Drobne wydzielenie kodu wspólnego do testowego helpera jest dozwolone, bez nowego frameworka. Wszystkie ważne decyzje modelu i lifecycle są poniżej, nie pozostają do wyboru writerowi.

### Stop / eskalacja

Zatrzymać dotkniętą fazę, gdy: qB zapisuje treść przed warunkiem metadanych; restart sam wznawia niezatwierdzony zakres; adapter G próbuje zgadywać sezon zamiast pozostawić `legacy-unkeyed`; nie można zatrzymać kolizji objętej gwarancją §8.3 przed drugim skutkiem; konieczna jest zmiana H1, rankingu, właściciela stanu, schematu poza opisanym rozszerzeniem albo nowa zależność. Znane ograniczenie niepowiązanych subskrypcji do E3 nie jest nowym blokerem. Zgłosić dowód i najwęższą zmianę planu orkiestratorowi. Lokalny bug realizacji kontraktu naprawić w tej samej fazie, potem powtórzyć właściwy test.

## 7. Kontekst wykonawcy i mapa plików

Czytać: ten plan → źródła §4 → scoped AGENTS dla dotykanych obszarów → `coding` z `python.md`, `testing.md`, `comments-docstrings.md` → wskazane w §5 symbole oraz ich konsumentów i testy. Brief fazy według `.agents/skills/subagent/assets/SUBAGENT-BRIEF.template.md`: baseline, zakres zapisu, zakazy, wejściowy gate i wymagane wyniki. Nie przekazywać surowych danych właściciela ani tokenów.

Mapa jest expected touch set, nie poleceniem utworzenia wszystkich możliwych abstrakcji. Ścieżki istniejące sprawdzono; nowe są jawnie oznaczone.

| Operacja | Ścieżki | Rola |
| --- | --- | --- |
| MODIFY | `anishift/application/control.py`, `watch_state.py` | schema 3, pokrycie odcinków, dowody publikacji, migracja |
| MODIFY | `anishift/application/acquisition.py`, `automation.py`, `control_views.py`, `__init__.py` | przygotowanie oferty, wspólne przyjęcie, IPC, lifecycle, projekcje |
| MODIFY | `anishift/application/transfers.py` | mapowanie listy qB, wybór, dowody per odcinek, serializacja zakresu współdzielonego hasha |
| CREATE | `anishift/application/acquisition_staging.py` | wąski helper I/O kopiowania/publikacji i cleanupu stagingu; bez własnego stanu trwałego |
| CREATE | `anishift/application/acquisition_decisions.py` | zamknięte schematy dowodowych wpisów i zapis JSONL na zlecenie ownera |
| MODIFY | `anishift/application/subscriptions.py` | wyłącznie adaptacja wejścia starej subskrypcji do wspólnego przyjęcia i zachowanie taken; bez nowego schedulera |
| MODIFY | `anishift/services/torrents/qbittorrent.py`, `types.py`, `anishift/platform/qbittorrent_process.py` | metadata-only, filePrio, obserwacje, własność i serializacja mutacji |
| MODIFY | `anishift/platform/local_control.py` | limit każdej wysyłanej ramki, jawny event błędu |
| MODIFY | `anishift/cli/resident.py`, `interactive/anime.py`, `interactive/state.py` | D/I/P/U05, stan ownera, zwięzłe subskrypcje i status, obsługa zdarzeń limitu |
| MODIFY, jeśli wymaga konsument | `anishift/cli/interactive/progress.py`, `anishift/bootstrap.py`, `anishift/application/ready.py` | etykiety i wiring; powiązanie zlecenia z istniejącym wynikiem |
| MODIFY | istniejące `tests/application/test_{watch_state,acquisition,transfers,automation}.py`, `tests/services/torrents/test_qbittorrent.py`, `tests/platform/test_local_control.py`, `tests/cli/test_{resident,interactive_anime,interactive_state}.py` | kontrakty, regresje i UI |
| CREATE | `tests/application/test_acquisition_staging.py`, `test_acquisition_decisions.py`, `tests/integration/test_episode_download.py` | granice plików, rejestr, prawdziwy qB i pipeline |
| MODIFY, tylko konieczne helpery | `tests/integration/harness.py`, `tests/integration/test_subscription_pipeline.py`, `tests/platform/test_qbittorrent_process.py` | reuse syntetyków i bramka starego wejścia; nie zmieniać znanej zawodnej asercji zamykania |
| READ ONLY | `episode_identity.py`, reguły `episode_selection.py`, `discovery.py`, `config/workspace.py`, `sessions.py`, `products.py`, `ready.py`, testy istniejącego Auto/Library/Undo | źródła reguł i chronione kontrakty; zmiana tylko jeśli dowód wykaże konieczne wpięcie |
| MODIFY podczas wykonania | scoped `AGENTS.md` dotkniętych modułów; `docs/work/acquisition/{spec.md,ux.md,masterplan.md}` | aktualny kontrakt nowych mutacji, klawiszy i status etapu, bez rozszerzania zakresu |
| CREATE podczas wykonania | `docs/work/acquisition/outcomes/e2.md` | dowody według §12 |
| DELETE | brak | G i stare zaplecze pozostają |

**Zakres tej sesji planistycznej:** tylko utworzenie niniejszego pliku. Powyższa mapa dotyczy przyszłego wykonania po review planu, nie upoważnia planisty do innych edycji.

## 8. Target design

### 8.1 UI i moment zlecenia

1. **Odcinki:** zaznaczalne są wyemitowane, niezlecone odcinki. Space/Enter przełącza bieżący; A: gdy wszystkie dostępne są zaznaczone, odznacza je, inaczej zaznacza wszystkie. Z zachowuje istniejącą składnię `1,3,9-12`/`5-`, zastępuje zaznaczenie, nieistniejący numer nie zmienia szkicu. Zleconego ani „możliwie zleconego” odcinka nie da się dodać przez D/A/Z; notka kieruje do P. „Możliwie zlecony” jest stanem niepewności legacy z §8.3, nie dowodem przyjęcia ani Pobrano.
2. **D:** jedno jawne polecenie użytkownika uruchamia w tle dobór i przyjęcie sugestii kolejno dla wybranych odcinków; brak osobnego ekranu U04 i drugiego Enter. Odcinki bez sugestii lub z błędem źródła mają własny powód i nie blokują pozostałych. `niepewny` może być sugestią bez dodatkowego potwierdzenia zgodnie z U-03/R-06. Nigdy automatyczny `niezgodny`.
3. Panel wysyła D jako **jedno polecenie ownera z ograniczoną listą kluczy i jednym `command_id`** (§8.7). Owner dobiera i przyjmuje odcinki kolejno, zapisując każde przyjęcie przed efektem; zdarzenia przekazują postęp oraz powód wyniku każdego odcinka. Lista pokazuje „Szukam wydania E…”. Esc/Tab zmieniają tylko widok i jego generację; także rozłączenie panelu nie przerywa partii ownera (P-04, Q-01). **Niedokończona partia nie jest wznawiana po restarcie ownera**: przyjęte odcinki pozostają trwałe, reszta jest niezlecona. UI przy wysłaniu informuje „Po restarcie niezlecone odcinki trzeba wybrać ponownie”, a przy odczycie przerwanej partii pokazuje jej status i odświeżone stany odcinków. Po rozliczeniu partii przejście do Przetwarzania tylko, gdy użytkownik nadal jest na ekranie/generacji rozpoczęcia; widoczna lista niezleconych z powodami, a zaznaczenie znika tylko dla przyjętych.
4. **I:** od razu lista wydań podświetlonego odcinka, niezależna od zaznaczenia innych odcinków. Ranking, filtrowanie rozdzielczości i `?` dla braków jak E1. Sugestia jest oznaczona na tej liście, a powód pod nią. Space/Enter zaznacza konkretne wydanie; zaznaczenie następnego zastępuje poprzednie, bo jeden odcinek ma jeden wybór. D pobiera zaznaczone, a bez zaznaczenia wydanie pod kursorem. Nie dodawać wielokrotnego pobierania wariantów tego samego odcinka przez A/Z.
5. Jawny wybór `niepewnego` lub `niezgodnego` wymaga potwierdzenia R-04 przed skutkiem, również gdy użyto D bez zaznaczenia. Potwierdzenie jest związane z konkretną parą i oceną; zmiana wyboru je unieważnia. `supported=False` pozostaje niedostępny. Szczegóły wyświetlane są przed D; nie powstaje dodatkowy kreator zwykłego pobrania.
6. **P:** działa dla zleconego/pobranego/gotowego oraz **„możliwie zleconego”** odcinka. Jednowierszowe „Pobrać E… ponownie? Obecne pliki zostają. Enter tak · Esc nie”, a dla niepewnego legacy „E… może być już zlecony. Pobrać mimo to? Obecne pliki zostają. Enter tak · Esc nie” → istniejący U04 tylko tego odcinka z sugestią i akcją Pobierz; I może zmienić wybór. Dopiero D albo Enter na Pobierz zleca nową próbę. Znane poprzednie pary są wykluczone; brak alternatywy to jawny brak, nie ponowienie tej samej pary. Przy nieznanej poprzedniej parze podgląd jawnie mówi, że nie można potwierdzić odmienności wydania (§8.6). P pozostaje wyjątkiem z potwierdzeniem i podglądem P-05, także jako wyjście z możliwego konfliktu; nie dodawać „Ustal cel” dla starych zleceń.
7. **S:** w E2 nie zleca niczego, pokazuje notkę „Subskrypcje: wróć do tytułów i użyj G”. Stopka oznacza niedostępność S, nie obiecuje nowego szkicu. Pod G stare O i sortowanie S pozostają jak dotąd.
8. **U05:** Enter na problemie „Nie ustalono pliku w paczce” otwiera listę obsługiwanych plików wideo z pełnymi względnymi ścieżkami qB i rozmiarami. Enter wiąże dokładny plik z odcinkiem, dołącza jego sidecary; Esc nic nie zmienia. Nie pokazywać napisów jako wybieralnych filmów mimo przykładowego wiersza ASS w starej makiecie.
9. Odcinki, Przetwarzanie i Biblioteka dostają stan/powód z ownera. „Pobrano” nie znaczy „Gotowe”. Niepewność H1 jest osobnym oznaczeniem wyniku i pozostaje po restarcie. Zachować 50-kolumnowy terminal, wspólny renderer, focus pól, generacje, brak I/O w renderze.

### 8.2 Jeden model przyjęć, dwa poziomy tożsamości

Rozszerzyć **`WatchState.acquisitions`**, nie dodawać równoległego `orders.json` ani drugiej rootowej listy zleceń. Jeden `AcquisitionConfirmation` pozostaje właścicielem fizycznego transferu/operacji. Dodać opcjonalny, jawnie wersjonowany wariant selektywny oraz kolekcję przypisań odcinków wewnątrz niego. Stare rekordy pozostają wariantem legacy. Nie tworzyć potwierdzeń z samych `taken_episodes`: model wymaga `info_hash`, `directory` i `required_files`, a poller i zwalnianie przechodzą po potwierdzeniach transferów. Bramka ownera korzysta z historii subskrypcji tylko do odczytu (§8.3).

Minimalny trwały kontrakt nowego wariantu:

- transfer: istniejące `operation_id`, `info_hash`, stan, origin i akcje; dodatkowo tryb selektywny, względny katalog stagingu, faza metadanych/selekcji, rewizja wybranego zakresu oraz ostatni potwierdzony zakres priorytetów;
- przypisanie odcinka: `EpisodeKey`, własny stabilny identyfikator przyjęcia, czas, źródło wejścia (`manual`/`legacy`), wskazanie poprzedniego przyjęcia przy P, wybrana referencja Torrentio, zapisany runtime target H1, werdykt i powód, jawne potwierdzenie odstępstwa R-04;
- pliki: dla każdego qB index, oryginalna względna ścieżka, dokładny rozmiar, rola wideo/sidecar; `fileIdx` źródła zachowany wyłącznie jako wskazówka;
- przekazanie: zarezerwowane płaskie nazwy wyjściowe, dowody lokalnej kopii/publikacji, stan całego zestawu, powiązanie z `group_id`, `request_id` istniejącego przetwarzania i późniejszym `set_id`;
- magnet może być odtworzony z hasha i zwalidowanych publicznych trackerów zapisanej referencji; nie zapisujemy pełnych URL-i z poświadczeniami ani sekretów. Pełna lista kandydatów należy do rejestru dowodowego, nie do ledgeru.

**Źródło prawdy:** nowe przyjęcie, przypisanie plików i powód są w WatchState; historyczne taken pozostaje w `SubscriptionService`, tylko do odczytu według §8.3. Status katalogowy to projekcja `EpisodeListing` + zapisane przyjęcia i ten odczyt legacy + istniejące `ProcessingRequest`/`ReadyGroup`. Stan qB jest obserwacją transportu, nie pamięcią zleceń. Wykonawca nie utrzymuje drugiej kopii stanów „Gotowe” obok dowodów istniejącego pipeline.

**Deduplikacja:** logicznie `EpisodeKey`; fizycznie po odczycie metadanych `(info_hash, oryginalna ścieżka pliku wideo)`. Jeden hash może mieć wiele odcinków, ale jedno fizyczne wideo nie może uruchomić dwóch przebiegów dla dwóch aliasów katalogowych. Taki konflikt jest widoczny i wymaga wyjaśnienia, nie automatycznej produkcji dwóch wyników. Zwykłe D nie tworzy nowego przyjęcia, jeśli kiedykolwiek istniało przyjęcie danego klucza, także zakończone błędem; kontynuacja tej samej operacji to wznowienie, a nowe wydanie to P.

Owner sprawdza deduplikację i zapisuje przypisanie razem z receipt **przed** jakimkolwiek add/filePrio/start. Szybkie dwa D lub D/G po wolnym HTTP trafiają do jednej serializowanej bramki. Rewizja transferu chroni przed powrotem starszego workera po dołożeniu odcinka. I/O działa w istniejącej puli; zmiany WatchState wracają do ownera. Nie tworzyć nowej kolejki schedulera.

### 8.3 Pomost G, stare subskrypcje i migracja

**Jedna reguła G i starej subskrypcji:** `ResidentSession.download` przekazuje dostępne AniList ID i zapisany offset kontekstu G; callback subskrypcji przekazuje jej `anilist_id` i `episode_offset`. `Subscription.anilist_id` jest opcjonalne (`subscriptions.py:276`, ścieżki `:893,:968,:991`), nie wolno zakładać powiązania. Tylko gdy AniList ID istnieje, wyliczyć kandydacki numer lokalny jako **stary numer − zapisany offset**. Numer musi być poprawnym numerem celu; nie zaokrąglać, nie zgadywać offsetu. Zbudować istniejący `identity_target` i wymagać H1 **`match`** na dostępnych danych wydania/pliku dla tego klucza. Dopiero wtedy przypisać `EpisodeKey` i deduplikować różne hashe. Sam numer, ID ani wynik `insufficient_evidence` nie potwierdzają klucza. To adapter przyjęcia, nie naprawa kalkulatora G ani H1.

**`legacy-unkeyed`:** brak ID, poprawnego numeru lub H1 `match` pozostawia rekord bez potwierdzonego `EpisodeKey`. Deduplikacja działa po hashu, a po uzyskaniu metadanych po parze hash + oryginalna ścieżka wideo; nie utożsamiać różnych odcinków paczki. Możliwy konflikt logiczny wymaga tego samego znanego AniList ID. **Gdy numer po odjęciu zapisanego offsetu jest poprawny, konflikt dotyczy tylko pary (ID, numer lokalny)**, nawet bez H1 `match`; inny numer tej samej serii nie jest blokowany. **Na całe ID konflikt rozszerza się tylko przy brakującym lub niepoprawnym numerze lokalnym.** Kandydacki numer ogranicza konflikt, ale sam nie potwierdza klucza. `episode_states` pokazuje dotknięte odcinki jako **„możliwie zlecone”**, z powodem i dostępnym P: zwykłe D odmawia, natomiast jawne P z potwierdzeniem i podglądem pozwala przyjąć wybrany odcinek mimo tej niepewności (§8.6). Ta sama reguła zakresu chroni odwrotną kolejność wejść. Brak ID nie jest globalnym konfliktem ze wszystkimi seriami, inne ID także nie blokuje celu (nie znosi to deduplikacji fizycznej). **Subskrypcja bez AniList ID nie jest blokowana przez nową drogę dla innego hasha**: to znane ograniczenie I-06 do E3, nie gwarancja braku duplikatu odcinka. Nie wiązać jej automatycznie ani nie zmieniać harmonogramu w E2.

**Uwaga wykonawcza F1:** w chwili przyjęcia G i subskrypcji wydanie Nyaa nie ma nazwy pliku, więc H1 daje `insufficient_evidence` i rekord pozostaje `legacy-unkeyed` z `LegacyScope` (ID, numer lokalny albo całe ID). Nieznany offset kontekstu G oznacza zakres całego ID. Potwierdzenie `EpisodeKey` po metadanych transferu (nazwa pliku z qB) nie jest wykonywane w E2 i przechodzi do E3 (§13).

**Wpięcie, nie import przyjęć:** bramka ownera czyta `taken_episodes`/`EpisodeOrder` z `SubscriptionService` **tylko do odczytu**, według powyższej reguły ID, offsetu i H1. Są pamięcią zlecenia, nigdy dowodem Pobrano. Jeśli zachowane dane wydania nie pozwalają na H1 `match`, wynik pozostaje `legacy-unkeyed`; taken z pasującym ID i poprawnym numerem lokalnym daje możliwy konflikt tylko tego numeru, a dopiero brak lub niepoprawność numeru uniemożliwiające zawężenie dają konflikt całego ID. Nie tworzyć `AcquisitionConfirmation` bez hasha ani fikcyjnego katalogu/listy plików. Nie kopiować taken do ledgeru, nie zmieniać aktywności, terminów ani zakresów subskrypcji; poller/release nie dostają dodatkowych transferów z tego odczytu. P z „możliwie zleconego” tworzy nowe rzeczywiste przyjęcie, nie poprawia ani nie importuje historycznego taken.

**Migracja WatchState:** schema 3, odczyt 1/2/3 ze ścisłą walidacją wersji. Wszystkie dotychczasowe pola i dowody pozostają. Stare acquisitions bez nowej tożsamości są jawnie legacy, nie stają się pobrane ani selektywne. Migracja jest idempotentna, bez importu taken, HTTP i uruchamiania pracy; liczba potwierdzeń transferów nie rośnie. Powiązania uzyskane później według powyższej reguły są osobną mutacją ownera, nie heurystyczną zmianą danych w parserze JSON.

Przed pierwszym zapisem schema 3 zabezpieczyć **oba pliki**, `state.json` i istniejący `subscriptions.json`, obok oryginałów, z nazwą wskazującą migrację E2. Brak `subscriptions.json` jest odnotowany, nie wymaga pustego pliku. Istniejącej kopii nie nadpisywać; błąd kopii blokuje pierwszy zapis nowego formatu. Test sprawdza byte-identical backup, niezmienność oryginalnego subscriptions, restart po każdej granicy i brak nowych pobrań. Nie zmieniać schematu subskrypcji 4 w E2. Cofnięcie programu wymaga zatrzymania rezydenta i odtworzenia kopii — starszy loader nie może po cichu usunąć nowych dowodów.

**M-06:** istniejące aktywne legacy transfery pozostają w swoich katalogach i kończą istniejącą drogą. Nie przenosić ich do stagingu i nie zmieniać priorytetów podczas migracji. Ich wynik otrzymuje ustawienia z chwili przyjęcia do przetwarzania. Nowy odcinek wskazujący hash takiego transferu może tylko przyłączyć się do już zamówionego i dowiedzionego pliku; nie wolno ustawić wszystkim legacy plikom priorytetu 0. Niejednoznaczność daje problem, nie drugie add. Po końcu G nadal korzysta ze wspólnej bramki przyjęć, a nie z niezależnego sprawdzania hashy.

### 8.4 Magnet, mapa plików i zakres paczki

1. Przyjęcie nowej sugestii odświeża dane wyboru przez istniejącą usługę E1; źródło Torrentio zawsze czytane na żywo. D robi jeden odczyt na odcinek, nie osobno do podglądu i ponownie do startu. AniList/ani.zip respektują Q-03, lecz owner ponownie sprawdza emisję, zapisane przyjęcia i ważność kontekstu; nie ufa przesłanemu z UI stanowi ani werdyktowi.
2. Nowy hash trafia do `workspace/temp/.acquisition/<operation_id>/data/`. Konstruktor ścieżki należy do aplikacji i używa workspace z istniejącej fasady. Transfery nie używają `.anishift-owner` przeznaczonego dla `RunSession`; generic cleanup runów ich nie usuwa. Katalog/rodzice nie mogą być symlinkiem ani junction. Ścieżki API są walidowane jako względne i pozostające pod tym katalogiem, również pod Windows (drive/UNC/`..`/ADS).
3. Jawna metoda metadata-only korzysta z opcji sprawdzonych N-03: `stopCondition=MetadataReceived`, `stopped=false`, `autoTMM=false`, `contentLayout=Original`, `useDownloadPath=false`. Stare `add_torrent(stopped=True)` zachowuje swój kontrakt. Magnet budowany standardowym kodowaniem URL z hasha i zwalidowanych trackerów, nigdy konkatenacją surowych pól z UI.
4. Odczyty metadanych prowadzi istniejący transfer poller, bez minutowego oczekiwania w handlerze IPC ani na wątku ownera. `checkingResumeData` to przejściowe uzgadnianie, nie brak plików i nie kompletność. Czekamy na potwierdzone zatrzymanie przed priorytetami; brak zatrzymania daje problem i próbę stop, bez startu treści. Tymczasowy `T_metadane=600 s` według próby N-03 oznacza „Nie uzyskano listy plików”, nie „martwy torrent”; wznowienie jest jawne i używa tego samego przyjęcia. Zastój korzysta z obecnego `transfer_stall_s`, bez automatycznej zmiany wydania.
5. **U-18:** najpierw dokładna unikalna nazwa wideo z Torrentio w liście qB. Przy kolizji/braku nazwy: H1 na pełnych oryginalnych ścieżkach qB z zapisanym celem i nazwą wydania, bez dowodów katalogowych. Automatyczny wybór tylko przy jednym rozstrzygającym `match`. Brak jednego wyniku → trwałe „Nie ustalono pliku w paczce”, U05; nie wybieramy najwyżej ocenionego z dwóch równorzędnych plików ani samego `insufficient_evidence`. Świadoma zgoda R-04 na konkretny kandydat nie jest zgodą na dowolny inny plik paczki.
6. U05 potwierdza istniejący qB index **wraz ze ścieżką i rozmiarem oraz rewizją listy**, nie sam index. Zmiana metadanych/rewizji odmawia ze wskazówką odświeżenia. Ten sam fizyczny plik już przypisany innemu celowi nie jest przyjmowany ponownie.
7. Sidecary: ten sam katalog w torrencie i dokładnie ten sam stem co wybrane wideo, rozszerzenie napisów/audio obsługiwane przez istniejące discovery. Nie rozszerzać selekcji po prefiksie (`01` nie dobiera `010`, `01.en` ani pliku innego katalogu); fonty, okładki, NCOP i inne wideo poza zakresem. Przy spłaszczeniu zachować wspólny stem całego zestawu i reguły kolizji istniejącego `flat_layout`.
8. Owner zapisuje pełny docelowy wybór jako **sumę plików wszystkich przyjętych odcinków tego transferu**. Dla nowej paczki: 0 dla reszty, 1 dla sumy; odczyt zwrotny `files()` musi potwierdzić zakres przed startem. Ustawienie priorytetów i resume są idempotentne względem rewizji. Dołożenie odcinka zatrzymuje/uzgadnia wspólny transfer, zapisuje nową sumę, ustawia ją i wznawia po weryfikacji. Nie usuwa plików odcinka już pobieranego/publikowanego. Późny worker starszej rewizji nie może cofnąć nowej sumy.
9. Każda mutacja managera sprawdza własność profilu **i hasha**. Hash obecny w qB bez zapisanego przyjęcia nie jest przejmowany. Po restarcie nie wykonywać ślepego add: najpierw uzgodnić hash, staging i zakres z qB. Niejednoznaczne wysłanie pozostaje chronione jako problem; brak odpowiedzi IPC nie oznacza braku zlecenia.

### 8.5 Kompletność, przekazanie do Auto i cleanup

**Jednostką gotowości jest zapisane przypisanie odcinka.** Wszystkie jego wymagane pliki: qB `progress=1`, brak stanu sprawdzania/przenoszenia, bezpieczna ścieżka, plik dostępny i o dokładnym rozmiarze. Nie czekać na 100% całej paczki; nie ufać samemu torrent progress ani samemu istnieniu pustego pliku.

Nowa droga nie zmienia nazw plików w qB na nazwy workspace. Zachowuje oryginalną mapę w stagingu i **kopiuje gotowy zestaw** do publikacji; nie tworzy hardlinku do danych nadal zapisywanych przez qB. Koszt chwilowej drugiej kopii jest świadomą ceną prostego oddzielenia Auto od wspólnych kawałków. Jeżeli Windows nie pozwala uzyskać stabilnego odczytu, krótko zatrzymać własny transfer, ponownie sprawdzić dowody, skopiować zestaw i wznowić pozostałe odcinki; nie czekać na zakończenie paczki.

Kolejność odporna na restart:

1. Owner rezerwuje cały płaski zestaw nazw, uwzględniając pliki workspace/ready, inne przyjęcia, Kosz/Undo i relokacje; zapisuje zamiar publikacji przed kopiowaniem. Kolizja daje nowe wolne nazwy, nigdy overwrite. Nowe P dostaje nowe nazwy, nie zmienia starego wyniku.
2. Worker kopiuje do prywatnej części stagingu i sprawdza kompletność kopii; zapisany dowód obejmuje plik źródłowy i kopię. Dla crash-gap publikacji użyć mocnej tożsamości pliku zgodnie z istniejącymi wzorcami ReadyStore/publikacji, nie tylko rozmiaru.
3. Publikacja poszczególnych plików do root jest wyłączna, bez replace istniejącego celu. Owner chroni **cały zarezerwowany zestaw** przed Auto do momentu potwierdzenia publikacji wszystkich jego elementów i trwałego zapisu. Zdarzenie filesystem po pierwszym MKV nie uruchamia przetwarzania bez sidecara. Ochrona odtwarza się z WatchState przed pierwszym skanem po restarcie.
4. Po zapisie pełnego dowodu zestawu owner emituje istniejące `files_changed` i wpuszcza dokładnie tę grupę do istniejącego Auto. Powiązanie z `ProcessingRequest` utrwala się w tej samej granicy przyjęcia runu, więc crash między zdarzeniem a odpowiedzią nie tworzy drugiego runu. Ustawienia snapshotowane jak dotąd przy przyjęciu do przetwarzania.
5. Sukces grafu, publikacja ReadyStore i potwierdzenia produktów wyznaczają Gotowe oraz `set_id`. Porażka planowania/przetwarzania nie cofa pamięci przyjęcia i nie uruchamia nowego pobrania. Oznaczenie niepewnego wyniku jest projekcją zachowanego przyjęcia po relokacji, nie domysłem z nazwy.
6. Wspólny torrent zostaje do czasu rozliczenia wszystkich jego odcinków. Dopiero po `release_completed` przez managera z `deleteFiles=false` i trwałym dowodzie zwolnienia wykonać cleanup własnego stagingu. **Oryginał każdego zamówionego pliku qB usunąć tylko przy trwałym dowodzie mocnej tożsamości jego opublikowanej kopii** (także po jej dowiedzionej relokacji do ready); sam rozmiar, stan Gotowe lub receipt zwolnienia nie wystarcza. Ta sama reguła obejmuje sidecary. Usunąć też własne niezlecone fragmenty, puste pozostałości i pliki robocze z manifestu; nie usuwać zamówionego pliku bez dowodu eksportu, nawet pustego. Pełny sukces wszystkich przypisań pozostawia pusty katalog operacji, który można usunąć. Manifest, brak linków i dowód zwolnienia chronią obce dane. Nie używać globalnego `rmtree(workspace/temp)`.

Przerwanie, anulowanie lub P nie są dowodem eksportu ani zgodą na usunięcie zamówionego oryginału (I-04). Bez powyższego dowodu plik pozostaje w stagingu do jawnego wznowienia/obsługi; nie wymagać wtedy pustego katalogu operacji. Cleanup po sukcesie obejmuje zarówno oryginały qB, jak i kopie tymczasowe z dowiedzionym eksportem. Błąd cleanupu pozostawia izolowany katalog, widoczny problem i ponowienie tego samego cleanupu po restarcie, nie nowe pobranie.

### 8.6 P i współbieżność prób

P tworzy nowe przyjęcie skorelowane z poprzednim. Wykluczenie obejmuje poprzednią **parę hash/plik**, a nie cały hash paczki; alias tej samej pary w odpowiedzi Torrentio nie omija zakazu. Przy nieustalonym pliku poprzedniej próby wykluczyć jej kandydata i nie ufać zmianie samego `fileIdx`; U05 dodatkowo wykrywa zbieżność fizycznego pliku.

**Wyjście z „możliwie zleconego”:** P nie wymaga istniejącego przyjęcia z potwierdzonym kluczem. Owner wiąże ofertę z wybranym `EpisodeKey` i referencjami do źródeł możliwego konfliktu (istniejące acquisition albo ID subskrypcji i zapis taken), sprawdza je ponownie przy zatwierdzeniu i zapisuje świadome odstępstwo przy nowym przyjęciu. Potwierdzenie dotyczy tylko tego klucza i obejrzanego konfliktu, nie całego ID ani przyszłych zleceń. Zmiana konfliktu wymaga ponownego potwierdzenia. Nie zgadywać poprzedniego hasha/pliku; wykluczać znane pary/kandydatów, a brak danych ujawnić w podglądzie. Fizyczna deduplikacja nadal obowiązuje. Bez potwierdzonej tożsamości nie zatrzymywać ani nie zmieniać niepewnego starego transferu — zachować go i jego pliki. Po nowym przyjęciu `episode_states` pokazuje rzeczywisty stan tego przyjęcia dla klucza, nie zasłania go odziedziczonym konfliktem; pozostałe odcinki zachowują własne stany. Zapisać `correction` z powodem `legacy_conflict_override`, kluczem, referencjami konfliktu i identyfikatorem nowego przyjęcia, bez fikcyjnego poprzedniego acquisition. Trwałe odstępstwo należy do WatchState, JSONL jest kopią dowodową.

Jeśli potwierdzone poprzednie pobieranie tego odcinka jest aktywne, nowe przyjęcie najpierw zapisuje zamiar zastąpienia i zatrzymuje stary zakres: prywatny samodzielny torrent bez usuwania danych, wspólna paczka odejmuje tylko pliki niepotrzebne pozostałym przyjęciom. Dopiero potwierdzenie pozwala wystartować nowe. Już przyjętego runu Auto nie zabijać — istniejący snapshot i poprzedni wynik pozostają; nowe przyjęcie ma odrębny zestaw nazw. P nie zmienia celu ani zleceń innych odcinków.

Przyjęcie ręczne podczas starej subskrypcji rezerwuje potwierdzony klucz we wspólnej bramce; callback stosuje §8.3, w tym ograniczenie dla subskrypcji bez AniList ID. Maszyna celów E3 później konsumuje te same trwałe przyjęcia; E2 nie implementuje jej liczników trzech prób.

### 8.7 API ownera i sesja panelu

Nowe operacje są jawne, z strict `encode_view/decode_view`, bez osłabiania istniejących kontraktów E1. `PROTOCOL_VERSION` pozostaje bez zmian; nowe DTO/metody są dodatkiem, a zmienione projekcje list mają aktualizowanych konsumentów w tej samej fazie.

| Operacja | Wejście | Wynik i skutki |
| --- | --- | --- |
| `episode_download` | lista 1–100 unikalnych `EpisodeKey` jednego wpisu, jeden `command_id` | trwały receipt przyjęcia polecenia partii → asynchroniczny dobór i przyjęcia kolejnych odcinków → zdarzenia wyników/powodów per odcinek; bez oczekiwania IPC na źródła ani metadane qB; ponad limit jawna odmowa przed skutkiem, bez dzielenia przez panel |
| `episode_offer` | klucz, opcjonalnie identyfikator zastępowanego przyjęcia albo tryb P dla możliwego konfliktu legacy | oferta do I/P z ograniczonym, sesyjnym identyfikatorem wyboru; owner wiąże rzeczywiste źródła konfliktu; bez pobierania |
| `episode_choose` | identyfikator oferty, dokładna para kandydata, potwierdzenie R-04 i ewentualnego konfliktu legacy, opcjonalne poprzednie przyjęcie, `command_id` | przyjęcie dokładnie obejrzanego wyboru po walidacji; wygasły/obcy wybór lub zmieniony konflikt odmawia; P z możliwego konfliktu zapisuje odstępstwo §8.6 |
| `episode_files` | identyfikator przyjęcia | U05 z rewizją i listą bezpiecznych plików; bez skutku |
| `episode_file_choose` | przyjęcie, rewizja, index/path/size, `command_id` | zapis mapowania, potem aktualizacja priorytetów |
| `episode_states` | AniList ID i ograniczona lista numerów widocznego wpisu | stany/powody z ledgeru i odczytu legacy §8.3; konflikt daje „możliwie zlecony” z dostępnym P tylko dla dotkniętych numerów; rzeczywiste przyjęcie klucza ma pierwszeństwo; bez sieci katalogowej i zgadywania H1 |
| istniejący `download` i callback starej subskrypcji | wybory + dostępny kontekst katalogowy | ta sama bramka deduplikacji; zgodność starego wyniku `DownloadReceipt` |

Przy ponad 100 zaznaczonych odcinkach UI przed wysłaniem D pokazuje **„Zaznacz najwyżej 100 odcinków”** i pozostawia zaznaczenie bez zmian; nie wysyła polecenia ani nie dzieli go na partie. Walidacja ownera pozostaje niezależna.

Oferta I/P jest pamięcią jednej jawnej interakcji, nie cache Torrentio: ograniczona liczba aktywnych ofert per sesja, zastępowana nową, usuwana po rozłączeniu; nie jest trwałym stanem przyjęcia. **Q-02 uzasadnia sesyjny `episode_offer`:** zatwierdzenie obejrzanego wyboru zużywa tę ofertę, bez drugiego zapytania Torrentio. Owner przechowuje jej rzeczywiste wejścia oceny do rejestru, zamiast ufać ocenie/hashom dostarczonym przez panel. Zmiana instancji ownera lub danych unieważnia ofertę i wymaga ponownego obejrzenia; restart nie zamienia starego potwierdzenia w zgodę na nowe wydanie. D bez podglądu buduje i zużywa ofertę wewnątrz jednego use case na odcinek.

Powtórzony `command_id` zwraca ten sam receipt, sprawdzany przed HTTP; zmieniona lista z tym ID odmawia. Receipt D potwierdza **przyjęcie polecenia partii**, nie wszystkich pobrań. W istniejącym mechanizmie receipts zachować ograniczoną listę kluczy, identyfikator instancji ownera i końcowy wynik partii; każde przyjęcie odcinka jest trwale skorelowane z command ID przed efektem. Kolejka pozostałych kluczy istnieje tylko w pamięci ownera. Po restarcie niedokończony receipt poprzedniej instancji jest odczytywany jako „partia przerwana”; ponowione ID nie wznawia reszty, stany przyjętych wynikają z ledgeru, reszta pozostaje niezlecona. Ponowne świadome D z nowym ID może zlecić resztę; wspólna bramka chroni wcześniej przyjęte. Nie powstaje trwały scheduler partii. Zdarzenia per odcinek są projekcją, nie jedyną pamięcią przyjęć. Panel bez sesji ownera zachowuje odczyty E1, lecz nowe mutacje wymagają połączenia z rezydentem, bez lokalnego obejścia trwałości.

### 8.8 Rejestr `decisions.jsonl`

Zapisuje wyłącznie owner, helper zajmuje się formatem i dopisaniem. Lokalny JSONL pod ścieżką wyprowadzoną z `WatchStateStore`, nie z CWD. Schemat zamknięty, `schema=1`, wersja H1 i parametrów, UTC, `kind`, `EpisodeKey`, ścieżka `manual`, identyfikator korelacji odczytu/przyjęcia. Angielskie identyfikatory techniczne, polskie komunikaty dopiero w UI.

- **`check`:** jedna zwarta linia na rzeczywisty odczyt Torrentio/ani.zip, także pusty/błędny/429, przekazana ownerowi bezpośrednio po odczycie. Cache hit nie jest odczytem źródła. Współdzielony odczyt ani.zip nie może udawać wielu pomiarów dla każdego zaznaczonego odcinka. Zachować rozróżnienie odczytu wpisu i znanego celu; `aired_at` tylko z AniList, nigdy z daty fallback ani.zip. Dla ani.zip zapisać obecność/brak `length`, bez dodawania kontroli H2. Wyniki według §5.6 planu przepływu; analiza widzi luki zamiast fikcyjnych odczytów.
- **`selection`:** rzeczywiste wejście H1 (`target` dokładnie z E1, bez dodanego roku/dowodów), wejścia rankingu, hash i względna nazwa/ścieżka, fakty i ocena każdego kandydata, wykluczenia P, wybór/powód. Dodatkowy kontekst katalogowy może być tylko osobnym polem, nigdy dopisanym do `target`. Wpis przy starcie przyjęcia i każdym jawnym wyborze; przy samym przeglądaniu I tylko po zmianie kandydatów/decyzji, bez dopisywania identycznych snapshotów. Każdy faktyczny odczyt nadal ma `check`.
- **`correction`:** P, jawna zmiana wydania i U05, z relacją do przyjęcia. Przy P jednoliniowy wybór powodu `quality` / `wrong_episode` można połączyć z istniejącym potwierdzeniem. P z „możliwie zleconego” zapisuje `legacy_conflict_override` i referencje według §8.6, bez wymagania fikcyjnego poprzedniego przyjęcia. Nie wyprowadzać `wrong_episode` z samej zmiany jakości ani niepewności legacy. Zwykły pierwszy wybór I nie jest automatycznie korektą błędnego pobrania.
- W E2 nie fabrykować `attempt` z wynikiem H2/U-08. Wynik techniczny pobrania należy do WatchState i istniejącej Historii; wpisy automatu dochodzą w E3.

Bez trackerów, magnetów, podpisanych URL-i, mediów, pełnych payloadów i absolutnych ścieżek. Minimalne nazwy/aliasy potrzebne do replayu są dozwolone **tylko w tym lokalnym rejestrze**, nie w logach. Allowlista sprawdza także zagnieżdżenia, nie tylko root.

Awaria dopisania jest widoczna jako problem rejestru i loguje bezpieczny kod; nie cofa przyjęcia ani nie generuje retry transferu. `selection` koreluje się z zapisanym przyjęciem, więc przerwanie między przyjęciem a append jest jawną luką obserwacji, nie drugim zleceniem. Czytnik raportuje urwany ostatni wpis; nie usuwa poprawnej historii ani nie traktuje braku wpisu jako braku kandydatów. Nie dodawać rotacji w E2. `cases.jsonl` nie zapełnia się automatycznie; zweryfikowane błędy z H2 idą procedurą regresji E1 po decyzji właściciela.

### 8.9 Q-08: rozmiar widoków i wszystkich ramek

1. Status i `state_changed` używają tej samej zwartej projekcji: aktywne przyjęcia/zadania, nierozwiązane problemy oraz ograniczone bieżące postępy; nie pełny ledger zakończonych hashy. Historia zachowuje 30 dni i domyślne 50 pozycji. Stare G nie może polegać na komplecie historycznych hashy w statusie: stan kandydatów odczytuje dla aktualnej listy, a ostateczny zakaz duplikatu zawsze egzekwuje owner.
2. Lista subskrypcji dostaje tylko metadane, liczniki, najbliższy termin i problem. `episodes`, `work_states`, `taken` i pełen zakres tylko w `subscription_get` używanym po Enter. Dostosować istniejący panel/listę i jego licznik do podsumowania, zachowując stare zachowanie subskrybowania G.
3. `episode_states` pyta tylko o aktywny wpis i ograniczoną partię numerów, nie o wszystkie odcinki wszystkich wpisów. Odpowiedzi ofert i plików dotyczą jednego odcinka/transferu. Liczby elementów i długości pól są walidowane, lecz ostateczny limit liczy **bajty zakodowanego UTF-8 całej ramki**, nie liczbę znaków.
4. Zachować odmowę `REFUSED/response_too_large` dla zbyt dużej odpowiedzi. Dodać wspólną ochronę wszystkich wyjść `_ServedConnection.send` oraz kontrolę przed umieszczeniem eventu w outboxie. Event ponad limit zastępuje mały jawny `control_problem` z `reason=event_too_large`, nazwą typu pominiętego zdarzenia i informacją o konieczności odświeżenia. Nie wysyłać części oryginalnego payloadu. Połączenie i kolejny poprawny event pozostają sprawne.
5. `ResidentSession.observe` i panel rozpoznają `control_problem`, zachowują ostatni poprawny widok, oznaczają go jako nieaktualny i pozwalają na jawne odświeżenie. Nie zapętlać automatycznego status → za duży event → status. Gdy duża Biblioteka, aktywna kolejka albo pojedyncze szczegóły nadal przekroczą limit, działa jawna odmowa; nic nie znika po cichu. Nie wprowadzać snapshotów z TTL ani arbitralnego wyrzucania aktywnej pracy dla uzyskania małej ramki.
6. Domyślne odczyty muszą być użyteczne przy dużej **historii zakończonych przyjęć** — samo zamienienie każdego statusu w odmowę nie realizuje Q-08. Test dużego ledgeru potwierdza, że rozmiar statusu nie rośnie wraz z nim. Pełna bardzo duża lista Biblioteki może otrzymać kontrolowaną odmowę bez zrywania kanału; poprawa nawigacji po takich listach nie jest dodatkową funkcją E2.
7. Przed wysłaniem zbyt dużego żądania klient także odmawia lokalnie, by nie uszkodzić kanału. Nowe mutacje i ich receipts są zwięzłe, więc odmowa odpowiedzi po zapisie nie powinna wystąpić normalnie; recovery po utracie odpowiedzi opiera się na command ID, nie na ponownym D z nowym ID.

## 9. Fazy wykonania i bramki

Jeden writer na fazę, świeży recenzent drugiej rodziny: autor → testy → review → poprawki autora → weryfikacja recenzenta. Orkiestrator integruje, sprawdza dowody i decyduje o przejściu. Nie uruchamiać równoległych writerów nad ownerem/schematem.

Ostatnia jednoznacznie przypisana faza produkcyjna E1, F5 UI, była autorstwa `astra`; finał E1 był krzyżowy, bez jednego autora. Dlatego **F0 E2 zaczyna `opus55`, recenzuje `astra`**, a potem role zmieniają się co fazę. Jeśli przed startem E2 orkiestrator wykona osobną fazę poprawek H1, zamienia całą poniższą sekwencję tak, aby pierwszy writer nie był autorem tej fazy; zapisuje to w outcome. Nie wyciągać autorstwa z samego autora commita integracyjnego. **Zastosowano:** poprawki H1 pisał `opus55`, więc sekwencja jest zamieniona (F0 `astra` → `opus55`, F1 `opus55` → `astra` itd.); nagłówki faz poniżej podają pierwotną kolejność, obowiązuje tabela ról w [outcome E2](../outcomes/e2.md).

### F0 — baseline i kontrakt wykonania (`opus55` → `astra`)

**Wejście:** plan po niezależnym review orkiestratora. Utworzyć branch od rzeczywistego HEAD E1, zapisać SHA i stan drzewa. Sprawdzić drift wskazanych symboli, stan H1 i delegację D-01. Utrwalić w źródłach produktu tylko wiążące zmiany D/I/A/S z §13. Sprawdzić dostępność binarki qB i istniejących helperów syntetycznych; nie uruchamiać pobrań właściciela. Uruchomić baseline bramek i zapisać znany fail osobno. Ustalić bezpieczne miejsce oraz sposób dostarczenia kopii stanu do testu migracji, bez wypisywania jej danych.

**Pilot przed migracją schema 3:** na odizolowanym syntetyku i prawdziwym qB sprawdzić kontrakt §8.4: lokalny seeder zna `.torrent`, odbiorca otrzymuje wyłącznie magnet i lokalnego peera/trackera, bez internetu. Bez zmian produkcyjnego schematu potwierdzić metadata stop bez treści → zatrzymanie → priorytety 0/1 → readback; puste pliki dopuszczone tylko w stagingu. Zapisać wersję qB, komendę, fixture i wyniki tak, aby pilot dało się powtórzyć bez lokalnego nieśledzonego `magnet_probe.py`. Skopiowanie `.torrent` odbiorcy nie jest dowodem. Pilot musi przejść **w F0, przed rozpoczęciem F1 i migracji**, aby błąd założenia nie obciążył prac nad stanem. D-01 pozostaje decyzją orkiestratora; F0 nie wymaga ponownego pytania właściciela.

**Gate:** odtwarzalny baseline, pilot qB PASS, brak nieznanych zmian/failures bez diagnozy, potwierdzony zakres E2 i zapisane tymczasowe D-01. Brak ludzkiego H1 nie zostaje ukryty jako PASS. Review F0 akceptuje mapę regresji i warunki migracji.

### F1 — trwałe przyjęcie i I-06 (`astra` → `opus55`)

**Wejście:** F0 z pilotem qB PASS. `control.py`, `watch_state.py`, bramka przyjęć w `automation.py`, niezbędny kontekst G/ResidentSession i starego callbacku subskrypcji. Wprowadzić §8.2–§8.3 oraz schema 3. **F1 dostarcza synchroniczne przyjęcie jednego przygotowanego klucza w bramce ownera: przyjęcie + receipt w jednym zapisie, bez add ani innych skutków qB.** Test luki D/G porównuje tę nową granicę przyjęcia ownera ze starym `download`, bez UI, na przygotowanych danych wyboru; nie wymaga jeszcze asynchronicznej partii `episode_download`. Pokryć wszystkie gałęzie §8.3: ID + offset + match; brak match/niepoprawny numer; to samo/inne/brak ID; zakres konfliktu po numerze i read-only taken. Testy dwóch klientów, powtórzonego command ID, błędu zapisu, restartu, usunięcia pliku i wygaśnięcia Historii. Asynchroniczne D, zdarzenia i lifecycle należą do F3, która używa tej samej bramki.

**Gate:** jedno logiczne przyjęcie i zero drugich skutków w obu kolejnościach nowa bramka/G oraz nowa bramka/stara subskrypcja z potwierdzonym kluczem. Unkeyed z poprawnym numerem daje konflikt tylko pary ID/numer; inny numer tej samej serii przechodzi, brak/niepoprawny numer rozszerza konflikt na ID, inne/brak ID nie blokuje logicznie. Subskrypcja bez ID z innym hashem działa, ten sam hash/plik jest deduplikowany; ograniczenie I-06 do E3 jawne. Migracje syntetyczne 1/2/3 idempotentne, liczba acquisitions nie rośnie od taken, kopie obu plików poprawne, brak masowego pobierania. Targeted testy + bramki repo + review PASS z wyjątkiem wyłącznie jawnego baseline failure.

### F2 — metadata-only i selekcja paczki (`opus55` → `astra`)

**Wejście:** trwałe typy F1. Rozszerzyć qB/protokoły/manager, dodać czyste mapowanie U-18 i sidecary, staging path oraz regułę sumy wyborów z §8.4. Testy HTTP dokładnych pól, hash ownership, priorytetów i odczytu zwrotnego; unit: padding, błędny/brak `fileIdx`, podwójna nazwa, dwie zgodne ścieżki, brak zgodnego, unsupported, stem/katalog sidecarów, unsafe Windows path.

Na syntetyku pilota F0 sprawdzić teraz **produkcyjny adapter i manager qB**: metadata stop → mapowanie → wybór → potwierdzone priorytety. To kontrola nowej implementacji wobec wcześniejszego pomiaru, nie pierwszy test wykonalności po migracji. Odbiorca nadal dostaje wyłącznie magnet. Nie rozwijać lifecycle i UI, jeśli adapter nie zachowuje kontraktu pilota.

**Gate:** realny metadata stop bez treści przed selekcją, dozwolone puste pliki wyłącznie w stagingu, unikalna mapa i oczekiwane priorytety; testy negatywne nie startują zawartości. Wynik i wersja qB zapisane. Review oraz bramki jak F1. Odrzucenie D-01 albo niezgodność qB → stop §6.

### F3 — lifecycle transferu, współdzielenie i recovery (`astra` → `opus55`)

**Wejście:** F2 PASS. Wpiąć admission → add/uzgodnienie → metadata → zapis mapy → filePrio → readback → start w ownerze i istniejącym pollerze. **F3 dostarcza asynchroniczną partię D (`episode_download`), zdarzenia wyników per odcinek i lifecycle; każdy przygotowany odcinek przyjmuje synchroniczna bramka z F1.** Dodać pozostałe API §8.7. Jeden hash, dołożenie odcinka, rewizje, globalna pauza, shutdown/drain, timeout metadanych, stary transfer M-06. Zaimplementować backend P, w tym potwierdzone wyjście z „możliwie zleconego” i zapis odstępstwa §8.6; odjęcie starego zakresu tylko przy potwierdzonym poprzednim celu. Test ownera: P z konfliktu → podgląd → przyjęcie, zmieniony konflikt odmawia, niepewny stary transfer pozostaje nietknięty. Bez nowego UI; zapis dowodowego `correction` dochodzi w F5.

**Gate:** restart na każdej granicy nie tworzy drugiego add/przyjęcia i nie wznawia niezatwierdzonych plików; P nie narusza innego odcinka paczki; spóźnione rezultaty są odrzucane; status/pauza reagują podczas oczekiwania na metadane. Rozłączenie panelu nie przerywa partii; restart po przyjęciu pierwszego odcinka zachowuje go, pozostawia resztę niezleconą i nie wznawia jej po ponowieniu tego samego command ID. Testy ownera z kontrolowaną granicą qB, bramki i review PASS.

### F4 — kompletność, publikacja zestawu i Auto (`opus55` → `astra`)

**Wejście:** F3. `acquisition_staging.py`, `transfers.py`, owner i minimalne wpięcie ReadyStore. Realizować §8.5: dowód wszystkich plików per odcinek, rezerwacja całego zestawu, kopia, wyłączna publikacja, trwałe przekazanie, cleanup. Testy przerwania przed/po każdym opublikowanym pliku, zablokowanego pliku, kolizji nazw, braku miejsca, startup scan i zdarzeń przyrostowych. E1 może wejść do Auto, gdy E3 tej samej paczki nadal trwa.

**Gate:** dokładnie jeden run na przyjęcie; 100% qB bez pliku/ze złym rozmiarem/brakującym sidecarem nie przechodzi; E2 spoza zamówienia nie przechodzi pełnego ani przyrostowego skanu przed i po restarcie. Gotowe zachowuje powiązanie i niepewność. Test sukcesu: po `release_completed` i dowodach mocnej tożsamości opublikowanych kopii katalog operacji jest pusty/usunięty, także oryginały qB. Testy braku dowodu po przerwaniu/anulowaniu/P: zamówiony plik zostaje. Cleanup nie narusza aktywnego drugiego odcinka. Regresje Auto, Library/Kosz/Undo i M-06 + bramki + review PASS.

### F5 — rejestr i kompletne Q-08 (`astra` → `opus55`)

**Wejście:** F4. Dodać rejestr §8.8, owner-only zapis `check` bezpośrednio po odczycie źródła oraz `selection/correction`. Zmienić projekcje i ich istniejących konsumentów razem; dodać kontrolę eventów i klienta §8.9. Ten krok nie przebudowuje zakładki Subskrypcje.

**Gate:** test replayu rzeczywistego target/candidates odtwarza werdykty/ranking, cache nie generuje odczytów, 429 jest zapisywane poprawnie, brak zakazanych danych. Duży ledger nie rozdyma statusu; `state.json` i P95 `save()` mieszczą się w progach §10. Subskrypcje mają odcinki wyłącznie w szczegółach; ramki odpowiedzi/eventu granicznej i ponadlimitowej nie zrywają kanału, następna komenda i zdarzenie działają. Uszkodzony zapis rejestru nie duplikuje transferu. Bramki i review PASS.

### F6 — D/I/P/U05 w panelu (`opus55` → `astra`)

**Wejście:** gotowy backend, DTO i zdarzenia. Wdrożyć §8.1 i §8.7 w Anime/ResidentSession/StateController, testy klawiszy, focusu i generacji. D z częściowym wynikiem, kursor fallback, A toggle, stan przyjęty z drugiego panelu, I z seedami i potwierdzeniami, P z wykluczeniem, U05, S nieaktywny. „Możliwie zlecony” pokazuje powód i P; test pełnej drogi potwierdzenie → podgląd → pobranie → correction, Esc bez skutku. Ponad 100 zaznaczeń daje komunikat przed wysłaniem i zero IPC. Stan oraz niepewność przez ownera; istniejące paski Przetwarzania i powrót na właściwy ekran.

**Gate:** testy kontrolerów i integracja panel → IPC → owner dowodzą wszystkich akcji, zero zleceń z renderu/nawigacji, jedno D wysyła jedną listę i jeden command ID. Esc/Tab nie przerywają partii ani nie powodują późnego przełączenia widoku; UI po restarcie odróżnia przyjęte od niezleconych. Ponowione D nie omija dedupe, G nadal pobiera/subskrybuje w granicach §8.3. P ma podgląd przed skutkiem. Smoke interakcji na syntetycznych ofertach przy ok. 50 kolumnach; bramki i review PASS. Uwagi ergonomiczne nie muszą czekać do długiego pobrania H2.

### F7 — dowód całego przepływu i migracja na kopii (`astra` → `opus55`)

**Wejście:** F6. Rozszerzyć syntetyk pilota F0, użyty przez adapter w F2, do paczki E1/E2/E3 z wideo, sidecarami, paddingiem i wspólnymi kawałkami. Przepuścić przez prawdziwe owner/IPC/WatchState, prywatny qB, publikację i istniejący graf aż do Biblioteki. Zewnętrzne płatne/sieciowe translation/TTS mogą mieć deterministyczny adapter testowy; generowanie testowych mediów i lokalne narzędzia są rzeczywiste. Nie przedstawiać takiego adaptera jako odsłuchanego lektora.

Osobno: E1 ukończone przy zatrzymanym E3; dołożenie E3 do istniejącego transferu; restart ownera i qB w trakcie; P; M-06 z aktywnym legacy; I-06 przy różnych hashach i obu kolejnościach; pełny/inkrementalny skan I-07. Przeprowadzić migrację **na kopii** rzeczywistych `state.json`/`subscriptions.json`, uruchomić drugi odczyt i porównać zachowane identyfikatory, pauzę, przyjęcia, produkty i oryginalne bajty. Oryginały runtime pozostają nietknięte.

**Gate:** E1 i E3 w Bibliotece, E2 nieobecne w skanie/runach/Bibliotece; jeden transfer paczki i brak duplikatów przyjęć/runów; cleanup pustych pozostałości potwierdzony; kopia stanu migruje bez utraty i skutków pobierania; pomiary Q-05 i rozmiarów IPC zapisane. Pełne bramki z uczciwym wynikiem baseline failure; review krzyżowe całego E2, bez otwartych poważnych findingów. Brak kopii właściciela oznacza niezaliczoną tę część gate, nie zastąpienie jej syntetykiem.

### F8 — odbiór H2 i outcome (`opus55` → `astra`, właściciel wykonuje H2)

**Wejście:** F7 z dostępnymi dowodami. Orkiestrator przekazuje właścicielowi scenariusz §11; uwagi realizacyjne poprawia autor fazy, świeży recenzent sprawdza ponownie. Zmiana wymagania wraca do właściciela, błąd H1 do procedury regresji E1. Dokończyć `outcomes/e2.md`, aktualizacje scoped AGENTS i status etapu.

**Gate:** rzeczywisty H2 PASS, potwierdzenie D-01, zamknięty outcome i review końcowe. Przy oddelegowanym odbiorze końcowym praca automatyczna może zakończyć się **`PENDING HUMAN`** i zostać przekazana orkiestratorowi do dalszej realizacji jego polecenia, lecz nie oznaczać E2 jako `ACCEPTED`, nie deklarować H2 PASS i nie scalać samodzielnie do `main`.

## 10. Strategia dowodu i bramki repo

| Twierdzenie | Najmniejszy wymagany dowód |
| --- | --- |
| Przyjęcie jest trwałe, panel nie jest ownerem | owner + WatchState + IPC, fault injection zapisu/utraconej odpowiedzi, ponowione ID |
| I-06 dla potwierdzonego klucza | F1: synchroniczna bramka nowego przyjęcia ownera kontra stare `download` w obu kolejnościach, bez add; F3: asynchroniczne D przez tę bramkę, potem dwa panele; G i subskrypcja z ID, stary numer 27 − offset 24 = lokalne 3, H1 match, różne hashe; restart; jedno przyjęcie/run; osobno offset 0 |
| `legacy-unkeyed` i granica I-06 | bez H1 match, ID + poprawne 27 − 24 = 3 → konflikt tylko E3, D dla E4 tej samej serii przechodzi; brak/niepoprawny numer → konflikt całego ID; obie kolejności wejść, inne ID bez blokady logicznej; brak ID → G i subskrypcja z innym hashem działają mimo przyjęcia nowej drogi; ten sam hash/ścieżka deduplikowane także bez ID, różne pliki paczki niescalane |
| Taken nie tworzy transferu | `SubscriptionService` czytane bez mutacji: ID + offset + H1 match blokują klucz; samo taken bez H1 daje konflikt pary ID/numer, inny numer nieblokowany; brak/niepoprawny numer rozszerza na ID, brak ID nie blokuje logicznie; bajty subskrypcji i liczba acquisitions bez zmian, poller/release nie otrzymują fikcyjnych rekordów |
| P wychodzi z możliwego konfliktu | konflikt jednego numeru oraz całego ID → `episode_states` pokazuje „możliwie zlecony” i P; potwierdzenie + podgląd → nowe przyjęcie wybranego klucza + `correction` (`legacy_conflict_override`), także gdy brak poprzedniego rekordu acquisition i hasha; brak potwierdzenia, Esc lub zmiana konfliktu → zero skutku; brak mutacji starego transferu/taken; restart zachowuje nowe przyjęcie, inne numery nie tracą stanu, deduplikacja fizyczna nadal działa |
| D jest jedną partią ownera | jedna lista i command ID; ponad limit odmowa przed efektem; Esc/Tab/rozłączenie nie zatrzymują kolejnych odcinków; błąd jednego daje zdarzenie z powodem i nie blokuje następnego; restart po pierwszym trwałym przyjęciu → reszta niezlecona, to samo ID nie wznawia, nowe D może zlecić resztę bez duplikatu |
| U-18 poprawnie wybiera plik | unit na paddingu, indeksie niezgodnym z nazwą, kolizjach i pełnych ścieżkach; U05 stale revision przez IPC |
| Selekcja dotyczy tylko zamówionych | realny qB, E1/E3, priorytety całej listy, dołożenie pliku i readback; brak potrzeby zerowych bajtów wspólnych kawałków E2 |
| P-07 niezależne od paczki | E1 + wszystkie jego sidecary ukończone przy E3 nieukończonym; E1 wpuszczone, E3 nie; fałszywe 100% i brak rozmiaru nie przechodzą |
| I-07 | puste i niepuste niezlecone `.mkv` w stagingu, pełny scan, zdarzenia przyrostowe, restart; brak grupy, runu i wyniku E2 |
| Publikacja odporna na restart | crash przed kopią, między plikami, przed/po zapisie całego zestawu i przed/po przyjęciu runu; kolizja i obcy plik bez overwrite |
| Cleanup oryginałów qB | sukces wszystkich odcinków + `release_completed` + trwała mocna tożsamość kopii → pusty/usunięty katalog operacji; brak dowodu po przerwaniu, anulowaniu i P → zamówiony oryginał zostaje; sam rozmiar lub release nie uprawnia do usunięcia; restart cleanupu idempotentny |
| M-06 | stan schema 2 z aktywnym transferem, migracja, dokończenie starą drogą i snapshot ustawień dopiero przy handoff |
| P zachowuje poprzedni wynik | podgląd i wykluczenie pary, nowy hash/plik i nowy zestaw, aktywna paczka innych odcinków nietknięta, wcześniejszy wynik obecny |
| Rejestr jest dowodem | prawdziwe wejścia buildera/rankera na fixture, odczyty/429, allowlista pól, błędy append, restart bez deduplikacji na podstawie JSONL |
| Q-08 i koszt trwałego ledgeru | 10 000 zakończonych przyjęć + aktywne zlecenia, duża lista subskrypcji; pomiar bajtów IPC i `state.json`, P50/P95 `WatchStateStore.save()` z progami poniżej; odpowiedź i event dokładnie w limicie/ponad, Unicode; następna komenda/event na tych samych kanałach |
| Chronione PR-01–PR-12 | istniejące testy ownera, scheduler/recovery, subskrypcji, discovery, ReadyStore, Library/Kosz/Undo, IPC i kontrolerów; nie osłabiać ich |
| Odcinek nadaje się do oglądania | właściciel wykonuje H2 z rzeczywistym przetwarzaniem/lektorem; syntetyk tego nie zastępuje |

Test qB używa profili pod `tmp_path`, losowych wolnych portów i loopback, rozłączonych od runtime właściciela. W `finally` zamyka tylko własne procesy, serwer i porty; nie kończy wszystkich `qbittorrent.exe`. Marker `integration` nie pomija testu domyślnie. Publiczna sieć to osobne `network`, nie warunek syntetyka. Znany fail automatycznego zamykania z otwartym GUI nie uprawnia do pominięcia nowego testu selektywnego pobierania; nowy test ma jawny teardown, bez zmiany polityki produktu.

**Próg kosztu stanu (F5/F7):** fixture 10 000 zakończonych przyjęć selektywnych, każde z jednym odcinkiem, wideo i sidecarem oraz kompletnymi dowodami publikacji, plus 10 aktywnych przyjęć. Pełny `state.json` ma mieć **≤ 64 MiB**, a P95 pełnego `WatchStateStore.save()` **≤ 1 s** na lokalnym dysku Windows użytym do odbioru. Jedna rozgrzewka i 20 kolejnych zapisów zmienionego stanu; pomiar obejmuje serializację, fsync, backup i replace, bez mocków. Zapisać rozmiar, P50/P95, liczbę prób i warunki sprzętowe. To jawny budżet inżynierski trwałości E2, nie próg czasów sieciowych Q-05. Przekroczenie zatrzymuje gate i wymaga diagnozy/przeplanowania zapisu; nie usuwać historii ani nie podnosić progu po zobaczeniu wyniku dla uzyskania PASS.

Kontrole podczas faz — dobór plików pytest do zmiany, wszystkie lint/type-check zawsze na całych drzewach. Przed checkpointem integracyjnym i każdym autoryzowanym commitem komplet:

```powershell
$env:PYTHONIOENCODING='utf-8'
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest
```

Przykładowa wąska kontrola po powstaniu nowych testów:

```powershell
uv run pytest -n 0 tests/application/test_acquisition_staging.py tests/application/test_acquisition_decisions.py tests/integration/test_episode_download.py
```

Wynik pełnego pytest zawierający znany fail podać jako **FAIL z dokładnym rozliczeniem**, nie PASS. Powtórka niestabilnego testu osobno może potwierdzić diagnozę, ale nie usuwa pierwszego wyniku. Nowy fail albo luka dowodu zatrzymuje odpowiednią fazę. Nie dodawać `xfail`, skipów ani wyłączeń dla uzyskania zielonej bramki.

**Q-05:** zarejestrować czasy D → wybór/przyjęcie → metadane → selekcja/start → kompletny odcinek → handoff → Gotowe, osobno zimny/ciepły katalog, pojedynczy plik, paczka i restart. Dla fixture/IPC wiele powtórzeń P50/P95, dla realnego qB i H2 liczba prób oraz rzeczywiste czasy. Brak arbitralnego progu wydajności; oczekiwanie ma stan i nawigację.

## 11. Odbiór właściciela — H2

Uruchom po wdrożeniu gałęzi przez orkiestratora `uv run anishift` w repo, z normalnym prywatnym qB AniShift i ustawieniami właściciela. Właściciel wybiera własny materiał; syntetyki F7 i kopia migracyjna muszą mieć wcześniej wynik. Przed próbą orkiestrator pokazuje krótkie podsumowanie D-01 i stan ludzkiego H1.

| Krok właściciela | Oczekiwany rezultat |
| --- | --- |
| Anime → wpis → jeden wyemitowany odcinek → D bez zaznaczeń | sugestia pobierana od razu, jeden wiersz odcinka w Przetwarzaniu, następnie wynik z lektorem w Bibliotece |
| Zaznacz E1 i E3 z tej samej paczki; sprawdź Space/A wszystkie/żadne/Z; D | jeden transfer paczki, tylko pliki obu odcinków i sidecary; E2 nie trafia do Przetwarzania/Biblioteki |
| W trakcie zamknij panel, ponownie otwórz; zatrzymaj i ponownie uruchom AniShift, nie usuwając stanu | panel nie przerywa partii; po restarcie przyjęcia i wybór plików zachowane, przyjęta praca trwa po wznowieniu; reszta niedokończonej partii jest niezlecona i wymaga nowego D, co UI wyjaśnia |
| I dla niezleconego odcinka → wybierz wydanie Space → D | seedy/rozmiar i powód są czytelne; dokładnie wybrane wydanie; ostrzeżenie dla niepewnego/niezgodnego przed skutkiem |
| P na pobranym odcinku → potwierdź → podgląd → Pobierz | poprzednia para wykluczona; dopiero zatwierdzenie podglądu zleca; poprzedni wynik nadal otwieralny |
| Przy przygotowanym problemie mapowania Enter w Przetwarzaniu → U05 → właściwe wideo | czytelne ścieżki, tylko właściwy plik i jego sidecary, Esc bez skutku |
| Otwórz ten sam odcinek drugim panelem i przez G, spróbuj zwykłego pobrania | widoczny stan już zleconego/odmowa, bez drugiego transferu i przetwarzania |
| Sprawdź Bibliotekę, odtwórz gotowy odcinek; po pełnym sukcesie wszystkich odcinków paczki i zwolnieniu qB sprawdź katalog operacji w stagingu | rzeczywisty obraz i lektor, opublikowane pliki zachowane; katalog operacji pusty/usunięty, także oryginały qB usunięte po dowodzie mocnej tożsamości kopii. Osobno na syntetyku przerwania/anulowania/P bez dowodu eksportu zamówiony oryginał zostaje — to oczekiwane zachowanie, nie błąd cleanupu |

Zwróć uwagę na późne przełączanie zakładki po Esc/Tab, czytelność przy ok. 50 kolumnach, mylenie Zlecono/Pobrano/Gotowe i oznaczenie niepewnego. Raport właściciela: **numer kroku, obserwacja, PASS/FAIL, uwaga**. Orkiestrator zapisuje czasy i wersję qB, nie zgaduje wrażeń właściciela. Brak dostępnej paczki/U05 można pokazać kontrolowanym syntetykiem F7, ale realny pojedynczy odcinek i odsłuch pozostają obowiązkowym dowodem H2.

## 12. Definition of Done i kontrakt `outcomes/e2.md`

- [ ] Warunki §2 spełnione, wszystkie fazy mają dowody i niezależną weryfikację.
- [ ] Nie ma otwartych poważnych/krytycznych findingów, fałszywych PASS ani ukrytej zmiany wymagań.
- [ ] WatchState migracja syntetyczna i na kopii właściciela, I-06, I-07, M-06, P i pełne Q-08 sprawdzone.
- [ ] Syntetyk używa prawdziwego qB i restartu, a outcome rozróżnia go od atrap usług i ludzkiego H2.
- [ ] H2 i D-01 otrzymały rzeczywiste potwierdzenie właściciela; bez niego status `PENDING HUMAN`.
- [ ] Diff mieści się w zakresie, scoped AGENTS opisują nowe pułapki, spec/UX odzwierciedlają zatwierdzone klawisze; G pozostaje.

`docs/work/acquisition/outcomes/e2.md` ma zawierać:

1. Status `ACCEPTED` / `PENDING HUMAN` / `PARTIAL` / `BLOCKED` / `REPLAN REQUIRED`, baseline rozgałęzienia, HEAD, branch, stan drzewa; autor i recenzent każdej fazy oraz zamknięcie findingów.
2. Stan końcowy widoczny użytkownikowi, dokładny zakres zmian i wersja schematu; procedura przywrócenia kopii po zatrzymaniu rezydenta.
3. Osobne dowody I-06 (różne hashe, oba wejścia, restart, ID/offset/H1 i jawne ograniczenie `legacy-unkeyed` do E3), partii D po restarcie, I-07 (niezamówione pliki i skany), U-18, P-07, P i M-06; nazwy testów, komendy, liczby i wynik.
4. Realny qB: wersja, lokalny syntetyk, sposób dostarczenia metadanych, kolejność restartów, wybrane priorytety, liczba transferów/runów/wyników, cleanup własnych procesów i pustych plików. Nie kopiować hashy realnych mediów ani profilu właściciela do Git.
5. Migracja na kopii: źródłowe wersje, liczności i zachowane identyfikatory w bezpiecznym agregacie, sumy kopii, idempotencja drugiego startu, zero nowych pobrań. Brak dostępu do kopii jawnie nazwany.
6. Rejestr: schemat i wersje reguł, przykładowy syntetyczny wpis `check`/`selection`, dowód minimalizacji pól i zachowania przy awarii, znane luki obserwacji.
7. Q-08: rozmiary UTF-8 statusu/list/szczegółów/zdarzeń dla dużego stanu, wynik odmowy i następnej komendy/eventu; rozmiar `state.json`, P50/P95 pełnego `save()` dla 10 000 przyjęć i wynik względem progów §10; żadnej deklaracji „ograniczone” wyłącznie na podstawie liczby elementów.
8. Q-05: pomiary wszystkich etapów i liczba prób; wyniki pełnych bramek, osobno znany środowiskowy fail i ewentualna niestabilność xdist.
9. Feedback H2, potwierdzenie/odrzucenie D-01, odziedziczony status H1, odchylenia od planu, ograniczenia i punkty wejścia E3. E3 dostaje przyjęcia/rejestr, nie deklarację wdrożonej nowej maszyny subskrypcji.

## 13. Odchylenia od wcześniejszych dokumentów

| Wcześniej | E2 | Authority / powód |
| --- | --- | --- |
| P-02/R-03, UX U03/U04: D → podgląd → Enter Pobierz | zwykłe D dobiera i pobiera, sugestia informacyjnie w I; P nadal ma podgląd | wiążący feedback właściciela 2026-09-29; wykonawca aktualizuje dokładnie te miejsca |
| A zaznacza wszystkie | A wszystkie/żadne, tylko uprawnione odcinki | ten sam feedback |
| I z podglądu; Enter wybiera sugestię | I bezpośrednio z odcinka, Space/Enter wybiera jedną wersję, D pobiera | ten sam feedback; jeden cel nie oznacza wielu wariantów |
| przyszła subskrypcja O | S zarezerwowane; w E2 nieaktywne z informacją o G, stare O pod G działa | ten sam feedback; podział E2/E3 pozostaje |
| N-03 PARTIAL i decyzja właściciela przed E2 | tymczasowe dopuszczenie pustych plików pod warunkami D-01 | delegacja właściciela i decyzja orkiestratora, nie nowy pomiar |
| U-19 „nowe pobrania płasko do roota” | torrent fizycznie w stagingu, wyłącznie kompletny zamówiony zestaw publikowany płasko do roota przed Auto | konieczne I-07; końcowy layout użytkownika zgodny z U-19 |
| outcome E1 rekomenduje także `cases.jsonl` w E2 | E2 dostarcza rejestr i korekty; aktywna baza zweryfikowanych przypadków/przeglądy w E3 | rekomendacja nie zmienia rezultatu masterplanu; nie tworzyć etykiet bez przeglądu |
| Q-08 E1 tylko odpowiedzi | ograniczenie projekcji, wszystkich odpowiedzi i eventów, konsumenci komunikatu limitu | jawny zakres E2 |
| stare G „bez zmian” | UI i źródło pozostają; admission dostaje wspólną tożsamość i kontrolę duplikatów | wymagany przez masterplan I-06 między wejściami |
| I-06 bez rozróżnienia jakości historycznej tożsamości | klucz z legacy wymaga ID, odjęcia offsetu i H1 match; unkeyed: konflikt pary ID/poprawny numer, całego ID tylko przy braku/niepoprawnym numerze; stan „możliwie zlecony” ma jawne wyjście P z correction; bez ID inny hash nie jest blokowany | korekta po review opus55 i decyzja właściciela; ograniczenie do E3, bez „Ustal cel” dla starych zleceń |
| §8.3/§10: klucz G i starej subskrypcji z ID, odjęcia offsetu i H1 `match` | w E2 G i subskrypcja pozostają `legacy-unkeyed` z zakresem (ID, numer) lub całego ID; potwierdzenie klucza po metadanych transferu przechodzi do E3 | F1: przed przyjęciem brak nazwy pliku, H1 daje `insufficient_evidence`; decyzja właściciela i korekta orkiestratora po review astra |
| I-04: zakaz usuwania pobranych plików | wąski wyjątek §8.5: oryginały qB we własnym stagingu są usuwane po `release_completed` i trwałym dowodzie mocnej tożsamości opublikowanej kopii; bez dowodu zostają, również po przerwaniu/anulowaniu/P | jawne odchylenie zaakceptowane korektą planu: publikacja zachowuje dane użytkownika, a cleanup usuwa zbędną drugą kopię i opróżnia staging; nie uprawnia do usuwania opublikowanych plików |
| Plan przepływu §5.6: szeroka lista pól celu `selection` (m.in. rok), kontekst automatu `t_due` i licznik prób | §8.8 zapisuje dokładne runtime wejście H1/rankingu E1 bez dopisywania roku/dowodów do target; dodatkowy katalog tylko osobno, bez fikcyjnych pól automatu w ścieżce ręcznej E2 | replay ma odtwarzać faktyczne wywołanie zamrożonej H1; momenty zapisu selection/check pozostają zgodne z §5.6 |

## 14. Ryzyka i reakcje

| Ryzyko | Sygnał | Reakcja / granica |
| --- | --- | --- |
| qB inaczej interpretuje metadata stop | treść przed selekcją, brak zatrzymania w pilocie | zatrzymać F0 przed migracją; regresja adaptera zatrzymuje F2, bez obejścia stopped add ani pobrania całej paczki |
| Brak identity w legacy | ID/offset/H1 nie potwierdzają klucza | konflikt pary ID/poprawny numer, całego ID tylko przy braku/niepoprawnym numerze; „możliwie zlecony” z wyjściem P; bez ID ograniczenie I-06 do E3, bez zgadywania klucza |
| Nowy odcinek i stary worker zmieniają tę samą paczkę | readback nie zgadza się z najnowszą sumą | rewizja ownera i serializacja po hashu; ponowne uzgodnienie, bez automatycznego startu starego zakresu |
| Wspólne kawałki tworzą niezamówione wideo | plik E2 istnieje mimo priority 0 | izolacja stagingu, nie próba gwarancji „zero bajtów”; test I-07 i cleanup |
| Przerwanie między publikacją MKV a sidecarem | discovery widzi częściowy zestaw | trwała blokada całego zestawu przed Auto i recovery po dowodach publikacji |
| Kopia potrzebuje dodatkowego miejsca lub plik jest zajęty | błąd kopiowania/dostępności | problem jednego przyjęcia, źródło zostaje; brak publikacji niepełnego zestawu, jawne wznowienie |
| Rejestr dowodowy staje się drugim stanem | kod przyjęcia czyta JSONL, znika blokada po uszkodzeniu logu | odrzucić w review; wyłącznie WatchState steruje wykonaniem |
| Odchudzenie statusu łamie G/subskrypcje | znikają znaczniki zamówionych albo licznik zależy od episodes | odczyt stanów aktualnej listy, liczniki ownera, test konsumentów w F5 |
| Event ponad limit zrywa obserwację | brak kolejnego zdarzenia, ponowne połączenia panelu | wspólna kontrola wysyłki i mały jawny problem; test tego samego połączenia |
| Znany fail qB maskuje nową usterkę | opis „to środowisko” bez reprodukcji | raport dokładnej asercji i porównanie baseline; nowy selektywny test musi mieć własny wynik |
| H1 wybiera nieprawidłowy materiał | zgłoszenie właściciela po obejrzeniu | zachować dowody, procedura regresji E1; nie stroić na egzaminie i nie dorabiać H2 do ścieżki ręcznej |

## 15. Decyzje tymczasowe i pytania do właściciela

- **D-01:** decyzja tymczasowa orkiestratora w ramach delegacji: puste pliki po priorytetach dopuszczone wyłącznie w izolowanym stagingu, z negatywnym testem i cleanupem. Nie pytać ponownie w F0; potwierdzenie wraz z dowodami w raporcie końcowym. Ewentualna zmiana skupiona w pilocie F0 i F2/§8.4.
- **D-02:** `T_metadane=600 s` to tymczasowy timeout operacyjny z próby N-03; mierzymy go w E2, nie traktujemy jako dowodu martwego źródła. To parametr inżynierski, nie pytanie do właściciela; zmianę z uzasadnieniem zapisać w outcome.

**Brak pytań produktowych blokujących rozpoczęcie wykonania.** Rozstrzygnięcia D/I/A/S i zakres etapów są przekazane w briefie. Dostęp do kopii stanu oraz wykonanie H2 są wymaganymi dowodami końcowymi, a nie powodem do zatrzymania niezależnych faz. Zlecenie samego planu nie upoważnia do implementacji ani commita.

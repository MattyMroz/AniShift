# AniShift: plan wdrożenia folderów i nowego przepływu

Status: **READY do wykonania, z opisanymi próbami platformowymi**
Specyfikacja: [spec.md](spec.md)
Baseline: `25121038fbf4ff1e1cecec3d4e644fdb235be679`
Odczytana gałąź: `work/local-automation/06-efficiency`
Docelowy artefakt aktywnego workstreamu: `docs/work/local-automation/06-efficiency/plan.md`
Data: 2026-09-13

## 1. Punkt startowy i sposób wykonania

Ten plan realizuje nową specyfikację, nie poprzedni atlas UX i nie dawny kilkunastotysięczny masterplan. P01–P08 z poprzedniego planu dostarczyły podstawę kodową. Nie wykonujemy ich ponownie. Nowa sekwencja zaczyna się od **P09**. Dawne raporty wykonania pozostają dostępne w historii wskazanego commitu; nie są dowodem odbioru nowego zachowania.

Najpierw wykonawca czyta cały `spec.md`, następnie ten plan. Odczytany commit jest podstawą projektu. Nie sprawdzono niezacommitowanego drzewa na komputerze użytkownika ani jego aktualnej konfiguracji runtime. Nie uruchamiano tutaj testów AniShift, płatnych usług, Windowsowego klienta ani operacji na mediach.

Zachować jeden owner, jeden koordynator i jeden renderer. Nie zaczynać od przemalowania list, usunięcia schedulerów lub dodania frameworka profili. Najpierw trzeba umieć ustalić cel i komplet materiału, a dopiero potem podpinać widoki.

Wykonuj fazy P09–P18 kolejno; każda korzysta ze sprawdzonego wyniku poprzednich. Wyniki prób zapisuj w jednym istniejącym miejscu przekazania workstreamu. Do P18 nowe ścieżki uruchamiaj wyłącznie na odseparowanym config/workspace. Kod może być integrowany wcześniej, ale nie wolno uruchamiać go na produkcyjnej bibliotece obsługiwanej przez starego właściciela. Nie dodawaj trwałego systemu feature flags tylko na czas tej migracji.

## 2. Różnica względem odczytanego kodu

Wskazania poniżej dotyczą plików w baseline. Nowe symbole w dalszej części są jawnie oznaczone jako planowane. Zestaw jest mapą zmian, nie nakazem edycji wszystkich sąsiednich plików.

| Obszar | Zweryfikowane zachowanie baseline | Potrzebna zmiana |
|---|---|---|
| `application/discovery.py` | `_PRIMARY_SOURCE_KINDS` obejmuje MKV, MP4, TXT; samodzielny SRT/ASS bez primary jest osierocony | Rozpoznawać primary według miejsca i celu, nie globalnie dopisać SRT jako primary wszędzie |
| `application/products.py` | Jedna tabela nazw `.pl`, `.spoken.pl`, `.displayed.pl`, wyników MKV/MP4 i audio | Dodać TXT wynikowy i rozpoznanie wyniku cover, bez kopiowania reguł nazw do UI |
| `application/inspection.py` | TXT sprawdzany jako UTF-8; napisy walidowane parserem; audio porównywane z czasem wideo | Pozwolić walidować samodzielne audio i obraz; nie wymagać wideo dla audiobooka |
| `application/planner.py` | `_build_text_plan` dopuszcza tylko `{FULL_PL}` i produkuje SRT | TXT→TXT, samodzielne napisy, audiobook, cover i adekwatna walidacja produktów |
| `application/planner.py` | `plan_auto` buduje zamiary z jednego presetu; `_plan` jest wspólne dla Auto/Manual | Recepta rozstrzygana dla grupy, nadal jeden wspólny planner i handlerzy |
| `application/translation_handler.py` | Wymaga wyjścia FULL_PL; `_translate_text` używa `spoken_to_srt` i spłaszcza whitespace | Osobna gałąź wyjścia TXT z zachowaniem struktury; istniejące tłumaczenie pozostaje usługą |
| `application/tts_handler.py` | Przyjmuje SPOKEN_PL jako ASS/SRT i zapisuje manifest klipów | Przyjmować również jawny tekst samodzielny i parametr osi czasu bez fikcyjnego filmu |
| `application/audio_handler.py` | `_mix` wymaga dwóch wejść: SOURCE_AUDIO i TTS_MANIFEST | Dopuścić manifest bez oryginału tylko dla samodzielnego głosu |
| `application/composition_handler.py` | `build_composition_request` wymaga VIDEO_MKV/VIDEO_MP4, a destination leży obok wybranego wideo | Dodać jawny wariant obraz+audio bez osłabiania kontraktu zwykłego kontenera |
| `services/audio/types.py`, `service.py` | `AudioRenderRequest.source_audio_path` już dopuszcza None; audio-service ma narrator-only | Reużyć istniejącego montażu, normalizacji, kodowania i resume, nie budować nowego audiogeneratora |
| `application/control.py` | Stan schematu 1; `auto_enabled=False`; osobne requests, acquisitions, products i receipts | Migracja semantyki pauzy, recept, pochodzenia gotowych zestawów i brakujących potwierdzeń |
| `application/subscriptions.py` | Schemat 3; first/next episode, taken, EpisodeOrder i terminy | Jawny wybór dowolnych numerów i przyszłego zakresu bez resetu historii |
| `application/transfers.py` | Kompletność zależy od całego transferu; cache plików odświeża się przy zmianie nazwy/ścieżki/ready | Potwierdzenie pojedynczego wybranego pliku paczki i aktualny postęp przed końcem torrenta |
| `application/ready.py` | `ReadyStore` relokuje cały zestaw z jednego katalogu; journal znika po apply/ACK | Zachować pochodzenie recepty i zestawu; rozdzielić publikację wyniku od późniejszego zwolnienia źródła paczki |
| `cli/interactive/state.py` | Cztery stare zakładki; Biblioteka składa się z odkrytych grup; Enter/Space w subskrypcjach przełączają wpis | Cztery nowe zakładki, karta zakresu, tylko ukończone wyniki, szczegóły i Kosz |
| `cli/interactive/app.py` | Home zawiera Panel/Auto/Ręczny/Anime; Auto startuje jednorazowo | Home bez Auto/Anime; właściwa zakładka startowa i powroty w obrębie Panelu |
| `cli/interactive/settings.py` | Wspólny edytor, autosave, warunkowe pola i osobny preset Auto | Recepty folderów bez powtarzania głosu/modelu i bez przebudowy edytorów |
| `platform/qbittorrent_process.py` | Prywatny profil, start na żądanie, przejęcie przez GUI ogranicza automat | Start z działającą aplikacją, pauza/wznowienie i bezpieczne zakończenie; widoczne własne GUI nie jest obcym klientem |
| `platform/tray.py`, `cli/watch.py` | Jedna ikona i rezydent, przekazanie otwarcia panelowi | Globalne Zatrzymaj/Wznów, zakończenie zasobów i oddzielny cel kliknięcia gotowego wyniku |

Najważniejszy wniosek integracyjny: usługa audio już potrafi pracować bez oryginalnej ścieżki. Ograniczenie jest w planowaniu i adapterze. Natomiast plików nie można „naprawić” samym nowym menu: discovery, tożsamość produktu i zapis recepty muszą najpierw obsłużyć nowe wejścia.

## 3. Granice zmiany i źródła prawdy

### Czego nie zastępujemy

`AppService`, `AutomationOwner`, `GraphCoordinator`/adapter `GraphScheduler`, istniejące handlery usług, `RunJournal`, walidowana publikacja i IPC zostają. Nie powstaje drugi watcher, druga baza, nowy frontend, osobny manager każdego rozszerzenia ani własny klient torrent.

Utrzymać zależność: renderer → kontroler → publiczna fasada/`ResidentSession` → owner → istniejące planowanie i wykonanie. Renderer nie czyta katalogu, nie wywołuje ffprobe, nie zapisuje subskrypcji i nie wykonuje usuwania.

Jeden workspace/config ma jednego właściciela wykonania. Kilka terminali może być osobnymi procesami interfejsu; „jedna instancja” nie oznacza jednego wątku dla całego programu ani zakazu okien klienckich.

### Kolejność autorytetu

Nowy `spec.md` określa rezultat. Kod baseline mówi, co jest obecnie. Starsze sekcje 06 wyjaśniają historię, ale nie mogą przywracać odrzuconej semantyki. W szczególności nie wracają: niezależny codzienny przełącznik pobierz-bez-przetwarzania, tracker obejrzenia, dodatkowy `inbox`, katalogi rewizji i SQLite. Korekta R-032 usuwa również katalogi pobrań per tytuł: nowe i ponawiane pobrania zapisują pliki bezpośrednio w `workspace/`, bez dodatkowego `downloads/`.

Pozostałe aktualne konwencje `AGENTS.md` obowiązują. Wykonawca czyta scoped instrukcje application/cli/platform/services i tests przed edycją. Komunikaty do użytkownika są polskie, kod i nazwy plików angielskie. Nie zmieniamy zależności runtime w tym zakresie.

### Aktywne kolizje

Workstream 06 nie został końcowo odebrany. Aktualizujemy jego żywy kontrakt i plan, zamiast uruchamiać równolegle drugi workstream ustalający inne znaczenie Auto. Podczas wdrożenia nie uruchamiać nowego kodu na danych obsługiwanych przez starego ownera. Przed zmianą gałęzi agent porównuje HEAD, `git status` i dotknięte symbole. Zmiana poza tym zakresem nie unieważnia automatycznie planu.

## 4. Projekt techniczny

### D-015. Jawne miejsca wejścia, nie heurystyka „czego teraz brakuje”

Dodać mały czysty moduł **`application/workflows.py`**. To jedyne nowe miejsce reguł wyboru celu. Nie jest registry pluginów. Zawiera zamknięty typ celu i funkcję rozstrzygającą pierwszą część ścieżki względem workspace.

Planowane wartości celu wykonania: `video`, `translate`, `audiobook`, `cover`. Dodatkowa właściwość wejścia `requires_sidecar` jest prawdziwa w `subs`. `ready` i `temp` to obszary danych, nie cele wykonania. Nie tworzyć `RunMode.AUDIOBOOK` ani odrębnego trybu regeneracji.

Routing ma następującą kolejność:

1. Ścieżka poza workspace, symlink/junction poza dozwolonym drzewem, temp lub ukryte dane: nie jest wejściem Auto.
2. Pierwszy segment `ready`: można odczytać inventory/Bibliotekę, nie tworzyć Auto.
3. Pierwszy segment `subs`: cel video, obowiązkowy sidecar.
4. Pierwszy segment `translate`, `audiobook` albo `cover`: odpowiedni cel.
5. Pozostała ścieżka: zwykłe video. TXT/SRT bez filmu pozostają materiałem do Ręcznego lub do umieszczenia w odpowiednim miejscu.

Ręcznie utworzone lub zastane zagnieżdżenie dziedziczy pierwszy segment; jest to zgodność odczytu, nie polecenie tworzenia katalogów serii. Nie interpretować każdej nazwy `subs` znalezionej głębiej jako nowej strefy. Porównania nazw systemowych na Windows są case-insensitive; fizycznie tworzone nazwy są małymi literami.

Stałe nazw ścieżek trafiają do istniejącego `anishift/paths.py`; `workflows.py` dostaje relatywną ścieżkę i nie importuje konfiguracji czy usług. Nie mieszamy routingu z ffprobe.

### D-016. Discovery rozpoznaje rolę pliku w zadaniu

Rozszerzyć `SourceGroup`/inspected group o cel wejścia i pochodzenie, zachowując kompatybilny domyślny cel dla starych grup. Dokładne umiejscowienie pola ma unikać cyklu `artifacts ↔ intents`; typ celu z `workflows.py` importuje wyłącznie bibliotekę standardową.

Nie dopisywać `.srt` do globalnej `_PRIMARY_SOURCE_KINDS` bez kontekstu. Zmienić wejście `classify_artifact`/grupowania tak, żeby znało cel. Warstwy wyższe nie tworzą drugiego parsera nazw.

| Cel | Główne źródło | Towarzyszące źródła | Konflikt |
|---|---|---|---|
| video | MKV/MP4 | exact-stem ASS/SRT/SSA, istniejące zgodne produkty | Nierozstrzygnięty konflikt źródeł; kilka sidecarów bez wyboru |
| translate | TXT lub napisy | Nie potrzebuje filmu | Dwa niezależne primary o tej samej bazie |
| audiobook | TXT/SRT | Nie potrzebuje oryginalnego audio | ASS/SSA jako żądanie audiobooka; kilka primary |
| cover | TXT/SRT albo audio | Dokładnie jeden obraz | Kilka obrazów, kilka niezależnych źródeł treści |

Puste, oczekujące grupy `subs`/`cover` muszą być widoczne w Przetwarzaniu bez planu wykonania. Brak składnika to opis oczekiwania, nie nowy FAILED run i nie zjadanie retry. Nie generować wątku oczekującego dla każdej pary.

Produkty tworzone w trwającym zadaniu nie są nowymi primary. Wykorzystać istniejące planned outputs, własność artefaktów i staging. W `cover` dostarczony `Book.mp3` jest źródłem audio, a nie gotowym lektorem do nieistniejącego filmu. W `audiobook` wynikowe audio należy do grupy źródłowego tekstu.

Konwencja `.pl` pozostaje w `products.py`. Nie wymaga się jej dla sidecarów. Nie wystarczy też zobaczyć `.pl.srt`, aby uznać dowolną grupę za wynik konkretnej zapisanej operacji. Poświadczenie produktu i wybór pliku użytkownika mają odrębne pochodzenie.

Dodać rozpoznanie SSA jako wejścia rodziny ASS i skierować je do używanego parsera pysubs2; staging/output normalizować do ASS. Sprawdzić także `subtitle_kind` i walidatory, które obecnie rozróżniają tylko ASS/SRT. Nie wystarczy dodać rozszerzenia w discovery; nie budować osobnego parsera SSA.

### D-017. Trzy bazowe recepty, zero kopii globalnych ustawień

Zachować istniejący preset wideo. Dodać do trwałej polityki automatyzacji małą strukturę preferencji recept, a nie trzy pełne `UserSettings`:

- translate: wybór wyniku TXT→TXT/SRT i polityka tłumaczenia właściwa dla celu;
- audiobook: tłumacz według polityki / czytaj bez tłumaczenia, domyślnie oś ciągła;
- video: wykorzystuje istniejący `AutoPreset` i jego produkty;
- subs: video z twardym wymogiem `SIDECAR`;
- cover: audiobook z obowiązkowym obrazem i eksportem MP4.

Model, provider, profile głosu, gain, kodek audio i limity pozostają w obecnym `UserSettings`/profilach. Do przyjętego `GroupIntent` materializować cel, produkty i ewentualne jednorazowe nadpisania. `RunSettingsSnapshot` nadal zachowuje ustawienia przyjęcia. Nie odczytywać globalnego nowego głosu w połowie starego runu.

The selected local video preset intentionally produces sidecars. Preserve it: merged containers are explicit exports, not a requirement for watching. Library Enter opens the recorded video of a completed sidecar-only video set through the existing OS association; F reveals its confirmed main product. Do not add player installation, configuration or mpv-specific arguments. Playback selection does not rewrite product provenance.

Zachować publiczny format istniejących presetów wideo. Nowe wybory tekstowe nie dopisują nieznanych pól do każdego starego presetu. Ich trwałość należy do rozszerzenia stanu recept; per-run zamiar nadal jest serializowany przez istniejące kontrakty.

### D-018. Te same usługi, nowe legalne wejścia i produkty

Planowane rozszerzenia typów są małe i odpowiadają rzeczywistym mediom:

- `ArtifactKind.TRANSLATED_TEXT` i odpowiadający wybór produktu TXT;
- `ArtifactKind.SOURCE_IMAGE`;
- odróżnienie finalnego cover MP4 od wejściowego MP4 w tabeli produktów, np. `COVER_MP4` z sufiksem `.cover.mp4`;
- zadanie tłumaczenia tekstu do TXT i lokalnej konwersji TXT→SRT, jeśli istniejące task kinds nie wyrażają ich poprawnie;
- kompozycja cover jako osobny wariant zadania w istniejącej domenie composition, nie nowy pipeline.

Nazwy konkretnych nowych enumów są planowane; lokalna zmiana nazwy jest dozwolona. Nie wolno natomiast udawać źródłowego wideo, aby obejść `_build_media_plan`.

Rozszerzyć `_GroupPlanner.build` o rozstrzygnięcie celu. W obrębie zwykłego video zachować działający `_build_media_plan`. Dla translate, audiobook i cover zbudować tylko potrzebny graf. `plan_auto` i `plan_manual` nadal prowadzą do wspólnego `_plan` i tych samych handlerów.

Recepty różnią się na poziomie group intents. Plan z kilkoma różnymi celami nie może przypisać wszystkim produktów wideo z jednego globalnego presetu. Auto przyjmuje niezależne legalne grupy, a blokujące wejście jednej grupy nie wyzerowuje grafów reszty. W jawnym podglądzie Ręcznego zachować czytelną odmowę nierozstrzygniętego wyboru, zamiast wykonywać ukryty podzbiór.

#### Tekst i napisy

`TranslationTaskHandler` otrzymuje gałąź TXT-output. Reużyć `TranslationExecutor.translate_file`, ale nie zapisywać tekstu przez `spoken_to_srt`. Nie korzystać z obecnego spłaszczania wszystkich białych znaków jako kontraktu dla dokumentu TXT.

Zachować kolejność akapitów przez lokalne identyfikatory fragmentów i jawny opis separacji. Długie akapity mogą być dzielone przez obecne chunkowanie, ale wynik jest składany po ID w oryginalnej kolejności, z zachowaniem pustych linii między akapitami. Nie opierać złożenia na tym, czy model odtworzył specjalny separator.

Walidacja kompletności ma analogicznie do `_require_complete_translation` odrzucić brakujący, pusty lub przestawiony fragment. Nie rozszerzać tego zadania do wiernego formatowania EPUB/PDF.

Dla SRT zachować czasy i liczbę merytorycznych zdarzeń. Dla ASS/SSA używać istniejącego `write_translated`/tag-safe text, zachowując style, rysunki, komentarze i wymagane metadane zgodnie z aktualnym kontraktem parsera. Nie klasyfikować dekoracji jako nowego zadania audiobookowego.

TXT→SRT bez dźwięku reużywa istniejącego `spoken_to_srt`: to roboczy skrypt z czasami szacunkowymi. Ten fakt ma być metadanymi podglądu/szczegółów; nie budować nowego algorytmu synchronizacji ani wywołań TTS dla translation-only.

#### Audiobook i głos na osi czasu

W `TtsTaskHandler` wydzielić mały wspólny etap budowy `SpeechRequest` oraz `NarrationTiming` z rozstrzygniętego tekstu. Tekst samodzielny i SRT nie wymagają wideo. Nie duplikować retry, walidacji klipów ani sesji dostawcy.

Dla osi ciągłej klipy zachowują `source_order`, a ich minimalne okna zaczynają się od zera. Istniejąca polityka serializacji audio układa je kolejno według rzeczywistych długości. Nie sklejać strumieni MP3 przez konkatenację bajtów i nie nakładać ich jednocześnie. Dla „Czasy SRT” przekazać oryginalne okna, korzystając z obecnego zachowania nakładek/serializacji.

`AudioTaskHandler._mix` ma dwa ścisłe warianty: manifest + oryginalne audio dla wideo albo sam manifest dla audiobooka. W tym drugim `source_audio_path=None`, co jest już legalne w `AudioRenderRequest` i `AudioService`. `source_path` jest istniejącym identyfikatorem materiału/ścieżką tekstu, nie wygenerowanym fałszywym WAV ciszy.

Nie dodawać nowej polityki `TimelinePolicy`, jeśli ustawienie okien przez caller spełnia kontrakt. Fingerprint musi jednak uwzględniać sposób budowy timingów, aby stare audio na osi źródła nie było cache-hitem dla osi ciągłej.

Sam głos bez tłumaczenia nie musi udawać artefaktu polskiego, jeśli użytkownik jawnie wskazał inną treść. Rozszerzony kontrakt wejścia TTS przenosi tekst i deklarowany język; aktualny wybrany głos musi go obsłużyć. Brak obsługi daje błąd przed kosztowną pracą, nie samoczynny wybór innego modelu.

#### Obraz i MP4

Zweryfikowane `CompositionTaskHandler.execute` wywołuje `build_composition_request`, które bezwarunkowo wymaga źródłowego MKV/MP4. Dodać rozdzielenie na zwykły kontrakt kontenera i kontrakt cover przed tą walidacją. Zwykły wariant nadal wymaga wideo i zachowuje dotychczasowe reguły destination; cover wymaga SOURCE_IMAGE oraz gotowego audio. Nie podstawiać obrazu pod `source_video` tylko po to, by zaspokoić stary typ.

W `services/composition` dodać małą gałąź przyjmującą zwalidowany obraz i audio. Reużyć obecnego process runnera, obsługi postępu, cancel, timeout, probe i atomowej publikacji. Pillow jest już zależnością: może wykonać walidację, orientację i przygotowanie pojedynczego kadru.

Domyślny kadr: 1920×1080, obraz dopasowany z zachowaniem proporcji, czarne dopełnienie, bez przycinania i bez animacji. To decyzja implementacyjna dla jednego prostego eksportu, nie nowy edytor wideo. Kadr w staging jest pojedynczym obrazem, nie materiałem z milionami zapisanych klatek.

FFmpeg odczytuje obraz przez `image2` z `pattern_type=none`, `loop=1` i jawnym framerate, mapuje dokładnie jeden strumień obrazu i audio. Wynik: H.264, yuv420p, AAC, MP4 z faststart; koniec według audio przy nieskończonym wejściu obrazu. Nie używać długości pierwszego fragmentu tekstu jako czasu całego filmu. Stała 25 fps jest parametrem eksportu, nie odczytem z obrazu.

Walidacja sprawdza obecność obu strumieni, niezerową długość oraz zachowanie końcówki dźwięku. Nie przenosić `-shortest` bezrefleksyjnie do zwykłej kompozycji filmu, gdzie inna ścieżka może być krótsza niż lektor.

### D-019. Ukończony zestaw ma pamiętać swój cel

Dodać jedną małą strukturę pochodzenia gotowej grupy wewnątrz istniejącego `WatchState`, planowana nazwa `ReadyGroup`. To nie drugi katalog anime i nie historia oglądania.

Minimalne informacje: stabilna tożsamość logiczna zestawu, bieżąca grupa/rdzeń nazwy w ready, wejściowy katalog i rdzeń nazwy, cel/recepta przyjęcia, należące źródła, odwołania do potwierdzonych produktów, główny wynik i ewentualne źródło czekające na zwolnienie przez torrent. Bieżące `exists` i postępy są pochodne, nie zapisywane osobno jako konkurencyjna prawda.

`ReadyStore.apply` aktualizuje tożsamości requests/markers/products jak dziś, a także rekord zestawu. Po usunięciu dziennika relokacji nadal wiadomo, że `ready/Book [2]` było audiobookiem z `audiobook/Book`, a nie zwykłym materiałem video.

Ten zapis służy czterem istniejącym potrzebom nowej specyfikacji: poprawnej regeneracji po relokacji, szczegółom plików, bezpiecznemu usunięciu całego zestawu i odrzuceniu błędnej interpretacji późnego sidecara. Nie służy szukaniu podobnych anime po dysku.

Nie trzymać kolejnej pełnej kopii `ProductConfirmation`. Rekord zestawu odsyła do potwierdzonych produktów; zapisuje tylko źródła i brakujące pochodzenie. Zewnętrzne pliki użyte w Ręcznym są referencjami tylko do odczytu, nie własnością do usunięcia.

### D-020. Płaskie pobrania, gotowość plików i bezpieczna relokacja

**Jedynym celem nowych i ponawianych pobrań jest główny `workspace/`.** Wspólna granica pozyskania ustala ten cel dla Anime, subskrypcji i Ponów. Usunąć tworzenie ścieżek docelowych z tytułu/sezonu/grupy; etykiety katalogu anime pozostają metadanymi. Historyczne `Subscription.directory` i zapisane położenie istniejącego transferu służą tylko do jego odczytu i migracji, nie wyznaczają miejsca następnego pobrania.

W `application/acquisition.py`, `application/subscriptions.py`, `services/torrents/qbittorrent.py` i wywołujących sprawdzić drogę wyznaczenia ścieżki do klienta. Sama zmiana `save_path` nie stanowi dowodu płaskiego zapisu paczki: jej wewnętrzne ścieżki też muszą być rozstrzygnięte. Przed dopuszczeniem transferu zawartości pozyskać metadane i ustawić przez klienta płaskie ścieżki wybranych plików. Użyć dostępnej funkcji klienta, nie drugiego downloadera. Brak możliwości bezpiecznego ustawienia układu zatrzymuje tylko to wydanie z problemem; nie uprawnia do cichego utworzenia katalogu tytułu. Ten kontrakt musi przejść próbę na docelowym qBittorrencie.

Owner rezerwuje docelowe nazwy przed zapisem danych. Domyślnie zachować nazwy wydania. Gdy koliduje którykolwiek plik zestawu, wybrać wspólny wolny rdzeń z dopiskiem `[2]`, `[3]` itd. dla powiązanego wideo i sidecarów. Sprawdzać też zarezerwowane nazwy innych pobrań i pochodne produkty. Zapisać mapowanie infohash + indeks pliku → ścieżka względna; to ta mapa, nie nazwa katalogu, łączy transfer z materiałem. Nie deduplikować różnych wydań po samej nazwie.

Obecne `TransferInspector._inspect` wymaga gotowości całego transferu. Rozszerzenie nie polega wyłącznie na zmianie etykiety procentu.

W potwierdzeniu pozyskania zapisać zweryfikowane pliki wraz z rozróżnieniem wybranych i kompletnych. Tożsamość pliku: infohash + indeks pliku klienta + oczekiwana ścieżka/rozmiar. Nie używać samego numeru wiersza UI. Poszerzyć typ `TorrentFile`, jeśli odpowiedni stabilny indeks nie jest jeszcze publicznie dostępny.

Gdy transfer ma już metadane i zmienia postęp, odświeżać szczegóły wybranych plików w istniejącym ograniczonym rytmie transferów. Nie cache'ować ich do momentu 100% całej paczki. Dla pojedynczego kompletnego pliku wymagać potwierdzenia klienta, zakończonej weryfikacji, bezpiecznej ścieżki, zgodnego rozmiaru i lokalnej dostępności. Nie uzależniać tego od `amount_left==0` całego torrenta.

Wznowienie/recheck/cofnięcie kompletności unieważnia jeszcze nieprzyjętą gotowość. Nie rozpocząć ponownie już przyjętego runu tylko z powodu kolejnego odczytu postępu. Wspólny katalog pobrań nie jest blokadą całego workspace: transfer przed poznaniem i rezerwacją nazw nie może zapisywać zawartości, a po ich ustaleniu Auto blokuje tylko przypisane mu niekompletne pliki. Niezależny ręcznie dodany film może zostać przetworzony równolegle.

Gdy manifest torrenta już deklaruje sidecar tego samego odcinka, oczekiwany zestaw obejmuje go nawet w zwykłym wejściu video. To wiedza o zamówionych plikach, nie heurystyka przewidująca przyszłe działania człowieka. `subs` zawsze wymaga sidecara.

Wynik gotowego odcinka publikować do `ready` niezależnie. Źródło nadal używane przez aktywną paczkę pozostaje na miejscu; `ReadyGroup` zachowuje referencję i oczekującą relokację. Po ukończeniu wybranych plików i zwolnieniu torrenta przenieść źródła do ustalonego wcześniej zestawu w ready.

Potrzebne rozszerzenie `ReadyStore`: przygotowanie docelowego rdzenia nazwy raz, możliwość relokacji produktów bez źródeł i późniejsze dokończenie źródeł. Nie wybierać nowego `[3]` przy drugiej części tego samego przeniesienia. Nie kopiować MKV, nie usuwać całego torrenta po pierwszym odcinku i nie zatrzymywać pozostałych pobrań.

### D-021. Pamięć pobrania jest niezależna od obecności pliku i historii UI

Rozszerzyć `EpisodeOrder` o jawny udział w zamówieniu, a `Subscription` o wybrany zakres i ewentualny ogon przyszłych odcinków. Konkretny projekt danych:

- znane numery nadal jako `Decimal` serializowany tekstowo;
- zbiór/rekord wybranych numerów i wykluczeń, nie sam `next_episode`;
- `future_from` jako granica automatycznego objęcia kolejnych zwykłych odcinków lub None;
- trwałe potwierdzenie pobrania z istniejącego `AcquisitionConfirmation`;
- tożsamość jawnego ponowienia, aby ukończony historycznie numer mógł być zamówiony jeszcze raz bez wymazania historii.

Wybór w UI nie modyfikuje `taken` ani `COMPLETE`. Kursor `next_episode` pozostaje pomocniczy/kompatybilny i jest wyliczany ze zbioru potrzeb, nie stanowi definicji całego zakresu.

Podświetlenie, zaznaczenie i fakt ukończenia to różne dane. W liście kulek widoczny wybór ma oznaczać oczekujące zamówienie. Za nim muszą pozostać osobne fakty: ukończone pozyskanie oraz nieukończona obróbka. Błąd TTS nie usuwa kompletności źródła i nie zleca add torrenta.

`A` zaznacza do nowego zamówienia zwykłe znane, dotąd nieukończone numery. Nie resetuje ukończeń. Dla ukończonego numeru użytkownik wybiera go i używa „Ponów”. Jeśli źródło jest nadal dostępne, ponowienie proponuje dokończenie/przebudowę, nie ukryte pobranie jeszcze jednej kopii; jeśli zostało usunięte, wykorzystuje zapisane zamówienie internetowe. Karta nie wymaga akcji „Mam lokalnie”.

Przy tworzeniu subskrypcji wcześniejsze numery można po prostu pozostawić odznaczone. Nie wdrażać porównywania całego dysku z katalogiem sezonu. Dedup znanego własnego torrenta i tej samej zapisanej operacji nadal obowiązuje, nawet bez takiego matchera.

Domyślny zakres obejmuje wskazany sezon. Dodatki spoza niego nie są automatycznie wciągane. 7.5 pozostaje osobną pozycją w znanej numeracji; nie zamienia się w 7 lub 8.

### D-022. Jedna publiczna pauza całego przepływu

Nie tworzyć obok siebie `watch_enabled`, `auto_enabled`, `download_enabled` i `resident_enabled` jako czterech przełączników użytkownika. Dotychczasowe pole `AutomationPolicy.auto_enabled` można zachować technicznie jako jedną trwałą zgodę na automatyczne wykonywanie, ale rozszerzyć jego skutek na harmonogram i transfery. UI nazywa stan Praca/Wstrzymano.

Po przyjęciu Zatrzymaj owner najpierw zapisuje zamiar, podnosi generację sterowania i blokuje nowe admission. Wyniki wolnego wyszukiwania muszą ponownie sprawdzić tę generację przed add. Własne aktywne transfery otrzymują stop; zapisać dokładnie zestaw zatrzymany tą pauzą, żeby Wznów nie uruchomiło cudzych/indywidualnie zatrzymanych.

Koordynator kończy rozpoczęte taski do bezpiecznej granicy. Nie wywoływać destrukcyjnego `cancel` wyłącznie po to, by imitować pause. Widok Pausing jest pochodną trwałego żądania pauzy i pozostałych aktywnych operacji. Po rozliczeniu przejść do oczekiwania na komendę; nie odpytywać okresowo Nyaa/qBit/FFmpeg.

Wznowienie przywraca bieżące uzgodnienie plików i kalendarza tylko aktywnych wpisów. Nie odtwarza każdej pominiętej godziny. Zachować limiter i historię retry. Wiele kliknięć ma tę samą idempotentną semantykę co obecne polecenia.

Przy nowej konfiguracji automatyzacja jest aktywna. Migracja zachowuje stare jawne Auto OFF jako pauzę do kontrolowanego przejścia. Historycznie wyłączone subskrypcje i zatrzymane transfery pozostają wyłączone. Dawne wyjątki katalogów trzeba wykazać w preflightcie; nie usuwać ich ani nie zostawiać jako niewidzialnych przeszkód. Przejście tych wyjątków zatwierdzić jednorazowo razem z nową rolą folderów, zanim aktywuje się produkcyjny runtime.

### D-023. Prywatny klient i cykl okien

Zmienić startup właściciela tak, aby w stanie Praca przygotowywał/dołączał własnego qBittorrenta przy starcie, nie dopiero przy download. Stan trwałej pauzy jest wyjątkiem: nie musi startować zatrzymanego klienta tylko po to, by nadal nic nie robił.

Istniejące dowody własności PID/czas utworzenia/binarka/profil/uwierzytelniony endpoint pozostają. Sam fakt widocznego własnego okna nie odbiera AniShift prawa do własnego profilu. Obcy lub niepewny proces nadal nie może być rekonfigurowany czy zamknięty. Zmiana tej reguły wymaga testów, nie usunięcia całego `_assert_ownership`.

Zakończ: zapisać shutdown → zablokować nowe admission → rozliczyć przyjęte operacje/bezpieczne taski → wstrzymać własne pobrania → zapisać resume klienta i zakończyć potwierdzoną własną instancję → wysłać panelom końcowy stan → zamknąć IPC/tray/watch/lock. Nie kończyć wszystkich `qbittorrent.exe` ani `python.exe` po nazwie.

Panel nie jest właścicielem zlecenia. Jego exit zamyka sesję IPC i zwalnia niezatwierdzone rezerwacje, nie startuje shutdown. Autostart pozostaje istniejącym mechanizmem po logowaniu; nie tworzyć usługi systemowej ani nowego zadania dla każdego folderu.

### D-024. Jeden widok pracy, krótka karta subskrypcji

Zamienić `_TABS` na `Anime`, `Subskrypcje`, `Przetwarzanie`, `Biblioteka`. Zachować istniejący `StateController` jako shell Panelu, nie budować osobnego panel frameworka.

`AnimeController` może zostać dzieckiem zakładki Anime. Otrzymuje cel powrotu i potrafi zwrócić przygotowaną intencję subskrypcji, zamiast od razu wywołać follow/check. Jego wyszukiwanie, grupowanie, filtry 1080p+, zakres, sortowanie i zabezpieczenie spóźnionych odpowiedzi pozostają.

Dodanie z Subskrypcji przechodzi do tego samego kontrolera. Wybranie „Subskrybuj” przenosi przygotowany draft do karty subskrypcji; dopiero zastosowanie zakresu składa polecenie właścicielowi. Grupa Anime otwiera się jak folder, Enter zaznacza odcinek, a jawne Pobierz zatwierdza zakres i przełącza do Przetwarzania. Nie tworzy subskrypcji. Po przyjęciu pozycji nie można przypadkowo zamówić ponownie przez zwykłe zaznaczanie.

Dla karty odcinków wystarczy rozszerzenie kontrolera zakładki albo jeden moduł `interactive/subscriptions.py`, jeśli oddzielenie rzeczywiście zmniejsza `state.py`. Nie tworzyć nowego pliku na listę, szczegół odcinka, zegar, akcję Space i potwierdzenie. W planie nowy kontroler subskrypcji jest jedynym przewidywanym wydzieleniem UI.

Przetwarzanie pokazuje bieżące pobrania i obróbkę zgodnie z R-043 i R-019. Wykorzystuje istniejący `RichRunProgress`, styl pasków i pomiary klienta torrent. Jeden zestaw widocznych pozycji steruje renderem, zaznaczeniem, stopką i akcjami. Przed metadanymi używa zachowanego tytułu wydania; po poznaniu plików ich rzeczywistych nazw. Przyjęcie, przygotowanie, pauza i brak transferu mają czytelne stany, nie fikcyjne procenty. Nie pokazuje hashy ani nierozliczonych operacji Kosza; historia zakończonych prób i problemy Biblioteki zachowują bezpieczne akcje. Techniczny snapshot i trwałe potwierdzenia pozostają źródłem stanu. Ręczne usunięcie transferu nie zabija ownera i nie wysyła ponownego add.

Projekcja Przetwarzania wyklucza niepewne pobrania i ich przekazania do kolejki; ten sam filtr steruje licznikiem, wyborem, akcjami oraz timerami. Przyjęte lokalne zlecenie obróbki ma niezależny dowód wykonania. Anime jest jedynym właścicielem fokusu swoich pól: Enter aktywuje zapytanie, Esc lub niezaznaczone Ctrl+C odbiera fokus, a ←/→ należą do edytora tylko podczas edycji. Tab zawsze przełącza zakładkę i odbiera fokus; powrót zachowuje szkic. Zmiana zakładki unieważnia spóźnioną nawigację. Wspólny TextInput podświetla grafem jako blok kursora zamiast wstawiać kreskę pomiędzy litery; nieaktywne pole renderuje samą treść.

Results remain grouped by material, not by every task. All visible bars use numeric percentage and elapsed fields; initial unknown values render zero, while later missing observations retain the last value and freeze the clock. Backend facts remain unknown until measured. Attached panels receive real transfer observations approximately once per second. Errors retain one concise reason; details open on demand.

### D-025. Biblioteka jest projekcją gotowych zestawów i dysku

Owner publikuje dane listy na podstawie potwierdzonych gotowych grup, źródeł i aktualnego inventory. Biblioteka nie pokazuje każdego wykrytego MKV jako gotowego. Główny wynik wyznacz raz z zamówionych produktów: video wybiera MKV przed MP4, bez kontenera zamówione audio przed pełnymi napisami; translate wybiera wskazany TXT/SRT/ASS, audiobook audio, cover MP4. W `ReadyGroup` zapisać odwołanie do tego wyniku. Brak pliku nie uruchamia cichego fallbacku do innego produktu ani oryginału.

Enter uses the owner's validated opening target: final video when produced, otherwise recorded source MKV/MP4 for a completed video set, with MKV priority. Other targets open their confirmed main product. Keep the existing `library_open` response and OS association; optional `playback=False` lets F reveal the confirmed product even when source video is missing. Missing/changed required products still refuse. Details retain exact file roles and product identity.

Odczyt listy nie ma prawa odtwarzać Auto w ready. Zewnętrzne usunięcie aktualizuje inventory i projekcję. Wykorzystać istniejący watcher, jego cache i broadcast state_changed. Przy otwarciu widoku wykonać lekkie uzgodnienie, by nie polegać na zdarzeniu, którego panel nie widział.

Odświeżanie co sekundę oznacza maksymalny rytm prezentacji aktualnego snapshotu, nie pełne discover/probe co sekundę. Zachować wybór po ID. Jeżeli zaznaczony plik zniknie, wybrać sąsiedni bez przenoszenia starej destrukcyjnej akcji na nowy wiersz.

Istniejące gotowe grupy sprzed nowego zapisu pochodzenia importować z wiarygodnych confirmations/requests i realnie poprawnych plików w ready. Wynik o nierozstrzygniętym celu może być otwierany i oglądany w szczegółach, ale regeneracja wymaga jawnego wyboru celu. Nie klasyfikować go do wideo tylko dlatego, że metadane nowego formatu jeszcze nie istnieją.

### D-026. Kosz: dwie czynności użytkownika, jedna jawna operacja

The application prepares the exact whole-set deletion preview internally. Delete immediately submits that preview in the same worker session, without a confirmation screen. The owner executes the command outside the renderer; Ctrl+Z restores the last deleted set.

Źródłem listy jest zestaw/proweniencja i istniejący klasyfikator sufiksów, nie `glob(stem + '*')`. Uzupełnienie o znany sidecar musi potwierdzić dokładny rdzeń nazwy. Chronić `Episode 01` przed wciągnięciem `Episode 010`, innej wersji i innego katalogu. Nie usuwać symbolicznych odwołań poza workspace.

Nowy mały adapter **`platform/recycle.py`** używa natywnego Windows `IFileOperation` przez istniejący w projekcie styl interop `ctypes`. To granica platformowa, nie ogólny manager plików. Ustawić tryb recyklingu, jawnie obsłużyć HRESULT i wynik przerwania. Nie uznawać samego sukcesu `PerformOperations` za dowód przeniesienia wszystkich plików.

Nie używać `FOF_NOCONFIRMATION` jako przyzwolenia na ewentualne trwałe skasowanie. Adapter nie ma fallbacku `unlink`, `rmtree` ani `deleteFiles=true` qBittorrenta. Próba na nośniku bez dostępnego Kosza ma zakończyć się odmową. To obowiązkowy gate platformowy; jeśli natywna droga nie spełnia tego kontraktu, nie uruchamiać jej na bibliotece użytkownika.

Przed wykonaniem owner ponownie sprawdza fingerprint zakresu, brak writerów, brak aktywnego runu i brak własności źródła przez aktywną paczkę. W tym ostatnim przypadku operacja mówi, że źródło czeka na zwolnienie; nie zatrzymuje całego sezonu i nie ogłasza usunięcia nieusuniętych plików.

Persist deletion evidence and per-file outcomes in the existing state. After interruption reconcile original identities and API results; do not delete a new file at the old path. Library shows remaining material as plain entries rather than operation/status rows. Recovery evidence remains in the owner ledger.

### D-027. Historia jest dziennikiem zdarzeń, nie nową prawdą wykonawczą

Dodać prosty append-only zapis JSONL pod `config/watch/history.jsonl`, obsługiwany przez jeden mały moduł **`application/history.py`**. Owner jest jedynym autorem. Zapis obejmuje przyjęcie zamówienia, pobranie, zakończenie/przerwanie/błąd przetwarzania, regenerację i usunięcie. Nie logować każdego procentu, treści tekstów, kluczy ani pełnych URL-i z sekretami.

Identyfikator zdarzenia jest stabilny dla danej operacji/generacji/rodzaju. Replay receipt nie dopisuje drugiego sukcesu. Dla retry historia rozróżnia próbę, ale zwykła lista nie mnoży niepotrzebnie wierszy materiału.

Retencja 30 dni dotyczy wyłącznie tego dziennika. Projekcja pokazuje ostatnie 50 zakończonych materiałów z możliwością szukania w zachowanym okresie. Porządek historii jest czasowy, Biblioteki alfabetyczny. Nie kopiować do JSONL pełnego grafu, settings i napisów.

Przy starcie i następnej potrzebnej dobie można atomowo przepisać dziennik z pominięciem starszych zakończonych wpisów. Nie dodawać pętli minutowej do rotacji. Niedomknięta ostatnia linia po awarii nie psuje pozostałych wpisów. Historia nigdy nie ustala, czy odcinek wolno pobrać ponownie: robi to trwały zapis zamówień.

Aktywne requests, problemy, potwierdzenia pobrania, `ReadyGroup` i źródła regeneracji mają własny wymagany cykl życia. Pruning historii nie usuwa ich kaskadowo. Trwała pamięć wykluczająca ponowne pobranie pozostaje także po usunięciu subskrypcji, jeśli istnieją powiązane własne zamówienia.

**Uzupełnienie zatwierdzone przez właściciela 2026-09-17:** istniejące `AcquisitionConfirmation` zachowuje opcjonalną referencję wydania Nyaa: identyfikator wydania i oryginalny tytuł, obok już zapisywanego hasha. Referencja jest utrwalana przy przyjęciu zamówienia i przeżywa usunięcie subskrypcji oraz rotację historii. Historia odsyła do operacji; nie przechowuje pełnych URL-i ani drugiej kopii zamówienia. Referencja pochodzi ze zweryfikowanego adresu źródła, a jej odtworzenie należy do adaptera Nyaa. Starsze wpisy bez referencji nadal chronią przed automatycznym pobraniem; jawne Ponów może wymagać ponownego wyboru wydania. Nie zgadujemy brakujących danych z nazwy pliku ani nie dodajemy alternatywnej drogi magnet. Test obejmuje zgodny odczyt starego zapisu, restart, usunięcie subskrypcji i jawne ponowienie bez utraty wcześniejszych faktów.

### D-028. Czas i stopka nie wymagają nowych usług

W projekcji subskrypcji przekazywać `airing_at`, pochodzenie, stan wydania i właściwy przyszły termin. Widoczny UI wylicza `max(0, termin - teraz)` w sekundach. Po przekroczeniu terminu zmienia etykietę zamiast odliczać ujemnie. Zmiana daty z backendu od razu zastępuje poprzedni cel zegara.

Renderer ma już rytm odświeżania. Wykorzystać go tylko w widocznych widokach; nie tworzyć wątku zegara na subskrypcję i nie odpytować katalogu z render(). Moment emisji, oczekiwane wydanie i gotowość wyniku nie są jednym czasem.

Wspólna stopka dostaje policzone przez ownera liczby aktywnych transferowanych materiałów i materiałów obrabianych, plus stan globalnej pracy. Liczyć logiczne pozycje, nie techniczne taski. Zamknięty panel nie jest powodem, aby utrzymywać co-sekundowe IPC/broadcast.

## 5. Struktura zmian w repozytorium

Docelowe pliki, które **mogą** wymagać edycji w tym zakresie:

```text
anishift/
├── paths.py                            nazwy miejsc, bez input/output duplikatów
├── bootstrap.py                        skład istniejących handlerów
├── application/
│   ├── workflows.py                    NOWY: czyste rozstrzyganie celu i recepty
│   ├── artifacts.py                    nowe typy tekstu/obrazu, cel grupy
│   ├── products.py                     nazwy nowych produktów
│   ├── discovery.py                    primary/sidecar według celu
│   ├── inspection.py                   standalone audio, obraz, tekst, SSA
│   ├── selection.py                    deterministyczny wybór wejść
│   ├── intents.py                      cel i jednorazowe wybory
│   ├── planner.py                      nowe grafy we wspólnym plannerze
│   ├── planning.py                     taski, snapshoty, walidacja grafu
│   ├── translation_handler.py          TXT jako TXT, bez nowego tłumacza
│   ├── subtitle_handler.py             konwersja TXT→SRT / normalizacja SSA
│   ├── tts_handler.py                  standalone tekst i sposób timingów
│   ├── audio_handler.py                oryginalne audio opcjonalne
│   ├── composition_handler.py          delegacja cover do istniejącej domeny
│   ├── service.py                      fasada nowych zamiarów/operacji
│   ├── automation.py                   routing, pause, status, przyjęcie poleceń
│   ├── control.py                      trwałe kontrakty i proweniencja zestawów
│   ├── control_payloads.py             walidacja nowych payloadów
│   ├── control_views.py                snapshoty bez surowego wnętrza usług
│   ├── watch_state.py                  migracja trwałego stanu
│   ├── watch.py                        fingerprint i kwalifikacja Auto
│   ├── subscriptions.py               zakres i jawne ponowienie
│   ├── transfers.py                    kompletność pojedynczych plików paczki
│   ├── ready.py                        produkty teraz, źródła po zwolnieniu
│   ├── recovery.py                     odtwarzanie rozszerzonego zamiaru
│   ├── history.py                      NOWY: ograniczony dziennik użytkowy
│   └── __init__.py                     tylko potrzebne eksporty publiczne
├── cli/
│   ├── main.py                         wejścia delegujące do ownera
│   ├── watch.py                        startup/tray/pełne zakończenie
│   ├── resident.py                     jawne metody klienta IPC
│   └── interactive/
│       ├── app.py                      Home i powroty bez jednorazowego Auto
│       ├── state.py                    nowy układ czterech zakładek
│       ├── subscriptions.py            NOWY tylko jeśli karta nie mieści się sensownie w state
│       ├── anime.py                    powrót intencji, bez drugiej wyszukiwarki
│       ├── manual.py                   kontekst celu, wyniki i regeneracja
│       ├── progress.py                 pobieranie w ciągłości materiału
│       ├── settings.py                 recepty i odziedziczone parametry
│       ├── settings_editors.py         wyłącznie konieczne nowe typy wyboru
│       ├── menu.py                     istniejące listy/stopka
│       └── prompts.py                  mapowanie klawiszy i widoczne odliczanie
├── config/
│   ├── field_catalog.py                pola recept i dostępne produkty
│   └── field_access.py                 wspólny odczyt/zapis, bez duplikacji settings
├── platform/
│   ├── recycle.py                      NOWY: wyłącznie natywny Kosz
│   ├── qbittorrent_process.py          własny startup/pause/shutdown
│   ├── tray.py                         oddzielne akcje ikony i wyniku
│   └── autostart.py                    istniejący mechanizm, bez nowych usług
└── services/
    ├── composition/                    mała gałąź obraz+audio, istniejący runner
    ├── audio/                          wykorzystanie narrator-only; tylko wymagane korekty
    └── subtitles/                      istniejący parser i zapis TXT/SRT/ASS
```

`composition_handler.py` istnieje w baseline i został odczytany razem z jego `build_composition_request`. Szczegółowe konsumenty w `services/composition` wykonawca zmienia tylko tam, gdzie prowadzi rzeczywista droga adaptera. Sam fakt umieszczenia ścieżki w tym drzewie nie wymaga refaktoryzacji całego modułu.

Trzy potrzebne nowe obszary nie mają już odpowiednika: reguła celu folderu, dziennik użytkowy i adapter Kosza. Kontroler subskrypcji jest opcjonalnym wydzieleniem, nie kolejnym podsystemem. Pozostałe rozszerzenia mieszczą się w istniejących modułach.

## 6. Kolejność wykonania

### P09. Ustalić baseline, zabezpieczyć migrację i dodać routing

**Rezultat:** program umie powiedzieć, jaki cel i komplet ma dana grupa, bez uruchamiania jeszcze nowego zakresu na mediach użytkownika.

1. Porównać aktualny HEAD z baseline w dotkniętych plikach. Odczytać scoped AGENTS. Zanotować niespójności z obecnym README/planem, ale nie naprawiać niezwiązanych problemów.
2. Uruchomić obecne pełne kontrole repo jako punkt odniesienia w izolowanej konfiguracji. Gdy wykryty błąd istnieje przed zmianą, odtworzyć go i oddzielić od nowej regresji; nie dopisywać fikcyjnego „baseline czysty”.
3. W `paths.py` dodać cztery foldery i wyznaczanie ścieżek. Sprawdzić kolizje nazw, wielkość liter, polskie znaki, spacjowane nazwy oraz brak wyjścia przez symlink/junction. Nie zmieniać root/temp/ready dowolnie.
4. Dodać `workflows.py`, cel grupy i testy routingu. W szczególności root→video, subs→video+sidecar, translate→tekst/napisy, audiobook→TXT/SRT, cover→treść+obraz, ready/temp→brak Auto. Ręczne zagnieżdżenie testować tylko jako zgodność odczytu; program nie tworzy katalogów tytułów.
5. Rozszerzyć schemat stanu 1→2 o recepty, rekordy gotowych zestawów i wymagane pending operations. Dopisać jawne defaults dla starych danych. Zrobić backup i test powtórzonego load bez kolejnej migracji.
6. Wykonać preflight zastanej konfiguracji: dawne wyjątki katalogów, nieukończone runy, stare Auto OFF, zarezerwowane nazwy z istniejącą treścią. Nie aktywować ich nową semantyką tylko dlatego, że testy przeszły.

**Dotknięcie:** paths, workflows, artifacts, control, watch_state, discovery i ich testy.

**Sprawdzenie kończące fazę:** tabela routingu ma testy z prawdziwymi katalogami tymczasowymi; żaden test nie odpala sieci. Stare fixtures stanu wczytują się bez zmiany znaczenia ukończonych pobrań. Zwykłe video nadal przechodzi dotychczasowy planner.

### P10. Obsłużyć kompletność i samodzielne tłumaczenie

**Rezultat:** pliki trafiają do właściwego zadania, `subs` nie rusza przed parą, TXT/SRT tłumaczą się bez wideo.

1. Przerobić rozpoznawanie primary według D-016. Zestaw oczekujący może istnieć bez pełnego primary, ale nigdy nie trafia do wykonania jako gotowy. Zachować ID oparte na relatywnej ścieżce i rdzeniu nazwy.
2. Dodać małe predykaty gotowości celu: video, paired video, translate, audiobook, cover. Predykat zwraca gotowość albo jeden stabilny powód oczekiwania/konfliktu. Nie zapisuje błędu runu przy każdym cyklu.
3. Rozszerzyć inspection dla samodzielnych napisów, SSA, tekstu i audio. Nie wywoływać `_catalog_video_duration` bez wideo. Nadal walidować rzeczywiste bajty, nie tylko rozszerzenie.
4. Dopisać produkt translated TXT i bezpieczne nazewnictwo w `products.py`. Źródłowy TXT nigdy nie jest podmieniany przez własny wynik. Kolizja docelowego pliku jest rozwiązana przez właściwy kontrakt publikacji, nie `overwrite=True` na źródle.
5. W plannerze dodać translate-only: TXT→TXT, SRT→SRT, ASS/SSA→ASS. Zachować możliwość TXT→SRT jako roboczego skryptu. Nie dokładać TTS do tego grafu.
6. W `TranslationTaskHandler` zachować strukturę akapitów, completeness i kolejność. Do SRT/ASS nadal używać obecnych parserów/writerów.
7. Zachować pierwszeństwo sidecara tej samej nazwy przed embedded. W `subs` brak sidecara blokuje także wtedy, gdy kontener zawiera poprawne EN/PL. Nie nadawać języka z braku suffixu ani z celu `subs`. Dla nowej konfiguracji preferować pełną ścieżkę polską przed angielską, zachowując rozstrzygnięte ręczne priorytety; sprawdzić metadane default/forced/nazwy ścieżki i nie traktować samych polskich signs jako pełnych dialogów. Nierozstrzygnięty konflikt źródeł ma trafić do istniejącego wyboru Ręcznego, nie do nowego detektora.

**Próby rozstrzygające:** SRT pierwszy, MKV pierwszy, zmiana nazwy, dwa pliki napisów, częściowo skopiowany sidecar, TXT z wieloma akapitami, długi akapit, polskie UTF-8, ASS z tagami i rysunkiem. Dla translate-only spy na granicy TTS ma licznik zero. W root samotny SRT nie ma żadnego wywołania tłumaczenia ani syntezy.

**Regresje:** `tests/application/test_discovery.py`, `test_planner.py`, `test_planner_properties.py` i testy istniejących usług subtitles/translation. Nowe scenariusze w `test_workflows.py` są dodatkiem, nie zastąpieniem testów starego video.

### P11. Wykonać audiobook przez istniejące TTS i audio

**Rezultat:** TXT/SRT daje używalne audio, bez fikcyjnego MKV i bez drugiej implementacji TTS.

1. W `intents.py` zapisać cel i sposób timingów jako właściwość zlecenia/grupy. Nie dodawać trzech trybów RunMode.
2. Dodać w plannerze zależności tekst→ewentualne tłumaczenie→TTS→audio→publikacja. Przy „Nie tłumacz” nie może powstać task tłumaczenia. Nie trzeba zapisywać FULL_PL tylko po to, by oszukać typ wejścia.
3. Zbudować wspólną konwersję źródłowego tekstu/cues do SpeechRequest i timings w `TtsTaskHandler`. Walidować kolejność, pustą treść i dozwolony głos. Obsługa batch, cancellation, retry i klipów pozostaje wspólna.
4. W `AudioTaskHandler._mix` dopuścić brak SOURCE_AUDIO dla jawnego samodzielnego celu. Przekazać `None` do istniejącej usługi. Nie usuwać walidacji wymaganej dla miksu video.
5. Dla SRT ciągłego użyć source_order i zerowych początków okien; sprawdzić wynik rzeczywistych placements. Dla source timing zachować oryginalne czasy. Nie nadpisywać źródłowego SRT nowymi czasami.
6. Uwzględnić cel/timing w fingerprints i zapisanych intents. Cache lub wznowienie starej osi czasu nie może zwrócić innego wariantu jako poprawnego.
7. W Ręcznym pokazywać tylko legalne produkty dla TXT/SRT; nie oferować MKV bez wideo. Zachować jeden podgląd całego wybranego zakresu i możliwość regeneracji na miejscu.

**Dowód multimedialny:** kontrolowane klipy o znanych długościach, różne formaty/tempo, długa przerwa w źródłowym SRT i nakładające się kwestie. Ciągły wariant nie zawiera tej wielominutowej przerwy; wariant timing ją respektuje. Pełne dekodowanie wyniku zachowuje końcówkę i poprawny kodek. Usługi sieciowe zastąpione na granicy nie są dowodem jakości wybranego głosu.

**Warunek przejścia:** wyłączenie wzorca „wideo wymagane do każdego audio” nie osłabia walidacji zwykłego lektora do filmu. Przerwane TTS nadal można dokończyć bez powtarzania potwierdzonych klipów zgodnie z obecnym resume.

### P12. Dodać cover i trwały zestaw wynikowy

**Rezultat:** poprawny MP4 z obrazu i audio/tekstu trafia do ready; każda gotowa grupa pamięta swój cel.

1. Dodać source image do inspection i source fingerprint. Walidować PNG/JPG/JPEG przez Pillow, orientację i rzeczywiste wymiary; odrzucić uszkodzony plik bez uruchamiania TTS dla niekompletnego zestawu.
2. Planner cover najpierw wymaga kompletnego wejścia, następnie reużywa audiobook albo dostarczone audio. Przy audio wejściowym nie tworzyć syntezy ani nowego miksu z wyimaginowanym oryginałem.
3. Dodać mały kontrakt obrazu+audio w istniejącej composition. Zarejestrować go w obecnym składzie handlerów/bootstrap. Nie tworzyć oddzielnego workera ani nowej usługi montażu.
4. Zbudować komendę według D-018. Sprawdzić mapowanie, obraz o nieparzystych wymiarach, portret, alpha, nazwę z `%`, odstępy i polskie znaki. Przekazywać argv, nigdy shell string.
5. Dodać `ReadyGroup` i zasilanie go przy udanej publikacji grupy. `ReadyStore` rezerwuje docelowy rdzeń nazwy całego zestawu; nowe typy muszą być rozpoznawane także przez `_destinations`.
6. Wykluczyć ready ze startów Auto, ale zachować jego discovery dla Biblioteki i Ręcznego. Odtworzyć cel z metadanych grupy, a nie z folderu ready.
7. Regeneracja cover może reużyć gotowe audio; poprawka samego obrazu nie tłumaczy tekstu i nie syntetyzuje głosu. Gdy audio nie istnieje, podgląd pokazuje konieczną pracę.

**Próby:** tekst+obraz w obu kolejnościach, audio+obraz, dwa obrazy, obraz skopiowany częściowo, input audio+TXT konflikt, uszkodzone JPG, przerwane kodowanie, kolizja dwóch Book z różnych miejsc. Wariant audio+obraz ma zero TTS. Wszystkie gotowe rezultaty trafiają do tego samego ready bez mieszania grup.

**Gate obrazu:** rzeczywisty FFmpeg/FFprobe potwierdza końcówkę audio oraz zgodny MP4. Jeśli ograniczenie konkretnej dystrybucji FFmpeg obala komendę, poprawić tę gałąź, nie usuwać wymaganego produktu i nie dokładać niezamówionego renderera.

### P13. Zakres subskrypcji i postęp pobrania na poziomie materiału

**Rezultat:** można zamówić wybrane i przyszłe odcinki, nie odtwarzać usuniętych i obrabiać pierwszy plik paczki bez czekania na całą paczkę.

1. Rozszerzyć `subscriptions.py` schemat 3→4 o zakres/future_from i jawne ponowienie. Migracja starszych danych zachowuje istniejące numery, enabled, taken, terminy oraz COMPLETE; nie nadaje COMPLETE rekordowi ORDERED bez dowodu.
2. Dodać do ownera/`ResidentSession` polecenie zapisania całego zakresu jednym command_id. Podniesienie generacji odrzuca spóźniony check. Zapis jest przed odpowiedzią i przed add.
3. Rozdzielić zaznaczanie draftu od zapisanych faktów. Zwykłe zastosowanie zakresu nie resetuje completed. Jawne repeat identyfikuje numer i wcześniejszą operację oraz tworzy nowy zamiar bez wymazania starej tożsamości.
4. Zastąpić w checkach założenie „wszystko od next_episode” sprawdzeniem wybranego zbioru/future_from i pamięci pozyskania. Dokończenie TTS opierać na requests/produktach, nie nowym `download`. Wszystkie nowe add oraz jawne Ponów kierować do głównego workspace zgodnie z D-020; nie przekazywać katalogu utworzonego z tytułu ani przywróconego z dawnej subskrypcji. Przed startem zawartości rozstrzygać płaskie ścieżki paczki, rezerwacje i kolizje nazw.
5. Rozszerzyć `TransferInspector` i potwierdzenia o kompletność wybranych plików. Usunąć zależność gotowości pierwszego pliku od 100% całego torrenta. W cache ująć zmiany właściwe dla per-file readiness.
6. Dopisać powiązanie identyfikatora materiału/grupy z pozyskaniem. Przejście downloading→processing zmienia projekcję tego samego materiału, nie dodaje drugiej pozycji tylko według nazwy.
7. Dopiąć dwuetapową relokację z D-020: wynik do ready teraz, źródło po zwolnieniu. Nie potwierdzać globalnego COMPLETE, gdy dopiero pierwszy plik jest gotowy. Nie zatrzymywać pozostałych transferów.
8. Utrzymać dotychczasowe odczyty AniList/Nyaa, mapowanie sezonów, limity i obsługę 429. Żadnego nowego źródła katalogu i nowego fuzzy matchera dysku.

**Scenariusze zakresu:** tylko 3 i 8; od 7 w połowie sezonu; wszystkie znane + przyszłe; koniec sezonu; 7.5; odznaczenie 1–6; usunięcie gotowego pliku; wyłączenie podczas GET; jawne Ponów po miesiącu. Brak `watched` i „Mam lokalnie” jest sprawdzany także w strukturach payloadów.

**Próba płaskiego zapisu (AC-071–072):** pojedynczy odcinek, paczka z katalogiem nadrzędnym i zagnieżdżonymi ścieżkami, dwa tytuły z identycznymi nazwami plików oraz jednoczesne Anime/subskrypcja/Ponów. Odczytać rzeczywiste ścieżki w kliencie i na dysku; po pobraniu i restarcie nie może powstać katalog tytułu/sezonu/grupy/torrenta. Oba kolidujące zestawy zachowują poprawne bajty i przypisanie napisów. Transfer oczekujący na metadane nie może zapisywać niezastrzeżonych plików ani blokować niezależnego materiału w root.

**Gate paczki:** dwa małe syntetyczne pliki w kontrolowanym torrencie, pierwszy kompletny, drugi celowo zatrzymany. Pierwszy wynik musi dać się odtworzyć w ready, drugi nadal pobierać, oryginał nie może zostać zniszczony ani skopiowany jako obejście. Recheck pierwszego i restart ownera nie tworzą drugiego runu. Dopiero zwolnienie pozwala dokończyć relokację źródeł.

### P14. Stałe czuwanie, globalna pauza i pełne zakończenie

**Rezultat:** uruchomienie w tle wykonuje nowy przepływ bez klikania Auto; Zatrzymaj i Zakończ mają różne, przewidywalne skutki.

1. Rozszerzyć jedną zgodę na automatyzację na harmonogram, add, kolejne taski i transfery. Kontrola przy dopuszczeniu efektu musi być na ownerze również po zakończeniu wolnego I/O.
2. Zapisać zestaw transferów zatrzymanych globalną pauzą. Przy wznowieniu sprawdzić nadal aktywne zamówienie i nie naruszać ręcznie wstrzymanych/cancelled transferów.
3. Wykorzystać `GraphCoordinator` i istniejące bezpieczne granice. Dla requestu PAUSED chronić staging; dla ukończonego wyniku dokończyć walidowaną publikację. Nie używać pełnego shutdown tylko po to, by zasymulować pause i od razu restart.
4. Na startupie Praca uruchomić/uzgodnić prywatnego klienta. Jeżeli binarka nie istnieje, użyć obecnego instalatora i manifestu. Pusta subskrypcja nadal nie oznacza zgody na przypadkowe pobieranie.
5. Naprawić rozróżnienie własnego GUI i rzeczywistej utraty własności procesu. Zachować profile, porty i dowody tożsamości. Nie kasować zabezpieczeń dlatego, że użytkownik chce otworzyć qBittorrenta.
6. Dopiąć pełne shutdown: narzędzia, klient, owner, IPC, tray i klienci UI. Zamknięcie jednego panelu pozostaje odłączeniem. Wszelkie panele wychodzą tylko ze swojej aplikacji, nie zamykają hosta terminalowego.
7. Sprawdzić autostart na istniejącym zadaniu po logowaniu; nowa instalacja nie wymaga codziennego terminala. Zachować trwałą pauzę i disabled subscriptions.

**Macierz:** uruchomienie bez ownera, dwa równoczesne starty, trzeci panel, zamknięcie jednego, otwarcie z tray, pause w trakcie GET/add/TTS/relokacji, resume, exit z aktywnym prywatnym klientem, osobisty klient obok, restart po pause i po exit. Każda próba używa osobnego config/workspace, nie listy pobrań użytkownika.

**Dowód idle:** po ustabilizowaniu pracy i po pełnej pauzie obserwować liczniki HTTP/probe/pełnych skanów. Oddzielić żywy podgląd UI od zamkniętego panelu. Brak widocznego okna nie jest wystarczającym wynikiem pomiaru.

### P15. Biblioteka, szczegóły i bezpieczny Kosz

**Rezultat:** widać tylko ukończone materiały, Enter/F działają poprawnie, a usunięcie całego zestawu nie zostawia śmieci i nie powoduje pobrania od nowa.

1. W projekcji ownera zastąpić „każda wykryta grupa” filtrem gotowego zestawu i faktycznie dostępnego wyniku. Błąd regeneracji nie usuwa starego dobrego wpisu. Nieudane pierwsze wykonanie nie jest nowym gotowym wpisem.
2. Dodać publiczny odczyt plików zestawu na potrzeby szczegółów. Metadane mają pochodzić z inspection/inventory, nie z osobnego skanu przy każdym renderze.
3. Zmienić otwieranie Biblioteki: preferuj jawny główny produkt, nie listę fallbacków kończącą się źródłem bez lektora. Przy braku pliku pokaż krótką odmowę i odśwież dane.
4. Dodać podgląd usunięcia oraz wykonanie potwierdzonego zestawu. Fingerprint listy ma być sprawdzany także przy Start, aby zmiana pliku między dialogiem i wykonaniem nie usunęła innego obiektu.
5. Zaimplementować `platform/recycle.py` i użyć go wyłącznie przez ownera. Rejestrować wynik per plik i operację pending. Nie usuwać potwierdzenia pobrania po usunięciu mediów.
6. Podłączyć zmiany `ready` do broadcastu stanu. Usunięcie/przywrócenie w Explorerze aktualizuje listę. Usunięcie części źródeł nie udaje usunięcia całego zestawu; część pozostająca jest dostępna w szczegółach albo jako problem, nie nowy automatyczny run.

**Gate Kosza:** na izolowanych plikach Windows sprawdzić przeniesienie, przywrócenie, odmowę po blokadzie, częściowy błąd, niedostępny Kosz/nośnik, polskie znaki i długie nazwy. Nie testować trwałego usuwania jako planu B. Podobne nazwy `01`/`010` i plik zewnętrzny są obowiązkowymi negatywnymi przypadkami.

**Ochrona paczki:** próba usunięcia zestawu ze źródłem nadal należącym do aktywnego torrenta ma odmówić przed pierwszą zmianą. Po zwolnieniu źródła ta sama normalna operacja obejmuje komplet, bez oddzielnego ustawienia „tylko wyniki”.

### P16. Złożyć nową nawigację z istniejących kontrolerów

**Rezultat:** codzienna ścieżka działa bez Home→Auto, a wyszukiwarka i subskrypcje są połączone, nie tylko obok siebie.

1. W `app.py` usunąć Auto/Anime z menu Home, zachować Panel/Ręczny/Ustawienia/Wyjście i dotychczasowe logo/maskotkę. Usunąć wyłącznie martwe konsumenckie gałęzie; techniczne `run --preset` pozostaje zgodnym wejściem delegującym.
2. W `state.py` zmienić kolejność zakładek i domyślne otwarcie trzeciej. Zapisać lokalny kontekst powrotu: tab, wybrane ID i pozycja listy. Powrót z Ustawień nie tworzy nowego ekranu od zera.
3. Osadzić `AnimeController` jako widok Panelu. Jego tekstowe pola korzystają z istniejącego `TextInput`. Subskrybuj zwraca draft; Pobierz składa jednorazowy pełny zamiar i przenosi do Przetwarzania po przyjęciu.
4. W karcie subskrypcji umieścić listę numerów, kulki i jeden zapis zakresu. Wyszukiwanie wywołane przez Dodaj wraca do tej karty. Nie dodawać pola „obejrzane do”, listy lokalnych dopasowań i osobnego ekranu metadanych każdego odcinka.
5. Przetwarzanie pokazuje pobieranie i obróbkę z rzeczywistym pomiarem i istniejącymi kolorami pasków. Nazwa źródła pozostaje pełną nazwą, przycinaną dopiero według szerokości terminala. Korekta P18 sprawdza grupę → wybór jednego odcinka → Pobierz → transfer w Przetwarzaniu → obróbka → gotowy wynik w Bibliotece, bez duplikatów i wewnętrznych ID.
6. Dodać widoczne, kontekstowe Ponów/Anuluj dla wskazanego materiału. Jeśli backend nadal anuluje cały run, UI musi tak mówić; do anulowania pojedynczego odcinka rozdzielić requests na grupy na wejściu Auto, nie udawać funkcji w etykiecie. Ręczny wielogrupowy zachowuje jawny zakres podglądu.
7. Dodać Bibliotekę ze szczegółami, Enter/F/Delete i jednym potwierdzeniem. Nie dodawać kółek do codziennego odtwarzania; zaznaczanie zbiorcze może być istniejącą akcją wyboru, a nie stałym trackerem.
8. Wspólna stopka pokazuje liczniki i stan pracy; skróty odpowiadają zakładce. Ujednolicić mapowanie klawiszy w `prompts.py`, nie implementować drugiej mapy w każdym kontrolerze.

**Odbiór klawiatury:** Home Enter→Przetwarzanie; lewo→Subskrypcje; lewo→Anime; prawo z Przetwarzania→Biblioteka. Dodaj→wyszukaj→Subskrybuj→zakres→Enter→powrót do szukania kolejnej serii. Żaden z tych kroków nie wymaga przepisywania tytułu.

**Rozmiary do próby:** 120×40, 80×24, bardzo niskie okno. Nie dodawać nowej maskotki zastępczej. Jeśli tekst zakładek się nie mieści, zachować wybieralność i informację o aktywnej, a nie po cichu zgubić Bibliotekę. Potwierdzenie usunięcia i aktywny przycisk zawsze muszą być widoczne.

### P17. Recepty, historia, zegary i końcowe spięcie

**Rezultat:** wspólne ustawienia rzeczywiście działają raz, ekran nie jest przeładowany, a wymagane ślady pracy są dostępne bez osobnego modułu kolekcji.

1. W istniejącej kategorii Auto udostępnić trzy bazowe recepty. Wyświetlać dziedziczenie subs/cover jako krótki opis roli, nie kolejne kopie pól modelu i głosu. Root kategorii nie ma globalnego przycisku Start.
2. W `field_catalog` i `field_access` dodać tylko potrzebne pola celu/wyjścia/timingów. Zmiana recepty nie resetuje sekretów, grupy wydań ani aktywnych subskrypcji. Reset jest zakresowy i potwierdzany.
3. Po zmianie ustawienia preferencja materializuje się dopiero w nowym zleceniu. Ręczny override pozostaje lokalny. Test obejmuje równoczesne video/audiobook i zmianę głosu w połowie pierwszego runu.
4. Dodać dziennik D-027, widok Historia pod Przetwarzaniem i wyszukiwanie zachowanych wpisów. Ponów korzysta z właściwej istniejącej drogi: resume, rebuild lub ponowne pozyskanie, nie jednej funkcji „usuń wszystko i zrób od nowa”.
5. Dodać sekundowe odliczanie na widocznej liście/karcie. Zegar używa snapshotu, nie HTTP. Brak daty, miniona emisja i aktualizacja terminu mają własne krótkie etykiety.
   Przed spięciem zegara domknąć zależności harmonogramu ujawnione w [raporcie przepływu](acquisition-flow-report.md): świeżo zatwierdzone zaległe odcinki otrzymują rzeczywistą możliwość pozyskania zamiast natychmiastowego wygaśnięcia historycznego okna; wyłączony ogon nie dopisuje zamówień; brak daty ma ograniczoną ścieżkę odświeżenia bez wymyślania emisji. Dowód obejmuje produkcyjne `check_due` dla jednej karty: `1` odznaczony, `2–7` dostępne i wybrane, `8–12` przyszłe i wybrane, restart oraz jawne Ponów. Zachować granice sezonu, numery ułamkowe i trwałe budżety prób. Sam test zapisu zakresu nie zamyka tej integracji.
6. Completed results notify once; clicking always opens Library and selects the exact current episode when the owner can validate its stable set ID. Unknown native identity opens Library without guessing a target; expired identity adds a concise notice. Ordinary icon activation remains Home. A new panel subscribes before attach and receives one-shot pending navigation with target revalidation.
7. Usunąć pozostałe teksty/akcje obejrzenia, Mam lokalnie i osobne Pobrania z nowej ścieżki UI oraz aktualnych instrukcji. Nie dotykać materiałów historycznych w Git tylko dla kosmetyki.

**Gate powiadomień:** rzeczywisty Windows z dwoma gotowymi wynikami; kliknięcie każdego dostępnego komunikatu nie może wskazać przypadkowego „ostatniego” pliku. Jeśli obecny balon tray nie pozwala uczciwie zachować kilku celów, serializować pokazywanie i wiązać cel z aktywnym balonem; nie udawać obsługi historycznych toastów. Zablokowane powiadomienia nie wpływają na sukces zadania.

### P18. Próby całego przepływu i kontrolowane przełączenie

**Rezultat:** stary interfejs nie pozostał obok nowego, a program spełnia scenariusze użytkownika na rzeczywistych granicach.

**Status odbioru: PARTIAL.** Sprawdzone: pojedynczy wybór w grupie, jawne pobranie, przejście do Przetwarzania, rzeczywisty pasek pobierania zgodny z TTS i przejście do ekstrakcji, blokada zwykłego ponownego zamówienia, usunięcie niepewnych pozycji z bieżącej listy. Fokus Enter/Esc i blokowy kursor zaakceptowane przez użytkownika. Testy API/IPC obejmują rzeczywistą ścieżkę kontrolera z zastąpioną granicą HTTP, nie stanowią pełnego odbioru dostawcy na żywo.

Najbliższa kolejność po zapisie sprawdzonego stanu w tematycznych commitach:

1. Independent spoken/displayed branches are committed in `fac2a65`. Complete R-045: confirmed absence of displayed cues is a successful omission, including composition and recovery; real failures remain partial/failed.
2. Durable terminal-failure admission is committed in `ac62c17`. Explicit retry, changed sources, unresolved remote-operation protection, and successful groups in a failed batch retain their separate contracts.
3. Hidden background tool launches are committed in `c4a0fab`. Ascending episode order and preserved subscription scope are committed in `e758e3a`; constrained absence, one-second panel transfer observations, numeric progress and notification-to-Library navigation are committed in `8d40761`. Integrated evidence: 5052 passed, 18 skipped, root Ruff/format and mypy Windows/Linux passed, Opus reviews followed by a fresh Astra pre-commit review.
4. Library opening is committed in `c307ca3`: Enter opens the recorded video through the OS association while sidecars stay separate; F reveals the confirmed product. Final gates passed with 5070 tests passed and 18 skipped, followed by Opus verification and a fresh Astra pre-commit review. The resident was restarted into this revision. A real keyboard smoke on Youjo Senki II episode 11 opened its exact MKV in the associated mpv and selected its EAC3 in Explorer with F. See the live checkpoint in `acquisition-flow-report.md`. Audiovisual quality, transfer freshness and native notification clicks still require their live acceptance; P18 remains PARTIAL.
5. After the functional path is accepted, reflect on interaction cost and agree the next bounded plan. Broad correctness auditing, redundant-test consolidation, search-quality work and refactoring for replaceable components remain later work.

#### Library actions and Undo — accepted corrective iteration

Baseline `c307ca3`. The user accepted the complete correction after the real Library check exposed false `library_source_held` refusal. Implement R-046/R-047 together with the existing whole-set recycle contract.

1. Prove the native round-trip first on one synthetic file. The existing worker must yield an exact receipt and preserved file identity; restore must resolve that exact Recycle Bin entry, preserve bin bookkeeping and publish without replacing an occupied destination. A native primitive failure stops Undo implementation until diagnosed.
2. Distinguish retained acquisition history from ownership using the existing manager's `released` evidence. A pure read must not invoke profile initialization, network, ACL changes or torrent release. Keep it off the owner thread and revalidate acquisition state at mutation boundaries. Matching active, uncertain or unproven acquisitions still block; retain every dedup record.
3. Add owner-validated exact-file opening for Details Enter/F, with current membership and identity checks. Keep list Enter/F semantics. Display whole-set Delete scope in both views. Preserve action refusals through unrelated snapshots, scoped to the affected selection/view.
4. Extend existing per-deletion durable evidence with optional restore fields rather than another store. Use append order to choose the last deletion with effects; successful Undo consumes that target without exposing an earlier deletion. Ctrl+Z uses the existing key binding. Preserve original deletion receipts and products, record admission before effects, reserve affected paths, and make retries/restart reconcile exact evidence rather than repeat uncertain moves. Occupied targets and missing bin items produce visible partial/refused outcomes.
5. Integrate focused regressions for released ownership, details, refusal visibility, last-target semantics, restart, partial effects, collisions and idempotence. Opus reviews; Astra fixes; parent runs root gates and a fresh Astra reviews before a requested local commit. Then parent performs controlled real whole-set deletion, resident restart and Undo, verifies restored bytes and Library availability, and demonstrates collision preservation. User accepts the interaction.

Expected changes are limited to acquisition/manager evidence, the existing Library/automation/control/persistence boundaries, recycle worker, CLI session/state and their tests. Reuse existing `PendingDeletion`, native worker, owner I/O pool and workspace staging. No extra dependency, player integration, unrelated refactor, global Shell undo or guessed restoration by filename. Optional nested persistence follows the existing schema-2 compatibility pattern; a new schema requires a demonstrated reason.

Native pilot passed on 2026-09-18: the existing recycler returned an exact filesystem receipt with unchanged size/mtime/device/inode. Parsing that receipt inside the virtual Recycle Bin resolved the correct Shell item. `IFileOperation.MoveItem` to unique same-volume staging removed both the physical receipt and the exact namespace entry; final non-replacing Windows rename restored the original identity and SHA-256. An initial pilot-only COM binding error was corrected against the installed SDK before any restore effect (`BHID_SFObject` is `3981e224`, not the UI handler `3981e225`). Evidence: temporary `library_recycle_pilot.py`, `library_restore_pilot.py` and `restore-state-e23f94072d354752b2c094dd61b5e5a7.json`. This proves the primitive, not the integrated Ctrl+Z lifecycle or collision handling.

Integration checkpoint, 2026-09-18: committed as `d2c779d` after Opus and fresh Astra PASS; commit hooks passed. Root Ruff/format and mypy Windows/Linux passed; `library-undo-integrated.xml` records 5104 passed, 18 skipped, zero failures/errors (the real private-client integration case explicitly deselected). Native whole-set recycling, reconstructed-owner Undo, exact identity/bytes, Library availability, collision preservation and explicit retry passed. The first integrated native attempt exposed a missing UTF-16 terminator in handle-based publication; the buffer was corrected and real Windows regression tests added. The exact synthetic source from that failed attempt was recovered and its original ledger successfully reconciled before repeating the complete smoke. The live resident and panel now load this revision. Actual keyboard Delete, Cancel and Ctrl+Z after a confirmed owner-process exit/restart passed on a separate synthetic set, with both original file identities and hashes restored. A repeated Ctrl+Z refused the consumed target. Live Youjo Delete opened the four-file whole-set confirmation and Enter on its default Cancel left media intact. Detailed evidence is in `acquisition-flow-report.md`. User interaction acceptance and the wider P18 scenarios remain pending.

Library UX correction, 2026-09-18: the user revoked the confirmation entirely. The current follow-up removes its state/rendering/handlers, submits Delete directly and retains Ctrl+Z. Library suppresses routine success/busy/progress prose and operation rows; materials use plain names, partial leftovers remain accessible and completed deletions disappear. Superseded cosmetic confirmation tests were removed; existing action tests cover direct dispatch and Undo. All 1007 CLI tests and root Ruff/format/mypy pass; Opus verified the final fixes. Actual keyboard Delete recycled the existing two-file synthetic set without another key or confirmation, and Library became empty without operation/status messages. Windows Terminal exited before Ctrl+Z could be sent; exact recovery was completed through the same public Undo API, with both original identities and hashes preserved. The synthetic owner was shut down. This follow-up remains uncommitted; a newly launched panel loads the simplified UI.

#### R-045 implementation checkpoint

- Add a constrained `ABSENT` artifact state and absent output IDs in `TaskResult`; only non-source displayed subtitles may use this state, without a runtime file.
- Keep one source of omission proof in the existing run journal. Preserve old result decoding defaults; do not add a second omission ledger or change WatchState merely to duplicate journal facts.
- Propagate confirmed absence through subtitle conversion and publication; container composition skips only that displayed input. Required audio, spoken text, full subtitles and source media remain strict.
- Saved joint splits follow the same approved absence semantics when explicitly executed; update their regression expectation rather than maintaining two runtime meanings of an empty displayed stream.
- Completed real products retain normal ready relocation and Library validation. A displayed-only no-op has no fake Library result. Verify that unchanged omissions do not start again after restart, including held-source and relocation boundaries.
- Required evidence: actual planner/handlers/scheduler publication, MKV mux and MP4 burn omission, strict failure cases, journal round-trip/restart, owner admission and Library. Follow with a controlled live run reusing confirmed Polish subtitles without retranslating.

Wykonać następujące ciągi od wejścia do końcowego pliku, nie tylko unit testy kontrolera:

1. Zwykłe MKV z EN i MKV z osadzonymi PL. Pierwsze tłumaczy, drugie wykorzystuje zadeklarowane PL. Każdy kończy się otwieralnym rezultatem.
2. `subs`: napisy przed filmem i film przed napisami z długą przerwą. Nie powstaje audiobook ani tłumaczenie z niewłaściwego źródła.
3. TXT→TXT, SRT→SRT, TXT/SRT→audio, gotowe audio+obraz→MP4. Tylko wymagane usługi są wywoływane.
4. Subskrypcja od połowy sezonu i przyszły numer pojawiający się w katalogu. Wcześniejsze odznaczone numery pozostają nietknięte.
5. Mała paczka z pierwszym odcinkiem gotowym przed drugim. Gotowy wynik jest odtwarzalny, a torrent nadal legalnie posiada potrzebny oryginał.
6. Jeden sukces i jeden błąd. Sukces w Bibliotece, błąd w Historii pod Przetwarzaniem; główna lista pokazuje pozostałe bieżące pobieranie, przygotowanie i obróbkę, a ponowienie błędu nie powtarza sukcesu. Pasek rzeczywistego pobrania ma ten sam pełny układ co TTS i ekstrakcja, zgodnie z R-043.
7. Regeneracja innym głosem, awaria publikacji i restart. Stary wynik pozostaje; potwierdzone niezależne etapy nie są powtarzane.
8. Usunięcie całego zestawu do Kosza, restart oraz rotacja historii. Odcinek nie pobiera się ponownie. Jawne Ponów działa.
9. Dwa panele, zamknięcie jednego, praca w tle, pauza, wznowienie i pełne zakończenie. Zero podwójnych ownerów i niezmieniony osobisty qBittorrent.
10. Ręczne usunięcie pliku w Explorerze przy otwartej Bibliotece oraz przywrócenie z Kosza. Widok się aktualizuje bez Auto.

Do automatycznych prób używać syntetycznych mediów i zastępować wyłącznie granice usług zdalnych. Osobny, świadomie uruchomiony smoke rzeczywistego dostawcy sprawdza brakujący kontrakt usługowy; nie wykonuje sezonu użytkownika jako „testu”.

Przed produkcyjnym przełączeniem zatrzymać poprzedniego ownera, zrobić kopie danych konfiguracyjnych i migracyjny preflight. Sprawdzić istniejące katalogi o zarezerwowanych nazwach. Zachować wyłączone subskrypcje, wstrzymane transfery, media i gotowe rezultaty. Dla zastanych katalogów tytułów zachować historyczne ścieżki do uzgodnienia; nowe zamówienia od razu używają root. Zmianę lokalizacji istniejących plików wykonywać po bezpiecznym zatrzymaniu ich zapisu: transfery przez klienta z potwierdzeniem mapowania, pliki zwolnione przez istniejącą kontrolowaną relokację. Sprawdzić kolizje przed przeniesieniem, nie pobierać danych ponownie, nie odtwarzać pustych katalogów tytułów. Nie uruchamiać starego i nowego schematu jednocześnie na tych samych plikach.

Zaktualizować README, `config/README`, aktywne scoped AGENTS i opis uruchomienia do faktycznej nowej ścieżki. Usunąć martwe menu i konsumentów starej projekcji Pobrań, lecz zostawić techniczne kontrakty używane przez tests/CLI, jeżeli nadal pełnią funkcję. Nie usuwać starego kodu zdalnej automatyzacji na innych gałęziach w ramach tej zmiany.

Właściciel sprawdza wygląd i klawiaturę na swoim terminalu po zakończeniu integracji. Brak takiej próby zapisuje się jako brak odbioru wizualnego, nie jako akceptację. Nie czekamy natomiast z testem harmonogramu na rzeczywisty kolejny sezon: replay kalendarza i kontrolowany zegar mogą sprawdzić go już podczas implementacji.

## 7. Schematy, IPC i zgodność

### Migracje wymagane przez ten plan

| Zapis | Baseline | Kierunek |
|---|---:|---|
| `config/watch/state.json` | Schemat 1 | Schemat 2: recepty, gotowe zestawy, pause-owned transfers, pending delete i kompletność plików |
| `config/subscriptions.json` | Schemat 3 | Schemat 4: wybierany zakres/future_from, jawne repeat bez resetu starych faktów |
| Journal runów | Obecne typy planu/intents | Wersjonować tylko rozszerzony kontrakt; stary legalny run nadal ma jawny cel albo bezpieczną odmowę wznowienia |
| `config/settings.json` | Obecne preferencje i profile | Bez kopii per folder; zmieniać schemat tylko jeśli rzeczywiście dochodzi pole globalne |
| `config/presets.json` | Obecny format AutoPreset | Zachować stare presety wideo; nowe cele materializować bez dopisywania im nieznanych pól |
| `history.jsonl` | Brak | Nowy nieautorytatywny dziennik, retencja 30 dni |

`watch_state.py` i `subscriptions.py` mają ścisłe listy kluczy. Sama nowa dataclass nie wystarcza: poszerzyć encode/decode, walidację, defaulty, round-trip i migracje. W `CommandReceipt.pending` jest zamknięta lista operacji; nowe mutacje zakresu/pauzy/Kosza muszą być świadomie dodane wraz z replay, a nie wysłane pod nieobsługiwanym stringiem.

Undo retains optional nested `PendingDeletion.restore` in schema 2, emitted only after admission. Older builds with the pre-Undo strict allowlist cannot load the resulting state. This accepted compatibility limitation requires coordinated state/media recovery for downgrade, never dropping restore fields or reverting the ledger independently of native effects.

Nie zapisywać sekretów w snapshots i historii. Per-file paths pozostają względne i walidowane. Nie używać payloadu z panela jako pozwolenia na dowolne skasowanie absolutnej ścieżki.

### Minimalne nowe polecenia fasady

Nazwy poniżej są planowane; nie mają być wprowadzane jako luźny dispatcher metod. Każde ma walidowany payload i test błędnego zakresu.

| Operacja | Właściciel semantyki | Idempotencja / ograniczenie |
|---|---|---|
| Pobranie recept / aktualizacja jednej recepty | Owner + istniejący katalog ustawień | Zmiana tylko wskazanej recepty; bez duplikatu globalnych preferencji |
| Podgląd/wykonanie zakresu dla różnych celów | Obecny preview/start | Ten sam preview ID, source fingerprints i reservation |
| Zastosowanie zakresu subskrypcji | SubscriptionService przez ownera | Jeden command ID i generacja wpisu przed efektem |
| Jawne repeat numerów | Owner + pozyskanie/wykonanie | Nowy zamiar, nie wymazanie wcześniejszego completed |
| Pauza / wznowienie | Owner | Powtórzenie nie zmienia listy ręcznie wstrzymanych |
| Szczegóły gotowego zestawu | Owner | Odczyt bez mutacji i sieci |
| Preview delete / wykonanie delete | Owner + adapter Kosza | Potwierdzony zakres i fingerprint, wynik per plik |
| Historia: strona / wyszukanie | Owner | Ograniczony odczyt; nie dekoduje mediów |

UI nie serializuje `ExecutionPlan`. Tak jak obecnie wysyła zamiar i odbiera `PlanPreview`; source/recipe decisions wykonuje owner. Po reconnect stare lokalne preview/draft dostają właściwą walidację instancji.

## 8. Weryfikacja i pokrycie kontraktu

Każda faza ma własne próby. Poniższe mapowanie jest końcową kontrolą, czy zachowanie ma właściciela; nie zastępuje konkretnych scenariuszy w fazach.

| Wymagania SPEC | Design / fazy | Główny dowód |
|---|---|---|
| R-001, R-004, R-017, R-020, R-028 | D-017–019; P10–12, P17–18 | Grafy potrzebnych etapów, kompatybilny Manual, force/resume i marker ręcznej decyzji |
| R-002, R-003, R-005, R-018, R-021, R-024, R-025 | D-022–023; P14, P18 | Wieloprocesowe IPC, pause/drain/restart, autostart, pomiary idle |
| R-006, R-007, R-012, R-013, R-014, R-027 | D-021, D-024; P13, P16 | Zakres z dziurami, future_from, brak watched/local flags, generation i history dedup |
| R-008, R-009, R-010, R-011 | D-028; P13, P17 | Fake clock, replay AniList/Nyaa, liczniki rzeczywistego HTTP |
| R-015, R-030, R-031 | D-020, D-023; P13–14, P18 | Rzeczywisty prywatny klient, pojedynczy plik paczki, ochrona osobistej instancji |
| R-016, R-032, R-033, R-034, R-038 | D-015–020; P09–10, P13, P18 | Routing, komplet par, płaskie pobrania i kolizje (AC-071–072), standalone bez primary video |
| R-035, R-036, R-037 | D-017–018; P11–12, P17 | Audio bez oryginału, ciągłe/source timing, TXT i realny cover MP4 |
| R-019, R-029, R-039, R-040, R-042 | D-019–020, D-025–026; P12–15 | Publikacja/ready, widoczność błędów, prawdziwy Kosz i zewnętrzne zmiany dysku |
| R-022, R-023, R-043, R-044 | D-024, D-028; P16–18 | Keyboard walk, realny terminal, stopka, powiadomienia i krótki widok |
| R-026, R-041 | D-019, D-021, D-027; P09, P13, P17–18 | Migracje, rotacja dziennika bez resetu dedup i trwałego stanu |
| I-001–005 | Wszystkie zmiany wspólnych granic | Brak podwójnego wykonania, nieaktualnego Start, niebezpiecznego delete i renderer-side effects |

AC-001–045 są regresyjną bazą po jawnych zmianach znaczenia w SPEC. Nowe próby AC-046–072 pokrywają zadania i UI tej wersji. Nie przepisujemy każdego AC w każdym teście; test może potwierdzać kilka powiązanych warunków jednym realistycznym scenariuszem.

### Testy automatyczne

Rozszerzyć istniejące pliki `test_discovery`, `test_planner`, `test_service`, `test_automation`, `test_control`, `test_ready`, `test_subscriptions`, `test_transfers`, `test_watch_state` oraz odpowiadające testy CLI. Dodać `test_workflows`, `test_history` i `test_recycle` dla nowych odpowiedzialności. Testy nowych wariantów mediów trzymać przy aktualnych testach domen, nie tworzyć jednego wielkiego mockowanego „test_all”.

Próba source-specific musi użyć rzeczywistego discovery/inspection/plannera i publikacji. Mockowanie `planner.plan_auto` tak, żeby od razu zwrócił oczekiwany graf, nie dowodzi poprawności folderów. W testach sieciowych mockować dostawcę/HTTP, nie decyzję scope/owner.

Przy każdej krytycznej naprawie najpierw odtworzyć stary błąd: SRT jako orphan, TXT odrzucone dla audio, czekanie na całe amount_left torrenta, gotowy oryginał pokazywany zamiast wynikowego filmu, wznowienie nieodpowiedniego transferu. Test ma padać przed potrzebną zmianą.

### Kontrole repo

Przed commitem kodu zgodnie z aktualnym AGENTS, z root, nie z podkatalogu:

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest -n 19 --tb=short -q --deselect "tests/platform/test_qbittorrent_process.py::test_private_clients_download_concurrently_reconnect_and_stop_independently"
git diff --check
```

Pełny pytest ma używać skonfigurowanego `testpaths`, w tym testów utilities; samo `pytest tests/` nie jest pełnym przebiegiem. Większe zestawy uruchamiać z `-n 19` zgodnie z aktualną decyzją użytkownika. Wskazany test rzeczywistych klientów torrent pozostaje wyłączony z automatycznych przebiegów; testy korzystają z odseparowanych `ANISHIFT_CONFIG_DIR` i `ANISHIFT_WORKSPACE_ROOT`. Nie wolno zwiększać timeoutów tylko po to, by ukryć regresję. Jeśli aktualne AGENTS/CI wymaga jeszcze innego targetu platformy, zachować go.

Test Windows oznaczony SKIP na Linuxie nie daje PASS dla Kosza, tray, autostartu i prywatnego klienta. Odbiór UI jest rzeczywistą interakcją w terminalu użytkownika, nie liczbą testów tekstowych.

## 9. Ryzyka, reakcje i granice replanowania

| Ryzyko | Jak je rozpoznać | Reakcja |
|---|---|---|
| Folder tylko zmienia etykietę, a stary planner dalej wymaga MKV | Standalone test kończy się video_missing/txt_products_unsupported | Naprawić wspólny wybór celu, nie wytwarzać fikcyjnego kontenera |
| Po relokacji cel grupy jest zapomniany | Audiobook w ready próbuje regenerować wideo | Dokończyć trwałą proweniencję i migrację przed włączeniem regen |
| SRT/obraz przychodzą w innym czasie | Dwa wyniki z niekompletnego zestawu | Sprawdzić stały kontrakt miejsca i qualification przed plannerem; nie wydłużać losowego timera |
| Historia 30 dni staje się pamięcią dedup | Usunięty odcinek wraca po rotacji | Przenieść decyzję do trwałych confirmations/orders i dopisać test restart+retencja |
| Nowy preset kopiuje wszystkie ustawienia | Zmiana głosu wymaga kilku ekranów | Zostawić globalne profile, materializować tylko delty celu |
| Gotowy plik paczki jest ruszany przez torrent | Brakujące dane, recheck albo ponowne pobieranie po relokacji | Publikować wynik niezależnie, źródło przenosić dopiero po zwolnieniu |
| Kosz może stać się trwałym usunięciem | API nie gwarantuje recyklingu na badanym nośniku | Odmówić operacji i zatrzymać ten gate; żadnego fallbacku unlink |
| Globalna pauza nie blokuje spóźnionego add | Nowy torrent po potwierdzeniu Zatrzymaj | Generacja i admission na ownerze tuż przed efektem |
| Sekundowy licznik generuje HTTP | Licznik requestów rośnie co odrysowanie | Usunąć I/O z UI, odczytywać zapisany termin |
| Wiersz po odświeżeniu wskazuje inny odcinek | Delete działa na sąsiednim wpisie | Stabilne ID + fingerprint potwierdzenia, nie numer wiersza |
| Model zwraca niekompletny tekst | Brak akapitu albo naruszona kolejność | Istniejąca kontrola kompletności rozszerzona na tekst; nie publikować częściowego sukcesu |
| Zakończ zabija cudzy klient lub host terminala | Znika osobisty qBit/inna zakładka | Pozytywny dowód własności i zakończenie tylko własnej aplikacji |

Lokalna zmiana nazwy helpera lub przeniesienie kilku funkcji nie wymaga nowej specyfikacji. Zmiana znaczenia kulek, liczby celów, domyślnej automatyzacji, własności plików albo gwarancji Kosza wymaga jawnego powrotu do kontraktu. Nie zastępować niespełnionego wymagania mniej wygodnym zachowaniem bez zaznaczenia zmiany.

## 10. Gotowość do przekazania i zakończenie implementacji

Plan jest kompletny co do kierunku i kolejności. Pozostałe gates są próbami konkretnych granic: per-file qBittorrent + relokacja, recykling bez trwałego fallbacku, rzeczywisty MP4, obsługa powiadomień i akceptacja terminala. Ich niepowodzenie zatrzymuje odpowiedni fragment, nie uruchamia nowej architektury całego programu.

Implementacja jest gotowa dopiero, gdy:

- normalny plik i subskrypcja przechodzą do wyniku bez codziennego Start;
- wymagane pary działają w obu kolejnościach, a standalone TXT/SRT ma rzeczywiste produkty;
- cztery miejsca zadaniowe korzystają z jednego ready i wspólnych ustawień; pobrania lądują płasko w głównym workspace bez katalogów tytułów;
- nie wróciły tracker obejrzenia, lokalne dopasowywanie kolekcji i osobne Pobrania;
- usuwanie całego zestawu działa przez Kosz i nie resetuje pobrania;
- kolejne okna nie tworzą drugiego ownera, a pauza i zakończenie są sprawdzone;
- wymagana weryfikacja i migracja mają rzeczywiste wyniki, a brak ręcznego odbioru jest jawny;
- dokumentacja opisuje to, co rzeczywiście działa, bez twierdzenia o odbiorze na podstawie samego commitu.

Wykonawca nie odtwarza wcześniejszego atlasu ani nie implementuje odrzuconych ekranów tylko dlatego, że w historycznym dokumencie miały identyfikator.

## 11. Źródła techniczne i granice odczytu

### Kod odczytanego commitu

Wszystkie poniższe odnośniki są przypięte do baseline, nie do ruchomego main:

- [Instrukcje aplikacji](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/AGENTS.md): właściciel, publikacja, granice i trwałość.
- [Discovery](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/discovery.py), [inspection](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/inspection.py), [products](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/products.py): primary, formaty, nazwy i obecne wymaganie wideo przy audio.
- [Planner](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/planner.py#L94-L345): wspólne `_plan`, ograniczenie TXT i wybór produktów.
- [Translation handler](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/translation_handler.py), [TTS handler](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/tts_handler.py), [audio handler](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/audio_handler.py), [composition handler](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/composition_handler.py): konkretne granice rozszerzenia.
- [Audio types](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/services/audio/types.py), [audio service](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/services/audio/service.py), [subtitles AGENTS](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/services/subtitles/AGENTS.md): narrator-only już istnieje, a TXT→SRT ma roboczy timing.
- [Control](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/control.py), [subscriptions](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/subscriptions.py), [transfers](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/transfers.py), [ready](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/ready.py): faktyczny zapis i ograniczenia obecnego przejścia plików.
- [Settings](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/cli/interactive/settings.py), [field catalog](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/config/field_catalog.py), [state](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/cli/interactive/state.py), [app](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/cli/interactive/app.py): istniejące ekrany i edytory do ponownego użycia.
- [pyproject](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/pyproject.toml): Python 3.14+, istniejące Pillow/pysubs2/Prompt Toolkit/Rich i pełne testpaths.

### Sprawdzone dokumentacje granic

- [Microsoft: SetOperationFlags](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-ifileoperation-setoperationflags): `FOFX_RECYCLEONDELETE`, wczesne zakończenie po błędzie i niebezpieczeństwo automatycznych potwierdzeń. Projekt adaptera wymaga rzeczywistej próby recyklingu.
- [Microsoft: GetAnyOperationsAborted](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-ifileoperation-getanyoperationsaborted): także poprawny HRESULT nie wyklucza przerwania operacji.
- [FFmpeg: image2](https://ffmpeg.org/ffmpeg-formats.html#image2): pojedynczy obraz, `loop`, `framerate` i wyłączenie interpretacji wzorca nazwy.
- [FFmpeg: opcje wyjścia](https://ffmpeg.org/ffmpeg.html): jawne mapowanie strumieni i zakończenie według krótszego wyjścia, używane tylko przy zapętlonym statycznym obrazie.

Dokumentacje potwierdzają dostępność mechanizmów, nie wykonany test na komputerze użytkownika. Plan nie zawiera deklaracji sprawdzenia niezapisanych danych, jakości długiego audiobooka na żywym providerze ani realnej premiery następnego sezonu.

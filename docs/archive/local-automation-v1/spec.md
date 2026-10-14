---
kind: specification
status: proposed
updated: 2026-09-05
baseline: bc74425b487fb9110da76911c26dca4194b2aad9
implementation: not-executed
language: pl
---

# AniShift | specyfikacja pełnej automatyzacji lokalnej

## Cel

Wskazuję anime, wybieram wydanie lub zapisuję subskrypcję. Program lokalnie pobiera, przygotowuje polskie napisy i lektora oraz udostępnia każdy gotowy odcinek bez czekania na resztę. Własny plik wrzucony do inbox przechodzi tę samą drogę bez otwierania Auto.

To specyfikacja zamawianego rezultatu. Rozwiązania techniczne i kolejność znajdują się w [masterplanie](masterplan.md); wyniki badania i ograniczenia dowodu w [researchu](research.md).

## Podstawa i rozdzielenie ustaleń

Źródłem wymagań jest aktualna wypowiedź właściciela. Załączony wcześniejszy brief proponował jeden pionowy wycinek oraz przyszły VPS, lecz aktualne zlecenie rozszerza cały zakres lokalny i wyklucza VPS. Nie trzeba wracać do właściciela po potwierdzenie, że chce także wyszukiwanie i subskrypcje.

Stan kodu opisują przypięte źródła S01–S14 i S43. Dotychczasowe Auto jest podstawą rozwoju, a nie brakującą funkcją do napisania od nowa. Wcześniejsze liczby PASS opisują wcześniejszy audyt; nie dowodzą wdrożenia tej automatyzacji.

**Wymagania właściciela:** lokalność, wygodne wyszukiwanie/wybór, download, automatyczne czuwanie, 1080p+, grupy, angielski tekst, polski lektor, foldery i gotowość pojedynczego odcinka.

**Decyzje projektowe tego pakietu:** konkretny klient qBittorrent, SQLite, katalog AniList, granice rootów, konfigurowalna równoległość transferów i wykonań rdzenia, wartości domyślne, sposób autostartu i opcjonalny import MAL XML. Są rozstrzygnięte do implementacji, ale nie udają uprzednio wyrażonego wyboru właściciela.

**Preferencje wymagające konfiguracji:** rzeczywista ścieżka biblioteki, konkretne ulubione grupy, profil produktu/głosu, odtwarzacz, zgoda na autostart i autolaunch klienta. Nie zgadujemy dwóch grup, o których właściciel wspomniał bez nazw.

## Przepływy użytkownika

### A. Jeden odcinek

Użytkownik otwiera Anime, wpisuje tytuł, wybiera właściwy sezon i pasujące wydanie. Podsumowanie pokazuje grupę, klasę jakości, numer i pliki. Po zatwierdzeniu nie trzeba otwierać strony z torrentami, dodawać pliku ręcznie do AniShift ani ponownie uruchamiać Auto. Gotowy produkt pojawia się w Bibliotece z akcją Oglądaj.

### B. Cały sezon albo kilka epizodów

Użytkownik zaznacza odcinki lub pliki paczki klawiaturą. Program pobiera zgodnie z zaakceptowanym manifestem. Pierwszy kompletny plik może być przetwarzany i oglądany, gdy pozostałe jeszcze się pobierają. Jeden plik obejmujący dwa odcinki jest pokazany jako wspólny fizyczny materiał, nie jako dwa niezależne pliki.

### C. Seria wychodząca

Użytkownik wybiera Obserwuj, określa następny epizod do zdobycia i regułę grupy/jakości. Harmonogram pamięta serię, sprawdza dostępność i obsługuje luki. Data emisji pomaga dobrać termin sprawdzenia, ale nie stanowi sygnału pobrania nieistniejącego wydania.

### D. Kolekcja na później

Tytuł zakończony lub odkładany może mieć niższy priorytet oraz limit przygotowanych nieobejrzanych epizodów. Świadomy tryb zbierania sezonu dopuszcza większy zakres. Sam wpis Plan to Watch z eksportu MAL nie uruchamia pobierania całej listy.

### E. Własny plik

Użytkownik wrzuca MKV/MP4 i opcjonalne SRT/ASS do inbox. Worker czuwa po zalogowaniu i przyjmuje tylko plik dopuszczony przez politykę gotowości producenta. Gotowy polski tekst pomija tłumaczenie. Nierozpoznana nazwa może być przetworzona do _unsorted bez czekania na katalog online.

### F. Powrót po wyłączeniu komputera

Po zalogowaniu worker uzgadnia klienta, kopie i produkty oraz w kontrolowany sposób nadrabia nowe wydania. Nie odtwarza wszystkich pominiętych timerów. Zachowane dobre produkty nie są ponownie tłumaczone tylko dlatego, że zamknięto terminal.

## Wymagania adresowalne

<a id="r01"></a>

### R01. Zakres lokalny

Cały codzienny przepływ działa na komputerze Windows użytkownika; bez VPS, chmury, kontenera i własnego serwera HTTP.

**Odbiór:** Wylogowanie/zalogowanie uruchamia lokalne czuwanie po jego włączeniu; odłączenie chmury/VPS nie blokuje żadnej funkcji lokalnej.

**Realizacja:** [T001](masterplan.md#t001), [T006](masterplan.md#t006), [T098](masterplan.md#t098), [T105](masterplan.md#t105), [T122](masterplan.md#t122), [T124](masterplan.md#t124), [T125](masterplan.md#t125), [T127](masterplan.md#t127), [T128](masterplan.md#t128).

<a id="r02"></a>

### R02. Istniejący produkt

Auto, ręczny tryb, tłumaczenie i TTS korzystają z obecnego AppService i GraphScheduler; nie budujemy drugiego silnika.

**Odbiór:** Syntetyczny plik daje przez mostek ten sam rodzaj produktów i uczciwe wyniki częściowe co obecna fasada; nie istnieje konkurencyjny pipeline.

**Realizacja:** [T001](masterplan.md#t001), [T002](masterplan.md#t002), [T005](masterplan.md#t005), [T008](masterplan.md#t008), [T015](masterplan.md#t015), [T020](masterplan.md#t020), [T033](masterplan.md#t033), [T035](masterplan.md#t035), [T036](masterplan.md#t036), [T039](masterplan.md#t039), [T040](masterplan.md#t040), [T089](masterplan.md#t089), [T096](masterplan.md#t096), [T121](masterplan.md#t121), [T127](masterplan.md#t127).

<a id="r03"></a>

### R03. Tytuły i aliasy

Wyszukiwanie rozpoznaje tytuł angielski, romaji, oryginalny, zapisane aliasy i literówki; pokazuje sezon, rok oraz format.

**Odbiór:** Zestaw English/romaji/native, aliasu, literówki i podobnych tytułów pokazuje trafne sugestie z widocznym formatem oraz sezonem.

**Realizacja:** [T004](masterplan.md#t004), [T042](masterplan.md#t042), [T043](masterplan.md#t043), [T044](masterplan.md#t044), [T047](masterplan.md#t047), [T048](masterplan.md#t048), [T050](masterplan.md#t050), [T054](masterplan.md#t054), [T090](masterplan.md#t090), [T107](masterplan.md#t107), [T108](masterplan.md#t108), [T113](masterplan.md#t113).

<a id="r04"></a>

### R04. Jawna tożsamość

Automatyczne pobieranie wymaga potwierdzonej serii i reguły numeracji; fuzzy score nie może sam utożsamiać sezonów.

**Odbiór:** Podobny tytuł z drugiego sezonu nie zostaje automatycznie pobrany; potwierdzona numeracja jest używana w single oraz batch.

**Realizacja:** [T009](masterplan.md#t009), [T043](masterplan.md#t043), [T044](masterplan.md#t044), [T045](masterplan.md#t045), [T047](masterplan.md#t047), [T049](masterplan.md#t049), [T050](masterplan.md#t050), [T056](masterplan.md#t056), [T066](masterplan.md#t066), [T067](masterplan.md#t067), [T073](masterplan.md#t073), [T087](masterplan.md#t087), [T090](masterplan.md#t090), [T108](masterplan.md#t108), [T113](masterplan.md#t113).

<a id="r05"></a>

### R05. Jakość

Zwykła lista wydań wyklucza materiały poniżej klasy 1080p; nieznana jakość wymaga sprawdzenia, a nie zgadywania.

**Odbiór:** 720p znika ze zwykłej listy; nieznana klasa nie udaje 1080; plik błędnie oznaczony 1080p jest odrzucony po probe.

**Realizacja:** [T011](masterplan.md#t011), [T031](masterplan.md#t031), [T051](masterplan.md#t051), [T056](masterplan.md#t056), [T091](masterplan.md#t091), [T113](masterplan.md#t113).

<a id="r06"></a>

### R06. Grupy wydań

Preferencje obejmują grupę i opcjonalnie konto uploadera jako różne pola, kolejność fallbacków oraz tryb ścisły.

**Odbiór:** Ścisła grupa nie przełącza się samoczynnie; fallback działa w zapisanej kolejności; uploader nie jest utożsamiany z grupą.

**Realizacja:** [T011](masterplan.md#t011), [T049](masterplan.md#t049), [T050](masterplan.md#t050), [T052](masterplan.md#t052), [T055](masterplan.md#t055), [T056](masterplan.md#t056), [T071](masterplan.md#t071), [T073](masterplan.md#t073), [T091](masterplan.md#t091), [T092](masterplan.md#t092), [T112](masterplan.md#t112), [T113](masterplan.md#t113).

<a id="r07"></a>

### R07. Tekst do lektora

Automatyzacja wymaga pełnych polskich lub angielskich napisów tekstowych; same znaki/piosenki, bitmapy i hardsub nie udają dialogów.

**Odbiór:** PL nie wywołuje translatora; EN przechodzi obecny translator; signs-only/bitmap/hardsub zatrzymuje się przed lektorem.

**Realizacja:** [T005](masterplan.md#t005), [T015](masterplan.md#t015), [T029](masterplan.md#t029), [T031](masterplan.md#t031), [T034](masterplan.md#t034), [T035](masterplan.md#t035), [T036](masterplan.md#t036), [T052](masterplan.md#t052), [T095](masterplan.md#t095), [T113](masterplan.md#t113), [T115](masterplan.md#t115), [T123](masterplan.md#t123).

<a id="r08"></a>

### R08. Pobieranie na żądanie

Użytkownik wybiera pojedynczy odcinek, wiele odcinków albo paczkę i po potwierdzeniu program sam pobiera oraz przetwarza.

**Odbiór:** Po jednym podsumowaniu wybrane pliki trafiają do klienta oraz obróbki bez ręcznego przenoszenia i ponownego Enter w Auto.

**Realizacja:** [T003](masterplan.md#t003), [T019](masterplan.md#t019), [T025](masterplan.md#t025), [T030](masterplan.md#t030), [T047](masterplan.md#t047), [T049](masterplan.md#t049), [T051](masterplan.md#t051), [T053](masterplan.md#t053), [T054](masterplan.md#t054), [T055](masterplan.md#t055), [T056](masterplan.md#t056), [T057](masterplan.md#t057), [T058](masterplan.md#t058), [T060](masterplan.md#t060), [T062](masterplan.md#t062), [T063](masterplan.md#t063), [T065](masterplan.md#t065), [T068](masterplan.md#t068), [T069](masterplan.md#t069), [T070](masterplan.md#t070), [T091](masterplan.md#t091), [T100](masterplan.md#t100), [T105](masterplan.md#t105), [T113](masterplan.md#t113), [T114](masterplan.md#t114), [T123](masterplan.md#t123), [T124](masterplan.md#t124), [T127](masterplan.md#t127).

<a id="r09"></a>

### R09. Subskrypcje

Zapisana seria jest okresowo sprawdzana; znalezione pasujące odcinki przechodzą bez kolejnego ręcznego uruchomienia Auto.

**Odbiór:** Po pojawieniu się zgodnego wydania zapisanej serii worker sam przyjmuje odcinek; brak nowego wydania nie jest błędem.

**Realizacja:** [T011](masterplan.md#t011), [T019](masterplan.md#t019), [T021](masterplan.md#t021), [T046](masterplan.md#t046), [T052](masterplan.md#t052), [T053](masterplan.md#t053), [T056](masterplan.md#t056), [T066](masterplan.md#t066), [T073](masterplan.md#t073), [T074](masterplan.md#t074), [T075](masterplan.md#t075), [T076](masterplan.md#t076), [T077](masterplan.md#t077), [T078](masterplan.md#t078), [T079](masterplan.md#t079), [T080](masterplan.md#t080), [T084](masterplan.md#t084), [T092](masterplan.md#t092), [T108](masterplan.md#t108), [T112](masterplan.md#t112), [T116](masterplan.md#t116), [T124](masterplan.md#t124), [T125](masterplan.md#t125), [T127](masterplan.md#t127).

<a id="r10"></a>

### R10. Biblioteka na później

Zakończone serie i odkładane tytuły mogą pobierać się w tle z niższym priorytetem oraz ograniczeniem zapasu i dysku.

**Odbiór:** Bieżący ręczny wybór ma pierwszeństwo przed backlog; limit zapasu i budżet miejsca wstrzymują kolejne przyjęcia bez kasowania plików.

**Realizacja:** [T054](masterplan.md#t054), [T062](masterplan.md#t062), [T072](masterplan.md#t072), [T073](masterplan.md#t073), [T075](masterplan.md#t075), [T077](masterplan.md#t077), [T079](masterplan.md#t079), [T083](masterplan.md#t083), [T085](masterplan.md#t085), [T088](masterplan.md#t088), [T092](masterplan.md#t092), [T114](masterplan.md#t114), [T116](masterplan.md#t116).

<a id="r11"></a>

### R11. Gotowość odcinka

Każdy kompletny plik jest przetwarzany i publikowany samodzielnie, również wewnątrz niezakończonego batch torrenta.

**Odbiór:** Plik 1 gotowy przy pliku 2 niekompletnym staje się odtwarzalny; stan globalny torrenta może być nadal nieukończony.

**Realizacja:** [T003](masterplan.md#t003), [T005](masterplan.md#t005), [T010](masterplan.md#t010), [T031](masterplan.md#t031), [T033](masterplan.md#t033), [T035](masterplan.md#t035), [T036](masterplan.md#t036), [T037](masterplan.md#t037), [T040](masterplan.md#t040), [T060](masterplan.md#t060), [T061](masterplan.md#t061), [T062](masterplan.md#t062), [T065](masterplan.md#t065), [T068](masterplan.md#t068), [T070](masterplan.md#t070), [T072](masterplan.md#t072), [T081](masterplan.md#t081), [T082](masterplan.md#t082), [T084](masterplan.md#t084), [T093](masterplan.md#t093), [T094](masterplan.md#t094), [T113](masterplan.md#t113), [T114](masterplan.md#t114), [T123](masterplan.md#t123), [T124](masterplan.md#t124), [T127](masterplan.md#t127), [T128](masterplan.md#t128).

<a id="r12"></a>

### R12. Watch folder

Wrzucenie gotowego MKV/MP4 i ewentualnych sidecarów do inbox uruchamia pracę; częściowe pliki nie są uznawane za gotowe wyłącznie przez stały rozmiar.

**Odbiór:** Gotowy drop daje jeden job; powolny zapis, kopiowany sidecar i własne produkty nie powodują fałszywego przyjęcia lub pętli.

**Realizacja:** [T021](masterplan.md#t021), [T025](masterplan.md#t025), [T026](masterplan.md#t026), [T027](masterplan.md#t027), [T028](masterplan.md#t028), [T029](masterplan.md#t029), [T030](masterplan.md#t030), [T032](masterplan.md#t032), [T061](masterplan.md#t061), [T087](masterplan.md#t087), [T101](masterplan.md#t101), [T115](masterplan.md#t115), [T124](masterplan.md#t124), [T125](masterplan.md#t125), [T127](masterplan.md#t127).

<a id="r13"></a>

### R13. Autostart

Po jednorazowym włączeniu worker startuje przy logowaniu i działa bez otwartego TUI; nie obiecujemy pracy przy wyłączonym/uśpionym PC.

**Odbiór:** Rzeczywiste logowanie Windows uruchamia dokładnie jednego workera, z właściwym cwd i state_root; wyłączenie taska jest odwracalne.

**Realizacja:** [T011](masterplan.md#t011), [T021](masterplan.md#t021), [T028](masterplan.md#t028), [T076](masterplan.md#t076), [T097](masterplan.md#t097), [T098](masterplan.md#t098), [T099](masterplan.md#t099), [T100](masterplan.md#t100), [T101](masterplan.md#t101), [T102](masterplan.md#t102), [T103](masterplan.md#t103), [T104](masterplan.md#t104), [T105](masterplan.md#t105), [T109](masterplan.md#t109), [T112](masterplan.md#t112), [T115](masterplan.md#t115), [T122](masterplan.md#t122), [T124](masterplan.md#t124), [T125](masterplan.md#t125), [T127](masterplan.md#t127), [T128](masterplan.md#t128).

<a id="r14"></a>

### R14. Widoczny postęp

Jedno okno pokazuje prawdziwy etap i aktywność; zamknięcie monitora nie zatrzymuje workera, a 15 odcinków nie otwiera 15 terminali.

**Odbiór:** Piętnaście odcinków nie otwiera piętnastu konsol; zamknięcie monitora nie zatrzymuje przygotowania odcinka.

**Realizacja:** [T023](masterplan.md#t023), [T037](masterplan.md#t037), [T064](masterplan.md#t064), [T080](masterplan.md#t080), [T088](masterplan.md#t088), [T089](masterplan.md#t089), [T093](masterplan.md#t093), [T094](masterplan.md#t094), [T096](masterplan.md#t096), [T097](masterplan.md#t097), [T101](masterplan.md#t101), [T115](masterplan.md#t115), [T120](masterplan.md#t120), [T124](masterplan.md#t124).

<a id="r15"></a>

### R15. Porządek plików

Nowa biblioteka ma katalog serii, typu, odcinka i rewizji; oryginalny płaski workspace pozostaje bez migracji i bez rekurencyjnego skanowania.

**Odbiór:** Dwie serie z odcinkiem 01 mają rozłączne rewizje; legacy workspace i jego pliki pozostają w dotychczasowych miejscach.

**Realizacja:** [T006](masterplan.md#t006), [T009](masterplan.md#t009), [T012](masterplan.md#t012), [T013](masterplan.md#t013), [T033](masterplan.md#t033), [T081](masterplan.md#t081), [T086](masterplan.md#t086), [T087](masterplan.md#t087), [T088](masterplan.md#t088), [T093](masterplan.md#t093), [T104](masterplan.md#t104), [T114](masterplan.md#t114), [T124](masterplan.md#t124), [T127](masterplan.md#t127).

<a id="r16"></a>

### R16. Ochrona źródeł

Źródła torrentów i własne pliki użytkownika nie są przenoszone ani kasowane automatycznie; produkty powstają w kontrolowanej kopii.

**Odbiór:** Test sum kontrolnych potwierdza brak modyfikacji źródeł i obcych torrentów po sukcesie, błędzie, cancel i sprzątaniu.

**Realizacja:** [T003](masterplan.md#t003), [T012](masterplan.md#t012), [T013](masterplan.md#t013), [T014](masterplan.md#t014), [T022](masterplan.md#t022), [T025](masterplan.md#t025), [T026](masterplan.md#t026), [T027](masterplan.md#t027), [T029](masterplan.md#t029), [T032](masterplan.md#t032), [T038](masterplan.md#t038), [T058](masterplan.md#t058), [T059](masterplan.md#t059), [T061](masterplan.md#t061), [T063](masterplan.md#t063), [T071](masterplan.md#t071), [T079](masterplan.md#t079), [T082](masterplan.md#t082), [T085](masterplan.md#t085), [T086](masterplan.md#t086), [T103](masterplan.md#t103), [T115](masterplan.md#t115), [T117](masterplan.md#t117), [T119](masterplan.md#t119), [T126](masterplan.md#t126).

<a id="r17"></a>

### R17. Restart i idempotencja

Ponowne zdarzenia, restart, timeout dodania torrenta i zanik sieci nie tworzą dubli; stan i zaakceptowane produkty są uzgadniane.

**Odbiór:** Restart w oknie add/copy/publish nie dubluje transferu lub joba, nie gubi gotowego produktu i nie przyjmuje spóźnionego callbacka.

**Realizacja:** [T010](masterplan.md#t010), [T014](masterplan.md#t014), [T015](masterplan.md#t015), [T017](masterplan.md#t017), [T018](masterplan.md#t018), [T019](masterplan.md#t019), [T020](masterplan.md#t020), [T021](masterplan.md#t021), [T022](masterplan.md#t022), [T024](masterplan.md#t024), [T026](masterplan.md#t026), [T028](masterplan.md#t028), [T029](masterplan.md#t029), [T030](masterplan.md#t030), [T032](masterplan.md#t032), [T033](masterplan.md#t033), [T038](masterplan.md#t038), [T039](masterplan.md#t039), [T040](masterplan.md#t040), [T058](masterplan.md#t058), [T059](masterplan.md#t059), [T061](masterplan.md#t061), [T063](masterplan.md#t063), [T070](masterplan.md#t070), [T071](masterplan.md#t071), [T076](masterplan.md#t076), [T086](masterplan.md#t086), [T094](masterplan.md#t094), [T097](masterplan.md#t097), [T102](masterplan.md#t102), [T103](masterplan.md#t103), [T116](masterplan.md#t116), [T117](masterplan.md#t117), [T119](masterplan.md#t119), [T126](masterplan.md#t126).

<a id="r18"></a>

### R18. Harmonogram

Daty emisji są wskazówką do sprawdzania, nie dowodem opublikowania wydania; braki kalendarza nie zatrzymują subskrypcji.

**Odbiór:** Zmiana daty, brak emisji i tydzień offline dają ograniczony catch-up; nie generują lawiny requestów ani fałszywej dostępności.

**Realizacja:** [T004](masterplan.md#t004), [T041](masterplan.md#t041), [T042](masterplan.md#t042), [T043](masterplan.md#t043), [T046](masterplan.md#t046), [T073](masterplan.md#t073), [T074](masterplan.md#t074), [T076](masterplan.md#t076), [T078](masterplan.md#t078), [T080](masterplan.md#t080), [T092](masterplan.md#t092), [T102](masterplan.md#t102), [T116](masterplan.md#t116), [T118](masterplan.md#t118), [T123](masterplan.md#t123).

<a id="r19"></a>

### R19. Odcinki dodatkowe

OVA, ONA, specials, filmy, ułamkowe numery, wersje v2 i numeracja absolutna nie są po cichu gubione lub mylone z odcinkiem regularnym.

**Odbiór:** Przypadki 7.5, OVA, SP-A, v2, offset absolutny oraz wspólny plik 1–2 mają poprawne i widoczne mapowanie.

**Realizacja:** [T007](masterplan.md#t007), [T009](masterplan.md#t009), [T034](masterplan.md#t034), [T044](masterplan.md#t044), [T045](masterplan.md#t045), [T046](masterplan.md#t046), [T049](masterplan.md#t049), [T050](masterplan.md#t050), [T056](masterplan.md#t056), [T060](masterplan.md#t060), [T065](masterplan.md#t065), [T066](masterplan.md#t066), [T067](masterplan.md#t067), [T068](masterplan.md#t068), [T069](masterplan.md#t069), [T071](masterplan.md#t071), [T072](masterplan.md#t072), [T075](masterplan.md#t075), [T083](masterplan.md#t083), [T084](masterplan.md#t084), [T087](masterplan.md#t087), [T091](masterplan.md#t091), [T095](masterplan.md#t095), [T114](masterplan.md#t114).

<a id="r20"></a>

### R20. Jedna historia

Import, watcher, ręczny wybór i subskrypcje prowadzą do tej samej trwałej kolejki i biblioteki, z oddzielnym stanem transferu.

**Odbiór:** Ten sam materiał z inbox i klienta trafia do jednej historii z zachowaniem pochodzenia; transfer i obróbka są nadal rozróżnione.

**Realizacja:** [T008](masterplan.md#t008), [T009](masterplan.md#t009), [T010](masterplan.md#t010), [T017](masterplan.md#t017), [T018](masterplan.md#t018), [T019](masterplan.md#t019), [T022](masterplan.md#t022), [T023](masterplan.md#t023), [T025](masterplan.md#t025), [T028](masterplan.md#t028), [T030](masterplan.md#t030), [T037](masterplan.md#t037), [T038](masterplan.md#t038), [T058](masterplan.md#t058), [T059](masterplan.md#t059), [T081](masterplan.md#t081), [T117](masterplan.md#t117).

<a id="r21"></a>

### R21. Obejrzane

Pobrane, przetworzone, uruchomione w mpv i obejrzane to odrębne fakty; postęp oglądania zmienia jawna akcja użytkownika.

**Odbiór:** Pobranie, ready i zakończenie mpv nie zmieniają watched; jawna akcja oraz jej cofnięcie działają na EpisodeKey.

**Realizacja:** [T010](masterplan.md#t010), [T017](masterplan.md#t017), [T036](masterplan.md#t036), [T067](masterplan.md#t067), [T068](masterplan.md#t068), [T071](masterplan.md#t071), [T072](masterplan.md#t072), [T075](masterplan.md#t075), [T077](masterplan.md#t077), [T080](masterplan.md#t080), [T081](masterplan.md#t081), [T082](masterplan.md#t082), [T083](masterplan.md#t083), [T084](masterplan.md#t084), [T086](masterplan.md#t086), [T093](masterplan.md#t093), [T107](masterplan.md#t107), [T108](masterplan.md#t108), [T124](masterplan.md#t124).

<a id="r22"></a>

### R22. Lista MAL

Można bezpiecznie zaimportować własny eksport XML listy; żaden import nie subskrybuje automatycznie całego plan-to-watch ani nie nadpisuje MAL.

**Status zakresowy:** opcjonalne rozszerzenie powiązane z obecną listą właściciela; brak eksportu nie blokuje zasadniczej automatyzacji. Pełna synchronizacja sieciowa nie jest zadeklarowana jako dostarczona.

**Odbiór:** Import XML pokazuje snapshot i wybór pozycji; nie tworzy automatycznie subskrypcji wszystkich tytułów ani zapisu do MAL.

**Realizacja:** [T083](masterplan.md#t083), [T107](masterplan.md#t107), [T108](masterplan.md#t108), [T127](masterplan.md#t127).

<a id="r23"></a>

### R23. Odporność integracji

Timeouty, 429, 401, HTML zamiast RSS, zmiana schematu i częściowe odpowiedzi mają widoczny stan i ograniczone ponowienia.

**Odbiór:** 429, timeout, 401, challenge HTML, zły XML i zmiana JSON mają odrębne stany i kontrolowane ponowienia.

**Realizacja:** [T002](masterplan.md#t002), [T004](masterplan.md#t004), [T007](masterplan.md#t007), [T016](masterplan.md#t016), [T018](masterplan.md#t018), [T023](masterplan.md#t023), [T039](masterplan.md#t039), [T041](masterplan.md#t041), [T042](masterplan.md#t042), [T043](masterplan.md#t043), [T046](masterplan.md#t046), [T047](masterplan.md#t047), [T048](masterplan.md#t048), [T053](masterplan.md#t053), [T054](masterplan.md#t054), [T055](masterplan.md#t055), [T057](masterplan.md#t057), [T064](masterplan.md#t064), [T074](masterplan.md#t074), [T076](masterplan.md#t076), [T078](masterplan.md#t078), [T095](masterplan.md#t095), [T100](masterplan.md#t100), [T106](masterplan.md#t106), [T109](masterplan.md#t109), [T110](masterplan.md#t110), [T111](masterplan.md#t111), [T118](masterplan.md#t118), [T121](masterplan.md#t121), [T123](masterplan.md#t123), [T125](masterplan.md#t125), [T128](masterplan.md#t128).

<a id="r24"></a>

### R24. Zasoby

Program respektuje miejsce na dysku, współbieżność obecnego rdzenia, priorytety oglądania i limity dostawców; nie zakłada darmowości bez końca.

**Odbiór:** Brak miejsca blokuje nową pracę, a oglądanie gotowych działa; limity klienta/hosta nie są omijane przez ręczny check-now.

**Realizacja:** [T011](masterplan.md#t011), [T015](masterplan.md#t015), [T016](masterplan.md#t016), [T020](masterplan.md#t020), [T021](masterplan.md#t021), [T026](masterplan.md#t026), [T031](masterplan.md#t031), [T039](masterplan.md#t039), [T040](masterplan.md#t040), [T041](masterplan.md#t041), [T042](masterplan.md#t042), [T051](masterplan.md#t051), [T062](masterplan.md#t062), [T064](masterplan.md#t064), [T069](masterplan.md#t069), [T070](masterplan.md#t070), [T074](masterplan.md#t074), [T077](masterplan.md#t077), [T078](masterplan.md#t078), [T085](masterplan.md#t085), [T105](masterplan.md#t105), [T109](masterplan.md#t109), [T112](masterplan.md#t112), [T116](masterplan.md#t116), [T118](masterplan.md#t118), [T120](masterplan.md#t120), [T122](masterplan.md#t122).

<a id="r25"></a>

### R25. Proste TUI

Obsługa jest klawiaturowa i zgodna z istniejącym rendererem; strzałki nie uruchamiają pobierania, Enter zatwierdza kontekstową akcję.

**Odbiór:** Próby klawiszy, wklejania, resize i bardzo niskiego terminala nie uruchamiają ukrytych działań; Auto pozostaje domyślne.

**Realizacja:** [T008](masterplan.md#t008), [T019](masterplan.md#t019), [T023](masterplan.md#t023), [T032](masterplan.md#t032), [T044](masterplan.md#t044), [T048](masterplan.md#t048), [T079](masterplan.md#t079), [T088](masterplan.md#t088), [T089](masterplan.md#t089), [T090](masterplan.md#t090), [T091](masterplan.md#t091), [T092](masterplan.md#t092), [T093](masterplan.md#t093), [T094](masterplan.md#t094), [T095](masterplan.md#t095), [T096](masterplan.md#t096), [T101](masterplan.md#t101), [T112](masterplan.md#t112), [T120](masterplan.md#t120).

<a id="r26"></a>

### R26. Granice bezpieczeństwa

Brak dowolnej powłoki, automatycznie uruchamianych plików pobranych z sieci, logowania sekretów oraz sterowania cudzymi torrentami.

**Odbiór:** Złośliwa ścieżka, argument powłoki, token w URL i obcy hash nie pozwalają na zapis poza root, wykonanie kodu ani ujawnienie sekretu.

**Realizacja:** [T007](masterplan.md#t007), [T012](masterplan.md#t012), [T013](masterplan.md#t013), [T014](masterplan.md#t014), [T015](masterplan.md#t015), [T016](masterplan.md#t016), [T020](masterplan.md#t020), [T024](masterplan.md#t024), [T027](masterplan.md#t027), [T038](masterplan.md#t038), [T041](masterplan.md#t041), [T055](masterplan.md#t055), [T057](masterplan.md#t057), [T059](masterplan.md#t059), [T060](masterplan.md#t060), [T063](masterplan.md#t063), [T065](masterplan.md#t065), [T069](masterplan.md#t069), [T082](masterplan.md#t082), [T098](masterplan.md#t098), [T099](masterplan.md#t099), [T100](masterplan.md#t100), [T104](masterplan.md#t104), [T106](masterplan.md#t106), [T107](masterplan.md#t107), [T110](masterplan.md#t110), [T111](masterplan.md#t111), [T119](masterplan.md#t119), [T126](masterplan.md#t126).

<a id="r27"></a>

### R27. Weryfikowalność

Każde wymaganie ma zadania, konkretne testy i scenariusz odbioru; dokument nie przedstawia planowanych testów jako wykonanych.

**Odbiór:** Wszystkie R01–R30 mają kartę, przypadek i klasę dowodu; unverified pozostaje widoczne do rzeczywistego wykonania.

**Realizacja:** [T001](masterplan.md#t001), [T002](masterplan.md#t002), [T003](masterplan.md#t003), [T005](masterplan.md#t005), [T006](masterplan.md#t006), [T007](masterplan.md#t007), [T008](masterplan.md#t008), [T096](masterplan.md#t096), [T110](masterplan.md#t110), [T111](masterplan.md#t111), [T113](masterplan.md#t113), [T114](masterplan.md#t114), [T115](masterplan.md#t115), [T116](masterplan.md#t116), [T117](masterplan.md#t117), [T118](masterplan.md#t118), [T119](masterplan.md#t119), [T120](masterplan.md#t120), [T121](masterplan.md#t121), [T122](masterplan.md#t122), [T123](masterplan.md#t123), [T124](masterplan.md#t124), [T127](masterplan.md#t127), [T128](masterplan.md#t128).

<a id="r28"></a>

### R28. Wdrożenie i wyłączenie

Konfiguracja lokalna, aktualizacja, backup, zatrzymanie i wyłączenie autostartu są odwracalne i nie usuwają dobrej biblioteki.

**Odbiór:** Wyłączenie autostartu, stop, backup i przywrócenie zgodnego stanu nie usuwają biblioteki ani oryginałów klienta.

**Realizacja:** [T006](masterplan.md#t006), [T011](masterplan.md#t011), [T012](masterplan.md#t012), [T014](masterplan.md#t014), [T017](masterplan.md#t017), [T022](masterplan.md#t022), [T024](masterplan.md#t024), [T057](masterplan.md#t057), [T079](masterplan.md#t079), [T085](masterplan.md#t085), [T097](masterplan.md#t097), [T098](masterplan.md#t098), [T099](masterplan.md#t099), [T102](masterplan.md#t102), [T103](masterplan.md#t103), [T104](masterplan.md#t104), [T105](masterplan.md#t105), [T106](masterplan.md#t106), [T109](masterplan.md#t109), [T112](masterplan.md#t112), [T121](masterplan.md#t121), [T122](masterplan.md#t122), [T125](masterplan.md#t125), [T126](masterplan.md#t126), [T128](masterplan.md#t128).

<a id="r29"></a>

### R29. Wiele źródeł

Pierwszy indeks to Nyaa; drugi to jawnie skonfigurowany RSS. AnimeTosho pozostaje zbadanym kandydatem, nie fikcyjnie działającym adapterem.

**Odbiór:** Awaria Nyaa nie uruchamia przypadkowego mirrora; używany jest tylko wcześniej skonfigurowany drugi feed w zgodnej polityce.

**Realizacja:** [T004](masterplan.md#t004), [T041](masterplan.md#t041), [T047](masterplan.md#t047), [T049](masterplan.md#t049), [T053](masterplan.md#t053), [T054](masterplan.md#t054), [T055](masterplan.md#t055), [T111](masterplan.md#t111), [T118](masterplan.md#t118), [T127](masterplan.md#t127).

<a id="r30"></a>

### R30. Obsługa wyjątków

Niejasne dopasowanie, brak ścieżki napisów, źle opisane wydanie i konflikt wyboru trafiają do listy Wymaga uwagi z jedną konkretną akcją naprawczą.

**Odbiór:** Każdy stan attention ma konkretną przyczynę i jedną sensowną najbliższą akcję; naprawa jednego odcinka nie resetuje całej konfiguracji.

**Realizacja:** [T010](masterplan.md#t010), [T016](masterplan.md#t016), [T031](masterplan.md#t031), [T032](masterplan.md#t032), [T034](masterplan.md#t034), [T045](masterplan.md#t045), [T052](masterplan.md#t052), [T064](masterplan.md#t064), [T066](masterplan.md#t066), [T067](masterplan.md#t067), [T072](masterplan.md#t072), [T080](masterplan.md#t080), [T086](masterplan.md#t086), [T087](masterplan.md#t087), [T095](masterplan.md#t095), [T109](masterplan.md#t109), [T110](masterplan.md#t110).

## Inwarianty

Źródła pozostają zachowane. AniShift nie przenosi plików klienta torrent, nie wyłącza seedowania po każdym ukończonym odcinku i nie usuwa jedynej poprawnej kopii w celu odzyskania miejsca.

Pobranie, produkty gotowe, możliwość odtwarzania i obejrzane są różnymi faktami. Zakończenie procesu mpv nie stanowi dowodu obejrzenia.

Zmiana źródła, pełnego sidecara, wybranego tracka lub treściowego profilu daje odrębną rewizję. Poprzedni dobry wynik jest dostępny do czasu jawnego porządkowania.

Identyfikacja sezonu i epizodu nie opiera się wyłącznie na podobieństwie tytułów. Nieoznaczone dodatki trafiają do decyzji; znane OVA, 7.5 i specials nie znikają przez uproszczony licznik last_episode.

Worker może działać bez monitora. Zwykłe zamknięcie nowego monitora nie anuluje jego jobów. Dotychczasowe ręczne Auto zachowuje własną semantykę anulowania.

## Granice jakości i dowodu

Wymaganie 1080p+ dotyczy klasy wydania oraz kontroli pliku po pobraniu. Rozdzielczość nie dowodzi jakości kodowania. Crop panoramiczny wymaga jawnej reguły klasy, a nie dowolnego ignorowania wysokości. Materiał poniżej wymagań nie jest automatycznie upscalowany w celu obejścia filtra.

Napisy muszą nadawać się do lektora. Kontrola wyklucza oczywiste signs/songs-only, język niezgodny i bitmapy. Bez odsłuchu lub porównania treści nie gwarantuje semantycznej kompletności żadnej grupy. Profile sprawdzonych wydań umożliwiają działanie bez pytania co odcinek.

Dla obcego producenta folderu stały rozmiar przez chwilę nie dowodzi końca zapisu. Tryb silny wymaga umowy przekazania: rename lub marker gotowości. Tryb wygodnego dropu stosuje ostrożne best-effort i nie obiecuje wiedzy o przyszłym ponownym otwarciu pliku.

Brak sieci jednego indeksu nie zatrzymuje lokalnego lektora i Biblioteki. Zmienione API może wymagać poprawki konkretnego adaptera. Nie ma obietnicy bezawaryjności wszystkich usług zewnętrznych.

## Poza zakresem

VPS, Google Drive, cloud worker, zdalny dostęp do serwera, telefon jako klient serwera, nowy GUI/player, autonomiczny agent z powłoką, OCR/ASR hardsubów, automatyczny upscale, nowe silniki tłumaczenia/TTS i pełna synchronizacja kont MAL/AniList nie należą do tego wdrożenia.

Nie tworzymy uniwersalnego managera torrentów, dynamicznego marketplace pluginów, własnego brokera i drugiej historii obok bazy automatyzacji. Nie robimy ogólnego audytu i czyszczenia całego historycznego długu jako warunku rozpoczęcia nowej funkcji.

## Warunek końcowego odbioru

Trzy obowiązkowe próby użytkowe: wybór wydania, subskrypcja oraz drop własnego pliku. Dodatkowo próba paczki z jednym plikiem gotowym przed pozostałymi, restart oraz rzeczywiste logowanie Windows. Właściciel widzi poprawny porządek, może odtworzyć pierwszy wynik i potwierdza odsłuch lektora.

Testy deterministyczne, prawdziwe narzędzia medialne, żywe integracje i ocena człowieka mają oddzielne wyniki. Brak próby jest widoczny jako nieweryfikowany; nie jest ukrywany pod ogólnym statusem done.

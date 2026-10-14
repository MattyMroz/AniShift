# AniShift: foldery zadaniowe i bezobsługowy przepływ

Status: **READY do planowania i implementacji zachowania**
Data: 2026-09-13
Aktualizacja aktywnego workstreamu: `docs/work/local-automation/06-efficiency/spec.md`
Podstawa kodowa: `25121038fbf4ff1e1cecec3d4e644fdb235be679`, gałąź `work/local-automation/06-efficiency`
Plan wykonania: [plan.md](plan.md)

## 1. Cel i zakres tej wersji

Użytkownik odkłada materiał w miejscu odpowiadającym oczekiwanemu wynikowi albo zamawia odcinki przez Anime/Subskrypcje. AniShift sam czeka na potrzebny komplet, pobiera, przetwarza i udostępnia wynik w `ready`. Codzienna obsługa nie wymaga uruchamiania Auto, potwierdzania każdego pliku ani ponownego wybierania głosu i tłumacza.

The primary goal is minimal clicking and supervision, with extensive controls available on demand. Acceptance follows the user's complete journey from choosing an episode to watching it. First deliver that working path; a broader correctness audit, test consolidation and refactoring for replaceable components belong to a later iteration.

To specyfikacja zmiany istniejącego programu, nie opis tego, co już działa. Aktualny kod jest punktem integracji, a nie argumentem za zachowaniem odrzuconej nawigacji. Wcześniejsze trzy dokumenty UX są materiałem historycznym: nie obowiązują ich oznaczenia obejrzenia, „mam lokalnie”, osobna zakładka Pobrania ani dodatkowe wejście Anime w Home.

Obowiązuje ostatni feedback użytkownika: stałe czuwanie; folder określa zadanie; wspólne ustawienia; wyszukiwarka połączona z subskrypcjami; pobieranie jako etap przetwarzania; Biblioteka bez trackera oglądania; usuwanie całego zestawu do Kosza; jeden proces wykonujący pracę, wiele podłączonych interfejsów.

### W tej zmianie

- Zwykłe MKV/MP4 z lektorem oraz wideo wymagające osobnych napisów.
- Samodzielne tłumaczenie TXT/SRT/ASS/SSA; audiobook z TXT/SRT; MP4 z jednego obrazu i tekstu/SRT lub gotowego audio.
- Foldery, kompletność zestawu, jeden współdzielony zestaw preferencji, poprawki i regeneracja.
- Połączone Anime/Subskrypcje, zakres odcinków, trwała pamięć pobrań, odliczanie do emisji.
- Przetwarzanie pokazujące bieżącą obróbkę materiałów, Biblioteka gotowych wyników, szczegóły plików, Kosz i ograniczona historia operacji.
- Uruchamianie, pauza, wznowienie, zakończenie, autostart, wiele paneli oraz migracja istniejących danych.

### Świadomie poza tą zmianą

EPUB/PDF, OCR, rozpoznawanie mowy z filmu bez napisów, automatyczne typesetting i kolorowanie napisów, montaż wielu obrazów, generowanie okładek, publikowanie na YouTube, synchronizacja MAL/AniList, status obejrzenia, automatyczne szukanie odpowiedników lokalnej kolekcji, VPS i panel WWW. Możliwość późniejszego dodania EPUB nie uzasadnia teraz frameworka importerów.

Nie projektujemy ponownie wszystkich ustawień i wszystkich ekranów. Zachowujemy działające edytory; zmieniamy tylko zakresy i przejścia konieczne do opisanych zachowań. Odbiór wyglądu pozostaje próbą w terminalu, nie skutkiem samego statusu READY dokumentu.

## 2. Najmniejszy układ miejsc pracy

**R-032. Cztery nazwane foldery zadaniowe, zwykłe wideo w root, jeden wynikowy `ready`.**

```text
workspace/
├── Film.mkv                  pobrane lub dodane wideo: przetwarzanie automatyczne
├── subs/                     wideo + obowiązkowe napisy obok
├── translate/                sam tekst lub napisy → tłumaczenie
├── audiobook/                TXT lub SRT → głos, opcjonalnie tłumaczenie
├── cover/                    tekst/SRT/audio + obraz → MP4
├── ready/                    ukończone materiały i ich zachowane źródła
└── temp/                     istniejące dane tymczasowe programu
```

Nazwy są krótkie, angielskie i rozróżniają cel. `subs` nie oznacza „wszystkie napisy”: oznacza „film z moimi napisami”. `cover` nie oznacza samej okładki: oznacza film ze statycznym obrazem. Nie tworzymy dodatkowych `video`, `manual`, `input`, `output`, `pending` ani katalogów na każde rozszerzenie.

Są **cztery dodatkowe miejsca zadaniowe**; razem z `ready` i `temp` daje to sześć nazwanych podfolderów systemowych. **Wszystkie nowe i ponawiane pobrania trafiają bezpośrednio do głównego `workspace/`.** Dotyczy to wyszukiwarki, subskrypcji, pojedynczych odcinków i paczek. Nie tworzymy katalogów według tytułu, sezonu, grupy ani nazwy torrenta; nie dodajemy również `downloads/`. Nazwa serii jest metadanymi, nie nazwą tworzonego katalogu. Liczba folderów nie rośnie wraz z liczbą subskrypcji.

Układ zapisany wewnątrz paczki torrentowej również nie może tworzyć takich podfolderów. Przed rozpoczęciem zapisu zawartości trzeba zapewnić płaskie, niekolidujące ścieżki. Kolizja nie może nadpisać innego pliku ani połączyć napisów z niewłaściwym filmem; rozróżnienie dotyczy nazw całych zestawów, nie nowych katalogów. Starsze katalogi są wyłącznie danymi do bezpiecznej migracji (R-026), nie wzorcem dla kolejnych pobrań. Ręcznie utworzone zagnieżdżenie może zachować dziedziczenie roli, ale aplikacja nie wymaga go ani nie tworzy.

Foldery zadaniowe są tworzone przy uruchomieniu poprawnie skonfigurowanej instalacji. `temp` powstaje, gdy jest potrzebny. Istniejący plik, dowiązanie albo zajęta przez wcześniejsze media nazwa folderu nie jest nadpisywana ani po cichu reinterpretowana.

| Miejsce | Wymagany komplet | Domyślny rezultat | Czego samo nie uruchamia |
|---|---|---|---|
| `workspace/` bezpośrednio | Jedno kompletne wideo i użyteczne napisy osadzone lub obok | Film z lektorem oraz wybrane trwałe produkty | Audiobooka z samotnego SRT/TXT |
| `subs` | Wideo + jeden rozstrzygnięty SRT/ASS/SSA o tej samej nazwie bazowej | Ten sam wynik wideo, ale z obowiązkowymi napisami zewnętrznymi | Tłumaczenia z napisów osadzonych, zanim przyjdzie sidecar |
| `translate` | Jeden TXT/SRT/ASS/SSA | TXT→TXT, SRT→SRT, ASS/SSA→ASS, po polsku | TTS i filmu |
| `audiobook` | Jeden TXT lub SRT | Samodzielne audio; tłumaczenie według wspólnej polityki | Wideo, oczekiwania na MKV i czytania ASS z ozdobnikami |
| `cover` | Dokładnie jeden TXT, SRT lub plik audio + jeden PNG/JPG/JPEG o tej samej nazwie bazowej | MP4 ze statycznym obrazem i pełnym audio | Samego audio jako zakończonego zadania przed nadejściem obrazu |
| `ready` | Ukończony wynik | Otwieranie, szczegóły, jawna regeneracja, usuwanie | Nowej pracy od samego pojawienia się pliku |

Nazwy folderów i domyślne formaty powyżej są decyzjami tej specyfikacji w ramach przekazanego wyboru. Nie są przedstawiane jako wcześniejsze cytaty użytkownika.

## 3. Kompletność: miejsce określa zamiar, nie kolejność kopiowania

**R-016. Start wymaga kompletnego i dostępnego wejścia właściwego dla danego miejsca.** Ukończony zapis jednego pliku nie dowodzi ukończenia całego zestawu. Znany torrent wymaga potwierdzenia klienta. Własne kopiowanie korzysta z kontroli dostępności i stabilności, bez obietnicy odgadnięcia dowolnej przerwy w zewnętrznym programie.

**R-033. W `subs` para jest obowiązkowa, niezależnie od kolejności.** `Film.srt` przed `Film.mkv` czeka na film; `Film.mkv` przed napisami czeka na napisy. Nawet użyteczne napisy osadzone nie omijają tej reguły. Oba pliki muszą być kompletne. Kilka konkurujących sidecarów pozostawia krótkie „Wybierz napisy”, zamiast wybierać losowo.

**R-038. Zgodna nazwa sidecara daje pierwszeństwo źródła, nie dowód języka.** W zwykłym wejściu wideo `Film.ass`/`Film.srt`/`Film.ssa`, obecny przy przyjęciu zadania, ma pierwszeństwo przed ścieżką w kontenerze. Sufiks `.pl` nie jest wymagany od użytkownika. Konwencje `.pl`, `.spoken.pl` i `.displayed.pl` pozostają nazwami produktów AniShift, nie warunkiem rozpoznania oryginalnych polskich napisów.

Język wynika z jawnego wyboru, metadanych wybranej ścieżki lub pochodzenia potwierdzonego produktu. Dla źródła o nieznanym języku obowiązuje istniejąca polityka tłumaczenia z automatycznym rozpoznaniem po stronie wybranego tłumacza; nie dopisujemy własnego niezweryfikowanego detektora ani założenia „każdy sidecar jest polski”. Jawne „Nie tłumacz” pozwala użyć dostarczonego tekstu bez zmiany treści. Potwierdzone źródło polskie przy polityce Auto nie wymaga ponownego tłumaczenia. Domyślny wybór napisów osadzonych preferuje pełne polskie dialogi przed angielskimi; sama polska ścieżka oznaczona jako znaki/forced nie zastępuje pełnych dialogów. Jawnie wybrana przez użytkownika kolejność języków ma pierwszeństwo przed domyślną.

**R-034. Samodzielne napisy są rzeczywistym wejściem, ale tylko dla jawnego celu.** W `translate` i `audiobook` nie wymagają filmu. W root i `subs` samotny SRT/ASS/SSA nie staje się audiobookiem, nawet po długim oczekiwaniu. TXT w root jest widoczny dla Ręcznego, lecz nie rozpoczyna niezamówionego audiobooka. Plik w złym miejscu pozostaje nienaruszony z jedną wskazówką właściwego folderu.

**Późniejszy plik do już przyjętego zadania.** Przyjęty zestaw wejść jest ustalony. Zmiana wykorzystywanego pliku unieważnia nieaktualną publikację, ale nie rozpoczyna drugiego równoległego zlecenia. Dodatkowy sidecar po ukończeniu zwykłego wideo nie staje się samodzielnym audiobookiem i nie przebudowuje historii. Dokładne powiązanie z własnym wcześniejszym przeniesieniem może wskazać istniejący materiał do Ręcznego; nie szukamy po całym dysku podobnych tytułów. Wątpliwy przypadek pozostaje oczekujący.

To ograniczenie nie dotyczy zwykłego użycia `subs`: tam program od początku wie, że ma czekać na parę. Nie dodajemy globalnego „odczekaj kilka minut na wszystko”, plików `.done` ani obowiązkowego przycisku Start dla folderów automatycznych.

## 4. Produkty i wspólna konfiguracja

**R-001. Jeden rdzeń wykonania.** Pobrania dostarczają wejście, a wszystkie cele używają wspólnego planowania, tłumaczenia, syntezy, publikacji, limitów i odzyskiwania. Foldery nie tworzą oddzielnych silników ani instancji programu.

**R-035. Audiobook nie wymaga fikcyjnego filmu ani ścieżki oryginalnej.** TXT i SRT mogą być tłumaczone, czytane bez tłumaczenia albo tłumaczone i czytane. Domyślny audiobook czyta kolejno tekst, bez wielominutowych przerw z osi czasu SRT. Kolejne akapity rozdziela stała cisza 0,3 s, żeby czytanie ciągłe miało naturalny oddech; nie jest to pauza wyliczona z osi czasu źródła. W Ręcznym dostępne jest zachowanie czasów SRT dla głosu do istniejącego filmu, np. materiału z YouTube. Oryginalny SRT nie jest kasowany ani zmieniany przez skrócenie pauz w audiobooku.

TTS ma zachować kolejność treści i całą końcówkę nagrania. Pusty tekst lub same niewymawialne znaczniki nie tworzą pustego „gotowego audiobooka”. ASS/SSA można samodzielnie tłumaczyć, ale nie proponujemy dla nich domyślnego audiobooka; służą głównie wideo.

TXT→przetłumaczony TXT zachowuje akapity i kolejność treści. TXT→SRT pozostaje opcją Ręcznego albo ustawienia wyniku `translate`, bez dodatkowego folderu. Bez nagrania czasy są roboczym skryptem lektora, nie synchronizacją z filmem. Informacja o roboczych czasach jest przy wyborze tego wyniku i w szczegółach, nie w każdej liście. Nie wykonujemy TTS tylko po to, aby przetłumaczyć TXT.

**R-036. `cover` wymaga obrazu przed rozpoczęciem zadania.** Obsługuje `Book.txt + Book.png`, `Book.srt + Book.jpg` i `Book.mp3 + Book.png` oraz pozostałe już obsługiwane formaty audio. Tekst może przejść tłumaczenie i TTS. Dostarczone audio jest używane bez ponownej syntezy. Nie zmieniamy jego treści ani nie dokładamy drugiego głosu.

Powstaje jeden MP4 ze statycznym obrazem przez pełną długość audio. Obraz zachowuje proporcje, nie jest automatycznie kadrowany ani animowany. Nie ma generatora obrazów ani wysyłki do serwisu. Dwa konkurujące obrazy albo tekst i niezależne audio z tym samym rdzeniem nazwy wymagają wyboru, a nie heurystyki. Pliki wygenerowane wewnątrz trwającego zadania nie są drugim konkurującym wejściem.

**R-037. Ustawienia treści są wspólne, cele są lokalne.** Silnik tłumaczenia, wybrany model, głos, profil głosu i podstawowe parametry są ustawiane raz. Recepta folderu przechowuje cel, politykę tłumaczenia, wynik i konieczne ustawienie sposobu czytania SRT, a nie kopię całych Ustawień.

`subs` dziedziczy receptę wideo i zmienia tylko wymóg sidecara. `cover` dziedziczy sposób przygotowania audiobooka i dodaje obowiązkowy obraz oraz MP4. `translate` nie dziedziczy eksportu wideo. Indywidualny override jest możliwy w Ręcznym tylko dla wybranego zakresu. Nie budujemy dowolnie definiowanych folderów, kreatora reguł ani osobnego katalogu głosów na każdą receptę.

This installation intentionally keeps narration and subtitle products beside the original video. A merged MKV remains an explicit export option: normal playback and narration regeneration must not require rewriting the video. Preserve the chosen preset rather than enabling MKV automatically. The user already uses mpv through the Windows file association; this work does not install, configure or add a dedicated integration for the player. Standalone audio keeps the existing codec preference; cover MP4 retains its compatible container audio.

**R-017. Zmiana ustawień nie przerabia historii.** Nowe zlecenia korzystają z bieżących wspólnych preferencji, przyjęte z zachowanego zestawu. Zmiana folderu już przetworzonego materiału jest nowym jawnym celem, a nie powodem do ponownego odkrywania wszystkich niezmienionych odcinków.

**R-045. Confirmed absence of displayed subtitles is a valid outcome.** A successful parse and classification of the selected full subtitle document may establish that no displayed cues exist. In that case, omit the displayed subtitle file and its mux/burn input while completing the requested narration and video normally. Do not create an empty file, substitute the source video as a result, or reinterpret a parse, read, write, or missing-spoken-stream failure as absence. Preserve the original requested intent and the confirmed absence through recovery; an unchanged successful omission must not trigger another automatic run. A displayed-only request with no cues is an informative no-op, not an openable Library product. This behavior applies when executing both new and explicitly resumed saved plans; existing journals and receipts are not rewritten in advance.

## 5. Czuwanie, Ręczny i regeneracja

**R-003. Auto oznacza działającą automatyzację, nie codzienną akcję menu.** Normalnie program obserwuje wejścia cały czas. Nie ma obowiązkowego „Auto → Start” ani osobnego przełączania wideo, TXT i SRT przed każdym użyciem. Nowa instalacja ma czuwanie aktywne; migracja szanuje wcześniej jawnie wstrzymane operacje zgodnie z R-026.

**R-004. Ręczny pozostaje wyjątkiem i narzędziem poprawki.** Pokazuje istniejące materiały z wejść i `ready`, pozwala zaznaczyć zakres i dostępny dla niego wynik. Nie wymaga czterech różnych Manuali. Samodzielny TXT/SRT oczekujący w root może być świadomie wykonany tą drogą. Nie dodajemy osobnego folderu Manual.

Wybrane, jeszcze niewykonywane grupy są chronione podczas edycji. Jeżeli Auto zdążyło już przyjąć grupę, Ręczny pokazuje trwającą pracę; nie udaje, że można bez kosztu zmienić jej wcześniejsze wejście. Można zaczekać na wynik i go poprawić albo jawnie zatrzymać wskazane zlecenie. Nie blokuje to pozostałego czuwania.

**R-020. Regeneracja odtwarza tylko potrzebny zakres.** Inny głos oznacza TTS i zależne wyniki, nie powtórne poprawne tłumaczenie. Zmiana tłumaczenia obejmuje jego konsumentów. Nowy eksport z gotowego audio nie wywołuje TTS. Gdy potrzebny plik pośredni rzeczywiście nie istnieje, podgląd ujawnia konieczną dodatkową pracę. Stary poprawny rezultat pozostaje używalny do udanej podmiany.

**R-028. Automat nie cofa świadomej decyzji.** Zakończony Ręczny, anulowanie wybranego celu i błąd po wyczerpaniu prób nie powodują samoczynnego nowego zlecenia dla tej samej wersji wejścia. Odznaczenie produktu nie jest natychmiast odwracane przez receptę domyślną. Przywrócenie pracy jest jawnym ponowieniem, zmianą rzeczywistego wejścia albo nowym zamówieniem.

**R-018. Ręczna praca zachowuje pierwszeństwo bez zrywania trwających etapów.** Pierwszeństwo nie oznacza osobnej puli zasobów. Pobieranie nie zajmuje slotu tłumacza, a oczekiwanie na obraz czy napisy nie zajmuje slotu TTS.

## 6. Anime i subskrypcje jako jeden przepływ

**R-022. Home i Panel mają różne role.** Home zachowuje obecną maskotkę i duży napis ANISHIFT. Minimalne menu tej wersji: `Panel`, `Ręczny`, `Ustawienia`, `Wyjście`. Panel jest pierwszy. Usuwamy jednorazowe Auto i dodatkowe Anime z Home; niczego nie trzeba włączać, żeby nowe poprawne wejście zaczęło się obrabiać.

Kolejność zakładek Panelu:

```text
Anime     Subskrypcje     Przetwarzanie     Biblioteka
```

Pierwsze otwarcie Panelu wybiera **Przetwarzanie**, mimo że to trzecia zakładka. Powrót z Ustawień, szczegółów lub edycji przywraca miejsce, z którego użytkownik wyszedł. Nie wymaga ponownych dwóch naciśnięć strzałki. Pojawienie się nowego zadania w tle nie przełącza aktywnego ekranu.

Anime otwiera pole zapytania bez fokusu. Enter włącza edycję; podczas edycji ←/→ przesuwają kursor, a Enter wyszukuje. Esc kończy edycję i zachowuje tekst; poza edycją strzałki przełączają zakładki, a Esc wraca. Ctrl+C kopiuje zaznaczenie, a bez zaznaczenia działa jak Esc. Tab przełącza zakładki również podczas edycji; powrót zachowuje tekst i zaznaczenia, lecz wymaga ponownego Enter do edycji. Jawne otwarcie zakresu lub nazwy grupy od razu włącza edycję; pierwszy Esc odbiera fokus, kolejny zamyka pole. Samo przełączenie zakładki niczego nie zatwierdza.

Aktywne pole pokazuje blok podświetlający znak pod kursorem, a na końcu tekstu pustą komórkę. Kursor nie wstawia dodatkowego znaku między literami i nie przesuwa tekstu przy ruchu w obrębie widocznego fragmentu. Pole nieaktywne nie pokazuje kursora ani zaznaczenia. Działające skróty edycji pozostają obsługiwane przez wspólny edytor.

**R-006. Subskrypcja zamawia konkretny sezon, grupę i zakres.** Nie opisuje obejrzenia ani posiadanej kolekcji. Użytkownik zaznacza numery do pozyskania i może wyłączyć wcześniejsze odcinki bez uzasadniania, czy je widział lub ma na dysku. Zwykłe odcinki sezonu można zaznaczyć zbiorczo. Odcinek 7.5 zachowuje swój numer; OVA/specjale spoza wskazanego sezonu wymagają osobnego jawnego wyboru.

**R-027. Wyszukiwanie prowadzi bezpośrednio do zamówienia.** Anime udostępnia szukanie, wybór tytułu/sezonu i grupy. Zachowuje filtrowanie wydań do 1080p i wyżej; nie dodaje gorszej jakości tylko po to, by zapełnić listę. „Pobierz” jest jednorazowym zamówieniem pobrania oraz dalszego wykonania, bez zakładania subskrypcji. „Subskrybuj” przenosi do karty w Subskrypcjach z przygotowanym tytułem i grupą; użytkownik ustala zakres i dopiero go zatwierdza.

Grupa jest otwierana jak folder: Enter otwiera jej odcinki, a Enter na odcinku przełącza zaznaczenie. Pierwsze wejście ma wszystkie odcinki odznaczone. Widoczne akcje to Zaznacz wszystkie, Pobierz i Cofnij; Enter na Pobierz zatwierdza dokładnie zaznaczony zakres i przenosi do Przetwarzania. Podświetlenie nie jest zaznaczeniem. To samo wydanie już zamówione lub pobrane nie może zostać przypadkowo ponownie zaznaczone do zwykłego pobrania; odtworzenie wymaga jawnego Ponów. Wybór drugiej wersji tego samego numeru w jednej grupie nie dodaje niejawnie drugiej kopii odcinka.

Lokalne wejście do grupy, zaznaczanie i powrót reagują bez oczekiwania na sieć. Wyszukiwanie pokazuje użyteczny wynik możliwie wcześnie; uzupełnianie katalogu nie uzasadnia zbędnego blokowania listy. Responsywność i czas oczekiwania są sprawdzane w rzeczywistym panelu.

Dodaj w Subskrypcjach otwiera ten sam ekran Anime, z zachowaniem kontekstu powrotu. Anulowanie niczego nie dodaje. Powrót do Anime zachowuje ostatnie zapytanie i pozwala od razu szukać kolejnej serii. Nie tworzymy drugiej wyszukiwarki ani ścieżki przez Ustawienia.

Lista subskrypcji pokazuje nazwę, grupę, aktywność i najbliższy termin. Space przełącza aktywność wpisu; Enter otwiera prostą kartę odcinków. Karta ma zaznaczenia `●/○`, numery i krótki faktyczny stan. Nie ma osobnego ekranu dla każdego odcinka.

W karcie Space edytuje wybór; Enter stosuje wskazany zakres. To lokalny szkic do zatwierdzenia, ponieważ każde zamówienie może uruchomić pobieranie. Esc odrzuca niezatwierdzoną zmianę. Dla nieznanej jeszcze liczby odcinków pojedyncza pozycja „Kolejne odcinki” określa kontynuację; nie trzeba co tydzień zaznaczać nowego numeru. Zakończony sezon nie ma kontynuacji poza swoim zakresem.

Kulka oznacza zamówioną, jeszcze niedokończoną pracę, nigdy „obejrzane”. Ukończenie odcinka usuwa go z oczekującego zaznaczenia; zapisany fakt pobrania pozostaje. Przypadek „pobrano, ale TTS nie powiódł się” zachowuje żądanie dokończenia, ale nie powoduje nowego pobrania. Ponowienie ukończonego i usuniętego materiału wymaga ponownego wybrania numeru oraz jawnego „Ponów”; samo otwarcie karty i zaznacz wszystko nie kasują historii.

**R-007. Tylko fakty potrzebne do pracy.** Osobno istnieją zakres zamówienia, przyjęcie torrenta, potwierdzone pobranie i ukończenie produktów. Nie ma pól, filtrów ani akcji `watched`, `unwatched`, `Nieoznaczony`, „Mam lokalnie” ani „Wskaż lokalne”. Użytkownik prowadzi listę oglądania poza AniShift.

**R-014. Usunięcie pliku nie usuwa pamięci pobrania.** Automat nie odtwarza odcinka usuniętego ręcznie lub przez Bibliotekę. Ta pamięć nie wygasa po trzydziestu dniach i nie jest wnioskowana z obecnej zawartości `ready`. Dopiero jawne ponowienie tworzy nowe zamówienie. Niedokończone lub niepewne przyjęcie torrenta nie jest fałszywym „pobrano”.

Ręczne usunięcie torrenta w qBittorrencie nie kończy procesu AniShift ani niezależnych zleceń. Brak transferu zostaje widocznie rozpoznany; nie pozostaje fikcyjny aktywny pasek i nie następuje samoczynne ponowne dodanie torrenta. Zachowane kompletne źródło i zapisane wyniki nie tracą swoich potwierdzeń tylko z powodu usunięcia wpisu klienta.

**R-013. Wyłączenie i usunięcie subskrypcji nie kasuje mediów.** Zatrzymuje przyszłe zamawianie z tego wpisu. Wcześniej przyjęta praca może się dokończyć wraz z obróbką. Zatrzymanie całej automatyzacji służy do wstrzymania również tej pracy. Spóźniona odpowiedź wyszukiwania nie reaktywuje wyłączonego wpisu.

**R-012. Można zapisać nadchodzący sezon przed pierwszym torrentem.** Brak wydania nie blokuje zapisu rozstrzygniętego sezonu i grupy. Nie wymyślamy daty ani torrentu. Po zakończeniu sezonu nie ma nieskończonego odpytywania; brakujące numery są widoczne. Nie następuje automatyczne zamówienie następnego sezonu franczyzy.

## 7. Czas i pobieranie

**R-008. Odliczanie jest wyświetlane co do sekundy.** Widoczna lista/karta subskrypcji pokazuje np. `02d 04:18:09` do następnej znanej emisji. Zmiana daty aktualizuje licznik. Po emisji, przed wydaniem, widnieje krótkie „Czeka na wydanie”. Bez daty: „Brak terminu”. Nie pokazujemy ujemnego licznika ani obietnicy gotowego lektora o czasie emisji.

W szczegółach subskrypcji można rozróżnić emisję i następne sprawdzenie, bez trzech stale rozwiniętych zegarów przy każdym odcinku. Dokładność prezentacji do sekundy nie oznacza pewności harmonogramu do sekundy.

**R-009. Odliczanie nie odpytuje sieci co sekundę.** Terminy są pobierane według rzeczywistej potrzeby kalendarza. Znana przyszła emisja nie wywołuje ciągłego wyszukiwania wydań. Wcześniejsze zachowanie dla wpisów bez powiązania z katalogiem pozostaje ograniczonym fallbackiem, nie nową automatyczną zgodą na pobranie innej serii.

**R-010. Brak wydania i awaria mają ograniczone ponowienia.** Zachować bieżące okna poszukiwania i budżety usług, z możliwością jawnego wznowienia. Koniec jednego okna nie blokuje późniejszego odcinka. Restart nie zeruje wyczerpanych prób.

**R-011. Limity obowiązują wszystkie wejścia.** Wyszukiwanie, subskrypcje, odliczanie i Ręczny nie tworzą własnych pul obchodzących limity. Brak połączenia nie blokuje obsługi lokalnych gotowych materiałów niewymagających sieci.

**R-031. Przyjęte pobrania mogą działać równolegle.** Ukończony, wymagany plik odcinka może rozpocząć obróbkę, gdy pozostałe pliki paczki jeszcze się pobierają. Plik częściowy, prealokacja lub chwilowe zero prędkości nie uprawniają do startu. Pobrana paczka pozostaje płaska w `workspace/`; zadeklarowany w niej sidecar należy do kompletu danego odcinka. Zestaw ręcznie umieszczony w `subs` czeka na oba składniki, nie na niezależny odcinek.

Nie zatrzymujemy całego torrenta tylko po to, aby przenieść jeden gotowy wynik. Gdy klient nadal potrzebuje oryginalnego pliku, gotowy wynik trafia do `ready` wcześniej, a oryginał jest przenoszony dopiero po jego zwolnieniu. Użytkownik może już oglądać wynik. Nie powstaje dodatkowa kopia wielkiego oryginału.

## 8. Przetwarzanie, historia i Biblioteka

**R-043. Przetwarzanie pokazuje pobieranie i dalszą obróbkę.** Przyjęte w Anime zamówienie jest widoczne od przygotowania pobrania przez rzeczywisty transfer do obróbki. Każda pozycja ma czytelną nazwę materiału, aktualny etap i istniejący kolorowy pasek postępu. Pobieranie wygląda dokładnie jak obecny pasek TTS lub ekstrakcji: ten sam układ etapu, nazwy, gradientu, procentu i czasu, z etykietą „Pobieranie” podczas transferu. Nie otrzymuje osobnego skróconego wariantu. Pobieranie pokazuje procent zmierzony przez klienta, a obróbka pomiar bieżącego etapu. Oczekiwanie na metadane lub potwierdzenie ma uczciwą etykietę bez fikcyjnego procentu. Pauza i brak transferu nie udają aktywności. Archiwalne zakończone próby nie zalewają bieżącej listy; pusta lista jasno mówi o braku bieżącej pracy.

Every visible bar has numeric percentage and elapsed fields, including the first snapshot. Before a measurement, presentation uses `0% | 00:00:00.000` while backend `None` remains unknown. A later unavailable reading preserves the last measured percentage and freezes elapsed time; pause and disconnect also freeze it. A new task or generation starts its own percentage. The shared renderer retains its gradient, 14-column phase and fixed fields at 80/120 columns. With a panel attached, actual qBittorrent reads run approximately once per second; acceptance compares visible freshness with the client's GUI, not just repaint frequency. Progress is never interpolated from elapsed time.

Wiersz używa rzeczywistej nazwy pliku lub wydania, nigdy hasha torrenta, identyfikatora grupy ani zlecenia. Nie powielamy tego samego materiału tylko dlatego, że zmienił etap. Jawne Pobierz po przyjęciu przełącza do Przetwarzania, gdzie widać wskazany zakres i jego postęp. Gotowy wynik trafia do Biblioteki. Samo zadanie przyjęte w tle nie przełącza dowolnego innego otwartego ekranu. Widok nie kasuje zamówień ani ochrony przed ponownym pobraniem.

Niepewne potwierdzenia pobrania nie są wierszami Przetwarzania ani jego licznika, także przy zachowanym starym odczycie klienta. Rzeczywiście przyjęta obróbka pozostaje widoczna na podstawie swojego zlecenia i zdarzeń wykonania. Niepewne wpisy nie zasłaniają bieżącej pracy i nie tworzą pustych pasków.

**R-019. Problem zachowuje swoją przyczynę i drogę ponowienia.** Zakończone niepowodzeniem lub przerwane zlecenie jest dostępne w Historii pod Przetwarzaniem; nie udaje nadal wykonywanej pracy na głównej liście. Nieudane nowe zadanie nie staje się nową pozycją gotowej Biblioteki. Przy nieudanej regeneracji stary poprawny wynik nadal pozostaje w Bibliotece, a błąd nowej próby w Historii. Problemy przenoszenia wyników i Kosza pozostają dostępne w Bibliotece. Poprawne niezależne wyniki nie są kasowane.

**R-041. Historia jest ograniczona, stan ochronny nie.** Przetwarzanie domyślnie pokazuje bieżące pobieranie i obróbkę zgodnie z R-043. Pod tą samą zakładką dostępna jest Historia, bez nowej zakładki głównej i bez kalendarza. Początkowo pokazuje ostatnie 50 zakończonych pozycji; można przeszukać zapis ostatnich 30 dni. Te liczby są wybranymi wartościami początkowymi tej wersji, nie wcześniejszą precyzyjną decyzją użytkownika.

Historia pozwala otworzyć istniejący wynik i jawnie ponowić pracę. Gdy pliki zniknęły, ponowne pobranie wymaga zachowanego zamówienia internetowego; historia lokalnego TXT nie pozwala odtworzyć usuniętych bajtów. Rotacja historii nie usuwa aktywnych problemów, potwierdzeń pobrania, ochrony przed ponowieniem ani metadanych aktualnej Biblioteki. Nie zapisujemy każdego procentu.

**R-029. `ready` jest jednym miejscem wszystkich ukończonych wyników.** Nie zmieniamy nazwy na `output` i nie tworzymy osobnych katalogów wynikowych dla recept. Normalnie przenoszone są źródła i produkty, z zachowaniem całego zestawu. Wyjątek techniczny dla oryginału nadal należącego do aktywnej paczki opisuje R-031. Kolizja nazw zachowuje oba materiały jako dwa rozróżnialne zestawy, nie miesza ich sidecarów.

**R-039. Biblioteka pokazuje rzeczywiście gotowe materiały.** Lista jest alfabetyczna z naturalną kolejnością numerów. Enter otwiera główny wynik: film, audio albo plik tekstowy/napisów zgodnie z rodzajem materiału. F pokazuje plik w folderze. Szczegóły pokazują wszystkie pliki tego zestawu, formaty i dostępne rezultaty; to zaakceptowana użyteczna funkcja, nie tracker kolekcji. Gdy zamówiono oba kontenery wideo, głównym wynikiem jest MKV. Bez kontenera pierwszeństwo ma zamówione audio, następnie pełne napisy. Nie potrzeba dodatkowego ekranu wyboru odtwarzania.

For a completed video set without a final container, Enter opens its recorded source video through the existing OS association, preferring MKV over MP4. This is a playback target, not a new produced artifact: `main_result` continues to identify the confirmed product. The existing player configuration handles sidecars. Missing or changed main products still refuse opening; a missing recorded video gives a precise source-file refusal. F reveals the confirmed main product independently of source-video availability. Standalone audio, text and cover keep their existing opening behavior. Legacy records without sufficient video ownership retain their prior product target.

**R-042. Ręczne zmiany plików odświeżają listę.** Po usunięciu pliku w Explorerze otwarta Biblioteka aktualizuje się automatycznie, bez F5 i bez restartu. Wyświetlany stan nie jest niezależną, edytowaną ręcznie kopią dysku. W normalnym monitorowanym lokalnym folderze odświeżenie następuje przy najbliższej aktualizacji widoku, docelowo w ciągu około sekundy; nie wymaga pełnego skanowania i dekodowania mediów co sekundę.

Nie oznaczamy usunięcia jako obejrzenia. Usunięcie części sidecarów aktualizuje szczegóły; usunięcie głównego wyniku nie tworzy fikcyjnej gotowości. Zmiany w `ready` nie uruchamiają samoczynnej regeneracji.

**R-040. Delete sends the whole set to the Recycle Bin immediately.** Pressing Delete acts on the selected material without a confirmation screen or another keystroke. It sends the source video and associated subtitles, narration and exports to the system Recycle Bin. There is no default results-only scope or permanent-delete fallback. Ctrl+Z is the way to undo an accidental deletion.

Zakres obejmuje rozpoznane pliki danego zestawu, w tym `.pl`, `.spoken.pl`, `.displayed.pl` i właściwe audio, nie dowolny plik zaczynający się podobnym tekstem. `01` nie obejmuje `010`. Nie usuwamy całego `workspace/`, `ready/`, folderu zadaniowego, fontów współdzielonych ani zewnętrznego pliku tylko dlatego, że użyto go kiedyś w Ręcznym. Bieżący writer, aktywne źródło torrenta lub zmieniony zestaw blokują niebezpieczne potwierdzenie.

Częściowe niepowodzenie operacji nie jest sukcesem: pliki już przeniesione pozostają w Koszu, nieusunięte są wskazane, a ponowienie dotyczy wyłącznie reszty tego samego potwierdzonego zakresu. Odtworzenie przez systemowy Kosz jest odświeżeniem Biblioteki, nie nowym zamówieniem pobrania.

**R-046. Accidental deletion can be undone from the application.** Ctrl+Z in Library restores the last deleted set from the system Recycle Bin, including after a resident restart. Restoration targets that exact deletion, preserves unrelated destination files and never creates a new download order. Recovery evidence remains durable; the action must not silently select an older deletion instead.

**R-047. Library actions are direct and quiet.** Enter in Details opens the selected owned file through its OS association; F reveals that file in its folder. The owner revalidates identity and membership. Delete also acts on the whole set from Details. Library shows material names and file details, without routine admission/success/busy messages, recycle/restore operation rows, global processing counters or missing-result status prose. Deleted rows disappear and restored rows return. Actual synchronous action refusals remain concise and readable; they do not add confirmation steps.

## 9. Życie aplikacji i obsługa terminala

**R-002. Jedna instancja wykonawcza, wiele widoków.** Ponowne otwarcie aplikacji dołącza do działającego właściciela tej instalacji/workspace. Kolejne okno nie tworzy drugiego pobrania, kolejki ani syntezy. Interfejsy mają własne zaznaczenia i edycje, ale wspólny stan pracy.

**R-005. Zamknięcie terminala zamyka tylko widok.** Przetwarzanie, subskrypcje i obserwacja pozostają aktywne. Wyjście z Home ma ten sam skutek. Nie zabijamy programu Windows Terminal ani niezwiązanych zakładek.

**R-021. Ikona oferuje Otwórz, Zatrzymaj/Wznów i Zakończ.** Otwórz przywołuje istniejący panel lub uruchamia jeden widok Home. Zatrzymaj jest pauzą całego przepływu: nie ma nowych wyszukiwań, pobrań, tłumaczeń ani syntez, a własne transfery są wstrzymane. Rozpoczęte operacje dochodzą do bezpiecznej granicy i zapisują wynik. Po dojściu do pauzy program czeka na polecenie, bez aktywnej pracy multimedialnej i okresowego HTTP. Zakaz dotyczy pracy podejmowanej przez program: ręczne przeglądanie katalogu w panelu pozostaje dostępne, bo samo niczego nie zamawia ani nie pobiera, natomiast ręczne wznowienie transferu, ręczne pobranie, ręczne sprawdzenie subskrypcji i jawny start przetwarzania są pod pauzą odmawiane.

Wznów wznawia tylko pracę zatrzymaną tą pauzą oraz nadal zamówione, aktywne subskrypcje. Nie włącza wpisów celowo wyłączonych ani transferów zatrzymanych osobno. Krótkie „Zatrzymywanie” przed „Wstrzymano” jest prawdziwym stanem, nie obietnicą natychmiastowego przerwania obcego requestu.

Zakończ kończy rezydenta, bezpiecznie zatrzymuje i zamyka jego prywatny klient oraz odłącza/kończy interfejsy AniShift. Nie zamyka osobistego qBittorrenta. Niezatwierdzone szkice nie wykonują się po wyjściu; zapisane zlecenia przeżywają zakończenie.

**R-015. Prywatny qBittorrent uruchamia się z działającym AniShift.** Nie czeka dopiero na pierwsze pobranie, zgodnie z nowszą decyzją użytkownika. Otworzenie drugiego panelu nie startuje drugiego klienta. Awaria klienta nie blokuje pracy lokalnej i nie przekierowuje pobrań do osobistej instancji. Normalne otwarcie okna własnego klienta nie jest automatycznie utratą własności.

**R-030. Przygotowanie klienta jest samodzielne i odseparowane.** Zachować własną binarkę/profil, weryfikację pobrania i niezależne porty. Pierwszy start może przygotować brakujące narzędzie bez ręcznej konfiguracji Web UI. Nie kopiować cudzej historii, torrentów, sekretów ani aktywnych zadań. Uszkodzona instalacja ma krótką diagnozę i ograniczone ponowienie.

**R-024. Autostart odtwarza pracę, nie wykonuje jej podczas wyłączonego komputera.** Dla tej lokalnej konfiguracji czuwanie uruchamia się po zalogowaniu, bez otwierania terminala i bez potrzeby codziennego Entera. Zakończ dotyczy bieżącej sesji; wyłączenie autostartu jest osobnym ustawieniem. Trwała pauza pozostaje pauzą po restarcie, dopóki użytkownik nie wybierze Wznów.

Po restarcie zachowane wyniki są uzgadniane, a nie wykonywane ponownie. Niepewna operacja zewnętrzna nie jest dowodem niewykonania. Wiele paneli po ponownym połączeniu nie może uruchomić nieaktualnego podglądu.

**R-025. Spokój interfejsu nie ukrywa pracy w tle.** W bezczynności nie przybywa zbędnych skanów, probe, HTTP ani zapisów procentów. Pauza nie obiecuje zerowej pamięci procesu. Sekundowy zegar i stopka są aktualizacją widocznego UI, nie osobną usługą pracującą stale przy zamkniętym terminalu.

**R-023. Notifications concern a result or a required decision.** A completed material offers one notification per successful attempt. Clicking always opens Library; a current owner-validated `set_id` selects the exact episode. Unknown native identity opens useful Library without guessing the latest result; an expired identified result adds a concise notice. Ordinary tray-icon activation opens Home. Playback remains the user's Enter action. Do not notify after every stage or repeat an offer for reusing an old product. A private client's completion notification is not proof of AniShift completion.

## 10. Minimalny język interfejsu i ustawienia

**R-044. Interfejs zachowuje markę, upraszcza obsługę.** Czarne tło, białe/szare etykiety, oszczędny akcent istniejącej marki, oryginalna maskotka i duży wordmark w Home. Bez nowego motywu, logo, dashboardu z kafelkami lub nowego frameworka.

Nagłówek i zakładki nie zmieniają położenia podczas pracy. Na dole są wyśrodkowane skróty bieżącego widoku oraz krótki wspólny stan: aktywne pobrania, przetwarzane materiały i praca/pauza. Liczby odpowiadają rzeczywistym materiałom, nie liczbie technicznych tasków.

Nie dodajemy nowych podstron tylko po to, aby wyświetlić jedną datę. Dane szczegółowe trafiają do istniejącego szczegółu albo krótkiego panelu kontekstowego. Typowy wiersz subskrypcji nie zawiera języka źródła, historii requestów, trzech czasów i statusu oglądania naraz.

Ustawienia zachowują istniejące kategorie i edytory. Ekran Auto służy teraz receptom folderów, nie przełączaniu codziennego trybu pracy. Wideo, Tłumaczenie i Audiobook to podstawowe recepty; `subs` i `cover` dziedziczą odpowiednią bazę. Przy edycji widoczne są tylko parametry mające zastosowanie. Wspólny model i głos nie są powtarzane na każdej podstronie.

Zachować autosave zwykłych preferencji, jawne zatwierdzanie sekretów i zakresowe potwierdzenie resetu. Reset recepty nie zmienia kluczy, subskrypcji, plików ani pauzy. Nawigacja nie jest zmianą wartości. Skróty literowe nie działają jak polecenia podczas wpisywania tekstu.

## 11. Migracja i granice integralności

**R-026. Migracja zachowuje dotychczasową pracę bez jej samoczynnego wznowienia.** Istniejące presety, ustawienia, poprawne wyniki, wpisy subskrypcji i dane klienta nie są usuwane. Stare `taken` pozostaje dowodem przekazania, nie potwierdzeniem pobrania. Nowy model nie włącza historycznie wyłączonych subskrypcji i nie odtwarza usuniętej kolekcji.

Historyczna ścieżka subskrypcji nie może odtwarzać katalogu tytułu przy następnym pobraniu. Zastane media i rozpoczęte transfery wymagają uzgodnienia z klientem przed zmianą lokalizacji; nie wolno przenosić pliku zapisywanego przez torrent poza kontrolą klienta. Migracja nie pobiera materiału ponownie i nie wymaga od użytkownika tworzenia nowych katalogów.

Zmiana semantyki folderów nie działa na przypadkowo istniejący katalog o zarezerwowanej nazwie bez sprawdzenia zawartości. Przejście aktywnej instalacji wymaga jednego kontrolowanego wdrożenia z zatrzymaniem starego właściciela; nie jest codziennym krokiem użytkownika. Stare plany pozostające w toku mają zostać bezpiecznie dokończone albo wstrzymane do zgodnego wznowienia, bez zgadywania nowej recepty.

Undo extends the existing schema-2 deletion record with optional restore evidence. After the first Undo admission, pre-Undo builds reject this state. Downgrade must preserve and reconcile both the ledger and media effects; removing recovery fields or restoring an older ledger alone is not a supported rollback.

**I-001. Wyłączność:** ten sam fizyczny zestaw źródeł i jego wersja nie są równocześnie przetwarzane przez dwa zlecenia, niezależnie od sposobu zgłoszenia. Sama zgodność nazw w dwóch różnych katalogach nie oznacza tego samego materiału.

**I-002. Prawdziwa gotowość:** zaznaczenie, przyjęcie torrenta i poprawny rozmiar pliku nie zastępują dowodu potrzebnego kompletu i poprawnych produktów.

**I-003. Integralność:** nieudana poprawka nie niszczy starego wyniku; spóźniony plik nie jest publikowany ponad nowszym; sprzątanie i Kosz nie obejmują niezwiązanych źródeł.

**I-004. Własność:** tylko potwierdzone zasoby AniShift podlegają jego automatycznemu zatrzymaniu, relokacji i usunięciu.

**I-005. Jawny zamiar:** renderer, nawigacja, odliczanie, zamknięcie widoku i rotacja historii nie tworzą nowych zamówień.

Ograniczenia wykonania: lokalny Windows, obecny rdzeń i renderer, istniejące narzędzia multimedialne, brak nowej bazy/brokera i nowych zależności runtime. Rozszerzenia formatów mają używać obecnych usług, a nie drugi raz implementować tłumaczenie i TTS.

## 12. Kryteria akceptacji

ID wcześniejszego workstreamu są zachowane. Kryteria zmienione przez nowszą decyzję mają w kolumnie znaczenia jawnie nowy kontrakt; nie należy testować jednocześnie przeciwnej historycznej wersji.

| ID | Wymagania | Obserwowalny wynik |
|---|---|---|
| AC-001 | R-002, I-001 | Dwa panele i watcher zgłaszające tę samą grupę dają jedną pracę |
| AC-002 | R-002, R-018 | Podczas tłumaczenia można sterować i zauważyć nowy niezależny materiał |
| AC-003 | R-003, R-021 | Pauza całego systemu blokuje nowe pobrania i przetwarzanie; nie ma zwykłego trybu pobierz-bez-obróbki |
| AC-004 | R-032, R-037 | Ta sama baza w root, subs i audiobook otrzymuje właściwy cel, bez kopiowania całych preferencji |
| AC-005 | R-004 | Zmiana wejścia po podglądzie uniemożliwia wykonanie starego wyboru |
| AC-006 | R-021 | Pauza kończy rozpoczęty etap do bezpiecznej granicy i nie rozpoczyna następnego |
| AC-007 | R-006 | Wybór 3 i 8 nie pobiera 1–2 ani 4–7; 7.5 nie gubi odcinka 8 |
| AC-008 | R-007, R-014 | Przyjęty torrent nie jest pobranym plikiem, a błąd TTS nie usuwa potwierdzenia pobrania |
| AC-009 | R-008, R-009 | Widoczny zegar zmienia sekundy bez sekundowych żądań Nyaa/AniList |
| AC-010 | R-008 | Czas emisji nie jest podpisany jako czas gotowego lektora |
| AC-011 | R-009 | Przełożenie emisji zmienia licznik; brak terminu nie oznacza teraz |
| AC-012 | R-010 | Brak wydania po końcu okna pozostaje widoczny, a kolejny odcinek nie jest przez niego blokowany |
| AC-013 | R-011 | Wyszukiwanie ręczne i subskrypcje respektują wspólną blokadę dostawcy |
| AC-014 | R-012 | Po zakończeniu sezonu nie powstają cykliczne poszukiwania hipotetycznych odcinków |
| AC-015 | R-014, R-040 | Usunięcie kompletnego odcinka i ponowny start nie pobierają go drugi raz |
| AC-016 | R-014, R-024 | Restart po przyjęciu torrenta uzgadnia istniejące zamówienie |
| AC-017 | R-016, R-031 | Prealokowany lub nadal zapisywany plik nie wchodzi do przetwarzania |
| AC-018 | R-016, R-028 | Własna publikacja i dwa zdarzenia plikowe nie tworzą nowego zlecenia |
| AC-019 | R-033 | MKV→SRT i SRT→MKV w subs kończą się jednym wideo, nigdy osobnym audiobookiem |
| AC-020 | R-018 | Nowy ręczny task dostaje właściwy wolny slot przed tłem, bez zrywania aktywnego |
| AC-021 | R-019 | Po wyczerpanym retry problem pozostaje widoczny; inne niezależne zadanie działa |
| AC-022 | R-021, R-031 | Pauza i uśpienie nie są liczone jako zastój aktywnego pobierania |
| AC-023 | R-015 | Start AniShift uruchamia jeden prywatny klient, a kolejny panel dołącza do niego |
| AC-024 | R-017, R-020 | Globalna zmiana głosu nie regeneruje gotowych odcinków; jawna poprawka nie powtarza tłumaczenia |
| AC-025 | R-020, I-003 | Awaria regeneracji zachowuje poprzedni dobry plik |
| AC-026 | R-005, R-021 | Zamknięcie terminala nie zatrzymuje automatyzacji; Zakończ rzeczywiście ją kończy |
| AC-027 | R-022, R-043 | Cztery zakładki mają określoną kolejność, a Panel otwiera domyślnie trzecią |
| AC-028 | R-029, R-031 | Gotowy wynik pierwszego odcinka paczki można otworzyć przed zakończeniem ostatniego |
| AC-029 | R-024 | Start po dłuższej przerwie nie odtwarza każdej pominiętej rundy harmonogramu |
| AC-030 | R-024, R-042 | Po wznowieniu system zauważa pliki dodane podczas przerwy i aktualizuje widok |
| AC-031 | R-025 | Ustalone idle i pełna pauza nie generują okresowych probe, HTTP i pełnych skanów |
| AC-032 | R-026 | Migracja starego taken nie tworzy fikcyjnego pobrano ani masowych ponowień |
| AC-033 | R-001, R-037 | Dotychczasowe tłumaczenie/TTS i zaawansowany wybór źródeł pozostają dostępne bez nowej zależności |
| AC-034 | R-012, R-027 | Nadchodzący sezon można zasubskrybować bez istniejącego torrenta |
| AC-035 | R-006, R-012 | Zakończony sezon pobiera tylko wybrany zakres, nie historię franczyzy |
| AC-036 | R-003, R-021 | Wznów przywraca globalnie zapisaną pracę, ale nie włącza wyłączonej subskrypcji |
| AC-037 | R-004 | Ręczny wykonuje tylko zaznaczone materiały i nie zmienia ustawień innych |
| AC-038 | R-027 | Dodaj, aktywność i Usuń wpis działają z listy; Enter otwiera kartę zamiast przełączać aktywność |
| AC-039 | R-013 | Wyłączenie podczas szukania blokuje spóźnione zamówienie nowego torrenta |
| AC-040 | R-028 | Automat nie odtwarza celowo pominiętych produktów po Ręcznym |
| AC-041 | R-020 | Jawne force z identycznymi ustawieniami tworzy nową pracę; zwykłe czuwanie nie |
| AC-042 | R-002, R-024 | Stary panel po restarcie nie wykonuje starego podglądu ani duplikatu komendy |
| AC-043 | R-029 | Wyniki wszystkich pięciu ścieżek wejścia trafiają do wspólnego ready, a kolizja nie miesza zestawów |
| AC-044 | R-030 | Nowa instalacja przygotowuje prywatnego klienta bez użycia osobistego profilu |
| AC-045 | R-015, R-031 | Własny i osobisty klient mogą współistnieć; zakończenie AniShift nie zamyka osobistego |
| AC-046 | R-032, R-033 | Ręcznie utworzone zagnieżdżenie dziedziczy rolę głównego miejsca zadaniowego; aplikacja sama go nie tworzy |
| AC-047 | R-033, R-038 | Film w subs z osadzonymi EN nadal czeka na sidecar; po jego przyjściu używa właśnie sidecara |
| AC-048 | R-034, R-038 | Sam SRT w root pozostaje oczekujący, ten sam SRT w translate tłumaczy się bez MKV |
| AC-049 | R-035 | TXT→TXT nie uruchamia TTS, zachowuje kolejność i akapity, a oryginał pozostaje |
| AC-050 | R-034 | Tłumaczenie SRT zachowuje czasy; ASS/SSA zachowuje potrzebne style i tagi bez nowego typesettingu |
| AC-051 | R-035 | Audiobook z SRT nie ma pauz między oryginalnymi czasami; wariant Ręczny „czasy SRT” je respektuje |
| AC-052 | R-035 | TXT→SRT bez nagrania jest opisany jako roboczy skrypt, nie gotowa synchronizacja |
| AC-053 | R-035 | „Nie tłumacz” wykonuje sam głos bez zlecenia tłumaczenia |
| AC-054 | R-036 | Obraz pierwszy i obraz ostatni prowadzą do jednego MP4 dopiero po komplecie |
| AC-055 | R-036 | Gotowe audio+obraz nie wykonuje TTS i nie obcina końcówki audio |
| AC-056 | R-036 | Konkurujące obrazy lub dwa źródła treści nie są wybierane losowo |
| AC-057 | R-037 | Jedna zmiana wspólnego głosu obejmuje nowe zadania wideo/audiobook/cover bez trzech edycji |
| AC-058 | R-027 | Anime→Subskrybuj→karta→zatwierdzenie nie wymaga ręcznego kopiowania tytułu i nie pobiera przed zatwierdzeniem |
| AC-059 | R-027, R-014 | Jawne Ponów usuniętego numeru działa, zwykłe zaznacz wszystko nie resetuje ukończeń |
| AC-060 | R-007 | Żaden ekran ani zapis nowego modelu nie wprowadza trackera obejrzenia lub „Mam lokalnie” |
| AC-061 | R-039 | Enter opens the final video or the recorded source video of a completed sidecar-only video set; F reveals the confirmed main product, and details list all owned files |
| AC-062 | R-040 | Delete immediately recycles the whole set without a confirmation; deleting 01 does not affect 010 |
| AC-063 | R-040 | Błąd Kosza nie wywołuje trwałego unlink, a częściowy wynik jest rozliczony |
| AC-064 | R-042 | Ręczne usunięcie/przywrócenie gotowego pliku zmienia otwartą listę bez Start i bez ponownego Auto |
| AC-065 | R-041 | Usunięcie historii starszej niż 30 dni nie powoduje ponownego pobrania ani utraty aktywnego błędu |
| AC-066 | R-021 | Globalna pauza pamięta, które transfery sama zatrzymała, i nie wznawia pozostałych |
| AC-067 | R-023 | A result notification opens Library and selects the exact episode when its identity is validated; unknown identity does not guess a result, and ordinary icon activation opens Home |
| AC-068 | R-044 | Stopka pokazuje prawdziwe liczby oraz skróty kontekstowe; wpisywanie tekstu nie wykonuje skrótów akcji |
| AC-069 | R-044 | Wąski terminal zachowuje dostęp do wszystkich czterech zakładek i działań bez obcinania potwierdzenia |
| AC-070 | R-026 | Konflikt istniejącego folderu z nową rolą zatrzymuje wyłącznie migrację tego miejsca, nie niszczy plików |
| AC-071 | R-032, R-026 | Pobrania kilku różnych tytułów z Anime, subskrypcji i Ponów, także paczki z własnym układem folderów, zapisują pliki bezpośrednio w workspace; nie powstają katalogi tytułów ani downloads, również po restarcie |
| AC-072 | R-032, I-003 | Dwa wydania z kolidującymi nazwami nie nadpisują się ani nie mieszają par wideo/napisy; rozdzielenie odbywa się nazwami zestawów, bez nowych podfolderów |

## 13. Zmiana kontraktu wobec poprzedniej specyfikacji

R-003/R-005/R-021 zastępują codzienny podział „Auto on/off niezależne od pobierania” stałą automatyzacją i pauzą całego przepływu. R-015/R-030 zastępują start klienta na żądanie startem wraz z AniShift. R-022 usuwa starą kolejność menu i osobne Pobrania. R-029 pozostaje przy ready, z doprecyzowaniem własności aktywnej paczki. R-032–044 dodają foldery, samodzielne produkty, Bibliotekę i historię. Pozostałe zabezpieczenia istniejącego rdzenia pozostają obowiązujące.

R-032 oraz AC-071–072 zastępują wcześniejsze dopuszczenie katalogów pobrań per seria: docelowe pobrania są płaskie w głównym `workspace/`, a `ready/` pozostaje wspólne.

Nie obowiązują wcześniejsze makiety z lokalnym oznaczaniem obejrzenia, „Mam lokalnie” ani obowiązkowym pośrednim menu po Enter w Bibliotece. Nie akceptujemy ich ponownie pod inną nazwą.

Nie ma otwartego pytania blokującego model folderów i przepływu. Pozostałe sprawdzenia empiryczne to rzeczywista wygoda układu, zachowanie Windows/Kosza i prywatnego klienta oraz kompletność produktów po awarii. Ich zakres i reakcje definiuje plan, a nie kolejne domyślne rozszerzanie funkcji.

## 14. Podstawa

- Decyzje właściciela w tej rozmowie, zwłaszcza odrzucenie statusu obejrzenia, rozdzielonych Pobrań i ręcznego uruchamiania codziennego Auto oraz przyjęcie folderów według celu.
- `wip.zip`: pełne skille `simple`, `specification`, `planning`; specyfikacja opisuje rezultat, plan sposób wykonania.
- [Aktualny workstream w odczytanym commicie](https://github.com/MattyMroz/AniShift/tree/25121038fbf4ff1e1cecec3d4e644fdb235be679/docs/work/local-automation/06-efficiency): starszy kontrakt i raport jako baseline, nie nadrzędne źródło nowego UX.
- [Planner](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/planner.py): obecny TXT tylko do polskich SRT i wspólne planowanie produktów.
- [Audio](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/services/audio/types.py): istniejące audio bez źródłowej ścieżki filmu; adapter aplikacji wymaga rozszerzenia.
- [Subskrypcje](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/subscriptions.py), [transfery](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/transfers.py), [ready](https://github.com/MattyMroz/AniShift/blob/25121038fbf4ff1e1cecec3d4e644fdb235be679/anishift/application/ready.py): istniejąca trwałość, granice kompletności i relokacji.

Status READY nie oznacza wdrożenia, wykonania testów aplikacji ani wizualnej akceptacji. Ten plik aktualizuje kontrakt w pakiecie do przekazania; nie został zapisany na GitHubie.

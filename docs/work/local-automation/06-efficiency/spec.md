---
kind: specification
status: READY
created: 2026-09-07
updated: 2026-09-08
baseline: a7d319f334a062d0fe016c774d9a5fb4fccbe9b6
source_branch: work/local-automation/06-efficiency
---

# AniShift: Manual, Auto i niezależne subskrypcje

## 1. Cel i obowiązywanie

**Manual: wybieram odcinki i uruchamiam pracę. Auto: aplikacja sama reaguje na gotowe pliki na dysku. Subskrypcje: osobno decyduję, co ma być pobierane, i mogę je dodawać, włączać, wyłączać oraz usuwać.**

Wszystkie drogi korzystają z obecnego przetwarzania AniShift. Regeneracja jest ponownym Auto dla wybranego zakresu, z opcjonalnie innymi ustawieniami i wymuszeniem wskazanej poprawki. Nie jest trzecim trybem ani nowym silnikiem.

To aktywna specyfikacja etapu 06. Zastępuje wcześniejszy załączony `spec.md` i niejednoznaczne notatki w `docs/plans/local-automation/plans/06-queue-and-control.md`. Stare dokumenty całej automatyzacji wyjaśniają historię; nie wolno na ich podstawie dodawać SQLite, osobnego inboxa, katalogów rewizji ani drugiego schedulera. Dokument opisuje zamawianą zmianę, nie już wdrożone funkcje.

Podstawa: doprecyzowania właściciela w rozmowie, kod wskazanego commitu oraz [research](research/2026-09-08-control-model-research.md). Sposób implementacji i kolejność prac: [plan.md](plan.md).

**Ustalenia właściciela:** lokalne działanie, istniejący rdzeń, ręczny wybór odcinków, Auto od plików, niezależne subskrypcje, pierwszeństwo ręcznej pracy bez zrywania trwających operacji, oszczędne terminy premier, ikona w tle, kontrola z aplikacji, brak nowych zależności i zmiany formatów produktów/presetów.

**Rozstrzygnięcia projektowe tej wersji:** globalny przełącznik Auto, zachowanie wcześniejszego wyjątku per katalog jako ograniczenia Auto, ochrona wybranych odcinków podczas edycji, kończenie już przyjętych transferów po wyłączeniu subskrypcji, brak automatycznego śledzenia kolejnego sezonu oraz jawne ustawienia początkowe w sekcji 6. Są to decyzje tej specyfikacji, nie rzekome cytaty właściciela ani pomiary.

`READY` oznacza kontrakt wystarczający do implementacji według planu. Nie oznacza wykonanego kodu, testów na Windowsie ani zaakceptowanych pomiarów wydajności.

## 2. Model pracy

```text
Subskrypcja WŁĄCZONA -> szukanie według terminu -> pobranie ----+
Ręczne pobranie z Anime -------------------------------------+-> plik w bibliotece
Własne skopiowanie pliku ------------------------------------+
                                                               |
                                  Auto WŁĄCZONE + gotowe wejście -> plan Auto

Manual -> wybór odcinków -> podgląd -> Start --------------------> plan wybranego zakresu
Regeneruj -> zakres + poprawka/ustawienia -> podgląd -> Start ----> plan Auto z odtworzeniem
                                                               |
                                             wspólne wykonanie -> produkty obok źródła
```

| Element | Jego zadanie | Czego nie robi |
| --- | --- | --- |
| Subskrypcja | Pamięta sezon, grupę, zakres, katalog i następny termin pozyskania. | Nie tłumaczy, nie wywołuje TTS, nie włącza Auto. |
| Pozyskanie | Dostarcza kompletny plik i wiarygodny stan transferu. | Nie utożsamia przyjęcia torrenta z pobraniem. |
| Auto | Rozpoznaje gotowe wejście, dobiera potrzebną pracę z presetu. | Nie wybiera anime i nie wymaga subskrypcji. |
| Manual | Pozwala wskazać odcinki i świadomie zatwierdzić ich wykonanie. | Nie wyłącza pozostałej automatyzacji i nie wymaga ręcznego budowania grafu etapów. |
| Regeneruj | Wywołuje Auto ponownie dla wybranego zakresu i poprawki. | Nie ma własnego planera ani kolejki. |
| Wykonanie | Realizuje potrzebne etapy, limity, publikację i postęp. | Nie zawiera reguł śledzenia premier. |
| Panel i ikona | Pokazują stan i przekazują polecenia. | Nie wykonują operacji domenowych przy odrysowaniu. |

**R-001. Jeden rdzeń.** Zachować obecne planowanie, handlery, publikację i `GraphScheduler`. Można rozszerzyć ich kontrakty; nie można stworzyć alternatywnego wykonania dla Auto, Manual, regeneracji albo subskrypcji. Harmonogram pozyskania nie jest kolejką tłumaczenia/TTS.

**R-002. Jeden właściciel pracy.** Panel, CLI, watcher i subskrypcje nie mogą równolegle wykonywać tej samej grupy ani nieskoordynowanie zapisywać wspólnego stanu. Sterowanie, obserwacja plików i obsługa terminów działają podczas aktywnego przetwarzania oraz wolnych odpowiedzi sieciowych.

## 3. Auto i Manual bez konfliktu

**R-003. Auto jest włączanym automatycznym przetwarzaniem biblioteki.** Włączenie Auto obejmuje gotowe nieobsłużone pliki już na dysku oraz pojawiające się później. Wyłączenie blokuje nowe automatyczne operacje przetwarzania, ale nie wyłącza subskrypcji, nie zatrzymuje pobierania i nie blokuje Manual. Rozpoczęte operacje kończą się do swojej bezpiecznej granicy, a niewykonana część czeka.

Pozostaje możliwość wyłączenia Auto dla wybranego katalogu, zgodnie z wcześniejszym ustaleniem właściciela. To wyjątek od Auto, nie osobny pipeline ani globalny tryb Manual. Bez wyjątku katalog dziedziczy ustawienie biblioteki; przy zagnieżdżeniu obowiązuje najbliższy jawny wyjątek. Globalne wyłączenie Auto blokuje wszystkie automatyczne starty, również w katalogu z jawnym Auto. Panel pokazuje skuteczne ustawienie, nie tylko lokalną wartość.

| Auto dla pliku | Subskrypcja | Rezultat |
| --- | --- | --- |
| Włączone | Włączona | Subskrypcja dostarcza odcinki; gotowe pliki są przetwarzane. |
| Wyłączone | Włączona | Odbywa się pobieranie; kompletne pliki czekają na Manual lub ponowne włączenie Auto. |
| Włączone | Wyłączona albo brak | Własne pliki i ukończone wcześniej zamówione pobrania nadal uruchamiają Auto. |
| Wyłączone | Wyłączona albo brak | Brak nowych działań tych automatów; Manual nadal działa. |

**R-004. Manual zaczyna się od wyboru odcinków.** Użytkownik może zaznaczyć jeden, kilka lub zakres odcinków. Domyślny preset wypełnia ustawienia, więc zwykła praca nie wymaga przechodzenia przez wszystkie opcje. Podgląd pokazuje wybrany zakres, zachowywane produkty i operacje potrzebne do wykonania. Dopiero Start składa zlecenie.

Obecny zaawansowany wybór napisów, audio, ścieżek i produktów pozostaje dostępny, ale jest opcjonalny. Manual nie oznacza wyłączania Auto w całej aplikacji ani zmiany trybu katalogu. Wybranie odcinków 3 i 8 nie uruchamia pozostałych.

Samo otwarcie listy niczego nie rezerwuje. Dopiero faktycznie wybrane grupy są chronione przed przejęciem przez Auto podczas edycji. Odznaczenie, wyjście lub utrata sesji edytora zwalnia ochronę. Grupa już wykonywana pokazuje konflikt; nie zatrzymujemy jej po cichu. Źródło zmienione po podglądzie wymaga ponownego podglądu. Zniknięcie ochrony po awarii rezydenta nie uprawnia starego panelu do Start na nieaktualnym stanie.

**R-005. Czuwanie to działający proces, nie trzeci przełącznik trybu.** Rezydent obsługuje niezależne ustawienia Auto i subskrypcji, przyjmuje Manual i utrzymuje stan. Nie dodajemy mylącego globalnego wyboru „albo Auto, albo Manual”. Jednorazowe uruchomienie Auto dla wybranego zakresu jest jawnym zleceniem i nie zmienia przełącznika Auto.

Uruchomienie samego panelu nie włącza automatyzacji, której użytkownik nie włączył. Dotychczas włączone czuwanie zachowuje działanie po migracji. Zamknięcie panelu nie anuluje zatwierdzonej pracy. Zatrzymanie całego AniShift jest osobnym działaniem.

**R-028. Ręczna decyzja nie jest zaraz cofana przez Auto.** Po wykonaniu Manual albo regeneracji tło nie przebudowuje tej samej wersji odcinka według domyślnego głosu ani nie dopisuje produktów celowo pominiętych w zatwierdzonym ręcznym zakresie. Nie wpływa to na nowe odcinki. Dalsze uzupełnienie tej grupy jest możliwe przez jawne Auto jednorazowo, regenerację albo obsługę rzeczywiście nowego wejścia. Ręczny błąd/anulowanie pozostają widoczne i nie uruchamiają nowego zlecenia z watchera dla tego samego zamiaru.

## 4. Subskrypcje pod kontrolą

**R-006. Subskrypcja ma jednoznaczny zakres.** Wskazuje konkretny sezon, grupę wydawniczą, reguły języka i jakości, zakres odcinków oraz katalog biblioteki. Tytuł jest etykietą i frazą wyszukania, nie jedynym dowodem tożsamości. Zachować numerację sezonów, części sezonu i numerację absolutną. Odcinek 7.5 nie przesuwa sam licznika kolejnego całkowitego odcinka.

Dodanie pokazuje sezon, grupę, katalog, pierwszy zamawiany odcinek i skuteczne Auto. Start od N obejmuje N, bez dodawania jedynki. Zachować ustalenie właściciela dotyczące jego wskaźnika `Matty_Mroz`, o ile taki wskaźnik jest wejściem; ta zmiana nie implementuje importera ani synchronizacji MAL. Pobranie i przetworzenie nie oznaczają obejrzenia.

Można dodać nadchodzący sezon bez istniejącego torrenta, wskazując grupę. Nieustalone dopasowanie nie pozwala pobrać przypadkowego wydania. Zamówienie dostępnych zaległości obejmuje tylko uzgodniony zakres, nie całą historię franczyzy.

**R-007. Osobne fakty o odcinku.** Rozróżniać: zamówiony zakres, dostępność wydania, stan transferu, gotowość źródła i gotowość poszczególnych produktów. Jeden licznik „następny odcinek” nie zastępuje braków. Tłumaczenie może być gotowe, kiedy lektor wymaga ponowienia; pobrany plik może czekać przy wyłączonym Auto.

**R-013. Wyłączanie i usuwanie nie niszczą danych.** Wyłączenie subskrypcji zatrzymuje jej przyszłe automatyczne sprawdzenia i zamawianie nowych pobrań. Zachowuje ustawienia, historię i braki. Usunięcie usuwa wpis subskrypcji, ale nie pliki, wyniki ani wcześniej przyjęte transfery. W interfejsie te skutki są podpisane.

Przyjęte transfery mogą się dokończyć. Zatrzymanie/anulowanie konkretnego pobrania jest osobną akcją. Jeżeli Auto jest włączone, ukończony plik nadal może zostać przetworzony po wyłączeniu lub usunięciu subskrypcji. Wyłączenie Auto jest właściwą akcją do zatrzymania samoczynnej obróbki.

**R-027. Pełne zarządzanie z aplikacji.** Lista subskrypcji udostępnia Dodaj, Włącz, Wyłącz i Usuń. Włączenie jest idempotentne: nie dubluje wpisu, nie zeruje historii i nie pobiera ponownie gotowych odcinków. Ponowne włączenie uzgadnia bieżące braki raz, bez odtwarzania każdej pominiętej godziny. Nie przywraca samo wcześniej wyczerpanych prób ani świadomie zamkniętych poszukiwań.

Wyłączenie/usunięcie w trakcie wyszukiwania musi zablokować dodanie torrenta przez spóźnioną odpowiedź. Już wysłane żądanie HTTP nie może zostać cofnięte, ale jego wynik nie może reaktywować wyłączonego wpisu. Transfer przyjęty przed zatwierdzeniem wyłączenia jest pokazywany jako wcześniej zamówiony. Wielokrotne kliknięcie i ponowienie po zerwaniu połączenia nie dublują skutku.

Włączona subskrypcja może czekać na premierę, transfer lub naprawę problemu. „Włączona” nie znaczy „ciągle odpytująca”. Zakończonego sezonu przycisk Włącz nie zamienia w wieczny polling; ponowne poszukanie jego braków jest jawną, ograniczoną czynnością.

## 5. Terminy premier zamiast ciągłego odpytywania

**R-008. Pierwsze sprawdzenie ma powód i termin.** Dla oczekiwanego odcinka pierwsze automatyczne szukanie wydania następuje nie wcześniej niż emisja plus oczekiwane opóźnienie grupy. Priorytet doboru opóźnienia: korekta użytkownika, wiarygodna historia danej serii/grupy, ustawienie początkowe. Pokazywać osobno emisję, szacunek wydania i następne sprawdzenie.

Historia korzysta z dat emisji i publikacji dopasowanych wydań, nie z czasu pobrania czy modyfikacji pliku. Paczki, reuploady i niepewne dopasowania nie uczą opóźnienia. Zmiana grupy nie dziedziczy bezwarunkowo jej poprzednika. To proste oszacowanie, nie LLM ani nowy system uczenia.

**R-009. Kalendarz także nie jest odpytywany na zapas.** Pobierać go przy dodaniu, potrzebie kolejnego terminu, jawnym odświeżeniu i celowej weryfikacji przy terminie sprawdzenia. Znana przyszła emisja nie wywołuje godzinnych odświeżeń całej listy. Potwierdzone przełożenie emisji odwołuje stary termin szukania.

Poprawna odpowiedź bez daty oznacza „Brak harmonogramu”, nie „wydane teraz” ani „sezon zakończony”. Przy znanej przyszłej przybliżonej dacie rozpoczęcia można poczekać do tej granicy. Bez żadnego terminu wpis czeka na uzupełnienie lub jawne odświeżenie; nie szuka nieustannie w Nyaa. Awaria kalendarza korzysta z ograniczonych retry. Czasy trwałe oznaczają konkretne chwile; interfejs wyświetla je lokalnie. Zmiana strefy/czasu letniego nie dubluje pracy.

**R-010. Spóźnione wydanie nie jest szukane wiecznie.** Poprawna odpowiedź bez wydania wyznacza następne sprawdzenie tego odcinka w jego oknie. Po wyczerpaniu okna pozostaje widoczny brak wymagający decyzji. Następny odcinek może być obsłużony mimo tej luki; nowa premiera nie wznawia automatycznie starych wygasłych poszukiwań.

„Sprawdź teraz” wykonuje jedno sprawdzenie wskazanego zakresu. „Szukaj dalej” jawnie otwiera nowe ograniczone okno. Obie akcje respektują blokadę dostawcy; nie oznaczają reaktywacji całej wyłączonej subskrypcji.

**R-011. Budżet obejmuje faktyczne HTTP.** Zachować rozstrzygnięty sezon, grupę, kategorię i przydatną frazę. Nie uruchamiać pełnego interaktywnego wyszukiwania aliasów/prequeli na każdą premierę. Zbieżne potrzeby tego samego zasobu współdzielą operację i wynik. RSS nie jest pełną historią sezonu; szukanie konkretnego brakującego numeru jest ograniczonym wyjątkiem.

Liczyć także retry, logowania, obie kategorie i odpowiedzi 304. Wspólna blokada dostawcy obowiązuje wszystkie ścieżki, również ręczne. Respektować `Retry-After`, odpowiedzi limitowania i ograniczać serie jednoczesnych żądań. Brak sieci nie zatrzymuje panelu i prac niewymagających sieci. Warunkowy cache stosować tylko tam, gdzie źródło go obsługuje; 304 nadal jest requestem.

**R-012. Koniec sezonu jest widoczny.** Nie szukać hipotetycznego odcinka poza zamówionym sezonem. Status zakończonej emisji nie dowodzi kompletu plików i nie zamyka przedwcześnie okna na wydanie finału. Po wyczerpaniu konkretnych okien wpis pozostaje jako zakończony: komplet, braki lub nieustalona kompletność. Nie znika automatycznie.

Zakończona subskrypcja nie wykonuje samoczynnych wyszukiwań ani odświeżeń kalendarza, także raz w tygodniu. Już przyjęte transfery mogą się dokończyć. Następny sezon jest osobnym jawnym zamówieniem, nie automatycznym skutkiem podobnej nazwy.

## 6. Ustawienia początkowe

Poniższe liczby są **propozycją zmienialnych ustawień**, nie zmierzonymi właściwościami grup, usług lub komputera. Zwykłe dodanie subskrypcji nie wymaga ich ręcznego wpisywania.

| Ustawienie | Początkowo | Znaczenie |
| --- | --- | --- |
| Opóźnienie wydania bez historii | 3 godziny | Pierwsze szukanie po emisji; jawna korekta ma pierwszeństwo. |
| Odstęp po poprawnym braku wydania | 1 godzina | Dotyczy należnego odcinka, nie wszystkich subskrypcji. |
| Okno poszukiwania | 72 godziny od pierwszego terminu | Potem brak wymagający uwagi. |
| Brak postępu transferu | 30 minut aktywnego pobierania | Nie naliczać pauzy, uśpienia i sprawdzania danych. |
| Budżet przejściowej awarii zewnętrznej operacji | 3 próby łącznie | Początkowa i dwa ponowienia, bez mnożenia między warstwami. |
| Odstępy retry bez wskazania serwera | 1 minuta, potem 5 minut | Dłuższe ograniczenie dostawcy ma pierwszeństwo. |

Budżet dotyczy konkretnej ponawialnej operacji, np. danego wywołania lub klipu, nie wszystkich żądań całego odcinka. Nie zastępuje istniejącej ograniczonej obsługi lokalnej blokady publikowanego pliku. Zachować ustawienia współbieżności etapów jako źródło limitów. Nie wpisywać do specyfikacji nowych stałych liczby tłumaczeń/głosów.

Dotychczasowe 10 sekund stabilności własnego pliku pozostaje kontrolą pomocniczą; nie dowodzi ukończenia torrenta.

## 7. Pliki, transfery i oszczędne przetwarzanie

**R-014. Zamówione nie znaczy pobrane.** Tożsamość wydania i zlecenia musi przetrwać restart między dodaniem torrenta a lokalnym potwierdzeniem. Niepewny wynik dodania uzgadnia się z klientem przed ponowieniem. Odcinek jest pobrany po potwierdzeniu ukończenia wymaganych plików i ich lokalnej dostępności. W paczce liczą się wybrane pliki, nie pominięte elementy.

Hash w kliencie, pełny zaalokowany rozmiar, brak zmian lub prędkość zero nie dowodzą kompletu. Istniejący poprawny odcinek zaspokaja zamówienie; nowe wydanie z większą liczbą seedów nie powoduje automatycznej podmiany. Ręczne usunięcie pliku nie zamawia automatycznie ponownego pobrania.

**R-015. qBittorrent na żądanie i z poszanowaniem własności.** Zarządzany klient startuje dla rzeczywistego pobrania lub wznowienia, nie przy otwarciu panelu, oczekiwaniu na premierę czy pustym wyszukaniu. Potrzebne transfery są odczytywane zbiorczo, nie raz na wiersz interfejsu.

Automatycznie zamknąć można tylko rozpoznaną własną instancję bez cudzej pracy. Instancji zastanej, ręcznie uruchomionej, przejętej przez użytkownika lub niepewnej nie zamykać i nie rekonfigurować globalnie. Kategoria `anishift` nie dowodzi własności procesu. Nie deklarować całkowitego braku wysyłania w trakcie pobierania; zachować ustalenie o braku dalszego seedowania po pobraniu dla zarządzanych zleceń.

**R-016. Gotowość jest wspólna dla wszystkich źródeł.** Watcher obsługuje zarówno własne pliki, jak i zakończone transfery. Nie przetwarza plików częściowych, niedostępnych lub zmienianych. Znany transfer wymaga potwierdzenia kompletności; nie obchodzi się go testem stabilności. Dla obcego kopiowania stosuje się dostępne lokalne kontrole, bez obietnicy wykrycia dowolnego wstrzymanego writera.

Brak wymaganych napisów pozostawia czytelny stan oczekiwania. Ich późniejsze pojawienie odblokowuje właściwą grupę. Zdarzenie ukończenia i zdarzenie pliku dla tego samego wejścia nie tworzą dwóch prac. Produkty AniShift aktualizują stan grupy, ale nie stają się nowymi odcinkami i nie wywołują pętli Auto.

**R-017. Auto wykonuje potrzebne operacje.** Poprawne dostępne produkty są ponownie wykorzystywane. Dodanie jednego odcinka nie powoduje ponownej inspekcji/dekodowania wszystkich niezmienionych mediów. Zmiana ustawień lub presetu sama nie regeneruje historii. Przyjęte zlecenie ma ustalone ustawienia; edycja innego przebiegu go nie zmienia. Nowe ustawienia stosuje się do nowych zleceń lub jawnie zmienionego oczekującego zakresu.

**R-029. Wspólny folder gotowych odcinków — ustalenie właściciela 2026-09-12.** Ręczne wejście pozostaje w głównym `workspace`, bez wymaganego `input`. Po udanym przetworzeniu źródło i związane produkty trafiają do jednego płaskiego `workspace/ready`. Regeneracja działa na odcinku bezpośrednio w `ready`; użytkownik nie przenosi go z powrotem. Relokacja nie tworzy nowego zlecenia Auto, a kolizja nazw nie nadpisuje innego odcinka. Na tym samym woluminie źródło jest przenoszone bez przepisywania zawartości. To ustalenie zastępuje wcześniejszy wymóg pozostawiania wszystkich produktów w pierwotnym katalogu źródła.

**R-018. Ręczna praca ma pierwszeństwo bez zrywania operacji.** Dotyczy Manual, jawnego Auto, regeneracji, świeżo wrzuconego własnego pliku i ręcznie wybranego pobrania, gdy plik będzie gotowy. Pochodzenie wynika z faktycznego zdarzenia/zamówienia, nie z nazwy katalogu ani samego istnienia subskrypcji.

Gotowa pilna operacja bierze następny pasujący wolny slot przed tłem. Rozpoczęty task kończy się normalnie; nie czeka się na całą partię. Operacja ukryta w buforze, ale nierozpoczęta, nie może omijać tej reguły. Czekanie na emisję, retry lub transfer nie zajmuje zasobu przetwarzania. Zależności i aktualne limity nadal obowiązują. Porządek naturalny nie blokuje pilnego wyniku za niezależną pracą tła. Przy stałym napływie ręcznej pracy tło może czekać; nie obiecujemy równocześnie bezwarunkowego priorytetu i braku zagłodzenia.

## 8. Awarie i regeneracja

**R-019. Problem ma ograniczone ponowienia i widoczny skutek.** Pokazywać etap, przyczynę, zachowane wyniki i następną akcję. Retry klienta i nadzoru nie mnożą swoich budżetów. Brak klucza, uprawnień, miejsca lub uszkodzone wejście wymaga uwagi bez bezowocnego wywoływania usług. Awaria jednego dostawcy nie blokuje niezależnych prac, a jego powrót nie zwalnia lawiny requestów.

Zastój transferu wynika z braku postępu podczas aktywnego pobierania, nie pojedynczego odczytu liczby seedów. Po progu własny zarządzany transfer można wstrzymać; nie usuwać jego danych. Zmiana transferu w cudzej instancji wymaga jawnej zgody. Dostępne są wznowienie, wybór innego wydania i anulowanie konkretnego pobrania. Bez samoczynnego krążenia między wydaniami i restartowania klienta w pętli.

**R-020. Regeneracja jest Auto z żądaniem odtworzenia.** Akcja Regeneruj wybiera odcinki, poprawkę/produkty i opcjonalne ustawienia zastępujące preset tylko dla tego zlecenia. Korzysta z tego samego automatycznego planowania co zwykłe Auto. Różnicą jest jawne odtworzenie wskazanego zakresu mimo istnienia produktów. Można wymusić ponowienie także bez zmiany ustawień. Nie tworzyć `RunMode.REGENERATE`, osobnego planera, pipeline'u ani kolejki regeneracji.

Auto wyznacza minimalną pracę: odtwarza wskazany produkt i wymagane zależne wyniki, a poprawnych niezależnych poprzedników nie wykonuje ponownie. Podgląd poprzedza Start. Przykłady:

| Poprawka | Wymagana logika |
| --- | --- |
| Inny głos/tempo syntezy | Ponowne TTS i zależne audio/eksporty; bez ponownego poprawnego tłumaczenia. |
| Głośność/miks | Obróbka dostępnego zgodnego audio i zależnych eksportów. |
| Poprawa tłumaczenia/tekstu | Odtworzenie wskazanego tekstu i zależnych rezultatów; nie niezwiązanych źródeł. |
| Tylko eksport/kontener | Kompozycja z poprawnych dostępnych wejść. |

Gdy potrzebny pośredni plik został usunięty, podgląd pokazuje konieczność jego odtworzenia, również ewentualnego TTS. Nie obiecywać „tylko miksu”, jeżeli pozostał jedynie gotowy zmiksowany lektor, z którego nie można odzyskać oddzielnego głosu.

Nie usuwać starego poprawnego produktu przed przygotowaniem i zwalidowaniem zastępstwa. Błąd/anulowanie nie niszczą poprzedniej wersji. Publikacja kilku plików może zakończyć się częściowo; taki zestaw nie jest ogłaszany zgodnym nowym kompletem. Musi dać się dokończyć po restarcie. Nie jest wymagany ogólny system wersji mediów.

## 9. Tło, widoczność i odtwarzanie

**R-021. Cicha praca i ikona.** Bez terminala na każdą partię i bez zabierania fokusu. Ikona AniShift w obszarze powiadomień otwiera obecny panel na ekranie Stan. Jej umieszczenie na pasku lub w rozwinięciu zależy od Windows i użytkownika. Menu ikony: Otwórz, Włącz/Wyłącz Auto, Zakończ AniShift. Podpowiedź rozróżnia pracę, oczekiwanie, wyłączone Auto i problem. Restart powłoki nie restartuje zleceń; ikona jest odtwarzana.

**R-022. Jeden ekran Stan.** W obecnym TUI pokazać Auto, skutki wyjątków katalogów, kolejkę, pobrania, subskrypcje, gotowe produkty i problemy. Każda pozycja wyjaśnia, co jest gotowe, co czeka, kiedy nastąpi następna operacja i dlaczego. Dostępne działania kontekstowe: Manual, Auto jednorazowo, Regeneruj, zarządzanie subskrypcją, ponowienie, sterowanie pobraniem, otwarcie folderu. Bez pamiętania CLI. Zachować istniejący wybór źródeł i ustawienia, bez przebudowy marki lub renderera.

**R-023. Powiadomienia tylko o wyniku i potrzebnej decyzji.** Nie o każdym kroku, oczekiwaniu i retry. Gotowy odcinek jest używalny niezależnie od reszty kolejki. Ten sam niezmieniony problem nie powiadamia ponownie po otwarciu panelu lub restarcie. Nowa generacja wyniku może powiadomić ponownie. Wyłączenie powiadomień przez Windows nie oznacza błędu zlecenia.

**R-024. Restart odtwarza zamiar i uzgadnia rzeczywistość.** Zachować zakresy, ustawienia, tożsamości, próby, terminy, blokady i wyniki potrzebne do bezpiecznej kontynuacji. Nie powtarzać potwierdzonych produktów. Po długiej nieobecności wykonać bieżące uzgodnienie, a nie wszystkie pominięte rundy zegara. Aktywne okno wygasłe podczas nieobecności może dostać jedno zapamiętane sprawdzenie powrotne; restart nie odnawia wyczerpanych prób i okien zakończonych przed restartem.

Wyłączone i zakończone subskrypcje pozostają nieaktywne. W uśpieniu/hibernacji lub przy wyłączonym komputerze nie obiecujemy pracy. Po powrocie uzgodnić zegar, dysk i utracone zdarzenia. Autostart jest świadomym ustawieniem i korzysta z obecnego mechanizmu po zalogowaniu.

Zakończ AniShift blokuje nowe starty, zachowuje zamiary i kończy aktualne operacje na bezpiecznych granicach. Własne transfery można zatrzymać do wznowienia; cudzej instancji nie zamykać. Nagłe zabicie procesu to recovery, nie gwarantowane łagodne zamknięcie.

**R-025. Bezczynność usuwa pracę, nie tylko ukrywa okno.** Po uzgodnieniu biblioteki, bez transferów, zmian plików, należnych terminów i poleceń, przy zamkniętym panelu nie rosną liczniki HTTP, uruchomień multimedialnych, pełnych skanów ani inspekcji niezmienionych mediów. Proces czeka na zdarzenia/terminy; nie utrzymuje animacji i bezczynnych zasobów wykonawczych. Historia/log nie rosną od identycznych komunikatów „żyję”.

Rozruch, wznowienie, utrata powiadomień i jawne odświeżenie mogą wymagać porównania biblioteki. Niewspierany nośnik może używać jawnego lekkiego trybu awaryjnego, nie cichego dekodowania wszystkich plików co kilka sekund. Nie obiecujemy zerowego RAM/CPU ani wymyślonych watów. Odbiór wymaga porównania przed/po w tym samym środowisku i bibliotece.

**R-026. Migracja bez fałszywego sukcesu.** Zachować istniejące subskrypcje, foldery, numerację i presety. Dawne `taken` oznacza przekazanie wydania, nie pobranie. Brak dowodu pozostaje niepewnością; migracja nie może masowo pobrać sezonów od początku. Uszkodzony zapis nie staje się pustą listą i nie daje zgody na nowe transfery. Wewnętrzny stan może otrzymać wersję i bezpieczny zapis, ale publiczne formaty mediów i presetów pozostają bez zmian.

## 10. Niezmienniki i granice

**I-001. Wyłączność:** jedna grupa/wersja wejścia ma jednego aktywnego właściciela przetwarzania, niezależnie od sposobu uruchomienia. Regeneracja to nowy jawny zamiar Auto, nie obejście tej ochrony.

**I-002. Prawdziwa gotowość:** wysłane zlecenie i przesunięty kursor nigdy nie zastępują dowodu poprawnego pliku/produktu.

**I-003. Integralność:** spóźniony wynik nie zastępuje nowszego źródła, nieudana przebudowa nie usuwa poprzedniego dobrego pliku, cleanup nie usuwa źródeł ani aktywnych danych.

**I-004. Własność:** tożsamość torrenta/kategoria nie dają prawa do zamykania cudzego klienta lub zmiany jego ustawień.

**I-005. Jawne sterowanie:** subskrypcja nie zmienia Auto, podgląd nie uruchamia pracy, Manual nie przełącza reszty biblioteki, renderer nie wykonuje operacji domenowych.

W zakresie są wszystkie opisane przepływy, również ich migracja, awarie i obsługa w obecnym TUI. Odłożone: automatyczne śledzenie całej franczyzy, samoczynna zmiana grupy lub lepszego wydania i osobne okna partii. Poza zakresem: VPS, chmura, Google Drive, webowy panel, nowy downloader, importer/synchronizacja MAL i kolejne źródła indeksu.

**Bez nowych zależności runtime, osobnego brokera/bazy usługowej, przepisywania rdzenia i zmiany formatów produktów/presetów.** Źródła i trwałe produkty nadal leżą obok siebie w `workspace/` i podfolderach serii; `temp/` pozostaje zarządzanym miejscem danych tymczasowych, `config/` miejscem stanu. Nie dodawać obowiązkowego układu input/output/cache. Kontrola procesu jest lokalna i nie wystawia publicznego API. Obowiązują obecne reguły ochrony sekretów.

## 11. Kryteria akceptacji

ID zachowują ciągłość z poprzednim projektem specyfikacji. Nowe AC-036–042 domykają doprecyzowany model. Brak requestów oznacza rzeczywistą nieobecność żądań, nie tylko ciszę w logu.

| ID | Powiązanie | Obserwowalny wynik |
| --- | --- | --- |
| AC-001 | R-001, R-002, I-001 | Jednoczesne zgłoszenie tej samej pracy z panelu, CLI i watchera daje jedno wykonanie. |
| AC-002 | R-002, R-018 | Podczas LLM i wolnego HTTP nowy plik zostaje zauważony, a sterowanie nie czeka na całą partię/rundę. |
| AC-003 | R-003, I-005 | Włączona subskrypcja przy wyłączonym skutecznym Auto pobiera, ale nie uruchamia obróbki. |
| AC-004 | R-003, R-005 | Wyjątek katalogu respektuje dziedziczenie; Auto jednorazowo nie zmienia przełącznika ani wyjątków. |
| AC-005 | R-004 | Wybrane grupy są chronione podczas edycji; zmiana źródła lub utrata sesji unieważnia podgląd. |
| AC-006 | R-003, R-005 | Po wyłączeniu Auto kończą się rozpoczęte operacje, nowe automatyczne nie startują, Manual działa. |
| AC-007 | R-006 | Zakres od N obejmuje N; sezon 2 nie pobiera sezonu 1; 7.5 nie gubi odcinka 8. |
| AC-008 | R-007, R-014 | Torrent tylko dodany nie jest pobranym odcinkiem; gotowe napisy przy błędzie TTS pozostają gotowe. |
| AC-009 | R-008, R-009 | Przyszła emisja nie powoduje Nyaa przed terminem ani godzinnych odświeżeń znanego kalendarza. |
| AC-010 | R-008 | Data lokalnego pliku/pobrania nie uczy opóźnienia grupy; korekta użytkownika ma pierwszeństwo. |
| AC-011 | R-009 | Przełożenie emisji przesuwa sprawdzenie; null daty nie oznacza teraz; zmiana strefy nie dubluje pracy. |
| AC-012 | R-010 | Brak wydania czeka do następnego terminu; wygasłe okno milczy; późniejszy odcinek działa mimo luki. |
| AC-013 | R-011, R-019 | Zbieżne potrzeby dzielą request; 429 blokuje wszystkie ścieżki; każde retry/304 jest policzone. |
| AC-014 | R-012 | Finał może dotrzeć po końcu emisji w swoim oknie; po zakończeniu subskrypcji nie ma cyklicznego ruchu. |
| AC-015 | R-012, R-013 | Kolejny sezon nie dodaje się sam; usuwanie wpisu/pliku nie uruchamia ukrytego kasowania/pobierania. |
| AC-016 | R-014, R-024 | Restart po przyjęciu torrenta przez klienta uzgadnia go i nie dodaje drugi raz. |
| AC-017 | R-014, R-016 | Pełny rozmiar i stabilność częściowego torrenta nie kwalifikują go do przetwarzania. |
| AC-018 | R-016, I-001, I-003 | Podwójne zdarzenia dają jedną pracę; produkt nie wywołuje Auto; zmienione źródło blokuje stary wynik. |
| AC-019 | R-016, R-017 | Dodanie napisów odblokowuje właściwą grupę bez ponownej inspekcji innych serii. |
| AC-020 | R-018 | Ręczny gotowy task dostaje następny właściwy slot, także przed buforowanym tłem, bez zrywania taska. |
| AC-021 | R-019 | Retry kilku warstw nie mnożą budżetu; niezależne usługi nadal obsługują pracę. |
| AC-022 | R-019 | Pauza, uśpienie i recheck nie naliczają zastoju; wykryty zastój nie tworzy pętli zamian/restartów. |
| AC-023 | R-015, I-004 | Puste sprawdzenie nie startuje qBittorrenta; własny może się zakończyć, cudzy/niepewny pozostaje. |
| AC-024 | R-017, R-020 | Zmiana głosu nie przerabia historii; jawna regeneracja używa Auto i nie powtarza poprawnego tłumaczenia. |
| AC-025 | R-020, R-024, I-003 | Błąd regeneracji zachowuje stary dobry produkt; częściowa publikacja nie udaje zgodnego kompletu. |
| AC-026 | R-021, R-022 | Tło nie otwiera okien; zamknięcie/ponowne otwarcie panelu i restart powłoki nie dublują pracy. |
| AC-027 | R-022, R-023 | Stan wyjaśnia emisję, termin, źródło, wynik i problem; właściwe akcje są dostępne bez CLI. |
| AC-028 | R-023 | Jeden odcinek jest dostępny przed resztą; zablokowane powiadomienia nie zmieniają sukcesu. |
| AC-029 | R-024 | Powrót po wielu terminach daje bieżące uzgodnienie, bez odtwarzania godzin i odnowienia wyczerpanych prób. |
| AC-030 | R-024, R-025 | Utrata zdarzeń/wznowienie odzyskują przeoczony plik i wracają do oczekiwania. |
| AC-031 | R-025 | W ustalonym idle nie przybywa HTTP, uruchomień narzędzi, pełnych skanów i powtórnych inspekcji. |
| AC-032 | R-026 | Migracja taken nie ogłasza niepobranych plików gotowymi i nie rozpoczyna masowego pobierania. |
| AC-033 | R-001, R-026 | Formaty, presety, istniejące zaawansowane Manual i wyszukiwanie pozostają zgodne; brak nowych zależności. |
| AC-034 | R-006, R-008 | Nadchodzący sezon można dodać bez torrenta; termin uruchamia obsługę bez następnego Start. |
| AC-035 | R-006, R-012 | Zamówione zaległości obejmują braki zakresu; zakończony sezon nie zostawia cyklicznych sprawdzeń. |
| AC-036 | R-003, R-013, R-027 | Cztery kombinacje Auto i subskrypcji dają dokładnie wyniki tabeli w sekcji 3. |
| AC-037 | R-004 | Zaznaczenie odcinków 3 i 8, podgląd i Start wykonują tylko ten zakres; bez edycji wszystkich ustawień. |
| AC-038 | R-027 | Dodaj/Wyłącz/Włącz/Usuń działają w panelu; ponowne Włącz nie zeruje historii ani nie dubluje wpisu. |
| AC-039 | R-013, R-027 | Wyłączenie/usunięcie podczas wolnego wyszukania blokuje późniejsze dodanie; wcześniejszy transfer jest zachowany. |
| AC-040 | R-020, R-028 | Ręczna regeneracja innym głosem nie jest cofnięta przez Auto; celowo pominięte produkty nie dorabiają się same. |
| AC-041 | R-020 | Wymuszenie bez zmiany ustawień rzeczywiście przebudowuje zakres przez Auto; zwykłe Auto go pomija. |
| AC-042 | R-002, R-024, I-005 | Stary panel po restarcie nie wykonuje nieaktualnego podglądu; ponowiona zaakceptowana komenda nie dubluje skutku. |
| AC-043 | R-029 | Plik wrzucony do roota po przetworzeniu trafia wraz z produktami do `ready`; regeneracja działa tam bez ręcznego przenoszenia. Kolizja zachowuje oba odcinki, a relokacja nie wywołuje kolejnego Auto. |

Dowód wydajności obejmuje ten sam Windows, bibliotekę i ustawienia przed/po: start, idle, jedną premierę, równoczesne premiery, ręczny plik podczas pracy i powrót po uśpieniu. Mierzyć rzeczywiste żądania według powodu/dostawcy, narzędzia, skany/inspekcje, czas CPU, pamięć i reakcję. Podać czas obserwacji i liczbę plików. Mniejszy ruch nie jest sukcesem, jeżeli pominięto odcinki.

## 12. Przekazanie

Wykonawca realizuje [plan.md](plan.md), nie dopowiada osobnych trybów i systemów. Materiał dla niego jest kompletnym kontraktem zmiany, ale empiryczne bramki Windows, qBittorrent i pomiary pozostają pracą implementacji. Nie ma otwartego wyboru podstawowej architektury. Późniejsza istotna zmiana zachowania wymaga aktualizacji tej specyfikacji i odpowiadającej części planu, nie sprzecznego dokumentu obok.

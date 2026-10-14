# Pozyskiwanie anime — bieżące ustalenia w jednym miejscu

To historyczna synteza badań i ustaleń z 2026-09-22, baseline `0e8a6bf9194d2786d426d3f3a58f48272b3eb087`. Od 2026-09-23 aktywnym punktem wejścia jest [manifest planowania](final/manifest.md), a kontrakt i rekomendacje utrzymują [specyfikacja](final/spec.md), [masterplan](final/masterplan.md), [plan wykonania](final/implementation-plan.md) i [makiety UX](final/ux.md). Poniższa synteza pozostaje materiałem źródłowym; nie stanowi równoległej specyfikacji ani zgody na implementację.

## Co ma dostać użytkownik

- Jedną wyszukiwarkę: tytuł → sezon/część → odcinki. W tym samym miejscu zwykłe pobieranie oraz dodanie subskrypcji emitowanego sezonu.
- Widoczną główną zakładkę **Subskrypcje**: wszystkie aktywne subskrypcje, zarządzanie nimi i wejście do wspólnego wyszukiwania/dodawania. Osobna wyszukiwarka o innym zachowaniu nie jest potrzebna.
- Możliwość pobrania wybranych odcinków także z widoku subskrypcji. Obie drogi korzystają z tego samego wyboru wydań i zlecania transferu.
- Przy subskrypcji: tytuł i sezon, liczba pozyskanych odcinków względem zamówionego zakresu, konkretne numery i stany, kolejna planowana emisja oraz zrozumiały powód oczekiwania albo problemu.
- Odliczanie **do planowanej emisji**, nie obietnicę czasu pojawienia się torrenta. Po emisji bez odpowiedniego wydania: „Czekam na wydanie”. Bez daty: „Termin nieznany”. To proponowane etykiety odpowiadające wyraźnie podanemu rozróżnieniu użytkownika.
- Automatyczne przekazanie pozyskanego pliku do przetwarzania, a wyniku do biblioteki. Pobrane, przetwarzane i gotowe pozostają odrębnymi stanami.
- Automatyczne usunięcie zakończonej subskrypcji z aktywnej listy oraz prostą możliwość ręcznego usunięcia. Szczegółowy warunek zakończenia i skutki usunięcia wymagają jeszcze uzgodnienia.

Użytkownik wyjaśnił, że wcześniejszy problem obejmował niemożność odnalezienia panelu i zrozumienia zarządzania, nie tylko zatrzymany automat. Przepływ ma zostać zaprojektowany od nowa; zachowanie starego UI nie jest wymaganiem.

## Wybór odcinka: co wiemy, co ustalono

1. **Tożsamość najpierw.** Heurystyka zwraca `match`, `mismatch` lub `insufficient_evidence` oraz przyczynę. Nie daje procentowej pewności. W pilocie 159 akceptacji było zgodnych z etykietami po siedmiu korektach tego samego autora; na etykietach historycznych 152 były zgodne, siedem nierozstrzygniętych. Ponadto heurystyka pozostawiła 55 rekordów bez rozstrzygnięcia, poprawnie odrzuciła 15 błędnych i błędnie odrzuciła dwa zgodne. To 231 skorelowanych rekordów z trzech franczyz, nie gwarancja ogólnej skuteczności.
2. **Polski język ma pierwszeństwo.** Użytkownik preferuje polskie napisy lub polskie audio. Typesetting nie może przeważyć nad odpowiednim polskim tłumaczeniem. Wzajemny priorytet pełnego polskiego audio i dialogowych napisów nie został ustalony.
3. **Preferowane 1080p.** Jeżeli brak odpowiedniego 1080p, dopuszczalne jest niższe lub wyższe. Nie przyjęto reguły „najwięcej pikseli wygrywa”. Kolejność zastępczych rozdzielczości pozostaje otwarta.
4. **Rozmiar jest wskazówką, nie dowodem.** Użytkownik podał około 1,4 GB jako przykład swojej intuicji. Nie ustanowił minimum ani limitu. Różne kodeki, źródła i liczba ścieżek utrudniają porównanie; sam większy plik nie dowodzi lepszego obrazu.
5. **Nie wybrano listy grup wydających.** Nieznana grupa nie oznacza błędnego wydania. Polskiego języka nie można dziedziczyć po nazwie grupy lub sąsiednim odcinku.
6. **Heurystyka pozostaje kierunkiem.** Laya zero-shot nie dała przewagi; odłożono ją wraz z kierunkiem Sonarr. Automatyczny typesetting to osobny przyszły temat, nie wdrożona funkcja.

## Jak automat może wybierać bez pytania o każdy plik

Propozycja wynikająca z badań, nie gotowa implementacja:

**Właściwy odcinek → najlepszy kandydat według preferencji i dostępnych wskazówek → uzgodnienie pliku w paczce → pobranie → kontrola zawartości → przetwarzanie.**

Flaga PL i deklaracja paczki służą do wyboru kandydata do sprawdzenia. Nie potwierdzają polskich dialogów w konkretnym pliku. W 159 kandydatach znaleziono 20 polskich flag, w tym dwie deklaracje `[POL]` w kontekście napisów paczki; 17 flag dotyczyło deklarowanej wysokości 1080. Nie znaleziono jawnej deklaracji polskiego audio ani potwierdzenia pełnych polskich dialogów. Sam manifest torrenta także nie pokazuje wewnętrznych ścieżek MKV. Jeżeli późniejsza kontrola wykaże brak PL, potrzebna jest ustalona z góry reguła: przetworzyć przydatną wersję obcojęzyczną czy próbować innego źródła. To nie musi oznaczać pytania człowieka przy każdym odcinku.

Ranking rozstrzyga preferencje, nie mierzy jakości obrazu. Grupa i liczba seedów nie mogą unieważnić stwierdzonej błędnej tożsamości. Brak danych nie powinien udawać potwierdzenia ani automatycznie wykluczać przydatnego wydania.

## Co naprawdę potwierdzono technicznie

- AniList dostarcza katalog i relacje, ani.zip mapowania i odcinki, Torrentio kandydatów do pobrania. Relacje sezonów i dodatków wymagają uporządkowania; nie ma jednego idealnego drzewa franczyzy.
- Pomiary HTTP: ani.zip około 0,085–0,201 s; Torrentio około 0,052–1,834 s. Część wyników pochodziła z cache; to nie czas całej operacji pobrania.
- Heurystyka: około 12,8 ms na 231 rekordów bez I/O. Sortowanie kandydatów jest jeszcze tańsze. To pomiary oddzielnych eksperymentów, nie SLA aplikacji.
- Rzeczywisty qB pobrał syntetyczne E1 i E3 bez ukończenia E2. Wybór i postęp przetrwały łagodne restarty. Indeksy surowego torrenta mogą różnić się od qB przez padding; sam indeks dostawcy nie wystarcza.
- Priorytet zero nie gwarantuje zera odebranych bajtów, ponieważ pliki współdzielą kawałki. `file.progress=1` nie gwarantuje osobnego pliku na dysku. Gotowość wymaga uzgodnienia wybranego pliku i jego rzeczywistej dostępności.
- Zbadany obecny kod subskrypcji ma ograniczenia kalendarzowe, grupowe i widoczności stanu. Nie ustalono konkretnej przyczyny awarii użytkownika. Przyszły projekt nie dziedziczy tych ograniczeń automatycznie.

## Najważniejsze luki do rozstrzygnięcia

| Temat | Co już wiadomo | Co pozostaje do decyzji lub dowodu |
| --- | --- | --- |
| Koniec subskrypcji | Użytkownik chce automatycznego sprzątania aktywnej listy | Rekomendacja: kończyć po pozyskaniu całego zamówionego zakresu, nie po samej emisji finału. Jak traktować nieznaną liczbę odcinków, dodatki i spóźnione wydania? |
| Ręczne usunięcie | Musi być proste i dostępne | Rekomendacja: zatrzymać przyszłe monitorowanie; pozostawić już zlecone transfery, przetwarzanie i pliki. Kasowanie danych to osobna czynność. To rekomendacja, nie zatwierdzony kontrakt. |
| Pamięć po zamknięciu | Nie wolno ponownie zlecać już przyjętej pracy | Usunięcie z aktywnej listy nie musi usuwać potwierdzeń pozyskania. Dokładny zapis stanu dopiero w projekcie. |
| Brak PL | Można znaleźć i przetworzyć wersję obcojęzyczną | Jak długo lub ile kandydatów sprawdzać dla PL, zanim użyjemy tłumaczenia? Bez nieograniczonego pobierania kolejnych pełnych wydań. |
| Sama wskazówka PL | Obecne dane nie potwierdzają polskich dialogów | Czy niepotwierdzona flaga PL ma uzasadniać wybór 720p lub 480p zamiast 1080p bez informacji o PL? Pilot tak porządkował, lecz nie jest to zatwierdzona reguła. Znane napisy signs-only nie powinny dostawać priorytetu pełnego tłumaczenia. |
| Rozdzielczość zastępcza | 1080p jest preferowane, inne dopuszczalne | Kolejność 720p/2160p i traktowanie innych wysokości, upscale oraz nieznanego skanowania. |
| Przed premierą | Wcześniejsza rozmowa dopuszczała subskrypcję zapowiedzianego sezonu | Najnowsza wypowiedź akcentuje nowy, aktualnie emitowany tytuł. Nie uznajemy tego automatycznie za odwołanie wcześniejszej możliwości; potwierdzić przy specyfikacji. |
| Polskie audio | Spełnia priorytet językowy użytkownika | Przy pełnej przydatnej ścieżce można uniknąć tworzenia drugiego lektora; ostateczny rezultat i pomijanie TTS wymagają uzgodnienia. |
| Brak postępu | Chwilowy zastój nie dowodzi martwego źródła | Warunki ponowienia i zastąpienia źródła, zachowanie danych częściowych, czytelne stany oczekiwania. |

## Gdzie są szczegóły

- [Manifest badań](final/manifest.md) — mapa wszystkich zakończonych partii i ich odbiorów.
- [API anime](anime-api-report.md) — możliwości usług, czasy i ograniczenia danych.
- [Heurystyka i Laya](reports/heuristic-laya-validation.md) — porównanie na zamrożonych rekordach.
- [Ranking wydań](reports/release-ranking-validation.md) — zależność sugestii od preferencji.
- [PL i 1080p](reports/polish-1080-selection-validation.md) — kolejne badanie według nowych preferencji; status odbioru w raporcie.
- [Paczki i wybór plików](reports/bundle-file-selection-validation.md) — transfer, indeksy, kompletność i restart.
- [Zastany system subskrypcji](reports/subscriptions-current-state.md) — opis starego kodu, nie docelowego UX.

Skrypty, wejścia i wyniki zabezpieczono w [pakiecie odtwarzalnych dowodów](evidence/README.md). Obejmuje heurystykę, ranking, zapisany wynik Layi, instrumenty paczek i subskrypcji oraz badanie PL/1080p. Lokalne odtworzenie obliczeń nie wymaga historycznych katalogów Temp, modelu ani sieci. Nie jest to ponowne wykonanie transferu qB lub pomiaru GPU. Pakiet jest zapisany w katalogu projektu; nie wykonano commita ani publikacji.

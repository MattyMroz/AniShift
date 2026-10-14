---
kind: research
status: active
date: 2026-10-02
baseline: 200de8a
---

# Kompletnie wyciągnięte wymagania etapu E3 (subskrypcje) oraz otwarte decyzje z dokumentów projektu

## 1. Wstęp i cel opracowania

Niniejszy dokument stanowi pełną syntezę i ekstrakcję wymagań, ustaleńdomenowych, inwariantów, reguł migracji oraz decyzji odłożonych do planu etapu **E3 (subskrypcje)**, pozyskanych z całości dokumentacji architektonicznej i specyfikacyjnej projektu AniShift (`spec.md`, `masterplan.md`, `ux.md`, plany etapu E1 i E2, outcome'y E1/E2 oraz rejestry decyzji).

Celem etapu E3 jest dostarczenie w pełni automatycznego, bezobsługowego mechanizmu subskrybowania nadchodzących odcinków anime. Użytkownik tworzy subskrypcję w systemie (tytuł → sezon → odcinek od punktu odcięcia `t_sub`), a rezydent (`AutomationOwner`) w tle cyklicznie monitoruje czas emisji (AniList), odpytuje źródła kandydatów (Torrentio), ocenia dopuszczalność i ranking wydań (heurystyka H1), pobiera wybrane pliki z paczek (qBittorrent), przechodzi przez opcjonalną kontrolę zawartości (H2) oraz przekazuje je do istniejącego grafu przetwarzania (tłumaczenie, lektor TTS) z publikacją w Bibliotece. Subskrypcja działa automatycznie przez cały sezon i ulega samoczynnemu zakończeniu po pobraniu wszystkich celów.

---

## 2. Tabela wymagań etapu E3 i powiązanych reguł systemowych

W poniższej tabeli zgromadzono wszystkie adresowalne wymagania funkcjonalne, jakościowe, inwarianty, stany oraz reguły domenowe obowiązujące w etapie E3 lub z nim powiązane.

| ID | Treść wymagania (1–2 zdania) | Źródło (plik § / linia) | Status | Uwagi i ewentualne modyfikacje |
| --- | --- | --- | --- | --- |
| **S-01** | `S` na liście odcinków wpisu spełniającego U-10 otwiera szkic subskrypcji (U06) z wyliczonym odcinkiem "od N", datą emisji i notką o zaległych wyemitowanych. | `spec.md` §5.4 / l. 157; `ux.md` U06 / l. 208–235 | Obowiązuje | W E1/E2 klawisz `S` wyświetlał wyłącznie informację o braku nowej subskrypcji. W E3 aktywuje formularz U06. |
| **S-02** | Wyemitowane odcinki sprzed momentu dodania subskrypcji są pobierane automatycznie przez subskrypcję. | `spec.md` §5.4 / l. 158; `e1-przeplyw-subskrypcji.md` §7 / l. 397 | USUNIĘTE | Zastąpione regułą W-b / U-09: subskrypcja obejmuje wyłącznie nowe odcinki (`airingAt > t_sub`). Zaległe pobiera się ręcznie (`D`). |
| **S-03** | Zakładka Subskrypcje pokazuje wszystkie aktywne subskrypcje w kolejności: najpierw z problemem, potem wg najbliższej emisji, bez terminu i wstrzymane na końcu. | `spec.md` §5.4 / l. 159–161; `ux.md` U07 / l. 236–262 | Obowiązuje | Pozycja wiersza tyka co sekundę (odliczanie); lista zmienia kolejność po emisji lub zmianie stanu, nie co sekundę. |
| **S-04** | Nad listą subskrypcji widoczna jest akcja "Dodaj subskrypcję" (`D`), otwierająca wyszukiwarkę Anime (U01). | `spec.md` §5.4 / l. 162; `ux.md` U07 / l. 239 | Obowiązuje | Pierwszy stały wiersz na liście subskrypcji. Po dodaniu powrót do podświetlonej nowej subskrypcji. |
| **S-05** | Enter na subskrypcji otwiera jej szczegóły (U08) z odcinkami zakresu, ich stanami, wynikiem ostatniego sprawdzenia i listą dodatków `S...`/OVA. | `spec.md` §5.4 / l. 163–165; `ux.md` U08 / l. 263–285 | Obowiązuje | Pozwala uruchomić `W` (wstrzymaj), `F` (szukaj teraz), `X` (usuń) lub pobrać zaległości z widoku U03. |
| **S-06** | "Szukaj teraz" (`F`) wykonuje natychmiastowe pojedyncze sprawdzenie podświetlonej/otwartej subskrypcji i pokazuje podsumowanie wyniku. | `spec.md` §5.4 / l. 166; `ux.md` U07 / l. 259 | Obowiązuje | Zmieniono zakres: dotyczy tylko podświetlonej/otwartej subskrypcji (dawniej sprawdzało wszystkie subskrypcje naraz). |
| **S-07** | Wstrzymaj (`W` / Space) zatrzymuje nowe zlecenia danej subskrypcji; trwające pobrania i przetwarzanie są kontynuowane. | `spec.md` §5.4 / l. 167; `ux.md` U07 / l. 259 | Obowiązuje | Zegary i czas do emisji biegną nadal. |
| **S-08** | Delete (`Del` / `X`) usuwa subskrypcję natychmiast bez pytania i kończy monitoring; `Ctrl+Z` na liście przywraca usuniętą subskrypcję z jej zakresem. | `spec.md` §5.4 / l. 168; `ux.md` U07 / l. 259 | Obowiązuje | Trwałe pliki na dysku, trwające pobrania i przetwarzanie NIE są usuwane przy usuwaniu subskrypcji. |
| **S-09** | Zakończona subskrypcja (U-11) znika z listy subskrypcji, a w Historii pojawia się wpis podsumowujący. | `spec.md` §5.4 / l. 165; `ux.md` U07 / l. 260 | Obowiązuje | Tworzona jest notatka w Historii: "Subskrypcja zakończona: tytuł, sezon, pobrano y/y". |
| **S-10** | Użytkownik może edytować parametr "od N" w istniejącej subskrypcji. | `spec.md` §5.4 / l. 166; `e1-przeplyw-subskrypcji.md` §7 / l. 398 | USUNIĘTE | Zakres wynika sztywno z punktu odcięcia `t_sub` i `n_cut`. |
| **S-11** | Globalna pauza Auto (`O`) wstrzymuje nowe zlecenia wszystkich subskrypcji ze stałą informacją nad listą. | `spec.md` §5.4 / l. 167; `ux.md` U07 / l. 258 | Obowiązuje | Ręczne pobieranie `D` w Anime działa nadal (decyzja D11); pauza dotyczy tylko automatu. |
| **S-12** | Problem pojedynczej subskrypcji nie blokuje pozostałych. Błąd całego monitoringu (np. zapis stanu) wyświetla się w stałym wierszu i ponawia próbę. | `spec.md` §5.4 / l. 168; `ux.md` U07 / l. 258 | Obowiązuje | Pełna izolacja błędów między poszczególnymi subskrypcjami. |
| **S-13** | Każde sprawdzenie subskrypcji generuje zwarty log diagnostyczny; szczegółowa treść decyzji (kandydaci, oceny H1, wybór) trafia do `decisions.jsonl`. | `spec.md` §5.4 / l. 170; `e1-przeplyw-subskrypcji.md` §5.6 / l. 340–357 | Obowiązuje | Rozdzielenie logowania tekstowego (podsumowania) od dowodowego rejestru decyzji w `config/watch/decisions.jsonl`. |
| **S-14** | Po 7 dobach bez zgodnego wydania wysyłane jest powiadomienie systemowe (`tray.notify`), a wiersz pokazuje problem. Szukanie trwa dalej 1x/dobę. | `spec.md` §5.4 / l. 169, U-14 / l. 104; `ux.md` §11 / l. 304 | Obowiązuje | Likwiduje dawne twarde uśmiercanie odcinka po 72 godzinach bez wydania. |
| **S-15** | Aplikacja posiada opcjonalny przełącznik trybu cienia (shadow mode), rejestrujący propozycje decyzji w `decisions.jsonl` bez zlecania pobrań w qBittorrent. | `spec.md` §5.4 / l. 171; `e1-przeplyw-subskrypcji.md` §5.5 / l. 332–335 | Obowiązuje | Służy do kalibracji parametrów P-2/P-5 w warunkach produkcyjnych; nie jest bramką wdrożenia. |
| **M-01** | Przeniesienie starych subskrypcji: stara subskrypcja staje się subskrypcją nowego wpisu; gdy ma należne cele sprzed migracji, startuje jako **wstrzymana**. | `spec.md` §5.6 / l. 194–196; `e1-przeplyw-subskrypcji.md` §3.2 / l. 62–72 | Obowiązuje | Zapobiega masowemu, niespodziewanemu pobieraniu starych celów zaraz po aktualizacji aplikacji (reguła W-f). |
| **M-02** | Odcinki oznaczone w starej subskrypcji jako przekazane (`taken`) są traktowane jako zlecone (U-16) i nie są pobierane ponownie. | `spec.md` §5.6 / l. 197; `e1-przeplyw-subskrypcji.md` §3.2 / l. 62 | Obowiązuje | Pamięć zlecenia chroni przed powtórnymi pobraniami tego samego odcinka. |
| **M-03** | Stara subskrypcja zakończona z brakami staje się subskrypcją **wstrzymaną** z opisem braku ("Wznów, aby pobrać"). | `spec.md` §5.6 / l. 198; `e1-przeplyw-subskrypcji.md` §3.2 / l. 62–64 | Obowiązuje | Pobiera wyłącznie zaległości będące celami po `t_sub`. |
| **M-04** | Stara subskrypcja zakończona z kompletem pobrań nie pojawia się na liście aktywnych. | `spec.md` §5.6 / l. 199 | Obowiązuje | Stare ukończone subskrypcje są filtrowane. |
| **M-05** | Stara subskrypcja bez rozpoznawalnego wpisu AniList pojawia się na liście z problemem "Nie rozpoznano sezonu — usuń i dodaj ponownie". | `spec.md` §5.6 / l. 200 | Obowiązuje | Wymaga interwencji użytkownika. |
| **M-06** | Trwające stare pobrania kończą się po staremu i są przetwarzane z ustawieniami z chwili przekazania. | `spec.md` §5.6 / l. 201; `e2-pobieranie.md` §8.3 / l. 210–211 | Obowiązuje | Nowe zasady priorytetów nie zerują ani nie psują starych transferów legacy. |
| **M-07** | Przed pierwszym zapisem w nowym formacie powstaje kopia obu plików stanu (`state.json` i `subscriptions.json`) obok oryginałów (`.bak`). | `spec.md` §5.6 / l. 202; `e2-pobieranie.md` §8.3 / l. 212–218 | Obowiązuje | Jeśli kopia się nie powiedzie, zapis nowego schematu 3 zostaje zablokowany. |
| **U-01** | Jedna droga wyboru: tytuł → sezon → odcinki → Pobierz lub Subskrybuj. Znikają grupy wydające z UI i kodu. | `spec.md` §4 / l. 90 | Obowiązuje | Zastępuje stary model grup wydań. |
| **U-02** | Katalog: AniList + ani.zip; kandydaci wyłącznie z Torrentio. Nyaa jest wycofana w E3/E5 z roli źródła świeżych odcinków. | `spec.md` §4 / l. 91–92; `e1-przeplyw-subskrypcji.md` §5.1 / l. 234–242 | Obowiązuje | Potwierdzone pilotem historycznym: Torrentio ma pokrycie 100% świeżych celów. |
| **U-03** | Tożsamość kandydata rozstrzyga heurystyka H1. W subskrypcji wydanie `niepewne` jest dopuszczone tylko wg twardych warunków §3.3. | `spec.md` §4 / l. 93; `e1-przeplyw-subskrypcji.md` §3.3 / l. 80–89 | Obowiązuje | Automat w subskrypcji bierze `niepewnego` tylko przy braku `zgodnego`, po odczekaniu `T_niepewny` i przy zgodnym numerze. |
| **U-04** | Ranking zgodnych kandydatów: klasa rozdzielczości (U-05) → flaga PL → MultiSub → NF/CR → seedy. | `spec.md` §4 / l. 94 | Obowiązuje | Jakość obrazu (1080p) wygrywa z niższą rozdzielczością (720p) posiadającą polskie napisy. |
| **U-05** | Klasy rozdzielczości: 1080p → 2160p → 720p → pozostałe → nieznana. | `spec.md` §4 / l. 95 | Obowiązuje | 720p pobierane jest tylko w ostateczności przy braku wyższych rozdzielczości. |
| **U-06** | Kandydaci w kontenerach nieobsługiwanych przez graf (np. mp4, avi, ts) są pomijani. | `spec.md` §4 / l. 96 | Obowiązuje | Zapobiega pobieraniu plików, których lektor/przepływ nie potrafi przetworzyć. |
| **U-07** | Rzeczywisty język i ścieżki napisów sprawdzane są w pliku po pobraniu. | `spec.md` §4 / l. 97 | Obowiązuje | Deklaracja PL z nazwy nie zwalnia z inspekcji ścieżek kontenera. |
| **U-08** | Lektor powstaje zawsze (nawet przy polskim dubbingu). W subskrypcji limit 3 automatycznych prób zamienia limit 2 pobrań z ręcznej ścieżki. | `spec.md` §4 / l. 98; `e1-przeplyw-subskrypcji.md` §3.3 / l. 91–95 | Obowiązuje | Przekroczenie 3 prób ustawia odcinek w stan `wyczerpany` z wysłaniem powiadomienia. |
| **U-09** | Subskrypcja obejmuje jeden sezon i jego zwykłe odcinki wyemitowane po `t_sub`. "Od N" wyliczane, bez edycji. Dodatki wyłączone. | `spec.md` §4 / l. 99; `e1-przeplyw-subskrypcji.md` §3.1 / l. 50–58 | Obowiązuje | Zabezpiecza przed cichym pobieraniem całej historii lub niejednoznacznych OVA. |
| **U-10** | Subskrybować można wpis, który ma jeszcze przyszłe odcinki: "w emisji", "zapowiedziany" lub "przerwa w emisji". | `spec.md` §4 / l. 100 | Obowiązuje | Wpisy ze statusem "zakończony" mają dostępny tylko przycisk Pobierz. |
| **U-11** | Subskrypcja kończy się automatycznie, gdy AniList oznaczy wpis jako zakończony, liczba odcinków jest znana i każdy cel jest spełniony. | `spec.md` §4 / l. 101; `e1-przeplyw-subskrypcji.md` §3.6 / l. 184 | Obowiązuje | Obecność celu w stanie `wyczerpany` blokuje automatyczne zakończenie subskrypcji. |
| **U-12** | Ręczne usunięcie subskrypcji kończy wyłącznie monitoring. Pobrane pliki, trwające transfery i przetwarzanie zostają. | `spec.md` §4 / l. 102 | Obowiązuje | Operacje na dysku są rozłączne od wpisów monitorujących. |
| **U-13** | Czas emisji pochodzi z AniList (`airingSchedule`). ani.zip służy do numeracji i tytułów. Odliczanie liczy czas do emisji. | `spec.md` §4 / l. 103 | Obowiązuje | Daty z ani.zip nie sterują harmonogramem monitoringu. |
| **U-14** | Harmonogram szukania po emisji: co 15 min przez 24 h, co 1 h do 72 h, potem raz na dobę. Powiadomienie po 7 dobach bez wydania. | `spec.md` §4 / l. 104; `e1-przeplyw-subskrypcji.md` §3.1, §4 | Obowiązuje | Likwiduje dawny mechanizm porzucania szukania po 72 godzinach. |
| **U-15** | Odcinek bez znanej daty emisji jest szukany, gdy wpis jest "w emisji"/"zakończony" i jego numer <= wyemitowanym wg AniList. | `spec.md` §4 / l. 105; `e1-przeplyw-subskrypcji.md` §3.1 / l. 59–60 | Obowiązuje | Zapobiega blokowaniu monitoringu, gdy AniList nie ma podanej dokładnej godziny. |
| **U-16** | Zlecony odcinek nie jest zlecany drugi raz (ani przez drugi panel, ani po restarcie), z wyjątkiem jawnego "Pobierz ponownie" (P). | `spec.md` §4 / l. 106 | Obowiązuje | Pamięć zleceń jest trwała w `WatchState.acquisitions`. |
| **U-17** | Z paczki pobierane są tylko pliki zamówionych odcinków oraz ich pliki towarzyszące (sidecary: napisy, audio). Fonty pomijane. | `spec.md` §4 / l. 107 | Obowiązuje | Mniejszy transfer i brak śmiecenia w stagingu. |
| **U-18** | Wskazanie pliku w paczce: unikalna nazwa wideo -> H1 na ścieżkach qB -> U05 (ręczny wybór). Sam `fileIdx` z Torrentio nie wystarcza. | `spec.md` §4 / l. 108 | Obowiązuje | Zapobiega pobieraniu błędnego odcinka ze wspólnego torrenta. |
| **U-19** | Nowe pobrania trafiają płasko do workspace root. Plik automatycznej próby wchodzi do Auto tylko przy trwałym rezultacie `przyjęta`. | `spec.md` §4 / l. 109; `e1-przeplyw-subskrypcji.md` §3.4 / l. 109–113 | Obowiązuje | Plik w toku lub odrzucony nie trafia do Auto. |
| **U-20** | Istniejące subskrypcje użytkownika są przenoszone automatycznie przy pierwszym starcie nowej wersji. | `spec.md` §4 / l. 110 | Obowiązuje | Gwarancja ciągłości pracy bez utraty wpisów. |
| **U-21** | Filmy są widoczne w powiązaniach franczyzy; pobieranie dla filmów po weryfikacji N-04. | `spec.md` §4 / l. 111 | Obowiązuje | Endpoint filmowy Torrentio przetestowany w E1 (N-04 PASS). |
| **U-22** | Kitsu ID sezonu jest zapisywane trwale w subskrypcji przy jej utworzeniu. | `spec.md` §4 / l. 112 | Obowiązuje | Awaria ani.zip nie blokuje już istniejących subskrypcji. |
| **U-23** | Wydanie z samym dubbingiem bez Dual/Multi Audio trafia na koniec listy zgodnych kandydatów. | `spec.md` §4 / l. 115 | Obowiązuje | Zapobiega nakładaniu lektora na dubbing bez oryginalnej ścieżki. |
| **U-24** | "Inne wydania" ukrywają 720p i niżej, jeżeli istnieje chociaż jedno zgodne wydanie 1080p lub 2160p. | `spec.md` §4 / l. 113 | Obowiązuje | Ogranicza szum informacyjny w UI. |
| **U-25** | Kodek (H.264, HEVC, AV1) i pochodzenie (WEB, Blu-ray) nie wpływają na ranking kandydatów. | `spec.md` §4 / l. 114 | Obowiązuje | Ranking opiera się na rozdzielczości, językach i seedach. |
| **Q-01** | Renderowanie panelu nigdy nie wykonuje operacji I/O, sieci ani zapisu stanu. | `spec.md` §6 / l. 212 | Obowiązuje | Każdy odczyt sieciowy działa w tle na dedykowanym wątku/interwale. |
| **Q-02** | Zapytania do zewnętrznych API podlegają ścisłym limitom: jedno AniList na wyszukanie, jedno ani.zip na wpis, jedno Torrentio na odcinek. | `spec.md` §6 / l. 213–215 | Obowiązuje | Zapobiega blokadom IP oraz nakładaniu limitów. |
| **Q-03** | Odpowiedzi ani.zip i franczyzy są ponownie używane przez czas z nagłówka `Cache-Control` (domyślnie 15 min). Odpowiedzi Torrentio nie są buforowane w AniShift. | `spec.md` §6 / l. 215 | Obowiązuje | Torrentio samo buforuje wyniki do 1h. |
| **Q-04** | Zapytania do API zewnętrznych podlegają istniejącemu `RequestControl` ze ścisłym przestrzeganiem pauz i ochłodzeń po kodzie HTTP 429. | `spec.md` §6 / l. 215; `e1-przeplyw-subskrypcji.md` §4 / l. 198 | Obowiązuje | Przekroczenie limitów automatycznie wydłuża odstępy zapytań (P-10). |
| **Q-05** | Czasy etapów są mierzone i rejestrowane w wynikach; każde widoczne czekanie posiada czytelny stan i możliwość przerwania (Esc). | `spec.md` §6 / l. 216 | Obowiązuje | Zapewnia pełną responsywność UI. |
| **Q-06** | Komunikaty błędów są zwięzłe, po polsku, bez ścieżek absolutnych, poświadczeń, tokenów ani pełnych URL-i. | `spec.md` §6 / l. 217 | Obowiązuje | Ochrona prywatności i sekretów. |
| **Q-07** | Logowanie odbywa się wyłącznie przez `get_logger(__name__)`; logowane są granice operacji i ponowienia, bez payloadów i tytułów z dysku. | `spec.md` §6 / l. 218 | Obowiązuje | Zgodność ze standardem Loguru w AniShift. |
| **Q-08** | Rozmiar każdej odpowiedzi i zdarzenia IPC jest ściśle ograniczony; listy główne nie przesyłają historii przyjęć ani pełnych list wszystkich subskrypcji. | `spec.md` §6 / l. 219; `e2-pobieranie.md` §8.7 | Obowiązuje | Rezydent zgłasza jawny błąd przy próbie przekroczenia limitu ramki zamiast zrywać połączenie. |
| **I-01** | Zapis stanu trwałego w `WatchState` prowadzi wyłącznie `AutomationOwner`. Panel wysyła polecenia i odbiera widoki. | `spec.md` §7 / l. 223 | Obowiązuje | Jeden właściciel stanu w architekture aplikacji. |
| **I-02** | Zaznaczenie ≠ zlecenie ≠ pobrano ≠ gotowe. Żaden widok nie wylicza jednego stanu z drugiego. | `spec.md` §7 / l. 224 | Obowiązuje | Każdy stan ma niezależny dowód trwały. |
| **I-03** | Odcinek raz zlecony nie jest zlecany ponowie bez jawnej akcji "Pobierz ponownie" (P). | `spec.md` §7 / l. 225 | Obowiązuje |
| **I-04** | AniShift zarządza wyłącznie własnymi torrentami w prywatnym profilu qBittorrent. Usunięcie subskrypcji lub zlecenia nie usuwa mediów z dysku. | `spec.md` §7 / l. 226 | Obowiązuje |
| **I-05** | Nawigacja, zegary, odliczanie, renderowanie, restarty oraz wygaśnięcie Historii nigdy nie tworzą nowych zleceń. | `spec.md` §7 / l. 227 | Obowiązuje |
| **I-06** | Ten sam fizyczny odcinek z dwóch różnych wejść (Pobierz / Subskrypcja / dwa panele) daje dokładnie jedno zlecenie i jeden przebieg Auto. | `spec.md` §7 / l. 228; `e2-pobieranie.md` §8.3 | Obowiązuje | Wspólna bramka deduplikacji w `AutomationOwner`. |
| **I-07** | Niezamówiony plik z paczki, który trafił na dysk przez wspólne kawałki (padding), nie uruchamia przetwarzania Auto. | `spec.md` §7 / l. 229; `e2-pobieranie.md` §8.5 / l. 230–235 | Obowiązuje | Puste i niezamówione pliki są ignorowane przez Auto i czyszczone po zakończeniu paczki. |
| **I-08** | Każda decyzja automatu (wybór wydania, pominięcie, odrzucenie) posiada zapisany trwały powód dostępny w szczegółach odcinka. | `spec.md` §7 / l. 230 | Obowiązuje | Powód trzymany w ledgerze, kopia dowodowa w `decisions.jsonl`. |
| **PR-01..12** | Chronione kontrakty z legacy system (jednokierunkowość, izolacja profilu qB, zachowanie Biblioteki, Kosza, Ctrl+Z, Historii 30 dni/50 pozycji, opcji lektora). | `spec.md` §13 / l. 287–305 | Obowiązuje | Zachowanie stabilności dotychczasowych modułów. |

---

## 3. Decyzje odłożone do planu etapu E3

Dokumentacja projektu jawnie przekazuje wykonawcy etapu E3 szereg decyzji, które zostały odłożone z etapu E1 i E2 do uszczegółowienia w planie E3. Poniżej znajduje się ich pełny wykaz wraz z cytatami i źródłami:

1. **Wczesna eskalacja przy powtarzanym odrzuceniu H2 z tym samym powodem długości:**
   - *Źródło:* `masterplan.md` §E3 (l. 106); `e1-przeplyw-subskrypcji.md` §3.6, §5.4.
   - *Cytat:* „do rozstrzygnięcia w planie E3: wczesna eskalacja, gdy kolejne próby tego samego celu H2 odrzuca z tym samym powodem długości”
   - *Kontekst:* Jeśli automat 3 razy z rzędu wybiera wydania odrzucane przez H2 z powodu rozjazdu długości (np. odcinek podwójny / specjalny), subskrypcja powinna od razu przejść w stan eskalacji/problemu zamiast trwonić kolejne próby.

2. **Dostrojenie otwartych parametrów przepływu subskrypcji (P-1 ... P-10):**
   - *Źródło:* `e1-przeplyw-subskrypcji.md` §4 (l. 185–225).
   - *Zestawienie parametrów:*
     - `P-1` (`T_start`): Opóźnienie pierwszego sprawdzenia po emisji `t_due` (ustalone na 0 h w U-14 / decyzji 2026-09-28; rejestr decyzji potwierdzi realne opóźnienia indeksowania Torrentio).
     - `P-2` (`T_niepewny`): Czas oczekiwania na wydanie `zgodne` przed dopuszczeniem wydania `niepewnego` (konfiguracja tymczasowa 72 h; do dostrojenia na podstawie wpisów w `decisions.jsonl`).
     - `P-3` (`N_prób`): Twardy limit automatycznych prób na dany odcinek celu (ustalony na 3 przez właściciela, W-d).
     - `P-5` (`T_rozdzielczość`): Czas oczekiwania na wydanie 1080p przed dopuszczeniem niższych rozdzielczości (konfiguracja tymczasowa 0 h; do dostrojenia na danych z rejestru).
     - `P-6` / `P-7` / `P-8`: Tolerancje i reżim pracy kontroli zawartości H2 (`T_kontroli` = 30 s limit `ffprobe`).
     - `P-9`: Timeouty prób (`T_metadane` = 600 s na pobranie metadanych z magnetu, `T_zastój` = 30 min zastoju transferu).
     - `P-10`: Harmonogram rzednienia odpytań U-14 w reakcji na ewentualne limity HTTP 429 z Torrentio.

3. **Wybór mechanizmu zastępczego dla fallbacku W-08 (po wycofaniu Nyaa):**
   - *Źródło:* `masterplan.md` §Nierozstrzygnięte decyzje (l. 173); `spec.md` W-08 / §11.
   - *Cytat:* „Przed E3: co zastąpi fallback po braku tytułu w AniList (D5, spec W-08, UX U01), gdy zniknie stara lista wydań Nyaa? Zachowanie E1 pozostaje rozstrzygnięte; odpowiedź wymaga decyzji właściciela przed usunięciem tej drogi w E3.”

4. **Kompletne wycofanie pomostu `G` z UI oraz wyczyszczenie starych wywołań w UI:**
   - *Źródło:* `masterplan.md` §Etapy E3/E5 (l. 42, 117); `e2-panel-anime.md` D5 (l. 366–368); `e2-pobieranie.md` §8.3.
   - *Kontekst:* W E2 panel Anime ukrył `G` i `S` z paska klawiszy, lecz zaplecze i stany zachowały ich obsługę. Plan E3 ma ostatecznie usunąć powiązania UI ze starą drogą grup Nyaa.

5. **Zasady retencji i rotacji dowodowego rejestru decyzji (`config/watch/decisions.jsonl`):**
   - *Źródło:* `e1-przeplyw-subskrypcji.md` §5.6 (l. 356).
   - *Cytat:* „Rotacja/retencja to temat E3, jeśli w ogóle.”

6. **Weryfikacja trybu cienia (Shadow Mode) i analiza wydań live:**
   - *Źródło:* `spec.md` S-15; `e1-przeplyw-subskrypcji.md` §5.1, §5.5.
   - *Kontekst:* Przełącznik trybu cienia pozwala przetestować maszynę stanów subskrypcji w środowisku produkcyjnym bez wykonywania fizycznych pobrań w qBittorrent, zbierając logi decyzyjne do optymalizacji P-2 i P-5.

7. **Przeniesienie modułu H2 do pakietu `anishift/` (jeśli H2 zostanie wdrożone w E3/E4):**
   - *Źródło:* `masterplan.md` §E3 (l. 106).
   - *Cytat:* „przy przeniesieniu H2 do `anishift/`: odczyt `ffprobe` w `services/media`, reguły w warstwie aplikacji, pętla prób i ponowienie `ffprobe` należą do maszyny stanów; `scripts/tmp/h2_synthetics.py` ma sztywną ścieżkę `DEFAULT_TEMP`, więc przy przeniesieniu do `tests/` zastąpić ją `tmp_path`”

8. **Wdrożenie stanów i pętli prób maszyny stanów w `AutomationOwner`:**
   - *Źródło:* `masterplan.md` §E3; `e1-przeplyw-subskrypcji.md` §3.3.
   - *Kontekst:* Zaimplementowanie trwałych stanów celów subskrypcyjnych (`oczekuje_emisji`, `należny`, `w_próbie`, `spełniony`, `wyczerpany`, `zlecony_ręcznie`) oraz zarządzania ich cyklem życia.

---

## 4. Konflikty, rozbieżności i niejasności między dokumentami

Poniżej zestawiono istniejące sprzeczności i niejasności w zapisach dokumentacji. Zgodnie z wytycznymi skilla `specification` i `research`, konflikty te zostają nazwane i pokazane z odnośnikami do źródeł, **bez arbitralnego rozstrzygania**:

1. **Opóźnienie pierwszeństwa i okno wygasania szukania subskrypcji:**
   - *Wersja A (`spec.md` §3.1 l. 57; PR-03 / dawny kontrakt L:R-010):* Parametry `AutomationPolicy` nakładają 3-godzinne opóźnienie po emisji przed rozpoczęciem szukania, sprawdzanie co 1 h oraz twarde 72-godzinne okno szukania, po którym nieznaleziony odcinek ulega trwałemu uśmierceniu jako brakujący.
   - *Wersja B (`spec.md` U-14 l. 104; `e1-przeplyw-subskrypcji.md` §4 l. 189, §7 l. 413):* Szukanie rusza natychmiast po emisji (`t_due + 0`), co 15 min przez pierwszą dobę, co 1 h do końca 3. doby, a następnie raz na dobę bez twardego końca szukania po 72 h. Po 7 dobach wysyłane jest powiadomienie systemowe, a monitoring trwa nadal.

2. **Automatyczne pobieranie zaległych wyemitowanych odcinków przy dodawaniu subskrypcji:**
   - *Wersja A (`spec.md` dawne S-02 l. 158; L:R-006):* Subskrypcja pozwalała na wybór "od odcinka N" i automatycznie pobierała zaległe wyemitowane odcinki od wskazanego numeru.
   - *Wersja B (`spec.md` U-09 l. 99, S-02 usunięte l. 158; `e1-przeplyw-subskrypcji.md` §3.1 l. 50–58, §7 l. 397):* Subskrypcja obejmuje wyłącznie nowe odcinki wyemitowane po momencie dodania (`airingAt > t_sub`). Zaległe odcinki wyemitowane przed `t_sub` NIE są zlecane przez subskrypcję — użytkownik musi pobrać je ręcznie (`D`). Parametr "Od N" jest nieedytowalny i wyliczany automatycznie.

3. **Dostępność i funkcja klawisza / przycisku `S` (Subskrybuj) w widoku odcinków (U03):**
   - *Wersja A (`spec.md` S-01 l. 157; `ux.md` U03 l. 119–120):* Klawisz `S` na liście odcinków U03 bezpośrednio otwiera formularz szkicu subskrypcji (U06).
   - *Wersja B (`ux.md` U03 l. 120, §14 D5 l. 366–368; `e2-panel-anime.md` D5):* Decyzją D5 w etapie E2 z paska klawiszy zakładki Anime usunięto przyciski `S` i `G`. W E2 naciśnięcie `S` wyświetla notatkę informacyjną. W E3 subskrypcję dodaje się z zakładki Subskrypcje (`D` Dodaj subskrypcję → otwiera wyszukiwarkę U01) LUB klawisz `S` na odcinkach zostanie przywrócony (niejasność jak pogodzić usunięcie `S` w E2 z zapisem spec S-01).

4. **Niejasność źródła czasu emisji (AniList vs ani.zip):**
   - *Wersja A (`spec.md` U-13 l. 103):* Jedynym źródłem czasu emisji sterującym odliczaniem i monitoringiem jest AniList (`airingSchedule`).
   - *Wersja B (`spec.md` §3.3 l. 76; `ux.md` U03 l. 129):* Wartości dat w ani.zip bywają sprzeczne z AniList (różnice od 1 do 20 dni). Aplikacja wyświetla w UI zastępczą datę z ani.zip jako "termin emisji niepotwierdzony (ani.zip)", lecz U-13 zakazuje używania dat ani.zip do sterowania monitoringiem.

5. **Limit automatycznych prób i wymiany wydań w subskrypcji:**
   - *Wersja A (`spec.md` U-08 ścieżka ręczna):* Obowiązuje limit maksymalnie dwóch automatycznych pobrań jednego odcinka bez decyzji użytkownika.
   - *Wersja B (`spec.md` U-08 zaktualizowane l. 98, W-d; `e1-przeplyw-subskrypcji.md` §3.3 l. 91–95):* W subskrypcji obowiązuje limit 3 automatycznych prób celu (`N_prób` = 3). Przekroczenie limitu ustawia odcinek w stan `wyczerpany` i wysyła powiadomienie, blokując dalsze automatyczne próby.

6. **Automatyczne podmienianie wydań w stanie `niepewne`:**
   - *Wersja A (potoczna interpretacja):* Automat po pobraniu wydania `niepewne` szuka dalej i podmienia plik po pojawieniu się wydania `zgodne`.
   - *Wersja B (`e1-przeplyw-subskrypcji.md` W-g l. 28, §3.3 l. 90; `spec.md` P-05 l. 150):* Przyjęte wydanie `niepewne` NIE jest podmieniane automatycznie przez system. Zamiana wydania może nastąpić wyłącznie na skutek świadomej akcji użytkownika "Pobierz ponownie" (P) w interfejsie.

---

## 5. Warunki wyjścia etapu E3 oraz scenariusz odbioru H3

### 5.1 Kryteria wyjścia etapu E3 (zgodnie z `masterplan.md` §Etapy)
- **Testy z symulowanym zegarem (Fake Clock):** Pozytywne przejście testów integracyjnych weryfikujących pełny cykl (emisja odcinka → odpytanie źródła → wybór kandydata → zlecenie pobrania → obsługa braku wydania po 72 h i do 7 dni → autozamknięcie po sezonie → odporność na restarty rezydenta w każdym punkcie → izolacja problemów między subskrypcjami).
- **Migracja danych na kopii rzeczywistego stanu:** Pomyślny test bezstratnego przeniesienia rzeczywistych plików stanu (`state.json` i `subscriptions.json`) na kopii środowiska użytkownika.
- **Scenariusz odbioru H3:** Pomyślne zaliczenie testu ciągłego działania u właściciela przez okres 7 dni.

### 5.2 Scenariusz odbioru H3 (zgodnie z `ux.md` §12.3 oraz `spec.md` §14)
1. **Tworzenie subskrypcji:** W zakładce Subskrypcje użytkownik wybiera `D` (Dodaj), wyszukuje tytuł w emisji w U01, wciska `S` w U03 i zatwierdza w szkicu U06. *Oczekiwany rezultat:* Szkic pokazuje wyliczony odcinek "Od odc.",notkę o wyemitowanych; nowy wpis pojawia się na liście subskrypcji z zegarem odliczającym czas do emisji; wyemitowane odcinki sprzed `t_sub` nie są pobierane automatycznie.
2. **Weryfikacja zmigrowanych starych subskrypcji:**
   - Subskrypcje aktywne bez należnych celów sprzed migracji pozostają aktywne.
   - Subskrypcje aktywne posiadające należne cele sprzed migracji startują jako **wstrzymane** i niczego nie pobierają przed wciśnięciem "Wznów" (`W`), a po wznowieniu pobierają wyłącznie cele powiązane z okresem (M-01).
   - Subskrypcje zakończone ze starymi brakami startują jako **wstrzymane** z odpowiednim opisem (M-03).
3. **Cofanie usunięcia:** Usunięcie dowolnej subskrypcji klawiszem `Delete` / `X`, a następnie naciśnięcie `Ctrl+Z`. *Oczekiwany rezultat:* Subskrypcja znika natychmiast bez pytań; po `Ctrl+Z` powraca z zachowaniem swojego stanu i zakresu; pliki mediów na dysku pozostają nietknięte.
4. **Próba 7 dni bez interwencji (bez dotykania aplikacji):** *Oczekiwany rezultat:* Nowo wyemitowane odcinki same pojawiają się w Bibliotece po przejściu Auto; subskrypcja zakończonego sezonu ulega automatycznemu usunięciu z listy subskrypcji.

---

## 6. Zakres wyraźnie wyłączony z etapu E3 (Co NIE należy do E3)

Dla zachowania pełnej przejrzystości i uniknięcia rozrastania się zakresu (scope creep), poniżej wymieniono elementy, które **wyraźnie NIE należą do etapu E3**:

### 6.1 Zakres etapu E4 (Kontrola zawartości po pobraniu)
- Rzeczywista inspekcja i rozróżnianie ścieżek napisów (PL vs obce) wewnątrz plików kontenera MKV.
- Automatyczne pomijanie tłumaczenia przy wykryciu pełnych polskich napisów.
- Automatyczna jednorazowa wymiana wydania na kolejne z rankingu w przypadku braku użytecznych napisów (U-08).
- Rozpoznawanie ścieżek "signs-only" (N-05).

### 6.2 Zakres etapu E5 (Sprzątanie i przełączenie)
- Fizyczne usunięcie martwych ścieżek w kodzie (stare zaplecze grup, kategorie Nyaa, nieużywane metody `ResidentSession` takie jak `search`, `download`, `follow`, `validate_deletion`, `order_groups`).
- Usunięcie starej pętli daemona `run_daemon` oraz legacy flag CLI `--resident`.
- Ostateczne usunięcie kodu wyszukiwania wydań na Nyaa (`_group_queries`).
- Końcowa aktualizacja głównych instrukcji (`AGENTS.md`, `README.md`) i scalenie feature branchy do `main`.

### 6.3 Zakres etapu E6 (Biblioteka jako widok tytułów)
- Przebudowa ekranu Biblioteki do układu wzorowanego na ekranie Anime (lista tytułów → Enter → odcinki).
- Masowe zaznaczanie i usuwanie pozycji w Bibliotece.
- Automatyczne rozpoznawanie plików pobranych ręcznie przez AniList.

### 6.4 Pozostałe tematy trwale odłożone lub zakazane (spec §10, §11, §12)
- Pobieranie zaległych wyemitowanych odcinków przez automat subskrypcji (rezerwa dla ścieżki ręcznej P-01..P-05).
- Pobieranie wydań dla filmów (odłożone do czasu pełnej weryfikacji N-04).
- Automatyczne pobieranie dodatków (`S...`, OVA, special) w ramach subskrypcji.
- Automatyczne przechodzenie subskrypcji na kolejny sezon (TV Sequel).
- Synchronizacja konta i stanów obejrzenia z zewnętrznymi serwisami (MyAnimeList, AniList scrobbling, AnimeSchedule).
- Automatyczny typesetting oraz montaż/scalanie napisów z różnych wydań.
- Zewnętrzne menedżery pobierania (Sonarr, Radarr, Prowlarr).
- Używanie modeli językowych / ML do rozpoznawania tożsamości odcinka (Laya).
- Pobieranie całej paczki wieloodcinkowej, gdy zamówiono tylko jej część.
- Modyfikowanie lub usuwanie plików użytkownika poza wyznaczonymi obszarami stagingu AniShift.
- Dotykanie osobistego profilu qBittorrent użytkownika oraz torrentów spoza profilu AniShift.

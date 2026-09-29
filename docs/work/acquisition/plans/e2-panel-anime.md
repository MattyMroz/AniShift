---
kind: plan
status: do-akceptacji-makiet
baseline: 01f5584
branch: work/acquisition/02-download
created: 2026-09-29
parent: e2-pobieranie.md
---

# Panel Anime: od nazwy do pobrania

## Do akceptacji właściciela

Najkrótsza ścieżka lektury: **makiety M03–M13 w §6 po cięciach** oraz
**trzy pytania w §14**. Pozostałe sekcje są kontraktem dla wykonawców.

- Jedna lista premier malejąco, bez grupowania; tylko data emisji.
- Space zaznacza odcinek. D pobiera. I pokazuje wydania z seedami.
- Puste komórki dla domyślnego stanu odcinka i zakończonego wpisu.
- Nieruchoma tabela; stopka to jedna linia informacji i jedna linia
  klawiszy (przy 50 kolumnach dwie linie klawiszy).
- Pytania: zostać po D w odcinkach? Czy C wystarczy do kopiowania?
  Czy rozszerzyć listę franczyzy o filmy powiązane przez `OTHER`?

## 1. Cel i miara sukcesu

Użytkownik wpisuje nazwę, wybiera wpis i odcinek, naciska D. Nie musi
wybierać grupy wydającej ani oglądać podglądu przed zwykłym pobraniem.
Informacje na ekranie służą następnej decyzji lub wyjaśniają wynik akcji.

```text
TERAZ: nazwa -> grupowany katalog -> odcinki -> D -> podgląd E1
       rzeczywiste pobranie jest osobną drogą G
                              |
LUKA: demonstracja E1 i dokładane wyjątki zamiast jednej ścieżki;
      nagłówki/stopki składane przez kilka warstw, zmienna geometria
                              |
CEL: nazwa -> chronologia -> odcinki -> D -> wynik przy odcinkach
     I/P tylko dla świadomego wyboru wydania
```

**Krok** to zatwierdzenie decyzji, nie każdy znak/strzałka. Nazwa+Enter
liczy się jako jeden krok; wskazanie odcinka i D jako jeden. Liczbę ruchów
kursora i czas oczekiwania mierzyć osobno, aby nie ukryć kosztu długiej listy.

| Od pola Anime | Przed: analiza obecnego kodu | Po: projekt |
| --- | --- | --- |
| Jedna franczyza z kilkoma wpisami | Nowa droga: 3 kroki tylko do podglądu, brak pobrania. Działające G: nazwa+Enter → G → Enter grupa → Space wydanie → D = **5** | nazwa+Enter → Enter wpis → D = **3** |
| Niepowiązane wyniki | G: 5 zatwierdzeń; nowa droga 4 do podglądu | nazwa+Enter → Enter tytuł → Enter wpis → D = **4** |
| Jeden wynik i jeden kompletny wpis | G nadal wymaga grupy i zaznaczenia | nazwa+Enter → D = **2** |
| Własne wydanie od listy odcinków | D → Enter/I kończy się odczytem | I → D = **2**, Space opcjonalnie; R-04 dodaje Enter tylko przy odstępstwie |

„Po” oznacza przyjęcie zlecenia, nie ukończenie transferu. Czasy do przyjęcia
i Biblioteki to osobny pomiar Q-05. „Przed” nie jest pomiarem sesji właściciela.

### Warunki końcowe

- [ ] Typowe pobranie w 3 krokach, bez obowiązkowego Space i podglądu.
- [ ] Płaska chronologia: zapowiedzi, nowsze premiery, starsze; typ nie tworzy sekcji.
- [ ] Brak dodatków `S…` na liście odcinków, emisja bez godziny.
- [ ] Zaznaczenia, kursor, wynik i błąd nie zmieniają geometrii tabeli/stopki.
- [ ] Przy 50/80/120 kolumnach widać numer i stan; w wydaniach obraz, język, seedy.
- [ ] D/I/P/U05 korzystają z ownera; rozróżnienie Zlecono/Pobrano/Gotowe ma dowody.
- [ ] Właściciel akceptuje makiety, działającą fixture i osobno odbiór E2.

## 2. Authority i baseline

Review `opus55`: **FAIL z trzema drobnymi uwagami U1–U3**. Niniejsza
korekta usuwa Enter z klawiszy odcinków i P z klawiszy wydań oraz ujednolica
`Space zaznacz`. Zgodnie z decyzją po tych poprawkach plan trafia do
właściciela bez kolejnej rundy review. Akceptacja właściciela pozostaje otwarta.

Najnowszy feedback właściciela i korekta review przekazana w zleceniu mają
pierwszeństwo przed starszymi makietami `ux.md` i wizualnymi fragmentami E2.
Inwarianty bezpieczeństwa `spec.md` pozostają wiążące. D1–D3 z §14 to
propozycje, nie udzielone zgody.

Baseline pierwszego planowania: `ec6a3ae5d9380f47b63e228ae6cb481e96c6d9eb`,
branch jak w metryce; 14 zmienionych
plików śledzonych oraz nowe `application/episode_commands.py` i
`tests/application/test_episode_commands.py`. Są to zmiany F3b, także
`cli/AGENTS.md`, `platform/{AGENTS.md,local_control.py}`, testy i outcome E2.
Przy końcowej kontroli HEAD to `01f5584`; status Git pokazuje już tylko
niniejszy nieśledzony plan. Opisy kodu poniżej pozostają ustaleniami
z baseline planowania; przed implementacją sprawdzić drift. Git zgłasza brak dostępu do siedmiu
starych katalogów pytest pod `workspace/temp/`; nie sprzątać ich.

| Zweryfikowany fakt | Źródło na baseline z F3b | Skutek |
| --- | --- | --- |
| `anime.py` ma 2359 linii, miesza G, katalog, wątki, stan i render | `AnimeController`, `_Screen`, `_render_*` | Podział według odpowiedzialności |
| D nadal woła `_start_offers` | `anime.py:857–875,981–1057` | Zmiana zachowania, nie samej etykiety |
| Zaznaczenia/dodatki/powody zmieniają wysokość | `anime.py:1607–1731,1776–1807` | Stały budżet regionów |
| PANEL, zakładki, Anime, globalny status i stopka katalogu składają się warstwowo | `state.py:1065–1080`, `app.py:_render_frame` | Jedna pełna klatka Anime |
| Franczyza sortowana po grupie, potem premierze rosnąco | `episode_selection.py:franchise_view`, `_entry_order`, `premiere_order` | Zmiana projekcji kolejności |
| Film `OTHER`, np. Scarlet Bond, może nie być widoczny | `_LEAF_RELATIONS`, `_walk`; `outcomes/e1.md:94` | Osobne rozszerzenie P2b, nie poprawka sortowania |
| Wszystkie sześć metod E2 jest w drzewie | `cli/resident.py:291–364` | Reuse API, brak drugiego download |
| Są trzy zdarzenia partii | `automation.py:_run_episode_batch` | Korelacja po command ID i kluczu |
| F3b daje cztery stany, bez pełnego per-odcinek Auto/Gotowe | `_episode_status`; `outcomes/e2.md:593–597` | Mapowanie §8; dalsze stany dopiero F4 |
| Rejestr i kompletne Q-08 pozostają F5 | `outcomes/e2.md:587–597` | UI nie zamyka całego E2 |
| Renderer ma `FormattedTextControl`, mysz przechwytuje m.in. kółko | `prompts.py:_WheelControl`, `TerminalRenderer.__init__` | Drag-select nie jest gotową funkcją widoku |
| Pola używają schowka aplikacji, bez ustawionego systemowego mostu | `text_input.py:_command`, `prompts.py:225–238` | Ctrl+C w polu nie dowodzi kopiowania do Notatnika |

Czytać przed wykonaniem: ten plan → `spec.md` W-/R-/P-/U-/S-/Q- i inwarianty
→ `ux.md` → plan E2 §8.1/8.6–8.9/F6 → końcowe sekcje outcome E2 i N-04
w outcome E1 → scoped AGENTS i wskazane symbole/testy. `masterplan.md`
ma starszy opis postępu; aktualność kodu ustalać z drzewa i outcome.

Dowody planowania: odczyt kodu, kontraktów, testów i Git. Makiety są
projektowane, nie są zrzutami działającego panelu. Bez uruchamiania qB,
produkcji i testów runtime. Historyczny F0 miał znany fail zamknięcia qB;
F3b raportuje 5675 passed/18 skipped bez `integration`, z review oczekującym
w odczytanym outcome. Nie przedstawiać tego jako nowych wyników kontroli.

## 3. Zakres

**W zakresie po akceptacji:** Anime od zapytania do D/I/P/U05, jego klatka,
płaska kolejność istniejących wpisów, zdarzenia i odczyty E2, kopiowanie
według D2, testy wyglądu/interakcji. U05 z Przetwarzania bez przebudowy pasków.
**Warunkowo:** rozszerzenie o filmy `OTHER` wyłącznie P2b po D3 i fixture.

**Poza zakresem:** S/scheduler E3, H1/ranking, transport qB, publikacja F4,
rejestr F5, schema trwałości, redesign innych zakładek, Home, Biblioteka,
Historia, Ręczny, Ustawienia, nowe filtry, tracker obejrzeń.

**Zakazane w tej sesji:** edycje poza tym dokumentem, commit, kod, prawdziwy qB.
**Zakazane w implementacji:** drugi owner/HTTP klient, lokalna historia
przyjęć, obchodzenie dedupe, emisja wywodzona z prezentowanej daty,
mutacje z renderu/nawigacji, zmiana H1 pod listę, zmiana semantyki G.

## 4. Zasady wizualne

### 4.1 Stała klatka

Jeden nagłówek i jedna stopka. Bez PANEL, dodatkowego ANIME, maskotki,
liczników globalnych, wersji i ścieżki workspace w tej zakładce.
Pozostałe zakładki zachowują dotychczasową klatkę.

| Region | Stałe miejsce | Treść |
| --- | --- | --- |
| Nagłówek | wiersz 1 | pełne zakładki, gdy się mieszczą, także przy 50 |
| Nagłówek | wiersz 2 | tytuł/kontekst, bez `/ Wpisy` i `/ Odcinki`; przy I `E3 / Wydania` |
| Nagłówek | wiersz 3 | zapytanie albo rezerwacja zaznaczeń; przy zerze pusta |
| Nagłówek | wiersz 4 | kolumny lub pusta linia |
| Lista | od 5 do początku stopki | przewijany środek, jeden wiersz na pozycję |
| Stopka 80/120 | H−1 | jedna linia informacji: status akcji przed szczegółem |
| Stopka 80/120 | H | jedna linia klawiszy |
| Stopka 50–79 | H−2 | ta sama jedna linia informacji |
| Stopka 50–79 | H−1, H | stałe dwie linie klawiszy |

Pusty wiersz informacji i zaznaczeń nadal zajmuje miejsce. Z zmienia treść
wiersza 3, nie położenie tabeli. Długi szczegół trafia pod `?`, nie tworzy
kolejnych linii stopki. Status ma pierwszeństwo przed szczegółem; trwały
powód pozostaje przypisany do odcinka i dostępny pod `?`, także po odczytaniu
lub zastąpieniu komunikatu akcji. Następna świadoma akcja może usunąć
komunikat sukcesu, ale nie błąd wymagający rozstrzygnięcia.

**Klawisze są stałe dla ekranu/trybu, nie dla wiersza.** Ruch kursora,
zaznaczenie lub event nie zamienia D w P ani nie chowa klawiszy tej linii.
Nieadekwatny skrót daje krótki status, np. `Zlecono | P pobierz ponownie`.
Osobne tryby Z, potwierdzenia R-04 i odzyskiwania wyniku mają własny
stały zestaw. To jawna zmiana interakcji, a nie reakcja stopki na kursor.

Enter nie występuje w linii klawiszy odcinków. Przy problemie pliku linia
informacji brzmi `Nie ustalono pliku w paczce · Enter wskaż plik` i prowadzi
do U05; w innym wierszu Enter daje `Brak pliku do wskazania`.
Enter nigdy nie zaznacza i nie jest ogólnym
„zrób coś”. W M18 jedyną akcją Enter jest nazwane `sprawdź wynik`, bez
wyboru odcinka, U05 ani nowej mutacji z nowym ID. Powrót kończy ten tryb.

`Tab widok`, `C kopiuj`, legenda `* sugerowane` i dodatkowe A/Z/S są pod
`? więcej`. Nie dublować podpowiedzi w statusie i klawiszach. Przy W<50
lub H<10 pokazać `Powiększ terminal do 50 x 10` z działającymi Esc/Tab.
Po resize może zmienić się geometria, po samym klawiszu wyboru — nie.

### 4.2 Kolumny i nazwy

- Płaskie tabele od lewego marginesu, bez ramek i centrowania listy.
- Kursor `>` jest niezależny od `[x]`. Niedopuszczalny wybór: puste miejsce
  checkboxa o tej samej szerokości. Odcinki rosnąco po numerze.
- Domyślny stan wyemitowanego niezleconego odcinka: **pusta komórka Stan**.
  W szczególe, gdy potrzebne, `Nie zlecono`. Jeden rdzeń „zlec-”; etykiety
  stanów zaczynają się wielką literą: `Zlecono`, `Zlecony?`, `Zlecam…`.
- Zakończony wpis: **pusty Status**. Zapowiedź/w emisji pozostają;
  nietypowe statusy przerwy/anulowania też zachowują znaczenie.
- Emisja `DD.MM.RRRR`, bez godziny, także przy 50. Lokalna data z timestampu
  nie zmienia `aired`; data ani.zip nie potwierdza emisji.
- Wpisy: Rok, Tytuł, Typ, Status. Odcinki: znacznik, Nr, Tytuł, Emisja, Stan.
- Wydania: stałe miejsca na kursor, `*` albo `!`, checkbox, Wydanie,
  Obraz, Język, Seedy. `!` ma pierwszeństwo przed `*`; sugestię wyjątku
  opisują szczegóły. Zgodność bez wyjątku nie wymaga pozytywnego komunikatu.
  Wyjątek ma tekst `Niepewne`/`Niezgodne` z powodem w linii informacji;
  jeśli zajmuje ją status, wyjątek nadal wskazuje `!`, a pełny opis jest pod `?`
  i obowiązkowo w R-04 przed skutkiem.
- Plik/rozmiar w jednej linii informacji, pełne dane pod `?`. Nie dodawać
  pola „Źródło”, jeśli nie ma go w DTO. Język jest deklaracją, nie gwarancją.
- Seedy wyrównane do prawej; brak = `?`, zero = `0`; duże liczby skracane
  np. `1.2M`, dokładna wartość pod `?`. Seedy nigdy nie znikają.
- **Jedno obcięcie: `…` wszędzie**, w makietach i produkcji. Żadnych `..`
  lub `...`. Szerokość w komórkach terminala, poprawne CJK/emoji/grafemy.
  Pełne nazwy pozostają w danych dla szczegółu i C.

| Szerokość | Reguła |
| --- | --- |
| 50 | pełny pasek `[Anime]  Subskrypcje  Przetwarzanie  Biblioteka` mieści się; bez `(1/4) < >`. Najpierw skracać tytuł, chronić numer/datę/stan i obraz/język/seedy |
| 80 | te same kolumny, więcej nazwy, stopka klawiszy w jednej linii |
| 120 | więcej nazwy, bez nowych kolumn/dodatkowych informacji |

Jeżeli nazwy zakładek kiedyś przestaną się mieścić, dopiero wtedy zwarty
pasek z bieżącą nazwą i rzeczywistą liczbą zakładek. Kolory z istniejącej
palety tylko wzmacniają tekst; monochromatyczna klatka zachowuje cały sens.

## 5. Przepływ i klawisze

```text
Zapytanie -> [Wyniki, gdy różne franczyzy] -> Wpisy -> Odcinki
Odcinki -> D -> wynik w tych samych wierszach
        -> I -> Wydania -> D -> [R-04] -> Odcinki
        -> P -> Alternatywy -> D -> [R-04] -> Odcinki
        -> Enter wskaż plik (problem pliku) -> U05 -> Enter -> Odcinki
Przetwarzanie -> Enter przy problemie pliku -> U05 -> Przetwarzanie
G -> zachowane grupy -> dotychczasowe D/O
```

### 5.1 Katalog

Zapytanie od razu ma fokus. Jedno pole `Szukaj:`, bez osobnego „Szukaj anime”.
Enter szuka; `/` z wyników/wpisów wraca do zachowanego hasła. Esc wyłącza
edycję, następny wraca do miejsca wejścia; na zapytaniu nie reklamować Esc.

Wyniki pomijać, gdy wszystkie są na widocznej liście franczyzy pierwszego
trafienia. Jeden wynik i jeden kompletny wpis prowadzą od razu do odcinków.
Nie sprawdzać ukrytych `specials` dodatkowym ani.zip tylko dla decyzji
o pominięciu; typ OVA i `specials` nie wymuszają zbędnego ekranu.
Nie pomijać niepełnej listy wpisów ani niepowiązanych wyników.

Chronologia: zapowiedzi bez daty/roku pierwsze, potem znane premiery malejąco
według `premiere_order` (sam rok jak koniec roku); remisy naturalnie po tytule
i ID. Pozostałe bez daty na końcu. Zapowiedź z datą jest w chronologii.
Kursor na wybranym wpisie; przy pominiętych wynikach na pierwszym trafieniu,
nie automatycznie na zapowiedzi. Osobne OVA/special są zwykłymi wpisami.

**Filmy `OTHER` są rozszerzeniem P2b, zależnym od D3.** Preferowana droga:
tylko znane filmy bezpośrednio powiązane z głównym łańcuchem, dołączone
w `franchise_view`, dedupe po AniList ID. Nie zmieniać `_walk`, łańcucha H1,
`identity_target` ani nie dodawać wszystkich `OTHER`/mangi. Fixture Scarlet
Bond musi wykazać dostępność węzła i niezmienność targetu przed implementacją.
Gdy potrzebny jest nowy odczyt/graf, zatrzymać P2b i wrócić po zakres.
Bez zgody D3 zostaje istniejący zbiór wpisów, a film można wyszukać osobno.
Film ma `EpisodeKey(id, 1)` i wiersz `Film`; pozytywne N-04 z outcome E1
pozwala użyć D, o ile konkretny film ma wymagane mapowanie.

G pozostaje dostępne do E3, z dotychczasowym warunkiem kontekstu
(wynik/wpis obecny w wynikach albo odcinki po pominięciu wpisów).
W wynikach/wpisach skrót w stopce jest stały; brak kontekstu daje krótki
status i wskazówkę pod `?`. W odcinkach G jest pod `?`. S do E3 daje tylko
wskazówkę do G, nie obiecuje subskrypcji nową drogą. O w G pozostaje.
Brak tytułu po udanym AniList zachowuje jawny fallback W-08 do Nyaa;
awaria AniList nie uruchamia fallbacku.

### 5.2 Zaznaczenia i D

**Odcinek zaznacza tylko Space.** A wszystkie dopuszczalne/żadne, Z zastępuje
wybór zakresem. Enter nie zaznacza. Linia 3 przy zerze pusta; przy wyborze
`Zaznaczone: 2`, numery dopisać tylko, jeśli mieszczą się w jednej linii.
Pełny zakres pod `?`. Błędny zakres zachowuje wybór; prawidłowy pomija
niedopuszczalne numery z krótkim statusem i szczegółami pod `?`.

D wysyła jedną listę 1–100 kluczy i jeden command ID. Bez zaznaczeń bierze
bieżący odcinek, nigdy następny „w zastępstwie”. Ponad limit: odmowa przed
IPC, bez dzielenia i utraty wyboru. Podczas partii lokalny napis `Zlecam…`
nie dowodzi przyjęcia. Ponowne D nie tworzy nowego ID. Space/A/Z są do
rozliczenia zablokowane; kursor, scroll, szczegóły, Esc/Tab i **odczyt I**
działają. Zatwierdzenie oferty D oraz P czekają na rozliczenie partii;
próba daje `Trwa zlecanie`. Potem odświeżyć stan i zweryfikować dopuszczalność
oraz sesję oferty, zanim zezwoli się na świadome D. Nie zatwierdzać automatycznie.

**Czyścić `[x]` po `episode_result` danego odcinka z `admitted` i ID**, nie
dopiero po całej partii. M07 pokazuje już wyczyszczone E1 i nadal wybrane E3.
W recovery równoważny dowód to odzyskany receipt; niezależne ownerowe
potwierdzenie istniejącego przyjęcia także usuwa niedopuszczalny wybór.
Samo `episode_searching` lub receipt przyjęcia partii niczego nie czyści.
Niezlecone odcinki zachowują wybór i powód; brak sugestii to lokalny wynik
`Brak wydania`, nie nowy trwały stan i nie twierdzenie o pustym źródle.

D1 proponuje pozostanie w odcinkach po D. Gdy właściciel zachowa P-03,
pełny sukces przełącza do Przetwarzania dopiero po rozliczeniu, przy tej
samej generacji; częściowy wynik pozostaje do przeczytania. Brak zgody D1
blokuje implementację zmienionego przejścia, nie resztę projektu.

F3b mapować dokładnie według §8. Brak znanego stanu to `Nieznany`, nigdy
domyślna pusta komórka; mutacje zablokowane do uzgodnienia. Ostatni poprawny
stan można zachować z oznaczeniem nieaktualności. Powody i niepewność nie
giną po strzałce, pozostają pod `?`. Data nie ustala dopuszczalności.

### 5.3 I/P/U05

I dotyczy odcinka pod kursorem, niezależnie od zaznaczeń. Bez pośredniego
OFFER. Space zaznacza jedno wydanie; wybór innego zastępuje poprzedni,
ponowny Space czyści. D bierze wybrane albo bieżące. Dla jednolitości Enter
także w wydaniach nie zaznacza. Brak licznika zaznaczeń w I/P — wystarczy `[x]`.
A/Z nie wybierają kilku wariantów. I zleconego jest odczytem; D daje status
`Zlecono | P pobierz ponownie`, bez zmiany stopki przy ruchu kursora.
P jest dostępne przez ten status i `?`, nie w linii klawiszy wydań.

P: `episode_offer(repeat=True)` z poprzednim admission, jeśli istnieje.
Alternatywy wyklucza owner. `D pobierz ponownie` stanowi zgodę na ponowienie.
`Obecne pliki zostają` i nieznany poprzednik/konflikt są widoczne przed
zatwierdzeniem, przy długim tekście także pod `?`. Nie ukrywać ryzyka
zmianą priorytetu statusu: gdy przesłania je błąd, zatwierdzanie jest
zablokowane do ponownego pokazania oferty. Brak alternatyw nie znosi wykluczeń.

Jawne niepewne/niezgodne wydanie zawsze dostaje osobne R-04 przed skutkiem,
również po P. R-04 pokazuje odcinek, wydanie i faktyczny powód; Enter znaczy
`pobierz mimo to`, Esc wraca. Bez pytania „Wybrać mimo to?” powtarzającego
stopkę. Pełny powód przewijany w środku. Zmiana oferty/konfliktu unieważnia
zgodę. Automatyczna niepewna sugestia D pozostaje dopuszczona bez R-04.

U05: Enter wskaż plik w odcinkach działa wyłącznie przy `episode_file_unresolved`;
z Przetwarzania otwiera ten sam widok. Tylko obsługiwane wideo z pełną
względną ścieżką i rozmiarem. Długie ścieżki dostępne pod `?` przed wyborem.
Enter wybiera dokładne index/path/size z rewizji, sidecary dołącza owner.
Zmiana mapy daje osobny tryb `Enter odśwież`; odświeżenie nie wybiera pliku,
potrzeba następnego świadomego Enter. Powrót do miejsca otwarcia.

### 5.4 Klawisze

| Ekran/tryb | Klawisz | Jedno znaczenie |
| --- | --- | --- |
| Listy | góra/dół, PgUp/PgDn, Home/End | kursor; kółko tylko przewija |
| Bez edycji | Tab/Shift+Tab, lewo/prawo | zakładka z zachowaniem kontekstu |
| Pole | litery/Space/skróty edycji | tekst, nigdy D/A/Z/S |
| Zapytanie | Enter | szukaj niepustego hasła |
| Wyniki/wpisy | Enter; /; G | otwórz; edytuj hasło; stare grupy |
| Odcinki | Space | zaznacz/odznacz, bez zlecenia |
| Odcinki | A; Z | wszystkie/żadne; pole zakresu (Enter stosuje, Esc zamyka) |
| Odcinki | D; I; P | sugestie; odczyt wydań; alternatywy ponowienia |
| Odcinki — problem pliku | Enter | U05; podpowiedź `Enter wskaż plik` tylko w linii informacji, bez problemu pliku krótka odmowa |
| Odcinki | S; G | wskazówka do G do E3; dotychczasowy pomost |
| Wydania | Space; D | jedno zaznaczenie; dokładny wybór |
| R-04 | Enter; Esc | pokazane odstępstwo; powrót bez skutku |
| U05 | Enter | dokładny plik z obejrzanej rewizji |
| Błąd odczytu / nieaktualna oferta/mapa | Enter ponów / odśwież | tylko nazwany odczyt, respektuje cooldown |
| Nieustalony wynik mutacji M18 | Enter sprawdź wynik | replay tego samego ID/payloadu; pozostałe mutacje zablokowane |
| Listy | ? więcej; C | szczegóły i pozostałe skróty; kopiowanie pozycji (D2) |
| Szczegóły | Esc; C; góra/dół | powrót; kopiowanie; przewijanie |
| Wszędzie | Esc / Ctrl+C bez selekcji tekstu | powrót, anulowanie odczytu; nigdy anulowanie przyjętej partii |

Ctrl+C z selekcją tekstu w edytorze nadal kopiuje zamiast wychodzić.
Wszystkie podpowiedzi Enter nazywają akcję; przy problemie pliku podpowiedź
jest w linii informacji, nie w linii klawiszy. Enter bez zdefiniowanej
akcji na danym ekranie niczego nie zmienia. M18 jest trybem całej konkretnej
intencji, więc zmiana kursora nie zmienia znaczenia „sprawdź wynik”.

## 6. Makiety po cięciach

Dane fikcyjne; wszystkie obcięcia używają `…`. Bloki 80 mają 12 wierszy
(4 nagłówka, 6 środka, 2 stopki); bloki 50 mają 13 (4+6+3). Na wyższym
terminalu rośnie tylko środek. Puste końce linii pominięto. 120 zachowuje
układ 80 z większą szerokością tytułu. Opisane podmiany dotyczą obu szerokości.

### M01 — zapytanie

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka

Szukaj: slime_








Enter szukaj
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka

Szukaj: slime_








Enter szukaj

```

### M02 — niepowiązane wyniki

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Wyniki
Szukaj: slime
  Rok   Tytuł                                    Typ   Status
> 2027  Slime Chronicle                          TV    Zapowiedź
  2026  Slime Season 4                           TV    W emisji
  2024  Slime Adventure                          ONA




Enter wybierz | / szukaj | G grupy | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Wyniki
Szukaj: slime
  Rok  Tytuł               Typ  Status
> 2027 Slime Chronicle     TV   Zapowiedź
  2026 Slime Season 4      TV   W emisji
  2024 Slime Adventure     ONA




Enter wybierz | / szukaj
G grupy | ? więcej | Esc
```

### M03 — płaska chronologia wpisów

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime

  Rok   Tytuł                                    Typ   Status
  -     Slime Season 5                           TV    Zapowiedź
> 2026  Slime Season 4                           TV    W emisji
  2024  Slime Season 3                           TV
  2022  Slime: Scarlet Bond                      Film
  2021  Slime Season 2                           TV
  2018  Slime                                    TV

Enter odcinki | / szukaj | G grupy | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime

  Rok  Tytuł               Typ  Status
  -    Slime Season 5      TV   Zapowiedź
> 2026 Slime Season 4      TV   W emisji
  2024 Slime Season 3      TV
  2022 Slime: Scarlet Bond Film
  2021 Slime Season 2      TV
  2018 Slime               TV

Enter odcinki | / szukaj
G grupy | ? więcej | Esc
```

Scarlet Bond pokazuje wariant **po D3/P2b**, nie obecną zawartość grafu.
Bez rozszerzenia lista ma istniejący zbiór wpisów. OVA zajmuje zwykły wiersz
według daty. Niepełna lista: linia informacji `Lista niepełna`. G zostaje
w stopce także przy niedostępnym kontekście; naciśnięcie daje krótki status.

### M04 — odcinki bez zaznaczeń

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)

      Nr  Tytuł                               Emisja      Stan
> [ ]  1  A New Beginning                     01.09.2026
  [ ]  2  The Meeting                         08.09.2026
  [ ]  3  A Promise                           15.09.2026
  [ ]  4  The Council                         22.09.2026
       5  The Next Day                        06.10.2026  Nie wyemitowano


Space zaznacz | D pobierz | I wydania | P ponownie | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)

      Nr Tytuł     Emisja     Stan
> [ ]  1 A New Be… 01.09.2026
  [ ]  2 The Meet… 08.09.2026
  [ ]  3 A Promise 15.09.2026
  [ ]  4 The Coun… 22.09.2026
       5 The Next… 06.10.2026 Nie wyemitowano

A New Beginning
Space zaznacz | D pobierz | I wydania
P ponownie | ? więcej | Esc
```

### M05 — zaznaczone 1 i 3, identyczne miejsca tabeli i klawiszy

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)
Zaznaczone: 2 (1, 3)
      Nr  Tytuł                               Emisja      Stan
  [x]  1  A New Beginning                     01.09.2026
  [ ]  2  The Meeting                         08.09.2026
> [x]  3  A Promise                           15.09.2026
  [ ]  4  The Council                         22.09.2026
       5  The Next Day                        06.10.2026  Nie wyemitowano


Space zaznacz | D pobierz | I wydania | P ponownie | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)
Zaznaczone: 2 (1, 3)
      Nr Tytuł     Emisja     Stan
  [x]  1 A New Be… 01.09.2026
  [ ]  2 The Meet… 08.09.2026
> [x]  3 A Promise 15.09.2026
  [ ]  4 The Coun… 22.09.2026
       5 The Next… 06.10.2026 Nie wyemitowano


Space zaznacz | D pobierz | I wydania
P ponownie | ? więcej | Esc
```

### M06 — Z, osobny tryb edycji

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)
Zakres: 1,3_
      Nr  Tytuł                               Emisja      Stan
  [x]  1  A New Beginning                     01.09.2026
  [ ]  2  The Meeting                         08.09.2026
> [x]  3  A Promise                           15.09.2026
  [ ]  4  The Council                         22.09.2026
       5  The Next Day                        06.10.2026  Nie wyemitowano

Przykład: 1,3,9-12 albo 5-
Enter zastosuj | Esc anuluj
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)
Zakres: 1,3_
      Nr Tytuł     Emisja     Stan
  [x]  1 A New Be… 01.09.2026
  [ ]  2 The Meet… 08.09.2026
> [x]  3 A Promise 15.09.2026
  [ ]  4 The Coun… 22.09.2026
       5 The Next… 06.10.2026 Nie wyemitowano

Przykład: 1,3,9-12 albo 5-
Enter zastosuj | Esc anuluj

```

Błędny zakres zachowuje tryb z `Brak odcinka 30` w informacji i poprzedni
wybór. Limit D: M05 z `Limit: 100 odcinków | Z zmień zakres`, zero IPC.

### M07 — D trwa; odebrano przyjęcie E1, E3 jeszcze nie

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)
Zaznaczone: 1 (3)
      Nr  Tytuł                               Emisja      Stan
       1  A New Beginning                     01.09.2026  Zlecono
  [ ]  2  The Meeting                         08.09.2026
> [x]  3  A Promise                           15.09.2026  Zlecam…
  [ ]  4  The Council                         22.09.2026
       5  The Next Day                        06.10.2026  Nie wyemitowano


Space zaznacz | D pobierz | I wydania | P ponownie | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)
Zaznaczone: 1 (3)
      Nr Tytuł     Emisja     Stan
       1 A New Be… 01.09.2026 Zlecono
  [ ]  2 The Meet… 08.09.2026
> [x]  3 A Promise 15.09.2026 Zlecam…
  [ ]  4 The Coun… 22.09.2026
       5 The Next… 06.10.2026 Nie wyemitowano


Space zaznacz | D pobierz | I wydania
P ponownie | ? więcej | Esc
```

Przed pierwszym wynikiem oba `[x]` zostają, oba stany `Zlecam…`. E1 jest
czyszczone dokładnie po jego `episode_result(admitted)`, nie po końcu partii.
I nadal odczytuje ofertę; D oferty dopiero po rozliczeniu. Próba zmiany
wyboru/nowej mutacji podczas partii: `Trwa zlecanie`. Stopka nie zmienia się.

### M08 — pełny wynik D, propozycja pozostania D1

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)

      Nr  Tytuł                               Emisja      Stan
       1  A New Beginning                     01.09.2026  Zlecono
  [ ]  2  The Meeting                         08.09.2026
>      3  A Promise                           15.09.2026  Zlecono
  [ ]  4  The Council                         22.09.2026
       5  The Next Day                        06.10.2026  Nie wyemitowano


Space zaznacz | D pobierz | I wydania | P ponownie | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)

      Nr Tytuł     Emisja     Stan
       1 A New Be… 01.09.2026 Zlecono
  [ ]  2 The Meet… 08.09.2026
>      3 A Promise 15.09.2026 Zlecono
  [ ]  4 The Coun… 22.09.2026
       5 The Next… 06.10.2026 Nie wyemitowano


Space zaznacz | D pobierz | I wydania
P ponownie | ? więcej | Esc
```

Komórki potwierdzają sukces, nie trzeba powtarzać go w statusie. D nadal
dotyczy zaznaczeń, jeśli są; brak zaznaczeń i zlecony kursor daje krótką
odmowę. P dotyczy kursora. I/P wracają na ten sam odcinek.

### M09 — wynik częściowy

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)
Zaznaczone: 1 (3)
      Nr  Tytuł                               Emisja      Stan
       1  A New Beginning                     01.09.2026  Zlecono
  [ ]  2  The Meeting                         08.09.2026
> [x]  3  A Promise                           15.09.2026  Brak wydania
  [ ]  4  The Council                         22.09.2026
       5  The Next Day                        06.10.2026  Nie wyemitowano

Zlecono 1 · nie zlecono 3 · I wybierz wydanie
Space zaznacz | D pobierz | I wydania | P ponownie | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)
Zaznaczone: 1 (3)
      Nr Tytuł     Emisja     Stan
       1 A New Be… 01.09.2026 Zlecono
  [ ]  2 The Meet… 08.09.2026
> [x]  3 A Promise 15.09.2026 Brak wydania
  [ ]  4 The Coun… 22.09.2026
       5 The Next… 06.10.2026 Nie wyemitowano

Zlecono 1 · nie zlecono 3 · I wybierz wydanie
Space zaznacz | D pobierz | I wydania
P ponownie | ? więcej | Esc
```

Całkowita porażka zachowuje zaznaczenia i przypisane powody. `no_suggestion`
znaczy brak sugestii; szczegół nie może twierdzić, że źródło nie miało
kandydatów. I pozwala zobaczyć rzeczywistą ofertę i wybrać z R-04.

### M10 — I, wydania z seedami

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 / E3 / Wydania

       Wydanie                                    Obraz Język    Seedy
 *[ ]  [Erai-raws] Slime S4 - 03                  1080p MultiSub   312
> [x]  [SubsPlease] Slime S4 - 03                 1080p -          820
  [ ]  [EMBER] Slime S04E03                       2160p PL          45
 ![ ]  Slime - 03                                 1080p -            ?


Plik: Slime S4 - 03.mkv | 1.4 GB
Space zaznacz | D pobierz | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 / E3 / Wydania

       Wydanie       Obraz Język    Seedy
 *[ ]  [Erai-raws] … 1080p MultiSub   312
> [x]  [SubsPlease]… 1080p -          820
  [ ]  [EMBER] S04E… 2160p PL          45
 ![ ]  Slime - 03    1080p -            ?


Plik: Slime S4 - 03.mkv | 1.4 GB
Space zaznacz | D pobierz
? więcej | Esc
```

Kursor na `!`: informacja `Niepewne: brak jednoznacznego sezonu`, bez drugiej
linii. Znany nieobsługiwany format nie ma checkboxa; informacja podaje
odmowę, D bez skutku. Stopka I pozostaje taka sama dla wszystkich wierszy.

### M11 — P, konflikt legacy

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 / E3 / Pobierz ponownie

       Wydanie                                    Obraz Język    Seedy
>*[ ]  [SubsPlease] Slime S4 - 03                 1080p -          820
  [ ]  [EMBER] Slime S04E03                       2160p PL          45




Zlecony? Nie znam poprzedniego wydania. Obecne pliki zostają.
Space zaznacz | D pobierz ponownie | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 / E3 / Pobierz ponownie

       Wydanie       Obraz Język    Seedy
>*[ ]  [SubsPlease]… 1080p -          820
  [ ]  [EMBER] S04E… 2160p PL          45




Zlecony? Wydanie nieznane. Obecne pliki zostają.
Space zaznacz | D pobierz ponownie
? więcej | Esc
```

Zwykłe P: `Obecne pliki zostają`. Dokładny konflikt i ocena wyjątku pod `?`
oraz w R-04 przed skutkiem. Brak alternatyw: `Brak innych wydań` w środku;
D pozostaje w stałej stopce P, ale daje odmowę zamiast omijać wykluczenia.

### M12 — R-04

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 / E3 / Potwierdź wydanie


To wydanie może nie być tym odcinkiem.
[Group] Slime - 03 [1080p]
Powód: brak jednoznacznego sezonu.




Enter pobierz mimo to | Esc wróć
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 / E3 / Potwierdź wydanie


To wydanie może nie być tym odcinkiem.
[Group] Slime - 03 [1080p]
Powód: brak jednoznacznego sezonu.




Enter pobierz mimo to | Esc wróć

```

Mismatch: `Heurystyka: inny materiał.` i faktyczny powód. Po P informacja
`Obecne pliki zostają`, Enter nazwany `pobierz ponownie mimo to`.
Długi powód przewijany, bez osobnej podpowiedzi szczegółów i bez ucięcia
uniemożliwiającego ocenę. Enter dotyczy dokładnie tego wydania/konfliktu.

### M13 — wybór pliku

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 / E3 / Wybierz plik

  Plik                                                            Rozmiar
> Season 4/S04E03 - A Promise.mkv                                  1.4 GB
  Special Edition/S04E03 - A Promise.mkv                           1.6 GB





Enter ten plik to E3 | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 / E3 / Wybierz plik

  Plik                                    Rozmiar
> Season 4/S04E03 - A Promise.mkv          1.4 GB
  Special Edition/S04E03 - A Prom…        1.6 GB





Enter ten plik to E3
? więcej | Esc
```

Wysyłanie: `Wybieram plik…` w informacji, ponowne Enter nie tworzy nowego ID.
Sukces wraca i odświeża ownerowy stan; nie oznacza jeszcze Pobrano.

### M14 — szczegóły i wynik C

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 / E3 / Szczegóły wydania


[Erai-raws] Slime Season 4 - 03 [1080p][MultiSub]
Plik: Season 4/S04E03 - A Promise.mkv
Rozmiar: 1.4 GB | Seedy: 312
C kopiuj | * sugerowane | Tab widok


Skopiowano nazwę wydania
Esc wydania
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 / E3 / Szczegóły wydania


[Erai-raws] Slime Season 4 - 03
[1080p][MultiSub]
Plik: Season 4/S04E03 - A Promise.mkv
Rozmiar: 1.4 GB | Seedy: 312
C kopiuj | * sugerowane | Tab widok

Skopiowano nazwę wydania
Esc wydania

```

To ekran otwarty przez `?`, więc pokazuje dodatkowe skróty i legendę w treści,
nie ponawia `? więcej`. Brak zbędnej oceny „zgodny”, brak źródła spoza DTO.
Z odcinków pokazuje tytuł, rzeczywisty powód, pełny zakres, A wszystkie/żadne,
Z zakres, C, S/G i Tab. C kopiuje pozycję, nie cały ekran pomocy.

### M15 — ładowanie odczytu

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime

  Rok   Tytuł                                    Typ   Status






Wczytuję wpisy…
Enter odcinki | / szukaj | G grupy | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime

  Rok  Tytuł               Typ  Status






Wczytuję wpisy…
Enter odcinki | / szukaj
G grupy | ? więcej | Esc
```

Zapytanie: szkielet M01 z informacją `Szukam tytułu…`. Odcinki/wydania/pliki:
ich docelowy szkielet i `Wczytuję odcinki…` / `Wczytuję wydania…` /
`Wczytuję pliki…`. Zachowane dane zostają podczas refreshu, nie udają świeżej
oferty. Niedopuszczalna akcja daje krótki status, nie zmienia stopki.

### M16 — błąd odczytu, osobny tryb ponowienia

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime

  Rok   Tytuł                                    Typ   Status






AniList nie odpowiada | Spróbuj za 30 s
Enter ponów | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime

  Rok  Tytuł               Typ  Status






AniList nie odpowiada | Spróbuj za 30 s
Enter ponów | ? więcej | Esc

```

Po cooldownie znika wyłącznie termin. Enter wcześniej nie wysyła żądania;
stopka pozostaje stała. ani.zip/Torrentio wskazują właściwe źródło.
Awaria samego harmonogramu zachowuje odcinki: `Brak terminów emisji` w jednej
linii informacji, szczegóły pod `?`, bez fałszywego pustego katalogu.

### M17 — brak mapowania/listy odcinków

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)

      Nr  Tytuł                               Emisja      Stan






Nie znam odcinków tego wpisu
Space zaznacz | D pobierz | I wydania | P ponownie | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)

      Nr Tytuł     Emisja     Stan






Nie znam odcinków tego wpisu
Space zaznacz | D pobierz | I wydania
P ponownie | ? więcej | Esc
```

Szczegół rozróżnia brak mapowania i poprawną pustą listę. D/I/P bez celu
dają odmowę. Pusta oferta I: `Brak wydań w źródle`, bez wniosku o emisji.
Same mismatch nadal widoczne zgodnie z R-04. Brak wyników AniList prowadzi
do zachowanej drogi Nyaa z jednym statusem, nigdy po awarii katalogu.

### M18 — wynik mutacji nieznany, Enter tylko sprawdza tę intencję

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)
Zaznaczone: 2 (1, 3)
      Nr  Tytuł                               Emisja      Stan
  [x]  1  A New Beginning                     01.09.2026  Nieznany
  [ ]  2  The Meeting                         08.09.2026
> [x]  3  A Promise                           15.09.2026  Nieznany
  [ ]  4  The Council                         22.09.2026
       5  The Next Day                        06.10.2026  Nie wyemitowano

Wynik nieznany
Enter sprawdź wynik | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)
Zaznaczone: 2 (1, 3)
      Nr Tytuł     Emisja     Stan
  [x]  1 A New Be… 01.09.2026 Nieznany
  [ ]  2 The Meet… 08.09.2026
> [x]  3 A Promise 15.09.2026 Nieznany
  [ ]  4 The Coun… 22.09.2026
       5 The Next… 06.10.2026 Nie wyemitowano

Wynik nieznany
Enter sprawdź wynik | ? więcej | Esc

```

To stan **Wynik nieznany**, nie deklaracja trwającego sprawdzania.
Enter replayuje to samo command ID/payload; nie zaznacza i nie otwiera U05.
Podczas faktycznego odczytu informacja `Sprawdzam…`, powtórny Enter bez
drugiego żądania. Dopiero potwierdzony przerwany receipt: normalny ekran,
niezlecone pozostają wybrane i mają `Przerwano`, status wskazuje ich numery;
nowe świadome D może dać nowe ID. Po restarcie panelu nie zgadywać dawnego
zakresu, gdy nie zna command ID; odczytać rzeczywiste stany.

### M19 — zmieniona mapa, osobny tryb odświeżenia

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 / E3 / Wybierz plik

  Plik                                                            Rozmiar
> Season 4/S04E03 - A Promise.mkv                                  1.4 GB
  Special Edition/S04E03 - A Promise.mkv                           1.6 GB




Lista plików się zmieniła. Wybierz ponownie.
Enter odśwież | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 / E3 / Wybierz plik

  Plik                                    Rozmiar
> Season 4/S04E03 - A Promise.mkv          1.4 GB
  Special Edition/S04E03 - A Prom…        1.6 GB




Lista plików się zmieniła. Wybierz ponownie.
Enter odśwież | ? więcej | Esc

```

Zmiana oferty/konfliktu: M10/M11 z informacją `Oferta się zmieniła` i tym
trybem odświeżenia; bez automatycznego D. `event_too_large`: ostatnia dobra
tabela, `Widok nieaktualny`, jawny Enter odśwież, mutacje zablokowane.
Nieznany wynik mutacji ma pierwszeństwo: M18, nie ogólne odświeżenie.

**Pauza:** zwykła tabela i zwykła stała stopka M04/M05; po D odmowa ownera
`PAUSED`, informacja `AniShift wstrzymany`. Zero nowego przyjęcia, brak
automatycznego wznowienia/replayu D z nowym ID. Wskazówka wznowienia
w Przetwarzaniu pod `?`. Pauza nie jest komunikatem o awarii źródła.

### M20 — docelowe stany dopiero po F4

80:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)

      Nr  Tytuł                               Emisja      Stan
       1  A New Beginning                     01.09.2026  Gotowe
       2  The Meeting                         08.09.2026  Przetwarzanie
       3  A Promise                           15.09.2026  Pobrano
       4  The Council                         22.09.2026  Pobieranie
>      5  Another Promise                     29.09.2026  Zlecony?
       6  The Next Day                        06.10.2026  Nie wyemitowano

Space zaznacz | D pobierz | I wydania | P ponownie | ? więcej | Esc
```
50:
```text
[Anime]  Subskrypcje  Przetwarzanie  Biblioteka
Slime Season 4 (2026)

      Nr Tytuł     Emisja     Stan
       1 A New Be… 01.09.2026 Gotowe
       2 The Meet… 08.09.2026 Przetwarzanie
       3 A Promise 15.09.2026 Pobrano
       4 The Coun… 22.09.2026 Pobieranie
>      5 Another … 29.09.2026 Zlecony?
       6 The Next… 06.10.2026 Nie wyemitowano
Another Promise
Space zaznacz | D pobierz | I wydania
P ponownie | ? więcej | Esc
```

Nie powtarzać konfliktu legacy w informacji, jeśli mówi o nim komórka;
dokładny powód pod `?`. `episode_file_unresolved` daje `Problem` w komórce
i `Nie ustalono pliku w paczce · Enter wskaż plik` w linii informacji.
Enter prowadzi wtedy do U05. Niepewność przyjętego wydania to oznaczenie szczegółu, nie fikcyjny stan
transferu. Przed F4 zamiast tej makiety obowiązuje wyłącznie mapowanie §8.

## 7. Kopiowanie (D2)

Rekomendacja: C kopiuje pełny tytuł wpisu, tytuł wpisu + E<n> + tytuł
odcinka, nazwę wydania albo względną ścieżkę U05. Bez obcięcia/koloru/kursora.
Sukces w jedynej linii informacji `Skopiowano tytuł/nazwę wydania/ścieżkę`;
błąd `Nie udało się skopiować`, bez treści w logach. W polu C jest literą.
Skrót odkrywalny pod `?`, nie w każdej stopce.

`mouse_support=True` przechwytuje mysz, a `FormattedTextControl` nie ma
gotowego zaznaczania renderowanej klatki. D2 pyta, czy kopiowanie pozycji
wystarcza. Jeśli potrzebne zaznaczanie fragmentu: najpierw sprawdzić
Shift+przeciąganie w Windows Terminal (osobno host VS Code). Wyłączenie
`mouse_support` oddaje mysz terminalowi, ale odbiera aplikacyjne kółko;
to materialny kompromis do decyzji, nie cicha zmiana renderera. Pełny model
drag-select odświeżanej klatki nie jest częścią rekomendowanego zakresu.

Rekomendowany helper Windows: `clip.exe`, **stdin jako bajty UTF-16LE
z BOM `FF FE`**, bez `shell=True`, bez tekstu w argumentach, z timeoutem,
poza renderem. Nie polegać na stronie kodowej konsoli ani domyślnym
`text=True`. Test granicy porównuje dokładnie BOM + zakodowane bajty
polskiego/CJK/emoji tekstu. Alternatywa tylko po wykazanej potrzebie:
Win32 `ctypes` i `CF_UNICODETEXT` (UTF-16LE z zakończeniem NUL), bez nowej
zależności. Ostateczny dowód to wklejenie pełnego Unicode do Notatnika;
schowek `get_app()` sam w sobie tego nie dowodzi. Bez eksportu na dysk
i bez zmiany wszystkich edytorów aplikacji przy okazji.

## 8. API E2 i mapowanie stanów

Sygnatury odczytane w F3b (`ResidentSession`):

| API | Użycie |
| --- | --- |
| `episode_download(keys: Sequence[EpisodeKey], *, command_id: str) -> EpisodeBatch` | jedna partia; receipt partii nie oznacza przyjęcia wszystkich odcinków |
| `episode_offer(key, *, repeat=False, previous_admission_id=None) -> EpisodeOfferView` | I/P, także konflikt bez previous admission |
| `episode_choose(offer, candidate, *, command_id, deviation_confirmed=False, conflict_confirmed=False) -> Mapping` | dokładny StreamCandidate i osobne zgody |
| `episode_files(admission_id) -> EpisodeFiles` | rewizja, index/path/size |
| `episode_file_choose(files, selected, *, command_id) -> Mapping` | dokładny obejrzany wybór |
| `episode_states(anilist_id, numbers) -> tuple[EpisodeStatus, ...]` | 1–100 numerów na odczyt, bez katalogowego HTTP |

### 8.1 Mapowanie F3b — zanim F4 da kolejne dowody

| Dane | Komórka Stan | Dopuszczalność |
| --- | --- | --- |
| `not_ordered` + `aired=True` | pusta | zwykłe D/Space/A/Z |
| `not_ordered` + `aired=False` | `Nie wyemitowano` | bez zwykłego pobrania |
| `possibly_admitted` | `Zlecony?` | zwykłe D/Space/A/Z blokowane, jawne P |
| `ordered` | `Zlecono` | bez kolejnego zwykłego D; P |
| `downloaded` | `Pobrano` | bez kolejnego zwykłego D; P |
| `reason=episode_file_unresolved` | `Problem` zamiast bazowej etykiety | pamięć przyjęcia nadal blokuje D; `Enter wskaż plik` w linii informacji |
| inny ownerowy problem | `Problem`, bezpieczny powód pod kursorem/`?` | nie cofa przyjęcia |
| brak potwierdzonego odczytu | `Nieznany` | mutacje do uzgodnienia zablokowane |

Lokalne nakładki konkretnej akcji: `Zlecam…` przed wynikiem, `Nieznany`
przy utracie odpowiedzi, `Brak wydania` po `no_suggestion`, `Przerwano`
dla potwierdzonej niezleconej reszty. Nie są nowymi stanami ledgeru.
Potwierdzone przyjęcie wygrywa nad lokalnym brakiem/nieznanym wynikiem.
`uncertain` pozostaje osobnym oznaczeniem, nie jest aliasem legacy.

**Do F4 ścieżka przyjęcia ma tylko Zlecono → Pobrano.** Nie pokazywać
Pobieranie/Przetwarzanie/Gotowe na podstawie upływu czasu, hasha, procentu
całej paczki ani samego receipt. M20 jest docelowe **po F4**, gdy owner
dostarczy potwierdzoną projekcję per odcinek. Obecne `downloaded` z COMPLETE
całego transferu jest ograniczeniem F3b; nie zgadywać wcześniejszej
gotowości jednego pliku. F4 ma rozliczyć E1 gotowy, gdy E3 paczki nadal trwa.

### 8.2 Ownership i zdarzenia

1. Owner ma trwałe przyjęcia, receipts, mapę plików i prawdę postępu. UI:
   drafty, pozycje, ostatnie snapshoty, pending command ID z payloadem.
   Bez nowej lokalnej trwałości i rekonstrukcji z Historii/JSONL.
2. I/P i choose tym samym katalogowym połączeniem
   `ResidentSession._episode_interaction`, nie ogólnym `command()`.
   Nowa oferta/disconnect/interrupt unieważnia poprzednią. D głównym
   kanałem; odczyt I w trakcie partii nie anuluje D ownera.
3. Esc/Tab usuwa aktualność widoku, nie przyjętą pracę. I/O poza lockiem
   renderu. Zmiana zakładki nie powoduje późnego automatycznego powrotu.
4. `StateController` przekazuje `episode_searching`, `episode_result`,
   `episode_batch` także przy nieaktywnej zakładce Anime. Command ID i klucz
   identyfikują wynik; generacja chroni nawigację. `episode_searching` nie
   czyści wyboru; `episode_result(admitted)` czyści tylko ten odcinek.
   Zdarzenia zduplikowane nie zwiększają liczników. `episode_batch` rozlicza
   partię, ale nie zastępuje trwałego odczytu receipt.
5. Stany aktywnego wpisu czytać poza renderem w porcjach do 100; A/Z nie
   kwalifikują nieodczytanych numerów. Jeden współdzielony refresh na wejściu,
   po istotnym evencie lub reconnect, nie przy każdym tyknięciu zegara.
   Owner ostatecznie rozstrzyga wyścig z drugim panelem.
6. `event_too_large`/odmowa odczytu zachowuje ostatni widok, oznacza jego
   nieaktualność, pozwala na jawny refresh bez pętli. F5 odpowiada za Q-08
   i rejestr, UI nie podnosi limitu ramek ani nie obcina danych w ciszy.
7. Nieznany wynik mutacji: replay identycznego command ID/payloadu.
   Wygaśnięcie oferty bez receipt wymaga ponownego obejrzenia, nie nowego
   automatycznego wyboru. Restart ownera nie wznawia reszty partii. Restart
   panelu bez zapamiętanego ID pozwala odczytać stany, nie wyliczyć z domysłu
   zakres przerwanego polecenia.

F3b musi przejść niezależną weryfikację przed P3. F4 i F5 są bramką finalnego
odbioru, nie warunkiem narysowania fixture. Wcześniejsza integracja F3b nie
oznacza zakończenia drogi do Biblioteki. Backend niepodający procentu nie
uprawnia do wymyślenia paska; Pobieranie wymaga dowodu F4, nie tylko braku
procentu.

## 9. Architektura i mapa plików

```text
interactive/app.py          jeden renderer, pełna klatka Anime
  -> state.py               zakładki, zdarzenia, wejście U05
     -> anime.py            kontroler nowej ścieżki i akcji API
        -> anime_state.py   ulotny stan i wybór
        -> anime_view.py    czysty render
        -> anime_legacy.py  zachowane G
        -> ResidentSession  jedyne wejście do ownera
```

`AnimeController/AnimeResult` pozostają publicznym wejściem. Stan ma
ekran/powrót, stabilne klucze kursora, offset, draft odcinków, jedno wybrane
wydanie, ofertę, rewizję U05 i pending command. Indeksy wyliczać z kluczy,
nie utrzymywać dwóch sprzecznych źródeł wyboru.

Render przyjmuje niemutowalny snapshot, geometrię i czas cooldownu;
zwraca Rich Text i viewport. Bez I/O, własnego zegara i mutacji zaznaczeń.
Jedna reguła geometrii także dla PgUp/PgDn. `StateController` dostarcza
zakładki/pauzę/połączenie jako dane, nie dokleja kolejnej stopki. `app.py`
omija dekoracyjną stopkę `_fit_frame` tylko dla pełnej klatki Anime,
zachowuje końcowe przycięcie i jeden `TerminalRenderer`. Testować cały łańcuch.
G wydzielić bez zmian filtrów, D/O i algorytmów, bez drugiego renderera.

| Operacja | Pliki | Zakres przyszłego wykonania |
| --- | --- | --- |
| MODIFY | `anishift/cli/interactive/anime.py` | nowy przepływ, usunięcie obowiązkowego OFFER |
| CREATE | `anishift/cli/interactive/anime_state.py` | stan ulotny, bez ownerowej logiki |
| CREATE | `anishift/cli/interactive/anime_view.py` | jeden szkielet 50/80/120 |
| CREATE | `anishift/cli/interactive/anime_legacy.py` | zachowane G i powroty |
| MODIFY | `anishift/cli/interactive/{state,app}.py` | eventy, U05, pełna klatka |
| READ ONLY, zmiana tylko przy luce | `interactive/{prompts,text_input,menu,palette}.py` | reuse; C już dociera jako tekst; zmiana myszy wymaga D2 |
| CREATE po D2 | `anishift/platform/clipboard.py` | clip UTF-16LE + BOM |
| MODIFY | `anishift/application/episode_selection.py` | chronologia; rozszerzenie projekcji filmu tylko P2b po D3 |
| READ ONLY | `cli/resident.py`, `application/{automation,episode_commands,acquisition}.py`, `platform/local_control.py` | API F3b–F5, backend integruje jego właściciel |
| MODIFY | `tests/cli/test_{anime_episodes,interactive_anime,interactive_state}.py` | nowe klawisze, G, nawigacja, focus |
| CREATE | `tests/cli/test_anime_view.py`, `tests/platform/test_clipboard.py` | geometria i bajty schowka |
| MODIFY | `tests/application/test_episode_selection.py` | chronologia, warunkowo P2b i niezmienny target |
| MODIFY po akceptacji | spec/ux/masterplan, plan E2, scoped AGENTS | synchronizacja §10 |
| DELETE | brak całych plików | wyłącznie martwe symbole nowej drogi E1 |

Nowe ścieżki są jawnie projektowane. Przed wykonaniem sprawdzić drift
F3b/F4/F5; nie odtwarzać ich pracy ani edytować cudzych zmian przy wydzielaniu.

## 10. Różnica i zmiany kontraktów

**Usuwamy:** grupowanie wpisów, godzinę emisji, odcinkowe `S…`, ruchomą linię
zaznaczeń, dodatkowy OFFER/Enter przed D, podwójne nagłówki/stopki,
rutynowe notki etapów, widoczne domyślne stany i pozytywne oceny zgodności,
licznik zaznaczenia I/P, Enter jako zaznaczenie, sprawdzanie dodatków tylko
dla pomijania ekranu.

**Chronimy:** dedupe, durable receipts/recovery, R-04 oddzielne od P,
wykluczenia poprzedniej pary, binding konfliktu/rewizji, pliki użytkownika,
zakres sąsiada paczki, rozróżnienie zaznaczenia/Zlecono/Pobrano/Gotowe,
legacy jako niepewność, ranking/H1/U-24, `?` versus `0` seedów, limity
partii/IPC, jeden owner/renderer, brak I/O w renderze, powroty i pauzę,
Bibliotekę/Undo/Historię/Home/Ręczny i dowody F4/F5/F7/F8.

Poniższe pliki **teraz pozostają nieedytowane**. Po akceptacji `ux.md`
przejmuje kontrakt, ten plan pozostaje mapą wykonania i dowodów.

| Źródło | Zastępowany zakres |
| --- | --- |
| `ux.md` §1–7, §11, §13–14 | klatka i makiety po cięciach, Space bez Enter, stałe klawisze per ekran, I/P/U05, powroty i recovery |
| `ux.md` H1/H2 | 3 kroki i odbiór 80/50, D1; prawdziwy odbiór Biblioteki pozostaje |
| `spec.md` W-01/W-03–W-06 | fokus, chronologia, puste domyślne statusy, data, brak `S…`, pomijanie; filmy OTHER tylko po D3/P2b |
| `spec.md` R-03–R-06 | pojedynczy szczegół, ocena tylko wyjątku, bez OFFER; R-04 zachowane; `no_suggestion` bez fałszywej diagnozy pustego źródła |
| `spec.md` P-01–P-03/P-05 | tylko Space zaznacza, stała rezerwacja, czyszczenie per wynik; P-03 tylko po D1; jawne P |
| `spec.md` §5.5 | „Nie zamówiono” zastąpić semantycznym „Nie zlecono”, domyślnie pusta komórka; legacy w komórce `Zlecony?`; pełny sens bez zmian; mapowanie F3b/F4 jawne |
| `spec.md` U-21 | pozytywne N-04 z outcome E1; odrębne od rozszerzenia zbioru wpisów OTHER |
| `spec.md` S-01/S-05, `ux.md` U08 | G/S do E3; przyszłe wspólne odcinki też bez informacyjnych dodatków, osobne OVA w chronologii |
| `spec.md` Q-01/Q-02/Q-05/PR-06 | brak zbędnego ani.zip, pomiar do przyjęcia, wyjątek klatki Anime przy zachowanych zakładkach/rendererze |
| plan E2 §6/§8.1, UI §8.6, F6, UI odbioru §11 | ten plan zastępuje wykonanie F6, obejmuje konieczny podział Anime; nie obowiązuje dawny zakaz tej przebudowy |
| plan E2 §8.7–8.9, F3–F5/F7/F8 | zachować API, bezpieczeństwo, backend i dowody; dopisać zależność akceptacji od F4/F5 |
| `masterplan.md`, scoped AGENTS | źródło wykonania UI E2, uzgodnione D1–D3, aktualny routing/podział; bez kopiowania makiet do AGENTS |

## 11. Fazy i bramki

Jeden writer, świeży recenzent innej rodziny: autor → testy → review →
poprawki autora → weryfikacja recenzenta. Prowadzący integruje i sprawdza
dowody. Bez równoległych writerów nad kontrolerem/ownerem. Brief według
`subagent`: baseline, kontrakt, zakres zapisu, zakazy, zależności i dowody.

| Faza | Autor → recenzent | Praca i zakres zapisu | Gate |
| --- | --- | --- | --- |
| P0 — projekt | astra → opus55; właściciel ocenia wygląd | tylko plan; potem prowadzący synchronizuje dokumenty §10 | poprawki U1–U3 po review, bez kolejnej rundy; akceptacja makiet i odpowiedzi D1–D3 przed kodem |
| P1 — pilot klatki | opus55 → astra | nowe state/view, testy renderu, minimalne state/app; bez mutacji backendu | fixture 50/80/120 zgodne z tymi makietami, właściciel widzi stałą geometrię |
| P2 — katalog | astra → opus55 | kontroler, G, kolejność istniejącej projekcji, testy katalogu/legacy | chronologia bez zmiany zbioru wpisów, brak odcinkowych dodatków, powroty i G/O |
| P2b — filmy OTHER, warunkowo | opus55 → astra | po P2 i D3: najpierw fixture, potem wyłącznie projekcja `franchise_view` i test | fixture dowodzi znanego filmu i niezmiennego `identity_target`, bez dodatkowego HTTP/zmiany `_walk`; inaczej stop tej fazy |
| P3 — D/I/P/U05 | astra → opus55 | kontroler/state/eventy, testy CLI/IPC z atrapą qB, zaakceptowane F3b | komplet akcji/recovery, Space/Enter, czyszczenie per wynik; F4/F5 rozliczone przed końcem |
| P4 — kopiowanie i odbiór | opus55 → astra | clipboard/kontroler/testy po D2, poprawki UX zgodne z planem | bajty Unicode i Notatnik, bramki, odbiór fixture |

Jeżeli D3 odrzuca P2b, pominąć ten krok i zamienić role P3/P4 tak, aby
autorzy kolejnych wykonanych faz nadal byli naprzemienni; zapisać w outcome.
Przed kodem `coding` i właściwe referencje/AGENTS, przy review `review`.
Plan nie upoważnia do commita ani prawdziwego qB.

### Checkpointy człowieka

**P0:** M03–M13 w 80 i 50, pytania §14. Przejdź „wpis → odcinek → D”,
„Space 1 i 3 → D”, „I → wydanie”, „P”, „Enter wskaż plik”. Kryterium: czytelny
następny ruch i brak szumu. Odpowiedź `Mxx, rozmiar, akceptuję/zmień, uwaga`.

**P1/P4:** runner fixture na syntetycznym ResidentSession i zapisanych
zdarzeniach, poza bootstrapem/realnym stanem/qB, np. `%TEMP%\opencode\panel_plan\`.
Autor podaje odtwarzalną komendę i dane. Ten sam renderer. Właściciel:
80×24 → 50×24 → 120×24, Space/A/A/Z/Esc/D/I/P, Enter normalny i M18.
I podczas partii czyta, ale D oferty nie zatwierdza do rozliczenia.
W P4 C i wklejenie polskiego/japońskiego tytułu/emoji do Notatnika.
Raport: scenariusz, rozmiar, obserwacja, PASS/FAIL. Fixture nie dowodzi transferu.

## 12. Strategia dowodu

| Kontrakt | Kontrola |
| --- | --- |
| Chronologia | zapowiedź z datą i bez, sezony, film z istniejącego zbioru, OVA, remis, brak daty; expected ID order |
| P2b | oddzielna fixture OTHER przed zmianą; projekcja dodaje tylko dopuszczony film, `identity_target` przed/po identyczny, brak HTTP |
| Stała geometria i stopka | całe `app -> state -> anime`, 50/80/120 × 15/24; 0/1/wiele/0, Z, kursor przez różne stany, błąd, event; stałe kolumny/stopka |
| Enter | Space zaznacza, Enter zwykłego odcinka nie zmienia wyboru; `Enter wskaż plik` tylko przy U05 w informacji; M18 replayuje tę samą intencję niezależnie od kursora; jawne nazwy akcji |
| Długie dane | CJK/emoji/grafemy, długi tytuł/powód, 1000 odcinków, duże seedy/?/0; szerokość komórek ≤ W, wysokość ≤ H, jedno `…`, seedy i wyrównanie `!` |
| Czysty render | ten sam snapshot/czas daje ten sam wynik i stan; granice I/O odmawiają wywołań |
| D przez IPC | prawdziwy kontroler/sesja/owner, atrapy źródła/qB; jeden ID/lista, receipt/przyjęcie, brak OFFER |
| Partia | 1 i 3 bez 2; `[x]` E1 znika po jego wyniku, E3 zostaje; 101 zero IPC; częściowe błędy, duplikaty eventów, Esc/Tab/reconnect, I w trakcie |
| R-04/P | zgodny bez pytania, automatyczny niepewny bez pytania, jawny wyjątek z R-04; zmiana oferty/konfliktu unieważnia zgodę; poprzednie pliki i zakres sąsiada zachowane |
| Dedupe/pauza | drugi panel między odczytem a D, legacy, `PAUSED` po D bez przyjęcia; brak automatycznego wznowienia |
| F3b/F4 | dokładne mapowanie §8.1; przed F4 nigdy Pobieranie/Przetwarzanie/Gotowe; po F4 per-odcinek dowody, nie hash paczki |
| Recovery | utrata odpowiedzi D/choose/file_choose, replay tego samego ID/payloadu, restart ownera bez reszty; bez zmyślonego zakresu po restarcie panelu |
| U05 | rewizja i index/path/size, pełna ścieżka dostępna, zmiana mapy → odświeżenie bez wyboru, potem świadomy wybór |
| G/reszta | dotychczasowe testy D/O/fallbacku, focus/Tab/kółko, Home/Library/Undo/Processing bez nowego renderera |
| Schowek | dokładne bajty `FF FE` + UTF-16LE, brak shell/tekstu w argumentach, timeout/błąd bez sukcesu; wklejenie zewnętrzne |

**Oczekiwane linie renderów pochodzą z makiet PO cięciach w tej wersji**,
nie ze starych snapshotów. Parametryzowane oczekiwane linie wystarczą,
bez nowej biblioteki. Aktualizacja oczekiwań tylko po uzgodnionej zmianie
makiety; oprócz tekstu koordynaty i interakcje. Nie usuwać zabezpieczeń
focusu/generacji/H1/seedów przy zmianie testów starego OFFER/dodatków.

Targeted po utworzeniu nowych plików:

```powershell
uv run pytest -n 0 tests/cli/test_anime_view.py tests/cli/test_anime_episodes.py tests/cli/test_interactive_anime.py tests/cli/test_interactive_state.py tests/platform/test_clipboard.py tests/application/test_episode_selection.py
```

Przed końcem wykonania i autoryzowanym commitem całe bramki:

```powershell
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest
```

Pełny pytest zawiera prawdziwe qB: w tej sesji zakaz, przyszły prowadzący
uruchamia w dopuszczonym oknie E2. Zestaw bez integracji nie zastępuje
pełnej bramki/F7/H2. Znany fail raportować jako FAIL, nie tuszować skipem.
P4 odbiera UX; F7/F8 nadal dowodzą selektywnej paczki E1/E3 bez E2,
restartu, migracji, Biblioteki i odsłuchu. Dla 10 tytułów właściciela
zapisać kroki i ruchy kursora oraz Q-05. Brak odbioru = `PENDING HUMAN`.

## 13. Ryzyka i granica adaptacji

| Ryzyko | Reakcja |
| --- | --- |
| Review zmienia API F3b | przed P3 ponownie odczytać DTO/sygnatury; zmiana recovery/ownership wymaga planu |
| P2b potrzebuje odczytów/grafu H1 | stop P2b, wrócić po zakres; nie dokładać OTHER do `_walk` |
| F4 nie daje stanów per odcinek | brak finalnego gate; wraca do backendu, bez pamięci UI jako obejścia |
| G zmienia działanie po przeniesieniu | poprawić przeniesienie i regresje |
| Dziecko poprawne, cała klatka ma drugi footer | naprawić kompozycję, test `_render_frame` |
| Właściciel wymaga myszy zamiast samego C | rozstrzygnąć D2 i kompromis kółka przed zmianą renderera |
| Wygląd nadal nie odpowiada intencji | wrócić do makiet, nie dodawać wyjątków w kodzie |

Lokalnie: prywatne nazwy/helpery, mechanika fixture i niesemantyczne
dopasowanie po przeniesieniu. Zmiany przejść, liczby kroków, informacji
R-04/P, myszy, zbioru franczyzy, ownership, trwałości lub technologii
wymagają decyzji i aktualizacji planu.

## 14. Pytania do właściciela

**D1. Po D zostać w odcinkach czy przejść automatycznie do Przetwarzania?**
Rekomendacja: zostać, z wynikiem przy odcinkach (M07–M09). Ułatwia wynik
częściowy i następny wybór. Zmienia P-03, więc wymaga zgody. Przy zachowaniu
P-03 pełny sukces przełącza tylko przy niezmienionej generacji, a wynik
częściowy pozostaje do odczytu; makietę przejścia uzgodnić przed kodem.

**D2. Czy C kopiujące pełną pozycję wystarczy, czy potrzebne jest zaznaczanie
fragmentu tekstu myszą?** Rekomendacja: C. Jeśli konieczna mysz, najpierw
sprawdzić Shift+przeciąganie w Windows Terminal. `mouse_support=True`
przechwytuje mysz; wyłączenie oddaje selekcję hostowi, ale usuwa aplikacyjne
kółko. Nie wprowadzać tej zmiany bez rozstrzygnięcia kompromisu.

**D3. Czy rozszerzyć franczyzę o filmy po relacji OTHER, np. Scarlet Bond?**
Rekomendacja: tak, ale wyłącznie osobnym P2b po fixture dowodzącej obecności
filmu i niezmienności H1. To rozszerzenie zbioru, nie konieczny element
sortowania. Przy odmowie pozostaje uporządkowanie obecnego zbioru i osobne
wyszukanie filmu; reszta panelu nie jest blokowana przez P2b.

Nie pytać ponownie o rozstrzygnięte: płaską listę, datę, brak dodatków,
D/I, Space/A/Z i seedy. Akceptacja makiet obejmuje wygląd, nie zastępuje
odpowiedzi na powyższe materialne zmiany.

## 15. Definition of Done i przekazanie

- [ ] Makiety po cięciach i D1–D3 mają akceptację właściciela; uwagi U1–U3 z review rozliczone bez kolejnej rundy.
- [ ] P1–P4 wykonane, P2b wykonane albo jawnie odłożone; F3b/F4/F5 zintegrowane.
- [ ] D zleca, Space wybiera, Enter ma jedną nazwaną akcję; stałe klawisze
  i geometria, dokładne mapowanie stanów, C/mysz według D2.
- [ ] Testy, bramki i odbiory mają konkretne wyniki, bez fałszywych PASS.
- [ ] Dokumenty §10 zgodne, bez konkurencyjnych wersji UX.
- [ ] Odbiór fixture i prawdziwy odbiór E2 rozliczone osobno.

Przekazanie: baseline/stan drzewa, zakres, autor/recenzent/findingi, komenda
fixture i klatki 50/80/120, kroki przed/po, dowody IPC/recovery/geometrii,
wyniki bramek, feedback właściciela i zależności F4/F5/F7/F8. Ta sesja
zmienia wyłącznie dokument; bez kodu, commita i uruchomienia qB.

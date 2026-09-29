---
kind: ux-contract
status: do-akceptacji-właściciela
updated: 2026-09-29
baseline: 0e8a6bf9194d2786d426d3f3a58f48272b3eb087
---

# UX: wybór odcinka, pobieranie i subskrypcje

**Decyzja orkiestratora 2026-09-29, do potwierdzenia:** uproszczenia zapytania, pomijania pojedynczego wpisu, zaznaczeń i szczegółów wydań oraz kontrakt P/komunikatów F6 poniżej. Nagłówek PANEL, liczniki globalne, status U01, „Nie zamówiono” i zaznaczanie wydań pozostają.

## 1. Zasady

- Ten dokument jest jedynym źródłem makiet, przejść i klawiszy tej pracy. Wymagania są w [spec.md](spec.md); kolejność budowy w [masterplan.md](masterplan.md).
- Każdy ekran ma oznaczony etap, w którym powstaje (E1–E3). Ekrany niewymienione (Home, Biblioteka, Ręczny, Ustawienia, paski Przetwarzania) **nie zmieniają się**.
- Dane w makietach są przykładowe. Etykiety w aplikacji są dokładnie takie jak w makietach, chyba że ekran nie mieści tekstu (§14).
- `[x]` = zaznaczone w szkicu, `>` = kursor. Zaznaczenie nigdy nie oznacza zlecenia.
- Każda akcja widoczna w stopce działa klawiszem; skrót literowy nie działa, gdy aktywne jest pole tekstowe.
- Esc wraca o jeden ekran i odtwarza poprzedni kursor, zaznaczenia i przewinięcie, bez ponownego pobierania danych.
- Zlecenie powstaje wyłącznie przez: `D` na odcinkach lub wydaniach (E2), także `D pobierz ponownie` w U04b po P, albo automatycznie dla celu subskrypcji dodanej przez Enter na „Dodaj subskrypcję” (U06). Nawigacja, render, odliczanie, Tab i Esc niczego nie zlecają.

## 2. Przejścia

```text
Home ─ Panel ─┬─ Anime ─ U01 Zapytanie/Tytuły ─ U02 Wpisy ─ U03 Odcinki ─┬─ D ─ dobór i pobranie sugestii           (E2)
              │          └─ G ─ stara lista wydań wg grup (pomost E1–E2, bez zmian)
              │                                                         ├─ I ─ U04b Inne wydania ─ D pobierz     (E2)
              │                                                         ├─ P ─ U04b Alternatywy ─ D ponownie    (E2)
              │                                                         └─ S ─ U06 Szkic subskrypcji             (E3)
              ├─ Subskrypcje ─ U07 Lista ─┬─ D ─ U01 (powrót: U07)                                           (E3)
              │                          ├─ Enter ─ U08 Szczegóły (= U03 w kontekście subskrypcji)          (E3)
              │                          └─ Delete ─ usunięcie od razu; Ctrl+Z cofa                        (E3)
              ├─ Przetwarzanie ─ wiersz z problemem ─ Enter ─ U05 Wybierz plik / U04b Inne wydania          (E2)
              └─ Biblioteka (bez zmian)
```

Po zleceniu widok przechodzi do Przetwarzania z nowymi odcinkami — tylko jeśli użytkownik nadal jest na ekranie i generacji rozpoczęcia. Po „Dodaj subskrypcję” widok wraca do miejsca startu: do U07, jeśli dodawanie zaczęło się z listy subskrypcji, inaczej do U03. E1 pozostaje historycznym etapem odczytowym: D otwierało U04 bez możliwości pobrania.

## 3. U01 — zapytanie i tytuły (E1)

```text
┌────────────────────────────────────────────────────────────────────────┐
│ [Anime]  Subskrypcje  Przetwarzanie  Biblioteka                        │
│                                                                        │
│ Szukaj anime: [slime_____________________________]                     │
│                                                                        │
│  Rok   Tytuł                                        Typ    Status      │
│> —     Slime Isekai Chronicle                       TV     zapowiedź   │
│  2024  That Time I Got Reincarnated as a Slime S3   TV     zakończony  │
│  2022  … the Movie: Scarlet Bond                    Film   zakończony  │
│  2018  That Time I Got Reincarnated as a Slime      TV     zakończony  │
│  2015  Tensei Shitara Slime (manga PV)              ONA    zakończony  │
│                                                                        │
│ Enter wybierz · G grupy · / szukaj · Esc wróć                         │
└────────────────────────────────────────────────────────────────────────┘
```

- Pole wyszukiwania startuje bez fokusu; pierwszy znak lub wklejenie włącza edycję i wpisuje tekst. Enter na polu lub `/` również włącza edycję; Enter w edycji szuka; Esc wyłącza edycję i zostawia tekst. Automatyczne rozpoczęcie pisania dotyczy tylko zapytania.
- Ekran pojawia się tylko, gdy choć jeden wynik wyszukiwania nie jest wpisem franczyzy pierwszego wyniku widocznym w U02. Gdy wszystkie wyniki są w U02, wyszukiwanie od razu otwiera U02 z kursorem na pierwszym wyniku, a Esc z U02 wraca do zapytania. Nieudany odczyt franczyzy po wyszukiwaniu pokazuje błąd, z którego Enter wraca do tej listy.
- Dokładnie jeden wynik i jeden wpis kompletnej franczyzy, bez dodatków, otwiera od razu U03; Esc wraca do zapytania. Wiele wpisów, wpis będący dodatkiem, dodatki z ani.zip lub niepełna lista zachowują U02. Sprawdzenie dodatków może wymagać odczytu odcinków przed decyzją o pominięciu.
- Przy pominiętym U02 `G grupy` pozostaje dostępne z U03 dla wpisu z wyników wyszukiwania, także bez mapowania odcinków; Esc ze starej listy wraca do U03. Błąd odczytu odcinków wyłącza pominięcie: Enter/Esc z błędu wraca do U02. Lista wczytana przy wykryciu dodatków jest używana przy pierwszym Enter z U02 bez drugiego odczytu; następne jawne wejścia ponawiają odczyt. Nieaktywny ekran zapytania nie pokazuje „Enter edytuj”.
- Lista: zapowiedzi bez roku na górze, potem data premiery malejąco (dzień, miesiąc, rok; sam rok liczy się jak koniec roku), przy remisie alfabetycznie (W-03). Rok pochodzi z daty premiery, a bez niej z roku sezonu; ta sama reguła obowiązuje w U02. Bez roku kolumna pokazuje „—”. Tytuł angielski, gdy istnieje, inaczej romaji. Kolumny Rok, Tytuł, Typ, Status wyrównane pod nagłówkiem; status jak w U02. Bez liczby odcinków.
- Wyszukiwanie w toku: w miejscu listy „Szukam tytułu…”; Esc przerywa.
- Brak tytułu po poprawnie zakończonym wyszukiwaniu AniList: „Brak tytułu w AniList, szukam wydań na Nyaa” → wyszukiwanie wpisanego hasła → stara lista wydań wg grup. Na wynikach pozostaje notka „Brak tytułu w AniList, wyniki dla hasła”; Esc wraca do zapytania. To przejście nie dotyczy awarii AniList (W-08).
- AniList niedostępny: „AniList nie odpowiada · spróbuj za 1 min” (czas z ochłodzenia).
- `G` (E1–E2): otwiera dotychczasową listę wydań pogrupowanych według grup wydających — bez zmian, z działającym `D` pobierz i `O` subskrybuj. Pomost na czas E1–E2; usuwany w E3, gdy nowa droga ma Pobierz i Subskrybuj.

## 4. U02 — wpisy franczyzy (E1)

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Anime › That Time I Got Reincarnated as a Slime                        │
│                                                                        │
│ SEZONY I CZĘŚCI                                                        │
│> 2018  That Time I Got Reincarnated as a Slime          TV  zakończony │
│  2021  … Season 2                                       TV  zakończony │
│  2021  … Season 2 Part 2                                TV  zakończony │
│  2024  … Season 3                                       TV  zakończony │
│  2026  … Season 4                                       TV  w emisji   │
│ Dodatki                                                               │
│  2019  … OAD                                            OVA zakończony │
│ FILMY I INNE                                                           │
│  2021  The Slime Diaries                                TV  zakończony │
│  2022  … the Movie: Scarlet Bond                        Film zakończony│
│                                                                        │
│ Enter odcinki · G grupy · Esc tytuły                                   │
└────────────────────────────────────────────────────────────────────────┘
```

- Grupy według spec W-04 i plan E1 §10.5.1. W grupie: wpisy bez roku na górze, potem data premiery rosnąco (sam rok jak koniec roku). Kursor startuje na wpisie wybranym w U01 albo na pierwszym wyniku, gdy U01 pominięto.
- Esc wraca do U01, gdy była pokazana, inaczej do zapytania (stopka „Esc wróć”).
- `G grupy` pojawia się w stopce tylko dla podświetlonego wpisu obecnego w wynikach wyszukiwania. Poza nimi G zachowuje notkę „G działa dla tytułów z wyników wyszukiwania”. G nadal jest dostępne w U01.
- Status dotyczy wpisu: „w emisji”, „zakończony”, „zapowiedź”, „przerwa w emisji”, „anulowany”.
- Lista przerwana na limicie: ostatni wiersz „Lista niepełna”. Przy jednej grupie wpisów jej nagłówek znika; przy wielu grupach podział pozostaje.
- Film w E1: U03 ma jeden wiersz „Film” i notkę „Tylko podgląd wydań”. Faktyczna dostępność pobierania w E2 nadal podlega U-21; UI nie pokazuje nazw etapów ani obietnic obsługi.

## 5. U03 — odcinki wpisu (E1; D/I/P w E2; S w E3)

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Anime › Slime › Season 4 (2026)                                        │
│ Zaznaczone (2): 3, 5                                                   │
│                                                                        │
│      Nr  Tytuł                         Emisja          Stan            │
│  [ ]  1  The Beginning of…             7.07 18:00      Nie zamówiono   │
│  [ ]  2  …                             14.07 18:00     Nie zamówiono   │
│  [x]  3  …                             21.07 18:00     Nie zamówiono   │
│  [ ]  4  …                             28.07 18:00     Nie zamówiono   │
│> [x]  5  …                             4.08 18:00      Nie zamówiono   │
│  …                                                                     │
│      24  …                             25.09 18:00     Nie wyemitowano │
│ Dodatki                                                               │
│       S1  Veldora's Journal            12.01.2027                      │
│                                                                        │
│ Space zaznacz · A wszystkie/żadne · Z zakres · D pobierz · I wydania   │
│ P ponownie · Esc wpisy                                                │
└────────────────────────────────────────────────────────────────────────┘
```

Stopka powyżej obowiązuje w E2. Przy pominiętym U02 pokazuje też `G grupy`, jeśli działa dla wpisu. `S` do E3 nie jest wymienione w stopce; naciśnięcie pokazuje „Subskrypcje: użyj G grupy”, gdy G jest dostępne w U03, inaczej „Subskrypcje: wróć do tytułów lub wpisów i użyj G”, bez zlecenia. E3 dodaje „S subskrybuj” (tylko dla wpisu spełniającego spec U-10); stare O pod G pozostaje w E2.

- Space lub Enter zaznacza/odznacza podświetlony odcinek. Zaznaczyć można tylko odcinek w stanie „Nie zamówiono”; przy innym stanie notka, np. „E3 jest już zlecony · P pobierz ponownie” (E2+) albo „E24 jeszcze nie wyemitowano”.
- Nad listą „Zaznaczone (n): …” z połączonymi zakresami, np. „Zaznaczone (4): 1–3, 7”. Bez zaznaczeń linia znika.
- `A` przełącza: zaznacza wszystkie wyemitowane odcinki w stanie „Nie zamówiono”, a gdy wszystkie już są zaznaczone — czyści zaznaczenie.
- `Z` otwiera pole w stopce „Zakres: [1,3,9-12 albo 5-]” (tylko liczby całkowite). Enter zatwierdza; jeden Esc zamyka bez zastosowania. Ctrl+C przy zaznaczonym tekście nadal kopiuje. `5-` znaczy „od 5 do ostatniego znanego”. Zakres zastępuje zaznaczenie. Numer nieistniejący → notka „Brak odcinka 30 w tym wpisie”, zaznaczenie bez zmian.
- `D` dobiera i zleca sugestie zaznaczonych; bez zaznaczeń — podświetlonego, bez U04 i dodatkowego Enter. Powód niezlecenia dotyczy danego odcinka i nie blokuje reszty; sugestia niepewna jest dopuszczona według spec U-03/R-06. Lista pokazuje „Szukam wydania E…”. Esc/Tab i rozłączenie panelu nie przerywają partii ownera; po restarcie przyjęte odcinki pozostają, niezleconą resztę trzeba wybrać ponownie (plan E2 §8.1/§8.7).
- `I` otwiera U04b podświetlonego odcinka, niezależnie od zaznaczeń innych odcinków.
- Emisja: data i godzina lokalna; bez daty „—”. Przyszły odcinek ma stan „Czeka na emisję”, gdy obejmuje go subskrypcja (E3), inaczej „Nie wyemitowano”. Odcinka „Nie wyemitowano” nie da się zaznaczyć do pobrania.
- Kolumna daty nie zawiera „(ani.zip)”. Przy bieżącym odcinku z datą zastępczą szczegół mówi „E3: termin emisji niepotwierdzony (ani.zip)”; data nadal nie dowodzi emisji.
- F6: stan legacy „może być zlecony” pozostaje odrębny od „Zlecono” i blokuje zwykłe D/A/Z, z jawnym wyjściem P. Po faktycznie przerwanej partii: „Nie zlecono E4–E8 · zaznacz je ponownie” (rzeczywiste numery); bez rutynowej notki o restarcie. Limit tylko po przekroczeniu: „Limit: 100 odcinków · Z zmień zakres”, zaznaczenie bez zmian.
- Dodatki `S…` nie mają pola wyboru (spec W-06).
- Brak mapowania ani.zip: zamiast listy „Brak mapowania odcinków dla tego wpisu · Esc wróć”.
- Terminy emisji niedostępne: jeden komunikat „Brak terminów emisji (AniList) · ponów za N s”; po ochłodzeniu lub bez terminu „Brak terminów emisji (AniList) · wróć i otwórz ponownie”. Bez nowego klawisza ponawiania.

**Pobierz ponownie (E2):** `P` na zleconym/pobranym/gotowym lub „może być zlecony” otwiera bezpośrednio U04b z alternatywami i oznaczoną sugestią. Wiersz ostrzeżenia: „Obecne pliki zostają”, a dla legacy „E3 może być już zlecony · Obecne pliki zostają”. Zastępowane wydanie jest wyłączone z wyboru. Zgodą na ponowienie jest dopiero `D pobierz ponownie` dla zaznaczonego, a bez zaznaczenia podświetlonego wydania. Nie ma wcześniejszego pytania Enter/Esc ani osobnego U04. R-04 nadal wymaga osobnego potwierdzenia jawnego niepewnego/niezgodnego wyboru. Zgoda legacy dotyczy pokazanych danych konfliktu; zmiana danych ją unieważnia. W subskrypcji ręczne zlecenie rezerwuje cel odcinka.

## 6. U04 — odczytowy podgląd E1; U04b — wydania i ponowienie E2

U04 jest wyłącznie odczytowym podglądem E1, bez akcji Pobierz. W E2 zwykłe D pomija podgląd, a I i P otwierają bezpośrednio U04b. Osobne U04 nie uczestniczy w pobieraniu E2.

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Anime › Slime › Season 4 › Pobierz                                     │
│                                                                        │
│  Odc  Sugerowane wydanie                       Obraz  Język      Seedy │
│>   3  [Erai-raws] … - 03 [1080p][Multi]        1080p  MultiSub     312 │
│                                                                        │
│  zgodny: Tytuł i numer odcinka są zgodne.                              │
│  Plik: … - 03.mkv · Rozmiar: 1.4G                                     │
│                                                                        │
│ ↑↓ wybierz · Enter/I wydania · Esc odcinki                             │
└────────────────────────────────────────────────────────────────────────┘
```

- Wiersze wypełniają się po kolei (jedno zapytanie na odcinek); dopóki trwa, wiersz ma „Szukam…”. Esc przerywa i nie wysyła kolejnych zapytań.
- Kolumna Język: „PL”, „MultiSub”, „PL · MultiSub” albo „—”. Platforma (NF/CR) tylko w szczególe, gdy znana; grupa pozostaje w nazwie wydania.
- Rozmiar tylko w szczególe bieżącego wydania, brak → „?”. Seedy brak → „?”; Obraz, Język i Seedy pozostają widoczne przy 50–120 kolumnach.
- Powód sugestii jest krótki i wynika z faktycznej oceny, bez powtarzania pól tabeli ani ogólnika „pierwsze według preferencji”.
- U04 i U04b używają tej samej formy szczegółu: „werdykt: krótki powód”, np. „niepewny: Brak wskazanego pliku.”. Szerokość kolumny Język w obu widokach wynika z ich widocznych danych; nie rezerwuje pustego miejsca na nieobecne etykiety.
- E1: wiersz „[ Pobierz … ]” nie istnieje; stopka jak w makiecie bez „Enter pobierz”.
- Brak `zgodnego`, ale jest `niepewny` (spec R-06): sugestią jest najlepszy `niepewny` z prefiksem „niepewne ·” w wierszu i szczegółem „niepewny: <powód>”. Niepewność dotyczy odcinka wskazanego w nagłówku/wierszu, nie jakości obrazu.

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Inne wydania › Slime S4 E3                                             │
│                                                                        │
│    Wydanie                                      Obraz  Język    Seedy │
│>   [Erai-raws] … - 03 [1080p][Multi]             1080p  MultiSub  312 │
│    [SubsPlease] … - 03 (1080p)                  1080p  —         820 │
│    [EMBER] … S04E03 (paczka)                    1080p  —          45 │
│    niepewne · … 03                              ?     —           ? │
│    niezgodne · Tensura Nikki - 03               1080p  —         110 │
│                                                                        │
│  zgodny: Tytuł i numer odcinka są zgodne.                              │
│  Plik: … - 03.mkv · Rozmiar: 1.4G                                     │
│                                                                        │
│ Space/Enter wybierz · D pobierz · ? szczegóły · Esc wróć               │
└────────────────────────────────────────────────────────────────────────┘
```

- Kolejność: zgodni według rankingu, potem niepewni, potem niezgodni. Bez kolumny Tożsamość; tekstowe prefiksy tylko dla wyjątków. Pełny werdykt i krótki powód pod kursorem; `? szczegóły` rozwija pełny powód, Esc zamyka szczegóły. Nazwa pliku i rozmiar pod kursorem; bez indeksu i pustej platformy.
- Kolumna Seedy jest widoczna przy każdej szerokości (także 50 kolumn); tytuł wydania skraca się pierwszy. Szerokość kolumny Język wynika z najdłuższej etykiety na liście.
- Widoczne rozdzielczości (spec U-24): 1080p, 2160p i nieznana. 720p i niższe są ukryte, jeśli istnieje choć jedno zgodne 1080p lub 2160p; inaczej widać wszystkie.
- E1: Enter nic nie robi (stopka: „? szczegóły · Esc podgląd”).
- E2: sugestia jest oznaczona na liście z powodem pod nią. Space/Enter zaznacza jedno wydanie; następny wybór zastępuje poprzedni. D pobiera zaznaczone, a bez zaznaczenia — podświetlone. Nie ma A/Z do pobierania kilku wersji jednego odcinka. Esc wraca do odcinków, także po P. Po P stopka mówi `D pobierz ponownie`, z ostrzeżeniem opisanym w §5.
- Jawny wybór `niepewnego` wymaga przed pobraniem potwierdzenia „To wydanie może nie być E3 serii Slime S4. Wybrać mimo to? Enter tak · Esc nie”; `niezgodny`: „Heurystyka uznała to za inny materiał: <powód>. Wybrać mimo to? Enter tak · Esc nie”. Dotyczy też D bez zaznaczenia. Zmiana wyboru unieważnia potwierdzenie (spec R-04).
- Wydanie w nieobsługiwanym formacie ma w kolumnie Obraz dopisek „(.avi)” i nie może być wybrane.

## 7. U05 — wybór pliku w paczce (E2)

Otwierany z wiersza Przetwarzania ze stanem „Nie ustalono pliku w paczce”.

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Wybierz plik › Slime S4 E3 — paczka [EMBER] Season 4                   │
│                                                                        │
│>  Season 4/S04E03 - The ... [ABCD1234].mkv            1.3 GB           │
│   Extras/NCOP 03.mkv                                  90 MB            │
│                                                                        │
│ Enter ten plik to E3 · Esc wróć                                        │
└────────────────────────────────────────────────────────────────────────┘
```

- Lista pokazuje tylko pliki wideo paczki (pełne ścieżki z qBittorrenta). Enter wybiera wideo odcinka; pliki towarzyszące o tej samej nazwie dołączają się same (spec U-17).
- Po wyborze wiersz w Przetwarzaniu przechodzi do „Pobieranie”. Esc nic nie zmienia.

## 8. U06 — szkic subskrypcji (E3)

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Nowa subskrypcja                                                       │
│                                                                        │
│  Tytuł:     That Time I Got Reincarnated as a Slime Season 4           │
│  Od odc.:   24                                                         │
│  Później:   E24 — emisja 25.09 18:00                                   │
│  Koniec:    po pobraniu E24 (sezon ma 24 odcinki)                      │
│  Dodatki:   nie; pobierasz je osobno z listy wpisów                    │
│                                                                        │
│  Wyemitowane E1–E23 nie wchodzą do subskrypcji                         │
│  · zaznacz je i D, aby pobrać                                          │
│                                                                        │
│> [ Dodaj subskrypcję ]                                                 │
│  [ Anuluj ]                                                            │
│                                                                        │
│ ↑↓ wybierz · Enter · Esc anuluj                                        │
└────────────────────────────────────────────────────────────────────────┘
```

- „Od odc.” jest wyliczone z punktu odcięcia (spec U-09): pierwszy odcinek niewyemitowany w chwili dodania; pole nie jest edytowalne.
- Notka „Wyemitowane E1–E23 nie wchodzą do subskrypcji · zaznacz je i D, aby pobrać” pojawia się, gdy wpis ma wyemitowane odcinki; Esc wraca do U03, gdzie można je zaznaczyć.
- Liczba odcinków nieznana: „Koniec: gdy sezon się zakończy i wszystkie odcinki będą pobrane”.
- Zapowiedź bez dat: „Później: od E1 — termin nieznany”.
- Globalna pauza: dodatkowy wiersz „AniShift jest wstrzymany — subskrypcja zacznie działać po wznowieniu”.
- Wpis istnieje już jako subskrypcja: zamiast szkicu notka „Ten sezon jest już subskrybowany · Enter pokaż” → U08.

## 9. U07 — lista subskrypcji (E3)

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Anime  [Subskrypcje]  Przetwarzanie  Biblioteka                        │
│                                                                        │
│  D Dodaj subskrypcję                                        Aktywne: 3 │
│                                                                        │
│> Slime Season 4                     od 5    Pobrano 18/20   Gotowe 17  │
│    Emisja E24 za 2 d 04:18:09                                          │
│  Frieren Season 2                   od 1    Pobrano 7/?     Gotowe 6   │
│    Czeka na wydanie E8 (od 5 h)                                        │
│  Dungeon Meshi Season 2             od 1    Pobrano 0/?     Gotowe 0   │
│    Wstrzymana — zakończona przez starą wersję; brakuje E1–E3 · W wznów │
│                                                                        │
│ Enter szczegóły · D dodaj · W wstrzymaj · F szukaj · Del usuń · ^Z cofnij│
└────────────────────────────────────────────────────────────────────────┘
```

- Pierwszy wiersz listy to zawsze „D Dodaj subskrypcję” (także przy pustej liście, wtedy z tekstem „Brak subskrypcji”).
- Kolejność (spec S-03): najpierw wpisy z problemem, potem według najbliższej emisji, wpisy bez terminu i wstrzymane na końcu, remis alfabetycznie. Kolejność zmienia się tylko po emisji lub zmianie stanu; kursor zostaje na tym samym wpisie.
- Drugi wiersz wpisu: dokładnie jeden stan z spec S-03. Odliczanie tyka co sekundę bez sieci.
- Stały wiersz nad listą, gdy dotyczy: „AniShift wstrzymany — subskrypcje czekają” (globalna pauza) albo „Monitoring nie działa: nie można zapisać stanu · ponowię za 5 min” (spec S-12).
- `W` (również Space): wstrzymaj/wznów podświetloną. `F`: szukaj teraz dla podświetlonej; wynik w drugim wierszu wpisu na 10 s („Sprawdzono E8: 12 kandydatów, 0 zgodnych”). `Delete` (również `X`): usuwa od razu, bez pytania; notka „Usunięto Frieren S2 · Ctrl+Z cofnij”. `Ctrl+Z`: przywraca ostatnio usuniętą subskrypcję, także po restarcie (spec S-08).
- Zakończona subskrypcja znika z listy (spec S-09).

## 10. U08 — szczegóły subskrypcji (E3)

To jest U03 tego wpisu z nagłówkiem subskrypcji. Lista zawiera cele subskrypcji (odcinki od wyliczonego N, spec U-09).

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Subskrypcje › Frieren Season 2                                         │
│ Od odc. 1 · Pobrano 7/? · Gotowe 6 · Czeka na wydanie E8 (od 5 h)      │
│ Ostatnie sprawdzenie 14:02: E8 — 9 kandydatów, 0 zgodnych (9 niepewnych)│
│                                                                        │
│      Nr  Tytuł                         Emisja          Stan            │
│       7  …                             21.09 17:00     Gotowe          │
│>      8  …                             28.09 17:00     Czeka na wydanie│
│       9  …                             5.10 17:00      Czeka na emisję │
│                                                                        │
│ Space zaznacz · D pobierz · I wydania · P ponownie                     │
│ W wstrzymaj · F szukaj teraz · X usuń · Esc lista                      │
└────────────────────────────────────────────────────────────────────────┘
```

- Pod listą odcinków sekcja „Dodatki tego sezonu”: klucze `S…` z ani.zip i powiązane wpisy OVA/special z AniList (tylko informacja; Enter na wpisie OVA przechodzi do jego U03, gdzie można pobrać). Subskrypcja ich nie pobiera.
- Wszystkie klawisze odcinków jak w U03 (Space i Enter zaznaczają, A, Z, D, P). Dodatkowo: `W`, `F`, `X` jak w U07. „Od odc.” nie jest edytowalne (spec S-10 usunięte).
- `I` na podświetlonym odcinku otwiera U04b tego odcinka (np. ręczny wybór przy „Czeka na wydanie”).

## 11. Stany i komunikaty

| Sytuacja | Tekst | Akcja |
| --- | --- | --- |
| Szukanie w toku | „Szukam tytułu…” / „Wczytuję wpisy…” / „Wczytuję odcinki…” / „Szukam…” w wierszu | Esc przerywa |
| AniList niedostępny | „AniList nie odpowiada · spróbuj za N s” | Esc; ponów przez Enter po czasie |
| ani.zip niedostępny | „Lista odcinków niedostępna (ani.zip) · spróbuj za N s” | jw. |
| Torrentio niedostępny | „Źródło wydań nie odpowiada · spróbuj za N s” | jw. |
| Brak mapowania | „Brak mapowania odcinków dla tego wpisu” | Esc |
| Brak kandydatów | „Brak wydań w źródle”; czas sprawdzenia i liczniki w szczególe poniżej | Esc |
| Brak zgodnego, jest niepewny | Sugestia „niepewne · …”; szczegół „niepewny: <powód>” dla wskazanego odcinka | Enter → U04b w E1; I w E2 |
| Brak zgodnego i niepewnego | „Brak pasującego wydania E6”; czas i liczba niezgodnych poniżej | Enter → U04b w E1; I w E2 |
| Rezydent nie wykonał nowego polecenia (np. starsza wersja) | „Rezydent nie wykonał polecenia. Jeśli AniShift był właśnie aktualizowany, uruchom go ponownie.” | Esc |
| Zlecono, lista plików w drodze (E2) | wiersz Przetwarzania „Pobieranie listy plików” | — |
| Nie ustalono pliku (E2) | „Nie ustalono pliku w paczce” | Enter → U05 |
| Brak napisów w dwóch wydaniach (E4) | „Brak napisów w dwóch wydaniach” | Enter → U04b |
| Termin nieznany (E3) | „Termin nieznany” | — |
| Przerwa w emisji (E3) | „Przerwa w emisji” | — |
| Brak wydania od 7 dni (E3) | „Nie znaleziono E6 od 7 dni · szukam raz dziennie” + jedno powiadomienie w zasobniku | F szukaj teraz, I inne wydania |
| Czeka na wydanie (E3) | „Czeka na wydanie E8 (od 5 h)” / „(od 3 dni; sprawdzam raz dziennie)” | F szukaj teraz |
| Kontrola po pobraniu w toku (E3) | „Kontrola E6” | — |
| Kontrola po pobraniu nie wykonała się (E3) | „Kontrola niewykonana” przy odcinku | — |
| Limit prób wyczerpany (E3) | „E6: wyczerpano próby (3 z 3)” + jedno powiadomienie w zasobniku | I inne wydania, P pobierz ponownie |
| Pauza globalna | „AniShift wstrzymany — …” w stałym wierszu | O wznów (listy główne) |

Tekst błędu jest krótki, bez URL-i, ścieżek absolutnych i szczegółów technicznych.

## 12. Scenariusze odbioru

Każdy scenariusz wykonuje właściciel; wynik przekazuje jako: numer kroku, co zobaczył, czy zgodne z oczekiwanym, uwaga.

### H1 — wybór odcinka (koniec E1)

1. Panel → Anime → wpisz „slime” → wybierz 2018 → Season 1 → zaznacz 4 → D.
   Oczekiwane: sugestia to wydanie S1E4 serii głównej; Slime Diaries i OAD nie są „zgodne” w I (mogą być „niepewne” albo „niezgodne”).
2. Powtórz dla 9 tytułów, które oglądasz (w emisji i zakończonych).
   Oczekiwane: do właściwego wpisu i odcinka w ≤ 3 wyborach od wpisania nazwy; sugestie sensowne albo wskazany konkretny błąd.
3. Zaznacz 1 i 3, `Z` wpisz `5-`, Esc w trakcie podglądu, wróć.
   Oczekiwane: zakres zastępuje zaznaczenie; Esc przerywa bez błędu; powrót odtwarza kursor.
4. Terminal zwężony do ok. 50 kolumn.
   Oczekiwane: nic się nie nakłada; nazwa bieżącej zakładki widoczna.

### H2 — pobieranie (koniec E2)

1. Pobierz jeden odcinek z pojedynczego wydania i dwa (E1, E3) z tej samej paczki.
2. W trakcie pobierania zamknij panel i uruchom ponownie AniShift.
   Oczekiwane: jeden transfer paczki; pobierają się tylko E1 i E3; po restarcie praca trwa; oba odcinki w Bibliotece z lektorem; E2 nie pojawia się w Przetwarzaniu.
3. `P` na pobranym odcinku → alternatywy → `D pobierz ponownie`.
   Oczekiwane: lista bez zastępowanego wydania, ostrzeżenie „Obecne pliki zostają”; nowe zlecenie tylko tego odcinka; poprzedni wynik zostaje. R-04 osobno przy jawnym niepewnym/niezgodnym wyborze.

### H3 — subskrypcje (koniec E3, 7 dni)

1. Subskrypcje → D → wyszukaj tytuł w emisji → `S` → Dodaj.
   Oczekiwane: szkic pokazuje wyliczone „Od odc.”, notkę o wyemitowanych; wpis na liście, odliczanie do emisji; wyemitowane odcinki nie są zlecane.
2. Sprawdź przeniesione stare subskrypcje.
   Oczekiwane: aktywne bez należnych celów sprzed migracji są aktywne; aktywne z należnymi celami sprzed migracji są wstrzymane i nic nie pobierają przed „Wznów”, a po wznowieniu te cele ruszają (spec M-01); zakończone z brakami są wstrzymane z opisem (spec M-03).
3. Usuń jedną subskrypcję `Delete`, potem `Ctrl+Z`.
   Oczekiwane: znika bez pytania; po Ctrl+Z wraca z tym samym zakresem; pobrane pliki cały czas na miejscu.
4. Nie dotykaj aplikacji przez 7 dni.
   Oczekiwane: odcinki pojawiają się w Bibliotece; zakończony sezon znika z listy.

### H4 — kontrola zawartości (koniec E4)

1. Pobierz odcinek z polskimi napisami i odcinek tylko z angielskimi.
   Oczekiwane: pierwszy bez tłumaczenia, drugi przetłumaczony; w szczegółach powód.
2. (Jeśli dostępne) odcinek z polską ścieżką dubbingu.
   Oczekiwane: lektor wygenerowany jak zwykle.

## 13. Klawisze

| Ekran | Klawisz | Skutek | Etap |
| --- | --- | --- | --- |
| Wszystkie poza polem tekstowym | ←→ / Tab / Shift+Tab | Zmiana zakładki (zachowuje stan ekranów) | bez zmian |
| Wszystkie | Esc / Ctrl+C (bez zaznaczenia tekstu) | O ekran wstecz; w polu tekstowym najpierw wyłącza edycję, wyjątek: zakres odcinków zamyka od razu | E1: uproszczenie zakresu |
| Pole tekstowe | wszystkie litery, Space, Delete | Tekst, nigdy skrót | bez zmian |
| U01 | Enter / `/`; pierwszy znak lub wklejenie w zapytaniu | Wybierz tytuł / edytuj zapytanie; znak i wklejenie rozpoczynają edycję bez utraty tekstu | E1 |
| U01, U02 | G | Stara lista wydań wg grup (pomost); w U02 tylko dla wpisu z wyników wyszukiwania | E1–E2; usuwane w E3 |
| U03 po pominięciu U02 | G | Stara lista wydań wpisu z wyników wyszukiwania; Esc z niej wraca do odcinków | E1–E2 |
| U02 | Enter | Odcinki wpisu | E1 |
| U03, U08 | Space, Enter | Zaznacz/odznacz odcinek | E1 |
| U03 | A | Zaznacz wszystkie wyemitowane niezamówione; gdy wszystkie są zaznaczone — odznacz | E1 |
| U08 | A | Wszystkie/żadne wyemitowane niezamówione | E3 |
| U03, U08 | Z | Zakres | E1 |
| U03, U08 | D | Dobierz i pobierz zaznaczone, bez zaznaczeń podświetlony | E2; U08 w E3 |
| U03, U08 | P | Pobierz ponownie podświetlony | E2 |
| U03, U08 | I | Inne wydania podświetlonego odcinka | E2; U08 w E3 |
| U03 | S | E2: notka o G, bez skutku; E3: szkic subskrypcji | E2/E3 |
| U04 | Enter / I | Inne wydania podświetlonego, tylko odczyt | E1 |
| U04b po P | D | Pobierz ponownie zaznaczone, bez zaznaczeń podświetlone; zgoda na pokazany konflikt legacy, R-04 osobno | E2 |
| U04b | ? | Pokaż/zwiń pełny powód; Esc zamyka rozwinięte szczegóły | E1/E2 |
| U04b | Space / Enter | Zaznacz jedno wydanie | E2 |
| U04b | D | Pobierz zaznaczone, bez zaznaczenia podświetlone; R-04 przed skutkiem | E2 |
| U05 | Enter | Ten plik to odcinek | E2 |
| U07 | Enter | Szczegóły | E3 |
| U07 | D | Dodaj subskrypcję (przejście do U01) | bez zmian (dziś też `D`) |
| U07, U08 | W, Space (tylko U07) | Wstrzymaj/wznów | bez zmian |
| U07, U08 | F | Szukaj teraz — tylko podświetlona/otwarta subskrypcja | zmiana: dziś wszystkie |
| U07, U08 | Delete, X | Usuń od razu, bez pytania | Delete nowe; X jak dziś |
| U07 | Ctrl+Z | Przywróć ostatnio usuniętą subskrypcję | E3 |
| Przetwarzanie | Enter na wierszu z problemem | Ekran naprawy (U05 / U04b) | E2 |
| Listy główne (U07, Przetwarzanie, Historia, Biblioteka) | U / M / O | Ustawienia / Ręczny / pauza globalna | bez zmian |

`D` na liście subskrypcji oznacza „Dodaj” (zachowane), na odcinkach i wydaniach — „Pobierz”. Znaczenie jest zawsze opisane w stopce.

## 14. Mały terminal i asynchroniczność

- Nagłówek i stopka są stałe, środek przewijany. Linie przycinane według szerokości komórek terminala.
- Rozmiar jest szczegółem, nie kolumną. W wydaniach przy 50–120 kolumnach zawsze widać obraz, język i seedy; najpierw skraca się nazwę. Wyjątki tożsamości są tekstem w wierszu, pełny werdykt pod kursorem. W odcinkach znika najpierw emisja, potem skraca się tytuł; numer i stan pozostają.
- Gdy cztery zakładki się nie mieszczą: „← Subskrypcje (2/4) →” z liczbą liczoną z listy zakładek (dziś wpisane na sztywno `/4`).
- Ekran zbyt niski na listę: „Powiększ terminal” + działające Esc/Tab.
- Każdy wynik sieciowy jest przypisany do generacji ekranu; Esc, zmiana zakładki i nowe zapytanie unieważniają spóźnione wyniki. Render nigdy nie wykonuje sieci ani zapisu.

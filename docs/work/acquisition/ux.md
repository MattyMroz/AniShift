---
kind: ux-contract
status: do-akceptacji-właściciela
updated: 2026-09-23
baseline: 0e8a6bf9194d2786d426d3f3a58f48272b3eb087
---

# UX: wybór odcinka, pobieranie i subskrypcje

## 1. Zasady

- Ten dokument jest jedynym źródłem makiet, przejść i klawiszy tej pracy. Wymagania są w [spec.md](spec.md); kolejność budowy w [masterplan.md](masterplan.md).
- Każdy ekran ma oznaczony etap, w którym powstaje (E1–E3). Ekrany niewymienione (Home, Biblioteka, Ręczny, Ustawienia, paski Przetwarzania) **nie zmieniają się**.
- Dane w makietach są przykładowe. Etykiety w aplikacji są dokładnie takie jak w makietach, chyba że ekran nie mieści tekstu (§14).
- `[x]` = zaznaczone w szkicu, `>` = kursor. Zaznaczenie nigdy nie oznacza zlecenia.
- Każda akcja widoczna w stopce działa klawiszem; skrót literowy nie działa, gdy aktywne jest pole tekstowe.
- Esc wraca o jeden ekran i odtwarza poprzedni kursor, zaznaczenia i przewinięcie, bez ponownego pobierania danych.
- Zlecenie powstaje wyłącznie przez: Enter na „Pobierz” (U04), Enter na „Dodaj subskrypcję” (U06), Enter na „Tak” w potwierdzeniu „Pobierz ponownie” (U03). Nawigacja, render, odliczanie, Tab i Esc niczego nie zlecają.

## 2. Przejścia

```text
Home ─ Panel ─┬─ Anime ─ U01 Zapytanie/Tytuły ─ U02 Wpisy ─ U03 Odcinki ─┬─ D ─ U04 Podgląd ─ I ─ U04b Inne wydania
              │          └─ G ─ stara lista wydań wg grup (pomost E1–E2, bez zmian)
              │                                                         ├─ P ─ potwierdzenie „Pobierz ponownie”   (E2)
              │                                                         └─ O ─ U06 Szkic subskrypcji             (E3)
              ├─ Subskrypcje ─ U07 Lista ─┬─ D ─ U01 (powrót: U07)                                           (E3)
              │                          ├─ Enter ─ U08 Szczegóły (= U03 w kontekście subskrypcji)          (E3)
              │                          └─ Delete ─ usunięcie od razu; Ctrl+Z cofa                        (E3)
              ├─ Przetwarzanie ─ wiersz z problemem ─ Enter ─ U05 Wybierz plik / U04b Inne wydania          (E2)
              └─ Biblioteka (bez zmian)
```

Po Enter na „Pobierz” widok przechodzi do Przetwarzania z zaznaczonymi nowymi odcinkami — tylko jeśli użytkownik nadal jest na tym podglądzie w chwili odpowiedzi. Po „Dodaj subskrypcję” widok wraca do miejsca startu: do U07, jeśli dodawanie zaczęło się z listy subskrypcji, inaczej do U03.

## 3. U01 — zapytanie i tytuły (E1)

```text
┌────────────────────────────────────────────────────────────────────────┐
│ [Anime]  Subskrypcje  Przetwarzanie  Biblioteka                        │
│                                                                        │
│ Szukaj anime: [slime_____________________________]                     │
│                                                                        │
│  Rok   Tytuł                                              Format        │
│> 2024  That Time I Got Reincarnated as a Slime Season 3   TV            │
│  2021  That Time I Got Reincarnated as a Slime Season 2   TV            │
│  2018  That Time I Got Reincarnated as a Slime            TV            │
│  2022  That Time I Got Reincarnated as a Slime the Movie  Film          │
│                                                                        │
│ Enter wybierz · G wydania wg grup · / szukaj · Esc wróć                │
└────────────────────────────────────────────────────────────────────────┘
```

- Pole wyszukiwania startuje bez fokusu; Enter na polu lub `/` włącza edycję; Enter w edycji szuka; Esc wyłącza edycję i zostawia tekst.
- Lista: rok premiery wpisu malejąco, bez roku na końcu, w roku alfabetycznie (W-03). Tytuł angielski, gdy istnieje, inaczej romaji. Bez liczby odcinków.
- Wyszukiwanie w toku: w miejscu listy „Szukam tytułu…”; Esc przerywa.
- Brak wyników: „Nie znaleziono tytułu „slime”. Zmień hasło.”
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
│ DODATKI                                                                │
│  2019  … OAD                                            OVA zakończony │
│ FILMY I INNE                                                           │
│  2021  The Slime Diaries                                TV  zakończony │
│  2022  … the Movie: Scarlet Bond                        Film zakończony│
│                                                                        │
│ Enter odcinki · Esc tytuły                                             │
└────────────────────────────────────────────────────────────────────────┘
```

- Grupy i kolejność według spec W-04 i plan E1 §10.5.1. Kursor startuje na wpisie wybranym w U01.
- Status dotyczy wpisu: „w emisji”, „zakończony”, „zapowiedź”, „przerwa w emisji”, „anulowany”.
- Lista przerwana na limicie: ostatni wiersz „Lista niepełna — pokazano najbliższe powiązania”.
- Film w E1: Enter otwiera U03 z jednym wierszem „Film” i notką „Pobieranie filmów zależy od pomiaru E1” (spec U-21).

## 5. U03 — odcinki wpisu (E1; P w E2; O w E3)

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Anime › Slime › Season 4 (2026)                                        │
│ Zaznaczone: 3, 5                                                       │
│                                                                        │
│      Nr  Tytuł                         Emisja          Stan            │
│  [ ]  1  The Beginning of…             7.07 18:00      Nie zamówiono   │
│  [ ]  2  …                             14.07 18:00     Nie zamówiono   │
│  [x]  3  …                             21.07 18:00     Nie zamówiono   │
│  [ ]  4  …                             28.07 18:00     Nie zamówiono   │
│> [x]  5  …                             4.08 18:00      Nie zamówiono   │
│  …                                                                     │
│      24  …                             25.09 18:00     Nie wyemitowano │
│ DODATKI (informacja)                                                   │
│       S1  Veldora's Journal            12.01.2027                      │
│                                                                        │
│ Space zaznacz · A wyemitowane · Z zakres · D podgląd · Esc wpisy       │
└────────────────────────────────────────────────────────────────────────┘
```

Stopka w kolejnych etapach: E2 dodaje „P pobierz ponownie”, E3 dodaje „O subskrybuj” (tylko dla wpisu spełniającego spec U-10).

- Space lub Enter zaznacza/odznacza podświetlony odcinek. Zaznaczyć można tylko odcinek w stanie „Nie zamówiono”; przy innym stanie notka, np. „E3 jest już zlecony · P pobierz ponownie” (E2+) albo „E24 jeszcze nie wyemitowano”.
- `A` zaznacza wszystkie wyemitowane odcinki w stanie „Nie zamówiono”.
- `Z` otwiera pole w stopce „Zakres: [1,3,9-12 albo 5-]” (tylko liczby całkowite). Enter zatwierdza, Esc zamyka. `5-` znaczy „od 5 do ostatniego znanego”. Zakres zastępuje zaznaczenie. Numer nieistniejący → notka „Brak odcinka 30 w tym wpisie”, zaznaczenie bez zmian.
- `D` otwiera U04 dla zaznaczonych; bez zaznaczeń — dla podświetlonego.
- Emisja: data i godzina lokalna; bez daty „—”. Przyszły odcinek ma stan „Czeka na emisję”, gdy obejmuje go subskrypcja (E3), inaczej „Nie wyemitowano”. Odcinka „Nie wyemitowano” nie da się zaznaczyć do pobrania.
- Dodatki `S…` nie mają pola wyboru (spec W-06).
- Brak mapowania ani.zip: zamiast listy „Brak mapowania odcinków dla tego wpisu · Esc wróć”.
- Terminy emisji niedostępne: notka nad listą „Terminy emisji niedostępne (AniList)”.

**Pobierz ponownie (E2):** `P` na podświetlonym odcinku, który jest zlecony/pobrany/gotowy, pokazuje w stopce: „Pobrać E3 ponownie? Obecne pliki zostają. Enter tak · Esc nie”. Tak → nowe zlecenie tylko tego odcinka z nową sugestią (bez podglądu), widok zostaje.

## 6. U04 — podgląd pobrania i inne wydania (E1; Pobierz w E2)

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Anime › Slime › Season 4 › Pobierz                                     │
│                                                                        │
│  Odc  Sugerowane wydanie                  Obraz  Język      Seedy  Rozm│
│>   3  [Erai-raws] … - 03 [1080p][Multi]   1080p  MultiSub     312  1.4G│
│    5  [SubsPlease] … - 05 (1080p)         1080p  —            820  1.3G│
│    7  Brak pewnego wydania (sprawdzono 14:02; niepewnych 6, niezgodnych 2)│
│                                                                        │
│  Powód E3: MultiSub · 1080p · najwięcej seedów wśród zgodnych          │
│                                                                        │
│  [ Pobierz 2 odcinki ]                                           (E2)  │
│                                                                        │
│ ↑↓ wybierz · Enter/I inne wydania · Esc odcinki                        │
└────────────────────────────────────────────────────────────────────────┘
```

- Wiersze wypełniają się po kolei (jedno zapytanie na odcinek); dopóki trwa, wiersz ma „Szukam…”. Esc przerywa i nie wysyła kolejnych zapytań.
- Kolumna Język: „PL”, „MultiSub”, „PL · MultiSub” albo „—”. Źródło platformy (NF/CR) i grupa są w wierszu „Powód” pod listą, nie w kolumnach.
- Rozmiar: przybliżony rozmiar pliku odcinka; brak → „?”. Seedy brak → „?”.
- Wiersz „Powód” pokazuje uzasadnienie dla podświetlonego odcinka.
- E1: wiersz „[ Pobierz … ]” nie istnieje; stopka jak w makiecie bez „Enter pobierz”.
- E2: ↑↓ dochodzi do wiersza „[ Pobierz N odcinki ]”; Enter na nim zleca odcinki z sugestią. Odcinki bez sugestii nie są zlecane; po zleceniu notka „Nie zlecono: E7 (brak pewnego wydania)”.
- Zmiana wydania w U04b zmienia sugestię tylko tego odcinka w tym podglądzie.

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Inne wydania › Slime S4 E3                                             │
│                                                                        │
│    Tożsamość     Wydanie                          Obraz  Język    Seedy │
│>   zgodny        [Erai-raws] … - 03 [1080p][Multi] 1080p  MultiSub  312 │
│    zgodny        [SubsPlease] … - 03 (1080p)      1080p  —         820 │
│    zgodny        [EMBER] … S04E03 (paczka)        1080p  —          45 │
│    niepewny      … 03 [720p]                      720p   —           ? │
│    niezgodny     Tensura Nikki - 03               1080p  —         110 │
│                                                                        │
│  Powód: brak rozpoznanego aliasu tytułu                                │
│                                                                        │
│ Enter wybierz (E2) · Esc podgląd                                       │
└────────────────────────────────────────────────────────────────────────┘
```

- Kolejność: zgodni według rankingu, potem niepewni, potem niezgodni. Powód tożsamości dla podświetlonego wiersza, po polsku.
- Widoczne rozdzielczości (spec U-24): 1080p, 2160p i nieznana. 720p i niższe są ukryte, jeśli istnieje choć jedno zgodne 1080p lub 2160p; inaczej widać wszystkie.
- E1: Enter nic nie robi (stopka: „Esc podgląd”).
- E2: Enter na `zgodny` ustawia sugestię i wraca do U04. Enter na `niepewny` pyta w stopce: „To wydanie może nie być E3 serii Slime S4. Wybrać mimo to? Enter tak · Esc nie”. Enter na `niezgodny` pyta: „Heurystyka uznała to za inny materiał: <powód>. Wybrać mimo to? Enter tak · Esc nie”.
- Wydanie w nieobsługiwanym formacie ma w kolumnie Obraz dopisek „(.avi)” i nie może być wybrane.

## 7. U05 — wybór pliku w paczce (E2)

Otwierany z wiersza Przetwarzania ze stanem „Nie ustalono pliku w paczce”.

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Wybierz plik › Slime S4 E3 — paczka [EMBER] Season 4                   │
│                                                                        │
│>  Season 4/S04E03 - The ... [ABCD1234].mkv            1.3 GB           │
│   Season 4/S04E03 - The ... [ABCD1234].ass            52 KB            │
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
│  Od odc.:   [5]                                                        │
│  Teraz:     E5–E23 (wyemitowane) — pobiorę od razu                     │
│  Później:   E24 — emisja 25.09 18:00                                   │
│  Koniec:    po pobraniu E24 (sezon ma 24 odcinki)                      │
│  Dodatki:   nie; pobierasz je osobno z listy wpisów                    │
│                                                                        │
│> [ Dodaj subskrypcję ]                                                 │
│  [ Anuluj ]                                                            │
│                                                                        │
│ ↑↓ wybierz · Enter · Esc anuluj                                        │
└────────────────────────────────────────────────────────────────────────┘
```

- „Od odc.” domyślnie podświetlony odcinek z U03; Enter na polu włącza edycję (liczba całkowita); wiersze „Teraz/Później/Koniec” przeliczają się na bieżąco.
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

To jest U03 tego wpisu z nagłówkiem subskrypcji. Lista zawiera odcinki od N.

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
│ Space zaznacz · D podgląd · I wydania · P ponownie · N od odc.         │
│ W wstrzymaj · F szukaj teraz · X usuń · Esc lista                      │
└────────────────────────────────────────────────────────────────────────┘
```

- Pod listą odcinków sekcja „Dodatki tego sezonu”: klucze `S…` z ani.zip i powiązane wpisy OVA/special z AniList (tylko informacja; Enter na wpisie OVA przechodzi do jego U03, gdzie można pobrać). Subskrypcja ich nie pobiera.
- Wszystkie klawisze odcinków jak w U03 (Space i Enter zaznaczają, A, Z, D, P). Dodatkowo: `N` zmienia „od odc.” (pole w stopce, spec S-10), `W`, `F`, `X` jak w U07.
- `I` na podświetlonym odcinku otwiera U04b tego odcinka (np. ręczny wybór przy „Czeka na wydanie”).

## 11. Stany i komunikaty

| Sytuacja | Tekst | Akcja |
| --- | --- | --- |
| Szukanie w toku | „Szukam tytułu…” / „Wczytuję wpisy…” / „Wczytuję odcinki…” / „Szukam…” w wierszu | Esc przerywa |
| AniList niedostępny | „AniList nie odpowiada · spróbuj za N s” | Esc; ponów przez Enter po czasie |
| ani.zip niedostępny | „Lista odcinków niedostępna (ani.zip) · spróbuj za N s” | jw. |
| Torrentio niedostępny | „Źródło wydań nie odpowiada · spróbuj za N s” | jw. |
| Brak mapowania | „Brak mapowania odcinków dla tego wpisu” | Esc |
| Brak kandydatów | „Brak kandydatów w źródle (sprawdzono HH:MM)” | Esc |
| Brak zgodnego | „Brak pewnego wydania (sprawdzono HH:MM; niepewnych n, niezgodnych m)” | Enter → U04b |
| Rezydent nie wykonał nowego polecenia (np. starsza wersja) | „Rezydent nie wykonał polecenia. Jeśli AniShift był właśnie aktualizowany, uruchom go ponownie.” | Esc |
| Zlecono, lista plików w drodze (E2) | wiersz Przetwarzania „Pobieranie listy plików” | — |
| Nie ustalono pliku (E2) | „Nie ustalono pliku w paczce” | Enter → U05 |
| Brak napisów w dwóch wydaniach (E4) | „Brak napisów w dwóch wydaniach” | Enter → U04b |
| Termin nieznany (E3) | „Termin nieznany” | — |
| Przerwa w emisji (E3) | „Przerwa w emisji” | — |
| Brak wydania od 7 dni (E3) | „Nie znaleziono E6 od 7 dni · szukam raz dziennie” + jedno powiadomienie w zasobniku | F szukaj teraz, I inne wydania |
| Czeka na wydanie (E3) | „Czeka na wydanie E8 (od 5 h)” / „(od 3 dni; sprawdzam raz dziennie)” | F szukaj teraz |
| Pauza globalna | „AniShift wstrzymany — …” w stałym wierszu | O wznów (listy główne) |

Tekst błędu jest krótki, bez URL-i, ścieżek absolutnych i szczegółów technicznych.

## 12. Scenariusze odbioru

Każdy scenariusz wykonuje właściciel; wynik przekazuje jako: numer kroku, co zobaczył, czy zgodne z oczekiwanym, uwaga.

### H1 — wybór odcinka (koniec E1)

1. Panel → Anime → wpisz „slime” → wybierz 2018 → Season 1 → zaznacz 4 → D.
   Oczekiwane: sugestia to wydanie S1E4 serii głównej; Slime Diaries i OAD są „niezgodne” w I.
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
3. `P` na pobranym odcinku → Tak.
   Oczekiwane: nowe zlecenie tylko tego odcinka; poprzedni wynik zostaje.

### H3 — subskrypcje (koniec E3, 7 dni)

1. Subskrypcje → D → wyszukaj tytuł w emisji → `O` → od bieżącego odcinka → Dodaj.
   Oczekiwane: wpis na liście, odliczanie do emisji.
2. Sprawdź przeniesione stare subskrypcje.
   Oczekiwane: aktywne są aktywne; zakończone z brakami są wstrzymane z opisem.
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
| Wszystkie | Esc / Ctrl+C (bez zaznaczenia tekstu) | O ekran wstecz; w polu tekstowym najpierw wyłącza edycję | bez zmian |
| Pole tekstowe | wszystkie litery, Space, Delete | Tekst, nigdy skrót | bez zmian |
| U01 | Enter / `/` | Wybierz tytuł / edytuj zapytanie | E1 |
| U01 | G | Stara lista wydań wg grup (pomost) | E1–E2; usuwane w E3 |
| U02 | Enter | Odcinki wpisu | E1 |
| U03, U08 | Space, Enter | Zaznacz/odznacz odcinek | E1 |
| U03, U08 | A | Zaznacz wszystkie wyemitowane niezamówione | E1 |
| U03, U08 | Z | Zakres | E1 |
| U03, U08 | D | Podgląd pobrania | E1 |
| U03, U08 | P | Pobierz ponownie podświetlony | E2 |
| U08 | I | Inne wydania podświetlonego odcinka | E3 |
| U03 | O | Szkic subskrypcji | E3 |
| U04 | Enter / I | Inne wydania podświetlonego; na „[ Pobierz ]” — zlecenie (E2) | E1/E2 |
| U04b | Enter | Wybierz wydanie (niepewny i niezgodny z potwierdzeniem) | E2 |
| U05 | Enter | Ten plik to odcinek | E2 |
| U07 | Enter | Szczegóły | E3 |
| U07 | D | Dodaj subskrypcję (przejście do U01) | bez zmian (dziś też `D`) |
| U07, U08 | W, Space (tylko U07) | Wstrzymaj/wznów | bez zmian |
| U07, U08 | F | Szukaj teraz — tylko podświetlona/otwarta subskrypcja | zmiana: dziś wszystkie |
| U07, U08 | Delete, X | Usuń od razu, bez pytania | Delete nowe; X jak dziś |
| U07 | Ctrl+Z | Przywróć ostatnio usuniętą subskrypcję | E3 |
| U08 | N | Zmień „od odc.” | E3 |
| Przetwarzanie | Enter na wierszu z problemem | Ekran naprawy (U05 / U04b) | E2 |
| Listy główne (U07, Przetwarzanie, Historia, Biblioteka) | U / M / O | Ustawienia / Ręczny / pauza globalna | bez zmian |

`D` ma dwa znaczenia zależnie od ekranu: na liście subskrypcji „Dodaj” (zachowane z obecnej wersji), na liście odcinków „podgląd pobrania”. Oba są zawsze opisane w stopce.

## 14. Mały terminal i asynchroniczność

- Nagłówek i stopka są stałe, środek przewijany. Linie przycinane według szerokości komórek terminala.
- Kolejność obcinania kolumn: rozmiar → seedy → emisja → tytuł odcinka. Numer, stan i tożsamość zostają zawsze.
- Gdy cztery zakładki się nie mieszczą: „← Subskrypcje (2/4) →” z liczbą liczoną z listy zakładek (dziś wpisane na sztywno `/4`).
- Ekran zbyt niski na listę: „Powiększ terminal” + działające Esc/Tab.
- Każdy wynik sieciowy jest przypisany do generacji ekranu; Esc, zmiana zakładki i nowe zapytanie unieważniają spóźnione wyniki. Render nigdy nie wykonuje sieci ani zapisu.

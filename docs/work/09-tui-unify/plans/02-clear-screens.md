---
kind: plan
status: w toku na work/tui/02-unified-tabs (PR #59); punkty „Do decyzji” rozstrzyga właściciel ekran po ekranie
created: 2026-10-11
baseline: work/tui/02-unified-tabs @ 49dd9ec
execution branch: work/tui/02-unified-tabs
---

# Plan 02: jasne ekrany — prawdziwe podpowiedzi, zrozumiałe komunikaty, czytelne subskrypcje

Podstawa: rozmowa z właścicielem 2026-10-11 (decyzje niżej, §2) i pełny spis ekranów
[inventory.md](../inventory.md) (73 ekrany panelu, Ustawień, Ręcznego, Home i wykonania; część Anime B01–B13 dopisana
osobno). Plan 01 ([plan.md](01-implementation.md)) ujednolicił klawisze i szkielet; ten plan nie zmienia jego słownika klawiszy
(§3 01-implementation.md) poza punktami nazwanymi w §2.

## 1. Rezultat

Na każdym ekranie interaktywnym AniShift (Home, cztery zakładki panelu z podekranami, Ustawienia, Ręczny, ekrany
postępu i wyniku):

1. dół ekranu ma jeden porządek i każda jego linia mówi coś, co użytkownik rozumie;
2. podpowiedź klawisza pojawia się tylko, gdy akcja zadziała teraz, bez duplikatów, z czasownikiem;
3. każdą podpowiedź klawisza można kliknąć — klik działa dokładnie jak ten klawisz;
4. każdy komunikat ze słownika (§5) jest zaakceptowany przez właściciela;
5. lista Subskrypcji mówi: ile odcinków wyszło, ile czeka na dysku i co program robi dalej, a gdy stoi — dlaczego;
6. subskrypcja nie zawiesza się na stałe, gdy zewnętrzna lista odcinków poprawi numerację (przypadek Sword).

Wygląd (paleta, akcenty, układ góra/dół, kursor `❯`) bez zmian, poza wyszarzeniem z §4.3, jeśli właściciel je przyjmie.

## 2. Decyzje właściciela 2026-10-11

- **D1.** Pasek klawiszy na dole zostaje (właściciel czyta go wzrokiem; pomaga laikowi). Trzy reguły:
  R1 nic, czego nie da się teraz zrobić; R2 zero duplikatów; R3 zero niejasnych słów.
- **D2.** Każda podpowiedź na dole jest klikalna, we wszystkich zakładkach.
- **D3.** `? więcej` → `? klawisze`.
- **D4.** Subskrypcje: w stopce tylko `D dodaj`; `/` działa dalej jako cichy alias.
- **D5.** `D` (i klik w `D dodaj`) w Subskrypcjach przenosi do zakładki Anime z polem wyszukiwania. Po dodaniu
  subskrypcji panel jak dziś wraca na listę Subskrypcji. Esc z wyszukiwarki nie wraca już do listy Subskrypcji.
- **D6.** Kolumna `Odcinki` = ile odcinków wyszło / ile ma sezon (`3/12`, nieznana długość `3/?`). Stare znaczenie
  (dysk + „obejrzane przed subskrypcją”) i jego błędny licznik znikają.
- **D7.** `Gotowe` = ile odcinków leży na dysku — bez zmian.
- **D8.** Bez kolumny „przetworzone” i bez strzałki „gdzie jestem”. Gdy program zalega, mówi to `Stan`: który
  odcinek stoi i dlaczego (wariant C).
- **D9.** Pojęcie „obejrzany” nie wchodzi do programu; właściciel usuwa obejrzane odcinki sam.
- **D10.** Połączenie Subskrypcji z Biblioteką niepotrzebne: Enter na gotowym odcinku w szczegółach subskrypcji
  już go odtwarza.

## 3. Stan obecny (dowody w inventory.md)

- **Stopki powstają w pięciu miejscach:** panel `StateController._keys` z `ScreenActions` (`ui/actions.py`), tabele
  Anime/Subskrypcji/Biblioteki `anime_view._key_lines`, stałe podpowiedzi Ustawień (`_MENU_HINT`… `ui/settings.py:52-70`),
  Ręczny `menu.with_footer` (`ui/manual.py:74-77`), Home i wynik w `ui/app.py:71,1151`. Żadna nie nadaje tagu
  `mark_target`, więc nic nie jest klikalne (inventory „F”).
- **Naruszenia:** wspólny panel 15 wzorców (R1 8, R2 1, R3 6), Ustawienia/Ręczny/Home/wykonanie 32 wzorce
  (R1 8, R2 3, R3 21), Anime 32 (R1 17, R2 1, R3 14). Najczęstsze: `R1-BUSY` (podpowiedzi akcji, które `_work` pomija przy
  zajętości), stałe stopki niezależne od wiersza (Historia pusta, szczegóły Biblioteki na wierszu informacyjnym),
  podwójne zapisy `↑↓/Tab`, `Enter/Space`, `D lub /`, techniczne słowa (`czeka N`, `Tryb cienia`, `Finalizacja`,
  `Metadane`, `Workspace`, `grupa`).
- **Linia statusu:** `Automat: praca · pobiera N · przetwarza N · czeka N · O wyłącz`; `czeka` liczy każdy materiał
  `stage=waiting` oraz przetwarzanie `accepted/paused` (`app/automation.py:1711-1736`), bez nazwy przyczyny.
- **Subskrypcje:**
  - `Odcinki` = `done` = dysk ∪ `watched` (`automation.py:4342-4354`). Odcinek pobrany przez subskrypcję
    i potem usunięty przestaje się liczyć. Overgeared pokazuje 2/12, choć wyszły 3.
  - `Stan` dla należnego celu mówi tylko `Czeka E3 od 01:12:00` (`subscription_texts.py:192-198`), bez przyczyny
    (szukam / czekam na PL / pobieram / brak wydania).
- **Sword (159042):**
  - ani.zip poprawiło numerację odcinków 2–4. `merge_listing` ustawia `CATALOG_CONFLICT` i nie podmienia
    zapisanego mapowania (`subscription_targets.py:512-513,620-633`).
  - Konflikt nie ma wyjścia. `_searchable` wyłącza szukanie (`automation.py:9138`).
  - Retry co kilka minut czyta ani.zip bez końca (`decisions.jsonl`).
  - Etykieta `Inny sezon w katalogu` (`subscription_texts.py:65`) nie opisuje zdarzenia.

## 4. Kontrakt dołu ekranu

### 4.1 Porządek linii (od dołu)

1. linia katalogu i wersji (bez zmian);
2. linia statusu automatu — tylko w panelu (bez zmian miejsca);
3. stopka klawiszy;
4. jeden wiersz powiadomienia (wynik ostatniej czynności, odmowa, „Usunięto · Ctrl+Z cofnij”);
5. wiersz uzupełnienia wiersza pod kursorem (pełny tytuł, ukryte kolumny, pełny stan) — tylko w tabelach.

Historia dziś rysuje problem i powiadomienie *pod* stopką (`ui/state.py:1317-1320`) — wyrównać do porządku 1–5.

### 4.2 Reguły stopki (wszystkie ekrany)

- **S1 (R1).** Podpowiedź istnieje tylko, gdy naciśnięcie wykona akcję teraz. Funkcja akcji ekranu dostaje stan
  wiersza *i* zajętość (`_busy`, BUSY Anime, test połączenia w Ustawieniach). Stałe krotki (`HISTORY_ACTIONS`,
  `DETAIL_ACTIONS`) stają się funkcjami stanu.
- **S2 (R2).** Jeden klawisz na akcję; alternatywy (`Tab` obok `↑↓`, `Space` obok `Enter`, `/` obok `D`, `→` obok
  `Enter`, `←` obok `Esc`) działają, ale nie są wypisywane.
- **S3 (R3).** Każdy segment ma postać `Klawisz czasownik` (`Enter otwórz`, `←→ zmień`, `Esc wróć`). Gołe
  `↑↓ · Enter · Esc` znikają; nawigacja `↑↓` jest tylko w pomocy, jak już w panelu (plan 01 §4.3).
- **S4 (D2).** Każdy segment stopki i podpowiedź `O włącz/wyłącz` w linii statusu niesie tag
  `mark_target(Click(ClickKind.KEY, klawisz))`; `app._follow_click` wysyła ten klawisz tą samą drogą co klawiatura.
  Jedna funkcja budująca stopkę (rozszerzenie `pack_keys`/`with_footer`) zamiast pięciu miejsc. Hover podświetla
  klikalny segment tak jak wiersze (istniejące `light_targets`).
- **S5 (D3).** `? klawisze` zamiast `? więcej` wszędzie; `Esc wróć` bez zmian. Ekrany, które dziś nie mają `?`
  (pola, pytania, propozycja), dalej go nie mają.
- **S6.** Pytania (`Anulować…? Enter tak · Esc nie`) są klikalne tak samo: klik w `Enter tak` = Enter.

### 4.3 Zajętość (Do decyzji, checkpoint C1)

Zajętość trwa zwykle ułamek sekundy (polecenie do rezydenta) i rzadko dłużej (odczyt Historii). Ścisłe S1
zabierałoby podpowiedzi na ten czas i stopka by migała. Propozycja: przy zajętości podpowiedzi akcji zostają na
miejscu, ale **wyszarzone** (istniejąca rola `gray`) i nieklikalne; po zakończeniu wracają. Alternatywa: znikają.

## 5. Słownik komunikatów

### 5.1 Zasada

Komunikat mówi, **co się dzieje i co z tym zrobić**, słowami użytkownika, krótko. Bez terminów wewnętrznych
(katalog, grupa, workspace, metadane, cień, owner, rezydent, H1). Jedno źródło każdego tekstu, jak dziś
(`*_texts.py`, stałe `Final`).

### 5.2 Teksty do przepisania (propozycje; właściciel akceptuje ekran po ekranie, checkpoint C2)

| Dziś | Gdzie | Propozycja |
|---|---|---|
| `? więcej` | stopki | `? klawisze` (D3) |
| `czeka 2` | linia statusu | `2 w kolejce` (czeka na start przetwarzania) |
| `pobiera 1 · przetwarza 1` | linia statusu | bez zmian |
| `Inny sezon w katalogu` | Subskrypcje Stan | znika razem z błędem Sword (§6.3) |
| `Tryb cienia — subskrypcje tylko zapisują propozycje` | Subskrypcje | `Tryb próbny · subskrypcje niczego nie pobierają` |
| `Finalizacja` (gdy finalizacja zawiodła) | Przetwarzanie | `Błąd zapisu` |
| `Wymaga uwagi` | Przetwarzanie, Subskrypcje | nazwa konkretnej przyczyny z istniejących słowników; ogólne tylko jako ostatnia deska |
| `Metadane` | Przetwarzanie | `Łączę` (do chwili, gdy klient zna pliki) |
| `Workspace nie zawiera materiału…`, `grupa`, `użyteczne napisy` | odmowy Auto | słowami: „W folderze AniShift nie ma odcinka do przetworzenia” itd. |
| `↑↓/Tab · ←→ · Enter · Esc` | Ustawienia | `Enter otwórz · ←→ zmień · Esc wróć` (S2, S3) |
| `↑↓ · Enter · Esc` | Ręczny | czasowniki ekranu (S3) |
| `dowolny klawisz zamyka` / `dowolny inny klawisz: powrót` | wynik, partia | `Esc zamknij` (prawdziwe dla każdego klawisza poza przewijaniem) |
| `Czeka E3 od 01:12:00` | Subskrypcje Stan | §6.2 |
| `Konflikt hasha` | Anime Stan | `Już pobierane innym wydaniem` |
| `Czeka na stare` | Anime Stan | `Czeka na poprzednie pobieranie` |
| `Kontrola`, `Bez kontroli`, `Kontrola E3` | Anime/U08 Stan | `Sprawdzam plik`, `Plik niesprawdzony`, `E3 · sprawdzam plik` |
| `propozycja zapisana` | U08 | znika z trybem próbnym (§5.2 wyżej) |
| `Zlecono` na wierszu bez zlecenia (`Szukam`, `Brak wydania`, dodatek) | wydania, U08 | pusty Stan (fallback `anime_state.py:108-114` usunięty) |
| `Odczyt H1`, `Cel: lokalny`, `S/E`, `absolutny`, `Kalibracja pewności…` | szczegóły wydania `?` | słowa „pasuje / nie pasuje / niepewne” i numer odcinka; kalibracja znika z widoku |
| `Rezydent nie wykonał polecenia…`, `Sprawdź prywatny klient AniShift i log` | Anime PROBLEM | „AniShift w tle nie odpowiedział · uruchom AniShift ponownie” / „sprawdź qBittorrenta AniShift” |
| `Pobrać mimo niepewnej tożsamości?` | potwierdzenie wydania | `Nie mam pewności, że to E3. Pobrać? Enter tak · Esc nie` |
| `Zakres: podaj 1,3,7.5 albo 5-` | edytor zakresu | `Zakres: np. 1,3 albo 5-` |
| `Trwa wyszukiwanie wydań` (także przy wysyłce) | odcinki, wydania | rozdzielić: `Szukam wydań` / `Wysyłam` |

Pełna lista R3 (Ustawienia N02–N34, panel R3-*, Anime B) jest w inventory.md; teksty spoza tabeli przechodzą przez
ten sam checkpoint w kolejności ekranów §7.

## 6. Subskrypcje

### 6.1 Kolumny (D6–D8)

`Tytuł · Odcinki · Gotowe · Stan`, bez nowej kolumny.

- **Odcinki** = `aired/episode_count`. Owner liczy `aired` w `subscription_row`: `cut` + liczba celów poza
  `awaiting_airing` (czyste dane rekordu, bez I/O). Pola `watched`, `done`, `on_disk` w wierszu i ich liczenie
  w `automation.py:4311-4354` znikają, razem z `watched_line` („obejrzane przed subskrypcją”), jeśli nic innego
  ich nie używa.
- **Gotowe** bez zmian (`ready`).

### 6.2 Stan

Wiersz dostaje od ownera stan najbliższego niespełnionego celu (`due_state`) obok `due_number`/`due_at`. Słowa
(propozycje do checkpointu C2):

| Sytuacja | Stan |
|---|---|
| odcinek jeszcze nie wyszedł | `E4 · 18.10 16:30` (dziś `Emisja E4 za …`) |
| wyszedł, szukam wydania | `E3 · szukam` |
| czekam na polskie napisy | `E3 · czekam na PL do 18:30` |
| pobieram / przetwarzam | `E3 · pobieram` / `E3 · przetwarzam` |
| brak wydania po pierwszej dobie | `E3 · brak wydania` |
| wyczerpane próby | `E3 · nie udało się · D pobierz ręcznie` |
| subskrypcja wstrzymana | `Wstrzymana · E4` |
| automat (`O`) wyłączony | bez zmian w wierszu; stan automatu mówi linia statusu |

Kolejność listy (`display_order`) bez zmian.

### 6.3 Poprawiona numeracja ani.zip (Sword) — Do decyzji, checkpoint C1

Dziś: każda zmiana numeracji zapisanych odcinków → konflikt bez wyjścia. Warianty:

- **A (rekomendacja):** owner przyjmuje nowe mapowanie od razu i zapisuje wpis `catalog_renumbered` w
  `decisions.jsonl`; każde pobranie i tak przechodzi H1 (tożsamość odcinka) i H2 (długość). U08 pokazuje jedną notkę
  „Lista odcinków zmieniła numerację (data)”.
- **B:** konflikt zostaje, ale z wyjściem: `Stan` = `Zmieniła się lista odcinków · Enter sprawdź`, w U08 jeden
  klawisz przyjmuje nową numerację; retry zatrzymuje się do decyzji.

Do czasu wdrożenia obejście dla Sword: usuń i dodaj subskrypcję, w szkicu odznacz E1.

## 7. Wykonanie

Kolejność według pilności i zależności; każda faza kończy się zielonymi bramkami (`ruff`, `ruff format --check`,
`mypy` win32+linux, `pytest`) i commitem tematycznym.

- **F1 — Sword i Odcinki/Stan** (logika ownera + teksty; przed 14.10, emisją E3 Sword):
  - §6.3 według decyzji C1, z testem regresji na zapisanym mapowaniu Sword (stare vs nowe `raw_episodes`);
  - `aired`, `due_state` w `SubscriptionRow`;
  - usunięcie `done/watched/on_disk`;
  - teksty §6.1–§6.2.
  - Wykonawca logiki: astra; przegląd: inna rodzina. Teksty panelu: orkiestrator.
- **F2 — wspólna stopka:**
  - jedna funkcja budująca segmenty z tagami `ClickKind.KEY` i obsługą w `app._follow_click`;
  - hover segmentów;
  - `? klawisze`;
  - przepięcie panelu (`_keys`, `anime_view._key_lines`) i statusu `O`.
  - Testy: klik w każdy segment złotych stopek = ten sam efekt co klawisz (rozszerzenie sondy
    `tests/cli/test_panel_keys.py`).
- **F3 — S1/S2 w panelu i Anime:**
  - funkcje akcji ze stanem i zajętością (§4.3 według C1);
  - Historia pusta, szczegóły Biblioteki na wierszu informacyjnym/bez pliku, `Enter szczegóły` bez AniList ID;
  - `D dodaj` (D4), D → zakładka Anime (D5);
  - porządek dołu Historii (§4.1);
  - naruszenia Anime (inventory część B, tabela zbiorcza): między innymi `Space zaznacz · D pobierz` na wierszach
    nieemitowanych, w trakcie wysyłki, na dodatkach, na pustym i nieobsługiwanym wydaniu; `Enter` na zapowiedzi;
    `S subskrybuj` na zakończonym sezonie; `Z zakres` na filmie; wiersze objaśnień szkicu subskrypcji jako cel
    `Enter`/`Space`; `Enter/Esc wróć` (R2) na ekranie problemu;
  - pomoc `?` wypisuje tylko klawisze, które działają z miejsca, w którym ją otwarto;
  - **Nowa subskrypcja — za mało odcinków na ekranie** (zgłoszenie właściciela 2026-10-11, zrzut):
    - szkic pokazuje E1–E8, a pod listą zostaje puste miejsce;
    - nad listą stoją trzy puste linie (pod zakładkami, pod okruszkiem, pod zdaniem).
    - Docelowo szkic wypełnia wysokość jak inne tabele (`AnimeSnapshot.fill`, `anime_view.overflows`), z jedną
      pustą linią pod zakładkami i bez pustych linii między okruszkiem, zdaniem i listą.
  - **Ponowne pobranie** (zgłoszenie właściciela 2026-10-11, zrzut):
    - `D` na już zleconym odcinku zamienia cały ekran w PROBLEM „Odcinek już zlecony / P pobierz ponownie”
      (`anime_texts._REPEATABLE_REFUSALS`, `refused_result`); właściciel nie umiał pobrać ponownie inaczej.
    - Docelowo odmowa trafia do wiersza powiadomienia pod listą, lista zostaje.
    - `P` na liście odcinków od razu otwiera wydania do ponownego pobrania, z podpowiedzią w stopce (S1), gdy
      odcinek już był zlecony.
    - Przed zmianą sprawdzić, dlaczego `P` z listy nie zadziałało u właściciela (inventory B04, R1-P-NEW).
  - **zaznaczenie myszą w polu tekstowym** (zgłoszenie właściciela 2026-10-11): dziś przeciągnięcie w polu
    (wyszukiwarka, zakres, pola Ręcznego i Ustawień) zaznacza tekst ramki (`FrameSelection`), a nie bufor
    `TextInput`. Backspace kasuje wtedy jeden znak przy kursorze zamiast zaznaczenia. Docelowo przeciągnięcie
    zaczęte w polu zaznacza zakres w `TextInput` (kursor i kotwica z `TextInput.place`). Backspace/Delete
    usuwają zaznaczenie, pisanie je zastępuje, Ctrl+C/Ctrl+X kopiują/wycinają. Przeciągnięcie poza polem
    zostaje zaznaczeniem ramki. Test: przeciągnięcie przez cały tekst pola + Backspace daje puste pole.
- **F4 — Ustawienia, Ręczny, Home, wynik:** stopki S2/S3 przez tę samą funkcję co F2 (klikalne), naruszenia
  N01–N34 z kategorii R1/R2.
- **F5 — słownik R3:** teksty zaakceptowane w C2, ekran po ekranie; złote testy tekstów zmieniają się razem z nimi.

F2 przed F3/F4, bo obie przepinają stopki na nową funkcję. F1 jest niezależna i idzie pierwsza.

## 8. Weryfikacja

- Złote stopki i sonda klawiszy (`tests/cli/test_panel_keys.py`) rozszerzone o: brak segmentu przy niespełnionym
  warunku (S1), brak aliasów (S2), klik = klawisz (S4).
- Test ownera: `subscription_row` liczy `aired` dla celów w każdym stanie; numeracja Sword nie blokuje rekordu.
- Ręczny smoke właściciela po F1 i po F3 (lista z przykładami §6.2 na żywych subskrypcjach).

## 9. Checkpointy właściciela

- **C1 (przed F1):** §6.3 wariant A czy B; §4.3 wyszarzenie czy znikanie.
- **C2 (przed F5, a dla tekstów Subskrypcji przed F1):** słowa z §5.2 i §6.2, w rozmowie, ekran po ekranie:
  Subskrypcje → Przetwarzanie → Biblioteka → Anime → Ustawienia → Ręczny → Home/wynik.
- **C3 (po F3):** właściciel klika stopki i ocenia jeden dzień pracy z listą Subskrypcji.

## 10. Poza zakresem

- Integracja z MyAnimeList i strona w sieci (pomysł na przyszłość).
- Stan „obejrzany”, strzałka postępu (D8, D9).
- Zmiana kolorów i układu poza §4.3.
- H1 P1/P2 i inne odłożone sprawy pobierania.

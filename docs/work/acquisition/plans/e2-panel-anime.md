---
kind: plan
status: prototyp-do-odbioru
baseline: 4dc8f61
branch: work/acquisition/02-download
created: 2026-09-29
parent: e2-pobieranie.md
---

# Panel Anime: od nazwy do pobrania

## Do obejrzenia przez właściciela

Odbiór odbywa się na **działającym panelu i kolorowych PNG**, nie na ASCII.
Główny układ: 80×24; kontrolny: 50×24. Dane są demonstracyjne.

```powershell
uv run python scripts/tmp/anime_panel_demo.py
uv run python scripts/tmp/anime_panel_demo.py --center
```

Pierwsza komenda pokazuje wyszukiwanie u góry, druga pośrodku. Wpisz Slime
albo Solo Leveling → Enter → wybierz wpis → Enter. Space zaznacza odcinek,
A wszystkie/żadne, Z otwiera zakres; D symuluje wyszukanie sugestii i wynik.
Zaznacz 1 i 3: po około 1,5 s pierwszy dostaje zielony flash i Zlecono,
po kolejnych 1,5 s trzeci Brak wydania. I otwiera opcjonalną listę wydań.
Przeciągnij tekst przez kilka wierszy, Ctrl+C/C skopiuj, kliknij, by wyczyścić.
Sprawdź wklejenie do Notatnika. Esc wraca; `?` pokazuje pomoc.

PNG są w `../screens/`. Zobacz szczególnie M01a/M01b, M05, M08, M09
i zaznaczenie myszą. **Do wyboru pozostaje położenie pola M01 oraz odbiór
wyglądu i ergonomii. D1–D3 są już rozstrzygnięte.**

## 1. Cel i miara sukcesu

```text
Teraz: nazwa → katalog → odcinki → D → podgląd; pobieranie osobno przez G
Cel:   nazwa → płaska chronologia → odcinki → D → wynik przy odcinkach
```

Typowa ścieżka: trzy zatwierdzenia (nazwa+Enter, wpis+Enter, D). D wybiera
najlepszą sugestię istniejącej heurystyki dla każdego zaznaczonego odcinka;
bez zaznaczeń działa na kursorze. I jest opcjonalne. „Zlecono” oznacza
potwierdzone przyjęcie, nie zakończony transfer. Biblioteka wymaga dowodów F4.

Warunki: stabilna tabela, pełna data bez godziny, brak odcinkowych dodatków
S…, seedy widoczne także przy 50 kolumnach, brak domyślnych pustych statusów
zastąpionych zbędnymi etykietami, jednoznaczne Space/Enter i zachowane recovery.

## 2. Authority i baseline

Feedback właściciela z 29.09, druga runda, zastępuje starsze makiety oraz
rekomendacje D1–D3. Wcześniejsze review opus55 zakończyło się trzema drobnymi
uwagami U1–U3, poprawionymi przed commitem planu `4dc8f61`. Obecne zlecenie
zatwierdza wykonanie P1 i zmienia jego wymagania; nie oznacza odbioru wyglądu.

W drzewie równolegle powstaje F4: zmiany `application/**` i jego testów są
cudzą pracą. Nie edytować, nie stashować ani nie formatować. Aktualne API
przed P3 odczytać ponownie; niniejszy prototyp nie łączy się z rezydentem.

Zweryfikowane punkty integracji:
- `TerminalRenderer` w `prompts.py` jest jedynym ownerem Prompt Toolkit;
  przyjmuje Rich Text i przekazuje klawisze z `_NORMALISED_KEYS`.
- `_WheelControl` dotąd obsługiwał kółko; nowy opcjonalny callback pozwala
  przekazać drag bez zmiany zachowania pozostałych ekranów. Prompt Toolkit
  przekazuje kolumny znakowe: adapter zamienia je na komórki terminala.
- Ctrl+C jest normalizowane jako `interrupt`. W Anime oznacza powrót lub
  wyjście z edycji; wybrane pole kopiuje. Nowa selekcja tekstu przechwytuje
  Ctrl+C przed powrotem, brak selekcji zachowuje jego znaczenie.
- `TextInput` pozostaje wspólnym edytorem pola zapytania i zakresu.
- `main._default` tworzył `ResidentSession` przed `try/finally`; błąd startu
  dawał traceback i pomijał cleanup serwisu. Granica CLI ma zgłosić po polsku
  brak połączenia, wskazać `anishift watch status`, zamknąć serwis i wyjść 1.
- F3b udostępnia D/I/P/U05 i cztery stany właściciela; nie daje podstawy do
  pokazywania Gotowe/Przetwarzanie przed dowodami F4.

## 3. Zakres tej iteracji

**P1:** produkcyjny stan widoku, czysty render, obsługa klawiatury i myszy,
Windows clipboard, spinner/flash; interfejs wejściowy danych i callback
akcji; offline demo; PNG; testy; komunikat błędu startu; aktualizacja planu.

Zapis: `cli/interactive/**`, `cli/main.py` tylko błąd startu, `cli/AGENTS.md`,
`tests/cli/**`, niniejszy plan, `screens/` i niezacommitowane demo/helper
w `scripts/tmp/`. Bez nowych zależności i bez commita.

**Później:** P2/P2b projekcja pełnej franczyzy, P3 prawdziwe D/I/P/U05,
integracja nowego widoku z panelem, F4/F5 i odbiór E2. Obecna droga G pozostaje
działająca. Prototyp nie zastępuje jej i nie udaje prawdziwego pobierania.

Zakazane: `application/**`, `platform/**`, `services/**`, cudze testy F4,
`pyproject.toml`, zamrożone skrypty; prawdziwy qB/rezydent/config właściciela.
Testy wyłącznie z `-m "not integration"`.

## 4. Stała klatka i język wizualny

Ciemne tło, istniejąca paleta rozszerzona semantycznymi rolami. Niebieski
oznacza aktywność/wybór, fiolet kontekst, pomarańcz ostrzeżenie, zieleń
potwierdzenie. Cienkie separatory `─` rozdzielają obszary; bez diagramu,
maskotki, dodatkowych ramek każdego wiersza i dekoracyjnych liczników.

| Region | Położenie (wiersze od 1) |
| --- | --- |
| Zakładki | 1, pełne etykiety także przy 50 |
| Separator i kontekst | 2–3 |
| Nagłówki tabeli | 5 |
| Dane | zawsze od 6, bez pustego wiersza pod nagłówkami, przewijany środek |
| Separator dolny | H−3 przy 80, H−4 przy 50 |
| Zaznaczenia / edytor Z | H−2 przy 80, H−3 przy 50; zawsze rezerwacja |
| Informacja / wynik | H−1 przy 80, H−2 przy 50 |
| Klawisze | ostatni wiersz przy 80, dwa ostatnie przy 50 |

`Zaznaczone: 2 (1, 3)` jest **wyłącznie na dole**. Zerowy wybór zostawia
pustą rezerwację. Z zmienia tę samą dolną linię, nie położenie tabeli.
Nie ma licznika wyboru w I/P. Długie tytuły obcinać jednym `…`, na granicy
grafemu, według komórek terminala. Pełny wiersz dostępny przez C i szczegóły.
Minimalnie 50×12; poniżej komunikat powiększenia.

Aktywna zakładka ma wyłącznie wyróżnione tło, bez nawiasów. Informacja na dole
jest domyślnie pusta; pokazuje notice, detail, status albo pełny ucięty tytuł.
W wydaniach spacja oddziela `*`/`!` od checkboxa, a kolumny Obraz/Język/Seedy
dzielą co najmniej dwie spacje.

Stan zwykłego niezleconego odcinka i zakończonego wpisu pusty. Podczas
aktywnego wyszukiwania w kolumnie Stan akcentowany spinner `⠹ szukam`,
cykl `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`, bez nawiasów.
Bez napisu „Zlecam…”. Po potwierdzeniu Zlecono i zielone tło wiersza przez
400 ms; wynik w dolnej informacji (np. zielone `Zlecono 1`, bez `[ok]`). Flash wygasa,
status zostaje. Do F4 jedyna ścieżka przyjęcia: Zlecono → Pobrano.

Animacje 10 fps, stały rozmiar spinnera. Zegar dostarczany do renderu,
żadnego I/O ani mutacji danych w czystym rendererze. Prompt Toolkit
porównuje klatki i wysyła zmienione komórki, bez czyszczenia całego ekranu.
Limit redraw zawsze 30 fps, odświeżanie 100 ms; ignorowane ruchy myszy nie
wywołują callbacku. Panel usuwa wygasłe terminy flash i sam składa wyniki
partii, np. `Zlecono 1 · nie zlecono 3 · I wydania`. Typ komunikatu jest jawny.
Jednorazowy notice znika przy następnej nawigacji lub akcji.

## 5. Przepływ i klawisze

Wyniki pomijać wyłącznie, gdy wszystkie należą do widocznej franczyzy.
Jeden kompletny wpis może prowadzić bezpośrednio do odcinków. Niepełne dane
pozostają jawne. Awaria AniList nie uruchamia fallbacku; poprawny pusty
wynik może uruchomić istniejącą drogę Nyaa.

**Wszystkie powiązane wpisy:** sezony, filmy, OVA/ONA, specjale, spin-offy
i odcinki typu 7.5 na jednej liście, po premierze malejąco, zapowiedzi u góry.
P1 używa fixture. P2b rozbuduje projekcję z dedupe stabilnych tożsamości,
zachowaniem H1 i `identity_target`; numer 7.5 nigdy nie jest zaokrąglany ani
podawany do starego całkowitoliczbowego `EpisodeKey`. Pobranie wymaga
zweryfikowanego mapowania domenowego. Nowe odczyty/graf i mapowanie speciali
muszą być zaprojektowane w P2b przed implementacją, nie przez UI.

| Ekran / gest | Znaczenie |
| --- | --- |
| Góra/dół, PgUp/PgDn, Home/End | kursor; kółko przewija niezależnie |
| Pole zapytania | zwykły `TextInput`; Enter wyszukuje |
| Wpisy, Enter | odcinki danego wpisu |
| Odcinki, Space | zaznacz/odznacz; Enter nigdy nie zaznacza |
| Odcinki, A / Z | wszystkie dopuszczalne/żadne; zakres zastępuje wybór |
| Odcinki, D | jedna partia dla wyboru albo kursora, najlepsza sugestia per odcinek |
| Odcinki, I | opcjonalny odczyt wydań kursora, niezależnie od wyboru |
| Odcinki, P | jawne ponowienie; nigdy automatyczne zastąpienie D |
| Wydania, Space / D | jedno zaznaczenie / wybrane albo bieżące wydanie |
| Wydania, P | pod `?` oraz statusem `Zlecono | P pobierz ponownie`, poza klawiszami |
| Problem pliku | informacja `Nie ustalono pliku w paczce · Enter wskaż plik`; Enter → U05 |
| R-04, Enter | nazwane `pobierz mimo to`, dokładny pokazany wyjątek |
| U05, Enter | dokładny plik z obejrzanej rewizji |
| M18, Enter | `sprawdź wynik`: ten sam command ID i payload |
| M19, Enter | `odśwież`: odczyt, nigdy automatyczny wybór |
| Mysz, przeciąganie | tekst przez wiele wierszy, bez chrome i znaczników |
| Mysz, klik | wyczyść zaznaczenie tekstu i przesuń kursor na kliknięty wiersz; bez zaznaczania checkboxa |
| Ctrl+C / C z zaznaczeniem | kopiowanie tekstu do Windows; C tylko poza edytorem |
| C bez zaznaczenia | pełny wiersz kursora; w edytorze litera C |
| Ctrl+C bez zaznaczenia / Esc | dotychczasowy powrót/wyjście; nie anulowanie przyjętej pracy |
| ? | szczegóły, A/Z, kopiowanie, G/S do E3 |

Stopka odcinków przy 80:
`Space zaznacz | D pobierz | I wydania | P ponownie | ? więcej | Esc`.
Przy 50: `Space zaznacz | D pobierz | I wydania`, potem
`P ponownie | ? więcej | Esc`. Bez Enter. I: `Space zaznacz | D pobierz | ? więcej | Esc`.

## 6. M01–M20: kontrakty ekranów i dowody wizualne

Wszystkie widoki dziedziczą geometrię §4 i tekstową selekcję §7. PNG
zastępują ASCII jako materiał akceptacyjny; pozostałe stany opisane tutaj
są kontraktem P3, nie deklaracją gotowej integracji.

| Makieta | Obowiązujący widok / zachowanie | PNG / etap |
| --- | --- | --- |
| M01a | pole u góry, fokus od razu, Enter szukaj | `m01a-szukaj-gora.png` |
| M01b | to samo pole wyśrodkowane, identyczne działanie | `m01b-szukaj-srodek.png` |
| M02 | niepowiązane wyniki; Enter wybiera franczyzę, zapytanie zachowane | P2 |
| M03 | pełna płaska chronologia, zapowiedź/film/OVA/ONA/spin-off/7.5 | `m03-wpisy.png`; P2b dane |
| M04 | odcinki, puste domyślne stany i dolna rezerwacja wyboru | `m04-odcinki.png` |
| M05 | Space na 1 i 3; licznik na dole, tabela nieruchoma | `m05-zaznaczone.png` |
| M06 | Z edytuje dolną rezerwację; Enter stosuje, Esc odrzuca; błąd zachowuje wybór | demo Z |
| M07 | braille + szukam w wierszach aktywnej partii | `m07-d-spinner.png` |
| M08 | przyjęty wiersz: Zlecono, znika jego `[x]`, zielony flash 400 ms i wynik na dole | `m08-po-d-flash.png` |
| M09 | 1 przyjęty, 3 Brak wydania i nadal wybrany; informacja o częściowym wyniku | `m09-czesciowy.png` |
| M10 | wydania z obrazem/językiem/seedami, `*` sugestia i `!` wyjątek; bez P w stopce | `m10-wydania.png` |
| M11 | jawne P, poprzednie pliki zostają; konflikt legacy pokazany przed zatwierdzeniem | P3; demo tylko symulacja |
| M12 | R-04: wydanie, odcinek, pełny powód odstępstwa; Enter pobierz mimo to | P3 |
| M13 | U05: ścieżka względna i rozmiar, Enter wybiera dokładną rewizję/index/path/size | P3 |
| M14 | szczegóły i pomoc; C/Ctrl+C kopiuje selekcję, C bez niej pozycję | demo `?` |
| M15 | ładowanie odczytu bez zmiany geometrii; stare dane jawnie nieaktualne | P3 |
| M16 | błąd źródła z czasem cooldownu, nazwane Enter ponów | P3 |
| M17 | brak odcinków: `Nie znam odcinków tego wpisu`, D/I/P odmawiają | P3 |
| M18 | `Wynik nieznany`; wiersze Nieznany; Enter sprawdza tę samą intencję | P3 |
| M19 | zmieniona oferta/mapa: Enter odśwież, ponowny świadomy wybór po odczycie | P3 |
| M20 | przed F4 tylko Zlecono/Pobrano; Problem i Zlecony? nie cofają przyjęcia | P3; dalsze stany po F4 |
| Selekcja tekstu | odwrócone tło tylko nad tekstem; daty i wiele wierszy | `m-zaznaczenie-mysza.png` |
| 50 kolumn | pełna data/stan, skrócony tytuł, dwie linie klawiszy | `m-50kol-odcinki.png` |

Pauza: zwykła tabela i stopka, D dostaje `PAUSED`, informacja
`AniShift wstrzymany`; bez automatycznego ponowienia po wznowieniu.

## 7. Zaznaczanie tekstu i schowek

Renderer zwraca tekst i mapę selektowalnych grafemów. Tytuły, daty, numery,
statusy, nazwy wydań i wartości szczegółu są tekstem. Logo, zakładki, ramki,
separatory, kursor, checkboxy, znaczniki sugestii i spinner nie należą do mapy.
Przeciąganie zaznacza w porządku czytania, z końcem inkluzywnym w obu kierunkach;
odwrócone tło obejmuje tylko tekst, również ostatni wskazany znak.
Kopiowanie pomija odstępy layoutu i chrome, zachowuje podział na wiersze.
Klik czyści i przesuwa kursor na wiersz. Resize, zmiana widoku i scroll czyszczą selekcję współrzędnych,
żeby nie kopiować innego tekstu po przemieszczeniu. Nie wyłączamy obsługi myszy.
W edytorze zapytania i zakresu C zawsze wpisuje literę, także przy selekcji
myszy; kopiuje Ctrl+C. Potwierdzenia rozróżniają `Skopiowano wiersz` i
`Skopiowano zaznaczenie`. Demo przywraca stan przez metodę panelu czyszczącą
selekcję i mapę ostatniej klatki.

Granica Windows: `clip.exe`, stdin BOM `FF FE` + UTF-16LE, bez shell,
bez tekstu w argumentach i logach, z timeoutem. Sukces dopiero po kodzie 0;
błąd zostawia `Nie udało się skopiować`. Test dokładnych bajtów polskiego,
japońskiego tekstu i emoji. Test manualny: zaznacz kilka wierszy, Ctrl+C,
wklej do Notatnika. W tej iteracji helper w `cli/interactive/`, zgodnie
z zakazem zapisu do `platform/`.

## 8. Integracja E2 i inwarianty P3

API ownera: `episode_download(keys, command_id)`, `episode_offer(key,
repeat, previous_admission_id)`, `episode_choose(offer, candidate,
command_id, deviation_confirmed, conflict_confirmed)`, `episode_files`,
`episode_file_choose`, `episode_states`. I/P i choose używają tego samego
`ResidentSession._episode_interaction`; D głównego kanału.

- Jeden owner i jedna trwała prawda. UI ma wyłącznie draft, kursor, snapshot,
  pending ID/payload oraz krótkotrwały feedback; bez nowej historii/cache.
- D: 1–100 kluczy; ponad limit odmowa przed IPC. Ponowne D w trakcie nie
  tworzy nowego ID. Space/A/Z i nowe mutacje zablokowane do rozliczenia.
- I podczas partii odczytuje; zatwierdzanie oferty czeka na rozliczenie.
  Po nim refresh stanu/oferty, nigdy automatyczne zatwierdzenie.
- `[x]` znika po `episode_result(admitted)` danego odcinka, nie po końcu
  partii. Receipt całej partii i `episode_searching` nie są dowodem przyjęcia.
- Wynik nieznany: replay identycznego command ID/payloadu. Po restarcie
  bez ID odczyt stanów, bez zgadywania zakresu. Restart ownera nie wznawia reszty.
- Esc/Tab nie anuluje przyjętej pracy. Generacja chroni nawigację, command ID
  i klucz korelują wyniki również poza aktywną zakładką. Duplikat nie liczy dwa razy.
- R-04 jest oddzielne od zgody na P; exact candidate i konflikt powiązane
  z obejrzaną ofertą. Wykluczenie poprzedniej pary i ochrona plików pozostają.
- U05 respektuje rewizję. Nowa mapa wymaga odświeżenia i nowego świadomego
  wyboru. `event_too_large` blokuje mutacje, zachowuje ostatni widok.
- F3b: `not_ordered` → pusto / Nie wyemitowano według `aired`;
  `possibly_admitted` → Zlecony?; `ordered` → Zlecono;
  `downloaded` → Pobrano. Problem/Nieznany nie przywracają uprawnienia do D.
- Brak sugestii daje Brak wydania, nie twierdzenie o pustym źródle.
  Daty i czas nie dowodzą emisji, transferu ani gotowości pliku.

## 9. Architektura i mapa plików

```text
demo / przyszły adapter ResidentSession
  -> AnimePanel (wejście, callback akcji, przyjęcie wyników)
     -> AnimeViewState -> AnimeSnapshot
     -> render_anime -> AnimeFrame (Rich Text + tekstowe hit regions)
  -> TerminalRenderer (jedna aplikacja Prompt Toolkit, diff klatek)
```

| Operacja | Pliki | Rola |
| --- | --- | --- |
| CREATE P1 | `interactive/anime_state.py` | ulotny stan, DTO prezentacji, wybór |
| CREATE P1 | `interactive/anime_view.py` | czysta geometria i render 50/80/120 |
| CREATE P1 | `interactive/anime_panel.py` | klawiatura, mysz, callback akcji, feedback |
| CREATE P1 | `interactive/anime_clipboard.py` | Windows UTF-16 przez clip |
| MODIFY P1 | `interactive/{prompts,palette}.py` | opcjonalny mouse callback, tempo, role kolorów |
| MODIFY P1 | `cli/main.py`, `tests/cli/**` | bezpieczny błąd startu i regresje |
| CREATE lokalnie | `scripts/tmp/anime_panel_demo.py`, helper PNG | fixture bez sieci i capture VT |
| MODIFY P2/P3 | `interactive/{anime,state,app}.py` | integracja klatki i API, zachowanie G |
| P2b osobno | projekcja franczyzy w domenie | wszystkie wpisy i special mapping, bez regresji H1 |

PNG powstają offscreen z bufora **rzeczywistego wyjścia VT Prompt Toolkit**,
nie z drugiej makiety HTML. Helper odtwarza komórki i kolory ANSI, sprawdza
tekst komórek z produkcyjną klatką i rasteruje Pillow z fontami Windows.
Surowy ANSI zostaje lokalnie w `scripts/tmp/anime-captures/`.

## 10. Synchronizacja kontraktów

Po odbiorze prowadzący aktualizuje `ux.md`, `spec.md` W-/R-/P-/U-/Q-,
plan E2 F6 i `masterplan.md`: pełna chronologia, dolny licznik, selekcja
tekstu, flash i pozostanie po D. Nie kopiować backendu do UI. H1, dedupe,
receipts, R-04, U05, F4/F5/F7/F8, Library/Undo i prawdziwy odbiór zostają.

## 11. Fazy i bramki

| Faza | Wynik | Warunek przejścia |
| --- | --- | --- |
| P0 | rozstrzygnięcia właściciela zapisane | D1–D3 zamknięte poniżej |
| P1 | produkcyjny widok + offline demo + PNG + testy + start error | przegląd kodu innego modelu, właściciel przeklika i wybierze M01 |
| P2 | katalog i nawigacja, zachowane G/O | regresje legacy i powrotów |
| P2b | pełna franczyza i mapowanie speciali | dowód kompletności, dedupe, brak zmiany H1/identity_target |
| P3 | prawdziwe D/I/P/U05 i eventy | korelacja/recovery, testy IPC z atrapami; zaakceptowany backend |
| P4 | końcowy odbiór UI/E2 | F4/F5 oraz odrębne dowody F7/F8 i odsłuch |

Autor → testy → świeży recenzent innej rodziny → poprawki → weryfikacja.
Orkiestrator integruje. Brak narzędzia delegacji oznacza jawnie oczekujące
niezależne review, nigdy własne PASS w jego zastępstwie.

## 12. Strategia dowodu

- Render: 80/50/120, stała wysokość i położenie danych przy 0/1/wielu
  zaznaczeniach, błędzie i wynikach. CJK/emoji/grafemy bez rozcięcia.
- Input: Space/A/Z, brak Enter jako wyboru, D całą partią, limit 100,
  brak powtórnej mutacji podczas partii; query/range bez przechwytywania liter.
- Mysz: wiele wierszy, drag w obie strony, tylko tekst, klik czyści,
  Unicode i konwersja współrzędnych Prompt Toolkit, resize/scroll.
- Kopiowanie: Ctrl+C ma pierwszeństwo; C kopiuje tylko poza edytorem,
  bez selekcji cały wiersz;
  dokładne BOM+bajty, błąd/timeout bez sukcesu, bez selekcji Ctrl+C wraca.
- Feedback: spinner tylko przed wynikiem, czyszczenie pojedynczego wyboru,
  flash wygasa po 400 ms, status nie znika, porażka bez zielonego sukcesu.
- Start sesji: `ControlError` → polski komunikat, exit 1, cleanup, bez tracebacku;
  późniejsze błędy `run_interactive` nie są przedstawiane jako błąd startu.
- PNG: obejrzeć każdy; błędny font/kolumny/poprzecinany tekst poprawić przed oddaniem.

```powershell
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest tests/cli -m "not integration"
uv run pytest -m "not integration"
```

Błędy równoległego F4 raportować z lokalizacją, nie naprawiać. Bez pełnej
integracji i manualnego odbioru nie deklarować zakończenia E2.

## 13. Ryzyka i granice

P1 nie dowodzi faktycznego transferu ani pełnego grafu franczyzy. P2b musi
rozstrzygnąć źródła i tożsamości 7.5/speciali. P3 musi zachować sesyjność
ofert i replay receipts. Selekcja tekstu jest aplikacyjna; wymagany manualny
odbiór drag w Windows Terminal/VS Code i wklejenie Unicode. Błąd backendu
startu nie jest naprawiany przez komunikat CLI.

## 14. Rozstrzygnięcia właściciela

- **D1: TAK, zostać w odcinkach**; potwierdzenie jako flash 400 ms + wynik na dole.
- **D2: zaznaczanie tekstu myszą**; Ctrl+C i C do schowka Windows, bez selekcji C wiersz.
- **D3: TAK, wszystkie powiązane wpisy**, także spin-offy i 7.5; domena w P2b.
- Główny rozmiar 80; 50 działa. M01 u góry czy pośrodku: decyzja po PNG.

## 15. Odbiór

- [x] P1: testy i bramki rozliczone; 11 PNG obejrzanych; demo odtwarzalne.
- [ ] Niezależny przegląd kodu i manualny odbiór właściciela.
- [ ] Wybór M01 zapisany; kontrakty §10 zsynchronizowane przez prowadzącego.
- [ ] P2/P2b/P3 i F4/F5 zakończone; prawdziwy odbiór E2 osobno.

### Dowody pierwszej rundy P1 — 29.09.2026 (przed poprawkami review)

- `pytest tests/cli -m "not integration"`: **1136 passed** na końcowym kodzie.
- `pytest -m "not integration"`: **5745 passed, 18 skipped, 1 failed**.
  Jedyny fail: równoległy F4,
  `tests/application/test_selective_publication.py::test_episode_states_follow_an_episode_from_ordering_to_its_ready_set`,
  timeout `_settled(owner)` przy linii 397. Bez edycji tego obszaru.
- `mypy anishift/ tests/` i wariant `--platform linux`: **PASS**, 570 plików.
- `ruff check anishift/ tests/`: wyłącznie **T201/E501** w cudzym roboczym
  `tests/application/test_selective_publication.py:223`; format check wskazuje
  wyłącznie ten plik. Własny zakres bez błędów. `git diff --check`: PASS.
- Offscreen Prompt Toolkit: prawdziwe Enter, Space, strzałki, D, I podczas
  partii, Esc, sekwencje SGR drag i Ctrl+C przeszły smoke. Schowek w smoke
  zastąpiony odbiornikiem tekstu; dokładne bajty Windows sprawdza test.
- 11 PNG z bufora VT: tekst komórek zgodny z produkcyjną klatką; każdy PNG
  otwarty i obejrzany. Font japoński poprawiony przed finalnym eksportem.
- Kontrast 18 par tekst/tło (bazowe, aktywne, flash): **PASS**, minimum 4,93:1.
- Demo i helper są gitignored. Brak commita, uruchomienia rezydenta i qB.

Najnowszy przegląd opus55: **FAIL**, 12 uwag kodowych i V1–V7. Poprawki tej
rundy realizują powyższe kontrakty; wymagają ponownej weryfikacji recenzenta.
Nadal oczekujące: ponowny niezależny przegląd (brak narzędzia delegacji w sesji),
ręczne drag w terminalu właściciela i rzeczywiste wklejenie do Notatnika,
akceptacja wyglądu i wybór M01. PNG dowodzą renderu, nie transferu ani
fizycznej obsługi myszy w konkretnym hoście terminalowym.

### Dowody po poprawkach review — 29.09.2026

- Wprowadzone 12 poprawek kodowych i V1–V7; plan opisuje aktualny kontrakt.
- `uv run pytest tests/cli -m "not integration"`: **1151 passed**, 10,85 s.
  Regresje obejmują końcowy znak selekcji w obu kierunkach, `5-`, C w edytorze
  z selekcją myszy, usuwanie notice, wyniki partii, wygaszanie flash, klik
  przesuwający kursor, zmianę stanu oraz ograniczenie obsługi błędu startu.
- `uv run mypy anishift/ tests/` i `uv run mypy --platform linux anishift/ tests/`:
  **PASS**, po 570 plików.
- `uv run ruff check anishift/ tests/ --extend-exclude tests/application/test_selective_publication.py`:
  **PASS**. Identyczne wyłączenie w `ruff format --check`: **567 files already formatted**.
  Bez wyłączenia pozostają znane T201/E501 i format w cudzym F4:223.
- `git diff --check`: **PASS**.
- Wszystkie **11 PNG** przegenerowane z VT, zgodne komórka po komórce
  z klatką i otwarte do oględzin. Braille ma fallback Segoe UI Symbol
  w rasteryzatorze; początkowy brak glifu w Consolas poprawiony.
- Smoke prawdziwego wejścia Prompt Toolkit: **PASS**. Dodatkowy przebieg
  potwierdził 10 glifów spinnera bez czyszczenia całego ekranu między klatkami.
  Nie zastępuje to oceny płynności w terminalu właściciela.
- Kontrast 18 par tekst/tło: **PASS**, minimum **4,93:1**.
- Pełnego pytest nie powtarzano w tej rundzie; wynik wcześniejszy pozostaje powyżej.
- Ponowna weryfikacja recenzenta, manualny schowek i wybór M01 pozostają otwarte.

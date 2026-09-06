---
kind: specification
status: awaiting-owner-acceptance
baseline: 167a181 (work/local-automation/05-polish)
branch: work/local-automation/06-efficiency
created: 2026-09-06
updated: 2026-09-07
---

# Plan 06: Kolejka, widoczność, awarie, regeneracja, subskrypcje

Specyfikacja zamawianego zachowania. Zastępuje wersję „wydajnościową” odrzuconą przez właściciela 2026-09-06
(„liczby bez pokrycia, bez scenariuszy”). Nie ma tu liczb docelowych; są tylko pomiary z logu i sond, każdy ze
źródłem, oraz wartości domyślne oznaczone jako domyślne. Po akceptacji powstaje szczegółowy plan tylko dla etapu 06a.

## Ustalenia właściciela (obowiązujące)

- Wszystko przez aplikację terminalową `anishift` (menu, strzałki, Enter). Żadnych komend do pamiętania.
  Komendy CLI zostają jako narzędzie techniczne, nie jako droga użytkownika.
- Nowy odcinek wrzucony ręcznie do folderu ma pierwszeństwo przed wszystkim. Bieżący odcinek się kończy, potem
  od razu ręczne. Nie przerywamy w połowie.
- Powiadomienia Windows: gotowy odcinek, awaria wymagająca uwagi.
- W menu głównym zakładka ze stanem: co się robi, kolejka, subskrypcje, problemy, i stamtąd regeneracja oraz
  Auto/Ręczny per katalog.
- Subskrypcję można dodać (ekran Anime, klawisz O jak dziś) i anulować z aplikacji. Subskrypcja sama się kończy
  po ostatnim odcinku sezonu i jest to widoczne.
- Rytm subskrypcji: przed premierą nic; w oknie premiery często; spóźniona co godzinę; zakończona nigdy.
- qBittorrent nie musi działać stale, ale ręcznie otwartego nie wolno zamykać.
- Ma działać tak samo albo lepiej; zero nowych zależności; zero zmian w plikach i presetach.

## Jak jest dziś (sprawdzone w kodzie i logu 2026-09-06)

| Sytuacja | Dziś | Źródło |
| --- | --- | --- |
| Plik wrzucony w trakcie partii | czeka na koniec okna, potem idzie razem z resztą w kolejności folderów; bez pierwszeństwa | `cli/watch.py` `_watch_loop`, README „Watching the library” |
| Widoczność | okno terminala otwiera się przy każdej partii, po błędzie zamyka się po 10 s jak po sukcesie; poza tym tylko log | `interactive/app.py` `_finish_batch` |
| Grupa padła (LLM, TTS) | nie jest ponawiana do restartu czuwania albo zmiany pliku; rejestr partii żyje w pamięci | `application/watch.py` `WatchLedger` |
| Torrent bez seedów | wisi w kliencie bez końca; subskrypcja policzyła odcinek jako wzięty; nikt nie zgłasza | `subscriptions.py` `_advance` |
| LLM/TTS niedostępne | TTS 3 ponowienia w ramach zadania; LLM wywala grupę w tym oknie | log „TTS retry 1/3”, `translation_handler` |
| Regeneracja | brak; gotowy produkt liczy się jako zrobiony; nowy głos = ręczne kasowanie plików | `planning.py` (produkt musi być MISSING), `manual.py` |
| Subskrypcje w aplikacji | tylko dodanie (Anime, O); lista, anulowanie i sprawdzenie tylko z CLI | `anime.py`, `cli/main.py` `subs_*` |
| Koniec sezonu | subskrypcja pyta nyaa co godzinę bez końca | `subscriptions.py` `check_all` |
| Runda subskrypcji | 26 subskrypcji = 99 zapytań w 162 s; w tym czasie pętla nie skanuje i nie widzi stop; podczas partii subskrypcje nie są sprawdzane | log 22:43–22:45; `_watch_loop` |
| Rozruch okna partii | 14,5 s, z czego 11,4 s to `discover()`: pełne dekodowanie 83 plików lektora | log pid 32048; cProfile |
| Odcinek w partii | ~110 s: ekstrakcja ~5 s, LLM 48–69 s (grupy równolegle), TTS + miks ~15–20 s (grupy po kolei) | log pid 32048 |
| qBittorrent bezczynny | 101 MB, 342 węzły DHT, CPU także bez pobierań | Web API |
| Powiadomienie Windows | możliwe przez wbudowane API systemu z PowerShella, bez zależności | sonda 2026-09-06 23:4x (wysłane) |

## Model: jedno zadanie na odcinek

Wszystkie sytuacje sprowadzają się do listy **zadań** trzymanej na dysku (`config/queue.json`, zapis atomowy).
Zadanie = jedna grupa źródłowa (odcinek) + co ma z niej powstać. Pola: pochodzenie, priorytet, stan, powód, liczba
prób, termin następnej próby, czasy, hash torrenta (gdy czeka na pobranie).

| Pochodzenie | Priorytet | Skąd |
| --- | --- | --- |
| ręczne | 1 (najwyższy) | plik wrzucony do folderu; pojedynczy odcinek wybrany w Anime; „Auto/Ręczny dla tego katalogu” ze Stanu |
| subskrypcja | 2 | nowy odcinek obserwowanej serii |
| zaległości | 3 | zakres albo cały sezon zamówiony w Anime lub przy dodaniu subskrypcji |
| regeneracja | 4 (domyślnie), 1 gdy oznaczona „pilne” | ekran Stan → katalog → Regeneruj |

W tym samym priorytecie: starsze pierwsze.

| Stan | Znaczenie | Co dalej |
| --- | --- | --- |
| `czeka na pobranie` | torrent dodany, plik niekompletny | klient pobiera; po komplecie i 10 s ciszy → `w kolejce` |
| `w kolejce` | plik gotowy, czeka na swoją kolej | worker bierze najwyższy priorytet po skończeniu bieżącego |
| `w toku` | worker pracuje: etap i postęp widoczne | → `gotowy` albo `błąd` |
| `gotowy` | produkty presetu są obok źródła | powiadomienie; wpis zostaje w historii ekranu Stan |
| `błąd` | awaria przejściowa, powód i termin ponowienia | ponowienie według tabeli awarii |
| `wymaga uwagi` | ponowienia wyczerpane albo awaria trwała | powiadomienie; zostaje do decyzji właściciela (ponów / pomiń) |
| `anulowane` | właściciel anulował albo źródło zniknęło | wpis w historii |

Wywłaszczenie: worker kończy bieżące zadanie, potem bierze zadanie o najwyższym priorytecie, więc ręczny plik
wchodzi zaraz po bieżącym odcinku. Ile zadań naraz: decyzja D2.

Restart komputera albo czuwania: lista jest na dysku; `w toku` wraca do `w kolejce`, produkty częściowe z `temp/`
są odrzucane, produkty gotowe zostają (nic nie tłumaczy się drugi raz).

Praca dzieje się **w procesie czuwania**, bez otwierania okien terminala (decyzja D3). Czuwanie zapisuje co kilka
sekund `config/watch/state.json` (bieżące zadanie, etap, postęp, kolejka, problemy); aplikacja to czyta i pokazuje.

## Ekran „Stan” w menu głównym (nazwa: decyzja D1)

Sekcje, strzałki + Enter, Esc wraca:

| Sekcja | Co pokazuje | Enter na wierszu |
| --- | --- | --- |
| Teraz | bieżące zadanie: seria, odcinek, etap (ekstrakcja / tłumaczenie / lektor / miks), postęp; albo „czuwanie: nic do zrobienia”; albo „czuwanie wyłączone” | „czuwanie wyłączone” → włącz (rejestruje zadanie logowania jak `autostart enable`) |
| Kolejka | zadania w kolejności wykonania z pochodzeniem i stanem | anuluj / oznacz pilne / przesuń na początek |
| Problemy | `błąd` i `wymaga uwagi` z powodem i terminem ponowienia | ponów teraz / pomiń (anuluj) / pokaż szczegóły (ostatnie linie logu tego zadania) |
| Subskrypcje | seria, grupa, następny odcinek, stan i termin (patrz niżej) | szczegóły; sprawdź teraz; zmień następny odcinek; anuluj |
| Katalogi | każdy folder biblioteki z liczbą gotowych / brakujących / z problemem | Auto dla katalogu (preset domyślny, priorytet ręczny); Ręczny dla katalogu (dzisiejszy kreator ograniczony do tego folderu); Regeneruj |
| Historia | ostatnie zakończone i anulowane (domyślnie 50) | szczegóły |

Aplikacja nie musi być otwarta, żeby cokolwiek działało. Otwarta pokazuje stan na żywo.

## Regeneracja (ekran Stan → Katalogi → Regeneruj)

Kroki: katalog → odcinki (wszystkie / zakres jak „4-10” / zaznaczone) → co od nowa → potwierdzenie z liczbą
odcinków → zadania w kolejce.

| Co od nowa | Zachowane | Kiedy |
| --- | --- | --- |
| lektor | tłumaczenie | zmieniony głos, za cicho, inny miks |
| tłumaczenie i lektor | ekstrakcja | inny styl albo model tłumaczenia |
| wszystko | nic | podejrzenie uszkodzonych plików pośrednich |

Stare produkty nie są kasowane: lądują w `workspace/temp/regeneracja/<data-godzina>/<katalog>/`, a planer widzi
brak produktu i wytwarza go bieżącymi ustawieniami. Właściciel może wrócić do starych kopiując je z `temp/`.
Regeneracja zmienionej tylko głośności bez ponownego TTS: nie-cel (miks powstaje z klipów TTS, więc ponowny
lektor jest tą samą operacją).

## Awarie: wykrycie → stan → co widzisz → co robi program

Ponowienia rosnące (domyślnie: 5 min, 15 min, 1 h, potem co godzinę do 24 h) kończą się stanem `wymaga uwagi`
i powiadomieniem. Wartości domyślne do zmiany w Ustawieniach, nie w kodzie.

| Sytuacja | Wykrycie | Stan | Co widzisz | Co robi program |
| --- | --- | --- | --- | --- |
| Torrent bez seedów / utknął | brak postępu przez czas T (decyzja D5) | `czeka na pobranie · utknął od 14:02` | Problemy | szuka innego wydania tego odcinka: ta sama grupa inna jakość ≥ 1080p, potem inna dozwolona grupa; znalezione → podmienia torrent; brak → `wymaga uwagi` |
| qBittorrent niedostępny | Web UI nie odpowiada | pobierania `czeka na klienta` | Teraz: „klient torrent niedostępny od 12:03” | ponawia co 10 min; uruchamia klienta, gdy zarządzany (etap 06e); po 1 h powiadomienie |
| nyaa niedostępne | timeout / HTML zamiast RSS / 429 | subskrypcje `nyaa nie odpowiada` | Subskrypcje | pierwszy błąd w rundzie kończy rundę; ponowienie w następnym tiku rytmu; powiadomienie dopiero, gdy przez to minęło okno premiery |
| AniList niedostępne | 403 / timeout | brak wpływu na przetwarzanie | Anime: „AniList nie odpowiada” jak dziś | termin z historii publikacji grupy |
| LLM niedostępny / 429 / timeout | błąd etapu tłumaczenia | zadanie `błąd · LLM` | Problemy + Teraz: „tłumaczenie wstrzymane do 12:33” | po 2 kolejnych błędach LLM wstrzymuje etap tłumaczenia dla wszystkich zadań na czas ponowienia; inne etapy idą (ekstrakcja, lektor gotowych tłumaczeń) |
| TTS niedostępny | błąd etapu lektora po wewnętrznych 3 próbach | `błąd · TTS` | jak wyżej | jak LLM, dla etapu lektora |
| Brak miejsca na dysku | wolne < próg (domyślnie 5 GB) | nowe zadania `czeka na miejsce` | Teraz + powiadomienie | nie zaczyna nowych zadań i nie dodaje torrentów; gotowe produkty dostępne |
| Plik uszkodzony / ffmpeg nie czyta | błąd ekstrakcji lub inspekcji | `wymaga uwagi · plik` | Problemy | bez ponowień; ponów po podmianie pliku |
| Brak użytecznych napisów w MKV | inspekcja | `wymaga uwagi · brak napisów` | Problemy (dziś: cisza) | czeka na dołożenie napisów obok pliku (jak w Ręcznym) |
| Czuwanie padło / restart | start procesu | `w toku` → `w kolejce` | Historia: „czuwanie uruchomione ponownie” | wznawia kolejkę; nie tłumaczy gotowego ponownie |
| Źródło zniknęło | skan | `anulowane · plik usunięty` | Historia | usuwa zadanie; produkty nie są ruszane |
| Ten sam odcinek z dwóch grup | dwie grupy w bibliotece | dwa zadania | Kolejka | oba przetwarza (jak dziś); ostrzeżenie w Katalogach |
| Właściciel anuluje zadanie w toku | Enter → anuluj | `anulowane` | Kolejka | bieżący etap dokańcza się do bezpiecznego punktu (jak dzisiejsze anulowanie Auto), pliki pośrednie sprzątane |

## Powiadomienia Windows

| Zdarzenie | Treść |
| --- | --- |
| odcinek gotowy | „Mushoku Tensei S3 · odc. 12 gotowy” |
| wymaga uwagi | „Buchigire · odc. 10: tłumaczenie nie działa od 3 h” |
| subskrypcja zakończona | „Grand Blue S3: sezon zakończony, obserwacja wyłączona” |
| torrent utknął, brak zamiennika | „Yani Neko · odc. 10: pobieranie utknęło, brak innego wydania” |

Bez powiadomień o każdej próbie i o każdym sprawdzeniu. Wyłączane w Ustawieniach. Realizacja: wbudowane API
Windows z PowerShella, bez nowej zależności (potwierdzone sondą).

## Subskrypcje

### W aplikacji

- Dodanie: ekran Anime, klawisz O na numerowanym odcinku (jak dziś); od razu zaległości jako zadania priorytetu 3.
- Lista i akcje: ekran Stan → Subskrypcje: szczegóły, sprawdź teraz, zmień następny odcinek, anuluj.
- Koniec sezonu: gdy następny odcinek przekracza liczbę odcinków sezonu (AniList) albo grupa opublikowała
  końcowy odcinek (tytuł z „END”/„FIN” u SubsPlease/Erai-raws) — subskrypcja przechodzi w `zakończona`, nic już
  nie pyta, powiadomienie; wiersz zostaje widoczny (decyzja D4).
- Bez informacji o końcu: po N kolejnych przegapionych terminach subskrypcja przechodzi w `uśpiona · brak nowych
  odcinków od 2 tyg.` i nie pyta sama; „sprawdź teraz” ją budzi (N domyślnie 2).

### Rytm sprawdzeń (jak ustalono)

| Stan subskrypcji | Rytm |
| --- | --- |
| przed terminem | nic |
| okno premiery (od terminu − 10 min do terminu + 6 h) | co 10 min |
| spóźniona (okno minęło bez trafienia) | co godzinę |
| bez terminu | co godzinę |
| zakończona / uśpiona | nigdy samoczynnie |

Termin: AniList `nextAiringEpisode.airingAt` + opóźnienie grupy uczone z trafień (domyślnie 45 min), a gdy AniList
nie odpowiada — data ostatniej publikacji grupy z nyaa + odstęp między jej publikacjami (jeden odstęp wystarczy;
jedna publikacja → założone 7 dni, oznaczone „założone”). Sprawdzenie w oknie: jedno zapytanie feedu uploadera
(`?page=rss&u=<grupa>`, 75 najnowszych wydań grupy) obsługuje wszystkie subskrypcje tej grupy; zapytanie per seria
tylko dla luki w numeracji. Sprawdzenia biegną obok kolejki, nie blokują jej ani skanu.

## Oszczędności (dopiero po powyższym, bez liczb docelowych)

- Inspekcja z dysku: wynik inspekcji każdego pliku zapamiętany pod kluczem ścieżka + rozmiar + czas zmiany;
  nowy proces sonduje tylko zmienione pliki. Dziś rozruch to głównie dekodowanie każdego lektora.
- qBittorrent na żądanie: uruchamiany, gdy jest co pobrać; zamykany tylko gdy uruchomił go AniShift (ten sam PID),
  nic nie pobiera, nie ma cudzych aktywnych torrentów i minął czas bezczynności (domyślnie 10 min). Ręcznie otwarty
  nigdy. Ustawienie do wyłączenia.
- Ekran Anime: powtórne wejście w ten sam tytuł bez powtarzania zapytań; AniList z pamięci, gdy leży.
- Pomiar partii: TTS po jednej grupie naraz jest dziś wąskim gardłem; pomiar 1 vs 2 na kopii realnych odcinków,
  decyzja po wyniku.

## Nie-cele

VPS; nowe zależności; zmiana formatu produktów i presetów; zmiana silników; scraping HTML nyaa; inne klienty niż
qBittorrent; przerywanie zadania w połowie; miks głośności bez ponownego lektora; import listy MAL (osobna funkcja).

## Decyzje właściciela

| Nr | Pytanie | Rekomendacja |
| --- | --- | --- |
| D1 | Nazwa zakładki w menu: „Stan”, „Kolejka”, „Czuwanie”? | „Stan” |
| D2 | Ile zadań naraz: jedno (najszybsza reakcja na ręczny plik, dłuższa kolejka wolniej) czy dwa (LLM dwóch odcinków nakłada się, ręczny plik czeka najwyżej jeden odcinek dłużej)? | dwa |
| D3 | Okno terminala per partia: usunąć całkiem, czy zostawić jako opcję w Ustawieniach? | usunąć |
| D4 | Zakończona subskrypcja: znika sama po 7 dniach, czy zostaje aż ją usuniesz? | znika po 7 dniach |
| D5 | Po jakim czasie bez postępu torrent liczy się jako utknięty i szukamy zamiennika? | 6 h |

## Mapa etapów (po akceptacji szczegółowy plan tylko dla 06a)

| Etap | Zakres | Dowód końca (na żywo, sprawdzasz Ty) |
| --- | --- | --- |
| 06a Kolejka i Stan | zadania na dysku, worker w czuwaniu bez okien, priorytety i wywłaszczenie, wznowienie po restarcie, `state.json`, ekran Stan (Teraz, Kolejka, Katalogi z Auto/Ręczny, Historia), powiadomienie „gotowy” | wrzucasz plik w trakcie partii → w Stanie widzisz, że idzie zaraz po bieżącym; zamykasz aplikację, praca trwa; restart czuwania nie tłumaczy nic drugi raz |
| 06b Awarie | tabela awarii, ponowienia, `wymaga uwagi`, sekcja Problemy, powiadomienia o awariach, torrent utknął | odłączasz sieć na chwilę → Problemy pokazują powód i termin, po powrocie sieci odcinek się kończy sam |
| 06c Subskrypcje | sekcja Subskrypcje z akcjami, koniec sezonu, uśpienie, rytm premier, feed uploadera, sprawdzenia obok kolejki | najbliższa premiera: odcinek w kolejce w oknie premiery; anulujesz subskrypcję z aplikacji |
| 06d Regeneracja | Katalogi → Regeneruj z zakresem i trybem, stare produkty w `temp/` | zmieniasz głos, regenerujesz 3 odcinki, słuchasz |
| 06e Oszczędności | inspekcja z dysku, qBittorrent na żądanie, cache Anime, pomiar TTS | rozruch bez czekania; qBittorrent znika po pracy, ręcznie otwarty zostaje |

Każdy etap: szczegółowy plan → jeden wykonawca Opus po skillach `simple` i `coding` → bramki → przegląd diffu przez
prowadzącego → smoke na żywo → Twoje sprawdzenie z tabeli → PR stacked. Błąd lokalny → poprawka w etapie; fałszywe
założenie → przeplanowanie etapu; zmiana wymagania → do Ciebie.

## Authority

Właściciel 2026-09-06/07 (wypowiedzi w „Ustalenia właściciela”); spec local-automation R09, R11, R12, R13, R17, R18,
R23, R24, R25; masterplan 3.3 (kolejność tick), 10.1, 10.2, 10.4. Kod: `cli/watch.py`, `application/watch.py`,
`application/subscriptions.py`, `application/acquisition.py`, `cli/interactive/{app,home,manual,anime}.py`,
`application/planning.py`, `platform/qbittorrent_config.py`.

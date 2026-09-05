---
kind: review
status: historical
reviewed-state: Fable revision with lead corrections on main 6eef7d1
date: 2026-09-05
---

# Review pakietu planów

To review wcześniejszego projektu na 6eef7d1. Nie ocenia nowej wizji serwera
i katalogu ani nie wyznacza następnego zadania. Aktualne wejście: [README](README.md)
i [brief dla Pro](pro-brief.md). Poniższe findingi zachowano jako dowody tamtego etapu.

## Aktualny werdykt

**Pakiet nadaje się do oceny kierunku przez właściciela, nie do wdrożenia
wszystkiego naraz.** Plan 05 jest propozycją pierwszej ograniczonej iteracji.
Plan 01 czeka na O11 i dowód blokady E01. Plan 02 jest planem eksperymentu
E02 i kontraktem docelowym, a nie gotowym przepisem na downloader. Plan 03
oddziela zmiany dialogu od dowodu geometrii ASS. Żaden proof ani nowa funkcja
nie zostały wykonane w tej fazie.

Fable 5.1 przygotował research i dwie wersje planów bez dalszych agentów
w głównej pracy i rewizji. Prowadzący odczytał rezultat, kod i źródła;
nie przyjął deklaracji autora o zamknięciu wszystkich findingów bez sprawdzenia.
Rewizja nadal zawierała zatrzymany magnet jako handshake, późną kontrolę
symlinka, próbkę zamiast hasha całej treści i odłożone przez użytkownika
próby filmu/hard-kill. Prowadzący poprawił te punkty oraz rozdzielił decyzję
projektową od jeszcze nieuzyskanego dowodu technicznego.

| Finding | Wynik w aktualnych dokumentach | Co nadal warunkuje wykonanie |
| --- | --- | --- |
| 1: root i lease | Osobna tożsamość biblioteki, lease systemowy, jeden writer, konflikt także Manual/Auto | E01: dokładne zachowanie uchwytów i cleanup; brak domyślnej gwarancji katalogów sieciowych |
| 2: gotowość | Potwierdzenie albo przekazanie producenta; aktywne pobrania wyłączone z A/heurystyki | O11: potwierdzana kolejka nie udaje pełnej automatycznej wrzutki |
| 3: wersje | Pełny hash wejść, kanoniczny format, stale, ponowna kontrola przed done | Pomiar kosztu; kontrakt niezmienności wejścia, bez obietnicy exactly-once modelu |
| 4: źródła | Propozycja Search API klienta, ograniczony kontrakt i paginacja | O03 i przypięte wydanie; master nie dowodzi całego 5.x |
| 5: metadata/D06 | Wadliwą sekwencję zastąpił E02, walidacja surowej metadanej przed payloadem | Nie wdrażać pobierania bez dowodu; brak bezpiecznej ścieżki oznacza stop |
| 6: ownership/retry | Trwała intencja zamiast samego tagu, reconciliation, Retry-After, osobny monitor i idempotentny handoff | Testy fixture'ów i zgodność rzeczywistego klienta dopiero w realizacji |
| 7: ASS proof | Klatka referencyjna, próbki czasowe, przypięty font/licencja, rozróżnienie PlayRes/wideo | Brak kontaktu z krawędzią nie dowodzi braku overflow; wynik eksperymentu |
| 8: integralność/API | Oba warianty layoutu z diagnozami; TaskResult → agregator → RunResult → UI | O12 po proof; nie kopiować obcego tekstu jako kompletnego PL |
| 9: źródła | Poprawione koła PyPI, wersje, stan locka i granice dowodów z master | Przypięcie wersji klienta w E02; nie badano runtime użytkownika |
| 10: zakres | Osobne gałęzie, brak piątej akcji Home, brak obowiązku filmu/hard-kill teraz | Akceptacja właściciela; README z animacją dopiero na końcu stabilnego wydania |

Dodatkowo Plan 05 nie używa zagnieżdżonego serializera presetu jako płaskiej
mapy warunków. Reset dwóch plików nie obiecuje atomowości; test ma pokazać
rzeczywisty częściowy stan i możliwość ponowienia.

Zweryfikowano `ProducedArtifact.metadata`, `RunResult.warnings`, zakres
`RunSession` (katalog runu, nie cała biblioteka), `_encode_preset` i
`setting_is_active`. Odczytano również kontrolery qBittorrent master:
[torrents](https://raw.githubusercontent.com/qbittorrent/qBittorrent/master/src/webui/api/torrentscontroller.cpp),
[search](https://raw.githubusercontent.com/qbittorrent/qBittorrent/master/src/webui/api/searchcontroller.cpp)
(2026-09-05). Są dowodem dostępnych operacji w tym źródle, nie testem instalacji.

Nie zmieniono kodu aplikacji, testów, zależności ani materiałów runtime.
Nowy pakiet pozostaje lokalnym draftem na gałęzi planistycznej, bez commita,
push ani PR. Publikacja kodu przez PR #41 to osobna, zakończona operacja.

## Historia: uwagi do pierwszego draftu

## Zakres i wynik pierwszego przeglądu

Dokumenty Fable sprawdzono względem specyfikacji, źródeł i kodu. Pierwszy draft
nie jest gotowy do wykonania. Poniższe uwagi wracają do tego samego Fable 5.1;
bez dalszych agentów. Kod aplikacji nie jest zmieniany.

## Wymagane korekty

1. **Tożsamość biblioteki i blokada procesu (poważne).** `discovery.py:246`
   wywołuje `create_group_id(Path(), stem)`, więc sam `group_id` koliduje między
   różnymi katalogami zawierającymi tę samą nazwę. Ledger musi uwzględniać
   kanoniczną tożsamość root. Zwykły plik z PID nie jest atomową blokadą;
   plan jednocześnie odkłada blokadę między procesami i obiecuje odmowę drugiego.
   Wybrać rzeczywistą blokadę root obejmującą start wykonania ze wszystkich
   wejść (Manual/Auto/watch), albo jawnie wstrzymać uruchamianie przy konflikcie.
   Nie dopuszczać konkurencyjnego Manual do tych samych produktów jako
   bezpiecznego fallbacku. Atomowy replace nie chroni przed ostatnim błędnym writerem.
2. **Gotowość wejścia (poważne).** Okno spokoju i stały mtime nie dowodzą
   zakończenia kopiowania; obecny plan dopuszcza start prealokowanego pliku,
   co przeczy F02. Nazwać kontrakt: sygnał gotowości od producenta/atomowy final
   rename/jawne potwierdzenie, a heurystyczne wrzutki jako osobną propozycję z
   ograniczeniem do zatwierdzenia. Pliki zarządzane przez pobieranie muszą być
   wyłączone z heurystyki watchera aż do jednoznacznego przekazania przez klienta.
3. **Fingerprints i lifecycle (poważne).** Hash statów to nie hash treści.
   Wskazać granice gwarancji albo fingerprint treści po gotowości. Nie ustanawiać
   `repr(dataclass)` jako trwałego formatu; kanoniczna serializacja wybranych
   niesekretnych pól, wersja schematu, uporządkowane kolekcje. Uwzględnić wszystkie
   istotne źródła grupy, zmiany sidecar podczas runu, restart i brak produktów;
   nie oznaczać nowej wersji jako done na podstawie starego RunResult.
4. **Kontrakt źródła wyszukiwania (poważne).** Dowolny szablon RSS/JSON nie
   definiuje parsera. Wybrać jeden jawny format/wersję lub gotowe search API
   klienta, zweryfikować pola i paginację, resztę odłożyć. Nowa polityka D08
   jest propozycją, nie dotychczasowym wymaganiem użytkownika. Nowe błędy muszą
   przestrzegać hierarchii z `anishift/errors.py`, nie równoległej niejasnej hierarchii.
5. **Magnet i walidacja przed zapisem (poważne).** Zatrzymany magnet nie
   gwarantuje dostępności `torrents/files`. Rozpisać metadata-only handshake i
   bramkę dowodu dla docelowej wersji API przed startem danych. Bezpieczna nazwa
   z wyniku wyszukiwania nie dowodzi bezpiecznych nazw w środku torrenta. API
   `torrents/files` nie dokumentuje atrybutu symlinka; nie udawać, że wystarczy
   odrzucić pole `l` z tego endpointu. Niepewna metadana lub układ blokuje import.
6. **Ukończenie, retry i ownership pobierania (poważne).** `progress=1` i rodzina
   UP nie wystarczają dla wybranych plików i stanu stopped/completed. Ukończenie
   musi bazować na wybranych indeksach, sprawdzeniu dostępności/rozmiaru i braku
   moving/checking/error. Monitorowanie należy do use case'u, nie tylko otwartego
   widoku. Ponowne `add` po timeout wymaga rekoncyliacji, nie ślepego retry.
   Istniejący cudzy torrent o tym samym hashu nie staje się własnością AniShift.
   Nie planować delete, jeśli v1 potrzebuje tylko stop. `utils/_retry.py` nie
   parsuje `Retry-After`; backoff i retry metody POST wymagają jawnego kontraktu.
7. **Dowód ASS (poważne).** Jedna klatka nie bada move/transformacji/karaoke.
   Domyślne tło FFmpeg jest czarne, więc bbox „niebiałych pikseli” obejmuje całe
   tło. Analizować maskę różnicy wobec tła i próbki czasowe eventów, z ustalonym
   licencjonowanym fontem. Obraz przycięty do kadru nie dowodzi braku overflow;
   osobno określić możliwość pomiaru poza kadrem lub ograniczenie dowodu.
   Sam font zastępczy nie potwierdza geometrii oryginalnego fontu. Rozdzielić
   układ wideo/PlayRes i renderer użytkownika, nie narzucać zmiany jego ustawień.
8. **Integralność tłumaczenia i API layoutu (poważne).** Automatyczne kopiowanie
   nietłumaczonego karaoke jako kompletnego polskiego produktu łamie poprzednie
   naprawy integralności. Nie zmieniać tej polityki bez decyzji; dla niewspieranych
   eventów jawna odmowa/niepełny wynik i zachowanie źródła. Rysunki już są
   zachowywane. Rozstrzygnąć zwracanie diagnoz bez psucia publicznego `split_line`
   oraz dotarcie diagnozy do użytkownika. Końcówki czasowników i kapitalizacja
   nie są wiarygodną analizą składni; preferować mały korpus i ostrożne kary
   zamiast ogłaszać twarde reguły dla wszystkich nazw i szyków.
9. **Aktualność researchu (mniejsze, z wpływem na design).** Każdy istotny
   wiersz tabeli źródeł ma mieć bezpośredni URL i datę, nie samą nazwę serwisu.
   Prowadzący odczytał PyPI JSON przez HTTP: watchfiles 1.2.0 ma
   `watchfiles-1.2.0-cp314-cp314-win_amd64.whl`; libtorrent najnowsze 2.1.1,
   Windows wheels do cp313, bez cp314. Poprawić fałszywą niepewność pierwszego
   i starą wersję drugiego. Polling można rekomendować dla prostoty, nie z powodu
   nieistnienia koła. Unikać obszernego powtarzania tej samej dokumentacji API.
   `uv.lock` zawiera już `requests`, `urllib3`, `packaging` i `filelock` jako
   zależności pośrednie. Nie uzasadniać wyboru klienta twierdzeniem, że
   qbittorrent-api dopiero doda requests/urllib3 do locka; istotna jest nowa
   bezpośrednia zależność i koszt utrzymania wrappera kontra własnego klienta.
10. **Spójność dokumentów i zakres (mniejsze).** Lokalizacja docs/plans jest
    jawnie wybrana przez użytkownika; nie wymaga kolejnej zgody. Nie wprowadzać
    piątej akcji Home jako domyślnej zmiany; zaproponować wejście w istniejącym
    Auto/settings bez nowego redesignu. Nie ustanawiać dziesięciu nowych zgód
    na detale, które plan powinien rozstrzygnąć. Oznaczyć publiczne propozycje
    materialne jako niezatwierdzone. Odsłuch/pełny odcinek/hard-kill są odłożone;
    obecne plany mają automatyczny syntetyczny proof, nie obowiązek testów filmu
    od właściciela teraz. W A04 usunąć sprzeczność „równolegle/nie równolegle”.

## Dowody uzupełnione przez prowadzącego

- [PyPI watchfiles JSON](https://pypi.org/pypi/watchfiles/json),
  [PyPI libtorrent JSON](https://pypi.org/pypi/libtorrent/json): odczyt 2026-09-05.
- [mpv manual](https://mpv.io/manual/stable/): odczyt 2026-09-05. `sub-ass-override`
  opisuje no/yes/scale/force/strip; force/strip mogą niszczyć ASS.
  `sub-ass-force-margins` dopuszcza ASS w czarnych pasach (domyślnie no),
  `sub-use-margins` dotyczy plain text lub mocno nadpisanego ASS.
  Prowadzący odczytał te sekcje, więc ograniczenie fetch Fable nie blokuje tej części.
- [qBittorrent API](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-5.0%29):
  odczyt 2026-09-05, sekcja `torrents/files`: index/name/size/progress/priority,
  bez deklarowanego pola atrybutów BEP47.

## Nowe ustalenia właściciela do naniesienia

- Gotowy kod został scalony przez PR #41 do main jako `6eef7d1`; drzewo kodu
  jest identyczne z `369efcd`. Wszystkie kontrole CI PR-a przeszły. Plany są na
  `work/planning/automation-and-subtitles`; późniejsze etapy na osobnych gałęziach.
- Końcowy etap: README z animacją prawdziwego terminala (slime, menu, postęp),
  GIF lub animowany WebP po sprawdzeniu odtwarzania na GitHubie, bez danych
  prywatnych. Tylko zaplanować, po stabilizacji docelowego interfejsu.

## Warunek ponownego review

Fable aktualizuje pięć draftów i proponuje kompletne uzupełnienie Planu 05.
Prowadzący sprawdza poprawki i warunki stopu. Nie nazywać pakietu zatwierdzonym
ani implementacji wykonaną. Brak dowodu technicznego zamienić w krótki plan
eksperymentu, a nie szczegółowy plan oparty na zgadywaniu.

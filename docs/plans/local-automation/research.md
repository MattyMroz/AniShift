---
kind: research
status: proposed
updated: 2026-09-05
baseline: bc74425b487fb9110da76911c26dca4194b2aad9
implementation: not-executed
language: pl
---

# AniShift | research integracji, bibliotek i aktualnego kodu

## Wniosek

Najmniejsza spójna architektura dla opisanego zakresu to lokalny worker z SQLite, cienki adapter qBittorrent, katalog AniList oraz indeks Nyaa z RSS i ograniczoną historią HTML. Istniejący AppService wykonuje lektora, obecny terminal pozostaje interfejsem, a mpv odtwarzaczem. Jest to rekomendacja wynikająca z odczytu kodu i dokumentacji, nie demonstracja uruchomionego produktu.

Research przeprowadzono 5 września 2026 r. Najważniejsze źródła są oficjalną dokumentacją, kodem projektów i metadanymi wydań. Próby dostępu zakończone błędem są jawnie odnotowane. Nie ogłaszamy, że sprawdzono wszystkie istniejące programy lub każdą grupę fansubową.

## Co wynika bezpośrednio ze źródeł

**Obecny AniShift ma rdzeń, który warto reużyć.** AppService jest synchroniczną fasadą z planowaniem i wykonaniem. Obecne discovery jest płaskie, a ID grup nie tworzą globalnego katalogu wieloseryjnego. Dlatego projekt rozdziela katalogi rewizji zamiast zamieniać iterdir na rglob. Podstawa: S03–S06, S11–S14.

**LiveChart RSS nie jest kalendarzem przyszłych odcinków.** Oficjalny opis feedu episodes mówi o minionych 24 godzinach i braku nadchodzących epizodów. FAQ/RSS nie dostarczyły publicznego wspieranego API odpowiadającego potrzebie przyszłego harmonogramu. To brak znalezionego potwierdzenia API, nie dowód, że żadna prywatna integracja nie istnieje. Podstawa: S15–S16.

**AniList udostępnia odpowiednie dane katalogowe, ale wymaga ostrożnej integracji.** Oficjalne repo dokumentacji opisuje GraphQL. Limity zawierają nominalne 90/min oraz ostrzeżenie o ograniczeniu 30/min. Plan zaczyna od mniejszego własnego budżetu i honoruje odpowiedzi serwera. Warunki zabraniają masowego gromadzenia oraz konkurencyjnych usług list; nie pobieramy pełnego katalogu. Podstawa: S17–S19.

**qBittorrent udostępnia listę plików i sterowanie wyborem.** Dokumentacja opisuje indeksy, priorytety i stany. Dostępna dokumentacja wrappera latest była rozwojowa, a wybrane stabilne wydanie to 2026.8.1. Metadata-only, nazwy parametrów i per-file gotowość muszą być sprawdzone na konkretnej parze. Podstawa: S20–S22.

**Nyaa ma użyteczny RSS, lecz nie należy udawać stabilnego API JSON.** Źródłowy szablon podaje namespace, infoHash, kategorię, statystyki i link. Istniejący parser klienta pokazuje HTML i paginację, ale nie dowodzi, że każdy element wdrożonej strony jest identyczny z upstreamem. Podstawa: S23–S25.

## Porównanie rozwiązań

| Obszar | Rozwiązanie | Wybór | Uzasadnienie |
| --- | --- | --- | --- |
| Silnik pobierania | qBittorrent + WebUI | Użyć | Sterowanie lokalne i per-file bez własnego torrent engine. |
| Obecny klient właściciela | „BitTorrent”, dokładna aplikacja nieznana | Ustalić przy setupie | Nie wolno udawać zgodności dowolnego klienta z API qBit. |
| Biblioteka klienta | qbittorrent-api 2026.8.1 | Użyć po smoke | Przypięta zależność, wczesny proof krytycznych funkcji. |
| Katalog | AniList GraphQL | Użyć | Tytuły, aliasy, relacje i hint emisji w jednym adapterze. |
| Strona sezonowa | LiveChart | Pomocniczo | Przydatna właścicielowi do odkrywania; RSS nie odpowiada za przyszłe daty. |
| Główny indeks | Nyaa | Użyć | Zgodny z codziennym wyborem właściciela, wsparty kodem RSS i parserami. |
| Alternatywa | Publiczny RSS | Użyć jako drugi adapter | Minimalne rozszerzenie bez dokładania platformy indexerów. |
| Alternatywa | AnimeTosho Newznab | Kandydat | Opis API jest dostępny; caps i filtry nie zostały tu dowiedzione. |
| Terminalowe pobieranie | nyaa-cli | Referencja | Przepływ już istnieje; nie wprowadzamy drugiej historii i osobnego UI. |
| Terminalowe anime | anipy-cli | Referencja | Wybór/sezony/listy; pełna aplikacja byłaby zbyt dużą zależnością. |
| Nazwy wydań | Anitopy | Użyć za adapterem | Parser cech; nie traktować jako resolvera sezonów. |
| Fuzzy search | RapidFuzz | Użyć | Szybki ranking sugestii, jawna normalizacja i twarde reguły tożsamości. |
| Watcher | Mały okresowy skan inbox | Zaimplementować | Brak dodatkowej zależności systemowej; stan/recovery i tak wymagane. |
| Harmonogram | next_check_at w SQLite | Zaimplementować | Nie potrzeba drugiego schedulera cron ani APScheduler dla tej skali. |
| Trwały stan | SQLite stdlib | Użyć | Transakcje, unikalność, restart, indeksy, backup. |
| Trwały stan | Zestaw JSON last_episode | Odrzucić | Trudniejsze atomowe relacje komend, transferów, epizodów i produktów. |
| Orkiestracja | Celery/Redis/Docker | Nie wprowadzać | Nie daje wartości lokalnemu jednemu workerowi. |
| Odtwarzanie | mpv | Użyć jako zewnętrzny proces | Nie pisać playera, nie mylić jego końca z watched. |
| Lista właściciela | MAL XML | Opcjonalnie | Kontrolowany import lokalny bez przejmowania konta. |
| Lista właściciela | MAL OAuth/write API | Poza tą edycją | Niezweryfikowany bieżący kontrakt; brak udawanego live sync. |

Nie przeprowadzono pełnego benchmarku wszystkich alternatywnych managerów anime. W szczególności brak porównawczych testów Sonarr/Prowlarr/Jackett nie pozwala nazwać ich gorszymi; po prostu nie są potrzebną zależnością przy wybranym bezpośrednim Nyaa/RSS i istniejącym AniShift. Dodanie takiego systemu tworzyłoby dodatkowego ownera biblioteki i instalację do utrzymania.

## Co dokładnie reużyć z GitHuba

Z AniShift reużywamy fasadę AppService, composition root, modele intencji, rezultaty, existing media probe, klasyfikację produktów, scheduler, logger oraz TerminalRenderer. Nie kopiujemy ich do automation.

Z projektu qBittorrent korzystamy przez API i bibliotekę. Nie implementujemy wymiany pieces, trackerów lub seedowania.

Ze źródeł Nyaa korzystamy jako z kontraktu struktury RSS; istniejący parser qBit-plugins pomaga rozpoznać historyczny HTML. Nowy parser ma obsłużyć błędy, ograniczenia i niekompletną historię, a nie odziedziczyć każdą stałą ze skryptu.

nyaa-cli i anipy-cli są materiałem porównawczym dla przebiegu wyboru. Nie kopiujemy całych aplikacji terminalowych do repo. W odczytanym module MAL anipy są cudzy client_id oraz ścieżka password grant; tego nie wolno przenosić jako własnej integracji.

Anitopy i RapidFuzz są zależnościami, nie kodem do przepisywania ręcznie. Testujemy wersję z Python 3.14 i kontrolujemy model wyjścia we własnym cienkim adapterze.

Publiczny kod nie jest bezwarunkowym pozwoleniem na pominięcie licencji. Plan preferuje biblioteki i własne małe adaptery; gdy faktycznie przenoszony jest fragment, wykonawca sprawdza jego konkretną licencję i zachowuje wymagane informacje. Nie wykonywano audytu prawnego całej dystrybucji.

## Grupy, języki i jakość

Właściciel nie podał nazw dwóch używanych grup. SubsPlease i Erai-raws zostały sprawdzone jako kandydaci, lecz dostęp nie pozwolił na porównanie reprezentatywnych plików i odsłuch. Nie istnieje w tym badaniu wynik „grupa X najlepsza” ani potwierdzona narodowość grupy.

Praktyczna reguła wyboru to: poprawna seria/epizod, 1080p+, właściwa grupa według preferencji, pełna tekstowa ścieżka EN lub PL i dostępność wydania. Seeders i etykieta trusted nie dowodzą jakości tłumaczenia. Wielojęzyczne wydanie może być użyteczne, ale obecność EN trzeba sprawdzić w konkretnym pliku.

Gotowe polskie napisy można przyjąć lokalnie i ominąć tłumaczenie. Automatyczne wyszukiwanie napisów na dodatkowych niezweryfikowanych portalach nie jest konieczne dla zamówionego głównego przebiegu.

## Stabilność i koszt utrzymania

Najmniej zmienny fragment to lokalna baza, kontrolowana kopia i użycie istniejącego rdzenia. Najbardziej podatny na zmianę jest parser historycznego HTML Nyaa. RSS i oficjalne API mają czytelniejsze granice, ale nadal wymagają statusu błędu i prób kontraktowych.

Największy koszt implementacyjny to poprawna tożsamość serii/epizodu, per-file paczki, crash windows oraz wspólny lifecycle workera i obecnego Auto. Sam formularz wyszukiwarki jest mniejszą częścią zadania.

Nie podano ceny miesięcznej ani terminu implementacji. Lokalne przechowywanie obejmuje oryginał torrenta, kopię do obróbki oraz produkty, więc nie można liczyć tylko sumy rozmiarów torrentów. Rzeczywista przepustowość i zapotrzebowanie na dysk wymagają próby na docelowym sprzęcie.

Deklarowane darmowe klucze właściciela pozostają istniejącą konfiguracją. Nie potwierdzono nieograniczonej darmowości usług ani stałych limitów na przyszłość. Projekt respektuje limity i nie wprowadza automatycznego płatnego fallbacku.

## Luki i konsekwencje

| Luka | Co wiadomo | Konsekwencja w planie |
| --- | --- | --- |
| Dokładny klient „BitTorrent” | Nie podano nazwy/wersji | Setup potwierdza qBit albo download pozostaje niedostępny. |
| qBit metadata-only na stabilnym wrapperze | Są dokumentacja i kandydat API, brak runtime próby | T003 przed automatycznym batch add. |
| Wdrożone Nyaa parametry/paginacja | Odczyt upstreamu i istniejącego parsera | T004 zapisuje małą bieżącą próbę bez pobierania anime. |
| AniList aktualne odpowiedzi | Dokumentacja oficjalna, brak rzeczywistego zestawu odpowiedzi w pakiecie | T004 potwierdza query i nullability. |
| Anitopy na Python 3.14 | Wersja 2.1.1 jest starsza | T002 import i przypadki parsera; nie zakładamy zgodności z wieku pakietu. |
| Najlepsza grupa | Brak reprezentatywnego porównania | Wybór per seria/konkretne wydanie; brak fikcyjnego rankingu. |
| LiveChart przyszłe daty przez RSS | RSS ich nie zawiera | Nie wybieramy go jako głównego przyszłego kalendarza. |
| MAL bieżące API/auth | Oficjalne strony niedostępne w tej sesji | XML + lokalne watched, bez outbound sync. |
| Rzeczywisty eksport MAL właściciela | Nie otrzymano | T107 weryfikuje shape na wybranym eksporcie; opcjonalne. |
| Windows logon i monitor | Przeczytana dokumentacja | T098–T104 oraz P15 muszą przejść rzeczywiste próby. |
| Pełna kompletność dodatków | Katalog/indeks może czegoś nie znać | Mówimy o znanych epizodach, nie o kompletnej franczyzie. |

## Źródła i zakres odczytu

Poniżej rozdzielono treść źródła, zakres odczytu i granicę wniosku. Data badania: 2026-09-05. Link do dynamicznej strony nie jest sam w sobie przypięciem wersji wdrożenia.

<a id="s01"></a>

### S01. AniShift: przypięty commit

**Adres:** [AniShift: przypięty commit](https://github.com/MattyMroz/AniShift/commit/bc74425b487fb9110da76911c26dca4194b2aad9).

**Zakres / wersja / dostęp:** GitHub connector, commit z 2026-09-05 16:59:24 UTC.

**Ustalenie:** Zweryfikowany punkt odniesienia gałęzi work/planning/automation-and-subtitles; nie deklaracja aktualnego main.

<a id="s02"></a>

### S02. AniShift: instrukcje repozytorium

**Adres:** [AniShift: instrukcje repozytorium](https://github.com/MattyMroz/AniShift/blob/bc74425b487fb9110da76911c26dca4194b2aad9/AGENTS.md).

**Zakres / wersja / dostęp:** pełna lektura.

**Ustalenie:** Python 3.14, bramki root, uv, rozdzielenie workspace/config/logów; starszy zakaz nowych podfolderów wewnątrz workspace.

<a id="s03"></a>

### S03. AniShift: fasada AppService

**Adres:** [AniShift: fasada AppService](https://github.com/MattyMroz/AniShift/blob/bc74425b487fb9110da76911c26dca4194b2aad9/anishift/application/service.py).

**Zakres / wersja / dostęp:** istotny przepływ discovery, plan_auto, execute, cancel.

**Ustalenie:** Synchroniczna fasada i blokady wątkowe; nie ma w niej trwałej automatyzacji ani blokady między procesami.

<a id="s04"></a>

### S04. AniShift: discovery

**Adres:** [AniShift: discovery](https://github.com/MattyMroz/AniShift/blob/bc74425b487fb9110da76911c26dca4194b2aad9/anishift/application/discovery.py).

**Zakres / wersja / dostęp:** wiersze 1–260.

**Ustalenie:** Płaski skan; grupowanie po nazwie; ID oparte na Path() i stem. Samo zastąpienie iterdir przez rglob byłoby niebezpieczne.

<a id="s05"></a>

### S05. AniShift: composition root

**Adres:** [AniShift: composition root](https://github.com/MattyMroz/AniShift/blob/bc74425b487fb9110da76911c26dca4194b2aad9/anishift/bootstrap.py).

**Zakres / wersja / dostęp:** pełna lektura.

**Ustalenie:** AppContext oraz create_app_service pozwalają użyć istniejącego rdzenia dla osobnego katalogu odcinka.

<a id="s06"></a>

### S06. AniShift: wyniki produktów

**Adres:** [AniShift: wyniki produktów](https://github.com/MattyMroz/AniShift/blob/bc74425b487fb9110da76911c26dca4194b2aad9/anishift/application/results.py).

**Zakres / wersja / dostęp:** pełna lektura.

**Ustalenie:** GroupResult rozróżnia nowe i zachowane produkty; SUCCEEDED, PARTIAL, FAILED, CANCELLED nie są historią oglądania.

<a id="s07"></a>

### S07. AniShift: granica CLI

**Adres:** [AniShift: granica CLI](https://github.com/MattyMroz/AniShift/blob/bc74425b487fb9110da76911c26dca4194b2aad9/anishift/cli/AGENTS.md).

**Zakres / wersja / dostęp:** przepływy i pułapki UI; końcówka długiej odpowiedzi częściowo ucięta.

**Ustalenie:** Jeden renderer, brak I/O w renderze, obecne menu i kody wyjścia; nie traktować nieprzeczytanej końcówki jako audytu.

<a id="s08"></a>

### S08. AniShift: obecny terminal

**Adres:** [AniShift: obecny terminal](https://github.com/MattyMroz/AniShift/blob/bc74425b487fb9110da76911c26dca4194b2aad9/anishift/cli/interactive/app.py).

**Zakres / wersja / dostęp:** wiersze 1–255.

**Ustalenie:** Home ma Auto, Ręczny, Ustawienia, Wyjście; zamknięcie obecnej sesji anuluje jej własną pracę.

<a id="s09"></a>

### S09. AniShift: klawisze i geometria

**Adres:** [AniShift: klawisze i geometria](https://github.com/MattyMroz/AniShift/blob/bc74425b487fb9110da76911c26dca4194b2aad9/anishift/cli/interactive/prompts.py).

**Zakres / wersja / dostęp:** wiersze 1–160.

**Ustalenie:** Klawiatura obejmuje Space, Enter i strzałki; menu ma stałe budżety wysokości wymagające dostosowania.

<a id="s10"></a>

### S10. AniShift: zależności

**Adres:** [AniShift: zależności](https://github.com/MattyMroz/AniShift/blob/bc74425b487fb9110da76911c26dca4194b2aad9/pyproject.toml).

**Zakres / wersja / dostęp:** wiersze 1–150.

**Ustalenie:** httpx, Prompt Toolkit, Typer, Rich i biblioteki napisów już istnieją; projekt wymaga Python 3.14+.

<a id="s11"></a>

### S11. AniShift: workspace

**Adres:** [AniShift: workspace](https://github.com/MattyMroz/AniShift/blob/bc74425b487fb9110da76911c26dca4194b2aad9/anishift/config/workspace.py).

**Zakres / wersja / dostęp:** pełna lektura.

**Ustalenie:** Kontrolowany temp i usuwanie wyłącznie rozpoznanych osieroconych katalogów; PID nie jest globalnym lockiem.

<a id="s12"></a>

### S12. AniShift: zasady application

**Adres:** [AniShift: zasady application](https://github.com/MattyMroz/AniShift/blob/bc74425b487fb9110da76911c26dca4194b2aad9/anishift/application/AGENTS.md).

**Zakres / wersja / dostęp:** pełna lektura.

**Ustalenie:** Nie dublować schedulera; utrzymać istniejącą współbieżność i publikację produktów.

<a id="s13"></a>

### S13. AniShift: wspólny Auto w CLI

**Adres:** [AniShift: wspólny Auto w CLI](https://github.com/MattyMroz/AniShift/blob/bc74425b487fb9110da76911c26dca4194b2aad9/anishift/cli/run.py).

**Zakres / wersja / dostęp:** pełna lektura.

**Ustalenie:** prepare_auto_run wybiera wszystkie gotowe grupy; nowa domena nie powinna importować CLI.

<a id="s14"></a>

### S14. AniShift: wybór źródeł

**Adres:** [AniShift: wybór źródeł](https://github.com/MattyMroz/AniShift/blob/bc74425b487fb9110da76911c26dca4194b2aad9/anishift/application/selection.py).

**Zakres / wersja / dostęp:** pełna lektura.

**Ustalenie:** group_is_ready oznacza obecność tekstu, nie potwierdza pełnych angielskich dialogów.

<a id="s15"></a>

### S15. LiveChart FAQ

**Adres:** [LiveChart FAQ](https://www.livechart.me/pages/faq).

**Zakres / wersja / dostęp:** oficjalna strona dostępna w przeglądarce; bez deklaracji aktualizacji treści.

**Ustalenie:** Nie znaleziono publicznego wspieranego API; FAQ kieruje do RSS.

<a id="s16"></a>

### S16. LiveChart RSS

**Adres:** [LiveChart RSS](https://www.livechart.me/pages/rss).

**Zakres / wersja / dostęp:** oficjalna dokumentacja feedów.

**Ustalenie:** Feed episodes obejmuje minione 24 h i nie zawiera nadchodzących odcinków; obsługuje warunkowe zapytania.

<a id="s17"></a>

### S17. AniList API: dokumentacja

**Adres:** [AniList API: dokumentacja](https://github.com/AniList/docs).

**Zakres / wersja / dostęp:** oficjalne repozytorium dokumentacji.

**Ustalenie:** GraphQL i informacje o anime/emisjach; dokładne zapytania muszą przejść wczesny test kontraktowy.

<a id="s18"></a>

### S18. AniList: limity

**Adres:** [AniList: limity](https://github.com/AniList/docs/blob/master/docs/guide/rate-limiting.md).

**Zakres / wersja / dostęp:** odczyt przez GitHub; blob 6b71f4b79dd09b898d0565790f7177e07facaef4.

**Ustalenie:** Dokumentacja podaje nominalne 90/min i ostrzeżenie o ograniczeniu do 30/min; honorować nagłówki, Retry-After i reset.

<a id="s19"></a>

### S19. AniList: warunki użycia

**Adres:** [AniList: warunki użycia](https://github.com/AniList/docs/blob/master/docs/guide/terms-of-use.md).

**Zakres / wersja / dostęp:** odczyt przez GitHub; blob 21add4053435988a68c78d7a62284a7574c6207c.

**Ustalenie:** Zakaz masowego gromadzenia i usług konkurencyjnych; lokalna integracja ma być komplementarna, nie kopią całej bazy.

<a id="s20"></a>

### S20. qBittorrent WebUI API 5.0

**Adres:** [qBittorrent WebUI API 5.0](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-5.0)).

**Zakres / wersja / dostęp:** oficjalne API; żywa wiki, nie kontrakt dowolnej wersji.

**Ustalenie:** Sterowanie transferami, listy plików z indeksami, priorytety, stany; wymagana negocjacja wersji.

<a id="s21"></a>

### S21. qbittorrent-api 2026.8.1

**Adres:** [qbittorrent-api 2026.8.1](https://pypi.org/project/qbittorrent-api/2026.8.1/).

**Zakres / wersja / dostęp:** stabilne wydanie 2026-08-16.

**Ustalenie:** Wybrany wrapper; opis deklaruje qBittorrent 5.2.3/API 2.15.1. Nie dowodzi instalacji klienta u użytkownika.

<a id="s22"></a>

### S22. qbittorrent-api: torrenty

**Adres:** [qbittorrent-api: torrenty](https://qbittorrent-api.readthedocs.io/en/latest/apidoc/torrents.html).

**Zakres / wersja / dostęp:** dostępna dokumentacja wersji rozwojowej; oznaczona jako pomocnicza.

**Ustalenie:** stop_condition MetadataReceived i priorytety plików wymagają sprawdzenia na przypiętej parze. Nie przenosić nowych funkcji dev do planu jako pewnych.

<a id="s23"></a>

### S23. Nyaa: kod serwisu

**Adres:** [Nyaa: kod serwisu](https://github.com/nyaadevs/nyaa).

**Zakres / wersja / dostęp:** repozytorium źródłowe, bez gwarancji wersji wdrożonej na nyaa.si.

**Ustalenie:** Wzorzec parametrów i formatu; nie publiczne stabilne JSON API.

<a id="s24"></a>

### S24. Nyaa: szablon RSS

**Adres:** [Nyaa: szablon RSS](https://github.com/nyaadevs/nyaa/blob/master/nyaa/templates/rss.xml).

**Zakres / wersja / dostęp:** odczyt przez GitHub; blob 3f5a0077680794eb2c6e1cd548d313b8620fab6b.

**Ustalenie:** RSS udostępnia tytuł, guid, pubDate, infoHash, kategorię, rozmiar i statystyki. Link bywa magnetem albo .torrent.

<a id="s25"></a>

### S25. Nyaa: istniejący parser klienta

**Adres:** [Nyaa: istniejący parser klienta](https://github.com/MadeOfMagicAndWires/qBit-plugins/blob/main/engines/nyaasi.py).

**Zakres / wersja / dostęp:** przeczytany kod wersji 1.3, 195 linii.

**Ustalenie:** HTMLParser, linki /view/, paginacja p i filtry; referencja, nie kod do bezmyślnego skopiowania.

<a id="s26"></a>

### S26. nyaa-cli

**Adres:** [nyaa-cli](https://github.com/metaory/nyaa-cli).

**Zakres / wersja / dostęp:** README i opis przepływu.

**Ustalenie:** Istniejący terminalowy workflow subskrypcji/jakości/grup; nie wprowadzać drugiej historii obok AniShift.

<a id="s27"></a>

### S27. anipy-cli

**Adres:** [anipy-cli](https://github.com/sdaqo/anipy-cli).

**Zakres / wersja / dostęp:** README i struktura projektu.

**Ustalenie:** Wzorce terminalowego wyboru/sezonów/pobierania; całej aplikacji nie osadzamy jako zależności.

<a id="s28"></a>

### S28. anipy-api: moduł MAL

**Adres:** [anipy-api: moduł MAL](https://github.com/sdaqo/anipy-cli/blob/master/api/src/anipy_api/mal.py).

**Zakres / wersja / dostęp:** wiersze 1–240; blob b1b8c7f442f34881214056b09f60125c48dccf6a.

**Ustalenie:** Przykład modeli listy, lecz zawiera cudzy client_id i password grant. Tych rozwiązań nie przenosić.

<a id="s29"></a>

### S29. AnimeTosho: informacje o API

**Adres:** [AnimeTosho: informacje o API](https://animetosho.org/about).

**Zakres / wersja / dostęp:** oficjalna strona; endpoint caps nie został odczytany.

**Ustalenie:** API typu Newznab jest kandydatem na drugi indeks; sam opis nie stanowi dowodu działania konkretnych parametrów.

<a id="s30"></a>

### S30. Anitopy

**Adres:** [Anitopy](https://pypi.org/project/anitopy/).

**Zakres / wersja / dostęp:** stabilne 2.1.1 z 2022-07-24.

**Ustalenie:** Parser cech nazw wydań. Nie rozstrzyga tożsamości serii ani poprawności numeracji.

<a id="s31"></a>

### S31. RapidFuzz

**Adres:** [RapidFuzz](https://pypi.org/project/RapidFuzz/).

**Zakres / wersja / dostęp:** 3.14.6; Windows cp314 wheel z 2026-08-30.

**Ustalenie:** Fuzzy matching; normalizacja wejścia jawna. Wynik podobieństwa nie jest zgodą na pobieranie.

<a id="s32"></a>

### S32. defusedxml

**Adres:** [defusedxml](https://pypi.org/project/defusedxml/).

**Zakres / wersja / dostęp:** dokumentacja projektu, stabilna linia 0.7.1.

**Ustalenie:** Bezpieczniejszy parser XML; dodatkowo potrzebny limit odpowiedzi, liczby rekordów i dekompresji.

<a id="s33"></a>

### S33. SQLite WAL

**Adres:** [SQLite WAL](https://sqlite.org/wal.html).

**Zakres / wersja / dostęp:** oficjalna dokumentacja.

**Ustalenie:** WAL na lokalnym filesystemie; jeden writer transakcyjny. Nie umieszczać aktywnej bazy na udziale sieciowym/synchronizowanym.

<a id="s34"></a>

### S34. Python 3.14 sqlite3

**Adres:** [Python 3.14 sqlite3](https://docs.python.org/3.14/library/sqlite3.html).

**Zakres / wersja / dostęp:** oficjalna dokumentacja.

**Ustalenie:** Parametry SQL, transakcje, backup i jawne połączenia per wątek.

<a id="s35"></a>

### S35. Windows Task Scheduler: schtasks create

**Adres:** [Windows Task Scheduler: schtasks create](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/schtasks-create).

**Zakres / wersja / dostęp:** oficjalna dokumentacja Microsoft.

**Ustalenie:** ONLOGON, kontekst bieżącego użytkownika, interactive token i najmniejsze uprawnienia.

<a id="s36"></a>

### S36. Windows: nazwy i ścieżki

**Adres:** [Windows: nazwy i ścieżki](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file).

**Zakres / wersja / dostęp:** oficjalna dokumentacja Microsoft.

**Ustalenie:** Nazwy zastrzeżone i reguły ścieżek; sanitizacja nie może być jedyną ochroną przed wyjściem poza root.

<a id="s37"></a>

### S37. Python subprocess

**Adres:** [Python subprocess](https://docs.python.org/3.14/library/subprocess.html).

**Zakres / wersja / dostęp:** oficjalna dokumentacja.

**Ustalenie:** Lista argumentów, bez shell=True, jawny cwd i lifecycle procesu.

<a id="s38"></a>

### S38. mpv manual

**Adres:** [mpv manual](https://mpv.io/manual/stable/).

**Zakres / wersja / dostęp:** oficjalny manual.

**Ustalenie:** Odtwarzacz zewnętrzny; zakończenie procesu nie jest dowodem obejrzenia odcinka.

<a id="s39"></a>

### S39. MAL API v2

**Adres:** [MAL API v2](https://myanimelist.net/apiconfig/references/api/v2).

**Zakres / wersja / dostęp:** strona niedostępna dla narzędzia badawczego.

**Ustalenie:** Brak potwierdzenia bieżącego kontraktu API; integracja sieciowa ma oddzielną bramkę, nie udajemy zweryfikowanego OAuth.

<a id="s40"></a>

### S40. MAL authorization

**Adres:** [MAL authorization](https://myanimelist.net/apiconfig/references/authorization).

**Zakres / wersja / dostęp:** strona niedostępna dla narzędzia badawczego.

**Ustalenie:** Nie zakładać obsługi PKCE S256 ani kopiować client_id. W tym zakresie dostarczamy import XML i lokalny postęp, nie automatyczny zapis MAL.

<a id="s41"></a>

### S41. SubsPlease

**Adres:** [SubsPlease](https://subsplease.org).

**Zakres / wersja / dostęp:** dostępna tylko prosta strona wyszukiwania.

**Ustalenie:** Kandydat do preferencji grup, nie zweryfikowany zwycięzca porównania jakości.

<a id="s42"></a>

### S42. Erai-raws

**Adres:** [Erai-raws](https://www.erai-raws.info).

**Zakres / wersja / dostęp:** witryna zwróciła błąd przy próbie odczytu.

**Ustalenie:** Nie potwierdzono jakości ani aktualnych formatów; grupa wybierana na podstawie konkretnego wydania i ścieżek napisów.

<a id="s43"></a>

### S43. AniShift: intencje produktu

**Adres:** [AniShift: intencje produktu](https://github.com/MattyMroz/AniShift/blob/bc74425b487fb9110da76911c26dca4194b2aad9/anishift/application/intents.py).

**Zakres / wersja / dostęp:** pełna otrzymana treść; odczyt żądany dla wierszy 1–260.

**Ustalenie:** GroupIntent MANUAL może wskazać konkretny track/artifact. AutoPreset nie przyjmuje takich ID; automatyzacja może programowo zbudować precyzyjną intencję i wykonać ją bez ekranu ręcznego.

## Materiały dostarczone przez właściciela

`Wklejony kod markdown(1).md`: wcześniejsza wizja, masterplan audytu i brief jednego wycinka. Został wykorzystany do rozpoznania historycznych granic, a nie do odrzucenia obecnego pełnego zakresu.

`Badanie AniShift TUI.txt`: historyczna propozycja interfejsu. Aktualny kod ma pierwszeństwo w ustaleniu, co jest już wdrożone.

`skills.zip`: źródło bieżących skilli planowania, researchu i specyfikacji. Wykorzystano simple, research, specification, masterplan, planning, workflow, coding, subagent i review oraz właściwe referencje/szablony. Nie wykonywano delegacji do subagentów tylko dlatego, że przeczytano jej instrukcję.

`wip.zip`: wcześniejszy pakiet skilli, nie aktualny checkout aplikacji. Kod AniShift został odczytany z dostępnego repozytorium GitHub, nie wymyślony na podstawie zawartości archiwum.

## Czego to badanie nie dowodzi

Nie pobrano i nie przetworzono żadnego rzeczywistego odcinka użytkownika. Nie uruchomiono jego Windows, qBittorrent, autostartu, TTS ani kont. Nie wykonano pełnego suite repozytorium. Nie potwierdzono wszystkich prywatnych konfiguracji i nie odczytano jego listy MAL. Pakiet zawiera ścieżki przeprowadzenia tych prób, a nie fikcyjne wyniki.

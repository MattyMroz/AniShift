---
kind: technical-brief
status: proposed
updated: 2026-09-05
baseline: bc74425b487fb9110da76911c26dca4194b2aad9
implementation: not-executed
language: pl
---

# AniShift | brief technologiczny i decyzje wdrożeniowe

## Rezultat

Wybór anime albo drop pliku uruchamia lokalny przebieg: pozyskanie kompletnego źródła, kontrolowana kopia, obecne Auto, uporządkowana biblioteka i Oglądaj. Subskrypcja usuwa cotygodniowe wyszukiwanie oraz ponowne uruchamianie obróbki. To jest jeden zakres do wykonania, nie plan samej wyszukiwarki.

## Stos

| Element | Technologia / wersja | Status |
| --- | --- | --- |
| Język i pakowanie | Python 3.14+, uv | Obecny projekt; S10. |
| Interfejs | Prompt Toolkit, Rich, Typer | Reużycie obecnego kodu; bez zmiany frameworka. |
| Przetwarzanie | AppService + GraphScheduler | Reużycie obecnego Auto i ręcznych intencji; S03, S12, S43. |
| HTTP katalogu/indeksu | Istniejący httpx | Mały wspólny adapter, budżet per host. |
| Trwały stan | sqlite3 ze stdlib, WAL | Lokalny dysk; bez ORM i serwera bazy. |
| Torrent client | qBittorrent z WebUI loopback | Wybrany backend; nazwa/wersja obecnego klienta właściciela nieznana. |
| Wrapper | qbittorrent-api==2026.8.1 | Nowa przypięta zależność; wymaga testu pary klient/wrapper. |
| Parser nazw wydań | anitopy==2.1.1 | Nowa zależność; parser cech, nie resolver tożsamości. |
| Ranking nazw | RapidFuzz==3.14.6 | Nowa zależność; fuzzy wyłącznie porządkuje propozycje. |
| XML/RSS/MAL XML | defusedxml==0.7.1 | Nowa zależność plus limit body i rekordów. |
| Katalog i hint emisji | AniList GraphQL | Publiczny odczyt, cache tylko używanych danych. |
| Nowe/historyczne wydania | Nyaa RSS + ograniczony HTML | Dwa tryby tego samego indeksu. |
| Drugie źródło | Jawnie skonfigurowany publiczny RSS | Jeden mały adapter, brak dynamicznych pluginów. |
| Autostart | Windows Task Scheduler | Przy logowaniu użytkownika, po zgodzie. |
| Monitor | Obecny terminal uruchamiany osobno | Najwyżej jedno okno na partię. |
| Oglądanie | Lokalny mpv | Zewnętrzny proces, bez własnego playera. |

Przypięcia nowych zależności są decyzją z badania na dzień 2026-09-05. Nie wymuszają upgrade wszystkich istniejących pakietów. Polecenie do wykonania dopiero w środowisku implementacyjnym:

```bash
uv add 'qbittorrent-api==2026.8.1' 'anitopy==2.1.1' 'RapidFuzz==3.14.6' 'defusedxml==0.7.1'
```

Lock należy wygenerować uv oraz przetestować na Windows/Python 3.14. Nie został tu wygenerowany nowy uv.lock dla aplikacji ani zainstalowany klient.

## Najważniejsze decyzje i ich kompromisy

**Jeden worker, jeden job na fizyczny plik, równoległość jako ustawienie.** Jeden koordynator upraszcza własność produktów i daje gotowość osobnego odcinka. Liczby równoległych transferów AniShift domyślnie nie ogranicza (kolejka należy do qBittorrent). Liczba równoległych wykonań rdzenia startuje od 1, bo każdy job ma własny scheduler i własne limity wobec dostawców; użytkownik może ją podnieść. Pomiar P14 rozstrzyga, czy osobne joby dają gorszą przepustowość niż obecny batch run i czy trzeba grupować gotowe rewizje w jedno wykonanie.

**SQLite zamiast kilku plików JSON.** Trzeba atomowo zapisać wybór, job, komendę i widoczną gotowość oraz wykrywać duplikaty. Worker jest ownerem domeny, ale frontend może krótko zapisać komendę. Dlatego nie nazywamy całej bazy systemem z dosłownie jednym writerem procesu.

**Kopia zamiast przenoszenia/hardlinków.** Wymaga więcej miejsca, lecz chroni wejście przed zmianami klienta oraz zachowuje seedowanie. Budżet obejmuje źródło w downloads, kopię, finalne MKV, audio i temp.

**Osobny katalog rewizji.** Chroni odtwarzany dobry wynik przed v2, zmianą tekstu lub głosu. Rewizja zależy od całego pakietu wejść, nie tylko hasha wideo. Dwie różne wersje polskich napisów nie mogą się scalić jako duplikat.

**Wyszukiwanie ma podpowiadać, a reguła pobrania ma być ścisła.** Tytuły i aliasy można dopasowywać fuzzy. Wybór sezonu, numeracji, jakości i grupy wymaga potwierdzonej tożsamości. Dzięki temu wygoda nie oznacza pobrania innego anime o podobnej nazwie.

**AniList zamiast odgadywania przyszłości z RSS LiveChart.** LiveChart episodes RSS dotyczy przeszłych emisji. Publiczny katalog AniList jest właściwszym kandydatem do hintów przyszłych odcinków. Żaden hint nie zastępuje potwierdzenia istnienia pasującego wydania. S15–S19.

**Dodatkowy RSS zamiast drugiej dużej aplikacji.** AnimeTosho i istniejące CLI zbadano jako kandydatów. Nie kopiujemy całych trackerów, kont ani UI do AniShift. Nyaa jest pierwszym kompletnym indeksowym adapterem tej edycji.

## Co użytkownik konfiguruje raz

Folder biblioteki i inbox, uwierzytelnione połączenie do qBittorrent, opcjonalne preferowane grupy, istniejący preset produktu/głosu, lokalny player oraz zgodę na autostart. Program nie wymaga tworzenia nowego konta AniList tylko do publicznego katalogu.

Autostart AniShift i autolaunch klienta torrent są odrębnymi zgodami. Domyślny monitor otwiera się dla lokalnego dropu, a subskrypcje mogą pracować cicho. Użytkownik może wybrać monitor dla każdej partii albo całkowitą ciszę.

## Decyzje, których nie trzeba ponownie przerzucać na właściciela

Magazyn stanu, układ modułów, zasady idempotencji, numeracja Decimal, mechanizm catch-up, sposób użycia rdzenia, kontrakty UI, brak serwera i kolejność wdrożenia zostały rozstrzygnięte. Wykonawca nie ma wybierać jeszcze raz między JSON/SQLite, własnym torrent stackiem i kilkoma trackerami.

## Rzeczy rzeczywiście wymagające potwierdzenia lub próby

| Punkt | Kto / kiedy | Czy blokuje cały zakres? |
| --- | --- | --- |
| Czy użyć qBittorrent, jeżeli obecny klient jest inny | Właściciel przy setupie | Blokuje download, nie lokalny import. |
| Dwie ulubione grupy | Właściciel albo pierwszy konkretny wybór wydania | Nie; można zacząć bez globalnej preferencji. |
| Katalog i wolne miejsce | Właściciel przy setupie + doctor | Blokuje zapis przy braku budżetu. |
| Autostart oraz monitor | Właściciel, jawna zgoda | Brak zgody oznacza start ręczny, bez ukrytej modyfikacji Windows. |
| Metadata-only i per-file completion | Wykonawca, T003 | Blokuje automatyczną paczkę bez dowodu. |
| Publiczne kontrakty AniList/Nyaa | Wykonawca, T004 | Zależne adaptery, nie cały obecny rdzeń. |
| Odsłuch i ergonomia | Właściciel, P15 | Wymagane do pełnego odbioru, nie zastępowane pytest. |

## MAL i granica automatyzacji kont

W tej edycji jest opcjonalny import lokalnego eksportu XML i własny stan obejrzenia. **Nie ma automatycznego zapisu na konto MyAnimeList ani live synchronizacji listy.** Odcinek gotowy lub otwarty w playerze nie jest oznaczany jako obejrzany na zewnętrznym koncie.

To jawna granica pakietu, nie deklaracja wdrożonego OAuth. Bieżącego oficjalnego kontraktu MAL nie udało się odczytać; cudzy client_id/password grant z innego projektu nie jest właściwym skrótem. S28, S39–S40.

## Utrzymanie i koszty

Największe ryzyko utrzymaniowe: zmiana HTML Nyaa, kontraktu klienta, danych o numeracji i dostępności usług. Wszystkie te granice mają adapter, bezpieczny stan awarii i scenariusz testowy.

Największy koszt lokalny: miejsce na multimedia oraz obróbkę. Plan nie liczy sumy torrentów jako całej biblioteki. Nie obiecuje zerowych kosztów przyszłych usług ani nie włącza nowych płatnych kont.

Nie ma kosztu utrzymania VPS w tym zakresie, bo VPS nie jest jego częścią. Nie podano fikcyjnej estymacji czasu implementacji lub ceny usług bez próby i wybranej konfiguracji.

## Definicja gotowego wdrożenia

Wyszukiwanie i wybór, gotowość pojedynczego pliku paczki, subskrypcja, inbox, restart, uporządkowana biblioteka i autostart działają przez rzeczywiste granice. Oddzielnie zapisane są root gates, testy kontrolowane, żywe integracje i odbiór właściciela. Szczegóły: [masterplan](masterplan.md), [specyfikacja](spec.md), [przekazanie agentowi](handoff.md).

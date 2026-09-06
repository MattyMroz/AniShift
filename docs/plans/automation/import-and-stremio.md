# Import do terminala i wykorzystanie Stremio

Stan: 2026-09-05. Research i doprecyzowanie kierunku, bez wdrożenia.

## Import pliku: dwa różne przypadki

Właściciel doprecyzował, że przeciągnięty do terminala plik ma być **kopiowany
przez AniShift** do biblioteki. To nie jest to samo, co obserwowanie folderu,
do którego inny program właśnie coś zapisuje.

Proponowany przebieg: odebranie ścieżki → sprawdzenie źródła i kolizji →
kopiowanie do zarządzanego stagingu na tym samym woluminie z postępem bajtowym
→ zamknięcie i weryfikacja kopii → publikacja bez nadpisania istniejącego pliku
→ przekazanie gotowości do wspólnego planera. Oryginał zostaje na miejscu.
Hash można liczyć podczas kopiowania; nie wymaga osobnego pełnego odczytu źródła.

AniShift zna zakończenie własnego kopiowania, więc nie potrzebuje dodatkowego
„A — plik gotowy” ani zgadywania po mtime. Nadal trzeba obsłużyć zmianę źródła
w trakcie, anulowanie, brak miejsca, kolizję oraz plik już leżący w bibliotece.
Otrzymanej ścieżki nie wykonywać jako polecenia powłoki. Wielokrotne upuszczenie
tego samego pliku nie powinno tworzyć kolejnych kopii i zleceń.

Warstwa terminala może dostarczać tekst ścieżki zamiast zdarzenia GUI drag/drop;
format i cytowanie trzeba potwierdzić w docelowym terminalu. W kodzie istnieje
`prompts.py:Keys.BracketedPaste → paste:`, ale Home w `app.py:_handle_home_key`
obsługuje tylko nawigację i Enter, nie import. Wklejenie do edytora ustawień
musi nadal edytować pole, a nie uruchamiać kopiowanie. To osobny kolejny etap,
nie część wykonywanego obecnie Planu 05.

Niezależny watcher folderu pozostaje późniejszą możliwością. Problem nieznanego
końca kopiowania dotyczy właśnie zapisów **zewnętrznego** programu, nie importu
kontrolowanego przez AniShift. Nie narzucać użytkownikowi potwierdzania własnych
kopii aplikacji.

## Magnet i klient pobierania

Magnet jest odwołaniem do torrenta, nie plikiem odcinka. Klient może pobrać
metadane od peerów; metadane opisują zawartość i pozwalają wybrać pliki.
Nie trzeba najpierw pobierać całego filmu. Brak dostępnych peerów może
uniemożliwić także uzyskanie metadanych. [BEP 9](https://www.bittorrent.org/beps/bep_0009.html).

Odczyt rejestru zainstalowanych aplikacji potwierdził **qBittorrent 5.2.3**
i **Stremio 5.0.25**. Nie odczytywano ustawień, kont, list torrentów ani dodatków.

W tagu qBittorrent `release-5.2.3` są `fetchMetadata`, `parseMetadata` i
`saveMetadata`: osobna ścieżka uzyskania informacji i eksportu metadanej
przed dodaniem właściwego transferu. To mocniejszy punkt integracji niż
wcześniejsze oczekiwanie na metadane zatrzymanego magnetu.
[Kod wydania](https://raw.githubusercontent.com/qbittorrent/qBittorrent/release-5.2.3/src/webui/api/torrentscontroller.cpp).

Wniosek projektowy: E02 zaczynać od tych operacji. Krótki proof w izolowanym
profilu ma potwierdzić gotowość, listę plików, eksport, selekcję, kolizje
i moment pierwszego zapisu danych. Odczyt źródła nie zastępuje takiej próby.
Nie ma powodu pisać własnego klienta BitTorrent ani odbierać użytkownikowi
możliwości wklejenia magnetu.

## Gdzie pasuje Stremio

Protokół dodatków rozdziela katalog, metadane i listę strumieni; katalog
może przyjmować wyszukiwanie. Wynik strumienia może wskazywać URL albo
`infoHash` oraz `fileIdx`. Nie każdy wynik jest magnetem.
[Protokół](https://raw.githubusercontent.com/Stremio/stremio-addon-sdk/master/docs/protocol.md),
[format strumienia](https://raw.githubusercontent.com/Stremio/stremio-addon-sdk/master/docs/api/responses/stream.md).

To daje możliwość późniejszego użycia zgodnego dodatku jako źródła wyszukiwania.
Nie dowodzi jednak, że lokalna aplikacja udostępnia nam gotowe API trwałej
kolejki pobrań. Nie znaleziono tu podstaw do traktowania cache odtwarzacza
jako ukończonego odcinka w bibliotece AniShift.

Rekomendacja: najpierw przyjmowanie magnetu wybranego przez użytkownika i
pobieranie przez już zainstalowany qBittorrent. Następnie jedno źródło
wyszukiwania w terminalu; Stremio/addon jest kandydatem, nie nowym obowiązkowym
silnikiem. Nie kopiować prywatnych tokenów dodatków ani instalować ich
automatycznie. Dostępność eksportu magnetu w lokalnym Stremio 5.0.25 nie została
potwierdzona — stare poradniki wersji 4 nie są takim dowodem.

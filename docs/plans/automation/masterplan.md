---
kind: masterplan
status: proposed
updated: 2026-09-05
baseline: 83150d8
---

# Masterplan: od wyboru anime do gotowego odcinka

## Cel i źródła

Wybierasz materiał, AniShift zajmuje się powtarzalną obsługą, wynik czeka
do oglądania. [Wizja](vision.md) wyjaśnia korzyści; [specyfikacja](specification.md)
utrwala wymagania. [GitHub #49](https://github.com/MattyMroz/AniShift/issues/49)
śledzi przedsięwzięcie. Issues są właścicielem statusu przeniesionego długu.

## Stan wyjściowy

Auto i tryb ręczny używają wspólnej fasady, planera i schedulera. Osiem pól presetu
jest dostępnych. Właściciel potwierdził codzienne Auto i naprawę scrolla 83150d8;
pełnego odbioru wszystkich ustawień nie zakładamy. Testy lokalne: 3102 PASS,
13 skip; macierz realnych narzędzi medialnych: 30 smoke PASS.

Nie wdrożono automatyki folderu, downloadera, subskrypcji, serwera ani sync.
Ogólne polerowanie jest odłożone. Minimalne zabezpieczenia nowej funkcji zostają.

## Etapy

| ID | Rezultat dla użytkownika | Wejście / zależności | Warunek wyjścia | Status |
| --- | --- | --- | --- | --- |
| A00 | Pełny preset Auto i poprawione przewijanie | istniejący produkt | kod i smoke PASS; scroll odebrany, pozostałe ustawienia bez pełnego human check | delivered |
| A01 | Przyjęty plik sam przechodzi do Auto | O16, tożsamość zlecenia i ochrona jednego writera | bez utraty oryginału, ręcznego startu i powtórek po restarcie | proposed-next |
| A02 | Wybrany odcinek pobiera się i przechodzi do Auto | wspólne intake, proof klienta/metadanych | potwierdzone ukończenie, bezpieczny import, postęp i retry | planned |
| A03 | Subskrybowane serie dostarczają nowe odcinki | A02, polityka dopasowania i next episode | restart bez duplikatów, pause, niepewne wyniki czekają | planned |
| A08 | Lista Gotowe otwiera właściwy produkt w mpv | produkty i historia; bez wymagania A03/VPS | jedno działanie, bez drugiego trackera watched | planned |
| A09 | Ten sam pipeline pracuje przy wyłączonym PC | przydatna automatyka, serwerowy zakres #45, proof środowiska | headless worker odzyskuje stan i ogranicza zasoby/retry | later |
| A10 | Produkty docierają do miejsca oglądania | A09, storage/sync, R01–R02 | ponawialny transfer, potwierdzenie dostępności i retencja | later |
| A11 | Prośba „chcę obejrzeć…” uruchamia istniejące działania | stabilne operacje i katalog | ograniczone uprawnienia, potwierdzanie niejednoznaczności | optional |
| A12 | Folder przyjmuje pliki zapisane przez inne programy | wspólne intake, O11, polityka zastanych plików | brak startu na częściowych plikach i własnych produktach | planned |

A12 jest osobnym wejściem, nie fundamentem wymaganym przez A02. Może wejść wcześniej,
jeśli oszczędza właścicielowi więcej pracy. Kopia AniShift i klient pobierania znają
własny koniec zapisu — nie wymagają watchera ani ręcznego potwierdzenia „A”.

Dawne ID A04–A07 zachowano dla historycznych odnośników: dialog, proof ASS,
layout ASS i README są odłożone do #22/#23/#34 oraz #48. Nie blokują automatyzacji.

## Najbliższa decyzja

Rekomendacja: **A01 — kontrolowana kopia → Auto**, mały działający wycinek
z restart-safe historią. Historia powstaje dla rzeczywistego scenariusza,
nie jako rozbudowana platforma zadań. Kopia zachowuje oryginał i sama uruchamia Auto.

Jeżeli największy codzienny koszt to obsługa pobrania, alternatywą jest wąski A02:
**magnet → jeden klient → plik → Auto**, jeszcze bez wyszukiwarki i subskrypcji.
To większa integracja, zależna od proof klienta. Nie obiecujemy terminu przed
wyjazdem na podstawie samego limitu modelu.

ChatGPT Pro dostaje [brief](pro-brief.md), rozstrzyga O16 z właścicielem i planuje
tylko wybrany wynik na aktualnym kodzie. Kodowanie wymaga osobnej akceptacji.

## Ryzyka i koszt utrzymania

| Ryzyko | Minimalna odpowiedź |
| --- | --- |
| Kilka trackerów „gotowe” | Jeden owner historii AniShift, odwołania do stanu klienta |
| Fałszywy koniec obcego zapisu | Protokół gotowości; sam rozmiar/mtime nie jest dowodem |
| Restart między wynikiem a statusem | Reconciliation, brak duplikatów; bez obietnicy exactly-once sieci |
| Więcej integracji niż korzyści | Jeden klient i jedno storage w pierwszej wersji |
| Serwer bez wybranego głosu | Mały proof OS/providerów przed wdrożeniem |
| Katalog wymusza migrację | Grupowanie wirtualne, osobna decyzja o fizycznych plikach |
| „Next” mylone z „watched” | Rozdziel pobranie, gotowość i obejrzenie |

JSON/SQLite, VPS, chmura i model synchronizacji pozostają otwarte. Nie tworzyć
nowego rejestru silników pobierania ani drugiego pipeline'u.

## Zmiana kierunku

2026-09-05: właściciel uznał działający Auto za podstawę nowych funkcji.
Ogólny audyt/benchmarki/layout odłożył, zamówił backlog, wizję i publikację.
Stare szczegółowe plany wymagają dostosowania do wspólnego intake; nie przywracać
odrzuconego TUI ani nie robić z heurystyk napisów bramki importu.

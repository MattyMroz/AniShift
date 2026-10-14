---
kind: plan
status: ready
created: 2026-09-04
---

# Plan 03 — akceptacja istniejącego produktu

## Jeden rezultat

Potwierdzić na wskazanym przez właściciela odcinku, że poprawiony przebieg daje
czytelny postęp, poprawne napisy i kompletny lektor, a przerwanie nie niszczy danych.
To domknięcie M08 oraz ocen UX, nie implementacja TXT/watchera/pobierania.

## Źródła i stan

Czytać root AGENTS, [manifest](../manifesto.md), [outcome](../outcomes/02-hardening.md)
i otwarte wiersze [tablicy](../tasks.md). Przed zmianą czytać AGENTS danej domeny.
Baseline wykonania: gałąź `work/reliability/01-hardening` po commitach napraw;
sprawdzić aktualny HEAD i drift. Automatyczne wyniki są w outcome.

Brakuje oceny fizycznego terminala, pełnego odcinka, świeżego Windows,
recovery po hard-kill i rzeczywistego progu 4 GiB. Kontrolowane anulowanie/restart,
zachowanie attachment i mały RF64 mają już dowody w outcome; nie powtarzać ich
bez nowego powodu ani nie rozszerzać wniosków na pełną akceptację produktu.

## Zakres i ochrona danych

Używać kopii materiału w osobnym workspace wskazanym przez `ANISHIFT_WORKSPACE_ROOT`
tylko dla procesu testowego. Właściciel wybiera odcinek, provider/model i zatwierdza
ewentualny limit żądań. Nie zmieniać jego preferencji ani kluczy na potrzeby dowodu.
Nie usuwać obecnych binarek, źródeł ani tempów, aby symulować czystą instalację.
Czysty Windows sprawdzać w oddzielnym środowisku. SAPI nie uruchamiać bez osobnej
zgody na próbę głosu, ponieważ wygasła licencja może otworzyć okno dostawcy.

## Kolejność wykonania

1. Właściciel uruchamia `uv run anishift`. Sprawdza gotową maskotkę bez loadera,
   Home, Ustawienia, resize oraz klawiaturę. Ocenia gradient i położenie ścieżki.
   Rejestruje pełny czas do pierwszej użytecznej klatki i zauważalne opóźnienia;
   mikrobenchmark funkcji nie zastępuje tego pomiaru.
2. Odsłuchuje [krótką próbkę](../proof/edge-polish.mp3). Następnie wskazuje odcinek
   i wybiera w Ręcznym napisy oraz lektora. Podczas pracy sprawdza nazwy etapów,
   procent albo jawną aktywność, retry oraz reakcję klawiszy.
3. Sprawdza początek, kilka powtórzonych kwestii, polskie podziały i koniec filmu.
   Ostatnia wypowiedź musi być kompletna, źródła niezmienione, produkty obok źródła.
   Zanotować czas etapów, provider calls/retry i formaty bez zapisywania tekstu/kluczy.
4. Na kopii danych anulować w TTS i renderze. Poczekać na zakończenie procesu,
   uruchomić nowy proces i wznowić. Potwierdzić reuse poprawnych artefaktów,
   brak spóźnionej publikacji i zachowanie poprzedniego produktu.
   Osobno wykonać hard-kill wyłącznie własnego procesu testowego na kopii materiału:
   zanotować jego PID i sprawdzić ownership przed zakończeniem. Wznowienie nie może
   zaakceptować niekompletnego pliku ani zmienić wcześniejszego produktu. Nie zabijać
   procesów po nazwie obrazu i nie używać rzeczywistej sesji właściciela jako fixture.
5. Domknąć pozostałe Q08: wizualna ocena fontu i ewentualne metadane rodzin,
   walidacja końca długiego materiału oraz automatyczne przekroczenie RIFF/RF64.
   Mały test wymuszonego RF64 już przechodzi, lecz nie sprawdza progu 4 GiB.
6. W oddzielnym Windows uruchomić brakujące narzędzia od zera. Sprawdzić SHA256,
   kolejność przed probe, anulowanie pobierania oraz widoczność fazy bez drugiego
   renderera. Odrzucony loader nie oznacza rezygnacji z informacji o długim downloadzie.

## Pliki i reakcja na finding

Kod na wejściu jest read-only. Wyniki dopisać do nowego outcome i zaktualizować
tablicę. Regresję odtworzyć w istniejącym teście dotkniętej domeny, naprawić
najmniejszą przyczynę, uruchomić pełne gates przed osobnym tematycznym commitem.
Nie budować nowego frameworka benchmarków ani nie przenosić katalogów bez dowodu.
Zmiana kontraktu produktu wraca do właściciela; problem jakości tłumaczenia nie
upoważnia do cichego przełączenia dostawcy.

## Warunek zakończenia

Powtarzalny raport wskazuje materiał bez prywatnej ścieżki, środowisko, wyniki
scenariuszy i akceptację właściciela. Otwarte ograniczenia pozostają widoczne.
Po akceptacji zaplanować P01 osobno: reuse `SpeechBatch`, istniejącego TTS i
`AudioService` bez źródłowego audio; rozstrzygnąć format, kolejność fragmentów,
opcjonalne tłumaczenie i rytm. Nie tworzyć drugiego pipeline.

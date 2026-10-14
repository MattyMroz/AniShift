# Zadanie poboczne: wygodny wybór odcinków i sposób ich pozyskania

Status: **WYBÓR WYDAŃ ZATWIERDZONY W R-027; WYBÓR PLIKÓW PACZKI DO ROZPOZNANIA**
Źródło: feedback użytkownika z 2026-09-16 podczas realizacji P16.
Kontekst: [spec.md](spec.md), szczególnie R-006, R-027 i R-031; [plan.md](plan.md).

## Potrzeba

Użytkownik chce przejść od znalezienia anime do właściwych odcinków bez zgadywania, czy użyć pobrania, paczki czy subskrypcji. Ma móc wygodnie wskazać potrzebny zakres, zobaczyć konsekwencje wyboru i sterować zamówioną pracą. Istotny jest poprawny, kompletny przepływ, a nie konkretna liczba ekranów.

Wejście do grupy jak do folderu, początkowo pusty wybór wydań, Enter przełączający odcinek oraz jawne Pobierz z przejściem do Przetwarzania należą już do zatwierdzonego R-027. Grupa wydań nie oznacza plików wewnątrz jednego torrenta. Pozostałe nierozstrzygnięte punkty tego dokumentu dotyczą przede wszystkim takiej paczki; nie cofają zatwierdzonego przepływu pojedynczych wydań.

Użytkownik poprosił o zapisanie tego jako zadania pobocznego. Zaproponował wejście do paczki i zaznaczanie jej elementów oraz rozróżnienie pobierania dostępnych odcinków od subskrybowania wychodzących. Sformułowania „chyba” i „nie wiem, jak to ma działać” pozostawiają szczegóły interakcji do rozpoznania; nie są akceptacją gotowej makiety ani zgodą na natychmiastowe rozszerzenie implementacji.

Późniejsze doprecyzowanie potwierdziło wymaganie jednej karty tytułu z multiselectem obejmującym dostępne i przyszłe numery: przykładowo `1` odznaczony, `2–7` do pozyskania teraz, `8–12` po udostępnieniu. Ten zakres należy już do głównego kontraktu subskrypcji. [Raport przepływu i API](acquisition-flow-report.md) rozdziela działający wybór w UI od luk wykonawczych harmonogramu, których domknięcie dodano do integracji P17. Osobnym zadaniem pobocznym pozostaje wybór zawartości paczki i dalsze uproszczenie obsługi.

## Sytuacje do przejścia z perspektywy użytkownika

| Sytuacja | Oczekiwany efekt | Kierunek do oceny |
|---|---|---|
| Wybrane odcinki już wyszły | Pobieram wskazane numery jednorazowo | Czytelne zaznaczenie zakresu i jedno jawne Pobierz, bez obowiązkowej subskrypcji |
| Seria nadal wychodzi lub jeszcze nie ruszyła | Program pozyskuje kolejne wybrane odcinki po ich udostępnieniu | Subskrypcja konkretnego sezonu i grupy, z jasnym początkiem kontynuacji |
| Chcę nadrobić serię i śledzić dalszą emisję | Pobieram wskazane dostępne odcinki i zamawiam przyszłe | Osobno widoczne „do pobrania teraz” i „kolejne odcinki”, bez niejawnego pobierania całej historii |
| Wydanie jest paczką | Rozumiem zawartość i mogę wybrać potrzebne elementy | Wejście w zawartość paczki, wybór odcinków oraz pokazanie powiązanych plików |
| Praca została przyjęta | Widzę, co czeka, co się pobiera i co jest gotowe; mogę wykonać potrzebną akcję | Spójne nazwy, zaznaczenie i postęp oraz jednoznaczny zakres Zatrzymaj/Wznów/Anuluj/Ponów |

Subskrypcja służy przede wszystkim automatycznemu pozyskiwaniu kolejnych odcinków, ale może również obejmować jawnie wybrany istniejący zakres. Nie należy przedstawiać jej jako jedynej drogi do pobrania już wydanych odcinków.

## Rekomendowany kierunek do sprawdzenia

Wykorzystać obecną wspólną wyszukiwarkę i wybór numerów: jednorazowe **Pobierz** dla wskazanego zakresu oraz **Subskrybuj** dla dalszego zamawiania. Paczkę traktować jako wydanie, którego zawartość można zrozumieć przed zatwierdzeniem, a nie jako obowiązek pobrania wszystkiego.

Porównać rozbudowanie istniejącego widoku zakresu z otwieranym szczegółem zawartości paczki. Osobny szczegół ma sens, jeśli rzeczywiście pomaga rozpoznać pliki lub rozstrzygnąć wybór; nie jest samodzielnym celem. To propozycja, nie ustalony projekt ekranów.

## Ograniczenia wynikające z obecnego kontraktu

- Zaznaczenie oznacza zamiar pozyskania lub dokończenia, nie obejrzenie ani „mam lokalnie”.
- Podgląd paczki, nawigacja i edycja szkicu nie uruchamiają pobierania. Skutek następuje dopiero po jawnym zatwierdzeniu.
- Wybrany odcinek może wymagać powiązanych napisów i innych zadeklarowanych składników. Wybór plików nie może tworzyć pozornie kompletnego materiału.
- Trzeba odróżnić wybór plików do pobrania w kliencie torrent od wyboru odcinków do przetwarzania. Nie wolno obiecywać pierwszego, jeśli implementacja robi tylko drugie.
- „Pobierz” pozostaje pozyskaniem wejścia do dalszego przetwarzania według obecnej specyfikacji. Ten zapis nie wprowadza nowego trybu pobierz-bez-obróbki.
- Zachować pamięć pobrania, jawne ponowienie usuniętych materiałów, globalną pauzę, ochronę cudzych plików i płaski zapis w workspace.
- Zatrzymanie pojedynczego pliku, całej paczki i subskrypcji to różne działania. Etykieta musi odpowiadać rzeczywistemu zakresowi backendu.

## Nierozstrzygnięte i najmniejsze potrzebne sprawdzenia

1. Czy w paczce wystarczy wybór numerów odcinków, czy użytkownik potrzebuje także listy poszczególnych plików? Sprawdzić na rzeczywistym przykładzie paczki z odcinkami, sidecarami i dodatkami.
2. Kiedy zawartość jest dostępna: w katalogu wydania czy dopiero po uzyskaniu metadanych torrenta? Sprawdzić aktualny przepływ, możliwość wyboru przed zapisem treści i uczciwy komunikat oczekiwania.
3. Jak powinno wyglądać pierwsze zaznaczenie w paczce i przy nowej subskrypcji, żeby nie zamówić niechcianej historii? Obejrzeć skutki na przykładzie dostępnych 1–8 i planowanych 9–12, z wyborem tylko 3, 7–8 i dalszej emisji.
4. Czy brakująca wygoda wynika z nieczytelnej nawigacji, braku funkcji czy niejasnego opisu istniejącego działania? Najpierw przejść gotowy interfejs P16 i porównać go z tymi sytuacjami.
5. Jak pokazać częściowo wybraną lub częściowo pobraną paczkę i zakres sterowania nią bez dublowania pozycji w Przetwarzaniu? Sprawdzić rzeczywiste możliwości klienta i zachowanie powiązanych plików.

## Kolejny krok

Przeprowadzić krótkie rozpoznanie po ustabilizowaniu bieżącej nawigacji: istniejąca funkcja → brakujący krok → najmniejsza poprawa. Użyć wskazanego przez użytkownika skilla `intent` z `C:/Users/MattyMroz/Desktop/PROJECTS/agents/skills/intent/SKILL.md`.

Przygotować jeden proponowany przepływ na konkretnych przykładach. Dopiero po rozstrzygnięciu istotnych wyborów przenieść zaakceptowane zmiany do specyfikacji i planu. Sam ten wpis nie zmienia kryteriów odbioru P16 ani nie oznacza, że wybór plików wewnątrz paczki został już zaimplementowany.

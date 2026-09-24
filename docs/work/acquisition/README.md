---
kind: manifest
status: do-akceptacji-właściciela
updated: 2026-09-23
baseline: c58392ad1fdd97413f57d8828bdb5dc11acf5a7b
---

# Manifest: wspólne pobieranie i subskrypcje anime

## 1. Co czytać i w jakiej kolejności

| Kolejność | Dokument | Rola |
| --- | --- | --- |
| 1 | Ten plik, §3 i §4 | Decyzje i zgody, na które czeka praca |
| 2 | [spec.md](spec.md) | Co ma być prawdą: cel, ustalenia, wymagania, zakazy, warunki sukcesu |
| 3 | [ux.md](ux.md) | Ekrany, przejścia, klawisze, scenariusze odbioru |
| 4 | [masterplan.md](masterplan.md) | Etapy E0, E00, E1–E5 i ich warunki wyjścia |
| 5 | [plans/e1-wybor-odcinka.md](plans/e1-wybor-odcinka.md) | Szczegółowy plan etapu E1 (startuje po E00) |
| 6 | [research/summary.md](research/summary.md) | Wnioski z badań źródeł danych; raporty, na które powołują się spec i plan E1, leżą obok w `research/` |

### Archiwum lokalne (poza gitem)

Surowe dane i historia pracy leżą w `workspace/.archive/acquisition/` (katalog ignorowany przez git, tylko na komputerze właściciela): `evidence/` (odpowiedzi API, skrypty badań, zbiory do testów), `final/` (zastąpiony pakiet), `final2/audit.md`, `final2/review.md`, `final2/spec-a-odzyskana.md` (odzyskany kontrakt A), `reports/`, `reviews/`, `briefs/` i eksport sesji. Ścieżki `workspace/.archive/…` w dokumentach wskazują to archiwum. Dane potrzebne testom etap E1 przycina do `tests/fixtures/` i dopiero one trafiają do repozytorium.

## 2. Stan

- **Etap:** E0 zakończony — decyzje i zgody rozliczone. Przed E1 dodany etap E00 (katalog modeli i wywołania zgodne z OpenCode, multimodalność; decyzja właściciela 2026-09-23). E1 zależy od E00.
- **Kod:** baseline to `main` po scaleniu PR #56 (łańcuch local-automation); praca na gałęzi `work/acquisition/00-model-catalog`.
- **Review pakietu:** `workspace/.archive/acquisition/final2/review.md`.
- **Następny krok:** napisanie osobnego szczegółowego planu E00 i jego akceptacja przez właściciela; potem wykonanie E00, dopiero po nim faza 0 planu E1.

## 3. Decyzje

Lista weta rozliczona z właścicielem 2026-09-23. Wszystkie ustalenia w spec obowiązują. Zmiany wprowadzone po jego odpowiedziach:

| Temat | Ustalenie |
| --- | --- |
| Kolejność wydań | 1080p → 2160p → 720p → reszta; w tej samej rozdzielczości: polskie → MultiSub → Netflix/Crunchyroll → więcej seedów. Automat bierze zwykłe 1080p. |
| Widoczność wydań | 4K widoczne jako opcja; 720p i niższe ukryte, gdy jest 1080p albo 4K (U-24). |
| Lektor | Zawsze, także przy polskim dubbingu. |
| Dubbing bez oryginału | Na koniec kolejki. |
| Subskrypcja | Tylko zwykłe odcinki sezonu; dodatki i OVA widoczne w szczegółach subskrypcji, pobierane osobno. |
| Usuwanie subskrypcji | Delete bez pytania, Ctrl+Z przywraca (jak w Bibliotece). |
| Szukanie po emisji | Co 15 min przez dobę, co godzinę do 3. doby, potem codziennie; po 7 dniach powiadomienie. |
| Fonty | Nie pobieramy osobnych plików fontów; fonty wewnątrz MKV zostają. |
| Lista MAL | Niepotrzebna; próbka pomiaru z Twoich subskrypcji i popularnych tytułów w emisji. |
| Sprawdzenie heurystyki | Na co najmniej 2000 tytułach (TV, kontynuacje, OVA, filmy, różne lata). Każde wydanie z korpusu oceniają dwa modele różnych rodzin („oceniający”), wywoływane skryptem przez silnik LLM AniShift (`anishift.services.llm`, silnik Palantir, modele z katalogu po E00) z poleceniem oceny i Twoim kluczem Palantir; w każdej paczce są wydania kontrolne o znanej odpowiedzi. Niezgodności rozstrzyga trzeci model, a trudne przypadki i 50 losowych trafiają do Ciebie. Cel: 0 błędnie uznanych za zgodne w całym korpusie. |

Wszystkie decyzje są rozstrzygnięte. Kodek i pochodzenie wydania (WEB/Blu-ray) nie wpływają na wybór (U-25).

## 4. Zgody do etapu E1

| Nr | Zgoda | Stan |
| --- | --- | --- |
| Z-1 | Pomiar świeżości i pokrycia Torrentio vs Nyaa przez 7 dni oraz korpus 2000 tytułów (~4000 zapytań Torrentio w 2–3 doby) | Zgoda; na VPS przez `VpsOracleManager` (`deploy/connect.ps1`, konfiguracja i klucz już są) |
| Z-2 | Odczyt listy MAL | Wycofana — niepotrzebna |
| Z-3 | Próba metadanych magnetu w tymczasowym qBittorrencie | Zgoda |

## 5. Rejestr etapów

| Etap | Plan | Wynik | Status |
| --- | --- | --- | --- |
| E0 | ten pakiet | — | current |
| E00 | `plans/e00-katalog-modeli.md` — do napisania i akceptacji przez właściciela przed rozpoczęciem pracy | `outcomes/e00.md` (powstanie) | planned |
| E1 | [plans/e1-wybor-odcinka.md](plans/e1-wybor-odcinka.md) | `outcomes/e1.md` (powstanie) | planned |
| E2–E5 | powstaną po wyniku poprzedniego etapu | — | planned |

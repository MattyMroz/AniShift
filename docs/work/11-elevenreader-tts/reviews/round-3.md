---
kind: review
status: pass-with-findings
reviewed-state: docs/work/11-elevenreader-tts/{plan,specification,file-map,intent}.md po poprawkach rundy 2
date: 2026-10-25
---

# Review: plan i specyfikacja silnika ElevenReader — runda 3

## Zakres

- przedmiot: całość zestawu po dwóch rundach poprawek, czytana od początku jako świeży wykonawca;
- authority: jak w rundach 1–2;
- ryzyka szczególne tej rundy: spójność odwołań, kolejność commitów wobec faz, formatowanie kontraktów, skutki
  uboczne na koncie, warunki stopu, kompletność checkpointów;
- poza review: wykonanie kodu.

Metoda: ciągły odczyt `plan.md` §13–§18 i porównanie z `specification.md` (F1–F22, N1–N7, I1–I5, Z1–Z7, D1–D11),
`file-map.md` i `intent.md`; wyrywkowe ponowne sprawdzenie odwołań do kodu
(`anishift/services/tts/artifacts.py:95-110`, `anishift/platform/qbittorrent_process.py:633-653`,
`EDP:docs/research/capabilities.md:62`).

## Werdykt

**Status:** PASS WITH FINDINGS

**Najważniejszy powód:** brak findingów krytycznych i poważnych; zostały poprawki precyzji i jedna nowa niewiadoma
(ACL profilu wobec szyfrowania cookies w Chrome), przeniesiona do fazy 0.

## Findings

### Krytyczne

Brak.

### Poważne

Brak.

### Mniejsze

#### M10. WAV obwiedni w katalogu `clips/` repozytorium resume

- miejsce: plan §13.4 (kontrakt `split_clip`, „obok `source`”), §13.7;
- dowód: katalog `clips/` należy do `TtsArtifactLayout`, który waliduje nazwy plików tymczasowych
  (`anishift/services/tts/artifacts.py:95-110`, `:147`);
- wpływ: po awarii procesu w `clips/` zostałby obcy plik; mylące dla diagnostyki, potencjalnie dla przyszłego
  sprzątania;
- reakcja: WAV w `tempfile.TemporaryDirectory`.

#### M11. Kolejność w `ChromeSession.start`: blokada przed utworzeniem katalogu

- miejsce: plan §13.8 `browser.py`;
- wpływ: pierwsze uruchomienie (brak `config/elevenreader/`) kończy się błędem tworzenia pliku blokady — wykryłby
  to pierwszy test, ale plan nie powinien prowadzić wykonawcy w błąd;
- reakcja: najpierw `mkdir` i ACL katalogu, potem blokada, potem profil.

#### M12. ACL profilu niesprawdzone wobec App-Bound Encryption Chrome

- miejsce: plan §13.10, F0;
- dowód: Chrome 127+ szyfruje cookies przez uprzywilejowaną usługę weryfikującą aplikację
  (<https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html>, odczyt 2026-10-25);
  `icacls /inheritance:r /grant:r konto:(OI)(CI)F` usuwa dostęp kont systemowych
  (`anishift/platform/qbittorrent_process.py:643-649`);
- wpływ: nieznany — możliwe, że sesja nie przetrwa restartu Chrome albo Chrome zgłosi błąd profilu;
- reakcja: spike F0 stosuje to samo ACL i sprawdza przetrwanie sesji (S0.10); wpis w §22.

#### M13. Nieopisane skutki uboczne na koncie

- miejsce: plan §13.9 krok 5 (`set_reading_speed`), §13.11 droga G2;
- dowód: prędkość z ustawień trafia do `user_config.playback_speed_rate` (`EDP:docs/research/capabilities.md:62`);
- wpływ: właściciel zobaczy w aplikacji ElevenReader prędkość 1x i ewentualnie zmieniony domyślny głos, bez
  wyjaśnienia;
- reakcja: punkt „Skutki uboczne na koncie” w §13.13, wzmianka w README i outcome.

#### M14. Niejasne przypisanie pracy F1 do commitów

- miejsce: plan §18 F1 (uwaga o kolejności), §19.2;
- wpływ: wykonawca F1 mógłby zacommitować `segmentation.py` w commicie wspólnych ramek, mieszając tematy;
- reakcja: jawne przypisanie: commit 2 = ramki MPEG; commit 4 = kontrakt dokumentu + segmentacja + `split_clip`.

#### M15. Akapit o limicie czasu FFmpeg wewnątrz bloku kodu

- miejsce: plan §13.7, koniec algorytmu `split_clip`;
- reakcja: przeniesienie poza blok.

### Sugestie

Brak nowych.

## Zgodność z kontraktem

| Wymaganie / decyzja | Stan | Dowód |
|---|---|---|
| F1–F4 | pass | §13.3–13.6, testy §18 F2 |
| F5 neutralizacja | pass | §13.8 `document.py`, testy F3 |
| F6 szyldy | pass | §13.15 (wiersz „szyld nieznaleziony”) |
| F7, F8 prędkość i głos | pass (zależne od F0) | §13.9, §13.11 |
| F9–F12 głosy i profile | pass (ID z F0) | §13.11, §18 F5 |
| F13 profil gitignorowany przed pierwszym plikiem | pass | §18 F0 krok 2a |
| F14–F17 sesja | pass | §13.10, §18 F5, F4b |
| F18–F19 doctor | pass | §18 F5 krok 10 |
| F20–F22 błędy | pass | §13.12, §13.13 |
| N1 sekrety | pass | §13.10, testy logowania, S6 |
| N2 cięcie | pass (ocena ucha w F6) | §13.7, §18 F1, F6 |
| N3 czas | pending (pomiar w F6) | §18 F6 |
| N4 anulowanie | pass | §13.9 `_unless_cancelled` |
| N5 Chrome po zamknięciu | pass | §13.8, §13.9 `finally` |
| N6 bramki | pass | §17.3 |
| N7 postęp | pass | §13.6 |
| I1–I5 | pass | §16, §21 |
| Z1–Z7 | pass | §14.3 |
| D1–D11 | rekomendacje zapisane, plan realizuje je jako założenia | `specification.md` |

## Regresje i integracja

- Granice warstw: UI → fasada aplikacji → usługi; DTO w aplikacji (runda 1, P2). Bez nowych findingów.
- Typy na dwóch platformach: `getattr` dla flag Windows (runda 2, P4). Bez nowych findingów.
- Cykl życia przeglądarki: lazy start, ponowne użycie między dokumentami, zamknięcie przy anulowaniu (runda 2, P6).
  Bez nowych findingów.

## Wykonane kontrole

```text
odczyt: plan.md §13–§18 w całości; specification.md; file-map.md;
        anishift/services/tts/artifacts.py:90-170; anishift/platform/qbittorrent_process.py:630-655;
        EDP:docs/research/capabilities.md:55-66
źródło sieciowe: security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html (wynik wyszukiwania 2026-10-25)
wynik: opisane findingi mniejsze
```

## Niewykonane kontrole

- Bramki i testy — zakaz uruchamiania kodu.
- Niezależne review innym modelem — zakaz tworzenia subagentów w tym zadaniu; plan wymaga go w fazie 7 (S5).

## Poprawki naniesione po rundzie

| Finding | Poprawka | Miejsce |
|---|---|---|
| M10 | WAV w `tempfile.TemporaryDirectory`; kontrakt efektów ubocznych | `plan.md` §13.4, §13.7 |
| M11 | kolejność `mkdir` → ACL → blokada → profil | `plan.md` §13.8 |
| M12 | S0.10 w spike, ACL stosowane w F0, wiersz w §22 | `plan.md` §18 F0, §22 |
| M13 | „Skutki uboczne na koncie” | `plan.md` §13.13 |
| M14 | jawne przypisanie pracy F1 do commitów 2 i 4 | `plan.md` §18 F1 |
| M15 | akapit przeniesiony poza blok kodu | `plan.md` §13.7 |

## Zalecany następny krok

Kończy rundy review planu (brak findingów krytycznych i poważnych). Następnie: akceptacja właściciela decyzji
D1–D11 i start fazy 0.

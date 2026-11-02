# Dokumenty AniShift: zacznij tutaj

[README projektu](../README.md) opisuje uruchomienie, komendy i konfigurację.
[Reference](reference/_index.md) zbiera niezależne materiały źródłowe, [ustawienia panelu](reference/settings.md)
i [materiał do przyszłego layoutu napisów](reference/subtitle-layout-engine.md).
Obowiązujące kontrakty związane z wdrożeniami pozostają przy swoich workstreamach:
[zapis stanu panelu — §1](work/02-plain-cli/plans/05-panel-state-persistence.md#1-manifest--jak-ma-się-zachowywać-zapis-stanu)
oraz [regresje tożsamości odcinka H1 — §10.6](work/08-acquisition/plans/07-episode-identity-integration.md#106-zasada-regresji).

## Workstreamy

Każdy workstream pozostaje w `work/<nn>-<nazwa>/`, niezależnie od statusu; numer to kolejność powstania.
Artefakty mają układ ze skilla `workflow` (§11): `specification.md`, `masterplan.md`,
`intent.md`, `research/`, `plans/`, `reviews/`, `outcomes/` i `session-logs/` — tylko gdy istnieje treść.
Historyczne plany i wyniki opisują swoje baseline'y, nie gwarantują dzisiejszego zachowania aplikacji.
„Zrobione” oznacza zakres scalony do `main`. „Niezaczęte” to plan bez kodu na `main`.
„—” oznacza brak osobno ustalonego PR. Statusy poniżej: stan `origin/main` @ `a0b36c6` z 2026-11-02.

| Katalog | Czym był | Status | PR |
|---|---|---|---|
| [00-rebuild/](work/00-rebuild/masterplan.md) | Przebudowa aplikacji, etapy 1–9; szczegóły etapów i PR w masterplanie | zrobione: rdzeń; porzucone: Textual etapu 9; zastąpione: pierwotna roadmapa | [#9](https://github.com/MattyMroz/AniShift/pull/9)–[#41](https://github.com/MattyMroz/AniShift/pull/41) |
| [01-textual-tui/](work/01-textual-tui/) | Etap 10: Palantir, katalog modeli, usunięcie pipeline i Textual TUI | zrobione: wspólny rdzeń; porzucone: interfejs Textual (snapshot na gałęzi `archive/textual-tui`) | [#41](https://github.com/MattyMroz/AniShift/pull/41) |
| [02-plain-cli/](work/02-plain-cli/) | Frontend Prompt Toolkit, ustawienia i zapis stanu panelu | zrobione | [#41](https://github.com/MattyMroz/AniShift/pull/41) |
| [03-llm-translation/](work/03-llm-translation/) | Tłumaczenie LLM i przejście z JSON na numerowane linie | zrobione | — |
| [04-reliability-audit/](work/04-reliability-audit/) | Audyt niezawodności, hardening i dopracowanie terminala | zrobione; dalszy odbiór i kwalifikacja w ideas.md | [#41](https://github.com/MattyMroz/AniShift/pull/41), [#50](https://github.com/MattyMroz/AniShift/pull/50) |
| [05-automation/](work/05-automation/) | Pierwszy pakiet automatyzacji | zastąpione przez lokalną automatyzację | — |
| [06-local-automation/](work/06-local-automation/) | Watch, wyszukiwanie, pobieranie i subskrypcje | zrobione; dalszy zakres zastąpiły etap 06 i pozyskiwanie | [#51](https://github.com/MattyMroz/AniShift/pull/51) |
| [06-local-automation/06-efficiency/](work/06-local-automation/06-efficiency/) | Manual, Auto i niezależne subskrypcje | zrobione | [#56](https://github.com/MattyMroz/AniShift/pull/56) |
| [07-local-automation-2/](work/07-local-automation-2/) | Foldery zadaniowe i dalszy model lokalnej pracy | zastąpione przez etap 06 i pozyskiwanie | [#56](https://github.com/MattyMroz/AniShift/pull/56), [#59](https://github.com/MattyMroz/AniShift/pull/59) |
| [08-acquisition/](work/08-acquisition/) | Katalog modeli, wybór odcinka, pobieranie, subskrypcje i algorytm E00–A1 | zrobione; E4 wykonuje częściowo 17-content-check, E5 i E6 odłożone w ideas.md (E6 planuje 18-library-titles-covers) | [#57](https://github.com/MattyMroz/AniShift/pull/57), [#59](https://github.com/MattyMroz/AniShift/pull/59) |
| [09-tui-unify/](work/09-tui-unify/) | Ujednolicenie czterech zakładek panelu | zrobione; dalsze pomysły w ideas.md | [#59](https://github.com/MattyMroz/AniShift/pull/59) |
| [10-quality/](work/10-quality/masterplan.md) | Jakość wyniku: baza testowa, szyldy, podział dialog / szyld, granice stylów, podział wierszy, czasy, głośność lektora | częściowo: układ dialogu i szyldów, polski podział wierszy, czcionka dialogu, narracja szyldów; granice stylów w 20-style-boundaries niezaczęte; głośność lektora zrobiona w 11-elevenreader-tts; etap 5 (czasy wyświetlania) bez dowodu | [#61](https://github.com/MattyMroz/AniShift/pull/61), [#65](https://github.com/MattyMroz/AniShift/pull/65), [#66](https://github.com/MattyMroz/AniShift/pull/66), [#71](https://github.com/MattyMroz/AniShift/pull/71), [#76](https://github.com/MattyMroz/AniShift/pull/76) |
| [11-elevenreader-tts/](work/11-elevenreader-tts/) | Lektor przez ElevenReader na bazie ElevenDownloaderPro: głos, timestampy, sesja i logowanie | zrobione: silnik, mierzona głośność, tempo, równoległe nagrania (limit 2), wykrywanie kawałków bez mowy; czeka odbiór właściciela na prawdziwych odcinkach (K2, K3) | [#78](https://github.com/MattyMroz/AniShift/pull/78), [#83](https://github.com/MattyMroz/AniShift/pull/83), [#89](https://github.com/MattyMroz/AniShift/pull/89), [#90](https://github.com/MattyMroz/AniShift/pull/90), [#93](https://github.com/MattyMroz/AniShift/pull/93), [#96](https://github.com/MattyMroz/AniShift/pull/96) |
| [12-catalog-fallback/](work/12-catalog-fallback/) | Zapas katalogu przy awarii AniList | niezaczęte: plan czeka na decyzje właściciela D1–D6; zgłoszenie [#64](https://github.com/MattyMroz/AniShift/issues/64) | — |
| [13-silent-stalls/](work/13-silent-stalls/) | Diagnoza cichych zawieszeń z 24.10 i niezależny przegląd PR #66 | częściowo: diagnoza; naprawy z diagnozy zrobione w kontroli zawartości (pkt 1) i sprzątaniu stagingu (pkt 3 i 5); reszta bez zmian | [#73](https://github.com/MattyMroz/AniShift/pull/73), [#74](https://github.com/MattyMroz/AniShift/pull/74) |
| [14-stall-watchdog/](work/14-stall-watchdog/) | Strażnik materiału, który utknął w przepływie | niezaczęte: plan czeka na decyzje właściciela D1–D7 | — |
| [15-layout-performance/](work/15-layout-performance/) | Wydajność układania bardzo długich linii dialogu | zrobione: limit `MAX_DIALOGUE_WORDS = 50`, linia ponad limitem zostaje nierozbita | [#71](https://github.com/MattyMroz/AniShift/pull/71) |
| [16-proper-names/](work/16-proper-names/) | Nazwy własne w tłumaczeniu: glosariusz serii | niezaczęte: plan czeka na decyzje właściciela D1–D8 | — |
| [17-content-check/](work/17-content-check/) | Kontrola zawartości po pobraniu: PL, obce, brak napisów, same szyldy | częściowo: reguła roli ścieżki i odrzucanie wydania bez napisów dialogowych w subskrypcji (F1, F2); zamiana wydania przy pobraniu ręcznym (F3) odłożona | [#74](https://github.com/MattyMroz/AniShift/pull/74) |
| [18-library-titles-covers/](work/18-library-titles-covers/) | Biblioteka jako widok tytułów i okładki w panelu | niezaczęte: plan czeka na decyzje właściciela O-1…O-11 | — |
| [19-tvmaze-episode-titles/](work/19-tvmaze-episode-titles/) | Brakujące tytuły odcinków z TVmaze | niezaczęte: plan czeka na decyzje właściciela D1–D7; zgłoszenie [#58](https://github.com/MattyMroz/AniShift/issues/58) | — |
| [20-style-boundaries/](work/20-style-boundaries/) | Granice stylów po tłumaczeniu | niezaczęte: plan czeka na decyzje właściciela D1–D5; zgłoszenie [#34](https://github.com/MattyMroz/AniShift/issues/34) | — |
| [21-playshift/](work/21-playshift/) | PlayShift (nazwa robocza): przenośny odtwarzacz na mpv, research, specyfikacja, masterplan, pomiary etapu 01 | aktywne: dokumenty scalone, pomiary etapu 01 wykonane; czeka ocena właściciela (K1) | [#85](https://github.com/MattyMroz/AniShift/pull/85), [#98](https://github.com/MattyMroz/AniShift/pull/98) |

## Dalsza praca i wznowienie

Aktywne: [21-playshift](work/21-playshift/README.md) (etap 01 czeka na ocenę właściciela) oraz odbiór
[11-elevenreader-tts](work/11-elevenreader-tts/README.md) na prawdziwych odcinkach. Plany 12, 14, 16, 18, 19 i 20
czekają na decyzje właściciela. Priorytety i odłożone etapy zbiera [ideas.md](ideas.md).
[Session logs](session-logs/) zawierają punkty wznowienia sesji używane przez `load-session`.

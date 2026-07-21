# Etap 4 — bugi UX i wymagania paska postępu (do naprawy w następnej sesji)

> Rdzeń tłumaczenia DZIAŁA (DeepL/Google tłumaczą, całościowy ASS 790→790, bramki zielone). ALE odpalenie programu ujawniło zepsute UX. Ten dokument spisuje realne bugi z użycia + wymagania jak przepływ ma działać. Zdiagnozowane faktami z kodu, nie z pamięci.

## Kontekst — jak przepływ działa TERAZ (fakty z runner.py)

Dla jednego pliku (`_process_mkv`, runner.py:167-247), kroki SEKWENCYJNE:
```
identify → extract (MA pasek, on_progress) → split → write displayed → translate (BRAK paska) → done
```
- Pliki lecą RÓWNOLEGLE (`_process_mkvs` ThreadPoolExecutor, ~5 naraz).
- Pasek per plik pokazuje TYLKO ekstrakcję (`extract_tracks(..., on_progress=...)`, :191).
- Tłumaczenie (`_translate_split`, :228) NIE dostaje `on_progress` → brak feedbacku.
- `translate_file` jest SYNCHRONICZNE: wysyła cały plik do DeepL/Google w 1-2 batchach i czeka. Nie ma etapów 0%→100%, jest skok „wysłane → gotowe".

## BUGI (realne, z odpalenia programu)

### BUG 1 — `[/repr.path]` w ścieżkach wyjściowych
- **Objaw:** `workspace[/repr.path][shisha] Youjo Senki...` — dosłowny marker `[/repr.path]` w ścieżce.
- **Źródło:** `cli/pipeline_ui.py:95` `console.print(f"    [gray]-> {outcome.displayed_path}[/gray]")`. Nazwy plików anime zawierają `[nawiasy]` (`[shisha]`, `[SubsPlease]`), które kolidują ze składnią znaczników rich. System kolorowania (`utils/rich_console/console.py:107` `_PATH_RE`) owija ścieżkę w `[repr.path]...[/repr.path]`, a `[nawiasy]` w nazwie rozwalają parsowanie.
- **Ograniczenie:** `utils/rich_console/` NIETYKALNE (CLAUDE.md, 1:1 mm_avh). Naprawa MUSI być po stronie `cli/pipeline_ui.py` — escapować `[`/`]` w nazwie pliku przed drukowaniem (rich escape: `\[`), albo drukować ścieżkę bez przepuszczania przez auto-koloryzer.
- **Dotknięte pliki:** wszystkie z `[nawiasami]` w nazwie (większość anime).

### BUG 2 — brak feedbacku podczas tłumaczenia (wygląda jakby wisiało)
- **Objaw:** po ekstrakcji pasek pliku stoi na 100%, a program „milczy" póki DeepL/Google nie odpowie. User myśli że zawiesiło.
- **Źródło:** `_translate_split` (:228) bez `on_progress`. Krok translate nie raportuje nic.
- **Uwaga architektoniczna:** tłumaczenie 1 pliku jest sync i „atomowe" (1-2 batche naraz) — NIE ma naturalnego 0-100%. Więc realnie potrzebny SPINNER („tłumaczę…"), nie pasek procentowy. Alternatywa (async z „3/8 batchy") = większa robota + ryzyko banu API (R7 świadomie odłożone).

### BUG 3 — „paski się nie kończą / dziwne logi" (do potwierdzenia z userem)
- **Objaw (user):** paski postępu wyglądają jakby się nie kończyły / dziwne logi na końcu.
- **Hipoteza:** powiązane z BUG 2 — pasek pliku stoi na 100% (ekstrakcja gotowa) podczas gdy tłumaczenie leci w tle, plus równoległe pliki mieszają output. Do potwierdzenia OBSERWACJĄ (odpalić, nagrać dokładny objaw).

## PYTANIA USERA o przepływ — do rozstrzygnięcia w następnej sesji

1. **Kiedy startuje tłumaczenie?** — TERAZ: per plik, zaraz po jego ekstrakcji+split (nie czeka aż WSZYSTKIE pliki się wypakują; każdy plik idzie swoją ścieżką identify→extract→translate niezależnie, równolegle z innymi). Pytanie usera: czy ma być tak (jak plik gotowy → tłumacz), czy inaczej (najpierw wypakuj wszystko, potem tłumacz wszystko)?
2. **Co ma się wyświetlać podczas tłumaczenia?** — opcje do wyboru:
   - (a) spinner per plik („tłumaczę [nazwa]… ⣾"),
   - (b) osobna faza z własnymi paskami (ekstrakcja: N pasków → potem tłumaczenie: N pasków),
   - (c) jeden pasek per plik który obejmuje CAŁY przepływ (extract+translate jako jeden postęp 0-100%).
3. **Podział ekranu / wiele pasków?** — powiązane z [[terminal-ui-refactor-scope]] (logi/historia góra + paski dół + live error report; whole-app, Live+Group). User już wcześniej planował refaktor UI — bugi UX warto naprawić W RAMACH tego refaktoru, nie punktowo.

## Ograniczenia (CLAUDE.md)
- `utils/` NIETYKALNE (1:1 mm_avh) — naprawy tylko w `cli/`, `pipeline/`.
- Naprawy weryfikować ODPALENIEM PROGRAMU (skill `verify`), nie tylko testami — „bramki zielone" maskowały te bugi.

## Co NIE jest bugiem (sprawdzone)
- `already_polish` → nie tłumaczy: DZIAŁA poprawnie (`_should_translate` runner.py:278). Pliki „already Polish" (Youjo, Kimi, Tsue) NIE są tłumaczone; nie-polskie (Mushoku, World Is Dancing) → `translated via deepl`. To jest OK, nie bug.

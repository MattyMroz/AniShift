# Jakość wyniku: specyfikacja

Status: projekt do akceptacji właściciela (2026-10-15).

## Cel

Odcinek obejrzany po AniShift ma brzmieć i wyglądać lepiej niż dziś:
- poprawne imiona i rodzaj gramatyczny postaci;
- lektor czyta tylko dialogi, bez szyldów i piosenek, i nie zostaje w tyle za postaciami;
- oryginał nie zagłusza lektora ani lektor oryginału;
- szyldy mieszczą się w swojej ramce.

Każda zmiana musi dać mierzalny zysk na stałym zestawie odcinków, a nie tylko „wyglądać lepiej” w kodzie.

## Kto ocenia

Właściciel, na trzech odcinkach wzorca (etap 0), przed zmianą i po niej. Testy i metryki są warunkiem koniecznym, ale nie wystarczającym.

## Zakres

W zakresie, w kolejności z [masterplanu](masterplan.md):
- wzorzec i pomiar bazowy;
- glosariusz postaci z AniList i oznaczanie szyldów w prompcie;
- kategoria „piosenka” i niepewne linie;
- miks lektora;
- dopasowanie szyldów.

Poza zakresem:
- lokalny TTS (odrzucony na teraz, `docs/ideas.md` §4);
- ElevenReader (bada właściciel);
- typesetting z samego obrazu (OCR, VLM);
- wielogłosowa obsada;
- API i strona WWW;
- podział `automation.py`.

## Ustalenia

- **Kolejność** wynika z audytu z 2026-10-14 (astra, argon) i decyzji właściciela: najpierw największy zysk przy najmniejszym koszcie.
- **Fakty z kodu, na których stoi plan:**
  - prompt przewiduje glosariusz i profil tytułu (`anishift/services/translation/engines/llm/prompts/system.md:11`), ale silnik wysyła tylko prompt, styl i linie (`anishift/services/translation/engines/llm/service.py:247-251`);
  - klasyfikator zna tylko `DIALOG`, `SIGN` i `UNCERTAIN`, a piosenki trafiają do `SIGN` (`anishift/services/subtitles/classifier.py:96-101`);
  - miks to stałe +7 dB dla lektora i `amix` bez duckingu (`anishift/services/audio/config.py:47-49`, `anishift/services/audio/output.py:113-119`);
  - oś czasu nigdy nie przyspiesza pojedynczej kwestii, tylko ją przesuwa (`anishift/services/audio/timeline.py:59-72`);
  - pole `Actor` (`SSAEvent.name`) nie jest nigdzie używane w `anishift/services/subtitles/`, choć w bibliotece właściciela ma je 17 z 21 źródłowych plików ASS: napisy Crunchyroll podają przy każdej linii imię mówiącego (np. `Maomao`, `Jinshi`) albo znacznik `SIGN`, `SFX`, `Text` przy szyldach (pomiar z 2026-10-15 na `workspace/ready/`).
- **Domyślne zachowanie** po każdym etapie ma być co najmniej tak dobre jak przed nim na wszystkich trzech odcinkach wzorca. Pogorszenie jednego odcinka blokuje etap.
- **Koszt:** każdy przebieg wzorca zużywa tokeny LLM i znaki TTS właściciela. Etap ponawia tylko kroki, których dotyczy (tłumaczenie albo lektor), nie cały pipeline.

## Kryteria sukcesu całości

- Właściciel ocenia każdy odcinek wzorca nie gorzej niż w pomiarze bazowym w każdym kryterium arkusza i lepiej w kryterium, którego dotyczył etap.
- Metryki automatyczne etapu (masterplan) przechodzą próg z planu etapu.
- Bramki jakości repo przechodzą.

## Nierozstrzygnięte

- Czy przebieg wzorca może działać w osobnym `ANISHIFT_WORKSPACE_ROOT` obok żywego rezydenta. Rozstrzyga etap 0, krok 1.

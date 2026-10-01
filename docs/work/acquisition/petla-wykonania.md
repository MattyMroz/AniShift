# Pętla wykonania (wiążąca dla orkiestratora)

Ustalone przez właściciela 01.10.2026. Plik przetrwa kompaktowanie kontekstu.
Czytaj go na początku każdej sesji i po każdym kompaktowaniu.

## Algorytm etapu

1. Orkiestrator zapisuje decyzje właściciela w planie (`plans/e2-panel-anime.md`
   §14, `plans/e2-pobieranie.md`), zanim zleci pracę.
2. Jeden autor (`opus55`) dostaje CAŁY etap jednym briefem według
   `.agents/skills/subagent/assets/SUBAGENT-BRIEF.template.md`: cel, fakty,
   decyzje, co czytać, co wolno i czego nie ruszać, checklista ukończenia,
   dowody, warunki stopu, format wyniku. Autor iteruje sam, aż uzna etap
   za skończony i gotowy do commita.
3. Orkiestrator sprawdza wynik: PNG porównuje z każdą decyzją właściciela,
   czyta diff i wyniki bramek. Braki wracają do autora bez udziału właściciela.
4. `astra` recenzuje cały etap tylko przed commitem i oddaje wszystkie findingi
   naraz. Autor poprawia, `astra` weryfikuje; pętla trwa do PASS.
5. Orkiestrator uruchamia bramki, commituje, restartuje rezydenta
   (`uv run anishift watch stop`, potem `uv run anishift`) i sam testuje na żywo.
6. Dopiero potem właściciel dostaje wynik z informacją: co zmienione,
   że wymagany jest restart i co sprawdzić.
7. Następny etap z listy poniżej, aż wszystkie są zrobione.

Zakazy orkiestratora: nie pokazywać właścicielowi niesprawdzonej pracy;
nie podawać liczb bez dowodu; nie dzielić etapu na mikrozadania z osobnym
review; nie testować z właścicielem kodu, którego rezydent nie załadował.

## Etapy do końca planu E2

| Nr | Etap | Stan |
| --- | --- | --- |
| 1 | Panel Anime P2/P3 (D9–D16) → review `astra` → commit | zrobione (`b68f4a9`, D9–D21) |
| 2 | Restart rezydenta, test orkiestratora na żywo według scenariusza §11 `e2-pobieranie.md` | zrobione (`971dc3b`, wynik w `outcomes/e2.md`) |
| 3 | F8: odbiór H2 właściciela, poprawki z odbioru w pętli 2–5 | czeka na właściciela (lista kroków w `outcomes/e2.md`) |
| 4 | `outcomes/e2.md`, AGENTS, status E2 | zrobione (status `PENDING HUMAN`) |
| 5 | Audyt całości i plan refaktoryzacji do akceptacji właściciela | plan zrobiony (`plans/e2-refaktoryzacja.md`, review `astra` PASS) |
| 6 | Etap A planu refaktoryzacji (A1–A6) według decyzji orkiestratora → review `astra` → commit | w toku |

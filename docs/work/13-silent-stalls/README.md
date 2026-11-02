# 13-silent-stalls

Diagnoza cichych zatrzymań rezydenta (stan z 2026-10-25): odcinki pobrane, lecz nigdy nieprzetworzone, martwe zlecenia,
wpisy `uncertain`, staging w `workspace/temp/` i timeouty TTS.

- `diagnosis.md` – przyczyny z dowodami (plik:linia, dane, komendy), propozycje napraw z testami regresyjnymi i drogi odzysku.

Status: diagnoza; naprawy trzech z jej punktów scalono osobno. Punkt 1 (pobrane wydanie bez napisów) naprawia
[PR #74](https://github.com/MattyMroz/AniShift/pull/74), punkty 3 i 5 (staging i martwe zlecenia) naprawia
[PR #73](https://github.com/MattyMroz/AniShift/pull/73). Punkty 2, 4 i 6 oraz ostrzeżenie o utknięciu bez zmian w kodzie.
Sama diagnoza nie zmieniała kodu, testów, `config/watch/` ani `workspace/`.

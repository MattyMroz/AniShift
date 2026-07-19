# Etap 4 — poprawki v2 (kompletne, ze źródeł, tylko polski)

> Poprzednia runda odrzucona jako "po łebkach": listy z pamięci (niekompletne, nieuporządkowane), garstka znaków interpunkcyjnych zamiast kompletu, rozdęte docstringi. Ta runda: KOMPLETNIE, ze SŁOWNIKA (Wikisłownik przez API), alfabetycznie, wszystkie znaki Unicode przez kategorie, tylko polski.
>
> Źródło prawdy: `<scratchpad>/polish-wordlists-source.md` (Wikisłownik 195 spójników + 217 przyimków; unicodedata UCD 16.0.0 zweryfikowane na 3.14.2 — 754 znaki tnące).

---

## DECYZJA NADRZĘDNA: TYLKO POLSKI (usuń multi-lang)

Program tłumaczy WYŁĄCZNIE na polski. Multi-lang = martwy kod.

**Granica wejście vs wynik (kluczowe):**
- `chunking.py` dzieli **WEJŚCIE** (obce napisy: JP/EN/...) → **ZOSTAJE WIELOJĘZYCZNE** (wszystkie znaki Unicode).
- `source_lang="auto"` (silnik wykrywa) → ZOSTAJE.
- `linebreak.py` dzieli **WYNIK** (już-polski tekst) → **TYLKO POLSKI**.
- `target_lang` = `"pl"` na sztywno (stała), NIE parametr panelu.

---

## 1. USUNIĘCIE MULTI-LANG

| Miejsce | Przed | Po |
|---|---|---|
| `constants.py` | `SUPPORTED_TARGET_LANGS` (10 języków) + `DEFAULT_TARGET_LANG="pl"` | `TARGET_LANG: Final = "pl"` (jedna stała, komentarz "always Polish"). Usuń `SUPPORTED_TARGET_LANGS` i `DEFAULT_TARGET_LANG`. |
| `config.py` | `target_lang: str = DEFAULT_TARGET_LANG` (pole configu) | Usuń pole `target_lang` z `TranslationConfig` (zawsze pl). |
| `settings_panel.py` | `_Field("target_lang", ...)` + import `SUPPORTED_TARGET_LANGS` + gałąź `_step_field` | Usuń pole języka z `_FIELDS`, import, gałąź, `UserSettings.target_lang`. |
| `user_settings.py` | `target_lang: str = "pl"` + `_clean_nonempty_string(target_lang)` | Usuń pole `target_lang` i jego walidację (zawsze pl). |
| `pipeline/types.py` `TranslationSettings` | `target_lang: str` | Usuń pole (runner używa stałej `TARGET_LANG`). |
| `runner.py` | przekazuje `target_lang=...` | używa `TARGET_LANG` z constants. |
| `service.py` | `translate_file(..., target_lang="pl")` | zostaje domyślne `"pl"` (fasada nadal przyjmuje param dla testów, default pl). |
| silniki (google/deepl) | `translate_batch(..., target_lang)` | ZOSTAJE (silnik dostaje "pl" zawsze; Protocol bez zmian — silnik nie deklaruje obsługiwanych języków). |

⚠️ **Silniki NIE deklarują `supported_target_langs()`** — niepotrzebne (LLM umie każdy, DeepL/Google lista martwa). Nie dodaję.

⚠️ Fasada `translate_file` zachowuje param `target_lang="pl"` (default) — bo testy go używają, i gdyby kiedyś wrócił wybór, punkt jest jeden. Ale runner/config nie mają już pola do wyboru — pl na sztywno przez `TARGET_LANG`.

---

## 2. `linebreak.py` — TYLKO POLSKI, kompletne listy ze słownika

**Docstring modułu:** zwięzły, "Tuned for POLISH output — the translation target is always Polish."

**`_CONJUNCTIONS`** — WSZYSTKIE polskie spójniki jednowyrazowe ze źródła sekcja 1A (rdzeń współczesny), ALFABETYCZNIE, komentarz `# source: pl.wiktionary.org Kategoria:Język polski - spójniki (2026-07)`:
```
a, aby, aczkolwiek, albo, albowiem, ale, ani, aniżeli, atoli, aż, ażeby,
bądź, bo, bodaj, bowiem, by, byle,
choć, chociaż, choćby, czy, czyli,
dlatego, dopóki, dopóty, dotąd,
gdy, gdyby, gdyż,
i, ile, ilekroć, im, iż,
jak, jakby, jakkolwiek, jako, jakoby, jednak, jednakże, jeśli, jeżeli,
kiedy,
lecz, ledwie, ledwo, lub,
mianowicie,
natomiast, niby, niczym, niemniej, nim, niż, niżeli,
oraz,
ponieważ, póki, póty, przeto,
skoro,
toteż, tudzież, tylko,
więc, wprawdzie, wszelako,
zanim, zarówno, zaś, zatem,
że, żeby
```
(Pomijam `minus`, `plus` — spójniki matematyczne, nie zdaniowe; nie tworzą punktu podziału napisu. Świadome.)

**`_NON_BREAKING_HEADS`** — kanon przyimków PROSTYCH ze źródła (te co NIE odrywamy od następnego słowa) + warianty fonetyczne, ALFABETYCZNIE, komentarz źródła:
```
bez, beze, dla, do, ku, między, na, nad, nade, o, od, ode, po, pod, pode,
przed, przede, przez, przeze, przy, u, w, we, z, za, ze
```
To kanon szkolny (18 prostych + 8 wariantów fonetycznych) — dokładnie te które fonetycznie zrastają się z rzeczownikiem.

**Osobny pełny zbiór przyimków wtórnych?** — NIE. Logika `_NON_BREAKING_HEADS` chroni tylko przed sierotą "przyimek na końcu wersu". Przyimki wtórne (`według`, `wobec`, `wśród`) są dłuższe (≥5 znaków) — nie tworzą jednoznakowej sieroty jak `w`/`z`. Kanon prostych wystarcza. Świadome (nie rozdymam).

**Znaki cięcia** (`_STRONG_PUNCT`/`_WEAK_PUNCT`) — zostają jako polskie (`.!?…:` / `,;—–`), bo linebreak działa na polskim wyniku. Named escapes dla em/en-dash (już jest).

---

## 3. `chunking.py` — WIELOJĘZYCZNE przez kategorie Unicode

**Zastąp ręczne listy znaków (`『』「」...`) kategoriami `unicodedata`** — obejmuje WSZYSTKIE 754 znaki tnące wszystkich języków, nie garstkę.

**Trzy poziomy podziału, różne zestawy znaków:**
- **`get_sentences`** — tnie na końcu ZDANIA: `. ! ? … 。 ！ ？` + whitespace. Zostaje jak jest (regex zdaniowy + skróty). Znaki końca zdania = podzbiór Po, ale specyficzny (z whitespace po), więc osobny regex — NIE cała kategoria Po (inaczej przecinek dzieliłby zdania).
- **`get_phrases`** — tnie na FRAZACH: znaki kategorii **Pd, Pe, Pf, Po** MINUS znaki końca zdania (te obsłużone w sentences) MINUS apostrof (subtelność). Zbudowane z `unicodedata` — komplet.
- **`get_words`** — tnie na SŁOWACH: whitespace + myślniki/ukośniki + symbole. Zostaje bogaty regex (już naprawiony), ale rozszerzę zestaw separatorów-symboli o kategorie jeśli sensowne.

**Wzorzec Pd/Pe/Pf/Po** (ze źródła 2.4), zbudowany raz na module-load:
```python
_SENTENCE_ENDINGS: Final[frozenset[str]] = frozenset(".!?…。！？")
_PHRASE_CUT_CHARS: Final[str] = "".join(
    ch for cp in range(0x110000)
    if (ch := chr(cp)) not in _SENTENCE_ENDINGS
    and ch != "'" and ch != "’"  # apostrophe: not a phrase break
    and unicodedata.category(ch) in {"Pd", "Pe", "Pf", "Po"}
)
```
**Subtelności zachowane** (jak oryginał text_chunker):
- apostrof `'`/`'` między literami NIE dzieli (wykluczony z phrase-cut).
- kropka w skrótach (Mr./Dr./itd.) NIE kończy zdania — obsłużone w `get_sentences` przez `_ABBREVIATIONS` (już jest).
- kropka między cyframi (liczby) — get_sentences wymaga whitespace po kropce, więc `3.14` nie dzieli. get_phrases: kropka jest sentence-ending → wykluczona z phrase-cut → nie dzieli liczb we frazie. OK.

⚠️ Otwierające `Ps`/`Pi` (`([{«"`) NIE w zestawie tnącym (nie zaczynamy frazy po otwierającym). Zgodne ze źródłem.

**Zależność:** `unicodedata` = stdlib. Zero nowych. `regex` (PyPI `\p{P}`) ODRZUCONE (lekki core).

**WordBreaker/CharBreaker/skróty** — już naprawione w poprzedniej rundzie, sprawdzę kompletność (paragraphy, combineThreshold, rekurencja).

---

## 4. AUDYT: docstringi zwięzłe, listy uporządkowane

- **Docstringi** — przejrzeć cały moduł; skrócić rozdęte (user się skarżył). Google-style ale zwięzłe: jedno zdanie gdzie wystarcza.
- **Listy/stałe** — wszystkie alfabetycznie (spójniki, przyimki, `__all__`).
- **Komentarze źródła** — każda lista ze słownika ma `# source: ...`.
- Inne "po łebkach" — szukam przy przeglądzie.

---

## 5. TESTY (kompletność — dowód że nie po łebkach)

- `linebreak`: test że KONKRETNE spójniki są w zbiorze (`jednak`, `ponieważ`, `aczkolwiek`, `tudzież`, `albowiem`, `niemniej`, `wszelako`) — dowód kompletności ze słownika.
- `linebreak`: test że kanon przyimków prostych kompletny (`bez`,`dla`,`do`,`ku`,`między`,`przez`,`przy`...) + warianty (`beze`,`nade`,`przede`).
- `linebreak`: alfabetyczność (opcjonalnie — trudne dla frozenset; pomijam, kolejność w źródle).
- `chunking`: tnie po CJK (`。`), arabskim (`،`), europejskich cudzysłowach zamykających (`»`), NIE tnie po otwierających (`«`,`(`); apostrof między literami nie dzieli.
- multi-lang usunięty: `target_lang` niedostępny w panelu/config; `TARGET_LANG == "pl"`; `SUPPORTED_TARGET_LANGS` nie istnieje.

---

## PODSUMOWANIE (przed→po)

| Plik | Zmiana |
|---|---|
| constants.py | `SUPPORTED_TARGET_LANGS`+`DEFAULT_TARGET_LANG` → `TARGET_LANG: Final="pl"` |
| config.py | usuń pole `target_lang` |
| user_settings.py | usuń `target_lang` + walidację |
| settings_panel.py | usuń pole języka + import |
| pipeline/types.py | usuń `TranslationSettings.target_lang` |
| runner.py | użyj `TARGET_LANG` |
| linebreak.py | `_CONJUNCTIONS` 63 słowa ze słownika (alfab.), `_NON_BREAKING_HEADS` 26 (kanon+warianty), docstring "POLISH only" |
| chunking.py | `get_phrases` przez unicodedata Pd/Pe/Pf/Po (754 znaki), subtelności zachowane |
| testy | kompletność list, Unicode cięcia, multi-lang usunięty |

**Źródło:** Wikisłownik (spójniki/przyimki), unicodedata UCD 16.0.0 (interpunkcja). Zero nowych zależności.

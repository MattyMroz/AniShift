# Etap 4 — poprawki (audyt adwersarialny po implementacji)

> Druga runda: przegląd całego `anishift/services/translation/` (29 plików) porównany z oryginałami (`scripts/tmp/text_chunker.py`, `srt_equalizer_reference.py`, `../mm_avh_working_space/modules/translator.py`, MangaShift translation). Szukam uproszczeń/zgubionej funkcjonalności przy przepisywaniu. 3 wskazane przez usera + wszystko co znalazłem sam.
>
> Status: PLAN → realizacja w ZADANIU 2.

---

## A) chunking.py — ZGUBIONE ZNAKI I LOGIKA (wskazane #1, potwierdzone)

Porównanie `chunking.py` vs `text_chunker.py` (oryginał). Chunker dzieli **wejściowy txt** który może być obcojęzyczny (JP anime, EN, mieszany) — więc znaki wszystkich języków są potrzebne.

**A1. `_RE_PHRASES` — zgubiony bogaty zestaw.**
- Oryginał `getPhrases` (l.16): `[,;:]\s+ | \s-+\s+ | —\s* | 『』「」„""«»〈〉 | [](){} | 。、 | \...\s+ | \*\s+ | \'\s+`
- Mój: TYLKO `[,;:]\s+ | \s-+\s+ | —\s*`
- **ZGUBIONE:** cudzysłowy CJK/francuskie (`『』「」„""«»〈〉`), nawiasy (`[](){}`), interpunkcja CJK (`。、`), wielokropek `…`, gwiazdka `*`, apostrof `'`.
- **POPRAWKA:** przywróć pełny zestaw znaków rozdzielających frazy. Poprawić regex.

**A2. `_RE_WORDS` — goły `\s+` zamiast bogatego zestawu.**
- Oryginał `getWords` (l.20): `[~@#%^*_+=<>|[](){}"『』「」„""«»〈〉…*''] | [\s\-—/]+ | \.(?=\w{2,}) | ,(?=[0-9]) | 。、` + specjalna logika `while` (dołączanie separatorów-symboli jako osobne tokeny, dołączanie reszty do poprzedniego).
- Mój: TYLKO `(\s+)` + zwykły `_recombine`.
- **ZGUBIONE:** cały bogaty podział słów na symbolach; specjalna logika przyklejania separatorów.
- **POPRAWKA:** przepisz `get_words` wg oryginału (bogaty regex + logika while-loop), otypowane, docstring.

**A3. `_RE_SENTENCES` — zgubiony zero-width `​`.**
- Oryginał (l.12): `[.!?。]+[\s​]+ | …\s+`
- Mój (l.25): `[.!?。]+[\s]+ | …\s+` — **zgubiony `​`** (usunąłem go „naprawiając" ruff RUF001 zamiast użyć escape).
- **POPRAWKA:** przywróć `​` przez escape `​` (nie literalny znak — użyj `re.compile("...\\u200b...")` lub char class z escapem).

**A4. `_recombine` — zgubiona logika skrótów (`nonPunc`) — Mr./Dr./Jan./vs.**
- Oryginał `getSentences` przekazuje `nonPunc` regex do `_recombine` (l.13): lista skrótów `Mr Ms Mrs Dr No Univ Jan Feb ... vs` — jeśli poprzedni fragment kończy się skrótem, NIE traktuje kropki jako końca zdania (scala z następnym).
- Mój `_recombine` (l.56): BEZ parametru `nonPunc` — traktuje każdą kropkę jako koniec zdania.
- **ZGUBIONE:** obsługa skrótów „Mr. Smith" nie dzieli się błędnie na „Mr." + „Smith".
- **POPRAWKA:** przywróć parametr `non_punc` w `_recombine`, przekazuj z `get_sentences` regex skrótów. Rozszerz o polskie skróty (`np`, `itd`, `itp`, `tzn`, `tj`, `dr`, `prof`, `mgr`, `inż`, `ul`, `godz`, `str`, `nr`, `wg`, `św`).

**A5. Uproszczony `CharBreaker` — zgubiona rekurencyjna struktura merge + paragraphy.**
- Oryginał: pełna rekurencja `breakText→breakParagraph→breakSentence→breakPhrase→breakWord` z generycznym `merge(parts, breakPart, combineThreshold)` i obsługą paragrafów (`getParagraphs`, `paragraphCombineThreshold`).
- Mój: spłaszczony `_collect` + `_merge` — pomija poziom paragrafów (`get_paragraphs` istnieje ale NIE jest wołany w `break_text`), nie ma `combineThreshold`.
- **OCENA:** to jest świadome uproszczenie (mój `break_text` idzie sentence→phrase→word, pomija paragraph i combineThreshold). Dla txt→SRT (jeden strumień tekstu) paragrafy rzadkie. **DECYZJA:** przywrócę pełną wierność oryginałowi (rekurencyjny merge + paragraphy + combineThreshold) — bo mini-ficzer txt może dostać wieloakapitowy tekst (książka/transkrypt), a oryginał to obsługiwał. Zachowam `WordBreaker` też (oryginał ma obie klasy; mój zgubił `WordBreaker` całkiem — `ChunkMethod="word"` nieużywalny).

**A6. Zgubiony `WordBreaker` + `method="word"`.**
- Oryginał ma `WordBreaker` (podział po słowach) i `chunk_text(method='word')`.
- Mój: `ChunkMethod = Literal["char","word"]` zadeklarowany, ale `WordBreaker` NIE istnieje, `chunk_text` nie ma `method` param — `"word"` martwy.
- **POPRAWKA:** albo przywróć `WordBreaker` (wierność), albo usuń martwy `ChunkMethod`/`"word"`. **DECYZJA:** przywrócę `WordBreaker` (pełna wierność oryginałowi — user chce nie gubić funkcjonalności), `chunk_text(method=...)`.

---

## B) linebreak.py — LISTY NIEKOMPLETNE, brak oznaczenia „polski" (wskazane #2)

**B1. Docstring nie mówi że to DLA POLSKIEGO.**
- Mój docstring mówi ogólnie „readable subtitle verses". User: zaznacz że linebreak jest dopracowany pod POLSKI.
- **POPRAWKA:** docstring: „Tuned for Polish subtitle output; other languages get a generic split."

**B2. `_CONJUNCTIONS` — 15 słów, polski ma dużo więcej.**
- Mój: `i, oraz, ale, że, więc, bo, aby, lub, a, czy, gdy, jak, kiedy, który, ponieważ`.
- **BRAKUJE (częste PL):** `ani, albo, natomiast, jednak, zatem, dlatego, ponadto, gdyż, skoro, chociaż, choć, mimo, dopóki, jeśli, jeżeli, tudzież, bądź, czyli, toteż, przeto, wszakże, więc, otóż, aczkolwiek, zaś, oraz, albowiem, bowiem, jakkolwiek, jako, niż, aby, żeby, iżby, by, aż, dopóty, odkąd, zanim, podczas, którzy, która, które, których, którym, którą`.
- **POPRAWKA:** rozbuduj do rozsądnie pełnego zestawu częstych polskich spójników.

**B3. `_NON_BREAKING_HEADS` — 16 przyimków, polski ma dużo więcej.**
- Mój: `w, we, z, ze, na, do, od, po, za, o, u, pod, nad, przy, bez, dla`.
- **BRAKUJE (częste PL):** `przez, między, wobec, spod, sprzed, poprzez, według, obok, wśród, ponad, poniżej, wewnątrz, naprzeciw, oprócz, prócz, względem, zamiast, dzięki, wbrew, ku, spomiędzy, znad, sponad, popod, ponad, śród, opodal, wokół, dokoła, wzdłuż, wobec, mimo, poza, obok, około, koło, celem, gwoli`.
- Dodatkowo: zaimki/rodzajniki które nie powinny być sierotą na końcu wersu (`ten, ta, to, ci, te, mój, twój, jego, jej, ich, nasz, wasz, taki, taka, takie`) — ale to bardziej „bez sierot" niż „nie tnij zrostów". **OCENA:** zostawiam listy przyimków; sieroty załatwia `_is_orphan`.
- **POPRAWKA:** rozbuduj przyimki.

**B4. Biblioteka NLP — ROZWAŻONE, ODRZUCONE.**
- Rozważyłem `stopwordsiso`/spaCy. **Decyzja: ręczne listy.** Powód: (a) linebreak potrzebuje SPÓJNIKÓW (ciąć przed) i PRZYIMKÓW (nie ciąć) rozdzielnie — lista stopwords je miesza z zaimkami/partykułami, i tak trzeba kategoryzować ręcznie; (b) spaCy pl = ciężki (łamie lekki core, ZAKAZANE CLAUDE.md); (c) `stopwordsiso` dałby jedną płaską listę bez kategorii = bezużyteczne dla cut-vs-noncut. Ręczne listy = zero wagi, pełna kontrola, KISS. Zapisuję decyzję.

**B5. `_STRONG_PUNCT` / `_WEAK_PUNCT` — sprawdzić kompletność dla PL.**
- Mój `_STRONG` = `.!?…:`, `_WEAK` = `,;—`.
- PL pauza dialogowa to `—` (jest w weak). Ale `–` (en-dash) i `-` (hyphen) używane też jako myślnik. **POPRAWKA:** dodaj `–` (en-dash U+2013) do weak punct. Wielokropek `…` jest w strong (OK, ale też jako `...` trzy kropki — `_best_cut` patrzy na `last_char` = jeden znak, więc `...` złapie tylko ostatnią `.` = strong, OK).

**B6. Edge case: tekst = sam znak interpunkcyjny / same spacje.**
- `split_line(".")` → `(".",)` (len<=max, OK). `split_line("   ")` → strip → `""` → `("",)`. **OCENA:** zwraca pusty string w krotce — akceptowalne (rzadkie), ale dodam test.

---

## C) settings_panel — target langs arbitralne (wskazane #3)

**C1. `_TARGET_LANGS = ("pl","en","de","es","fr","ja")` — arbitralne 6, polski nie wyróżniony.**
- User: **polski = priorytet (default, pierwszy, 100%), reszta = „działa" (generyczny podział).**
- **DECYZJA (mój osąd — czysty wyraz):**
  - SSOT języków docelowych: silnik deklaruje co umie. Ale google/deepl umieją ~30 języków — sztywna lista w silniku też arbitralna. Praktyczny SSOT: stała w domenie `constants.py` `SUPPORTED_TARGET_LANGS` z **`pl` PIERWSZY** + częste inne, DERYWOWANA przez panel (nie sztywna w panelu).
  - `pl` jest defaultem `UserSettings.target_lang` (już jest) i pierwszy w liście (cyklowanie zaczyna od pl).
  - Docstring/komentarz: polski dopracowany (linebreak pod PL); inne języki tłumaczą się (silnik umie), ale podział wersów generyczny.
- **POPRAWKA:** przenieś listę do `translation/constants.py` jako `SUPPORTED_TARGET_LANGS` (pl pierwszy), panel importuje. Usuń sztywne `_TARGET_LANGS` z panelu.

---

## D) INNE ZNALEZIONE (audyt reszty modułu)

**D1. `_batching.py` `_restore` — zgubiona logika comma-newline z mm_avh.**
- mm_avh `_clean_translation` (translator.py:125): `nl_plain + ", " → ",\n"` (gdy marker poprzedzony przecinkiem → przecinek zostaje z newline). Też `NEWLINE_MARKER + ", " → ",\n"`.
- Mój `_restore`: tylko `NEWLINE_MARKER → \n` + strip spacji wokół `\n`. Nie ma specjalnego traktowania `, ` przed markerem.
- **OCENA:** MangaShift `_batching._restore` (którego kopiowałem) TEŻ nie ma tej logiki — to był mm_avh-ism. Dla AniShift spoken/displayed są jednoliniowe (bez `\n` na wejściu), więc NEWLINE_MARKER to no-op. **DECYZJA: NIE przywracam** — to martwa ścieżka w AniShift (brak `\n` w input). Zostawiam jak MangaShift. Odnotowane jako świadome.

**D2. `deepl/_lang_codes.py` — mapowanie tylko en/pt.**
- Mój (kopia MangaShift): `_OVERRIDES = {en: EN-US, pt: PT-PT}`. DeepL wymaga wariantu regionalnego też dla innych (np. `en-GB`, `pt-BR`). Ale my dajemy `pl` (bez wariantu) — działa. Inne języki: `to_deepl_code` robi `.upper()` → `DE`, `FR`, `ES` = poprawne kody DeepL.
- **OCENA:** dla docelowego PL i częstych języków `.upper()` wystarcza. DeepL akceptuje `EN-US`/`EN-GB` ale `EN` samo daje błąd → dlatego override. Pozostałe języki bez wariantu są OK. **DECYZJA: bez zmian** (MangaShift-proven, PL działa). Odnotowane.

**D3. `google/service.py` `is_available` = zawsze True — OK, ale detekcja sieci?**
- Google darmowy, `is_available=True` zawsze. Brak sieci → błąd przy translate (łapany, fallback). **OCENA: OK** (E7 obsłużone przez fallback). Bez zmian.

**D4. `_retry.py` — usunąłem `backoff` param (linear/exponential) i `cap_s` opcjonalność.**
- Plan pierwotny miał `backoff: Literal["linear","exponential"]`. Uprościłem do samego exponential (bo PLR0913). Deepl używa exponential — OK. Google ma własny linear inline. **OCENA: świadome, OK** (jedyny sync konsument to deepl=exponential). Bez zmian.

**D5. `llm/service.py` — kontekst sąsiednich linii (A4 wymagań) nie zaimplementowany.**
- `LlmTranslateConfig.context_lines` istnieje, ale `_build_user` go nie używa. **OCENA:** to etap 5 (realizacja LLM). Szkielet OK. Bez zmian teraz (odnotowane jako etap 5).

**D6. `chunking.py` `chunk_text` — brak `method` param mimo `ChunkMethod` typu.**
- Powiązane z A6. Naprawić razem.

**D7. Test coverage edge case'ów — brakuje.**
- Brak testów: pusty tekst w linebreak, sam znak interpunkcyjny, bardzo długie słowo (>limit bez spacji), tekst mieszany JP/PL w chunkerze, znaki obce (cudzysłowy CJK) w chunkerze, długie PL zdania z różnymi spójnikami (`ani`, `natomiast`, `jednak`).
- **POPRAWKA:** dodaj testy edge case dla chunking i linebreak.

---

## PODSUMOWANIE POPRAWEK (do realizacji)

| # | Plik | Poprawka | Skąd |
|---|------|----------|------|
| A1 | chunking.py | `_RE_PHRASES` pełny zestaw znaków (CJK/fr cudzysłowy, nawiasy, `。、…*'`) | text_chunker.py:16 |
| A2 | chunking.py | `get_words` bogaty regex + logika while-loop | text_chunker.py:18-32 |
| A3 | chunking.py | `_RE_SENTENCES` przywróć `​` | text_chunker.py:12 |
| A4 | chunking.py | `_recombine` z `non_punc` (skróty Mr./Dr. + polskie) | text_chunker.py:13,34-43 |
| A5 | chunking.py | pełny rekurencyjny `CharBreaker` (paragraphy, combineThreshold) | text_chunker.py:94-142 |
| A6 | chunking.py | przywróć `WordBreaker` + `chunk_text(method=)` | text_chunker.py:46-91,145-150 |
| B1 | linebreak.py | docstring „dla polskiego" | user |
| B2 | linebreak.py | `_CONJUNCTIONS` pełne PL spójniki | wiedza PL |
| B3 | linebreak.py | `_NON_BREAKING_HEADS` pełne PL przyimki | wiedza PL |
| B5 | linebreak.py | dodaj `–` en-dash do weak punct | wiedza PL |
| C1 | constants.py + panel | `SUPPORTED_TARGET_LANGS` (pl pierwszy), panel derywuje | user |
| D7 | testy | edge case'y chunking + linebreak | — |

**Bez zmian (świadome, odnotowane):** D1 (comma-newline martwe w AniShift), D2 (lang codes PL działa), D3 (is_available), D4 (retry uproszczenie OK), D5 (context_lines = etap 5).

**Zależności:** ZERO nowych (biblioteka NLP odrzucona — ręczne listy).

# 11-elevenreader-tts

Nowy silnik lektora AniShift: ElevenReader (Eleven v4, głosy Piotr Fronczewski i Adam) przez prawdziwy Chrome z
zalogowaną sesją. Cały odcinek jest nagrywany jednym dokumentem i cięty na klipy kwestii w ciszy. W tym samym
workstreamie: głośność lektora mierzona względem oryginału z limiterem, przycinanie ciszy na brzegach klipów i
tempo na głos. `elevenbytes` zostaje zapasem.

## Status

Zrobione i scalone do `main` (stan z 2026-11-02): silnik ElevenReader, mierzona głośność lektora z limiterem,
przycinanie ciszy i tempo na głos ([PR #78](https://github.com/MattyMroz/AniShift/pull/78)); poprawki nagrań z
brakującą kwestią i napisy piosenek ([#83](https://github.com/MattyMroz/AniShift/pull/83)); dwa odcinki naraz, limit 2
([#89](https://github.com/MattyMroz/AniShift/pull/89), [#90](https://github.com/MattyMroz/AniShift/pull/90));
domyślne tempo Fronczewskiego 1,35 ([#93](https://github.com/MattyMroz/AniShift/pull/93)); wykrywanie kawałków
zwracających tekst bez mowy ([#96](https://github.com/MattyMroz/AniShift/pull/96)).

Czeka na właściciela: odbiór na prawdziwych odcinkach (K2 z `outcomes/02-parallel-documents.md` ma status
`pending-human`; K3, ucho właściciela, nie ma zapisu w repo). Otwarte zgłoszenie
[#95](https://github.com/MattyMroz/AniShift/issues/95): wymuszenie wypowiedzenia linii, którą ElevenReader zwraca
bez mowy. `outcomes/01-elevenreader-engine.md` (E10) nie powstał.

## Kolejność czytania

1. [intent.md](intent.md) — problem, kierunek, ryzyko regulaminu, odrzucone drogi.
2. [specification.md](specification.md) — ustalenia, wymagania, zakazy, kryteria sukcesu, otwarta decyzja D1.
3. [plan.md](plan.md) — stan z dowodami, decyzja „port czy EDP”, design, etapy E0–E10 z zależnościami i pasami
   zapisu, punkty kontrolne K1–K3.
4. [file-map.md](file-map.md) — pliki źródłowe i dotknięte, z przypisaniem do etapów.
5. [plans/02-parallel-documents.md](plans/02-parallel-documents.md) i
   [outcomes/02-parallel-documents.md](outcomes/02-parallel-documents.md) — kilka odcinków naraz.

Artefakt nieutworzony: `outcomes/01-elevenreader-engine.md` (E10).

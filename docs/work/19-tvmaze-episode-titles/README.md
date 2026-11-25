# 19-tvmaze-episode-titles

Angielskie tytuły odcinków z TVmaze (issue #58). Status: research, specyfikacja i plan odświeżone 2026-11-26 na
`main` @ `1f76e30`, decyzje D1-D7 rozstrzygnięte przez właściciela 2026-11-25, kod niezaczęty.

| Plik | Zawartość |
| --- | --- |
| `research.md` | stan w kodzie, TVmaze (endpointy, limity, licencja, kształt odpowiedzi), pomiar na 23 subskrypcjach |
| `specification.md` | decyzje D1-D7, wymagania, inwarianty, zakazy i warunki sukcesu |
| `plan.md` | pliki, fazy, testy, migracja stanu, checkpoint właściciela i bramki |
| `reviews/round-1.md` | przegląd artefaktów z 2026-10-25 (przed odświeżeniem) |

Wniosek w jednym zdaniu: TVmaze zgadza się z numeracją ani.zip w 23 na 23 seriali i daje angielski tytuł dla 26
wyemitowanych odcinków, które dziś pokazują romaji albo „Odcinek N”, a `ListedEpisode.title` z
`AcquisitionService.episodes()` staje się jedynym źródłem tytułu odcinka dla workstreamu 23.

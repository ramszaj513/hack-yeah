# Sugestie efemeryczne przeliczane on-demand zamiast trwałych propozycji

Solver nie zapisuje propozycji w bazie: przy każdym `GET /state` (czyli po każdym zdarzeniu)
przelicza na bieżąco rozłączny zestaw **sugerowanych objazdów** z Residual Pool. Przejęty
objazd (Claim) jest trwały, ale sama sugestia istnieje tylko jako wynik obliczenia.
Rozważaliśmy zapisywanie propozycji w tabeli `proposals` oraz klasyczny model z przypinaniem
i re-solve przy każdym zdarzeniu (ADR 0003/0004). Odrzuciliśmy trwałe propozycje, bo wymagają
retrakcji, powiadomień i rozwiązywania konfliktów między nieaktualnymi wierszami. Efemeryczne
sugestie są zawsze spójne z pulą, a ich koszt przeliczenia jest znikomy przy skali demo.

## Consequences

- „Auto-run po zdarzeniu” realizuje `GET /state`; nie ma osobnego endpointu `/optimize`.
- Sugestia nie ma trwałego identyfikatora — `POST /claim` przekazuje jej zawartość
  (`trip_id`, `need_id`, `crate_ids`) i waliduje ją na bieżąco; nieaktualna → `409`.
- Sugestie są wzajemnie rozłączne w obrębie jednego przeliczenia, więc przejęcie dowolnego
  podzbioru nie powoduje konfliktów.
- Brak powiadomień push i retrakcji — kierowca widzi aktualny stan przy odświeżeniu.
- Przy większej skali trzeba by dodać cache/inkrementalność; poza zakresem MVP.

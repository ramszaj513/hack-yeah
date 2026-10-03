# Zasugeruj i przejmij zamiast ciągłego re-planu i nieprzypiętych propozycji

Solver produkuje **sugerowane objazdy**, które kierowca jawnie **przejmuje** (Claim). Skrzynki i slot znikają z puli dopiero po przejęciu. Odrzucamy zarówno stary model „nieprzypiętych propozycji z natychmiastowym re-solve przy każdym zdarzeniu” (stary ADR 0003), jak i pełne przypinanie z góry. Ciągły re-plan powodował wyścigi, „martwe” powiadomienia i burze solvera; pełne przypinanie blokowało zasoby przez wolno reagujących. Model „zasugeruj → przejmij” jest prostszy, przewidywalny i odpowiada realnym przejazdom, gdzie decyzję podejmuje kierowca.

## Consequences

- Znika potrzeba retrakcji powiadomień i debounce — sugerowany objazd po prostu wygasa bez przejęcia.
- Między wygenerowaniem a przejęciem dwaj kierowcy mogą zobaczyć tę samą propozycję; rozwiązujemy to atomowym przejęciem po stronie serwera (pierwszy wygrywa).
- Brak ciągłego optymalnego planu „na teraz” — świadomie stawiamy prostotę i zrozumiałość nad globalną optymalność.
- Można później dodać limit czasu ważności sugestii, ale nie jest wymagany do MVP.

## Uzupełnienie

ADR 0005 precyzuje realizację: sugestie są efemeryczne i przeliczane przy każdym `GET /state`
(czyli po każdym zdarzeniu). To nie jest „ciągły re-plan” w duchu odrzuconym powyżej — nie ma
trwałych propozycji, powiadomień ani retrakcji; solver zwraca po prostu świeży, rozłączny
zestaw sugestii nad bieżącą pulą.

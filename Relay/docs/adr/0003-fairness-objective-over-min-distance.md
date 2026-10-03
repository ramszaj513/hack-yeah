# Cel sprawiedliwościowy (wklęsła użyteczność) zamiast minimalizacji dystansu

Solver nie minimalizuje czasu ani odległości, lecz maksymalizuje `Σ_n severity_n · log(1 + delivered_n)` — wklęsłą użyteczność ważoną pilnością punktów potrzeb. Rozważaliśmy klasyczny cel „najkrótsza droga / najniższy koszt”, typowy dla aplikacji przewozowych, oraz twarde ograniczenie „każdy punkt dostaje co najmniej X”. Pierwszy systematycznie zagładza dalekie i trudniejsze punkty, drugi bywa niewykonalny przy braku zasobów. Wklęsła użyteczność daje diminishing returns: każda kolejna jednostka dla już obsłużonego punktu jest warta mniej, więc solver sam się rozkłada i nie może zignorować pilnego, odległego punktu. To jest główna różnica względem „kolejnego Ubera”.

## Consequences

- Sprawiedliwość jest mierzalna: **Starvation Index** i wskaźnik zapełnienia punktów.
- Możliwy jest uczciwy kompromis „mniej optymalny dystansowo, ale szerszy zasięg” — pokazujemy go przełącznikiem `nearest_fit ↔ fair_share`.
- Wklęsły cel utrudnia dokładne ILP, ale rozwiązanie zachłanne (marginal gain) jest szybkie i wytłumaczalne.
- Zdefiniowanie `delivered_n` (jednostki łączne vs per kategoria) wymaga decyzji; MVP używa jednostek łącznych.

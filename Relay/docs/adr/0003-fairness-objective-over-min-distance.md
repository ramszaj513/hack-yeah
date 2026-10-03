# A fairness objective (concave utility) instead of distance minimization

The solver does not minimize time or distance; it maximizes `Σ_n severity_n · log(1 + delivered_n)` — a concave utility weighted by need-point urgency. We considered the classic objective "shortest path / lowest cost", typical of ride-hailing apps, and a hard constraint "every point gets at least X". The first systematically starves distant and harder points; the second is often infeasible when resources are scarce. Concave utility gives diminishing returns: each additional unit for an already-served point is worth less, so the solver spreads itself out and cannot ignore an urgent, distant point. This is the main difference from "yet another Uber".

## Consequences

- Fairness becomes measurable: the **Starvation Index** and the point fill rate.
- An honest trade-off is possible: "less optimal in distance, but broader in reach" — we show it with the `nearest_fit ↔ fair_share` switch.
- A concave objective makes exact ILP harder, but a greedy solution (marginal gain) is fast and explainable.
- Defining `delivered_n` (total units vs per category) requires a decision; the MVP uses total units.

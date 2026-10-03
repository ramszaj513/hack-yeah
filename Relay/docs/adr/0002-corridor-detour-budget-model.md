# Corridor and detour-budget model instead of a global VRP

We compute matching locally: each **trip** is a segment `origin → destination` with a
**detour budget**, and crates and need-points fall into a **corridor** drawn around it.
Instead of creating new jobs (as in a dispatch model), we use trips that are happening
anyway. We considered the classic approach — a single global solve over the whole pool (old
ADR 0004) — and independent solves per need-point (old ADR 0003). We rejected both: a global
solve grows in cost with total demand, and per-point solving loses competition for the same
resources. The corridor model is inherently incremental, local, and computationally cheap.

## Consequences

- Complexity on the order of `O(trips × nearby crates)` — no distance matrix and no VRP solver.
- Match quality depends on the quality of declared trips; if nobody drives in a given
  direction, a crate waits.
- Distances are approximate (Haversine), so `extra_minutes` is an estimate — we always show
  it explicitly on the map.
- The model is resilient to loss of connectivity: trips and corridors can be recomputed
  locally, without the cloud.

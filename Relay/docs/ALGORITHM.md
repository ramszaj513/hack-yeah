# Relay — algorithm and cases

A description of the two-phase solver, the metrics, and the full case catalog. Related
decisions: ADR 0002 (corridor), ADR 0003 (fairness), ADR 0005 (ephemeral suggestions).

## Goal

Match crates to trips "that are happening anyway" and distribute aid fairly, rather than
minimizing distance. We maximize:

```
U = Σₙ severityₙ · Σ_c log(1 + deliveredₙ,c)
```

`deliveredₙ,c` is the number of crates of category `c` already delivered to point `n`.
The concavity per category means each additional crate is worth less, so the solver spreads
itself out and cannot starve a distant, urgent point.

## Phase 1 — candidate generation

For every pair (trip `t` with status `available`, point `N` with status `open`):

1. Compute `detour_km(t,N) = dist(O,N) + dist(N,D) − dist(O,D)`.
   If `> allowance_km(t)` → reject.
2. Detour route = polyline `[O, N, D]`. Collect `available` crates for which
   `polyline_dist(crate, [O,N,D]) ≤ corridor_half_km(t)`.
3. Filter out crates whose category has `remaining == 0` at `N`.
4. `s = min(slots_free, Σ remaining(N))`. Select `s` crates greedily:
   - pick the category with the largest marginal gain
     `Δ(c) = severity_N · [log(1+delivered_c+1) − log(1+delivered_c)]`,
   - from that category take the nearest crate (tie-break: `id`).
   Mixing categories within one detour is allowed.
5. If ≥ 1 crate was selected → candidate `(t, N, crate_ids, extra_minutes, utility_gain)`.

Complexity: `O(trips × points × crates)` — no global matrix and no VRP.

## Phase 2 — greedy selection (disjoint suggestions)

```
used_trips, claimed_crates = ∅
while True:
    best = argmax over candidates(score, tie_breaks)
    if best is None: break
    emit best
    used_trips += best.trip
    claimed_crates += best.crates
    update delivered/remaining in memory
    close N if all remaining == 0
    rebuild candidates skipping used_trips and claimed_crates
```

Scorers (mode switch):

| Mode | `score` | tie-breaks |
|---|---|---|
| `fair_share` | `utility_gain` | `(−extra_minutes, trip_id, need_id)` |
| `nearest_fit` | `−extra_minutes` | `(utility_gain, trip_id, need_id)` |

Suggestions are disjoint (no crate or trip appears in two), so the client can claim any
subset without surprises. After a `claim` the pool changes and `GET /state` recomputes a
fresh, disjoint set.

## Metrics

- `unmet_n = Σ_c remaining(n,c)`
- `capacity_n = Σ_c needed(n,c)`
- `Starvation Index = Σ_n severity_n·(unmet_n/capacity_n) / Σ_n severity_n × 100%`
  (for `capacity_n == 0` the point is closed and skipped)
- `fill_n = 100% · (1 − unmet_n/capacity_n)`

The panel shows the `Starvation Index` globally and `fill_n` per point.

## Case catalog

### Input / validation

| # | Case | Behavior |
|---|---|---|
| 1 | Unknown category | `422` |
| 2 | Coordinates out of range | `422` |
| 3 | `detour_budget_min ≤ 0` or `slots_free ≤ 0` | `422` |
| 4 | `severity` outside 1..5 | `422` |
| 5 | All `needed == 0` when creating a point | `closed` immediately |
| 6 | Duplicate `id` | `409` |
| 7 | Missing body / bad JSON | `422` |

### Candidate generation

| # | Case | Result |
|---|---|---|
| 8 | No crates / trips / open points | no suggestions |
| 9 | `O == D` (point trip) | `seg_dist` computes the distance to the point |
| 10 | `detour_km > allowance` | pair rejected |
| 11 | No crates in corridor `[O,N,D]` | pair rejected |
| 12 | Crates exist, but the category is not needed | rejected |
| 13 | `slots_free` less than needed | take `slots_free` |
| 14 | Fewer crates than needed | take all available |
| 15 | A crate in the corridor of many trips | candidate for each; greedy assigns it once |
| 16 | `delivered_c ≥ needed_c` | category excluded |
| 17 | Equal marginal gains | tie-break by `id` |
| 18 | Point fully satisfied | `closed`, skipped |

### Greedy / conflicts

| # | Case | Handling |
|---|---|---|
| 19 | Trip already used in a suggestion | skipped |
| 20 | Crate already assigned | skipped |
| 21 | Point closed during the loop | skipped |
| 22 | Candidate invalidated | skipped on rebuild |
| 23 | No new candidate in a pass | end of loop |
| 24 | Point served partially by several trips | allowed |
| 25 | Equal `detour` in `nearest_fit` | tie-break `utility_gain`, then `id` |
| 26 | All trips used | no further suggestions |

### Claim

| # | Case | Behavior |
|---|---|---|
| 27 | `trip_id` already `used` | `409` |
| 28 | Crate already `claimed` | `409` |
| 29 | Number of crates of a category > `remaining` | `409` |
| 30 | Point `closed` | `409` |
| 31 | Valid claim | transaction: crates→claimed, trip→used, delivered += n, maybe need→closed |
| 32 | Two fast claims | `Lock` + transaction; the first wins |

### Control

| # | Case | Behavior |
|---|---|---|
| 33 | Unknown `mode` | `400` |
| 34 | Mode change | stored in `settings`; `/state` recomputes |
| 35 | `POST /reset` | `DELETE` tables + seed; `200` |
| 36 | No seed after restart | `db.init()` seeds if empty |

## Known MVP limitations

- Greedy does not give a global optimum (a deliberate trade-off — see ADR 0003).
- The sum of logs per category favors points with many categories; acceptable for the demo.
- The corridor is computed along the polyline `[O,N,D]`, not along real roads (ADR 0002).

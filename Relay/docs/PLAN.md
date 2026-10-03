# Relay — implementation plan (2 h, 1 coding agent)

Master project plan. Reference docs: `ARCHITECTURE.md`, `ALGORITHM.md`,
`IMPLEMENTATION.md`, `GLOSSARY.md`, `adr/`.

## 0. Locked decisions

| Area | Decision |
|---|---|
| Stack | Python + FastAPI + SQLite; frontend `index.html` + Leaflet from CDN, no build step |
| Time | Geometry only; departure windows are skipped |
| Detours | 1 trip = exactly 1 detour |
| Fairness | `U = Σₙ severityₙ · Σ_c log(1 + deliveredₙ,c)` |
| Deliveries | Partial, min. 1 crate |
| Trigger | After every event; `GET /state` recomputes suggestions |
| Scale | Area ~30×30 km, speed 50 km/h (0.8333 km/min) |
| Views | Admin map only |
| Comparison | Global switch `fair_share` / `nearest_fit` |
| Tests | One end-to-end smoke test |
| QR | Skipped; a crate has a text `id` |

Suggestions are **ephemeral** — we do not store them in the database; we recompute them in
`GET /state` (see ADR 0005). "Auto-run after an event" = the frontend refreshes `/state`
after every POST/claim.

## 1. Architecture

```
Relay/
├─ app/
│  ├─ config.py     # R, LAT0, SPEED_KMH, DB_PATH, MODES
│  ├─ db.py         # SQLite schema, seed, queries, transactions, Lock
│  ├─ geometry.py   # xy(), dist(), seg_dist(), polyline_dist()
│  ├─ solver.py     # phase 1 (candidates), phase 2 (greedy), metrics
│  └─ main.py       # FastAPI, validation, endpoints
├─ web/
│  ├─ index.html
│  ├─ app.js
│  └─ style.css
├─ tests/
│  └─ test_smoke.py
├─ requirements.txt # fastapi, uvicorn, pytest, httpx
└─ run.sh
```

Flow: `POST` → validation → SQLite → the frontend calls `GET /state` → the server computes
candidates and the greedy pass → returns disjoint suggestions → `POST /claim` (transaction)
→ refetch.

One uvicorn worker + a `threading.Lock` around mutations and solver runs = no races.

## 2. Data model

```sql
CREATE TABLE crates(
  id TEXT PRIMARY KEY, category TEXT NOT NULL, lat REAL, lon REAL,
  status TEXT NOT NULL DEFAULT 'available');       -- available | claimed

CREATE TABLE trips(
  id TEXT PRIMARY KEY, olat REAL, olon REAL, dlat REAL, dlon REAL,
  detour_budget_min REAL NOT NULL, slots_free INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'available');       -- available | used

CREATE TABLE need_points(
  id TEXT PRIMARY KEY, name TEXT, lat REAL, lon REAL,
  severity INTEGER NOT NULL DEFAULT 1,             -- 1..5
  status TEXT NOT NULL DEFAULT 'open');            -- open | closed

CREATE TABLE requirements(
  need_id TEXT, category TEXT, needed INTEGER NOT NULL,
  delivered INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(need_id, category));

CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);  -- mode
```

`remaining(need,cat) = max(0, needed − delivered)`. A point closes when all
`remaining == 0`.

## 3. Geometry and constants

```python
R = 6371.0; LAT0 = 52.2297                      # Warsaw as the map center
SPEED_KMH = 50.0; SPEED_KM_PER_MIN = SPEED_KMH/60.0

def xy(lat, lon):                               # local flat system in km
    return (R*radians(lon)*cos(radians(LAT0)), R*radians(lat))
def dist(a, b): ...                             # km (Euclid in xy)
def seg_dist(p, a, b): ...                      # clamped projection (handles a==b)
def polyline_dist(p, pts): min(seg_dist(...))   # distance to the O→N→D route
```

- `allowance_km(t) = detour_budget_min × SPEED_KM_PER_MIN`
- `corridor_half_km(t) = allowance_km(t) / 2`
- `detour_km(t,N) = dist(O,N) + dist(N,D) − dist(O,D)`
- `extra_minutes = detour_km / SPEED_KM_PER_MIN`

The local projection is equivalent to a "straight line" at 30 km (ADR 0002).

## 4. Algorithm

### Phase 1 — candidate generation (per trip × point pair)

1. Compute `detour_km(t,N)`; if `> allowance_km(t)` → reject.
2. Detour route = polyline `[O, N, D]`; collect `available` crates with
   `polyline_dist(crate, [O,N,D]) ≤ corridor_half_km(t)`.
3. Filter out categories whose `N` no longer needs them (`remaining == 0`).
4. `s = min(slots_free, Σ remaining(N))`; select `s` crates greedily: first the
   category with the largest `Δ(c) = severity_N · [log(1+delivered_c+1) − log(1+delivered_c)]`,
   then the nearest crate of that category (tie-break `id`). Mixed categories allowed.
5. If ≥ 1 crate was selected → candidate `(t, N, crate_ids, extra_minutes, utility_gain)`.

### Phase 2 — greedy selection (disjoint suggestions)

```
used_trips, claimed_crates = ∅
while True:
    best = argmax over candidates(score, tie_break)
    if none: break
    emit best
    used_trips += best.trip; claimed_crates += best.crates
    update delivered/remaining in memory; close N if full
    rebuild candidates skipping used_trips and claimed_crates
```

- `fair_share`: `score = utility_gain`, tie-break `(−extra_minutes, trip_id, need_id)`.
- `nearest_fit`: `score = −extra_minutes`, tie-break `(utility_gain, trip_id, need_id)`.

Suggestions are disjoint → the client can claim any subset without surprises.

### Metrics

- `unmet_n = Σ_c remaining(n,c)`; `capacity_n = Σ_c needed(n,c)`.
- `Starvation Index = Σ_n severity_n·(unmet_n/capacity_n) / Σ_n severity_n × 100%`.
- Panel: % fill per point + the global index.

## 5. Case catalog

### 5a. Input / validation

| # | Case | Behavior |
|---|---|---|
| 1 | Unknown category | `422` |
| 2 | Coordinates out of range | `422` |
| 3 | `detour_budget_min ≤ 0` or `slots_free ≤ 0` | `422` |
| 4 | `severity` outside 1..5 | `422` |
| 5 | All `needed == 0` when creating a point | `closed` immediately, never a candidate |
| 6 | Duplicate `id` | `409` |
| 7 | Missing body / bad JSON | `422` |

### 5b. Candidate generation

| # | Case | Result |
|---|---|---|
| 8 | No crates / trips / open points | no suggestions |
| 9 | `O == D` (point trip) | degenerate segment; `seg_dist` → distance to the point |
| 10 | `detour_km > allowance` | pair rejected |
| 11 | No crates in corridor `[O,N,D]` | pair rejected |
| 12 | Crates exist, but the category is not needed | rejected |
| 13 | `slots_free` less than needed | take `slots_free` |
| 14 | Fewer crates than needed | take all available |
| 15 | A crate in the corridor of many trips | candidate for each; greedy assigns it once |
| 16 | `delivered_c ≥ needed_c` | category excluded |
| 17 | Equal marginal gains | tie-break by `id` |
| 18 | Point fully satisfied | `closed`, skipped |

### 5c. Greedy / conflicts

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

### 5d. Claim

| # | Case | Behavior |
|---|---|---|
| 27 | `trip_id` already `used` | `409` |
| 28 | Crate already `claimed` | `409` |
| 29 | Number of crates of a category > `remaining` | `409` |
| 30 | Point `closed` | `409` |
| 31 | Valid claim | transaction: crates→claimed, trip→used, delivered += n, maybe need→closed |
| 32 | Two fast claims | `Lock` + transaction; the first wins |

### 5e. Control

| # | Case | Behavior |
|---|---|---|
| 33 | Unknown `mode` | `400` |
| 34 | Mode change | stored in `settings`; `/state` recomputes |
| 35 | `POST /reset` | `DELETE` tables + seed; `200` |
| 36 | No seed after restart | `db.init()` seeds if empty |

## 6. API

| Method | Path | Body → Response |
|---|---|---|
| `GET` | `/state` | `{mode, crates, trips, need_points, suggestions, metrics}` |
| `POST` | `/crates` | `{category, lat, lon}` → `{id}` |
| `POST` | `/trips` | `{olat,olon,dlat,dlon,detour_budget_min,slots_free}` → `{id}` |
| `POST` | `/need-points` | `{name,lat,lon,severity,requirements:{cat:qty}}` → `{id}` |
| `POST` | `/claim` | `{trip_id, need_id, crate_ids}` → `200` / `409` |
| `POST` | `/mode` | `{mode}` → `200` / `400` |
| `POST` | `/reset` | — → `200` |

## 7. Frontend

- Leaflet map (OSM), center `LAT0`, zoom covering ~30 km.
- Need-points: circle, color by `severity`, size by unmet.
- Trips: grey `O→D` lines.
- Suggestions: polyline `O→crates→N→D`, with a **Claim** button in the panel.
- Panel: `Starvation Index`, fill bars, mode switch, `Reset`.
- After every POST/claim: `fetch('/state')` → redraw (this implements auto-run).

## 8. Seed (contrast scenario)

- ~6 need-points in a 30×30 km square, including a far one with `severity=5`.
- ~15 crates in trip corridors.
- ~5 trips crossing the center, budgets varied 5–15 min.
- Tuned so that `nearest_fit` serves a nearby low-urgency point, while `fair_share`
  reaches the far `severity=5` point. That is the demo moment.

## 9. Smoke test (`tests/test_smoke.py`)

1. `GET /state` → there are suggestions.
2. `POST /claim` of the first suggestion → `200`.
3. `GET /state` → crates `claimed`, trip `used`, `delivered` grew, the suggestion is gone.
4. `POST /mode {nearest_fit}` → `200`, different ordering.
5. `POST /reset` → the state returns to the seed.

## 10. 2 h schedule

| Time | Step | Checkpoint |
|---|---|---|
| 0:00–0:15 | `config`, `db` (DDL + seed) | `GET /state` returns the seed without the solver |
| 0:15–0:50 | `geometry` + `solver` | disjoint fair vs nearest suggestions |
| 0:50–1:10 | `main` (endpoints + claim + Lock) | smoke test passes |
| 1:10–1:35 | frontend: map, panel, toggle, claim | clickable end to end |
| 1:35–1:50 | contrast seed + manual demo | mode difference visible |
| 1:50–2:00 | polish, freeze, README run | `./run.sh` starts from scratch |

## 11. Risks

- **No contrast in the seed** → the biggest demo risk; spend +10 min on the seed.
- **Corridor too wide** → everything falls into one candidate; vary the budgets.
- **Greedy favors large points** (sum of logs per category) → acceptable in the MVP.

## 12. Hard cuts

No ILP/OR-Tools, no QR, no time windows, no auth, no animations, no multiple detours per trip,
no unit tests.

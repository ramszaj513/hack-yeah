# Relay — implementation (2 h, 1 agent)

Step by step. Algorithm details: `ALGORITHM.md`; components: `ARCHITECTURE.md`.

## Order of work

### Step 0 — skeleton (0:00–0:05)

- `mkdir -p app web tests`; `requirements.txt`: `fastapi`, `uvicorn`, `pytest`, `httpx`.
- `config.py`: `R`, `LAT0`, `SPEED_KMH`, `SPEED_KM_PER_MIN`, `DB_PATH`, `MODES`.

### Step 1 — data and seed (0:05–0:15)

- `db.py`: DDL (5 tables), `init()` seeds if empty; `get_conn()`, `Lock`.
- A `seed.py`-style function in `db.py`: ~6 need-points (including a far `severity=5` one),
  ~15 crates, ~5 trips with budgets 5–15 min.
- Checkpoint: `GET /state` (still without the solver) returns the seed.

### Step 2 — geometry (0:15–0:20)

- `geometry.py`: `xy`, `dist`, `seg_dist` (clamped; `a==b` → distance to the point),
  `polyline_dist`.

### Step 3 — solver (0:20–0:50)

- `solver.py`:
  - `build_candidates(trips, need_points, crates, delivered, mode)` — phase 1,
  - `solve(...)` — phase 2 greedy, returns disjoint suggestions,
  - `metrics(...)` — Starvation Index and fill per point.
- Checkpoint: for the seed, disjoint suggestions are visible; `fair_share` and `nearest_fit` differ.

### Step 4 — API (0:50–1:10)

- `main.py`: `GET /state`, `POST /crates|/trips|/need-points|/claim|/mode|/reset`.
- Input validation per the case tables (section 5a of ALGORITHM.md).
- `claim` in a transaction under `Lock`; returns `409` for stale suggestions.
- Smoke test `tests/test_smoke.py`.

### Step 5 — frontend (1:10–1:35)

- `web/index.html`: map container + panel; Leaflet and CSS from CDN.
- `web/app.js`: `loadState()` → `fetch('/state')` → draw markers, routes, and suggestions;
  `claim()`; `setMode()`; `reset()`; after every action `loadState()`.
- `web/style.css`: simple two-column layout.

### Step 6 — contrast seed (1:35–1:50)

- Tune positions/urgencies so that under `nearest_fit` the far point is ~0%, while under
  `fair_share` it is served.
- Write down the demo narrative.

### Step 7 — freeze (1:50–2:00)

- `run.sh`: `uvicorn app.main:app --reload`.
- README: how to run. Freeze the scope.

## Smoke test (E2E)

```
1. GET /state               -> there are suggestions
2. POST /claim (first)      -> 200
3. GET /state               -> crates claimed, trip used, delivered up, suggestion gone
4. POST /mode nearest_fit   -> 200, different ordering
5. POST /reset              -> 200, state returns to the seed
```

## Hard cuts

No ILP/OR-Tools, no QR, no time windows, no auth, no animations, no multiple detours per
trip, no unit tests.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| No fair vs nearest contrast in the seed | spend +10 min on the seed; it is the heart of the demo |
| Corridor too wide (large budget) | vary the trip budgets in the seed |
| Greedy favors large points | accept it; out of MVP scope |
| Race on claim | `Lock` + transaction, first one wins |

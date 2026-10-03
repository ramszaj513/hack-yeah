# Relay — architecture

The concrete architecture of the MVP built in ~2 h by one agent. No cloud dependencies.

## Component overview

```
┌──────────────────────────────────────────────────────────┐
│  Frontend (index.html + Leaflet from CDN)                │
│  - OSM map, seed, mode switch, fairness panel            │
│  - after every POST/claim: fetch('/state')               │
└───────────────────────────┬──────────────────────────────┘
                            │ REST / JSON
┌───────────────────────────▼──────────────────────────────┐
│  Backend (FastAPI, one worker + threading.Lock)          │
│  - GET /state  → computes suggestions (auto-run)         │
│  - POST /crates /trips /need-points /claim /mode /reset  │
│  - SQLite: crates, trips, need_points, requirements      │
└───────────────────────────┬──────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────┐
│  Solver (solver.py)                                      │
│  Phase 1: candidates (corridor + detour cost)            │
│  Phase 2: greedy proportional fairness / nearest-fit     │
└──────────────────────────────────────────────────────────┘
```

## File layout

```
Relay/
├─ app/
│  ├─ config.py     # R, LAT0, SPEED_KMH, DB_PATH, MODES
│  ├─ db.py         # SQLite schema, seed, queries, transactions, Lock
│  ├─ geometry.py   # xy(), dist(), seg_dist(), polyline_dist()
│  ├─ solver.py     # phase 1, phase 2, metrics
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

## Data model (SQLite)

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

Post-MVP (ADR 0006/0007) adds two tables:

```sql
CREATE TABLE detours(
  id TEXT PRIMARY KEY, trip_id TEXT, need_id TEXT, mode TEXT,
  extra_minutes REAL, utility_gain REAL,
  status TEXT NOT NULL DEFAULT 'suggested',   -- suggested|claimed|picked_up|delivered|expired
  created_at REAL, expires_at REAL);

CREATE TABLE detour_crates(detour_id TEXT, crate_id TEXT, PRIMARY KEY(detour_id, crate_id));
```

## Geometry and constants

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

At a 30 km scale the local projection is equivalent to a "straight line" (per ADR 0002).

## API

| Method | Path | Body → Response |
|---|---|---|
| `GET` | `/state` | `{mode, crates, trips, need_points, suggestions, metrics}` |
| `POST` | `/crates` | `{category, lat, lon}` → `{id}` |
| `POST` | `/trips` | `{olat,olon,dlat,dlon,detour_budget_min,slots_free}` → `{id}` |
| `POST` | `/need-points` | `{name,lat,lon,severity,requirements:{cat:qty}}` → `{id}` |
| `POST` | `/claim` | `{trip_id, need_id, crate_ids}` → `200` / `409` |
| `POST` | `/mode` | `{mode}` → `200` / `400` |
| `POST` | `/reset` | — → `200` |

Post-MVP endpoints (ADR 0006/0007):

| Method | Path | Body → Response |
|---|---|---|
| `GET` | `/health` | liveness probe, no DB access → `{status, service, version}` |
| `GET` | `/config` | → `{categories, modes, ttl_seconds, center}` |
| `GET` | `/state?mode=<mode>` | preview another scorer without persisting or changing the stored mode → `200` / `400` |
| `PATCH` | `/crates/{id}` | `{category?,lat?,lon?}` → `200` |
| `DELETE` | `/crates/{id}` | — → `200` / `409` |
| `PATCH` | `/trips/{id}` | `{olat?,olon?,dlat?,dlon?,detour_budget_min?,slots_free?}` → `200` |
| `DELETE` | `/trips/{id}` | — → `200` / `409` |
| `PATCH` | `/need-points/{id}` | `{name?,lat?,lon?,severity?,requirements?,status?}` → `200` |
| `DELETE` | `/need-points/{id}` | — → `200` |
| `POST` | `/claim` | `{detour_id}` **or** `{trip_id,need_id,crate_ids}` → `200` / `409` |
| `POST` | `/detours/{id}/pickup` | — → `200` / `409` |
| `POST` | `/detours/{id}/deliver` | — → `200` / `409` |

`GET /state` is also the "auto-run": each time it recomputes candidates and the greedy pass
over the current pool. There is no separate `/optimize` endpoint and no persistent proposals
(see ADR 0005).

## Frontend

- Leaflet map (OSM), center `LAT0`, zoom covering ~30 km.
- Need-points: circle, color by `severity`, size by unmet.
- Trips: grey `O→D` lines.
- Suggestions: polyline `O→crates→N→D`, with a **Claim** button in the panel.
- Panel: `Starvation Index`, fill bars per point, mode switch, `Reset`.
- After every POST/claim: `fetch('/state')` → redraw.

## Concurrency

One uvicorn worker. Mutations (POST / claim / reset) and solver runs are guarded by a
`threading.Lock`. Writes go through SQLite transactions. Claim is atomic: the first one wins.

## Demo data (seed)

The seeding script creates a contrast scenario:

- ~6 need-points in a 30×30 km square, including a far one with `severity=5`,
- ~15 crates in trip corridors,
- ~5 trips crossing the center, budgets 5–15 min.

Goal: `nearest_fit` serves a nearby low-urgency point, while `fair_share` reaches the far
`severity=5` point.

## Principles (non-goals)

- No real routing and no API keys — distances are approximate (ADR 0002).
- No global VRP — the solver is local and incremental (ADR 0002).
- No persistent proposals and no re-planning — the "suggest → claim" model (ADR 0004, 0005).
- No QR, time windows, login, accounts, or payments.
- No ILP/OR-Tools and no unit tests (only a smoke test).

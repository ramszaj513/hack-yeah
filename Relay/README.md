# Relay

**Fair aid on trips that happen anyway.**

Relay is a hackathon app for humanitarian aid logistics in crises (flood, earthquake, evacuation). Instead of a central dispatcher and "yet another Uber", Relay fits donations into trips that residents are already making, and distributes aid by **fairness**, not distance.

> Design docs and MVP. Implementation plan: [`docs/PLAN.md`](docs/PLAN.md); architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); algorithm: [`docs/ALGORITHM.md`](docs/ALGORITHM.md).

---

## Problem

- During a crisis, resources (food, water, medicine) are scattered across residents' homes, not stored in a single warehouse.
- Responders have **need-points**, but they do not know who can deliver what, or when.
- The classic solution — a central dispatch optimizer — is expensive, brittle, and **unfair**: it sends aid wherever it is nearest and easiest, leaving distant and more urgent points without support.
- In a crisis, connectivity and power are often down, so the solution cannot rely on constant cloud connectivity.

## Solution — three pillars

1. **The crate as the unit.** We standardize donations into a single crate: one volume, one category. Donors pack crates, drivers have *N* free slots. This solves the capacity problem without modeling weight and volume.
2. **Trips instead of jobs.** A resident does not get a "ride" like on Uber — they declare a trip they are **going to make anyway** (`origin → destination`, **detour budget** in minutes, free slots). The system only adds crates along the way.
3. **Fairness instead of the shortest path.** Matching maximizes a **concave utility function** (proportional fairness), so no point — even a distant and urgent one — is skipped in favor of the nearest one.

## Actors

| Actor | Role |
|---|---|
| **Resident–Donor** | Reports crates (category + location). |
| **Resident–Driver** | Reports a trip they are making anyway, with a detour budget and a number of free slots. |
| **Administrator / responders** | Creates need-points with demand and urgency weight (severity). |

The same person can be both donor and driver — there are no separate accounts.

## How it works (flow)

1. Residents report **crates**, and drivers report **trips**.
2. An administrator creates **need-points** with demand and urgency.
3. After every event the system recomputes **suggested detours**: around each trip it draws a corridor (based on the detour budget) and checks which crates and need-points can be fitted in.
4. The driver sees a proposal: "take these crates and add +7 min, deliver to point X".
5. The driver **claims** the proposal; the crates leave the pool. No reaction = no reservation — the suggestion simply disappears on the next recomputation.

## Data model

| Concept | Description |
|---|---|
| **Crate** | The standard unit: one category, one volume, one location. |
| **Trip** | `origin`, `destination`, `detour_budget_min`, `slots_free`. |
| **Need-Point** | Location, demand per category, `severity` (1–5). |
| **Detour** | A set of crates picked up along a trip corridor and delivered to one need-point. |
| **Suggested Detour** | An ephemeral detour proposal before it is claimed. |
| **Starvation Index** | Metric: urgency-weighted shortage of unmet demand. |

## Algorithm

**Phase 1 — feasibility (corridor insertion).** The detour route is the polyline `[O, N, D]`; the corridor around it follows from the detour budget. We collect crates in the corridor and reject pairs that exceed the budget. Complexity `O(trips × points × crates)` — no global matrix and no VRP.

**Phase 2 — selection (proportional fairness).** We maximize:

```
U = Σₙ severityₙ · Σ_c log(1 + deliveredₙ,c)
```

The concave per-category utility means each additional crate is worth less, so the solver spreads itself out and cannot starve a distant point. Selection is greedy (marginal gain) and fast. Details and the full case catalog: [`docs/ALGORITHM.md`](docs/ALGORITHM.md).

## Demo — the heart of the presentation

A switch between two scorers on the same data:

- **Nearest-fit** (the "Uber" baseline): minimize detour → everything flows to the nearest point.
- **Fair-share** (ours): maximize concave utility → spread + urgency priority.

A map + a chart of point fill levels + the **Starvation Index**. We point out a point that gets 0% under nearest-fit but is served under fair-share — those are the 20 seconds that win the room.

## MVP scope

| We build | We skip |
|---|---|
| Leaflet + OpenStreetMap map (no API key) | Real routing / Distance Matrix |
| FastAPI + SQLite backend | Full global VRP |
| Corridor + greedy fairness solver | Time windows and ordering |
| Synthetic city seed | Persistent proposals and re-planning |
| "Suggest → claim" flow | QR, login, accounts, payments |
| Fairness panel + Starvation Index | Weight/volume model (crate = 1 slot) |

## Post-MVP additions

Implemented on top of the frozen MVP (see ADR 0006/0007):

- **Persistent detours with TTL** — suggestions get a `detour_id` and a validity countdown.
- **Checkpoints** — a claimed detour moves through `claimed → picked up → delivered`, with
  physical progress counters.
- **Mode preview** — `GET /state?mode=…` scores the same data with either algorithm without
  changing the stored mode; the **Compare** tab shows Fair-share vs Nearest-fit side by side.
- **Admin CRUD** — create, edit and delete crates, trips and need-points via the **Add** and
  **Manage** tabs (and `POST`/`PATCH`/`DELETE` endpoints).
- **Map filters** — toggle layers and filter crates by category / need-points by status.

## Tech stack

- **Backend:** FastAPI (Python) + SQLite.
- **Solver:** pure Python (no cloud dependencies).
- **Frontend:** a single page with a map (Leaflet + OSM from CDN), no build step.
- **Data:** seed at startup. The demo never depends on data entered live.

## Repository structure

```
Relay/
├─ app/                       # FastAPI + SQLite backend
│  ├─ config.py               # R, LAT0, SPEED_KMH, DB_PATH, MODES, categories
│  ├─ db.py                   # schema, contrast seed, transactions, Lock
│  ├─ geometry.py             # xy(), dist(), seg_dist(), polyline_dist()
│  ├─ solver.py               # phase 1 (corridor) + phase 2 (greedy fairness)
│  └─ main.py                 # API endpoints + frontend mounting
├─ web/                       # frontend: Leaflet from CDN, no build step
│  ├─ index.html
│  ├─ app.js
│  └─ style.css
├─ tests/
│  └─ test_smoke.py           # end-to-end smoke test (pytest)
├─ pyproject.toml             # uv project (dependencies + pytest config)
├─ requirements.txt           # the same for `pip` (optional)
├─ run.sh                     # run the whole app locally
├─ README.md                  # this file
└─ docs/
   ├─ PLAN.md                 # master implementation plan (2 h)
   ├─ MANUAL.md               # user manual (how to use the app)
   ├─ ARCHITECTURE.md         # components, data model, API, seed
   ├─ ALGORITHM.md            # solver, metrics, case catalog
   ├─ IMPLEMENTATION.md       # implementation steps and smoke test
   ├─ GLOSSARY.md             # domain language
   └─ adr/                    # design decisions
```

## Quick start

[`uv`](https://docs.astral.sh/uv/) is required (it manages Python and dependencies).

```bash
cd Relay
./run.sh                        # uv sync + uvicorn (auto-reload)
# browser: http://127.0.0.1:8000
```

Options: `PORT=9000 ./run.sh`, `NO_RELOAD=1 ./run.sh`.
Tests: `uv run pytest`. Reset data: `POST /reset` or the button in the panel.

> **How do I use the app?** See [`docs/MANUAL.md`](docs/MANUAL.md) — or click **?**
> in the top-right corner of the panel. On your first visit the guide opens by itself.

## Status

Design docs complete, MVP implemented per [`docs/PLAN.md`](docs/PLAN.md), plus the
post-MVP additions above (ADR 0006/0007). FastAPI + SQLite backend, two-phase solver,
persistent detours with TTL and checkpoints, admin CRUD and map filters, a tabbed
Leaflet frontend (Demo / Add / Manage / Compare), a contrast-scenario seed, and an
end-to-end smoke test. Design rationale: [`docs/adr/`](docs/adr/).

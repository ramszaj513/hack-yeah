# Ephemeral suggestions recomputed on demand instead of persistent proposals

The solver does not store proposals in the database: on every `GET /state` (that is, after every event) it recomputes, on the fly, a disjoint set of **suggested detours** from the Residual Pool. A claimed detour (Claim) is persistent, but the suggestion itself exists only as a computation result. We considered storing proposals in a `proposals` table and the classic model with assignment and re-solve on every event (ADR 0003/0004). We rejected persistent proposals because they require retraction, notifications, and conflict resolution between stale rows. Ephemeral suggestions are always consistent with the pool, and their recomputation cost is negligible at demo scale.

## Consequences

- "Auto-run after an event" is implemented by `GET /state`; there is no separate `/optimize` endpoint.
- A suggestion has no persistent identifier — `POST /claim` sends its contents (`trip_id`, `need_id`, `crate_ids`) and validates them on the fly; stale → `409`.
- Suggestions are mutually disjoint within one computation, so claiming any subset causes no conflicts.
- No push notifications and no retractions — the driver sees the current state on refresh.
- At larger scale one would need caching/incrementality; out of MVP scope.

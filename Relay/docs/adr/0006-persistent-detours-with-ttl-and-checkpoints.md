# Persistent detours with TTL and checkpoints

We extend the "suggest → claim" model along two axes requested after the MVP: suggestions
are now **persistent** with a **time-to-live (TTL)**, and a claimed detour has an operational
**lifecycle** with checkpoints.

The solver still computes suggestions on demand in `GET /state`, but instead of returning
purely ephemeral objects, each suggestion is stored as a row in a new `detours` table with a
`detour_id`, `created_at`, `expires_at` and `status`. Suggestions that are identical to a
still-valid stored one (same trip, need-point and crate set) keep their id and expiry, so the
countdown is stable across requests; new ones are inserted and stale ones are removed. This
supersedes ADR 0005 (ephemeral suggestions) while keeping its core property: a suggestion
reserves nothing until it is claimed.

After a claim, the detour moves through checkpoints:

```
suggested --claim--> claimed --pickup--> picked_up --deliver--> delivered
```

Crates follow the same lifecycle (`available → claimed → picked_up → delivered`). Demand
(`requirements.delivered`) is still committed at claim time, so the solver and metrics remain
coherent; the checkpoints additionally expose the *physical* progress (crates in transit vs.
actually delivered) without changing demand accounting.

## Consequences

- The UI can show a validity countdown, and a claim can be traced by a stable `detour_id`.
- Claiming by `detour_id` validates expiry and status; an expired suggestion → `409`.
- The original contents-based claim (`trip_id`, `need_id`, `crate_ids`) is kept for
  compatibility and creates a `claimed` detour on the fly.
- A small amount of housekeeping is needed: expired suggestions are pruned on the next
  `GET /state`, and deleting an available crate/trip also drops suggested detours that
  referenced it.
- At larger scale one would need a background sweeper and indexing; out of scope here.

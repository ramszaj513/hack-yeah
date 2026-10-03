# Suggest and claim instead of continuous re-planning and unpinned proposals

The solver produces **suggested detours** that the driver explicitly **claims**. Crates and the slot leave the pool only after the claim. We reject both the old model of "unpinned proposals with an immediate re-solve on every event" (old ADR 0003) and full up-front assignment. Continuous re-planning caused races, "dead" notifications, and solver storms; full assignment blocked resources for slow responders. The "suggest → claim" model is simpler, predictable, and matches real trips, where the driver makes the decision.

## Consequences

- There is no need for notification retraction or debounce — a suggested detour simply expires without a claim.
- Between generation and claim, two drivers may see the same proposal; we solve this with an atomic server-side claim (first one wins).
- There is no continuous optimal "right now" plan — we deliberately put simplicity and clarity above global optimality.
- A suggestion validity timeout could be added later, but it is not required for the MVP.

## Addendum

ADR 0005 makes the realization precise: suggestions are ephemeral and recomputed on every
`GET /state` (that is, after every event). This is not "continuous re-planning" in the sense
rejected above — there are no persistent proposals, notifications, or retractions; the solver
simply returns a fresh, disjoint set of suggestions over the current pool.

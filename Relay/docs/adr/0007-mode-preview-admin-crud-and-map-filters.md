# Mode preview, admin CRUD and map filters

The MVP exposed a single global mode and no way to manage resources from the UI. We add three
capabilities that make the tool usable as a real admin console without touching the solver or
the locked MVP decisions:

1. **Mode preview.** `GET /state?mode=<mode>` computes suggestions and metrics for the
   requested scorer *without persisting them and without changing the stored mode*. This lets
   the frontend compare Fair-share and Nearest-fit side by side on the same data — the demo
   that previously required flipping the global switch back and forth. An unknown mode →
   `400`.

2. **Admin CRUD.** `PATCH`/`DELETE` for crates, trips and need-points. Available crates and
   trips can be edited or deleted; a claimed/used resource cannot (`409`), which protects the
   integrity of in-flight detours. Editing a need-point can change its name, urgency,
   requirements and status; when demand shrinks below what was already delivered, the
   delivered count is clamped. Deleting a need-point cascades to its requirements and detours.

3. **Map filters and a tabbed UI.** The admin panel is split into **Demo / Add / Manage /
   Compare** tabs. Layer checkboxes and category/status filters live on the map; the Add tab
   posts to the existing create endpoints.

We deliberately keep the added surface small: no authentication, no optimistic locking, no
bulk operations. Those belong to a real deployment, not this MVP.

## Consequences

- The same dataset can be scored by both algorithms in one request pair, so the fairness
  contrast is immediate and side-by-side.
- Preview requests do not create persistent detours; only the stored mode does.
- Resource deletion cleans up stale suggested detours that referenced the removed resource.
- Editing is restricted to available resources, so the "first claim wins" invariant holds.

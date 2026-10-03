# Relay — user manual

A guide to the app: what it shows, what each element means, and how to run the demo.
A shorter version is also available inside the app under the **?** button in the
top-right corner of the panel.

---

## 1. What this is (in 30 seconds)

In a crisis, donations are scattered across residents' homes, and responders do not know
who can deliver what, or when. Relay **fits aid into trips that are happening anyway** —
someone is driving from point A to B, and we add crates along the way.

A classic optimizer sends aid wherever it is **nearest and easiest** — distant, urgent
points are left without support. Relay distributes aid **fairly**: no point, no matter how
far or urgent, is starved in favor of the nearest one.

The whole idea lives in one switch: **Nearest-fit** (how "yet another Uber" works) vs
**Fair-share** (how Relay works). Flip it, or open the **Compare** tab and see both side by
side on the same data.

---

## 2. Glossary

| Term | Meaning |
|---|---|
| **Crate** | The standard donation unit: one category, one volume, one location. It takes 1 slot. |
| **Trip** | A declaration: "I'm driving from `origin` to `destination`". It has a **detour budget** and **free slots**. |
| **Detour budget** | How many minutes the driver is willing to add (5–15 min). It sets how wide the corridor is. |
| **Need-point** | A place with demand per category and an **urgency** (1–5). |
| **Requirement** | How much of a category a point still needs. The point closes when unmet reaches 0. |
| **Urgency (severity)** | Weight 1–5. It drives fairness: higher urgency = stronger priority. |
| **Corridor** | The area around the route `O → point → D`. Only crates in the corridor enter a detour. |
| **Suggested detour** | A proposal: "take these crates and add +X min, deliver to point Y". It has a **limited validity** and reserves nothing. |
| **Claim** | Clicking "Claim". The crates become `claimed`, the trip is used up, and the detour becomes active. |
| **Checkpoint** | The driver's confirmation: **Picked up**, then **Delivered**. |
| **Active detour** | A claimed detour moving through `claimed → picked up → delivered`. |
| **Starvation Index** | A measure of unmet demand weighted by urgency. Lower is better. |
| **Fill** | The percentage of a point's demand that is satisfied. |

---

## 3. The map — what is what

| Map symbol | Meaning |
|---|---|
| **Grey dashed line** | A trip (`O → D`) that is happening anyway. |
| **Small colored dot** | A crate. Color = category. Crates that are claimed/delivered are faded and dashed. |
| **Large colored circle** | A need-point. **Color = urgency** (green → red). **Size = unmet demand**. |
| **Orange dashed line** | A suggested detour: `O → crates → need-point → D`. |
| **Colored solid line** | An active detour. Color shows its status (claimed = blue, picked up = purple, delivered = green). |
| **Numbered orange marker** | The suggestion number — it matches the panel list. |

The **Layers** box (top-left) toggles trips, crates, need-points, suggestions and active
detours, and filters crates by category and need-points by status. The legend (top-right)
explains the symbols. Click any object for details.

---

## 4. The panel — tabs

The panel has four tabs:

- **Demo** — mode switch, Starvation Index, fill bars, suggested detours, active detours and
  the Reset button.
- **Add** — forms to report crates, trips and need-points.
- **Manage** — edit or delete resources and filter by name/id.
- **Compare** — run Fair-share and Nearest-fit on the same data and see the difference.

### Demo tab details

1. **Matching mode** — Fair-share (ours) vs Nearest-fit (the "Uber" baseline).
2. **Starvation Index** — `now → after suggestions`. The first number is the real state; the
   second is the projection if every visible suggestion were claimed. Below it: counters
   (crates in transit, physically delivered, active detours) and a fill bar per point.
3. **Suggested detours** — each card shows the detour time, trip, target point, utility gain,
   crate list, a **validity countdown**, and a **Claim** button.
4. **Active detours** — claimed detours with **Picked up** / **Delivered** checkpoint buttons.

The **?** button (top-right) opens the short in-app guide.

---

## 5. How to use it — step by step

1. Open `http://127.0.0.1:8000` (`./run.sh`) and wait for the map to render.
2. On the **Demo** tab, pick **Fair-share**. A suggestion appears for the distant point
   "Rembertow East" (urgency 5).
3. Click **Claim** on a suggestion. The crates become `claimed` and the detour moves to the
   **Active detours** section.
4. Click **Picked up**, then **Delivered**. The crate statuses change on the map, and the
   "delivered" counter rises.
5. Use **Reset to seed** to return to the starting point.
6. Switch to **Nearest-fit** and compare — or use the **Compare** tab (below).

> **Validity:** a suggestion is valid for a limited time (countdown on the card). If it
> expires before you claim it, it disappears and the system recomputes fresh ones. Nothing is
> reserved until you click **Claim**, and the first claim wins.

---

## 6. The demo script (the 20 seconds that land)

1. Open the **Compare** tab and click **Run comparison**.
2. Look at the far-away point **"Rembertow East" (urgency 5)**: Fair-share fills it, Nearest-fit
   leaves it at 0%. Green rows are the fairness win.
3. The header shows the **Starvation Index** for both modes — much lower for Fair-share.
4. Back on the **Demo** tab with Fair-share, **Claim** the first detour and run the checkpoints.

That is the project's thesis: fairness instead of the shortest path.

---

## 7. How to read the metrics

- **Starvation Index** = `Σ severity · (unmet / capacity) / Σ severity · 100%`.
  `0%` = nobody is starving, `100%` = nothing arrived. Lower is better.
- **`now → after suggestions`** — base state vs. projection including all suggestions.
- **Counters** — *in transit* = crates claimed or picked up; *delivered* = crates physically
  delivered (checkpoint reached); *active detours* = claimed/picked-up/delivered detours.
- **Fill bars** — solid = current state, translucent = gain from suggestions.
- **Utility gain** — the objective value of a proposal; higher is more valuable for fairness.

---

## 8. Fair-share vs Nearest-fit — what is the difference

The Fair-share objective:

```
U = Σₙ severityₙ · Σ_c log(1 + deliveredₙ,c)
```

Every additional crate for an already-served point is worth **less and less**
(diminishing returns), so the solver spreads itself out and cannot systematically starve a
distant, urgent point. Nearest-fit minimizes detour alone, so it quickly uses up trips on the
cheapest deliveries. Both modes consider the same candidates; only the selection differs.

---

## 9. Adding, managing and comparing

- **Add tab** — report a crate (category + location), a trip (from, to, detour budget, free
  slots) or a need-point (name, urgency, demand per category). Invalid input (unknown
  category, out-of-range coordinates, non-positive budget/slots) is rejected with `422`.
- **Manage tab** — filter by name/id, then **Edit** or **Delete**. Only *available* crates and
  trips can be changed or removed; a claimed/used resource returns `409`. Need-points can be
  edited at any time, including their demand and status.
- **Compare tab** — computes both scorers without changing the stored mode, and lists each
  point's projected fill under each mode plus the difference.

---

## 10. API

Categories: `food`, `water`, `meds`, `hygiene`, `other`. Interactive docs: `/docs`.

```bash
# Create
curl -X POST http://127.0.0.1:8000/crates -H 'Content-Type: application/json' \
  -d '{"category":"food","lat":52.23,"lon":21.01}'
curl -X POST http://127.0.0.1:8000/trips -H 'Content-Type: application/json' \
  -d '{"olat":52.20,"olon":21.00,"dlat":52.27,"dlon":21.05,"detour_budget_min":10,"slots_free":3}'
curl -X POST http://127.0.0.1:8000/need-points -H 'Content-Type: application/json' \
  -d '{"name":"New point","lat":52.25,"lon":21.03,"severity":4,"requirements":{"water":3,"food":2}}'

# Edit / delete (only available crates and trips)
curl -X PATCH http://127.0.0.1:8000/trips/t-to-rembertow -H 'Content-Type: application/json' -d '{"detour_budget_min":12}'
curl -X PATCH http://127.0.0.1:8000/need-points/n-wola -H 'Content-Type: application/json' -d '{"severity":5,"requirements":{"meds":4}}'
curl -X DELETE http://127.0.0.1:8000/crates/c01

# State: normal, or preview another scorer
curl http://127.0.0.1:8000/state
curl 'http://127.0.0.1:8000/state?mode=nearest_fit'

# Claim a suggestion, then run checkpoints
curl -X POST http://127.0.0.1:8000/claim -H 'Content-Type: application/json' \
  -d '{"detour_id":"detour-XXXXXXXX"}'
curl -X POST http://127.0.0.1:8000/detours/detour-XXXXXXXX/pickup
curl -X POST http://127.0.0.1:8000/detours/detour-XXXXXXXX/deliver

# Mode / reset / config
curl -X POST http://127.0.0.1:8000/mode -H 'Content-Type: application/json' -d '{"mode":"nearest_fit"}'
curl -X POST http://127.0.0.1:8000/reset
curl http://127.0.0.1:8000/config

# Liveness probe (no database access)
curl http://127.0.0.1:8000/health
```

After adding data, refresh the page (or perform any action in the panel) — `GET /state`
recomputes the suggestions from scratch.

---

## 11. FAQ and troubleshooting

**I don't see any suggestions.**
No suggestions is correct when there is not at the same time: an available crate, a free trip,
and an open need-point. Check that crates have a needed category and lie in the trip corridor
(close to the `O → point → D` polyline), and that the detour budget is sufficient.

**My suggestion disappeared.**
Suggestions have a limited validity (countdown on the card). When one expires, the system
recomputes a fresh set on the next refresh — this is expected, and a new suggestion usually
appears if resources are still available.

**I click "Claim" but get an error.**
If the state changed between generation and your click (someone else claimed the resources, or
you clicked twice, or the suggestion expired), the server returns a conflict. Refresh and try
again; the first claim wins.

**Can I undo a claim?**
No. Once claimed, the crates are committed and the trip is used. You can still delete the
*need-point* itself, which also removes its detours.

**Why can't I edit/delete a crate or trip?**
Only available ones can be changed. A crate that is claimed/picked up/delivered, or a used
trip, is protected to keep in-flight detours consistent.

**I switched mode but the "now" metric didn't change.**
That is normal: "now" is the base state. The comparison shows up in "after suggestions", in
the suggestions themselves, and in the Compare tab. Claim a suggestion to change the permanent
state.

**I want to start from scratch.**
Click **Reset to seed** in the panel, or `curl -X POST http://127.0.0.1:8000/reset`.

**Change the port?**
`PORT=9000 ./run.sh`. Without auto-reload: `NO_RELOAD=1 ./run.sh`.

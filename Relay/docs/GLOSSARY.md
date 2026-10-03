# Relay — domain glossary

The project's shared language. Technical terms stay in English so they match the code and API.

## Actors

**Resident (Citizen)**
A registered person who can report **crates**, **trips**, or both. There are no separate
"donor" and "driver" accounts.
_Avoid_: Donor, User (as an account type)

**Administrator (Admin)**
A responder/operator who creates **need-points** and sets their urgency.
_Avoid_: Dispatcher, Operator

## Delivery

**Crate**
The standard donation unit: one **category**, one volume, the donor's location. A driver
carries crates that each take one **slot**. A QR code is a post-MVP extension — in the MVP a
crate only has a text `id`.
_Avoid_: Resource, Item, Donation, Package

**Category**
One of the fixed values (food, water, meds, hygiene, other), shared by crates and
need-point demand.
_Avoid_: Type

**Trip**
A resident's declaration that they are driving `origin → destination`, with a **detour
budget** (how many minutes they are willing to add) and a number of **free slots**. It
replaces the former "Transport Offer". In the MVP the time window is skipped — only geometry
and the detour budget matter.
_Avoid_: Transport Offer, Ride, Job

**Detour Budget**
The maximum extra time a driver agrees to spend helping, expressed in minutes. It determines
the allowed detour cost and the corridor width.
_Avoid_: Extra time, Limit

**Need-Point**
A location created by the administrator with **demand** (per category) and **urgency**.
Open until the demand is satisfied.
_Avoid_: Incident, Site, Demand

**Requirement**
The quantities per category that a need-point still needs (`remaining = needed − delivered`).
It shrinks as deliveries arrive; the point closes when everything reaches zero.
_Avoid_: Quota, Need

**Urgency (Severity)**
A weight 1–5 assigned to a need-point. It drives fairness: concave utility rewards serving
points with higher urgency.
_Avoid_: Priority (as a separate entity)

## Matching

**Run**
A single solver computation over the pool, producing zero or more **suggested detours**. In
the MVP it happens on every `GET /state` (after every event).
_Avoid_: Solve, Batch, Cycle

**Residual Pool**
The crates and trips not yet assigned to any claimed detour. Only this pool is visible to a
run.
_Avoid_: Backlog, Queue

**Detour**
Crates collected along one trip's corridor and delivered to one need-point. It exists as a
**suggested detour** before the driver claims it.
_Avoid_: Route, Trip, Job

**Suggested Detour**
An ephemeral detour proposal before it is claimed. It is not stored in the database; it does
not reserve resources and disappears on the next recomputation (see ADR 0005). Suggestions
within one run are mutually disjoint.
_Avoid_: Proposal, Draft

**Claim**
Explicit acceptance of a suggested detour by the driver. An atomic transaction: crates become
`claimed`, the trip becomes `used`, and demand decreases.
_Avoid_: Accept, Assignment

## Metrics and UX

**Corridor**
The area around the polyline `[O, N, D]` for a trip–point pair, with a width derived from the
detour budget. Only crates inside the corridor are considered.
_Avoid_: Buffer, Zone

**Starvation Index**
The urgency-weighted indicator of unmet demand:
`Σ_n severity_n·(unmet_n/capacity_n) / Σ_n severity_n × 100%`. The main fairness metric in the
demo.
_Avoid_: Deficit, Shortage

**Fill**
The percentage of a need-point's demand that is satisfied: `100% · (1 − unmet/capacity)`.
_Avoid_: Completion

**Checkpoint**
A manual confirmation by the driver (picked up / delivered). Optional and out of MVP scope.
_Avoid_: Status update

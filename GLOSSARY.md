# Disaster Relief Logistics

Coordinates citizen-donated supplies and citizen-driven transport to government-designated relief locations during an emergency response.

## Language

### Actors

**Citizen**:
A registered person who may declare Resources, make a Transport Offer, or both — there is no separate "donor" or "driver" account type.
_Avoid_: Donor, User, Driver (as an account type)

**Driver**:
The role a Citizen plays once assigned to a Route. Not a distinct account — any Citizen with an active Transport Offer can become one.
_Avoid_: Volunteer driver

**Admin**:
A government operator who creates Need-Points and triggers manual optimization Runs.
_Avoid_: Operator, Dispatcher

### Supply & Demand

**Resource**:
A quantity of one Category that a Citizen has available at their home for pickup.
_Avoid_: Supply, Item, Donation

**Category**:
One entry in the fixed vocabulary (food, water, medicine, hygiene, other) that both a Resource and a Need-Point's Requirement are expressed in. The matching vocabulary is what lets a Requirement be satisfied by a Resource at all.
_Avoid_: Type

**Transport Offer**:
A Citizen's declaration of the time window(s) during which they're willing to drive. Carries no stated capacity — a Route's size is bounded by this time window, not by what the car can hold.
_Avoid_: Driver profile, Vehicle

**Need-Point**:
An Admin-created location with a Requirement: specific Categories and quantities still needed there. Stays open, and can be partially satisfied across multiple Runs, until every Category's quantity is met.
_Avoid_: Incident, Site, Demand, Drop point

**Requirement**:
The per-Category quantities a Need-Point still needs. Shrinks as Routes deliver against it; the Need-Point closes when every Category reaches zero.
_Avoid_: Quota, Need

### Routing & Matching

**Run**:
One execution of the solver over the Residual Pool, producing zero or more new Proposals. Triggered by any pool-changing event — a new Resource, Transport Offer, or Need-Point, a Decline, or a Timeout — or manually by an Admin.
_Avoid_: Optimization cycle, Solve, Batch

**Residual Pool**:
The Resources, Transport Offers, and Requirement quantities not currently held by a Proposal or an accepted Route. Only this pool is visated by a Run — an accepted Route is never revisited.
_Avoid_: Unassigned queue, Backlog

**Route**:
A multi-pickup, single-drop plan: one Driver visiting one or more donor homes, then delivering everything to one Need-Point. Exists as a Proposal before the Driver accepts it.
_Avoid_: Assignment, Trip, Job

**Proposal**:
A Route in the window between being computed and being accepted. A Proposal does not reserve its Resources or Driver against the Residual Pool — a later Run may hand the same Route to a different Driver before the original one responds.
_Avoid_: Pending assignment, Offer, Draft

**Timeout**:
The admin-configurable duration after which an unanswered Proposal auto-releases its Resources and Driver back to the Residual Pool.
_Avoid_: Expiry

**Decline**:
A Driver's explicit rejection of a Proposal, releasing its Resources and Driver back to the Residual Pool immediately rather than waiting for the Timeout.

### Driver Experience

**Checkpoint**:
A manual status tap by the Driver on an accepted Route (Picked up, Delivered). The only ground-truth signal of progress — there is no continuous location tracking.
_Avoid_: Status update, Milestone

**Estimated Position**:
A point on the admin map interpolated from elapsed time against the Route's planned duration, shown between Checkpoints. An extrapolation, not a measured location.
_Avoid_: Live location, Current position

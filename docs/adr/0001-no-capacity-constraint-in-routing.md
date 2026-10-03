# No vehicle capacity constraint in routing

A Transport Offer carries no stated cargo capacity, and the solver has no capacity dimension — a Route's size is bounded only by the Driver's available time window and travel time. We considered modeling capacity as a single scalar ("fits N standard units") or as true multi-dimensional weight+volume, but both require collecting a new data point from every Citizen and add a real constraint dimension to the solver. For hackathon scope we dropped it entirely, accepting that a Route can be computed which no real car could physically carry.

## Consequences

Because Transport Offers never collect a capacity field, this can't be patched in later without asking every already-registered Citizen to retroactively supply one.

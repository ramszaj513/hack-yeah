# Crate as an atomic unit instead of an abstract quantity

We model donations as **crates**: unit volume, one category, a QR code, the donor's location. The `Resource` of the original model was an abstract quantity with no volume, and `Transport Offer` did not declare capacity — as a result the solver could plan a route that no car could physically carry. Instead of adding a weight/volume dimension, we considered two alternatives: a scalar "holds N standard units" and a true weight+volume model. Both require collecting new data from every resident and add a real dimension to the solver. We chose a single standard crate because it reduces capacity to slot counting and gives a physical, scannable artifact for the demo.

## Consequences

- Capacity = the number of a trip's **free slots**; the problem of unpredictable capacity disappears.
- Standardization limits unusual donations — everything must fit within one crate volume.
- A crate carries no weight, so in theory a driver could receive a load heavier than is comfortable; we accept this as a deliberate hackathon-scale trade-off.
- A QR code opens the door to later supply-chain verification (proof-of-impact) without changing the model.

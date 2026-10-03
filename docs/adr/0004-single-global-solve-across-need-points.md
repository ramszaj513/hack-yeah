# One global solve across all open Need-Points per Run

Each Run solves across every open Need-Point and the entire Residual Pool at once, rather than running an independent solve per Need-Point. We considered per-Need-Point solves as the simpler, more obviously-scalable option, but rejected it because independent solves can't see each other's choices within the same Run — two Need-Points could both claim the same nearby Driver, or a Driver could be sent to a farther Need-Point when a closer one needed exactly the same Resources.

## Consequences

A single large Run has to model every open Need-Point and the full Residual Pool together, so solver cost grows with total open demand rather than per-incident demand.

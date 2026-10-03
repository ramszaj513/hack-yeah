# Proposals stay reassignable until accepted; every event triggers an immediate re-run

A Route only locks when its Driver taps Accept. Before that, it's a Proposal, and it does *not* reserve its Resources or Driver against the Residual Pool — a Run triggered by any later event (a new Resource, Transport Offer, Need-Point, Decline, or Timeout) is free to hand the same Route to a different, better-fit Driver while the original Proposal is still unanswered. Runs fire on every such event, with no debounce window. We considered the opposite on both axes — pinning a Proposal as soon as it's sent, and batching events into a fixed interval (e.g. every 60s) — specifically to avoid a Driver's notification going stale out from under them and to avoid solver-storm risk. We rejected both: pinning would let a slow-to-respond Driver block a Route that a faster Driver could serve sooner, and in an emergency-response context we weighted "the globally best plan right now" above "never surprise an individual Driver."

## Consequences

A Driver's Proposal notification can go silently dead with no retraction push if it's reassigned before they respond (see Proposal, GLOSSARY.md) — this is deliberate, not an oversight, and shouldn't be "fixed" by adding pinning without revisiting this decision.

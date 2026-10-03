# Straight-line distance instead of a real routing API

The solver's distance/time matrix uses straight-line (Haversine) distance between points rather than real road travel time. We considered the Google Distance Matrix API and a self-hosted OSRM instance, both of which would give road-accurate times and a stronger "built on real routing tech" story. We chose Haversine specifically to remove any live external API or Cloud billing dependency that could fail silently during judging, at the cost of route quality and ETA accuracy.

## Consequences

Estimated Position (interpolated driver progress, see GLOSSARY.md) is calibrated against straight-line distances, so it will drift further from reality in areas with indirect roads.

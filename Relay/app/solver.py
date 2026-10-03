"""Two-phase solver: candidates (corridor) + greedy selection (fairness).

Description: ``docs/ALGORITHM.md``; decisions: ADR 0002 (corridor), 0003 (fairness),
0005 (ephemeral suggestions).
"""

from __future__ import annotations

import math

from .config import EPS, FAIR_SHARE, NEAREST_FIT, SPEED_KM_PER_MIN
from .geometry import dist, polyline_dist


def _remaining(need: dict) -> dict[str, int]:
    return {
        cat: max(0, r["needed"] - r["delivered"])
        for cat, r in need["requirements"].items()
    }


def build_candidate(
    trip: dict,
    need: dict,
    crates: list[dict],
    delivered: dict[tuple[str, str], int],
) -> dict | None:
    """Phase 1: build the best candidate for a (trip, need-point) pair.

    Returns ``None`` if the pair is infeasible (budget / no crates).
    """
    o = (trip["olat"], trip["olon"])
    d = (trip["dlat"], trip["dlon"])
    n = (need["lat"], need["lon"])

    allowance_km = trip["detour_budget_min"] * SPEED_KM_PER_MIN
    detour_km = dist(o, n) + dist(n, d) - dist(o, d)
    if detour_km > allowance_km + EPS:
        return None
    detour_km = max(0.0, detour_km)

    rem = {c: r for c, r in _remaining(need).items() if r > 0}
    if not rem:
        return None

    corridor_half_km = allowance_km / 2.0
    route = [o, n, d]

    pool: list[tuple[float, dict]] = []
    for cr in crates:
        if cr.get("status", "available") != "available":
            continue
        if cr["category"] not in rem:
            continue
        d_cr = polyline_dist((cr["lat"], cr["lon"]), route)
        if d_cr <= corridor_half_km + EPS:
            pool.append((d_cr, cr))
    if not pool:
        return None

    s = min(int(trip["slots_free"]), sum(rem.values()))
    severity = need["severity"]
    sim: dict[str, int] = {
        c: delivered.get((need["id"], c), 0) for c in need["requirements"]
    }
    rem_sim = dict(rem)
    chosen: list[dict] = []
    chosen_ids: set[str] = set()

    def nearest_crate(cat: str) -> tuple[float, dict] | None:
        best: tuple[tuple[float, str], float, dict] | None = None
        for d_cr, cr in pool:
            if cr["id"] in chosen_ids or cr["category"] != cat:
                continue
            key = (d_cr, cr["id"])
            if best is None or key < best[0]:
                best = (key, d_cr, cr)
        if best is None:
            return None
        return best[1], best[2]

    for _ in range(s):
        best_cat: str | None = None
        best_key: tuple[float, str] | None = None
        for cat, left in rem_sim.items():
            if left <= 0:
                continue
            if nearest_crate(cat) is None:
                continue
            d0 = sim.get(cat, 0)
            # delta(c) = severity * [log(1+delivered_c+1) - log(1+delivered_c)]
            delta = severity * (math.log(1 + d0 + 1) - math.log(1 + d0))
            key = (-delta, cat)
            if best_key is None or key < best_key:
                best_key = key
                best_cat = cat
        if best_cat is None:
            break
        picked = nearest_crate(best_cat)
        assert picked is not None
        _, crate = picked
        chosen.append(crate)
        chosen_ids.add(crate["id"])
        sim[best_cat] = sim.get(best_cat, 0) + 1
        rem_sim[best_cat] -= 1

    if not chosen:
        return None

    utility_gain = 0.0
    for cat in need["requirements"]:
        d0 = delivered.get((need["id"], cat), 0)
        utility_gain += severity * (math.log(1 + sim.get(cat, d0)) - math.log(1 + d0))

    chosen.sort(key=lambda cr: dist(o, (cr["lat"], cr["lon"])))

    route = [list(o)]
    for cr in chosen:
        route.append([cr["lat"], cr["lon"]])
    route.append(list(n))
    route.append(list(d))

    return {
        "trip_id": trip["id"],
        "need_id": need["id"],
        "crate_ids": [cr["id"] for cr in chosen],
        "crates": chosen,
        "trip": trip,
        "need": need,
        "route": route,
        "extra_minutes": detour_km / SPEED_KM_PER_MIN,
        "utility_gain": utility_gain,
    }


def _candidate_key(mode: str):
    if mode == NEAREST_FIT:
        return lambda c: (
            c["extra_minutes"],
            -c["utility_gain"],
            c["trip_id"],
            c["need_id"],
        )
    # fair_share (default)
    return lambda c: (
        -c["utility_gain"],
        c["extra_minutes"],
        c["trip_id"],
        c["need_id"],
    )


def solve(
    trips: list[dict],
    need_points: list[dict],
    crates: list[dict],
    delivered: dict[tuple[str, str], int],
    mode: str = FAIR_SHARE,
) -> list[dict]:
    """Phase 2: greedy selection of mutually disjoint suggestions."""
    key = _candidate_key(mode)

    available_trips = [t for t in trips if t.get("status", "available") == "available"]
    open_needs = [n for n in need_points if n.get("status", "open") == "open"]

    used_trips: set[str] = set()
    claimed_crates: set[str] = set()
    closed_needs: set[str] = set()
    sim: dict[tuple[str, str], int] = dict(delivered)
    suggestions: list[dict] = []

    while True:
        live_crates = [
            cr
            for cr in crates
            if cr["id"] not in claimed_crates
            and cr.get("status", "available") == "available"
        ]
        candidates: list[dict] = []
        for t in available_trips:
            if t["id"] in used_trips:
                continue
            for n in open_needs:
                if n["id"] in closed_needs:
                    continue
                cand = build_candidate(t, n, live_crates, sim)
                if cand is not None:
                    candidates.append(cand)
        if not candidates:
            break

        best = min(candidates, key=key)
        suggestions.append(best)
        used_trips.add(best["trip_id"])
        for cid in best["crate_ids"]:
            claimed_crates.add(cid)
        for cr in best["crates"]:
            k = (best["need_id"], cr["category"])
            sim[k] = sim.get(k, 0) + 1

        need = next(n for n in open_needs if n["id"] == best["need_id"])
        if all(
            sim.get((need["id"], cat), 0) >= r["needed"]
            for cat, r in need["requirements"].items()
        ):
            closed_needs.add(need["id"])

    return suggestions


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _apply_suggestions(
    need_points: list[dict], suggestions: list[dict]
) -> dict[tuple[str, str], int]:
    proj: dict[tuple[str, str], int] = {}
    for n in need_points:
        for cat, r in n["requirements"].items():
            proj[(n["id"], cat)] = r["delivered"]
    for s in suggestions:
        for cr in s["crates"]:
            k = (s["need_id"], cr["category"])
            proj[k] = proj.get(k, 0) + 1
    return proj


def _scalar_metrics(
    need_points: list[dict], delivered: dict[tuple[str, str], int]
) -> tuple[float, dict[str, dict]]:
    total_sev = 0
    weighted = 0.0
    per_point: dict[str, dict] = {}
    for n in need_points:
        capacity = sum(r["needed"] for r in n["requirements"].values())
        if capacity <= 0:
            continue
        unmet = sum(
            max(0, r["needed"] - delivered.get((n["id"], cat), r["delivered"]))
            for cat, r in n["requirements"].items()
        )
        unmet = max(0, min(capacity, unmet))
        fill = 100.0 * (1.0 - unmet / capacity)
        total_sev += n["severity"]
        weighted += n["severity"] * (unmet / capacity)
        per_point[n["id"]] = {
            "capacity": capacity,
            "unmet": unmet,
            "fill_pct": round(fill, 1),
        }
    starve = 100.0 * weighted / total_sev if total_sev else 0.0
    return round(starve, 1), per_point


def metrics(need_points: list[dict], suggestions: list[dict]) -> dict:
    """Starvation Index and fill per need-point (actual state + suggestion projection)."""
    actual: dict[tuple[str, str], int] = {}
    for n in need_points:
        for cat, r in n["requirements"].items():
            actual[(n["id"], cat)] = r["delivered"]

    projected = _apply_suggestions(need_points, suggestions)

    starve, per_actual = _scalar_metrics(need_points, actual)
    proj_starve, per_proj = _scalar_metrics(need_points, projected)

    points = []
    for n in need_points:
        capacity = sum(r["needed"] for r in n["requirements"].values())
        if capacity <= 0:
            continue
        a = per_actual.get(
            n["id"], {"capacity": capacity, "unmet": 0, "fill_pct": 100.0}
        )
        p = per_proj.get(
            n["id"], {"capacity": capacity, "unmet": 0, "fill_pct": 100.0}
        )
        points.append(
            {
                "need_id": n["id"],
                "name": n["name"],
                "severity": n["severity"],
                "status": n["status"],
                "capacity": capacity,
                "delivered": sum(
                    r["delivered"] for r in n["requirements"].values()
                ),
                "unmet": a["unmet"],
                "fill_pct": a["fill_pct"],
                "projected_unmet": p["unmet"],
                "projected_fill_pct": p["fill_pct"],
            }
        )

    return {
        "starvation_index": starve,
        "projected_starvation_index": proj_starve,
        "points": points,
    }

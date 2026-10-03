"""Local planar geometry (flat projection in km).

All functions take and return ``(lat, lon)`` coordinates in degrees, and compute
distances in kilometers on a local equidistant projection around ``LAT0``.
At a ~30 km scale this projection is equivalent to a "straight line" (ADR 0002).
"""

from __future__ import annotations

from math import cos, degrees, hypot, radians

from .config import LAT0, LON0, R


def xy(lat: float, lon: float) -> tuple[float, float]:
    """Convert ``(lat, lon)`` to the local km coordinate system."""
    x = R * radians(lon) * cos(radians(LAT0))
    y = R * radians(lat)
    return (x, y)


def latlon_offset(dx_km: float, dy_km: float) -> tuple[float, float]:
    """Inverse of ``xy`` for an offset in km from the map center ``(LAT0, LON0)``.

    Used by the seed to define the scenario in kilometers.
    """
    lat = LAT0 + degrees(dy_km / R)
    lon = LON0 + degrees(dx_km / (R * cos(radians(LAT0))))
    return (lat, lon)


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Euclidean distance in km between two ``(lat, lon)`` points."""
    ax, ay = xy(*a)
    bx, by = xy(*b)
    return hypot(ax - bx, ay - by)


def seg_dist(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    """Distance from point ``p`` to segment ``a-b`` (clamped to the endpoints).

    Handles the degenerate segment ``a == b`` (returns the distance to the point).
    """
    px, py = xy(*p)
    ax, ay = xy(*a)
    bx, by = xy(*b)
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return hypot(px - cx, py - cy)


def polyline_dist(p: tuple[float, float], pts: list[tuple[float, float]]) -> float:
    """Minimal distance from point ``p`` to the polyline ``pts``."""
    if len(pts) < 2:
        return dist(p, pts[0]) if pts else float("inf")
    return min(seg_dist(p, pts[i], pts[i + 1]) for i in range(len(pts) - 1))

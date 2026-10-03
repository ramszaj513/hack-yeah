"""Geometria lokalna (płaski rzut w km).

Wszystkie funkcje przyjmują i zwracają współrzędne ``(lat, lon)`` w stopniach,
a odległości liczą w kilometrach na lokalnym rzucie ekwidystantnym wokół ``LAT0``.
Przy skali ~30 km ten rzut jest równoważny „prostej linii" (ADR 0002).
"""

from __future__ import annotations

from math import cos, degrees, hypot, radians

from .config import LAT0, LON0, R


def xy(lat: float, lon: float) -> tuple[float, float]:
    """Zamienia ``(lat, lon)`` na lokalny układ w km."""
    x = R * radians(lon) * cos(radians(LAT0))
    y = R * radians(lat)
    return (x, y)


def latlon_offset(dx_km: float, dy_km: float) -> tuple[float, float]:
    """Odwrotność ``xy`` dla przesunięcia w km od środka mapy ``(LAT0, LON0)``.

    Używane przez seed, żeby definiować scenariusz w kilometrach.
    """
    lat = LAT0 + degrees(dy_km / R)
    lon = LON0 + degrees(dx_km / (R * cos(radians(LAT0))))
    return (lat, lon)


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Odległość euklidesowa w km między dwoma punktami ``(lat, lon)``."""
    ax, ay = xy(*a)
    bx, by = xy(*b)
    return hypot(ax - bx, ay - by)


def seg_dist(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    """Odległość punktu ``p`` od odcinka ``a-b`` (z przycięciem do końców).

    Obsługuje zdegenerowany odcinek ``a == b`` (zwraca odległość do punktu).
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
    """Minimalna odległość punktu ``p`` od łamanej ``pts``."""
    if len(pts) < 2:
        return dist(p, pts[0]) if pts else float("inf")
    return min(seg_dist(p, pts[i], pts[i + 1]) for i in range(len(pts) - 1))

"""Warstwa danych: schemat SQLite, seed scenariusza demo, transakcje i Lock.

Schemat i model danych: ``docs/ARCHITECTURE.md``; przypadki: ``docs/ALGORITHM.md``.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from pathlib import Path

from . import geometry as geo
from .config import CATEGORIES, DB_PATH, DEFAULT_MODE

# Jeden worker uvicorn + ten Lock wokół mutacji i przeliczeń = brak wyścigów.
lock = threading.Lock()


class Conflict(Exception):
    """Stan nie pozwala wykonać operacji (→ HTTP 409)."""


class NotFound(Exception):
    """Zasób nie istnieje (→ HTTP 404)."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS crates(
  id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  lat REAL,
  lon REAL,
  status TEXT NOT NULL DEFAULT 'available'
);

CREATE TABLE IF NOT EXISTS trips(
  id TEXT PRIMARY KEY,
  olat REAL, olon REAL, dlat REAL, dlon REAL,
  detour_budget_min REAL NOT NULL,
  slots_free INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'available'
);

CREATE TABLE IF NOT EXISTS need_points(
  id TEXT PRIMARY KEY,
  name TEXT,
  lat REAL, lon REAL,
  severity INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS requirements(
  need_id TEXT NOT NULL,
  category TEXT NOT NULL,
  needed INTEGER NOT NULL,
  delivered INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(need_id, category)
);

CREATE TABLE IF NOT EXISTS settings(
  key TEXT PRIMARY KEY,
  value TEXT
);
"""


def connect() -> sqlite3.Connection:
    """Nowe połączenie do bazy z ``Row`` jako fabryką wierszy."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Seed scenariusza kontrastu
# ---------------------------------------------------------------------------


def _ll(dx_km: float, dy_km: float) -> tuple[float, float]:
    """Skrót: przesunięcie km od środka mapy → ``(lat, lon)``."""
    return geo.latlon_offset(dx_km, dy_km)


# Punkty potrzeb: (id, name, dx, dy, severity, {category: needed})
# Cel: w trybie nearest_fit daleki punkt (severity=5) dostaje 0%,
# a w fair_share zostaje obsłużony.
_NEEDS = [
    ("n-centrum", "Śródmieście", 0, 0, 2, {"food": 3}),
    ("n-praga", "Praga", 7, 3, 1, {"water": 2}),
    ("n-wola", "Wola", -6, 4, 3, {"meds": 2}),
    ("n-mokotow", "Mokotów", 3, -7, 2, {"food": 2, "hygiene": 1}),
    ("n-bialoleka", "Białołęka", 5, 13, 4, {"water": 3, "food": 1}),
    ("n-rembertow", "Rembertów-Wschód", 14, -14, 5, {"meds": 2, "water": 1}),
]

# Przejazdy: (id, (ox,oy), (dx,dy), detour_budget_min, slots_free)
# Budżety zróżnicowane 5–15 min, trasy przecinają centrum.
# t-na-rembertow prowadzi dokładnie przez (0,0) i ma duży budżet, więc jako
# jedyny dosięga dalekiego punktu n-rembertow — to jest dźwignia kontrastu.
_TRIPS = [
    ("t-centrum-wschod", (-16, -2), (16, 2), 6, 2),
    ("t-polnoc-poludnie", (-4, 16), (4, -16), 5, 2),
    ("t-zachod-wschod", (-16, 6), (16, -6), 8, 3),
    ("t-poludniowy-wschod", (10, 16), (-10, -16), 7, 2),
    ("t-na-rembertow", (-14, 14), (16, -8), 15, 3),
    ("t-obwodnica", (-15, -10), (15, 10), 9, 3),
]

# Skrzynki: (id, category, dx, dy)
_CRATES = [
    ("c01", "food", -1, 1),
    ("c02", "food", 2, -2),
    ("c03", "food", -5, 5),
    ("c04", "water", 6, 3),
    ("c05", "water", 8, 3),
    ("c06", "water", 13, -13),
    ("c07", "meds", 13, -13),
    ("c08", "meds", 12, -12),
    ("c09", "meds", -6, 4),
    ("c10", "meds", -5, 4),
    ("c11", "water", 4, 13),
    ("c12", "food", 5, 12),
    ("c13", "hygiene", 3, -7),
    ("c14", "food", 3, -6),
    ("c15", "water", -2, 2),
    ("c16", "food", 10, -10),
    ("c17", "meds", 14, -13),
    ("c18", "water", 14, -15),
]


def _insert_seed(conn: sqlite3.Connection) -> None:
    for nid, name, dx, dy, sev, reqs in _NEEDS:
        lat, lon = _ll(dx, dy)
        conn.execute(
            "INSERT INTO need_points(id, name, lat, lon, severity, status) "
            "VALUES(?,?,?,?,?,'open')",
            (nid, name, lat, lon, sev),
        )
        for cat, qty in reqs.items():
            conn.execute(
                "INSERT INTO requirements(need_id, category, needed, delivered) "
                "VALUES(?,?,?,0)",
                (nid, cat, qty),
            )

    for cid, cat, dx, dy in _CRATES:
        lat, lon = _ll(dx, dy)
        conn.execute(
            "INSERT INTO crates(id, category, lat, lon, status) "
            "VALUES(?,?,?,?,'available')",
            (cid, cat, lat, lon),
        )

    for tid, (ox, oy), (dx, dy), budget, slots in _TRIPS:
        olat, olon = _ll(ox, oy)
        dlat, dlon = _ll(dx, dy)
        conn.execute(
            "INSERT INTO trips(id, olat, olon, dlat, dlon, detour_budget_min, "
            "slots_free, status) VALUES(?,?,?,?,?,?,?,'available')",
            (tid, olat, olon, dlat, dlon, budget, slots),
        )


def seed(conn: sqlite3.Connection) -> None:
    """Czyści tabele i wstawia scenariusz demo (jedna transakcja)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        for table in ("requirements", "need_points", "trips", "crates", "settings"):
            conn.execute(f"DELETE FROM {table}")
        _insert_seed(conn)
        conn.execute(
            "INSERT INTO settings(key, value) VALUES('mode', ?)", (DEFAULT_MODE,)
        )
        conn.execute("INSERT INTO settings(key, value) VALUES('seeded', '1')")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def reset(conn: sqlite3.Connection) -> None:
    """``POST /reset`` — powrót do stanu seeda."""
    seed(conn)


def init() -> None:
    """Tworzy schemat i seeduje, jeśli baza jest jeszcze niezaseedowana."""
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'seeded'"
        ).fetchone()
        if row is None:
            seed(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Odczyt
# ---------------------------------------------------------------------------


def get_mode(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = 'mode'").fetchone()
    return row["value"] if row else DEFAULT_MODE


def set_mode(conn: sqlite3.Connection, mode: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES('mode', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (mode,),
    )
    conn.commit()


def load_state(conn: sqlite3.Connection) -> dict:
    """Zwraca pełny stan z bazy w formie gotowej dla solvera i API."""
    crates = [dict(r) for r in conn.execute("SELECT * FROM crates ORDER BY id")]
    trips = [dict(r) for r in conn.execute("SELECT * FROM trips ORDER BY id")]
    need_rows = [
        dict(r) for r in conn.execute("SELECT * FROM need_points ORDER BY id")
    ]
    req_rows = [
        dict(r) for r in conn.execute("SELECT * FROM requirements ORDER BY need_id, category")
    ]

    reqs_by_need: dict[str, dict] = {}
    for r in req_rows:
        reqs_by_need.setdefault(r["need_id"], {})[r["category"]] = {
            "needed": r["needed"],
            "delivered": r["delivered"],
            "remaining": max(0, r["needed"] - r["delivered"]),
        }

    needs = []
    for n in need_rows:
        n["requirements"] = reqs_by_need.get(n["id"], {})
        needs.append(n)

    return {
        "mode": get_mode(conn),
        "crates": crates,
        "trips": trips,
        "need_points": needs,
    }


def delivered_map(need_points: list[dict]) -> dict[tuple[str, str], int]:
    """Mapa ``(need_id, category) -> delivered`` dla solvera."""
    out: dict[tuple[str, str], int] = {}
    for n in need_points:
        for cat, r in n["requirements"].items():
            out[(n["id"], cat)] = r["delivered"]
    return out


# ---------------------------------------------------------------------------
# Zapis: tworzenie zasobów
# ---------------------------------------------------------------------------


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def add_crate(
    conn: sqlite3.Connection, category: str, lat: float, lon: float, cid: str | None
) -> str:
    cid = cid or _gen_id("crate")
    exists = conn.execute("SELECT 1 FROM crates WHERE id = ?", (cid,)).fetchone()
    if exists:
        raise Conflict(f"Skrzynka o id={cid} już istnieje")
    conn.execute(
        "INSERT INTO crates(id, category, lat, lon, status) VALUES(?,?,?,?,'available')",
        (cid, category, lat, lon),
    )
    conn.commit()
    return cid


def add_trip(
    conn: sqlite3.Connection,
    olat: float,
    olon: float,
    dlat: float,
    dlon: float,
    detour_budget_min: float,
    slots_free: int,
    tid: str | None,
) -> str:
    tid = tid or _gen_id("trip")
    exists = conn.execute("SELECT 1 FROM trips WHERE id = ?", (tid,)).fetchone()
    if exists:
        raise Conflict(f"Przejazd o id={tid} już istnieje")
    conn.execute(
        "INSERT INTO trips(id, olat, olon, dlat, dlon, detour_budget_min, "
        "slots_free, status) VALUES(?,?,?,?,?,?,?,'available')",
        (tid, olat, olon, dlat, dlon, detour_budget_min, slots_free),
    )
    conn.commit()
    return tid


def add_need(
    conn: sqlite3.Connection,
    name: str,
    lat: float,
    lon: float,
    severity: int,
    requirements: dict[str, int],
    nid: str | None,
) -> str:
    nid = nid or _gen_id("need")
    exists = conn.execute(
        "SELECT 1 FROM need_points WHERE id = ?", (nid,)
    ).fetchone()
    if exists:
        raise Conflict(f"Punkt potrzeb o id={nid} już istnieje")

    # Przypadek 5: wszystkie ``needed == 0`` → punkt od razu zamknięty.
    total = sum(requirements.values())
    status = "closed" if total == 0 else "open"

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO need_points(id, name, lat, lon, severity, status) "
            "VALUES(?,?,?,?,?,?)",
            (nid, name, lat, lon, severity, status),
        )
        for cat, qty in requirements.items():
            conn.execute(
                "INSERT INTO requirements(need_id, category, needed, delivered) "
                "VALUES(?,?,?,0)",
                (nid, cat, qty),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return nid


# ---------------------------------------------------------------------------
# Zapisywanie objazdu (Claim) — atomowe, pierwszy wygrywa
# ---------------------------------------------------------------------------


def claim(
    conn: sqlite3.Connection, trip_id: str, need_id: str, crate_ids: list[str]
) -> dict:
    """Przejmuje sugerowany objazd. Rzuca ``Conflict``/``NotFound``."""
    trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if trip is None:
        raise NotFound(f"Nie ma przejazdu id={trip_id}")
    need = conn.execute(
        "SELECT * FROM need_points WHERE id = ?", (need_id,)
    ).fetchone()
    if need is None:
        raise NotFound(f"Nie ma punktu potrzeb id={need_id}")

    # Kandydat nieaktualny — nie ufamy danym klienta.
    if trip["status"] != "available":
        raise Conflict("Przejazd został już użyty")
    if need["status"] != "open":
        raise Conflict("Punkt potrzeb jest zamknięty")
    if not crate_ids:
        raise Conflict("Trzeba przejąć co najmniej jedną skrzynkę")

    # Wczytaj skrzynki i sprawdź dostępność.
    placeholders = ",".join("?" for _ in crate_ids)
    rows = conn.execute(
        f"SELECT * FROM crates WHERE id IN ({placeholders})", crate_ids
    ).fetchall()
    if len(rows) != len(set(crate_ids)):
        raise NotFound("Niektóre skrzynki nie istnieją")
    for cr in rows:
        if cr["status"] != "available":
            raise Conflict(f"Skrzynka {cr['id']} jest już przejęta")

    # Zlicz per kategoria i zweryfikuj zapotrzebowanie.
    counts: dict[str, int] = {}
    for cr in rows:
        counts[cr["category"]] = counts.get(cr["category"], 0) + 1

    reqs = {
        r["category"]: r
        for r in conn.execute(
            "SELECT * FROM requirements WHERE need_id = ?", (need_id,)
        ).fetchall()
    }
    for cat, n in counts.items():
        req = reqs.get(cat)
        if req is None:
            raise Conflict(f"Punkt potrzeb nie wymaga kategorii {cat}")
        if n > max(0, req["needed"] - req["delivered"]):
            raise Conflict(f"Zbyt dużo skrzynek kategorii {cat}")

    # Atomowa transakcja: crates→claimed, trip→used, delivered += n.
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            f"UPDATE crates SET status='claimed' WHERE id IN ({placeholders})",
            crate_ids,
        )
        conn.execute(
            "UPDATE trips SET status='used' WHERE id = ?", (trip_id,)
        )
        for cat, n in counts.items():
            conn.execute(
                "UPDATE requirements SET delivered = delivered + ? "
                "WHERE need_id = ? AND category = ?",
                (n, need_id, cat),
            )

        # Zamknij punkt, jeśli wszystko zaspokojone.
        remaining_rows = conn.execute(
            "SELECT needed, delivered FROM requirements WHERE need_id = ?",
            (need_id,),
        ).fetchall()
        if all(
            r["delivered"] >= r["needed"] for r in remaining_rows
        ):
            conn.execute(
                "UPDATE need_points SET status='closed' WHERE id = ?", (need_id,)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "trip_id": trip_id,
        "need_id": need_id,
        "crate_ids": sorted(crate_ids),
        "delivered": counts,
    }

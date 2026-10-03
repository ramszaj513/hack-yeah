"""Data layer: SQLite schema, demo scenario seed, transactions and Lock.

Schema and data model: ``docs/ARCHITECTURE.md``; cases: ``docs/ALGORITHM.md``.
Post-MVP additions (persistent detours with TTL, checkpoints, CRUD) are documented
in ``docs/adr/0006`` and ``docs/adr/0007``.
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path

from . import geometry as geo
from .config import DB_PATH, DEFAULT_MODE, SEED_VERSION

# One uvicorn worker + this Lock around mutations and solver runs = no races.
lock = threading.Lock()


class Conflict(Exception):
    """The current state does not allow the operation (-> HTTP 409)."""


class NotFound(Exception):
    """The resource does not exist (-> HTTP 404)."""


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

-- Persistent detours: suggested (with TTL) -> claimed -> picked_up -> delivered.
CREATE TABLE IF NOT EXISTS detours(
  id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL,
  need_id TEXT NOT NULL,
  mode TEXT NOT NULL,
  extra_minutes REAL NOT NULL DEFAULT 0,
  utility_gain REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'suggested',
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS detour_crates(
  detour_id TEXT NOT NULL,
  crate_id TEXT NOT NULL,
  PRIMARY KEY(detour_id, crate_id)
);
"""

# Crate lifecycle: available -> claimed -> picked_up -> delivered.
# Trip status: available -> used.


def connect() -> sqlite3.Connection:
    """Open a new database connection with ``Row`` as the row factory."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Contrast scenario seed
# ---------------------------------------------------------------------------


def _ll(dx_km: float, dy_km: float) -> tuple[float, float]:
    """Shorthand: offset in km from the map center -> ``(lat, lon)``."""
    return geo.latlon_offset(dx_km, dy_km)


# Need-points: (id, name, dx, dy, severity, {category: needed})
# Goal: under nearest_fit the far point (severity=5) gets 0%,
# while under fair_share it is served.
_NEEDS = [
    ("n-downtown", "City Center", 0, 0, 2, {"food": 3}),
    ("n-praga", "Praga", 7, 3, 1, {"water": 2}),
    ("n-wola", "Wola", -6, 4, 3, {"meds": 2}),
    ("n-mokotow", "Mokotow", 3, -7, 2, {"food": 2, "hygiene": 1}),
    ("n-bialoleka", "Bialoleka", 5, 13, 4, {"water": 3, "food": 1}),
    ("n-rembertow-east", "Rembertow East", 14, -14, 5, {"meds": 2, "water": 1}),
]

# Trips: (id, (ox,oy), (dx,dy), detour_budget_min, slots_free)
# Budgets vary from 5 to 15 min; routes cross the center.
# t-to-rembertow runs exactly through (0,0) and has a large budget, so it is the
# only trip that reaches the far n-rembertow-east point — the contrast lever.
_TRIPS = [
    ("t-downtown-east", (-16, -2), (16, 2), 6, 2),
    ("t-north-south", (-4, 16), (4, -16), 5, 2),
    ("t-west-east", (-16, 6), (16, -6), 8, 3),
    ("t-southeast", (10, 16), (-10, -16), 7, 2),
    ("t-to-rembertow", (-14, 14), (16, -8), 15, 3),
    ("t-ring-road", (-15, -10), (15, 10), 9, 3),
]

# Crates: (id, category, dx, dy)
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
    """Clear the tables and insert the demo scenario (single transaction)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        for table in (
            "detour_crates",
            "detours",
            "requirements",
            "need_points",
            "trips",
            "crates",
            "settings",
        ):
            conn.execute(f"DELETE FROM {table}")
        _insert_seed(conn)
        conn.execute(
            "INSERT INTO settings(key, value) VALUES('mode', ?)", (DEFAULT_MODE,)
        )
        conn.execute("INSERT INTO settings(key, value) VALUES('seeded', '1')")
        conn.execute(
            "INSERT INTO settings(key, value) VALUES('seed_version', ?)",
            (SEED_VERSION,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def reset(conn: sqlite3.Connection) -> None:
    """``POST /reset`` — restore the seed state."""
    seed(conn)


def init() -> None:
    """Create the schema and seed if the database is missing or on an old seed version."""
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        seeded = conn.execute(
            "SELECT value FROM settings WHERE key = 'seeded'"
        ).fetchone()
        version = conn.execute(
            "SELECT value FROM settings WHERE key = 'seed_version'"
        ).fetchone()
        if seeded is None or version is None or version["value"] != SEED_VERSION:
            seed(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Read
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
    """Return the full database state in a form ready for the solver and API."""
    crates = [dict(r) for r in conn.execute("SELECT * FROM crates ORDER BY id")]
    trips = [dict(r) for r in conn.execute("SELECT * FROM trips ORDER BY id")]
    need_rows = [
        dict(r) for r in conn.execute("SELECT * FROM need_points ORDER BY id")
    ]
    req_rows = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM requirements ORDER BY need_id, category"
        )
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
    """Map ``(need_id, category) -> delivered`` for the solver."""
    out: dict[tuple[str, str], int] = {}
    for n in need_points:
        for cat, r in n["requirements"].items():
            out[(n["id"], cat)] = r["delivered"]
    return out


# ---------------------------------------------------------------------------
# Persistent detours
# ---------------------------------------------------------------------------


def _detour_crates(conn: sqlite3.Connection, detour_id: str) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT dc.crate_id, c.category, c.lat, c.lon, c.status "
            "FROM detour_crates dc JOIN crates c ON c.id = dc.crate_id "
            "WHERE dc.detour_id = ? ORDER BY dc.crate_id",
            (detour_id,),
        )
    ]


def load_detours(conn: sqlite3.Connection) -> list[dict]:
    """Return active detours (everything except expired suggestions)."""
    rows = conn.execute(
        "SELECT * FROM detours WHERE status != 'expired' ORDER BY created_at DESC"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        crates = _detour_crates(conn, d["id"])
        d["crate_ids"] = [c["crate_id"] for c in crates]
        d["crates"] = crates
        out.append(d)
    return out


def persist_suggestions(
    conn: sqlite3.Connection, suggestions: list[dict], mode: str, ttl: float
) -> list[tuple[str, float]]:
    """Store the freshly computed suggestions as persistent, expiring detours.

    Suggestions identical to an existing valid one keep their id and expiry, so the
    countdown is stable across ``GET /state`` calls. Returns ``(detour_id, expires_at)``
    aligned with the input list.
    """
    now = time.time()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "UPDATE detours SET status='expired' "
            "WHERE status='suggested' AND expires_at < ?",
            (now,),
        )
        existing: dict[tuple, sqlite3.Row] = {}
        for d in conn.execute(
            "SELECT * FROM detours WHERE status='suggested'"
        ).fetchall():
            crates = frozenset(
                r["crate_id"]
                for r in conn.execute(
                    "SELECT crate_id FROM detour_crates WHERE detour_id = ?",
                    (d["id"],),
                )
            )
            existing[(d["trip_id"], d["need_id"], crates)] = d

        kept: set[str] = set()
        result: list[tuple[str, float]] = []
        for s in suggestions:
            sig = (s["trip_id"], s["need_id"], frozenset(s["crate_ids"]))
            row = existing.get(sig)
            if row is not None and row["mode"] == mode:
                kept.add(row["id"])
                result.append((row["id"], row["expires_at"]))
                continue
            did = _gen_id("detour")
            conn.execute(
                "INSERT INTO detours(id, trip_id, need_id, mode, extra_minutes, "
                "utility_gain, status, created_at, expires_at) "
                "VALUES(?,?,?,?,?,?,'suggested',?,?)",
                (
                    did,
                    s["trip_id"],
                    s["need_id"],
                    mode,
                    float(s["extra_minutes"]),
                    float(s["utility_gain"]),
                    now,
                    now + ttl,
                ),
            )
            for cid in s["crate_ids"]:
                conn.execute(
                    "INSERT INTO detour_crates(detour_id, crate_id) VALUES(?,?)",
                    (did, cid),
                )
            result.append((did, now + ttl))

        for did in [d["id"] for d in existing.values() if d["id"] not in kept]:
            conn.execute("DELETE FROM detour_crates WHERE detour_id = ?", (did,))
            conn.execute("DELETE FROM detours WHERE id = ?", (did,))
        conn.execute("DELETE FROM detours WHERE status='expired'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return result


def physical_counts(conn: sqlite3.Connection) -> dict:
    """Physical progress of crates: in transit and delivered, globally and per need."""
    in_transit = conn.execute(
        "SELECT COUNT(*) AS n FROM crates WHERE status IN ('claimed','picked_up')"
    ).fetchone()["n"]
    delivered = conn.execute(
        "SELECT COUNT(*) AS n FROM crates WHERE status = 'delivered'"
    ).fetchone()["n"]
    per_need = {
        r["need_id"]: r["n"]
        for r in conn.execute(
            "SELECT d.need_id AS need_id, COUNT(*) AS n "
            "FROM detour_crates dc JOIN detours d ON d.id = dc.detour_id "
            "JOIN crates c ON c.id = dc.crate_id "
            "WHERE c.status = 'delivered' GROUP BY d.need_id"
        )
    }
    detour_counts = {
        r["status"]: r["n"]
        for r in conn.execute(
            "SELECT status, COUNT(*) AS n FROM detours GROUP BY status"
        )
    }
    return {
        "in_transit": in_transit,
        "delivered": delivered,
        "per_need_delivered": per_need,
        "detour_counts": detour_counts,
    }


# ---------------------------------------------------------------------------
# Write: creating resources
# ---------------------------------------------------------------------------


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def add_crate(
    conn: sqlite3.Connection, category: str, lat: float, lon: float, cid: str | None
) -> str:
    cid = cid or _gen_id("crate")
    exists = conn.execute("SELECT 1 FROM crates WHERE id = ?", (cid,)).fetchone()
    if exists:
        raise Conflict(f"A crate with id={cid} already exists")
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
        raise Conflict(f"A trip with id={tid} already exists")
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
        raise Conflict(f"A need-point with id={nid} already exists")

    # Case 5: all ``needed == 0`` -> the point is closed immediately.
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
# Write: admin editing (PATCH / DELETE)
# ---------------------------------------------------------------------------


def update_crate(
    conn: sqlite3.Connection,
    cid: str,
    category: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> None:
    row = conn.execute("SELECT * FROM crates WHERE id = ?", (cid,)).fetchone()
    if row is None:
        raise NotFound(f"There is no crate with id={cid}")
    if row["status"] != "available":
        raise Conflict("Only an available crate can be edited")
    sets, params = [], []
    if category is not None:
        sets.append("category = ?")
        params.append(category)
    if lat is not None:
        sets.append("lat = ?")
        params.append(lat)
    if lon is not None:
        sets.append("lon = ?")
        params.append(lon)
    if not sets:
        return
    conn.execute(
        f"UPDATE crates SET {', '.join(sets)} WHERE id = ?", (*params, cid)
    )
    conn.commit()


def delete_crate(conn: sqlite3.Connection, cid: str) -> None:
    row = conn.execute("SELECT * FROM crates WHERE id = ?", (cid,)).fetchone()
    if row is None:
        raise NotFound(f"There is no crate with id={cid}")
    if row["status"] != "available":
        raise Conflict("Only an available crate can be deleted")
    # Drop stale suggested detours that referenced this crate.
    for d in conn.execute(
        "SELECT DISTINCT dc.detour_id AS did FROM detour_crates dc "
        "JOIN detours d ON d.id = dc.detour_id "
        "WHERE dc.crate_id = ? AND d.status = 'suggested'",
        (cid,),
    ).fetchall():
        conn.execute("DELETE FROM detour_crates WHERE detour_id = ?", (d["did"],))
        conn.execute("DELETE FROM detours WHERE id = ?", (d["did"],))
    conn.execute("DELETE FROM crates WHERE id = ?", (cid,))
    conn.commit()


def update_trip(
    conn: sqlite3.Connection,
    tid: str,
    olat: float | None = None,
    olon: float | None = None,
    dlat: float | None = None,
    dlon: float | None = None,
    detour_budget_min: float | None = None,
    slots_free: int | None = None,
) -> None:
    row = conn.execute("SELECT * FROM trips WHERE id = ?", (tid,)).fetchone()
    if row is None:
        raise NotFound(f"There is no trip with id={tid}")
    if row["status"] != "available":
        raise Conflict("Only an available trip can be edited")
    fields = [
        ("olat", olat),
        ("olon", olon),
        ("dlat", dlat),
        ("dlon", dlon),
        ("detour_budget_min", detour_budget_min),
        ("slots_free", slots_free),
    ]
    sets, params = [], []
    for name, value in fields:
        if value is not None:
            sets.append(f"{name} = ?")
            params.append(value)
    if not sets:
        return
    conn.execute(
        f"UPDATE trips SET {', '.join(sets)} WHERE id = ?", (*params, tid)
    )
    conn.commit()


def delete_trip(conn: sqlite3.Connection, tid: str) -> None:
    row = conn.execute("SELECT * FROM trips WHERE id = ?", (tid,)).fetchone()
    if row is None:
        raise NotFound(f"There is no trip with id={tid}")
    if row["status"] != "available":
        raise Conflict("Only an available trip can be deleted")
    # Drop stale suggested detours that referenced this trip.
    for d in conn.execute(
        "SELECT id FROM detours WHERE trip_id = ? AND status = 'suggested'",
        (tid,),
    ).fetchall():
        conn.execute("DELETE FROM detour_crates WHERE detour_id = ?", (d["id"],))
        conn.execute("DELETE FROM detours WHERE id = ?", (d["id"],))
    conn.execute("DELETE FROM trips WHERE id = ?", (tid,))
    conn.commit()


def update_need(
    conn: sqlite3.Connection,
    nid: str,
    name: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    severity: int | None = None,
    requirements: dict[str, int] | None = None,
    status: str | None = None,
) -> None:
    row = conn.execute("SELECT * FROM need_points WHERE id = ?", (nid,)).fetchone()
    if row is None:
        raise NotFound(f"There is no need-point with id={nid}")

    conn.execute("BEGIN IMMEDIATE")
    try:
        sets, params = [], []
        for field, value in (
            ("name", name),
            ("lat", lat),
            ("lon", lon),
            ("severity", severity),
        ):
            if value is not None:
                sets.append(f"{field} = ?")
                params.append(value)
        if sets:
            conn.execute(
                f"UPDATE need_points SET {', '.join(sets)} WHERE id = ?",
                (*params, nid),
            )

        if requirements is not None:
            existing = {
                r["category"]: r
                for r in conn.execute(
                    "SELECT * FROM requirements WHERE need_id = ?", (nid,)
                ).fetchall()
            }
            for cat, qty in requirements.items():
                if cat in existing:
                    delivered = min(existing[cat]["delivered"], qty)
                    conn.execute(
                        "UPDATE requirements SET needed = ?, delivered = ? "
                        "WHERE need_id = ? AND category = ?",
                        (qty, delivered, nid, cat),
                    )
                else:
                    conn.execute(
                        "INSERT INTO requirements(need_id, category, needed, delivered) "
                        "VALUES(?,?,?,0)",
                        (nid, cat, qty),
                    )
            for cat in set(existing) - set(requirements):
                conn.execute(
                    "DELETE FROM requirements WHERE need_id = ? AND category = ?",
                    (nid, cat),
                )

        if status is not None:
            new_status = status
        else:
            rows = conn.execute(
                "SELECT needed, delivered FROM requirements WHERE need_id = ?",
                (nid,),
            ).fetchall()
            new_status = (
                "closed"
                if not rows or all(r["delivered"] >= r["needed"] for r in rows)
                else "open"
            )
        conn.execute(
            "UPDATE need_points SET status = ? WHERE id = ?", (new_status, nid)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def delete_need(conn: sqlite3.Connection, nid: str) -> None:
    row = conn.execute("SELECT * FROM need_points WHERE id = ?", (nid,)).fetchone()
    if row is None:
        raise NotFound(f"There is no need-point with id={nid}")
    conn.execute("BEGIN IMMEDIATE")
    try:
        detour_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM detours WHERE need_id = ?", (nid,)
            ).fetchall()
        ]
        for did in detour_ids:
            conn.execute("DELETE FROM detour_crates WHERE detour_id = ?", (did,))
        conn.execute("DELETE FROM detours WHERE need_id = ?", (nid,))
        conn.execute("DELETE FROM requirements WHERE need_id = ?", (nid,))
        conn.execute("DELETE FROM need_points WHERE id = ?", (nid,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ---------------------------------------------------------------------------
# Detour lifecycle: claim -> pickup -> deliver
# ---------------------------------------------------------------------------


def _claim_target(
    conn: sqlite3.Connection,
    trip_id: str | None,
    need_id: str | None,
    crate_ids: list[str] | None,
    detour_id: str | None,
) -> tuple[str, str, list[str], str, float, float]:
    """Resolve the claim target from either a detour id or explicit contents."""
    if detour_id is not None:
        d = conn.execute("SELECT * FROM detours WHERE id = ?", (detour_id,)).fetchone()
        if d is None:
            raise NotFound(f"There is no detour with id={detour_id}")
        if d["status"] != "suggested":
            raise Conflict("This detour has already been claimed")
        if d["expires_at"] < time.time():
            raise Conflict("This suggestion has expired")
        ids = [
            r["crate_id"]
            for r in conn.execute(
                "SELECT crate_id FROM detour_crates WHERE detour_id = ?",
                (detour_id,),
            ).fetchall()
        ]
        return (
            d["trip_id"],
            d["need_id"],
            ids,
            d["mode"],
            d["extra_minutes"],
            d["utility_gain"],
        )
    if not trip_id or not need_id or not crate_ids:
        raise Conflict("Incomplete claim payload")
    return trip_id, need_id, list(crate_ids), DEFAULT_MODE, 0.0, 0.0


def claim(
    conn: sqlite3.Connection,
    trip_id: str | None = None,
    need_id: str | None = None,
    crate_ids: list[str] | None = None,
    detour_id: str | None = None,
) -> dict:
    """Claim a suggested detour (by id or explicit contents). Raises Conflict/NotFound."""
    trip_id, need_id, crate_ids, mode, extra, gain = _claim_target(
        conn, trip_id, need_id, crate_ids, detour_id
    )
    now = time.time()

    trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if trip is None:
        raise NotFound(f"There is no trip with id={trip_id}")
    need = conn.execute(
        "SELECT * FROM need_points WHERE id = ?", (need_id,)
    ).fetchone()
    if need is None:
        raise NotFound(f"There is no need-point with id={need_id}")

    # Stale candidate — we do not trust client-provided data.
    if trip["status"] != "available":
        raise Conflict("The trip has already been used")
    if need["status"] != "open":
        raise Conflict("The need-point is closed")
    if not crate_ids:
        raise Conflict("At least one crate must be claimed")

    placeholders = ",".join("?" for _ in crate_ids)
    rows = conn.execute(
        f"SELECT * FROM crates WHERE id IN ({placeholders})", crate_ids
    ).fetchall()
    if len(rows) != len(set(crate_ids)):
        raise NotFound("Some crates do not exist")
    for cr in rows:
        if cr["status"] != "available":
            raise Conflict(f"Crate {cr['id']} has already been claimed")

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
            raise Conflict(f"The need-point does not require category {cat}")
        if n > max(0, req["needed"] - req["delivered"]):
            raise Conflict(f"Too many crates of category {cat}")

    new_detour_id = detour_id
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            f"UPDATE crates SET status='claimed' WHERE id IN ({placeholders})",
            crate_ids,
        )
        conn.execute("UPDATE trips SET status='used' WHERE id = ?", (trip_id,))
        for cat, n in counts.items():
            conn.execute(
                "UPDATE requirements SET delivered = delivered + ? "
                "WHERE need_id = ? AND category = ?",
                (n, need_id, cat),
            )
        if new_detour_id is not None:
            conn.execute(
                "UPDATE detours SET status='claimed' WHERE id = ?",
                (new_detour_id,),
            )
        else:
            new_detour_id = _gen_id("detour")
            conn.execute(
                "INSERT INTO detours(id, trip_id, need_id, mode, extra_minutes, "
                "utility_gain, status, created_at, expires_at) "
                "VALUES(?,?,?,?,?,?,'claimed',?,?)",
                (new_detour_id, trip_id, need_id, mode, extra, gain, now, now),
            )
            for cid in crate_ids:
                conn.execute(
                    "INSERT INTO detour_crates(detour_id, crate_id) VALUES(?,?)",
                    (new_detour_id, cid),
                )

        remaining_rows = conn.execute(
            "SELECT needed, delivered FROM requirements WHERE need_id = ?",
            (need_id,),
        ).fetchall()
        if all(r["delivered"] >= r["needed"] for r in remaining_rows):
            conn.execute(
                "UPDATE need_points SET status='closed' WHERE id = ?", (need_id,)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "detour_id": new_detour_id,
        "status": "claimed",
        "trip_id": trip_id,
        "need_id": need_id,
        "crate_ids": sorted(crate_ids),
        "delivered": counts,
    }


def _transition(conn: sqlite3.Connection, detour_id: str, frm: set[str], to: str) -> dict:
    d = conn.execute("SELECT * FROM detours WHERE id = ?", (detour_id,)).fetchone()
    if d is None:
        raise NotFound(f"There is no detour with id={detour_id}")
    if d["status"] not in frm:
        raise Conflict(f"Cannot move a detour from '{d['status']}' to '{to}'")
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            f"UPDATE crates SET status=? WHERE id IN "
            "(SELECT crate_id FROM detour_crates WHERE detour_id=?)",
            (to, detour_id),
        )
        conn.execute("UPDATE detours SET status=? WHERE id=?", (to, detour_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"detour_id": detour_id, "status": to}


def pickup_detour(conn: sqlite3.Connection, detour_id: str) -> dict:
    """Checkpoint: the driver has picked up the crates."""
    return _transition(conn, detour_id, {"claimed"}, "picked_up")


def deliver_detour(conn: sqlite3.Connection, detour_id: str) -> dict:
    """Checkpoint: the crates have been delivered."""
    return _transition(conn, detour_id, {"claimed", "picked_up"}, "delivered")

"""FastAPI: validation, endpoints and frontend mounting.

API contract: ``docs/ARCHITECTURE.md``; case catalog: ``docs/ALGORITHM.md``.
The post-MVP endpoints (mode preview, CRUD, detour checkpoints) are documented in
``docs/adr/0006`` and ``docs/adr/0007``.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, solver
from .config import (
    CATEGORIES,
    LAT0,
    LON0,
    MODES,
    SUGGESTION_TTL_SECONDS,
)

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create the schema and seed if the database is empty (case 36).
    db.init()
    yield


app = FastAPI(title="Relay", version="0.2.0", lifespan=lifespan)


# --- Input models ----------------------------------------------------------


class CrateIn(BaseModel):
    category: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    id: str | None = None


class TripIn(BaseModel):
    olat: float = Field(ge=-90, le=90)
    olon: float = Field(ge=-180, le=180)
    dlat: float = Field(ge=-90, le=90)
    dlon: float = Field(ge=-180, le=180)
    detour_budget_min: float = Field(gt=0)
    slots_free: int = Field(gt=0)
    id: str | None = None


class NeedIn(BaseModel):
    name: str = ""
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    severity: int = Field(ge=1, le=5)
    requirements: dict[str, int] = Field(default_factory=dict)
    id: str | None = None


class ClaimIn(BaseModel):
    detour_id: str | None = None
    trip_id: str | None = None
    need_id: str | None = None
    crate_ids: list[str] | None = None


class ModeIn(BaseModel):
    mode: str


class CratePatch(BaseModel):
    category: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class TripPatch(BaseModel):
    olat: float | None = Field(default=None, ge=-90, le=90)
    olon: float | None = Field(default=None, ge=-180, le=180)
    dlat: float | None = Field(default=None, ge=-90, le=90)
    dlon: float | None = Field(default=None, ge=-180, le=180)
    detour_budget_min: float | None = Field(default=None, gt=0)
    slots_free: int | None = Field(default=None, gt=0)


class NeedPatch(BaseModel):
    name: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    severity: int | None = Field(default=None, ge=1, le=5)
    requirements: dict[str, int] | None = None
    status: str | None = None


# --- Helpers ---------------------------------------------------------------


def _validate_category(category: str) -> None:
    if category not in CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown category '{category}'. Allowed: {list(CATEGORIES)}",
        )


def _validate_requirements(reqs: dict[str, int]) -> None:
    for cat, qty in reqs.items():
        _validate_category(cat)
        if qty < 0:
            raise HTTPException(
                status_code=422,
                detail=f"Requirement for '{cat}' cannot be negative",
            )


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


def _serialize_suggestion(s: dict, detour_id: str | None, expires_at: float) -> dict:
    return {
        "detour_id": detour_id,
        "expires_at": expires_at,
        "trip_id": s["trip_id"],
        "need_id": s["need_id"],
        "crate_ids": s["crate_ids"],
        "extra_minutes": round(s["extra_minutes"], 1),
        "utility_gain": round(s["utility_gain"], 3),
        "trip": s["trip"],
        "need": s["need"],
        "crates": s["crates"],
        "route": s["route"],
    }


# --- State / config --------------------------------------------------------


@app.get("/health")
def health() -> dict:
    """Liveness probe. Intentionally does not touch the database."""
    return {"status": "ok", "service": "relay", "version": app.version}


@app.get("/config")
def get_config() -> dict:
    """Frontend configuration: categories, modes, TTL, map center."""
    return {
        "categories": list(CATEGORIES),
        "modes": list(MODES),
        "ttl_seconds": SUGGESTION_TTL_SECONDS,
        "center": {"lat": LAT0, "lon": LON0},
    }


@app.get("/state")
def get_state(mode: str | None = None) -> dict:
    """Full state + freshly computed, disjoint suggestions + metrics.

    Pass ``?mode=nearest_fit`` to preview another scorer without changing the stored
    mode (and without persisting preview suggestions).
    """
    if mode is not None and mode not in MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown mode '{mode}'. Allowed: {list(MODES)}",
        )

    with db.lock:
        conn = db.connect()
        try:
            data = db.load_state(conn)
            requested = mode or data["mode"]
            delivered = db.delivered_map(data["need_points"])
            suggestions = solver.solve(
                data["trips"],
                data["need_points"],
                data["crates"],
                delivered,
                requested,
            )
            metrics = solver.metrics(data["need_points"], suggestions)

            if requested == data["mode"]:
                meta = db.persist_suggestions(
                    conn, suggestions, requested, SUGGESTION_TTL_SECONDS
                )
            else:
                meta = [(None, 0.0) for _ in suggestions]

            detours = db.load_detours(conn)
            physical = db.physical_counts(conn)
            stored_mode = data["mode"]
        finally:
            conn.close()

    for p in metrics["points"]:
        p["delivered_physical"] = physical["per_need_delivered"].get(
            p["need_id"], 0
        )

    return {
        "mode": stored_mode,
        "preview_mode": requested if mode is not None else None,
        "server_time": time.time(),
        "ttl_seconds": SUGGESTION_TTL_SECONDS,
        "crates": data["crates"],
        "trips": data["trips"],
        "need_points": data["need_points"],
        "detours": detours,
        "suggestions": [
            _serialize_suggestion(s, meta[i][0], meta[i][1])
            for i, s in enumerate(suggestions)
        ],
        "metrics": metrics,
        "physical": {
            "in_transit": physical["in_transit"],
            "delivered": physical["delivered"],
            "detour_counts": physical["detour_counts"],
        },
    }


# --- Create ----------------------------------------------------------------


@app.post("/crates")
def create_crate(body: CrateIn) -> dict:
    _validate_category(body.category)
    with db.lock:
        conn = db.connect()
        try:
            cid = db.add_crate(conn, body.category, body.lat, body.lon, body.id)
        except db.Conflict as exc:
            raise _conflict(exc) from exc
        finally:
            conn.close()
    return {"id": cid}


@app.post("/trips")
def create_trip(body: TripIn) -> dict:
    with db.lock:
        conn = db.connect()
        try:
            tid = db.add_trip(
                conn,
                body.olat,
                body.olon,
                body.dlat,
                body.dlon,
                body.detour_budget_min,
                body.slots_free,
                body.id,
            )
        except db.Conflict as exc:
            raise _conflict(exc) from exc
        finally:
            conn.close()
    return {"id": tid}


@app.post("/need-points")
def create_need_point(body: NeedIn) -> dict:
    _validate_requirements(body.requirements)
    with db.lock:
        conn = db.connect()
        try:
            nid = db.add_need(
                conn,
                body.name,
                body.lat,
                body.lon,
                body.severity,
                body.requirements,
                body.id,
            )
        except db.Conflict as exc:
            raise _conflict(exc) from exc
        finally:
            conn.close()
    return {"id": nid}


# --- Edit / delete ---------------------------------------------------------


@app.patch("/crates/{cid}")
def edit_crate(cid: str, body: CratePatch) -> dict:
    patch = body.model_dump(exclude_unset=True)
    if "category" in patch:
        _validate_category(patch["category"])
    with db.lock:
        conn = db.connect()
        try:
            db.update_crate(conn, cid, **patch)
        except db.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except db.Conflict as exc:
            raise _conflict(exc) from exc
        finally:
            conn.close()
    return {"id": cid}


@app.delete("/crates/{cid}")
def remove_crate(cid: str) -> dict:
    with db.lock:
        conn = db.connect()
        try:
            db.delete_crate(conn, cid)
        except db.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except db.Conflict as exc:
            raise _conflict(exc) from exc
        finally:
            conn.close()
    return {"ok": True, "id": cid}


@app.patch("/trips/{tid}")
def edit_trip(tid: str, body: TripPatch) -> dict:
    patch = body.model_dump(exclude_unset=True)
    with db.lock:
        conn = db.connect()
        try:
            db.update_trip(conn, tid, **patch)
        except db.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except db.Conflict as exc:
            raise _conflict(exc) from exc
        finally:
            conn.close()
    return {"id": tid}


@app.delete("/trips/{tid}")
def remove_trip(tid: str) -> dict:
    with db.lock:
        conn = db.connect()
        try:
            db.delete_trip(conn, tid)
        except db.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except db.Conflict as exc:
            raise _conflict(exc) from exc
        finally:
            conn.close()
    return {"ok": True, "id": tid}


@app.patch("/need-points/{nid}")
def edit_need_point(nid: str, body: NeedPatch) -> dict:
    patch = body.model_dump(exclude_unset=True)
    if "requirements" in patch and patch["requirements"] is not None:
        _validate_requirements(patch["requirements"])
    if "status" in patch and patch["status"] not in ("open", "closed"):
        raise HTTPException(
            status_code=422, detail="status must be 'open' or 'closed'"
        )
    with db.lock:
        conn = db.connect()
        try:
            db.update_need(conn, nid, **patch)
        except db.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except db.Conflict as exc:
            raise _conflict(exc) from exc
        finally:
            conn.close()
    return {"id": nid}


@app.delete("/need-points/{nid}")
def remove_need_point(nid: str) -> dict:
    with db.lock:
        conn = db.connect()
        try:
            db.delete_need(conn, nid)
        except db.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except db.Conflict as exc:
            raise _conflict(exc) from exc
        finally:
            conn.close()
    return {"ok": True, "id": nid}


# --- Claim + checkpoints ---------------------------------------------------


@app.post("/claim")
def claim(body: ClaimIn) -> dict:
    with db.lock:
        conn = db.connect()
        try:
            result = db.claim(
                conn,
                trip_id=body.trip_id,
                need_id=body.need_id,
                crate_ids=body.crate_ids,
                detour_id=body.detour_id,
            )
        except db.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except db.Conflict as exc:
            raise _conflict(exc) from exc
        finally:
            conn.close()
    return {"ok": True, **result}


@app.post("/detours/{detour_id}/pickup")
def pickup(detour_id: str) -> dict:
    with db.lock:
        conn = db.connect()
        try:
            result = db.pickup_detour(conn, detour_id)
        except db.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except db.Conflict as exc:
            raise _conflict(exc) from exc
        finally:
            conn.close()
    return {"ok": True, **result}


@app.post("/detours/{detour_id}/deliver")
def deliver(detour_id: str) -> dict:
    with db.lock:
        conn = db.connect()
        try:
            result = db.deliver_detour(conn, detour_id)
        except db.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except db.Conflict as exc:
            raise _conflict(exc) from exc
        finally:
            conn.close()
    return {"ok": True, **result}


# --- Mode / reset ----------------------------------------------------------


@app.post("/mode")
def set_mode(body: ModeIn) -> dict:
    if body.mode not in MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown mode '{body.mode}'. Allowed: {list(MODES)}",
        )
    with db.lock:
        conn = db.connect()
        try:
            db.set_mode(conn, body.mode)
        finally:
            conn.close()
    return {"mode": body.mode}


@app.post("/reset")
def reset() -> dict:
    with db.lock:
        conn = db.connect()
        try:
            db.reset(conn)
        finally:
            conn.close()
    return {"ok": True}


# --- Frontend (mounted last so it does not shadow the API) -----------------

if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

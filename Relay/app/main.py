"""FastAPI: walidacja, endpointy i montaż frontendu.

Kontrakt API: ``docs/ARCHITECTURE.md``; katalog przypadków: ``docs/ALGORITHM.md``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, solver
from .config import CATEGORIES, MODES

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Tworzy schemat i seeduje, jeśli baza jest pusta (przypadek 36).
    db.init()
    yield


app = FastAPI(title="Relay", version="0.1.0", lifespan=lifespan)


# --- Modele wejścia --------------------------------------------------------


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
    trip_id: str
    need_id: str
    crate_ids: list[str]


class ModeIn(BaseModel):
    mode: str


# --- Pomocnicze ------------------------------------------------------------


def _validate_category(category: str) -> None:
    if category not in CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Nieznana kategoria '{category}'. Dozwolone: {list(CATEGORIES)}",
        )


def _validate_requirements(reqs: dict[str, int]) -> None:
    for cat, qty in reqs.items():
        _validate_category(cat)
        if qty < 0:
            raise HTTPException(
                status_code=422,
                detail=f"Zapotrzebowanie dla '{cat}' nie może być ujemne",
            )


def _serialize_suggestion(s: dict) -> dict:
    return {
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


# --- Endpointy -------------------------------------------------------------


@app.get("/state")
def get_state() -> dict:
    """Pełny stan + świeżo przeliczone, rozłączne sugestie + metryki."""
    with db.lock:
        conn = db.connect()
        try:
            data = db.load_state(conn)
        finally:
            conn.close()

        delivered = db.delivered_map(data["need_points"])
        suggestions = solver.solve(
            data["trips"],
            data["need_points"],
            data["crates"],
            delivered,
            data["mode"],
        )
        metrics = solver.metrics(data["need_points"], suggestions)

    return {
        "mode": data["mode"],
        "crates": data["crates"],
        "trips": data["trips"],
        "need_points": data["need_points"],
        "suggestions": [_serialize_suggestion(s) for s in suggestions],
        "metrics": metrics,
    }


@app.post("/crates")
def create_crate(body: CrateIn) -> dict:
    _validate_category(body.category)
    with db.lock:
        conn = db.connect()
        try:
            cid = db.add_crate(conn, body.category, body.lat, body.lon, body.id)
        except db.Conflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
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
            raise HTTPException(status_code=409, detail=str(exc)) from exc
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
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            conn.close()
    return {"id": nid}


@app.post("/claim")
def claim(body: ClaimIn) -> dict:
    with db.lock:
        conn = db.connect()
        try:
            result = db.claim(conn, body.trip_id, body.need_id, body.crate_ids)
        except db.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except db.Conflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            conn.close()
    return {"ok": True, **result}


@app.post("/mode")
def set_mode(body: ModeIn) -> dict:
    if body.mode not in MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Nieznany tryb '{body.mode}'. Dozwolone: {list(MODES)}",
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


# --- Frontend (montowany na końcu, żeby nie przesłonił API) ----------------

if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

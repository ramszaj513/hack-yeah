"""Smoke test E2E dla Relay (zob. docs/PLAN.md sekcja 9).

Używa osobnej bazy w katalogu tymczasowym, żeby nie ruszać danych deweloperskich.
"""

from __future__ import annotations

import os
import tempfile

_tmp_db = os.path.join(tempfile.mkdtemp(prefix="relay-test-"), "relay.db")
os.environ["RELAY_DB_PATH"] = _tmp_db

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _client():
    return TestClient(app)


def _far_point(metrics, need_id="n-rembertow"):
    for p in metrics["points"]:
        if p["need_id"] == need_id:
            return p
    raise AssertionError(f"brak punktu {need_id} w metrykach")


def test_fair_vs_nearest_contrast_and_claim_and_reset():
    with _client() as client:
        # Seed od zera.
        assert client.post("/reset").status_code == 200

        # 1. GET /state -> są sugestie.
        fair = client.get("/state").json()
        assert fair["mode"] == "fair_share"
        assert len(fair["suggestions"]) > 0

        # Kontrast: fair_share dociera do dalekiego, pilnego punktu.
        fair_far = _far_point(fair["metrics"])
        assert fair_far["projected_fill_pct"] == 100.0

        # 4. POST /mode nearest_fit -> inne uporządkowanie; daleki punkt głoduje.
        assert client.post("/mode", json={"mode": "nearest_fit"}).status_code == 200
        nearest = client.get("/state").json()
        assert nearest["mode"] == "nearest_fit"
        assert (
            nearest["metrics"]["projected_starvation_index"]
            > fair["metrics"]["projected_starvation_index"]
        )
        near_far = _far_point(nearest["metrics"])
        assert near_far["projected_fill_pct"] == 0.0
        assert all(s["need_id"] != "n-rembertow" for s in nearest["suggestions"])

        # Wracamy do fair_share i przejmujemy pierwszą sugestię.
        assert client.post("/mode", json={"mode": "fair_share"}).status_code == 200
        state = client.get("/state").json()
        first = state["suggestions"][0]
        trip_id = first["trip_id"]
        need_id = first["need_id"]
        crate_ids = first["crate_ids"]
        before_delivered = {
            p["need_id"]: p["delivered"] for p in state["metrics"]["points"]
        }

        # 2. POST /claim pierwszej sugestii -> 200.
        resp = client.post(
            "/claim",
            json={"trip_id": trip_id, "need_id": need_id, "crate_ids": crate_ids},
        )
        assert resp.status_code == 200, resp.text

        # 3. GET /state -> crates claimed, trip used, delivered wzrosło, sugestia znika.
        after = client.get("/state").json()
        crates_by_id = {c["id"]: c for c in after["crates"]}
        for cid in crate_ids:
            assert crates_by_id[cid]["status"] == "claimed"
        trips_by_id = {t["id"]: t for t in after["trips"]}
        assert trips_by_id[trip_id]["status"] == "used"

        after_delivered = {
            p["need_id"]: p["delivered"] for p in after["metrics"]["points"]
        }
        assert after_delivered.get(need_id, 0) > before_delivered.get(need_id, 0)

        # Żadna nowa sugestia nie używa już tego przejazdu ani tych skrzynek.
        for s in after["suggestions"]:
            assert s["trip_id"] != trip_id
            assert not (set(s["crate_ids"]) & set(crate_ids))

        # Ponowny claim tej samej sugestii -> 409 (przejazd już użyty).
        resp2 = client.post(
            "/claim",
            json={"trip_id": trip_id, "need_id": need_id, "crate_ids": crate_ids},
        )
        assert resp2.status_code == 409

        # 5. POST /reset -> stan wraca do seeda.
        assert client.post("/reset").status_code == 200
        reset_state = client.get("/state").json()
        assert all(c["status"] == "available" for c in reset_state["crates"])
        assert all(t["status"] == "available" for t in reset_state["trips"])
        assert all(p["delivered"] == 0 for p in reset_state["metrics"]["points"])
        assert reset_state["mode"] == "fair_share"


def test_validation_cases():
    with _client() as client:
        assert client.post("/reset").status_code == 200

        # 1. Nieznana kategoria -> 422.
        r = client.post("/crates", json={"category": "pizza", "lat": 52.2, "lon": 21.0})
        assert r.status_code == 422

        # 2. Współrzędne poza zakresem -> 422.
        r = client.post("/crates", json={"category": "food", "lat": 200, "lon": 21.0})
        assert r.status_code == 422

        # 3. Budżet <= 0 / sloty <= 0 -> 422.
        r = client.post(
            "/trips",
            json={
                "olat": 52.0,
                "olon": 21.0,
                "dlat": 52.1,
                "dlon": 21.1,
                "detour_budget_min": 0,
                "slots_free": 2,
            },
        )
        assert r.status_code == 422

        # 4. severity poza 1..5 -> 422.
        r = client.post(
            "/need-points",
            json={
                "name": "Zły",
                "lat": 52.0,
                "lon": 21.0,
                "severity": 9,
                "requirements": {"food": 1},
            },
        )
        assert r.status_code == 422

        # 6. Duplikat id -> 409.
        base = {"category": "food", "lat": 52.0, "lon": 21.0, "id": "dup-crate"}
        assert client.post("/crates", json=base).status_code == 200
        assert client.post("/crates", json=base).status_code == 409

        # 33. mode nieznany -> 400.
        assert client.post("/mode", json={"mode": "magic"}).status_code == 400


def test_empty_need_point_is_closed():
    with _client() as client:
        assert client.post("/reset").status_code == 200
        r = client.post(
            "/need-points",
            json={
                "name": "Puste",
                "lat": 52.0,
                "lon": 21.0,
                "severity": 1,
                "requirements": {},
            },
        )
        assert r.status_code == 200
        nid = r.json()["id"]
        state = client.get("/state").json()
        point = next(n for n in state["need_points"] if n["id"] == nid)
        assert point["status"] == "closed"

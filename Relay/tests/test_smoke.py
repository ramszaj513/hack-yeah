"""Relay end-to-end smoke test (see docs/PLAN.md section 9).

Uses a separate database in a temporary directory so it does not touch development data.
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


def _far_point(metrics, need_id="n-rembertow-east"):
    for p in metrics["points"]:
        if p["need_id"] == need_id:
            return p
    raise AssertionError(f"missing need-point {need_id} in metrics")


def test_fair_vs_nearest_contrast_and_claim_and_reset():
    with _client() as client:
        # Start from a clean seed.
        assert client.post("/reset").status_code == 200

        # 1. GET /state -> there are suggestions.
        fair = client.get("/state").json()
        assert fair["mode"] == "fair_share"
        assert len(fair["suggestions"]) > 0

        # Contrast: fair_share reaches the far, urgent point.
        fair_far = _far_point(fair["metrics"])
        assert fair_far["projected_fill_pct"] == 100.0

        # 4. POST /mode nearest_fit -> different ordering; the far point starves.
        assert client.post("/mode", json={"mode": "nearest_fit"}).status_code == 200
        nearest = client.get("/state").json()
        assert nearest["mode"] == "nearest_fit"
        assert (
            nearest["metrics"]["projected_starvation_index"]
            > fair["metrics"]["projected_starvation_index"]
        )
        near_far = _far_point(nearest["metrics"])
        assert near_far["projected_fill_pct"] == 0.0
        assert all(
            s["need_id"] != "n-rembertow-east" for s in nearest["suggestions"]
        )

        # Go back to fair_share and claim the first suggestion.
        assert client.post("/mode", json={"mode": "fair_share"}).status_code == 200
        state = client.get("/state").json()
        first = state["suggestions"][0]
        trip_id = first["trip_id"]
        need_id = first["need_id"]
        crate_ids = first["crate_ids"]
        before_delivered = {
            p["need_id"]: p["delivered"] for p in state["metrics"]["points"]
        }

        # 2. POST /claim of the first suggestion -> 200.
        resp = client.post(
            "/claim",
            json={"trip_id": trip_id, "need_id": need_id, "crate_ids": crate_ids},
        )
        assert resp.status_code == 200, resp.text

        # 3. GET /state -> crates claimed, trip used, delivered grew, suggestion gone.
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

        # No new suggestion reuses that trip or those crates.
        for s in after["suggestions"]:
            assert s["trip_id"] != trip_id
            assert not (set(s["crate_ids"]) & set(crate_ids))

        # Claiming the same suggestion again -> 409 (trip already used).
        resp2 = client.post(
            "/claim",
            json={"trip_id": trip_id, "need_id": need_id, "crate_ids": crate_ids},
        )
        assert resp2.status_code == 409

        # 5. POST /reset -> the state returns to the seed.
        assert client.post("/reset").status_code == 200
        reset_state = client.get("/state").json()
        assert all(c["status"] == "available" for c in reset_state["crates"])
        assert all(t["status"] == "available" for t in reset_state["trips"])
        assert all(p["delivered"] == 0 for p in reset_state["metrics"]["points"])
        assert reset_state["mode"] == "fair_share"


def test_validation_cases():
    with _client() as client:
        assert client.post("/reset").status_code == 200

        # 1. Unknown category -> 422.
        r = client.post("/crates", json={"category": "pizza", "lat": 52.2, "lon": 21.0})
        assert r.status_code == 422

        # 2. Coordinates out of range -> 422.
        r = client.post("/crates", json={"category": "food", "lat": 200, "lon": 21.0})
        assert r.status_code == 422

        # 3. Budget <= 0 / slots <= 0 -> 422.
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

        # 4. severity outside 1..5 -> 422.
        r = client.post(
            "/need-points",
            json={
                "name": "Bad point",
                "lat": 52.0,
                "lon": 21.0,
                "severity": 9,
                "requirements": {"food": 1},
            },
        )
        assert r.status_code == 422

        # 6. Duplicate id -> 409.
        base = {"category": "food", "lat": 52.0, "lon": 21.0, "id": "dup-crate"}
        assert client.post("/crates", json=base).status_code == 200
        assert client.post("/crates", json=base).status_code == 409

        # 33. Unknown mode -> 400.
        assert client.post("/mode", json={"mode": "magic"}).status_code == 400


def test_empty_need_point_is_closed():
    with _client() as client:
        assert client.post("/reset").status_code == 200
        r = client.post(
            "/need-points",
            json={
                "name": "Empty point",
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


def test_health_endpoint():
    with _client() as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_persistent_detour_ttl_and_checkpoints():
    with _client() as client:
        assert client.post("/reset").status_code == 200

        state = client.get("/state").json()
        assert state["suggestions"]
        first = state["suggestions"][0]
        assert first["detour_id"]
        assert first["expires_at"] > state["server_time"]

        # Suggestion ids are stable across consecutive GET /state calls.
        again = client.get("/state").json()
        assert [s["detour_id"] for s in state["suggestions"]] == [
            s["detour_id"] for s in again["suggestions"]
        ]

        # Claim by detour id.
        resp = client.post("/claim", json={"detour_id": first["detour_id"]})
        assert resp.status_code == 200, resp.text
        did = resp.json()["detour_id"]

        state2 = client.get("/state").json()
        detour = next(d for d in state2["detours"] if d["id"] == did)
        assert detour["status"] == "claimed"
        for cid in first["crate_ids"]:
            assert next(c for c in state2["crates"] if c["id"] == cid)["status"] == "claimed"

        # Checkpoint: picked up.
        assert client.post(f"/detours/{did}/pickup").status_code == 200
        state3 = client.get("/state").json()
        assert next(d for d in state3["detours"] if d["id"] == did)["status"] == "picked_up"
        for cid in first["crate_ids"]:
            assert (
                next(c for c in state3["crates"] if c["id"] == cid)["status"]
                == "picked_up"
            )

        # Checkpoint: delivered.
        assert client.post(f"/detours/{did}/deliver").status_code == 200
        state4 = client.get("/state").json()
        assert next(d for d in state4["detours"] if d["id"] == did)["status"] == "delivered"
        for cid in first["crate_ids"]:
            assert (
                next(c for c in state4["crates"] if c["id"] == cid)["status"]
                == "delivered"
            )
        assert state4["physical"]["delivered"] >= len(first["crate_ids"])

        # A delivered detour cannot be picked up again.
        assert client.post(f"/detours/{did}/pickup").status_code == 409

        # A claimed crate cannot be deleted.
        assert client.delete(f"/crates/{first['crate_ids'][0]}").status_code == 409


def test_mode_preview_does_not_change_stored_mode():
    with _client() as client:
        assert client.post("/reset").status_code == 200

        preview = client.get("/state?mode=nearest_fit").json()
        assert preview["mode"] == "fair_share"
        assert preview["preview_mode"] == "nearest_fit"
        far = next(
            p for p in preview["metrics"]["points"] if p["need_id"] == "n-rembertow-east"
        )
        assert far["projected_fill_pct"] == 0.0

        # The stored mode and its suggestions are untouched.
        stored = client.get("/state").json()
        assert stored["mode"] == "fair_share"
        assert any(
            s["need_id"] == "n-rembertow-east" for s in stored["suggestions"]
        )

        assert client.get("/state?mode=magic").status_code == 400


def test_admin_crud_and_deletion_conflicts():
    with _client() as client:
        assert client.post("/reset").status_code == 200

        # --- Crate ---
        r = client.post(
            "/crates",
            json={"category": "food", "lat": 52.0, "lon": 21.0, "id": "tmp-crate"},
        )
        assert r.status_code == 200
        assert (
            client.patch("/crates/tmp-crate", json={"category": "water"}).status_code
            == 200
        )
        state = client.get("/state").json()
        assert next(c for c in state["crates"] if c["id"] == "tmp-crate")["category"] == "water"
        assert client.delete("/crates/tmp-crate").status_code == 200
        assert client.delete("/crates/tmp-crate").status_code == 404
        assert (
            client.patch("/crates/tmp-crate", json={"category": "food"}).status_code
            == 404
        )

        # --- Trip ---
        r = client.post(
            "/trips",
            json={
                "olat": 52.0,
                "olon": 21.0,
                "dlat": 52.1,
                "dlon": 21.1,
                "detour_budget_min": 8,
                "slots_free": 2,
                "id": "tmp-trip",
            },
        )
        assert r.status_code == 200
        assert (
            client.patch(
                "/trips/tmp-trip", json={"detour_budget_min": 12}
            ).status_code
            == 200
        )
        state = client.get("/state").json()
        assert next(
            t for t in state["trips"] if t["id"] == "tmp-trip"
        )["detour_budget_min"] == 12
        assert client.delete("/trips/tmp-trip").status_code == 200

        # --- Need-point ---
        r = client.post(
            "/need-points",
            json={
                "name": "Tmp",
                "lat": 52.0,
                "lon": 21.0,
                "severity": 2,
                "requirements": {"food": 2},
                "id": "tmp-need",
            },
        )
        assert r.status_code == 200
        assert (
            client.patch(
                "/need-points/tmp-need",
                json={"severity": 5, "requirements": {"food": 1, "water": 3}},
            ).status_code
            == 200
        )
        state = client.get("/state").json()
        point = next(n for n in state["need_points"] if n["id"] == "tmp-need")
        assert point["severity"] == 5
        assert point["requirements"]["water"]["needed"] == 3
        assert "food" in point["requirements"]
        assert (
            client.patch(
                "/need-points/tmp-need", json={"status": "weird"}
            ).status_code
            == 422
        )
        assert client.delete("/need-points/tmp-need").status_code == 200


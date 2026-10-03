import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_empty_transcript_is_explicitly_rejected() -> None:
    response = client.post(
        "/api/v1/check",
        json={"video": {"id": "abc123", "language": "en"}, "transcript": []},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "no_transcript"
    assert "Speech-to-text is not used" in response.json()["warnings"][0]


def test_demo_response_contains_evidence_and_concerning_claims() -> None:
    response = client.post(
        "/api/v1/check",
        json={
            "video": {"id": "abc123", "title": "Demo", "language": "en"},
            "transcript": [{"text": "The Constitution was signed in 1791.", "start": 1, "duration": 3}],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "complete"
    assert any(claim["verdict"] == "false" for claim in payload["claims"])
    assert all(claim["evidence"] for claim in payload["claims"])


def test_fixture_has_valid_json() -> None:
    fixture = Path(__file__).parents[2] / "fixtures" / "demo-results.json"
    assert json.loads(fixture.read_text(encoding="utf-8"))["claims"]

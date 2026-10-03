import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_missing_transcript_is_rejected_cleanly(monkeypatch) -> None:
    from app.pipeline.transcript import TranscriptUnavailable

    def unavailable(video_id: str):
        raise TranscriptUnavailable("missing")

    monkeypatch.setattr("app.main.fetch_english_transcript", unavailable)
    response = client.post(
        "/api/v1/check",
        json={"video": {"id": "abc123", "language": "en"}, "url": "https://www.youtube.com/watch?v=abc123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "no_transcript"
    assert "Speech-to-text is not used" in response.json()["warnings"][0]


def test_demo_mode_is_labelled_as_a_fixture(monkeypatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    from app.config import settings

    settings.cache_clear()
    try:
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
        assert payload["mode"] == "demo"
        # A fixture must never be mistaken for a real check of this video.
        assert "fixture" in payload["warnings"][0].lower()
    finally:
        settings.cache_clear()


def test_missing_model_key_does_not_pretend_to_check(monkeypatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from app.config import settings

    settings.cache_clear()
    try:
        response = client.post(
            "/api/v1/check",
            json={
                "video": {"id": "abc123", "title": "Demo", "language": "en"},
                "transcript": [{"text": "Something factual was said here.", "start": 1, "duration": 3}],
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "failed"
    finally:
        settings.cache_clear()


def test_fixture_has_valid_json() -> None:
    fixture = Path(__file__).parents[2] / "fixtures" / "demo-results.json"
    assert json.loads(fixture.read_text(encoding="utf-8"))["claims"]

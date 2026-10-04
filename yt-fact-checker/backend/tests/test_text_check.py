import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.schemas import ClaimType, TextCheckRequest, Verdict
from app.pipeline.extraction import ExtractedClaim
from app.pipeline.orchestrator import run_text_pipeline
from app.pipeline.rhetoric import DetectedSignal
from app.models.schemas import Technique
from app.pipeline.sources import Retrieval


client = TestClient(app)
TEXT = "The capital of Australia is Canberra."


@pytest.fixture(autouse=True)
def live_settings(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    settings.cache_clear()
    yield
    settings.cache_clear()


@pytest.mark.parametrize("text", ["too short", " " * 40, "a" * 3001])
def test_selection_limits(text):
    assert client.post("/api/v1/check/text", json={"text": text}).status_code == 422


def test_demo_never_reuses_video_verdicts(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    settings.cache_clear()
    response = client.post("/api/v1/check/text", json={"text": TEXT}).json()
    assert response["mode"] == "demo"
    assert response["status"] == "failed"
    assert response["claims"] == []


def test_text_does_not_fetch_youtube_transcript(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    settings.cache_clear()
    def forbidden(*args):
        raise AssertionError("Text checking must not fetch captions")
    monkeypatch.setattr("app.main.fetch_english_transcript", forbidden)
    response = client.post("/api/v1/check/text", json={"text": TEXT})
    assert response.status_code == 200
    assert response.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_context_is_not_an_anchor_and_missing_sources_are_not_false(monkeypatch):
    context_quote = "Only the surrounding context contains this invented statement."
    async def extraction(segments, video, text_context=None):
        assert segments[0].text == TEXT
        assert video.publishedAt == ""
        assert text_context == context_quote
        return [ExtractedClaim(TEXT, TEXT, ClaimType.GENERAL, None, None),
                ExtractedClaim(context_quote, context_quote, ClaimType.GENERAL, None, None)]
    async def rhetoric(segments, video, text_context=None):
        return [DetectedSignal(context_quote, Technique.LOADED_LANGUAGE, "high", "Context only.")]
    async def retrieval(*args):
        return Retrieval(docs=[], failed=[], attempted=["test"])
    monkeypatch.setattr("app.pipeline.orchestrator.extract_claims", extraction)
    monkeypatch.setattr("app.pipeline.orchestrator.detect_signals", rhetoric)
    monkeypatch.setattr("app.pipeline.orchestrator.gather_evidence", retrieval)
    response = await run_text_pipeline(TextCheckRequest(text=TEXT, context=context_quote))
    assert len(response.claims) == 1
    assert response.claims[0].verdict == Verdict.COULDNT_VERIFY
    assert response.signals == []


def test_stream_reports_status_and_complete(monkeypatch):
    async def extraction(*args, **kwargs):
        return []
    async def rhetoric(*args, **kwargs):
        return []
    monkeypatch.setattr("app.pipeline.orchestrator.extract_claims", extraction)
    monkeypatch.setattr("app.pipeline.orchestrator.detect_signals", rhetoric)
    response = client.post("/api/v1/check/text/stream", json={"text": TEXT})
    assert response.status_code == 200
    events = [json.loads(frame[6:]) for frame in response.text.strip().split("\n\n")]
    assert events[0] == {"type": "status", "status": "extracting_claims"}
    assert events[-1]["type"] == "complete"
    assert events[-1]["response"]["status"] == "no_claims"

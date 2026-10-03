import json
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models.schemas import CheckRequest, CheckResponse
from app.pipeline.analysis import analyze_live
from app.pipeline.evidence import configured_provider


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "fixtures" / "demo-results.json"

app = FastAPI(title="yt-fact-checker API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings()["frontend_origins"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def load_demo_response() -> CheckResponse:
    with FIXTURE_PATH.open(encoding="utf-8") as fixture:
        return CheckResponse.model_validate(json.load(fixture))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/check", response_model=CheckResponse)
async def check_video(request: CheckRequest) -> CheckResponse:
    if not request.transcript:
        return CheckResponse(
            analysisId=str(uuid4()),
            status="no_transcript",
            mode="live",
            warnings=["This video cannot be checked because no usable transcript is available. Speech-to-text is not used."],
        )

    if settings()["demo_mode"]:
        return load_demo_response()

    try:
        return await analyze_live(request, configured_provider())
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Fact-checking service failed before producing a result.") from exc

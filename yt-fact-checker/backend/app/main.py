import asyncio
import json
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app import cache
from app.config import settings
from app.models.schemas import CheckRequest, CheckResponse, TextCheckRequest
from app.pipeline.orchestrator import run_pipeline, run_text_pipeline
from app.pipeline.transcript import TranscriptUnavailable, fetch_english_transcript


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "fixtures" / "demo-results.json"

app = FastAPI(title="yt-fact-checker API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


NO_TRANSCRIPT = (
    "This video cannot be checked because no usable English transcript is available. "
    "Speech-to-text is not used."
)


def load_demo_response() -> CheckResponse:
    with FIXTURE_PATH.open(encoding="utf-8") as fixture:
        response = CheckResponse.model_validate(json.load(fixture))
    response.mode = "demo"
    response.warnings = [
        "Demo fixture: these claims are canned sample output, not a live check of this video."
    ] + list(response.warnings)
    return response


@app.get("/api/v1/cache")
async def cache_stats() -> dict:
    """What has been stored, by stage. Empty unless CACHE_ENABLED is on."""
    return {"enabled": settings().cache_enabled, "entries": cache.stats()}


@app.delete("/api/v1/cache")
async def cache_clear() -> dict:
    """Force the next check to be computed from scratch."""
    return {"removed": cache.clear()}


@app.get("/health")
async def health() -> dict[str, str]:
    config = settings()
    return {
        "status": "ok",
        "mode": "demo" if config.demo_mode else "live",
        "model_configured": "yes" if config.llm_enabled else "no",
    }


# YouTube throttles server-side callers without answering, so this fetch can
# hang indefinitely. It is also synchronous, which would block the event loop
# for every other request while it waited.
TRANSCRIPT_TIMEOUT_SECONDS = 15.0


async def _ensure_transcript(request: CheckRequest) -> CheckResponse | None:
    """Fill in the transcript server-side when the extension didn't supply one."""
    if request.transcript:
        return None

    def unavailable(detail: str) -> CheckResponse:
        return CheckResponse(
            analysisId=str(uuid4()),
            status="no_transcript",
            mode="live",
            warnings=[detail],
        )

    try:
        request.transcript = await asyncio.wait_for(
            asyncio.to_thread(fetch_english_transcript, request.video.id),
            timeout=TRANSCRIPT_TIMEOUT_SECONDS,
        )
    except TranscriptUnavailable:
        return unavailable(NO_TRANSCRIPT)
    except asyncio.TimeoutError:
        return unavailable(
            "YouTube did not return captions in time. Captions are normally read in your "
            "browser; this fallback is often throttled."
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not fetch the YouTube transcript.") from exc
    return None


@app.post("/api/v1/check", response_model=CheckResponse)
async def check_video(request: CheckRequest) -> CheckResponse:
    early = await _ensure_transcript(request)
    if early is not None:
        return early

    if settings().demo_mode:
        return load_demo_response()

    try:
        return await run_pipeline(request)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Fact-checking failed before producing a result.") from exc


@app.post("/api/v1/check/stream")
async def check_video_stream(request: CheckRequest) -> StreamingResponse:
    """Server-sent events: status changes and claims as each one is decided.

    The full pipeline takes long enough that a single blocking response would
    look frozen, so results are pushed to the panel as they resolve.
    """

    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def emit(event: dict) -> None:
            await queue.put(event)

        async def run() -> None:
            try:
                early = await _ensure_transcript(request)
                if early is not None:
                    await queue.put({"type": "complete", "response": early.model_dump(mode="json")})
                    return

                if settings().demo_mode:
                    await queue.put(
                        {"type": "complete", "response": load_demo_response().model_dump(mode="json")}
                    )
                    return

                response = await run_pipeline(request, emit)
                await queue.put({"type": "complete", "response": response.model_dump(mode="json")})
            except Exception as exc:
                await queue.put({"type": "error", "message": str(exc)})
            finally:
                await queue.put(None)

        worker = asyncio.create_task(run())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            worker.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/v1/check/text", response_model=CheckResponse)
async def check_text(request: TextCheckRequest) -> CheckResponse:
    # Video fixtures would imply a verdict about unrelated selected text.
    if settings().demo_mode:
        return CheckResponse(analysisId=str(uuid4()), status="failed", mode="demo",
                             warnings=["Text checking requires live mode. Video demo results are not used for selections."])
    try:
        return await run_text_pipeline(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Text checking failed.") from exc


@app.post("/api/v1/check/text/stream")
async def check_text_stream(request: TextCheckRequest) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def emit(event: dict) -> None:
            await queue.put(event)

        async def run() -> None:
            try:
                if settings().demo_mode:
                    response = await check_text(request)
                else:
                    response = await run_text_pipeline(request, emit)
                await emit({"type": "complete", "response": response.model_dump(mode="json")})
            except Exception:
                await emit({"type": "error", "message": "Text checking failed. Please try again."})
            finally:
                await queue.put(None)

        worker = asyncio.create_task(run())
        try:
            while (event := await queue.get()) is not None:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

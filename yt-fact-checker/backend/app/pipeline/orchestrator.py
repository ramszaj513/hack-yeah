"""Pipeline assembly.

    transcript -> extract -> anchor -> route -> retrieve -> adjudicate
               -> refute -> verify citations -> emit

Claims are processed concurrently and emitted as each one finishes, so the side
panel can fill in progressively instead of waiting on the slowest claim.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable
from uuid import uuid4

from app.config import settings
from app.models.schemas import (
    CheckRequest,
    CheckResponse,
    Claim,
    Context,
    TranscriptSegment,
    UnverifiedReason,
    Verdict,
)
from app.pipeline.anchoring import anchor_quote
from app.pipeline.extraction import ExtractedClaim, extract_claims
from app.pipeline.llm import LLMUnavailable
from app.pipeline.sources import gather_evidence
from app.pipeline.sources.base import ClaimContext
from app.pipeline.verdict import adjudicate
from app.pipeline.verification import verify_citations


Emit = Callable[[dict], Awaitable[None]]

MAX_CONCURRENT_CLAIMS = 6


async def _noop(_: dict) -> None:
    return None


async def _process_claim(
    extracted: ExtractedClaim,
    segments: list[TranscriptSegment],
    semaphore: asyncio.Semaphore,
) -> Claim | None:
    anchor = anchor_quote(extracted.quote, segments)
    if anchor is None:
        # The quote is not in the transcript, so the claim was invented.
        return None

    context = ClaimContext(
        claim=extracted.claim,
        country=extracted.country,
        timeframe=extracted.timeframe,
    )

    async with semaphore:
        retrieval = await gather_evidence(context, extracted.claim_type)

        if not retrieval.docs:
            reason = (
                UnverifiedReason.PROVIDER_ERROR
                if retrieval.all_failed
                else UnverifiedReason.NO_EVIDENCE_FOUND
            )
            basis = (
                "Every evidence provider failed for this claim, so it was not assessed."
                if retrieval.all_failed
                else "No source addressing this claim was found. That is not evidence the claim is false."
            )
            claim = Claim(
                text=extracted.claim,
                quote=extracted.quote,
                startSeconds=anchor.startSeconds,
                endSeconds=anchor.endSeconds,
                verdict=Verdict.COULDNT_VERIFY,
                claimType=extracted.claim_type,
                unverifiedReason=reason,
                basis=basis,
                evidence=[],
                context=Context(country=extracted.country, timeframe=extracted.timeframe),
            )
            return claim

        try:
            # Adjudication and refutation run on the stronger model: extraction
            # is a structural task, but deciding what the evidence actually
            # establishes is where capability shows up in the output.
            result = await adjudicate(
                context,
                retrieval.docs,
                model=settings().openai_reasoning_model,
                refute=settings().enable_refutation_pass,
            )
        except LLMUnavailable as exc:
            return Claim(
                text=extracted.claim,
                quote=extracted.quote,
                startSeconds=anchor.startSeconds,
                endSeconds=anchor.endSeconds,
                verdict=Verdict.COULDNT_VERIFY,
                claimType=extracted.claim_type,
                unverifiedReason=UnverifiedReason.PROVIDER_ERROR,
                basis=f"The adjudication step was unavailable: {exc}",
                evidence=[],
                context=Context(country=extracted.country, timeframe=extracted.timeframe),
            )

    claim = Claim(
        text=extracted.claim,
        quote=extracted.quote,
        startSeconds=anchor.startSeconds,
        endSeconds=anchor.endSeconds,
        verdict=result.verdict,
        claimType=extracted.claim_type,
        unverifiedReason=result.unverified_reason,
        confidence=result.confidence,
        basis=result.basis,
        evidence=result.evidence,
        context=Context(country=extracted.country, timeframe=extracted.timeframe),
    )

    if settings().enable_citation_verification:
        claim = await verify_citations(claim)

    return claim


async def run_pipeline(request: CheckRequest, emit: Emit | None = None) -> CheckResponse:
    send = emit or _noop
    config = settings()
    analysis_id = str(uuid4())
    warnings: list[str] = []

    segments = request.transcript
    if not segments:
        return CheckResponse(
            analysisId=analysis_id,
            status="no_transcript",
            warnings=["No usable transcript was supplied."],
        )

    if len(segments) > config.max_transcript_segments:
        kept = config.max_transcript_segments
        cutoff = segments[kept - 1].start
        warnings.append(
            f"This video is long, so only the first {int(cutoff // 60)} minutes were analysed."
        )
        segments = segments[:kept]

    if not config.llm_enabled:
        return CheckResponse(
            analysisId=analysis_id,
            status="failed",
            warnings=["No model provider is configured, so no claim can be checked."],
        )

    await send({"type": "status", "status": "extracting_claims"})

    try:
        extracted = await extract_claims(segments, request.video)
    except LLMUnavailable as exc:
        return CheckResponse(
            analysisId=analysis_id,
            status="failed",
            warnings=[f"Claim extraction failed: {exc}"],
        )

    if not extracted:
        return CheckResponse(
            analysisId=analysis_id,
            status="no_claims",
            warnings=["No checkable factual claims were found in this video."],
        )

    await send({"type": "status", "status": "gathering_evidence"})

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CLAIMS)
    tasks = [
        asyncio.create_task(_process_claim(item, segments, semaphore))
        for item in extracted
    ]

    claims: list[Claim] = []
    dropped = 0

    for future in asyncio.as_completed(tasks):
        try:
            claim = await future
        except Exception:
            dropped += 1
            continue
        if claim is None:
            dropped += 1
            continue
        claims.append(claim)
        await send({"type": "claim", "claim": claim.model_dump(mode="json")})

    if dropped:
        warnings.append(
            f"{dropped} candidate claim(s) were discarded because they could not be traced "
            "back to the transcript or failed to process."
        )

    claims.sort(key=lambda item: item.startSeconds)

    await send({"type": "status", "status": "reviewing_results"})

    return CheckResponse(
        analysisId=analysis_id,
        status="complete",
        mode="live",
        claims=claims,
        warnings=warnings,
    )

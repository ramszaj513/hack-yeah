"""Pipeline assembly.

    transcript -> extract -> anchor -> route -> retrieve -> adjudicate
               -> refute -> verify citations -> emit

Claims are processed concurrently and emitted as each one finishes, so the side
panel can fill in progressively instead of waiting on the slowest claim.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re
from typing import Awaitable, Callable
from uuid import uuid4

from app.config import settings
from app.models.schemas import (
    CheckRequest,
    CheckResponse,
    Claim,
    Context,
    Signal,
    TranscriptSegment,
    UnverifiedReason,
    Verdict,
    VideoMetadata,
    TextCheckRequest,
)
from app.pipeline.anchoring import Anchor, anchor_quote
from app.pipeline.extraction import ExtractedClaim, extract_claims
from app.pipeline.rhetoric import detect_signals
from app.pipeline.llm import LLMUnavailable
from app.pipeline.sources import Retrieval, gather_evidence
from app.pipeline.sources.base import ClaimContext
from app.pipeline.verdict import adjudicate
from app.pipeline.verification import verify_citations, verify_retrieved


Emit = Callable[[dict], Awaitable[None]]

MAX_CONCURRENT_CLAIMS = 6

# How much of a claim's vocabulary a pooled source must share before it is
# offered to that claim as extra evidence.
POOL_MIN_OVERLAP = 0.3
POOL_EXTRA_DOCS = 3

_WORD = re.compile(r"[a-z0-9]+")


async def _noop(_: dict) -> None:
    return None


@dataclass
class Prepared:
    """A claim with its own evidence, before anything has been decided."""

    extracted: ExtractedClaim
    anchor: Anchor
    context: ClaimContext
    retrieval: Retrieval


def _unresolved(prepared: Prepared, reason: UnverifiedReason, basis: str) -> Claim:
    item = prepared.extracted
    return Claim(
        text=item.claim,
        quote=item.quote,
        startSeconds=prepared.anchor.startSeconds,
        endSeconds=prepared.anchor.endSeconds,
        verdict=Verdict.COULDNT_VERIFY,
        claimType=item.claim_type,
        unverifiedReason=reason,
        basis=basis,
        evidence=[],
        context=Context(country=item.country, timeframe=item.timeframe),
    )


async def _prepare(
    extracted: ExtractedClaim,
    segments: list[TranscriptSegment],
    semaphore: asyncio.Semaphore,
) -> Prepared | None:
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
        # Check quotes before anything is decided on them, not after.
        if settings().enable_citation_verification:
            await verify_retrieved(retrieval.docs)
    return Prepared(extracted=extracted, anchor=anchor, context=context, retrieval=retrieval)


def _relevant_from_pool(context: ClaimContext, own: list, pool: list) -> list:
    """Lend a claim the sources its neighbours found.

    Retrieval runs per claim, so two claims about the same episode can end up
    with different sources and reach contradictory verdicts — one citing a
    passage the other was never shown. Pooling what the whole video turned up
    lets each claim see the same material.
    """
    seen = {doc.url.rstrip("/") for doc in own}
    terms = {word for word in _WORD.findall(context.claim.lower()) if len(word) > 3}
    if not terms:
        return []

    scored: list[tuple[float, object]] = []
    for doc in pool:
        if doc.url.rstrip("/") in seen:
            continue
        haystack = set(_WORD.findall(f"{doc.title} {doc.snippet}".lower()))
        if not haystack:
            continue
        overlap = len(terms & haystack) / len(terms)
        if overlap >= POOL_MIN_OVERLAP:
            scored.append((overlap, doc))

    scored.sort(key=lambda row: row[0], reverse=True)
    return [doc for _, doc in scored[:POOL_EXTRA_DOCS]]


async def _decide(prepared: Prepared, pool: list, semaphore: asyncio.Semaphore) -> Claim:
    item = prepared.extracted
    retrieval = prepared.retrieval

    docs = list(retrieval.docs) + _relevant_from_pool(prepared.context, retrieval.docs, pool)

    if not docs:
        return _unresolved(
            prepared,
            UnverifiedReason.PROVIDER_ERROR if retrieval.all_failed else UnverifiedReason.NO_EVIDENCE_FOUND,
            "Every evidence provider failed for this claim, so it was not assessed."
            if retrieval.all_failed
            else "No source addressing this claim was found. That is not evidence the claim is false.",
        )

    async with semaphore:
        try:
            # Adjudication and refutation run on the stronger model: extraction
            # is a structural task, but deciding what the evidence actually
            # establishes is where capability shows up in the output.
            result = await adjudicate(
                prepared.context,
                docs,
                model=settings().openai_reasoning_model,
                refute=settings().enable_refutation_pass,
            )
        except LLMUnavailable as exc:
            return _unresolved(
                prepared,
                UnverifiedReason.PROVIDER_ERROR,
                f"The adjudication step was unavailable: {exc}",
            )

    claim = Claim(
        text=item.claim,
        quote=item.quote,
        startSeconds=prepared.anchor.startSeconds,
        endSeconds=prepared.anchor.endSeconds,
        verdict=result.verdict,
        claimType=item.claim_type,
        unverifiedReason=result.unverified_reason,
        confidence=result.confidence,
        basis=result.basis,
        evidence=result.evidence,
        context=Context(country=item.country, timeframe=item.timeframe),
    )

    if settings().enable_citation_verification:
        claim = await verify_citations(claim)

    return claim


async def _collect_signals(
    segments: list[TranscriptSegment],
    video: VideoMetadata,
    send: Emit,
    text_context: str | None = None,
) -> list[Signal]:
    """Review rhetoric and anchor each signal, emitting as they resolve."""
    try:
        detected = await detect_signals(segments, video, text_context)
    except LLMUnavailable:
        return []

    signals: list[Signal] = []
    for item in detected:
        anchor = anchor_quote(item.quote, segments)
        # Same gate as a claim: a passage that is not in the transcript was
        # imagined, and must not be marked on the timeline.
        if anchor is None:
            continue
        signal = Signal(
            quote=item.quote,
            startSeconds=anchor.startSeconds,
            endSeconds=anchor.endSeconds,
            technique=item.technique,
            severity=item.severity,
            note=item.note,
        )
        signals.append(signal)
        await send({"type": "signal", "signal": signal.model_dump(mode="json")})

    signals.sort(key=lambda item: item.startSeconds)
    return signals


async def run_pipeline(request: CheckRequest, emit: Emit | None = None, *, text_context: str | None = None) -> CheckResponse:
    tasks: list[asyncio.Task] = []
    try:
        return await _run_pipeline(request, emit, text_context=text_context, owned_tasks=tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _run_pipeline(request: CheckRequest, emit: Emit | None = None, *, text_context: str | None, owned_tasks: list[asyncio.Task]) -> CheckResponse:
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

    # Rhetorical review needs no retrieval, so it runs alongside the factual
    # pass rather than adding to the wait.
    signals_task = asyncio.create_task(_collect_signals(segments, request.video, send, text_context))
    owned_tasks.append(signals_task)

    try:
        extracted = await extract_claims(segments, request.video, text_context)
    except LLMUnavailable as exc:
        signals_task.cancel()
        await asyncio.gather(signals_task, return_exceptions=True)
        return CheckResponse(
            analysisId=analysis_id,
            status="failed",
            warnings=[f"Claim extraction failed: {exc}"],
        )

    if not extracted:
        return CheckResponse(
            analysisId=analysis_id,
            status="no_claims",
            signals=await signals_task,
            warnings=["No checkable factual claims were found in this selection." if text_context is not None else "No checkable factual claims were found in this video."],
        )

    await send({"type": "status", "status": "gathering_evidence"})

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CLAIMS)
    claims: list[Claim] = []
    dropped = 0

    # Phase one: gather evidence for every claim, then pool it. Claims are not
    # decided yet, because a claim judged before its neighbours have searched
    # can contradict one judged after them.
    prepared: list[Prepared] = []
    total = len(extracted)
    await send({"type": "progress", "stage": "evidence", "done": 0, "total": total})

    # Reported one by one rather than awaited in a block: gathering evidence for
    # a long video takes minutes, and a status line that never moves for that
    # long is indistinguishable from a hang.
    gathering = [asyncio.create_task(_prepare(item, segments, semaphore)) for item in extracted]
    owned_tasks.extend(gathering)
    for future in asyncio.as_completed(gathering):
        try:
            result = await future
        except Exception:
            result = None
        if result is None:
            dropped += 1
        else:
            prepared.append(result)
        await send({
            "type": "progress",
            "stage": "evidence",
            "done": len(prepared) + dropped,
            "total": total,
        })

    pool = []
    pooled_urls: set[str] = set()
    for item in prepared:
        for doc in item.retrieval.docs:
            url = doc.url.rstrip("/")
            if url not in pooled_urls:
                pooled_urls.add(url)
                pool.append(doc)

    await send({"type": "status", "status": "reviewing_results"})

    # Phase two: decide each claim against its own evidence plus whatever the
    # pool adds, streaming results as they land.
    tasks = [asyncio.create_task(_decide(item, pool, semaphore)) for item in prepared]
    owned_tasks.extend(tasks)
    decided = 0
    await send({"type": "progress", "stage": "verdicts", "done": 0, "total": len(prepared)})

    for future in asyncio.as_completed(tasks):
        try:
            claim = await future
        except Exception:
            dropped += 1
            continue
        claims.append(claim)
        decided += 1
        await send({"type": "claim", "claim": claim.model_dump(mode="json")})
        await send({
            "type": "progress",
            "stage": "verdicts",
            "done": decided,
            "total": len(prepared),
        })

    if dropped:
        warnings.append(
            f"{dropped} candidate claim(s) were discarded because they could not be traced "
            "back to the transcript or failed to process."
        )

    claims.sort(key=lambda item: item.startSeconds)

    return CheckResponse(
        analysisId=analysis_id,
        status="complete",
        mode="live",
        claims=claims,
        signals=await signals_task,
        warnings=warnings,
    )


async def run_text_pipeline(request: TextCheckRequest, emit: Emit | None = None) -> CheckResponse:
    # Internal adapter reuses retrieval, adjudication and quote verification.
    # Only selected text becomes anchorable evidence; surrounding context cannot.
    adapted = CheckRequest(
        video=VideoMetadata(id="text-selection", title=request.pageTitle, language="auto"),
        url=str(request.pageUrl or ""),
        transcript=[TranscriptSegment(text=request.text, start=0, duration=0)],
    )
    response = await run_pipeline(adapted, emit, text_context=request.context)
    response.warnings.append("Only the selected fragment was analysed; surrounding context may change its meaning.")
    return response

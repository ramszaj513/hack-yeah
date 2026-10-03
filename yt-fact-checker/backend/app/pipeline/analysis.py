from uuid import uuid4

from app.models.schemas import CheckRequest, CheckResponse, Claim, Verdict
from app.pipeline.citations import validate_claim_citations
from app.pipeline.claims import extract_candidate_claims
from app.pipeline.context import resolve_context
from app.pipeline.evidence import EvidenceProvider


async def analyze_live(request: CheckRequest, provider: EvidenceProvider | None) -> CheckResponse:
    if not request.transcript:
        return CheckResponse(analysisId=str(uuid4()), status="no_transcript", warnings=["No usable transcript was supplied."])

    candidates = extract_candidate_claims(request.transcript)
    if not candidates:
        return CheckResponse(analysisId=str(uuid4()), status="no_claims", warnings=["No checkable factual claims were found."])

    claims: list[Claim] = []
    for candidate in candidates:
        context, needs_context = resolve_context(candidate.text, request.video)
        evidence = []
        verdict = Verdict.COULDNT_VERIFY
        basis = "No reliable evidence provider is configured for this claim."
        if needs_context:
            verdict = Verdict.CONTEXT_NEEDED
            basis = "The claim refers to an unspecified government, law, economy, or country. More context is needed before checking it."
        elif provider:
            try:
                result = await provider.search(candidate.text, context.model_dump())
                evidence = result.evidence
                verdict = result.suggested_verdict or verdict
                if evidence and not result.basis:
                    basis = "A fact-checking source was found. Open the source and verify the review in context."
                elif result.basis:
                    basis = result.basis
                else:
                    basis = "No reliable matching source was found."
            except Exception:
                basis = "The evidence provider was unavailable; the claim was not assigned a definitive verdict."

        claims.append(
            validate_claim_citations(
                Claim(
                    text=candidate.text,
                    startSeconds=candidate.start,
                    endSeconds=candidate.end,
                    verdict=verdict,
                    basis=basis,
                    evidence=evidence,
                    context=context,
                )
            )
        )

    return CheckResponse(
        analysisId=str(uuid4()),
        status="complete",
        mode="live",
        claims=claims,
        warnings=["Live mode is conservative: claims are not marked true or false without validated evidence."],
    )

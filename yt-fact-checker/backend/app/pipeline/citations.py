from urllib.parse import urlparse

from app.models.schemas import Claim, Evidence, Verdict


CONCERNING_VERDICTS = {
    Verdict.FALSE,
    Verdict.POTENTIALLY_FALSE,
    Verdict.MISLEADING,
}


def is_valid_evidence_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_claim_citations(claim: Claim) -> Claim:
    """Make citation quality a hard boundary for definitive verdicts."""
    valid_evidence = [item for item in claim.evidence if is_valid_evidence_url(str(item.url))]
    claim.evidence = valid_evidence

    if claim.verdict in {
        Verdict.FALSE,
        Verdict.POTENTIALLY_FALSE,
        Verdict.MISLEADING,
        Verdict.SUPPORTED,
    } and not valid_evidence:
        claim.verdict = Verdict.COULDNT_VERIFY
        claim.basis = "No usable evidence link was available, so this claim was not assigned a definitive verdict."
    return claim

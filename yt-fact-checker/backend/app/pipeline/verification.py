"""Citation verification.

The model claims a source says something. This fetches the source and checks
whether those words are actually on the page. It is plain string matching, not
another model call, which is exactly why it is worth having: it cannot be
talked out of its answer.

A fetch that fails (paywall, bot blocking, timeout) is recorded as *unknown*
rather than *false*. Only a page we successfully read and that does not contain
the quoted words counts against the claim.
"""

from __future__ import annotations

import asyncio
import html
import re

from app.models.schemas import Claim, Evidence, UnverifiedReason, Verdict
from app.pipeline.anchoring import quote_appears_in
from app.pipeline.sources.base import http_client


DEFINITIVE = {Verdict.FALSE, Verdict.POTENTIALLY_FALSE, Verdict.MISLEADING, Verdict.SUPPORTED}

# Below this, we assume we failed to read the page rather than that the quote
# is missing from it.
MIN_READABLE_WORDS = 120

_SCRIPT = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def html_to_text(markup: str) -> str:
    without_scripts = _SCRIPT.sub(" ", markup)
    return html.unescape(_TAG.sub(" ", without_scripts))


async def _verify_one(evidence: Evidence) -> None:
    if not evidence.snippet.strip():
        evidence.quoteVerified = None
        return

    try:
        async with http_client() as client:
            response = await client.get(
                str(evidence.url),
                headers={"Accept": "text/html,application/xhtml+xml,*/*"},
            )
            if response.status_code >= 400:
                evidence.quoteVerified = None
                return
            body = response.text
    except Exception:
        evidence.quoteVerified = None
        return

    text = html_to_text(body)

    # A page we could not actually read — JS-rendered shells, consent walls,
    # PDFs — yields almost no text. Calling that "quote not found" would be a
    # claim about the page we are not entitled to make, and it downgrades
    # correct verdicts, so it is recorded as unknown instead.
    if len(text.split()) < MIN_READABLE_WORDS:
        evidence.quoteVerified = None
        return

    evidence.quoteVerified = quote_appears_in(evidence.snippet, text)


async def verify_citations(claim: Claim) -> Claim:
    """Check every cited quote, then downgrade the verdict if none survive."""
    if not claim.evidence:
        return claim

    await asyncio.gather(*(_verify_one(item) for item in claim.evidence), return_exceptions=True)

    checked = [item for item in claim.evidence if item.quoteVerified is not None]
    verified = [item for item in checked if item.quoteVerified]

    # Sort verified citations first so the panel leads with what held up.
    claim.evidence.sort(key=lambda item: (item.quoteVerified is not True, item.tier))

    if claim.verdict in DEFINITIVE and checked and not verified:
        claim.verdict = Verdict.COULDNT_VERIFY
        claim.unverifiedReason = UnverifiedReason.CITATION_UNVERIFIABLE
        claim.confidence = min(claim.confidence, 0.3)
        claim.basis = (
            "The cited sources were retrieved, but none of them contained the quoted passage "
            "this verdict relied on, so no definitive verdict is reported. " + claim.basis
        )[:3000]

    return claim

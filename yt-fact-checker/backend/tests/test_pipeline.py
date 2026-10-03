"""Tests for the parts that must hold without any model in the loop.

These cover the mechanical guarantees the product's trustworthiness rests on:
a claim must be traceable to the transcript, and a citation must be traceable
to the page it points at.
"""

import pytest

from app.models.schemas import Claim, Evidence, TranscriptSegment, UnverifiedReason, Verdict
from app.pipeline.anchoring import anchor_quote, quote_appears_in
from app.pipeline.extraction import ExtractedClaim, _deduplicate, chunk_segments
from app.pipeline.sources import ROUTES
from app.pipeline.verdict import _to_evidence
from app.pipeline.verification import html_to_text, verify_citations


SEGMENTS = [
    TranscriptSegment(text="welcome back to the channel today", start=0, duration=3),
    TranscriptSegment(text="the unemployment rate in poland fell to", start=3, duration=3),
    TranscriptSegment(text="five percent last year which is a record", start=6, duration=3),
    TranscriptSegment(text="and thats great news for everyone", start=9, duration=3),
]


def test_anchor_returns_real_timestamps_not_estimates() -> None:
    anchor = anchor_quote("the unemployment rate in poland fell to five percent last year", SEGMENTS)
    assert anchor is not None
    assert anchor.score == 1.0
    assert anchor.startSeconds == 3.0
    assert anchor.endSeconds == 9.0


def test_anchor_rejects_a_quote_that_was_never_said() -> None:
    # The hallucination gate: an invented claim cannot be placed on the timeline.
    assert anchor_quote("the moon landing was filmed in a studio in arizona", SEGMENTS) is None


def test_anchor_tolerates_punctuation_and_case() -> None:
    assert anchor_quote("The unemployment rate in Poland FELL to five percent!", SEGMENTS) is not None


def test_quote_appears_in_detects_absent_quotes() -> None:
    assert quote_appears_in("five percent last year", "It fell to five percent last year, officials said.")
    assert not quote_appears_in("five percent last year", "An article about growing tomatoes indoors.")


def test_chunking_handles_unpunctuated_captions() -> None:
    # Auto-generated captions often carry no '.' at all; chunking must not
    # depend on sentence punctuation to make progress.
    segments = [TranscriptSegment(text="word " * 20, start=float(i * 5), duration=5.0) for i in range(300)]
    chunks = chunk_segments(segments)
    assert len(chunks) > 1
    assert sum(len(chunk) for chunk in chunks) == len(segments)


def test_duplicate_claims_are_collapsed() -> None:
    from app.models.schemas import ClaimType

    def claim(text: str) -> ExtractedClaim:
        return ExtractedClaim("quote", text, ClaimType.GENERAL, None, None)

    claims = [
        # The same point restated, as speakers routinely do. Trailing
        # punctuation must not make these look like different claims.
        claim("Unemployment in Poland fell to five percent last year."),
        claim("Last year unemployment in Poland fell to five percent."),
        claim("The capital of Australia is Canberra."),
    ]
    assert len(_deduplicate(claims)) == 2


def test_citations_must_point_at_a_retrieved_source() -> None:
    from app.pipeline.sources.base import RetrievedDoc

    docs = [RetrievedDoc(title="Only source", publisher="X", url="https://example.com/a", sourceType="web")]
    # Index 7 does not exist; a model citing it must not produce evidence.
    built = _to_evidence(docs, [{"source_index": 7, "quote": "anything", "stance": "supports"}])
    assert built == []


def test_html_to_text_strips_scripts() -> None:
    text = html_to_text("<html><script>var x = 'hidden';</script><p>Visible claim text</p></html>")
    assert "Visible claim text" in text
    assert "hidden" not in text


@pytest.mark.asyncio
async def test_unverifiable_citations_downgrade_a_definitive_verdict(monkeypatch) -> None:
    claim = Claim(
        text="A definitive sounding claim.",
        startSeconds=0,
        endSeconds=1,
        verdict=Verdict.FALSE,
        basis="Sources say so.",
        confidence=0.9,
        evidence=[
            Evidence(
                title="Source",
                publisher="Example",
                url="https://example.com/a",
                sourceType="journalism",
                snippet="a sentence that is not actually on the page",
            )
        ],
    )

    async def fake_verify(evidence):
        evidence.quoteVerified = False

    monkeypatch.setattr("app.pipeline.verification._verify_one", fake_verify)
    result = await verify_citations(claim)

    assert result.verdict == Verdict.COULDNT_VERIFY
    assert result.unverifiedReason == UnverifiedReason.CITATION_UNVERIFIABLE


@pytest.mark.asyncio
async def test_unreachable_pages_do_not_punish_the_claim(monkeypatch) -> None:
    claim = Claim(
        text="A definitive sounding claim.",
        startSeconds=0,
        endSeconds=1,
        verdict=Verdict.FALSE,
        basis="Sources say so.",
        evidence=[
            Evidence(
                title="Paywalled",
                publisher="Example",
                url="https://example.com/a",
                sourceType="journalism",
                snippet="a quoted sentence",
            )
        ],
    )

    async def fake_verify(evidence):
        evidence.quoteVerified = None  # fetch failed, not a fabrication

    monkeypatch.setattr("app.pipeline.verification._verify_one", fake_verify)
    result = await verify_citations(claim)

    assert result.verdict == Verdict.FALSE


def test_scientific_claims_reach_the_literature() -> None:
    from app.models.schemas import ClaimType

    assert "europe_pmc" in ROUTES[ClaimType.SCIENTIFIC]
    assert "google_fact_check" in ROUTES[ClaimType.POLITICAL]

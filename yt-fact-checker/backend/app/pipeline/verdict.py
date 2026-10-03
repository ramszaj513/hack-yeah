"""Per-claim adjudication.

One call judges one claim against one evidence set, and may only cite sources
from that set. A second, adversarial call then tries to knock the verdict down.
Single-pass judgements are confidently wrong often enough that the refutation
step earns its cost on exactly the claims that matter most.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.schemas import Evidence, UnverifiedReason, Verdict
from app.pipeline.llm import LLMUnavailable, structured_call
from app.pipeline.sources.base import ClaimContext, RetrievedDoc


VERDICT_VALUES = [
    "false",
    "potentially_false",
    "misleading",
    "supported",
    "context_needed",
    "couldnt_verify",
]

REASON_VALUES = [
    "",
    "no_evidence_found",
    "sources_conflict",
    "evidence_not_specific",
    "citation_unverifiable",
    "provider_error",
    "claim_ambiguous",
]


VERDICT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "confidence", "basis", "unverified_reason", "citations"],
    "properties": {
        "verdict": {"type": "string", "enum": VERDICT_VALUES},
        "confidence": {"type": "number", "description": "0 to 1."},
        "basis": {"type": "string", "description": "Two or three sentences explaining the verdict."},
        "unverified_reason": {"type": "string", "enum": REASON_VALUES},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source_index", "quote", "stance"],
                "properties": {
                    "source_index": {"type": "integer"},
                    "quote": {
                        "type": "string",
                        "description": "Sentence copied verbatim from that source's excerpt.",
                    },
                    "stance": {"type": "string", "enum": ["supports", "contradicts", "context"]},
                },
            },
        },
    },
}


REFUTATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict_holds", "revised_verdict", "reason"],
    "properties": {
        "verdict_holds": {"type": "boolean"},
        "revised_verdict": {"type": "string", "enum": VERDICT_VALUES},
        "reason": {"type": "string"},
    },
}


VERDICT_PROMPT = """You are adjudicating one factual claim against a fixed evidence set.

Claim: {claim}
{context}

Evidence:
{evidence}

Rules:
- Judge ONLY on the evidence above. You have no other knowledge for this task.
- Cite sources by their index. Every citation's `quote` must be copied verbatim
  from that source's excerpt. Do not paraphrase and do not cite a source whose
  excerpt does not actually mention the claim.
- Absence of evidence is not evidence of falsity. If nothing here addresses the
  claim, return couldnt_verify with unverified_reason=no_evidence_found.
- If sources genuinely disagree, return couldnt_verify with
  unverified_reason=sources_conflict rather than picking a side.
- If the evidence is about a different country, period or population than the
  claim, return context_needed or couldnt_verify with
  unverified_reason=evidence_not_specific.
- Use `misleading` when the claim is literally defensible but omits context that
  changes its meaning.
- Use `false` only when strong evidence directly contradicts it;
  `potentially_false` when evidence leans against it without being decisive.
- Set unverified_reason to "" for definitive verdicts.

Verdicts: {verdicts}
"""


REFUTATION_PROMPT = """Check this verdict for material defects.

Claim: {claim}
Proposed verdict: {verdict}
Stated basis: {basis}

Evidence:
{evidence}

The verdict STANDS by default. Overturn it only for a defect you can name that
would change what a reader concludes:
- the cited excerpts do not actually establish what the basis says they do;
- the evidence concerns a different country, period, population or definition
  than the claim;
- a definitive verdict rests on a single weak source;
- contradicting evidence in the set was ignored.

Do NOT overturn a verdict because:
- the claim uses loose or informal wording ("simple", "basically", "a lot of"),
  as long as its substance is right;
- the claim omits precision that does not change whether it is true;
- the evidence states the fact in different words than the claim does;
- you personally would have phrased the basis differently.

A plainly correct claim backed by clear evidence must keep its verdict. Hedging
a well-evidenced verdict into couldnt_verify is itself a failure: it tells the
viewer nothing and hides a real answer behind false caution.
"""


@dataclass
class Adjudication:
    verdict: Verdict
    confidence: float
    basis: str
    unverified_reason: UnverifiedReason | None
    evidence: list[Evidence]


def render_evidence(docs: list[RetrievedDoc]) -> str:
    if not docs:
        return "(no sources were retrieved)"
    blocks = []
    for index, doc in enumerate(docs):
        blocks.append(
            f"[{index}] {doc.title}\n"
            f"    publisher: {doc.publisher} ({doc.sourceType})\n"
            f"    url: {doc.url}\n"
            f"    excerpt: {doc.snippet or '(no excerpt available)'}"
        )
    return "\n\n".join(blocks)


def _context_lines(context: ClaimContext) -> str:
    lines = []
    if context.country:
        lines.append(f"Country: {context.country}")
    if context.timeframe:
        lines.append(f"Timeframe: {context.timeframe}")
    return "\n".join(lines)


def _to_evidence(docs: list[RetrievedDoc], citations: list[dict]) -> list[Evidence]:
    """Build evidence entries strictly from cited, in-range sources."""
    built: list[Evidence] = []
    used: set[int] = set()

    for citation in citations:
        index = citation.get("source_index")
        if not isinstance(index, int) or not 0 <= index < len(docs) or index in used:
            continue
        used.add(index)
        doc = docs[index]
        try:
            built.append(
                Evidence(
                    title=doc.title,
                    publisher=doc.publisher,
                    url=doc.url,
                    sourceType=doc.sourceType,
                    snippet=(citation.get("quote") or "")[:2000],
                    supports=citation.get("stance") or "supports",
                )
            )
        except Exception:
            continue
    return built


async def adjudicate(
    context: ClaimContext,
    docs: list[RetrievedDoc],
    *,
    model: str | None = None,
    refute: bool = True,
) -> Adjudication:
    prompt = VERDICT_PROMPT.format(
        claim=context.claim,
        context=_context_lines(context),
        evidence=render_evidence(docs),
        verdicts=", ".join(VERDICT_VALUES),
    )

    payload, _ = await structured_call(
        prompt=prompt,
        schema_name="claim_verdict",
        schema=VERDICT_SCHEMA,
        model=model,
        max_output_tokens=1600,
    )

    try:
        verdict = Verdict(payload.get("verdict", "couldnt_verify"))
    except ValueError:
        verdict = Verdict.COULDNT_VERIFY

    raw_reason = payload.get("unverified_reason") or ""
    try:
        reason = UnverifiedReason(raw_reason) if raw_reason else None
    except ValueError:
        reason = None

    basis = (payload.get("basis") or "").strip() or "No basis was provided for this claim."
    confidence = payload.get("confidence")
    confidence = float(confidence) if isinstance(confidence, (int, float)) else 0.0
    confidence = min(1.0, max(0.0, confidence))

    evidence = _to_evidence(docs, payload.get("citations") or [])

    definitive = verdict in {Verdict.FALSE, Verdict.POTENTIALLY_FALSE, Verdict.MISLEADING, Verdict.SUPPORTED}
    if refute and definitive:
        try:
            challenge, _ = await structured_call(
                prompt=REFUTATION_PROMPT.format(
                    claim=context.claim,
                    verdict=verdict.value,
                    basis=basis,
                    evidence=render_evidence(docs),
                ),
                schema_name="verdict_challenge",
                schema=REFUTATION_SCHEMA,
                model=model,
                max_output_tokens=900,
            )
        except LLMUnavailable:
            challenge = {"verdict_holds": True}

        if not challenge.get("verdict_holds", True):
            try:
                revised = Verdict(challenge.get("revised_verdict", "couldnt_verify"))
            except ValueError:
                revised = Verdict.COULDNT_VERIFY
            note = (challenge.get("reason") or "").strip()
            verdict = revised
            confidence = min(confidence, 0.5)
            basis = f"{basis} On review: {note}" if note else basis
            if revised == Verdict.COULDNT_VERIFY and reason is None:
                reason = UnverifiedReason.EVIDENCE_NOT_SPECIFIC

    return Adjudication(
        verdict=verdict,
        confidence=confidence,
        basis=basis[:3000],
        unverified_reason=reason,
        evidence=evidence,
    )

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
        "basis": {
            "type": "string",
            "description": (
                "At most two sentences, under 300 characters, written for a viewer "
                "skimming a side panel. State what the evidence shows and why that "
                "gives this verdict. Do not restate the claim, do not list the "
                "sources, do not narrate your reasoning process."
            ),
        },
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
        "reason": {
            "type": "string",
            "description": (
                "At most two sentences, under 300 characters. If the verdict is "
                "overturned this replaces the basis shown to the viewer, so state "
                "what the evidence supports — not what the earlier verdict got wrong."
            ),
        },
    },
}


# Static text first, variable text last.
#
# OpenAI caches the longest common PREFIX of a prompt, so the rules below are
# billed at the cached rate on every call after the first. With the claim and
# evidence at the top, as they were, the prefix differed for every claim and
# nothing was ever cached.
VERDICT_PROMPT = """You are adjudicating one factual claim against a fixed evidence set.

Rules:
- Judge ONLY on the evidence above. You have no other knowledge for this task.
- Judge the claim as written, at its own scope. "The first permit for a
  BWRX-300" is not the claim "the first permit for any reactor", and refuting
  the second leaves the first untouched. Do not widen or narrow a claim and
  then disagree with the version you produced.
- When a claim reports what ONE named study, review or meta-analysis found,
  only that study can settle it. Other studies reaching other conclusions do
  not make it false — they study something else, often under different
  conditions. If the excerpts do not cover the study named, return
  couldnt_verify. Reporting a specific finding accurately is not an error just
  because the wider literature is mixed.
- Experimental conditions are part of the population. During exercise is not
  after exercise; dehydrated subjects are not euhydrated ones; a dose or
  formulation is not another one. Evidence from different conditions does not
  contradict the claim, it is simply about something else.
- Before calling a number wrong, convert units and check it is not the same
  quantity expressed differently. Sodium and salt differ by a factor of about
  2.54 — 3.27 g of sodium IS 8.3 g of salt. Grams against milligrams, per day
  against per week, and one currency against another work the same way. A
  conversion is agreement, not contradiction.
- Where a phrase has more than one reading and one of them makes the claim
  absurd, take the reading its audience would. "Polish capital is investing"
  in a story about investors means Polish money, not the city of Warsaw. The
  transcript was translated, so judge the meaning, not the wording.
- Cite sources by their index. Every citation's `quote` must be copied verbatim
  from that source's excerpt. Do not paraphrase and do not cite a source whose
  excerpt does not actually mention the claim.
- A comparison may be settled by combining facts from different sources, as
  long as EACH part is stated outright in a cited excerpt and the final step is
  simple arithmetic or ordering. If one excerpt dates a university to 1096 and
  another dates an empire to 1325, you may conclude the university came first;
  cite both. Requiring a single source to have phrased the whole comparison
  would leave plainly answerable claims unanswered.
  This permits ordering dates, comparing quantities and unit conversion only.
  It does NOT permit inferring an unstated fact, estimating a missing number,
  or assuming two sources are talking about the same thing when they may not
  be. If any part is missing from the excerpts, say so and do not guess.
- Absence of evidence is not evidence of falsity. If nothing here addresses the
  claim, return couldnt_verify with unverified_reason=no_evidence_found.
- Weigh sources by authority, in this order: primary data and official
  statistics, then peer-reviewed research, then established fact-checkers, then
  reference works, then journalism, then general web pages. Use
  unverified_reason=sources_conflict only when sources of COMPARABLE authority
  genuinely disagree. One weak page contradicting several strong ones is not a
  conflict — follow the better evidence and say so in the basis.
- If the claim names no country and no time period but the answer depends on
  one — unemployment, inflation, crime, population, spending — return
  context_needed. Do NOT quietly assume the United States, or any other
  country, and judge the claim against it. This rule outranks the evidence:
  an unanswerable claim stays unanswerable even when the sources are excellent.
- If the evidence is about a genuinely different country, period or population
  than the claim, return context_needed or couldnt_verify with
  unverified_reason=evidence_not_specific. "Genuinely different" means a
  reader would draw a different conclusion — not that the claim rounded a
  number, used a synonym, or named a slightly wider group than the source.
  A source reporting 1,949 arrests supports a claim of "1,948 detained"; a
  source reporting 305 injured police supports "305 police and gendarmes
  injured". Match the substance, not the wording.
- A claim that someone SAID, ALLEGED or REPORTED something is about the
  statement, not about whether the statement is true. If the evidence shows
  the statement was made, the claim is supported.
- Do not refute a claim about what is PLANNED or INTENDED with a document
  about what has been APPROVED, AUTHORISED or BUILT so far. "They plan 26
  reactors" is not contradicted by a permit covering 24: the permit is a
  different fact. The same holds for targets, proposals and applications.
- Mark a citation's stance as "contradicts" only when the source asserts
  something incompatible with the claim. A source that simply does not mention
  the claim, or that says no documentary evidence survives, is not
  contradicting it — use "context". The stance is shown to the viewer as a
  badge, so calling silence a contradiction tells them a source disproves
  something it never addressed.
- When a claim has several parts and the evidence settles some but not others,
  do not call the whole thing false. Say which part holds and return
  context_needed or couldnt_verify for the rest. "He visited Gdansk and Berlin"
  with Berlin confirmed and Gdansk merely undocumented is not a false claim.
- Weigh an excerpt by its status line. One confirmed on its page outranks one
  that was NOT FOUND there, whatever either says and whatever their publishers
  are. Do not let excerpts that failed the check outvote a confirmed one; if
  the only material against a claim failed the check, the claim is not refuted.
- A record that is missing is not a record that refutes. Historical sources are
  incomplete by nature, and "there is no documentary evidence" means the
  question is open, not settled against the claim.
- Never return false or potentially_false for a recent event on the strength of
  evidence that predates it. If the claim is dated and every excerpt is older
  than that date — a standing institutional page, a prior year's results — the
  evidence simply has not caught up. Return couldnt_verify with
  unverified_reason=no_evidence_found. Calling a true report of something that
  just happened "false" is the worst error this system can make.
- Use `misleading` when the claim is literally defensible but omits context that
  changes its meaning.
- Use `false` only when strong evidence directly contradicts it;
  `potentially_false` when evidence leans against it without being decisive.
- Set unverified_reason to "" for definitive verdicts.

Verdicts: false, potentially_false, misleading, supported, context_needed, couldnt_verify

=== Everything above is fixed. The case to decide follows. ===

Claim: {claim}
{context}

Evidence:
{evidence}
"""


REFUTATION_PROMPT = """Check this verdict for material defects.

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
- you personally would have phrased the basis differently;
- a number differs trivially from the source (1,948 against 1,949, "over 400"
  against 400). Speakers round and sources revise. Overturn only when the
  difference changes what a reader would conclude;
- the claim and the source use different words for the same thing ("detained"
  against "arrested", "police" against "police and gendarmes"). Overturn only
  if the substitution actually changes the meaning;
- the claim reports that someone SAID or ALLEGED something. If the evidence
  shows they said it, the claim is supported — whether the allegation itself
  is true is a different claim that was not made here;
- the claim is slightly broader or narrower than the evidence while remaining
  substantially accurate.

context_needed means the claim CANNOT be assessed as stated — a missing
country, a missing period, an ambiguous term. It is not a resting place for a
claim you did assess and found a little imprecise. If the substance checks out,
keep the verdict.

Keep `reason` to one or two sentences. It is shown to a viewer underneath the
basis, not written for another model.

A plainly correct claim backed by clear evidence must keep its verdict. Hedging
a well-evidenced verdict into couldnt_verify is itself a failure: it tells the
viewer nothing and hides a real answer behind false caution.
"""


# A verdict is challenged when it is the kind that goes wrong: thin sourcing,
# weak sourcing, or the model's own hesitancy. Re-litigating a confident
# verdict backed by several good sources does not catch errors — it just
# invites the challenger to manufacture a doubt, which is how plain facts end
# up hedged into uselessness.
STRONG_TIER = 3
CONFIDENT = 0.85


def _worth_challenging(confidence: float, evidence: list[Evidence]) -> bool:
    strong = [item for item in evidence if item.tier <= STRONG_TIER]
    if len(strong) >= 2 and confidence >= CONFIDENT:
        return False
    return True


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
        verified = getattr(doc, "snippetVerified", None)
        if verified is True:
            status = "excerpt CONFIRMED present on the page"
        elif verified is False:
            status = "excerpt NOT FOUND on the page - treat as unreliable"
        elif getattr(doc, "modelReported", False):
            status = "excerpt unchecked (page could not be read)"
        else:
            status = "excerpt supplied directly by the source's own API"
        blocks.append(
            f"[{index}] {doc.title}\n"
            f"    publisher: {doc.publisher} ({doc.sourceType})\n"
            f"    url: {doc.url}\n"
            f"    status: {status}\n"
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
                    snippet=(citation.get("quote") or "")[:600],
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
    )

    payload, _ = await structured_call(
        prompt=prompt,
        schema_name="claim_verdict",
        schema=VERDICT_SCHEMA,
        model=model,
        max_output_tokens=1600,
        cache_key="ytfc-verdict",
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
    if refute and definitive and _worth_challenging(confidence, evidence):
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
                cache_key="ytfc-refute",
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
            # Replace rather than append. The challenge explains the verdict the
            # viewer is actually being shown; keeping the overturned reasoning
            # in front of it doubled the length and contradicted itself.
            basis = note or basis
            if revised == Verdict.COULDNT_VERIFY and reason is None:
                reason = UnverifiedReason.EVIDENCE_NOT_SPECIFIC

    return Adjudication(
        verdict=verdict,
        confidence=confidence,
        basis=basis[:700],
        unverified_reason=reason,
        evidence=evidence,
    )

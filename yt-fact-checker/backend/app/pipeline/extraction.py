"""LLM claim extraction.

Replaces the regex extractor, which split sentences on ``[.!?]`` and therefore
collapsed into a single unusable blob on auto-generated captions — the most
common caption type on YouTube, and one that frequently carries no punctuation
at all.

Two properties make the rest of the pipeline trustworthy:

* every claim carries the **verbatim transcript quote** it came from, so the
  timestamp can be derived deterministically and an invented claim can be
  detected and dropped;
* every claim is **decontextualised** into a standalone sentence, because
  "they spent 40 billion on it last year" cannot be searched for as written.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
import re

from app import cache
from app.config import settings
from app.models.schemas import ClaimType, TranscriptSegment, VideoMetadata
from app.pipeline.llm import LLMUnavailable, structured_call


CHUNK_SECONDS = 420.0
CHUNK_MAX_CHARS = 9000

_WORD = re.compile(r"[a-z0-9]+")


@dataclass
class ExtractedClaim:
    quote: str
    claim: str
    claim_type: ClaimType
    country: str | None
    timeframe: str | None


EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["claims"],
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["quote", "claim", "claim_type", "checkworthy", "country", "timeframe"],
                "properties": {
                    "quote": {
                        "type": "string",
                        "description": "Verbatim span copied from the transcript, 4-40 words.",
                    },
                    "claim": {
                        "type": "string",
                        "description": "Standalone, checkable restatement with pronouns and vague references resolved.",
                    },
                    "claim_type": {
                        "type": "string",
                        "enum": ["definitional", "statistical", "scientific", "historical", "political", "general"],
                    },
                    "checkworthy": {
                        "type": "boolean",
                        "description": "False for opinion, prediction, rhetoric, satire or personal experience.",
                    },
                    "country": {"type": "string", "description": "Country the claim is about, or empty."},
                    "timeframe": {"type": "string", "description": "Year or period the claim is about, or empty."},
                },
            },
        }
    },
}


PROMPT = """You extract checkable factual claims from a YouTube transcript chunk.

Rules:
- Copy `quote` VERBATIM from the transcript. Do not fix grammar, punctuation or
  capitalisation. It must appear character-for-character in the text below, or
  the claim will be discarded.
- Write `claim` as a statement ABOUT THE WORLD that stands entirely on its own.
  A researcher who has never seen this video must be able to check it using
  public sources alone.
- Resolve pronouns ("they", "it") and vague references ("the government",
  "this country") using the video title and surrounding transcript. If the
  transcript is not in English, write the claim in English.
- Resolve relative times — "on Thursday", "four days ago", "last month",
  "recently" — against the VIDEO'S publication date given below, never against
  the day the check is being run and never against a year you associate with
  the subject matter. A video published three weeks ago saying "on Friday"
  means the Friday before IT was published.
- If the publication date is unknown, do not resolve relative times at all.
  Write the claim without a date and leave `timeframe` empty. A confidently
  wrong date makes correct evidence look like it describes a different event,
  and the claim is then reported as false when it is true.
- Never invent a year. A wrong year is worse than no year.
- The claim must NOT refer to the video, the transcript, the speaker, or the
  order things were said in. Those are facts about a recording, not about the
  world, and nothing can verify them.
    BAD : "The video is about commutative rings."
    BAD : "The first example given in the transcript is the integers."
    BAD : "The speaker says vitamin D prevents colds."
    GOOD: "The integers form a commutative ring."
    GOOD: "Vitamin D supplementation prevents the common cold."
  If a sentence carries a checkable fact wrapped in narration, extract the fact
  and discard the narration.
- Set `checkworthy` to false for opinions, predictions, jokes, sarcasm,
  rhetorical questions, personal anecdotes and value judgements. Extract them
  anyway with checkworthy=false rather than silently dropping them.
- Do NOT invent claims that are not stated in this chunk.
- Do not add detail the speaker did not give. If a surname is used without a
  first name, keep it that way — supplying the wrong one makes the claim refer
  to someone who does not exist, and it will come back unverifiable.
- When translating, choose the meaning the speaker intended, not the literal
  word. Polish "kapitał" in a financial context is "capital" in the sense of
  money and investors, never a capital city; "cialo" in mathematics is a
  field, not a body. A literal rendering that changes the meaning turns a
  correct statement into a false one.
- Prefer specific, consequential, verifiable assertions over trivia.
- Return at most the number of claims stated below.

Choosing `claim_type`:
- definitional : mathematics, logic, or a definition true by established
                 convention ("a field is a commutative ring"). Checked against
                 reference works, not research papers.
- scientific   : an empirical finding about the natural world, medicine or
                 health, where the literature is the right authority.
- statistical  : a number, rate or quantity about a population or economy.
- historical   : something that happened at a particular time or place.
- political    : a contested public claim about policy, law or public figures.
- general      : anything else.

=== Everything above is fixed. The material to process follows. ===

Video published: {published}
Today's date (for reference only — do NOT resolve the transcript against it): {today}
Maximum claims for this chunk: {limit}
Video title: {title}

Transcript chunk:
-------------------------
{chunk}
-------------------------
"""


def chunk_segments(segments: list[TranscriptSegment]) -> list[list[TranscriptSegment]]:
    """Split the transcript into time-bounded windows.

    Chunking by time rather than by sentence is what makes unpunctuated
    auto-captions workable, and it lets long videos be processed in parallel
    instead of truncated.
    """
    chunks: list[list[TranscriptSegment]] = []
    current: list[TranscriptSegment] = []
    current_chars = 0
    window_start = segments[0].start if segments else 0.0

    for segment in segments:
        too_long = segment.start - window_start >= CHUNK_SECONDS
        too_big = current_chars + len(segment.text) > CHUNK_MAX_CHARS
        if current and (too_long or too_big):
            chunks.append(current)
            current = []
            current_chars = 0
            window_start = segment.start
        current.append(segment)
        current_chars += len(segment.text) + 1

    if current:
        chunks.append(current)
    return chunks


def render_chunk(chunk: list[TranscriptSegment]) -> str:
    return "\n".join(f"[{int(item.start // 60):02d}:{int(item.start % 60):02d}] {item.text}" for item in chunk)


async def _extract_chunk(chunk: list[TranscriptSegment], video: VideoMetadata, limit: int) -> list[ExtractedClaim]:
    key = cache.key_for("extract", render_chunk(chunk), video.title, limit,
                        date.today().isoformat(), video.publishedAt, settings().openai_model)
    cached = cache.get(key)
    if cached is not None:
        return [ExtractedClaim(quote=i["quote"], claim=i["claim"],
                               claim_type=ClaimType(i["claim_type"]),
                               country=i["country"], timeframe=i["timeframe"]) for i in cached]

    prompt = PROMPT.format(
        limit=limit,
        title=video.title or "(unknown)",
        today=date.today().isoformat(),
        published=video.publishedAt or "unknown — do not resolve relative times",
        chunk=render_chunk(chunk),
    )
    payload, _ = await structured_call(
        prompt=prompt,
        schema_name="claim_extraction",
        schema=EXTRACTION_SCHEMA,
        max_output_tokens=3000,
        cache_key="ytfc-extract",
    )

    results: list[ExtractedClaim] = []
    for item in payload.get("claims", []):
        if not item.get("checkworthy"):
            continue
        quote = (item.get("quote") or "").strip()
        claim = (item.get("claim") or "").strip()
        if not quote or not claim:
            continue
        try:
            claim_type = ClaimType(item.get("claim_type", "general"))
        except ValueError:
            claim_type = ClaimType.GENERAL
        results.append(
            ExtractedClaim(
                quote=quote[:2000],
                claim=claim[:2000],
                claim_type=claim_type,
                country=(item.get("country") or "").strip() or None,
                timeframe=(item.get("timeframe") or "").strip() or None,
            )
        )

    cache.put(key, [{"quote": i.quote, "claim": i.claim, "claim_type": i.claim_type.value,
                     "country": i.country, "timeframe": i.timeframe} for i in results])
    return results


def _deduplicate(claims: list[ExtractedClaim]) -> list[ExtractedClaim]:
    """Drop near-duplicate claims, which repeat when a speaker restates a point."""
    unique: list[ExtractedClaim] = []
    seen: list[set[str]] = []

    for claim in claims:
        # Tokenise rather than split: trailing punctuation would otherwise make
        # "year." and "year" count as different words and hide a duplicate.
        tokens = {word for word in _WORD.findall(claim.claim.lower()) if len(word) > 3}
        if not tokens:
            continue
        duplicate = False
        for previous in seen:
            overlap = len(tokens & previous) / max(1, min(len(tokens), len(previous)))
            if overlap > 0.75:
                duplicate = True
                break
        if not duplicate:
            seen.append(tokens)
            unique.append(claim)
    return unique


async def extract_claims(segments: list[TranscriptSegment], video: VideoMetadata) -> list[ExtractedClaim]:
    config = settings()
    chunks = chunk_segments(segments)
    if not chunks:
        return []

    # Ask each chunk for a slightly generous share so the final cap can pick the
    # best across the whole video rather than front-loading the first chunk.
    per_chunk = max(2, min(6, config.max_claims))
    results = await asyncio.gather(
        *(_extract_chunk(chunk, video, per_chunk) for chunk in chunks),
        return_exceptions=True,
    )

    collected: list[ExtractedClaim] = []
    failures = 0
    for result in results:
        if isinstance(result, BaseException):
            failures += 1
            continue
        collected.extend(result)

    if not collected and failures == len(chunks):
        raise LLMUnavailable("Claim extraction failed for every transcript chunk.")

    return _deduplicate(collected)[: config.max_claims]

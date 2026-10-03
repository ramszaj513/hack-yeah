"""Rhetorical analysis: how something is being said, not whether it is true.

This runs beside fact-checking rather than inside it. A claim can be perfectly
accurate and still be deployed to mislead — a true statistic with its base rate
removed, a sponsorship read as editorial, a contested political question framed
as settled. None of that is visible to a pipeline that only asks whether
sentences match sources.

It is also the part of this tool most capable of doing harm. A detector of
"propaganda" that flags opinions it disagrees with is worse than no detector,
so the prompt names the technique rather than judging the position, requires a
verbatim quote for every signal, and is told that most honest argument uses
emphasis and emotion legitimately. Silence is the correct output for an
ordinary video.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app import cache
from app.config import settings
from app.models.schemas import Technique, TranscriptSegment, VideoMetadata
from app.pipeline.extraction import chunk_segments, render_chunk
from app.pipeline.llm import LLMUnavailable, structured_call


@dataclass
class DetectedSignal:
    quote: str
    technique: Technique
    severity: str
    note: str


TECHNIQUE_VALUES = [item.value for item in Technique]


SIGNAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["signals"],
    "properties": {
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["quote", "technique", "severity", "note"],
                "properties": {
                    "quote": {
                        "type": "string",
                        "description": "Verbatim span copied from the transcript, 4-40 words.",
                    },
                    "technique": {"type": "string", "enum": TECHNIQUE_VALUES},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "note": {
                        "type": "string",
                        "description": "One sentence, under 200 characters, naming what the passage does.",
                    },
                },
            },
        }
    },
}


PROMPT = """You review how a video argues, not whether its facts are right.

Report only passages where a identifiable technique is at work. The techniques:

undisclosed_ad
    Promotion presented as the presenter's own view, or a sponsorship whose
    commercial nature is not made plain where it is read.
emotional_manipulation
    Fear, outrage, guilt or pity used in place of an argument to carry a
    conclusion the evidence does not.
loaded_language
    An unnamed authority doing load-bearing work — "experts agree" standing in
    for the argument on a contested point — or a word chosen to pre-judge what
    is in question. Ordinary speech says "studies show" constantly; flag it
    only where the unnamed authority is what the conclusion actually rests on,
    not whenever a source goes uncited.
logical_fallacy
    False dilemma, strawman, ad hominem, slippery slope, circular reasoning,
    or treating correlation as cause.
cherry_picking
    A real figure stripped of its base rate, comparison or timeframe, or
    evidence selected so the exceptions disappear.
conspiracy_framing
    Hidden actors with unnamed motives; "they don't want you to know"; a
    narrative built so that absence of evidence counts as confirmation.
political_framing
    A genuinely contested political question presented as settled, or one side
    described in terms its holders would not recognise.
unfalsifiable
    Put so that nothing could count against it.

Rules, and these matter more than finding something:

- Return NOTHING for an ordinary video. Most speech uses emphasis, humour,
  strong wording and emotion legitimately, and none of that is a technique.
  An empty list is the normal, correct answer.
- Name the technique, never the position. You are not assessing whether a view
  is right, popular, or one you would hold. A clearly argued political opinion
  is not propaganda; a conclusion forced by fear is, whichever side it serves.
  If flagging a passage would amount to disagreeing with its viewpoint, do not
  flag it.
- Apply the same threshold whatever the politics. If you would not flag the
  mirror-image passage from the opposing side, do not flag this one.
- `quote` must appear in the transcript character-for-character, or the signal
  is discarded.
- severity: high only where a viewer would be materially misled; low for
  something worth noticing but minor. If a passage would only ever be "low"
  and the video is otherwise plain, prefer returning nothing: a list of minor
  observations on an honest video is noise, and it teaches viewers to ignore
  the marks that matter.
- Do not flag a passage merely for being wrong. Falsity is checked elsewhere;
  this is about the method of persuasion.
- Return only passages you ARE flagging. This list is not your working notes.
  If you examine a passage and conclude the technique does not apply, leave it
  out — never return a signal whose own note explains why it is not an
  instance.
- A sponsorship that says it is a sponsorship is correctly disclosed and is
  not undisclosed_ad. Flag that technique only where the commercial
  relationship is hidden, blurred, or revealed far from the promotion itself.
- At most {limit} signals for this chunk, the clearest ones.

=== Everything above is fixed. The material to review follows. ===

Video title: {title}

Transcript chunk:
-------------------------
{chunk}
-------------------------
"""


async def _review_chunk(chunk: list[TranscriptSegment], video: VideoMetadata, limit: int) -> list[DetectedSignal]:
    key = cache.key_for("rhetoric", render_chunk(chunk), video.title, limit,
                        settings().openai_model)
    cached = cache.get(key)
    if cached is not None:
        return [DetectedSignal(quote=i["quote"], technique=Technique(i["technique"]),
                               severity=i["severity"], note=i["note"]) for i in cached]

    payload, _ = await structured_call(
        prompt=PROMPT.format(limit=limit, title=video.title or "(unknown)", chunk=render_chunk(chunk)),
        schema_name="rhetoric_signals",
        schema=SIGNAL_SCHEMA,
        max_output_tokens=2000,
        cache_key="ytfc-rhetoric",
    )

    found: list[DetectedSignal] = []
    for item in payload.get("signals", []) or []:
        quote = (item.get("quote") or "").strip()
        note = (item.get("note") or "").strip()
        if not quote or not note:
            continue
        try:
            technique = Technique(item.get("technique"))
        except ValueError:
            continue
        severity = item.get("severity") if item.get("severity") in {"low", "medium", "high"} else "low"
        found.append(
            DetectedSignal(quote=quote[:2000], technique=technique, severity=severity, note=note[:300])
        )
    cache.put(key, [{"quote": i.quote, "technique": i.technique.value,
                     "severity": i.severity, "note": i.note} for i in found])
    return found


async def detect_signals(segments: list[TranscriptSegment], video: VideoMetadata) -> list[DetectedSignal]:
    """Review the whole transcript. Needs no retrieval, so it is cheap and fast."""
    chunks = chunk_segments(segments)
    if not chunks:
        return []

    results = await asyncio.gather(
        *(_review_chunk(chunk, video, 4) for chunk in chunks),
        return_exceptions=True,
    )

    collected: list[DetectedSignal] = []
    for result in results:
        if isinstance(result, BaseException):
            continue
        collected.extend(result)

    return collected[: settings().max_signals]

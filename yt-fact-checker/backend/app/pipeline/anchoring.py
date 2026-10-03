"""Deterministic mapping from a quoted span back to a transcript timestamp.

The model is never trusted to report *when* something was said. It reports what
was said, verbatim, and this module finds that text in the transcript. That
matters because the extension paints markers on the YouTube scrubber: an
approximate timestamp puts a red "false" marker over innocent footage.

Failing to anchor a quote is also the hallucination check. If the sentence
cannot be found in the transcript, the model invented it and the claim is
dropped rather than shown.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re

from app.models.schemas import TranscriptSegment


MIN_SCORE = 0.6

_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass
class Anchor:
    startSeconds: float
    endSeconds: float
    score: float


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _segment_tokens(segments: list[TranscriptSegment]) -> tuple[list[str], list[int]]:
    """Flatten the transcript into tokens plus the segment each token came from."""
    tokens: list[str] = []
    owners: list[int] = []
    for index, segment in enumerate(segments):
        for token in _tokenize(segment.text):
            tokens.append(token)
            owners.append(index)
    return tokens, owners


def _span_time(segments: list[TranscriptSegment], first: int, last: int) -> tuple[float, float]:
    start_segment = segments[first]
    end_segment = segments[last]
    return start_segment.start, end_segment.start + max(end_segment.duration, 0.0)


def anchor_quote(quote: str, segments: list[TranscriptSegment]) -> Anchor | None:
    """Locate `quote` in the transcript and return its real time span."""
    needle = _tokenize(quote)
    if not needle or not segments:
        return None

    haystack, owners = _segment_tokens(segments)
    if not haystack:
        return None

    window = len(needle)
    if window > len(haystack):
        window = len(haystack)

    needle_counts = Counter(needle)
    best_score = 0.0
    best_range: tuple[int, int] | None = None

    current = Counter(haystack[:window])
    overlap = sum((current & needle_counts).values())
    best_score = overlap / window
    best_range = (0, window - 1)

    for start in range(1, len(haystack) - window + 1):
        leaving = haystack[start - 1]
        entering = haystack[start + window - 1]
        if leaving != entering:
            if current[leaving] <= needle_counts[leaving]:
                overlap -= 1
            current[leaving] -= 1
            if current[leaving] == 0:
                del current[leaving]
            current[entering] += 1
            if current[entering] <= needle_counts[entering]:
                overlap += 1

        score = overlap / window
        if score > best_score:
            best_score = score
            best_range = (start, start + window - 1)
            if score == 1.0:
                break

    if best_range is None or best_score < MIN_SCORE:
        return None

    first_segment = owners[best_range[0]]
    last_segment = owners[min(best_range[1], len(owners) - 1)]
    start_seconds, end_seconds = _span_time(segments, first_segment, last_segment)
    return Anchor(startSeconds=start_seconds, endSeconds=max(end_seconds, start_seconds), score=best_score)


def quote_appears_in(quote: str, document: str, threshold: float = 0.62) -> bool:
    """Check that a cited span really occurs in fetched source text.

    Used by citation verification. Tolerant of whitespace, punctuation and
    light normalisation, because a page re-fetched later rarely matches
    character-for-character what the model read — but strict enough that a
    fabricated quote, which shares almost no vocabulary with the page it
    claims to come from, still fails.
    """
    needle = _tokenize(quote)
    if not needle:
        return False

    haystack = set(_tokenize(document))
    if not haystack:
        return False

    present = sum(1 for token in needle if token in haystack)
    return present / len(needle) >= threshold

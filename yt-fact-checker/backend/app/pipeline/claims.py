import re
from dataclasses import dataclass

from app.models.schemas import TranscriptSegment


@dataclass
class CandidateClaim:
    text: str
    start: float
    end: float


OPINION_PREFIXES = (
    "i think",
    "i believe",
    "in my opinion",
    "we should",
    "we must",
    "hopefully",
    "i predict",
    "it will",
    "we will",
)


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def extract_candidate_claims(segments: list[TranscriptSegment], limit: int = 12) -> list[CandidateClaim]:
    """Conservative baseline extractor used when no model provider is configured.

    It intentionally returns fewer claims rather than turning opinions, questions,
    and slogans into fact checks. A production provider can replace this stage while
    keeping the same CandidateClaim contract.
    """
    candidates: list[CandidateClaim] = []
    joined = ""
    ranges: list[tuple[int, int, TranscriptSegment]] = []
    for segment in segments:
        start = len(joined)
        joined = f"{joined} {segment.text}".strip()
        ranges.append((start, len(joined), segment))

    for match in re.finditer(r"[^.!?]+(?:[.!?]|$)", joined):
        sentence = match.group(0).strip()
        normalized = sentence.lower().strip()
        if len(sentence) < 24 or sentence.endswith("?"):
            continue
        if normalized.startswith(OPINION_PREFIXES):
            continue
        if not re.search(r"\b(is|are|was|were|has|have|had|means|caused|spent|signed|protects|increased|decreased)\b", normalized):
            continue
        matching_segments = [item for start, end, item in ranges if end > match.start() and start < match.end()]
        if not matching_segments:
            continue
        candidates.append(
            CandidateClaim(
                text=sentence,
                start=matching_segments[0].start,
                end=matching_segments[-1].start + matching_segments[-1].duration,
            )
        )
        if len(candidates) >= limit:
            return candidates
    return candidates

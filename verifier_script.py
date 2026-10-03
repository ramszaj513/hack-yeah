import argparse
import json
import os
import re
import sys
from typing import List, Literal

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field
from youtube_transcript_api import YouTubeTranscriptApi


# ============================================================
# Configuration
# ============================================================

# Cheap-ish default model.
# Override in PowerShell with:
#
#   $env:OPENAI_MODEL = "gpt-4.1"
#
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# Maximum transcript characters sent to OpenAI.
#
# Override:
#
#   $env:MAX_TRANSCRIPT_CHARS = "20000"
#
MAX_TRANSCRIPT_CHARS = int(
    os.getenv("MAX_TRANSCRIPT_CHARS", "100000")
)

# Maximum number of claims to return.
MAX_CLAIMS = int(
    os.getenv("MAX_CLAIMS", "5")
)

# Whether to use OpenAI web search for verification.
#
# Default: enabled.
#
# Disable with:
#
#   $env:ENABLE_WEB_SEARCH = "false"
#
ENABLE_WEB_SEARCH = (
    os.getenv("ENABLE_WEB_SEARCH", "true").lower()
    in ("1", "true", "yes", "on")
)


# ============================================================
# Structured JSON schema
# ============================================================

class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str = Field(
        description="Approximate timestamp in the video, e.g. 02:31"
    )

    claim: str = Field(
        description="The factual claim made in the video"
    )

    classification: Literal[
        "potentially_false",
        "potentially_misleading",
        "unverified",
        "supported",
        "opinion_or_rhetoric",
    ]

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the classification from 0 to 1"
    )

    explanation: str = Field(
        description="Why the claim received this classification"
    )

    evidence_summary: str = Field(
        description="Concise summary of the evidence used"
    )

    source_urls: List[str] = Field(
        description="URLs of sources used to verify or assess the claim"
    )


class Analysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_assessment: Literal[
        "contains_potentially_misleading_claims",
        "no_major_problematic_claims_found",
        "insufficient_evidence",
    ]

    summary: str

    claims: List[Claim]


# ============================================================
# YouTube helpers
# ============================================================

def extract_video_id(url_or_id: str) -> str:
    """Extract an 11-character YouTube video ID."""

    value = url_or_id.strip()

    # Already a YouTube ID
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value

    patterns = [
        r"(?:v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, value)

        if match:
            return match.group(1)

    raise ValueError(
        f"Could not extract YouTube video ID from: {url_or_id}"
    )


def format_timestamp(seconds: float) -> str:
    """Convert seconds into MM:SS or HH:MM:SS."""

    total_seconds = max(0, int(seconds))

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"


def fetch_transcript(
    video_id: str,
    languages: List[str] | None = None,
) -> str:
    """
    Fetch a YouTube transcript.

    Preferred languages are tried first. If they are unavailable,
    the first available transcript is used.
    """

    api = YouTubeTranscriptApi()

    if languages is None:
        languages = ["en"]

    try:
        transcript = api.fetch(
            video_id,
            languages=languages,
        )

    except Exception as first_error:

        try:
            transcript_list = api.list(video_id)
            available = list(transcript_list)

            if not available:
                raise RuntimeError(
                    "No transcripts/captions are available for this video."
                )

            selected = None

            # Prefer English if available.
            for item in available:
                if getattr(item, "language_code", "") == "en":
                    selected = item
                    break

            if selected is None:
                selected = available[0]

            transcript = selected.fetch()

        except Exception as fallback_error:
            raise RuntimeError(
                "Could not fetch a YouTube transcript.\n"
                f"Preferred-language error: {first_error}\n"
                f"Fallback error: {fallback_error}"
            ) from fallback_error

    lines = []

    for snippet in transcript:
        text = snippet.text.strip()

        if not text:
            continue

        timestamp = format_timestamp(snippet.start)

        lines.append(
            f"[{timestamp}] {text}"
        )

    return "\n".join(lines)


def limit_transcript(
    transcript: str,
    max_chars: int,
) -> str:
    """
    Shorten very long transcripts.

    Keeps material from both the start and end rather than only taking
    the beginning of the video.
    """

    if len(transcript) <= max_chars:
        return transcript

    beginning_chars = int(max_chars * 0.66)
    ending_chars = max_chars - beginning_chars

    beginning = transcript[:beginning_chars]
    ending = transcript[-ending_chars:]

    return (
        beginning
        + "\n\n"
        "[... MIDDLE OF TRANSCRIPT OMITTED TO REDUCE API USAGE ...]"
        "\n\n"
        + ending
    )


# ============================================================
# OpenAI helpers
# ============================================================

def extract_grounding_urls(response) -> List[str]:
    """
    Extract URLs from OpenAI web-search citations.

    This is deliberately defensive because response object structures
    can evolve between SDK versions.
    """

    urls = set()

    try:
        response_dict = response.model_dump(
            mode="json",
            exclude_none=True,
        )
    except Exception:
        return []

    def walk(value):
        if isinstance(value, dict):

            # Typical URL citation object
            if value.get("type") == "url_citation":
                url = value.get("url")

                if url:
                    urls.add(url)

            for child in value.values():
                walk(child)

        elif isinstance(value, list):

            for child in value:
                walk(child)

    walk(response_dict)

    return sorted(urls)


def build_prompt(
    video_url: str,
    transcript: str,
    max_claims: int,
) -> str:

    return f"""
You are analyzing a YouTube video transcript for potentially false
or misleading factual claims.

Your job is fact-checking, not judging the creator.

Identify a maximum of {max_claims} of the MOST IMPORTANT factual claims
that appear worth checking.

For each claim:

- Determine what factual assertion is actually being made.
- Verify it against reliable sources.
- Prefer primary sources, official government/statistical sources,
  academic sources, and reputable news organizations.
- Distinguish between false, misleading, unverified, supported,
  and opinion/rhetoric.
- Do not call something false merely because it sounds unusual.
- Do not treat absence of evidence as evidence of falsity.
- Do not invent claims that are not in the transcript.
- Ignore obvious jokes, sarcasm, rhetorical questions and personal
  opinions unless they contain a factual assertion.
- Give an approximate timestamp based on transcript timestamps.
- Include URLs of relevant sources.

Classification rules:

"potentially_false"
    Strong reliable evidence contradicts the claim.

"potentially_misleading"
    The statement contains some factual basis but omits important
    context, selectively presents information, or creates a misleading
    impression.

"unverified"
    There is not enough reliable evidence to establish whether the
    claim is true or false.

"supported"
    Reliable evidence generally supports the claim.

"opinion_or_rhetoric"
    The statement is mainly opinion, rhetoric, prediction, satire,
    or another non-factual assertion.

Overall assessment:

"contains_potentially_misleading_claims"
    At least one material claim appears potentially false or misleading.

"no_major_problematic_claims_found"
    No major false or misleading claims were identified in the
    analyzed transcript.

"insufficient_evidence"
    Available evidence is insufficient to make a useful assessment.

IMPORTANT:

The transcript may have been shortened. Do not infer anything from
text that was omitted.

Return ONLY the requested JSON structure.

YouTube video:
{video_url}

Transcript:
-------------------------
{transcript}
-------------------------
"""


def analyze_transcript(
    video_url: str,
    transcript: str,
    max_claims: int,
) -> tuple[Analysis, List[str]]:

    client = OpenAI()

    prompt = build_prompt(
        video_url=video_url,
        transcript=transcript,
        max_claims=max_claims,
    )

    # Structured-output schema.
    json_schema = {
        "type": "json_schema",
        "name": "youtube_fact_check",
        "strict": True,
        "schema": Analysis.model_json_schema(),
    }

    request = {
        "model": MODEL,
        "input": prompt,

        "text": {
            "format": json_schema,
        },

        # Keep generated output bounded.
        "max_output_tokens": 4096,
    }

    # Web search is particularly useful here because the purpose is
    # checking claims against current information.
    if ENABLE_WEB_SEARCH:
        request["tools"] = [
            {
                "type": "web_search",
            }
        ]

    response = client.responses.create(
        **request
    )

    if not response.output_text:
        raise RuntimeError(
            "OpenAI returned an empty response."
        )

    try:
        analysis = Analysis.model_validate_json(
            response.output_text
        )

    except Exception as exc:
        raise RuntimeError(
            "OpenAI returned invalid JSON despite structured output.\n"
            f"Raw response:\n{response.output_text}"
        ) from exc

    grounding_urls = extract_grounding_urls(response)

    # Add grounding URLs to claims where useful.
    if grounding_urls:
        for claim in analysis.claims:

            existing = set(claim.source_urls)

            for url in grounding_urls:

                if url not in existing:
                    claim.source_urls.append(url)

    return analysis, grounding_urls


# ============================================================
# Error handling
# ============================================================

def print_api_error(exc: Exception) -> None:
    """Convert OpenAI exceptions into a clean JSON error."""

    message = str(exc)

    status_code = getattr(
        exc,
        "status_code",
        None,
    )

    error_type = type(exc).__name__

    if status_code == 429:
        error = {
            "error": "RateLimitError",
            "message": (
                "OpenAI API rate limit or quota was exceeded."
            ),
            "details": message,
            "model": MODEL,
        }

    elif status_code in (401, 403):
        error = {
            "error": "AuthenticationError",
            "message": (
                "OpenAI rejected the API key or the project "
                "does not have permission to use this model."
            ),
            "details": message,
            "model": MODEL,
        }

    else:
        error = {
            "error": error_type,
            "message": message,
            "model": MODEL,
        }

    print(
        json.dumps(
            error,
            indent=2,
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Fetch a YouTube transcript and analyze it using "
            "OpenAI for potentially false or misleading claims."
        )
    )

    parser.add_argument(
        "youtube_url",
        help="YouTube video URL or 11-character video ID",
    )

    parser.add_argument(
        "--max-chars",
        type=int,
        default=MAX_TRANSCRIPT_CHARS,
        help=(
            "Maximum transcript characters sent to OpenAI "
            f"(default: {MAX_TRANSCRIPT_CHARS})"
        ),
    )

    parser.add_argument(
        "--max-claims",
        type=int,
        default=MAX_CLAIMS,
        help=(
            "Maximum number of claims to return "
            f"(default: {MAX_CLAIMS})"
        ),
    )

    parser.add_argument(
        "--language",
        action="append",
        default=None,
        help=(
            "Preferred transcript language. "
            "Can be supplied multiple times."
        ),
    )

    parser.add_argument(
        "--no-web-search",
        action="store_true",
        help="Disable OpenAI web search verification",
    )

    args = parser.parse_args()

    # Command-line option overrides environment variable.
    global ENABLE_WEB_SEARCH

    if args.no_web_search:
        ENABLE_WEB_SEARCH = False

    # --------------------------------------------------------
    # API key
    # --------------------------------------------------------

    if not os.getenv("OPENAI_API_KEY"):

        print(
            json.dumps(
                {
                    "error": "MissingApiKey",
                    "message": (
                        "OPENAI_API_KEY environment variable "
                        "is not set."
                    ),
                },
                indent=2,
            ),
            file=sys.stderr,
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Validate settings
    # --------------------------------------------------------

    if args.max_chars < 1000:

        print(
            json.dumps(
                {
                    "error": "InvalidArgument",
                    "message": (
                        "--max-chars must be at least 1000."
                    ),
                },
                indent=2,
            ),
            file=sys.stderr,
        )

        sys.exit(1)

    if args.max_claims < 1:

        print(
            json.dumps(
                {
                    "error": "InvalidArgument",
                    "message": (
                        "--max-claims must be at least 1."
                    ),
                },
                indent=2,
            ),
            file=sys.stderr,
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Process
    # --------------------------------------------------------

    try:

        video_id = extract_video_id(
            args.youtube_url
        )

        video_url = (
            f"https://www.youtube.com/watch?v={video_id}"
        )

        print(
            f"OpenAI model: {MODEL}",
            file=sys.stderr,
        )

        print(
            f"Web search: {ENABLE_WEB_SEARCH}",
            file=sys.stderr,
        )

        print(
            f"Max transcript chars: {args.max_chars:,}",
            file=sys.stderr,
        )

        print(
            f"Max claims: {args.max_claims}",
            file=sys.stderr,
        )

        # ----------------------------------------------------
        # Transcript
        # ----------------------------------------------------

        print(
            "Fetching YouTube transcript...",
            file=sys.stderr,
        )

        transcript = fetch_transcript(
            video_id,
            languages=args.language,
        )

        if not transcript.strip():
            raise RuntimeError(
                "The transcript is empty."
            )

        original_length = len(transcript)

        transcript = limit_transcript(
            transcript,
            args.max_chars,
        )

        print(
            (
                f"Transcript size: "
                f"{original_length:,} chars -> "
                f"{len(transcript):,} chars sent to OpenAI"
            ),
            file=sys.stderr,
        )

        # ----------------------------------------------------
        # OpenAI
        # ----------------------------------------------------

        print(
            "Analyzing transcript with OpenAI...",
            file=sys.stderr,
        )

        analysis, grounding_urls = analyze_transcript(
            video_url=video_url,
            transcript=transcript,
            max_claims=args.max_claims,
        )

        # ----------------------------------------------------
        # Final standardized JSON
        # ----------------------------------------------------

        output = {
            "video_id": video_id,
            "video_url": video_url,

            "model": MODEL,

            "transcript": {
                "original_characters": original_length,
                "analyzed_characters": len(transcript),
                "was_truncated": (
                    original_length > len(transcript)
                ),
            },

            "verification": {
                "web_search_enabled": ENABLE_WEB_SEARCH,
                "grounding_source_count": len(grounding_urls),
            },

            "analysis": analysis.model_dump(),
        }

        print(
            json.dumps(
                output,
                indent=2,
                ensure_ascii=False,
            )
        )

    except Exception as exc:

        print_api_error(exc)
        sys.exit(1)


if __name__ == "__main__":
    main()


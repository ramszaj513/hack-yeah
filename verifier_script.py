"""Command-line fact check for a single YouTube video.

This is a thin front-end over the same pipeline the extension's backend runs
(``yt-fact-checker/backend/app/pipeline``). It deliberately holds no analysis
logic of its own: two implementations drifted apart once already, producing two
different verdict vocabularies for the same product.

Usage:
    python verifier_script.py https://www.youtube.com/watch?v=VIDEO_ID
    python verifier_script.py VIDEO_ID --max-claims 5 --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import sys


BACKEND = Path(__file__).resolve().parent / "yt-fact-checker" / "backend"
sys.path.insert(0, str(BACKEND))


def extract_video_id(url_or_id: str) -> str:
    value = url_or_id.strip()
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

    raise ValueError(f"Could not extract a YouTube video ID from: {url_or_id}")


def _timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _print_human(response, video_url: str) -> None:
    print(f"\n{video_url}")
    print(f"status: {response.status}   claims: {len(response.claims)}\n")

    for warning in response.warnings:
        print(f"  ! {warning}")
    if response.warnings:
        print()

    for claim in response.claims:
        print("=" * 78)
        print(f"[{_timestamp(claim.startSeconds)}] {claim.verdict.value.upper()}  ({claim.claimType.value})")
        print(f"  claim   : {claim.text}")
        if claim.quote:
            print(f"  said    : “{claim.quote}”")
        print(f"  basis   : {claim.basis}")
        if claim.unverifiedReason:
            print(f"  reason  : {claim.unverifiedReason.value}")
        for item in claim.evidence:
            if item.quoteVerified is True:
                mark = "verified"
            elif item.quoteVerified is False:
                mark = "QUOTE NOT ON PAGE"
            else:
                mark = "unreachable"
            print(f"    - [{item.sourceType}/{item.supports}/{mark}] {item.publisher}")
            print(f"      {item.url}")
        print()


async def _run(video_id: str, as_json: bool) -> int:
    from app.models.schemas import CheckRequest, VideoMetadata
    from app.pipeline.orchestrator import run_pipeline
    from app.pipeline.transcript import TranscriptUnavailable, fetch_english_transcript

    video_url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        transcript = fetch_english_transcript(video_id)
    except TranscriptUnavailable as exc:
        print(json.dumps({"error": "TranscriptUnavailable", "message": str(exc)}, indent=2), file=sys.stderr)
        return 1

    print(f"transcript: {len(transcript)} segments", file=sys.stderr)

    request = CheckRequest(
        video=VideoMetadata(id=video_id, title="", description=""),
        url=video_url,
        transcript=transcript,
    )

    async def emit(event: dict) -> None:
        if event["type"] == "status":
            print(f"  … {event['status']}", file=sys.stderr)
        elif event["type"] == "claim":
            print(f"  ✓ {event['claim']['verdict']}: {event['claim']['text'][:70]}", file=sys.stderr)

    response = await run_pipeline(request, emit)

    if as_json:
        print(json.dumps({"video_id": video_id, "video_url": video_url, **response.model_dump(mode="json")}, indent=2, ensure_ascii=False))
    else:
        _print_human(response, video_url)

    return 0 if response.status in {"complete", "no_claims"} else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Fact-check a YouTube video from the command line.")
    parser.add_argument("youtube_url", help="YouTube video URL or 11-character video ID")
    parser.add_argument("--max-claims", type=int, help="Maximum number of claims to assess")
    parser.add_argument("--no-web-search", action="store_true", help="Disable open-web retrieval")
    parser.add_argument("--no-verify", action="store_true", help="Skip fetching sources to confirm quotes")
    parser.add_argument("--json", action="store_true", help="Emit the raw JSON response")
    args = parser.parse_args()

    # The pipeline reads configuration from the environment, so CLI flags are
    # applied before anything imports the settings cache.
    if args.max_claims is not None:
        if args.max_claims < 1:
            print("--max-claims must be at least 1", file=sys.stderr)
            sys.exit(1)
        os.environ["MAX_CLAIMS"] = str(args.max_claims)
    if args.no_web_search:
        os.environ["ENABLE_WEB_SEARCH"] = "false"
    if args.no_verify:
        os.environ["ENABLE_CITATION_VERIFICATION"] = "false"
    os.environ["DEMO_MODE"] = "false"

    try:
        video_id = extract_video_id(args.youtube_url)
    except ValueError as exc:
        print(json.dumps({"error": "InvalidInput", "message": str(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)

    if not os.getenv("OPENAI_API_KEY"):
        # The backend's .env is the single place the key lives.
        from dotenv import load_dotenv

        load_dotenv(BACKEND / ".env")

    if not os.getenv("OPENAI_API_KEY"):
        print(
            json.dumps(
                {
                    "error": "MissingApiKey",
                    "message": "Set OPENAI_API_KEY, or add it to yt-fact-checker/backend/.env",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        sys.exit(asyncio.run(_run(video_id, args.json)))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

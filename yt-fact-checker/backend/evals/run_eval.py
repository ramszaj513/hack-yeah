"""Score the pipeline against hand-labelled transcripts.

    python -m evals.run_eval            # all scripts
    python -m evals.run_eval health     # one script

Claims are matched back to expectations by time overlap, since quote anchoring
already guarantees a claim's timestamps come from the transcript itself.
"""

from __future__ import annotations

import asyncio
import sys

from app.config import settings
from app.models.schemas import CheckRequest, Claim, TranscriptSegment, VideoMetadata, Verdict
from app.pipeline.orchestrator import run_pipeline
from evals.fixtures import SCRIPTS, Expectation, Script


# A verdict is "acceptable" for an expectation if it lands in this set.
ACCEPTED: dict[str, set[Verdict]] = {
    "supported": {Verdict.SUPPORTED},
    "refuted": {Verdict.FALSE, Verdict.POTENTIALLY_FALSE, Verdict.MISLEADING},
    "misleading": {Verdict.MISLEADING, Verdict.CONTEXT_NEEDED},
    "context_needed": {Verdict.CONTEXT_NEEDED, Verdict.COULDNT_VERIFY},
}

RESET, BOLD = "\033[0m", "\033[1m"
GREEN, RED, YELLOW, DIM = "\033[32m", "\033[31m", "\033[33m", "\033[2m"


def _overlaps(claim: Claim, item: Expectation) -> bool:
    return claim.startSeconds < item.start + item.duration and item.start < claim.endSeconds


def _match(claim: Claim, script: Script) -> Expectation | None:
    candidates = [item for item in script.segments if _overlaps(claim, item)]
    if not candidates:
        return None
    # Prefer a checkable expectation over narration when a claim spans both.
    ranked = sorted(candidates, key=lambda item: (item.expect == "dropped", -item.duration))
    return ranked[0]


async def evaluate(script: Script) -> tuple[int, int, list[str]]:
    request = CheckRequest(
        video=VideoMetadata(id=script.id, title=script.title),
        transcript=[
            TranscriptSegment(text=item.text, start=item.start, duration=item.duration)
            for item in script.segments
        ],
    )

    response = await run_pipeline(request)

    print(f"\n{BOLD}{script.title}{RESET}  ({len(response.claims)} claims)")
    for warning in response.warnings:
        print(f"  {DIM}! {warning}{RESET}")

    passed = 0
    total = 0
    failures: list[str] = []
    matched: set[int] = set()

    for claim in response.claims:
        expectation = _match(claim, script)
        if expectation is None:
            failures.append(f"[{script.id}] claim could not be matched to a segment: {claim.text[:60]}")
            print(f"  {RED}?{RESET} unmatched: {claim.text[:66]}")
            continue

        matched.add(int(expectation.start))
        total += 1

        if expectation.expect == "dropped":
            # Narration, opinion and prediction must not surface as claims.
            failures.append(
                f"[{script.id}] extracted a '{expectation.note}' segment as a claim: {claim.text[:60]}"
            )
            print(f"  {RED}✗{RESET} should have been dropped ({expectation.note}): {claim.text[:52]}")
            continue

        allowed = ACCEPTED.get(expectation.expect, set())
        if claim.verdict in allowed:
            passed += 1
            print(f"  {GREEN}✓{RESET} {claim.verdict.value:18} {claim.text[:56]}")
        else:
            failures.append(
                f"[{script.id}] expected {expectation.expect}, got {claim.verdict.value} "
                f"({claim.unverifiedReason.value if claim.unverifiedReason else '-'}): {claim.text[:60]}"
            )
            print(
                f"  {RED}✗{RESET} {claim.verdict.value:18} expected {expectation.expect:15} {claim.text[:40]}"
            )
            print(f"      {DIM}{claim.basis[:110]}{RESET}")

    # Checkable segments the extractor never produced a claim for.
    for item in script.segments:
        if item.expect == "dropped" or int(item.start) in matched:
            continue
        total += 1
        failures.append(f"[{script.id}] missed a checkable claim entirely: {item.text[:60]}")
        print(f"  {YELLOW}–{RESET} missed ({item.expect}): {item.text[:58]}")

    return passed, total, failures


async def main() -> None:
    wanted = sys.argv[1:]
    scripts = [s for s in SCRIPTS if not wanted or any(w in s.id for w in wanted)]

    print(f"{DIM}extraction={settings().openai_model}  reasoning={settings().openai_reasoning_model}{RESET}")

    results = await asyncio.gather(*(evaluate(script) for script in scripts))

    passed = sum(item[0] for item in results)
    total = sum(item[1] for item in results)
    failures = [line for item in results for line in item[2]]

    print(f"\n{BOLD}{'=' * 70}{RESET}")
    rate = (passed / total * 100) if total else 0.0
    colour = GREEN if rate >= 80 else YELLOW if rate >= 60 else RED
    print(f"{BOLD}score: {colour}{passed}/{total} ({rate:.0f}%){RESET}")

    if failures:
        print(f"\n{BOLD}failures{RESET}")
        for line in failures:
            print(f"  - {line}")


if __name__ == "__main__":
    asyncio.run(main())

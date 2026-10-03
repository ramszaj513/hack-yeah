# yt-fact-checker

A Chrome/Chromium extension that helps viewers inspect factual claims in YouTube videos.

The viewer chooses **Check this video**. The extension reads the video's public English captions in the viewer's own browser session and sends them to a FastAPI backend, which extracts claims, retrieves evidence, adjudicates each claim, and verifies every citation before showing it. Speech-to-text is not used. Results are claim-level verdicts with evidence links; false, potentially false, and misleading claims receive distinct markers on the YouTube timeline.

## How a check runs

```
captions → extract claims → anchor to transcript → route by claim type
         → retrieve evidence (parallel) → adjudicate → refute → verify citations
```

Each stage exists to remove a specific way the result could be wrong:

| Stage | File | What it guarantees |
| --- | --- | --- |
| Extract | `pipeline/extraction.py` | Claims are decontextualised into standalone, checkable sentences, and opinions/predictions are labelled and dropped. Time-window chunking means unpunctuated auto-captions still work. |
| Anchor | `pipeline/anchoring.py` | The timestamp comes from finding the quoted words in the transcript, never from the model. A quote that isn't in the transcript means the claim was invented, and it is discarded. |
| Route | `pipeline/sources/__init__.py` | A health claim reaches the biomedical literature; a political one reaches fact-checkers. |
| Retrieve | `pipeline/sources/` | Wikipedia, Europe PMC, OpenAlex, Semantic Scholar, Google Fact Check Tools, and open-web search, queried in parallel per claim. |
| Adjudicate | `pipeline/verdict.py` | The verdict may only cite the evidence retrieved for *that* claim, and must quote the span it relies on. |
| Refute | `pipeline/verdict.py` | A second pass argues against every definitive verdict; verdicts that don't survive are downgraded rather than published. |
| Verify | `pipeline/verification.py` | Each cited page is fetched and the quoted span is string-matched against it. A definitive verdict whose citations don't check out is downgraded to `couldnt_verify`. |

Claims stream back over server-sent events as each one is decided, so the side panel fills in progressively.

### Why the uncertainty taxonomy matters

`couldnt_verify` is split by `unverifiedReason`: `no_evidence_found`, `sources_conflict`, `evidence_not_specific`, `citation_unverifiable`, `provider_error`, `claim_ambiguous`. "Nobody has published on this" and "our provider timed out" are very different things for a viewer weighing the result, and collapsing them would overstate what the tool knows.

## Run the backend

```bash
cd backend
uv venv .venv && uv pip install -e ".[dev]"      # or: python -m venv .venv && pip install -e ".[dev]"
cp .env.example .env                              # then add your OPENAI_API_KEY
.venv/bin/uvicorn app.main:app --reload --port 8000
```

`GET /health` reports whether a model key is configured and whether demo mode is on.

With `DEMO_MODE=true` the API returns the documented fixture instead of checking anything. The response is labelled `mode: "demo"` and carries an explicit warning, and the side panel shows a demo banner — fixture output must never be presented as a real check.

## Build and load the extension

```bash
cd extension
npm install
npm run build
```

Open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**, and select `extension/dist`.

The extension expects the backend at `http://localhost:8000`. Override before building:

```bash
VITE_API_BASE_URL="http://localhost:8000" npm run build
```

## Command line

```bash
python verifier_script.py https://www.youtube.com/watch?v=VIDEO_ID
python verifier_script.py VIDEO_ID --max-claims 5 --json
```

Same pipeline as the extension backend — it holds no analysis logic of its own.

## Test

```bash
cd backend && .venv/bin/python -m pytest
```

The pipeline tests cover the guarantees that hold without a model in the loop: quote anchoring, hallucinated-quote rejection, citation verification, and verdict downgrading.

## Evaluation

```bash
cd backend && .venv/bin/python -m evals.run_eval              # all scripts
cd backend && .venv/bin/python -m evals.run_eval adversarial  # one script
```

Four hand-labelled transcripts in `evals/fixtures.py`, written without punctuation to match auto-generated captions. Each segment is labelled `supported`, `refuted`, `context_needed` or `dropped` (opinions, predictions and narration that must never become claims), and the runner scores a real pipeline run against those labels.

The fourth script is held out: it was written after the pipeline was tuned on the first three, and it targets the failure mode that matters most — calling a surprising-but-true claim false, or waving through a falsehood that merely sounds sensible.

Recent runs score **20–21 / 21**. The score moves between runs because open-web retrieval returns different sources each time, so treat a single run as a sample rather than a fixed number. Remaining misses are compound claims needing several independently-sourced facts (e.g. comparing three historical dates); they fail as `couldnt_verify` rather than as a wrong verdict.

## Known limits

- English captions only, YouTube only, no automatic scanning, no speech-to-text.
- No overall per-video trust score. Claims are judged individually; a video is not scored.
- Captions are fetched in the browser because YouTube blocks most datacenter IPs. The server-side fallback works locally but is unreliable once deployed.
- Very long videos are truncated at `MAX_TRANSCRIPT_SEGMENTS`, and the response says so in its warnings.
- Semantic Scholar rate-limits anonymous callers; Europe PMC and OpenAlex cover for it.
- The result is a decision aid. Open the sources and judge for yourself.

See `docs/demo.md` and `docs/disclosure.md` for the presentation flow and external-resource disclosure.

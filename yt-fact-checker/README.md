# yt-fact-checker

A Chrome/Chromium extension that helps viewers inspect factual claims in YouTube videos.

The viewer chooses **Check this video**. The extension sends the video URL to a FastAPI backend, which fetches public English captions with `youtube-transcript-api`. Speech-to-text is not used. Results are claim-level verdicts with evidence links. False, potentially false, and misleading claims receive distinct markers on the YouTube timeline.

## Current implementation

- Manifest V3 extension written in TypeScript.
- YouTube content script with explicit check button and caption retrieval.
- Side panel for progress and claim results.
- Timestamped timeline markers for concerning claims.
- FastAPI backend with strict request/response schemas.
- Deterministic demo fixture mode for a reliable hackathon presentation.
- Heuristic live claim extraction and an optional Google Fact Check Tools provider.
- Citation URL validation and uncertainty-first verdict handling.
- Extension privacy settings page with a session-data clear action.

## Run the backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

The default `.env.example` uses `DEMO_MODE=true`. This intentionally returns the documented fixture response so the extension can be demonstrated without API keys. Fixture mode must be disclosed as such.

## Build and load the extension

```powershell
cd extension
npm install
npm run build
```

Then open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**, and select `extension/dist`.

The extension expects the backend at `http://localhost:8000`. Change `VITE_API_BASE_URL` before building if needed:

```powershell
$env:VITE_API_BASE_URL = "http://localhost:8000"
npm run build
```

## Test

```powershell
cd backend
pytest
```

## Product boundaries

- YouTube only for the MVP.
- English captions only.
- No automatic scanning.
- No speech-to-text.
- No overall trust score.
- Claims may be `false`, `potentially_false`, `misleading`, `supported`, `context_needed`, or `couldnt_verify`.
- The result is a decision aid; viewers should open and inspect the evidence links themselves.

See `docs/demo.md` and `docs/disclosure.md` for the presentation flow and external-resource disclosure.

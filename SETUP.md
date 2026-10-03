# Setup guide

Getting `yt-fact-checker` running on a fresh machine. Expect about ten minutes.

## What you need

| | Version | Check with |
| --- | --- | --- |
| Python | 3.11 or newer | `python3 --version` |
| Node.js | 18 or newer | `node --version` |
| Browser | any Chromium one — Chrome, Brave, Edge | |
| OpenAI API key | one with credit on it | |

[uv](https://docs.astral.sh/uv/) makes the Python setup faster but is optional; both paths are below.

**About the API key:** `.env` is deliberately gitignored, so cloning the repo does not give you one. Either get the project key from a teammate, or create your own at [platform.openai.com](https://platform.openai.com/api-keys). Do not paste a key into chat, a commit, or an issue — if one does leak, revoke it on that page immediately.

## 1. Get the code

```bash
git clone git@github.com:ramszaj513/hack-yeah.git
cd hack-yeah
```

## 2. Backend

```bash
cd yt-fact-checker/backend

# with uv
uv venv .venv && uv pip install -e ".[dev]"

# or with plain Python
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

Create the config and add your key:

```bash
cp .env.example .env
```

Open `.env` and set `OPENAI_API_KEY=sk-...`. Everything else has a working default. The two settings worth knowing:

- `MAX_CLAIMS` — how many claims per video (default 16). Lower it to 5 while testing; each claim costs money and time.
- `DEMO_MODE` — `true` returns a canned fixture instead of checking anything. Useful for frontend work without spending credit. The response is labelled as a fixture so it cannot be mistaken for a real check.

The other API keys in `.env.example` are optional. The pipeline runs without them, just with fewer evidence sources.

## 3. Start it

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Check it came up:

```bash
curl http://localhost:8000/health
# {"status":"ok","mode":"live","model_configured":"yes"}
```

`"model_configured":"no"` means the key is missing or `.env` was not picked up.

## 4. Extension

In a second terminal:

```bash
cd yt-fact-checker/extension
npm install
npm run build
```

Then load it:

1. Open `chrome://extensions` (on Brave, `brave://extensions`)
2. Turn on **Developer mode**
3. **Load unpacked** → select `yt-fact-checker/extension/dist`

If the backend is not on `http://localhost:8000`, set the URL before building:

```bash
VITE_API_BASE_URL="http://localhost:8000" npm run build
```

## 5. Run a check

Open a YouTube video that has captions and makes factual claims — a news segment or an explainer works far better than music. Click the purple **Check this video** button at the top right.

Claims appear one at a time as each is decided. A full check takes **one to three minutes**: every claim triggers a web search, academic lookups, an adversarial second pass, and a fetch of each cited page to confirm the quote is really there.

### Without the browser

```bash
cd hack-yeah
yt-fact-checker/backend/.venv/bin/python verifier_script.py "https://www.youtube.com/watch?v=VIDEO_ID" --max-claims 5
```

Add `--json` for raw output, `--no-web-search` to skip open-web retrieval.

## 6. Tests

```bash
cd yt-fact-checker/backend
.venv/bin/python -m pytest              # fast, no API calls
.venv/bin/python -m evals.run_eval      # scores real runs against labelled transcripts, costs credit
```

The eval score moves between runs — open-web retrieval returns different sources each time — so read it as a sample, not a fixed number.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Button does nothing | The extension was not reloaded after a rebuild. Reload it on the extensions page, then reload the YouTube tab so the content script re-injects. |
| Side panel never opens on Brave | Brave does not implement `chrome.sidePanel`. Results open in a tab instead — this is expected. |
| `"model_configured":"no"` | `.env` missing, or started from the wrong directory. Run uvicorn from `yt-fact-checker/backend`. |
| `no_transcript` | The video has no captions, or YouTube refused the request. Captions are normally read in your browser; the server-side fallback is blocked on most cloud IPs. |
| Everything returns `couldnt_verify` | Usually no API key, or no credit on the account. Check `/health` and your OpenAI usage page. |
| Backend errors after `git pull` | Dependencies changed. Re-run the install command from step 2. |
| Extension behaves oddly after `git pull` | Re-run `npm run build` and reload the extension. The API contract has changed before. |

## After pulling changes

```bash
git pull
cd yt-fact-checker/backend && uv pip install -e ".[dev]"   # if dependencies changed
cd ../extension && npm run build                            # then reload the extension
```

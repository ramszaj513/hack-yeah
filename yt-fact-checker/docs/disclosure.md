# External resource disclosure

The repository contains a new hackathon implementation of the extension and backend.

## General-purpose tools

- TypeScript, Vite, Chrome Extension Manifest V3.
- Python, FastAPI, Pydantic, httpx, pytest.

## External data and sources

- YouTube captions fetched on the backend with the no-key `youtube-transcript-api` library after the viewer explicitly starts a check. The library reads public caption tracks, including auto-generated English captions. It does not transcribe audio.
- Demo evidence links point to public U.S. National Archives and Congress.gov pages.
- Live Google Fact Check Tools integration is optional and requires the team's own API key.

## AI use

The implementation may use an AI coding assistant for design, coding, debugging, and documentation. The team remains responsible for understanding, testing, licensing, security, and factual accuracy. No generated verdict should be treated as authoritative without opening its evidence links.

## Privacy

The extension does not scan videos automatically and does not store browsing history. A check sends only the selected video's identifier, title, description, and available captions to the configured backend. Results live in Chrome session storage until the browser closes or the viewer clears them from the extension's privacy settings.

## Demo mode

`DEMO_MODE=true` returns the checked-in `fixtures/demo-results.json` response. It is deterministic for presentation reliability and must not be described as a live fact-check of the currently playing video.

# External resource disclosure

The repository contains a new hackathon implementation of the extension and backend.

## General-purpose tools

- TypeScript, Vite, Chrome Extension Manifest V3.
- Python, FastAPI, Pydantic, httpx, pytest.

## External data and sources

- YouTube captions supplied by the video page after the viewer explicitly starts a check.
- Demo evidence links point to public U.S. National Archives and Congress.gov pages.
- Live Google Fact Check Tools integration is optional and requires the team's own API key.

## AI use

The implementation may use an AI coding assistant for design, coding, debugging, and documentation. The team remains responsible for understanding, testing, licensing, security, and factual accuracy. No generated verdict should be treated as authoritative without opening its evidence links.

## Demo mode

`DEMO_MODE=true` returns the checked-in `fixtures/demo-results.json` response. It is deterministic for presentation reliability and must not be described as a live fact-check of the currently playing video.

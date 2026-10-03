# Demo runbook

## Setup

1. Start the FastAPI backend with `DEMO_MODE=true`.
2. Build and load `extension/dist` in Chrome/Chromium.
3. Open any YouTube video with English captions.
4. Click **Check this video**.

In demo mode the backend returns the prepared fixture claims, while the extension still exercises the real click, loading, panel, and marker flow. State clearly that the fixture is prepared and is not live evidence retrieval.

## What to show

1. The viewer has to explicitly click **Check this video**.
2. The progress state says what is happening.
3. False and potentially false claims appear first.
4. The false claim has the strongest timeline marker; the potentially false and misleading markers are more subtle.
5. Clicking a marker opens the side panel and focuses the matching claim.
6. Each result has a timestamp and a source link.
7. Supported claims remain available in the list but have no concerning marker.
8. Stop the backend or use a video without captions to show the no-transcript/error boundary.

## Fixture claims

The fixture intentionally uses simple, auditable constitutional-history examples so a presenter can open the source links during the pitch. Replace the fixture with a prepared political video and verify every source before submission.

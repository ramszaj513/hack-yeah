import type {
  AnalysisResponse,
  Claim,
  RuntimeMessage,
  SessionState,
  StreamEvent,
  TranscriptSegment,
  VideoMetadata,
} from "../shared/types";

declare const API_BASE_URL: string;

const initialState: SessionState = {
  status: "ready",
  claims: [],
  warnings: [],
};

async function setState(next: Partial<SessionState>): Promise<SessionState> {
  const current = await chrome.storage.session.get("state");
  const state = { ...((current.state as SessionState | undefined) ?? initialState), ...next };
  await chrome.storage.session.set({ state });
  return state;
}

async function getState(): Promise<SessionState> {
  const current = await chrome.storage.session.get("state");
  return (current.state as SessionState | undefined) ?? initialState;
}

async function openSidePanel(tabId?: number): Promise<void> {
  if (tabId === undefined) return;
  try {
    await chrome.sidePanel.open({ tabId });
  } catch {
    // The panel can fail to open on a non-YouTube or restricted page.
  }
}

async function sendMarkers(tabId: number | undefined, claims: Claim[]): Promise<void> {
  if (tabId === undefined) return;
  try {
    await chrome.tabs.sendMessage(tabId, { type: "RENDER_MARKERS", claims });
  } catch {
    // The tab may have navigated while the backend was processing.
  }
}

/** True while the user is still on the video this analysis was started for. */
async function stillCurrent(videoId: string): Promise<boolean> {
  const current = await getState();
  return current.video?.id === videoId;
}

async function applyEvent(
  event: StreamEvent,
  video: VideoMetadata,
  tabId: number | undefined,
): Promise<void> {
  if (!(await stillCurrent(video.id))) return;

  if (event.type === "status") {
    await setState({ status: event.status });
    return;
  }

  if (event.type === "claim") {
    // Claims arrive as each one is decided, so the panel fills in gradually
    // instead of showing nothing until the slowest claim finishes.
    const current = await getState();
    const claims = [...current.claims, event.claim].sort((a, b) => a.startSeconds - b.startSeconds);
    await setState({ claims });
    await sendMarkers(tabId, claims);
    return;
  }

  if (event.type === "complete") {
    const response: AnalysisResponse = event.response;
    await setState({
      status: response.status === "complete" ? "complete" : response.status,
      claims: response.claims,
      warnings: response.warnings,
      mode: response.mode,
      error: undefined,
    });
    await sendMarkers(tabId, response.claims);
    return;
  }

  await setState({ status: "failed", error: event.message, warnings: [] });
}

async function readStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: StreamEvent) => Promise<void>,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");

      if (!frame.startsWith("data:")) continue;
      try {
        await onEvent(JSON.parse(frame.slice(5).trim()) as StreamEvent);
      } catch {
        // A malformed frame should not abort an otherwise healthy stream.
      }
    }
  }
}

async function checkVideo(
  video: VideoMetadata,
  url: string,
  transcript: TranscriptSegment[] | undefined,
  tabId?: number,
): Promise<void> {
  await setState({ video, status: "loading_transcript", claims: [], warnings: [], error: undefined });

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/check/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video, url, transcript: transcript ?? [] }),
    });

    if (!response.ok) throw new Error(`Backend returned ${response.status}`);
    if (!response.body) throw new Error("The backend returned no response stream.");

    await readStream(response.body, (event) => applyEvent(event, video, tabId));
  } catch (error) {
    if (!(await stillCurrent(video.id))) return;
    const message = error instanceof Error ? error.message : "The fact-checking service is unavailable.";
    await setState({ status: "failed", error: message, warnings: [] });
  }
}

chrome.runtime.onInstalled.addListener(() => {
  void chrome.storage.session.set({ state: initialState });
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
});

chrome.runtime.onMessage.addListener((message: RuntimeMessage, sender, sendResponse) => {
  if (message.type === "GET_STATE") {
    void getState().then(sendResponse);
    return true;
  }

  if (message.type === "CHECK_STARTED") {
    void setState({
      video: message.video,
      status: "loading_transcript",
      claims: [],
      warnings: [],
      mode: undefined,
      error: undefined,
    });
    void openSidePanel(sender.tab?.id);
    void checkVideo(message.video, message.url, message.transcript, sender.tab?.id);
    return false;
  }

  if (message.type === "VIDEO_CHANGED") {
    void setState({
      video: message.video ?? undefined,
      status: message.video ? "ready" : "unsupported",
      claims: [],
      warnings: [],
      mode: undefined,
      error: undefined,
      selectedClaimId: undefined,
    });
    return false;
  }

  if (message.type === "MARKER_CLICK") {
    void setState({ selectedClaimId: message.claimId });
    void openSidePanel(sender.tab?.id);
    return false;
  }

  if (message.type === "START_CHECK") {
    void chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
      if (tab?.id !== undefined) void chrome.tabs.sendMessage(tab.id, { type: "START_CHECK" });
    });
    return false;
  }

  if (message.type === "SEEK_TO") {
    void chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
      if (tab?.id !== undefined) void chrome.tabs.sendMessage(tab.id, message);
    });
    return false;
  }

  if (message.type === "CLEAR_SESSION") {
    void chrome.storage.session.set({ state: initialState }).then(() => sendResponse({ ok: true }));
    return true;
  }

  return false;
});

import type { AnalysisResponse, RuntimeMessage, SessionState, VideoMetadata } from "../shared/types";

declare const API_BASE_URL: string;

const initialState: SessionState = {
  status: "ready",
  claims: [],
  warnings: [],
};

async function setState(next: Partial<SessionState>): Promise<SessionState> {
  const current = await chrome.storage.session.get("state");
  const state = { ...(current.state as SessionState | undefined ?? initialState), ...next };
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

async function sendMarkers(tabId: number | undefined, response: AnalysisResponse): Promise<void> {
  if (tabId === undefined) return;
  try {
    await chrome.tabs.sendMessage(tabId, { type: "RENDER_MARKERS", claims: response.claims });
  } catch {
    // The tab may have navigated while the backend was processing.
  }
}

async function checkVideo(video: VideoMetadata, transcript: RuntimeMessage & { type: "TRANSCRIPT_READY" }, tabId?: number): Promise<void> {
  await setState({ video, status: "extracting_claims", claims: [], warnings: [], error: undefined });
  await setState({ status: "gathering_evidence" });

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video, transcript: transcript.transcript }),
    });

    if (!response.ok) throw new Error(`Backend returned ${response.status}`);
    const result = (await response.json()) as AnalysisResponse;
    const current = await getState();
    if (current.video?.id !== video.id) return;
    await setState({
      status: result.status === "complete" ? "complete" : result.status,
      claims: result.claims,
      warnings: result.warnings,
      mode: result.mode,
      error: undefined,
    });
    await sendMarkers(tabId, result);
  } catch (error) {
    const current = await getState();
    if (current.video?.id !== video.id) return;
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
    void setState({ video: message.video, status: "loading_transcript", claims: [], warnings: [], mode: undefined, error: undefined });
    void openSidePanel(sender.tab?.id);
    return false;
  }

  if (message.type === "TRANSCRIPT_READY") {
    void checkVideo(message.video, message, sender.tab?.id);
    return false;
  }

  if (message.type === "NO_TRANSCRIPT") {
    void setState({
      video: message.video,
      status: "no_transcript",
      claims: [],
      warnings: ["This video cannot be checked because no usable transcript is available. Speech-to-text is not used."],
      mode: "live",
      error: undefined,
    });
    void openSidePanel(sender.tab?.id);
    return false;
  }

  if (message.type === "VIDEO_CHANGED") {
    void setState({ video: message.video ?? undefined, status: message.video ? "ready" : "unsupported", claims: [], warnings: [], mode: undefined, error: undefined, selectedClaimId: undefined });
    return false;
  }

  if (message.type === "MARKER_CLICK") {
    void setState({ selectedClaimId: message.claimId });
    void openSidePanel(sender.tab?.id);
    return false;
  }

  if (message.type === "START_CHECK") {
    void chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
      if (tab.id !== undefined) void chrome.tabs.sendMessage(tab.id, { type: "START_CHECK" });
    });
    return false;
  }

  if (message.type === "SEEK_TO") {
    void chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
      if (tab.id !== undefined) void chrome.tabs.sendMessage(tab.id, message);
    });
    return false;
  }

  if (message.type === "CLEAR_SESSION") {
    void chrome.storage.session.set({ state: initialState }).then(() => sendResponse({ ok: true }));
    return true;
  }

  return false;
});

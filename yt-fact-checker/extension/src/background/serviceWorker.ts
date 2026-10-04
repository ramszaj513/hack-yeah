import type {
  AnalysisResponse,
  Claim,
  RuntimeMessage,
  SessionState,
  Settings,
  Signal,
  StreamEvent,
  TranscriptSegment,
  VideoMetadata,
  TextSelection,
} from "../shared/types";
import { DEFAULT_SETTINGS } from "../shared/types";

declare const API_BASE_URL: string;

const initialState: SessionState = {
  status: "ready",
  claims: [],
  signals: [],
  warnings: [],
};
let activeRun = "";
let controller: AbortController | undefined;
let lastTextStart = 0;
let stateWrites: Promise<unknown> = Promise.resolve();

async function getSettings(): Promise<Settings> {
  const stored = await chrome.storage.local.get("settings");
  return { ...DEFAULT_SETTINGS, ...((stored.settings as Partial<Settings> | undefined) ?? {}) };
}

async function setSettings(settings: Settings): Promise<Settings> {
  await chrome.storage.local.set({ settings });
  // The content script decides what to mark and when to interrupt, so it needs
  // to hear about this immediately rather than on the next check.
  const tabs = await chrome.tabs.query({ url: "*://*.youtube.com/watch*" });
  for (const tab of tabs) {
    if (tab.id === undefined) continue;
    try {
      await chrome.tabs.sendMessage(tab.id, { type: "SETTINGS_CHANGED", settings });
    } catch {
      // Tab without the content script loaded; nothing to update.
    }
  }
  return settings;
}

function setState(next: Partial<SessionState>, runId?: string): Promise<SessionState> {
  const write = stateWrites.then(async () => {
    const current = await getState();
    if (runId !== undefined && activeRun !== runId) return current;
    const state = { ...current, ...next };
    await chrome.storage.session.set({ state });
    return state;
  });
  stateWrites = write.catch(() => undefined);
  return write;
}

async function getState(): Promise<SessionState> {
  const current = await chrome.storage.session.get("state");
  return (current.state as SessionState | undefined) ?? initialState;
}

function hasSidePanel(): boolean {
  return typeof chrome.sidePanel?.open === "function";
}

/** Show the results UI.
 *
 * Chrome gets the side panel. Brave and other Chromium forks that do not
 * implement chrome.sidePanel fall back to the same page in a tab — without
 * this, the button appears to do nothing at all on those browsers.
 */
async function openSidePanel(tabId?: number): Promise<void> {
  if (hasSidePanel() && tabId !== undefined) {
    try {
      await chrome.sidePanel.open({ tabId });
      return;
    } catch (error) {
      console.warn("[yt-fact-checker] side panel unavailable, falling back to a tab:", error);
    }
  }

  const url = chrome.runtime.getURL("sidepanel.html");
  try {
    const existing = await chrome.tabs.query({ url });
    if (existing.length > 0 && existing[0].id !== undefined) {
      await chrome.tabs.update(existing[0].id, { active: true });
      return;
    }
    // Opened in the foreground: a background tab is indistinguishable from the
    // button having done nothing, which is how this looked on Brave.
    await chrome.tabs.create({ url, active: true });
  } catch (error) {
    console.warn("[yt-fact-checker] could not open the results view:", error);
  }
}

async function sendMarkers(
  tabId: number | undefined,
  claims: Claim[],
  signals: Signal[],
): Promise<void> {
  if (tabId === undefined) return;
  try {
    await chrome.tabs.sendMessage(tabId, { type: "RENDER_MARKERS", claims, signals });
  } catch {
    // The tab may have navigated while the backend was processing.
  }
}

/** True while the user is still on the video this analysis was started for. */
async function stillCurrent(runId: string): Promise<boolean> {
  return activeRun === runId;
}

async function applyEvent(
  event: StreamEvent,
  runId: string,
  tabId: number | undefined,
  textMode = false,
): Promise<void> {
  if (!(await stillCurrent(runId))) return;

  if (event.type === "status") {
    await setState({ status: event.status, progress: undefined }, runId);
    return;
  }

  if (event.type === "progress") {
    await setState({ progress: { stage: event.stage, done: event.done, total: event.total } }, runId);
    return;
  }

  if (event.type === "claim") {
    // Claims arrive as each one is decided, so the panel fills in gradually
    // instead of showing nothing until the slowest claim finishes.
    const current = await getState();
    const claims = [...current.claims, event.claim].sort((a, b) => a.startSeconds - b.startSeconds);
    await setState({ claims }, runId);
    if (!textMode) await sendMarkers(tabId, claims, current.signals ?? []);
    return;
  }

  if (event.type === "signal") {
    const current = await getState();
    const signals = [...(current.signals ?? []), event.signal].sort(
      (a, b) => a.startSeconds - b.startSeconds,
    );
    await setState({ signals }, runId);
    if (!textMode) await sendMarkers(tabId, current.claims, signals);
    return;
  }

  if (event.type === "complete") {
    const response: AnalysisResponse = event.response;
    await setState({
      status: response.status === "complete" ? "complete" : response.status,
      claims: response.claims,
      signals: response.signals ?? [],
      warnings: response.warnings,
      mode: response.mode,
      error: undefined,
      progress: undefined,
    }, runId);
    if (!textMode && activeRun === runId) await sendMarkers(tabId, response.claims, response.signals ?? []);
    return;
  }

  if (event.type === "error") {
    await setState({ status: "failed", error: event.message, warnings: [] }, runId);
    return;
  }

  // Anything else is a kind of event this build does not know about. Ignoring
  // it keeps an older extension working against a newer backend; treating the
  // unknown as a failure, as this once did, meant adding a field to the stream
  // broke every client that had not been reloaded.
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
  controller?.abort();
  const abort = new AbortController();
  controller = abort;
  const runId = crypto.randomUUID();
  activeRun = runId;
  await setState({
    video,
    textSelection: undefined,
    sourceTabId: tabId,
    selectedClaimId: undefined,
    progress: undefined,
    mode: undefined,
    status: "loading_transcript",
    claims: [],
    signals: [],
    warnings: [],
    error: undefined,
  }, runId);

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/check/stream`, {
      signal: abort.signal,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video, url, transcript: transcript ?? [] }),
    });

    if (!response.ok) throw new Error(`Backend returned ${response.status}`);
    if (!response.body) throw new Error("The backend returned no response stream.");

    await readStream(response.body, (event) => applyEvent(event, runId, tabId));
  } catch (error) {
    if (!(await stillCurrent(runId))) return;
    const message = error instanceof Error ? error.message : "The fact-checking service is unavailable.";
    await setState({ status: "failed", error: message, warnings: [] }, runId);
  }
}

function startText(selection: TextSelection, tabId?: number): void {
  // Called directly from the click handler to retain the user gesture.
  void openSidePanel(tabId);
  void checkText(selection, tabId);
}

async function checkText(selection: TextSelection, tabId?: number): Promise<void> {
  const text = selection.text.trim();
  if (text.length < 30 || text.length > 3000) {
    await setState({ error: "Zaznacz od 30 do 3000 znaków.", warnings: ["Zaznacz od 30 do 3000 znaków."] });
    return;
  }
  if (Date.now() - lastTextStart < 1500) return;
  lastTextStart = Date.now();
  controller?.abort();
  const abort = new AbortController();
  controller = abort;
  const runId = crypto.randomUUID();
  activeRun = runId;
  selection = { ...selection, text, pageTitle: selection.pageTitle.slice(0, 500), context: selection.context.slice(0, 1500) };
  await setState({ ...initialState, status: "extracting_claims", video: undefined,
    textSelection: selection, sourceTabId: tabId, selectedClaimId: undefined,
    error: undefined, mode: undefined, progress: undefined }, runId);
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/check/text/stream`, {
      method: "POST", signal: abort.signal, headers: { "Content-Type": "application/json" },
      body: JSON.stringify(selection),
    });
    if (!response.ok) throw new Error(`Text check returned ${response.status}`);
    if (!response.body) throw new Error("No response stream.");
    await readStream(response.body, event => applyEvent(event, runId, tabId, true));
  } catch (error) {
    if (!(await stillCurrent(runId))) return;
    await setState({ status: "failed", error: error instanceof Error ? error.message : "Text check unavailable.", progress: undefined }, runId);
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "check-selection", title: "Zweryfikuj zaznaczony tekst",
      contexts: ["selection"], documentUrlPatterns: ["http://*/*", "https://*/*"] });
  });
  void chrome.storage.session.set({ state: initialState });
  // Guarded: on browsers without the Side Panel API this throws and takes the
  // rest of the install handler down with it.
  if (typeof chrome.sidePanel?.setPanelBehavior === "function") {
    void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => undefined);
  }
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== "check-selection" || info.editable || !info.selectionText) return;
  const url = new URL(info.frameUrl ?? info.pageUrl ?? tab?.url ?? "https://example.invalid");
  url.search = ""; url.hash = "";
  startText({ text: info.selectionText, pageUrl: url.href, pageTitle: tab?.title ?? "", context: "" }, tab?.id);
});

chrome.action.onClicked.addListener((tab) => {
  void openSidePanel(tab.id);
});

chrome.runtime.onMessage.addListener((message: RuntimeMessage, sender, sendResponse) => {
  if (message.type === "CHECK_TEXT") {
    startText(message.selection, sender.tab?.id);
    return false;
  }
  if (message.type === "RETRY_TEXT") {
    void getState().then(current => {
      if (current.textSelection) void checkText(current.textSelection, current.sourceTabId);
    });
    return false;
  }
  if (message.type === "GET_STATE") {
    void getState().then(sendResponse);
    return true;
  }

  if (message.type === "CHECK_STARTED") {
    controller?.abort();
    activeRun = "";
    // Opening the panel must happen while the user's click is still the
    // active gesture, so this handler does nothing slow.
    void setState({
      video: message.video,
      textSelection: undefined,
      status: "loading_transcript",
      claims: [],
      signals: [],
      warnings: [],
      mode: undefined,
      error: undefined,
    });
    void openSidePanel(sender.tab?.id);
    return false;
  }

  if (message.type === "TRANSCRIPT_READY") {
    void getState().then(current => {
      if (!current.textSelection && current.video?.id === message.video.id)
        void checkVideo(message.video, message.url, message.transcript, sender.tab?.id);
    });
    return false;
  }

  if (message.type === "VIDEO_CHANGED") {
    void getState().then(current => {
      if (current.textSelection) return;
      controller?.abort();
      activeRun = "";
      void setState({
        video: message.video ?? undefined,
        status: message.video ? "ready" : "unsupported",
        claims: [],
        signals: [],
        warnings: [],
        mode: undefined,
        error: undefined,
        selectedClaimId: undefined,
        progress: undefined,
      });
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

  if (message.type === "GET_SETTINGS") {
    void getSettings().then(sendResponse);
    return true;
  }

  if (message.type === "SET_SETTINGS") {
    void setSettings(message.settings).then(sendResponse);
    return true;
  }

  if (message.type === "CLEAR_SESSION") {
    controller?.abort();
    activeRun = "";
    void chrome.storage.session.set({ state: initialState }).then(() => sendResponse({ ok: true }));
    return true;
  }

  return false;
});

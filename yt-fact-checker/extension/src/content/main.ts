import type { Claim, RuntimeMessage, TranscriptSegment, VideoMetadata } from "../shared/types";

let currentVideoId: string | null = null;
let checkButton: HTMLButtonElement | null = null;
let markerHost: HTMLElement | null = null;

const CONCERNING = ["false", "potentially_false", "misleading"];
const VERDICT_LABELS: Record<string, string> = {
  false: "False",
  potentially_false: "Potentially false",
  misleading: "Misleading",
};

// A claim can be anchored to a span of only a second or two. Holding the
// notice a little longer gives the viewer time to actually read it.
const MIN_VISIBLE_SECONDS = 7;

let flaggedClaims: Claim[] = [];
let popupHost: HTMLElement | null = null;
let popupClaimId: string | null = null;
const dismissed = new Set<string>();
let videoEl: HTMLVideoElement | null = null;

function getVideoId(): string | null {
  return new URLSearchParams(window.location.search).get("v");
}

function getVideoMetadata(videoId: string): VideoMetadata {
  return {
    id: videoId,
    title: document.querySelector("h1.ytd-watch-metadata")?.textContent?.trim() ?? "",
    description: document.querySelector("ytd-text-inline-expander")?.textContent?.trim() ?? "",
    language: "en",
  };
}

function send(message: RuntimeMessage): void {
  void chrome.runtime.sendMessage(message);
}

function extractBalancedJson(source: string, start: number, opening: string, closing: string): string | null {
  const first = source.indexOf(opening, start);
  if (first < 0) return null;
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = first; index < source.length; index += 1) {
    const char = source[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') inString = false;
      continue;
    }
    if (char === '"') {
      inString = true;
      continue;
    }
    if (char === opening) depth += 1;
    if (char === closing) {
      depth -= 1;
      if (depth === 0) return source.slice(first, index + 1);
    }
  }
  return null;
}

function playerResponseFromHtml(html: string): Record<string, any> | null {
  const marker = html.indexOf("ytInitialPlayerResponse");
  if (marker < 0) return null;
  const json = extractBalancedJson(html, html.indexOf("=", marker), "{", "}");
  if (!json) return null;
  try {
    return JSON.parse(json) as Record<string, any>;
  } catch {
    return null;
  }
}

function transcriptFromJson3(payload: Record<string, any>): TranscriptSegment[] {
  return (payload.events ?? [])
    .filter((event: any) => Array.isArray(event.segs) && typeof event.tStartMs === "number")
    .map((event: any) => ({
      text: event.segs.map((segment: any) => segment.utf8 ?? "").join("").replace(/\s+/g, " ").trim(),
      start: event.tStartMs / 1000,
      duration: (event.dDurationMs ?? 0) / 1000,
    }))
    .filter((segment: TranscriptSegment) => segment.text.length > 0);
}

async function fetchTranscript(videoId: string): Promise<TranscriptSegment[] | null> {
  const page = await fetch(window.location.href, { credentials: "include" });
  if (!page.ok) return null;
  const playerResponse = playerResponseFromHtml(await page.text());
  const tracks = playerResponse?.captions?.playerCaptionsTracklistRenderer?.captionTracks ?? [];
  const track = tracks.find((candidate: any) => String(candidate.languageCode ?? "").toLowerCase().startsWith("en"));
  if (!track?.baseUrl) return null;

  const separator = String(track.baseUrl).includes("?") ? "&" : "?";
  const captions = await fetch(`${track.baseUrl}${separator}fmt=json3`, { credentials: "include" });
  if (!captions.ok) return null;
  const payload = await captions.json() as Record<string, any>;
  const segments = transcriptFromJson3(payload);
  return segments.length > 0 ? segments : null;
}

const TRANSCRIPT_TIMEOUT_MS = 10000;

function startCheck(): void {
  const videoId = getVideoId();
  if (!videoId) return;
  setButtonState("Checking", true);

  const video = getVideoMetadata(videoId);
  const url = window.location.href;

  // Sent synchronously: chrome.sidePanel.open() is only permitted inside the
  // user-gesture window, so anything awaited before this point silently loses
  // the right to open the panel.
  send({ type: "CHECK_STARTED", video, url });

  // Captions are read here, in the viewer's own session, because YouTube
  // blocks most datacenter IPs — a server-side fetch fails as soon as the
  // backend runs anywhere but localhost. The backend still has its own
  // fallback for when this comes back empty.
  void (async () => {
    let transcript: TranscriptSegment[] | undefined;
    try {
      transcript = (await withTimeout(fetchTranscript(videoId), TRANSCRIPT_TIMEOUT_MS)) ?? undefined;
    } catch {
      transcript = undefined;
    }
    send({ type: "TRANSCRIPT_READY", video, url, transcript });
  })();
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T | null> {
  return Promise.race([
    promise,
    new Promise<null>((resolve) => setTimeout(() => resolve(null), ms)),
  ]);
}

function setButtonState(label: string, disabled: boolean): void {
  if (!checkButton) return;
  checkButton.replaceChildren();
  const dot = document.createElement("span");
  dot.className = "ytf-check-dot";
  checkButton.append(dot, document.createTextNode(label));
  checkButton.disabled = disabled;
}

// YouTube's own action row, so the button sits beside Like and Share instead
// of floating over the video.
const ACTION_ROW_SELECTORS = [
  "ytd-watch-metadata #top-level-buttons-computed",
  "#above-the-fold #top-level-buttons-computed",
  "#top-level-buttons-computed",
];

function findActionRow(): HTMLElement | null {
  for (const selector of ACTION_ROW_SELECTORS) {
    const row = document.querySelector<HTMLElement>(selector);
    if (row) return row;
  }
  return null;
}

function injectCheckButton(): void {
  if (checkButton?.isConnected) return;

  const row = findActionRow();
  // The row renders after the player, so this simply retries on the next tick
  // rather than falling back to an overlay the viewer did not ask for.
  if (!row) return;

  const button = document.createElement("button");
  button.className = "ytf-check-button";
  button.type = "button";

  const dot = document.createElement("span");
  dot.className = "ytf-check-dot";
  button.append(dot, document.createTextNode("Check facts"));

  button.addEventListener("click", () => startCheck());
  row.append(button);
  checkButton = button;
}

function clearMarkers(): void {
  markerHost?.remove();
  markerHost = null;
}

function claimAtTime(seconds: number): Claim | null {
  for (const claim of flaggedClaims) {
    if (dismissed.has(claim.id)) continue;
    const until = Math.max(claim.endSeconds, claim.startSeconds + MIN_VISIBLE_SECONDS);
    if (seconds >= claim.startSeconds && seconds <= until) return claim;
  }
  return null;
}

function hidePopup(): void {
  popupHost?.remove();
  popupHost = null;
  popupClaimId = null;
}

function showPopup(claim: Claim): void {
  // Attach to the player itself, so the notice survives theater and
  // fullscreen, where YouTube reparents everything else.
  const player = document.querySelector<HTMLElement>("#movie_player");
  if (!player) return;

  hidePopup();
  popupClaimId = claim.id;

  const host = document.createElement("div");
  host.className = "ytf-popup";

  const head = document.createElement("div");
  head.className = "ytf-popup-head";
  const badge = document.createElement("span");
  badge.className = `ytf-popup-badge ytf-popup-${claim.verdict}`;
  badge.textContent = VERDICT_LABELS[claim.verdict] ?? claim.verdict;
  head.append(badge);

  const close = document.createElement("button");
  close.className = "ytf-popup-close";
  close.type = "button";
  close.textContent = "✕";
  close.title = "Dismiss for this claim";
  close.addEventListener("click", (event) => {
    event.stopPropagation();
    dismissed.add(claim.id);
    hidePopup();
  });
  head.append(close);
  host.append(head);

  const text = document.createElement("p");
  text.className = "ytf-popup-claim";
  text.textContent = claim.text;
  host.append(text);

  if (claim.basis) {
    const basis = document.createElement("p");
    basis.className = "ytf-popup-basis";
    basis.textContent = claim.basis;
    host.append(basis);
  }

  const foot = document.createElement("div");
  foot.className = "ytf-popup-foot";

  const verified = claim.evidence.find((item) => item.quoteVerified === true) ?? claim.evidence[0];
  if (verified) {
    const link = document.createElement("a");
    link.href = verified.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.className = "ytf-popup-link";
    link.textContent = `Source: ${verified.publisher}`;
    link.addEventListener("click", (event) => event.stopPropagation());
    foot.append(link);
  }

  const details = document.createElement("button");
  details.className = "ytf-popup-more";
  details.type = "button";
  details.textContent = "All sources";
  details.addEventListener("click", (event) => {
    event.stopPropagation();
    send({ type: "MARKER_CLICK", claimId: claim.id, startSeconds: claim.startSeconds });
  });
  foot.append(details);
  host.append(foot);

  player.append(host);
  popupHost = host;
}

function syncPopup(): void {
  if (!videoEl) return;
  const claim = claimAtTime(videoEl.currentTime);

  if (claim === null) {
    if (popupHost) hidePopup();
    return;
  }
  if (claim.id !== popupClaimId) showPopup(claim);
}

function attachPlaybackWatcher(): void {
  const video = document.querySelector<HTMLVideoElement>("video");
  if (!video || video === videoEl) return;
  videoEl = video;
  // timeupdate fires about four times a second, which is responsive enough
  // and cheap, since syncPopup only touches the DOM when the claim changes.
  video.addEventListener("timeupdate", syncPopup);
  video.addEventListener("seeking", () => {
    if (popupHost) hidePopup();
  });
}

function renderMarkers(claims: Claim[]): void {
  clearMarkers();
  const concerning = claims.filter((claim) => CONCERNING.includes(claim.verdict));
  flaggedClaims = concerning;
  attachPlaybackWatcher();
  if (concerning.length === 0) return;

  const progress = document.querySelector<HTMLElement>(".ytp-progress-bar-container");
  const video = document.querySelector<HTMLVideoElement>("video");
  if (!progress) return;
  markerHost = document.createElement("div");
  markerHost.className = "ytf-marker-host";
  const duration = video?.duration && Number.isFinite(video.duration)
    ? video.duration
    : Math.max(...concerning.map((claim) => claim.endSeconds), 1);

  for (const claim of concerning) {
    const marker = document.createElement("button");
    marker.type = "button";
    marker.className = `ytf-marker ytf-marker-${claim.verdict}`;
    marker.style.left = `${Math.min(99.5, Math.max(0.5, (claim.startSeconds / duration) * 100))}%`;
    marker.title = `${claim.verdict.replace("_", " ")}: ${claim.text}`;
    marker.setAttribute("aria-label", `Open ${claim.verdict.replace("_", " ")} claim`);
    marker.addEventListener("click", (event) => {
      event.stopPropagation();
      if (video) video.currentTime = claim.startSeconds;
      send({ type: "MARKER_CLICK", claimId: claim.id, startSeconds: claim.startSeconds });
    });
    markerHost.append(marker);
  }
  progress.append(markerHost);
}

function handleNavigation(): void {
  const nextId = getVideoId();
  if (nextId === currentVideoId) return;
  currentVideoId = nextId;
  send({ type: "VIDEO_CHANGED", video: nextId ? getVideoMetadata(nextId) : null });
  clearMarkers();
  hidePopup();
  flaggedClaims = [];
  dismissed.clear();
  videoEl = null;
  if (checkButton) {
    checkButton.remove();
    checkButton = null;
  }
  if (nextId) injectCheckButton();
}

chrome.runtime.onMessage.addListener((message: any) => {
  if (message.type === "RENDER_MARKERS") renderMarkers(message.claims as Claim[]);
  if (message.type === "START_CHECK") startCheck();
  if (message.type === "SEEK_TO") {
    const video = document.querySelector<HTMLVideoElement>("video");
    if (video) video.currentTime = message.seconds;
  }
});

const style = document.createElement("style");
style.textContent = `
  /* Borrows YouTube's own chip tokens so it follows the site's light and dark
     themes instead of imposing a palette of its own. */
  .ytf-check-button { display: inline-flex; align-items: center; gap: 7px; height: 36px; margin-left: 8px; padding: 0 16px; border: 0; border-radius: 18px; background: var(--yt-spec-badge-chip-background, #272727); color: var(--yt-spec-text-primary, #f1f1f1); font: 500 14px/1 Roboto, Arial, sans-serif; white-space: nowrap; cursor: pointer; }
  .ytf-check-button:hover { background: var(--yt-spec-10-percent-layer, #3f3f3f); }
  .ytf-check-button:disabled { cursor: default; opacity: .6; }
  .ytf-check-dot { width: 7px; height: 7px; border-radius: 50%; background: #3ea6ff; flex: none; }
  .ytf-check-button:disabled .ytf-check-dot { animation: ytf-pulse 1.4s ease-in-out infinite; }
  @keyframes ytf-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .25; } }
  .ytf-marker-host { position: absolute; inset: 0; pointer-events: none; z-index: 20; }
  .ytf-marker { position: absolute; top: 50%; transform: translate(-50%, -50%); width: 7px; height: 14px; padding: 0; border: 1px solid #fff; border-radius: 3px; pointer-events: auto; cursor: pointer; box-shadow: 0 0 3px #000; }
  .ytf-marker-false { height: 20px; width: 9px; background: #ef4444; }
  .ytf-marker-potentially_false { height: 16px; width: 8px; background: #f59e0b; border-radius: 1px; transform: translate(-50%, -50%) rotate(45deg); }
  .ytf-marker-misleading { height: 12px; width: 7px; background: #facc15; border-radius: 50%; border-style: dotted; }

  /* Sits above the control bar so it never covers the scrubber or captions. */
  .ytf-popup { position: absolute; left: 16px; bottom: 72px; z-index: 60; width: min(360px, 40%); padding: 14px; border-radius: 12px; background: #0f0f0fF2; color: #f1f1f1; font: 400 13px/1.5 Roboto, Arial, sans-serif; box-shadow: 0 6px 24px #0009; animation: ytf-pop .16s ease-out; }
  @keyframes ytf-pop { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
  .ytf-popup-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 9px; }
  .ytf-popup-badge { display: inline-flex; align-items: center; gap: 6px; color: #f1f1f1; font-size: 12px; font-weight: 500; }
  .ytf-popup-badge::before { width: 8px; height: 8px; border-radius: 2px; content: ""; background: currentColor; }
  .ytf-popup-false { color: #f05d5d; }
  .ytf-popup-potentially_false { color: #e5a33d; }
  .ytf-popup-misleading { color: #d9c04a; }
  .ytf-popup-close { border: 0; background: transparent; color: #909090; font-size: 14px; line-height: 1; padding: 2px 4px; cursor: pointer; }
  .ytf-popup-close:hover { color: #f1f1f1; }
  .ytf-popup-claim { margin: 0 0 7px; font-size: 14px; font-weight: 500; line-height: 1.4; }
  .ytf-popup-basis { margin: 0 0 12px; color: #aaa; font-size: 12.5px; }
  .ytf-popup-foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .ytf-popup-link { overflow: hidden; color: #3ea6ff; font-size: 12px; text-decoration: none; text-overflow: ellipsis; white-space: nowrap; }
  .ytf-popup-link:hover { text-decoration: underline; }
  .ytf-popup-more { border: 0; border-radius: 16px; padding: 6px 12px; background: #272727; color: #f1f1f1; font: 500 12px Roboto, Arial, sans-serif; cursor: pointer; white-space: nowrap; }
  .ytf-popup-more:hover { background: #3f3f3f; }
  .ytp-fullscreen .ytf-popup { bottom: 96px; width: min(420px, 32%); }
`;
document.documentElement.append(style);

window.addEventListener("yt-navigate-finish", handleNavigation);
window.addEventListener("popstate", handleNavigation);
setInterval(() => {
  handleNavigation();
  // YouTube re-renders the metadata row on its own, which detaches the button
  // without clearing the reference, so connectedness is what to test.
  if (currentVideoId && !checkButton?.isConnected) injectCheckButton();
  // The player element is replaced on navigation, so re-attach if needed.
  if (flaggedClaims.length > 0) attachPlaybackWatcher();
}, 1000);
handleNavigation();

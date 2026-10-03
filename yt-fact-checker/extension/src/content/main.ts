import type { Claim, RuntimeMessage, TranscriptSegment, VideoMetadata } from "../shared/types";

let currentVideoId: string | null = null;
let checkButton: HTMLButtonElement | null = null;
let markerHost: HTMLElement | null = null;

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

async function startCheck(): Promise<void> {
  const videoId = getVideoId();
  if (!videoId) return;
  const video = getVideoMetadata(videoId);
  send({ type: "CHECK_STARTED", video });
  setButtonState("Reading captions…", true);
  try {
    const transcript = await fetchTranscript(videoId);
    if (!transcript) {
      send({ type: "NO_TRANSCRIPT", video });
      setButtonState("No captions found", false);
      return;
    }
    send({ type: "TRANSCRIPT_READY", video, transcript });
    setButtonState("Checking…", true);
  } catch {
    send({ type: "NO_TRANSCRIPT", video });
    setButtonState("Could not read captions", false);
  }
}

function setButtonState(label: string, disabled: boolean): void {
  if (!checkButton) return;
  checkButton.textContent = label;
  checkButton.disabled = disabled;
}

function injectCheckButton(): void {
  if (checkButton || !document.body) return;
  checkButton = document.createElement("button");
  checkButton.className = "ytf-check-button";
  checkButton.type = "button";
  checkButton.textContent = "Check this video";
  checkButton.addEventListener("click", () => void startCheck());
  document.body.append(checkButton);
}

function clearMarkers(): void {
  markerHost?.remove();
  markerHost = null;
}

function renderMarkers(claims: Claim[]): void {
  clearMarkers();
  const concerning = claims.filter((claim) => ["false", "potentially_false", "misleading"].includes(claim.verdict));
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
  if (checkButton) {
    checkButton.remove();
    checkButton = null;
  }
  if (nextId) injectCheckButton();
}

chrome.runtime.onMessage.addListener((message: any) => {
  if (message.type === "RENDER_MARKERS") renderMarkers(message.claims as Claim[]);
  if (message.type === "START_CHECK") void startCheck();
  if (message.type === "SEEK_TO") {
    const video = document.querySelector<HTMLVideoElement>("video");
    if (video) video.currentTime = message.seconds;
  }
});

const style = document.createElement("style");
style.textContent = `
  .ytf-check-button { position: fixed; top: 76px; right: 24px; z-index: 2147483646; border: 0; border-radius: 999px; padding: 10px 16px; color: #fff; background: #635bff; font: 600 13px system-ui, sans-serif; box-shadow: 0 4px 14px #0005; cursor: pointer; }
  .ytf-check-button:hover { background: #5148e5; }
  .ytf-check-button:disabled { opacity: .7; cursor: wait; }
  .ytf-marker-host { position: absolute; inset: 0; pointer-events: none; z-index: 20; }
  .ytf-marker { position: absolute; top: 50%; transform: translate(-50%, -50%); width: 7px; height: 14px; padding: 0; border: 1px solid #fff; border-radius: 3px; pointer-events: auto; cursor: pointer; box-shadow: 0 0 3px #000; }
  .ytf-marker-false { height: 20px; width: 9px; background: #ef4444; }
  .ytf-marker-potentially_false { height: 16px; width: 8px; background: #f59e0b; border-radius: 1px; transform: translate(-50%, -50%) rotate(45deg); }
  .ytf-marker-misleading { height: 12px; width: 7px; background: #facc15; border-radius: 50%; border-style: dotted; }
`;
document.documentElement.append(style);

window.addEventListener("yt-navigate-finish", handleNavigation);
window.addEventListener("popstate", handleNavigation);
setInterval(() => {
  handleNavigation();
  if (currentVideoId && !checkButton) injectCheckButton();
}, 1000);
handleNavigation();

import type { Claim, RuntimeMessage, SessionState, Verdict } from "../shared/types";

const app = document.querySelector<HTMLElement>("#app")!;
const order: Verdict[] = ["false", "potentially_false", "misleading", "supported", "context_needed", "couldnt_verify"];
const labels: Record<Verdict, string> = {
  false: "False",
  potentially_false: "Potentially false",
  misleading: "Misleading",
  supported: "Supported",
  context_needed: "Context needed",
  couldnt_verify: "Couldn’t verify",
};

let state: SessionState = { status: "ready", claims: [], warnings: [] };

function send<T = unknown>(message: RuntimeMessage): Promise<T> {
  return new Promise((resolve) => chrome.runtime.sendMessage(message, resolve));
}

function formatTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

function textElement(tag: string, text: string, className?: string): HTMLElement {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

function renderClaim(claim: Claim): HTMLElement {
  const article = document.createElement("article");
  article.className = `claim ${claim.verdict}${state.selectedClaimId === claim.id ? " selected" : ""}`;
  article.id = `claim-${claim.id}`;

  const head = document.createElement("div");
  head.className = "claim-head";
  head.append(textElement("span", labels[claim.verdict], `badge ${claim.verdict}`));
  const timestamp = document.createElement("button");
  timestamp.className = "timestamp";
  timestamp.type = "button";
  timestamp.textContent = formatTime(claim.startSeconds);
  timestamp.title = "Jump to this moment in the video";
  timestamp.addEventListener("click", () => void send({ type: "SEEK_TO", seconds: claim.startSeconds }));
  head.append(timestamp);
  article.append(head);

  article.append(textElement("p", claim.text, "claim-text"));
  article.append(textElement("p", claim.basis, "basis"));

  const sources = document.createElement("div");
  sources.className = "evidence";
  for (const evidence of claim.evidence) {
    const link = document.createElement("a");
    link.href = evidence.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = `${evidence.title} · ${evidence.publisher}`;
    sources.append(link);
  }
  if (claim.evidence.length > 0) article.append(sources);
  else article.append(textElement("p", "No reliable evidence link was found.", "basis"));
  return article;
}

function render(): void {
  app.replaceChildren();
  const shell = document.createElement("section");
  shell.className = "shell";
  shell.append(textElement("p", "Evidence-first checks", "eyebrow"));
  shell.append(textElement("h1", "yt-fact-checker"));
  shell.append(textElement("p", "Check factual claims in this YouTube video. Open the sources and decide for yourself.", "intro"));

  const check = document.createElement("button");
  check.className = "check";
  check.type = "button";
  check.textContent = state.status === "loading_transcript" || state.status === "extracting_claims" || state.status === "gathering_evidence" || state.status === "reviewing_results"
    ? "Checking…"
    : "Check this video";
  check.disabled = check.textContent !== "Check this video";
  check.addEventListener("click", () => void send({ type: "START_CHECK" }));
  shell.append(check);

  if (state.video?.title) shell.append(textElement("p", state.video.title, "video-title"));

  const status = document.createElement("div");
  status.className = `status${state.status === "failed" ? " error" : state.status === "complete" ? " success" : ""}`;
  const statusText: Record<SessionState["status"], string> = {
    ready: "Nothing has been checked yet.",
    loading_transcript: "Reading the video's available captions…",
    extracting_claims: "Extracting checkable factual claims…",
    gathering_evidence: "Gathering evidence links…",
    reviewing_results: "Reviewing citations…",
    complete: `${state.claims.length} claim${state.claims.length === 1 ? "" : "s"} assessed.`,
    no_transcript: "This video cannot be checked because no usable transcript is available. Speech-to-text is not used.",
    no_claims: "No checkable factual claims were found.",
    failed: state.error ?? "The fact-checking service is unavailable. Try again.",
    unsupported: "Open a YouTube video to use the checker.",
  };
  status.textContent = statusText[state.status];
  shell.append(status);

  if (state.mode === "demo") {
    shell.append(textElement("p", "Demo fixture results — these claims are not a live check of the current video.", "warning"));
  }

  for (const warning of state.warnings) shell.append(textElement("p", warning, "warning"));

  const groups = order
    .map((verdict) => ({ verdict, claims: state.claims.filter((claim) => claim.verdict === verdict) }))
    .filter((group) => group.claims.length > 0);
  for (const group of groups) {
    const title = textElement("h2", labels[group.verdict], "group-title");
    title.append(textElement("span", String(group.claims.length)));
    shell.append(title);
    for (const claim of group.claims) shell.append(renderClaim(claim));
  }

  if (state.claims.length > 0) {
    const legend = document.createElement("div");
    legend.className = "legend";
    legend.append(textElement("span", "False", "false"), textElement("span", "Potentially false", "potentially_false"), textElement("span", "Misleading", "misleading"));
    shell.append(legend);
  } else if (state.status === "ready") {
    shell.append(textElement("p", "False and misleading moments will be marked on the video timeline after a check.", "empty"));
  }
  app.append(shell);

  if (state.selectedClaimId) {
    document.querySelector(`#claim-${CSS.escape(state.selectedClaimId)}`)?.scrollIntoView({ block: "nearest" });
  }
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "session" || !changes.state?.newValue) return;
  state = changes.state.newValue as SessionState;
  render();
});

void send<SessionState>({ type: "GET_STATE" }).then((next) => {
  if (next) state = next;
  render();
});

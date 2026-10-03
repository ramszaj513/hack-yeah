import type { Claim, Evidence, RuntimeMessage, SessionState, UnverifiedReason, Verdict } from "../shared/types";

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

/** Why a claim went unresolved. These are very different situations and
 *  collapsing them into one label would overstate what we actually know. */
const reasons: Record<UnverifiedReason, string> = {
  no_evidence_found: "No source addressing this was found — that is not evidence it is false.",
  sources_conflict: "Reliable sources disagree, so no verdict is reported.",
  evidence_not_specific: "The sources found do not address this particular point.",
  citation_unverifiable: "The quoted passage could not be found on the cited pages.",
  provider_error: "An evidence provider failed, so this claim was not assessed.",
  claim_ambiguous: "The claim is too ambiguous to check as stated.",
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

  if (claim.quote && claim.quote.trim()) {
    article.append(textElement("p", `“${claim.quote}”`, "said"));
  }

  article.append(textElement("p", claim.basis, "basis"));

  if (claim.unverifiedReason) {
    article.append(textElement("p", reasons[claim.unverifiedReason], "warning"));
  }

  const sources = document.createElement("div");
  sources.className = "evidence";
  for (const evidence of claim.evidence) sources.append(renderEvidence(evidence));

  if (claim.evidence.length > 0) article.append(sources);
  else article.append(textElement("p", "No reliable evidence link was found.", "basis"));
  return article;
}

function renderEvidence(evidence: Evidence): HTMLElement {
  const row = document.createElement("div");
  row.className = "evidence-row";

  const link = document.createElement("a");
  link.href = evidence.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = `${evidence.title} · ${evidence.publisher}`;
  row.append(link);

  const meta = document.createElement("div");
  meta.className = "evidence-meta";
  meta.append(textElement("span", evidence.sourceType.replace("_", " "), `tag tag-${evidence.sourceType}`));

  if (evidence.supports === "contradicts") {
    meta.append(textElement("span", "contradicts claim", "tag tag-contradicts"));
  }

  // Whether we could confirm the quoted passage is actually on the page. This
  // is a mechanical check, not a judgement about the source's reliability.
  if (evidence.quoteVerified === true) {
    meta.append(textElement("span", "quote verified", "tag tag-verified"));
  } else if (evidence.quoteVerified === false) {
    meta.append(textElement("span", "quote not found on page", "tag tag-unverified"));
  } else {
    meta.append(textElement("span", "page unreachable", "tag tag-unknown"));
  }

  row.append(meta);

  if (evidence.snippet && evidence.snippet.trim()) {
    row.append(textElement("p", `“${evidence.snippet}”`, "evidence-quote"));
  }
  return row;
}

function render(): void {
  app.replaceChildren();
  const shell = document.createElement("section");
  shell.className = "shell";
  const header = document.createElement("div");
  header.className = "claim-head";
  const titles = document.createElement("div");
  titles.append(textElement("p", "Evidence-first checks", "eyebrow"), textElement("h1", "yt-fact-checker"));
  const privacy = document.createElement("button");
  privacy.className = "timestamp";
  privacy.type = "button";
  privacy.textContent = "Privacy";
  privacy.addEventListener("click", () => chrome.runtime.openOptionsPage());
  header.append(titles, privacy);
  shell.append(header);
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

  // Gathering evidence for a long video runs for minutes. Without a count the
  // panel looks frozen, which is how a working check gets mistaken for a hang.
  const progress = state.progress;
  if (progress && progress.total > 0 && state.status !== "complete") {
    const label = progress.stage === "evidence" ? "sources gathered" : "claims assessed";
    status.append(textElement("span", `${progress.done} of ${progress.total} ${label}`, "progress"));

    const track = document.createElement("div");
    track.className = "progress-track";
    const fill = document.createElement("div");
    fill.className = "progress-fill";
    fill.style.width = `${Math.round((progress.done / progress.total) * 100)}%`;
    track.append(fill);
    status.append(track);
  }

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

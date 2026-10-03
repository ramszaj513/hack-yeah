import type {
  Claim,
  Evidence,
  RuntimeMessage,
  SessionState,
  Settings,
  Signal,
  Technique,
  UnverifiedReason,
  Verdict,
} from "../shared/types";
import { DEFAULT_SETTINGS } from "../shared/types";

const app = document.querySelector<HTMLElement>("#app")!;

const order: Verdict[] = [
  "false",
  "potentially_false",
  "misleading",
  "supported",
  "context_needed",
  "couldnt_verify",
];

const labels: Record<Verdict, string> = {
  false: "False",
  potentially_false: "Doubtful",
  misleading: "Misleading",
  supported: "Checks out",
  context_needed: "Needs context",
  couldnt_verify: "Unverified",
};

/** Shown only on a claim that went unresolved, where the reason changes how
 *  much weight the result deserves. Everything else is left unexplained. */
const reasons: Record<UnverifiedReason, string> = {
  no_evidence_found: "Nothing found either way.",
  sources_conflict: "Reliable sources disagree.",
  evidence_not_specific: "Sources don't address this point.",
  citation_unverifiable: "Quotes weren't on the cited pages.",
  provider_error: "A source lookup failed.",
  claim_ambiguous: "Too ambiguous to check.",
};

const techniques: Record<Technique, string> = {
  undisclosed_ad: "Undisclosed promotion",
  emotional_manipulation: "Emotional pressure",
  loaded_language: "Loaded language",
  logical_fallacy: "Faulty reasoning",
  cherry_picking: "Selective evidence",
  conspiracy_framing: "Conspiracy framing",
  political_framing: "One-sided framing",
  unfalsifiable: "Unfalsifiable",
};

let state: SessionState = { status: "ready", claims: [], signals: [], warnings: [] };
let settings: Settings = DEFAULT_SETTINGS;
let settingsOpen = false;

function send<T = unknown>(message: RuntimeMessage): Promise<T> {
  return new Promise((resolve) => chrome.runtime.sendMessage(message, resolve));
}

function formatTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

function el(tag: string, text: string, className?: string): HTMLElement {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

function iconButton(label: string, title: string, onClick: () => void): HTMLButtonElement {
  const button = document.createElement("button");
  button.className = "icon";
  button.type = "button";
  button.textContent = label;
  button.title = title;
  button.setAttribute("aria-label", title);
  button.addEventListener("click", onClick);
  return button;
}

function seekButton(seconds: number): HTMLButtonElement {
  const button = document.createElement("button");
  button.className = "timestamp";
  button.type = "button";
  button.textContent = formatTime(seconds);
  button.title = "Jump here";
  button.addEventListener("click", () => void send({ type: "SEEK_TO", seconds }));
  return button;
}

function renderEvidence(evidence: Evidence): HTMLElement {
  const row = document.createElement("div");
  row.className = "evidence-row";

  const link = document.createElement("a");
  link.href = evidence.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = evidence.publisher;
  row.append(link);

  const meta = document.createElement("div");
  meta.className = "evidence-meta";
  meta.append(el("span", evidence.sourceType.replace("_", " "), "tag"));
  if (evidence.supports === "contradicts") meta.append(el("span", "against", "tag tag-contradicts"));
  // Only the confirmed case is worth a word; silence covers the rest.
  if (evidence.quoteVerified === true) meta.append(el("span", "quote checked", "tag tag-verified"));
  else if (evidence.quoteVerified === false) meta.append(el("span", "quote not found", "tag tag-unverified"));
  row.append(meta);

  if (evidence.snippet.trim()) row.append(el("p", `“${evidence.snippet}”`, "evidence-quote"));
  return row;
}

function renderClaim(claim: Claim): HTMLElement {
  const article = document.createElement("article");
  article.className = `claim ${claim.verdict}${state.selectedClaimId === claim.id ? " selected" : ""}`;
  article.id = `claim-${claim.id}`;

  const head = document.createElement("div");
  head.className = "claim-head";
  head.append(el("span", labels[claim.verdict], `badge ${claim.verdict}`), seekButton(claim.startSeconds));
  article.append(head, el("p", claim.text, "claim-text"));

  if (claim.basis) article.append(el("p", claim.basis, "basis"));
  if (claim.unverifiedReason) article.append(el("p", reasons[claim.unverifiedReason], "reason"));

  if (claim.evidence.length > 0) {
    const sources = document.createElement("div");
    sources.className = "evidence";
    for (const item of claim.evidence) sources.append(renderEvidence(item));
    article.append(sources);
  }
  return article;
}

function renderSignal(signal: Signal): HTMLElement {
  const article = document.createElement("article");
  article.className = `claim signal severity-${signal.severity}`;

  const head = document.createElement("div");
  head.className = "claim-head";
  head.append(el("span", techniques[signal.technique], "badge signal"), seekButton(signal.startSeconds));
  article.append(head, el("p", signal.note, "claim-text"), el("p", `“${signal.quote}”`, "said"));
  return article;
}

function renderSettings(): HTMLElement {
  const box = document.createElement("div");
  box.className = "settings";

  const options: Array<[keyof Settings, string]> = [
    ["popups", "Notices over the video"],
    ["hideSupported", "Hide claims that check out"],
    ["showSignals", "Flag manipulation and hidden ads"],
    ["strongSignalsOnly", "Only the clearest of those"],
  ];

  for (const [key, label] of options) {
    const row = document.createElement("label");
    row.className = "setting";

    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = Boolean(settings[key]);
    input.addEventListener("change", () => {
      settings = { ...settings, [key]: input.checked };
      void send({ type: "SET_SETTINGS", settings });
      render();
    });

    row.append(input, el("span", label));
    box.append(row);
  }
  return box;
}

function visibleClaims(): Claim[] {
  if (!settings.hideSupported) return state.claims;
  return state.claims.filter((claim) => claim.verdict !== "supported");
}

function visibleSignals(): Signal[] {
  if (!settings.showSignals) return [];
  const all = state.signals ?? [];
  return settings.strongSignalsOnly ? all.filter((item) => item.severity !== "low") : all;
}

const BUSY: SessionState["status"][] = [
  "loading_transcript",
  "extracting_claims",
  "gathering_evidence",
  "reviewing_results",
];

function statusLine(): string {
  switch (state.status) {
    case "ready":
      return "";
    case "loading_transcript":
      return "Reading captions";
    case "extracting_claims":
      return "Finding claims";
    case "gathering_evidence":
      return "Gathering sources";
    case "reviewing_results":
      return "Checking quotes";
    case "complete":
      return "";
    case "no_transcript":
      return "This video has no usable captions.";
    case "no_claims":
      return "No checkable claims here.";
    case "unsupported":
      return "Open a YouTube video.";
    case "failed":
      return state.error ?? "Couldn't reach the checker.";
  }
}

function render(): void {
  app.replaceChildren();

  const shell = document.createElement("section");
  shell.className = "shell";

  const header = document.createElement("div");
  header.className = "header";
  header.append(el("h1", "Fact check"));

  const tools = document.createElement("div");
  tools.className = "tools";
  tools.append(
    iconButton("⚙", "Settings", () => {
      settingsOpen = !settingsOpen;
      render();
    }),
    iconButton("✕", "Close", () => window.close()),
  );
  header.append(tools);
  shell.append(header);

  if (settingsOpen) shell.append(renderSettings());

  const busy = BUSY.includes(state.status);
  const claims = visibleClaims();
  const signals = visibleSignals();

  if (state.status === "ready" || state.status === "unsupported") {
    const check = document.createElement("button");
    check.className = "check";
    check.type = "button";
    check.textContent = "Check this video";
    check.disabled = state.status === "unsupported";
    check.addEventListener("click", () => void send({ type: "START_CHECK" }));
    shell.append(check);
  }

  const line = statusLine();
  if (line) {
    const status = document.createElement("div");
    status.className = `status${state.status === "failed" ? " error" : ""}`;
    status.append(el("span", line, "status-label"));

    const progress = state.progress;
    if (busy && progress && progress.total > 0) {
      status.append(el("span", `${progress.done}/${progress.total}`, "progress"));
      const track = document.createElement("div");
      track.className = "progress-track";
      const fill = document.createElement("div");
      fill.className = "progress-fill";
      fill.style.width = `${Math.round((progress.done / progress.total) * 100)}%`;
      track.append(fill);
      status.append(track);
    }
    shell.append(status);
  }

  if (state.mode === "demo") shell.append(el("p", "Sample results, not a real check.", "warning"));
  for (const warning of state.warnings) shell.append(el("p", warning, "warning"));

  for (const verdict of order) {
    const group = claims.filter((claim) => claim.verdict === verdict);
    if (group.length === 0) continue;
    const title = el("h2", labels[verdict], "group-title");
    title.append(el("span", String(group.length)));
    shell.append(title);
    for (const claim of group) shell.append(renderClaim(claim));
  }

  if (signals.length > 0) {
    const title = el("h2", "How it's argued", "group-title");
    title.append(el("span", String(signals.length)));
    shell.append(title);
    for (const signal of signals) shell.append(renderSignal(signal));
  }

  if (state.status === "complete" && claims.length === 0 && signals.length === 0) {
    shell.append(el("p", "Nothing to flag.", "empty"));
  }

  app.append(shell);

  if (state.selectedClaimId) {
    document
      .querySelector(`#claim-${CSS.escape(state.selectedClaimId)}`)
      ?.scrollIntoView({ block: "nearest" });
  }
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "session" && changes.state?.newValue) {
    state = changes.state.newValue as SessionState;
    render();
  }
  if (area === "local" && changes.settings?.newValue) {
    settings = { ...DEFAULT_SETTINGS, ...(changes.settings.newValue as Partial<Settings>) };
    render();
  }
});

void (async () => {
  settings = (await send<Settings>({ type: "GET_SETTINGS" })) ?? DEFAULT_SETTINGS;
  const next = await send<SessionState>({ type: "GET_STATE" });
  if (next) state = next;
  render();
})();

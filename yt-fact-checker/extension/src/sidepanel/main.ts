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
const textLabels: Record<Verdict, string> = {
  false: "Fałszywe", potentially_false: "Wątpliwe", misleading: "Wprowadzające w błąd",
  supported: "Potwierdzone", context_needed: "Wymaga kontekstu", couldnt_verify: "Nie udało się zweryfikować",
};
function verdictLabel(verdict: Verdict): string {
  return state.textSelection ? textLabels[verdict] : labels[verdict];
}

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
const textTechniques: Record<Technique, string> = {
  undisclosed_ad: "Ukryta promocja", emotional_manipulation: "Presja emocjonalna",
  loaded_language: "Język sugerujący ocenę", logical_fallacy: "Błąd logiczny",
  cherry_picking: "Wybiórcze dowody", conspiracy_framing: "Narracja spiskowa",
  political_framing: "Jednostronne przedstawienie", unfalsifiable: "Twierdzenie nieweryfikowalne",
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

const ICONS = {
  // Drawn rather than typed: an emoji glyph carries its own colour and ignores
  // the stylesheet, so it never matched anything else in the panel.
  settings: "M4 7h10M4 12h7M4 17h12M16 5v4M13 10v4M18 15v4",
  close: "M6 6l12 12M18 6L6 18",
};

function iconButton(path: string, title: string, onClick: () => void): HTMLButtonElement {
  const button = document.createElement("button");
  button.className = "icon";
  button.type = "button";
  button.title = title;
  button.setAttribute("aria-label", title);

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.6");
  svg.setAttribute("stroke-linecap", "round");

  const shape = document.createElementNS("http://www.w3.org/2000/svg", "path");
  shape.setAttribute("d", path);
  svg.append(shape);

  button.append(svg);
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
  head.append(el("span", verdictLabel(claim.verdict), `badge ${claim.verdict}`));
  if (!state.textSelection) head.append(seekButton(claim.startSeconds));
  article.append(head, el("p", claim.text, "claim-text"));
  if (state.textSelection && claim.quote) article.append(el("p", `“${claim.quote}”`, "said"));

  if (claim.basis) article.append(el("p", claim.basis, "basis"));
  if (state.textSelection && claim.verdict !== "couldnt_verify") {
    const certainty = claim.confidence >= .8 ? "wysoka" : claim.confidence >= .5 ? "umiarkowana" : "niska";
    article.append(el("p", `Pewność oceny modelu: ${certainty}. To nie jest prawdopodobieństwo prawdziwości.`, "reason"));
  }
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
  head.append(el("span", state.textSelection ? textTechniques[signal.technique] : techniques[signal.technique], "badge signal"));
  if (!state.textSelection) head.append(seekButton(signal.startSeconds));
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
  if (state.textSelection) {
    switch (state.status) {
      case "extracting_claims": return "Wyszukiwanie twierdzeń w zaznaczeniu…";
      case "gathering_evidence": return "Zbieranie źródeł…";
      case "reviewing_results": return "Sprawdzanie dowodów i cytatów…";
      case "no_claims": return "Ten fragment nie zawiera faktów możliwych do sprawdzenia. Może być opinią lub oceną.";
      case "failed": return state.error ?? "Nie udało się sprawdzić tekstu.";
    }
  }
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
  header.append(el("h1", state.textSelection ? "Weryfikacja tekstu" : "Fact check"));

  const tools = document.createElement("div");
  tools.className = "tools";
  tools.append(
    iconButton(ICONS.settings, "Settings", () => {
      settingsOpen = !settingsOpen;
      render();
    }),
    iconButton(ICONS.close, "Close", () => window.close()),
  );
  header.append(tools);
  shell.append(header);

  if (settingsOpen) shell.append(renderSettings());

  const busy = BUSY.includes(state.status);
  const claims = visibleClaims();
  const signals = visibleSignals();

  if (state.textSelection) {
    const selection = state.textSelection;
    const summary = document.createElement("section");
    summary.className = "selection-summary";
    summary.append(el("p", "Zaznaczony fragment", "selection-label"));
    summary.append(el("blockquote", selection.text, "selection-quote"));
    const source = document.createElement("a");
    if (/^https?:\/\//.test(selection.pageUrl)) source.href = selection.pageUrl;
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    source.textContent = selection.pageTitle || new URL(selection.pageUrl).hostname;
    summary.append(source);
    shell.append(summary);
    shell.append(el("p", "Analizujemy wybrany fragment i najbliższy kontekst. Ocena sposobu argumentacji nie jest dowodem fałszu.", "warning"));
    const actions = document.createElement("div");
    actions.className = "text-actions";
    const retry = document.createElement("button");
    retry.className = "check"; retry.type = "button";
    retry.textContent = "Sprawdź ponownie"; retry.disabled = busy;
    retry.addEventListener("click", () => void send({ type: "RETRY_TEXT" }));
    actions.append(retry);
    if (!busy && state.claims.length > 0) {
      const copy = document.createElement("button");
      copy.className = "check"; copy.type = "button"; copy.textContent = "Kopiuj wynik";
      copy.addEventListener("click", () => {
        const report = [selection.text, selection.pageUrl, ...state.claims.map(claim =>
          `${verdictLabel(claim.verdict)}: ${claim.text}\n${claim.basis}\n${claim.evidence.map(item => item.url).join("\n")}`),
          ...state.warnings].join("\n\n");
        void navigator.clipboard.writeText(report).then(() => { copy.textContent = "Skopiowano"; })
          .catch(() => { copy.textContent = "Nie udało się skopiować"; });
      });
      actions.append(copy);
    }
    shell.append(actions);
  }

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
    const title = el("h2", verdictLabel(verdict), "group-title");
    title.append(el("span", String(group.length)));
    shell.append(title);
    for (const claim of group) shell.append(renderClaim(claim));
  }

  if (signals.length > 0) {
    const title = el("h2", state.textSelection ? "Sposób argumentacji" : "How it's argued", "group-title");
    title.append(el("span", String(signals.length)));
    shell.append(title);
    for (const signal of signals) shell.append(renderSignal(signal));
  }

  if (state.status === "complete" && claims.length === 0 && signals.length === 0) {
    shell.append(el("p", state.textSelection ? "Brak widocznych wyników. To nie oznacza, że cały fragment został potwierdzony." : "Nothing to flag.", "empty"));
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

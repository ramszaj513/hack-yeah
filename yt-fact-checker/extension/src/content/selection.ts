import type { RuntimeMessage, SessionState, TextSelection } from "../shared/types";
import { textSummary } from "../shared/textSummary";

const host = document.createElement("div");
host.style.cssText = "all:initial;position:fixed!important;z-index:2147483647!important;display:none!important;pointer-events:auto!important";
const root = host.attachShadow({ mode: "closed" });
const style = document.createElement("style");
style.textContent = `
  :host { color-scheme:dark; } * { box-sizing:border-box; }
  [hidden] { display:none!important; }
  button { font:600 13px/1.4 system-ui,sans-serif; cursor:pointer; }
  .trigger { padding:10px 15px; border:1px solid #42648b; border-radius:20px; background:#142336; color:#eef6ff; box-shadow:0 4px 18px #0005; }
  button:focus-visible { outline:3px solid #69b6ff; outline-offset:2px; } button:disabled { cursor:default; opacity:.7; }
  .card { width:min(350px,calc(100vw - 24px)); max-height:calc(100vh - 24px); overflow:auto; padding:18px;
    background:#151a22; color:#eef3fa; border:1px solid #354051; border-radius:16px; box-shadow:0 10px 36px #0005; font:400 13px/1.55 system-ui,sans-serif; }
  .top { display:flex; align-items:center; justify-content:space-between; gap:16px; color:#a8b7cc; font-size:11px; letter-spacing:.04em; }
  .close { border:0; background:transparent; color:#bbc6d5; font-size:22px; padding:0 4px; line-height:1; }
  h2 { margin:12px 0 8px; font-size:17px; line-height:1.35; font-weight:650; }
  h2[data-tone=positive] { color:#8ddbb3; } h2[data-tone=caution] { color:#f2cf85; } h2[data-tone=danger] { color:#ffa6a6; }
  p { margin:0; color:#c6cfdd; } .meta { margin-top:14px; font-size:11px; color:#97a7bd; }
  .signal { margin-top:10px; font-size:12px; color:#c5b4e8; } .actions { display:flex; gap:8px; margin-top:14px; }
  .details,.retry { padding:9px 12px; border:1px solid #45546b; border-radius:9px; background:#243247; color:#e9f2ff; }
  .details { flex:1; } .details:hover,.retry:hover { background:#304461; }
  .loading { display:flex; align-items:center; gap:9px; margin-top:12px; color:#a9c9f4; font-size:12px; }
  .spinner { width:14px; height:14px; border:2px solid #425770; border-top-color:#9dc9ff; border-radius:50%; animation:spin .85s linear infinite; flex:none; }
  @keyframes spin { to { transform:rotate(360deg); } }
  @media(prefers-reduced-motion:reduce) { .spinner { animation:none; } }
`;
const trigger = document.createElement("button");
trigger.className = "trigger"; trigger.type = "button"; trigger.textContent = "Zweryfikuj";
trigger.title = "Wyślij zaznaczony fragment i jego najbliższy kontekst do analizy";
const card = document.createElement("section");
card.className = "card"; card.hidden = true;
card.setAttribute("role", "region"); card.setAttribute("aria-label", "Podsumowanie weryfikacji");
// Build DOM nodes directly: pages such as YouTube can enforce Trusted Types
// and reject innerHTML, even for our static popup markup.
function node<K extends keyof HTMLElementTagNameMap>(tag: K, className = "", text = ""): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}
const top = node("div", "top");
const closeButton = node("button", "close", "×");
closeButton.type = "button"; closeButton.setAttribute("aria-label", "Zamknij");
top.append(node("span", "", "WERYFIKACJA FRAGMENTU"), closeButton);
const status = node("div");
status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
const heading = node("h2");
const body = node("p", "body");
status.append(heading, body);
const loading = node("div", "loading");
const loadingText = node("span", "", "Analiza w toku…");
const spinner = node("span", "spinner"); spinner.setAttribute("aria-hidden", "true");
loading.append(spinner, loadingText);
const meta = node("p", "meta");
const signal = node("p", "signal");
const details = node("button", "details", "Zobacz szczegóły →"); details.type = "button";
const retry = node("button", "retry", "Ponów"); retry.type = "button";
const actions = node("div", "actions"); actions.append(retry, details);
card.append(top, status, loading, signal, meta, actions);
root.append(style, trigger, card); document.documentElement.append(host);
let selection: TextSelection | null = null;
let timer: ReturnType<typeof setTimeout>;
let runId = "";
let dismissed = "";
let cardMode = false;
let anchor = { right: innerWidth - 16, bottom: 72 };
function hide(): void { host.style.setProperty("display", "none", "important"); }
function place(): void {
  const size = host.getBoundingClientRect();
  host.style.left = `${Math.max(12, Math.min(anchor.right - size.width, innerWidth - size.width - 12))}px`;
  host.style.top = `${Math.max(12, Math.min(anchor.bottom + 8, innerHeight - size.height - 12))}px`;
}
function close(): void {
  clearTimeout(timer);
  dismissed = runId;
  if (root.activeElement instanceof HTMLElement) root.activeElement.blur();
  hide(); cardMode = false;
}
function editable(node: Node | null): boolean {
  const element = node instanceof Element ? node : node?.parentElement;
  return Boolean(element?.closest('input, textarea, [contenteditable]:not([contenteditable="false"])'));
}
function showSelection(): void {
  if (cardMode || root.activeElement) return;
  const selected = window.getSelection();
  const text = selected?.toString().trim() ?? "";
  if (!selected?.rangeCount || text.length < 30 || editable(selected.anchorNode) || editable(selected.focusNode)) { hide(); return; }
  const range = selected.getRangeAt(0);
  const bounds = range.getBoundingClientRect();
  if (!bounds.width && !bounds.height) { hide(); return; }
  anchor = bounds;
  const surrounding = range.commonAncestorContainer.textContent ?? "";
  const index = surrounding.indexOf(text);
  const context = index >= 0 ? `${surrounding.slice(Math.max(0, index - 500), index)}\n[Selected fragment]\n${surrounding.slice(index + text.length, index + text.length + 500)}` : "";
  const url = new URL(location.href); url.search = ""; url.hash = "";
  selection = { text, pageUrl: url.href, pageTitle: document.title.slice(0, 500), context };
  trigger.disabled = text.length > 3000;
  trigger.textContent = trigger.disabled ? "Zaznacz maks. 3000 znaków" : "Zweryfikuj";
  trigger.hidden = false; card.hidden = true; host.style.setProperty("display", "block", "important"); place();
}
function render(state: SessionState): void {
  const summary = textSummary(state);
  heading.textContent = summary.title; heading.dataset.tone = summary.tone;
  body.textContent = state.error === "Zaznacz od 30 do 3000 znaków." ? state.error : summary.body;
  meta.textContent = summary.pending ? "Wynik pojawi się tutaj po zakończeniu analizy." : summary.meta;
  signal.textContent = summary.signal; signal.hidden = !summary.signal;
  loading.hidden = !summary.pending;
  loadingText.textContent = state.progress && state.progress.total > 0
    ? `Analiza w toku: ${state.progress.done}/${state.progress.total}` : "Analiza w toku…";
  retry.hidden = state.status !== "failed"; details.disabled = !runId;
  card.hidden = false; trigger.hidden = true; cardMode = true;
  const parent = document.fullscreenElement ?? document.documentElement;
  if (host.parentElement !== parent) parent.append(host);
  host.style.setProperty("display", "block", "important"); place();
}
function start(): void {
  if (!selection) return;
  dismissed = ""; runId = "";
  render({ status: "extracting_claims", claims: [], signals: [], warnings: [] });
  void chrome.runtime.sendMessage({ type: "CHECK_TEXT", selection } satisfies RuntimeMessage).catch(() => {
    heading.textContent = "Odśwież stronę";
    body.textContent = "Rozszerzenie zostało przeładowane. Odśwież stronę i spróbuj ponownie.";
  });
}
trigger.addEventListener("pointerdown", event => event.preventDefault());
trigger.addEventListener("click", () => { if (!trigger.disabled) start(); });
retry.addEventListener("click", start);
closeButton.addEventListener("click", close);
details.addEventListener("click", () => {
  void chrome.runtime.sendMessage({ type: "OPEN_TEXT_DETAILS", runId } satisfies RuntimeMessage)
    .then(response => { if (response?.error) { body.textContent = response.error; retry.hidden = false; } })
    .catch(() => { body.textContent = "Nie udało się otworzyć szczegółów. Odśwież stronę."; });
});
chrome.runtime.onMessage.addListener((message, _sender, respond) => {
  if (message.type === "TEXT_CHECK_PING") { respond({ ok: true }); return false; }
  if (message.type !== "TEXT_CHECK_UPDATE") return false;
  const state = message.state as SessionState;
  if (!state.textRunId || !state.textSelection) return false;
  if (message.show) { runId = state.textRunId; dismissed = ""; selection = state.textSelection; }
  if (runId !== state.textRunId || dismissed === runId) return false;
  render(state); respond({ ok: true }); return false;
});
document.addEventListener("selectionchange", () => { clearTimeout(timer); timer = setTimeout(showSelection, 180); });
document.addEventListener("mouseup", event => { if (event.button === 0 && !event.composedPath().includes(host)) showSelection(); });
document.addEventListener("pointerdown", event => { if (!event.composedPath().includes(host) && !cardMode) hide(); });
document.addEventListener("keydown", event => { if (event.key === "Escape") close(); });
window.addEventListener("scroll", () => { if (!cardMode) hide(); }, true);
window.addEventListener("resize", () => { if (cardMode) place(); else hide(); });
document.addEventListener("fullscreenchange", () => {
  const parent = document.fullscreenElement ?? document.documentElement;
  parent.append(host);
  if (cardMode) place();
});

import type { RuntimeMessage, SessionState, TextSelection } from "../shared/types";
import { textSummary } from "../shared/textSummary";

const host = document.createElement("div");
host.style.cssText = "position:fixed;z-index:2147483647;display:none";
const root = host.attachShadow({ mode: "closed" });
const style = document.createElement("style");
style.textContent = `
  :host { color-scheme:dark; } * { box-sizing:border-box; }
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
`;
const trigger = document.createElement("button");
trigger.className = "trigger"; trigger.type = "button"; trigger.textContent = "Zweryfikuj";
trigger.title = "Wyślij zaznaczony fragment i jego najbliższy kontekst do analizy";
const card = document.createElement("section");
card.className = "card"; card.hidden = true;
card.setAttribute("role", "region"); card.setAttribute("aria-label", "Podsumowanie weryfikacji");
// Static markup only; all page and result text is assigned with textContent.
card.innerHTML = `<div class="top"><span>WERYFIKACJA FRAGMENTU</span><button type="button" class="close" aria-label="Zamknij">×</button></div>
  <div role="status" aria-live="polite"><h2></h2><p class="body"></p></div>
  <p class="signal"></p><p class="meta"></p><div class="actions"><button type="button" class="retry">Ponów</button><button type="button" class="details">Zobacz szczegóły →</button></div>`;
const heading = card.querySelector("h2")!;
const body = card.querySelector<HTMLElement>(".body")!;
const meta = card.querySelector<HTMLElement>(".meta")!;
const signal = card.querySelector<HTMLElement>(".signal")!;
const details = card.querySelector<HTMLButtonElement>(".details")!;
const retry = card.querySelector<HTMLButtonElement>(".retry")!;
root.append(style, trigger, card); document.documentElement.append(host);
let selection: TextSelection | null = null;
let timer: ReturnType<typeof setTimeout>;
let runId = "";
let dismissed = "";
let cardMode = false;
let anchor = { right: innerWidth - 16, bottom: 72 };
function hide(): void { host.style.display = "none"; }
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
  trigger.hidden = false; card.hidden = true; host.style.display = "block"; place();
}
function render(state: SessionState): void {
  const summary = textSummary(state);
  heading.textContent = summary.title; heading.dataset.tone = summary.tone;
  body.textContent = state.error === "Zaznacz od 30 do 3000 znaków." ? state.error : summary.body;
  meta.textContent = summary.pending ? "Wynik pojawi się tutaj po zakończeniu analizy." : summary.meta;
  signal.textContent = summary.signal; signal.hidden = !summary.signal;
  retry.hidden = state.status !== "failed"; details.disabled = !runId;
  card.hidden = false; trigger.hidden = true; cardMode = true; host.style.display = "block"; place();
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
card.querySelector(".close")!.addEventListener("click", close);
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
  render(state); return false;
});
document.addEventListener("selectionchange", () => { clearTimeout(timer); timer = setTimeout(showSelection, 180); });
document.addEventListener("mouseup", event => { if (event.button === 0 && !event.composedPath().includes(host)) showSelection(); });
document.addEventListener("pointerdown", event => { if (!event.composedPath().includes(host) && !cardMode) hide(); });
document.addEventListener("keydown", event => { if (event.key === "Escape") close(); });
window.addEventListener("scroll", () => { if (!cardMode) hide(); }, true);
window.addEventListener("resize", () => { if (cardMode) place(); else hide(); });

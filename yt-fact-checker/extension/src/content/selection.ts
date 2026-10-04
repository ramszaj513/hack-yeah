import type { RuntimeMessage, TextSelection } from "../shared/types";

// An isolated shadow tree prevents the host page's button styles leaking in.
const host = document.createElement("div");
host.style.cssText = "position:fixed;z-index:2147483647;display:none";
const root = host.attachShadow({ mode: "closed" });
const style = document.createElement("style");
style.textContent = `
  button { all:initial; box-sizing:border-box; display:block; padding:10px 15px;
    border:1px solid #42648b; border-radius:20px; background:#142336; color:#eef6ff;
    font:600 13px/1.3 system-ui,sans-serif; box-shadow:0 4px 18px #0005; cursor:pointer; }
  button:hover { background:#203953; }
  button:focus-visible { outline:3px solid #69b6ff; outline-offset:2px; }
  button:disabled { cursor:default; opacity:.8; }
`;
const button = document.createElement("button");
button.type = "button";
button.textContent = "Zweryfikuj";
button.title = "Wyślij zaznaczony fragment i jego najbliższy kontekst do analizy";
root.append(style, button);
document.documentElement.append(host);
let selection: TextSelection | null = null;
let timer: ReturnType<typeof setTimeout>;

function hide(): void { host.style.display = "none"; }
function editable(node: Node | null): boolean {
  const element = node instanceof Element ? node : node?.parentElement;
  return Boolean(element?.closest('input, textarea, [contenteditable]:not([contenteditable="false"])'));
}

function showSelection(): void {
  const selected = window.getSelection();
  const text = selected?.toString().trim() ?? "";
  if (!selected?.rangeCount || text.length < 30 || editable(selected.anchorNode) || editable(selected.focusNode)) {
    hide(); return;
  }
  const range = selected.getRangeAt(0);
  const bounds = range.getBoundingClientRect();
  if (!bounds.width && !bounds.height) { hide(); return; }
  const parent = range.commonAncestorContainer;
  const surrounding = parent.textContent ?? "";
  const index = surrounding.indexOf(text);
  // Copy only a bounded neighbourhood, never the whole page or form fields.
  const context = index >= 0 ? `${surrounding.slice(Math.max(0, index - 500), index)}\n[Selected fragment]\n${surrounding.slice(index + text.length, index + text.length + 500)}` : "";
  const url = new URL(location.href);
  url.search = "";
  url.hash = "";
  selection = { text, pageUrl: url.href, pageTitle: document.title.slice(0, 500), context };
  const tooLong = text.length > 3000;
  button.disabled = tooLong;
  button.textContent = tooLong ? "Zaznacz maks. 3000 znaków" : "Zweryfikuj";
  host.style.display = "block";
  const size = host.getBoundingClientRect();
  host.style.left = `${Math.max(8, Math.min(bounds.right - size.width, innerWidth - size.width - 8))}px`;
  host.style.top = `${Math.max(8, Math.min(bounds.bottom + 8, innerHeight - size.height - 8))}px`;
}

button.addEventListener("pointerdown", event => event.preventDefault());
button.addEventListener("click", () => {
  if (!selection || button.disabled) return;
  const message: RuntimeMessage = { type: "CHECK_TEXT", selection };
  void chrome.runtime.sendMessage(message).catch(() => {
    button.disabled = false;
    button.textContent = "Odśwież stronę i spróbuj ponownie";
    host.style.display = "block";
  });
  hide();
});
document.addEventListener("selectionchange", () => {
  clearTimeout(timer);
  timer = setTimeout(showSelection, 180);
});
document.addEventListener("mouseup", event => {
  if (event.button === 0 && !event.composedPath().includes(host)) showSelection();
});
document.addEventListener("pointerdown", event => {
  if (!event.composedPath().includes(host)) hide();
});
document.addEventListener("keydown", event => { if (event.key === "Escape") hide(); });
window.addEventListener("scroll", hide, true);
window.addEventListener("resize", hide);

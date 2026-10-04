import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const script = await readFile(new URL("../dist/selection.js", import.meta.url), "utf8");
const text = "The capital of Australia is Canberra.";
function harness() {
  class Element {
    constructor(tag = "div") {
      this.tag = tag; this.children = []; this.events = {}; this.dataset = {}; this.hidden = false;
      this.style = { setProperty(name, value) { this[name] = value; } };
    }
    set innerHTML(_value) { throw new TypeError("TrustedHTML required"); }
    append(...items) { for (const item of items) { this.children.push(item); item.parentElement = this; } }
    attachShadow() { this.shadow = new Element("shadow"); this.shadow.activeElement = null; return this.shadow; }
    setAttribute() {}
    addEventListener(type, handler) { this.events[type] = handler; }
    closest() { return null; }
    blur() {}
    getBoundingClientRect() { return { width: 350, height: 240, right: 400, bottom: 150 }; }
  }
  const html = new Element("html");
  const events = {};
  let runtimeListener;
  let beforeSend = () => {};
  const document = { documentElement: html, fullscreenElement: null, title: "Test",
    createElement: tag => new Element(tag), addEventListener(type, handler) { events[type] = handler; } };
  const selected = { rangeCount: 1, anchorNode: new Element(), focusNode: new Element(),
    toString: () => text, getRangeAt: () => ({ commonAncestorContainer: { textContent: text },
      getBoundingClientRect: () => ({ width: 200, height: 20, right: 400, bottom: 150 }) }) };
  const chrome = { runtime: { sendMessage() { beforeSend(); return Promise.resolve(); },
    onMessage: { addListener(handler) { runtimeListener = handler; } } } };
  vm.runInNewContext(script, { document, chrome, window: { getSelection: () => selected, addEventListener() {} },
    Element, HTMLElement: Element, URL, location: { href: "https://www.youtube.com/watch?v=test" },
    innerWidth: 1000, innerHeight: 800, setTimeout, clearTimeout });
  const host = html.children[0];
  const walk = node => [node, ...node.children.flatMap(walk)];
  const find = cls => walk(host.shadow).find(node => node.className === cls);
  return { host, events, find, setBeforeSend(fn) { beforeSend = fn; }, update(state, show) {
    runtimeListener({ type: "TEXT_CHECK_UPDATE", state, show }, {}, () => {});
  } };
}
test("popup initializes on a page that rejects innerHTML and shows loading before sending the request", () => {
  const h = harness();
  h.events.mouseup({ button: 0, composedPath: () => [] });
  h.setBeforeSend(() => {
    assert.equal(h.host.style.display, "block");
    assert.equal(h.find("card").hidden, false);
    assert.equal(h.find("loading").hidden, false);
  });
  h.find("trigger").events.click();
});
test("context-menu start shows a popup and closing it prevents later updates reopening it", () => {
  const h = harness();
  const state = { textRunId: "run-1", textSelection: { text }, status: "extracting_claims", claims: [], signals: [], warnings: [] };
  h.update(state, true);
  assert.equal(h.host.style.display, "block");
  assert.equal(h.find("loading").hidden, false);
  h.find("close").events.click();
  assert.equal(h.host.style.display, "none");
  h.update({ ...state, status: "complete" }, false);
  assert.equal(h.host.style.display, "none");
});
test("finished analysis replaces loading with the summary", () => {
  const h = harness();
  const state = { textRunId: "run-1", textSelection: { text }, status: "extracting_claims", claims: [], signals: [], warnings: [] };
  h.update(state, true);
  h.update({ ...state, status: "complete" }, false);
  assert.equal(h.find("loading").hidden, true);
  assert.match(h.find("body").textContent, /Nie uzyskano oceny/);
});

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import vm from "node:vm";

const bundle = await readFile(new URL("../dist/background.js", import.meta.url), "utf8");
const selection = { text: "The capital of Australia is Canberra.", pageUrl: "https://example.com/", pageTitle: "Test", context: "" };
const flush = async () => { for (let i = 0; i < 15; i++) await new Promise(resolve => setImmediate(resolve)); };

function harness() {
  const listeners = {};
  const store = {};
  const requests = [];
  const calls = [];
  let now = 10000;
  const event = name => ({ addListener(fn) { listeners[name] = fn; } });
  const chrome = {
    storage: {
      session: { async get() { return { ...store }; }, async set(value) { Object.assign(store, value); } },
      local: { async get() { return {}; }, async set() {} },
    },
    runtime: { onInstalled: event("installed"), onMessage: event("message"), getURL: path => `chrome-extension://test/${path}` },
    sidePanel: { async open() { calls.push("open"); }, async setPanelBehavior() {} },
    action: { onClicked: event("action") },
    contextMenus: { onClicked: event("context"), removeAll(fn) { fn(); }, create(value) { calls.push(value); } },
    tabs: { async query() { return []; }, async sendMessage() {}, async create() {}, async update() {} },
  };
  class Clock extends Date { static now() { return now; } }
  const fetch = (url, options) => {
    calls.push("fetch");
    return new Promise(resolve => requests.push({ url, options, resolve }));
  };
  vm.runInNewContext(bundle, { chrome, fetch, crypto: { randomUUID }, AbortController, TextDecoder, URL, Date: Clock, console });
  const send = message => listeners.message(message, { tab: { id: 7 } }, () => {});
  const complete = (request, warnings = []) => {
    const data = new TextEncoder().encode(`data: ${JSON.stringify({ type: "complete", response: {
      status: "complete", claims: [], signals: [], warnings, mode: "live",
    } })}\n\n`);
    request.resolve({ ok: true, body: new ReadableStream({ start(controller) { controller.enqueue(data); controller.close(); } }) });
  };
  return { listeners, store, requests, calls, send, complete, advance() { now += 2000; } };
}

test("text checking shows the inline card without opening the panel", async () => {
  const h = harness();
  h.send({ type: "CHECK_TEXT", selection });
  await flush();
  assert.equal(h.calls.includes("open"), false);
  assert.match(h.requests[0].url, /\/check\/text\/stream$/);
  assert.deepEqual(JSON.parse(h.requests[0].options.body), selection);
  assert.equal(h.store.state.video, undefined);
});

test("details open the panel from the user's click", async () => {
  const h = harness();
  h.send({ type: "CHECK_TEXT", selection });
  await flush();
  h.send({ type: "OPEN_TEXT_DETAILS", runId: h.store.state.textRunId });
  assert.equal(h.calls.includes("open"), true);
});

test("new selection cancels the old request and ignores stale results", async () => {
  const h = harness();
  h.send({ type: "CHECK_TEXT", selection });
  await flush();
  h.advance();
  h.send({ type: "CHECK_TEXT", selection: { ...selection, text: "The capital of France is the city of Paris." } });
  await flush();
  assert.equal(h.requests[0].options.signal.aborted, true);
  h.complete(h.requests[1], ["new result"]);
  await flush();
  h.complete(h.requests[0], ["stale result"]);
  await flush();
  assert.deepEqual(Array.from(h.store.state.warnings), ["new result"]);
});

test("YouTube navigation does not erase an active text analysis", async () => {
  const h = harness();
  h.send({ type: "CHECK_TEXT", selection });
  await flush();
  h.send({ type: "VIDEO_CHANGED", video: { id: "abc123" } });
  await flush();
  assert.equal(h.store.state.textSelection.text, selection.text);
  assert.equal(h.requests[0].options.signal.aborted, false);
});

test("oversized selection never reaches the backend", async () => {
  const h = harness();
  h.send({ type: "CHECK_TEXT", selection: { ...selection, text: "a".repeat(3001) } });
  await flush();
  assert.equal(h.requests.length, 0);
  assert.match(h.store.state.error, /3000/);
});

test("context menu is registered for selections and avoids editable fields", () => {
  const h = harness();
  h.listeners.installed();
  assert.deepEqual(Array.from(h.calls.find(value => value?.id === "check-selection").contexts), ["selection"]);
  h.listeners.context({ menuItemId: "check-selection", editable: true, selectionText: selection.text }, { id: 7 });
  assert.equal(h.requests.length, 0);
});

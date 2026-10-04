import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { transform } from "esbuild";
const source = await readFile(new URL("../src/shared/textSummary.ts", import.meta.url), "utf8");
const { code } = await transform(source, { loader: "ts", format: "esm" });
const { textSummary } = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
const state = (verdicts, extra = {}) => ({ status: "complete", claims: verdicts.map(verdict => ({ verdict, evidence: [] })), signals: [], warnings: [], ...extra });
test("mixed findings never label the whole fragment supported", () => {
  const result = textSummary(state(["supported", "false", "couldnt_verify"]));
  assert.equal(result.tone, "danger");
  assert.match(result.title, /Mieszane/);
  assert.match(result.body, /bez pełnego rozstrzygnięcia: 1/);
});
test("partial streams never yield a verdict", () => {
  const result = textSummary(state(["supported"], { status: "gathering_evidence" }));
  assert.equal(result.pending, true);
  assert.equal(result.title, "Sprawdzam…");
});
test("missing evidence and empty results cannot produce a green summary", () => {
  assert.notEqual(textSummary(state(["couldnt_verify"])).tone, "positive");
  assert.notEqual(textSummary(state([])).tone, "positive");
});
test("routine scope notice does not falsely downgrade supported results", () => {
  assert.equal(textSummary(state(["supported"], { warnings: ["Only the selected fragment was analysed; surrounding context may change its meaning."] })).tone, "positive");
  assert.notEqual(textSummary(state(["supported"], { warnings: ["1 candidate failed to process"] })).tone, "positive");
});
test("sources are deduplicated and rhetoric is presented separately", () => {
  const result = textSummary(state([], { claims: ["supported", "supported"].map(verdict => ({ verdict, evidence: [{ url: "https://example.com/a" }] })), signals: [{ severity: "high" }] }));
  assert.equal(result.meta, "Twierdzenia: 2 · Źródła: 1");
  assert.equal(result.tone, "positive");
  assert.match(result.signal, /perswazji/);
});

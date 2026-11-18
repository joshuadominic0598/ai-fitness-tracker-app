"use strict";
const assert = require("node:assert/strict"), fs = require("node:fs"), vm = require("node:vm");
const source = fs.readFileSync(require.resolve("../src/fitness_tracker/web/app.js"), "utf8");
(async () => {
  const status = { textContent: "" };
  let calls = 0;
  const bytes = new TextEncoder().encode([
    JSON.stringify({ type: "stage", message: "Checking your workout…" }),
    JSON.stringify({ type: "final", response: { text: "**Ready**", action: "answer" } }), ""
  ].join("\n"));
  let offset = 0;
  const ctx = {
    state: { token: "test-session" }, TextDecoder,
    $: () => status, chatStage: "",
    fetch: async () => {
      calls++;
      return { ok: true, headers: { get: () => "application/x-ndjson" },
        body: { getReader: () => ({
          read: async () => {
            if (offset >= bytes.length) return { done: true };
            const value = bytes.slice(offset, offset + 7); offset += 7;
            return { done: false, value };
          }, releaseLock() {},
        }) }
      };
    },
    esc: value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll('"', "&quot;"),
    button: (label, action, kind, extra) => `<button ${extra || ""}>${label}</button>`,
  };
  vm.createContext(ctx);
  vm.runInContext(source.slice(source.indexOf("async function api("), source.indexOf("async function refresh(")), ctx);
  const result = await ctx.api("chat", { message: "Log my workout", stream: true });
  assert.equal(result.text, "**Ready**");
  assert.equal(status.textContent, "Checking your workout…");
  assert.equal(calls, 1);
  vm.runInContext(source.slice(source.indexOf("function chatText("), source.indexOf("function messageHtml(")), ctx);
  const html = ctx.chatText('**Steps**\n\n1. Hold the handles.\n2. Lower slowly.\n\n[Video](https://www.youtube.com/watch?v=test)\n<script>alert(1)</script>');
  assert.match(html, /<ol><li>Hold/);
  assert.match(html, /<strong>Steps<\/strong>/);
  assert.match(html, /href="https:\/\/www.youtube.com/);
  assert.doesNotMatch(html, /<script>/);
  vm.runInContext(source.slice(source.indexOf("function draftHtml("), source.indexOf("function agentDetails(")), ctx);
  const draft = ctx.draftHtml({ id: "draft", kind: "workout", data: { notes: "Needs clarification (not included in the sets above): Curl equipment?" } }, true);
  assert.match(draft, /disabled title="Resolve/);
  console.log("Coach streaming passed: chunked Unicode, stages, validated final response, lists, links and unresolved approval controls.");
})().catch(error => { console.error(error); process.exitCode = 1; });

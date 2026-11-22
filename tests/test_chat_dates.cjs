"use strict";
const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
const source = fs.readFileSync(require.resolve("../src/fitness_tracker/web/app.js"), "utf8");
(async () => {
  const input = { value: "", style: {} }, error = { textContent: "" };
  let focused = 0;
  const date = { value: "", checkValidity: () => true, focus: () => focused++ };
  const requests = [];
  const ctx = {
    state: { today: "2026-11-22", coach_consent: { accepted: true }, chat_status: { busy: false } },
    journalDate: "2026-11-22", chatEdit: null, chatBusy: false, coachModelBusy: false,
    chatLoggingKind: null, chatRevisionId: null, chatResearchMode: false,
    chatComposerDraft: "", optimisticChat: null,
    voiceInput: { isBusy: () => false },
    chatIsBusy: () => false, pendingCoachConnection: () => false,
    $: id => ({ "#chat-input": input, "#chat-error": error, "#coach-log-date": date })[id],
    crypto: { randomUUID: () => "logging-date-test" },
    resizeChatComposer() {}, syncChatThread() {}, ensureChatPolling() {},
    refresh: async () => {}, refreshChatSnapshot: async () => {},
    api: async (path, payload) => { requests.push(payload); return { action: "answer" }; },
    addDays: (value, amount) => {
      const day = new Date(value + "T12:00:00Z");
      day.setUTCDate(day.getUTCDate() + amount);
      return day.toISOString().slice(0, 10);
    },
  };
  vm.createContext(ctx);
  vm.runInContext(source.slice(source.indexOf("function chatMessageDate("), source.indexOf("async function action(")), ctx);
  for (const kind of ["workout", "home_workout", "cardio", "meal", "creatine", "supplement", "sleep", "body", "plan", "any"]) {
    ctx.chatLoggingKind = kind;
    input.value = "Prepare a preview with my details";
    await ctx.sendChat({ preventDefault() {} });
    assert.match(error.textContent, /Which date should I use/);
    assert.equal(requests.length, 0, `${kind} requires a date before dispatch`);
    assert.equal(input.value, "Prepare a preview with my details", "asking for a date retains the message");
  }
  assert.equal(focused, 10);
  ctx.chatLoggingKind = null;
  input.value = "What should I consider for recovery?";
  await ctx.sendChat({ preventDefault() {} });
  assert.equal(requests.at(-1).date, null, "ordinary coaching does not require a logging date");
  for (const [message, selected, expected] of [
    ["Log my cardio", "2026-11-21", "2026-11-21"],
    ["Log my meal for 2026-11-20", "2026-11-22", "2026-11-20"],
    ["Log my sleep yesterday", "2025-01-01", "2026-11-21"],
    ["Log my creatine today", "2025-01-01", "2026-11-22"],
    ["Log my meal for Nov 21, not today", "2026-11-22", "2026-11-21"],
    ["Log my cardio for 21 November 2026", "", "2026-11-21"],
    ["Log my home workout on 21/11/2026", "", "2026-11-21"],
  ]) {
    date.value = selected;
    input.value = message;
    await ctx.sendChat({ preventDefault() {} });
    assert.equal(requests.at(-1).date, expected, message);
  }
  date.value = "";
  ctx.chatRevisionId = "pending-preview";
  input.value = "Change my meal portion";
  await ctx.sendChat({ preventDefault() {} });
  assert.equal(requests.at(-1).revise_draft_id, "pending-preview", "corrections retain the dated preview");
  ctx.esc = String;
  ctx.dateLabel = value => value;
  vm.runInContext(source.slice(source.indexOf("function coachDateControl("), source.indexOf("function coach()")), ctx);
  assert.match(ctx.coachDateControl(), /id="coach-log-date"/);
  assert.match(ctx.coachDateControl(), /Entries will use <strong>2026-11-22/);
  console.log("Chat dates passed: visible logging date, all log types require a date when cleared, explicit/relative dates override selection, ordinary chat and revisions remain available.");
})().catch(error => { console.error(error); process.exit(1); });

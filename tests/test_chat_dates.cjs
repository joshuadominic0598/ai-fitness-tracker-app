"use strict";
const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
const source = fs.readFileSync(require.resolve("../src/fitness_tracker/web/app.js"), "utf8");
(async () => {
  const input = { value: "", style: {}, focus() {} }, error = { textContent: "" };
  const requests = [], dialogs = [];
  const ctx = {
    state: { today: "2026-11-23", coach_consent: { accepted: true }, chat_status: { busy: false } },
    journalDate: "2026-11-22", chatLogDate: null, chatEdit: null, chatBusy: false, coachModelBusy: false,
    chatLoggingKind: null, chatRevisionId: null, chatResearchMode: false,
    chatComposerDraft: "", optimisticChat: null,
    voiceInput: { isBusy: () => false, cancel() {} },
    chatIsBusy: () => false, pendingCoachConnection: () => false,
    $: id => ({ "#chat-input": input, "#chat-error": error })[id],
    crypto: { randomUUID: () => "logging-date-test" },
    resizeChatComposer() {}, syncChatThread() {}, ensureChatPolling() {}, render() {}, toast() {},
    closeModal: async () => {}, location: { hash: "#coach" },
    esc: value => String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;"),
    field: (label, name, value, type, attrs) => `<input name="${name}" value="${value}" ${attrs}>`,
    button: label => `<button>${label}</button>`,
    modal: (title, description, body) => dialogs.push({ title, description, body }),
    refresh: async () => {}, refreshChatSnapshot: async () => {},
    api: async (path, payload) => { requests.push(payload); return { action: "answer" }; },
    addDays: (value, amount) => {
      const day = new Date(value + "T12:00:00Z");
      day.setUTCDate(day.getUTCDate() + amount);
      return day.toISOString().slice(0, 10);
    },
  };
  vm.createContext(ctx);
  vm.runInContext(source.slice(source.indexOf("function prepareCoachMessage("), source.indexOf("async function action(")), ctx);
  vm.runInContext(source.slice(source.indexOf("function openCoachLogDate("), source.indexOf("function drawPlan(")), ctx);
  const selection = (day, message = "", kind = "meal") => ({
    elements: { date: { value: day, checkValidity: () => day >= "1900-01-01" && day <= "2050-12-31" }, message: { value: message } }, dataset: { kind },
  });
  input.value = "Unsent note";
  ctx.openCoachLogDate("meal");
  assert.match(dialogs.at(-1).title, /Which day is this food for/);
  assert.match(dialogs.at(-1).body, /name="date" value="" required/);
  assert.equal(input.value, "Unsent note", "opening or cancelling does not replace the composer");
  assert.equal(ctx.chatLogDate, null);
  assert.equal(requests.length, 0, "opening the date dialog never submits a chat");
  await assert.rejects(ctx.confirmCoachLogDate(selection("")), /Choose a valid date/);
  await ctx.confirmCoachLogDate(selection("2026-11-21"));
  assert.match(input.value, /Log my food for 2026-11-21/);
  assert.equal(ctx.chatLogDate, "2026-11-21");
  assert.equal(ctx.chatLoggingKind, "meal");
  assert.equal(requests.length, 0, "confirming a date only prepares the message");
  input.value += "2 eggs";
  await ctx.sendChat({ preventDefault() {} });
  assert.equal(requests.at(-1).date, "2026-11-21");
  for (const kind of ["workout", "home_workout", "cardio", "meal", "creatine", "supplement", "sleep", "body", "plan", "any"]) {
    ctx.chatLogDate = null;
    ctx.chatLoggingKind = kind;
    input.value = "Prepare a preview with my details";
    const count = requests.length;
    await ctx.sendChat({ preventDefault() {} });
    assert.equal(requests.length, count, `${kind} asks for a date before dispatch`);
    assert.equal(input.value, "Prepare a preview with my details", "asking for a date retains the message");
    assert.match(dialogs.at(-1).body, /Prepare a preview with my details/);
  }
  const original = 'Log my food: eggs & "toast"';
  ctx.chatLogDate = null;
  ctx.chatLoggingKind = null;
  input.value = original;
  await ctx.sendChat({ preventDefault() {} });
  assert.match(dialogs.at(-1).body, /eggs &amp; &quot;toast&quot;/);
  await ctx.confirmCoachLogDate(selection("2026-11-20", original, "any"));
  assert.equal(input.value, original, "choosing a date preserves the original typed request exactly");
  await ctx.sendChat({ preventDefault() {} });
  assert.equal(requests.at(-1).date, "2026-11-20");
  assert.equal(requests.at(-1).message, original);
  ctx.prepareCoachMessage("What should I consider for recovery?");
  await ctx.sendChat({ preventDefault() {} });
  assert.equal(requests.at(-1).date, null, "ordinary coaching does not inherit Track's date");
  for (const question of ["How do I log my food?", "Explain how to record a workout", "Don't log this meal yet"]) {
    ctx.prepareCoachMessage(question);
    const dialogsBefore = dialogs.length;
    await ctx.sendChat({ preventDefault() {} });
    assert.equal(dialogs.length, dialogsBefore, "questions about logging and negated requests do not need dates");
    assert.equal(requests.at(-1).message, question);
  }
  for (const [message, selected, expected] of [
    ["Log my cardio", "2026-11-21", "2026-11-21"],
    ["Log my meal for 2026-11-20", "2026-11-22", "2026-11-20"],
    ["Log my sleep yesterday", "2025-01-01", "2026-11-22"],
    ["Log my creatine today", "2025-01-01", "2026-11-23"],
    ["Log my meal for Nov 21, not today", "2026-11-22", "2026-11-21"],
    ["Log my cardio for 21 November 2026", null, "2026-11-21"],
    ["Log my home workout on 21/11/2026", null, "2026-11-21"],
  ]) {
    ctx.chatLogDate = selected;
    ctx.chatLoggingKind = null;
    input.value = message;
    await ctx.sendChat({ preventDefault() {} });
    assert.equal(requests.at(-1).date, expected, message);
  }
  ctx.chatLogDate = null;
  ctx.chatRevisionId = "pending-preview";
  input.value = "Change my meal portion";
  await ctx.sendChat({ preventDefault() {} });
  assert.equal(requests.at(-1).revise_draft_id, "pending-preview", "corrections retain the dated preview");
  ctx.chatEdit = { date: "2026-11-19", kind: "meal" };
  ctx.$ = id => ({ "#chat-edit-input": input, "#chat-edit-error": error })[id];
  input.value = "Log my meal: 3 eggs";
  await ctx.sendChat({ preventDefault() {} }, null, null, 1);
  assert.equal(requests.at(-1).date, "2026-11-19", "full edits preserve the original request date");
  assert.ok(!source.includes('class="coach-log-date"'), "there is no repeated date banner");
  console.log("Chat dates passed: date-first food shortcut, cancelled dialogs preserve text, all logging kinds prompt when undated, selected and written dates, ordinary chat, corrections and edits.");
})().catch(error => { console.error(error); process.exit(1); });

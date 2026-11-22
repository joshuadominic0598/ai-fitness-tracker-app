"use strict";
const fs = require("node:fs"),
  vm = require("node:vm"),
  assert = require("node:assert/strict");
const source = fs.readFileSync(
  require.resolve("../src/fitness_tracker/web/app.js"),
  "utf8",
);
const code = source.slice(
  source.indexOf("function prepareCoachMessage("),
  source.indexOf("async function action("),
);
(async () => {
  const input = { value: "What percentage is 98 of 112?", style: {}, scrollHeight: 120 },
    error = { textContent: "" };
  let calls = 0,
    prevented = false,
    resolve;
  const ctx = {
    resizeChatComposer: () => {},
    VoiceInput: require("../src/fitness_tracker/web/voice-input.js"),
    state: { coach_consent: { accepted: false }, chat_status: { busy: false } },
    chatResearchMode: false,
    chatLoggingKind: null,
    chatRevisionId: null,
    chatLogDate: null,
    voiceInput: { isBusy: () => false, cancel: () => {} },
    chatBusy: false,
    coachModelBusy: false,
    pendingCoachConnection: () => false,
    optimisticChat: null,
    chatComposerDraft: "",
    $: (id) => ({ "#chat-input": input, "#chat-error": error })[id],
    journalDate: "2026-11-09",
    location: { hash: "#coach" },
    crypto: { randomUUID: () => "test-request-1234" },
    chatIsBusy: () => ctx.chatBusy || ctx.state.chat_status.busy,
    syncChatThread: () => {},
    ensureChatPolling: () => {},
    toast: () => {},
    api: async (path, data) => {
      calls++;
      assert.ok(prevented);
      assert.equal(path, "chat");
      assert.equal(data.date, null, "ordinary questions do not inherit the Track date");
      assert.equal(data.request_id, "test-request-1234");
      assert.equal(
        data.research,
        true,
        "Research is explicitly selected for this message",
      );
      assert.ok(
        !("consent" in data),
        "agreement is saved, not requested per message",
      );
      return new Promise((r) => (resolve = r));
    },
    refresh: async () => {},
    refreshChatSnapshot: async () => {},
  };
  vm.createContext(ctx);
  vm.runInContext(code, ctx);
  ctx.esc = (s) => String(s);
  ctx.icon = () => "";
  vm.runInContext(
    source.slice(
      source.indexOf("const coachStarters ="),
      source.indexOf("function coach()"),
    ),
    ctx,
  );
  const starters = vm.runInContext("coachStarters", ctx);
  assert.equal(starters.length, 5);
  assert.equal((ctx.coachPromptCards().match(/data-prompt=/g) || []).length, 4);
  assert.match(ctx.coachPromptCards(), /data-action="start-coach-log" data-kind="meal"/);
  input.focus = () => {};
  for (const starter of starters) {
    ctx.prepareCoachMessage(starter.prompt);
    assert.equal(input.value, starter.prompt);
    assert.equal(ctx.chatLoggingKind, null, "task shortcuts leave logging intent to the request");
    assert.equal(ctx.chatComposerDraft, starter.prompt);
  }
  assert.equal(calls, 0, "choosing a card only prepares an editable message");
  assert.ok(
    !source.includes("youtube-connection-form"),
    "no YouTube API setup",
  );
  assert.ok(
    !source.includes("video-search-form"),
    "no coach video search setup",
  );
  const originalQuery = ctx.$;
  ctx.$ = () => null;
  ctx.prepareCoachMessage("Estimate my meal after agreement");
  assert.equal(ctx.chatComposerDraft, "Estimate my meal after agreement");
  ctx.$ = originalQuery;
  input.focus = () => {};
  ctx.prepareCoachMessage("What percentage is 98 of 112?");
  assert.equal(input.value, ctx.chatComposerDraft);
  let keydown,
    submitted = 0;
  ctx.document = {
    addEventListener: (type, listener) => {
      if (type === "keydown") keydown = listener;
    },
  };
  const queryBeforeKeys = ctx.$;
  ctx.$ = (id) =>
    id === "#chat-form"
      ? { requestSubmit: () => submitted++ }
      : queryBeforeKeys(id);
  vm.runInContext(
    source.slice(
      source.indexOf('document.addEventListener(\n  "keydown"'),
      source.indexOf('document.addEventListener("input"'),
    ),
    ctx,
  );
  const press = (extra = {}) => {
    let blocked = false;
    keydown({
      target: { id: "chat-input" },
      key: "Enter",
      preventDefault: () => (blocked = true),
      ...extra,
    });
    return blocked;
  };
  assert.equal(press(), true);
  assert.equal(submitted, 1, "Enter submits once");
  assert.equal(
    press({ shiftKey: true }),
    false,
    "Shift+Enter preserves newline",
  );
  assert.equal(
    press({ isComposing: true }),
    false,
    "IME composition cannot submit",
  );
  press({ repeat: true });
  ctx.chatBusy = true;
  press();
  assert.equal(
    submitted,
    1,
    "held Enter and pending replies cannot duplicate requests",
  );
  ctx.chatBusy = false;
  ctx.$ = queryBeforeKeys;
  const event = {
    preventDefault() {
      prevented = true;
    },
  };
  await ctx.sendChat(event);
  assert.equal(calls, 0);
  assert.match(error.textContent, /agreement/);
  ctx.state.coach_consent.accepted = true;
  ctx.pendingCoachConnection = () => true;
  await ctx.sendChat(event);
  assert.equal(calls, 0, "an unapplied connection selection cannot send through the previous provider");
  assert.match(error.textContent, /Switch connection/);
  ctx.pendingCoachConnection = () => false;
  ctx.chatResearchMode = true;
  const pending = ctx.sendChat(event);
  assert.equal(
    ctx.chatResearchMode,
    false,
    "the next message returns to quick chat",
  );
  assert.equal(
    ctx.optimisticChat.text,
    "What percentage is 98 of 112?",
    "user bubble appears before response",
  );
  assert.equal(ctx.optimisticChat.status, "pending");
  assert.equal(input.value, "");
  assert.notEqual(input.disabled, true, "follow-up composing stays available");
  input.value = "My next question";
  resolve({});
  await pending;
  assert.equal(
    input.value,
    "My next question",
    "answer does not erase follow-up text",
  );
  assert.equal(ctx.chatBusy, false);
  assert.equal(ctx.optimisticChat, null);
  ctx.chatLoggingKind = "workout";
  ctx.chatRevisionId = "pending-draft";
  let reviewed = false;
  ctx.showAiPreview = async () => {
    reviewed = true;
  };
  ctx.api = async (path, data) => {
    assert.equal(data.logging_kind, "workout");
    assert.equal(data.revise_draft_id, "pending-draft");
    assert.equal(data.research, false);
    return {
      draft: { id: "ready-draft" },
      preview_summary: "Prepared: 18 g protein.",
    };
  };
  await ctx.sendChat(event);
  assert.equal(reviewed, false, "preview does not navigate away from chat");
  assert.equal(ctx.location.hash, "#coach");
  assert.equal(
    ctx.chatLoggingKind,
    null,
    "completed logging does not force later chat into logging mode",
  );
  assert.equal(ctx.chatRevisionId, null);
  ctx.activeAiPreview = { draft_id: "ready-draft" };
  ctx.render = () => {};
  ctx.api = async () => ({ approved: { date: "2026-11-08" } });
  input.value = "I approve";
  await ctx.sendChat(event);
  assert.equal(
    ctx.location.hash,
    "#coach",
    "approval saves without leaving chat",
  );
  assert.equal(ctx.journalDate, "2026-11-08");
  assert.equal(ctx.activeAiPreview, null);
  input.value = "A follow-up I am composing";
  ctx.api = async (path, data) => {
    assert.equal(data.message, "I approve");
    assert.equal(data.approve_draft_id, "specific-preview");
    return { approved: { date: "2026-11-08" } };
  };
  await ctx.sendChat(event, "specific-preview");
  assert.equal(input.value, "A follow-up I am composing");
  assert.equal(ctx.location.hash, "#coach");
  ctx.api = async () => {
    throw Error("Provider unavailable");
  };
  input.value = "Retry this meal";
  await ctx.sendChat(event);
  assert.equal(input.value, "Retry this meal");
  assert.equal(ctx.optimisticChat.status, "failed");
  assert.match(error.textContent, /unavailable/);
  ctx.refreshChatSnapshot = async () => {
    ctx.state.messages = [
      {
        role: "assistant",
        request_id: "test-request-1234",
        text: "The answer was saved",
      },
    ];
  };
  input.value = "Response reached the server";
  await ctx.sendChat(event);
  assert.equal(
    input.value,
    "",
    "a completed response is not falsely offered as a failed resend",
  );
  assert.equal(ctx.optimisticChat, null);
  vm.runInContext(
    source.slice(
      source.indexOf("function draftHtml("),
      source.indexOf("function quotaSummary("),
    ),
    ctx,
  );
  ctx.state.drafts = [
    {
      id: "pending",
      kind: "meal",
      data: { date: "2026-11-13", protein: 18, description: "Toast" },
    },
  ];
  ctx.button = (label, action, kind, attrs) =>
    `<button data-action="${action}" ${attrs || ""}>${label}</button>`;
  ctx.previewEntryDetails = () => "18 g protein";
  const html = ctx.messageHtml({
    role: "assistant",
    text: "18 g protein",
    draft: { id: "pending" },
  });
  assert.ok(
    html.indexOf('data-action="approve-chat-draft"') <
      html.indexOf('class="message-resources"'),
    "approval is visible outside collapsed resources",
  );
  assert.match(html, /not saved yet/);
  assert.match(html, /View in Track/);
  for (const kind of [
    "workout",
    "plan",
    "supplement",
    "sleep",
    "body",
    "batch",
  ]) {
    const draft = {
      id: kind,
      kind,
      data:
        kind === "batch"
          ? { entries: [{ kind: "sleep", data: { date: "2026-11-13" } }] }
          : { date: "2026-11-13" },
    };
    ctx.state.drafts = [draft];
    const message = ctx.messageHtml({
      role: "assistant",
      text: "Review proposed changes",
      draft,
    });
    assert.match(message, /approve-chat-draft/);
    assert.match(message, /Suggest changes/);
    assert.match(message, /View in Track/);
    assert.ok(
      message.indexOf("approve-chat-draft") <
        message.indexOf("message-resources"),
    );
  }
  const savedHtml = ctx.messageHtml({
    role: "assistant",
    text: "Saved 18 g",
    approved: { date: "2026-11-13" },
  });
  assert.match(savedHtml, /view-approved-track/);
  assert.match(savedHtml, /data-date="2026-11-13"/);
  console.log(
    "Chat submission passed: immediate message, generation state, saved agreement, follow-up preservation and visible failure.",
  );
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});

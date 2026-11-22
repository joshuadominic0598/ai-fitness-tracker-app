"use strict";
const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
const source = fs.readFileSync(require.resolve("../src/fitness_tracker/web/app.js"), "utf8");
(async () => {
  const input = { value: "Log my food: bread and milk", focus() {}, closest: () => ({ scrollIntoView() {} }) };
  const mainInput = { value: "", style: {}, focus() {} }, error = { textContent: "" };
  const draft = { id: "original-draft", kind: "meal", data: { date: "2026-11-20", items: [] } };
  let finish, payload, rendered = 0;
  const ctx = {
    state: { coach_consent: { accepted: true }, drafts: [draft], chat_status: { busy: false }, messages: [
      { id: 1, role: "user", text: input.value, context_date: "2026-11-20", logging_kind: "meal", request_id: "original-request" },
      { id: 2, role: "assistant", text: "Original estimate", action: "meal", draft, request_id: "original-request" },
    ] },
    chatEdit: null, chatBusy: false, coachModelBusy: false, optimisticChat: null,
    chatRevisionId: null, chatLoggingKind: null, chatResearchMode: false, chatLogDate: null,
    chatComposerDraft: "", journalDate: "2026-11-21", location: { hash: "#coach" },
    voiceInput: { cancel() {}, isBusy: () => false },
    esc: value => String(value).replaceAll("<", "&lt;"),
    icon: () => "", button: (label, action, kind, attrs) => `<button data-action="${action}" ${attrs || ""}>${label}</button>`,
    $: id => ({ "#chat-input": mainInput, "#chat-error": error, "#chat-edit-input": input, "#chat-edit-error": error })[id],
    chatIsBusy: () => ctx.chatBusy,
    closeModal: async () => {}, render: () => rendered++, syncChatThread() {}, resizeChatComposer() {}, ensureChatPolling() {},
    pendingCoachConnection: () => false, crypto: { randomUUID: () => "updated-request" },
    api: async (path, data) => { payload = data; return new Promise(resolve => finish = resolve); },
    refresh: async () => {}, refreshChatSnapshot: async () => {},
  };
  vm.createContext(ctx);
  vm.runInContext(source.slice(source.indexOf("function draftHtml("), source.indexOf("function quotaSummary(")), ctx);
  vm.runInContext(source.slice(source.indexOf("function chatVisibleMessages("), source.indexOf("function chatThreadHtml(")), ctx);
  vm.runInContext(source.slice(source.indexOf("function prepareCoachMessage("), source.indexOf("async function action(")), ctx);
  assert.doesNotMatch(ctx.messageHtml({ role: "user", text: "New request", request_id: "pending-request", status: "pending" }), /chat-edit-input/);
  assert.equal(await ctx.editChatPreview("original-draft"), true);
  assert.equal(ctx.chatEdit.messageId, 1);
  assert.equal(ctx.chatEdit.text, "Log my food: bread and milk");
  assert.equal(ctx.chatEdit.date, "2026-11-20");
  assert.equal(rendered, 0, "editing stays in the existing thread");
  const editing = ctx.messageHtml(ctx.state.messages[0]);
  assert.match(editing, /chat-edit-input/);
  assert.match(editing, /Update preview/);
  assert.match(editing, /Cancel/);
  assert.match(ctx.draftHtml(draft, true), /disabled/);
  input.value = "Log my food: 400ml milk";
  const pending = ctx.sendChat({ preventDefault() {} }, null, null, 1);
  assert.equal(payload.edit_message_id, 1);
  assert.equal(payload.message, "Log my food: 400ml milk");
  assert.equal(payload.date, "2026-11-20");
  assert.equal(payload.logging_kind, "meal");
  assert.equal(payload.revise_draft_id, null, "the edited full source is not a patch");
  const visible = ctx.chatVisibleMessages();
  assert.equal(visible.length, 1, "the old answer is replaced by generation, not another user bubble");
  assert.equal(visible[0].id, 1);
  assert.equal(visible[0].text, payload.message);
  const revised = { ...draft, id: "updated-draft" };
  ctx.state.messages = [
    { ...ctx.state.messages[0], text: payload.message, request_id: payload.request_id, status: "sent", edit_message_id: 1, replace_response_id: 2 },
    { ...ctx.state.messages[1], text: "Updated estimate", draft: revised, request_id: payload.request_id },
  ];
  ctx.state.drafts = [revised];
  finish({ draft: revised });
  await pending;
  assert.equal(ctx.optimisticChat, null);
  assert.equal(ctx.chatVisibleMessages().length, 2);
  assert.equal(ctx.state.messages[1].id, 2);
  for (const kind of ["meal", "creatine", "supplement", "sleep", "workout"]) {
    const compact = ctx.draftHtml({ ...revised, kind }, true);
    assert.match(compact, /chat-preview-actions/);
    assert.doesNotMatch(compact, /Review your preview|Review the list above/);
    for (const action of ["approve-chat-draft", "change-preview", "preview-ai-draft", "dismiss-draft"]) assert.ok(compact.includes(action));
  }
  ctx.state.messages[0].status = "pending";
  assert.equal(ctx.chatVisibleMessages().length, 1, "polling and reload hide the superseded answer while updating");
  ctx.state.messages[0] = { ...ctx.state.messages[0], status: "sent", text: "Change the milk to 400ml", revise_draft_id: "earlier-preview" };
  ctx.startChatEdit(ctx.chatEditableExchange(1));
  assert.equal(ctx.chatEdit, null, "a follow-up correction stays in the patch workflow");
  assert.equal(ctx.chatRevisionId, revised.id);
  assert.equal(mainInput.value, "Change the milk to 400ml");
  mainInput.value = "Change the milk to 600ml";
  const patchRequest = ctx.sendChat({ preventDefault() {} });
  assert.equal(payload.revise_draft_id, revised.id);
  assert.equal(payload.edit_message_id, undefined);
  finish({ draft: revised });
  await patchRequest;
  console.log("Chat edits passed: inline source editing, one exchange, original date, full replacement, compact actions and pending recovery.");
})().catch(error => { console.error(error); process.exitCode = 1; });

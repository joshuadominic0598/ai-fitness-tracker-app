"use strict";
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  vm = require("node:vm");
(async () => {
  const source = fs.readFileSync(
    require.resolve("../src/fitness_tracker/web/app.js"),
    "utf8",
  );
  let body;
  const ctx = {
    workoutForm: {
      date: "2026-11-10",
      kind: "plan",
      exercises: [{ exercise_id: "Plank" }],
    },
    byId: { Plank: { name: "Plank" } },
    modal: (title, description, html) => (body = html),
    sessionTitle: (d) => d,
    field: (label) => `<label>${label}</label>`,
    button: () => "",
    usualPicker: () => "",
    pickerResults: () => "",
    esc: (s) => s,
    image: (id) => id,
    entryFooter: () => "",
    formDraft: null,
  };
  vm.createContext(ctx);
  vm.runInContext(
    source.slice(
      source.indexOf("function drawPlan("),
      source.indexOf("function dailyJournal()"),
    ),
    ctx,
  );
  ctx.drawPlan();
  assert.match(body, /Plank/);
  assert.doesNotMatch(
    body,
    /data-set|type="number"|Resistance|Session duration/,
  );
  let prepared,
    rendered = 0;
  const chatInput = { focus() {} };
  const flow = {
    journalDate: "2026-11-11",
    state: { coach_consent: { accepted: true } },
    location: { hash: "#overview" },
    $: (id) => (id === "#chat-input" ? chatInput : null),
    closeModal: async () => {},
    prepareCoachMessage: (text) => (prepared = text),
    render: () => rendered++,
    toast: () => {},
    chatLoggingKind: null,
    chatRevisionId: null,
    editChatPreview: async () => false,
  };
  vm.createContext(flow);
  vm.runInContext(
    source.slice(
      source.indexOf("async function openAiLog("),
      source.indexOf("function drawPlan("),
    ),
    flow,
  );
  await flow.openAiLog("workout");
  assert.equal(flow.location.hash, "coach");
  assert.equal(flow.chatLoggingKind, "workout");
  assert.match(prepared, /Log my workout for 2026-11-11/);
  assert.equal(rendered, 1);
  await flow.openAiLog("meal", "pending-id");
  assert.equal(flow.chatRevisionId, "pending-id");
  assert.match(prepared, /Suggest changes/);
  flow.state.drafts = [
    {
      id: "older",
      kind: "batch",
      data: { entries: [{ kind: "sleep", data: { date: "2026-11-09" } }] },
    },
  ];
  await flow.openAiLog("any", "older");
  assert.equal(flow.journalDate, "2026-11-09");
  assert.match(prepared, /2026-11-09/);
  assert.equal(flow.location.hash, "coach");

  const review = {
    GoalTracking: require("../src/fitness_tracker/web/goals.js"),
    journalDate: "2026-11-11",
    activeAiPreview: {
      date: "2026-11-11",
      draft_id: "d",
      entries: [{ kind: "workout" }],
    },
    state: { drafts: [] },
    button: (label) => label,
    previewEntryDetails: () => "SET DETAILS",
    esc: (text) => String(text),
    draftHtml: () => "DRAFT",
  };
  vm.createContext(review);
  vm.runInContext(
    source.slice(
      source.indexOf("function previewMatches("),
      source.indexOf("async function showAiPreview("),
    ),
    review,
  );
  assert.match(
    review.verificationFooter("workout"),
    /Verify this workout preview/,
  );
  assert.equal(review.verificationFooter("meal"), "");
  review.activeAiPreview.entries = [{ kind: "creatine", amount: 5, unit: "g" }];
  assert.match(
    review.verificationFooter("creatine"),
    /Verify this creatine preview/,
  );
  assert.equal(review.verificationFooter("supplement"), "");
  review.activeAiPreview.entries = [{ kind: "workout" }];
  review.activeAiPreview.summary = "Prepared: 18 g protein.";
  assert.match(review.verificationFooter("workout"), /Prepared: 18 g protein/);
  assert.ok(
    source.indexOf("d.workouts.map(dayWorkout)") <
      source.indexOf('verificationFooter("workout")}</div>'),
    "verification follows the workout entries",
  );
  console.log(
    "AI logging checks passed: exercise-only plans and inline chat logging.",
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

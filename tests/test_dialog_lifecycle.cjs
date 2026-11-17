"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { create } = require("../src/fitness_tracker/web/dialog-lifecycle.js");
class NativeDialog {
  open = false;
  scrollTop = 1200;
  listeners = [];
  queued = [];
  addEventListener(type, listener) {
    if (type === "close") this.listeners.push(listener);
  }
  showModal() {
    this.open = true;
  }
  close() {
    this.open = false;
    this.queued.push(() => this.listeners.forEach((listener) => listener()));
  }
  flushClose() {
    this.queued.shift()?.();
  }
}
(async () => {
  let content = "first form",
    clears = 0;
  const dialog = new NativeDialog();
  const lifecycle = create(dialog, () => {
    clears++;
    content = "";
  });
  lifecycle.show();
  assert.equal(dialog.scrollTop, 0);
  const closed = lifecycle.close();
  let settled = false;
  closed.then(() => (settled = true));
  assert.equal(
    settled,
    false,
    "wait for the native close event before refreshing",
  );
  content = "second form";
  lifecycle.show();
  assert.equal(dialog.open, false);
  dialog.flushClose();
  await closed;
  await Promise.resolve();
  assert.equal(
    content,
    "second form",
    "a late close must not erase the new editor",
  );
  assert.equal(dialog.open, true);
  assert.equal(clears, 0);
  const done = lifecycle.close();
  assert.equal(lifecycle.close(), done);
  dialog.flushClose();
  await done;
  assert.equal(content, "");
  assert.equal(clears, 1);
  for (let i = 0; i < 8; i++) {
    content = "editor " + i;
    lifecycle.show();
    dialog.scrollTop = 2000;
    const closing = lifecycle.close();
    dialog.flushClose();
    await closing;
    content = "next " + i;
    lifecycle.show();
    assert.equal(dialog.open, true);
    assert.equal(dialog.scrollTop, 0);
  }
  // Native Escape closes also clean up, without requiring the save path.
  dialog.close();
  dialog.flushClose();
  assert.equal(content, "");
  // A background refresh that never finishes must not block either button.
  const source = fs.readFileSync(
    require.resolve("../src/fitness_tracker/web/app.js"),
    "utf8",
  );
  const action = source.slice(
    source.indexOf("async function action("),
    source.indexOf('document.addEventListener("click"'),
  );
  let workoutOpened = false,
    foodOpened = false,
    refreshCalls = 0;
  const context = {
    WorkoutHistory: {},
    openWorkout: () => {
      workoutOpened = true;
    },
    simpleForm: (kind) => {
      foodOpened = kind === "meal";
    },
    refresh: () => {
      refreshCalls++;
      return new Promise(() => {});
    },
  };
  vm.createContext(context);
  vm.runInContext(action, context);
  context.action("new-workout", { dataset: {} });
  context.action("new-meal", { dataset: {} });
  assert.equal(workoutOpened, true);
  assert.equal(foodOpened, true);
  assert.equal(refreshCalls, 0);
  console.log(
    "Dialog lifecycle checks passed: queued closes, rapid reopen, scroll reset, repeated saves, and offline editor opening.",
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
// Keep the interactive page out of composited transitions, including tab changes.
{
  const source = fs.readFileSync(
    require.resolve("../src/fitness_tracker/web/app.js"),
    "utf8",
  );
  const renderSource = source.slice(
    source.indexOf("function render()"),
    source.indexOf("const dialogLifecycle ="),
  );
  const elements = { "#page-label": {}, "#nav": {}, "#content": {} };
  const context = {
    BodyMap: { bind() {} },
    voiceInput: { cancel() {} },
    resizeChatComposer() {},
    location: { hash: "#overview" },
    document: { body: { classList: { toggle() {} } } },
    pages: { overview: "Overview" },
    page: "overview",
    $: (id) => elements[id],
    overview: () => "<button>Edit workout</button>",
    track: () => "",
    workouts: () => "",
    nutrition: () => "",
    exercises: () => "",
    progress: () => "",
    coach: () => "",
    settings: () => "",
    goals: () => "",
    icon: () => "",
  };
  vm.createContext(context);
  vm.runInContext(renderSource, context);
  context.render();
  context.render();
  assert.match(elements["#content"].innerHTML, /Edit workout/);
  assert.ok(
    !renderSource.includes(".animate("),
    "animate navigation decoration, never interactive page content",
  );
  console.log(
    "Page refresh checks passed: content remains outside composited transitions.",
  );
}

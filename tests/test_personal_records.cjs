"use strict";
const fs = require("node:fs"),
  vm = require("node:vm"),
  assert = require("node:assert/strict");
const source = fs.readFileSync(
  require.resolve("../src/fitness_tracker/web/app.js"),
  "utf8",
);
const original = {
  bench: { weight: 50, reps: 6, date: "2026-11-11" },
  pushup: { weight: 0, reps: 20, date: "2026-11-12" },
  plank: { weight: 0, reps: 0, seconds: 60, date: "2026-11-12" },
  curl: { weight: 10, reps: 8, date: "2026-11-11" },
};
const ctx = {
  state: { insights: { prs: original }, entries: [], today: "2026-11-13" },
  byId: {
    bench: { name: "Bench Press", bodyParts: ["Chest", "Triceps"] },
    pushup: { name: "Pushups", bodyParts: ["Chest"] },
    plank: { name: "Plank", bodyParts: ["Abs"] },
    curl: { name: "Dumbbell Curl", bodyParts: ["Biceps"] },
  },
  WorkoutHistory: {
    usualExercises: () => [
      { id: "curl", count: 4 },
      { id: "bench", count: 2 },
    ],
  },
  n: String,
  image: (id) => `/assets/${id}.webp`,
  sessionTitle: (value) => value,
  recordExercise: "",
  recordBodyPart: "",
  empty: (title, detail, action) => `${title} ${detail} ${action || ""}`,
  button: (label, action) =>
    `<button data-action="${action}">${label}</button>`,
};
vm.createContext(ctx);
vm.runInContext(
  source.slice(source.indexOf("const esc ="), source.indexOf("const n =")),
  ctx,
);
vm.runInContext(
  source.slice(
    source.indexOf("function exerciseRecords("),
    source.indexOf("function resetDialog("),
  ),
  ctx,
);
let html = ctx.exerciseRecords();
assert.equal((html.match(/class="pr-kpi"/g) || []).length, 4);
assert.ok(html.indexOf("<h3>Dumbbell Curl") < html.indexOf("<h3>Bench Press"));
assert.match(html, /Filter PRs by exercise/);
assert.match(html, /Filter PRs by body part/);
assert.match(html, /50<small> kg × <\/small>6/);
assert.match(html, /60<small> sec/);
ctx.recordBodyPart = "Chest";
html = ctx.exerciseRecords();
assert.equal((html.match(/class="pr-kpi"/g) || []).length, 2);
assert.match(html, /2 \/ 4 EXERCISES/);
assert.doesNotMatch(html, /<h3>Plank/);
ctx.recordExercise = "bench";
html = ctx.exerciseRecords();
assert.equal((html.match(/class="pr-kpi"/g) || []).length, 1);
assert.match(html, /<h3>Bench Press/);
ctx.recordExercise = "plank";
html = ctx.exerciseRecords();
assert.match(html, /No PRs match these filters/);
assert.match(html, /clear-pr-filters/);
ctx.recordBodyPart = "";
assert.match(ctx.exerciseRecords(), /Longest hold/);
assert.equal(original.bench.weight, 50, "filters cannot alter saved PRs");
let focused = false;
const region = { outerHTML: "" };
ctx.$ = (selector) =>
  selector === ".records-card" ? region : { focus: () => (focused = true) };
ctx.updateExerciseRecords("pr-exercise-filter");
assert.match(region.outerHTML, /<h3>Plank/);
assert.equal(focused, true, "filter rerender restores keyboard focus");
console.log(
  "PR filters passed: tracked exercises, body parts, combined/empty results, unchanged weights/time records and keyboard focus.",
);

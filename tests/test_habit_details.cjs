"use strict";
const fs = require("node:fs"), vm = require("node:vm"), assert = require("node:assert/strict");
const source = fs.readFileSync(require.resolve("../src/fitness_tracker/web/app.js"), "utf8");
const day = "2026-11-17", rest = "2026-11-18";
const entries = [
  { kind: "workout", date: day, exercises: [{ exercise_id: "curl", sets: [{ weight: 10, reps: 8 }, { weight: 10, reps: 6 }] }] },
  { kind: "meal", date: day, protein: 30 },
  { kind: "meal", date: day, protein: 25 },
  { kind: "creatine", date: day, amount: 3, unit: "g" },
  { kind: "supplement", date: day, name: "Creatine", amount: 2, unit: "g" },
  { kind: "supplement", date: day, name: "Vitamin D <test>", amount: 1, unit: "tablet" },
  { kind: "sleep", date: day, period: "night", hours: 7, continuous_hours: 5 },
  { kind: "sleep", date: day, period: "afternoon", hours: 2 },
  { kind: "meal", date: rest, protein: 80 },
  { kind: "plan", date: rest, exercises: [{ exercise_id: "curl" }] },
];
const ctx = {
  state: { today: rest, entries, insights: { daily: { [day]: { workouts: 1 }, [rest]: { workouts: 0 } } } },
  byId: { curl: { name: "Curl", primaryMuscles: ["biceps"], bodyParts: ["Biceps"] } },
  BodyMap: require("../src/fitness_tracker/web/body-map.js"),
  GoalTracking: require("../src/fitness_tracker/web/goals.js"),
  dateLabel: d => d,
};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf("const esc ="), source.indexOf("const iconPaths =")), ctx);
vm.runInContext(source.slice(source.indexOf("function heatmap("), source.indexOf("function dayEntries(")), ctx);
vm.runInContext(source.slice(source.indexOf("function sleepSummary("), source.indexOf("function sleepJournal(")), ctx);
let html = ctx.habitDayDetails(day);
assert.match(html, /Workout day/);
assert.match(html, /1 exercise · 2 sets/);
assert.match(html, /Focus areas<\/dt><dd>Biceps/);
assert.match(html, /55 g · 2 meals/);
assert.match(html, /Creatine<\/dt><dd>5 g/);
assert.match(html, /Vitamin D &lt;test&gt; · 1 tablet/);
assert.doesNotMatch(html, /<test>/);
assert.match(html, /9 h total · 7 h night · 2 h naps/);
assert.match(html, /5 h uninterrupted/);
html = ctx.habitDayDetails(rest);
assert.match(html, /Rest day/);
assert.match(html, /No workout logged/);
assert.match(html, /80 g · 1 meal/);
assert.match(html, /Creatine<\/dt><dd>Not logged/);
assert.match(html, /Sleep<\/dt><dd>Not logged/);
assert.doesNotMatch(html, /Focus areas/);
html = ctx.habitDayDetails("2026-11-16");
assert.match(html, /Protein<\/dt><dd>Not logged/);
html = ctx.heatmap();
assert.match(html, /class="heat-cell rest/);
assert.match(html, /data-action="activity-day" data-date="2026-11-17"/);
assert.doesNotMatch(html, /title=/, "rich day details should replace the duplicate native tooltip");
assert.equal(entries[0].exercises[0].sets[0].weight, 10);
console.log("Habit details passed: daily totals, focus areas, rest days, plans excluded, legacy creatine, sleep, missing logs and escaped names.");

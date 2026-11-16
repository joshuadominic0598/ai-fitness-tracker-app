"use strict";
const assert = require("node:assert/strict");
const G = require("../src/fitness_tracker/web/goals.js");
assert.deepEqual(G.windowFor({ period: 1, unit: "week" }, "2026-11-10"), {
  start: "2026-11-09",
  end: "2026-11-15",
});
assert.deepEqual(G.windowFor({ period: 2, unit: "week" }, "2026-01-01"), {
  start: "2025-12-22",
  end: "2026-01-04",
});
assert.deepEqual(G.windowFor({ period: 3, unit: "day" }, "2024-03-01"), {
  start: "2024-02-28",
  end: "2024-03-01",
});
const entries = [
  { kind: "meal", date: "2026-11-09", protein: 98 },
  { kind: "meal", date: "2026-11-10", protein: 102 },
  { kind: "meal", date: "2026-11-11", protein: 500 }, // future
  { kind: "workout", date: "2026-11-09" },
  { kind: "workout", date: "2026-11-09" },
  { kind: "plan", date: "2026-11-10" },
  {
    kind: "supplement",
    date: "2026-11-09",
    name: "Creatine",
    unit: "g",
    amount: 5,
  },
  {
    kind: "supplement",
    date: "2026-11-09",
    name: "Creatine",
    unit: "capsule",
    amount: 20,
  },
];
assert.equal(
  G.progress(
    entries,
    { amount: 3, period: 1, unit: "week" },
    "workout",
    "2026-11-10",
    "2026-11-10",
  ).value,
  1,
);
assert.equal(
  G.progress(
    entries,
    { amount: 35, period: 1, unit: "week" },
    "creatine",
    "2026-11-10",
    "2026-11-10",
  ).value,
  5,
);
assert.equal(
  G.progress(
    entries,
    { amount: 700, period: 1, unit: "week" },
    "protein",
    "2026-11-10",
    "2026-11-10",
  ).value,
  200,
);
const metric = G.intakeMetrics(
  entries,
  "protein",
  { amount: 100, period: 1, unit: "day" },
  "2026-11-09",
  "2026-11-10",
);
assert.equal(metric.day.percent, 98);
assert.equal(metric.history.days, 1); // Today is not in exact-hit/completed-day metrics.
assert.equal(metric.history.met, 0);
assert.equal(metric.history.attainment, 98);
assert.equal(metric.week.value, 200); // The chosen week includes all logged days through today.
const later = G.intakeMetrics(
  entries,
  "protein",
  { amount: 100, period: 1, unit: "day" },
  "2026-11-10",
  "2026-11-11",
);
assert.equal(later.history.days, 2);
assert.equal(later.history.met, 1);
assert.equal(later.history.percent, 100); // Weekly/aggregate quantity can compensate across days.
assert.equal(later.history.attainment, 99); // Per-day attainment does not hide a low day.
const weekly = G.intakeMetrics(
  entries,
  "protein",
  { amount: 700, period: 1, unit: "week" },
  "2026-11-10",
  "2026-11-10",
);
assert.equal(weekly.isDailyGoal, false);
assert.equal(weekly.day.target, 100);
assert.equal(weekly.week.target, 700);
assert.equal(
  G.intakeMetrics(
    [],
    "protein",
    { amount: 100, period: 1, unit: "day" },
    "2026-11-10",
    "2026-11-10",
  ).history.percent,
  null,
);
assert.equal(
  G.intakeMetrics(
    entries,
    "creatine",
    { amount: 0, period: 1, unit: "day" },
    "2026-11-10",
    "2026-11-10",
  ).day.percent,
  null,
);
console.log(
  "Goal checks passed: calendar windows, historical dates, unit-aware totals, percent attainment, exact hits excluding today, and quantity versus daily coverage.",
);

const suppRecords = [
  {
    kind: "supplement",
    name: "Collagen",
    date: "2026-11-09",
    amount: 500,
    unit: "mg",
  },
  {
    kind: "supplement",
    name: "Collagen",
    date: "2026-11-09",
    amount: 0.5,
    unit: "g",
  },
  {
    kind: "supplement",
    name: "Collagen",
    date: "2026-11-09",
    amount: 1,
    unit: "capsule",
  },
];
const sg = { amount: 1, measure: "g", period: 1, unit: "day" };
assert.equal(
  G.supplementProgress(suppRecords, sg, "Collagen", "2026-11-09", "2026-11-10")
    .value,
  1,
);
assert.equal(
  G.supplementProgress(
    suppRecords,
    { ...sg, measure: "days" },
    "Collagen",
    "2026-11-09",
    "2026-11-10",
  ).value,
  1,
);
assert.equal(
  G.supplementProgress(
    suppRecords,
    { ...sg, measure: "doses" },
    "Collagen",
    "2026-11-09",
    "2026-11-10",
  ).value,
  3,
);
assert.equal(
  G.supplementProgress(suppRecords, sg, "Collagen", "2026-11-09", "2026-11-10")
    .incompatible,
  1,
);
console.log(
  "Supplement progress checks passed: convertible masses, unique days, dose counts and incompatible units.",
);

"use strict";
const G = require("../src/fitness_tracker/web/goals.js"),
  assert = require("node:assert/strict");
for (const [reference, end, days] of [
  ["2026-11-09", "2026-11-30", 30],
  ["2026-12-01", "2026-12-31", 31],
  ["2027-02-04", "2027-02-28", 28],
  ["2028-02-04", "2028-02-29", 29],
  ["2048-02-04", "2048-02-29", 29],
  ["2050-02-04", "2050-02-28", 28],
]) {
  const window = G.windowFor({ period: 1, unit: "month" }, reference);
  assert.equal(window.start, reference.slice(0, 7) + "-01");
  assert.equal(window.end, end);
  assert.equal(G.monthCoverage([], reference, reference).days, days);
}
assert.deepEqual(G.windowFor({ period: 1, unit: "week" }, "2050-01-01"), {
  start: "2049-12-27",
  end: "2050-01-02",
});
assert.deepEqual(G.windowFor({ period: 2, unit: "month" }, "2028-03-10"), {
  start: "2028-02-01",
  end: "2028-03-31",
});
const entries = [
  { kind: "meal", date: "2026-11-01", protein: 98 },
  { kind: "meal", date: "2026-11-09", protein: 110 },
  { kind: "meal", date: "2026-11-09", protein: 5 },
  { kind: "meal", date: "2026-10-31", protein: 100 },
  { kind: "meal", date: "2026-11-30", protein: 200 },
  {
    kind: "supplement",
    date: "2026-11-09",
    name: "Creatine",
    amount: 5,
    unit: "g",
  },
];
const coverage = G.monthCoverage(entries, "2026-11-09", "2026-11-10");
assert.equal(coverage.foodDays, 2);
assert.equal(coverage.creatineDays, 1);
assert.equal(coverage.days, 30);
const metric = G.intakeMetrics(
  entries,
  "protein",
  { amount: 3000, period: 1, unit: "month" },
  "2026-11-09",
  "2026-11-10",
);
assert.equal(metric.day.target, 100);
assert.equal(metric.month.target, 3000);
assert.equal(metric.month.value, 213);
assert.equal(metric.history.start, "2026-11-01");
assert.equal(metric.history.days, 9);
const feb = G.intakeMetrics(
  [],
  "protein",
  { amount: 2800, period: 1, unit: "month" },
  "2050-02-15",
  "2050-02-28",
);
assert.equal(feb.day.target, 100);
assert.equal(feb.month.days, 28);
console.log(
  "Calendar checks passed: Monday–Sunday weeks, actual month lengths, leap years through 2050, monthly quantity targets and no future credit.",
);

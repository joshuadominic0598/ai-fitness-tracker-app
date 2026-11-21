"use strict";
const assert = require("node:assert/strict");
const G = require("../src/fitness_tracker/web/goals.js");
const D = require("../src/fitness_tracker/web/dashboard.js");
const cardio = (minutes, intensity, date = "2026-11-18") => ({ kind: "cardio", activity: "Badminton", minutes, intensity, date });
const today = "2026-11-19";
for (const [goal, logs, expected] of [
  [{ moderate: 150, high: 0 }, [cardio(75, "high")], 100],
  [{ moderate: 0, high: 30 }, [cardio(80, "moderate")], 100 * 80 / 60],
  [{ moderate: 60, high: 30 }, [cardio(60, "moderate"), cardio(30, "high")], 100],
  [{ moderate: 90, high: 0 }, [cardio(30, "high")], 100 * 60 / 90],
]) {
  const p = G.cardioProgress([...logs, cardio(900, "high", "2026-11-22"), cardio(900, "high", "2026-11-15")], goal, "2026-11-18", today);
  assert.ok(Math.abs(p.percent - expected) < 1e-9);
  assert.equal(p.minutes, logs.reduce((sum, e) => sum + e.minutes, 0));
}
assert.equal(G.cardioProgress([], {}, today, today).percent, null);
const profile = { goals: { workout: { amount: 3, period: 1, unit: "week" } }, cardio_goal: { moderate: 150, high: 0 } };
const logs = [cardio(30, "high", "2026-11-16"), cardio(90, "moderate", "2026-11-18")];
const calendar = D.calendar(logs, profile, "2026-11", "cardio", today);
const week = calendar.weeks.find(w => w.start === "2026-11-16");
assert.equal(week.percent, 100);
assert.equal(week.days[0].ratio, 0.4);
assert.equal(week.days[2].ratio, 1);
assert.equal(week.days[4].tone, "future");
assert.equal(week.tone, "met");
assert.equal(G.progress(logs, profile.goals.workout, "workout", today, today).value, 0);
const meals = [
  { kind: "meal", date: "2026-11-16", protein: 10, calories: 200 },
  { kind: "meal", date: "2026-11-16", protein: 20, calories: 300 },
  { kind: "meal", date: today, protein: 30, calories: 999 },
  { kind: "meal", date: "2026-11-20", protein: 30, calories: 999 },
];
let m = G.calorieMetrics(meals, today, today);
assert.equal(m.day.value, 999);
assert.equal(m.week.value, 1499);
assert.equal(m.history.average, 500 / 3);
assert.equal(m.history.days, 3);
assert.equal(G.calorieMetrics([], "2026-11-16", "2026-11-16").history.average, null);
const legacy = { kind: "meal", date: "2026-11-17", protein: 5 };
m = G.calorieMetrics([...meals, legacy], today, today);
assert.equal(m.week.missing, 1);
assert.equal(m.history.average, null, "unknown calories must not produce a falsely complete average");
assert.equal(m.history.value, 500);
assert.deepEqual(D.intakeSeries([...meals, legacy], "calories", "daily", today), [
  { start: "2026-11-16", end: "2026-11-16", value: 500 },
  { start: today, end: today, value: 999 },
]);
assert.equal(D.intakeSeries([...meals, legacy], "calories", "weekly", today)[0].value, 1499);
console.log("Cardio and calories passed: 2:1 goal credit, mixed targets, weekly calendar, strength separation, calorie totals and missing-data handling.");

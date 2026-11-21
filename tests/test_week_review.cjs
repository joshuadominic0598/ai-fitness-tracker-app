"use strict";
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  vm = require("node:vm");
const D = require("../src/fitness_tracker/web/dashboard.js"),
  G = require("../src/fitness_tracker/web/goals.js");
const profile = {
  weekly_goal: 3,
  goals: {
    workout: { amount: 3, period: 1, unit: "week" },
    protein: { amount: 100, period: 1, unit: "day" },
    creatine: { amount: 3, period: 1, unit: "day" },
  },
  supplements: ["Creatine", "Vitamin D"],
  consistency_supplements: ["Creatine", "Vitamin D"],
  supplement_goals: {
    "Vitamin D": { amount: 14, measure: "tablet", period: 1, unit: "week" },
  },
};
const log = (date, amount, name = "Vitamin D", unit = "tablet") => ({
  kind: "supplement",
  date,
  name,
  amount,
  unit,
});
const supplements = [
  log("2026-11-09", 2),
  log("2026-11-10", 2),
  log("2026-11-12", 2),
  log("2026-11-13", 2),
  log("2026-11-14", 2),
  log("2026-11-15", 3),
];
let cal = D.calendar(
    supplements,
    profile,
    "2026-11",
    "supplements",
    "2026-11-14",
  ),
  week = cal.weeks.find((w) => w.start === "2026-11-09");
assert.ok(Math.abs(week.percent - 1000 / 14) < 1e-8);
assert.ok(
  week.days.every(
    (d) => d.tone === (d.day > "2026-11-14" ? "future" : "building"),
  ),
  "elapsed days stay blue; future days stay dark",
);
for (const [index, total] of [
  [8, 2],
  [9, 4],
  [10, 4],
  [11, 6],
  [12, 8],
  [13, 10],
  [14, 10],
])
  assert.ok(
    Math.abs(cal.days[index].ratio - total / 14) < 1e-9,
    "daily supplement display is cumulative weekly progress; future entries excluded",
  );
cal = D.calendar(supplements, profile, "2026-11", "supplements", "2026-11-16");
week = cal.weeks.find((w) => w.start === "2026-11-09");
assert.ok(Math.abs(week.percent - 1300 / 14) < 1e-8);
assert.ok(
  week.days.every((d) => d.tone === "met"),
  "90%+ turns the entire week green",
);
assert.equal(
  cal.weeks.find((w) => w.start === "2026-11-16").percent,
  0,
  "reset cumulative totals each Monday",
);
assert.equal(cal.days[15].ratio, 0);
assert.equal(cal.days[15].tone, "building", "today can show weekly progress");
assert.equal(
  cal.days[16].tone,
  "future",
  "tomorrow keeps the shared dark future style",
);
assert.equal(
  cal.weeks.find((w) => w.start === "2026-11-23").tone,
  "unlogged",
  "entirely future weekly scores stay neutral like protein",
);
const exact = {
  ...profile,
  supplement_goals: {
    "Vitamin D": { amount: 10, measure: "tablet", period: 1, unit: "week" },
  },
};
assert.equal(
  D.calendar(
    [log("2026-11-09", 9)],
    exact,
    "2026-11",
    "supplements",
    "2026-11-16",
  ).days[8].tone,
  "met",
);
const earlyCompletion = D.calendar(
  [log("2026-11-09", 9)],
  exact,
  "2026-11",
  "supplements",
  "2026-11-10",
);
assert.equal(earlyCompletion.days[8].tone, "met");
assert.equal(earlyCompletion.days[9].tone, "met");
assert.equal(
  earlyCompletion.days[10].tone,
  "future",
  "hitting 90% early must not color future days",
);
assert.equal(
  earlyCompletion.weeks.find((w) => w.start === "2026-11-09").percent,
  90,
  "future styling does not change weekly completion",
);
const mixed = {
  ...profile,
  supplements: ["Vitamin D", "Vitamin C"],
  consistency_supplements: ["Vitamin D", "Vitamin C"],
  supplement_goals: {
    "Vitamin D": { amount: 14, measure: "tablet", period: 1, unit: "week" },
    "Vitamin C": { amount: 14, measure: "tablet", period: 1, unit: "week" },
  },
};
assert.equal(
  D.calendar(
    [log("2026-11-09", 28)],
    mixed,
    "2026-11",
    "supplements",
    "2026-11-16",
  ).weeks.find((w) => w.start === "2026-11-09").percent,
  50,
  "extra doses of one supplement cannot replace another goal",
);
const creatine = [log("2026-11-09", 5, "Creatine", "g")];
week = D.calendar(
  creatine,
  profile,
  "2026-11",
  "creatine",
  "2026-11-09",
).weeks.find((w) => w.start === "2026-11-09");
assert.ok(
  Math.abs(week.percent - 500 / 21) < 1e-8,
  "future days count zero against full-week creatine target",
);
assert.ok(week.days.slice(1).every((d) => d.ratio === 0));
assert.equal(
  week.status,
  undefined,
  "calendar week no longer classifies Met or Met so far",
);
const meals = Array.from({ length: 7 }, (_, i) => ({
  kind: "meal",
  date: `2026-11-${String(9 + i).padStart(2, "0")}`,
  protein: 90,
}));
const records = [
  ...supplements,
  ...creatine,
  ...meals,
  { kind: "workout", date: "2026-11-09" },
  { kind: "workout", date: "2026-11-09" },
  { kind: "workout", date: "2026-11-11" },
];
const targets = D.weeklyTargets(records, profile, "2026-11-12", "2026-11-16");
assert.equal(targets.start, "2026-11-09");
assert.deepEqual(
  targets.rows.map((r) => [r.key, r.value, r.target]),
  [
    ["workout", 2, 3],
    ["protein", 630, 700],
    ["creatine", 5, 21],
  ],
);
const historical = G.intakeMetrics(
  records,
  "protein",
  profile.goals.protein,
  "2026-11-12",
  "2026-11-16",
  { historyPeriod: "week" },
);
assert.equal(historical.week.value, 630);
assert.equal(historical.week.percent, 90);
assert.equal(historical.history.start, "2026-11-09");
assert.equal(historical.history.end, "2026-11-15");
assert.equal(historical.history.days, 7);
assert.equal(historical.history.attainment, 90);
assert.equal(historical.history.average, 90);
const current = G.intakeMetrics(
  records,
  "protein",
  profile.goals.protein,
  "2026-11-16",
  "2026-11-16",
  { historyPeriod: "week" },
);
assert.equal(current.week.value, 0);
assert.equal(current.history.days, 0);
assert.equal(current.history.average, null);
const partialWeekEntries = [
  { kind: "meal", date: "2026-11-09", protein: 140 },
  { kind: "meal", date: "2026-11-09", protein: 70 },
  { kind: "meal", date: "2026-11-11", protein: 80 }, // Today.
  { kind: "meal", date: "2026-11-12", protein: 900 }, // Future.
  { kind: "creatine", date: "2026-11-09", amount: 3, unit: "g" },
  log("2026-11-09", 2, "Creatine", "g"), // Legacy gram entry.
  log("2026-11-09", 10, "Creatine", "capsule"),
  log("2026-11-11", 5, "Creatine", "g"),
];
for (const [key, average] of [["protein", 105], ["creatine", 2.5]]) {
  const metrics = G.intakeMetrics(
    partialWeekEntries, key, { ...profile.goals[key], amount: 0 },
    "2026-11-10", "2026-11-11", { historyPeriod: "week" },
  );
  assert.equal(metrics.history.days, 2);
  assert.equal(metrics.history.average, average,
    "average includes missing days, excludes today/future, and works without a target");
  assert.equal(G.intakeMetrics(
    [], key, profile.goals[key], "2026-11-10", "2026-11-11",
    { historyPeriod: "week" },
  ).history.average, 0, "completed days without logs average zero");
}
const dedicatedCreatine = {
  kind: "creatine",
  date: "2026-11-09",
  name: "Creatine",
  amount: 5,
  unit: "g",
};
const dedicatedProfile = {
  ...profile,
  supplements: ["Vitamin D"],
  consistency_supplements: ["Vitamin D"],
};
assert.equal(
  G.intakeMetrics(
    [dedicatedCreatine],
    "creatine",
    profile.goals.creatine,
    "2026-11-09",
    "2026-11-16",
  ).day.value,
  5,
);
assert.equal(
  G.monthCoverage([dedicatedCreatine], "2026-11-09", "2026-11-16").creatineDays,
  1,
);
assert.equal(
  D.calendar(
    [dedicatedCreatine],
    dedicatedProfile,
    "2026-11",
    "creatine",
    "2026-11-16",
  ).days[8].value,
  5,
);
assert.equal(
  D.weeklyTargets(
    [dedicatedCreatine],
    dedicatedProfile,
    "2026-11-09",
    "2026-11-16",
  ).rows.find((r) => r.key === "creatine").value,
  5,
);
assert.equal(
  D.calendar(
    [dedicatedCreatine],
    dedicatedProfile,
    "2026-11",
    "supplements",
    "2026-11-16",
  ).loggedDays,
  0,
  "creatine does not count toward supplement tracking",
);
const source = fs.readFileSync(
  require.resolve("../src/fitness_tracker/web/app.js"),
  "utf8",
);
const ctx = {
  Dashboard: D,
  GoalTracking: G,
  state: { entries: records, profile, today: "2026-11-16" },
  reviewDate: "2026-11-12",
  dateLabel: String,
  esc: String,
  n: (v) =>
    Number(v || 0)
      .toFixed(1)
      .replace(/\.0$/, ""),
  goalPeriodText: () => "per week",
  goalRange: (r) => `${r.start} – ${r.end}`,
  button: (label, action, kind, attrs) =>
    `<button data-action="${action}" ${attrs || ""}>${label}</button>`,
  supplementUnitLabel: (u) => u,
};
vm.createContext(ctx);
vm.runInContext(
  source.slice(
    source.indexOf("function reviewWeekControls("),
    source.indexOf("function overview("),
  ),
  ctx,
);
vm.runInContext(
  source.slice(
    source.indexOf("function nutritionMetrics("),
    source.indexOf("function nutrition("),
  ),
  ctx,
);
let html = ctx.weeklyGoalsPanel();
for (const label of ["Gym days", "Protein", "Creatine", "Vitamin D"])
  assert.ok(html.includes(`<h3>${label}</h3>`));
assert.match(html, /2<\/strong><span>\/ 3 days/);
assert.match(html, /630<\/strong><span>\/ 700 g/);
assert.match(html, /2026-11-09 – 2026-11-15/);
html = ctx.nutritionMetrics();
assert.match(html, /review-week-prev/);
assert.match(html, /value="2026-11-12"/);
assert.match(html, /630 \/ 700 g/);
assert.match(html, /7<small> completed days/);
assert.match(html, /Average daily intake<\/span><strong>90 g\/day/);
assert.match(html, /Average daily intake<\/span><strong>0\.7 g\/day/);
ctx.reviewDate = "2026-11-16";
assert.match(ctx.nutritionMetrics(), /0 \/ 700 g/);
assert.equal((ctx.nutritionMetrics().match(/Average daily intake<\/span><strong>—/g) || []).length, 3);
assert.match(ctx.weeklyGoalsPanel(), /2026-11-16 – 2026-11-22/);
console.log(
  "Week review passed: historical navigation, full-week targets, overview categories, cumulative supplements, 90% green rows and zero-filled future days.",
);

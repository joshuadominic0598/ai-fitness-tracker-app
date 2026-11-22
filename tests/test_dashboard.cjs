"use strict";
const assert = require("node:assert/strict"),
  d = require("../src/fitness_tracker/web/dashboard.js");
const profile = {
  goals: {
    protein: { amount: 100, period: 1, unit: "day" },
    creatine: { amount: 5, period: 1, unit: "day" },
  },
  sleep_goal: 7,
  night_hours_goal: 6,
  consistency_supplements: ["Creatine", "Vitamin D"],
  supplement_goals: {
    "Vitamin D": { amount: 1, period: 1, unit: "day", measure: "tablet" },
  },
};
const entries = [
  { kind: "workout", date: "2026-11-09" },
  { kind: "meal", date: "2026-11-09", protein: 98 },
  { kind: "meal", date: "2026-11-10", protein: 80 },
  {
    kind: "supplement",
    date: "2026-11-09",
    name: "Vitamin D",
    amount: 1,
    unit: "tablet",
  },
  {
    kind: "supplement",
    date: "2026-11-09",
    name: "Creatine",
    amount: 5,
    unit: "g",
  },
  { kind: "sleep", date: "2026-11-09", period: "night", hours: 6.5 },
  { kind: "sleep", date: "2026-11-09", period: "afternoon", hours: 1 },
  { kind: "workout", date: "2026-11-15" },
];
let data = d.calendar(entries, profile, "2026-11", "protein", "2026-11-12");
assert.equal(data.days.length, 30);
assert.equal(data.offset, 6, "Monday-first alignment");
assert.equal(data.days[8].tone, "met", "98% is brightest green");
assert.equal(data.days[9].tone, "near", "80% is medium green");
assert.equal(data.days[10].tone, "unlogged");
assert.equal(data.days[14].tone, "future");
assert.equal(data.days[14].ratio, 0);
assert.equal(
  d.calendar(entries, profile, "2026-11", "workout", "2026-11-12").loggedDays,
  1,
  "future workout is not credited",
);
assert.ok(
  Math.abs(
    d.calendar(entries, profile, "2026-11", "supplements", "2026-11-12").days[8]
      .ratio -
      1 / 7,
  ) < 1e-9,
  "supplement days show cumulative weekly progress",
);
assert.equal(
  d.calendar(entries, profile, "2026-11", "sleep", "2026-11-12").days[8].ratio,
  1,
  "night sleep plus naps can meet both core goals",
);
assert.equal(
  d.calendar(entries, profile, "2028-02", "workout", "2028-02-29").days.length,
  29,
);
assert.equal(
  d.calendar(entries, profile, "2050-12", "workout", "2050-12-31").days.length,
  31,
);
assert.equal(
  d.dailyTarget({ amount: 700, period: 1, unit: "week" }, "2026-11-09"),
  100,
);
assert.equal(
  d.dailyTarget({ amount: 2900, period: 1, unit: "month" }, "2028-02-29"),
  100,
);
assert.equal(d.tone(0, false, false), "unlogged");
assert.equal(d.tone(0.98, true, false), "met");
console.log(
  "Dashboard checks passed: friendly near-goal colors, real month lengths, Monday alignment, goal units, sleep and no future credit.",
);

for (const [ratio, expected] of [
  [0, "critical"], [0.2499, "critical"], [0.25, "critical"], [0.4999, "critical"],
  [0.5, "low"], [0.5999, "low"],
  [0.6, "mid"], [0.6999, "mid"],
  [0.7, "partial"], [0.7999, "partial"],
  [0.8, "near"], [0.8999, "near"],
  [0.9, "met"], [0.95, "met"], [1, "met"], [1.12, "met"],
]) {
  assert.equal(d.tone(ratio, true, false), expected);
}
const excess = [
  {
    kind: "supplement",
    date: "2026-11-12",
    name: "Creatine",
    amount: 5.6,
    unit: "g",
  },
];
const over = d.calendar(excess, profile, "2026-11", "creatine", "2026-11-13")
  .days[11];
assert.equal(
  Math.round(over.ratio * 100),
  112,
  "above-goal intake remains visible as 112%",
);
assert.equal(over.tone, "met");
assert.match(over.note, /112%/);
const extraProtein = d.calendar(
  [{ kind: "meal", date: "2026-11-12", protein: 125 }],
  profile,
  "2026-11",
  "protein",
  "2026-11-13",
).days[11];
assert.equal(extraProtein.ratio, 1.25, "protein quantity is also uncapped");

// Week summaries always cover Monday–Sunday, even across month boundaries.
const weekFor = (data, start) => data.weeks.find((w) => w.start === start);
const fullWeek = Array.from({ length: 7 }, (_, i) => ({
  kind: "meal",
  date: `2026-11-${String(2 + i).padStart(2, "0")}`,
  protein: 80,
}));
let week = weekFor(
  d.calendar(fullWeek, profile, "2026-11", "protein", "2026-11-13"),
  "2026-11-02",
);
assert.equal(week.end, "2026-11-08");
assert.ok(Math.abs(week.percent - 80) < 1e-9);
assert.equal(week.tone, "near");
assert.equal(week.days.length, 7);
const current = [
  {
    kind: "supplement",
    date: "2026-11-09",
    name: "Creatine",
    amount: 5.6,
    unit: "g",
  },
  {
    kind: "supplement",
    date: "2026-11-10",
    name: "Creatine",
    amount: 5.6,
    unit: "g",
  },
  {
    kind: "supplement",
    date: "2026-11-15",
    name: "Creatine",
    amount: 100,
    unit: "g",
  },
];
week = weekFor(
  d.calendar(current, profile, "2026-11", "creatine", "2026-11-10"),
  "2026-11-09",
);
assert.ok(
  Math.abs(week.percent - 224 / 7) < 1e-9,
  "weekly intake always divides by seven, with uncapped daily intake",
);
assert.equal(week.tone, "critical");
assert.match(week.note, /all 7/);
week = weekFor(
  d.calendar(current, profile, "2026-11", "creatine", "2026-11-11"),
  "2026-11-09",
);
assert.ok(
  Math.abs(week.percent - 224 / 7) < 1e-9,
  "future and missing days count as zero",
);
week = weekFor(
  d.calendar(
    entries,
    { ...profile, weekly_goal: 3 },
    "2026-11",
    "workout",
    "2026-11-12",
  ),
  "2026-11-09",
);
assert.ok(
  Math.abs(week.percent - 100 / 3) < 1e-9,
  "gym score uses weekly attendance target, not seven daily workouts",
);
const twoGymDays = [
  { kind: "workout", date: "2026-11-09" },
  { kind: "workout", date: "2026-11-09" },
  { kind: "workout", date: "2026-11-10" },
];
week = weekFor(
  d.calendar(
    twoGymDays,
    {
      ...profile,
      goals: {
        ...profile.goals,
        workout: { amount: 6, period: 2, unit: "week" },
      },
    },
    "2026-11",
    "workout",
    "2026-11-13",
  ),
  "2026-11-09",
);
assert.ok(
  Math.abs(week.percent - 200 / 3) < 1e-9,
  "duplicate workouts count once and multiweek targets normalize to weekly shares",
);
const boundary = Array.from({ length: 7 }, (_, i) => ({
  kind: "meal",
  date: i < 6 ? `2026-10-${26 + i}` : "2026-11-01",
  protein: 100,
}));
week = d.calendar(boundary, profile, "2026-11", "protein", "2026-11-13")
  .weeks[0];
assert.equal(week.start, "2026-10-26");
assert.equal(week.end, "2026-11-01");
assert.equal(
  week.percent,
  100,
  "adjacent month records count in the full week",
);
assert.equal(week.days.filter((day) => day.outsideMonth).length, 6);
const upcoming = weekFor(
  d.calendar(entries, profile, "2026-11", "protein", "2026-11-13"),
  "2026-11-16",
);
assert.equal(upcoming.percent, 0);
const off = weekFor(
  d.calendar(
    entries,
    {
      ...profile,
      goals: {
        ...profile.goals,
        creatine: { amount: 0, period: 1, unit: "day" },
      },
    },
    "2026-11",
    "creatine",
    "2026-11-13",
  ),
  "2026-11-09",
);
assert.equal(off.percent, null);
assert.equal(
  d.calendar([], profile, "2028-02", "protein", "2028-02-29").weeks.at(-1).end,
  "2028-03-05",
);
assert.equal(
  d.calendar([], profile, "2050-12", "protein", "2050-12-31").weeks.at(-1).end,
  "2051-01-01",
);

// Render the real calendar template, including the eighth column and full row alignment.
const vm = require("node:vm"),
  fs = require("node:fs");
const source = fs.readFileSync(
  require.resolve("../src/fitness_tracker/web/app.js"),
  "utf8",
);
const view = {
  Dashboard: d,
  state: { entries: current, profile, today: "2026-11-10" },
  dashboardMonth: "2026-11",
  dashboardMetric: "creatine",
  esc: String,
  n: (number) => Number(number.toFixed(1)),
  dateLabel: String,
  button: (label, action) =>
    `<button data-action="${action}">${label}</button>`,
};
vm.createContext(view);
vm.runInContext(
  source.slice(
    source.indexOf("function activityDayHtml("),
    source.indexOf("function updateActivityCalendar("),
  ),
  view,
);
const calendarHtml = view.activityCalendarInner();
assert.match(calendarHtml, /Weekly score/);
assert.equal(
  (calendarHtml.match(/class="activity-day weekly-score /g) || []).length,
  6,
);
assert.equal(
  (calendarHtml.match(/data-action="activity-day"/g) || []).length,
  30,
);
assert.match(calendarHtml, /data-week-start="2026-11-09"[^>]*32%/);
assert.doesNotMatch(calendarHtml, /Met so far/);
assert.doesNotMatch(calendarHtml, />Upcoming</);
const weeklySupplementProfile = {
  ...profile,
  supplement_goals: {
    "Vitamin D": { amount: 1, period: 1, unit: "week", measure: "tablet" },
  },
};
const weeklySupplement = weekFor(
  d.calendar(
    [
      {
        kind: "supplement",
        date: "2026-11-02",
        name: "Vitamin D",
        amount: 1,
        unit: "tablet",
      },
    ],
    weeklySupplementProfile,
    "2026-11",
    "supplements",
    "2026-11-13",
  ),
  "2026-11-02",
);
assert.equal(
  weeklySupplement.percent,
  100,
  "weekly supplement quantities are not lost to daily caps",
);

const panelProfile = {
  supplements: ["Creatine", "Vitamin D", "Vitamin C", "Frequency", "No target"],
  goals: { creatine: { amount: 3.5, period: 1, unit: "day" } },
  supplement_goals: {
    "Vitamin D": { amount: 3, measure: "tablet", period: 1, unit: "week" },
    "Vitamin C": { amount: 2, measure: "tablet", period: 1, unit: "week" },
    Frequency: { amount: 3, measure: "days", period: 1, unit: "week" },
  },
};
const panelLog = (name, date, amount, unit) => ({
  kind: "supplement",
  name,
  date,
  amount,
  unit,
});
const panelWeek = d.weeklySupplements(
  [
    panelLog("Vitamin D", "2026-11-09", 2, "tablets"),
    panelLog("Vitamin D", "2026-11-14", 1, "tablet"),
    panelLog("Vitamin D", "2026-11-08", 8, "tablet"),
    panelLog("Vitamin D", "2026-11-15", 8, "tablet"),
    panelLog("Vitamin C", "2026-11-14", 1, "tablet"),
    panelLog("Vitamin C", "2026-11-14", 500, "mg"),
    panelLog("Creatine", "2026-11-09", 7, "g"),
    panelLog("Creatine", "2026-11-10", 3500, "mg"),
    panelLog("Frequency", "2026-11-10", 1, "tablet"),
    panelLog("Frequency", "2026-11-10", 1, "tablet"),
    panelLog("Extra", "2026-11-11", 1, "capsule"),
  ],
  panelProfile,
  "2026-11-14",
  "2026-11-14",
);
const panelRow = (name) => panelWeek.rows.find((r) => r.name === name);
assert.equal(panelWeek.start, "2026-11-09");
assert.equal(panelWeek.end, "2026-11-15");
assert.equal(
  panelWeek.rows.length,
  6,
  "include all configured and logged supplements",
);
assert.equal(panelRow("Vitamin D").value, 3);
assert.equal(panelRow("Vitamin D").achieved, true);
assert.equal(panelRow("Vitamin D").remaining, 0);
assert.equal(panelRow("Vitamin C").value, 1);
assert.equal(panelRow("Vitamin C").remaining, 1);
assert.equal(
  panelRow("Vitamin C").incompatible,
  1,
  "never convert mg to tablets",
);
assert.equal(panelRow("Vitamin C").consumed.length, 2);
assert.equal(panelRow("Creatine").value, 10.5, "convert compatible mass units");
assert.equal(panelRow("Creatine").target, 24.5);
assert.equal(panelRow("Creatine").equivalent, true);
assert.equal(panelRow("Frequency").value, 1, "count a day once");
assert.equal(panelRow("No target").target, null);
assert.equal(panelRow("No target").consumed.length, 0);
assert.equal(panelRow("Extra").target, null);
const newWeek = d.weeklySupplements(
  [panelLog("Vitamin D", "2026-11-14", 3, "tablet")],
  panelProfile,
  "2026-11-16",
  "2026-11-16",
);
assert.equal(
  newWeek.rows.find((r) => r.name === "Vitamin D").value,
  0,
  "reset on Monday",
);
const monthlyPanel = d.weeklySupplements(
  [],
  {
    supplements: ["Monthly"],
    supplement_goals: {
      Monthly: { amount: 30, measure: "tablet", period: 1, unit: "month" },
    },
  },
  "2026-11-01",
  "2026-11-01",
);
assert.ok(Math.abs(monthlyPanel.rows[0].target - ((6 * 30) / 31 + 1)) < 1e-9);

"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const Dashboard = require("../src/fitness_tracker/web/dashboard.js");
const GoalTracking = require("../src/fitness_tracker/web/goals.js");
const source = fs.readFileSync(require.resolve("../src/fitness_tracker/web/app.js"), "utf8");
const day = i => new Date(Date.UTC(2026, 0, 1 + i, 12)).toISOString().slice(0, 10);
const entries = Array.from({ length: 200 }, (_, i) => ({ kind: "meal", date: day(i), protein: i + 1 }));
entries.push({ kind: "meal", date: day(199), protein: 10 });
entries.push({ kind: "meal", date: day(200), protein: 999 });
const daily = Dashboard.intakeSeries([...entries].reverse(), "protein", "daily", day(199));
assert.equal(daily.length, 20);
assert.equal(daily[0].start, day(180));
assert.equal(daily.at(-1).value, 210);
const weekly = Dashboard.intakeSeries(entries, "protein", "weekly", day(199));
assert.equal(weekly.length, 20);
assert.ok(weekly.every(p => new Date(p.start + "T12:00:00Z").getUTCDay() === 1));
const boundary = Dashboard.intakeSeries([
 { kind: "meal", date: "2026-12-31", protein: 10 },
 { kind: "meal", date: "2027-01-03", protein: 20 },
 { kind: "meal", date: "2027-01-04", protein: 5 },
], "protein", "weekly", "2027-01-04");
assert.deepEqual(boundary, [
 { start: "2026-12-28", end: "2027-01-03", value: 30 },
 { start: "2027-01-04", end: "2027-01-10", value: 5 },
]);
assert.deepEqual(Dashboard.intakeSeries([
 { kind: "creatine", date: day(2), amount: 5, unit: "g" },
 { kind: "supplement", name: "Creatine", date: day(2), amount: 2, unit: "g" },
 { kind: "supplement", name: "Vitamin C", date: day(2), amount: 3, unit: "g" },
 { kind: "creatine", date: day(4), amount: 0, unit: "g" },
], "creatine", "daily", day(5)).map(p => p.value), [7, 0]);
assert.deepEqual(Dashboard.intakeSeries([], "protein", "daily", day(0)), []);
const context = { Dashboard, GoalTracking, state: { entries, today: day(199), profile: { goals: { protein: { amount: 100, period: 1, unit: "day" }, creatine: { amount: 5, period: 1, unit: "day" } } } }, intakeMetric: "protein", intakePeriod: "daily", esc: String, n: String, dateLabel: d => d, empty: (a, b) => a + b };
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf("function chart("), source.indexOf("function muscles()")), context);
vm.runInContext(source.slice(source.indexOf("function intakePanel()"), source.indexOf("function papersHtml")), context);
for (const period of ["daily", "weekly"]) {
 context.intakePeriod = period;
 const html = context.intakePanel();
 assert.ok(html.includes("<polyline"));
 assert.equal((html.match(/<circle /g) || []).length, 20);
 assert.ok(!html.includes("<rect"));
 assert.ok(html.includes('aria-pressed="true"'));
 assert.ok(html.includes("View chart data"));
 assert.ok(html.includes(period === "weekly" ? "Monday–Sunday" : "Daily totals"));
}
console.log("Intake chart passed: daily/weekly line charts, latest 20 sorted aggregates, multiple entries, week/year boundaries, future exclusion, creatine aliases, zero and empty data.");

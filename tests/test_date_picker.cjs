"use strict";
const assert = require("node:assert/strict"),
  D = require("../src/fitness_tracker/web/date-picker.js");
const november = D.monthDays("2026-11");
assert.equal(november.length, 42);
assert.equal(november[0].day, "2026-10-26");
assert.equal(
  november[6].day,
  "2026-11-01",
  "November 1 belongs in Sunday column",
);
assert.equal(
  november[20].day,
  "2026-11-15",
  "selected Sunday remains in Sunday column",
);
for (const month of [
  "1900-01",
  "2026-11",
  "2027-02",
  "2028-02",
  "2048-02",
  "2050-12",
]) {
  const days = D.monthDays(month);
  days.forEach((d, i) =>
    assert.equal((new Date(d.day + "T12:00:00Z").getUTCDay() + 6) % 7, i % 7),
  );
}
assert.ok(
  D.monthDays("2028-02").some((d) => d.day === "2028-02-29" && !d.disabled),
);
assert.ok(!D.monthDays("2027-02").some((d) => d.day === "2027-02-29"));
assert.equal(D.moveMonth("2028-01-31", 1), "2028-02-29");
assert.equal(D.moveMonth("2027-01-31", 1), "2027-02-28");
assert.equal(D.moveMonth("2026-12-31", 1), "2027-01-31");
assert.ok(
  D.monthDays("1900-01")
    .filter((d) => d.day < "1900-01-01")
    .every((d) => d.disabled),
);
assert.ok(
  D.monthDays("2050-12")
    .filter((d) => d.day > "2050-12-31")
    .every((d) => d.disabled),
);
assert.equal(D.clamp("2051-01-01"), "2050-12-31");
assert.equal(D.clamp("1899-12-31"), "1900-01-01");
console.log(
  "Date picker checks passed: Monday-first rows, Sunday placement, leap years, month shifts and 1900–2050 bounds.",
);

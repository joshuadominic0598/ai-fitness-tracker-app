"use strict";
const fs = require("node:fs"),
  vm = require("node:vm"),
  assert = require("node:assert/strict");
const source = fs.readFileSync(
  require.resolve("../src/fitness_tracker/web/app.js"),
  "utf8",
);
const helpers = source.slice(
  source.indexOf("function supplementLogUnit("),
  source.indexOf("function goals("),
);
(async () => {
  const form = {},
    unit = { value: "g", dataset: {} },
    amount = { value: "", dataset: {} },
    select = { value: "Collagen" };
  const elements = {
    "#simple-entry-form": form,
    "#entry-unit": unit,
    "#entry-amount": amount,
    "#entry-name": select,
  };
  const fresh = {
    supplement_goals: {
      Collagen: { measure: "tablet" },
      "Vitamin D": { measure: "tablet" },
      Magnesium: { measure: "mg" },
    },
  };
  let resolve;
  const ctx = {
    state: { profile: { supplement_goals: { Collagen: { measure: "g" } } } },
    $: (id) => elements[id],
    api: () => new Promise((r) => (resolve = r)),
  };
  vm.createContext(ctx);
  vm.runInContext(helpers, ctx);
  let pending = ctx.refreshSupplementUnit();
  resolve(fresh);
  await pending;
  assert.equal(unit.value, "tablet", "fresh goal unit replaces cached grams");
  assert.equal(amount.value, "1", "tablet logs default to one without typing");
  assert.equal(ctx.supplementLogUnit("Creatine"), "g");
  select.value = "Magnesium";
  pending = ctx.refreshSupplementUnit();
  resolve(fresh);
  await pending;
  assert.equal(unit.value, "mg", "selection uses its own saved goal");
  assert.equal(amount.value, "", "switching to measured dose removes the tablet default");
  unit.value = "tablet";
  amount.value = "2";
  ctx.syncSupplementAmount(true);
  assert.equal(amount.value, "2", "editing preserves the historical tablet count");
  amount.dataset.manual = "true";
  ctx.syncSupplementAmount();
  assert.equal(amount.value, "2", "explicitly entered tablet counts stay intact");
  delete amount.dataset.manual;
  unit.value = "capsule";
  pending = ctx.refreshSupplementUnit(true);
  resolve(fresh);
  await pending;
  assert.equal(
    unit.value,
    "capsule",
    "opening edit preserves actual historical unit",
  );
  pending = ctx.refreshSupplementUnit();
  unit.dataset.manual = "true";
  unit.value = "scoop";
  resolve(fresh);
  await pending;
  assert.equal(unit.value, "scoop", "late refresh preserves manual input");
  delete unit.dataset.manual;
  pending = ctx.refreshSupplementUnit();
  elements["#simple-entry-form"] = {};
  resolve(fresh);
  await pending;
  assert.equal(
    unit.value,
    "scoop",
    "closed/replaced dialog ignores pending response",
  );
  vm.runInContext(
    source.slice(
      source.indexOf("function sleepSummary("),
      source.indexOf("function sleepJournal("),
    ),
    ctx,
  );
  const result = ctx.sleepSummary([
    { kind: "sleep", hours: 3, period: "night", continuous_hours: 3 },
    { kind: "sleep", hours: 3, period: "night", continuous_hours: 3 },
    { kind: "sleep", hours: 1, period: "afternoon", continuous_hours: null },
  ]);
  assert.equal(result.total, 7);
  assert.equal(result.night, 6);
  assert.equal(result.continuous, 3);
  assert.equal(
    ctx.sleepSummary([
      { kind: "sleep", hours: 7, period: "night", continuous_hours: null },
    ]).known,
    false,
  );
  console.log("Supplement freshness and sleep continuity checks passed.");
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});

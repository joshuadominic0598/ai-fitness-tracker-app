"use strict";
const assert = require("node:assert/strict");
const map = require("../src/fitness_tracker/web/body-map.js");
const catalog = {
  press: {
    name: "Bench press",
    bodyParts: ["Chest"],
    secondaryMuscles: ["triceps", "shoulders"],
  },
  curl: {
    name: "Reverse curl",
    bodyParts: ["Forearms"],
    secondaryMuscles: ["biceps", "forearms"],
  },
  plank: {
    name: "Plank",
    primaryMuscles: ["abdominals"],
    secondaryMuscles: [],
  },
  thigh: {
    name: "Leg press",
    primaryMuscles: ["quadriceps", "hamstrings"],
    secondaryMuscles: ["glutes"],
  },
};
const workout = (date, id, count = 1, reps = 10, seconds = 0) => ({
  kind: "workout",
  date,
  exercises: [
    {
      exercise_id: id,
      sets: Array.from({ length: count }, () => ({ reps, seconds, weight: 0 })),
    },
  ],
});
const current = workout("2026-11-11", "press");
let report = map.summarize([current], catalog);
assert.equal(report.areas.Chest.primary, 1);
assert.equal(report.areas.Triceps.secondary, 1);
assert.equal(report.areas.Triceps.exposure, report.areas.Chest.exposure / 2);
assert.equal(report.areas.Chest.reps, 10);
assert.equal(report.areas.Chest.level, 1);
assert.equal(report.personalized, false);
const usual = [
  workout("2026-11-09", "press", 3),
  workout("2026-11-10", "press", 3),
];
const heavier = [
  workout("2026-11-09", "press", 10),
  workout("2026-11-10", "press", 10),
];
const light = map.summarize([current], catalog, [...usual, current], {
  end: "2026-11-11",
});
const heavy = map.summarize([current], catalog, [...heavier, current], {
  end: "2026-11-11",
});
assert.ok(
  light.areas.Chest.level > heavy.areas.Chest.level,
  "identical current set counts adapt to different users' normal set ranges",
);
assert.ok(
  light.areas.Chest.level < 1,
  "a lower-volume day stays below the user's usual volume",
);
const fewer = workout("2026-11-11", "press", 1, 5);
const lower = map.summarize([fewer], catalog, [...usual, fewer], {
  end: "2026-11-11",
});
assert.ok(
  lower.areas.Chest.level < light.areas.Chest.level,
  "repetitions affect relative emphasis",
);
const holds = [
  workout("2026-11-09", "plank", 3, 0, 30),
  workout("2026-11-10", "plank", 3, 0, 30),
];
const shortHold = workout("2026-11-11", "plank", 1, 0, 15);
report = map.summarize([shortHold], catalog, [...holds, shortHold], {
  end: "2026-11-11",
});
assert.equal(report.areas.Abs.seconds, 15);
assert.equal(report.areas.Abs.reps, 0);
assert.equal(
  report.areas.Abs.exposure,
  0.5,
  "timed exercises use the user's usual seconds per set",
);
report = map.summarize(
  [workout("2026-11-11", "curl", 2), workout("2026-11-11", "thigh", 3)],
  catalog,
);
assert.equal(report.areas.Forearms.primary, 2);
assert.equal(
  report.areas.Forearms.secondary,
  0,
  "a primary muscle is not also counted as secondary",
);
assert.equal(report.areas.Biceps.secondary, 2);
assert.equal(report.areas.Quads.primary, 3, "quad work has its own tally");
assert.equal(
  report.areas.Hamstrings.primary,
  3,
  "hamstring work stays separate from quads",
);
assert.equal(
  report.sessions,
  1,
  "exercise rows on the same day do not inflate workout days",
);
assert.deepEqual(map.period("2026-11-15", "week"), {
  start: "2026-11-09",
  end: "2026-11-15",
});
assert.deepEqual(map.period("2026-11-16", "week"), {
  start: "2026-11-16",
  end: "2026-11-22",
});
assert.deepEqual(map.period("2028-02-29", "day"), {
  start: "2028-02-29",
  end: "2028-02-29",
});
assert.deepEqual(map.period("2050-12-31", "week"), {
  start: "2050-12-26",
  end: "2051-01-01",
});
const future = workout("2026-11-12", "press", 100);
assert.equal(
  map.summarize([current], catalog, [...usual, current, future], {
    end: "2026-11-11",
  }).reference,
  light.reference,
  "future data does not change a historical scale",
);
const weekly = map.summarize(usual, catalog, usual, {
  mode: "week",
  end: "2026-11-15",
});
assert.equal(weekly.areas.Chest.primary, 6);
assert.equal(weekly.mode, "week");
const empty = map.summarize(
  [{ kind: "plan", date: "2026-11-11", exercises: current.exercises }],
  catalog,
);
assert.equal(empty.active.length, 0, "plans never shade completed training");
const html = map.render(report, { preview: true, title: "Daily focus" });
assert.ok(
  html.includes('aria-label="Front body muscle map"') &&
    html.includes('aria-label="Back body muscle map"'),
);
assert.ok(html.includes("AI PREVIEW · NOT SAVED"));
assert.ok(
  html.includes('tabindex="0"') && html.includes('data-muscle="Forearms"'),
);
const escaped = map.render(
  map.summarize([workout("2026-11-11", "press")], {
    ...catalog,
    press: { ...catalog.press, name: '<img src=x onerror="x">' },
  }),
);
assert.ok(!escaped.includes("<img src=x"));
console.log(
  "Body-map checks passed: user-specific ranges, reps/time, primary/secondary deduplication, weekly calendar, preview state and safe accessible rendering.",
);

// The Insights integration excludes future logs even when its calendar week ends later.
{
  const fs = require("node:fs"),
    vm = require("node:vm");
  const source = fs.readFileSync(
    require.resolve("../src/fitness_tracker/web/app.js"),
    "utf8",
  );
  let selected, baseline;
  const context = {
    bodyMapDate: "2026-11-12",
    bodyMapMode: "week",
    journalDate: "2026-11-12",
    state: {
      today: "2026-11-12",
      entries: [workout("2026-11-09", "press"), workout("2026-11-15", "press")],
    },
    byId: catalog,
    dateLabel: (d) => d,
    sessionTitle: (d) => d,
    BodyMap: {
      period: map.period,
      summarize: (records, byId, history) => {
        selected = records;
        baseline = history;
        return { sessions: records.length };
      },
      render: () => "map",
    },
  };
  vm.createContext(context);
  vm.runInContext(
    source.slice(
      source.indexOf("function insightsBodyMapInner()"),
      source.indexOf("function dailyJournal()"),
    ),
    context,
  );
  context.insightsBodyMapInner();
  assert.equal(selected.length, 1);
  assert.equal(baseline.length, 1);
  context.bodyMapMode = "day";
  context.bodyMapDate = "2026-11-15";
  context.insightsBodyMapInner();
  assert.equal(selected.length, 0);
}

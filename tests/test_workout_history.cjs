"use strict";
const assert = require("node:assert/strict");
const H = require("../src/fitness_tracker/web/workout-history.js");
const catalog = {
  Barbell_Curl: { category: "strength" },
  Plank: { category: "strength" },
  Running: { category: "cardio" },
};
const entries = [
  {
    id: "new",
    kind: "workout",
    date: "2026-11-08",
    exercises: [
      {
        exercise_id: "Barbell_Curl",
        sets: [{ weight: 22.5, reps: 8, seconds: 0 }],
      },
    ],
  },
  {
    id: "old",
    kind: "workout",
    date: "2026-11-05",
    exercises: [
      {
        exercise_id: "Barbell_Curl",
        sets: [{ weight: 20, reps: 10, seconds: 0 }],
      },
      {
        exercise_id: "Plank",
        tracking: "time",
        sets: [{ weight: 0, reps: 0, seconds: 45 }],
      },
    ],
  },
  {
    id: "plan",
    kind: "plan",
    date: "2026-11-09",
    exercises: [{ exercise_id: "Running", sets: [{ seconds: 300 }] }],
  },
  {
    id: "future",
    kind: "workout",
    date: "2026-11-20",
    exercises: [{ exercise_id: "Running", sets: [{ seconds: 300 }] }],
  },
];
assert.equal(H.latestWorkout(entries, "2026-11-09").id, "new");
assert.equal(H.latestWorkout(entries, "2026-11-06").id, "old");
assert.equal(H.latestWorkout(entries, "2026-11-01"), null);
assert.equal(H.latestWorkout(entries, "2026-11-09", "new").id, "old");
assert.deepEqual(
  H.usualExercises(entries, "2026-11-09").map((e) => [e.id, e.count]),
  [
    ["Barbell_Curl", 2],
    ["Plank", 1],
  ],
);
const copy = H.makeExercise(entries, "Barbell_Curl", "2026-11-09", catalog);
assert.equal(copy.sets[0].weight, 22.5);
copy.sets[0].weight = 99;
assert.equal(entries[0].exercises[0].sets[0].weight, 22.5);
const plank = H.makeExercise(entries, "Plank", "2026-11-09", catalog);
assert.equal(plank.tracking, "time");
assert.equal(plank.sets[0].seconds, 45);
assert.equal(plank.sets[0].reps, 0);
assert.equal(
  H.makeExercise([], "Plank", "2026-11-09", catalog).sets[0].seconds,
  30,
);
assert.equal(
  H.makeExercise([], "Running", "2026-11-09", catalog).tracking,
  "time",
);
assert.equal(
  H.modeFor({ exercise_id: "Plank", tracking: "reps" }, catalog),
  "time",
);
const duplicate = [
  {
    id: "a",
    kind: "workout",
    date: "2026-11-08",
    exercises: [{ exercise_id: "Plank" }, { exercise_id: "Plank" }],
  },
];
assert.equal(H.usualExercises(duplicate, "2026-11-09")[0].count, 1);
console.log(
  "Workout history checks passed: recall, date cutoff, usual frequency, independent copies, time-only planks.",
);
const bodyCatalog = {
  ...catalog,
  Flat_Bench_Lying_Leg_Raise: { equipment: "body only", category: "strength" },
};
const legRaise = H.makeExercise(
  [],
  "Flat_Bench_Lying_Leg_Raise",
  "2026-11-09",
  bodyCatalog,
);
assert.equal(legRaise.load_mode, "bodyweight");
assert.equal(legRaise.tracking, "reps");
assert.equal(
  H.makeExercise([], "Barbell_Curl", "2026-11-09", bodyCatalog).load_mode,
  "weighted",
);
assert.equal(
  H.makeExercise([], "Plank", "2026-11-09", bodyCatalog).load_mode,
  "bodyweight",
);
assert.equal(
  H.normalize(
    {
      exercise_id: "Barbell_Curl",
      load_mode: "bodyweight",
      sets: [{ weight: 20, reps: 10, seconds: 0 }],
    },
    bodyCatalog,
  ).sets[0].weight,
  0,
);
assert.equal(
  H.normalize(
    {
      exercise_id: "Plank",
      load_mode: "weighted",
      tracking: "time",
      sets: [{ weight: 5, reps: 0, seconds: 45 }],
    },
    bodyCatalog,
  ).sets[0].weight,
  5,
);
assert.equal(
  H.normalize(
    {
      exercise_id: "Flat_Bench_Lying_Leg_Raise",
      sets: [{ weight: 0, reps: 12, seconds: 0 }],
    },
    bodyCatalog,
  ).load_mode,
  "bodyweight",
);
console.log(
  "Bodyweight defaults, explicit load choices, and legacy recall checks passed.",
);

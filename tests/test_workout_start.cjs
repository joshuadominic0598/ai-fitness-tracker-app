"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const WorkoutHistory = require("../src/fitness_tracker/web/workout-history.js");
const source = fs.readFileSync(require.resolve("../src/fitness_tracker/web/app.js"), "utf8");
const saved = {
  id: "saved", date: "2026-11-17", kind: "workout", duration: 45,
  exercises: [{ exercise_id: "Hammer_Curls", sets: [{ weight: 10, reps: 8 }] }],
};
let redraws = 0;
const ctx = {
  state: { today: "2026-11-19", entries: [saved] }, journalDate: "2026-11-18",
  byId: { Hammer_Curls: { equipment: "dumbbell" } }, WorkoutHistory,
  sessionTitle: day => day, drawWorkout: () => redraws++,
};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf("function openWorkout("), source.indexOf("function syncWorkout(")), ctx);
ctx.openWorkout();
assert.equal(ctx.workoutForm.date, "2026-11-18");
assert.equal(ctx.workoutForm.exercises.length, 0, "a new day cannot copy the last session");
ctx.journalDate = saved.date;
ctx.openWorkout();
assert.equal(ctx.workoutForm.exercises.length, 0, "new still means empty on a previously logged day");
ctx.openWorkout("workout", saved);
assert.equal(ctx.workoutForm.id, "saved");
assert.equal(ctx.workoutForm.exercises[0].sets[0].reps, 8, "explicit edits load actual saved sets");
ctx.workoutForm.exercises[0].sets[0].weight = 99;
assert.equal(saved.exercises[0].sets[0].weight, 10, "editing does not mutate saved state");
ctx.openWorkout("plan");
assert.equal(ctx.workoutForm.exercises.length, 0, "new plans also start empty");
assert.equal(redraws, 4);
const picker = source.slice(source.indexOf('    case "pick-exercise": {'), source.indexOf('    case "request-blank-workout":'));
ctx.syncWorkout = () => {};
vm.runInContext(`function pick(el, id) { switch ("pick-exercise") { ${picker} } }`, ctx);
ctx.openWorkout();
ctx.pick({ dataset: {} }, "Hammer_Curls");
assert.equal(ctx.workoutForm.exercises[0].sets[0].reps, 0, "searching a known exercise creates a fresh set");
assert.equal(ctx.workoutForm.exercises[0].sets[0].weight, 0);
ctx.openWorkout();
ctx.pick({ dataset: { recall: "true" } }, "Hammer_Curls");
assert.equal(ctx.workoutForm.exercises[0].sets[0].reps, 8, "recent recall explicitly imports the saved sets");
assert.equal(ctx.workoutForm.exercises[0].sets[0].weight, 10);
console.log("Workout starts passed: empty new days and same days; explicit edits preserved and isolated.");
